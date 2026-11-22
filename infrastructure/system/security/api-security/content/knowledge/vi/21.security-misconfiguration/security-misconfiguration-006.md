# Feature flag và environment config

Feature flag và environment config giúp đội phát triển bật/tắt chức năng, triển khai thay đổi theo từng nhóm người dùng và cấu hình ứng dụng cho development, staging hoặc production. Nếu quản lý thiếu chặt chẽ, chúng cũng có thể trở thành nguồn gây lỗi bảo mật API: endpoint quản trị vô tình được mở, xác thực bị tắt ở một môi trường, CORS cho phép origin không tin cậy, debug hoặc actuator lộ ra Internet, hay một tính năng tài chính được bật cho sai tenant.

Trong bảo mật API, cấu hình quyết định nhiều thuộc tính quan trọng: endpoint nào được phục vụ, hệ thống nào được gọi, credential nào được dùng, giới hạn tài nguyên bao nhiêu, lỗi được hiển thị thế nào và những bước nghiệp vụ nào được phép chạy. Feature flag có thể thay đổi hành vi đó ngay khi ứng dụng đang hoạt động. Vì vậy, cả flag lẫn cấu hình môi trường cần được xem là một phần của security control plane, có chủ sở hữu, quyền thay đổi, kiểm tra, audit và quy trình khôi phục.

Một nguyên tắc cần giữ xuyên suốt: feature flag quyết định tính năng có sẵn trong một phạm vi triển khai; authorization quyết định principal cụ thể có được thực hiện action trên object cụ thể hay không. Bật tính năng không cấp quyền cho người dùng, và tắt tính năng không thay thế quy trình thu hồi quyền.

## 1. Phân biệt feature flag và environment config

Hai khái niệm thường được dùng cùng nhau nhưng có mục đích khác nhau:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Feature flag | Bật/tắt hoặc chọn biến thể hành vi của một tính năng | Bật API export mới cho 5% tenant |
| Release flag | Điều khiển quá trình phát hành một phiên bản chức năng | Chỉ bật luồng checkout mới ở staging trước |
| Operational flag | Cho phép vận hành dừng hoặc giới hạn một hoạt động | Tạm ngừng tạo export khi hệ thống lưu trữ quá tải |
| Experiment flag | Chọn biến thể để đo lường trải nghiệm | So sánh hai cách sắp xếp kết quả tìm kiếm |
| Environment config | Cung cấp giá trị cấu hình theo môi trường triển khai | Database endpoint, CORS origins, timeout |
| Security policy config | Xác định chính sách bảo mật có hiệu lực | Issuer/audience, giới hạn upload, allowlist outbound host |
| Secret | Cung cấp credential hoặc khóa bí mật | Database password, API key, signing key |

Feature flag thường thay đổi trong thời gian chạy và có thể nhắm đến một nhóm người dùng hoặc tenant. Environment config thường được xác định khi triển khai hoặc nạp lại theo một quy trình có kiểm soát. Secret là loại dữ liệu nhạy cảm riêng, cần kho lưu trữ và quyền truy cập chặt chẽ; không nên coi secret như một flag hoặc giá trị cấu hình thông thường.

### 1.1. Ví dụ trong API

Một dịch vụ có thể có các cấu hình:

- Flag new-invoice-export quyết định tenant nào được dùng luồng export mới.
- Cấu hình MAX_EXPORT_ROWS giới hạn số dòng của một lần export trong môi trường.
- Security policy quy định endpoint export yêu cầu permission INVOICE_EXPORT.
- Secret lưu credential để ghi file vào object storage.

Bốn giá trị này có liên quan nhưng không thể thay thế nhau. Nếu flag export bật, server vẫn phải kiểm tra permission và phạm vi invoice. Nếu giới hạn export được đặt quá cao, một tenant có thể gây quá tải. Nếu secret bị lộ, kẻ tấn công có thể truy cập storage ngay cả khi flag đã tắt.

## 2. Feature flag không phải cơ chế authorization

Một lỗi thiết kế phổ biến là dùng flag để quyết định ai được truy cập API. Ví dụ, frontend chỉ hiển thị nút quản trị khi flag bật, còn server cho phép mọi request đến endpoint tương ứng. Người dùng có thể gọi trực tiếp endpoint mà không cần giao diện.

Feature flag chỉ nên quyết định chức năng có được triển khai hoặc cung cấp trong một phạm vi hay không. Mỗi request vẫn phải đi qua các lớp bảo vệ:

1. Xác thực principal và credential.
2. Kiểm tra function permission cho endpoint/action.
3. Kiểm tra object và tenant scope.
4. Kiểm tra field, trạng thái và điều kiện nghiệp vụ.
5. Kiểm tra feature có được bật cho deployment/tenant hay không.
6. Ghi audit và thực hiện side effect trong transaction phù hợp.

Thứ tự cụ thể có thể thay đổi theo kiến trúc, nhưng không được để việc bật flag bỏ qua các bước authorization.

### 2.1. Ma trận feature và quyền

| Feature | Flag bật | Authorization | Kết quả |
|---|---|---|---|
| Export invoice | Có | User có INVOICE_EXPORT, invoice thuộc phạm vi được phép | Cho phép theo quota và policy |
| Export invoice | Có | User không có permission | Từ chối |
| Export invoice | Tắt | User có permission | Tính năng chưa được cung cấp; không thực hiện export |
| Admin role editor | Có | Principal không có USER_ROLE_MANAGE | Từ chối |
| Admin role editor | Tắt | Principal có quyền quản trị | Tính năng bị tắt theo rollout/incident policy |

Flag có thể làm tính năng không khả dụng với cả người có quyền, ví dụ khi đang rollout hoặc xảy ra sự cố. Flag không thể biến principal không có quyền thành principal được phép.

### 2.2. Không tin flag hoặc role do client gửi

Không nhận các giá trị như isAdmin, featureEnabled, tenantTier, permissions hoặc environment từ request body/header để quyết định security policy. Client có thể sửa JavaScript, gọi API trực tiếp hoặc tạo request khác với giao diện chính thức.

Nếu ứng dụng cần gửi thông tin biến thể giao diện cho client, thông tin đó chỉ phục vụ hiển thị. Server phải tự đánh giá flag bằng cấu hình tin cậy và tenant/principal context đã xác thực. Không để header tùy ý như X-Feature-Enabled: true mở endpoint hoặc bỏ qua validation.

## 3. Thiết kế và quản lý vòng đời feature flag

Mỗi flag cần có định nghĩa rõ ràng trước khi được tạo:

- Tên ổn định, mô tả mục đích và loại flag.
- Owner chịu trách nhiệm nghiệp vụ và kỹ thuật.
- Phạm vi áp dụng: toàn hệ thống, môi trường, tenant, user hoặc client.
- Giá trị mặc định và hành vi khi flag provider không khả dụng.
- Điều kiện bật/tắt và tiêu chí rollout.
- Các dependency, endpoint và workflow bị ảnh hưởng.
- Ngày tạo, ngày xem xét lại và thời hạn loại bỏ.
- Quyền được phép tạo, thay đổi và phê duyệt flag.

Không tạo flag mà không có owner hoặc không biết nó điều khiển hành vi nào. Flag cũ có thể bị quên và trở thành nhánh code không còn được kiểm thử; số lượng flag tăng không kiểm soát cũng làm policy khó hiểu và dễ cấu hình sai.

### 3.1. Phân loại theo mức độ ảnh hưởng

| Loại flag | Ví dụ | Kiểm soát cần chú ý |
|---|---|---|
| UI/release | Hiển thị màn hình mới | Không dựa vào flag UI để bảo vệ endpoint |
| Business capability | Bật tính năng tạo invoice mới | Kiểm tra quyền, tenant, quota và workflow |
| Financial/security-sensitive | Bật refund tự động hoặc thay đổi payout | Phê duyệt, audit, giới hạn phạm vi và fail-safe |
| Operational kill switch | Dừng tạo job hoặc gọi provider | Xác định side effect đang chạy và cách phục hồi |
| Experiment | Chọn biến thể giao diện | Không dùng biến thể để thay đổi quyền hoặc dữ liệu bảo mật |

Flag điều khiển hành động tài chính, cấp quyền, dữ liệu nhạy cảm hoặc giao tiếp diện rộng cần được xem xét như thay đổi security policy. Cần có người phê duyệt, lịch sử thay đổi và cách kiểm tra trước khi áp dụng.

### 3.2. Tránh flag vĩnh viễn

Release flag nên có điều kiện kết thúc: sau khi rollout hoàn tất, xóa nhánh cũ và xóa flag. Operational flag có thể tồn tại lâu hơn nhưng cần owner, mô tả, runbook và kiểm tra định kỳ.

Một danh mục flag hữu ích gồm:

- Flag đang rollout.
- Flag đã bật toàn bộ và cần loại bỏ.
- Flag đang tắt do incident.
- Flag hết hạn nhưng chưa được dọn.
- Flag không còn được code tham chiếu.

Không xóa flag chỉ vì giá trị hiện tại là false; trước tiên xác định code path, dashboard, automation và runbook còn phụ thuộc hay không.

## 4. Đánh giá flag theo tenant và principal

Trong hệ thống multi-tenant, flag targeting phải dùng tenant context đã được xác minh. Một user có thể thuộc nhiều tenant, và một tenant có thể có nhiều role. Flag cần xác định rõ nhắm đến tenant, user, API client hay deployment.

Các nguyên tắc:

- Lấy tenant từ security context hoặc membership đã xác minh.
- Không tin tenant ID tùy ý trong query/body để chọn nhóm được bật flag.
- Tách cấu hình rollout theo tenant khỏi permission của từng user.
- Không dùng email, số điện thoại hoặc dữ liệu cá nhân làm targeting key nếu không cần.
- Có hành vi rõ khi tenant không có cấu hình riêng.
- Không để cache flag của tenant A được dùng cho tenant B.

### 4.1. Ví dụ targeting an toàn

Giả sử luồng invoice export mới chỉ được bật cho một nhóm tenant tham gia pilot. Server có thể:

1. Xác thực caller.
2. Xác định tenant từ membership đã kiểm tra.
3. Kiểm tra flag cho tenant đó.
4. Kiểm tra permission INVOICE_EXPORT.
5. Kiểm tra invoice thuộc tenant và user có quyền đọc.
6. Kiểm tra quota, row limit và concurrency.
7. Tạo export job với tenant context tin cậy.

Việc tenant nằm trong nhóm pilot chỉ cho phép tenant sử dụng phiên bản chức năng mới; không cấp quyền export cho mọi thành viên của tenant.

### 4.2. Cache và tính nhất quán

Flag thường được cache để giảm latency. Cần xác định:

- Cache key gồm những chiều nào: environment, tenant, flag và có thể user/client.
- TTL tối đa và cơ chế invalidation.
- Hành vi khi cấu hình đổi nhưng cache chưa cập nhật.
- Cách tránh dùng kết quả của tenant khác.
- Cách xử lý khi flag provider hoặc cache không khả dụng.

Với kill switch hoặc flag bảo vệ thao tác có tác động lớn, TTL quá dài có thể làm một instance tiếp tục cho phép action sau khi flag đã bị tắt. Cân nhắc push invalidation, polling ngắn, versioned config hoặc cơ chế kiểm tra trực tiếp ở thời điểm thực thi. Không giả định mọi instance nhận thay đổi cùng lúc.

## 5. Fail-safe và secure default cho flag

Không có một giá trị fallback đúng cho mọi flag. Hành vi khi flag service lỗi phải được quyết định theo tác động của tính năng.

| Loại flag | Fallback thường cân nhắc | Lý do |
|---|---|---|
| Tính năng mới chưa rollout | Tắt | Tránh vô tình mở tính năng chưa sẵn sàng |
| Action tài chính nhạy cảm | Tắt hoặc chuyển manual review | Tránh thực hiện side effect khi không xác định policy |
| Kiểm soát bảo vệ bắt buộc | Dùng policy an toàn đã đóng gói và xác minh | Không để lỗi flag provider làm tắt authentication/authorization |
| Tính năng đọc ít rủi ro | Có thể dùng giá trị cache gần nhất theo thời hạn | Duy trì khả năng phục vụ có giới hạn |
| Kill switch | Cần thiết kế đường vận hành độc lập và được kiểm soát | Tắt nhanh nhưng không phụ thuộc duy nhất vào dịch vụ đang lỗi |

Không dùng feature flag để bật/tắt authentication, authorization hoặc validation cốt lõi theo cách có thể vô tình mở quyền khi provider lỗi. Nếu cần chế độ khẩn cấp, phải định nghĩa rõ state, quyền thay đổi, audit và hành vi của từng instance.

### 5.1. Kill switch không phải rollback hoàn chỉnh

Kill switch có thể ngăn tạo operation mới, nhưng không tự hoàn tác side effect đã xảy ra. Ví dụ tắt flag refund tự động không thu hồi khoản refund đã gửi đến provider. Một kill switch tốt cần nêu rõ:

- Chặn request mới hay cả job đang chờ?
- Job đang chạy được hoàn tất, hủy hay chuyển sang review?
- Callback đến sau khi tắt flag được xử lý thế nào?
- Có cần đối soát operation đang pending không?
- Ai được bật lại và cần điều kiện phê duyệt nào?

Đối với workflow tài chính, không nên hủy mù quáng các bước reconciliation hoặc callback chỉ vì đã tắt tính năng khởi tạo mới.

## 6. Environment config và tách biệt môi trường

Development, test, staging và production có dữ liệu, credential, endpoint và mức truy cập khác nhau. Cấu hình cần ngăn một môi trường vô tình dùng tài nguyên hoặc quyền của môi trường khác.

| Thuộc tính | Development/Test | Staging | Production |
|---|---|---|---|
| Dữ liệu | Synthetic hoặc đã giả danh hóa | Dữ liệu thử nghiệm được kiểm soát | Dữ liệu thật theo policy |
| Credential | Credential riêng, quyền thấp | Credential riêng cho sandbox/pre-prod | Secret production, quyền tối thiểu |
| API provider | Mock/sandbox | Sandbox hoặc endpoint kiểm thử | Endpoint chính thức đã allowlist |
| Debug | Có thể bật trong môi trường cô lập | Hạn chế | Tắt hoặc chỉ truy cập nội bộ có kiểm soát |
| API docs | Nội bộ | Có kiểm soát | Không công khai ngoài chủ đích |
| CORS | Origin dev cụ thể | Origin staging cụ thể | Origin production đã phê duyệt |
| Rate limit | Phù hợp test | Gần với production | Theo tải và SLA |
| Logging | Debug có kiểm soát, không dùng secret thật | Cấu trúc gần production | Redaction, retention và access control |

Không sao chép nguyên cấu hình production sang máy developer hoặc CI. Không dùng dữ liệu production thật trong môi trường test nếu chưa có cơ chế giả danh hóa và phê duyệt phù hợp.

### 6.1. Không suy đoán môi trường từ request

Không cho client tự chọn environment bằng header, query hoặc body. Môi trường phải do deployment và cấu hình hạ tầng xác định. Nếu request gửi X-Environment: production, server không được chuyển sang credential hoặc endpoint production dựa trên giá trị đó.

Tương tự, không dùng hostname hoặc header không được xác minh để quyết định bật debug, bỏ TLS, thay đổi CORS hoặc chuyển sang database khác. Reverse proxy header chỉ đáng tin khi request đến từ proxy được cấu hình tin cậy và các header cũ đã được loại bỏ/ghi đè.

### 6.2. Cấu hình phải có kiểu và validation

Tránh đọc mọi giá trị cấu hình dưới dạng chuỗi rồi tự chuyển đổi ở nhiều nơi. Dùng cấu trúc có kiểu, kiểm tra range và fail startup khi cấu hình bắt buộc sai.

Ví dụ với Spring Boot:

~~~java
@ConfigurationProperties(prefix = "security.api")
@Validated
public record ApiSecurityProperties(
    @NotEmpty List<String> allowedOrigins,
    @NotEmpty List<String> allowedPartnerHosts,
    @Min(1) @Max(1000) int maxPageSize,
    @NotNull Duration requestTimeout,
    boolean exposeApiDocs
) {}
~~~

Các annotation chỉ là ví dụ. Cần bổ sung validator cho URL/scheme/host, kiểm tra giá trị trùng, kiểm tra timeout dương và quy tắc liên trường. Không để ứng dụng khởi động với giá trị rỗng hoặc không hợp lệ rồi âm thầm dùng default rộng quyền.

## 7. Cấu hình bảo mật API cần kiểm soát chặt

Một số cấu hình có ảnh hưởng trực tiếp đến ranh giới bảo mật:

| Nhóm cấu hình | Ví dụ sai | Hành vi an toàn cần hướng tới |
|---|---|---|
| Authentication | Cho phép anonymous trên endpoint cần đăng nhập | Mặc định yêu cầu xác thực; public route được khai báo rõ |
| Authorization | Bỏ qua method security hoặc bật quyền quá rộng | Permission rõ theo function và object policy |
| CORS | Cho phép mọi origin cùng credential | Allowlist origin cụ thể; chỉ bật credential khi cần |
| TLS/proxy | Tin forwarded header từ mọi nguồn | Chỉ tin proxy đã xác minh; cấu hình TLS đúng |
| Error handling | Trả stack trace và config | Error response ổn định, chi tiết nội bộ chỉ ở log kiểm soát |
| Debug/actuator | Public heap dump, env, metrics hoặc shutdown | Chỉ expose endpoint vận hành cần thiết trên network/identity được bảo vệ |
| API docs | Swagger UI hoặc schema quản trị công khai ngoài chủ đích | Giới hạn môi trường, mạng và quyền truy cập |
| Rate limit | Không giới hạn hoặc chỉ giới hạn theo IP | Giới hạn theo principal/tenant/client/action và global capacity |
| Upload/body | Không có byte limit hoặc parser limit | Giới hạn kích thước, thời gian, nesting và số phần tử |
| Outbound integration | URL bất kỳ hoặc redirect tùy ý | Host/scheme allowlist, timeout và response limits |
| Cookie/session | Cookie thiếu Secure/HttpOnly/SameSite phù hợp | Cấu hình theo loại client và threat model |
| Logging | Ghi token hoặc payload nhạy cảm | Redaction, access control và retention |

### 7.1. CORS là cấu hình, không phải authorization

CORS kiểm soát việc browser cho phép JavaScript từ origin nào đọc response. Nó không ngăn mọi client khác gọi API và không thay thế authentication hoặc authorization. Không dùng CORS như hàng rào bảo vệ endpoint admin.

Trong production, khai báo origin chính xác theo scheme, host và port. Không phản chiếu Origin tùy ý, và không kết hợp wildcard origin với credential. Kiểm tra cả preflight method/header và cấu hình credential theo đúng nhu cầu.

### 7.2. Debug, actuator và API documentation

Debug endpoint, environment dump, heap dump, metrics và actuator có thể tiết lộ biến môi trường, đường dẫn nội bộ, trạng thái dependency hoặc thông tin vận hành. Chỉ expose endpoint cần thiết, giới hạn mạng và xác thực/authorization riêng.

API documentation cũng có thể tiết lộ endpoint nội bộ, schema nhạy cảm và operation quản trị. Không dựa vào việc URL khó đoán. Nếu docs cần có trong production, hãy giới hạn đối tượng truy cập và không công bố secret/example chứa dữ liệu thật.

### 7.3. Proxy và forwarded headers

Ứng dụng sau reverse proxy có thể dùng X-Forwarded-For, X-Forwarded-Proto hoặc Forwarded để xác định client IP và scheme. Nếu tin các header này từ request Internet trực tiếp, attacker có thể giả IP, vượt rate limit hoặc tạo URL callback sai.

Chỉ cấu hình trusted proxy ranges/instances; proxy phải ghi đè header do client gửi. Kiểm thử đường đi trực tiếp đến application port nếu kiến trúc yêu cầu mọi traffic phải qua gateway.

## 8. Quản lý nguồn cấu hình và thay đổi runtime

Cấu hình có thể đến từ file, environment variable, secret manager, config server, database hoặc feature flag platform. Cần xác định thứ tự ưu tiên và nguồn nào là authoritative.

Nguyên tắc:

- Chỉ cho phép nguồn cấu hình được phê duyệt.
- Xác thực và phân quyền truy cập config server/secret manager.
- Dùng TLS và workload identity cho kết nối giữa ứng dụng và control plane.
- Validate cấu hình trước khi áp dụng.
- Không để request của người dùng ghi trực tiếp vào runtime config.
- Gắn version, timestamp, actor và lý do cho thay đổi.
- Giữ khả năng rollback về một version đã xác minh.
- Không cho phép giá trị cấu hình chứa biểu thức được thực thi tùy ý.

### 8.1. Cấu hình bất biến và cấu hình runtime

Một số giá trị nên chỉ thay đổi khi triển khai, như listen port, trust store hoặc database endpoint. Một số giá trị có thể thay đổi runtime, như rollout percentage hoặc kill switch. Phân loại rõ giúp giảm số đường thay đổi và tránh ứng dụng nạp một phần cấu hình mới trong khi các phần khác vẫn cũ.

Nếu cần reload runtime, hãy:

1. Nhận bản cấu hình có version.
2. Xác thực nguồn và quyền thay đổi.
3. Validate toàn bộ cấu hình như một đơn vị.
4. Kiểm tra tương thích với phiên bản ứng dụng.
5. Áp dụng nguyên tử hoặc chuyển sang version mới hoàn chỉnh.
6. Ghi audit và metric kết quả.
7. Rollback nếu health check hoặc invariant không đạt.

Không cập nhật rời rạc các field security quan trọng theo thứ tự có thể tạo trạng thái trung gian không an toàn.

### 8.2. Phát hiện config drift

Config drift xảy ra khi các instance cùng môi trường chạy với giá trị khác nhau ngoài dự kiến. Một instance có thể bật debug, dùng CORS rộng hoặc giới hạn rate khác các instance còn lại.

Cần theo dõi:

- Config version và hash đã áp dụng trên từng instance.
- Flag version và thời điểm cập nhật.
- Instance chưa nhận được thay đổi hoặc reload thất bại.
- Giá trị thực tế khác desired state.
- Thay đổi thủ công ngoài pipeline.
- Secret sắp hết hạn hoặc chưa được xoay vòng.

Không đưa giá trị secret vào dashboard drift. Có thể so sánh version, fingerprint an toàn hoặc trạng thái rotation mà không hiển thị nội dung bí mật.

## 9. Secret không phải feature flag

Không lưu password, API key, private key, signing key hoặc token trong file feature flag, flag targeting rule, mã nguồn hay biến cấu hình công khai. Feature flag platform thường có nhiều người được quyền xem và thay đổi hơn secret manager.

Secret cần:

- Lưu trong secret manager hoặc cơ chế tương đương.
- Quyền truy cập theo workload identity và least privilege.
- Tách secret theo môi trường, service và provider.
- Rotation, revoke và theo dõi expiry.
- Không in ra log hoặc error message.
- Hạn chế thời gian tồn tại trong memory và phạm vi process có thể truy cập.
- Có quy trình xử lý khi secret bị lộ.

Environment variable có thể là cách truyền secret vào process trong một số nền tảng, nhưng cần đánh giá khả năng bị lộ qua process inspection, crash dump, diagnostic endpoint và log. Ưu tiên tích hợp secret manager theo cơ chế của nền tảng; không giả định env var tự động an toàn.

## 10. Rollout feature flag an toàn

Rollout theo tỷ lệ giúp phát hiện lỗi trước khi bật cho toàn bộ người dùng. Tuy nhiên, rollout cần được thiết kế sao cho không tạo khác biệt bảo mật giữa các nhóm hoặc phá vỡ dữ liệu khi chuyển qua lại giữa hai phiên bản.

Một quy trình tham khảo:

1. Tắt flag mặc định và triển khai code có cả hai đường xử lý.
2. Kiểm thử cả flag off và flag on trong CI.
3. Bật cho môi trường thử nghiệm với dữ liệu giả.
4. Bật cho nhóm nội bộ hoặc tenant pilot được phê duyệt.
5. Theo dõi lỗi, latency, denial, dữ liệu sai và side effect.
6. Tăng dần tỷ lệ theo tiêu chí định trước.
7. Dừng rollout nếu metric vượt ngưỡng.
8. Bật toàn bộ, loại bỏ flag tạm thời và code cũ sau khi ổn định.

### 10.1. Deterministic targeting

Nếu rollout theo phần trăm, nên dùng phép gán ổn định theo tenant/user key đã xác minh để một principal không đổi biến thể liên tục giữa các request. Không dùng giá trị do client tự chọn làm seed để tự đưa mình vào nhóm được bật.

Với hệ thống multi-tenant, cân nhắc rollout theo tenant để tránh hai user trong cùng tổ chức nhìn thấy hai hành vi có tác động dữ liệu khác nhau. Nếu cần rollout theo user, xác định rõ các workflow có chia sẻ trạng thái giữa user và tác động của việc dùng hai phiên bản đồng thời.

### 10.2. Kiểm tra tương thích dữ liệu

Nếu flag đổi schema, định dạng event hoặc quy tắc ghi dữ liệu, cần bảo đảm phiên bản cũ và mới có thể cùng tồn tại trong giai đoạn rollout. Không bật flag mới trước khi database migration, consumer và downstream service tương thích.

Với event/message, có thể dùng thay đổi additive trước, triển khai consumer hiểu cả hai schema, rồi mới bật producer mới. Rollback flag không nhất thiết rollback được dữ liệu đã ghi theo định dạng mới; cần kế hoạch migration/compensation.

## 11. Kiểm soát quyền thay đổi flag và config

Quyền thay đổi cấu hình có thể tương đương quyền thay đổi hành vi production. Một người có thể không có quyền gọi endpoint refund nhưng nếu được phép bật flag refund tự động hoặc thay đổi policy payout, họ có thể gián tiếp tạo tác động tương tự.

Phân quyền control plane cần tách biệt:

- Người tạo đề xuất thay đổi.
- Người review/approve thay đổi nhạy cảm.
- Service identity áp dụng cấu hình.
- Người vận hành được dùng kill switch trong tình huống khẩn cấp.
- Người audit chỉ đọc lịch sử và trạng thái.

Với thay đổi nhạy cảm, áp dụng separation of duties, MFA/step-up, approval và audit. Không dùng một tài khoản quản trị chung cho mọi operator.

### 11.1. Audit event cho flag/config

Ghi nhận tối thiểu:

- Actor hoặc service identity.
- Flag/config key và environment.
- Giá trị trước/sau ở dạng không chứa secret.
- Scope targeting: global, tenant hoặc nhóm được phê duyệt.
- Lý do, ticket/change reference và approval.
- Version, thời điểm và kết quả áp dụng.
- Instance/region đã nhận thay đổi nếu cần.

Không ghi giá trị bí mật. Nếu cấu hình chứa URL hoặc identifier nhạy cảm, áp dụng masking phù hợp.

## 12. Kiểm thử feature flag và environment config

Kiểm thử cần bao phủ cả trạng thái bật/tắt, lỗi provider, khác biệt môi trường và quyền của actor thay đổi cấu hình.

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Default | Flag chưa tồn tại hoặc chưa được cấu hình | Hành vi theo secure default đã định |
| Flag provider failure | Timeout, lỗi xác thực hoặc cache miss | Fallback đúng theo loại flag |
| Authorization | Flag bật nhưng user thiếu permission | API vẫn từ chối |
| Object/tenant | Flag bật cho tenant A, user gửi tenant B | Không áp dụng targeting sai tenant |
| Client tampering | Gửi featureEnabled/isAdmin trong body hoặc header | Không ảnh hưởng quyết định server |
| Cache isolation | Hai tenant dùng cùng instance/cache | Không rò flag giữa tenant |
| Kill switch | Tắt khi có job đang chạy | Job và callback theo runbook, không mất đối soát |
| Environment separation | Staging và production có config khác nhau | Không dùng nhầm endpoint/credential |
| Secure config | CORS wildcard, debug hoặc actuator public | Startup/deployment check phát hiện |
| Runtime reload | Config mới sai schema hoặc thiếu field | Từ chối áp dụng, giữ version an toàn |
| Config drift | Một instance không nhận version mới | Có metric/alert và quy trình khắc phục |
| Rollback | Rollback flag sau khi đã ghi dữ liệu mới | Dữ liệu và workflow vẫn nhất quán |
| Control plane | User không có quyền thay đổi flag | Từ chối và audit |
| Secret handling | Kiểm tra log, flag console và crash diagnostics | Không lộ secret |

### 12.1. Test cả hai nhánh code

Mỗi flag cần có test cho:

- Flag off.
- Flag on.
- Flag không xác định.
- Flag provider lỗi.
- Targeting match và không match.
- Config version cũ và mới trong giai đoạn chuyển tiếp.

Nếu chỉ test nhánh bật, code cũ có thể bị hỏng. Nếu chỉ test nhánh tắt, tính năng mới có thể bỏ qua authorization hoặc validation.

### 12.2. Kiểm thử trong pipeline

CI/CD có thể kiểm tra cấu hình theo schema, phát hiện key không biết, xác minh URL/scheme/host, phát hiện debug setting không được phép và so sánh policy giữa môi trường. Không in secret ra log khi chạy validator.

Trước production deployment, kiểm tra:

- Security config version đã được review.
- Flag nhạy cảm có owner và approval.
- Production secret được inject từ nguồn tin cậy.
- CORS, debug, docs và actuator đúng chính sách.
- Authentication, authorization và rate limit không bị vô hiệu hóa.
- Health check không tiết lộ chi tiết nội bộ.

## 13. Giám sát và phản ứng khi cấu hình sai

Theo dõi các chỉ số:

- Flag/config version theo instance và environment.
- Số lần bật/tắt flag nhạy cảm.
- Thay đổi targeting theo tenant hoặc principal.
- Tỷ lệ request đi vào code path mới/cũ.
- Authorization denial và lỗi nghiệp vụ sau rollout.
- Tỷ lệ timeout, 5xx, latency và resource use.
- Số lần fallback vì flag/config provider lỗi.
- Config validation/reload failure.

Alert nên tập trung vào thay đổi bất thường hoặc sai lệch so với baseline. Ví dụ flag refund tự động bật ngoài change window, một tenant không nằm trong pilot lại dùng endpoint mới, actuator trở nên public hoặc một instance chạy config version cũ.

Khi phát hiện sai cấu hình:

1. Xác định scope: một instance, một region, một tenant hay toàn hệ thống.
2. Dừng rollout hoặc dùng kill switch đã được phê duyệt.
3. Bảo toàn audit và config version để điều tra.
4. Xác định request/job đã thực hiện side effect.
5. Đối soát dữ liệu và xử lý compensation nếu cần.
6. Khôi phục config đã xác minh.
7. Kiểm tra mọi instance đã nhận cấu hình đúng.
8. Ghi nhận nguyên nhân và bổ sung test/policy ngăn tái diễn.

Không chỉ nhìn thấy flag đã tắt trong dashboard rồi kết luận hệ thống an toàn. Cần xác minh trạng thái thực tế trên instance, queue, worker và provider liên quan.

## 14. Những sai lầm thường gặp

- **Dùng feature flag thay authorization:** người không có quyền vẫn có thể gọi endpoint trực tiếp.
- **Tin flag do client gửi:** client có thể tự bật tính năng hoặc giả tenant.
- **Mặc định bật khi provider lỗi:** tính năng chưa được phê duyệt có thể mở ngoài ý muốn.
- **Dùng một fallback cho mọi flag:** action tài chính và tính năng đọc có mức rủi ro khác nhau.
- **Không có owner hoặc expiry:** flag cũ tồn tại và tạo nhánh code không được kiểm thử.
- **Targeting bằng dữ liệu không tin cậy:** attacker có thể tự đưa mình vào nhóm pilot.
- **Cache không có tenant scope:** flag của tenant này được dùng cho tenant khác.
- **Kill switch chỉ tắt request mới:** job/callback đang chạy tiếp tục tạo side effect ngoài dự kiến.
- **Coi environment là header client:** request có thể chọn cấu hình hoặc credential production.
- **Dùng chung credential giữa môi trường:** staging bị xâm nhập có thể ảnh hưởng production.
- **Để debug/actuator/docs public:** lộ thông tin cấu hình và vận hành.
- **CORS được coi là authorization:** non-browser client vẫn có thể gọi API.
- **Reload cấu hình từng phần:** instance rơi vào trạng thái security policy không nhất quán.
- **Không theo dõi config drift:** một số instance tiếp tục dùng policy cũ.
- **Đưa secret vào flag platform:** người có quyền xem flag có thể lấy credential.
- **Không kiểm tra cả hai nhánh rollout:** lỗi xuất hiện khi bật/tắt hoặc rollback.

## 15. Checklist trước khi phát hành

- [ ] Mỗi flag có tên, mục đích, owner, loại, scope, default và ngày xem xét.
- [ ] Flag chỉ điều khiển tính khả dụng/biến thể; authorization vẫn được kiểm tra ở server.
- [ ] Targeting dùng principal/tenant context đã xác minh.
- [ ] Client không thể tự gửi flag, role hoặc environment để mở chức năng.
- [ ] Flag nhạy cảm có approval, audit và rollback/kill-switch runbook.
- [ ] Fallback khi flag provider lỗi được định nghĩa theo tác động của từng flag.
- [ ] Kill switch xử lý rõ request mới, job đang chạy và callback đến muộn.
- [ ] Flag cache có tenant scope, TTL và invalidation phù hợp.
- [ ] Release flag có kế hoạch loại bỏ; operational flag có review định kỳ.
- [ ] Environment được xác định bởi deployment, không bởi request client.
- [ ] Dev, staging và production tách dữ liệu, endpoint, credential và quyền.
- [ ] Cấu hình có kiểu, schema validation và secure default.
- [ ] CORS, TLS/proxy, debug, actuator, API docs, rate limit và error handling được kiểm tra.
- [ ] Secret nằm trong secret manager, được tách theo service/môi trường và có rotation.
- [ ] Runtime config có version, atomic apply, audit và rollback.
- [ ] Có phát hiện config drift giữa các instance.
- [ ] CI/CD kiểm tra cấu hình và cả nhánh flag on/off.
- [ ] Có test provider failure, targeting, cache isolation, kill switch và rollback.
- [ ] Có dashboard/alert cho thay đổi flag, config version và lỗi sau rollout.

Feature flag và environment config là một phần của bề mặt bảo mật API vì chúng có thể thay đổi endpoint, quyền vận hành, dependency và hành vi workflow. Khi flag được tách khỏi authorization, cấu hình được xác thực theo schema, môi trường và secret được phân tách, còn mọi thay đổi đều có owner và audit, hệ thống sẽ giảm nguy cơ mở nhầm chức năng hoặc triển khai sai chính sách bảo mật.
