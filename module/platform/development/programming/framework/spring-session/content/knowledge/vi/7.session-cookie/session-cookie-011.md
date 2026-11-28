# Xóa cookie đúng tên, miền, đường dẫn và kiểm tra cookie trùng

Cookie phiên là phương tiện để trình duyệt gửi session ID về ứng dụng. Với Spring Session, cookie thường mang tên SESSION và chứa một ID được repository dùng để tìm dữ liệu phiên trong Redis, JDBC hoặc kho lưu trữ khác. Khi đăng xuất, đổi tên cookie, thay context path hoặc chuyển ứng dụng sang domain mới, việc xóa cookie phải khớp với phạm vi cookie đã được tạo. Nếu tên đúng nhưng domain hoặc path khác, trình duyệt có thể giữ cookie cũ và tiếp tục gửi nó trong request.

Bài này giải thích cách trình duyệt xác định phạm vi cookie, cách Spring Session tạo và xóa cookie, cách phát hiện nhiều cookie cùng tên và cách kiểm thử response thực tế. Trọng tâm là xử lý đúng bộ ba tên, domain và path, đồng thời hiểu những thuộc tính khác như Secure, HttpOnly và SameSite.

## 1. Cookie được nhận diện theo phạm vi nào?

Một cookie lưu trong trình duyệt có nhiều thuộc tính. Những thuộc tính quyết định phạm vi lưu trữ và gửi cookie gồm:

- **Name:** tên cookie, ví dụ SESSION.
- **Domain:** host hoặc miền mà cookie áp dụng.
- **Path:** đường dẫn URL mà cookie áp dụng.
- **Expires/Max-Age:** thời hạn lưu ở phía trình duyệt.
- **Secure:** chỉ gửi cookie qua kết nối bảo mật HTTPS.
- **HttpOnly:** ngăn JavaScript đọc cookie qua API trình duyệt.
- **SameSite:** giới hạn việc gửi cookie trong một số ngữ cảnh điều hướng cross-site.

Đối với việc thay thế hoặc xóa một cookie đã tồn tại, bộ ba cần đối chiếu trước tiên là **name, domain và path**. Trình duyệt có thể lưu nhiều cookie cùng tên nếu chúng thuộc các phạm vi domain hoặc path khác nhau. Khi phát Set-Cookie để xóa, ứng dụng cần phát lệnh hết hạn cho đúng phạm vi của từng cookie cũ.

Ví dụ, trình duyệt có thể lưu đồng thời:

| Name | Domain | Path | Phạm vi gửi |
|---|---|---|---|
| SESSION | Host-only: app.example.com | / | Mọi request trên host theo path / |
| SESSION | example.com | /admin | Request tới domain và nhánh /admin |
| SESSION | Host-only: app.example.com | /shop | Request tới app.example.com trong nhánh /shop |

Ba cookie trên có cùng tên nhưng là các cookie khác nhau. Xóa cookie SESSION ở path / không tự động xóa cookie SESSION ở path /admin hoặc /shop.

Tên cookie phân biệt chữ hoa và chữ thường. SESSION và session không phải cùng một tên. Domain và path cũng phải được cấu hình nhất quán giữa lúc tạo và lúc xóa.

### Host-only cookie và Domain cookie

Nếu Set-Cookie không có thuộc tính Domain, trình duyệt tạo host-only cookie: cookie chỉ được gửi tới host đã phát nó. Ví dụ, app.example.com phát cookie không có Domain thì cookie đó chỉ áp dụng cho app.example.com.

Nếu response có Domain=example.com, cookie có thể được gửi tới example.com và các subdomain phù hợp như app.example.com hoặc api.example.com. Không nên đặt Domain rộng hơn phạm vi cần thiết vì cookie phiên là thông tin xác thực dạng bearer credential.

Trong các trình duyệt hiện đại, dấu chấm đứng đầu trong .example.com không tạo ra một phạm vi riêng so với example.com. Điều quan trọng là cookie host-only hay cookie có Domain attribute, cùng miền được chỉ định.

Khi xóa cookie host-only, hãy phát cookie hết hạn mà không thêm Domain. Khi xóa cookie có Domain, hãy phát cookie hết hạn với đúng Domain đã dùng lúc tạo. Không thể giả định rằng xóa cookie ở host-only sẽ xóa cookie có Domain hoặc ngược lại.

### Path cookie

Path xác định những request path nào được gửi kèm cookie. Ví dụ:

- Path=/ áp dụng cho toàn bộ ứng dụng trên host.
- Path=/portal áp dụng cho /portal và các đường dẫn con phù hợp.
- Path=/admin áp dụng cho nhánh quản trị.

Nếu không chỉ định Path khi tạo cookie, trình duyệt tự suy ra default-path từ URL request đã tạo cookie. Cách suy ra này dễ gây khác biệt giữa các endpoint. Vì vậy, với cookie session, nên cấu hình path rõ ràng và dùng cùng giá trị trong suốt vòng đời cookie.

Path không phải cơ chế phân quyền. Một ứng dụng khác trên cùng host có thể có path riêng; việc cookie không được gửi tới path khác không thay thế xác thực và kiểm tra quyền tại máy chủ.

## 2. Vì sao xóa cookie sai path hoặc domain không có tác dụng?

Cookie được xóa bằng cách gửi một Set-Cookie có cùng phạm vi lưu trữ, nhưng giá trị rỗng hoặc giá trị không còn được sử dụng và thời hạn đã hết. Cách phổ biến là:

- Giữ đúng cookie name.
- Giữ đúng Domain attribute hoặc giữ trạng thái host-only như cookie cũ.
- Giữ đúng Path.
- Đặt Max-Age=0 hoặc Expires là thời điểm trong quá khứ.

Ví dụ cookie ban đầu:

~~~http
Set-Cookie: SESSION=abc123; Path=/portal; Domain=example.com; Secure; HttpOnly; SameSite=Lax
~~~

Lệnh xóa tương ứng:

~~~http
Set-Cookie: SESSION=; Path=/portal; Domain=example.com; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Secure; HttpOnly; SameSite=Lax
~~~

Nếu ứng dụng gửi lệnh xóa với Path=/, cookie ban đầu ở Path=/portal có thể vẫn còn. Tương tự, nếu cookie cũ là host-only nhưng lệnh xóa thêm Domain=example.com, trình duyệt có thể coi đó là một cookie có phạm vi khác và không xóa cookie host-only ban đầu.

Có thể phát nhiều header Set-Cookie trong cùng response để xóa nhiều biến thể cookie. Không nối nhiều cookie vào một header Set-Cookie duy nhất bằng dấu phẩy; Set-Cookie là header có quy tắc riêng và mỗi cookie cần một header riêng.

Không dùng header Cookie của request để suy ra Domain hoặc Path. Trình duyệt chỉ gửi các cặp name=value trong Cookie header; nó không gửi lại thuộc tính Domain, Path, Expires, Secure, HttpOnly hay SameSite. Máy chủ cần biết cấu hình cookie cũ từ cấu hình ứng dụng, deployment hoặc hồ sơ migration.

## 3. Spring Session tạo và xóa cookie như thế nào?

Trong ứng dụng Servlet, Spring Session dùng HttpSessionIdResolver để đọc session ID từ request và ghi/xóa session ID trên response. Resolver mặc định thường là CookieHttpSessionIdResolver. Resolver này sử dụng CookieSerializer để chuyển session ID thành cookie HTTP.

Với DefaultCookieSerializer, các thuộc tính thường được cấu hình gồm:

- cookieName: tên cookie.
- cookiePath: path.
- domainName hoặc domainNamePattern: phạm vi domain.
- useSecureCookie: thuộc tính Secure.
- useHttpOnlyCookie: thuộc tính HttpOnly.
- sameSite: chính sách SameSite.
- cookieMaxAge: thời hạn lưu cookie ở trình duyệt.

Tên cookie mặc định thường dùng bởi Spring Session là SESSION. Khi ứng dụng thay đổi tên, path hoặc domain, hãy cập nhật cấu hình serializer và kế hoạch xóa các cookie đã được phát theo cấu hình cũ.

Ví dụ cấu hình serializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    public CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
~~~

Ví dụ trên đặt path là /, bật HttpOnly và Secure, và dùng SameSite=Lax. Nếu ứng dụng cần cookie dùng chung giữa các subdomain, có thể cấu hình domain rõ ràng, nhưng chỉ khi thực sự cần:

~~~java
serializer.setDomainName("example.com");
~~~

Khi không cần chia sẻ giữa subdomain, giữ cookie host-only bằng cách không đặt Domain thường là lựa chọn có phạm vi hẹp hơn.

Trong môi trường phát triển HTTP localhost, bật Secure có thể khiến trình duyệt không gửi cookie trên một số cấu hình. Production nên dùng HTTPS và Secure=true. Có thể dùng profile cấu hình riêng cho local development, nhưng không để cấu hình production vô tình tắt Secure.

### Spring Session tự hết hạn cookie khi invalidate

Khi session bị invalidate hoặc bị xóa qua API repository, Spring Session có thể gọi resolver để hết hạn cookie trên response hiện tại. Cookie serializer phát một Set-Cookie có cùng tên và phạm vi mà nó đang cấu hình, với thời hạn bằng 0.

Điều này chỉ xử lý cookie theo cấu hình hiện hành của ứng dụng. Nếu trình duyệt còn cookie cũ được phát bởi cấu hình trước đó, chẳng hạn tên vẫn là SESSION nhưng path cũ là /portal, trong khi serializer hiện tại đã đổi sang /, lệnh xóa mới có thể không xóa được cookie cũ. Khi migration, ứng dụng phải phát lệnh hết hạn cho các phạm vi cũ đã biết.

Không phải request nào repository trả về null cũng tự động làm trình duyệt xóa cookie. Khi cookie cũ trỏ tới session đã hết hạn, Spring Session có thể coi request như không có session hợp lệ; việc có gửi Set-Cookie xóa cookie hay không phụ thuộc resolver và luồng xử lý cụ thể. Hãy kiểm tra response thực tế bằng integration test hoặc công cụ trình duyệt.

## 4. Xóa cookie khi đăng xuất

Khi người dùng đăng xuất, cần xử lý cả hai phía:

1. Xóa hoặc invalidate session ở repository để ID cũ không còn truy cập được.
2. Gửi Set-Cookie hết hạn để trình duyệt ngừng gửi cookie cũ.

Spring Security có thể invalidate HttpSession và xóa cookie trong logout handler. Ví dụ:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

deleteCookies("SESSION") hữu ích với cấu hình cookie đơn giản. Tuy nhiên, khi cookie được tạo với Domain hoặc Path tùy chỉnh, không nên mặc định rằng thao tác xóa theo tên sẽ khớp mọi biến thể đã tồn tại. Hãy kiểm tra header Set-Cookie mà logout handler phát ra. Nếu Path/Domain không khớp cookie ban đầu, trình duyệt vẫn giữ cookie đó.

Với Spring Session, để resolver thực hiện việc hết hạn cookie theo serializer đang dùng thường giúp tránh lệch cấu hình. Nếu ứng dụng cần xóa thêm cookie cũ hoặc cookie có phạm vi khác, hãy bổ sung handler riêng với đầy đủ thuộc tính.

### Tạo Set-Cookie hết hạn với Spring ResponseCookie

Spring Framework cung cấp ResponseCookie để xây dựng header Set-Cookie. Ví dụ xóa cookie có Domain=example.com và Path=/portal:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

import java.time.Duration;

public void expirePortalSessionCookie(HttpServletResponse response) {
    ResponseCookie expired = ResponseCookie.from("SESSION", "")
            .domain("example.com")
            .path("/portal")
            .maxAge(Duration.ZERO)
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax")
            .build();

    response.addHeader(HttpHeaders.SET_COOKIE, expired.toString());
}
~~~

Đối với cookie host-only, bỏ lời gọi domain(...). Phải dùng đúng path đã tạo cookie. Ví dụ trên chỉ minh họa một cookie cụ thể; nếu trước đây ứng dụng đã phát cookie SESSION ở nhiều path hoặc domain, hãy phát một header hết hạn cho từng phạm vi cần dọn.

ResponseCookie giúp tạo header rõ ràng, nhưng không tự tìm và xóa mọi cookie cũ. Ứng dụng phải biết những biến thể cookie từng phát ra. Cũng cần tránh gửi nhiều header xóa trùng lặp không cần thiết.

### Cookie và session là hai việc riêng

Xóa cookie ở trình duyệt không xóa session trong Redis/JDBC. Người dùng có thể sao chép cookie trước đó hoặc một tab khác vẫn giữ ID cũ. Vì vậy, logout phải invalidate session ở repository. Ngược lại, xóa session ở repository không xóa cookie khỏi các trình duyệt khác; các trình duyệt đó chỉ nhận biết session đã mất khi gửi request tiếp theo.

Không dùng việc xóa cookie làm cơ chế thu hồi xác thực duy nhất. Repository phải từ chối session ID đã bị invalidate hoặc hết hạn.

## 5. Phát hiện cookie trùng tên

Trình duyệt có thể gửi nhiều cookie cùng tên nếu chúng được lưu ở path hoặc domain khác nhau. Ví dụ, request tới /portal/orders có thể mang cả cookie SESSION ở path=/ và SESSION ở path=/portal.

Header request có thể có dạng:

~~~http
Cookie: SESSION=old-value; SESSION=new-value
~~~

Header này không cho máy chủ biết cookie nào được tạo ở path nào hoặc domain nào. Domain và Path không xuất hiện trong Cookie request header. Vì vậy, khi có cookie trùng tên, không thể dựa vào header để xác định phạm vi nguồn gốc.

Trong Servlet, request.getCookies() trả về mảng Cookie. Có thể duyệt để đếm cookie cùng tên:

~~~java
int sessionCookieCount = 0;

Cookie[] cookies = request.getCookies();
if (cookies != null) {
    for (Cookie cookie : cookies) {
        if ("SESSION".equals(cookie.getName())) {
            sessionCookieCount++;
        }
    }
}

if (sessionCookieCount > 1) {
    // Ghi nhận trạng thái trùng tên, không ghi giá trị cookie.
}
~~~

Không log giá trị cookie để chẩn đoán. Session ID là bearer credential; người có ID hợp lệ có thể chiếm quyền sử dụng session tương ứng. Chỉ log tên cookie, số lượng, endpoint, instance và mã tương quan đã được kiểm soát.

Spring Session CookieHttpSessionIdResolver đọc cookie theo tên được cấu hình. Khi request chứa nhiều cookie cùng tên, resolver có thể nhận nhiều giá trị. Không nên phụ thuộc vào thứ tự trình duyệt gửi cookie hoặc giả định giá trị đầu tiên luôn là cookie đúng. Hành vi cụ thể còn phụ thuộc resolver và cách Servlet container phân tích header.

Cách xử lý bền vững là loại bỏ các cookie trùng tên ở những phạm vi cũ, rồi giữ lại một cookie có phạm vi được định nghĩa rõ ràng. Nếu phải hỗ trợ migration, hãy xác định rõ các path/domain cũ đã phát và phát Set-Cookie hết hạn cho từng phạm vi đó.

### Không thể phân biệt Domain/Path từ request Cookie

Một request Cookie header chỉ có name=value. Nó không có metadata Domain hoặc Path. Nếu hai cookie cùng tên được gửi, server nhìn thấy hai giá trị nhưng không thể xác định chính xác giá trị nào đến từ path nào chỉ dựa trên header.

Do đó, đừng viết code tự chọn cookie bằng cách đoán rằng cookie có ID dài hơn, mới hơn hoặc đứng trước là đúng. Nếu có nhiều cookie SESSION, cần xử lý tình trạng cấu hình trùng và làm sạch các cookie cũ ở response.

## 6. Đổi cookie name, domain hoặc path khi triển khai

Thay đổi cookie scope là một migration, đặc biệt khi ứng dụng đang có người dùng đăng nhập và nhiều tab hoạt động.

Ví dụ trước đây ứng dụng phát:

~~~http
Set-Cookie: SESSION=...; Path=/portal; Domain=example.com; Secure; HttpOnly
~~~

Sau triển khai, cấu hình mới là:

~~~http
Set-Cookie: SESSION=...; Path=/; Secure; HttpOnly
~~~

Cookie mới là host-only ở path=/; cookie cũ có Domain=example.com và Path=/portal vẫn có thể còn trong trình duyệt. Trình duyệt có thể gửi cả hai khi request tới /portal. Nếu resolver đọc nhiều giá trị cùng tên, request có thể gặp tình trạng mơ hồ.

Một kế hoạch migration an toàn:

1. Ghi lại cấu hình cũ: cookie name, Domain attribute có được đặt hay không, Path và các biến thể từng phát hành.
2. Chọn cấu hình mới và cố định cookie name, Domain, Path cho mọi instance.
3. Trong giai đoạn chuyển tiếp, phát Set-Cookie hết hạn cho từng phạm vi cũ đã biết.
4. Chỉ phát cookie mới theo phạm vi mới.
5. Kiểm tra response có nhiều header Set-Cookie và xác nhận trình duyệt đã loại bỏ cookie cũ.
6. Theo dõi số request có cookie trùng tên và bỏ hỗ trợ biến thể cũ khi thời gian chuyển đổi kết thúc.

Nếu thay đổi tên từ JSESSIONID sang SESSION hoặc ngược lại, cookie cũ có tên cũ sẽ không tự biến mất. Cần hết hạn riêng cookie cũ theo đúng Domain/Path đã dùng. Việc đổi tên cookie không xóa session dữ liệu phía máy chủ; cần quyết định riêng liệu các session cũ có tiếp tục được chấp nhận hay cần thu hồi.

Trong rolling deployment nhiều instance, tất cả node phải có cấu hình cookie tương thích trong cùng giai đoạn. Nếu node A phát Path=/portal còn node B phát Path=/, trình duyệt có thể tích lũy cookie trùng tên tùy request đi qua node nào. Dùng cấu hình tập trung và triển khai đồng bộ để tránh mỗi instance phát một phạm vi khác nhau.

## 7. Các thuộc tính cookie khác cần giữ nhất quán

Name, Domain và Path quyết định cookie nào được thay thế hoặc xóa. Các thuộc tính khác không thay đổi bộ nhận diện cookie theo cùng cách, nhưng vẫn cần được cấu hình phù hợp:

| Thuộc tính | Tác dụng | Lưu ý khi xóa |
|---|---|---|
| Secure | Chỉ gửi cookie qua HTTPS | Giữ cấu hình phù hợp để header hết hạn được xử lý trên luồng HTTPS |
| HttpOnly | Ngăn JavaScript đọc cookie | Nên giữ HttpOnly cho cookie phiên |
| SameSite | Điều khiển việc gửi cookie trong ngữ cảnh cross-site | Cần phù hợp với luồng SSO/điều hướng và cấu hình ban đầu |
| Max-Age/Expires | Xác định thời gian lưu cookie | Dùng Max-Age=0 hoặc Expires ở quá khứ để hết hạn |
| Priority | Gợi ý mức ưu tiên lưu cookie cho trình duyệt hỗ trợ | Không thay thế Name/Domain/Path |
| Partitioned | Cookie phân vùng theo top-level site trong trình duyệt hỗ trợ | Cần hiểu partition context khi triển khai luồng nhúng/cross-site |

Secure, HttpOnly và SameSite không thể thay thế việc khớp Domain và Path. Một cookie có đủ Secure và HttpOnly nhưng được xóa ở path sai vẫn có thể còn trong trình duyệt.

Đối với cookie phiên xác thực, thường nên:

- Bật Secure khi ứng dụng chạy qua HTTPS.
- Bật HttpOnly để script phía client không đọc được session ID.
- Chọn SameSite phù hợp; Lax thường phù hợp cho nhiều ứng dụng web truyền thống, còn SSO hoặc luồng cross-site có thể cần thiết kế khác.
- Có CSRF protection phù hợp; SameSite không thay thế toàn bộ cơ chế CSRF.
- Giữ cookie name và path ổn định trong toàn bộ cụm instance.

## 8. Kiểm tra cookie trong trình duyệt và HTTP response

Để xác định vì sao cookie cũ vẫn còn, cần kiểm tra cả nơi trình duyệt lưu cookie và header request/response.

### Dùng Developer Tools

Trong Chrome hoặc Edge:

1. Mở Developer Tools.
2. Chọn tab Application.
3. Mở Storage > Cookies và chọn đúng origin.
4. Kiểm tra Name, Domain, Path, Expires/Max-Age, Secure, HttpOnly và SameSite.
5. Tìm các dòng có cùng tên SESSION nhưng khác Domain hoặc Path.
6. Mở tab Network, chọn request bị lỗi và xem Request Headers/Cookies để biết trình duyệt đã gửi cookie nào.
7. Chọn response đăng xuất hoặc response đổi cookie, kiểm tra từng header Set-Cookie.
8. Tải lại trang hoặc gửi request tiếp theo để xác nhận cookie cũ đã biến mất.

Khi có nhiều cookie cùng tên, bảng Application hữu ích hơn việc chỉ nhìn một giá trị trong request header vì bảng hiển thị Domain và Path của từng cookie. Không chia sẻ ảnh chụp hoặc log chứa giá trị cookie thật.

### Dùng curl

Có thể kiểm tra response header bằng curl mà không cần in nội dung cookie ra log công khai:

~~~bash
curl -i -X POST https://app.example.com/logout
~~~

Để lưu cookie jar và gửi lại trong request tiếp theo:

~~~bash
curl -c cookies.txt -b cookies.txt -i https://app.example.com/account
~~~

Cookie jar có thể chứa session ID thật. Hãy bảo vệ file, không commit vào Git và xóa sau khi kiểm thử. Khi debug, tập trung vào tên, Domain, Path và trạng thái hết hạn; che giá trị cookie trước khi chia sẻ.

Nếu cần xem Set-Cookie, kiểm tra response headers tại máy phát triển. Một response có thể có nhiều dòng Set-Cookie; cần xác nhận mỗi dòng xóa đúng một biến thể cookie cũ. Đừng gộp các dòng thành một chuỗi để phân tích bằng cách tách dấu phẩy vì thuộc tính Expires có dấu phẩy bên trong.

## 9. Kiểm thử xóa cookie và cookie trùng tên

Kiểm thử nên xác nhận header Set-Cookie được phát ra với đúng phạm vi và xác nhận trình duyệt/client loại bỏ đúng cookie. MockMvc có thể kiểm tra response header:

~~~java
mockMvc.perform(post("/logout"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        HttpHeaders.SET_COOKIE,
        org.hamcrest.Matchers.containsString("Path=/portal")
    ));
~~~

Đây là ví dụ rút gọn; nếu response có nhiều header Set-Cookie, hãy lấy danh sách header thay vì giả định chỉ có một giá trị. Với cookie deletion, cần kiểm tra:

- Tên cookie đúng và phân biệt chữ hoa/thường.
- Domain có mặt hoặc vắng mặt đúng như cookie gốc.
- Path khớp cookie gốc.
- Max-Age bằng 0 hoặc Expires nằm trong quá khứ.
- Secure/HttpOnly/SameSite theo chính sách cookie.
- Response có một Set-Cookie riêng cho mỗi phạm vi cũ cần xóa.

Có thể kiểm tra cookie trùng tên bằng cách gửi hai cookie cùng tên trong một request:

~~~java
mockMvc.perform(get("/portal")
        .cookie(
            new Cookie("SESSION", "old-id"),
            new Cookie("SESSION", "new-id")
        ))
    .andDo(result -> {
        Cookie[] cookies = result.getRequest().getCookies();
        // Kiểm tra số lượng cookie SESSION; không ghi giá trị ra log.
    });
~~~

MockMvc xác minh ứng dụng và resolver nhận được request mô phỏng. Nó không thay thế kiểm thử trình duyệt thực tế về quy tắc lưu cookie theo Domain/Path, vì Cookie object gửi trong test không mô phỏng đầy đủ cookie jar của trình duyệt. Với migration domain/path, nên có kiểm thử end-to-end trên trình duyệt hoặc client có cookie jar.

### Ma trận kiểm thử đề xuất

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Xóa cookie path=/ | Cookie gốc path=/ | Response hết hạn đúng SESSION ở path=/ |
| Xóa cookie path=/portal | Cookie gốc path=/portal | Response hết hạn đúng SESSION ở path=/portal |
| Xóa host-only cookie | Cookie gốc không có Domain | Response hết hạn không thêm Domain |
| Xóa domain cookie | Cookie gốc Domain=example.com | Response hết hạn có cùng Domain |
| Hai cookie cùng tên khác path | SESSION ở / và /portal | Cả hai biến thể được phát lệnh hết hạn riêng |
| Cookie name thay đổi | Có SESSION cũ, cấu hình mới APPSESSION | Xóa SESSION cũ và chỉ phát APPSESSION mới |
| Logout nhiều lần | Gửi logout khi không còn session | Không phát sinh lỗi invalidate; response ổn định |
| Rolling deployment | Hai instance dùng cùng cấu hình cookie | Không tạo thêm biến thể cookie khác scope |
| SameSite/HTTPS | Request qua HTTPS và luồng cross-site thực tế | Cookie được gửi đúng theo chính sách đã chọn |

## 10. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đăng xuất nhưng cookie vẫn hiện trong Application | Path hoặc Domain của Set-Cookie xóa không khớp | Đối chiếu cookie gốc và header xóa |
| Request gửi hai SESSION | Cookie cũ cùng tên còn ở path/domain khác | Phát header hết hạn cho từng scope cũ |
| Logout xóa session trong Redis nhưng browser vẫn gửi ID | Repository invalidate thành công, cookie chưa được xóa | Kiểm tra resolver và response Set-Cookie |
| Browser không gửi cookie | Domain/path không khớp, Secure/HTTPS hoặc SameSite | Kiểm tra URL, proxy và thuộc tính cookie |
| Chỉ một số instance gặp lỗi session | Cấu hình cookie name/path/domain khác nhau giữa node | Đồng bộ cấu hình và rolling deployment |
| Xóa cookie mới nhưng cookie cũ vẫn tồn tại | Chỉ xóa scope hiện hành, bỏ sót scope migration | Lập danh sách các biến thể từng phát |
| Header Set-Cookie bị ghi đè | Code dùng setHeader thay vì addHeader khi cần nhiều cookie | Dùng addHeader cho từng Set-Cookie riêng |
| Cookie bị lộ trong log | Debug ghi toàn bộ Cookie header hoặc Cookie value | Che giá trị; chỉ ghi tên và số lượng |

Một lỗi thường gặp trong code Servlet là dùng response.setHeader("Set-Cookie", value) nhiều lần. Lệnh setHeader có thể thay thế header đã đặt trước đó. Khi cần xóa nhiều cookie trong cùng response, dùng response.addHeader("Set-Cookie", value) hoặc API tương đương để giữ nhiều header Set-Cookie riêng biệt.

## 11. Quy trình chuẩn khi thay đổi hoặc xóa cookie session

Trước khi thay đổi cấu hình cookie, hãy lập một bảng các biến thể đang tồn tại:

| Ứng dụng | Cookie name | Domain | Path | Hành động |
|---|---|---|---|---|
| Ứng dụng chính | SESSION | Host-only | / | Giữ hoặc xóa theo mục tiêu |
| Portal cũ | SESSION | example.com | /portal | Phát Set-Cookie hết hạn |
| Admin cũ | SESSION | Host-only | /admin | Phát Set-Cookie hết hạn |

Sau đó thực hiện theo trình tự:

1. Xác định cookie nào được phát bởi cấu hình hiện tại và các phiên bản trước.
2. Kiểm tra cookie jar của trình duyệt và request header để phát hiện trùng tên.
3. Xác định chính xác Domain attribute có được đặt hay không và Path của từng biến thể.
4. Cấu hình DefaultCookieSerializer thống nhất cho toàn bộ instance.
5. Trong logout, invalidate session ở repository và để Spring Session resolver hết hạn cookie hiện hành.
6. Với cookie cũ khác scope, phát từng Set-Cookie hết hạn riêng, đúng name/domain/path.
7. Kiểm tra response và cookie jar bằng Developer Tools hoặc browser automation.
8. Xác nhận request tiếp theo không gửi cookie cũ và session ID cũ không còn được repository chấp nhận.

Khi dùng nhiều instance, cấu hình cookie phải giống nhau trên tất cả node. Nếu triển khai rolling update, tránh để các node đồng thời phát cookie cùng tên nhưng khác domain/path. Khi đổi scope, cần một giai đoạn migration có chủ đích và kiểm thử qua load balancer.

Cookie session là chìa khóa tham chiếu tới session ở máy chủ. Xóa cookie đúng phạm vi giúp trình duyệt ngừng gửi ID cũ; invalidate session trong repository mới là bước thu hồi quyền sử dụng ID đó. Kết hợp hai thao tác và kiểm tra cookie trùng tên sẽ giúp logout và migration cookie hoạt động nhất quán.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — CookieHttpSessionIdResolver Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieHttpSessionIdResolver.html)
- [Spring Session — DefaultCookieSerializer Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/DefaultCookieSerializer.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)

