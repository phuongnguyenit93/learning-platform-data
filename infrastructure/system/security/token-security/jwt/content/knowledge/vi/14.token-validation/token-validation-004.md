# Chọn cấu hình xác minh từ ngữ cảnh tin cậy

## 1. Vì sao phải chọn chính sách trước khi xác minh JWT?

Một hệ thống có thể nhận JWT từ nhiều issuer, nhiều ứng dụng khách và nhiều luồng nghiệp vụ. Các token này có thể cùng dùng định dạng JWS Compact, nhưng khác nhau về thuật toán, nguồn khóa, audience, loại token, claims bắt buộc, thời hạn và yêu cầu thu hồi. Vì vậy, một bộ xác minh không thể áp dụng một cấu hình tùy ý cho mọi token.

Trước khi đọc token, bên nhận phải xác định **yêu cầu hiện tại đang được xử lý trong ngữ cảnh nào**: endpoint nào nhận token, tài nguyên nào cần được bảo vệ, loại thông tin xác thực nào được chấp nhận, tenant nào đang được phục vụ và issuer nào được phép cấp token cho ngữ cảnh đó. Từ các thông tin đã được thiết lập bằng cấu hình hoặc xác thực độc lập, hệ thống chọn một **chính sách xác minh (validation policy)** cụ thể.

Đây là một ranh giới bảo mật quan trọng:

- Ngữ cảnh tin cậy quyết định tập chính sách có thể áp dụng.
- Header và claims chưa xác minh chỉ là dữ liệu đầu vào để kiểm tra hoặc, trong trường hợp được thiết kế cẩn thận, gợi ý một lựa chọn bên trong tập chính sách đã cho phép.
- Token chỉ trở thành dữ liệu đáng tin cậy sau khi vượt qua xác minh mật mã và toàn bộ điều kiện của chính sách đã chọn.

Nếu để token tự chọn issuer, nguồn khóa, thuật toán hoặc audience, kẻ tấn công có thể điều khiển bộ xác minh sử dụng một cấu hình do chính họ cung cấp. Hậu quả có thể là chấp nhận token từ issuer không mong muốn, dùng nhầm khóa, nhầm loại token hoặc bỏ qua ranh giới giữa các dịch vụ.

Nội dung áp dụng cho bảo mật JWT nói chung, độc lập với ngôn ngữ lập trình, framework hoặc thư viện cụ thể.

## 2. Phân biệt ngữ cảnh tin cậy và dữ liệu chưa xác minh

Không phải mọi thông tin có trong request đều đáng tin cậy. Một số dữ liệu được tạo bởi cấu hình máy chủ hoặc được xác thực qua một kênh độc lập; một số khác do người gửi tự kiểm soát.

| Thông tin | Mức độ tin cậy trước khi xác minh JWT | Cách sử dụng |
| --- | --- | --- |
| Định danh endpoint/API đã được router của máy chủ phân giải | Có thể tin cậy nếu cấu hình routing và proxy được bảo vệ | Chọn chính sách dành cho endpoint |
| Audience/resource server được cấu hình cho API | Tin cậy | Xác định audience bắt buộc |
| Bản ghi issuer được quản trị viên đăng ký và phê duyệt | Tin cậy trong phạm vi bản ghi đó | Chọn tập chính sách và nguồn khóa được phép |
| Danh tính client được xác thực độc lập, ví dụ bằng mTLS hoặc cơ chế client authentication đã kiểm chứng | Tin cậy theo phạm vi cơ chế xác thực | Có thể giới hạn issuer/profile mà client được dùng |
| Tenant được xác định từ một ngữ cảnh đã xác thực hoặc ánh xạ server-side | Tin cậy theo quy trình xác định tenant | Chọn chính sách tenant hoặc kiểm tra ràng buộc tenant |
| Header HTTP do client gửi, như Host hoặc X-Tenant-ID, khi chưa được proxy kiểm soát | Chưa mặc nhiên tin cậy | Chỉ sử dụng sau khi có quy tắc xác thực/chuẩn hóa và ràng buộc hạ tầng |
| Giá trị iss, aud, typ, kid, alg trong JWT chưa xác minh | Chưa tin cậy | Đối chiếu với policy; không dùng để tạo trust mới |
| Claims sub, role, scope, tenant trong payload chưa xác minh | Chưa tin cậy | Không tạo danh tính hoặc quyền trước khi xác minh |

Một thông tin có thể được dùng để **định tuyến** nhưng không được dùng để **cấp quyền**. Ví dụ, Host có thể giúp reverse proxy chọn virtual host nếu proxy được cấu hình đúng; nhưng ứng dụng không nên tin một giá trị Host tùy ý để tự tạo issuer hoặc JWKS URL.

Tương tự, một giá trị iss chưa xác minh đôi khi có thể dùng như gợi ý tìm một bản ghi issuer trong danh sách đã đăng ký. Nó không chứng minh issuer đó đáng tin cậy. Sau khi xác minh chữ ký, claim iss vẫn phải khớp chính xác với issuer trong chính sách đã chọn.

## 3. Các nguồn ngữ cảnh thường dùng để chọn policy

Một chính sách xác minh thường được chọn dựa trên sự kết hợp của các yếu tố sau:

| Nguồn ngữ cảnh | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Endpoint hoặc API | Dịch vụ đang bảo vệ tài nguyên nào? | API hóa đơn, API hồ sơ, API quản trị |
| Loại credential được endpoint chấp nhận | Access token, ID token hay một profile JWT chuyên biệt? | API chỉ nhận OAuth access token |
| Resource/audience | Token phải được cấp cho tài nguyên nào? | https://api.example.org/invoices |
| Tenant hoặc miền định danh | Yêu cầu thuộc không gian khách hàng nào? | Tenant A chỉ dùng issuer đã đăng ký cho tenant A |
| Issuer được đăng ký | Những authorization server nào được phép phát hành token? | Issuer doanh nghiệp, issuer đối tác |
| Client đã xác thực | Ứng dụng gọi API là client nào? | Ứng dụng nội bộ hoặc đối tác đã được cấp credential |
| Kênh xác thực bổ sung | Có yêu cầu ràng buộc token với client, thiết bị hoặc kênh không? | mTLS, proof-of-possession theo profile |
| Chính sách vận hành | Có quy tắc đặc biệt về khóa, thu hồi hoặc thời gian không? | Khóa khẩn cấp bị vô hiệu hóa |

Không phải endpoint nào cũng cần tất cả các yếu tố trên. Cần chọn tập thông tin tối thiểu nhưng đủ để xác định duy nhất một policy. Nếu nhiều yếu tố xung đột hoặc không thể xác định policy rõ ràng, nên từ chối yêu cầu thay vì tự chọn cấu hình rộng hơn.

## 4. Mô hình phân giải chính sách theo thứ tự

Một luồng an toàn có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Nhận request và token chưa tin cậy"] --> B["Phân giải endpoint/resource từ routing đã kiểm soát"]
    B --> C["Lấy tenant/client context đã xác thực nếu cần"]
    C --> D["Tìm policy từ registry cấu hình tin cậy"]
    D --> E{"Có policy phù hợp và duy nhất?"}
    E -- "Không" --> X["Từ chối: không xác định được policy"]
    E -- "Có" --> F["Parse header có giới hạn"]
    F --> G{"Header phù hợp policy?"}
    G -- "Không" --> X
    G -- "Có" --> H["Chọn khóa trong nguồn đã gắn với issuer"]
    H --> I["Xác minh chữ ký hoặc bảo vệ mật mã"]
    I --> J{"Bằng chứng mật mã hợp lệ?"}
    J -- "Không" --> X
    J -- "Có" --> K["Kiểm tra iss, aud, thời gian, typ và claims"]
    K --> L{"Claims khớp policy và ngữ cảnh?"}
    L -- "Không" --> X
    L -- "Có" --> M["Tạo ngữ cảnh token đã xác minh"]
    M --> N["Đánh giá quyền trên hành động và tài nguyên"]
~~~

Trình tự chi tiết có thể khác theo profile JOSE, nhưng nguyên tắc chọn policy vẫn giữ nguyên:

1. Xác định endpoint và tài nguyên từ cấu hình routing của máy chủ.
2. Xác định tenant hoặc client nếu quy trình xác thực độc lập cung cấp được ngữ cảnh đáng tin cậy.
3. Tra cứu policy trong registry đã được quản trị, không dựng policy từ token.
4. Nếu có nhiều issuer được phép, thu hẹp lựa chọn vào danh sách issuer gắn với endpoint/tenant/client.
5. Parse header để đối chiếu thuật toán, loại token và chọn ứng viên khóa trong kho khóa đã được gắn với issuer.
6. Xác minh chữ ký hoặc cơ chế bảo vệ mật mã.
7. Kiểm tra lại issuer, audience, thời gian, loại token, tenant và các claims bắt buộc.
8. Tạo ngữ cảnh danh tính đã xác minh, rồi mới đánh giá quyền truy cập.

## 5. Thiết kế registry chính sách xác minh

Một registry là tập cấu hình được quản trị, xác định endpoint nào chấp nhận loại token nào và tin cậy issuer/nguồn khóa nào. Registry có thể được lưu trong cấu hình triển khai, cơ sở dữ liệu quản trị hoặc hệ thống cấu hình trung tâm, miễn là có kiểm soát thay đổi và tính toàn vẹn.

Ví dụ minh họa:

~~~yaml
validationPolicies:
  invoices-api:
    endpointId: invoices-read
    acceptedTokenProfile: oauth-access-token
    expectedAudience: https://api.example.org/invoices
    issuers:
      - issuerId: corporate-identity
        issuer: https://identity.example.org/
        jwksSource: corporate-identity-jwks
        allowedAlgorithms: [RS256]
        requiredType: at+jwt
        requiredClaims: [iss, sub, aud, exp, iat]
    clockSkewSeconds: 60
    maxTokenAgeSeconds: 900

  partner-callback-api:
    endpointId: partner-callback
    acceptedTokenProfile: partner-signed-jwt
    expectedAudience: https://api.example.org/partner-callback
    issuers:
      - issuerId: partner-alpha
        issuer: https://auth.partner-alpha.example/
        jwksSource: partner-alpha-jwks
        allowedAlgorithms: [ES256]
        requiredClaims: [iss, sub, aud, exp]
    clockSkewSeconds: 30
~~~

Các tên và giá trị trong ví dụ chỉ mô tả cấu trúc logic, không phải cú pháp tiêu chuẩn. Một policy đầy đủ có thể còn bao gồm:

- Loại serialization và profile JWT/JOSE được phép.
- Issuer chính xác và danh sách issuer được phép cho endpoint.
- Audience/resource identifier cần khớp.
- Allowlist thuật toán và yêu cầu đối với metadata khóa.
- JWKS URI hoặc kho khóa đã được đăng ký, kèm cache và rotation policy.
- Claims bắt buộc, kiểu dữ liệu và quy tắc thời gian.
- Yêu cầu tenant/client, scope hoặc token binding.
- Quy tắc thu hồi, chống replay và thời hạn tối đa.
- Mã policy, phiên bản cấu hình và trạng thái hiệu lực.

Policy nên có định danh ổn định để log, kiểm toán và kiểm thử. Mỗi request cần phân giải ra một policy rõ ràng; không nên âm thầm kết hợp các phần cấu hình từ nhiều policy khác nhau nếu chưa có quy tắc hợp nhất được thiết kế và kiểm thử.

## 6. Chọn policy khi hệ thống có nhiều issuer

Một API có thể chấp nhận token từ nhiều issuer, chẳng hạn issuer nội bộ và issuer của một đối tác. Đây là trường hợp cần đặc biệt chú ý vì cùng một kid có thể xuất hiện trong nhiều JWKS, cùng một thuật toán có thể được nhiều issuer sử dụng và các issuer có thể cấp token cho những audience khác nhau.

### 6.1. Endpoint chỉ chấp nhận một issuer

Đây là trường hợp đơn giản nhất. Policy của endpoint đã chỉ định issuer và JWKS tương ứng. Bộ xác minh dùng đúng nguồn khóa đó, sau khi chữ ký hợp lệ thì so sánh claim iss với issuer đã cấu hình.

Giá trị iss trong token không được phép thay đổi nguồn khóa của endpoint. Nếu iss khác policy, token bị từ chối.

### 6.2. Endpoint chấp nhận một tập issuer cố định

Nếu endpoint thực sự cần hỗ trợ nhiều issuer, hãy cấu hình một bảng ánh xạ:

| Endpoint | Issuer được phép | Nguồn khóa | Audience |
| --- | --- | --- | --- |
| Partner API | https://auth.partner-a.example/ | JWKS của partner A đã đăng ký | https://api.example.org/partner |
| Partner API | https://auth.partner-b.example/ | JWKS của partner B đã đăng ký | https://api.example.org/partner |

Có hai chiến lược chính:

- **Thử từng policy trong tập rất nhỏ:** chỉ khi số issuer ít, tập khóa và chi phí được giới hạn, đồng thời không có hành vi rò rỉ thông tin qua khác biệt lỗi/thời gian. Sau khi một policy xác minh thành công, claim iss phải khớp chính xác policy đó.
- **Dùng iss làm gợi ý tra cứu trong allowlist:** parse iss chưa xác minh, so khớp chính xác với khóa của registry, rồi chọn policy đã đăng ký. Không tìm thấy thì từ chối; tìm thấy vẫn phải xác minh chữ ký và kiểm tra lại iss sau xác minh.

Không dùng iss để tải metadata hoặc JWKS của một issuer mới tùy ý. Không chuẩn hóa URL issuer theo suy đoán, ví dụ tự bỏ dấu slash cuối, đổi chữ hoa/thường hoặc bỏ cổng; so khớp phải theo định danh issuer đã được đăng ký và quy tắc của profile.

### 6.3. Tách biệt không gian khóa giữa issuer

Không bao giờ tra kid trên một kho khóa toàn cục không gắn issuer. Hai issuer có thể cùng đặt kid là signing-key-1 nhưng dùng hai cặp khóa khác nhau. Cặp khóa phải được tìm trong đúng tập khóa của issuer được policy lựa chọn.

Cache cũng phải được khóa theo issuer và nguồn JWKS, không chỉ theo kid. Nếu không, khóa của issuer A có thể bị dùng nhầm để kiểm tra token tự khai issuer B.

## 7. Tenant và client: chọn policy mà không tin dữ liệu do request tự khai

### 7.1. Tenant

Trong hệ thống đa tenant, tenant có thể ảnh hưởng đến issuer, audience, khóa, chính sách thời gian hoặc quyền truy cập. Nhưng không phải mọi giá trị tenant trong request đều đáng tin cậy.

Ví dụ, người gọi gửi header X-Tenant-ID: tenant-blue. Nếu ứng dụng dùng ngay giá trị đó để chọn issuer và JWKS, người gọi có thể thử chuyển sang tenant khác hoặc làm hệ thống tin một nguồn khóa không liên quan.

Một quy trình an toàn cần:

1. Xác định tenant từ miền truy cập, client đã xác thực, phiên đã xác minh hoặc ánh xạ server-side được kiểm soát.
2. Kiểm tra người gọi có được phép hoạt động trong tenant đó theo cơ chế độc lập.
3. Tra cứu danh sách issuer và policy đã đăng ký cho tenant.
4. Xác minh JWT bằng nguồn khóa của issuer tương ứng.
5. Sau xác minh, kiểm tra claim tenant trong token có khớp tenant context hay không nếu profile yêu cầu.
6. Khi truy cập tài nguyên, kiểm tra lại quyền và ranh giới dữ liệu tenant.

Nếu tenant chỉ được xác định từ một path hoặc header do client cung cấp, giá trị đó có thể giúp tìm tài nguyên cần yêu cầu nhưng chưa đủ để mở rộng vùng tin cậy. Cần một bước xác thực/ủy quyền ràng buộc nó với danh tính hoặc client.

### 7.2. Client

Client có thể được xác thực bằng mTLS, private_key_jwt hoặc cơ chế khác. Khi client identity đã được xác minh độc lập, policy có thể giới hạn những issuer, token profile hoặc audience mà client được phép dùng.

Không lấy client_id từ payload chưa xác minh để kết luận client đang gọi API. Claim client_id chỉ có thể được dùng sau khi token được xác minh và vẫn cần đối chiếu với ngữ cảnh client độc lập nếu hợp đồng yêu cầu ràng buộc hai bên.

### 7.3. Không trộn tenant, issuer và subject

Ba khái niệm này có ý nghĩa khác nhau:

- **Issuer:** bên phát hành token và chịu trách nhiệm về chữ ký/claims theo hợp đồng.
- **Subject:** chủ thể mà token nói tới trong phạm vi issuer.
- **Tenant:** không gian khách hàng hoặc vùng dữ liệu của ứng dụng.

Một subject có thể trùng chuỗi giữa hai issuer nhưng không nhất thiết là cùng một danh tính. Khóa định danh nội bộ thường phải bao gồm issuer cùng subject, hoặc dùng ánh xạ danh tính đã được xác minh. Không dùng sub đơn lẻ làm khóa định danh toàn cục nếu có nhiều issuer.

## 8. Ngữ cảnh HTTP và reverse proxy

Nhiều triển khai dựa vào hostname, path hoặc header do proxy thêm để xác định endpoint. Các giá trị này chỉ đáng tin cậy khi toàn bộ chuỗi hạ tầng bảo đảm:

- Proxy biên loại bỏ hoặc ghi đè các header định tuyến do client tự gửi, thay vì nối thêm một cách mơ hồ.
- Chỉ proxy được phép mới có thể kết nối trực tiếp đến dịch vụ phía sau, hoặc có cơ chế xác thực proxy.
- Ứng dụng chỉ tin forwarded headers từ proxy đã được xác định; không tin X-Forwarded-Host, X-Forwarded-Proto hoặc X-Forwarded-For từ mọi nguồn.
- Host/authority được kiểm tra với danh sách host được phục vụ; không tạo JWKS URI từ Host tùy ý.
- Endpoint được ánh xạ sang một endpoint ID hoặc resource ID nội bộ đã cấu hình.

Nếu ứng dụng phục vụ nhiều hostname, cần có bảng ánh xạ hostname đã phê duyệt sang tenant/resource/policy. Hostname lạ, header mâu thuẫn hoặc thiếu ngữ cảnh bắt buộc phải bị từ chối.

Không nên lấy URL hiện tại của request rồi ghép thêm đường dẫn /.well-known/openid-configuration hoặc /jwks để tự khám phá issuer. Discovery phải bắt đầu từ issuer đã được đăng ký và được kiểm tra theo một quy trình riêng.

## 9. Discovery và đăng ký issuer có kiểm soát

Trong một hệ sinh thái OAuth/OIDC, issuer có thể công bố metadata chứa endpoint JWKS. Discovery hữu ích khi onboard issuer mới hoặc quản lý endpoint khóa, nhưng cần tách nó khỏi luồng xác minh token thông thường.

Quy trình onboarding an toàn có thể gồm:

1. Quản trị viên hoặc quy trình provisioning xác định issuer dự kiến và lý do tin cậy issuer đó.
2. Hệ thống lấy metadata từ địa chỉ issuer đã đăng ký, qua HTTPS và chính sách egress được kiểm soát.
3. Kiểm tra trường issuer trong metadata khớp chính xác issuer dự kiến.
4. Kiểm tra jwks_uri thuộc nguồn được phép, không chuyển hướng tới địa chỉ ngoài vùng tin cậy.
5. Lấy JWKS, kiểm tra cấu trúc, loại khóa, metadata và giới hạn kích thước/số lượng khóa.
6. Ghi nhận bản ghi issuer, nguồn khóa, thời hạn cache và người/quy trình phê duyệt.
7. Chỉ sau khi đăng ký hoàn tất, policy runtime mới được phép sử dụng issuer đó.

Không để mỗi token mới có iss chưa biết kích hoạt một quy trình onboarding tự động. Nếu cần đăng ký issuer động, đó phải là một workflow quản trị có xác thực, phê duyệt, kiểm tra mạng và audit trail; không phải một hành vi phụ của request xác minh JWT.

## 10. Kiểm tra lại claims theo policy đã chọn

Chọn đúng policy mới chỉ xác định bộ quy tắc cần áp dụng. Sau khi xác minh chữ ký hoặc bảo vệ mã hóa thành công, bên nhận phải kiểm tra claims trong token theo policy đó.

| Claim/thuộc tính | Điều kiện kiểm tra theo policy |
| --- | --- |
| iss | Khớp chính xác issuer gắn với policy đã chọn |
| aud | Chứa audience/resource server của endpoint; xử lý đúng dạng chuỗi hoặc mảng |
| exp | Token chưa hết hạn theo quy tắc thời gian và leeway |
| nbf | Token đã đến thời điểm được phép sử dụng |
| iat | Hợp lý theo đồng hồ, tuổi tối đa và profile nếu có yêu cầu |
| sub | Có mặt, đúng kiểu và ý nghĩa theo loại token/profile |
| typ | Phù hợp loại token được endpoint chấp nhận; typ header và profile cần được xử lý theo hợp đồng |
| tenant | Khớp tenant context đã được xác định độc lập nếu policy yêu cầu |
| client_id/azp | Phù hợp client hoặc ứng dụng được phép theo profile |
| scope/roles | Được diễn giải theo policy và vẫn phải qua bước authorization cho tài nguyên/hành động |

Không phải mọi claim đều bắt buộc với mọi JWT. Policy/profile quyết định claim nào phải có và quy tắc kiểm tra tương ứng. Ví dụ, ID token, access token và JWT dùng trong một giao thức nội bộ có thể có yêu cầu claims khác nhau. Không áp dụng một bộ required claims duy nhất cho mọi loại JWT.

### 10.1. Audience là ranh giới giữa các resource server

Một issuer có thể cấp token cho nhiều API. Việc API A và API B cùng tin issuer không có nghĩa token dành cho API A có thể được dùng ở API B.

Ví dụ:

- Token có aud là https://api.example.org/profile chỉ dành cho API hồ sơ.
- Endpoint hóa đơn yêu cầu https://api.example.org/invoices.
- Chữ ký đúng và issuer đúng nhưng audience không khớp vẫn phải từ chối.

Policy phải quy định audience chính xác cho từng resource server. Không chấp nhận mọi audience chỉ vì chúng cùng domain hoặc có chung tiền tố.

### 10.2. Token profile ngăn nhầm lẫn loại token

Một hệ thống có thể sử dụng nhiều JWT cho các mục đích khác nhau:

- Access token để gọi resource server.
- ID token để client nhận kết quả xác thực người dùng trong OpenID Connect.
- JWT assertion để xác thực client hoặc trao đổi token.
- Token nội bộ cho một luồng nghiệp vụ chuyên biệt.

Không dùng một loại token thay cho loại khác chỉ vì chúng có cùng cấu trúc ba phần và chữ ký hợp lệ. Policy cần phân biệt serialization, typ/profile, audience, issuer và claims bắt buộc. Endpoint chỉ nhận access token không nên chấp nhận ID token dành cho client đăng nhập.

## 11. Fallback và xử lý khi không xác định được policy

Một số lỗi không thể giải quyết bằng cách thử cấu hình khác:

| Tình huống | Hành vi an toàn |
| --- | --- |
| Không xác định được endpoint/resource | Từ chối vì thiếu ngữ cảnh |
| Tenant context mâu thuẫn với route hoặc client đã xác thực | Từ chối và ghi nhận mã lỗi phù hợp |
| Issuer không nằm trong danh sách policy được phép | Từ chối |
| Có nhiều policy phù hợp nhưng không có quy tắc chọn duy nhất | Từ chối do mơ hồ |
| Policy trỏ đến JWKS không khả dụng | Xử lý theo chính sách vận hành đã định nghĩa; không bỏ xác minh |
| Không tìm thấy khóa phù hợp | Refresh giới hạn nếu được phép, sau đó từ chối |
| Header yêu cầu thuật toán ngoài allowlist | Từ chối; không thử thuật toán khác |
| Chữ ký đúng nhưng iss/aud/tenant/profile sai | Từ chối token |
| Token hợp lệ nhưng thiếu quyền với tài nguyên | Từ chối ở bước authorization |

Không nên có fallback kiểu “nếu policy A thất bại thì thử mọi issuer”, “nếu không có audience thì bỏ qua” hoặc “nếu JWKS lỗi thì tin payload”. Những fallback này biến lỗi cấu hình hoặc lỗi hạ tầng thành cơ hội vượt ranh giới tin cậy.

Khi có lỗi cấu hình policy, nên xử lý như lỗi vận hành và phát cảnh báo nội bộ; không chuyển sang policy rộng hơn chỉ để request tiếp tục chạy.

## 12. Mã giả phân giải policy và xác minh token

Đoạn mã giả sau mô tả một API có danh sách issuer được cấu hình sẵn:

~~~text
function validateRequestToken(request):
    endpoint = resolveConfiguredEndpoint(request.routingContext)
    require endpoint exists

    tenantContext = resolveAuthenticatedTenantContext(request)
    clientContext = resolveAuthenticatedClientContext(request)

    policySet = trustedPolicyRegistry.find(
        endpointId = endpoint.id,
        tenantId = tenantContext.id if required,
        clientId = clientContext.id if required
    )
    require policySet is not empty

    rawToken = extractExactlyOneAllowedToken(request)
    require rawToken satisfies input limits

    untrustedHeader = strictParseProtectedHeader(rawToken)
    untrustedIssuer = strictReadIssuerHintIfNeeded(rawToken)

    policy = selectOnePolicyFromConfiguredSet(
        policySet,
        issuerHint = untrustedIssuer,
        tokenHeader = untrustedHeader
    )
    require policy exists and selection is unambiguous

    require untrustedHeader.alg in policy.allowedAlgorithms
    keySet = trustedKeySetFor(policy.issuer, policy.jwksSource)
    key = selectCompatibleKey(keySet, untrustedHeader.kid, untrustedHeader.alg, policy)
    require key exists
    require verifyTokenCryptographically(rawToken, key, policy)

    claims = parseVerifiedClaims(rawToken, policy)
    require claims.iss exactly equals policy.issuer
    require claims.aud contains policy.expectedAudience
    require validateTimeClaims(claims, policy.clockPolicy)
    require validateTokenProfile(claims, untrustedHeader, policy)
    require validateTenantAndClientBinding(claims, tenantContext, clientContext, policy)

    return ValidatedTokenContext(
        policyId = policy.id,
        issuer = claims.iss,
        subject = claims.sub,
        audience = claims.aud,
        claims = claims
    )

function handleProtectedOperation(request):
    tokenContext = validateRequestToken(request)
    require authorizationPolicy.allows(
        tokenContext,
        request.action,
        request.resource
    )
    return executeOperation(request)
~~~

Hàm resolveConfiguredEndpoint phải dựa trên routing đã được bảo vệ. Hàm resolveAuthenticatedTenantContext và resolveAuthenticatedClientContext chỉ trả về ngữ cảnh đã được xác minh độc lập; nếu tenant/client chưa được xác thực thì không được giả định chúng là tin cậy.

Hàm strictReadIssuerHintIfNeeded có thể đọc iss trước xác minh chỉ để tìm trong policySet đã giới hạn. Nó không được tạo policy mới, tạo URL hoặc tải khóa. Sau khi xác minh mật mã, claim iss phải được so khớp lại với policy.

## 13. Kiểm thử lựa chọn policy

Kiểm thử cần xác nhận không chỉ token hợp lệ hay không, mà còn **policy nào được chọn và vì sao**.

| Nhóm | Ca kiểm thử |
| --- | --- |
| Endpoint | API hóa đơn chọn đúng policy hóa đơn; route lạ không rơi về policy mặc định rộng |
| Host/proxy | Host lạ, forwarded header do client giả mạo, proxy không được tin cậy, nhiều giá trị host mâu thuẫn |
| Issuer | Issuer được đăng ký, issuer lạ, issuer sai chữ hoa/thường, issuer có slash khác biệt, issuer hint trỏ policy khác endpoint |
| Multi-issuer | Hai issuer cùng kid, cùng alg nhưng khóa khác nhau; cache không dùng chéo giữa issuer |
| Tenant | Tenant header giả, tenant không được client phép dùng, tenant claim khác tenant context đã xác thực |
| Client | client_id trong token không khớp client đã xác thực; client không được dùng issuer/profile đó |
| Audience | Token đúng chữ ký/issuer nhưng aud dành cho API khác; aud dạng chuỗi và mảng |
| Token profile | ID token gửi tới endpoint access token; typ đúng nhưng chữ ký sai; claims thiếu theo profile |
| Fallback | Không policy, nhiều policy cùng khớp, JWKS lỗi, kid không thấy, không được chuyển sang policy rộng hơn |
| Discovery | Issuer chưa đăng ký, metadata issuer mismatch, jwks_uri redirect hoặc trỏ địa chỉ nội bộ |
| Authorization | Token hợp lệ nhưng scope/role hoặc quyền trên tài nguyên không đủ |

Nên kiểm thử cả cấu hình thay đổi: issuer bị vô hiệu hóa, endpoint đổi audience, tenant được chuyển sang issuer mới và policy được rollback. Các thay đổi cần có hiệu lực nhất quán trên những instance xác minh, đồng thời tránh cache policy cũ quá lâu.

## 14. Vận hành, kiểm toán và thay đổi policy

Chính sách xác minh là một phần của cấu hình bảo mật, do đó cần được quản lý như một tài sản quan trọng:

- Mỗi policy có ID, phiên bản, chủ sở hữu và phạm vi endpoint/tenant/client rõ ràng.
- Thay đổi issuer, audience, thuật toán hoặc JWKS source phải được xem xét và kiểm thử như thay đổi bảo mật.
- Lưu dấu vết ai hoặc quy trình nào đã đăng ký issuer, thay đổi nguồn khóa và vô hiệu hóa policy.
- Khi thu hồi issuer hoặc khóa, có quy trình cập nhật cache và phân phối thay đổi tới mọi điểm xác minh.
- Không ghi token hoặc claims nhạy cảm vào log; chỉ ghi policy ID, mã lỗi, endpoint ID và metadata vận hành cần thiết.
- Theo dõi số request không có policy, issuer không được phép, tenant mismatch, audience mismatch và các lần fallback bị từ chối.

Nếu dùng cache cho policy hoặc issuer registry, cache key cần bao gồm đúng phạm vi như endpoint, tenant và phiên bản policy. Không chia sẻ một policy giữa hai tenant chỉ vì tên issuer hoặc kid giống nhau.

## 15. Checklist triển khai

Trước khi bật xác minh JWT trên một endpoint, hãy kiểm tra:

1. [ ] Endpoint/resource được phân giải từ routing đã được bảo vệ và ánh xạ tới định danh nội bộ rõ ràng.
2. [ ] Tenant và client context chỉ được dùng khi đã xác thực hoặc được ánh xạ server-side có kiểm soát.
3. [ ] Policy được lấy từ registry tin cậy; không được tạo từ header hoặc claims chưa xác minh.
4. [ ] Issuer được phép và nguồn khóa được gắn với đúng endpoint/tenant/client.
5. [ ] Nếu dùng iss làm gợi ý, giá trị đó chỉ tra trong allowlist đã cấu hình và được kiểm tra lại sau xác minh.
6. [ ] Audience được xác định cho resource server cụ thể; không chấp nhận token dành cho API khác.
7. [ ] Token profile phân biệt access token, ID token và các JWT chuyên biệt.
8. [ ] Allowlist thuật toán, metadata khóa, JWKS URI và chính sách cache được xác lập trước.
9. [ ] Không có fallback rộng khi thiếu policy, issuer lạ, khóa không tìm thấy hoặc nguồn JWKS lỗi.
10. [ ] Sau xác minh mật mã, iss, aud, thời gian, tenant/client binding và claims bắt buộc được kiểm tra.
11. [ ] Authorization được thực hiện riêng theo hành động và tài nguyên.
12. [ ] Policy có phiên bản, audit trail, quy trình rotation/disable và kiểm thử thay đổi.

## 16. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** issuer, audience và các registered claims của JWT.
- **RFC 7515 — JSON Web Signature (JWS):** protected header và xác minh chữ ký.
- **RFC 7517 — JSON Web Key (JWK):** cấu trúc khóa và JWK Set.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh issuer/audience, lựa chọn thuật toán và phòng nhầm lẫn giữa các loại JWT.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile dành riêng cho OAuth access token dạng JWT.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata discovery và các endpoint của authorization server.
- **OpenID Connect Discovery 1.0:** cơ chế discovery metadata của OpenID Provider; cần sử dụng cùng quy trình đăng ký issuer tin cậy.

**Nguyên tắc ghi nhớ:** Chọn policy từ ngữ cảnh máy chủ và danh sách tin cậy đã được quản trị. Header/claims chưa xác minh chỉ được dùng trong phạm vi hẹp để đối chiếu hoặc thu hẹp lựa chọn đã cho phép. Sau đó phải xác minh mật mã, issuer, audience, thời gian và token profile trước khi tạo danh tính; cuối cùng mới đánh giá quyền trên tài nguyên.
