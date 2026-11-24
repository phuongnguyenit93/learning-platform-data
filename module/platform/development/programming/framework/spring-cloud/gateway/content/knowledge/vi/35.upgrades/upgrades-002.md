# Thay đổi tên artifact, starter và namespace cấu hình

Spring Cloud Gateway là cổng vào cho các microservices, nơi route predicate chọn request, filter chain biến đổi request/response và các thành phần như service discovery, load balancer, security, circuit breaker và observability hỗ trợ vận hành. Khi nâng cấp module **SPRING_CLOUD_GATEWAY**, cần kiểm tra đồng thời dependency Maven/Gradle và namespace cấu hình. Một dự án có thể biên dịch sau khi đổi phiên bản nhưng vẫn khởi động với cấu hình cũ, bỏ qua route hoặc thay đổi hành vi của header chuyển tiếp.

Từ Spring Cloud 2025.0, Spring Cloud Gateway chuẩn hóa lại tên module và starter để phân biệt hai kiểu sử dụng (**Server** và **ProxyExchange**) cùng hai web stack (**WebFlux** và **WebMVC**). Các artifact cũ được đánh dấu deprecated và có thể phát cảnh báo khi ứng dụng khởi động. Cùng đợt này, các prefix cấu hình cũng được chuyển theo module. Vì vậy, nâng cấp cần được thực hiện như một thay đổi đồng bộ giữa dependency, property và kiểm thử hành vi.

## Phân biệt các module trước khi chọn artifact

Trước khi thay tên dependency, xác định ứng dụng đang dùng mô hình nào:

- **Gateway Server WebFlux**: gateway định tuyến theo route predicate và filter chain trên Spring WebFlux/Reactor. Đây là lựa chọn reactive, sử dụng runtime Netty do Spring Boot cung cấp; không chạy trong Servlet container truyền thống hoặc đóng gói WAR.
- **Gateway Server WebMVC**: gateway server dựa trên Spring MVC và Servlet stack. Chọn module này khi kiến trúc ứng dụng sử dụng MVC.
- **Gateway ProxyExchange WebFlux/WebMVC**: thư viện hỗ trợ lập trình proxy exchange trong controller hoặc luồng xử lý của ứng dụng. Đây không phải starter thay thế trực tiếp cho một Gateway Server khai báo route bằng properties.

Tên mới giúp dependency thể hiện rõ loại gateway và web stack. Không đổi từ WebFlux sang WebMVC chỉ vì artifact mới có chữ `webmvc`; đó là thay đổi kiến trúc, có thể kéo theo khác biệt về runtime, filter, API và cách viết kiểm thử.

## Bảng đổi tên artifact và starter

Các tên dưới đây là mapping được công bố trong ghi chú phát hành Spring Cloud 2025.0:

| Artifact cũ | Artifact mới | Trường hợp sử dụng |
|---|---|---|
| `spring-cloud-gateway-server` | `spring-cloud-gateway-server-webflux` | Module triển khai Gateway Server WebFlux |
| `spring-cloud-gateway-server-mvc` | `spring-cloud-gateway-server-webmvc` | Module triển khai Gateway Server WebMVC |
| `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` | Starter cho Gateway Server WebFlux |
| `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` | Starter cho Gateway Server WebMVC |
| `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` | ProxyExchange trên WebFlux |
| `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` | ProxyExchange trên WebMVC |

Group ID của các dependency Spring Cloud này vẫn là `org.springframework.cloud`. Khi ứng dụng dùng starter, thường chỉ cần khai báo starter tương ứng; không thêm trực tiếp module triển khai nếu starter đã kéo module đó vào. Chỉ khai báo artifact cấp module khi dự án có lý do rõ ràng để quản lý dependency theo cách đó.

## Quản lý phiên bản bằng Spring Cloud BOM

Không đặt một phiên bản Gateway tùy ý tách khỏi Spring Cloud Release Train. Chọn release train tương thích với phiên bản Spring Boot của ứng dụng theo bảng tương thích chính thức, rồi import BOM để các module Spring Cloud dùng cùng bộ phiên bản.

Ví dụ Maven với Gateway Server WebFlux:

```xml
<properties>
    <spring-cloud.version>2025.0.x</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
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
</dependencies>
```

`2025.0.x` trong ví dụ là ký hiệu cần thay bằng phiên bản phát hành cụ thể mà dự án chọn; không sao chép nguyên chuỗi này vào build. Nếu ứng dụng dùng Gateway Server WebMVC, thay starter bằng `spring-cloud-starter-gateway-server-webmvc`. Với Gradle, áp dụng cùng nguyên tắc import BOM qua cơ chế dependency management/platform của dự án và không khai báo phiên bản Gateway riêng lẻ.

Sau khi đổi dependency, xem dependency tree để phát hiện artifact cũ còn được kéo vào gián tiếp. Một thư viện nội bộ hoặc starter khác có thể vẫn phụ thuộc tên cũ, vì vậy chỉ sửa dòng dependency trực tiếp chưa đủ để kết luận quá trình nâng cấp hoàn tất.

## Chuyển namespace cấu hình

Spring Cloud 2025.0 thay prefix cấu hình để khớp tên module mới. Cần tìm và chuyển các property trong tất cả nguồn cấu hình mà ứng dụng sử dụng, bao gồm `application.yml`, `application-*.yml`, file `.properties`, Config Server, biến môi trường, Helm values, ConfigMap, test fixture và cấu hình triển khai.

| Module | Prefix cũ | Prefix mới |
|---|---|---|
| Gateway Server WebFlux | `spring.cloud.gateway.*` | `spring.cloud.gateway.server.webflux.*` |
| Gateway Server WebMVC | `spring.cloud.gateway.mvc.*` | `spring.cloud.gateway.server.webmvc.*` |
| ProxyExchange WebFlux | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webflux.*` |
| ProxyExchange WebMVC | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webmvc.*` |

Phần suffix phía sau prefix được giữ theo property tương ứng, nhưng vẫn cần kiểm tra tài liệu của release train đích vì một số property có thể thay đổi hoặc bị loại bỏ độc lập với việc đổi prefix.

Ví dụ, cấu hình Gateway Server WebFlux trước nâng cấp:

```yaml
spring:
  cloud:
    gateway:
      enabled: true
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
      discovery:
        locator:
          enabled: true
      httpclient:
        connect-timeout: 2000
```

Sau khi chuyển sang namespace mới:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          enabled: true
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
          discovery:
            locator:
              enabled: true
          httpclient:
            connect-timeout: 2000
```

Trong ví dụ, route vẫn có cùng `id`, URI, predicate, filter và timeout. Thay đổi nằm ở vị trí prefix cấu hình. Với Gateway Server WebMVC, chuyển nhóm property từ `spring.cloud.gateway.mvc` sang `spring.cloud.gateway.server.webmvc`. Với ProxyExchange, chọn đúng nhánh `proxy-exchange.webflux` hoặc `proxy-exchange.webmvc` theo web stack của ứng dụng.

## Dùng Properties Migrator trong giai đoạn chuyển đổi

Spring Cloud 2025.0 release notes đề xuất dùng `spring-boot-properties-migrator` để hỗ trợ các prefix cũ trong giai đoạn chuyển đổi. Có thể thêm dependency này tạm thời vào runtime classpath để nhận chẩn đoán property cũ khi ứng dụng khởi động và hỗ trợ di trú.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Đọc toàn bộ thông báo khởi động, chuyển các property được báo sang prefix mới và chạy lại ứng dụng. Sau khi hoàn tất, gỡ `spring-boot-properties-migrator` khỏi build. Đây là công cụ hỗ trợ di trú tạm thời, không nên giữ lâu dài như một cách thay thế việc cập nhật cấu hình nguồn.

Không dựa riêng vào việc ứng dụng khởi động thành công. Hãy kiểm tra route thực tế qua Actuator hoặc kiểm thử tích hợp, vì property cũ có thể không còn điều khiển module mới theo cách dự án kỳ vọng.

## Kiểm tra thay đổi Forwarded và X-Forwarded headers

Một thay đổi hành vi cần được rà soát khi nâng cấp là xử lý header `Forwarded` và `X-Forwarded-*`. Theo ghi chú phát hành Spring Cloud 2025.0, chức năng này được tắt mặc định trong các bản sửa lỗi tương ứng để tránh tin cậy header do nguồn không xác định gửi tới.

Nếu Gateway nhận traffic qua ingress, reverse proxy hoặc load balancer và cần dùng các header này để xác định host, scheme hay địa chỉ client, phải cấu hình rõ các proxy được tin cậy bằng regular expression:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '10\.0\.0\..*'
```

Với Gateway Server WebMVC, property tương ứng là `spring.cloud.gateway.server.webmvc.trusted-proxies`. Thay biểu thức mẫu bằng dải địa chỉ hoặc pattern thực tế của các proxy thuộc quyền kiểm soát. Không dùng pattern cho phép mọi nguồn như `.*`, vì request client có thể giả mạo header chuyển tiếp và làm sai lệch thông tin host, scheme hoặc IP mà ứng dụng dùng cho bảo mật và logging.

Sau khi nâng cấp, kiểm tra luồng request qua đúng ingress/proxy trong môi trường staging. Xác nhận Gateway chỉ tin header từ proxy đã khai báo và downstream nhận được giá trị `Forwarded`/`X-Forwarded-*` đúng như thiết kế.

## Quy trình nâng cấp có kiểm soát

Thực hiện lần lượt để có thể xác định nguyên nhân nếu build hoặc hành vi runtime thay đổi:

1. **Ghi nhận baseline**: lưu phiên bản Spring Boot, Spring Cloud Release Train, artifact đang dùng, cấu hình route, filter, discovery, load balancer, security và forwarded headers. Ghi lại các request kiểm thử đại diện cùng kết quả hiện tại.
2. **Chọn release train đích**: đối chiếu bảng tương thích Spring Boot/Spring Cloud và release notes của các phiên bản trung gian. Không nhảy qua một major release mà chưa đọc breaking changes của các release train liên quan.
3. **Đổi dependency**: import BOM tương thích, chuyển sang starter/module mới đúng với WebFlux, WebMVC hoặc ProxyExchange, rồi kiểm tra dependency tree để loại bỏ artifact deprecated ngoài ý muốn.
4. **Đổi property prefix**: chuyển các namespace trong mọi nguồn cấu hình. Dùng Properties Migrator tạm thời nếu cần chẩn đoán các key cũ, sau đó gỡ dependency hỗ trợ.
5. **Rà soát bảo mật và proxy**: cấu hình `trusted-proxies` khi cần header chuyển tiếp; kiểm tra lại Spring Security, TLS termination, CORS và header do ingress thêm vào.
6. **Chạy kiểm thử**: kiểm tra route predicate, filter chain, biến đổi path/header, service discovery, `lb://` load balancing, rate limit, circuit breaker, retry, timeout, TLS và metrics/tracing.
7. **Triển khai thử và quan sát**: phát hành lên staging hoặc một nhóm instance giới hạn; so sánh status code, upstream, latency, log và metric với baseline trước khi rollout toàn bộ.

## Lệnh kiểm tra dependency và cấu hình

Với Maven, có thể xem dependency tree của Gateway:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm các prefix cũ trong repository bằng công cụ tìm kiếm văn bản, ví dụ:

```bash
rg -n "spring\.cloud\.gateway(\.mvc|\.proxy)?\." .
```

Lệnh tìm kiếm chỉ bao quát file trong repository hiện tại. Hãy kiểm tra riêng Config Server, secret/config store, biến môi trường và manifest triển khai nếu chúng được quản lý ở nơi khác. Sau khi thay đổi, chạy lại tìm kiếm để xác nhận các key cũ đã được xử lý hoặc có lý do tương thích được ghi nhận.

## Các lỗi thường gặp sau nâng cấp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build không tìm thấy starter cũ hoặc báo artifact deprecated | Dependency chưa chuyển sang tên mới hoặc đang dùng release train không đồng bộ | Chọn đúng release train, cập nhật starter/module theo bảng mapping và kiểm tra dependency tree |
| Ứng dụng khởi động nhưng route không xuất hiện | YAML vẫn dùng prefix cũ hoặc property được đặt dưới nhánh WebFlux/WebMVC sai | Chuyển namespace theo module đang chạy, kiểm tra cấu hình hiệu lực và route qua Actuator |
| Route có nhưng request đi sai upstream | Route/filter bị thay đổi ngoài ý muốn hoặc cấu hình mới không được nạp | So sánh route id, URI, predicate, filter và thứ tự route với baseline |
| Host, scheme hoặc IP client thay đổi sau nâng cấp | Forwarded headers không còn được tin cậy mặc định hoặc trusted proxy chưa cấu hình đúng | Xác định proxy thực tế và đặt `trusted-proxies` phù hợp; kiểm tra header ở ingress và downstream |
| Lỗi `ClassNotFoundException` hoặc `NoSuchMethodError` | Các module Spring Cloud/Spring Boot không cùng bộ phiên bản hoặc dependency cũ còn trên classpath | Dùng BOM tương thích, loại dependency trùng và kiểm tra runtime dependency tree |
| ProxyExchange không hoạt động như Gateway Server | Chọn nhầm artifact ProxyExchange thay cho starter Server hoặc ngược lại | Xác định ứng dụng cần khai báo route hay proxy exchange trong code rồi chọn module đúng |

## Checklist trước khi hoàn tất

- [ ] Spring Boot và Spring Cloud Release Train nằm trong ma trận tương thích.
- [ ] Starter/module đã đổi sang tên mới phù hợp với WebFlux, WebMVC hoặc ProxyExchange.
- [ ] Không còn artifact deprecated ngoài các trường hợp chuyển tiếp có chủ đích.
- [ ] Prefix cấu hình đã được chuyển trong file, Config Server, biến môi trường và cấu hình triển khai.
- [ ] Properties Migrator đã được gỡ sau khi xử lý các cảnh báo.
- [ ] `trusted-proxies` phản ánh đúng các proxy tin cậy nếu ứng dụng dùng Forwarded headers.
- [ ] Route, filter, discovery, load balancing, security, resilience, TLS và observability đã được kiểm thử.
- [ ] Staging cho kết quả tương đương baseline trước khi rollout toàn bộ.

## Tài liệu tham khảo

- [Spring Cloud 2025.0 Release Notes — breaking changes của Spring Cloud Gateway](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes): bảng đổi tên module/starter, property prefix và lưu ý về trusted proxies.
- [How to Include Spring Cloud Gateway](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html): starter Gateway Server WebFlux và yêu cầu runtime.
- [Spring Cloud Gateway Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): danh sách property theo namespace WebFlux và WebMVC.

Khi nâng cấp Spring Cloud Gateway, hãy chọn đúng loại module trước, đồng bộ artifact với release train, chuyển toàn bộ namespace cấu hình và xác minh lại hành vi ở ranh giới proxy. Đây là các bước cần thiết để route predicate, filter chain, khám phá dịch vụ và cơ chế bảo mật tiếp tục vận hành đúng sau khi thay đổi tên dependency và property.
