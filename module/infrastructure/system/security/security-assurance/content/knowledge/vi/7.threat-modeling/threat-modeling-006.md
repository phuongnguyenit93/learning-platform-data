# Attack surface – Nhận diện và kiểm chứng bề mặt tấn công

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **attack surface (bề mặt tấn công)** và phân biệt nó với tài sản, điểm yếu, đường tấn công, mô hình đe dọa và mức rủi ro.
- Nhận diện điểm vào, giao diện, danh tính, luồng dữ liệu và ranh giới tin cậy mà tác nhân đe dọa có thể tác động tới ở ứng dụng Java, dịch vụ cloud và quy trình phát triển.
- Xây dựng **attack surface inventory** và **data flow diagram (DFD)** có chủ sở hữu, phạm vi và thời điểm, kể cả bề mặt nội bộ, không công khai và phụ thuộc bên thứ ba.
- Kết hợp các phương pháp khám phá từ thiết kế, mã nguồn, tài sản thực chạy, cấu hình và kiểm thử để phát hiện phần bề mặt bị bỏ sót.
- Chuyển kết quả nhận diện thành threat scenarios, yêu cầu bảo mật, security controls, trường hợp kiểm thử, hồ sơ bằng chứng và kế hoạch giảm thiểu.
- Duy trì đánh giá bề mặt tấn công **liên tục** qua release, thay đổi IAM, cấu hình mạng, dependency và sự kiện vận hành.

## 1. Attack surface là gì?

**Attack surface** là tập hợp những điểm, giao diện, khả năng hoặc đường tương tác mà qua đó một tác nhân đe dọa có thể cố gắng tác động đến tài sản, dữ liệu, hành vi hoặc quyền của hệ thống. Điểm tương tác có thể là một API trên Internet, một endpoint nội bộ, tài khoản có quyền quản trị, webhook, file import, message queue, thành phần cung cấp bản cập nhật, hoặc giao diện dành cho con người.

Một phần bề mặt tấn công có thể **được chủ ý cung cấp** cho người dùng hợp lệ. Ví dụ chức năng thanh toán phải tiếp nhận request. Mục tiêu không phải triệt tiêu mọi bề mặt, mà là **biết chính xác nó tồn tại ở đâu, vì sao cần tồn tại, ai được phép sử dụng, được kiểm soát thế nào và có bằng chứng gì cho kết luận đó**.

Trong module **SECURITY_SECURITY_ASSURANCE**, nhận diện attack surface là một bước giúp biến phân tích rủi ro thành mục tiêu, yêu cầu, security controls, phép kiểm thử, audit và hoạt động khắc phục. Một chương trình assurance có thể báo “mọi endpoint đã được kiểm tra quyền” chỉ khi có căn cứ về **những endpoint nào thực sự tồn tại** và phạm vi nào được bao phủ. Một endpoint bị quên trong inventory làm suy yếu cả kết luận, dù mọi bài kiểm thử hiện tại đều đạt.

### Phân biệt thuật ngữ

| Khái niệm | Câu hỏi chính | Minh họa |
| --- | --- | --- |
| **Asset (tài sản)** | Điều gì có giá trị cần bảo vệ? | Báo cáo khách hàng, khóa ký, dữ liệu đơn hàng. |
| **Attack surface** | Tác nhân có thể tác động vào hệ thống từ đâu? | `/api/reports/{id}/export`, ingress, role IAM, giao diện admin. |
| **Entry point (điểm vào)** | Tương tác bắt đầu qua giao diện cụ thể nào? | Request tới endpoint export, một message gửi vào queue. |
| **Trust boundary (ranh giới tin cậy)** | Dữ liệu/quyền đi qua vùng có giả định tin cậy khác nhau ở đâu? | Internet → API; tenant A → dữ liệu tenant B; ứng dụng → cloud IAM. |
| **Vulnerability (điểm yếu/lỗ hổng)** | Kiểm soát hoặc triển khai nào có thể bị khai thác? | Endpoint export không kiểm tra quyền trên report ID. |
| **Attack vector (phương thức tấn công)** | Kỹ thuật hoặc cách tương tác nào được dùng? | Thay ID đối tượng, gửi file độc hại, lạm dụng token. |
| **Attack path (đường tấn công)** | Những bước và điều kiện nào nối điểm vào tới mục tiêu? | Token bị lộ → worker có quyền rộng → lấy dữ liệu storage. |
| **Risk scenario (kịch bản rủi ro)** | Điều kiện nào tạo hậu quả gì, cho tài sản nào? | Người dùng tenant A xuất được báo cáo B dẫn đến lộ thông tin. |
| **Attack surface management** | Ai quản lý trạng thái, thay đổi và ưu tiên xử lý? | Phát hiện endpoint mới, xác định owner, kiểm tra exposure và theo dõi sửa. |

**Có bề mặt tấn công không đồng nghĩa có lỗ hổng.** Một API public được thiết kế đúng vẫn là attack surface. Ngược lại, một điểm yếu nghiêm trọng trong tính năng chỉ gọi được nội bộ vẫn có thể quan trọng nếu attacker chiếm được workload hoặc quyền nội bộ.

**Giảm số cổng mở không tự đồng nghĩa giảm rủi ro.** Đóng một cổng thử nghiệm không dùng là hữu ích; việc chuyển toàn bộ chức năng rủi ro cao sang một cổng 443 vẫn để lại bề mặt tấn công về nghiệp vụ và danh tính.

## 2. Ranh giới phạm vi: bên ngoài, bên trong và đường cung ứng

Một bài threat modeling phải nêu rõ **ai được giả định là tác nhân có thể gây hại**. Không nên chỉ xét người lạ trên Internet; người dùng đã đăng nhập, tenant khác, nhân sự có đặc quyền, workload bị chiếm, nhà cung cấp hoặc pipeline bị xâm nhập đều có thể tác động lên hệ thống ở những mức khác nhau.

### Các nhóm bề mặt tấn công

| Nhóm | Điểm tương tác điển hình | Câu hỏi cần hỏi |
| --- | --- | --- |
| **Web/API công khai** | Website, REST, GraphQL, upload, callback, websocket | Được gọi bởi ai, có xác thực/phân quyền, rate limit và validation không? |
| **API và hạ tầng nội bộ** | Service-to-service, gRPC, queue, internal ingress, database port | Mạng nội bộ có bị coi là đáng tin tuyệt đối không; workload identity được kiểm tra thế nào? |
| **Danh tính và quyền** | Tài khoản, phiên, token, IAM role, service account, SSO, key | Có ai giữ quyền quá rộng, khóa dùng chung hoặc tài khoản cũ chưa thu hồi? |
| **Dữ liệu và lưu trữ** | Database, object storage, backup, export, cache, search index | Có đường đọc trực tiếp, signed URL, bản sao dữ liệu, quyền truy cập phụ không? |
| **Quản trị và quan sát** | Admin UI, Actuator, metrics, tracing, dashboard, debug interface | Có lộ cấu hình, thông tin nhạy cảm hoặc thao tác đặc quyền không? |
| **Nền tảng và mạng** | Ingress, DNS, CDN, load balancer, Kubernetes API, host, container runtime | Quy tắc inbound/outbound, segmentation, policy và cấu hình đang chạy ra sao? |
| **Chuỗi cung ứng và CI/CD** | Repository, build runner, artifact registry, package mirror, pipeline secret | Ai có thể thay code, build, dependency, artifact và bản triển khai? |
| **Con người/quy trình** | Kênh hỗ trợ, phê duyệt thay đổi, chia sẻ file, xử lý sự cố | Có đường bị lợi dụng để cấp quyền, thay dữ liệu hoặc phá vỡ control không? |
| **Bên thứ ba** | Webhook/payment provider, email service, identity provider, SaaS tích hợp | Dữ liệu và quyền đã trao cho đối tác nào, có hợp đồng và kiểm soát phù hợp không? |

Không phải mọi nhóm đều cần cùng mức chi tiết. Phạm vi đánh giá phụ thuộc vào **tài sản quan trọng, mục tiêu bảo mật, môi trường, loại đối thủ và kịch bản hậu quả**. Tuy nhiên, loại trừ một nhóm cần được ghi thành giới hạn, không được ngầm hiểu rằng nhóm đó không tồn tại.

### Bề mặt tấn công khác với đường truy cập Internet

Ví dụ dịch vụ `export-worker` chạy trong subnet riêng, không có public IP. Worker vẫn nhận message từ queue, đọc dữ liệu qua IAM, ghi object storage và kéo image từ registry. Nếu queue bị người gửi không hợp lệ thao túng hoặc IAM role bị lộ, worker vẫn là một phần bề mặt tấn công cần đánh giá.

Một mạng riêng, VPN hoặc service mesh có thể giảm mức phơi lộ từ một số tác nhân nhưng không thay thế **xác thực danh tính workload, ủy quyền theo tài nguyên và theo dõi control ở runtime**.

## 3. Từ tài sản và luồng dữ liệu đến attack surface

Hãy xem nền tảng xuất báo cáo đa tenant. Người dùng truy cập API Java/Spring Boot thông qua gateway. API tạo job; worker lấy dữ liệu từ database và ghi file vào storage; người dùng nhận một đường dẫn tải file.

~~~mermaid
flowchart TD
    U["Người dùng Internet"] --> GW["DNS / CDN / API Gateway"]
    GW --> API["Spring Boot report-api"]
    IAM["Identity Provider"] --> API
    API --> Q["Message Queue"]
    Q --> W["Export Worker"]
    W --> DB[("Database đa tenant")]
    W --> ST[("Object Storage / CSV")]
    API --> ST
    ST --> U
    CI["CI/CD + Artifact Registry"] --> API
    CI --> W
    API --> LOG["Audit / Log Collector"]
    W --> LOG
~~~

Các **trust boundary** phải được đánh dấu khi phân tích sơ đồ: Internet và gateway; client và API; tenant A và tenant B; API và queue; workload và quyền IAM; hệ thống xử lý và storage; CI/CD và production; hệ thống ghi log và kho bằng chứng.

Một sơ đồ DFD có ích khi mỗi **node và luồng** nêu được:
- Tài sản/dữ liệu xử lý, mức nhạy cảm và mục đích.
- Chủ thể gửi/nhận và danh tính được tin cậy.
- Giao thức, endpoint, cổng, queue/topic hoặc loại message.
- Chính sách xác thực, phân quyền, mã hóa và giới hạn kích thước/tốc độ.
- Quyền tác động tới tài nguyên và vùng mạng.
- Người sở hữu; nơi kiểm tra cấu hình và bằng chứng.
- Môi trường và phiên bản đúng của sơ đồ, cùng các giả định chưa xác minh.

### Lập danh sách điểm vào từ DFD

| ID | Điểm vào / đường tương tác | Tác nhân khả dĩ | Tài sản tác động | Control cần kiểm chứng |
| --- | --- | --- | --- | --- |
| AS-01 | `GET /api/reports/{id}` | Người dùng đã đăng nhập từ tenant khác | Nội dung báo cáo | Authorization cấp đối tượng/tenant |
| AS-02 | `POST /api/exports` | User hoặc client có token bị lạm dụng | Export job, CPU, dữ liệu | Xác thực, quyền tạo job, quota và validation |
| AS-03 | Message queue: `export.requests` | Producer sai quyền hoặc API bị chiếm | Hành vi worker | Producer ACL, message validation, job ownership |
| AS-04 | Worker → object storage | Workload bị lạm dụng | CSV và dữ liệu khách hàng | IAM tối thiểu, policy bucket, thời hạn URL |
| AS-05 | `/actuator/**` và endpoint quản trị | Người có thể tới mạng nội bộ/admin | Cấu hình, thao tác điều khiển | Network boundary, endpoint exposure, auth/authorization |
| AS-06 | CI pipeline và artifact registry | Người có quyền repository hoặc token CI | Image production | Quyền ghi/deploy, review, provenance, secret handling |
| AS-07 | Central log pipeline | Workload hoặc admin có quyền thay log | Bằng chứng và detection | Quyền ghi/xóa, kiểm tra end-to-end, cảnh báo mất log |

Danh sách trên là **giả định mô hình**, chưa chứng minh từng điểm đang mở ở production. Phải đối chiếu với endpoint thực tế, policy và cấu hình đang chạy.

## 4. Cách khám phá bề mặt tấn công có hệ thống

Một workshop chỉ dựa vào sơ đồ kiến trúc có thể bỏ sót “shadow API”, service cũ, resource bị quên hoặc cấu hình thay đổi sau release. Cần **đối chiếu nhiều nguồn độc lập**.

### Bước 1 — Xác định phạm vi và giả định

Ghi danh sách môi trường, domain/account/cluster, namespace, service, tenant, phiên bản, dữ liệu và chủ sở hữu. Phân biệt nơi đánh giá là **design, staging hay production**, và actor nằm ở **Internet, nội bộ, tenant khác hay admin**.

### Bước 2 — Đọc thiết kế và định nghĩa giao diện

Nguồn dữ liệu có thể gồm API contract/OpenAPI, data flow diagram, service catalog, kiến trúc cloud, IAM model, cấu hình ingress, route, event/topic schema, dependency map, CI/CD workflow, chính sách upload/export và runbook. Những nguồn này cho thấy hệ thống **được dự định** hoạt động thế nào.

### Bước 3 — Đối chiếu với cấu hình và tài sản thực chạy

Trong phạm vi được cấp phép, xác minh DNS, ingress, load balancer, API gateway, cloud resources, cluster service, network policy, IAM, exposed management endpoint, object storage policy và actual deployment. Kiểm tra cả tài sản **không có owner**, bản cũ còn phục vụ traffic hoặc endpoint chỉ xuất hiện qua feature flag.

Khi sử dụng công cụ discovery/scan, cần được cấp quyền và cấu hình tốc độ phù hợp để tránh ảnh hưởng production. Kết quả scan là một góc nhìn trong **thời điểm, tài khoản truy cập, mạng nguồn và phạm vi đã cho**, không phải bằng chứng mọi tài sản đều được phát hiện.

### Bước 4 — Xem mã nguồn và hành vi ứng dụng

Đối chiếu route/controller, endpoint dành cho admin, callback, serializer, file parser, message consumer, job scheduler và cơ chế truy cập storage. Đường tương tác có thể chỉ xuất hiện khi có header/role/feature flag cụ thể. Với Spring Boot, cần chú ý cả route của actuator, health, metrics, tài nguyên tĩnh, debug/error response và các thư viện tích hợp.

### Bước 5 — Vẽ ranh giới tin cậy và đường ảnh hưởng

Đối với từng entry point, theo dữ liệu đến tài sản đích và quyền mà request có thể kích hoạt. Kiểm tra khả năng một actor ít quyền điều khiển một hành động đặc quyền, ví dụ gửi `reportId` vào queue làm worker có quyền cao thực thi mà không kiểm tra lại **chủ sở hữu job và tenant**.

### Bước 6 — Hợp nhất, loại trùng và gán owner

Chuẩn hóa tên tài sản, route, environment, identity và nguồn phát hiện. Hai scanner có thể cùng báo một endpoint; không nên đếm hai lần. Ngược lại, cùng một route có thể có **nhiều kiểu giao tiếp và actor** nên cần tách thành các kịch bản khác nhau.

### Bước 7 — Review với người có ngữ cảnh

Developer, Ops/SRE, Security/AppSec, chủ sở hữu dữ liệu và nhóm phụ trách CI/CD cùng xác nhận đường dữ liệu, quyền, tác động và giới hạn. Không một công cụ nào tự biết đủ **ý nghĩa nghiệp vụ** của mỗi điểm vào.

## 5. Từ attack surface đến threat modeling

Attack surface trả lời **“ở đâu có thể tương tác?”**; threat modeling trả lời tiếp **“ai có thể làm gì, cần điều kiện nào, hậu quả là gì và control nào ngăn chặn?”**.

Ví dụ dùng STRIDE như khung gợi ý, không coi là danh sách đầy đủ:

| STRIDE | Câu hỏi trên bề mặt đã nhận diện | Threat scenario minh họa |
| --- | --- | --- |
| **Spoofing** | Actor hoặc workload có thể giả danh không? | Kẻ tấn công dùng token service không được ràng buộc đúng audience. |
| **Tampering** | Input, message hoặc artifact có thể bị sửa trái phép không? | Consumer tin vào trường `tenantId` do message producer không đáng tin gửi. |
| **Repudiation** | Sự kiện quan trọng có đủ bằng chứng để truy vết không? | Chỉnh IAM role mà không có audit event liên kết actor và thay đổi. |
| **Information disclosure** | Có đường nào đọc dữ liệu ngoài quyền không? | Export báo cáo của tenant khác qua API hoặc URL storage. |
| **Denial of service** | Giao diện có thể bị lạm dụng để làm cạn tài nguyên không? | API export cho tạo job không giới hạn, worker bị nghẽn queue. |
| **Elevation of privilege** | Quyền thấp có dẫn tới hành động quyền cao không? | Workload dùng service account có quyền đọc nhiều bucket ngoài phạm vi. |

Không cần gán mọi hàng STRIDE cho mọi endpoint. Tập trung các kịch bản **có điều kiện khả thi và hậu quả đáng quan tâm**, rồi ghi rõ giả định và nguồn thông tin.

### Ví dụ mô tả threat scenario

**RISK-AS-01:** người dùng tenant A đã đăng nhập gửi yêu cầu export với ID báo cáo của tenant B; nếu API/worker chỉ kiểm tra role chung và không đối chiếu quyền cấp đối tượng, worker có thể tạo CSV của tenant B, dẫn tới lộ dữ liệu.

- **Điểm vào:** `POST /api/exports` và message `export.requests`.
- **Trust boundary:** user A → API; API → worker đặc quyền; worker → dữ liệu tenant B.
- **Điều kiện:** attacker có credential hợp lệ và nhận biết hoặc có thể chọn ID báo cáo không thuộc mình.
- **Tài sản và tác động:** nội dung báo cáo nhạy cảm; bí mật và quyền riêng tư.
- **Security control dự kiến:** authorization cấp đối tượng tại lúc tạo và nhận job; IAM tối thiểu; link download ràng buộc tài nguyên và thời hạn; audit logging.
- **Giới hạn:** tính đoán được của ID, chính sách link và thực tế cấu hình phải được xác minh trước khi kết luận likelihood.

Trong thiết kế, có thể bổ sung **abuse case**: user A thay `reportId`; gọi export qua endpoint khác; gọi lại job ID cũ sau khi quyền bị thu hồi; sử dụng link do một user khác tạo; gửi yêu cầu hàng loạt. Các ca này được chuyển thành test có đầu vào và expected result cụ thể.

## 6. Đánh giá và ưu tiên bề mặt tấn công theo rủi ro

Không phải mọi bề mặt có cùng mức ưu tiên. Một endpoint public `/health` chỉ trả trạng thái giới hạn có thể có rủi ro thấp hơn một API admin nội bộ nhưng cho phép xuất toàn bộ dữ liệu.

Nên xem xét đồng thời:

| Yếu tố | Câu hỏi | Dữ liệu hỗ trợ |
| --- | --- | --- |
| **Khả năng tiếp cận (exposure)** | Internet, mạng nội bộ, VPN, tenant khác hay chỉ admin? | Network policy, ingress, kết quả kiểm tra từ góc nhìn thích hợp |
| **Quyền cần có** | Anonymous, user, operator, CI workload hay privileged account? | IAM effective permissions, role mapping, negative tests |
| **Mức nhạy cảm tài sản** | Dữ liệu nào hoặc hành động nào có thể tác động? | Phân loại dữ liệu, tài sản, chủ sở hữu nghiệp vụ |
| **Khả năng khai thác** | Có điều kiện thực tế nào giúp actor sử dụng điểm yếu? | Threat model, kiểm thử, dữ liệu sự cố/advisory phù hợp |
| **Độ rộng ảnh hưởng** | Một đối tượng, một tenant, nhiều tenant hay toàn hệ thống? | Dependency graph, IAM scope, business impact |
| **Hiệu lực control** | Các lớp phòng ngừa/phát hiện/ứng phó có thật sự hoạt động? | Test, cấu hình runtime, log, review |
| **Thời gian phơi lộ** | Điểm tương tác tồn tại từ khi nào và có thay đổi không? | Change history, deployment, inventory, scan |
| **Mức tin cậy của đánh giá** | Có gì chưa biết, chưa quét hoặc chưa được kiểm chứng? | Gap list, coverage và giới hạn của evidence |

Có thể dùng rubric likelihood × impact 5×5 nếu đó là phương pháp được tổ chức phê duyệt. Tuy nhiên, điểm 1–5 là **thang thứ bậc**, không tự tương đương xác suất hoặc thiệt hại tiền tệ. Cũng không nên dùng `số endpoint public × mức CVSS lớn nhất` như một công thức rủi ro có giá trị phổ quát.

Ví dụ hai phát hiện:

| Phát hiện | Kết luận bước đầu | Công việc tiếp theo |
| --- | --- | --- |
| Một endpoint nội bộ chỉ trả telemetry đã làm sạch, có network restriction và xác thực được test | Có attack surface cần theo dõi nhưng chưa đủ cơ sở kết luận rủi ro cao | Đối chiếu quyền và phạm vi thực tế, giữ evidence hiệu lực |
| API export public thiếu kiểm tra tenant, truy cập báo cáo nhạy cảm | Kịch bản lộ dữ liệu rõ; cần ưu tiên triage và giảm thiểu | Tái hiện an toàn, xác định phạm vi, sửa control, retest và đối chiếu deployment |

Nếu một điểm vào không rõ chủ sở hữu, phiên bản hoặc loại dữ liệu, nên gắn **trạng thái chưa đánh giá/độ tin cậy thấp**; không mặc nhiên cho điểm rủi ro thấp.

## 7. Security controls nhằm giảm bề mặt tấn công

Một số biện pháp **giảm số đường tương tác**, số khác **giảm khả năng khai thác hoặc hậu quả** trên bề mặt bắt buộc phải tồn tại. Hai loại đều quan trọng và cần được đánh giá riêng.

### 7.1. Loại bỏ hoặc giới hạn điểm vào không cần thiết

- Xóa hoặc tắt endpoint thử nghiệm, chức năng debug và giao diện quản trị không còn sử dụng.
- Chỉ công bố ingress, route, listener và cổng đúng nhu cầu; kiểm tra cả IPv4/IPv6 và các vùng triển khai được hỗ trợ.
- Không cho phép truy cập công khai tới storage, database, queue hoặc API quản trị khi không có nhu cầu được phê duyệt.
- Tách môi trường development/staging/production, hạn chế dữ liệu thật và tài khoản quyền cao ở môi trường phụ.
- Vô hiệu hóa tài khoản, secret, certificate hoặc integration không còn được dùng; giảm số đường nhờ credential cũ.
- Giảm quyền network và IAM giữa các service đến mức cần thiết, không dựa duy nhất vào vị trí “bên trong mạng”.

Giảm bề mặt thành công phải có **bằng chứng trạng thái thực tế**. Xóa route trong code không đảm bảo bản triển khai cũ, DNS hoặc load balancer không còn phục vụ route đó.

### 7.2. Gia cố những điểm vào cần giữ

- **Xác thực và phân quyền:** danh tính người dùng/workload; kiểm tra resource/action/tenant; từ chối mặc định ở nơi phù hợp.
- **Kiểm tra input:** kích thước, định dạng, allowlist hợp lệ, xử lý parser; tránh tin dữ liệu từ queue/webhook chỉ vì kênh có vẻ nội bộ.
- **Bảo vệ luồng outbound:** ngăn service tự do truy cập đích không phù hợp với nghiệp vụ; giảm rủi ro request qua URL do user cung cấp.
- **Rate limiting và quota:** giảm nguy cơ lạm dụng trên API tốn tài nguyên, phù hợp với người dùng hợp lệ và tình huống phân tán.
- **Quản trị secret và khóa:** tránh bí mật trong code, image, log; xoay/thu hồi theo quy trình, dùng identity ngắn hạn khi phù hợp.
- **Mã hóa và bảo vệ dữ liệu:** TLS, mã hóa dữ liệu lưu trữ khi cần, hạn chế bản sao và quyền đọc các kết quả export.
- **Giám sát:** log sự kiện có ích, thử đường alert và health của pipeline; giám sát thay đổi exposure và IAM.
- **Quản lý dependency/artifact:** kiểm soát nguồn package và quyền phát hành, kiểm tra artifact triển khai, review quyền CI.

Một rule WAF có thể giảm một số kiểu request độc hại, nhưng không tự sửa logic authorization, quyền IAM quá rộng hay đường đọc storage trực tiếp. Phải kiểm tra **đường gây hại cụ thể** sau khi áp dụng control.

## 8. Ví dụ Java/Spring Boot: kiểm soát bề mặt HTTP và quản trị

Giả sử dịch vụ nhận request bên ngoài qua `/api/**`, có nhóm chức năng admin `/api/admin/**`, và cần một health endpoint để hệ thống giám sát. Các endpoint actuator khác không có nhu cầu mở qua HTTP.

Cấu hình Spring Boot minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Cấu hình trên giới hạn **các actuator endpoint được công bố qua web** theo ví dụ. Trong môi trường thực, đường mạng và hành vi endpoint có thể thay đổi theo cấu hình, phiên bản Spring Boot và hạ tầng. Giới hạn HTTP exposure không thay kiểm soát IAM, firewall hoặc auth cho các giao diện quản trị khác.

Minh họa phân quyền request của Spring Security 6 / Spring Boot 3, với ứng dụng API dùng JWT bearer token và chỉ cho phép health endpoint công khai:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/actuator/**").denyAll()
                .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}))
            .build();
    }
}
~~~

Đây là **một phần cấu hình minh họa**: ứng dụng thực tế còn phải cấu hình JWT decoder/issuer/audience, mô hình authority, chính sách session/CSRF theo loại client, cơ chế phân quyền nghiệp vụ và bảo vệ endpoint ở gateway hoặc management port phù hợp. Quy tắc `authenticated()` ở `/api/**` **chưa đủ để bảo vệ dữ liệu từng tenant**; cần tiếp tục kiểm tra quyền trên đối tượng trong controller/service.

### Vì sao cần kiểm chứng ở runtime?

Có thể xuất hiện chênh lệch giữa cấu hình dự kiến và thực tế:

- Deployment sử dụng profile Spring khác, dẫn đến cấu hình exposure khác.
- Một instance cũ hoặc gateway route cũ vẫn phục vụ `/actuator/**`.
- Admin API bị đưa vào route public trong ingress.
- Công cụ monitoring đang gọi health với tham số hoặc địa chỉ khác với thiết kế.
- Một API mới bỏ qua service authorization do dùng đường repository trực tiếp.

Vì vậy, Developer cung cấp cấu hình, PR và test; Ops/SRE xác minh route và ingress đang chạy; Security/assessor đối chiếu tiêu chí và phạm vi bằng chứng.

### Bộ ca kiểm thử tham khảo

| Test ID | Kiểm tra | Kết quả mong đợi theo chính sách ví dụ |
| --- | --- | --- |
| AS-T01 | Gọi `/actuator/health` không có token, từ đường mạng được phép | Chỉ nhận nội dung health tối thiểu đã phê duyệt |
| AS-T02 | Gọi `/actuator/env` từ client không có quyền | Không công bố endpoint hoặc bị từ chối |
| AS-T03 | User thường gọi `/api/admin/jobs` | Bị từ chối |
| AS-T04 | User hợp lệ của tenant A đọc/xuất dữ liệu tenant B | Không trả dữ liệu trái phép |
| AS-T05 | Không xác thực gọi API cần bảo vệ | Bị từ chối theo chính sách API |
| AS-T06 | Route cũ, profile phụ hoặc deployment cũ có khả năng mở management endpoint | Không còn đường truy cập ngoài phạm vi đã phê duyệt |
| AS-T07 | Dịch vụ cố đọc bucket ngoài quyền cần thiết | IAM hoặc policy từ chối thao tác |
| AS-T08 | Tạo sự kiện thay đổi route/IAM thử trong phạm vi được phép | Event được ghi nhận, alert hoạt động khi đúng tiêu chí |

Các expected result cần được đồng bộ với **chính sách và hạ tầng thật**; ví dụ gateway có thể biến HTTP status trong ứng dụng thành một phản hồi khác. Test phải kiểm chứng cả **không lộ dữ liệu**, không chỉ một status code.

## 9. Attack surface inventory và bằng chứng có thể audit

Một bảng kiểm kê bề mặt tấn công không nên chỉ có “URL + open/closed”. Mỗi record cần hỗ trợ truy vết đến **risk scenario, control và kiểm thử**.

| Trường | Ý nghĩa |
| --- | --- |
| Surface ID, tên | Định danh duy nhất, tránh đếm trùng |
| Loại điểm vào | API, network, IAM, queue, storage, admin, supply chain... |
| Asset/service/environment | Hệ thống, tài sản, môi trường, vùng/tenant |
| Actor và trust boundary | Ai có thể tác động, qua ranh giới nào |
| Interface/permission | Route, method, topic, role, network rule hoặc tích hợp |
| Data/action impact | Dữ liệu hoặc hành động nằm sau giao diện |
| Exposure status | Public/internal/restricted/unknown, cách xác minh |
| Control IDs | Cơ chế phòng ngừa, phát hiện và ứng phó |
| Risk/requirement IDs | Kịch bản rủi ro và mục tiêu/tiêu chí kiểm chứng |
| Owner và reviewer | Người vận hành/chịu trách nhiệm và người đánh giá |
| Evidence và thời điểm | Nguồn kiểm tra, phiên bản, kết quả, timestamp |
| Residual exposure/limitation | Phần chưa kiểm thử, giả định và rủi ro còn lại |
| Review trigger | Release, IAM change, route change, incident, kỳ đánh giá |

### Mẫu inventory record

Những giá trị nằm trong dấu `<...>` là placeholder, không phải hiện vật đã quan sát. Các giá trị dùng để mô tả scenario chỉ mang tính minh họa:

~~~yaml
surface_id: AS-EXPORT-001
module: SECURITY_SECURITY_ASSURANCE
type: api
service: report-api
environment: production
interface:
  method: POST
  path: /api/exports
actor: authenticated-user
trust_boundary: "Client -> API -> Queue -> Worker"
asset: customer-reports
data_classification: confidential
exposure: "<PUBLIC_INTERNAL_RESTRICTED_WITH_EVIDENCE>"
owner: "<SERVICE_OWNER>"
risk_ids:
  - RISK-AS-01
requirement_ids:
  - REQ-AS-AUTHZ-01
control_ids:
  - CTRL-AUTHZ-01
  - CTRL-IAM-01
  - CTRL-AUDIT-01
evidence_refs:
  - "<API_ROUTE_AND_INGRESS_INVENTORY>"
  - "<NEGATIVE_AUTHORIZATION_TEST>"
  - "<IAM_POLICY_RUNTIME_SNAPSHOT>"
  - "<CI_RUN_AND_ARTIFACT_DIGEST>"
  - "<DEPLOYMENT_AND_LOG_VERIFICATION>"
last_verified_at: "<ISO_8601_UTC>"
reviewer: "<ASSESSOR>"
result: "<PASS_FAIL_INCONCLUSIVE>"
limitations: "<UNTESTED_ENDPOINTS_IDENTITIES_OR_PATHS>"
reassessment_trigger: "New endpoint, IAM policy or export flow change"
~~~

**Một record có đủ trường chưa tự chứng minh control đạt.** Bằng chứng có chất lượng phải xác minh được: nguồn, cách lấy, phạm vi, phiên bản/môi trường, người chịu trách nhiệm, thời điểm, trạng thái đúng/sai và các giới hạn.

### Ví dụ: ánh xạ claim–control–evidence

| Thành phần | Nội dung |
| --- | --- |
| **RISK-AS-01** | User tenant A có thể lấy báo cáo tenant B qua đường export hoặc storage. |
| **OBJ-CONF-01** | Bảo vệ tính bí mật dữ liệu khách hàng giữa các tenant. |
| **REQ-AS-01** | Mọi đường đọc và xuất báo cáo chỉ cho actor đã được cấp quyền với đối tượng tương ứng. |
| **CTRL-AUTHZ-01** | API và worker kiểm tra quyền cấp đối tượng theo actor, tenant và job. |
| **CTRL-IAM-01** | Workload có quyền storage tối thiểu; link tải giới hạn đúng tài nguyên và thời hạn. |
| **TEST-AS-01** | Tạo job cross-tenant, tráo job ID, thử tải từ đường trực tiếp và kiểm tra cấp quyền. |
| **EV-AS-01** | Test report, IAM snapshot, cấu hình bucket, image digest và runtime verification. |
| **FIND-AS-01** | Nếu link tải bỏ qua kiểm tra quyền, ghi finding và kiểm chứng sau khắc phục. |

Khi đánh giá, một phát hiện ở `CTRL-IAM-01` có thể làm claim tổng thể **chưa đủ căn cứ** dù `CTRL-AUTHZ-01` đã pass. Kết luận phải nêu phạm vi bằng chứng và những đường chưa kiểm tra.

## 10. Attack surface thay đổi như thế nào theo thời gian?

Attack surface là một **trạng thái thay đổi liên tục**. Các sự kiện thường làm thay đổi điểm tương tác:

- Thêm route, HTTP method, GraphQL mutation, gRPC method hoặc webhook.
- Bật feature flag, thêm tenant hoặc khu vực triển khai, đưa service lên public ingress.
- Thay security group, network policy, WAF hoặc API gateway route.
- Cấp quyền mới cho workload, dùng chung secret, tạo service account hoặc quyền khẩn cấp.
- Thêm queue/topic, message consumer, callback đến bên thứ ba hoặc export/storage URL.
- Thay dependency, base image, build plugin, CI runner, artifact registry hoặc nhà cung cấp.
- Thay đổi log pipeline, cách truy vấn dữ liệu và quyền đối với backup.
- Ngừng dịch vụ nhưng quên DNS, route cũ, credential hoặc storage còn truy cập được.

~~~mermaid
flowchart TD
    A["Cập nhật asset và attack surface inventory"] --> B["Phát hiện thay đổi theo commit/deploy/config"]
    B --> C["Đối chiếu điểm vào, owner, trust boundary"]
    C --> D{"Có thay đổi rủi ro hoặc control?"}
    D -- "Có" --> E["Cập nhật threat scenario và yêu cầu"]
    E --> F["Triển khai control, kiểm thử và review"]
    F --> G["Xác minh trạng thái runtime và lưu bằng chứng"]
    D -- "Không" --> G
    G --> H["Đánh giá còn hiệu lực, finding và trigger"]
    H --> A
~~~

**Không thể dùng mã nguồn để chứng minh mọi thứ ở production**; ingress, IAM, DNS, bucket policy và một số runtime flags thay đổi độc lập với source. Cần tổng hợp kết quả từ pipeline và nền tảng vận hành, so sánh **desired state** với **actual state**.

### Các chỉ số theo dõi tham khảo

| Chỉ số | Ý nghĩa | Rủi ro diễn giải |
| --- | --- | --- |
| Tỷ lệ endpoint/tài sản có owner | Mức quản lý danh mục | Chỉ số cao không chứng minh route được kiểm soát |
| Số điểm vào chưa phân loại exposure | Khoảng trống hiểu biết cần xử lý | Có thể tăng do khả năng khám phá tốt hơn |
| Tỷ lệ điểm vào quan trọng có test bảo mật còn hiệu lực | Mức bao phủ bằng chứng theo scope | Test hình thức có thể không kiểm tra đường gây hại |
| Thời gian từ phát hiện route ngoài inventory tới triage | Năng lực phản ứng trước thay đổi | Đo nhanh không đồng nghĩa xử lý triệt để |
| Số thay đổi IAM/ingress ngoài quy trình được phát hiện | Tín hiệu drift | Không phát hiện có thể do thiếu log |
| Tỷ lệ finding đã retest trên deployment thực tế | Khả năng chứng minh đã khắc phục | Retest một lần không bảo đảm không tái xuất hiện |

Không đặt mục tiêu **“số endpoint phải giảm bằng mọi giá”**. Một dịch vụ có nhiều điểm vào được quản lý tốt có thể ít rủi ro hơn dịch vụ có một điểm vào nhưng quyền quản trị vô hạn. Chỉ số cần đi kèm độ nhạy tài sản, độ phơi lộ, khả năng khai thác và độ tin cậy của evidence.

## 11. Ranh giới trách nhiệm khi đánh giá attack surface

| Vai trò | Trách nhiệm thực tế | Bằng chứng có thể cung cấp |
| --- | --- | --- |
| **Developer / Tech Lead** | Mô tả route, logic phân quyền, message consumer, file handler, dependency và behavior | API spec, source/review, test suites, change records |
| **Ops / SRE / Platform** | Xác minh actual ingress, DNS, network, IAM, deployment, storage và management endpoints | Runtime inventory, config snapshots, IAM effective permissions |
| **Security / AppSec** | Điều phối threat model, hỗ trợ phát hiện đường tấn công, xác lập tiêu chí và review control | Threat scenarios, test plan, assessment findings |
| **SOC / Incident Response** | Đánh giá góc nhìn detection, log, nguồn sự kiện và tác động sự cố | End-to-end alert test, incident records, telemetry gaps |
| **Risk/Service Owner** | Xác nhận tài sản và tác động; quyết định ưu tiên, kế hoạch và ngoại lệ theo thẩm quyền | Risk register, approval, acceptance conditions |
| **Assessor / Audit** | Đối chiếu bằng chứng và scope; xác nhận kết luận theo yêu cầu độc lập | Review trail, sampling, gap analysis và finding |

Nên xác định người **Accountable** cho từng tài sản/attack surface, người **Responsible** thực hiện kiểm tra và người có quyền **chấp nhận residual risk**. Người phát hiện điểm vào không mặc nhiên là người có quyền sửa hoặc đóng mọi rủi ro liên quan.

Một ngoại lệ được phê duyệt chỉ thể hiện quyết định chấp nhận rủi ro trong điều kiện, phạm vi và thời hạn xác định; nó không biến một endpoint thiếu authorization thành “đã an toàn”.

## 12. Case study: một đường export bị bỏ sót

### Bối cảnh

Nhóm quản lý báo cáo công bố API xem và tải báo cáo có kiểm tra quyền tenant. Sau đó một nhóm khác bổ sung tính năng xuất CSV chạy bất đồng bộ. API tạo job, worker ghi file vào storage, trả signed download link. Một bản scan public routes chỉ nhìn thấy `POST /api/exports` và `GET /api/exports/{jobId}`; bản báo cáo scan ghi “không phát hiện endpoint nguy hiểm”.

Trong lần review thiết kế, assessor nhận thấy:
- Endpoint tạo job đã xác thực nhưng nhận `reportId` do client cung cấp.
- Queue chỉ nhận message từ API nên worker mặc định tin `tenantId` trong message.
- Workload role của worker có quyền đọc dữ liệu nhiều tenant.
- Signed download link có thời hạn nhưng không chắc lúc tạo file đã kiểm tra quyền đúng.
- Hệ thống log nhận sự kiện tạo job nhưng chưa có event tải file thành công.

### Phân tích

**Điểm vào không chỉ là hai HTTP routes.** Toàn bộ đường gồm API, queue, worker identity, database, storage và link tải. Trust boundary quan trọng là **request của người dùng ít quyền dẫn tới hành động của worker có đặc quyền**. Cần xem xác thực, quyền tạo job, quyền đọc báo cáo ở thời điểm xử lý và khả năng tải file từ storage.

| Kịch bản | Control cần xem | Bằng chứng cần yêu cầu |
| --- | --- | --- |
| User A đặt `reportId` thuộc tenant B | Authorization cấp đối tượng trước khi tạo job | Negative integration test với hai tenant, đường API thực |
| User A tráo `jobId` của user B | Ràng buộc chủ sở hữu job khi đọc trạng thái/kết quả | Test truy cập job của người khác |
| Message bị sửa hoặc producer ngoài quyền gửi job | Producer ACL, validation và authorization ở worker | Queue policy, test message sai quyền và worker behavior |
| Worker đọc dữ liệu ngoài phạm vi | IAM tối thiểu; tenant boundary và policy ở tầng lưu trữ | Effective IAM snapshot và thử quyền từ chối |
| Link tải bị chia sẻ/đoán hoặc còn hiệu lực lâu | URL giới hạn tài nguyên/thời hạn; cách cấp cho actor phù hợp | Test thời hạn, quyền tải, scope URL và storage policy |
| CSV được tạo nhưng không theo dõi tải | Event tải và detection phù hợp | Event thử, collector ID, alert hoặc kết quả giám sát |
| Bản sửa chỉ nằm trên branch | Kiểm soát deploy và kiểm chứng runtime | Commit/build, artifact digest và deployment đang chạy |

### Từ finding đến remediation

1. **Ghi finding có phạm vi:** route/job/actor/tài sản và cách tái hiện với dữ liệu thử, không trích dữ liệu khách hàng thật.
2. **Đánh giá mức ảnh hưởng:** xác định tập dữ liệu có thể truy cập, điều kiện khai thác, thời điểm tính năng tồn tại và giới hạn của log.
3. **Thiết kế sửa nguyên nhân:** kiểm tra quyền cấp đối tượng cả ở API và ngữ cảnh job; giới hạn quyền worker; ràng buộc link với đúng đối tượng và thời gian; bổ sung telemetry.
4. **Regression test:** xác nhận user hợp lệ vẫn xuất được, actor khác tenant bị từ chối, tráo job ID không tải được, worker không vượt quyền, link hết hạn không còn dùng được.
5. **Kiểm chứng triển khai:** đối chiếu commit, CI, image digest, IAM/storage config và deployment đích; đánh giá các bản cũ còn hoạt động.
6. **Đóng finding có căn cứ:** reviewer xác minh lại, ghi residual risk, ngoại lệ nếu có và trigger đánh giá lại.

Chỉ đóng ticket API sau khi trả HTTP 403 là chưa đủ nếu worker hoặc direct storage vẫn tạo đường lấy dữ liệu. Bằng chứng sửa lỗi phải bao phủ **đường gây hại trong phạm vi claim**, không chỉ đoạn code được thay đổi.

## 13. Bài tập thực hành

**Tình huống:** một ứng dụng Java/Spring Boot quản lý tài liệu nội bộ vừa được chuyển lên Kubernetes. Nhóm phát triển khẳng định “đã có authentication ở gateway” và “không còn cổng nào ngoài 443”. Một báo cáo runtime cho biết:

- Ingress mới có đường `/api/documents/import` nhận tệp do người dùng tải lên.
- `/actuator/health` công khai, còn một endpoint metrics dùng internal ingress.
- Worker xử lý tệp có quyền đọc nhiều bucket và gọi API nội bộ.
- CI runner có quyền cập nhật cả image production và deployment.
- Một service cũ chưa có owner vẫn còn DNS record và route nội bộ.
- Log của endpoint import có khoảng trống sau lần đổi collector.

### Yêu cầu

1. Liệt kê ít nhất **sáu attack surface** và xác định actor, entry point, trust boundary và tài sản bị ảnh hưởng.
2. Chọn **ba kịch bản rủi ro** từ những điểm vào đó. Nêu rõ điều kiện và hậu quả, tránh khẳng định lỗ hổng khi chưa có bằng chứng.
3. Xác định **control phòng ngừa**, **control phát hiện** và **control phản ứng** cho tính năng import file.
4. Viết ít nhất bốn security acceptance criteria với trường hợp hợp lệ và bị từ chối.
5. Đề xuất bằng chứng để xác nhận service cũ không còn được gọi và log import đã thực sự hoạt động.
6. Xác định ai chịu trách nhiệm triển khai, ai review assurance và ai được phê duyệt chấp nhận một phần rủi ro còn lại.

### Gợi ý lời giải

| Điểm vào | Mối quan tâm cần kiểm chứng | Bằng chứng phù hợp |
| --- | --- | --- |
| `/api/documents/import` | Kiểm soát loại file, kích thước, quyền người dùng, parser và tài nguyên xử lý | API contract, input tests, quota tests, log event |
| Worker xử lý file | Nội dung không đáng tin đi vào tiến trình có quyền, nguy cơ lạm dụng luồng outbound | Identity và IAM thực, kết quả kiểm tra policy và xử lý file thử |
| Internal metrics | Còn bao phủ bởi network policy và auth phù hợp hay có route ngoài dự kiến? | Ingress/service mapping, test quyền truy cập từ vùng mạng đại diện |
| CI/CD runner | Một pipeline compromise có thể phát hành artifact/triển khai ngoài phạm vi? | Quyền runner, review workflow, artifact digest, audit deploy |
| Service cũ và DNS | Có đường cũ bỏ qua control mới, tài sản không có owner? | DNS, ingress, inventory, lưu lượng và quyết định decommission |
| Log import | Có mất khả năng phát hiện abuse và truy vết thao tác? | Event thử → collector → rule/alert → người xử lý |

**Ví dụ tiêu chí nghiệm thu:**

- Actor không có quyền import hoặc không xác thực **không thể** tạo job import.
- Tệp vượt giới hạn, không đúng định dạng hoặc không đạt chính sách xử lý bị từ chối có kiểm soát, không làm lộ dữ liệu bí mật trong lỗi.
- File được xử lý trong phạm vi quyền cần thiết; workload **không có quyền** truy cập bucket hoặc đích mạng ngoài chính sách.
- Các lần import có ID liên kết, trạng thái và event phục vụ audit; một sự kiện thử có thể được truy vết tới collector trong ngưỡng đã được phê duyệt.
- Khi decommission service cũ, route/DNS/credential liên quan được quản lý và kiểm tra lại; không dựa chỉ vào việc đã xóa repository.

Để xác minh, dùng **dữ liệu kiểm thử hợp lệ**, tài khoản và môi trường được cấp phép. Mọi tiêu chí phải ghi rõ phiên bản, phạm vi mạng, danh tính và giới hạn bằng chứng.

## 14. Những sai lầm thường gặp

| Nhận định thiếu căn cứ | Vì sao sai? | Cách cải thiện |
| --- | --- | --- |
| “Chỉ cần liệt kê open ports.” | Không bao phủ API logic, quyền, storage, queue, CI và người dùng | Đánh giá luồng dữ liệu, danh tính, quyền và đường tác động |
| “API nội bộ không có attack surface.” | Actor nội bộ hoặc workload bị chiếm vẫn có thể tương tác | Kiểm tra trust boundary, mTLS/workload identity và authorization |
| “Đã có authentication nên mọi request an toàn.” | Người dùng hợp lệ vẫn có thể đọc/sửa resource không thuộc quyền | Kiểm thử authorization cấp đối tượng và nghiệp vụ |
| “Không thấy trong scanner thì không tồn tại.” | Scanner bị giới hạn bởi mạng, role, thời điểm và logic ẩn | Đối chiếu source, contracts, runtime inventory, gateway và logs |
| “Đóng cổng là giảm mọi rủi ro.” | Cùng đường tác động có thể chuyển qua HTTP 443 hoặc credential | Xác nhận đường gây hại, quyền và tài sản sau thay đổi |
| “CI xanh chứng minh production chỉ có các route đã test.” | Runtime config, deployment cũ, feature flag và ingress có thể khác | Kiểm chứng artifact, config và exposure ở môi trường đích |
| “Bằng chứng export từ CMDB luôn chính xác.” | Inventory có thể thiếu tài sản và owner | Kiểm tra độ phủ qua nguồn độc lập, ghi unknown |
| “Chỉ cần giảm số endpoint để có điểm risk thấp.” | Mức tác động và điều kiện khai thác có thể cao ở một endpoint | Dùng scenario, likelihood/impact và evidence |
| “Đã merge PR thì finding đóng.” | Route cũ hoặc IAM thay đổi chưa được triển khai/kiểm tra | Retest, review, runtime verification và audit trail |
| “Đã chấp nhận ngoại lệ thì control đạt.” | Chấp nhận rủi ro khác với khắc phục kỹ thuật | Giữ status control, residual risk, thẩm quyền và hạn review riêng |

## Ghi nhớ

- **Attack surface** gồm mọi điểm tương tác mà tác nhân có thể tác động lên hệ thống; nó bao gồm API, workload, IAM, dữ liệu, quản trị, con người, CI/CD và bên thứ ba.
- **Mỗi điểm vào phải được gắn với tài sản, actor, trust boundary, dữ liệu/hành động, owner và môi trường cụ thể**; các điểm chưa xác minh phải được ghi rõ.
- Attack surface mapping dẫn tới **threat scenario → yêu cầu → security control → test → evidence → finding → khắc phục/retest**.
- **Thu hẹp bề mặt và giảm rủi ro có liên quan nhưng không đồng nhất**: chỉ giảm số cổng hoặc API không chứng minh bề mặt còn lại đã an toàn.
- Bằng chứng đáng tin phải **đối chiếu từ thiết kế, mã và trạng thái runtime**, có phiên bản, thời điểm, phạm vi, phương pháp và giới hạn.
- **Attack surface thay đổi liên tục** khi release, cấu hình, quyền, tài sản hoặc nhà cung cấp thay đổi; chương trình security assurance phải phát hiện thay đổi, đánh giá và kiểm chứng lại.
