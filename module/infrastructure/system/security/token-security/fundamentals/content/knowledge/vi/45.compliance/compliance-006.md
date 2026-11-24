# Pseudonymous subject

## Mục tiêu

Token bảo mật cần nhận diện chủ thể để API áp dụng quyền truy cập, ghi nhận hành động và liên kết request trong một phạm vi được phép. Tuy nhiên, đưa email, số điện thoại hoặc mã khách hàng trực tiếp vào token làm tăng lượng dữ liệu cá nhân xuất hiện trong log, trace, cache, hệ thống phân tích và các dịch vụ nhận token.

**Pseudonymous subject** là cách biểu diễn chủ thể bằng một định danh giả danh, thường là chuỗi opaque không trực tiếp tiết lộ danh tính thật. Định danh này giúp hệ thống nhận biết cùng một chủ thể trong phạm vi được thiết kế, đồng thời giảm việc chia sẻ dữ liệu định danh trực tiếp giữa các thành phần.

Sau bài này, bạn có thể:

- Giải thích vai trò của claim `sub` và quan hệ với `iss` trong JWT/OIDC.
- Phân biệt subject công khai (public) và subject theo cặp (pairwise) trong OpenID Connect.
- Thiết kế subject ổn định, không chứa PII và có phạm vi sử dụng rõ ràng.
- Phân biệt pseudonymization với anonymization và hiểu giới hạn tuân thủ.
- Tránh liên kết chéo người dùng giữa tenant, client hoặc mục đích xử lý.
- Bảo vệ bảng ánh xạ, khóa HMAC, log, metric, trace và dữ liệu kiểm toán.
- Xây dựng kiểm thử cho tính ổn định, không va chạm, giới hạn phạm vi và quyền riêng tư của subject.

## 1. Vì sao subject nên là định danh giả danh?

Một JWT có thể chứa claim `sub` để xác định chủ thể mà token đại diện. Nếu hệ thống đặt trực tiếp email vào `sub`, mọi resource server, log collector hoặc công cụ quan sát nhận được token đều có thể đọc email đó. JWT thường chỉ được mã hóa Base64URL và ký; chữ ký không che giấu nội dung payload.

Ví dụ không nên dùng:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "nguyen.van.a@example.test",
  "aud": "orders-api",
  "scope": "orders:read"
}
~~~

Một thiết kế tốt hơn dùng subject opaque:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "usr_7f91d2a4c8e64b1a",
  "aud": "orders-api",
  "scope": "orders:read"
}
~~~

Giá trị subject giả danh không tự tiết lộ email hay tên người dùng. Resource server dùng subject này để tìm quan hệ quyền hoặc dữ liệu trong phạm vi được cấp phép.

Tuy vậy, subject giả danh vẫn có thể liên kết các hoạt động của cùng một người. Nếu có bảng ánh xạ từ subject sang tài khoản thật, hoặc có dữ liệu phụ trợ giúp tái nhận diện, subject vẫn là dữ liệu có khả năng liên quan đến một cá nhân. **Pseudonymization làm giảm khả năng nhận diện trực tiếp; nó không tự biến dữ liệu thành dữ liệu vô danh.**

### Subject trả lời câu hỏi nào?

| Thành phần | Vai trò | Không nên hiểu là |
| --- | --- | --- |
| `sub` | Định danh chủ thể trong phạm vi issuer/profile xác định | Email, username hoặc ID toàn cục bắt buộc |
| `iss` | Định danh nhà phát hành | Tenant ID |
| `aud` | Resource server/bên nhận token | Subject hoặc client đang đăng nhập |
| `client_id` / `azp` | Định danh ứng dụng client theo profile | Subject của người dùng |
| `tenant_id` / `tid` | Ngữ cảnh tenant nếu nhà phát hành định nghĩa | Thay thế `sub` |
| `scope` / `roles` | Quyền hoặc phạm vi được cấp | Danh tính của chủ thể |

Trong hệ thống có nhiều issuer, không dùng `sub` đơn lẻ làm khóa toàn cục. Cặp `(iss, sub)` mới xác định subject trong không gian định danh của nhà phát hành. Hai issuer khác nhau có thể phát hành cùng chuỗi `sub` cho hai người khác nhau.

## 2. Public subject và pairwise subject trong OIDC

OpenID Connect định nghĩa hai loại subject identifier quan trọng:

- **Public subject:** cùng một người dùng có cùng `sub` khi đăng nhập qua các client thuộc cùng issuer.
- **Pairwise subject:** cùng một người dùng nhận subject khác nhau cho các client thuộc các sector khác nhau. Điều này giảm khả năng các client tự liên kết hoạt động của người dùng với nhau.

Ví dụ:

| Người dùng thật | Client / sector | Subject |
| --- | --- | --- |
| Tài khoản A | `shop.example.test` | `p_91a0...` |
| Tài khoản A | `support.example.test` | `p_4c82...` |
| Tài khoản A | `billing.example.test` | `p_7e10...` |

Các ứng dụng trên có thể cùng xác thực một tài khoản, nhưng không thể chỉ so sánh `sub` để biết đó là cùng một người nếu nhà cung cấp dùng pairwise subject. Việc liên kết giữa các ứng dụng cần một cơ chế có thẩm quyền và mục đích được phép, chẳng hạn backend identity service với kiểm soát truy cập phù hợp.

### Sector identifier

Trong OIDC, pairwise subject được tính theo sector identifier. Với web client, sector thường được xác định từ host của redirect URI đã đăng ký; client có thể dùng `sector_identifier_uri` theo quy tắc của OIDC để nhóm các redirect URI. Các client thuộc cùng sector có thể nhận cùng pairwise subject cho một người dùng, còn client ở sector khác nhận giá trị khác.

Không tự coi hostname của tenant, API audience hoặc `client_id` là sector identifier nếu cấu hình OIDC không quy định như vậy. Cần kiểm tra chính xác cách Identity Provider triển khai public/pairwise subject và sector.

### Vì sao pairwise hữu ích?

Pairwise subject hạn chế khả năng các bên nhận token tự ghép hồ sơ người dùng từ nhiều ứng dụng. Ví dụ, hệ thống cửa hàng và hệ thống hỗ trợ có thể không cần biết cùng một người dùng đang sử dụng cả hai dịch vụ. Nếu cả hai nhận một `sub` toàn cục, việc liên kết dữ liệu trở nên dễ dàng hơn mức cần thiết.

Pairwise subject không ngăn mọi hình thức liên kết. Các thuộc tính khác như email, số điện thoại, địa chỉ IP, thiết bị, thời gian hoạt động hoặc claim tùy chỉnh vẫn có thể làm lộ mối liên hệ. Privacy review cần xem toàn bộ payload và dữ liệu quan sát, không chỉ riêng `sub`.

## 3. Thiết kế pseudonymous subject cho access token

Một subject tốt cần có các đặc tính:

1. **Opaque:** không chứa email, tên, số điện thoại, mã nhân viên hoặc ID có thể đoán ra.
2. **Ổn định trong phạm vi cần thiết:** cùng một chủ thể nhận cùng subject trong cùng issuer/purpose/sector nếu hợp đồng yêu cầu tính ổn định.
3. **Có phạm vi:** không tái sử dụng một subject toàn cục cho mọi tenant, client và mục đích nếu không cần liên kết.
4. **Không tái sử dụng:** khi tài khoản bị xóa hoặc subject bị ngừng, không gán lại giá trị đó cho người khác.
5. **Không thể suy đoán dễ dàng:** tránh số thứ tự tăng dần, hash email thuần hoặc phép mã hóa có thể đảo ngược bằng khóa phổ biến.
6. **Được phát hành từ nguồn tin cậy:** resource server chỉ sử dụng subject sau khi xác minh token, issuer và audience.
7. **Không thay đổi tùy tiện:** đổi subject có thể phá vỡ quan hệ dữ liệu, audit và quyền đã gắn với subject cũ.

Ví dụ một API nội bộ có thể lưu quan hệ:

~~~text
(issuer_alias, subject, tenant_id) -> internal_principal_id
~~~

Khóa quan hệ phải phản ánh đúng mô hình định danh. Nếu `sub` là pairwise theo client, backend cần biết issuer và ngữ cảnh sector/client theo hợp đồng trước khi tra cứu. Không được xóa các thành phần phạm vi rồi chỉ dùng `sub` làm khóa.

### Subject trong access token và ID token

ID token OIDC xác nhận danh tính đăng nhập cho client; `sub` trong ID token là định danh subject theo issuer và subject type. Access token dành cho resource server và có thể mang `sub` theo profile/nhà phát hành tương ứng.

Không giả định `sub` trong mọi access token luôn bằng `sub` trong ID token, đặc biệt khi có token exchange, delegation, service account hoặc profile riêng. Hãy tuân theo hợp đồng của authorization server. Resource server không nên tự suy ra người dùng từ `client_id` khi token đại diện cho một ứng dụng hoặc service principal.

## 4. Các cách tạo subject giả danh

### Cách A — Định danh ngẫu nhiên và bảng ánh xạ

Identity service tạo một giá trị ngẫu nhiên đủ mạnh, ví dụ UUID ngẫu nhiên hoặc chuỗi ngẫu nhiên dài, rồi lưu ánh xạ:

~~~text
principal_id (internal) | issuer | sector | pseudonymous_sub
------------------------|--------|--------|-----------------
P-10042                 | idp-1  | shop   | p_a83f...
P-10042                 | idp-1  | support| p_71c2...
~~~

Ưu điểm:

- Không để lộ cấu trúc ID nội bộ.
- Có thể tạo pairwise subject khác nhau cho từng sector.
- Có thể thu hồi hoặc thay đổi mapping có kiểm soát.
- Dễ quản lý vòng đời và xử lý tài khoản hợp nhất/tách.

Nhược điểm:

- Cần lưu trữ mapping và bảo vệ dữ liệu.
- Phải xử lý transaction, backup, khôi phục và đồng bộ khi cấp subject.
- Bảng mapping trở thành tài sản nhạy cảm vì có thể liên kết pseudonym với danh tính thật.

Đây thường là lựa chọn dễ quản trị khi hệ thống cần pairwise subject, hỗ trợ nhiều issuer/tenant hoặc có quy trình thay đổi định danh phức tạp.

### Cách B — HMAC theo phạm vi

Có thể tạo pseudonym xác định bằng HMAC với khóa bí mật phía server:

~~~text
subject = base64url(
    HMAC-SHA-256(
        K_scope,
        issuer || 0x00 || sector || 0x00 || internal_subject
    )
)
~~~

Trong đó:

- `K_scope` là khóa bí mật được quản lý an toàn và tách theo phạm vi hoặc phiên bản.
- `issuer` và `sector` ngăn cùng một ID nội bộ tạo ra cùng pseudonym ở các phạm vi khác nhau.
- `internal_subject` là định danh nội bộ ổn định, không phải dữ liệu do client tùy ý gửi.
- Kết quả chỉ được phát hành qua identity service; không gửi khóa HMAC đến resource server.

HMAC giúp chống đoán giá trị nếu khóa đủ mạnh và được bảo vệ. Nhưng HMAC không mã hóa dữ liệu gốc và không cung cấp khả năng giải mã ngược. Nếu cần tra cứu principal từ subject, hệ thống phải có mapping hoặc tính toán lại khi biết principal và key.

Không dùng SHA-256 trực tiếp trên email hoặc số điện thoại. Các giá trị này có entropy thấp và có thể bị dò bằng từ điển; salt công khai cũng không ngăn việc dò từng giá trị phổ biến. HMAC với secret quản lý phía server tốt hơn cho pseudonym ổn định, nhưng vẫn cần phân tích khả năng liên kết và quản trị khóa.

### So sánh lựa chọn

| Tiêu chí | Random + mapping | HMAC scoped |
| --- | --- | --- |
| Tạo pairwise subject | Tự nhiên qua mapping theo sector | Cần đưa sector vào đầu vào HMAC |
| Tra ngược về principal | Có qua bảng mapping được bảo vệ | Cần mapping hoặc tính lại với key và principal |
| Đổi subject | Có thể cấp giá trị mới và quản lý alias | Đổi key/scope làm thay đổi kết quả |
| Phụ thuộc storage | Cao hơn | Có thể thấp hơn khi chỉ cần tái tính |
| Quản trị khóa | Không cần khóa tạo pseudonym, nhưng mapping cần bảo vệ | Cần secret, rotation và versioning |
| Xử lý merge/split tài khoản | Linh hoạt qua mapping | Cần quy tắc và mapping bổ sung |
| Rủi ro liên kết | Nếu dùng chung mapping/ID ở nhiều nơi | Nếu dùng cùng key và cùng input trên nhiều phạm vi |

Không có cách nào tự động đáp ứng mọi yêu cầu. Chọn theo mục đích, khả năng vận hành, phạm vi liên kết cần thiết và yêu cầu pháp lý.

## 5. Pseudonymization không phải anonymization

Pseudonymization thay thế thông tin nhận diện trực tiếp bằng một định danh khác. Nếu có thông tin bổ sung hoặc khóa để liên kết lại với cá nhân, dữ liệu vẫn có thể được tái nhận diện.

Ví dụ:

- `sub = p_a83f...` không nói trực tiếp người dùng là ai.
- Bảng mapping `p_a83f... → account 10042` có thể xác định người dùng.
- Một tập log chứa subject, IP, thời gian và hành vi chi tiết có thể cho phép suy ra danh tính ngay cả khi không có mapping.
- Nếu cùng pseudonym được dùng ở nhiều dịch vụ, các dịch vụ có thể liên kết lịch sử hoạt động.

Vì vậy, pseudonymous subject là một **biện pháp bảo vệ dữ liệu**, không phải lý do để bỏ qua nghĩa vụ bảo vệ dữ liệu cá nhân.

### Các nguyên tắc compliance cần áp dụng

Tùy luật và vai trò tổ chức, cần đánh giá các nguyên tắc như:

- **Data minimization:** chỉ đưa claim cần thiết vào token.
- **Purpose limitation:** dùng subject đúng mục đích đã xác định; không tái sử dụng để theo dõi hoạt động ngoài mục đích.
- **Storage limitation:** đặt thời hạn lưu giữ mapping, event, log và dữ liệu liên kết.
- **Integrity and confidentiality:** giới hạn truy cập, mã hóa dữ liệu lưu trữ và bảo vệ khóa.
- **Accountability:** lưu hồ sơ về thiết kế, mục đích, người truy cập mapping và quyết định thay đổi.
- **Privacy by design/default:** mặc định không chia sẻ định danh trực tiếp và không bật liên kết chéo nếu không cần.

Theo GDPR, pseudonymized data vẫn có thể là personal data khi có thể quy về một cá nhân bằng thông tin bổ sung. Tổ chức cần đánh giá căn cứ xử lý, vai trò controller/processor, nghĩa vụ thông báo, quyền của chủ thể dữ liệu và yêu cầu đánh giá tác động khi áp dụng. Các quy định cụ thể phải được đối chiếu với pháp luật áp dụng và tư vấn pháp lý của tổ chức; không suy luận rằng chỉ đổi email thành một chuỗi ngẫu nhiên là đã tuân thủ.

## 6. Bảo vệ bảng mapping và khóa pseudonym

Nếu hệ thống có mapping từ pseudonymous subject sang internal principal, đây là dữ liệu có độ nhạy cao.

Các biện pháp:

1. **Tách quyền:** resource server thông thường chỉ cần subject đã xác thực; không cần quyền đọc mapping toàn cục.
2. **Least privilege:** chỉ identity service hoặc quy trình nghiệp vụ được phê duyệt mới có thể tra mapping.
3. **Mã hóa khi lưu:** bảo vệ database, backup, snapshot và bản export.
4. **Audit access:** ghi nhận ai truy cập mapping, mục đích, thời điểm và kết quả; không log dữ liệu nhạy cảm không cần thiết.
5. **Tách môi trường:** key và mapping của development, staging, production không dùng chung.
6. **Bảo vệ khóa HMAC:** lưu trong KMS/HSM hoặc secret manager phù hợp; hạn chế quyền sử dụng và rotation.
7. **Không đưa mapping vào token:** token chỉ mang pseudonymous subject; không mang internal principal ID hoặc bảng liên kết.
8. **Retention có chủ đích:** xóa hoặc hạn chế mapping khi hết mục đích, đồng thời xử lý các yêu cầu lưu trữ bắt buộc và audit theo chính sách.

### Quản lý HMAC key rotation

Nếu subject được tính trực tiếp từ HMAC, thay khóa sẽ tạo pseudonym mới. Có thể quản lý phiên bản khóa:

~~~text
subject format: ps_v2_<base64url-hmac>
key version: v2
scope: issuer + sector
~~~

Tuy nhiên, không nên tự ý chuyển subject của tất cả người dùng ngay khi xoay khóa. Cần xác định:

- Có cần giữ khả năng tra cứu subject cũ trong thời gian chuyển tiếp không?
- Có thể tính subject mới từ principal nội bộ không?
- Token cũ còn hiệu lực bao lâu?
- Database và cache có hỗ trợ alias cũ/mới không?
- Các hệ thống audit có cần giữ subject cũ để tra cứu lịch sử không?
- Có rủi ro hai phiên bản key cùng tạo ra mapping không nhất quán không?

Một phương án là lưu mapping giữa principal, sector và subject version; phát hành subject mới cho token mới, chấp nhận subject cũ trong khoảng chuyển đổi có giới hạn, rồi loại bỏ theo kế hoạch. Việc giữ alias phải có mục đích và thời hạn, không biến thành liên kết vĩnh viễn không kiểm soát.

## 7. Dùng subject trong authorization và multi-tenant

Subject giả danh xác định chủ thể trong phạm vi issuer; nó không tự xác định tenant hoặc quyền trên dữ liệu.

Một quyết định truy cập có thể cần các yếu tố:

~~~text
verified issuer
+ verified subject
+ authenticated tenant context
+ resource ownership / membership
+ scope or role
+ requested action
~~~

Ví dụ API nhận token đã xác minh:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "p_7f91d2a4c8e64b1a",
  "aud": ["orders-api"],
  "tenant_id": "tenant-acme",
  "scope": "orders:read"
}
~~~

API cần kiểm tra:

- Chữ ký, issuer, audience, thời gian và token profile hợp lệ.
- `sub` được diễn giải trong namespace của `iss`.
- `tenant_id` (nếu có) được issuer tin cậy phát hành và đúng policy; hoặc tenant được xác định qua membership server-side.
- Chủ thể có quyền `orders:read` trong tenant đó.
- Truy vấn dữ liệu được ràng buộc bằng tenant context đã xác thực.

Không dùng subject làm tenant ID. Không dùng tenant ID để thay subject. Không giả định một người dùng chỉ thuộc một tenant. Nếu cùng người dùng có nhiều tenant membership, policy phải xác định tenant đang hoạt động cho từng request.

### Tránh liên kết subject giữa các issuer

Hai issuer có thể cấp cùng `sub`, hoặc một issuer có thể cấp subject theo pairwise sector. Khóa dữ liệu nên chứa namespace:

~~~text
principal_key = (issuer_id, subject_type, subject_value)
~~~

Nếu cần liên kết tài khoản giữa hai issuer, hãy thực hiện qua quy trình account linking được xác thực, có sự đồng ý/căn cứ xử lý và audit phù hợp. Không tự ghép hai tài khoản vì email trùng nhau hoặc vì chuỗi `sub` giống nhau.

## 8. Bảo vệ subject trong log, metric và trace

Subject giả danh vẫn có thể theo dõi hành vi của một người theo thời gian. Vì vậy, không nên đưa `sub` vào mọi hệ thống telemetry một cách mặc định.

| Kênh | Khuyến nghị |
| --- | --- |
| Application log | Chỉ ghi khi cần điều tra; dùng tham chiếu có phạm vi và quyền truy cập hạn chế |
| Security audit event | Ghi pseudonymous subject hoặc reference cần thiết, issuer alias, action và outcome |
| Metrics | Không dùng `sub` làm label; dùng outcome, service, client class và enum giới hạn |
| Distributed trace | Không thêm `sub` vào span/baggage mặc định; dùng correlation ID ngẫu nhiên của request |
| Error response | Không trả subject, mapping hoặc thông tin tài khoản nội bộ cho client |
| Analytics | Ưu tiên dữ liệu tổng hợp; giới hạn khả năng liên kết chéo mục đích |

Nếu cần một mã correlation ổn định cho điều tra, tạo reference riêng cho mục đích audit thay vì tái sử dụng `sub` toàn cục. Reference này vẫn cần kiểm soát truy cập và retention. Không băm `sub` bằng SHA-256 rồi cho rằng kết quả đã vô danh; nếu input có thể đoán được, hash có thể bị dò và vẫn cho phép liên kết.

## 9. Ví dụ Java: tạo subject HMAC theo sector

Ví dụ dưới đây minh họa HMAC-SHA-256 với secret do hệ thống quản lý. Trong production, key phải lấy từ KMS/HSM hoặc secret manager, không hardcode trong source code, file cấu hình được commit hoặc token.

~~~java
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

final class PseudonymousSubjectFactory {

    private final SecretKey key;

    PseudonymousSubjectFactory(SecretKey key) {
        this.key = key;
    }

    String create(
        String issuer,
        String sector,
        String internalSubject
    ) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);

            String input = issuer + "\u0000"
                + sector + "\u0000"
                + internalSubject;

            byte[] digest = mac.doFinal(
                input.getBytes(StandardCharsets.UTF_8)
            );

            String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);

            return "ps_v1_" + encoded;
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot create pseudonymous subject", ex
            );
        }
    }
}
~~~

Byte `\u0000` phân tách các thành phần đầu vào để tránh nhập nhằng khi ghép chuỗi. Phiên bản `v1` giúp nhận biết quy tắc/key version. Giá trị `internalSubject` phải đến từ identity store đáng tin, không lấy từ request chưa xác thực.

Đoạn code không giải quyết việc quản lý key, mapping, rotation hoặc xóa dữ liệu. Nó chỉ minh họa phép tính. Nếu dùng pairwise subject theo OIDC, hãy tuân theo chuẩn và cấu hình sector của provider; không tự triển khai thuật toán rồi tuyên bố tương thích OIDC nếu chưa đáp ứng đầy đủ quy tắc.

## 10. Kiểm thử pseudonymous subject

Test cần chứng minh subject có tính ổn định trong phạm vi được thiết kế, khác nhau giữa các phạm vi cần tách và không tiết lộ PII.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Cùng issuer, sector và principal tạo subject hai lần | Kết quả ổn định |
| Cùng principal nhưng sector khác nhau | Subject khác nhau nếu policy pairwise yêu cầu |
| Cùng principal nhưng issuer khác nhau | Namespace/pseudonym không bị trộn |
| Principal khác nhau cùng sector | Subject khác nhau với xác suất va chạm không đáng kể |
| Subject không chứa email/tên/số điện thoại | Không lộ PII trực tiếp |
| Key version thay đổi | Subject mới được quản lý theo migration/alias policy |
| Token issuer không tin cậy | Không sử dụng `sub` để tra principal |
| Subject trùng nhưng issuer khác | Không coi là cùng principal |
| Client cố gửi `X-Subject` hoặc `X-User-Id` | Không ghi đè danh tính đã xác thực |
| Mapping service không truy cập được | Fail theo policy; không fallback sang email hoặc dữ liệu client tự gửi |

### Ví dụ unit test

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.crypto.spec.SecretKeySpec;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;

class PseudonymousSubjectFactoryTest {

    private PseudonymousSubjectFactory factory;

    @BeforeEach
    void setUp() {
        byte[] testKey = new byte[32];
        Arrays.fill(testKey, (byte) 0x5A);
        factory = new PseudonymousSubjectFactory(
            new SecretKeySpec(testKey, "HmacSHA256")
        );
    }

    @Test
    void isStableWithinSameScope() {
        String first = factory.create(
            "issuer-a", "shop.example.test", "principal-42"
        );
        String second = factory.create(
            "issuer-a", "shop.example.test", "principal-42"
        );

        assertEquals(first, second);
    }

    @Test
    void differsAcrossSectors() {
        String shop = factory.create(
            "issuer-a", "shop.example.test", "principal-42"
        );
        String support = factory.create(
            "issuer-a", "support.example.test", "principal-42"
        );

        assertNotEquals(shop, support);
    }

    @Test
    void doesNotContainInternalIdentifier() {
        String subject = factory.create(
            "issuer-a", "shop.example.test",
            "principal-42"
        );

        assertFalse(subject.contains("principal-42"));
    }
}
~~~

Test cuối chỉ minh họa rằng output không chứa chuỗi đầu vào trực tiếp; nó không chứng minh output không thể bị tái nhận diện hoặc không thể liên kết. Bộ test production cần dùng key fixture riêng, kiểm tra mapping authorization, key rotation, access control và log/metric leakage. Không dùng dữ liệu cá nhân thật trong test.

### Kiểm thử log và telemetry

- Capture log trong test khi refresh/access token được xác minh; kiểm tra không có token nguyên văn.
- Kiểm tra metric registry không có tag `sub`, email, `user_id` hoặc family ID.
- Kiểm tra trace exporter không nhận raw token hoặc subject toàn cục ngoài policy.
- Kiểm tra audit event chỉ có trường được phê duyệt và reference đúng phạm vi.
- Kiểm tra subject của issuer A không bị tra cứu bằng namespace issuer B.
- Kiểm tra mapping service yêu cầu quyền phù hợp và ghi audit cho truy cập nhạy cảm.

## 11. Vòng đời tài khoản và subject

Subject cần được quản lý xuyên suốt vòng đời tài khoản:

- **Tạo tài khoản:** cấp subject ổn định theo issuer/sector và lưu mapping nếu cần.
- **Đổi email/tên:** không thay subject chỉ vì thuộc tính hồ sơ thay đổi.
- **Đổi tenant hoặc sector:** xác định có cần subject mới hay không theo phạm vi và mục đích.
- **Hợp nhất tài khoản:** dùng quy trình account linking; không tự thay subject cũ bằng subject của tài khoản khác mà không migration/audit.
- **Khóa tài khoản:** vô hiệu hóa phiên/token theo policy; subject không trở thành quyền truy cập.
- **Xóa tài khoản:** xử lý mapping, token, log và dữ liệu còn lưu theo retention/legal hold; không tái sử dụng subject cho người khác.
- **Khôi phục tài khoản:** xác minh chủ thể và quyết định giữ hay cấp lại subject theo policy; không dựa vào email cũ làm bằng chứng duy nhất.

Nếu subject bị thay đổi, token cũ có thể vẫn còn hiệu lực trong thời hạn của nó. Cần thu hồi phiên hoặc token phù hợp, cập nhật cache và quan hệ quyền để tránh hai subject cùng đại diện cho một principal trong khoảng chuyển tiếp không kiểm soát.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đặt email vào `sub` | PII xuất hiện ở mọi nơi nhận token | Dùng subject opaque |
| Dùng `sub` mà bỏ `iss` | Đụng định danh giữa các issuer | Khóa theo `(iss, sub)` |
| Dùng một subject toàn cục cho mọi client | Các bên dễ liên kết hoạt động | Cân nhắc pairwise subject |
| Hash email thuần | Có thể dò bằng từ điển | HMAC với secret hoặc random mapping |
| Cho rằng pseudonym là anonymous | Đánh giá sai nghĩa vụ bảo vệ dữ liệu | Đánh giá khả năng tái nhận diện và dữ liệu phụ trợ |
| Dùng subject làm tenant ID | Sai ranh giới định danh và dữ liệu | Tách subject, tenant và authorization |
| Ghi `sub` vào mọi metric label | Cardinality cao và theo dõi người dùng | Metric chỉ dùng nhãn enum |
| Cho resource server đọc mapping toàn cục | Tăng nguy cơ tái nhận diện | Tách service và least privilege |
| Xoay HMAC key không có kế hoạch | Subject đổi hàng loạt, mất liên kết dữ liệu | Versioning, migration và alias có thời hạn |
| Tái sử dụng subject sau khi xóa tài khoản | Audit và tham chiếu lịch sử bị nhập nhằng | Không tái sử dụng subject |
| Tin `sub` từ request/header | Client có thể giả mạo danh tính | Chỉ lấy từ token đã xác minh |

## 13. Checklist thiết kế và compliance

- [ ] `sub` không chứa PII trực tiếp hoặc ID nội bộ có thể suy đoán.
- [ ] Subject được diễn giải cùng namespace `iss`.
- [ ] Public/pairwise subject được chọn theo nhu cầu liên kết thực tế.
- [ ] Sector identifier được cấu hình đúng theo OIDC provider.
- [ ] Subject ổn định trong phạm vi cần thiết và không tái sử dụng.
- [ ] Pseudonymization không bị hiểu nhầm là anonymization.
- [ ] Có mục đích xử lý, căn cứ và thời hạn lưu trữ rõ ràng.
- [ ] Mapping và HMAC key được bảo vệ, tách quyền và audit.
- [ ] Không phát hành internal principal ID hoặc mapping vào token.
- [ ] Tenant, subject, audience và scope được kiểm tra riêng.
- [ ] Log, metric và trace không chứa token hoặc định danh không cần thiết.
- [ ] Có quy trình key rotation, account linking, account deletion và subject migration.
- [ ] Có test ổn định, pairwise scope, namespace issuer và chống rò rỉ PII.
- [ ] Có quy trình xử lý yêu cầu của chủ thể dữ liệu và sự cố lộ mapping.

## Ghi nhớ

- `sub` là định danh subject trong phạm vi issuer; luôn xét cùng `iss`.
- Pairwise subject giúp hạn chế liên kết người dùng giữa các sector/client, nhưng không ngăn mọi hình thức suy luận danh tính.
- Pseudonymization giảm nhận diện trực tiếp; dữ liệu vẫn có thể là dữ liệu cá nhân nếu có thể tái nhận diện.
- Random mapping và HMAC scoped là hai cách phổ biến, mỗi cách có yêu cầu vận hành riêng.
- Không dùng email hash thuần, raw subject làm metric label hoặc mapping toàn cục không kiểm soát.
- Subject không thay thế tenant context, scope, role hoặc authorization.
- Quyền truy cập mapping và khóa pseudonym phải được bảo vệ như tài sản nhạy cảm.

### Tiêu chuẩn tham khảo

- **OpenID Connect Core 1.0:** Subject Identifier Types, public và pairwise subject identifiers.
- **RFC 7519 — JSON Web Token:** claim `sub` và `iss`.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** subject và các claim trong JWT access token.
- **GDPR, Article 4(5):** khái niệm pseudonymisation và thông tin bổ sung cần được giữ riêng.
- **GDPR, Article 25 và 32:** data protection by design/default và bảo mật xử lý.
- **NIST Privacy Framework:** quản trị rủi ro quyền riêng tư trong vòng đời dữ liệu.
