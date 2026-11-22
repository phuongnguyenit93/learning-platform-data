# Phiên bản lược đồ claims và tương thích với bên sử dụng

## 1. Vì sao cần quản lý phiên bản lược đồ claims?

Một **JSON Web Token (JWT)** mang tập claims mà issuer phát hành theo một hợp đồng nhất định. Consumer dựa trên hợp đồng đó để đọc định danh, audience, thời hạn, ngữ cảnh và thông tin quyền. Khi hệ thống phát triển, hợp đồng có thể thay đổi: thêm claim, bỏ claim, đổi kiểu dữ liệu, thu hẹp tập giá trị hoặc thay đổi ý nghĩa của một claim đang tồn tại.

Nếu issuer và consumer triển khai thay đổi ở những thời điểm khác nhau, chúng có thể không còn hiểu token theo cùng một cách. Ví dụ:

- Issuer bắt đầu phát hành `tenant_id` nhưng consumer cũ chỉ biết `organization_id`.
- Issuer đổi `roles` từ chuỗi sang mảng, trong khi consumer cũ chỉ xử lý chuỗi.
- Consumer mới yêu cầu claim `account_status`, nhưng token cũ chưa có trường này.
- Issuer giữ nguyên tên `role` nhưng đổi ý nghĩa từ vai trò toàn hệ thống sang vai trò trong một tenant.

Những thay đổi này có thể làm gián đoạn dịch vụ hoặc tạo lỗi phân quyền nếu consumer tự suy diễn cách chuyển đổi. **Phiên bản lược đồ claims (claims schema version)** giúp issuer và consumer xác định bộ quy tắc cấu trúc, kiểu dữ liệu và ngữ nghĩa nào đang áp dụng.

JWT không có một trường phiên bản lược đồ chung bắt buộc cho mọi ứng dụng. RFC 7519 định nghĩa định dạng JWT và các registered claims, còn phiên bản hợp đồng claims thường do token profile hoặc hệ thống tự quy định. Không nên nhầm phiên bản hợp đồng claims với phiên bản của chuẩn JWT.

## 2. Phân biệt phiên bản JWT, token profile và schema claims

Ba khái niệm có liên quan nhưng không đồng nghĩa:

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **JWT specification** | Định dạng và quy tắc nền được mô tả trong tiêu chuẩn JWT | RFC 7519 |
| **Token profile** | Quy tắc sử dụng JWT cho một mục đích/giao thức cụ thể, gồm loại token, header, claims và validation | JWT access token theo RFC 9068 |
| **Claims schema version** | Phiên bản hợp đồng cấu trúc và ngữ nghĩa claims do profile/hệ thống quản lý | Schema access token nội bộ phiên bản 2 |

Một hệ thống có thể cập nhật schema từ phiên bản 1 lên phiên bản 2 mà vẫn sử dụng cùng định dạng JWT và cùng thuật toán ký. Ngược lại, việc thay đổi thuật toán hoặc khóa ký không nhất thiết làm schema claims đổi phiên bản.

Ví dụ, JWT header có thể chứa `typ` để chỉ loại nội dung/token theo profile. Với JWT access token theo RFC 9068, giá trị `at+jwt` được dùng để nhận diện loại token. `typ` không mặc nhiên là trường phiên bản schema claims. Chỉ dùng header hoặc claim làm dấu phiên bản khi hợp đồng đã quy định rõ ý nghĩa của nó.

## 3. Những thay đổi cần đánh giá tương thích

Không phải mọi thay đổi đều có mức ảnh hưởng giống nhau. Trước khi sửa schema, cần đánh giá cả **cấu trúc** lẫn **ngữ nghĩa**.

### 3.1. Thay đổi thường có thể tương thích

Một thay đổi có thể tương thích nếu consumer hiện tại vẫn đọc và xử lý token mới theo cách an toàn:

- Thêm một claim tùy chọn mới mà consumer cũ cho phép bỏ qua claim chưa biết.
- Bổ sung một giá trị metadata không ảnh hưởng quyết định bảo mật.
- Mở rộng tài liệu hoặc mô tả mà không đổi tên, kiểu và ý nghĩa claim.
- Thêm một giá trị mới vào một trường mà mọi consumer liên quan đã được thiết kế để xử lý giá trị chưa biết an toàn.

Tuy nhiên, **thêm optional claim không luôn tương thích**. Consumer dùng schema nghiêm ngặt với `additionalProperties: false` có thể từ chối token có trường mới. Một consumer có thể bỏ qua claim lạ ở phiên bản cũ, nhưng consumer khác lại yêu cầu allowlist chính xác. Phải kiểm tra hành vi thực tế của từng consumer.

### 3.2. Thay đổi thường không tương thích

Các thay đổi sau thường làm token cũ hoặc consumer cũ không còn đáp ứng hợp đồng:

- Thêm một claim mới vào danh sách bắt buộc.
- Xóa claim mà consumer đang yêu cầu.
- Đổi kiểu dữ liệu, ví dụ string thành number hoặc object thành array.
- Đổi cấu trúc object lồng nhau hoặc kiểu phần tử trong array.
- Đổi định dạng, đơn vị hoặc miền giá trị theo cách consumer cũ không hiểu.
- Đổi ngữ nghĩa nhưng giữ nguyên tên claim.
- Thu hẹp enum khiến một giá trị trước đây hợp lệ bị từ chối.
- Đổi tên claim mà không có cơ chế chuyển đổi.

Đặc biệt, **đổi ngữ nghĩa là thay đổi không tương thích ngay cả khi tên và kiểu dữ liệu không đổi**. Ví dụ `tenant_id` trước đây là tenant đang chọn, sau đó lại biểu thị tenant sở hữu tài khoản. Consumer cũ vẫn đọc được chuỗi nhưng có thể áp dụng sai ranh giới dữ liệu.

### 3.3. Bảng phân loại thay đổi

| Thay đổi | Rủi ro | Cách xử lý khuyến nghị |
| --- | --- | --- |
| Thêm optional claim | Consumer strict có thể từ chối | Kiểm tra unknown-claim policy; triển khai consumer hỗ trợ trước |
| Thêm required claim | Token cũ thiếu trường | Tạo profile/schema mới và rollout theo giai đoạn |
| Bỏ optional claim | Consumer có thể vẫn phụ thuộc | Kiểm tra usage, ngừng phát hành theo lộ trình |
| Bỏ required claim | Consumer có thể mong đợi dữ liệu | Cập nhật hợp đồng và consumer; không bỏ âm thầm |
| Đổi string thành array | Parser cũ sai kiểu | Dùng claim mới hoặc phiên bản schema mới |
| Thêm giá trị enum | Consumer có thể dùng switch/allowlist đóng | Xác định cách xử lý giá trị lạ; cập nhật consumer trước |
| Bỏ giá trị enum | Token cũ có thể không còn hợp lệ | Chờ token cũ hết hạn và xử lý dữ liệu chuyển tiếp |
| Đổi ý nghĩa claim | Có nguy cơ sai quyền dù schema vẫn hợp lệ | Tên mới hoặc profile mới; không tái định nghĩa tại chỗ |
| Đổi tên claim | Consumer cũ không tìm thấy | Giai đoạn dual-read/dual-write có kiểm soát |
| Tăng kích thước/danh sách claim | Vượt giới hạn header hoặc parser | Đánh giá giới hạn và tối ưu payload |

## 4. Backward compatibility và forward compatibility

Các thuật ngữ backward/forward compatibility đôi khi được dùng theo góc nhìn khác nhau. Để tránh mơ hồ, hãy nêu rõ **ai là phiên bản cũ, ai là phiên bản mới và token nào đang được xử lý**.

Trong bài này:

- **Consumer cũ với token mới:** consumer đã triển khai trước đó có thể xử lý token do issuer mới phát hành hay không?
- **Consumer mới với token cũ:** consumer vừa nâng cấp có thể xử lý token còn hiệu lực do issuer cũ phát hành hay không?

Hai chiều cần được kiểm thử riêng. Một thay đổi có thể hoạt động ở chiều này nhưng hỏng ở chiều còn lại.

### 4.1. Ma trận issuer/consumer

| Issuer | Consumer | Câu hỏi cần xác minh |
| --- | --- | --- |
| Cũ | Cũ | Hành vi nền trước khi thay đổi |
| Mới | Cũ | Consumer cũ có chấp nhận claim mới/giá trị mới không? |
| Cũ | Mới | Consumer mới có hỗ trợ token cũ trong thời gian chuyển đổi không? |
| Mới | Mới | Hai bên có cùng áp dụng schema mới không? |

Không chỉ kiểm thử một cặp issuer/consumer mới nhất. Trong thời gian rollout, các tổ hợp cũ/mới có thể cùng hoạt động vì token đã phát hành còn hạn và nhiều API chưa được cập nhật đồng thời.

### 4.2. Ví dụ thêm claim

Schema phiên bản 1 có:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17"
}
```

Phiên bản 2 thêm claim tùy chọn `account_tier`:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "account_tier": "business"
}
```

Consumer cũ chỉ tương thích nếu nó chấp nhận claim bổ sung và không từ chối token do schema strict. Consumer mới phải tiếp tục xử lý token cũ khi `account_tier` vắng mặt, nếu profile quy định claim này là optional. Nếu một thao tác mới thực sự cần `account_tier`, thao tác đó phải kiểm tra sự hiện diện và tính hợp lệ riêng.

## 5. Cách định danh phiên bản schema

Không có một cách duy nhất phù hợp mọi kiến trúc. Hãy chọn một cách rõ ràng, ổn định và được ràng buộc với issuer, audience cùng loại token.

### 5.1. Cấu hình schema theo issuer và audience

Consumer có thể cấu hình sẵn rằng:

```text
issuer: https://identity.example.org
audience: https://api.orders.example.org
token_profile: orders-access-token
schema_version: 2
```

Ưu điểm:

- Không cần thêm claim phiên bản vào mọi token.
- Consumer kiểm soát được profile nào được phép cho từng issuer/audience.
- Không phải dựa vào giá trị phiên bản do bên phát hành tùy ý đưa vào payload.

Hạn chế là cần quản lý cấu hình đồng bộ giữa các consumer và có kế hoạch khi một issuer phát hành nhiều profile khác nhau.

### 5.2. Claim phiên bản được định nghĩa trong hợp đồng

Một hệ thống có thể định nghĩa custom claim để thể hiện phiên bản:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "https://claims.example.org/profile_version": "2"
}
```

Tên claim và giá trị `2` chỉ là quy ước minh họa. JWT không định nghĩa một claim phiên bản schema chung tên `version`, `ver` hay `schema_version` cho mọi ứng dụng.

Nếu sử dụng claim phiên bản:

- Định nghĩa tên, kiểu dữ liệu, tập giá trị và ý nghĩa trong hợp đồng.
- Quy định phiên bản nào áp dụng cho issuer, audience và loại token nào.
- Xác minh chữ ký và các ràng buộc token trước khi tin claim phiên bản trong payload.
- Chỉ ánh xạ giá trị phiên bản vào một schema nằm trong allowlist cấu hình.
- Từ chối phiên bản không hỗ trợ hoặc không phù hợp với issuer/audience.

Không cho một claim phiên bản chưa được xác minh lựa chọn schema lỏng hơn để bỏ qua kiểm tra bảo mật. Consumer có thể phân tích JSON cơ bản trước khi xác minh, nhưng không dùng giá trị đó để đưa ra quyết định tin cậy.

### 5.3. Phân biệt claim phiên bản với JOSE header

JOSE header có các tham số như `alg`, `kid`, `typ`. Chúng phục vụ xử lý và nhận diện token theo cơ chế JOSE/profile. `typ` có thể giúp phân biệt loại token, nhưng không tự động là phiên bản schema claims.

Header được đọc trước khi xác minh để biết cách tiến hành xác minh, vì vậy các giá trị trong header ban đầu vẫn là dữ liệu chưa tin cậy. Thuật toán và khóa được phép phải lấy từ cấu hình tin cậy, không để token tùy ý chọn. Sau khi xác minh, consumer mới sử dụng thông tin header đã được bảo vệ theo profile.

Không nhầm `kid` (định danh khóa) với phiên bản schema; xoay khóa ký không đồng nghĩa thay đổi hợp đồng claims.

### 5.4. Chọn schema khi thiếu marker

Nếu token cũ không có claim phiên bản, consumer cần một quy tắc rõ ràng để nhận diện profile cũ, chẳng hạn cấu hình issuer/audience/loại token và thời hạn chuyển đổi. Không đoán phiên bản dựa trên việc “token có vẻ chứa trường nào”.

Nếu nhiều schema cùng chấp nhận một cấu trúc nhưng có ý nghĩa bảo mật khác nhau, consumer phải có cách phân biệt đáng tin cậy hoặc từ chối token mơ hồ.

## 6. Chiến lược rollout khi thay đổi schema

### 6.1. Thêm claim optional mới

Đây thường là thay đổi dễ triển khai hơn, nếu consumer cũ được phép bỏ qua claim lạ.

Trình tự gợi ý:

1. Công bố hợp đồng claim mới, kiểu dữ liệu và ngữ nghĩa.
2. Kiểm tra consumer hiện tại có từ chối unknown claim hay không.
3. Cập nhật consumer để chấp nhận claim mới nhưng không phụ thuộc bắt buộc vào nó.
4. Kiểm thử token cũ và token mới.
5. Cập nhật issuer để bắt đầu phát hành claim.
6. Chỉ bật chức năng phụ thuộc claim sau khi consumer cần thiết đã sẵn sàng.

Nếu consumer cũ dùng schema đóng, phải cập nhật hoặc định tuyến token theo profile trước khi issuer phát hành claim mới.

### 6.2. Thêm claim required mới

Không thể phát hành ngay claim mới rồi đồng thời yêu cầu mọi consumer cũ phải có nó. Một quy trình chuyển đổi an toàn:

1. Định nghĩa schema/profile phiên bản mới.
2. Cập nhật consumer để hỗ trợ cả profile cũ và mới, mỗi profile có validation rõ ràng.
3. Triển khai consumer mới trước, xác nhận các phiên bản đã sẵn sàng.
4. Cập nhật issuer để phát hành token theo profile mới cho audience/consumer tương ứng.
5. Theo dõi tỷ lệ token cũ/mới và lỗi validation.
6. Chờ token cũ hết hạn, cộng khoảng clock skew và thời gian cache/propagation cần thiết.
7. Ngừng chấp nhận profile cũ khi không còn consumer hoặc token hợp lệ cần hỗ trợ.

Nếu không thể hỗ trợ song song, cần một thời điểm chuyển đổi có kiểm soát và chấp nhận khả năng gián đoạn đã được đánh giá.

### 6.3. Đổi tên hoặc đổi kiểu claim

Giả sử phiên bản 1 dùng `roles` là chuỗi, phiên bản 2 cần mảng chuỗi. Không nên đổi kiểu tại chỗ trong khi consumer cũ vẫn đang chạy.

Có thể dùng claim mới trong giai đoạn chuyển tiếp:

```json
{
  "roles": "order_reader",
  "https://claims.example.org/roles": ["order_reader"]
}
```

Ví dụ trên chỉ minh họa kỹ thuật chuyển đổi. Hợp đồng phải chỉ rõ claim nào là nguồn chuẩn, cách xử lý khi hai giá trị không khớp và thời điểm dừng claim cũ. Không để mỗi consumer tự chọn giá trị ưu tiên.

### 6.4. Loại bỏ schema cũ

Chỉ ngừng hỗ trợ schema cũ khi:

- Issuer đã ngừng phát hành token cũ.
- Token cũ đã hết hạn hoặc được thu hồi theo cơ chế tin cậy.
- Cache, hàng đợi hoặc thành phần trung gian không còn giữ token cũ cần xử lý.
- Các consumer liên quan đã chuyển sang profile mới.
- Log và metric không còn ghi nhận việc sử dụng hợp lệ của schema cũ trong khoảng theo dõi đã định.

Không xóa validation cũ chỉ vì issuer đã triển khai bản mới; access token đã phát hành vẫn có thể còn hiệu lực.

## 7. Chiến lược đọc/ghi song song (dual-read và dual-write)

### 7.1. Dual-read

Consumer tạm thời hỗ trợ cả tên claim cũ và mới:

- Nếu chỉ có claim cũ, chuyển đổi theo quy tắc đã định.
- Nếu chỉ có claim mới, dùng claim mới.
- Nếu cả hai cùng có và tương đương, chấp nhận theo quy tắc.
- Nếu cả hai cùng có nhưng mâu thuẫn, từ chối token hoặc áp dụng hành vi lỗi được hợp đồng quy định.

Không dùng fallback kiểu “thử trường mới, nếu sai thì dùng trường cũ” cho claims đặc quyền mà không xác định rõ trường hợp sai. Cách đó có thể che giấu dữ liệu mâu thuẫn.

### 7.2. Dual-write

Issuer có thể phát hành cả claim cũ và mới trong giai đoạn tương thích. Chỉ làm vậy khi:

- Hai trường có ánh xạ xác định và cùng nguồn dữ liệu có thẩm quyền.
- Không có khả năng tạo hai giá trị mâu thuẫn.
- Consumer cũ và mới đều hiểu cách xử lý.
- Có thời điểm dừng phát hành claim cũ.

Dual-write kéo dài làm tăng kích thước token và nguy cơ drift. Hãy đặt ngày kết thúc, metric theo dõi và điều kiện gỡ bỏ rõ ràng.

### 7.3. Không thay đổi ngữ nghĩa dưới cùng một tên

Nếu claim cũ và mới có ngữ nghĩa khác nhau, không dual-write cùng một tên hoặc ánh xạ chúng như thể tương đương. Dùng tên riêng hoặc profile riêng để consumer không diễn giải nhầm. Thay đổi ý nghĩa của claim đặc quyền là thay đổi bảo mật, cần đánh giá và kiểm thử như một thay đổi breaking.

## 8. Quản lý nhiều issuer và nhiều consumer

Một hệ thống lớn có thể nhận token từ nhiều issuer, và mỗi issuer có thể phát hành token cho nhiều audience. Không nên giả định tất cả đều dùng cùng một schema chỉ vì cùng là JWT.

Hãy quản lý hợp đồng theo một tổ hợp rõ ràng:

| Thành phần | Câu hỏi quản lý |
| --- | --- |
| Issuer (`iss`) | Bên nào được phép phát hành token và claims nào? |
| Audience (`aud`) | Consumer/resource server nào được phép nhận? |
| Token type/profile | Access token, ID token hay loại token chuyên biệt nào? |
| Schema version | Cấu trúc và ngữ nghĩa claims nào đang áp dụng? |
| Signing keys | Khóa nào được phép xác minh token của issuer? |
| Validation policy | Claims nào required, optional, conditional và giá trị nào hợp lệ? |

Ví dụ, cùng một issuer có thể phát hành access token cho API đơn hàng và API thanh toán. Hai API có thể cần tập claim khác nhau. Một claim `payment_limit` không nên được chấp nhận ở API đơn hàng chỉ vì issuer cũng phát hành claim đó cho API thanh toán.

Consumer nên dùng cấu hình allowlist gắn với issuer, audience và profile để xác định schema được chấp nhận. Không chọn schema chỉ dựa trên tên claim tùy biến hoặc dữ liệu client gửi.

## 9. Token còn hạn trong thời gian chuyển đổi

JWT là dữ liệu đã phát hành và ký tại một thời điểm. Khi issuer nâng schema, token cũ không tự thay đổi. Một consumer mới có thể tiếp tục nhận token cũ cho đến khi hết hạn, trừ khi có cơ chế thu hồi hoặc giới hạn khác.

Khi lập kế hoạch chuyển đổi, cần tính đến:

- Thời hạn sống tối đa của access token cũ.
- Clock skew được cho phép khi kiểm tra `exp` và `nbf`.
- Thời gian cache token ở client, gateway hoặc dịch vụ trung gian.
- Thời gian đồng bộ cấu hình và khóa giữa các consumer.
- Khả năng refresh token tạo access token theo profile mới.
- Cơ chế thu hồi hoặc introspection nếu cần chấm dứt token trước hạn.

Không dùng `iat` hoặc một claim phiên bản do client kiểm soát để tự động tin token cũ hơn. Việc chấp nhận schema cũ phải nằm trong chính sách có thời hạn và ràng buộc với issuer/audience cụ thể.

## 10. Schema versioning và key rotation là hai việc khác nhau

Hai thay đổi thường diễn ra gần nhau nhưng cần được quản lý riêng:

| Thay đổi | Ảnh hưởng chính | Cách kiểm soát |
| --- | --- | --- |
| Schema versioning | Tên, kiểu, required/optional, ý nghĩa claims | Profile/schema registry, rollout consumer/issuer, tương thích token cũ |
| Key rotation | Khóa ký dùng để tạo/xác minh token | JWKS/key distribution, `kid`, overlap khóa cũ/mới, thu hồi khóa bị xâm phạm |

Có thể xoay khóa mà không đổi schema. Cũng có thể đổi schema mà vẫn ký bằng khóa hiện tại. Nếu thực hiện đồng thời, hãy kiểm thử cả hai chiều: token schema cũ ký bằng khóa cũ và token schema mới ký bằng khóa mới trong giai đoạn overlap.

Không dùng `kid` để biểu thị schema version; `kid` nhận diện khóa. Không coi việc thay khóa là cách thu hồi mọi token cũ nếu hệ thống vẫn chấp nhận khóa cũ trong thời gian chuyển tiếp.

## 11. Kiểm thử tương thích trước khi phát hành

Một bộ kiểm thử schema versioning nên bao gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Issuer cũ phát hành token cũ, consumer cũ nhận | Hoạt động như baseline |
| Issuer mới thêm optional claim, consumer cũ nhận | Chấp nhận nếu unknown-claim policy cho phép |
| Issuer mới phát hành schema mới, consumer mới nhận | Validation và xử lý đúng |
| Consumer mới nhận token cũ | Hỗ trợ trong thời gian chuyển đổi nếu profile cũ còn được phép |
| Token thiếu claim mới nhưng profile cũ hợp lệ | Không từ chối nhầm theo schema mới |
| Token schema mới thiếu claim required mới | Từ chối |
| Claim đổi kiểu dữ liệu | Không tự ép kiểu hoặc diễn giải khác |
| Claim cũ và mới cùng có nhưng mâu thuẫn | Từ chối hoặc xử lý theo quy tắc chuyển đổi rõ ràng |
| Claim phiên bản không được hỗ trợ | Từ chối an toàn |
| Claim phiên bản đến từ token sai chữ ký | Không dùng nó để chọn schema tin cậy |
| Token đúng schema nhưng sai issuer/audience | Từ chối |
| Token cũ còn hạn sau khi issuer nâng cấp | Xử lý theo chính sách overlap đã định |
| Token cũ hết hạn hoặc bị thu hồi | Từ chối theo quy tắc thời gian/trạng thái |
| Schema mới làm token tăng kích thước | Vẫn nằm trong giới hạn truyền tải/parser |

Nên kiểm thử bằng token đã ký trong môi trường kiểm thử, không chỉ kiểm tra JSON payload độc lập. Đồng thời kiểm tra metric và log để nhận diện consumer nào còn sử dụng schema cũ.

## 12. Ví dụ triển khai chuyển từ schema 1 sang schema 2

Giả sử schema 1 có:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "roles": "order_reader"
}
```

Schema 2 chuẩn hóa `roles` thành mảng và bổ sung claim phiên bản theo namespace:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "roles": ["order_reader"],
  "https://claims.example.org/profile_version": "2"
}
```

Lộ trình có thể gồm:

1. Công bố schema 2 và quy tắc ánh xạ `roles` cũ sang mảng.
2. Triển khai consumer có thể đọc schema 1 và schema 2, với validation riêng cho từng phiên bản.
3. Kiểm thử token schema 1, schema 2 và trường hợp version marker sai/không hỗ trợ.
4. Bật issuer phát hành schema 2 theo audience hoặc nhóm consumer đã sẵn sàng.
5. Theo dõi số lượng token schema 1 còn được chấp nhận và lỗi của consumer.
6. Chờ token schema 1 hết hạn, tính cả clock skew và cache.
7. Ngừng phát hành và sau đó ngừng chấp nhận schema 1 theo chính sách đã công bố.

Nếu token trong giai đoạn chuyển tiếp chứa cả `roles` cũ và mới, issuer phải tạo hai giá trị từ cùng một nguồn có thẩm quyền. Consumer phải từ chối nếu hai giá trị không tương đương theo quy tắc ánh xạ. Không tự chọn giá trị có nhiều quyền hơn.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Nghĩ JWT có sẵn claim version chuẩn | Các bên tự hiểu `ver` hoặc `version` khác nhau | Định nghĩa profile/version claim rõ ràng |
| Thêm required claim ngay lập tức | Consumer/token cũ bị từ chối | Rollout song song và có thời gian overlap |
| Chỉ kiểm thử issuer mới với consumer mới | Bỏ sót tổ hợp cũ/mới đang chạy thực tế | Kiểm thử ma trận issuer/consumer |
| Đổi kiểu nhưng giữ tên claim | Consumer có thể parse sai hoặc ép kiểu nguy hiểm | Claim mới hoặc schema version mới |
| Đổi ngữ nghĩa nhưng giữ nguyên tên | Quyết định phân quyền sai mà không có lỗi parse | Định nghĩa tên/profile mới |
| Tin version marker trước khi xác minh token | Kẻ tấn công có thể chọn schema yếu hơn | Chỉ dùng marker sau xác minh và allowlist |
| Dùng `kid` làm schema version | Trộn lẫn vòng đời khóa với hợp đồng dữ liệu | Quản lý key rotation và schema version riêng |
| Xóa schema cũ ngay khi issuer nâng cấp | Token cũ còn hạn bị từ chối bất ngờ | Chờ hết hạn/thu hồi và theo dõi usage |
| Dual-write không có ngày kết thúc | Payload phình to, logic phức tạp và drift | Đặt tiêu chí và thời điểm gỡ bỏ |
| Mặc định claim mới khi bị thiếu | Có thể cấp quyền hoặc ngữ cảnh sai | Fail closed với dữ liệu cần cho bảo mật |

## 14. Tình huống tự kiểm tra

Một issuer đang phát hành schema 1, trong đó `roles` là chuỗi. Hệ thống muốn chuyển sang schema 2, trong đó `roles` là mảng chuỗi. Một số consumer đã nâng cấp, một số consumer cũ vẫn đang chạy. Access token có thời hạn tối đa 10 phút.

**Câu hỏi 1:** Issuer có thể đổi ngay `roles` thành mảng cho tất cả consumer không?

**Trả lời:** Không nếu consumer cũ vẫn mong đợi chuỗi. Cần triển khai consumer hỗ trợ schema 2 trước hoặc định tuyến profile theo audience/consumer; sau đó mới chuyển issuer.

**Câu hỏi 2:** Consumer mới có nên tiếp tục nhận token schema 1 không?

**Trả lời:** Có thể, nếu schema 1 vẫn nằm trong danh sách profile được chấp nhận và validation riêng cho schema 1 còn được duy trì trong thời gian chuyển đổi. Không được dùng schema 2 để diễn giải token schema 1 theo kiểu ép kiểu.

**Câu hỏi 3:** Một token có `profile_version = "99"` nhưng chữ ký chưa được xác minh. Consumer có nên chọn schema 99 để parse và xử lý không?

**Trả lời:** Không. Marker chưa được xác minh là dữ liệu không đáng tin. Consumer chỉ chọn schema từ cấu hình tin cậy và marker đã được xác minh; phiên bản không hỗ trợ phải bị từ chối.

**Câu hỏi 4:** Sau khi issuer ngừng phát hành schema 1, có thể xóa ngay validation schema 1 không?

**Trả lời:** Không. Token schema 1 đã phát hành có thể vẫn còn hạn hoặc đang được cache. Chỉ ngừng hỗ trợ khi token cũ đã hết hạn/thu hồi và consumer không còn cần xử lý chúng.

## 15. Ghi nhớ

Phiên bản schema claims là phiên bản của **hợp đồng dữ liệu và ngữ nghĩa** giữa issuer với consumer. Hãy phân loại thay đổi trước khi triển khai, xác định rõ issuer/audience/token profile áp dụng, kiểm thử cả consumer cũ với token mới lẫn consumer mới với token cũ, và dành thời gian overlap cho token đã phát hành.

Ưu tiên thay đổi bổ sung có kiểm soát khi consumer có thể bỏ qua claim mới an toàn. Với thay đổi kiểu, tên, required hoặc ngữ nghĩa, dùng profile/schema version mới và rollout theo giai đoạn. **Không để token cũ bị diễn giải theo schema mới chỉ vì tên claim vẫn giống nhau.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT, Claims Set và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh issuer, audience, thuật toán và phân biệt loại token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): ví dụ về token profile và quy tắc claims/header của access token.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): kiểu dữ liệu và cấu trúc JSON.
