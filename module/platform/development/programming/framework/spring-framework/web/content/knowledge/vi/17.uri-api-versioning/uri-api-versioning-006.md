# Chiến lược phiên bản API theo đường dẫn, header, tham số hoặc media type trong Spring MVC

## 1. Tại sao cần phiên bản API?

Một ứng dụng web, mobile hoặc đối tác có thể phụ thuộc vào hợp đồng REST API trong nhiều năm. Nếu một endpoint đã trả:

~~~http
GET /api/v1/customers/42 HTTP/1.1
Accept: application/json
~~~

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

mà server bất ngờ thay JSON thành:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

thì client cũ có thể không đọc được `fullName` nữa. **API versioning** giúp nhóm thay đổi không tương thích thành những contract có thể được client chọn, đồng thời hỗ trợ v1 và v2 trong một giai đoạn chuyển tiếp.

Chủ đề của bài là **bốn nơi có thể biểu thị phiên bản**:
1. **Đường dẫn URI:** `/api/v1/customers/42`.
2. **Request header:** `API-Version: 1`.
3. **Query parameter:** `/api/customers/42?version=1`.
4. **Media type:** `Accept: application/vnd.demo.customer.v1+json` hoặc tham số media type.

Mỗi lựa chọn ảnh hưởng routing, API documentation, cache key, CORS, proxy, client SDK và cách gỡ lỗi. Không có phương án luôn tốt nhất. **Phiên bản API không đồng nghĩa với phiên bản JAR, Spring Boot, database migration hoặc Git tag.** Một lần deploy có thể phục vụ nhiều API versions; một API version có thể tồn tại qua nhiều lần deploy.

### Bạn sẽ học gì?

- Phân biệt breaking vs non-breaking changes và chính sách nâng phiên bản.
- So sánh path, header, query param, media type theo HTTP semantics.
- Cấu hình `@GetMapping`/`@RequestMapping` trên **Spring MVC 6.x** và kiểm thử trên **Spring Boot 3.3.5 / Java 17**.
- Phân biệt `Accept` với `Content-Type`, `produces` với `consumes`, mapping conditions với parameter binding.
- Hiểu **Spring Framework 7** có API versioning native (`ApiVersionConfigurer`, `version` trong mapping) nhưng **không có ở Spring 6.x**.
- Xác định behavior khi thiếu/không hỗ trợ version, 400/404/406/415, response errors và contract tests.
- Quản lý CDN caching, `Vary`, CORS preflight, authorization, migration/deprecation/sunset.

Bài tập trung **Spring MVC Servlet stack**, không phải Spring WebFlux. Khi chuyển version framework, luôn kiểm tra đúng tài liệu cho Spring Framework/Spring Boot đang được dependency manager sử dụng.

## 2. API contract bao gồm những gì?

Một hợp đồng API không chỉ là field JSON. Nó còn bao gồm:
- Resource URI, path variable, HTTP method và ý nghĩa hành động.
- Request query/header/body, content type, validation, required/default values.
- Response field name, kiểu, nullability, collection envelope, timestamps, pagination, sort.
- HTTP statuses, error codes, retry/idempotency rules.
- Authentication/authorization, ownership/tenant, CORS/CSRF và bảo vệ dữ liệu.
- Business semantics: tỷ giá nào, làm tròn ra sao, filter thế nào, dữ liệu tại thời điểm nào.
- Hành vi vận hành có thể là hợp đồng: rate limit, max page size, deprecation date.

Bởi vậy đổi field `fullName` là một breaking change dễ thấy, nhưng đổi page index từ zero-based sang one-based cũng có thể phá client ngay cả khi JSON schema giống nhau.

| Thay đổi | Đánh giá thường gặp | Vì sao |
| --- | --- | --- |
| Thêm JSON field optional | Thường tương thích | Nhưng strict deserializer có thể không chấp nhận |
| Rename/remove field | Breaking | Client cũ không thấy thuộc tính |
| Đổi số thành chuỗi | Breaking hoặc rủi ro cao | Kiểu/format thay đổi |
| Thêm enum value | Có thể breaking | Client exhaustive switch có thể lỗi |
| Thêm endpoint mới | Thường tương thích | Không ảnh hưởng endpoint cũ nếu không conflict |
| Đổi default sort/filter/page size | Có thể breaking | Behavior khác |
| Thay 200 + body bằng 204 | Có thể breaking | Client đang parse body |
| Bắt buộc request header mới | Breaking | Client cũ không gửi |
| Tối ưu truy vấn, thay thư viện nội bộ | Thường không | Nếu output/semantics không đổi |
| Vá lỗ hổng phân quyền v1 | Có thể ảnh hưởng | Không duy trì lỗ hổng chỉ để tương thích |

**Không nhất thiết bump major API version cho mỗi thêm field**; dùng contract tests và danh sách consumer thực tế để xác định. Ngược lại, tăng con số v2 không tự động khiến v2 đúng về security và hành vi nghiệp vụ.

### 2.1. Chọn cách biểu diễn version

Có API dùng `1`/`2`, có API dùng `1.0`/`1.1`, có API dựa ngày như `2026-10-01`. Cần quy định format, parser, cách so sánh, các version được hỗ trợ và ý nghĩa major/minor. Không so sánh `1.10` và `1.9` như số thực, và không vừa dùng `v1` ở header, `1.0` ở URL mà thiếu quy tắc mapping rõ ràng.

## 3. So sánh bốn phương án

| Tiêu chí | Path | Header | Query param | Media type |
| --- | --- | --- | --- | --- |
| Ví dụ | `/api/v1/orders` | `API-Version: 1` | `?version=1` | `Accept: application/vnd.demo.v1+json` |
| Version thấy trực tiếp trong URL | Có | Không | Có | Không |
| Thử bằng browser URL thuần | Dễ | Cần thiết lập header | Dễ | Cần thiết lập Accept |
| Gateway/LB route theo version | Rất thuận tiện | Phải giữ/đọc header | Phải giữ query param | Phải đọc Accept |
| Cache key theo URI thông thường | Tách path | Cần `Vary`/CDN key | Query thuộc URI | Cần `Vary: Accept` |
| Browser CORS custom header | Không do version | Có thể trigger preflight | Không do version | Thường ít hơn với Accept hợp lệ, có các điều kiện |
| Công cụ OpenAPI/codegen | Dễ phân spec theo base path | Cần model header | Cần model param | Cần model media types |
| Nhược điểm | Nhân route/link và nhiều URL | Ẩn trên URL; CORS/proxy | Dễ quên; CDN bỏ query | Negotiation, Accept tooling phức tạp |
| Điểm mạnh | Dễ vận hành và debug | URI tài nguyên ổn định | Link chia sẻ được | Version gắn với representation |

**Gợi ý lựa chọn:** với API công khai có nhiều consumers/gateway thông thường, path major version thường dễ giải thích và vận hành. Nếu có SDK HTTP thống nhất và muốn giữ URI ổn định, header là lựa chọn hợp lý. Query phù hợp API đơn giản/chuyển đổi có chính sách rõ. Media type phù hợp khi version chủ yếu thay đổi **representation** và hệ thống đã quen dùng content negotiation.

Không chọn chiến lược chỉ vì số dòng controller ít; xét cả quy trình hỗ trợ v1 cũ và cache/CORS/debugging của client.

## 4. Chiến lược 1: phiên bản trong đường dẫn

Ví dụ:

~~~text
GET /api/v1/customers/42
GET /api/v2/customers/42
~~~

Spring MVC 6.x mapping đơn giản:

~~~java
@RestController
@RequestMapping("/api/v1/customers")
class CustomerV1Controller {
    @GetMapping("/{id}")
    CustomerV1 find(@PathVariable long id) {
        return service.findV1(id);
    }
}
~~~

Controller v2 có `@RequestMapping("/api/v2/customers")` và return `CustomerV2`. Đây là **fragment** dùng các kiểu service/DTO chưa định nghĩa; chương trình đầy đủ nằm ở mục 9.

### Ưu điểm

- URL thể hiện version, dễ copy vào curl/browser/documentation.
- CDN và reverse proxy nhận hai URI khác nhau; URL-based routing rõ.
- Có thể deploy v1/v2 vào những cụm khác nhau hoặc cùng ứng dụng.
- Mỗi version dễ có OpenAPI riêng; link/`Location` dễ kiểm.
- Dễ tìm consumers v1 thông qua path-aware metrics.

### Hạn chế

- Resource logic có thể xuất hiện ở nhiều controller và nhiều deep links.
- Client upgrade thường phải đổi base path và cập nhật SDK.
- Việc cùng tài nguyên có nhiều URI cần quyết định canonical links.
- v1 không tự ổn định nếu bạn thay DTO hoặc behavior trong controller v1.
- URL `/api/v99/...` có thể 404 theo routing bình thường; không mặc nhiên là 400 “unsupported version”.

Khi dùng path, một major version trên base path thường đủ. Không cần tăng `/v1.0.1` cho mọi patch deploy nếu contract cũ vẫn tương thích.

## 5. Chiến lược 2: phiên bản trong request header

Client gọi cùng URL:

~~~http
GET /api/header/customers/42 HTTP/1.1
API-Version: 1
Accept: application/json
~~~

và phiên bản mới:

~~~http
GET /api/header/customers/42 HTTP/1.1
API-Version: 2
Accept: application/json
~~~

Với **Spring 6**, đặt version trong điều kiện mapping:

~~~java
@GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=1",
            produces = "application/json")
CustomerV1 readV1(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=2",
            produces = "application/json")
CustomerV2 readV2(@PathVariable long id) {
    return v2(id);
}
~~~

`headers="API-Version=1"` được Spring dùng để **chọn method**. Nó khác hẳn:

~~~java
@RequestHeader("API-Version") String version
~~~

Annotation tham số chỉ **đọc version sau khi handler đã được chọn**; nó không tự chuyển giữa method v1/v2.

### Ưu điểm và trade-off

URI tài nguyên ổn định, SDK HTTP có thể gắn header version tự động. Nhưng version không hiển thị trên URL, dễ bị bỏ sót khi chia sẻ link hoặc test thủ công. Gateway phải forward đúng header, CORS phải cho custom header nếu frontend chạy khác origin, cache key cần xét version.

Nếu response public khác nhau theo `API-Version` nhưng chung URL, cân nhắc:

~~~http
Cache-Control: public, max-age=60
Vary: API-Version
~~~

`Vary` thông báo cho HTTP caches rằng header này ảnh hưởng representation. Nó **không tự được thêm** chỉ vì `@GetMapping(headers=...)` và **không thay phép phân quyền**. Nếu endpoint personalized, phải dùng `private` hoặc `no-store` và authentication/tenant scoping phù hợp, không dùng Vary để bảo vệ bí mật.

### CORS preflight

Browser frontend ở `https://app.example.test` gọi API khác origin và tự gắn `API-Version`:

~~~javascript
fetch("https://api.example.test/api/header/customers/42", {
  headers: { "API-Version": "2" }
});
~~~

Vì custom header không nằm trong CORS-safelisted request headers, browser thường preflight:

~~~http
OPTIONS /api/header/customers/42 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: api-version
~~~

Server phải cho phép origin/method/header ở **CORS policy**, rồi actual request vẫn chịu authentication/authorization. CORS preflight thành công không có nghĩa version hợp lệ hoặc user được phép xem dữ liệu.

## 6. Chiến lược 3: phiên bản bằng query parameter

~~~text
GET /api/query/customers/42?version=1
GET /api/query/customers/42?version=2
~~~

Spring 6.x:

~~~java
@GetMapping(path = "/api/query/customers/{id}", params = "version=1")
CustomerV1 v1ByQuery(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/query/customers/{id}", params = "version=2")
CustomerV2 v2ByQuery(@PathVariable long id) {
    return v2(id);
}
~~~

`params` trong `@GetMapping` là **mapping condition**. `@RequestParam("version")` chỉ bind giá trị ở một handler được chọn; không tự tạo hai versions.

Ưu điểm: client dễ chạy trên browser/curl, link có version tường minh, không thêm custom header. Nhưng:
- Client quên hoặc lặp `version` có thể khiến routing không theo ý định.
- URL query string có thể bị strip/normalize khi gateway rewrite.
- CDN có thể cấu hình **ignore query params** khi tính cache key; khi đó `?version=1` và `?version=2` bị trộn.
- Nếu phần URL chứa token/PII khác, raw query logs rất nhạy cảm; không nên log full URL một cách mù quáng.
- Nếu dùng `version` đồng thời cho domain query filter, cần đặt tên tránh trùng.

**Chính sách cần định nghĩa:** version có bắt buộc không? Có default cố định? Cho phép `v1` hay chỉ `1`? Unknown version trả 400 hay 404? Duplicate values `?version=1&version=2` bị từ chối hay normalize? Không dựa vào một hiệu ứng ngẫu nhiên của handler matching thay cho hợp đồng lỗi.

## 7. Chiến lược 4: phiên bản qua media type

### 7.1. Vendor media type trong `Accept`

Request cho v1:

~~~http
GET /api/media/customers/42 HTTP/1.1
Accept: application/vnd.demo.customer.v1+json
~~~

Request v2:

~~~http
GET /api/media/customers/42 HTTP/1.1
Accept: application/vnd.demo.customer.v2+json
~~~

Spring MVC 6:

~~~java
@GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v1+json")
CustomerV1 mediaV1(@PathVariable long id) {
    return v1(id);
}

@GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v2+json")
CustomerV2 mediaV2(@PathVariable long id) {
    return v2(id);
}
~~~

`Accept` diễn đạt **representation mong muốn từ server**, còn `produces` giúp Spring chọn handler/converter và `Content-Type` response. Với Jackson trên Spring Boot Web thông thường, hậu tố `+json` được hỗ trợ cho vendor media types.

### 7.2. Phân biệt `Accept`, `Content-Type`, `produces` và `consumes`

| Thành phần | Mô tả | Thường sử dụng |
| --- | --- | --- |
| `Accept` request header | Client muốn **nhận** loại representation nào | GET/POST/... |
| `Content-Type` request header | Client đang **gửi body** định dạng nào | POST/PUT/PATCH |
| `produces` mapping | Representation server có thể trả | Response negotiation |
| `consumes` mapping | Representation request body server chấp nhận | Request conversion |

Ví dụ POST versioned request:

~~~http
POST /api/media/customers HTTP/1.1
Content-Type: application/vnd.demo.customer.v2+json
Accept: application/vnd.demo.customer.v2+json

{"givenName":"An","familyName":"Nguyen"}
~~~

Nếu input contract cũng khác, cần DTO và `consumes` tương ứng. Đừng lấy `Content-Type` để quyết định version của một GET không có body. Lỗi không match `Accept` có thể dẫn đến 406 Not Acceptable; body Content-Type không được hỗ trợ thường dẫn đến 415 Unsupported Media Type.

### 7.3. Tham số của media type không phải vendor suffix

Một hình thức khác:

~~~http
Accept: application/json;v=2
~~~

Đây là **media type parameter `v=2`**, không phải tên `application/vnd.demo.customer.v2+json`. Spring Framework 7 hỗ trợ resolver chuyên dụng cho media type parameter. Trên Spring MVC 6.x, chỉ thêm `produces="application/json;v=2"` mà không hiểu media type matching có thể không đủ để phân biệt mọi tình huống, đặc biệt khi request không có tham số `v`. Nên kiểm thử cụ thể hoặc dùng vendor media types như demo cho Spring 6.

### 7.4. Trade-offs và caching

Media type versioning cho phép một URI nhiều representations, phù hợp hệ thống đã xây quanh HTTP negotiation. Nó phức tạp hơn khi chia sẻ link, quản lý `Accept` defaults, q-values, vendor types trong proxy, OpenAPI/codegen và CDN. Nếu response công khai có thể cache cùng URI:

~~~http
Cache-Control: public, max-age=60
Vary: Accept
~~~

Với personalized data, `Vary: Accept` không thay `private/no-store` hay phân quyền user. CORS có những quy tắc safelisted Accept request header; một Accept phù hợp thường không trigger preflight chỉ bởi version, nhưng các ràng buộc Fetch về giá trị/kích thước vẫn áp dụng, không nên khẳng định mọi Accept đều “simple”.

## 8. Spring MVC 6.x: mapping conditions khác hệ thống API versioning

Các thuộc tính có sẵn trong Spring Framework 6.x:

~~~java
@GetMapping(
    path = "/api/customers/{id}",
    params = "version=1",
    headers = "X-Channel=mobile",
    produces = "application/json")
~~~

Request phải match các điều kiện tương ứng. Cơ chế này rất hữu ích nhưng **không tự cung cấp**:
- Một registry version được hỗ trợ toàn ứng dụng.
- Semantic version parser, baseline version routing.
- Quy định missing/unknown version thống nhất giữa controllers.
- Deprecation/sunset header tự động.
- Client compatibility, DTO conversion hoặc database migration.
- Cache safety, CORS, authorization hoặc OpenAPI cho từng version.

**Cực kỳ quan trọng:** `@GetMapping(version="1.0")` và `WebMvcConfigurer.configureApiVersioning` là API mới của **Spring Framework 7**. Chúng **không biên dịch trên Spring MVC 6.1/6.2** do Spring Boot 3.x sử dụng. Đừng lấy một snippet Spring 7 rồi sửa mỗi dependency `spring-webmvc` của Boot 3: cần bộ framework/platform tương thích.

## 9. Ví dụ hoàn chỉnh: bốn chiến lược trên Spring Boot 3.3.5

Một ứng dụng mẫu chạy Java 17, Spring MVC 6.1.x (theo dependency management của Boot 3.3.5), Gradle và MockMvc. Sử dụng response fixtures để **chứng minh cách chọn version**, không dùng database và không có bảo mật đăng nhập.

Hợp đồng v1:

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

Hợp đồng v2:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

Cấu trúc:

~~~text
api-version-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/apiversion/
    │   ├── ApiVersionDemoApplication.java
    │   └── web/CustomerVersionsController.java
    └── test/java/com/example/apiversion/web/
        └── CustomerVersionsControllerTest.java
~~~

### 9.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'api-version-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Main application

`src/main/java/com/example/apiversion/ApiVersionDemoApplication.java`:

~~~java
package com.example.apiversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiVersionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiVersionDemoApplication.class, args);
    }
}
~~~

### 9.3. Controller tám mappings

`src/main/java/com/example/apiversion/web/CustomerVersionsController.java`:

~~~java
package com.example.apiversion.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerVersionsController {

    public record CustomerV1(long id, String fullName) {}

    public record CustomerV2(
            long id, String givenName, String familyName, boolean active) {}

    private CustomerV1 v1(long id) {
        return new CustomerV1(id, "Nguyen An");
    }

    private CustomerV2 v2(long id) {
        return new CustomerV2(id, "An", "Nguyen", true);
    }

    @GetMapping("/api/v1/customers/{id}")
    public CustomerV1 pathV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping("/api/v2/customers/{id}")
    public CustomerV2 pathV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=1", produces = "application/json")
    public CustomerV1 headerV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/header/customers/{id}",
            headers = "API-Version=2", produces = "application/json")
    public CustomerV2 headerV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/query/customers/{id}",
            params = "version=1", produces = "application/json")
    public CustomerV1 queryV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/query/customers/{id}",
            params = "version=2", produces = "application/json")
    public CustomerV2 queryV2(@PathVariable("id") long id) {
        return v2(id);
    }

    @GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v1+json")
    public CustomerV1 mediaV1(@PathVariable("id") long id) {
        return v1(id);
    }

    @GetMapping(path = "/api/media/customers/{id}",
            produces = "application/vnd.demo.customer.v2+json")
    public CustomerV2 mediaV2(@PathVariable("id") long id) {
        return v2(id);
    }
}
~~~

Có **hai public DTO records khác nhau** nên test có thể xác minh field cũ biến mất chỉ ở v2. Mỗi handler có routing condition phân biệt; không dùng `version=` của Spring 7 trong project Boot 3.

**Giới hạn của ví dụ:** controller trả fixture theo ID bất kỳ, không tra DB hoặc kiểm quyền. Production cần trả 404 nếu resource không tồn tại và xác thực/ủy quyền theo principal; **chọn version không cấp quyền đọc**.

### 9.4. Gọi API bằng curl

Chạy project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows có thể dùng `.\gradlew.bat bootRun`.

Path:

~~~bash
curl -i 'http://localhost:8080/api/v1/customers/42'
curl -i 'http://localhost:8080/api/v2/customers/42'
~~~

Header:

~~~bash
curl -i 'http://localhost:8080/api/header/customers/42' \
  -H 'API-Version: 1' -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/header/customers/42' \
  -H 'API-Version: 2' -H 'Accept: application/json'
~~~

Query:

~~~bash
curl -i 'http://localhost:8080/api/query/customers/42?version=1'
curl -i 'http://localhost:8080/api/query/customers/42?version=2'
~~~

Media type:

~~~bash
curl -i 'http://localhost:8080/api/media/customers/42' \
  -H 'Accept: application/vnd.demo.customer.v1+json'

curl -i 'http://localhost:8080/api/media/customers/42' \
  -H 'Accept: application/vnd.demo.customer.v2+json'
~~~

Kết quả dự kiến mỗi request là HTTP **200**, v1 trả:

~~~json
{"id":42,"fullName":"Nguyen An"}
~~~

v2 trả:

~~~json
{"id":42,"givenName":"An","familyName":"Nguyen","active":true}
~~~

Trên media endpoint, `Content-Type` trả về vendor MIME tương ứng khi converter hoạt động. Những URL header/query không match có thể trả lỗi routing khác nhau theo tình huống, **không tự bảo đảm một code 400 duy nhất**. Khi version không hỗ trợ, phải định nghĩa error handler/strategy nếu contract cần một body chuẩn.

## 10. MockMvc: kiểm cả schema, không chỉ HTTP status

`src/test/java/com/example/apiversion/web/CustomerVersionsControllerTest.java`:

~~~java
package com.example.apiversion.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerVersionsControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void pathV1ReturnsLegacyShape() throws Exception {
        mvc.perform(get("/api/v1/customers/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.fullName").value("Nguyen An"))
                .andExpect(jsonPath("$.givenName").doesNotExist());
    }

    @Test
    void pathV2ReturnsNewShape() throws Exception {
        mvc.perform(get("/api/v2/customers/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.familyName").value("Nguyen"))
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void headerV1SelectsLegacy() throws Exception {
        mvc.perform(get("/api/header/customers/42")
                        .header("API-Version", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));
    }

    @Test
    void headerV2SelectsNew() throws Exception {
        mvc.perform(get("/api/header/customers/42")
                        .header("API-Version", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void queryV1AndV2SelectCorrectDtos() throws Exception {
        mvc.perform(get("/api/query/customers/42")
                        .param("version", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));

        mvc.perform(get("/api/query/customers/42")
                        .param("version", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void mediaV1UsesVendorJsonType() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v1+json")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                                "application/vnd.demo.customer.v1+json")))
                .andExpect(jsonPath("$.fullName").value("Nguyen An"));
    }

    @Test
    void mediaV2UsesVendorJsonType() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v2+json")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                                "application/vnd.demo.customer.v2+json")))
                .andExpect(jsonPath("$.givenName").value("An"))
                .andExpect(jsonPath("$.fullName").doesNotExist());
    }

    @Test
    void unknownVendorTypeIsNotAcceptable() throws Exception {
        mvc.perform(get("/api/media/customers/42")
                        .accept(MediaType.parseMediaType(
                                "application/vnd.demo.customer.v3+json")))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Không dùng `@AutoConfigureMockMvc(addFilters=false)` nếu sau này thêm Spring Security và muốn kiểm authentication. Test trên tập trung MVC mapping, response shapes và media negotiation; **không** chứng minh CDN, browser CORS hay API gateway đang forward đúng version. Khi triển khai thật, thêm E2E tests qua reverse proxy và contract tests từ SDK/consumer.

## 11. Spring Framework 7 có API versioning chuyên dụng

Từ **Spring Framework 7**, MVC có `ApiVersionStrategy` để resolve, parse, validate phiên bản và hỗ trợ deprecation. Spring Framework 7 mở rộng `@RequestMapping` và các annotation shortcut với thuộc tính `version`.

**Đây là mã riêng cho Spring 7/Boot 4 tương thích, không thuộc demo Spring Boot 3 ở trên.**

### 11.1. Chọn resolver theo header

~~~java
package com.example.modernversion;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiVersionConfig implements WebMvcConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("API-Version");
    }
}
~~~

Controller Spring 7:

~~~java
package com.example.modernversion;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModernCustomerController {

    @GetMapping(path = "/api/customers/{id}", version = "1.0")
    public Map<String, String> v1() {
        return Map.of("fullName", "Nguyen An");
    }

    @GetMapping(path = "/api/customers/{id}", version = "2.0")
    public Map<String, String> v2() {
        return Map.of("givenName", "An", "familyName", "Nguyen");
    }
}
~~~

Spring 7 giải version từ `API-Version: 1.0` hoặc `2.0`, sau đó chọn mapping. `@GetMapping(version=...)` không dùng được ở Spring 6.x. Đây là fragment minh họa cơ chế, có thể đặt vào một dự án Spring 7 tương thích cùng component scanning.

### 11.2. Các cách resolve tích hợp

`ApiVersionConfigurer` hỗ trợ:
- `useRequestHeader("API-Version")`: version trong header.
- `useRequestParam("version")`: version trong query.
- `usePathSegment(index)`: version trong path segment, ví dụ `/api/{version}/customers`; segment **phải là URI variable** trong mapping/path prefix, không chỉ hardcode `v1`.
- `useMediaTypeParameter(compatibleMediaType, "v")`: lấy `v` từ media type trong Accept/Content-Type tùy trường hợp có thể áp dụng.

Ví dụ query resolver:

~~~java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestParam("version");
}
~~~

Ví dụ media type parameter:

~~~java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useMediaTypeParameter(
            org.springframework.http.MediaType.APPLICATION_JSON, "v");
}
~~~

Mỗi fragment ở đây là **một lựa chọn thay thế trong callback**, không phải copy cả hai method override vào cùng class. Với path versioning, chỉ số segment tính từ 0; ví dụ `/api/{version}/...` thường index 1. Đọc tài liệu phiên bản thực tế để cấu hình path resolver và các prefix.

### 11.3. Các quy tắc version của Spring 7

- Mặc định parser xử lý thành phần semantic version `major.minor.patch`; phần minor/patch có thể mặc định 0.
- Có thể thay parser nếu dùng calendar version hoặc format doanh nghiệp.
- Versions được hỗ trợ thường thu thập từ các mappings đã khai báo, hoặc cấu hình danh sách rõ ràng.
- Khi version không được hỗ trợ, `InvalidApiVersionException` thường gây **400**.
- Mặc định yêu cầu version khi bật strategy; thiếu version có `MissingApiVersionException`, thường **400**, trừ khi cấu hình default/optional version.
- Mapping nhận **fixed version** như `"1.2"` hoặc **baseline version** như `"1.2+"`, hữu ích khi một handler vẫn tương thích cho những versions về sau.
- `ApiVersionDeprecationHandler` hỗ trợ phát thông tin deprecation/sunset khi cấu hình.

**Spring 7 không tự version JSON DTO, business logic hoặc authorization.** Nó cung cấp building blocks cho routing và lifecycle, không quyết định hộ team thời gian giữ v1 hay schema phù hợp.

### 11.4. Lưu ý migration Boot 3 → Boot 4

Không nâng mỗi `spring-webmvc` lên 7.x trong project Boot 3.3 mà bỏ qua bộ dependency management. Cần kiểm Java baseline, Servlet/Jakarta namespaces, Spring Security, springdoc, các starter, integration tests và deployment runtime theo ma trận tương thích chính thức. Nếu chưa thể nâng, cách dùng `path`, `headers`, `params`, `produces` trong Spring 6 vẫn có thể phục vụ versioned APIs khi bạn kiểm đủ error behavior và compatibility.

## 12. Missing/unknown version, lỗi và default

Bất kể chọn phương án nào, cần trả lời các câu hỏi:
- Không gửi version có bị từ chối, hay mặc định cố định v1?
- Gửi v99 hoặc chuỗi không parse được thì status/body nào?
- Gửi `version=1&version=2` thì xử lý ra sao?
- Có cho major 1.0 và minor 1.1 cùng một handler không?
- Các client gửi `Accept: */*` hoặc không gửi Accept nhận version nào?
- Một API retired version có trả migration document không?

**Không mặc định version mới nhất nếu muốn bảo toàn client cũ.** Nếu hôm nay `GET /api/customers` không có version là v1, ngày mai tự động chuyển v2 thì request cũ sẽ đổi contract dù code client không thay. Nếu phải có default, hãy cố định và document rõ deadline.

### 12.1. HTTP statuses không đồng nhất giữa strategies

| Tình huống | Status thường gặp / cần xem xét |
| --- | --- |
| `/api/v99/...` không có MVC mapping | 404 trong routing thông thường |
| Header/query mapping conditions không match | 404 hoặc 400 tùy condition và MVC exception handling |
| Accept không tương thích với `produces` | Thường 406 Not Acceptable |
| Request Content-Type không hợp `consumes` | Thường 415 Unsupported Media Type |
| Spring 7 native missing version | Thường 400 theo `MissingApiVersionException` |
| Spring 7 native unsupported version | Thường 400 theo `InvalidApiVersionException` |
| Request bị Security chặn trước MVC | 401 hoặc 403 theo auth/authorization |
| Version đã sunset theo policy | Status/domain error do sản phẩm quyết định; có thể là 400/410 |

Không khẳng định mọi unknown version phải là 404 hay mọi 406 là unsupported API version. Nếu client cần machine-readable error **ổn định**, hãy dùng version validation/exception mapping tường minh và integration tests.

Ví dụ error body RFC 9457 do ứng dụng tự định nghĩa:

~~~json
{
  "type": "about:blank",
  "title": "Unsupported API version",
  "status": 400,
  "detail": "Requested API version is not supported.",
  "code": "UNSUPPORTED_API_VERSION",
  "supportedVersions": ["1", "2"]
}
~~~

`supportedVersions` chỉ nên liệt kê các versions public/allowed cho client, không lộ internal beta hoặc tenant-private features. Đây **không phải body tự động có ở mọi Boot 3/4 project**.

## 13. Cache, `Vary` và dữ liệu cá nhân hóa

### 13.1. Path/query vs header/media type

Theo HTTP cache thông thường, target URI gồm path/query, vì vậy `/api/v1/items` và `/api/v2/items`, hay `?version=1` với `?version=2`, được phân biệt. Nhưng CDN có thể cấu hình **ignore query params**, URL rewrites hoặc custom cache keys, phải test thực tế.

Với header version trên cùng URI, response cacheable nên phát:

~~~http
Cache-Control: public, max-age=60
Vary: API-Version
~~~

Với media type versioning trên cùng URI:

~~~http
Cache-Control: public, max-age=60
Vary: Accept
~~~

HTTP `Vary` yêu cầu cache xét request header khi chọn representation đã lưu. Không quên những variants khác như Accept-Language/Accept-Encoding nếu có. Đừng xóa `Vary` của CORS/proxy khi controller thêm Vary riêng.

### 13.2. `Vary` không phải bảo vệ user

Hai user Alice và Bob có thể dùng cùng API v2, cùng origin, cùng Accept/header version. Cache vẫn có thể nhầm nếu dữ liệu riêng bị cho vào shared cache. Với `/api/me` hoặc tài nguyên theo principal/tenant, chọn `Cache-Control: private` hoặc `no-store` tùy mức độ nhạy cảm, và bắt buộc authentication/authorization đúng ở origin. `Vary: API-Version` hoặc `Vary: Accept` không thay quyền truy cập.

Spring `@Cacheable` ở service còn là một tầng khác, không tự hiểu HTTP version/`Vary`. Nếu cache domain theo `id` nhưng kết quả phụ thuộc tenant/role, cần cache key/scope đúng hoặc bỏ cache; versioning không tự sửa leak bên trong service.

## 14. API gateway, OpenAPI và client SDK

### 14.1. Gateway

- Path: proxy route/strip/rewrite `/api/v1`/`/api/v2` nhưng không làm lạc version khỏi upstream selection.
- Header: forward `API-Version`, không bỏ hoặc tự normalize giá trị sai.
- Query: giữ `version` trong URL khi rewrite; bảo đảm CDN cache key có nó.
- Media type: giữ `Accept`/`Content-Type` và support vendor MIME `+json`.
- Test cả OPTIONS preflight nếu browser dùng custom version header.
- Với nhiều instances, cùng một version phải luôn trả cùng contract trong rolling deployments.

### 14.2. OpenAPI

Path version dễ chia base paths/specs. Header/query versioning trên cùng path/method có thể cần nhiều OpenAPI documents, schema alternatives và generator configuration để SDK không chỉ đoán một response type. Vendor media type có thể dùng nhiều media-type keys trong `responses.content`, nhưng code generator phải được xác minh.

Với mỗi version nên công bố:
- Cách truyền version cùng các giá trị hỗ trợ.
- Request/response schemas và examples.
- Error codes/statuses.
- Authentication, CORS, pagination, validation, sorting và idempotency rules.
- Chính sách missing/invalid version và caching.
- Ngày deprecated/sunset, migration guide.

### 14.3. Observability

Log/trace nên có **effective version** đã validate (ví dụ `1`/`2`). Không đưa raw unbounded version header/query vào metric labels, tránh cardinality và log injection. Đo adoption, 4xx/5xx, latency, usage theo từng version và consumer segment có quyền truy cập.

## 15. Deprecation và Sunset

Một versioning strategy không hoàn chỉnh nếu không có kế hoạch ngừng hỗ trợ:
1. Phát hành v2 song song với v1.
2. Công bố khác biệt contract, ví dụ thay `fullName` bằng `givenName/familyName`.
3. Cung cấp docs/SDK/client adapter cho v2.
4. Theo dõi traffic v1 từ thực tế, đặc biệt mobile apps/partners release chậm.
5. Đánh dấu v1 deprecated và gửi thông báo đủ sớm.
6. Có thời điểm Sunset dự kiến, kênh hỗ trợ và rollback plan.
7. Chỉ retire version khi đã đánh giá impact, security và compliance.

Các HTTP signals chuẩn gồm `Deprecation` (RFC 9745), `Sunset` (RFC 8594), `Link` tới tài liệu/migration. Spring Framework 7 có `ApiVersionDeprecationHandler` có thể phát những headers theo cấu hình; ở Spring MVC 6, có thể tự thêm qua response/filter/interceptor theo chính sách. Không giả định Spring tự sinh ngày sunset hay migration documentation.

**Deprecation khác Sunset:** deprecated nghĩa là khuyến nghị client chuyển đi; sunset là mốc dự kiến API không còn hoạt động/được hỗ trợ. Ngay cả version cũ cũng cần áp dụng các bản vá security, không giữ lỗ hổng chỉ để “tương thích”.

## 16. Tổ chức code để không nhân đôi business logic

Một thiết kế thông thường:

~~~text
GET /api/v1/customers -> V1 controller / DTO --\
                                               \
                                                -> Shared service / domain
                                               /       |
GET /api/v2/customers -> V2 controller / DTO --/        v
                                                     repository
~~~

Controllers/adapters phụ trách mapping HTTP và DTO per version; service/domain giữ nghiệp vụ dùng chung nếu semantics không thay. Nếu thay đổi business rules thực sự, thiết kế policy tường minh và test, không chỉ đổi tên field.

V1 và v2 nên dùng DTO riêng khi có breaking schema change. Không expose JPA entity trực tiếp: thay bảng/entity graph có thể vô tình đổi public response ở cả versions. Nếu DTO v1 vẫn cần `fullName`, adapter có thể xây từ domain `givenName` và `familyName` theo quy tắc đã document.

Với mutation operations, hai versions có thể cùng tác động một database. Cần bảo toàn transaction, optimistic locking, idempotency, audit và field defaults. Dùng expand/contract database migrations khi rollout nhiều phiên bản server/client, đừng xóa cột ngay khi v2 được deploy.

## 17. Lỗi thường gặp và cách chẩn đoán

| Lỗi | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| `@GetMapping(version=...)` không biên dịch ở Boot 3 | Trộn API Spring 7 với Spring 6 | Dùng mapping conditions hoặc nâng platform đúng phiên bản |
| `@RequestHeader` có version nhưng handler vẫn không đổi | Chỉ bind, không chọn mapping | `headers=...` hoặc Spring 7 version strategy |
| V2 nhận response v1 qua CDN | Cache key bỏ header/query version | `Vary` và CDN rules, test cache thực |
| POST Content-Type vendor đúng nhưng GET không chọn | Content-Type mô tả request body | Dùng Accept/produces để chọn response |
| Header API-Version gây OPTIONS | Custom header không safelisted | CORS allow origin/method/header, xử lý OPTIONS trước auth |
| `Accept` v3 cho 406 | Không có matching `produces` | Thêm supported type hoặc trả error hợp đồng |
| Method mappings conflict khi startup | Conditions bị trùng | So path/method/params/headers/produces |
| Default latest làm mobile app cũ lỗi | Contract thay khi không truyền version | Dùng default cố định hoặc required version |
| Một endpoint v1 thành schema v2 sau refactor | Shared DTO bị đổi | Contract tests và adapters riêng |
| Authorization chỉ tồn tại ở v2 | Bỏ sót security rules cũ | Kiểm cả versions, object/tenant authorization |
| V1 tồn tại mãi | Không có sunset roadmap | Support policy, adoption metrics, thông báo |
| CORS 403 bị hiểu thành unsupported version | Preflight chặn trước actual request | Kiểm DevTools OPTIONS và filters |
| Route v99 trả 404 thay 400 | Mapping conditions không là version parser | Error policy rõ, Spring 7 native khi phù hợp |
| OpenAPI chỉ có một response type | Header/query versions dùng cùng path | Tách specifications và test codegen |
| v1/v2 đổi semantics ngầm | Version chỉ áp dụng tên DTO | Version behavior/service policy tường minh |

### Quy trình gỡ lỗi có thứ tự

1. Xác minh **đúng Spring Framework major version** và thuộc tính annotation có tồn tại.
2. Ghi method/URL/query/version header/Accept/Content-Type thực tế, không copy token bí mật vào logs.
3. Kiểm reverse proxy rewrite và forwarded headers.
4. Kiểm Spring handler mappings và `params`/`headers`/`produces` conditions.
5. Nếu frontend cross-origin, tách preflight OPTIONS với request thật.
6. Kiểm authentication/authorization đã chặn trước MVC hay chưa.
7. Nếu có CDN, kiểm cache key, `Vary`, freshness và private directives.
8. Test JSON field presence/absence cùng HTTP status/media type.
9. Thử nhiều nodes trong rolling deployment và các versions cùng một fixture.
10. So contract với OpenAPI, migration docs và consumer tests.

## 18. Checklist triển khai

- [ ] Chọn format version, định nghĩa breaking change và supported versions.
- [ ] Chọn **một** nơi truyền version chính: path, header, query hoặc media type.
- [ ] Xác định missing/unknown/duplicate version policy, không âm thầm nâng latest.
- [ ] Với Spring 6 dùng `path`, `headers`, `params`, `produces`; với Spring 7 có version strategy.
- [ ] Mỗi version có DTO/mapping độc lập khi khác schema; dùng service chung hợp lý.
- [ ] Test đúng body, statuses, 406/415, unknown/missing version, auth và tenant ownership.
- [ ] Test CORS nếu custom header từ browser.
- [ ] Test URL/query/header/Accept cache key tại CDN/proxy; `Vary` không thay `no-store` cho dữ liệu private.
- [ ] Viết OpenAPI, consumer tests, curl và SDK examples.
- [ ] Theo dõi adoption, công bố deprecation/sunset, có migration/rollback plan.
- [ ] Không bỏ security fixes hay rò rỉ dữ liệu ở old versions.

### Câu hỏi tự kiểm tra

**1.** `@RequestHeader("API-Version")` có tự phân route v1/v2 không?

**Trả lời:** Không. Spring MVC 6 chọn handler qua mapping conditions; Spring 7 có resolver + `version` annotation.

**2.** `?version=2` luôn được CDN cache riêng v1?

**Trả lời:** Không chắc. URI thông thường khác, nhưng CDN có thể ignore query params; phải test chính sách cache key.

**3.** `Accept` và `Content-Type` khác nhau thế nào?

**Trả lời:** Accept yêu cầu kiểu representation nhận về; Content-Type mô tả kiểu body gửi lên.

**4.** Với same URL và `API-Version`, cacheable public response nên có gì?

**Trả lời:** `Vary: API-Version` hoặc custom cache key tương thích; dữ liệu cá nhân cần `private/no-store` độc lập.

**5.** Vì sao Boot 3.3.5 không dùng `@GetMapping(version="1.0")`?

**Trả lời:** Vì Boot 3.3.5 dùng Spring Framework 6.1.x, còn thuộc tính version được thêm ở Spring Framework 7.

**6.** CORS preflight chấp thuận API-Version có chứng minh user được phép xem dữ liệu không?

**Trả lời:** Không. CORS là kiểm soát của browser, auth và authorization phải kiểm riêng.

**7.** Version v2 có bắt buộc tách database khỏi v1?

**Trả lời:** Không. Có thể dùng shared domain/repository và adapters/DTO riêng, cùng migration data tương thích.

**8.** Tại sao không default version thiếu thành latest?

**Trả lời:** Vì cùng request của client cũ sẽ đổi hợp đồng khi server phát hành latest mới.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): `path`, `params`, `headers`, `consumes`, `produces`.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): cơ chế mapping, Accept/Content-Type; bản Spring 7 có `version`.
- [Spring Framework 7 — API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html): `ApiVersionStrategy`, parser, resolver, supported versions và deprecation.
- [Spring Framework 7 — API Version Configurer](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-version.html): request header/query/path/media type parameter resolvers.
- [Spring Blog — API Versioning in Spring (2025)](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): mục tiêu và thay đổi trong Spring Framework 7.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): Accept, Content-Type, status và representation negotiation.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): `Vary`, cache key và shared/private caching.
- [RFC 8594 — Sunset Header](https://www.rfc-editor.org/rfc/rfc8594.html): tín hiệu sunset.
- [RFC 9745 — Deprecation Header](https://www.rfc-editor.org/rfc/rfc9745.html): tín hiệu deprecation.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): custom header preflight và security boundaries.

**Ghi nhớ:** versioning là **cam kết hợp đồng lâu dài** giữa server và client. Path, header, query param và media type đều khả thi, nhưng phải quyết định cùng caching, CORS, gateway, documentation, security, error behavior và migration. Trên Spring MVC 6.x dùng mapping conditions; Spring Framework 7 có versioning native, không trộn code giữa hai nền tảng.
