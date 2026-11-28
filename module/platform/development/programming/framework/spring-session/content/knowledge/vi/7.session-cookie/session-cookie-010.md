# `domainNamePattern` và giới hạn ký tự khi suy ra miền cookie

Khi một ứng dụng Spring Session được truy cập qua nhiều tên miền con, cookie session có thể cần được chia sẻ ở phạm vi tên miền cha. `DefaultCookieSerializer` cung cấp `domainNamePattern` để suy ra thuộc tính `Domain` từ hostname của request. Cấu hình này hữu ích với các ứng dụng như `app.example.com` và `admin.example.com`, nhưng cần giới hạn chặt miền được phép, hiểu cách regex lấy kết quả và kiểm tra các quy tắc tên miền mà trình duyệt chấp nhận.

`domainNamePattern` chỉ quyết định giá trị thuộc tính `Domain` của cookie. Nó không tạo session ID, không thay đổi nơi lưu session trong Redis/JDBC và không cấp quyền truy cập cho người dùng. Nếu suy ra sai miền, trình duyệt có thể từ chối cookie, gửi cookie đến nhiều máy chủ hơn dự kiến hoặc không gửi cookie ở request tiếp theo. Vì cookie session là thông tin mang quyền sử dụng phiên, phạm vi miền cần được thiết kế như một phần của ranh giới bảo mật.

## 1. Cookie host-only và cookie có thuộc tính Domain

Khi server phát hành cookie mà không có thuộc tính `Domain`, trình duyệt lưu cookie dạng host-only. Cookie đó chỉ được gửi đến đúng host đã phát hành nó. Ví dụ, cookie được phát hành bởi `app.example.com` sẽ được gửi đến `app.example.com`, nhưng không tự động được gửi đến `admin.example.com`.

Khi response có `Domain=example.com`, trình duyệt có thể gửi cookie đến `example.com` và các tên miền con phù hợp như `app.example.com`, `admin.example.com`. Điều này giúp nhiều ứng dụng con dùng chung session cookie nếu chúng được thiết kế để cùng chia sẻ phiên.

| Cách phát hành | Phạm vi gửi cookie |
|---|---|
| Không có `Domain` | Chỉ host đã phát hành cookie |
| `Domain=example.com` | `example.com` và các subdomain hợp lệ của nó |
| `Domain=app.example.com` | Host đó và các subdomain của nó, không phải sibling như `admin.example.com` |
| `Domain=other.net` từ host `app.example.com` | Trình duyệt từ chối vì miền không phải host hiện tại hoặc miền cha phù hợp |

Thuộc tính `Domain` mở rộng phạm vi cookie. Một ứng dụng dễ bị ảnh hưởng hơn nếu cookie được gửi đến nhiều subdomain, đặc biệt khi một subdomain do hệ thống khác hoặc bên thứ ba quản lý. Chỉ mở rộng cookie đến miền cha khi các ứng dụng con thực sự cần chia sẻ session và cùng tuân thủ chính sách bảo mật.

## 2. `domainNamePattern` hoạt động như thế nào?

`DefaultCookieSerializer` có thể cấu hình một miền cố định bằng `setDomainName(...)` hoặc suy ra miền từ hostname bằng `setDomainNamePattern(...)`. Với pattern, serializer kiểm tra hostname của request và lấy miền từ nhóm bắt (capturing group) số 1 trong biểu thức chính quy.

Ví dụ, ứng dụng nhận request ở `shop.example.com`, `admin.example.com` và `example.com`. Có thể dùng pattern cho phép các host thuộc `example.com`:

```java
DefaultCookieSerializer serializer = new DefaultCookieSerializer();
serializer.setDomainNamePattern(
    "^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)*(example\\.com)$"
);
```

Nhóm bắt thứ nhất là `(example\.com)`. Với hostname `shop.example.com`, serializer suy ra `example.com` và đặt `Domain=example.com`. Phần `(?:...)` là nhóm không bắt, dùng để khớp các nhãn subdomain mà không làm thay đổi số thứ tự của nhóm bắt cần lấy.

Ví dụ với hai miền gốc được cho phép:

```java
serializer.setDomainNamePattern(
    "^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)*(example\\.com|example\\.net)$"
);
```

Pattern này cho phép hostname thuộc `example.com` hoặc `example.net`; nhóm bắt thứ nhất trả về một trong hai miền gốc. Trong ứng dụng thực tế, cần xác thực kỹ từng nhãn hostname và giới hạn danh sách miền theo những tên miền mà tổ chức kiểm soát.

Kết quả minh họa:

| Hostname của request | Giá trị nhóm bắt 1 | Domain cookie suy ra |
|---|---|---|
| `example.com` | `example.com` | `example.com` |
| `shop.example.com` | `example.com` | `example.com` |
| `admin.eu.example.com` | `example.com` | `example.com` |
| `portal.example.net` | `example.net` | `example.net` |
| `example.org` | Không khớp | Không đặt `Domain` theo pattern |

Khi pattern không khớp, serializer có thể không đặt thuộc tính `Domain`; cookie khi đó trở thành host-only. Điều này có thể là hành vi an toàn mong muốn, nhưng phải được kiểm thử và hiểu rõ. Không nên mặc định rằng pattern không khớp sẽ luôn làm request thất bại hoặc xóa cookie cũ.

### Vì sao phải dùng nhóm bắt thứ nhất?

Serializer lấy giá trị từ nhóm bắt đầu tiên. Nếu pattern có nhóm bắt phụ ở phía trước, nhóm 1 có thể trả về một phần hostname thay vì miền gốc. Dùng nhóm không bắt `(?:...)` cho các phần chỉ cần gom nhóm, và dành nhóm bắt đầu tiên cho giá trị miền muốn trả về.

Ví dụ không nên dùng:

```java
// Nhóm 1 chỉ bắt subdomain; nhóm 2 mới bắt miền gốc.
serializer.setDomainNamePattern(
    "^([a-z0-9]+)\\.(example\\.com)$"
);
```

Với `shop.example.com`, nhóm 1 là `shop`, không phải `example.com`. Pattern đúng cần dùng nhóm không bắt cho subdomain và đặt miền gốc ở nhóm bắt đầu tiên.

## 3. Pattern cần khớp toàn bộ hostname

`domainNamePattern` là biểu thức chính quy dùng để so khớp hostname. Nên viết pattern có `^` và `$` để thể hiện rõ ý định khớp toàn bộ tên máy chủ. Nếu chỉ tìm một chuỗi con như `example.com` ở bất kỳ vị trí nào, một hostname không thuộc miền được phép nhưng có chứa chuỗi đó vẫn có thể bị nhận nhầm.

Ví dụ pattern quá rộng:

```java
// Không an toàn: chỉ cần hostname chứa example.com ở đâu đó.
serializer.setDomainNamePattern("(example\\.com)");
```

Pattern này không thể hiện giới hạn hostname hoàn chỉnh. Một host như `example.com.attacker.net` có thể chứa chuỗi `example.com` nhưng không thuộc miền `example.com`. Hãy dùng pattern có neo đầu/cuối và allowlist rõ ràng.

Pattern cũng cần được thiết kế cho cấu trúc tên miền thật. Biểu thức `\w+\.\w+` thường quá đơn giản: nó có thể không chấp nhận dấu gạch nối hợp lệ trong nhãn DNS, chỉ lấy hai nhãn cuối và xử lý sai các public suffix nhiều cấp như `co.uk`. Không thể suy ra miền đăng ký được chỉ bằng cách luôn lấy hai nhãn cuối của mọi hostname.

## 4. Giới hạn ký tự của hostname và miền cookie

`domainNamePattern` không tự cắt ngắn hostname để làm cho miền hợp lệ. Serializer lấy chuỗi từ nhóm bắt; trình duyệt sẽ áp dụng quy tắc cookie và hostname của nó. Vì vậy, pattern phải chỉ trả về một tên miền hợp lệ và ứng dụng nên xác thực độ dài trước khi phát hành cookie.

Đối với tên miền DNS thông thường, các giới hạn phổ biến cần nhớ là:

- Mỗi nhãn DNS (phần giữa hai dấu chấm) tối đa 63 octet.
- Tên miền đầy đủ có giới hạn DNS khoảng 255 octet ở dạng wire format; dạng văn bản thường tối đa 253 ký tự ASCII khi không tính dấu chấm cuối cùng.
- Nhãn hostname thông thường dùng chữ cái ASCII, chữ số và dấu gạch nối; dấu gạch nối không được đứng ở đầu hoặc cuối nhãn.
- Tên miền nên được chuẩn hóa về chữ thường để so sánh và cấu hình nhất quán.
- Tên miền quốc tế hóa cần được chuyển sang dạng ASCII IDNA/Punycode khi dùng trong giao thức và cấu hình cookie.

Các giới hạn trên là quy tắc của DNS/hostname, không phải một cơ chế giới hạn độ dài riêng của `domainNamePattern`. Giới hạn kích thước cookie là vấn đề khác: trình duyệt và hạ tầng HTTP có giới hạn cho toàn bộ cookie hoặc header, và các giới hạn cụ thể có thể khác nhau. Không nên lưu dữ liệu lớn trong cookie session; Spring Session thường chỉ cần cookie mang session ID.

### Các ký tự nên loại khỏi giá trị Domain

Giá trị `Domain` là tên miền, không phải URL. Không đưa các thành phần sau vào nhóm bắt:

- Scheme như `https://` hoặc `http://`.
- Port như `:8080`.
- Path như `/app` hoặc `/`.
- Ký tự wildcard `*` để biểu diễn subdomain.
- Khoảng trắng, dấu gạch chéo, dấu hai chấm hoặc ký tự điều khiển.
- Dấu gạch dưới trong hostname Internet thông thường.

Ví dụ `example.com` là miền; `https://example.com:8443/app` là URL và không hợp lệ làm giá trị `Domain`. Dấu chấm đầu như `.example.com` từng được dùng trong ví dụ cũ, nhưng hành vi hiện đại coi dấu chấm đầu là không có ý nghĩa; nên cấu hình miền không có dấu chấm đầu.

## 5. Giới hạn độ dài ngay trong regex

Có thể giới hạn độ dài mỗi nhãn bằng regex, thay vì chấp nhận chuỗi bất kỳ. Ví dụ sau chỉ cho phép nhãn DNS ASCII dài từ 1 đến 63 ký tự, không bắt đầu hoặc kết thúc bằng dấu gạch nối; nhóm bắt 1 vẫn là miền gốc được cho phép:

```java
String label = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
String domainPattern = "^(?:" + label + "\\.)*(example\\.com|example\\.net)$";

DefaultCookieSerializer serializer = new DefaultCookieSerializer();
serializer.setDomainNamePattern(domainPattern);
```

Độ dài nhãn trong ví dụ được giới hạn, nhưng pattern vẫn chưa kiểm tra tổng chiều dài của toàn bộ hostname. Nếu ứng dụng nhận hostname từ nhiều nguồn hoặc có yêu cầu chặt chẽ, hãy xác thực cả tổng chiều dài và từng nhãn bằng một hàm kiểm tra riêng trước khi phát hành cookie. Không nên dùng regex quá phức tạp để thay thế một thư viện hostname/IDNA đã được kiểm chứng.

Pattern ở trên cũng chỉ minh họa cho miền `example.com` và `example.net`. Hãy thay bằng danh sách miền thực tế do tổ chức kiểm soát. Không thay allowlist bằng `.*` hoặc một mẫu chỉ lấy hai nhãn cuối vì điều đó có thể mở rộng cookie sang miền không mong muốn.

## 6. Public suffix và miền gốc được phép

Trình duyệt không cho một website tùy ý đặt cookie trên public suffix như `com`, `net` hoặc `co.uk`. Public suffix là phần hậu tố mà người dùng có thể đăng ký tên miền trực tiếp bên dưới. Ví dụ, `example.co.uk` là miền đăng ký; `co.uk` là public suffix. Nếu ứng dụng suy ra `co.uk` làm cookie domain, trình duyệt thường từ chối cookie hoặc xử lý theo chính sách public suffix.

Không có một quy tắc “lấy hai nhãn cuối” đúng cho tất cả quốc gia và loại tên miền. Ví dụ:

| Hostname | Miền đăng ký cần cân nhắc | Public suffix |
|---|---|---|
| `app.example.com` | `example.com` | `com` |
| `shop.example.co.uk` | `example.co.uk` | `co.uk` |
| `portal.example.com.au` | `example.com.au` | `com.au` |

Với danh sách domain có cấu trúc khác nhau, cách an toàn thường là allowlist tường minh các miền gốc mà ứng dụng kiểm soát, hoặc dùng thư viện hiểu Public Suffix List khi cần xác định miền đăng ký động. Không tự suy đoán miền gốc bằng cách cắt chuỗi tại dấu chấm cuối hoặc lấy hai thành phần cuối.

## 7. Cấu hình đầy đủ với Spring Session

Ví dụ sau cấu hình cookie cho các subdomain của hai miền do ứng dụng kiểm soát. `HttpSessionIdResolver` dùng cookie resolver và `DefaultCookieSerializer` để phát hành cookie với miền suy ra từ hostname:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieHttpSessionIdResolver;
import org.springframework.session.web.http.DefaultCookieSerializer;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class SessionCookieConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        CookieHttpSessionIdResolver resolver =
                new CookieHttpSessionIdResolver();

        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("APPSESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        serializer.setDomainNamePattern(
                "^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)*(example\\.com|example\\.net)$");

        resolver.setCookieSerializer(serializer);
        return resolver;
    }
}
```

Đây là cấu hình minh họa; `example.com` và `example.net` phải được thay bằng các miền thật mà tổ chức kiểm soát. `Secure=true` phù hợp với môi trường HTTPS. Nếu ứng dụng chạy HTTP cục bộ, hãy cấu hình riêng cho profile phát triển thay vì hạ mức bảo vệ của production. `HttpOnly` ngăn JavaScript đọc cookie qua API trình duyệt thông thường; `SameSite` kiểm soát một phần cách cookie được gửi trong ngữ cảnh site khác.

Nếu đã cấu hình `setDomainName(...)` với một miền tĩnh, không nên đồng thời dựa vào `domainNamePattern` để suy ra một miền khác. Trong `DefaultCookieSerializer`, miền tĩnh có thể được ưu tiên; hãy chọn một cơ chế rõ ràng và xác minh hành vi theo phiên bản Spring Session đang dùng.

## 8. Hostname phía sau reverse proxy và nguy cơ Host header

`domainNamePattern` suy ra miền từ hostname mà ứng dụng nhìn thấy trong request. Khi ứng dụng chạy sau load balancer hoặc reverse proxy, hostname đó có thể chịu ảnh hưởng của header `Host` hoặc forwarded host header. Nếu proxy chuyển tiếp giá trị do client tự đặt mà không xác thực, client có thể thử làm ứng dụng phát hành cookie cho một miền khác.

Các biện pháp cần áp dụng:

- Cấu hình reverse proxy chỉ chuyển tiếp host đã được xác thực và nằm trong danh sách domain phục vụ.
- Chỉ tin `Forwarded` hoặc `X-Forwarded-Host` từ proxy đáng tin cậy; không bật xử lý forwarded header cho mọi nguồn Internet nếu kiến trúc không bảo đảm điều đó.
- Dùng allowlist domain trong regex để hostname lạ không thể tạo ra cookie domain tùy ý.
- Kiểm thử hostname mà Servlet request thực sự nhìn thấy khi đi qua proxy, thay vì chỉ kiểm thử khi gọi ứng dụng trực tiếp.
- Không ghi nhận cookie session hoặc session ID đầy đủ trong log khi điều tra lỗi domain.

Regex allowlist là một lớp giới hạn, không thay thế cấu hình proxy và kiểm soát Host header. Nếu hostname không thuộc danh sách được phép, ưu tiên để cookie host-only hoặc từ chối request theo chính sách host của ứng dụng.

## 9. Localhost, địa chỉ IP và nhiều miền không liên quan

Trong môi trường phát triển, ứng dụng thường chạy tại `localhost`, `127.0.0.1` hoặc một tên host nội bộ. Các host này không có miền cha công khai để chia sẻ cookie theo cách thông thường. Không nên cố suy ra `Domain=localhost` hoặc một domain cookie từ địa chỉ IP; để serializer không đặt `Domain` thường phù hợp hơn và cookie sẽ host-only.

Hai miền không liên quan như `example.com` và `example.net` không thể dùng một cookie domain chung. Pattern có thể phát hành cùng tên cookie riêng trên mỗi miền, nhưng trình duyệt vẫn lưu cookie theo phạm vi từng miền. Người dùng không được tự động chia sẻ cookie giữa các miền đó. Nếu cần đăng nhập một lần qua nhiều miền, hãy dùng cơ chế xác thực liên miền phù hợp như OpenID Connect hoặc một luồng SSO, không cố mở rộng thuộc tính `Domain`.

## 10. Quan hệ với `__Host-` và `__Secure-` cookie prefix

Trình duyệt hiện đại hỗ trợ các tiền tố cookie để áp dụng điều kiện bảo mật bổ sung:

- Cookie có tên bắt đầu bằng `__Secure-` cần được phát hành qua kết nối an toàn và có thuộc tính `Secure`.
- Cookie có tên bắt đầu bằng `__Host-` cần có `Secure`, `Path=/` và không được có thuộc tính `Domain`.

Vì `domainNamePattern` được dùng để phát hành thuộc tính `Domain`, nó không tương thích với mục tiêu dùng cookie `__Host-`. Nếu muốn dùng `__Host-APPSESSION`, phải bảo đảm serializer không đặt domain, đồng thời đặt `Secure=true` và `Path=/`. Nếu muốn chia sẻ cookie giữa subdomain, cần dùng cookie có `Domain` phù hợp và không dùng tiền tố `__Host-`.

Đây là một quyết định kiến trúc: host-only cookie với tiền tố `__Host-` giới hạn cookie ở một host; cookie domain cho phép chia sẻ giữa subdomain nhưng mở rộng phạm vi tin cậy. Chọn theo mô hình triển khai và ranh giới bảo mật thực tế.

## 11. Xóa cookie cần đúng domain và path

Cookie được định danh bởi tổ hợp tên, domain và path. Khi hết hạn cookie, response cần phát hành cookie cùng tên với thời hạn hết hạn và phạm vi domain/path phù hợp với cookie đã lưu. Nếu lúc đăng nhập cookie có `Domain=example.com; Path=/` nhưng lúc logout chỉ phát hành cookie host-only hoặc path khác, trình duyệt có thể giữ lại cookie cũ.

Với `domainNamePattern`, cần kiểm thử cả chiều phát hành và chiều hết hạn. Nếu ứng dụng có nhiều hostname, hãy bảo đảm request logout đi qua hostname phù hợp hoặc có logic xóa cookie tương ứng với các domain/path đã phát hành. Không nên phát hành một cookie domain rộng hơn chỉ để cố xóa cookie cũ; cần xác định đúng cookie scope.

Nếu đổi tên cookie hoặc thay đổi domain/path trong quá trình triển khai, người dùng có thể còn cookie cũ trong trình duyệt. Cần có kế hoạch chuyển đổi hoặc xóa cookie cũ trong một giai đoạn tương thích, đồng thời bảo đảm session cũ hết hạn theo TTL phía server.

## 12. Kiểm thử pattern và cookie được phát hành

Đừng chỉ kiểm thử regex độc lập. Cần kiểm thử response `Set-Cookie` để biết serializer thực sự phát hành domain nào và trình duyệt có thể chấp nhận phạm vi đó hay không.

Một bảng test tối thiểu nên bao gồm:

| Hostname đầu vào | Kết quả mong đợi |
|---|---|
| `example.com` | Domain là `example.com` |
| `shop.example.com` | Domain là `example.com` |
| `admin.eu.example.com` | Domain là `example.com` |
| `portal.example.net` | Domain là `example.net` |
| `example.org` | Không đặt Domain theo pattern |
| `example.com.attacker.net` | Không đặt Domain theo pattern |
| `localhost` | Không đặt Domain theo pattern |
| `127.0.0.1` | Không đặt Domain theo pattern |
| Host có port trong cấu hình sai | Phải được chuẩn hóa/loại bỏ port trước khi so khớp; không đưa port vào Domain |

Trong integration test, gửi request với hostname mong muốn và kiểm tra header `Set-Cookie`:

```java
MvcResult result = mockMvc.perform(get("/session/start")
        .header("Host", "shop.example.com"))
    .andExpect(status().isOk())
    .andReturn();

String setCookie = result.getResponse().getHeader("Set-Cookie");
assertThat(setCookie).contains("Domain=example.com");
assertThat(setCookie).contains("Path=/");
assertThat(setCookie).contains("HttpOnly");
assertThat(setCookie).contains("Secure");
```

Đoạn mã là minh họa cho test với MockMvc và AssertJ; endpoint phải tạo session để resolver phát hành cookie. Cấu hình MockMvc cần cài filter Spring Session. Một số phiên bản Servlet test framework có thể chuẩn hóa hoặc xử lý header `Host` khác nhau, vì vậy nên bổ sung kiểm thử end-to-end qua reverse proxy trong môi trường staging.

Ngoài trường hợp khớp, cần kiểm tra pattern không khớp, miền public suffix, nhãn quá dài, hostname có ký tự lạ, IDN, logout và thay đổi domain/path. Nếu test chỉ xác nhận regex trả về chuỗi mà không kiểm tra header thực tế, lỗi cấu hình serializer hoặc cookie scope có thể bị bỏ sót.

## 13. Nguyên tắc thiết kế

- Dùng `domainNamePattern` khi ứng dụng thực sự cần suy ra miền cookie từ nhiều hostname.
- Dành capturing group số 1 cho miền gốc; dùng nhóm không bắt cho phần regex phụ.
- Neo pattern bằng `^` và `$`, giới hạn theo allowlist domain mà tổ chức kiểm soát.
- Không lấy hai nhãn cuối một cách máy móc; cân nhắc public suffix nhiều cấp như `co.uk`.
- Tuân thủ giới hạn nhãn DNS 63 octet, tổng hostname và quy tắc ký tự; pattern không tự cắt ngắn hoặc làm sạch chuỗi.
- Không suy domain từ Host/forwarded header không đáng tin cậy.
- Giữ cookie host-only cho localhost, IP và trường hợp không cần chia sẻ subdomain.
- Kiểm tra tương thích giữa `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite` và tiền tố `__Host-`/`__Secure-`.
- Kiểm thử `Set-Cookie` cho cả hostname được phép, hostname bị từ chối, logout và các môi trường qua proxy.

Với Spring Session, cookie chỉ cần mang session ID để `SessionRepository` tìm dữ liệu ở Redis hoặc JDBC. `domainNamePattern` giúp chọn phạm vi hostname phù hợp cho cookie đó, nhưng giá trị nhóm bắt phải là một miền hợp lệ, được cho phép và có độ dài đúng chuẩn. Một allowlist chặt cùng kiểm thử cookie thực tế sẽ giúp chia sẻ session giữa các subdomain mà không vô tình mở rộng quyền gửi cookie sang những host ngoài ý muốn.
