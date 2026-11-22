# Mô hình đe dọa và cách nhận diện bề mặt tấn công

Một ứng dụng có thể dùng Spring Security, HTTPS và mật khẩu được băm đúng cách nhưng vẫn để lộ dữ liệu nếu đội phát triển không nhận ra một đường truy cập hoặc một hành vi lạm dụng. **Mô hình đe dọa (threat modeling)** giúp trả lời các câu hỏi: chúng ta đang bảo vệ điều gì; ai có thể gây hại; họ đi vào bằng đường nào; điều gì có thể xảy ra; và cần kiểm chứng biện pháp bảo vệ ra sao?

Bài học sử dụng **một ứng dụng Spring Boot giả định** để luyện tư duy. Mục tiêu là tự xây dựng được bản đồ bề mặt tấn công và một danh sách rủi ro có căn cứ. Những nguy cơ trong ví dụ là **kịch bản cần kiểm tra**, không phải kết luận rằng hệ thống thực tế đang có lỗ hổng.

## 1. Hiểu đúng các thuật ngữ

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tài sản (asset)** | Dữ liệu, chức năng, danh tính hoặc năng lực hệ thống cần bảo vệ. | Thông tin đơn hàng, quyền hoàn tiền, khóa ký webhook. |
| **Tác nhân đe dọa (threat actor)** | Chủ thể có khả năng hoặc động cơ thực hiện hành vi gây hại. | Người dùng bên ngoài, tài khoản khách bị chiếm, đối tác tích hợp bị xâm phạm. |
| **Bề mặt tấn công (attack surface)** | Tổng các điểm tiếp xúc, chức năng và đường truyền mà một tác nhân có thể tương tác để ảnh hưởng hệ thống. | REST API, trang đăng nhập, endpoint webhook, file upload, cổng quản trị, dependency/build pipeline. |
| **Điểm vào (entry point)** | Đường cụ thể để dữ liệu hoặc lệnh đi từ một nguồn vào hệ thống. | POST /api/orders, message consumer, sự kiện từ dịch vụ đối tác. |
| **Ranh giới tin cậy (trust boundary)** | Vị trí mà dữ liệu/danh tính đi giữa các miền có mức tin cậy hoặc quyền khác nhau. | Trình duyệt → backend; API → cơ sở dữ liệu; dịch vụ ngoài → webhook. |
| **Đe dọa (threat)** | Tình huống một tác nhân có thể làm tổn hại tài sản. | Khách A xem đơn của khách B. |
| **Lỗ hổng (vulnerability)** | Điểm yếu cụ thể khiến đe dọa có thể xảy ra. | Endpoint lấy đơn theo ID nhưng không kiểm tra owner. |
| **Rủi ro (risk)** | Kết hợp khả năng xảy ra và mức độ tác động trong bối cảnh cụ thể. | Rò rỉ dữ liệu khách hàng trên một API có thể truy cập công khai. |
| **Biện pháp kiểm soát (control)** | Cách ngăn ngừa, phát hiện, giới hạn hoặc khắc phục tác động. | Kiểm tra quyền sở hữu, rate limit, xác minh chữ ký, audit log. |

**Threat modeling khác việc chạy công cụ quét lỗ hổng.** Công cụ quét có thể phát hiện phiên bản thư viện lỗi thời hoặc cấu hình HTTP bất thường; nó khó tự hiểu quy tắc nghiệp vụ “người dùng chỉ đọc đơn của chính mình”. Threat modeling cần cả hiểu biết về kiến trúc, quyền, dữ liệu và các trường hợp sử dụng sai.

**Bề mặt tấn công không đồng nghĩa chỉ với API công khai.** Một message queue, tác vụ định kỳ, file được import, API quản trị chỉ mở trong mạng nội bộ hoặc pipeline CI/CD vẫn có thể trở thành đường dẫn tới tài sản quan trọng. Có thể giảm số điểm phơi lộ mà không loại bỏ hết rủi ro; mục tiêu là hiểu và kiểm soát các đường có khả năng bị khai thác.

## 2. Bắt đầu từ tài sản và mục tiêu bảo vệ

Trước khi đếm endpoint, cần biết **điều gì sẽ bị ảnh hưởng** nếu một điểm vào bị lợi dụng.

Giả sử hệ thống quản lý đơn hàng có các tài sản sau:

| Tài sản | Yêu cầu bảo vệ quan trọng | Nếu mất kiểm soát |
| --- | --- | --- |
| Hồ sơ khách và địa chỉ giao hàng | **Bí mật** và truy cập đúng chủ sở hữu | Lộ thông tin cá nhân. |
| Đơn hàng, số tiền, trạng thái thanh toán | **Toàn vẹn** | Thay số tiền hoặc giả mạo trạng thái “đã thanh toán”. |
| Chức năng hoàn tiền và cập nhật vai trò | **Phân quyền** và khả năng truy vết | Hoàn tiền trái phép hoặc nâng quyền. |
| JWT, session cookie, API key, khóa ký webhook | **Bí mật**, vòng đời và thu hồi phù hợp | Giả mạo danh tính hoặc yêu cầu đối tác. |
| API và hàng đợi xử lý đơn | **Sẵn sàng** và giới hạn tài nguyên | Nghẽn tài nguyên, chậm xử lý đơn. |
| Log/audit trail | **Toàn vẹn** và đủ bằng chứng | Không xác định được thao tác nhạy cảm đã xảy ra. |

Ba thuộc tính nền tảng thường dùng là **CIA**: Confidentiality (bí mật), Integrity (toàn vẹn) và Availability (sẵn sàng). Với ứng dụng nghiệp vụ còn cần xét kiểm soát quyền, tính xác thực của hành động, khả năng truy vết, quyền riêng tư và an toàn vận hành.

Đặt câu hỏi cụ thể: “Nếu khách A biết ID đơn của khách B thì điều gì phải ngăn A đọc dữ liệu đó?”; “Ai được phép đánh dấu đơn đã thanh toán, và bằng chứng nào được chấp nhận?”; “Mất quyền truy cập vào endpoint quản trị gây hậu quả nào?”. Câu hỏi về tài sản định hướng việc tìm đường tấn công, thay vì bắt đầu bằng một danh sách lỗ hổng chung chung.

## 3. Xác định phạm vi, người dùng và giả định

Một mô hình có ích phải ghi rõ **phạm vi**: phiên bản, môi trường và thành phần được xét. Ví dụ:

- Ứng dụng Java 17+ và Spring Boot với REST API cho khách mua hàng và nhân viên quản trị.
- Trình duyệt/mobile gọi API qua reverse proxy hoặc gateway.
- Backend dùng cơ sở dữ liệu đơn hàng, object storage để lưu tài liệu và message queue cho xử lý bất đồng bộ.
- Đơn vị thanh toán gọi endpoint webhook để báo sự kiện.
- Backend có thể gọi một dịch vụ ngoài để kiểm tra thông tin vận chuyển.
- Monitoring/management endpoint và CI/CD tồn tại nhưng có phạm vi truy cập riêng.

Đây là các **giả định để thực hành**; mỗi dự án phải thay bằng sơ đồ, URL, cấu hình và quyền triển khai thật. Ghi rõ phần chưa xác minh như “có chắc webhook chỉ được gọi từ nhà cung cấp?”, “management endpoint có nằm sau gateway?”, “ứng dụng dùng cookie-session hay bearer token?”. Một giả định chưa được kiểm chứng không được xem là biện pháp bảo vệ.

Đồng thời xác định **tác nhân và khả năng**:

- Khách chưa đăng nhập: gửi được request tới đường công khai, tự điều khiển path, query, body và nhiều header.
- Khách đã đăng nhập: có quyền hợp lệ với tài khoản của **chính mình** nhưng có thể thử truy cập ID của người khác.
- Nhân viên nội bộ: có một số đặc quyền; cần xét nguy cơ lạm dụng hoặc tài khoản bị chiếm.
- Dịch vụ đối tác: gửi dữ liệu vào webhook, có thể gửi lại sự kiện hoặc bị giả mạo nếu cơ chế xác thực yếu.
- Quy trình tự động và dependency: có quyền truy cập dữ liệu hoặc hạ tầng theo cấu hình, tạo thêm chuỗi rủi ro khi bị xâm phạm.

Không giả định “nằm trong mạng nội bộ” nghĩa là luôn đáng tin: một tài khoản, workload hoặc máy nội bộ cũng có thể bị chiếm quyền.

## 4. Vẽ luồng dữ liệu và đánh dấu ranh giới tin cậy

Sơ đồ luồng dữ liệu (data-flow diagram, DFD) giúp nhìn thấy điểm dữ liệu đi vào và vượt qua ranh giới. Ví dụ đơn giản:

~~~mermaid
flowchart LR
    U["Khách hàng / trình duyệt"] -->|"HTTP request"| G["Gateway"]
    E["Đối tác thanh toán"] -->|"Webhook"| G
    G -->|"HTTP"| A["Spring Boot API"]
    A -->|"Đọc/ghi đơn"| D[("Orders DB")]
    A -->|"Upload/download"| F[("Object Storage")]
    A -->|"Sự kiện đơn"| Q["Message Queue"]
    Q --> W["Order Worker"]
    A -->|"HTTPS"| S["Dịch vụ vận chuyển"]
    OP["Nhân viên vận hành"] -->|"Management access"| M["Management Endpoint"]
~~~

Mỗi mũi tên đại diện **một luồng cần đánh giá**, không ngầm khẳng định tất cả thành phần nằm chung mức tin cậy. Cần chú thích thêm khu vực Internet, gateway/DMZ, runtime backend, dữ liệu, mạng vận hành, hệ thống đối tác, kênh deploy. Một số ranh giới chính:

1. **Internet → gateway/API:** dữ liệu người dùng tự cung cấp; cần xác thực, giới hạn đầu vào, phân quyền và giới hạn lưu lượng.
2. **Đối tác → webhook:** nhận thông điệp từ hệ thống ngoài; cần kiểm chứng nguồn/bằng chứng, tính toàn vẹn, thời hạn và chống phát lại tùy giao thức.
3. **Ứng dụng → cơ sở dữ liệu:** ứng dụng có thể truy cập nhiều bản ghi hơn quyền của người dùng; phải giữ kiểm soát quyền ở tầng nghiệp vụ, truy vấn và tài khoản DB.
4. **API → queue/worker:** thông điệp có thể đến muộn, lặp hoặc sai thứ tự; worker không nên coi mọi trường dữ liệu là hợp lệ chỉ vì đã qua queue.
5. **Backend → dịch vụ ngoài:** cần kiểm soát URL/host đích, credentials, dữ liệu được gửi đi, timeout và kết quả trả về.
6. **Vận hành → management/CI/CD:** đây là đường có đặc quyền cao, cần quản lý danh tính, mạng, secrets và nhật ký thay đổi.

**Một ranh giới tin cậy có thể nằm bên trong cùng một process hoặc hệ thống.** Ví dụ: principal đã xác thực nhưng không có quyền hoàn tiền; một Service dùng quyền hệ thống để truy vấn DB nhưng phải kiểm tra quyền của khách theo từng bản ghi.

Đối với mỗi mũi tên, ghi: nguồn → đích, dữ liệu đi qua, giao thức, danh tính sử dụng, mức tin cậy, xác thực ở đâu, phân quyền ở đâu, có lưu/log dữ liệu không và điều gì sẽ xảy ra nếu dữ liệu bị sửa, giả mạo, lặp hoặc biến mất.

## 5. Lập bảng kiểm kê bề mặt tấn công

Sau sơ đồ tổng quan, tạo **inventory** cho các điểm vào, điểm ra, interface đặc quyền và đường cung ứng phần mềm. Bảng ví dụ:

| Điểm tiếp xúc | Ai điều khiển đầu vào? | Dữ liệu/quyền liên quan | Câu hỏi cần kiểm tra |
| --- | --- | --- | --- |
| GET /api/catalog | Người dùng Internet | Dữ liệu sản phẩm công khai | Có rò rỉ trường nội bộ hoặc dữ liệu của khách? |
| POST /api/orders | Khách đã đăng nhập | Giá, số lượng, danh tính người mua | Có tin giá tiền do client tự gửi? Có chống gửi lặp? |
| GET /api/orders/{id} | Khách đã đăng nhập | Đơn của từng khách | Có kiểm tra owner/tenant theo từng ID? |
| POST /api/payments/webhook | Dịch vụ ngoài; cũng có thể bị gọi giả | Trạng thái thanh toán | Chữ ký, timestamp, event ID, idempotency được xác minh thế nào? |
| POST /api/documents | Khách đã đăng nhập | File và object storage | Giới hạn kích thước/loại file/quyền đọc lại ra sao? |
| /api/admin/** | Nhân viên và người có thể gửi request | Hoàn tiền, cập nhật quyền | Phân quyền chi tiết, ghi audit và xác nhận thao tác nhạy cảm? |
| Consumer của orders.created | Producer và message broker | Lệnh xử lý đơn | Tin cậy schema/producer tới mức nào? Xử lý sự kiện lặp ra sao? |
| HTTP client gọi dịch vụ ngoài | Backend, đầu vào gián tiếp từ user | Egress network, token đối tác | URL đích có bị người dùng thao túng thành SSRF? |
| /actuator/** hoặc cổng management | Mạng vận hành nếu cấu hình đúng | Health, metrics, thông tin vận hành | Cổng và endpoint nào thực sự được expose; có xác thực hay giới hạn mạng? |
| CI/CD và kho artifacts | Người có quyền repo/build | Credentials deploy, quyền phát hành | Secrets, branch protection, dependency và supply chain được quản lý ra sao? |

Đây là **ứng viên cần điều tra**; bảng không nói rằng endpoint đó đang tồn tại hoặc có lỗi trong dự án nào khác.

Cần xem cả các đường **không đi qua Controller**: scheduled jobs, WebSocket, GraphQL, batch import CSV/Excel, file parser, message listener, RPC/gRPC, callback đăng nhập, email links, static files, debug endpoints, health/metrics, cache/backup, container/admin console, cloud IAM, object storage public ACL và endpoint nội bộ giữa microservice.

Để tìm inventory thật, đối chiếu nhiều nguồn: sơ đồ triển khai, bản cấu hình gateway/Ingress, danh sách route/controller, Spring SecurityFilterChain, OpenAPI/Swagger, actuator mapping nếu được phép, job/consumer definitions, dependency và các tích hợp ngoài. **Chỉ nhìn source code hoặc chỉ nhìn danh sách URL ngoài Internet đều chưa đủ**, vì thực tế có thể khác: route được mount qua gateway, management dùng cổng riêng, proxy rewrite path hoặc endpoint phụ được bật theo profile.

## 6. Cách phân tích đe dọa bằng STRIDE

STRIDE là bộ câu hỏi để không bỏ sót các kiểu đe dọa phổ biến. Hãy áp dụng nó **trên từng thành phần và luồng dữ liệu** đã vẽ, thay vì chỉ tick một checklist.

| Nhóm STRIDE | Câu hỏi gợi mở | Ví dụ ở hệ thống đơn hàng |
| --- | --- | --- |
| **S — Spoofing (giả mạo danh tính)** | Có ai giả làm user, service hoặc đối tác được không? | Gửi webhook giả danh nhà cung cấp thanh toán. |
| **T — Tampering (sửa đổi)** | Dữ liệu/lệnh có thể bị sửa trái phép khi truyền hoặc lưu không? | Client tự đổi số tiền khi tạo đơn; sửa message trong queue. |
| **R — Repudiation (chối bỏ)** | Có thể xác định ai đã thực hiện thao tác nhạy cảm không? | Không biết nhân viên nào đã hoàn tiền. |
| **I — Information Disclosure (lộ thông tin)** | Dữ liệu nào có thể lộ cho chủ thể sai? | Khách A đọc đơn của khách B; token lọt vào log. |
| **D — Denial of Service (từ chối dịch vụ)** | Có điểm nào bị làm cạn tài nguyên không? | Gửi file khổng lồ, tạo quá nhiều job, gọi API tốn DB. |
| **E — Elevation of Privilege (leo thang đặc quyền)** | Chủ thể có thể làm vượt quyền đã cấp không? | User thường gọi chức năng admin; token của worker có quyền quá lớn. |

STRIDE là **phương pháp gợi ý đe dọa**, không phải bằng chứng về lỗ hổng. Có thể kết hợp với các kiểu sai sót API thường gặp như **BOLA/IDOR** (truy cập sai đối tượng), **broken function-level authorization** (gọi chức năng sai vai trò), mass assignment, SSRF, injection, cấu hình sai, lạm dụng business flow, thiếu giới hạn tài nguyên. Một nguy cơ có thể liên quan nhiều nhóm STRIDE.

Những câu hỏi hữu ích cho từng điểm vào:

- Nếu đổi **danh tính**: client có giả được user ID/role qua header hoặc tham số không?
- Nếu đổi **đối tượng**: ID bản ghi có bị thay bằng ID người khác được không?
- Nếu đổi **trạng thái**: có thể yêu cầu chuyển trạng thái trái quy trình hoặc gửi lặp sự kiện không?
- Nếu đổi **khối lượng**: request rất lớn, nhiều lần, đồng thời hoặc chậm có làm cạn tài nguyên không?
- Nếu đổi **nguồn dữ liệu**: file, message hay phản hồi đối tác có được tin quá mức không?
- Nếu người dùng không qua trình duyệt chính thức: API còn kiểm soát đúng khi gọi bằng script hoặc client khác không?

## 7. Đi sâu vào các đường tấn công minh họa

### 7.1. Đọc đơn hàng của người khác (BOLA/IDOR)

**Tài sản:** thông tin đơn, địa chỉ, lịch sử giao dịch. **Điểm vào:** GET /api/orders/{id}. **Tác nhân:** người dùng đã đăng nhập nhưng chỉ có quyền đối với đơn của mình.

Kịch bản cần xét: client thay {id} từ đơn của A sang đơn của B. Nếu server chỉ xác nhận “đã đăng nhập” rồi tìm đơn theo ID, kiểm tra Authentication đã thành công nhưng **ủy quyền theo đối tượng** thất bại.

Biện pháp phù hợp: lấy user/tenant từ principal đã được xác thực; Service truy vấn theo cặp (orderId, ownerId/tenantId) hoặc kiểm tra quyền ở tầng dữ liệu; không tin ownerId client tự cung cấp; giới hạn dữ liệu trả về. Thêm test đăng nhập A yêu cầu đơn của B và xác minh **không nhận được nội dung của B**, kể cả khi ID tồn tại. Trả 403 hoặc 404 tùy thiết kế che giấu sự tồn tại, nhưng phải nhất quán.

### 7.2. Giả mạo hoặc phát lại webhook thanh toán

**Tài sản:** trạng thái thanh toán và số tiền. **Điểm vào:** POST /api/payments/webhook. **Ranh giới:** nhà cung cấp ngoài → backend.

Kịch bản: hệ thống dựa vào trường status=PAID trong body mà không xác minh thông điệp, hoặc chấp nhận cùng một sự kiện nhiều lần gây hành động lặp như ghi nhận giao dịch/hoàn tiền hai lần.

Cần xác minh chữ ký/HMAC hoặc cơ chế nhà cung cấp quy định, sử dụng raw body khi đặc tả ký yêu cầu, kiểm timestamp/thời hạn và event ID, lưu trạng thái xử lý idempotent, kiểm số tiền/currency/order reference bằng dữ liệu server đang có, và kiểm tra chuyển trạng thái hợp lệ. **Chỉ giới hạn IP, chỉ dùng HTTPS hoặc chỉ đặt đường dẫn khó đoán thường không đủ** để chứng minh thông điệp là thật.

Kiểm thử: chữ ký sai, sự kiện cũ, sự kiện trùng, giao dịch tham chiếu đơn không tồn tại, số tiền không khớp, các sự kiện đến sai thứ tự.

### 7.3. Gọi URL do người dùng cung cấp (SSRF)

**Tài sản:** metadata nội bộ, token, tài nguyên trong mạng không công khai. **Điểm vào:** chức năng backend tải ảnh/tài liệu từ URL được nhập.

Kịch bản: backend có thể truy cập hệ thống nội bộ; nếu người dùng điều khiển URL, ứng dụng có thể bị biến thành bên gửi request tới địa chỉ mà người dùng không truy cập trực tiếp được.

Biện pháp: tốt nhất chỉ gọi các domain/đích nghiệp vụ cần thiết; xác minh scheme và host, kiểm tra địa chỉ mạng sau DNS và khi chuyển hướng, hạn chế egress ở tầng mạng, timeout/response size; không gửi credential nhạy cảm theo URL không tin cậy. Chỉ chặn một vài chuỗi ký tự trong URL không đủ trước biến thể DNS/redirect.

Kiểm thử theo môi trường an toàn: URL hợp lệ; domain không trong danh sách cho phép; đường dẫn redirect ra đích không được phép; địa chỉ mạng nội bộ/metadata bị từ chối.

### 7.4. Cookie-session và hành động thay đổi dữ liệu

Nếu ứng dụng dùng cookie tự gửi theo request, kẻ tấn công có thể tìm cách khiến trình duyệt người dùng thực hiện hành động ngoài ý muốn. **CSRF** là nguy cơ cần xét với cơ chế xác thực và client cụ thể. Spring Security có hỗ trợ CSRF, nhưng đội phát triển phải hiểu vì sao bật/tắt, token được cấp và gửi theo cách nào, cookie áp dụng SameSite/Secure/HttpOnly ra sao.

Hỏi tiếp: API dùng Bearer token do JavaScript chủ động đưa vào Authorization hay cookie-session? Có endpoint POST/PUT/DELETE nào thiếu cơ chế chống giả mạo không? Browser CORS có được hiểu đúng không? **CORS không thay thế CSRF hoặc phân quyền server**.

### 7.5. Tệp tải lên và xử lý bất đồng bộ

Một upload có thể vượt giới hạn kích thước, có nội dung sai loại, khai thác parser, bị lưu ở khu vực công khai hoặc được một worker xử lý với quyền cao hơn người gửi. Đường queue làm xuất hiện thêm các vấn đề: retry, duplicate, poison message, nghẽn tài nguyên và sự kiện đến sai thứ tự.

Cần giới hạn kích thước/số lượng, xác minh loại file theo nội dung khi phù hợp, lưu cách ly, dùng quyền storage tối thiểu, scan/xử lý tại môi trường hạn chế, giới hạn số lượt thử và đưa message lỗi vào dead-letter queue theo chính sách. Worker phải xác thực dữ liệu và điều kiện nghiệp vụ của **chính hành động worker thực hiện**.

### 7.6. Lộ đường quản trị hoặc cấu hình vận hành

Endpoint quản trị và management cần được xác định theo môi trường: path nào, port nào, ai được kết nối, middleware nào bảo vệ. Spring SecurityFilterChain bảo vệ một nhóm URL trên ứng dụng **không tự chứng minh** rằng một cổng management riêng, proxy khác hoặc console hạ tầng cũng được bảo vệ như thế.

Hạn chế expose các chức năng không cần thiết, áp dụng authn/authz và network policy, quản lý secrets/role đặc quyền tối thiểu, giám sát thay đổi cấu hình và cập nhật bản vá. Cũng cần bảo vệ đường deploy vì credential CI/CD có thể đủ quyền sửa ứng dụng ngay cả khi API được bảo vệ tốt.

## 8. Từ đe dọa sang kế hoạch kiểm soát có thể kiểm chứng

Một danh sách “có thể bị tấn công” chỉ hữu ích khi nối được với hậu quả, biện pháp và một cách kiểm chứng cụ thể. Có thể dùng **risk register**:

| Mã | Kịch bản / ranh giới | Khả năng và tác động giả định | Kiểm soát cần có | Bằng chứng xác minh |
| --- | --- | --- | --- | --- |
| TM-01 | A đọc đơn của B qua API | Khả năng cao nếu thiếu owner check; tác động cao | Authorization theo owner/tenant trong Service | Test cross-user/cross-tenant, kiểm response không lộ dữ liệu |
| TM-02 | Webhook giả xác nhận thanh toán | Tác động cao; khả năng tùy cơ chế xác minh hiện có | Signature, timestamp, idempotency, reconciliation | Test signature sai, replay, amount mismatch |
| TM-03 | URL import gọi tới mạng nội bộ | Tùy việc có nhận URL từ user và cấu hình egress | Allowlist đích, chặn IP nội bộ, network egress policy | Test redirect/DNS/địa chỉ cấm |
| TM-04 | Flood upload làm cạn tài nguyên | Tùy rate limit, quota và workload | Size limit, quota, timeout, backpressure | Load test được cấp phép, metric tài nguyên |
| TM-05 | Admin/management bị expose | Tác động cao; khả năng phụ thuộc mạng và quyền | Giới hạn network, xác thực, phân quyền, audit | Kiểm tra từ vùng mạng ngoài, thử quyền thấp |

**Các mức đánh giá trong bảng chỉ là giả định phục vụ học tập.** Muốn ưu tiên thật, phải biết điểm nào có thể truy cập, điều kiện khai thác, khả năng bị lợi dụng, dữ liệu bị ảnh hưởng, controls hiện có và nhu cầu nghiệp vụ. Không biến số giả định thành “điểm rủi ro chuẩn”.

Một cách phân mức thực dụng:

- **Ưu tiên rất cao:** đường có thể tiếp cận, hậu quả nghiêm trọng, thiếu kiểm soát trọng yếu hoặc có bằng chứng khai thác.
- **Ưu tiên cao:** tác động lớn nhưng có một số điều kiện/kiểm soát làm giảm khả năng.
- **Ưu tiên trung bình/thấp:** đường khó tiếp cận hơn, tài sản ít nhạy cảm hoặc hậu quả giới hạn, nhưng vẫn phải có chủ sở hữu và lịch xem lại.

Tác động nên xét cả **confidentiality, integrity, availability, tiền, pháp lý và khách hàng**. Khi chưa đủ dữ liệu để xếp mức, ghi **“cần xác minh”** thay vì đoán. Mỗi mục nên có chủ sở hữu, hướng xử lý (giảm thiểu, chấp nhận có phê duyệt, chuyển giao hoặc loại bỏ chức năng), trạng thái và thời điểm kiểm tra lại.

## 9. Spring Security hỗ trợ phần nào trong mô hình?

Với ứng dụng Spring MVC/Servlet, Spring Security tổ chức xử lý xác thực và phân quyền quanh **SecurityFilterChain**. Nó có thể giúp xác thực HTTP request, giới hạn route theo role/authority, bảo vệ CSRF theo cấu hình, quản lý SecurityContext và áp dụng method security. Những cơ chế này là **controls** đối với một số đe dọa đã phát hiện.

Ví dụ cấu hình minh họa đặt chính sách URL. Đây là **một mảnh cấu hình dành cho ứng dụng Spring Boot đã có Spring Security dependency**, không phải chương trình Java độc lập:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Các class trong đoạn này đến từ Spring Security: HttpSecurity, SecurityFilterChain, HttpMethod từ Spring Framework. **Đoạn mã chỉ diễn tả chính sách truy cập đường dẫn**, không cung cấp cơ chế đăng nhập, token, user store, quyền object, xác minh webhook, network controls hoặc bảo vệ các cổng nằm ngoài filter chain được cấu hình. Cơ chế xác thực cần được cấu hình phù hợp với loại client; việc để CSRF mặc định hay điều chỉnh phải gắn với threat model thực tế.

Trong ví dụ trên, điều kiện authenticated() ở /api/orders/** **không đảm bảo** người dùng A không đọc đơn B. Cần một quy tắc cấp dữ liệu:

~~~text
Danh tính đã xác thực: customerId = A
Yêu cầu: GET /api/orders/42
Service tra cứu: orderId = 42 AND ownerId = A
Nếu không tìm thấy hoặc không được phép → không trả dữ liệu đơn 42
~~~

Tương tự, hasRole("ADMIN") chưa thể chứng minh nhân viên đó được hoàn tiền đơn cụ thể với mọi trạng thái. Quy tắc cấp đối tượng, trạng thái và ngữ cảnh thường thuộc Service/domain; có thể hỗ trợ bằng method security nếu phù hợp. Lưu ý self-invocation có thể bỏ qua Spring proxy khi triển khai kiểm soát ở method, vì vậy phải kiểm tra thực tế qua đường gọi ứng dụng.

Một threat model tốt giúp **chọn đúng control**; nó không yêu cầu thêm filter hoặc thêm annotation vào mọi hàm một cách máy móc.

## 10. Ví dụ Java 17: ghi nhận các luồng đi qua ranh giới

Để tránh chỉ nói bằng lý thuyết, có thể viết một chương trình nhỏ biểu diễn **inventory tĩnh** của hệ thống giả định. Chương trình sau không quét mạng, không phát hiện lỗ hổng và không tự quyết định luồng nào nguy hiểm; nó chỉ in ra các điểm cần xem xét.

Lưu thành tệp **SurfaceInventory.java**:

~~~java
import java.util.List;

public class SurfaceInventory {

    record Flow(
        String interfaceName,
        String sourceZone,
        String targetZone,
        String data
    ) {}

    public static void main(String[] args) {
        List<Flow> flows = List.of(
            new Flow("GET /api/orders/{id}", "Browser", "API", "Order details"),
            new Flow("POST /api/payments/webhook", "PaymentPartner", "API", "Payment event"),
            new Flow("EVENT orders.created", "Queue", "Worker", "Order event"),
            new Flow("SQL orders lookup", "API", "Database", "Order records"),
            new Flow("GET /actuator/health", "OpsNetwork", "Management", "Health data")
        );

        for (Flow flow : flows) {
            System.out.println(
                flow.interfaceName() + " | "
                + flow.sourceZone() + " -> " + flow.targetZone()
                + " | " + flow.data()
            );
        }
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac SurfaceInventory.java
java SurfaceInventory
~~~

**Kết quả stdout chính xác:**

~~~text
GET /api/orders/{id} | Browser -> API | Order details
POST /api/payments/webhook | PaymentPartner -> API | Payment event
EVENT orders.created | Queue -> Worker | Order event
SQL orders lookup | API -> Database | Order records
GET /actuator/health | OpsNetwork -> Management | Health data
~~~

Từ output, hãy bổ sung bằng **phân tích của con người**: mỗi sourceZone có đáng tin không, ai điều khiển input, điều gì được bảo vệ ở targetZone, khả năng giả mạo/tampering/replay/DoS, cách phân quyền và test phủ định. Khi làm thực tế, inventory nên có dữ liệu kiểm chứng từ mã nguồn và cấu hình triển khai; không coi danh sách hard-code này là bằng chứng hệ thống thực.

## 11. Quy trình threat modeling gọn cho một tính năng mới

Áp dụng vòng lặp sau với chức năng “khách tạo và xem đơn hàng”:

1. **Chốt phạm vi:** phiên bản release, các endpoint/tác vụ liên quan, môi trường và điều không nằm trong phạm vi.
2. **Xác định tài sản:** dữ liệu đơn, tài khoản, tiền, secret, khả năng xử lý và nhật ký cần bảo vệ.
3. **Vẽ luồng:** client → gateway → API → DB/queue/third-party; chú thích nơi đổi quyền và mức tin cậy.
4. **Kiểm kê bề mặt:** từng method/path, body, file, header, callback, consumer, cổng admin; xác minh với deployment thật.
5. **Tìm kịch bản sai:** áp dụng STRIDE và các abuse case như đổi ID, sửa tiền, giả webhook, gửi lặp, flooding, gọi chức năng ngoài vai trò.
6. **Ưu tiên và giao trách nhiệm:** mô tả tác động, điều kiện, control hiện có, owner, mức ưu tiên và hạng mục còn thiếu bằng chứng.
7. **Thực thi và kiểm chứng:** triển khai kiểm soát phù hợp, thêm test phủ định, quan sát log/metrics và rà lại khi có thay đổi kiến trúc.

**Mẫu ghi một đe dọa hoàn chỉnh:**

~~~yaml
id: TM-ORDERS-001
asset: Customer order details
entry_point: GET /api/orders/{id}
actor: Authenticated user without ownership
trust_boundary: Browser -> API -> Order data
threat: Read another customer's order by changing the order ID
preconditions: Endpoint accessible to logged-in users
impact: Unauthorized exposure of order and address information
controls:
  - Authorize by current principal and order owner/tenant
  - Limit fields returned in the response
verification:
  - User A requesting User B's order receives no B data
  - Cross-tenant access is also denied
owner: Order API team
status: Proposed; confirm against the deployed implementation
~~~

Các giá trị trên mô tả **bài tập giả định**, không phải phát hiện đã được xác nhận ở một hệ thống cụ thể. Khi lập hồ sơ thực tế, thay bằng bằng chứng, công việc và chủ sở hữu thật.

## 12. Ma trận kiểm thử phủ định theo ranh giới

Một cách đơn giản để biến threat model thành hành động là lập ma trận **ai → làm gì → với tài nguyên nào → kỳ vọng**:

| Chủ thể / tình huống | Hành động kiểm thử | Kỳ vọng an toàn |
| --- | --- | --- |
| Chưa đăng nhập | Xem đơn riêng của người khác | Không trả nội dung đơn. |
| User A | Xem/sửa đơn thuộc User B | Không cho phép truy cập hoặc thay đổi. |
| User A | Gửi trường totalAmount cao/thấp tùy ý | Server tính/kiểm giá từ nguồn tin cậy theo nghiệp vụ. |
| User thường | Gọi chức năng hoàn tiền dành cho admin | Bị từ chối và không có side effect. |
| Webhook không có chữ ký hợp lệ | Báo đơn đã thanh toán | Không cập nhật trạng thái thanh toán. |
| Webhook đúng nhưng gửi trùng event ID | Phát lại sự kiện | Không thực hiện tác động nghiệp vụ trùng lặp. |
| Upload file quá lớn hoặc sai loại | Gửi file | Bị giới hạn/kiểm soát, không làm cạn tài nguyên. |
| URL import không thuộc đích cho phép | Yêu cầu backend tải nội dung | Không gọi tới đích bị cấm. |
| Người ngoài mạng vận hành | Truy cập management endpoint riêng | Không lộ thông tin hoặc quyền vận hành. |

Kiểm thử nên đặt ở **đường gọi thực sự**: HTTP + filter chain + Service + dữ liệu/quyền, hoặc message listener/worker khi đường vào không phải HTTP. Kiểm thử “trả 403” chưa đủ nếu trước khi trả lỗi hệ thống đã thực hiện thay đổi; cần xác minh trạng thái DB, message, giao dịch và log liên quan.

Dùng môi trường, tài khoản và dữ liệu thử được phép kiểm tra; không đưa tài khoản thật, token thật hoặc thông tin nhạy cảm vào bài kiểm thử hay log chụp kết quả.

## 13. Dấu hiệu một mô hình còn thiếu

- Chỉ kiểm kê **GET/POST Controller** mà quên queue, file, admin, CI/CD, hệ thống thứ ba.
- Chỉ đánh dấu “đã login”, bỏ qua **quyền với từng đối tượng, từng tenant và từng hành động**.
- Ghi “đã có Spring Security” như câu trả lời cho mọi đe dọa, không chỉ ra matcher, policy, trust boundary và test.
- Coi JSON từ một Service nội bộ hoặc thông điệp từ queue là tự động đáng tin.
- Trộn giả định chưa kiểm chứng với bằng chứng đã xác nhận; không lưu nguồn, người chịu trách nhiệm, phiên bản.
- Xếp tất cả đe dọa là “high” hoặc dùng điểm số tùy ý mà không xét tài sản và điều kiện tiếp cận.
- Chỉ liệt kê lỗ hổng kỹ thuật, bỏ qua **lạm dụng quy trình nghiệp vụ** (đổi chủ sở hữu, hoàn tiền lặp, sai trạng thái).
- Chỉ kiểm thử luồng thành công; không có test về quyền thấp, object khác owner, thông điệp giả, trùng hoặc input cực trị.
- Xong một lần rồi bỏ: tính năng mới, route mới, tích hợp mới, thay đổi cách dùng cookie/JWT hay phân vùng mạng đều làm **mô hình cần được xem lại**.

## 14. Bài tập thực hành

Chọn một tính năng có ít nhất **hai vai trò** và **một tài sản nhạy cảm** (ví dụ khách xem đơn và admin hoàn tiền). Trong 30–45 phút, tạo các sản phẩm sau:

1. Một sơ đồ có client, API, kho dữ liệu và ít nhất một ranh giới tin cậy.
2. Một bảng liệt kê từng điểm vào, danh tính/đầu vào do ai kiểm soát và tài sản bị ảnh hưởng.
3. Ít nhất ba kịch bản STRIDE hoặc abuse case **có điều kiện, hậu quả và giả định rõ ràng**.
4. Mỗi kịch bản có một control cụ thể và một test phủ định có thể thực thi.
5. Một danh sách điều chưa biết cần hỏi DevOps, QA hoặc chủ sở hữu nghiệp vụ trước khi ưu tiên.

Tự đánh giá bằng ba câu hỏi: **(1)** Có đường nào đi vào hệ thống không qua Controller? **(2)** Có chỗ nào “đăng nhập hợp lệ” nhưng vẫn không được phép truy cập tài nguyên? **(3)** Biện pháp nào đã có **bằng chứng kiểm thử**, biện pháp nào mới là giả định?

## Kết luận

Mô hình đe dọa bắt đầu từ **tài sản và luồng dữ liệu**, phát hiện các **điểm tiếp xúc và ranh giới tin cậy**, sau đó đặt giả thuyết về các cách danh tính, dữ liệu hoặc quyền có thể bị lạm dụng. Spring Security giúp thực thi nhiều biện pháp xác thực và phân quyền, nhưng chính sách nghiệp vụ, quyền theo đối tượng, integrations, hạ tầng, kiểm thử và vận hành vẫn cần được xem xét có chủ đích. Giá trị cuối cùng của threat modeling là **bản đồ rủi ro có thể hành động và kiểm chứng**, được cập nhật khi ứng dụng thay đổi.
