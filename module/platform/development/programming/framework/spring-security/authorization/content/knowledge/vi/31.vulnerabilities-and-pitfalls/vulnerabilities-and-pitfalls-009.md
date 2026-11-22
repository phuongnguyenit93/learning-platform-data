# Đường dẫn thay thế, HTTP method khác và lỗi chuẩn hóa request

## 1. Vì sao đây là lỗ hổng phân quyền?

Spring Security có thể quyết định quyền truy cập dựa trên **đường dẫn và HTTP method**, trong khi Spring MVC, servlet container hoặc reverse proxy cũng phải diễn giải chính request ấy để chọn controller. Nếu các tầng hiểu khác nhau về đường dẫn, hoặc rule chỉ kiểm tra GET mà endpoint có thể xử lý DELETE/PATCH qua một lối khác, request có thể đi tới chức năng nhạy cảm dưới một quy tắc phân quyền yếu hơn dự kiến.

Ví dụ một API quản lý tài liệu:

| Thao tác thật | Endpoint dự kiến | Quyền tối thiểu |
| --- | --- | --- |
| Đọc tài liệu 42 | GET /api/documents/42 | DOC_READ |
| Đọc metadata theo HEAD nếu ứng dụng hỗ trợ | HEAD /api/documents/42 | DOC_READ |
| Sửa tài liệu 42 | PATCH /api/documents/42 | DOC_EDIT |
| Xóa tài liệu 42 | DELETE /api/documents/42 | DOC_DELETE |

Một cấu hình yếu có thể chỉ kiểm tra chuỗi đường dẫn hoặc để các request không khớp rơi vào nhánh permitAll. Khi đó người chỉ có DOC_READ có thể chạm tới thao tác xóa, hoặc một đường dẫn được backend coi là tương đương lại không khớp rule bảo vệ. Không phải mọi biến thể URL đều được container/Spring chấp nhận; **lỗ hổng chỉ tồn tại khi request thực tế đến được handler nhạy cảm mà không trải qua phép kiểm tra quyền tương ứng**.

Mục tiêu của bài:

1. Nhận diện các dạng đường dẫn thay thế, HTTP method và khác biệt chuẩn hóa có thể tạo khoảng hở giữa **security matcher** và **handler mapping**.
2. Hiểu các lớp bảo vệ sẵn có (đặc biệt FilterChainProxy và StrictHttpFirewall), giới hạn của chúng, cũng như cách cấu hình có thể vô tình làm mất bảo vệ.
3. Thiết kế luật phân quyền phân biệt **resource + action + HTTP method**, áp dụng mặc định từ chối (deny by default), rồi kiểm thử trên request đi qua toàn bộ filter chain và proxy thật.
4. Phân biệt **request bị từ chối ở firewall**, **không có handler phù hợp** và **bị từ chối vì thiếu quyền**; các trạng thái HTTP có thể khác nhau nhưng không được xuất hiện side effect trái phép.

## 2. Một request đi qua những lớp nào?

~~~text
Client gửi request-target, ví dụ:
  PATCH /gateway/api/documents/42
           |
           v
CDN / load balancer / reverse proxy
  (có thể rewrite prefix, redirect, decode hoặc chặn request)
           |
           v
Servlet container
  (requestURI, contextPath, servletPath, pathInfo, queryString)
           |
           v
Spring Security: FilterChainProxy + HttpFirewall
  -> chọn SecurityFilterChain theo securityMatcher
  -> chọn quy tắc authorizeHttpRequests theo requestMatcher
           |
           v
Spring MVC: DispatcherServlet + HandlerMapping
  -> chọn controller/method + biến đường dẫn
           |
           v
Service + kiểm tra quyền trên đối tượng/tenant
~~~

Hai câu hỏi bắt buộc trả lời khi rà soát hệ thống:

- **Bộ phận nào hiểu request này là đường dẫn và method gì để phân quyền?**
- **Bộ phận nào hiểu request này là đường dẫn và method gì để chạy nghiệp vụ?**

Các biểu diễn không được mặc định là đồng nhất:

| Thuộc tính / tầng | Ý nghĩa và rủi ro |
| --- | --- |
| Request-target HTTP | Chuỗi client gửi, có thể chứa mã hóa phần trăm, dấu chấm, dấu chấm phẩy |
| Reverse proxy | Có thể bỏ/thêm prefix hoặc rewrite URL trước khi Java nhận; quy tắc upstream ảnh hưởng kết quả |
| HttpServletRequest.getRequestURI() | Gồm context path và phần URI theo hợp đồng servlet; cách container xử lý mã hóa cần kiểm chứng |
| getContextPath(), getServletPath(), getPathInfo() | Các thành phần dùng khi xác định vị trí servlet; cách diễn giải có khác biệt theo container/mapping |
| getQueryString() | Phần sau dấu ?, **không phải** thành phần path để requestMatchers(String) tự kiểm tra |
| HttpFirewall + RequestMatcher | Có thể từ chối request bất thường, bọc request và chuẩn hóa phần dùng để match |
| Spring MVC HandlerMapping | Có quy tắc nhận diện route, path variable, mapping method và cấu hình parsing của riêng nó |

Spring Security dùng FilterChainProxy với HttpFirewall để thu hẹp khác biệt giữa container và các phép so khớp. Mặc định **StrictHttpFirewall** từ chối nhiều URL không chuẩn hóa hoặc nguy hiểm, cũng như các HTTP method không nằm trong allowlist. Các request đáng ngờ có thể bị loại trước khi đến AuthorizationManager/controller. Không nên coi việc tự chuẩn hóa thêm nhiều lần là một giải pháp tương đương firewall: một tầng có thể decode một lần, tầng tiếp theo decode lần nữa, dẫn tới ý nghĩa khác nhau. Nếu có tình huống cần URL đặc biệt hợp lệ, phải xác định rõ hành vi của cả proxy, container, firewall và MVC rồi mới thay đổi cấu hình.

## 3. Đường dẫn thay thế: các trường hợp dễ bỏ sót

Những đường dẫn dưới đây là **ca kiểm thử đề xuất**, không phải lời khẳng định Spring Security mặc định cho chúng đi qua. Mỗi ca phải quan sát kết quả từ môi trường thật.

| Biến thể | Ví dụ với tài liệu 42 | Nguy cơ cần kiểm chứng |
| --- | --- | --- |
| Dấu / cuối | /api/documents/42/ | Router và security matcher có thể khác nhau về trailing slash, nhất là sau migration hoặc custom mapping |
| Nhiều dấu / | /api//documents/42 | Proxy/container có thể gom slash nhưng một rule đọc chuỗi thô không gom |
| Đoạn . hoặc .. | /api/tmp/../documents/42 | Một tầng loại bỏ dot-segment còn tầng khác so khớp trước chuẩn hóa |
| Ký tự URL-encoded | /api/documents/%34%32 | Decode một lần dẫn về ID 42; phải kiểm chứng matcher và handler có cùng định danh |
| Encoded slash | /api/documents%2F42 | Tách segment trước/sau decode có thể khác; firewall mặc định thường chặn |
| Double encoding | /api/documents/%2534%2532 | Decode nhiều lần có thể đổi nghĩa; không tự động decode tiếp để thử “sửa” URL |
| Dấu chấm phẩy / matrix | /api/documents/42;view=full | Servlet, firewall và MVC có thể loại bỏ hoặc xử lý path parameter khác nhau |
| Chữ hoa / chữ thường | /API/documents/42 | Case sensitivity có thể khác giữa route, proxy hoặc custom matcher |
| Đường dẫn alias | /v1/documents/42 hoặc /internal/documents/42 | Nhiều URL cùng tới một nghiệp vụ nhưng chỉ một URL được gắn rule |
| Suffix / phần mở rộng | /api/documents/42.json | Route/content negotiation hoặc route legacy có thể ánh xạ cùng dữ liệu |
| Context/servlet prefix | /app/api/documents/42 | Nhầm lẫn context path, servlet path và pattern gây lệch phạm vi bảo vệ |
| Proxy rewrite | /gateway/documents/42 được rewrite thành /api/documents/42 | Bảo vệ ở edge và trong app thấy path khác nhau |
| Internal forward | Một endpoint công khai forward tới tài nguyên được bảo vệ | Phải kiểm tra đường dispatch/handler đích, không chỉ đường request ban đầu |
| Query đổi hành động/đối tượng | GET /api/documents/42?export=secret | Matcher path không tự xét query; business action có thể nhạy cảm hơn GET thông thường |

**Điểm kiểm tra quyết định:** với mỗi biến thể, ghi lại (a) proxy chuyển gì, (b) firewall chấp nhận hay từ chối, (c) SecurityFilterChain và rule nào khớp, (d) controller nào chạy, (e) quyền trên tài liệu/tenant được kiểm tra ở đâu. Không nên suy ra lỗ hổng chỉ từ việc URL trông “lạ”.

### 3.1. Dấu chấm phẩy, mã hóa và nhiều lần giải mã

Spring Security mô tả rủi ro từ path parameters và khác biệt servletPath/pathInfo giữa các servlet container. StrictHttpFirewall mặc định là lớp bảo vệ quan trọng đối với URL không chuẩn hóa, dấu chấm phẩy, encoded slash và nhiều kiểu ký tự đáng ngờ. Nếu ứng dụng cần **matrix variables**, việc bật setAllowSemicolon(true) là thay đổi có hệ quả bảo mật; phải thêm test đối chiếu route và quyền, không chỉ thêm ngoại lệ cho firewall để request chạy được.

Tương tự, không dùng URLDecoder.decode cho toàn bộ path rồi so khớp với prefix bằng tay. URLDecoder được thiết kế cho dữ liệu dạng form-urlencoded, có quy tắc dấu + khác với path, và dễ tạo thêm một vòng decode không nhất quán. Quyết định cần dựa trên biểu diễn path **đã được framework định nghĩa và kiểm chứng**, trong đó request bất định hoặc không hợp lệ bị từ chối.

### 3.2. Alias và rewrite đôi khi nguy hiểm hơn encoded payload

Giả sử cả /api/documents/{id} và /legacy/documents/{id} cùng gọi service xóa. Nếu chỉ /api/** thuộc một SecurityFilterChain hẹp, alias /legacy/** có thể rơi sang chain khác hoặc không có chain phù hợp, tùy cấu hình. Tương tự, rule bao phủ /api/** không tự bảo vệ một servlet khác dưới /admin-api/**.

Rà soát toàn bộ lối vào nghiệp vụ nhạy cảm: controller mapping, route legacy, versioning, proxy rewrite, servlet phụ, actuator/custom endpoints, internal forward. Nếu dùng nhiều SecurityFilterChain, cần **chain bao phủ phần còn lại** và xác minh thứ tự ưu tiên các chain. Trong một chain, các rule authorizeHttpRequests có thứ tự, **rule khớp đầu tiên quyết định**; một permitAll rộng đứng trước rule hạn chế sẽ che khuất rule phía sau.

## 4. HTTP method và chuyển đổi method

Một path không đại diện duy nhất cho một hành động. Xét từng method và mapping thật, không áp quyền đọc cho mọi request chỉ vì cùng URL.

| Method / tình huống | Điểm cần kiểm tra |
| --- | --- |
| GET | Quyền đọc; endpoint GET không nên tạo thay đổi dữ liệu nhạy cảm |
| HEAD | Spring MVC có thể phục vụ HEAD qua handler GET; xác định rõ quyền đọc và kiểm thử không tạo side effect |
| POST | Quyền tạo/thực hiện tác vụ; không dùng quyền GET làm điều kiện thay thế |
| PUT, PATCH | Quyền sửa; đôi khi hai method đi qua handler khác nhau |
| DELETE | Quyền xóa; test bằng principal chỉ có quyền đọc để chứng minh bị chặn |
| OPTIONS | CORS preflight là yêu cầu kiểm tra khả năng cross-origin, **không phải** yêu cầu thực hiện thao tác đích |
| TRACE, CONNECT, method lạ | Thường không cần trong API; StrictHttpFirewall có allowlist method mặc định, không mở toàn bộ |
| Form POST kèm _method=DELETE | Chỉ có tác dụng khi HiddenHttpMethodFilter được bật và xử lý; phải kiểm tra method mà Security thấy |
| X-HTTP-Method-Override hoặc header tương tự | Không phải chức năng tự động của mọi ứng dụng; nếu gateway/custom filter hỗ trợ thì đó là một đường chuyển method phải được phân quyền và kiểm thử |

Spring Boot 3.3 có thuộc tính spring.mvc.hiddenmethod.filter.enabled với giá trị mặc định false. Nếu bật HiddenHttpMethodFilter để hỗ trợ form HTML, hãy kiểm tra thứ tự filter để **method hiệu lực được xác định trước khi đánh giá quyền**, và chỉ hỗ trợ kiểu override đã chọn. Không giả định một header tùy ý luôn có tác dụng hoặc luôn bị bỏ qua. Nếu proxy có khả năng đổi method, test cả phía trước và phía sau proxy.

Với CORS, preflight OPTIONS thường không mang cookie xác thực nên cần xử lý CORS đúng thứ tự (Spring Security có tích hợp cors). Không khắc phục lỗi preflight bằng cách mở mọi OPTIONS trên mọi route một cách mù quáng; OPTIONS được dùng để đàm phán cross-origin còn **request GET/POST/PATCH/DELETE thực vẫn phải đi qua phân quyền**. CORS hạn chế hành vi browser trong bối cảnh cross-origin, không phải cơ chế xác thực/phân quyền API.

**CSRF là kiểm soát khác với authorization.** Khi test POST/PUT/PATCH/DELETE có CSRF protection, thiếu token có thể làm request bị chặn trước khi test đến rule quyền. Bổ sung CSRF hợp lệ trong test có chủ đích kiểm tra permission; ngược lại, kiểm thử CSRF như một ca riêng. Không dùng “403 do thiếu CSRF” để khẳng định rule DOC_DELETE đã đúng.

## 5. Cách thiết kế rule rõ ràng trong Spring Security 6.x

Đối với ứng dụng Servlet/Spring Boot 3.x, hãy mô hình hóa quyền theo **method và route**. Đoạn sau là mã cấu hình trong ứng dụng Spring Security (cần dependencies, Authentication và controller tương ứng), không phải chương trình Java chạy bằng javac thuần.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentSecurityConfig {

    @Bean
    SecurityFilterChain documentSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Mỗi action có authority riêng.
            .requestMatchers(HttpMethod.GET,
                "/api/documents", "/api/documents/{id}")
                .hasAuthority("DOC_READ")
            .requestMatchers(HttpMethod.HEAD,
                "/api/documents", "/api/documents/{id}")
                .hasAuthority("DOC_READ")
            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("DOC_CREATE")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/{id}")
                .hasAuthority("DOC_EDIT")
            .requestMatchers(HttpMethod.DELETE, "/api/documents/{id}")
                .hasAuthority("DOC_DELETE")

            // Phương thức/route chưa được khai báo không tự được mở.
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Cấu hình ví dụ chỉ cho phép các method/path đã liệt kê; nếu sản phẩm cần PUT, alias hoặc trang công khai, phải khai báo quy tắc cụ thể và test tương ứng. Không coi đoạn này là cấu hình hoàn chỉnh cho xác thực, CSRF, CORS, session, OAuth2 hoặc nhiều SecurityFilterChain. Đặc biệt, nếu có thêm các chain hẹp bằng securityMatcher, cần xác minh **mọi đường vào đều được bao phủ**; một rule anyRequest trong chain A không có nghĩa request không khớp chain A sẽ được chain A xử lý.

Lưu ý cơ chế matcher có thể khác tùy phiên bản Spring Security, sự hiện diện của Spring MVC, servlet mapping và cách xây dựng RequestMatcher. Với nhiều servlet hoặc đường dẫn tùy biến, dùng matcher phù hợp với servletPath và kiểm thử **trùng với cấu hình route thực**. Không trộn các quy tắc Regex/Ant/MVC tự chế mà không chứng minh chúng có cùng ngữ nghĩa với HandlerMapping. Trong các hệ thống nhiều tenant hoặc có phân quyền trên tài liệu cụ thể, thêm kiểm soát ở **service/method layer** dựa trên đối tượng đã tải (ví dụ kết hợp @EnableMethodSecurity và @PreAuthorize); một người có DOC_READ vẫn không có quyền xem tài liệu của tenant khác chỉ nhờ match URL.

Các nguyên tắc đi cùng:

- Ưu tiên allowlist route/method; đặt rule rộng/anyRequest cuối cùng và chọn denyAll hoặc ít nhất kiểm soát chặt theo chính sách sản phẩm.
- Duy trì StrictHttpFirewall mặc định nếu không có lý do nghiệp vụ đã được phân tích và test để thay đổi.
- Không dùng web.ignoring cho API động; với nội dung public nên cân nhắc permitAll để request vẫn qua các filter an ninh khác.
- Bảo đảm proxy chỉ tin các Forwarded/X-Forwarded-* header từ nguồn đáng tin cậy; không cho client tự quyết định context path, host hoặc scheme theo cách ảnh hưởng security rule.
- Nếu có URL alias hợp lệ, bảo vệ **mọi alias** với quyền tương đương, hoặc gom chúng về cùng route đã được kiểm chứng trước khi vào ứng dụng.
- Không lấy quyền từ query string, header tự khai, đường dẫn đã tự ghép hoặc “method ưu tiên” do client gửi; dùng Authentication/AuthorizationManager và quyết định ở tầng service.

## 6. Ví dụ Java 17+ độc lập: thấy rõ lỗi rule quá rộng

Ví dụ sau không phụ thuộc Spring; nó mô phỏng một đường dẫn tài liệu **cố định** để so sánh hai chính sách. weakPolicy cố ý chứa lỗi: dùng quyền DOC_READ cho mọi method trên path chính và mặc định cho phép path còn lại. strictPolicy áp rule theo method, từ chối đường dẫn khác và không chấp nhận yêu cầu override trong mô hình đơn giản này. **Không dùng strictPolicy làm bộ chuẩn hóa URL cho ứng dụng thật**: Spring MVC/HttpFirewall phải xử lý route và parsing; ví dụ chỉ chứng minh cách viết phép kiểm tra quyền và test các biến thể.

Lưu thành **AuthorizationRouteDemo.java**:

~~~java
import java.util.Set;

public class AuthorizationRouteDemo {
    record Request(String method, String path, boolean overrideRequested) {}

    private static final String DOCUMENT_PATH = "/api/documents/42";

    // Phản ví dụ: quyền đọc áp dụng cho mọi method, đường dẫn lạ được mặc định mở.
    static boolean weakPolicy(Request request, Set<String> authorities) {
        if (DOCUMENT_PATH.equals(request.path())) {
            return authorities.contains("DOC_READ");
        }
        return true;
    }

    // Mô hình kiểm thử một route cố định: chỉ chấp nhận method và path tường minh.
    static boolean strictPolicy(Request request, Set<String> authorities) {
        if (request == null || authorities == null
                || request.method() == null || request.path() == null
                || request.overrideRequested()
                || !DOCUMENT_PATH.equals(request.path())) {
            return false;
        }

        return switch (request.method()) {
            case "GET", "HEAD" -> authorities.contains("DOC_READ");
            case "PATCH" -> authorities.contains("DOC_EDIT");
            case "DELETE" -> authorities.contains("DOC_DELETE");
            default -> false;
        };
    }

    private static void check(String label, Request request,
                              Set<String> authorities,
                              boolean weakExpected, boolean strictExpected) {
        boolean weak = weakPolicy(request, authorities);
        boolean strict = strictPolicy(request, authorities);
        if (weak != weakExpected || strict != strictExpected) {
            throw new AssertionError(label + ": unexpected decision");
        }
        System.out.println(label + " | weak=" + result(weak)
                + " | strict=" + result(strict));
    }

    private static String result(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> reader = Set.of("DOC_READ");
        check("GET canonical", new Request("GET", DOCUMENT_PATH, false),
                reader, true, true);
        check("DELETE with read", new Request("DELETE", DOCUMENT_PATH, false),
                reader, true, false);
        check("POST with read", new Request("POST", DOCUMENT_PATH, false),
                reader, true, false);
        check("HEAD with read", new Request("HEAD", DOCUMENT_PATH, false),
                reader, true, true);
        check("trailing slash", new Request("GET", DOCUMENT_PATH + "/", false),
                reader, true, false);
        check("encoded digits", new Request("GET", "/api/documents/%34%32", false),
                reader, true, false);
        check("double slash", new Request("GET", "/api/documents//42", false),
                reader, true, false);
        check("dot segment", new Request("GET", "/api/tmp/../documents/42", false),
                reader, true, false);
        check("method override", new Request("GET", DOCUMENT_PATH, true),
                reader, true, false);
        check("PATCH with edit", new Request("PATCH", DOCUMENT_PATH, false),
                Set.of("DOC_EDIT"), false, true);
        check("DELETE with delete", new Request("DELETE", DOCUMENT_PATH, false),
                Set.of("DOC_DELETE"), false, true);
        check("TRACE with read", new Request("TRACE", DOCUMENT_PATH, false),
                reader, true, false);
        check("GET anonymous", new Request("GET", DOCUMENT_PATH, false),
                Set.of(), false, false);
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac --release 17 AuthorizationRouteDemo.java
java AuthorizationRouteDemo
~~~

Stdout chính xác khi chạy chương trình:

~~~text
GET canonical | weak=ALLOW | strict=ALLOW
DELETE with read | weak=ALLOW | strict=DENY
POST with read | weak=ALLOW | strict=DENY
HEAD with read | weak=ALLOW | strict=ALLOW
trailing slash | weak=ALLOW | strict=DENY
encoded digits | weak=ALLOW | strict=DENY
double slash | weak=ALLOW | strict=DENY
dot segment | weak=ALLOW | strict=DENY
method override | weak=ALLOW | strict=DENY
PATCH with edit | weak=DENY | strict=ALLOW
DELETE with delete | weak=DENY | strict=ALLOW
TRACE with read | weak=ALLOW | strict=DENY
GET anonymous | weak=DENY | strict=DENY
~~~

Lưu ý khi diễn giải:

- weakPolicy là **phản ví dụ cố tình không an toàn**: DELETE với quyền đọc vẫn ALLOW; một path khác nhận ALLOW theo nhánh mặc định.
- strictPolicy phân quyền rõ theo method, không có fallback cho phép. HEAD được cấp quyền đọc **theo lựa chọn minh họa**, không phải yêu cầu mọi API bắt buộc hỗ trợ HEAD.
- Biến overrideRequested chỉ là cờ mô phỏng: trong triển khai thật, hệ thống phải chọn **không hỗ trợ method override** hoặc dùng cơ chế đã kiểm soát để mọi tầng nhận cùng effective method. Không có API HTTP tiêu chuẩn nào tự sinh cờ này.
- Kết quả strict=DENY đối với encoded/dot path chứng minh **rule mô phỏng từ chối chuỗi chưa chuẩn**, không chứng minh servlet hoặc firewall thực tế sẽ trả cùng mã HTTP. Một URL bị chặn 400 hay không map 404 vẫn có thể là kết quả an toàn.
- Ví dụ chỉ có resource ID 42 để nhìn rõ logic. Ứng dụng thật phải xử lý path variable và quyền **trên từng object/tenant**, không viết một danh sách ID hard-coded.

## 7. Kiểm thử tích hợp cần bao phủ cả matcher lẫn handler

### 7.1. Ma trận chức năng và bảo mật

Thực hiện theo từng nhóm identity (anonymous, DOC_READ, DOC_EDIT, DOC_DELETE, admin nếu có) và từng route được publish. Giữ method/path thật giống production.

| Thử nghiệm | Kết quả cần chứng minh |
| --- | --- |
| DOC_READ + GET /api/documents/42 | Được đọc nếu có quyền object/tenant |
| DOC_READ + DELETE /api/documents/42 | Không xóa, không gọi service xóa |
| DOC_READ + PATCH /api/documents/42 | Không sửa dữ liệu, kể cả khi có CSRF hợp lệ |
| DOC_DELETE + DELETE /api/documents/42 | Được phép nếu quyền object/tenant và điều kiện nghiệp vụ đều hợp lệ |
| Method không đăng ký | Không khớp một nhánh quyền rộng và không chạy handler nhạy cảm |
| HEAD trên route GET | Hành vi theo chính sách đã khai báo; không vô tình chạy logic ghi |
| OPTIONS preflight hợp lệ | Được CORS xử lý theo cấu hình, không mang nghĩa cấp quyền cho DELETE/PATCH thực |
| POST _method=DELETE khi filter bật | Security và handler đều đánh giá DELETE; quyền đọc không đủ |
| Header X-HTTP-Method-Override khi app/gateway có hỗ trợ | Method hiệu lực nhất quán, kiểm tra đúng authority |
| Alias, trailing slash, double slash, dot-segment | Chặn hoặc phân quyền đúng sau routing; không có bypass |
| Encoded slash/percent, semicolon, double encoded | Bị firewall/container chặn hoặc xử lý thống nhất; không có dữ liệu nhạy cảm lộ ra |
| Context path, servlet phụ, proxy rewrite | Đường đi thực vẫn vào đúng SecurityFilterChain/rule |
| Một route có id và query chọn tenant khác | Service kiểm tra tenant/owner của tài nguyên đích |
| Internal forward/error dispatch | Dispatcher phù hợp được bảo vệ; không vô tình chuyển tới endpoint nhạy cảm |
| Nhiều filter chain / rule chồng lấp | Chứng minh chain đầu tiên và rule đầu tiên là lựa chọn dự kiến |

**Không đòi mọi request bất thường phải trả 403.** StrictHttpFirewall có thể trả lỗi request (thường là 400 tùy cấu hình), MVC có thể trả 404/405, xác thực có thể đưa tới 401 hoặc redirect. Tiêu chí bảo mật là: không có truy cập thành công trái quyền, không có side effect và không có dữ liệu nhạy cảm được trả ra. Với ca chính xác là principal đã xác thực, route tồn tại và permission thiếu, 403 thường là kỳ vọng hợp lý.

### 7.2. Test MockMvc xuyên SecurityFilterChain

Trong dự án Spring Boot, sử dụng spring-security-test, Spring Boot test và MockMvc gắn với context thật. Đoạn sau là **trích đoạn test tích hợp** (không phải Java độc lập; phụ thuộc SecurityFilterChain và API của ứng dụng):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentRoutingSecurityIT {

    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readPermissionCannotDelete() throws Exception {
        mvc.perform(delete("/api/documents/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readPermissionCannotPatch() throws Exception {
        mvc.perform(patch("/api/documents/42").with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

Đối với endpoint có thật, cần bổ sung assert **service xóa/sửa không được gọi** (spy/mock thích hợp) hoặc so sánh trạng thái database trước và sau. Bổ sung test chiều ngược: principal DOC_DELETE được xóa hợp lệ, DOC_EDIT được PATCH hợp lệ; nếu tất cả đều 403 vì CSRF hoặc route không tồn tại thì bộ test chưa chứng minh permission. Đảm bảo MockMvc đã áp bộ lọc Spring Security; @AutoConfigureMockMvc trong cấu hình Boot thông thường đăng ký filter, còn khi tự dựng MockMvc cần thêm springSecurity() để tránh test controller trực tiếp mà bỏ qua chain.

### 7.3. Test server thật phía sau proxy

MockMvc không mô phỏng đầy đủ bước giải mã URL của connector HTTP, servlet container hay rewrite của reverse proxy. Vì vậy cần test bổ sung ở môi trường staging/test có **cùng proxy và cùng loại servlet container/cấu hình production**, dùng HTTP client gửi request-target thô khi thư viện hỗ trợ.

- Gửi GET, HEAD, POST, PATCH, DELETE đến route chính và alias, xác nhận rule permission và handler tương ứng.
- Gửi path có trailing slash, double slash, dấu chấm/phần trăm, semicolon và mã hóa lặp; ghi kết quả thực ở proxy, firewall, MVC và side effect.
- Kiểm tra context path, servlet path và rewrite; test các RequestMatcher trên chain hẹp lẫn chain fallback.
- Nếu frontend sử dụng method override, test cả biến thể có/không có filter, thứ tự filter và CSRF.
- Test proxy chỉ chấp nhận header forwarding từ hop đáng tin; request từ Internet tự thêm header không được đổi phạm vi route/tenant.

Các request path không chuẩn có thể bị HTTP client tự normalize trước khi gửi. Khi cần kiểm tra dot-segment, chọn công cụ giữ nguyên request-target (ví dụ curl với --path-as-is cho test nội bộ), đồng thời ghi lại request được proxy nhận để chắc chắn đã test đúng payload.

### 7.4. Kiểm tra phân quyền đối tượng

Kể cả khi SecurityFilterChain match chính xác, URL /api/documents/42 có thể trả một đối tượng của tenant khác. Phân quyền chỉ theo DOC_READ/DOC_EDIT/DOC_DELETE không tự giải quyết **IDOR/BOLA**. Cần kiểm tra object ID, tenant/owner, trạng thái đối tượng và action thật tại tầng service, ví dụ bằng method security hay policy service. Test cùng user nhưng đổi id/tenant và dùng alias khác; mọi lối vào cùng một object phải áp cùng kết quả chính sách.

## 8. Cách điều tra khi test phát hiện chênh lệch

1. **Xác nhận request thật:** method, raw request-target, headers forwarding/override và URL được proxy chuyển tới Java. Không ghi token/secret vào log công khai.
2. **Xác nhận firewall:** request bị StrictHttpFirewall từ chối, được bọc cho matching hay đã đi tiếp? Nếu có RequestRejectedException, đừng “sửa” bằng cách tắt firewall trước khi hiểu nguyên nhân.
3. **Xác nhận chain được chọn:** securityMatcher và thứ tự các SecurityFilterChain. Cần chứng minh các alias không rơi vào một chain thiếu rule.
4. **Xác nhận rule đầu tiên khớp:** rule GET/POST/PATCH/DELETE đúng thứ tự; permitAll rộng có che các rule hẹp không?
5. **Xác nhận handler và service:** cùng request được MVC định tuyến đến đâu; hành động thật là read, export, modify hay delete; quyền trên object/tenant được kiểm tra ở đâu?
6. **Xác nhận kết quả:** mã HTTP, body được trả, thay đổi dữ liệu và bản ghi audit. Đánh giá thành công theo nguyên tắc **không có side effect hoặc lộ dữ liệu khi trái quyền**, không chỉ theo việc nhận 403.

Sai sót phổ biến là so sánh path bằng startsWith, so sánh chuỗi raw sau khi tự decode, lấy HTTP method trước một filter override, cho phép mọi path không được liệt kê, dựa vào CORS hoặc CSRF như thể chúng là authorization, dùng một filter chain chỉ áp /api/** mà quên alias, hoặc bỏ qua test thực tế phía sau reverse proxy.

## 9. Tiêu chí hoàn thành và tài liệu tham khảo

Một bộ bảo vệ đủ tốt cho phạm vi bài này cần chứng minh: **(1)** mọi route đến chức năng nhạy cảm được một SecurityFilterChain phù hợp bao phủ; **(2)** method và business action tương ứng đúng authority; **(3)** biến thể path không tạo khác biệt giữa matching và routing dẫn tới bypass; **(4)** request bất thường bị loại hoặc xử lý thống nhất; **(5)** quyền object/tenant được kiểm tra tại service; **(6)** test kiểm chứng cả HTTP response lẫn việc không có side effect.

Tài liệu chính thức để đối chiếu với phiên bản framework đang sử dụng:

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): thứ tự matcher, HTTP method, SecurityFilterChain, default deny.
- [Spring Security – HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): khác biệt URL, StrictHttpFirewall, HTTP method allowlist.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước cơ chế xác thực/phân quyền.
- [Spring Security – Spring MVC test integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): áp filter bảo mật trong MockMvc.
- [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): thiết lập spring.mvc.hiddenmethod.filter.enabled.

Quy tắc xuyên suốt: **cùng một thao tác nghiệp vụ phải đòi cùng quyền dù người gọi chọn route alias, phương thức HTTP hoặc cách viết request khác nhau; khi chưa có phép kiểm tra quyền chắc chắn, phải từ chối.**