# Kiểm thử predicate với các yêu cầu khớp và không khớp

## 1. Vì sao một route “chạy được” vẫn có thể định tuyến sai?

Trong **Spring Cloud Gateway**, client đi qua API Gateway để tới microservices. Gateway dùng **route predicates** quyết định request nào thuộc route nào, sau đó mới chạy **filter chain** nhằm biến đổi path/header, xác thực, giới hạn lưu lượng, retry, circuit breaker, chọn service instance và quan sát hoạt động.

Giả sử hệ thống có một route chỉ dành cho đối tác:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Host=catalog.test
  - Header=X-Channel,^partner$
  - Query=mode,^full$
~~~

Thử một request “đúng” và thấy HTTP 200 **chưa đủ**. Chúng ta còn phải chứng minh:

- Request thiếu `X-Channel` không đi vào route.
- `POST` không được dùng route chỉ định `GET`.
- Host khác không chọn nhầm backend đối tác.
- Query thiếu hoặc sai không vô tình được chấp nhận.
- Khi route không khớp, backend **không nhận request**.
- Nếu còn route khác cũng có thể khớp, Gateway chọn **route đúng ưu tiên**, không chỉ trả 200 tình cờ.

Bài **“Kiểm thử predicate với các yêu cầu khớp và không khớp”** thuộc chương **Kiểm thử** của module **SPRING_CLOUD_GATEWAY**. Chúng ta sẽ kết hợp **ma trận đầu vào**, lệnh `curl`, backend echo và kiểm thử tự động với **JUnit 5 + WebTestClient + MockWebServer**. Đó là nền móng để sau này kiểm thử xác thực, rate limiting, circuit breaker, retry, TLS, service discovery và observability trên đúng route.

> **Phạm vi chính:** Spring Cloud Gateway **Server WebFlux**. Đây là pipeline của `RoutePredicateHandlerMapping`/`RouteLocator`. Server Web MVC sử dụng WebMvc.fn và có thư viện predicate/filter riêng; không sao chép nguyên các import/reactive tests của bài sang Server MVC.

Sau bài, bạn có thể:

1. Giải thích quy tắc **AND giữa predicates** và **OR trong các lựa chọn của một predicate**.
2. Viết ma trận ca khớp/không khớp cho path, method, host, header, query.
3. Chọn phép đo xác định **route đã được chọn** thay vì chỉ nhìn status.
4. Dựng stub backend độc lập, kiểm tra **không có downstream call** khi route không khớp.
5. Viết integration test chạy Gateway trên random port với `WebTestClient`.
6. Xử lý các góc cạnh: slash, regex, case, route order, fallback, CORS preflight, proxy trust và thời gian.

## 2. Predicate được đánh giá ở pha nào?

Ở Server WebFlux, Gateway nhận một `ServerWebExchange`. Thành phần route matching tìm trong danh sách `Route` runtime, kiểm tra predicate của từng route và chọn một route phù hợp. Chỉ sau đó, các `GlobalFilter` và `GatewayFilter` liên quan mới tham gia pipeline xử lý request.

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> E["ServerWebExchange"]
    E --> R["RoutePredicateHandlerMapping"]
    R --> P{"Có Route với<br/>predicate khớp?"}
    P -->|"Không"| N["Không có Gateway route<br/>thường 404 nếu không có handler khác"]
    P -->|"Có"| A["Route runtime được chọn"]
    A --> F["Combined GlobalFilter + GatewayFilter"]
    F --> U["HTTP routing / LB → backend"]
    U --> O["Response trả về client"]
~~~

**Hai câu hỏi cần phân biệt:**

1. **Route selection:** request có khớp predicate và được chọn route dự định không?
2. **Request handling:** sau khi route được chọn, filters và backend có xử lý thành công không?

Một request có thể **khớp route đúng** nhưng trả 401 vì Spring Security, 429 vì limiter, 503 vì backend không có instance, hoặc 502 vì TLS/connection lỗi. Ngược lại, một request không khớp route dự định vẫn có thể trả 200 vì **route dự phòng**, controller local hoặc một route có predicate rộng hơn.

### 2.1. AND giữa các predicate trong một route

Với route có:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Host=catalog.test
  - Header=X-Channel,^partner$
  - Query=mode,^full$
~~~

Điều kiện kết hợp về mặt logic:

\[
\operatorname{match}(r,q)
=P_{\mathrm{path}}(q)
\land P_{\mathrm{method}}(q)
\land P_{\mathrm{host}}(q)
\land P_{\mathrm{header}}(q)
\land P_{\mathrm{query}}(q)
\]

Chỉ cần **một điều kiện false** là route này không được chọn. Đây là quy tắc chung cho các predicate factories được ghép trong một RouteDefinition.

### 2.2. OR bên trong một predicate liệt kê nhiều giá trị

Ví dụ:

~~~yaml
predicates:
  - Method=GET,HEAD
~~~

nghĩa là method thuộc tập GET **hoặc** HEAD. Tương tự:

~~~yaml
predicates:
  - Path=/api/catalog/**,/v2/catalog/**
~~~

chấp nhận một trong hai mẫu path. Nếu route có **hai dòng predicate khác nhau**, cả hai phải đồng thời đạt, trừ khi bạn dùng một custom predicate có logic khác hoặc DSL tự viết.

### 2.3. Một ví dụ cho thấy AND/OR dễ bị nhầm

~~~yaml
predicates:
  - Path=/api/orders/**
  - Path=/api/catalog/**
~~~

Đây **không** tương đương “orders hoặc catalog”: hai predicate cùng áp vào một request, nên thường không thể cùng khớp hai prefix khác nhau. Hãy khai báo **một dòng Path với nhiều patterns**, hoặc hai route definitions riêng theo mục tiêu.

### 2.4. Route order và filter order khác nhau

Khi **nhiều route** cùng có predicate true, Gateway xét thứ tự route runtime. Route có `order` **nhỏ hơn** có ưu tiên cao hơn (ví dụ `-10` trước `10`). Đừng nhầm với thứ tự thực thi GatewayFilter pre/post; đó là cơ chế khác.

Trong kiểm thử, **route được chọn** cần chứng minh bằng route ID, response marker hoặc backend target. Chỉ assert HTTP 200 không phát hiện việc fallback route nhận traffic sai.

## 3. Chiến lược kiểm thử theo ba tầng

| Tầng kiểm thử | Công cụ | Chứng minh được | Chưa chứng minh |
| --- | --- | --- | --- |
| **Predicate unit test** | MockServerWebExchange + factory hoặc custom predicate | Logic của **một** predicate | Route YAML bind đúng, Gateway routing, backend forwarding |
| **Route integration test** | `@SpringBootTest(RANDOM_PORT)`, WebTestClient, stub backend | Bind config, ghép AND, chọn route, filter marker, có/không downstream call | Toàn bộ mạng/TLS/proxy production |
| **End-to-end/staging** | cURL/Postman, ingress, DNS, mTLS, registry thật | Host/Forwarded/headers/CORS và hạ tầng gần thực tế | Mọi tổ hợp input hoặc race condition |

Một thiết kế đáng tin nên có cả **positive** và **negative tests**:

- **Positive:** giữ tất cả điều kiện true, xác nhận route marker và backend nhận đúng request.
- **Negative:** thay **duy nhất một** điều kiện thành false, giữ các điều kiện còn lại đúng và xác nhận **backend không được gọi**.
- **Boundary:** kiểm tra ranh giới regex, slash, case, encoded path, query lặp, time window.
- **Overlap:** thêm route khác có thể nhận request để chứng minh độ ưu tiên.

### 3.1. Vì sao negative tests cần thay một yếu tố mỗi lần?

Nếu test “sai” vừa dùng POST, vừa đổi Host, vừa thiếu Header, vừa đổi Path, ta không biết predicate nào đang chặn. Khi một predicate bị xóa nhầm, test vẫn có thể pass do các điều kiện false còn lại.

Một **bảng quyết định** sẽ giúp nhận diện từng rule:

| Case | Path | Method | Host | X-Channel | Query mode | Kỳ vọng route |
| --- | --- | --- | --- | --- | --- | --- |
| T0 | `/api/catalog/items/42` | GET | catalog.test | partner | full | **Khớp** |
| T1 | `/api/orders/items/42` | GET | catalog.test | partner | full | Không khớp — Path |
| T2 | `/api/catalog/items/42` | POST | catalog.test | partner | full | Không khớp — Method |
| T3 | `/api/catalog/items/42` | GET | wrong.test | partner | full | Không khớp — Host |
| T4 | `/api/catalog/items/42` | GET | catalog.test | *thiếu* | full | Không khớp — Header |
| T5 | `/api/catalog/items/42` | GET | catalog.test | Partner | full | Không khớp — giá trị Header |
| T6 | `/api/catalog/items/42` | GET | catalog.test | partner | *thiếu* | Không khớp — Query |
| T7 | `/api/catalog/items/42` | GET | catalog.test | partner | short | Không khớp — Query regex |
| T8 | `/api/catalog/items/42` | GET | catalog.test | partner | full | Khớp lại để phát hiện test pollution |

Chú ý T5: với regex `^partner$`, **giá trị** `Partner` khác `partner` vì Java regex thường phân biệt hoa/thường. Tên HTTP header như `X-Channel` lại **không phân biệt hoa/thường** theo HTTP semantics — hai quy tắc khác nhau.

## 4. Tạo route kiểm thử có marker quan sát

Để tập trung vào predicate, backend của lab nhận **nguyên path** từ client, không thêm `StripPrefix`. Ta dùng một response marker riêng do Gateway filter thêm:

~~~text
X-Matched-Route: catalog-partner
~~~

Marker này chỉ phục vụ test và chẩn đoán. Không biến nó thành bằng chứng xác thực/authorization của backend; client hoặc proxy cũng có thể tự gửi header có tên giống nhau nếu không có trust boundary.

### 4.1. Spring Cloud Gateway Server WebFlux 5.x

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: predicate-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-partner
              order: -10
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Host=catalog.test
                - Header=X-Channel,^partner$
                - Query=mode,^full$
              filters:
                - AddRequestHeader=X-Downstream-Probe,catalog-partner
                - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

### 4.2. WebFlux 4.2.x / 4.3.x

Ở các dòng WebFlux 4.x, namespace route tương ứng là `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: catalog-partner
          order: -10
          uri: http://127.0.0.1:9091
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Host=catalog.test
            - Header=X-Channel,^partner$
            - Query=mode,^full$
          filters:
            - AddRequestHeader=X-Downstream-Probe,catalog-partner
            - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

Chọn **một** namespace theo version thật: Gateway WebFlux 5.x dùng `spring.cloud.gateway.server.webflux.routes`, còn WebFlux 4.2/4.3 dùng `spring.cloud.gateway.routes`. Tên starter mới `spring-cloud-starter-gateway-server-webflux` được tài liệu 4.3/5.x mô tả; một số dòng 4.x cũ dùng `spring-cloud-starter-gateway`. Hãy để Spring Cloud BOM chọn version tương thích Spring Boot và kiểm tra application type là **reactive**.

### 4.3. Ý nghĩa của route

| Thuộc tính | Vì sao đưa vào lab? |
| --- | --- |
| `id: catalog-partner` | Nhận diện route trong logs và Actuator |
| `order: -10` | Có thể kiểm thử route priority sau này |
| `uri: http://127.0.0.1:9091` | Đích backend kiểm soát được, không phụ thuộc Internet |
| `Path=/api/catalog/**` | Test prefix và segment boundaries |
| `Method=GET` | Phân biệt GET với POST/OPTIONS |
| `Host=catalog.test` | Test Host header/virtual host |
| `Header=X-Channel,^partner$` | Test header name, value regex và thiếu header |
| `Query=mode,^full$` | Test query name/value |
| `AddRequestHeader` | Backend nhận marker chứng minh filter chạy |
| `AddResponseHeader` | Client nhận marker chứng minh route có filter tương ứng |

**Đừng chèn route `Path=/**` làm fallback vào baseline**. Khi có fallback, các negative cases có thể trả 200 từ route khác và test “404 khi không khớp” sẽ thất bại dù predicate chính vẫn đúng. Ta sẽ thử fallback một cách riêng ở mục sau.

### 4.4. Full args và shortcut

Predicate có thể viết dạng ngắn như `Header=X-Channel,^partner$`, hoặc dạng đầy đủ theo field:

~~~yaml
- name: Header
  args:
    header: X-Channel
    regexp: "^partner$"

- name: Query
  args:
    param: mode
    regexp: "^full$"
~~~

Với `Path` có nhiều patterns ở Gateway WebFlux 5.x, tài liệu còn nêu dạng `args` keys được đánh chỉ số như `patterns.0`, `patterns.1` thay vì JSON array trực tiếp khi post route qua Actuator. Kiểm thử **binding của cấu hình thực tế** quan trọng không kém kiểm thử predicate riêng lẻ.

## 5. Backend echo để đo việc request có thực sự được forward

Trong lab thủ công, tạo **hai ứng dụng Spring Boot độc lập**:

| Thành phần | Port | Trách nhiệm |
| --- | ---: | --- |
| Gateway Server WebFlux | `8080` | Chọn route và thêm marker |
| Backend catalog | `9091` | Trả HTTP 200 và đếm số request đến backend |

Backend là một Spring Boot WebFlux project nhỏ với dependency `spring-boot-starter-webflux`. Cấu hình:

~~~yaml
# application.yml của backend
server:
  port: 9091
~~~

Lớp khởi động `src/main/java/demo/catalog/CatalogBackendApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogBackendApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/catalog/CatalogBackendController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogBackendController {

    private final AtomicInteger calls = new AtomicInteger();

    @GetMapping("/api/catalog/items/{id}")
    public Map<String, Object> item(
            @PathVariable String id,
            ServerHttpRequest request) {

        int count = calls.incrementAndGet();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("backend", "catalog-9091");
        result.put("id", id);
        result.put("path", request.getPath().value());
        result.put("method", request.getMethod().name());
        result.put("channel", request.getHeaders()
                .getFirst("X-Channel"));
        result.put("probe", request.getHeaders()
                .getFirst("X-Downstream-Probe"));
        result.put("backendCalls", count);
        return result;
    }

    @GetMapping("/__test/calls")
    public Map<String, Integer> calls() {
        return Map.of("calls", calls.get());
    }
}
~~~

Endpoint `/__test/calls` chỉ dành cho **lab** và **không được công khai trong production**; nếu bị lộ, nó cho phép suy đoán lưu lượng. Trong hệ thống thật, nên dùng metrics có authentication/RBAC, không tạo một HTTP endpoint test không được bảo vệ.

### 5.1. Vì sao counter quan trọng hơn status 404?

Giả sử lệnh tới Gateway với Host sai trả 404. Chỉ có 404 chưa chứng minh predicate Host đã ngăn request; có thể Gateway vẫn forward tới backend và backend trả 404.

Nếu backend counter không tăng **và** route marker không xuất hiện, bằng chứng mạnh hơn:

~~~text
Trước request: backendCalls = 8
Gửi request Host sai: Gateway trả 404
Sau request:   backendCalls = 8
=> backend endpoint thử nghiệm không được gọi
~~~

Counter trên chỉ đếm **đúng handler `/api/catalog/items/{id}`**. Để chứng minh không có **bất kỳ** downstream request nào, hãy dùng mock HTTP server/dispatcher đếm mọi request (mục 8) hoặc backend access logs có correlation ID.

### 5.2. Khởi chạy

Trong hai terminal của hai project:

~~~bash
# Terminal 1, backend
./mvnw spring-boot:run

# Terminal 2, Gateway
./mvnw spring-boot:run
~~~

Trên Windows, dùng `mvnw.cmd spring-boot:run`. Những đoạn mã trong bài là **hướng dẫn để tự thực hành**, không có nghĩa đã build hoặc chạy thực tế trên repository.

Kiểm tra backend trước:

~~~bash
curl -i "http://127.0.0.1:9091/api/catalog/items/42"
curl -sS "http://127.0.0.1:9091/__test/calls"
~~~

Backend phải trả HTTP 200 và đếm thêm một request. Khi kiểm thử qua Gateway, không thay đổi cấu hình backend giữa các ca để tránh nhầm lỗi routing với backend outage.

## 6. Kiểm thử thủ công bằng cURL: đủ điều kiện và thiếu một điều kiện

### 6.1. Positive case: tất cả predicates đều đúng

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
X-Matched-Route: catalog-partner
Content-Type: application/json

{
  "backend": "catalog-9091",
  "id": "42",
  "path": "/api/catalog/items/42",
  "method": "GET",
  "channel": "partner",
  "probe": "catalog-partner",
  "backendCalls": 2
}
~~~

Số `backendCalls` phụ thuộc số request trước đó; không assert bằng 2 trên mọi máy. Cần đối chiếu:

1. HTTP status **200** từ backend.
2. Response header `X-Matched-Route: catalog-partner` từ route đã chọn.
3. Body `backend=catalog-9091` và `probe=catalog-partner` từ backend nhận request.
4. Backend counter tăng đúng **một** lần cho một GET nếu không có retry/filter phụ.

Một HTTP 200 từ controller khác không đủ đáp ứng bốn điều kiện này.

### 6.2. Negative: Path khác

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/orders/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Nếu lab **chỉ có route `catalog-partner` và không có handler khác**, Gateway thường trả 404, không có `X-Matched-Route`. Backend counter phải giữ nguyên.

### 6.3. Negative: Method khác

~~~bash
curl -i -X POST \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Mặc dù `Path/Host/Header/Query` đều đúng, `Method=GET` false. Trong lab chỉ có Gateway route này, thường là 404. Một ứng dụng có các handler khác có thể cho 405 hoặc response khác; **không coi status code là hợp đồng tổng quát của một predicate miss**.

### 6.4. Negative: Host khác

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: wrong.test" \
  -H "X-Channel: partner"
~~~

Trong môi trường HTTPS production, tên Host còn liên quan TLS SNI và reverse proxy routing. Lab HTTP trên localhost cố ý dùng header `Host` để kiểm tra predicate, **không mô phỏng đầy đủ TLS hostname verification**.

### 6.5. Negative: thiếu hoặc sai header

~~~bash
# Thiếu X-Channel
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test"

# Có X-Channel nhưng regex không chấp nhận "Partner"
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: Partner"
~~~

Test thêm tên header viết thường:

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "x-channel: partner"
~~~

HTTP header names không phân biệt hoa/thường nên case cuối **phải khớp**; giá trị vẫn là `partner` đúng regex. Nếu case cuối thất bại, kiểm tra HTTP client/proxy hoặc custom predicate, không mặc định blame Spring regex.

### 6.6. Negative: query thiếu hoặc sai

~~~bash
# Thiếu "mode"
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"

# mode=short không khớp ^full$
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=short" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Query keys và values có thể chịu URL encoding và parsing; khi test tên/value trùng hoặc case khác, hãy xác nhận **những gì WebFlux request thực sự giải mã**. Tránh xây authorization chỉ dựa vào một query predicate có thể bị duplicate/misparse.

### 6.7. Positive lại sau các negative cases

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Phép thử lặp giúp phát hiện test state pollution, thay đổi nhầm route/runtime hoặc backend không sẵn sàng sau một negative case.

## 7. Viết assertions đúng: không chỉ `expectStatus().isOk()`

Nên có ba lớp assertion khi kiểm tra route:

| Nơi đo | Positive case | Negative case |
| --- | --- | --- |
| **HTTP từ Gateway** | Status hợp lệ và marker `X-Matched-Route` đúng | Không có marker của route đó; status phù hợp môi trường cô lập |
| **Backend HTTP stub** | Nhận đúng method/path/header; số calls tăng đúng | Không nhận call nào của request thử |
| **Route inventory / logs** | Route ID và cấu hình đúng | Không có route dự định được chọn; nếu có fallback, nhận diện route khác |

**Marker header không phải chứng cứ duy nhất.** Một proxy có thể lặp hoặc thêm header trùng; một error handler có thể trả status trước khi filter chạy; hoặc backend có thể trả cùng header. Kết hợp **marker của Gateway + backend request count/recording + route ID quan sát** sẽ khó tạo false positive hơn.

Trong một backend stub chỉ dùng cho test, có thể gắn `X-Backend-Id: catalog-stub` vào mọi response. Khi đó:

~~~text
X-Matched-Route: catalog-partner  (Gateway route filter)
X-Backend-Id: catalog-stub       (Backend stub)
~~~

Hai header độc lập giúp phân biệt **route đã match** với **backend đã được gọi**. Với một route không khớp, cả hai phải vắng mặt trong baseline không có fallback/controller khác.

## 8. Integration test tự động bằng WebTestClient và MockWebServer

Đây là phần kiểm thử quan trọng nhất: **Gateway chạy thật trên random port**, còn backend dùng một HTTP stub khởi động trên cổng động. Test không cần biết port 8080/9091 hay phụ thuộc server bên ngoài.

~~~mermaid
flowchart LR
    T["JUnit WebTestClient"] --> G["Gateway WebFlux<br/>RANDOM_PORT"]
    G -->|"chỉ nếu predicate match"| M["MockWebServer<br/>random port"]
    M --> R["RecordedRequest + call counter"]
    G --> H["HTTP response + route marker"]
    H --> T
    R --> T
~~~

### 8.1. Các dependency test

Ví dụ Maven cho project **Gateway Server WebFlux 4.3.x + Spring Boot 3.5.x**, sử dụng Spring Cloud BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- API MockWebServer 4.x được dùng trong code ví dụ -->
    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Cloud dependencies nên được quản lý bằng **Spring Cloud BOM**. MockWebServer 4.12.0 được ghi version tường minh để thống nhất Java API mẫu; đây là **dependency chỉ dành cho test**, không nhúng vào Gateway production. Nếu tổ chức đã dùng MockWebServer 5.x hoặc Spring Boot 4.x, kiểm tra API/packages và test starter của dòng đó trước khi áp mẫu.

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Spring Test. `WebTestClient` đến từ Spring Test/WebFlux trên classpath. Với test thực sự cần xác minh Netty HTTP handling, **RANDOM_PORT** đáng tin hơn unit test chỉ gọi trực tiếp predicate factory.

### 8.2. Lớp khởi động Gateway

`src/main/java/demo/gateway/GatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

Test class đặt dưới package `demo.gateway` để thuộc cùng vùng scan. Đừng thêm một `@Controller` nhận chính path `/api/catalog/**` vào project này, vì nó có thể làm negative test trả response từ handler khác.

### 8.3. application-predicate-test.yml

Đặt tại `src/test/resources/application-predicate-test.yml` cho **Gateway 4.3.x/Boot 3.5.x**, đúng với lớp test Java ở mục 8.4:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-partner
          order: -10
          uri: http://127.0.0.1:${test.stub.port}
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Host=catalog.test
            - Header=X-Channel,^partner$
            - Query=mode,^full$
          filters:
            - AddRequestHeader=X-Downstream-Probe,catalog-partner
            - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

Với `@ActiveProfiles("predicate-test")`, file profile này cung cấp danh sách test routes. Placeholder `${test.stub.port}` được `@DynamicPropertySource` đăng ký từ MockWebServer sau khi backend stub mở cổng.

**Quan trọng:** Nếu có route list ở `application.yml` của main source, cần xác nhận test profile **thay thế đúng danh sách routes**; không để routes khác được nạp từ discovery/Java bean khiến negative cases được xử lý ngoài dự kiến. Trong ví dụ này, profile-specific routes là tập route duy nhất của Gateway.

Đối với **Gateway WebFlux 5.x/Spring Boot 4.x**, giữ nguyên nội dung route nhưng chuyển prefix:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-partner
              order: -10
              uri: http://127.0.0.1:${test.stub.port}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Host=catalog.test
                - Header=X-Channel,^partner$
                - Query=mode,^full$
              filters:
                - AddRequestHeader=X-Downstream-Probe,catalog-partner
                - AddResponseHeader=X-Matched-Route,catalog-partner
~~~

Hai đoạn **không cùng tồn tại trong một test file**. Test Java mục 8.4 có import `@AutoConfigureWebTestClient` của **Spring Boot 3.5.x**; nếu chuyển sang Gateway 5.x/Boot 4.x, cũng phải cập nhật import/test auto-configuration theo Boot 4.x. Khi nâng cấp, migration prefix phải được bao phủ bằng test, vì YAML sai namespace có thể khiến ứng dụng vẫn startup nhưng không có route mong đợi.

### 8.4. Test JUnit 5: tất cả điều kiện đều khớp

`src/test/java/demo/gateway/CatalogPredicateIT.java`:

~~~java
package demo.gateway;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = GatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("predicate-test")
@Execution(ExecutionMode.SAME_THREAD)
class CatalogPredicateIT {

    private static final MockWebServer BACKEND = startBackend();

    @Autowired
    private WebTestClient client;

    @DynamicPropertySource
    static void registerBackendPort(DynamicPropertyRegistry registry) {
        registry.add("test.stub.port", BACKEND::getPort);
    }

    private static MockWebServer startBackend() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "application/json")
                        .addHeader("X-Backend-Id", "catalog-stub")
                        .setBody("{\"backend\":\"catalog-stub\"}");
            }
        });

        try {
            server.start(); // Port ngẫu nhiên trên localhost
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
        return server;
    }

    @AfterAll
    static void stopBackend() throws IOException {
        BACKEND.shutdown();
    }

    @Test
    void allPredicatesMatchAndForwardToBackend()
            throws InterruptedException {

        int before = BACKEND.getRequestCount();

        client.get()
                .uri("/api/catalog/items/42?mode=full")
                .header(HttpHeaders.HOST, "catalog.test")
                .header("X-Channel", "partner")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Matched-Route", "catalog-partner")
                .expectHeader().valueEquals(
                        "X-Backend-Id", "catalog-stub")
                .expectBody()
                .jsonPath("$.backend").isEqualTo("catalog-stub");

        assertThat(BACKEND.getRequestCount())
                .isEqualTo(before + 1);

        RecordedRequest request =
                BACKEND.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath())
                .isEqualTo("/api/catalog/items/42?mode=full");
        assertThat(request.getHeader("X-Downstream-Probe"))
                .isEqualTo("catalog-partner");
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("negativeCases")
    void onePredicateFailsSoBackendIsNotCalled(
            String caseName,
            HttpMethod method,
            String pathAndQuery,
            String host,
            String channel) {

        int before = BACKEND.getRequestCount();

        WebTestClient.RequestHeadersSpec<?> request =
                client.method(method)
                        .uri(pathAndQuery)
                        .header(HttpHeaders.HOST, host);

        if (channel != null) {
            request.header("X-Channel", channel);
        }

        request.exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Matched-Route")
                .expectHeader().doesNotExist("X-Backend-Id");

        assertThat(BACKEND.getRequestCount())
                .as(caseName + " must not hit the backend")
                .isEqualTo(before);
    }

    static Stream<Arguments> negativeCases() {
        return Stream.of(
                Arguments.of("wrong path", HttpMethod.GET,
                        "/api/orders/items/42?mode=full",
                        "catalog.test", "partner"),
                Arguments.of("wrong method", HttpMethod.POST,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", "partner"),
                Arguments.of("wrong host", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "wrong.test", "partner"),
                Arguments.of("missing header", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", null),
                Arguments.of("wrong header value", HttpMethod.GET,
                        "/api/catalog/items/42?mode=full",
                        "catalog.test", "Partner"),
                Arguments.of("missing query", HttpMethod.GET,
                        "/api/catalog/items/42",
                        "catalog.test", "partner"),
                Arguments.of("wrong query value", HttpMethod.GET,
                        "/api/catalog/items/42?mode=short",
                        "catalog.test", "partner")
        );
    }
}
~~~

### 8.5. Đọc kỹ test để tránh false positives

- `@SpringBootTest(RANDOM_PORT)` chạy Gateway với **HTTP server thật**, không chỉ mock factory. Từ Spring Boot 3.x, `@AutoConfigureWebTestClient` có import `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`; Boot 4.x tái tổ chức một số test auto-config packages.
- `@DynamicPropertySource` đưa cổng của MockWebServer vào URI route **trước khi application context bind config**. Không hardcode port 9091 khiến test CI xung đột.
- Stub dùng `Dispatcher` trả một response nhất quán cho mọi downstream request và đếm qua `getRequestCount()`, nên **negative test không cần enqueue response**.
- Positive test xác nhận **route marker**, **backend marker**, **đúng path/method/header downstream** và số backend calls tăng một.
- Negative cases chỉ đổi một yếu tố, assert **không có marker** và **backend calls không tăng**.
- `@Execution(SAME_THREAD)` tránh test methods trong class chạy song song trên cùng counter. Các test classes khác không được dùng chung stub static này.
- `BACKEND.takeRequest(...)` chỉ gọi ở positive test, đọc một recorded request và có timeout 1 giây; không để test treo vô hạn.
- Response HTTP 404 cho negative case là kỳ vọng **của fixture cô lập không có route hoặc handler dự phòng**. Nếu môi trường có fallback, phải đổi assertion sang **route ID/target được chọn**, không coi 404 là quy tắc tổng quát của predicate.

### 8.6. Lệnh chạy và phạm vi báo cáo

Ví dụ Maven:

~~~bash
./mvnw -Dtest=CatalogPredicateIT test
~~~

Tên test có hậu tố `IT` có thể bị cấu hình plugin phân loại sang **Failsafe integration-test** thay vì Surefire. Nếu Maven Surefire trong dự án không chạy `*IT` theo mặc định, hãy cấu hình test includes hoặc đổi tên thành `CatalogPredicateTest`, rồi dùng tên mới trong lệnh. Trong CI chạy đúng goal của plugin đang được dùng, tránh báo build “xanh” trong khi **0 tests executed**.

Ví dụ này chỉ định **mẫu code để học và tự chạy**, chưa được build/test ở repository hiện tại. Khi viết test thật, cần khớp chính xác version của Spring Boot, Spring Cloud Gateway, Java/JUnit và MockWebServer.

## 9. Unit test một predicate factory: nhanh nhưng không thay integration test

Khi đang phát triển **custom RoutePredicateFactory** hoặc cần kiểm tra logic regex của một built-in, có thể dựng một `MockServerWebExchange` mà không khởi động HTTP server.

Ví dụ sau sử dụng `HeaderRoutePredicateFactory` trên Gateway Server WebFlux:

~~~java
package demo.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.handler.predicate
        .HeaderRoutePredicateFactory;
import org.springframework.mock.http.server.reactive
        .MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class HeaderPredicateUnitTest {

    @Test
    void matchesOnlyExpectedHeaderValue() {
        var config = new HeaderRoutePredicateFactory.Config();
        config.setHeader("X-Channel");
        config.setRegexp("^partner$");

        var predicate = new HeaderRoutePredicateFactory()
                .apply(config);

        var matching = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42")
                        .header("X-Channel", "partner"));

        var wrongValue = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42")
                        .header("X-Channel", "Partner"));

        var missingHeader = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("/api/catalog/items/42"));

        assertThat(predicate.test(matching)).isTrue();
        assertThat(predicate.test(wrongValue)).isFalse();
        assertThat(predicate.test(missingHeader)).isFalse();
    }
}
~~~

Nếu signature constructor/setter thay đổi giữa Gateway patches, đối chiếu Javadoc của đúng artifact. **Bài kiểm tra factory này không chứng minh**:

- `Header=X-Channel,^partner$` được binder đọc đúng từ YAML.
- Route có đủ bốn predicate còn lại.
- Route `catalog-partner` có priority mong muốn.
- Request đi qua filters và tới backend nào.

Đó là lý do **unit test nhanh + HTTP integration test** bổ sung cho nhau thay vì thay thế nhau.

### 9.1. Kiểm thử custom predicate có các quy tắc khác built-in

Nếu một dự án tự viết `TenantPlanRoutePredicateFactory`, phải test:

1. Binding của `Config`: tên trường, kiểu, null/default, regex/range.
2. Positive/negative với `ServerWebExchange` giả lập.
3. Behavior khi field hoặc header không có.
4. Exception/error behavior nếu config sai hoặc dependency lookup không sẵn sàng.
5. Performance, thread safety và tác động của việc đọc body/remote address.

**Không cho rằng predicate đồng nghĩa authorization.** Predicate chỉ chọn route; kiểm tra quyền truy cập tenant/resource cần dựa vào danh tính đã xác minh và policy an toàn.

## 10. Những góc cạnh phải có trong test suite

### 10.1. Path: prefix, slash và URL encoding

Các mẫu path cần phân biệt:

~~~yaml
- Path=/api/catalog/**
- Path=/api/catalog/{id}
- Path=/api/catalog/items/{id}
~~~

Chúng **không tương đương**. Wildcard `**` cho phép một phạm vi path rộng; mẫu `{id}` đại diện một biến URI template tại vị trí tương ứng. Các ca nên kiểm:

| Request path | Câu hỏi cần trả lời |
| --- | --- |
| `/api/catalog/items/42` | Ca chính có khớp không? |
| `/api/catalog/items/42/` | Trailing slash có được chấp nhận? |
| `/api/catalog` | Wildcard có chấp nhận root segment? |
| `/api/catalog/` | Root với slash khác thế nào? |
| `/api/catalogue/items/42` | Prefix gần giống có bị loại? |
| `/API/catalog/items/42` | Case sensitivity có đúng contract? |
| `/api/catalog/items/%34%32` | Đường dẫn đã decode và URI variable thế nào? |
| `/api/catalog/items/%2Fetc` | Encoded slash được tầng proxy/container xử lý ra sao? |
| `/api/catalog/../admin` | Dot segments có bị normalize trước predicate? |

Tài liệu Gateway WebFlux mô tả `Path` có tùy chọn `matchTrailingSlash`; trong các dòng được tham khảo, **mặc định true**. Muốn test slash nghiêm ngặt, cấu hình dạng đầy đủ:

~~~yaml
- name: Path
  args:
    patterns.0: /api/catalog/items/{id}
    matchTrailingSlash: false
~~~

Đối với `Path=/api/catalog/**` của lab, `matchTrailingSlash` có thể **không đủ để phân biệt tất cả các path** do `**` đã rất rộng. Khi API cần đúng một segment/format, hãy chọn pattern hẹp hơn và có tests tương ứng.

**Quan trọng:** Nếu đặt `spring.webflux.base-path`, tài liệu Gateway nêu nó ảnh hưởng cách path predicate được diễn giải (base path được thêm vào patterns). Đừng dùng test trên `/api/catalog/**` ở local mà bỏ qua base path khác tại staging.

### 10.2. Path rewrite/filter không xảy ra trước route selection

Với route:

~~~yaml
predicates:
  - Path=/external/**
filters:
  - StripPrefix=1
~~~

Predicate kiểm tra **đường dẫn client tới Gateway**. `StripPrefix` chỉ có tác dụng khi route đã được chọn, vì nó là **GatewayFilter**. Do vậy:

- `GET /external/items/42` có thể chọn route, rồi backend nhận `/items/42`.
- `GET /items/42` không tự khớp route chỉ vì sau strip prefix hai path giống nhau.

Trong test, hãy khẳng định cả **path client** lẫn **path backend**. Nếu chỉ nhìn backend response, có thể bỏ sót một route predicate rộng sai hoặc một rewrite không như mong đợi.

### 10.3. Method: GET khác HEAD/OPTIONS/POST

Ví dụ:

~~~yaml
- Method=GET
~~~

không có nghĩa mọi method “liên quan đến GET” đều mặc định khớp. Kiểm tra riêng `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH` và `DELETE` khi route cần bảo vệ quyền truy cập theo phương thức.

Nếu muốn nhiều methods:

~~~yaml
- Method=GET,HEAD
~~~

Khi có browser CORS preflight, request `OPTIONS` có thể bị Gateway route predicate loại, hoặc được xử lý ở lớp CORS khác trước khi backend thấy request. Một `OPTIONS 200` do CORS middleware trả **không chứng minh** route dành cho GET được chọn.

### 10.4. Header và cookie: tên có mặt chưa chắc giá trị phù hợp

Header predicate:

~~~yaml
- Header=X-Channel,^partner$
~~~

Test đủ:

- Header không tồn tại.
- Header có giá trị rỗng.
- `partner` khớp.
- `Partner`, `partner-extra` hoặc `other` không khớp.
- Header name viết thường `x-channel` vẫn phải được HTTP stack nhận như cùng tên.
- Nhiều giá trị/header lặp, dấu phẩy/space và độ dài lớn.

Cookie predicate có dạng:

~~~yaml
- Cookie=region,^(north|south)$
~~~

Các ca:

~~~http
Cookie: region=north
Cookie: region=east
Cookie: session=abc
~~~

Tương ứng cần phân biệt **khớp, không khớp giá trị, thiếu cookie**. Nhưng cookie do trình duyệt/client gửi **không phải bằng chứng quyền truy cập**; cookie authentication phải được xác minh chữ ký/session/CSRF và policy đúng.

### 10.5. Query: missing, regex, duplicate keys

~~~yaml
- Query=mode,^full$
~~~

Khác với:

~~~yaml
- Query=mode
~~~

Dạng có regex bắt buộc tham số có giá trị theo pattern; dạng chỉ có tên tập trung vào sự hiện diện của tham số. Test:

~~~text
?mode=full
?mode=short
?mode=
?other=full
?mode=full&mode=short
?mode=full%20
?Mode=full
~~~

Với duplicate keys, thứ tự values và behavior của phiên bản Gateway/Spring khi kiểm tra regex cần **được xác minh thật**, không dùng một giá trị đầu hoặc cuối theo giả định. Nếu downstream cho phép multi-value query, kiểm thử cả **giá trị đến backend** để tránh parameter pollution.

### 10.6. Host: virtual host không đồng nghĩa người gọi đáng tin

~~~yaml
- Host=**.example.test
~~~

Host predicate có thể dùng patterns và URI template variables như `{sub}.example.test`. Nhưng trong môi trường HTTP local, client có thể sửa Host:

~~~bash
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Điều này phù hợp để **test route matching**, không phù hợp để chứng minh client là “đối tác đã xác thực”. Production cần kiểm tra:

1. Public ingress chỉ nhận các hosts được phép.
2. TLS SNI/certificate và HTTP Host có tương thích.
3. Reverse proxy có giữ hoặc rewrite Host theo thiết kế.
4. Không có đường truy cập bypass ingress tới Gateway mà khách hàng tự giả Host.
5. Không dùng Host một mình thay authentication/authorization.

### 10.7. RemoteAddr và XForwardedRemoteAddr

Predicate:

~~~yaml
- RemoteAddr=10.10.0.0/16
~~~

đánh giá địa chỉ remote theo resolver của Gateway. Khi Gateway sau reverse proxy, remote socket address có thể là **IP của proxy**, không phải IP client thật. Đừng cố “test IP client” bằng cách chỉ thêm:

~~~http
X-Forwarded-For: 10.10.1.55
~~~

rồi kết luận `RemoteAddr` chắc chắn nhận 10.10.1.55. WebFlux Gateway còn hỗ trợ resolver/các predicate dựa X-Forwarded-For trong một số phiên bản; cấu hình trust cần tuân theo **số lượng proxy đáng tin**, không dùng `trustAll` cho traffic untrusted.

Test hai lớp:

- **Unit/integration trong network giả lập:** cung cấp remote address mong muốn bằng mock exchange hoặc một reverse proxy test.
- **Staging qua edge thật:** gửi request từ IP cho phép và không cho phép, thử spoofed XFF; ghi lại địa chỉ được resolver chọn.

Không dùng Client IP header không đáng tin để mở một route quản trị hoặc bỏ qua xác thực.

### 10.8. After, Before, Between: thời gian làm test dễ chập chờn

Các predicate theo thời gian của Gateway nhận `ZonedDateTime`:

~~~yaml
predicates:
  - After=2020-01-01T00:00:00Z
  - Before=2100-01-01T00:00:00Z
~~~

Ví dụ này mô tả cửa sổ rộng để dạy cú pháp, **không phải policy production**. Với `Between`, cần có cả thời điểm bắt đầu và kết thúc, thời điểm thứ hai phải sau thời điểm thứ nhất.

Những test dễ flaky:

~~~text
now + 100 ms -> request bắt đầu
CI tải cao/GC/pipeline chậm -> request tới Gateway muộn hơn dự kiến
=> assertion sai tùy thời gian máy
~~~

Nguyên tắc:

1. Không dùng ranh giới cách thời gian hiện tại vài mili giây trong integration test HTTP.
2. Chọn **mốc far-past/far-future** khi chỉ cần chứng minh nhánh match/nonmatch ở mức cơ bản.
3. Muốn test chính xác hành vi ngay trên ranh giới, nên tách logic thời gian vào **custom predicate dùng `Clock` có thể inject** hoặc một lớp có thể test trực tiếp. Đừng giả định built-in After/Before/Between tự hỗ trợ mock `Clock` trong mọi version.
4. Dùng UTC hoặc timezone có offset/zone rõ ràng; tránh thời điểm mơ hồ lúc đổi DST.
5. Kiểm tra đồng hồ giữa các Gateway replica khi policy phụ thuộc thời gian.

### 10.9. Version predicate là feature theo phiên bản

Gateway WebFlux 5.x có `Version` predicate tích hợp với API versioning của Spring Framework. Một route:

~~~yaml
predicates:
  - Path=/api/**
  - Version=1.3
~~~

chỉ có ý nghĩa đúng khi đã cấu hình **`ApiVersionStrategy`** để đọc version từ header, query, media-type parameter hoặc path. Tài liệu Gateway 5.x lưu ý: **nếu không cấu hình strategy, Version predicate có thể luôn pass** do request không có resolved version được xem là matching.

Vì vậy, khi áp Version predicate cần:

- Test có/không có header/query version.
- Test đúng version, version khác, version malformed.
- Test ứng dụng **thật sự đăng ký version resolver**.
- Test route ID được chọn khi có nhiều versions.
- Không coi Version predicate tự bảo đảm authentication hay compatibility contract.

Không bê `Version` của WebFlux 5.x vào project Gateway 4.2 mà không xác minh feature/version tương ứng.

### 10.10. ReadBody và các predicate có chi phí body

Gateway WebFlux hỗ trợ `ReadBody` predicate theo Java DSL:

~~~java
// Đoạn mô tả từ Java DSL, không phải YAML có lambda.
.route("body-route", r -> r
        .readBody(String.class, body -> body.contains("yes"))
        .uri("http://127.0.0.1:9091"))
~~~

Theo tài liệu Gateway 4.3/5.x được tham khảo, `ReadBody` cần một Java `Predicate<T>`, **không thể biểu diễn lambda trực tiếp bằng cấu hình YAML**. Predicate đọc và cache request body để các bước sau có thể đọc lại.

Negative tests ở đây cần kiểm tra:

- Body đúng/sai/empty/malformed.
- Codec, Content-Type và charset.
- Large payload vượt limit và memory usage.
- Body có thể replay xuống backend sau khi predicate đã đọc.
- Concurrent requests và cancellation, tránh buffer retention.

Đừng dùng predicate đọc body trên mọi request chỉ để nhận diện một header đơn giản: tăng chi phí CPU/heap/direct buffers và có thể tác động tới streaming.

### 10.11. Weight predicate không phải sự lựa chọn định tuyến chắc chắn từng request

Một hệ thống chia traffic theo nhóm weight, ví dụ 80/20, có **kết quả thống kê**. Không viết test:

~~~text
Gửi một GET → bắt buộc route A vì weight A = 80
~~~

Một request riêng lẻ có thể rơi vào route B. Cách phù hợp:

1. Unit test cấu hình/đăng ký nhóm weight.
2. Integration test gửi đủ sample requests, đo phân bố với khoảng sai số hợp lý.
3. Tránh assert chính xác tuyệt đối 80/20 vì thuật toán ngẫu nhiên và đồng thời.
4. Với logic cần hoàn toàn deterministic, tách bộ chọn hoặc inject nguồn random có thể điều khiển trong unit tests.
5. Kiểm tra routing security/policy giống nhau giữa các nhánh, không chỉ tỉ lệ.

Không dùng weight như giải pháp bảo đảm một tenant luôn vào cùng instance; đó là yêu cầu sticky routing/session affinity riêng.

## 11. Route chồng lấn, fallback và thứ tự ưu tiên

Đây là ca dễ tạo **false positive nhất** trong kiểm thử predicate. Hãy tưởng tượng hai tuyến:

~~~yaml
# Chỉ là đoạn routes, đặt dưới namespace phù hợp version.
- id: catalog-partner
  order: -10
  uri: http://127.0.0.1:9091
  predicates:
    - Path=/api/catalog/**
    - Method=GET
    - Host=catalog.test
    - Header=X-Channel,^partner$
    - Query=mode,^full$
  filters:
    - AddResponseHeader=X-Matched-Route,catalog-partner

- id: catalog-fallback
  order: 100
  uri: http://127.0.0.1:9091
  predicates:
    - Path=/api/catalog/**
    - Method=GET
  filters:
    - AddResponseHeader=X-Matched-Route,catalog-fallback
~~~

**Route thứ hai là một fallback có chủ đích** cho GET catalog; nó không phân biệt Host/Header/Query. Chỉ bật trong **bộ test riêng**: nếu thêm nó vào profile `predicate-test` ở mục 8, các negative cases của partner route không còn kỳ vọng 404 hoặc backend call count giữ nguyên.

### 11.1. Ma trận khi có fallback

| Request | Route partner match? | Route fallback match? | Kỳ vọng được chọn |
| --- | --- | --- | --- |
| GET đúng Path/Host/Header/Query | Có | Có | `catalog-partner` vì order -10 trước 100 |
| GET đúng Path, sai Host | Không | Có | `catalog-fallback` |
| GET đúng Path, thiếu Header | Không | Có | `catalog-fallback` |
| GET đúng Path, sai Query | Không | Có | `catalog-fallback` |
| POST đúng Path | Không | Không | Không có route trong fixture này |
| GET Path khác | Không | Không | Không có route trong fixture này |

Ví dụ GET Host sai **có thể trả HTTP 200** từ fallback. Đó không phải bug của predicate Host: route partner đã bị loại, route khác được chọn. Nếu ứng dụng coi partner route là đường duy nhất được phép, fallback rộng như vậy có thể trở thành **lỗ hổng authorization**.

### 11.2. Test chọn đúng route khi cả hai cùng match

Với request hợp lệ:

~~~bash
curl -i \
  "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "Host: catalog.test" \
  -H "X-Channel: partner"
~~~

Kỳ vọng:

~~~text
HTTP 200
X-Matched-Route: catalog-partner
~~~

Nếu header là `catalog-fallback` dù cả hai match, hãy kiểm tra:

- `order` thực tế đã bind đúng không?
- Route partner có bị thiếu predicate/định nghĩa lỗi nên không materialize không?
- Host, query, header mà Gateway nhận đã bị ingress rewrite chưa?
- Có route thứ ba ưu tiên cao hơn không?
- Route definitions trong cache có cùng revision trên các Gateway replicas không?

### 11.3. Test fallback không vô tình nhận request đặc quyền

Một quyết định thiết kế có thể là **không cho fallback nhận path dành cho đối tác**, thay vì chỉ dựa vào thứ tự:

~~~yaml
predicates:
  - Path=/public/catalog/**
  - Method=GET
~~~

Khi tách namespace public/partner, bạn có thể test chéo để đảm bảo request thuộc `/api/catalog/**` không bao giờ đi vào `/public/catalog/**`. Tuy nhiên, nếu security cần dựa trên token/role, hãy sử dụng Spring Security và backend authorization; **cách đặt path/route predicate không phải security boundary đầy đủ**.

### 11.4. Đừng dùng route ID trùng hoặc order tie không có chủ đích

Hai routes cùng ID từ nhiều nguồn (YAML, Config Server, Redis, Java DSL) có thể khiến quan sát/refresh không xác định theo kỳ vọng và gây lỗi materialization. Với hai routes cùng predicate và cùng `order`, hành vi chọn một route cụ thể **không nên được dùng như hợp đồng kinh doanh** nếu không có tie-breaker đã được tài liệu hóa và kiểm chứng trong phiên bản thực tế.

Trong test setup, nên:

- Gán ID duy nhất.
- Gán order rõ ràng khi predicates có thể chồng lấn.
- Kiểm tra cả positive và negative cho mỗi route trong nhóm.
- Có route marker hoặc backend target riêng để biết route nào thực sự chạy.

## 12. Negative route test khác negative security test

Predicate trả false có thể làm request **không đi vào route này**, nhưng không tự bảo vệ toàn Gateway hoặc backend khỏi request nguy hiểm. Ví dụ:

~~~yaml
- Host=admin.example.test
- Header=X-Is-Admin,^true$
~~~

Hai điều kiện này chỉ kiểm tra **Host và header do client có thể khai**. Không được coi chúng là authentication. Client có thể gửi:

~~~bash
curl "http://127.0.0.1:8080/admin" \
  -H "Host: admin.example.test" \
  -H "X-Is-Admin: true"
~~~

Do đó, với routes nhạy cảm phải test:

| Loại kiểm thử | Đòi hỏi |
| --- | --- |
| Predicate selection | Route đúng có/không được chọn theo path/method/host/header/query |
| Authentication | Anonymous, expired token, bad issuer/audience, signed token hợp lệ |
| Authorization | Principal đúng nhưng thiếu role/scope/tenant permission |
| Backend trust | Header identity giả từ client bị loại bỏ, backend xác minh context |
| Rate limiting | Quota key tin cậy, 429, store outage, không bypass qua fallback |
| CORS/CSRF | OPTIONS preflight, browser credentials, request state-changing |
| Host/forwarded trust | Client giả Host, X-Forwarded-For/Proto, proxy bypass |
| TLS | HTTPS, SNI/certificate, downstream TLS/mTLS và downgrade policy |

**Một test predicate đúng không chứng minh security hoàn chỉnh.** Khi thêm route mới, cần chạy cả matrix bảo mật và kiểm tra các filter được áp lên **route thực tế đã chọn**, không chỉ một route trong YAML.

### 12.1. Đường CORS OPTIONS là trường hợp đặc biệt

Browser có thể gửi:

~~~http
OPTIONS /api/catalog/items/42 HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: X-Channel
~~~

Vì route của lab có `Method=GET`, request OPTIONS **không khớp** theo phương thức. Nhưng Gateway/Spring CORS handler có thể xử lý preflight theo cấu hình riêng; việc preflight trả 200/204 không có nghĩa route GET đã được forward tới backend.

Phải tách ba assertions:

1. OPTIONS preflight trả CORS headers theo policy (nếu CORS được bật).
2. Backend **không được gọi** bởi preflight khi chỉ cần xử lý ở Gateway.
3. Actual GET với Origin/headers hợp lệ mới đi đúng route và có response CORS hợp lệ.

Không tự tạo wildcard `Access-Control-Allow-Origin: *` cho request có credentials và không dùng CORS làm authentication.

### 12.2. Predicate header không thay thế filter header

`Header=X-Channel,^partner$` chỉ dùng header để **chọn route**. Nó không tự xóa header client, xác minh chữ ký hoặc gắn identity đáng tin cho downstream. Nếu backend tin một marker `X-Partner-ID`, phải:

- Xác thực đối tác bằng cơ chế thật.
- Loại bỏ các header mà client có thể giả mạo.
- Tạo marker mới từ security context đã xác minh.
- Kết nối tới backend trên trust boundary phù hợp.
- Test backend nhận đúng một giá trị đã được xác minh.

Predicate kết hợp với **GatewayFilter** hoặc WebFilter/Spring Security có vai trò khác nhau. Từng lớp phải có test riêng.

## 13. Chẩn đoán khi kết quả test không đúng mong đợi

### 13.1. Tự hỏi “có route nào đã được dựng không?”

Một negative test trả 404 có thể xảy ra vì **route không khớp**, nhưng cũng có thể bởi route YAML **không được load** do sai prefix, thiếu starter, không có bean predicate factory hoặc binding errors.

Trước khi đánh giá logic Path/Header/Host, xác minh **route runtime tồn tại**:

1. Gateway startup không có lỗi cấu hình.
2. Route ID `catalog-partner` xuất hiện trong runtime route list.
3. Predicate strings tương ứng với cấu hình kỳ vọng.
4. Với request hoàn toàn hợp lệ, Gateway thực sự forward tới backend.
5. Stub backend còn sống và không bị xung đột cổng.

Nếu positive case đã thất bại, **không nên tin negative cases** ngay cả khi tất cả đều trả 404.

### 13.2. Actuator chỉ giúp kiểm tra cấu hình route, không chứng minh một request đã match

Khi Spring Boot Actuator được bật **trong management plane riêng**, Gateway WebFlux có thể cung cấp:

~~~bash
# Chỉ chạy trên cổng quản trị nội bộ được cho phép:
curl -sS "http://127.0.0.1:9090/actuator/gateway/routes"

curl -sS \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-partner"
~~~

Đó là các endpoint quan sát route runtime; chúng giúp xác minh route ID, URI, predicate, filters và order. Tuy nhiên **GET /actuator/gateway/routes** chỉ cho biết route **được đăng ký**, không ghi nhận từng request nào đã đi qua route đó.

Trong ví dụ tích hợp mục 8, **không cần mở Actuator** để test: response markers và MockWebServer đã đủ. Khi dùng Actuator ở staging:

- Hạn chế `management.endpoint.gateway.access=read-only`.
- Expose chỉ endpoints cần thiết, yêu cầu authentication/RBAC.
- Không expose `/actuator/gateway/routes` hoặc write/refresh ra Internet.
- Nếu routes có thể refresh từ DB/Config Server, xác minh mỗi replica đã nhận revision dự kiến.

### 13.3. Logging có thể giúp, nhưng không thay assertions

Khi debug tại môi trường cô lập:

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
~~~

Logging có thể chỉ ra route matching/factory/errors theo phiên bản. Không bật DEBUG/TRACE kéo dài trong production; đặc biệt không ghi nguyên `Authorization`, `Cookie`, raw body, query credentials hoặc IP/tenant PII.

Một trace hữu ích nên phân biệt:

~~~text
requestId = test-123
selectedRouteId = catalog-partner
downstreamHost = 127.0.0.1:9091
responseStatus = 200
downstreamAttempts = 1
~~~

Tên trường chỉ là **ví dụ observability tự thiết kế**, không khẳng định Gateway mặc định xuất đầy đủ bốn fields. Cần giữ correlation ID an toàn, không để client chèn ký tự điều khiển vào logs.

### 13.4. Vì sao 502/503 khác predicate miss?

Xét:

~~~text
Predicate match = true
  → chọn route đúng
  → Gateway gọi backend
  → backend port đóng
  → HTTP 5xx do transport / unavailable
~~~

Đây là **route selection thành công, upstream call thất bại**. Nếu test chỉ có:

~~~java
client.get()
        .uri("/api/catalog/items/42?mode=full")
        .exchange()
        .expectStatus().isOk();
~~~

thì nó không cho biết lỗi ở predicate hay backend. Phải bổ sung Host/Header, kiểm tra route tồn tại, backend stub, response marker và logs. Một số filter có thể không thêm marker lên response khi lỗi xảy ra trước pha ghi headers; **đừng coi marker vắng mặt là bằng chứng duy nhất không khớp route**.

### 13.5. Cách tránh test “xanh” vì một handler khác

Khi chạy test Gateway, hạn chế việc scan các controllers không liên quan. Có thể:

- Tạo một **test application** chỉ chứa Gateway route config.
- Dùng `@SpringBootTest(classes = GatewayApplication.class)` ở package rõ ràng.
- Tắt discovery locator và nguồn route phụ trong profile test nếu có.
- Gán route IDs duy nhất, tránh nhiều routes đồng thời trùng path.
- Assert **backend recording** ngoài HTTP status.

Nếu project dùng service discovery tự tạo routes, negative cases có thể được một route từ discovery nhận. Khi đó cần tắt discovery locator trong fixture hoặc viết test xác nhận route được chọn cụ thể theo phạm vi mong muốn.

## 14. Thiết kế CI để kết quả ổn định và có thể điều tra

### 14.1. Không phụ thuộc backend Internet

Một route integration test không nên định tuyến tới:

~~~yaml
uri: https://some-public-api.example
~~~

rồi assert 200. Internet có thể lỗi DNS, TLS, rate limit, WAF, traffic policy hoặc trả nội dung khác theo thời gian. **MockWebServer hoặc WireMock trên random port** giúp test độc lập mạng ngoài và có recorded requests.

### 14.2. Quản lý test state

| Nguồn state | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Gateway port cố định | Xung đột khi chạy song song | `RANDOM_PORT` |
| Backend port cố định | Xung đột port trên CI | Mock backend random port |
| Stub response queue | Response cũ rơi vào test sau | Dispatcher không phụ thuộc queue hoặc reset rõ ràng |
| Shared request count | Parallel tests gây sai số | Chạy tuần tự trong fixture hoặc tạo stub riêng cho mỗi test |
| Gateway route cache | Fixture vẫn dùng route từ test khác | Isolated context/profile/revision |
| Discovery registry | Instances thay đổi ngoài test | Stub registry hoặc tắt auto-discovery |
| Time predicate | Clock/timezone thay đổi | Mốc xa ranh giới hoặc Clock có thể kiểm soát |
| Retry/timeout | Một request có nhiều backend calls | Vô hiệu retry trong predicate-only fixture hoặc assert theo policy |
| Security middleware | 401/403 chặn trước routing | Dùng test security setup có chủ đích |

### 14.3. Test với fallback phải có class/profile riêng

Khi bổ sung route fallback, ta đã **đổi contract**: negative của route chính không còn nghĩa “backend không được gọi”. Nên tách:

- `PredicateStrictRouteIT`: duy nhất một route, negative = no downstream calls/404.
- `PredicateFallbackRouteIT`: hai routes, negative của route chính = **fallback được chọn**, route marker tương ứng, backend nào nhận call.
- `PredicateSecurityIT`: kiểm thử auth, role/scope, tenant boundaries và CORS.

Không lấy lại một phương thức kiểm thử “expect 404” cho mọi môi trường một cách máy móc.

### 14.4. Mutation tests và khả năng bắt regression

Một cách đánh giá ma trận negative có đủ mạnh là **cố tình bỏ từng predicate trong test branch**:

~~~text
Bỏ Method=GET  -> test POST phải thất bại
Bỏ Host=...    -> test wrong Host phải thất bại
Bỏ Header=...  -> test missing/wrong Header phải thất bại
Bỏ Query=...   -> test missing/wrong Query phải thất bại
Bỏ Path=...    -> test wrong Path phải thất bại
~~~

Nếu bỏ predicate mà bộ test vẫn pass, có thể **test chưa thực sự kiểm soát điều kiện đó**, đã bị một route/filter khác chặn hoặc đang assert nhầm behavior. Không cần dùng mutation testing framework mới có thể làm phép thử tư duy này, nhưng nên đưa vào review đối với routes nhạy cảm.

### 14.5. Tiêu chí hoàn thành một pipeline test

Trong báo cáo CI, nên ghi:

~~~text
Test suite: predicate-routing
Version: Spring Boot + Spring Cloud Gateway (exact BOM)
Profiles: predicate-test
Test backend: MockWebServer random port
Positive cases passed: 1 or more
Negative cases passed: 7 or more
Backend unexpected calls: 0
Unmatched route observations: expected
Test failures: 0
~~~

Đây là **mẫu báo cáo**, không phải kết quả đã chạy của bài này. Không báo “PASS” nếu Maven/Gradle thực tế chạy **0 tests** hoặc chỉ build mà không thực hiện integration tests.

## 15. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Mọi request đều 404, kể cả positive | Route không được load, YAML sai prefix, thiếu starter | Route inventory/logs, profile, BOM, route ID |
| Positive trả 404, backend không nhận call | Một predicate false: Host/Header/Query/Path/Method | Đối chiếu request raw và ma trận T0 |
| Positive trả 502/503 | Route có thể match, backend/transport lỗi | Stub port, DNS, TLS, timeout, error mapping |
| Positive 200 nhưng sai route marker | Route khác có order cao hơn hoặc filters khác | Route priority và predicates overlap |
| Negative Host trả 200 | Fallback route match, Host header bị rewrite, predicate thiếu | Marker route/backend, Ingress/proxy behavior |
| Negative Method trả 405 thay 404 | Servlet/WebFlux handler khác hoặc method handling | Kiểm tra HandlerMapping/route list |
| Negative Header vẫn match | Header không được cấu hình, regex rộng, header lặp | Full args/shortcut, actual headers |
| Header name lowercase bị reject | Custom code/proxy normalize sai | HTTP header semantics, request captured |
| Query `?mode=full&mode=short` cho kết quả lạ | Duplicate query values và parser behavior | Recorded request, resolver, route predicate implementation |
| Slash case khác local và staging | Base-path, ingress rewrite, URL decoding, matcher config | Raw incoming path tại Gateway |
| `RemoteAddr` không thấy IP client | Peer là reverse proxy; XFF không được resolver dùng | Trusted proxy topology và resolver |
| XFF giả được chấp nhận | Trust-all hoặc ingress không sanitize | Spoofing negative tests |
| OPTIONS trả 200 nhưng GET không forward | CORS preflight độc lập route GET | Actual request, backend call count |
| Test backend count tăng >1 | Retry/redirect/filter gọi lại hoặc parallel traffic | Recorded requests, retry config, isolation |
| Test chạy local nhưng CI fail ngẫu nhiên | Port conflict, race, shared stub state, time window | RANDOM_PORT, lifecycle, test parallel |
| Test 404 khi đã thêm fallback | Contract đã thay đổi, vẫn assert no route | Assert fallback route ID/target |
| `Version` predicate không lọc version | Chưa cấu hình ApiVersionStrategy theo bản 5.x | Version resolver + positive/negative version tests |
| URI template variable sai | `Path` pattern/encoding khác | Check `URI_TEMPLATE_VARIABLES_ATTRIBUTE` và rewrite |

### 15.1. Quy trình phân tích một ca test thất bại

1. **Xác nhận test thực sự đã chạy** và dùng đúng profile/BOM.
2. **Xác nhận route runtime tồn tại** và predicate definition giống dự định.
3. **Xem request gửi vào Gateway**: method, raw path, Host, Header, query, remote address.
4. **Kiểm tra route được chọn**: marker, route ID, order; có fallback không?
5. **Kiểm tra recorded backend requests**: có call không, method/path/header đúng không?
6. **Kiểm tra lỗi downstream**: 5xx do transport, DNS, LB, TLS hay backend.
7. **Xem security/CORS**: request có bị xử lý trước route matching không?
8. **Loại bỏ test pollution**: stub queue, shared count, concurrency, config refresh.
9. **Sửa code/config hoặc sửa kỳ vọng test có căn cứ**, không đơn giản đổi 404 thành “any 4xx”.

Một assertion quá lỏng như `is4xxClientError()` có thể che nhầm giữa 401 do auth, 403 do policy, 404 do no route và 429 do limiter. Với test predicate, hãy xác định **kết quả route và downstream forwarding**, không chỉ nhóm status.

## 16. Bài tập mở rộng

### Bài 1 — Thêm một lựa chọn Method

Đổi:

~~~yaml
- Method=GET
~~~

thành:

~~~yaml
- Method=GET,HEAD
~~~

Viết hai test xác minh GET và HEAD match, rồi vẫn từ chối POST. Lưu ý **HEAD response không có body theo HTTP semantics**, nên không thể áp lại assertion JSON body của GET. Kiểm tra route marker/backend attempts theo phương án phù hợp.

### Bài 2 — Thu hẹp Path

Thay `Path=/api/catalog/**` bằng một pattern chỉ cho một item cụ thể như `/api/catalog/items/{id}`. Kiểm thử:

- `/api/catalog/items/42`: khớp.
- `/api/catalog/items/42/details`: không khớp.
- `/api/catalog/items/`: không khớp pattern item có ID.
- `/api/catalog/items/42/`: phụ thuộc `matchTrailingSlash`.

Giải thích vì sao test positive cũ **không chứng minh** wildcard không quá rộng.

### Bài 3 — Thêm fallback và sửa assertions

Thêm `catalog-fallback` với `order: 100` và marker riêng. Sửa negative test cho Host/Header/Query thành:

~~~text
Strict partner route: KHÔNG match
Fallback route: CÓ match
HTTP response: có thể 200
X-Matched-Route: catalog-fallback
Backend call: CÓ
~~~

Nếu test vẫn mong 404, nó đang kiểm tra **một kiến trúc cũ**, không phải hành vi mới.

### Bài 4 — Kiểm tra X-Forwarded-For spoofing

Dựng một reverse proxy test (không dùng Internet) để phân biệt **IP thực của reverse proxy** và **XFF do client gửi**. Thiết kế hai ca:

1. Trusted proxy sanitize/append XFF đúng.
2. Client giả XFF và cố tạo cùng địa chỉ được phép.

Chỉ đánh dấu đạt khi resolver chọn **địa chỉ theo trust topology**, không phải giá trị do client tự khai.

### Bài 5 — Kiểm thử regression bằng mutation

Trong branch test tạm, bỏ `Header=X-Channel,^partner$` rồi chạy negative test “missing header”. Test đó **phải fail** vì backend sẽ được gọi. Khôi phục cấu hình và lặp lại với từng predicate còn lại. Đây là cách kiểm tra chất lượng ma trận mà không cần một framework mutation testing riêng.

## 17. Checklist kiểm thử predicate trước khi phát hành

- [ ] Có ít nhất một request **đúng tất cả điều kiện**, xác minh route ID/marker và backend call.
- [ ] Với **mỗi predicate**, có negative case đổi đúng một biến.
- [ ] Kiểm tra method/path/header/query/Host mà Gateway nhận thật, không suy từ client code.
- [ ] Kiểm tra **header name** không phân biệt hoa/thường nhưng **regex value** theo pattern đã khai báo.
- [ ] Kiểm tra path slash, URL encoding, prefix gần giống, query lặp/empty/malformed.
- [ ] Với Host và RemoteAddr, kiểm tra Ingress/reverse proxy topology và trust boundary.
- [ ] Không dùng Host/X-Forwarded-For/client header như bằng chứng authentication.
- [ ] Phân biệt **predicate miss** với 401/403/429/502/503 từ lớp khác.
- [ ] Assert **không có downstream call** cho negative case trong fixture chỉ có một route.
- [ ] Nếu có fallback, assert **route fallback đúng**, không cố ép no-hit/404.
- [ ] Route IDs duy nhất; `order` rõ ràng khi nhiều routes có thể khớp.
- [ ] Test configuration YAML bind thành route runtime đúng namespace của Gateway version.
- [ ] Random application port và stub port; test không phụ thuộc Internet/backend thật.
- [ ] Stub trả marker rõ, lưu recorded method/path/headers và backend request count.
- [ ] Test state được cô lập; không có stale queue/route cache hoặc concurrent counter races.
- [ ] Tests thực sự được runner thực thi; CI hiển thị số tests và failures.
- [ ] CORS OPTIONS được test riêng với actual request; security tests không bị thay bằng predicate tests.
- [ ] Time-based/Weight/Version/ReadBody predicates có phương pháp test phù hợp tính chất riêng.
- [ ] Actuator chỉ dùng trên management plane bảo vệ, không expose write routes cho public.
- [ ] Với routes mới hoặc thay đổi, có smoke test qua TLS/Ingress thực và kiểm tra gateway replica.
- [ ] Có observability: route ID, response status, backend attempts, timeout, latency và lý do lỗi đã phân loại.

## 18. Câu hỏi tự kiểm tra

**1. Một route khai báo Path, Method, Header. Request chỉ đúng Path và Method có được chọn không?**

Không. Các predicate trong cùng RouteDefinition được kết hợp theo logic **AND**; thiếu Header làm route đó không khớp.

**2. `Method=GET,POST` và hai dòng `Method=GET`/`Method=POST` có giống nhau không?**

Không. Một predicate Method nhận nhiều methods là **OR**; hai dòng predicate độc lập trong một route sẽ là **AND**, thường không thể cùng đúng với một HTTP request có một method.

**3. Negative test trả 404 có đủ chứng minh route không match không?**

Không. Backend có thể trả 404 sau khi đã nhận request, hoặc handler khác trả 404. Cần route marker và backend recording/call count.

**4. Vì sao test `Host=catalog.test` chưa phải test xác thực đối tác?**

Vì client có thể gửi HTTP Host tùy ý trong nhiều môi trường. Predicate Host là điều kiện định tuyến, không kiểm tra credentials/permission. Cần security chain và trust boundary.

**5. Khi thêm một fallback route GET catalog, negative test sai query có nhất thiết 404 không?**

Không. Route partner không match nhưng fallback có thể match và trả 200. Test nên assert `X-Matched-Route: catalog-fallback` và backend target tương ứng.

**6. Vì sao dùng `@SpringBootTest(RANDOM_PORT)` với MockWebServer có giá trị hơn chỉ test một predicate factory?**

Vì integration test kiểm tra **binding YAML, AND giữa predicates, Gateway route selection, filter marker và downstream call** qua HTTP server thật; unit factory chỉ kiểm tra logic đơn lẻ.

**7. Khi một GET đúng route nhưng trả 503, kết luận predicate sai có hợp lý không?**

Không. Request có thể đã chọn đúng route nhưng backend, discovery hoặc connection gặp lỗi. Cần kiểm tra route runtime/markers/downstream attempts và transport.

**8. Khi dùng `Version=1.3` trên Gateway WebFlux 5.x, cần kiểm chứng điều gì trước tiên?**

Cần chắc chắn API version strategy/resolver đã được cấu hình; nếu thiếu, predicate có thể không lọc version như mong đợi. Sau đó test version đúng/sai/thiếu.

**9. Tại sao một test Weight 80/20 không nên assert request đầu tiên luôn vào route 80?**

Vì phân tuyến theo weight mang tính thống kê; một request không chứng minh phân bố. Dùng nhiều mẫu, tolerances và test policy giống nhau giữa nhánh.

**10. Khi nào nên gọi một negative test là “không forward”?**

Khi có bằng chứng backend **không nhận downstream call** cho request đang test trong môi trường cô lập, chứ không chỉ vì client thấy 404 hoặc route marker vắng mặt.

## 19. Tài liệu tham khảo chính thức

1. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): Path, Method, Host, Header, Query, Cookie, RemoteAddr, Version, ReadBody và thời gian; AND giữa predicates.
2. [Spring Cloud Gateway WebFlux 4.3 — Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/request-predicates-factories.html): cú pháp và behavior trên dòng 4.3.
3. [Spring Cloud Gateway WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): namespace route cũ và semantics cơ bản.
4. [Spring Cloud Gateway WebFlux 5.0 — Configuring Predicates and Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): shortcut vs full args, ví dụ binding.
5. [Spring Cloud Gateway WebFlux 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html): `RoutePredicateHandlerMapping` và filter chain.
6. [Spring Cloud Gateway WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): kiểm tra route ID, predicates, filters và order; yêu cầu bảo vệ management endpoints.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest(RANDOM_PORT)`, WebTestClient, mock vs running server.
8. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToServer, response assertions và end-to-end testing.
9. [OkHttp MockWebServer](https://square.github.io/okhttp/features/mockwebserver/): HTTP stub, recorded requests, dispatcher và backend-call verification.
10. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): security policy trên WebFlux không đồng nhất với route predicates.

**Ghi nhớ:** Kiểm thử route predicate không chỉ là “một request đúng trả 200”. Một bộ kiểm thử tốt phải chứng minh **đúng route được chọn khi mọi điều kiện khớp**, đồng thời chứng minh **route đó không nhận request khi từng điều kiện bị sai**. Hãy luôn kết hợp **positive + negative + boundary cases**, marker route, recorded backend calls và test có cấu hình cô lập. Với nhiều routes, **một predicate không khớp không có nghĩa toàn Gateway không forward**: route khác vẫn có thể xử lý request. Cuối cùng, nhớ rằng **predicate chọn đường đi; authentication, authorization, rate limiting, retry và TLS phải được kiểm thử ở các tầng trách nhiệm riêng**.
