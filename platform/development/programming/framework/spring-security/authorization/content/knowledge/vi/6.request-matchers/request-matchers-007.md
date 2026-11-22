# Đường dẫn có dấu gạch chéo cuối, chữ hoa và ký tự mã hóa trong RequestMatcher

## 1. Vì sao cùng một endpoint lại có nhiều dạng URL?

Trong ứng dụng Spring Boot/Spring Security, người viết policy thường nhìn thấy một route rõ ràng:

```text
GET /api/admin/users
```

Nhưng một HTTP client có thể gửi những biến thể:

```text
GET /api/admin/users/
GET /API/ADMIN/users
GET /api/admin%2Fusers
GET /api/%61dmin/users
GET /api/admin//users
GET /api/admin/../public
GET /api/admin;v=1/users
```

Ở đây, `%2F` là cách mã hóa percent của ký tự `/`; `%61` biểu diễn chữ `a`. Một số biến thể bị tầng trước ứng dụng **từ chối**, một số không khớp controller, một số được chuẩn hóa và có thể được định tuyến tới cùng logic. Kết quả phụ thuộc **Servlet container, proxy, firewall, RequestMatcher, cấu hình Spring MVC và phiên bản thư viện**. Vì vậy, không được khẳng định rằng mọi URL trong bảng đều được xử lý giống nhau.

Rủi ro lớn nhất không chỉ là lỗi 404 khó hiểu. Nếu **tầng phân quyền thấy một đường dẫn** nhưng **tầng xử lý nghiệp vụ thấy một đường dẫn khác**, hệ thống có thể cấp sai quyền: một endpoint quản trị bị biến thể URL đi qua một rule rộng hơn, hoặc request bị kiểm tra bằng đường dẫn trước khi giải mã rồi controller lại ánh xạ sau khi giải mã.

**Mục tiêu của bài**:

1. Hiểu tác động của **trailing slash**: `/reports` và `/reports/`.
2. Hiểu **case sensitivity**: `/admin`, `/Admin`, `/ADMIN`.
3. Hiểu percent encoding, double encoding, dấu gạch chéo mã hóa và path normalization.
4. Tách vai trò của `StrictHttpFirewall`, `SecurityFilterChain`, `RequestMatcher` và `@RequestMapping`.
5. Chọn quy ước canonical URL an toàn, không phá ranh giới quyền.
6. Viết rule bảo vệ ổn định và kiểm thử các biến thể ở MockMvc lẫn trên HTTP stack thực tế.

Ví dụ tập trung vào **Spring Security Servlet/Spring MVC**, Java 17+. WebFlux dùng những thành phần khác. Khi có nhiều version, hãy đối chiếu **resolved Spring Framework/Spring Security version** của project, không áp dụng một quan sát của môi trường này cho mọi hệ thống.

## 2. Đường đi của request: ai nhìn thấy URL ở bước nào?

```text
Client/browser/curl
      │
      ▼
CDN / load balancer / reverse proxy
      │   Có thể redirect, decode, gộp slash hoặc từ chối.
      ▼
Servlet container
      │   requestURI, contextPath, servletPath, pathInfo...
      ▼
Spring Security FilterChainProxy + HttpFirewall
      │   Kiểm tra/bao request và loại URL nguy hiểm.
      ▼
Chọn SecurityFilterChain (securityMatcher)
      │
      ▼
AuthorizationFilter + requestMatchers
      │   Matcher đầu tiên khớp sẽ quyết định policy.
      ▼
DispatcherServlet + HandlerMapping
      │   Chọn controller theo mapping của Spring MVC.
      ▼
Service/domain authorization
      │   Kiểm tra quyền trên đúng object/tenant/owner.
      ▼
Business action / response
```

Đây là sơ đồ khái niệm, không thay thế thứ tự chính xác của từng filter do dự án tùy chỉnh. Điều quan trọng:

- **Tầng proxy và container** có thể thay đổi hoặc từ chối URL trước khi Java code nhận được.
- **`HttpFirewall`** không phải authorization rule; nó ngăn/chuẩn hóa một số request không an toàn trước khi matcher dùng đường dẫn.
- **`securityMatcher`** chọn filter chain nào được dùng; nếu không chain nào khớp, request có thể không được Spring Security bảo vệ.
- **`requestMatchers`** quyết định quyền **bên trong chain** đã chọn.
- **Spring MVC `@RequestMapping`** định tuyến controller, có thể chịu quy ước path matching khác nếu cấu hình lệch.
- **Service policy** vẫn cần kiểm tra object/tenant. Việc URL trông giống tài nguyên được phép không chứng minh được quyền trên từng bản ghi.

**Nguyên tắc:** request dùng cho security matching và cho controller mapping phải có **cùng quan điểm về cấu trúc URL**. Với URL mơ hồ hoặc không được hỗ trợ, nên từ chối rõ ràng thay vì giải mã/chuẩn hóa nhiều lần theo các quy tắc khác nhau.

## 3. Trailing slash: /resource không mặc nhiên bằng /resource/

### 3.1. Hai URL khác nhau ở cấp path

```text
/api/reports
/api/reports/
```

Dấu `/` cuối làm thay đổi chuỗi đường dẫn. Theo cấu hình, request có thể:

- Khớp cùng handler và cùng security rule.
- Khớp security rule nhưng không khớp handler → có thể 404 sau khi đã qua authorization.
- Không khớp security rule, rơi vào fallback deny.
- Được proxy/filter redirect từ dạng có slash sang dạng canonical.
- Bị trả lỗi bởi tầng trước nếu quy ước của hệ thống yêu cầu URL chính xác.

**Không đoán hành vi của `requestMatchers("/api/reports")` chỉ từ tên API.** Kết quả phụ thuộc matcher implementation đang được dùng. Với `PathPatternParser` mặc định trong Spring Framework 6.x/7.x, việc tùy ý khớp thêm dấu slash cuối **không được bật**.

### 3.2. Thay đổi quan trọng ở Spring Framework 6

Trong `PathPatternParser`:

```text
Spring Framework 6.x mặc định:
  matchOptionalTrailingSeparator = false
  caseSensitive                 = true
```

Trước đó một số cấu hình lịch sử tự coi trailing slash là tùy chọn. Spring Framework 6.0 đổi default và deprecate chức năng tự động match dấu slash cuối vì vấn đề an toàn; tài liệu Framework 7.0 giới thiệu cách xử lý bằng `UrlHandlerFilter` thay vì dựa trên optional trailing-slash matching kiểu cũ.

Ví dụ với parsed PathPattern theo mặc định:

```text
Pattern: /api/reports

Path: /api/reports      -> MATCH
Path: /api/reports/     -> NO MATCH
```

Đây là kết quả **của pattern cụ thể với default parser**, không phải lời khẳng định rằng mọi `AntPathRequestMatcher`, matcher custom hoặc cấu hình Spring Security cũ xử lý giống hệt.

### 3.3. Khuyến nghị: một dạng URL chuẩn

Chọn một convention, ví dụ:

```text
Canonical: GET /api/reports
Alias:     GET /api/reports/
```

Sau đó quyết định rõ alias sẽ:

1. **Bị từ chối/không match:** đơn giản, chặt chẽ cho API yêu cầu URL chính xác.
2. **Được redirect một cách có chủ đích** về canonical URL; cần bảo đảm proxy và security xử lý trước/sau redirect nhất quán.
3. **Được hỗ trợ như route thứ hai** nếu sản phẩm cần tương thích client cũ; cả hai phải có **cùng policy** và được test.

Không nên sửa bằng cách bật toàn bộ cấu hình match rộng hơn chỉ để che lỗi một endpoint; việc thay đổi global parser có thể ảnh hưởng những URL nhạy cảm khác.

### 3.4. Nếu cả hai dạng thật sự cần hỗ trợ

Một cách khai báo rõ cho **hai đường dẫn** ở cả Spring MVC và lớp HTTP authorization:

```java
// Spring MVC controller fragment:
@GetMapping({"/api/reports", "/api/reports/"})
public List<ReportView> listReports() {
    return reportService.listVisibleReports();
}
```

Và trong cấu hình Spring Security tương ứng:

```java
.requestMatchers(
        HttpMethod.GET,
        "/api/reports",
        "/api/reports/"
).hasAuthority("report:read")
```

Đây là hai **fragment tích hợp**, cần dependencies, controller, service, imports và `SecurityFilterChain`. Việc liệt kê tường minh thường dễ giải thích hơn một giả định "hai URL tự động tương đương". Nếu về mặt nghiệp vụ chỉ một dạng được phép, không cần mở dạng còn lại.

### 3.5. Redirect bằng UrlHandlerFilter khi phiên bản hỗ trợ

Spring Framework **6.2+** có `UrlHandlerFilter` để xử lý trailing slash bằng redirect hoặc wrap request. Ví dụ API mong đợi URL không slash cuối:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

// Fragment tạo filter, không phải một SecurityFilterChain:
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/reports/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
```

Filter cần được **đăng ký đúng thứ tự**, theo tài liệu Spring Framework: sau `ForwardedHeaderFilter` (nếu dùng) và trước security filters/Servlet request-path processing. Ví dụ ở trên **chỉ tạo filter**, chưa tự đăng ký hay quyết định thứ tự. Tự bọc request (`wrapRequest()`) cũng là lựa chọn nhưng cần hiểu cách đường dẫn được thay đổi cho những filter về sau.

HTTP **308 Permanent Redirect** bảo toàn phương thức và body theo ngữ nghĩa HTTP. Với các thao tác thay đổi dữ liệu, nên thiết kế canonical URL rõ ràng và test client behavior; không trông chờ redirect như một lớp authorization hay giả định mọi client sẽ tự động follow redirect.

**Đặc biệt:** xử lý trailing slash không có nghĩa tự cho phép các URL mơ hồ như `%2F`, `//` hoặc `../`. Đây là vấn đề khác, thuộc firewall/path normalization.

## 4. Chữ hoa/chữ thường: /Admin không nhất thiết là /admin

### 4.1. Mặc định của PathPatternParser

`PathPatternParser` sử dụng `caseSensitive = true` theo mặc định. Vì vậy, với parser đó:

```text
Pattern: /api/admin/**

/api/admin/users     -> MATCH
/api/Admin/users     -> NO MATCH
/API/admin/users     -> NO MATCH
/api/ADMIN/users     -> NO MATCH
```

Cần phân biệt **path URL** với **host** trong URL: tên miền thường không phân biệt chữ hoa/thường theo quy tắc DNS, nhưng **path** có thể phân biệt. Không biến một thuộc tính của tên miền thành giả định cho đường dẫn.

### 4.2. Vì sao mismatch ở đây có thể nguy hiểm?

Giả sử controller được tùy chỉnh **không phân biệt hoa/thường** và xử lý cả hai:

```text
/api/admin/users
/api/ADMIN/users
```

Nhưng security matcher chỉ khớp chữ thường, rồi fallback quá rộng:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
)
```

Nếu MVC thực sự route `/api/ADMIN/users` vào controller admin trong khi security matcher không khớp rule quản trị, request có thể chỉ phải qua `authenticated()`. **Đây là tình huống cấu hình gây rủi ro, không phải mặc định Spring MVC nhất định hành xử như vậy.**

Đổi fallback thành `denyAll()` giúp biến những URL không khớp rule đã khai báo thành từ chối, giảm nguy cơ mở quyền khi có đường dẫn biến thể.

### 4.3. Có nên cấu hình case-insensitive toàn ứng dụng?

Thường **không** chỉ để xử lý lỗi URL của một client. Nếu business yêu cầu URL không phân biệt chữ hoa/thường, phải:

- Thống nhất cùng chính sách ở proxy, container, security matchers và MVC handler mappings.
- Test sự tương ứng giữa các route có tên khác nhau chỉ bởi chữ hoa/thường.
- Không tự ý chuyển **ID tài nguyên, token, chữ ký, mã kiểm tra** sang lowercase: các dữ liệu đó có thể phân biệt chữ hoa/thường.
- Giữ rule bảo vệ nhóm admin ngay cả với biến thể hợp lệ.
- Tạo danh sách URL canonical khi có thể, thay vì chấp nhận mọi biến thể không kiểm soát.

`PathPatternParser#setCaseSensitive(false)` có tồn tại trong một số phiên bản, nhưng thay đổi parser không phải "một lệnh sửa mọi nơi" của Spring Security; chỉ cấu hình khi nắm rõ matcher, MVC và hệ quả bảo mật. Với ứng dụng mới, **giữ case-sensitive mặc định** thường dễ audit hơn.

## 5. Percent encoding: ký tự mã hóa không đơn thuần là tên khác

### 5.1. Cơ bản về percent encoding

Trong URI, một số octet có thể được biểu diễn bằng `%HH` (hai chữ số hex). Ví dụ:

| Chuỗi trong request target | Ý nghĩa sau percent decode | Điều cần lưu ý |
| --- | --- | --- |
| `%2F` hoặc `%2f` | `/` | Slash là **dấu phân đoạn path**, nguy cơ đổi cấu trúc |
| `%5C` | `\` | Backslash có thể gây nhầm đường dẫn |
| `%2E` | `.` | Dot segment có thể liên quan path traversal |
| `%25` | `%` | Liên quan nguy cơ **double encoding** |
| `%3B` | `;` | Semicolon/path parameter có thể tác động matching |
| `%61` | `a` | Ký tự chữ thông thường nhưng decoder/matcher phải thống nhất |
| `%00` | NUL | Không nên cho vào path xử lý nghiệp vụ |
| `%20` | Dấu cách | Có thể hợp lệ trong một số URL/resource naming |

Không phải mọi giá trị percent-encoded đều độc hại, và cũng **không thể khẳng định** mọi encoded path đều được Spring Security chấp nhận. Chính sách firewall mặc định chủ yếu chặn các biểu diễn gây mơ hồ/nguy hiểm. Kết quả cuối cùng còn phụ thuộc URL container/proxy chuyển đến Spring.

### 5.2. Encoded slash %2F: cùng byte, khác cấu trúc

Hai request:

```text
/api/admin/users
/api/admin%2Fusers
```

có thể được nhìn thấy khác nhau:

- Nếu có tầng **giải mã** `%2F` thành `/` trước khi so khớp, cấu trúc path có thêm một segment.
- Nếu tầng khác giữ nguyên phần mã hóa khi phân tích segment, `admin%2Fusers` có thể vẫn nằm trong một segment.
- Nếu firewall chặn encoded slash, request sẽ bị từ chối **trước khi đến authorization matcher**.

Sự khác nhau giữa cách nhìn của proxy, Servlet container, security filter và handler mapping có thể gây lỗi **authorization bypass**. Chính vì vậy, `StrictHttpFirewall` mặc định không cho phép encoded slash.

**Không sửa bằng cách tùy tiện gọi `setAllowUrlEncodedSlash(true)`.** Việc mở encoded slash phải có threat model, hiểu toàn bộ stack, test tất cả đường dẫn nhạy cảm và có lý do nghiệp vụ thật sự. Thường giải pháp tốt hơn là chọn một định dạng ID không chứa `/`, hoặc gửi định danh qua một cơ chế khác có contract rõ ràng.

### 5.3. Double encoding

Một chuỗi như:

```text
%252F
```

sau **một lần** percent decode có thể trở thành `%2F`; sau **lần thứ hai** có thể trở thành `/`. Khi proxy decode một lần, service decode thêm lần nữa, hai tầng không còn cùng nhìn một URL. `StrictHttpFirewall` mặc định không cho phép encoded percent `%25` chính vì rủi ro kiểu này.

Không dùng các bước "decode đến khi hết dấu %" hoặc decode thủ công ở nhiều lớp. Đối với route, dựa vào parser/HTTP stack thống nhất và chỉ giải mã dữ liệu ở tầng nhận giá trị đã có contract.

### 5.4. Encoded dot, path traversal và normalized path

Những dạng:

```text
/api/admin/../public
/api/admin/%2E%2E/public
/api/admin//users
/api/admin\users
```

là các tình huống cần kiểm tra kỹ. Dấu chấm `.`/`..`, nhiều slash, backslash hoặc mã hóa các ký tự ấy có thể được proxy/container chuẩn hóa khác nhau. Không nên tự gộp chúng bằng `String.replace(...)` để "chữa" phân quyền.

Một hướng an toàn:

1. Từ chối URL không chuẩn/mơ hồ tại tầng firewall nếu không có nhu cầu rõ.
2. Thiết kế security matcher và MVC handler trên cùng nền parse path.
3. Định nghĩa fallback **deny by default**.
4. Chạy test qua toàn stack được deploy.
5. Vẫn kiểm tra quyền theo object tại service thay vì hoàn toàn tin vào URL.

### 5.5. Semicolon và matrix/path parameters

Semicolon trong path có thể là dấu phân cách path parameters ở một số chuẩn/cơ chế, ví dụ:

```text
/api/admin;mode=preview/users
/api/reports;v=1
```

Các tầng có thể giữ, loại hoặc diễn giải segment parameters khác nhau. `StrictHttpFirewall` thường từ chối semicolon theo mặc định. Nếu ứng dụng có lý do chính đáng để dùng matrix variables, phải thiết kế path parsing và security matching cùng một quan điểm, tránh nới firewall toàn cục chỉ để cho một URL hoạt động.

### 5.6. Không dùng URLDecoder để quyết định route bằng tay

`java.net.URLDecoder` được thiết kế cho **application/x-www-form-urlencoded** và có quy tắc chuyển dấu `+` thành dấu cách. Đó **không phải** cơ chế thay thế cho Servlet/Spring path parser. Đoạn kiểu này không nên dùng để tự đưa ra authorization:

```java
// KHÔNG dùng như chính sách phân quyền HTTP:
String path = java.net.URLDecoder.decode(
        request.getRequestURI(), java.nio.charset.StandardCharsets.UTF_8);
if (path.startsWith("/api/admin")) {
    // ...
}
```

Cách làm này dễ tạo trạng thái "security đã kiểm tra một chuỗi, controller lại xử lý chuỗi khác" và có nguy cơ double decoding. Hãy dùng `RequestMatcher`/`HttpFirewall` được framework hỗ trợ và kiểm thử theo contract.

## 6. StrictHttpFirewall: lớp từ chối request mơ hồ

Spring Security Servlet cung cấp `HttpFirewall`, thường dùng `StrictHttpFirewall` làm implementation mặc định. Nó không thay thế authentication/authorization, nhưng giảm nguy cơ URL được phân tích không thống nhất.

### 6.1. Những nhóm request bị chặn theo mặc định

Theo Javadoc `StrictHttpFirewall` các dòng hiện đại, default bao gồm việc từ chối:

- Slash mã hóa `%2F`, backslash `\`/`%5C`, encoded percent `%25`.
- Semicolon trong path, các dạng ký tự không an toàn như NUL hoặc một số ký tự điều khiển.
- Một số URL không normalized và những cấu trúc bất thường khác.
- HTTP method, header name/value, parameter name/value hoặc hostname không đáp ứng chính sách firewall được cấu hình.

Danh sách trên chỉ nêu **nhóm tiêu biểu**, không phải bản sao đầy đủ mọi quy tắc của mọi phiên bản. Dùng Javadoc trùng phiên bản để biết default và các setter có hiệu lực. Ví dụ `setAllowUrlEncodedSlash`, `setAllowBackSlash`, `setAllowSemicolon`, `setAllowUrlEncodedPercent` tồn tại ở các dòng tương ứng nhưng mặc định chặt chẽ là một lựa chọn bảo mật có lý do.

### 6.2. REJECT, DENY và NOT_FOUND khác nhau

| Tình huống | Cơ chế thường xử lý | Diễn giải |
| --- | --- | --- |
| `/api/admin%2Fusers` bị firewall chặn | `HttpFirewall` / `RequestRejectedException` | **REJECT** vì request target không được chấp nhận |
| `/api/ADMIN/users` không khớp rule admin, fallback `denyAll` | `AuthorizationFilter` | **DENY** vì không có policy cho phép |
| `/api/reports/` đã qua authorization nhưng không có MVC handler | `DispatcherServlet` | **NOT_FOUND** vì route không tồn tại |
| `/api/admin/users` khớp rule admin, user không có role | `AuthorizationFilter` | **DENY** do không đủ quyền |
| `/api/reports` khớp rule đọc và handler, resource ID không thuộc user | Service/domain policy | **DENY** theo quyền trên đối tượng |

**Đừng đồng nhất các kết quả trên với HTTP status cố định**. Request bị `RequestRejectedException` thường được bộ xử lý firewall/host chuyển thành một status cụ thể (ví dụ 400 tùy cấu hình), còn authorization deny có thể trở thành 403 hoặc redirect login; handler không tồn tại có thể 404. Muốn test security đúng, phải kiểm tra **request bị chặn ở lớp nào**, không chỉ thấy status 403/404.

### 6.3. Có nên cấu hình firewall mềm hơn?

Mặc định **không**. Trước khi nới chính sách:

1. Xác định yêu cầu nghiệp vụ thật: ID có cần chứa slash không, hay chỉ do client gửi URL sai?
2. Xác định đường đi proxy → container → firewall → MVC, cách từng tầng decode/normalize.
3. Giới hạn phạm vi thay đổi nếu có thể và kiểm tra không làm mở cả URL admin/private.
4. Bổ sung test raw HTTP với percent encoding chữ hoa/chữ thường, double encoding, dot-segment, semicolon.
5. Phân tích tác động cache, router, WAF, log và bộ phân quyền theo object.
6. Ghi rõ lý do, owner, quy trình review bảo mật và chiến lược rollback.

Bật một setter "allow" chỉ vì test fail hoặc thấy lỗi 400 là phản ứng nguy hiểm: lỗi ban đầu có thể chính là một bảo vệ đang hoạt động đúng.

## 7. PathPatternRequestMatcher và cách tránh lệch MVC/Security

Spring Security có nhiều implementation `RequestMatcher`, trong đó có `PathPatternRequestMatcher`, `MvcRequestMatcher` và các matcher cũ dùng phong cách Ant. Lựa chọn và đường code mà `requestMatchers(String)` đi qua có thể thay đổi theo dòng Spring Security, sự hiện diện của Spring MVC và cấu hình ứng dụng.

### 7.1. Vì sao nên hiểu PathPattern?

Spring MVC dùng parsed `PathPattern`/`RequestPath` để xử lý đường dẫn theo segment. Cách tiếp cận này giúp giải mã/sanitize các segment riêng lẻ, thay vì decode cả chuỗi path rồi vô tình làm thay đổi số phân đoạn.

Với pattern thông dụng:

| Pattern | Ý nghĩa với PathPattern theo mặc định |
| --- | --- |
| `/api/reports` | Đúng route cụ thể, không tự nhận thêm slash cuối |
| `/api/reports/` | Route kết thúc bằng slash |
| `/api/reports/*` | Một phân đoạn con dưới reports |
| `/api/reports/**` | Route reports và các phân đoạn bên dưới theo ngữ nghĩa `**` |
| `/api/reports/{id}` | Một segment làm biến `id` |
| `/api/admin/**` | Nhóm admin và các descendant tương ứng |

Cẩn trọng: `/api/reports/**` là **quy tắc rộng hơn** `/api/reports` và có thể khớp nhiều path. Không dùng `/**` hoặc `/**` sau một tiền tố công khai chỉ để "sửa trailing slash" nếu nó vô tình cấp quyền cho các endpoint con nhạy cảm.

### 7.2. Minh họa cấu hình dùng PathPatternRequestMatcher

Với dòng Spring Security hỗ trợ API tương ứng (ví dụ 6.5+), có thể chọn matcher tường minh:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class RouteSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        return http.authorizeHttpRequests(auth -> auth

            // Rule quản trị trước các route khác.
            .requestMatchers(paths.matcher("/api/admin/**"))
                .hasRole("ADMIN")

            // Chỉ khai báo dạng canonical của route reports.
            .requestMatchers(paths.matcher(HttpMethod.GET, "/api/reports"))
                .hasAuthority("report:read")

            // Những path/method không khai báo bị từ chối.
            .anyRequest().denyAll()
        ).build();
    }
}
```

Đây là **lớp cấu hình dùng trong project Spring Boot/Spring Security**, không thể chạy bằng `javac` độc lập. Nó giả định project có cơ chế authentication và controller phù hợp; không xử lý riêng CSRF/login/CORS. Import `PathPatternRequestMatcher` và factory API cần đối chiếu version thật, nhất là khi dự án còn ở 6.3/6.4 hoặc có nhiều Servlet.

Khi sử dụng parsed matcher, hãy đảm bảo nó tương thích cấu hình `PathPatternParser` và Servlet mapping của MVC. Nếu project dùng tùy chỉnh case sensitivity hay parser options riêng, cần xem cách tạo matcher/builder tương ứng; không mặc định `withDefaults()` tự biết mọi customization.

### 7.3. An toàn của matcher tổng quát

Ví dụ không nên đặt:

```java
.requestMatchers("/api/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

`AuthorizationFilter` xét **matcher đầu tiên khớp**. Request admin đã khớp `/api/**`, rule admin sau không tự được xét thêm. Đây là lỗi thứ tự, độc lập với vấn đề slash/encoding.

Với fallback:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/reports").hasAuthority("report:read")
.anyRequest().denyAll()
```

một biến thể không khớp sẽ bị từ chối ở HTTP authorization (nếu request đến được chain này). Không tự thay `denyAll` bằng `permitAll` để "cho phép mọi biến thể URL".

### 7.4. securityMatcher chọn chain trước requestMatchers

`http.securityMatcher("/api/**")` giới hạn **phạm vi SecurityFilterChain**, khác với `requestMatchers` trong `authorizeHttpRequests`. Nếu chỉ định nghĩa một chain cho `/api/**` mà không có chain khác khớp URL biến thể, request ngoài chain có thể **không được bảo vệ bởi Spring Security**.

Khi có nhiều chain:

- Cung cấp một **fallback SecurityFilterChain** không giới hạn matcher nếu cần bảo vệ toàn ứng dụng.
- Kiểm tra `@Order` và chain được chọn.
- Test các biến thể hoa/thường và slash ở **mức chain selection** lẫn **authorization rule**.
- Không suy rằng `anyRequest().denyAll()` trong chain `/api/**` sẽ chặn một request vốn không khớp chain.

## 8. Xây quy ước URL canonical an toàn

Một bản "quy ước" không chỉ ghi "dùng lowercase, không slash cuối". Nó phải chỉ rõ cách xử lý request không tuân theo quy ước.

### 8.1. Quy ước đề xuất cho API

| Chủ đề | Quy ước ví dụ | Khi client gửi dạng khác |
| --- | --- | --- |
| Static route literals | Viết thường: `/api/reports` | Không tự lowercase tùy ý toàn path |
| Trailing slash | Không dùng slash cuối cho resource endpoint | Chọn rõ reject/404/redirect 308 hoặc alias |
| Encoded slash/backslash | Không chấp nhận trong route path | Giữ default firewall rejection |
| Dot segments/double slash | Không chấp nhận path không normalized | Từ chối thay vì tự sửa nhiều lần |
| Resource IDs | Dùng UUID hoặc ID không chứa separator nguy hiểm | Validate ID ở service; không dùng ID khó đoán thay quyền |
| HTTP method | Định nghĩa GET/POST/PATCH/DELETE đúng use case | Không tự mở method khác |
| Query parameters | Không dùng query để ngụy trang đường dẫn đặc quyền | Phân quyền bằng route và action, validate query riêng |
| Fallback | `anyRequest().denyAll()` | Không có rule nghĩa là không được cấp quyền |

Convention chỉ có ý nghĩa khi **proxy, container, Security và MVC cùng áp dụng**, và các ngoại lệ được test.

### 8.2. Có nên tự lowercase URL trước security?

Không nên dùng một filter tự viết để làm:

```java
// Anti-pattern: đừng dùng như cơ chế quyết định route.
String normalized = request.getRequestURI().toLowerCase();
if (normalized.startsWith("/api/admin")) {
    // ...
}
```

Vì `toLowerCase()` trên toàn bộ URL cũng đổi **ID, token, slug, chữ ký** có thể phân biệt hoa/thường. Ngoài ra, `startsWith("/api/admin")` sẽ nhận cả `/api/administrator`, không phải phân đoạn admin chính xác.

Nếu policy bắt buộc route literal phải lowercase, hãy để router/handler xác định và từ chối biến thể không hợp lệ, giữ nguyên **giá trị biến path**. Với nhận diện prefix, dùng `RequestMatcher` theo segment, không thay bằng chuỗi thô.

### 8.3. Kết hợp quyền theo đối tượng

Dù matcher xử lý URL đúng:

```text
GET /api/documents/d42
```

thì `document:read` vẫn không chứng minh người gọi có quyền đọc `d42`. Ở service cần kiểm tra tenant, owner, ACL, reviewer, trạng thái hoặc logic nghiệp vụ tương ứng. Bảo vệ object-level là **lớp bổ sung** khi URL/client có thể chỉ định ID.

### 8.4. Không tiết lộ URL nhạy cảm trong lỗi

Có thể log reason code nội bộ như `FIREWALL_REJECT_ENCODED_SLASH` hoặc `AUTHZ_DENY_NO_MATCH`, nhưng không cần trả chi tiết policy, owner, tenant hay stack trace cho caller. Hạn chế ghi nguyên request target chứa token/query secret vào log. Khi cần chẩn đoán encoding, có thể log bản đã làm sạch/giới hạn và request ID.

## 9. Java 17+ độc lập: quan sát các biến thể đường dẫn

Chương trình dưới đây mô phỏng **một policy cố ý chặt chẽ**. Nó dùng `java.net.URI` để phân biệt raw path với decoded path và một tập quy tắc từ chối tối giản để minh họa. **Đây không phải implementation của Spring Security hay StrictHttpFirewall**: không giả lập Servlet container, reverse proxy, các setter firewall hoặc sự chọn filter chain. Đặc biệt, quy tắc mô phỏng chỉ chặn **một số** mẫu encoding tiêu biểu, không đủ làm bộ bảo vệ production.

Tạo tệp `PathVariantAuthorizationDemo.java`:

```java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

public class PathVariantAuthorizationDemo {

    private static boolean suspiciousRawPath(String raw) {
        if (raw == null || !raw.startsWith("/")
                || raw.contains("//")
                || raw.contains("\\")
                || raw.contains(";")) {
            return true;
        }

        String lower = raw.toLowerCase(Locale.ROOT);
        return lower.contains("%2f")  // encoded /
                || lower.contains("%5c") // encoded backslash
                || lower.contains("%25") // encoded percent
                || lower.contains("%2e") // encoded dot
                || lower.contains("%3b") // encoded semicolon
                || lower.contains("%00"); // encoded NUL
    }

    private static boolean hasRole(Set<String> authorities, String role) {
        return authorities != null
                && authorities.contains("ROLE_" + role);
    }

    static String decide(String target, Set<String> authorities) {
        URI uri;
        try {
            uri = URI.create(target);
        } catch (IllegalArgumentException e) {
            return "REJECT";
        }

        String raw = uri.getRawPath();
        if (suspiciousRawPath(raw)
                || uri.isAbsolute()
                || uri.getRawAuthority() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            return "REJECT";
        }

        // Chỉ minh họa khái niệm: URI.getPath() giải mã percent.
        // Ứng dụng Spring thực phải để HttpFirewall + RequestMatcher
        // và MVC xử lý path, không tự dùng hàm này để bảo vệ URL.
        String path = uri.getPath();

        // Phân biệt đúng segment, không dùng startsWith("/api/admin").
        if (path.equals("/api/admin")
                || path.startsWith("/api/admin/")) {
            return hasRole(authorities, "ADMIN") ? "ALLOW" : "DENY";
        }

        // Canonical report URL: không chấp nhận slash cuối.
        if (path.equals("/api/reports")) {
            return authorities != null && authorities.contains("report:read")
                    ? "ALLOW" : "DENY";
        }

        return "DENY";
    }

    public static void main(String[] args) {
        Set<String> user = Set.of("ROLE_USER", "report:read");
        Set<String> admin = Set.of("ROLE_ADMIN", "report:read");

        System.out.println("reports-canonical="
                + decide("/api/reports", user));
        System.out.println("reports-trailing-slash="
                + decide("/api/reports/", user));
        System.out.println("reports-uppercase="
                + decide("/API/reports", user));
        System.out.println("admin-ordinary-user="
                + decide("/api/admin/users", user));
        System.out.println("admin-admin-user="
                + decide("/api/admin/users", admin));
        System.out.println("admin-trailing-slash="
                + decide("/api/admin/", user));
        System.out.println("admin-case-variant="
                + decide("/api/ADMIN/users", user));
        System.out.println("admin-encoded-letter-user="
                + decide("/api/%61dmin/users", user));
        System.out.println("admin-encoded-letter-admin="
                + decide("/api/%61dmin/users", admin));
        System.out.println("admin-encoded-slash="
                + decide("/api/admin%2Fusers", admin));
        System.out.println("double-encoded-slash="
                + decide("/api/admin%252Fusers", admin));
        System.out.println("double-slash="
                + decide("/api/admin//users", admin));
        System.out.println("semicolon-path="
                + decide("/api/admin;v=1/users", admin));
        System.out.println("unknown-path="
                + decide("/api/administrator", admin));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac PathVariantAuthorizationDemo.java
java PathVariantAuthorizationDemo
```

Kết quả stdout:

```text
reports-canonical=ALLOW
reports-trailing-slash=DENY
reports-uppercase=DENY
admin-ordinary-user=DENY
admin-admin-user=ALLOW
admin-trailing-slash=DENY
admin-case-variant=DENY
admin-encoded-letter-user=DENY
admin-encoded-letter-admin=ALLOW
admin-encoded-slash=REJECT
double-encoded-slash=REJECT
double-slash=REJECT
semicolon-path=REJECT
unknown-path=DENY
```

**Giải thích:**

1. `/api/reports` được user có `report:read` xem, nhưng `/api/reports/` là route khác theo convention **chỉ một đường dẫn chính thức**.
2. `/api/admin/users` cần `ROLE_ADMIN`, trong khi `ROLE_USER` không đủ.
3. `/api/%61dmin/users` sau decode ký tự chữ `a` được demo phân loại vào nhánh admin, vì vậy **không** mở quyền cho user thường. Trong Spring thực, đường đi còn phụ thuộc firewall/parser/container; bài học không khuyên tự decode path như code demo.
4. `%2F` và `%25` bị mô phỏng trả `REJECT` vì đầu vào có mẫu encoding nguy hiểm. Demo không đại diện toàn bộ quy tắc `StrictHttpFirewall`.
5. `/api/administrator` không phải nhánh con `/api/admin`; kiểm tra segment tách biệt giúp tránh cấp role theo một prefix chuỗi quá rộng.
6. `DENY` nghĩa là matcher/policy mô phỏng không cho phép; `REJECT` nghĩa là bộ lọc đầu vào **tự viết cho bài học** từ chối. Đây không phải mã HTTP.

**Lưu ý về Java URL parsing:** `URI.getRawPath()` giữ lại biểu diễn percent-encoded, còn `URI.getPath()` trả đường dẫn đã decode. Trong server thật, không thay thế `HttpServletRequest`/`HttpFirewall`/`PathPatternRequestMatcher` bằng đoạn mã này. Nếu cần test edge cases, phải gửi request qua đúng proxy, container và Spring stack thật.

## 10. Ma trận kiểm thử RequestMatcher theo biến thể

### 10.1. Trước tiên xác định expected behavior cho từng loại

Giả sử API chủ đích có:

```text
GET /api/reports                 -> report:read
GET /api/admin/users             -> ROLE_ADMIN
All other URL/method variants   -> deny or reject unless explicitly supported
```

Ma trận nên kiểm tra:

| Request target | Điều cần kiểm chứng | Kết quả an toàn theo convention |
| --- | --- | --- |
| `/api/reports` | Canonical path + quyền đọc | Cho phép khi có `report:read` |
| `/api/reports/` | Slash cuối | Từ chối hoặc redirect có chủ đích |
| `/API/reports` | Chữ hoa khác | Không tự tương đương |
| `/api/admin/users` | Endpoint nhạy cảm | Chỉ role ADMIN + policy bổ sung |
| `/api/admin/users/` | Slash cuối trong nhánh admin | Không được hạ yêu cầu role |
| `/api/ADMIN/users` | Biến thể case | Không được rơi vào rule công khai |
| `/api/admin%2Fusers` | Encoded slash | Mặc định firewall chặn trong stack phù hợp |
| `/api/admin%252Fusers` | Double encoding | Không được decode thành đường dẫn được mở quyền |
| `/api/admin%2fusers` | Hex viết thường | Cùng mối nguy encoded slash |
| `/api/admin;v=1/users` | Semicolon/path parameters | Không được bypass rule admin |
| `/api/admin//users` | Double slash | Không được bỏ qua policy admin |
| `/api/admin/../reports` | Dot segments | Không được hạ quyền do normalize khác nhau |
| `/api/%61dmin/users` | Encoded chữ cái | Nếu được route tới admin, vẫn bắt buộc admin |
| `/api/administrator` | Prefix giả | Không được hiểu nhầm là `/api/admin/` |
| `/api/reports?admin=true` | Query string không thay path | Không có quyền admin chỉ vì tham số query |
| `POST /api/reports` | Sai HTTP method | Không dùng quyền GET để cấp POST |

Bảng trên mô tả **mục tiêu an toàn**, không khẳng định status code/chính sách xử lý mặc định của mọi phiên bản. Mục tiêu test là bảo đảm request **không đến handler nhạy cảm khi không đủ quyền**, bất kể bị firewall reject, matcher deny hay handler không khớp.

### 10.2. MockMvc test những đường bình thường

Đây là **fragment** của một test Spring Boot MVC có Spring Security Test, `MockMvc`, controller/fixture và imports tương ứng:

```java
@Test
@WithMockUser(authorities = "report:read")
void canonicalReportPathCanReachHandler() throws Exception {
    mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "report:read")
void trailingSlashDoesNotGainReportAccess() throws Exception {
    mockMvc.perform(get("/api/reports/"))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "USER")
void userCannotReachAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
}
```

Các expected `200`/`403` chỉ đúng **với cấu hình allowlist ở mục 7**, handler thực sự tồn tại/return status phù hợp, matcher không cho alias và không có filter khác tác động. Trong project khác, trailing slash có thể trả 404 hoặc redirect có chủ đích; khi đó viết assertion đúng contract. Đừng nhầm “không khớp controller” với “đã thực thi authorization đầy đủ” chỉ vì response 404.

### 10.3. Kiểm thử encoded path cần chạy qua HTTP thực

`MockMvc` không phải Servlet container/reverse proxy đầy đủ. Một request builder chứa `%2F` có thể không tái hiện đúng việc proxy/container decode, reject hay thay đổi request-target của hệ thống production. Do đó:

1. Test đường bình thường, trailing slash/case bằng MockMvc ở phạm vi framework.
2. Dùng integration test với embedded server thật, và test thêm qua reverse proxy nếu deploy có proxy.
3. Gửi request-target được mã hóa **đúng raw bytes** từ công cụ HTTP phù hợp, tránh để client tự normalize hoặc follow redirect ngoài ý định.
4. Kiểm tra sự khác nhau giữa lớp firewall, matcher và handler; quan sát response không đủ để chứng minh không có bypass.
5. Với request admin, assert **handler nhạy cảm không được gọi** khi thiếu quyền; có thể dùng audit/test spy.
6. Nếu chỉnh firewall hoặc parser, chạy lại toàn bộ ma trận sau mỗi thay đổi.

Ví dụ lệnh curl chỉ để minh họa cách giữ nguyên URL được gửi:

```bash
curl --path-as-is -i "http://localhost:8080/api/admin%2Fusers"
curl --path-as-is -i "http://localhost:8080/api/admin/../reports"
curl --path-as-is -i "http://localhost:8080/api/ADMIN/users"
```

`curl --path-as-is` giúp không tự loại bỏ một số thành phần path trước khi gửi, nhưng **không bỏ qua** proxy/container/firewall ở server. Nếu test gặp redirect, tránh tự động theo để phân biệt response ban đầu và response ở URL đích. Chỉ chạy trong môi trường được phép kiểm thử.

### 10.4. Kiểm tra HTTP chain selection

Nếu app có:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll());
```

một path khác chữ hoa/đường dẫn có encoding có thể không khớp `securityMatcher` theo cùng cách với URL canonical. Kiểm thử cả trường hợp **không chain nào khớp**; cần fallback chain thực sự bảo vệ các request còn lại. Không chỉ test `authorizeHttpRequests` của chain API rồi kết luận ứng dụng an toàn.

## 11. Chẩn đoán lỗi theo triệu chứng

| Hiện tượng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| `/api/reports` được, `/api/reports/` trả 404 | MVC không auto-match trailing slash | Xem `@RequestMapping`, parser, redirect policy |
| Slash cuối trả 403 thay vì 404 | Matcher không khớp, fallback deny | Kiểm tra rule đầu tiên được xét và chain |
| `/API/reports` khác kết quả `/api/reports` | Path matching case-sensitive | Kiểm tra parser ở MVC/Security |
| Biến thể uppercase vào được admin | MVC/security mismatch + fallback rộng | Kiểm tra chain/rule chồng lấn |
| `%2F` bị reject trước controller | StrictHttpFirewall hoặc container | Xem exception/log đã làm sạch; không mở firewall vội |
| `%252F` tạo kết quả khó đoán | Double encoding qua nhiều tầng | Kiểm tra proxy decode, container, app code |
| `/api/admin//users` hành xử khác | URL normalization hoặc path parser | Test raw request qua deployed stack |
| `/api/administrator` bị đòi role admin | `startsWith("/api/admin")` không phân biệt segment | Dùng `RequestMatcher` đúng |
| Request bị 403 trước khi permission được đánh giá | CSRF, firewall hoặc chain khác | Tách từng filter/policy |
| Path chính xác nhưng handler vẫn chạy ngoài Security | Không SecurityFilterChain phù hợp | Kiểm tra `securityMatcher`/`@Order` và fallback |
| Dữ liệu tenant khác vẫn bị lộ dù matcher đúng | Thiếu object authorization | Bổ sung policy ở service/repository |
| MockMvc pass nhưng production khác | Proxy/container decode/normalize khác | Integration test qua cùng HTTP stack |

**Cách đọc log:** cần phân biệt request bị `RequestRejectedException`, matcher không khớp, bị `AuthorizationDenied`, thiếu authentication, hay không có MVC handler. Không in raw request chứa token/PII vào log. Nếu cần xác minh, bật logging có kiểm soát trong môi trường test thay vì thay đổi rule toàn cục.

## 12. Những phản ứng sửa lỗi nguy hiểm

1. **Bật toàn bộ optional trailing slash matching** chỉ vì một endpoint cần alias: có thể làm thay đổi quy tắc cả vùng ứng dụng và gây lệch MVC/Security.
2. **Đưa `/**` lên đầu với `permitAll`** để “cho nhiều URL chạy được”: mở nhầm endpoint bảo mật.
3. **Dùng `.toLowerCase()` trên toàn URL**, bao gồm ID/slug/token: đổi dữ liệu, có thể gây nhầm người dùng/tài nguyên.
4. **Cho phép `%2F`, `%25`, `%5C`** ở `StrictHttpFirewall` chỉ để qua test: nới biên an toàn trước khi hiểu đường decode.
5. **Decode path nhiều lần** bằng `URLDecoder` hoặc custom regex: có thể tạo khác biệt giữa policy và controller.
6. **So sánh prefix thô với `startsWith("/admin")`**: nhận cả `/administrator` và các trường hợp không phải segment.
7. **Cho rằng 404 luôn an toàn**: có thể là response từ handler hoặc exception đã để lộ dữ liệu bên trong trước khi trả lỗi; cần test side effects.
8. **Cho rằng 403 luôn xuất phát từ hasRole/hasAuthority**: có thể do CSRF hoặc filter khác; tìm đúng lớp chặn.
9. **Cho rằng MockMvc luôn tái hiện proxy/Servlet container**: nó phù hợp nhiều kiểm thử framework, nhưng không thay thế raw HTTP end-to-end với encoding.
10. **Chỉ bảo vệ một SecurityFilterChain**, không có fallback: URL biến thể có thể rơi ngoài phạm vi chain.
11. **Tin vào đường dẫn khó đoán** thay vì kiểm tra quyền object: vẫn có BOLA/IDOR.
12. **Phụ thuộc vào redirect như kiểm soát truy cập**: redirect chỉ là chính sách URL canonical, authorization vẫn phải chạy trên request đích.

## 13. Quy trình triển khai chuẩn cho nhóm route nhạy cảm

### Bước 1 — Liệt kê URL và các biến thể thực sự được phép

Viết hợp đồng cho mỗi HTTP method + path:

```text
GET /api/reports             -> authenticated + report:read
GET /api/admin/users         -> ROLE_ADMIN
GET /api/reports/            -> reject / redirect / explicit alias?
GET /API/reports             -> reject or explicitly supported?
Encoded slash in URI path    -> reject by default
All other path/methods       -> deny by default
```

Mọi dấu `?` trong ví dụ là quyết định cần chốt trước khi deploy. Không để framework/proxy ngầm quyết định chính sách thay sản phẩm.

### Bước 2 — Ghi rõ parser và chiến lược matcher

Xác định Spring Framework/Security version, Servlet container, có Spring MVC hay không, có custom `PathPatternParser`/`MvcRequestMatcher`/`AntPathRequestMatcher` hay không, và có bao nhiêu `SecurityFilterChain`. Không suy ra implementation chỉ vì gọi `requestMatchers("...")` trong source code.

### Bước 3 — Chọn canonicalization một lần tại ranh giới phù hợp

Với trailing slash, quyết định reject/redirect/alias rõ ràng; nếu dùng `UrlHandlerFilter`, đăng ký đúng thứ tự. Với encoded separator/path traversal, giữ firewall chặt chẽ; không tự decode trong nhiều lớp.

### Bước 4 — Bảo vệ route nhạy cảm trước rule rộng

Ví dụ cấu trúc:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("report:read")
.anyRequest().denyAll()
```

Nếu có nhiều filter chain, cả chain selection phải được test với URL biến thể.

### Bước 5 — Đồng bộ controller mapping

Nếu chỉ một URL canonical được hỗ trợ, controller cũng nên chỉ map URL đó; nếu cần alias, bổ sung có chủ đích. Đặc biệt rà soát trailing slash và case sensitivity sau upgrade Spring Framework 5.x → 6.x/7.x.

### Bước 6 — Viết test theo cả tầng và cả chuỗi request

Unit test matcher/policy → MockMvc integration → embedded server → proxy end-to-end, bao gồm encoding và đường dẫn nhạy cảm. Kết quả mong đợi được mô tả theo **cho phép/không cho phép handler nhạy cảm**, cùng lý do tầng nào chặn.

### Bước 7 — Review thay đổi cấu hình liên quan URL

Một thay đổi ở proxy rewrite, firewall setter, `UrlHandlerFilter`, MVC path parser hoặc `SecurityFilterChain` đều có thể ảnh hưởng authorization mà code business không đổi. Hãy coi đây là thay đổi bảo mật và chạy lại test ma trận.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Với `PathPatternParser` mặc định trong Spring Framework 6.x, `/api/reports` có tự khớp `/api/reports/` không?

**Đáp án:** Không. Default `matchOptionalTrailingSeparator=false`. Nếu muốn hỗ trợ cả hai, phải quyết định alias/redirect hoặc cấu hình có chủ đích và test.

**Câu 2.** Pattern `/api/admin/**` mặc định có tự khớp `/API/ADMIN/users` không?

**Đáp án:** Không với `PathPatternParser` case-sensitive mặc định. Nhưng kết quả end-to-end phụ thuộc matcher/handler thực; quan trọng là fallback không được mở quyền cho URL biến thể.

**Câu 3.** `%2F` và `%2f` có cùng ý nghĩa percent encoding không?

**Đáp án:** Có, hex trong biểu diễn percent không phân biệt hoa/thường; cả hai đều biểu diễn octet slash. `StrictHttpFirewall` mặc định không cho phép encoded slash ở Servlet stack tương ứng.

**Câu 4.** Tại sao `/api/admin%2Fusers` là tình huống nguy hiểm khi các tầng decode khác nhau?

**Đáp án:** Một tầng có thể xem `admin%2Fusers` là một segment, tầng khác xem sau decode thành `admin/users` hai segment. Nếu policy và handler không cùng cách phân tích, quyền có thể bị áp dụng sai.

**Câu 5.** Có nên bật `setAllowUrlEncodedSlash(true)` chỉ để client gọi API chứa slash trong ID?

**Đáp án:** Không. Cần đánh giá rủi ro xuyên suốt proxy/container/firewall/router. Thường nên dùng định dạng ID khác hoặc thiết kế API khác, không mở global firewall mà chưa review.

**Câu 6.** Vì sao `/api/administrator` không nên được match bằng kiểm tra thô `startsWith("/api/admin")`?

**Đáp án:** Vì đó là một tiền tố chuỗi chứ không phải phân đoạn path; nó nhận nhầm `administrator`. Dùng segment-aware RequestMatcher.

**Câu 7.** Security rule cho `/api/reports` trả DENY với slash cuối nhưng controller vẫn có alias. Có nên đặt `/api/**.permitAll()` để sửa không?

**Đáp án:** Không. Cần khai báo alias cùng permission, hoặc redirect chuẩn, hoặc để alias không được hỗ trợ. Mở wildcard public có thể cấp quyền sai cho endpoint khác.

**Câu 8.** Một HTTP request mang `%252F`; vì sao phải nghĩ về double decoding?

**Đáp án:** Một lần decode có thể tạo `%2F` và lần tiếp theo tạo `/`. Nếu các tầng decode khác số lần, cấu trúc path dùng cho policy và handler có thể khác nhau.

**Câu 9.** MockMvc test `%2F` pass thì production qua reverse proxy chắc chắn an toàn?

**Đáp án:** Không. MockMvc không mô phỏng đầy đủ raw request-target/proxy/Servlet container. Cần integration test với stack được triển khai, nhất là sau khi đổi firewall/parser/rewrite.

**Câu 10.** Lỗi 404 có chứng minh request đã được phân quyền chính xác không?

**Đáp án:** Không. Có thể không có handler sau khi qua security, hoặc request bị biến đổi ở tầng khác. Test phải xác nhận request thiếu quyền không đến được hành động nhạy cảm và object policy vẫn hoạt động.

**Kết luận:** *Một URL chỉ an toàn khi mọi tầng hiểu nó nhất quán.* Với `RequestMatcher`, hãy xác định rõ trailing slash, case sensitivity và percent encoding; giữ `StrictHttpFirewall` chặt chẽ, không decode path tùy tiện, dùng fallback `denyAll`, quản lý `SecurityFilterChain` có phạm vi đúng và kiểm thử cả raw HTTP stack. Đường dẫn chính xác là cần thiết, nhưng không thay thế quyền trên đối tượng.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Authorize HttpServletRequests và request matching: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security — Java configuration; securityMatcher versus requestMatchers: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — StrictHttpFirewall API (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html
- Spring Framework 6.2 — PathPatternParser API, trailing slash và case-sensitive defaults: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html
- Spring Framework — Mapping Requests, PathPattern syntax: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Servlet path matching, segment decoding và URL parsing: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html
- Spring Framework — UrlHandlerFilter và filter ordering: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework 6.2 — UrlHandlerFilter API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/UrlHandlerFilter.html
- Spring Security — MockMvc integration test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
