# Connection state: trạng thái kết nối trong TCP/IP

> **Chương:** TCP IP  
> **Học phần:** SECURITY_NETWORK_SECURITY — An ninh mạng  
> **Chủ đề:** Vòng đời kết nối TCP, máy trạng thái của hai đầu kết nối, theo dõi trạng thái tại firewall/NAT và ứng dụng trong giám sát, phân tích lưu lượng, phòng vệ mạng.

Một yêu cầu HTTPS có thể thất bại dù máy khách phân giải DNS đúng và router có đường tới máy chủ. Nguyên nhân có thể là quá trình bắt tay TCP chưa hoàn tất, kết nối đã bị đóng, bảng trạng thái của firewall hết chỗ, hoặc ứng dụng giữ những socket đáng lẽ phải giải phóng. Để xác định đúng điểm lỗi, cần hiểu **connection state**: trạng thái mà mỗi thành phần duy trì về một kết nối trong từng giai đoạn.

Trong học phần **SECURITY_NETWORK_SECURITY**, khái niệm này liên kết trực tiếp với firewall có trạng thái (*stateful firewall*), NAT, VPN, IDS/IPS, phân đoạn mạng, giám sát xâm nhập và kiến trúc cloud. Điểm quan trọng là **TCP endpoint**, **thiết bị theo dõi luồng mạng** và **ứng dụng** có thể nhìn cùng một kết nối qua những hệ trạng thái khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích TCP duy trì trạng thái để truyền dữ liệu tin cậy như thế nào và nhận biết một kết nối qua địa chỉ, cổng, giao thức.
2. Mô tả **three-way handshake**, quá trình đóng bằng **FIN/ACK**, vai trò **RST** và ý nghĩa của các trạng thái TCP chính.
3. Phân biệt **CLOSED, LISTEN, SYN-SENT, SYN-RECEIVED, ESTABLISHED, FIN-WAIT-1, FIN-WAIT-2, CLOSE-WAIT, CLOSING, LAST-ACK, TIME-WAIT**.
4. Phân biệt máy trạng thái TCP của host với các trạng thái **NEW, ESTABLISHED, RELATED, INVALID** của hệ thống connection tracking.
5. Phân tích các tình huống bảo mật như SYN flood, cạn kiệt bảng trạng thái, giả mạo RST, timeout và đường về bất đối xứng.
6. Dùng công cụ quan sát ở mức cơ bản để khoanh vùng sự cố kết nối trước khi điều chỉnh cấu hình.

## 2. Một kết nối TCP được nhận diện như thế nào?

TCP (*Transmission Control Protocol*) là giao thức hướng kết nối ở tầng vận chuyển. Trước khi trao đổi dữ liệu thông thường, hai đầu thiết lập trạng thái thông qua quá trình bắt tay. Trong quá trình truyền, mỗi đầu duy trì thông tin như số thứ tự (*sequence number*), số xác nhận (*acknowledgment number*), cửa sổ nhận, bộ đệm, bộ hẹn giờ và trạng thái đóng/mở.

Một kết nối giữa hai endpoint thường được phân biệt bằng **bộ bốn giá trị**:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| IP nguồn | 10.10.10.25 | Địa chỉ của máy khách |
| Cổng nguồn | 51514 | Cổng tạm thời (*ephemeral port*) phía máy khách |
| IP đích | 10.20.30.50 | Địa chỉ máy chủ API |
| Cổng đích | 443 | Cổng dịch vụ HTTPS |

Kèm **giao thức TCP**, nhiều hệ thống mạng gọi mô tả luồng này là **5-tuple**: IP nguồn, cổng nguồn, IP đích, cổng đích và protocol. Chiều phản hồi sử dụng cặp nguồn/đích đảo lại. Các cơ chế NAT có thể thay đổi một hoặc nhiều giá trị giữa các đoạn mạng nhưng vẫn phải duy trì ánh xạ phù hợp để phản hồi quay về đúng luồng.

**Đừng nhầm kết nối với yêu cầu ứng dụng.** Một kết nối TCP có thể mang nhiều HTTP request khi dùng HTTP keep-alive; HTTP/2 còn ghép nhiều stream vào cùng một kết nối. Ngược lại, một phiên làm việc của người dùng có thể trải qua nhiều kết nối TCP. Trạng thái **ESTABLISHED** chỉ mô tả kết nối TCP ở một đầu, không chứng minh người dùng đã đăng nhập hay API đã phân quyền thành công.

### 2.1. Trạng thái được lưu ở đâu?

Mỗi bên giữ trạng thái của chính mình:

- **Máy khách:** hệ điều hành ghi nhận socket đang gửi SYN, đã thiết lập, đang chờ FIN hay đã đóng.
- **Máy chủ:** một socket lắng nghe ở trạng thái LISTEN; mỗi kết nối được chấp nhận có trạng thái riêng. Tùy hệ điều hành và cách triển khai, trạng thái chờ bắt tay có thể được quản lý bằng cấu trúc riêng.
- **Firewall/NAT:** có thể giữ entry theo dõi luồng, timeout, hướng lưu lượng và thông tin dịch địa chỉ. Đây là **trạng thái của thiết bị trung gian**, không phải bản sao chính xác máy trạng thái TCP của một endpoint.
- **Ứng dụng:** giữ trạng thái phiên đăng nhập, giao dịch, TLS hoặc HTTP độc lập với trạng thái TCP.

Không có một “trạng thái duy nhất của toàn mạng” được mọi thiết bị cùng cập nhật tức thời. Các góc nhìn có thể khác nhau trong lúc mất gói, thay đổi tuyến, timeout hoặc khi thiết bị trung gian không quan sát được đủ hai chiều.

## 3. Thiết lập kết nối: TCP three-way handshake

Giả sử máy khách **10.10.10.25:51514** muốn kết nối đến **10.20.30.50:443**. Cổng 443 thường được sử dụng cho HTTPS, nhưng đây vẫn là quá trình bắt tay TCP trước khi các bên trao đổi thông điệp TLS trên kết nối đó.

~~~mermaid
sequenceDiagram
    participant C as Client 10.10.10.25:51514
    participant S as Server 10.20.30.50:443
    Note over C: CLOSED → SYN-SENT
    Note over S: LISTEN
    C->>S: SYN, Seq=x
    Note over S: SYN-RECEIVED
    S-->>C: SYN + ACK, Seq=y, Ack=x+1
    Note over C: ESTABLISHED
    C->>S: ACK, Ack=y+1
    Note over S: ESTABLISHED
    C->>S: Dữ liệu ứng dụng sau khi thiết lập
~~~

### Bước 1 — Client gửi SYN

Ứng dụng gọi thao tác kết nối (ví dụ hàm `connect()` trên một socket). TCP client chọn số thứ tự khởi đầu (*Initial Sequence Number — ISN*) và gửi gói có cờ **SYN**. Trạng thái phía client chuyển từ **CLOSED** sang **SYN-SENT**.

Máy chủ thường có socket ở trạng thái **LISTEN** để chấp nhận kết nối mới. Khi nhận SYN hợp lệ, máy chủ có thể cấp phát hoặc ghi nhận thông tin chờ bắt tay, chọn ISN của mình và gửi phản hồi. Việc lưu trữ cụ thể phụ thuộc hệ điều hành, cấu hình backlog và cơ chế chống SYN flood.

### Bước 2 — Server trả SYN + ACK

Máy chủ gửi **SYN, ACK**: vừa yêu cầu đồng bộ số thứ tự của nó, vừa xác nhận SYN của client. Trạng thái bên máy chủ đi tới **SYN-RECEIVED** (có thể hiển thị là `SYN-RECV` trong công cụ của một số hệ điều hành).

Trong ví dụ đơn giản, SYN chiếm một vị trí trong không gian số thứ tự TCP nên ACK của server xác nhận `x + 1`. SYN của server cũng cần được client xác nhận.

### Bước 3 — Client gửi ACK

Khi nhận SYN + ACK hợp lệ, client gửi ACK xác nhận `y + 1` và chuyển sang **ESTABLISHED**. Sau khi server nhận ACK hợp lệ này, phía server cũng chuyển sang **ESTABLISHED**.

**Trạng thái ở hai phía không thay đổi đồng thời.** Client có thể đã ở ESTABLISHED trong lúc ACK cuối vẫn đang trên đường tới server. Mất gói hoặc truyền lại có thể làm các trạng thái tạm thời khác nhau.

### 3.1. Bắt tay xác nhận điều gì?

Three-way handshake giúp hai đầu đồng bộ số thứ tự ban đầu và xác nhận khả năng trao đổi các gói điều khiển cần thiết qua đường mạng. TCP còn có thể thương lượng một số tùy chọn như **MSS**, **window scaling** và **SACK permitted** trong SYN/SYN+ACK khi được hỗ trợ.

Quá trình này **không tự xác thực danh tính người dùng**, **không mã hóa dữ liệu** và **không xác minh quyền gọi API**. Với HTTPS, bắt tay TLS diễn ra sau khi kết nối TCP được hình thành (bỏ qua các cơ chế mở rộng tối ưu hóa đặc thù); TLS xác thực điểm cuối và thiết lập bảo vệ mật mã, còn ứng dụng tiếp tục áp dụng xác thực và phân quyền nghiệp vụ.

### 3.2. Điều gì xảy ra nếu gói bắt tay bị mất?

- **SYN không đến server:** client có thể truyền lại SYN theo cơ chế timeout; kết nối cuối cùng có thể thất bại.
- **SYN + ACK bị mất:** server có thể truyền lại SYN + ACK khi còn trạng thái chờ; client chưa nhận phản hồi nên chưa hoàn tất bắt tay.
- **ACK cuối bị mất:** hai phía có thể tạm thời ở trạng thái khác nhau. Server có thể gửi lại SYN + ACK; client xác nhận lại theo quy tắc TCP.
- **Firewall chặn một chiều:** một phía liên tục chờ phản hồi; chỉ nhìn capture tại client dễ nhầm với server bị hỏng.

Số lần truyền lại và bộ hẹn giờ là chi tiết của TCP stack và cấu hình; không có một timeout cố định áp dụng cho mọi hệ điều hành hoặc mạng.

## 4. Các trạng thái của máy trạng thái TCP

Đặc tả TCP hiện đại mô tả **11 trạng thái điển hình**. Chúng phản ánh tiến trình kết nối của **một endpoint**, vì vậy trong cùng thời điểm client và server có thể ở hai trạng thái khác nhau.

| Trạng thái | Ý nghĩa thực tế | Thường thấy khi |
|---|---|---|
| **CLOSED** | Không có trạng thái kết nối đang tồn tại tại endpoint | Chưa kết nối hoặc đã giải phóng kết nối |
| **LISTEN** | Socket phía server chờ yêu cầu kết nối đến | Dịch vụ mở cổng để chấp nhận kết nối |
| **SYN-SENT** | Đã gửi SYN, đang chờ phản hồi phù hợp | Client bắt đầu `connect()` |
| **SYN-RECEIVED** | Đã nhận SYN và gửi SYN + ACK, đang chờ hoàn tất bắt tay | Server đang xử lý yêu cầu mở kết nối; cũng có thể xuất hiện khi mở đồng thời |
| **ESTABLISHED** | Kết nối TCP đã thiết lập, có thể truyền và xác nhận dữ liệu | Trao đổi ứng dụng bình thường |
| **FIN-WAIT-1** | Đã gửi FIN để đóng chiều gửi, đang chờ ACK cho FIN và/hoặc FIN từ bên kia | Endpoint chủ động đóng |
| **FIN-WAIT-2** | FIN của mình đã được xác nhận, đang chờ phía kia gửi FIN | Một bên đã đóng chiều gửi |
| **CLOSE-WAIT** | Đã nhận FIN từ peer và xác nhận; ứng dụng cục bộ chưa đóng chiều gửi | Peer chủ động đóng, ứng dụng local còn phải xử lý/đóng |
| **CLOSING** | Hai bên gần như đồng thời gửi FIN, đang chờ ACK cho FIN của mình | Đóng đồng thời |
| **LAST-ACK** | Đã gửi FIN sau khi nhận FIN từ peer, đang chờ ACK cuối | Endpoint phản ứng với yêu cầu đóng của bên kia |
| **TIME-WAIT** | Đã hoàn tất một đường đóng bình thường và giữ trạng thái trong khoảng an toàn | Bên gửi ACK cuối theo trình tự đóng chủ động điển hình |

Tên hiển thị có thể khác: `SYN-RECV` thay cho SYN-RECEIVED, `FIN-WAIT-1` hoặc `FIN-WAIT1`, `TIME-WAIT` hay `TIME_WAIT`. Khi đọc công cụ, cần biết hệ điều hành và nguồn dữ liệu đang hiển thị.

### 4.1. Sơ đồ chuyển trạng thái rút gọn

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> LISTEN: Passive open
    CLOSED --> SYN_SENT: Active open / send SYN
    LISTEN --> SYN_RCVD: Receive SYN / send SYN+ACK
    SYN_SENT --> ESTABLISHED: Receive SYN+ACK / send ACK
    SYN_RCVD --> ESTABLISHED: Receive final ACK
    ESTABLISHED --> FIN_WAIT_1: Local close / send FIN
    ESTABLISHED --> CLOSE_WAIT: Receive FIN / send ACK
    FIN_WAIT_1 --> FIN_WAIT_2: Receive ACK of FIN
    FIN_WAIT_1 --> CLOSING: Receive FIN before ACK of own FIN
    FIN_WAIT_1 --> TIME_WAIT: Receive FIN+ACK completing close
    FIN_WAIT_2 --> TIME_WAIT: Receive FIN / send ACK
    CLOSING --> TIME_WAIT: Receive ACK of own FIN
    CLOSE_WAIT --> LAST_ACK: Local close / send FIN
    LAST_ACK --> CLOSED: Receive ACK of own FIN
    TIME_WAIT --> CLOSED: TIME-WAIT timer expires
~~~

Sơ đồ tập trung vào các nhánh thường gặp, chưa vẽ tất cả trường hợp như **simultaneous open**, hủy bắt tay, retransmission, RST, lỗi hệ thống hoặc các thay đổi do timeout. Trong thực tế, xử lý một gói tin còn phải thỏa điều kiện sequence/ACK và các quy tắc kiểm tra TCP.

### 4.2. Những điểm dễ nhầm

**LISTEN không phải ESTABLISHED.** Một ứng dụng có thể đang lắng nghe cổng 443 trong khi chưa có client nào kết nối. Socket LISTEN và các socket kết nối cụ thể là các đối tượng khác nhau.

**SYN-RECEIVED không đồng nghĩa bị tấn công.** Đây là giai đoạn hợp lệ trong bắt tay; điều đáng chú ý là số lượng/trạng thái kéo dài bất thường so với lưu lượng bình thường và khả năng của máy chủ.

**CLOSE-WAIT khác TIME-WAIT.** CLOSE-WAIT thường cho biết ứng dụng cục bộ đã nhận yêu cầu đóng nhưng vẫn chưa đóng socket theo luồng ứng dụng. TIME-WAIT là trạng thái quản lý an toàn sau một trình tự đóng bình thường, không mặc định là dấu hiệu rò rỉ.

**ESTABLISHED không chứng minh kết nối đang hữu dụng.** Peer có thể đã mất điện hoặc đường mạng bị cắt mà phía local chưa nhận được sự kiện hay chưa có lần truyền/timeout để phát hiện.

## 5. Đóng kết nối: FIN, ACK, RST và TIME-WAIT

TCP là luồng dữ liệu **song công** (*full-duplex*): mỗi hướng gửi có thể được đóng độc lập. Một bên gửi **FIN** để báo rằng nó sẽ không gửi thêm dữ liệu theo hướng đó; bên kia vẫn có thể gửi dữ liệu cho đến khi nó cũng đóng chiều gửi của mình.

### 5.1. Đóng bình thường theo hai hướng

Giả sử client chủ động đóng trước, server đóng sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    Note over C,S: Trước đó cả hai ESTABLISHED
    C->>S: FIN
    Note over C: FIN-WAIT-1
    S-->>C: ACK của FIN
    Note over S: CLOSE-WAIT
    Note over C: FIN-WAIT-2
    Note over S: Ứng dụng xử lý phần còn lại rồi đóng
    S-->>C: FIN
    Note over S: LAST-ACK
    C->>S: ACK của FIN
    Note over C: TIME-WAIT
    Note over S: CLOSED
    Note over C: Chờ hết thời gian an toàn rồi CLOSED
~~~

Đây thường được mô tả bằng **bốn thông điệp**, nhưng thực tế ACK và FIN có thể được gộp trong cùng một segment nếu phù hợp. Số segment trên mạng không phải lúc nào cũng là bốn.

### 5.2. Vì sao cần TIME-WAIT?

TIME-WAIT giúp xử lý những segment trễ của kết nối cũ và cho phép gửi lại ACK cuối nếu peer gửi lại FIN vì chưa nhận được ACK. Trong mô hình TCP cổ điển, thời gian chờ liên quan đến **2 × MSL** (*Maximum Segment Lifetime*) — khoảng được dùng để giới hạn tuổi thọ tối đa của segment trong mạng.

Độ dài TIME-WAIT và cách quản lý entry là **phụ thuộc TCP stack/hệ điều hành**. Không nên lấy một con số quan sát ở hệ thống A để mặc định áp dụng cho tất cả thiết bị. Cũng không nên tùy tiện rút ngắn hoặc vô hiệu hóa cơ chế này chỉ để giảm số dòng `TIME-WAIT`; thay đổi đó có thể ảnh hưởng an toàn khi tái sử dụng kết nối.

TIME-WAIT thường xuất hiện ở phía hoàn tất nhánh đóng chủ động và gửi ACK cuối. Nếu hai bên cùng đóng gần như đồng thời, luồng chuyển trạng thái sẽ khác và cả hai bên có thể có TIME-WAIT.

### 5.3. RST khác FIN

**RST** (*Reset*) được dùng để từ chối hoặc chấm dứt kết nối theo cách đặt lại trạng thái thay vì hoàn tất trình tự đóng có thứ tự bằng FIN. Ví dụ, kết nối đến cổng không có tiến trình lắng nghe có thể nhận RST từ máy đích, nếu hệ thống không lọc gói theo một chính sách khác.

RST hợp lệ phải được xử lý theo các quy tắc kiểm tra TCP, đặc biệt là tính phù hợp của thông tin sequence với trạng thái kết nối. Việc nhìn thấy gói có cờ RST trong capture **chưa đủ** để chứng minh endpoint đã chấp nhận reset.

| Đặc điểm | Đóng bằng FIN | Đóng bằng RST |
|---|---|---|
| Ý định | Kết thúc có trật tự một hướng truyền và phối hợp đóng hai chiều | Đặt lại hoặc từ chối kết nối |
| Dữ liệu đang đợi | Thiết kế cho phép kết thúc luồng và xử lý dữ liệu theo cơ chế TCP | Dữ liệu chưa được xử lý có thể bị mất/không được ứng dụng nhận |
| Dấu hiệu | FIN, ACK; các trạng thái FIN-WAIT, CLOSE-WAIT, LAST-ACK, TIME-WAIT | RST; kết nối có thể bị hủy nếu reset được chấp nhận |
| Khi điều tra | Kiểm tra ai đóng trước, ứng dụng local có hoàn tất đóng không | Kiểm tra bên gửi, sequence hợp lệ, policy của firewall/load balancer và log ứng dụng |

### 5.4. Half-close và “half-open” không giống nhau

**Half-close** là trạng thái hợp lệ khi một bên đã gửi FIN, ngừng truyền theo chiều của nó nhưng vẫn có thể nhận dữ liệu từ bên kia. Ví dụ: client gửi hết nội dung rồi thông báo kết thúc chiều gửi, server vẫn trả kết quả.

Thuật ngữ **half-open connection** có nhiều cách dùng trong tài liệu:

- Trong bảo mật/SYN flood, thường chỉ yêu cầu kết nối **chưa hoàn tất three-way handshake**, chẳng hạn server còn đợi ACK cuối.
- Trong mô tả lỗi TCP, đôi khi chỉ trường hợp một endpoint vẫn tin kết nối tồn tại trong khi peer đã mất trạng thái do crash/restart hoặc sự cố mạng.

Vì vậy khi báo cáo sự cố, hãy dùng tên trạng thái cụ thể như `SYN-RECEIVED`, `ESTABLISHED` hoặc `CLOSE-WAIT` cùng vị trí quan sát, tránh chỉ ghi “half-open” mà không giải thích.

## 6. Các bộ hẹn giờ và cơ chế duy trì trạng thái

TCP không chỉ chuyển trạng thái khi thấy cờ SYN/FIN/RST. Những bộ hẹn giờ và phản hồi cũng ảnh hưởng đến tính sẵn sàng của kết nối.

| Cơ chế | Vấn đề giải quyết | Quan sát có thể gặp |
|---|---|---|
| **Retransmission timeout (RTO)** | Gửi lại dữ liệu/segment cần thiết chưa được ACK | Lặp SYN hoặc retransmission, tăng độ trễ, có thể timeout |
| **Idle/application timeout** | Giới hạn thời gian không hoạt động theo chính sách dịch vụ hoặc proxy | Endpoint/proxy đóng kết nối khi không có hoạt động |
| **TCP keepalive** | Thử phát hiện peer không còn phản hồi trong một số kết nối không hoạt động | Gói probe sau khoảng nhàn rỗi; tùy hệ điều hành/cấu hình và có thể bị tắt |
| **TCP user timeout** | Giới hạn thời gian dữ liệu gửi mà chưa được xác nhận theo khả năng stack/API | Ứng dụng phát hiện kết nối không tiến triển dù socket từng ESTABLISHED |
| **FIN/close timeout** | Tránh giữ vô hạn một số trạng thái đóng hoặc mồ côi | Entry còn ở FIN-WAIT-2 hoặc trạng thái khác theo chính sách stack |
| **TIME-WAIT timer** | Giữ trạng thái sau khi đóng để xử lý segment trễ/retransmission | Nhiều entry TIME-WAIT trong dịch vụ nhiều kết nối ngắn |

Điều kiện và thời gian thực tế thay đổi theo hệ điều hành, phiên bản, tài nguyên và loại socket. **Không có keepalive không đồng nghĩa lỗi mạng được phát hiện ngay lập tức.** Một kết nối không gửi/nhận gì có thể trông như còn sống trong khi đường truyền đã đứt.

### 6.1. Tại sao cổng tạm thời có thể cạn?

Client thường dùng một cổng nguồn tạm thời khi kết nối tới server. Nếu ứng dụng tạo rất nhiều kết nối mới trong thời gian ngắn, giữ quá nhiều socket hoặc liên tục đóng/mở tới cùng tập đích, nó có thể gặp giới hạn cổng nguồn khả dụng, bộ đếm kết nối hoặc tài nguyên hệ điều hành.

Để cải thiện, cần tìm nguyên nhân: ứng dụng có mở kết nối trùng lặp không, có pool/keep-alive phù hợp không, server có đang phản hồi và đóng kết nối đúng không? TIME-WAIT là tín hiệu cần diễn giải trong **bối cảnh tổng lưu lượng và giới hạn tài nguyên**, không mặc định là thủ phạm.

## 7. Trạng thái TCP và trạng thái connection tracking của firewall

**Đây là hai khái niệm khác nhau.** Máy trạng thái TCP mô tả vòng đời socket ở endpoint. Stateful firewall hoặc NAT duy trì **bảng connection tracking** (*conntrack*) để ghi nhớ các luồng mà nó quan sát, từ đó áp dụng chính sách và xử lý lưu lượng phản hồi.

Trong hệ sinh thái Linux Netfilter, các nhãn trạng thái conntrack thường được dùng trong rule gồm:

| Trạng thái conntrack | Ý nghĩa theo ngữ cảnh theo dõi kết nối | Lưu ý |
|---|---|---|
| **NEW** | Gói được hệ thống phân loại như bắt đầu luồng/chưa thấy phản hồi cần thiết, theo giao thức và cấu hình | Không đồng nghĩa tuyệt đối với TCP `SYN-SENT` hoặc một gói SYN duy nhất |
| **ESTABLISHED** | Hệ thống theo dõi xác định luồng đã có hoạt động phù hợp theo cả hai chiều hoặc được xem là đã thiết lập theo cơ chế của nó | Không phải bằng chứng API đã xác thực người dùng; không luôn trùng thời điểm endpoint chuyển TCP ESTABLISHED |
| **RELATED** | Luồng mới có quan hệ được hệ thống xác định với luồng đã theo dõi, ví dụ một số thông điệp lỗi ICMP hoặc giao thức có helper | Không có nghĩa mọi kết nối giữa cùng hai IP tự động RELATED |
| **INVALID** | Gói không xác định được trạng thái hợp lệ theo logic theo dõi, hoặc không phù hợp ngữ cảnh đang có | Có thể do gói bất thường, thiếu trạng thái, timeout hoặc bất đối xứng; cần điều tra trước khi kết luận tấn công |
| **UNTRACKED** | Gói được cấu hình bỏ qua connection tracking ở một số hệ thống | Chỉ xuất hiện khi nền tảng/chính sách hỗ trợ và có sử dụng |

Một conntrack entry còn có thể có trạng thái *protocol-specific* như `SYN_SENT`, `SYN_RECV`, `ESTABLISHED`, `FIN_WAIT`, `TIME_WAIT` trong công cụ xem trạng thái. Chúng **không thay thế** các nhãn tổng quát dùng trong rule như `ct state established`, và không cần ánh xạ một-một với trạng thái socket của cả hai endpoint.

### 7.1. Stateful firewall cho phép lưu lượng chiều về ra sao?

Giả sử chính sách mong muốn là:

1. Máy khách trong mạng ứng dụng được phép **khởi tạo** TCP tới API:443.
2. Firewall tạo entry conntrack khi thấy luồng phù hợp và kiểm tra rule.
3. Khi phản hồi từ API quay lại, firewall nhận ra nó thuộc luồng đã theo dõi và có thể cho phép theo chính sách cho traffic hồi đáp.
4. Khi có FIN/RST hoặc timeout, entry được cập nhật/xóa theo cơ chế tracking của thiết bị.

Một mô tả **chính sách logic**:

~~~text
IF packet is part of tracked ESTABLISHED or permitted RELATED traffic
    THEN allow according to zone and policy
ELSE IF packet starts an allowed NEW flow
    THEN allow and track
ELSE
    THEN deny and record suitable counters
~~~

Đây không phải cấu hình firewall hoàn chỉnh. Quy tắc thực tế còn phụ thuộc **zone/interface, hướng, NAT, thứ tự rule, loại giao thức và chính sách egress/ingress**. Cần cân nhắc ICMP cần thiết cho hoạt động mạng (ví dụ thông báo phục vụ path MTU discovery) khi xây dựng chính sách.

**Sai lầm phổ biến:** vì đã có rule `ESTABLISHED,RELATED`, người quản trị cho rằng mọi phản hồi phải luôn được cho qua. Nếu bảng trạng thái bị xóa, thời gian chờ hết hạn, hoặc đường phản hồi đi qua thiết bị khác chưa thấy chiều khởi tạo, firewall có thể không nhận ra luồng và từ chối gói.

### 7.2. NAT cần trạng thái để chuyển phản hồi

Ví dụ máy nội bộ **10.10.10.25:51514** truy cập **203.0.113.20:443** qua cổng NAT có địa chỉ công cộng **198.51.100.5**. Thiết bị có thể tạo ánh xạ:

~~~text
Trước NAT: 10.10.10.25:51514   -> 203.0.113.20:443 (TCP)
Sau NAT:   198.51.100.5:62010 -> 203.0.113.20:443 (TCP)
Phản hồi:  203.0.113.20:443    -> 198.51.100.5:62010
                           NAT ánh xạ về 10.10.10.25:51514
~~~

Các IP công cộng trong ví dụ lấy từ dải dành cho tài liệu (**198.51.100.0/24**, **203.0.113.0/24**) và không đại diện endpoint thật. Cổng `62010` chỉ để minh họa: cổng NAT chọn có thể khác theo thuật toán và trạng thái đang dùng.

Khi entry hết hạn hoặc bị xóa do lỗi thiết bị/failover thiếu đồng bộ, phản hồi có thể không còn tìm được ánh xạ. Vì thế **timeout NAT, timeouts của load balancer và chính sách firewall** là thành phần quan trọng khi phân tích các kết nối “mất sau một lúc không hoạt động”.

### 7.3. Đường đi bất đối xứng

Nếu gói đi qua firewall A nhưng gói phản hồi đi qua firewall B, B có thể không biết trạng thái của luồng được A khởi tạo. Tùy thiết bị, kiến trúc đồng bộ session, chế độ kiểm tra và policy, phản hồi có thể bị chặn.

~~~mermaid
flowchart LR
    C["Client"]
    FWA["Firewall A<br/>Thấy SYN, tạo state"]
    S["Server"]
    FWB["Firewall B<br/>Không có entry tương ứng"]
    C -->|"SYN / request"| FWA --> S
    S -->|"SYN+ACK / response"| FWB
    FWB -. "Có thể DROP" .-> C
~~~

Giải pháp thiết kế có thể là giữ đường hai chiều nhất quán, đồng bộ trạng thái khi nền tảng hỗ trợ, điều chỉnh định tuyến hoặc áp dụng điểm kiểm soát có hiểu topology. **Không nên tắt stateful inspection chỉ để che một lỗi định tuyến** khi chưa đánh giá tác động bảo mật.

## 8. Connection state trong VPN, cloud và ứng dụng

### 8.1. VPN và các kết nối nằm trong tunnel

Trạng thái **tunnel VPN** và trạng thái **kết nối TCP bên trong VPN** khác nhau. IKE/IPsec hoặc giao thức VPN khác có trạng thái phiên/khóa/tunnel riêng; một tunnel báo “up” không chứng minh tất cả TCP flow bên trong đang hoạt động. Có thể đường VPN tồn tại nhưng firewall ở phía xa từ chối TCP/443, MTU gây lỗi hoặc dịch vụ đích không lắng nghe.

Một gói TCP nằm trong tunnel có thể chỉ được firewall ngoài tunnel nhìn thấy dưới dạng lưu lượng được mã hóa. Để quan sát TCP flags/trạng thái bên trong, sensor cần ở vị trí phù hợp sau giải mã hoặc nơi lưu lượng còn ở dạng rõ.

### 8.2. Cloud security group và load balancer

Một số nền tảng cloud cung cấp security group/stateful filtering: cho phép kết nối khởi tạo theo quy tắc, và luồng phản hồi có thể được xử lý dựa trên trạng thái nền tảng. Nhưng **khả năng theo dõi, quy tắc đặc biệt, thời gian chờ và hành vi khi thay đổi rule phụ thuộc nhà cung cấp và loại dịch vụ**.

Load balancer hoặc proxy có thể kết thúc TCP từ client rồi mở **một kết nối TCP khác** tới backend:

~~~mermaid
flowchart LR
    C["Client<br/>TCP connection A"]
    LB["Load balancer / reverse proxy<br/>Hai trạng thái socket độc lập"]
    APP["Backend API<br/>TCP connection B"]
    C <-->|"A: Client ↔ LB"| LB
    LB <-->|"B: LB ↔ Backend"| APP
~~~

Một kết nối client ESTABLISHED **không đảm bảo** kết nối backend ESTABLISHED. Khi xử lý sự cố, kiểm tra riêng timeout, RST, health check và log của từng leg, cũng như TLS có kết thúc ở proxy hay chuyển xuyên qua.

### 8.3. TCP không phải toàn bộ trạng thái của ứng dụng

| Lớp | Ví dụ trạng thái | Điều nó chứng minh |
|---|---|---|
| **TCP** | ESTABLISHED | Endpoint đã hoàn thành bắt tay TCP theo quan sát tại endpoint |
| **TLS** | Handshake thành công | Kênh TLS được thiết lập theo chính sách xác thực/mật mã đã áp dụng |
| **HTTP** | Request đang chờ, 200, 401, 403, 503 | Kết quả xử lý ở tầng giao thức/ứng dụng |
| **Danh tính** | Session/token hợp lệ hoặc hết hạn | Một số bằng chứng về chủ thể và phiên |
| **Nghiệp vụ** | Đơn hàng thuộc khách hàng hiện tại hay không | Quyền và điều kiện thao tác với dữ liệu cụ thể |

Ví dụ `ss` báo ESTABLISHED, nhưng client nhận **HTTP 403**: khả năng kết nối TCP thường đã đạt mục đích; cần xem xác thực/phân quyền, policy API hoặc WAF, thay vì chỉ điều chỉnh routing.

### 8.4. UDP và QUIC khác TCP như thế nào?

**UDP không có máy trạng thái bắt tay TCP** với các trạng thái SYN-SENT, ESTABLISHED, TIME-WAIT. Tuy vậy, firewall/NAT vẫn có thể tạo entry conntrack cho các luồng UDP quan sát được và đặt timeout theo chính sách. Do đó, nhãn “ESTABLISHED” của một entry UDP trong firewall không có nghĩa UDP đã thực hiện bắt tay TCP.

**QUIC** chạy trên UDP nhưng tự duy trì trạng thái kết nối, xác thực và mã hóa ở tầng giao thức của QUIC/TLS; QUIC không dùng ba gói SYN, SYN+ACK, ACK kiểu TCP. Khi điều tra HTTP/3, cần dùng telemetry phù hợp với QUIC thay vì chỉ tìm trạng thái TCP của socket.

## 9. Mối đe dọa dựa trên trạng thái kết nối

Theo dõi connection state giúp ngăn traffic bất thường, nhưng đồng thời tạo ra **tài nguyên hữu hạn** mà kẻ tấn công có thể gây áp lực.

| Kịch bản | Trạng thái/tín hiệu liên quan | Tác động có thể xảy ra | Biện pháp phòng vệ |
|---|---|---|---|
| **SYN flood** | Nhiều yêu cầu SYN; server tăng trạng thái chờ bắt tay, SYN/ACK retransmit | Đầy hàng đợi/kết cấu phục vụ kết nối mới; cạn tài nguyên | SYN cookies khi phù hợp, SYN proxy, rate limit và bảo vệ DDoS tại mạng biên |
| **Cạn bảng conntrack** | Entry/usage tiến gần giới hạn; thông báo table full/drops | Kết nối hợp lệ mới có thể bị từ chối hoặc mất trạng thái | Giới hạn traffic mới, capacity planning, tối ưu timeout theo yêu cầu, scale và giám sát |
| **Ứng dụng giữ socket sau FIN** | Nhiều CLOSE-WAIT kéo dài trên máy chủ | Tiêu tốn file descriptor/socket, có thể dừng tiếp nhận kết nối | Sửa luồng đóng socket, timeout ứng dụng, giám sát fd và số socket |
| **RST giả mạo hoặc bất thường** | Nhiều RST ngoài dự kiến, các phiên bị chấm dứt | Gián đoạn kết nối nếu RST được endpoint chấp nhận | Kiểm tra nguồn và sequence RST, anti-spoofing, bảo vệ đường kết nối và giám sát |
| **Kết nối nhàn rỗi bị thiết bị trung gian quên** | Conntrack/NAT/LB timeout khi endpoint còn nghĩ ESTABLISHED | Kết nối “treo”, lần gửi tiếp theo có thể thất bại | Căn chỉnh timeout, keepalive phù hợp, retry/backoff tại ứng dụng |
| **Quá nhiều kết nối ngắn** | TIME-WAIT lớn, tăng tốc độ mở/đóng kết nối | Áp lực socket, cổng nguồn, CPU hoặc NAT state tùy kiến trúc | Connection pooling, reuse HTTP hợp lý, tìm lỗi churn và đánh giá khả năng chịu tải |
| **Slow client ở lớp HTTP** | TCP vẫn ESTABLISHED nhưng request hoàn tất rất chậm | Chiếm worker/buffer/tài nguyên ứng dụng | Timeout đọc/ghi và giới hạn tài nguyên HTTP, reverse proxy và rate limit phù hợp |

Những tín hiệu này **không đủ để tự kết luận tấn công**. Ví dụ TIME-WAIT tăng có thể là hệ quả bình thường của lượng kết nối ngắn cao; SYN-RECEIVED tăng có thể do đường về đang mất gói. Cần đối chiếu baseline, băng thông, tỷ lệ hoàn tất handshake, tài nguyên và log từ nhiều lớp.

### 9.1. SYN flood khai thác giai đoạn nào?

SYN flood thường tạo nhiều yêu cầu bắt đầu kết nối mà không hoàn thành bắt tay bình thường. Server hoặc thiết bị trung gian có thể phải giữ trạng thái/bộ đếm trong lúc đợi ACK, làm ảnh hưởng khả năng phục vụ client thật.

**SYN cookies** cho phép một số TCP stack tránh giữ toàn bộ trạng thái chờ cho mọi SYN khi áp dụng cơ chế này. Tuy nhiên đây không phải giải pháp duy nhất cho DDoS: băng thông đường vào, năng lực firewall/LB, CPU và các nguồn lực khác vẫn có thể bị quá tải. Cơ chế và giới hạn tùy nền tảng.

### 9.2. Vì sao stateful firewall vẫn cần phòng vệ trước DoS?

Để lọc dựa trên trạng thái, thiết bị có thể tạo và tra cứu entry cho từng luồng. Nếu mỗi flow tiêu tốn tài nguyên, lưu lượng kết nối mới quá lớn có thể làm đầy bảng, tăng chi phí xử lý hoặc đẩy entry hợp lệ ra khỏi thời gian sống mong đợi.

Khi thiết kế, cần quan sát đồng thời **connection rate**, **concurrent connections**, **table utilization**, **drops**, **latency** và năng lực xử lý của thiết bị. Việc tăng dung lượng bảng chỉ xử lý một phần vấn đề; bảo vệ tuyến vào, rate limit và giới hạn theo nguồn/vùng sử dụng thường cần phối hợp.

### 9.3. IDS/IPS cần nhìn đúng hướng và đúng giai đoạn

IDS/IPS phân tích TCP flags, sequence, window và cấu trúc session để nhận diện dấu hiệu bất thường. Nếu sensor chỉ thấy một chiều, có thể khó xác định handshake đã hoàn tất hay chưa. Một IPS inline có thể chặn gói theo rule, nhưng cần cẩn thận với traffic hợp lệ bị rớt do mất gói hoặc đường đi bất đối xứng.

TLS mã hóa payload HTTP sau khi thiết lập; sensor không có điểm giải mã hợp lệ thường chủ yếu dựa vào metadata của TCP/TLS và mẫu lưu lượng. **Trạng thái TCP là tín hiệu hữu ích, nhưng không thể thay thế log ứng dụng, IdP hay phân quyền dữ liệu.**

## 10. Công cụ quan sát connection state

Trên Linux, công cụ `ss` cho biết trạng thái socket được kernel ghi nhận; công cụ conntrack (nếu được cài và có quyền thích hợp) cung cấp góc nhìn bảng theo dõi luồng. Chúng trả lời **hai câu hỏi khác nhau**, cần so sánh khi điều tra.

### 10.1. Quan sát socket TCP bằng ss

Các lệnh dưới đây **chỉ đọc trạng thái**:

~~~bash
# Liệt kê kết nối TCP, kèm địa chỉ/cổng dạng số
ss -tan

# Thống kê trạng thái socket
ss -s

# Các socket đang chờ hoàn tất bắt tay ở phía nhận
ss -tan state syn-recv

# Các socket đang chờ ứng dụng cục bộ đóng sau khi peer gửi FIN
ss -tan state close-wait

# Các socket TIME-WAIT
ss -tan state time-wait

# Các socket đang lắng nghe TCP
ss -tln
~~~

Ví dụ đầu ra **minh họa**, các cột/tên trạng thái có thể thay đổi:

~~~text
State       Recv-Q Send-Q Local Address:Port      Peer Address:Port
LISTEN      0      128    10.20.30.50:443         0.0.0.0:*
ESTAB       0      0      10.20.30.50:443         10.10.10.25:51514
TIME-WAIT   0      0      10.20.30.50:443         10.10.10.26:51515
~~~

`Recv-Q` và `Send-Q` cần được giải thích theo **loại socket và trạng thái**. Đối với LISTEN, các giá trị này có thể liên quan tới hàng đợi kết nối; không nên diễn giải giống hàng đợi byte trên một socket ESTABLISHED.

Muốn biết tiến trình nào giữ socket, có thể dùng `ss -tanp` với quyền xem thông tin tiến trình phù hợp. Thiếu quyền có thể khiến phần tên tiến trình trống, trong khi kết nối vẫn tồn tại.

### 10.2. Xem trạng thái conntrack

Nếu host dùng Linux Netfilter conntrack và có công cụ `conntrack`, ví dụ đọc bảng:

~~~bash
# Xem các entry TCP đang được theo dõi; có thể cần quyền quản trị
sudo conntrack -L -p tcp
~~~

Bảng này có thể lớn và chứa địa chỉ/mô tả lưu lượng nhạy cảm; chỉ thu thập trong môi trường có quyền, lọc và lưu giữ theo chính sách. Không phải mọi firewall, cloud gateway hoặc reverse proxy đều dùng chung cơ chế conntrack hay cung cấp góc nhìn này.

Điểm cần kiểm tra gồm bộ địa chỉ/cổng hai chiều, timeout, trạng thái được hệ thống báo, dấu hiệu đã thấy traffic chiều về và số lượng entry. Một entry bị mất trong khi socket endpoint vẫn báo ESTABLISHED là tình huống hoàn toàn có thể xảy ra.

### 10.3. Đọc TCP flags trong packet capture

Khi được phép capture ở đúng interface, có thể dùng Wireshark hoặc `tcpdump` để xem chuỗi SYN/SYN+ACK/ACK, FIN, RST và các lần truyền lại. Ví dụ lệnh **quan sát**, giới hạn vào một cặp host:

~~~bash
sudo tcpdump -ni eth0 'tcp and host 10.10.10.25 and host 10.20.30.50'
~~~

Lưu ý interface thực tế có thể không phải `eth0`; capture có thể chứa dữ liệu nhạy cảm. Áp dụng phạm vi, thời gian thu thập và quyền truy cập phù hợp. Đối với các kết nối qua load balancer/NAT/VPN, hãy ghi rõ **điểm capture** vì 5-tuple, địa chỉ hoặc khả năng quan sát payload có thể thay đổi theo từng đoạn.

### 10.4. Tín hiệu kết hợp khi giám sát

| Nguồn | Dữ liệu quan trọng | Gợi ý phân tích |
|---|---|---|
| Socket host | SYN-RECV, ESTAB, CLOSE-WAIT, FIN-WAIT, TIME-WAIT, retransmission | Giai đoạn và tài nguyên của endpoint |
| Firewall/NAT | Connection count, NEW rate, state table utilization, drops/timeouts | Áp lực trạng thái và hiệu lực chính sách |
| Load balancer | Active connections, backend resets, idle timeout, health | Lỗi giữa kết nối client và backend |
| IDS/IPS / packet capture | Flags, RTT, retransmission, sequence bất thường | Chuỗi giao tiếp thực tế và hành vi đáng ngờ |
| Ứng dụng / API | Accept/connect timeout, TLS failure, HTTP status, request ID | Lỗi vận hành ở lớp cao hơn TCP |
| Router / VPN | Link, route, tunnel state, packet loss, MTU, ACL counter | Khả năng chuyển tiếp và chính sách trên đường đi |

## 11. Phân tích các tình huống thường gặp

### Tình huống A — Client gửi SYN nhưng không thấy SYN + ACK

**Triệu chứng:** client liên tục truyền lại SYN; ứng dụng báo connect timeout.

**Giả thuyết:** firewall chặn SYN; tuyến đi/tuyến về không hoạt động; gói tới server nhưng server không có dịch vụ đang lắng nghe; SYN + ACK bị chặn trên đường về; server hoặc thiết bị trung gian quá tải. Nếu host nhận SYN tới cổng đóng và được phép phản hồi, nó có thể gửi RST thay vì im lặng.

**Cách phân biệt:** capture ở client và gần server, xem route hai chiều, rule/counter firewall, trạng thái LISTEN và tải máy chủ. Nếu server nhận SYN mà không gửi phản hồi, hướng điều tra khác với trường hợp server gửi SYN + ACK nhưng client không bao giờ nhận.

### Tình huống B — Nhiều SYN-RECV trên server

**Triệu chứng:** số lượng yêu cầu đang chờ bắt tay tăng, tỷ lệ kết nối thành công giảm.

**Giả thuyết:** SYN flood, mất ACK cuối do lỗi mạng/chính sách, backlog hoặc năng lực server không phù hợp, sensor quan sát sai giai đoạn.

**Cách phân biệt:** đo SYN/s, SYN+ACK/s, ACK hoàn tất, địa chỉ nguồn và phân bố, thời gian chờ, CPU, backlog và trạng thái thiết bị biên. Không nên chỉ căn cứ vào một ảnh chụp `ss` để kết luận nguồn traffic độc hại.

### Tình huống C — CLOSE-WAIT tăng liên tục

**Triệu chứng:** nhiều socket nằm lâu ở CLOSE-WAIT; số file descriptor của tiến trình tăng.

**Giải thích thường gặp:** peer đã gửi FIN, TCP stack cục bộ đã xác nhận, nhưng ứng dụng vẫn chưa đóng socket của mình. Có thể luồng xử lý bị treo, bỏ sót nhánh cleanup hoặc giữ tham chiếu đến connection.

**Cách tiếp cận:** kiểm tra tiến trình sở hữu socket, logs, cơ chế xử lý EOF, timeout và đường cleanup trong ứng dụng. Thay đổi routing hoặc đột ngột hạ thời gian TIME-WAIT không sửa được nguyên nhân của CLOSE-WAIT.

### Tình huống D — TIME-WAIT rất nhiều ở máy chủ

**Triệu chứng:** số entry TIME-WAIT cao sau một đợt tăng traffic.

**Cách hiểu:** phía quan sát có thể là bên chủ động hoàn tất nhiều kết nối ngắn. Cần xem thêm tỷ lệ mở/đóng, thiết kế keep-alive/connection pool, giới hạn tài nguyên, cổng nguồn và timeout. Nhiều TIME-WAIT **có thể là bình thường** nếu hệ thống đủ năng lực và không có lỗi.

**Hướng cải thiện:** giảm churn không cần thiết, tái sử dụng kết nối khi giao thức cho phép, đặt timeout ứng dụng/proxy phù hợp; tránh can thiệp tham số TCP một cách cơ học.

### Tình huống E — TCP báo ESTABLISHED nhưng API không phản hồi

**Triệu chứng:** có socket ESTABLISHED, nhưng request chờ hoặc timeout.

**Giả thuyết:** phía đối diện đã mất kết nối nhưng local chưa phát hiện; mất gói/PMTU; proxy idle timeout; ứng dụng bị nghẽn, deadlock hoặc chờ DB; TLS/HTTP đang lỗi; authz từ chối nhưng client chưa xử lý phù hợp.

**Cách phân biệt:** xem retransmission, thời gian chờ socket, log proxy/API, tín hiệu TLS, trạng thái thread/connection pool và các yêu cầu độc lập. **TCP ESTABLISHED chỉ là một lớp của chuỗi phục vụ ứng dụng.**

### Tình huống F — Kết nối chỉ lỗi khi qua firewall hoặc NAT

**Triệu chứng:** gọi trực tiếp từ cùng subnet được; qua vùng mạng hoặc VPN thì lỗi ngắt quãng.

**Giả thuyết:** bảng conntrack đầy, NAT entry hết hạn, route bất đối xứng, ACL giữa các zone không nhất quán hoặc MTU khác nhau.

**Cách phân biệt:** so 5-tuple và timestamp ở hai phía, xem drops/conntrack events, đường đi hai chiều, tình trạng state replication khi HA failover, NAT mapping và cờ TCP. Tránh chỉ sửa timeout theo cảm tính trước khi xác định điểm mất trạng thái.

## 12. Bảo vệ kết nối khi thiết kế kiến trúc mạng

Các nguyên tắc sau kết nối trực tiếp kiến thức TCP state với học phần bảo mật mạng:

1. **Phân đoạn theo chức năng:** chỉ cho phép khởi tạo kết nối TCP giữa các vùng thực sự cần thiết; chiều phản hồi áp dụng theo policy và cơ chế stateful của thiết bị.
2. **Giữ đường đi phù hợp:** với firewall/NAT stateful, đánh giá tuyến cả hai chiều, load balancing, failover và khả năng đồng bộ trạng thái.
3. **Bảo vệ năng lực xử lý kết nối:** dự kiến concurrent flow, connection rate, SYN backlog, conntrack/NAT table, CPU, bandwidth và timeout theo tải bình thường lẫn tình huống bất thường.
4. **Giảm khả năng lạm dụng:** rate limit, SYN flood protection, anti-spoofing, ACL và biện pháp DDoS phù hợp với vị trí mạng.
5. **Đồng bộ timeout giữa các tầng:** client, proxy, load balancer, firewall, VPN và API phải có chính sách nhất quán đủ cho nghiệp vụ; nếu khác, ứng dụng cần xử lý đóng/retry có kiểm soát.
6. **Đặt giám sát đúng vị trí:** sensor ở trước/giữa/sau điểm kết thúc TLS hay NAT sẽ quan sát những trường khác nhau; ghi rõ nguồn sự kiện và đường đi dữ liệu.
7. **Không suy diễn quyền từ trạng thái:** một kết nối TCP hợp lệ vẫn cần TLS phù hợp, xác thực danh tính, phân quyền API và giới hạn dữ liệu.

### 12.1. Một ma trận chính sách tham khảo

Với kiến trúc gồm mạng client, gateway, API và database:

| Đường kết nối | Ý định policy | Cơ chế cần phối hợp |
|---|---|---|
| Client → gateway TCP/443 | Cho phép trong phạm vi dịch vụ công khai | Rate limit, DDoS protection, TLS, WAF nếu phù hợp |
| Gateway → API TCP/cổng nội bộ | Chỉ gateway/nguồn tin cậy khởi tạo | Segmentation, identity giữa service, kiểm tra request |
| API → database TCP/cổng DB | Chỉ workload được phép khởi tạo | Security group/ACL, DB identity và quyền tối thiểu |
| Client → database TCP/cổng DB | Từ chối trực tiếp | Phân đoạn, rule ở ranh giới mạng dữ liệu |
| Mạng người dùng → giao diện quản trị firewall | Từ chối | Tách management plane, MFA/RBAC ở mạng quản trị |

Mục tiêu là để mỗi thiết bị biết **luồng nào được phép khởi tạo**, **luồng phản hồi nào thuộc trạng thái hợp lệ** và **điều kiện nào phải từ chối**. Ví dụ chỉ là chính sách logic; cấu hình thực tế tùy thiết bị và kiến trúc.

## 13. Bài tập tự kiểm tra

### Bài tập 1 — Dự đoán trạng thái

Một client gọi `connect()` đến server đang LISTEN. Hãy điền trạng thái của từng phía sau các mốc:

1. Client đã gửi SYN nhưng chưa nhận phản hồi.
2. Server nhận SYN và đã gửi SYN + ACK.
3. Client nhận SYN + ACK và gửi ACK cuối.
4. Server nhận ACK cuối.

**Đáp án định hướng:** (1) client SYN-SENT; (2) server SYN-RECEIVED; (3) client ESTABLISHED, server có thể còn SYN-RECEIVED nếu ACK đang trên đường; (4) server ESTABLISHED.

### Bài tập 2 — Đọc quá trình đóng

Client gửi FIN, server ACK nhưng chưa gửi FIN. Client đang ở trạng thái gì nếu ACK đã tới? Server thường ở trạng thái gì?

**Đáp án định hướng:** client **FIN-WAIT-2**; server **CLOSE-WAIT**. Khi server đóng chiều gửi và phát FIN, server vào LAST-ACK; client ACK FIN và vào TIME-WAIT trong trình tự thông thường.

### Bài tập 3 — Điều tra sự cố bảo mật

Một firewall ghi nhận tăng đột biến **NEW connections**, sau đó xuất hiện thông báo cạn bảng conntrack. Đồng thời ứng dụng không mở được thêm kết nối dù CPU ứng dụng vẫn bình thường.

Hãy nêu ít nhất ba nguồn dữ liệu cần kiểm tra và hai nhóm biện pháp ngắn hạn/dài hạn.

**Đáp án định hướng:** đối chiếu connection rate tại biên, số entry và drops/timeout của firewall, số TCP SYN và tỷ lệ hoàn tất handshake tại server, router/flow logs và dữ liệu DDoS. Biện pháp trước mắt có thể gồm giới hạn traffic bất thường tại biên và bảo vệ tài nguyên cho luồng hợp lệ; dài hạn cần rà soát capacity, timeout theo loại luồng, phân đoạn, scaling và hành vi mở/đóng kết nối của ứng dụng. Chỉ thay đổi giới hạn bảng khi đã hiểu nguyên nhân.

### Bài tập 4 — Phân biệt các lớp trạng thái

Một packet capture cho thấy TCP bắt tay hoàn tất, nhưng trình duyệt nhận HTTP 403. Có thể kết luận firewall “không cho kết nối TCP” không?

**Đáp án định hướng:** không. TCP đã thiết lập tại những điểm quan sát được; HTTP 403 thường thuộc tầng HTTP/ứng dụng hoặc thành phần gateway/WAF phát sinh phản hồi. Cần xác định nguồn trả 403 và kiểm tra xác thực, phân quyền, policy của API/gateway.

### Bài tập 5 — Vẽ sơ đồ quan sát

Với client → NAT → load balancer → API, hãy vẽ số lượng kết nối TCP có thể tồn tại, đánh dấu nơi đổi địa chỉ/cổng, nơi kết thúc TLS và nơi lưu connection state. Nếu load balancer làm TCP proxy, hãy phân biệt kết nối **client ↔ LB** và **LB ↔ API**. Chỉ ra ít nhất một tình huống mà client còn ESTABLISHED nhưng kết nối backend đã bị reset.

## 14. Thuật ngữ cần nhớ

| Thuật ngữ | Ghi nhớ |
|---|---|
| **TCP connection state** | Trạng thái máy TCP của một endpoint trong vòng đời kết nối |
| **Three-way handshake** | SYN → SYN + ACK → ACK để thiết lập trạng thái TCP |
| **SYN-SENT / SYN-RECEIVED** | Đang chờ phản hồi hoặc hoàn tất bắt tay |
| **ESTABLISHED** | Kết nối TCP đã được thiết lập theo phía quan sát |
| **FIN / RST** | Kết thúc một chiều có thứ tự / đặt lại hoặc từ chối kết nối |
| **CLOSE-WAIT** | Đã nhận FIN, đang chờ ứng dụng cục bộ đóng |
| **TIME-WAIT** | Giữ trạng thái trong một khoảng sau khi hoàn tất đóng thông thường |
| **Half-close** | Một chiều gửi đã đóng, chiều còn lại vẫn có thể truyền dữ liệu |
| **Conntrack** | Cơ chế thiết bị trung gian theo dõi trạng thái luồng để áp policy/NAT |
| **NEW / ESTABLISHED / RELATED / INVALID** | Nhãn trạng thái của connection tracking, không phải máy trạng thái TCP endpoint |
| **5-tuple** | IP nguồn, cổng nguồn, IP đích, cổng đích, giao thức |
| **Backlog** | Hàng đợi/cấu trúc giới hạn các yêu cầu hoặc kết nối đang chờ được xử lý theo thiết kế stack |
| **SYN cookies** | Một kỹ thuật giảm nhu cầu giữ state chờ SYN khi áp dụng |
| **Idle timeout** | Khoảng không hoạt động trước khi một thành phần quyết định đóng/quên trạng thái |
| **State exhaustion** | Cạn tài nguyên phục vụ lưu trữ/xử lý trạng thái kết nối |

## 15. Tổng kết

**Connection state là chìa khóa để hiểu thời điểm một kết nối TCP được mở, đang truyền dữ liệu, đóng lại hoặc thất bại.** Máy khách và máy chủ duy trì trạng thái TCP riêng; firewall, NAT, VPN gateway và load balancer còn duy trì trạng thái theo dõi luồng riêng, với timeout và quy tắc thực thi có thể khác nhau. Một kết nối chỉ vận hành ổn định khi các thành phần này có thông tin và chính sách tương thích dọc theo đường đi hai chiều.

Khi điều tra sự cố hoặc xây dựng kiến trúc an ninh mạng, hãy luôn xác định **trạng thái đang được quan sát ở đâu**, **gói SYN/ACK/FIN/RST nào đã thật sự đi qua**, **thiết bị trung gian còn entry hay không**, và **ứng dụng/TLS/authorization đã xử lý đến bước nào**. Từ đó mới chọn đúng biện pháp: sửa luồng đóng socket, điều chỉnh timeout có cơ sở, tăng năng lực stateful firewall, khắc phục định tuyến bất đối xứng hoặc bảo vệ hệ thống trước SYN flood và DDoS.
