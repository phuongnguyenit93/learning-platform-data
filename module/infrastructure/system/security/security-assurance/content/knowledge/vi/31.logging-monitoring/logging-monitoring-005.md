# Centralized logging: Thu thập log tập trung và bảo đảm khả năng kiểm chứng

Trong một hệ thống phân tán, sự kiện liên quan đến một yêu cầu có thể xuất hiện ở gateway, ứng dụng, cơ sở dữ liệu, máy chủ, nền tảng container, dịch vụ định danh và tài khoản cloud. Nếu mỗi thành phần chỉ lưu log cục bộ, người vận hành khó ghép các sự kiện theo thời gian; khi máy chủ bị thay thế, tài khoản bị xâm phạm hoặc dịch vụ bị lỗi, một phần chứng cứ cũng có thể biến mất.

**Centralized logging** là khả năng thu nhận log từ những nguồn đã xác định, vận chuyển đến hệ thống quản lý tập trung, chuẩn hóa, bảo vệ, lưu trữ và cung cấp cơ chế truy vấn/khai thác cho mục tiêu vận hành, phát hiện bảo mật, điều tra và kiểm toán. “Tập trung” ở đây có thể là **một lớp quản trị và truy vấn thống nhất** trên nhiều kho dữ liệu; không bắt buộc mọi sự kiện phải nằm trong một máy chủ hoặc một vùng địa lý.

Trong module **SECURITY_SECURITY_ASSURANCE**, chủ đề này thuộc chương **Logging và monitoring**. Mục tiêu của security assurance không chỉ là kiểm tra rằng “đã bật log” hoặc “có dashboard”. Tổ chức phải đưa ra **bằng chứng** cho thấy sự kiện quan trọng thực sự được tạo ra, đi qua pipeline, được bảo vệ khỏi truy cập/sửa đổi trái phép, có thể tìm lại đúng thời hạn và được sử dụng để phát hiện, xử lý bất thường. Kết quả đánh giá cần nối được **mục tiêu bảo mật → control → phép kiểm tra → bằng chứng → phát hiện → khắc phục**.

Sau bài học, người học có thể thiết kế luồng logging tập trung có phân định trách nhiệm, xác định nguồn log và trường dữ liệu tối thiểu, xây dựng yêu cầu về độ tin cậy và bảo vệ log, kiểm tra toàn tuyến bằng sự kiện thử, đánh giá mức độ bao phủ, và lập hồ sơ assurance phục vụ kiểm toán hoặc xử lý sự cố.

## 1. Centralized logging giải quyết những vấn đề nào?

Hãy xét một tình huống: tài khoản quản trị đăng nhập qua nhà cung cấp định danh, thay đổi chính sách mạng trên cloud, sau đó truy cập một cơ sở dữ liệu bằng kết nối từ workload. Mỗi thao tác có thể được ghi bởi một hệ thống khác nhau:

- Identity Provider (IdP): đăng nhập, MFA, cấp token, thay đổi quyền và nhóm.
- Cloud control plane: gọi API để tạo, sửa hoặc xóa tài nguyên và policy.
- Hạ tầng mạng: luồng kết nối, firewall decision, VPN, proxy hoặc DNS.
- Máy chủ/container: thao tác đặc quyền, process và thay đổi tệp cấu hình.
- Ứng dụng: thay đổi tài khoản, thao tác nhạy cảm và kết quả kiểm tra ủy quyền.
- Cơ sở dữ liệu: truy cập dữ liệu hoặc thay đổi quyền theo những loại audit được bật.

Nếu chỉ có log ở từng nguồn, nhóm điều tra phải truy cập nhiều hệ thống, xử lý nhiều định dạng và múi giờ, rồi tự ghép chuỗi hành vi. Centralized logging tạo một đường thu thập ổn định và bối cảnh chung để các sự kiện được tra cứu, đối chiếu và giám sát.

### Giá trị và giới hạn

| Giá trị cần có | Centralized logging hỗ trợ | Điều chưa thể tự kết luận |
|---|---|---|
| **Khả năng quan sát** | Tìm kiếm và liên kết sự kiện từ nhiều nguồn, ứng dụng và tài khoản. | Có nguồn quan trọng nào bị thiếu hoặc tắt ghi log hay không. |
| **Phát hiện bất thường** | Cung cấp dữ liệu cho rule, dashboard và hệ thống cảnh báo/SIEM. | Phát hiện có đúng, đủ kịp thời và có người phản hồi không. |
| **Điều tra** | Lưu sự kiện và bối cảnh theo thời gian, đối chiếu nhiều đường đi. | Log có đầy đủ, không bị sửa hoặc chứng minh tuyệt đối một hành động không xảy ra hay không. |
| **Bằng chứng kiểm toán** | Truy vết cấu hình logging, lịch sử truy cập và kết quả kiểm tra. | Một kho log tồn tại có đáp ứng tất cả yêu cầu bảo mật hoặc pháp lý không. |
| **Tính bền vững của bằng chứng** | Giảm phụ thuộc vào log nằm trong một máy có thể mất hoặc bị thay thế. | Kho tập trung có bất khả xâm phạm hoặc không có điểm lỗi chung hay không. |

**Log khác metric và trace.** Log ghi lại các sự kiện có ngữ cảnh; metric thường mô tả số đo theo thời gian; distributed trace nối các span của một request xuyên dịch vụ. Ba nguồn dữ liệu có thể bổ trợ nhau, nhưng việc có trace hoặc metric không tự thay thế audit log.

**Log management khác SIEM.** Hệ thống tập trung có thể chỉ thu thập, lưu và tìm kiếm. SIEM bổ sung chức năng phân tích, tương quan và phát hiện an ninh. Một hệ thống có cả hai khả năng vẫn cần kiểm thử riêng chất lượng thu thập và hiệu lực phát hiện.

## 2. Kiến trúc tổng quát của luồng logging tập trung

~~~mermaid
flowchart LR
    A["Ứng dụng, OS, DB, IAM, network, cloud audit"] --> B["Collector / agent / API connector"]
    B --> C["Bộ đệm, hàng đợi và truyền tải bảo vệ"]
    C --> D["Validation, parsing, enrichment, routing"]
    D --> E["Kho lưu trữ có kiểm soát truy cập"]
    E --> F["Search, dashboard, SIEM, điều tra"]
    D --> G["Quarantine / dead-letter cho sự kiện lỗi"]
    B --> H["Telemetry pipeline"]
    C --> H
    D --> H
    E --> H
    H --> I["Cảnh báo pipeline và coverage"]
~~~

Luồng minh họa gồm sáu lớp:

1. **Nguồn sinh sự kiện (*producer*):** ứng dụng, hệ điều hành, thiết bị, thành phần định danh, control plane hoặc dịch vụ SaaS.
2. **Bộ thu thập (*collector/agent/connector*):** đọc từ file/journal, stream, syslog, endpoint, API hoặc sự kiện nền tảng; bổ sung metadata xác định nguồn và chuyển tiếp.
3. **Bộ đệm/truyền tải (*buffer/transport*):** xử lý sự cố kết nối, áp dụng xác thực, mã hóa, retry, điều tiết và kiểm soát áp lực nhận (*backpressure*).
4. **Xử lý (*processing*):** kiểm tra định dạng, gắn nhãn môi trường, chuẩn hóa trường, lọc dữ liệu nhạy cảm, định tuyến theo mục đích và ghi nhận lỗi.
5. **Lưu trữ (*storage*):** quản lý phân vùng, retention, tìm kiếm, bảo vệ quyền truy cập, bảo toàn log theo yêu cầu và phục hồi.
6. **Tiêu thụ (*consumer*):** truy vấn, dashboard, detection rule, case management, kiểm toán hoặc xuất dữ liệu có kiểm soát.

Cần giám sát **chính pipeline logging**. Nếu agent ngừng gửi dữ liệu hoặc parser âm thầm bỏ sự kiện, dashboard có thể vẫn hoạt động trong khi các bằng chứng cần thiết đã bị mất.

### Centralized không có nghĩa là điểm lỗi duy nhất

Một kho hoặc tài khoản tập trung có thể trở thành mục tiêu hấp dẫn. Thiết kế cần cân nhắc khả năng chịu lỗi, tách quyền quản trị, mô hình phân vùng dữ liệu, dự phòng theo vùng, nơi lưu bản sao độc lập và phương án phục hồi phù hợp. Với yêu cầu data residency, log có thể được giữ ở từng vùng và truy vấn qua một lớp liên kết; phải cân nhắc quyền truy cập và quy định truyền dữ liệu giữa các vùng.

## 3. Lập inventory và chọn nguồn log theo rủi ro

**Không thể đánh giá coverage nếu chưa có danh mục nguồn bắt buộc.** Danh mục nên xuất phát từ inventory tài sản, data flow, threat model, yêu cầu phát hiện và nghĩa vụ kiểm toán của từng hệ thống.

| Nhóm nguồn | Sự kiện cần cân nhắc | Câu hỏi assurance |
|---|---|---|
| IAM/IdP/SSO | Đăng nhập thành công/thất bại, MFA, thay đổi user/role/group, phát hành hoặc thu hồi thông tin xác thực. | Sự kiện đặc quyền có được gửi đủ từ mọi tenant và có thời gian/actor rõ không? |
| Cloud control plane | Tạo/xóa tài nguyên, thay đổi IAM, cấu hình mạng, key, logging và chính sách cấp tổ chức. | Audit log có bật cho đúng tài khoản, region và loại thao tác không? |
| Hệ điều hành/host | Đăng nhập đặc quyền, sudo, thay đổi cấu hình bảo mật, tác vụ nhạy cảm, lỗi dịch vụ. | Có agent trên mọi host áp dụng, gồm host ngắn hạn hay không? |
| Container/Kubernetes | API audit, thay đổi RBAC, tạo workload, thao tác secret, log runtime và sự kiện cluster. | Control plane managed và node/workload có được thu thập theo đúng phần trách nhiệm không? |
| Ứng dụng/API gateway | Truy cập endpoint, lỗi xác thực/ủy quyền, thao tác nhạy cảm, thay đổi trạng thái nghiệp vụ. | Có event ID, actor, outcome và correlation ID đủ cho điều tra không? |
| Database/data platform | Thay đổi quyền, truy vấn hoặc hành động dữ liệu nhạy cảm theo phạm vi audit đã chọn. | Chính sách audit có phù hợp độ nhạy cảm mà không tạo rủi ro lộ dữ liệu không? |
| Mạng và lớp biên | Firewall/flow, proxy, DNS, load balancer, VPN, WAF. | Có đủ điểm quan sát để đánh giá đường truy cập đáng quan tâm không? |
| Backup, KMS và công cụ bảo mật | Thay đổi chính sách khóa, sử dụng khóa nhạy cảm, lỗi backup, thay đổi cấu hình phát hiện. | Các hành động có thể xóa hoặc vô hiệu hóa bằng chứng có được ghi không? |
| CI/CD, repository, IaC | Thay đổi pipeline, phân quyền, tạo token, deploy và thay đổi cấu hình quan trọng. | Có thể truy từ một thay đổi sản xuất về người phê duyệt và artifact không? |
| SaaS và nhà cung cấp bên thứ ba | Audit tenant, thay đổi quyền, export, chia sẻ và tích hợp. | Có quyền dùng API log, phạm vi/kỳ lưu, độ trễ hoặc giới hạn quota nào? |

Ví dụ, hệ thống xử lý dữ liệu nhạy cảm nên ưu tiên khả năng truy vết thay đổi quyền và truy cập dữ liệu. Hệ thống xử lý số lượng request rất lớn có thể chỉ lưu thống kê cho một số sự kiện thông thường, nhưng **không nên tùy tiện lấy mẫu hoặc bỏ sự kiện audit bắt buộc** nếu điều đó làm mất khả năng kiểm chứng.

### Tạo ma trận bắt buộc

Với từng loại nguồn, lưu ít nhất: hệ thống/tài khoản, resource ID, môi trường, khu vực địa lý, chủ sở hữu, phân loại dữ liệu, các loại event bắt buộc, cơ chế sinh và xuất, đường truyền, đích nhận, retention, người được truy cập, tần suất kiểm tra và kiểm soát liên quan. Ma trận phải cập nhật khi xuất hiện tài khoản mới, region mới, node auto-scaling, tích hợp SaaS hoặc luồng dữ liệu mới.

Nếu một nguồn không hỗ trợ một loại audit event, cần ghi **giới hạn quan sát và rủi ro còn lại**; không gán cho nó trạng thái “đã kiểm soát” chỉ vì connector không báo lỗi.

### Shared responsibility của logging

Trong IaaS, khách hàng thường cần cấu hình logging cho guest OS và ứng dụng, trong khi CSP cung cấp các nguồn audit của control plane và dịch vụ được phép xuất. Với PaaS/managed database, CSP vận hành các thành phần nền tảng theo cam kết; khách hàng phải bật và thu những log có thể cấu hình theo dịch vụ. Với SaaS, khả năng audit, export, retention và thời điểm có sẵn sự kiện phụ thuộc sản phẩm, gói dịch vụ và hợp đồng.

Người chịu trách nhiệm giải trình phía tổ chức vẫn phải **kiểm tra** phần mình được cung cấp và đánh giá bằng chứng phía CSP cho phần không thể quan sát trực tiếp. “Nhà cung cấp giữ log” không tự chứng minh tổ chức có quyền truy cập, thời gian lưu hoặc khả năng phục vụ điều tra cần thiết.

## 4. Thiết kế sự kiện có cấu trúc và ngữ cảnh đầy đủ

Một hệ thống tập trung khó sử dụng nếu mỗi nguồn tạo văn bản tùy ý. **Structured logging** dùng định dạng máy đọc được, thường là JSON, cho phép tìm kiếm theo trường và tương quan giữa hệ thống.

Bản ghi sự kiện minh họa:

~~~json
{
  "event_time": "2026-11-28T03:15:20.123Z",
  "event_id": "evt-order-api-000381",
  "source": {
    "service": "order-api",
    "environment": "production",
    "region": "region-a",
    "instance_id": "order-api-pod-17"
  },
  "event": {
    "category": "authentication",
    "action": "login",
    "outcome": "failure",
    "severity": "warning"
  },
  "actor": {
    "type": "user",
    "id": "user-pseudonym-42"
  },
  "request": {
    "correlation_id": "req-80e7c",
    "client_ip": "198.51.100.24"
  },
  "reason_code": "INVALID_CREDENTIAL"
}
~~~

Địa chỉ IP trong ví dụ thuộc dải dành cho tài liệu; các giá trị còn lại là giả định. Trong hệ thống thật, địa chỉ IP, định danh và metadata truy cập có thể là dữ liệu cá nhân: chỉ thu và lưu khi cần thiết, theo quy định/chính sách áp dụng.

### Những trường nên chuẩn hóa

| Trường | Mục đích | Lưu ý |
|---|---|---|
| **event_time** | Thời điểm sự kiện xảy ra ở nguồn. | Ưu tiên UTC, định dạng rõ múi giờ; ghi độ chính xác và khả năng lệch đồng hồ. |
| **ingest_time** | Thời điểm hệ thống thu nhận sự kiện. | Dùng để đo độ trễ; không thay thế thời điểm thực tế của sự kiện. |
| **event_id** | Nhận dạng/deduplicate bản ghi nếu nguồn hỗ trợ. | ID phải ổn định qua retry; không giả định mọi nguồn có ID toàn cục duy nhất. |
| **source + asset identity** | Xác định ứng dụng, account, host, region, namespace và instance phát sinh. | Không đồng nhất hostname tạm thời với định danh tài sản bền vững. |
| **action, outcome, category** | Phân loại thao tác và kết quả thực hiện. | Dùng tập giá trị nhất quán để tương quan và tạo rule. |
| **actor/subject** | Ai thực hiện và đối tượng bị tác động. | Phân biệt user, workload identity, service account và hành động hệ thống. |
| **correlation_id / trace_id** | Ghép sự kiện thuộc một yêu cầu hoặc quy trình. | Không dùng ID làm dữ liệu xác thực hoặc chứa thông tin bí mật. |
| **schema_version** | Xác định cấu trúc log mà parser cần đọc. | Giúp cập nhật pipeline không phá truy vấn cũ. |
| **sensitivity/retention class** | Quy định đích lưu, quyền và thời gian giữ. | Không dựa hoàn toàn vào nhãn do nguồn không đáng tin khai báo. |

**Sự kiện bảo mật cần mô tả kết quả và lý do đủ để điều tra**, chẳng hạn từ chối phân quyền, tạo quyền mới hoặc vô hiệu hóa log. Không nên ghi mật khẩu, access token, private key, session cookie, chuỗi kết nối chứa bí mật hoặc toàn bộ payload nhạy cảm.

### Độ chính xác thời gian và tương quan

Đồng hồ host, container, máy người dùng, log từ API SaaS và hệ thống cloud có thể có mức trễ khác nhau. Nên đồng bộ thời gian qua nguồn đáng tin cậy theo chính sách, giữ cả **event_time** và **ingest_time**, đo mức lệch cho phép và ghi timezone rõ ràng. Khi tương quan, phải xét sai lệch và độ trễ thay vì khẳng định thứ tự tuyệt đối từ hai timestamp sát nhau.

Với các sự kiện định danh và API, nên truyền correlation ID theo đường gọi nhưng không tin giá trị client cung cấp nếu chưa được kiểm tra. Có thể tạo ID mới ở ingress và truyền nội bộ để truy vết; không dùng correlation ID làm cơ chế bảo mật.

## 5. Phương án thu thập và vận chuyển

Các nguồn và giới hạn vận hành khác nhau đòi hỏi phương thức thu thập phù hợp:

| Phương thức | Phù hợp với | Điểm cần kiểm tra |
|---|---|---|
| **Agent trên host** | File/journal hệ điều hành, ứng dụng chạy VM. | Quyền agent, trạng thái dịch vụ, offset đọc, vùng đệm khi mất mạng, log rotation. |
| **DaemonSet/collector trên node** | Container log và node trong Kubernetes. | Phạm vi node pool, namespace, thay node, metadata gắn đúng workload. |
| **Sidecar/SDK hoặc stdout** | Ứng dụng hoặc workload có cấu trúc log riêng. | Ảnh hưởng hiệu năng, hành vi khi queue đầy, format, sampling và tình trạng trùng sự kiện. |
| **Syslog / giao thức thiết bị** | Network appliance, firewall, một số máy chủ. | Cơ chế xác thực, mất gói/khả năng bảo đảm truyền, TLS nếu hỗ trợ, clock và event format. |
| **Cloud-native audit stream/export** | Control plane, PaaS, log nền tảng. | Log có bật không, phạm vi region/account, quyền export, delay, quota và retention nguồn. |
| **API polling/webhook của SaaS** | Audit từ ứng dụng bên thứ ba. | Cursor/checkpoint, rate limit, trang kết quả, retry, duplicate, ký/xác minh webhook nếu có. |

Không có một phương thức luôn tốt nhất. Syslog UDP có thể mất gói hoặc không cung cấp cơ chế xác nhận nhận thành công; TCP/TLS cải thiện tính tin cậy trên từng chặng nhưng vẫn **không bảo đảm end-to-end rằng bản ghi đã vào kho lưu trữ**. API polling phải xử lý phân trang, rate limit và thứ tự xuất hiện trễ; webhook phải xác minh nguồn gửi và cơ chế retry theo thiết kế nhà cung cấp.

### Thiết kế cho lỗi và gián đoạn

Nên định nghĩa rõ yêu cầu độ tin cậy:

- **Buffer tại nguồn hoặc collector:** khi mất kết nối, giữ log trong khả năng tài nguyên cho phép; theo dõi dung lượng, số sự kiện chờ và nguy cơ tràn.
- **Retry có giới hạn và backoff:** tránh làm sập nguồn hoặc hệ thống đích khi gặp lỗi tạm thời.
- **Hàng đợi bền vững:** tách tốc độ sinh log và tốc độ xử lý; cân nhắc dữ liệu tồn đọng, khả năng replay và bảo vệ chính hàng đợi.
- **Dead-letter/quarantine:** giữ sự kiện không parse hoặc không thể xử lý theo chính sách, tránh bỏ âm thầm; thiết kế quyền truy cập vì sự kiện lỗi có thể chứa dữ liệu nhạy cảm.
- **Idempotency/deduplication:** một luồng gửi lại có thể tạo bản ghi trùng; ưu tiên event ID ổn định, nhưng kiểm tra nguy cơ trùng hoặc va chạm ID.
- **Backpressure và giới hạn thông lượng:** ghi nhận việc drop/sampling hoặc tắc nghẽn; thiết kế ưu tiên khác nhau cho audit event và log vận hành thường.
- **Đích nhận dự phòng/độc lập:** phụ thuộc mức rủi ro và yêu cầu bảo toàn; kiểm tra điều kiện failover và đồng bộ giữa các vùng.

**At-least-once delivery** thường chấp nhận khả năng bản ghi trùng; **at-most-once** có thể mất bản ghi; bảo đảm **exactly-once** toàn tuyến cần kiểm tra cẩn thận từng thành phần và không nên mặc định khi đọc quảng cáo của một sản phẩm. Với audit log quan trọng, tiêu chí phải diễn đạt cụ thể độ trễ, phạm vi và tỷ lệ mất chấp nhận được, đồng thời yêu cầu bằng chứng kiểm chứng.

### Bảo vệ đường truyền

Đường chuyển log cần xác thực danh tính nguồn/đích và mã hóa khi cần (ví dụ TLS, mutual TLS, private endpoint hoặc kết nối bảo vệ theo dịch vụ), quản lý chứng chỉ/secret, quyền tối thiểu và giới hạn điểm nhận. Tránh để collector hoặc API token có quyền đọc/sửa dữ liệu nhiều hơn mức cần thiết. Phải ghi lại việc thay đổi credential, lỗi xác thực và thời điểm collector ngừng hoạt động.

## 6. Chuẩn hóa, làm giàu, lọc và bảo vệ dữ liệu

Một pipeline thường có các bước **validation → parsing → normalization → enrichment → routing → storage**. Mỗi bước có thể tăng giá trị dữ liệu nhưng cũng tạo rủi ro làm sai hoặc mất bằng chứng gốc.

### Normalization không được làm mất ý nghĩa của sự kiện

Ví dụ, cùng kết quả đăng nhập thất bại có thể được gọi là “denied”, “failure” hoặc mã số nội bộ từ ba nguồn. Schema chuẩn hóa có thể ánh xạ thành một trường outcome chung, nhưng nên giữ **source event code**, phiên bản parser và dữ liệu thô cần thiết trong phạm vi chính sách. Nếu parser thay đổi cách hiểu các trường, phải có test và khả năng truy vết.

Đối với sự kiện không hợp lệ: không tự động xóa mọi bản ghi không parse được. Cần phân loại lỗi định dạng, giữ bản ghi phù hợp tại khu vực cách ly, thông báo cho owner nguồn và đo tỷ lệ parsing failure.

### Log injection và nguồn dữ liệu không đáng tin cậy

Trường lấy từ request của người dùng (header, URL, tên tệp, tham số, username) có thể chứa dấu xuống dòng hoặc chuỗi được cố ý tạo để giả mạo thêm một bản ghi. Ứng dụng nên ghi log dạng cấu trúc, encode/escape dữ liệu điều khiển, giới hạn độ dài và không ghép nội dung đầu vào trực tiếp vào định dạng log dễ bị phá vỡ. UI tra cứu phải encode dữ liệu khi hiển thị, tránh dùng nội dung sự kiện làm lệnh hoặc biểu thức truy vấn đáng tin cậy.

### Lọc dữ liệu nhạy cảm đúng thời điểm

Ưu tiên **không sinh bí mật trong log ngay từ nguồn**. Sau đó có thể dùng bộ lọc/redaction ở collector hoặc pipeline như lớp phòng vệ bổ sung. Nếu chỉ che bí mật lúc hiển thị trên dashboard, dữ liệu nhạy cảm vẫn tồn tại ở hàng đợi, bản thô hoặc kho lưu trữ. Kiểm tra việc lọc bằng dữ liệu thử an toàn và xem xét cả log lỗi, stack trace, URL query, header và message tự do.

Một số trường như địa chỉ IP, user ID, địa chỉ email hoặc truy vấn database có thể phục vụ điều tra nhưng cần giới hạn quyền truy cập, thời hạn lưu và mục đích sử dụng theo chính sách. Quy định bảo vệ dữ liệu khác nhau theo phạm vi pháp lý; không đặt thời gian giữ dữ liệu chung cho mọi quốc gia, ngành hoặc loại log.

## 7. Bảo mật, tính toàn vẹn và vòng đời lưu trữ

Kho log thường chứa thông tin nhạy cảm về hạ tầng và người dùng, đồng thời có thể là bằng chứng trong điều tra. Vì vậy, hệ thống lưu log phải được bảo vệ như một tài sản quan trọng.

| Yêu cầu | Biện pháp thường dùng | Bằng chứng cần xác nhận |
|---|---|---|
| **Confidentiality** | Mã hóa đường truyền và khi lưu, giới hạn role truy vấn/xuất log, tách tenant. | Cấu hình mã hóa/key policy, quyền truy cập hiệu lực, audit hoạt động truy vấn và export. |
| **Integrity / chống sửa trái phép** | Quyền ghi tách quyền xóa, lưu trữ append-only hoặc WORM nếu phù hợp, checksum/hash chain theo nhu cầu. | Trạng thái retention lock, quyền quản trị, bản ghi thay đổi policy, thử truy cập sửa/xóa được phép. |
| **Availability** | Buffer, queue, lưu trữ phù hợp, theo dõi quota, kế hoạch dự phòng/phục hồi. | Kiểm tra truy vấn sau sự cố, tình trạng replica/backup và diễn tập phục hồi phù hợp. |
| **Retention** | Lịch giữ/xóa theo loại log, yêu cầu kiểm toán và data classification. | Policy retention, lifecycle, kiểm tra dữ liệu hết hạn, quy trình giữ phục vụ điều tra. |
| **Access accountability** | Role riêng cho operator, analyst, auditor; phê duyệt truy cập; audit mọi thao tác nhạy cảm. | IAM mapping, access review, log truy vấn/xóa/export, ticket phê duyệt. |
| **Provenance** | Định danh nguồn, thời điểm thu thập, phiên bản collector/parser và đường đi. | Source ID, pipeline metadata, version, evidence chain hoặc audit trail. |

### Tamper resistance khác bất biến tuyệt đối

Việc bật cơ chế **immutable/WORM retention** có thể giảm rủi ro sửa/xóa log trong một thời hạn, nhưng mức bảo vệ phụ thuộc cấu hình và quyền quản trị. Một tài khoản có quyền thay đổi policy khóa lưu giữ, thay khóa mã hóa hoặc làm gián đoạn việc ghi log vẫn có thể gây mất khả năng quan sát, dù dữ liệu đã lưu không dễ xóa.

Cần xem xét tách biệt **quyền quản lý workload** và **quyền thay đổi hệ thống lưu log**, cảnh báo khi tắt audit/đổi retention và khả năng bảo toàn chứng cứ ở vị trí được kiểm soát độc lập. Không tuyên bố “không thể bị sửa” nếu chưa xác định đầy đủ threat model và quyền hiệu lực.

### Retention, legal hold và xóa dữ liệu

Tổ chức phải xác định thời hạn giữ phù hợp theo mục đích: truy vấn nóng ngắn hạn, kho lưu trữ dài hạn hoặc yêu cầu giữ phục vụ điều tra. Có thể phân tầng theo loại log và giá trị điều tra. Khi áp dụng legal hold hoặc retention lock, phải bảo đảm cơ chế cấp phép và kết thúc giữ phù hợp nghĩa vụ pháp lý. Cần có khả năng chứng minh dữ liệu được giữ đúng hạn và được xóa sau khi hết hạn theo chính sách, trừ khi có căn cứ hợp lệ để tiếp tục giữ.

Thiết kế nên tính cả **chi phí ingest**, băng thông, indexing, truy vấn, storage, bản sao và export. Việc cắt log đột ngột vì vượt chi phí có thể làm mất chứng cứ; các chính sách sampling/lọc phải được quản trị và kiểm tra theo mức độ quan trọng của sự kiện.

## 8. Từ log tập trung đến phát hiện và phản ứng

Centralized logging cung cấp dữ liệu đầu vào cho monitoring, nhưng không tự tạo ra quy trình xử lý sự cố. Đối với từng kịch bản rủi ro, cần xác định sự kiện, logic phát hiện, ngưỡng, người nhận và cách xử lý.

| Mục tiêu phát hiện | Nguồn và tín hiệu cần có | Điều kiện kiểm tra |
|---|---|---|
| Tài khoản đặc quyền bị lạm dụng | IdP/SSO, IAM, cloud audit: đăng nhập lạ, thay đổi quyền, bỏ MFA. | Tạo sự kiện thử hợp lệ, xác nhận rule phát hiện và alert đến đúng owner. |
| Log bị vô hiệu hóa | Control-plane audit, cấu hình collector/agent, thay đổi policy lưu trữ. | Kiểm tra cảnh báo khi nguồn mất heartbeat hoặc cấu hình bị thay đổi. |
| Truy cập dữ liệu nhạy cảm bất thường | Application/data access audit, IAM, DB audit theo nhu cầu. | Đánh giá khả năng liên kết actor–resource–action–outcome và tránh truy cập dữ liệu thật trái phép. |
| Di chuyển từ development sang production | Identity federation, network, API audit, workload log. | Kiểm tra correlation ID, principal và luồng kết nối giữa các môi trường. |
| Hoạt động quản trị ngoài cửa sổ thay đổi | Audit hệ thống, change ticket, deployment record. | Tương quan thời điểm/owner và phân biệt bảo trì hợp lệ. |

Một quy trình cần kiểm tra đủ **thu nhận → phân tích → alert → phân công → phản ứng → đóng ticket**. Sự kiện đã có trong kho nhưng rule không phát hiện vẫn là lỗ hổng kiểm soát phát hiện; alert xuất hiện nhưng không ai xử lý cũng chưa đáp ứng mục tiêu vận hành assurance.

### Tương quan cần dữ liệu đáng tin cậy

Ví dụ, có thể ghép login của IdP với thao tác API theo principal và khoảng thời gian; ghép log ứng dụng với trace ID và host ID; hoặc tìm các thay đổi quyền ngay trước truy vấn dữ liệu bất thường. Những phép ghép này bị ảnh hưởng bởi clock skew, thiếu định danh, dùng chung tài khoản dịch vụ hoặc dữ liệu đến trễ. Khi thiếu bằng chứng, kết luận nên nói rõ **mức tin cậy và giới hạn tương quan**, thay vì coi mọi phép nối là chứng minh tuyệt đối về tác nhân.

## 9. Assurance controls: Chuyển yêu cầu thành phép kiểm tra có bằng chứng

Để đánh giá chương trình centralized logging, nên lập **control register** liên kết các nguồn trong phạm vi với mục tiêu và người chịu trách nhiệm. Ví dụ:

| Control ID | Mục tiêu | Tiêu chí có thể kiểm chứng | Bằng chứng |
|---|---|---|---|
| LOG-COV-01 | Có log từ mọi nguồn quan trọng trong phạm vi. | Mỗi cặp (nguồn, loại sự kiện bắt buộc) có cấu hình thu thập và sự kiện xác minh trong kỳ. | Inventory, config export, sự kiện thử hoặc log thực tế được phép, coverage report. |
| LOG-TRN-01 | Vận chuyển log bảo vệ và có khả năng phát hiện thất thoát. | Các kết nối chính được xác thực/mã hóa theo yêu cầu; có giám sát queue, retry, drop và thời gian trễ. | Cấu hình agent/transport, trạng thái queue, test gián đoạn có kiểm soát. |
| LOG-INT-01 | Hạn chế sửa/xóa bằng chứng trái phép. | Quyền ghi, đọc, quản trị và xóa được tách theo chính sách; thao tác thay đổi được audit. | IAM policy hiệu lực, cấu hình lock/retention, kiểm tra quyền và log thay đổi. |
| LOG-DAT-01 | Giảm rò rỉ bí mật và dữ liệu cá nhân trong log. | Event schema và redaction kiểm soát trường nhạy cảm theo chính sách. | Test log giả lập, kiểm tra pipeline thô và đích lưu, data access review. |
| LOG-RET-01 | Lưu và truy xuất log đúng thời hạn. | Log bắt buộc có thể truy vấn sau thời gian giữ tối thiểu, được xóa theo chính sách khi hết hạn. | Lifecycle config, mẫu truy vấn theo kỳ, biên bản thử truy xuất/xóa. |
| LOG-MON-01 | Phát hiện hỏng pipeline và mất nguồn. | Nguồn ngừng gửi hoặc vượt ngưỡng ingest lag được cảnh báo đến owner. | Heartbeat/source freshness dashboard, synthetic test, alert/ticket. |
| LOG-DET-01 | Những kịch bản bảo mật trọng yếu có thể phát hiện và phản hồi. | Use case thử được từ sự kiện nguồn đến ticket/response. | Rule version, sự kiện thử, alert, ACK/ticket và biên bản diễn tập. |

Tiêu chí mẫu là định hướng; mức thời gian, danh mục sự kiện và loại log bắt buộc phải được tổ chức phê duyệt theo rủi ro. Control ID là giá trị minh họa, không phải mã của một framework chính thức.

### Định nghĩa kết quả kiểm soát

| Trạng thái | Khi nào sử dụng |
|---|---|
| **PASS** | Có bằng chứng đủ mới, đúng phạm vi, chứng minh các tiêu chí áp dụng đã được đáp ứng. |
| **FAIL** | Có bằng chứng cấu hình hoặc hành vi thực tế không đáp ứng yêu cầu: nguồn bị thiếu, log thất thoát, quyền sai hoặc alert không hoạt động. |
| **INCONCLUSIVE** | Không đủ dữ liệu hoặc phạm vi, lỗi kiểm tra, không xác định được hiệu lực của policy hay độ trễ. |
| **NOT_APPLICABLE** | Kiểm soát/loại sự kiện thực sự không áp dụng và có lý do được xác nhận. |

Một **ngoại lệ được phê duyệt** không tự làm kết quả kỹ thuật biến thành PASS. Khi một nguồn log chưa thể xuất vì giới hạn API, cần nêu lỗ hổng quan sát, biện pháp bù trừ, người chấp nhận rủi ro và thời điểm đánh giá lại.

## 10. Quy trình kiểm thử end-to-end

Đây là phần quan trọng nhất để chuyển cấu hình logging từ trạng thái “có vẻ đúng” thành assurance dựa trên bằng chứng.

### Bước 1 — Chốt phạm vi và bản đồ sự kiện

Xác định account, cluster, ứng dụng, tenant, nguồn và loại sự kiện bắt buộc. Đánh dấu những nguồn được CSP quản lý và giới hạn có thể truy cập. Chọn một hoặc nhiều sự kiện thử đại diện cho từng tuyến thu thập; không thử trên dữ liệu nhạy cảm thật.

### Bước 2 — Kiểm tra cấu hình từng lớp

Xác minh log ở nguồn đã bật, agent hoạt động, quyền đọc nguồn đủ, connector có quyền API cần thiết, routing đúng đích, queue còn dung lượng, parser đúng phiên bản và retention áp dụng. Kiểm tra nguồn log mới/cụm autoscaling có tham gia pipeline hay không.

### Bước 3 — Phát sinh sự kiện thử có kiểm soát

Ví dụ, dùng một danh tính thử trong môi trường được ủy quyền để thực hiện **một lần đăng nhập thất bại chủ động** hoặc thao tác ứng dụng không nhạy cảm đã thiết kế riêng cho kiểm thử. Ghi lại actor thử, timestamp, event ID/correlation ID và điểm nguồn. Không tạo hành vi tấn công thật, không dùng dữ liệu cá nhân thật hoặc gây ảnh hưởng lớn tới hệ thống.

### Bước 4 — Theo dõi sự kiện qua các chặng

Kiểm tra log nguồn có sự kiện, collector đã đọc, queue đã nhận, parser không loại bỏ, dữ liệu tới đích lưu, có thể truy vấn theo ID và sự kiện được hiển thị đủ trường cần thiết. Ghi **event_time**, **ingest_time**, độ trễ, trường bị mất/sai, vấn đề duplicate và nguồn không có dữ liệu.

Nếu không tìm thấy sự kiện, không tự suy luận rằng phía nguồn không tạo log. Cần điều tra ở từng chặng và ghi rõ chặng đầu tiên thiếu bằng chứng.

### Bước 5 — Kiểm tra phát hiện và phản ứng

Với một use case đã phê duyệt, kích hoạt sự kiện thử an toàn và xác nhận rule nhận dữ liệu, sinh alert, định tuyến đến đúng kênh, được ACK hoặc tạo ticket theo quy trình. Cần ghi thời gian thực tế và kết quả, không chỉ lưu screenshot dashboard.

### Bước 6 — Kiểm tra tình huống lỗi

Tại môi trường kiểm thử hoặc trong cửa sổ được cho phép, mô phỏng mất kết nối hoặc lỗi parse; quan sát buffer/retry, cảnh báo backlog, drop, dead-letter và khả năng khôi phục. Không chủ động ngắt log production hoặc xóa log đang phục vụ điều tra nếu không có thẩm quyền và kế hoạch an toàn.

### Bước 7 — Đối chiếu và đóng phát hiện

So sánh kết quả với tiêu chí: coverage, độ trễ tối đa, thời gian lưu, quyền truy cập, khả năng phát hiện. Tạo finding khi FAIL hoặc INCONCLUSIVE; gán owner, biện pháp sửa, thời hạn và retest. Lưu tất cả bằng chứng với control ID, phiên bản baseline và thời điểm kiểm tra.

~~~mermaid
flowchart TD
    A["Control, nguồn log và tiêu chí đạt"] --> B["Xác minh cấu hình và quyền"]
    B --> C["Tạo sự kiện thử được phép"]
    C --> D["Truy vết source, collector, queue, parser, storage"]
    D --> E{"Có đủ bằng chứng?"}
    E -->|Không| F["INCONCLUSIVE: bổ sung bằng chứng"]
    E -->|Có| G{"Đạt tiêu chí?"}
    G -->|Có| H["PASS và lưu evidence"]
    G -->|Không| I["FAIL, finding và owner"]
    I --> J["Sửa lỗi và retest"]
    F --> B
    J --> C
~~~

## 11. Một hồ sơ bằng chứng logging hoàn chỉnh trông thế nào?

Mẫu YAML dưới đây chỉ minh họa nội dung control register; không phải cấu hình sẵn để chạy trên một hệ thống cụ thể.

~~~yaml
control_id: LOG-COV-01
control_name: "Centralized security audit log coverage"
baseline_version: "2026.11"
scope:
  environment: "production"
  account: "orders-prod-example"
  source: "identity-provider"
  event_type: "authentication_failure"
  region: "region-a"

responsibility:
  accountable: "Orders Service Owner"
  source_owner: "Identity Platform Team"
  pipeline_owner: "Observability Team"
  assurance_reviewer: "Security Assurance Team"

acceptance_criteria:
  event_generated_at_source: true
  event_reaches_central_store: true
  required_fields:
    - event_time
    - source.service
    - event.action
    - event.outcome
    - actor.id
  max_ingestion_lag_seconds: 120
  alert_route_verified: true

test:
  id: "LOG-TEST-EXAMPLE-005"
  executed_at_utc: "2026-11-28T03:15:20Z"
  synthetic_event_id: "test-auth-005"
  source_event_found: true
  collector_observed: true
  storage_query_found: true
  measured_ingestion_lag_seconds: 18
  alert_received: false

result: "FAIL"
finding:
  id: "LOG-FINDING-005"
  description: "Sự kiện đến kho log nhưng chưa tới kênh cảnh báo theo use case"
  owner: "Security Monitoring Team"
  next_action: "Kiểm tra rule, định tuyến alert và chạy lại test"
  evidence_reference: "evidence/log-review/LOG-TEST-EXAMPLE-005"
~~~

Mốc 120 giây, số đo 18 giây và các ID đều là **giả định**, chỉ phục vụ ví dụ. Với control này, điều kiện ingest đã đạt nhưng alert chưa được nhận; kết quả tổng thể **FAIL** vì tiêu chí phát hiện/định tuyến cũng nằm trong phạm vi đã xác định. Khi có nhiều control riêng, có thể ghi PASS cho ingest và FAIL cho alert để xác định chính xác owner, nhưng không gộp thành PASS chung khi mục tiêu cuối chưa đạt.

### Hồ sơ evidence nên bảo toàn điều gì?

Bản ghi tối thiểu gồm: control ID, asset/source ID, người/nhóm chịu trách nhiệm, thời điểm UTC, loại sự kiện, phương pháp thu thập, phiên bản rule/parser, kết quả nguồn–đích, dấu vết pipeline, truy vấn dùng để xác minh, bằng chứng cảnh báo/ticket, ngoại lệ và kết quả retest.

Khi cần chia sẻ bằng chứng ngoài nhóm vận hành, xuất một tập đã được lọc dữ liệu nhạy cảm, có đường dẫn trong kho kiểm soát quyền. Với yêu cầu kiểm tra tính toàn vẹn, tổ chức có thể ghi hash và audit trail cho artifact bằng chứng; hash riêng lẻ không chứng minh nguồn đã tạo đầy đủ mọi sự kiện nếu pipeline đã bỏ sót trước đó.

## 12. Đo lường chất lượng Centralized logging

Chỉ số hữu ích cần gắn với phạm vi, khoảng đo và ngưỡng đã được tổ chức xác định.

| Chỉ số | Cách diễn giải | Điều dễ bị bỏ sót |
|---|---|---|
| **Source coverage** | Số nguồn bắt buộc được cấu hình và kiểm chứng / tổng nguồn bắt buộc trong inventory. | Nguồn mất quyền API, tài khoản mới, node tạm thời chưa xuất log. |
| **Event-class coverage** | Số cặp (nguồn, loại sự kiện bắt buộc) được kiểm tra thành công / tổng cặp áp dụng. | Một nguồn gửi log chung nhưng thiếu audit event quan trọng. |
| **Ingestion lag** | Chênh lệch ingest_time và event_time trong phạm vi đo. | Đồng hồ nguồn lệch, webhook/API xuất chậm, queue backlog. |
| **Pipeline error/drop rate** | Tỷ lệ lỗi thu nhận, parse, chuyển tiếp hoặc bản ghi bị loại theo telemetry. | Không đo được các bản ghi chưa bao giờ tới collector. |
| **Source freshness** | Thời gian từ sự kiện cuối hoặc heartbeat gần nhất. | Nguồn ít hoạt động có thể im lặng bình thường; cần sự kiện heartbeat hoặc test. |
| **Query/retention availability** | Có thể truy vấn dữ liệu mong muốn trong kỳ lưu bắt buộc. | Dữ liệu nằm trong archive nhưng không khôi phục được theo yêu cầu. |
| **Detection-to-alert latency** | Thời gian từ event đến alert có thể hành động. | Có alert nhưng chưa được chuyển tới người chịu trách nhiệm. |
| **Alert delivery và response** | Tỷ lệ test alert đến đúng nơi, được ACK/xử lý đúng quy trình. | Tự động gửi không chứng minh con người đã xem và phản hồi. |

Ví dụ: inventory liệt kê 50 cặp (nguồn, loại sự kiện) bắt buộc. Có 44 cặp đã có thử nghiệm thành công trong kỳ, 3 cặp chưa test, 2 cặp thiếu quyền đọc và 1 cặp thất bại. **Coverage được kiểm chứng = 44/50 = 88%**. Nếu chỉ đo 44 cặp thành công rồi công bố “100% pipeline healthy”, báo cáo đã bỏ qua 6 cặp còn thiếu kết luận.

Nên xem các chỉ số này **đồng thời**: số sự kiện giảm có thể do giảm tải thật hoặc nguồn ngừng phát; số alert giảm có thể do cải thiện bảo mật hoặc rule bị tắt. Việc hệ thống “không báo lỗi” chưa đủ chứng minh các sự kiện bắt buộc vẫn đang được thu.

## 13. Những sai lầm phổ biến và cách khắc phục

| Sai lầm | Hệ quả đối với assurance | Cách khắc phục |
|---|---|---|
| Bật log nhưng không kiểm tra từ đầu đến cuối. | Không biết sự kiện có đến đích, có parse đúng hay không. | Thực hiện synthetic end-to-end test và lưu kết quả từng chặng. |
| Chỉ dựa vào dashboard “agent healthy”. | Agent có thể chạy nhưng quyền đọc nguồn sai hoặc nguồn im lặng. | Kiểm tra event-class coverage, heartbeat và nguồn log thực tế. |
| Dùng một số đo tổng lưu lượng để kết luận không mất log. | Có thể mất riêng loại audit quan trọng khi volume chung vẫn cao. | Theo dõi coverage theo nguồn/loại event và lỗi pipeline. |
| Chỉ giữ log ở workload/container. | Log biến mất khi pod, VM hoặc đĩa bị xóa/thay thế. | Gửi ra kho phù hợp, kiểm tra buffer và retention. |
| Tắt audit để giảm chi phí mà không phân tích rủi ro. | Tạo khoảng trống điều tra hoặc không đáp ứng yêu cầu kiểm soát. | Phê duyệt policy lọc/sampling theo mục tiêu, đo tác động trước thay đổi. |
| Đưa token, mật khẩu hoặc toàn bộ request vào log. | Kho tập trung trở thành nguồn lộ thông tin nhạy cảm. | Sửa log tại nguồn, redaction trong pipeline, quyền truy cập và retention phù hợp. |
| Cho quản trị workload toàn quyền xóa log tập trung. | Người có đặc quyền có thể xóa hoặc vô hiệu hóa bằng chứng. | Tách nhiệm vụ, hạn chế quyền, audit thao tác quản trị và cơ chế bảo vệ phù hợp. |
| Không phân biệt event_time và ingest_time. | Điều tra nhầm thứ tự sự kiện hoặc báo trễ không chính xác. | Giữ cả hai trường, đồng bộ đồng hồ và đo skew. |
| Bỏ sự kiện parser lỗi. | Các sự kiện bất thường hoặc thay đổi schema biến mất âm thầm. | Quarantine, alert parsing failure, xử lý theo owner nguồn. |
| Coi có SIEM là đã có phản ứng. | Alert chưa được gửi, triage hoặc chuyển thành hành động. | Kiểm thử cả kịch bản phát hiện, định tuyến, ACK và ticket. |
| Dùng chung một retention cho mọi loại log. | Lưu quá lâu dữ liệu nhạy cảm hoặc xóa sớm chứng cứ bắt buộc. | Phân loại theo mục đích và quy định áp dụng, chứng minh lifecycle. |
| Chỉ kiểm tra một account hoặc region. | Bỏ sót môi trường mới, luồng SaaS hoặc nguồn thứ ba. | Đối chiếu inventory, kiểm tra completeness trước khi tính tỷ lệ đạt. |

## 14. Tình huống thực hành: Log có ở nguồn nhưng không có trong SIEM

Một doanh nghiệp vận hành hệ thống bán hàng trên Kubernetes. Đăng nhập quản trị qua IdP, API chạy trong nhiều pod, đơn hàng lưu trên managed database. Nhóm bảo mật sử dụng SIEM để phát hiện thay đổi quyền bất thường và truy cập dữ liệu nhạy cảm.

Trong một buổi diễn tập, nhóm tạo sự kiện thử **thay đổi nhóm quyền của tài khoản thử** theo quy trình được phép. Sự kiện xuất hiện trong hệ thống audit của IdP, nhưng không tìm thấy trong SIEM sau thời gian tối đa mà chính sách chấp nhận. Dashboard cho thấy collector có kết nối tốt; queue trung gian gần đầy; một số bản ghi IdP gần đây bị lỗi parse sau thay đổi schema. Nhóm quản trị khẳng định “centralized logging đang chạy” vì máy chủ lưu log vẫn hoạt động.

### Câu hỏi

1. Có đủ bằng chứng để đánh giá control phát hiện thay đổi quyền là PASS không?
2. Những chặng nào cần kiểm tra để tìm nguyên nhân?
3. Những bằng chứng nào phải lưu để phục vụ đánh giá và retest?
4. Cần sửa thiết kế như thế nào để một lỗi tương tự được phát hiện sớm?

### Hướng giải quyết

**Bước 1 — Kết luận theo bằng chứng:** Sự kiện đã được xác nhận có ở IdP nhưng chưa đến SIEM theo tiêu chí. Control liên quan **không đạt** ở thời điểm kiểm tra; nếu chưa biết chính xác giới hạn quan sát của từng chặng, ghi rõ phần cần điều tra. Dashboard “collector connected” không đủ chứng minh event delivery.

**Bước 2 — Truy vết các chặng:** Kiểm tra nguồn IdP, permission/cursor của connector, thời điểm polling, bản ghi vào queue, dung lượng/backlog, log retry/drop, phiên bản parser, mục quarantine và đích lưu. Đối chiếu event ID và event_time xuyên suốt; lưu ingest_time từng chặng nếu có.

**Bước 3 — Xác minh tính toàn vẹn và quyền:** Kiểm tra quyền của connector và người vận hành, lịch sử thay đổi cấu hình, quyền truy cập bản ghi lỗi parse và liệu dữ liệu nhạy cảm có bị đưa vào dead-letter hay không. Không xóa dữ liệu lỗi trước khi xác định nhu cầu bảo toàn chứng cứ.

**Bước 4 — Khắc phục:** Sửa mapping schema có kiểm thử, thiết lập alert backlog/parser error, kiểm tra retry/replay các bản ghi tồn (nếu nguồn/hàng đợi hỗ trợ và nằm trong phạm vi được phép), giám sát quota, bổ sung canary event cho loại audit quan trọng.

**Bước 5 — Retest:** Tạo sự kiện mới trong phạm vi được duyệt, xác nhận hiện diện từ IdP tới lưu trữ/SIEM, độ trễ dưới ngưỡng, trường actor/action/outcome đúng và alert/ticket được tạo. Nếu replay được dữ liệu cũ, cần tách rõ kết quả phục hồi lịch sử và kết quả vận hành ổn định sau sửa.

**Bước 6 — Báo cáo:** Lưu asset/source ID, control ID, thời điểm, phạm vi, bản ghi thử được lọc, cấu hình trước/sau, ticket, người chịu trách nhiệm và thời điểm retest. Kết quả cuối cùng chỉ chuyển PASS khi bằng chứng đủ cho các tiêu chí đã phê duyệt.

## 15. Checklist thực hành cho Security Assurance

Trước khi đánh dấu một hệ thống centralized logging là đạt yêu cầu, hãy xác nhận:

1. **Phạm vi:** Có inventory nguồn log, account, region, tenant, cluster và loại sự kiện bắt buộc, cùng phần chưa bao phủ không?
2. **Trách nhiệm:** Đã xác định ai bật log ở nguồn, ai vận hành collector/queue, ai quản trị kho và ai phản ứng với alert chưa?
3. **Chất lượng sự kiện:** Có event_time, source, actor, action, outcome, correlation ID khi cần, schema version và cách xử lý đồng hồ lệch không?
4. **Truyền tải:** Có xác thực/mã hóa, buffer/retry, giám sát backlog/drop, quarantine và phương án khôi phục phù hợp không?
5. **Quyền và bảo mật:** Có ngăn bí mật bị ghi log, giới hạn quyền truy cập/xóa/export, audit hoạt động quản trị và bảo vệ bằng chứng không?
6. **Retention:** Đã quy định và kiểm chứng thời hạn lưu, truy xuất, phân tầng, xóa dữ liệu và legal hold nếu áp dụng chưa?
7. **Kiểm tra đầu-cuối:** Đã phát sinh sự kiện thử an toàn, đối chiếu từng chặng, truy vấn đích và đo thời gian trễ thực tế chưa?
8. **Phát hiện và phản ứng:** Rule sử dụng đúng dữ liệu, alert tới đúng owner và có bằng chứng triage/ACK/ticket chưa?
9. **Kết luận:** PASS, FAIL, INCONCLUSIVE và NOT_APPLICABLE được dùng nhất quán, có evidence, owner, risk exception và retest chưa?
10. **Liên tục:** Có kiểm tra khi thêm nguồn mới, đổi schema, đổi quyền API, thay retention, nâng cấp pipeline và khi xuất hiện mất heartbeat không?

**Centralized logging chỉ tạo ra giá trị security assurance khi tổ chức chứng minh được log quan trọng được sinh ra, đến được nơi lưu/truy vấn, giữ đúng nội dung và thời hạn, được bảo vệ phù hợp và phục vụ phát hiện–điều tra–khắc phục trong thực tế.**
