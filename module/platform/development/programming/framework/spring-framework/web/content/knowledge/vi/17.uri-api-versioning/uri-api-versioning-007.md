# Hỗ trợ API versioning từ Spring 7: phân giải phiên bản, ánh xạ và thông báo ngừng hỗ trợ

> **Phạm vi:** Spring Framework **7.x** (Spring Web MVC trên Servlet stack) và Spring Boot **4.x**, Java 17+; phân giải API version từ HTTP request, phân biệt phiên bản được hỗ trợ và phiên bản được ánh xạ, quy tắc chọn handler với `@RequestMapping(version = ...)`, cùng chính sách `Deprecation` / `Sunset` / `Link` khi kết thúc một API contract. Tính năng API versioning tích hợp sẵn này được thêm vào Spring Framework 7, **không phải** API `WebMvcConfigurer` của Spring Framework 6.x / Spring Boot 3.x. Các ví dụ Java theo Spring Framework 7.0.x, Boot 4.0.x; nếu đang dùng Spring 6.x cần dùng cách ánh xạ phiên bản riêng hoặc nâng cấp stack một cách có kế hoạch.

## 1. Vì sao cần version API?

Một API được client sử dụng lâu dài sẽ phải thay đổi. Ví dụ ở API `GET /api/books`:

- Phiên bản 1 trả `{"title":"Spring"}`.
- Phiên bản 2 trả thêm mã sách, tên tác giả hoặc đổi tên field như `{"id":1,"name":"Spring"}`.
- Mobile app cũ vẫn mong field `title`; nếu server đột ngột trả shape khác mà không có lộ trình, app cũ có thể không hoạt động.
- Backend muốn thông báo v1 đã lỗi thời, cho client thời gian chuyển v2 rồi mới cân nhắc ngừng hỗ trợ.

**API versioning** cho phép server có nhiều hợp đồng giao tiếp đồng thời và chọn response/behavior theo phiên bản client yêu cầu.

```text
Client v1 --API-Version: 1.0--\
                              \
                               DispatcherServlet
                              /         |
Client v2 --API-Version: 2.0--/          v
                             ApiVersionResolver
                                      |
                             ApiVersionParser
                                      |
                           Validate supported version
                                      |
                              Handler mapping
                             /               \
                      version="1.0"      version="2.0+"
                          |                  |
                      V1 response          V2 response
                          |
                 Deprecation/Sunset hints
```

**Version API không phải version thư viện Maven:** `Spring Framework 7.0.9` là phiên bản nền tảng; `API-Version: 1.0` là **hợp đồng do ứng dụng định nghĩa**. Không buộc `API-Version` bằng version của Spring Boot hay version deploy của service.

**Version API cũng không phải giải pháp cho mọi thay đổi:** nhiều thay đổi tương thích ngược (thêm field optional, sửa lỗi, tăng hiệu năng) có thể không cần version mới. Versioning nên đi với quy tắc compatibility, contract tests và chính sách lifecycle rõ ràng.

## 2. Điều mới trong Spring Framework 7

Trước Spring 7, ứng dụng thường tự viết:
- `/api/v1/books` và `/api/v2/books` trên hai path khác nhau;
- điều kiện `headers="X-API-Version=1"`, query param `?v=2` hoặc vendor media type;
- `HandlerInterceptor` / `RequestCondition` / custom mapping để xử lý phiên bản phức tạp;
- tự thêm response headers công bố ngừng hỗ trợ.

Spring Framework 7 đưa vào MVC cơ chế cấu hình chính thức qua `WebMvcConfigurer#configureApiVersioning(ApiVersionConfigurer)`, một `ApiVersionStrategy` để điều phối resolver, parser, validation và deprecation handler, và thuộc tính `version` trên annotation request mapping. <https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html>

### 2.1. Bốn thành phần cần phân biệt

| Thành phần | Trách nhiệm | Cần dùng trực tiếp? |
| --- | --- | --- |
| `ApiVersionConfigurer` | Khai báo vị trí lấy version, parser, danh sách supported versions, policy missing/default, deprecation handler | **Có**, trong `WebMvcConfigurer` |
| `ApiVersionResolver` | Lấy chuỗi version thô từ header, query, media type parameter hoặc path segment | Dùng built-in hoặc custom |
| `ApiVersionParser` | Parse giá trị thô thành kiểu `Comparable<?>` phục vụ so sánh/sắp xếp | Mặc định đủ nếu version số kiểu `1.2.3` |
| `ApiVersionStrategy` | Điều phối resolution, parsing, validation, chọn mapping và phát tín hiệu deprecated version | Framework thường quản lý, không tự new |
| `ApiVersionDeprecationHandler` | Sinh thông tin deprecated/sunset với response headers | Cấu hình khi có lifecycle |
| `StandardApiVersionDeprecationHandler` | Implementation chuẩn dựa theo RFC 9745 và RFC 8594 | Có sẵn, dùng cho thông báo lifecycle |

Luồng logic (giản lược):

```text
HTTP request
   |
ApiVersionResolver: "2.1"
   |
ApiVersionParser -> comparable version 2.1.0
   |
Validate 2.1 thuộc supported versions?
   |             \
   | yes          \ no -> InvalidApiVersionException -> 400
   v
Choose compatible @GetMapping(version=...)
   |
Execute handler (Model, service, converters...)
   |
If requested version deprecated:
  ApiVersionDeprecationHandler adds headers
   |
HTTP response
```

Khi API versioning được bật, mặc định **client phải gửi version**; thiếu dẫn đến `MissingApiVersionException` và HTTP **400**. Có thể đặt default version hoặc cho phép thiếu, nhưng phải hiểu hệ quả compatibility trước khi thay mặc định.

## 3. Cấu hình ApiVersionConfigurer trong Spring MVC

Cách đơn giản nhất là lấy version từ header `API-Version`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiVersionWebConfig implements WebMvcConfigurer {
    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("API-Version");
    }
}
```

Đây là **snippet độc lập về class config**, cần đặt vào project có Spring Framework 7/Spring Web MVC. API này không có trên Spring Boot 3.x đang quản lý Spring Framework 6.x.

**Điểm cốt lõi:** call `useRequestHeader("API-Version")` kích hoạt cơ chế versioning, nhưng các controller vẫn phải khai báo `@GetMapping(version = "1.0")` hoặc mapping tương thích theo ý định. Thêm config không tự biến mọi endpoint thành nhiều phiên bản.

### 3.1. Các cách phân giải version được hỗ trợ

| Nguồn | Dạng request | Cấu hình trong Spring 7 | Trade-off |
| --- | --- | --- | --- |
| Header riêng | `API-Version: 2.0` | `configurer.useRequestHeader("API-Version")` | URI ổn định; client cần truyền header |
| Query parameter | `GET /api/books?api-version=2.0` | `configurer.useQueryParam("api-version")` | Dễ thử bằng URL; query là một phần cache key; dễ bị link share sai |
| Path segment | `GET /api/2.0/books` | `configurer.usePathSegment(1)` với path `/api/{version}/books` | Rõ ràng về URI, CDN routing dễ hơn; prefix phải chuẩn |
| Media type parameter | `Accept: application/json;version=2.0` | `configurer.useMediaTypeParameter(MediaType.APPLICATION_JSON,"version")` | Tận dụng content negotiation; client/proxy phải xử lý đúng |
| Tùy biến | Header khác, composite strategy | `configurer.useVersionResolver(customResolver)` | Linh hoạt nhưng phải kiểm thử nguồn, ambiguity, validation |

Các snippet bảng là **phương án thay thế**, không đặt đồng thời mọi resolver nếu không có policy về thứ tự/độ ưu tiên rõ ràng.

### 3.2. Header versioning

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version");
}
```

Client:

```bash
curl -i -H 'API-Version: 2.0' http://localhost:8080/api/books
```

Header này là **API contract version**, không phải authorization. Client tự chọn version **được hỗ trợ**; server vẫn kiểm tra authentication, tenant, permission như bình thường.

### 3.3. Query parameter versioning

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useQueryParam("api-version");
}
```

```http
GET /api/books?api-version=2.0
```

Cần định nghĩa behavior khi có nhiều giá trị query param cùng tên; không dùng logic “lấy phiên bản cao nhất” tự viết nếu framework đã có parser và policy. Cache, canonical links, OpenAPI và client SDK phải gửi query này ổn định.

### 3.4. Path segment versioning

Với URL `/api/2.0/books`, path segments tính từ 0 thường là `api` = 0, `2.0` = 1, `books` = 2:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.usePathSegment(1);
}
```

Đường dẫn controller cần chứa **URI variable** ở vị trí được giải phiên bản:

```java
@RestController
@RequestMapping("/api/{version}/books")
class PathBookController {
    @GetMapping(version = "2.0")
    public String booksV2() {
        return "books-v2";
    }
}
```

Đây là snippet controller riêng chỉ để minh họa path resolver; không ghép vào demo header ở mục 8. Biến path có thể tên khác `version`, nhưng cần nằm đúng index được cấu hình. Path resolver không trả `null` khi không thể tìm version (trừ biến thể có `Predicate<RequestPath>` để nhận diện path nào có version). Với ứng dụng có cả route `/health` và `/api/{version}/...`, cần thiết kế predicate/path prefix hoặc tách routing config sao cho non-versioned endpoints không bị parse sai.

### 3.5. Media type parameter

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useMediaTypeParameter(
            MediaType.APPLICATION_JSON, "version");
}
```

```http
GET /api/books
Accept: application/json;version=2.0
```

Resolver có thể đọc media type parameter từ `Accept` hoặc `Content-Type` theo API javadoc, khi media type tương thích với type cấu hình. Không nhầm `Accept` (client muốn response type nào) với `Content-Type` (request body type). Khi dùng `Vary: Accept` và HTTP cache, cần cấu hình/kiểm thử cache để không trả nhầm representation giữa versions.

### 3.6. Không có version trong request

Mặc định khi đã bật versioning, thiếu version có thể phát sinh:

```text
MissingApiVersionException -> HTTP 400 Bad Request
```

Để dùng default version có chủ đích:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version")
            .setDefaultVersion("1.0");
}
```

Theo API config, đặt default version khiến version không còn bắt buộc và request không khai báo được gán default. Có thể dùng:

```java
configurer.setVersionRequired(false);
```

Khi không yêu cầu version và **không đặt default**, Spring có thể chọn version mới nhất theo strategy; đây là một lựa chọn nguy hiểm cho backward compatibility vì client im lặng có thể tự động chuyển response contract khi server thêm version mới.

**Khuyến nghị:** production public APIs nên công bố rõ hành vi thiếu version: trả 400 yêu cầu client khai báo, hoặc giữ một default lâu dài với migration plan, thay vì đổi sang version cao nhất âm thầm.

## 4. ApiVersionParser: version có nghĩa gì?

Spring 7 cung cấp parser mặc định `SemanticApiVersionParser`: nhận số phiên bản dưới dạng `major`, `minor`, `patch`; nếu thiếu minor/patch sẽ mặc định 0.

| Chuỗi | Phân giải về mặt thành phần |
| --- | --- |
| `1` | `1.0.0` |
| `1.2` | `1.2.0` |
| `1.2.3` | `1.2.3` |
| `2.0` | `2.0.0` |

Điều này cho phép so sánh phiên bản theo số thay vì theo chuỗi. Ví dụ 2.10 lớn hơn 2.9 về số, trong khi so sánh chuỗi lexicographic có thể sai.

**Không nhầm tên parser với npm/SemVer đầy đủ:** mặc dù hỗ trợ major/minor/patch, không tự cho rằng mọi cú pháp prerelease/build metadata như `1.2.3-beta+7` đều được chấp nhận hoặc có ordering như thư viện SemVer bất kỳ. Nếu doanh nghiệp định nghĩa version bằng ngày tháng như `2026-10` hoặc dùng mã riêng, cần custom `ApiVersionParser` tuân hợp đồng `Comparable<?>` và kiểm thử lỗi parse.

### 4.1. Custom resolver và parser

Spring có extension:
- `ApiVersionResolver` khi nguồn version nằm ở một cơ chế không có built-in.
- `ApiVersionParser<?>` khi định dạng version custom.
- `ApiVersionStrategy` lưu parser/resolver và so sánh metadata.

Chỉ custom khi hợp đồng thật sự cần. Nếu version đến từ token/tenant metadata thay vì request header, vẫn cần bảo đảm không cho attacker nâng/hạ quyền bằng cách điều khiển string; API version chỉ là cách chọn contract chứ **không** là authorization.

## 5. Supported version khác mapped version

Đây là một khái niệm quan trọng và dễ gây hiểu sai trong Spring 7:

1. **Supported version:** phiên bản mà application chấp nhận là version hợp lệ (validation).
2. **Mapped version:** điều kiện chọn method controller, có thể là fixed `"1.0"` hoặc baseline `"2.0+"`.
3. **Selected version:** version client thật sự yêu cầu sau resolver/parser/default.

Mặc định Spring phát hiện supported versions từ những giá trị được khai báo trong controller mappings. Nhưng một **baseline mapping** có thể cung cấp implementation cho các version cao hơn mà **chưa xuất hiện trong annotation**, nếu bạn đã thêm chúng vào danh sách supported versions.

Ví dụ:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version");
    configurer.addSupportedVersions("1.0", "2.0", "2.1");
}
```

Và:

```java
@GetMapping(path = "/books", version = "1.0")
public String v1() {
    return "v1";
}

@GetMapping(path = "/books", version = "2.0+")
public String v2AndLater() {
    return "v2";
}
```

Kết quả khi configuration và mappings cùng hoạt động:

| API-Version | Supported? | Mapping ứng viên | Kết quả |
| --- | --- | --- | --- |
| `1.0` | Có | Fixed `1.0` | `v1()` |
| `2.0` | Có | Baseline `2.0+` | `v2AndLater()` |
| `2.1` | Có, thêm explicit | Baseline `2.0+` | `v2AndLater()` |
| `3.0` | Không | Không vào mapping vì validation từ chối | 400 |
| Không có header | Thiếu | Không chọn | 400 mặc định |

**Dấu `+` ở đây không phải SemVer range parser tổng quát**. Đó là cú pháp đặc biệt của điều kiện version trên Spring request mapping để nói “từ mốc này trở đi trong tập versions được hỗ trợ”.

### 5.1. Fixed mapping

```java
@GetMapping(version = "2.0")
```

Chỉ khớp version bằng `2.0` theo parser. Nó không tự nhận `2.1`.

### 5.2. Baseline mapping

```java
@GetMapping(version = "2.0+")
```

Được dùng cho version 2.0 và các phiên bản cao hơn **đã được đánh dấu supported**. Nó đặc biệt hữu ích khi thay đổi nhỏ không cần controller mới: một implementation v2 có thể tiếp tục xử lý phiên bản 2.1.

**Chú ý an toàn contract:** nếu v2 logic không tương thích với version 2.1 do response shape bị thay đổi, đừng thêm 2.1 supported chỉ để tránh viết mapping. Baseline mapping là lời hứa compatibility cho các version cao hơn tương ứng.

### 5.3. Mapping không khai báo version

```java
@GetMapping("/books")
```

Nếu có method không khai báo version, nó có thể match mọi version nhưng sẽ bị mapping cụ thể hơn ưu tiên. Có thể dùng nó như fallback có chủ đích, nhưng tránh một unversioned method làm ẩn lỗi compatibility.

### 5.4. Quy tắc chọn phiên bản gần nhất

Giả sử có ba methods cho cùng URL/HTTP method:
- không gắn version;
- fixed `1.1`;
- baseline `1.2+`;
- fixed `1.5`.

Spring 7 so điều kiện phiên bản và chọn mapping phù hợp cụ thể nhất; baseline chỉ match từ ngưỡng trở lên, còn fixed version phù hợp được ưu tiên cho đúng version của nó. Với request `1.3`, baseline `1.2+` có thể thắng nếu `1.3` được khai báo supported. Với request `1.5`, fixed `1.5` sẽ có ưu thế so với baseline cũ, không đẩy request về method version thấp.

**Đừng mặc định chỉ cần dùng `"1.2+"` là 1.3, 1.4, 1.5... đều hợp lệ:** validation vẫn kiểm tra supported versions. Mặc định support detection từ mappings chỉ lấy các version được khai báo; cần thêm các version trung gian khi muốn hỗ trợ.

## 6. Thay đổi lifecycle: Deprecated, Sunset và removed

API versioning không chỉ là phân giải request. Một phần quan trọng là **làm sao thông báo client chuẩn bị chuyển sang phiên bản mới**.

Cần phân biệt:

| Trạng thái | Nghĩa | Hành động server/client |
| --- | --- | --- |
| **Supported** | Version hợp lệ và có implementation | Server xử lý bình thường |
| **Deprecated** | Version vẫn có thể hoạt động nhưng nhà cung cấp khuyến nghị chuyển đi | Trả header `Deprecation`, Link tới hướng dẫn migrate; theo dõi usage |
| **Sunset announced** | Đã thông báo mốc dự kiến không còn cung cấp resource/version | Trả `Sunset` và Link tới thông tin chính sách |
| **Removed/unsupported** | Version không còn được server chấp nhận | Ngừng mapping/supported list; trả lỗi theo contract/API gateway |

**Deprecated không đồng nghĩa 404, 410 hoặc 400 ngay lập tức.** Khi version còn hỗ trợ, request vẫn được xử lý. Header giúp client biết thời gian/lộ trình.

**Sunset header không tự hẹn giờ tắt API.** Nó là metadata nói về thời điểm dự kiến. Sau thời điểm đó, việc tắt version thực sự cần thay đổi cấu hình, code, gateway và bảo đảm migration policy; không có nghĩa Spring tự xóa controller method theo ngày.

## 7. StandardApiVersionDeprecationHandler: thông báo chuẩn

Spring Framework 7 cung cấp `org.springframework.web.accept.StandardApiVersionDeprecationHandler`, phù hợp với:

- **RFC 9745 — Deprecation HTTP Response Header Field**.
- **RFC 8594 — The Sunset HTTP Header Field**.
- **Link** header với `rel="deprecation"` hoặc `rel="sunset"` chỉ tới trang tài liệu/hướng dẫn tương ứng.

Các method được công bố trong Spring 7 Javadoc:

```java
StandardApiVersionDeprecationHandler handler =
        new StandardApiVersionDeprecationHandler();

handler.configureVersion("1.0")
        .setDeprecationDate(
                ZonedDateTime.parse("2026-07-01T00:00:00Z"))
        .setSunsetDate(
                ZonedDateTime.parse("2027-07-01T00:00:00Z"))
        .setDeprecationLink(
                URI.create("https://docs.example.test/api/migrate-v2"))
        .setSunsetLink(
                URI.create("https://docs.example.test/api/sunset-v1"));

configurer.setDeprecationHandler(handler);
```

Đây là **snippet nằm trong `configureApiVersioning(...)`**, cần imports `java.net.URI`, `java.time.ZonedDateTime`, `StandardApiVersionDeprecationHandler`. Domain `docs.example.test` chỉ là ví dụ minh họa, không phải URL hoạt động.

### 7.1. Cú pháp và mục đích headers

Khi client request version 1.0, response có thể gồm:

```http
Deprecation: @1782864000
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://docs.example.test/api/migrate-v2>; rel="deprecation"; type="text/html"
Link: <https://docs.example.test/api/sunset-v1>; rel="sunset"; type="text/html"
```

**Các dòng trên là dạng minh họa** theo RFC, không phải assertion rằng container sẽ luôn format/case/order y hệt. `Deprecation` dùng timestamp dạng structured field (RFC 9745); `Sunset` dùng HTTP-date (RFC 8594); `Link` có relation type giúp client phân biệt tài liệu deprecation và sunset.

Ngày giờ trong ví dụ **không đồng nghĩa** phiên bản 1.0 tự ngừng hoạt động đúng giờ đó. Khi application chạy ở môi trường thật, dùng ngày được product/legal/ops công bố, đừng lấy ngày học ví dụ làm lịch sản phẩm.

### 7.2. Bản v2 còn hoạt động

Với version 2.0 và 2.1 chưa đánh dấu deprecated, deprecation handler trên không phát các headers deprecated-v1 tương ứng. Điều này giúp client nhận cảnh báo **đúng phiên bản** thay vì nhận thông báo không liên quan.

### 7.3. Thông báo cho một nhóm request nhất định

`StandardApiVersionDeprecationHandler.VersionSpec#setRequestPredicate(Predicate<HttpServletRequest>)` cho phép lọc những request mà response nên mang deprecation headers. Chẳng hạn nhóm API dưới `/api/legacy/` cần cảnh báo, còn `/actuator` không. Đây là tính năng tùy chọn; việc phân nhóm phải dựa trên route/feature thật để không vô tình che thông báo của những client cần migrate.

### 7.4. Nếu dùng custom ApiVersionParser

Constructor `StandardApiVersionDeprecationHandler(ApiVersionParser<?>)` cho phép dùng parser cùng kiểu với application. Nếu application dùng version parse custom nhưng deprecation handler vẫn dùng parser mặc định, thông tin deprecated version có thể được so sánh sai hoặc không nhận diện được. Giữ nhất quán cùng parser cho mapping/validation/deprecation.

### 7.5. Không tự tạo header giả theo cú pháp đoán

Ví dụ này **không** tương đương:

```http
Deprecation: true
Sunset: 2027-07-01
```

Bởi RFC mới có cú pháp rõ cho từng header. Đừng phát giá trị tùy ý rồi mong client hiểu. Ưu tiên handler chuẩn hoặc xây custom handler có tests theo RFC; document nơi xem migration guide.

## 8. Ví dụ hoàn chỉnh chạy được — Java 17+, Spring Boot 4.x

Ví dụ này dùng Spring Boot **4.0.x** (quản lý Spring Framework 7.0.x), Java 17+, **Spring Web MVC**, không có database hay Spring Security để tập trung vào phân giải, mapping và deprecation headers.

**Không dùng** `spring-boot-starter-web` của bài Spring Boot 3 rồi mặc định đó là starter khuyến nghị cho Boot 4. Spring Boot 4 modular hóa starters; Spring MVC starter khuyến nghị là `spring-boot-starter-webmvc`, test companion là `spring-boot-starter-webmvc-test`.

### 8.1. Tạo Maven project

Tại [Spring Initializr](https://start.spring.io/), chọn Maven, Java 17+ và Spring Boot 4.0.x, thêm dependency **Spring Web MVC**. Dependency chính:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
</dependencies>
```

Đây là fragment của POM. Project Initializr tạo parent/BOM, version, plugin và metadata cần thiết. Nếu muốn thay version Boot mới hơn, cần kiểm tra tài liệu Spring Framework đi kèm để tránh nhầm API giữa 7.0 và 7.1.

Cấu trúc:

```text
src/main/
  java/com/example/demo/DemoApplication.java
```

### 8.2. Java source đầy đủ

Đặt toàn bộ vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.time.ZonedDateTime;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.accept.StandardApiVersionDeprecationHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class ApiVersionWebConfiguration implements WebMvcConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        // Trong demo, client chọn API contract qua header.
        configurer.useRequestHeader("API-Version");

        // Hai version có mapping, 2.1 tiếp tục dùng baseline v2.
        configurer.addSupportedVersions("1.0", "2.0", "2.1");

        // Nếu không có version, Spring trả 400 (default policy).
        configurer.setVersionRequired(true);

        StandardApiVersionDeprecationHandler deprecated =
                new StandardApiVersionDeprecationHandler();

        deprecated.configureVersion("1.0")
                .setDeprecationDate(
                        ZonedDateTime.parse("2026-07-01T00:00:00Z"))
                .setSunsetDate(
                        ZonedDateTime.parse("2027-07-01T00:00:00Z"))
                .setDeprecationLink(URI.create(
                        "https://docs.example.test/api/migrate-v2"))
                .setSunsetLink(URI.create(
                        "https://docs.example.test/api/sunset-v1"));

        configurer.setDeprecationHandler(deprecated);
    }
}

record BookV1(String title) {
}

record BookV2(long id, String name, String author) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping(version = "1.0")
    public List<BookV1> booksV1() {
        return List.of(new BookV1("Spring"));
    }

    @GetMapping(version = "2.0+")
    public List<BookV2> booksV2() {
        return List.of(new BookV2(
                1L, "Spring", "Spring Team"));
    }
}
```

**Giải thích:**
- `@Configuration` + `WebMvcConfigurer#configureApiVersioning` kích hoạt resolver qua `useRequestHeader("API-Version")`.
- `addSupportedVersions("1.0", "2.0", "2.1")` công bố những version hợp lệ; version trong annotated mappings cũng có thể được phát hiện tự động theo default. Khai báo explicit giúp reviewer thấy version 2.1 thật sự được chấp nhận.
- `setVersionRequired(true)` nhấn mạnh default policy: client không truyền version bị từ chối.
- V1 method cố định `version="1.0"` trả shape cũ.
- V2 method `version="2.0+"` là baseline mapping, nên cũng xử lý version 2.1 đã được khai báo supported.
- Handler phiên bản cũ gửi metadata `Deprecation`, `Sunset` và `Link`.
- Mỗi record immutable, không có database/security; trong production cần authentication, authorization, rate limiting, input validation và các policy vận hành.
- Mặc dù 2.1 dùng handler v2, nội dung version 2.1 vẫn là một public contract cần được test; không tự nhận là backward compatible chỉ vì cùng Java method.

### 8.3. Chạy

Từ root project:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Nếu không đặt port, server dùng `http://localhost:8080` theo cấu hình phổ biến của Spring Boot.

### 8.4. Gọi version 1.0

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 1.0'
```

Kết quả quan trọng:

```http
HTTP/1.1 200
Content-Type: application/json
Deprecation: @...
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://docs.example.test/api/migrate-v2>; rel="deprecation"; type="text/html"
Link: <https://docs.example.test/api/sunset-v1>; rel="sunset"; type="text/html"

[{"title":"Spring"}]
```

Header `Deprecation` có timestamp được sinh từ ngày đã cấu hình; `@...` là ký hiệu mô tả, không phải literal value phải xuất hiện. Các headers Link có thể gộp/được serialize theo thứ tự khác, nên hãy kiểm tra ý nghĩa của relations thay vì so nguyên raw response. Body JSON order/whitespace cũng do converter quyết định.

### 8.5. Gọi version 2.0

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 2.0'
```

Response:

```json
[{"id":1,"name":"Spring","author":"Spring Team"}]
```

Status 200. Bản v2 không có deprecation hints cho v1 nếu chỉ `configureVersion("1.0")`.

### 8.6. Gọi version 2.1 dùng baseline mapping

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 2.1'
```

Vì 2.1 đã được thêm vào `addSupportedVersions` và `@GetMapping(version="2.0+")`, response body dùng cấu trúc v2:

```json
[{"id":1,"name":"Spring","author":"Spring Team"}]
```

**Điểm học tập:** `2.1` **không nhất thiết cần một Java controller method mới**, nếu cùng implementation đúng contract. Nhưng bản version mới vẫn phải đi qua release review.

### 8.7. Gọi version không hỗ trợ

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 3.0'
```

Vì `3.0` không có trong danh sách supported versions và không được phát hiện từ mappings, Spring MVC ném `InvalidApiVersionException`, HTTP **400 Bad Request** theo tài liệu. HTTP error body thực tế phụ thuộc error configuration, nên không ghi một JSON body bất biến ở đây.

### 8.8. Không truyền version

```bash
curl -i 'http://localhost:8080/api/books'
```

Nếu bật `setVersionRequired(true)` và không có default, Spring MVC ném `MissingApiVersionException`, HTTP **400 Bad Request**. Điều này khác hoàn toàn với `404 Not Found` (không có tài nguyên) hoặc `406 Not Acceptable` (content negotiation).

### 8.9. PowerShell

Bash dùng `\` để nối dòng. Trong PowerShell dùng `curl.exe` trên một dòng:

```powershell
curl.exe -i "http://localhost:8080/api/books" -H "API-Version: 1.0"
```

Header version là một giá trị chuỗi; dùng `1.0` thay vì `v1` vì parser mặc định không tự hiểu tùy ý mọi tên version.

## 9. Kiểm thử MockMvc trên Spring Boot 4

Spring Boot 4 modular hóa các test starters; dùng `spring-boot-starter-webmvc-test` thay vì chỉ áp dụng nguyên hướng dẫn `spring-boot-starter-test` cũ của Boot 3. Thêm vào Maven POM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc-test</artifactId>
    <scope>test</scope>
</dependency>
```

Trong Boot 4, `@AutoConfigureMockMvc` nằm tại `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`, **không còn** đường dẫn cũ `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

### 9.1. File test có thể chạy

Tạo `src/test/java/com/example/demo/ApiVersioningTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiVersioningTest {

    @Autowired
    MockMvc mvc;

    @Test
    void v1ShouldReturnOldRepresentation() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "1.0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("Spring"));
    }

    @Test
    void v2AndV21ShouldUseV2Representation() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "2.0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("Spring"));

        mvc.perform(get("/api/books")
                        .header("API-Version", "2.1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].author")
                        .value("Spring Team"));
    }

    @Test
    void missingVersionShouldBeRejected() throws Exception {
        mvc.perform(get("/api/books"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownVersionShouldBeRejected() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "3.0"))
                .andExpect(status().isBadRequest());
    }
}
```

Các test này kiểm tra mapping và missing/unsupported behavior. Chúng chưa kiểm tra chính xác cú pháp của response deprecation headers, vì vậy cần test riêng.

### 9.2. Test deprecation headers

Có thể bổ sung test:

```java
@Test
void v1ShouldExposeDeprecationHints() throws Exception {
    mvc.perform(get("/api/books")
                    .header("API-Version", "1.0"))
            .andExpect(status().isOk())
            .andExpect(header().exists("Deprecation"))
            .andExpect(header().exists("Sunset"))
            .andExpect(header().exists("Link"));
}
```

Đây là snippet method **thêm vào class test đã có**, cần import:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
```

Test này xác minh các headers tồn tại; trong production nên parse kiểm tra `Deprecation` structured date, `Sunset` HTTP-date, `Link rel` và ngày chuyển version theo contract. Đồng thời test rằng `API-Version: 2.0` không nhận warning của v1.

### 9.3. Chạy test

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Nếu một framework document/starter khác thay đổi test dependencies hoặc mock setup, kiểm tra Boot 4.0.x Javadoc và Maven dependency tree. Không thêm nhầm cùng lúc cả Spring Boot 3 test auto-config package và Boot 4 test starter.

## 10. Client support trong Spring 7

Theo tài liệu Spring Framework 7, khả năng tương thích version client được tích hợp với:
- `RestClient`;
- `WebClient`;
- declarative HTTP service clients (HTTP interface);
- testing `MockMvc` và `WebTestClient`.

Điều này không có nghĩa client tự đoán version server. Client phải chọn một version phù hợp API contract; cấu hình client có thể hỗ trợ gắn thông tin version vào request theo strategy được hỗ trợ. Trong ứng dụng chỉ sử dụng header, cách rõ nhất là truyền `API-Version` trên từng request/đặt default request header trong client builder theo API tương ứng:

```java
// Fragment minh họa RestClient dùng Spring 7; URL chỉ là demo.
RestClient client = RestClient.builder()
        .baseUrl("https://api.example.test")
        .defaultHeader("API-Version", "2.0")
        .build();
```

Cần import `org.springframework.web.client.RestClient` và dependency client tương thích Spring Boot 4. Đừng nhầm defaultHeader với parser/configurer phía server; phải đặt cùng tên header với `useRequestHeader("API-Version")`. Với web app dùng browser, CORS cần cho phép `API-Version` vì đây không phải CORS-safelisted request header, và cache layer phải biết version nằm ở header.

## 11. Chọn chiến lược version cho một hệ thống thực

| Tiêu chí | URL path `/v1/...` | Header `API-Version` | Query `?v=1` | Media type param |
| --- | --- | --- | --- | --- |
| Dễ thử trên trình duyệt | Cao | Cần header tool | Cao | Cần header |
| URI cho mỗi version khác nhau | Có | Không | Query khác | Không |
| Reverse proxy/CDN routing | Tương đối dễ | Phải chú ý header | Phải bao query | Chú ý Accept/Content-Type |
| Mức độ rõ với consumer | Cao | Tùy tài liệu/SDK | Cao | Cần hiểu content negotiation |
| Nguy cơ cache trộn version | Thường thấp hơn nếu URI tách | **Phải có Vary/cache key theo header** | Cache key query | **Vary: Accept**, media variants |
| Thêm URL mới khi đổi version | Có | Không | Không | Không |

Không có một chiến lược tốt cho mọi tổ chức. Điều quan trọng là **công bố và duy trì một contract nhất quán**:
- Thời điểm nào tăng major/minor.
- Version nào được hỗ trợ đồng thời.
- Khi nào chỉ sửa bug mà không đổi version.
- Client nhận 400 khi thiếu/sai version hay có default.
- Header/link nào phát cảnh báo chuyển phiên bản.
- Cách client tự động sinh/gắn version (SDK, OpenAPI).
- Lộ trình kiểm thử các versions cũ.

### 11.1. Caching với version qua header

Nếu cache/CDN dùng một URI `/api/books` cho nhiều version mà **bỏ qua API-Version**, cached body v1 có thể được gửi cho client v2.

Ví dụ response:

```http
Vary: API-Version
```

Khi resource được phép cache, `Vary` báo rằng representation phụ thuộc vào request header; CDN/proxy phải thực sự đưa header vào cache key theo chính sách của sản phẩm. Nếu API có dữ liệu riêng, còn phải áp `Cache-Control: private/no-store` và authorization-aware cache strategy; `Vary` không tự bảo vệ dữ liệu bí mật.

### 11.2. Versioning không thay content negotiation

`@GetMapping(version="2.0", produces="application/json")` có thể đồng thời dùng version mapping và điều kiện `produces`. Version quyết định hợp đồng; media type quyết định representation format. Nếu dùng media type parameter làm nguồn version, cần đảm bảo proxy/client truyền đúng `Accept` hoặc `Content-Type`; không tự xem `Accept: application/json` có version được đoán nếu chưa cấu hình default.

### 11.3. Security và backward compatibility

- Không để version 1.0 bỏ qua authentication/authorization vì đó là “legacy”.
- Không mở một endpoint v1 chứa dữ liệu user B qua điều kiện mapping chỉ vì v2 đã sửa quyền.
- Rate limit/CSRF/CORS/input validation phải bao phủ mọi supported versions.
- Version request không phải token để nâng quyền.
- Mọi thay đổi bảo mật quan trọng thường phải được backport cho versions còn hỗ trợ, hoặc công bố sunset nhanh có kiểm soát.

## 12. Policy ngừng hỗ trợ phiên bản: quy trình kỹ thuật và sản phẩm

Một lộ trình đơn giản:

1. **Công bố v2:** mapping/API docs/SDK contract tests, migration guide.
2. **Quan sát v1 usage:** phân tích theo clientId/SDK version/tenant đã làm sạch dữ liệu, không log access token.
3. **Đánh dấu v1 deprecated:** bật `StandardApiVersionDeprecationHandler`, headers Deprecation/Link.
4. **Công bố Sunset:** đặt ngày dự kiến, thêm Sunset/Link, liên hệ những client còn dùng v1.
5. **Hỗ trợ giai đoạn chuyển đổi:** lỗi chi tiết, mapping cũ hoạt động theo policy, tránh phá hợp đồng đột ngột.
6. **Sunset thực tế:** update supported version list, controllers/gateway/SDK và error response theo lịch đã phê duyệt.
7. **Theo dõi hậu sunset:** số request v1 không còn được hỗ trợ, alert, support policy và rollback nếu cần.

### 12.1. Deprecation header không tự “tắt” endpoint

`configureVersion("1.0")` chỉ đăng ký deprecation metadata. Nó **không tự loại 1.0 khỏi supported versions**. Nếu muốn loại version sau sunset, cần thay đổi config/routing được triển khai và test.

### 12.2. Trạng thái HTTP cho version đã bị gỡ

Khi Spring 7 validation thấy version không nằm trong supported list, `InvalidApiVersionException` mặc định được xử lý thành **400 Bad Request**. Nếu doanh nghiệp muốn một response riêng (ví dụ error code `API_VERSION_RETIRED` hoặc `410 Gone` cho route đã sunset), cần xây contract/error handling riêng; **đừng mặc định framework tự trả 410** khi đến ngày trong Sunset header.

### 12.3. Thời điểm deprecation và sunset khác nhau

`Deprecation` cho biết API bị tuyên bố lỗi thời từ một thời điểm; `Sunset` cho biết thời điểm dự kiến resource ngừng khả dụng theo policy. Hai mốc có thể khác nhau. Không cần đợi đến ngày Sunset mới bắt đầu thông báo cho client. Dùng ngày giờ có timezone rõ, tốt nhất UTC, và theo dõi thay đổi chính sách.

### 12.4. Link tới migration guide phải ổn định

URI trong `Link rel="deprecation"` / `rel="sunset"` phải là URL công khai ổn định và không chứa token hay dữ liệu nhạy cảm. Nếu docs host đổi, duy trì redirects hợp lệ. Không xây link dựa trên `Host`/`X-Forwarded-Host` do client tùy ý để tránh host-header poisoning.

## 13. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Project Boot 3 báo không có `configureApiVersioning` | Đang dùng Spring Framework 6.x | Dùng Boot 4/Spring 7 hoặc phương án versioning cũ |
| `@GetMapping(version=...)` không compile | Dependency/framework version chưa đủ mới | Xác minh Spring 7.x và starter Web MVC |
| Version 2.1 trả 400 dù mapping 2.0+ | 2.1 chưa nằm trong supported versions | Thêm `addSupportedVersions("2.1")` hoặc mapping version tương ứng |
| Request thiếu header trả 400 | Mặc định version required | Client phải gửi; hoặc đặt default có chủ đích |
| Bật `setVersionRequired(false)` rồi client cũ đổi shape | Chọn latest version khi missing | Dùng default cố định hoặc bắt buộc header |
| Handler nhận sai version | Fixed/baseline mapping bị hiểu sai | Review `version="1.0"` vs `"2.0+"` và supported list |
| Path version 400 | Segment index/prefix sai | Đếm path segments từ 0; URI variable tương ứng |
| Version `v1` bị reject | Default parser nhận version số | Dùng 1.0 hoặc custom parser |
| Unsupported version không trả 404 | Validator xử lý sớm hơn mapping | Đây là behavior 400 mặc định của Spring 7 |
| Không thấy Deprecation header | Chưa cấu hình handler hoặc version chưa đánh deprecated | `setDeprecationHandler` và `configureVersion("1.0")` |
| Sunset đã qua nhưng v1 vẫn 200 | Handler chỉ phát metadata | Chính sách removal phải triển khai riêng |
| Header Deprecation không giống HTTP-date | RFC 9745 dùng dạng timestamp | Parse theo đúng RFC, không ép format Sunset |
| CORS preflight từ browser bị chặn | Custom API-Version header chưa allowed | CORS allowedHeaders, OPTIONS, auth setup |
| CDN trả JSON v1 cho v2 | Cache key bỏ qua API-Version | Vary/header-aware caching |
| MockMvc không tìm AutoConfigureMockMvc | Boot 4 đã đổi package/test starter | Dùng `spring-boot-starter-webmvc-test` và import mới |
| Hai controller mappings ambiguity | Duplicate path/method/version conditions | Giảm overlap, test handler resolution |
| Lỗi validation bị biến thành 200 | Custom @ExceptionHandler trả body thiếu status | Giữ 400/ProblemDetail phù hợp contract |

## 14. Checklist QA trước triển khai

1. Chạy Spring Framework 7.x thực sự, với Boot 4.x quản lý tương thích; không dựa trên snippet Spring 6.x.
2. Config `configureApiVersioning` có một resolver rõ ràng (header/query/path/media) và parser đúng định dạng version.
3. Missing-version policy có chủ đích: 400 hoặc default cố định.
4. Supported versions được định nghĩa đúng, không ngầm cho mọi version tương lai bằng baseline mapping.
5. Fixed và baseline mappings không tranh nhau mơ hồ; test version ở ranh giới.
6. Response DTO v1/v2 có contract tests so schema, nullability, names, semantics, lỗi và security.
7. Custom header version có CORS/caching/proxy treatment rõ ràng.
8. Mọi version đều có authentication/authorization/validation và rate limits phù hợp.
9. Deprecated versions phát `Deprecation`/`Sunset`/`Link` đúng RFC, link thực sự giúp migrate.
10. Có lộ trình gỡ version và metrics theo client đã chọn lọc; không dựa vào header để tự tắt controller.
11. MockMvc/HTTP integration tests bao missing, malformed, unsupported, v1, v2, baseline v2.1 và thông báo deprecated.
12. Monitoring phân biệt lỗi version selection với lỗi business/controller, tránh dùng 500 cho một request version không hỗ trợ.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Cấu hình API versioning đầu tiên trong Spring Web MVC 7 đặt ở đâu?

**Đáp án:** Callback `WebMvcConfigurer#configureApiVersioning(ApiVersionConfigurer)`; ví dụ `configurer.useRequestHeader("API-Version")`.

**Câu 2.** `@GetMapping(version="2.0")` có mặc định xử lý request `2.1` không?

**Đáp án:** Không. Đó là fixed version. Muốn dùng implementation từ 2.0 trở đi, cân nhắc baseline `version="2.0+"` và khai báo các higher versions là supported.

**Câu 3.** Tại sao version 2.1 có thể trả 400 dù có method `version="2.0+"`?

**Đáp án:** Version 2.1 chưa nằm trong supported versions; mapping compatibility và validation là hai bước khác nhau.

**Câu 4.** Mặc định không có header version sau khi bật API versioning thì sao?

**Đáp án:** `MissingApiVersionException`, HTTP 400, trừ khi bạn thay policy required/default.

**Câu 5.** `Sunset: ...` có làm framework xóa controller ngay tại mốc giờ đó không?

**Đáp án:** Không. Nó là metadata thông báo; muốn ngừng hỗ trợ phải có thay đổi release/config/gateway tương ứng.

**Câu 6.** `Deprecation` và `Sunset` có một định dạng ngày giống hệt nhau không?

**Đáp án:** Không. Deprecation theo RFC 9745 sử dụng cấu trúc timestamp, Sunset theo RFC 8594 dùng HTTP-date.

**Câu 7.** Vì sao phải chú ý `Vary: API-Version` khi cache URI không đổi?

**Đáp án:** Để cache/client biết representation khác nhau theo header; nếu CDN bỏ qua, có thể trả body sai version.

**Câu 8.** `API-Version: 2.0` đã đủ để xác thực người dùng không?

**Đáp án:** Không. Nó chỉ chọn contract. Authentication/authorization/CSRF và business security vẫn độc lập.

## 16. Nguồn tham khảo chính thức

- [Spring Framework 7 — API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html): ApiVersionStrategy, ApiVersionResolver, ApiVersionParser, validation, deprecation.
- [Spring Framework 7 — MVC Config API Version](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-version.html): configureApiVersioning, header/query/path/media resolvers, supported versions.
- [Spring Framework 7 — Request Mapping API Version](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#_api_version): fixed, baseline và unversioned mappings.
- [Spring Framework 7 — ApiVersionConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/config/annotation/ApiVersionConfigurer.html): method signatures.
- [Spring Framework 7 — StandardApiVersionDeprecationHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/accept/StandardApiVersionDeprecationHandler.html): deprecation/sunset/link strategies.
- [Spring Framework 7 — VersionSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/accept/StandardApiVersionDeprecationHandler.VersionSpec.html): setDeprecationDate, setSunsetDate, links.
- [Spring Blog — API Versioning in Spring (2025-09-16)](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): thiết kế và động cơ của tính năng Spring 7.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17+, Spring Framework 7, Servlet baseline.
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, test starter và package thay đổi.
- [RFC 9745 — Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745): cú pháp deprecation và khái niệm deprecated.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594): sunset time và lifecycle hints.

**Kết luận:** từ Spring Framework 7, bạn có thể cấu hình nơi lấy phiên bản qua `ApiVersionConfigurer`, dùng `@RequestMapping(version = "x.y")` hoặc `"x.y+"` để chọn handler, kiểm tra danh sách supported versions, và thông báo vòng đời bằng `StandardApiVersionDeprecationHandler`. Để vận hành tốt, cần thêm compatibility tests, caching/CORS policies, security và một kế hoạch migration/sunset thực sự — không chỉ thêm version annotation rồi bỏ mặc client cũ.
