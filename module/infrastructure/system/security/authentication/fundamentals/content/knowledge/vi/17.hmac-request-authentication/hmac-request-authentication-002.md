# Shared secret — Bí mật dùng chung trong xác thực request bằng HMAC

> **Chương:** HMAC request authentication  
> **Chủ đề:** Shared secret

**Shared secret** là một giá trị bí mật được chia sẻ trước giữa bên tạo request và bên xác minh request. Trong xác thực request bằng **HMAC (Hash-based Message Authentication Code)**, cả hai bên dùng cùng khóa bí mật để tạo hoặc kiểm tra mã xác thực cho một thông điệp. Nếu chữ ký hợp lệ, bên nhận có bằng chứng rằng request được tạo bởi một chủ thể đang kiểm soát khóa tương ứng và nội dung được ký không bị thay đổi trên đường truyền.

Shared secret không phải password người dùng, API key chỉ dùng làm tên định danh, hay một chuỗi bí mật đặt trong mã nguồn rồi gửi cho mọi client. Nó là **khóa mật mã có vòng đời**: phải được sinh đủ ngẫu nhiên, phân phối qua kênh tin cậy, lưu trữ có kiểm soát, gắn với đúng client/phạm vi, luân chuyển và thu hồi khi cần. Nếu nhiều client dùng chung một secret, bên nhận khó phân biệt client nào đã tạo request và một client bị lộ khóa có thể ảnh hưởng tới tất cả.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, tập trung vào cách quản lý shared secret để xác thực request an toàn. Người học cần phân biệt tính toàn vẹn/xác thực thông điệp với mã hóa, authorization, chống replay và quản lý phiên; đồng thời hiểu ranh giới tin cậy giữa client, gateway, API và hệ thống quản lý khóa.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích shared secret và cách HMAC dùng khóa đối xứng để xác thực thông điệp.
2. Phân biệt secret, key ID, API key, password, hash thường và HMAC.
3. Thiết kế sinh, phân phối, lưu trữ, giới hạn phạm vi, rotation và revocation của secret.
4. Mô tả dữ liệu request cần được ký và cách tạo canonical representation ổn định.
5. Phòng chống sửa nội dung, replay, giả mạo client, rò rỉ secret và lỗi cấu hình proxy.
6. Thiết kế xác minh HMAC với so sánh constant-time, nonce, timestamp và xử lý request đồng thời.
7. Xây dựng test plan và threat model cho tích hợp service-to-service dùng HMAC.

## 2. Shared secret và HMAC là gì?

HMAC là một cơ chế tạo mã xác thực thông điệp dựa trên một hàm băm mật mã và một khóa bí mật. Với HMAC-SHA-256, hai bên dùng cùng secret key và cùng thông điệp để tính mã xác thực. Bên nhận tự tính lại mã và so sánh với mã được gửi kèm request.

Ở mức khái niệm:

~~~text
message = canonical_request(request)
tag = HMAC-SHA-256(shared_secret, message)

Client gửi:
  key_id
  timestamp
  nonce
  signature = tag

Server:
  tìm secret theo key_id
  tự canonicalize request
  tính HMAC với secret tương ứng
  so sánh an toàn với signature nhận được
~~~

HMAC không phải chỉ là SHA-256 của secret nối với nội dung. Không tự thiết kế công thức như hash(secret + message) hoặc hash(message + secret); hãy dùng thư viện HMAC chuẩn của nền tảng.

### 2.1. HMAC cung cấp điều gì?

Khi triển khai đúng, HMAC có thể cung cấp:

- **Message integrity:** phát hiện nội dung được ký bị thay đổi;
- **Message authentication:** xác nhận bên tạo mã có khả năng sử dụng khóa bí mật tương ứng;
- **Keyed verification:** người không có secret khó tạo mã hợp lệ cho một request mới.

HMAC không tự cung cấp:

- **Confidentiality:** nội dung request không được mã hóa bởi HMAC; vẫn cần TLS;
- **Authorization:** chữ ký hợp lệ không có nghĩa client được phép gọi mọi API;
- **Replay protection:** một chữ ký hợp lệ có thể bị gửi lại nếu giao thức không ràng buộc thời gian/nonce và không lưu trạng thái chống replay;
- **Non-repudiation:** vì nhiều bên cùng giữ một khóa, bên xác minh cũng có khả năng tạo chữ ký; HMAC không chứng minh riêng một cá nhân đã ký theo nghĩa chữ ký số bất đối xứng.

### 2.2. Shared secret khác các loại credential nào?

| Thành phần | Đặc điểm | Có phải shared secret HMAC không? |
| --- | --- | --- |
| **Password** | Bí mật do người dùng nhớ, thường có entropy thấp và được xác minh bằng password hashing | Không |
| **API key dạng bearer** | Chuỗi ai sở hữu có thể dùng để truy cập trong phạm vi được cấp | Không nhất thiết; có thể không ký nội dung request |
| **HMAC key** | Khóa ngẫu nhiên được hai phía dùng để tạo/xác minh MAC | Có |
| **Public key** | Khóa công khai dùng kiểm tra chữ ký bất đối xứng | Không |
| **Private key** | Khóa bí mật riêng của một chủ thể để ký | Không phải shared secret; verifier dùng public key |
| **Hash thông thường** | Tóm tắt nội dung, không có khóa bí mật | Không |
| **Session token** | Giá trị đại diện phiên, thường hoạt động như bearer credential | Không, trừ khi một giao thức riêng định nghĩa khác |

Một API key có thể dùng làm **key ID** để tra cứu secret, nhưng không nên mặc định chính API key là khóa HMAC. Nên tách định danh công khai khỏi khóa ký bí mật.

## 3. HMAC request authentication hoạt động ra sao?

Client và server cần thống nhất một giao thức: request nào được ký, cách biểu diễn request, thuật toán, key ID, timestamp, nonce, định dạng chữ ký và chính sách replay. Cả hai bên phải tính HMAC trên **cùng một chuỗi byte**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant K as Secret store / KMS
    participant S as API server
    participant R as Replay store
    C->>K: Lấy hoặc sử dụng secret được cấp cho client
    K-->>C: Secret trong phạm vi bảo vệ
    C->>C: Canonicalize request
    C->>C: Tính HMAC(secret, canonical request)
    C->>S: Request + key_id + timestamp + nonce + signature
    S->>K: Tra secret theo key_id
    K-->>S: Secret/handle xác minh
    S->>S: Canonicalize đúng cùng quy tắc, tính HMAC
    S->>S: So sánh tag bằng constant-time
    S->>R: Kiểm tra và tiêu thụ nonce nguyên tử
    R-->>S: Nonce mới và hợp lệ
    S->>S: Xác thực principal và kiểm tra authorization
    S-->>C: Response
~~~

Sơ đồ thể hiện trách nhiệm logic; trong thực tế client và server có thể dùng KMS/HSM, secret manager hoặc thư viện mật mã tại runtime. Không nhất thiết đưa secret ra khỏi KMS nếu dịch vụ hỗ trợ thao tác HMAC trực tiếp.

### 3.1. Trình tự xác minh ở server

1. Kiểm tra cấu trúc request, phương thức, kích thước và header bắt buộc.
2. Đọc key ID từ trường đã quy định; xác định client/principal và trạng thái secret.
3. Kiểm tra timestamp nằm trong cửa sổ chấp nhận.
4. Tạo canonical request từ dữ liệu server thực sự nhận được.
5. Tính HMAC bằng secret tương ứng.
6. So sánh chữ ký theo cách constant-time, không dùng so sánh chuỗi thông thường có thể lộ timing.
7. Chỉ sau khi chữ ký hợp lệ, kiểm tra nonce và tiêu thụ một lần theo thao tác nguyên tử.
8. Ánh xạ key ID sang principal, áp dụng authorization theo action/resource/tenant.
9. Ghi audit event đã loại bí mật và thực hiện request.

Thứ tự kiểm tra có thể tối ưu theo tải và nguy cơ DoS, nhưng **không thực thi nghiệp vụ trước khi xác thực request**. Không cập nhật trạng thái nonce hoặc tài nguyên dựa trên một request chưa được xác minh.

## 4. Sinh shared secret đủ mạnh

Shared secret phải được sinh bằng **cryptographically secure random number generator (CSPRNG)**. Không dùng tên service, email, timestamp, UUID không rõ nguồn entropy, password con người hoặc chuỗi tự nghĩ làm HMAC key.

Với HMAC-SHA-256, một khóa ngẫu nhiên 256 bit (32 byte) là lựa chọn thực tế phổ biến. Thuật toán HMAC cho phép khóa có độ dài khác, nhưng key phải có entropy đủ cao và phù hợp chính sách. Không cần tự băm password để biến nó thành HMAC key; password có thể bị đoán và cần cơ chế password KDF riêng.

### 4.1. Nguyên tắc sinh khóa

- Sinh khóa bằng API CSPRNG của nền tảng hoặc KMS/HSM.
- Dùng entropy đủ lớn; tránh chuỗi có thể đoán hoặc có cấu trúc từ thông tin tổ chức.
- Lưu key dưới dạng byte hoặc encoding chuẩn đã thống nhất; không vô tình đổi encoding khi tính HMAC.
- Tạo một secret riêng cho từng client/integration và môi trường khi có thể.
- Không sinh lại cùng một secret cho nhiều khách hàng chỉ để dễ cấu hình.
- Không đưa secret vào log, ticket, source control, tài liệu onboarding hoặc biến môi trường được dump rộng rãi.

Ví dụ biểu diễn một secret ngẫu nhiên bằng Base64 hoặc Base64url:

~~~text
key_id: client-school-a-v3
secret_encoding: base64url
secret: [giá trị ngẫu nhiên được cấp qua kênh bảo mật]
algorithm: HMAC-SHA-256
~~~

Đây là metadata minh họa, không phải secret thật. **Key ID không cần bí mật**, nhưng không nên chứa thông tin nhạy cảm; secret phải được bảo vệ riêng.

### 4.2. Độ dài khóa và tag

HMAC-SHA-256 thường tạo tag 256 bit. Giữ đầy đủ tag là lựa chọn đơn giản và an toàn. Nếu một giao thức bắt buộc cắt ngắn tag, cần đánh giá xác suất đoán, giới hạn thử và quy định độ dài tối thiểu phù hợp; không tùy tiện cắt còn vài byte để tiết kiệm header. Không dùng HMAC-MD5 hoặc HMAC-SHA-1 cho thiết kế mới khi có lựa chọn hiện đại phù hợp.

## 5. Phân phối secret giữa hai bên

Một khóa chỉ hữu ích khi cả client và server nhận đúng cùng một giá trị, nhưng quá trình phân phối chính là thời điểm secret dễ bị lộ. Cần có kênh provisioning tin cậy, xác minh danh tính đối tác và kiểm soát ai có thể đọc khóa.

### 5.1. Kênh provisioning

Các lựa chọn thường gặp:

- Secret manager/KMS tích hợp với workload identity để cấp quyền đọc hoặc sử dụng khóa;
- Cổng quản trị tích hợp có xác thực mạnh, chỉ hiển thị secret một lần khi tạo;
- Kênh trao đổi ngoài băng đã được xác minh cho tích hợp B2B;
- Quy trình cấp credential có phê duyệt, audit, thời hạn và xác nhận nhận khóa.

Không gửi secret qua email/chat thường, issue tracker, query string, mã QR công khai hoặc tài liệu dùng chung. Nếu phải chuyển một lần cho đối tác, dùng kênh mã hóa và xác minh người nhận qua một kênh độc lập. Sau khi trao đổi, hạn chế khả năng xem lại secret và ghi nhận thời điểm cấp.

### 5.2. Phân tách môi trường

Development, staging và production phải có key riêng. Không dùng khóa production trong ví dụ, test fixture, log CI hoặc môi trường local. Khi một môi trường bị lộ, phạm vi ảnh hưởng phải được giới hạn trong môi trường đó.

### 5.3. Cấp quyền theo nguyên tắc tối thiểu

Một service chỉ nên được đọc hoặc sử dụng secret cần cho công việc của nó. Tách quyền:

- Ai được tạo secret?
- Ai được xem secret một lần?
- Runtime nào được dùng secret để ký?
- Server nào được xác minh bằng secret?
- Ai được rotate/revoke?
- Ai có quyền audit metadata?

Không cấp quyền đọc toàn bộ secret store cho một ứng dụng chỉ vì nó cần một khóa HMAC. Ưu tiên quyền theo secret ID, namespace, workload identity và môi trường.

## 6. Lưu trữ và sử dụng secret an toàn

Shared secret là dữ liệu xác thực có giá trị cao. Việc lưu trong database, file cấu hình hoặc biến môi trường cần được đánh giá theo mô hình đe dọa thực tế.

### 6.1. Secret manager và KMS/HSM

Ưu tiên:

- Secret manager chuyên dụng với access policy, audit và rotation;
- KMS/HSM có khả năng thực hiện HMAC mà không xuất khóa ra ứng dụng;
- Workload identity để runtime lấy đúng quyền sử dụng khóa;
- Mã hóa backup và giới hạn người có thể khôi phục;
- Tách metadata không bí mật (key ID, trạng thái, thời hạn) khỏi material bí mật.

Nếu ứng dụng cần lấy secret vào bộ nhớ, giảm thời gian tồn tại và không tạo bản sao không cần thiết. Tránh đưa secret vào command-line argument, crash dump, debug trace hoặc output của CI.

### 6.2. Biến môi trường có phải luôn an toàn?

Environment variable tiện cho cấu hình nhưng có thể bị lộ qua process inspection, crash dump, diagnostic endpoint, log khởi động hoặc hệ thống triển khai. Không nên coi biến môi trường là secret manager. Nếu dùng, cần giới hạn quyền đọc tiến trình, tránh in cấu hình và có kế hoạch rotate. Với hệ thống nhạy cảm, ưu tiên KMS/secret manager và quyền truy cập ngắn hạn.

### 6.3. Không dùng một secret cho mọi mục đích

Không dùng chung HMAC key cho:

- Xác thực request API;
- Ký token hoặc cookie;
- Mã hóa dữ liệu;
- Tạo reset token;
- Ký webhook cho nhiều đối tác không liên quan.

Mỗi mục đích nên có khóa riêng hoặc khóa dẫn xuất theo cơ chế chuẩn với context separation, chẳng hạn HKDF khi kiến trúc thực sự cần dẫn xuất. Không tự nối tên mục đích vào secret rồi băm tùy tiện để tạo key.

## 7. Mỗi client nên có secret riêng

Nếu nhiều client cùng dùng một shared secret, mọi bên giữ khóa đều có khả năng tạo HMAC hợp lệ cho các request của nhau. Server khó xác định nguồn cụ thể, và việc thu hồi một client có thể buộc thay khóa cho tất cả.

~~~mermaid
flowchart TD
    A["API verifier"] --> K[("Key registry / KMS")]
    K --> S1["Secret riêng: client A"]
    K --> S2["Secret riêng: client B"]
    K --> S3["Secret riêng: client C"]
    S1 --> P1["Principal A"]
    S2 --> P2["Principal B"]
    S3 --> P3["Principal C"]
~~~

### 7.1. Lợi ích của khóa riêng theo client

- Xác định được principal theo key ID;
- Thu hồi một client mà không làm gián đoạn các client khác;
- Giới hạn phạm vi khi một secret bị lộ;
- Áp dụng quyền, quota, rate limit và audit theo từng client;
- Luân chuyển khóa độc lập theo lịch và rủi ro.

### 7.2. Key ID không phải secret

Request thường mang một key ID để server biết cần tra khóa nào. Key ID chỉ là **selector**, không phải bằng chứng xác thực. Kẻ tấn công có thể biết key ID; server vẫn phải xác minh HMAC bằng secret và kiểm tra trạng thái key.

Không cho phép client tự chọn tenant hoặc principal tùy ý từ key ID mà thiếu mapping server-side. Key registry phải ràng buộc key ID với principal, tenant, scope, trạng thái và thuật toán được phép.

## 8. Ký request: canonicalization quan trọng thế nào?

HMAC xác thực **chuỗi byte chính xác**. Nhưng một HTTP request có nhiều thành phần và có thể được biểu diễn khác nhau mà vẫn có ý nghĩa tương tự. Client và server phải định nghĩa cùng một cách chuẩn hóa (*canonicalization*).

Một canonical request có thể bao gồm:

1. HTTP method, viết theo quy tắc đã định;
2. Authority/host hoặc audience API;
3. Path đã chuẩn hóa theo quy tắc chính xác;
4. Query parameters theo thứ tự/encoding được quy định;
5. Các header được chọn và giá trị đã chuẩn hóa;
6. Content digest của body;
7. Timestamp;
8. Nonce hoặc request ID;
9. Key ID/algorithm nếu giao thức quy định chúng trong chuỗi ký.

Ví dụ chuỗi ký minh họa:

~~~text
POST
api.example.org
/v1/payments
amount=250000&currency=VND
content-type:application/json
content-digest:sha-256=:BASE64_DIGEST:
created:1790000000
nonce:random-unique-value
~~~

Đây chỉ là một định dạng minh họa. Không phải chuẩn HTTP signature hoàn chỉnh. Client và server phải dùng một đặc tả đã thống nhất; khi có thể, ưu tiên tiêu chuẩn được đánh giá thay vì tự tạo canonical format không rõ quy tắc.

### 8.1. Những lỗi canonicalization phổ biến

- Client sắp xếp query parameter nhưng server giữ nguyên thứ tự, hoặc ngược lại;
- Một bên decode percent-encoding trước khi ký, bên kia ký chuỗi encoded;
- Path có dấu gạch chéo lặp, dot segment hoặc ký tự Unicode được chuẩn hóa khác nhau;
- Header trùng tên xuất hiện nhiều lần nhưng hai bên nối giá trị khác nhau;
- Header có khoảng trắng, chữ hoa/thường hoặc dấu phẩy được xử lý không nhất quán;
- Proxy thay đổi host, path, content encoding hoặc query trước khi verifier kiểm tra;
- Body được parse rồi serialize lại, làm đổi whitespace, thứ tự field hoặc biểu diễn số;
- Một bên ký body rỗng nhưng bên kia không phân biệt request không có body và body dài 0 byte.

### 8.2. Ký raw body hay digest?

Có thể đưa raw body vào canonical string, nhưng request body lớn hoặc streaming khiến việc xử lý khó hơn. Một lựa chọn phổ biến là tính **digest** của body rồi ký digest đó. Server phải tính lại digest từ body nhận được và so khớp; không tin digest do client gửi nếu chưa đưa digest vào chuỗi HMAC.

Nếu body được giải nén, biến đổi hoặc chuẩn hóa bởi proxy, hai phía phải thống nhất **body nào** được ký: byte nhận ở edge, byte chuyển tới backend hay biểu diễn khác. Không được để HMAC xác thực một body nhưng business logic xử lý một body khác.

### 8.3. Host, path và audience

Ký host/authority hoặc audience giúp ngăn request đã ký cho một API bị chuyển sang API khác. Ký method và path giúp ngăn đổi GET thành POST hoặc chuyển request sang endpoint nhạy cảm hơn. Nếu hệ thống dùng reverse proxy, cần xác định giá trị nào là authority/path gốc và proxy nào được phép đặt lại chúng.

## 9. Chống replay bằng timestamp và nonce

Một HMAC hợp lệ có thể bị ghi lại rồi gửi lại. HMAC chứng minh người tạo request từng kiểm soát secret, nhưng không tự chứng minh request đang được gửi lần đầu.

### 9.1. Timestamp

Client gửi thời điểm tạo request. Server chỉ chấp nhận request trong cửa sổ thời gian được cấu hình, có tính đến clock skew. Timestamp giúp giới hạn thời gian một chữ ký cũ có thể được chấp nhận.

Timestamp không đủ chống replay trong cửa sổ chấp nhận. Kẻ tấn công có thể gửi lại cùng request nhiều lần trong khoảng thời gian đó.

### 9.2. Nonce

Nonce là giá trị ngẫu nhiên hoặc duy nhất cho mỗi request. Server lưu/đánh dấu nonce đã dùng trong phạm vi key/principal và cửa sổ thời gian; request lặp lại bị từ chối.

Yêu cầu:

- Nonce đủ khó đoán và không tái sử dụng trong phạm vi khóa;
- Nonce được đưa vào canonical request để chữ ký bảo vệ nó;
- Server lưu trạng thái trong TTL bao phủ cửa sổ timestamp;
- Kiểm tra và tiêu thụ nonce phải **nguyên tử** để hai request đồng thời không cùng được chấp nhận;
- Cache nonce được phân tán/nhất quán đủ cho mọi instance API nhận request;
- Phản hồi retry và timeout phải có ngữ nghĩa rõ, tránh client vô tình tạo giao dịch trùng.

### 9.3. Idempotency key khác nonce

Nonce chống việc dùng lại một request đã ký; **idempotency key** giúp ứng dụng xử lý retry của cùng một thao tác nghiệp vụ mà không thực hiện hai lần. Hai khái niệm có thể cùng xuất hiện nhưng không thay thế nhau.

Ví dụ, client gửi lệnh tạo thanh toán, server xử lý xong nhưng response bị mất. Client cần retry an toàn theo idempotency key; nếu giao thức yêu cầu nonce một lần, retry có thể cần request mới với nonce mới nhưng cùng idempotency key. Server phải bảo đảm không tạo khoản thanh toán thứ hai.

## 10. So sánh HMAC an toàn

Sau khi server tính tag mong đợi, cần so sánh với tag nhận được bằng hàm **constant-time comparison** do thư viện chuẩn cung cấp, trong phạm vi độ dài hợp lệ. Không dùng so sánh chuỗi thông thường có thể dừng ở byte khác biệt đầu tiên.

Pseudocode:

~~~text
expected_tag = HMAC_SHA256(secret_for_key_id, canonical_request)

if not constant_time_equal(expected_tag, supplied_tag):
    reject_request()
~~~

Trước khi so sánh, kiểm tra encoding và độ dài tag theo giao thức. Không tự padding tag sai định dạng để cố làm nó hợp lệ. Phản hồi lỗi công khai nên chung chung; log nội bộ có thể ghi nhóm nguyên nhân đã lọc bí mật.

### 10.1. Không so sánh bằng hash thường

HMAC đã tạo tag có khóa. Không cần thêm SHA-256 của tag hoặc so sánh hash của hai chuỗi bằng hàm không phù hợp. Dùng API HMAC và API constant-time compare được nền tảng cung cấp.

### 10.2. Thứ tự kiểm tra và chống DoS

Server có thể kiểm tra nhanh định dạng, key ID, kích thước, timestamp và quota trước khi thực hiện HMAC tốn tài nguyên. Nhưng không nên tiết lộ quá nhiều thông tin về key registry qua lỗi chi tiết. Không thực hiện nghiệp vụ trước khi xác minh chữ ký và chống replay. Rate limit theo key ID, nguồn và toàn dịch vụ giúp giảm request rác.

## 11. Authorization sau HMAC

HMAC hợp lệ xác thực request theo một key đã được đăng ký. Server cần ánh xạ key ID thành **principal**, rồi kiểm tra quyền trên hành động, tài nguyên và tenant.

~~~text
verified_key:
  key_id = client-school-a-v3
  principal = integration_school_a
  tenant = school-a
  scopes = [attendance:write]

request:
  method = POST
  path = /v1/attendance
  resource_tenant = school-a
  action = attendance:write

decision:
  PERMIT only if signature, replay policy, account status,
  tenant binding, scope and resource policy all pass
~~~

Một request ký đúng bằng secret của trường A không được phép ghi dữ liệu trường B nếu principal không có quyền đó. Không lấy role, tenant hoặc scope do client gửi trong body làm căn cứ cuối cùng. Quyền phải đến từ mapping/policy server-side.

### 11.1. Phân tách xác thực và phân quyền

| Kiểm tra | Câu hỏi |
| --- | --- |
| HMAC | Request có được tạo bởi bên kiểm soát secret tương ứng và nội dung ký có toàn vẹn không? |
| Replay protection | Request này có còn mới và chưa được tiêu thụ không? |
| Principal mapping | Secret thuộc client/service nào? |
| Authorization | Principal được gọi action trên resource/tenant này không? |
| Business validation | Dữ liệu có hợp lệ theo quy tắc nghiệp vụ không? |

Một request có thể vượt qua HMAC nhưng thất bại ở authorization hoặc validation. Đây là hành vi đúng, không phải lỗi xác thực.

## 12. TLS vẫn cần thiết

HMAC không mã hóa request và response. Kẻ quan sát mạng có thể đọc body, metadata và tag nếu kết nối không được bảo vệ. TLS cũng giúp xác thực server, bảo vệ nội dung và giảm nguy cơ secret/request bị thu thập trên đường truyền.

Sử dụng HTTPS với xác minh certificate và hostname đúng. Không tắt TLS verification để khắc phục lỗi môi trường. Nếu TLS kết thúc tại gateway, bảo vệ kết nối gateway-backend và xác định chính xác request bytes được HMAC kiểm tra ở tầng nào.

### 12.1. HMAC không che giấu dữ liệu

Nếu body chứa thông tin cá nhân, điểm số hoặc thông tin thanh toán, HMAC chỉ bảo vệ tính toàn vẹn/xác thực của phần được ký; nó không làm nội dung bí mật. TLS, kiểm soát quyền, mã hóa lưu trữ và data minimization vẫn cần thiết.

### 12.2. TLS và HMAC có vai trò khác nhau

- TLS bảo vệ kênh client-server và thường xác thực server.
- HMAC có thể xác thực request ở cấp ứng dụng, kể cả qua một số lớp trung gian nếu canonicalization và trust boundary được thiết kế đúng.
- mTLS xác thực client bằng certificate và proof of possession khóa riêng.
- OAuth access token xác định quyền/ủy quyền trong audience và scope phù hợp.

Không nên thêm HMAC chỉ vì “có thêm lớp bảo mật” mà chưa xác định mối đe dọa. Với service-to-service, mTLS hoặc token sender-constrained có thể phù hợp hơn tùy hạ tầng và khả năng vận hành.

## 13. Rủi ro của shared secret và phạm vi ảnh hưởng

### 13.1. Secret bị lộ

Khi attacker lấy được secret, họ có thể tạo request HMAC hợp lệ trong phạm vi key đó cho tới khi key bị thu hồi hoặc thay thế. Timestamp và nonce không giúp chống kẻ đang kiểm soát secret tạo request mới.

Phản ứng cần:

1. Xác định key ID, principal, tenant, môi trường và các hệ thống sử dụng secret;
2. Vô hiệu hoặc thu hồi key bị lộ theo quy trình có kiểm soát;
3. Cấp secret mới qua kênh tin cậy, cập nhật client và server;
4. Kiểm tra request bất thường, dữ liệu bị đọc/sửa và token/session phát sinh;
5. Thu hồi credential/phần quyền liên quan nếu cần;
6. Xóa secret khỏi source, artifact, log và backup theo chính sách, đồng thời đánh giá phạm vi lộ;
7. Rà soát nguyên nhân và kiểm thử lại.

### 13.2. Một secret dùng chung cho nhiều client

Nếu 50 đối tác dùng cùng một secret, chỉ một đối tác bị xâm nhập có thể giả mạo request của các đối tác còn lại. Server cũng không thể quy trách nhiệm chính xác dựa trên chữ ký đó. Dùng key riêng theo client để giới hạn blast radius và hỗ trợ thu hồi độc lập.

### 13.3. Client công khai không giữ được static secret

Một secret nhúng trong JavaScript chạy trên browser, ứng dụng mobile có thể reverse engineer hoặc desktop client phân phối rộng **không thể được xem là bí mật lâu dài**. Người dùng có thể trích xuất nó từ bundle, binary, bộ nhớ hoặc runtime. Nếu mọi bản cài đặt có cùng secret, một bản bị phân tích có thể làm lộ khóa của tất cả.

Đối với browser/mobile public client, cân nhắc:

- Dùng backend-for-frontend để giữ secret ở server;
- Dùng OAuth/OIDC với Authorization Code + PKCE cho user authentication;
- Dùng mTLS/workload identity cho service được quản lý;
- Dùng cơ chế proof-of-possession phù hợp như DPoP trong kiến trúc OAuth hỗ trợ;
- Cấp credential riêng có thời hạn/ngữ cảnh cho từng client khi có cơ chế bảo vệ thực sự.

Không gọi một khóa nhúng trong app là “secret an toàn” chỉ vì đã obfuscate hoặc mã hóa bằng một khóa khác nằm cùng binary.

## 14. Rotation và quản lý vòng đời key

Secret phải có trạng thái và vòng đời rõ ràng. Một key registry có thể lưu:

| Metadata | Ý nghĩa |
| --- | --- |
| **key_id** | Định danh công khai của khóa |
| **principal/tenant** | Client và phạm vi được gắn |
| **algorithm** | Thuật toán HMAC được phép |
| **created_at / expires_at** | Thời điểm cấp và hạn sử dụng nếu có |
| **status** | pending, active, retiring, revoked |
| **secret reference** | Tham chiếu tới KMS/secret manager, không phải secret plaintext |
| **scopes/policy** | Quyền request mà principal có thể thực hiện |
| **rotation metadata** | Khóa mới/cũ, overlap và thời điểm kết thúc |

### 14.1. Rotation không gián đoạn

Một quy trình rotation có kiểm soát:

1. Tạo secret mới với key ID mới cho cùng principal.
2. Phân phối secret mới tới client qua kênh bảo mật.
3. Cho phép server xác minh cả key cũ và mới trong khoảng overlap ngắn, có ngày kết thúc.
4. Client chuyển sang ký bằng key mới; theo dõi request theo key ID để xác nhận chuyển đổi.
5. Ngừng chấp nhận key cũ và thu hồi secret cũ.
6. Xóa hoặc vô hiệu material cũ khỏi nơi lưu theo retention policy; cập nhật inventory/audit.

Không để overlap kéo dài vô thời hạn. Nếu secret cũ bị lộ, không nên chờ hết lịch rotation bình thường; cần revoke nhanh và chấp nhận gián đoạn có kiểm soát nếu cần.

### 14.2. Thu hồi và trạng thái key

Server phải kiểm tra trạng thái key ID trước khi chấp nhận request. Key revoked/expired/disabled không được dùng chỉ vì HMAC đúng. Cache key status cần TTL và cơ chế invalidation để thu hồi có hiệu lực theo yêu cầu.

Nếu một key bị thu hồi nhưng request đã xác minh và đang chạy, cần xác định chính sách cho transaction đang thực hiện. Với thao tác tài chính/nhạy cảm, có thể cần kiểm tra trạng thái principal lần cuối trước khi commit.

### 14.3. Backup và khôi phục

HMAC verifier cần secret gốc để tính tag; mất khóa có thể làm client không thể xác thực. Backup phải được bảo vệ tương đương secret production, có quyền phục hồi giới hạn và audit. Không xuất toàn bộ secret thành một file backup không mã hóa để “phòng trường hợp”.

## 15. Canonicalization qua proxy và nhiều tầng dịch vụ

Trong kiến trúc có CDN, WAF, load balancer, API gateway và backend, request có thể thay đổi trước khi HMAC verifier nhìn thấy nó.

Ví dụ:

- Gateway thay Host bằng tên nội bộ;
- Path prefix được thêm/bỏ;
- Query parameters được sắp xếp hoặc decode;
- Header hop-by-hop bị loại;
- Body được giải nén hoặc chuyển encoding;
- Một header trùng tên bị gộp;
- Gateway chuyển request thành HTTP/2 hoặc HTTP/1.1.

### 15.1. Chọn điểm xác minh

Hai cách phổ biến:

**Xác minh tại edge/gateway:** gateway nhận request gốc, tạo canonical representation theo hợp đồng và kiểm tra HMAC. Backend nhận principal context được gateway bảo vệ. Cần bảo đảm backend chỉ tin gateway và không có đường truy cập bypass.

**Xác minh tại backend:** gateway chuyển tiếp request mà không thay đổi các thành phần đã ký, hoặc cung cấp metadata nguyên bản theo một hợp đồng được bảo vệ. Backend phải có đủ dữ liệu để tái tạo chính xác canonical request mà client đã ký.

Không được để gateway kiểm tra HMAC trên request A rồi backend xử lý request B đã bị biến đổi. Nếu có chuyển đổi, cần xác định dữ liệu nào được xác thực và dữ liệu nào được xử lý.

### 15.2. Header chuyển tiếp không phải bằng chứng tự thân

Một header như X-Authenticated-Client chỉ đáng tin nếu được tạo bởi gateway đã xác minh HMAC, header do client gửi đã bị xóa và backend xác thực gateway qua mạng/kênh tin cậy. Backend không được tin header cùng tên từ Internet.

## 16. Ví dụ thiết kế request ký bằng HMAC

Giả sử một hệ thống trường học cho phép integration server gửi bản ghi điểm danh tới API. Mỗi trường có key ID và secret riêng.

### 16.1. Request minh họa

~~~http
POST /v1/attendance HTTP/1.1
Host: api.learning.example
Content-Type: application/json
X-Key-Id: school-a-prod-v2
X-Request-Timestamp: 1790000000
X-Request-Nonce: 7Qv3k9xP2mN8rT4w
X-Content-SHA256: BASE64URL_BODY_DIGEST
X-Signature: BASE64URL_HMAC_TAG

{"course_id":"course-101","student_id":"student-417","present":true}
~~~

Các giá trị key ID, timestamp, nonce và chữ ký chỉ là dữ liệu giả minh họa. Secret không được gửi trong header hoặc body. Server dùng key ID để tra secret, tính lại digest và HMAC theo canonical format đã định nghĩa.

### 16.2. Canonical request minh họa

~~~text
HMAC-REQUEST-V1
POST
api.learning.example
/v1/attendance
content-type:application/json
content-sha256:BASE64URL_BODY_DIGEST
timestamp:1790000000
nonce:7Qv3k9xP2mN8rT4w
key-id:school-a-prod-v2
~~~

Client và server phải thống nhất encoding, newline, chữ hoa/thường, thứ tự trường, xử lý query và header trùng. Prefix version giúp nâng cấp format có kiểm soát; server chỉ chấp nhận phiên bản được cấu hình.

### 16.3. Pseudocode phía client

~~~text
sign_request(request, key_id, secret):
    timestamp = current_unix_time()
    nonce = secure_random_unique_value()
    body_digest = SHA256(exact_bytes_sent_as_body)

    canonical = build_canonical_request(
        protocol_version,
        method,
        authority,
        path_and_query,
        selected_headers,
        body_digest,
        timestamp,
        nonce,
        key_id
    )

    signature = HMAC_SHA256(secret, UTF8(canonical))
    send_request_with(key_id, timestamp, nonce, body_digest, signature)
~~~

### 16.4. Pseudocode phía server

~~~text
verify_request(request):
    validate_format_and_size(request)
    key = lookup_active_key(request.key_id)
    if key is missing or key.status is not ACTIVE:
        reject()

    if timestamp_outside_allowed_window(request.timestamp):
        reject()

    actual_digest = SHA256(exact_received_body_bytes)
    if not constant_time_equal(actual_digest, request.body_digest):
        reject()

    canonical = build_canonical_request_using_server_received_values(request)
    expected = HMAC_SHA256(key.secret, UTF8(canonical))
    if not constant_time_equal(expected, decode_signature(request.signature)):
        reject()

    if not atomically_consume_nonce(key.id, request.nonce, request.timestamp):
        reject_replay()

    principal = key.principal
    authorize(principal, request.method, request.resource, request.tenant)
    process_business_request()
~~~

Pseudocode chỉ là khung tư duy. Trong production cần xử lý key rotation, cache trạng thái, nonce phân tán, clock skew, idempotency, lỗi provider/KMS, giới hạn request và canonicalization đúng theo đặc tả đã chọn.

## 17. Kiểm thử HMAC request authentication

Test trong môi trường được phép, dùng key riêng cho từng client thử nghiệm. Không đưa secret production vào fixture hoặc log.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Signature | Chữ ký đúng với request nguyên vẹn | Được xác thực nếu key còn active và policy đạt |
| Tampering | Sửa body sau khi ký | HMAC/digest không khớp, từ chối |
| Method/path | Đổi POST thành GET hoặc đổi path | Chữ ký không hợp lệ |
| Query | Thay, thêm hoặc đổi encoding query | Kết quả theo canonicalization; thay đổi ngoài hợp đồng phải bị phát hiện |
| Header | Sửa content type hoặc header đã ký | Từ chối |
| Body | Body rỗng, body lớn, encoding khác hoặc chunked | Xử lý đúng theo giao thức, không lệch bytes |
| Key ID | Key ID không tồn tại hoặc đã revoked | Từ chối, không tiết lộ secret |
| Wrong secret | Dùng secret của client khác | Từ chối |
| Replay | Gửi lại cùng nonce/request | Request thứ hai bị từ chối |
| Concurrent replay | Hai request cùng nonce đến hai instance | Chỉ một request được chấp nhận |
| Timestamp | Timestamp quá cũ hoặc quá xa tương lai | Từ chối theo cửa sổ |
| Clock skew | Client lệch đồng hồ trong giới hạn | Xử lý theo policy; không mở cửa sổ vô hạn |
| Constant-time | Tag sai ở byte đầu/cuối | Dùng API constant-time; không có nhánh so sánh tự chế |
| Tenant | Secret tenant A ký request tới resource tenant B | Authentication có thể hợp lệ, authorization phải từ chối |
| Rotation | Client chuyển từ key cũ sang key mới | Overlap có giới hạn; key cũ bị từ chối sau cutover |
| Proxy | Gateway thay path/host hoặc client gửi header giả | Hành vi đúng hợp đồng; backend không tin header ngoài |
| Logging | Bật debug, tracing và error capture | Không xuất hiện secret, tag nhạy cảm hoặc dữ liệu xác thực không cần thiết |
| Client exposure | Kiểm tra secret nhúng trong web/mobile bundle | Thiết kế không dựa vào static secret công khai |

### 17.1. Kiểm tra bất biến bảo mật

- Không có request nào được xử lý nghiệp vụ trước khi HMAC hợp lệ;
- Request bị sửa sau khi ký luôn bị từ chối;
- Một nonce chỉ được chấp nhận một lần trong phạm vi quy định;
- Key revoked không được chấp nhận dù chữ ký đúng;
- Key của client này không xác thực được principal khác;
- Chữ ký hợp lệ không vượt qua authorization hoặc tenant isolation;
- Secret không xuất hiện trong log, response, URL, source control hoặc artifact;
- Rotation không vô tình giữ key cũ hoạt động vô thời hạn.

## 18. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng password làm HMAC key | Entropy thấp, dễ đoán/offline guessing | Sinh khóa ngẫu nhiên bằng CSPRNG |
| Dùng một secret cho mọi client | Một client bị lộ ảnh hưởng toàn hệ thống | Key riêng theo client/principal |
| Gửi secret trong mỗi request | Lộ trực tiếp credential | Chỉ gửi key ID và HMAC tag |
| Ký chỉ body, bỏ method/path | Request có thể bị chuyển endpoint hoặc đổi hành động | Ký method, authority, path/query và body digest |
| Không ký timestamp/nonce | Request hợp lệ có thể bị replay | Timestamp + nonce và replay store |
| Dùng hash(secret + message) | Công thức tự chế không phải HMAC | Dùng HMAC API chuẩn |
| So sánh tag thông thường | Có thể tạo timing side channel | Constant-time compare |
| Canonicalization không thống nhất | False reject hoặc request khác được chấp nhận | Đặc tả versioned và test vector chung |
| Tin key ID do client khai như principal | Có thể nhầm tenant/identity | Server-side key registry |
| HMAC đúng là cho phép mọi action | Authentication bị nhầm với authorization | Policy theo action/resource/tenant |
| Secret nhúng trong browser/mobile | Có thể bị trích xuất từ client công khai | BFF, OAuth/PKCE, mTLS hoặc cơ chế phù hợp |
| Rotation không có overlap/kết thúc | Outage hoặc key cũ còn hiệu lực quá lâu | Quy trình rotation có thời hạn và audit |
| Tin header do client gửi sau proxy | Giả mạo principal | Gateway xóa header, backend xác thực gateway |
| Không bảo vệ bằng TLS | Lộ nội dung request và metadata | HTTPS với xác minh server đúng |

## 19. Checklist vận hành shared secret

1. **Mục đích:** Secret dùng cho request authentication nào? Có đang bị dùng chung cho token, encryption hoặc webhook không?
2. **Chất lượng khóa:** Được sinh bằng CSPRNG, đủ entropy, đúng encoding và thuật toán không?
3. **Phạm vi:** Mỗi client có key riêng? Key ID được ánh xạ server-side tới principal/tenant/scope chưa?
4. **Provisioning:** Secret được phân phối qua kênh tin cậy, có xác minh người nhận và audit không?
5. **Storage:** Dùng secret manager/KMS/HSM; quyền đọc/sử dụng có giới hạn theo workload không?
6. **Request format:** Method, authority, path, query, header, body digest, timestamp và nonce được canonicalize thống nhất không?
7. **Verification:** Dùng HMAC API chuẩn và constant-time compare; xử lý key ID/state đúng không?
8. **Replay:** Timestamp có cửa sổ, nonce có TTL và tiêu thụ nguyên tử; idempotency được xử lý riêng không?
9. **TLS:** Nội dung request có được bảo vệ; hostname/server certificate được xác minh đúng không?
10. **Proxy:** Gateway và backend thống nhất request bytes/identity; header client gửi bị xóa và backend chỉ tin gateway?
11. **Authorization:** Principal có quyền tối thiểu; tenant/resource được kiểm tra ở server?
12. **Rotation/revocation:** Có key version, overlap có hạn, cutover, revoke khẩn cấp và cache invalidation không?
13. **Incident response:** Có thể xác định client/key bị lộ, thay secret và rà soát request/phiên/token liên quan không?
14. **Testing:** Có test tampering, replay, concurrency, canonicalization, key rotation và logging không?

## 20. Bài tập tình huống

Một nền tảng học tập tích hợp với 30 trường. Đội phát triển tạo một chuỗi secret cố định rồi nhúng vào JavaScript của cổng quản trị. Mọi trường dùng chung secret này. Client chỉ tính HMAC trên JSON body, không ký HTTP method, path, timestamp hoặc nonce. Gateway ghi request body khi lỗi. Backend chấp nhận mọi request có HMAC đúng và lấy tenant_id từ body để chọn dữ liệu. Khi một trường kết thúc hợp tác, đội vận hành không biết phải thu hồi secret nào.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** về secret exposure, identity, integrity, replay, authorization và vận hành.
2. Thiết kế lại mô hình key registry với key ID, principal, tenant, scope và trạng thái.
3. Đề xuất phương án thay shared secret nhúng trong browser bằng kiến trúc phù hợp hơn.
4. Xác định canonical request cần ký và quy tắc xử lý body/query/header qua gateway.
5. Thiết kế timestamp, nonce, replay store và idempotency cho request tạo bản ghi điểm danh.
6. Đề xuất quy trình rotation và revocation khi một trường bị lộ khóa hoặc kết thúc hợp tác.
7. Viết test chứng minh request hợp lệ của trường A không thể truy cập tenant B và request đã ký không thể replay.

**Gợi ý đối chiếu:** secret công khai trong JavaScript không thể giữ bí mật; mỗi trường cần credential riêng; key ID chỉ là selector; HMAC không mã hóa và không cấp quyền; cần ký đủ ngữ cảnh request, timestamp/nonce, TLS, constant-time compare, server-side tenant mapping và lifecycle quản lý khóa.

## 21. Ghi nhớ

- **Shared secret** là khóa bí mật hai phía cùng giữ; với HMAC, nó được dùng để tạo và kiểm tra mã xác thực thông điệp.
- HMAC cung cấp **tính toàn vẹn và xác thực thông điệp**, không cung cấp mã hóa, authorization hay replay protection tự động.
- Secret phải được sinh ngẫu nhiên, phân phối qua kênh tin cậy, lưu trong secret manager/KMS phù hợp và **tách riêng theo client/mục đích**.
- Client và server phải ký cùng một canonical request; method, path, query, header và body digest cần quy tắc rõ ràng.
- Timestamp giới hạn tuổi request; nonce và replay store ngăn sử dụng lại; idempotency xử lý retry nghiệp vụ.
- Server dùng HMAC chuẩn, so sánh constant-time, ánh xạ key ID sang principal và kiểm tra authorization riêng.
- Secret nhúng trong browser/mobile public client không thể được xem là bí mật lâu dài; chọn BFF, OAuth/PKCE, mTLS hoặc cơ chế thích hợp.
- Rotation, revocation, audit và incident response là phần bắt buộc của vòng đời shared secret.

Một thiết kế HMAC request authentication an toàn không chỉ tạo được chữ ký đúng. Nó phải biết **ai đang giữ khóa, request nào được ký, dữ liệu nào được bảo vệ, request có mới không, principal được làm gì và secret sẽ được thay thế hoặc thu hồi ra sao**.
