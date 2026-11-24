# Ảnh hưởng của trạng thái phiên và resume đến việc đổi máy chủ

## Bối cảnh: kết nối lại không đồng nghĩa có thể tiếp tục cùng phiên

RSocket giữ kết nối hai chiều và cho phép nhiều interaction cùng chạy trên một connection. Trong triển khai có cân bằng tải, load balancer thường chọn một node khi client mở TCP hoặc WebSocket connection. Các stream RSocket sau đó được multiplex trên connection đó và cùng đi tới node đã được chọn.

Khi connection bị đứt, client có thể kết nối lại. Nhưng nếu kết nối mới được chuyển tới node khác, node mới có thể không biết phiên RSocket cũ, không có bộ đệm frame chưa được xác nhận và không giữ trạng thái cần để tiếp tục các stream đang chạy.

RSocket Resume cho phép hai peer khôi phục một session sau khi transport bị gián đoạn, trong giới hạn trạng thái Resume còn được lưu giữ. Để Resume thành công, node nhận kết nối lại phải tìm được trạng thái phiên tương ứng. Điều này tạo ra yêu cầu trực tiếp với chiến lược cân bằng tải:

- Giữ client quay lại đúng node đang sở hữu session.
- Hoặc chia sẻ/khôi phục trạng thái Resume giữa các node theo cách nhất quán.
- Nếu không thể Resume, tạo session mới và khôi phục tiến trình nghiệp vụ bằng cursor hoặc checkpoint ở tầng ứng dụng.

Bài học này phân biệt connection affinity, trạng thái session RSocket và trạng thái nghiệp vụ; giải thích quá trình Resume khi client đổi backend; so sánh sticky session với shared state; và trình bày cách thiết kế failover, timeout, rolling deployment và kiểm thử.

## 1. Phân biệt connection, RSocket session và trạng thái ứng dụng

Ba lớp trạng thái có vòng đời và cách phục hồi khác nhau.

| Lớp | Nội dung | Phạm vi tồn tại |
|---|---|---|
| Transport connection | TCP socket hoặc WebSocket đang mở, địa chỉ peer và trạng thái mạng | Từ lúc connect đến khi transport đóng |
| RSocket session | Resume token, vị trí frame, buffer gửi/nhận và trạng thái interaction cần cho Resume | Trong thời gian session còn hiệu lực |
| Application state | Danh tính người dùng, subscription, cursor, checkpoint, transaction, công việc đang chạy | Theo hợp đồng và kho lưu trữ của ứng dụng |

Một transport connection có thể bị đóng trong khi RSocket session vẫn còn khả năng Resume. Ngược lại, session có thể hết hạn dù client vẫn có thể mở một transport connection mới.

RSocket session cũng không phải bản sao toàn bộ trạng thái Java của ứng dụng. Resume không tự khôi phục:

- Đối tượng trong heap của node cũ.
- Một transaction database đang mở.
- Subscription tới Kafka hoặc broker nếu subscription đó chỉ tồn tại trong process cũ.
- Requester registry hoặc cache riêng của node.
- Công việc nghiệp vụ đã chạy dở nhưng chưa lưu trạng thái.
- Checkpoint mà ứng dụng chưa ghi bền vững.

Các trạng thái đó cần được quản lý riêng. Vì vậy, thiết kế HA phải trả lời hai câu hỏi: có thể tiếp tục session giao thức không, và nếu không thể thì ứng dụng có thể tiếp tục nghiệp vụ từ đâu?

## 2. Load balancer chọn node ở cấp connection

Một RSocket connection có thể mang nhiều request-response, fire-and-forget, request-stream và request-channel. Với TCP proxy hoặc WebSocket proxy thông thường, load balancer chọn backend khi thiết lập transport connection.

~~~mermaid
flowchart TD
    C["RSocket Client"] --> LB["Load Balancer"]
    LB -->|Connection A| N1["Node A"]
    LB -->|Connection B| N2["Node B"]
    N1 --> S1["Nhiều RSocket stream trên connection A"]
    N2 --> S2["Nhiều RSocket stream trên connection B"]
~~~

Các stream trên cùng một connection không tự động được chia sang các node khác nhau. Chúng được multiplex qua connection và được xử lý bởi peer ở đầu bên kia của connection.

Điều này có một số hệ quả:

- Cân bằng tải thường xảy ra khi tạo connection mới.
- Một connection tồn tại lâu có thể giữ tải trên node ban đầu trong thời gian dài.
- Số connection không phản ánh đầy đủ tải CPU, số stream hoặc throughput.
- Khi connection bị ngắt và client reconnect, load balancer có thể chọn node khác.
- Việc chọn node khác không tự động chuyển session state từ node cũ.

Không nên coi một TCP load balancer là bộ định tuyến từng RSocket route. Nếu muốn phân phối từng interaction sang nhiều backend, cần một kiến trúc proxy hoặc gateway hiểu giao thức và có mô hình quản lý session phù hợp.

## 3. Điều gì xảy ra khi client reconnect và gửi RESUME?

Khi Resume được bật và transport bị gián đoạn, client có thể mở transport mới rồi yêu cầu tiếp tục session cũ. Hai peer dùng resume token và vị trí frame để xác định trạng thái nào đã được peer nhận.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as Load Balancer
    participant A as Node A
    participant B as Node B

    C->>LB: Kết nối ban đầu
    LB->>A: TCP/WebSocket connection
    C->>A: SETUP + Resume được cấu hình
    A-->>C: Session hoạt động
    C->>A: Nhiều RSocket interaction
    Note over C,A: Transport bị gián đoạn
    C->>LB: Mở transport mới và yêu cầu RESUME
    LB->>B: Chọn backend khác
    C->>B: RESUME token + vị trí frame
    B->>B: Tìm trạng thái session
    alt B có trạng thái Resume hợp lệ
        B-->>C: RESUME_OK
        B-->>C: Phát lại frame còn thiếu
        C-->>B: Tiếp tục session
    else B không có trạng thái session
        B-->>C: RESUME_REJECTED hoặc lỗi Resume
        C->>LB: Tạo session mới
        C->>B: SETUP mới và khôi phục nghiệp vụ
    end
~~~

Resume không chỉ là reconnect TCP. Client phải gửi thông tin Resume theo giao thức; server phải tìm được session tương ứng và có đủ trạng thái để tiếp tục.

Nếu node B không có session state của node A, nó không thể tự suy ra buffer và vị trí frame chỉ từ việc client gửi lại một token. Trong trường hợp đó, Resume bị từ chối hoặc không thể hoàn tất. Client cần xử lý kết quả này bằng fallback phù hợp.

### Frame nào có thể được phát lại?

Resume sử dụng vị trí frame mà mỗi peer đã nhận để xác định phần dữ liệu cần truyền lại. Các frame còn nằm trong buffer Resume và chưa được peer xác nhận ở cấp giao thức có thể được phát lại.

Đây là phục hồi ở tầng giao thức. Nó không có nghĩa mọi event đã được commit vào database của consumer. Một payload có thể đã đến ứng dụng nhưng process crash trước khi commit; hoặc ứng dụng đã commit nhưng trạng thái nhận frame chưa được bảo toàn như mong đợi trong tình huống lỗi. Vì vậy, dữ liệu nghiệp vụ vẫn cần event ID, idempotency và checkpoint nếu không được phép mất hoặc lặp tác dụng phụ.

## 4. Những trạng thái cần có để Resume thành công

Một session có thể cần lưu các thông tin như:

- Resume token nhận diện session.
- Vị trí frame gửi và nhận ở mỗi hướng.
- Buffer các frame đã gửi nhưng chưa được peer xác nhận.
- Thông tin cần thiết để tiếp tục các interaction đang mở.
- Trạng thái timeout, session duration và giới hạn buffer.
- Các thông tin giao thức khác mà implementation sử dụng để khôi phục session.

Chi tiết cấu trúc phụ thuộc implementation RSocket. Ứng dụng không nên tự tạo một bản ghi đơn giản chỉ chứa token rồi giả định đã sao lưu đủ session state.

### Resume store mặc định và shared store

Nếu Resume store chỉ nằm trong bộ nhớ của node, session chỉ có thể được tiếp tục khi reconnect quay lại node còn giữ trạng thái đó và trạng thái chưa hết hạn.

Muốn hỗ trợ reconnect sang node khác, implementation cần có cơ chế chia sẻ hoặc khôi phục trạng thái Resume giữa các node. Một số implementation cung cấp SPI hoặc extension để thay Resume store; khả năng dùng shared store và các yêu cầu dữ liệu cụ thể phụ thuộc phiên bản.

Shared store phải lưu đủ thông tin mà implementation cần, không chỉ một mapping token sang node. Nếu session buffer hoặc frame position không được chia sẻ đúng, node đích vẫn không thể Resume an toàn.

### Yêu cầu nhất quán của shared state

Shared store phải xử lý đúng các thao tác cạnh tranh:

- Ghi frame mới và cập nhật vị trí gửi.
- Ghi nhận frame peer đã nhận.
- Xóa dữ liệu đã được xác nhận.
- Đọc và khôi phục session khi reconnect.
- Ngăn hai node cùng nhận quyền sở hữu một session.
- Hết hạn session và giải phóng buffer.

Nếu replication bất đồng bộ làm node B đọc trạng thái cũ, B có thể replay thiếu hoặc sai frame. Nếu hai node cùng xử lý một token, chúng có thể ghi đè trạng thái của nhau. Cần atomic ownership hoặc lease, cập nhật có thứ tự và chính sách fencing phù hợp.

Không tự triển khai shared Resume store bằng một bảng key-value đơn giản nếu chưa hiểu đầy đủ contract của implementation. Resume store là một phần của protocol state, nên lỗi nhất quán có thể gây lỗi khó phục hồi hơn một lần reconnect thất bại.

## 5. Chiến lược 1: sticky session hoặc connection affinity

Sticky session cố gắng đưa các lần reconnect của cùng client về node ban đầu.

Ví dụ:

~~~mermaid
flowchart LR
    C["Client A"] --> LB["Load Balancer"]
    LB -->|Affinity key A| N1["Node A"]
    C2["Client B"] --> LB
    LB -->|Affinity key B| N2["Node B"]
~~~

Nếu Node A vẫn hoạt động và còn session state, client reconnect về Node A có cơ hội Resume thành công mà không cần chia sẻ trạng thái giữa các node.

### Cách tạo affinity

Tùy transport và hạ tầng, có thể dùng:

- Cookie affinity cho WebSocket handshake nếu cookie được giữ qua reconnect.
- Hash theo địa chỉ nguồn hoặc một định danh ổn định do proxy nhìn thấy.
- TLS client certificate identity nếu proxy có thể sử dụng danh tính đã xác thực.
- Routing key ở gateway hoặc service discovery.
- Session directory để ánh xạ một định danh session tới node sở hữu.

Không phải cách nào cũng phù hợp với mọi transport. Với TCP proxy thông thường, load balancer không nhìn thấy cookie HTTP. Với WebSocket, cookie có thể được dùng khi handshake nhưng resume token nằm trong frame RSocket sau khi WebSocket đã upgrade. Một HTTP proxy thông thường không thể dựa vào token trong frame để chọn backend nếu nó không hiểu giao thức RSocket.

Hash theo source IP cũng có giới hạn: nhiều client có thể dùng chung NAT, địa chỉ IP có thể thay đổi khi chuyển mạng, và một nhóm client có thể dồn tải lên một node.

### Sticky session không giải quyết node failure

Nếu Node A chết, affinity có thể vẫn cố đưa client về A hoặc chọn node khác nhưng node mới không có session state. Sticky session chỉ giúp reconnect quay về cùng owner khi owner còn sống.

Vì vậy, sticky session là cách giảm xác suất phải chuyển session giữa node; nó không phải cơ chế HA đầy đủ. Cần có fallback application recovery và có thể cần shared state nếu muốn chịu được mất node.

## 6. Chiến lược 2: shared hoặc replicated Resume state

Trong mô hình này, các node có thể truy cập trạng thái Resume chung. Client reconnect tới Node B; B tìm session bằng token, đọc frame positions và buffer, sau đó tiếp tục session nếu state còn hợp lệ.

~~~mermaid
flowchart TD
    C["Client"] --> LB["Load Balancer"]
    LB --> A["Node A"]
    LB --> B["Node B"]
    A <--> R["Shared Resume Store"]
    B <--> R
    A -->|Lưu session state| R
    B -->|Khôi phục session state| R
~~~

Lợi ích:

- Client có thể reconnect tới node khác.
- Node failure ít phụ thuộc vào session state trong heap của node cũ.
- Có thể drain hoặc thay node trong rolling deployment dễ hơn.
- Phân phối connection mới linh hoạt hơn.

Đổi lại, shared state tạo thêm yêu cầu về latency, consistency, availability và dung lượng lưu trữ. Mỗi frame có thể làm tăng hoạt động đọc/ghi hoặc buffer tùy implementation. Nếu shared store trở thành bottleneck hoặc bị lỗi, khả năng Resume của toàn cluster cũng bị ảnh hưởng.

### Không phải mọi shared store đều tương thích

Cần kiểm tra implementation RSocket đang dùng có cho phép tùy chỉnh Resume store hay không, dữ liệu nào phải được lưu và các node cần đồng bộ cấu hình nào. Với RSocket Java, hãy kiểm tra API ResumeStore/ResumeStoreFactory của đúng phiên bản trước khi xây dựng custom store.

Không giả định có thể dùng Redis hoặc database bất kỳ làm Resume store chỉ bằng cách lưu resume token. Store cần đáp ứng semantics của implementation về frame buffer, vị trí và lifecycle session.

### Những điều kiện để chia sẻ an toàn

- Tất cả node tương thích về phiên bản giao thức và định dạng Resume state.
- Resume token không bị ánh xạ nhầm giữa các session.
- Một session chỉ có một owner hoạt động tại một thời điểm, hoặc store có cơ chế phối hợp an toàn.
- Ghi vị trí và buffer có thứ tự nhất quán.
- Session expiry được áp dụng nhất quán trên toàn cluster.
- Có giới hạn dung lượng cho buffer và số session.
- Khi store mất dữ liệu hoặc không khả dụng, client có đường fallback rõ ràng.

## 7. Chiến lược 3: định tuyến reconnect về session owner

Một kiến trúc khác là duy trì session directory:

| Trường | Mục đích |
|---|---|
| session key/token reference | Định danh session theo cách an toàn |
| owner node | Node đang giữ session |
| lease/heartbeat | Xác định owner còn sống |
| expiresAt | Hạn sử dụng của mapping |
| generation/fencing token | Ngăn owner cũ tiếp tục ghi sau khi bị thay thế |

Khi client reconnect, một thành phần định tuyến tìm owner và chuyển connection tới node đó.

Cách này có thể kết hợp với sticky session. Nếu owner còn sống, reconnect quay lại đúng node. Nếu owner đã chết, directory cần đánh dấu owner không còn hợp lệ và chọn một trong hai đường:

1. Khôi phục session từ shared Resume state trên node mới.
2. Từ chối Resume và yêu cầu client tạo session mới, sau đó khôi phục nghiệp vụ bằng application checkpoint.

### Giới hạn của proxy thông thường

Resume token nằm trong giao thức RSocket, không phải một HTTP header mặc định mà mọi load balancer đều hiểu. Một TCP proxy hoặc WebSocket reverse proxy thông thường không thể tự đọc và định tuyến theo token nếu không terminate/parse giao thức.

Nếu dùng protocol-aware gateway để đọc token, cần bảo vệ token, tránh ghi log, giới hạn quyền truy cập và bảo đảm gateway không làm sai semantics của TLS hoặc frame. Có thể dùng một routing key riêng được cấp ở tầng kết nối nếu kiến trúc hỗ trợ, nhưng key đó phải được xác thực và liên kết an toàn với session.

## 8. Resume và application recovery giải quyết hai bài toán khác nhau

Resume giúp tiếp tục session giao thức và phát lại frame còn nằm trong trạng thái Resume. Application recovery giúp khôi phục công việc nghiệp vụ khi session không thể tiếp tục hoặc khi ứng dụng cần xác nhận dữ liệu đã commit.

| Tình huống | RSocket Resume | Application recovery |
|---|---|---|
| TCP connection đứt ngắn, session còn state | Có thể tiếp tục session | Có thể không cần tạo subscription mới |
| Reconnect về node khác không có session state | Thất bại | Mở session mới và đọc từ checkpoint |
| Node cũ chết, state chỉ ở memory | Không thể khôi phục từ node khác | Khôi phục nếu event log/checkpoint còn |
| Client đã commit event nhưng ACK nghiệp vụ mất | Resume không chứng minh commit | Deduplicate event và gửi lại ACK |
| Session hết thời hạn | Không thể Resume session cũ | Resubscribe từ cursor/checkpoint |
| Application handler hoặc broker consumer bị restart | Không tự khôi phục object nghiệp vụ | Khởi tạo lại từ durable state |

Một thiết kế bền vững thường kết hợp cả hai:

1. Dùng Resume để xử lý gián đoạn transport ngắn.
2. Dùng application checkpoint để tiếp tục khi Resume không còn khả năng.
3. Dùng event ID và idempotency để chịu được duplicate.
4. Dùng durable event log hoặc nguồn có cursor để phát lại dữ liệu.
5. Không coi protocol Resume là bảo đảm exactly-once cho side effect nghiệp vụ.

Ví dụ, client đang đọc event đến offset 500. Transport bị ngắt và reconnect về node khác. Nếu Resume thành công, session tiếp tục theo frame positions. Nếu Resume thất bại, client mở request-stream mới với cursor ứng dụng đã commit, ví dụ offset 497. Event 498-500 có thể được phát lại; client deduplicate và chỉ xác nhận checkpoint sau khi transaction đã commit.

## 9. Thời hạn Resume, buffer và cửa sổ reconnect

Resume chỉ có thể thành công khi trạng thái session còn tồn tại và đủ dữ liệu để tiếp tục. Cần cấu hình các giới hạn có chủ đích:

- **Session duration:** thời gian session được giữ sau khi transport mất kết nối.
- **Stream timeout:** thời gian một stream có thể chờ hoặc tồn tại theo chính sách implementation.
- **Resume buffer capacity:** số byte hoặc frame có thể giữ để replay.
- **Keepalive interval:** chu kỳ kiểm tra peer còn hoạt động.
- **Reconnect retry window:** khoảng thời gian client tiếp tục thử kết nối lại.
- **Store retention:** thời gian shared store giữ trạng thái session.

Các giới hạn cần tương thích. Nếu client retry trong 10 phút nhưng server chỉ giữ session 2 phút, phần lớn retry sẽ không thể Resume. Nếu giữ session quá lâu, buffer và metadata của nhiều session có thể chiếm bộ nhớ hoặc dung lượng store.

### Ước lượng buffer

Một ước lượng sơ bộ cho buffer gửi là:

\[
B \approx \lambda \times \bar{s} \times T
\]

Trong đó:

- \(\lambda\): tốc độ frame hoặc payload được tạo mỗi giây.
- \(\bar{s}\): kích thước trung bình của mỗi frame.
- \(T\): khoảng thời gian cần giữ dữ liệu để Resume.

Ví dụ, nếu một session tạo 100 payload/giây, mỗi payload trung bình 2 KB và giữ dữ liệu 30 giây, buffer lý thuyết khoảng 6 MB cho session đó, chưa tính overhead và metadata. 1.000 session ở mức này có thể cần khoảng 6 GB nếu mọi session đều giữ buffer tối đa. Cần đo bằng workload thực và áp dụng giới hạn, vì không phải mọi frame đều nằm trong buffer cùng lúc.

### Khi buffer đầy

Nếu peer bị mất kết nối lâu hoặc tạo dữ liệu nhanh hơn khả năng xác nhận, buffer có thể đạt giới hạn. Implementation có thể từ chối thêm dữ liệu, kết thúc session hoặc khiến Resume không thể tiếp tục tùy chính sách. Không nên giả định buffer sẽ tự mở rộng vô hạn.

Ứng dụng cần có metrics về buffer occupancy, số session gần chạm giới hạn, Resume rejection và fallback recovery.

## 10. Cấu hình client, server và load balancer

Resume phải được cấu hình ở cả hai peer theo API và khả năng của implementation. Client cần bật Resume và reconnect theo retry policy; server cần giữ trạng thái session đủ lâu và cung cấp Resume store phù hợp.

Tên API và cách tạo custom store thay đổi theo phiên bản RSocket Java. Hãy kiểm tra Javadoc của đúng artifact trước khi dùng method hoặc constructor cụ thể; không giả định có một thuộc tính Spring Boot chung tên spring.rsocket.resume.* cho mọi phiên bản.

### Các tham số cần thống nhất

| Thành phần | Tham số/chính sách | Mục tiêu |
|---|---|---|
| Client | Resume enabled | Yêu cầu tiếp tục session khi transport reconnect |
| Client | Retry có backoff và jitter | Tránh reconnect storm |
| Client | Resume window | Thời gian tối đa client tiếp tục thử |
| Server | Resume enabled | Chấp nhận khôi phục session |
| Server | Session duration | Giữ session state đủ lâu |
| Server | Resume store | Lưu frame position và buffer theo implementation |
| Cả hai | Resume token/session contract | Nhận diện đúng session |
| Load balancer | TCP/WebSocket timeout | Không cắt connection đang hoạt động ngoài dự kiến |
| Load balancer | Affinity/routing | Đưa reconnect tới owner hoặc node có shared state |
| Cluster | Node drain và health check | Ngừng nhận connection mới có kiểm soát |

Ví dụ bảng cấu hình ứng dụng minh họa (đây là mô hình tham số của hệ thống, không phải các property Spring Boot chuẩn):

~~~yaml
rsocket:
  client:
    resume-enabled: true
    reconnect:
      initial-delay: 500ms
      max-delay: 15s
      jitter: 0.25
      max-elapsed-time: 3m
  server:
    resume-enabled: true
    session-retention: 3m
    resume-buffer-limit: 16MB
  load-balancer:
    connection-affinity: session-owner
    idle-timeout: 90s
~~~

Giá trị trên chỉ minh họa. Cần chọn timeout và buffer dựa trên latency, tốc độ phát dữ liệu, thời gian gián đoạn cần chịu đựng và dung lượng cluster.

### TCP load balancer

Với TCP, load balancer nên:

- Giữ nguyên một backend cho mỗi connection đã mở.
- Cho phép connection sống lâu và có timeout idle phù hợp keepalive.
- Hỗ trợ reconnect tới owner nếu dùng affinity.
- Có health check để ngừng gửi connection mới tới node không khỏe.
- Không cắt đồng loạt mọi connection khi cấu hình hoặc node thay đổi nếu có thể drain có kiểm soát.

### WebSocket load balancer

Với WebSocket, cần hỗ trợ HTTP Upgrade và giữ nguyên connection sau handshake. Cookie hoặc header của handshake có thể hỗ trợ affinity nếu client gửi lại khi reconnect. Tuy nhiên, resume token được trao đổi trong frame RSocket sau khi WebSocket đã mở; proxy HTTP thông thường không tự hiểu token đó.

Hãy kiểm tra idle timeout của proxy, hỗ trợ ping/pong và việc proxy có giữ frame hai chiều đúng cách không. Không giả định một HTTP session hoặc cookie đồng nghĩa với RSocket session Resume.

## 11. Rolling deployment và connection draining

RSocket connection thường sống lâu hơn một HTTP request. Khi deploy phiên bản mới, node cũ có thể vẫn giữ nhiều session và stream đang chạy.

Một quy trình drain có thể gồm:

1. Đánh dấu node không nhận connection mới.
2. Tiếp tục phục vụ connection hiện có trong một khoảng grace period.
3. Ngừng tạo subscription hoặc công việc mới theo chính sách.
4. Cho client cơ hội hoàn tất hoặc reconnect có kiểm soát.
5. Nếu Resume state được chia sẻ, cho phép reconnect tới node mới.
6. Nếu Resume state chỉ local, client cần fallback application recovery sau khi node cũ đóng.
7. Đóng connection còn lại trước deadline shutdown.

Không terminate process ngay khi bắt đầu deploy nếu cần bảo toàn session state trong memory. Nếu buộc phải restart nhanh, hãy thông báo cho client hoặc để client xử lý Resume rejection và resubscribe từ checkpoint.

### Tránh reconnect storm

Khi một node bị loại khỏi cluster, hàng nghìn client có thể reconnect gần như đồng thời. Dùng exponential backoff, jitter và giới hạn số lần thử trong một cửa sổ. Server mới cũng cần giới hạn tốc độ accept connection và tốc độ khôi phục session.

Không retry liên tục với khoảng delay cố định rất ngắn. Điều đó có thể làm node mới quá tải ngay khi vừa khởi động.

## 12. Cân bằng tải theo connection có thể gây lệch tải

Vì một connection có thể chứa nhiều stream dài hạn, round-robin theo connection count không nhất thiết cân bằng CPU hoặc throughput.

Ví dụ:

| Node | Connection | Active stream | Throughput |
|---|---:|---:|---:|
| Node A | 100 | 2.000 | 80 MB/s |
| Node B | 100 | 300 | 12 MB/s |
| Node C | 100 | 450 | 18 MB/s |

Số connection bằng nhau nhưng tải khác nhau đáng kể. Khi cân bằng tải, cần đo:

- Active connection và active stream.
- Request/response rate.
- Payload bytes per second.
- CPU, heap và GC pause.
- Resume buffer usage.
- Shared store latency và error rate.
- Số reconnect và Resume attempt theo node.
- Số session đang chờ hoặc bị từ chối Resume.

Có thể giới hạn số stream hoặc tải trên mỗi connection, giới hạn subscription theo principal, hoặc điều chỉnh cách client tạo connection. Tuy nhiên, mở nhiều connection chỉ để cân bằng tải có thể làm tăng chi phí handshake, memory và quản lý session. Hãy đo trước khi thay đổi.

## 13. Khi nào chọn sticky session, shared state hoặc application recovery?

| Điều kiện | Chiến lược phù hợp |
|---|---|
| Node ít thay đổi, session ngắn, chấp nhận reconnect mới khi node chết | Sticky session + application recovery |
| Cần Resume khi transport đứt nhưng node vẫn sống | Affinity về cùng node |
| Cần chuyển session qua node khác khi node cũ còn sống hoặc đang drain | Shared Resume state hoặc session-owner routing |
| Cần chịu được node chết hoàn toàn | Shared/replicated Resume state nếu implementation hỗ trợ, cộng application recovery |
| Không cần giữ stream giao thức, chỉ cần tiếp tục dữ liệu nghiệp vụ | New session + checkpoint/replay có thể đơn giản hơn |
| Nguồn dữ liệu không có durable log/cursor | Cần thiết kế lại nguồn hoặc chấp nhận giới hạn khôi phục |

Không nhất thiết phải triển khai shared Resume store cho mọi hệ thống. Nếu stream có thể mở lại nhanh từ checkpoint và không cần giữ nguyên interaction đang chạy, application recovery có thể đơn giản và đáng tin cậy hơn.

Ngược lại, nếu cần duy trì session lâu dài với nhiều stream đang mở và muốn tiếp tục frame mà không khởi tạo lại interaction, Resume và session affinity/shared state có giá trị rõ ràng.

## 14. Kiểm thử Resume và đổi node

Kiểm thử chỉ với một client/server trên localhost không đủ để chứng minh khả năng Resume qua load balancer. Cần có ít nhất hai node và một proxy hoặc test router có thể thay đổi backend.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Transport đứt rồi reconnect về cùng node | Resume thành công nếu session còn hiệu lực |
| Reconnect về node khác, không có shared state | Resume bị từ chối hoặc fallback có kiểm soát |
| Reconnect về node khác có shared Resume state | Resume thành công nếu state nhất quán và còn hạn |
| Node owner chết, state chỉ ở memory | Không Resume; application recovery tiếp tục từ checkpoint |
| Node owner chết, shared state còn | Node khác có thể khôi phục nếu implementation hỗ trợ và store đủ state |
| Session hết retention | Resume bị từ chối, client mở session mới |
| Resume buffer đầy | Có hành vi giới hạn rõ ràng và metrics |
| Shared store chậm hoặc lỗi | Không tạo trạng thái session sai; fallback theo policy |
| Hai reconnect đồng thời dùng cùng token | Chỉ một session owner được chấp nhận |
| Rolling deployment | Node drain không gây mất dữ liệu nghiệp vụ |
| Client reconnect đồng loạt | Backoff/jitter ngăn reconnect storm |
| Application ACK bị mất | Duplicate được xử lý idempotent sau replay |

### Test chuyển node có shared store

Một integration test nên thực hiện:

1. Khởi động Node A và Node B với cấu hình Resume tương thích.
2. Client kết nối qua load balancer và được định tuyến tới Node A.
3. Mở một request-stream dài hạn và nhận một số payload.
4. Làm gián đoạn transport.
5. Buộc load balancer định tuyến reconnect tới Node B.
6. Client gửi RESUME với token của session cũ.
7. Xác nhận Node B tìm được state và trả RESUME_OK.
8. Xác nhận các frame còn thiếu được phát lại theo protocol.
9. Xác nhận stream tiếp tục mà không tạo session nghiệp vụ trùng.

### Test fallback khi Resume thất bại

Một test khác nên xóa session state hoặc làm Node A mất hoàn toàn rồi reconnect về Node B:

1. Client đang đọc tới event có cursor 500.
2. Node A bị dừng và không còn Resume state.
3. Client nhận Resume rejection hoặc lỗi reconnect.
4. Client tạo session RSocket mới.
5. Client đăng ký lại từ application checkpoint đã commit, ví dụ 497.
6. Event 498-500 có thể được phát lại.
7. Client deduplicate và không lặp tác dụng phụ.
8. Client tiếp tục ACK checkpoint mới.

Test này quan trọng hơn việc chỉ kiểm tra một lần Resume thành công, vì nó xác nhận ứng dụng vẫn có thể phục hồi khi điều kiện giao thức không còn đáp ứng.

## 15. Các lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ reconnect tự giữ session | Client tạo session mới và mất interaction cũ | Bật Resume ở hai peer và giữ session state |
| Round-robin reconnect sang node bất kỳ | Node đích không tìm thấy session | Dùng affinity, owner routing hoặc shared state |
| Chỉ chia sẻ resume token | Thiếu frame buffer và vị trí cần để Resume | Chia sẻ đầy đủ state theo contract implementation |
| Nghĩ sticky session chịu được node chết | Session local vẫn mất khi owner chết | Bổ sung shared state hoặc application recovery |
| Dùng Resume thay checkpoint nghiệp vụ | Không bảo đảm database đã commit | Dùng application ACK, event ID và checkpoint |
| Dùng một Redis key đơn giản làm Resume store | Có thể sai thứ tự, race hoặc thiếu dữ liệu protocol | Triển khai đúng Resume store contract của implementation |
| Dùng source IP làm affinity duy nhất | NAT và thay đổi mạng gây đổi owner hoặc lệch tải | Chọn routing identity ổn định hơn |
| Cho rằng HTTP proxy đọc được Resume token | Reconnect có thể đến sai node | Dùng affinity handshake, session directory hoặc protocol-aware gateway |
| Giữ session quá lâu và buffer không giới hạn | Tăng heap hoặc shared-store usage | Giới hạn TTL, buffer và số session |
| Idle timeout nhỏ hơn keepalive window | Proxy cắt connection đang hoạt động | Đồng bộ timeout và keepalive |
| Deploy node rồi kill ngay | Mất session state local | Drain, Resume shared state hoặc fallback checkpoint |
| Retry đồng loạt không jitter | Reconnect storm làm node mới quá tải | Exponential backoff và jitter |
| Chỉ đo số connection | Không thấy node có nhiều stream nặng | Đo active stream, throughput, CPU và buffer |
| Không kiểm thử Resume rejection | Client có thể mắc kẹt sau node failure | Kiểm thử fallback tạo session mới và replay |

## Kết luận

Trạng thái phiên quyết định việc một client có thể tiếp tục RSocket session khi load balancer chuyển kết nối sang máy chủ khác hay không. Một connection mới chỉ là transport mới; để Resume thành công, node đích phải tìm được resume token và toàn bộ trạng thái giao thức cần thiết, gồm frame positions và buffer còn hiệu lực.

Sticky session giúp client quay lại node sở hữu session khi node đó còn sống. Shared Resume state hoặc session-owner routing có thể hỗ trợ chuyển node, nhưng đòi hỏi implementation hỗ trợ và cơ chế lưu trữ nhất quán. Khi Resume không thể thực hiện, client cần tạo session mới và khôi phục nghiệp vụ từ application checkpoint hoặc cursor, đồng thời xử lý duplicate bằng idempotency.

Hãy thiết kế load balancer ở cấp connection, đặt timeout phù hợp với keepalive, drain node có kiểm soát, giới hạn Resume window và buffer, đo tải theo active stream thay vì chỉ số connection, và kiểm thử cả Resume thành công lẫn fallback sau node failure. Nhờ đó, hệ thống có thể mở rộng ngang mà vẫn kiểm soát được tính liên tục của session và dữ liệu nghiệp vụ.

## Tài liệu tham khảo

- [RSocket Protocol — Resume và Session](https://rsocket.io/about/protocol/)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [RSocket Core API](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/index.html)
- [Spring Framework — RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor — Retry và Backpressure](https://projectreactor.io/docs/core/release/reference/)
