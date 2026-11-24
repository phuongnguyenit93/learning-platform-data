# Ranh giới xác thực tại gateway và kiểm tra quyền tại dịch vụ

## 1. Bối cảnh: một cổng vào không thay thế bảo mật của microservice

Trong hệ thống microservices, **SPRING_CLOUD_GATEWAY** là điểm nhận request từ client, thực hiện route predicate và filter chain, có thể thay đổi path/header, chọn instance qua `lb://`, áp dụng rate limiting, circuit breaker, retry, TLS và ghi nhận telemetry. Vì Gateway nằm ở **ranh giới vào hệ thống**, việc kiểm tra xác thực tại đây giúp từ chối sớm request không hợp lệ.

Nhưng Gateway **không sở hữu toàn bộ dữ liệu và quy tắc nghiệp vụ** của mọi dịch vụ. Một token hợp lệ và có quyền gọi API "đọc đơn hàng" chưa chắc cho phép người dùng đọc **bất kỳ đơn hàng nào**.

Ví dụ:

- Người dùng `user-a` sở hữu đơn hàng `O-100`.
- Người dùng `user-b` sở hữu đơn hàng `O-200`.
- Cả hai đều có scope `orders.read`, nghĩa là có quyền sử dụng chức năng đọc đơn hàng.
- `user-a` gửi `GET /api/orders/O-200`.

Gateway có thể xác minh token của `user-a` và thấy scope `orders.read` hợp lệ. **Orders Service vẫn phải từ chối truy cập `O-200`**, vì chỉ dịch vụ này (hoặc một bộ phận phân quyền nghiệp vụ đáng tin cậy mà nó sử dụng) mới biết đơn hàng thuộc về ai.

**Nguyên tắc trọng tâm: xác thực ở Gateway không thay thế kiểm tra quyền tại dịch vụ.** Nên xem Gateway là tầng kiểm soát sớm, còn dịch vụ là nơi thực thi quyết định phân quyền cuối cùng dựa trên tài nguyên thực tế.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **authentication** (xác thực), **authorization** (phân quyền) và **business/resource-level authorization**.
2. Xác định trách nhiệm của Gateway, Identity Provider và downstream service theo nguyên tắc **defense in depth**.
3. Cấu hình Spring Security WebFlux Resource Server xác minh JWT (`iss`, chữ ký, `exp`/`nbf`, `aud`) và kiểm tra scope ở Gateway.
4. Viết kiểm tra quyền sở hữu đơn hàng ở Orders Service mà không tin ID/header do client tự khai báo.
5. Giải thích `401` khác `403`, `WebFilter` khác `GlobalFilter`, và `TokenRelay` khác kiểm tra quyền.
6. Kiểm thử từ chối sớm tại Gateway, từ chối theo tài nguyên tại backend và đường gọi trực tiếp đến service.
7. Nhận diện ranh giới tin cậy khi dùng TLS/mTLS, `lb://`, rate limiting, retry, circuit breaker và observability.

> **Phạm vi kỹ thuật:** ví dụ minh họa Spring Boot 3.5.x, Spring Cloud 2025.0.x, **Spring Cloud Gateway Server WebFlux 4.3.x**, Spring Security 6.5.x. Starter Gateway dùng `spring-cloud-starter-gateway-server-webflux`; route YAML dùng prefix `spring.cloud.gateway.server.webflux`. Các version được nêu để minh họa một cặp tương thích, không phải gợi ý ghim mãi bản phát hành `*.0` trong production.

## 2. Authentication và authorization là hai câu hỏi khác nhau

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication – xác thực** | "Request đến từ danh tính nào, và bằng chứng danh tính có hợp lệ không?" | Verify chữ ký JWT, issuer, audience, hạn token và các yêu cầu token khác. |
| **Coarse-grained authorization – phân quyền mức API** | "Danh tính này có được gọi **nhóm API** này với HTTP method này không?" | Token có `SCOPE_orders.read` mới được `GET /api/orders/**`. |
| **Fine-grained / resource authorization – quyền trên tài nguyên** | "Danh tính này có được đọc **đơn hàng O-200** đang thuộc tenant/user nào không?" | Đối chiếu `sub` của token và owner/tenant của đơn hàng trong dữ liệu đáng tin cậy. |
| **Network trust** | "Đường gọi tới service có xuất phát từ kết nối/máy chủ được chấp nhận không?" | NetworkPolicy, mTLS, service-to-service identity. |
| **Transport security** | "Dữ liệu có được bảo vệ trong quá trình truyền không?" | HTTPS và xác minh certificate/hostname ở cả các chặng cần bảo vệ. |

Một ví dụ phổ biến là đưa việc kiểm tra scope vào Gateway, rồi cho rằng mọi service bên trong mạng đều có thể tin `X-User-Id` hoặc bỏ qua kiểm tra owner. Cách này có lỗ hổng: request có thể đi vòng qua Gateway nếu service bị truy cập trực tiếp, hoặc một dịch vụ nội bộ khác không được tin cậy đầy đủ có thể gọi chéo.

### Phân quyền theo chiều ngang và chiều dọc

- **Vertical authorization:** người dùng được đọc nhưng không được sửa/xóa. Ví dụ `orders.read` khác `orders.write`.
- **Horizontal authorization:** hai người có cùng role/scope nhưng không được truy cập tài nguyên của nhau. Ví dụ `user-a` không được xem `O-200` của `user-b`.
- **Tenant isolation:** cùng một ID hoặc route trong hệ thống đa tenant cần đối chiếu tenant của token với tenant được lưu trên bản ghi; tenant ID do client gửi không tự đủ tin cậy.

Gateway thường kiểm soát tốt **định dạng token, HTTP method, path, scope cơ bản**, còn service cần kiểm tra **owner, tenant, trạng thái nghiệp vụ và quyền trên từng bản ghi**. Với những quyết định trải qua nhiều dịch vụ, có thể sử dụng hệ thống policy chung, nhưng service vẫn phải gọi hoặc áp dụng chính sách một cách đáng tin cậy.

## 3. Ranh giới tin cậy trong kiến trúc API Gateway

```mermaid
flowchart LR
    U["Client"] -->|"Access token"| G["Gateway WebFlux\nSpring Security"]
    I["Identity Provider\nIssuer + JWKS"] -.->|"Public keys / metadata"| G
    G -->|"Request đã qua kiểm tra API-level"| O["Orders Service\nResource Server"]
    I -.->|"Public keys / metadata"| O
    O -->|"Kiểm tra owner / tenant"| DB[("Orders DB")]
    O -->|"200 / 403 / 404"| G
    G -->|"HTTP response"| U
```

**Identity Provider (IdP)** chịu trách nhiệm phát hành access token theo chính sách OAuth2/OIDC; nó không tự biết đơn hàng `O-200` có thuộc người dùng yêu cầu tại thời điểm đọc hay không.

**Gateway** nhận token, xác minh tính hợp lệ và áp dụng điều kiện chung của API. Gateway có thể từ chối `401`/ `403` **trước khi** chọn một upstream để proxy.

**Orders Service** là resource server riêng, cần xử lý các câu hỏi: token này dành cho service nào; có scope gì; người gọi là ai; có quyền đọc đơn hàng từ database không? Service không được xem "đã qua Gateway" là bằng chứng tự thân đủ để cho phép mọi thao tác.

**Database / domain data** chứa nguồn sự thật về owner, tenant, quyền quản lý hoặc trạng thái của đơn hàng. Đường dẫn `/orders/O-200` chỉ là một yêu cầu truy cập, **không phải bằng chứng có quyền**.

### Phân chia trách nhiệm thực tế

| Nhiệm vụ | Gateway | Orders Service | IdP / nền tảng |
| --- | --- | --- | --- |
| Nhận client request và chọn route | Có | Không | Không |
| Xác minh token có chữ ký hợp lệ, issuer, thời gian, audience | Nên có tại cửa vào | **Nên tự xác minh** token dùng cho mình | Phát hành token, công bố metadata/JWKS |
| Chặn URL/method không được cấp scope | Có thể làm sớm | Kiểm tra lại theo API nội bộ | Phát hành scope/claims theo chính sách |
| Kiểm tra owner của `O-200` | Thường không có nguồn dữ liệu cần thiết | **Có, trách nhiệm chính** | Không mặc định biết owner |
| Kiểm tra tenant và policy nghiệp vụ | Có thể kiểm tra tenant ở mức route | **Phải đảm bảo tenant/resource access** | Cung cấp tenant claim nếu chính sách yêu cầu |
| TLS kết nối Gateway → upstream | Cấu hình HttpClient HTTPS/mTLS | Chứng minh danh tính TLS server; có thể xác minh client | PKI/cert management |
| Rate limiting, retry, circuit breaker | Có thể triển khai chung | Tự bảo vệ tài nguyên và tính nhất quán nghiệp vụ | Metrics/observability |
| Giám sát, audit | Log quyết định cấp cửa vào | Log/audit quyết định theo tài nguyên | Tập trung logs/traces theo chính sách |

**Defense in depth** không phải "lặp lại cùng một kiểm tra để trang trí". Mỗi tầng cần chịu trách nhiệm cho điều mà nó thực sự biết và có khả năng chứng minh.

## 4. JWT hợp lệ cần kiểm tra những gì?

Một access token dạng JWT thường chứa ba phần Base64URL `header.payload.signature`. Payload **có thể đọc được** nếu chỉ dùng JWS ký thông thường; **không đặt bí mật** vào claim với giả định JWT được mã hóa.

Ví dụ các claim *minh họa*, không phải token thật:

```json
{
  "iss": "https://idp.example.test/realms/lab",
  "sub": "user-a",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1920000000,
  "nbf": 1919990000
}
```

Một Resource Server JWT phải kiểm tra phù hợp:

| Kiểm tra | Mục đích | Nếu thiếu |
| --- | --- | --- |
| **Signature + thuật toán hợp lệ** | Chứng minh token do issuer được tin cậy ký và không bị sửa. | Client có thể tự giả claim `sub`, `scope`, `tenant`. |
| **`iss`** | Token đến từ đúng hệ thống phát hành được cho phép. | Có thể chấp nhận token từ issuer khác. |
| **`aud`** | Token được phát hành cho đúng resource server/API. | Token dành cho ứng dụng khác có thể bị dùng nhầm. |
| **`exp` và `nbf`** | Token còn trong khoảng thời gian sử dụng hợp lệ. | Chấp nhận token hết hạn hoặc chưa có hiệu lực. |
| **Scope/authority** | Kiểm tra người gọi được phép sử dụng chức năng nào. | Có thể cho phép phương thức ngoài quyền. |
| **Owner/tenant/policy** | Kiểm tra quyền trên bản ghi thực tế. | Dễ xảy ra IDOR/BOLA khi đổi ID trên path. |

Spring Security Resource Server có sẵn cơ chế dùng metadata của issuer và JWKS để kiểm tra chữ ký JWT, `iss`, `exp`/`nbf`. **`aud` nên được cấu hình rõ** cho API. Khi sử dụng bearer access token, Spring Security thường chuyển các scope trong `scope` hoặc `scp` thành `GrantedAuthority` với prefix **`SCOPE_`**. Ví dụ `orders.read` tương ứng `SCOPE_orders.read`.

Không viết code chỉ giải mã JWT thành JSON rồi đọc `sub` hoặc `scope` mà bỏ qua bước **verify signature**. Các claim không được xác minh là dữ liệu không đáng tin cậy.

### 401 và 403 không giống nhau

- **401 Unauthorized:** thiếu bằng chứng xác thực hoặc token không hợp lệ/hết hạn/sai issuer/audience. Với bearer token, phản hồi thường kèm `WWW-Authenticate: Bearer` theo tiêu chuẩn và cấu hình.
- **403 Forbidden:** đã có danh tính được xác thực nhưng **không đủ quyền** cho hành động/tài nguyên, chẳng hạn thiếu `orders.read` hoặc truy cập đơn hàng không thuộc mình.
- **404 Not Found:** không có route/handler/tài nguyên, hoặc một chính sách có chủ đích không tiết lộ sự tồn tại tài nguyên. Đừng mặc định mọi trường hợp thiếu quyền đều phải trả 404.

Status thực tế còn phụ thuộc quy tắc security được áp dụng **trước** route mapping: một URL không có route nhưng bị rule security `denyAll` chặn có thể trả **403** trước khi có cơ hội trả 404. Khi debug, phân biệt nguồn response bằng log/trace.

## 5. Tại sao Spring Security WebFlux không phải một GatewayFilter thông thường?

Gateway Server WebFlux có ít nhất hai cơ chế filter khác nhau:

```text
WebFlux HTTP handling
  |
  +-- Spring Security WebFilter chain (SecurityWebFilterChain)
  |     - Authentication (JWT bearer token)
  |     - Authorization (URL + method + scope)
  |
  +-- RoutePredicateHandlerMapping
        - Path=/api/orders/**
        - Chọn Route
          |
          +-- FilteringWebHandler
                - GlobalFilter + GatewayFilter của route
                - StripPrefix, header transforms
                - LoadBalancer / routing / Netty HttpClient
```

- `SecurityWebFilterChain` là một phần của **Spring WebFlux security pipeline**. Nó có thể chặn request trước khi request đến các Gateway route filters.
- `GlobalFilter` thuộc pipeline **Spring Cloud Gateway** sau khi route được chọn; tên "global" không biến nó thành cách thay thế toàn bộ bảo mật WebFlux.
- `GatewayFilter` hoặc `GatewayFilterFactory` gắn với route cụ thể, thường phục vụ transform/path/header, rate limiter, retry hoặc circuit breaker.
- Nếu chỉ cài một filter thủ công kiểu `Authorization != null`, bạn **chưa** kiểm chứng JWT hay quyền truy cập.

Trong bài này, **Spring Security** chịu trách nhiệm authentication và kiểm tra scope cơ bản; Gateway route filter chỉ biến đổi request và proxy. Bên Orders Service cũng dùng Spring Security để validate token, rồi chạy kiểm tra nghiệp vụ.

## 6. Ví dụ Gateway: kiểm tra JWT và scope ngay tại cửa vào

Giả sử ứng dụng Gateway nhận:

- `GET /public/status`: public, được proxy đến `/status` của Orders Service.
- `GET /api/orders/{orderId}`: yêu cầu access token hợp lệ có scope `orders.read`, rồi proxy đến `/orders/{orderId}`.

Chúng ta **không mở API POST/PUT/DELETE** trong ví dụ để người học không vô tình hiểu scope đọc cũng cho quyền ghi.

### 6.1. Dependency Maven

Dùng **JDK 17+, Maven**, Spring Boot `3.5.0` và Spring Cloud `2025.0.0` *chỉ để minh họa release train tương thích*. Dự án mới cần chọn bản vá còn được hỗ trợ theo Spring Cloud compatibility matrix.

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>secured-gateway</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
```

Resource Server starter đưa vào các phần cần thiết để xác minh JWT (bao gồm Spring Security và hỗ trợ JOSE/JWT theo dependency được quản lý). **Không cần** `spring-boot-starter-oauth2-client` chỉ để kiểm tra một JWT bearer token đến từ client. OAuth2 client và `TokenRelay` phục vụ tình huống khác, giải thích ở mục 9.

### 6.2. Entry point Gateway

Tạo `src/main/java/com/example/gateway/GatewayApplication.java`:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 6.3. Cấu hình issuer, audience và route

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  application:
    name: secured-gateway

  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/lab
          audiences:
            - orders-api

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-status
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/public/status
              filters:
                - StripPrefix=1

            - id: orders-api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
```

Đây là ví dụ có **IdP giả định**. `https://idp.example.test/realms/lab` **chỉ là placeholder**, không phải dịch vụ thật. Bạn phải thay bằng `issuer-uri` chính xác của IdP đang quản lý và sử dụng **access token thật** có `aud` phù hợp. Không tạo token ký giả hoặc tắt kiểm chứng chỉ để demo trả 200.

Ý nghĩa từng phần:

- `issuer-uri`: IdP metadata endpoint giúp Resource Server xác định JWKS/signing keys; issuer của token phải khớp.
- `audiences: orders-api`: access token phải dành cho API có audience `orders-api`. Trong demo, cả Gateway lẫn Orders Service dùng cùng audience có chủ đích; khi hệ thống có nhiều API với audience khác nhau cần chiến lược khác.
- `Path=/api/orders/**`: route chọn HTTP request từ client.
- `StripPrefix=1`: `/api/orders/O-100` đi tới backend là `/orders/O-100`.
- `RemoveRequestHeader=X-User-Id`, `RemoveRequestHeader=X-Tenant-Id`: tránh chuyển tiếp **nguyên vẹn** các identity headers do client có thể giả mạo. Chúng không thay thế việc backend xác minh JWT và kiểm tra owner.

> **Chú ý audience:** ví dụ chỉ có một API nghiệp vụ và cả hai tầng kiểm tra token dành cho `orders-api`. Ở hệ thống có nhiều backend với audience riêng, **không nhận bừa mọi audience ở Gateway rồi gửi cùng token cho mọi service**. Cần thiết kế token audience theo resource server, và cân nhắc token exchange/delegation nếu Gateway phải đổi một access token đầu vào thành token dành cho downstream.

### 6.4. Tạo SecurityWebFilterChain cho Gateway

Tạo `src/main/java/com/example/gateway/GatewaySecurityConfig.java`:

```java
package com.example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
                // Chỉ phù hợp với API stateless dùng Authorization: Bearer.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/status")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
```

Điểm cần hiểu:

1. `@EnableWebFluxSecurity` và bean `SecurityWebFilterChain` đăng ký chính sách ở **tầng WebFlux**, không phải Gateway route filter.
2. `permitAll()` chỉ áp dụng `GET /public/status`. Không có nghĩa mọi request `/public/**` đều public.
3. `hasAuthority("SCOPE_orders.read")` kiểm tra authority mà JWT scope đã được chuyển thành sau bước verify token.
4. `anyExchange().denyAll()` giúp **fail closed**: đường dẫn hoặc HTTP method chưa được cho phép sẽ bị từ chối. Ví dụ không cấp quyền ghi đơn hàng.
5. `oauth2ResourceServer(...jwt(...))` bật kiểm tra bearer JWT.
6. `csrf(...disable)` chỉ phù hợp với **API stateless hoàn toàn dựa vào bearer token trong Authorization header**, không sử dụng cookie/session cho xác thực. Nếu dùng session, OAuth2 Login/BFF hoặc cookie được tự động gửi, phải thiết kế CSRF protection đúng; không copy dòng disable một cách máy móc.

**Giới hạn của rule Gateway:** nó biết HTTP method, URL và authority; nó không đọc database để biết đơn hàng thuộc `user-a` hay `user-b`. Backend vẫn bắt buộc làm bước tiếp theo.

### 6.5. Có cần kiểm tra vai trò hay scope cụ thể trong mọi route?

Khi API lớn dần, có thể phân biệt:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyExchange().denyAll()
```

Đây là **mẫu mở rộng về phân quyền**, không phải đoạn thay thế trực tiếp khi backend chưa hỗ trợ `POST`. Gateway không nên tự giả định quyền ghi chỉ vì token có quyền đọc hoặc vì user đã đăng nhập.

## 7. Orders Service phải tự kiểm tra quyền trên tài nguyên

Ở phía backend, hãy tạo **một ứng dụng Spring Boot riêng**, ví dụ `orders-service`, lắng nghe cổng `9001`. Đây không phải Gateway và không cần starter Spring Cloud Gateway.

Dịch vụ cần:

- Xác minh JWT đầu vào bằng issuer/audience thích hợp.
- Kiểm tra scope `orders.read` khi gọi endpoint `/orders/{id}`.
- Kiểm tra `sub` đã xác thực với **owner của bản ghi**.
- Không dùng `X-User-Id`, `X-Tenant-Id` hoặc `orderId` do client gửi làm bằng chứng quyền truy cập.

### 7.1. Dependency và cấu hình Resource Server của dịch vụ

Trong Maven project Spring Boot 3.5.x của **Orders Service**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Đây là **phần dependencies** của `pom.xml` backend, không phải một `pom.xml` độc lập. Giả sử project backend đã có Spring Boot parent/BOM và plugin build phù hợp.

`src/main/resources/application.yml` của **Orders Service**:

```yaml
server:
  address: 127.0.0.1
  port: 9001

spring:
  application:
    name: orders-service
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/lab
          audiences:
            - orders-api
```

Issuer placeholder phải được thay bằng IdP thật trong cả Gateway lẫn backend. Cấu hình backend giống Gateway về audience trong **demo một API**; thực tế phải quy hoạch token audience riêng cho từng resource server theo chính sách bảo mật.

**Lưu ý:** binding `127.0.0.1` chỉ phù hợp cho hai process cùng máy. Trong container/Kubernetes cần cấu hình hostname và network policy thích hợp, **không** mở trực tiếp Orders Service cho Internet. Network isolation bổ sung phòng vệ, nhưng không thay bước xác minh token/quyền trong service.

### 7.2. SecurityWebFilterChain phía service

Tạo `src/main/java/com/example/orders/OrdersSecurityConfig.java`:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain ordersSecurity(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/status")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
```

Ngay cả khi request **không qua Gateway**, Orders Service vẫn đòi token hợp lệ và scope `orders.read` cho `/orders/**`. Đó là phần phòng vệ giúp giảm hậu quả từ cấu hình sai route, service bị gọi nội bộ hoặc một đường mạng bỏ qua Gateway.

`/status` chỉ là endpoint công khai phục vụ demo. Trong production, health/Actuator endpoints phải có chính sách riêng theo môi trường; việc cho phép truy cập một endpoint kiểm tra trạng thái không đồng nghĩa cho phép tiết lộ thông tin cấu hình, metrics hoặc secrets.

### 7.3. Controller kiểm tra quyền sở hữu

Dữ liệu mock để minh họa:

```text
Order O-100 -> owner user-a
Order O-200 -> owner user-b
```

Tạo `src/main/java/com/example/orders/OrdersController.java`:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    // Dữ liệu giả lập, không phải hệ quản lý đơn hàng production.
    private static final Map<String, String> ORDER_OWNERS = Map.of(
            "O-100", "user-a",
            "O-200", "user-b"
    );

    @GetMapping("/status")
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/orders/{id}")
    public Mono<ResponseEntity<Map<String, String>>> getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.defer(() -> {
            String owner = ORDER_OWNERS.get(id);

            if (owner == null) {
                return Mono.just(ResponseEntity
                        .status(HttpStatus.NOT_FOUND)
                        .body(Map.of("error", "not_found")));
            }

            // jwt.getSubject() là identity từ JWT đã được xác minh
            // bởi Resource Server trước khi controller chạy.
            if (!owner.equals(jwt.getSubject())) {
                return Mono.just(ResponseEntity
                        .status(HttpStatus.FORBIDDEN)
                        .body(Map.of("error", "not_allowed")));
            }

            return Mono.just(ResponseEntity.ok(
                    Map.of("orderId", id, "ownerId", owner)));
        });
    }
}
```

Trong ứng dụng Spring Boot backend, cần có entry point `@SpringBootApplication` đặt tại `com.example.orders` hoặc package cha phù hợp để component scan tìm được controller/security config.

**Tại sao controller dùng `jwt.getSubject()`?** Vì `Jwt` được Spring Security Resource Server tạo từ token **đã xác minh**. Nó khác hoàn toàn:

```java
// KHÔNG AN TOÀN nếu dùng để phân quyền:
String claimedUser = request.getHeaders().getFirst("X-User-Id");
```

Một client có thể gửi `X-User-Id: user-b` để giả danh người khác. Mã demo cố ý **bỏ qua header này** và so sánh với owner của đơn hàng trong nguồn dữ liệu phía server.

Trong production:

- Đọc owner/tenant từ database hoặc domain service đáng tin cậy, không từ một map cố định.
- Dùng truy vấn ràng buộc **cả tài nguyên và danh tính**, ví dụ về mặt ý tưởng `findByIdAndOwnerId(orderId, subject)`, nếu hợp đồng dữ liệu cho phép. Điều này giảm rủi ro truy cập ngoài owner và tránh lộ thông tin tài nguyên.
- Với role admin/delegate, cần chính sách rõ ràng và audit; không tự cho phép mọi user có scope `orders.read` thấy toàn bộ đơn hàng.
- Tách **authentication subject** và **authorization domain user ID** nếu IdP dùng ID khác ID nội bộ. Cần ánh xạ đáng tin cậy, không giả định mọi hệ thống đều có `sub = user-a`.
- Kiểm soát tenant/owner trong cùng giao dịch hoặc quy trình nhất quán để giảm rủi ro TOCTOU khi quyền và tài nguyên thay đổi đồng thời.

### 7.4. Dùng method security khi phù hợp

Với Spring Security reactive, có thể bật `@EnableReactiveMethodSecurity` và dùng `@PreAuthorize` cho điều kiện ở tầng service method:

```java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
```

Ví dụ giới hạn một service method theo scope:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> findOrder(String id) {
    // Kiểm tra owner/tenant cần được thực thi bên trong
    // nghiệp vụ hoặc qua policy bean đáng tin cậy.
    return orderRepository.findViewById(id);
}
```

Đây là **mảnh mã minh họa**, giả định đã có `OrderView`, `orderRepository` và các import tương ứng. Chỉ thêm annotation scope **không** đủ để giải quyết vấn đề `user-a` xem `O-200`: logic quyền trên tài nguyên vẫn phải có.

Với các method reactive, Spring Security dùng Reactor Context để mang security context qua pipeline; đừng chuyển danh tính vào `ThreadLocal` tự quản lý rồi mong nó luôn theo được các bước async.

## 8. Luồng HTTP từ client đến hai tầng quyết định

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway Security
    participant R as Gateway Route/Proxy
    participant S as Orders Service Security
    participant O as Orders Domain/DB

    C->>G: GET /api/orders/O-200 + JWT của user-a
    G->>G: Verify signature, iss, aud, exp/nbf
    G->>G: Kiểm tra SCOPE_orders.read
    alt Token/scope không hợp lệ
        G-->>C: 401 hoặc 403
    else Được gọi API
        G->>R: Cho phép route /api/orders/**
        R->>S: GET /orders/O-200 + bearer token
        S->>S: Verify token và SCOPE_orders.read độc lập
        alt Token backend không hợp lệ
            S-->>C: 401/403 qua Gateway
        else Token backend hợp lệ
            S->>O: Đọc owner của O-200
            O-->>S: owner=user-b
            S->>S: user-a != user-b
            S-->>C: 403 Forbidden qua Gateway
        end
    end
```

Đối với `GET /api/orders/O-100` của `user-a` (token hợp lệ và scope đủ), cả hai tầng có thể cho phép và controller trả `200 OK`.

**Không gắn hai vai trò làm một:** Gateway có thể từ chối trước khi HTTP proxy; Orders Service mới quyết định owner/tenant cụ thể. Nếu downstream trả 403, Gateway thường chuyển status đó về client; 403 không nhất thiết có nguồn gốc tại Gateway.

## 9. Token đi từ Gateway xuống service theo cách nào?

Chọn mô hình theo loại client và cách cấp token:

### 9.1. Client gửi bearer JWT; Gateway là Resource Server

Kịch bản của bài:

```http
GET /api/orders/O-100 HTTP/1.1
Authorization: Bearer <access-token>
```

- Gateway xác minh bearer JWT và yêu cầu scope trước khi proxy.
- Muốn Orders Service xác minh độc lập, backend phải **nhận được bearer access token được phép dùng cho nó** (hoặc một loại downstream credential tương đương được thiết kế đúng).
- Với route HTTP proxy thông thường, `Authorization` là header request có thể được chuyển tiếp nếu không có security/filter/proxy component nào loại bỏ hay thay thế. **Phải kiểm thử thực tế** chính sách forward header của ứng dụng, không mặc định mọi middleware sẽ giữ nó trong mọi trường hợp.
- Backend tiếp tục verify chữ ký, issuer, audience, hạn token và owner. **Gateway xác thực rồi không tự biến header bất kỳ thành danh tính đáng tin cậy.**

Nếu backend yêu cầu audience khác với token đầu vào, không tùy tiện dùng lại token sai audience. Hãy xem cơ chế **token exchange / on-behalf-of** của IdP phù hợp, hoặc một kiến trúc xác thực service-to-service đã được phê duyệt.

### 9.2. OAuth2 Login / BFF: TokenRelay

Một Gateway đóng vai trò **OAuth2 Client** (ví dụ người dùng đăng nhập bằng OAuth2 Login, Gateway quản lý authorized client) có thể dùng filter **`TokenRelay`** để lấy access token phù hợp và chuyển tới downstream.

Mẫu cấu hình route khi đã có OAuth2 client registration/authorized client đúng:

```yaml
filters:
  - TokenRelay=
```

**Điều kiện bắt buộc:**

1. Thêm dependency `spring-boot-starter-oauth2-client`.
2. Cấu hình `spring.security.oauth2.client.*` đúng để có `ReactiveClientRegistrationRepository` và hạ tầng authorized client.
3. Đảm bảo access token được relay **có audience/scope phù hợp** cho downstream.
4. Thiết kế persistence của `ReactiveOAuth2AuthorizedClientService` phù hợp production (mặc định có thể là in-memory).
5. **Backend vẫn xác minh access token và quyền trên tài nguyên.**

Đừng nhầm `TokenRelay` là "bật tự động" chỉ bằng cách thêm Spring Security Resource Server JWT. Một ứng dụng chỉ nhận và verify bearer token không nhất thiết cần OAuth2 Client hoặc TokenRelay; đó là hai mô hình liên quan nhưng khác nhau.

### 9.3. Dùng header danh tính nội bộ

Một số hệ thống truyền `X-Authenticated-User` hay `X-Tenant` xuống backend thay vì chuyển access token. Cách này chỉ an toàn nếu đã thiết kế **trust boundary chặt chẽ**:

- Gateway xóa mọi header cùng tên do client gửi trước khi tự phát hành thông tin danh tính.
- Service **chỉ** nhận header danh tính từ một Gateway/service proxy đã được xác thực bằng mTLS/service identity hoặc cơ chế ký message có kiểm chứng.
- Không thể đi vòng qua Gateway bằng đường mạng khác; có NetworkPolicy/egress/ingress phù hợp.
- Header có chống giả mạo, replay và kiểm soát audience/tenant đúng chính sách.
- Service vẫn kiểm tra quyền trên resource dù biết danh tính.

Nếu chưa có những bảo đảm đó, **ưu tiên để service tự xác minh token** thay vì đọc một header thuần văn bản.

## 10. Thực hành và kiểm thử theo ma trận quyền

Bài dùng IdP thật theo cấu hình `issuer-uri` và access token phù hợp để không phải minh họa cách **tự ký JWT giả**. Khi chạy trên localhost:

1. Khởi động **Orders Service** ở `127.0.0.1:9001`.
2. Khởi động **Gateway** ở `127.0.0.1:8080`.
3. Cung cấp một JWT access token thật được IdP phát hành, có issuer và audience `orders-api`, scope `orders.read`, subject khớp user mẫu đã cấu hình.
4. Không chia sẻ token thật trong log, ảnh chụp, ví dụ commit hay issue tracker.

> Vì `https://idp.example.test/realms/lab` là placeholder, không thể chạy thành công các bước có token cho tới khi thay bằng IdP có thật, cấu hình JWKS và nhận được JWT hợp lệ. Nếu token có `sub` khác `user-a`/`user-b`, hãy thay dữ liệu mock owner cho khớp danh tính thử nghiệm, không sửa claim bằng tay.

### 10.1. Public endpoint

```bash
curl -i http://127.0.0.1:8080/public/status
```

Khi Orders Service hoạt động, kết quả mong đợi có body:

```json
{"status":"ok"}
```

Endpoint này được `permitAll` trong **cả hai** security chains. Lưu ý: request mang một bearer token **hỏng** vẫn có thể bị tầng authentication từ chối dù path public; `permitAll` không có nghĩa hệ thống phải bỏ qua mọi credential không hợp lệ.

### 10.2. Không có access token

```bash
curl -i http://127.0.0.1:8080/api/orders/O-100
```

Với policy minh họa, request không đủ điều kiện xác thực và thường được Gateway trả `401 Unauthorized`. **Không có HTTP proxy đến Orders Service** cho nhánh này.

### 10.3. Token hợp lệ nhưng thiếu scope

Dùng một access token có issuer/audience hợp lệ nhưng không có `orders.read`. Gửi request tương tự:

```bash
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-100
```

Token đã xác thực nhưng scope không đủ nên Gateway thường trả **403 Forbidden**. Đừng dùng `YOUR_ACCESS_TOKEN` như một chuỗi token thật; đó chỉ là placeholder cần thay bằng bearer access token được cấp đúng.

### 10.4. Token `user-a` có scope đọc, gọi đúng đơn hàng

Nếu access token chứa `sub=user-a`, `aud=orders-api`, `scope=orders.read` và còn hiệu lực:

```bash
curl -i -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-100
```

Khi backend nhận được token và xác minh thành công, response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"O-100","ownerId":"user-a"}
```

### 10.5. Cùng token nhưng gọi đơn hàng của người khác

```bash
curl -i -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-200
```

Gateway **vẫn cho phép gọi API** vì token có scope đọc. Orders Service thấy `O-200` thuộc `user-b` và trả **403 Forbidden** theo ví dụ. Đây là phép thử quan trọng nhất của bài: **có scope không đồng nghĩa có quyền trên mọi đối tượng**.

### 10.6. Giả header và gọi trực tiếp backend

```bash
curl -i \
  -H "X-User-Id: user-b" \
  -H "X-Tenant-Id: privileged" \
  -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-200
```

Gateway loại bỏ hai header người dùng có thể tự gửi; backend chỉ dùng identity từ JWT đã xác minh, nên không cho `user-a` đọc đơn của `user-b`.

Thử gọi **trực tiếp** Orders Service trong môi trường demo:

```bash
curl -i http://127.0.0.1:9001/orders/O-100
```

Không có bearer token, Orders Service vẫn trả **401** (theo cấu hình bảo mật). Điều này chứng minh service không phụ thuộc **duy nhất** vào việc request đã qua Gateway. Trong production cần thêm network isolation; việc test trực tiếp chỉ để chứng minh tầng bảo vệ riêng của service.

### 10.7. Bảng kỳ vọng

| Request | Gateway | Orders Service | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| `GET /public/status`, không token | Cho phép | Cho phép | `200`, `{"status":"ok"}` |
| `GET /api/orders/O-100`, không token | Từ chối | Không được gọi | `401` |
| Token sai chữ ký/`iss`/`aud` hoặc hết hạn | Từ chối | Không được gọi | Thường `401` |
| Token hợp lệ, thiếu `orders.read` | Từ chối | Không được gọi | Thường `403` |
| `user-a` có scope, đọc `O-100` | Cho phép | Owner khớp | `200` |
| `user-a` có scope, đọc `O-200` | Cho phép | Owner khác | `403` từ service |
| Không token gọi trực tiếp `:9001/orders/O-100` | Không tham gia | Từ chối | `401` |
| `POST /api/orders/O-100` | Chưa được cấp quyền | Không được gọi | `403` theo `denyAll` khi security đã xác thực |
| `GET /unknown` | Bị `denyAll` | Không được gọi | Có thể `403`, không mặc định `404` |

Không nên chỉ assert HTTP status: để phân biệt nguồn gốc của 403, kết hợp bộ đếm request backend, route ID, tracing hoặc audit. **Không log access token** để làm bằng chứng.

## 11. Trường hợp đáng chú ý khi triển khai production

### 11.1. IDOR/BOLA: sửa ID trên path không phải quyền truy cập

Lỗi **Broken Object Level Authorization** xảy ra khi ứng dụng xác thực thành công nhưng quên kiểm tra quyền trên đối tượng được yêu cầu. Đổi `/orders/O-100` thành `/orders/O-200` phải dẫn tới kết quả tương ứng với quyền thực tế, không chỉ scope. Kiểm tra owner/tenant ở tầng truy vấn hoặc domain và áp dụng cho cả thao tác đọc, sửa, xóa, xuất file, báo cáo.

### 11.2. Nhiều issuer, nhiều audience và phân quyền đa tenant

Nếu Gateway phục vụ Orders, Billing và User Profile, mỗi service có thể yêu cầu audience riêng. Không cấu hình "chấp nhận mọi token từ IdP" rồi coi mọi access token đều đủ quyền. Phải xem:

- `iss` được cho phép theo tenant hoặc vùng tin cậy nào.
- `aud` dành cho resource server nào.
- Scope/role được ánh xạ ra sao; role IdP không tự đồng nghĩa quyền nghiệp vụ.
- Tenant ID trong token có phù hợp với tenant của tài nguyên không.
- Khi dùng client credentials (machine-to-machine), có còn `sub` đại diện user cuối không? Cần chính sách riêng cho service identity.

Một resource server dùng **opaque token** có thể dùng introspection thay cho JWT validation; đó là mô hình khác với ví dụ JWT nhưng vẫn phải kiểm tra quyền theo tài nguyên.

### 11.3. Token rotation, expiry và revocation

JWT thường có hạn và chữ ký; Resource Server kiểm tra khóa công khai được công bố qua JWKS và các claim thời gian. Một JWT chưa hết hạn **không tự động biết** tài khoản vừa bị thu hồi quyền trong database hoặc bị chặn ngay tức thì. Với yêu cầu thu hồi nhanh, cân nhắc access token TTL ngắn, introspection, denylist hoặc cơ chế chính sách phù hợp.

Nếu IdP/JWKS không khả dụng, phải có chiến lược cache khóa, timeout và xử lý lỗi **fail closed**. Không chuyển sang "bỏ kiểm tra chữ ký" khi mạng có sự cố.

### 11.4. CSRF và CORS không phải phân quyền

- **CORS** là quy tắc trình duyệt cho cross-origin requests, không ngăn `curl` hoặc client khác gọi API. Cấu hình CORS đúng origin/method/header; xử lý preflight `OPTIONS` theo kiến trúc bảo mật, nhưng không mở rộng quyền ghi dữ liệu.
- **CSRF** quan trọng nếu authentication dùng cookie/session được trình duyệt tự gửi. Chỉ disable CSRF khi API thực sự stateless và không dựa vào cookie; ví dụ chỉ dùng bearer JWT trong `Authorization` header là một trường hợp như vậy.
- Đừng dùng CORS allowlist làm danh sách người được phép đọc đơn hàng.

### 11.5. Rate limiting, circuit breaker và retry

Gateway có thể **chặn sớm** qua Spring Security hoặc rate limiter trước khi gọi backend. Circuit breaker và retry giải quyết tính sẵn sàng, **không thay thế** xác minh quyền:

- Rate limiter theo identity phải lấy identity **đã xác thực**; không tin `X-User-Id` tự gửi.
- Retry không được biến một lỗi `401`/`403` thành "cơ hội" thử lại một danh tính khác, và không retry mù quáng thao tác ghi.
- Fallback/circuit breaker không được trả dữ liệu nhạy cảm khi service chính đã từ chối quyền hoặc không xác định được principal.
- Service discovery/`lb://` chỉ chọn instance; mọi replica của service cần chính sách JWT và owner/tenant nhất quán.

### 11.6. TLS, service-to-service và header trust

TLS giữa client–Gateway và Gateway–service là **hai chặng**. Nếu Gateway chuyển bearer token xuống service, cần bảo vệ chặng phía sau bằng HTTPS/mTLS theo chính sách, xác minh chứng chỉ và tên host. Không gửi access token tới URI backend không được allowlist hoặc certificate không hợp lệ. NetworkPolicy/firewall/mTLS giúp hạn chế bypass và giả service, nhưng **không loại bỏ việc kiểm tra quyền nghiệp vụ**.

### 11.7. Observability và audit

Ghi nhận các trường **không nhạy cảm**: route ID, service ID, HTTP method, normalized path, kết quả `401`/`403`, nguyên nhân phân loại (invalid_token/insufficient_scope/owner_mismatch), trace ID, latency và nơi đưa ra quyết định. Không log raw bearer token, cookie, signing keys, private claims, toàn bộ query chứa PII hoặc dữ liệu đơn hàng nhạy cảm. Audit ở service có thể ghi principal ID và resource ID **theo chính sách bảo vệ dữ liệu**, nhưng nên hạn chế những dữ liệu đó trong metrics label để tránh lộ PII và cardinality cao.

## 12. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `401` dù có `Authorization` | Token hết hạn, sai chữ ký, issuer, audience, `nbf` hoặc thiếu cấu hình JWKS. | Xem log Resource Server/IdP và claims đã kiểm chứng; không log toàn bộ token. |
| `403` tại Gateway | JWT hợp lệ nhưng thiếu `SCOPE_orders.read`, method/path bị `denyAll`. | Xem HTTP method, matcher, authority mapping và audit gateway. |
| `403` từ Orders Service | Owner/tenant không khớp, hoặc service có policy chặt hơn. | Kiểm tra ID resource và dữ liệu quyền ở source of truth. |
| Cùng bearer token qua Gateway thì 401 ở backend | Authorization không được chuyển tiếp; backend yêu cầu audience khác; issuer/JWKS khác; token không hợp lệ ở backend. | Kiểm tra chính sách header forwarding, audience và backend security configuration. |
| Truy cập trực tiếp backend không token vẫn được đọc đơn | Service chưa tự bảo vệ endpoint hoặc matcher sai. | Thêm Resource Server + authorization trên service, kiểm thử direct access. |
| `X-User-Id: admin` làm vượt quyền | Backend đang tin header client thay cho danh tính xác thực. | Loại header không tin cậy, xác minh JWT hoặc thiết lập trust boundary có chứng minh. |
| URL không có route nhưng trả 403 thay vì 404 | Security rule `denyAll` từ chối trước route matching. | Phân biệt tầng security và route mapping; không suy lỗi route chỉ từ status. |
| `TokenRelay` không có tác dụng | Chưa cấu hình OAuth2 client/registration, không có authorized client, thiếu starter. | Xem `ReactiveClientRegistrationRepository` và client security config. |
| `CSRF 403` ở request dùng cookie/session | CSRF protection và session workflow chưa cấu hình đúng. | Phân biệt cookie-based với bearer stateless; thiết kế CSRF phù hợp. |
| Request qua `lb://` đến replica không nhất quán | Security config/issuer/audience/permissions giữa các replica khác nhau. | Kiểm tra deployment, config/secret rotation và policy rollout. |
| Service trả 200 cho order của người khác | Chỉ check scope, quên owner/tenant. | Bổ sung kiểm tra resource authorization và test chéo nhiều user. |
| 5xx khi kiểm tra token | JWKS/IdP unreachable, certificate/TLS lỗi hoặc app config sai. | Xác minh kết nối issuer/JWKS, TLS trust, timeout, log root cause. |

## 13. Checklist thiết kế và kiểm thử

- [ ] IdP phát hành access token có issuer, audience, thời hạn và scope phù hợp.
- [ ] Gateway dùng Spring Security WebFlux, **không** chỉ kiểm tra sự tồn tại header `Authorization`.
- [ ] API không khai báo rõ quyền được **deny by default**; GET/read và POST/write không chia sẻ scope tùy tiện.
- [ ] Backend tự kiểm tra access token hoặc một danh tính đã xác minh theo trust model chặt chẽ.
- [ ] Kiểm tra owner/tenant trên dữ liệu đáng tin cậy trong **mọi** thao tác đọc/ghi/xóa.
- [ ] Test token thiếu/hỏng/sai audience/sai issuer/hết hạn và scope thiếu.
- [ ] Test **hai người cùng scope** nhưng chỉ một người là owner của tài nguyên.
- [ ] Test đường gọi trực tiếp đến service không có token, sai token và giả header.
- [ ] Có chính sách rõ về TokenRelay/token exchange nếu dùng OAuth2 Client/BFF.
- [ ] Không coi `lb://`, TLS, rate limiter, retry hoặc circuit breaker là thay thế phân quyền.
- [ ] Chỉ tắt CSRF nếu thực sự là bearer stateless; CORS không phải authorization.
- [ ] Không đưa token/PII vào logs, metrics hoặc trace attributes không được bảo vệ.

### Câu hỏi tự kiểm tra

**1. Vì sao JWT hợp lệ có `orders.read` vẫn có thể nhận 403 khi đọc một đơn hàng cụ thể?**

Vì scope thường chỉ cấp quyền **sử dụng loại thao tác**; quyền trên đơn hàng cụ thể còn phụ thuộc owner, tenant và trạng thái nghiệp vụ tại Orders Service.

**2. Nếu đã kiểm tra JWT tại Gateway, có thể bỏ Spring Security ở Orders Service không?**

Không nên trong kiến trúc defense in depth. Dịch vụ có thể bị gọi qua đường khác hoặc nhận một request từ thành phần nội bộ khác; backend phải có khả năng xác minh quyền và danh tính đáng tin cậy theo mô hình được thiết kế.

**3. `GlobalFilter` trong Gateway có thay được `SecurityWebFilterChain` của Spring Security không?**

Không. Chúng thuộc hai pipeline khác nhau; việc tự kiểm tra header trong filter không thực hiện đầy đủ xác thực/ủy quyền chuẩn.

**4. `401` và `403` dùng khác nhau như thế nào?**

`401` thường là thiếu/sai chứng thực; `403` là đã xác thực nhưng không đủ quyền. `403` có thể xuất phát ở Gateway hoặc service.

**5. `sub` của JWT và `X-User-Id` từ request có cùng mức tin cậy không?**

Không. `sub` chỉ đáng tin khi token được xác minh đầy đủ; `X-User-Id` do client gửi có thể bị giả mạo.

**6. `TokenRelay` có làm Orders Service tự kiểm tra owner và audience không?**

Không. TokenRelay chỉ chuyển credential phù hợp xuống downstream; backend phải validate token và thực thi policy của mình.

**7. Vì sao API chỉ dùng bearer token stateless có thể tắt CSRF, nhưng app dùng session cookie thì không nên copy cấu hình này?**

Vì cookie/session authentication được trình duyệt gửi tự động, làm thay đổi mô hình nguy cơ CSRF. Cần quyết định dựa trên cách lưu và gửi credential, không dựa trên tên "Gateway".

**8. Nếu service hỗ trợ `lb://` với nhiều instance, quyền truy cập có được bảo đảm tự động không?**

Không. LoadBalancer chỉ chọn instance; mọi replica phải có cùng chính sách xác thực, phân quyền và kiểm tra owner/tenant phù hợp.

## Kết luận

**Gateway xác thực sớm để giảm request không hợp lệ, nhưng dịch vụ phải quyết định quyền trên tài nguyên mà nó sở hữu.** Trong Spring Cloud Gateway Server WebFlux, Spring Security `SecurityWebFilterChain` có thể xác minh bearer JWT, issuer, audience và scope **trước khi** Gateway proxy; Orders Service cần tự xác minh token được phép dùng cho mình, sau đó kiểm tra owner/tenant trên dữ liệu nghiệp vụ. Khi các tầng này phối hợp với TLS/mTLS, giới hạn lưu lượng, discovery, circuit breaker, retry và observability có kiểm soát, hệ thống có thể bảo vệ cả cửa vào **lẫn** các đường gọi nội bộ.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/how-it-works.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Boot — OAuth2 Resource Server properties và audiences](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Cloud — đối chiếu release train tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
