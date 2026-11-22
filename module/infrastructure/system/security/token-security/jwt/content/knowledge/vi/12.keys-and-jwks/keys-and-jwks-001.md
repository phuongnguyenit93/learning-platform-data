# Vòng đời khóa từ sinh, phân phối đến ngừng sử dụng

Trong hệ thống sử dụng **JSON Web Token (JWT)**, một token có chữ ký hợp lệ chỉ đáng tin khi khóa dùng để xác minh thuộc về đúng bên phát hành, được phép dùng cho đúng thuật toán, và vẫn nằm trong chính sách tin cậy tại thời điểm kiểm tra. Vì vậy, bảo vệ JWT không chỉ là chọn thuật toán ký: hệ thống phải quản lý **toàn bộ vòng đời khóa** từ khi tạo, lưu trữ, phân phối, sử dụng, luân chuyển, thu hồi đến hủy.

Bài này thuộc chủ đề **Security - JSON Web Token (JWT)**, chương **Khóa và JWKS**, áp dụng cho các hệ thống xác thực/phân quyền nói chung, độc lập với ngôn ngữ lập trình và framework.

## 1. Vì sao vòng đời khóa quyết định độ tin cậy của JWT?

JWT thường được biểu diễn dưới dạng `header.payload.signature`. Với JWT có chữ ký (JWS), phần chữ ký giúp bên nhận phát hiện nội dung bị sửa và xác minh token được ký bởi bên nắm khóa tương ứng. Chữ ký **không mã hóa** payload: bất kỳ ai có token thường có thể giải mã Base64url để đọc claims. Muốn bảo mật nội dung phải có cơ chế thích hợp khác (ví dụ JWE), không thể chỉ dựa vào chữ ký.

Các tình huống dưới đây minh họa vì sao khóa phải được quản trị theo vòng đời:

- **Khóa bí mật bị lộ:** kẻ tấn công có thể ký token giả nếu còn hệ thống tin khóa đó, kể cả khi mã nguồn xác minh chữ ký đúng.
- **Khóa công khai được phân phối sai:** bên xác minh có thể chấp nhận khóa do kẻ tấn công đưa vào, dẫn đến tin token giả.
- **Đổi khóa mà không phối hợp:** token còn hạn được ký bằng khóa cũ đột nhiên bị từ chối; hoặc token bằng khóa mới chưa được các bên xác minh nhận diện.
- **Không thu hồi khóa đã mất an toàn:** token do khóa bị lộ ký vẫn được chấp nhận đến khi hệ thống cập nhật chính sách hoặc bộ nhớ đệm.
- **Giữ khóa cũ quá lâu:** bề mặt tấn công và phạm vi truy cập tồn dư tăng không cần thiết.

Điểm cốt lõi: **vòng đời khóa** và **vòng đời token** liên quan nhau nhưng không đồng nhất. Khóa có thể ký nhiều token; một token có thể hết hạn trước hoặc sau thời điểm khóa ngừng ký. Xác minh chữ ký chỉ là một bước trong việc chấp nhận JWT, bên nhận còn phải kiểm tra các claims như `iss`, `aud`, `exp`, `nbf` và quyền hạn theo ngữ cảnh.

## 2. Khóa, JWK, JWKS và các vai trò

| Khái niệm | Ý nghĩa | Lưu ý bảo mật |
| --- | --- | --- |
| **Khóa đối xứng** | Một bí mật chung dùng cho cả ký và xác minh, thường với họ HMAC (`HS256`, `HS384`, `HS512`). | Mỗi bên được phép xác minh đồng thời có khả năng tạo chữ ký; không công bố bí mật này qua JWKS công khai. |
| **Khóa bất đối xứng** | Cặp khóa riêng/khóa công khai; bên phát hành ký bằng private key, bên nhận xác minh bằng public key. | Private key chỉ nằm trong vùng tin cậy của bên ký; public key có thể phân phối rộng. |
| **JWK (JSON Web Key)** | Cách biểu diễn một khóa bằng đối tượng JSON, gồm các thuộc tính như `kty`, `kid` và tham số khóa. | Một JWK có thể chứa vật liệu bí mật; **không phải JWK nào cũng được phép xuất bản**. |
| **JWKS (JSON Web Key Set)** | Đối tượng JSON chứa mảng `keys` gồm nhiều JWK; thường dùng để công bố **các khóa công khai** cho bên xác minh. | Đường dẫn JWKS phải nằm trong cấu hình tin cậy của issuer; JWKS không tự chứng minh nguồn gốc của chính nó. |
| **`kid` (Key ID)** | Định danh giúp chọn khóa tương ứng với chữ ký JWT. | Chỉ là gợi ý tra cứu trong tập khóa đã tin cậy; không phải bằng chứng xác thực. |
| **Bên phát hành (issuer)** | Tạo token, quản lý khóa ký và thông báo khóa xác minh. | Quyết định khi nào bắt đầu/dừng ký bằng từng khóa. |
| **Bên xác minh (verifier)** | Nhận token, tìm khóa phù hợp và kiểm tra chữ ký cùng claims. | Phải tự kiểm soát nguồn khóa, thuật toán cho phép và chính sách token. |

Với kiến trúc nhiều dịch vụ, ký và xác minh thường tách vai trò: một dịch vụ định danh ký bằng private key, nhiều API xác minh bằng public key được lấy qua JWKS. Đây là một lợi ích thực tế của chữ ký bất đối xứng: API không cần giữ bí mật có khả năng tạo token.

> **Ranh giới tin cậy:** Nguồn khóa phải được cấu hình hoặc khám phá từ metadata của issuer đã tin cậy qua kênh bảo mật. Không được lấy một URL tùy ý do JWT tự khai báo rồi coi khóa ở URL đó là đáng tin.

## 3. Mô hình trạng thái vòng đời khóa

~~~mermaid
flowchart LR
    A["Sinh khóa"] --> B["Lưu trữ và đăng ký"]
    B --> C["Phân phối / công bố để xác minh"]
    C --> D["Ký đang hoạt động"]
    D --> E["Ngừng ký, còn xác minh"]
    E --> F["Ngừng tin cậy / rút khỏi phân phối"]
    F --> G["Hủy vật liệu bí mật"]
    D -. "Bị lộ hoặc nghi bị lộ" .-> X["Thu hồi khẩn cấp"]
    E -. "Bị lộ hoặc nghi bị lộ" .-> X
    X --> F
~~~

Tên trạng thái là một mô hình quản trị gợi ý, không phải các trường bắt buộc của chuẩn JWT:

| Trạng thái | Được tạo JWT mới? | Bên xác minh có thể tin JWT cũ? | Điều kiện chuyển tiếp |
| --- | --- | --- | --- |
| **Generated / Registered** | Chưa | Chưa, nếu chưa phân phối khóa xác minh | Khóa được sinh đúng chuẩn, bảo vệ và đăng ký metadata. |
| **Published / Staged** | Chưa | Có thể xác minh chữ ký bằng public key, nhưng chính sách token vẫn quyết định việc chấp nhận | Các bên nhận đã có thể tải/nhận khóa mới. |
| **Active signing** | Có | Có, nếu token và khóa hợp lệ | Chỉ một hoặc số lượng khóa ký được kiểm soát rõ cho từng issuer/purpose. |
| **Verify-only** | Không | Có, trong thời gian chuyển tiếp đã định | Đã chuyển việc ký sang khóa mới nhưng token cũ còn hạn. |
| **Revoked / Untrusted** | Không | Không | Khóa bị lộ, bị dùng sai, hoặc bị chấm dứt tin cậy. |
| **Destroyed** | Không | Không, trừ bản ghi kiểm toán vô hại | Vật liệu bí mật đã bị hủy theo chính sách lưu giữ và sao lưu. |

**Thu hồi khẩn cấp khác với nghỉ hưu theo lịch.** Khi khóa được thay bình thường, thường cần một giai đoạn chỉ xác minh để token cũ còn hạn tiếp tục hoạt động. Khi private key bị lộ, kéo dài thời gian xác minh có thể cho phép token giả được chấp nhận; vì vậy phải ưu tiên ngừng tin cậy khóa bị lộ và chấp nhận việc một số phiên hợp lệ phải đăng nhập lại.

## 4. Giai đoạn 1 — Sinh khóa an toàn

### 4.1. Chọn loại khóa và thuật toán

Quyết định dựa vào mô hình tin cậy, khả năng tương thích giữa issuer và verifier, chính sách mã hóa của tổ chức, và hỗ trợ thực tế của hệ thống.

| Họ thuật toán JWS | Kiểu khóa | Ví dụ cấu hình | Điểm cần xét |
| --- | --- | --- | --- |
| HMAC | Bí mật đối xứng (`oct`) | `HS256` với bí mật được sinh ngẫu nhiên, đủ độ dài | Phù hợp khi một miền tin cậy kiểm soát toàn bộ bên ký và xác minh; rò rỉ tại verifier đồng nghĩa mất bí mật ký. |
| RSA PKCS#1 v1.5 | Cặp RSA | `RS256`, thường dùng RSA ít nhất 2048 bit theo chính sách hiện hành | Tương thích rộng; kích thước chữ ký/khóa lớn hơn một số lựa chọn khác. |
| RSA-PSS | Cặp RSA | `PS256` | Đảm bảo các bên đều hỗ trợ trước khi chuyển đổi thuật toán. |
| ECDSA | Cặp EC | `ES256` với đường cong P-256 | Khóa/chữ ký gọn; cần triển khai thư viện mật mã và quản lý nonce đúng chuẩn. |
| EdDSA | Cặp OKP | Ed25519, khi được các bên hỗ trợ | Thiết kế hiện đại; cần kiểm tra hỗ trợ thuật toán và profile áp dụng. |

Không chọn thuật toán chỉ vì tên gọi có vẻ mạnh. **Issuer và verifier phải thống nhất danh sách thuật toán cho phép từ cấu hình đáng tin**; không tự đổi kiểu khóa theo `alg` do token không đáng tin gửi đến. Không chấp nhận `alg: "none"` trong luồng yêu cầu token có chữ ký.

### 4.2. Nguyên tắc khi sinh khóa

1. Dùng bộ sinh số ngẫu nhiên mật mã an toàn (CSPRNG), thư viện mật mã đã được đánh giá hoặc khả năng sinh khóa của HSM/KMS. Tránh sinh từ mật khẩu, thời gian, ID máy, UUID dự đoán được hoặc giá trị tự đặt.
2. Với `HS256`, bí mật cần có entropy đủ mạnh (thông thường tối thiểu 256 bit ngẫu nhiên cho mức an toàn tương ứng); không dùng chuỗi cấu hình dễ đoán làm secret.
3. Sinh cặp khóa bất đối xứng ngay trong HSM/KMS khi chính sách yêu cầu không xuất private key; cấp quyền sử dụng để ký theo nguyên tắc đặc quyền tối thiểu.
4. Gán định danh khóa mới **không trùng trong phạm vi issuer**, ví dụ `kid` là mã phiên bản ngẫu nhiên hoặc định danh sinh từ quy trình quản trị. Tránh tái sử dụng `kid` cho vật liệu khóa khác.
5. Ghi metadata **ngoài vật liệu bí mật**: issuer sở hữu, mục đích ký, thuật toán được phép, `kid`, thời điểm tạo, thời điểm kích hoạt/ngừng ký/ngừng xác minh, phiên bản, người hoặc quy trình phê duyệt.
6. Tách khóa theo mục đích và ranh giới tin cậy khi hợp lý: môi trường thử nghiệm và production, từng issuer, từng tenant hoặc từng loại token nhạy cảm. Một khóa dùng chung ở nhiều nơi làm tăng phạm vi ảnh hưởng nếu bị lộ.

**Ví dụ:** cùng một tổ chức phát hành access token và token cho thao tác đặc biệt. Nếu yêu cầu bảo mật và verifier khác nhau, có thể dùng hai nhóm khóa riêng. Khi một nhóm gặp sự cố, nhóm còn lại không tự động mất tin cậy.

## 5. Giai đoạn 2 — Bảo quản và kiểm soát quyền dùng khóa

Private key hoặc HMAC secret là tài sản nhạy cảm. Mục tiêu là giảm cả khả năng đánh cắp lẫn khả năng sử dụng trái phép.

- **Lưu trữ:** ưu tiên HSM, KMS, hệ thống quản lý secret hoặc kho khóa có mã hóa; hạn chế xuất private key ở dạng thô. Nếu ứng dụng bắt buộc giữ khóa trong bộ nhớ, phải giảm quyền tiến trình và thời gian tồn tại của bản sao.
- **Phân quyền:** bên ký chỉ có quyền ký với đúng khóa cần thiết. Bên xác minh bất đối xứng chỉ nhận public key; không cấp quyền truy cập private key để đơn giản hóa việc tích hợp.
- **Vận hành:** không đưa secret/private key vào repository, artifact build, ảnh container, log, thông báo lỗi, ticket hoặc telemetry. Quét lộ lọt secret và kiểm soát bản sao lưu.
- **Truy cập và kiểm toán:** theo dõi thao tác tạo, thay đổi trạng thái, gọi ký bất thường, thay đổi chính sách, xuất/khôi phục/sao lưu khóa; bảo vệ log khỏi chỉnh sửa.
- **Sao lưu và khôi phục:** xác định trước liệu khóa có được sao lưu hay không và ai có thể khôi phục. Bản sao lưu giữ vật liệu bí mật vẫn là phần của vòng đời: chỉ hủy khóa trong hệ thống chính là chưa đủ nếu còn bản sao được phép phục hồi.
- **Ranh giới thuật toán:** không tái sử dụng cùng vật liệu khóa cho nhiều thuật toán, giao thức hoặc mục đích độc lập khi không có thiết kế chứng minh an toàn rõ ràng.

Sử dụng HSM/KMS giúp giảm nguy cơ private key bị trích xuất nhưng **không tự loại bỏ** rủi ro: tài khoản hoặc dịch vụ có quyền gọi thao tác ký vẫn có thể bị lạm dụng. Vì thế cần giới hạn quyền, theo dõi và khả năng vô hiệu hóa khóa.

## 6. Giai đoạn 3 — Phân phối khóa và JWKS

### 6.1. Hai mô hình phân phối

**Chữ ký đối xứng:** issuer và verifier phải nhận cùng một secret qua kênh bảo mật riêng, ví dụ hệ thống quản lý secret và cơ chế cấp quyền. **Không công khai khóa `oct` trong JWKS.** Nếu phải cấp secret cho nhiều bên không cùng miền tin cậy, nên cân nhắc chuyển sang chữ ký bất đối xứng.

**Chữ ký bất đối xứng:** issuer giữ private key, công bố public key qua cấu hình được kiểm soát hoặc một endpoint JWKS sử dụng HTTPS. Metadata của issuer có thể quảng bá địa chỉ `jwks_uri`; verifier phải xác thực issuer và nguồn metadata trước khi tin địa chỉ đó.

### 6.2. Ví dụ một JWKS công khai

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-2026-b",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_NEW_RSA_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là dữ liệu **minh họa cấu trúc**, không phải các public key thật có thể dùng để xác minh. Trong JWK:

- `kty` mô tả loại khóa (`RSA`, `EC`, `OKP`, `oct`); các tham số như `n`/`e` của RSA hoặc `crv`/`x`/`y` của EC phụ thuộc vào `kty`.
- `kid` giúp xác định khóa được sử dụng trong một đợt ký. Tập JWKS có thể chứa cả public key cũ đang ở giai đoạn verify-only và public key mới được công bố trước.
- `use: "sig"` biểu thị mục đích chữ ký; `key_ops`, nếu được sử dụng, cũng phải phù hợp với thao tác cho phép. `alg` có thể giúp mô tả thuật toán dự kiến, nhưng **không thay thế** cấu hình allowlist của verifier.
- Với RSA JWK, các tham số private như `d`, `p`, `q`; với EC/OKP là `d`; với khóa đối xứng là `k` đều không được xuất hiện trong JWKS công khai.

JWKS **không chứa danh sách JWT đang có hiệu lực**, không tự thu hồi token, và cũng không mặc nhiên là chứng thư đảm bảo khóa đáng tin. Sự tin cậy đến từ cấu hình issuer, transport và chính sách xác minh.

### 6.3. Kiểm soát phía công bố và phía tiêu thụ JWKS

**Issuer/JWKS provider** cần:

- Phục vụ JWKS qua HTTPS với chứng chỉ hợp lệ; áp dụng kiểm soát thay đổi đối với nội dung và endpoint.
- Hỗ trợ nhiều public key đồng thời để chuyển khóa không gián đoạn.
- Công bố khóa mới trước khi bắt đầu ký; giữ khóa cũ đủ thời gian cho token hợp lệ còn tồn tại, trừ tình huống thu hồi khẩn cấp.
- Cấu hình caching hợp lý (`Cache-Control`, `ETag` khi có thể), theo dõi tính sẵn sàng và cảnh báo khi JWKS bị lỗi hay thay đổi bất thường.
- Đảm bảo không có vật liệu khóa bí mật, thông tin quản trị hoặc khóa thuộc môi trường/issuer khác bị công bố nhầm.

**Verifier/JWKS consumer** cần:

1. Gắn một cấu hình issuer đã tin cậy với đúng địa chỉ metadata/JWKS; không tin địa chỉ `jku` hoặc `x5u` tùy ý nằm trong header JWT vì có thể gây thay thế nguồn khóa hoặc SSRF.
2. Parse header để lấy `alg` và `kid` **chỉ cho mục đích chọn khóa dự kiến**, chưa xem header/payload là dữ liệu đã xác thực.
3. Chỉ tìm `kid` trong tập khóa của issuer tương ứng, xác minh `kty`, mục đích dùng khóa, thuật toán và các ràng buộc đã cấu hình; từ chối khóa mơ hồ/trùng `kid` hoặc không khớp.
4. Xác minh chữ ký bằng thư viện đáng tin, sau đó kiểm tra `iss`, `aud`, `exp`, `nbf`, các điều kiện nghiệp vụ và loại token. Header `alg` không thể buộc verifier chấp nhận thuật toán ngoài allowlist.
5. Dùng cache có TTL/giới hạn kích thước và cơ chế làm mới. Khi gặp `kid` chưa biết, có thể làm mới JWKS theo chính sách **có giới hạn tần suất**, tránh mỗi token lạ gây một request mạng. Lỗi lấy JWKS phải tuân thủ chính sách fail-closed phù hợp; không chuyển sang bỏ qua chữ ký.

Lưu ý: Không được lấy một RSA public key rồi dùng nó như bí mật HMAC chỉ vì header do attacker đặt `HS256`. Đây là dạng **algorithm/key confusion** mà thiết kế xác minh phải ngăn chặn.

## 7. Giai đoạn 4 — Ký và xác minh bằng khóa đang hoạt động

Khi phát hành JWT, issuer xác định **khóa ký active** cùng thuật toán theo cấu hình tin cậy, tạo header có `alg`/`kid` phù hợp, đưa các claims cần thiết vào payload rồi ký. Việc ký phải kiểm soát hạn sử dụng của token và thời điểm phát hành; token quá dài hạn khiến việc đổi khóa khó hơn.

Một quy trình khái niệm phía verifier:

~~~text
nhận jwt
  -> đọc header ở trạng thái CHƯA TIN CẬY
  -> chọn issuer/JWKS đã tin cậy theo cấu hình và ngữ cảnh nhận token
  -> từ chối alg không được phép; tìm kid trong phạm vi issuer
  -> kiểm tra loại khóa, mục đích và ràng buộc thuật toán
  -> xác minh chữ ký với public key / secret được phép
  -> kiểm tra iss, aud, exp, nbf, loại token và chính sách quyền
  -> chỉ khi tất cả PASS mới chấp nhận
~~~

Đặc biệt, với hệ thống có nhiều issuer hoặc tenant, nội dung `iss` đọc từ payload trước xác minh chỉ có thể hỗ trợ **tra cứu theo danh sách issuer đã cấu hình**, không được tự động cấp quyền tin cậy cho một issuer mới hoặc một JWKS ngoài danh sách.

Không có bảo đảm rằng JWT hợp lệ về mặt mật mã là đủ để cấp quyền cho một hành động. Cần kiểm tra đúng audience, token type, scopes/roles, điều kiện tài khoản, và giới hạn thời gian theo chính sách.

## 8. Giai đoạn 5 — Luân chuyển khóa theo kế hoạch (rotation)

**Rotation** là đưa khóa mới vào sử dụng và ngừng dùng khóa cũ, có giai đoạn chuyển tiếp để hệ thống vẫn xác minh được token hợp lệ. Không nên chờ đến lúc khóa lộ mới xây quy trình này.

### 8.1. Trình tự luân chuyển khóa bất đối xứng

1. **Sinh khóa B** bằng quy trình bảo mật; đăng ký metadata và xác định `kid=B`, thời điểm kích hoạt.
2. **Công bố public key B trong JWKS** bên cạnh public key A đang hoạt động; private key B vẫn được bảo vệ.
3. **Chờ các verifier có đủ cơ hội làm mới cache.** Đo theo TTL thực tế, độ trễ triển khai và mức sẵn sàng của các consumer; kiểm tra họ có thể chọn B đúng cách.
4. **Chuyển issuer sang ký bằng B** và ngừng ký bằng A. Token mới mang `kid=B`; A chuyển sang verify-only.
5. **Giữ public key A trong JWKS** cho đến khi mọi token hợp lệ đã ký bằng A hết thời hạn chấp nhận (cộng mức lệch đồng hồ và bộ đệm hoạt động cần thiết).
6. **Rút A khỏi JWKS/tập khóa tin cậy**, xử lý cache, thu hồi quyền ký bằng A và hủy private key theo chính sách cùng tất cả bản sao/sao lưu phù hợp.

~~~mermaid
sequenceDiagram
    participant I as Issuer
    participant J as JWKS
    participant V as Verifier
    I->>J: Công bố public key B (A + B)
    V->>J: Làm mới cache, nhận A + B
    I->>I: Chuyển ký A sang B
    I->>V: JWT mới có kid B
    V->>V: Xác minh token A hoặc B còn hợp lệ
    I->>J: Sau cửa sổ chuyển tiếp, rút A
    V->>J: Làm mới cache, chỉ còn B
~~~

### 8.2. Tính cửa sổ giữ khóa cũ

Giả sử:

- `T_stop`: thời điểm issuer **thực sự ngừng ký** bằng khóa A;
- `L_max`: thời hạn sống tối đa của token được ký bằng A tính từ thời điểm phát hành;
- `S`: độ lệch đồng hồ được phép khi xác minh;
- `B`: bộ đệm vận hành có cơ sở (chẳng hạn trễ đồng bộ/phân phối theo chính sách).

Một mốc tham khảo để **ngừng chấp nhận khóa A trong luân chuyển bình thường** là:

~~~text
T_retire >= T_stop + L_max + S + B
~~~

Công thức chỉ đúng khi hệ thống thực sự cưỡng chế `L_max`, không còn issuer bí mật tiếp tục ký bằng A, và không có ngoại lệ như token dùng rất lâu, tác vụ offline hoặc chính sách chấp nhận token khác. Nếu các verifier có cache JWKS dài, cần thiết kế việc làm mới và ngừng tin cậy nhất quán. Không dùng công thức này để trì hoãn thu hồi khóa đã lộ.

**Ví dụ cụ thể:** issuer dừng ký bằng A lúc 10:00, access token có thời hạn tối đa 15 phút, cho phép clock skew 1 phút và thêm 4 phút đệm vận hành. Nếu không có trường hợp đặc biệt, thời điểm dự kiến rút A là từ 10:20 trở đi. Trước 10:00, public key B phải được công bố đủ sớm để các verifier tải về.

### 8.3. Rotation với HMAC

Không có public key để công bố. Issuer và **mọi verifier được phép** phải nhận secret B thông qua kênh bảo mật trước khi dùng; trong giai đoạn chuyển tiếp, verifier có thể giữ cả secret A/B cùng với ánh xạ `kid` an toàn. Sau khi hết hạn token A, xóa secret A khỏi nơi sử dụng, bản sao lưu và nơi cấp phát theo chính sách.

Đây là lý do rotation khóa đối xứng phức tạp hơn khi có nhiều dịch vụ hoặc tổ chức tham gia: mọi verifier đều là bên nắm bí mật có khả năng ký. Nếu không thể kiểm soát đầy đủ người giữ secret, nên đánh giá lại kiến trúc.

### 8.4. Chu kỳ rotation là một chính sách

Không có một số ngày cố định phù hợp cho mọi hệ thống. Xác định lịch dựa trên mức độ nhạy cảm, rủi ro lộ khóa, yêu cầu pháp lý/nội bộ, khả năng tự động hóa, số verifier và thời hạn token. Thực hiện định kỳ và **tập dượt thu hồi khẩn cấp**; rút ngắn thời hạn token giúp giảm cửa sổ chuyển tiếp nhưng không thay thế rotation.

## 9. Giai đoạn 6 — Thu hồi khẩn cấp khi khóa bị lộ hoặc nghi bị lộ

Phải có quy trình riêng khi private key/secret bị lộ, quyền ký bị chiếm, JWKS bị thay thế, hoặc có bằng chứng token giả. Đây là sự kiện an ninh, không phải lượt rotation thông thường.

**Trình tự ứng cứu đề xuất:**

1. **Khoanh vùng:** xác định `kid`, issuer, môi trường, các loại token và hệ thống chịu tác động; bảo toàn chứng cứ và audit log.
2. **Ngăn ký tiếp:** khóa quyền dùng khóa bị nghi lộ, vô hiệu hóa thao tác ký và cô lập tài khoản/dịch vụ bị chiếm; sinh khóa thay thế từ môi trường tin cậy.
3. **Ngừng tin cậy khóa bị lộ ở verifier:** rút public key/secret khỏi tập tin cậy, đẩy bản cập nhật tới consumer, chủ động làm mới hoặc vô hiệu hóa cache theo cơ chế vận hành. Khi cần, từ chối toàn bộ token đã ký bằng `kid` đó, kể cả token còn `exp`.
4. **Khôi phục an toàn:** phân phối khóa mới, chuyển phát hành token, kích hoạt phiên/đăng nhập lại hoặc biện pháp phục hồi cần thiết; theo dõi lỗi xác minh và dấu hiệu tái khai thác.
5. **Điều tra và phòng ngừa:** xác định điểm lộ khóa, xoay các thông tin xác thực liên quan, xử lý bản sao và sao lưu, cải thiện quyền truy cập, giám sát và quy trình triển khai.

**Rút khóa khỏi JWKS không đảm bảo thu hồi tức thời.** Một verifier có thể còn giữ khóa cũ trong cache, dùng cấu hình cục bộ hoặc không có kết nối mạng. Kế hoạch ứng cứu phải tính đến khả năng phát tín hiệu khẩn, làm mới cache cưỡng bức, danh sách khóa bị cấm hoặc tạm từ chối traffic cho đến khi mọi consumer quan trọng cập nhật.

Việc vô hiệu hóa chữ ký theo `kid` thường ảnh hưởng **tất cả** token dùng khóa đó. Nếu chỉ muốn thu hồi một token hoặc một phiên riêng lẻ, cần cơ chế khác như token có tuổi thọ ngắn, denylist theo `jti`/phiên, hoặc kiểm tra trạng thái phía server. Một JWKS không thể tự thu hồi từng JWT.

## 10. Giai đoạn 7 — Ngừng sử dụng và hủy khóa

**Retire** nghĩa là chấm dứt vai trò của khóa theo chính sách, còn **destroy** là xử lý vật liệu bí mật để không thể tiếp tục sử dụng. Các bước này cần được ghi nhận độc lập:

- Xác nhận mọi issuer đã ngừng ký bằng khóa cũ, mọi verifier cần thiết đã thôi tin khóa và các token liên quan không còn được phép sử dụng.
- Xóa quyền ký, bí mật hoặc private key khỏi KMS/HSM và các kho triển khai; xử lý phiên bản bí mật, bản sao vùng khác, thiết bị dự phòng và sao lưu theo chính sách được phê duyệt.
- Cập nhật JWKS, file cấu hình, registry khóa, cache và tài liệu vận hành; không để cùng một `kid` vô tình trỏ đến khóa khác.
- Lưu bản ghi kiểm toán không chứa bí mật: `kid`, mục đích, thuật toán, thời điểm tạo/kích hoạt/ngừng ký/ngừng tin cậy/hủy, lý do và chủ thể phê duyệt.
- Kiểm tra lại rằng không có nơi nào còn phát hành hoặc chấp nhận token bằng khóa bị loại bỏ. Với hệ thống có hỗ trợ xác minh dữ liệu lưu trữ dài hạn, thiết kế chính sách lưu bằng chứng và xác minh lịch sử **riêng** thay vì giữ khóa active vô thời hạn.

Khi khóa đã hết tin cậy, **đừng đồng nhất việc vẫn giữ public key để lưu hồ sơ với việc tiếp tục chấp nhận chữ ký của nó trong luồng xác thực trực tuyến**. Hai mục đích có ranh giới và chính sách khác nhau.

## 11. Ví dụ end-to-end: thay khóa mà dịch vụ không gián đoạn

Một hệ thống có dịch vụ phát hành token `auth.example.test` và hai API xác minh sử dụng JWKS. Ban đầu issuer ký bằng khóa `K1`; mỗi JWT có `kid=K1`, `exp` trong tối đa 10 phút.

| Thời điểm | Issuer | JWKS | API xác minh |
| --- | --- | --- | --- |
| Trước T0 | Ký bằng `K1` | Công bố public `K1` | Tin `K1`. |
| T0 | Sinh `K2`, chưa dùng để ký | Công bố public `K1` + `K2` | Làm mới cache để biết `K2`. |
| T1 | Bắt đầu ký bằng `K2`; dừng `K1` | Vẫn có `K1` + `K2` | Xác minh token còn hạn của cả hai khóa. |
| T2, sau cửa sổ hợp lệ | Chỉ ký bằng `K2` | Rút public `K1` | Không còn chấp nhận token bằng `K1`. |
| T3 | Ngừng quyền ký và hủy private `K1` | Chỉ còn `K2` | Ghi nhận kiểm tra hoàn tất. |

Nếu API thứ hai vẫn cache JWKS chỉ chứa `K1` tại T1, token mới có `kid=K2` sẽ bị từ chối. Giải pháp là **pre-publish** `K2` và xác nhận phân phối trước khi kích hoạt, chứ không yêu cầu API bỏ qua kiểm tra chữ ký khi chưa tìm thấy khóa.

Ngược lại, nếu `K1` bị lộ tại T1, hệ thống phải chuyển sang quy trình **thu hồi khẩn cấp**, không tiếp tục chấp nhận `K1` chỉ để tránh làm người dùng mất phiên.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Gắn private key/HMAC secret trong mã nguồn hoặc ảnh triển khai | Khóa có thể lộ qua repository, artifact hoặc bản sao. | Sử dụng KMS/HSM/secret manager, kiểm soát quyền và quét secret. |
| Công khai JWK có trường bí mật hoặc `kty=oct` | Bất kỳ ai đọc JWKS có thể tạo chữ ký. | Chỉ xuất đúng public-key material; kiểm tra schema trước khi publish. |
| Tin `jku`/`x5u` trong JWT mà không giới hạn | Attacker chỉ đến máy chủ khóa của họ; nguy cơ SSRF. | Pin issuer/JWKS tin cậy, allowlist nguồn, không fetch URL tùy ý từ token. |
| Chấp nhận `alg` theo header mà không allowlist | Algorithm confusion; có thể bypass xác minh. | Ràng buộc thuật toán + loại khóa + issuer ở verifier. |
| Đổi khóa ký trước khi public key mới được nhận | Token mới thất bại xác minh trên verifier cache cũ. | Công bố trước, đo cache và kiểm thử trước khi kích hoạt. |
| Rút khóa cũ quá sớm | Token hợp lệ bị từ chối hàng loạt. | Tính cửa sổ từ thời điểm ngừng ký và TTL tối đa. |
| Giữ khóa cũ mãi trong JWKS | Tăng số khóa có thể được tin cậy, tăng rủi ro vận hành. | Có ngày ngừng tin cậy rõ ràng và dọn dẹp có kiểm toán. |
| Mỗi `kid` lạ đều tải lại JWKS | Tạo tải hoặc DoS vào endpoint JWKS. | Rate limit refresh, cache, backoff và giám sát. |
| Chỉ xóa public key khỏi JWKS khi bị lộ | Các cache có thể tiếp tục chấp nhận token giả. | Có playbook cưỡng bức làm mới và chặn `kid` khẩn cấp. |
| Chỉ kiểm tra chữ ký mà bỏ qua `iss`/`aud`/`exp` | Token từ sai đối tượng hoặc sai ngữ cảnh vẫn được chấp nhận. | Kiểm tra đầy đủ claims và chính sách ứng dụng. |

## 13. Checklist kiểm tra vận hành

**Trước khi đưa khóa vào dùng**

- [ ] Khóa sinh bằng nguồn ngẫu nhiên và kích thước/thuật toán đúng chính sách.
- [ ] Private key hoặc HMAC secret được bảo vệ, quyền ký được giới hạn và kiểm toán.
- [ ] `kid` là duy nhất trong phạm vi issuer; mục đích và thời gian hiệu lực được ghi nhận.
- [ ] JWKS công khai chỉ có public key; verifier đã cấu hình issuer, thuật toán và nguồn khóa tin cậy.
- [ ] Đã kiểm thử xác minh token đúng, token sai chữ ký, sai `kid`, sai issuer, sai audience và hết hạn.

**Trong kỳ rotation**

- [ ] Public key mới được công bố và xác nhận verifier có thể cập nhật trước khi đổi khóa ký.
- [ ] Khóa cũ ngừng ký đúng thời điểm và chỉ còn verify-only trong cửa sổ cho phép.
- [ ] Có giám sát số token/kid, lỗi xác minh, lỗi JWKS, độ mới cache và bất thường ký.
- [ ] Khóa cũ được ngừng tin cậy và hủy đúng hạn; bằng chứng hoàn tất được lưu.

**Khi có sự cố**

- [ ] Có cách vô hiệu hóa quyền ký, cấm khóa và làm mới verifier khẩn cấp.
- [ ] Có biện pháp xử lý những token đã ký bằng khóa bị nghi lộ, kể cả token chưa hết hạn.
- [ ] Có kế hoạch phục hồi phiên, thông báo cho các bên liên quan và điều tra truy nguyên.

## 14. Phân biệt các quyết định thường nhầm

**Đổi `kid` có phải là đổi khóa không?** Không. `kid` chỉ là định danh. Rotation thực sự cần **vật liệu khóa mới** và quá trình chuyển phân phối, sử dụng, ngừng tin cậy. Đổi tên khóa trong header không giảm rủi ro khi bí mật cũ đã lộ.

**Chỉ cần JWT có `exp` ngắn thì không phải rotation?** Không. TTL ngắn giới hạn tuổi token hợp lệ; private key/secret vẫn có thể bị đánh cắp và dùng để ký token mới cho đến khi bị chặn. Hai cơ chế giải quyết hai rủi ro khác nhau.

**Nếu JWKS còn public key cũ, có nghĩa issuer vẫn đang dùng private key cũ để ký?** Không. Trong giai đoạn verify-only, chỉ public key cũ còn được phân phối để xác minh token đã ký trước đó; issuer đã dừng ký mới bằng private key tương ứng.

**JWKS có phải nơi quyết định token được cấp quyền truy cập không?** Không. JWKS hỗ trợ xác minh chữ ký. Issuer, audience, thời gian, loại token, phạm vi quyền và tình trạng phiên hoặc đối tượng vẫn phải được kiểm tra riêng.

**Có thể bỏ qua lỗi JWKS để hệ thống luôn sẵn sàng?** Không được bỏ qua chữ ký. Có thể tiếp tục dùng một cache khóa trước đó **còn nằm trong chính sách tin cậy và chưa bị thu hồi** theo thời hạn chặt chẽ; khi thiếu khóa đáng tin, phải từ chối token tương ứng.

## 15. Tài liệu chuẩn để đối chiếu

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): định dạng JWK và JWKS.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): biểu diễn và xác minh chữ ký của JWT.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): định danh thuật toán và các tham số khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và các registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các rủi ro như algorithm confusion, quản trị thuật toán và quy tắc xác minh an toàn.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): sử dụng các khóa OKP/EdDSA trong hệ sinh thái JOSE.

**Nguyên tắc xuyên suốt:** chỉ ký bằng khóa được phép và còn an toàn; chỉ xác minh bằng khóa từ nguồn đã tin cậy; triển khai rotation có khoảng chuyển tiếp được tính toán; và khi mất tin cậy phải thu hồi khóa theo chính sách khẩn cấp thay vì đợi JWT hết hạn.
