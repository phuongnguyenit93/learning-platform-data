# STUN và TURN

**STUN** và **TURN** là hai giao thức hỗ trợ WebRTC tìm đường truyền giữa các peer khi thiết bị nằm sau NAT, firewall hoặc mạng có chính sách hạn chế. STUN giúp một thiết bị biết địa chỉ IP và port mà máy chủ bên ngoài quan sát được. TURN cấp một địa chỉ relay và chuyển tiếp packet khi hai peer không thể kết nối trực tiếp.

Hai giao thức này thường được sử dụng trong quy trình **ICE (Interactive Connectivity Establishment)**. ICE thu thập các candidate từ giao diện mạng, STUN và TURN; trao đổi candidate qua signaling; sau đó kiểm tra các cặp candidate để chọn đường truyền hoạt động. STUN không phải máy chủ chuyển tiếp media. TURN mới chuyển tiếp traffic giữa các peer và vì vậy tiêu thụ băng thông, CPU và cổng mạng của hạ tầng.

STUN/TURN cũng liên quan trực tiếp tới quyền riêng tư và bảo mật. Candidate có thể tiết lộ địa chỉ mạng; TURN credential bị lộ có thể bị lạm dụng để tạo relay traffic; một TURN server mở không yêu cầu xác thực có thể trở thành open relay gây tốn chi phí hoặc bị dùng làm hạ tầng trung gian cho lưu lượng không mong muốn.

Bài học thuộc chương **WebRTC** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào ICE, STUN Binding, TURN allocation, candidate types, credential, privacy, abuse prevention và kiểm chứng hành vi trong browser.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao WebRTC cần ICE, STUN và TURN khi hai peer nằm sau NAT hoặc firewall.
2. Phân biệt STUN server, TURN server và signaling server.
3. Mô tả cách STUN Binding giúp phát hiện server-reflexive address.
4. Giải thích vì sao STUN không bảo đảm hai peer có thể kết nối trực tiếp.
5. Phân biệt host, server-reflexive, peer-reflexive và relay candidate.
6. Mô tả TURN allocation, permission, channel binding và luồng relay.
7. Cấu hình RTCPeerConnection với RTCIceServer, username, credential và iceTransportPolicy.
8. Dùng TURN credential ngắn hạn và hiểu vì sao không nhúng shared secret vào JavaScript.
9. Đánh giá IP privacy, chi phí relay, open relay, quota và abuse controls.
10. Thu thập và phân loại ICE candidate bằng DevTools và một trang lab chạy trên localhost.

## 2. Vì sao WebRTC cần STUN và TURN?

Một máy tính hoặc điện thoại thường nằm trong mạng nội bộ và đi ra Internet thông qua router NAT. Thiết bị có thể có địa chỉ như 192.168.x.x hoặc 10.x.x.x, nhưng peer ở Internet không thể dùng trực tiếp địa chỉ riêng đó để gửi packet tới thiết bị.

NAT tạo mapping giữa địa chỉ/port nội bộ và địa chỉ/port bên ngoài. Mapping có thể phụ thuộc vào destination, thời gian tồn tại, loại traffic và chính sách firewall. Vì vậy, biết địa chỉ public của mình chưa đủ để kết luận peer có thể kết nối tới mình.

~~~text
Peer A                         Router/NAT A                  Internet
192.168.1.10:50000  ------->   198.51.100.10:62000  ---------> STUN/TURN

Peer B                         Router/NAT B
10.0.0.8:51000      ------->   203.0.113.20:63000
~~~

Khi Peer A gửi packet tới STUN server, server nhìn thấy địa chỉ nguồn sau NAT. STUN có thể trả địa chỉ đó cho A. A đưa địa chỉ này vào danh sách candidate để thử kết nối với B.

Nếu NAT hoặc firewall không cho phép đường trực tiếp, hai peer có thể dùng TURN. Mỗi peer gửi traffic tới relay server; TURN chuyển tiếp packet giữa hai phía.

### 2.1. Ba dịch vụ có vai trò khác nhau

| Thành phần | Vai trò | Có chuyển tiếp media? |
| --- | --- | --- |
| Signaling server | Trao đổi SDP offer/answer, ICE candidate và thông tin phiên | Không nhất thiết; signaling là kênh điều phối |
| STUN server | Trả lời Binding request để client biết mapped address; cũng được ICE dùng cho connectivity checks | Không |
| TURN server | Cấp relay address và chuyển tiếp packet giữa client với peer | Có |

Signaling server không phải STUN/TURN server. Hai peer có thể trao đổi signaling qua HTTPS hoặc WebSocket, trong khi ICE dùng STUN/TURN riêng để thiết lập đường media/data.

### 2.2. ICE kết nối các mảnh lại với nhau

ICE là quy trình tìm đường truyền. Nó thu thập candidate, trao đổi chúng với peer, tạo candidate pair, gửi connectivity check và chọn pair có thể truyền dữ liệu.

~~~mermaid
flowchart TD
    A["Tạo RTCPeerConnection"] --> B["Gather ICE candidates"]
    B --> C["Host candidates từ giao diện mạng"]
    B --> D["STUN Binding: server-reflexive candidates"]
    B --> E["TURN Allocate: relay candidates"]
    C --> F["Trao đổi candidates qua signaling"]
    D --> F
    E --> F
    F --> G["Tạo candidate pairs"]
    G --> H["STUN connectivity checks"]
    H --> I{"Có pair hợp lệ?"}
    I -->|Có| J["Nominate selected candidate pair"]
    I -->|Không| K["Thử pair khác hoặc ICE thất bại"]
    J --> L["Truyền media/data"]
~~~

ICE có thể chọn đường trực tiếp nếu có candidate pair hoạt động. Nếu chỉ có relay pair hoạt động, media/data đi qua TURN. Không phải mọi cuộc gọi đều cần TURN, nhưng ứng dụng production nên có phương án TURN vì nhiều mạng doanh nghiệp, mạng di động và firewall không cho phép kết nối trực tiếp.

## 3. STUN hoạt động như thế nào?

**STUN (Session Traversal Utilities for NAT)** là giao thức cho phép client khám phá địa chỉ transport mà server quan sát được. Trong trường hợp phổ biến, client gửi STUN Binding request qua UDP tới STUN server. Server đọc source IP và port của packet sau khi NAT đã xử lý, rồi trả địa chỉ đó trong thuộc tính XOR-MAPPED-ADDRESS của Binding success response.

Ví dụ:

~~~text
Client local socket:     192.168.1.20:54000
NAT public mapping:      198.51.100.25:62010

Client  -- Binding Request -->  STUN server
Client  <-- Binding Success --  STUN server
                 XOR-MAPPED-ADDRESS = 198.51.100.25:62010
~~~

Địa chỉ public mapping này được dùng để tạo **server-reflexive candidate**, thường viết tắt là srflx.

### 3.1. STUN không mở port NAT theo cách bảo đảm

STUN không ra lệnh cho mọi router mở một cổng inbound cố định. Nó quan sát mapping được tạo khi client gửi request ra ngoài. Khả năng peer gửi packet ngược lại phụ thuộc hành vi NAT, firewall, mapping lifetime và việc connectivity check có tạo được đường đi phù hợp hay không.

Ví dụ:

- Một số NAT tái sử dụng cùng mapping cho nhiều destination.
- Một số NAT tạo mapping khác nhau tùy destination.
- Firewall có thể chỉ nhận packet trả lời cho luồng outbound đã được cho phép.
- Mapping có thể hết hạn nếu không có traffic duy trì.

Vì vậy, biết XOR-MAPPED-ADDRESS chỉ là một phần của bài toán. ICE cần kiểm tra candidate pair thực tế bằng STUN connectivity checks.

### 3.2. STUN server không chuyển tiếp dữ liệu

STUN server xử lý request và trả response. Sau khi client nhận server-reflexive address, media không đi qua STUN server. Nếu đường trực tiếp được thiết lập, peer trao đổi packet trực tiếp theo candidate pair đã chọn.

Điều này giúp STUN nhẹ và ít tốn băng thông hơn TURN, nhưng STUN không thể giải quyết các mạng mà NAT/firewall không cho phép kết nối trực tiếp.

### 3.3. STUN không phải hệ thống xác thực người dùng

STUN Binding request thông thường không xác thực tài khoản ứng dụng. STUN có các cơ chế integrity/credential cho những usage nhất định, nhưng việc một client nhận được mapped address không chứng minh người dùng đã đăng nhập hoặc được phép tham gia phòng họp.

Authentication người dùng phải được thực hiện ở signaling/application server. TURN authentication là cơ chế riêng để kiểm soát việc sử dụng relay.

## 4. TURN hoạt động như thế nào?

**TURN (Traversal Using Relays around NAT)** cho phép client cấp phát một relay transport address trên TURN server. Peer gửi packet tới relay address đó; TURN server chuyển tiếp packet tới client đã tạo allocation và ngược lại.

~~~text
Peer A                 TURN relay                  Peer B
   |                       |                          |
   |-- Allocate request -->|                          |
   |<-- Relay address -----|                          |
   |                       |<-- Allocate request -----|
   |                       |---- Relay address ------>|
   |                       |                          |
   |-- packet ------------>|---- packet ------------->|
   |<-- packet ------------|<--- packet --------------|
~~~

TURN server có thể được đặt ở hạ tầng công cộng hoặc vùng mạng được thiết kế để nhận traffic từ các mạng bị hạn chế. Client có thể kết nối tới TURN bằng UDP, TCP hoặc TLS tùy server và browser hỗ trợ.

### 4.1. Allocation

Allocation là trạng thái relay được tạo trên TURN server cho một client. Client gửi Allocate request; server xác thực credential, cấp relay address và giữ trạng thái allocation trong một khoảng thời gian có giới hạn.

Response thành công chứa địa chỉ relay trong thuộc tính XOR-RELAYED-ADDRESS; nó cũng có thể chứa mapped address mà server nhìn thấy ở phía client. ICE dùng relay address để tạo **relay candidate**.

TURN server phải quản lý:

- Allocation lifetime và refresh.
- Credential và message integrity.
- Permission cho peer address được phép gửi traffic tới allocation.
- Channel binding nếu client dùng ChannelData để truyền hiệu quả hơn.
- Quota số allocation, băng thông và relay port.

### 4.2. Permission

Client cần tạo permission cho địa chỉ peer trước khi TURN server chuyển tiếp data từ peer tới allocation. Permission giới hạn IP peer nào được phép gửi packet vào relay allocation.

Permission có lifetime riêng và phải được refresh khi cần. Nó giúp hạn chế việc allocation trở thành một cổng nhận packet tùy ý từ mọi địa chỉ.

### 4.3. Channel binding

TURN có thể dùng ChannelBind để gắn một channel number với địa chỉ peer. Sau khi channel được thiết lập, data có thể được gửi dưới dạng ChannelData với overhead thấp hơn Data indication.

Channel number và permission là trạng thái của TURN allocation. Client phải refresh hoặc thiết lập lại khi trạng thái hết hạn.

### 4.4. TURN chuyển tiếp packet, không đồng nghĩa giải mã media

Trong WebRTC thông thường, media được bảo vệ bằng DTLS-SRTP giữa hai endpoint. TURN relay chuyển tiếp packet mã hóa và không cần giải mã nội dung media để thực hiện relay. Tuy nhiên, TURN server vẫn quan sát được metadata mạng như địa chỉ client/peer, thời gian, kích thước và lưu lượng.

TURN là một thành phần tin cậy về khả năng chuyển tiếp và tính sẵn sàng. Hãy chọn nhà cung cấp/hạ tầng, bảo vệ credential và giám sát relay traffic như một dịch vụ có chi phí và rủi ro vận hành.

## 5. Bốn loại ICE candidate

ICE dùng nhiều loại candidate để thử các đường truyền khác nhau:

| Candidate type | Ý nghĩa | Thường được tạo bởi |
| --- | --- | --- |
| host | Địa chỉ trên giao diện mạng của thiết bị, có thể là interface vật lý, VPN hoặc mạng nội bộ | ICE agent trên thiết bị |
| srflx (server-reflexive) | Địa chỉ mapping mà STUN server quan sát được sau NAT | STUN Binding |
| prflx (peer-reflexive) | Địa chỉ được phát hiện trong quá trình connectivity check với peer | ICE connectivity checks |
| relay | Địa chỉ được cấp bởi relay server | TURN Allocate |

Ví dụ candidate line trong SDP:

~~~text
a=candidate:4234997325 1 udp 2043278322 192.0.2.172 44323 typ host
~~~

Các trường thể hiện foundation, component, transport, priority, address, port và type. Trong ví dụ, typ host chỉ ra candidate thuộc loại host.

### 5.1. Candidate pair

Mỗi peer gửi danh sách candidate cho peer còn lại qua signaling. ICE ghép candidate local với candidate remote thành candidate pair và thử kết nối.

Một pair có thể là:

- host ↔ host.
- srflx ↔ srflx.
- host ↔ srflx.
- relay ↔ host.
- relay ↔ relay.

ICE ưu tiên các pair theo priority và kiểm tra connectivity. Một candidate xuất hiện trong SDP chưa có nghĩa nó sẽ được chọn. Candidate pair chỉ có giá trị sau khi connectivity check thành công và được nomination theo quy trình ICE.

### 5.1. Connectivity check dùng STUN nhưng không phải STUN Binding khám phá NAT

ICE dùng STUN Binding request/response trên từng candidate pair để kiểm tra hai phía có thể trao đổi packet hay không. Những request này được xác thực bằng ICE credentials (ufrag/password) được thương lượng trong SDP và có các thuộc tính phục vụ kiểm tra integrity/role.

ICE credentials ràng buộc connectivity check với ICE session. Chúng không phải mật khẩu đăng nhập ứng dụng và không thay thế xác thực participant trên signaling server.

ICE còn dùng consent freshness để kiểm tra peer vẫn có thể nhận traffic và việc tiếp tục gửi packet còn được cho phép. Consent freshness giúp hạn chế gửi dữ liệu tới địa chỉ không còn phản hồi hoặc không còn consent; nó không chứng minh người dùng vẫn đăng nhập hay có quyền nghiệp vụ.

### 5.2. Trickle ICE

Với Trickle ICE, candidate được gửi tới peer ngay khi thu thập được thay vì đợi gathering hoàn tất. Điều này giúp bắt đầu connectivity check sớm và giảm thời gian thiết lập cuộc gọi.

Browser phát sự kiện icecandidate khi có candidate mới. Khi event.candidate là null, quá trình gathering đã hoàn tất theo API event model thông dụng.

### 5.3. Candidate không phải danh tính

IP address, port và candidate type chỉ mô tả đường truyền. Không dùng candidate để xác định người dùng, tổ chức hoặc quyền tham gia phiên. Signaling phải xác thực participant và ràng buộc candidate với đúng phiên đã được cấp quyền.

## 6. Cấu hình STUN và TURN trong RTCPeerConnection

Browser nhận danh sách ICE server thông qua cấu hình RTCPeerConnection:

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: 'stun:stun.example.net:3478',
    },
    {
      urls: [
        'turn:turn.example.net:3478?transport=udp',
        'turn:turn.example.net:3478?transport=tcp',
        'turns:turn.example.net:5349?transport=tcp',
      ],
      username: temporaryTurnUsername,
      credential: temporaryTurnPassword,
    },
  ],
  iceTransportPolicy: 'all',
});
~~~

Ý nghĩa:

- urls chứa STUN/TURN URI mà ICE agent có thể dùng.
- username và credential được dùng khi kết nối tới TURN server.
- STUN Binding thông thường không cần username/credential như TURN Allocate.
- iceTransportPolicy='all' cho phép ICE xem xét các candidate type phù hợp, gồm host, srflx và relay.

Các địa chỉ và port trong ví dụ là giá trị minh họa. Production cần thay bằng STUN/TURN endpoint của tổ chức hoặc nhà cung cấp đã được cấu hình.

### 6.1. Chỉ sử dụng relay candidate

Nếu ứng dụng cần tránh tiết lộ địa chỉ IP của thiết bị cho peer, có thể đặt:

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: 'turns:turn.example.net:5349?transport=tcp',
      username: temporaryTurnUsername,
      credential: temporaryTurnPassword,
    },
  ],
  iceTransportPolicy: 'relay',
});
~~~

relay policy chỉ cho phép relay candidates được đưa vào pool candidate của ICE. Điều này buộc đường truyền sử dụng TURN nếu kết nối thành công, nhưng có thể tăng latency, băng thông relay và chi phí.

Nếu TURN không truy cập được hoặc credential hết hạn, kết nối có thể thất bại vì host/srflx candidates đã bị loại khỏi lựa chọn.

### 6.2. Cấu hình nhiều TURN transport

Một số mạng chặn UDP nhưng cho phép TCP/TLS đi qua firewall. Có thể cung cấp nhiều TURN URL để browser thử các transport phù hợp:

| URI | Ý nghĩa thường gặp |
| --- | --- |
| turn:turn.example.net:3478?transport=udp | TURN qua UDP |
| turn:turn.example.net:3478?transport=tcp | TURN qua TCP |
| turns:turn.example.net:5349?transport=tcp | TURN qua TLS/TCP |

Không phải mọi browser hoặc hạ tầng đều hỗ trợ mọi tổ hợp giống nhau. Kiểm tra browser compatibility, firewall, TLS certificate và port range trong môi trường thực tế.

### 6.3. Thu thập candidate bằng JavaScript

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    { urls: 'stun:stun.example.net:3478' },
    {
      urls: 'turn:turn.example.net:3478?transport=udp',
      username: temporaryTurnUsername,
      credential: temporaryTurnPassword,
    },
  ],
});

pc.createDataChannel('probe');

pc.addEventListener('icecandidate', (event) => {
  if (event.candidate) {
    console.log({
      type: event.candidate.type,
      protocol: event.candidate.protocol,
    });
  } else {
    console.log('ICE candidate gathering completed');
  }
});

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
~~~

Ví dụ trên chỉ thu thập candidate. Chưa có remote peer và chưa thực hiện connectivity check với peer, vì vậy không thể kết luận kết nối media/data thực tế sẽ thành công.

## 7. TURN credential và xác thực

TURN relay tiêu thụ tài nguyên của server. Nếu cho phép anonymous allocation, người ngoài có thể dùng server làm relay và tạo chi phí băng thông hoặc abuse traffic. Production WebRTC nên bật cơ chế xác thực TURN và cấp credential theo người dùng/phiên.

### 7.1. Long-term credentials

TURN hỗ trợ cơ chế long-term credential với username, password, realm và nonce. Client dùng credential để xác thực request như Allocate và các thao tác liên quan.

Không đặt username/password cố định có quyền sử dụng TURN trong JavaScript bundle hoặc HTML. Mọi người dùng có thể xem source, DevTools, network request hoặc cấu hình runtime để lấy credential.

### 7.2. Credential ngắn hạn qua backend

Một mô hình phổ biến:

1. Người dùng đăng nhập ứng dụng qua HTTPS.
2. Browser gọi endpoint backend để xin TURN credential.
3. Backend kiểm tra session và quyền tham gia cuộc gọi.
4. Backend tạo username/password có thời hạn ngắn theo cơ chế TURN provider hỗ trợ.
5. Browser nhận credential và đưa vào RTCIceServer.
6. TURN server xác thực credential và giới hạn allocation theo thời hạn/quota.

Backend giữ shared secret; browser chỉ nhận credential tạm thời được tạo cho phiên. Khi credential bị lộ, thời gian sử dụng và phạm vi thiệt hại bị giới hạn.

### 7.3. TURN REST-style temporary credentials

coturn hỗ trợ mô hình xác thực dựa trên shared secret thường được gọi là TURN REST API/time-limited credentials. Một cách triển khai dùng username chứa timestamp hết hạn và user identifier; password được tính bằng HMAC với shared secret mà backend và TURN server cùng biết.

Đây là quy ước triển khai của hệ sinh thái coturn, không phải một HTTP REST API chung được TURN protocol bắt buộc. Hãy dùng cơ chế chính thức của TURN provider và thư viện phù hợp; không tự thiết kế định dạng credential khác với server.

Ví dụ cấu hình browser nhận credential từ backend:

~~~js
async function getIceServers() {
  const response = await fetch('/api/webrtc/turn-credentials', {
    credentials: 'same-origin',
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error('Không lấy được TURN credentials');
  }

  const data = await response.json();

  return [
    { urls: 'stun:stun.example.net:3478' },
    {
      urls: data.turnUrls,
      username: data.username,
      credential: data.credential,
    },
  ];
}

const iceServers = await getIceServers();
const pc = new RTCPeerConnection({ iceServers });
~~~

Endpoint credential cần xác thực session, chống CSRF theo cơ chế HTTP của ứng dụng, rate limit và trả Cache-Control: no-store. Không ghi credential vào log hoặc analytics.

### 7.4. Credential hết hạn không đồng nghĩa connection tự đóng

TURN credential được dùng để xác thực thao tác với TURN server. Khi credential hết hạn, allocation đang tồn tại có thể vẫn hoạt động cho tới khi lifetime/refresh hoặc policy của server yêu cầu xác thực lại. Không dựa vào việc credential hết hạn như cơ chế revoke tức thì.

Nếu cần thu hồi phiên, ứng dụng nên đóng RTCPeerConnection, ngừng sử dụng allocation, thu hồi session ở signaling/backend và áp dụng chính sách quota/credential của TURN server.

## 8. Bảo vệ TURN server khỏi open relay và abuse

TURN server công khai là một dịch vụ có thể tiêu thụ nhiều băng thông. Cấu hình sai có thể cho phép bất kỳ ai dùng server làm relay.

### 8.1. Không cho phép anonymous allocation trong production

- Bật long-term credential hoặc cơ chế authentication secret phù hợp.
- Tắt no-auth/anonymous access trên listener dành cho ứng dụng WebRTC.
- Không dùng một credential tĩnh chung cho tất cả client.
- Cấp credential ngắn hạn gắn với user/session.
- Thu hồi shared secret nếu bị lộ và xoay vòng theo kế hoạch.

### 8.2. Giới hạn allocation và lưu lượng

Đặt giới hạn phù hợp cho:

- Số allocation đồng thời trên mỗi user/account/IP.
- Băng thông vào/ra và tổng lưu lượng theo phiên.
- Thời gian allocation và refresh.
- Dải relay port min/max trên firewall.
- Kích thước packet và tần suất request.
- Số kết nối đồng thời và tốc độ tạo phiên.

Không đặt quota quá thấp khiến cuộc gọi hợp lệ bị ngắt; cần đo lưu lượng thực tế, peak concurrency và mức bitrate media.

### 8.3. Bảo vệ listener và relay network

- Chỉ mở các listener UDP/TCP/TLS cần thiết.
- Cấu hình firewall cho listener ports và relay port range.
- Nếu server nằm sau NAT, cấu hình external/public IP mapping chính xác.
- Dùng TLS certificate hợp lệ cho turns endpoint.
- Giữ coturn và hệ điều hành được cập nhật.
- Không công khai admin/metrics interface trên Internet nếu không cần.
- Giới hạn relay traffic tới các dải địa chỉ phù hợp với chính sách mạng.

### 8.4. Tránh TURN server thành proxy cho địa chỉ nội bộ

TURN relay có thể gửi traffic tới peer address được client yêu cầu. Cần áp dụng chính sách chống truy cập tới các dải IP nội bộ, loopback, link-local hoặc địa chỉ hạ tầng nhạy cảm nếu mô hình triển khai yêu cầu. Kiểm tra khả năng peer address restriction và deny peer IP của TURN server.

Đây là biện pháp quan trọng khi TURN server có thể được dùng bởi nhiều tenant hoặc client không hoàn toàn tin cậy. Không để TURN trở thành đường đi tới metadata endpoint hoặc dịch vụ quản trị trong mạng nội bộ.

### 8.5. Theo dõi dấu hiệu abuse

Theo dõi:

- Số allocation theo user, IP, realm và thời gian.
- Lưu lượng relay theo phiên và theo tenant.
- Tỷ lệ authentication failure và stale credential.
- Allocation tăng đột biến hoặc tồn tại bất thường.
- Traffic tới destination/port không thuộc use case.
- CPU, memory, network throughput và relay port exhaustion.

Khi phát hiện abuse, có thể revoke credential, chặn account/IP, giới hạn allocation, giảm quota hoặc cô lập relay node bị ảnh hưởng.

## 9. IP privacy và lựa chọn đường truyền

ICE candidate có thể chứa địa chỉ IP của thiết bị hoặc địa chỉ NAT public. Khi candidate được gửi qua signaling tới peer, peer có thể biết thông tin mạng tương ứng.

### 9.1. STUN có thể tiết lộ public mapped address

Server-reflexive candidate chứa địa chỉ public mà STUN server quan sát. Nó có thể cung cấp thông tin về mạng, nhà cung cấp Internet hoặc khu vực địa lý ở mức nhất định.

Host candidate cũng có thể tiết lộ địa chỉ interface nội bộ. Các browser hiện đại có thể dùng mDNS để che địa chỉ host trong một số tình huống, nhưng điều đó không thay thế việc đánh giá candidate và privacy policy.

### 9.2. TURN-only giúp ẩn địa chỉ peer khỏi peer còn lại

Đặt iceTransportPolicy='relay' để ICE chỉ sử dụng relay candidate:

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: 'turns:turn.example.net:5349?transport=tcp',
      username: temporaryTurnUsername,
      credential: temporaryTurnPassword,
    },
  ],
  iceTransportPolicy: 'relay',
});
~~~

Peer nhận relay address của TURN server thay vì host/srflx candidate của thiết bị bên kia. Điều này giúp che địa chỉ IP thiết bị khỏi peer trong phạm vi kết nối WebRTC được cấu hình relay-only.

Khi đánh giá privacy, hãy kiểm tra cả related address/related port trong candidate và SDP. Một relay candidate có thể có thông tin địa chỉ liên quan phục vụ chẩn đoán; không giả định chỉ đặt relay policy là mọi metadata địa chỉ đã được ẩn trong mọi browser. Dùng cơ chế privacy của browser, kiểm tra candidate thực tế và tránh chuyển tiếp hoặc ghi log trường địa chỉ không cần thiết.

### 9.3. TURN-only không ẩn IP khỏi mọi bên

TURN-only không có nghĩa ẩn IP khỏi:

- Website/signaling service mà người dùng truy cập qua HTTPS.
- TURN server nhận kết nối relay.
- Nhà mạng, VPN hoặc hạ tầng mạng trên đường tới TURN.
- Dịch vụ khác mà browser gọi ngoài WebRTC.

Nó chủ yếu giảm việc tiết lộ địa chỉ mạng của một peer cho peer còn lại. Nếu mục tiêu là ẩn địa chỉ khỏi website, cần cơ chế privacy ở client/network riêng; chỉ cấu hình TURN không giải quyết mục tiêu đó.

### 9.4. Privacy và hiệu năng có đánh đổi

| Lựa chọn | Quyền riêng tư với peer | Hiệu năng/chi phí |
| --- | --- | --- |
| ICE all, có direct candidate | Peer có thể thấy host hoặc srflx candidate tùy browser | Có cơ hội đi đường trực tiếp, thường giảm latency và relay cost |
| ICE relay-only | Peer chỉ thấy relay candidate nếu cấu hình hoạt động đúng | Traffic qua TURN, tăng latency và băng thông server |
| Chờ người dùng chấp nhận cuộc gọi rồi mới gửi candidate | Giảm việc tiết lộ IP/presence trước khi người dùng trả lời | Có thể tăng thời gian thiết lập sau khi accept |

Hãy giải thích trade-off cho sản phẩm. Một ứng dụng họp nội bộ có thể ưu tiên TURN để đáp ứng chính sách privacy; ứng dụng game thời gian thực có thể cần đường trực tiếp để giảm latency.

## 10. Bảo mật signaling và ICE candidate

STUN/TURN không thay thế signaling an toàn. Ứng dụng vẫn cần bảo vệ kênh trao đổi SDP và candidate.

- Dùng HTTPS/WSS cho signaling.
- Xác thực người dùng và quyền tham gia room trước khi nhận offer/answer.
- Chỉ chuyển candidate tới peer thuộc đúng session.
- Ràng buộc candidate với call ID, participant và ICE generation.
- Không cho client tự thêm peer vào room hoặc đổi recipient tùy ý.
- Validate kích thước và cấu trúc SDP/candidate trước khi xử lý.
- Không ghi toàn bộ SDP/candidate vào log công khai nếu chứa địa chỉ mạng hoặc identifier nhạy cảm.
- Dùng cơ chế chống replay và kiểm soát trạng thái signaling phù hợp.

Candidate exchange có thể được thực hiện qua WebSocket, nhưng WebSocket chỉ là transport của signaling. Nó không xác thực ICE candidate hoặc cấp relay allocation.

## 11. Thực hành: quan sát STUN/TURN candidate trong browser

Bài lab dùng browser hiện đại và Node.js 18 trở lên, không cần package ngoài. Node.js chỉ phục vụ trang lab trên localhost; STUN/TURN server phải là endpoint mà bạn được phép sử dụng.

Lab cho phép:

- Nhập STUN URL.
- Nhập TURN URL, temporary username và credential.
- Chọn policy all hoặc relay.
- Thu thập candidate và hiển thị type/protocol.
- Không hiển thị raw candidate line hoặc IP address để tránh vô tình lộ thông tin mạng khi chụp màn hình.

Nếu chỉ có STUN server, bạn có thể quan sát host và srflx candidate. Muốn thấy relay candidate, cần TURN server đã cấp credential hợp lệ.

### 11.1. Tạo file index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STUN and TURN candidate lab</title>
  <style>
    body {
      font: 16px system-ui, sans-serif;
      max-width: 850px;
      margin: 32px auto;
      padding: 0 16px;
    }
    label {
      display: block;
      margin: 12px 0;
    }
    input, select, button {
      box-sizing: border-box;
      padding: 8px;
      max-width: 100%;
    }
    input {
      width: 100%;
    }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f2f2f2;
      padding: 12px;
    }
  </style>
</head>
<body>
  <h1>STUN and TURN candidate lab</h1>
  <p>Nhập server được cấp cho lab. Không dùng credential production lâu dài.</p>

  <label>
    STUN URL
    <input id="stunUrl" value="stun:stun.example.net:3478">
  </label>

  <label>
    TURN URL
    <input id="turnUrl" value="turn:turn.example.net:3478?transport=udp">
  </label>

  <label>
    TURN username
    <input id="turnUsername" autocomplete="off">
  </label>

  <label>
    TURN credential
    <input id="turnCredential" type="password" autocomplete="new-password">
  </label>

  <label>
    ICE transport policy
    <select id="policy">
      <option value="all">all</option>
      <option value="relay">relay only</option>
    </select>
  </label>

  <button id="gather">Gather candidates</button>
  <button id="stop">Close peer connection</button>

  <h2>ICE gathering state</h2>
  <pre id="state">new</pre>

  <h2>Candidate summary</h2>
  <pre id="candidates">Chưa thu thập candidate.</pre>

  <script>
    let pc = null;
    const candidates = new Set();

    const stateOutput = document.querySelector('#state');
    const candidateOutput = document.querySelector('#candidates');

    function closePeerConnection() {
      if (pc) {
        pc.close();
        pc = null;
      }
    }

    function showCandidates() {
      candidateOutput.textContent = candidates.size
        ? Array.from(candidates).sort().join('\n')
        : 'Không có candidate nào được thu thập.';
    }

    document.querySelector('#stop').addEventListener('click', () => {
      closePeerConnection();
      stateOutput.textContent = 'closed';
    });

    document.querySelector('#gather').addEventListener('click', async () => {
      closePeerConnection();
      candidates.clear();
      showCandidates();
      stateOutput.textContent = 'gathering';

      const iceServers = [];
      const stunUrl = document.querySelector('#stunUrl').value.trim();
      const turnUrl = document.querySelector('#turnUrl').value.trim();
      const username = document.querySelector('#turnUsername').value;
      const credential = document.querySelector('#turnCredential').value;
      const policy = document.querySelector('#policy').value;

      if (stunUrl) {
        iceServers.push({ urls: stunUrl });
      }

      if (turnUrl) {
        if (!username || !credential) {
          stateOutput.textContent = 'error';
          candidateOutput.textContent =
            'TURN URL đã nhập nhưng thiếu username hoặc credential.';
          return;
        }

        iceServers.push({
          urls: turnUrl,
          username,
          credential,
        });
      }

      try {
        pc = new RTCPeerConnection({
          iceServers,
          iceTransportPolicy: policy,
        });

        pc.createDataChannel('candidate-probe');

        pc.addEventListener('icegatheringstatechange', () => {
          stateOutput.textContent = pc.iceGatheringState;
        });

        pc.addEventListener('icecandidate', (event) => {
          if (
            !event.candidate ||
            event.candidate.candidate === ''
          ) {
            stateOutput.textContent = 'complete';
            showCandidates();
            return;
          }

          const candidate = event.candidate;
          candidates.add(
            'type=' + candidate.type +
            ', protocol=' + candidate.protocol
          );
          showCandidates();
        });

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
      } catch (error) {
        stateOutput.textContent = 'error';
        candidateOutput.textContent = error.name + ': ' + error.message;
        closePeerConnection();
      }
    });
  </script>
</body>
</html>
~~~

### 11.2. Tạo file server.mjs

~~~js
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const htmlPath = resolve('index.html');

createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost:3000');

  if (url.pathname !== '/') {
    response.writeHead(404, {
      'Content-Type': 'text/plain; charset=utf-8',
    });
    response.end('Not found');
    return;
  }

  try {
    const html = await readFile(htmlPath);
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(html);
  } catch {
    response.writeHead(500, {
      'Content-Type': 'text/plain; charset=utf-8',
    });
    response.end('Không đọc được index.html');
  }
}).listen(3000, () => {
  console.log('Open http://localhost:3000');
});
~~~

### 11.3. Chạy lab

~~~bash
node server.mjs
~~~

Mở http://localhost:3000. Nhập STUN/TURN endpoint do tổ chức hoặc môi trường lab cấp. Nếu chưa có TURN credential, để trống TURN URL và chỉ thử STUN.

### 11.4. Quan sát STUN candidate

1. Nhập STUN URL hợp lệ.
2. Để TURN URL trống.
3. Chọn policy all.
4. Nhấn Gather candidates.
5. Quan sát các candidate type được browser thu thập.

Tùy mạng và browser, có thể thấy host và srflx candidate. Nếu STUN server không truy cập được, candidate srflx có thể không xuất hiện. Host candidate có thể được browser biểu diễn bằng mDNS hoặc ẩn theo privacy policy.

### 11.5. Quan sát relay candidate

1. Nhập TURN URL.
2. Nhập temporary username và credential hợp lệ.
3. Chọn policy all.
4. Nhấn Gather candidates.
5. Tìm candidate có type=relay.

Nếu relay candidate không xuất hiện, kiểm tra credential, TURN listener, DNS, firewall, relay port range và transport URL. Một TURN server có thể reachable trên listener nhưng relay port range lại bị firewall chặn.

### 11.6. Thử relay-only

Chọn policy relay only rồi gather lại. Nếu TURN server và credential hợp lệ, các candidate được hiển thị phải thuộc loại relay. Nếu không có relay candidate, ICE không có đường candidate để sử dụng theo policy này.

### 11.7. Giới hạn lab

- Lab chỉ thu thập candidate; không tạo remote peer, không chạy connectivity check hai phía và không chọn selected candidate pair.
- Candidate summary chỉ hiển thị type/protocol để tránh in địa chỉ IP ra màn hình.
- STUN/TURN endpoint và credential phải được cấp riêng; giá trị example.net không phải server công khai có thể dùng.
- Lab không kiểm tra chất lượng media, latency hoặc băng thông relay.
- Browser có thể thay đổi cách hiển thị host candidate theo mDNS và chính sách privacy.

## 12. Chẩn đoán lỗi STUN/TURN

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có srflx candidate | STUN DNS/port không truy cập được, UDP bị chặn hoặc Binding request thất bại | Kiểm tra DNS, firewall, STUN listener và ICE gathering log |
| Không có relay candidate | TURN credential sai/hết hạn, Allocate bị từ chối hoặc relay port range bị chặn | Kiểm tra TURN auth, realm, expiry, listener và relay ports |
| Có candidate nhưng ICE không connected | Candidate exchange lỗi, NAT/firewall chặn pair, peer không reachable | Kiểm tra signaling, connectivity checks và candidate pair state |
| Chỉ hoạt động trên cùng Wi-Fi | Đường host candidate hoạt động nhưng NAT traversal qua Internet thất bại | Thêm STUN/TURN và thử mạng khác |
| Hoạt động khi tắt VPN | VPN thay đổi route, UDP policy hoặc candidate/interface được sử dụng | Kiểm tra interface, DNS, UDP và TURN TCP/TLS fallback |
| Relay-only thất bại | TURN không khả dụng hoặc credential không hợp lệ | Kiểm tra credential và relay port range trước khi đổi policy |
| Cuộc gọi có độ trễ cao | Media đang đi qua TURN xa hoặc transport TCP/TLS qua mạng nghẽn | Kiểm tra selected candidate pair, region và relay transport |
| TURN bill tăng đột biến | Open relay, credential bị lộ, allocation abuse hoặc bitrate/concurrency tăng | Kiểm tra quota, auth failures, allocation và traffic theo user/IP |

### 12.1. Dùng getStats để kiểm tra selected pair

Khi đã kết nối với peer thật, getStats() có thể giúp xác định candidate pair đang được chọn:

~~~js
async function inspectSelectedCandidatePair(pc) {
  const stats = await pc.getStats();
  let selectedPairId = null;

  for (const report of stats.values()) {
    if (report.type === 'transport' && report.selectedCandidatePairId) {
      selectedPairId = report.selectedCandidatePairId;
      break;
    }
  }

  if (!selectedPairId) {
    for (const report of stats.values()) {
      if (
        report.type === 'candidate-pair' &&
        report.state === 'succeeded' &&
        report.nominated
      ) {
        selectedPairId = report.id;
        break;
      }
    }
  }

  const pair = selectedPairId
    ? stats.get(selectedPairId)
    : null;

  if (!pair) {
    return { selected: false };
  }

  const local = stats.get(pair.localCandidateId);
  const remote = stats.get(pair.remoteCandidateId);

  return {
    selected: true,
    localType: local?.candidateType ?? null,
    remoteType: remote?.candidateType ?? null,
    protocol: local?.protocol ?? null,
    currentRoundTripTime: pair.currentRoundTripTime ?? null,
    availableOutgoingBitrate: pair.availableOutgoingBitrate ?? null,
  };
}
~~~

Candidate type local/remote cho biết đường truyền đang dùng host, srflx hay relay. Không log address/port nếu không cần cho chẩn đoán; đây là dữ liệu mạng có thể nhạy cảm.

## 13. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ STUN tự mở cổng NAT | Có srflx candidate nhưng peer vẫn không kết nối được | Dùng ICE connectivity checks và cung cấp TURN fallback |
| Nghĩ STUN chuyển tiếp media | Kỳ vọng media đi qua STUN server | Dùng TURN khi cần relay |
| Không cấu hình TURN vì STUN hoạt động trên Wi-Fi | Cuộc gọi lỗi ở mạng doanh nghiệp/di động | Cung cấp TURN UDP và TCP/TLS fallback |
| Dùng TURN anonymous | Server có thể bị dùng làm open relay | Bật authentication, quota và credential ngắn hạn |
| Nhúng shared secret trong JavaScript | Bất kỳ client nào cũng có thể tạo credential | Chỉ backend giữ secret và cấp temporary credential |
| Dùng credential tĩnh cho mọi user | Credential bị lộ có phạm vi sử dụng rộng | Cấp username/password có expiry và gắn session/user |
| Chỉ mở listener port mà quên relay range | Allocate thành công nhưng media không đi qua được | Mở relay port range trên firewall/NAT |
| Nghĩ relay-only ẩn IP khỏi website | Website vẫn thấy IP qua HTTP/signaling; TURN cũng thấy IP client | Xác định rõ privacy cần bảo vệ khỏi peer hay khỏi service |
| Log toàn bộ candidate | Lộ địa chỉ mạng và thông tin môi trường | Chỉ log type/protocol hoặc redact địa chỉ |
| Không giới hạn allocation/bandwidth | Chi phí tăng và relay node có thể cạn tài nguyên | Quota theo user, rate limit và monitoring |
| Dùng STUN/TURN credential làm user authentication | Credential relay không chứng minh quyền ứng dụng | Authentication ở signaling/backend; TURN credential chỉ cấp quyền dùng relay |

## 14. Checklist triển khai STUN/TURN

1. **Có ICE fallback đầy đủ:** thu thập host/srflx/relay candidate theo nhu cầu và kiểm tra connectivity pair.
2. **Triển khai TURN production:** không dựa vào STUN đơn lẻ cho mọi loại mạng.
3. **Hỗ trợ nhiều transport:** cân nhắc TURN UDP, TCP và TLS/TCP theo firewall/browser.
4. **Bật TURN authentication:** không để listener production cho anonymous allocation.
5. **Cấp credential ngắn hạn:** backend xác thực user/session rồi tạo credential theo provider.
6. **Giữ shared secret ở server:** không gửi secret tới browser hoặc commit vào source control.
7. **Giới hạn allocation:** quota theo user, IP, tenant và concurrency.
8. **Giới hạn relay ports:** đồng bộ cấu hình server, NAT và firewall.
9. **Chặn peer address nguy hiểm:** áp dụng restriction với loopback, private/link-local và hạ tầng nội bộ theo chính sách.
10. **Bảo vệ signaling:** HTTPS/WSS, xác thực room và kiểm tra participant trước khi chuyển candidate.
11. **Đánh giá IP privacy:** dùng relay-only khi cần che IP peer và chấp nhận trade-off.
12. **Giảm dữ liệu log:** không ghi raw candidate hoặc TURN credential nếu không cần.
13. **Theo dõi chi phí:** đo allocation, bytes relayed, bandwidth, latency và auth failures.
14. **Kiểm thử nhiều mạng:** Wi-Fi gia đình, mạng di động, VPN và mạng doanh nghiệp có firewall.
15. **Chuẩn bị sự cố:** biết cách rotate shared secret, revoke credential, block abuse và scale relay capacity.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “STUN và TURN là cùng một dịch vụ.” | STUN khám phá mapped address và hỗ trợ checks; TURN cấp relay address và chuyển tiếp packet. |
| “Có srflx candidate nghĩa là kết nối trực tiếp chắc chắn thành công.” | NAT/firewall có thể vẫn chặn candidate pair; ICE phải kiểm tra connectivity. |
| “TURN chỉ là STUN có thêm IP.” | TURN duy trì allocation, permission/channel state và relay traffic. |
| “Signaling server là STUN server.” | Signaling trao đổi SDP/candidate; STUN/TURN hỗ trợ tìm và chuyển tiếp đường media. |
| “TURN giải mã media.” | Trong WebRTC thông thường, TURN chuyển tiếp packet DTLS-SRTP được mã hóa giữa các endpoint. |
| “Credential TURN là credential đăng nhập ứng dụng.” | Nó chỉ xác thực việc sử dụng TURN relay; ứng dụng cần authentication riêng. |
| “Credential hết hạn lập tức đóng mọi allocation.” | Allocation có lifetime/refresh riêng; cần cơ chế đóng phiên và revoke ở tầng ứng dụng. |
| “Relay-only ẩn IP khỏi mọi bên.” | Nó giảm tiết lộ IP của peer cho peer còn lại; website và TURN server vẫn có thể biết IP client. |
| “TURN càng nhiều server càng tốt.” | Cần chọn region, capacity, quota và fallback theo latency/chi phí thực tế. |
| “Candidate line có thể log công khai.” | Candidate có thể chứa IP, port và thông tin mạng nhạy cảm. |

## 16. Câu hỏi tự đánh giá

**Câu 1.** STUN Binding response cung cấp thông tin gì cho ICE?

**Gợi ý trả lời:** Nó cung cấp mapped/reflexive transport address mà STUN server quan sát, thường qua XOR-MAPPED-ADDRESS; ICE dùng nó để tạo server-reflexive candidate.

**Câu 2.** Vì sao STUN không bảo đảm kết nối trực tiếp?

**Gợi ý trả lời:** NAT mapping/filtering và firewall behavior có thể ngăn packet từ peer tới địa chỉ đã khám phá; ICE phải chạy connectivity checks.

**Câu 3.** TURN khác STUN ở điểm cốt lõi nào?

**Gợi ý trả lời:** TURN cấp relay allocation và chuyển tiếp packet giữa client với peer; STUN Binding chỉ khám phá mapped address và không relay media.

**Câu 4.** Bốn loại candidate trong ICE là gì?

**Gợi ý trả lời:** host, server-reflexive, peer-reflexive và relay.

**Câu 5.** Khi nào nên dùng iceTransportPolicy='relay'?

**Gợi ý trả lời:** Khi cần buộc traffic WebRTC đi qua TURN, ví dụ để hạn chế peer thấy địa chỉ IP của thiết bị; phải chấp nhận chi phí và latency cao hơn.

**Câu 6.** Vì sao không nhúng TURN shared secret trong JavaScript?

**Gợi ý trả lời:** Client có thể đọc source và runtime config; shared secret bị lộ sẽ cho phép tạo credential relay ngoài kiểm soát. Backend phải giữ secret và cấp credential ngắn hạn.

**Câu 7.** TURN credential có thay thế application authentication không?

**Gợi ý trả lời:** Không. Nó chỉ xác thực việc sử dụng relay; signaling/backend vẫn phải xác thực user và kiểm tra quyền tham gia phiên.

**Câu 8.** Relay-only có ẩn IP khỏi website không?

**Gợi ý trả lời:** Không. Nó chủ yếu che địa chỉ của peer khỏi peer còn lại; website và TURN server vẫn có thể quan sát IP của client.

**Câu 9.** Vì sao cần giới hạn allocation và relay bandwidth?

**Gợi ý trả lời:** TURN chuyển tiếp traffic thực nên có thể bị lạm dụng để tạo chi phí, cạn relay port, băng thông hoặc tài nguyên server.

## Tài liệu tham khảo

- IETF — [RFC 8489: Session Traversal Utilities for NAT (STUN)](https://www.rfc-editor.org/rfc/rfc8489.html).
- IETF — [RFC 8656: Traversal Using Relays around NAT (TURN)](https://www.rfc-editor.org/rfc/rfc8656.html).
- IETF — [RFC 8445: Interactive Connectivity Establishment (ICE)](https://www.rfc-editor.org/rfc/rfc8445.html).
- IETF — [RFC 8827: WebRTC Security Architecture](https://www.rfc-editor.org/rfc/rfc8827.html).
- IETF — [RFC 8828: WebRTC IP Address Handling Requirements](https://www.rfc-editor.org/rfc/rfc8828.html).
- MDN — [Introduction to WebRTC protocols](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Protocols).
- MDN — [RTCPeerConnection() constructor](https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/RTCPeerConnection).
- MDN — [RTCIceCandidate](https://developer.mozilla.org/en-US/docs/Web/API/RTCIceCandidate).
- coturn — [TURN server documentation and TURN REST API credentials](https://github.com/coturn/coturn/wiki/turnserver).
