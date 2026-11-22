# 3.9. Consent, prompt, max_age, login_hint và lựa chọn tài khoản

## Mục tiêu bài học

Trong một ứng dụng Spring Security đóng vai trò **OpenID Connect Relying Party (RP)**, việc chuyển người dùng sang OpenID Provider (OP) để đăng nhập chỉ là một phần của trải nghiệm xác thực. Ứng dụng còn cần kiểm soát **khi nào hỏi người dùng chấp thuận quyền**, **khi nào yêu cầu xác thực lại**, **khi nào cho chọn tài khoản**, và **có nên gợi ý sẵn danh tính đăng nhập hay không**.

Sau bài học, bạn có thể:

- Phân biệt **đồng ý cấp quyền (consent)**, **xác thực người dùng (authentication)** và **lựa chọn tài khoản (account selection)**.
- Giải thích ý nghĩa các giá trị của tham số OIDC `prompt`: `none`, `login`, `consent`, `select_account`.
- Dùng `max_age` và claim `auth_time` để diễn đạt yêu cầu về độ mới của lần xác thực.
- Hiểu cách `login_hint` ảnh hưởng đến giao diện đăng nhập mà không trở thành bằng chứng danh tính.
- Tùy biến Authorization Request trong **Spring Security OAuth 2.0 Client / OIDC Login** theo chính sách của ứng dụng.
- Nhận biết các lỗi, giới hạn và lưu ý bảo mật khi OP không thể đáp ứng yêu cầu.

## 1. Bối cảnh: đăng nhập không chỉ có một quyết định

Xét một ứng dụng **Customer Portal** viết bằng Spring Boot. Portal sử dụng một OP tương thích OpenID Connect để cho phép khách hàng đăng nhập.

Khi khách truy cập Portal, ứng dụng có thể cần những trải nghiệm khác nhau:

1. Khách đã đăng nhập tại OP từ trước; Portal muốn **tái sử dụng phiên SSO** để tránh yêu cầu nhập thông tin đăng nhập.
2. Khách muốn **đổi sang tài khoản khác** đang có tại OP, chẳng hạn từ tài khoản cá nhân sang tài khoản công việc.
3. Khách chuẩn bị thay đổi phương thức thanh toán; Portal yêu cầu **lần xác thực đủ gần thời điểm hiện tại**.
4. Portal cần truy cập thêm một phạm vi dữ liệu; khách phải có cơ hội **đồng ý cấp quyền** theo chính sách của OP.
5. Khách vừa nhập email tại Portal; Portal muốn chuyển email đó sang OP để **gợi ý ô đăng nhập**.

Các tình huống này tương ứng với các điều khiển nằm trong **OIDC Authorization Request** gửi từ RP đến OP. Chúng không có cùng ý nghĩa:

| Câu hỏi | Cơ chế thường liên quan | Ý nghĩa |
|---|---|---|
| Người dùng có cần tương tác lúc này không? | `prompt` | Điều khiển cách OP xử lý tương tác |
| Có yêu cầu hiện lại màn hình consent không? | `prompt=consent` | Đề nghị OP xin lại sự chấp thuận |
| Lần xác thực cuối có quá cũ không? | `max_age`, `auth_time` | Đặt và kiểm tra độ mới của authentication |
| Có nên gợi ý tài khoản nào? | `login_hint` | Gợi ý danh tính đầu vào cho OP |
| Có nên cho người dùng chọn tài khoản? | `prompt=select_account` | Đề nghị OP trình bày lựa chọn tài khoản |

**Điểm cốt lõi:** giao diện đăng nhập, màn hình cấp quyền và cơ chế xác thực lại là các bước khác nhau, dù OP có thể kết hợp chúng trong cùng một hành trình.

## 2. Consent trong OpenID Connect là gì?

### 2.1. Consent là quyết định cho phép chia sẻ hoặc cấp quyền

Trong OAuth 2.0 và OIDC, **consent** thường là tương tác tại Authorization Server/OP để người dùng chấp thuận cho một client nhận các quyền truy cập hoặc thông tin được yêu cầu.

Ví dụ, Portal yêu cầu:

~~~text
scope=openid profile email
~~~

OP có thể hiển thị thông báo tương đương:

> Customer Portal muốn biết danh tính của bạn và đọc một số thông tin hồ sơ, chẳng hạn tên và email.

Nếu người dùng chấp thuận, OP tiếp tục luồng ủy quyền theo chính sách. Nếu họ từ chối, OP có thể trả lỗi `access_denied` về redirect URI của client.

**Consent không đồng nghĩa với authentication:**

- **Authentication:** OP xác định ai là người dùng, bằng mật khẩu, passkey, MFA hoặc phương thức khác.
- **Consent:** người dùng/OP quyết định cho phép client nhận quyền hoặc thông tin nào.
- **Authorization tại Resource Server:** API kiểm tra access token và quyền thực tế để cho phép hoặc từ chối thao tác.

Đã đăng nhập không có nghĩa đã đồng ý mọi scope; đã consent cũng không tự động có nghĩa người dùng được phân quyền thực hiện mọi nghiệp vụ tại Portal.

### 2.2. Vì sao có lúc không thấy màn hình consent?

Không phải mọi lần Authorization Request đều dẫn tới một màn hình hỏi quyền. OP có thể bỏ qua giao diện consent vì:

- Người dùng đã cấp cùng phạm vi quyền cho client ở lần trước.
- Client thuộc nhóm ứng dụng nội bộ được quản trị viên phê duyệt trước theo chính sách của OP.
- Chính sách của nhà cung cấp cho phép xử lý một số scope mà không cần hỏi riêng trong lần truy cập đó.
- OP sử dụng cách thức ghi nhận sự chấp thuận khác đã được thiết lập.

Điều này **không** chứng minh ứng dụng không dùng OAuth 2.0/OIDC. Sự xuất hiện của màn hình consent do sự kết hợp giữa yêu cầu của client, scope, trạng thái cấp quyền trước đó và chính sách của OP quyết định.

### 2.3. Consent liên quan đến scope, nhưng scope không phải quyền nghiệp vụ

OIDC định nghĩa một số scope quen thuộc:

| Scope | Mục đích điển hình |
|---|---|
| `openid` | Chỉ ra yêu cầu dùng OIDC; cần có để nhận ID token theo luồng phù hợp |
| `profile` | Yêu cầu các claim hồ sơ như tên, tên hiển thị... tùy chính sách OP |
| `email` | Yêu cầu các claim email |
| `phone` | Yêu cầu các claim số điện thoại |
| `address` | Yêu cầu các claim địa chỉ |
| `offline_access` | Yêu cầu cơ chế truy cập khi người dùng không hiện diện, thường liên quan refresh token, nếu OP cho phép |

Không thể suy ra rằng scope luôn trả đủ mọi claim; một số claim có thể được cung cấp qua **UserInfo Endpoint**, và OP vẫn áp dụng chính sách phát hành.

Scope của API tùy nhà cung cấp, chẳng hạn `orders.read` hay `payments.write`, không tự biến thành các quyền Spring Security trong ứng dụng. Portal vẫn cần xác định người dùng được phép làm gì với dữ liệu nội bộ của chính mình.

### 2.4. Yêu cầu consent lại bằng `prompt=consent`

Ví dụ một Authorization Request có:

~~~text
prompt=consent
~~~

Giá trị `consent` yêu cầu OP **nhắc người dùng thể hiện sự đồng ý** trước khi trả kết quả ủy quyền, ngay cả khi trước đó đã có phiên đăng nhập hoặc grant. Theo OIDC, OP nên hỏi lại; hành vi giao diện cụ thể còn phụ thuộc vào khả năng và chính sách của OP.

Các tình huống phù hợp:

- Ứng dụng vừa yêu cầu **scope bổ sung** mà trước đây chưa có.
- Một luồng nghiệp vụ cần người dùng xem lại quyền chia sẻ dữ liệu.
- Chính sách của provider yêu cầu xác nhận rõ ràng với quyền nhạy cảm.

Không nên gắn `prompt=consent` cho mọi lượt mở trang nếu không có nhu cầu: người dùng có thể gặp consent lặp lại, gây khó chịu hoặc không hoàn thành được luồng khi OP không hỗ trợ trải nghiệm tương ứng.

Với `offline_access`, OP có thể yêu cầu cơ chế consent phù hợp hoặc điều kiện cấp refresh token riêng. **Yêu cầu `offline_access` hay `prompt=consent` không bảo đảm sẽ nhận refresh token**; kết quả phụ thuộc grant, kiểu client và chính sách OP.

## 3. Tham số `prompt`: ứng dụng yêu cầu OP xử lý tương tác thế nào?

`prompt` là tham số chuẩn của OIDC Authentication Request. Giá trị là một tập các từ khóa phân tách bằng **dấu cách**. Các giá trị cơ bản:

| Giá trị | RP yêu cầu OP làm gì? | Khi thường dùng |
|---|---|---|
| `none` | Không hiển thị bất kỳ giao diện xác thực/consent tương tác nào; nếu không đáp ứng được thì trả lỗi | Kiểm tra khả năng SSO âm thầm trong ngữ cảnh phù hợp |
| `login` | Yêu cầu người dùng xác thực lại | Truy cập hoạt động có độ nhạy cao, đổi phiên xác thực |
| `consent` | Yêu cầu OP nhắc người dùng chấp thuận cấp quyền | Xin thêm scope hoặc cần xác nhận quyền |
| `select_account` | Yêu cầu OP cho chọn tài khoản | Người dùng muốn chuyển tài khoản đăng nhập |

### 3.1. `prompt=none` — không cho phép tương tác

Khi nhận `prompt=none`, OP **không được** đưa ra bước tương tác với người dùng. Nếu OP không thể trả một kết quả thành công mà không cần tương tác, nó trả lỗi thích hợp.

Các tình huống thường dẫn đến lỗi:

- Chưa có phiên đăng nhập hợp lệ tại OP: `login_required`.
- Cần người dùng tương tác để đáp ứng yêu cầu: `interaction_required`.
- Chưa có consent cần thiết: `consent_required`.
- Cần người dùng chọn tài khoản: `account_selection_required`.

Các mã lỗi nêu trên là lỗi theo OIDC; OP có thể phát sinh mã phù hợp với tình huống và mức hỗ trợ của mình.

**Không được kết hợp `none` với bất kỳ giá trị `prompt` nào khác.** Ví dụ `prompt=none%20login` là yêu cầu không hợp lệ về mặt ngữ nghĩa.

`prompt=none` không có nghĩa là “đăng nhập mà không cần kiểm tra bảo mật”. Nó yêu cầu OP **chỉ thành công khi đã đủ điều kiện để xử lý không tương tác**. Các cơ chế SSO âm thầm phụ thuộc vào phiên/cookie và khả năng trình duyệt; chặn cookie bên thứ ba hoặc giới hạn iframe có thể khiến phương án silent authentication trong iframe không hoạt động ổn định. Trong ứng dụng web hiện đại, cần có phương án chuyển hướng đăng nhập tương tác bình thường khi cần.

### 3.2. `prompt=login` — yêu cầu xác thực lại

`prompt=login` đề nghị OP xác thực lại người dùng, ngay cả khi browser đang có phiên SSO. “Xác thực lại” **không nhất thiết là nhập lại mật khẩu**: OP có thể áp dụng passkey, MFA hoặc cơ chế khác.

Theo OIDC, OP nên thực hiện tái xác thực; nếu không thể, OP phải trả lỗi phù hợp. Tuy nhiên, chỉ dựa vào việc URL chứa `prompt=login` để kết luận lần xác thực mới thực sự xảy ra là chưa đủ cho một thao tác có yêu cầu bảo mật cao.

Đối với chính sách **“xác thực trong vòng N giây gần đây”**, `max_age` kết hợp kiểm tra `auth_time` cung cấp thông tin rõ hơn về thời điểm xác thực, trình bày ở phần tiếp theo.

### 3.3. `prompt=consent` — yêu cầu chấp thuận lại

`prompt=consent` liên quan đến quyền mà client yêu cầu, **không ép người dùng phải nhập lại mật khẩu**. OP có thể đang biết rõ danh tính người dùng nhưng vẫn cần họ xác nhận quyền chia sẻ.

Nếu kết hợp:

~~~text
prompt=login consent
~~~

RP yêu cầu cả xác thực lại **và** hiển thị consent. Các từ trong giá trị `prompt` được phân tách bằng dấu cách; khi đưa vào URL phải URL-encode:

~~~text
prompt=login%20consent
~~~

Không dùng dấu phẩy (`login,consent`) làm ký hiệu phân tách chuẩn.

### 3.4. `prompt=select_account` — yêu cầu chọn tài khoản

Khi một người dùng có nhiều tài khoản được OP nhận biết, `select_account` đề nghị OP đưa ra khả năng chọn tài khoản, thay vì mặc định sử dụng tài khoản SSO hiện tại.

Ví dụ:

~~~text
prompt=select_account
~~~

Theo OIDC, OP nên hỏi người dùng chọn tài khoản. Nếu không thể làm được, OP có thể trả lỗi `account_selection_required`. Trải nghiệm thực tế phụ thuộc OP: provider có thể hiển thị danh sách tài khoản, ô nhập username, hay một hình thức lựa chọn khác.

**RP không được xem `prompt=select_account` là bằng chứng người dùng đã chọn một tài khoản cụ thể.** Sau callback, RP phải dựa trên ID token hợp lệ và định danh `iss` + `sub` để xác định ai vừa đăng nhập.

### 3.5. Kết hợp các giá trị `prompt`

Có thể kết hợp một số giá trị, ngoại trừ `none` phải đứng độc lập:

| Yêu cầu | Ví dụ |
|---|---|
| Xác thực lại và hỏi consent | `prompt=login consent` |
| Cho chọn tài khoản rồi hỏi consent | `prompt=select_account consent` |
| Cho chọn tài khoản và xác thực lại | `prompt=select_account login` |
| Xử lý không cần tương tác | `prompt=none` |

Một số provider không hỗ trợ đầy đủ mọi giá trị hoặc cách kết hợp. Client cần kiểm tra tài liệu/metadata của OP; phản hồi lỗi là kết quả giao thức cần được xử lý, không nên mặc định các lựa chọn luôn được đáp ứng.

## 4. `max_age`: độ mới của sự kiện xác thực

### 4.1. `max_age` đo điều gì?

`max_age` là số nguyên biểu diễn **số giây tối đa có thể trôi qua từ lần OP chủ động xác thực người dùng** đến thời điểm yêu cầu OIDC mà RP cho phép.

Ví dụ:

~~~text
max_age=300
~~~

Portal yêu cầu lần xác thực tại OP đủ mới theo ngưỡng **5 phút**. Nếu lần xác thực trước đã quá ngưỡng, OP cần xử lý việc xác thực lại để đáp ứng yêu cầu.

Một số ví dụ:

| Giá trị | Ý nghĩa |
|---|---|
| `max_age=0` | Yêu cầu xác thực tích cực lại, kể cả khi người dùng đã đăng nhập trước đó |
| `max_age=300` | Giới hạn độ cũ của lần xác thực trong khoảng 5 phút |
| `max_age=900` | Giới hạn trong khoảng 15 phút |

Điểm cần phân biệt: `max_age` nói về **authentication freshness**, không nói về thời gian sống của HTTP session tại RP và **không** thay đổi trực tiếp TTL của access token hoặc ID token.

### 4.2. Vai trò bắt buộc của claim `auth_time`

Khi Authentication Request có tham số `max_age`, **ID token trả về phải có claim `auth_time`** theo OIDC Core. `auth_time` là thời điểm OP đã xác thực người dùng, biểu diễn bằng số giây từ Unix epoch.

Ví dụ payload ID token đã được rút gọn:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "user-9841",
  "aud": "portal-web",
  "iat": 1760000900,
  "exp": 1760004500,
  "auth_time": 1760000700
}
~~~

**`iat` không thay thế `auth_time`.**

- `iat`: thời điểm **ID token được phát hành**.
- `auth_time`: thời điểm **người dùng thực sự được xác thực** tại OP.

Một người dùng có thể đã xác thực từ lâu nhưng vừa được phát hành ID token mới; chỉ nhìn `iat` sẽ không biết sự kiện xác thực đã quá cũ hay chưa.

Đối với tác vụ nhạy cảm, RP cần kiểm tra ID token hợp lệ và áp chính sách độ mới dựa trên `auth_time`. Nếu `auth_time` không có dù RP đã yêu cầu `max_age`, hoặc không thỏa ngưỡng chấp nhận, ứng dụng không nên tự coi yêu cầu xác thực mới đã được đáp ứng.

Ví dụ chính sách bằng lời:

> Chỉ cho phép thay đổi phương thức thanh toán khi `auth_time` nằm trong 5 phút gần nhất, xét độ lệch đồng hồ cho phép và quy tắc xác minh token.

Thông thường RP cũng cần đảm bảo cơ chế kích hoạt lại OIDC Authentication Request khi ngưỡng không đạt; việc có phiên Spring Security tại Portal **không tự động khiến browser bắt đầu một luồng xác thực mới** mỗi khi người dùng mở màn hình nhạy cảm.

### 4.3. `max_age=0` và `prompt=login` giống, khác nhau ở đâu?

Cả hai đều có thể khiến OP yêu cầu xác thực lại, nhưng khác ở mức thông tin có thể kiểm tra:

- `prompt=login` diễn đạt yêu cầu **hành vi tương tác**: hãy xác thực lại.
- `max_age=0` đặt ngưỡng độ mới rất chặt, dẫn đến yêu cầu tái xác thực và làm phát sinh nghĩa vụ có `auth_time` trong ID token.
- `max_age=300` cho phép dùng kết quả xác thực đủ gần đây, kể cả khi không cần đưa người dùng trở lại màn hình nhập thông tin đăng nhập.

Trong hệ thống cần chứng minh độ mới của xác thực, nên thiết kế dựa trên `max_age` + `auth_time`, cùng việc kiểm tra token đúng chuẩn. Có thể kết hợp `prompt=login` theo trải nghiệm mong muốn, nhưng nó không thay thế kiểm tra độ mới.

### 4.4. `max_age` không tương đương thời gian hết hạn phiên SSO

Giả sử OP có phiên SSO kéo dài nhiều giờ. Portal yêu cầu `max_age=300`:

- Nếu OP xác thực người dùng cách đây 2 phút, có thể sử dụng phiên hiện tại.
- Nếu OP xác thực người dùng cách đây 20 phút, OP cần xác thực lại theo yêu cầu.
- Sau khi Portal đăng nhập, HTTP session của Portal có thể có thời hạn khác với phiên SSO của OP.

Mỗi lớp có đồng hồ và quy tắc riêng: **OP authentication**, **RP session**, **ID token**, **access token**, **refresh token**. Không nên dùng thời điểm hết hạn token như đại diện cho thời điểm người dùng vừa xác thực.

## 5. `login_hint`: gợi ý tài khoản, không phải khẳng định danh tính

`login_hint` là một chuỗi mà RP gửi đến OP để **gợi ý người dùng có thể muốn đăng nhập bằng tài khoản nào**.

Ví dụ:

~~~text
login_hint=alice%40example.com
~~~

OP có thể dùng gợi ý này để điền trước email, chọn sẵn account, hoặc giảm bước nhập username. Tuy nhiên:

- Đây chỉ là **hint**, không phải yêu cầu bắt buộc OP phải dùng.
- OP có thể bỏ qua, biến đổi hoặc xử lý theo cách riêng.
- RP **không được** coi `login_hint` là bằng chứng người dùng thực sự đã xác thực dưới danh tính đó.
- Sau callback, định danh đáng tin cậy phải được lấy từ **ID token đã xác minh**, thông thường là cặp `iss` + `sub`.

### 5.1. Kịch bản sử dụng thích hợp

Ví dụ Portal có bước nhập email để tìm lựa chọn đăng nhập doanh nghiệp. Người dùng nhập `alice@example.com`; Portal chuyển hướng đến OP kèm `login_hint`. OP có thể hiển thị sẵn địa chỉ này, nhưng người dùng vẫn thực hiện xác thực theo quy trình OP.

`login_hint` giúp **cải thiện trải nghiệm**, không thay thế việc xác minh quyền sở hữu email hay việc kiểm tra ID token.

### 5.2. Lưu ý bảo mật và quyền riêng tư

Email hoặc mã định danh trong `login_hint` có thể xuất hiện trong URL chuyển hướng và có thể bị ghi trong lịch sử trình duyệt, proxy hoặc log nếu hệ thống cấu hình không phù hợp. Vì vậy:

- Chỉ gửi dữ liệu cần thiết, được người dùng hoặc quy trình hợp lệ cung cấp.
- Không đưa mật khẩu, access token, mã OTP hay bí mật khác vào `login_hint`.
- URL-encode giá trị bằng thư viện xử lý URI đúng cách.
- Không tự động tin một `login_hint` do browser truyền đến để liên kết/đổi tài khoản nội bộ.
- Tránh lưu Authorization Request đầy đủ chứa dữ liệu nhạy cảm vào log ứng dụng.

### 5.3. `login_hint` khác `id_token_hint`

OIDC còn có tham số `id_token_hint` để gợi ý thông tin về **một phiên xác thực/End-User đã biết qua ID token**. Đây là thông tin khác với chuỗi tài khoản nhập tay của `login_hint`.

| Tham số | Dữ liệu điển hình | Mục đích |
|---|---|---|
| `login_hint` | Email, username hoặc định danh mà OP hiểu | Gợi ý tài khoản cho giao diện xác thực |
| `id_token_hint` | ID token đã phát hành trước đó | Gợi ý cho OP về End-User/phiên liên quan theo ngữ cảnh OIDC |

Không nên nhầm `id_token_hint` với access token; khi dùng cần tuân thủ yêu cầu của OP và tránh làm lộ token. Cả hai tham số đều **không cho RP bỏ qua việc xác thực kết quả callback mới**.

## 6. Lựa chọn tài khoản trong ứng dụng có SSO

### 6.1. Tại sao “chọn tài khoản” là bài toán riêng?

Một trình duyệt có thể nhớ nhiều tài khoản tại OP. Nếu Portal chỉ khởi động luồng OIDC mặc định, OP có thể dùng ngay phiên SSO hiện tại.

Điều này thuận tiện khi người dùng muốn tiếp tục tài khoản cũ, nhưng dễ gây nhầm nếu họ muốn mở Portal bằng tài khoản khác. `prompt=select_account` đề nghị OP để họ lựa chọn.

Ví dụ:

- Trên OP có tài khoản `alice@company.example` và `alice.personal@example.com`.
- Người dùng muốn mở Portal với tài khoản công việc.
- Portal khởi động OIDC Authorization Request có `prompt=select_account`.
- OP thực hiện chọn tài khoản theo khả năng của mình.
- Portal nhận callback, kiểm tra ID token và lập phiên cục bộ theo **`iss` + `sub` của tài khoản thực tế**.

Cần tách biệt **nhãn hiển thị** với **khóa danh tính**. Email có thể đổi hoặc không được OP xác nhận; `sub` trong phạm vi issuer mới phù hợp hơn để xác định tài khoản đã đăng nhập.

### 6.2. Đổi tài khoản tại OP và tại Portal không tự động đồng bộ

Có ít nhất hai loại trạng thái:

1. **Phiên đăng nhập tại Portal (RP):** thông thường chứa `SecurityContext` và trạng thái phiên servlet.
2. **Phiên SSO tại OP:** do OP quản lý, có thể tồn tại độc lập với phiên Portal.

Nếu người dùng bấm “Đổi tài khoản”:

- Portal cần quyết định cách kết thúc hoặc thay thế phiên cục bộ hiện tại để tránh giữ nhầm dữ liệu của người dùng cũ.
- Khởi động một yêu cầu đăng nhập OIDC mới với `prompt=select_account` nếu OP hỗ trợ.
- Khi callback thành công, kiểm tra định danh nhận được và thiết lập trạng thái ứng dụng theo tài khoản mới.
- Làm rõ cách lưu các `OAuth2AuthorizedClient`/token theo principal để không gửi token của tài khoản A khi đã chuyển sang B.
- Xử lý trường hợp người dùng hủy hoặc OP trả lỗi mà không vô tình liên kết dữ liệu giữa hai tài khoản.

**Không nên giả định** rằng gọi endpoint logout của Portal sẽ đăng xuất toàn bộ tài khoản trên OP. Nếu nghiệp vụ cần đăng xuất tại OP, phải dùng cơ chế logout OIDC được OP hỗ trợ và xử lý chính sách phiên rõ ràng.

### 6.3. Chỉ truyền `login_hint` không phải là cơ chế đổi tài khoản

Giả sử Portal gửi:

~~~text
login_hint=bob%40example.com
~~~

Nhưng OP đang có phiên SSO cho Alice. OP có thể bỏ qua hint và trả về Alice nếu chính sách cho phép. Vì vậy, khi mục đích là **để người dùng chọn tài khoản**, hãy dùng `prompt=select_account` khi phù hợp và **kiểm tra principal thực tế sau callback**; đừng dùng `login_hint` như lệnh ép đổi sang Bob.

## 7. Authorization Request hoàn chỉnh

Một ví dụ OIDC Authorization Code Request có lựa chọn tài khoản, giới hạn độ mới và gợi ý email:

~~~http
GET /authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorp&scope=openid%20profile%20email&state=RANDOM_STATE&nonce=RANDOM_NONCE&prompt=select_account&max_age=300&login_hint=alice%40example.com&code_challenge=RANDOM_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

Các thành phần chính:

| Tham số | Vai trò |
|---|---|
| `response_type=code` | Chọn luồng Authorization Code |
| `client_id` | Định danh RP/OAuth client đã đăng ký |
| `redirect_uri` | Callback đã đăng ký tại OP |
| `scope=openid ...` | Yêu cầu OIDC và các scope bổ sung |
| `state` | Liên kết request và callback; hỗ trợ chống CSRF |
| `nonce` | Liên kết ID token với yêu cầu xác thực theo cơ chế OIDC |
| `code_challenge` / `code_challenge_method` | Thành phần PKCE để bảo vệ việc trao đổi authorization code |
| `prompt` | Yêu cầu về tương tác với người dùng |
| `max_age` | Giới hạn độ cũ của lần xác thực tại OP |
| `login_hint` | Gợi ý tài khoản đăng nhập |

`RANDOM_STATE`, `RANDOM_NONCE` và `RANDOM_CHALLENGE` chỉ là placeholder minh họa. Trong ứng dụng thực, để Spring Security tạo và quản lý các giá trị bảo mật này theo luồng chuẩn; không dùng chuỗi cố định hoặc tự thiết kế callback thiếu kiểm tra.

### 7.1. Những gì được xử lý tại OP và tại RP

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant RP as Spring Boot RP
    participant OP as OpenID Provider
    User->>Browser: Chọn đăng nhập/đổi tài khoản
    Browser->>RP: GET /oauth2/authorization/corp
    RP-->>Browser: Redirect Authorization Request (prompt, max_age, login_hint...)
    Browser->>OP: Yêu cầu xác thực OIDC
    OP->>User: Xác thực, consent, chọn tài khoản nếu cần
    OP-->>Browser: Redirect với code và state hoặc error
    Browser->>RP: Callback tại /login/oauth2/code/corp
    RP->>OP: Trao đổi code lấy token
    OP-->>RP: ID token và token khác theo luồng
    Note over RP: Xác minh ID token, auth_time nếu cần, định danh iss + sub
    RP-->>Browser: Thiết lập phiên và trả nội dung Portal
~~~

`prompt`, `max_age` và `login_hint` là tham số gửi **trong bước authorization**. Chúng không phải header gửi kèm mọi lần gọi API, cũng không phải giá trị RP có thể thay đổi sau khi đã nhận ID token rồi mong OP tự áp dụng ngược trở lại.

## 8. Tích hợp trong Spring Security OAuth 2.0 OIDC Client

### 8.1. Cấu hình client registration

Thêm dependency OAuth 2.0 Client cho ứng dụng Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/company
~~~

Đây là ví dụ **confidential web client** lưu secret phía server. `issuer-uri` cho phép Spring Security sử dụng metadata discovery của OP tương thích; URI và thông tin client phải được cấu hình đúng tại nhà cung cấp.

Đăng nhập bằng registration `corp` thường được khởi tạo qua:

~~~text
/oauth2/authorization/corp
~~~

Callback mặc định theo cấu hình ví dụ:

~~~text
/login/oauth2/code/corp
~~~

### 8.2. Thêm `prompt` và `max_age` bằng Authorization Request Resolver

Spring Security có `DefaultOAuth2AuthorizationRequestResolver` để xây dựng Authorization Request. Có thể bọc resolver mặc định rồi bổ sung tham số OIDC, giữ nguyên các dữ liệu mà framework đã tạo như `state`, `redirect_uri`, `nonce` và PKCE (nếu được cấu hình/sử dụng).

Ví dụ **chính sách áp dụng cho toàn bộ đăng nhập OIDC của ứng dụng minh họa**: hỏi chọn tài khoản và yêu cầu authentication trong 5 phút gần đây.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver delegate =
                new DefaultOAuth2AuthorizationRequestResolver(
                        clientRegistrations,
                        OAuth2AuthorizationRequestRedirectFilter
                                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);

        OAuth2AuthorizationRequestResolver resolver =
                new OAuth2AuthorizationRequestResolver() {

                    @Override
                    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
                        return customize(delegate.resolve(request));
                    }

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request, String registrationId) {
                        return customize(delegate.resolve(request, registrationId));
                    }
                };

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }

    private static OAuth2AuthorizationRequest customize(
            OAuth2AuthorizationRequest original) {

        if (original == null || !original.getScopes().contains("openid")) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(parameters -> {
                    parameters.put("prompt", "select_account");
                    parameters.put("max_age", "300");
                })
                .build();
    }
}
~~~

Giải thích:

1. `delegate.resolve(...)` giữ cách Spring Security xác định client registration, redirect URI, scope và dữ liệu bảo vệ luồng.
2. `OAuth2AuthorizationRequest.from(original)` tạo builder từ request đã hình thành để chỉ bổ sung những tham số cần thiết.
3. `additionalParameters(...)` đưa `prompt` và `max_age` vào Authorization Request gửi đến OP.
4. Kiểm tra scope `openid` giới hạn tùy biến cho request OIDC.
5. Khi callback, Spring Security vẫn xử lý Authorization Code/OIDC Login theo cơ chế chuẩn của framework.

Đoạn code sử dụng các API servlet của Spring Security 6 và Java chạy với `jakarta.servlet`. Trong môi trường có nhiều provider hoặc nhiều loại luồng, nên áp chính sách theo **registrationId/luồng nghiệp vụ** thay vì tự động đặt `select_account` cho mọi lần đăng nhập.

### 8.3. Thay chính sách theo hành trình của người dùng

Không phải thao tác nào cũng cần cùng bộ tham số:

| Hành trình | Ý định | Ví dụ tham số |
|---|---|---|
| Đăng nhập thông thường | Dùng SSO nếu hợp lệ | Không bắt buộc thêm `prompt` |
| Người dùng bấm “Đổi tài khoản” | Cho chọn danh tính | `prompt=select_account` |
| Đổi dữ liệu nhạy cảm | Đòi hỏi xác thực đủ mới | `max_age=300`, kết hợp kiểm tra `auth_time` |
| Yêu cầu phạm vi quyền mới | Đề nghị cấp quyền | `prompt=consent` cùng scope phù hợp |
| Gợi ý email đã nhập | Giảm thao tác nhập | `login_hint=...` |
| Thử luồng không tương tác | Chỉ chấp nhận nếu không cần UI | `prompt=none` và xử lý lỗi phù hợp |

Với nhiều luồng, có thể viết một `OAuth2AuthorizationRequestResolver` tùy biến dựa trên route đã được kiểm soát hoặc dữ liệu phiên đáng tin cậy. **Không chuyển nguyên văn tùy ý các query parameter do người dùng gửi vào browser** thành `prompt`, `max_age` hay `login_hint` mà không có allowlist, kiểm tra giá trị và xác định chính sách.

Ví dụ, yêu cầu `?prompt=none` gắn vào URL Portal **không có nghĩa** Spring Security sẽ tự động chuyển nguyên vẹn giá trị đó sang OP. Chỉ khi ứng dụng chủ động tạo/thay đổi Authorization Request thì tham số mới được gửi.

### 8.4. Đọc `auth_time` sau khi đã đăng nhập

Trong Spring Security, principal OIDC có thể được truy cập dưới dạng `OidcUser`. Ví dụ endpoint để **quan sát** thời điểm xác thực mà OP đưa vào ID token:

~~~java
import java.time.Instant;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    @GetMapping("/session-info")
    SessionInfo sessionInfo(@AuthenticationPrincipal OidcUser user) {
        return new SessionInfo(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getIdToken().getAuthenticationTime());
    }

    record SessionInfo(String issuer, String subject, Instant authTime) {}
}
~~~

Trường `authTime` có thể `null` nếu request OIDC không yêu cầu trả claim đó. Khi chính sách yêu cầu `max_age`, RP cần đảm bảo có `auth_time` hợp lệ và kiểm tra ngưỡng tại thời điểm thực hiện thao tác nhạy cảm; **chỉ hiển thị thông tin này chưa phải là cơ chế phân quyền**.

Tùy phiên bản và cách tích hợp, framework xử lý nhiều kiểm tra ID token cơ bản, nhưng ứng dụng vẫn phải thiết kế việc **kích hoạt lại luồng đăng nhập và thực thi freshness policy của nghiệp vụ**. Không nên mặc định HTTP session còn sống đồng nghĩa `auth_time` luôn đủ mới.

## 9. Xử lý lỗi và tình huống biên

### 9.1. Người dùng từ chối consent

OP có thể trả về:

~~~text
error=access_denied
~~~

Portal cần hiển thị thông báo phù hợp và không coi thao tác xin quyền là thành công. Nếu phạm vi quyền mới là tùy chọn, ứng dụng có thể tiếp tục với chức năng giới hạn; nếu bắt buộc, phải giải thích tác vụ chưa thể thực hiện.

### 9.2. `prompt=none` không đáp ứng được

Ví dụ:

~~~text
error=login_required
~~~

hoặc:

~~~text
error=consent_required
~~~

Đây có thể là kết quả **bình thường của một phép kiểm tra silent SSO**. Ứng dụng không nên lặp lại vô hạn cùng request `prompt=none`. Nếu người dùng muốn tiếp tục, cần khởi động luồng đăng nhập tương tác phù hợp.

### 9.3. Người dùng chọn tài khoản khác tài khoản gợi ý

Nếu Portal truyền `login_hint=alice@example.com` nhưng OP xác thực Bob, Portal phải xử lý danh tính **Bob theo ID token hợp lệ**, không dùng hint của Alice để tra cứu dữ liệu và token của Alice. Nếu ứng dụng yêu cầu tài khoản cụ thể, cần áp quy tắc đối chiếu định danh tin cậy và từ chối hoặc hướng dẫn người dùng khi không khớp.

### 9.4. OP không hỗ trợ yêu cầu tương tác

Một số nhà cung cấp chỉ hỗ trợ tập con của các giá trị `prompt`, hoặc có hành vi khác nhau theo loại client, cấu hình tenant và chính sách đăng nhập. RP cần:

- Xem xét khả năng OP công bố trong tài liệu và metadata khi có.
- Xử lý callback lỗi đúng cơ chế của Spring Security; không coi mọi lỗi là thông tin đăng nhập sai.
- Tránh triển khai luồng “đổi tài khoản” dựa trên giả định chắc chắn OP luôn hiển thị màn hình chọn tài khoản.

### 9.5. Yêu cầu xác thực mới liên tục

Nếu Portal luôn gửi `max_age=0` cho mọi lượt truy cập hoặc bắt đầu xác thực mới ngay khi trang được tải lại, người dùng có thể bị điều hướng và xác thực lặp đi lặp lại. Hãy áp chính sách theo tác vụ cần bảo vệ và chỉ bắt đầu luồng tương tác mới khi thực sự cần.

## 10. Tình huống áp dụng

### Tình huống A: đổi tài khoản đang dùng

Người dùng đang đăng nhập Portal bằng tài khoản công việc, muốn chuyển sang tài khoản cá nhân.

**Thiết kế:** Portal cung cấp hành động “Đổi tài khoản”, chuẩn bị thay thế trạng thái đăng nhập cục bộ theo chính sách, rồi khởi động OIDC Login với `prompt=select_account`. Sau callback, Portal lấy `iss` + `sub` của ID token hợp lệ để thiết lập tài khoản thực tế.

**Tránh:** chỉ gửi `login_hint` khác rồi tự đổi user nội bộ khi chưa xác minh callback.

### Tình huống B: xác nhận lại trước khi thay đổi mật khẩu hoặc phương thức thanh toán

Portal yêu cầu người dùng vừa xác thực trong **5 phút**.

**Thiết kế:** Khi cần thiết, bắt đầu yêu cầu OIDC mới với `max_age=300`. Sau khi OP trả về, kiểm tra ID token hợp lệ và thời điểm `auth_time` theo quy tắc thời gian của hệ thống, rồi mới cho phép thao tác. Cần tránh để một HTTP session cũ vượt qua chính sách freshness.

**Tránh:** dùng `iat` của ID token mới thay cho `auth_time`, hoặc giả định `prompt=login` tự đủ để chứng minh chính sách 5 phút.

### Tình huống C: xin thêm quyền đọc hồ sơ

Portal đã có phiên đăng nhập nhưng cần một scope mới.

**Thiết kế:** Tạo Authorization Request với các scope cần thiết và yêu cầu consent nếu chính sách OP/ứng dụng cần, chẳng hạn `prompt=consent`. Xử lý trường hợp người dùng từ chối. Chỉ gọi API bằng access token có quyền phù hợp.

**Tránh:** coi ID token hoặc sự hiện diện của màn hình consent như bằng chứng đã có quyền truy cập API.

### Tình huống D: chuyển email đã nhập sang OP

Người dùng nhập email trước khi bấm nút đăng nhập.

**Thiết kế:** Xác thực định dạng đầu vào ở mức phù hợp, mã hóa đúng khi tạo URL và gửi `login_hint`. Sau callback, Portal phải xác định danh tính theo token đã kiểm tra.

**Tránh:** dùng email ở `login_hint` làm khóa xác định người dùng ngay cả khi claim của ID token cho thấy một chủ thể khác.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Portal muốn không hiển thị bất kỳ bước tương tác nào và chấp nhận lỗi nếu OP không thể xử lý âm thầm. Nên yêu cầu gì?

**Đáp án:** `prompt=none`. Cần xử lý các lỗi như `login_required` hoặc `consent_required` và có hướng chuyển sang tương tác khi phù hợp.

**Câu 2.** Portal muốn người dùng được xác thực gần đây; vì sao không chỉ dùng thời điểm phát hành ID token?

**Đáp án:** `iat` chỉ là thời điểm phát hành token, còn `auth_time` là thời điểm OP xác thực người dùng. Dùng `max_age` và kiểm tra `auth_time` cho chính sách độ mới.

**Câu 3.** Có thể gửi `prompt=none login` để OP im lặng thử SSO rồi hiển thị login khi không được không?

**Đáp án:** Không. `none` không được đi cùng giá trị `prompt` khác. Hai trải nghiệm phải được điều phối bằng các yêu cầu riêng theo phản hồi của OP.

**Câu 4.** Portal gửi `login_hint=alice@example.com` nhưng ID token hợp lệ trả về `sub` của Bob. Ai là người vừa đăng nhập?

**Đáp án:** Danh tính được xác định theo `iss` và `sub` trong ID token đã kiểm tra. `login_hint` chỉ là gợi ý và không chứng minh Alice đã đăng nhập.

**Câu 5.** Người dùng đã đăng nhập, nhưng ứng dụng muốn họ chấp thuận thêm một scope. Tham số nào phù hợp?

**Đáp án:** Có thể yêu cầu `prompt=consent` cùng scope cần xin. OP quyết định cách thể hiện consent theo chính sách; ứng dụng cần xử lý từ chối.

## Ghi nhớ

- **Consent** là sự chấp thuận về phạm vi quyền/thông tin; khác với hành vi xác thực danh tính.
- **`prompt`** định hướng tương tác tại OP: `none`, `login`, `consent` và `select_account`. Giá trị `none` phải đứng một mình.
- **`max_age`** yêu cầu độ mới của xác thực tính bằng giây; **`auth_time`** trong ID token cho phép RP kiểm tra thời điểm thực tế mà OP xác thực người dùng.
- **`login_hint`** chỉ giúp gợi ý đầu vào, tuyệt đối không thay thế danh tính đã xác minh qua **`iss` + `sub`**.
- Trong **Spring Security**, có thể bổ sung các tham số này qua `OAuth2AuthorizationRequestResolver`, đồng thời duy trì luồng OIDC Authorization Code chuẩn và áp chính sách theo hành trình nghiệp vụ.
