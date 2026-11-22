# Tách luồng bắc–nam và đông–tây trong hệ thống

## 1. Vì sao cần phân biệt hai hướng lưu lượng?

Khi đưa một ứng dụng lên đám mây, việc kết nối được các thành phần mới chỉ là điều kiện cần. Kiến trúc sư còn phải hiểu **ai đang giao tiếp với ai, đi qua ranh giới tin cậy nào, cần độ trễ ra sao và khi một đoạn mạng hỏng thì phần nào của hệ thống bị ảnh hưởng**. Đó là lý do thiết kế mạng thường phân biệt hai nhóm:

- **Lưu lượng bắc–nam (north–south):** lưu lượng đi **vào hoặc ra khỏi một ranh giới hệ thống đã chọn**, ví dụ người dùng Internet gọi API trong môi trường cloud, hoặc ứng dụng nội bộ gọi cổng thanh toán bên ngoài.
- **Lưu lượng đông–tây (east–west):** lưu lượng **giữa các thành phần cùng nằm bên trong ranh giới đó**, ví dụ API gọi dịch vụ giỏ hàng, dịch vụ đặt chỗ truy cập cơ sở dữ liệu, hoặc hai workload trao đổi sự kiện.

Phân tách không chỉ nhằm vẽ sơ đồ đẹp. Hai nhóm thường có **điểm kiểm soát, chính sách an ninh, cách cân bằng tải, nhu cầu quan sát và mẫu thất bại** khác nhau. Một lỗ hổng ở điểm vào công khai và một lỗ hổng cho phép dịch vụ nội bộ di chuyển ngang có cách phòng vệ khác nhau. Ngược lại, kiểm tra quá nhiều lớp không cần thiết trên mỗi lượt gọi nội bộ có thể làm tăng độ trễ và chi phí.

Trong module **CLOUD_ARCHITECTURE**, bài này hướng dẫn chuyển yêu cầu nghiệp vụ thành lựa chọn **mạng, compute, dữ liệu và mô hình triển khai**, đồng thời cân nhắc **bảo mật, độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tinh thần Well-Architected.

**Ví dụ xuyên suốt:** nền tảng đặt chỗ có web/mobile client, API, dịch vụ tìm kiếm, dịch vụ đặt chỗ, cơ sở dữ liệu, hàng đợi, hệ thống giám sát và cổng thanh toán bên thứ ba. Hệ thống cần cho khách đặt chỗ an toàn, vẫn phục vụ tra cứu khi một dịch vụ phụ thuộc chậm, và cho phép vận hành chẩn đoán sự cố.

## 2. Định nghĩa đúng ranh giới trước khi đặt tên luồng

Hai thuật ngữ **không mô tả hướng địa lý** và không tự nói gói tin là HTTP, TCP hay UDP. Chúng phụ thuộc vào **ranh giới đang xét**: trung tâm dữ liệu, tài khoản cloud, VPC/VNet, cụm Kubernetes, vùng tin cậy hay một ứng dụng.

| Luồng | Nếu ranh giới là môi trường ứng dụng trong VPC/VNet | Phân loại thường dùng |
| --- | --- | --- |
| Trình duyệt Internet → public load balancer → API | Đi từ ngoài vào trong | Bắc–nam, **ingress** |
| API → dịch vụ thanh toán trên Internet | Đi từ trong ra ngoài | Bắc–nam, **egress** |
| API → database qua private address | Hai thành phần nội bộ giao tiếp | Đông–tây |
| Search service → cache nội bộ | Hai thành phần nội bộ giao tiếp | Đông–tây |
| API tại VPC A → dịch vụ tại VPC B cùng tổ chức | Vượt ranh giới VPC, nhưng nằm trong hệ thống doanh nghiệp | Có thể gọi đông–tây liên VPC ở cấp toàn hệ thống; là luồng vượt biên nếu đang đánh giá riêng VPC A |
| Ứng dụng cloud → datacenter riêng qua VPN/private link | Vượt ranh giới cloud/on-premises | Thường là luồng bắc–nam đối với từng môi trường; có thể xem là luồng nội bộ liên vùng trong kiến trúc tổng thể |
| Pod A → Pod B trong cùng cụm Kubernetes | Giao tiếp giữa workload nội bộ cụm | Đông–tây |

**Quy ước quan trọng:** trên mỗi sơ đồ hoặc bảng flow, ghi rõ **ranh giới nào được dùng để phân loại**. Đừng tranh luận tên gọi nếu chưa thống nhất cấp kiến trúc. Một kết nối giữa hai VPC có thể được gọi khác nhau khi nhìn ở cấp VPC hay cấp nền tảng doanh nghiệp, nhưng **nguồn, đích, port, đường đi và mức tin cậy của nó không thay đổi**.

### Không nhầm với những cặp khái niệm khác

- **Ingress/egress** nhấn mạnh chiều **đi vào/đi ra** một ranh giới. Cả hai là những trường hợp thường gặp của bắc–nam.
- **Public/private subnet** mô tả thiết kế định tuyến và khả năng truy cập theo đường mạng. Gắn nhãn private không tự tạo một chính sách bảo mật đầy đủ.
- **Control plane/data plane:** control plane là thành phần điều khiển cấu hình và trạng thái; data plane thực hiện chuyển/áp dụng lưu lượng. Cả hai có thể phát sinh lưu lượng bắc–nam hoặc đông–tây tùy ranh giới.
- **L4/L7:** tầng kiểm soát TCP/UDP hoặc giao thức ứng dụng; đây là **cách xử lý lưu lượng**, không phải tên hướng lưu lượng.

## 3. Nhìn hai luồng trên một sơ đồ kiến trúc

~~~mermaid
flowchart TB
    USER["Người dùng web / mobile"]
    PAY["Cổng thanh toán bên ngoài"]

    subgraph CLOUD["Ranh giới ứng dụng trong cloud"]
        EDGE["Public DNS / CDN / WAF"]
        LB["Public Load Balancer / API Gateway"]
        WEB["Web / API"]
        SEARCH["Search Service"]
        BOOK["Booking Service"]
        DB[("Database private")]
        Q[("Message Queue")]
        EGRESS["Egress Proxy / NAT / Firewall"]
        EDGE --> LB
        LB --> WEB
        WEB --> SEARCH
        WEB --> BOOK
        SEARCH --> DB
        BOOK --> DB
        BOOK --> Q
        BOOK --> EGRESS
    end

    USER -->|"Bắc–nam: ingress HTTPS"| EDGE
    EGRESS -->|"Bắc–nam: egress HTTPS"| PAY
~~~

Trong sơ đồ, các kết nối từ API đến Search, Booking, database và hàng đợi là **đông–tây** theo ranh giới môi trường cloud đã vẽ. Kết nối từ client vào và từ Booking tới cổng thanh toán ngoài cloud là **bắc–nam**. Đường phản hồi của mỗi kết nối không biến nó thành một loại luồng mới; cần phân biệt **bên khởi tạo phiên** với các gói phản hồi đã thuộc phiên đó.

Sơ đồ chỉ là mô hình logic. Trên hệ thống thực, có thể có CDN ngoài phạm vi tài khoản, nhiều availability zone, private load balancer, DNS riêng, hệ thống định danh và dịch vụ managed nằm ngoài subnet do đội ứng dụng quản lý. Phải vẽ bổ sung các thành phần có tác động thực tới tuyến đường, quyền truy cập và khả năng chịu lỗi.

## 4. Thiết kế lưu lượng bắc–nam vào hệ thống (ingress)

Luồng từ người dùng bên ngoài đến ứng dụng cần xác định **điểm tiếp nhận công khai, chuỗi kiểm soát, định tuyến ứng dụng và đường tới backend không công khai**.

~~~text
Client Internet
  -> DNS công cộng
  -> CDN / lớp chống DDoS nếu cần
  -> WAF (cho luồng HTTP phù hợp)
  -> public L7 load balancer / API gateway
  -> dịch vụ web / API nội bộ
  -> các dịch vụ nghiệp vụ phía sau
~~~

Các thành phần có thể được gộp, thay vị trí hoặc không cần đến, tùy dịch vụ và nhu cầu. Ví dụ một load balancer có thể tích hợp WAF; CDN có thể là điểm TLS đầu tiên; API Gateway có thể trực tiếp là lớp nhận lưu lượng. Không bắt buộc mọi ứng dụng có đủ tất cả thiết bị trong chuỗi.

### 4.1. Xác định đâu là điểm vào hợp lệ

Với mỗi API công khai, cần trả lời:

1. Những **hostname, đường dẫn, phương thức và giao thức** nào cần phục vụ từ Internet?
2. TLS được chấm dứt ở đâu? Đoạn **từ proxy tới backend** có cần TLS tiếp và xác thực nội bộ không?
3. Ai thực hiện **xác thực và phân quyền**? WAF giúp lọc một nhóm mẫu tấn công ở HTTP nhưng không thay thế xác thực hoặc kiểm tra quyền nghiệp vụ.
4. Có giới hạn yêu cầu theo IP, tài khoản, phiên hoặc API key không? Cần cơ chế chống abuse nào?
5. Backend có cần địa chỉ public không? Nếu không, giữ backend trong mạng không nhận kết nối trực tiếp từ Internet.
6. Khi backend lỗi, health check và routing hoạt động thế nào? Có biến lỗi ứng dụng thành lỗi toàn vùng không?

**Nguyên tắc giảm bề mặt tấn công:** đưa **chỉ các điểm vào thật sự cần thiết** ra ngoài. Database, message broker, dịch vụ quản trị và cổng metrics thường không nên có endpoint Internet. Quyền truy cập cho quản trị viên nên đi qua kênh được xác thực, ghi log và giới hạn theo vai trò.

### 4.2. Vai trò của load balancer và API gateway

| Thành phần | Phù hợp cho | Không nên mặc định suy ra |
| --- | --- | --- |
| **L4 load balancer** | Phân phối kết nối TCP/UDP, giữ một số đặc tính giao thức và hiệu năng truyền tải | Hiểu mọi quy tắc phân quyền HTTP |
| **L7 load balancer / reverse proxy** | Định tuyến theo host/path, TLS, health check, một số kiểm soát HTTP | Thực hiện đầy đủ xác thực, ủy quyền và logic nghiệp vụ |
| **API gateway** | Chính sách API: xác thực token, quota client, routing, version, log và đôi khi chuyển đổi request | Tự làm an toàn tất cả dịch vụ nội bộ và logic ứng dụng |
| **WAF** | Lọc các yêu cầu HTTP theo quy tắc/mẫu rủi ro thích hợp | Thay thế chống DDoS ở mọi lớp, IAM, vá lỗ hổng hoặc kiểm soát quyền truy cập dữ liệu |
| **CDN** | Cache/phân phối nội dung, giảm RTT với người dùng phân tán | Có thể cache an toàn mọi response chứa dữ liệu cá nhân hay trạng thái giao dịch |

Ví dụ, request **xác nhận đặt chỗ** thường cần xác thực, kiểm tra quyền truy cập đơn, chống gọi lại trùng (idempotency) và cập nhật giao dịch đúng đắn tại backend. CDN/WAF/API gateway có thể giảm tải và lọc đầu vào, nhưng không thể thay thế những quy tắc này.

### 4.3. Tin cậy địa chỉ IP của client đúng cách

Khi đi qua CDN, reverse proxy hoặc load balancer, backend có thể thấy IP của proxy thay vì IP gốc. Các header như X-Forwarded-For chỉ đáng tin khi **được tạo/chuẩn hóa bởi proxy mà tổ chức kiểm soát**, đồng thời ứng dụng chỉ chấp nhận chúng từ nguồn proxy hợp lệ. Tin giá trị header do client Internet tự gửi có thể dẫn tới sai rate limit, kiểm toán hoặc phân quyền dựa trên IP.

## 5. Thiết kế lưu lượng bắc–nam ra ngoài (egress)

Ứng dụng cần truy cập bên ngoài để gọi cổng thanh toán, gửi email, tải bản vá, gọi API của đối tác hoặc kết nối dịch vụ định danh. **Luồng đi ra cũng cần kiểm soát**, vì đó có thể là đường rò rỉ dữ liệu và là nguồn chi phí/độ phụ thuộc lớn.

### 5.1. Ba cách egress thường gặp

| Cách đi ra | Đặc trưng | Điểm cần kiểm tra |
| --- | --- | --- |
| IP công khai trực tiếp trên workload | Đơn giản trong một số trường hợp, nhưng workload có nhiều bề mặt mạng hơn | IAM, firewall, không nhận kết nối ngoài ý muốn, cách thay IP và quan sát |
| NAT gateway/NAT instance | Cho workload địa chỉ riêng khởi tạo kết nối tới endpoint ngoài bằng địa chỉ nguồn được dịch | **NAT không tự kiểm soát nội dung ứng dụng hoặc tạo allowlist theo FQDN**; còn cần định tuyến, firewall và chính sách |
| Egress proxy/firewall chuyên dụng | Tập trung một số kiểm soát đích, danh tính, lọc và nhật ký | Năng lực xử lý, TLS, HA, privacy, độ trễ, chi phí và việc trở thành điểm lỗi chung |

**NAT và firewall có nhiệm vụ khác nhau.** NAT chuyển đổi địa chỉ/port cho luồng đi qua. Một kết nối ra ngoài vẫn có thể đi đến đích không mong muốn nếu chỉ có NAT mà không có chính sách egress thích hợp. Ngược lại, chặn mọi egress cũng có thể làm hệ thống mất DNS, NTP, truy cập API đối tác hoặc khả năng lấy bản vá.

### 5.2. Phân loại đích và giới hạn luồng cần thiết

- **Dịch vụ đối tác:** ghi rõ FQDN/API, giao thức/port, yêu cầu xác thực, thời gian chờ, cơ chế retry, dữ liệu được phép gửi và người phụ trách hợp đồng.
- **Dịch vụ managed của cloud:** ưu tiên endpoint riêng khi phù hợp và được hỗ trợ; kiểm tra loại đường kết nối, chính sách và chi phí. Private endpoint không có nghĩa không cần IAM, TLS hoặc policy.
- **Cập nhật hệ thống/CI:** xác định dịch vụ tải image/package, registry, kho bản vá và giải pháp mirror nếu cần.
- **Logging/telemetry:** ghi nhận đường chuyển log/trace và phân loại dữ liệu để tránh vô tình gửi thông tin khách hàng tới điểm thu nhận không được phê duyệt.

**Egress allowlist theo tên miền** cần đánh giá khả năng thực thi của thiết bị/công cụ: cloud firewall lớp mạng có thể chỉ hỗ trợ IP/CIDR; tên miền có thể trỏ tới IP biến động hoặc dùng CDN; một số cơ chế lọc dựa SNI/HTTP host có hạn chế với TLS và DNS. Không viết một quy tắc tên miền trên giấy rồi mặc định mọi loại firewall đều hỗ trợ.

### 5.3. Thiết kế khi đối tác không phản hồi

Trong nền tảng đặt chỗ, API thanh toán có thể chậm hoặc trả kết quả không chắc chắn. Những hành vi cần làm rõ gồm:

1. Timeout hợp lý theo **ngân sách độ trễ của toàn hành trình**, không để cuộc gọi chờ vô hạn.
2. Retry có backoff/jitter và giới hạn; không tự thử lại giao dịch không an toàn nếu thiếu cơ chế idempotency/đối soát.
3. Ghi trạng thái trung gian và đối soát khi đã gửi yêu cầu nhưng chưa nhận kết quả.
4. Phân biệt lỗi kết nối egress, lỗi DNS, lỗi TLS, đối tác trả 4xx/5xx và lỗi logic nghiệp vụ.
5. Ưu tiên giữ những hành trình độc lập (ví dụ tìm kiếm) hoạt động khi đối tác thanh toán gặp sự cố.

Kiểm soát egress vì thế vừa là bài toán mạng, vừa ảnh hưởng trực tiếp tới độ tin cậy của các workflow ứng dụng.

## 6. Thiết kế lưu lượng đông–tây giữa các dịch vụ

Lưu lượng nội bộ không nên mặc định được tin cậy chỉ vì nó dùng địa chỉ private. Nếu một workload bị xâm nhập, kết nối đông–tây mở rộng có thể cho phép **lateral movement** sang database, hàng đợi hoặc dịch vụ quản trị.

Mục tiêu là **cho phép đúng luồng công việc, giảm khả năng di chuyển ngang, kiểm soát dữ liệu và giữ độ trễ phù hợp**.

### 6.1. Lập ma trận giao tiếp trước khi tạo rule

Ví dụ một ma trận lưu lượng cho nền tảng đặt chỗ:

| Nguồn | Đích | Giao thức/port minh họa | Mục đích | Điều kiện cho phép |
| --- | --- | --- | --- | --- |
| Public LB | Web/API | HTTPS :443 hoặc cổng backend được chọn | Chuyển request từ Internet đã qua lớp edge | Chỉ nhận từ lớp LB/proxy được ủy quyền |
| Web/API | Search Service | TCP :8080 qua HTTP/gRPC phù hợp | Tìm phòng | Xác thực giữa dịch vụ, giới hạn timeout |
| Web/API | Booking Service | TCP :8443 | Gửi yêu cầu đặt chỗ | Danh tính/ủy quyền rõ, tracing và retry an toàn |
| Booking Service | Booking DB | TCP :5432 (ví dụ PostgreSQL) | Đọc/ghi giao dịch | Chỉ service account/role của Booking và nhóm vận hành được duyệt |
| Booking Service | Message Broker | Port theo broker thực tế | Phát sự kiện xác nhận | Quyền publish vào đúng topic/queue |
| Search Service | Cache | TCP :6379 nếu dùng Redis cấu hình tương ứng | Tăng tốc đọc | Chỉ Search có quyền; cache không public |
| Booking Service | Egress Proxy | Port proxy được duyệt | Gọi thanh toán bên ngoài | Egress chỉ đến đối tác được cho phép |
| Các service | DNS, telemetry, identity | Port/giao thức theo môi trường | Phân giải tên, log/trace, xác thực | Danh sách phụ thuộc nền tảng được xác nhận |

Các port và dịch vụ trong bảng là **minh họa**, không phải cấu hình mặc định bắt buộc. Trong triển khai thật, phải xác nhận TLS, port, nguồn/đích, phương thức xác thực, IP hoặc nhãn nhận dạng và hành vi trong nhiều môi trường.

### 6.2. Phân đoạn mạng theo trust zone

Một tổ chức có thể chia thành:

- **Edge zone:** chỉ chứa điểm vào được phép công khai như load balancer, proxy hoặc ingress.
- **Application zone:** các workload ứng dụng, không nhận kết nối Internet trực tiếp nếu không cần.
- **Data zone:** database, broker, cache và lưu trữ nhạy cảm; chỉ nhận từ đúng ứng dụng và kênh quản trị.
- **Management/observability zone:** kênh quản trị, nhật ký, giám sát và điều khiển triển khai.

Một mô hình luồng mong muốn:

~~~mermaid
flowchart LR
    I["Internet"] -->|443| E["Edge zone"]
    E -->|Đường được duyệt| A["Application zone"]
    A -->|Port + danh tính đúng| D["Data zone"]
    O["Management zone"] -->|Quyền quản trị giới hạn| A
    O -->|Quyền vận hành giới hạn| D
    A -->|Telemetry được kiểm soát| O
~~~

Giới hạn bằng **chính sách mặc định từ chối khi phù hợp**, sau đó chỉ mở những kết nối cần thiết. Tùy nền tảng, có thể dùng security group, NSG, distributed firewall, network policy của Kubernetes, service mesh hoặc policy dựa danh tính workload.

Không nên giả định một security group, ACL hoặc network policy hoạt động giống nhau: có cơ chế **stateful**, có cơ chế **stateless**, có rule tầng mạng, có rule nhận diện workload ở tầng ứng dụng. Phải xác minh chiều lưu lượng, rule phản hồi, tính kế thừa và thứ tự xử lý trên nền tảng cụ thể.

### 6.3. Network segmentation và service identity bổ sung cho nhau

Chặn theo mạng giúp giảm bề mặt có thể kết nối. **Danh tính dịch vụ và ủy quyền ứng dụng** giúp quyết định dịch vụ đang kết nối có được phép thực hiện hành động cụ thể hay không. Ví dụ:

- Security policy có thể cho phép Booking Service mở TCP tới DB, nhưng tài khoản DB của Booking chỉ nên có quyền đúng schema/bảng cần thiết.
- TLS/mTLS phù hợp có thể bảo vệ và xác minh kết nối dịch vụ; vẫn cần ủy quyền theo hành động và quản lý vòng đời chứng chỉ.
- Rate limit/bulkhead ở service giúp kiểm soát mức tiêu thụ tài nguyên khi một bên gọi quá nhiều.
- Log truy cập, trace ID và audit ở tầng ứng dụng giúp trả lời **ai đã thực hiện tác vụ nào**, điều mà flow log theo IP/port không thể tự suy ra.

**Zero trust** ở đây có nghĩa không mặc định tin các dịch vụ chỉ vì cùng VPC. Cần xác minh danh tính, chính sách truy cập và trạng thái bảo vệ theo rủi ro; không đồng nghĩa mọi cuộc gọi phải đi qua một gateway tập trung gây tăng độ trễ.

## 7. Chọn cơ chế kiểm soát theo lớp mạng và nền tảng

| Cơ chế | Vị trí áp dụng | Tác dụng chính | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| Route table | VPC/VNet, subnet, kết nối liên mạng | Quy định tuyến next hop/đích có thể đi | Không tự xác thực danh tính hay cho phép truy cập |
| Security group/NSG/firewall | Workload, NIC, subnet hoặc mạng | Cho phép/chặn theo địa chỉ, port, giao thức và một số đối tượng được hỗ trợ | Thường không hiểu ý nghĩa nghiệp vụ |
| Network ACL | Subnet hoặc ranh giới mạng có hỗ trợ | Một lớp lọc bổ sung | Phải kiểm tra stateful/stateless và traffic chiều về |
| Private endpoint/service endpoint | Kết nối tới managed service | Cho phép luồng theo đường private khi dịch vụ hỗ trợ | Không thay phân quyền, mã hóa và giới hạn dữ liệu |
| Kubernetes NetworkPolicy | Pod trong namespace/cụm | Hạn chế kết nối pod ingress/egress theo selector và IP block được hỗ trợ | Chỉ có hiệu lực khi CNI hỗ trợ enforcement; không đồng nghĩa policy L7 |
| Service mesh/mTLS | Lưu lượng giữa workload | Danh tính dịch vụ, mã hóa nội bộ, một số điều khiển/routing L7 | Thêm proxy/control plane, chi phí và độ phức tạp vận hành |
| API Gateway / ingress controller | Điểm vào API hoặc cụm | Routing, xác thực/chính sách HTTP tùy sản phẩm | Không tự chặn các đường kết nối nội bộ bỏ qua gateway |
| Flow logs + tracing | Quan sát lưu lượng/ứng dụng | Chẩn đoán đường đi, kết nối bị từ chối, độ trễ hành trình | Flow log không thay log nghiệp vụ; trace có thể thiếu đường mạng bị chặn |

### Ví dụ Kubernetes: giới hạn pod API chỉ nhận từ pod web

Đoạn sau **minh họa NetworkPolicy** trên một cụm đã có CNI hỗ trợ enforcement. Đặt trong namespace booking, pod API có nhãn app: api và pod web có nhãn app: web:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-default-deny
  namespace: booking
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-allow-web
  namespace: booking
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 8080
~~~

**Giải thích:** rule đầu chọn các pod API và cô lập cả ingress lẫn egress. Rule thứ hai cho phép pod web **trong cùng namespace** gọi cổng 8080 của pod API. Chỉ những policy áp lên cùng pod mới tạo ra tập quyền hợp lệ theo quy tắc cộng dồn của NetworkPolicy. Đoạn này **chưa phải cấu hình production hoàn chỉnh**: egress API đến DNS, identity, DB, queue, telemetry và các phụ thuộc được phép đang bị chặn, cần khai báo các policy tương ứng. Phải kiểm tra port thực, CNI, selector và hành vi của traffic tới managed service nằm ngoài cụm.

Ví dụ cũng cho thấy **mở ingress ở API không tự cho phép API đi ra**. Tách hai chiều là cách kiểm soát rõ một mặt của giao tiếp đông–tây.

## 8. Lộ trình gói tin, latency và bẫy đưa mọi luồng qua một điểm tập trung

Thiết kế mạng phải xem cả **đường đi thực tế** chứ không chỉ biết endpoint tồn tại. Với mỗi luồng, cần tính đến hop qua reverse proxy, load balancer, NAT, firewall, private link, service mesh sidecar và tuyến giữa vùng.

### 8.1. Ví dụ ngân sách độ trễ

Giả sử đường xử lý một yêu cầu đặt chỗ là tuần tự:

| Đoạn | Thời gian minh họa |
| --- | ---: |
| Edge và public LB | 20 ms |
| Web/API xử lý và gọi Booking | 25 ms |
| Booking đọc/ghi DB | 45 ms |
| Gọi phụ thuộc thanh toán | 180 ms |
| Trả kết quả và overhead khác | 30 ms |
| **Tổng trong một lượt đo minh họa** | **300 ms** |

Đây là **số giả định của một đường xử lý**, không phải phép cộng các percentile. Không được cộng p95 của từng thành phần rồi gọi kết quả là p95 end-to-end: phân bố độ trễ và sự tương quan các lần gọi cần được đo trực tiếp từ yêu cầu thật hoặc bài thử đại diện.

Nếu đưa mọi kết nối API ↔ DB qua một firewall tập trung ở vùng khác, lưu lượng đông–tây có thể chịu thêm RTT, phí truyền dữ liệu và điểm lỗi tập trung. Trong cấu trúc **hub-and-spoke**, hub hữu ích cho một số kết nối chia sẻ và kiểm soát tập trung; nhưng không phải mọi giao tiếp nội bộ trong một spoke đều cần chạy qua hub. Phải cân nhắc giữa **kiểm soát tập trung** với **đường đi ngắn, khả dụng, chi phí và thông lượng**.

### 8.2. Đừng quên chi phí đường mạng

Chi phí có thể phát sinh từ load balancer, NAT gateway, dữ liệu truyền ra Internet, chuyển zone/vùng, endpoint riêng, firewall chuyên dụng, đường kết nối dedicated và lượng log mạng. Mức giá tùy cloud và cấu hình; không suy ra "private traffic là miễn phí".

Khi đánh giá một phương án phải xác định **số byte, số kết nối, số lần gọi, vị trí nguồn/đích, chiều dữ liệu, số hop và dự báo biến động**. Dùng workload thật để quyết định thành phần nào xứng đáng đưa qua gateway/firewall đắt tiền, thành phần nào cần đi đường nội bộ tối ưu.

## 9. Ranh giới mạng, availability zone và hybrid cloud

Từ góc nhìn độ tin cậy, ranh giới bắc–nam và đông–tây còn liên quan tới **phạm vi hỏng hóc**:

- **Nhiều availability zone:** API ở zone A có thể gọi DB/instance trong zone B. Đó vẫn là giao tiếp nội bộ theo ranh giới ứng dụng, nhưng phải tính độ trễ, chi phí liên zone và khả năng chịu lỗi.
- **Nhiều VPC/VNet:** kết nối private giữa các mạng vẫn cần route không trùng CIDR, policy hai đầu, DNS và cơ chế quan sát. Có route không có nghĩa policy cho phép.
- **Hybrid cloud/on-premises:** dùng VPN hoặc kết nối riêng theo yêu cầu; quyết định rõ dữ liệu nào đi qua, ai sở hữu DNS/identity, băng thông dự phòng và điều gì xảy ra khi link hỏng.
- **Nhiều vùng:** ứng dụng cần quyết định trạng thái nào được sao chép, chuyển người dùng về vùng nào, RPO/RTO và chính sách phân quyền khi failover. Không nên để một dependency đồng bộ xa trở thành điểm lỗi chặn cả hành trình.

Ví dụ, web/API đặt ở cloud nhưng mỗi lần tìm kiếm lại gọi database đặt trong datacenter riêng có thể khiến **bắc–nam liên môi trường** trở thành điểm nghẽn của mọi yêu cầu. Nếu nghiệp vụ cho phép một mức độ trễ cập nhật, một chỉ mục đọc hoặc cache gần phần tìm kiếm có thể giảm số lần đi qua liên kết. Đổi lại phải xác định **nguồn dữ liệu sự thật, độ mới chấp nhận được, quyền sao chép và cách xử lý khi mất đồng bộ**.

## 10. Thiết kế bảo mật theo đường đi và điểm kiểm soát

Trước khi áp firewall rule, thực hiện một bài tập **threat modeling theo data flow**:

1. **Tài sản:** dữ liệu khách, trạng thái thanh toán, thông tin xác thực, bí mật ứng dụng, hệ thống quản trị.
2. **Nguồn đe dọa và điểm vào:** Internet, đối tác, tài khoản bị chiếm quyền, workload nội bộ bị xâm nhập, pipeline hoặc kết nối quản trị.
3. **Ranh giới tin cậy:** Internet ↔ edge, edge ↔ app, app ↔ data, cloud ↔ bên thứ ba/on-premises.
4. **Kiểm soát:** TLS, xác thực, ủy quyền, segmentation, kiểm tra input, mTLS khi phù hợp, IAM dữ liệu, rate limit, audit.
5. **Phản ứng sự cố:** có thể tạm chặn một luồng hoặc cô lập một service mà vẫn giữ những hành trình độc lập hoạt động không?

### Kiểm soát vào ra và kiểm soát nội bộ có mục đích khác nhau

| Nguy cơ | Điểm kiểm soát chính | Bằng chứng |
| --- | --- | --- |
| Client không hợp lệ gọi API Internet | Edge, WAF/rate limit, API authentication và authorization | Thử request lỗi, kiểm tra 401/403/429 và audit |
| Backend bị truy cập trực tiếp, bỏ qua edge | Security policy, private routing, cấu hình endpoint | Quét từ ngoài Internet và kiểm tra route/SG |
| Service bị chiếm quyền gọi ngang sang database khác | Segmentation, workload identity, DB credentials và quyền schema | Kiểm thử kết nối bị từ chối giữa các trust zone |
| Dữ liệu bị gửi ra ngoài trái phép | Egress allowlist/proxy, IAM, kiểm soát dữ liệu và logging | Kiểm thử đích egress bị chặn và kiểm toán dữ liệu truyền |
| Kẻ tấn công đọc/sửa traffic nội bộ | Mã hóa transport, xác minh endpoint và quản trị chứng chỉ | Kiểm tra TLS/mTLS và phát hiện chứng chỉ không hợp lệ |
| Liên kết mạng bị gián đoạn | Timeout, circuit breaker, queue, vùng dự phòng | Chaos test/mô phỏng mất kết nối và xác nhận hành vi ứng dụng |

Không công bố mọi tài nguyên sau một reverse proxy rồi cho rằng chỉ cần bảo vệ reverse proxy. Nếu một dịch vụ nội bộ vẫn có đường truy cập khác hoặc quyền DB quá rộng, sự cố ở một workload có thể lan rộng.

## 11. Quan sát và xác minh đường đi của từng loại lưu lượng

Sơ đồ mạng phải được kiểm tra bằng kết quả thật. Một hệ thống observability tốt phân biệt **tầng mạng, tầng ứng dụng và nghiệp vụ**:

| Dữ liệu quan sát | Phù hợp để trả lời | Giới hạn |
| --- | --- | --- |
| Load balancer / gateway logs | Client nào gọi route nào, status, latency tại edge | Không thấy đầy đủ các cuộc gọi phía sau nếu thiếu tracing |
| Flow logs, firewall logs | IP/port/protocol, accept/deny, lưu lượng giữa zone và workload | Không tự chứng minh người dùng nghiệp vụ nào thực hiện hành động gì |
| DNS/proxy logs | Endpoint nào được phân giải/gọi, các lỗi DNS hoặc chặn egress | Phải cân nhắc privacy, giữ log và thay đổi IP động |
| Distributed traces | Đường gọi giữa dịch vụ, latency từng span, điểm nghẽn logic | Có thể không phản ánh gói tin bị chặn trước khi tạo span |
| Application/DB audit logs | Danh tính nghiệp vụ, thao tác trên dữ liệu, trạng thái giao dịch | Cần kiểm soát PII, bí mật và quyền truy cập log |
| Metrics hệ thống | Error rate, saturation, connection pool, queue depth, throughput | Chỉ số CPU bình thường không chứng minh hành trình người dùng thành công |

Một bộ chỉ số minh họa nên có:

- **Bắc–nam ingress:** tỉ lệ request hợp lệ, 4xx/5xx theo nguyên nhân, p95/p99 end-to-end, số kết nối, rate limit/WAF drops, lỗi TLS, phân bố theo route.
- **Bắc–nam egress:** số request tới mỗi bên thứ ba, DNS/connect/TLS timeouts, tỷ lệ retry, lỗi HTTP, lưu lượng/chi phí qua NAT hoặc proxy.
- **Đông–tây:** tỷ lệ RPC thành công, timeout, connection reset, saturation DB, queue backlog, số luồng bị firewall/network policy chặn, throughput liên zone.
- **Khả năng phục hồi:** thời gian phát hiện lỗi, thời gian cô lập, khả năng phục vụ một phần khi đối tác/ngách mạng bị mất, kết quả failover và đối soát giao dịch.

Khi gặp sự cố "API chậm", hỏi **chậm ở đoạn nào?**. Nếu LB ghi latency thấp nhưng trace cho thấy một dependency ở service B mất 2 giây, chỉ tối ưu CDN sẽ không sửa đúng nguyên nhân. Nếu trace không xuất hiện cuộc gọi đến B và flow logs cho biết kết nối bị deny, phải kiểm tra route/policy/DNS trước khi sửa logic ứng dụng.

## 12. Quy trình thiết kế và kiểm thử có thể thực hiện

~~~mermaid
flowchart TD
    A["Xác định hành trình người dùng, SLO và loại dữ liệu"]
    A --> B["Vẽ ranh giới tin cậy và inventory các luồng"]
    B --> C["Phân loại ingress, egress, east–west"]
    C --> D["Lập ma trận nguồn-đích-port-danh tính"]
    D --> E["Chọn routing, LB, NAT/proxy, segmentation"]
    E --> F["Triển khai qua IaC và kiểm thử policy"]
    F --> G["Load test, fault test, security test"]
    G --> H["Quan sát thực tế, ADR và điều chỉnh"]
    H --> B
~~~

### Bộ kiểm thử tối thiểu

| Kịch bản | Kiểm thử mong đợi |
| --- | --- |
| Client Internet gọi API đúng đường | DNS, TLS, edge routing và xác thực hoạt động; p95 đạt mục tiêu dưới tải đã định |
| Client tìm cách gọi database/backend private trực tiếp | Bị từ chối ở mạng hoặc điểm kiểm soát thích hợp, có bằng chứng |
| Service không có quyền gọi DB hoặc service khác | Kết nối/ủy quyền bị từ chối theo ma trận; không ảnh hưởng luồng hợp lệ |
| Ứng dụng gọi đối tác thanh toán | Đúng tuyến egress và chính sách; có log, timeout và đối soát an toàn |
| Đối tác thanh toán mất kết nối | Hành trình tìm kiếm vẫn hoạt động; đặt chỗ có trạng thái lỗi/chờ rõ ràng |
| Một zone, đường VPN hoặc egress proxy lỗi | Có hành vi failover/suy giảm được dự báo; RTO/RPO được đo nếu liên quan |
| Tăng traffic nhiều lần trong chiến dịch | Kiểm tra LB, NAT port/capacity, DNS, connection pool, database và chi phí liên zone |

**Không chỉ thử happy path**. Một kiến trúc có thể vượt load test trong tình trạng bình thường nhưng thất bại khi một pod, subnet, zone hoặc đường liên kết mất kết nối. Kết quả kiểm thử cần đi kèm dữ liệu cấu hình, tải, thời gian, vùng và giới hạn áp dụng.

## 13. Bài thực hành: tách luồng trong hệ thống đặt chỗ

**Đề bài:** công ty muốn triển khai website đặt chỗ lên cloud. Client bên ngoài truy cập HTTPS; API gọi dịch vụ tìm kiếm và đặt chỗ; dịch vụ đặt chỗ cập nhật PostgreSQL và gửi sự kiện vào broker; yêu cầu thanh toán đi tới nhà cung cấp ngoài cloud. Phần tìm kiếm phải duy trì khi cổng thanh toán chậm. Database không được truy cập trực tiếp từ Internet.

### Yêu cầu thực hiện

1. **Vẽ sơ đồ ranh giới** của ứng dụng và tô/ghi chú ingress, egress và east–west. Thể hiện rõ DNS, public LB/gateway, private workload, database và egress.
2. **Lập ma trận ít nhất tám luồng**: nguồn, đích, protocol/port, dữ liệu trao đổi, danh tính, chính sách cho phép và người sở hữu.
3. **Thiết kế điểm vào:** chỉ ra thành phần public, nơi xử lý TLS, xác thực, rate limit và đường đến backend; giải thích cách ngăn truy cập backend trực tiếp.
4. **Thiết kế egress:** các đích bên thứ ba nào được phép, đi bằng NAT hay proxy nào, theo dõi lỗi/tải ra sao và bảo vệ khi đối tác bị gián đoạn thế nào.
5. **Thiết kế east–west:** ít nhất ba trust zone; ghi rõ các kết nối cần chặn và cách kiểm thử chặn. Nêu thêm cơ chế xác thực dịch vụ/DB tương ứng.
6. **Thử một kịch bản lỗi:** mất egress thanh toán, một service bị chiếm quyền hoặc mất kết nối qua zone. Đưa ra mục tiêu độ trễ/khả dụng và dữ liệu đo được để xác nhận.
7. **Ước lượng chi phí:** liệt kê load balancer, NAT/proxy, dữ liệu qua zone/vùng, private endpoint và log mạng nếu dùng; đề xuất cách đo chi phí thực.
8. **Viết ADR ngắn:** chọn một phương án mạng, nêu lựa chọn bị loại, đánh đổi bảo mật–hiệu năng–độ tin cậy–chi phí và điều kiện cần xem lại.

### Mẫu bảng để nộp

| ID | Hướng theo ranh giới đã chọn | Nguồn → Đích | Cơ chế định tuyến/kiểm soát | Bằng chứng nghiệm thu |
| --- | --- | --- | --- | --- |
| F-01 | Bắc–nam ingress | Client → public API | DNS, TLS, WAF/LB, auth | API đúng trả thành công; request không có quyền bị từ chối |
| F-02 | Đông–tây | API → Booking | Private routing + identity/allow policy | Chỉ API hợp lệ được phép gọi |
| F-03 | Đông–tây | Booking → DB | Private connection + DB role | Client ngoài và service không có quyền không truy cập được |
| F-04 | Bắc–nam egress | Booking → Payment provider | Egress path và timeout đã duyệt | Khi đối tác lỗi, có trạng thái/đối soát an toàn |

**Tiêu chí đạt:** mỗi thành phần chỉ nhận/gửi những luồng cần thiết; có bằng chứng về quyền, độ trễ, lưu lượng, lỗi và chi phí; đường vào/ra công khai cùng đường ngang nội bộ được kiểm tra độc lập; các kịch bản gián đoạn không tạo lỗi dây chuyền vượt mục tiêu đã thỏa thuận.

## 14. Checklist rà soát kiến trúc theo Well-Architected

- [ ] Đã chọn ranh giới hệ thống để phân loại bắc–nam và đông–tây, có sơ đồ nguồn–đích đầy đủ.
- [ ] Chỉ công khai những endpoint cần thiết; backend và dữ liệu nhạy cảm được bảo vệ theo lớp mạng và quyền.
- [ ] Ingress có cơ chế TLS, xác thực, phân quyền, routing, chống abuse và giám sát phù hợp với rủi ro.
- [ ] Egress được kiểm soát theo đích/nghiệp vụ; không coi NAT là firewall; có kế hoạch xử lý đối tác lỗi.
- [ ] Ma trận east–west có port, danh tính, dữ liệu, owner và phương pháp kiểm chứng cho từng luồng.
- [ ] Đã tính các phụ thuộc DNS, identity, logging, NTP, image/patch registry khi áp deny-by-default.
- [ ] Đã xem xét khả năng bị lateral movement khi một workload bị xâm nhập.
- [ ] Đã kiểm chứng semantics thực tế của security group/NSG, ACL, Kubernetes policy và service mesh nếu sử dụng.
- [ ] Đã đo p95/p99 theo hành trình, tránh suy sai từ latency hoặc health check của từng thành phần.
- [ ] Đã đánh giá routing, độ trễ, điểm lỗi chung và phí truyền dữ liệu khi qua hub, zone, region hay hybrid link.
- [ ] Đã thử mất dịch vụ, mất kết nối, chặn sai policy, tải đỉnh và phục hồi; lưu lại kết quả kiểm tra.
- [ ] Đã phân trách nhiệm vận hành, bảo mật, quản lý thay đổi và ghi ADR cho lựa chọn mạng.

Tách đúng lưu lượng bắc–nam và đông–tây giúp kiến trúc sư **đặt cơ chế kiểm soát đúng nơi**: bảo vệ các điểm vào/ra của hệ thống, giới hạn sự lan rộng giữa dịch vụ nội bộ, đồng thời giữ đường đi và chi phí phù hợp. Việc phân tách chỉ tạo giá trị khi được nối với yêu cầu nghiệp vụ, cấu hình mạng thực tế, số đo quan sát và thử nghiệm sự cố.
