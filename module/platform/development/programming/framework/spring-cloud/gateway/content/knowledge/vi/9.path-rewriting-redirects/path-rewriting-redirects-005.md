# Escape ký tự thay thế trong YAML và Java DSL của Spring Cloud Gateway

## 1. Vì sao cùng một phép rewrite được viết khác nhau?

Trong **Spring Cloud Gateway**, request đi qua **route predicate** để chọn tuyến, rồi các **GatewayFilter** có thể biến đổi đường dẫn/header trước khi gửi tới microservice. Gateway còn có thể sửa header phản hồi, chẳng hạn `Location` của một redirect từ backend. Ví dụ, client gọi `/public/orders/42` nhưng backend chỉ nhận `/orders/42`.

Với `RewritePath` hoặc `RewriteResponseHeader`, **biểu thức chính quy (Java regex)** xác định phần cần tìm, còn **replacement** quyết định nội dung thay thế. Các ký tự `$`, `{` và `\` rất dễ bị hiểu nhầm vì đi qua nhiều tầng:

1. **YAML**: đọc scalar dạng plain, single-quoted hoặc double-quoted.
2. **Spring Boot/Spring Cloud**: nạp và bind cấu hình; cú pháp `${property}` có thể bị hiểu là placeholder cấu hình.
3. **Java regex**: nhóm bắt `(?<segment>...)` được tham chiếu bằng `${segment}` hoặc `$1` trong replacement.
4. **Java DSL**: Java `String` có quy tắc escape riêng đối với dấu backslash; chuỗi Java thường không cần cách bảo vệ placeholder giống file YAML.

Mục tiêu bài học là viết đúng cú pháp, hiểu chính xác **tầng nào xử lý dấu escape**, tránh làm sai request path, để lộ URL backend trong redirect, hoặc gây lỗi khi chạy Gateway. Những kỹ thuật này hỗ trợ việc vận hành cổng vào microservices có xác thực, rate limit, circuit breaker, retry, TLS, service discovery và quan sát request. Chúng **không tự thay thế** các cơ chế bảo mật hay resiliency đó.

> **Quy tắc nhớ nhanh:** Với regex `/public/(?<segment>.*)`, replacement cuối cùng ở tầng Java regex là `/${segment}`. Trong **`application.yml`**, thường viết `/$\{segment}`; trong **Java DSL**, viết `"/${segment}"`. Đây là cú pháp được tài liệu Spring Cloud Gateway minh họa cho `RewritePath`.

### 1.1. Phạm vi phiên bản và biến thể

Ví dụ chính sử dụng **Gateway Server WebFlux 4.3+/5.x**, khai báo route ở `spring.cloud.gateway.server.webflux.routes`. Với WebFlux 4.2 trở về trước, prefix phổ biến là `spring.cloud.gateway.routes`. Java DSL WebFlux dùng `RouteLocatorBuilder`, còn Gateway Server Web MVC dùng `RouterFunction` với before-filter/after-filter. Không trộn các API WebFlux và Web MVC chỉ vì cả hai đều mang tên Spring Cloud Gateway.

## 2. Cú pháp regex và replacement: hai phía khác nhau

Giả sử cần chuyển:

```text
Client:  GET /public/orders/42
Backend: GET /orders/42
```

Mẫu tìm kiếm:

```regex
^/public/(?<segment>.*)$
```

- `^` và `$` trong **regex** neo đầu và cuối chuỗi.
- `(?<segment>.*)` là nhóm bắt có tên `segment`, lấy giá trị `orders/42`.
- Replacement `/${segment}` nối dấu `/` với nội dung nhóm, tạo `/orders/42`.
- `$1` có thể thay nhóm bắt thứ nhất nếu regex dùng `(...)` không tên, nhưng dễ sai khi thay đổi thứ tự nhóm.

| Ký hiệu | Xuất hiện ở đâu? | Ý nghĩa |
|---|---|---|
| `(?<name>...)` | Phần **regex** | Tạo nhóm có tên `name` |
| `(...)` | Phần **regex** | Tạo nhóm có số thứ tự |
| `${name}` | Phần **replacement** của Java regex | Thay bằng giá trị nhóm tên `name` |
| `$1` hoặc `$2` | Phần **replacement** | Thay bằng nhóm số 1 hoặc 2 |
| `{id}` | URI template của `Path`/`SetPath` | **Không phải** cú pháp tham chiếu nhóm regex |

Chữ `$` trong regex `...$` là ký tự **neo cuối**; nó không có ý nghĩa tham chiếu nhóm như `${name}` ở replacement.

## 3. Viết `RewritePath` trong YAML

### 3.1. Dạng shorthand

```yaml
# application.yml – Gateway Server WebFlux 4.3+/5.x
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/orders/**
              filters:
                - RewritePath=^/public/(?<segment>.*)$, /$\{segment}
                - AddRequestHeader=X-Via-Gateway, true
```

Với request `GET /public/orders/42`, `Path` predicate chọn `orders-route` trước; `RewritePath` đổi path thành `/orders/42` trước khi proxy tới `http://localhost:8081`. Backend còn nhận header `X-Via-Gateway: true`.

Trong cấu hình YAML, ký hiệu cần chú ý là **`$\{segment}`**: dấu backslash ở trước `{` giúp biểu thức tham chiếu nhóm không bị tầng cấu hình xử lý sai khi nó chưa đến Java regex. Trong Java DSL không viết thêm dấu này.

### 3.2. Dạng đầy đủ `name/args`

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/orders/**
              filters:
                - name: RewritePath
                  args:
                    regexp: '^/public/(?<segment>.*)$'
                    replacement: '/$\{segment}'
```

Đây là cách viết **thay thế** cho đoạn shorthand, không phải một route phải khai báo hai lần. Dạng `name/args` giúp dễ kiểm tra đúng tên tham số `regexp` và `replacement`. Single quote YAML giữ nguyên dấu backslash trong văn bản scalar; tuy nhiên, nó không có nghĩa là Spring hoàn toàn bỏ qua bước xử lý cấu hình phía sau.

### 3.3. Bảng escape theo kiểu scalar YAML

Giả sử cần gửi replacement có ý nghĩa Java regex `/${segment}`:

| Kiểu YAML | Nội dung trong file | Nhận xét |
|---|---|---|
| Plain | `replacement: /$\{segment}` | Cách ngắn gọn, thường dùng trong ví dụ |
| Single quoted | `replacement: '/$\{segment}'` | Giữ nguyên `\` trong scalar, dễ đọc |
| Double quoted | `replacement: "/$\\{segment}"` | YAML cần `\\` để giữ một dấu `\` |
| **Sai** | `replacement: "/$\{segment}"` | `\{` không phải YAML escape hợp lệ trong double quotes |
| Dễ nhầm | `replacement: /${segment}` | Có thể bị Spring diễn giải như placeholder `segment` |

Đừng hỏi “bao nhiêu dấu backslash?” khi chưa xác định lớp xử lý: **text trong file** → **YAML parse** → **Spring binding** → **replacement trong Java regex**. Nếu cấu hình đi qua Helm, CI template, environment variable hoặc một công cụ sinh YAML khác, phải kiểm tra cả lớp bổ sung.

## 4. Java DSL: cú pháp nhóm trực tiếp

Trong **Gateway Server WebFlux**, có thể tạo route bằng Java:

```java
package com.example.gateway;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {
    @Bean
    RouteLocator routes(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("orders-route", r -> r
                .path("/public/orders/**")
                .filters(f -> f
                    .rewritePath(
                        "^/public/(?<segment>.*)$",
                        "/${segment}")
                    .addRequestHeader("X-Via-Gateway", "true"))
                .uri("http://localhost:8081"))
            .build();
    }
}
```

Trong Java source, **`"/${segment}"`** là một chuỗi `String` bình thường: Java không có cú pháp nội suy `${...}`. Giá trị đó đi trực tiếp tới phần xử lý regex replacement.

**Lỗi thường gặp** là sao chép nguyên dạng YAML `/$\{segment}` sang chuỗi Java:

```java
// Sai: \{ không phải escape hợp lệ trong Java String.
// .rewritePath("^/public/(?<segment>.*)$", "/$\{segment}")

// Đúng:
.rewritePath("^/public/(?<segment>.*)$", "/${segment}")
```

Nếu viết Java source `"/$\\{segment}"`, Java tạo chuỗi replacement có dấu `\` thực; Java regex có thể hiểu đó là escape làm **mất ý nghĩa tham chiếu nhóm**. Vì thế khi cần nhóm, cứ dùng `"/${segment}"`.

### 4.1. Java regex có dấu backslash

Muốn match ID toàn chữ số, regex logic có `\d+`; trong **Java String** phải viết `\\d+`:

```java
.rewritePath(
    "^/public/orders/(?<id>\\d+)$",
    "/orders/${id}")
```

| Ý định regex | Trong YAML single-quoted/plain | Trong Java `String` |
|---|---|---|
| `\d+` — chữ số | `\d+` | `"\\d+"` |
| `\.` — dấu chấm thật | `\.` | `"\\."` |
| `\?` — dấu hỏi thật | `\?` | `"\\?"` |
| `(?<id>...)` — nhóm có tên | `(?<id>...)` | `"(?<id>...)"` |

Trong YAML double-quoted regex, `\d` cũng không phải escape YAML hợp lệ, nên cần `\\d` hoặc chuyển sang single quotes.

### 4.2. Java DSL của Gateway Server Web MVC

Gateway Server **Web MVC** có before-filter `rewritePath` và routing API khác:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.rewritePath;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
class MvcGatewayRoutes {
    @Bean
    RouterFunction<ServerResponse> ordersProxy() {
        return route("orders-route")
            .GET("/public/orders/**", http())
            .before(uri("http://localhost:8081"))
            .before(rewritePath(
                "^/public/(?<segment>.*)$",
                "/${segment}"))
            .build();
    }
}
```

Tầng **Java String** của MVC vẫn dùng `"/${segment}"`. Khi kết hợp MVC với `lb()`, kiểm tra quy tắc thứ tự before-filter và load-balancer trong tài liệu đúng phiên bản.

## 5. Nhóm có tên, nhóm theo số và nhóm không tồn tại

### 5.1. Hai nhóm có tên

```text
Regex:        ^/api/v1/(?<resource>orders|items)/(?<id>\d+)$
Replacement:  /${resource}/${id}
Input:        /api/v1/orders/42
Output:       /orders/42
```

- Trong **YAML**, replacement viết `/$\{resource}/$\{id}`.
- Trong **Java DSL**, replacement viết `"/${resource}/${id}"`.
- Trong Java source, regex có `\d+` phải viết thành `"\\d+"`.

### 5.2. Nhóm theo số

```text
Regex:        ^/api/v1/(orders|items)/(\d+)$
Replacement:  /$1/$2
Input:        /api/v1/items/17
Output:       /items/17
```

`$1` và `$2` không có ngoặc nhọn nên thường không gặp xung đột `${property}`. Tuy nhiên, chúng dễ tham chiếu sai khi thêm một nhóm bắt mới. Với route quan trọng, đặt tên nhóm thường giúp bảo trì dễ hơn.

### 5.3. Tham chiếu tên nhóm không tồn tại

```yaml
# Sai: regex chỉ có nhóm 'name', replacement lại yêu cầu 'id'.
- RewritePath=^/api/(?<name>.*)$, /$\{id}
```

Java regex có thể ném `IllegalArgumentException` vì không tìm thấy nhóm tên `id`. Một cấu hình route đọc được không có nghĩa mọi request đều rewrite thành công; cần gọi URL thật sự kích hoạt biểu thức.

## 6. Nếu muốn dấu `$` là ký tự thật

Trong Java `Matcher`, dấu `$` ở replacement là cú pháp nhóm. Muốn literal dollar, dùng `\$` ở **giá trị replacement mà regex nhận**. Java source phải viết `"\\$"` để truyền một dấu backslash:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String input = "price=42";
String regex = "(?<amount>\\d+)";

String withGroup = Pattern.compile(regex).matcher(input)
    .replaceAll("USD ${amount}"); // "price=USD 42"

String literalDollar = Pattern.compile(regex).matcher(input)
    .replaceAll("\\$"); // "price=$"

String replacement = Matcher.quoteReplacement("${amount}");
String exactLiteral = Pattern.compile(regex).matcher(input)
    .replaceAll(replacement); // "price=${amount}"
```

`Matcher.quoteReplacement(s)` biến `s` thành replacement **literal**: dấu `$` và `\` không còn là ký tự điều khiển nhóm. Chỉ dùng nó khi **không muốn** nội suy capturing group; nếu quote luôn `"${amount}"` rồi kỳ vọng nhận giá trị nhóm, kết quả sẽ sai.

## 7. Khi `SetPath` hoặc `StripPrefix` đơn giản hơn

Không phải mọi phép đổi path đều cần regex:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: product-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/products/{id}
              filters:
                - SetPath=/products/{id}
```

`SetPath` dùng biến **URI template** `{id}` của predicate, không dùng `${id}` hoặc `$\{id}` của Java regex. Với `GET /public/products/42`, backend nhận `/products/42`.

| Mục tiêu | Filter phù hợp | Ví dụ |
|---|---|---|
| Loại N segment đầu | `StripPrefix` | `StripPrefix=1` |
| Gán path từ biến URI template | `SetPath` | `SetPath=/products/{id}` |
| Thay path bằng Java regex | `RewritePath` | `RewritePath=... , /$\{segment}` |
| Thêm prefix cố định | `PrefixPath` | `PrefixPath=/v1` |

`Path` predicate luôn tham gia **chọn route trước**, còn các filter trên xử lý path sau bước match. Không đặt `RewritePath` và `StripPrefix` liên tiếp nếu chưa tính rõ đường dẫn sau từng bước.

## 8. Replacement khi sửa response redirect

### 8.1. `RedirectTo` khác `RewriteResponseHeader`

**`RedirectTo`** trả một redirect trực tiếp từ Gateway, ví dụ:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: docs-redirect
              uri: http://localhost:8081
              predicates:
                - Path=/old-docs
              filters:
                - RedirectTo=302, https://docs.example.test/new-docs
```

Ở đây URL redirect là giá trị cấu hình cố định, không tham chiếu nhóm regex. **`RewriteResponseHeader`** lại xử lý giá trị header từ **backend response** sau khi Gateway đã proxy request; `RewriteLocationResponseHeader` là filter chuyên cho header `Location`.

### 8.2. Rewrite header `Location` từ host nội bộ ra host công khai

Giả sử backend trả:

```http
HTTP/1.1 302 Found
Location: http://backend.internal/orders/42
```

Gateway muốn trả `Location: https://api.example.test/orders/42`. Có thể cấu hình:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-redirect
              uri: http://localhost:8081
              predicates:
                - Path=/orders/**
              filters:
                - name: RewriteResponseHeader
                  args:
                    name: Location
                    regexp: '^http://backend\.internal(?<path>/.*)$'
                    replacement: 'https://api.example.test$\{path}'
```

`(?<path>/.*)` lấy phần path của URL backend; replacement trong **YAML** dùng `$\{path}`. Dấu `\.` trong regex khớp dấu chấm hostname thật. Với redirect cần xử lý cả URL tương đối, protocol, query và proxy headers, nên cân nhắc `RewriteLocationResponseHeader` hoặc logic rõ ràng thay vì một regex quá rộng.

Chỉ rewrite đến host public được cho phép; đừng nhận host đích bất kỳ từ client hoặc header không đáng tin, vì có thể phát sinh **open redirect**. TLS inbound/outbound, OAuth2/JWT và việc giới hạn quyền truy cập là các chính sách riêng.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Lỗi “Could not resolve placeholder” | YAML dùng `${segment}` như placeholder cấu hình | Dùng `$\{segment}` trong YAML |
| YAML parser báo escape không hợp lệ | Double quote chứa `\{` hoặc `\d` | Dùng single quote/plain hoặc escape thành `\\{`, `\\d` |
| Java `illegal escape character` | Java source có `"/$\{id}"` hoặc `"\d+"` | Dùng `"/${id}"` và `"\\d+"` |
| Rewrite không thay path | Regex không khớp path thực tế | Kiểm tra predicate, regex, thứ tự filter và path backend |
| Java `IllegalArgumentException` về nhóm | Replacement tham chiếu nhóm không được định nghĩa | So lại `(?<id>...)` và `${id}` |
| Java `IndexOutOfBoundsException` | `$2` nhưng regex không có nhóm thứ hai | Sửa số nhóm hoặc dùng nhóm tên |
| Backend trả `404` sau rewrite | Path mới không đúng API backend | Log path trước/sau filter, xác minh backend |
| Redirect lộ hostname nội bộ | Chưa xử lý backend `Location` | Dùng `RewriteLocationResponseHeader` hoặc `RewriteResponseHeader` có kiểm soát |
| Có khác biệt giữa các URL encoded | Proxy, WebFlux, backend xử lý `%2F`/dot segments khác nhau | Kiểm thử qua đủ các lớp và xác định canonical path |

## 10. Kiểm thử thực tế

### 10.1. Kiểm tra request path

Cần một Gateway ở `localhost:8080` với cấu hình mục 3 và một backend **echo path** ở `localhost:8081`. Có thể thử:

```bash
curl -i 'http://localhost:8080/public/orders/42'
curl -i 'http://localhost:8080/public/orders/42/items/1'
curl -i 'http://localhost:8080/public/catalog/42'
curl --path-as-is -i 'http://localhost:8080/public/orders/a%2Fb'
```

Hai request đầu match route và backend kỳ vọng nhận `/orders/42`, `/orders/42/items/1`. Request `/public/catalog/42` không match predicate ví dụ; trường hợp percent-encoded slash cần quan sát **path thực nhận** thay vì đoán trước status. Nếu backend không chạy, lỗi kết nối khác với regex không khớp.

### 10.2. Kiểm tra redirect

Cho backend trả `302` với `Location: http://backend.internal/orders/42`, dùng cấu hình mục 8 rồi gọi:

```bash
curl -i 'http://localhost:8080/orders/42'
```

Không dùng `-L` trong bước đầu: `curl -L` tự đi theo redirect và có thể che mất `Location` cần kiểm tra. Sau khi rewrite thành công, client phải nhận `Location: https://api.example.test/orders/42`. Nếu không, xem backend response thực và cấu hình filter của route.

### 10.3. Thử Java regex độc lập

Đoạn Java sau giúp kiểm tra regex và replacement đã đến đúng **tầng Java**:

```java
import java.util.regex.Pattern;

public class RewriteCheck {
    public static void main(String[] args) {
        String source = "/public/orders/42";
        String regex = "^/public/(?<segment>.*)$";
        String replacement = "/${segment}";
        String result = Pattern.compile(regex)
            .matcher(source)
            .replaceAll(replacement);

        if (!"/orders/42".equals(result)) {
            throw new AssertionError(result);
        }
        System.out.println(result);
    }
}
```

Kiểm tra Java thuần không tự chứng minh phần cấu hình YAML đã được bind đúng hoặc proxy đã gửi path đúng. Vì vậy cần cả test request qua Gateway thật và, với hệ thống nhiều lớp, qua reverse proxy/ingress giống production.

## 11. Nguyên tắc an toàn khi rewrite path/header

1. **Phân biệt match và rewrite:** `Path` chọn route trước, `RewritePath` sửa request sau. Khi sai route, sửa replacement không giải quyết việc match.
2. **Giới hạn pattern:** ưu tiên `(?<id>\d+)` nếu ID chỉ có số; sử dụng `.*` có mục đích và neo regex bằng `^`/`$` khi cần khớp trọn path.
3. **Coi encoding là một ranh giới:** `%2F`, `%252F` và `..` có thể bị nhiều lớp hiểu khác nhau; không tự giải mã toàn chuỗi rồi dùng làm cơ sở phân quyền.
4. **Bảo vệ redirect:** chỉ cho phép host/scheme hợp lệ, kiểm tra header `Location`. Không coi sửa URL là thay thế cho kiểm soát quyền hoặc xác thực JWT.
5. **Tránh regex cho việc đơn giản:** dùng `StripPrefix`/`SetPath` khi chỉ cần bỏ segment hoặc đặt path theo URI template.
6. **Xác minh stack và phiên bản:** Server WebFlux và Server Web MVC có API và prefix khác nhau; dùng release train Spring Cloud tương thích Spring Boot.
7. **Quan sát đủ đường đi:** log có kiểm soát route ID, path trước/sau filter và response status; tránh log token, cookie hoặc path nhạy cảm. Khi dùng `lb://`, cần cả discovery/load-balancer.
8. **Kiểm thử retry/circuit breaker và TLS:** rewrite có thể đổi URL downstream nhưng không bảo đảm hành vi retry idempotent hoặc kết nối TLS đúng. Bảo vệ endpoint Actuator nếu dùng để xem route/filter.

## 12. Bài tập và đáp án

**Bài 1.** Regex `/legacy/(?<rest>.*)` cần đổi sang `/v2/<rest>`. Viết replacement trong YAML và Java DSL.

**Đáp án:** YAML `/v2/$\{rest}`, Java DSL `"/v2/${rest}"`. Regex phải có nhóm tên `rest`.

**Bài 2.** Vì sao YAML `replacement: "/$\{rest}"` có thể lỗi? Sửa thế nào?

**Đáp án:** `\{` không phải escape hợp lệ của YAML double quotes. Dùng `replacement: '/$\{rest}'` hoặc `replacement: "/$\\{rest}"`.

**Bài 3.** Java DSL viết `rewritePath("/v1/(?<id>\\d+)", "/$\{id}")` có gì sai?

**Đáp án:** phần regex `\\d+` là đúng khi nằm trong Java source; phần replacement `\{id}` không phải escape Java hợp lệ. Viết `"/${id}"`.

**Bài 4.** `SetPath=/products/{id}` có dùng cùng quy tắc escape với `RewritePath` không?

**Đáp án:** không. `SetPath` dùng URI template `{id}` của predicate; `RewritePath` dùng nhóm regex `${id}`.

**Bài 5.** Backend trả `Location: http://backend.internal/orders/9`. Có nên dùng `RewritePath` để sửa URL chuyển hướng của client không?

**Đáp án:** không. `RewritePath` sửa **request path**; `RewriteResponseHeader` hoặc `RewriteLocationResponseHeader` sửa **response Location**.

**Bài 6.** Muốn đưa chuỗi literal `price=$5` vào `Matcher.replaceAll`, làm sao tránh `$5` bị hiểu thành tham chiếu nhóm?

**Đáp án:** dùng `Matcher.quoteReplacement("price=$5")` khi cần literal replacement. Không quote toàn bộ replacement nếu mục tiêu là thay bằng một capturing group.

## 13. Tài liệu chính thức

- [Spring Cloud Gateway – RewritePath GatewayFilter (Server WebFlux)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritepath-factory.html): ví dụ YAML `$\{segment}`.
- [Spring Cloud Gateway – RewriteResponseHeader GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriteresponseheader-factory.html): cách dùng regex/replacement trên response header.
- [Spring Cloud Gateway – SetPath GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html): template `{id}` khác nhóm regex.
- [Spring Cloud Gateway – RewritePath Filter (Server Web MVC)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/rewritepath.html): YAML và Java DSL MVC.
- [Spring Cloud Gateway project – ví dụ Java RouteLocatorBuilder](https://spring.io/projects/spring-cloud-gateway): `rewritePath(..., "/${segment}")` trong Java.
- [Oracle Java – Matcher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): nhóm `$1`, `${name}` và `quoteReplacement`.

**Ghi nhớ:** đích cuối của replacement regex cho nhóm `segment` là `/${segment}`. Trong **YAML của Spring Cloud Gateway**, viết `/$\{segment}`; trong **Java DSL**, viết trực tiếp `"/${segment}"`. Hiểu rõ ranh giới **YAML → Spring config → Java regex** sẽ giúp thay đường dẫn và header redirect đúng, tránh lỗi escape khó phát hiện.
