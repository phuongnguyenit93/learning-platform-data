# Kiểm tra jti, trạng thái thu hồi hoặc ràng buộc bổ sung khi có

## 1. Vì sao xác minh chữ ký và thời gian vẫn có thể chưa đủ?

Một JWT có chữ ký hợp lệ, issuer đúng, audience đúng và chưa hết hạn vẫn có thể không còn được phép sử dụng. Ví dụ:

- Người dùng đã đăng xuất hoặc phiên đã bị quản trị viên vô hiệu hóa.
- Tài khoản hoặc client đã bị khóa sau khi token được phát hành.
- Token bị lộ và cần thu hồi trước exp.
- JWT assertion hoặc proof chỉ được phép sử dụng một lần nhưng đã được gửi trước đó.
- Token chỉ hợp lệ khi được trình bày cùng một client certificate hoặc proof-of-possession tương ứng.
- Ngữ cảnh tenant, client, phiên hoặc mức xác thực đã thay đổi kể từ lúc token được cấp.

Vì vậy, ngoài xác minh mật mã và claims cơ bản, một số hệ thống cần kiểm tra **JWT ID (jti)**, trạng thái thu hồi (revocation status), trạng thái phiên hoặc các ràng buộc bổ sung (token binding/context binding).

Ba khái niệm phải được phân biệt:

1. **Token hợp lệ về mật mã:** chữ ký/MAC hoặc bảo vệ mã hóa đã được xác minh bằng khóa tin cậy.
2. **Token còn được phép sử dụng:** token chưa hết hạn, chưa bị thu hồi và vẫn đáp ứng các ràng buộc trạng thái hiện hành.
3. **Request được phép:** người trình bày token đáp ứng quyền đối với hành động và tài nguyên cụ thể.

Một jti duy nhất không tự ngăn replay; một denylist không thay thế xác minh chữ ký; token binding không tự cấp quyền. Các kiểm tra này bổ sung cho nhau và chỉ nên bật khi policy/token profile yêu cầu.

Nội dung thuộc module Security - JSON Web Token (JWT), áp dụng chung cho mọi ngôn ngữ và nền tảng, không phụ thuộc Java hoặc Spring Security.

## 2. jti là gì?

Claim **jti (JWT ID)** là định danh của một JWT. Theo RFC 7519, giá trị jti được gán theo cách bảo đảm xác suất trùng lặp ngẫu nhiên là không đáng kể. Khi nhiều issuer phát hành JWT, việc tránh va chạm giữa các issuer cần được xử lý trong phạm vi hệ thống sử dụng.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://api.example.org/invoices",
  "jti": "7c8f2d6a-2b9e-4d83-9f7b-0b5c2a4d1e60",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

jti định danh token, không phải định danh người dùng, phiên đăng nhập hoặc request. Hai token được phát hành cho cùng một subject vẫn nên có jti khác nhau nếu chúng là hai token riêng biệt.

### 2.1. jti không phải bí mật và không phải bằng chứng xác thực

Giá trị jti thường được thiết kế khó đoán và duy nhất, nhưng bản thân nó không phải khóa mật mã. Kẻ tấn công có thể tự tạo một chuỗi jti trong JWT giả. Chỉ sau khi chữ ký hoặc bảo vệ mật mã thành công, bên nhận mới được dùng jti như một định danh đã được issuer xác nhận.

Không dùng jti làm:

- Bằng chứng rằng token do issuer tin cậy phát hành.
- Mật khẩu hoặc secret để truy cập API.
- Định danh người dùng toàn cục.
- Bằng chứng rằng token chưa từng được sử dụng.
- Giá trị có thể ghi vào denylist chỉ vì nó xuất hiện trong một token chưa xác minh.

### 2.2. Phạm vi duy nhất của jti

Một jti cần được hiểu trong phạm vi issuer và loại token. Khi lưu trạng thái, không nên chỉ dùng jti làm khóa toàn cục nếu nhiều issuer có thể tự chọn cùng một chuỗi.

Khóa logic có thể gồm:

~~~text
issuer + token_profile + jti
~~~

Ví dụ:

| Issuer | Profile | jti | Định danh trạng thái |
| --- | --- | --- | --- |
| identity-A | access-token | token-001 | A/access/token-001 |
| identity-B | access-token | token-001 | B/access/token-001 |
| identity-A | one-time-assertion | token-001 | A/assertion/token-001 |

Các trường hợp trên phải được xem là khác nhau nếu policy định nghĩa phạm vi như vậy. Có thể dùng hash của bộ giá trị đã chuẩn hóa làm storage key; cần tránh nối chuỗi mơ hồ bằng dấu phân cách không được escape.

### 2.3. jti có bắt buộc không?

RFC 7519 không yêu cầu mọi JWT phải có jti. Token profile hoặc ứng dụng quyết định có bắt buộc hay không. Ví dụ, một luồng assertion dùng một lần hoặc một cơ chế chống replay có thể yêu cầu jti; một access token ngắn hạn không dùng trạng thái có thể không cần tra jti.

Nếu policy yêu cầu jti:

- Claim phải hiện diện sau khi xác minh mật mã.
- Giá trị phải đúng kiểu và nằm trong giới hạn độ dài.
- Issuer phải tạo jti với xác suất trùng lặp không đáng kể.
- Bên nhận phải xác định rõ jti được dùng để định danh, thu hồi hay chống replay.

Không tự giả định rằng chỉ cần có claim jti là token đã được bảo vệ khỏi replay.

## 3. Phân biệt replay và revocation

Replay và revocation có liên quan nhưng giải quyết hai vấn đề khác nhau.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Replay detection/prevention** | Một token hoặc proof có đang bị trình bày lại trái với chính sách sử dụng không? | Assertion chỉ được dùng một lần nhưng bị gửi lần thứ hai |
| **Revocation** | Token vốn được phát hành hợp lệ có còn được phép sử dụng không? | Người dùng đăng xuất, tài khoản bị khóa hoặc token bị lộ |
| **Expiration** | Token còn nằm trong cửa sổ thời gian được phép không? | exp đã qua |
| **Authorization** | Token hợp lệ và còn hoạt động có đủ quyền cho hành động này không? | Có scope đọc nhưng yêu cầu xóa tài nguyên |

Một access token bearer thông thường có thể được dùng nhiều lần trong thời hạn hiệu lực. Chỉ vì jti đã xuất hiện trong một request không có nghĩa phải từ chối mọi request tiếp theo. Ngược lại, một assertion một lần hoặc DPoP proof thường cần cơ chế phát hiện việc sử dụng lại theo đúng profile.

Do đó, policy phải nói rõ:

- Token được phép dùng nhiều lần hay chỉ một lần?
- Trạng thái được lưu ở phạm vi issuer, client, user, session hay resource server?
- Thời gian lưu trạng thái là bao lâu?
- Request đồng thời có được phép cùng tiêu thụ một token một lần không?
- Khi kho trạng thái không sẵn sàng, hệ thống phải từ chối hay có ngoại lệ đã được phê duyệt?

## 4. jti và cơ chế chống replay

### 4.1. Vì sao chỉ kiểm tra jti là chưa đủ?

Giả sử một JWT assertion có jti là assertion-789. Nếu bên nhận chỉ kiểm tra claim có tồn tại mà không lưu trạng thái đã sử dụng, cùng assertion đó có thể được gửi lại nhiều lần.

Muốn phát hiện replay, bên nhận cần một kho trạng thái hoặc cơ chế nonce có tính duy nhất. Sau khi xác minh chữ ký, hệ thống kiểm tra jti đã được tiêu thụ chưa và ghi nhận lần sử dụng theo cách nguyên tử.

~~~mermaid
flowchart TD
    A["Nhận assertion/JWT proof"] --> B["Xác minh chữ ký và claims"]
    B --> C{"jti bắt buộc và hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Tạo khóa trạng thái issuer + profile + jti"]
    D --> E["Thực hiện atomic insert-if-absent"]
    E --> F{"Đã tồn tại?"}
    F -- "Có" --> Y["Từ chối: replay"]
    F -- "Không" --> G["Chấp nhận lần sử dụng đầu nếu các policy khác đạt"]
~~~

Thao tác insert-if-absent phải nguyên tử. Nếu triển khai theo hai bước “đọc xem có chưa” rồi “ghi lại”, hai request đồng thời có thể cùng thấy jti chưa tồn tại và cùng được chấp nhận.

### 4.2. Chống replay cho token dùng một lần

Với token dùng một lần:

1. Xác minh chữ ký hoặc authenticated decryption.
2. Xác minh issuer, audience, exp/nbf/iat và profile.
3. Kiểm tra jti có mặt và hợp lệ.
4. Tạo storage key gắn với issuer và profile.
5. Thực hiện thao tác consume nguyên tử; chỉ một request có thể thành công.
6. Nếu jti đã tồn tại, từ chối lần trình bày tiếp theo.

Nếu thao tác nghiệp vụ cần thực hiện sau khi consume, cần xác định cách xử lý khi tiến trình bị lỗi giữa lúc đánh dấu đã dùng và lúc hoàn tất nghiệp vụ. Có thể cần transaction, idempotency key hoặc trạng thái giao dịch để tránh token bị tiêu thụ nhưng hành động chưa được thực hiện. Không tự động cho phép dùng lại token sau lỗi vì có thể mở cửa replay.

### 4.3. Thời hạn lưu jti đã dùng

Một bản ghi replay cần tồn tại ít nhất trong khoảng token/proof còn có thể được chấp nhận. Với token có exp và leeway L, TTL thường không nên kết thúc trước exp + L, cộng thêm biên an toàn nếu hệ thống cần.

Nếu token không có exp nhưng policy yêu cầu chống replay, phải có một giới hạn thời gian hữu hạn khác. Không thể xóa trạng thái quá sớm nếu token vẫn có thể được chấp nhận.

## 5. Revocation: thu hồi token trước khi hết hạn

JWT thường được thiết kế để xác minh cục bộ bằng chữ ký, không cần hỏi issuer mỗi request. Đây là ưu điểm về độ trễ và khả năng mở rộng, nhưng tạo ra một đánh đổi: nếu không có trạng thái bổ sung, resource server có thể tiếp tục chấp nhận token đã phát hành cho tới khi exp hết hiệu lực.

**Revocation** bổ sung trạng thái để nói rằng một token hoặc một phạm vi credential không còn được chấp nhận, dù chữ ký vẫn hợp lệ và exp chưa tới.

Các tình huống thường cần thu hồi:

- Người dùng đăng xuất hoặc quản trị viên kết thúc phiên.
- Tài khoản bị khóa, bị xóa hoặc bị nghi ngờ xâm phạm.
- Client bị vô hiệu hóa hoặc mất quyền sử dụng.
- Refresh token hoặc token family bị phát hiện sử dụng bất thường.
- JWT bị lộ hoặc bị gửi nhầm.
- Khóa ký bị xâm phạm.
- Quyền truy cập hoặc tenant binding thay đổi cần có hiệu lực ngay.

Không phải mọi hệ thống đều cần tra trạng thái thu hồi cho mọi access token. Cần xác định yêu cầu thu hồi tức thời, mức rủi ro và độ trễ chấp nhận được.

## 6. Các chiến lược thu hồi JWT

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Access token ngắn hạn | Giảm thời gian token bị lộ có thể được dùng | Không thu hồi tức thời; token còn hạn vẫn hoạt động |
| Denylist theo jti | Lưu token đã bị thu hồi; kiểm tra mỗi request | Có trạng thái và truy vấn; cần đồng bộ phân tán |
| Token introspection | Hỏi authorization server trạng thái active của token | Phụ thuộc mạng/authorization server; tăng độ trễ |
| Session hoặc token version | So sánh claim phiên/phiên bản với trạng thái hiện tại | Cần truy cập trạng thái hoặc cache |
| Vô hiệu hóa signing key | Ngừng tin cậy một khóa hoặc issuer | Ảnh hưởng tất cả token được ký bằng khóa đó |
| Refresh token rotation/revocation | Thu hồi refresh token hoặc cả token family | Chủ yếu ngăn cấp token mới; access token đã phát hành có thể còn hiệu lực tới exp nếu không có kiểm tra khác |

Các chiến lược có thể kết hợp. Ví dụ, access token ngắn hạn cùng denylist jti cho sự kiện thu hồi khẩn cấp; introspection cho tài nguyên nhạy cảm; key revocation khi khóa ký bị lộ.

## 7. Denylist theo jti

Denylist là kho trạng thái chứa định danh của các token đã bị thu hồi. Khi nhận JWT, resource server xác minh mật mã và claims trước, sau đó kiểm tra định danh đã xác minh có trong denylist không.

### 7.1. Chỉ ghi nhận jti sau khi xác minh token

Không cho phép một request mang JWT giả tạo tùy ý bản ghi thu hồi bằng cách gửi jti do kẻ tấn công tự chọn. Luồng thu hồi cần:

1. Xác minh token và issuer.
2. Kiểm tra token profile và jti.
3. Xác định actor có quyền thu hồi token/phiên đó hay không.
4. Ghi bản ghi thu hồi vào kho trạng thái tin cậy.

Đối với API xác nhận thu hồi, cần xác thực client/actor và kiểm tra quyền sở hữu hoặc quyền quản trị. Không cung cấp endpoint cho phép bất kỳ ai gửi jti bất kỳ vào denylist.

### 7.2. Khóa lưu trữ

Không nên dùng riêng jti làm khóa toàn cục. Có thể tạo khóa logic:

~~~text
revocation_key = hash(issuer || token_profile || jti)
~~~

Việc nối chuỗi cần có encoding không mơ hồ (ví dụ length-prefix hoặc cấu trúc serialization chuẩn), không ghép các giá trị tùy tiện bằng dấu phân cách có thể xuất hiện trong dữ liệu. Hash giúp giới hạn độ dài khóa lưu trữ và tránh để lộ trực tiếp định danh trong một số hệ thống; nó không thay thế kiểm soát truy cập hoặc bảo vệ kho dữ liệu.

Một số hệ thống dùng fingerprint của toàn token đã chuẩn hóa để thu hồi chính xác một chuỗi token, đặc biệt khi issuer không cung cấp jti. Cần lưu ý rằng fingerprint chỉ nhận diện đúng token bytes; cùng một claims được ký lại sẽ có fingerprint khác. Nếu profile có jti, dùng jti gắn với issuer thường phù hợp hơn để biểu diễn danh tính token.

### 7.3. TTL của bản ghi thu hồi

Nếu token có exp, bản ghi denylist cần tồn tại tới khi token chắc chắn không còn được chấp nhận:

~~~text
revocation_record_expiry >= token.exp + accepted_clock_skew
~~~

Nếu hệ thống có nhiều profile hoặc nhiều validator với leeway khác nhau, TTL phải dựa trên thời điểm chấp nhận muộn nhất có thể. Xóa bản ghi trước thời điểm đó có thể làm token bị thu hồi quay lại trạng thái được chấp nhận.

Nếu token không có exp hoặc có thời hạn không giới hạn, cần một chính sách lưu trạng thái khác; không đặt TTL tùy ý ngắn rồi coi việc thu hồi vẫn có hiệu lực.

### 7.4. Lưu gì trong denylist?

Chỉ lưu dữ liệu cần thiết:

- Khóa định danh đã tính từ issuer/profile/jti hoặc token fingerprint.
- Thời điểm thu hồi.
- Thời điểm hết hiệu lực của bản ghi.
- Lý do hoặc mã sự kiện đã chuẩn hóa nếu cần audit.
- Actor/hệ thống thực hiện thu hồi theo chính sách kiểm toán.

Không lưu nguyên bearer token, private key, HMAC secret hoặc claims nhạy cảm nếu không có nhu cầu rõ ràng. Bảo vệ kho denylist bằng phân quyền, mã hóa phù hợp, audit và giới hạn truy cập.

## 8. Kiểm tra trạng thái thu hồi trong request

Sau khi xác minh mật mã và claims:

1. Xác định issuer, token profile và jti đã được xác minh.
2. Tạo khóa trạng thái theo namespace đã định nghĩa.
3. Tra cứu denylist hoặc trạng thái phiên.
4. Nếu có bản ghi thu hồi còn hiệu lực, từ chối token.
5. Nếu không có bản ghi và kho trạng thái trả lời đáng tin cậy, tiếp tục bước authorization.
6. Nếu không thể xác định trạng thái vì kho dữ liệu lỗi, áp dụng chính sách failure mode đã được quyết định trước.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Verify chữ ký / authenticated decrypt"]
    B --> C{"Bằng chứng mật mã hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Validate iss, aud, exp, nbf, profile"]
    D --> E{"Claims hợp lệ?"}
    E -- "Không" --> X
    E -- "Có" --> F["Tạo revocation key từ issuer/profile/jti"]
    F --> G["Tra denylist hoặc session state"]
    G --> H{"Đã thu hồi?"}
    H -- "Có" --> X
    H -- "Không" --> I{"Trạng thái được kiểm tra đáng tin cậy?"}
    I -- "Không" --> Y["Từ chối theo fail-closed policy"]
    I -- "Có" --> J["Tạo validated token context"]
    J --> K["Kiểm tra authorization"]
~~~

Không tra cứu hoặc ghi nhận trạng thái thu hồi dựa trên claims chưa xác minh. Có thể parse sơ bộ để kiểm tra cú pháp, nhưng kết quả không được dùng để kết luận token active/revoked hoặc tạo bản ghi trạng thái.

## 9. Token introspection và OAuth revocation

### 9.1. Introspection

OAuth 2.0 Token Introspection (RFC 7662) cho phép resource server hỏi authorization server trạng thái của token. Phản hồi thường có claim **active** để cho biết token có đang hoạt động theo chính sách của authorization server hay không; có thể kèm scope, client, subject, audience và thời hạn.

Introspection hữu ích khi:

- Cần kiểm tra trạng thái token gần thời gian thực.
- Authorization server quản lý phiên/thu hồi tập trung.
- Resource server không muốn tự duy trì denylist phân tán.
- Token có thể là opaque hoặc JWT nhưng hệ thống muốn dùng một cơ chế trạng thái thống nhất.

Resource server phải xác thực với introspection endpoint theo hợp đồng, bảo vệ kênh TLS, kiểm tra nguồn phản hồi và áp dụng đúng audience/scope. Không gửi token tới endpoint introspection không đáng tin cậy.

### 9.2. Cache kết quả introspection

Cache phản hồi active=true có thể giảm tải và độ trễ nhưng tạo ra cửa sổ mà token vừa bị thu hồi vẫn được chấp nhận cho tới khi cache hết hạn. TTL cache phải phản ánh yêu cầu revocation latency.

Đối với tài nguyên nhạy cảm, có thể dùng TTL rất ngắn hoặc không cache trạng thái active. Cache kết quả inactive thường ít rủi ro hơn về quyền truy cập nhưng vẫn cần thời hạn và giới hạn dung lượng.

### 9.3. Token revocation endpoint

OAuth 2.0 Token Revocation (RFC 7009) định nghĩa cơ chế client yêu cầu authorization server thu hồi token. Authorization server có thể quản lý trạng thái token hoặc refresh token liên quan. Việc endpoint trả thành công không có nghĩa mọi resource server đã cập nhật trạng thái tức thời; hệ thống cần xác định cơ chế lan truyền, introspection hoặc cache invalidation.

Revocation endpoint phải xác thực client theo yêu cầu giao thức và không được cho phép người gọi thu hồi token của chủ thể khác ngoài phạm vi quyền.

## 10. Thu hồi theo session, token version và key

### 10.1. Session state

JWT có thể chứa claim định danh phiên như sid theo một profile/hợp đồng cụ thể. Bên nhận có thể tra trạng thái phiên để biết phiên đã bị kết thúc hay chưa.

Một session ID không phải claim bắt buộc chung của mọi JWT. Nếu sử dụng, phải định nghĩa:

- Issuer nào cấp và namespace nào áp dụng.
- Phiên gắn với subject/client nào.
- Khi nào phiên bị thu hồi.
- Thời gian giữ trạng thái và cách cache.
- Cách xử lý token phát hành trước/sau khi phiên thay đổi.

### 10.2. Token version hoặc credential version

Một hệ thống có thể duy trì phiên bản credential của user/client. Token mang claim phiên bản đã được ký; resource server so sánh với phiên bản hiện tại trong trạng thái tin cậy. Khi tài khoản bị khóa hoặc toàn bộ token cần vô hiệu, tăng version có thể làm các token cũ không còn khớp.

Đây là cơ chế riêng của ứng dụng, không phải registered claim tiêu chuẩn. Cần xác định cách version được gắn với subject/issuer, thời điểm cập nhật có hiệu lực, cache invalidation và xử lý đồng thời.

### 10.3. Vô hiệu hóa signing key

Nếu private signing key bị xâm phạm, có thể phải ngừng tin cậy toàn bộ token được ký bằng khóa đó. Hành động này có phạm vi rộng hơn thu hồi một jti:

- Đánh dấu khóa/kid hoặc fingerprint không còn được chấp nhận.
- Cập nhật policy và cache trên tất cả resource server.
- Xử lý token đã ký trước thời điểm phát hiện theo kế hoạch ứng phó.
- Phát hành khóa thay thế và theo dõi việc chuyển đổi.

Không chỉ xóa khóa khỏi JWKS rồi giả định mọi node lập tức ngừng dùng nó; cache cũ có thể vẫn giữ khóa. Cần cơ chế emergency invalidation hoặc deny rule được phân phối tới các validator.

## 11. Ràng buộc token với client hoặc người trình bày

JWT bearer token là credential dạng bearer: ai sở hữu token có thể trình bày nó. Nếu token bị sao chép, kẻ khác có thể dùng token cho tới khi nó hết hạn hoặc bị thu hồi. jti không chứng minh người gửi request là client được cấp token.

Để giảm rủi ro token bị đánh cắp và phát lại, có thể dùng **sender-constrained token** hoặc proof-of-possession. Token khi đó được ràng buộc với một khóa hoặc chứng thư mà client phải chứng minh đang sở hữu.

### 11.1. Confirmation claim (cnf)

Một số profile OAuth dùng claim **cnf (confirmation)** để mang thông tin ràng buộc token với khóa của client. Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "aud": "https://api.example.org/",
  "sub": "client-42",
  "cnf": {
    "jkt": "base64url-thumbprint-of-client-public-key"
  }
}
~~~

cnf không phải claim bắt buộc cho mọi JWT. Cấu trúc bên trong phụ thuộc profile, ví dụ DPoP hoặc mutual-TLS certificate-bound access token. Bên nhận phải xác minh đúng cơ chế tương ứng; chỉ kiểm tra cnf tồn tại là chưa đủ.

### 11.2. DPoP

OAuth 2.0 Demonstrating Proof of Possession (DPoP, RFC 9449) dùng một JWT proof riêng cho request. Proof thường ràng buộc với:

- Phương thức HTTP (htm).
- URI đích (htu).
- Thời điểm phát hành (iat).
- Định danh proof (jti).
- Public key trong header của proof.
- Nonce của server nếu cơ chế nonce được sử dụng.

Với access token được ràng buộc DPoP, token có thể chứa cnf.jkt là thumbprint của public key. Resource server phải xác minh proof bằng khóa tương ứng và kiểm tra thumbprint khớp token, request method/URI đúng, thời gian hợp lệ, access token hash (ath) khi profile yêu cầu và proof chưa bị replay.

Để chống replay proof, resource server thường lưu jti theo phạm vi khóa/issuer và thời gian ngắn, hoặc dùng server nonce theo profile. Chỉ kiểm tra chữ ký DPoP proof mà không kiểm tra htm/htu/iat/jti/ath sẽ không đạt yêu cầu.

### 11.3. Mutual-TLS certificate-bound access token

OAuth mutual-TLS (RFC 8705) có thể ràng buộc access token với chứng thư client. Token chứa confirmation claim tham chiếu fingerprint chứng thư, thường là cnf.x5t#S256.

Resource server phải:

1. Xác minh access token và claims.
2. Lấy chứng thư client từ kết nối TLS đã được xác thực bởi hạ tầng tin cậy.
3. Tính fingerprint theo profile.
4. So khớp fingerprint với cnf trong token.
5. Từ chối nếu request không trình bày đúng chứng thư được ràng buộc.

Không lấy chứng thư từ header HTTP do client tự gửi rồi coi nó là chứng thư TLS đã xác thực. Cần bảo đảm proxy chuyển tiếp danh tính chứng thư theo một kênh tin cậy và ứng dụng chỉ tin proxy được cấu hình.

## 12. Các ràng buộc bổ sung theo ngữ cảnh

Ngoài jti, revocation và token binding, một policy có thể cần kiểm tra claims ràng buộc với ngữ cảnh:

| Ràng buộc | Mục đích | Cách kiểm tra |
| --- | --- | --- |
| client_id / azp | Token được cấp cho client nào | Đối chiếu với client context hoặc profile |
| tenant_id | Token thuộc tenant nào | So khớp tenant đã xác định từ ngữ cảnh tin cậy |
| sid | Token thuộc phiên nào | Kiểm tra trạng thái phiên khi policy yêu cầu |
| auth_time | Thời điểm người dùng thực hiện xác thực | Kiểm tra độ mới của lần xác thực cho thao tác nhạy cảm |
| acr / amr | Mức độ/phương thức xác thực | Kiểm tra mức assurance và phương thức theo policy |
| nonce | Ràng buộc phản hồi với một request/flow đã khởi tạo | So khớp nonce lưu trong trạng thái giao dịch theo profile |
| cnf | Ràng buộc token với khóa/chứng thư | Xác minh proof hoặc certificate binding |
| scope / roles | Phạm vi quyền được cấp | Đưa vào authorization sau khi claims đã xác minh |

Không phải mọi claim trên đều là registered claim của JWT. Một số thuộc OIDC, OAuth profile hoặc hợp đồng ứng dụng. Cần phân biệt rõ nguồn tiêu chuẩn, kiểu dữ liệu, semantics và nơi có thẩm quyền phát hành claim.

Các claim chưa xác minh không được dùng để chọn tenant, client, mức xác thực hoặc quyền trước khi verify thành công. Sau đó vẫn phải đối chiếu với ngữ cảnh request và dữ liệu trạng thái hiện hành.

## 13. Phân phối trạng thái trong hệ thống nhiều node

Revocation và replay prevention làm giảm tính stateless của JWT. Nếu nhiều resource server cùng xác minh token, chúng phải nhìn thấy trạng thái nhất quán trong khoảng thời gian phù hợp.

Các câu hỏi cần giải quyết:

- Denylist/nonce store có dùng chung cho tất cả node cần kiểm tra không?
- Thời gian lan truyền sự kiện thu hồi tối đa là bao lâu?
- Cache local có thể giữ trạng thái active cũ trong bao lâu?
- Hai request đồng thời có thể cùng tiêu thụ một jti không?
- Khi kho trạng thái lỗi hoặc mất kết nối, hành vi của từng endpoint là gì?
- Có cơ chế xóa cache khẩn cấp khi tài khoản, phiên hoặc khóa bị vô hiệu không?

### 13.1. Tính nhất quán và cửa sổ thu hồi

Nếu một node ghi nhận jti đã bị thu hồi nhưng node khác chưa nhận sự kiện, token có thể tiếp tục được chấp nhận ở node thứ hai. Cần xác định **revocation propagation window** tối đa và đánh giá nó theo độ nhạy cảm tài nguyên.

Các cách giảm cửa sổ:

- Dùng kho trạng thái trung tâm hoặc hệ thống phân phối sự kiện đáng tin cậy.
- Giới hạn TTL cache trạng thái active.
- Chủ động invalidate cache khi có sự kiện thu hồi.
- Đặt TTL ngắn cho access token.
- Dùng introspection cho endpoint cần trạng thái gần thời gian thực.

Không tuyên bố thu hồi tức thời nếu kiến trúc chỉ cập nhật trạng thái bất đồng bộ và các node có cache dài.

### 13.2. Fail closed hay fail open?

Nếu policy yêu cầu kiểm tra revocation/replay nhưng kho trạng thái không truy cập được, hệ thống không biết token còn active hay không.

| Lựa chọn | Hành vi | Rủi ro |
| --- | --- | --- |
| **Fail closed** | Từ chối request khi không thể kiểm tra trạng thái bắt buộc | Có thể giảm availability khi kho trạng thái lỗi |
| **Fail open** | Tạm chấp nhận token nếu chữ ký và claims cơ bản hợp lệ | Token đã bị thu hồi hoặc replay có thể được chấp nhận |

Với thao tác nhạy cảm, token dùng một lần hoặc chính sách yêu cầu revocation tức thời, fail closed thường phù hợp hơn. Nếu một hệ thống chọn fail open cho một endpoint ít nhạy cảm, đó phải là quyết định rủi ro được tài liệu hóa, có giới hạn thời gian, giám sát và phương án giảm thiểu; không phải fallback ngầm.

## 14. Mã giả kiểm tra jti, revocation và binding

Mã giả sau giả định token đã qua xác minh mật mã và claims cơ bản:

~~~text
function validateAdditionalTokenState(tokenContext, request, policy, now):
    claims = tokenContext.verifiedClaims

    if policy.requireJti:
        require claims.jti exists
        require claims.jti is a valid bounded string

    if policy.requireOneTimeUse:
        require claims.jti exists
        replayKey = namespacedKey(
            tokenContext.issuer,
            tokenContext.profile,
            claims.jti
        )
        expiry = effectiveAcceptanceEnd(claims.exp, policy.clockSkew)
        require atomicInsertIfAbsent(replayKey, expiresAt = expiry)

    if policy.checkRevocation:
        require claims.jti exists or policy.revocationIdentifier exists
        revocationKey = namespacedKey(
            tokenContext.issuer,
            tokenContext.profile,
            revocationIdentifier(claims, policy)
        )
        state = trustedRevocationStore.lookup(revocationKey)
        require stateStoreAvailable(state)
        require state is not REVOKED

    if policy.requireSessionActive:
        require trustedSessionStore.isActive(claims.sid, claims.sub)

    if policy.requireClientBinding:
        require verifiedClientContextMatches(claims, request.clientContext)

    if policy.requireTenantBinding:
        require claims.tenant_id == request.trustedTenantContext.id

    if policy.requireDpop:
        proof = strictParseDpopProof(request.dpopHeader)
        require verifyDpopProof(proof)
        require proof.publicKeyThumbprint == claims.cnf.jkt
        require proof.htm == request.method
        require proof.htu == canonicalRequestUri(request)
        require proof.iat is within policy.proofAgeWindow
        require proof.ath matches hashOfPresentedAccessToken(request)
        require atomicInsertIfAbsent(
            dpopReplayKey(proof.publicKeyThumbprint, proof.jti),
            expiresAt = proof.iat + policy.proofReplayWindow
        )

    return AdditionalTokenChecksPassed
~~~

Đây là pseudocode khái quát; không phải mọi policy đều cần tất cả các bước. Các hàm DPoP, mTLS, session và revocation phải tuân thủ đúng profile giao thức. Nếu không thể xác định trạng thái bắt buộc do kho dữ liệu lỗi, không được giả định token active.

## 15. Ví dụ lựa chọn cơ chế

| Tình huống | Kiểm tra phù hợp | Lý do |
| --- | --- | --- |
| API nhận access token bearer ngắn hạn, không yêu cầu thu hồi tức thời | exp và policy thời gian; có thể dùng access token TTL ngắn | Đơn giản, chấp nhận cửa sổ rủi ro tới exp |
| Người dùng đăng xuất và token cần bị chặn ngay | Denylist jti hoặc kiểm tra session/introspection | Có trạng thái thu hồi trước exp |
| JWT assertion chỉ được sử dụng một lần | jti + atomic consume store | Ngăn hai lần sử dụng cùng assertion |
| Token bị phát hiện rò rỉ | Thu hồi jti/session; cân nhắc vô hiệu hóa khóa nếu phạm vi rộng | Giảm khả năng sử dụng token đã lộ |
| Resource server cần trạng thái token gần thời gian thực | Introspection hoặc trạng thái tập trung | Authorization server quyết định token active |
| Access token phải gắn với client key | DPoP và cnf.jkt | Người trình bày phải chứng minh sở hữu khóa |
| Access token gắn với client certificate | mTLS và cnf.x5t#S256 | Token chỉ được dùng với chứng thư tương ứng |
| Khóa ký issuer bị lộ | Emergency key invalidation và rotation | Không thể chỉ thu hồi một vài jti nếu mọi token ký bằng khóa bị nghi ngờ |

Không nên bật mọi cơ chế cho mọi endpoint. Hãy bắt đầu từ yêu cầu bảo mật, khả năng hạ tầng và độ trễ thu hồi cần đạt.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nghĩ jti tự ngăn replay | Token vẫn có thể được gửi lại nhiều lần | Có replay store/nonce và atomic consume khi cần |
| Dùng jti chưa xác minh để ghi denylist | Attacker có thể tạo trạng thái giả hoặc gây quá tải | Chỉ ghi sau xác minh và kiểm tra quyền thu hồi |
| Dùng jti đơn lẻ trên nhiều issuer | Va chạm hoặc thu hồi nhầm token | Namespace theo issuer và profile |
| Dùng replay cache cho access token dùng nhiều lần | Request hợp lệ thứ hai bị từ chối | Phân biệt one-time token với bearer access token |
| TTL denylist ngắn hơn cửa sổ token còn hiệu lực | Token đã thu hồi quay lại được chấp nhận | Giữ bản ghi ít nhất tới exp + leeway |
| Kiểm tra revocation trước verify | Tốn tài nguyên và tin dữ liệu do attacker kiểm soát | Verify/claims trước khi tra trạng thái |
| Cache active quá lâu | Thu hồi có hiệu lực chậm | TTL cache phù hợp revocation SLA |
| Không có atomic consume | Hai request đồng thời cùng dùng một token một lần | Dùng thao tác nguyên tử trong kho trạng thái |
| Coi refresh rotation đã thu hồi access token cũ | Access token đã phát hành vẫn có thể dùng tới exp | Kết hợp denylist/introspection nếu cần |
| Coi DPoP chữ ký hợp lệ là đủ | Proof có thể sai method/URI hoặc bị replay | Kiểm tra toàn bộ DPoP binding |
| Tin chứng thư trong HTTP header | Client có thể giả mạo binding | Dùng chứng thư từ TLS đã xác thực/kênh proxy tin cậy |
| Fail open khi revocation store lỗi | Token đã thu hồi có thể được chấp nhận | Định nghĩa failure policy rõ, ưu tiên fail closed cho thao tác nhạy cảm |

## 17. Kiểm thử replay, revocation và binding

| Nhóm | Ca kiểm thử |
| --- | --- |
| jti | Thiếu, rỗng, sai kiểu, quá dài, trùng giữa issuer, trùng trong cùng issuer |
| Replay | Cùng assertion gửi hai lần; hai request đồng thời; jti đã được consume |
| TTL | Bản ghi còn tồn tại tới exp + leeway; không xóa quá sớm |
| Revocation | Token active, token bị thu hồi, tài khoản/phiên bị khóa, khóa ký bị vô hiệu |
| Store failure | Timeout, mất kết nối, dữ liệu stale, replica chậm, cache chưa invalidate |
| Multi-node | Thu hồi ở node A và kiểm tra ở node B; đo propagation window |
| Introspection | active true/false, endpoint lỗi, phản hồi không đáng tin cậy, cache TTL |
| DPoP | Key thumbprint mismatch, htm/htu sai, iat cũ/tương lai, jti replay, ath sai, nonce sai |
| mTLS | Chứng thư đúng, sai fingerprint, chứng thư hết hạn, proxy header giả |
| Binding context | Tenant mismatch, client mismatch, session mismatch, authentication context không đạt |
| Không rò rỉ | Log không chứa bearer token/secret; lỗi không làm lộ trạng thái nhạy cảm |

Đặc biệt, kiểm thử đồng thời là bắt buộc cho token dùng một lần. Một test tuần tự có thể pass dù triển khai vẫn mắc race condition giữa thao tác lookup và insert.

## 18. Checklist triển khai

1. [ ] Xác định jti có bắt buộc theo token profile hay không.
2. [ ] jti được issuer tạo với xác suất trùng lặp ngẫu nhiên không đáng kể.
3. [ ] Trạng thái jti được namespace theo issuer và token profile.
4. [ ] Phân biệt token bearer dùng nhiều lần với assertion/proof chỉ dùng một lần.
5. [ ] Replay detection dùng thao tác atomic consume; TTL bao phủ toàn bộ cửa sổ chấp nhận.
6. [ ] Chỉ tra revocation sau khi xác minh mật mã và claims.
7. [ ] Denylist không lưu nguyên bearer token; quyền ghi/đọc và audit được bảo vệ.
8. [ ] TTL bản ghi thu hồi không ngắn hơn exp cộng clock skew/leeway.
9. [ ] Nếu cần thu hồi tức thời, chọn denylist, introspection hoặc session state phù hợp.
10. [ ] Cache trạng thái active có TTL phù hợp với yêu cầu propagation/revocation.
11. [ ] Quy định fail-closed/fail-open cho từng endpoint; không có fallback ngầm.
12. [ ] Key revocation có cơ chế emergency invalidation trên tất cả node.
13. [ ] DPoP/mTLS binding được xác minh theo profile, không chỉ kiểm tra cnf tồn tại.
14. [ ] Tenant, client, session và authentication context được đối chiếu với nguồn tin cậy.
15. [ ] Có kiểm thử replay đồng thời, multi-node, store outage và cache invalidation.
16. [ ] Log không chứa token, secret hoặc dữ liệu binding nhạy cảm.

## 19. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** claim jti và các registered claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành bảo vệ JWT và validation theo profile.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile access token dạng JWT, bao gồm jti và claims liên quan.
- **RFC 7009 — OAuth 2.0 Token Revocation:** giao thức thu hồi token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái active của token.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc access token với chứng thư client.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWT, cnf/jkt và chống replay theo request.

**Nguyên tắc ghi nhớ:** jti chỉ định danh token; muốn chống replay cần lưu và tiêu thụ trạng thái theo cách nguyên tử. Muốn thu hồi trước exp cần một cơ chế trạng thái như denylist, introspection hoặc session check. Muốn chống đánh cắp bearer token cần ràng buộc với khóa/chứng thư và xác minh proof tương ứng. Chỉ áp dụng các kiểm tra bổ sung sau khi token đã được xác minh mật mã và theo đúng policy của endpoint.
