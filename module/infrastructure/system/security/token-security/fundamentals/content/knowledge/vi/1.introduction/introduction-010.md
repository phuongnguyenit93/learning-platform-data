# Giới hạn của việc coi token là bằng chứng vĩnh viễn

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích token chứng minh điều gì, và vì sao một token từng được cấp hợp lệ không mặc nhiên tiếp tục đáng tin trong mọi thời điểm.
- Phân biệt **tính toàn vẹn của token**, **hiệu lực của token** và **quyền thực tế đối với tài nguyên**.
- Nhận diện giới hạn của JWT, opaque token, access token, refresh token và ID token trong OAuth 2.0/OpenID Connect (OIDC).
- Thiết kế việc hết hạn, kiểm tra claims, thu hồi, cập nhật quyền và chống đánh cắp/phát lại token theo mức rủi ro.

## 1. Token là bằng chứng có phạm vi và thời hạn

Trong một hệ thống xác thực, token thường được phát hành sau khi một thành phần đáng tin cậy, chẳng hạn **Authorization Server** (máy chủ ủy quyền), xác minh một sự kiện hoặc chấp thuận một quyền truy cập. Ứng dụng gửi token đến **Resource Server** (API bảo vệ tài nguyên), nơi token được kiểm tra trước khi xử lý yêu cầu.

Ví dụ, hệ thống bán hàng cấp access token cho nhân viên được đọc đơn hàng. Token có thể mang thông tin về người dùng, bên phát hành, API đích, phạm vi truy cập và thời điểm hết hạn. Tuy nhiên, việc cấp token lúc 09:00 không đảm bảo rằng lúc 09:10 nhân viên vẫn còn làm việc, còn được phép đọc đơn hàng hay vẫn là người duy nhất nắm giữ token.

Có ba câu hỏi độc lập cần trả lời:

1. **Token có thực sự do nguồn được tin cậy phát hành và có bị sửa đổi không?** Với JWT ký số, câu hỏi này liên quan đến chữ ký, thuật toán và khóa xác minh. Với opaque token, API thường phải hỏi hệ thống quản lý token.
2. **Token có hợp lệ cho yêu cầu hiện tại không?** Cần xét thời gian, bên phát hành, đối tượng nhận, loại token, trạng thái thu hồi và những ràng buộc liên quan.
3. **Hành động trên tài nguyên cụ thể có đang được cho phép không?** Cần xét quyền hiện hành, chủ sở hữu tài nguyên, trạng thái tài khoản, chính sách nghiệp vụ và ngữ cảnh của yêu cầu.

**Token hợp lệ không tự động đồng nghĩa với yêu cầu được phép thực hiện.** Tính hợp lệ về mật mã chỉ giải quyết một phần của quyết định truy cập.

> Nguyên tắc: Tin vào token trong đúng **bên phát hành, mục đích, đối tượng nhận, thời gian và điều kiện** mà nó được cấp; khi quyết định nghiệp vụ phụ thuộc vào trạng thái thay đổi, cần kiểm tra thêm nguồn trạng thái phù hợp.

## 2. Một tình huống cho thấy giới hạn của token

Giả sử API quản lý đơn hàng nhận access token có thời hạn 15 phút.

| Thời điểm | Sự kiện | Điều cần hiểu |
| --- | --- | --- |
| 09:00 | Authorization Server cấp token cho nhân viên A, có quyền đọc đơn hàng. | Quyền tại thời điểm cấp đã được kiểm tra. |
| 09:04 | Quản trị viên khóa tài khoản A vì phát hiện rủi ro. | Trạng thái tài khoản và chính sách đã thay đổi. |
| 09:06 | Một yêu cầu dùng token cũ đến API. | Chữ ký và thời hạn vẫn có thể hợp lệ. |
| 09:06 | API chỉ kiểm tra chữ ký và thời hạn rồi trả dữ liệu. | Quyết định có thể sai nếu nghiệp vụ yêu cầu khóa tài khoản có hiệu lực ngay. |
| 09:15 | Token hết hạn. | Token phải bị từ chối theo thời hạn, nhưng thiệt hại trước đó không tự biến mất. |

Nếu API xác minh JWT **ngoại tuyến** và không có cơ chế biết tài khoản vừa bị khóa, nó không thể tự suy ra thay đổi vào 09:04 từ một token đã được ký lúc 09:00. Hệ thống có thể chọn kiểm tra trạng thái tài khoản ở mỗi yêu cầu, áp dụng danh sách thu hồi, rút ngắn hạn token, hoặc phối hợp nhiều biện pháp; lựa chọn phụ thuộc độ nhạy của thao tác và yêu cầu về độ trễ.

Giả sử token trên bị đánh cắp lúc 09:02. Kẻ tấn công có thể dùng nó như người dùng hợp lệ nếu token là **bearer token** và chưa có cơ chế bổ sung ngăn sử dụng trái phép. Chữ ký của token vẫn đúng vì kẻ tấn công **sao chép** token chứ không chỉnh sửa nó. Do đó, kiểm tra chữ ký không chứng minh người gửi yêu cầu chính là người được cấp token.

## 3. Không phải token nào cũng có cùng ý nghĩa

| Loại token | Dùng để làm gì? | Giới hạn nếu suy diễn quá mức |
| --- | --- | --- |
| **Access token** | Cho client gọi API theo quyền được cấp, đối tượng nhận và thời hạn xác định. | Không chứng minh quyền trên từng bản ghi còn tồn tại; không phải bằng chứng danh tính dùng cho mọi hệ thống. |
| **Refresh token** | Xin access token mới từ Authorization Server khi điều kiện cho phép. | Không phải token để gọi API nghiệp vụ; cần lưu trữ, giới hạn, xoay vòng hoặc ràng buộc phù hợp vì có thể duy trì phiên lâu hơn. |
| **ID token (OIDC)** | Truyền thông tin về sự kiện xác thực cho ứng dụng khách (relying party). | Không nên dùng thay access token để mở quyền gọi Resource Server. Audience và quy tắc kiểm tra của nó phục vụ client nhận ID token. |
| **JWT** | Một định dạng biểu diễn claims, thường được ký để bên nhận kiểm chứng. | Là định dạng chứ không tự chỉ định mục đích; payload JWT ký số thường đọc được, và chữ ký không bảo đảm claims vẫn phản ánh trạng thái hiện tại. |
| **Opaque token** | Giá trị tham chiếu không tự mang dữ liệu để API giải mã theo chuẩn JWT; thường được tra cứu/introspection. | Không mặc nhiên an toàn hơn trước hành vi đánh cắp hoặc phát lại; tra cứu vẫn cần đúng chính sách, và kết quả có thể bị ảnh hưởng bởi cache. |

Hai phân loại **mục đích** (access/refresh/ID) và **định dạng** (JWT/opaque) là hai trục khác nhau: access token có thể là JWT hoặc opaque token. Không nên viết logic “chuỗi có ba phần thì chắc chắn là token được phép vào API”.

Trong OAuth 2.0, access token thường biểu diễn một quyền truy cập đã được **ủy quyền có giới hạn**. Trong OIDC, ID token phục vụ việc cung cấp thông tin xác thực cho client. Cả hai cần được kiểm tra theo hợp đồng giao thức riêng; token được phát hành cho dịch vụ X không thể chỉ vì chữ ký đúng mà trở thành thẻ thông hành cho dịch vụ Y.

## 4. Claims có giá trị, nhưng không phải lời hứa vĩnh viễn

Một access token dạng JWT có thể chứa payload minh họa sau:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "employee-42",
  "aud": "orders-api",
  "scope": "orders:read orders:write",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "tok-example-abc123"
}
~~~

Đây chỉ là payload minh họa, **không phải token hoàn chỉnh** và không đại diện cho một định danh thật. Các mốc thời gian dạng số là Unix timestamp tính bằng giây; **exp** trong ví dụ cách **iat** 900 giây (15 phút).

| Claim | Ý nghĩa thường gặp | Sai lầm khi tin tuyệt đối |
| --- | --- | --- |
| **iss** | Bên phát hành. | Chấp nhận bất kỳ token ký đúng bởi một khóa nào đó mà không xác nhận issuer đáng tin. |
| **sub** | Chủ thể mà token nói đến. | Coi việc biết mã người dùng là bằng chứng người đang gửi yêu cầu chính là chủ thể ấy. |
| **aud** | Đối tượng nhận dự kiến. | Chấp nhận token cấp cho API khác, gây nhầm lẫn giữa các dịch vụ. |
| **scope** | Phạm vi quyền được ủy quyền. | Xem quyền chung “đọc đơn hàng” là quyền đọc **mọi** đơn hàng, bỏ qua kiểm tra quyền theo đối tượng. |
| **iat** | Thời điểm cấp. | Diễn giải thời điểm cấp thành chứng nhận người dùng vừa xác thực lại. |
| **nbf**, **exp** | Thời điểm token bắt đầu có hiệu lực và hết hiệu lực. | Bỏ qua thời gian hoặc áp dụng sai đơn vị; tưởng token chưa hết hạn tức là chưa thể bị thu hồi. |
| **jti** | Mã định danh token, nếu issuer có cấp. | Nghĩ rằng chỉ cần có mã này là tự động phát hiện phát lại; cần cơ chế lưu/đối chiếu mới làm được điều đó. |

Một token do issuer đáng tin cậy phát hành có thể phản ánh **ảnh chụp của một quyết định trong quá khứ**. Những tình huống như thay đổi vai trò, chuyển bộ phận, hủy quyền truy cập dự án, khóa tài khoản, chấm dứt hợp đồng hoặc đổi chính sách dữ liệu đều có thể khiến ảnh chụp đó không còn đủ để cho phép yêu cầu mới.

Đặc biệt, **scope là một giới hạn quyền được cấp**, không thay thế kiểm tra quyền sở hữu hay chính sách cho từng tài nguyên. Scope “orders:read” có thể đủ điều kiện để yêu cầu được xem xét, nhưng API vẫn phải xác minh nhân viên có quyền đọc **đơn hàng số 123** hay không.

## 5. Ba lớp kiểm tra tại Resource Server

Một thiết kế dễ kiểm soát thường chia việc xử lý thành ba lớp:

**Lớp 1 — Kiểm tra token và nguồn tin cậy.** Xác định token thuộc loại API chấp nhận, issuer có nằm trong danh sách tin cậy, chữ ký JWT hợp lệ với thuật toán được cho phép và khóa tương ứng, hoặc trạng thái opaque token được xác nhận qua dịch vụ đáng tin. Không chọn thuật toán xác minh chỉ vì header của token yêu cầu; cần cấu hình thuật toán được chấp nhận theo issuer và loại token. Khi dùng JWT, cần xử lý an toàn cơ chế chọn khóa, đổi khóa và cache khóa công khai.

**Lớp 2 — Kiểm tra ràng buộc đối với yêu cầu.** Kiểm tra audience của **API này**, thời hạn (**exp**), thời điểm bắt đầu hiệu lực (**nbf**), phạm vi quyền và những ràng buộc bổ sung mà hệ thống thực sự cam kết sử dụng. Sai lệch đồng hồ chỉ nên được bù trong khoảng nhỏ được cấu hình; không biến thời hạn thành vô nghĩa. Một token hợp lệ về chữ ký nhưng sai audience hoặc hết hạn phải bị từ chối.

**Lớp 3 — Ra quyết định truy cập hiện hành.** Với thao tác yêu cầu quyền động, kiểm tra tài khoản có bị khóa không, quyền hiện tại có đáp ứng chính sách không, người dùng có sở hữu hoặc được giao quản lý tài nguyên không, và thao tác có cần xác thực lại hay phê duyệt bổ sung không.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant API as Orders API
    participant P as Nguồn quyền hiện tại

    C->>AS: Đăng nhập / nhận ủy quyền
    AS-->>C: Access token
    C->>API: Yêu cầu + access token
    API->>API: Kiểm loại token, issuer, chữ ký/trạng thái, audience, thời hạn, scope
    API->>P: Kiểm tài khoản và quyền với đơn hàng
    P-->>API: Quyết định theo chính sách hiện hành
    API-->>C: Kết quả hoặc từ chối
~~~

Ví dụ thuật toán ở mức mô tả (không phải mã nguồn dùng trực tiếp trong production):

~~~text
authorize(request, orderId):
    token = extractAccessToken(request)
    claims = verifyTokenUsingTrustedIssuerAndAllowedAlgorithm(token)
    require claims.isValid
    require claims.audience includes "orders-api"
    require claims.isWithinValidityWindow
    require claims.scope includes "orders:read"
    require tokenIsNotRevokedIfThisSystemTracksRevocation(token)
    require accountIsActive(claims.subject)
    require currentPolicyAllows(claims.subject, "read", orderId)
    return ALLOW
~~~

Ở đây, **tokenIsNotRevokedIfThisSystemTracksRevocation** chỉ là một điểm mở rộng: cách thực hiện phụ thuộc mô hình JWT, introspection, danh sách thu hồi hoặc trạng thái phiên. Nếu hệ thống không kiểm tra trạng thái hiện hành trong một luồng nhất định, cần **nói rõ độ trễ chấp nhận được** trước khi thay đổi quyền có hiệu lực, không giả định luôn đạt tính tức thời.

Trong HTTP API, token thiếu/không hợp lệ thường dẫn đến **401 Unauthorized** (kèm challenge phù hợp); token đã được chấp nhận nhưng không đủ quyền thường dẫn đến **403 Forbidden**. Các phản hồi cần tránh tiết lộ thông tin nội bộ về tài khoản và tài nguyên.

## 6. Hết hạn, thu hồi và thay đổi quyền là ba vấn đề liên quan nhưng khác nhau

**Hết hạn** là giới hạn thời gian đã đặt khi cấp token. Access token sống ngắn giúp thu hẹp cửa sổ sử dụng nếu bị lộ, nhưng không thể tự động dừng ngay mọi token đang lưu hành khi tài khoản bị khóa giữa chừng.

**Thu hồi (revocation)** là hành động hoặc trạng thái khiến token không còn được chấp nhận trước hạn hết hiệu lực dự kiến. Trong OAuth 2.0, có cơ chế chuẩn để client yêu cầu thu hồi token (RFC 7009). Hiệu lực của thu hồi đối với các token đã phát hành phụ thuộc cách Authorization Server và Resource Server phối hợp; không nên ngầm kết luận mọi API đã biết ngay tức thì.

**Thay đổi quyền** là cập nhật chính sách đối với chủ thể hoặc tài nguyên. Ngay cả khi token còn “active”, thao tác vẫn có thể phải bị từ chối vì vai trò đã đổi, tài nguyên chuyển chủ, quyền ủy quyền bị rút hoặc quy định nghiệp vụ không còn cho phép.

Các cơ chế thường phối hợp như sau:

| Cơ chế | Giải quyết tốt điều gì? | Điểm cần đánh đổi hoặc kiểm soát |
| --- | --- | --- |
| Access token sống ngắn | Giới hạn thời gian token bị lộ có thể bị lợi dụng. | Không bảo đảm vô hiệu hóa ngay; phụ thuộc đồng hồ và khả năng cấp token mới. |
| Opaque token + introspection | Cho phép Resource Server hỏi trạng thái token từ Authorization Server (RFC 7662). | Thêm phụ thuộc mạng, độ trễ, tính sẵn sàng; cache kết quả “active” có thể làm chậm nhận biết thu hồi. |
| JWT + danh sách thu hồi / trạng thái phiên | Dừng một số JWT trước khi hết hạn dù kiểm tra chữ ký ngoại tuyến. | Cần đồng bộ dữ liệu, TTL và dọn thông tin thu hồi; thực tế lại có phần kiểm tra trạng thái tập trung. |
| Kiểm tra quyền trên tài nguyên | Phản ánh vai trò, chủ sở hữu và chính sách nghiệp vụ mới. | Tốn truy vấn hoặc yêu cầu cache được thiết kế theo mức độ nhạy cảm. |
| Refresh token rotation | Giới hạn khả năng dùng lâu dài của refresh token bị sao chép, tạo tín hiệu khi phát hiện tái sử dụng token cũ. | Cần theo dõi họ token/phiên, xử lý sử dụng đồng thời hợp lệ và thu hồi khi nghi bị xâm phạm. |
| Token ràng buộc với bên gửi (ví dụ DPoP, mTLS) | Giảm giá trị của bản sao token nếu kẻ tấn công không có khóa ràng buộc. | Cần client và API hỗ trợ, bảo vệ khóa và kiểm tra proof; không loại bỏ mọi rủi ro trên thiết bị bị chiếm quyền. |

Không có một con số thời gian sống đúng cho tất cả hệ thống. Token cho thao tác đọc thông tin công khai và token cho chuyển tiền hoặc quản trị bảo mật có mức rủi ro khác nhau. Quyết định thiết kế cần quy định rõ **thời gian tối đa mà thay đổi quyền hoặc thu hồi có thể chưa được phản ánh**. Nếu tổ chức yêu cầu khóa tài khoản có hiệu lực gần như ngay lập tức, chỉ dựa vào JWT hết hạn sau 15 phút là chưa đủ.

## 7. Refresh token không biến quyền truy cập thành vô hạn

Trong OAuth 2.0, refresh token giúp client xin access token mới **khi phiên hoặc sự ủy quyền vẫn còn được chấp nhận**. Điều này khác với việc client có một quyền vĩnh viễn.

Một vòng đời hợp lý có thể là:

1. Authorization Server cấp access token có hạn dùng ngắn và, nếu luồng thích hợp, refresh token được bảo vệ tốt hơn.
2. Resource Server chỉ chấp nhận access token phù hợp; refresh token được gửi đến đúng endpoint của Authorization Server.
3. Khi access token hết hạn, client xin token mới; máy chủ có thể xét trạng thái phiên, quyền ủy quyền, thiết bị và chính sách.
4. Khi người dùng đăng xuất, tài khoản bị khóa hoặc phát hiện rủi ro, hệ thống có thể thu hồi refresh token/phiên và thực thi chính sách thu hồi access token đang lưu hành.
5. Nếu sử dụng **refresh token rotation**, lần làm mới hợp lệ nhận refresh token mới và token cũ bị vô hiệu theo quy tắc của máy chủ. Việc tái sử dụng token cũ bất thường là tín hiệu có thể đã xảy ra sao chép token.

Cần định nghĩa quy tắc xử lý khi hai yêu cầu làm mới đến gần nhau: tái sử dụng do cạnh tranh hợp lệ và tái sử dụng do đánh cắp có biểu hiện gần giống nhau. Không nên tuyên bố mọi lần dùng token cũ đều là tấn công mà không xét hành vi client và thiết kế máy chủ.

OIDC cũng cần được hiểu đúng: **ID token không phải access token**, còn claim phản ánh thời điểm xác thực (ví dụ **auth_time** trong ngữ cảnh OIDC) có thể hữu ích để yêu cầu xác thực mới cho thao tác nhạy cảm. Có một ID token cũ hoặc một access token vẫn chưa hết hạn không chứng minh người dùng vừa cung cấp yếu tố xác thực gần đây.

## 8. Đánh cắp và phát lại: token hợp lệ vẫn có thể do kẻ khác cầm

Phần lớn access token dạng bearer có tính chất: **ai nắm giữ giá trị token có thể thử sử dụng nó**. Vì vậy cần bảo vệ token từ lúc phát hành, truyền tải, lưu trữ, ghi log cho đến khi hết hạn hoặc bị hủy.

Một số tình huống cần thiết kế cụ thể:

| Tình huống | Vì sao kiểm tra chữ ký không đủ? | Biện pháp phù hợp |
| --- | --- | --- |
| Token lọt vào log, URL, công cụ theo dõi lỗi | Kẻ khác có thể sao chép nguyên chuỗi hợp lệ. | Truyền qua TLS và header phù hợp; tránh token trong URL; che token trong log và telemetry; thu hồi khi lộ. |
| XSS đọc dữ liệu lưu trong trình duyệt | Mã độc chạy cùng ngữ cảnh có thể truy cập token nếu nơi lưu cho phép. | Hạn chế XSS/CSP; cân nhắc mô hình BFF hoặc cookie **HttpOnly, Secure, SameSite** cùng biện pháp chống CSRF thích hợp; tránh lưu token dài hạn tại nơi JavaScript có thể đọc khi không cần thiết. |
| Thiết bị hoặc máy chủ bị xâm nhập | Khóa/tokens có thể bị lấy từ môi trường đang chạy. | Kho lưu an toàn của hệ điều hành, quản lý secret, ràng buộc token theo bên gửi nếu phù hợp, phát hiện bất thường và thu hồi phiên. |
| Dùng lại token sau khi vai trò bị rút | Token cũ vẫn chứa scope hoặc role tại lúc cấp. | Kiểm tra quyền động, trạng thái phiên/thu hồi hoặc token ngắn hạn với độ trễ chấp nhận được. |
| Gửi token cho API sai | Chữ ký đúng không bảo đảm token được cấp cho API đó. | Kiểm tra **aud**, **iss**, loại token và scope theo hợp đồng của từng API. |
| Phát lại yêu cầu quan trọng | Bearer token hợp lệ không tự ngăn cùng token được sử dụng nhiều lần. | Ràng buộc bên gửi (DPoP/mTLS khi phù hợp); chống phát lại proof, khóa idempotency/nonce riêng cho thao tác cần tính duy nhất. |

Với **DPoP**, client chứng minh quyền kiểm soát khóa qua proof gắn với yêu cầu; Resource Server phải xác minh proof, các trường ràng buộc và cơ chế chống phát lại theo giao thức. Với **mTLS**, token có thể được ràng buộc với chứng chỉ client. Hai cơ chế này làm token bị sao chép khó sử dụng hơn, nhưng không thay thế bảo vệ khóa, chống tấn công ở client và kiểm tra quyền truy cập.

Lưu ý rằng **chống phát lại token** và **chống thực thi trùng một giao dịch** là hai bài toán khác nhau. Ngay cả với một token hợp lệ dùng đúng chủ sở hữu, API thanh toán vẫn cần idempotency hoặc cơ chế nghiệp vụ tương đương để tránh xử lý một lệnh nhiều lần.

## 9. Một số ngộ nhận cần loại bỏ

**“JWT có chữ ký nên thông tin trong đó luôn đúng.”** Chữ ký giúp kiểm tra dữ liệu không bị sửa sau khi ký và được ký bởi khóa phù hợp. Nó không cập nhật trạng thái tài khoản, vai trò hoặc chủ sở hữu tài nguyên sau thời điểm phát hành.

**“Có exp là đã giải quyết thu hồi.”** Exp đặt một giới hạn thời gian; thu hồi trước hạn cần cơ chế hoặc chính sách bổ sung. Thời gian sống ngắn chỉ giới hạn khoảng rủi ro.

**“Opaque token luôn cho phép thu hồi tức thì.”** Opaque token thường thuận lợi cho kiểm tra trạng thái tập trung, nhưng độ trễ tra cứu, cache và cách triển khai vẫn quyết định thời gian có hiệu lực của thu hồi.

**“Nếu scope cho phép thì không cần kiểm tra quyền dữ liệu.”** Scope giới hạn phạm vi mà client được ủy quyền; quyền thực hiện hành động trên bản ghi cụ thể phải xét chính sách nghiệp vụ hiện hành.

**“Đăng xuất khỏi giao diện là mọi token đã vô hiệu.”** Xóa token phía client chỉ loại bỏ một bản sao do client kiểm soát. Token từng bị sao chép vẫn có thể tồn tại, nên cần chiến lược xử lý phiên, refresh token và access token ở phía máy chủ.

**“Đổi khóa ký là cách chuẩn để thu hồi một tài khoản.”** Đổi/loại khóa có thể làm vô hiệu hóa hàng loạt token được ký bằng khóa đó, tác động rất rộng. Đây là công cụ xử lý vòng đời hoặc sự cố khóa, thường không phù hợp để thu hồi một phiên đơn lẻ.

## 10. Áp dụng vào thiết kế API

Khi xây dựng dịch vụ xác thực, phân quyền và OAuth 2.0/OIDC, hãy trả lời rõ các câu hỏi sau trong tài liệu thiết kế:

- **Nguồn tin cậy là ai?** API chấp nhận issuer, kiểu token, thuật toán xác minh và tập khóa nào? Ranh giới tin cậy giữa các dịch vụ được xác định thế nào?
- **Token được cấp cho ai và để làm gì?** API kiểm tra audience, scope và loại token ra sao? Có ngăn sử dụng ID token hoặc refresh token sai mục đích không?
- **Token còn hiệu lực lúc nhận yêu cầu không?** Có kiểm tra exp, nbf và trạng thái thu hồi cần thiết không? Cách xử lý lệch đồng hồ, đổi khóa, lỗi introspection được quy định thế nào?
- **Quyền hiện tại nằm ở đâu?** Những hành động nào cần truy vấn chính sách, vai trò, chủ sở hữu tài nguyên hoặc trạng thái tài khoản mới nhất? Cache quyền được phép cũ tối đa bao lâu?
- **Token bị lộ sẽ ra sao?** Token sống bao lâu, được lưu ở đâu, có xuất hiện trong URL/log không, có ràng buộc bên gửi và cơ chế thu hồi/giám sát phù hợp không?
- **Refresh token bị sao chép sẽ ra sao?** Có rotation, phát hiện reuse, thu hồi họ token hoặc yêu cầu xác thực lại theo mức rủi ro không?
- **Có kiểm chứng kịch bản thay đổi giữa phiên không?** Thử khóa tài khoản, thu hồi quyền, chuyển chủ sở hữu tài nguyên, dùng token cho sai API, phát lại token và dùng token hết hạn.

Những thao tác nguy cơ cao như đổi email khôi phục, thêm khóa truy cập, chuyển tiền hoặc nâng quyền có thể cần **xác thực lại gần thời điểm thực hiện**, kiểm tra phiên hiện hành và phê duyệt bổ sung. Việc một access token còn hiệu lực không tự thỏa các yêu cầu này.

### Ví dụ vận dụng: API đọc đơn hàng

API nhận access token JWT còn 8 phút trước khi hết hạn; token có audience là “orders-api” và scope “orders:read”. Nhân viên vừa bị rút khỏi nhóm phụ trách đơn hàng số 123.

- **Kiểm tra mật mã/thời gian:** Có thể đạt nếu chữ ký, issuer, audience và thời gian đều hợp lệ.
- **Kiểm tra scope:** Có thể đạt vì token vẫn chứa “orders:read”.
- **Kiểm tra quyền đối với đơn hàng 123:** Phải từ chối nếu chính sách hiện hành yêu cầu thành viên nhóm phụ trách và nhân viên không còn thỏa điều kiện.
- **Bài học thiết kế:** Một chữ ký hợp lệ và một scope đúng chỉ đưa yêu cầu đến bước đánh giá quyền; chúng không đóng vai trò chứng nhận quyền vĩnh viễn.

## Kết luận

Token là **bằng chứng có điều kiện tại thời điểm sử dụng**, gắn với một bên phát hành đáng tin cậy, mục đích sử dụng, đối tượng nhận, thời hạn và trạng thái hệ thống. JWT, opaque token, access token, refresh token và ID token giải quyết những phần khác nhau của quy trình xác thực và ủy quyền; không loại nào tự tạo ra quyền truy cập bất biến.

Một hệ thống an toàn phải kết hợp **xác minh token**, **giới hạn vòng đời**, **khả năng nhận biết thu hồi/thay đổi quyền** và **quyết định phân quyền trên tài nguyên hiện hành**. Khi có rủi ro đánh cắp hoặc phát lại, cần thêm biện pháp bảo vệ quá trình lưu trữ, truyền tải, khóa chứng minh sở hữu và hành vi nghiệp vụ. Điều cần thiết kế rõ nhất là: **hệ thống chấp nhận thông tin trong token cũ tới thời điểm nào, trong tình huống nào và với hậu quả gì?**

### Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
