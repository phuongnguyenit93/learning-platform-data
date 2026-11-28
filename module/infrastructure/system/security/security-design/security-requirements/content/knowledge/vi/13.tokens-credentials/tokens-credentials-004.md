# Token issuer

## 1. Token issuer là ai và vì sao cần được đặc tả?

**Token issuer** là chủ thể phát hành token và chịu trách nhiệm về các khẳng định được đưa vào token theo một chính sách xác định. Trong một hệ thống truy cập API, issuer thường là authorization server hoặc một thành phần được giao nhiệm vụ phát hành credential.

Ví dụ, nền tảng học tập có một dịch vụ identity cấp access token để người học gọi API khóa học. API cần biết không chỉ token có chữ ký hợp lệ hay không, mà còn chữ ký đó thuộc issuer nào và issuer ấy có được tin cậy để cấp loại token này cho API hay không.

Nếu bất kỳ dịch vụ nào tự ký token cũng được chấp nhận, kẻ tấn công có thể dựng một issuer riêng, tự khai quyền quản trị và gửi token vào hệ thống. Việc token có cấu trúc hợp lệ hoặc có chữ ký kiểm tra được bằng một public key bất kỳ không thiết lập được quyền truy cập.

Mục tiêu của yêu cầu bảo mật là xác định **ai được phát hành token nào, dựa trên căn cứ nào, cho chủ thể và tài nguyên nào, đồng thời bên nhận phải kiểm tra điều gì trước khi tin token**.

## 2. Issuer, subject, audience và client là các vai trò khác nhau

Trong JWT, claim `iss` nhận diện bên phát hành; `sub` nhận diện chủ thể; `aud` nhận diện bên nhận dự kiến. JWT cơ sở không bắt buộc mọi ứng dụng phải dùng tất cả registered claims, nên profile của hệ thống phải quy định rõ claim nào bắt buộc. [RFC 7519, mục 4.1](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1).

Các vai trò trong nền tảng giả định có thể được biểu diễn như sau:

| Vai trò | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Issuer | Dịch vụ identity production | Ai chịu trách nhiệm cấp token và nội dung của token? |
| Subject | Người học hoặc workload | Token đang nói về chủ thể nào? |
| Audience | API khóa học | Tài nguyên nào được phép tiếp nhận token này? |
| Client | Ứng dụng web học tập | Ứng dụng nào tham gia yêu cầu token? |
| Resource server | Dịch vụ thực thi API | Thành phần nào kiểm tra token rồi quyết định truy cập? |

Không dùng tên client thay thế audience nếu profile không định nghĩa như vậy. Không đồng nhất subject với con người trong mọi luồng: một token dành cho workload có thể mô tả chính ứng dụng hoặc một chủ thể máy.

Trong thiết kế nhiều issuer, bản ghi người dùng nên giữ nguồn gốc identity. Hai token có cùng `sub` nhưng thuộc hai issuer khác nhau không tự mô tả cùng một người. Việc liên kết tài khoản giữa các nguồn là một nghiệp vụ có kiểm soát, không phải phép so sánh một chuỗi định danh đơn lẻ.

## 3. Định nghĩa quan hệ tin cậy trước khi nhận token

### 3.1. Tin cậy issuer là một quyết định cấu hình

Một API cần có chính sách xác định issuer được chấp nhận cho từng loại truy cập. Không tạo quan hệ tin cậy chỉ vì token tự khai một URL nhìn có vẻ nội bộ hoặc vì máy chủ tại URL đó trả về được một bộ khóa.

Ví dụ chính sách khái niệm:

```yaml
tokenTrustPolicy:
  policyId: courses-api-production-v3
  expectedIssuer: https://identity.learning.example
  expectedAudience: https://api.learning.example/courses
  tokenProfile: oauth-access-token-jwt
  trustedKeySetUri: https://identity.learning.example/keys
  maximumTokenLifetimeSeconds: 600
  allowedClockSkewSeconds: 30
  acceptedSubjects: enrolled-users-and-approved-workloads
```

Đây là mô tả yêu cầu cho hệ thống giả định, không phải schema cấu hình của một thư viện. Danh sách thuật toán, quy tắc claim và hành vi thu hồi còn phải được bổ sung theo profile đã chọn. Các giá trị 600 và 30 giây là ví dụ quyết định rủi ro, không phải giá trị mặc định cho mọi hệ thống.

### 3.2. Tách môi trường và phạm vi thẩm quyền

Issuer dùng cho môi trường thử nghiệm không được mặc nhiên có quyền phát hành token production. Tương tự, issuer được tin cho chức năng học tập không nhất thiết được tin cho cổng quản trị hoặc công cụ vận hành dữ liệu.

Một yêu cầu có thể nêu:

> **TI-TRUST-01:** API khóa học production chỉ chấp nhận token theo profile đã chốt từ issuer production được cấu hình cho API đó. Token có cùng tên chủ thể hoặc quyền nhưng phát hành từ issuer thử nghiệm, issuer đối tác chưa được cấp phạm vi hoặc issuer do client tự cung cấp phải bị từ chối.

Allowlist phải đủ cụ thể. So khớp theo chuỗi chứa tên tổ chức, suffix rộng hoặc một wildcard không có ranh giới rõ có thể làm một issuer ngoài phạm vi được tiếp nhận.

## 4. Định danh issuer và metadata

Trong OAuth authorization server metadata, `issuer` là một định danh phải khớp với issuer dùng để lấy metadata. Metadata không khớp không được dùng. Quy tắc so sánh chuỗi được định nghĩa riêng, không phải tự chuẩn hóa tùy tiện cho tiện tích hợp. [RFC 8414, mục 3.3 và 4](https://www.rfc-editor.org/rfc/rfc8414.html#section-3.3).

OpenID Connect Discovery cũng ràng buộc issuer trong metadata với issuer đã dùng để truy xuất cấu hình và `iss` trong ID token. Việc có nhiều issuer trên một host là một trường hợp được hỗ trợ; vì thế không thể chỉ kiểm tra hostname rồi bỏ qua path. [OpenID Connect Discovery, mục 3 và 4.3](https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderConfig).

Với chính sách ví dụ, nhóm thiết kế cần phân biệt rõ:

```text
https://identity.learning.example
https://identity.learning.example/
https://identity.learning.example/tenant-a
https://identity.learning.example/tenant-b
https://identity-staging.learning.example
```

Không tự coi các giá trị này tương đương trong bộ kiểm tra token. Cách biểu diễn issuer phải được thống nhất ngay khi thiết lập tích hợp và tuân theo giao thức hoặc profile đang sử dụng.

URL issuer cũng không có nghĩa API được tự động tải mọi URL xuất hiện trong token. Cấu hình tin cậy cần xác định cách lấy metadata, nguồn khóa, quy tắc TLS, giới hạn truy cập mạng và hành vi khi phản hồi không đúng định dạng.

## 5. Chữ ký phải gắn với đúng issuer

JWT Best Current Practices yêu cầu kiểm tra rằng khóa dùng để xác minh thuộc issuer tương ứng, kiểm soát tập thuật toán được chấp nhận và không tin trực tiếp dữ liệu nhận từ token để thực hiện các phép tra cứu nguy hiểm. Các trường như `kid`, `jku` hoặc `x5u` có thể trở thành đầu vào tấn công nếu xử lý không được giới hạn. [RFC 8725, mục 3.1, 3.8 và 3.10](https://www.rfc-editor.org/rfc/rfc8725.html#section-3).

Trong hệ thống giả định, có thể chuyển thành các yêu cầu:

- Khóa xác minh được lưu hoặc truy xuất trong phạm vi issuer đã được cấu hình, không nằm trong một kho khóa toàn cục chỉ tra theo `kid`.
- Giá trị `kid` chỉ chọn một khóa trong tập được tin cậy; nó không cấp quyền tải một khóa bất kỳ hoặc truy cập một đường dẫn tùy ý.
- Danh sách thuật toán cho phép được quản lý bởi chính sách của hệ thống, không do token mở rộng.
- Kết quả xác minh thất bại không được xử lý bằng cách bỏ qua chữ ký hoặc thử một chế độ yếu hơn.

Ví dụ, hai issuer có thể cùng sử dụng nhãn khóa `key-2026-01`. Hệ thống phải giữ liên kết giữa issuer, định danh khóa và vật liệu khóa tương ứng. Chỉ thấy nhãn giống nhau không chứng minh hai khóa hay hai issuer có quan hệ tin cậy.

Trong thiết kế dùng chữ ký bất đối xứng, bên xác minh có thể được cấp public key mà không có quyền ký token mới. Dịch vụ giữ private key hoặc được phép gọi thao tác ký vẫn cần kiểm soát nghiêm ngặt. Chuyển private key vào một dịch vụ quản lý khóa không tự giải quyết việc một workload có quyền gọi ký quá rộng.

## 6. Profile token quyết định cách kiểm tra

### 6.1. Không chấp nhận mọi JWT như cùng một loại token

Một issuer có thể phát hành access token, ID token hoặc token phục vụ chức năng riêng. Việc cùng issuer và cùng định dạng JWT không làm các token đó thay thế được nhau.

Đối với JWT access token theo RFC 9068, resource server phải kiểm tra loại token, issuer, audience, chữ ký và thời hạn theo profile. Profile này sử dụng giá trị `typ` là `at+jwt` hoặc `application/at+jwt`, đồng thời không chấp nhận thuật toán `none`. [RFC 9068, mục 4](https://www.rfc-editor.org/rfc/rfc9068.html#section-4).

Ví dụ các phần dữ liệu minh họa của access token:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "production-key-v3"
}
```

```json
{
  "iss": "https://identity.learning.example",
  "sub": "learner-704",
  "aud": "https://api.learning.example/courses",
  "client_id": "learning-web",
  "scope": "courses:read",
  "iat": 1800000000,
  "exp": 1800000600,
  "jti": "token-example-8e21"
}
```

Hai khối JSON không phải một token đã ký và không dùng làm credential thực tế. Thuật toán trong ví dụ chỉ minh họa một header; lựa chọn triển khai phải theo chính sách mật mã được phê duyệt và yêu cầu của profile.

### 6.2. Chữ ký hợp lệ chưa kết thúc việc phân quyền

Trong ví dụ, `courses:read` không cấp quyền sửa khóa học hoặc đọc dữ liệu của mọi tổ chức. Resource server còn phải kiểm tra hành động, tài nguyên, chủ thể và các điều kiện nghiệp vụ.

Claims là kết quả của một thời điểm phát hành. Nếu quyền quản trị bị thu hồi sau đó, token cũ không tự sửa nội dung của nó. Yêu cầu về độ mới của quyền hoặc thời gian thu hồi phải được thiết kế riêng, không suy ra từ việc chữ ký tiếp tục hợp lệ.

JWT được ký cũng không mặc nhiên giữ bí mật nội dung. Dữ liệu nhạy cảm không nên xuất hiện trong token chỉ vì token đã có chữ ký. Nhóm thiết kế cần xác định claim tối thiểu mà resource server thực sự cần.

## 7. Issuer phát hành opaque token

Issuer không chỉ tồn tại trong kiến trúc JWT. Với opaque token, resource server có thể cần gọi một endpoint tin cậy để kiểm tra trạng thái và lấy thông tin liên quan. OAuth Token Introspection mô tả cơ chế phản hồi `active` cùng metadata về token, bảo vệ endpoint và các đánh đổi khi cache phản hồi. [RFC 7662, mục 2 và 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-2).

Trong một thiết kế opaque token, nguồn tin cậy không thể chỉ được chọn từ một URL không được xác thực do người gửi cung cấp. Hệ thống cần biết endpoint introspection nào được phép nhận token, cách xác thực resource server và phạm vi thông tin được tin từ phản hồi.

Ví dụ yêu cầu riêng:

> **TI-INT-01:** API chỉ gửi token cần introspection đến endpoint đã được cấu hình cho ngữ cảnh truy cập. Kết quả chỉ được dùng khi giao tiếp được bảo vệ, phản hồi hợp lệ và điều kiện về chủ thể, tài nguyên, quyền cùng hiệu lực được đáp ứng. Không xác minh được thì không cho phép thao tác bảo vệ.

Cache kết quả có thể làm chậm việc nhận biết token đã bị thu hồi. Chính sách phải chốt thời gian cache, phạm vi khóa cache và giới hạn hiệu lực thực tế. Không để một kết quả cũ tiếp tục cho phép sau thời hạn được chấp nhận chỉ vì endpoint đang lỗi.

Nếu một endpoint hỗ trợ nhiều loại token, phải có quy tắc phân biệt rõ. Một token JWT thất bại kiểm tra không nên tự được chuyển sang một đường kiểm tra khác có điều kiện lỏng hơn để cố tìm kết quả cho phép.

## 8. Yêu cầu đối với quá trình phát hành

### 8.1. Căn cứ phát hành

Issuer phải xác định yêu cầu cấp token dựa trên một căn cứ hợp lệ: kết quả xác thực, grant, danh tính workload hoặc cơ chế được profile cho phép. Không chỉ nhận một JSON có các trường `sub`, `role` rồi ký nguyên nội dung đó.

Client có thể đề nghị phạm vi hoặc tài nguyên nhưng issuer phải tính quyền thực tế từ chính sách và nguồn dữ liệu được tin cậy. Việc client yêu cầu `admin:write` không chứng minh client hoặc người dùng được phép nhận quyền đó.

> **TI-MINT-01:** Issuer phải suy ra subject, audience, quyền và thời hạn từ căn cứ cấp token đã kiểm tra cùng chính sách hiện hành. Các thuộc tính do client cung cấp chỉ được sử dụng trong phạm vi giao thức cho phép và không được mở rộng quyền vượt căn cứ đã được cấp.

### 8.2. Phân tách trách nhiệm

Một hệ thống cần xác định ai được quản lý client, ai thay chính sách cấp quyền, ai quản lý khóa ký và workload nào được gọi thao tác phát hành. Người có quyền đọc public metadata không vì thế được quyền tạo token.

Đối với một thao tác quản trị issuer có tác động lớn, yêu cầu có thể cần xác thực mạnh, phê duyệt độc lập hoặc kiểm soát thay đổi. Mục tiêu là ngăn một tài khoản quản trị thông thường tự sửa chính sách rồi cấp token đặc quyền mà không có bằng chứng.

### 8.3. Thời hạn và dữ liệu đầu ra

Issuer phải áp dụng giới hạn thời gian sống cho từng loại token. Đồng hồ của issuer và resource server cần được quản lý; khoảng chấp nhận sai lệch phải được công bố thay vì tăng dần khi có lỗi tích hợp.

Token và credential liên quan phải được trả qua đường giao tiếp được bảo vệ, hạn chế rò rỉ qua URL, log hoặc hệ thống theo dõi. Một mã lỗi không được đính kèm toàn bộ token để giúp người vận hành dễ tìm kiếm.

## 9. Luân chuyển khóa và xử lý khóa bị lộ

### 9.1. Luân chuyển theo kế hoạch

Trong một thiết kế có nhiều resource server cache public key, thay khóa không chỉ là đổi một tệp ở issuer. Cần xác định trạng thái của token đang lưu hành và thời điểm các bên xác minh có thể nhận khóa mới.

Một kế hoạch cho hệ thống giả định có thể gồm:

1. Chuẩn bị khóa mới và gán định danh không gây nhầm với khóa đang có.
2. Công bố public key mới qua nguồn tin cậy đã cấu hình.
3. Xác nhận các đường xác minh cần thiết có thể nhận khóa mới theo cơ chế đã chọn.
4. Chuyển issuer sang ký token mới bằng khóa mới.
5. Giữ khả năng xác minh token cũ đến khi chúng hết hiệu lực theo chính sách, bao gồm sai lệch thời gian đã chấp nhận.
6. Loại khóa cũ khỏi tập hoạt động theo kế hoạch, ghi nhận kết quả và xử lý dữ liệu khóa tương ứng.

Đây là một trình tự vận hành minh họa, không phải thời gian chồng lấp cố định của mọi hệ thống. Khoảng giữ khóa cũ phải dựa trên token thực sự có thể còn hiệu lực, cơ chế cache và chính sách của các bên nhận.

### 9.2. Khóa bị lộ cần đường xử lý khác

Khi private key bị lộ, việc tiếp tục tin mọi token ký bằng khóa đó có thể cho phép token giả được sử dụng. Không thể coi đây là một đợt luân chuyển thông thường chỉ cần chờ token cũ hết hạn.

Xóa public key ở nguồn công bố chưa chứng minh mọi cache đã loại khóa. Hệ thống cần cơ chế khẩn cấp phù hợp để các điểm thực thi ngừng tin khóa hoặc issuer bị ảnh hưởng theo thời hạn đã cam kết.

> **TI-KEY-INC-01:** Kể từ khi quyết định vô hiệu hóa khẩn cấp một khóa ký được phát hành bởi hệ thống quản trị tin cậy, mọi điểm thực thi thuộc phạm vi phải ngừng chấp nhận token dựa trên khóa đó trong tối đa 60 giây ở ví dụ này, kể cả khi public key còn nằm trong cache. Việc nhận diện khóa phải gắn với issuer và phiên bản hoặc vật liệu khóa tương ứng.

Mốc 60 giây là tham số minh họa cần được chốt theo rủi ro. Nếu kiến trúc không đáp ứng được, không được vẫn ghi yêu cầu này rồi chỉ kiểm tra thời điểm xóa khóa tại issuer.

## 10. Tính khả dụng và hành vi khi có lỗi

Issuer không khả dụng có thể ảnh hưởng khác nhau đến cấp token mới và kiểm tra token đã phát hành. Trong kiến trúc xác minh chữ ký cục bộ, token còn hiệu lực có thể tiếp tục được đánh giá bằng khóa đã được tin và còn nằm trong chính sách cache. Trong kiến trúc cần introspection trực tiếp, tác động có thể khác.

Yêu cầu cần phân biệt các tình huống:

| Tình huống | Câu hỏi chính sách cần chốt |
|---|---|
| Token endpoint lỗi | Có trả lỗi rõ ràng và tránh phát hành token theo đường dự phòng ngoài chính sách không? |
| Metadata tạm thời không lấy được | Cấu hình đã xác minh còn được sử dụng bao lâu và trong điều kiện nào? |
| Gặp định danh khóa mới | Có thể làm mới tập khóa từ nguồn tin cậy với giới hạn nào? |
| Không tìm được khóa phù hợp | Hệ thống từ chối thế nào mà không bỏ qua xác minh? |
| Introspection không phản hồi | Có quyết định cache còn hiệu lực được phép dùng hay phải từ chối? |
| Hệ thống vừa nhận thông báo khóa bị lộ | Thông báo khẩn cấp có ghi đè việc dùng cache bình thường không? |

Không tự chuyển sang issuer khác chỉ vì issuer chính gặp sự cố. Issuer thay thế phải nằm trong thiết kế tin cậy được phê duyệt với cùng các ràng buộc cần thiết, không phải một máy chủ dự phòng được thêm vào lúc xử lý lỗi.

Các lần làm mới metadata hoặc khóa cần có giới hạn thời gian, kích thước, tần suất và khả năng phối hợp giữa request đồng thời. Nếu mỗi token lạ đều tạo một đợt tải mạng không giới hạn, đường kiểm tra token có thể bị dùng để gây quá tải.

## 11. Nhiều tenant và chuyển đổi issuer

### 11.1. Cùng issuer không đồng nghĩa cùng phạm vi dữ liệu

Một issuer có thể phục vụ nhiều tenant. Khi đó, token hợp lệ từ issuer chưa đủ chứng minh người dùng được truy cập tenant được chỉ định trong URL hoặc header request.

Yêu cầu cần chỉ rõ nguồn của thông tin tenant, cách liên kết subject với tenant và kiểm tra tài nguyên. Không lấy một `tenantId` do client tùy ý gửi làm căn cứ duy nhất để chọn quyền hoặc mở dữ liệu của tenant khác.

Nếu mỗi tenant có issuer riêng, việc chọn chính sách phải theo một registry được quản lý. Không tự khám phá và tin mọi issuer có path trông giống `/tenant/...`.

### 11.2. Chuyển issuer là thay đổi quan hệ tin cậy

Khi chuyển sang nhà cung cấp mới, cần xác định cách ánh xạ tài khoản, loại token, audience, quyền và vòng đời credential. Có thể có khoảng hai issuer cùng được chấp nhận, nhưng khoảng đó phải có phạm vi, thời điểm bắt đầu, thời điểm kết thúc và tiêu chí loại issuer cũ.

Không liên kết tài khoản chỉ vì email hoặc `sub` có vẻ giống nhau. Các yêu cầu về liên kết cần duy trì bằng chứng nguồn gốc và tránh đưa một danh tính từ issuer ít được tin hơn vào quyền của tài khoản đặc quyền hiện có.

## 12. Ví dụ đặc tả yêu cầu cho API khóa học

Giả sử API khóa học production sử dụng JWT access token, thời gian sống tối đa 10 phút và chỉ nhận issuer đã cấu hình. Các tham số dưới đây là ví dụ, không phải yêu cầu mặc định của giao thức.

| ID | Yêu cầu | Bằng chứng kiểm chứng dự kiến |
|---|---|---|
| TI-ISS-01 | API bắt buộc có issuer đúng chính sách production và so khớp theo profile; không chấp nhận issuer ngoài danh sách | Token từ issuer lạ, staging hoặc định danh khác bị từ chối |
| TI-BIND-01 | Khóa xác minh phải thuộc issuer và thuật toán được phép của profile | Token ký bằng khóa ngoài phạm vi không vượt qua kiểm tra |
| TI-AUD-01 | Audience phải chứa định danh API khóa học được cấu hình | Token cho API khác không truy cập được API khóa học |
| TI-TYPE-01 | Endpoint chỉ tiếp nhận access token của profile đã chọn, không chấp nhận ID token hoặc token chức năng khác | Các loại token thay thế bị từ chối dù có chữ ký hợp lệ |
| TI-CLAIM-01 | Issuer chỉ cấp quyền từ căn cứ đã kiểm tra; dữ liệu client không tự tạo role hoặc mở rộng audience | Yêu cầu tự khai quyền quản trị không nhận được quyền đó |
| TI-LIFE-01 | Token của profile ví dụ có thời gian sống tối đa 600 giây; dung sai thời gian tối đa 30 giây được áp dụng nhất quán | Kiểm tra token quá dài hạn, hết hạn và tại các mốc biên |
| TI-KEYSRC-01 | Địa chỉ metadata và nguồn khóa được giới hạn theo cấu hình tin cậy; token không tạo truy cập mạng tùy ý | Token chứa địa chỉ khác không khiến server kết nối đến địa chỉ đó |
| TI-ROT-01 | Luân chuyển khóa theo kế hoạch không làm ngừng tiếp nhận token hợp lệ ngoài dự kiến và không mở rộng thời hạn token cũ | Quan sát token cũ, token mới và các node qua thời điểm chuyển khóa |
| TI-REVOKE-01 | Vô hiệu hóa khóa khẩn cấp có hiệu lực tại mọi điểm thực thi trong tối đa 60 giây theo phạm vi ví dụ | Dùng token liên quan qua các node và cache sau mốc vô hiệu hóa |
| TI-FAIL-01 | Không xác minh được nguồn, khóa hoặc điều kiện bắt buộc thì không thực hiện thao tác bảo vệ | Giả lập lỗi phụ thuộc và đối chiếu tác động nghiệp vụ |
| TI-TENANT-01 | Token hợp lệ vẫn phải đáp ứng liên kết chủ thể với tenant và tài nguyên được yêu cầu | Token của tenant A không đọc được tài nguyên tenant B |
| TI-AUDIT-01 | Cấp token, thay chính sách tin cậy và thay khóa phải có sự kiện truy vết; không ghi credential nguyên vẹn | Log liên kết được quyết định mà không chứa token hay khóa bí mật |

Yêu cầu về thu hồi quyền của một người dùng hoặc workload cần được viết riêng nếu hệ thống cần phản ứng trước lúc token hết hạn. Thời gian sống 10 phút không tự đáp ứng cam kết thu hồi trong 60 giây; hai yêu cầu cần cơ chế thực thi tương ứng.

## 13. Tiêu chí chấp nhận theo ranh giới tin cậy

Các tình huống dưới đây mô tả cách kiểm chứng yêu cầu, chưa phải báo cáo kiểm thử một hệ thống thực tế.

| Tình huống | Thao tác kiểm chứng | Kết quả mong đợi |
|---|---|---|
| Token hợp lệ | Dùng đúng issuer, khóa, audience, loại và quyền | Chỉ thực hiện được hành động nằm trong chính sách |
| Issuer tự dựng | Tạo token bằng một issuer và khóa không được cấp tin cậy | Từ chối, không tự thêm issuer vào registry |
| Issuer thử nghiệm | Gửi token staging đến API production | Từ chối dù subject và tên quyền giống token production |
| Khóa không thuộc issuer | Giữ issuer hợp lệ nhưng ký bằng khóa khác | Từ chối liên kết issuer và khóa không hợp lệ |
| Trùng định danh khóa | Dùng cùng nhãn `kid` từ issuer khác | Không chọn nhầm khóa từ phạm vi khác |
| Sai audience | Dùng token dành cho một API khác | Từ chối trước tác động nghiệp vụ |
| Sai loại token | Dùng ID token hoặc token chức năng riêng làm access token | Không được tiếp nhận ở endpoint không phù hợp |
| Metadata không khớp | Trả metadata có issuer khác cấu hình tin cậy | Không dùng metadata đó để thiết lập tin cậy |
| Nguồn khóa do token chỉ định | Đưa địa chỉ không được cho phép vào token | Không tạo truy cập mạng tùy ý hoặc gửi credential đến đó |
| Quá thời hạn | Dùng token hết hạn hoặc vượt thời gian sống đã cho phép | Từ chối theo dung sai được công bố |
| Thu hồi khóa qua cache | Giữ public key cũ tại một node rồi phát lệnh vô hiệu hóa | Node vẫn ngừng chấp nhận theo thời hạn cam kết |
| Client tự nâng quyền | Đề nghị scope hoặc claim vượt căn cứ được cấp | Issuer từ chối hoặc giới hạn theo chính sách, không cấp vượt quyền |
| Chuyển tenant | Đổi tenant trong request nhưng giữ token cũ | Không truy cập được tài nguyên ngoài phạm vi |
| Cùng subject khác issuer | Dùng cùng chuỗi subject từ hai issuer | Không tự hợp nhất identity hoặc quyền |
| Issuer mất khả dụng | Giả lập lỗi cấp token, tải khóa hoặc introspection | Hành vi đúng từng chính sách lỗi, không bỏ qua xác minh |

Mỗi phép kiểm chứng cần quan sát cả phản hồi và trạng thái nghiệp vụ. Một request trả lỗi sau khi đã thay đổi dữ liệu vẫn không đáp ứng yêu cầu từ chối trước tác động.

## 14. Theo dõi, ứng phó sự cố và lỗi đặc tả thường gặp

Log nên phân biệt token không được tin, sai audience, sai loại, hết hạn, không tìm thấy khóa và phụ thuộc không khả dụng bằng mã nguyên nhân phù hợp. Không đưa toàn bộ token, client secret, private key hoặc dữ liệu cá nhân không cần thiết vào log để phục vụ chẩn đoán.

Hoạt động quản trị cần ghi ai thay registry issuer, ai thay nguồn khóa, chính sách nào được áp dụng và thay đổi có hiệu lực ở đâu. Khi xảy ra sự cố, nhóm vận hành phải xác định được các tài nguyên đang tin issuer hoặc khóa bị ảnh hưởng; chỉ có danh sách máy chủ issuer là chưa đủ.

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
|---|---|---|
| “Token có chữ ký là được” | Không xác định nguồn khóa và thẩm quyền | Ràng buộc issuer, khóa, thuật toán và profile |
| “Tin mọi issuer nội bộ” | Phạm vi nội bộ không đồng nghĩa thẩm quyền giống nhau | Liệt kê issuer được chấp nhận cho từng API và mục đích |
| “Đọc issuer rồi tải khóa theo URL” | Đầu vào chưa được xác thực có thể mở rộng tin cậy hoặc truy cập mạng | Chọn trong registry và nguồn khóa đã được kiểm soát |
| “ID token cũng là JWT nên dùng cho API” | Nhầm mục đích của các token | Chốt profile và điều kiện tiếp nhận riêng |
| “Đổi khóa là thu hồi ngay” | Bỏ qua cache và các điểm xác minh độc lập | Nêu thời hạn lan truyền và bằng chứng mất hiệu lực thực tế |
| “Issuer lỗi thì dùng tạm một issuer khác” | Thay đổi ranh giới tin cậy lúc sự cố | Thiết kế trước đường dự phòng và điều kiện cho phép |
| “Cùng subject là cùng người” | Bỏ qua nguồn gốc identity | Giữ liên kết issuer-subject và quy trình liên kết tài khoản |

Một đặc tả token issuer đầy đủ nối được quyết định phát hành với căn cứ cấp quyền và quyết định tiếp nhận tại tài nguyên đích. Issuer phải có phạm vi thẩm quyền rõ; bên nhận phải thực thi quan hệ tin cậy đã cấu hình; các thay đổi khóa, quyền và tính khả dụng phải có hành vi có thể quan sát cùng giới hạn thời gian được kiểm chứng.
