# Đích đến an toàn của liên kết khôi phục tài khoản

## 1. Recovery link destination là gì?

Trong chương **Email Link Recovery**, liên kết được gửi qua email đưa người dùng tới một trang của hệ thống để tiếp tục khôi phục tài khoản. **Recovery link destination** là đích URL mà liên kết đó mở ra, cùng cách hệ thống kiểm soát việc điều hướng từ trang này đến bước tiếp theo.

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Địa chỉ nhận email | Thông báo được gửi đến hộp thư nào? | Email khôi phục đã được đăng ký và xác minh |
| Đích của liên kết | Bấm vào liên kết sẽ mở origin và đường dẫn nào? | https://accounts.example.invalid/account-recovery/email |
| Đích sau khi hoàn tất | Người dùng được đưa đi đâu khi thao tác kết thúc? | Trang đăng nhập cố định của sản phẩm |

Gửi đến đúng hộp thư chưa bảo đảm liên kết an toàn. Nếu máy chủ xây URL từ một Host giả hoặc chấp nhận callback tùy ý, token hợp lệ vẫn có thể bị chuyển đến hệ thống của kẻ tấn công.

Ngược lại, mở đúng tên miền chưa có nghĩa người mở liên kết được phép thực hiện mọi thao tác. Token phải gắn với tài khoản, tenant, mục đích và giao dịch cụ thể; quy trình có thể còn cần bằng chứng bổ sung.

Sau bài học, người học có thể:

- Xác định nguồn dữ liệu đáng tin để tạo URL khôi phục.
- Ngăn giả mạo Host và chuyển hướng mở.
- Thiết kế trang tiếp nhận không làm lộ token qua tài nguyên, log hoặc điều hướng.
- Phân biệt mở trang bằng GET, xác nhận bằng POST và hoàn tất khôi phục.
- Áp dụng nguyên tắc này cho nhiều tenant, nhiều giao diện và các tình huống mất mật khẩu, MFA hoặc passkey.

Các tên miền kết thúc bằng .invalid trong bài là địa chỉ minh họa, không phải dịch vụ thực tế.

## 2. Tình huống: email đúng, URL sai

Minh quên mật khẩu. Kẻ tấn công gửi một yêu cầu khởi tạo khôi phục cho email của Minh và tìm cách khiến dịch vụ dùng tên miền do mình kiểm soát khi xây liên kết.

Một cách xây dựng nguy hiểm là:

~~~text
link = "https://" + request.headers["Host"]
       + "/account-recovery/email?token=" + token
~~~

Nếu thành phần xử lý yêu cầu tin vào Host chưa được xác thực, email gửi tới Minh có thể chứa:

~~~text
https://attacker.example.invalid/account-recovery/email?token=SECRET
~~~

Khi Minh bấm, token được gửi đến máy chủ của kẻ tấn công. Việc token ngẫu nhiên, hết hạn nhanh hay chỉ được dùng một lần không ngăn lần sử dụng trái phép đầu tiên sau khi nó bị đánh cắp.

Một biến thể khác dùng đúng tên miền sản phẩm nhưng đi qua endpoint chuyển hướng:

~~~text
https://accounts.example.invalid/go
    ?next=https://attacker.example.invalid/collect
    &token=SECRET
~~~

Nếu endpoint chuyển hướng mang token sang đích ngoài, tên miền đúng ở đầu URL vẫn không bảo vệ được bí mật.

Vì vậy, phải kiểm soát cả **URL được tạo ban đầu** và **mọi bước chuyển hướng có thể xảy ra sau đó**.

## 3. Ranh giới tin cậy khi chọn đích

Nguồn quyết định đích nên là cấu hình hoặc registry do hệ thống quản lý. Định danh tenant và mục đích khôi phục được máy chủ xác định hợp lệ sẽ chọn một mục đã đăng ký.

~~~text
tenant hợp lệ + mục đích khôi phục
                |
                v
registry đích do hệ thống quản lý
                |
                v
origin HTTPS cố định + đường dẫn khôi phục cố định
                |
                v
bộ dựng URI thêm token theo hợp đồng
~~~

Các giá trị sau không được tự trở thành origin khôi phục:

- Host, Forwarded hoặc X-Forwarded-Host do khách tùy ý gửi.
- callbackUrl, redirectUri, returnTo hoặc next trong payload.
- Tên miền lấy bằng cách tách chuỗi email của người dùng.
- Một địa chỉ lấy từ nội dung email hoặc tham số của liên kết trước đó.
- Mã tenant chưa được kiểm tra hoặc một mục cấu hình do người chưa có quyền quản trị sửa.

Trong hạ tầng có reverse proxy, thông tin chuyển tiếp chỉ đáng tin khi proxy được xác định rõ, xử lý các header do khách tự đặt và truyền dữ liệu theo hợp đồng đã cấu hình. Dù vậy, cấu hình origin khôi phục riêng thường giúp đường đi của token dễ kiểm soát hơn việc suy ra origin từ từng yêu cầu.

Nếu không tìm thấy đích đã đăng ký, dừng phát hành liên kết cho luồng đó và báo lỗi vận hành nội bộ. Không tự fallback về Host hiện tại hoặc đích mà khách cung cấp.

## 4. Cấu trúc một đích được phép

Một đích web minh họa là:

~~~text
https://accounts.example.invalid/account-recovery/email?token=OPAQUE_TOKEN
|-----| |----------------------| |---------------------| |----------------|
 scheme          host                  path                  query
~~~

Trong thiết kế này:

- Scheme bắt buộc là HTTPS.
- Host và cổng được lấy từ cấu hình được phép.
- Path là route chuyên biệt cho tiếp nhận liên kết khôi phục.
- Query chỉ chứa dữ liệu theo hợp đồng, chẳng hạn token mờ.
- Không có thông tin đăng nhập dạng userinfo trong URL.
- Không có đích chuyển hướng bên ngoài hoặc script trong tham số.

**Origin** gồm scheme, host và cổng hiệu lực. Chỉ so sánh host mà bỏ qua scheme hoặc cổng có thể chấp nhận một dịch vụ khác với dịch vụ đã định.

### 4.1. So sánh URL bằng cấu trúc, không bằng cảm giác

Bảng sau giả định hệ thống chỉ cho phép origin https://accounts.example.invalid với cổng HTTPS mặc định và path /account-recovery/email.

| URL hoặc thành phần | Quyết định | Giải thích |
|---|---|---|
| https://accounts.example.invalid/account-recovery/email | Đúng đích cấu hình | Khớp origin và route |
| http://accounts.example.invalid/account-recovery/email | Từ chối làm liên kết phát hành | Token không được gửi qua HTTP |
| https://accounts.example.invalid.attacker.example.invalid/collect | Từ chối | Host thực tế khác host đã đăng ký |
| https://accounts.example.invalid@attacker.example.invalid/collect | Từ chối | Phần trước @ là userinfo; host là miền của kẻ tấn công |
| https://attacker.example.invalid/?site=accounts.example.invalid | Từ chối | Chuỗi tên miền xuất hiện trong query không xác định origin |
| //attacker.example.invalid/collect | Từ chối làm đích đầu vào | Đây là tham chiếu URL phụ thuộc scheme, không phải đích cố định đã đăng ký |
| https://accounts.example.invalid:8443/account-recovery/email | Từ chối nếu chưa đăng ký riêng | Cổng khác tạo origin khác |
| https://accounts.example.invalid/redirect?next=... | Từ chối làm route khôi phục mặc định | Route chuyển hướng không tương đương route tiếp nhận token |

Không dùng quy tắc “chuỗi có chứa tên miền sản phẩm” hoặc “bắt đầu bằng https://accounts.example.invalid” để xác định an toàn.

Nếu chấp nhận nhiều URL cấu hình, phân tích bằng thư viện URI/URL phù hợp rồi kiểm tra từng thành phần. Tập origin được phép cần chính xác, nhỏ và có người chịu trách nhiệm quản lý. Một wildcard cho toàn bộ tên miền con có thể đưa token đến tên miền con đã bị bỏ quên hoặc được giao cho hệ thống khác.

### 4.2. Chuẩn hóa có hợp đồng rõ ràng

Tên miền, cổng mặc định và các dạng mã hóa có thể có nhiều biểu diễn. Quy tắc chuẩn hóa phải được xác định ở thời điểm đăng ký cấu hình, không phải chuỗi thay thế tùy ý trong endpoint khôi phục.

Không chuyển toàn bộ URL thành chữ thường: đường dẫn và dữ liệu token có thể phân biệt chữ hoa với chữ thường. Không giải mã phần trăm nhiều lần hoặc ghép các đoạn URL đã được giải mã bằng các bộ phân tích khác nhau.

Đối với tên miền quốc tế, cấu hình cần có biểu diễn tên miền đã được kiểm tra và thống nhất cho so sánh cũng như vận hành. Tránh để hai thành phần hiểu cùng một chuỗi thành hai đích khác nhau.

## 5. Dựng liên kết từ registry cố định

Ví dụ Java dưới đây minh họa một registry rất nhỏ. Đích đã chứa sẵn cả origin và path, không lấy từ yêu cầu HTTP.

~~~java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Map;

public final class RecoveryLinkFactory {
    private static final Map<String, URI> TARGETS = Map.of(
        "tenant-blue",
        URI.create(
            "https://accounts-blue.example.invalid/account-recovery/email"
        ),
        "tenant-green",
        URI.create(
            "https://accounts-green.example.invalid/account-recovery/email"
        )
    );

    public static URI build(String trustedTenantId, String token) {
        URI target = TARGETS.get(trustedTenantId);
        if (target == null) {
            throw new IllegalArgumentException("No registered recovery target");
        }

        // Vi du nay dung token 32 byte, Base64 URL-safe khong padding.
        if (token == null || !token.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Invalid token representation");
        }

        try {
            return new URI(
                target.getScheme(),
                null,
                target.getHost(),
                target.getPort(),
                target.getPath(),
                "token=" + token,
                null
            );
        } catch (URISyntaxException e) {
            throw new IllegalStateException("Invalid recovery target", e);
        }
    }
}
~~~

Giới hạn biểu diễn trong ví dụ gắn với token 32 byte được mã hóa Base64 URL-safe không padding. Một hệ thống dùng biểu diễn khác phải có hợp đồng tương ứng. Khớp biểu thức định dạng không chứng minh token hợp lệ; phần kiểm tra token phải kiểm tra bản ghi, mục đích, hạn dùng và trạng thái.

Tên trustedTenantId thể hiện điều kiện đầu vào của hàm: lớp gọi đã xác định tenant hợp lệ và chọn giao dịch thuộc tenant đó. Một chuỗi do khách gửi không tự trở nên đáng tin vì được đặt tên như vậy.

Registry trong hệ thống thực tế có thể đến từ cấu hình triển khai. Khi đó cần kiểm tra cấu hình lúc nạp: HTTPS, host và cổng được phép, path được phép, không userinfo, không query hoặc fragment ngoài hợp đồng. Việc thay đổi đích cần chịu kiểm soát tương xứng với quyền chuyển nơi nhận bí mật khôi phục.

Ngoài dựng URI, khi đưa URL vào email HTML phải dùng cơ chế escape thuộc tính HTML đúng ngữ cảnh. URL encoding và HTML escaping giải quyết hai vấn đề khác nhau. Không đưa nguyên một chuỗi không tin cậy vào thuộc tính href.

## 6. Trang đích phải tiếp tục đúng giao dịch

Token trong liên kết là một bí mật có thể cấp quyền theo phạm vi. Trang đích phải tra cứu quan hệ đã được tạo ở máy chủ thay vì chọn tài khoản từ dữ liệu giao diện.

Một bản ghi liên quan có thể chứa:

~~~text
recovery_request_id
tenant_id
account_id
purpose
token_verifier
expires_at
status
account_security_version
~~~

token_verifier là dữ liệu kiểm tra token theo thiết kế lưu trữ; không có nghĩa phải lưu nguyên token bí mật.

Khi tiếp nhận token, máy chủ kiểm tra:

1. Token có biểu diễn và độ dài hợp lệ.
2. Token khớp dữ liệu kiểm tra được lưu.
3. Giao dịch thuộc tenant và route đang xử lý.
4. Mục đích token phù hợp với thao tác sẽ thực hiện.
5. Token chưa hết hạn, bị thu hồi hoặc được dùng trước đó.
6. Trạng thái bảo mật của tài khoản còn cho phép tiếp tục.
7. Bằng chứng bổ sung, nếu chính sách yêu cầu, đã được đáp ứng trước thao tác nhạy cảm.

Không chọn account_id theo một tham số email rồi chỉ kiểm tra rằng token “có tồn tại ở đâu đó”. Hai điều kiện đó chưa chứng minh token thuộc tài khoản đang bị tác động.

Tương tự, liên kết đặt lại mật khẩu không được mở route xóa MFA chỉ vì cùng một token có thể phân tích được ở cả hai nơi. Mất MFA hoặc passkey có thể cần quy trình bổ sung; kiểm soát đích không làm giảm yêu cầu xác minh đó.

## 7. Mở liên kết không đồng nghĩa tiêu thụ quyền khôi phục

Hệ thống email, bộ quét chống mã độc, trình xem trước hoặc cơ chế tải trước có thể truy cập liên kết trước người dùng. Vì vậy, một request GET đến trang khôi phục không phải bằng chứng về ý định hoàn tất.

Thiết kế nên tách rõ:

| Bước | Hành vi | Tác dụng được phép |
|---|---|---|
| GET trang đích | Mở trang, có thể kiểm tra không làm thay đổi trạng thái quyền | Hiển thị bước tiếp tục hoặc lỗi chung |
| POST có xác nhận | Người dùng chủ động tiếp tục theo giao diện và hợp đồng | Kiểm tra rồi đổi token lấy quyền khôi phục giới hạn nếu thiết kế dùng bước đổi |
| POST thực hiện thao tác | Gửi mật khẩu mới hoặc hành động khôi phục đã được cấp phép | Thay đổi thông tin xác thực theo phạm vi sau khi kiểm tra đủ điều kiện |

Không đổi mật khẩu, xóa MFA, đăng ký passkey hoặc đăng nhập đầy đủ chỉ vì URL được tải. Cũng không đánh dấu token đã dùng ngay trong một GET chỉ để biết liên kết “đã được mở”.

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt hoặc bộ xem trước
    participant R as Trang khôi phục
    participant S as Dịch vụ khôi phục
    B->>R: GET liên kết có token
    R-->>B: Trang tiếp tục, chưa tiêu thụ token
    Note over B,R: Người dùng chủ động xác nhận
    B->>R: POST tiếp tục với bảo vệ yêu cầu
    R->>S: Kiểm tra token và chính sách
    S-->>R: Quyền khôi phục giới hạn
    R-->>B: Điều hướng đến URL sạch
    B->>R: POST thao tác đã được cấp quyền
    R->>S: Kiểm tra và tiêu thụ quyền nguyên tử
    S-->>R: Kết quả thao tác
~~~

Bước xác nhận chỉ giảm tác dụng phụ do tải trước thông thường. Nó không bảo đảm mọi bot đều bị ngăn và không thay thế kiểm tra bằng chứng. Không viết JavaScript tự động POST ngay sau khi trang tải rồi coi đó là xác nhận chủ động.

### 7.1. Đổi token và sử dụng quyền là hai trạng thái khác nhau

Nếu dùng cơ chế đổi token sang phiên khôi phục giới hạn, việc đổi phải nguyên tử: một token chưa dùng chỉ được đổi thành quyền phù hợp theo chính sách. Sau khi đổi, token cũ không được dùng để tạo thêm các quyền độc lập.

Quyền mới phải ngắn hạn, chỉ áp dụng cho giao dịch và mục đích tương ứng. Nếu đặt trong cookie, cookie cần các thuộc tính bảo vệ phù hợp như Secure, HttpOnly và SameSite theo thiết kế. Nó không được dùng làm phiên đăng nhập thông thường.

Đến bước cuối, kiểm tra lại quyền, hạn hiệu lực và trạng thái tài khoản; cập nhật thông tin xác thực và tiêu thụ quyền trong cùng ranh giới nhất quán. Hai yêu cầu song song không được cùng hoàn tất từ một quyền chỉ dùng một lần.

Một cơ chế khác có thể giữ token đến POST cuối rồi tiêu thụ trực tiếp, nhưng vẫn phải giải quyết việc lộ token và tải trước. Không thể chỉ đổi tên cookie thành “recovery session” rồi bỏ những ràng buộc trên.

### 7.2. Bảo vệ POST theo ngữ cảnh trình duyệt

Khi dựa vào cookie hoặc phiên trình duyệt, áp dụng bảo vệ CSRF và kiểm tra nguồn yêu cầu theo kiến trúc của ứng dụng. Có thể ràng buộc bước xác nhận với một phiên khởi tạo và nonce do máy chủ quản lý.

Không dùng token khôi phục làm một lời giải mặc định cho mọi vấn đề CSRF hoặc nhầm lẫn tài khoản. Một người dùng đang đăng nhập tài khoản A nhưng mở liên kết của tài khoản B cần được dẫn qua quy trình rõ ràng; không được âm thầm gắn thông tin xác thực mới của B vào A.

## 8. Giảm nơi token xuất hiện

Token đặt trong URL có thể đi vào lịch sử trình duyệt, log của CDN/proxy/ứng dụng, công cụ quan sát và các hệ thống ghi lại trang. HTTPS bảo vệ đường truyền giữa các đầu kết nối phù hợp; nó không tự xóa token khỏi các đầu cuối này.

### 8.1. Trang tiếp nhận tối giản

Trang xử lý liên kết nên có ít tài nguyên và phụ thuộc nhất có thể. Tránh script phân tích hành vi, công cụ ghi lại phiên, widget hỗ trợ và tài nguyên bên thứ ba có thể đọc URL.

Các header minh họa:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Referrer-Policy làm giảm việc URL nguồn bị gửi đi theo cơ chế referrer. Nó không ngăn một script đang chạy trong trang tự đọc URL rồi gửi đi. Content Security Policy cần được điều chỉnh theo tài nguyên thật; cùng origin cũng không bảo đảm mọi script đều được phép tiếp xúc với token.

Không đưa token vào tiêu đề trang, thông báo lỗi, thuộc tính phục vụ phân tích hành vi hoặc dữ liệu hỗ trợ khách hàng. Khi chọn cách ghi nhận lỗi, kiểm tra cả lớp hạ tầng đứng trước ứng dụng, không chỉ logger trong mã nghiệp vụ.

### 8.2. Query và fragment có đánh đổi khác nhau

| Cách mang token | Đặc điểm | Điều phải xử lý |
|---|---|---|
| Query, ví dụ ?token=... | Được gửi cùng HTTP request tới origin đích | Lọc dữ liệu ở log, tránh referrer và tài nguyên không cần thiết |
| Fragment, ví dụ #token=... | Fragment không nằm trong request HTTP mà trình duyệt gửi đến máy chủ | JavaScript phía khách phải đọc và chuyển token an toàn; vẫn có rủi ro từ script, lịch sử và công cụ ghi lại trang |

Fragment không biến URL thành nơi cất bí mật an toàn tuyệt đối. Nó thay đổi thành phần nào tiếp xúc với token và tăng trách nhiệm cho mã phía khách.

Sau khi đổi token thành quyền khôi phục giới hạn một cách hợp lệ, máy chủ có thể trả chuyển hướng đến URL sạch, ví dụ phản hồi 303 đến /account-recovery/continue. Không đưa token vào Location hoặc tham số của trang đích tiếp theo.

Việc làm sạch URL hoặc dùng history.replaceState chỉ giảm phơi lộ kể từ thời điểm thực hiện. Nó không xóa token đã được lưu ở proxy, log, lịch sử đồng bộ hoặc hệ thống khác trước đó.

### 8.3. Không thêm chuỗi theo dõi nhấp vào đường đi bí mật

Nếu hệ thống gửi email hỗ trợ bọc liên kết để đo lượt nhấp, xem xét tắt cơ chế này cho liên kết có token khi có quyền cấu hình. Mỗi trung gian nhận URL đầy đủ trở thành một nơi có thể tiếp xúc với bí mật.

Không dùng dịch vụ rút gọn URL công khai hoặc route quảng cáo làm cầu nối mặc định cho liên kết khôi phục. Nếu hạ tầng email phía người nhận tự viết lại liên kết, thiết kế vẫn phải xử lý được tải trước mà không tiêu thụ token qua GET.

## 9. Đích sau khôi phục và chuyển hướng mở

Trang hoàn tất thường muốn đưa người dùng trở lại sản phẩm. Không vì yêu cầu trải nghiệm này mà chấp nhận một returnTo tùy ý từ URL ban đầu.

Thiết kế đơn giản là sử dụng đích cố định. Nếu có vài lựa chọn hợp lệ, dùng mã đích và ánh xạ ở máy chủ:

~~~text
SIGN_IN  -> https://app.example.invalid/sign-in
HELP     -> https://help.example.invalid/account-recovery
~~~

Mã đích chỉ chọn trong tập đã định; nó không chứa một URL tùy ý. Đích được gắn với giao dịch tại máy chủ, kiểm tra theo tenant và chỉ sử dụng ở thời điểm thích hợp.

Nếu nghiệp vụ bắt buộc hỗ trợ URL động, cần phân tích, chuẩn hóa và kiểm tra origin cùng route theo hợp đồng chặt chẽ. Việc chỉ kiểm tra chuỗi bắt đầu bằng dấu / chưa đủ để chứng minh một URL là đường dẫn nội bộ an toàn: dạng //, dấu phân cách bị mã hóa và cách xử lý khác nhau của proxy hoặc framework có thể gây bất ngờ.

Một chữ ký trên returnTo chỉ chứng minh dữ liệu không bị thay đổi kể từ khi ký. Nếu máy chủ ký một đích độc hại mà không kiểm tra, chữ ký hợp lệ vẫn đi cùng một đích nguy hiểm.

Nguyên tắc điều hướng cần giữ:

- Không chuyển token sang origin khác.
- Không đưa token vào query hoặc fragment của đích sau hoàn tất.
- Không dùng chuyển hướng lâu dài có thể bị lưu lại cho URL chứa bí mật.
- Không tự tạo phiên đăng nhập đầy đủ chỉ vì bước chuyển hướng diễn ra.
- Thực hiện kiểm soát session theo chính sách của thao tác đã hoàn tất, không theo các tham số điều hướng.

## 10. Nhiều tenant, nhiều giao diện và thiết bị khác nhau

### 10.1. Tên miền riêng của tenant

Nếu sản phẩm hỗ trợ tên miền riêng, việc đăng ký tên miền phải xác minh quyền kiểm soát và đưa đích vào registry được quản lý. Không suy ra rằng người nhập một tên miền trong biểu mẫu đã có quyền nhận token trên miền đó.

Một giao dịch cần gắn tenant tại máy chủ. Token của tenant A không được chấp nhận tại route của tenant B chỉ vì hai route dùng chung cơ sở dữ liệu.

Khi thay đổi hoặc ngừng sử dụng một tên miền, cần xem xét cả giao dịch đang chờ, thư đã gửi và quyền kiểm soát DNS. Không chuyển hướng các liên kết cũ chứa token đến tên miền mới một cách mù quáng; đánh giá lại hiệu lực và đường đi của bí mật theo chính sách.

### 10.2. Nhiều giao diện và vùng triển khai

Có thể có nhiều origin cho web, quản trị hoặc vùng phục vụ khác nhau. Mỗi origin nhận token là một thành phần của ranh giới tin cậy.

Máy chủ chọn origin bằng dữ liệu định tuyến hợp lệ và cấu hình. Nếu một vùng chưa có cấu hình, không lấy origin từ yêu cầu để “chạy tạm”. Giao diện quản trị có yêu cầu khôi phục riêng cũng không được tự dùng luồng đơn giản hơn của giao diện người dùng thông thường.

### 10.3. Mở liên kết trên thiết bị khác

Người dùng có thể mất điện thoại rồi mở email trên máy tính mới. Ràng buộc cứng liên kết vào cookie hoặc thiết bị từng khởi tạo có thể khiến việc khôi phục không sử dụng được.

Nếu chính sách cần ràng buộc thiết bị, phải có luồng thay thế rõ ràng cho tình huống mất thiết bị. Tín hiệu thiết bị hỗ trợ đánh giá rủi ro; bản thân việc liên kết mở ở thiết bị mới không đủ để kết luận là chủ tài khoản hay kẻ tấn công.

Nếu hỗ trợ mở ứng dụng, chỉ sử dụng các đích ứng dụng được đăng ký và cơ chế xác minh liên kết phù hợp với nền tảng. Không coi một custom URL scheme tùy ý là bằng chứng rằng chỉ ứng dụng hợp lệ có thể nhận token. Nên có đường đi web được kiểm soát cho trường hợp ứng dụng chưa cài hoặc thiết bị xác thực đã mất.

## 11. Xử lý lỗi và các tình huống cần kiểm chứng

Liên kết hết hạn, đã dùng, bị thu hồi hoặc không khớp mục đích cần dẫn đến trang lỗi an toàn. Trang có thể hướng dẫn bắt đầu yêu cầu mới nhưng không in token hoặc chi tiết tài khoản ra thông báo.

Không tự chuyển sang một luồng ít bằng chứng hơn khi token lỗi. Nếu người dùng mất toàn bộ phương tiện, cần đi vào quy trình thay thế đã thiết kế, với chính sách riêng.

| Tình huống | Kết quả mong đợi |
|---|---|
| Khách sửa Host hoặc X-Forwarded-Host | URL phát hành vẫn lấy từ registry hợp lệ |
| Payload chứa callbackUrl bên ngoài | Không thay được đích nhận token |
| URL có userinfo hoặc host chỉ chứa chuỗi tên miền hợp lệ | Không vượt qua kiểm tra cấu hình |
| Token chứa ký tự làm thay đổi cấu trúc query | Bị từ chối theo hợp đồng hoặc được xử lý bằng bộ dựng URI phù hợp |
| GET do bộ quét email thực hiện | Không hoàn tất khôi phục hoặc tiêu thụ token |
| Trang được tải cùng tài nguyên bên thứ ba | Không có thành phần không cần thiết được tiếp xúc với token |
| Token của tenant A mở tại tenant B | Bị từ chối, không đổi tài khoản đích |
| Token đặt lại mật khẩu được đưa vào route xóa MFA | Không được cấp quyền ngoài mục đích |
| Hai POST đồng thời đổi cùng token | Không tạo hai quyền khôi phục độc lập trái chính sách |
| Hai yêu cầu cùng sử dụng quyền một lần | Chỉ một yêu cầu có thể hoàn tất |
| returnTo độc hại có chữ ký do hệ thống từng cấp sai | Không coi chữ ký là thay thế cho kiểm tra đích |
| Tên miền đích bị bỏ cấu hình | Không fallback về host do khách chọn |
| Người dùng đang có phiên của tài khoản khác | Không âm thầm cập nhật nhầm tài khoản |
| Token hết hạn hoặc đã thu hồi | Trang lỗi chung, có lối bắt đầu lại an toàn |
| Thao tác hoàn tất và điều hướng tiếp | URL mới không mang token; quyền và session được xử lý theo chính sách |

Các tình huống này kiểm tra cả chuỗi gửi email, proxy, trang tiếp nhận và điểm thực hiện thao tác. Chỉ nhìn vào hàm tạo URL chưa đủ để biết token có đi qua một route chuyển hướng hoặc hệ thống log khác ở phía sau hay không.

## 12. Vận dụng: chọn đúng đích cho yêu cầu của Minh

Với yêu cầu quên mật khẩu của Minh, máy chủ chọn tenant và tài khoản từ giao dịch hợp lệ, lấy route khôi phục từ registry rồi dựng URL HTTPS. Email được gửi qua kênh đã đăng ký; nội dung liên kết không phụ thuộc Host hoặc callback mà người gửi yêu cầu cung cấp.

Khi Minh hoặc một bộ xem trước mở liên kết, trang chỉ tiếp nhận và trình bày bước tiếp tục. Quyền khôi phục chỉ được sử dụng qua thao tác được bảo vệ, kiểm tra đúng tài khoản và mục đích. Token không đi vào công cụ theo dõi, đích ngoài hoặc URL sau hoàn tất.

Nếu yêu cầu thực tế là mất MFA hoặc passkey, cùng nguyên tắc chọn đích vẫn được áp dụng, nhưng trang phải tiếp tục đúng chính sách của mục đích đó. Sở hữu liên kết email không tự động biến thành quyền bỏ mọi yếu tố xác thực còn lại.
