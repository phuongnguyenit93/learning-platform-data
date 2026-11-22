# Di trú thuật toán hoặc khóa mà không mở rộng danh sách tin cậy tùy tiện

## 1. Mục tiêu và nguyên tắc an toàn

Một hệ thống JWT có thể cần thay khóa ký, chuyển từ HMAC sang chữ ký bất đối xứng, đổi RSA sang ECDSA/EdDSA hoặc thay thư viện JOSE. Những thay đổi này thường diễn ra khi hệ thống vẫn đang phục vụ request và có token cũ chưa hết hạn.

Rủi ro lớn nhất trong quá trình di trú là làm cho verifier “dễ chấp nhận hơn” để tránh gián đoạn: cho phép mọi thuật toán mà thư viện hỗ trợ, tin bất kỳ khóa nào xuất hiện trong JWKS, thêm issuer mới mà chưa xác minh, hoặc thử nhiều khóa/thuật toán cho đến khi chữ ký khớp. Cách làm đó biến một thay đổi vận hành thành việc mở rộng ranh giới tin cậy.

Mục tiêu của di trú an toàn:

- Chỉ chấp nhận issuer đã được phê duyệt.
- Chỉ chấp nhận token profile và audience đã được định nghĩa cho resource server.
- Chỉ cho phép tập thuật toán tường minh, phù hợp với profile và chính sách mật mã.
- Chỉ dùng khóa được liên kết trước với issuer, thuật toán, mục đích và phiên bản cụ thể.
- Giới hạn thời gian chấp nhận token được ký bằng khóa/thuật toán cũ.
- Có kế hoạch triển khai, quan sát, rollback và kết thúc hỗ trợ khóa cũ.

**Di trú là thay đổi có kiểm soát bên trong trust boundary đã xác định. Không biến header của token, JWKS tùy ý hoặc khả năng của thư viện thành nguồn cấp quyền tin cậy.**

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào di trú thuật toán và khóa mà không mở rộng danh sách tin cậy tùy tiện, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Phân biệt thay khóa và thay thuật toán

Hai loại thay đổi thường bị gọi chung là “key rotation”, nhưng tác động khác nhau.

| Thay đổi | Ví dụ | Điều thay đổi | Điều cần giữ ổn định |
| --- | --- | --- | --- |
| Rotation cùng thuật toán | RS256 key A → RS256 key B | Key pair và `kid` | Issuer, audience, token profile, thuật toán |
| Di trú thuật toán | RS256 → PS256 hoặc ES256 | Thuật toán và thường cả loại khóa | Issuer, audience, token profile và chính sách tin cậy |
| Di trú mô hình khóa | HS256 → RS256 | Secret đối xứng → private/public key | Danh tính issuer và hợp đồng token |
| Thay thư viện | JOSE library A → library B | Implementation và cách gọi API | Ngữ nghĩa chuẩn, trust configuration và hành vi xác minh |
| Thay issuer | issuer cũ → issuer mới | Nguồn phát hành token | Phải có quy trình onboarding trust riêng, không phải rotation thông thường |

Rotation cùng thuật toán thường đơn giản hơn: verifier cần biết thêm public key mới trong một khoảng thời gian có giới hạn. Di trú thuật toán đòi hỏi kiểm tra hỗ trợ chuẩn, kiểu khóa, định dạng chữ ký, chính sách allowlist và khả năng tương tác của tất cả issuer/verifier.

Thay issuer là thay đổi trust relationship. Không nên coi việc thêm issuer mới vào allowlist như một bước phụ của key rotation.

## 3. Trust registry phải được cấu hình tường minh

### 3.1. Không để token tự mở rộng danh sách tin cậy

Protected header của JWS chứa `alg` và có thể chứa `kid`. Trước khi chữ ký được xác minh, cả header lẫn payload đều là dữ liệu đầu vào không đáng tin. Verifier có thể đọc header để định tuyến việc chọn khóa, nhưng chỉ được dùng các giá trị đó bên trong cấu hình tin cậy đã có.

Không làm các việc sau:

- Chấp nhận mọi giá trị `alg` mà thư viện hỗ trợ.
- Dùng `alg` từ token để tự động chuyển sang một thuật toán khác.
- Tải `jku` hoặc `x5u` từ URL do token cung cấp.
- Thêm issuer chỉ vì token tự khai `iss`.
- Tin `kid` như một chứng cứ rằng khóa tương ứng đã được phê duyệt.
- Thử mọi khóa và mọi thuật toán cho đến khi có một phép xác minh thành công.

### 3.2. Mô hình ràng buộc khóa

Một trust registry có thể biểu diễn logic như sau:

~~~yaml
trusted_issuers:
  - issuer: https://authorization.example.org
    token_profile: oauth-jwt-access-token
    audience: https://api.example.org/orders
    allowed_algorithms:
      - RS256
    keys:
      - kid: as-rs256-2026-01
        alg: RS256
        kty: RSA
        use: sig
        status: active
~~~

Đây là cấu hình khái niệm, không phải schema bắt buộc của một sản phẩm. Điểm quan trọng là mối liên hệ giữa:

- Issuer đã được tin cậy.
- Token profile/type được chấp nhận.
- Audience của resource server.
- Thuật toán được allowlist.
- `kid` và khóa tương ứng.
- Loại khóa, mục đích sử dụng và trạng thái vòng đời.

Không dùng một `kid` để trỏ đến một tập khóa không phân biệt thuật toán hoặc mục đích. Mỗi khóa cần được kiểm tra các thuộc tính phù hợp với thuật toán đã cấu hình.

### 3.3. Kiểm tra thuộc tính JWK

Với khóa bất đối xứng trong JWK/JWKS, verifier nên kiểm tra các thuộc tính liên quan:

| Thuộc tính | Ý nghĩa vận hành |
| --- | --- |
| `kid` | Định danh khóa trong tập khóa của issuer |
| `kty` | Loại khóa, ví dụ RSA hoặc EC |
| `alg` | Thuật toán mà khóa được dự kiến sử dụng, nếu được cung cấp |
| `use` | Mục đích khóa, ví dụ `sig` |
| `key_ops` | Các thao tác được phép, ví dụ `verify` |
| `crv` | Curve đối với khóa EC/OKP |
| `n`, `e` | Thành phần public của RSA |
| `x`, `y` | Thành phần public của EC |

Các thuộc tính phải phù hợp với allowlist và profile. Ví dụ, không dùng khóa EC để xác minh RS256 hoặc dùng khóa có `use: enc` làm khóa chữ ký. Nếu JWK có `alg`, giá trị đó phải tương thích với thuật toán đã cấu hình.

### 3.4. `kid` chỉ là chỉ mục, không phải trust anchor

`kid` không bí mật và không tự xác thực khóa. Nó giúp chọn một khóa trong tập khóa đã được tin cậy. Verifier phải:

1. Xác định issuer từ cấu hình tin cậy.
2. Lấy JWKS từ URI đã cấu hình cho issuer đó.
3. Tìm `kid` trong JWKS đã được lấy qua kênh tin cậy.
4. Kiểm tra loại khóa, mục đích và thuật toán.
5. Xác minh chữ ký bằng khóa phù hợp.

Không lấy URL từ `jku`/`x5u` trong token rồi tải khóa tùy ý. Nếu hệ thống dùng certificate chain (`x5c`), phải có chính sách xác minh certificate path và trust anchor rõ ràng; không coi việc token mang theo certificate là đủ để tin issuer.

## 4. Lập kế hoạch di trú trước khi thay đổi

Trước khi triển khai, lập inventory cho từng issuer/resource server:

- Thuật toán và key ID hiện tại.
- Loại khóa, kích thước/curve và nơi lưu private key/secret.
- Token profile, `typ`, issuer, audience và claims bắt buộc.
- Thời hạn access token lớn nhất và clock skew được chấp nhận.
- Thời gian cache JWKS tại từng verifier.
- Tất cả consumer còn sử dụng token cũ.
- Phiên bản thư viện/provider/HSM có hỗ trợ thuật toán đích không.
- Quy trình rollback và người chịu trách nhiệm đóng migration window.

Không chỉ kiểm tra cấu hình tại issuer. Một verifier cũ có thể vẫn chạy ở một region, worker nền, gateway hoặc đối tác tích hợp. Nếu không biết hết consumer, việc gỡ khóa cũ có thể gây lỗi; ngược lại, giữ khóa cũ vô thời hạn sẽ kéo dài trust window.

### 4.1. Chọn thuật toán đích theo chính sách

Thuật toán đích phải đáp ứng:

- Profile JOSE/JWT đang dùng.
- Chính sách mức an toàn và yêu cầu compliance.
- Khả năng hỗ trợ đồng nhất của issuer và verifier.
- Khả năng tạo/lưu khóa tại HSM/KMS nếu có.
- Định dạng chữ ký và interoperability.
- Hiệu năng và kích thước token đã được đo trên workload đại diện.

Không chọn thuật toán chỉ vì một thư viện có thể xử lý nó. Không hạ mức an toàn hoặc dùng tham số yếu để làm cho hệ cũ tương thích.

### 4.2. Xác định migration window

Migration window là khoảng thời gian có giới hạn mà verifier tạm thời chấp nhận cả cấu hình cũ và cấu hình mới. Window phải được xác định bằng các mốc có thể kiểm chứng:

- Thời điểm public key mới được công bố.
- Thời điểm tất cả verifier nhận được cấu hình mới.
- Thời điểm issuer bắt đầu ký bằng khóa/thuật toán mới.
- Thời hạn tối đa của token cũ.
- Clock skew và thời gian cache/propagation.
- Thời điểm cuối cùng token cũ có thể được chấp nhận.

Không dùng một khoảng “để sau tính” hoặc giữ cấu hình cũ không thời hạn. Cần có ngày/điều kiện đóng window và người chịu trách nhiệm.

## 5. Di trú thuật toán có kiểm soát

### 5.1. Allowlist chuyển tiếp phải hẹp

Giả sử hệ thống đang dùng RS256 và muốn chuyển sang ES256. Trong thời gian chuyển tiếp, verifier có thể cần chấp nhận hai thuật toán:

~~~yaml
allowed_algorithms:
  - RS256
  - ES256
~~~

Danh sách này chỉ an toàn nếu cả hai thuật toán đều đã được phê duyệt, khóa được ràng buộc đúng loại/thuật toán và migration window có thời hạn. Đây không phải lý do để bật toàn bộ thuật toán JOSE.

Nếu có nhiều issuer hoặc nhiều token profile, allowlist nên được xác định riêng theo issuer/profile/resource. Không tạo một danh sách toàn cục rộng khiến mọi API chấp nhận mọi thuật toán cho mọi token.

### 5.2. Ràng buộc từng thuật toán với đúng khóa

Trong thời gian chuyển tiếp:

| Issuer | Profile | `alg` | `kid` | Loại khóa | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| authorization.example.org | access token | RS256 | `as-rs256-old` | RSA public | Verify legacy |
| authorization.example.org | access token | ES256 | `as-es256-new` | EC P-256 public | Verify new |

Verifier không được:

- Thử khóa RSA với ES256 hoặc ngược lại.
- Dùng một secret HMAC như public key RSA.
- Bỏ qua `alg`/key type mismatch.
- Chọn thuật toán thay thế khi xác minh thất bại.
- Chấp nhận khóa không có trong registry/JWKS tin cậy.

### 5.3. Không để client thương lượng thuật toán ký access token

Thuật toán phát hành là quyết định của issuer theo token contract. Client không được yêu cầu tùy ý `alg` để issuer ký bằng một thuật toán khác. Resource server cũng không được để token quyết định allowlist.

Nếu cần hỗ trợ nhiều thế hệ consumer, issuer có thể phát hành token theo profile/cấu hình đã đăng ký cho từng audience/client khi có lý do tương tác rõ ràng. Mỗi profile phải có quy tắc xác minh riêng, không để một endpoint suy đoán tùy tiện.

### 5.4. Tránh algorithm confusion

Một lỗi nghiêm trọng là dùng cùng một luồng xác minh cho HMAC và chữ ký bất đối xứng mà không ràng buộc loại khóa. Ví dụ, một implementation sai có thể diễn giải public key RSA như secret HMAC khi token đổi `alg` từ RS256 sang HS256.

Phòng vệ:

- Allowlist thuật toán độc lập với token.
- Mỗi thuật toán chỉ dùng với loại khóa tương ứng.
- Tách cấu hình verifier cho HMAC và asymmetric khi cần.
- Không fallback giữa các thuật toán.
- Kiểm thử token đổi `alg`, khóa sai loại và header bất thường.

## 6. Rotation khóa trong cùng một thuật toán

Rotation cùng thuật toán thường ít phức tạp hơn migration thuật toán, nhưng vẫn cần đồng bộ issuer và verifier.

### 6.1. Trình tự rotation bình thường

~~~mermaid
sequenceDiagram
    participant AS as Issuer
    participant JWKS as JWKS endpoint
    participant RS as Resource Server
    AS->>AS: Tạo key pair mới, kid mới
    AS->>JWKS: Công bố public key mới
    RS->>JWKS: Refresh JWKS
    JWKS-->>RS: Public key cũ + mới
    AS->>AS: Chuyển signer sang private key mới
    AS-->>RS: Phát hành JWT với kid mới
    RS->>RS: Chọn public key mới và verify
    Note over AS,RS: Giữ public key cũ trong thời gian token cũ còn hợp lệ
    AS->>JWKS: Gỡ public key cũ sau sunset
~~~

Trình tự:

1. Tạo khóa mới bằng hệ thống quản lý khóa tin cậy.
2. Gán `kid` mới, không tái sử dụng `kid` cũ.
3. Công bố public key mới trong JWKS.
4. Chờ verifier refresh JWKS hoặc xác nhận key cache đã cập nhật.
5. Chuyển issuer sang ký token mới bằng khóa mới.
6. Theo dõi tỷ lệ token dùng `kid` mới và lỗi xác minh.
7. Chỉ gỡ khóa cũ khi mọi token ký bằng khóa đó đã hết cửa sổ chấp nhận.

### 6.2. Thời điểm gỡ khóa cũ

Thời gian giữ public key cũ phải bao phủ:

~~~text
old_key_retirement_time >=
    last_old_token_issued_at
    + maximum_old_token_lifetime
    + accepted_clock_skew
    + verifier_cache_and_propagation_margin
~~~

Đây là mô hình tính thời điểm, không phải công thức thay thế chính sách cache. Nếu verifier có thể giữ JWKS cũ lâu hơn dự kiến, cần tính cả thời gian đó hoặc có cơ chế invalidation được xác nhận.

Không gỡ public key cũ ngay khi issuer đổi signer; token cũ vẫn có thể còn hiệu lực. Ngược lại, không giữ khóa cũ vô hạn chỉ vì chưa biết consumer nào còn dùng nó. Cần telemetry và lịch sunset.

### 6.3. `kid` không được tái sử dụng

Không gán lại cùng một `kid` cho khóa mới. Cache có thể tiếp tục ánh xạ `kid` cũ tới key material cũ, tạo lỗi xác minh hoặc hành vi không nhất quán. `kid` nên duy nhất trong phạm vi issuer và được quản lý như một định danh phiên bản bất biến.

## 7. Chuyển từ HMAC sang chữ ký bất đối xứng

Chuyển HS256 sang RS256/ES256/EdDSA là thay đổi cả thuật toán lẫn mô hình quyền khóa.

### 7.1. Vì sao cần migration riêng?

Với HMAC:

- Issuer và verifier giữ cùng secret.
- Mọi verifier có khả năng tạo chữ ký.
- Secret phải được phân phối đến từng verifier.

Với chữ ký bất đối xứng:

- Issuer giữ private key.
- Verifier chỉ cần public key.
- Public key có thể phân phối qua JWKS.
- Verifier không có quyền ký nếu chỉ giữ public key.

Do đó, migration không chỉ đổi chuỗi `alg`. Nó còn cần thay đổi quyền truy cập secret, key provider, cấu hình JWKS và cách xử lý sự cố.

### 7.2. Các bước chuyển đổi

1. Tạo cặp khóa bất đối xứng mới.
2. Công bố public key mới qua JWKS của đúng issuer đã tin cậy.
3. Cấu hình verifier hỗ trợ đúng thuật toán mới và đúng key type.
4. Xác nhận tất cả resource server có thể lấy và xác minh public key mới.
5. Chuyển issuer sang ký token mới bằng private key.
6. Trong migration window, chỉ chấp nhận HS cũ và thuật toán bất đối xứng mới đã phê duyệt, gắn với các khóa tương ứng.
7. Ngừng phát hành token HMAC.
8. Chờ token HMAC cũ hết cửa sổ chấp nhận hoặc thu hồi chúng theo kế hoạch.
9. Gỡ HMAC secret khỏi verifier và secret distribution system.
10. Xác nhận không còn request hợp lệ nào cần khóa cũ; đóng allowlist cũ.

### 7.3. Không phát tán HMAC secret trong JWKS công khai

JWK có thể biểu diễn khóa đối xứng bằng trường `k`, nhưng HMAC secret không phải public key. Không đưa secret HMAC vào JWKS công khai hoặc endpoint mà verifier/đối tác không có quyền ký có thể đọc.

Trong giai đoạn chuyển tiếp, nếu verifier vẫn cần xác minh HS token, secret phải được phân phối qua kênh bí mật có kiểm soát. Điều này có nghĩa các verifier đó vẫn có quyền ký cho đến khi secret bị gỡ.

### 7.4. Kết thúc quyền ký ở verifier

Sau khi migration hoàn tất:

- Verifier asymmetric chỉ giữ public key.
- Private key chỉ nằm tại issuer hoặc dịch vụ ký chuyên trách.
- HMAC secret cũ bị xóa khỏi secret store, cấu hình, backup hoạt động và runtime theo quy trình quản lý bí mật.
- Quyền truy cập key-management service được rà soát.
- Audit xác nhận không còn thành phần cần secret cũ.

Xóa secret khỏi một file cấu hình chưa đủ nếu secret còn trong environment, snapshot, image, log hoặc backup. Xử lý các bản sao theo chính sách retention và incident response.

## 8. JWKS publication, cache và đồng bộ verifier

### 8.1. Công bố khóa mới trước khi ký

Với chữ ký bất đối xứng, public key mới phải có sẵn cho verifier trước khi issuer phát hành token đầu tiên dùng private key tương ứng. Nếu issuer ký trước, một số RS chưa cập nhật JWKS sẽ không tìm thấy `kid` và từ chối token hợp lệ.

Trình tự an toàn:

1. Tạo key pair mới và xác minh public key có thể được parse bởi các thư viện đích.
2. Thêm public JWK mới vào JWKS của issuer.
3. Kiểm tra JWKS response, TLS, cache headers và khả năng truy cập từ từng vùng.
4. Làm mới cache hoặc chờ cache refresh theo chính sách.
5. Chạy kiểm thử xác minh token thử nghiệm bằng key mới.
6. Chuyển issuer sang ký token production bằng key mới.

Không đưa private key vào JWKS. Không công bố HMAC secret ở endpoint JWKS công khai.

### 8.2. Xử lý `kid` chưa biết

Khi verifier nhận token có `kid` chưa nằm trong cache:

1. Kiểm tra issuer đã được cấu hình tin cậy.
2. Refresh JWKS từ URI tin cậy với timeout và giới hạn tần suất.
3. Tìm lại đúng `kid`.
4. Kiểm tra `kty`, `alg`, `use`, `key_ops` và curve/modulus nếu có.
5. Nếu không có khóa phù hợp, từ chối token.

Không tải khóa từ URL do token cung cấp. Không refresh JWKS trên mọi request có `kid` lạ; dùng cooldown hoặc negative cache ngắn để tránh refresh storm.

### 8.3. Cache phải hỗ trợ rotation và sự cố

Cache JWKS cần có:

- TTL và quy tắc refresh rõ ràng.
- Cơ chế cập nhật khóa mới.
- Cơ chế loại bỏ khóa bị thu hồi.
- Giới hạn kích thước response và số lượng khóa.
- Timeout, retry có giới hạn và circuit breaker.
- Metrics về cache hit/miss, refresh lỗi và `kid` không tìm thấy.

Trong sự cố khóa bị lộ, TTL dài có thể khiến verifier tiếp tục tin khóa đã bị thu hồi. Cần có cơ chế invalidation khẩn cấp hoặc policy block key ID, không phụ thuộc hoàn toàn vào cache expiration bình thường.

## 9. Xử lý token cũ và token được cấp trong thời gian di trú

### 9.1. Token cũ vẫn có thể hợp lệ trong thời gian giới hạn

Sau khi issuer chuyển sang thuật toán/khóa mới, token cũ không tự biến mất. Nếu token cũ chưa hết hạn và verifier vẫn chấp nhận khóa cũ, nó tiếp tục hợp lệ theo chính sách hiện hành.

Migration plan phải xác định:

- Thời điểm cuối cùng issuer được phép phát hành token cũ.
- Maximum lifetime của token cũ.
- Clock skew mà verifier chấp nhận.
- Thời gian cache JWKS và propagation.
- Cách xử lý refresh token hoặc session có thể tiếp tục tạo access token cũ.
- Cách xác định consumer còn gửi token cũ.

Đừng chỉ dựa vào `iat` để cho rằng token cũ đã hết hiệu lực. Verifier phải kiểm tra chữ ký, thời hạn và các claims theo profile; việc đóng migration dựa trên mốc phát hành cuối cùng và cửa sổ chấp nhận thực tế.

### 9.2. Không tự động re-sign token cũ

Không decode một JWT cũ rồi ký lại payload bằng khóa mới một cách máy móc. Việc này có thể:

- Chuyển tiếp claims đã lỗi thời hoặc quyền đã bị thu hồi.
- Bỏ qua việc xác minh issuer, audience, profile và chữ ký ban đầu.
- Giữ nguyên `exp` hoặc `jti` không còn phù hợp.
- Biến token được cấp theo chính sách cũ thành credential mới mà không đánh giá lại grant.

Nếu cần cấp token theo khóa mới, hãy thực hiện lại quy trình phát hành có thẩm quyền: xác minh client/grant, kiểm tra trạng thái và quyền hiện tại, tạo claims mới rồi ký token mới. Nếu client cần credential mới, dùng cơ chế refresh/re-authentication theo giao thức.

### 9.3. Token type và audience vẫn phải được tách biệt

Trong thời gian có hai thuật toán, không để verifier chấp nhận một token chỉ vì chữ ký hợp lệ. Vẫn phải kiểm tra:

- Token profile/type, ví dụ access token profile.
- Issuer chính xác.
- Audience của resource server.
- Claims bắt buộc và kiểu dữ liệu.
- `exp`, `nbf`, `iat` và clock skew.
- Scope/permission theo hợp đồng.

Không dùng cùng một validator rộng cho ID token, access token, client assertion và các JWT nội bộ nếu các profile có mục đích khác nhau.

## 10. Ứng phó khi khóa cũ bị lộ hoặc bị nghi ngờ

Di trú định kỳ khác với ứng phó sự cố. Khi khóa bị lộ, mục tiêu ưu tiên là ngăn attacker tiếp tục tạo token giả; không nhất thiết giữ overlap để tránh gián đoạn.

### 10.1. Các bước ứng phó

1. Xác định issuer, `kid`, thuật toán, môi trường và resource server bị ảnh hưởng.
2. Đánh giá liệu attacker có thể ký token mới bằng khóa bị lộ hay không.
3. Tạo khóa mới từ nguồn tin cậy và chuyển issuer sang khóa mới.
4. Phát tín hiệu thu hồi/invalidation cho tất cả verifier.
5. Ngừng chấp nhận `kid` hoặc secret bị ảnh hưởng theo chính sách khẩn cấp.
6. Thu hồi session, refresh token hoặc credential liên quan nếu cần.
7. Kiểm tra log/audit để xác định token giả hoặc hành vi bất thường.
8. Rà soát nơi khóa có thể còn tồn tại: secret manager, HSM, CI/CD, runtime, image, backup và log.
9. Xác minh mọi region, gateway, worker và consumer đã áp dụng trust update.

### 10.2. Không giữ khóa bị xâm phạm chỉ để duy trì tương thích

Trong rotation bình thường, giữ khóa cũ để xác minh token còn hiệu lực là hợp lý. Khi khóa bị xâm phạm, giữ khóa trong allowlist cho phép attacker tiếp tục tạo token có chữ ký hợp lệ. Cần quyết định rõ giữa tính sẵn sàng và rủi ro giả mạo; với credential có quyền cao, thường phải ưu tiên loại bỏ khóa bị xâm phạm và buộc cấp lại token.

### 10.3. Nếu HMAC secret bị lộ

Vì mọi verifier giữ HMAC secret đều có khả năng ký, cần xác định mọi thành phần từng nhận secret, không chỉ issuer. Thu hồi secret tại tất cả verifier và secret distribution system; kiểm tra bản sao trong backup hoặc môi trường không còn hoạt động. Chuyển sang secret mới hoặc mô hình asymmetric theo incident plan.

### 10.4. Nếu private key bất đối xứng bị lộ

Public key tương ứng phải bị loại khỏi trust set của verifier. Công bố key mới và cập nhật issuer. Không giữ public key cũ trong JWKS chỉ vì một số token còn hạn nếu attacker có thể tiếp tục ký token giả. Có thể cần thu hồi toàn bộ token được ký bằng key đó hoặc dùng trạng thái token tập trung.

## 11. Rollout, quan sát và rollback

### 11.1. Rollout theo giai đoạn

Một kế hoạch triển khai có thể gồm:

| Giai đoạn | Thay đổi | Điều kiện chuyển bước |
| --- | --- | --- |
| 0. Inventory | Ghi nhận issuer, verifier, key, algorithm, token lifetime và cache | Không còn consumer chưa xác định |
| 1. Prepare | Tạo khóa mới, kiểm tra thư viện và công bố public key | Verifier đọc được key mới |
| 2. Enable verification | Bật đúng thuật toán/khóa mới trong allowlist hẹp | Test token mới xác minh thành công ở mọi vùng |
| 3. Switch signer | Issuer bắt đầu ký bằng khóa/thuật toán mới | Metrics xác nhận token mới được chấp nhận |
| 4. Observe | Theo dõi token cũ, lỗi verify và consumer | Không còn consumer hợp lệ cần token cũ |
| 5. Sunset | Ngừng chấp nhận khóa/thuật toán cũ | Qua maximum lifetime + skew + propagation |
| 6. Cleanup | Gỡ secret/key cũ và cấu hình chuyển tiếp | Audit xác nhận trust set cuối cùng |

Không chuyển bước chỉ dựa trên một request thử nghiệm. Cần quan sát tất cả region, replica và loại consumer.

### 11.2. Metrics cần theo dõi

- Số token xác minh theo issuer, `kid`, `alg` và token profile.
- Tỷ lệ token mới so với token cũ.
- Lỗi invalid signature, unknown `kid`, issuer/audience mismatch và expired token.
- JWKS cache hit/miss và refresh error.
- Độ trễ xác minh p50/p95/p99.
- Request bị từ chối do policy và do credential.
- Số consumer vẫn sử dụng thuật toán/khóa cũ.

Không ghi raw token hoặc secret vào metrics/log. Có thể ghi các định danh cấu hình như issuer đã biết, `kid`, thuật toán và mã lỗi tổng quát.

### 11.3. Rollback an toàn

Rollback phải được định nghĩa trước khi chuyển signer:

- Có thể chuyển signer về khóa cũ nếu khóa cũ vẫn an toàn, chưa bị thu hồi và còn trong trust registry.
- Verifier có thể tiếp tục xác minh cả hai khóa trong migration window đã phê duyệt.
- Không mở rộng allowlist sang thuật toán không liên quan để “chữa cháy”.
- Không rollback về khóa đã bị lộ hoặc thuật toán đã bị cấm.
- Nếu đã đóng migration window và gỡ khóa cũ, rollback cần một kế hoạch mới được phê duyệt; không tự bật lại trust cũ.

Rollback không có nghĩa là chấp nhận mọi token từng được phát hành. Mỗi token vẫn phải qua cùng issuer, audience, profile, time và authorization checks.

## 12. Di trú thư viện và khả năng tương tác

Thay thư viện JOSE/JWT cũng là một dạng migration. Hai thư viện có thể cùng tuyên bố hỗ trợ một thuật toán nhưng khác nhau về API, mặc định xác minh, kiểu dữ liệu khóa, xử lý claims hoặc định dạng chữ ký.

### 12.1. Kiểm tra tương thích chuẩn

Trước khi thay thư viện, xác minh:

- JWS Compact Serialization và signing input được tạo đúng.
- Thuật toán JOSE được hỗ trợ đúng profile.
- ECDSA signature dùng định dạng JOSE fixed-width R || S, không nhầm với ASN.1 DER.
- RSA-PSS dùng đúng tham số theo JOSE profile, không chỉ cùng tên PSS.
- EdDSA/curve được hỗ trợ đúng theo RFC 8037.
- JWK/JWKS được parse đúng và kiểm tra thuộc tính khóa.
- NumericDate, audience dạng chuỗi/mảng và claims tùy chỉnh được xử lý nhất quán.
- Token type/profile và validation rules không bị thay đổi ngầm.

### 12.2. Giữ nguyên chính sách xác minh

Khi thay thư viện, không vô tình đổi:

- Tập thuật toán được phép.
- Quy tắc issuer và audience.
- Clock skew và cách kiểm tra `exp`, `nbf`, `iat`.
- Quy tắc required claims và kiểu dữ liệu.
- Cách chọn khóa và kiểm tra `kid`.
- Cách phân biệt invalid token với lỗi key provider.

Một thư viện mới trả về “valid” không có nghĩa nó tương đương thư viện cũ nếu cấu hình validation khác nhau. So sánh hành vi bằng test vectors và negative tests, không chỉ bằng một token hợp lệ.

### 12.3. Dùng test vectors và kiểm thử chéo

Tạo bộ token test được phát hành bằng implementation A và xác minh bằng implementation B, sau đó đảo chiều nếu B cũng phát hành. Bộ kiểm thử cần bao gồm:

- Mỗi thuật toán/curve/key size đang dùng.
- Token có claims tối thiểu và claims mở rộng.
- Token có audience dạng chuỗi và mảng nếu profile cho phép.
- Token hết hạn, chưa có hiệu lực và sai issuer/audience.
- Chữ ký sai, payload/header bị sửa và `kid` không tồn tại.
- JWK có key type, use, key_ops hoặc alg không phù hợp.

Không dùng private key production trong bộ test. Tạo khóa test riêng và bảo đảm chúng không được tin cậy ở production.

## 13. Kiểm thử migration trước và trong rollout

### 13.1. Test matrix

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Token cũ, đúng issuer/profile/audience và còn hạn trong migration window | Chấp nhận bằng đúng khóa/thuật toán cũ |
| Token mới, đúng issuer/profile/audience | Chấp nhận bằng đúng khóa/thuật toán mới |
| Token cũ sau thời điểm sunset | Từ chối |
| Token dùng thuật toán ngoài allowlist | Từ chối |
| Token khai `alg` mới nhưng dùng key type cũ không tương thích | Từ chối |
| `kid` mới nhưng không có trong JWKS tin cậy | Refresh có giới hạn, sau đó từ chối |
| `kid` trùng nhưng key material khác với registry/cache | Không chấp nhận thay đổi không được quản lý; báo lỗi cấu hình |
| Token từ issuer chưa được phê duyệt | Từ chối |
| Token đúng chữ ký nhưng sai audience | Từ chối |
| Token có `jku`/`x5u` trỏ đến host tùy ý | Không tải URL đó |
| JWKS endpoint lỗi, cache còn key hợp lệ theo policy | Xử lý theo cache/availability policy đã định nghĩa |
| JWKS endpoint lỗi và không có key tin cậy | Không bỏ qua xác minh |
| Key cũ bị thu hồi khẩn cấp | Từ chối token theo key ID bị block |
| Token ID/access/assertion sai profile | Từ chối theo quy tắc token type |

### 13.2. Kiểm thử thời gian và cache

Test các mốc:

- Trước khi public key mới được công bố.
- Sau khi JWKS có key mới nhưng verifier chưa refresh.
- Sau khi verifier refresh và trước khi issuer chuyển signer.
- Ngay sau khi issuer chuyển signer.
- Gần thời điểm token cũ hết hạn.
- Sau maximum lifetime + clock skew + cache propagation.
- Sau khi khóa cũ bị gỡ hoặc bị block khẩn cấp.

Các mốc này giúp phát hiện lỗi rollout và xác nhận sunset thật sự đóng được trust path cũ.

### 13.3. Kiểm thử multi-region và consumer cũ

Không chỉ test một instance. Kiểm tra:

- Mọi region và replica có cùng trust registry.
- Gateway, background worker và service-to-service consumer.
- Client/partner không tự giữ logic verify cũ.
- JWKS cache tại các node được cập nhật đúng.
- Không có instance cũ khởi động lại rồi nạp lại cấu hình trust đã hết hạn.

## 14. Những cách làm mở rộng trust không an toàn

1. **Bật mọi thuật toán thư viện hỗ trợ:** làm rộng bề mặt chấp nhận và có thể mở đường cho algorithm confusion.
2. **Tin `alg` trong token:** để dữ liệu không tin cậy quyết định chính sách mật mã.
3. **Thử mọi khóa:** làm mất ràng buộc giữa issuer, `kid`, thuật toán và key type.
4. **Tải `jku`/`x5u` tùy ý:** cho token quyết định nguồn khóa và có thể tạo SSRF hoặc trust injection.
5. **Thêm issuer mới để xử lý token lỗi:** biến sự cố migration thành thay đổi trust relationship.
6. **Giữ khóa cũ vô thời hạn:** kéo dài khả năng chấp nhận token/khóa yếu hoặc bị lộ.
7. **Gỡ public key cũ ngay sau khi đổi signer:** làm token cũ còn hạn bị từ chối ngoài kế hoạch.
8. **Tái sử dụng `kid`:** gây cache ambiguity và chọn nhầm key material.
9. **Tự động re-sign payload cũ:** chuyển tiếp claims cũ mà không đánh giá lại grant.
10. **Dùng chung verifier cho mọi token type:** tạo cross-token confusion.
11. **Rollback bằng cách bật thuật toán bị cấm:** biến rollback thành hạ cấp bảo mật.
12. **Không kiểm tra mọi consumer:** để một region hoặc đối tác tiếp tục dùng đường xác minh cũ.
13. **Không có sunset owner:** migration window trở thành cấu hình vĩnh viễn.
14. **Xóa secret khỏi một nơi duy nhất:** bỏ sót bản sao trong runtime, image, backup hoặc pipeline.

## 15. Checklist di trú an toàn

### Trust boundary

- [ ] Issuer đã được phê duyệt và không được thêm chỉ dựa trên claim từ token.
- [ ] Audience và token profile được giữ đúng.
- [ ] Allowlist thuật toán tường minh theo issuer/profile/resource.
- [ ] Mỗi thuật toán được ràng buộc với đúng key type và key purpose.
- [ ] Không tin URL khóa từ `jku`/`x5u` tùy ý.
- [ ] `kid` chỉ được dùng để chọn khóa trong tập khóa tin cậy.
- [ ] Không có fallback hoặc thử mọi thuật toán/khóa.

### Kế hoạch migration

- [ ] Đã inventory issuer, verifier, consumer, token lifetime và cache.
- [ ] Thuật toán đích đáp ứng chính sách an toàn và hỗ trợ interoperability.
- [ ] Migration window có thời điểm bắt đầu, kết thúc và owner.
- [ ] Public key mới được công bố trước khi signer sử dụng.
- [ ] Token cũ được giữ trong thời gian cần thiết, có giới hạn.
- [ ] Có quy tắc xử lý refresh token/session và consumer cũ.

### Rotation và ứng phó

- [ ] `kid` mới duy nhất và không tái sử dụng.
- [ ] Key rotation có lịch và trạng thái rõ ràng.
- [ ] Có đường thu hồi/invalidation khẩn cấp.
- [ ] Khóa bị lộ không được giữ lại chỉ để tương thích.
- [ ] HMAC secret được gỡ khỏi mọi verifier sau migration HS-to-asymmetric.
- [ ] Có kế hoạch xử lý token/credential được ký bằng khóa bị xâm phạm.

### Rollout và xác minh

- [ ] Có test positive/negative cho thuật toán, key type, issuer, audience và token profile.
- [ ] Có test JWKS cache, unknown kid, refresh failure và key rotation.
- [ ] Có test multi-region và mọi loại consumer.
- [ ] Theo dõi token cũ/mới, verify error, cache và p95/p99.
- [ ] Rollback chỉ dùng khóa/thuật toán còn được phê duyệt và chưa bị xâm phạm.
- [ ] Đóng migration window và gỡ cấu hình cũ sau sunset.
- [ ] Audit xác nhận trust registry cuối cùng không rộng hơn chính sách đã duyệt.

## 16. Kết luận

Di trú thuật toán và khóa cần giữ nguyên trust boundary trong khi thay đổi có kiểm soát những thành phần bên trong nó. Phân biệt key rotation với algorithm migration và issuer migration; ràng buộc issuer, token profile, audience, thuật toán, `kid` và thuộc tính khóa; công bố public key mới trước khi ký; giới hạn overlap theo maximum token lifetime, clock skew và cache propagation; sau đó đóng cấu hình cũ.

Với migration từ HMAC sang chữ ký bất đối xứng, cần loại bỏ dần quyền ký khỏi resource server bằng cách gỡ HMAC secret khỏi verifier. Với sự cố khóa bị lộ, ưu tiên thu hồi trust path bị xâm phạm thay vì duy trì overlap vì tương thích. Khi thay thư viện, giữ nguyên chính sách xác minh và dùng test vectors/negative tests để chứng minh hành vi tương đương.

**Không mở rộng trust chỉ để migration dễ hơn. Mỗi issuer, thuật toán và khóa mới phải được phê duyệt, ràng buộc rõ ràng, kiểm thử và có thời điểm sunset.**

## Tài liệu chuẩn để đọc tiếp

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, signing input và xác minh chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWKS và thuộc tính khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và ràng buộc khóa.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA và OKP key types.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata issuer và JWKS endpoint.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, key trust và token confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token profile và validation.
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): mô hình khóa HMAC đối xứng.
