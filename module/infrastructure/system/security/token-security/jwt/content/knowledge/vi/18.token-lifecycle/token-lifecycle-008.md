# Thu hồi theo khóa ký và phạm vi ảnh hưởng

## 1. Vì sao thu hồi khóa ký có thể vô hiệu hóa nhiều JWT?

Một JSON Web Token (JWT) được bảo vệ bằng JSON Web Signature (JWS) có chữ ký được tạo từ khóa ký. Resource server dùng khóa tương ứng để xác minh chữ ký. Nếu một khóa ký không còn được tin cậy, mọi token phụ thuộc vào khóa đó có thể phải bị từ chối, kể cả token được phát hành hợp lệ trước đó.

Đây là một cách thu hồi ở quy mô lớn: **thu hồi niềm tin vào khóa ký để ngăn chấp nhận các token được ký bằng khóa đó**. Cách làm này đặc biệt quan trọng khi khóa riêng bị lộ, bị sử dụng trái phép, hoặc issuer không thể xác định chính xác những token giả mạo đã được tạo ra.

Tuy nhiên, JWT không có một trường hay lệnh thu hồi khóa dùng chung cho mọi hệ thống. Việc một resource server ngừng tin khóa phụ thuộc vào cách nó lấy khóa, cache khóa, cập nhật cấu hình và áp dụng chính sách xác minh. Xóa khóa khỏi JWKS là một tín hiệu phân phối; nó không bảo đảm mọi verifier lập tức xóa bản khóa đã cache.

Cần phân biệt ba hành động:

- **Key rotation:** thay khóa hiện tại bằng khóa mới theo kế hoạch, thường có giai đoạn hai khóa cùng được chấp nhận.
- **Key revocation:** tuyên bố một khóa không còn đáng tin và từ chối token dựa trên khóa đó.
- **Token/session revocation:** vô hiệu hóa một token, một phiên hoặc một nhóm token theo định danh/quan hệ của chúng, trong khi khóa ký vẫn có thể tiếp tục được sử dụng.

**Thu hồi khóa có phạm vi ảnh hưởng rộng theo khóa; thu hồi token hoặc phiên có thể nhắm chính xác hơn.** Chọn biện pháp dựa trên loại sự cố, mức độ chắc chắn về khóa bị ảnh hưởng và độ trễ thu hồi cần đạt.

## 2. Khóa ký, kid và JWKS liên hệ với nhau thế nào?

### 2.1. Khóa ký và khóa xác minh

Với chữ ký bất đối xứng như RSA hoặc ECDSA:

- Issuer giữ khóa riêng (private key) để ký JWT.
- Resource server dùng khóa công khai (public key) tương ứng để xác minh.
- Việc resource server biết khóa công khai không cho phép nó tạo chữ ký hợp lệ.

Với HMAC:

- Issuer và mọi verifier cùng giữ một bí mật (shared secret).
- Bất kỳ thành phần nào có bí mật đó đều có khả năng tạo chữ ký hợp lệ.
- Thu hồi secret đòi hỏi loại bỏ hoặc thay secret ở tất cả thành phần đang sử dụng nó.

Sự khác biệt này ảnh hưởng trực tiếp đến phạm vi sự cố. Với khóa bất đối xứng, có thể cô lập quyền ký ở issuer và phân phối khóa công khai cho nhiều verifier. Với HMAC, mỗi verifier cũng nắm khả năng ký, nên việc chia sẻ secret rộng làm tăng số thành phần có thể giả mạo token.

### 2.2. kid là định danh khóa

JOSE header có thể chứa kid (Key ID) để verifier chọn khóa tương ứng trong tập khóa đã được cấu hình hoặc công bố:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-02",
  "typ": "JWT"
}
~~~

**kid không phải bằng chứng khóa đáng tin và không tự thực hiện thu hồi.** Nó chỉ giúp định vị khóa. Verifier phải tra kid trong tập khóa đã gắn với issuer được tin cậy, đồng thời kiểm tra thuật toán, loại khóa và mục đích sử dụng có phù hợp.

Không lấy khóa từ URL tùy ý trong token như jku hoặc x5u. Không dùng kid làm đường dẫn file, câu truy vấn hay URL trực tiếp. Không dùng cùng một kid cho hai khóa khác nhau trong cùng phạm vi issuer khi token của cả hai khóa có thể còn được chấp nhận.

Nếu token không có kid, verifier chỉ có thể xử lý khi profile và cấu hình định nghĩa cách chọn khóa rõ ràng, không mơ hồ. Không thử mọi khóa trong mọi issuer rồi chấp nhận khóa nào xác minh thành công.

### 2.3. JWKS là tập khóa công khai được công bố

Issuer có thể công bố các khóa xác minh qua JWKS (JSON Web Key Set). Một JWK thường có các thuộc tính như kty, kid, use, key_ops, alg và các tham số khóa.

Verifier thường tải JWKS từ endpoint được cấu hình trong metadata tin cậy của issuer và cache trong một khoảng thời gian. Vì vậy, việc xóa một khóa khỏi JWKS không nhất thiết làm bản khóa trong cache biến mất ngay lập tức.

JWKS cũng không phải danh sách thu hồi chuẩn tự động áp dụng cho mọi verifier. Nó là cơ chế phân phối khóa. Hệ thống cần quy định cách làm mới cache, cách xử lý kid không còn được công bố và cách phát tín hiệu khẩn cấp khi một khóa bị xâm phạm.

## 3. Phạm vi ảnh hưởng khi thu hồi một khóa

### 3.1. Những token có thể bị ảnh hưởng

Khi một khóa bị thu hồi, tập token chịu ảnh hưởng thường được xác định bởi tổ hợp:

- Issuer đã phát hành token.
- Định danh khóa kid và thuật toán ký.
- Loại token/profile được ký bằng khóa đó.
- Audience/resource mà các token hướng đến.
- Thời gian và chính sách phát hành token.

Nếu cùng một khóa được dùng cho nhiều loại token hoặc nhiều audience, thu hồi khóa có thể ảnh hưởng tất cả các nhóm đó. Một khóa dùng chung cho access token, ID Token, client assertion hoặc token nội bộ có thể tạo phạm vi ảnh hưởng lớn hơn dự kiến.

kid chỉ có ý nghĩa trong phạm vi issuer/key set tương ứng. Hai issuer độc lập có thể dùng cùng chuỗi kid; không được thu hồi hoặc tin khóa chỉ dựa trên kid mà thiếu ngữ cảnh issuer.

### 3.2. Ví dụ phạm vi ảnh hưởng

Giả sử issuer dùng cùng khóa signing-key-A để ký:

| Nhóm token | Audience | Thời hạn tối đa |
| --- | --- | --- |
| Access token đơn hàng | https://api.orders.example.org | 10 phút |
| Access token thanh toán | https://api.payments.example.org | 5 phút |
| ID Token | web-client-123 | 15 phút |

Nếu khóa A bị xâm phạm, chỉ xóa khóa khỏi cấu hình của API đơn hàng sẽ chưa đủ nếu API thanh toán và client OIDC vẫn tin khóa đó. Kẻ tấn công có thể tạo token giả cho các audience khác mà verifier vẫn chấp nhận.

Ngược lại, nếu hệ thống dùng khóa riêng theo issuer, loại token hoặc nhóm audience, có thể thu hẹp phạm vi ảnh hưởng. Việc phân tách khóa cần cân bằng với độ phức tạp quản lý, vận hành và xoay khóa.

### 3.3. Thu hồi khóa có thể làm mất hiệu lực cả token hợp lệ

Nếu khóa bị xâm phạm, verifier thường không thể phân biệt chắc chắn token hợp lệ do issuer tạo và token giả do kẻ tấn công tạo chỉ bằng chữ ký của cùng khóa. Cả hai đều có chữ ký toán học hợp lệ.

Vì vậy, biện pháp an toàn thường là từ chối toàn bộ token được ký bằng khóa bị xâm phạm, kể cả token phát hành trước thời điểm phát hiện, trừ khi hệ thống có bằng chứng độc lập đáng tin cậy để phân loại.

Không dựa hoàn toàn vào iat để giữ lại token cũ trong sự cố lộ khóa. Kẻ tấn công nắm khóa riêng có thể tạo token với iat lùi về quá khứ. Log phát hành ở issuer có thể hỗ trợ điều tra, nhưng chỉ giữ lại token nếu có cách xác minh độc lập rằng token thực sự đã được phát hành.

## 4. Planned rotation và emergency revocation khác nhau

| Tiêu chí | Planned rotation | Emergency revocation |
| --- | --- | --- |
| Lý do | Định kỳ, hết tuổi khóa, thay đổi chính sách hoặc chuẩn bị trước | Khóa bị lộ, nghi bị lạm dụng, sai phạm vi tin cậy |
| Mục tiêu | Chuyển sang khóa mới mà không gián đoạn | Ngừng tin khóa cũ nhanh nhất có thể |
| Khóa cũ | Thường tiếp tục xác minh token cũ đến khi hết hạn | Bị từ chối theo chính sách khẩn cấp |
| Giai đoạn overlap | Có chủ đích và có thời hạn | Thường phải rút ngắn hoặc loại bỏ |
| Cache JWKS | Có thể chờ hết TTL/overlap | Cần invalidation và denylist khẩn cấp |
| Ảnh hưởng người dùng | Thường ít thấy | Có thể buộc đăng nhập/cấp token lại |

Không dùng quy trình rotation thông thường cho một khóa đã bị xác nhận xâm phạm. Giữ khóa cũ trong JWKS chỉ để token cũ tiếp tục hoạt động sẽ tiếp tục cho phép verifier chấp nhận chữ ký do kẻ tấn công tạo.

## 5. Quy trình xoay khóa có kế hoạch

Với khóa chưa có dấu hiệu bị xâm phạm, mục tiêu là để issuer và verifier chuyển đổi đồng bộ:

1. **Tạo khóa mới:** tạo cặp khóa trong KMS/HSM hoặc vùng bảo vệ khóa phù hợp; cấp kid mới và không tái sử dụng ID cũ.
2. **Công bố khóa xác minh mới:** thêm public key vào JWKS hoặc cơ chế phân phối tin cậy trước khi issuer bắt đầu ký bằng khóa mới.
3. **Chờ verifier cập nhật:** cho các resource server tải/cập nhật khóa mới; kiểm tra cache và phân phối trên toàn bộ môi trường.
4. **Chuyển issuer sang ký bằng khóa mới:** phát hành token mới với kid mới.
5. **Giữ public key cũ trong giai đoạn overlap:** tiếp tục xác minh token đã ký bằng khóa cũ cho đến khi hết hạn tối đa và hết khoảng clock skew/cache cần thiết.
6. **Ngừng công bố khóa cũ:** chỉ sau khi không còn token hợp lệ cần xác minh bằng khóa đó.
7. **Hủy hoặc lưu trữ khóa riêng cũ:** theo chính sách lưu giữ và kiểm toán; bảo đảm khóa riêng cũ không còn được dùng để ký.

Ví dụ:

~~~text
Thời điểm T0: JWKS công bố K1
Thời điểm T1: JWKS công bố K1 + K2
Thời điểm T2: Issuer bắt đầu ký token mới bằng K2
Thời điểm T3: Token K1 cuối cùng hết hạn + clock skew
Thời điểm T4: Gỡ K1 khỏi JWKS và kết thúc overlap
~~~

Thời gian overlap phải dựa trên thời hạn token thực tế, clock skew, cache và thời gian cập nhật cấu hình. Không dùng một khoảng cố định cho mọi hệ thống.

## 6. Thu hồi khẩn cấp khi khóa bị xâm phạm

Khi có bằng chứng hoặc nghi ngờ đáng tin cậy rằng khóa riêng bị lộ, cần ưu tiên containment và xác định phạm vi ảnh hưởng.

### 6.1. Các bước xử lý

1. **Xác nhận phạm vi khóa:** xác định issuer, kid, thuật toán, loại khóa, mục đích sử dụng và các hệ thống đang tin khóa.
2. **Ngừng ký bằng khóa:** vô hiệu hóa quyền ký hoặc gỡ khóa riêng khỏi dịch vụ ký/KMS/HSM theo quy trình sự cố.
3. **Đánh dấu khóa không còn được tin:** thêm kid vào danh sách từ chối khẩn cấp tại verifier hoặc cập nhật trust configuration. Không chỉ dựa vào việc xóa khóa khỏi JWKS.
4. **Phân phối tín hiệu thu hồi:** làm mới JWKS/cache, đẩy cấu hình khẩn cấp và xác minh các resource server đã nhận chính sách mới.
5. **Tạo và công bố khóa thay thế:** chỉ sau khi kiểm soát được môi trường ký và bảo đảm khóa mới không bị lộ cùng nguồn.
6. **Chuyển issuer sang khóa mới:** xác nhận token mới mang kid mới và verifier chấp nhận đúng khóa mới.
7. **Vô hiệu hóa token/phiên bị ảnh hưởng:** áp dụng introspection, session revocation, denylist hoặc buộc cấp token mới theo mức độ sự cố.
8. **Điều tra và kiểm toán:** rà soát thời gian nghi lộ khóa, log ký, token đã phát hành, request bất thường và các hành động đã được chấp nhận.

### 6.2. Vì sao xóa khóa khỏi JWKS chưa đủ?

Một verifier có thể đang giữ public key cũ trong cache và tiếp tục xác minh token bằng khóa đó cho đến khi cache hết hạn. Một số hệ thống chỉ tải JWKS khi khởi động hoặc khi gặp kid chưa biết. Nếu không có cơ chế invalidation, việc xóa khóa trên máy chủ JWKS có thể không có tác dụng tức thời.

Đối với sự cố khẩn cấp, cần một tín hiệu từ chối khóa độc lập với JWKS cache, ví dụ:

- Danh sách issuer + kid bị thu hồi được phân phối tới verifier.
- Cấu hình denylist khẩn cấp có ưu tiên cao hơn cache khóa.
- Cơ chế push invalidation hoặc refresh có xác nhận.
- Policy gateway/resource server từ chối kid bị xâm phạm trước khi xác minh chữ ký.

Danh sách từ chối phải được bảo vệ, có audit và có cơ chế đồng bộ. Không để token tự chọn issuer hoặc endpoint rồi tự cập nhật danh sách tin cậy.

### 6.3. Thời gian thu hồi thực tế

Thời gian từ lúc quyết định thu hồi đến lúc toàn bộ verifier từ chối token phụ thuộc:

- TTL của JWKS cache.
- Cơ chế refresh khi nhận kid chưa biết.
- Khả năng phân phối cấu hình và invalidation.
- Số lượng resource server, region, gateway và ứng dụng client.
- Hành vi khi dịch vụ cấu hình hoặc JWKS tạm thời không khả dụng.

Nếu yêu cầu thu hồi trong vài giây, chỉ đặt JWKS cache TTL thấp có thể chưa đủ. Cần đo thời gian lan truyền và kiểm thử cơ chế khẩn cấp thực tế.

## 7. HMAC và khóa bất đối xứng có phạm vi thu hồi khác nhau

### 7.1. HMAC secret

Với HS256/HS384/HS512, issuer và verifier dùng chung secret. Nếu secret bị lộ ở một verifier, kẻ tấn công có thể tự tạo token có chữ ký hợp lệ đối với mọi hệ thống dùng cùng secret.

Khi thu hồi HMAC secret:

- Tất cả verifier đang dùng secret cũ phải ngừng chấp nhận nó.
- Issuer phải chuyển sang secret mới.
- Cần xác minh mọi bản sao secret trong cấu hình, biến môi trường, secret store, backup và pipeline triển khai.
- Nếu nhiều issuer/service dùng chung secret, phải đánh giá toàn bộ phạm vi đó.

HMAC có thể phù hợp trong một ranh giới tin cậy nhỏ, nhưng chia sẻ secret cho nhiều resource server làm tăng số nơi có thể ký token. Không thể chỉ thay secret ở issuer rồi cho rằng verifier cũ sẽ tự ngừng tin secret.

### 7.2. Chữ ký bất đối xứng

Với RS256, PS256, ES256 hoặc thuật toán bất đối xứng khác:

- Khóa riêng ký được giữ tại issuer hoặc dịch vụ ký được ủy quyền.
- Verifier chỉ cần khóa công khai.
- Khi khóa riêng bị xâm phạm, gỡ public key khỏi tập khóa được tin cậy và phân phối lệnh từ chối kid đó.
- Khóa công khai cũ có thể tiếp tục tồn tại trong cache, nên vẫn cần emergency denylist/invalidation.

Mô hình bất đối xứng giúp giới hạn quyền tạo chữ ký ở issuer, nhưng không tự giải quyết bài toán phân phối thu hồi đến mọi verifier.

### 7.3. Không nhầm khóa ký với khóa mã hóa

Nếu hệ thống dùng JWE hoặc Nested JWT, cần quản lý riêng:

- Khóa ký JWS: bảo vệ tính toàn vẹn và nguồn ký.
- Khóa mã hóa JWE: bảo vệ tính bí mật và khả năng giải mã.

Thu hồi khóa ký có thể làm verifier từ chối mọi JWS dùng khóa đó. Thu hồi khóa giải mã có thể khiến hệ thống không đọc được các JWE đã mã hóa bằng khóa cũ. Hai hành động có phạm vi và tác động vận hành khác nhau; không xoay hoặc xóa cả hai loại khóa như thể chúng có cùng vai trò.

## 8. Giảm phạm vi ảnh hưởng bằng thiết kế khóa

Phạm vi ảnh hưởng khi thu hồi phụ thuộc vào cách phân bổ khóa từ trước. Một khóa ký dùng cho mọi loại token và mọi API sẽ tạo ra blast radius lớn.

Có thể cân nhắc phân tách theo:

- Issuer hoặc môi trường (production, staging, development).
- Token profile (access token, ID Token, client assertion, token nội bộ).
- Nhóm audience/resource có ranh giới tin cậy khác nhau.
- Mức độ nhạy cảm hoặc yêu cầu thu hồi khác nhau.
- Khu vực hoặc miền bảo mật khi có nhu cầu vận hành rõ ràng.

Không nhất thiết tạo một khóa cho từng API nhỏ nếu chi phí quản lý vượt lợi ích. Hãy chọn ranh giới sao cho khi một khóa bị xâm phạm, hệ thống biết chính xác những token và consumer nào phải bị ảnh hưởng.

Các biện pháp hỗ trợ:

- Dùng KMS/HSM hoặc dịch vụ ký chuyên biệt để hạn chế truy cập khóa riêng.
- Giới hạn quyền gọi thao tác ký theo workload/client và mục đích.
- Audit mọi lần sử dụng khóa và thay đổi key status.
- Đặt tuổi tối đa cho khóa và lịch rotation.
- Dùng kid duy nhất trong phạm vi issuer và không tái sử dụng.
- Tách khóa giữa các môi trường; không dùng khóa staging cho production.
- Đặt giới hạn thời hạn access token để giảm cửa sổ token cũ còn được chấp nhận.

## 9. Phân biệt thu hồi khóa với thu hồi token hoặc phiên

Không phải mọi yêu cầu thu hồi đều cần vô hiệu hóa cả khóa ký:

| Cơ chế | Phạm vi | Trường hợp phù hợp | Giới hạn |
| --- | --- | --- | --- |
| Key revocation theo kid | Tất cả token được ký bằng khóa đó trong phạm vi issuer/profile áp dụng | Khóa bị lộ hoặc không còn được tin | Phạm vi rộng, có thể buộc nhiều người dùng đăng nhập lại |
| JWT ID denylist (jti) | Một token cụ thể | Token bị đánh cắp hoặc cấp sai | Cần lưu và tra cứu trạng thái; phải bảo đảm jti duy nhất theo issuer |
| Session revocation | Một phiên hoặc nhóm token của phiên | Logout, thiết bị mất, phiên có rủi ro | Cần liên kết token với session và kiểm tra trạng thái |
| Refresh token revocation/rotation | Khả năng cấp access token mới từ refresh token | Thu hồi quyền tiếp tục phiên | Access token đã phát hành vẫn có thể còn hạn nếu không có kiểm tra bổ sung |
| Token introspection | Trạng thái token theo authorization server | Cần quyết định trạng thái tập trung | Tăng phụ thuộc mạng và cần chính sách cache |
| Giảm thời hạn token | Token mới có cửa sổ sử dụng ngắn hơn | Giảm tác động của token bị lộ | Không thu hồi tức thời token hiện có |

kid giúp xác định khóa đã ký token; jti giúp định danh token. Không nhầm hai giá trị này và không dùng một danh sách jti để thay thế cơ chế từ chối khóa đã bị xâm phạm.

Nếu một issuer có log phát hành đầy đủ và token có jti, có thể lập danh sách token đã phát hành bằng khóa bị ảnh hưởng để phân tích hoặc thu hồi có chọn lọc. Tuy nhiên, khi khóa riêng đã bị lộ, attacker có thể tạo token giả với jti tùy ý; danh sách chỉ chứa token hợp lệ đã phát hành không tự phát hiện mọi token giả.

## 10. Cache, JWKS và hành vi khi không tìm thấy khóa

### 10.1. Cache cần có chính sách rõ

Verifier nên xác định:

- JWKS được cache bao lâu.
- Khi nào refresh: hết TTL, gặp kid chưa biết, nhận tín hiệu invalidation hoặc thay đổi cấu hình.
- Có cho phép tiếp tục dùng stale JWKS khi endpoint lỗi không.
- Cách phân phối emergency denylist và thời gian áp dụng tối đa.
- Cách xác nhận tất cả instance đã nhận phiên bản cấu hình mới.

Với rotation thông thường, dùng cache có kiểm soát giúp giảm tải JWKS endpoint. Với key compromise, tiếp tục dùng stale key có thể kéo dài thời gian chấp nhận token giả. Chính sách stale-if-error phải phân biệt rõ rotation bình thường và sự cố khóa bị xâm phạm.

### 10.2. kid không tìm thấy

Khi token có kid không nằm trong JWKS cache, verifier có thể refresh JWKS một lần theo chính sách để xử lý trường hợp issuer vừa công bố khóa mới. Nếu vẫn không tìm thấy khóa, token phải bị từ chối.

Không refresh vô hạn cho mỗi token có kid ngẫu nhiên. Kẻ tấn công có thể tạo nhiều token với kid khác nhau để gây tải lên JWKS endpoint. Cần rate limit, cache kết quả không tìm thấy trong thời gian ngắn phù hợp và giới hạn số lần refresh đồng thời.

### 10.3. Khóa đã bị thu hồi nhưng vẫn nằm trong cache

Emergency denylist theo issuer + kid phải được kiểm tra trước khi chấp nhận chữ ký. Dù cache vẫn chứa public key, verifier vẫn phải từ chối nếu key ID đã bị thu hồi.

Không chỉ kiểm tra trạng thái khóa ở lần tải JWKS. Trạng thái thu hồi cần được áp dụng tại mỗi quyết định xác minh hoặc thông qua một cơ chế cache trạng thái có độ trễ được giới hạn và đo lường.

## 11. Xác định và thông báo phạm vi ảnh hưởng

Khi một khóa bị thu hồi, nhóm vận hành cần lập danh sách thành phần chịu ảnh hưởng:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Issuer | Issuer nào đã sử dụng khóa? Có nhiều issuer dùng chung secret không? |
| kid | Token nào mang key ID này? Có trường hợp thiếu hoặc trùng ID không? |
| Algorithm/key type | Thuật toán và loại khóa nào bị ảnh hưởng? |
| Token profile | Access token, ID Token, assertion hay token nội bộ? |
| Audience | API/client/resource server nào đang chấp nhận các token này? |
| Thời hạn | Token có thể còn hiệu lực đến khi nào? |
| Verifier/cache | Instance nào đang cache khóa hoặc chưa nhận denylist? |
| KMS/HSM | Khóa riêng/secret đã được dùng ở đâu, ai có quyền truy cập? |
| Session/refresh | Phiên hoặc refresh token nào có thể cần thu hồi thêm? |

Thông báo sự cố nên nêu rõ issuer + kid, thời điểm áp dụng, nhóm token/audience bị ảnh hưởng, hành động yêu cầu ở verifier, cách xác nhận đã cập nhật và hướng xử lý người dùng bị đăng xuất. Không gửi khóa riêng, HMAC secret hoặc toàn bộ token qua kênh thông báo thông thường.

## 12. Kiểm thử khả năng thu hồi khóa

Không chỉ kiểm thử rằng issuer ngừng ký bằng khóa cũ. Cần kiểm thử toàn bộ đường đi từ quyết định thu hồi đến mọi verifier:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token ký bằng K1 trước planned rotation | Vẫn được chấp nhận trong overlap nếu còn hạn và policy cho phép |
| Token mới ký bằng K2 sau rotation | Được chấp nhận khi K2 đã được công bố và tin cậy |
| Token K1 hết hạn sau overlap | Bị từ chối theo thời gian |
| Token K1 sau emergency revocation | Bị từ chối dù chữ ký toán học hợp lệ |
| Verifier còn cache public key K1 | Emergency denylist vẫn khiến token K1 bị từ chối |
| Một region chưa nhận cấu hình thu hồi | Phát hiện qua telemetry; không tuyên bố thu hồi toàn hệ thống đã hoàn tất |
| Token có kid không tồn tại | Refresh có giới hạn, sau đó từ chối |
| Token có kid đã bị thu hồi | Từ chối mà không fallback sang khóa khác |
| Hai issuer có cùng chuỗi kid | Trạng thái thu hồi của issuer này không áp nhầm issuer kia |
| HMAC secret cũ còn ở một verifier | Kiểm thử phát hiện verifier chưa hoàn tất rotation/revocation |
| Token dùng thuật toán khác với cấu hình của khóa | Từ chối |
| JWE dùng khóa mã hóa cũ | Xử lý theo kế hoạch khóa mã hóa riêng, không nhầm với khóa ký |

Nên đo thời gian từ lúc phát lệnh thu hồi đến lúc verifier cuối cùng từ chối token. Đây là chỉ số thực tế về độ trễ thu hồi, không chỉ là thời gian cập nhật JWKS trên máy chủ.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ xóa khóa khỏi JWKS sẽ thu hồi tức thì | Verifier vẫn dùng khóa trong cache | Emergency denylist và cache invalidation có xác nhận |
| Giữ khóa bị lộ để token cũ tiếp tục chạy | Attacker vẫn có thể tạo token được chấp nhận | Từ chối toàn bộ token dùng khóa bị xâm phạm |
| Chỉ xoay khóa ở issuer | Verifier cũ vẫn tin khóa cũ | Cập nhật và xác minh mọi verifier |
| Dùng một khóa cho mọi loại token/audience | Sự cố một khóa ảnh hưởng toàn hệ thống | Phân tách khóa theo ranh giới tin cậy phù hợp |
| Dùng chung HMAC secret cho nhiều API | Mọi API có secret đều có thể ký token | Giới hạn phạm vi secret hoặc dùng chữ ký bất đối xứng |
| Coi kid là cơ chế thu hồi | Không có trạng thái thu hồi nào được thực thi | Dùng denylist/trust policy theo issuer và kid |
| Tin iat để giữ token trước thời điểm lộ khóa | Attacker có thể backdate token | Từ chối kid bị xâm phạm hoặc dùng bằng chứng phát hành độc lập |
| Refresh JWKS không giới hạn khi kid lạ | Có thể bị DoS vào endpoint khóa | Rate limit và giới hạn refresh |
| Xóa khóa giải mã cùng lúc với khóa ký | Không thể giải mã JWE còn cần xử lý | Quản lý vòng đời hai loại khóa riêng |
| Không kiểm thử region/instance cuối cùng | Một số verifier vẫn chấp nhận khóa cũ | Theo dõi rollout và xác nhận từng nhóm verifier |

## 14. Tình huống tự kiểm tra

Issuer phát hành access token bằng khóa RSA có kid=key-A. Khóa riêng bị lộ. Một số resource server tải JWKS mỗi 5 phút, một số instance có cache dài hơn. Issuer đã xóa public key A khỏi JWKS và bắt đầu ký bằng key-B.

**Câu hỏi 1:** Chỉ xóa key-A khỏi JWKS có bảo đảm mọi token ký bằng A bị từ chối ngay không?

**Trả lời:** Không. Verifier đang cache public key A vẫn có thể xác minh token bằng khóa đó. Cần phân phối trạng thái thu hồi issuer + key-A đến các verifier, vô hiệu cache hoặc dùng denylist có ưu tiên cao hơn JWKS cache, rồi xác nhận mọi instance đã áp dụng.

**Câu hỏi 2:** Có nên tiếp tục chấp nhận token key-A được phát hành trước lúc phát hiện lộ khóa không?

**Trả lời:** Khi khóa riêng đã bị lộ, chữ ký không phân biệt được token hợp lệ và token giả. Attacker còn có thể đặt iat lùi về quá khứ. Mặc định an toàn là từ chối tất cả token dùng key-A, trừ khi có bằng chứng phát hành độc lập đủ tin cậy cho một tập token cụ thể.

**Câu hỏi 3:** Việc đổi sang key-B có làm các refresh token cũ tự mất hiệu lực không?

**Trả lời:** Không nhất thiết. Refresh token có thể là opaque token hoặc được bảo vệ bằng cơ chế/khóa khác. Cần đánh giá vòng đời refresh token và session riêng; nếu sự cố ảnh hưởng phiên, phải thu hồi chúng theo cơ chế tương ứng.

**Câu hỏi 4:** Khi nào có thể kết luận sự cố thu hồi đã hoàn tất?

**Trả lời:** Khi issuer không còn ký bằng key-A, mọi verifier liên quan đã nhận chính sách từ chối key-A, các cache/trust path đã được xử lý, kiểm thử xác nhận token key-A bị từ chối trên toàn bộ audience/region và telemetry không còn ghi nhận verifier chấp nhận khóa bị thu hồi.

## 15. Ghi nhớ

Thu hồi theo khóa ký là biện pháp thu hồi diện rộng: nó có thể vô hiệu hóa mọi token được ký bằng khóa đó trong phạm vi issuer và verifier áp dụng chính sách. kid giúp nhận diện khóa, còn JWKS giúp phân phối khóa; cả hai không tự bảo đảm thu hồi tức thời vì verifier có thể cache khóa.

Với rotation có kế hoạch, công bố khóa mới trước khi ký bằng nó và giữ khóa cũ đến khi token cũ hết hạn. Với khóa bị xâm phạm, ngừng ký, đánh dấu issuer + kid không còn được tin, phân phối emergency denylist/invalidation và xác nhận mọi verifier đã từ chối khóa đó. Đánh giá riêng access token, ID Token, refresh token, session, HMAC secret và khóa mã hóa.

**Phạm vi thu hồi phải được thiết kế từ lúc phân bổ khóa, không đợi đến khi xảy ra sự cố mới xác định hệ thống nào đang tin khóa đó.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký JWS và protected header.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn khóa và JSON Web Key Set.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán chữ ký và mã hóa JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành an toàn khi chọn thuật toán, khóa và xác minh JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các ràng buộc xác minh.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): tra cứu trạng thái token tại authorization server.
