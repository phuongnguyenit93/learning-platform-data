# Phân biệt HTTPS và cách mã hóa dữ liệu trong HTTP Basic

Trong quá trình đăng nhập, nhiều người nhìn thấy header `Authorization: Basic ...` chứa một dãy ký tự khó đọc và cho rằng tài khoản, mật khẩu đã được **mã hóa an toàn**. Đây là một nhầm lẫn nguy hiểm. **HTTP Basic chỉ dùng Base64 để *biểu diễn* cặp `username:password`; HTTPS dùng TLS để *mã hóa và bảo vệ dữ liệu trên đường truyền*.** Hai cơ chế giải quyết hai vấn đề khác nhau và thường được dùng cùng nhau.

Hãy ghi nhớ ngay ba điểm:

- **HTTP Basic** là một cơ chế **xác thực**: client gửi thông tin đăng nhập trong header `Authorization`, server xác minh thông tin đó.
- **Base64** là **mã hóa biểu diễn dữ liệu (encoding)** có thể đảo ngược mà không cần khóa bí mật. Đây không phải mã hóa bảo mật (encryption), cũng không phải hàm băm mật khẩu (hash).
- **HTTPS** là HTTP truyền qua **TLS**: TLS mã hóa và kiểm tra tính toàn vẹn dữ liệu giữa hai đầu của kết nối TLS, đồng thời xác thực danh tính máy chủ dựa trên chứng chỉ hợp lệ. HTTPS không tự quyết định người dùng nào được đăng nhập.

Bài học tập trung vào sự khác biệt này trong luồng đăng nhập/đăng xuất của Spring Security Servlet, kèm ví dụ Java 17 có thể chạy độc lập để kiểm chứng Base64.

## 1. Đọc đúng header HTTP Basic

Theo RFC 7617, client tạo phần credentials bằng các bước:

1. Ghép **username**, dấu hai chấm `:` và **password** thành một chuỗi `username:password`.
2. Chuyển chuỗi thành byte theo bộ mã ký tự phù hợp.
3. Dùng Base64 để chuyển byte thành ký tự ASCII biểu diễn.
4. Gửi giá trị đó ở header `Authorization: Basic <base64>` khi xác thực bằng HTTP Basic.

Ví dụ chỉ sử dụng tài khoản giả lập:

```text
Username                 demo
Password                 pass123
Chuỗi ghép               demo:pass123
Giá trị Base64           ZGVtbzpwYXNzMTIz
HTTP Authorization       Basic ZGVtbzpwYXNzMTIz
```

Request HTTP sau minh họa cấu trúc nội dung, **không phải cách truyền mật khẩu được khuyến nghị qua mạng công cộng**:

```http
GET /api/profile HTTP/1.1
Host: example.test
Authorization: Basic ZGVtbzpwYXNzMTIz
```

Dễ thấy header không chứa chữ `demo:pass123` ở dạng văn bản trực tiếp. Tuy nhiên, bất kỳ ai đọc được `ZGVtbzpwYXNzMTIz` đều có thể giải mã Base64 ra chính xác `demo:pass123`. Không tồn tại khóa bí mật hoặc thuật toán bất đối xứng nào trong bước Base64 này.

**Không nhầm với mã hóa URL hoặc mã hóa ký tự:** Trong HTTP Basic, Base64 chỉ là cách đóng gói các byte credentials cho cú pháp header. Nó không thay đổi quyền truy cập, không xóa sự hiện diện của mật khẩu và không tạo một token bảo mật độc lập.

### Quy tắc về dấu hai chấm và bảng mã ký tự

Dấu `:` **đầu tiên** ngăn cách username và password. Vì thế username không được chứa dấu `:` theo RFC 7617, trong khi password có thể chứa dấu này; chẳng hạn `demo:abc:def` có username là `demo` và password là `abc:def`.

Với ký tự ASCII như ví dụ trên, việc encoding thường nhất quán. Với tên hoặc mật khẩu có dấu tiếng Việt, các client/server có thể gặp khác biệt về cách chuyển Unicode thành byte. RFC 7617 cho phép server nêu `charset="UTF-8"` trong challenge `WWW-Authenticate`; mặc định lịch sử không ấn định duy nhất một bảng mã cho mọi client. Hãy sử dụng thư viện/framework tương thích và kiểm thử cụ thể, không tự giả định mọi client đều dùng UTF-8 giống nhau.

## 2. Tự chứng minh Base64 có thể đảo ngược bằng Java 17

Tạo tệp `BasicEncodingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicEncodingDemo {
    public static void main(String[] args) {
        // Credentials giả lập: chỉ để minh họa định dạng HTTP Basic.
        String credentials = "demo:pass123";

        String encoded = Base64.getEncoder().encodeToString(
                credentials.getBytes(StandardCharsets.UTF_8)
        );
        String decoded = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8
        );

        System.out.println("Authorization: Basic " + encoded);
        System.out.println("Decoded: " + decoded);
        System.out.println("Round-trip matches: " + credentials.equals(decoded));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BasicEncodingDemo.java
java BasicEncodingDemo
```

Đầu ra chính xác:

```text
Authorization: Basic ZGVtbzpwYXNzMTIz
Decoded: demo:pass123
Round-trip matches: true
```

`Base64.getEncoder()` không có khóa mã hóa, còn `Base64.getDecoder()` khôi phục dữ liệu đầu vào. Code in chuỗi credentials chỉ để làm rõ tính đảo ngược của **mật khẩu giả**; tuyệt đối không log, in console, chia sẻ ảnh chụp hoặc ghi lại giá trị `Authorization` hay password thật trong ứng dụng.

Cũng không nhầm Base64 với **hash mật khẩu**. Khi lưu tài khoản, ứng dụng phải dùng thuật toán băm mật khẩu phù hợp, có salt và chi phí tính toán được thiết kế cho mật khẩu (ví dụ BCrypt, Argon2), thông qua `PasswordEncoder` thích hợp. Server nhận mật khẩu từ HTTP Basic để kiểm tra với bản hash đã lưu; mã hóa Base64 header **không thay thế** bước lưu và kiểm chứng mật khẩu an toàn.

## 3. HTTPS thực sự bảo vệ điều gì?

HTTPS có thể được hiểu ở mức khái quát là **HTTP chạy bên trong kênh TLS**. Với kết nối HTTPS thông thường:

1. Client kết nối tới tên miền đích và thương lượng một kết nối TLS.
2. Client kiểm tra chứng chỉ, tên máy chủ và chuỗi tin cậy theo chính sách xác thực TLS áp dụng; hai bên thỏa thuận khóa phiên bảo mật.
3. HTTP request (bao gồm method, đường dẫn, header `Authorization` và body) được đưa qua kênh TLS đã mã hóa.
4. Đầu kết thúc TLS giải mã dữ liệu và chuyển request cho thành phần xử lý HTTP; server vẫn phải xác minh credentials và kiểm tra quyền truy cập.
5. Response cũng được mã hóa khi gửi qua kết nối TLS này.

Sơ đồ khái niệm:

```text
Client                              Server / TLS endpoint
  |                                        |
  |====== Thiết lập TLS + xác thực server |
  |                                        |
  |  HTTP request nằm trong bản ghi TLS   |
  |  {Authorization: Basic ...} --[MÃ HÓA]-->|
  |                                        | Giải mã TLS
  |                                        | Giải mã Base64
  |                                        | Xác thực user
  |<--[MÃ HÓA]-- HTTP response qua TLS     |
```

Sơ đồ đơn giản hóa cho mục đích học. HTTP/1.1, HTTP/2 và HTTP/3 có chi tiết tầng vận chuyển khác nhau; điều quan trọng ở đây là **dữ liệu HTTP được bảo vệ trong kết nối TLS khi dùng HTTPS**.

TLS đem lại ba thuộc tính quan trọng: **tính bí mật** chống nghe lén nội dung trên đoạn mạng được bảo vệ, **tính toàn vẹn** giúp phát hiện sửa đổi trái phép trong truyền tải, và **xác thực đầu kết nối** (thông thường là xác thực server bằng chứng chỉ). HTTPS **không tự xác thực người dùng**; endpoint vẫn cần HTTP Basic, form login, OAuth2/OIDC hoặc cơ chế khác nếu tài nguyên yêu cầu đăng nhập.

TLS cũng không bảo đảm bí mật tại mọi nơi: code chạy ở client và endpoint kết thúc TLS có thể thấy request ở dạng rõ; reverse proxy, gateway, APM và hệ thống log có thể nhìn thấy header nếu được cấp quyền. Dữ liệu giữa TLS terminator và backend cần kênh tin cậy hoặc TLS phù hợp với hạ tầng. HTTPS không tự ngăn XSS, malware, tài khoản bị đánh cắp hay server lưu mật khẩu sai cách.

**Lưu ý về metadata:** Kẻ quan sát mạng vẫn có thể suy ra một số thông tin như địa chỉ IP, kích thước/lưu lượng và đôi khi tên miền từ DNS/SNI tùy cơ chế bảo vệ đang dùng. Không diễn giải HTTPS là ẩn toàn bộ dấu vết kết nối.

## 4. So sánh theo đúng lớp trách nhiệm

| Tiêu chí | HTTP Basic + Base64 | HTTPS / TLS |
|---|---|---|
| Mục đích chính | Truyền thông tin để **xác thực người dùng** | Bảo vệ **đường truyền** HTTP |
| Cơ chế | Ghép `username:password` rồi Base64 encode | Bắt tay TLS, khóa phiên, mã hóa có kiểm tra toàn vẹn |
| Có khóa bí mật để giải Base64? | **Không** | Có cơ chế khóa mật mã của TLS |
| Có thể hoàn nguyên nội dung? | **Có**, bất kỳ ai có chuỗi Base64 đều giải mã được | Chỉ đầu kết nối TLS có khóa phù hợp mới giải mã nội dung được bảo vệ |
| Thành phần HTTP | Header `Authorization: Basic ...` | Bảo vệ request/response trên kênh truyền |
| Có xác thực người dùng? | Có, khi server kiểm tra đúng credentials | **Không tự làm** |
| Có bảo vệ mật khẩu khỏi nghe lén khi truyền? | **Không nếu chỉ dùng HTTP** | Có, trong phạm vi kênh TLS được cấu hình và xác thực đúng |
| Có giải quyết việc lưu hash password? | Không | Không |
| Đăng xuất | Client phải ngừng dùng/gửi credentials; cơ chế cache tùy client | Đóng TLS không mặc nhiên logout tài khoản |

Đặc biệt, **không có phép so sánh “HTTPS mạnh hơn Base64 bao nhiêu lần”** vì chúng không cùng loại thuật toán: Base64 là encoding, TLS là giao thức truyền thông an toàn.

### Bốn tình huống dễ gặp

| Tình huống | Có xác thực người dùng bằng Basic? | Thông tin trên đường truyền có được TLS bảo vệ? | Nhận định |
|---|---|---|---|
| `http://...` + `Authorization: Basic ...` | Có thể | **Không** | Rất rủi ro: kẻ nghe lén có thể lấy và decode password |
| `https://...` + `Authorization: Basic ...` | Có thể | **Có** | HTTP Basic được bảo vệ khi truyền qua TLS hợp lệ |
| `https://...` nhưng không gửi credentials | Chưa chắc, tùy cơ chế khác | **Có** | HTTPS an toàn đường truyền nhưng chưa chứng minh user đã đăng nhập |
| `http://...` + Base64 trong body/query | Không tự tạo xác thực Basic | **Không** | Base64 ở đâu cũng không mã hóa bảo mật |

HTTP Basic qua HTTPS là tổ hợp thường gặp cho các endpoint đơn giản hoặc hệ thống tích hợp; nó vẫn phải đi cùng mật khẩu mạnh, phân quyền, chính sách xác thực và cách quản lý credentials phù hợp.

## 5. Luồng challenge–response của HTTP Basic

HTTP Basic dùng khuôn khổ xác thực HTTP. Một trường hợp phổ biến diễn ra như sau:

**Bước 1 — Client chưa gửi credentials:**

```http
GET /api/profile HTTP/1.1
Host: example.test
```

**Bước 2 — Server yêu cầu xác thực:**

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="training-api"
```

`401 Unauthorized` nghĩa là request chưa được xác thực theo yêu cầu của tài nguyên (tên status nghe giống “không được phép”, nhưng đây là lỗi xác thực). Header `WWW-Authenticate` cho biết scheme mà server hỗ trợ; `realm` định danh phạm vi bảo vệ để client hiển thị hoặc tổ chức thông tin đăng nhập.

**Bước 3 — Client gửi lại credentials:**

```http
GET /api/profile HTTP/1.1
Host: example.test
Authorization: Basic ZGVtbzpwYXNzMTIz
```

**Bước 4 — Server kiểm tra:** Server lấy phần sau `Basic `, decode Base64, tách username và password, dùng cơ chế xác thực để kiểm tra mật khẩu/quyền và trả response phù hợp. Thành công có thể là `200 OK`; thất bại thường là `401 Unauthorized` kèm challenge. Khi user đã xác thực nhưng không đủ quyền truy cập tài nguyên, `403 Forbidden` thường phù hợp hơn.

Client có thể gửi header Basic **ngay ở request đầu tiên** nếu đã biết credentials và phạm vi bảo vệ; không phải lúc nào cũng cần đủ hai vòng request. Một số browser có thể nhớ credentials Basic và tự thêm header trong các request phù hợp.

Nếu dùng HTTPS, những HTTP message trong ví dụ vẫn có cấu trúc như trên **sau khi TLS đã giải mã tại endpoint**; người nghe lén trên đường truyền chỉ thấy dữ liệu TLS mã hóa thay vì nhìn được header Basic trực tiếp.

## 6. Spring Security Servlet xử lý Basic như thế nào?

Trong Spring Security Servlet, cấu hình `httpBasic(...)` kích hoạt hỗ trợ HTTP Basic. Ở luồng cơ bản, `BasicAuthenticationFilter` đọc header `Authorization` có scheme `Basic`, xử lý credentials và đưa thông tin xác thực hợp lệ vào `SecurityContext` theo cơ chế của framework. Việc xác minh người dùng thực tế tùy `AuthenticationManager`, provider, `UserDetailsService` và `PasswordEncoder` được cấu hình.

Ví dụ cấu hình cho ứng dụng **Spring Boot / Spring Security Servlet**, không phải chương trình Java chạy độc lập:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Khi triển khai thật, ứng dụng cần có nguồn người dùng và cách xác minh mật khẩu thích hợp. Đoạn cấu hình minh họa chỉ cho biết **Spring Security nhận và xử lý HTTP Basic**; nó không định nghĩa sẵn tài khoản `demo/pass123` và không ngụ ý endpoint sẽ chấp nhận credentials giả lập của bài học.

Đừng tự viết filter giải mã Base64 rồi so sánh với password dạng rõ trong database. Hãy để cơ chế xác thực của Spring Security thực hiện kiểm tra credentials và sử dụng `PasswordEncoder` cho mật khẩu được lưu.

**Basic không đồng nghĩa với session đăng nhập.** Một request gửi `Authorization: Basic ...` thường có thể được xác thực trên từng request mà không cần session để chuyên chở credentials. Tuy nhiên, ứng dụng vẫn có thể tạo `HttpSession` bởi code hoặc thành phần khác tùy cấu hình. Cũng không được kết luận “chọn Basic thì tự động stateless tuyệt đối”. Nếu muốn API stateless, cần thiết kế chính sách session, repository bảo mật và cơ chế xác thực phù hợp với toàn bộ ứng dụng.

### So sánh nhanh với form login và Bearer token

- **HTTP Basic:** Client gửi trực tiếp cặp username/password đã Base64 encode trong header mỗi khi cần. Không có nút logout thống nhất ở giao thức; browser có thể cache credentials.
- **Form login dùng session:** User thường gửi mật khẩu đến endpoint đăng nhập qua HTTPS một lần, sau đó browser mang cookie phiên; server quản lý trạng thái đăng nhập theo phiên. Thiết kế này phù hợp với nhiều giao diện web, có cơ chế logout phiên rõ hơn.
- **Bearer token:** Client gửi một token được cấp theo quy trình riêng, ví dụ `Authorization: Bearer <token>`. Token là credential cần bảo vệ nhưng **khác** với `Basic <base64(username:password)>`; việc token có dạng JWT hay mã không trong suốt là lựa chọn hệ thống. TLS vẫn quan trọng.

Các lựa chọn trên đều có thể dùng HTTPS; đừng gọi HTTPS là “phương thức đăng nhập” cạnh tranh với Basic hoặc form login.

## 7. Kiểm thử đúng cách mà không làm lộ credentials

Có thể thử trong môi trường test qua HTTPS với tài khoản giả và endpoint do mình kiểm soát.

Dạng lệnh sau giúp `curl` hỏi mật khẩu thay vì đặt mật khẩu trực tiếp vào tham số dòng lệnh:

```bash
curl --basic --user demo https://example.test/api/profile
```

Địa chỉ `example.test` chỉ là tên miền minh họa, nên lệnh chỉ hoạt động khi bạn thay bằng endpoint thực có HTTPS và tài khoản test thích hợp. Khi được hỏi password, nhập vào kênh input phù hợp; không chèn password thật vào script, URL, shell history hoặc issue tracker.

Để tự xem chuỗi Header của **credentials giả**, bạn có thể dùng ví dụ Java độc lập ở phần 2. Khi quan sát Network tab, proxy debug hay `curl -v`, cần che hoặc xóa `Authorization` và password trước khi chia sẻ log. Công cụ debug hoặc server có khả năng xem dữ liệu **sau khi TLS giải mã**, nên HTTPS không làm cho bản log tự an toàn.

Không dùng các tham số vô hiệu hóa xác minh chứng chỉ TLS như `-k` / `--insecure` trong kiểm thử bảo mật thực tế để “chữa” lỗi cấu hình; hành động này loại bỏ một phần bảo vệ quan trọng trước máy chủ giả mạo.

### Dấu hiệu kiểm tra trong ứng dụng

1. Kiểm tra URL được gọi có scheme `https://` và chứng chỉ đáng tin với hostname đích.
2. Kiểm tra request có mang `Authorization: Basic ...` khi cần; tuyệt đối che nội dung header khi báo cáo lỗi.
3. Kiểm tra phản hồi `401` và `WWW-Authenticate` khi chưa xác thực; phân biệt với `403` khi user đã xác thực nhưng thiếu quyền.
4. Kiểm tra backend xác minh với kho credentials/hash đúng cách và phân quyền cho từng tài nguyên.
5. Nếu có reverse proxy, kiểm tra từng đoạn truyền sau TLS termination. Chỉ có HTTPS từ browser đến gateway không tự bảo vệ đoạn gateway–backend sử dụng HTTP không mã hóa.

## 8. Rủi ro và lỗi suy luận phổ biến

### “Tôi thấy chuỗi Base64 nên mật khẩu đã được mã hóa”

**Sai.** Bất kỳ ai nắm được header Basic đều có thể decode để thu lại username/password. Base64 có thể phục vụ truyền dữ liệu nhưng **không tạo bí mật**. Nếu đi qua HTTP rõ, credentials có nguy cơ lộ với người quan sát được traffic.

### “Chỉ cần dùng HTTPS là có đăng nhập và phân quyền”

**Sai.** HTTPS bảo vệ kết nối tới endpoint TLS, không xác minh user ứng dụng. Xác thực, phân quyền, quản lý phiên và lưu hash mật khẩu là các trách nhiệm riêng của ứng dụng.

### “Đã có HTTPS nên server không thể nhìn thấy mật khẩu”

**Sai.** Endpoint TLS bắt buộc giải mã request để xử lý; nếu Basic được gửi thì ứng dụng xác thực có thể nhận credentials đã decode. TLS bảo vệ khi truyền, không tự mã hóa mật khẩu ở trạng thái lưu trữ, không che khỏi log và không ngăn code có quyền truy cập credentials.

### “Đóng tab hay gọi logout session là đủ để xóa Basic authentication”

**Không chắc.** Browser và HTTP client có thể cache/reuse credentials Basic cho phạm vi bảo vệ phù hợp. HTTP Basic không đưa ra cơ chế logout ứng dụng giống một session đã được invalidate. Muốn ngừng truy cập phải bảo đảm client không gửi credentials nữa, xử lý cache theo client, hoặc thu hồi/đổi credentials trên server khi cần. Với API tự viết client, việc xóa Authorization header khỏi các request sau là bước quan trọng.

### “Đã dùng HTTPS nên không cần phòng CSRF, XSS hay bảo vệ log”

**Sai.** TLS chỉ xử lý lớp truyền tải. Nếu browser tự gửi credentials, rủi ro CSRF có thể vẫn liên quan đến thao tác đổi trạng thái; chính sách CSRF phải dựa trên mô hình client thực tế. XSS có thể dẫn đến hành động trái phép từ ứng dụng; logging header/cookie/credentials có thể làm lộ bí mật ngay trong hạ tầng.

### “Basic qua HTTPS là tuyệt đối an toàn”

**Không đúng.** Dù HTTPS là yêu cầu nền tảng khi dùng Basic, mật khẩu vẫn là credential thường được gửi lại nhiều lần. Cần quản lý secrets, quyền truy cập tối thiểu, bảo vệ chống brute force, rate limiting, giám sát an toàn, chính sách thay đổi/thu hồi credentials và lựa chọn cơ chế đăng nhập phù hợp với sản phẩm. Basic thường không phải lựa chọn lý tưởng cho giao diện người dùng cần đăng nhập đa yếu tố, logout thuận tiện hoặc phiên dài hạn.

## 9. Bài tập tình huống

**Tình huống A:** Dev nói “Không cần HTTPS, header đã là `Authorization: Basic ZGVtbzpwYXNzMTIz`”. Bạn nên phản biện rằng Base64 có thể decode ngay thành `demo:pass123`; HTTPS với chứng chỉ hợp lệ là điều kiện quan trọng để bảo vệ credentials trên mạng.

**Tình huống B:** API `https://service.example.test/api/profile` trả `401` dù TLS handshake thành công. Điều này không mâu thuẫn: kết nối truyền tải đã thiết lập an toàn, nhưng người dùng chưa gửi credentials hợp lệ hoặc server chưa xác thực được.

**Tình huống C:** Người dùng đăng nhập Basic qua browser, đóng tab rồi mở lại API vẫn được xác thực. Không được kết luận server còn `HttpSession` theo mặc định; browser có thể giữ cache HTTP Basic và gửi lại credentials.

**Tình huống D:** Gateway tiếp nhận HTTPS nhưng forward HTTP sang backend qua một mạng không tin cậy. Kênh client–gateway được bảo vệ, còn đoạn gateway–backend có thể để lộ header Basic. Phải đánh giá từng điểm kết thúc TLS và từng đoạn mạng.

**Tình huống E:** Hệ thống lưu `ZGVtbzpwYXNzMTIz` trong database để “mã hóa mật khẩu”. Đây là thiết kế sai: Base64 decode được dễ dàng. Mật khẩu lưu trữ phải được xử lý bằng password hashing thích hợp, khác với encoding header lúc request.

## 10. Tự đánh giá

1. **HTTP Basic mã hóa bảo mật mật khẩu không?** Không; nó Base64 encode cặp `username:password`, đảo ngược được.
2. **HTTPS có thay thế HTTP Basic không?** Không; HTTPS bảo vệ đường truyền, còn Basic cung cấp dữ liệu để server xác thực người dùng.
3. **Basic qua HTTP khác gì Basic qua HTTPS?** Nội dung header Basic có thể giống nhau ở lớp HTTP, nhưng chỉ HTTPS đặt HTTP trong kênh TLS được bảo vệ.
4. **Server có thấy plaintext password sau khi TLS giải mã không?** Thành phần xác thực ở server có thể nhận mật khẩu sau khi decode Basic để xác minh, vì vậy phải bảo vệ log, bộ nhớ và kho tài khoản.
5. **HTTP Basic dùng cookie session bắt buộc không?** Không; Basic truyền credentials trong Authorization header, còn session là cơ chế riêng.
6. **Tên gọi “encoding”, “encryption”, “hashing” có hoán đổi được không?** Không. Encoding thay đổi biểu diễn có thể đảo ngược công khai; encryption dùng khóa để giữ bí mật; password hashing là phép một chiều được thiết kế để xác minh mật khẩu lưu trữ.

**Kết luận cần nhớ:** `Authorization: Basic ...` chỉ che cách nhìn thông thường bằng Base64 và vẫn chứa credentials có thể khôi phục. **Dùng HTTPS/TLS đúng cách để bảo vệ credentials khi truyền**, đồng thời để Spring Security xác thực và phân quyền, sử dụng password hashing phù hợp và bảo vệ toàn bộ hệ thống khỏi rò rỉ credentials.

### Tài liệu đối chiếu

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html): định dạng `username:password`, Base64, challenge, charset và giới hạn bảo mật.
- [Spring Security — HTTP Basic Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): cách bật và xử lý HTTP Basic trong Spring Security.
- [MDN — HTTP authentication](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication): cơ chế challenge/response và cảnh báo HTTP Basic phải kết hợp HTTPS.