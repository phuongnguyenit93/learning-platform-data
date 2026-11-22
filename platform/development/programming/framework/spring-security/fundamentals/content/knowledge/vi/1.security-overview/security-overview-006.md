# Các thuật ngữ đầu tiên: principal, credentials, Authentication và authority

Khi một yêu cầu đến ứng dụng, Spring Security cần trả lời hai nhóm câu hỏi: **ai đang yêu cầu** và **người đó được phép làm gì**. Trong đó, bốn thuật ngữ thường xuất hiện cùng nhau nhưng mang nghĩa khác nhau:

- **Principal** là danh tính đang được nói đến.
- **Credentials** là bằng chứng để kiểm tra lời khai về danh tính ấy.
- **Authentication** là đối tượng biểu diễn yêu cầu xác thực hoặc kết quả đã xác thực, cùng trạng thái và dữ liệu liên quan.
- **Authority** là quyền được cấp và được dùng khi hệ thống quyết định có cho phép một hành động hay không.

Hãy hình dung Mai nhập tên `mai` và mật khẩu để đọc bài viết. Tên đăng nhập là một lời khai; mật khẩu là bằng chứng cần được xác minh. Nếu kiểm tra thành công, hệ thống có thể xác nhận danh tính Mai. Nhưng ngay cả khi Mai được xác thực, việc đọc hoặc xuất bản bài vẫn phụ thuộc vào quyền và chính sách truy cập. **Xác thực (authentication)** và **phân quyền (authorization)** là hai quyết định khác nhau.

## 1. Bản đồ khái niệm

| Thuật ngữ | Câu hỏi cần trả lời | Ví dụ | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| `principal` | “Danh tính nào?” | `"mai"`, một `UserDetails`, một `Jwt` | Danh tính ấy đã được kiểm chứng |
| `credentials` | “Bằng chứng nào?” | Mật khẩu vừa nhập, bearer token | Bằng chứng đã hợp lệ |
| `Authentication` | “Đối tượng và trạng thái xác thực hiện tại là gì?” | `UsernamePasswordAuthenticationToken` | Chắc chắn có đủ quyền truy cập |
| `authority` | “Được cấp quyền nào?” | `ROLE_EDITOR`, `article:read` | Tự động có mọi quyền khác |

Một luồng đăng nhập bằng tên và mật khẩu thường diễn ra như sau:

~~~text
Client gửi: principal="mai" + credentials=<mật khẩu>
                           |
                           v
        Authentication chưa được xác thực
                           |
                           v
       AuthenticationManager / AuthenticationProvider
               kiểm tra bằng chứng
                  /                 \
          Thành công              Thất bại
             |                       |
             v                       v
  Authentication đáng tin       AuthenticationException
  (principal, authorities,
   authenticated=true)
             |
             v
     SecurityContext, nếu cơ chế sử dụng
             |
             v
  Chính sách authorization kiểm tra authority
     phù hợp với thao tác/tài nguyên
~~~

Đây là mô hình để hiểu thuật ngữ, không có nghĩa mọi hệ thống đều đăng nhập bằng mật khẩu. Với bearer token, JWT hoặc cơ chế liên kết danh tính, cách nhận và kiểm tra bằng chứng khác nhau, còn bốn khái niệm vẫn cần được phân biệt.

## 2. Principal: danh tính của chủ thể

**Principal** đại diện cho danh tính mà quá trình xác thực đang xét. Chủ thể có thể là người dùng, tài khoản dịch vụ hoặc ứng dụng gọi API. Một principal không nhất thiết là một thực thể Java cùng kiểu trong mọi cơ chế xác thực.

Trong Spring Security, `Authentication#getPrincipal()` trả về `Object`. Những trường hợp thường gặp:

1. **Trước xác thực bằng tên/mật khẩu:** giá trị có thể chỉ là `String` chứa tên `"mai"`; bất kỳ ai cũng có thể gửi lời khai này, nên chưa đáng tin.
2. **Sau khi xác thực thành công:** một provider có thể trả `UserDetails` gồm tên đăng nhập, trạng thái tài khoản và thông tin ứng dụng cần dùng. Điều này không bắt buộc cho mọi provider.
3. **Với resource server xác thực JWT:** principal có thể là đối tượng `Jwt` đã qua xử lý xác thực, thay vì `UserDetails`.
4. **Với người dùng vô danh:** có thể tồn tại một principal đại diện cho anonymous; nó không chứng minh một tài khoản thực đã đăng nhập.

Cũng cần phân biệt ba biểu thức:

- `authentication`: **toàn bộ đối tượng** mang dữ liệu xác thực.
- `authentication.getPrincipal()`: **danh tính nằm trong** đối tượng đó.
- `authentication.getName()`: **tên biểu diễn danh tính**, được tính theo kiểu `Authentication` cụ thể.

Giao diện `Authentication` mở rộng `java.security.Principal`, nhưng điều đó không khiến `getPrincipal()` luôn là `String` hoặc `UserDetails`. Vì vậy đừng ép kiểu như `(UserDetails) authentication.getPrincipal()` khi chưa biết cơ chế xác thực đang sử dụng. Nếu cần ID nghiệp vụ ổn định, hãy xác định rõ hợp đồng ánh xạ từ principal sang tài khoản của ứng dụng.

## 3. Credentials: bằng chứng để chứng minh lời khai

**Credentials** là dữ liệu được dùng để kiểm tra rằng một principal có cơ sở được tin cậy. Trong đăng nhập bằng mật khẩu, đây thường là mật khẩu thô người dùng vừa nhập. Với API, đó có thể là bearer token hoặc dữ liệu chứng minh danh tính phù hợp với giao thức.

| Trường hợp | Principal/lời khai | Credentials/bằng chứng |
| --- | --- | --- |
| Biểu mẫu đăng nhập | `mai` | Mật khẩu do Mai gửi |
| HTTP Basic | Tên đăng nhập được tách từ thông tin xác thực | Mật khẩu đi kèm |
| Bearer token | Danh tính sẽ được rút ra từ token hợp lệ | Bearer token do client gửi |
| Tài khoản dịch vụ | Danh tính dịch vụ | Bí mật hoặc bằng chứng do cơ chế đang dùng yêu cầu |

Phương thức `Authentication#getCredentials()` trả về `Object` và có thể trả `null`. Giá trị `null` **không tự chứng minh đăng nhập thất bại**: sau khi xác thực thành công, `ProviderManager` mặc định thường cố xóa credentials nhạy cảm của đối tượng kết quả nếu đối tượng hỗ trợ `CredentialsContainer`. Khi đó ứng dụng vẫn có principal và authorities để làm việc nhưng không cần giữ mật khẩu thô.

Các điều cần thực hiện:

- Không ghi mật khẩu, bearer token hoặc bí mật khác vào log, thông báo lỗi, phản hồi API, hay đặt chúng trong lời gọi `toString()` dùng để ghi nhật ký.
- Không giữ credentials thô trong `SecurityContext` để tái sử dụng. Sau khi kiểm tra, chỉ giữ dữ liệu thực sự cần cho lần xử lý.
- Không tự so sánh mật khẩu thô bằng chuỗi ở controller. Dùng provider và `PasswordEncoder` được cấu hình phù hợp.
- Không nhầm **bearer token do client cung cấp** với đối tượng **`Authentication` trong Spring Security**. Hai thứ này đều đôi khi được gọi nôm na là “token” nhưng có vai trò khác nhau.

## 4. Authentication: yêu cầu và kết quả xác thực

`org.springframework.security.core.Authentication` là giao diện trung tâm trong Spring Security. Cùng một giao diện có thể đại diện cho **yêu cầu chưa xác thực** hoặc **kết quả đã được xác thực**. Ví dụ `UsernamePasswordAuthenticationToken` dùng để chứa tên và mật khẩu trước khi kiểm tra, rồi một đối tượng cùng loại có thể biểu diễn kết quả đáng tin cậy sau đó.

| Thành phần | Phương thức | Ý nghĩa |
| --- | --- | --- |
| Danh tính | `getPrincipal()` | Đối tượng đại diện cho chủ thể |
| Bằng chứng | `getCredentials()` | Dữ liệu chứng minh danh tính, có thể đã bị xóa |
| Quyền được cấp | `getAuthorities()` | Tập `GrantedAuthority` dùng làm đầu vào cho phân quyền |
| Trạng thái | `isAuthenticated()` | Trạng thái tin cậy theo cách triển khai `Authentication` |
| Tên chủ thể | `getName()` | Tên mà đối tượng đưa ra để nhận diện |
| Chi tiết khác | `getDetails()` | Dữ liệu bổ sung do cơ chế xác thực điền, không phải nơi mặc định để lưu quyền |

Phân biệt trước/sau một cách cụ thể:

~~~text
Trước khi kiểm tra:
  principal       = "mai"                (chưa được xác minh)
  credentials     = mật khẩu vừa nhận
  isAuthenticated = false
  authorities     = []

Sau khi provider xác minh thành công (minh họa):
  principal       = "mai" hoặc UserDetails của Mai
  credentials     = null                 (thường gặp do xóa dữ liệu nhạy cảm)
  isAuthenticated = true
  authorities     = ["ROLE_EDITOR", "article:read"]
~~~

Một `AuthenticationManager` như `ProviderManager` chọn provider phù hợp để xác thực. Khi thông tin không hợp lệ, `authenticate(...)` thường **ném `AuthenticationException`**; không nên hình dung sai rằng mọi lần đăng nhập thất bại đều tạo một kết quả bình thường với cờ `false`.

**Ranh giới tin cậy:** mã xử lý request chỉ được tạo dữ liệu đầu vào chưa xác thực. Chỉ thành phần xác thực được tin cậy mới nên đánh dấu kết quả đã xác thực dựa trên bằng chứng đã kiểm tra. Việc tạo `Authentication` với `isAuthenticated=true` từ dữ liệu tùy ý mà client gửi có thể bỏ qua toàn bộ cơ chế bảo vệ.

### SecurityContext giữ Authentication để dùng ở đâu?

Trong ứng dụng **servlet** thông thường, sau khi xác thực thành công, bộ lọc Spring Security có thể đưa kết quả vào `SecurityContext`; `SecurityContextHolder` giúp mã đang xử lý truy cập ngữ cảnh hiện tại. Đoạn sau chỉ là mã bên trong ứng dụng đã tích hợp Spring Security, không phải chương trình độc lập:

~~~java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String displayName = current.getName();
    // displayName dùng cho hiển thị/audit phù hợp;
    // quyền truy cập do Spring Security quyết định.
}
~~~

Hai kiểu được import từ `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. `getAuthentication()` có thể `null`, hoặc mang token anonymous tùy cấu hình. Với ứng dụng reactive, ngữ cảnh bảo mật dùng cơ chế gắn với Reactor thay vì giả định `ThreadLocal` của servlet.

**Bẫy quan trọng:** `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` trong cơ chế nội bộ. Do đó điều kiện viết tay `current != null && current.isAuthenticated()` không phải phép kiểm đáng tin để xác định “người dùng thực đã đăng nhập”. Dùng quy tắc `authenticated()` hoặc thành phần đánh giá loại xác thực mà Spring Security cung cấp. Dù đã xác thực, quyền truy cập tài nguyên vẫn phải qua phân quyền.

## 5. Authority: quyền được cấp để phân quyền

**Authority** mô tả một quyền/nhãn quyền mà hệ thống công nhận cho chủ thể. Spring Security biểu diễn nó qua giao diện `GrantedAuthority`, thường dùng lớp `SimpleGrantedAuthority` chứa một chuỗi, ví dụ:

- `ROLE_EDITOR`: vai trò biên tập viên.
- `article:read`: quyền đọc bài viết.
- `article:publish`: quyền xuất bản bài viết.
- `SCOPE_messages.read`: ví dụ một scope được ánh xạ thành authority trong một số cấu hình OAuth2.

`Authentication#getAuthorities()` trả về danh sách các `GrantedAuthority`. Danh sách này có thể rỗng ngay cả khi một người đã được xác thực. Việc có quyền nào phụ thuộc vào nguồn cấp và cách ánh xạ quyền đã được cấu hình; **không được tin các chuỗi quyền tự do do client gửi**.

### Role không phải một loại danh tính khác

Trong cấu hình phổ biến, **role là quy ước về tên của authority** với tiền tố `ROLE_`. Ví dụ role `EDITOR` thường tương ứng chuỗi authority `ROLE_EDITOR`. So sánh hai kiểu kiểm tra:

| Điều kiện | Chuỗi cần có trong `GrantedAuthority` với cấu hình mặc định |
| --- | --- |
| `hasAuthority("article:read")` | `article:read` |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` |
| `hasRole("EDITOR")` | `ROLE_EDITOR` |
| `hasAuthority("EDITOR")` | `EDITOR` |

`hasRole` mặc định thêm `ROLE_`; `hasAuthority` so khớp đúng chuỗi truyền vào. Tiền tố này có thể được cấu hình khác. Quyền `ROLE_EDITOR` không mặc nhiên bao gồm `ROLE_ADMIN`; `article:read` cũng không tự mang theo `article:publish`. Nếu có phân cấp vai trò hay quan hệ giữa các quyền, ứng dụng phải thiết lập chúng rõ ràng.

**Authentication trả lời ai đã được nhận diện và trong trạng thái nào; authorization dùng authorities và các điều kiện khác để xác định một thao tác có được phép hay không.** Một principal đã xác thực không mặc nhiên được truy cập mọi tài nguyên.

## 6. Ví dụ Java 17+ có thể chạy để quan sát bốn thuật ngữ

Ví dụ sử dụng các lớp Spring Security thật, quan sát một yêu cầu chưa xác thực và **mô phỏng** một kết quả đã xác thực. Đoạn tạo kết quả chỉ để học cấu trúc dữ liệu: nó **không kiểm tra mật khẩu** và không phải cách triển khai đăng nhập production.

Tạo một dự án Gradle với `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'AuthTermsDemo'
}
~~~

Tạo tệp `src/main/java/AuthTermsDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthTermsDemo {
    public static void main(String[] args) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-secret");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.principal=" + request.getPrincipal());
        System.out.println("request.hasCredentials=" + (request.getCredentials() != null));
        System.out.println("request.authorities=" + request.getAuthorities().size());

        // Minh họa kết quả một provider tin cậy có thể tạo ra.
        // Chương trình này KHÔNG hề kiểm tra mật khẩu.
        Authentication result =
                UsernamePasswordAuthenticationToken.authenticated(
                        "mai",
                        null,
                        List.of(
                                new SimpleGrantedAuthority("ROLE_EDITOR"),
                                new SimpleGrantedAuthority("article:read")));

        String labels = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.joining(", "));

        boolean mayRead = result.getAuthorities().stream()
                .anyMatch(a -> "article:read".equals(a.getAuthority()));

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.hasCredentials=" + (result.getCredentials() != null));
        System.out.println("result.authorities=" + labels);
        System.out.println("result.mayRead=" + mayRead);
    }
}
~~~

Với JDK 17 trở lên và Gradle đã cài đặt, chạy từ thư mục dự án:

~~~bash
gradle run --quiet
~~~

Đầu ra của chương trình:

~~~text
request.authenticated=false
request.principal=mai
request.hasCredentials=true
request.authorities=0
result.authenticated=true
result.name=mai
result.hasCredentials=false
result.authorities=ROLE_EDITOR, article:read
result.mayRead=true
~~~

Diễn giải kết quả: `request` chứa principal do người dùng khai và credentials chưa được kiểm tra; vì thế `authenticated=false`. Trong `result` minh họa, cờ được đặt `true`, credentials là `null`, còn authorities có `ROLE_EDITOR` và `article:read`. Phép `mayRead` chỉ so khớp một chuỗi quyền để minh họa cách đọc `GrantedAuthority`; trong ứng dụng thật, hãy để cơ chế authorization của Spring Security xử lý chính sách truy cập. Ví dụ cố ý chỉ in **sự hiện diện** của credentials, không in bí mật.

Mẫu độc lập này khóa phiên bản `spring-security-core:6.5.11` để người đọc có thể chạy lại. Trong dự án Spring Boot dùng starter bảo mật, hãy theo phiên bản do Spring Boot quản lý, tránh tự ý ghi đè phiên bản phụ thuộc.

## 7. Bốn thuật ngữ đi cùng một quyết định truy cập

Giả sử người dùng Mai đã xác thực thành công và có authorities `ROLE_EDITOR` và `article:read`:

| Tác vụ | Quy tắc | Kết quả theo dữ liệu giả định |
| --- | --- | --- |
| Đọc bài viết | `hasAuthority("article:read")` | Cho phép |
| Xuất bản bài viết | `hasAuthority("article:publish")` | Từ chối vì thiếu quyền |
| Mở phần biên tập | `hasRole("EDITOR")` | Cho phép theo tiền tố mặc định |
| Quản trị hệ thống | `hasRole("ADMIN")` | Từ chối vì thiếu `ROLE_ADMIN` |

Một phần cấu hình servlet tương ứng có thể viết như sau. Đây là **mảnh cấu hình cần nằm trong một `SecurityFilterChain` hợp lệ**, không phải tệp Java độc lập:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/articles/**").hasAuthority("article:read")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Ngoài authority, một tài nguyên có thể đòi hỏi người truy cập là chủ sở hữu, thuộc đúng nhóm khách hàng hoặc đáp ứng ràng buộc nghiệp vụ. Vì vậy một quyền chung không tự thay thế mọi bước kiểm tra theo đối tượng cụ thể.

## 8. Các nhầm lẫn phổ biến

1. **“Có principal là đã đăng nhập.”** Chưa đúng: đó có thể chỉ là tên người dùng tự khai trước khi xác thực.
2. **“Có credentials là đã xác thực.”** Chưa đúng: bằng chứng phải được provider kiểm tra.
3. **“`getCredentials() == null` nghĩa là chưa đăng nhập.”** Không đúng: bí mật thường bị xóa sau xác thực.
4. **“`Authentication` và principal là một.”** Không đúng: `Authentication` là đối tượng rộng hơn, chứa principal cùng trạng thái, credentials và authorities.
5. **“`isAuthenticated()==true` cho phép đi khắp hệ thống.”** Không đúng: cần phân quyền; với anonymous token còn phải xét loại trạng thái.
6. **“`hasRole("EDITOR")` kiểm tra chuỗi `EDITOR`.”** Mặc định nó kiểm tra `ROLE_EDITOR`; `hasAuthority` đối chiếu đúng chuỗi nhận vào.
7. **“Một role luôn bao gồm mọi role yếu hơn.”** Không mặc định; thứ bậc phải được cấu hình.
8. **“Có thể nhận danh sách quyền trực tiếp từ JSON của người dùng.”** Không an toàn: chỉ quyền được thiết lập từ nguồn tin cậy mới được dùng để cấp truy cập.
9. **“Có `article:read` chắc chắn đọc được mọi bài.”** Chưa đủ: có thể còn điều kiện về chủ sở hữu hoặc phạm vi dữ liệu.

## 9. Tự kiểm tra nhận thức

**Tình huống A.** Mai nhập `mai` và một mật khẩu sai. Principal vẫn là tên được khai báo; credentials vẫn được gửi, nhưng quá trình xác thực không tạo được kết quả đáng tin. Không được cấp quyền chỉ vì đã có hai dữ liệu đầu vào.

**Tình huống B.** Sau xác thực, `getCredentials()` là `null`, `getAuthorities()` chứa `article:read`. Hai điều này không mâu thuẫn: có thể xóa bí mật nhưng vẫn giữ danh tính và quyền cần thiết.

**Tình huống C.** Một `Authentication` có `ROLE_READER`, còn tài nguyên yêu cầu `hasAuthority("article:publish")`. Kể cả người dùng đã xác thực, chính sách này vẫn từ chối vì không có authority được yêu cầu.

**Tình huống D.** Dưới tiền tố role mặc định, `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` cùng cần nhãn `ROLE_ADMIN`; `hasAuthority("ADMIN")` đòi một nhãn khác.

Khi đọc mã Spring Security, hãy tự hỏi theo thứ tự: **principal nào đang được nói đến, credentials nào được kiểm tra, thành phần nào tạo `Authentication` đáng tin và quy tắc nào đối chiếu authorities với hành động cần bảo vệ?** Trả lời đủ bốn câu hỏi giúp tách rõ lỗi xác thực với lỗi phân quyền.

### Tài liệu tra cứu

- [Spring Security — `Authentication` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
