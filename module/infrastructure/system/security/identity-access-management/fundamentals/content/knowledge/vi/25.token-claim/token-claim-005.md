# Token audience — token này dành cho hệ thống nào?

Một token có chữ ký hợp lệ chưa chắc được phép sử dụng tại API đang nhận nó. Cùng một hệ thống IAM có thể phát hành token cho cổng nhân sự, API chấm công và API bảng lương. Nếu mọi dịch vụ đều chấp nhận mọi token do hệ thống đó ký, ranh giới giữa các ứng dụng có thể bị phá vỡ.

**Audience** xác định bên nhận mà token được phát hành để sử dụng. Trong JWT, thông tin này thường nằm trong claim `aud`. Resource server kiểm tra audience để trả lời câu hỏi: “Token có dành cho mình không?”, trước khi dùng scope, role hoặc các thuộc tính khác để quyết định quyền truy cập.

Bài học tập trung vào JWT access token trong OAuth và ID Token trong OpenID Connect (OIDC), đồng thời giải thích cách áp dụng nguyên tắc giới hạn bên nhận khi access token có dạng opaque.

## 1. Tại sao IAM cần giới hạn audience?

Giả sử doanh nghiệp có ba thành phần:

- Authorization Server: `https://login.example.com/`.
- Timesheet API: định danh tài nguyên `urn:example:timesheet-api`.
- Payroll API: định danh tài nguyên `urn:example:payroll-api`.

Một nhân viên được cấp token để đọc dữ liệu chấm công. Người đó hoặc một ứng dụng giữ token thử gửi nó tới Payroll API.

```text
Authorization Server
    |
    | token có aud = urn:example:timesheet-api
    v
Ứng dụng nhân viên
    |
    +----> Timesheet API: đúng bên nhận, tiếp tục kiểm tra quyền
    |
    +----> Payroll API: sai bên nhận, từ chối token
```

Token trong ví dụ có thể còn hạn, đúng người dùng và được ký bằng khóa chính thức. Những thuộc tính đó không biến token chấm công thành token bảng lương.

Audience giúp thu hẹp nơi token được chấp nhận. Nó không tự ngăn kẻ lấy cắp bearer token sử dụng token tại chính API có audience phù hợp, không mã hóa nội dung token và không thay thế kiểm tra quyền từng tài nguyên. Bảo vệ kênh truyền, quản lý vòng đời token và các cơ chế ràng buộc bên gửi vẫn là những trách nhiệm riêng.

## 2. Ý nghĩa và kiểu dữ liệu của `aud`

Theo [RFC 7519, mục 4.1.3](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.3), `aud` xác định các bên nhận dự kiến của JWT. Nó có thể là một chuỗi khi chỉ có một audience hoặc một mảng chuỗi. Các giá trị được so sánh có phân biệt chữ hoa và chữ thường.

Ví dụ một audience:

```json
{
  "aud": "urn:example:timesheet-api"
}
```

Ví dụ nhiều audience:

```json
{
  "aud": [
    "urn:example:timesheet-api",
    "urn:example:reporting-api"
  ]
}
```

Mảng audience không phải danh sách scope và không thể được xử lý như một chuỗi phân cách bằng dấu phẩy. API phải kiểm tra tư cách bên nhận theo đúng phần tử trong mảng, không tìm một đoạn văn bản gần giống định danh của mình.

RFC 7519 định nghĩa `aud` là claim tùy chọn ở tầng JWT tổng quát. Điều đó không có nghĩa mọi ứng dụng đều được phép bỏ qua nó. Profile giao thức và hợp đồng tích hợp có thể bắt buộc audience. Trong bài này, Timesheet API yêu cầu JWT access token có audience hợp lệ; token thiếu `aud` bị từ chối.

## 3. Audience khác issuer, subject, client và scope

Một payload minh họa của access token có thể chứa:

```json
{
  "iss": "https://login.example.com/",
  "sub": "employee-1042",
  "aud": "urn:example:timesheet-api",
  "client_id": "employee-web",
  "scope": "timesheet:read",
  "iat": 2000000000,
  "exp": 2000000300,
  "jti": "demo-access-token-1042"
}
```

Đây chỉ là JSON phục vụ học tập, chưa có JOSE header hoặc chữ ký nên không phải token có thể sử dụng. Các mốc thời gian là dữ liệu cố định minh họa cửa sổ 300 giây.

| Thông tin | Câu hỏi được trả lời trong ví dụ | Giá trị minh họa |
|---|---|---|
| `iss` | Ai phát hành token? | Authorization Server của doanh nghiệp |
| `sub` | Token nói về chủ thể nào? | Nhân viên `employee-1042` |
| `aud` | Bên nào là nơi sử dụng token dự kiến? | Timesheet API |
| `client_id` | OAuth client nào yêu cầu token? | Ứng dụng `employee-web` |
| `scope` | Phạm vi truy cập nào được cấp? | Đọc dữ liệu chấm công |
| `exp` | Token được chấp nhận trước thời điểm nào? | Mốc hết hạn của token |

Ý nghĩa chính xác của từng claim vẫn phụ thuộc loại token và profile. Chẳng hạn, `azp` trong một số ngữ cảnh OIDC mô tả authorized party; không được tùy ý xem nó, `client_id` và `aud` là các tên thay thế cho cùng một dữ liệu.

**Audience xác định nơi áp dụng quyền; scope mô tả phạm vi quyền trong hợp đồng của tài nguyên đó.** Một API khác cũng có scope tên `read` không được vì thế chấp nhận token của Timesheet API.

Sau khi audience đúng, `timesheet:read` cũng chưa cho phép đọc chấm công của mọi nhân viên. API còn cần đối chiếu chủ sở hữu bản ghi, tenant, vai trò hoặc chính sách ABAC. Điều này nối kiểm tra token với nguyên tắc ít quyền nhất trong IAM.

## 4. Access token và ID Token có audience khác nhau

Trong tích hợp OIDC thông thường, ID Token gửi cho client để client xác minh thông tin đăng nhập; access token được sử dụng tại resource server để truy cập tài nguyên.

| Loại token | Bên tiêu thụ dự kiến | Audience trong ví dụ |
|---|---|---|
| ID Token | OIDC client/Relying Party | `employee-web` |
| Access token cho chấm công | Timesheet API | `urn:example:timesheet-api` |
| Access token cho bảng lương | Payroll API | `urn:example:payroll-api` |

[OIDC Core, mục 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation) yêu cầu client kiểm tra `aud` của ID Token chứa `client_id` đã đăng ký của mình; các audience bổ sung cũng phải được client tin cậy. Những kiểm tra `azp` áp dụng theo extension và quy tắc của tích hợp, không thay thế audience.

Timesheet API không được lấy audience của ID Token làm cấu hình audience cho access token chỉ vì cả hai token cùng đến từ một nhà cung cấp danh tính. Client cũng không nên gửi ID Token làm bearer token để gọi API theo hợp đồng OAuth access token của bài này.

Đối với JWT access token theo [RFC 9068, mục 4](https://www.rfc-editor.org/rfc/rfc9068.html#section-4), resource server phải kiểm tra audience chứa định danh tài nguyên mà nó mong đợi cho chính mình, đồng thời kiểm tra issuer, chữ ký và thời hạn. Profile này còn yêu cầu JOSE `typ` nhận diện access token là `at+jwt` hoặc `application/at+jwt`. Không áp đặt giá trị `typ` đó cho mọi token JWT của mọi giao thức.

Để tránh nhầm loại token, nên có bộ kiểm tra và hợp đồng rõ ràng cho từng loại. Không dùng một hàm “JWT có chữ ký đúng” chung rồi cho cả ID Token lẫn access token đi vào cùng luồng cấp quyền API.

## 5. Kiểm tra audience bằng cấu hình đáng tin cậy

Timesheet API cần biết trước mình chấp nhận định danh nào. Ví dụ hợp đồng của hệ thống quy định:

```text
Trusted issuer:     https://login.example.com/
Expected audience:  urn:example:timesheet-api
Accepted purpose:   OAuth access token
Required scope:     timesheet:read
```

`Expected audience` phải lấy từ cấu hình của API hoặc ánh xạ tài nguyên được quản trị. Không lấy audience trong token làm giá trị kỳ vọng để so sánh với chính nó. Cũng không suy ra cấu hình tin cậy trực tiếp từ `Host`, query parameter hoặc header tùy ý do người gọi cung cấp.

Chỉ decode Base64URL để nhìn thấy `aud` không chứng minh claim đúng. Một payload do người gửi tự tạo cũng có thể ghi tên Timesheet API. Cần kiểm tra toàn bộ token bằng khóa, thuật toán và issuer được cho phép, rồi mới sử dụng claims đã xác minh để tạo ngữ cảnh bảo mật.

[RFC 8725, mục 3.9](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.9) yêu cầu sử dụng và xác minh audience khi cùng issuer có thể phát hành JWT cho nhiều ứng dụng. Thiếu audience hoặc audience không gắn với bên nhận trong trường hợp đó phải dẫn tới từ chối token. Đây là rào cản quan trọng chống việc thay thế token giữa các ứng dụng.

### 5.1. So khớp chính xác, không đoán tương đương

Nếu hợp đồng chọn `https://api.example.com/timesheet` làm audience thì các giá trị dưới đây không tự được coi là giống nhau:

```text
https://api.example.com/timesheet
https://api.example.com/timesheet/
https://API.example.com/timesheet
https://api.example.com/timesheet-admin
```

Audience là định danh theo hợp đồng token, không phải yêu cầu thực hiện URL normalization. Không tự lowercase toàn chuỗi, bỏ dấu `/`, dùng `startsWith`, dùng wildcard hoặc chỉ so tên miền để mở rộng tập token được chấp nhận.

Một audience có hình thức URL cũng không có nghĩa API phải truy cập URL đó. Bên nhận không tải khóa hoặc metadata từ địa chỉ tùy ý trong claim `aud`.

### 5.2. Xử lý một hoặc nhiều audience

Với chính sách yêu cầu đúng định danh `urn:example:timesheet-api`, phép kiểm tra cơ bản là tìm một phần tử bằng chính xác định danh này trong tập audience đã được xác minh.

```text
audienceMatches(aud, expectedAudience):
    if aud is a non-empty string:
        return aud == expectedAudience

    if aud is a non-empty array and every item is a non-empty string:
        return any item == expectedAudience

    return false
```

Đây là mã giả cho chính sách của bài học. JSON sai kiểu, `null`, mảng rỗng hoặc mảng có phần tử không phải chuỗi đều bị từ chối. Không tự chuyển số hay đối tượng thành chuỗi để “cứu” token.

Nếu ứng dụng còn hạn chế các audience bổ sung, phải kiểm tra chính sách đó riêng. Chỉ việc có tên mình trong mảng không đáp ứng mọi quy tắc của mọi profile; ID Token OIDC là một ví dụ có quy tắc đối với audience bổ sung.

## 6. Đưa audience vào toàn bộ luồng quyết định truy cập

Luồng minh họa dưới đây áp dụng cho Timesheet API nhận JWT access token đã được ký. Các hàm biểu diễn trách nhiệm thiết kế, không phải API của một thư viện Java cụ thể.

```text
authorizeTimesheetRead(rawToken, request):
    policy = configuredPolicyForTimesheetApi()

    verifiedClaims = verifyAccessToken(
        rawToken,
        trustedIssuer = policy.issuer,
        trustedKeys = policy.signingKeys,
        allowedAlgorithms = policy.algorithms,
        acceptedTokenProfile = policy.tokenProfile
    )

    requireValidTimeClaims(verifiedClaims, policy.clockTolerance)
    require audienceMatches(verifiedClaims.aud, policy.expectedAudience)

    identity = resolveSubjectWithinIssuer(verifiedClaims.iss, verifiedClaims.sub)
    requireAllowedTenant(identity, request.targetTenant)
    requireScope(verifiedClaims, "timesheet:read")
    requireAllowedRecordAccess(identity, request.timesheetOwner)

    return allowRead()
```

Hệ thống có thể tổ chức thứ tự kiểm tra nội bộ khác nhau, nhưng không được cấp quyền từ claims chưa xác minh hoặc bỏ qua bất kỳ điều kiện bắt buộc nào. Kiểm tra audience chỉ là một gate trong chuỗi quyết định, không phải hàm xác minh token hoàn chỉnh.

Đối với nhiều issuer, cấu hình nên giữ quan hệ giữa issuer, khóa tin cậy, profile và audience tương ứng. Ví dụ:

```text
Issuer doanh nghiệp A -> khóa A -> audience timesheet-A -> tenant A
Issuer doanh nghiệp B -> khóa B -> audience timesheet-B -> tenant B
```

Không gộp thành hai danh sách issuer và audience độc lập rồi vô tình chấp nhận mọi tổ hợp chéo. Cùng một `sub` hoặc cùng một chuỗi audience cũng không đủ chứng minh token thuộc đúng tenant; các mối liên hệ phải được kiểm tra theo hợp đồng danh tính.

## 7. Token được cấp audience như thế nào?

Authorization Server quyết định tài nguyên mà token được phép hướng tới, dựa trên yêu cầu client và chính sách cấp quyền. Client có thể yêu cầu một tài nguyên nhưng không được vì vậy tự cấp quyền sử dụng tài nguyên đó.

[RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html#section-2) chuẩn hóa tham số `resource` để client biểu đạt tài nguyên mong muốn. Giá trị là một URI tuyệt đối, không có fragment. Authorization Server có thể dùng nguyên giá trị đó làm audience hoặc ánh xạ sang một định danh phù hợp với tài nguyên.

Ví dụ, hợp đồng của hệ thống có thể ánh xạ:

```text
Client yêu cầu resource:
    https://api.example.com/timesheet

Authorization Server áp dụng chính sách và cấp token có aud:
    urn:example:timesheet-api
```

Ánh xạ này là lựa chọn minh họa, không phải quy tắc tự suy ra từ hostname. Nếu nhà cung cấp dùng tham số tên `audience`, phải đối chiếu đúng giao thức và tài liệu của họ; không coi đó là tham số phổ quát thay thế `resource` trong mọi yêu cầu OAuth.

Đối với danh tính workload, ý nghĩa audience vẫn như vậy: dịch vụ gọi là client, còn API đích là bên nhận token. Việc không có người dùng tương tác không làm audience trở thành định danh của workload gọi.

## 8. Audience qua gateway và giữa các service

Audience nên phản ánh ranh giới tài nguyên logic đã thiết kế. Nhiều instance của cùng Timesheet API có thể dùng cùng một audience; không cần cấp một audience cho mỗi pod hoặc địa chỉ IP chỉ vì triển khai có nhiều bản sao.

Tuy nhiên, một gateway chung không làm mọi backend tự nhiên trở thành cùng tài nguyên. Cần phân biệt hai thiết kế:

- Gateway định tuyến tới Timesheet API, còn token vốn dành cho Timesheet API. Backend tiếp tục kiểm tra token theo hợp đồng đó.
- Token chỉ dành cho một tài nguyên gateway. Nếu gateway cần gọi một API độc lập với quan hệ tin cậy khác, phải có cơ chế ủy quyền hoặc token phù hợp cho chặng tiếp theo.

Trong thiết kế thứ hai, không giải quyết lỗi audience bằng cách cho mọi backend chấp nhận audience gateway. Cần xác định rõ gateway đang đại diện cho ai, được gọi tài nguyên nào và quyền có được thu hẹp hay không.

[RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html#section-2.1) định nghĩa OAuth Token Exchange, cho phép yêu cầu token đích với thông tin tài nguyên/audience theo chính sách Authorization Server. Đây là một cơ chế có thể dùng khi service cần token phù hợp cho dịch vụ downstream; không phải mọi hệ thống đều hỗ trợ và việc đổi token không mặc nhiên cấp mọi quyền đã yêu cầu.

Ví dụ thiết kế:

```text
Ứng dụng -> Timesheet API
           token T1, aud = timesheet-api

Timesheet API -> cơ chế cấp/đổi token được cho phép
               nhận T2, aud = reporting-api

Timesheet API -> Reporting API
               sử dụng T2 và scope giới hạn cho báo cáo
```

Nếu nhiều API thật sự cần nhận cùng token nhiều audience, phải đánh giá phạm vi quyền chung và khả năng token bị chuyển tiếp giữa chúng. Việc cấp một token cho toàn bộ hệ thống chỉ để tiện tích hợp sẽ làm suy yếu lợi ích giới hạn bên nhận.

## 9. Audience với opaque token

Access token không bắt buộc có dạng JWT đọc được. Với opaque token, resource server có thể dùng introspection hoặc cơ chế xác minh khác đã thỏa thuận với Authorization Server để biết token còn hoạt động và được phép sử dụng ở đâu.

[RFC 7662, mục 2.2 và 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-2.2) quy định phản hồi introspection có `active`; các trường như `aud` là tùy chọn. Khi token bị giới hạn theo resource server, Authorization Server phải thực hiện kiểm tra áp dụng cho resource server đang introspect.

Vì vậy, không áp đặt máy móc rằng mọi phản hồi introspection đều phải có JSON `aud`, nhưng cũng không tự xem `active: true` là giấy phép dùng token ở mọi API. Hợp đồng phải quy định rõ Authorization Server đã xác nhận token cho bên introspect hay API cần kiểm tra thêm audience/tài nguyên từ phản hồi.

Client nên sử dụng access token theo hợp đồng OAuth thay vì xây logic nghiệp vụ phụ thuộc việc tự giải mã token. JWT có thể được thay bằng opaque token mà ý nghĩa bên nhận và phạm vi quyền vẫn cần được giữ đúng.

## 10. Các tình huống cần kiểm chứng

Giả sử Timesheet API tin cậy issuer `https://login.example.com/`, yêu cầu access token có audience `urn:example:timesheet-api` và scope `timesheet:read`. Các trường hợp dưới đây là tình huống học tập, không phải kết quả đã chạy kiểm thử trên một ứng dụng cụ thể.

| Tình huống | Quyết định mong đợi |
|---|---|
| Chữ ký, issuer, thời gian đúng; `aud` là Timesheet API | Tiếp tục kiểm tra scope, tenant và bản ghi |
| Token còn hạn nhưng `aud` là Payroll API | Từ chối token tại Timesheet API |
| Scope có `timesheet:read` nhưng audience sai | Từ chối; scope không bù cho audience |
| Chỉ decode thấy audience đúng nhưng chữ ký sai | Từ chối |
| Token thiếu `aud` | Từ chối theo chính sách access token của ví dụ |
| `aud` là mảng chuỗi có Timesheet API | Qua kiểm tra membership; còn tùy chính sách audience bổ sung |
| `aud` là mảng có chuỗi hợp lệ và một số nguyên | Từ chối vì sai kiểu theo chính sách ví dụ |
| `aud` chỉ có tiền tố gần giống, như `timesheet-api-admin` | Từ chối |
| ID Token có audience là `employee-web` được gửi gọi API | Từ chối theo hợp đồng loại token của API |
| Audience đúng nhưng issuer thuộc đối tác khác chưa được chấp nhận | Từ chối |
| Token dành cho môi trường thử nghiệm được gửi vào production | Từ chối nếu không đáp ứng issuer/audience/profile production |
| Token hợp lệ cho API nhưng người dùng không được đọc bản ghi đích | Từ chối thao tác theo chính sách phân quyền |

Khi chẩn đoán lỗi audience, cần so sánh giá trị API kỳ vọng với token thực tế được cấp trong môi trường thử nghiệm an toàn, kiểm tra loại token và luồng yêu cầu resource. Tránh ghi nguyên bearer token vào log, gửi token thật lên công cụ giải mã công khai hoặc tắt audience validation để xử lý nhanh.

Nếu hai môi trường có ranh giới tin cậy khác nhau, nên cấu hình định danh và issuer/profile phù hợp để token không đi chéo môi trường. Chỉ việc hostname endpoint khác nhau không chứng minh audience validation đang phân biệt được hai môi trường.

## 11. Tự kiểm tra hiểu biết

**Cùng issuer và cùng khóa ký thì token có dùng được cho mọi API không?** Không. API phải kiểm tra token dành cho mình và phù hợp profile, sau đó mới xét quyền.

**Audience đúng có đồng nghĩa người dùng được đọc mọi dữ liệu không?** Không. Scope, tenant, chủ sở hữu bản ghi và các chính sách RBAC/ABAC vẫn phải được đánh giá.

**Audience của ID Token có phải luôn là audience của access token không?** Không. Trong tích hợp OIDC thông thường, ID Token dành cho client, còn access token dành cho tài nguyên theo hợp đồng OAuth.

**Có thể tự thêm audience vào payload để gọi API khác không?** Không. Thay đổi JWT đã ký làm mất tính toàn vẹn. Muốn truy cập tài nguyên khác phải được Authorization Server cấp token phù hợp theo chính sách.

**Audience có ngăn replay tại đúng API không?** Không tự nó. Audience giới hạn bên nhận; chống sử dụng token bị đánh cắp tại đúng bên nhận cần các biện pháp khác phù hợp với loại token và luồng sử dụng.
