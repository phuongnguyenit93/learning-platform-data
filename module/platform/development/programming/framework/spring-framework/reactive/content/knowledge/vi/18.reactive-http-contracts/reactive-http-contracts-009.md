# Nhận diện hỗ trợ API versioning theo phiên bản Spring Framework

## 1. Mục tiêu

API versioning là cách một ứng dụng duy trì nhiều phiên bản của **hợp đồng HTTP** trong thời gian chuyển đổi. Client cũ tiếp tục gửi request theo hợp đồng cũ, trong khi client mới sử dụng cấu trúc request/response mới. Ví dụ, API 1.0 trả về status đơn giản; API 2.0 bổ sung currency hoặc thay đổi cách biểu diễn trạng thái.

Điểm cần nhận diện trong Spring WebFlux là **khả năng versioning tích hợp sẵn phụ thuộc phiên bản Spring Framework**:

- Spring Framework 5.x và 6.x cho phép tự xây dựng API versioning bằng các điều kiện mapping, filter, router hoặc logic ứng dụng. Các nhánh này chưa có bộ API versioning first-class như Framework 7.
- **Spring Framework 7.0 trở lên** bổ sung API versioning tích hợp cho cả Spring MVC và Spring WebFlux. Có cấu hình resolver/parser/validation, thuộc tính version trên request mapping, route predicate cho functional endpoints, client support và test support.
- Spring Framework 7.1 đang ở giai đoạn preview tại thời điểm tài liệu này được cập nhật; khi triển khai production cần dùng bản stable phù hợp với Spring Boot và các thư viện trong dự án.

Bài học tập trung vào WebFlux. Các ví dụ native API versioning bên dưới yêu cầu **Spring Framework 7.0+**. Nếu dự án vẫn ở Framework 6.x, không thể chỉ thêm thuộc tính `version` vào `@GetMapping` rồi mong framework tự xử lý.

## 2. Phân biệt ba loại “version”

Trong dự án Spring, từ version có thể chỉ những thứ khác nhau:

1. **Spring Framework version:** phiên bản thư viện nền tảng, ví dụ 6.2.19 hoặc 7.0.10. Nó quyết định API nào có sẵn khi biên dịch và chạy ứng dụng.
2. **Application/API version:** phiên bản hợp đồng mà server công bố cho client, ví dụ API 1.0 và API 2.0. Đây là phiên bản do đội phát triển API thiết kế.
3. **Resource/static asset version:** phiên bản hoặc hash trong URL của JavaScript, CSS, ảnh để cache busting, ví dụ `/assets/app-8f3a.js`. `VersionResourceResolver` xử lý nhóm này, không phải cơ chế versioning cho REST API.

Một ứng dụng chạy Spring Framework 7.0.10 có thể cung cấp API 1.0, 2.0 và 3.0 cùng lúc. Không có quy tắc nào yêu cầu số API phải giống số Spring Framework. Nâng Spring Framework từ 6.2 lên 7.0 cũng không tự động biến API của ứng dụng từ v1 thành v2.

## 3. Ma trận hỗ trợ theo Spring Framework

| Spring Framework | API versioning first-class trong WebFlux | Có thể version API bằng cách tự cấu hình? | Nhận diện |
| --- | --- | --- | --- |
| 5.0–5.3 | Không có `ApiVersionConfigurer` và thuộc tính `version` trên `@RequestMapping` | Có, bằng path/header/query/media type, mapping conditions hoặc filter/router tự viết | Phải tự quản lý version resolution, validation và deprecation |
| 6.0–6.2 | Chưa có bộ API versioning tích hợp của Framework 7 | Có, bằng các cơ chế mapping và routing sẵn có | Không dùng được native `configureApiVersioning` hoặc `@GetMapping(version=...)` |
| 7.0.x | Có, cho MVC và WebFlux | Có; nên ưu tiên hạ tầng native khi phù hợp | Có `ApiVersionStrategy`, resolver/parser, mapping version, validation và deprecation |
| 7.1.x | Kế thừa nền tảng native của 7.0; xem trạng thái stable/preview trước khi nâng cấp | Có | Kiểm tra release notes và compatibility của bản đang dùng |

**Mốc quan trọng là 7.0.** Javadoc của `ApiVersionConfigurer` ghi rõ API này được giới thiệu từ Spring Framework 7.0. Release notes 7.0 cũng xác nhận MVC và WebFlux có first-class support cho API versioning.

Tại thời điểm cập nhật bài học (08-11-2026), tài liệu Spring liệt kê Framework 7.0.10 là bản stable và 7.1.0-RC2 là bản preview. Số patch thay đổi theo thời gian; hãy xem trang release/version chính thức trước khi chọn dependency.

### 3.1. Vì sao Framework 6.x vẫn có thể version API?

Versioning không phải khả năng chỉ Spring mới có. HTTP request đã có path, query string, headers và media type. Spring Framework 6.x có các điều kiện mapping như:

- `path`: tạo route riêng như `/api/v1/orders` và `/api/v2/orders`.
- `headers`: chỉ khớp khi header có giá trị nhất định.
- `params`: chỉ khớp khi query parameter có giá trị nhất định.
- `produces`: chọn handler theo media type mà client chấp nhận.

Những cơ chế này đủ để xây dựng routing theo phiên bản. Điều còn thiếu là **một bộ quản lý version dùng chung**: chuẩn hóa cách lấy version, parse và so sánh version, xác thực danh sách version hỗ trợ, áp dụng default, chọn mapping theo baseline, phát thông báo deprecation và cấu hình tương ứng cho client/test.

Đây là khác biệt giữa “có thể tự triển khai API versioning” và “Framework có API versioning first-class”.

## 4. API versioning native trong Framework 7.0 gồm những gì?

Framework 7.0 bổ sung các thành phần phối hợp với nhau:

| Thành phần | Vai trò |
| --- | --- |
| `ApiVersionStrategy` | Điều phối cách resolve, parse, validate và thông báo deprecation |
| `ApiVersionResolver` | Lấy giá trị version từ request |
| `ApiVersionParser` | Chuyển chuỗi version thành dạng có thể so sánh |
| `ApiVersionConfigurer` | Cấu hình resolver, parser, default và supported versions |
| `ApiVersionDeprecationHandler` | Gửi thông tin version đã deprecated qua response headers |
| `@RequestMapping(version=...)` | Chọn annotated controller method theo version |
| `version(...)` predicate | Chọn functional route theo version |

Ứng dụng thường cấu hình qua `WebFluxConfigurer.configureApiVersioning(...)` hoặc Spring Boot properties. Sau khi cấu hình, `ApiVersionStrategy` được WebFlux sử dụng trong quá trình mapping request. Phần lớn controller không cần tự gọi strategy.

Native support áp dụng cho cả:

- Annotated controllers: `@RequestMapping`, `@GetMapping`, `@PostMapping` và các annotation chuyên biệt khác.
- Functional endpoints: `RouterFunction` với request predicate `version(...)`.
- Client: `WebClient`, `RestClient` và HTTP Service clients.
- Testing: `WebTestClient`; Spring MVC cũng có hỗ trợ tương ứng trong MockMvc.

## 5. Chọn nơi đặt API version trong request

Không có một chuẩn HTTP duy nhất bắt buộc mọi API phải đặt version ở cùng một vị trí. Framework 7.0 có các resolver tích hợp:

| Cách truyền | Request ví dụ | Cấu hình WebFlux | Đặc điểm |
| --- | --- | --- | --- |
| Header | `X-API-Version: 2.0` | `useRequestHeader("X-API-Version")` | URL không đổi; cần cấu hình cache/proxy để xét header version |
| Query parameter | `?apiVersion=2.0` | `useQueryParam("apiVersion")` | Dễ thử bằng browser/curl; version xuất hiện trong URL và cache key |
| Path segment | `/api/v2/orders/42` | `usePathSegment(index)` | Dễ đọc, dễ route/cache; version trở thành một phần URL |
| Media type parameter | `Accept: application/json;version=2.0` | `useMediaTypeParameter(...)` | Gắn version với representation; client và content negotiation phức tạp hơn |
| Custom resolver | Theo contract của ứng dụng | `useVersionResolver(...)` | Dùng khi quy tắc lấy version đặc thù |

### 5.1. Version trong header

Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
X-API-Version: 2.0
Accept: application/json
```

Header phù hợp khi muốn giữ một URL ổn định và version là metadata của API contract. Khi sử dụng CDN, reverse proxy hoặc cache HTTP, cần bảo đảm cache key xét header version; nếu không, response v1 có thể bị dùng nhầm cho request v2.

### 5.2. Version trong path

Ví dụ:

```http
GET /api/v2/orders/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Đối với path resolver, bạn chỉ định index bắt đầu từ 0 của segment chứa version. Path phải khai báo URI variable, ví dụ `/api/{version}/orders`. Nếu path segment không tồn tại hoặc không hợp lệ, resolver có thể phát `InvalidApiVersionException`. Có thể cấu hình predicate để xác định path nào thực sự có version.

Path version dễ quan sát và cache, nhưng cần quy hoạch URL và có thể tạo nhiều route public cho cùng resource.

### 5.3. Version trong query parameter

Ví dụ:

```http
GET /api/orders/42?apiVersion=2.0 HTTP/1.1
```

Query parameter thuận tiện cho thử nghiệm và client đơn giản. Tuy nhiên, cần giữ tên parameter thống nhất, xử lý khi client gửi nhiều giá trị, và bảo đảm proxy/cache không bỏ qua parameter khi tạo cache key.

### 5.4. Version trong media type parameter

Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Accept: application/json;version=2.0
```

Cách này biểu đạt rằng client muốn một phiên bản cụ thể của representation. Cấu hình resolver chỉ rõ media type tương thích và tên parameter. Không nhầm version parameter với MIME subtype riêng như `application/vnd.example.order-v2+json`; hai chiến lược có thể cùng xuất hiện nhưng là hai contract khác nhau.

### 5.5. Khi nào cần custom resolver?

Nếu version đến từ một gateway header đã chuẩn hóa, một token claim hoặc một quy tắc routing đặc biệt, có thể triển khai `ApiVersionResolver`. Resolver nên:

- Trả về một giá trị version rõ ràng hoặc trạng thái không có version theo contract.
- Không tự truy vấn database hoặc gọi network blocking khi resolve request.
- Xử lý giá trị thiếu/sai theo một quy tắc nhất quán.
- Không tin dữ liệu version như một thông tin xác thực hay phân quyền.
- Được kiểm thử cho cả request hợp lệ, thiếu version và version không hỗ trợ.

Nếu cấu hình nhiều resolver, thứ tự resolver có ý nghĩa. Khi cần kết hợp header và query parameter, hãy cấu hình thứ tự rõ ràng bằng Java config thay vì giả định thứ tự từ nhiều property độc lập.

## 6. Cấu hình API versioning trong Spring WebFlux 7.0

### 6.1. Cấu hình bằng WebFluxConfigurer

Ví dụ dùng request header:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.ApiVersionConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiVersioningConfiguration implements WebFluxConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("X-API-Version");
        configurer.addSupportedVersions("1.0", "2.0");
    }
}
```

Điểm cần hiểu:

- `configureApiVersioning` là callback được thêm trong Framework 7.0.
- `useRequestHeader` chọn header dùng để resolve version.
- `addSupportedVersions` khai báo version được chấp nhận.
- Mặc định, Framework có thể tự phát hiện version được khai báo trong controller mappings. Nếu muốn chỉ dùng danh sách version khai báo tường minh, có thể tắt phát hiện version từ mapping bằng `detectSupportedVersions(false)` rồi khai báo danh sách hỗ trợ.
- Khi bật version resolver, version request mặc định là bắt buộc. Có thể thay đổi bằng default version hoặc cấu hình required theo API của Framework 7.0.

Không cần gọi trực tiếp `ApiVersionStrategy` trong từng controller. Hãy để cấu hình WebFlux quản lý strategy chung.

### 6.2. Cấu hình bằng Spring Boot properties

Trong Spring Boot có tích hợp API versioning của Framework 7, có thể cấu hình bằng properties:

```properties
spring.webflux.apiversion.use.header=X-API-Version
```

Nếu muốn request thiếu header dùng một version mặc định:

```properties
spring.webflux.apiversion.default=1.0
spring.webflux.apiversion.use.header=X-API-Version
```

Tương đương YAML:

```yaml
spring:
  webflux:
    apiversion:
      default: 1.0
      use:
        header: X-API-Version
```

Spring Boot cũng có các thuộc tính cho resolver query parameter, path segment và media type parameter. Nếu cần nhiều resolver hoặc thứ tự tùy chỉnh, dùng `WebFluxConfigurer`.

**Chú ý tương thích:** các property `spring.webflux.apiversion.*` thuộc cấu hình Spring Boot có hỗ trợ API versioning của Framework 7. Không sao chép property này vào dự án Boot 3.x đang quản lý Framework 6.x rồi kỳ vọng nó tự hoạt động; hãy kiểm tra dependency tree và tài liệu đúng phiên bản Boot.

### 6.3. Chọn default và version required

Khi API versioning được bật:

- Mặc định request cần cung cấp version; nếu thiếu, Framework phát `MissingApiVersionException` và trả 400.
- Có thể cấu hình default version để request không gửi version được gán một giá trị mặc định.
- Có thể cho phép request không có version; khi đó cần thiết kế mapping không version và mapping version cụ thể sao cho kết quả rõ ràng.
- Nếu dùng default, hãy ghi rõ version mặc định trong API contract và tài liệu client.

Không tự ý dùng version mới nhất làm default chỉ vì nó mới hơn. Client cũ không có header có thể nhận representation thay đổi ngoài ý muốn. Một default ổn định hoặc yêu cầu client gửi version tường minh thường dễ kiểm soát hơn.

## 7. Mapping controller method theo version

Sau khi bật resolver, có thể khai báo version trên `@RequestMapping` hoặc các annotation chuyên biệt.

### 7.1. Fixed version

Ví dụ hai method cùng path:

```java
@GetMapping(path = "/{id}", version = "1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    return Mono.just(new OrderV1(id, "PAID"));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}
```

Hai method cùng xử lý path nhưng chỉ được chọn khi version request tương ứng. Đây là cách phù hợp khi version 2 có representation hoặc semantics khác version 1.

### 7.2. Baseline version

Một mapping có version `1.2+` là **baseline mapping**: nó hỗ trợ version 1.2 và các version cao hơn trong tập version được hỗ trợ, cho đến khi có mapping cụ thể hơn được chọn.

Ví dụ:

```java
@GetMapping(path = "/{id}", version = "1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    return Mono.just(new OrderV1(id, "PAID"));
}

@GetMapping(path = "/{id}", version = "1.2+")
public Mono<OrderV2> getFromV1_2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(new OrderV2(id, "PAID", "VND"));
}
```

Baseline giúp một method tiếp tục phục vụ các version mới hơn khi contract vẫn tương thích, giảm việc phải nhân bản controller method cho mọi version.

Cần nhớ rằng baseline không tự làm cho mọi số version trở thành hợp lệ. Request version vẫn phải nằm trong tập supported versions theo cấu hình hoặc mapping.

### 7.3. Mapping không khai báo version

Một method không có thuộc tính version được xem là có thể match mọi version, nhưng sẽ có độ ưu tiên thấp hơn mapping version cụ thể. Đây là cách giữ một endpoint tương thích với client cũ trong lúc đã có handler version mới.

Ví dụ khái niệm:

```java
@GetMapping("/{id}")
public Mono<LegacyOrder> getLegacy(@PathVariable String id) {
    return Mono.just(loadLegacyOrder(id));
}

@GetMapping(path = "/{id}", version = "2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    return Mono.just(loadOrderV2(id));
}
```

Đây là mã minh họa, các hàm load do ứng dụng định nghĩa. Nếu request version 2.0, mapping cụ thể 2.0 được ưu tiên. Với request không version, kết quả còn phụ thuộc cấu hình required/default; hãy kiểm thử rõ thay vì suy đoán.

### 7.4. Cách Framework chọn mapping

| Mapping đã khai báo | Request version | Kết quả |
| --- | --- | --- |
| `1.0` | `1.0` | Match fixed version 1.0 |
| `1.0` | `2.0` | Không match |
| `1.2+` | `1.2` | Match baseline |
| `1.2+` | `1.5` | Match nếu 1.5 là supported version |
| Không khai báo version | Version bất kỳ | Có thể match, nhưng bị mapping cụ thể ưu tiên |
| `2.0` và `1.2+` | `2.0` | Mapping fixed 2.0 cụ thể được ưu tiên |
| Chỉ có `1.2+` | `1.1` | Không match baseline |
| Có fixed version cao hơn nhưng request vượt version đó | Ví dụ request 1.6 trong khi mapping fixed cao nhất là 1.5 và baseline thấp hơn | Có thể không có mapping phù hợp; Framework trả lỗi version không chấp nhận |

Ví dụ chi tiết theo tài liệu Framework: nếu mapping có version 1.1, baseline 1.2+ và fixed 1.5, request 1.3 chọn baseline 1.2+; request 1.5 chọn fixed 1.5. Request 1.6 không tự động dùng baseline 1.2+ vì mapping fixed 1.5 có mức ưu tiên cao hơn nhưng không match request. Vì vậy phải thiết kế tập mapping và supported versions có chủ đích.

## 8. Semantic version parser và validation

### 8.1. Parse version để so sánh đúng

Mặc định Framework dùng parser semantic version. Version được tách thành major, minor và patch để so sánh theo số, thay vì so sánh chuỗi từ điển.

| Version A | Version B | Kết quả so sánh |
| --- | --- | --- |
| `1.2` | `1.10` | 1.2 nhỏ hơn 1.10 |
| `2.0` | `1.9.9` | 2.0 lớn hơn 1.9.9 |
| `1.2` | `1.2.0` | Thành phần thiếu được hiểu là 0 theo semantic parser |
| `2.0.1` | `2.0` | 2.0.1 lớn hơn 2.0 |

Không dùng `String.compareTo` để tự quyết định version nếu version có thành phần số. So sánh chuỗi có thể cho kết quả sai, ví dụ chuỗi "1.10" đứng trước "1.2" theo thứ tự từ điển.

### 8.2. Version theo ngày hoặc định dạng riêng

Nếu tổ chức dùng version theo ngày, ví dụ `2026-11`, hoặc một quy tắc riêng, có thể cấu hình custom `ApiVersionParser`. Parser phải tạo ra kiểu có thứ tự so sánh nhất quán và xử lý input không hợp lệ.

Đừng chuyển parser sang định dạng tùy chỉnh chỉ để đáp ứng một client. Chọn một format đơn giản, ghi rõ trong tài liệu API và giữ ổn định qua thời gian.

### 8.3. Supported versions được xác định thế nào?

Theo mặc định, Framework có thể lấy version từ các giá trị được khai báo trong controller mappings. Cách này tiện khi version 1.0 và 2.0 xuất hiện trực tiếp trong mapping.

Nếu muốn danh sách supported versions tường minh:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("X-API-Version");
    configurer.detectSupportedVersions(false);
    configurer.addSupportedVersions("1.0", "2.0", "2.1");
}
```

Khi đã tắt auto detection, danh sách explicit phải đầy đủ. Nếu một version đầu tiên chưa được khai báo trong mapping nhưng được dùng làm default, hãy thêm nó vào supported versions theo cấu hình phù hợp.

### 8.4. Lỗi version thiếu, không hợp lệ hoặc không có mapping

Các trường hợp quan trọng:

- Không gửi version khi version là required: `MissingApiVersionException`, thường HTTP 400.
- Gửi version chưa được hỗ trợ: `InvalidApiVersionException`, HTTP 400.
- Version hợp lệ nhưng không có mapping tương thích: có thể nhận `NotAcceptableApiVersionException`, HTTP 400.
- Gửi version hợp lệ và có mapping: controller method phù hợp được gọi.

Hãy phân biệt lỗi version với lỗi business. Một API version không được hỗ trợ là lỗi contract/routing, không phải lỗi “resource không tồn tại” 404.

## 9. Deprecation và vòng đời phiên bản

Versioning không chỉ là giữ nhiều controller method. API còn cần một chính sách thông báo và ngừng hỗ trợ phiên bản cũ.

Framework 7.0 cung cấp `ApiVersionDeprecationHandler`. Handler mặc định `StandardApiVersionDeprecationHandler` có thể thêm các response headers:

- `Deprecation`: thông báo version đã bị deprecated.
- `Sunset`: thông tin thời điểm version dự kiến ngừng phục vụ.
- `Link`: liên kết tới tài liệu hoặc hướng dẫn chuyển đổi.

Các header được mô tả theo RFC 9745 (Deprecation) và RFC 8594 (Sunset). Ứng dụng có thể cấu hình handler tùy chỉnh nếu cần schema hoặc chính sách khác.

Quy trình vận hành nên có các bước:

1. Phát hành version mới và duy trì version cũ trong thời gian chuyển đổi.
2. Đánh dấu version cũ deprecated khi đã có kế hoạch ngừng.
3. Gửi thông tin deprecation/sunset trong response để client có thể chủ động di chuyển.
4. Theo dõi số lượng request theo version và client còn sử dụng.
5. Thông báo lịch ngừng hỗ trợ qua tài liệu/channels phù hợp.
6. Chỉ gỡ mapping cũ sau khi đã đánh giá tác động và hoàn tất chính sách tương thích.

Không gắn deprecation header chỉ để “thử cho vui”. Thời điểm sunset phải phản ánh cam kết thực tế của đội vận hành.

## 10. Functional endpoints trong WebFlux

API versioning không chỉ dành cho annotated controllers. Với functional endpoints, sau khi cấu hình WebFlux versioning, có thể thêm predicate `version(...)` vào route:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.RequestPredicates.version;

@Configuration(proxyBeanMethods = false)
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return route()
                .GET("/api/orders/{id}", version("1.0"), handler::getV1)
                .GET("/api/orders/{id}", version("2.0"), handler::getV2)
                .build();
    }
}
```

Đây là cấu hình route minh họa; `OrderHandler` cần cung cấp hai method trả `Mono<ServerResponse>` tương ứng. Version predicate hỗ trợ fixed version như 1.2 và baseline như 1.2+.

Điểm quan trọng: phải bật API versioning trong WebFlux Config trước. Nếu không có ApiVersionStrategy, predicate version không thể resolve version request theo contract mà bạn mong muốn.

## 11. Client support và kiểm thử

### 11.1. WebClient và RestClient

Framework 7.0 cung cấp `ApiVersionInserter` để client biết cách thêm version vào request. Ví dụ WebClient có thể cấu hình inserter dùng header một lần, sau đó request chỉ cần chỉ định version cần gọi.

Ý tưởng:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://localhost:8080")
        .apiVersionInserter(
                ApiVersionInserter.useHeader("X-API-Version"))
        .build();
```

Sau đó client gọi API với version tương ứng bằng API version client support. `RestClient` và HTTP Service clients cũng có hỗ trợ tương tự. Tên resolver phía client nên khớp contract phía server.

Nếu không dùng API inserter, client vẫn có thể set header/query/path thủ công. Inserter giúp tránh lặp lại logic đặt version ở từng request.

### 11.2. WebTestClient

Với test WebFlux, có thể gửi version bằng header để kiểm tra từng mapping. Ví dụ:

```java
client.get()
        .uri("/api/orders/42")
        .header("X-API-Version", "1.0")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("PAID");
```

Khi dùng ApplicationContext setup, WebTestClient có thể dùng cấu hình API versioning của context. Nếu test ở standalone setup, cần cung cấp ApiVersionStrategy và cấu hình client inserter phù hợp. Không giả định test client tự biết cách thêm version nếu chưa cấu hình.

### 11.3. Các tình huống test cần có

- Version 1.0 gọi đúng handler và đúng response schema.
- Version 2.0 gọi đúng handler và trả field mới.
- Request thiếu version trả status theo policy required/default.
- Version không hỗ trợ bị từ chối.
- Version hợp lệ nhưng không có mapping tương thích bị xử lý đúng.
- Baseline mapping hoạt động với từng supported version.
- Mapping không version không vô tình che mapping version cụ thể.
- Deprecation headers xuất hiện đúng với version đã đánh dấu.
- WebClient/HTTP Service client gửi đúng header/query/path.
- WebTestClient test cả version hợp lệ lẫn lỗi version.

## 12. Ví dụ Spring Boot WebFlux hoàn chỉnh với Framework 7.0+

Ví dụ sau dùng Java 17+, Spring Boot 4.x tương thích Spring Framework 7.0+, và API version được truyền qua header `X-API-Version`. Dự án không cần database; dữ liệu minh họa được tạo trong controller.

### 12.1. Dependency

Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dự án cần Spring Boot plugin và dependency management phù hợp. Dùng BOM của Boot 4.x để chọn Spring Framework 7.x đồng bộ; không override riêng spring-webflux bằng một version khác với Framework core.

### 12.2. Cấu hình application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.webflux.apiversion.use.header=X-API-Version
```

Cấu hình này làm cho header X-API-Version là nguồn version của request. Khi đã bật resolver, version mặc định là bắt buộc nếu không cấu hình default.

### 12.3. Application class

Tệp `src/main/java/demo/ApiVersioningApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiVersioningApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiVersioningApplication.class, args);
    }
}
```

### 12.4. Controller với hai phiên bản

Tệp `src/main/java/demo/OrderController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(path = "/{id}", version = "1.0")
    public Mono<OrderV1> getV1(@PathVariable String id) {
        return Mono.just(new OrderV1(id, "PAID"));
    }

    @GetMapping(path = "/{id}", version = "2.0")
    public Mono<OrderV2> getV2(@PathVariable String id) {
        return Mono.just(new OrderV2(id, "PAID", "VND"));
    }

    public record OrderV1(String id, String status) {
    }

    public record OrderV2(
            String id,
            String status,
            String currency) {
    }
}
```

Cả hai method cùng xử lý path `/api/orders/{id}`. Request version 1.0 nhận representation `OrderV1`; request version 2.0 nhận `OrderV2` có thêm currency. Hai method trả Mono, nên controller vẫn tuân thủ WebFlux reactive return type.

### 12.5. Test bằng WebTestClient

Tệp `src/test/java/demo/OrderControllerTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(
        controllers = OrderController.class,
        properties = "spring.webflux.apiversion.use.header=X-API-Version")
class OrderControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void version10SelectsV1Representation() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "1.0")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.status").isEqualTo("PAID")
                .jsonPath("$.currency").doesNotExist();
    }

    @Test
    void version20SelectsV2Representation() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "2.0")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.status").isEqualTo("PAID")
                .jsonPath("$.currency").isEqualTo("VND");
    }

    @Test
    void missingVersionIsRejected() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unsupportedVersionIsRejected() {
        client.get()
                .uri("/api/orders/42")
                .header("X-API-Version", "3.0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Test sử dụng ApplicationContext WebFlux test slice và property version resolver. Không cần dựng server thật. Chạy bằng:

```bash
./gradlew test
```

Nếu dự án bật Spring Security hoặc có filter tùy chỉnh, cấu hình test slice tương ứng để các filter đó không che mất kết quả của API version mapping.

### 12.6. Gọi bằng curl

Khởi động ứng dụng:

```bash
./gradlew bootRun
```

Request version 1.0:

```bash
curl -i -H "X-API-Version: 1.0" http://localhost:8080/api/orders/42
```

Body JSON chính:

```json
{
  "id": "42",
  "status": "PAID"
}
```

Request version 2.0:

```bash
curl -i -H "X-API-Version: 2.0" http://localhost:8080/api/orders/42
```

Body JSON chính:

```json
{
  "id": "42",
  "status": "PAID",
  "currency": "VND"
}
```

Request không gửi header hoặc gửi version 3.0 không được hỗ trợ sẽ nhận HTTP 400 theo cấu hình ví dụ.

## 13. Làm API versioning trên Framework 6.x

Nếu dự án đang ở Spring Framework 6.x, vẫn có thể version endpoint bằng các điều kiện mapping đã có. Ví dụ dùng header:

```java
@RestController
@RequestMapping("/api/orders")
public class LegacyOrderController {

    @GetMapping(path = "/{id}", headers = "X-API-Version=1.0")
    public Mono<OrderV1> getV1(@PathVariable String id) {
        return Mono.just(new OrderV1(id, "PAID"));
    }

    @GetMapping(path = "/{id}", headers = "X-API-Version=2.0")
    public Mono<OrderV2> getV2(@PathVariable String id) {
        return Mono.just(new OrderV2(id, "PAID", "VND"));
    }
}
```

Đây là cách tự định tuyến theo giá trị header. Các biến thể khác:

```java
@GetMapping(path = "/{id}", params = "apiVersion=1.0")
public Mono<OrderV1> getV1(@PathVariable String id) {
    // ...
}

@GetMapping(path = "/{id}", params = "apiVersion=2.0")
public Mono<OrderV2> getV2(@PathVariable String id) {
    // ...
}
```

Hoặc tách URL:

```java
@GetMapping("/v1/orders/{id}")
public Mono<OrderV1> getV1(@PathVariable String id) {
    // ...
}

@GetMapping("/v2/orders/{id}")
public Mono<OrderV2> getV2(@PathVariable String id) {
    // ...
}
```

Các đoạn trên là mẫu routing, phần body nghiệp vụ được lược bỏ. Trên Framework 6.x, những mapping này có thể hoạt động, nhưng **không có** native thuộc tính `version` của `@RequestMapping` hay callback `configureApiVersioning`.

### 13.1. Những phần phải tự quản lý trên 6.x

Nếu tự triển khai, ứng dụng cần quyết định và kiểm soát:

- Resolver lấy version từ header, query, path hay media type.
- Parser và quy tắc so sánh version; tránh so sánh chuỗi sai.
- Danh sách supported versions và hành vi với version thiếu/không hợp lệ.
- Mapping baseline và fallback cho client cũ.
- Default version và chính sách deprecation.
- Response headers thông báo deprecation/sunset.
- Client helper để gửi đúng version.
- Test cases cho mọi version, missing, unsupported và mapping conflict.

Có thể gom logic vào WebFilter, custom HandlerMapping/RequestCondition, router predicate hoặc một thư viện riêng. Tuy nhiên, không nên rải logic parse header/version trong từng controller vì rất dễ không nhất quán.

### 13.2. Vì sao không override Framework 7 vào dự án Boot 3?

Spring Boot quản lý một tập dependency tương thích với nhau. Boot 3.x được xây dựng trên các thế hệ Spring Framework 6.x; API versioning native yêu cầu Framework 7.0+. Chỉ override dependency `spring-webflux` hoặc `spring-web` lên 7.0 trong khi các module Spring khác vẫn 6.x có thể tạo classpath không đồng bộ và lỗi runtime.

Nếu muốn native support, hãy nâng cấp theo bộ phiên bản Spring Boot/Framework được hỗ trợ cùng nhau. Nếu chưa thể nâng cấp, giữ giải pháp routing thủ công trên Framework 6.x và viết test đầy đủ.

## 14. Các lỗi thường gặp khi nhận diện version support

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| Nghĩ Framework 6.2 có `@GetMapping(version=...)` | Thuộc tính mapping version thuộc Framework 7.0+ | Kiểm tra Spring Framework dependency trước khi dùng |
| Nghĩ API versioning chỉ có trong MVC | Framework 7.0 hỗ trợ cả MVC và WebFlux | Dùng WebFluxConfigurer cho reactive stack |
| Nghĩ chỉ cần thêm header là Framework tự hiểu version | Phải cấu hình resolver trước | Cấu hình ApiVersionConfigurer hoặc Boot property |
| Nghĩ mọi version chuỗi đều được chấp nhận | Framework xác thực supported versions | Khai báo mapping hoặc supported list |
| Nghĩ baseline 1.2+ tự chấp nhận mọi version tương lai | Version phải thuộc tập supported versions và mapping phải phù hợp | Quản lý supported versions và test version boundary |
| Nghĩ version không gửi luôn dùng version mới nhất | Hành vi phụ thuộc required/default/mapping | Cấu hình default hoặc required rõ ràng |
| Nghĩ `@RequestMapping(version=...)` thay thế path/header/query | Mapping version chỉ hoạt động sau khi resolver biết lấy version ở đâu | Cấu hình strategy và mapping cùng nhau |
| Dùng chuỗi version không theo thứ tự số | Có thể so sánh sai | Dùng semantic parser hoặc parser riêng |
| Dùng API version để biểu diễn mọi lần deploy | Tạo nhiều version không cần thiết | Chỉ tăng version khi thay đổi contract cần tương thích riêng |
| Coi version API là version thư viện Spring | Hai version độc lập | Ghi rõ Framework version và API version trong tài liệu |
| Nghĩ `VersionResourceResolver` là REST API versioning | Nó version static resource URL/cache | Dùng ApiVersionStrategy cho API contract |
| Bật nhiều resolver mà không định nghĩa ưu tiên | Có thể resolve version từ nguồn khác nhau ngoài ý muốn | Cấu hình thứ tự bằng Java config |
| Nâng Framework riêng lẻ trong Boot cũ | Có thể lệch version các module Spring | Nâng cấp theo BOM/compatibility matrix |

## 15. Checklist khi nâng cấp hoặc thiết kế API versioning

1. **Đọc phiên bản thật:** xem dependency tree hoặc BOM để biết Spring Framework/WebFlux đang chạy ở nhánh 5.x, 6.x hay 7.x.
2. **Kiểm tra API native:** chỉ dùng `ApiVersionConfigurer` và thuộc tính `@RequestMapping(version=...)` khi dự án có Framework 7.0+.
3. **Chọn resolver:** header, query, path, media type hoặc custom; ghi rõ contract cho client.
4. **Chọn parser:** semantic version mặc định hay format riêng; không so sánh chuỗi tùy tiện.
5. **Khai báo supported versions:** dùng auto detection từ mappings hoặc danh sách tường minh.
6. **Quyết định missing version:** required hay default; không để client cũ bị chuyển sang contract mới ngoài dự kiến.
7. **Thiết kế mapping:** fixed version, baseline và fallback không version; test ưu tiên mapping.
8. **Lập chính sách deprecation:** thông báo client, thời gian sunset, Link và đo lượng request còn dùng version cũ.
9. **Cấu hình client:** WebClient, RestClient, HTTP Service clients phải gửi version đúng resolver.
10. **Kiểm thử:** version hợp lệ, missing, unsupported, baseline, no-match, deprecation và content contract.
11. **Kiểm tra cache/proxy:** nếu version ở header, bảo đảm cache key phân biệt version.
12. **Nâng cấp đồng bộ:** dùng phiên bản Spring Boot/Framework tương thích; không chỉ thay riêng một JAR.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework 7.0 – API Versioning trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-versioning.html): ApiVersionStrategy, resolver, parser, validation và deprecation.
- [Spring Framework 7.0 – WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình `configureApiVersioning`, resolver và supported versions.
- [Spring Framework 7.0 – Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): thuộc tính `version`, fixed version, baseline version và cách chọn mapping.
- [Spring Framework 7.0 – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): predicate `version(...)` cho RouterFunction.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): property `spring.webflux.apiversion.*` và cấu hình versioning cho WebFlux.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): xác nhận first-class API versioning cho MVC và WebFlux.
- [Spring Framework 6.2 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes): đối chiếu các thay đổi của nhánh 6.2.
- [API Versioning in Spring](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): lý do bổ sung feature, server/client/testing support và ví dụ tổng quan.
- [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): nhánh stable, thời gian hỗ trợ và hướng nâng cấp.

## 17. Ghi nhớ

**API versioning native trong Spring WebFlux bắt đầu từ Spring Framework 7.0.** Trên Framework 7.0+, cấu hình resolver bằng `WebFluxConfigurer.configureApiVersioning` hoặc Boot properties, sau đó dùng `@RequestMapping(version=...)` cho annotated controllers hoặc `version(...)` cho functional routes. Framework hỗ trợ resolve, parse, validate, supported versions, client integration, WebTestClient và thông báo deprecation.

Trên Framework 5.x/6.x, vẫn có thể version API bằng path, header, query parameter hoặc media type thông qua các điều kiện mapping sẵn có; ứng dụng phải tự quản lý quy tắc version, validation, fallback và deprecation. Đừng nhầm version của Spring Framework với version của API ứng dụng. Hãy kiểm tra dependency thật trước khi chọn cách triển khai, và chỉ nâng Framework theo bộ tương thích Spring Boot/BOM.
