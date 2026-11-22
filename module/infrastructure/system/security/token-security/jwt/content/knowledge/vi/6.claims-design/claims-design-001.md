# Claim là gì và quan hệ giữa claims với nghiệp vụ

## 1. Claim là gì?

Trong **JSON Web Token (JWT)**, *claim* là một cặp **tên – giá trị** trong đối tượng JSON mang thông tin mà bên phát hành token (*issuer*) đưa ra về một chủ thể, một phiên truy cập hoặc ngữ cảnh sử dụng token. Tập hợp các cặp này gọi là **JWT Claims Set**.

Ví dụ một tập claims:

```json
{
  "iss": "https://identity.example.net",
  "sub": "user_42",
  "aud": "https://api.orders.example.net",
  "exp": 1767226500,
  "tenant_id": "tenant_17",
  "scope": "orders:read orders:create"
}
```

Ở đây, bên phát hành khẳng định rằng token dành cho API đơn hàng, có chủ thể là `user_42`, liên quan đến tenant `tenant_17` và mang các phạm vi truy cập được cấp. Đây là **những khẳng định do issuer đưa ra**; API nhận token phải xác minh token và quyết định từng khẳng định có đủ tin cậy cho mục đích sử dụng hay không.

Ba khái niệm cần phân biệt:

- **Claim**: một thông tin cụ thể, chẳng hạn `sub = "user_42"`.
- **Claims Set**: toàn bộ đối tượng JSON gồm các claim trong payload.
- **JWT**: định dạng mang Claims Set cùng thông tin cần thiết để bảo vệ, truyền và kiểm tra token. JWT có thể được ký theo JWS hoặc mã hóa theo JWE; định dạng và cách bảo vệ thực tế phụ thuộc vào giao thức sử dụng.

Trong JWT ký thông dụng, payload được mã hóa **Base64URL để biểu diễn**, không phải để giữ bí mật. Người có token thường đọc được claims. Chữ ký hợp lệ giúp phát hiện payload bị thay đổi và xác thực nguồn ký theo khóa tin cậy; chữ ký **không tự chứng minh** mọi thông tin nghiệp vụ còn mới, người cầm token là chủ thể hợp pháp, hoặc chủ thể được phép thao tác trên từng tài nguyên.

## 2. Claims thể hiện điều gì trong một hệ thống nghiệp vụ?

Claims tạo ra một **hợp đồng dữ liệu giữa bên phát hành token và bên nhận token**. Hợp đồng đó cho biết API có thể hiểu thông tin nào, ý nghĩa của thông tin đó, ai có trách nhiệm xác nhận và trong trường hợp nào nó được phép dùng để đưa ra quyết định.

Có thể chia các claims thường gặp thành bốn nhóm theo mục đích sử dụng:

| Nhóm | Ví dụ | Câu hỏi nghiệp vụ liên quan |
| --- | --- | --- |
| Chủ thể và nguồn phát hành | `sub`, `iss` | Ai hoặc thực thể nào được token đề cập? Ai phát hành khẳng định này? |
| Giới hạn và mục đích token | `aud`, `exp`, `nbf`, `iat`, `jti` | Token dành cho bên nào, có thể được chấp nhận khi nào, cần nhận diện phiên bản token nào? |
| Ngữ cảnh nghiệp vụ | `tenant_id`, `organization_id`, `region` | Yêu cầu thuộc không gian dữ liệu hoặc tổ chức nào? |
| Khả năng truy cập được cấp | `scope`, `roles`, `permissions` | Issuer đã cấp phạm vi hoặc vai trò nào, và bên nhận sẽ diễn giải chúng ra sao? |

Các tên ở hai nhóm cuối thường là **claim tùy biến**: JWT không quy định chung cách hiểu `tenant_id`, `roles` hay `permissions` cho mọi hệ thống. Ví dụ, `roles = ["manager"]` trong hệ thống bán hàng không nhất thiết có cùng ý nghĩa với `manager` trong hệ thống nhân sự.

**Claim không đồng nghĩa với bản ghi nghiệp vụ.** `sub = "user_42"` thường là định danh ổn định để tìm người dùng trong một phạm vi issuer đã thỏa thuận; token không chứa toàn bộ hồ sơ người dùng. `tenant_id = "tenant_17"` có thể xác định ngữ cảnh tenant được chọn lúc phát hành, nhưng không bảo đảm người dùng vẫn còn là thành viên tenant đó tại thời điểm một API đang xử lý yêu cầu.

## 3. Từ dữ liệu nghiệp vụ đến claim: ánh xạ có chủ đích

Không phải mọi trường dữ liệu trong cơ sở dữ liệu đều nên đưa vào JWT. Khi thiết kế, hãy đi từ **nhu cầu của bên nhận token** tới claim cần thiết:

1. **Xác định ai nhận token.** Ví dụ, API đơn hàng cần biết issuer, đối tượng nhận token và định danh chủ thể. Một dịch vụ báo cáo có thể cần bộ claims khác.
2. **Xác định quyết định cần đưa ra.** API cần kiểm tra phạm vi gọi endpoint, lựa chọn tenant hay quyền truy cập một đơn hàng cụ thể?
3. **Xác định nguồn sự thật.** Dữ liệu nào có thể do hệ thống định danh xác nhận, dữ liệu nào chỉ dịch vụ nghiệp vụ mới biết?
4. **Xác định độ biến động.** Nếu quyền hoặc trạng thái thay đổi ngay trong thời gian sống của token, API cần tra cứu trạng thái mới nhất hoặc có cơ chế thu hồi/cập nhật thích hợp.
5. **Định nghĩa hợp đồng claims.** Ghi rõ tên, kiểu dữ liệu, ý nghĩa, phạm vi định danh, nguồn phát hành, bên tiêu thụ, tính bắt buộc và quy tắc xử lý khi thiếu/sai.

Ví dụ về lựa chọn:

| Thông tin | Có nên là claim? | Lý do |
| --- | --- | --- |
| Định danh chủ thể `sub` | Thường có | Giúp API liên kết hành động với chủ thể; cần xác định phạm vi duy nhất theo `iss`. |
| API đích `aud` | Nên có và được kiểm tra | Hạn chế chấp nhận nhầm token phát hành cho một hệ thống khác. |
| Phạm vi được cấp `scope` | Có khi phù hợp với giao thức | Giúp kiểm tra phạm vi thao tác; không thay thế quy tắc truy cập từng đối tượng. |
| Tenant đang được chọn `tenant_id` | Có thể có, theo hợp đồng | Tiện cho phân vùng dữ liệu, nhưng phải đối chiếu tenant của tài nguyên và quan hệ thành viên khi cần. |
| Số dư ví, giá đơn hàng, trạng thái tài khoản | Thường không nên | Dễ lỗi thời; hệ thống sở hữu dữ liệu phải cung cấp giá trị hiện hành. |
| Mật khẩu, khóa bí mật, dữ liệu cá nhân nhạy cảm | Không | Token dễ bị sao chép, ghi log hoặc bị đọc nếu chỉ ký; tạo rủi ro lộ dữ liệu không cần thiết. |

Nếu sử dụng một claim như `email` để hiển thị giao diện, hãy chấp nhận khả năng thông tin đó cũ. Nếu dùng email làm khóa phân quyền hoặc định danh chính, việc đổi email sẽ gây lỗi mô hình; thông thường nên dùng định danh ổn định, không tái sử dụng theo hợp đồng.

## 4. Ví dụ: claims trong API quản lý đơn hàng đa tenant

Giả sử một nền tảng có nhiều cửa hàng (**tenant**). Người dùng chọn cửa hàng `tenant_17` để thao tác với đơn hàng. Dịch vụ định danh phát hành **access token** có Claims Set minh họa:

```json
{
  "iss": "https://identity.example.net",
  "sub": "user_42",
  "aud": "https://api.orders.example.net",
  "iat": 1767225600,
  "nbf": 1767225600,
  "exp": 1767226500,
  "jti": "token_a81f",
  "tenant_id": "tenant_17",
  "scope": "orders:read orders:create"
}
```

Hai giá trị thời gian `iat` và `exp` trong ví dụ cách nhau **900 giây (15 phút)**, biểu diễn bằng số giây từ Unix epoch. Các giá trị chỉ để minh họa hợp đồng dữ liệu, không phải một token có thể sử dụng. `tenant_id` và cách đặt tên các phạm vi `orders:read`, `orders:create` là quy ước riêng của hệ thống ví dụ.

Khi nhận `GET /orders/order_123`, dịch vụ đơn hàng cần kết hợp **kiểm tra token** và **kiểm tra nghiệp vụ**:

```text
Yêu cầu: GET /orders/order_123
  |
  +-- 1. Xác minh chữ ký / bảo vệ mật mã theo cấu hình tin cậy
  +-- 2. Kiểm tra iss, aud, exp, nbf (nếu có), loại token và các ràng buộc cần thiết
  +-- 3. Lấy sub, tenant_id, scope từ claims đã được xác minh
  +-- 4. Yêu cầu phải có scope "orders:read"
  +-- 5. Tải order_123 và kiểm tra order.tenant_id == tenant_id trong ngữ cảnh
  +-- 6. Kiểm tra chính sách hiện hành: chủ sở hữu, thành viên, vai trò,
  |      trạng thái đơn hàng, các quy tắc truy cập khác nếu áp dụng
  +-- 7. Chỉ trả dữ liệu khi tất cả điều kiện bắt buộc đều đạt
```

Ví dụ, `scope` có `orders:read` **không mặc nhiên** cho phép đọc mọi đơn hàng. Nếu `order_123` thuộc `tenant_99`, hoặc người dùng không có quyền xem đơn cụ thể, yêu cầu vẫn phải bị từ chối. Không được tin riêng `tenant_id` do client gửi trong URL/header để quyết định phân vùng; cần liên kết tenant trong yêu cầu với ngữ cảnh token đã xác minh và kiểm tra quyền trên tài nguyên thật.

Ngược lại, một token thiếu `orders:read` không được tự động nâng quyền chỉ vì dữ liệu đơn hàng có trường `owner_id = "user_42"`. Quy tắc chính xác là lựa chọn của nghiệp vụ, nhưng phải được thực thi nhất quán tại điểm kiểm soát truy cập.

### Một claim, nhiều cách diễn giải sai

Giả sử token có `"roles": ["admin"]`. Nếu không định nghĩa rõ **admin của hệ thống nào, tenant nào, với những hành động nào**, một API có thể lầm tưởng đây là quyền quản trị toàn cục. Khi vai trò cần gắn tổ chức, hợp đồng có thể thể hiện bằng ngữ cảnh tenant được kiểm chứng hoặc một cấu trúc phân quyền riêng. Bên nhận vẫn phải áp dụng chính sách của mình; không tự xem tên vai trò do một issuer bất kỳ phát hành là quyền tuyệt đối.

## 5. Claims, xác thực và phân quyền liên hệ với nhau thế nào?

Ba bước liên quan nhưng không thay thế cho nhau:

| Bước | Câu hỏi | Dữ liệu chính |
| --- | --- | --- |
| **Xác thực token** | Token có đúng issuer tin cậy, đúng bên nhận, đúng thời hạn, đúng kiểu và được bảo vệ hợp lệ không? | `iss`, `aud`, `exp`, `nbf`, thuật toán, khóa và cấu hình chấp nhận |
| **Xác định ngữ cảnh chủ thể** | Token đang nói về ai, yêu cầu đang thao tác trong tenant/phiên nào? | `sub`, `tenant_id` và dữ liệu ngữ cảnh được chấp nhận |
| **Phân quyền nghiệp vụ** | Chủ thể có được thực hiện hành động này trên tài nguyên này *ngay lúc này* không? | `scope` hoặc claims liên quan **kết hợp** chính sách, quan hệ sở hữu, trạng thái và dữ liệu hiện hành |

JWT là cơ chế **chuyển một số khẳng định có thể kiểm chứng giữa các thành phần**. Nó không tự quyết định toàn bộ quyền trong nghiệp vụ. Chẳng hạn, hệ thống thanh toán có thể chấp nhận token hợp lệ cho thao tác `payments:create`, nhưng vẫn phải từ chối nếu tài khoản bị khóa, hạn mức không đủ hoặc giao dịch vi phạm trạng thái cho phép.

Trong mô hình máy gọi máy, `sub` có thể đại diện cho một dịch vụ hoặc một chủ thể kỹ thuật, không nhất thiết là con người. Tương tự, cùng một người có thể có nhiều vai trò tại nhiều tổ chức; không nên mặc định mọi claim mang ý nghĩa toàn cục.

## 6. Những ranh giới tin cậy cần ghi vào hợp đồng

**Ai được quyền khẳng định điều gì?** Một issuer định danh có thể đáng tin để xác nhận `sub` nhưng chưa chắc có đủ dữ liệu để khẳng định hạn mức tín dụng mới nhất. Nếu nhiều issuer được chấp nhận, bên nhận phải cấu hình riêng issuer, audience, thuật toán, khóa tin cậy và tập claims có ý nghĩa; không nhập chung các giá trị có cùng tên nhưng khác ngữ nghĩa.

**Claims có thể cũ.** Khi người dùng bị vô hiệu hóa, rời tổ chức, bị thu hồi vai trò hoặc khi đơn hàng đổi chủ, token đã phát hành có thể còn hiệu lực đến `exp`. Với dữ liệu quyền dễ biến động, cân nhắc thời hạn token ngắn, kiểm tra quyền dựa trên dữ liệu hiện hành, cơ chế thu hồi hoặc tham chiếu trạng thái ở nơi có thẩm quyền. Chọn biện pháp theo yêu cầu độ trễ thu hồi quyền của nghiệp vụ.

**Token có thể bị đánh cắp hoặc dùng lại.** Có chữ ký đúng không chứng minh người gửi yêu cầu là chủ thể ban đầu. Bảo vệ đường truyền và nơi lưu token, giảm thời gian hiệu lực; với yêu cầu chống phát lại cao, cân nhắc token ràng buộc với bên sở hữu khóa, `jti` kết hợp cơ chế theo dõi phù hợp, hoặc biện pháp chống phát lại riêng. Riêng `jti` không tự ngăn replay nếu không có logic kiểm tra.

**Claims có thể lộ dữ liệu.** JWT ký không mặc nhiên mã hóa nội dung. Tránh đặt bí mật, danh sách quyền quá lớn, thông tin cá nhân không cần thiết hoặc dữ liệu nghiệp vụ nhạy cảm vào payload. Nếu cần bảo mật nội dung ở cấp token, đánh giá JWE cùng các yêu cầu truyền tải và quản lý khóa; mã hóa token cũng không thay thế kiểm soát quyền truy cập.

**Một token chỉ nên có mục đích rõ ràng.** Không tùy tiện dùng ID token của quá trình đăng nhập làm access token cho API. Bên nhận phải xác minh đúng loại token, audience và hồ sơ claims theo giao thức đang áp dụng, tránh chấp nhận token hợp lệ về mật mã nhưng sai mục đích.

## 7. Quy ước thiết kế claims dễ duy trì

### Phân biệt claims chuẩn và claims tùy biến

RFC 7519 định nghĩa những tên claim đã đăng ký như:

- `iss` (*issuer*): bên phát hành token.
- `sub` (*subject*): chủ thể được đề cập; định danh phải được hiểu trong phạm vi issuer/hợp đồng.
- `aud` (*audience*): các bên nhận dự kiến; có thể là một chuỗi hoặc mảng chuỗi.
- `exp` (*expiration time*): thời điểm token không còn được chấp nhận.
- `nbf` (*not before*): thời điểm sớm nhất token được chấp nhận.
- `iat` (*issued at*): thời điểm phát hành.
- `jti` (*JWT ID*): định danh JWT; hữu ích cho theo dõi hoặc chính sách chống replay nếu có hỗ trợ.

Các claim theo chuẩn không mặc nhiên bắt buộc trong **mọi** JWT; ứng dụng hoặc hồ sơ giao thức phải quy định cụ thể trường nào bắt buộc và kiểm tra tương ứng. Thời gian `exp`, `nbf`, `iat` dùng định dạng **NumericDate**; không so sánh như chuỗi ngày tháng.

Các trường như `tenant_id`, `roles`, `permissions` là quy ước riêng hoặc do một hồ sơ giao thức khác định nghĩa. Tránh đặt claim tùy biến trùng tên với claim đã đăng ký nhưng mang nghĩa khác. Khi chia sẻ giữa nhiều tổ chức hoặc nhà phát hành, có thể dùng tên claim dạng URI để giảm xung đột, đồng thời tài liệu hóa ý nghĩa rõ ràng.

### Mẫu hợp đồng cho một claim nghiệp vụ

| Thuộc tính | Ví dụ với `tenant_id` |
| --- | --- |
| Tên và kiểu dữ liệu | `tenant_id`: chuỗi không rỗng |
| Ý nghĩa | Tenant mà access token được phát hành cho trong phiên/ngữ cảnh hiện tại |
| Nguồn xác nhận | Dịch vụ phát hành kiểm tra quyền chọn tenant trước khi đưa vào token |
| Phạm vi duy nhất | ID tenant theo quy ước của nền tảng, không tự suy từ tên hiển thị |
| Bên nhận hợp lệ | API đơn hàng đã được liệt kê trong `aud` |
| Bắt buộc hay tùy chọn | Bắt buộc với API đa tenant trong ví dụ |
| Kiểm tra khi sử dụng | So khớp tenant của tài nguyên; xác minh quyền thành viên hiện hành nếu chính sách yêu cầu |
| Xử lý lỗi | Thiếu, sai kiểu, không khớp hoặc không đủ quyền: từ chối theo quy tắc API |
| Chu kỳ thay đổi | Tenant của phiên có thể thay đổi; phát hành token mới khi chuyển ngữ cảnh |

Đối với `scope`, cần định nghĩa tên quyền, ngữ cảnh áp dụng, cách biểu diễn (chẳng hạn chuỗi phân tách bằng dấu cách theo hồ sơ OAuth đang dùng) và quan hệ với luật phân quyền nghiệp vụ. Không giả định `scope`, `scp`, `roles`, `permissions` là các tên đồng nghĩa ở mọi nhà phát hành.

### Nguyên tắc triển khai ở bên nhận

1. Chỉ lấy dữ liệu phân quyền từ **token đã được kiểm tra đầy đủ**, không từ phần payload vừa giải mã rồi tin ngay.
2. Ràng buộc issuer, audience, loại token và các thuật toán được chấp nhận theo cấu hình; không chọn thuật toán tin cậy dựa riêng trên đề xuất từ token.
3. Kiểm tra kiểu dữ liệu và sự hiện diện của từng claim bắt buộc. Giá trị thiếu, sai kiểu hoặc không có ngữ nghĩa hợp lệ phải được xử lý rõ ràng, thường là từ chối truy cập.
4. Tách kiểm tra **phạm vi token** khỏi kiểm tra **quyền trên tài nguyên**. Mọi điểm truy cập dữ liệu nhạy cảm phải áp dụng chính sách cần thiết.
5. Giữ payload nhỏ, giảm dữ liệu cá nhân và tài liệu hóa thay đổi của hợp đồng để các bên phát hành/tiêu thụ không diễn giải sai.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Claim trong JWT là dữ liệu chắc chắn đúng vì có chữ ký.” | Chữ ký bảo vệ tính toàn vẹn và xác minh nguồn ký; dữ liệu còn phải được chấp nhận từ đúng issuer, đúng mục đích và có thể đã lỗi thời. |
| “Có `role=admin` là được làm mọi việc.” | Cần xác định phạm vi của vai trò, chính sách của API và quyền trên tài nguyên cụ thể. |
| “Có `tenant_id` thì không cần kiểm tra tenant của dữ liệu.” | Phải ngăn truy cập chéo tenant bằng đối chiếu tenant, quyền chủ thể và tài nguyên. |
| “Dồn hết dữ liệu người dùng vào token giúp tránh mọi truy vấn.” | Payload phình to, lộ dữ liệu và dễ lỗi thời; chỉ đưa vào thông tin thực sự cần tại thời điểm sử dụng. |
| “Token còn hạn thì quyền luôn còn hiệu lực.” | Quyền, trạng thái tài khoản và tài nguyên có thể đổi trước `exp`; lựa chọn chiến lược cập nhật/thu hồi tương ứng. |
| “JWT bắt buộc phải có `roles` và `scope`.” | Chúng phụ thuộc hồ sơ token và hợp đồng giữa các hệ thống, không phải mọi JWT đều có. |

## 9. Tình huống tự kiểm tra

Một access token đã được xác minh có `sub = "user_42"`, `tenant_id = "tenant_17"`, `scope = "orders:read"`, thời hạn còn hiệu lực. Người dùng yêu cầu đọc đơn hàng `order_777`. Dữ liệu thực cho biết đơn thuộc `tenant_17`, nhưng chính sách mới chỉ cho phép chủ đơn hoặc nhân viên chăm sóc khách hàng đọc; `user_42` không thuộc hai nhóm này.

**Câu hỏi:** Có được trả dữ liệu đơn hàng không?

**Đáp án:** **Không.** Các claims cho biết ngữ cảnh và phạm vi được phát hành, nhưng chưa thỏa điều kiện phân quyền trên đơn hàng cụ thể. Nếu API chỉ kiểm tra JWT hợp lệ và `orders:read`, nó đã bỏ qua chính sách nghiệp vụ.

Khi thiết kế claims cho một hệ thống khác, hãy tự hỏi: *Bên nhận thật sự cần biết điều gì từ issuer, ai là nguồn sự thật của thông tin đó, thông tin tồn tại bao lâu và API còn phải kiểm tra những điều kiện nghiệp vụ nào?* Trả lời được bốn câu hỏi này là nền tảng để đưa claims vào đúng vai trò trong kiến trúc bảo mật.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa JWT Claims Set, các loại tên claim và registered claim names.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành bảo mật JWT, đặc biệt về kiểm tra thuật toán, audience, issuer và tránh nhầm lẫn giữa các loại token.
