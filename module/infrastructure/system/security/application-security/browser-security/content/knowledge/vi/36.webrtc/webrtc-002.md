# Peer connection

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vai trò của `RTCPeerConnection` trong việc thiết lập kết nối media và data giữa các peer.
- Mô tả offer/answer, SDP, ICE candidate, STUN và TURN trong quá trình thiết lập kết nối.
- Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong signaling và ICE candidate, đặc biệt là địa chỉ IP.
- Hiểu cách DTLS-SRTP bảo vệ media và DTLS bảo vệ WebRTC data channel, cùng giới hạn của các cơ chế này.
- Thiết kế signaling có xác thực, kiểm tra quyền theo room/peer và xác minh message trước khi chuyển tiếp.
- Chọn cấu hình ICE phù hợp với yêu cầu riêng tư và kiểm thử trạng thái kết nối bằng DevTools.

## 1. Peer connection là gì?

WebRTC cho phép hai hoặc nhiều thiết bị trao đổi âm thanh, video và dữ liệu thời gian thực. Trong trình duyệt, `RTCPeerConnection` là đối tượng quản lý kết nối giữa một peer cục bộ và peer từ xa. Nó phối hợp thương lượng media, tìm đường truyền, thiết lập transport được mã hóa và theo dõi trạng thái kết nối.

Một peer connection có thể mang:

- Audio track từ microphone hoặc nguồn âm thanh khác.
- Video track từ camera, màn hình hoặc nguồn video khác.
- Data channel để gửi dữ liệu tùy ứng dụng như chat, trạng thái trò chơi hoặc file chunk.

Peer connection không tự cung cấp một hệ thống tài khoản, danh tính hoặc quyền truy cập phòng họp. Ứng dụng thường cần một signaling service để hai peer trao đổi thông tin thiết lập kết nối. Signaling service có trách nhiệm xác thực người dùng, kiểm tra họ có quyền tham gia room hay không và chuyển đúng message đến đúng peer.

Một kết nối trực tiếp thường có đường truyền media giữa hai thiết bị. Nếu NAT hoặc firewall không cho phép kết nối trực tiếp, ICE có thể chọn đường relay qua TURN server. Nhiều ứng dụng còn dùng SFU hoặc media server để phân phối luồng đến nhiều người tham gia; khi đó mô hình mạng và ranh giới tin cậy khác với kết nối peer-to-peer thuần túy.

## 2. Các thành phần của quá trình kết nối

### 2.1. Signaling

WebRTC không quy định một giao thức signaling duy nhất. Ứng dụng có thể dùng WebSocket, HTTPS, WebTransport hoặc một cơ chế khác để chuyển offer, answer và ICE candidate giữa các peer. Signaling thường trao đổi:

- SDP offer và SDP answer mô tả khả năng media, codec, transport và thông tin thiết lập.
- ICE candidate mô tả địa chỉ/port và kiểu đường truyền mà peer có thể dùng.
- Các message điều khiển như tham gia room, rời room, từ chối cuộc gọi hoặc khởi động lại ICE.

Signaling là một ranh giới bảo mật quan trọng. Nếu attacker có thể đọc hoặc sửa message signaling, họ có thể tìm cách thay peer đích, chèn candidate, phát lại offer hoặc thay đổi fingerprint trong SDP. Kênh signaling cần được bảo vệ bằng HTTPS/WSS, xác thực session và kiểm tra quyền ở server.

### 2.2. SDP offer và answer

SDP (Session Description Protocol) là định dạng văn bản mô tả phiên. Offerer tạo offer, gửi qua signaling; peer còn lại đặt remote description, tạo answer và gửi answer về. Mỗi bên thiết lập local/remote description để thương lượng thông tin chung.

Ví dụ khởi tạo offer:

```js
const peer = new RTCPeerConnection({
  iceServers: [
    { urls: "stun:stun.example.net:3478" }
  ]
});

const offer = await peer.createOffer();
await peer.setLocalDescription(offer);

await signaling.send({
  type: "offer",
  callId,
  description: peer.localDescription
});
```

Peer nhận offer có thể xử lý như sau:

```js
await peer.setRemoteDescription(message.description);

const answer = await peer.createAnswer();
await peer.setLocalDescription(answer);

await signaling.send({
  type: "answer",
  callId,
  description: peer.localDescription
});
```

Các đoạn code là phần minh họa của một signaling flow; `signaling`, `callId` và việc quản lý đối tượng `peer` phải được ứng dụng triển khai. Trong ứng dụng thực tế, cần xử lý offer đến đồng thời, trạng thái signaling không hợp lệ, cuộc gọi bị hủy và lỗi khi đặt description. Có thể dùng mô hình *perfect negotiation* để xử lý tình huống hai peer cùng tạo offer (glare) thay vì tự giả định chỉ có một bên luôn offer trước.

SDP không phải dữ liệu vô hại. Nó có thể chứa ICE username fragment/password, fingerprint DTLS, codec, media direction, thông tin ứng dụng và các địa chỉ ứng viên. Không ghi toàn bộ SDP vào log công khai hoặc gửi nó đến analytics không cần thiết.

### 2.3. ICE, STUN và TURN

ICE (Interactive Connectivity Establishment) tìm một cặp đường truyền khả thi giữa hai peer. Trình duyệt thu thập các ICE candidate, kiểm tra kết nối và chọn đường truyền hoạt động.

| Thành phần | Vai trò | Thông tin cần lưu ý |
| --- | --- | --- |
| Host candidate | Địa chỉ giao diện mạng cục bộ của thiết bị. | Có thể tiết lộ thông tin mạng nội bộ; trình duyệt hiện đại có thể dùng mDNS để che địa chỉ host trong một số trường hợp. |
| Server-reflexive candidate (`srflx`) | Địa chỉ công khai được quan sát qua STUN. | Có thể tiết lộ địa chỉ IP công khai của người dùng cho peer hoặc thành phần nhận signaling. |
| Relay candidate (`relay`) | Địa chỉ cấp bởi TURN server để chuyển tiếp traffic. | Peer nhìn thấy địa chỉ relay; TURN server vẫn có thể quan sát địa chỉ mạng của client kết nối đến nó. |
| STUN | Hỗ trợ phát hiện địa chỉ ánh xạ và kiểm tra khả năng kết nối qua NAT. | STUN không xác thực người dùng ứng dụng và không mã hóa media. |
| TURN | Chuyển tiếp traffic khi đường trực tiếp không khả thi hoặc khi policy yêu cầu relay. | Cần credential có thời hạn, giới hạn quota và bảo vệ khỏi bị dùng làm relay công cộng. |

Ví dụ cấu hình STUN và TURN:

```js
const peer = new RTCPeerConnection({
  iceServers: [
    { urls: "stun:stun.example.net:3478" },
    {
      urls: [
        "turn:turn.example.net:3478?transport=udp",
        "turns:turn.example.net:5349?transport=tcp"
      ],
      username: shortLivedTurnUsername,
      credential: shortLivedTurnCredential
    }
  ]
});
```

Không nhúng secret TURN dài hạn vào JavaScript. Trình duyệt cần credential để dùng TURN nên người dùng có thể quan sát credential tạm thời trong runtime hoặc Network. Server nên cấp credential có thời hạn ngắn, giới hạn dung lượng/bandwidth và gắn với phiên hoặc người dùng theo thiết kế.

## 3. Trickle ICE và trao đổi candidate

ICE gathering có thể diễn ra sau khi ứng dụng đặt local description. Với Trickle ICE, mỗi candidate được gửi qua signaling ngay khi thu thập được thay vì đợi gom đủ toàn bộ candidate.

```js
peer.addEventListener("icecandidate", (event) => {
  if (!event.candidate) {
    signaling.send({ type: "ice-complete", callId });
    return;
  }

  signaling.send({
    type: "ice-candidate",
    callId,
    candidate: event.candidate
  });
});
```

Peer nhận candidate:

```js
await peer.addIceCandidate(message.candidate);
```

Trong ứng dụng thật, cần xử lý candidate đến trước khi remote description được đặt. Có thể tạm xếp candidate vào hàng đợi, sau đó thêm vào peer connection sau khi `setRemoteDescription()` thành công. Candidate cũng phải được gắn với đúng call, đúng peer và đúng ICE generation; candidate cũ sau ICE restart không được trộn vào phiên mới.

Không chuyển tiếp candidate chỉ dựa trên `callId` do client gửi. Server phải xác minh socket thuộc về cuộc gọi đó và người gửi là thành viên được phép. Khi cuộc gọi kết thúc, loại bỏ trạng thái signaling và candidate queue liên quan.

## 4. Tạo peer connection và quản lý trạng thái

`RTCPeerConnection` cung cấp các event/state giúp ứng dụng biết quá trình kết nối đang ở giai đoạn nào:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `signalingState` | Trạng thái thương lượng offer/answer, ví dụ `stable`, `have-local-offer` hoặc `have-remote-offer`. |
| `iceGatheringState` | Trạng thái thu thập candidate: `new`, `gathering` hoặc `complete`. |
| `iceConnectionState` | Trạng thái ICE: `new`, `checking`, `connected`, `completed`, `failed`, `disconnected` hoặc `closed`. |
| `connectionState` | Trạng thái tổng hợp của các transport trong peer connection, gồm `new`, `connecting`, `connected`, `disconnected`, `failed` và `closed`. |

Ví dụ theo dõi trạng thái:

```js
peer.addEventListener("connectionstatechange", () => {
  switch (peer.connectionState) {
    case "connected":
      showCallStatus("Đã kết nối");
      break;
    case "disconnected":
      showCallStatus("Đang thử khôi phục kết nối");
      break;
    case "failed":
      showCallStatus("Không thể thiết lập kết nối");
      break;
    case "closed":
      showCallStatus("Cuộc gọi đã kết thúc");
      break;
  }
});
```

`disconnected` có thể chỉ là trạng thái tạm thời do mạng thay đổi. Ứng dụng nên có chiến lược retry/ICE restart hợp lý, tránh tạo vô hạn peer connection hoặc tự động reconnect mà không kiểm tra session và quyền cuộc gọi còn hiệu lực.

Khi kết thúc cuộc gọi, gọi `peer.close()`, dừng track do ứng dụng sở hữu khi không còn cần, xóa listener và xóa dữ liệu signaling. Đóng peer connection không tự thu hồi quyền microphone/camera nếu track hoặc stream vẫn được ứng dụng giữ và sử dụng ở nơi khác.

## 5. Bảo vệ media transport

WebRTC dùng các cơ chế mã hóa ở tầng transport:

- Media audio/video thường được bảo vệ bằng SRTP; khóa được thiết lập thông qua DTLS, tạo thành DTLS-SRTP.
- Data channel dùng SCTP chạy trên DTLS, vì vậy dữ liệu data channel cũng được bảo vệ trên đường truyền.
- DTLS certificate fingerprint được đưa vào SDP để peer kiểm tra danh tính khóa của transport trong quá trình thiết lập.

Các cơ chế này bảo vệ dữ liệu trên đường truyền giữa hai đầu DTLS. Chúng không tự xác thực tài khoản người dùng, không xác minh người tham gia có quyền vào room và không ngăn signaling server bị lạm dụng để chuyển SDP đến sai peer.

Nếu attacker có thể thay SDP hoặc fingerprint trong signaling mà không bị phát hiện, họ có thể tìm cách khiến hai phía thiết lập transport với endpoint không mong muốn. Vì vậy, signaling cần tính xác thực và toàn vẹn: dùng HTTPS/WSS, xác thực sender, kiểm tra room membership, gắn offer/answer với call ID và peer ID do server quản lý, đồng thời không cho client tự đổi người nhận.

Trong mô hình SFU, mỗi trình duyệt thường thiết lập kết nối DTLS-SRTP với SFU. SFU có thể giải mã media để định tuyến, chuyển mã hoặc xử lý luồng rồi mã hóa lại cho người nhận. Do đó, DTLS-SRTP hop-by-hop không đồng nghĩa media được mã hóa đầu cuối giữa hai người dùng. Nếu yêu cầu bảo mật cần SFU cũng không đọc được nội dung, phải thiết kế thêm E2EE ở tầng media (ví dụ dùng cơ chế frame encryption/insertable streams khi nền tảng hỗ trợ), quản lý khóa và xác minh peer riêng. Không nên tuyên bố E2EE chỉ vì ứng dụng dùng WebRTC.

## 6. Quyền truy cập microphone, camera và màn hình

Việc tạo `RTCPeerConnection` không tự cấp quyền truy cập thiết bị. Ứng dụng thường lấy media bằng `getUserMedia()` hoặc `getDisplayMedia()` rồi thêm track vào peer connection.

```js
const localStream = await navigator.mediaDevices.getUserMedia({
  audio: true,
  video: {
    width: { ideal: 1280 },
    height: { ideal: 720 }
  }
});

for (const track of localStream.getTracks()) {
  peer.addTrack(track, localStream);
}
```

`getUserMedia()` cần secure context và sự cho phép của người dùng. Quyền có thể bị từ chối hoặc thu hồi; thiết bị có thể biến mất giữa cuộc gọi. Ứng dụng cần xử lý lỗi `NotAllowedError`, `NotFoundError`, `NotReadableError` và trạng thái track bị mute/ended mà không làm lộ thông tin thiết bị trong log.

Với screen sharing, gọi `getDisplayMedia()` theo tương tác rõ ràng của người dùng. Trình duyệt hiển thị UI chọn màn hình/cửa sổ/tab; ứng dụng không được tự ý chọn và thu hình mọi nội dung mà người dùng không biết. Cần có chỉ báo chia sẻ, nút dừng và xử lý `track.onended` để dừng luồng khi người dùng kết thúc chia sẻ từ UI của trình duyệt.

Nếu nhúng ứng dụng trong iframe, cần cấu hình Permissions Policy và thuộc tính `allow` phù hợp, ví dụ cho phép `camera` và `microphone` chỉ ở frame đáng tin cậy. Không cấp quyền rộng cho iframe bên thứ ba nếu không có nhu cầu.

## 7. Riêng tư địa chỉ IP và lựa chọn ICE transport

ICE candidate có thể tiết lộ thông tin mạng. Tùy trình duyệt, cấu hình và đường truyền, remote peer có thể nhìn thấy địa chỉ IP công khai hoặc thông tin host candidate. Điều này có thể làm lộ mạng đang dùng, vị trí mạng gần đúng hoặc mối liên hệ giữa các phiên truy cập.

Các lựa chọn thường gặp:

- **Kết nối trực tiếp:** giảm độ trễ và chi phí relay, nhưng peer có thể quan sát địa chỉ mạng được dùng cho kết nối.
- **Dùng TURN khi cần:** peer nhìn thấy địa chỉ relay thay vì địa chỉ IP trực tiếp của đối phương. TURN server vẫn nhìn thấy địa chỉ IP của client kết nối đến relay.
- **Relay-only:** cấu hình `iceTransportPolicy: "relay"` để chỉ sử dụng relay candidate trong quá trình kết nối. Điều này tăng mức che địa chỉ peer nhưng có thể làm tăng độ trễ, băng thông và chi phí TURN; kết nối sẽ thất bại nếu không có relay khả dụng.

Ví dụ relay-only:

```js
const peer = new RTCPeerConnection({
  iceTransportPolicy: "relay",
  iceServers: [
    {
      urls: "turns:turn.example.net:5349?transport=tcp",
      username: shortLivedTurnUsername,
      credential: shortLivedTurnCredential
    }
  ]
});
```

Relay-only là lựa chọn policy cho peer connection cụ thể; nó không làm ẩn IP khỏi TURN provider, signaling server, hệ điều hành hoặc mọi thành phần mạng. Hãy xác định rõ mục tiêu riêng tư trước khi chọn cấu hình. Không ghi candidate nguyên vẹn vào analytics; nếu cần telemetry, chỉ thu thập trường đã giảm nhạy cảm và có thời hạn lưu giữ.

Trình duyệt có thể dùng mDNS để thay địa chỉ host candidate bằng hostname cục bộ khó suy ra IP nội bộ. Đây là biện pháp bảo vệ quyền riêng tư do trình duyệt triển khai, không phải bảo đảm rằng mọi loại candidate hoặc mọi trình duyệt đều che được toàn bộ địa chỉ. Kiểm tra thực tế trên các browser/version được hỗ trợ.

## 8. Signaling security: xác thực peer và quyền tham gia

Signaling server phải là nơi kiểm soát ai được tạo cuộc gọi, ai được tham gia và ai có thể gửi offer/candidate cho ai. Một thiết kế cơ bản nên thực hiện:

1. Xác thực session người dùng qua HTTPS/WSS.
2. Khi tạo hoặc tham gia room, kiểm tra quyền theo room, tenant và trạng thái cuộc gọi.
3. Server cấp call ID và ánh xạ participant ID từ dữ liệu server-side.
4. Chỉ chuyển offer/answer/candidate giữa các participant hiện đang được phép trong cùng cuộc gọi.
5. Kiểm tra loại message, schema, kích thước, tốc độ gửi và trạng thái signaling.
6. Khi participant rời room, bị kick hoặc mất quyền, từ chối message mới và thông báo đóng peer connection cho các bên liên quan.

Không tin `to`, `from`, `roomId` hoặc `callId` do client gửi nếu chưa đối chiếu với session và trạng thái server. Nếu client gửi `from: "user-1"`, server phải xác định sender từ kết nối đã xác thực, không lấy giá trị đó làm danh tính. Một user không được tự chuyển offer đến participant ngoài room.

Ví dụ message signaling:

```json
{
  "type": "offer",
  "callId": "call-7d21",
  "to": "participant-b",
  "description": {
    "type": "offer",
    "sdp": "v=0\\r\\n..."
  }
}
```

Server xác định sender từ session, kiểm tra sender và recipient cùng thuộc cuộc gọi, rồi mới chuyển message. Không cho client tự gán role hoặc quyền. Với offer/answer, server có thể giữ trạng thái signaling để từ chối message đến sai thứ tự hoặc replay từ một phiên đã đóng.

## 9. Kiểm tra và xử lý SDP/candidate không tin cậy

SDP và ICE candidate đến từ remote peer là input không tin cậy. Trình duyệt có parser và kiểm tra giao thức, nhưng ứng dụng vẫn cần giới hạn tài nguyên và xác thực ngữ cảnh trước khi gọi API tương ứng.

Áp dụng các biện pháp:

- Giới hạn kích thước SDP và candidate message trước khi parse hoặc chuyển tiếp.
- Xác nhận `description.type` chỉ thuộc loại được chấp nhận ở trạng thái hiện tại (`offer`, `answer`, hoặc rollback khi luồng negotiation cho phép).
- Kiểm tra candidate thuộc đúng `callId`, participant, `sdpMid`/`sdpMLineIndex` và ICE generation.
- Không chấp nhận candidate sau khi cuộc gọi đóng hoặc từ sender đã bị loại khỏi room.
- Rate limit offer, renegotiation và candidate để tránh tiêu thụ CPU/băng thông quá mức.
- Không render SDP, candidate hoặc error text vào HTML; coi chúng là dữ liệu kỹ thuật không tin cậy.
- Che thông tin IP, ICE credentials và fingerprint khỏi log thông thường; chỉ giữ khi cần chẩn đoán, có quyền truy cập và retention rõ ràng.

Khi gọi `setRemoteDescription()` hoặc `addIceCandidate()`, bắt lỗi và đưa kết nối về trạng thái có thể phục hồi hoặc đóng sạch. Không tự động thử lại liên tục với cùng một SDP lỗi. Với ICE restart, tạo negotiation mới theo trạng thái peer connection và không trộn candidate của generation cũ.

## 10. Data channel và bảo vệ dữ liệu ứng dụng

Data channel được tạo qua `createDataChannel()` và sự kiện `datachannel` ở phía nhận. Nó phù hợp cho dữ liệu realtime không phải audio/video, nhưng mọi message vẫn cần xác thực và authorization ở tầng ứng dụng.

```js
const channel = peer.createDataChannel("app-events", {
  ordered: true
});

channel.addEventListener("open", () => {
  channel.send(JSON.stringify({
    type: "presence",
    state: "ready"
  }));
});

channel.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  validateApplicationMessage(message);
  handleAuthorizedApplicationMessage(message);
});
```

DTLS bảo vệ data channel trên đường truyền, nhưng không tự xác định người gửi được quyền gọi action nào. Ứng dụng cần kiểm tra schema, loại message, kích thước, rate limit và quyền theo resource. Nếu data channel được dùng để truyền file, cần giới hạn kích thước, số chunk, tổng dung lượng và thời gian giữ buffer; không ghi file nhận được ra hệ thống hoặc hiển thị trực tiếp nếu chưa xác minh loại dữ liệu.

Thuộc tính `ordered` điều khiển thứ tự giao nhận. Với dữ liệu có thể mất hoặc không cần thứ tự, ứng dụng có thể cân nhắc `maxRetransmits` hoặc `maxPacketLifeTime` theo yêu cầu. Những tùy chọn này ảnh hưởng độ tin cậy và độ trễ, không phải biện pháp authorization.

## 11. Cấu hình và chính sách triển khai

Một số kiểm soát trình duyệt và máy chủ cần phối hợp:

| Thành phần | Kiểm soát nên xem xét |
| --- | --- |
| Secure context | Phục vụ ứng dụng qua HTTPS; dùng `wss://` cho signaling WebSocket. `localhost` có thể được xem là secure context trong môi trường phát triển. |
| CSP | Giới hạn `connect-src` cho signaling endpoint và các API cần thiết. Kiểm tra `media-src` nếu ứng dụng tải media từ URL. |
| Permissions Policy | Giới hạn `camera`, `microphone`, `display-capture` và các capability không cần thiết, đặc biệt trong iframe. |
| Signaling auth | Xác thực session, kiểm tra Origin cho WebSocket signaling và quyền room/participant. |
| ICE servers | Chỉ dùng STUN/TURN tin cậy; cấp TURN credential ngắn hạn, giới hạn quota và theo dõi lạm dụng. |
| Logging | Không ghi raw SDP, candidate, TURN secret, token hoặc dữ liệu media vào log phổ thông. |
| SFU/TURN infrastructure | Cập nhật phần mềm, giới hạn cổng và nguồn truy cập, bảo vệ credential, theo dõi dung lượng và abuse. |

`connect-src` có thể cần cho endpoint signaling WebSocket và các endpoint HTTPS dùng để cấp TURN credential. Không thêm wildcard rộng nếu không cần. CSP không thay thế xác thực signaling hoặc authorization room.

## 12. Kiểm thử peer connection

Hãy kiểm thử trên các trình duyệt và mạng mà sản phẩm hỗ trợ. Dùng tài khoản thử và cuộc gọi thử, tránh đưa nội dung cá nhân vào log.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Peer chưa đăng nhập | Mở signaling connection và thử tham gia room. | Server từ chối hoặc không cấp call membership. |
| Người dùng ngoài room gửi offer | Gửi signaling message với `callId` của room khác. | Server từ chối và không chuyển SDP. |
| Giả mạo sender/recipient | Sửa `from`, `to` hoặc participant ID trong payload. | Server lấy sender từ session và kiểm tra recipient theo membership. |
| Candidate cũ sau ICE restart | Gửi candidate thuộc generation cũ sau khi ICE credentials thay đổi. | Server/client loại bỏ candidate không còn hợp lệ. |
| SDP/candidate quá lớn | Gửi message vượt giới hạn hoặc lặp nhanh. | Server áp dụng giới hạn kích thước/rate và giữ tài nguyên ổn định. |
| Mạng chặn UDP | Thử kết nối trong mạng chỉ cho TCP/TLS. | TURN/TCP hoặc TURN/TLS được dùng nếu đã cấu hình và được phép. |
| Relay-only | Đặt `iceTransportPolicy: "relay"` và quan sát candidate/selected pair. | Chỉ dùng đường relay; kết nối thất bại có kiểm soát nếu relay không khả dụng. |
| Quyền microphone bị từ chối | Từ chối prompt hoặc thu hồi quyền rồi bắt đầu cuộc gọi. | Ứng dụng hiển thị trạng thái phù hợp và không giả định track tồn tại. |
| Dừng screen sharing | Dừng chia sẻ từ UI trình duyệt. | Ứng dụng nhận track ended và cập nhật trạng thái cuộc gọi. |
| Data channel gửi message sai | Gửi JSON sai schema, payload lớn hoặc action ngoài quyền. | Ứng dụng từ chối message và không thực hiện side effect. |
| Participant bị kick | Gỡ participant khỏi room trong lúc cuộc gọi đang hoạt động. | Signaling server từ chối message mới và các peer dọn kết nối/subscription tương ứng. |

### 12.1. Quan sát bằng DevTools

Trong Chrome/Edge, mở `chrome://webrtc-internals` hoặc công cụ tương đương của trình duyệt để quan sát peer connection, ICE candidate, selected candidate pair, codec, byte count và trạng thái transport. DevTools Network giúp theo dõi signaling request và WebSocket frame.

Khi chẩn đoán:

1. Ghi lại `signalingState`, `iceGatheringState`, `iceConnectionState` và `connectionState`.
2. Xác định selected candidate pair là host, srflx hay relay.
3. Kiểm tra liệu TURN có được sử dụng khi mạng yêu cầu relay không.
4. So sánh offer/answer và thời điểm candidate được gửi để tìm lỗi signaling hoặc candidate đến sai thứ tự.
5. Kiểm tra quyền camera/microphone và trạng thái track khi media không xuất hiện.
6. Xóa hoặc bảo vệ log chẩn đoán sau khi xử lý vì SDP và candidate có thể chứa thông tin nhạy cảm.

Không gửi file dump WebRTC internals công khai nếu chưa loại bỏ địa chỉ IP, ICE credentials, fingerprint và thông tin phiên.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cho rằng peer connection tự xác thực người dùng | Người chưa có quyền có thể tham gia signaling hoặc nhận dữ liệu nếu server không kiểm soát. | Xác thực session và authorize room/participant ở signaling server. |
| Chuyển tiếp mọi SDP/candidate theo ID client gửi | Có thể chuyển offer đến peer ngoài cuộc gọi hoặc cho phép replay. | Gắn message với sender từ session, call membership và trạng thái negotiation server-side. |
| Coi STUN là transport bảo mật | STUN chỉ hỗ trợ khám phá/kiểm tra đường truyền, không mã hóa media hay cấp quyền. | Dùng DTLS-SRTP/DTLS và xác thực signaling riêng. |
| Cho rằng DTLS-SRTP luôn là E2EE | Trong mô hình SFU, media server có thể giải mã media ở đầu kết nối của nó. | Xác định rõ ranh giới tin cậy; triển khai E2EE tầng media nếu cần. |
| Không xem xét IP trong ICE candidate | Có thể làm lộ địa chỉ mạng cho peer hoặc hạ tầng. | Đánh giá relay-only, mDNS và chính sách lưu log theo yêu cầu riêng tư. |
| Dùng TURN credential dài hạn trong JavaScript | Credential có thể bị trích xuất và dùng để tiêu tốn tài nguyên relay. | Cấp credential tạm thời, quota và giám sát abuse. |
| Không dọn peer connection khi kết thúc | Giữ track, socket, buffer và tài nguyên thiết bị không cần thiết. | Đóng peer, dừng track khi phù hợp, dọn listener và trạng thái signaling. |
| Tin mọi data channel message vì transport đã mã hóa | Peer đã kết nối vẫn có thể gửi action hoặc payload trái quyền. | Validate schema, authorize action/resource và giới hạn message. |

## 14. Bài thực hành

Xây dựng một demo cuộc gọi giữa hai tab hoặc hai trình duyệt với signaling server trong môi trường local/staging.

1. Tạo signaling channel qua HTTPS/WSS và xác thực người dùng trước khi tham gia room.
2. Tạo `RTCPeerConnection` với STUN và TURN credential tạm thời; thiết lập offer/answer.
3. Bật Trickle ICE và chuyển candidate qua signaling; xử lý candidate đến trước remote description bằng hàng đợi.
4. Thêm audio/video track sau khi người dùng cấp quyền. Kiểm tra trường hợp từ chối quyền và dừng track.
5. Tạo data channel, gửi một message JSON và kiểm tra schema ở phía nhận.
6. Thử giả mạo `callId`, `from`, `to` và candidate từ một user ngoài room; xác nhận signaling server từ chối.
7. Thử `iceTransportPolicy: "relay"`, quan sát selected candidate pair và ghi lại đánh đổi về độ trễ/kết nối.
8. Đóng cuộc gọi, thu hồi session hoặc kick participant; xác nhận peer connection, track và trạng thái signaling được dọn đúng.
9. Dùng DevTools hoặc WebRTC internals ghi lại trạng thái kết nối và candidate type, đồng thời che thông tin IP/credential trước khi lưu bằng chứng.

Hoàn thành bài thực hành khi bạn giải thích được `RTCPeerConnection` phối hợp signaling và ICE ra sao, dữ liệu nào có thể lộ qua SDP/candidate, transport được mã hóa bảo vệ đến đâu, và vì sao xác thực cùng authorization vẫn phải được thực thi ở signaling server và tầng ứng dụng.
