'use strict';
'require view';
'require fs';

var CTL = '/usr/bin/zflip3-webcam-ctl';

function kv(s) {
	var o = {};
	(s || '').trim().split('\n').forEach(function(l) {
		var i = l.indexOf('=');
		if (i > 0) o[l.slice(0, i)] = l.slice(i + 1).trim();
	});
	return o;
}

return view.extend({
	title: _('Z Flip3 Webcam & Speaker'),

	load: function() {
		return L.resolveDefault(fs.exec(CTL, [ 'status' ]), {});
	},

	render: function(data) {
		var self = this;
		var host = E('div', { 'class': 'cbi-section' }, [ _('memuat…') ]);
		var fill = function(r) {
			var s = kv(r && r.stdout);
			var on = s.running === '1';
			host.replaceChildren(
				E('table', { 'class': 'table' }, [
					E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td' }, [ _('Stream') ]), E('td', { 'class': 'td' }, [ on ? _('jalan') : _('mati') ]) ]),
					E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td' }, [ _('PID') ]), E('td', { 'class': 'td' }, [ s.pid || '-' ]) ]),
					E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td' }, [ _('Speaker amp') ]), E('td', { 'class': 'td' }, [ s.amp || '-' ]) ]),
					E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td' }, [ _('USB URL') ]), E('td', { 'class': 'td' }, [ s.url_usb || '-' ]) ]),
					E('tr', { 'class': 'tr' }, [ E('td', { 'class': 'td' }, [ _('WiFi URL') ]), E('td', { 'class': 'td' }, [ s.url_ap || '-' ]) ])
				])
			);
		};
		fill(data);

		var refresh = function() {
			return L.resolveDefault(fs.exec(CTL, [ 'status' ]), {}).then(fill);
		};
		var act = function(args) {
			return fs.exec(CTL, args).then(refresh);
		};
		var btn = function(label, args, cls) {
			return E('button', {
				'class': 'btn cbi-button ' + (cls || 'cbi-button-apply'),
				'click': function(ev) { ev.preventDefault(); return act(args); }
			}, [ label ]);
		};

		return E('div', {}, [
			host,
			E('div', { 'style': 'display:flex;gap:8px;flex-wrap:wrap;margin:12px 0' }, [
				btn(_('Start stream'), [ 'start' ]),
				btn(_('Stop stream'), [ 'stop' ], 'cbi-button-negative'),
				btn(_('Speaker on'), [ 'audio-on' ]),
				btn(_('Speaker off'), [ 'audio-off' ], 'cbi-button-negative'),
				btn(_('Refresh'), [ 'status' ])
			]),
			E('p', { 'class': 'cbi-section-descr' }, [
				_('Buka Web AI-style viewer untuk kamera di URL di atas. Untuk laptop: VLC/Open Network Stream atau OBS IP camera.')
			]),
			E('p', { 'class': 'cbi-section-descr' }, [
				_('Speaker menerima PCM S16LE 44.1 kHz mono lewat POST /audio pada port 8082.')
			])
		]);
	}
});
