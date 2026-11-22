# Định tuyến DNS bằng Azure Traffic Manager

## 1. Bối cảnh và mục tiêu

Trong hệ sinh thái Microsoft Azure, một ứng dụng web có thể được triển khai đồng thời ở nhiều region nhằm phục vụ người dùng ở các khu vực khác nhau và tiếp tục hoạt động khi một điểm triển khai gặp sự cố. Ví dụ, doanh nghiệp đặt một bản ứng dụng tại Southeast Asia và một bản tại East Asia. Cả hai đều có địa chỉ truy cập công khai, nhưng người dùng chỉ cần ghi nhớ một tên miền là **app.example.com**.

Câu hỏi là: khi người dùng truy cập tên miền chung, làm thế nào hệ thống chọn điểm đến phù hợp, phát hiện endpoint không khỏe và thay đổi kết quả phân giải tên khi cần?

**Azure Traffic Manager** giải quyết bài toán này ở tầng **DNS**. Traffic Manager trả lời truy vấn DNS theo phương pháp định tuyến đã chọn và trạng thái giám sát endpoint. Sau khi nhận kết quả DNS, thiết bị người dùng kết nối **trực tiếp đến endpoint ứng dụng**.

Sau bài học, bạn có thể:

1. Giải thích sự khác biệt giữa định tuyến DNS và proxy/cân bằng tải chuyển tiếp lưu lượng.
2. Nhận diện profile, endpoint, routing method, health probe và DNS TTL.
3. Chọn phương pháp định tuyến phù hợp cho ưu tiên dự phòng, chia tỷ lệ, độ trễ hoặc khu vực địa lý.
4. Cấu hình một Traffic Manager profile bằng Azure Portal và Azure CLI.
5. Kết nối custom domain, thiết kế HTTPS và kiểm tra DNS.
6. Thử nghiệm failover, hiểu giới hạn do DNS cache và xử lý các sự cố thường gặp.
7. Phối hợp Traffic Manager với dịch vụ tính toán, mạng, giám sát, bảo mật và kiểm soát chi phí trên Azure.

## 2. Traffic Manager hoạt động ở tầng DNS

Traffic Manager **không nhận rồi chuyển tiếp từng HTTP request** như reverse proxy. Nó vận hành theo mô hình sau:

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant R as Recursive DNS resolver
    participant T as Azure Traffic Manager DNS
    participant A as Endpoint A
    participant B as Endpoint B
    U->>R: Hỏi IP của app.example.com
    R->>T: Truy vấn tên thuộc Traffic Manager
    T-->>R: Trả lời theo routing method và health
    R-->>U: Trả lời DNS được cache theo TTL
    U->>A: Kết nối HTTPS trực tiếp tới endpoint được chọn
    Note over U,A: Traffic Manager không nằm trên đường truyền HTTP
    T->>A: Health probe theo cấu hình
    T->>B: Health probe theo cấu hình
~~~

Một luồng điển hình:

1. Người dùng nhập **https://app.example.com**.
2. Bản ghi DNS của tổ chức trỏ tên này đến **tm-prod-app.trafficmanager.net**.
3. Recursive DNS resolver hỏi hệ thống DNS của Traffic Manager.
4. Traffic Manager xem routing method, các endpoint được bật và trạng thái monitoring để lựa chọn kết quả DNS.
5. Resolver lưu kết quả theo cơ chế cache/TTL và trả lại cho client.
6. Trình duyệt kết nối trực tiếp qua Internet đến endpoint được phân giải, ví dụ một Azure App Service.
7. Khi endpoint gặp lỗi, Traffic Manager có thể thay đổi **các câu trả lời DNS tiếp theo** theo chính sách.

Điểm mấu chốt: Traffic Manager điều khiển **địa chỉ mà DNS trả về**, không tự di chuyển phiên TCP/HTTPS đang mở và không giải mã lưu lượng ứng dụng.

### 2.1. Lợi ích của cách làm ở DNS

- Hỗ trợ các endpoint ở nhiều region, nhiều Azure subscription hoặc cả ngoài Azure khi chúng có địa chỉ công khai phù hợp.
- Không tạo thêm một chặng proxy trên đường truyền dữ liệu ứng dụng.
- Có thể quản lý ưu tiên dự phòng và một số kiểu phân bổ lưu lượng từ một cấu hình tập trung.
- Hoạt động với nhiều loại ứng dụng có thể truy cập qua DNS, miễn endpoint và cơ chế giám sát tương thích.

### 2.2. Giới hạn phải nhớ

- Tốc độ chuyển hướng chịu ảnh hưởng **DNS TTL, cache của recursive resolver và client**.
- Phiên đã kết nối không được Traffic Manager chuyển liền sang endpoint khác.
- Không cung cấp TLS termination, WAF, xử lý cookie, session affinity hoặc route theo HTTP path.
- Không làm dịch vụ chỉ có IP riêng trong VNet tự trở thành public endpoint.
- Không thay thế cơ chế đồng bộ dữ liệu, triển khai đa region và thiết kế chịu lỗi của ứng dụng.

Vì thế, Traffic Manager phù hợp để điều phối **điểm đến ở mức DNS**, nhưng một ứng dụng muốn chịu lỗi đa region còn cần cả lớp dữ liệu, xử lý phiên và khả năng hoạt động độc lập của từng region.

## 3. Phân biệt Traffic Manager với những dịch vụ cân bằng tải khác

Azure có nhiều lựa chọn phân phối ứng dụng. Dùng đúng dịch vụ dựa trên câu hỏi cần giải quyết:

| Dịch vụ | Tầng và chức năng chính | Trường hợp điển hình |
|---|---|---|
| **Azure Traffic Manager** | Định tuyến qua DNS đến các endpoint công khai | Chọn region/endpoint bằng ưu tiên, trọng số, vị trí hoặc độ trễ dự kiến |
| **Azure Front Door** | Dịch vụ phân phối ứng dụng toàn cầu ở HTTP/HTTPS, hoạt động như reverse proxy tại edge | Tăng tốc ứng dụng web, TLS termination, WAF và route L7 |
| **Azure Application Gateway** | Bộ cân bằng tải ứng dụng L7 ở phạm vi triển khai Azure, có thể tích hợp WAF | Route theo host/path, cân bằng HTTP/HTTPS cho workload |
| **Azure Load Balancer** | Cân bằng kết nối L4 TCP/UDP trong mô hình hỗ trợ | Phân phối lưu lượng đến VM hoặc dịch vụ backend theo giao thức L4 |

Ví dụ, nếu yêu cầu là “người dùng ở một khu vực sẽ được trả về endpoint ứng dụng khỏe nhất theo chính sách DNS”, Traffic Manager có thể phù hợp. Nếu yêu cầu là “đọc HTTP path rồi chuyển **/api** và **/images** sang các backend khác nhau”, cần một dịch vụ L7 như Front Door hoặc Application Gateway.

Có thể kết hợp chúng: Traffic Manager trỏ đến các endpoint mà phía sau đã có Application Gateway hoặc dịch vụ ứng dụng. Tuy nhiên, mỗi tầng thêm vào phải có nhiệm vụ rõ ràng, tránh tạo đường định tuyến khó giám sát.

## 4. Những thành phần cấu hình chính

### 4.1. Traffic Manager profile

**Profile** là tài nguyên quản lý routing method, tên DNS, endpoint monitoring và danh sách endpoint. Khi tạo profile, bạn chọn tên DNS duy nhất trong vùng **trafficmanager.net**.

Ví dụ:

- Tên profile: **tm-prod-app**.
- DNS name: **tm-prod-app.trafficmanager.net**.
- Routing method: **Priority**.
- DNS TTL: **60 giây**.
- Monitor: **HTTPS**, cổng **443**, đường dẫn **/health**.

Tên DNS nêu trên chỉ mang tính minh họa; prefix phải chưa được sử dụng trên dịch vụ.

### 4.2. Endpoint

Endpoint là đích mà Traffic Manager có thể trả về trong câu trả lời DNS. Một profile có thể chứa nhiều endpoint với trạng thái bật/tắt và tham số riêng theo routing method.

### 4.3. Routing method

Routing method quy định cách Traffic Manager chọn một hoặc nhiều endpoint khi có truy vấn DNS. Những phương pháp phổ biến gồm **Priority, Weighted, Performance, Geographic, MultiValue** và **Subnet**.

### 4.4. Health monitoring

Traffic Manager có thể chủ động thăm dò endpoint bằng HTTP, HTTPS hoặc TCP để phát hiện đích không sẵn sàng. Tình trạng do probe quan sát được ảnh hưởng đến việc chọn endpoint trong các truy vấn tiếp theo.

### 4.5. DNS TTL

**Time to Live (TTL)** là thời gian DNS answer được phép lưu trong cache theo tiêu chuẩn DNS. TTL ngắn giúp resolver có cơ hội hỏi lại sớm hơn, nhưng không biến failover thành tức thời.

## 5. Các loại endpoint

| Loại endpoint | Mô tả | Ví dụ |
|---|---|---|
| **Azure endpoint** | Tài nguyên Azure công khai thuộc loại được Traffic Manager hỗ trợ | Một Azure App Service hoặc Public IP resource được hỗ trợ |
| **External endpoint** | FQDN hoặc địa chỉ IP công khai của dịch vụ ngoài Azure hoặc endpoint không được khai báo như Azure endpoint | Ứng dụng trong trung tâm dữ liệu hoặc dịch vụ ở nhà cung cấp khác |
| **Nested endpoint** | Một Traffic Manager profile khác được dùng làm endpoint trong profile hiện tại | Profile toàn cầu chọn profile vùng hoặc profile dự phòng |

**Azure endpoint** thường được tham chiếu bằng resource ID của tài nguyên hỗ trợ; **external endpoint** có target dạng public DNS name hoặc public IP. Khi dùng external endpoint với phương thức **Performance**, phải khai báo **endpoint location** phù hợp để thuật toán có cơ sở đánh giá.

Endpoint phải thực sự truy cập được qua đường mạng cần thiết và trả lời health probe thích hợp. **Traffic Manager không dùng để trả IP riêng của Private Endpoint hoặc tạo đường truy cập đến một ứng dụng chỉ chạy nội bộ trong VNet.** Đối với truy cập private, cần giải pháp DNS/mạng riêng tương ứng.

### 5.1. Endpoint status và monitor status khác nhau

- **Endpoint status** phản ánh endpoint có được bật để tham gia điều phối hay không.
- **Monitor status** phản ánh tình trạng sức khỏe do dịch vụ theo dõi.

Một endpoint có thể được bật trong cấu hình nhưng monitor đánh giá là không khỏe. Ngược lại, một endpoint đã bị tắt theo chủ ý sẽ không được chọn cho lưu lượng dù ứng dụng ở phía sau vẫn hoạt động.

## 6. Sáu phương pháp định tuyến DNS

### 6.1. Priority — ưu tiên chính và dự phòng

Phương pháp **Priority** chọn endpoint khỏe có thứ tự ưu tiên cao nhất. Giá trị ưu tiên **càng nhỏ thì thứ tự càng cao**.

Ví dụ:

| Endpoint | Priority | Ý nghĩa |
|---|---:|---|
| App tại Southeast Asia | 1 | Primary |
| App tại East Asia | 2 | Standby |

Trong trạng thái bình thường, DNS được điều phối về endpoint Priority 1. Khi endpoint đó bị đánh giá không khỏe, Traffic Manager có thể trả về endpoint Priority 2.

Phù hợp khi dữ liệu hoặc chi phí yêu cầu kiến trúc **active-passive** và doanh nghiệp muốn kiểm soát rõ đâu là region chính. Nhưng cần chuẩn bị region dự phòng hoạt động đầy đủ, không chỉ dựng một endpoint rỗng.

### 6.2. Weighted — phân chia tương đối bằng trọng số

Phương pháp **Weighted** chọn endpoint dựa trên trọng số cấu hình.

Ví dụ:

| Endpoint | Weight | Kỳ vọng phân bổ tương đối |
|---|---:|---|
| App phiên bản A | 80 | Xấp xỉ 80% quyết định DNS trong tập điều kiện phù hợp |
| App phiên bản B | 20 | Xấp xỉ 20% quyết định DNS trong tập điều kiện phù hợp |

**Không được hiểu bảng này là chính xác 80% và 20% HTTP requests.** Một recursive resolver có thể cache kết quả cho rất nhiều client và người dùng gửi số lượng request khác nhau. Trọng số ảnh hưởng lựa chọn trong cơ chế DNS, còn lượng request thực tế phụ thuộc cache, số client, thời lượng phiên và lưu lượng ứng dụng.

Phù hợp để phân bổ DNS theo tỷ trọng hoặc di chuyển một phần lưu lượng từng bước. Với canary release cần kiểm soát chính xác theo request/user, có thể cần giải pháp ở L7.

### 6.3. Performance — chọn điểm có độ trễ mạng dự kiến thấp hơn

Traffic Manager sử dụng thông tin về độ trễ mạng giữa các khu vực và endpoint để chọn đích phù hợp cho vị trí được suy ra từ truy vấn DNS. Phương pháp này hướng đến trải nghiệm người dùng tốt hơn khi ứng dụng chạy đa region.

Ví dụ: người dùng Đông Nam Á thường được định tuyến đến region thuận lợi theo dữ liệu độ trễ mạng, trong khi người dùng ở khu vực khác có thể nhận endpoint khác.

Lưu ý:

- Đây là **đánh giá dự kiến dựa trên thông tin mạng**, không phải phép đo RTT thực tế cho từng HTTP request.
- Vị trí client có thể được suy ra từ recursive resolver; **EDNS Client Subnet** có thể cải thiện độ chính xác khi được hỗ trợ.
- Cấu hình mạng, DNS resolver, VPN hoặc các đường truyền Internet khác nhau có thể làm lựa chọn không đúng với vị trí vật lý của từng người dùng.
- Endpoint external cần thông tin vị trí thích hợp.

Nếu mục tiêu là cải thiện trải nghiệm đa quốc gia, hãy đo thực tế từ mạng của người dùng và cân nhắc CDN, edge hoặc các dịch vụ L7 khi cần.

### 6.4. Geographic — phân phối theo vùng địa lý đã ánh xạ

**Geographic** cho phép ánh xạ người dùng theo quốc gia, vùng hoặc khu vực địa lý đã được dịch vụ hỗ trợ tới endpoint.

Ví dụ:

| Nhóm địa lý trong thiết kế | Endpoint được chỉ định |
|---|---|
| Nhóm thị trường tại châu Á | App Asia |
| Nhóm thị trường tại châu Âu | App Europe |

Phù hợp với nhu cầu phân tách thị trường hoặc trải nghiệm theo khu vực. Tuy nhiên, **định tuyến theo DNS không phải bảo đảm tuyệt đối về vị trí thực của người dùng hay nơi dữ liệu được lưu trữ**.

Một điểm quan trọng: Geographic ưu tiên tuân thủ ánh xạ khu vực. Nếu endpoint được gán cho một khu vực bị lỗi, Traffic Manager không tự động chuyển toàn bộ lưu lượng khu vực đó sang endpoint của khu vực khác theo ý muốn của doanh nghiệp. Nếu cần dự phòng trong cùng một địa lý, hãy cân nhắc các profile lồng nhau và kiểm thử đúng hành vi.

### 6.5. MultiValue — trả về nhiều địa chỉ

**MultiValue** có thể trả về nhiều endpoint khỏe trong một phản hồi DNS khi endpoint và cấu hình đáp ứng yêu cầu của phương pháp. Trường hợp sử dụng thường liên quan các endpoint external có địa chỉ IPv4/IPv6 hợp lệ thay vì những đích chỉ có hostname.

Ứng dụng hoặc client nhận một tập địa chỉ và tự xử lý việc lựa chọn/kết nối tiếp theo. Cách này khác với Weighted, vốn điều phối lựa chọn DNS dựa trên tỷ trọng.

Trước khi dùng MultiValue, kiểm tra kỹ giới hạn đối tượng endpoint và hành vi của DNS client vì không phải tất cả profile hoặc backend đều phù hợp.

### 6.6. Subnet — ánh xạ theo dải IP nguồn

Phương pháp **Subnet** cho phép ánh xạ các dải địa chỉ IP của client được xác định từ truy vấn DNS đến những endpoint tương ứng. Ví dụ, tổ chức muốn các yêu cầu phát sinh từ một số dải IP của nhà cung cấp hoặc mạng đối tác ưu tiên endpoint riêng.

Cần chú ý:

- DNS server có thể thấy địa chỉ của recursive resolver hoặc thông tin client subnet được cung cấp qua EDNS Client Subnet.
- Một máy khách dùng DNS resolver trung gian có thể được nhận diện khác với IP truy cập HTTP trực tiếp.
- Đây không phải là cơ chế xác thực người dùng, firewall hay bảo vệ nội dung theo IP.

**Kết luận lựa chọn phương pháp:** chọn **Priority** cho chính–dự phòng, **Weighted** cho tỷ lệ DNS, **Performance** cho điểm đến dự kiến có độ trễ tốt, **Geographic** cho ánh xạ khu vực, **MultiValue** cho nhiều IP hợp lệ và **Subnet** cho ánh xạ nguồn theo dải IP.

## 7. Thiết kế hai region: ví dụ cho ứng dụng đặt ở châu Á

Giả sử ứng dụng thương mại điện tử có hai bản triển khai độc lập:

- **Endpoint A:** app-sea.example.net, đặt tại Southeast Asia.
- **Endpoint B:** app-ea.example.net, đặt tại East Asia.
- **Tên miền cho khách hàng:** app.example.com.
- **Traffic Manager profile:** tm-prod-app.trafficmanager.net.

Các miền **example.com** và **example.net** ở đây chỉ là tên minh họa dành cho tài liệu; khi thực hành phải dùng domain hoặc endpoint thật có quyền quản lý.

~~~mermaid
flowchart TD
    U[Khách hàng mở app.example.com] --> DNS[Recursive DNS]
    DNS --> TM[Traffic Manager: tm-prod-app.trafficmanager.net]
    TM -->|Priority 1, healthy| A[App Southeast Asia]
    TM -->|Priority 2 khi A unhealthy| B[App East Asia]
    U -->|HTTPS trực tiếp theo DNS answer| A
    U -.->|HTTPS sau DNS failover| B
    A --> DA[(Dữ liệu vùng A)]
    B --> DB[(Dữ liệu vùng B)]
    DA <-.->|Đồng bộ dữ liệu theo kiến trúc| DB
~~~

Hình trên mô tả hai luồng truy cập ở những thời điểm khác nhau; không có nghĩa Traffic Manager sao chép session hay database.

**Điều kiện để failover có ích:**

1. Endpoint A và B đều có thể phục vụ hostname công khai cần thiết.
2. Cả hai đều được phép nhận traffic production và được triển khai phiên bản tương thích.
3. Dữ liệu được sao chép/khôi phục theo thiết kế ứng dụng, có RPO/RTO đã xác định.
4. Health endpoint phát hiện được những lỗi khiến bản ứng dụng không còn phục vụ hợp lệ.
5. Custom domain và chứng chỉ TLS hợp lệ tại cả hai endpoint.
6. Ứng dụng tránh lưu session chỉ trong bộ nhớ của một instance/region hoặc có cơ chế phục hồi hợp lý.
7. Người vận hành đo được việc chuyển tuyến thực tế với DNS cache và phiên hiện hữu.

Nếu chỉ có bản ứng dụng dự phòng nhưng dữ liệu không sẵn sàng, việc DNS chuyển sang region B vẫn có thể làm người dùng gặp lỗi.

## 8. Health probe hoạt động như thế nào?

Traffic Manager định kỳ kiểm tra endpoint bằng giao thức đã cấu hình. Thông tin thường cần chọn:

| Thiết lập | Chức năng | Ví dụ |
|---|---|---|
| **Protocol** | Loại kết nối để kiểm tra | HTTPS |
| **Port** | Cổng của ứng dụng | 443 |
| **Path** | Đường dẫn HTTP/HTTPS cần trả lời thành công | /health |
| **Probing interval** | Khoảng thời gian kiểm tra | Theo chế độ và tính năng hỗ trợ |
| **Timeout** | Giới hạn chờ phản hồi của probe | Theo giá trị cấu hình |
| **Tolerated failures** | Ngưỡng số lần kiểm tra thất bại trước khi coi endpoint không khỏe | Theo chính sách độ nhạy |
| **Expected status codes** | Những HTTP status code được chấp nhận nếu tính năng được cấu hình | Ví dụ, HTTP 200 |

### 8.1. Thiết kế health endpoint

Endpoint **/health** nên trả về phản hồi ngắn, ổn định và đại diện cho khả năng ứng dụng nhận yêu cầu mới.

Ví dụ ý nghĩa:

- HTTP 200: ứng dụng sẵn sàng nhận lưu lượng theo tiêu chí giám sát.
- HTTP 503: ứng dụng không nên nhận lưu lượng mới do thiếu phụ thuộc quan trọng.

Một trang HTML bình thường luôn trả HTTP 200 có thể khiến Traffic Manager tiếp tục xem endpoint là khỏe dù chức năng thanh toán hoặc đọc dữ liệu đã lỗi. Mặt khác, nếu health endpoint kiểm tra quá nhiều dịch vụ phụ không cần thiết, một lỗi nhỏ có thể dẫn đến failover không mong muốn.

Hãy phân biệt:

- **Liveness:** tiến trình còn hoạt động.
- **Readiness:** điểm triển khai có đủ điều kiện nhận lưu lượng thực tế.
- **Synthetic business check:** một kiểm tra sâu mô phỏng luồng nghiệp vụ quan trọng.

Traffic Manager chỉ có thể đánh giá dựa trên loại probe và tiêu chí được cấu hình. Đội ứng dụng chịu trách nhiệm thiết kế đường dẫn/logic phù hợp.

### 8.2. HTTPS probe và chứng chỉ

Nếu dùng HTTPS, endpoint phải có TLS và host/certificate phù hợp với kiến trúc. Giao thức kiểm tra không đồng nghĩa Traffic Manager sẽ trở thành điểm TLS termination cho người dùng.

Cần kiểm tra hostname và HTTP Host header được dùng cho health probe, đặc biệt khi backend phục vụ nhiều domain trên cùng một endpoint. Một số cấu hình monitoring cho phép chỉ định custom header; hãy xác nhận khả năng và giá trị mà profile đang dùng hỗ trợ.

### 8.3. Các trạng thái giám sát

Giao diện có thể hiển thị endpoint là **Online, Degraded, Disabled, CheckingEndpoint, Stopped** hoặc trạng thái phù hợp khác theo tình huống.

Đừng kết luận chỉ dựa trên trạng thái profile. Hãy xem **endpoint status**, **monitor status**, đường dẫn probe, response code và log ứng dụng. Nếu toàn bộ endpoint đều không khỏe, cần hiểu hành vi routing và thiết kế ứng dụng trong tình huống đó; Traffic Manager không thể tạo ra một bản ứng dụng khỏe chỉ bằng đổi DNS.

## 9. DNS TTL và giới hạn của thời gian failover

Đây là phần quan trọng nhất khi đánh giá khả năng phục hồi.

Giả sử profile có TTL **60 giây**. Khi endpoint A hỏng, Traffic Manager cần thời gian để probe phát hiện lỗi, thay đổi trạng thái và trả kết quả DNS mới. Nhưng một số recursive DNS resolver hoặc ứng dụng vẫn có thể tiếp tục sử dụng địa chỉ của A đang được cache.

Mô hình thời gian khái niệm:

~~~text
t0: Endpoint A ngừng phục vụ
    |
    +-- Health probes xác định A không khỏe
    |
    +-- Traffic Manager bắt đầu trả lời endpoint B cho DNS queries mới
    |
    +-- Recursive resolver / client cache hết hạn và hỏi lại
    |
    +-- Những kết nối mới của client chuyển dần tới B
~~~

**TTL 60 giây không bảo đảm người dùng được chuyển hết sang B trong đúng 60 giây.** TTL chỉ là một thành phần. Các yếu tố khác gồm:

- Probe interval, timeout và số lần lỗi được chấp nhận.
- Bộ nhớ cache tại DNS resolver, hệ điều hành, ứng dụng hoặc thư viện DNS.
- Hành vi resolver tuân thủ hoặc điều chỉnh TTL.
- Các phiên TCP, TLS, WebSocket hoặc keep-alive đã mở.
- DNS lookup mới có được thực hiện khi client thử kết nối lại không.

TTL thấp thường giảm thời gian cache theo thiết kế nhưng có thể tăng số truy vấn DNS và chi phí. TTL cao giảm tần suất hỏi lại nhưng làm quá trình chuyển endpoint chậm hơn.

**RTO của ứng dụng phải được đo bằng bài kiểm thử failover thực tế**, không tính đơn thuần từ TTL. Traffic Manager không bảo đảm failover tức thời cho tất cả client.

## 10. Chuẩn bị trước khi tạo Traffic Manager profile

Trước khi cấu hình, cần:

1. **Có từ hai endpoint public hoạt động** nếu mục tiêu là thử failover; mỗi endpoint phải trả lời HTTPS hoặc giao thức được giám sát.
2. **Có quyền Azure** để tạo profile và endpoint ở resource group/subscription.
3. **Chọn routing method** theo yêu cầu: ưu tiên dự phòng, phân bố tỷ lệ hoặc tối ưu điểm đến.
4. **Định nghĩa readiness/health path** thống nhất và kiểm tra từng endpoint trực tiếp.
5. **Xác nhận tên miền** mà tổ chức sở hữu và có quyền sửa DNS records.
6. **Cấu hình TLS và custom host** trên tất cả backend sẽ phục vụ hostname chung.
7. **Chuẩn bị logging và cảnh báo** cho cả ứng dụng, DNS routing và trạng thái endpoint.
8. **Ước tính chi phí** theo profile, số endpoint/monitoring và số lượng DNS queries.

Khi ứng dụng xử lý dữ liệu cá nhân hoặc có yêu cầu lưu trú dữ liệu, cần đánh giá cả region của backend, nơi lưu trữ/sao chép dữ liệu và chính sách của từng dịch vụ. Chọn Geographic không tự thực thi yêu cầu pháp lý về dữ liệu.

## 11. Tạo profile bằng Azure Portal

Ví dụ dưới đây dùng **Priority** để triển khai primary/standby.

1. Trong **Azure Portal**, tìm **Traffic Manager profiles** và chọn tạo profile mới.
2. Nhập tên profile, ví dụ **tm-prod-app**; chọn subscription và resource group phù hợp.
3. Đặt routing method thành **Priority**.
4. Chọn tạo profile. Kiểm tra DNS name được cấp dưới **trafficmanager.net**.
5. Mở phần **Configuration**, đặt DNS TTL mong muốn, ví dụ **60 giây**.
6. Trong phần endpoint monitoring, chọn **HTTPS**, **Port 443**, **Path /health**, cùng các thiết lập probe/expected response phù hợp.
7. Mở mục **Endpoints**, thêm endpoint A với **Priority 1**.
8. Thêm endpoint B với **Priority 2**.
9. Xác nhận các endpoint được bật, target đúng và monitoring đã chuyển sang trạng thái phù hợp.
10. Truy vấn tên **tm-prod-app.trafficmanager.net** để kiểm tra kết quả DNS, sau đó mới gắn domain thật.

Khi tạo endpoint, có thể chọn **Azure endpoint** nếu tài nguyên Azure thuộc loại được hỗ trợ hoặc **External endpoint** nếu đích là FQDN công khai. Các ví dụ endpoint dạng **app-sea.example.net** trong bài chỉ dùng để minh họa; phải thay bằng đích thật khi chạy thử.

Không nên chuyển DNS sản xuất sang profile trước khi health probe, TLS, đường truyền và phương án rollback đã được kiểm chứng.

## 12. Thực hiện bằng Azure CLI

Azure CLI cung cấp các lệnh quản lý Traffic Manager. Ví dụ bên dưới minh họa mô hình dùng **externalEndpoints** trỏ tới hai hostname public đã hoạt động. Chạy trên môi trường thử nghiệm được phép và thay toàn bộ giá trị placeholder.

### 12.1. Đăng nhập và tạo resource group

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-traffic-lab \
  --location southeastasia
~~~

Traffic Manager là dịch vụ định tuyến DNS toàn cầu; location của resource group dùng cho metadata quản lý nhóm tài nguyên, không phải nơi mọi DNS query phải được xử lý.

### 12.2. Tạo Traffic Manager profile

~~~bash
az network traffic-manager profile create \
  --resource-group rg-traffic-lab \
  --name tm-prod-app \
  --routing-method Priority \
  --unique-dns-name tm-prod-app \
  --ttl 60 \
  --protocol HTTPS \
  --port 443 \
  --path /health
~~~

Prefix **tm-prod-app** phải là tên DNS duy nhất có thể sử dụng trên Azure Traffic Manager. Trong bài thực hành thật, nên đặt prefix riêng để tránh trùng với profile của người khác.

### 12.3. Tạo hai endpoint external

~~~bash
az network traffic-manager endpoint create \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --name app-primary \
  --type externalEndpoints \
  --target app-sea.example.net \
  --priority 1

az network traffic-manager endpoint create \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --name app-secondary \
  --type externalEndpoints \
  --target app-ea.example.net \
  --priority 2
~~~

Nếu backend là một tài nguyên Azure được hỗ trợ, có thể dùng kiểu **azureEndpoints** và target resource ID theo tham số tương ứng, thay vì khai báo hostname như external endpoint. Khi dùng Performance với external endpoint, cần cung cấp location được hỗ trợ để định tuyến.

### 12.4. Kiểm tra cấu hình và endpoint

~~~bash
az network traffic-manager profile show \
  --resource-group rg-traffic-lab \
  --name tm-prod-app \
  --output json

az network traffic-manager endpoint list \
  --resource-group rg-traffic-lab \
  --profile-name tm-prod-app \
  --output table
~~~

Kết quả cần kiểm tra gồm DNS name, routing method, TTL, protocol/port/path, endpoint priority, target, endpoint status và monitor status. Nếu endpoint chưa được đánh giá Online, hãy kiểm tra app/health URL, DNS và firewall trước khi chuyển sang production.

**Lưu ý:** domain example.net không có endpoint thật trong lab mẫu. Những lệnh tạo profile/endpoint chỉ có giá trị thực hành khi bạn đã thay chúng bằng hostname công khai thực sự có ứng dụng hoạt động.

## 13. Dùng tên miền riêng với Traffic Manager

Giả sử tổ chức sở hữu **example.com** và muốn mọi người truy cập:

**https://app.example.com**

Một cấu hình DNS mẫu tại DNS provider:

~~~dns
app.example.com.  CNAME  tm-prod-app.trafficmanager.net.
~~~

Sau thay đổi, luồng phân giải có thể là:

~~~text
app.example.com
    |
    +-- CNAME --> tm-prod-app.trafficmanager.net
                      |
                      +-- Traffic Manager trả về target endpoint đã chọn
                            |
                            +-- DNS resolver truy tiếp tới IP nếu cần
~~~

### 13.1. Root domain và subdomain

Ở subdomain như **app.example.com**, CNAME thường là lựa chọn đơn giản. Tại **apex/root domain** như **example.com**, nhiều hệ thống DNS không cho tạo CNAME tiêu chuẩn do xung đột các record khác. Khi cần trỏ apex, hãy kiểm tra tính năng **alias/ANAME/ALIAS** tương ứng của nhà cung cấp DNS. Azure DNS có khả năng alias record trong những trường hợp được hỗ trợ.

Không giả định mọi DNS provider hỗ trợ cùng một kiểu alias.

### 13.2. HTTPS và chứng chỉ TLS

Traffic Manager chỉ điều phối DNS; trình duyệt vẫn mở kết nối TLS đến **endpoint được chọn**. Vì người dùng nhập **app.example.com**, backend cần được cấu hình để phục vụ hostname đó và có chứng chỉ TLS hợp lệ cho hostname phù hợp.

Các bước kiểm tra:

1. Custom domain được gán/được chấp nhận tại từng backend.
2. Chứng chỉ TLS hợp lệ cho tên truy cập và được gia hạn đúng hạn.
3. Backend xử lý đúng HTTP Host header và SNI.
4. Không có redirect loop giữa hostname mặc định và custom domain.
5. Cả primary và secondary phục vụ cùng đường dẫn ứng dụng và health probe.

Nếu endpoint A có chứng chỉ cho app.example.com nhưng endpoint B chỉ có chứng chỉ cho tên mặc định của dịch vụ, DNS failover sang B có thể gây lỗi TLS dù endpoint B vẫn Online trong điều kiện probe nhất định.

## 14. Kiểm tra DNS và mô phỏng failover

### 14.1. Truy vấn DNS

Trên máy có công cụ DNS:

~~~bash
nslookup app.example.com

dig app.example.com CNAME
dig app.example.com A
dig tm-prod-app.trafficmanager.net
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName app.example.com
Resolve-DnsName tm-prod-app.trafficmanager.net
~~~

Kết quả cần đánh giá:

- CNAME có trỏ đúng Traffic Manager profile không?
- Profile có trả về endpoint đang mong đợi không?
- DNS resolver có còn cache kết quả trước đó không?
- IP/FQDN nhận được có tương ứng với backend thực tế không?

Không dùng kết quả của **một máy và một lần truy vấn** để kết luận toàn bộ người dùng đang đến cùng endpoint. Recursive resolver, vị trí địa lý, phương pháp định tuyến và cache có thể khiến kết quả khác nhau.

### 14.2. Kiểm thử Priority failover

Trong sandbox, quy trình có thể như sau:

1. Cấu hình A Priority 1 và B Priority 2; cả hai phải hoạt động.
2. Xác nhận DNS đang chọn A khi A khỏe.
3. Tạo sự cố có kiểm soát trên **health path của A** hoặc làm endpoint A không đạt readiness, nhưng chỉ trong môi trường thử nghiệm.
4. Theo dõi monitor status của A chuyển sang không khỏe theo ngưỡng cấu hình.
5. Thực hiện những DNS query mới để kiểm tra câu trả lời chuyển sang B.
6. Quan sát client còn dùng kết quả cũ trong cache và thời gian truy cập phục hồi.
7. Khôi phục A, kiểm tra trạng thái Online và hành vi trả endpoint theo Priority sau khi có thể chọn lại.
8. Ghi thời gian từ lúc A lỗi đến lúc phát hiện, DNS đổi, và người dùng thực tế truy cập được B.

Trong môi trường production, cần theo quy trình diễn tập và tránh cố ý làm hỏng ứng dụng thật khi chưa có kế hoạch.

### 14.3. Phân biệt những mốc thời gian

- **Phát hiện:** thời gian probe xác nhận endpoint không khỏe.
- **Đổi câu trả lời DNS:** thời điểm Traffic Manager bắt đầu trả endpoint thay thế cho query phù hợp.
- **Thay đổi tại resolver/client:** thời điểm bản cache hết hạn hoặc bị làm mới.
- **Phục hồi ứng dụng:** thời điểm người dùng hoàn tất tác vụ nghiệp vụ tại endpoint B.

Các mốc này có thể cách nhau đáng kể. Đo RTO bằng trải nghiệm ứng dụng thực tế và ghi lại phương pháp đo.

## 15. Weighted routing cho canary hoặc chuyển dịch dần

Ví dụ doanh nghiệp chuẩn bị chuyển bản ứng dụng từ **v1** sang **v2**:

1. Triển khai v2 độc lập và kiểm tra endpoint/health.
2. Cấu hình Weighted cho hai endpoint, đặt trọng số thiên về v1.
3. Theo dõi error rate, latency và metrics ứng dụng; không chỉ nhìn DNS query count.
4. Tăng trọng số của v2 từng bước khi các tiêu chí đạt yêu cầu.
5. Chuẩn bị khả năng quay lại v1 nếu lỗi tăng.

Ví dụ các mức **90/10 → 70/30 → 50/50 → 0/100** biểu diễn mục tiêu tương đối cho quyết định DNS, không bảo đảm chính xác tỷ lệ HTTP request hay số người dùng. Cache và session dài có thể làm tỷ lệ thật chênh lệch đáng kể.

Nếu cần chia traffic theo user ID, cookie, header hoặc request path, hãy sử dụng tầng ứng dụng/L7 hoặc cơ chế phát hành phù hợp thay vì dựa vào Weighted của Traffic Manager.

## 16. Geographic routing và yêu cầu dữ liệu

Một tổ chức có khách hàng ở nhiều vùng có thể muốn ánh xạ khách hàng châu Âu tới ứng dụng châu Âu, khách hàng châu Á tới ứng dụng châu Á.

Geographic routing là một phần của thiết kế trải nghiệm hoặc điều phối DNS, nhưng **không tự chứng minh tuân thủ dữ liệu**. Các yêu cầu lưu trú dữ liệu cần xem xét:

- Dữ liệu của từng endpoint được lưu ở đâu.
- Database, backup, replication và log có được truyền sang region khác không.
- API phụ trợ, hàng đợi và các dịch vụ toàn cầu xử lý dữ liệu ở đâu.
- Client có thể sử dụng DNS resolver/VPN khiến hệ thống suy luận vị trí khác thực tế hay không.
- Khi endpoint trong khu vực lỗi, hệ thống có được phép chuyển sang region khác không.

Nếu có ràng buộc không được chuyển người dùng sang vùng khác, hãy thiết kế dự phòng **trong cùng vùng được phép**, có thể bằng nested profile với điều kiện phù hợp. Nếu được phép failover ra ngoài khu vực, phải có quyết định pháp lý và vận hành rõ ràng.

## 17. Nested profiles cho chính sách định tuyến nhiều tầng

Một Traffic Manager profile có thể tham chiếu tới profile khác bằng **nested endpoint**. Điều này cho phép kết hợp các mục tiêu định tuyến thành nhiều lớp.

Ví dụ:

~~~mermaid
flowchart TD
    ROOT[Global profile: Geographic] --> ASIA[Asia profile: Priority]
    ROOT --> EU[Europe profile: Performance]
    ASIA --> A1[App Asia primary]
    ASIA --> A2[App Asia secondary]
    EU --> E1[App Europe region 1]
    EU --> E2[App Europe region 2]
~~~

Thiết kế có thể phân nhóm người dùng theo vùng địa lý ở profile ngoài, rồi dùng Priority/Performance bên trong vùng đó để chọn endpoint phù hợp.

Đánh đổi là thêm profile, cấu hình health, DNS behavior và chi phí vận hành. Cần kiểm tra:

- Cách profile cha xác định tính sẵn sàng của nested endpoint.
- Phạm vi failover có được phép theo quy tắc dữ liệu không.
- TTL và hành vi cache ở từng lớp.
- Đường truy cập thực tế sau khi một hoặc nhiều endpoint bị lỗi.
- Giới hạn nesting và tính năng của Traffic Manager tại thời điểm thiết kế.

Không giả định nested profile tự sửa mọi trường hợp chuyển vùng hoặc dữ liệu dự phòng.

## 18. Bảo mật mô hình Traffic Manager

Vì Traffic Manager chỉ giải quyết DNS, cần bố trí bảo mật ở các lớp khác:

**DNS và quyền quản trị:**

- Chỉ cấp quyền Azure RBAC cần thiết cho người tạo/sửa profile và endpoint.
- Ghi nhận thay đổi profile, DNS zone và custom domain.
- Bảo vệ tài khoản quản trị bằng Microsoft Entra ID, MFA/PIM khi phù hợp.
- Giữ quyền quản lý domain/DNS của tổ chức trong phạm vi được kiểm soát.

**Endpoint và ứng dụng:**

- Cấu hình HTTPS tại từng backend, không dựa vào Traffic Manager để mã hóa lưu lượng.
- Sử dụng WAF hoặc dịch vụ ứng dụng phù hợp khi cần bảo vệ HTTP.
- Cấu hình firewall/WAF để health probe của Traffic Manager được xử lý đúng; nếu hạn chế nguồn, hãy dùng thông tin probe IP hoặc service tags được Azure công bố và cập nhật theo hướng dẫn hiện hành.
- Bảo vệ origin khỏi truy cập trái phép theo thiết kế ứng dụng; DNS routing không tự ẩn địa chỉ backend.
- Đặt authentication/authorization của ứng dụng tại đúng lớp.

**Dữ liệu và khả dụng:**

- Sao chép hoặc phục hồi dữ liệu theo quy tắc nhất quán, có RPO/RTO.
- Bảo đảm backend dự phòng được cập nhật, vá lỗi và giám sát tương tự backend chính.
- Kiểm tra session handling, cache, upload và giao dịch khi người dùng chuyển endpoint.

Khi health probe bị firewall chặn, Traffic Manager có thể đánh giá endpoint không khỏe dù ứng dụng vẫn phục vụ người dùng khác. Phải phân biệt lỗi monitor với lỗi ứng dụng thực tế.

## 19. Giám sát, cảnh báo và vận hành

Một hệ thống đa endpoint nên giám sát cả **Traffic Manager**, **backend** và **DNS/custom domain**.

| Lớp | Điều cần theo dõi |
|---|---|
| Traffic Manager profile | Routing method, TTL, cấu hình monitor, thay đổi endpoint |
| Endpoint health | Online/Degraded/Disabled và thời điểm thay đổi |
| DNS | Kết quả phân giải ở nhiều địa điểm, DNS query volume, cache behavior |
| Backend | HTTP error rate, latency, CPU, số kết nối, lỗi dependency |
| TLS/domain | Hiệu lực chứng chỉ, custom hostname, DNS record |
| Quản trị | Azure Activity Log, lịch sử thay đổi cấu hình |
| Chi phí | Số lượng profile/endpoint, truy vấn DNS, chi phí dịch vụ liên quan |

Có thể sử dụng Azure Monitor metrics và alerts theo những metric mà Traffic Manager cung cấp, kết hợp application monitoring của từng backend. Đối với kết quả failover, một probe từ bên ngoài ở nhiều vị trí thường có ích vì nó đo được cả DNS lẫn khả năng phục vụ HTTP/HTTPS.

Một chính sách cảnh báo có thể yêu cầu:

- Endpoint primary bị đánh giá không khỏe liên tục.
- Không còn endpoint khỏe đáp ứng routing method.
- Error rate ứng dụng tại backend tăng sau khi traffic chuyển.
- Chứng chỉ TLS sắp hết hạn.
- Cấu hình endpoint hoặc custom DNS thay đổi ngoài lịch bảo trì.

Không giả định số truy vấn DNS chính là số HTTP requests. Một resolver có thể phục vụ nhiều client từ cache mà không phát sinh truy vấn mới đến Traffic Manager cho từng request.

## 20. Xử lý lỗi thường gặp

### 20.1. DNS không trả về profile mong muốn

Kiểm tra CNAME hoặc alias record, tên profile có đúng không, DNS zone được phân quyền đúng hay chưa, và TTL/cache. Dùng cả resolver mặc định và resolver khác khi điều tra; không suy luận lỗi từ một kết quả duy nhất.

### 20.2. Profile trả về endpoint đã ngừng hoạt động

Kiểm tra monitor protocol, port, path, trạng thái Online/Degraded, timeout và tolerated failures. Endpoint có thể vẫn trả 200 tại **/health** dù nghiệp vụ thật lỗi. Cũng có thể cached DNS answer còn trỏ tới endpoint cũ.

### 20.3. Endpoint bị đánh giá Degraded dù website mở được

Kiểm tra firewall/WAF chặn monitoring probes, URL path sai, HTTP status code, yêu cầu Host header, cấu hình HTTPS hoặc redirect loop. Đối chiếu log request của health endpoint để xem traffic probe có tới hay không.

### 20.4. Failover hoạt động trên máy thử nhưng người dùng còn bị lỗi

DNS resolver/client cache và kết nối còn mở có thể giữ đích cũ. Backend thứ hai cũng có thể thiếu session, dữ liệu hoặc TLS certificate. Kiểm tra DNS response mới, kết nối TCP/HTTPS thật và các tác vụ nghiệp vụ, thay vì chỉ xem profile status.

### 20.5. HTTPS lỗi sau khi chuyển region

Đảm bảo **app.example.com** đã được cấu hình tại cả hai backend và certificate hợp lệ ở mỗi điểm. Nếu endpoint dùng một hostname khác trong quá trình health monitoring, kiểm tra sự khác biệt giữa probe và truy cập thật.

### 20.6. Phân phối Weighted khác tỷ lệ mong muốn

Kiểm tra DNS cache, lượng client sau mỗi resolver, số request trong mỗi session, khoảng thời gian quan sát và endpoint health. Weighted điều phối theo DNS, không cân từng HTTP request.

### 20.7. Người dùng nhận endpoint của region không mong đợi

Với Performance, xem vị trí recursive resolver, EDNS Client Subnet, dữ liệu độ trễ mạng và region location của external endpoint. Với Geographic/Subnet, kiểm tra mapping và cách dịch vụ nhận diện nguồn DNS query.

### 20.8. Không thể dùng Traffic Manager cho backend private

Traffic Manager cần endpoint có khả năng giải quyết/truy cập theo mô hình public được hỗ trợ. Nếu backend chỉ có private IP hoặc private endpoint trong VNet, cần thiết kế DNS riêng, ingress phù hợp hoặc dịch vụ gateway/L7 với khả năng kết nối private theo yêu cầu.

## 21. Kiểm soát chi phí và rủi ro vận hành

Chi phí Traffic Manager có thể phụ thuộc số DNS queries, số endpoint và mô hình health monitoring/tính năng theo bảng giá hiện hành. Các endpoint backend, băng thông, hệ thống dữ liệu, Azure Monitor và dịch vụ bảo mật khác có chi phí riêng.

Khi thiết kế, cần cân nhắc:

- TTL quá ngắn làm resolver hỏi lại thường xuyên hơn, có thể tăng lượng DNS queries.
- Nhiều endpoint và profile lồng nhau làm tăng khối lượng cấu hình, monitoring và chi phí.
- Region dự phòng cần đủ năng lực phục vụ, vì khi failover toàn bộ tải có thể dồn sang endpoint còn lại.
- Bản sao dữ liệu và băng thông liên region có thể chiếm phần chi phí lớn hơn bản thân DNS routing.
- Việc lạm dụng health probes quá sâu có thể gây tải không cần thiết lên backend.

Ước lượng bằng Azure Pricing Calculator và kiểm tra hóa đơn thực tế trong Azure Cost Management sau giai đoạn thử nghiệm. Không sử dụng một cấu hình chỉ vì chi phí DNS thấp nếu hệ thống dự phòng không đủ năng lực phục vụ.

## 22. Bài thực hành: primary/secondary với Priority routing

**Bối cảnh:** bạn có hai web endpoints công khai trong môi trường lab; cả hai đều trả HTTP 200 tại **/health** và phục vụ một trang có nội dung dễ nhận biết A/B.

**Yêu cầu chuẩn bị:** Azure subscription được phép tạo Traffic Manager, quyền cập nhật DNS nếu thử custom domain, hai backend public có TLS phù hợp và môi trường có thể gây lỗi thử nghiệm.

### Phần A — Thiết kế

1. Chọn tên profile duy nhất và tạo bảng endpoint A/B.
2. Chọn Priority 1 cho A, Priority 2 cho B, TTL 60 giây, health probe HTTPS 443 **/health**.
3. Xác định cách ứng dụng B tiếp nhận yêu cầu khi A lỗi; kiểm tra dữ liệu, session và domain.
4. Ghi lại kỳ vọng: bình thường A được chọn; khi A không khỏe, câu trả lời DNS mới chuyển về B.

### Phần B — Cấu hình

1. Tạo Traffic Manager profile.
2. Thêm hai endpoint public theo Priority.
3. Kiểm tra monitor status từng endpoint.
4. Dùng tên **trafficmanager.net** để kiểm tra giải đáp DNS.
5. Nếu đã chuẩn bị hostname và TLS ở cả hai backend, trỏ custom domain bằng CNAME phù hợp.

### Phần C — Thử sự cố

1. Truy vấn DNS nhiều lần với thời gian ghi nhận.
2. Kiểm tra ứng dụng A hoạt động và health trả thành công.
3. Trong lab, cố ý làm health endpoint A không đạt điều kiện đã đặt.
4. Theo dõi A chuyển không khỏe và các query DNS mới lựa chọn B.
5. Từ máy thử, đo thời gian để HTTPS thực sự phục vụ từ B.
6. Khôi phục A, quan sát A Online và routing quay về primary theo cấu hình Priority.
7. Ghi lại độ trễ phát hiện, khoảng thời gian cache, các phiên bị ảnh hưởng và kết quả nghiệp vụ.

### Phần D — Báo cáo

Báo cáo nên có:

| Mục | Thông tin cần ghi |
|---|---|
| Profile | DNS name, routing method, TTL |
| Endpoints | Target, priority, monitor status |
| Probe | Protocol, port, path và tiêu chí đánh giá |
| Failover | Thời điểm A lỗi, A Degraded, DNS chọn B và người dùng truy cập thành công |
| DNS | Resolver đã dùng, kết quả truy vấn và TTL quan sát |
| Backend | Trạng thái ứng dụng và dữ liệu ở A/B |
| Kết luận | Khoảng thời gian phục hồi quan sát được và nguyên nhân chính |

Sau thực hành, khôi phục health endpoint, trả lại DNS record về cấu hình cần thiết và dọn các tài nguyên lab được phép xóa. Kiểm tra rằng không còn DNS record trỏ tới một profile đã xóa.

Nếu chỉ có một endpoint public, người học vẫn có thể luyện tạo profile, health monitoring và DNS lookup, nhưng **chưa thể tuyên bố đã kiểm thử failover hai endpoint**.

## 23. Checklist trước khi triển khai production

- [ ] Đã chọn routing method theo nhu cầu nghiệp vụ và hiểu các giới hạn DNS.
- [ ] Mỗi endpoint public được truy cập đúng hostname/cổng và có TLS hợp lệ.
- [ ] Health path phản ánh khả năng phục vụ ứng dụng, không chỉ phản hồi 200 giả.
- [ ] DNS TTL, probe interval và failure threshold được chọn theo mục tiêu phục hồi.
- [ ] Custom domain được cấu hình tại tất cả backend có thể nhận traffic.
- [ ] Backend dự phòng có dữ liệu, cấu hình, secret, session strategy và năng lực xử lý phù hợp.
- [ ] Đã kiểm thử chuyển tuyến khi một endpoint không khỏe và khi endpoint phục hồi.
- [ ] Đã ghi rõ DNS cache và thời gian chuyển thực tế trong kỳ vọng RTO.
- [ ] Đã xác minh dữ liệu, logging và chính sách lưu trú nếu định tuyến theo geography.
- [ ] Có cảnh báo endpoint health, lỗi backend, TLS và những thay đổi profile bất thường.
- [ ] Đã phân quyền RBAC, bảo vệ DNS provider và ghi nhận thay đổi.
- [ ] Có kế hoạch rollback, người trực và hướng dẫn khắc phục lỗi DNS/endpoint.

## 24. Câu hỏi tự kiểm tra

1. Vì sao Traffic Manager không thể trực tiếp route theo HTTP path hoặc chèn WAF?
2. Một profile Priority có A ưu tiên 1 và B ưu tiên 2. Khi A bị Degraded, các DNS query mới có thể nhận kết quả nào?
3. Tại sao TTL 60 giây không bảo đảm toàn bộ người dùng failover trong 60 giây?
4. Weighted 80/20 có đảm bảo tỷ lệ 80/20 HTTP requests không? Vì sao?
5. Performance routing dựa vào phép đo RTT trực tiếp của từng trình duyệt hay thông tin khác?
6. Khi endpoint public trả 200 nhưng database bị lỗi, nên cải tiến health endpoint như thế nào?
7. Khi custom domain là app.example.com, chứng chỉ TLS cần được chuẩn bị ở đâu?
8. Geographic routing có tự đảm bảo tuân thủ data residency và failover sang quốc gia khác không?
9. Nested profile mang lại lợi ích gì và những rủi ro cấu hình nào?
10. Khi thấy DNS phân giải đúng nhưng ứng dụng không truy cập được, bạn phải kiểm tra thêm những lớp nào?

## 25. Tổng kết

**Azure Traffic Manager là công cụ định tuyến toàn cầu ở tầng DNS.** Profile chứa routing method, endpoint, monitoring và TTL; dịch vụ chọn câu trả lời DNS dựa trên chính sách và tình trạng endpoint. Sáu phương pháp định tuyến phục vụ những mục tiêu khác nhau: Priority, Weighted, Performance, Geographic, MultiValue và Subnet.

Khi triển khai, cần hiểu rằng **lưu lượng HTTPS đi trực tiếp đến backend** và **DNS cache khiến failover không tức thời**. Một hệ thống có tính sẵn sàng cao phải chuẩn bị backend đa region, dữ liệu, custom domain/TLS, health probe, kiểm soát truy cập và kiểm thử khôi phục. Traffic Manager là một thành phần điều phối, cần phối hợp với các dịch vụ Azure khác để vận hành ứng dụng an toàn, hiệu quả và kiểm soát được chi phí.
