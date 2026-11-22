# Kiểm soát dấu gạch chéo cuối đường dẫn trong Spring MVC và khác biệt giữa các phiên bản

## 1. Vấn đề cần hiểu

Dấu gạch chéo cuối đường dẫn (*trailing slash*) là ký tự `/` ở cuối phần **path** của URL, chẳng hạn:

- `GET /api/users`: không có dấu `/` cuối.
- `GET /api/users/`: có dấu `/` cuối.
- `GET /api/users?page=1` và `GET /api/users/?page=1`: vẫn khác nhau ở **path**; query string `?page=1` không quyết định trailing slash.
- Đường dẫn gốc `/` là trường hợp riêng, không được tùy tiện rút thành chuỗi rỗng.

Với Spring MVC, câu hỏi là một phương thức controller khai báo `@GetMapping("/api/users")` có nhận cả hai URL đầu tiên không. Câu trả lời **phụ thuộc vào phiên bản Spring Framework, cấu hình path matching, các mapping được khai báo và bộ lọc hoặc reverse proxy đặt trước ứng dụng**. Không nên xem hai URL này đương nhiên là tương đương.

Phạm vi bài học: **Spring MVC trên Servlet stack**, gồm ứng dụng Spring Framework thuần và ứng dụng dùng Spring Boot. Spring WebFlux, Spring Cloud Gateway, cấu hình proxy hoặc Servlet container có những cơ chế riêng; không tự suy diễn rằng chúng sử dụng cùng API với MVC.

## 2. Cơ chế định tuyến và nguyên nhân khác biệt

Khi một HTTP request đi vào ứng dụng MVC, proxy và các Servlet filter (nếu có) xử lý trước, sau đó `DispatcherServlet` tìm handler phù hợp, thường thông qua `RequestMappingHandlerMapping`. Spring so path đã nhận với các mẫu trong `@RequestMapping`, `@GetMapping`, `@PostMapping`... và đồng thời xét HTTP method, `params`, `headers`, `consumes` và `produces` khi được khai báo.

Xét controller:

```java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping("/api/users")
    public String listUsers() {
        return "users";
    }
}
```

Đây là một lớp controller trong ứng dụng đã có Spring MVC và bộ khởi động web phù hợp, không phải tệp Java độc lập chạy bằng `java UserController`.

- `GET /api/users` khớp mapping và thông thường trả HTTP 200, body `users`.
- Với mặc định từ **Spring Framework 6.0 trở đi**, `GET /api/users/` **không khớp** mapping trên. Nếu không có mapping/filter/proxy nào khác xử lý, kết quả thường là **404 Not Found**.
- Nếu có Spring Security, reverse proxy, filter chuyển hướng hoặc route khác, trạng thái HTTP quan sát được có thể khác (ví dụ 301/308, 401/403). Vì vậy phải kiểm tra toàn bộ đường đi của request trước khi kết luận.

`PathPatternParser` phân tích mẫu URL thành `PathPattern` và so với path của request. `AntPathMatcher` là chiến lược so khớp chuỗi truyền thống. **Lựa chọn parser và quy tắc chấp nhận slash cuối là hai vấn đề khác nhau**; chỉ đổi sang `AntPathMatcher` không phải giải pháp đáng tin để khôi phục hành vi cũ.

## 3. Bảng mốc phiên bản cần nhớ

| Nền tảng | Mặc định đối với `@GetMapping("/api/users")` khi gọi `/api/users/` | Ghi chú |
| --- | --- | --- |
| Spring Framework 5.x, gồm 5.3 (thường đi với Boot 2.x) | Thường **khớp** nhờ optional trailing-slash match mặc định bật | Kiểm tra cấu hình tùy chỉnh; Boot 2.6 chuyển chiến lược MVC mặc định sang `PathPatternParser` nhưng điều này không đồng nghĩa tắt trailing-slash match. |
| Spring Framework 6.0–6.1 (thường Boot 3.0–3.3) | Mặc định **không khớp** | Từ 6.0, mặc định trailing-slash match đổi từ `true` sang `false` và các API bật lại tính năng được đánh dấu deprecated. |
| Spring Framework 6.2 (thường Boot 3.4–3.5) | Mặc định **không khớp** | Có `UrlHandlerFilter` (giới thiệu từ Framework 6.2) để redirect hoặc wrap request một cách tường minh. API cũ vẫn deprecated. |
| Spring Framework 7.0+ (dòng Boot 4.x) | Mặc định **không khớp** | Hỗ trợ optional trailing-slash match trong path parser **đã bị loại bỏ**; dùng mapping tường minh, redirect/rewrite hoặc `UrlHandlerFilter`. |

Đây là các **mốc phiên bản Framework**, còn Spring Boot quản lý phiên bản Framework thông qua dependency management. Khi cần xác nhận chính xác một dự án, kiểm tra phiên bản Framework thực tế trong dependency tree, không suy từ mã nguồn hoặc một thuộc tính Boot đơn lẻ.

Một số khác biệt dễ nhầm:

1. Spring Framework 5.3 giới thiệu khả năng chọn `PathPatternParser`, trong khi trước đó MVC thường dựa vào `AntPathMatcher`.
2. Spring Boot 2.6 đổi mặc định chiến lược khớp URL sang `PathPatternParser`. Điều này khác với mốc **Spring Framework 6.0 tắt trailing slash match theo mặc định**.
3. `PathMatchConfigurer#setUseTrailingSlashMatch(true)` và `PathPatternParser#setMatchOptionalTrailingSeparator(true)` bị deprecated từ Framework 6.0; **không đưa các API đó vào cấu hình mới** vì đường nâng cấp 7.0 không còn hỗ trợ.
4. Không có một thuộc tính `application.yml` phổ quát tên `spring.mvc.trailing-slash` bảo đảm bật lại cơ chế này ở mọi phiên bản. `spring.mvc.pathmatch.matching-strategy` điều khiển **chiến lược matching** trong các bản Boot hỗ trợ thuộc tính đó, không phải công tắc chuẩn để hợp nhất hai URL.

## 4. Chọn chính sách URL theo mục tiêu của API

### Phương án A — Chỉ có một URL chuẩn (khuyến nghị mặc định)

Thiết kế và công bố `/api/users` là endpoint chuẩn. Giữ một mapping:

```java
@GetMapping("/api/users")
public String listUsers() {
    return "users";
}
```

Client phải dùng URL đúng như tài liệu. Dấu slash cuối không hợp lệ sẽ không khớp mapping theo mặc định của Framework 6+. Ưu điểm là có một đường dẫn thống nhất trong OpenAPI, cache, log, chữ ký request và các rule phân quyền; đánh đổi là các client gửi `/api/users/` cần được cập nhật hoặc nhận lỗi.

**Không được tự ý loại bỏ slash ở cuối tất cả URL** nếu ứng dụng có path đặc thù, URL đã ký, reverse proxy đang rewrite, hoặc hợp đồng API yêu cầu dạng có slash.

### Phương án B — Cho phép cả hai dạng tại một endpoint cụ thể

Khai báo chính xác hai mẫu cần hỗ trợ:

```java
package demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping({"/api/users", "/api/users/"})
    public String listUsers() {
        return "users";
    }
}
```

Với controller trên, `GET /api/users` **và** `GET /api/users/` cùng trả `200 OK` với body `users` trong một ứng dụng không có filter/security chặn chúng. Khác với redirect, hai yêu cầu được xử lý trực tiếp, không có round trip thứ hai.

Dùng phương án này khi chỉ một số endpoint phải duy trì tương thích. Tránh khai báo trùng đường dẫn trong nhiều controller gây ambiguity, tránh nhân đôi toàn bộ API nếu không có yêu cầu rõ ràng. Nếu endpoint nhận nhiều HTTP method, khai báo biến thể cho đúng method tương ứng, thay vì thêm `@RequestMapping` không giới hạn method.

### Phương án C — Chuyển hướng sang URL chuẩn tại proxy hoặc filter

Nếu mục tiêu là **canonical URL**, hãy chuyển từ `/api/users/` sang `/api/users`. Ví dụ một reverse proxy được phép xử lý chính sách slash cuối có thể trả 308 và header `Location: /api/users`. Sau đó client gửi request mới đến URL chuẩn.

- **308 Permanent Redirect**: chuyển hướng lâu dài, giữ HTTP method và request body theo chuẩn; một số client/cache có thể ghi nhớ redirect.
- **307 Temporary Redirect**: chuyển hướng tạm thời, vẫn bảo toàn method và body.
- **301/302**: có lịch sử hành vi client thay đổi method (đặc biệt POST thành GET); không mặc định dùng cho API ghi dữ liệu.
- **Redirect khác với rewrite/wrap**: redirect phát phản hồi 3xx để client gọi lại; rewrite/wrap làm ứng dụng tiếp tục xử lý ngay trong cùng request. Những khác biệt này ảnh hưởng quan sát HTTP, logging, cache và các client không tự theo redirect.

Chọn 308 khi chính sách URL đã ổn định và client hỗ trợ; chọn 307 trong giai đoạn chuyển đổi nếu cần tránh hiệu ứng cache dài hạn. Kiểm tra kỹ các request POST/PUT/PATCH, payload lớn, xác thực và URL ký số.

## 5. `UrlHandlerFilter` từ Spring Framework 6.2

Với Spring MVC Servlet trên Framework **6.2+**, `org.springframework.web.filter.UrlHandlerFilter` cho phép cấu hình từng nhóm path. Ví dụ dưới đây dùng Spring Boot với Spring MVC, yêu cầu phụ thuộc Spring Framework 6.2+:

```java
package demo.web;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

@Configuration
public class TrailingSlashConfig {

    @Bean
    FilterRegistrationBean<UrlHandlerFilter> trailingSlashFilter() {
        UrlHandlerFilter filter = UrlHandlerFilter
                .trailingSlashHandler("/api/**")
                .redirect(HttpStatus.PERMANENT_REDIRECT)
                .build();

        FilterRegistrationBean<UrlHandlerFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }
}
```

Với mapping `@GetMapping("/api/users")` ở phần 2, trong điều kiện chuỗi filter đúng thứ tự:

```text
GET /api/users   -> 200 OK, body: users
GET /api/users/  -> 308 Permanent Redirect
                    Location: /api/users
GET /api/users   -> 200 OK, body: users  (nếu client theo redirect)
```

Đoạn trên minh họa **cấu hình filter và trạng thái mong đợi**, không phải stdout từ một chương trình Java độc lập. Mốc `Ordered.HIGHEST_PRECEDENCE + 20` chỉ là ví dụ về độ ưu tiên; cần xác minh thứ tự filter thực tế của ứng dụng. Tài liệu Spring yêu cầu `UrlHandlerFilter` chạy **sau `ForwardedHeaderFilter`, trước `ServletRequestPathFilter` (nếu có) và trước các security filter**. Nếu hệ thống có reverse proxy hoặc Spring Security, phải xác nhận rằng thứ tự đó thật sự được đáp ứng; không xem một hằng số order là bảo đảm cho mọi cấu hình.

Nếu cần giữ nguyên một request và chuyển path nội bộ, API Servlet dùng `wrapRequest()`:

```java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/**")
        .wrapRequest()
        .build();
```

Khi đó client gửi `/api/users/` có thể nhận trực tiếp phản hồi từ handler của `/api/users`, không có 3xx. Đổi lại, ứng dụng cần kiểm tra xem log, filter khác và security matcher có cùng nhìn thấy path đã chuẩn hóa không. **Không đăng ký đồng thời nhiều filter có logic slash chồng chéo**, vì có thể sinh vòng redirect hoặc hành vi khó đoán.

Lưu ý giới hạn của filter:

- Quy tắc `"/api/**"` chỉ tác động đến nhóm path đã cấu hình; không có chủ ý đổi mọi URL của hệ thống.
- Root path `/` được loại trừ khỏi xử lý trailing slash.
- Khi normalization áp dụng, một type-level `@RequestMapping("/")` có thể tạo ra slash không mong muốn; với controller thực sự ở root, tài liệu Spring hướng dẫn dùng `@RequestMapping` không khai báo path khi phù hợp.
- `UrlHandlerFilter` chỉ có từ 6.2; ở Framework 6.0–6.1 chọn mapping tường minh hoặc redirect/rewrite tại hạ tầng hay filter tự viết được kiểm soát. Không sao chép class này vào dự án 6.0 rồi kỳ vọng biên dịch.

## 6. Cấu hình cũ trong quá trình nâng cấp: đọc được nhưng không xây mới

Trong một số dự án Spring Framework 6.x, có thể gặp cấu hình di trú:

```java
// CHỈ MINH HỌA CẤU HÌNH CŨ CỦA FRAMEWORK 6.x.
// Deprecated từ 6.0; không sử dụng cho triển khai mới hoặc Framework 7.
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    configurer.setUseTrailingSlashMatch(true);
}
```

Hoặc mã trực tiếp với `PathPatternParser#setMatchOptionalTrailingSeparator(true)`. Cả hai cách dựa trên cơ chế matching được đánh dấu deprecated từ 6.0 và bị loại bỏ khi chuyển lên 7.0. Nếu vẫn phải duy trì dự án 6.x, cần xác định chính xác parser/handler mapping đang hoạt động và thử cả hai biến thể URL; không dùng mẹo này như chiến lược nâng cấp dài hạn.

**Không nhầm với** `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` trong các bản Boot cũ hỗ trợ: cài đặt đó chọn engine xử lý mẫu, không tự cho phép trailing slash trên Framework 6+; ở Framework 7 các API matching kiểu chuỗi cũng nằm trong xu hướng loại bỏ/deprecated.

## 7. Bảo mật và nhất quán giữa MVC với Spring Security

Một lý do Spring bỏ mặc định nới lỏng là tránh **bất đồng về diễn giải path** giữa tầng phân quyền và tầng định tuyến. Tưởng tượng một rule bảo vệ `/resources` khác quyền với `/resources/**`. Nếu security matcher đánh giá `/resources/` theo một quy tắc, còn MVC cho phép nó đi vào handler của `/resources`, người dùng có thể nhận quyền khác dự kiến. Đây là ví dụ rủi ro thiết kế, **không khẳng định mọi cấu hình Spring Security đều bị bypass**.

Nguyên tắc triển khai:

1. Áp dụng normalization **trước** bước phân quyền nếu chọn filter/rewrite, để Security và MVC nhìn cùng một path; kiểm tra bằng integration test thật.
2. Rà soát cả path có và không có slash ở API công khai, endpoint admin, health/actuator và static resources; không giả định chúng cùng chính sách.
3. Đảm bảo proxy, gateway, CDN, Spring Security và controller có chung quy ước canonical URL; xét cả chữ hoa/chữ thường, mã hóa `%2F` và slash lặp khi phù hợp.
4. Với redirect, không đánh rơi query string, phương thức hoặc body; kiểm tra `Location` và host/scheme khi ứng dụng đặt sau trusted proxy. Không tin `X-Forwarded-*` từ nguồn không tin cậy.
5. Đối với request không có handler, các security filter có thể trả 401/403 trước khi MVC có cơ hội trả 404; chỉ nhìn status code chưa đủ để xác định quy tắc path matching.

## 8. Kiểm thử hồi quy

Để kiểm tra **chính hành vi path mapping mặc định** độc lập với web server, reverse proxy và filter tùy chỉnh, dùng `MockMvc` standalone. Ví dụ JUnit Jupiter với `spring-test` và các phụ thuộc kiểm thử Spring tương thích phiên bản:

```java
package demo.web;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class UserControllerTest {

    @Test
    void spring6AndLaterDefaultRequiresExactPath() throws Exception {
        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(new UserController())
                .build();

        mvc.perform(get("/api/users"))
                .andExpect(status().isOk())
                .andExpect(content().string("users"));

        mvc.perform(get("/api/users/"))
                .andExpect(status().isNotFound());
    }
}
```

Bài test này dùng **controller một mapping** ở phần 2, và mong đợi mặc định Framework **6.0+**. Trên dự án 5.x (mặc định cũ), test thứ hai có thể nhận 200; khi dùng controller khai báo **hai mapping tường minh** ở phần 4, phải đổi kỳ vọng thứ hai thành 200. Vì là standalone, bài test này **không chứng minh thứ tự servlet filter, Spring Security, proxy hay `UrlHandlerFilter` ngoài đời thực**.

Sau khi thêm filter hoặc cấu hình Security, cần integration test với web context phù hợp, có đủ filter chain. Ma trận tối thiểu:

| Request | Mặc định 6+ với một mapping | Hai mapping tường minh | Filter redirect 308 |
| --- | --- | --- | --- |
| `GET /api/users` | 200 | 200 | 200 |
| `GET /api/users/` | 404 nếu không có handler khác | 200 | 308, `Location: /api/users` |
| `GET /api/users/?page=1` | 404 nếu không có handler khác | 200 | 308, kiểm tra query được bảo toàn |
| `POST /api/users/` | Tùy mapping POST thực tế (có thể 404/405) | Tùy mapping POST thực tế | Nếu áp dụng quy tắc, kiểm tra 307/308 bảo toàn method/body |
| `GET /` | Tùy root mapping | Tùy root mapping | Không bị filter rút slash của root |

Các giá trị 200 và 404 ở bảng là **tình huống minh họa** cho controller GET trả `users`, không phải cam kết với mọi ứng dụng. Kiểm tra redirect với **client không tự theo redirect** để thấy phản hồi 308 ban đầu; sau đó có thể kiểm tra riêng client có theo redirect.

Lệnh quan sát nhanh khi ứng dụng chạy ở cổng 8080:

```bash
curl -i --max-redirs 0 http://localhost:8080/api/users
curl -i --max-redirs 0 http://localhost:8080/api/users/
curl -i --max-redirs 0 'http://localhost:8080/api/users/?page=1'
```

Đầu ra cần xem là dòng HTTP status và header `Location` (nếu có), không phải chỉ nội dung body. Không dùng `curl -L` ở bước đầu vì nó sẽ tự theo redirect và làm mất dấu vết của phản hồi 3xx.

## 9. Chẩn đoán khi sau nâng cấp gặp 404 hoặc redirect lạ

Thực hiện theo trình tự sau:

1. **Xác định phiên bản thật**: xem Spring Framework, Spring Boot và `spring-webmvc` trong dependency tree; tìm mốc 5.3 → 6.x hoặc 6.x → 7.x.
2. **Xem khai báo handler**: kiểm tra `@RequestMapping` ở class và method, prefix của servlet, path của context và tên URL thực tế; lưu ý `@RequestMapping("/")` tại class level.
3. **Kiểm tra request thực tế**: ghi HTTP method, raw path, query string và header `Location`; so `/api/users` với `/api/users/` trước và sau reverse proxy.
4. **Rà soát cấu hình matching**: xác minh `PathPatternParser`, cấu hình `WebMvcConfigurer`, những API deprecated còn sót, và rule rewrite từ proxy/filter.
5. **Quan sát filter/security**: thứ tự `ForwardedHeaderFilter` → normalization → Spring Security → MVC phải được kiểm chứng, tránh chuyển hướng vòng lặp, sai host/scheme hoặc security rule lệch path.
6. **Khóa hành vi bằng test**: kiểm thử cả hai đường dẫn, tất cả HTTP method được hỗ trợ, query string, body, redirect, auth và client thực tế trước khi phát hành.

Không đánh đồng: **404** thường là không tìm được handler; **405** là đường dẫn có handler nhưng HTTP method không phù hợp; **308** là chuyển hướng; **401/403** thường đến từ lớp bảo mật. Các thành phần và cấu hình có thể thay đổi đường đi nên cần dùng log/filter chain để xác minh nguồn trả mã.

## 10. Bài tập tự kiểm tra

1. Dự án nâng từ Boot 2.7 lên Boot 3.2; `GET /catalog` hoạt động nhưng `GET /catalog/` trả 404. Hãy giải thích mốc thay đổi từ Framework 5.3 sang 6.x, rồi chọn giữa chuẩn hóa URL và khai báo mapping kép.
2. API `POST /orders/` phải được chuyển sang `POST /orders` mà giữ payload JSON. Hãy lý giải vì sao 307/308 phù hợp hơn việc mặc định dùng 301/302; kiểm tra client có hỗ trợ redirect không.
3. Với Framework 6.2+, hãy áp dụng `UrlHandlerFilter` cho `/api/**` và viết integration test chứng minh `/api/users/` redirect 308, query string giữ nguyên, filter chạy trước Security.
4. Trước khi nâng lên Framework 7, tìm và loại bỏ việc phụ thuộc vào `setUseTrailingSlashMatch` và `setMatchOptionalTrailingSeparator`, thay bằng chiến lược URL tường minh.

## Tài liệu chính thức

- [Spring Framework 6.x: hướng dẫn nâng cấp — thay đổi trailing slash match](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x).
- [Spring Framework 7.x: Servlet filters, mục URL Handler](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Javadoc `UrlHandlerFilter` trong Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/UrlHandlerFilter.html).
- [Javadoc `PathPatternParser` trong Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html).
- [Spring Framework 7.0 Release Notes — các API path matching đã bị loại bỏ](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes).
- [Spring Boot 2.7: cấu hình MVC path matching](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/web.html).
