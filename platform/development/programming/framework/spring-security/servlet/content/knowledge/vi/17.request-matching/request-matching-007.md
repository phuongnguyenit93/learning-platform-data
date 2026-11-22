# AntPathRequestMatcher, MvcRequestMatcher và lưu ý khi đọc cấu hình cũ trong Spring Security Servlet

## 1. Mục tiêu và phạm vi

Khi bảo vệ một ứng dụng **Spring Security Servlet**, chúng ta thường viết các quy tắc kiểu “GET /api/public được truy cập tự do”, “GET /api/projects/{id} phải đăng nhập”, “/api/admin yêu cầu ROLE_ADMIN”. Đằng sau những quy tắc đó là một câu hỏi quan trọng: **request nào thực sự khớp với mẫu đường dẫn và HTTP method đã khai báo?**

Spring Security dùng các đối tượng triển khai **RequestMatcher** để trả lời câu hỏi này. Hai tên thường gặp khi đọc code cũ là:

- **AntPathRequestMatcher**: so khớp đường dẫn theo kiểu Ant-style và có thể ràng buộc HTTP method.
- **MvcRequestMatcher**: tích hợp với cách Spring MVC hiểu request mapping thông qua **HandlerMappingIntrospector**, đặc biệt hữu ích khi controller cũng dùng các mẫu đường dẫn MVC.

Với code Spring Security 6 trở lên, cần phân biệt thêm **securityMatcher(...)** chọn một **SecurityFilterChain**, **requestMatchers(...)** tạo các quy tắc authorization *bên trong chain*, và những API lịch sử như **antMatchers**, **mvcMatchers**, **authorizeRequests** hoặc **WebSecurityConfigurerAdapter**.

Sau bài này bạn có thể:

1. Giải thích hợp đồng của RequestMatcher, đường đi của một Servlet request và ý nghĩa true/false.
2. So sánh AntPathRequestMatcher và MvcRequestMatcher theo nguồn ngữ nghĩa, path, method, servlet path và bối cảnh Spring MVC.
3. Đọc cấu hình Spring Security 5.x dùng antMatchers/mvcMatchers/antMatcher mà không nhầm giữa chọn filter chain và phân quyền.
4. Viết cấu hình mới bằng SecurityFilterChain + authorizeHttpRequests + RequestMatcher tường minh.
5. Biết khi nào cần HandlerMappingIntrospector và tại sao có nhiều Servlet hoặc nhiều SecurityFilterChain làm thay đổi kết quả.
6. Chạy demo **Java 17+ / Spring Boot 3.3.13 / Spring Security 6 / Maven**, thử bằng curl và kiểm thử với MockMvc.
7. Tránh những sai sót phổ biến: wildcard quá rộng, quy tắc đặt sai thứ tự, tưởng URL query là path, nhầm 401 với 403, bỏ qua CSRF, hoặc tin rằng đổi tên DSL đồng nghĩa giữ nguyên semantics.

**Phạm vi:** Servlet stack, chủ yếu Spring MVC. WebFlux dùng cơ chế matcher và security filter chain khác. Những khuyến nghị về API được gắn với nhánh phiên bản của ví dụ; khi nâng cấp Spring Security, cần kiểm tra API/deprecation theo **đúng phiên bản đang chạy**.

## 2. RequestMatcher thực chất làm gì?

Trong Spring Security Servlet, **RequestMatcher** là một interface nhận đối tượng **HttpServletRequest** và trả về kết quả có khớp điều kiện không.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

// Chữ ký khái niệm từ interface:
boolean matches(HttpServletRequest request);
~~~

Đây là mảnh minh họa hợp đồng, không phải một Java file độc lập: không thể đặt method tự do ở top level. Trong code thực, Spring Security gọi matcher để chọn chain hoặc đối chiếu authorization rules.

**RequestMatcher không phải AuthenticationManager.** Kết quả matches(request) == true chỉ nói rằng request thỏa *điều kiện*, không chứng minh người dùng đã đăng nhập hoặc đủ quyền.

Ví dụ:

~~~text
GET /api/projects/42
   |
   | path/method matcher?
   v
MvcRequestMatcher(GET, "/api/projects/{id}") -> true
   |
   | authorization policy?
   v
authenticated() -> cần Authentication hợp lệ
   |
   +-- Chưa đăng nhập: thường 401 với HTTP Basic
   +-- Đăng nhập hợp lệ: tiếp tục đến MVC controller
~~~

Nếu một matcher cho /api/admin trả true thì quy tắc **hasRole("ADMIN")** mới quyết định yêu cầu quyền. Nếu không khớp, Spring Security có thể thử quy tắc tiếp theo hoặc rơi vào **anyRequest().denyAll()**. Đừng mặc định request không khớp sẽ tự trả HTTP 404: security có thể chặn trước khi DispatcherServlet tìm controller.

### RequestMatcher có thể kiểm tra gì?

Một số implementation và composition cho phép kiểm tra:

- Đường dẫn request.
- HTTP method (GET, POST, PUT...).
- Servlet path hoặc những thuộc tính request khác tùy matcher.
- Header, IP, một predicate tùy biến hoặc kết hợp **AndRequestMatcher / OrRequestMatcher / NegatedRequestMatcher**.

Đề bài này tập trung vào **AntPathRequestMatcher** và **MvcRequestMatcher**; không đồng nhất mọi loại RequestMatcher với pattern matching kiểu Ant.

## 3. Hai lớp rất dễ nhầm: securityMatcher và requestMatchers

Một request trước hết phải được gắn với **SecurityFilterChain** thích hợp. Sau đó, trong chain được chọn, các filter thực thi authentication và authorization.

~~~text
HTTP Servlet request
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy
        |
        +-- SecurityFilterChain @Order(1)
        |       securityMatcher("/api/**") ?
        |
        +-- SecurityFilterChain @Order(2)
        |       securityMatcher("/**") ?
        |
        v
Chain KHỚP đầu tiên theo thứ tự
        |
        v
BasicAuthenticationFilter / các filter phù hợp
        |
        v
AuthorizationFilter
        |
        +-- requestMatchers(GET, "/api/public").permitAll()
        +-- requestMatchers(GET, "/api/admin").hasRole("ADMIN")
        +-- anyRequest().denyAll()
        |
        v
DispatcherServlet / Controller (nếu được phép)
~~~

| Vị trí | API thường gặp | Ý nghĩa |
| --- | --- | --- |
| **Chọn chain** | http.securityMatcher(...) | Chain này có xử lý request không? |
| **Chọn rule authorization** | authorizeHttpRequests(...).requestMatchers(...) | Rule nào áp dụng trong chain đã chọn? |
| **Khai endpoint MVC** | @GetMapping, @PostMapping, @RequestMapping | Controller/handler nào tiếp nhận request nếu tới MVC? |

**Quy tắc tối quan trọng:** một request chỉ đi qua **chain đầu tiên khớp** trong FilterChainProxy, không tự chạy tất cả chain. Nếu không chain nào khớp và không có lớp bảo vệ khác, request có thể đi qua mà **không được áp Spring Security**. Vì vậy cấu hình nhiều chain phải có kiểm tra phạm vi phủ và một chain fallback rõ ràng nếu cần.

**securityMatcher("/api/**") không tự cho phép /api/**.** Nó chỉ chọn chain; trong chain vẫn phải khai authentication/authorization. Ngược lại, **requestMatchers("/api/**").permitAll()** là quy tắc cho phép truy cập rất rộng trong một chain và có thể làm lộ endpoint nếu đứng trước rule hạn chế hơn.

### Ví dụ sai thứ tự rule

~~~java
// Mảnh minh họa: KHÔNG đưa thứ tự này vào production.
authorize
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().denyAll();
~~~

Nếu rule đầu tiên đã khớp /api/admin, quy tắc ADMIN sau đó không còn được xét. Hãy đặt các quy tắc cụ thể và nhạy cảm trước wildcard rộng, hoặc tránh permitAll trên /api/** khi không thực sự có nhu cầu.

Đây là fragment trong lambda authorizeHttpRequests, không phải Java class độc lập.

## 4. AntPathRequestMatcher: cách đọc mã cũ

**AntPathRequestMatcher** nằm trong package:

~~~text
org.springframework.security.web.util.matcher.AntPathRequestMatcher
~~~

Nó có thể được tạo với path pattern và tùy chọn HTTP method. Ví dụ dành cho code sử dụng nhánh Spring Security 6 tương thích với class này:

~~~java
RequestMatcher reportsGet =
    new AntPathRequestMatcher("/api/reports/**", "GET");
~~~

Đây là fragment; trong class đầy đủ cần import RequestMatcher và AntPathRequestMatcher. **GET** là ràng buộc method, còn **/api/reports/**** là pattern path.

### 4.1. Ngữ nghĩa Ant-style

Những ký hiệu thường gặp:

| Pattern | Chủ đích | Cẩn trọng |
| --- | --- | --- |
| **/api/public** | Một path cụ thể | Không suy ra có hỗ trợ trailing slash/encoded variants giống mọi MVC cấu hình |
| **/api/reports/** | Những đường dẫn con theo Ant-style | Rộng hơn một endpoint cần đúng một tham số |
| **/api/reports/* ** | Một segment path sau /reports/ | Dấu * không có ý nghĩa tương đương ** trên mọi vị trí |
| **/api/** | Phạm vi API rộng | Không nên dùng permitAll nếu có endpoint nhạy cảm |
| **/** | Phạm vi gần như toàn bộ | Phù hợp làm fallback chain/rule có chủ đích, không làm rule public tùy tiện |

Trong bảng trên, khoảng trắng sau dấu * ở nhãn **/api/reports/* ** chỉ để Markdown không làm nhầm ký hiệu emphasis; pattern thực trong code là **/api/reports/** với một dấu sao ở cuối nếu định nghĩa một segment. Ví dụ minh họa rõ bằng block:

~~~text
One segment: /api/reports/*
Many levels: /api/reports/**
~~~

**Đừng chỉ nhìn pattern rồi dự đoán chính xác tất cả edge case** như slash ở cuối, path rỗng, percent-encoding, dấu chấm phẩy hoặc path normalization. Những trường hợp đó còn phụ thuộc implementation, HttpFirewall, phiên bản framework và cấu hình container. Cần test bằng request thật trên stack đang triển khai.

### 4.2. Nó so khớp phần nào của HttpServletRequest?

Với AntPathRequestMatcher truyền thống, đường dẫn thường được suy từ **servletPath + pathInfo** trên HttpServletRequest. **Query string không phải phần path** dùng để đối chiếu.

~~~text
GET /api/reports/42?download=false
    ^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^
    request path     query string
~~~

Một rule cho path /api/reports/42 thường không thay đổi kết quả chỉ vì query parameter khác nhau. Nếu nghiệp vụ cần kiểm tra owner, reportId hoặc query parameter, phải làm **authorization ở tầng dữ liệu/nghiệp vụ** hoặc RequestMatcher đặc biệt có thiết kế phù hợp; không thể suy ra quyền truy cập tài nguyên từ path match đơn thuần.

Khi tự viết unit test với MockHttpServletRequest, cần để **servletPath/pathInfo** thể hiện đúng path mà matcher đọc; chỉ thay **requestURI** không phải lúc nào cũng phản ánh dữ liệu matcher sử dụng. Mục kiểm thử sẽ có ví dụ đặt servletPath tường minh.

### 4.3. AntPathRequestMatcher có phải lựa chọn mặc định mới?

Không nên xem nó là lựa chọn mặc định tương lai. Trong các nhánh Spring Security mới hơn, các API Ant-style có thể bị **deprecated và định hướng thay thế** bằng request matching dựa trên PathPattern. Đặc biệt khi nâng cấp lên những phiên bản có thay đổi API, hãy xem Javadoc/migration guide của **chính phiên bản** trước khi sao chép constructor AntPathRequestMatcher từ một bài cũ.

Trong bài này AntPathRequestMatcher được dùng chủ yếu để **đọc/kiểm thử cấu hình lịch sử**. Ví dụ ứng dụng mới sẽ sử dụng **MvcRequestMatcher** một cách tường minh để mô tả MVC endpoint trong môi trường Spring Security 6.

## 5. MvcRequestMatcher: gắn ngữ nghĩa với Spring MVC

**MvcRequestMatcher** là một RequestMatcher tích hợp với Spring MVC, sử dụng **HandlerMappingIntrospector** để nhận diện request theo mô hình mapping của MVC.

Tên đầy đủ:

~~~text
org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher
org.springframework.web.servlet.handler.HandlerMappingIntrospector
~~~

Giả sử có Spring MVC controller:

~~~java
@GetMapping("/api/reports/{reportId}")
public ReportDto show(@PathVariable String reportId) {
    // Fragment: ReportDto và dữ liệu nghiệp vụ chưa được định nghĩa tại đây.
    return reportService.find(reportId);
}
~~~

Đây chỉ là fragment để minh họa path variable của MVC; không coi là đoạn biên dịch độc lập. Đường dẫn **/api/reports/{reportId}** biểu diễn route một report theo cách MVC đọc pattern. Một MvcRequestMatcher có thể được định nghĩa tương ứng:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector);

RequestMatcher reportGet =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

Trong đó **introspector** là một **HandlerMappingIntrospector** được cung cấp trong ngữ cảnh MVC. Mục 10 có SecurityConfig đầy đủ và compile được.

### 5.1. Vì sao cần HandlerMappingIntrospector?

Spring MVC có thể thay đổi chiến lược route matching theo framework version/cấu hình, ví dụ PathPatternParser và các quy tắc xử lý path. MvcRequestMatcher dựa trên thông tin từ MVC thay vì tự áp một bộ quy tắc Ant độc lập lên mọi request.

Hệ quả thực tế:

- Muốn khớp với controller MVC thì MvcRequestMatcher có lợi thế về sự nhất quán.
- Không nên dựng một HandlerMappingIntrospector không thuộc đúng ApplicationContext của DispatcherServlet rồi kỳ vọng mapping luôn đồng nhất.
- Trong Spring Boot MVC app thông thường, một bean HandlerMappingIntrospector được framework cung cấp để có thể inject vào SecurityConfig.
- Với nhiều DispatcherServlet hoặc nhiều Servlet không phải MVC, cần xác định matcher dành cho servlet nào và kiểm tra routing; không nên mặc định một MVC matcher áp đúng toàn bộ web app.

### 5.2. Gắn HTTP method

MvcRequestMatcher.Builder có thể xây matcher cho đúng method:

~~~java
RequestMatcher getReport =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

Trong trường hợp này **POST** cùng path không khớp matcher **GET**. Nhưng **không khớp một authorization rule** không tự đảm bảo HTTP 405: nếu request rơi vào **anyRequest().denyAll()**, security có thể trả 401/403 trước khi MVC xử lý và trả Method Not Allowed.

Nếu muốn contract 405 chuẩn cho một MVC endpoint, cần xem tương tác giữa mapping, authorization và exception handling, thay vì kỳ vọng RequestMatcher tự phát status 405.

### 5.3. Servlet path và context path

**Servlet path** không phải lúc nào cũng là path trong URL sau hostname. Một app có thể chạy với context path hoặc DispatcherServlet mapping khác root. **MvcRequestMatcher.Builder.servletPath(...)** giúp chỉ rõ servlet path khi cần.

Ví dụ fragment cấu hình cho DispatcherServlet được map ở một servlet path khác:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

RequestMatcher protectedGet =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

Fragment trên **chỉ áp dụng khi DispatcherServlet và mapping thực tế phù hợp với servletPath "/mvc"**. Không thêm servletPath("/mvc") vào project demo root path ở mục 10, vì app root sẽ không khớp như dự kiến. Khi triển khai dưới context path, phân biệt contextPath, servletPath và pathInfo; dùng MockMvc/integration test ở đúng cách deploy.

**Dễ nhầm:** MvcRequestMatcher không được dùng để suy ra quyền xem một report từ việc route có biến {reportId}. Matcher chỉ nhận dạng request; kiểm tra “report này thuộc user nào?” phải ở phương thức/service có authorization đúng dữ liệu.

## 6. So sánh trực diện Ant và MVC matcher

| Tiêu chí | AntPathRequestMatcher | MvcRequestMatcher |
| --- | --- | --- |
| Nguồn ngữ nghĩa | Ant-style path matching | Ngữ nghĩa Spring MVC thông qua HandlerMappingIntrospector |
| Bối cảnh dùng | Đọc code cũ, một số filter/rule cũ, URL ngoài MVC có kiểm soát | Bảo vệ endpoint Spring MVC trong nhánh hỗ trợ class này |
| Path variable | Có thể xử lý Ant pattern; không mặc nhiên đồng bộ toàn bộ MVC mapping | Phù hợp với những pattern dùng ở MVC, như /items/{id} |
| HTTP method | Có constructor nhận method dạng String | Builder hỗ trợ HttpMethod |
| MVC context | Không cần HandlerMappingIntrospector | Cần HandlerMappingIntrospector phù hợp |
| Servlet path | Dựa vào các phần request path của Servlet | Có thể cấu hình servletPath trên builder |
| Query string | Không phải phần path thông thường | Không phải phần path của MVC matcher thông thường |
| Trailing slash, encoding, path parameter | Có thể khác Spring MVC config | Hướng tới cách MVC xử lý, vẫn phải test |
| Nâng cấp framework | Cần xem API deprecation và thay thế PathPattern theo version | Cần xem MVC matcher còn được khuyến nghị ở version đang dùng không |

**Đừng tạo “bảng kết quả chắc chắn” cho mọi wildcard/URL Unicode bằng suy luận.** Ví dụ, khi một controller dùng MVC path pattern khác cấu hình AntPathMatcher, các edge case về decoded path, dấu chấm phẩy hay trailing slash có thể khác nhau. Thay vì dựa vào trí nhớ về một phiên bản cũ, hãy viết regression tests cho các route nhạy cảm.

### Cùng một URL nhưng hai ý niệm khớp khác nhau

~~~text
Spring MVC mapping: GET /api/reports/{reportId}
Legacy security:     /api/reports/**
Intended rule:       allow authenticated()
Unexpected scope:    có thể rộng hơn một report một segment
~~~

Nếu controller chỉ có route một segment, một Ant wildcard quá rộng có thể áp rule tương tự cho những route mới dưới /api/reports/** trong tương lai. Chọn matcher hẹp và có fallback denyAll. Nếu API muốn cả phân hệ /api/reports/**, hãy công bố rõ phạm vi và test từng nhóm quyền.

## 7. Đọc DSL cũ: antMatchers, mvcMatchers, antMatcher

Trong dự án Spring Security 5.x / WebSecurityConfigurerAdapter, có thể gặp:

~~~java
// Fragment cấu hình lịch sử; KHÔNG dùng nguyên trong Spring Security 6.
@Override
protected void configure(HttpSecurity http) throws Exception {
    http.antMatcher("/api/**")
        .authorizeRequests()
        .antMatchers("/api/public").permitAll()
        .antMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated();
}
~~~

Những tên method trông gần giống nhau nhưng có vai trò khác:

| Cấu hình lịch sử | Ý nghĩa lịch sử | Hướng đọc khi chuyển sang cấu hình bean mới |
| --- | --- | --- |
| **http.antMatcher("/api/**")** | Chọn phạm vi của HttpSecurity/security chain | **http.securityMatcher(...)** |
| **authorizeRequests().antMatchers(...)** | Áp luật authorization bằng matcher Ant | **authorizeHttpRequests().requestMatchers(...)** với matcher/semantics được chọn rõ |
| **authorizeRequests().mvcMatchers(...)** | Áp luật authorization bằng matcher gắn MVC | Tạo MvcRequestMatcher và dùng trong **requestMatchers(...)** nếu nhánh version phù hợp |
| **authorizeRequests()** | DSL authorization cũ | **authorizeHttpRequests(...)** |
| **WebSecurityConfigurerAdapter** | Kiểu cấu hình kế thừa class | **@Bean SecurityFilterChain** và các bean liên quan |
| **web.ignoring().antMatchers(...)** | Bỏ qua Spring Security filters ở URL | Cân nhắc **permitAll** trước; không chuyển mù thành bỏ qua mọi filter |

**Cảnh báo:** chuyển đổi DSL không phải chỉ thay tên method. Ví dụ:

~~~java
// Sai về ý định khi muốn CHỌN filter chain cho /api/**:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll());
~~~

Code fragment này không tương đương với **http.antMatcher("/api/**")** cũ: nó **cho phép** những request API khớp pattern trong chain hiện tại, khác hoàn toàn với chọn phạm vi chain. Muốn giữ chain selector, dùng **securityMatcher(...)** và khai authorization rule riêng bên trong.

### WebSecurityConfigurerAdapter đã biến mất khỏi Spring Security 6

Không cố thêm import WebSecurityConfigurerAdapter vào project Boot 3/Security 6 rồi mong biên dịch. Cấu hình hiện đại tạo các bean SecurityFilterChain, UserDetailsService/AuthenticationProvider, PasswordEncoder hoặc các thành phần khác theo nhu cầu.

Những từ khóa **antMatchers** và **mvcMatchers** trong các bài hướng dẫn cũ có thể không còn overload DSL tương ứng ở các phiên bản mới. Đọc Javadoc của **bản Security thực tế** và chọn matcher tường minh nếu có nghi ngờ về chiến lược mặc định.

### requestMatchers(String...) có luôn là Ant không?

**Không nên khẳng định như vậy.** Các overload requestMatchers nhận chuỗi đường dẫn có thể chọn matcher dựa vào **classpath, servlet environment, Spring Security version và cấu hình**. Với Spring MVC trên classpath, một số nhánh Spring Security có cơ chế chọn matcher gắn MVC; với nhiều servlet, sự lựa chọn có thể trở nên không tường minh và cần configuration cụ thể.

Trong bài này, cấu hình ứng dụng **không phụ thuộc vào việc framework tự đoán**: nó tạo **MvcRequestMatcher.Builder(introspector)** và truyền trực tiếp các đối tượng MvcRequestMatcher vào requestMatchers(...).

## 8. Nhiều SecurityFilterChain và @Order: lỗi chỉ xuất hiện sau khi deploy

Giả sử hệ thống có:

~~~text
Chain #1 @Order(1) securityMatcher("/api/**")
Chain #2 @Order(2) securityMatcher("/**")
~~~

Request GET /api/admin được chain #1 tiếp nhận trước. Nó **không** tiếp tục chạy chain #2 chỉ vì một authorization rule bên trong chain #1 không khớp; chain #1 phải có quyết định tương ứng.

**Lỗi nguy hiểm:** chain #1 không có bất kỳ rule bảo vệ nào cho /api/admin, hoặc rộng rãi permitAll, trong khi developer tưởng chain #2 có hasRole("ADMIN") sẽ bảo vệ. Thực tế chain #2 không được dùng cho request đó.

**Lỗi khác:** một chain chọn quá hẹp, ví dụ chỉ khớp /api/private/**; request /api/private không khớp như người viết tưởng và không có fallback chain đủ bảo vệ. Hãy test cả base path, trailing slash và các biến thể được routing chấp nhận.

### Phân biệt matcher chọn chain và matcher permission bằng checklist

Khi thấy một cấu hình:

1. Tìm bao nhiêu bean **SecurityFilterChain**.
2. Xác định thứ tự bằng **@Order** và default order.
3. Đọc từng **securityMatcher(...)** hoặc matcher chọn chain tương đương.
4. Xác định request được chain **đầu tiên** nào nhận.
5. Trong chain đó, đọc **authorizeHttpRequests(...)** theo thứ tự khai báo.
6. Tìm rule **đầu tiên** khớp và hành động permitAll/authenticated/hasRole/denyAll.
7. Kiểm tra filter xác thực (formLogin/httpBasic/OAuth2 resource server...) có bật ở chain này không.
8. Đối chiếu handler MVC có route tương ứng không, nhất là khi có servlet path riêng.
9. Nếu không chain nào khớp, xem lại phạm vi bảo vệ trước khi kết luận request an toàn.

Các bước trên quan trọng hơn việc đoán tên method nào “giống antMatchers nhất”.

## 9. Request matching, Authorization và response HTTP không phải một thứ

Matcher chỉ tạo điều kiện nhánh. Mã HTTP cuối cùng phụ thuộc vào cả authentication, authorization, CSRF, exception handling, Spring MVC và các filter khác.

| Tình huống trong demo mục 10 | Kết quả thường thấy | Lý do |
| --- | --- | --- |
| GET /api/public không credentials | 200 | Rule permitAll |
| GET /api/projects/42 không credentials | 401 + Basic challenge | Rule authenticated không đạt |
| GET /api/projects/42 có learner hợp lệ | 200 | Basic authentication thành công |
| GET /api/admin có learner hợp lệ | 403 | Thiếu ROLE_ADMIN |
| GET /api/admin có admin hợp lệ | 200 | Đủ role |
| GET /api/projects/42/extra có admin hợp lệ | 403 | Không khớp rule endpoint, rơi vào denyAll |
| POST /api/admin có admin và CSRF hợp lệ | 403 | GET-only matcher không khớp, denyAll |
| POST /api/admin không CSRF token | Có thể 403 từ CsrfFilter | CSRF có thể chặn trước authorization |

**401 vs 403:** HTTP Basic thường gửi 401/WWW-Authenticate khi chưa xác thực; user đã xác thực mà thiếu quyền nhận 403. Nhưng 403 cũng có thể là CSRF failure. **405** chỉ thường được MVC đưa ra khi method không phù hợp và request đến được MVC; nếu security chặn trước thì không được mặc định 405.

**Không nên tắt CSRF chỉ để kiểm thử method rule.** Trong test POST, cấp token hợp lệ bằng spring-security-test **with(csrf())** để cô lập nhánh authorization. Với ứng dụng browser dùng session/cookie, bảo vệ CSRF cần đánh giá nghiêm túc; ngay cả HTTP Basic cũng có thể được browser nhớ và tự gửi credentials.

### RequestMatcher không quyết định quyền trên dữ liệu

Matcher cho GET /api/projects/{projectId} chỉ nói request có dạng endpoint dự kiến. Nó không biết:

- Dự án có thuộc người đăng nhập không.
- Dữ liệu có nhạy cảm hơn role chung không.
- User đã bị thu hồi quyền trên một dự án cụ thể chưa.
- Thông số projectId có hợp lệ hay không.

Đừng dùng permitAll/authenticated đơn thuần để bỏ kiểm tra ownership. Phần kiểm tra object-level authorization phải được thiết kế ở service/domain, hoặc dùng method security có kiểm tra nguồn dữ liệu đáng tin.

## 10. Ứng dụng runnable: chọn MvcRequestMatcher tường minh

Demo dùng:

- **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6**, **Maven**.
- Một SecurityFilterChain, tránh nhầm thứ tự nhiều chain khi học matcher.
- GET **/api/public**: công khai.
- GET **/api/projects/{projectId}**: yêu cầu user đã đăng nhập.
- GET **/api/admin**: chỉ ROLE_ADMIN.
- Các request còn lại: **denyAll**.
- HTTP Basic trên đường phát triển cục bộ, tài khoản mẫu BCrypt.
- **MockMvc** kiểm thử cả MVC matcher và một AntPathRequestMatcher độc lập.

Không có logic lưu/sửa dữ liệu ở các endpoint để demo chỉ tập trung vào matching. Các account là dữ liệu test, không dùng ra production. HTTP Basic truyền username/password dưới dạng Base64; **cần HTTPS** khi chứa credential thật.

### 10.1. Cấu trúc dự án

~~~text
matcher-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/matcherdemo/
    │   ├── MatcherDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/matcherdemo/
        └── MatchingIntegrationTest.java
~~~

### 10.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>matcher-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **một file Maven XML hoàn chỉnh**. Dùng Spring Boot parent để quản lý dependency versions tương thích. Đừng chép thêm các build block từ bài hướng dẫn khác vào cuối pom.xml.

### 10.3. MatcherDemoApplication.java

~~~java
package com.example.matcherdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatcherDemoApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig.java

~~~java
package com.example.matcherdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
            new MvcRequestMatcher.Builder(introspector);

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET, "/api/public"))
                    .permitAll()
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET,
                        "/api/projects/{projectId}"))
                    .authenticated()
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET, "/api/admin"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Tại sao demo dùng MvcRequestMatcher rõ ràng?**

1. SecurityConfig inject **HandlerMappingIntrospector** cùng Spring MVC app.
2. Builder tạo matcher với path template và HTTP method cho từng endpoint.
3. Rule **/api/projects/{projectId}** tương ứng @GetMapping cùng mẫu trong controller.
4. **/api/admin** đòi ROLE_ADMIN; user admin được seed bằng roles("ADMIN"), tạo authority tương ứng.
5. **anyRequest().denyAll()** chặn path/method không được công bố thay vì để lộ qua wildcard rộng.
6. **httpBasic** hỗ trợ kiểm thử 401/403 đơn giản, **formLogin disabled** tránh redirect trang HTML.
7. **STATELESS** làm rõ rằng mỗi request demo được xác thực qua HTTP Basic; việc này không tự tắt CSRF.
8. Không cần tự viết AuthenticationManager/BasicAuthenticationFilter; Spring Security kết nối UserDetailsService và PasswordEncoder vào flow username/password chuẩn của ứng dụng.

**Lưu ý khi chuyển phiên bản:** demo nhắm Spring Security 6.x trong Spring Boot 3.3.13. Với phiên bản mới hơn, API được khuyến nghị có thể thay đổi (đặc biệt PathPatternRequestMatcher); hãy kiểm tra compatibility trước khi copy code sang major version khác.

### 10.5. DemoController.java

~~~java
package com.example.matcherdemo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/api/projects/{projectId}")
    public Map<String, String> project(
            @PathVariable String projectId,
            Authentication authentication) {

        return Map.of(
            "projectId", projectId,
            "viewer", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

Controller **không** cố xác thực password hoặc kiểm tra role lần nữa; filter chain làm việc đó. Trong ứng dụng thật có dữ liệu dự án, service cần thêm **object-level authorization** để kiểm tra người dùng có quyền xem projectId cụ thể hay không.

Không có POST/PUT/DELETE trong controller; điều này giúp test matching theo HTTP method và CSRF riêng.

## 11. Thử ứng dụng bằng Maven và curl

Từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Yêu cầu JDK 17+ và Maven. Nếu dependency chưa có trong cache thì cần truy cập repository. Mặc định demo lắng nghe **http://localhost:8080** nếu không thay cấu hình cổng.

### 11.1. Public GET

~~~bash
curl -i http://localhost:8080/api/public
~~~

Kỳ vọng **HTTP 200** và:

~~~json
{"message":"public-ok"}
~~~

### 11.2. Endpoint bảo vệ không credentials

~~~bash
curl -i http://localhost:8080/api/projects/42
~~~

Kỳ vọng **401 Unauthorized** và HTTP Basic challenge, thường là header **WWW-Authenticate: Basic ...** trong cấu hình demo.

### 11.3. User thường xem project

~~~bash
curl -i -u learner:learner-pass \
  http://localhost:8080/api/projects/42
~~~

Kỳ vọng **200 OK**:

~~~json
{"projectId":"42","viewer":"learner"}
~~~

### 11.4. Query parameter không phải path

~~~bash
curl -i -u learner:learner-pass \
  "http://localhost:8080/api/projects/42?view=full"
~~~

Dù query string thêm **view=full**, matcher cho GET /api/projects/{projectId} vẫn nhận path tương ứng; controller không dùng query này, nên response projectId/viewer giữ như trên.

### 11.5. Thiếu role ADMIN

~~~bash
curl -i -u learner:learner-pass \
  http://localhost:8080/api/admin
~~~

Kỳ vọng **403 Forbidden**, vì username/password hợp lệ nhưng learner chỉ có ROLE_USER.

### 11.6. Có role ADMIN

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Kỳ vọng **200 OK** với:

~~~json
{"message":"admin-ok"}
~~~

### 11.7. Sai password

~~~bash
curl -i -u learner:incorrect-password \
  http://localhost:8080/api/projects/42
~~~

Kỳ vọng **401** vì authentication thất bại, khác với thiếu quyền ADMIN.

### 11.8. Path gần giống nhưng không phải route được cho phép

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/projects/42/extra
~~~

Kỳ vọng **403** do **anyRequest().denyAll()** trong chain, không phải vì người dùng thiếu quyền ADMIN. Đừng mặc định MVC trả 404 nếu security đã từ chối trước.

**Lưu ý bí mật:** các mật khẩu trong curl chỉ là dữ liệu demo. Với credentials thật, tránh để password trong shell history, script hoặc process listing; luôn dùng **HTTPS** trên đường truyền thực vì Basic Base64 không mã hóa bí mật.

## 12. Kiểm thử MockMvc qua cả filter chain và MVC

Tạo file **src/test/java/com/example/matcherdemo/MatchingIntegrationTest.java**:

~~~java
package com.example.matcherdemo;

import static org.hamcrest.Matchers.startsWith;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MatchingIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetNeedsNoLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void projectGetWithoutCredentialsIsChallenged() throws Exception {
        mvc.perform(get("/api/projects/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void mvcPathVariableMatchesValidProjectGet() throws Exception {
        mvc.perform(get("/api/projects/42")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.projectId").value("42"))
            .andExpect(jsonPath("$.viewer").value("learner"));
    }

    @Test
    void queryStringDoesNotChangeEndpointPath() throws Exception {
        mvc.perform(get("/api/projects/42")
                .param("view", "full")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.projectId").value("42"));
    }

    @Test
    void learnerIsForbiddenOnAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanReadAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-ok"));
    }

    @Test
    void adjacentPathIsNotAllowedByMvcRule() throws Exception {
        mvc.perform(get("/api/projects/42/extra")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postDoesNotMatchGetOnlyAdminRule() throws Exception {
        mvc.perform(post("/api/admin")
                .with(csrf())
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void legacyAntMatcherChecksServletPathAndHttpMethod() {
        AntPathRequestMatcher legacy =
            new AntPathRequestMatcher("/api/projects/**", "GET");

        MockHttpServletRequest good =
            new MockHttpServletRequest("GET", "/api/projects/42");
        good.setServletPath("/api/projects/42");
        assertTrue(legacy.matches(good));

        MockHttpServletRequest wrongMethod =
            new MockHttpServletRequest("POST", "/api/projects/42");
        wrongMethod.setServletPath("/api/projects/42");
        assertFalse(legacy.matches(wrongMethod));

        MockHttpServletRequest wrongPath =
            new MockHttpServletRequest("GET", "/api/admin");
        wrongPath.setServletPath("/api/admin");
        assertFalse(legacy.matches(wrongPath));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Điều kiểm thử xác nhận:**

1. Public endpoint không đòi đăng nhập.
2. Project URL không credentials bị 401 + Basic challenge.
3. MVC path template nhận đúng GET /api/projects/42 khi user hợp lệ.
4. Query parameter không thay đổi kết quả khớp path.
5. Learner không thể truy cập /api/admin dù đã xác thực.
6. Admin truy cập đúng quyền.
7. Path con /api/projects/42/extra không được coi là path template chỉ một project.
8. POST /api/admin có **CSRF token hợp lệ** vẫn không khớp GET-only permission và bị denyAll.
9. AntPathRequestMatcher lịch sử có thể kiểm tra riêng path và method; unit test đặt **servletPath** tường minh để matcher đọc đúng thông tin.

**MockMvc ở đây đi qua Spring Security filter chain**, nhờ @AutoConfigureMockMvc và spring-security-test, nên các test HTTP Basic xác minh việc user được xác thực qua hệ thống được cấu hình thật. Đây là kiểm thử tốt hơn việc chỉ dùng @WithMockUser khi mục tiêu là kiểm tra UserDetailsService/PasswordEncoder cùng authorization.

### Tại sao test POST lại dùng with(csrf())?

Trong ví dụ CSRF không bị tắt. Nếu POST /api/admin **thiếu** token thì CsrfFilter có thể từ chối ngay bằng 403, khiến test cũng “pass 403” nhưng không chứng minh được **GET-only matcher** đang hoạt động. Gắn with(csrf()) hợp lệ giúp request đi qua CSRF, tới rule authorization, nên bài test phản ánh đúng ý định kiểm tra method matcher.

### Tại sao test Ant không chỉ đặt requestURI?

AntPathRequestMatcher truyền thống sử dụng servletPath/pathInfo. MockHttpServletRequest có thể cần setServletPath để tái hiện phần path phù hợp. Trong test trực tiếp, đặt cả URI ở constructor và servletPath để không nhầm rằng một giá trị Mock riêng đã thể hiện toàn bộ Servlet mapping.

## 13. Khi nào nên dùng matcher nào?

**Khi đọc dự án Spring Security 5.x:** nếu thấy AntPathRequestMatcher hoặc antMatchers, trước tiên hãy xác định nó dùng cho chain selector hay authorization rule, rồi đọc patterns và thứ tự rules. Đừng tự động “hiện đại hóa” bằng thay toàn bộ bằng MVC matcher mà không test tác động tới servlet path, wildcard và encoding.

**Khi viết ứng dụng Spring MVC với Spring Security 6 thuộc nhánh hỗ trợ MvcRequestMatcher:** dùng MvcRequestMatcher tường minh có thể giúp bảo vệ route theo ngữ nghĩa MVC, nhất là khi có path variable. Tuy nhiên cần HandlerMappingIntrospector cùng context, và vẫn phải có authorization ở object/service khi dữ liệu cá nhân phụ thuộc ID.

**Khi ứng dụng có Servlet khác MVC:** tránh đưa MVC matcher một cách mù quáng lên mọi Servlet. Hãy xác định request mapping thật sự và chọn matcher tương ứng. Có thể sử dụng matcher không gắn MVC với method/path xác định rõ, hoặc strategy khác mà framework version hỗ trợ.

**Khi nâng cấp sang Spring Security mới hơn:** không mặc định AntPathRequestMatcher hay MvcRequestMatcher là giải pháp được khuyến nghị mãi mãi. Một số nhánh định hướng dùng **PathPatternRequestMatcher** và builder/path handling mới. Kiểm tra migration guide, các deprecation chính thức và test sau nâng cấp; không sao chép API của Boot 3.3 sang phiên bản khác mà không kiểm tra.

**Khi ứng dụng không cần matcher tường minh:** overload requestMatchers(String...) có thể thuận tiện, nhưng khi behavior phụ thuộc servlet/MVC hoặc security review cần chứng minh chính xác, hãy chọn RequestMatcher tường minh hoặc kiểm tra implementation thực tế của version. Không khẳng định chuỗi path luôn được diễn giải là Ant trong mọi version.

### Một quyết định nhanh

| Tình huống | Hướng xử lý |
| --- | --- |
| MVC controller có path variable, Spring Security 6 tương thích | Cân nhắc MvcRequestMatcher + HandlerMappingIntrospector |
| Sửa bug trong Ant rule cũ trước khi nâng cấp | Hiểu Ant semantics và thêm test regression trước |
| Nhiều servlet/DispatcherServlet | Xác định servletPath, context và matcher chain rõ ràng |
| Nhiều SecurityFilterChain | Thiết kế securityMatcher + @Order + fallback chain riêng |
| Rule có nhiều wildcard | Soát phạm vi cấp quyền và thứ tự, thêm denyAll |
| Có resource ID trong path | Matcher route + object-level authorization ở service |
| Nâng cấp Spring Security major version | Tham khảo migration guide/Javadoc của version đích và kiểm thử |

## 14. Các lỗi thường gặp khi chuyển cấu hình cũ

### Lỗi 1 — Đổi http.antMatcher thành requestMatchers(...).permitAll

Sai về ngữ nghĩa. antMatcher trên HttpSecurity trước kia chọn **phạm vi chain**. permitAll trong authorizeHttpRequests **cấp quyền** cho request khớp. Dùng securityMatcher để chọn chain, rồi viết authorization riêng.

### Lỗi 2 — Nghĩ antMatchers và mvcMatchers chỉ khác tên

Sai. Ant và MVC matchers có thể khác behavior ở các trường hợp path đặc biệt, servlet mapping, encoded path và trailing slash. Không nâng cấp bằng tìm/thay chuỗi mà không có test.

### Lỗi 3 — Đặt wildcard permitAll trước rule ADMIN

Ví dụ permitAll("/api/**") trước hasRole("ADMIN") có thể làm /api/admin bị cho phép. Rule đầu tiên khớp thường quyết định authorization; dùng mẫu hẹp và denyAll fallback.

### Lỗi 4 — Tin rằng SecurityFilterChain thứ hai sẽ bổ sung quyền cho chain thứ nhất

FilterChainProxy chọn chain **đầu tiên** khớp. Không cộng dồn các chain như middleware độc lập. Kiểm tra @Order và securityMatcher.

### Lỗi 5 — Dùng matcher GET nhưng kỳ vọng tự trả 405

Không khớp authorization rule có thể dẫn đến 401/403. 405 chỉ là hành vi của MVC mapping trong những điều kiện request tới được MVC. Kiểm thử đúng component chịu trách nhiệm.

### Lỗi 6 — Nhầm query string với URL path

Query parameters không phải path. Security rule cho /api/projects/{id} không kiểm tra project thuộc user nào, càng không dựa vào query string để quyết định ownership trừ khi có policy riêng.

### Lỗi 7 — Quên servlet path và context path

Một matcher cấu hình cho root MVC app có thể không còn phù hợp khi DispatcherServlet được map ở servlet path khác. Đừng lấy full URL rồi so bằng string equals tùy tiện; cấu hình và test trên topology thực tế.

### Lỗi 8 — Inject sai HandlerMappingIntrospector

MvcRequestMatcher cần nhìn đúng MVC application context. Với ứng dụng chia context hoặc nhiều servlet, phải cấu hình phù hợp; test tích hợp thay vì chỉ khởi tạo một matcher độc lập thiếu MVC handler mapping.

### Lỗi 9 — Dùng @WithMockUser rồi kết luận BasicAuthenticationFilter đã hoạt động

@WithMockUser tạo Authentication giả lập trong test. Nó hữu ích cho authorization, nhưng không chứng minh username/password được tra từ UserDetailsService. Khi cần kiểm tra cả flow, dùng HTTP Basic hoặc form login test thật.

### Lỗi 10 — Test POST thiếu CSRF rồi tuyên bố method rule đã được kiểm tra

POST bị 403 có thể do CsrfFilter. Nếu mục tiêu là matcher HTTP method, hãy gửi CSRF token hợp lệ trong MockMvc, hoặc kiểm tra trực tiếp RequestMatcher bằng MockHttpServletRequest.

### Lỗi 11 — Bỏ qua vùng không khớp chain

Nếu không SecurityFilterChain nào bảo vệ một request và không có cơ chế bảo vệ khác, request có thể đi tiếp ngoài Spring Security. Tạo fallback chain rõ ràng và test những URL ngoài dự kiến.

### Lỗi 12 — Dùng securityMatcher("/**") là đủ bảo mật

securityMatcher("/**") chỉ chọn chain. Bạn vẫn cần AuthenticationProvider, authorizeHttpRequests, CSRF/session policy và các rule cụ thể. Matcher khớp không tự ngăn truy cập.

### Lỗi 13 — Coi matchers là kiểm tra tài nguyên thuộc user

Dù /api/projects/42 trùng pattern, user có được phép xem project 42 còn phụ thuộc nghiệp vụ. Không thiếu object-level authorization.

### Lỗi 14 — Mang code AntPathRequestMatcher sang major version mới mà không kiểm tra

API có thể deprecated hoặc thay đổi. Chọn giải pháp matching được framework version hỗ trợ, kiểm tra migration guide và chạy toàn bộ security regression tests.

## 15. Quy trình đọc cấu hình cũ khi tiếp quản dự án

Đừng sửa ngay khi nhìn thấy antMatchers. Hãy đi qua từng bước:

1. **Ghi version thực tế**: Spring Security, Spring Framework, Boot và Servlet container; không dùng cú pháp của phiên bản khác.
2. **Liệt kê configuration beans**: SecurityFilterChain, WebSecurityConfigurerAdapter cũ, WebSecurityCustomizer và các filter được tự đăng ký.
3. **Xác định dispatcher**: app chạy root context hay context path; có nhiều DispatcherServlet hoặc Servlet không phải MVC không?
4. **Xác định chain selection**: antMatcher/securityMatcher và @Order; request nào đi qua chain nào?
5. **Tách authentication khỏi authorization**: form login, Basic, Bearer, session/CSRF; rule chỉ đòi role hay có method security?
6. **Đọc permission rules theo thứ tự**: permitAll/authenticated/hasRole/hasAuthority/denyAll; tìm wildcard bao trùm.
7. **Đối chiếu controller mappings**: @GetMapping, @PostMapping, path variable và method; không dựa riêng vào comments.
8. **Phân tích edge cases**: base path, trailing slash, encoded characters, semicolon path parameters, query string, method mismatch.
9. **Viết test trước khi đổi matcher**: cả trường hợp được phép và bị từ chối; đặc biệt negative tests.
10. **Chọn matcher tường minh khi cần**: Ant trong phiên bản đang chạy, MVC + introspector, hoặc PathPattern trên nhánh mới phù hợp.
11. **Nâng cấp theo migration guide**: sửa code để compile, rồi so hành vi HTTP trước/sau.
12. **Phân tích status bị thay đổi**: 401/403/404/405 có thể do thứ tự filter chứ không nhất thiết do controller.
13. **Xem xét CSRF khi method đổi**: không tắt toàn cục để test một endpoint.
14. **Kiểm tra default deny/fallback chain**: request không khớp bất kỳ permission rule hoặc chain nào không được vô tình trở thành public.
15. **Rà soát thông tin nhạy cảm**: không log Authorization header, CSRF token, password hoặc Session ID trong test/debug production.

**Nguyên tắc review:** thay đổi từ antMatchers sang requestMatchers phải chứng minh được *cùng phạm vi bảo vệ* hoặc có lý do thay đổi được ghi rõ, không chỉ chứng minh biên dịch thành công.

## 16. Bài tập thực hành có đáp án

### Bài A — Chọn chain hay chọn quyền?

Đọc hai cấu hình:

~~~java
http.securityMatcher("/api/**");
~~~

~~~java
authorize.requestMatchers("/api/**").permitAll();
~~~

Chúng tương đương không?

**Đáp án:** Không. Cấu hình thứ nhất chọn phạm vi của một chain; cấu hình thứ hai cấp permitAll cho pattern trong một chain. Thay nhầm có thể khiến /api/admin trở nên public.

### Bài B — GET-only rule

Một matcher cấu hình GET /api/admin, user admin gửi POST /api/admin. Matcher có trả true không? Response nhất thiết phải là 405 không?

**Đáp án:** Method không khớp nên matcher GET-only trả false. Response không nhất thiết 405: CSRF, authorization denyAll hoặc handler khác có thể xử lý trước MVC.

### Bài C — ROLE_ prefix

User được khai báo roles("ADMIN"). Rule hasRole("ADMIN") kiểm tra authority nào theo cấu hình mặc định?

**Đáp án:** ROLE_ADMIN. Nếu dùng authorities("ADMIN") thì không tự có prefix; có thể phải dùng hasAuthority("ADMIN") tùy thiết kế.

### Bài D — /api/reports/** quá rộng

Controller chỉ có GET /api/reports/{id}; liệu cho phép cả /api/reports/** có luôn đúng yêu cầu không?

**Đáp án:** Không nhất thiết. Wildcard Ant rộng có thể bao gồm các path con ngoài route một segment; nếu có route mới trong tương lai, rule có thể cấp quyền quá mức. Chọn matcher tương ứng endpoint/intent và thêm negative-path test.

### Bài E — Query parameter

GET /api/projects/42?view=full có khác path matcher của GET /api/projects/42 không?

**Đáp án:** Query string thông thường không phải path mà Ant/MVC path matcher so. Nhưng quyền xem project 42 cần kiểm tra ở service theo dữ liệu thực.

### Bài F — Hai chain

Chain thứ nhất match /api/**, chain thứ hai match /** và có rule ADMIN. Nếu chain thứ nhất nhận /api/admin, chain thứ hai có tự kiểm tra tiếp role không?

**Đáp án:** Không. Chỉ chain đầu tiên khớp được dùng, và trong đó phải có rule bảo vệ phù hợp.

### Bài G — @WithMockUser so với HTTP Basic

@WithMockUser(roles="ADMIN") giúp một test GET /api/admin pass. Điều đó đã chứng minh BCrypt PasswordEncoder và InMemoryUserDetailsManager được nối đúng chưa?

**Đáp án:** Chưa. @WithMockUser cung cấp Authentication test; muốn kiểm tra credential flow, dùng httpBasic("admin", "admin-pass") qua MockMvc.

### Bài H — Servlet path tùy biến

Một MVC app thay DispatcherServlet servletPath từ root sang /mvc. Có nên giữ nguyên mọi MvcRequestMatcher builder mà không test không?

**Đáp án:** Không. Kiểm tra servlet path, context path, HandlerMappingIntrospector và matcher constructor/builder. Cấu hình servletPath nếu thích hợp, rồi test URL thực.

### Bài I — CSRF cản test POST

POST /api/admin trả 403 nhưng không gửi CSRF. Có thể kết luận chính rule GET-only đã chặn không?

**Đáp án:** Chưa. CsrfFilter có thể trả 403 trước. Gắn CSRF token hợp lệ khi muốn cô lập kiểm tra method/authorization hoặc test matcher trực tiếp.

### Bài K — Nâng cấp API

Nhìn thấy dự án cũ dùng WebSecurityConfigurerAdapter, antMatchers và AntPathRequestMatcher. Bạn sẽ thay tất cả bằng string requestMatchers trước khi viết test chứ?

**Đáp án:** Không. Ghi nhận version, chain selection, servlet context và rule order, viết regression tests, chọn matcher phù hợp version đích và xác minh quyền truy cập không thay đổi ngoài ý muốn.

## 17. Checklist khi áp dụng RequestMatcher

- [ ] Đã xác định rõ **matcher chọn chain** hay **matcher áp luật authorization**.
- [ ] Đã biết ứng dụng dùng Spring Security version nào trước khi chọn Ant, MVC hoặc PathPattern matcher.
- [ ] Đã phân biệt AntPathRequestMatcher và MvcRequestMatcher về nguồn ngữ nghĩa.
- [ ] Nếu dùng MVC matcher, HandlerMappingIntrospector phải thuộc context MVC phù hợp.
- [ ] HTTP method được ràng buộc nếu đó là một phần của API contract.
- [ ] Đã kiểm tra context path, servlet path và nhiều servlet khi có.
- [ ] Không coi query string là path hoặc dùng route matching thay object-level authorization.
- [ ] Đã xem thứ tự securityMatcher + @Order trong ứng dụng có nhiều chain.
- [ ] Đã kiểm tra rule đầu tiên khớp không permitAll quá rộng.
- [ ] Có fallback denyAll hoặc chiến lược bảo vệ tương đương, không bỏ rơi URL.
- [ ] Đã phân biệt 401/403 từ security với 404/405 từ MVC.
- [ ] Các test GET và POST xét CSRF đúng để kết luận chính xác.
- [ ] Các endpoint nhạy cảm có test pass/fail với user đúng và sai role.
- [ ] Đã test wildcard, path variable, URL gần giống, phương thức sai và query string.
- [ ] Khi migrate antMatchers/mvcMatchers/WebSecurityConfigurerAdapter, đã đối chiếu security behavior chứ không chỉ compile.
- [ ] Không bỏ qua Spring Security filter chain bằng web.ignoring trừ khi biết rõ hệ quả.
- [ ] Có regression tests được chạy lại khi nâng cấp Spring Security/Servlet container.

**Kết luận:** **AntPathRequestMatcher** và **MvcRequestMatcher** đều thực hiện RequestMatcher nhưng không nên coi chúng hoán đổi vô điều kiện. Ant matcher mang semantics Ant-style thường gặp trong dự án cũ; MVC matcher sử dụng HandlerMappingIntrospector để phù hợp hơn với request mapping của Spring MVC. Khi đọc cấu hình lịch sử, điểm cốt lõi là phân biệt **http.antMatcher/securityMatcher** (chọn chain) với **antMatchers/mvcMatchers/requestMatchers** bên trong authorization (chọn rule). Hãy dùng matcher tường minh khi ngữ nghĩa quan trọng, giữ **deny-by-default**, và chứng minh bằng MockMvc các request được phép cũng như bị từ chối.
