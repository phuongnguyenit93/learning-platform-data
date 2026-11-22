# Từ chối an toàn khi cấu hình thiếu, khóa lỗi hoặc kiểm tra thất bại

## 1. Fail closed là nguyên tắc cốt lõi của xác minh JWT

Khi một hệ thống dùng JWT để quyết định quyền truy cập, hệ thống chỉ được cho phép request sau khi đã chứng minh token hợp lệ theo một chính sách tin cậy. Nếu không thể xác minh vì thiếu cấu hình, không tìm được khóa đáng tin cậy, lỗi thư viện mật mã hoặc một bước kiểm tra bắt buộc thất bại, kết quả phải là **không cấp quyền**.

Nguyên tắc này thường được gọi là **fail closed** hoặc **default deny**: khi không thể đưa ra quyết định bảo mật đáng tin cậy, hệ thống từ chối thao tác. Đối lập với nó là **fail open**, tức tiếp tục cho phép vì một kiểm tra bị lỗi hoặc không thực hiện được. Trong luồng xác minh token, fail open có thể biến một sự cố cấu hình hoặc hạ tầng thành đường vòng bỏ qua xác thực.

Fail closed không có nghĩa mọi lỗi đều phải trả cùng một mã HTTP hoặc mọi lỗi đều là lỗi token. Cần phân biệt:

- Token không hợp lệ: từ chối thông tin xác thực.
- Cấu hình hoặc khóa không hợp lệ: verifier không đủ điều kiện hoạt động an toàn.
- Dịch vụ phụ thuộc tạm thời không khả dụng: không thể xác minh ở thời điểm đó, nên vẫn từ chối quyền truy cập và báo lỗi vận hành phù hợp.
- Token hợp lệ nhưng không đủ quyền: xác thực thành công, nhưng từ chối hành động theo chính sách phân quyền.

Bài học thuộc chương **Xác minh token** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho issuer, verifier, API gateway và resource server; không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 2. Fail closed và fail open khác nhau thế nào?

### 2.1. Quy tắc quyết định

Một verifier chỉ được trả kết quả cho phép khi tất cả điều kiện bắt buộc đều đạt:

1. Cấu hình xác minh hợp lệ và đang hoạt động.
2. Token có định dạng và cấu trúc được hỗ trợ.
3. Thuật toán nằm trong allowlist của chính sách.
4. Khóa được chọn từ nguồn tin cậy, đúng loại và đúng mục đích.
5. Chữ ký hợp lệ theo đúng thuật toán.
6. Các claims bắt buộc và thời hạn hợp lệ.
7. Token thuộc đúng issuer, audience và loại credential.
8. Chính sách thu hồi, phiên và quyền truy cập bắt buộc đều đạt.

Nếu bất kỳ điều kiện bắt buộc nào không đạt hoặc không thể đánh giá, hệ thống không được cấp quyền.

### 2.2. Ví dụ fail open và fail closed

| Tình huống | Fail open (không an toàn) | Fail closed (đúng nguyên tắc) |
| --- | --- | --- |
| Không có cấu hình issuer | Bỏ kiểm tra issuer | Không khởi động/không sẵn sàng hoặc từ chối request |
| Allowlist thuật toán rỗng | Chấp nhận thuật toán token tự khai báo | Coi cấu hình không hợp lệ; không xác minh |
| Không đọc được khóa | Dùng khóa mặc định hoặc bỏ chữ ký | Không xác minh, từ chối quyền |
| Chữ ký sai | Bỏ qua bước verify để request tiếp tục | Từ chối token |
| Không tải được JWKS | Tin khóa trong header hoặc chấp nhận token không chữ ký | Chỉ dùng khóa cache còn hợp lệ theo policy; nếu không có thì từ chối |
| Thư viện xác minh phát sinh lỗi | Catch lỗi rồi trả về thành công | Phân loại lỗi và không cấp quyền |
| Thiếu claim bắt buộc | Điền giá trị mặc định rồi tiếp tục | Từ chối token |
| Không kiểm tra được trạng thái thu hồi bắt buộc | Bỏ qua kiểm tra thu hồi | Từ chối hoặc báo dịch vụ xác minh tạm thời không khả dụng |

### 2.3. Quy tắc đơn giản

**Chỉ kết quả xác minh thành công rõ ràng mới được phép chuyển sang bước phân quyền.** Không được diễn giải trạng thái `unknown`, `error`, `timeout`, `missing`, `malformed` hoặc `unsupported` thành `valid`.

Một hàm xác minh không nên chỉ trả về một giá trị boolean mà không phân biệt nguyên nhân vận hành. Tuy nhiên, dù phân loại nội bộ chi tiết đến đâu, chỉ trạng thái xác thực thành công mới được đi tiếp.

## 3. Cấu hình xác minh thiếu hoặc không hợp lệ

### 3.1. Những cấu hình bắt buộc phải có

Tùy loại token và kiến trúc, verifier thường cần các thông tin được cấu hình tin cậy:

- Issuer hoặc tập issuer được chấp nhận.
- Audience mong đợi của API/resource hiện tại.
- Danh sách thuật toán JWS được phép.
- Nguồn khóa tin cậy: khóa tĩnh, JWKS endpoint đã cấu hình hoặc kho khóa được quản trị.
- Chính sách chọn khóa, bao gồm cách xử lý `kid`.
- Claims bắt buộc, thời hạn token và clock skew cho phép.
- Loại token và chính sách phân quyền tương ứng.
- Chính sách thu hồi/introspection nếu hệ thống yêu cầu.

Không phải mọi JWT đều bắt buộc có cùng tập claims theo RFC. Điều quan trọng là verifier phải xác định rõ **claim nào bắt buộc đối với loại token và API cụ thể**. Nếu một claim được policy yêu cầu nhưng cấu hình policy bị thiếu, verifier không được tự suy ra giá trị mặc định.

### 3.2. Thiếu issuer hoặc audience

Nếu không biết issuer nào được tin cậy, verifier không có cơ sở để xác định nguồn phát hành. Nếu không biết audience mong đợi, verifier không thể chứng minh token được phát hành cho API đang xử lý request.

Không được:

- Chấp nhận bất kỳ giá trị `iss` nào trong token.
- Bỏ qua `aud` chỉ vì payload có chữ ký hợp lệ.
- Dùng issuer hoặc audience lấy từ request chưa được xác thực làm policy tin cậy.
- Tự động lấy JWKS từ URL do token cung cấp.

Trong hệ thống nhiều issuer, claim `iss` trong payload chưa xác thực có thể được dùng như **chỉ mục chọn một cấu hình issuer đã đăng ký trước**. Sau khi chữ ký hợp lệ, verifier vẫn phải xác nhận `iss` đúng tuyệt đối với issuer của cấu hình đó. Giá trị trong token không được tạo ra một issuer hoặc nguồn khóa mới.

### 3.3. Allowlist thuật toán bị thiếu hoặc rỗng

Verifier phải có danh sách thuật toán được phép từ cấu hình tin cậy. Nếu danh sách này trống, không đọc được hoặc không hợp lệ, đó là lỗi cấu hình. Không được:

- Chấp nhận mọi thuật toán mà token khai báo.
- Tự bật `none`.
- Tự chuyển từ RSA sang HMAC hoặc từ thuật toán này sang thuật toán khác.
- Chọn thuật toán dựa vào khả năng thư viện thay vì policy.
- Dùng thuật toán mặc định không được phê duyệt.

Một policy hợp lệ phải ràng buộc thuật toán với issuer, loại token và loại khóa tương ứng.

### 3.4. Thiếu cấu hình ở thời điểm khởi động

Nếu một thành phần bắt buộc để xác minh không tồn tại, lựa chọn an toàn thường là:

1. Không đánh dấu dịch vụ là ready.
2. Không nhận request cần xác minh JWT như thể dịch vụ hoạt động bình thường.
3. Ghi lỗi cấu hình có mã định danh và thông tin chẩn đoán không nhạy cảm.
4. Chỉ chuyển sang trạng thái sẵn sàng sau khi cấu hình hợp lệ được nạp và kiểm tra đầy đủ.

Tùy kiến trúc, có thể dừng tiến trình ngay khi khởi động hoặc để tiến trình chạy nhưng readiness ở trạng thái không sẵn sàng. Điểm bắt buộc là không phục vụ request với chính sách xác minh bị thiếu.

### 3.5. Cấu hình thay đổi khi hệ thống đang chạy

Nếu hỗ trợ reload cấu hình:

- Parse và kiểm tra toàn bộ cấu hình mới trước khi công bố.
- Kiểm tra issuer, audience, allowlist, nguồn khóa và các ràng buộc key/algorithm.
- Chỉ thay thế cấu hình đang dùng bằng một phiên bản hoàn chỉnh, hợp lệ theo cơ chế cập nhật nguyên tử.
- Không để request nhìn thấy trạng thái cấu hình nửa cũ nửa mới.
- Không giữ cấu hình cũ nếu nó đã bị thu hồi, vi phạm policy hoặc chứa khóa bị đánh dấu compromised.

Có thể tiếp tục dùng **last-known-good configuration** trong một lỗi cập nhật tạm thời chỉ khi cấu hình cũ vẫn còn hiệu lực, chưa bị thu hồi và policy cho phép. Nếu không chứng minh được điều đó, dịch vụ phải chuyển sang trạng thái không sẵn sàng hoặc từ chối xác minh.

## 4. Khóa thiếu, sai định dạng hoặc không đáng tin cậy

### 4.1. Không tìm thấy khóa

Với JWS dùng khóa bất đối xứng, verifier thường tra khóa theo `kid` trong tập khóa tin cậy. Nếu không tìm thấy:

1. Kiểm tra `kid` có tồn tại và đúng kiểu dữ liệu không.
2. Tìm trong key set đã cấu hình cho issuer tương ứng.
3. Nếu dùng JWKS từ xa, có thể thực hiện một lần refresh theo policy và giới hạn tần suất.
4. Nếu key vẫn không tồn tại, từ chối token.

Không được dùng khóa bất kỳ chỉ vì nó có thể xác minh chữ ký. Khóa phải thuộc đúng issuer và đúng mục đích.

### 4.2. Khóa sai định dạng hoặc sai loại

Các lỗi cần từ chối:

- JWK/PEM/DER bị hỏng hoặc parse không hoàn chỉnh.
- Khóa RSA có modulus không đáp ứng kích thước tối thiểu theo JWA/policy.
- Khóa EC không thuộc curve được thuật toán yêu cầu.
- Khóa OKP có `crv` không được hỗ trợ hoặc không khớp thuật toán.
- Khóa HMAC sau khi decode không đủ độ dài hoặc không đạt policy entropy.
- Khóa thiếu thành phần bắt buộc hoặc có tham số không hợp lệ.
- Khóa private/public không phải một cặp tương ứng khi issuer cần ký.
- Metadata `kty`, `crv`, `alg`, `use` hoặc `key_ops` mâu thuẫn với policy.

Không tự sửa khóa hỏng, cắt bớt byte, thay curve hoặc chuyển sang một loại khóa khác để thử cho token hoạt động.

### 4.3. Không có khóa mặc định để cứu request

Một lỗi nghiêm trọng là khi key lookup thất bại, ứng dụng dùng:

- Secret mặc định như `secret`, `change-me` hoặc chuỗi mẫu.
- Khóa development trong production.
- Public key được nhúng trong token hoặc tải từ URL chưa xác thực.
- Khóa cũ đã retire hoặc compromised.
- Một khóa của issuer khác có cùng `kid`.

Các cách này làm mất ranh giới tin cậy. Nếu không có khóa đúng, kết quả phải là không xác minh được.

### 4.4. Key ID và nguồn khóa

`kid` chỉ là định danh, không phải bằng chứng khóa đáng tin cậy. Verifier phải tra `kid` trong tập khóa đã cấu hình cho issuer; không dùng trực tiếp nó làm đường dẫn tệp, câu truy vấn hoặc URL.

Các header như `jku` hoặc `x5u` không được phép khiến verifier tải tài nguyên tùy ý do token chỉ định. Nếu hệ thống cần nguồn khóa từ xa, endpoint phải được cấu hình/đăng ký trước và được bảo vệ bằng chính sách mạng, TLS, redirect, cache và kiểm soát nguồn.

## 5. Lỗi khi tải JWKS và xử lý cache

### 5.1. Không có kết nối tới JWKS

Nếu JWKS endpoint không khả dụng, verifier không được mặc định rằng token hợp lệ. Cần phân biệt:

- **Có khóa cache còn hợp lệ:** có thể tiếp tục xác minh bằng khóa đó nếu cache vẫn nằm trong thời hạn và policy cho phép.
- **Có khóa cache đã quá hạn:** chỉ được dùng trong khoảng stale tối đa được policy quy định rõ, nếu không có thông tin khóa bị thu hồi/compromised và mô hình rủi ro cho phép.
- **Không có khóa phù hợp:** không thể xác minh; từ chối quyền.
- **Không tải được JWKS và không thể chứng minh khóa còn tin cậy:** từ chối quyền, báo lỗi phụ thuộc hạ tầng.

Không có một quy tắc cache stale phù hợp cho mọi hệ thống. Hệ thống nhạy cảm có thể yêu cầu không dùng khóa quá hạn; hệ thống khác có thể cho phép một khoảng stale ngắn để chịu lỗi mạng. Dù lựa chọn nào, giới hạn phải được cấu hình, đo lường và ghi lại, không được tự mở rộng vô thời hạn.

### 5.2. `kid` mới trong lúc JWKS lỗi

Nếu token chứa `kid` chưa có trong cache và JWKS không truy cập được, verifier không có căn cứ để tin khóa mới. Phải từ chối request cho đến khi có thể lấy và xác minh khóa từ nguồn tin cậy.

Không được:

- Bỏ qua chữ ký.
- Dùng khóa gần giống hoặc khóa cũ bất kỳ.
- Tin `jwk` nhúng trong header nếu profile không cho phép và không có cơ chế tin cậy rõ ràng.
- Tải URL tùy ý từ header.
- Chấp nhận token vì issuer “có vẻ đúng”.

### 5.3. Tránh refresh storm và DoS

Attacker có thể gửi nhiều token với `kid` ngẫu nhiên để buộc verifier liên tục tải JWKS. Cần:

- Giới hạn tần suất refresh.
- Dùng single-flight/coalescing để nhiều request cùng chờ một lần refresh.
- Negative-cache `kid` không tồn tại trong thời gian ngắn có giới hạn.
- Giới hạn kích thước response, số lượng JWK và thời gian tải.
- Chỉ tải từ endpoint đã cấu hình.
- Không để refresh thất bại làm verifier tự chuyển sang fail open.

Rate limit và cache chỉ bảo vệ tài nguyên; chúng không biến một khóa chưa xác minh thành khóa đáng tin.

### 5.4. Khóa bị thu hồi hoặc compromised

Nếu một khóa đã bị đánh dấu compromised, không được tiếp tục dùng khóa đó chỉ vì nó vẫn còn trong cache hoặc chữ ký token vẫn hợp lệ về mặt toán học. Cần có cơ chế phân phối trạng thái thu hồi và làm mất hiệu lực cache theo yêu cầu sự cố.

Last-known-good key set chỉ được giữ khi các khóa trong đó vẫn được policy cho phép. Khi có thông tin thu hồi, trạng thái thu hồi phải ưu tiên hơn tính sẵn sàng.

## 6. Thuật toán không được hỗ trợ hoặc không khớp khóa

### 6.1. Allowlist và thuật toán trong header

Protected header chưa được xác thực cho đến khi chữ ký hợp lệ. Verifier có thể đọc `alg` để đối chiếu với policy, nhưng không được để giá trị này tự quyết định cơ chế xác minh.

Từ chối khi:

- `alg` bị thiếu hoặc sai kiểu.
- `alg` không nằm trong allowlist.
- `alg` là `none` trong endpoint yêu cầu chữ ký.
- Thuật toán không được thư viện hoặc profile hỗ trợ.
- Thuật toán khai báo không khớp loại khóa.
- Tham số bắt buộc hoặc critical header không được hỗ trợ.

### 6.2. Không fallback giữa các họ thuật toán

Ví dụ một verifier dự kiến nhận `RS256` nhưng token khai báo `HS256`. Không được dùng RSA public key như HMAC secret để “thử xem có hợp lệ không”. Đây là kiểu lỗi algorithm confusion.

Tương tự:

- Không xác minh `RS256` bằng cơ chế `PS256`.
- Không dùng curve P-384 cho `ES256`.
- Không dùng khóa `OKP` như khóa `EC`.
- Không tự chuyển Ed448 sang Ed25519.
- Không hạ cấp sang thuật toán yếu hơn khi thư viện không hỗ trợ thuật toán được yêu cầu.

Mỗi issuer/loại token phải có policy thuật toán rõ ràng, ràng buộc với loại khóa và tham số tương ứng.

### 6.3. Không hiểu critical header thì phải từ chối

Nếu protected header chứa tham số `crit`, verifier phải hỗ trợ và thực thi mọi extension được đánh dấu critical. Nếu có extension không biết, không hỗ trợ hoặc không thể thực hiện đúng, phải từ chối token.

Không được bỏ qua `crit` để tiếp tục xác minh như thể header không có extension đó.

## 7. Chữ ký và cấu trúc token không hợp lệ

### 7.1. Lỗi định dạng JWS

Từ chối token nếu:

- Không có đúng số đoạn theo serialization mà endpoint chấp nhận.
- Base64URL sai định dạng hoặc không giải mã được.
- Header hoặc payload không phải JSON hợp lệ theo policy.
- Chữ ký sai độ dài hoặc sai định dạng.
- Token vượt giới hạn kích thước.
- Có tham số header không được hỗ trợ.
- Token dùng serialization khác với loại endpoint dự kiến.

Nếu endpoint chỉ chấp nhận JWS Compact, không tự đoán hoặc fallback sang JWE, nested JWT hay một định dạng khác.

### 7.2. Chữ ký không hợp lệ

Chữ ký sai, thiếu hoặc không xác minh được phải dẫn đến từ chối. Các lỗi có thể bao gồm:

- Payload hoặc header bị sửa.
- Sai public key hoặc secret.
- Sai thuật toán/hash/padding/curve.
- Sai định dạng chữ ký ECDSA DER/raw.
- Chữ ký bị cắt ngắn, thêm byte hoặc hỏng khi truyền.
- Thư viện mật mã trả lỗi hoặc timeout.

Không được bỏ qua bước verify khi gặp exception, trả `true` trong nhánh catch hoặc coi trạng thái `unknown` là hợp lệ.

### 7.3. Không tin claims trước khi chữ ký hợp lệ

Header và payload có thể được parse trước để định tuyến hoặc kiểm tra cấu trúc, nhưng dữ liệu đó vẫn là **untrusted input**. Không sử dụng `sub`, `role`, `scope`, `iss`, `aud` hoặc bất kỳ claim nào để cấp quyền trước khi chữ ký được xác minh.

Với hệ thống nhiều issuer, claim `iss` chưa xác thực chỉ được dùng để tìm một cấu hình issuer có sẵn. Sau xác minh, phải so khớp lại issuer chính xác và kiểm tra audience.

## 8. Lỗi claims và chính sách token

### 8.1. Claim bắt buộc bị thiếu

Nếu policy yêu cầu claim mà token không có hoặc có kiểu dữ liệu sai, phải từ chối. Ví dụ:

- Thiếu `iss` trong loại token yêu cầu issuer.
- Thiếu `aud` hoặc audience không chứa API hiện tại.
- Thiếu `exp` khi access-token policy bắt buộc thời hạn.
- `exp`, `nbf` hoặc `iat` có kiểu dữ liệu không hợp lệ.
- `scope` hoặc `roles` không đúng cấu trúc được quy định.
- Thiếu claim phân biệt loại token khi profile yêu cầu.

Không tự thêm claim mặc định hoặc diễn giải giá trị sai kiểu thành giá trị hợp lệ.

### 8.2. Token hết hạn hoặc chưa có hiệu lực

Verifier phải kiểm tra `exp` và `nbf` theo policy:

- `exp`: thời điểm token không còn được chấp nhận.
- `nbf`: thời điểm trước đó token chưa được chấp nhận.
- `iat`: thời điểm phát hành; có thể được kiểm tra để giới hạn tuổi token hoặc phát hiện giá trị bất thường.

NumericDate trong JWT tính theo giây từ Unix epoch. Chỉ cho phép clock skew nhỏ nếu policy quy định. Không tăng leeway tùy tiện khi gặp lỗi đồng hồ hoặc token bị từ chối.

Nếu đồng hồ hệ thống không đáng tin cậy và policy cần kiểm tra thời gian, verifier không thể đưa ra quyết định hợp lệ; cần khắc phục nguồn thời gian hoặc từ chối xác minh.

### 8.3. Sai issuer, audience hoặc token type

Một chữ ký hợp lệ không có nghĩa token phù hợp với mọi API. Từ chối khi:

- `iss` không đúng issuer được cấu hình.
- `aud` không chứa audience của resource hiện tại.
- Token type không đúng với loại credential endpoint yêu cầu.
- ID Token bị dùng thay access token hoặc ngược lại.
- Token có scope/role không đáp ứng quyền cần thiết.

Nên áp dụng quy tắc xác minh riêng cho từng loại token và endpoint để tránh nhầm lẫn giữa các JWT có cấu trúc gần giống nhau.

## 9. Lỗi hạ tầng và phụ thuộc xác minh

### 9.1. KMS/HSM hoặc dịch vụ mật mã không khả dụng

Nếu verifier cần gọi KMS/HSM hoặc dịch vụ xác minh từ xa và phụ thuộc đó timeout, trả lỗi hoặc không truy cập được:

- Không bỏ qua xác minh.
- Không chuyển sang một khóa cục bộ không được phê duyệt.
- Không dùng thuật toán khác để thử.
- Từ chối cấp quyền và ghi nhận lỗi phụ thuộc.
- Chuyển readiness/health theo chính sách vận hành nếu lỗi ảnh hưởng toàn bộ khả năng xác minh.

Nếu hệ thống có một bản public key đã được xác thực và được phép sử dụng cục bộ, có thể dùng bản đó theo policy. Nhưng không được tự tạo cơ chế fallback ngoài thiết kế.

### 9.2. Dịch vụ thu hồi hoặc introspection không khả dụng

JWT thường được xác minh cục bộ, nhưng một số hệ thống còn yêu cầu kiểm tra trạng thái phiên, denylist, token revocation hoặc introspection.

Nếu policy yêu cầu kiểm tra đó để quyết định quyền, không truy cập được dịch vụ phụ thuộc nghĩa là chưa thể chứng minh token được phép. Phải từ chối hoặc báo dịch vụ tạm thời không khả dụng.

Chỉ được bỏ qua một kiểm tra phụ thuộc khi policy được thiết kế rõ ràng cho phép điều đó, có giới hạn rủi ro và được phê duyệt trước. Không tự thay đổi policy trong lúc sự cố.

### 9.3. Timeout và retry

Retry có thể hữu ích với lỗi mạng tạm thời, nhưng cần:

- Timeout hữu hạn.
- Số lần retry giới hạn.
- Backoff có jitter.
- Circuit breaker và giới hạn đồng thời khi cần.
- Không lặp refresh JWKS hoặc gọi KMS không giới hạn.
- Không cho phép request tiếp tục khi retry hết mà không có kết quả xác minh thành công.

Hết retry mà vẫn không xác minh được thì kết quả là không cấp quyền.

## 10. Xử lý lỗi và phản hồi HTTP

### 10.1. Phân biệt lỗi token với lỗi dịch vụ

Fail closed là quyết định bảo mật; mã HTTP cần phản ánh đúng loại sự cố:

| Tình huống | Phản hồi thường phù hợp | Ghi chú |
| --- | --- | --- |
| Không có token hoặc bearer token không hợp lệ | `401 Unauthorized` | Có thể dùng challenge `WWW-Authenticate: Bearer` |
| Token hợp lệ nhưng thiếu quyền/scope | `403 Forbidden` | Xác thực thành công, phân quyền thất bại |
| Cấu hình verifier không hợp lệ | Dịch vụ không ready; nếu request vẫn đến thì không cấp quyền | Đây là lỗi vận hành, không phải bằng chứng token sai |
| JWKS/KMS/introspection bắt buộc tạm thời không khả dụng | Có thể trả `503 Service Unavailable` | Không cấp quyền; cho biết hệ thống chưa thể xác minh |
| Lỗi nội bộ bất ngờ | `5xx` phù hợp theo kiến trúc | Không biến exception thành thành công |

Đây là hướng dẫn HTTP thường dùng; hợp đồng API và profile triển khai có thể quy định chi tiết hơn. Dù mã phản hồi nào được chọn, kết quả không được cho phép thao tác khi xác minh chưa thành công.

### 10.2. Không tiết lộ chi tiết xác minh cho client

Không nên trả về các thông tin như:

- Secret hoặc nội dung private key.
- Toàn bộ JWK nội bộ hoặc vị trí kho khóa.
- Chi tiết parser/stack trace của thư viện mật mã.
- Token đầy đủ hoặc signing input nhạy cảm.
- Lý do chi tiết giúp attacker phân biệt các bước nội bộ trong một hệ thống có nguy cơ oracle.

Client thường chỉ cần biết thông tin xác thực không hợp lệ hoặc dịch vụ tạm thời không thể xử lý. Chi tiết phục vụ vận hành được ghi ở log nội bộ đã kiểm soát.

### 10.3. Phân loại lỗi nội bộ

Nên có các nhóm lỗi rõ ràng, ví dụ:

| Mã lỗi nội bộ | Ý nghĩa | Quyết định |
| --- | --- | --- |
| `CONFIG_MISSING` | Thiếu policy bắt buộc | Not ready / deny |
| `CONFIG_INVALID` | Cấu hình sai hoặc mâu thuẫn | Not ready / deny |
| `TOKEN_MALFORMED` | Token sai định dạng | Reject |
| `ALG_NOT_ALLOWED` | Thuật toán ngoài allowlist | Reject |
| `KEY_NOT_FOUND` | Không tìm thấy khóa tin cậy | Reject |
| `KEY_INVALID` | Khóa sai định dạng/loại/tham số | Reject hoặc not ready nếu lỗi cấu hình |
| `KEY_SOURCE_UNAVAILABLE` | Nguồn khóa bắt buộc không khả dụng | Deny / dependency unavailable |
| `SIGNATURE_INVALID` | Chữ ký không hợp lệ | Reject |
| `CLAIM_INVALID` | Claim bắt buộc sai hoặc thiếu | Reject |
| `REVOCATION_UNAVAILABLE` | Không kiểm tra được trạng thái thu hồi bắt buộc | Deny / dependency unavailable |
| `AUTHZ_DENIED` | Token hợp lệ nhưng không đủ quyền | Deny |

Các tên trên chỉ là ví dụ thiết kế. Không nhất thiết phải dùng đúng chuỗi này; điều quan trọng là hệ thống phân biệt được lỗi đầu vào, lỗi cấu hình, lỗi khóa, lỗi phụ thuộc và lỗi phân quyền.

## 11. Mã giả xác minh theo nguyên tắc fail closed

### 11.1. Luồng xác minh tổng quát

~~~text
function authorizeRequest(token, verifierPolicy, keyResolver):
    if verifierPolicy is missing or invalid:
        return DENY(CONFIG_INVALID)

    if verifierPolicy.expectedIssuer is empty:
        return DENY(CONFIG_MISSING)

    if verifierPolicy.allowedAlgorithms is empty:
        return DENY(CONFIG_INVALID)

    if verifierPolicy.expectedAudience is empty:
        return DENY(CONFIG_MISSING)

    parsed = strictParseExpectedJwtFormat(token)
    if parsed failed:
        return DENY(TOKEN_MALFORMED)

    header = parsed.protectedHeader
    if header.alg is missing:
        return DENY(ALG_NOT_ALLOWED)

    if header.alg not in verifierPolicy.allowedAlgorithms:
        return DENY(ALG_NOT_ALLOWED)

    if header contains unsupported critical parameters:
        return DENY(UNSUPPORTED_HEADER)

    keyResult = keyResolver.resolveOnlyFromTrustedSources(
        configuredIssuer = verifierPolicy.expectedIssuer,
        kid = header.kid,
        algorithm = header.alg
    )

    if keyResult is unavailable:
        return DENY(KEY_SOURCE_UNAVAILABLE)

    if keyResult has no matching trusted key:
        return DENY(KEY_NOT_FOUND)

    if key does not match algorithm, issuer or key policy:
        return DENY(KEY_INVALID)

    signingInput = originalHeader64 + "." + originalPayload64
    if signature verification is not explicitly successful:
        return DENY(SIGNATURE_INVALID)

    claims = parsePayloadStrictly(parsed.payload)
    if claims parsing failed:
        return DENY(CLAIM_INVALID)

    if claims.iss != verifierPolicy.expectedIssuer:
        return DENY(CLAIM_INVALID)

    if expected audience is not present in claims.aud:
        return DENY(CLAIM_INVALID)

    if required expiry is missing or now >= claims.exp:
        return DENY(CLAIM_INVALID)

    if claims.nbf exists and now < claims.nbf:
        return DENY(CLAIM_INVALID)

    if token type or other required claims fail:
        return DENY(CLAIM_INVALID)

    if required revocation check is unavailable:
        return DENY(REVOCATION_UNAVAILABLE)

    if revocation or authorization policy denies:
        return DENY(AUTHZ_DENIED)

    return ALLOW(validatedClaims)
~~~

Mã giả nhấn mạnh rằng chỉ nhánh cuối cùng mới cho phép. Trong triển khai thật, parser, key resolver và thư viện JOSE phải tuân thủ đúng chuẩn; không tự viết primitive mật mã. Nếu một thao tác ném exception hoặc trả trạng thái không xác định, lớp điều phối phải chuyển thành kết quả deny tương ứng.

### 11.2. Luồng ký token cũng phải fail closed

Nguyên tắc tương tự áp dụng cho issuer:

- Không có private key hợp lệ: không phát hành token.
- Key store/KMS không khả dụng: không bỏ qua chữ ký.
- Thuật toán không được policy cho phép: không tự chuyển sang thuật toán khác.
- Chữ ký tạo ra sai định dạng hoặc không thể xác minh bằng public key tương ứng: không phát hành token.
- Không tạo JWT không chữ ký để thay thế khi signer gặp lỗi.

Mã giả:

~~~text
function issueAccessToken(claims, signingPolicy, signer):
    if signingPolicy is missing or invalid:
        return ISSUE_FAILURE(CONFIG_INVALID)

    if signingPolicy.algorithm not in approvedAlgorithms:
        return ISSUE_FAILURE(ALG_NOT_ALLOWED)

    if signing key is missing, invalid, retired or compromised:
        return ISSUE_FAILURE(KEY_INVALID)

    result = signer.sign(claims, signingPolicy)
    if result is not explicitly successful:
        return ISSUE_FAILURE(SIGNING_FAILED)

    if output does not match expected JWS format:
        return ISSUE_FAILURE(SIGNATURE_FORMAT_INVALID)

    return result.token
~~~

Không trả token rỗng, token không chữ ký hoặc token ký bằng secret mẫu trong bất kỳ nhánh lỗi nào.

## 12. Health check, readiness và khả năng phục hồi

### 12.1. Phân biệt liveness và readiness

- **Liveness:** tiến trình còn hoạt động hay không.
- **Readiness:** dịch vụ có đủ điều kiện nhận request cần xác minh hay không.
- **Dependency health:** JWKS, KMS/HSM, nguồn thời gian, kho thu hồi hoặc dịch vụ bắt buộc có hoạt động không.

Một lỗi cấu hình cố định có thể khiến readiness không đạt dù tiến trình vẫn sống. Điều này giúp hệ thống điều phối không gửi traffic tới verifier chưa có policy hợp lệ.

Không nên để một lần timeout JWKS ngắn làm tiến trình restart liên tục nếu có thể xử lý qua cache và readiness policy. Nhưng cũng không được giữ readiness xanh vô thời hạn khi không còn khóa nào có thể được tin cậy.

### 12.2. Trạng thái sẵn sàng theo chính sách

Một dịch vụ có thể được coi là ready khi:

- Policy xác minh đã parse và kiểm tra thành công.
- Có ít nhất một cấu hình issuer/audience/algorithm hợp lệ cần thiết.
- Nguồn khóa có thể cung cấp khóa tin cậy hoặc cache còn hợp lệ theo policy.
- Crypto provider và key resolver có thể thực hiện các thao tác bắt buộc.
- Nguồn thời gian đủ tin cậy nếu kiểm tra thời hạn là bắt buộc.

Điều kiện cụ thể phụ thuộc kiến trúc. Readiness không được đánh dấu thành công chỉ vì tiến trình mở được cổng mạng.

### 12.3. Cập nhật cấu hình nguyên tử

Khi cập nhật JWKS hoặc policy:

1. Tải/nhận dữ liệu mới.
2. Parse và kiểm tra toàn bộ cấu trúc.
3. Kiểm tra key type, curve/modulus, metadata và issuer.
4. Áp dụng thông tin thu hồi hoặc compromised key.
5. Tạo snapshot hoàn chỉnh.
6. Công bố snapshot theo cách nguyên tử.
7. Giải phóng snapshot cũ theo chính sách cache và rotation.

Không để verifier đọc một key set đang cập nhật dở. Nếu bản mới không hợp lệ, không thay thế bằng dữ liệu nửa chừng; tiếp tục dùng snapshot cũ chỉ khi nó còn được phép tin cậy.

## 13. Logging, giám sát và ứng phó sự cố

### 13.1. Ghi nhận đủ để điều tra

Log nội bộ có thể ghi:

- Thời điểm và request/correlation ID.
- Issuer đã được cấu hình.
- `kid` và `alg` sau khi đã giới hạn độ dài/kiểu dữ liệu.
- Nhóm lỗi: malformed, key not found, signature invalid, claim invalid, dependency unavailable.
- Nguồn khóa/cache version đã dùng.
- Trạng thái refresh JWKS và độ tuổi cache.
- Kết quả readiness/dependency health.

Không ghi HMAC secret, private key, toàn bộ token, payload nhạy cảm hoặc dữ liệu xác thực có thể tái sử dụng. Nếu cần điều tra token cụ thể, dùng fingerprint an toàn theo quy trình đã phê duyệt và giới hạn quyền truy cập log.

### 13.2. Metrics và cảnh báo

Theo dõi:

- Tỷ lệ token bị từ chối theo nhóm lỗi.
- Số lần key lookup thất bại hoặc unknown `kid`.
- Tỷ lệ JWKS refresh lỗi, cache age và số lần refresh.
- Lỗi KMS/HSM và độ trễ ký/xác minh.
- Số lần cấu hình invalid hoặc reload thất bại.
- Readiness transitions.
- Tỷ lệ token sai chữ ký hoặc thuật toán không được phép.

Một đợt tăng đột biến unknown `kid` có thể là rotation chưa đồng bộ hoặc hoạt động gây DoS. Một đợt tăng SIGNATURE_INVALID có thể là token bị sửa, sai key deployment hoặc lỗi chuyển đổi định dạng. Cần phân tích theo nguồn và thời điểm, không tự động nới lỏng kiểm tra.

### 13.3. Runbook khi verifier bắt đầu từ chối hàng loạt

1. Xác định lỗi thuộc cấu hình, key parsing, JWKS, KMS/HSM, signature hay claims.
2. Kiểm tra thay đổi gần nhất về issuer, audience, allowlist, `kid`, key set và rotation.
3. Xác nhận public key đang dùng thuộc đúng issuer và còn được tin cậy.
4. Kiểm tra độ tuổi cache, trạng thái endpoint JWKS và giới hạn refresh.
5. Kiểm tra clock synchronization và policy thời hạn.
6. Khôi phục cấu hình/key set hợp lệ theo quy trình có kiểm soát.
7. Chỉ mở lại readiness khi xác minh đã hoạt động và test an toàn đạt.
8. Nếu nghi ngờ khóa bị lộ, ưu tiên thu hồi và rotation; không rollback để tiếp tục tin khóa compromised.

Không xử lý sự cố bằng cách tạm tắt xác minh chữ ký hoặc chấp nhận mọi thuật toán.

## 14. Kiểm thử fail closed

### 14.1. Kiểm thử cấu hình

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Thiếu issuer | Startup/readiness fail hoặc deny |
| Thiếu audience | Startup/readiness fail hoặc deny |
| Allowlist rỗng | Config invalid, không xác minh |
| JWKS endpoint không được cấu hình | Không tự lấy URL từ token |
| Cấu hình có issuer/algorithm mâu thuẫn | Từ chối nạp cấu hình |
| Reload cấu hình lỗi | Không công bố snapshot lỗi |
| Key bị đánh dấu compromised | Không sử dụng dù còn trong cache |

### 14.2. Kiểm thử khóa và chữ ký

- Khóa không tồn tại hoặc `kid` không tìm thấy.
- JWK/PEM/DER sai định dạng.
- Khóa sai `kty`, `crv`, modulus hoặc key usage.
- Secret HMAC quá ngắn.
- Chữ ký sai, bị cắt hoặc thêm byte.
- `alg` là `none` hoặc ngoài allowlist.
- Thuật toán không khớp loại khóa.
- Thư viện verify trả lỗi hoặc timeout.

Tất cả phải dẫn đến không cấp quyền.

### 14.3. Kiểm thử phụ thuộc

- JWKS timeout, DNS lỗi hoặc TLS validation thất bại.
- JWKS trả JSON sai hoặc key set không hợp lệ.
- `kid` mới xuất hiện khi JWKS không khả dụng.
- KMS/HSM không truy cập được.
- Dịch vụ revocation/introspection bắt buộc timeout.
- Nguồn thời gian không đáng tin cậy.
- Cache stale vượt giới hạn.

Verifier chỉ được tiếp tục dùng dữ liệu cache nếu policy cho phép rõ ràng và khóa chưa bị thu hồi. Các trường hợp khác phải deny.

### 14.4. Kiểm thử claims và quyền

- Thiếu `iss`, `aud` hoặc `exp` khi policy yêu cầu.
- `iss` sai hoặc audience không khớp.
- Token hết hạn hoặc chưa tới `nbf`.
- Sai token type.
- Scope/role không đủ.
- Token hợp lệ về chữ ký nhưng bị thu hồi.

Không được nhầm “chữ ký hợp lệ” với “được phép truy cập”.

## 15. Những hiểu lầm phổ biến

**“Nếu JWKS không truy cập được thì cứ bỏ qua xác minh để giữ dịch vụ hoạt động.”** Sai. Chỉ được dùng khóa cache còn được policy cho phép; nếu không có khóa đáng tin cậy thì không cấp quyền.

**“Cấu hình thiếu có thể dùng giá trị mặc định để chạy tạm.”** Sai với issuer, audience, thuật toán hoặc khóa tin cậy. Giá trị mặc định không được phê duyệt có thể tạo ranh giới tin cậy ngoài ý muốn.

**“Bắt exception rồi trả success giúp tránh gián đoạn.”** Sai. Exception trong bước bảo mật không phải kết quả xác minh thành công.

**“Token có chữ ký đúng thì không cần kiểm tra claims.”** Sai. Chữ ký không chứng minh audience, thời hạn, loại token hoặc quyền phù hợp.

**“Unknown kid thì thử tất cả khóa có sẵn.”** Không nên. Chỉ tra trong tập khóa tin cậy đã ràng buộc với issuer và thuật toán; không thử khóa ngoài policy.

**“Last-known-good luôn an toàn để dùng mãi.”** Sai. Khóa cũ có thể bị thu hồi hoặc compromised; stale cache phải có giới hạn và tôn trọng thông tin thu hồi.

**“Fail closed nghĩa là luôn trả 401.”** Không hẳn. Token sai thường là 401; thiếu quyền thường là 403; phụ thuộc xác minh không khả dụng có thể là 503. Điểm chung là không cấp quyền.

**“Từ chối an toàn có nghĩa phải dừng toàn bộ hệ thống.”** Không nhất thiết. Có thể giữ tiến trình sống, đánh dấu readiness không đạt hoặc chỉ từ chối những luồng phụ thuộc cấu hình lỗi. Nhưng không được phục vụ request bằng cách bỏ kiểm tra.

## 16. Câu hỏi tự kiểm tra

1. Fail closed khác fail open như thế nào trong luồng xác minh JWT?
2. Vì sao allowlist thuật toán rỗng phải được xem là lỗi cấu hình?
3. Nếu claim `iss` chưa xác thực được dùng để chọn issuer config, cần kiểm tra lại điều gì sau khi chữ ký hợp lệ?
4. Khi JWKS endpoint không khả dụng, điều kiện nào cho phép sử dụng khóa cache?
5. Vì sao không được dùng khóa mặc định hoặc khóa development khi key lookup thất bại?
6. Nếu thư viện xác minh ném exception, vì sao không thể coi request là hợp lệ?
7. Phân biệt 401, 403 và 503 trong một hệ thống fail closed.
8. Last-known-good configuration có thể được giữ trong điều kiện nào và khi nào phải loại bỏ?
9. Nếu revocation/introspection là kiểm tra bắt buộc nhưng dịch vụ đó timeout, hệ thống nên xử lý thế nào?
10. Những test âm tính nào cần có để chứng minh verifier thực sự fail closed?

## 17. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), cấu trúc JWS và protected header.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), JWK/JWKS và metadata khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), thuật toán JWS và tham số khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), claims và NumericDate.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), xử lý bearer token và phản hồi lỗi xác thực.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), khuyến nghị xác minh thuật toán, khóa, issuer, audience và loại JWT.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), ngữ nghĩa các mã trạng thái HTTP như 401, 403 và 503.
