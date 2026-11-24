# IP privacy: bảo vệ địa chỉ mạng trong WebRTC

WebRTC cho phép trình duyệt thiết lập kết nối thời gian thực giữa các peer để truyền âm thanh, video hoặc dữ liệu. Để tìm đường kết nối hiệu quả, ICE thu thập và kiểm tra nhiều địa chỉ mạng. Các địa chỉ này có thể tiết lộ thông tin nhiều hơn một request HTTP thông thường: địa chỉ IP cục bộ, địa chỉ public do NAT ánh xạ, cấu trúc mạng, loại kết nối và đôi khi cả đường mạng thực mà thiết bị đang sử dụng.

IP privacy trong WebRTC là việc kiểm soát ai có thể nhìn thấy các địa chỉ đó, khi nào địa chỉ được thu thập và loại candidate nào được phép dùng. Mục tiêu không chỉ là ẩn IP khỏi peer. JavaScript của website, signaling server, STUN server và TURN server có thể quan sát những phần khác nhau của đường kết nối.

Không có một cài đặt duy nhất bảo vệ mọi phía. mDNS có thể che địa chỉ host cục bộ khỏi JavaScript và signaling ở một số trình duyệt; `iceTransportPolicy: "relay"` giới hạn ICE vào relay candidates để peer không nhận địa chỉ trực tiếp của người dùng; TURN chuyển tiếp media nhưng máy chủ TURN vẫn nhìn thấy địa chỉ nguồn của kết nối. Website vẫn có thể nhìn thấy địa chỉ public của request HTTP thông thường.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao ICE có thể tiết lộ nhiều địa chỉ IP hơn HTTP.
- Phân biệt host, server-reflexive, peer-reflexive và relay candidates.
- Mô tả vai trò của ICE, STUN, TURN và signaling.
- Phân biệt IP mà website, signaling server, peer, STUN server và TURN server có thể quan sát.
- Giải thích cách mDNS che địa chỉ IP cục bộ trong host candidate.
- Cấu hình `iceTransportPolicy: "relay"` và hiểu trade-off của TURN-only.
- Nhận diện rủi ro khi dùng VPN, split tunnel, proxy và nhiều network interface.
- Trì hoãn ICE gathering cho đến khi người dùng chấp nhận cuộc gọi.
- Tránh gửi candidate hoặc SDP thô vào analytics và log không cần thiết.
- Kiểm thử IP privacy mà không công khai địa chỉ thật trong báo cáo.
- Thiết kế fallback khi TURN không truy cập được hoặc candidate privacy làm giảm khả năng kết nối.

## 1. Vì sao WebRTC có thể tiết lộ IP?

Với HTTP thông thường, web server nhìn thấy địa chỉ IP nguồn của kết nối đến server, thường là địa chỉ public sau NAT hoặc địa chỉ exit của proxy/VPN. JavaScript của trang không có API chung để đọc trực tiếp địa chỉ interface mạng của thiết bị.

WebRTC cần thiết lập đường truyền giữa các peer. Một peer có thể nằm sau NAT, firewall hoặc nhiều interface mạng. Vì vậy, ICE phải tìm các địa chỉ và thử các cặp đường truyền có thể sử dụng.

Các địa chỉ candidate được đưa đến WebRTC application qua API. Ứng dụng có thể chuyển tiếp chúng qua signaling để peer còn lại thực hiện connectivity checks. Điều này tạo thêm bề mặt lộ thông tin:

- Website có thể đọc candidate từ JavaScript và thu thập dữ liệu mạng.
- Signaling server có thể nhìn thấy candidate nếu ứng dụng gửi chúng qua server.
- Peer có thể biết địa chỉ được trao đổi trong signaling và sử dụng cho kết nối trực tiếp.
- STUN server nhìn thấy địa chỉ nguồn của gói STUN.
- TURN server nhìn thấy địa chỉ nguồn đang kết nối đến relay và chuyển tiếp dữ liệu.

### 1.1 Các loại địa chỉ có thể xuất hiện

| Loại địa chỉ | Ví dụ khái quát | Ý nghĩa |
|---|---|---|
| Private IPv4 | `192.168.x.x`, `10.x.x.x`, `172.16.x.x` đến `172.31.x.x` | Có thể tiết lộ mạng LAN hoặc mạng nội bộ |
| Link-local IPv4 | `169.254.x.x` | Có thể tiết lộ cấu hình interface cục bộ |
| IPv6 local | ULA hoặc link-local IPv6 | Có thể tiết lộ cấu trúc mạng IPv6 |
| Public IPv4/IPv6 | Địa chỉ được định tuyến trên Internet | Có thể tiết lộ ISP, vùng địa lý gần đúng hoặc đường mạng |
| TURN relay address | Địa chỉ của relay server | Peer nhìn thấy relay thay vì địa chỉ trực tiếp của người dùng |

Không phải mọi candidate đều chứa IP thật. Trình duyệt có thể thay địa chỉ host bằng tên mDNS hoặc áp dụng chính sách lọc candidate. Hành vi phụ thuộc browser, cấu hình, mạng và phiên bản.

### 1.2 IP address là dữ liệu fingerprinting

Địa chỉ IP có thể được kết hợp với:

- Loại mạng và ISP.
- Vùng địa lý gần đúng.
- IPv4/IPv6 availability.
- Số lượng interface hoặc candidate.
- Cấu trúc private subnet.
- Độ trễ đến các peer hoặc relay.
- Kết quả connectivity check.

Ngay cả khi địa chỉ private đã được che, số lượng candidate hoặc khả năng kết nối trực tiếp vẫn có thể cung cấp tín hiệu fingerprinting. Vì vậy, bảo vệ IP cần đi cùng data minimization và retention policy.

## 2. ICE, STUN, TURN và signaling

### 2.1 ICE

Interactive Connectivity Establishment (ICE) tìm đường truyền giữa hai peer. Mỗi peer thu thập ICE candidates, trao đổi chúng qua signaling rồi thử các cặp candidate để tìm đường hoạt động.

Một kết nối có thể thử nhiều cặp địa chỉ. Khi một cặp phù hợp được chọn, ICE dùng đường đó để vận chuyển media hoặc data channel.

### 2.2 STUN

STUN giúp một peer biết địa chỉ và port public mà NAT đang ánh xạ cho gói tin đi ra. Server STUN quan sát gói đến và phản hồi thông tin mapped address.

Địa chỉ đó thường trở thành server-reflexive candidate (`srflx`). Nó có thể tiết lộ public IP mà thiết bị dùng để truy cập STUN server.

STUN không chuyển tiếp media. Nó giúp khám phá mapping để peer có thể thử kết nối trực tiếp.

### 2.3 TURN

TURN cấp một relay allocation. Media hoặc data được gửi qua relay khi kết nối trực tiếp không khả dụng hoặc khi ứng dụng yêu cầu relay-only.

Peer đối diện nhìn thấy địa chỉ relay của TURN server thay vì địa chỉ trực tiếp của người dùng. Tuy nhiên, TURN server vẫn nhìn thấy địa chỉ IP nguồn của client đang kết nối đến relay. Nhà cung cấp TURN vì thế là một thành phần cần được tin cậy và quản lý.

### 2.4 Signaling

WebRTC không quy định một signaling transport duy nhất. Ứng dụng thường gửi SDP offer/answer và ICE candidates qua WebSocket hoặc HTTP.

Nếu signaling server nhận candidate thô, server có thể lưu hoặc log địa chỉ. TLS bảo vệ dữ liệu trên đường truyền, nhưng không ngăn server endpoint nhìn thấy payload sau khi giải mã.

### 2.5 Luồng kết nối

~~~text
Peer A / Browser                         Peer B / Browser
      |                                         |
      | Gather ICE candidates                   | Gather ICE candidates
      |---- STUN request ----------------------> STUN server
      |<--- mapped address ---------------------|
      |                                         |
      |---- SDP + candidates --> Signaling <----|
      |                                         |
      |<---------- SDP + candidates ------------|
      |                                         |
      |---------- ICE connectivity checks ----->|
      |<--------- ICE connectivity checks ------|
      |                                         |
      +======= direct media/data path ==========+
                     hoặc
      +======= TURN relay path =================+
~~~

Đường truyền cuối cùng có thể trực tiếp hoặc qua TURN. Loại candidate được dùng ảnh hưởng đến IP mà peer có thể quan sát.

## 3. ICE candidate và thông tin IP

Một ICE candidate chứa thông tin về địa chỉ, port, transport, priority và loại candidate. Candidate có thể xuất hiện trong SDP hoặc được chuyển tiếp riêng qua trickle ICE.

### 3.1 Host candidate

Host candidate đại diện cho địa chỉ interface cục bộ của peer. Đây có thể là địa chỉ private IPv4, IPv6 hoặc địa chỉ khác trên interface mạng.

Nếu interface được cấp trực tiếp một địa chỉ globally routable, host candidate cũng có thể là địa chỉ public. Vì vậy, tên loại `host` mô tả nguồn candidate, không bảo đảm địa chỉ là private.

Nếu lộ trực tiếp, host candidate có thể tiết lộ subnet nội bộ, cấu trúc mạng hoặc tạo một định danh giúp liên kết các phiên duyệt web.

Trình duyệt có thể che host IP bằng mDNS hostname như:

~~~text
a1b2c3d4-....local
~~~

Tên `.local` không trực tiếp cho JavaScript biết địa chỉ IP cục bộ. Trong các môi trường có thể kết nối trên cùng LAN, ICE agent có thể sử dụng cơ chế mDNS để phân giải tên trong quá trình connectivity check.

mDNS host obfuscation là một biện pháp giảm lộ IP cục bộ, nhưng không đồng nghĩa mọi thông tin mạng đã được ẩn.

### 3.2 Server-reflexive candidate (`srflx`)

Server-reflexive candidate phản ánh mapped address mà STUN server quan sát được sau NAT.

Địa chỉ này thường là public IP của đường mạng đang gửi STUN. Nó có thể khác địa chỉ mà web server quan sát được nếu WebRTC và HTTP đi qua các interface hoặc route khác nhau.

### 3.3 Peer-reflexive candidate (`prflx`)

Peer-reflexive candidate có thể được phát hiện trong quá trình ICE connectivity checks khi một peer nhận STUN packet từ địa chỉ chưa có trong danh sách candidate đã biết.

Candidate này thường xuất hiện trong quá trình kiểm tra kết nối, không nhất thiết là một candidate được thu thập và signaling ngay từ đầu.

### 3.4 Relay candidate

Relay candidate được cấp từ TURN server. Candidate chứa địa chỉ của relay allocation mà peer dùng để gửi dữ liệu qua TURN.

Khi chỉ dùng relay candidates, peer đối diện không cần biết địa chỉ trực tiếp của người dùng để truyền media. Tuy nhiên, TURN server vẫn cần biết địa chỉ nguồn của client để duy trì allocation và chuyển tiếp packet.

### 3.5 So sánh candidate

| Candidate type | Nguồn tạo | Thông tin có thể tiết lộ | Cách giảm lộ |
|---|---|---|---|
| `host` | Interface cục bộ | IP private/local, cấu trúc LAN | Browser mDNS, relay-only |
| `srflx` | STUN mapping | Public mapped IP | Relay-only; giới hạn đường mạng |
| `prflx` | Connectivity checks | Địa chỉ peer-reflexive | Relay-only; kiểm soát ICE policy |
| `relay` | TURN allocation | Địa chỉ relay, không phải IP trực tiếp của peer | Dùng TURN provider đáng tin cậy, bảo vệ log |

## 4. Ai nhìn thấy địa chỉ nào?

Cần xác định rõ đối tượng cần bảo vệ trước khi chọn giải pháp.

| Bên quan sát | Có thể thấy | Biện pháp giảm lộ |
|---|---|---|
| JavaScript của website | Candidate mà browser expose qua API | Browser IP handling, mDNS, relay-only |
| Signaling server | SDP/candidate mà client gửi qua signaling | Relay-only, giảm log, không lưu candidate lâu |
| Remote peer | Candidate được trao đổi và đường kết nối được chọn | Relay-only, trì hoãn ICE đến khi chấp nhận |
| STUN server | Địa chỉ nguồn của gói STUN | Chọn server tin cậy, hạn chế server không cần thiết |
| TURN server | Địa chỉ nguồn kết nối đến relay và metadata phiên | TURN provider tin cậy, retention thấp |
| HTTP web server | Public source IP của HTTP request | VPN/proxy/network routing; WebRTC policy không ẩn phần này |

### 4.1 Website vẫn có thể biết public IP qua HTTP

`iceTransportPolicy: "relay"` không làm cho website mất khả năng nhìn thấy public IP của request HTTP. Web server vẫn nhận kết nối từ địa chỉ mạng hoặc proxy exit của người dùng.

Relay-only bảo vệ chủ yếu việc ICE candidate trực tiếp được dùng và trao đổi với peer. Nó không phải VPN và không ẩn mọi traffic của trình duyệt.

### 4.2 Signaling server là một điểm quan sát

Nếu ứng dụng gửi SDP chứa candidate qua signaling server, server có thể đọc payload. Chỉ dùng WSS hoặc HTTPS không che nội dung khỏi chính server.

Nếu cần giảm retention:

- Không ghi SDP/candidate vào access log hoặc analytics.
- Không lưu candidate trong database lâu hơn thời gian cần.
- Xóa signaling session sau khi cuộc gọi kết thúc.
- Tránh ghi candidate thô vào error reporting.
- Dùng relay-only khi không muốn signaling server nhận địa chỉ trực tiếp.

### 4.3 Peer và website không phải cùng một bên

Ứng dụng có thể tin cậy website nhưng chưa tin cậy peer, ví dụ một cuộc gọi từ người lạ. Trong tình huống này, website có thể cần địa chỉ để vận hành, nhưng không muốn peer biết IP trực tiếp của người dùng.

Relay-only là lựa chọn quan trọng để giảm việc tiết lộ IP trực tiếp cho peer.

## 5. mDNS host candidate và giới hạn của nó

Một số trình duyệt dùng mDNS hostname để thay thế IP private trong host candidate trước khi expose cho web application.

Ví dụ candidate có thể có dạng:

~~~text
candidate:... 1 udp ... device-random-name.local 54321 typ host
~~~

Thay vì:

~~~text
candidate:... 1 udp ... 192.168.1.25 54321 typ host
~~~

### 5.1 mDNS giúp điều gì?

- Giảm việc JavaScript đọc trực tiếp địa chỉ private của interface.
- Giảm việc signaling server hoặc peer nhận private IP qua candidate đã được che.
- Hỗ trợ một số trường hợp kết nối cùng LAN bằng cách phân giải tên mDNS trong quá trình ICE.
- Giảm một nguồn fingerprinting dựa trên private IP.

### 5.2 mDNS không bảo vệ mọi IP

mDNS chủ yếu xử lý việc lộ địa chỉ host cục bộ. Nó không tự ẩn server-reflexive candidate có public mapped address.

Nếu ứng dụng vẫn gửi `srflx` candidate qua signaling, peer có thể nhìn thấy public IP. Muốn ngăn peer biết IP trực tiếp, hãy cân nhắc relay-only.

### 5.3 mDNS không phải cam kết đồng nhất trên mọi trình duyệt

Cách triển khai, điều kiện tạo hostname và khả năng phân giải có thể khác giữa browser, hệ điều hành, mạng doanh nghiệp và phiên bản.

Không viết ứng dụng dựa trên giả định rằng mọi host candidate luôn là `.local`. Hãy kiểm tra candidate thực tế mà browser expose trong môi trường mục tiêu.

mDNS hostname cũng có thể cung cấp tín hiệu fingerprinting như số lượng interface hoặc khả năng kết nối trong một số ngữ cảnh. Nó là một lớp giảm lộ địa chỉ, không phải bảo đảm ẩn danh.

## 6. Relay-only bằng iceTransportPolicy

WebRTC cung cấp `iceTransportPolicy` trong `RTCConfiguration`.

Hai giá trị tiêu chuẩn thường dùng:

- `all`: ICE agent có thể dùng các candidate phù hợp theo chính sách của browser.
- `relay`: ICE agent chỉ sử dụng relay candidates, chẳng hạn candidate đi qua TURN.

`all` là giá trị mặc định. Ngay cả khi chọn `all`, browser vẫn có thể áp dụng chính sách lọc candidate riêng vì lý do riêng tư hoặc bảo mật.

Ví dụ:

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: [
        "turn:turn.example.test:3478?transport=udp",
        "turns:turn.example.test:5349?transport=tcp"
      ],
      username: "short-lived-user",
      credential: "short-lived-password"
    }
  ],
  iceTransportPolicy: "relay"
});
~~~

Với cấu hình này, ICE chỉ dùng relay candidates. Ứng dụng cần cấp TURN credential ngắn hạn từ backend, không nhúng username/password cố định trong JavaScript bundle.

### 6.1 Điều gì được bảo vệ?

Relay-only giúp ngăn remote peer nhận địa chỉ IP trực tiếp của người dùng qua các candidate host/srflx được dùng cho kết nối. Nó cũng giới hạn candidate được expose cho ứng dụng theo policy của ICE agent.

Tuy nhiên:

- Website vẫn có thể biết public IP qua HTTP request.
- TURN server thấy IP nguồn của client.
- Signaling server vẫn thấy candidate được gửi qua signaling.
- Browser extension hoặc phần mềm trên thiết bị nằm ngoài threat model của API này.
- Không thể coi relay-only là bảo vệ chống mọi hình thức theo dõi mạng.

### 6.2 Trade-off của relay-only

| Lợi ích | Chi phí hoặc hạn chế |
|---|---|
| Peer không cần biết IP trực tiếp | Mọi media/data phải qua TURN |
| Giảm lộ IP qua ICE candidate | Tăng độ trễ và băng thông relay |
| Giảm rủi ro peer discovery mạng nội bộ | Có thể làm cuộc gọi không kết nối nếu TURN lỗi |
| Kiểm soát đường truyền tập trung | Tăng chi phí vận hành TURN |
| Phù hợp với peer chưa đáng tin | Chất lượng phụ thuộc vị trí và capacity của relay |

Relay-only thường phù hợp với cuộc gọi từ người lạ, dịch vụ tư vấn nhạy cảm, hoặc khi sản phẩm ưu tiên che địa chỉ IP khỏi peer hơn tối ưu đường truyền trực tiếp.

### 6.3 TURN cần được cấu hình đúng

Cần có TURN server reachable qua các transport phù hợp với mạng người dùng. Một số mạng chặn UDP; TURN TCP hoặc TLS có thể là fallback.

TURN server nên:

- Dùng credential ngắn hạn, có thời hạn.
- Giới hạn allocation và băng thông.
- Có rate limit và monitoring.
- Không ghi IP/call metadata quá thời hạn cần thiết.
- Được đặt ở vùng địa lý phù hợp với chính sách dữ liệu.
- Có xác thực và bảo vệ chống relay abuse.

Không dùng một TURN server công khai không rõ nhà vận hành cho dữ liệu nhạy cảm.

## 7. Trì hoãn ICE gathering cho đến khi người dùng chấp nhận

Một website có thể tạo `RTCPeerConnection` và bắt đầu thu thập candidate trước khi người dùng chấp nhận cuộc gọi. Điều này có thể tiết lộ địa chỉ mạng hoặc trạng thái online sớm hơn mong đợi.

Với cuộc gọi đến từ người lạ, ứng dụng có thể trì hoãn việc tạo offer/answer hoặc gọi `setLocalDescription()` cho đến khi người dùng chọn Accept.

Mô hình:

~~~text
Có cuộc gọi đến
      |
      v
Hiển thị thông tin người gọi
      |
      v
Người dùng chọn Accept?
   |             |
  Không          Có
   |             |
Không bắt đầu    Tạo/hoàn tất
ICE gathering    PeerConnection
                 |
                 v
             Trao đổi candidate
~~~

### 7.1 Ví dụ trì hoãn PeerConnection

~~~js
let peerConnection = null;

async function acceptCall(turnConfig) {
  peerConnection = new RTCPeerConnection({
    iceServers: turnConfig.iceServers,
    iceTransportPolicy: "relay"
  });

  const channel = peerConnection.createDataChannel("control");

  peerConnection.onicecandidate = event => {
    if (event.candidate) {
      sendCandidateThroughSignaling(event.candidate);
    }
  };

  const offer = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offer);

  sendOfferThroughSignaling(offer);
  return channel;
}
~~~

Ví dụ chỉ minh họa vị trí bắt đầu PeerConnection sau khi người dùng chấp nhận. Trong ứng dụng thực tế, signaling và SDP offer/answer cần được phối hợp theo vai trò caller/callee.

Không nhất thiết phải xin quyền camera/microphone mới có ICE candidate. Data channel hoặc peer connection không gắn media cũng có thể bắt đầu ICE. Vì vậy, không xem permission camera là ranh giới bảo vệ IP.

### 7.2 Không gửi candidate trước khi consent

Nếu sản phẩm muốn peer chưa biết IP trước khi người dùng chấp nhận, cần bảo đảm ứng dụng không gửi candidate hoặc SDP chứa candidate qua signaling sớm.

Chỉ trì hoãn giao diện hiển thị cuộc gọi là chưa đủ nếu code đã tạo PeerConnection và gửi candidate nền.

## 8. Candidate filtering và signaling

Ứng dụng thường nhận candidate qua sự kiện `icecandidate`:

~~~js
pc.onicecandidate = event => {
  if (event.candidate) {
    sendCandidateThroughSignaling(event.candidate);
  }
};
~~~

Candidate có thể chứa địa chỉ. Nếu ứng dụng chỉ muốn peer nhận relay candidates, có thể cấu hình relay-only ở ICE agent ngay từ đầu.

### 8.1 Không chỉ lọc candidate sau khi browser đã expose

Ví dụ:

~~~js
pc.onicecandidate = event => {
  if (!event.candidate) return;

  if (event.candidate.type === "relay") {
    sendCandidateThroughSignaling(event.candidate);
  }
};
~~~

Đoạn code này chỉ hạn chế candidate được gửi đến peer. Nó không ngăn JavaScript của chính trang đọc candidate host/srflx trước đó, và không ngăn script khác cùng trang truy cập đối tượng nếu có quyền.

Nếu mục tiêu là giảm IP mà application JavaScript nhìn thấy hoặc dùng, hãy dùng browser IP privacy controls khi có, và `iceTransportPolicy: "relay"` khi cần giới hạn candidate. Lọc signaling là lớp bổ sung cho phía peer, không phải thay thế relay policy.

### 8.2 Không sửa SDP bằng regex

Không xóa candidate line khỏi SDP bằng regex một cách tùy tiện. Việc sửa SDP có thể làm hỏng ICE credentials, media section hoặc candidate gathering state.

Dùng API WebRTC và policy chuẩn để giới hạn candidate. Nếu ứng dụng cần chỉ gửi relay candidate, thực hiện trong `onicecandidate` và vẫn cấu hình relay-only để candidate không được dùng ngoài ý muốn.

### 8.3 Không log raw SDP

SDP có thể chứa ICE username fragment, password, fingerprint và candidate address. Hãy coi SDP như dữ liệu phiên nhạy cảm:

- Không ghi raw SDP vào analytics.
- Không lưu vào application log ở production.
- Không gửi lên crash reporting nếu không redact.
- Xóa signaling payload sau khi phiên kết thúc theo retention policy.

## 9. VPN, proxy và split tunnel

Người dùng có thể bật VPN hoặc proxy để ẩn địa chỉ public gốc. Tuy nhiên, WebRTC có thể sử dụng đường mạng khác với HTTP tùy hệ điều hành, VPN route và cấu hình browser.

### 9.1 Split tunnel

Split tunnel định tuyến chỉ một phần traffic qua VPN. Nếu HTTP đi qua VPN nhưng UDP/STUN của WebRTC đi qua interface mạng trực tiếp, STUN server có thể nhìn thấy public IP của ISP thay vì VPN exit.

Điều này không phải lúc nào cũng xảy ra; kết quả phụ thuộc route table, firewall, VPN client và browser implementation. RFC 8828 mô tả đây là một trường hợp cần cân nhắc khi xử lý IP privacy.

### 9.2 HTTP proxy không đồng nghĩa WebRTC proxy

Một HTTP proxy có thể chỉ xử lý HTTP/HTTPS. WebRTC media thường dùng UDP và có thể không đi qua proxy đó.

Nếu muốn kiểm soát WebRTC traffic, cần cấu hình network policy hoặc TURN phù hợp, không chỉ bật proxy trong browser.

### 9.3 VPN không thay thế relay-only

VPN có thể thay đổi địa chỉ nguồn nhìn thấy trên một số đường mạng. Nhưng peer vẫn có thể nhận các host candidate hoặc candidate khác tùy browser và routing.

Nếu yêu cầu sản phẩm là peer không được biết IP trực tiếp, relay-only là kiểm soát ở tầng ICE rõ ràng hơn. VPN chỉ là một lớp mạng bổ sung và cần kiểm thử với split tunnel, IPv6 và các interface thực tế.

### 9.4 IPv6 và nhiều interface

Thiết bị có thể có IPv4, IPv6, Wi-Fi, Ethernet, VPN và interface ảo cùng lúc. Chỉ kiểm tra một địa chỉ IPv4 không đủ để đánh giá IP privacy.

Kiểm thử cần quan sát cả candidate IPv4/IPv6, host/srflx/relay và đường route thực tế.

## 10. Browser IP handling và mDNS

RFC 8828 mô tả các mức xử lý địa chỉ WebRTC với trade-off giữa hiệu năng và quyền riêng tư. Tùy browser, chính sách có thể giới hạn interface, địa chỉ private hoặc cách expose candidate.

Ứng dụng web không có một API chuẩn để ép browser dùng mọi chính sách IP handling nội bộ. Cấu hình `iceTransportPolicy` là cơ chế chuẩn phía ứng dụng để giới hạn ICE candidates vào relay.

### 10.1 Default route và các địa chỉ liên quan

Một browser có thể ưu tiên route mặc định để tránh sử dụng mọi interface. Tuy nhiên, tùy policy, địa chỉ private của interface được chọn vẫn có thể được dùng hoặc expose dưới dạng host candidate.

### 10.2 Default route only

Chính sách chỉ dùng default route và không expose địa chỉ private có thể giảm lộ thông tin mạng nội bộ. Nhưng direct connectivity có thể kém hơn, NAT hairpin có thể xảy ra hoặc kết nối cần TURN.

### 10.3 mDNS hostname

mDNS thay IP private trong host candidate bằng tên `.local` được tạo ngẫu nhiên hoặc có tính duy nhất. Đây là một kỹ thuật che địa chỉ cục bộ, được mô tả trong tài liệu IETF về mDNS ICE candidates.

Không nên dựa vào mDNS để ẩn public IP. Server-reflexive candidate vẫn có thể tiết lộ public mapped address nếu policy cho phép.

## 11. Thiết kế quyền riêng tư theo threat model

Trước khi chọn policy, trả lời ba câu hỏi:

1. Cần ẩn IP khỏi ai?
2. Có chấp nhận giảm chất lượng hoặc tăng chi phí không?
3. Có cần direct peer-to-peer để đạt latency và bandwidth mục tiêu không?

### 11.1 Mức bảo vệ tham khảo

| Mục tiêu | Biện pháp |
|---|---|
| Giảm lộ private IP cho website JavaScript | Dựa vào browser IP handling/mDNS; dùng relay-only nếu cần giới hạn candidate |
| Giảm lộ IP trực tiếp cho remote peer | `iceTransportPolicy: "relay"` và TURN |
| Không gửi candidate trước khi user chấp nhận | Trì hoãn ICE negotiation/gathering và signaling |
| Giảm signaling server lưu địa chỉ | Relay-only, không log SDP/candidate, retention ngắn |
| Giảm dữ liệu TURN provider giữ | Chọn provider, giới hạn log và retention |
| Giảm lộ IP qua HTTP | VPN/proxy hoặc kiến trúc mạng phù hợp; relay-only không giải quyết phần này |
| Hạn chế fingerprinting | Giảm candidate, không thu thập hoặc lưu IP, giới hạn telemetry |

### 11.2 Cuộc gọi với người lạ

Một chính sách hợp lý là:

- Không tạo ICE gathering trước khi người dùng chấp nhận.
- Dùng relay-only cho peer chưa đáng tin.
- Cấp TURN credential ngắn hạn.
- Chỉ chia sẻ candidate relay qua signaling.
- Chuyển sang direct candidate sau khi người dùng được thông báo và chấp thuận, nếu sản phẩm cho phép.
- Đóng PeerConnection và xóa signaling data khi cuộc gọi kết thúc.

### 11.3 Cuộc gọi nội bộ hoặc mạng doanh nghiệp

Mạng doanh nghiệp có thể cần direct host candidates để kết nối LAN nhanh và giảm chi phí TURN. Khi đó:

- Đánh giá mDNS và browser policy.
- Không log private IP không cần thiết.
- Cấu hình TURN enterprise nếu cần.
- Xác định rõ peer nào được tin cậy.
- Đánh giá rủi ro fingerprinting giữa các browsing context.

Không bật relay-only mặc định cho mọi môi trường nếu sản phẩm cần kết nối LAN trực tiếp và đã có kiểm soát quyền riêng tư phù hợp.

## 12. Ví dụ quan sát candidate mà không log IP

Khi debug, có thể quan sát loại candidate và transport mà không ghi địa chỉ thực:

~~~js
async function inspectIceCandidates() {
  const pc = new RTCPeerConnection({
    iceServers: [
      { urls: "stun:stun.example.test:3478" }
    ]
  });

  // Data channel tạo một application m-line để bắt đầu ICE.
  pc.createDataChannel("privacy-check");

  pc.onicecandidate = event => {
    if (!event.candidate) {
      console.log("ICE gathering complete");
      return;
    }

    const candidate = event.candidate;

    console.table({
      type: candidate.type,
      protocol: candidate.protocol,
      address: candidate.address ? "[redacted]" : null,
      port: candidate.port,
      relatedAddress: candidate.relatedAddress ? "[redacted]" : null
    });
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  return pc;
}

inspectIceCandidates();
~~~

Không ghi `candidate.candidate` hoặc toàn bộ SDP vào log vì chuỗi đó có thể chứa địa chỉ và thông tin phiên.

Ví dụ relay-only:

~~~js
const pc = new RTCPeerConnection({
  iceServers: [
    {
      urls: "turns:turn.example.test:5349?transport=tcp",
      username: "ephemeral-user",
      credential: "ephemeral-password"
    }
  ],
  iceTransportPolicy: "relay"
});
~~~

Credential trong ví dụ là placeholder. Trong production, backend nên cấp TURN credential có thời hạn ngắn và giới hạn theo user/session.

## 13. Kiểm thử IP privacy

Chỉ kiểm thử trên thiết bị, browser profile và signaling/TURN server do bạn kiểm soát. Không đưa IP thật vào ticket, screenshot công khai hoặc báo cáo.

### 13.1 Quan sát candidate types

1. Tạo một `RTCPeerConnection` trong trang lab.
2. Đăng ký `onicecandidate`.
3. Ghi lại `candidate.type`, `protocol` và số lượng candidate.
4. Redact `address`, `relatedAddress` và raw candidate string.
5. Lặp lại với mạng Wi-Fi, Ethernet, VPN và IPv6 nếu có.

Mục tiêu là hiểu loại candidate và thay đổi policy, không thu thập địa chỉ cá nhân.

### 13.2 So sánh mDNS

- Dùng browser có mDNS host candidate.
- Quan sát host candidate đã redact.
- Kiểm tra xem candidate có `.local` hay không.
- Không cố resolve hoặc công bố IP private thật.
- So sánh hành vi giữa các browser và môi trường mạng.

Không coi việc thấy `.local` là bằng chứng mọi IP đã được che.

### 13.3 So sánh `all` và `relay`

Tạo hai PeerConnection:

~~~js
async function comparePolicies() {
  const directPC = new RTCPeerConnection({
    iceServers: [
      { urls: "stun:stun.example.test:3478" }
    ],
    iceTransportPolicy: "all"
  });

  const relayPC = new RTCPeerConnection({
    iceServers: [
      {
        urls: "turn:turn.example.test:3478?transport=udp",
        username: "ephemeral-user",
        credential: "ephemeral-password"
      }
    ],
    iceTransportPolicy: "relay"
  });

  directPC.createDataChannel("direct-probe");
  relayPC.createDataChannel("relay-probe");

  const directOffer = await directPC.createOffer();
  await directPC.setLocalDescription(directOffer);

  const relayOffer = await relayPC.createOffer();
  await relayPC.setLocalDescription(relayOffer);

  return { directPC, relayPC };
}

comparePolicies();
~~~

So sánh:

- Số lượng và loại candidate.
- Candidate nào được chuyển qua signaling.
- Kết nối có thành công không.
- RTT và packet loss.
- Media có bị gián đoạn khi TURN không reachable không.

Không log địa chỉ thật. Chỉ cần type, transport, kết quả và metric hiệu năng đã loại thông tin định danh.

### 13.4 Kiểm thử split tunnel

Nếu có môi trường lab VPN:

1. Xác nhận HTTP đi theo route dự kiến bằng hệ thống kiểm thử của tổ chức.
2. Chạy WebRTC candidate gathering.
3. So sánh loại candidate và route mà TURN/STUN server quan sát.
4. Kiểm tra IPv4 và IPv6.
5. Thử VPN full-tunnel và split-tunnel.
6. Xác nhận không có candidate ngoài policy mong muốn.

Không dùng một website “WebRTC leak test” bất kỳ làm bằng chứng duy nhất. Công cụ đó có thể thu thập địa chỉ và candidate của bạn. Ưu tiên lab tự quản lý hoặc dịch vụ kiểm thử đã được phê duyệt.

### 13.5 Kiểm tra signaling và logging

- Xác nhận signaling server không ghi raw SDP/candidate.
- Kiểm tra log reverse proxy không chứa payload signaling.
- Kiểm tra analytics không nhận IP hoặc candidate string.
- Xác nhận TURN credential không bị log.
- Xóa signaling session sau khi cuộc gọi kết thúc.

## 14. Những nhầm lẫn thường gặp

### 14.1 Nghĩ HTTPS ngăn WebRTC lộ IP

HTTPS bảo vệ request đến web server trên đường truyền. Nó không ngăn ICE thu thập candidate để thiết lập peer connection.

### 14.2 Nghĩ mDNS che mọi địa chỉ

mDNS chủ yếu che host/private address trong candidate. Server-reflexive candidate vẫn có thể tiết lộ public mapped IP.

### 14.3 Nghĩ VPN luôn định tuyến WebRTC

VPN có thể split tunnel hoặc không route UDP/IPv6 như HTTP. Cần kiểm thử đường ICE thực tế.

### 14.4 Nghĩ STUN là relay

STUN giúp khám phá mapped address. TURN mới chuyển tiếp media qua relay.

### 14.5 Nghĩ relay-only ẩn IP khỏi mọi bên

Relay-only giảm việc peer biết địa chỉ trực tiếp. TURN provider vẫn thấy địa chỉ nguồn và HTTP server vẫn thấy public IP của request.

### 14.6 Nghĩ chỉ lọc candidate khi signaling là đủ

Candidate vẫn được JavaScript của trang nhìn thấy trước khi lọc. Dùng relay-only nếu muốn ICE agent không sử dụng/expose candidate non-relay theo policy.

### 14.7 Nghĩ camera permission là điều kiện để lộ IP

ICE có thể chạy với data channel hoặc kết nối chỉ nhận media. Không giả định người dùng chưa cấp quyền camera thì IP không thể được thu thập.

### 14.8 Nghĩ mọi candidate phải được gửi đến peer

Ứng dụng kiểm soát signaling. Peer chỉ nhận candidate được ứng dụng trao đổi, nhưng JavaScript của website có thể đã quan sát candidate từ browser API.

### 14.9 Nghĩ candidate IP chỉ là dữ liệu kỹ thuật

Candidate có thể tiết lộ mạng nội bộ, ISP, vị trí gần đúng hoặc tạo fingerprint. Coi nó là dữ liệu nhạy cảm.

### 14.10 Nghĩ tắt WebRTC là giải pháp duy nhất

Có thể giữ WebRTC và dùng mDNS, relay-only, trì hoãn ICE, signaling retention ngắn và TURN đáng tin cậy để cân bằng privacy với trải nghiệm.

## 15. Checklist review IP privacy

- [ ] Đã xác định cần bảo vệ IP khỏi website, signaling server, peer hay TURN provider.
- [ ] Hiểu host, srflx, prflx và relay candidate.
- [ ] Không log raw SDP, candidate string hoặc IP address không cần thiết.
- [ ] Đã đánh giá mDNS host candidate trên browser mục tiêu.
- [ ] Không coi mDNS là biện pháp che public IP.
- [ ] Dùng `iceTransportPolicy: "relay"` khi cần che IP trực tiếp khỏi peer.
- [ ] TURN server có UDP và TCP/TLS phù hợp mạng người dùng.
- [ ] TURN credential ngắn hạn và không nhúng secret cố định trong bundle.
- [ ] Đã đánh giá RTT, packet loss, băng thông và chi phí relay.
- [ ] Trì hoãn ICE gathering cho cuộc gọi từ peer chưa đáng tin.
- [ ] Không gửi SDP/candidate trước khi người dùng chấp nhận nếu sản phẩm yêu cầu.
- [ ] Candidate filtering không được xem là thay thế relay-only.
- [ ] Đã đánh giá VPN, split tunnel, proxy và IPv6.
- [ ] Signaling server có retention policy cho SDP/candidate.
- [ ] TURN provider có chính sách log và retention rõ ràng.
- [ ] Không coi IP privacy là authentication hoặc authorization.
- [ ] Có fallback khi TURN không khả dụng.
- [ ] Kiểm thử bằng môi trường lab, redact địa chỉ và không công khai IP thật.
- [ ] Đã kiểm tra cả browser và native peer nếu sản phẩm hỗ trợ cả hai.

## 16. Bài thực hành

Thực hiện với browser, signaling và TURN server lab do bạn kiểm soát. Dùng dữ liệu giả lập và không đưa địa chỉ IP thật vào tài liệu công khai.

### Bài 1: Phân loại ICE candidates

Tạo PeerConnection với STUN server lab. Quan sát candidate type mà không ghi địa chỉ. Giải thích host, srflx, prflx và relay khác nhau thế nào.

### Bài 2: Quan sát mDNS host candidate

Dùng browser hỗ trợ mDNS. Kiểm tra host candidate đã redact và xác định liệu nó chứa IP trực tiếp hay `.local` hostname. Ghi nhận khác biệt giữa browser versions.

### Bài 3: So sánh all và relay

Tạo hai PeerConnection với `iceTransportPolicy` lần lượt là `all` và `relay`. So sánh candidate type, kết nối thành công, RTT và đường media.

### Bài 4: TURN-only và lỗi relay

Tắt TURN server lab hoặc chặn transport. Quan sát relay-only không còn candidate usable và kết nối thất bại. Khôi phục TURN và xác nhận kết nối lại.

### Bài 5: Trì hoãn ICE đến khi Accept

Xây dựng màn hình incoming call. Chỉ tạo PeerConnection và bắt đầu offer/answer sau khi người dùng bấm Accept. Kiểm tra signaling không nhận candidate trước đó.

### Bài 6: Kiểm tra split tunnel

Trong VPN lab, so sánh HTTP route và STUN/TURN route trên IPv4/IPv6. Xác định có interface ngoài VPN nào tham gia candidate gathering không.

### Bài 7: Redact signaling logs

Gửi SDP và ICE candidates qua signaling lab. Cấu hình log chỉ lưu session ID, candidate type và trạng thái kết nối; không lưu địa chỉ hoặc raw SDP. Xác nhận retention cleanup.

### Bài 8: Kiểm tra dữ liệu sau cuộc gọi

Kết thúc cuộc gọi, đóng PeerConnection, xóa signaling state và kiểm tra không còn candidate/IP trong application logs hoặc analytics.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao WebRTC có thể tiết lộ IP mà HTTP không tiết lộ cho JavaScript?**

ICE cần thu thập nhiều địa chỉ để tìm đường peer-to-peer và đưa candidate cho ứng dụng, trong khi HTTP thông thường chỉ cho web server thấy địa chỉ nguồn của request.

**2. Host candidate đại diện cho điều gì?**

Địa chỉ interface cục bộ của peer; browser có thể che IP private bằng mDNS hostname.

**3. Server-reflexive candidate được tạo như thế nào?**

STUN server quan sát mapped address của packet đi qua NAT và trả thông tin để ICE tạo candidate.

**4. TURN relay candidate giúp gì cho IP privacy?**

Peer dùng địa chỉ relay của TURN server thay vì địa chỉ trực tiếp của người dùng.

**5. mDNS có che public IP không?**

Không. Nó chủ yếu che private host address; srflx candidate vẫn có thể tiết lộ public mapped address.

**6. `iceTransportPolicy: "relay"` có tác dụng gì?**

Giới hạn ICE vào relay candidates, giảm việc peer nhận địa chỉ IP trực tiếp của người dùng.

**7. Relay-only có ẩn IP khỏi TURN server không?**

Không. TURN server vẫn thấy địa chỉ nguồn của client đang kết nối đến relay.

**8. Vì sao VPN có thể không đủ?**

Split tunnel hoặc routing khác nhau có thể khiến WebRTC/STUN đi qua interface ngoài VPN, trong khi HTTP đi qua VPN.

**9. Vì sao cần trì hoãn ICE cho cuộc gọi từ người lạ?**

Để tránh thu thập và gửi candidate trước khi người dùng chấp nhận, giảm việc peer biết IP hoặc trạng thái online quá sớm.

**10. Vì sao không nên log raw SDP/candidate?**

Chúng có thể chứa địa chỉ IP, ICE credentials hoặc metadata phiên, tạo rủi ro riêng tư và fingerprinting.

## Ghi nhớ

WebRTC cần ICE candidates để tìm đường kết nối, nhưng các candidate có thể tiết lộ địa chỉ private, public và cấu trúc mạng. mDNS giúp che host IP cục bộ trong một số browser; `iceTransportPolicy: "relay"` dùng TURN để giảm việc peer nhìn thấy IP trực tiếp. Hãy xác định rõ bên cần bảo vệ, trì hoãn ICE đến khi người dùng chấp nhận, bảo vệ signaling và TURN logs, kiểm thử VPN/IPv6 và không coi một biện pháp đơn lẻ là ẩn danh tuyệt đối.

## Tài liệu tham khảo

- [RFC 8828: WebRTC IP Address Handling Requirements](https://www.rfc-editor.org/rfc/rfc8828.html)
- [RFC 8827: WebRTC Security Architecture](https://www.rfc-editor.org/rfc/rfc8827.html)
- [RFC 8445: Interactive Connectivity Establishment (ICE)](https://www.rfc-editor.org/rfc/rfc8445.html)
- [RFC 8489: Session Traversal Utilities for NAT (STUN)](https://www.rfc-editor.org/rfc/rfc8489.html)
- [RFC 8656: Traversal Using Relays around NAT (TURN)](https://www.rfc-editor.org/rfc/rfc8656.html)
- [W3C: WebRTC 1.0](https://www.w3.org/TR/webrtc/)
- [MDN: WebRTC connectivity](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Connectivity)
- [MDN: RTCPeerConnection configuration and iceTransportPolicy](https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/RTCPeerConnection)
- [IETF: Using Multicast DNS to protect privacy when exposing ICE candidates](https://datatracker.ietf.org/doc/draft-ietf-mmusic-mdns-ice-candidates/)
