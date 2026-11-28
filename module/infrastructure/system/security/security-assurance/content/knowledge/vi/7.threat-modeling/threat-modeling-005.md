# STRIDE trong Threat Modeling và Security Assurance

## 1. STRIDE giải quyết bài toán gì?

Khi đánh giá bảo mật một hệ thống, câu hỏi “đã có HTTPS, đăng nhập, tường lửa và kiểm thử bảo mật chưa?” là chưa đủ. Cần biết **kẻ tấn công hoặc sự cố có thể lợi dụng thành phần và luồng dữ liệu nào để vi phạm mục tiêu bảo mật**. Nếu chỉ dựa vào danh sách lỗ hổng đã biết, đội phát triển có thể bỏ sót các vấn đề đặc thù của logic nghiệp vụ, quyền truy cập và ranh giới tin cậy.

**Threat modeling (mô hình hóa đe dọa)** là hoạt động mô tả hệ thống, tài sản cần bảo vệ, các giả định và đường tấn công có thể xảy ra; từ đó nhận diện rủi ro, chọn biện pháp kiểm soát và xác định cần kiểm chứng điều gì. **STRIDE** là một phương pháp phân loại đe dọa thành sáu nhóm để người đánh giá đặt câu hỏi có hệ thống:

| Chữ | Nhóm đe dọa | Câu hỏi cốt lõi | Thuộc tính có thể bị vi phạm |
| :---: | --- | --- | --- |
| **S** | **Spoofing** – Giả mạo danh tính | Có thể giả làm người dùng, dịch vụ hoặc hệ thống khác không? | Xác thực / tính chân thực danh tính. |
| **T** | **Tampering** – Sửa đổi trái phép | Có thể làm sai dữ liệu, lệnh, cấu hình hoặc trạng thái không? | Tính toàn vẹn (*integrity*). |
| **R** | **Repudiation** – Chối bỏ hành động | Một chủ thể có thể phủ nhận hành động vì thiếu dấu vết đáng tin không? | Trách nhiệm giải trình / khả năng truy vết. |
| **I** | **Information Disclosure** – Tiết lộ thông tin | Thông tin có thể được truy cập hoặc lộ cho chủ thể không có quyền không? | Tính bí mật (*confidentiality*). |
| **D** | **Denial of Service** – Từ chối dịch vụ | Có thể làm dịch vụ không đáp ứng nhu cầu hợp lệ không? | Tính sẵn sàng (*availability*). |
| **E** | **Elevation of Privilege** – Leo thang đặc quyền | Chủ thể có thể thực hiện hành động vượt quyền đã được cấp không? | Phân quyền / thực thi đặc quyền. |

STRIDE được dùng để **khơi gợi và tổ chức các giả thuyết đe dọa**, không phải một công cụ tự động chứng minh hệ thống tồn tại lỗ hổng. Một mục STRIDE chỉ được coi là vấn đề được xác nhận khi có bằng chứng tương ứng; trước đó có thể là **kịch bản cần phân tích hoặc kiểm thử**.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật từ rủi ro, yêu cầu và controls tới kiểm thử, audit, khắc phục. STRIDE giúp tạo ra **bộ câu hỏi kiểm chứng** cho chương trình assurance liên tục: biết mình cần bảo vệ điều gì, tránh điều gì, vì sao controls được chọn và bằng chứng nào cho thấy chúng còn hoạt động.

### STRIDE không phải bộ ba CIA

CIA gồm bí mật, toàn vẹn và sẵn sàng; STRIDE bổ sung các góc nhìn **danh tính, chối bỏ và đặc quyền** giúp tìm ra nguyên nhân làm thất bại những thuộc tính bảo mật. Các nhóm STRIDE có thể chồng lấn: một vụ giả mạo danh tính (S) có thể dẫn tới leo thang quyền (E), tiết lộ dữ liệu (I) hoặc sửa đổi dữ liệu (T). Việc gắn nhiều nhãn cho một kịch bản là bình thường, miễn mô tả rõ **đường tấn công và hậu quả**.

## 2. Chuẩn bị mô hình hệ thống trước khi đặt câu hỏi STRIDE

STRIDE hiệu quả hơn khi người tham gia cùng nhìn vào một **mô hình hệ thống cụ thể**, thay vì đọc tên các công nghệ rồi đoán lỗ hổng. Một mô hình đơn giản thường dùng **Data Flow Diagram (DFD – sơ đồ luồng dữ liệu)**.

Các phần tử cần quan tâm:

| Phần tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **External entity** | Người dùng hoặc hệ thống tương tác với hệ thống đang phân tích từ bên ngoài phạm vi kiểm soát. | Người dùng SaaS, đối tác, Identity Provider. |
| **Process** | Thành phần thực thi xử lý và quyết định nghiệp vụ. | API Gateway, Invoice Service, Notification Worker. |
| **Data flow** | Thông tin hoặc lệnh truyền giữa các thành phần. | HTTP request, event trên message broker, kết quả truy vấn. |
| **Data store** | Nơi dữ liệu hoặc trạng thái được lưu. | PostgreSQL, object storage, kho log, cache. |
| **Trust boundary** | Ranh giới nơi mức độ tin cậy hoặc quyền kiểm soát thay đổi. | Internet → Gateway; Gateway → Service; tenant A → dữ liệu tenant B. |

**Trust boundary quan trọng hơn việc các thành phần có nằm cùng mạng hay không.** Ví dụ dù API Gateway và Invoice Service đều chạy trong cùng Kubernetes cluster, service không nên mặc nhiên tin một header tên tenant từ client chỉ vì yêu cầu đã đi qua gateway. Tài khoản dịch vụ, gateway, message broker và ứng dụng có mô hình danh tính, quyền và khả năng bị xâm nhập khác nhau.

### 2.1. Xác định tài sản, yêu cầu và giả định

Trước khi vẽ DFD, nhóm nên xác định:

1. **Tài sản và dữ liệu quan trọng:** hóa đơn, hồ sơ khách hàng, khóa API, token, trạng thái thanh toán, log, bản sao lưu.
2. **Yêu cầu bảo mật:** ví dụ chỉ chủ thể được phép thuộc đúng tenant mới có thể đọc hóa đơn; thay đổi hóa đơn phải có dấu vết truy xuất; API nhận giao dịch phải đạt SLO.
3. **Vai trò và định danh:** người dùng, admin, service account, nhà cung cấp danh tính và quyền nào thực sự được cấp.
4. **Phạm vi phân tích:** phiên bản, các thành phần trong/ngoài phạm vi, môi trường, đối tác, đường truy cập và thời điểm đánh giá.
5. **Giả định cần xác minh:** gateway có thực thi xác thực hay không, broker có ACL ra sao, các hệ thống dùng chung credential nào, dịch vụ xử lý trực tiếp hay qua job nền.

Nếu giả định chưa có bằng chứng, ghi **chưa xác minh**, không trình bày như sự thật đã biết.

### 2.2. Ví dụ DFD: nền tảng hóa đơn đa tenant

Giả sử một nền tảng SaaS cho người dùng nhiều doanh nghiệp đăng nhập, đọc hóa đơn, xuất báo cáo và nhận thông báo. Mô hình giản lược:

~~~mermaid
flowchart LR
    U["Người dùng / Internet"] -->|HTTPS: token + invoice ID| G["API Gateway"]
    IDP["Identity Provider"] -->|Keys / identity metadata| G
    G -->|Authenticated request| A["Invoice Service"]
    A -->|SQL query| DB[("Invoice Database")]
    A -->|Invoice-export event| MQ[("Message Broker")]
    MQ --> W["Export Worker"]
    W --> OBJ[("Object Storage")]
    A --> LOG[("Audit / Observability")]
    W --> LOG
    W -->|Download link / notification| U
~~~

**Ranh giới tin cậy cần đánh dấu trong buổi review:**

- **B1 – Người dùng ↔ Gateway:** input và token từ Internet là dữ liệu không đáng tin cho đến khi được xác thực, kiểm tra và ràng buộc quyền.
- **B2 – Gateway ↔ Invoice Service:** thông tin danh tính/tenant truyền qua thành phần khác; service phải có cơ chế xác minh ngữ cảnh tin cậy và kiểm tra quyền theo đối tượng.
- **B3 – Service ↔ Database:** service account có quyền đọc/ghi; phải kiểm soát truy vấn, phạm vi tenant và khả năng sửa dữ liệu.
- **B4 – Service ↔ Broker ↔ Worker:** message có thể được replay, sửa, giả nguồn, xử lý trùng hoặc chạy bằng tài khoản quá quyền.
- **B5 – Worker ↔ Object Storage ↔ người nhận:** file export có thể chứa dữ liệu nhạy cảm; kiểm soát quyền tải, thời hạn liên kết, khả năng chia sẻ tiếp và log.
- **B6 – Ứng dụng ↔ Logging/Monitoring:** log có thể tiết lộ token, dữ liệu khách hàng hoặc bị sửa/xóa; hệ thống cảnh báo cũng cần bảo vệ.

Sơ đồ trên **chỉ minh họa**. Trong hệ thống thật, phải cập nhật đúng cách Gateway/IdP xác thực, hướng của các luồng, các API phụ, cache, backup, quản trị và tích hợp bên thứ ba. Một đường dữ liệu bị bỏ quên là một điểm mù của mô hình đe dọa.

## 3. Cách áp STRIDE vào các phần tử DFD

Một kỹ thuật phổ biến là **STRIDE-per-element**: xét các nhóm đe dọa liên quan với từng phần tử trong sơ đồ. Bảng sau là **gợi ý rà soát**, không phải quy định loại trừ các nhóm khác:

| Phần tử | Nhóm thường cần xem xét | Câu hỏi thực hành |
| --- | --- | --- |
| **External entity** | S, R (có thể thêm nhóm khác theo ngữ cảnh) | Có thể giả mạo danh tính hoặc phủ nhận hành động đã thực hiện không? |
| **Process** | S, T, R, I, D, E | Có thể sai nhận diện, sửa trạng thái, thiếu audit, rò rỉ, quá tải hoặc vượt quyền không? |
| **Data flow** | T, I, D; đồng thời xem S/R nếu danh tính và nguồn thông điệp quan trọng | Dữ liệu có thể bị thay đổi, lộ hoặc chặn; nguồn gửi có được xác thực không? |
| **Data store** | T, I, D; thêm S/R/E khi có tài khoản hoặc hành vi quản trị | Dữ liệu có thể bị sửa, đọc, xóa hoặc làm không thể truy cập không? |
| **Trust boundary** | Xem lại đủ nhóm theo luồng và cơ chế vượt ranh giới | Điều gì đang được tin tưởng khi dữ liệu hoặc quyền đi qua ranh giới? |

Ví dụ **luồng xuất hóa đơn** cần rà soát cả S (giả tài khoản chạy worker), T (sửa ID hóa đơn trong event), R (không xác định ai yêu cầu export), I (lộ file), D (queue backlog), E (worker đọc được dữ liệu mọi tenant). Cùng một luồng có thể có nhiều loại đe dọa liên quan; không nên chỉ gắn một nhãn cho mỗi mũi tên DFD.

## 4. Quy trình thực hành STRIDE từ đầu đến cuối

### Bước 1 — Xác định mục tiêu bảo mật và phạm vi

Ghi rõ **hệ thống/phiên bản**, tài sản quan trọng, người dùng hợp lệ, môi trường, luồng nghiệp vụ trọng yếu, nghĩa vụ cần đáp ứng và những phần nằm ngoài phạm vi. Ưu tiên các luồng có hậu quả lớn như đọc dữ liệu khách hàng, thanh toán, quản trị tài khoản và khôi phục.

### Bước 2 — Vẽ DFD cùng ranh giới tin cậy

Mô tả các thành phần xử lý, nơi lưu, actor và từng luồng mang dữ liệu/lệnh. Với từng luồng, trả lời: ai gửi, ai nhận, giao thức, dữ liệu gì, danh tính nào, kiểm soát tại chỗ nào, ai sở hữu thành phần? Kiểm tra cả **đường thay thế** như admin API, batch job, webhook, file export, backup và truy cập vận hành.

### Bước 3 — Lặp qua các phần tử và STRIDE

Đặt câu hỏi cụ thể cho từng đường, không dùng nhãn chung như “hệ thống có thể bị hack”. Viết mỗi đe dọa dưới dạng **điều kiện → hành vi/sự kiện → tài sản bị ảnh hưởng → hậu quả**.

### Bước 4 — Đối chiếu controls hiện tại và khoảng trống

Với mỗi đe dọa, xác định biện pháp **ngăn ngừa, phát hiện, giới hạn và khôi phục**. Ghi trạng thái **đã có và được xác minh**, **đã có nhưng chưa kiểm chứng**, hoặc **đang lên kế hoạch**. Đừng tự gán trạng thái “đã xử lý” chỉ vì kiến trúc có tên công cụ.

### Bước 5 — Đánh giá rủi ro và ưu tiên

Phân tích **impact** theo dữ liệu, người dùng, hoạt động kinh doanh và nghĩa vụ; phân tích **likelihood** theo điều kiện, mức phơi lộ và bằng chứng. Dùng thang/rubric đã được tổ chức phê duyệt; tránh coi mức STRIDE hay CVSS là điểm rủi ro nghiệp vụ. Xem xét rủi ro trước và sau kiểm soát theo phạm vi cụ thể.

### Bước 6 — Giao trách nhiệm, xử lý và kiểm chứng

Gắn threat ID với **control owner**, người triển khai, người kiểm thử, risk owner và hạn xử lý. Chuyển mối đe dọa thành **security requirements có thể kiểm tra**, ví dụ “mọi truy vấn hóa đơn phải kiểm tra tenant của principal ở phía máy chủ”. Sau khi sửa, phải **retest** trên phiên bản và phạm vi liên quan.

### Bước 7 — Duy trì mô hình qua thay đổi

Cập nhật DFD và kết luận khi có API mới, dữ liệu mới, đổi identity provider, mở tích hợp đối tác, thay quyền service account hoặc sự cố. Threat modeling không chỉ là buổi workshop trước dự án; nó là **đầu vào liên tục cho security assurance**.

~~~mermaid
flowchart TD
    A["Mục tiêu, tài sản, phạm vi"] --> B["DFD + trust boundaries"]
    B --> C["Nhận diện S / T / R / I / D / E"]
    C --> D["Risk scenario + Impact / Likelihood"]
    D --> E["Security requirements + controls"]
    E --> F["Test / Audit / Evidence"]
    F --> G{"Claim đủ bằng chứng?"}
    G -- "Chưa" --> H["Phát hiện, khắc phục, kiểm thử lại"]
    H --> F
    G -- "Đã đủ trong phạm vi" --> I["Kết luận residual risk + quyết định"]
    I --> J["Giám sát thay đổi, đánh giá lại"]
    J --> B
~~~

## 5. S — Spoofing: giả mạo danh tính

**Spoofing** xảy ra khi kẻ tấn công hoặc một thành phần không đáng tin làm hệ thống **tin sai danh tính** của chủ thể hoặc hệ thống đang giao tiếp.

### Câu hỏi khai phá

- Một client có thể tự khai người dùng/tenant bằng header, cookie hoặc trường request mà không có nguồn xác thực không?
- Token có được kiểm tra chữ ký, issuer, audience, expiry và loại token theo hợp đồng tin cậy không?
- Service A có thể giả là Service B khi gọi nội bộ hoặc xuất event không?
- Tài khoản robot, API key, danh tính quản trị và tài khoản khẩn cấp có được quản lý và kiểm tra phạm vi tương xứng không?
- Mối quan hệ giữa tài khoản người dùng và tenant có được xác nhận từ nguồn tin cậy không?

### Kịch bản minh họa

Invoice Service nhận header do client gửi là X-Tenant-Id rồi dùng header đó để chọn dữ liệu, mặc dù danh tính từ token không được ràng buộc với tenant tương ứng. Một client có thể **mạo nhận ngữ cảnh tenant** khi gọi API.

### Controls phù hợp

- Xác thực dựa trên danh tính đáng tin, kiểm tra đầy đủ token và vòng đời thông tin xác thực.
- Xác thực giữa các service khi cần, ràng buộc danh tính dịch vụ với quyền được cấp.
- Không tin header danh tính do client tự cung cấp; thiết lập và bảo vệ ngữ cảnh danh tính qua ranh giới tin cậy.
- MFA và quản lý vòng đời tài khoản có đặc quyền phù hợp với kịch bản.
- Quản lý khóa và secret, chống sử dụng lại credential, xử lý vô hiệu hóa và xoay vòng.

### Bằng chứng assurance

Các kiểm thử token sai chữ ký, sai issuer/audience, hết hạn, tài khoản không có quyền; test người dùng tenant A gửi ID hoặc header của tenant B; review cơ chế truyền danh tính giữa gateway và service; cấu hình hiện hành của identity provider và danh sách ngoại lệ.

**Điểm dễ nhầm:** xác thực thành công chỉ cho biết “ai đang yêu cầu” theo cơ chế tương ứng; nó **chưa chứng minh người đó có quyền** thực hiện mọi hành động. Kịch bản truy cập dữ liệu vượt quyền phải kiểm tra thêm ở nhóm E và I.

## 6. T — Tampering: sửa đổi trái phép

**Tampering** là khả năng làm thay đổi dữ liệu, cấu hình, lệnh hoặc trạng thái **trái với quy tắc cho phép**, trong khi truyền, lưu trữ hoặc xử lý.

### Câu hỏi khai phá

- Client có thể sửa trường giá, tenant ID, trạng thái duyệt hay số tiền mà service không xác minh phía máy chủ không?
- Có thể sửa nội dung event ở message broker hoặc phát lại event cũ gây thay đổi sai trạng thái không?
- Có thể thay bản build, cấu hình IaC, script triển khai, log hoặc dữ liệu backup không?
- Có quy tắc chống cập nhật đồng thời làm mất dữ liệu, chống xử lý trùng và kiểm tra toàn vẹn không?

### Kịch bản minh họa

Một event tạo hóa đơn chứa trường amount và tenantId từ nguồn chưa được xác minh. Worker nhận event và lưu trực tiếp, không đối chiếu trạng thái giao dịch gốc. Kết quả có thể là hóa đơn sai tiền hoặc sai tenant.

### Controls phù hợp

- Kiểm tra dữ liệu đầu vào, quy tắc nghiệp vụ và authorization tại phía máy chủ.
- Bảo vệ tính toàn vẹn và nguồn của thông điệp bằng cơ chế thích hợp với môi trường (xác thực kênh, ACL broker, chữ ký/MAC khi mô hình đe dọa yêu cầu).
- Sử dụng idempotency key, versioning/optimistic locking hoặc các cơ chế chống ghi trùng và mất cập nhật khi phù hợp.
- Bảo vệ quy trình build/deploy, quyền sửa cấu hình và audit trail.
- Đối soát dữ liệu quan trọng, kiểm tra integrity ở điểm nhận và sau phục hồi.

### Bằng chứng assurance

Negative tests với trường tiền sai, event không hợp lệ, replay, concurrent updates; review schema và quy tắc tính toán; kiểm tra quyền sửa dữ liệu, cấu hình thực tế của broker; đối soát dữ liệu nguồn và đích. Bằng chứng phải đi từ **hành vi bị cấm** đến kết quả bị từ chối hoặc xử lý an toàn.

**Điểm dễ nhầm:** mã hóa chỉ nhằm bảo mật nội dung không tự bảo đảm tính toàn vẹn trong mọi cấu hình. Cần chọn giao thức và cơ chế có bảo vệ phù hợp, đồng thời vẫn phải xác minh ý nghĩa nghiệp vụ của dữ liệu.

## 7. R — Repudiation: chối bỏ hành động

**Repudiation** đề cập khả năng một chủ thể phủ nhận một hành động bởi hệ thống **không có bằng chứng đủ tin cậy để quy hành động đó tới chủ thể hoặc chuỗi xử lý**.

### Câu hỏi khai phá

- Khi người dùng xuất danh sách hóa đơn hoặc quản trị viên đổi quyền, có bản ghi ai làm, lúc nào, trên tài nguyên nào không?
- Có thể liên kết request, event, worker và kết quả xử lý bằng correlation ID không?
- Log có nguy cơ bị chính tài khoản bị điều tra sửa/xóa không?
- Đồng hồ giữa các dịch vụ có thống nhất; chính sách lưu giữ có đủ phục vụ kiểm toán và điều tra?
- Dữ liệu audit có được bảo vệ khỏi lộ secret và dữ liệu cá nhân ngoài nhu cầu không?

### Kịch bản minh họa

Worker xuất tệp hóa đơn lên object storage nhưng log chỉ ghi “Export completed”, không có user/service principal, tenant, job ID hoặc thời gian liên hệ với yêu cầu gốc. Khi tệp bị phát tán, rất khó chứng minh ai đã yêu cầu xuất và chuỗi xử lý đã xảy ra thế nào.

### Controls phù hợp

- Audit logging cho các hành động bảo mật và nghiệp vụ nhạy cảm, kèm actor đáng tin, action, resource, result, timestamp và correlation ID.
- Bảo vệ log khỏi sửa/xóa trái phép; quản lý quyền truy cập, retention, đồng bộ thời gian và phát hiện mất log.
- Truy vết các chuỗi bất đồng bộ từ request qua broker đến worker.
- Với yêu cầu đảm bảo chứng cứ cao, xem xét ký số, dấu thời gian hoặc cơ chế bằng chứng chuyên dụng phù hợp; đừng mặc nhiên coi log ứng dụng là bằng chứng không thể chối bỏ về mặt pháp lý.

### Bằng chứng assurance

Thử luồng export thành công, bị từ chối và lỗi giữa chừng; kiểm tra log có thể nối lại tác nhân với tài nguyên và job; test quyền ghi/xóa log, thời gian lưu và khả năng truy xuất khi điều tra. Đánh giá độc lập phải phân biệt **có log** với **log đủ nguồn gốc và toàn vẹn để hỗ trợ kết luận**.

**Điểm dễ nhầm:** logging không bảo đảm tuyệt đối tính không thể chối bỏ (*non-repudiation*). Một bản ghi log thiếu bảo vệ, sai nguồn danh tính hoặc không đủ chuỗi bằng chứng vẫn có thể bị tranh cãi.

## 8. I — Information Disclosure: tiết lộ thông tin

**Information Disclosure** là việc thông tin nhạy cảm bị hiển thị, truy xuất hoặc truyền tới chủ thể **không có quyền hoặc không có mục đích sử dụng được phép**.

### Câu hỏi khai phá

- API có thể trả dữ liệu tenant khác khi biết hoặc đoán object ID không?
- Response lỗi có tiết lộ stack trace, câu truy vấn, token, secret, thông tin cấu hình hoặc định danh người khác không?
- Dữ liệu nhạy cảm có bị ghi vào log, URL, cache, bản sao test, object storage hoặc dashboard giám sát không?
- Liên kết tải file export có thể bị chia sẻ, truy cập sau khi hết quyền hoặc tồn tại quá lâu không?
- Danh sách kết quả, tìm kiếm và thống kê có làm lộ dữ liệu qua suy diễn hoặc kết hợp các nguồn không?

### Kịch bản minh họa

Một file export được đặt trong bucket cho phép truy cập công khai, hoặc link tải thiếu kiểm tra quyền và có thời hạn quá dài. Người có link không thuộc tenant vẫn đọc được hóa đơn.

### Controls phù hợp

- Kiểm tra quyền đối tượng tại service và điểm truy cập dữ liệu, nguyên tắc quyền tối thiểu, phân tách tenant.
- Mã hóa khi truyền/lưu trữ và quản lý khóa phù hợp; kiểm soát truy cập chính là lớp phải có, không thay thế bằng mã hóa.
- Phân loại dữ liệu, giới hạn trường trả về, minimization, masking/pseudonymization khi thích hợp.
- Chặn truy cập công khai ngoài chính sách, quyền tải file có phạm vi/thời hạn; bảo vệ secret, log, cache và môi trường không sản xuất.
- Kiểm tra data lineage và các luồng export, backup, analytics, xử lý lỗi.

### Bằng chứng assurance

Test truy cập chéo tenant, quyền đọc file export, kiểm tra chính sách bucket trên môi trường thực tế, quét dữ liệu nhạy cảm trong log/test dataset, review câu trả lời API và cơ chế hết hạn quyền. Gắn evidence với từng đường dữ liệu; một test API đọc đạt không chứng minh đường export hoặc backup an toàn.

**Điểm dễ nhầm:** việc có quyền truy cập bucket không đồng nghĩa người dùng có quyền xem mọi dữ liệu bên trong. Phân quyền ở từng lớp cần hỗ trợ cùng một chính sách.

## 9. D — Denial of Service: từ chối dịch vụ

**Denial of Service** là khả năng làm dịch vụ hoặc tài nguyên **không đáp ứng được yêu cầu hợp lệ**; nguyên nhân có thể là lưu lượng độc hại, lạm dụng nghiệp vụ, lỗi hệ thống hoặc phụ thuộc bị cạn tài nguyên.

### Câu hỏi khai phá

- Có endpoint tìm kiếm/export dùng CPU, bộ nhớ, database connection hoặc hàng đợi không giới hạn?
- Người dùng thông thường có thể yêu cầu một tác vụ lớn làm nghẽn dịch vụ của tenant khác không?
- Retry có giới hạn, backoff, jitter và idempotency không? Khi service phụ lỗi, có xảy ra retry storm không?
- Một worker dừng có làm queue backlog ảnh hưởng các tác vụ quan trọng khác?
- Có điểm lỗi chung ở database, DNS, IAM, broker, cloud region hoặc quyền vận hành khẩn cấp?

### Kịch bản minh họa

API export cho phép yêu cầu báo cáo trên hàng triệu hóa đơn không giới hạn dung lượng, thời gian hoặc số job đồng thời. Một tài khoản hợp lệ có thể gửi nhiều yêu cầu khiến database cạn kết nối và API tạo/xem hóa đơn của các tenant khác timeout.

### Controls phù hợp

- Rate limit, quota theo tenant/chủ thể, giới hạn truy vấn, pagination, deadline và budget tài nguyên.
- Cách ly tài nguyên, queue riêng cho tác vụ nặng, concurrency control, backpressure và load shedding.
- Timeout, circuit breaker, retry có giới hạn và tính idempotent cho các thao tác cần thiết.
- Quan sát SLI/SLO ở mức giao dịch, cảnh báo backlog, connection pool và error budget.
- Khả năng dự phòng, kế hoạch ứng cứu và diễn tập khôi phục theo BIA/RTO/RPO.

### Bằng chứng assurance

Load/stress tests trong môi trường được phép với workload đại diện; đo tỷ lệ hoàn tất của người dùng hợp lệ, độ trễ, thời gian phục hồi, ảnh hưởng liên tenant và false positives từ rate limit. Kết quả diễn tập failover và restore chứng minh giới hạn tác động trong kịch bản đã thử.

**Điểm dễ nhầm:** API trả HTTP 200 hoặc máy chủ còn chạy không chứng minh giao dịch nghiệp vụ đáp ứng thời hạn. Mục tiêu availability phải được xác định bằng SLI/SLO phù hợp.

## 10. E — Elevation of Privilege: leo thang đặc quyền

**Elevation of Privilege** xảy ra khi một chủ thể có thể thực hiện hành động **vượt quyền đã được cấp**, bao gồm vượt quyền giữa vai trò, tenant, tài nguyên hoặc thành phần dịch vụ.

### Câu hỏi khai phá

- Một người dùng có thể sửa userId, tenantId, invoiceId hoặc role trong request để thao tác thay người khác không?
- Có thể gọi endpoint admin hoặc bypass kiểm tra quyền qua REST, GraphQL, job nền hoặc hàng đợi?
- Có quyền dịch vụ quá rộng: worker đọc mọi tenant trong khi chỉ cần xử lý một job cụ thể?
- Có đường gọi trực tiếp service hoặc thay đổi danh tính qua gateway không được kiểm tra lại?
- Khi dùng token delegated/service token, các quyền/claims có được xác thực và giới hạn theo đúng mục đích không?

### Kịch bản minh họa

API sửa hóa đơn chỉ kiểm tra người dùng đã đăng nhập, sau đó nhận invoiceId và tenantId từ body. Người dùng tenant A gửi invoiceId của tenant B và cập nhật trạng thái hóa đơn B: đây là tình huống **Broken Object Level Authorization (BOLA/IDOR)** và có thể dẫn tới **leo thang quyền theo đối tượng**, đồng thời gây **tampering**.

### Controls phù hợp

- Authorization phía server trên **mỗi thao tác và đối tượng nhạy cảm**, mặc định từ chối khi thiếu thông tin/quyền.
- Ràng buộc tài nguyên với principal/tenant từ ngữ cảnh tin cậy, dùng RBAC/ABAC hoặc mô hình chính sách phù hợp.
- Tách quyền quản trị, quyền dịch vụ, quyền đọc/ghi/xuất; cấp quyền tối thiểu và rà soát định kỳ.
- Phân tách vai trò, kiểm soát thao tác nguy hiểm, bảo vệ luồng khẩn cấp và kiểm soát thay mặt người dùng (*delegation*) theo chính sách.
- Kiểm thử các đường bypass ngoài tuyến API chính, gồm batch, webhook và worker bất đồng bộ.

### Bằng chứng assurance

Ma trận quyền theo vai trò và tenant đã được duyệt, integration/negative tests trên mọi đường thao tác trong phạm vi, code review điểm quyết định authorization, kiểm tra quyền service account và bằng chứng cấu hình triển khai. Test phải bao phủ **được phép và không được phép**, không chỉ trường hợp thành công.

**Điểm dễ nhầm:** người dùng có token hợp lệ chưa chắc được phép sửa một hóa đơn cụ thể. Phân biệt **authentication** (ai) và **authorization** (được làm gì trên tài nguyên nào) giúp đánh giá đúng.

## 11. Bảng STRIDE cho một hệ thống mẫu

Bảng này minh họa cách biến câu hỏi thành kịch bản cụ thể và công việc assurance. Các threat ID chỉ dùng trong ví dụ, không phải kết quả quét hệ thống thật.

| ID | Loại | Kịch bản trong Invoice SaaS | Security requirement / control | Evidence cần có |
| --- | --- | --- | --- | --- |
| **TH-S-01** | S | Client gửi tenant giả qua header và được service tin. | Tenant context lấy từ danh tính được kiểm chứng; header do client kiểm soát không cấp quyền. | Negative test thay header/claim; review gateway và service. |
| **TH-T-02** | T | Event export bị sửa invoice ID hoặc tenant để worker xử lý sai. | Xác thực nguồn event, xác minh quyền/ngữ cảnh, validation và idempotency. | Test event sai nguồn, sai tenant, bị replay; ACL broker. |
| **TH-R-03** | R | Không truy vết được ai yêu cầu export sau khi worker hoàn tất. | Audit trail xuyên request–job–worker, log được bảo vệ. | Correlation test, log mẫu, test quyền xóa/sửa. |
| **TH-I-04** | I | File export của tenant A bị người tenant B tải. | Object authorization, quyền tải và thời hạn giới hạn, bucket private. | Negative test download, cấu hình storage và log. |
| **TH-D-05** | D | Nhiều export làm nghẽn database, gây timeout các tenant. | Quota, queue/concurrency limits, isolation và monitoring. | Load test, kết quả SLI và backlog theo tenant. |
| **TH-E-06** | E | Người dùng có quyền đọc được gọi API sửa hóa đơn vì thiếu object-level authorization. | Authz theo thao tác và đối tượng; phân quyền tối thiểu. | Test read-only user cố sửa; ma trận quyền và code review. |

**Lưu ý về thứ tự ưu tiên:** mã TH-I-04 và TH-E-06 không tự động có cùng mức rủi ro. Mức độ phụ thuộc loại dữ liệu, số lượng đối tượng, quyền khai thác, controls hiện hành, phạm vi và hậu quả nghiệp vụ.

## 12. Từ threat đến security requirement có thể kiểm thử

Một threat model có giá trị khi kết quả được chuyển thành **yêu cầu kiểm soát đo được** và **kiểm thử phù hợp**. Mỗi dòng threat register nên có đường truy vết:

**Threat → Security objective → Security requirement → Control → Verification → Evidence → Residual risk / Decision.**

Ví dụ cho TH-I-04:

**Threat:** người không thuộc tenant tải được file export.

**Mục tiêu:** chỉ người có quyền mới xem dữ liệu hóa đơn thuộc tenant tương ứng.

**Yêu cầu kiểm chứng được:** “Với mọi file export nằm trong phạm vi, người dùng phải được xác thực; trước khi cấp quyền tải, service xác minh tenant, quyền truy cập, trạng thái và thời hạn cho phép. Mọi yêu cầu không có quyền bị từ chối theo chính sách và không làm lộ nội dung file.”

**Controls:** authorization ở endpoint tạo link và/hoặc nơi phục vụ file; object storage không công khai; quyền có thời hạn; log sự kiện tải; kiểm soát chia sẻ.

**Tests và evidence:**

1. Tenant A tạo file A và có thể tải trong điều kiện cho phép.
2. Tenant B không tải được file A dù biết URL hoặc object ID.
3. Tài khoản thiếu quyền export không tạo/tải file; token hết hạn hoặc vô hiệu không cấp quyền.
4. Đường tải qua worker, CDN hoặc storage trực tiếp không bypass chính sách.
5. Cấu hình production, đường dữ liệu và bằng chứng kiểm tra tương ứng bản triển khai.

Một HTTP 403 hoặc 404 có thể được chọn theo chính sách API; tiêu chí quan trọng là **không cấp dữ liệu và không tạo rò rỉ bổ sung**, không phải cố định một status code cho mọi sản phẩm.

### Ví dụ kiểm thử Java/Spring Security

Với API dùng Spring Security Resource Server, một **integration test** có thể kiểm tra rằng ngữ cảnh tenant A không thể đọc hóa đơn thuộc tenant B. Đoạn mã dưới đây minh họa phần **authorization** khi MockMvc đã được cấu hình Spring Security Test và bộ dữ liệu thử có hóa đơn của tenant B:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InvoiceAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void tenantACannotReadTenantBInvoice() throws Exception {
        mvc.perform(get("/api/invoices/{id}", "invoice-of-tenant-b")
                .with(jwt().jwt(token -> token.claim("tenant_id", "tenant-a"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Trong ví dụ, giả định thiết kế trả **403** khi chủ thể đã xác thực nhưng không có quyền; sản phẩm chọn **404** để tránh tiết lộ sự tồn tại tài nguyên cần điều chỉnh assertion tương ứng. Các import, dữ liệu thử, quyền principal và cấu hình test phải khớp hệ thống thực. Đặc biệt, helper jwt() của Spring Security Test **tạo authentication giả lập**, nên bài test này **không chứng minh** chữ ký, issuer, audience hay expiry của JWT được xác minh đúng. Cần thêm kiểm thử ở ranh giới xác thực với token thật hoặc token được ký phục vụ kiểm thử để hỗ trợ claim Spoofing.

**Một ca test không thay thế được test coverage.** Bằng chứng cần gắn test với danh sách endpoint, các thao tác read/write/export, vai trò, tenant, phiên bản và môi trường trong phạm vi.

## 13. Đánh giá rủi ro sau khi nhận diện threat

STRIDE **không tự cung cấp kết quả likelihood, impact hoặc mức rủi ro được chấp nhận**. Sau khi có kịch bản, nhóm cần sử dụng phương pháp risk assessment của tổ chức:

1. **Impact:** nếu kịch bản xảy ra, hậu quả đối với confidentiality, integrity, availability, khách hàng, tài chính, nghĩa vụ và vận hành là gì?
2. **Likelihood:** điều kiện để xảy ra, mức phơi lộ, khả năng khai thác, tiền lệ và bằng chứng controls cho thấy xác suất/tần suất ra sao?
3. **Inherent risk:** mức rủi ro theo giả định chưa tính các controls được chọn, nếu phương pháp của tổ chức yêu cầu.
4. **Current residual risk:** rủi ro còn lại khi tính **controls đã triển khai và có evidence phù hợp**.
5. **Target residual risk:** mục tiêu sau những cải tiến đã lên kế hoạch, cần ghi rõ **chưa đạt** cho đến khi có retest.
6. **Decision:** người có thẩm quyền xử lý/chấp nhận rủi ro còn lại theo chính sách; ghi hạn, phạm vi và điều kiện tái xét.

Ví dụ TH-I-04 có thể có **impact cao** do lộ thông tin thương mại nhưng likelihood khác nhau khi file public, khi link có thời hạn hoặc khi có kiểm tra quyền đối tượng. Đánh giá phải dựa trên **cơ chế thực tế**, không giảm điểm chỉ vì “có WAF”.

### Không đếm đe dọa thành mức rủi ro

Mười kịch bản nhỏ không nhất thiết nghiêm trọng hơn một kịch bản có thể làm gián đoạn toàn bộ dịch vụ hoặc lộ dữ liệu nhạy cảm diện rộng. Threat count hữu ích để theo dõi **độ bao phủ phân tích**, còn quyết định đầu tư và khắc phục dựa trên **rủi ro, yêu cầu bắt buộc và tác động nghiệp vụ**.

## 14. Hồ sơ threat model có thể kiểm toán

Nếu threat model chỉ nằm trong ảnh sơ đồ và cuộc họp, người kiểm toán khó biết giả định nào đã được xử lý. Cần gắn **threat ID**, owner, control, test và status với phiên bản hệ thống.

Ví dụ một hiện vật YAML **mang tính minh họa**, không phải metadata bài học hoặc khuôn dạng bắt buộc:

~~~yaml
threat_id: TH-I-04
category: Information Disclosure
title: Cross-tenant export file download
scope:
  system: invoice-saas
  release: "2.8"
  environment: production
  components:
    - Export API
    - Export Worker
    - Object Storage
  trust_boundaries:
    - External client to API
    - Worker to object storage
scenario: >
  A principal from tenant B attempts to download
  an export owned by tenant A.
security_objective: Only authorized tenant members can read exports
requirements:
  - REQ-AUTHZ-EXPORT-01
controls:
  - CTRL-EXPORT-OBJECT-AUTHZ
  - CTRL-STORAGE-PRIVATE
evidence:
  - artifact: tests/export-authorization-release-2.8
    covers: tenant-level denial cases
  - artifact: reviews/storage-policy-production
    covers: non-public storage configuration
limitations:
  - CDN edge cache policy not yet independently verified
owner_role: Invoice Service Owner
risk_owner_role: Customer Data Risk Owner
current_status: Open - evidence gap
planned_action: Verify CDN path and retest download permissions
decision: Pending authorized risk review
reassessment_triggers:
  - New export delivery mechanism
  - Change in tenant identity handling
  - Object storage or CDN policy changes
~~~

Các đường dẫn, tên và kết quả trong mẫu là **ví dụ**; khi áp dụng phải trỏ tới hiện vật thật, người chịu trách nhiệm, bản phát hành và ngày đánh giá. Hồ sơ có thể đặt trong công cụ quản trị rủi ro hoặc kho mã có kiểm soát phiên bản, miễn **truy vết được và bảo vệ khỏi sửa trái phép**.

### Claim – Argument – Evidence (CAE)

Một cách trình bày kết luận assurance:

- **Claim:** “Trong bản phát hành và các đường tải file được nêu rõ, chỉ người thuộc tenant có quyền mới tải được file export.”
- **Argument:** “Service đối chiếu principal và tenant với quyền trên đối tượng export; storage không public; các đường tải dùng chính sách tương đương; kiểm tra cả trường hợp bị từ chối.”
- **Evidence:** API inventory, access policy, test chéo tenant, cấu hình storage thực tế, review luồng CDN/worker, báo cáo retest và danh sách ngoại lệ.

Nếu còn đường CDN chưa kiểm tra, chỉ có thể kết luận cho **những đường đã có bằng chứng**. Đừng biến một claim có giới hạn thành câu “mọi dữ liệu đã an toàn”.

### Bảng chất lượng bằng chứng

| Tiêu chí | Câu hỏi assurance | Dấu hiệu còn yếu |
| --- | --- | --- |
| **Relevance** | Evidence kiểm tra đúng tình huống STRIDE không? | Kiểm tra login thành công để chứng minh quyền trên từng hóa đơn. |
| **Coverage** | Tất cả đường dữ liệu, vai trò, tài khoản, tenant liên quan đã được xét? | Chỉ test endpoint GET, không test export, batch hoặc admin. |
| **Provenance** | Ai/công cụ nào tạo ra, artifact gốc ở đâu? | Ảnh chụp “PASS” không có test report. |
| **Freshness** | Đúng phiên bản, môi trường và cấu hình đang đánh giá? | Test cũ trước khi thay API Gateway hoặc IdP. |
| **Repeatability** | Có input, phương pháp và kỳ vọng để tái tạo? | “Team đã thử thủ công và thấy ổn.” |
| **Integrity** | Bằng chứng có thể bị sửa/xóa hoặc chứa secret không? | Log không kiểm soát quyền, thiếu timestamp. |
| **Independence** | Người review có đủ độc lập tương xứng rủi ro? | Chủ thể tự đánh giá rủi ro cao mà không review cần thiết. |
| **Limits** | Có ghi rõ điều chưa test và ngoại lệ? | Báo cáo “zero threats” trong khi phạm vi DFD bỏ sót export. |

## 15. Tổ chức buổi threat modeling và phân công trách nhiệm

Buổi review tốt cần nhiều góc nhìn. Thành phần có thể gồm:

| Vai trò | Đóng góp |
| --- | --- |
| **Product/business owner** | Xác định luồng nghiệp vụ, giá trị tài sản và hậu quả khi bị xâm hại. |
| **Architect/technical lead** | Cung cấp DFD, trust boundaries, mô hình giao tiếp và quyết định thiết kế. |
| **Developer/service owner** | Xác nhận các code path, validation, authorization và điều kiện lỗi trong hệ thống thật. |
| **Security engineer/threat model facilitator** | Dẫn dắt câu hỏi STRIDE, kiểm tra giả định và đề xuất yêu cầu kiểm chứng. |
| **Data owner** | Xác định độ nhạy, phạm vi dữ liệu, quyền sử dụng và nghĩa vụ liên quan. |
| **Control owner/operations** | Cung cấp trạng thái cấu hình, vận hành, bằng chứng và khả năng phản ứng/khôi phục. |
| **Risk owner** | Quyết định xử lý/chấp nhận rủi ro theo thẩm quyền, căn cứ impact và evidence. |
| **Security assurance/assessor** | Đánh giá tính đầy đủ của lập luận, bằng chứng, giới hạn và kiểm thử độc lập khi cần. |

Một buổi review thực tế có thể bắt đầu bằng **luồng nghiệp vụ nguy hiểm nhất**, đi từ đầu vào đến dữ liệu nhạy cảm; mỗi người nêu threat, điều kiện và mức hậu quả dự kiến. Người điều phối gộp các threat trùng thực chất, gắn ID/owner, tránh tranh luận mãi về nhãn STRIDE nếu điều quan trọng là **đường tấn công và biện pháp xử lý**.

### Đầu ra của buổi review

Nên lưu: phiên bản DFD và phạm vi, danh sách threat/assumptions, mục tiêu/yêu cầu bảo mật, controls hiện tại và thiếu sót, bước kiểm chứng, owner, mức ưu tiên và rủi ro chưa quyết định. Mỗi phát hiện phải có đường tới công việc triển khai và kết quả retest.

## 16. STRIDE trong SDLC và vận hành liên tục

Không cần tổ chức lại một workshop toàn hệ thống sau mỗi dòng mã, nhưng cần biết **thay đổi nào làm giả định tin cậy cũ không còn đúng**.

| Thời điểm | Hoạt động STRIDE | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Thiết kế mới** | Lập DFD, tài sản, trust boundaries; rà sáu nhóm đe dọa. | Mô hình phiên bản, threat register, security requirements. |
| **Phát triển tính năng** | Rà đường dữ liệu/API mới, controls, test cases; review các assumptions. | Pull request review, integration/security tests, threat mapping. |
| **Trước phát hành** | Kiểm tra những threats trọng yếu có controls/evidence đúng release. | Risk acceptance nếu cần, kết quả kiểm thử và phát hiện chưa xử lý. |
| **Trong vận hành** | Theo dõi sự cố, config drift, log/telemetry và điểm yếu mới liên quan. | Incident timeline, alert, kiểm tra cấu hình, action tracker. |
| **Sau sự cố hoặc audit** | Kiểm tra threat đã được dự đoán hay bị bỏ sót, vì sao control không hiệu quả. | Post-incident review, cập nhật DFD/requirements/retest. |
| **Thay kiến trúc/phụ thuộc** | Rà lại trust boundaries và phụ thuộc chung, ưu tiên đường mới hoặc đổi quyền. | Threat model delta, bằng chứng đánh giá lại. |

**Các trigger đặc biệt cần chú ý:** bổ sung endpoint export, mở webhooks, thêm service account hoặc quyền admin, thay JWT provider, đổi tenant isolation, tăng quyền worker, thêm cache/CDN, đổi object storage policy, di chuyển vùng và tích hợp đối tác mới.

### Một bộ chỉ số hỗ trợ quản trị

- Tỷ lệ luồng nghiệp vụ rủi ro cao đã có DFD và review threat model cập nhật.
- Tỷ lệ threat trọng yếu có security requirement, control owner và cách kiểm chứng.
- Số threat có evidence gap, phát hiện quá hạn hoặc ngoại lệ sắp hết hiệu lực.
- Tỷ lệ threat đã được retest sau khắc phục và có kết luận residual risk.
- Số thay đổi trust boundary chưa được threat review trước release.

Các chỉ số trên giúp kiểm tra **quy trình assurance có bao phủ và được duy trì hay không**; chúng không trực tiếp chứng minh hệ thống hoàn toàn an toàn.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Đã chạy SAST/scanner thì không cần STRIDE.” | Scanner phát hiện nhóm lỗi theo khả năng công cụ; STRIDE tìm kịch bản, logic nghiệp vụ và ranh giới tin cậy. |
| “Mỗi phần tử DFD chỉ có một loại STRIDE.” | Một phần tử/luồng có thể phát sinh nhiều đe dọa; bảng mapping là gợi ý hỏi. |
| “STRIDE cho biết sẵn xác suất và mức thiệt hại.” | STRIDE phân loại/khơi gợi đe dọa; risk assessment phải phân tích riêng. |
| “Có đăng nhập thì không có leo thang quyền.” | Authentication không thay thế authorization theo hành động/tài nguyên. |
| “Mọi request nội bộ đều đáng tin.” | Có ranh giới quyền giữa gateway, service, worker, broker và tài khoản dịch vụ. |
| “Cứ bật TLS là không bị tampering hoặc disclosure.” | TLS bảo vệ kênh trong điều kiện phù hợp; dữ liệu ở endpoint, log, storage và logic nghiệp vụ vẫn cần controls. |
| “Có log là không thể chối bỏ hành động.” | Log cần nguồn danh tính đúng, tính toàn vẹn, phạm vi, retention và đôi khi bằng chứng mạnh hơn. |
| “Có nhiều server thì không có DoS.” | Điểm lỗi chung, database, queue và quá tải tài nguyên vẫn có thể làm mất availability. |
| “Đã đóng ticket nghĩa là threat được xử lý.” | Cần chứng minh control triển khai, retest và cập nhật residual risk. |
| “Không tìm thấy threat nghĩa là không có threat.” | Có thể còn thiếu phạm vi, giả định hoặc góc nhìn; kết luận luôn có giới hạn. |
| “Threat model chỉ viết một lần trước khi code.” | Thay đổi kiến trúc, dữ liệu, quyền, đối tác và sự cố phải kích hoạt review phù hợp. |

## 18. Bài tập tự kiểm tra

### Tình huống A — Tin header phía client

Invoice Service nhận X-User-Role: admin từ một HTTP header có thể do client trực tiếp đặt và dùng để mở quyền sửa hóa đơn. Hãy xác định các nhóm STRIDE và cách kiểm chứng.

**Gợi ý:** Có **Spoofing** (giả ngữ cảnh danh tính) và **Elevation of Privilege** (thao tác vượt quyền); nếu hóa đơn bị sửa có thêm **Tampering**. Cần xác thực nguồn identity, xây dựng principal tin cậy, authorization phía server theo tài nguyên và negative tests đổi header hoặc tenant.

### Tình huống B — Export không ghi tác nhân

Một file hóa đơn được xuất lên object storage, nhưng audit log không lưu ai khởi tạo job và link có thể được gửi tiếp. Phân tích.

**Gợi ý:** **Repudiation** do thiếu chuỗi truy vết, **Information Disclosure** do link chia sẻ có thể lộ dữ liệu; kiểm tra actor/job correlation, quyền object, thời hạn link, môi trường storage và log access.

### Tình huống C — Worker xử lý event lặp

Broker gửi lại cùng một event cập nhật trạng thái thanh toán. Worker không có idempotency, mỗi lần nhận đều tạo thêm giao dịch điều chỉnh. Đó là nhóm gì?

**Gợi ý:** **Tampering** theo nghĩa trạng thái nghiệp vụ bị thay đổi sai do replay/duplicate processing; có thể kèm **Denial of Service** nếu retry làm nghẽn worker. Kiểm tra idempotency key, transaction boundaries, deduplication, schema validation và kết quả giao dịch dưới điều kiện giao hàng ít nhất một lần (*at-least-once*).

### Tình huống D — Load test đạt nhưng thiếu cô lập tenant

Load test với một tenant đạt SLO, nhưng một tenant có thể gửi hàng trăm job export nặng chiếm toàn bộ pool kết nối. Nhóm tuyên bố đã xử lý DoS.

**Gợi ý:** Chưa đủ. Threat **Denial of Service** liên quan **khả năng cô lập tài nguyên liên tenant**; cần test nhiều tenant, quota, queue và tác động tới giao dịch hợp lệ trong điều kiện cạnh tranh tài nguyên. Load test một tenant không chứng minh fairness/cách ly.

### Tình huống E — Token hợp lệ nhưng dữ liệu sai tenant

Người dùng đã đăng nhập với token hợp lệ và gọi GET /invoices/other-tenant-id để lấy dữ liệu của tenant khác. Test xác thực JWT vẫn đạt. Đây có phải STRIDE đã được xử lý?

**Gợi ý:** Chưa. Token hợp lệ mới hỗ trợ **Spoofing** ở mức danh tính; phải kiểm tra **Elevation of Privilege** và **Information Disclosure** qua object-level authorization. Yêu cầu test theo tenant và quyền, đối chiếu mọi endpoint, kể cả export.

### Tình huống F — Một thay đổi cấu hình mở đường đi mới

API trước đây chỉ nhận yêu cầu qua gateway có xác thực. Nhóm triển khai một endpoint nội bộ để đối tác gọi trực tiếp service, không cập nhật DFD. Điều gì phải làm?

**Gợi ý:** Cập nhật **trust boundary**, mô hình xác thực, phân quyền và các luồng dữ liệu; rà đủ STRIDE cho endpoint mới. Kết quả test gateway cũ không chứng minh đường đối tác an toàn. Gắn threat, owner, requirements, evidence và quyết định release/risk theo thẩm quyền.

## Kết luận

**STRIDE** là một phương pháp có cấu trúc giúp phát hiện các kịch bản **giả mạo, sửa đổi, chối bỏ, lộ thông tin, từ chối dịch vụ và leo thang quyền** trên từng thành phần, luồng dữ liệu và ranh giới tin cậy. Giá trị thực tế của STRIDE nằm ở việc chuyển các kịch bản đó thành **mục tiêu bảo mật, security requirements, controls và phép kiểm chứng có bằng chứng**, gắn rõ owner và rủi ro còn lại. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, một threat model đáng tin phải phản ánh đúng hệ thống thực, công khai giả định/giới hạn, cập nhật khi thiết kế và vận hành thay đổi, đồng thời dẫn tới hành động khắc phục và đánh giá lại. STRIDE giúp đặt đúng câu hỏi; bằng chứng và quyết định có trách nhiệm mới cho phép kết luận hệ thống đã xử lý một rủi ro trong phạm vi nào.
