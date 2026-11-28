# Token subject

## 1. Subject trả lời câu hỏi nào?

**Subject** là chủ thể mà các phát biểu trong token nói đến. Trong JWT, claim thường dùng để nhận diện chủ thể này là `sub`. Subject có thể là một người dùng hoặc một danh tính ứng dụng, tùy loại token và quy tắc phát hành.

Ví dụ, ứng dụng quản lý hóa đơn gọi API nhân danh nhân viên An. Token có thể có subject là tài khoản của An, trong khi ứng dụng quản lý hóa đơn là client đã xin token. Nếu một job tự động gọi API bằng quyền của chính nó, subject lại có thể đại diện cho ứng dụng đó.

Theo JWT, giá trị `sub` là chuỗi phân biệt chữ hoa, chữ thường; định danh phải duy nhất trong phạm vi issuer hoặc duy nhất toàn cục. JWT tổng quát không bắt buộc mọi token đều có `sub`; profile sử dụng phải xác định khi nào claim này cần có. [RFC 7519, mục 4.1.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.2)

Trong IAM, đọc subject là bước xác định “token đang đại diện cho chủ thể nào”. Việc đó chưa trả lời chủ thể có được phép đọc một hóa đơn, thuộc tenant nào hoặc có thể thực hiện thao tác quản trị hay không.

## 2. Đọc subject trong một ví dụ

Đây là phần dữ liệu minh họa của một access token theo hợp đồng tích hợp giả định. Nó không phải token hoàn chỉnh, không có bằng chứng mật mã và không dùng được để truy cập hệ thống:

```json
{
  "iss": "https://identity.example.test",
  "sub": "person-7b32",
  "aud": "invoice-api",
  "client_id": "invoice-web",
  "scope": "invoices:read"
}
```

Có thể diễn giải như sau:

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| `iss` | Bên phát hành đưa ra các phát biểu trong token |
| `sub` | Chủ thể được token nói đến: `person-7b32` |
| `aud` | API dự kiến tiếp nhận token: `invoice-api` |
| `client_id` | Client đã xin token: `invoice-web` |
| `scope` | Phạm vi truy cập được biểu diễn trong tích hợp này |

Như vậy, subject không phải URL của API và cũng không nhất thiết là client ID. Việc các giá trị đôi khi bằng nhau trong một luồng cụ thể không làm chúng trở thành cùng một khái niệm.

Hợp đồng token phải mô tả rõ tên claim, kiểu dữ liệu, trường bắt buộc và ý nghĩa của từng trường. Không thể thấy một JSON có những tên quen thuộc rồi kết luận nó đã đáp ứng đầy đủ một chuẩn access token.

## 3. Định danh bằng cặp issuer và subject

Giả sử API chấp nhận hai nhà cung cấp danh tính độc lập:

| Issuer | Subject | Danh tính thực tế trong ví dụ |
| --- | --- | --- |
| `https://idp-a.example.test` | `42` | Tài khoản An tại IdP A |
| `https://idp-b.example.test` | `42` | Tài khoản Bình tại IdP B |

Nếu API chỉ tra người dùng bằng `sub = "42"`, hai danh tính có thể bị nhập làm một. Một lỗi ánh xạ như vậy có thể dẫn tới đọc dữ liệu, dùng vai trò hoặc tiếp quản tài khoản của người khác dù token của cả hai đều có chữ ký hợp lệ từ issuer tương ứng.

Thiết kế thường dùng một khóa danh tính ngoài như sau:

```text
ExternalIdentityKey = (validatedIssuer, validatedSubject)
```

Từ “validated” có ý nghĩa quan trọng: issuer và subject phải đến từ token đã được xác minh theo cấu hình tin cậy. Một người gọi có thể tự viết chuỗi issuer trong JSON; việc chuỗi đó khớp một URL không chứng minh bên sở hữu URL đã phát hành token.

Một mô hình ánh xạ trong cơ sở dữ liệu có thể gồm:

| Trường | Vai trò |
| --- | --- |
| `issuer` | Định danh issuer đã được cấu hình tin cậy |
| `subject` | Giá trị subject nguyên vẹn theo quy tắc của issuer |
| `local_principal_id` | ID nội bộ mà ứng dụng dùng cho người dùng hoặc workload |
| `link_status` | Trạng thái liên kết còn hoạt động hay đã bị vô hiệu hóa |

Nên có ràng buộc duy nhất trên cặp `(issuer, subject)` và xử lý liên kết tài khoản theo một quy trình được kiểm soát. Không ghép hai chuỗi bằng một ký tự bất kỳ rồi bỏ qua khả năng nhập nhằng của phép ghép; khóa ghép trong cơ sở dữ liệu hoặc kiểu dữ liệu có cấu trúc diễn tả quan hệ rõ hơn.

Khi issuer xác định thêm các quy tắc namespace hoặc loại danh tính, mô hình nội bộ cũng phải thể hiện chúng nhất quán. Không dùng một giá trị tenant chưa được xác minh để “sửa” xung đột định danh.

## 4. Subject của người dùng và subject của workload

Không nên mặc định mọi `sub` đều tra được trong bảng nhân viên.

Trong JWT Access Token Profile cho OAuth 2.0, với luồng có resource owner, subject thường tương ứng với resource owner; với luồng như client credentials không có resource owner tham gia, subject thường tương ứng với định danh ứng dụng do authorization server xác định. Đây là ngữ nghĩa của profile, không phải suy luận từ hình dạng chuỗi. [RFC 9068, mục 2.2](https://www.rfc-editor.org/rfc/rfc9068.html#section-2.2)

Hai tình huống minh họa:

```text
Nhân viên dùng ứng dụng web:
  subject được ánh xạ tới một người dùng
  client được ánh xạ tới ứng dụng web

Job đồng bộ chạy bằng quyền của chính nó:
  subject được ánh xạ tới một danh tính ứng dụng
  client được ánh xạ tới ứng dụng xin token
```

Hệ thống phân quyền cần biết loại principal theo dữ liệu đáng tin cậy. Ví dụ, quy tắc “chỉ nhân viên có thể tự phê duyệt hồ sơ của mình” không nên vô tình áp dụng cho một workload chỉ vì workload cũng có một chuỗi `sub`.

Authorization server phải quản lý namespace chủ thể để ứng dụng không tự chọn một client ID trùng với subject của người dùng đặc quyền rồi được nhận quyền của người đó. RFC 9068 cũng nêu nguy cơ nhầm lẫn này khi dùng client ID làm subject cho client credentials. [RFC 9068, mục 5](https://www.rfc-editor.org/rfc/rfc9068.html#section-5)

Ở phía API, không nhận diện loại principal chỉ bằng tiền tố như `person-` hoặc `service-` nếu hợp đồng tích hợp không bảo đảm và thực thi quy tắc đó. Một chuỗi trông giống tên người dùng không phải bằng chứng rằng đã có người dùng đăng nhập hoặc thực hiện MFA.

## 5. Phân biệt subject với các định danh gần giống

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| Subject, thường là `sub` | Token đang nói về chủ thể nào? |
| Issuer, thường là `iss` | Ai phát hành và chịu trách nhiệm về các phát biểu? |
| Audience, thường là `aud` | Token dành cho bên nhận nào? |
| `client_id` trong profile phù hợp | Client nào đã xin token? |
| `azp` trong OpenID Connect | Bên được xác định là authorized party theo ngữ nghĩa OIDC |
| Actor trong mô hình ủy quyền | Ai đang hành động thay mặt subject? |
| Token ID, thường là `jti` | Đây là token cụ thể nào? |
| Email hoặc tên hiển thị | Thông tin hồ sơ nào đang được cung cấp? |

Một người dùng có thể nhận nhiều token khác nhau theo thời gian. Vì thế, token ID không phù hợp để làm ID lâu dài của tài khoản. Tương tự, tên hiển thị có thể trùng và email có thể thay đổi; không nên mặc định các giá trị đó có tính ổn định như định danh chủ thể mà hợp đồng đã bảo đảm.

Trong token exchange, claim `act` có thể biểu diễn bên hành động được ủy quyền. `sub` ở cấp ngoài vẫn nói về subject của token, còn thông tin trong `act` nhận diện actor. Không được thay thế hai vai trò này cho nhau khi ra quyết định truy cập hoặc ghi audit. [RFC 8693, mục 4.1](https://www.rfc-editor.org/rfc/rfc8693.html#section-4.1)

Ví dụ về thông tin logic trong một luồng ủy quyền đã được hệ thống hỗ trợ:

```json
{
  "iss": "https://identity.example.test",
  "sub": "person-7b32",
  "aud": "invoice-api",
  "act": {
    "sub": "support-operator-18"
  }
}
```

Ví dụ này diễn đạt subject là `person-7b32`, actor hiện tại là `support-operator-18`. Nó không tự cấp quyền hỗ trợ viên hành động thay mặt bất kỳ ai. Cả việc phát hành token ủy quyền và việc chấp nhận thao tác tại API phải được chính sách cho phép.

## 6. Khi nào có thể tin subject?

Một chuỗi `sub` đọc được từ payload chưa thể trở thành danh tính của request. Cách xử lý cần dựa vào loại token và profile đã chọn:

```text
Nhận credential
  -> xác định loại token được API chấp nhận
  -> kiểm tra bằng thư viện và cấu hình tin cậy
  -> kiểm tra issuer, audience, thời gian và các ràng buộc áp dụng
  -> kiểm tra subject đúng schema và yêu cầu của profile
  -> ánh xạ danh tính ngoài sang principal nội bộ
  -> kiểm tra trạng thái và quyền đối với tài nguyên
```

Với JWT được bảo vệ bằng chữ ký, phải xác minh tính toàn vẹn, thuật toán được phép và khóa thuộc đúng issuer theo cấu hình tin cậy. Không để token tự chỉ định một issuer hoặc địa chỉ khóa tùy ý rồi mặc nhiên tin nó. Với opaque token, thông tin subject cần đến từ cơ chế xác minh đáng tin cậy của hệ thống thay vì cố giải mã chuỗi.

Nếu API yêu cầu subject, cần xác định rõ cách xử lý khi thiếu `sub`, có giá trị `null`, có kiểu số hoặc có chuỗi không đáp ứng hợp đồng. Không tự động chuyển sang `email`, `username` hay một subject mặc định để tiếp tục truy cập.

Giữ nguyên quy tắc so sánh của định danh. Chẳng hạn, JWT quy định `sub` là chuỗi phân biệt hoa thường; tự chuyển hết về chữ thường có thể nhập hai subject thành một. Cũng không ép chuỗi `"00042"` thành số `42` chỉ để tiện truy vấn.

API cần kiểm tra đúng loại token trước khi sử dụng subject. ID token dành cho client đăng nhập không tự trở thành access token hợp lệ của API dù có `sub` mà API nhận ra.

## 7. Từ subject đến kiểm soát truy cập ở mức đối tượng

Giả sử sau khi xác minh token, API ánh xạ được:

```text
(issuer, subject) -> local principal P100
```

Một hóa đơn trong cơ sở dữ liệu có chủ sở hữu `P200`. Nếu request là:

```http
GET /invoices/invoice-819 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
```

API phải kiểm tra `P100` có quyền xem hóa đơn của `P200` hay không. Chữ ký hợp lệ và việc subject tồn tại chỉ giúp xác lập danh tính, không tự chứng minh quyền sở hữu đối tượng.

Có thể biểu diễn một chính sách minh họa:

```text
Cho phép đọc hóa đơn nếu:
  credential hợp lệ cho invoice-api
  VÀ principal còn hoạt động
  VÀ token có phạm vi đọc cần thiết
  VÀ principal được phép truy cập tenant của hóa đơn
  VÀ (principal là chủ sở hữu HOẶC có quyền xem thay được cấp rõ ràng)
```

Trong chính sách này, subject là một đầu vào để tìm principal. Scope, trạng thái tài khoản, tenant và quan hệ với đối tượng vẫn cần được đánh giá riêng. Vai trò hoặc thuộc tính cũng phải lấy từ nguồn có thẩm quyền, không suy ra từ nội dung định danh.

Không lấy tham số `userId` trong URL làm subject của request. Bên gọi có thể đổi URL, nhưng danh tính đã xác minh phải do lớp bảo mật thiết lập. Nếu API hỗ trợ thao tác thay mặt người khác, đó là một quyền riêng cần được kiểm tra và ghi nhận.

## 8. Subject trong OpenID Connect và quyền riêng tư

Đối với ID token của OpenID Connect, `sub` là bắt buộc và định danh người dùng trong phạm vi issuer; nó không được cấp lại cho một người dùng khác. OIDC định nghĩa subject kiểu public và pairwise. Với pairwise, định danh được tính theo sector, nên cùng người dùng có thể có subject khác nhau giữa các sector; các client cùng sector có thể nhận cùng định danh tương ứng. [OpenID Connect Core, mục 2 và 8](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes)

Ví dụ, cùng một người dùng đăng nhập ứng dụng học tập và ứng dụng bán hàng có thể xuất hiện với hai subject pairwise khác nhau. Thiết kế này hạn chế khả năng các bên tự liên kết hoạt động chỉ bằng một ID chung.

Vì thế, không nên cho rằng mọi ứng dụng trong tổ chức đều có thể ghép tài khoản chỉ bằng cách so sánh `sub`. Cũng không được tự động ghép các subject khác nhau chỉ vì chúng có cùng email. Việc liên kết cần một quy trình xác minh quyền sở hữu tài khoản và thẩm quyền của nguồn dữ liệu.

Public subject không có nghĩa dữ liệu phải được công khai trên Internet. Pairwise subject cũng không bảo đảm mọi dữ liệu trong token là vô danh: email, số điện thoại, tenant hoặc nhật ký truy cập vẫn có thể giúp nhận diện người dùng.

Không suy đoán subject trong access token luôn bằng subject trong ID token. Các loại token có bên nhận và profile khác nhau; chỉ dựa vào quan hệ được bên phát hành bảo đảm và được hợp đồng tích hợp mô tả.

## 9. Subject trong vòng đời danh tính

Khi người dùng đổi tên hoặc email, liên kết tài khoản không nên tự mất chỉ vì ứng dụng đã chọn thông tin hiển thị làm khóa chính. Một định danh chủ thể ổn định giúp tách thông tin hồ sơ có thể đổi khỏi quan hệ danh tính mà ứng dụng đang quản lý.

Tuy nhiên, subject ổn định không có nghĩa tài khoản luôn được phép truy cập. Nếu principal nội bộ bị vô hiệu hóa, quy trình cấp quyền và kiểm tra request phải thực hiện chính sách tương ứng. Chỉ thấy `(issuer, subject)` từng tồn tại trong cơ sở dữ liệu không đủ để khôi phục mọi quyền cũ.

Khi chuyển IdP hoặc thay đổi issuer, cần kế hoạch ánh xạ có chứng cứ. Cùng chuỗi subject dưới issuer mới không tự động là cùng tài khoản. Ngược lại, nếu cơ chế pairwise hoặc cấu hình sector thay đổi làm subject khác đi, cũng không nên tự tạo tài khoản trùng mà bỏ qua quy trình migration đã thiết kế.

Liên kết một danh tính ngoài mới vào tài khoản có đặc quyền là thao tác nhạy cảm. Cần xác minh người yêu cầu có quyền thực hiện liên kết và giữ được dấu vết ai đã tạo, thay đổi hoặc gỡ ánh xạ.

## 10. Audit và các tình huống kiểm thử

Nhật ký kiểm toán nên phân biệt principal nội bộ, issuer, subject, client và actor khi có. Điều này giúp trả lời “quyền của ai được sử dụng” và “bên nào thực hiện hành động” mà không ghi toàn bộ token.

Subject có thể là dữ liệu nhận diện gián tiếp. Chỉ ghi những trường cần thiết, giới hạn người đọc log và thời gian lưu; không coi một chuỗi khó đọc là dữ liệu không nhạy cảm. Với token chưa xác minh được, không ghi nhận subject do nó tự khai là danh tính đã đăng nhập thành công.

Các tình huống sau giúp kiểm chứng thiết kế:

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Hai issuer tin cậy có cùng chuỗi `sub` | Ánh xạ thành hai danh tính ngoài độc lập |
| JWT chứa subject đã biết nhưng chữ ký sai | Không thiết lập principal từ subject đó |
| Token dành cho audience khác | Không dùng subject để bỏ qua kiểm tra bên nhận |
| Thiếu hoặc sai kiểu `sub` khi profile yêu cầu | Từ chối, không fallback âm thầm sang email |
| Subject chỉ khác chữ hoa hoặc số 0 đầu | So sánh theo hợp đồng, không tự chuẩn hóa gây nhập nhằng |
| Workload có token hợp lệ | Áp dụng đúng chính sách cho danh tính máy |
| Subject thuộc người dùng khác chủ hóa đơn | Kiểm tra quyền đối tượng trước khi trả dữ liệu |
| Hai subject pairwise có cùng email | Không tự động gộp tài khoản |
| Token có actor được ủy quyền | Phân biệt actor với subject trong quyền và audit |
| Principal đã bị vô hiệu hóa | Thực thi chính sách trạng thái và thu hồi quyền đã thiết kế |

Hiểu đúng token subject giúp nối dữ liệu trong token với mô hình danh tính của ứng dụng. Khóa định danh cần đúng phạm vi issuer, principal cần được ánh xạ từ bằng chứng đã xác minh, còn quyết định truy cập phải kết hợp trạng thái, quyền và tài nguyên cụ thể.
