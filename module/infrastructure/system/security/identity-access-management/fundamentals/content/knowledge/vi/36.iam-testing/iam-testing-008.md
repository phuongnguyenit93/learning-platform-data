# Token validation test

## 1. Kiểm thử xác minh token nhằm chứng minh điều gì?

**Token validation test** kiểm chứng rằng một thành phần chỉ chấp nhận token đáp ứng đúng hợp đồng tin cậy của nó, đồng thời từ chối token sai định dạng, sai nguồn, sai bên nhận, hết hiệu lực hoặc không phù hợp với mục đích sử dụng.

Một API không nên tạo principal chỉ vì giải mã được payload hoặc nhìn thấy claim `sub`. Bộ test phải chứng minh token đã được xử lý theo loại credential, cấu hình trust và các điều kiện được yêu cầu tại ranh giới đó.

Ví dụ, một token có chữ ký hợp lệ do IdP doanh nghiệp phát hành nhưng dành cho `report-api` không tự được dùng tại `course-api`. Một ID token dành cho client đăng nhập cũng không mặc định là access token hợp lệ cho API. Các ca này quan trọng vì dữ liệu token có vẻ hợp lệ và có thể vượt qua những test chỉ kiểm tra chữ ký.

Mục tiêu không phải tạo thật nhiều chuỗi token lỗi rồi kiểm tra API trả mã khác 200. Cần biết **điều kiện nào đang bị vi phạm, request có đi qua validator thật không, và liệu hệ thống có ngăn việc tạo danh tính hoặc tác động được bảo vệ hay không**.

## 2. Xác định loại token và hợp đồng trước khi viết expected

### 2.1. Không có một validator chung cho mọi token

| Loại đầu vào | Bên thường sử dụng | Nội dung cần xác định khi kiểm thử |
| --- | --- | --- |
| Access token tự chứa | Resource server/API | Profile, issuer, audience, mật mã, thời hạn và các ràng buộc bổ sung |
| Access token opaque | API hoặc thành phần kiểm tra trạng thái | Cách tra cứu đáng tin cậy, trạng thái và metadata cần cho bên nhận |
| ID token OIDC | Client/Relying Party | Quy tắc xác minh danh tính và ràng buộc giao dịch của flow tương ứng |
| Refresh token | Token endpoint theo cơ chế được hỗ trợ | Ràng buộc client/grant và vòng đời; không coi là credential API thông thường |
| Token phiên riêng của ứng dụng | Ứng dụng đã thiết lập phiên | Hợp đồng session, nguồn phát hành, hiệu lực và thu hồi |
| Token có ràng buộc người giữ | Bên nhận hỗ trợ cơ chế tương ứng | Xác minh thêm bằng chứng ràng buộc, không chỉ đọc token |

JWT là một dạng biểu diễn claims, không phải một mục đích truy cập duy nhất. Những claims bắt buộc phụ thuộc profile/giao thức và ứng dụng; không phải mọi JWT đều có cùng bộ trường bắt buộc. Cần tách quy tắc định dạng khỏi hợp đồng sử dụng. [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519.html)

### 2.2. Ghi hợp đồng của ranh giới đang kiểm tra

Một hợp đồng minh họa cho API có thể nêu:

```yaml
boundary: course-api-bearer
credential: signed_jwt_access_token
trustedIssuer: https://identity.example.org
acceptedAudience: course-api
allowedAlgorithms:
  - RS256
requiredClaims:
  - iss
  - sub
  - aud
  - exp
  - iat
clockSkewSeconds: 0
unknownKeyBehavior: bounded_refresh_then_reject_if_unresolved
```

Đây là mô tả test minh họa, không phải cấu hình chuẩn của sản phẩm. `RS256`, tập claims và độ lệch thời gian bằng 0 là lựa chọn của ví dụ để có expected rõ; không phải khuyến nghị duy nhất cho mọi triển khai.

Hợp đồng còn cần xác định nguồn khóa, kiểu dữ liệu, ý nghĩa subject, loại token được phép, trạng thái thu hồi và hành vi khi phụ thuộc lỗi. Nếu có yêu cầu về độ mới xác thực, tenant hoặc bằng chứng người giữ, phải ghi chúng riêng; không suy ra từ việc chữ ký hợp lệ.

## 3. Chọn lớp kiểm thử đúng với điều cần chứng minh

### 3.1. Unit test của validator

Đưa token và ngữ cảnh xác minh vào validator thật, dùng clock, trust profile và nguồn khóa được kiểm soát. Kiểm tra chấp nhận/từ chối, principal đầu ra và phân loại lỗi theo hợp đồng nội bộ.

Nếu mock validator trả về một principal đã xác thực, test đó không kiểm tra token validation. Nó có thể kiểm tra controller hoặc authorization ở phía sau, nhưng cần đặt tên và báo cáo đúng phạm vi.

### 3.2. Integration test của ranh giới API

Gửi credential qua đường nhận thực tế của ứng dụng để kiểm tra bộ lọc, parser header, cấu hình validator và việc tạo security context. Cần chứng minh endpoint không bị vô tình loại khỏi chuỗi bảo mật hoặc nhận token bằng một cơ chế khác với dự kiến.

Một ca API âm tính nên xác nhận handler được bảo vệ không thực hiện nghiệp vụ. Không chỉ kiểm tra một exception trong validator mà bỏ qua việc filter có thể bắt exception rồi tiếp tục request.

### 3.3. Kiểm thử tích hợp với bên phát hành

Một tập ca dùng IdP/authorization server của môi trường thử có thể kiểm tra profile thật, audience, phát hành, luân chuyển và thu hồi. Lớp này bổ sung cho fixture tự ký, nhưng không thay thế khả năng tạo điều kiện lỗi có kiểm soát ở lớp thấp hơn.

Không dùng token người dùng thật hoặc credential production làm dữ liệu test. Mỗi môi trường cần namespace, khóa và tài khoản thử riêng để test không thể làm token thử được chấp nhận ngoài phạm vi dự kiến.

## 4. Tạo một token chuẩn làm đối chứng

### 4.1. Một fixture hợp lệ, một thời điểm cố định

Chọn đồng hồ điều khiển được tại thời điểm `T0`. Một payload minh họa cho profile của ví dụ:

```json
{
  "iss": "https://identity.example.org",
  "sub": "subject-test-17",
  "aud": "course-api",
  "iat": 1700000000,
  "nbf": 1700000020,
  "exp": 1700000330
}
```

Trong fixture này, đặt `T0 = 1700000030`, nên `iat = T0 - 30`, `nbf = T0 - 10`, `exp = T0 + 300`. Các số là dữ liệu thử với clock cố định, không phải token để sử dụng theo thời gian hiện tại.

Token được ký bằng khóa riêng **chỉ dành cho test**; validator tin khóa công khai tương ứng qua nguồn khóa thử được cấu hình. Header có thuật toán được phép và tham chiếu khóa đúng. Payload JSON ở trên chưa phải token đã ký và không được sử dụng trực tiếp làm credential.

Trước các ca âm tính, xác nhận fixture chuẩn được validator chấp nhận và principal có đúng issuer/subject. Với test API, bảo đảm endpoint thật sự thành công khi có cả token hợp lệ lẫn quyền cần thiết; nếu không, các ca sau có thể đều bị chặn vì nguyên nhân ngoài token.

### 4.2. Thay một điều kiện cần kiểm tra

Để kiểm tra audience sai, tạo token vẫn được ký hợp lệ nhưng có audience không dành cho API. Nếu chỉ sửa payload trong chuỗi token mà không ký lại, validator có thể từ chối vì chữ ký sai, và test chưa chứng minh audience được kiểm tra.

Quy tắc tương tự áp dụng cho `exp`, `nbf`, issuer, subject và claims bắt buộc. Riêng ca kiểm tra tính toàn vẹn phải cố ý sửa thông điệp mà không tạo chữ ký hợp lệ mới.

Một số ràng buộc không thể tách hoàn toàn do cách validator chọn trust profile. Không cần ép đúng thứ tự lỗi nội bộ nếu hợp đồng không yêu cầu, nhưng phải thiết kế fixture để điều kiện quan tâm thật sự được thách thức và có bằng chứng bổ sung khi cần.

## 5. Nhóm kiểm thử định dạng và cách nhận credential

| Ca | Mục đích kiểm chứng |
| --- | --- |
| Không có credential | Endpoint được bảo vệ không tạo principal mặc định |
| Scheme không được hỗ trợ | Không tự coi chuỗi bất kỳ là bearer token |
| Header thiếu phần token hoặc nhiều credential mâu thuẫn | Parser xử lý theo hợp đồng rõ, không chọn danh tính nhiều quyền hơn |
| Token sai số phần hoặc encoding không hợp lệ | Không đi tiếp với payload chưa được phân tích đúng |
| Payload/header sai kiểu dữ liệu | Không ép kiểu tùy tiện thành một danh tính hợp lệ |
| Token vượt giới hạn kích thước được thiết kế | Từ chối có kiểm soát, không làm cạn tài nguyên |
| JSON có field bảo mật trùng trong profile không cho phép | Không để parser và validator hiểu hai giá trị khác nhau |
| Dạng token không được hỗ trợ tại endpoint | Không tự chuyển sang một đường xác minh lỏng hơn |

Với duplicate fields hoặc encoding bất thường, cần tạo fixture giữ đúng chuỗi đầu vào. Nếu helper đọc JSON rồi serialize lại đã loại mất field trùng, ca test không còn kiểm tra điều kiện dự kiến.

Đừng mặc định mọi biểu diễn khác nhau của header đều phải bị từ chối; parser cần tuân theo giao thức và hợp đồng endpoint. Bộ test nên kiểm tra những hình thức được hỗ trợ hợp lệ và những hình thức bị cấm, tránh vô tình tạo một quy tắc riêng không tương thích.

## 6. Nhóm kiểm thử mật mã, thuật toán và nguồn khóa

Các quy tắc về thuật toán, khóa, audience và loại token cần dựa trên trust profile đã cấu hình, không do token tự quyết định. RFC 8725 nhấn mạnh việc xác minh thuật toán và tách quy tắc cho những loại JWT khác nhau. [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html)

Với profile minh họa chỉ chấp nhận JWT đã ký bằng `RS256`, các ca cần thiết gồm:

| Ca | Thiết lập | Expected tại ranh giới |
| --- | --- | --- |
| Khóa và thuật toán hợp lệ | Fixture chuẩn | Chấp nhận nếu các điều kiện khác đạt |
| Payload bị sửa | Đổi một byte payload, không ký lại hợp lệ | Từ chối |
| Chữ ký bị sửa | Đổi phần chữ ký của fixture | Từ chối |
| Khóa không thuộc trust | Ký bằng khóa test khác chưa được cho phép | Từ chối |
| Thuật toán ngoài danh sách | Token hợp lệ về mật mã theo thuật toán khác | Từ chối theo profile |
| Token không có bảo vệ chữ ký | Dạng không đáp ứng yêu cầu đã ký của profile | Từ chối |
| Tham chiếu khóa không giải quyết được | Không có khóa tin cậy tương ứng sau cơ chế xử lý được phép | Từ chối, không dùng khóa bất kỳ |
| Nguồn khóa do đầu vào tự khai | Token đề xuất một nguồn ngoài trust đã cấu hình | Không mở rộng trust hoặc tải tùy ý |

Một key ID chỉ là tham chiếu để chọn khóa trong ngữ cảnh được tin cậy; nó không tự chứng minh khóa có thẩm quyền. Bộ test có thể dùng nguồn khóa giả lập và quan sát lời gọi để xác nhận validator không truy cập một địa chỉ không được phép hoặc gây refresh vô hạn.

Kiểm tra lỗi thuật toán cần thực sự đi qua quyết định về thuật toán. Một fixture bị lỗi encoding ngay từ đầu chỉ chứng minh parser từ chối, không chứng minh allowlist được áp dụng. Tương tự, không dùng một helper test đã tự chặn mọi thuật toán lạ rồi coi đó là bằng chứng validator production an toàn.

## 7. Nhóm kiểm thử issuer, audience, subject và loại token

### 7.1. Đúng chữ ký chưa đủ

Một bên phát hành có thể cấp token cho nhiều client và API. Token được chấp nhận ở một bên nhận không tự được dùng ở nơi khác. Với profile minh họa, cần kiểm tra:

- Issuer đúng được chấp nhận; issuer khác hoặc thiếu issuer bị từ chối.
- Audience có bên nhận được phép được xử lý theo profile; audience không dành cho API hoặc thiếu audience bắt buộc bị từ chối.
- `aud` có dạng hợp lệ được hỗ trợ, kể cả danh sách nếu profile cho phép; kiểu dữ liệu khác bị xử lý đúng.
- Subject đáp ứng hợp đồng được chuyển sang principal đúng; subject thiếu/rỗng nếu bị cấm thì bị từ chối.
- Cùng chuỗi subject ở nguồn khác không bị ghép vào tài khoản của issuer được tin cậy.

Không chuẩn hóa issuer theo cách làm hai namespace khác nhau bị coi như một chỉ để test đạt. Các quy tắc so sánh phải lấy từ giao thức/profile đang sử dụng, không từ cảm nhận rằng hai URL “trông giống nhau”.

### 7.2. Ngăn dùng sai loại token

Tạo những fixture có hình thức tương tự nhưng mục đích khác: ID token, access token dành cho API khác, token xác nhận email hoặc token phiên riêng. Kiểm tra chúng không được chấp nhận ngoài hợp đồng, ngay cả khi cùng tổ chức phát hành hoặc cùng subject.

Nếu profile sử dụng kiểu token, audience, namespace claim hoặc khóa riêng để phân biệt, test phải bao phủ những ràng buộc đó. Không chỉ đổi một tên biến trong helper từ `idToken` sang `accessToken` rồi tin rằng fixture đã khác về ngữ nghĩa.

Refresh token không được biến thành credential của API tài nguyên chỉ vì backend cũng nhận ra chuỗi đó. Với token có ràng buộc người giữ, cần có ca token đúng nhưng bằng chứng bổ sung thiếu/sai; validation riêng chuỗi token không chứng minh ràng buộc đã được thực thi.

## 8. Kiểm thử thời gian bằng clock điều khiển được

### 8.1. Hết hạn và chưa tới hiệu lực

Theo ngữ nghĩa JWT, `exp` giới hạn thời điểm chấp nhận trước khi hết hạn; `nbf` biểu diễn mốc chưa được dùng trước đó. Dung sai đồng hồ, nếu có, phải được cấu hình và kiểm tra rõ. [RFC 7519, các claim thời gian](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.4)

Với ví dụ đặt skew bằng 0:

| Điều kiện tại `now` | Expected về điều kiện thời gian |
| --- | --- |
| `now = exp - 1` giây | Chưa hết hạn |
| `now = exp` | Hết hạn, bị từ chối |
| `now = exp + 1` giây | Hết hạn, bị từ chối |
| `now = nbf - 1` giây | Chưa tới hiệu lực, bị từ chối |
| `now = nbf` | Điều kiện `nbf` được thỏa |
| `now = nbf + 1` giây | Điều kiện `nbf` được thỏa |

Các hàng chỉ nói về ràng buộc đang xét; token vẫn phải đạt mọi điều kiện khác. Fixture cần có khoảng hiệu lực đủ để việc kiểm tra `nbf` không đồng thời thất bại vì `exp`.

Nếu triển khai cho phép skew, kiểm tra ngay trong, tại và ngoài biên dung sai theo hợp đồng thư viện/cấu hình. Không dùng độ lệch lớn trong test để mọi fixture luôn hợp lệ. Cũng không dùng thời gian ngủ thực chỉ để chờ token hết hạn nếu lớp test có thể điều khiển clock.

### 8.2. Required claims và kiểu dữ liệu

Trong profile của ví dụ, `exp` và `iat` bắt buộc, còn `nbf` có thể vắng mặt. Vì vậy ca thiếu `exp` phải bị từ chối, nhưng thiếu `nbf` không tự làm token sai nếu các điều kiện khác đều đạt.

Thử giá trị thời gian sai kiểu, đơn vị không đúng hợp đồng hoặc không thể biểu diễn trong thư viện. Không mặc định mọi field thời gian đều là chuỗi ngày hoặc tự chia mili giây để “sửa” đầu vào không hợp lệ.

`iat` không tự thay thế `auth_time` hoặc bằng chứng về việc người dùng vừa xác thực. Nếu profile quy định giới hạn tuổi token hay không cho thời điểm phát hành ở tương lai ngoài dung sai, bổ sung ca cho đúng các quy định đó. Không gán một quy tắc tùy ý cho mọi JWT rồi gọi đó là yêu cầu chung của định dạng.

## 9. Với OIDC, kiểm tra thêm ngữ cảnh giao dịch

ID token được xử lý tại client/RP theo flow OIDC tương ứng. OpenID Connect Core có các quy tắc xác minh riêng, gồm issuer, audience và các điều kiện về nonce/authorized party khi áp dụng. Bộ test cần lấy đúng profile và flow mà ứng dụng hỗ trợ. [OpenID Connect Core — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)

Những tình huống nên đưa vào thiết kế test gồm:

- Giao dịch hợp lệ và ID token tương ứng tạo đúng phiên/tài khoản.
- Request đã yêu cầu nonce nhưng token không có giá trị nonce phù hợp theo hợp đồng.
- Kết quả của giao dịch khác không được gắn vào ngữ cảnh hiện tại.
- Token dành cho client khác hoặc có cấu trúc audience/authorized party không thỏa điều kiện của flow bị từ chối.
- Khi có yêu cầu xác thực mới, dữ liệu thời điểm xác thực được kiểm tra đúng, không thay bằng thời điểm cấp token.

Các ca callback còn cần kiểm tra ràng buộc giao dịch của luồng đăng nhập; việc xác minh một ID token trong unit test không chứng minh callback thực tế đã xử lý đúng. `state`, `nonce` và PKCE có chức năng khác nhau, không nên coi chúng là một check trùng có thể tùy ý bỏ.

Với kiểm thử replay, xác định rõ đối tượng có tính sử dụng một lần. Không mặc định mọi bearer access token chỉ được sử dụng một request: nhiều access token được dùng lại trong thời hạn theo thiết kế. Ca replay của giao dịch đăng nhập, authorization code hoặc proof riêng cần expected của chính cơ chế đó.

## 10. Token opaque và introspection

Không cố parse mọi token thành JWT. Khi API dùng introspection, bộ test cần kiểm tra kênh và bên cung cấp kết quả đáng tin cậy, trạng thái `active` cùng metadata mà resource server cần.

RFC 7662 định nghĩa `active` là giá trị boolean trong phản hồi introspection. HTTP 200 không tự có nghĩa token đang hoạt động; phản hồi `active=false` là một kết quả cần được xử lý. [RFC 7662 — Introspection Response](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.2)

| Phản hồi/tình huống | Điều cần kiểm tra |
| --- | --- |
| `active=true` và metadata phù hợp | Chuyển sang kiểm tra quyền theo hợp đồng |
| `active=false` | Không tạo ngữ cảnh được chấp nhận cho tài nguyên |
| Thiếu `active` hoặc sai kiểu | Không ép thành true hoặc coi thiếu là hợp lệ |
| Metadata không đáp ứng bên nhận | Không dùng trạng thái active như quyền truy cập mọi API |
| Endpoint timeout/lỗi | Không biến lỗi phụ thuộc thành token hợp lệ |
| Phản hồi không đến từ nguồn tin cậy | Không chấp nhận chỉ vì JSON đúng schema |

Nếu `active=true` nhưng scope không đủ cho hành động, token có thể được chấp nhận ở bước validation rồi bị từ chối ở authorization. Bộ test phải phân biệt hai kết quả, thay vì ghi mọi lần không thực hiện được nghiệp vụ thành lỗi token.

Nếu thiết kế cache phản hồi introspection, cần kiểm tra cả độ mới, thời hạn token khi có và tác động của thu hồi. Một phản hồi đã cache không phải thông tin vừa được authorization server xác nhận ở thời điểm hiện tại.

## 11. Kiểm thử cache khóa, luân chuyển và thu hồi

### 11.1. Tập khóa có vòng đời

Một chuỗi trạng thái minh họa:

```text
Ban đầu: validator tin K1
  → đưa K2 vào nguồn khóa theo kế hoạch
  → token hợp lệ ký K2 được xác minh sau cập nhật được phép
  → K1 chỉ còn được tin trong phạm vi và khoảng chuyển tiếp đã thiết kế
  → khi K1 hết trust, token dựa vào K1 bị xử lý theo trạng thái mới
```

Expected phải theo kế hoạch luân chuyển và hợp đồng cache thực tế. Không tự thêm một khoảng chuyển tiếp cho khóa bị lộ, và không đòi validator lập tức biết mọi thay đổi nếu kiến trúc chưa có cơ chế bảo đảm tương ứng. Thay vào đó cần kiểm tra giới hạn và quy trình cập nhật đã cam kết.

Bổ sung ca nguồn khóa tạm lỗi, key ID không biết, nhiều request cùng cần refresh và dữ liệu nguồn quay về phiên bản cũ. Xác nhận không gây vòng refresh vô hạn, tải khuếch đại hoặc mở lại trust đã bị thu hồi ngoài thiết kế.

### 11.2. Thu hồi token không chỉ là kiểm tra chữ ký

JWT có chữ ký và thời gian còn hợp lệ chưa chắc phản ánh trạng thái tài khoản/grant mới nhất. Nếu hệ thống có kiểm tra thu hồi, trạng thái tài khoản hoặc phiên bản phiên, test phải đi qua chính đường đó.

Nếu API chỉ xác minh ngoại tuyến và không có cơ chế thu hồi khác, không viết expected rằng một token cũ mất hiệu lực tức thời chỉ vì hàng tài khoản đã bị khóa. Cần nêu đúng cửa sổ còn hiệu lực và các biện pháp mà kiến trúc thực tế sử dụng.

Với session, refresh token và access token, việc thu hồi có thể theo cơ chế khác nhau. Một test gọi endpoint logout thành công không chứng minh mọi loại credential ở mọi bên nhận đều đã bị vô hiệu hóa.

## 12. Assertion ở API: token bị từ chối phải dừng ở đâu?

Với token không được chấp nhận, cần kiểm tra theo hợp đồng của API:

- Không tạo principal đáng tin từ các claims chưa xác minh.
- Không gọi nghiệp vụ được bảo vệ hoặc tạo thay đổi trái phép.
- Không trả dữ liệu tài nguyên nhạy cảm trong body hoặc header.
- Phản hồi lỗi phù hợp, không chứa raw token, secret hoặc chi tiết nội bộ không cần thiết.
- Sự kiện quan sát phân biệt credential không hợp lệ với lỗi nguồn khóa/introspection khi hợp đồng yêu cầu.

Đừng gắn chặt mọi ca với một chuỗi exception có thể thay đổi giữa các phiên bản thư viện. Nên kiểm tra hành vi và phân loại lỗi ổn định mà ứng dụng công bố; chỉ kiểm tra thông báo chi tiết khi đó thật sự là hợp đồng cần giữ.

Với token hợp lệ, xác nhận principal có đúng nguồn và subject, rồi kiểm tra một thao tác được phép. Thêm một ca token hợp lệ nhưng thiếu quyền để chứng minh hệ thống không gộp “validation đạt” với “mọi hành động đều được phép”.

## 13. Ca test minh họa và cách tránh expected sai

```yaml
id: TOKEN_AUD_02
boundary: course-api-bearer
fixture:
  base: valid_access_token_at_fixed_clock
  change:
    aud: report-api
  signWith: trusted_test_key_K1
expected:
  credentialAccepted: false
  trustedPrincipalCreated: false
  protectedBusinessCall: none
  resourceState: unchanged
```

Schema chỉ minh họa dữ liệu test. `signWith` biểu diễn thao tác tạo fixture trong môi trường thử; không đưa khóa riêng vào tệp ca test hoặc log. Vì chữ ký vẫn hợp lệ theo khóa được tin cậy, ca này thách thức phạm vi bên nhận thay vì chỉ làm hỏng token ở mức byte.

Trình tự khái niệm:

```text
given: clock cố định, trust profile và nguồn khóa test
given: fixture chuẩn được chấp nhận trong cùng môi trường
given: biến thể có một vi phạm đã xác định
when:  đưa biến thể vào đúng ranh giới
then:  kiểm tra kết quả validation và principal
then:  kiểm tra handler/tài nguyên không bị tác động trái phép
```

Một ca audience có thể đạt giả nếu token chuẩn cũng bị từ chối vì hết hạn theo clock hệ thống, nguồn khóa test không truy cập được hoặc endpoint yêu cầu một điều kiện khác mà fixture chưa đáp ứng. Đối chứng dương và dữ liệu thử được kiểm soát là cách phân biệt lỗi bảo mật với lỗi thiết lập.

## 14. Duy trì bộ test và bằng chứng

Nhóm ca nên có định danh theo ràng buộc: định dạng, mật mã, trust, issuer, audience, loại token, thời gian, giao dịch, trạng thái và tác động thực thi. Gắn chúng với boundary/profile cụ thể, không gom mọi thứ vào một test “bad token”.

Khi cập nhật thư viện hoặc cấu hình trust, chạy các ca liên quan đến thay đổi và kiểm tra expected với hợp đồng. Không đổi expected chỉ vì phiên bản mới chấp nhận thêm một hình thức mà hệ thống chưa cho phép. Ngược lại, không mặc định một thay đổi về chuỗi lỗi là hồi quy bảo mật nếu hành vi bảo vệ vẫn đúng.

Bằng chứng test cần có case ID, profile, clock, phiên bản ứng dụng/cấu hình và kết quả quan sát. Không log raw credential hoặc tạo fixture từ token đã thu thập của người dùng thật. Fixture lỗi cũng có thể chứa thông tin nhạy cảm nếu được sửa từ dữ liệu thật.

Token validation test hiệu quả chứng minh đúng nguồn, đúng bên nhận, đúng loại, đúng hiệu lực và đúng ràng buộc của credential tại một ranh giới cụ thể. Khi kết hợp fixture hợp lệ, biến thể có mục tiêu và kiểm tra tác động ở phía sau validator, bộ test mới phát hiện được việc token bị chấp nhận sai thay vì chỉ chứng minh parser biết trả lỗi.
