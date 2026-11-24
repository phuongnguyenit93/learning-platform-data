# Chọn loại token theo rủi ro và yêu cầu kiểm tra

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt bốn quyết định **mục đích token**, **định dạng token**, **cách chứng minh quyền sở hữu token** và **vòng đời token** trước khi lựa chọn giải pháp.
- Đánh giá khi nào nên dùng JWT tự xác minh, opaque token với introspection, hoặc cơ chế kết hợp để đáp ứng yêu cầu thu hồi quyền.
- Chọn access token, refresh token và ID token đúng vai trò trong OAuth 2.0/OpenID Connect (OIDC), tránh nhầm định dạng token với quyền truy cập.
- Lượng hóa những đánh đổi về độ trễ kiểm tra, tính sẵn sàng, tính mới của quyền, rò rỉ dữ liệu trong claims và nguy cơ token bị đánh cắp hoặc phát lại.
- Xây dựng một phương án cấp phát, xác minh, lưu trữ, thu hồi và giám sát token cho tình huống thực tế.

## 1. Chọn token là bài toán thiết kế ranh giới tin cậy

Trong một hệ thống xác thực và phân quyền, câu hỏi “Nên dùng JWT hay opaque token?” thường được đặt ra quá sớm. Trước khi so định dạng, cần biết **token cấp cho ai, dùng để chứng minh điều gì, ở đâu, trong bao lâu và bên nhận cần xác minh những điều kiện nào**.

Ví dụ cùng một người dùng có thể:

1. Đăng nhập vào ứng dụng bằng một luồng OIDC, nơi client nhận **ID token** để xác minh thông tin xác thực.
2. Nhận **access token** với audience là Orders API để gọi API đọc đơn hàng.
3. Nhận **refresh token** (nếu được cấp) để xin access token mới từ Authorization Server.
4. Thực hiện một thao tác hoàn tiền có rủi ro cao, nơi Resource Server cần **kiểm tra quyền hiện hành, trạng thái giao dịch và có thể yêu cầu xác thực lại** dù access token chưa hết hạn.

Ba token đầu **khác nhau về mục đích**; quyết định dùng JWT hay opaque token là một lựa chọn khác, thường liên quan đến cách Resource Server xác minh access token.

**Nguyên tắc cốt lõi:** Một token có chữ ký đúng hoặc được introspection trả về “active” chưa đủ để cấp quyền cho mọi thao tác. Quyết định truy cập cần kết hợp xác minh token với scope, audience, chính sách và trạng thái của tài nguyên.

## 2. Bốn trục lựa chọn phải xét độc lập

| Trục thiết kế | Những lựa chọn thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Mục đích** | Access token, refresh token, ID token (OIDC). | Token gửi đến Resource Server, token endpoint hay client? |
| **Định dạng và cách tra cứu** | JWT có chữ ký, opaque/reference token, các định dạng được profile hỗ trợ. | Resource Server xác minh tại chỗ hay hỏi Authorization Server? |
| **Cách sử dụng** | Bearer hoặc token ràng buộc với bên gửi (DPoP/mTLS khi hỗ trợ). | Người sao chép token có thể dùng nó mà không có khóa/chứng chỉ không? |
| **Vòng đời và thu hồi** | Hạn ngắn, introspection, danh sách thu hồi, rotation, trạng thái phiên và quyền động. | Thay đổi quyền hoặc khóa tài khoản có hiệu lực nhanh đến đâu? |

Không thể lấy **JWT** làm đối lập với **refresh token** vì một thuật ngữ chỉ định dạng, còn thuật ngữ kia chỉ mục đích. Access token có thể là JWT hoặc opaque; refresh token thường được AS quản lý theo trạng thái và có thể có dạng opaque; ID token OIDC thông thường là JWT theo quy định giao thức.

Tương tự, **JWT không mặc nhiên là bearer**, và **opaque token không mặc nhiên có ràng buộc bên gửi**. Cơ chế chống sao chép/phát lại phải được thiết kế và xác minh riêng.

## 3. Lập hồ sơ rủi ro trước khi chọn định dạng

Xác định ít nhất sáu chiều của tình huống sử dụng:

| Chiều rủi ro / yêu cầu | Câu hỏi đánh giá | Hệ quả thiết kế có thể phát sinh |
| --- | --- | --- |
| **Độ nhạy dữ liệu** | Token mở đường tới thông tin công khai, đơn hàng, hồ sơ y tế hay thanh toán? | Dữ liệu nhạy cảm đòi hỏi quyền hẹp, kiểm tra động và giám sát chặt hơn. |
| **Mức thiệt hại khi bị lạm dụng** | Chỉ đọc dữ liệu, sửa quyền, duyệt giao dịch hay chuyển tiền? | Hành động không thể hoàn tác có thể cần step-up, duyệt bổ sung, chống xử lý trùng. |
| **Thời gian tối đa chấp nhận quyền cũ** | Sau khi khóa tài khoản, token cũ được phép tiếp tục trong tối đa bao lâu? | Yêu cầu gần tức thời thường cần kiểm tra trạng thái trực tuyến hoặc cơ chế đồng bộ thu hồi. |
| **Khả năng kết nối** | Resource Server có thể hỏi AS trên mỗi request không? | Kiểm tra JWT tại chỗ giảm phụ thuộc mạng nhưng cần chấp nhận giới hạn về tính mới trạng thái. |
| **Môi trường client** | Backend bí mật, SPA, mobile, thiết bị IoT hay ứng dụng bên thứ ba? | Cách lưu token, xác thực client, rotation và ràng buộc khóa thay đổi. |
| **Số lượng API và ranh giới tổ chức** | Một API, nhiều audience, nhiều tenant hoặc nhiều miền tin cậy? | Cần kiểm tra issuer, audience, scope và chính sách theo tenant; tránh chuyển tiếp token sai đích. |

Nên ghi kết quả dưới dạng **yêu cầu kiểm chứng được**, thay vì những nhãn chung như “bảo mật cao”:

~~~text
Ví dụ: API duyệt hoàn tiền
- Chỉ nhận access token dành cho refunds-api.
- Tài khoản bị khóa phải bị chặn đối với yêu cầu mới trong giới hạn vận hành đã định.
- Mỗi thao tác cần quyền duyệt hiện hành trên đúng tenant và đúng giao dịch.
- Token bị lộ phải có khả năng thu hồi theo quy trình sự cố.
- Yêu cầu cần chống thực thi trùng và có nhật ký quyết định truy cập.
~~~

Giới hạn vận hành phải do tổ chức xác định. Không có một thời hạn token hoặc một loại token nào tự đáp ứng mọi mức rủi ro.

## 4. JWT access token: kiểm tra tại chỗ, cần hiểu giới hạn dữ liệu

Với JWT access token **được ký**, Resource Server thường xác minh chữ ký và claims bằng khóa tin cậy của issuer, không phải gọi lại AS để hỏi trạng thái token trên từng yêu cầu.

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-7d2"
}
~~~

Đây chỉ là payload giả, **chưa phải JWT đầy đủ**. Giá trị **exp** cách **iat** 900 giây (15 phút); ví dụ không đề xuất thời hạn mặc định.

### JWT thuận lợi khi nào?

- API cần xác minh nhiều request với độ trễ thấp và lượng truy cập cao.
- Nhiều Resource Server có thể quản lý tập issuer/khóa công khai đáng tin theo một hợp đồng thống nhất.
- Có thể chấp nhận token phản ánh một số claims tại **thời điểm phát hành**, trong giới hạn thời gian sống đã xác định.
- Kết nối đến AS có thể gián đoạn nhưng API vẫn có đủ dữ liệu và chính sách cần thiết để ra quyết định với một token hợp lệ.
- Token chỉ chứa thông tin tối thiểu, không làm lộ dữ liệu nhạy cảm khi client hoặc thành phần trung gian đọc payload.

### JWT có các đánh đổi nào?

**Chữ ký không cập nhật quyền.** Nếu người dùng bị xóa role lúc 10:02 còn JWT được cấp lúc 10:00 và hết hạn lúc 10:15, API chỉ xác minh JWT ngoại tuyến có thể không biết quyền đã bị thu hồi lúc 10:02.

**JWT ký số thường không được mã hóa.** Payload dạng JWS thường có thể giải mã để đọc, dù không thể tùy tiện sửa mà vẫn giữ chữ ký hợp lệ. Không lưu mật khẩu, secret, dữ liệu nhạy cảm hoặc toàn bộ hồ sơ người dùng trong claims. Khi có yêu cầu bảo mật nội dung, cần xem xét thiết kế tránh đưa dữ liệu vào token hoặc một cơ chế mã hóa đúng chuẩn; chỉ “base64url” không phải mã hóa.

**Khóa và thuật toán là một phần của ranh giới tin cậy.** Cần khóa xác minh đúng issuer, thuật toán trong danh sách cho phép, quy trình đổi khóa và cache JWKS an toàn. Không chấp nhận thuật toán do header token tự quyết định; không dùng khóa lấy từ URL chưa được tin cậy do token cung cấp.

**Token càng nhiều claims càng dễ lỗi thời và càng rộng ảnh hưởng.** Nhúng toàn bộ role, permission và tenant vào JWT có thể làm API bỏ qua policy hiện hành. Chỉ nhúng những claims đã có hợp đồng kiểm tra rõ ràng và còn phù hợp trong vòng đời token.

## 5. Opaque access token: kiểm tra trạng thái qua máy chủ tin cậy

**Opaque token** là giá trị mà Resource Server không diễn giải trực tiếp như JWT theo hợp đồng token hiện hành. Thông thường AS lưu hoặc giải quyết token thành trạng thái và thuộc tính; Resource Server dùng **introspection** (RFC 7662) hoặc cơ chế tra cứu tin cậy khác.

Ví dụ token client nhận:

~~~text
access_token = "opaque_example_K4s9..."  // giá trị giả
~~~

Resource Server có thể gọi introspection endpoint sau khi xác thực theo phương thức mà AS yêu cầu. Phản hồi minh họa:

~~~json
{
  "active": true,
  "client_id": "dashboard-client",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1730000900
}
~~~

Một phản hồi **active: true** cho biết trạng thái token theo thông tin của AS **tại thời điểm introspection**, không khẳng định người dùng có quyền với mọi đơn hàng. API vẫn phải áp dụng audience, scope, tenant và policy.

### Opaque token thuận lợi khi nào?

- Tổ chức muốn tập trung kiểm soát token, hỗ trợ thu hồi trước hạn và cập nhật trạng thái token.
- Resource Server có thể truy vấn AS/dịch vụ introspection an toàn, với độ trễ và tính sẵn sàng đáp ứng yêu cầu.
- Client không cần tự đọc payload token và tổ chức muốn giảm dữ liệu thông tin nhúng trực tiếp trong access token.
- Chính sách yêu cầu hạn chế khả năng các hệ thống ngoài phạm vi đọc claims nội bộ.

### Đánh đổi cần định lượng

- **Mỗi lần introspection** có chi phí mạng, khả năng quá tải và phụ thuộc vào trạng thái AS.
- Nếu **cache kết quả active**, việc thu hồi có thể bị nhận biết muộn trong thời gian cache còn hiệu lực, cộng với độ trễ đồng bộ giữa các hệ thống.
- Nếu không cache, phải có khả năng chịu tải, bảo vệ endpoint, giới hạn truy cập và chính sách khi AS lỗi.
- Nếu Resource Server dùng kết quả cũ khi AS không truy cập được, phải ghi rõ rủi ro và điều kiện; với thao tác nhạy cảm, thường nên từ chối khi không xác minh được trạng thái cần thiết.
- **Opaque không tự chống đánh cắp**: một giá trị opaque dạng bearer bị sao chép vẫn có thể dùng được cho tới khi bị từ chối.

**Kết luận lựa chọn:** JWT hợp lý khi cần kiểm tra địa phương và có thể quản trị độ trễ thu hồi; opaque hợp lý khi muốn tra cứu trạng thái tập trung và chấp nhận phụ thuộc dịch vụ. Cả hai đều cần kiểm tra phân quyền đúng tài nguyên.

## 6. So sánh yêu cầu kiểm tra JWT và opaque token

| Tiêu chí | JWT ký số, xác minh ngoại tuyến | Opaque token, introspection |
| --- | --- | --- |
| Xác minh nguồn | Chữ ký, khóa, issuer và thuật toán tin cậy. | Kênh và endpoint introspection tin cậy, xác thực Resource Server, trạng thái do AS trả về. |
| Kiểm tra còn hiệu lực | exp, nbf, audience, loại token và các ràng buộc đã cấu hình. | active, exp khi có, audience, scope và các thuộc tính theo hợp đồng. |
| Phụ thuộc AS mỗi request | Thường không cần nếu khóa đã có và không yêu cầu trạng thái online khác. | Có nếu không cache; giảm khi cache nhưng đổi lấy trạng thái có thể cũ. |
| Phản ánh thu hồi trước hạn | Cần blacklist/denylist, phiên/policy lookup hoặc cơ chế khác; không do chữ ký tự quyết. | Có thể phản ánh trạng thái AS khi introspection đủ mới và AS đã ghi nhận thu hồi. |
| Dữ liệu có thể lộ ở token | Payload JWS thường đọc được. | Client thường chỉ thấy chuỗi tham chiếu; dữ liệu tại AS vẫn cần bảo vệ. |
| Quyền theo tài nguyên | Vẫn cần đánh giá policy/owner/tenant khi phù hợp. | Vẫn cần đánh giá policy/owner/tenant khi phù hợp. |
| Rủi ro chính | Claims cũ, xử lý khóa sai, chấp nhận nhầm audience hoặc loại token. | Phụ thuộc mạng, cache stale, cấu hình introspection, token bị sao chép. |

Thực tế có thể dùng **phương án lai**: JWT ký số thời hạn ngắn để xác minh ngoại tuyến, cộng một truy vấn quyền hiện hành cho thao tác quan trọng; hoặc opaque token với cache introspection rất ngắn và cơ chế vô hiệu cache khi thu hồi. “JWT” và “opaque” không bắt buộc kéo theo hai kiến trúc hoàn toàn tách biệt.

## 7. Khung quyết định theo khả năng thu hồi và tính sẵn sàng

Hai yêu cầu thường kéo ngược nhau: **phải kiểm tra quyền mới nhất** và **API vẫn hoạt động khi AS không sẵn sàng**.

**Độ trễ thu hồi** được mô tả bằng câu hỏi: sau một thay đổi tại nguồn sự thật, mất tối đa bao lâu trước khi một request dùng thông tin cũ bị từ chối?

Với JWT chỉ xác minh ngoại tuyến, không có danh sách thu hồi hoặc kiểm tra chính sách, thời gian chấp nhận token cũ có thể kéo dài tới **phần thời hạn còn lại** của token, cùng sai lệch đồng hồ được cho phép. Nếu JWT mới được phát hành ngay trước khi quyền bị rút, giá trị gần bằng toàn bộ TTL của access token.

Với opaque token introspection, thời gian nhận biết thu hồi phụ thuộc ít nhất vào:

1. Thời gian AS ghi nhận và phản ánh trạng thái thu hồi.
2. TTL cache introspection (nếu có) tại Resource Server/gateway.
3. Độ trễ lan truyền sự kiện, đồng bộ hoặc cache khác trong hạ tầng.
4. Chính sách xử lý lỗi khi truy vấn trạng thái thất bại.

Không nên hứa “thu hồi tức thì” nếu có cache trạng thái active hoặc dữ liệu phân quyền bị chậm đồng bộ.

~~~mermaid
flowchart TD
    A["Mục đích: Resource Server cần access token"] --> B{"Phải phản ánh thu hồi/quyền mới gần như ngay?"}
    B -->|Có| C{"Có dịch vụ trạng thái/permission online đủ tin cậy?"}
    C -->|Có| D["Opaque + introspection đủ mới hoặc JWT + kiểm tra trạng thái động"]
    C -->|Không| E["Thiết kế lại SLO, hạ tầng trạng thái hoặc giới hạn thao tác khi không kiểm được"]
    B -->|Không, chấp nhận TTL rõ ràng| F{"Cần xác minh ngoại tuyến/độ trễ rất thấp?"}
    F -->|Có| G["JWT ký số ngắn hạn, kiểm issuer/audience/scope, kiểm quyền theo tài nguyên"]
    F -->|Không| H["So sánh JWT và opaque theo hiệu năng, vận hành, riêng tư và quy mô"]
    D --> I["Bổ sung bảo vệ lưu trữ, thu hồi, chống token bị sao chép theo rủi ro"]
    G --> I
    H --> I
    E --> I
~~~

Sơ đồ là **gợi ý lựa chọn kiến trúc**, không phải quy tắc bắt buộc của chuẩn. Với endpoint chỉ đọc dữ liệu rủi ro thấp, chấp nhận một độ trễ thu hồi xác định có thể là lựa chọn hợp lý; với endpoint chuyển tiền hoặc khóa tài khoản, nên ưu tiên xác minh trạng thái và kiểm soát giao dịch hiện hành.

## 8. Bearer hay token ràng buộc với bên gửi?

Lựa chọn JWT/opaque **không giải quyết riêng vấn đề token bị sao chép**. Phần lớn access token OAuth được sử dụng theo cơ chế bearer: ai giữ giá trị token có thể thử dùng nó nếu chưa có ràng buộc bổ sung.

Các biện pháp cần xét cùng nhau:

| Biện pháp | Giảm rủi ro gì? | Giới hạn |
| --- | --- | --- |
| TLS, không gửi token trong URL, che log | Giảm rò rỉ trên đường truyền và trong hạ tầng quan sát. | Không ngăn token bị lấy từ client/thiết bị đã bị xâm nhập. |
| Access token thời hạn ngắn | Thu hẹp cửa sổ lạm dụng của một bản sao. | Không dừng sử dụng trước hạn nếu thiếu cơ chế thu hồi. |
| Scope và audience hẹp | Giảm phạm vi API và thao tác mà token bị lộ có thể truy cập. | Không ngăn giả mạo người giữ token trong phạm vi được cấp. |
| **DPoP** | Ràng buộc token với khóa của client và proof ở request. | Cần kiểm proof, chống phát lại và bảo vệ khóa; thiết bị bị xâm nhập vẫn nguy hiểm. |
| **mTLS-bound token** | Ràng buộc token với chứng chỉ/khóa client. | Phù hợp tùy môi trường; quản lý chứng chỉ và kênh TLS có chi phí. |
| Introspection/danh sách thu hồi | Cho phép phản ứng trước hạn. | Phụ thuộc trạng thái, cache và khả năng lan truyền. |
| Cơ chế idempotency/nonce cho giao dịch | Ngăn thao tác nghiệp vụ bị thực hiện trùng. | Khác với chống phát lại proof/token; cần thiết kế riêng ở ứng dụng. |

Với **DPoP** (RFC 9449), Resource Server cần xác minh proof theo phương thức và URI yêu cầu, thời gian, jti/nonce theo chính sách, khóa công khai và ràng buộc access token. Chỉ nhìn thấy header DPoP là chưa đủ. Với **mTLS** (RFC 8705), Resource Server phải kiểm tra ràng buộc chứng chỉ với token theo đúng profile.

Nếu client không thể bảo vệ khóa, sender-constraining vẫn giúp giảm một số kiểu tấn công nhưng **không biến thiết bị bị chiếm quyền thành đáng tin**.

**Điểm lựa chọn:** Với client thứ ba, thiết bị phân tán hoặc quyền nhạy cảm, cần đánh giá lợi ích của DPoP/mTLS so với khả năng triển khai; không nên gọi bearer token “an toàn” chỉ vì nó là JWT có chữ ký hợp lệ.

## 9. Access, refresh và ID token: chọn đúng mục đích trước

### Access token để gọi API

Resource Server chỉ chấp nhận loại access token và profile mà nó được cấu hình hỗ trợ. Các điều kiện tối thiểu thường gồm:

- Nguồn phát hành đáng tin, xác minh chữ ký hoặc introspection theo định dạng.
- Token chưa hết hạn, đúng thời điểm bắt đầu có hiệu lực, không bị thu hồi nếu hệ thống yêu cầu kiểm tra.
- Audience khớp **chính Resource Server**; tránh dùng token cấp cho dịch vụ khác.
- Scope được cấp đáp ứng endpoint, với cách so khớp giá trị chính xác.
- Phân quyền hiện hành đối với chủ thể và tài nguyên cụ thể, kể cả tenant, quyền sở hữu và trạng thái giao dịch.
- Nếu token sender-constrained: kiểm tra proof/khóa tương ứng.

### Refresh token để xin access token mới

Client gửi refresh token cho **Authorization Server**, không gửi đến API nghiệp vụ. Việc phát hành refresh token phụ thuộc loại client, grant và chính sách phiên. Với public client, nên tuân thủ yêu cầu bảo vệ refresh token theo OAuth 2.0 Security Best Current Practice (RFC 9700), thường sử dụng **refresh token rotation hoặc sender-constraining**.

Refresh token có thể sống lâu hơn access token nên đòi hỏi nơi lưu trữ an toàn, thời hạn, ràng buộc client, khả năng thu hồi và kiểm soát tái sử dụng. Khi refresh token rotation được áp dụng, lần đổi hợp lệ có thể trả refresh token mới và vô hiệu token cũ; dùng lại token cũ bất thường là tín hiệu có thể đã bị sao chép.

### ID token để client xử lý thông tin xác thực OIDC

ID token trong OIDC được cấp **cho relying party/client** để cung cấp thông tin về sự kiện xác thực. Nó không phải access token cho API và không nên được Resource Server chấp nhận chỉ vì chứa **sub**, **email** hay **roles**.

Nếu giao dịch cần xác thực gần đây, client/ứng dụng có thể áp dụng các cơ chế xác thực lại theo OIDC và policy, ví dụ yêu cầu **max_age** hoặc xem xét **auth_time** nếu phù hợp. Một access token vừa được refresh không chứng minh người dùng vừa thực hiện MFA.

## 10. Lưu trữ theo môi trường và ranh giới tin cậy

| Client / môi trường | Hướng tiếp cận thường thích hợp | Điều cần tránh |
| --- | --- | --- |
| **Backend confidential client** | Lưu refresh token/secret phía server trong kho bí mật hoặc vùng dữ liệu hạn quyền; xác thực client tại AS. | Đưa token vào log, backup không bảo vệ, secret trong mã nguồn. |
| **Web có Backend-for-Frontend (BFF)** | Giữ token nhạy cảm phía backend; trình duyệt giữ phiên bằng cookie an toàn. | Nhầm cookie HttpOnly là đã miễn nhiễm CSRF/XSS; bỏ qua Secure, SameSite, CSRF. |
| **SPA thuần trình duyệt** | Giảm thời gian sống và quyền; đánh giá có cần refresh token không, áp rotation/sender constraint nếu được cấp. | Coi localStorage là kho bí mật chống XSS; lưu refresh token dài hạn không kiểm soát. |
| **Ứng dụng mobile** | Dùng Keychain/Keystore hoặc kho an toàn tương đương, ràng buộc token/khóa khi phù hợp. | Ghi token trong crash log, clipboard, backup dễ trích xuất. |
| **Service-to-service** | Client credentials với access token audience/scope hẹp, mTLS khi phù hợp; thường không cần refresh token của phiên người dùng. | Dùng một token quyền rộng cho tất cả microservice. |
| **Thiết bị edge/IoT** | Cân nhắc JWT ký số để xác minh cục bộ khi offline; hạn ngắn và quản lý khóa/thiết bị. | Nghĩ rằng xác minh offline cho biết trạng thái thu hồi mới nhất. |

Bất kể lựa chọn nào, không đưa token vào URL hoặc log; dùng TLS, quản lý phiên, xoay vòng/thu hồi khi thích hợp và giám sát sử dụng bất thường.

Nếu một ứng dụng hoạt động offline, **khả năng hiển thị dữ liệu cục bộ** và **quyền gọi API trên server** là hai vấn đề khác nhau: việc client tự giải mã JWT offline không thể thay thế kiểm tra token tại Resource Server khi đồng bộ hoặc gửi thao tác lên server.

## 11. Ví dụ cấu hình theo kịch bản

Các lựa chọn dưới đây là **phương án minh họa có điều kiện**, không phải tiêu chuẩn bắt buộc cho mọi tổ chức.

| Kịch bản | Đặc điểm rủi ro / vận hành | Phương án có thể cân nhắc | Yêu cầu kiểm tra không được bỏ |
| --- | --- | --- | --- |
| **API đọc dữ liệu nghiệp vụ nội bộ** | Tải cao, quyền khá ổn định; chấp nhận độ trễ thu hồi theo TTL ngắn. | JWT access token ký số, hạn ngắn. | Chữ ký, issuer, aud, exp/nbf, scope, tenant và policy cho bản ghi. |
| **API duyệt hoàn tiền** | Thiệt hại cao, quyền thay đổi cần có hiệu lực nhanh. | Opaque + introspection đủ mới, hoặc JWT + kiểm tra trạng thái/policy online; có thể thêm step-up. | Quyền duyệt hiện hành, trạng thái giao dịch, chống xử lý trùng, thu hồi và audit. |
| **Nhiều microservice nội bộ** | Tải lớn, các ranh giới dịch vụ rõ, có client máy–máy. | Access token JWT hoặc opaque theo SLA; audience hẹp, mTLS nếu phù hợp. | Không nhận token sai audience, không chuyển tiếp tùy tiện token đặc quyền giữa service. |
| **Ứng dụng mobile của người dùng** | Token có nguy cơ bị lấy từ thiết bị, cần duy trì phiên. | AT ngắn hạn; refresh token được bảo vệ, rotation/sender constraint; định dạng AT do AS–API thống nhất. | Lưu an toàn, quản lý phiên/thu hồi, kiểm tra scope/aud, phát hiện reuse. |
| **Ứng dụng SaaS nhiều tenant** | Nguy cơ truy cập chéo tổ chức, role có phạm vi tenant. | JWT hoặc opaque đều có thể; quyết định quan trọng là quyền theo tenant tại API. | Tenant của tài nguyên lấy từ nguồn server tin cậy; không suy role toàn cục từ claim thiếu ngữ cảnh. |
| **Gateway/edge cần xác minh hạn chế kết nối AS** | Offline validation được ưu tiên; trạng thái thu hồi có thể đến trễ. | JWT ký số với khóa đã tin cậy, hạn phù hợp và quy trình đổi khóa. | Issuer, aud, thời gian, scope và chính sách giới hạn hoạt động khi thiếu trạng thái mới. |

Đôi khi câu trả lời phù hợp là **không cần token người dùng**: endpoint hoàn toàn công khai có thể không yêu cầu access token. Ngược lại, một yêu cầu có tác động lớn có thể cần thêm bước phê duyệt, xác thực lại và kiểm soát giao dịch dù token đã được xác minh hoàn chỉnh.

## 12. Ví dụ cụ thể: công ty vận hành ba API

Giả sử một công ty có:

- **Catalog API** đọc dữ liệu sản phẩm công khai.
- **Orders API** đọc/cập nhật đơn hàng theo tenant.
- **Payments API** tạo hoàn tiền, cần xác minh quyền duyệt hiện hành và chống xử lý hai lần.

Ứng dụng nhân viên sử dụng Authorization Code + PKCE. Authorization Server cấp access token riêng theo audience, hoặc thực hiện cơ chế cấp token phù hợp với hợp đồng cho từng API.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant O as Orders API
    participant P as Payments API
    participant POL as Nguồn quyền hiện hành

    C->>AS: Xin token đúng audience/scope
    AS-->>C: Access token dành cho orders-api
    C->>O: GET /orders/123 với token Orders
    O->>O: Kiểm token và scope
    O->>POL: Kiểm tenant và quyền đọc
    POL-->>O: Cho phép / từ chối
    O-->>C: Kết quả

    C->>P: POST /refunds với token Orders
    P-->>C: Từ chối vì sai audience

    C->>AS: Xin token dành cho payments-api theo quyền được cấp
    AS-->>C: Access token dành cho Payments (nếu được cấp)
    C->>P: POST /refunds với token Payments
    P->>P: Xác minh token và trạng thái cần thiết
    P->>POL: Kiểm quyền duyệt, tenant, giao dịch
    POL-->>P: Kết quả policy hiện hành
    P-->>C: Kết quả hoặc từ chối
~~~

Trong thiết kế này:

- Catalog API công khai có thể không cần bearer token.
- Orders API có thể dùng JWT access token ngắn hạn để giảm chi phí xác minh; vẫn phải kiểm quyền theo tenant và đơn hàng.
- Payments API có thể ưu tiên introspection hoặc kiểm tra phiên/quyền online và một cơ chế chống lặp giao dịch. **Opaque token không thay thế policy check**.
- Client không được gửi ID token thay access token cho bất kỳ API nào.
- Refresh token chỉ gửi về AS để xin AT mới khi còn được phép. Nếu bị thu hồi, client không được tự “gia hạn” bằng cách sửa exp trong JWT.

## 13. Một thuật toán quyết định có thể đưa vào thiết kế

Để nhóm kỹ thuật thống nhất lựa chọn, viết một bản ghi kiến trúc ngắn với các bước:

1. **Định nghĩa principal và mục đích.** Token đại diện người dùng, service hay client? Hành động là đọc, ghi, duyệt hay chỉ thiết lập phiên? Bên nhận chính xác là ai?
2. **Chọn đúng token chức năng.** Resource Server cần access token; token endpoint xử lý refresh token; client OIDC xử lý ID token.
3. **Định nghĩa phạm vi quyền.** Mỗi API có audience, scope, quyền theo tài nguyên và tenant ra sao? Có cần sender-constraining?
4. **Đặt yêu cầu thu hồi đo được.** Sau khóa tài khoản/thu hồi quyền, token hoặc thao tác cũ được chấp nhận tối đa bao lâu? Ai chịu trách nhiệm bảo đảm độ trễ?
5. **Chọn hình thức xác minh.** JWT offline nếu đáp ứng yêu cầu thu hồi, riêng tư và độ trễ; opaque/introspection hoặc kết hợp trạng thái nếu cần tính mới.
6. **Thiết kế vòng đời.** Hạn access token, điều kiện cấp refresh token, expiration/inactivity timeout, rotation, revocation, quản lý phiên và khóa.
7. **Xác định hành vi khi lỗi.** JWKS không tải được, introspection timeout, policy store lỗi, cache quá hạn thì cho phép hay từ chối theo từng mức rủi ro?
8. **Định nghĩa giám sát/kiểm thử.** Kiểm token sai audience, scope, issuer, loại token, hết hạn, vai trò cũ, phát lại, đồng thời refresh, khóa tài khoản và thu hồi.

Có thể biểu diễn điều kiện API dưới dạng mã giả sau. Đây là **sơ đồ kiểm tra**, không phải đoạn mã triển khai thư viện bảo mật:

~~~text
function authorize(request, resource):
    access = extractAccessToken(request)

    tokenContext = validateByConfiguredProfile(
        access,
        trustedIssuer = service.issuer,
        expectedAudience = service.audience,
        expectedTokenUse = "access",
        allowedAlgorithmsOrIntrospection = service.validationProfile
    )
    if tokenContext.invalid:
        return DENY_401

    if senderConstraintRequired:
        require validateSenderProof(request, tokenContext)

    require tokenContext.isWithinValidityWindow
    require exactScopeMatch(tokenContext.scopes, requiredScope(resource.action))

    if requiresFreshStatus(resource.action):
        require checkCurrentTokenOrSessionState(tokenContext)

    require accountAndTenantAreActive(tokenContext.subject, resource.tenant)
    require currentPolicyAllows(
        subject = tokenContext.subject,
        client = tokenContext.client,
        action = resource.action,
        resource = resource
    )

    return ALLOW
~~~

Ở đây, **validateByConfiguredProfile** chỉ chấp nhận profile phù hợp do server đã cấu hình. Không suy định dạng hay thuật toán đáng tin từ nội dung người gửi tự khai. Nếu truy vấn trạng thái/policy bắt buộc không thể hoàn thành, thao tác nhạy cảm nên từ chối theo chính sách đã định.

## 14. Kiểm soát lỗi và thử nghiệm quyết định lựa chọn

Chọn token xong cần chứng minh mô hình hoạt động khi các giả định ban đầu thay đổi.

| Phép thử | Kỳ vọng |
| --- | --- |
| Gửi token có chữ ký đúng nhưng **aud=api-khac**. | API từ chối vì token không dành cho mình. |
| Dùng ID token làm Bearer cho Resource Server. | Từ chối do sai loại/mục đích token. |
| JWT chưa hết hạn, tài khoản vừa bị khóa. | Theo đúng SLA thu hồi và lớp policy đã thiết kế; không tự nhận chữ ký là quyền còn hiệu lực. |
| Opaque token bị thu hồi nhưng introspection cache còn active. | Đo thực tế thời gian nhận biết; chỉnh TTL/cơ chế vô hiệu cache để đáp ứng yêu cầu. |
| Issuer quay vòng khóa JWT. | Chấp nhận token hợp lệ đúng khóa theo giai đoạn chuyển tiếp; từ chối token không còn hợp lệ. |
| Token bearer bị sao chép từ log. | Giám sát/lộ lọt và biện pháp thu hồi có thể thực thi; tránh log token từ đầu. |
| DPoP-bound token bị gửi không có proof hoặc proof sai. | Từ chối và kiểm tra ràng buộc khóa/phương thức/URI. |
| Hai request dùng cùng refresh token khi rotation. | Client đồng bộ một lần refresh; AS phát hiện/reject reuse theo policy. |
| API thiếu kết nối tới AS/policy store. | Hành vi rõ ràng theo mức rủi ro, không âm thầm mở quyền. |
| Client chỉ có scope đọc nhưng người dùng có role quản lý. | API từ chối thao tác ghi dù role có vẻ đủ. |
| Người dùng có role tenant A yêu cầu dữ liệu tenant B. | API từ chối nếu không có quyền chính xác tại tenant B. |

Các thử nghiệm nên đo **độ trễ thực tế** của thu hồi, ngoài kiểm tra pass/fail. Một phương án được gọi là “token sống ngắn” nhưng TTL và đồng hồ lệch lớn vẫn có thể không đáp ứng yêu cầu vận hành.

## 15. Những ngộ nhận làm sai lựa chọn

**“JWT luôn an toàn hơn opaque vì được ký.”** Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành khi xác minh đúng; opaque có thể được xác minh qua AS đáng tin và thuận lợi cho quản lý trạng thái. Hai mô hình có rủi ro khác nhau.

**“Opaque luôn thu hồi tức thì.”** Introspection chỉ phản ánh dữ liệu mà AS và hệ thống cache đang có. Độ trễ đồng bộ, cache và lỗi mạng quyết định thời điểm Resource Server thực sự biết thu hồi.

**“JWT không thể thu hồi.”** JWT tự xác minh ngoại tuyến không có chức năng hỏi thu hồi sẵn có, nhưng hệ thống có thể bổ sung denylist, trạng thái phiên/policy, hoặc dùng TTL ngắn; mỗi cách có chi phí riêng.

**“Bearer token có exp ngắn thì không cần chống rò rỉ.”** Trong thời hạn còn hiệu lực, một bản sao vẫn có thể bị sử dụng. Phải bảo vệ lưu trữ, truyền tải, log và đánh giá ràng buộc bên gửi.

**“Mọi API trong cùng công ty có thể dùng chung một token.”** Token cần đúng audience và scope; dùng chung token quyền rộng làm tăng phạm vi thiệt hại khi một thành phần bị xâm nhập.

**“Refresh token giải quyết quyền đã bị rút.”** Refresh token chỉ cho phép yêu cầu cấp token mới khi AS chấp nhận; access token đang lưu hành vẫn cần quy tắc thu hồi và phân quyền riêng.

**“JWT chứa roles tức là quyết định authorization đã xong.”** Role/permission trong claim có thể cũ, sai tenant hoặc thiếu điều kiện nghiệp vụ. Resource Server cần kiểm tra quyền trên tài nguyên khi chính sách yêu cầu.

## 16. Bài tập tự đánh giá

Hãy lựa chọn một phương án ban đầu và nêu **điều kiện** để phương án đó phù hợp.

**Tình huống A.** Hệ thống chỉ đọc báo cáo thống kê nội bộ, có hàng nghìn request/giây, ít thay đổi quyền; tổ chức chấp nhận một khoảng trễ thu hồi đã biết. API cần chạy ổn khi AS gián đoạn ngắn.

**Gợi ý:** JWT access token ký số, audience hẹp, hạn ngắn theo SLA là lựa chọn hợp lý để đánh giá. Vẫn kiểm scope và permission/tài nguyên cần thiết; không đưa dữ liệu nhạy cảm vào claims.

**Tình huống B.** API hoàn tiền có yêu cầu khóa quyền nhân viên nhanh, cần xác minh quyền phê duyệt theo từng giao dịch và không cho phép thao tác trùng.

**Gợi ý:** Chọn opaque + introspection với trạng thái đủ mới hoặc JWT + kiểm tra trạng thái/policy online; thêm xác thực lại nếu chính sách yêu cầu và idempotency theo giao dịch. Không có định dạng token nào tự giải quyết toàn bộ yêu cầu.

**Tình huống C.** Ứng dụng mobile phải duy trì phiên nhiều ngày, người dùng có thể mất thiết bị, quyền API được cấp giới hạn cho từng khách hàng.

**Gợi ý:** Access token ngắn hạn, refresh token được bảo vệ bằng lưu trữ an toàn và rotation/sender-constraining theo cấu hình, revocation cho thiết bị/phiên, scope/audience hẹp và quyền theo khách hàng hiện hành. Định dạng access token còn tùy yêu cầu API và AS.

**Tình huống D.** Gateway xác minh token ở khu vực xa, đường truyền tới AS không ổn định; đồng thời tổ chức yêu cầu khóa tài khoản có hiệu lực trong vài giây.

**Gợi ý:** Có xung đột yêu cầu. JWT ngoại tuyến đơn thuần khó bảo đảm thu hồi vài giây nếu TTL dài; cần kênh đồng bộ trạng thái hoặc nguồn policy cục bộ có bảo đảm lan truyền, hay giới hạn chức năng trong lúc mất liên lạc. Phải làm rõ cam kết SLA trước khi chọn token.

## Kết luận

Lựa chọn token bắt đầu từ **rủi ro của thao tác và yêu cầu kiểm tra**, rồi mới đến định dạng. **Access token** cho Resource Server, **refresh token** cho Authorization Server và **ID token** cho client OIDC có những chức năng khác nhau. Với access token, **JWT** phù hợp khi cần xác minh tại chỗ và có thể quản lý giới hạn độ trễ trạng thái; **opaque token với introspection** phù hợp khi cần kiểm soát trạng thái tập trung và hạ tầng hỗ trợ tra cứu tin cậy. Cả hai đều có thể cần policy check ở thời điểm truy cập.

Quyết định tốt cần mô tả rõ **issuer, audience, scope, claims, thời hạn, thu hồi, ràng buộc bên gửi, lưu trữ và hành vi khi phụ thuộc bị lỗi**. Đặc biệt, phải đo được khoảng thời gian hệ thống còn chấp nhận quyền cũ sau khi token bị thu hồi hoặc tài khoản đổi trạng thái. Chính ranh giới tin cậy và những giới hạn thực tế đó quyết định tính phù hợp của token.

### Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
