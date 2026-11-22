# 1.2 Mô hình đe dọa, tài sản cần bảo vệ và ranh giới tin cậy

Mô hình đe dọa (*threat modeling*) là cách phân tích một hệ thống từ góc nhìn an toàn: **đang bảo vệ điều gì, ai hoặc điều gì có thể gây hại, họ tiếp cận qua đâu, và biện pháp nào làm rủi ro còn ở mức chấp nhận được?** Đây là hoạt động thiết kế và đánh giá lặp lại theo thay đổi của hệ thống, không phải bảng liệt kê lỗ hổng hay một lần chạy công cụ quét bảo mật.

Trong module **Java Advance - security-cryptography**, mô hình đe dọa giúp quyết định chỗ nào cần xác thực, phân quyền, bảo vệ tính toàn vẹn, mã hóa, quản lý khóa, kiểm toán và giới hạn tài nguyên. Chọn thuật toán mã hóa trước khi xác định tài sản và đường tấn công dễ dẫn đến giải pháp an toàn trên một đường truyền nhưng vẫn làm lộ dữ liệu ở lớp ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **tài sản**, **tác nhân đe dọa**, **đe dọa**, **lỗ hổng**, **kịch bản tấn công**, **kiểm soát** và **rủi ro còn lại**.
2. Liệt kê tài sản theo vòng đời dữ liệu, gồm dữ liệu gốc, khóa bí mật, token, quyền truy cập, log và bản sao lưu; xác định thuộc tính bảo mật cần giữ cho từng tài sản.
3. Vẽ được luồng dữ liệu và **ranh giới tin cậy** giữa client, dịch vụ Java, cơ sở dữ liệu, dịch vụ quản lý khóa và bên thứ ba.
4. Dùng STRIDE cùng kịch bản lạm dụng nghiệp vụ để tìm đường tấn công cụ thể, xếp ưu tiên, chọn kiểm soát và lập phép kiểm chứng.
5. Nhận ra vì sao **TLS, mã hóa dữ liệu và xác thực người dùng không thay thế cho kiểm tra quyền trên từng tài nguyên**.

## 2. Khái niệm cốt lõi: đe dọa khác gì lỗ hổng?

| Khái niệm | Ý nghĩa | Ví dụ trong API tải tài liệu |
| --- | --- | --- |
| Tài sản (*asset*) | Điều có giá trị cần được bảo vệ | Nội dung hợp đồng, quyền sở hữu tệp, khóa giải mã |
| Tác nhân đe dọa (*threat actor*) | Người hoặc thực thể có khả năng gây hại, có chủ ý hay vô ý | Người dùng hợp lệ muốn đọc tài liệu của tổ chức khác; tài khoản dịch vụ bị chiếm |
| Bề mặt tấn công (*attack surface*) | Các điểm có thể tương tác với hệ thống | Endpoint HTTPS, webhook, job queue, API KMS, pipeline CI/CD |
| Đe dọa (*threat*) | Sự kiện/hành vi có thể vi phạm thuộc tính bảo mật | Người dùng thay `documentId` để đọc tài liệu không thuộc quyền mình |
| Lỗ hổng/điểm yếu (*vulnerability*) | Thiếu sót khiến đe dọa có đường thực hiện | API chỉ kiểm tra đã đăng nhập, bỏ qua quyền trên `documentId` |
| Kiểm soát (*control*) | Biện pháp phòng ngừa, phát hiện hoặc giảm tác hại | Phân quyền theo tài liệu và tenant, xác thực token, audit, quota |
| Rủi ro (*risk*) | Kết hợp khả năng xảy ra và tác động đối với mục tiêu bảo vệ | Lộ tài liệu khách hàng gây thiệt hại tài chính và pháp lý |
| Rủi ro còn lại (*residual risk*) | Rủi ro sau khi áp dụng và kiểm chứng kiểm soát | Tài khoản có quyền hợp lệ bị chiếm vẫn có thể tải tài liệu được cấp phép |

**Phân biệt quan trọng:** một ý tưởng tấn công chưa chứng minh rằng hệ thống hiện có lỗ hổng; ngược lại, không thấy lỗi qua một bài kiểm thử không chứng minh hệ thống không có đe dọa. Mô hình đe dọa ghi rõ *giả định*, *kịch bản* và *bằng chứng kiểm tra*, rồi cập nhật khi có thông tin mới.

Cách đặt câu hỏi hữu ích cho một kịch bản:

> “Ai có thể đưa dữ liệu hoặc lệnh vào qua ranh giới nào, với quyền gì, nhằm thay đổi tài sản nào, gây hại ra sao? Kiểm soát ở đâu, và làm thế nào kiểm tra kiểm soát đó?”

## 3. Xác định tài sản cần bảo vệ

Không chỉ dữ liệu kinh doanh mới là tài sản. Hãy liệt kê cả những thứ **cho phép truy cập hoặc giải mã dữ liệu**. Với mỗi tài sản, ghi chủ sở hữu, nơi tồn tại, người được quyền sử dụng, thời gian lưu giữ, luồng di chuyển và tác động nếu bị lộ/sửa/xóa/không truy cập được.

| Tài sản | Thuộc tính cần bảo vệ | Ví dụ đường phơi lộ hoặc bị thay đổi |
| --- | --- | --- |
| Bản rõ (*plaintext*) của tài liệu, dữ liệu cá nhân | Bí mật, toàn vẹn, quyền riêng tư | Response API, bộ nhớ tiến trình, bản tạm, log, bản sao lưu |
| Bản mã (*ciphertext*) và metadata | Toàn vẹn, tính sẵn sàng, liên kết đúng với chủ sở hữu | Object storage, URL đối tượng, metadata tenant, nonce/IV |
| Khóa đối xứng, khóa riêng, secret KMS, mật khẩu dịch vụ | Bí mật và quyền sử dụng; khả năng thu hồi/luân chuyển | Biến môi trường, file cấu hình, mã nguồn, CI log, IAM role |
| Token phiên, refresh token, API key | Bí mật, hạn sử dụng, phạm vi quyền | Header, cookie, cache, báo cáo lỗi, công cụ quan sát |
| Danh tính, role, policy, ACL, mối quan hệ tenant–object | Toàn vẹn và tính xác thực | Trường `ownerId` do client gửi, dữ liệu phân quyền trong DB |
| Audit log, thời điểm, request ID | Toàn vẹn, truy vết, giới hạn tiết lộ | Log bị sửa/xóa, log chứa token hoặc plaintext |
| Dịch vụ, quota, dữ liệu sao lưu, cấu hình hạ tầng | Sẵn sàng, khả năng khôi phục | DDoS, thao tác xóa, cấu hình sai, lỗi khóa/giải mã |

Các thuộc tính thường được xem xét:

- **Confidentiality (bí mật):** chủ thể không được phép không thể đọc nội dung.
- **Integrity (toàn vẹn):** sửa đổi trái phép được ngăn hoặc phát hiện.
- **Availability (sẵn sàng):** người được phép có thể dùng dịch vụ, kể cả trong điều kiện lỗi hợp lý.
- **Authenticity (tính xác thực):** danh tính hoặc nguồn gốc thông điệp được xác minh đúng.
- **Authorization (quyền):** danh tính hợp lệ chỉ thao tác đúng tài nguyên và hành động được cấp.
- **Accountability (truy vết):** hoạt động quan trọng được ghi nhận đủ để điều tra; log đơn thuần không mặc nhiên chứng minh chống chối bỏ tuyệt đối.
- **Privacy (quyền riêng tư):** giới hạn thu thập, suy luận, liên kết, lưu trữ và chia sẻ dữ liệu về cá nhân.

### Phân loại tài sản theo vòng đời

Một bản rõ có thể đi qua `client -> HTTPS -> JVM heap -> DB -> backup -> log/monitoring`. Mã hóa bản ghi trong DB chưa đủ nếu endpoint cho người sai quyền lấy bản rõ, khóa nằm cùng nơi với dữ liệu dưới cùng quyền truy cập, hoặc debug log in ra request/response nhạy cảm. Đừng bỏ qua dữ liệu trong bộ nhớ, tệp tạm, snapshot, bản sao môi trường test và thông điệp lỗi.

Với khóa bí mật, hãy ghi riêng: **ai có thể yêu cầu mã hóa/giải mã**, ai có thể lấy/export khóa, chính sách IAM, vị trí tạo/lưu khóa, cơ chế luân chuyển/thu hồi, các bản khóa cũ cần để đọc dữ liệu cũ, cùng kế hoạch khi khóa bị lộ hoặc bị mất. Quyền gọi `Decrypt` trên KMS là một tài sản quyền lực dù byte khóa không bao giờ rời KMS.

## 4. Ranh giới tin cậy là gì?

**Ranh giới tin cậy (*trust boundary*)** là nơi dữ liệu hoặc lệnh đi giữa các vùng có chủ sở hữu, cơ chế xác thực, mức đặc quyền hay giả định tin cậy khác nhau. Ranh giới thường trùng với kết nối mạng nhưng **không nhất thiết**: hai thành phần cùng máy, cùng VPC hoặc cùng JVM vẫn có thể có quyền và nguồn dữ liệu khác nhau.

Ví dụ hệ thống Java cho phép người dùng tải tài liệu đã mã hóa:

```text
[Trình duyệt / người dùng]    (không tin đầu vào)
            |
            | B1: HTTPS + phiên/token
            v
[Gateway / API Java]          (xác thực danh tính, áp dụng quyền)
       |                 \
       | B2: SQL/TLS      \ B3: KMS API/TLS, IAM role
       v                   v
[DB: metadata/ACL]      [KMS: quản lý và sử dụng khóa]
       |
       | tham chiếu đối tượng
       v
[Object storage: bản mã]      (quyền và chính sách truy cập riêng)
```

Lưu ý: hình trên là **sơ đồ logic đơn giản**, không ngụ ý DB trực tiếp truy cập object storage; triển khai thực tế thường có luồng API Java -> object storage riêng, cũng cần vẽ thành một ranh giới. Vị trí kết thúc TLS tại gateway/load balancer phải được ghi rõ: nếu gateway giải mã TLS, chặng từ gateway đến backend là một luồng khác cần đánh giá.

Tại **mỗi lần vượt ranh giới**, đặt sáu câu hỏi:

1. Ai gửi và ai nhận? Có xác minh đúng danh tính dịch vụ/người dùng không?
2. Những byte nào là dữ liệu **không đáng tin** (ID, header, JWT, nội dung tệp, sự kiện, thông tin tenant)?
3. Bên nhận có thực hiện thêm quyền cao hơn, truy vấn DB, gọi KMS hoặc ghi tệp dựa trên dữ liệu đó không?
4. Kiểm tra đầu vào, **ủy quyền**, giới hạn kích thước/tốc độ, chống phát lại và xác minh toàn vẹn đặt ở đâu?
5. Lộ, sửa, mất hoặc gửi lại dữ liệu qua ranh giới sẽ ảnh hưởng tài sản nào?
6. Khi kiểm soát thất bại, có dấu hiệu kiểm toán và cách ngăn lan truyền thiệt hại không?

Một số ranh giới hay bị bỏ sót:

- **Client -> backend:** client kiểm soát ID, body, query, file upload; kể cả người dùng đã đăng nhập, toàn bộ trường do họ gửi vẫn không đáng tin.
- **Gateway -> service:** gateway xác thực không mặc nhiên đồng nghĩa backend đã phân quyền; backend cần hợp đồng xác thực có thể kiểm chứng, hạn chế tin header danh tính từ Internet.
- **Service -> DB/cache/object storage:** tài khoản dịch vụ có thể rộng quyền hơn người dùng cuối; cần tenant isolation, truy vấn ràng buộc quyền, least privilege và bảo vệ kết nối.
- **Service -> KMS/HSM:** việc có quyền gọi giải mã có thể biến server bị chiếm thành “cỗ máy giải mã”; giới hạn quyền theo key, điều kiện, mục đích và theo dõi lạm dụng.
- **Ứng dụng -> webhook/partner/queue:** dữ liệu hoặc sự kiện của bên ngoài phải kiểm tra nguồn, chữ ký/MAC khi được thiết kế, thời gian, nonce/idempotency và schema; xác thực kết nối chỉ giải quyết một phần.
- **Build/CI -> production secrets:** artifact, dependency và người có quyền triển khai có thể thay đổi chương trình chạy với đặc quyền sản xuất.

**Nguyên tắc:** “nội bộ”, “chạy trong Kubernetes”, “có HTTPS” hoặc “đã đăng nhập” không phải bảo đảm cho mọi hành động. Tin cậy phải có *phạm vi*, *điều kiện xác minh* và *thời hạn* cụ thể.

## 5. Quy trình xây dựng mô hình đe dọa

### Bước 1 — Chốt phạm vi và các giả định

Ghi tên chức năng, luồng nghiệp vụ, các actor (người dùng, admin, service, bên thứ ba), môi trường, điểm vào/ra, loại dữ liệu và điều gì **nằm ngoài** phạm vi. Ví dụ: “Xét `GET /api/documents/{id}` và thao tác giải mã phục vụ tải về; không phân tích quy trình thanh toán”. Ghi giả định kiểm chứng được, như “gateway xác minh JWT và backend chỉ nhận kết nối từ gateway”; không xem giả định là sự thật khi chưa kiểm thử.

### Bước 2 — Kiểm kê tài sản và phân quyền

Dùng bảng ở mục 3 để mô tả tác động nếu vi phạm từng thuộc tính. Tách **chủ sở hữu dữ liệu**, **người được phép xem**, **tài khoản máy thực thi** và **người quản trị khóa**; các danh tính này không đồng nhất.

### Bước 3 — Vẽ luồng dữ liệu (DFD) và đánh dấu ranh giới

DFD tối thiểu cần có **external entities**, **processes**, **data stores**, **data flows** và **trust boundaries**. Trên các mũi tên, ghi dữ liệu chuyển đi, giao thức, cơ chế xác thực, điểm kết thúc mã hóa và nơi ra quyết định quyền. Vẽ riêng đường đi ghi, đọc, xóa, sao lưu và luân chuyển khóa nếu mức rủi ro khác nhau.

### Bước 4 — Tìm các kịch bản đe dọa

Duyệt từng tài sản và mỗi điểm vượt ranh giới. Kết hợp STRIDE (mục 6) với các câu hỏi: “Nếu client thay ID?”, “Nếu token bị lấy cắp?”, “Nếu service role bị chiếm?”, “Nếu dữ liệu/ciphertext bị tráo?”, “Nếu retry cùng sự kiện nhiều lần?”, “Nếu KMS không phản hồi?”. Nêu **tiền điều kiện -> hành động -> kiểm soát bị vượt qua -> hậu quả**, tránh chỉ ghi “có nguy cơ hacker”.

### Bước 5 — Ưu tiên và gắn kiểm soát

Ước lượng **khả năng xảy ra** và **mức tác động** theo bối cảnh thực tế; cân nhắc mức phơi lộ, quyền cần có, độ khó khai thác và kiểm soát đang tồn tại. Ví dụ thang nội bộ 1–5: khả năng 4 và tác động 5 cho điểm 20; đây chỉ là phép sắp xếp thảo luận, **không phải xác suất định lượng hay chuẩn ngành**. Nêu chủ sở hữu rủi ro, người thực thi, thời hạn và trạng thái (giảm thiểu/chuyển giao/tránh/chấp nhận có lý do).

### Bước 6 — Kiểm chứng, lưu vết và cập nhật

Với mỗi kiểm soát, viết kiểm thử hoặc tiêu chí quan sát: request khác tenant bị từ chối, token giả bị loại, IAM không cho key trái phép, log không chứa bearer token, hạn mức không làm cạn tài nguyên. Lưu artifact mô hình, quyết định và rủi ro còn lại cùng version thiết kế. Cập nhật khi thêm endpoint, nhà cung cấp, cơ chế xác thực, vùng lưu trữ hoặc thay đổi luồng khóa.

## 6. STRIDE: gợi ý để không bỏ sót lớp đe dọa

STRIDE có sáu nhóm. Áp chúng lên thành phần và đường dữ liệu **cụ thể**; một thành phần có thể gặp nhiều nhóm, và một threat có thể liên quan nhiều nhóm.

| Nhóm | Câu hỏi kiểm tra | Kịch bản ở API tài liệu | Kiểm soát điển hình |
| --- | --- | --- | --- |
| **S — Spoofing** (mạo danh) | Ai có thể giả làm người/dịch vụ khác? | Kẻ xấu gửi token giả hoặc giả header `X-User` | Xác minh chữ ký token, issuer, audience, thời hạn; bảo vệ mTLS/identity giữa service; bỏ header không đáng tin |
| **T — Tampering** (sửa đổi) | Ai thay dữ liệu/lệnh ngoài ý muốn? | Bản mã/metadata bị sửa, tenant ID bị tráo | Kiểm tra ủy quyền và tính toàn vẹn; AEAD khi mã hóa; kiểm soát ghi DB/object |
| **R — Repudiation** (phủ nhận hành động) | Có truy vết ai đã làm gì không? | Người có quyền tải/xóa tài liệu phủ nhận hành động | Audit theo actor đã xác minh, resource ID, thời điểm; chống sửa log; hạn chế dữ liệu nhạy cảm trong log |
| **I — Information Disclosure** (tiết lộ) | Ai đọc được thông tin không được phép? | BOLA khiến tải tài liệu của tenant khác; token lọt vào log | Phân quyền cấp đối tượng, tenant isolation, TLS, mã hóa phù hợp, redaction log |
| **D — Denial of Service** (từ chối dịch vụ) | Ai có thể làm hệ thống cạn tài nguyên? | Spam request giải mã làm hết quota KMS/CPU | Rate limit, quota, timeout, backpressure, kiểm soát tài nguyên, circuit breaker theo nhu cầu |
| **E — Elevation of Privilege** (leo thang quyền) | Người dùng có thể hành động ngoài vai trò? | Dùng input `role=admin` hoặc service account quá rộng quyền | Quyền từ nguồn đáng tin, kiểm tra server-side cho từng action, IAM tối thiểu, phân tách nhiệm vụ |

STRIDE là **khung gợi ý**, không đảm bảo phát hiện hết tấn công nghiệp vụ, riêng tư hay chuỗi cung ứng. Với hành vi lạm dụng quy trình, thêm *abuse case*; với đường tấn công nhiều bước, dùng *attack tree*; với yêu cầu về quyền riêng tư, có thể bổ sung LINDDUN. Đừng biến việc điền đủ sáu hàng thành mục tiêu thay cho tìm ra rủi ro có thật.

## 7. Ví dụ xuyên suốt: tải tài liệu đã mã hóa theo tenant

**Bài toán:** Dịch vụ Java lưu tệp dưới dạng bản mã trong object storage; DB lưu metadata gồm `documentId`, `tenantId`, `ownerId` và tham chiếu đối tượng; KMS bảo vệ khóa. Người dùng gửi `GET /api/documents/{id}` để tải tệp. Người dùng hợp lệ **chỉ được xem tài liệu được cấp quyền trong tenant của mình**.

### 7.1 Luồng hợp lệ

1. Client gọi API qua HTTPS với thông tin phiên/token.
2. Thành phần xác thực kiểm tra bằng chứng danh tính; Java API nhận **principal đã xác minh**. Nếu JWT được dùng, phải kiểm tra chữ ký, thuật toán được cho phép, issuer, audience, thời hạn và các claim cần thiết theo giao thức; giải mã chuỗi JWT ra JSON không có nghĩa là đã xác thực.
3. Server nhận `id` từ URL **như dữ liệu do client kiểm soát**, lấy metadata tài liệu từ kho đáng tin.
4. Policy kiểm tra cả **tenant**, **quyền trên tài liệu** và **hành động đọc**. Không dùng `ownerId` hoặc `tenantId` do client tự khai làm quyết định quyền.
5. Chỉ khi policy cho phép, service mới yêu cầu lấy bản mã/giải mã qua KMS theo đặc quyền tối thiểu rồi trả nội dung. Response và log tuân theo chính sách bảo vệ dữ liệu.

### 7.2 Kịch bản lạm dụng đáng ưu tiên

| ID | Ranh giới và kịch bản | Tài sản / tác hại | Kiểm soát cần có | Cách xác minh |
| --- | --- | --- | --- | --- |
| T1 | B1: người đã đăng nhập đổi `id=doc-a` thành `id=doc-b` của người/tenant khác (**BOLA**) | Bí mật của tài liệu bị lộ | Policy theo từng đối tượng, tenant và hành động ở backend; mặc định từ chối | Kiểm thử cùng tenant khác owner, khác tenant, tài liệu không tồn tại; không trả bản rõ |
| T2 | B1: dùng token giả, hết hạn hoặc sai audience | Mạo danh, truy cập trái phép | Xác minh token đúng chuẩn, không tin header tùy ý từ client | Gửi token thiếu/sai chữ ký, sai issuer/audience, hết hạn và xác nhận từ chối |
| T3 | B2/B3: tài khoản dịch vụ hoặc IAM role bị chiếm để gọi giải mã rộng khắp | Lộ hàng loạt bản rõ dù storage đã mã hóa | IAM/KMS policy tối thiểu, tách quyền, giới hạn phạm vi key, audit và cảnh báo | Thử một role không được cấp phép gọi decrypt; kiểm tra audit KMS |
| T4 | API -> storage: sửa bản mã hoặc tráo metadata tenant/đối tượng | Trả dữ liệu sai, mất toàn vẹn | Kiểm soát ghi, ràng buộc bản mã với ngữ cảnh, dùng mã hóa xác thực (AEAD) khi thiết kế yêu cầu | Thử sửa bit bản mã/AAD hoặc thay liên kết đối tượng; giải mã phải thất bại hoặc bị chặn |
| T5 | B1/B3: spam tải/giải mã, file cực lớn | Gián đoạn API hoặc hết quota KMS | Rate limit, giới hạn kích thước, timeout, quota, backpressure | Load test có giới hạn, đo lỗi và ảnh hưởng lên người dùng hợp lệ |
| T6 | API -> log/observability: log token, plaintext, URL chứa secret | Rò rỉ dữ liệu qua hệ thống phụ trợ | Redaction, không ghi credential/bản rõ, phân quyền và retention log | Quét log ở tình huống thành công/lỗi; không thấy bearer token hay plaintext |

**Phân tích T1 theo chuỗi nguyên nhân:**

- **Tiền điều kiện:** Alice có tài khoản hợp lệ và biết/đoán được ID của tài liệu Bob. ID là tham số đầu vào, dù là UUID ngẫu nhiên vẫn có thể bị lộ qua log, link hoặc API khác.
- **Điểm vượt ranh giới:** client gửi `id`; API dùng ID đó để đọc metadata và giải mã bằng quyền của server.
- **Lỗi thiết kế có thể có:** API kiểm tra “đã login” rồi gọi `decrypt(documentId)`, không kiểm tra Alice có quyền trên tài liệu này.
- **Hậu quả:** tài liệu của Bob bị tiết lộ. **TLS không ngăn được** vì request được gửi qua kênh hợp lệ; **mã hóa storage không ngăn được** vì chính server có quyền giải mã.
- **Sửa đúng chỗ:** backend ra quyết định quyền theo principal đã xác minh và metadata/policy tin cậy **trước mọi thao tác lấy bản rõ**; deny by default; kiểm thử chéo người dùng và tenant.

Đây là nhóm **Broken Object Level Authorization (API1:2023)** trong OWASP API Security Top 10. Đổi ID tuần tự sang UUID hoặc chỉ che nút tải trên UI không giải quyết được gốc rễ.

### 7.3 Biên giới mật mã và quản lý khóa

Mật mã chỉ có ý nghĩa khi trả lời chính xác **bảo vệ tài sản nào trước tác nhân nào**:

- **TLS** bảo vệ kênh truyền đến điểm kết thúc TLS và xác thực endpoint theo cấu hình; TLS không xác định người dùng có quyền đọc tài liệu hay không. Khi TLS kết thúc tại proxy, vẽ lại đường đi proxy -> service.
- **Mã hóa dữ liệu lưu trữ** hỗ trợ bảo mật bản rõ nếu storage/bản sao lưu bị đọc trái phép. Nếu tiến trình có quyền giải mã bị chiếm, mối đe dọa chuyển sang quyền sử dụng khóa và đường xuất bản rõ.
- **Mã hóa xác thực** như AES-GCM có thể phát hiện bản mã/AAD bị sửa khi dùng đúng; với cùng một khóa, không tái sử dụng nonce/IV và cần lưu/đưa đúng AAD khi giải mã. AEAD không tự làm kiểm tra ủy quyền.
- **Chữ ký số/MAC** hỗ trợ xác minh nguồn và tính toàn vẹn theo giả định khóa/chứng chỉ được quản lý đúng; chúng không tự mã hóa nội dung để giữ bí mật.
- **Hash mật khẩu** khác mã hóa đảo ngược: dùng cơ chế password hashing có salt và cost phù hợp (ví dụ Argon2id theo chính sách) thay vì lưu mật khẩu bằng AES hay SHA-256 đơn thuần.
- **Khóa và secret** cần lưu giữ, phân quyền, rotation và audit riêng. Tránh nhúng khóa trong mã nguồn, image build, stack trace hoặc log; hạn chế quyền decrypt hơn cả quyền đọc bản mã.

Một kiểm soát có thể giảm một loại đe dọa nhưng để nguyên loại khác. Mô hình đe dọa tốt ghi rõ **điều kiện kiểm soát đúng**, vị trí kiểm chứng và rủi ro còn lại.

## 8. Ví dụ Java 17: kiểm tra quyền trước khi chạm bản rõ

Đoạn sau chỉ minh họa **quy tắc phân quyền đơn giản theo chủ sở hữu và tenant**. Nó không kết nối mạng/DB/KMS, không xác thực token và không mã hóa thật. Trong ứng dụng thực tế, `Principal` phải được tạo từ **ngữ cảnh xác thực đã kiểm chứng**, còn `Document` phải đến từ nguồn metadata tin cậy.

Lưu thành `TrustBoundaryDemo.java`:

```java
import java.util.Objects;

public class TrustBoundaryDemo {
    record Principal(String userId, String tenantId) {}
    record Document(String id, String ownerId, String tenantId) {}

    static boolean canRead(Principal actor, Document document) {
        if (actor == null || document == null
                || actor.userId() == null || actor.userId().isBlank()
                || actor.tenantId() == null || actor.tenantId().isBlank()) {
            return false;
        }

        return Objects.equals(actor.tenantId(), document.tenantId())
                && Objects.equals(actor.userId(), document.ownerId());
    }

    public static void main(String[] args) {
        Principal alice = new Principal("alice", "tenant-a");
        System.out.println(canRead(alice,
                new Document("doc-1", "alice", "tenant-a")));
        System.out.println(canRead(alice,
                new Document("doc-2", "bob", "tenant-a")));
        System.out.println(canRead(alice,
                new Document("doc-3", "alice", "tenant-b")));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
```

Kết quả stdout chính xác:

```text
true
false
false
```

Hàng đầu cho phép Alice đọc tài liệu của mình. Hàng thứ hai từ chối tài liệu của Bob trong cùng tenant; hàng thứ ba từ chối tài liệu có cùng owner ID nhưng thuộc tenant khác. **Chỉ so sánh user ID mà bỏ qua tenant là thiếu**, cũng như chỉ so sánh tenant mà không kiểm tra quyền trên từng tài liệu.

Trong hệ thống thật, thay `canRead` bằng policy phù hợp (owner, chia sẻ có kiểm soát, vai trò, điều kiện thời gian, quyền hành động). Hàm nên trả **deny** khi metadata thiếu hoặc danh tính chưa xác minh. Thứ tự quan trọng là: **xác thực -> nạp thông tin đáng tin -> phân quyền tài nguyên -> truy xuất/giải mã -> trả dữ liệu**. Cách trả 403/404 và thông tin log phải theo chính sách tránh lộ sự tồn tại tài nguyên, không biến thông báo lỗi thành kênh rò rỉ.

### Chuyển mô hình thành phép kiểm thử

Đối với API thật, ít nhất phải có các ca:

1. User được cấp quyền, đúng tenant, đúng tài liệu: được tải và nội dung chính xác.
2. User khác cùng tenant nhưng chưa được cấp quyền: bị từ chối; service không gọi KMS/decrypt.
3. User có cùng tên/ID trong tenant khác: bị từ chối; truy vấn metadata luôn ràng buộc tenant theo chính sách.
4. Token sai chữ ký, sai audience, hết hạn, hoặc không có token: thất bại trước khi truy xuất nội dung.
5. Request chứa `ownerId`, `tenantId` hoặc `role` giả trong body/header: không thay đổi quyết định quyền.
6. Role dịch vụ chỉ được phép dùng một khóa: yêu cầu giải mã bằng khóa ngoài phạm vi bị từ chối, có audit.
7. Bản mã/AAD bị can thiệp, log lỗi, retry hoặc lượng request vượt quota: xử lý an toàn, không trả bản rõ sai hay rò secret.

Cần có cả kiểm thử unit policy, integration cho boundary API/DB/KMS (môi trường kiểm thử an toàn), và kiểm tra cấu hình IAM thực tế. Test chạy qua không thay thế rà soát giả định và thay đổi kiến trúc.

## 9. Ghi nhận quyết định, mức ưu tiên và rủi ro còn lại

Một bản ghi threat tối thiểu nên có:

| Trường | Nội dung mẫu |
| --- | --- |
| `ID` / phạm vi | `T1` — `GET /api/documents/{id}` |
| Tài sản, mục tiêu | Bản rõ hợp đồng; chỉ owner/được chia sẻ trong đúng tenant mới đọc |
| Tác nhân và tiền điều kiện | User hợp lệ có thể gửi ID của tài liệu khác |
| Ranh giới/đường tấn công | Client -> Java API -> metadata -> KMS/decrypt |
| Hậu quả | Lộ nội dung tài liệu trái phép |
| Đánh giá trước kiểm soát | Khả năng 4/5 x tác động 5/5 = 20/25 (ví dụ nội bộ) |
| Kiểm soát và vị trí | Policy kiểm tra tenant, action và quyền object ở backend, trước decrypt |
| Bằng chứng | Test chéo tenant/user, audit request bị từ chối, không gọi KMS |
| Owner, trạng thái | Nhóm sở hữu API; đang triển khai/đã kiểm chứng; ngày đánh giá |
| Rủi ro còn lại | Token hợp lệ bị đánh cắp vẫn có thể truy cập tài liệu trong quyền được cấp; cân nhắc session control, MFA và phát hiện bất thường |

Không cộng trừ điểm một cách máy móc: các thang số không mô tả đầy đủ mức phơi lộ, tác động pháp lý, mục tiêu của attacker hoặc tương quan giữa nhiều đe dọa. Nếu rủi ro được chấp nhận, cần người chịu trách nhiệm, lý do, thời hạn xem xét lại và tiêu chí mở lại đánh giá.

**Khi nào cập nhật mô hình?** Khi thêm luồng dữ liệu (webhook, export, analytics), dữ liệu nhạy cảm, tenant mới, thay đổi quyền IAM, phương thức xác thực, thư viện mật mã, vị trí TLS termination, logic chia sẻ đối tượng hoặc công đoạn backup/restore. Mô hình là tài liệu sống gắn với thiết kế, code review và kiểm thử.

## 10. Các lỗi tư duy thường gặp

- **“Đã dùng HTTPS nên an toàn.”** HTTPS bảo vệ kênh đến điểm TLS termination; request của người có quyền thấp vẫn có thể làm lộ dữ liệu nếu thiếu authorization.
- **“Đã mã hóa DB, kể cả admin/service bị chiếm cũng không đọc được.”** Phải xem ai có quyền decrypt và bản rõ xuất hiện ở đâu. Mã hóa không thay thế kiểm soát truy cập và phân tách quyền.
- **“Đã xác thực JWT thì mọi object ID do người dùng gửi đều đáng tin.”** Token xác thực người gọi; mỗi object/action cần kiểm tra quyền độc lập.
- **“UUID đủ ngẫu nhiên nên không cần policy.”** Khó đoán ID không phải ranh giới bảo vệ: ID có thể lộ hoặc được chia sẻ ngoài ý muốn.
- **“Trong cùng private network thì không có ranh giới.”** Các service/role có đặc quyền và đường dữ liệu khác nhau; tài khoản bị chiếm vẫn gây hại.
- **“Có đủ sáu ô STRIDE là xong.”** STRIDE chỉ là checklist tìm ý tưởng; cần kịch bản cụ thể, tác động, owner, kiểm soát và kiểm chứng.
- **“Threat = bug đã xảy ra.”** Threat là điều có thể sai; cần tách giả định, điểm yếu đã xác minh và rủi ro chưa được xử lý.
- **“Log càng nhiều càng tốt.”** Log có thể biến thành tài sản nhạy cảm, đặc biệt nếu chứa bản rõ, token, khóa hoặc dữ liệu cá nhân.
- **“Mã hóa xác thực tự đảm bảo dữ liệu thuộc đúng user.”** AEAD bảo vệ toàn vẹn trong ngữ cảnh khóa/AAD được chọn; việc user có quyền với object vẫn do authorization quyết định.

## 11. Bài luyện tập áp dụng

Một dịch vụ Spring/Java nhận webhook từ đối tác, ghi sự kiện vào queue, worker cập nhật trạng thái thanh toán trong DB, và API cho người dùng xem lịch sử. Hãy tự tạo một trang threat model:

1. Liệt kê ít nhất sáu tài sản: trạng thái/tham chiếu thanh toán, danh tính người dùng, khóa bí mật xác thực webhook, message ID, quyền cập nhật DB, audit log.
2. Vẽ ranh giới **đối tác -> webhook**, **API -> queue**, **worker -> DB**, **người dùng -> API đọc**, và đánh dấu ai xác thực ai.
3. Viết ít nhất năm kịch bản: webhook giả, phát lại webhook hợp lệ, sửa tenant/order ID trong payload, tiêu thụ queue lặp gây cập nhật sai, người dùng đọc giao dịch của người khác, hoặc queue bị quá tải.
4. Với mỗi kịch bản, ghi tiền điều kiện, tài sản bị ảnh hưởng, kiểm soát dự kiến và một test chứng minh. Ví dụ chống replay có thể cần xác thực nguồn, thời gian có giới hạn **và** idempotency theo event ID ở phía tiêu thụ; chỉ có HTTPS chưa đủ.
5. Ghi một giả định còn phải xác minh (ví dụ “đối tác có cơ chế ký webhook”) và một rủi ro còn lại sau kiểm soát.

**Tiêu chí hoàn thành:** người khác đọc artifact có thể tìm đúng điểm vượt ranh giới, thấy rõ đường từ dữ liệu không tin cậy tới quyền cao, biết tại đâu kiểm tra nó và cách xác nhận kết quả — không cần suy diễn “service này chắc đã an toàn”.

## Tài liệu tham khảo

- [OWASP — Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html): quy trình xây dựng mô hình, DFD, STRIDE, kiểm soát và review.
- [OWASP — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): ví dụ lỗi phân quyền từng đối tượng.
- [OWASP — Threat Modeling trong DevSecOps Guideline](https://owasp.github.io/DevSecOpsGuideline/2-Process/2-1-Design/2-1-1-Threat-modeling/): ví dụ DFD, ranh giới tin cậy và STRIDE.
