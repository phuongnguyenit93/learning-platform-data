# Xoay vòng khóa với khoảng chuyển tiếp giữa khóa cũ và khóa mới

## 1. Vì sao cần khoảng chuyển tiếp khi xoay vòng khóa?

**Xoay vòng khóa (key rotation)** là quá trình thay khóa đang dùng bằng khóa mới theo một kế hoạch có kiểm soát. Với JWT và JOSE, việc thay khóa cần phối hợp giữa bên phát hành token, bên xác minh hoặc giải mã, dịch vụ phân phối khóa và các bộ đệm JWKS ở nhiều hệ thống.

Nếu thay khóa đột ngột, có thể xảy ra hai tình huống:

- Bên phát hành đã ký token bằng khóa mới nhưng bên nhận chưa có khóa công khai mới để xác minh.
- Bên phát hành đã ngừng dùng khóa cũ và xóa khóa công khai cũ quá sớm, trong khi vẫn còn token được ký bằng khóa đó nhưng chưa hết hạn.

Vì vậy, một lần xoay vòng thông thường cần có **khoảng chuyển tiếp (overlap period)**. Trong khoảng này, hệ thống công bố cả khóa cũ và khóa mới; bên phát hành bắt đầu dùng khóa mới, còn bên nhận vẫn có thể xác minh token được ký bằng khóa cũ.

Với một cặp khóa ký bất đối xứng:

- Khóa riêng tư cũ ngừng dùng để ký token mới tại thời điểm chuyển đổi.
- Khóa công khai cũ tiếp tục được công bố để xác minh token cũ còn hiệu lực.
- Khóa công khai mới được công bố trước khi bắt đầu ký bằng khóa riêng tư mới.
- Sau khi mọi token hợp lệ dùng khóa cũ đã hết hạn theo chính sách, khóa công khai cũ mới được gỡ khỏi JWKS.

**Khoảng chuyển tiếp không phải là thời gian tiếp tục ký bằng cả hai khóa một cách tùy ý.** Nó là thời gian các bên xác minh chấp nhận những token đã được ký bằng khóa cũ trong khi token mới được phát hành bằng khóa mới.

## 2. Các trạng thái của khóa trong vòng đời xoay vòng

Có thể mô hình hóa vòng đời một khóa ký như sau:

| Trạng thái | Bên phát hành | Bên xác minh | JWKS công khai |
| --- | --- | --- | --- |
| **Prepared** | Chưa ký token bằng khóa mới | Chưa cần xác minh token mới | Chưa công bố hoặc đang chuẩn bị |
| **Published / Pre-active** | Chưa dùng khóa riêng tư mới để ký | Đã có thể lấy khóa công khai mới | Công bố khóa mới cùng khóa cũ |
| **Active for signing** | Dùng khóa mới để ký token mới | Xác minh token bằng khóa mới và khóa cũ | Giữ cả hai khóa |
| **Verify-only** | Không ký token mới bằng khóa cũ | Vẫn xác minh token cũ | Giữ khóa công khai cũ nếu còn cần xác minh |
| **Retired** | Khóa cũ đã bị vô hiệu hóa cho mục đích phát hành | Không còn cần khóa cũ cho dữ liệu hợp lệ | Gỡ khóa cũ khỏi JWKS |
| **Revoked / Compromised** | Ngừng dùng ngay | Từ chối dữ liệu phụ thuộc khóa bị lộ theo quy trình ứng phó | Gỡ hoặc đánh dấu khóa bị thu hồi, đồng thời xử lý cache |

Các trạng thái này mô tả mục đích sử dụng. Một khóa có thể chuyển từ **active for signing** sang **verify-only** mà không cần xóa ngay khỏi hệ thống. Việc ngừng ký và việc ngừng xác minh là hai mốc khác nhau.

Không nên dùng một trường trạng thái duy nhất thay cho chính sách thực tế. Cần quản lý riêng việc khóa có được phép ký, xác minh, mã hóa hoặc giải mã hay không.

## 3. Quy trình xoay vòng khóa ký JWS theo kế hoạch

Giả sử dịch vụ phát hành đang ký JWT bằng cặp khóa **K1** và chuẩn bị chuyển sang cặp **K2**. JWKS công khai chứa khóa xác minh tương ứng.

~~~mermaid
flowchart TD
    A["Đang ký bằng K1"] --> B["Tạo K2 và kiểm tra khóa"]
    B --> C["Công bố public K2 cùng public K1"]
    C --> D["Chờ phân phối và cache JWKS cập nhật"]
    D --> E["Chuyển issuer sang ký bằng K2"]
    E --> F["Giữ public K1 để xác minh token cũ"]
    F --> G["Chờ token K1 hết hạn và hết leeway"]
    G --> H["Gỡ public K1 khỏi JWKS"]
    H --> I["Retire K1"]
~~~

### Giai đoạn 1 — Chuẩn bị khóa mới

- Tạo K2 bằng hệ thống quản lý khóa phù hợp, chẳng hạn HSM hoặc dịch vụ quản lý khóa.
- Kiểm tra thuật toán, độ dài khóa, mục đích sử dụng và quyền truy cập.
- Gán một KEY ID (KID) mới, duy nhất trong tập khóa của issuer.
- Bảo vệ khóa riêng tư K2 và chỉ cấp quyền ký cho thành phần cần thiết.

Khóa mới phải phù hợp với chính sách thuật toán của bên phát hành và bên xác minh. Không đổi thuật toán một cách ngầm định cùng lúc với đổi khóa nếu chưa có kế hoạch tương thích riêng.

### Giai đoạn 2 — Công bố khóa công khai mới trước khi sử dụng

Công bố JWK công khai của K2 trong JWKS, đồng thời vẫn giữ JWK công khai K1:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-k1",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-for-k1",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-k2",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-for-k2",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là ví dụ cấu trúc; các giá trị modulus là placeholder, không phải khóa sử dụng được.

Bên nhận cần có cơ hội tải JWKS mới trước khi issuer bắt đầu phát hành token mang KID K2. Nếu bắt đầu ký bằng K2 ngay khi mới cập nhật JWKS ở máy chủ, các verifier đang giữ cache cũ có thể chưa biết K2 và từ chối token hợp lệ.

### Giai đoạn 3 — Chờ phân phối và cache cập nhật

Thời gian chờ phụ thuộc vào:

- Cache-Control max-age hoặc chính sách cache tương đương của JWKS.
- Thời gian truyền bá cấu hình đến CDN, proxy và các vùng triển khai.
- Tần suất các verifier làm mới JWKS.
- Cách verifier xử lý ETag, Last-Modified hoặc phản hồi không thay đổi.
- Những verifier không tuân thủ cache policy hoặc chỉ tải khóa khi khởi động.

Nên xác nhận khóa K2 đã xuất hiện trong JWKS được nhìn thấy từ các vùng và nhóm verifier quan trọng. Nếu có verifier không tự làm mới khóa, cần có kế hoạch cập nhật hoặc khởi động lại phù hợp trước khi phát hành token bằng K2.

### Giai đoạn 4 — Chuyển sang ký bằng khóa mới

Sau khi khóa công khai K2 đã được phân phối đủ rộng:

- Chuyển issuer sang dùng khóa riêng tư K2 để ký token mới.
- Ghi KID K2 vào protected header của JWS.
- Giữ K1 trong JWKS để xác minh các token đã được ký trước thời điểm chuyển đổi.
- Theo dõi lỗi xác minh, số lượng token theo KID và tình trạng làm mới JWKS.

Từ thời điểm chuyển đổi, K1 nên ở trạng thái **verify-only**. Không tiếp tục ký token mới bằng K1 chỉ vì khóa công khai cũ vẫn còn trong JWKS.

### Giai đoạn 5 — Kết thúc overlap và gỡ khóa cũ

Khi tất cả token hợp lệ được ký bằng K1 đã hết hạn theo chính sách, gỡ khóa công khai K1 khỏi JWKS. Sau đó hoàn tất quy trình retire khóa cũ theo chính sách lưu giữ, kiểm toán và quản lý bí mật.

Không nên gỡ khóa cũ chỉ vì issuer đã chuyển sang K2. Cần tính đến token cũ còn hiệu lực, độ lệch đồng hồ và thời gian xử lý yêu cầu đang diễn ra.

## 4. Tính thời điểm an toàn để gỡ khóa công khai cũ

Mốc gỡ khóa cũ phải dựa trên **thời điểm hết hạn muộn nhất của token được ký bằng khóa cũ**, không chỉ dựa vào ngày đổi khóa.

Nếu hệ thống có giới hạn thời hạn token tối đa, có thể ước lượng:

~~~text
oldKeyRemovalTime >=
    lastOldTokenIssuedAt
    + maximumTokenLifetime
    + acceptedClockSkew
    + operationalSafetyMargin
~~~

Trong đó:

- **lastOldTokenIssuedAt:** thời điểm muộn nhất issuer còn phát hành token bằng K1.
- **maximumTokenLifetime:** thời hạn tối đa mà profile cho phép token K1 tồn tại.
- **acceptedClockSkew:** dung sai đồng hồ mà verifier chấp nhận khi kiểm tra exp.
- **operationalSafetyMargin:** khoảng dự phòng cho độ trễ xử lý, request đang chạy hoặc sai lệch vận hành đã được đánh giá.

Nếu biết exp lớn nhất thực tế của các token K1 đã phát hành, có thể dùng mốc đó thay cho phép tính theo thời hạn tối đa:

~~~text
oldKeyRemovalTime >=
    maximumExpirationOfK1Tokens
    + acceptedClockSkew
    + operationalSafetyMargin
~~~

### Ví dụ tính overlap

Giả sử:

- Token cũ cuối cùng được phát hành lúc **12:00**.
- Profile giới hạn thời hạn access token tối đa **15 phút**.
- Verifier cho phép clock skew **60 giây**.
- Đội vận hành chọn safety margin **2 phút**.

Khi đó:

~~~text
12:00 + 15 phút + 1 phút + 2 phút = 12:18
~~~

Theo các giả định trên, không nên gỡ public K1 trước **12:18**. Mốc này chỉ là ví dụ; hệ thống thực tế cần dùng giới hạn token, clock skew và thời gian xử lý của chính mình.

### Nếu token không có thời hạn tối đa thì sao?

Nếu token K1 có thể không có exp, hoặc issuer cho phép thời hạn không giới hạn, không thể tính một overlap hữu hạn an toàn chỉ từ thời điểm chuyển khóa.

Cần giải quyết bằng chính sách token, chẳng hạn:

- Bắt buộc access token có exp.
- Giới hạn thời hạn tối đa của token theo profile.
- Dùng cơ chế thu hồi hoặc kiểm tra trạng thái khi cần.
- Đặt một mốc ngừng chấp nhận token cũ và triển khai chính sách đó nhất quán ở mọi verifier.

Không nên giữ khóa cũ vô thời hạn chỉ vì chưa có giới hạn thời hạn token.

## 5. Vai trò của JWKS cache trong khoảng chuyển tiếp

**JWKS (JSON Web Key Set)** là tập hợp các JWK được công bố để bên nhận tìm khóa phù hợp. Trong quá trình xoay vòng, cache JWKS ảnh hưởng trực tiếp đến thời điểm một khóa mới có thể được sử dụng và thời điểm khóa cũ có thể được gỡ.

### Cache quá lâu có thể gây lỗi gì?

Nếu verifier tải JWKS trước khi K2 được công bố rồi giữ cache quá lâu, token mới có KID K2 có thể bị từ chối vì verifier chưa biết khóa này.

### Cache quá ngắn có thể gây lỗi gì?

Cache quá ngắn làm tăng số lần gọi endpoint JWKS, tạo tải không cần thiết lên issuer, CDN và mạng. Khi có nhiều verifier, việc làm mới đồng thời có thể tạo ra đợt tải tăng đột biến.

### Quy tắc vận hành nên có

- Công bố khóa mới trước thời điểm bắt đầu sử dụng nó.
- Cấu hình cache lifetime có cân nhắc đến tần suất rotation và khả năng ứng phó sự cố.
- Dùng ETag hoặc cơ chế kiểm tra phiên bản để giảm truyền dữ liệu không cần thiết.
- Có cơ chế làm mới JWKS khi gặp KID chưa biết, nhưng phải giới hạn tần suất và gộp các yêu cầu đồng thời.
- Không để mỗi token với KID ngẫu nhiên kích hoạt một lần tải JWKS mới; điều đó có thể bị lợi dụng gây DoS.
- Xử lý lỗi JWKS endpoint theo chính sách rõ ràng; không chuyển sang tin khóa do token cung cấp.
- Theo dõi phiên bản JWKS, thời điểm cập nhật thành công và số verifier đang dùng dữ liệu cũ.

Một verifier có thể thử làm mới JWKS khi gặp KID không tìm thấy, nhưng chỉ truy cập **nguồn JWKS đã được cấu hình tin cậy**. Không dùng jku, x5u hoặc URL tùy ý từ token để tải khóa nếu profile không cho phép và không có cơ chế xác minh nguồn đó.

### Cache cũ và việc gỡ khóa

Khi K1 bị gỡ khỏi JWKS, một verifier có thể vẫn giữ bản cache cũ chứa K1 cho đến khi cache hết hạn hoặc được làm mới. Với rotation thông thường, việc này cần được tính trong thiết kế cache và thời hạn token. Với khóa bị xâm phạm, cần xử lý mạnh hơn bằng invalidation/refresh chủ động hoặc danh sách từ chối KID, vì chờ cache hết hạn có thể quá lâu.

## 6. KID giúp chọn khóa trong thời gian overlap

Trong JOSE Header, KEY ID (KID) là định danh giúp bên nhận chọn khóa ứng viên từ tập khóa đã tin cậy.

Ví dụ:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-k2"
}
~~~

Trong overlap, JWKS có cả K1 và K2. Verifier đọc KID để tìm đúng JWK, sau đó vẫn phải kiểm tra:

- Khóa thuộc đúng issuer hoặc trust domain.
- Khóa phù hợp với thuật toán đã được cấu hình cho endpoint.
- Loại khóa và mục đích sử dụng đúng, ví dụ khóa RSA dùng xác minh chữ ký.
- Các thuộc tính JWK như use, key_ops, alg nếu profile sử dụng.
- Signature thực sự hợp lệ trên Signing Input gốc.

KID không phải bằng chứng mật mã và không phải bí mật. Người gửi token có thể tự ghi một KID bất kỳ vào header. Vì vậy:

- Không dùng KID như đường dẫn file hoặc URL.
- Không truy vấn một kho khóa không giới hạn bằng giá trị do token kiểm soát.
- Không tái sử dụng KID cũ cho khóa mới khi token cũ hoặc cache cũ vẫn còn.
- Nếu không tìm thấy KID, xử lý theo chính sách refresh có giới hạn rồi từ chối nếu vẫn không tìm thấy.

Dùng KID duy nhất cho từng phiên bản khóa giúp tránh trường hợp verifier chọn nhầm khóa trong thời gian chuyển tiếp.

## 7. Quản lý khóa riêng tư và khóa công khai khi rotation

Với chữ ký bất đối xứng, hai loại khóa có vòng đời sử dụng khác nhau:

| Thời điểm | Khóa riêng tư cũ K1 | Khóa công khai cũ K1 | Khóa riêng tư mới K2 | Khóa công khai mới K2 |
| --- | --- | --- | --- | --- |
| Trước rotation | Ký token | Xác minh token | Được chuẩn bị, chưa ký | Chưa công bố |
| Pre-publish K2 | Vẫn ký token cũ | Xác minh token cũ | Chưa ký | Được công bố |
| Sau cutover | Ngừng ký | Xác minh token cũ | Ký token mới | Xác minh token mới |
| Trong overlap | Không được dùng để ký | Tiếp tục xác minh token cũ | Đang ký | Đang xác minh |
| Sau overlap | Retire/disable và xử lý lưu giữ | Gỡ khỏi JWKS | Tiếp tục ký | Tiếp tục xác minh |

Khóa riêng tư K1 không cần tiếp tục được cấp cho issuer chỉ vì public K1 còn cần cho xác minh. Có thể vô hiệu hóa quyền ký và giữ bản lưu trữ được kiểm soát theo yêu cầu kiểm toán hoặc khôi phục, nếu chính sách cho phép.

**Không bao giờ đưa private key vào JWKS công khai.** JWK công khai cho RSA chỉ chứa thành phần công khai; EC hoặc OKP chỉ công bố các thành phần public tương ứng. JWK chứa khóa đối xứng với trường k là bí mật và không được công bố tại endpoint JWKS công khai.

## 8. Xoay vòng khóa cho JWE có khác JWS không?

Có. JWS thường dùng khóa ký để phát hành và khóa xác minh để kiểm tra chữ ký. Với JWE, cần phân biệt khóa dùng để mã hóa hoặc thiết lập CEK với khóa dùng để giải mã.

### Rotation khóa nhận JWE

Giả sử bên gửi mã hóa cho khóa công khai của bên nhận:

1. Bên nhận tạo cặp khóa mới K2.
2. Công bố public K2 trong JWKS cùng public K1.
3. Bên gửi tải hoặc cập nhật danh sách khóa và bắt đầu mã hóa thông điệp mới cho K2.
4. Bên nhận giữ private K1 để giải mã các JWE cũ còn cần xử lý.
5. Sau khi hết thời hạn thông điệp, retry window và retention window được phép, private K1 mới được retire.

Với JWE, bên nhận có thể cần giữ **khóa riêng tư cũ để giải mã dữ liệu đã mã hóa trước cutover**. Đây là vòng đời khác với khóa riêng tư ký JWS, vốn có thể ngừng ký ngay khi chuyển đổi trong khi public key cũ vẫn dùng xác minh.

### Khi nào gỡ public key cũ khỏi JWKS JWE?

Nếu bên gửi dùng JWKS để chọn public key mã hóa, public K1 nên được gỡ hoặc đánh dấu không còn dùng cho mã hóa mới khi đã chuyển tất cả sender sang K2. Tuy nhiên, việc giữ hoặc gỡ public K1 cho sender phụ thuộc hợp đồng phân phối khóa và khả năng sender còn dùng cache cũ.

Bên nhận vẫn phải giữ private K1 trong khoảng cần giải mã các ciphertext cũ, ngay cả khi public K1 không còn được công bố cho việc mã hóa mới.

### Khóa JWE bị xâm phạm

Nếu private key giải mã K1 bị lộ, kẻ tấn công có thể giải mã những ciphertext đã thu thập được và được mã hóa cho K1. Xoay vòng khóa chỉ bảo vệ dữ liệu mới sau khi sender chuyển sang K2; nó không thể làm cho ciphertext cũ đã bị thu thập trở nên bí mật trở lại.

Cần đánh giá việc ngừng nhận ciphertext dùng K1, tái mã hóa dữ liệu lưu trữ bằng khóa mới, thu hồi khóa và xử lý dữ liệu có thể đã bị lộ. Quyết định giữ private K1 để giải mã dữ liệu cũ phải được cân nhắc với rủi ro tiếp tục giữ khóa đã bị xâm phạm.

## 9. Xoay vòng khóa HMAC có khác không?

Với thuật toán đối xứng như HS256, bên phát hành và bên xác minh dùng **cùng một secret**. Không thể công bố secret này trong JWKS công khai.

Quy trình rotation HMAC thường cần phối hợp giữa tất cả issuer và verifier:

1. Tạo secret mới K2 trong kho bí mật.
2. Phân phối K2 an toàn đến tất cả verifier trước khi issuer dùng nó.
3. Cấu hình verifier chấp nhận K1 và K2 trong khoảng overlap.
4. Chuyển issuer sang ký token mới bằng K2 và ghi KID K2.
5. Tiếp tục xác minh token K1 còn hiệu lực bằng K1.
6. Sau khi token K1 hết hạn theo chính sách, xóa K1 khỏi tất cả issuer/verifier và hoàn tất retire.

Vì mọi bên giữ secret HMAC đều có thể tạo MAC hợp lệ, phạm vi tin cậy của HS256 khác với chữ ký bất đối xứng. Cần hạn chế số thành phần được quyền giữ secret và không chia sẻ secret qua endpoint JWKS công khai.

## 10. Rotation định kỳ và rotation khẩn cấp khi khóa bị lộ

Hai tình huống này cần quy trình khác nhau.

### Rotation định kỳ

Mục tiêu là chuyển đổi không gián đoạn:

- Pre-publish khóa mới.
- Chờ phân phối và cache cập nhật.
- Chuyển phát hành sang khóa mới.
- Giữ khóa cũ để xác minh hoặc giải mã dữ liệu còn hiệu lực.
- Gỡ khóa cũ sau khi hết thời hạn chấp nhận.

Trong trường hợp này, overlap giúp duy trì khả năng xử lý token hợp lệ đã phát hành trước cutover.

### Rotation khẩn cấp do compromise

Nếu private key ký K1 bị lộ, không nên giữ K1 trong trạng thái verify-only chỉ để duy trì overlap như rotation định kỳ. Kẻ tấn công có thể tạo token mới với chữ ký hợp lệ bằng khóa đã bị lộ.

Quy trình ứng phó cần cân nhắc:

1. Ngừng ký ngay bằng K1 và vô hiệu hóa quyền truy cập vào private key bị lộ.
2. Tạo K2 và chuyển issuer sang ký bằng K2 theo quy trình khẩn cấp.
3. Gỡ K1 khỏi JWKS hoặc đánh dấu bị thu hồi theo cơ chế mà tất cả verifier thực sự kiểm tra.
4. Chủ động làm mới cache JWKS, phát tín hiệu invalidation hoặc cập nhật denylist KID ở các verifier.
5. Từ chối token ký bằng K1, kể cả token có exp chưa đến, nếu chính sách ứng phó xác định khóa đã mất tin cậy.
6. Đánh giá token và dữ liệu đã phát hành trong thời gian khóa có thể bị lộ; cân nhắc yêu cầu xác thực lại hoặc thu hồi phiên.
7. Kiểm tra log, phạm vi truy cập khóa và nguyên nhân compromise; lưu bằng chứng phục vụ điều tra.

Chỉ xóa K1 khỏi JWKS là chưa đủ nếu verifier vẫn giữ cache cũ và tiếp tục chấp nhận chữ ký bằng K1. Với sự cố compromise, cần cơ chế từ chối khóa bị thu hồi độc lập với cache thông thường hoặc một cách bảo đảm verifier cập nhật ngay.

Ngoài ra, chữ ký hợp lệ từ K1 không thể phân biệt token thật do issuer tạo với token giả do kẻ tấn công tạo sau khi có private key. Khi khóa ký đã bị lộ, phải xem xét toàn bộ token được xác thực bằng khóa đó trong khoảng rủi ro.

## 11. Ví dụ timeline cho rotation không gián đoạn

Giả sử hệ thống dùng JWS RS256, có JWKS cache tối đa 5 phút và access token có thời hạn tối đa 15 phút.

~~~text
11:50  Công bố public K2 trong JWKS; public K1 vẫn còn.
11:50-11:56  Chờ cache và các verifier cập nhật; kiểm tra K2 đã được nhìn thấy.
12:00  Issuer chuyển sang ký token mới bằng private K2.
12:00 trở đi  Verifier xác minh token K2 bằng public K2 và token cũ bằng public K1.
12:15  Token K1 cuối cùng có thể hết hạn theo max lifetime (giả sử phát hành cuối lúc 12:00).
12:16  Cộng 60 giây clock skew.
12:18  Cộng 2 phút safety margin; có thể xem xét gỡ public K1 nếu không còn yêu cầu xử lý nào khác.
~~~

Các mốc trên minh họa cách tính. Thời gian chờ pre-publish và thời điểm gỡ khóa phải dựa trên cache thực tế, giới hạn exp, clock skew, request đang chạy và chính sách của từng verifier.

## 12. Theo dõi và kiểm thử trong quá trình overlap

Trong khoảng chuyển tiếp, cần quan sát được trạng thái của cả khóa cũ và khóa mới.

### Chỉ số nên theo dõi

- Số token được phát hành theo từng KID.
- Số lần xác minh thành công/thất bại theo KID.
- Số verifier đã tải phiên bản JWKS chứa khóa mới.
- Tần suất refresh JWKS và lỗi kết nối endpoint.
- Số lần KID không tìm thấy và số lần refresh được kích hoạt.
- Token còn hiệu lực được ký bằng khóa cũ, nếu issuer có thể thống kê an toàn.
- Số yêu cầu còn cần giải mã bằng khóa JWE cũ.

Không ghi nguyên token hoặc private key vào log. KID, issuer, mã lỗi và timestamp thường đủ để chẩn đoán rotation nếu được ghi theo chính sách bảo vệ log.

### Kiểm thử trước và sau cutover

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token K1 trước cutover, còn hạn | Xác minh thành công trong overlap |
| Token K2 sau cutover | Xác minh thành công sau khi verifier nhận K2 |
| Verifier cache JWKS cũ và gặp K2 | Refresh nguồn JWKS tin cậy theo giới hạn rồi xác minh |
| Token có KID không tồn tại | Refresh có kiểm soát, sau đó từ chối |
| Token K1 đã hết hạn | Từ chối dù public K1 vẫn còn trong JWKS |
| K1 đã gỡ sau overlap | Không còn token hợp lệ nào cần K1 |
| Token ký bằng K1 sau khi K1 bị compromise | Từ chối theo chính sách thu hồi khẩn cấp |
| JWE cũ trong retention window | Giải mã bằng private key cũ nếu khóa chưa bị thu hồi và chính sách cho phép |
| JWE mới sau cutover | Giải mã bằng private key mới |

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bắt đầu ký bằng khóa mới trước khi công bố public key | Verifier cache cũ không tìm thấy KID mới | Pre-publish và chờ phân phối |
| Xóa public key cũ ngay khi chuyển issuer | Token cũ còn hạn bị từ chối | Giữ public key cũ đến hết thời hạn chấp nhận |
| Tiếp tục ký bằng private key cũ trong overlap không có lý do | Kéo dài thời gian phụ thuộc khóa cũ | Chuyển issuer sang khóa mới tại cutover |
| Không giới hạn lifetime của token | Không xác định được lúc an toàn để gỡ khóa cũ | Bắt buộc exp và giới hạn thời hạn tối đa |
| Bỏ qua JWKS cache | Một số verifier dùng tập khóa cũ | Xây dựng chính sách cache/refresh và kiểm thử đa vùng |
| Tự tải khóa từ URL trong token | Kẻ tấn công có thể điều khiển nguồn khóa | Dùng issuer/JWKS URI đã cấu hình tin cậy |
| Tái sử dụng KID cho khóa mới | Cache cũ có thể ánh xạ KID sang khóa sai | Gán KID mới, duy nhất và không tái sử dụng |
| Đưa private hoặc symmetric key vào JWKS công khai | Lộ bí mật ký/giải mã | Chỉ công bố public JWK; giữ secret trong kho bảo mật |
| Giữ khóa bị compromise để duy trì overlap | Token giả mạo vẫn có thể được chấp nhận | Thu hồi khóa và buộc verifier từ chối KID bị lộ |
| Gỡ private JWE key quá sớm | Không giải mã được ciphertext cũ còn cần xử lý | Giữ private key trong retention window theo chính sách |
| Giữ private JWE key bị lộ quá lâu | Tăng khả năng giải mã dữ liệu cũ bị thu thập | Xử lý incident, cân nhắc thu hồi và tái mã hóa |

## 14. Checklist triển khai rotation

**Trước cutover**

- [ ] Xác định lý do rotation và loại khóa: JWS signing, JWE recipient hay HMAC.
- [ ] Tạo khóa mới và kiểm tra thuật toán, mục đích sử dụng, quyền truy cập.
- [ ] Gán KID mới, không trùng với khóa đang hoạt động hoặc khóa còn trong overlap.
- [ ] Công bố public key mới trước khi sử dụng; không đưa private/symmetric secret vào public JWKS.
- [ ] Kiểm tra JWKS từ các vùng, CDN và nhóm verifier quan trọng.
- [ ] Xác nhận chính sách cache, refresh, ETag và xử lý unknown KID.

**Trong overlap**

- [ ] Chuyển issuer sang khóa mới tại một thời điểm cutover được ghi nhận.
- [ ] Dừng ký bằng private key cũ.
- [ ] Giữ public key cũ để xác minh token cũ còn hiệu lực.
- [ ] Theo dõi token theo KID, lỗi xác minh và tình trạng JWKS cache.
- [ ] Giữ private JWE key cũ nếu còn ciphertext hợp lệ cần giải mã.
- [ ] Không nới lỏng kiểm tra issuer, audience, exp, thuật toán hoặc loại khóa.

**Kết thúc rotation**

- [ ] Tính mốc hết hạn muộn nhất của token cũ cộng clock skew và safety margin.
- [ ] Xác nhận không còn yêu cầu hợp lệ cần khóa cũ.
- [ ] Gỡ public signing key cũ khỏi JWKS hoặc gỡ khóa mã hóa cũ khỏi danh sách dùng cho mã hóa mới.
- [ ] Retire/disable khóa cũ và xử lý lưu giữ hoặc hủy theo chính sách.
- [ ] Xác nhận tất cả verifier đã cập nhật và không còn phụ thuộc vào khóa cũ.

**Ghi nhớ:** Rotation an toàn cần công bố khóa mới trước khi sử dụng, chuyển issuer sang khóa mới, giữ khóa cũ đúng thời gian để xử lý dữ liệu còn hiệu lực và chỉ retire khi đã hết nhu cầu. Với JWS, public key cũ thường tiếp tục xác minh token cũ sau khi private key ngừng ký. Với JWE, private key cũ có thể còn cần để giải mã ciphertext cũ. Rotation định kỳ dùng overlap để duy trì dịch vụ; rotation do compromise phải thu hồi niềm tin và buộc verifier từ chối khóa bị lộ, kể cả khi token chưa hết hạn.

### Tài liệu chuẩn để tra cứu

- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa, JWK Set và thuộc tính KID, use, key_ops.
- **RFC 7515 — JSON Web Signature (JWS):** chữ ký JWS, protected header và xác minh bằng khóa.
- **RFC 7516 — JSON Web Encryption (JWE):** quản lý khóa, mã hóa và giải mã JWE.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán chữ ký, MAC, quản lý khóa và mã hóa nội dung.
- **RFC 8725 — JSON Web Token Best Current Practices:** chính sách thuật toán, khóa tin cậy và xác minh JWT an toàn.
- **RFC 9111 — HTTP Caching:** hành vi cache HTTP có liên quan đến phân phối JWKS.
