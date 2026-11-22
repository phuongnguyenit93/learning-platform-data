# Kiểm tra cấu hình WebFlux thực tế khi thư viện bổ sung bean làm thay đổi mặc định

## 1. Bài toán: thêm một thư viện nhưng hành vi WebFlux đổi

Trong Spring Boot, cùng một mã controller WebFlux có thể trả kết quả khác sau khi thêm starter hoặc nâng phiên bản dependency, dù không sửa `application.yml`. Một thư viện có thể đóng góp cấu hình tự động (auto-configuration), định nghĩa `@Bean`, đăng ký `WebFilter`, `WebExceptionHandler`, `WebFluxConfigurer`, codec, converter, bộ định tuyến hoặc security chain. Những bean mới có thể **bổ sung** hành vi, **thay thế** bean mặc định theo điều kiện, hoặc **thay đổi thứ tự xử lý**.

Ví dụ thực tế:
- Trước khi thêm starter, `GET /api/products` trả 200; sau đó trả 401 vì Spring Security thêm filter chain.
- Thêm `WebFilter` từ thư viện làm response có header mới hoặc chặn một nhóm URL.
- Thêm `WebFluxConfigurer` làm CORS, formatters hoặc static-resource routing khác đi.
- Một `CodecCustomizer` thay đổi JSON decoding hoặc giới hạn buffer, khiến body từng được chấp nhận giờ báo lỗi.
- Một bean `WebExceptionHandler` định dạng lỗi khác trước, hoặc xử lý ngoại lệ mà controller advice không nhận.
- Một cấu hình mang `@EnableWebFlux` khiến các tùy chỉnh WebFlux của Spring Boot không còn được áp dụng như trước.

Câu hỏi chính của bài: **Làm thế nào chứng minh bean nào đến từ thư viện, điều kiện cấu hình nào thay đổi, và hành vi HTTP thực sự khác ở đâu?**

### Kết quả học tập

Sau bài này, bạn sẽ:
1. Phân biệt cơ chế auto-configuration **back off** với cơ chế **đóng góp thêm bean**.
2. Phân biệt `WebFluxConfigurer` (giữ auto-config của Boot) với `@EnableWebFlux` (tự chủ cấu hình WebFlux).
3. Đọc `ConditionEvaluationReport`, các endpoint Actuator `conditions`, `beans`, `configprops`, `env`, `mappings` đúng mục đích.
4. Kiểm tra nguồn gốc bean từ dependency, class hoặc auto-config import, thứ tự filter và thứ tự giải quyết lỗi.
5. Dựng thí nghiệm before/after có khả năng tái lập, bao gồm request, response và assertion.
6. Chọn giải pháp tối thiểu mà không vô hiệu hóa tùy tiện auto-configuration.

Phạm vi: Spring Boot **3.5.x**, Spring Framework 6, Java 17+, WebFlux reactive runtime. Mọi code có package/import cụ thể cho 3.x; khi dùng Spring Boot 4.x trở lên cần kiểm tra API và tên module tương ứng.

## 2. Hiểu đúng ba cơ chế làm thay đổi mặc định

### 2.1. Thư viện đưa bean mới vào chuỗi xử lý: additive

Nhiều loại bean có ý nghĩa **cộng thêm**, không tự loại bỏ cấu hình có sẵn.

Ví dụ, các `WebFilter` hiện diện trong application context có thể được Spring WebFlux đưa vào filter chain. Khi thư viện thêm một `WebFilter` mới, hệ thống có thêm một bước xử lý trước/sau handler. Filter đó có thể sửa request, đặt header, từ chối request hoặc bắt lỗi downstream. Controller không đổi nhưng kết quả HTTP có thể đổi.

Tương tự, một `WebFluxConfigurer` có thể thêm `CorsRegistry`, converter hoặc resource handler vào WebFlux configuration. Không phải cứ có bean `WebFluxConfigurer` là Spring Boot ngừng cấu hình WebFlux.

### 2.2. Auto-configuration rút lui vì một điều kiện không còn thỏa: back-off

Spring Boot dùng nhiều điều kiện như:

| Điều kiện thường gặp | Tác dụng khi kiểm tra | Vì sao có thể thay đổi sau khi thêm thư viện |
|---|---|---|
| `@ConditionalOnClass` | Kiểm tra một class có trong classpath | Starter mới kéo thêm API/driver/class |
| `@ConditionalOnMissingClass` | Chỉ bật khi class không có | Class mới xuất hiện khiến nhánh mặc định rút |
| `@ConditionalOnBean` | Cần bean đúng type/name | Thư viện cung cấp bean làm nhánh mới được bật |
| `@ConditionalOnMissingBean` | Chỉ tạo cấu hình/bean nếu chưa có bean phù hợp | Bean ứng dụng/thư viện xuất hiện khiến bean mặc định không được tạo |
| `@ConditionalOnProperty` | Kiểm tra property và giá trị | Dependency mang thêm cấu hình hay thay môi trường khởi động |
| `@ConditionalOnWebApplication` | Chỉ áp dụng cho web application type phù hợp | Runtime bị chọn là Servlet thay vì REACTIVE |
| `@Profile` | Chỉ tạo bean khi profile tương ứng active | Khác biệt dev/staging/prod hoặc test profile |

**Không có quy tắc “thư viện thêm bean nào cũng vô hiệu hóa mặc định”.** Phải tìm đúng auto-configuration class hoặc phương thức `@Bean` có điều kiện, và điều kiện thực sự được đánh giá.

Ví dụ minh họa cơ chế của một starter (fragment, không phải toàn bộ thư viện runnable):

~~~java
@AutoConfiguration
class VendorPolicyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RequestPolicy.class)
    RequestPolicy defaultRequestPolicy() {
        return new VendorDefaultRequestPolicy();
    }
}
~~~

Nếu một bean `RequestPolicy` khác đủ điều kiện đã tồn tại tại lúc điều kiện được đánh giá, phương thức tạo mặc định có thể không được kích hoạt. Chi tiết cần xác minh trong **conditions report**. Đối với thư viện Spring Boot 3.x viết đúng chuẩn auto-config, cấu hình của nó thường được khai báo tại `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; ví dụ fragment trên chưa chứa file đăng ký này và các type nghiệp vụ.

### 2.3. Thứ tự hoặc quyền ưu tiên của nhiều bean thay đổi

Ngay cả khi cả hai bean đều tồn tại:
- `@Order` / `Ordered` của `WebFilter` quyết định thứ tự trên đường đi vào.
- `WebExceptionHandler` có thể xử lý lỗi trước các handler khác.
- Handler mappings và router functions có cơ chế thứ tự/mức độ ưu tiên riêng; route mới có thể bắt request trước route cũ.
- `@Primary` ảnh hưởng lựa chọn bean trong một số tình huống dependency injection khi có nhiều candidate, **không** tự đổi thứ tự filter, cũng không tự làm một auto-configuration back off.
- `@Qualifier` chọn đúng bean tại điểm injection; `@ConditionalOnMissingBean` lại là một quy tắc đăng ký bean, không phải quy tắc inject.

Vì vậy kết luận phải dựa vào **bean nào được tạo, bean nào thực sự được dùng và hành vi request cuối**.

## 3. Xác nhận đây thật sự là WebFlux runtime

Đừng bắt đầu bằng việc tìm bug của `WebFilter` nếu ứng dụng đang chạy Spring MVC.

Spring Boot mặc định chọn MVC khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt. Đó là lựa chọn có chủ đích vì ứng dụng MVC đôi khi cần `WebClient`. Nếu muốn REACTIVE runtime, phải xác định application type rõ ràng, chẳng hạn khi thực sự cần bằng API `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`, và kiểm tra dependency/cấu hình phù hợp.

Phân biệt:

| Dấu hiệu | Kết luận phù hợp |
|---|---|
| Class `WebClient` có trong classpath | Chỉ chứng minh client reactive có thể dùng, **chưa** chứng minh server WebFlux |
| Có `spring-boot-starter-webflux` | Thường là dấu hiệu WebFlux, nhưng chưa đủ khi đồng thời có MVC starter |
| Context là reactive web server application context và mapping dùng `DispatcherHandler` | Bằng chứng mạnh hơn về runtime WebFlux |
| Có `WebFilter` bean nhưng request không đi qua nó | Kiểm tra type runtime, bean loading, chain và order |
| Có `FilterRegistrationBean` kiểu Servlet | Không phải công cụ đăng ký WebFlux `WebFilter` trên Reactor Netty |

Kiểm tra bằng dependency tree:

~~~bash
mvn dependency:tree
# Dự án Gradle:
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm `spring-boot-starter-web`, `spring-boot-starter-webflux`, `spring-boot-starter-security` và các vendor starter. Kiểm tra cả dependency **transitive**: một starter nội bộ có thể mang theo MVC hoặc security mà người phát triển không để ý.

## 4. Phân biệt WebFluxConfigurer và @EnableWebFlux

Đây là một khác biệt đặc biệt quan trọng khi thư viện đăng ký configuration.

### 4.1. Mở rộng cấu hình mà giữ mặc định Spring Boot

Spring Boot khuyến nghị khai báo `@Configuration` implements `WebFluxConfigurer`, nhưng **không đặt `@EnableWebFlux`**, nếu muốn bổ sung WebFlux configuration và vẫn giữ những tiện ích Boot tự cấu hình.

Ví dụ bổ sung CORS:

~~~java
@Configuration(proxyBeanMethods = false)
class CorsConfiguration implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://example.org")
                .allowedMethods("GET", "POST");
    }
}
~~~

Đây là fragment đặt trong project WebFlux với imports tương ứng. Nó chỉ thêm mapping CORS; không nhằm thay thế toàn bộ WebFlux infrastructure. Nếu một thư viện đưa bean kiểu này vào ứng dụng, CORS effective configuration có thể đổi dù không sửa property.

### 4.2. Lấy toàn quyền cấu hình WebFlux

`@EnableWebFlux` nhập cấu hình WebFlux của Spring Framework và cho phép ứng dụng quản lý việc cấu hình chi tiết. Nhưng khi dùng Spring Boot, annotation này khiến một phần **WebFlux auto-configuration của Boot rút lui**, vì Boot giả định ứng dụng muốn tự nắm quyền điều khiển WebFlux.

Hệ quả là các tùy chỉnh mặc định của Boot về codec, static resources hoặc integration khác có thể không còn giống lúc chưa thêm annotation. Không kết luận rằng framework “không còn bất kỳ mặc định nào”: Spring Framework vẫn có cấu hình của nó. Chính xác thành phần nào thay đổi phải xem conditions report và test.

Nếu một library `@Configuration` được import và vô tình chứa `@EnableWebFlux`, đây là một nghi vấn quan trọng cần kiểm tra. **Không tự động thêm `@EnableWebFlux` chỉ để một bean `WebFluxConfigurer` hoạt động** trong ứng dụng Boot.

### 4.3. Cấp can thiệp HttpHandler/codec

Có những cơ chế khác:
- `WebHttpHandlerBuilderCustomizer` có thể chỉnh builder xây `HttpHandler` do Boot tự cấu hình.
- `CodecCustomizer` có thể điều chỉnh `HttpMessageReader` và `HttpMessageWriter`, ảnh hưởng JSON, SSE, dung lượng đọc.
- `WebFilter` là lớp bao quanh request.
- `WebExceptionHandler` là lớp giải quyết lỗi ở mức WebFlux.

Cùng thay “cấu hình WebFlux”, nhưng chúng tác động các giai đoạn khác nhau. **Gọi đúng tên bean/type rồi đo hành vi thực, không suy từ tên jar**.

## 5. Bảng rà soát các bean có thể do thư viện đóng góp

| Bean/thay đổi | Dấu hiệu ở runtime | Kiểm tra chính |
|---|---|---|
| `WebFilter` | Thêm header, chặn request, thay route behavior, tăng latency | Liệt kê filter, order, test cùng một URL |
| `WebExceptionHandler` | Mã lỗi, body lỗi và content type đổi | Bean/order, lỗi ở trước handler và trong handler |
| `WebFluxConfigurer` | CORS, converter, formatters, static mappings đổi | Bean definitions, CORS preflight và mapping |
| `CodecCustomizer` | JSON/SSE/decoding khác, giới hạn memory khác | Codec registrations, payload tests, conditions |
| `WebHttpHandlerBuilderCustomizer` | HttpHandler pipeline thay đổi | Bean definition + thử đường request |
| `SecurityWebFilterChain` và security starter | 401/403, redirect/login, CSRF, CORS behavior | Security configuration và filter chain |
| `RouterFunction` / `HandlerMapping` | 404 mới, route precedence hoặc handler mới | `/actuator/mappings`, tracing request |
| `WebFluxConfigurationSupport` / `@EnableWebFlux` | Boot WebFlux auto-config không match như trước | `/actuator/conditions`, tìm annotation/import |
| `ReactiveWebServerFactory` / factory customizer | Cổng, SSL, engine hoặc server settings đổi | Bean inventory + startup log + HTTP kiểm chứng |
| Jackson module/converter bean | JSON field, null/enum/date serialization đổi | Config/codec beans + JSON golden tests |
| Một property source thêm vào | Binding khác dù file gốc không đổi | `/actuator/env`, `/actuator/configprops`, property precedence |

Cột thứ ba quan trọng: **số lượng bean tăng không đủ kết luận**. Phải xác định thêm bean có tham gia vào pipeline của endpoint đang lỗi hay không.

## 6. Quy trình điều tra từ dấu hiệu đến nguyên nhân

### Bước 1 — Chốt khác biệt có thể tái lập

Lưu baseline (trước thêm thư viện) và candidate (sau thêm thư viện):
- Commit/build hash, JDK, Spring Boot version, profile, property sources, các biến môi trường quan trọng.
- Runtime dependencies, transitive dependency tree, library versions.
- Request chính xác: method, URL, query, headers, auth, body.
- Response: status, `Content-Type`, `Access-Control-Allow-Origin`, security headers, body.
- Điều kiện mạng, reverse proxy và trạng thái DB/external API.

Giữ nguyên mọi yếu tố khác nếu có thể. Nếu vừa thêm library vừa đổi profile, sẽ khó biết nguyên nhân chính.

~~~text
BASELINE:  GET /api/probe, Origin=https://client.example
           status 200, không có X-Library, không có CORS allow-origin

CANDIDATE: GET /api/probe, Origin=https://client.example
           status 200, có X-Library và Access-Control-Allow-Origin

=> nghi vấn một WebFilter và một WebFluxConfigurer vừa được kích hoạt
~~~

Đây là ví dụ giả định để giải thích phương pháp, không phải kết quả đo từ hệ thống của bạn.

### Bước 2 — Đọc condition evaluation report

Spring Boot có thể in báo cáo quyết định auto-configuration khi bật `--debug`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Với executable JAR đã build, dùng `java -jar <tên-jar>.jar --debug` (thay tên JAR thực). Report thường chia các match và non-match, nêu điều kiện nào được thỏa hoặc không thỏa.

Câu cần trả lời:
- `WebFluxAutoConfiguration` có match trong cả hai lần chạy không?
- Có auto-config mới từ vendor được kích hoạt không?
- Có `@ConditionalOnMissingBean` nào không match vì bean cụ thể từ thư viện đã tồn tại?
- Có thêm `SecurityAutoConfiguration` hoặc cấu hình security reactive tương ứng không?
- Môi trường đã chọn Servlet thay vì REACTIVE chưa?

**Condition report là bằng chứng về quyết định tạo bean**, không phải bằng chứng duy nhất về hành vi HTTP. Cần nối với bean inventory và test.

### Bước 3 — Xem các Actuator endpoint chẩn đoán

Với `spring-boot-starter-actuator` và cấu hình **chỉ dùng trong local/test có bảo vệ**, các endpoint hữu ích:

| Endpoint | Câu trả lời |
|---|---|
| `/actuator/conditions` | Vì sao auto-config match hoặc không match |
| `/actuator/beans` | Bean nào tồn tại, type, nguồn/quan hệ phụ thuộc tùy thông tin endpoint |
| `/actuator/configprops` | `@ConfigurationProperties` nào đã bind, giá trị hiệu lực (có sanitization) |
| `/actuator/env` | Property source và giá trị `Environment` đang được giải quyết |
| `/actuator/mappings` | Controller/function/router mappings được đăng ký |
| `/actuator/health` | Ứng dụng đã chạy và tình trạng health, không chứng minh auto-config đúng |

Ví dụ local `application.properties` để điều tra:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans,configprops,env,mappings
~~~

Phải có Actuator dependency và quyền truy cập endpoint thích hợp. **Không mở công khai** những endpoint nhạy cảm trong production: bean inventory và cấu hình có thể tiết lộ tên class, kiến trúc hay bí mật, dù Spring Boot có cơ chế che giá trị nhạy cảm. Hãy bảo vệ bằng authentication/authorization hoặc chỉ chạy trong môi trường local được cô lập.

Kiểm tra:

~~~bash
curl -s http://localhost:8080/actuator/conditions
curl -s http://localhost:8080/actuator/beans
curl -s http://localhost:8080/actuator/mappings
~~~

Các phản hồi là JSON có cấu trúc lớn; không giả định mọi endpoint luôn tồn tại hoặc HTTP 200. Việc có mặt phụ thuộc dependency, exposure, access và security.

### Bước 4 — Truy nguồn bean đến đúng jar/configuration

Trong output `beans` hoặc debugger của `ApplicationContext`, xác định:
- Bean name và concrete bean type.
- Class/bean method hoặc configuration nào khai báo.
- Bean đến từ application `@ComponentScan`, `@Import`, auto-config của Boot hay vendor library.
- Conditions/profile có làm bean chỉ xuất hiện ở môi trường nhất định không.
- Bean thuộc loại additive, override injection hay khiến default bean back off.
- Filter/handler có order nào và có thực sự khớp URL lỗi không.

Ở jar thư viện, xem `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (nếu thư viện dùng cơ chế Boot 3 auto-config), hoặc các `@Configuration` được import thủ công. Không sửa file nội bộ của framework để workaround trước khi tìm đúng nguồn.

### Bước 5 — Đối chiếu hành vi HTTP cuối cùng

Thực hiện lại request baseline và candidate cùng headers, method và body. Ví dụ với CORS:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

Một phép thử CORS đầy đủ còn cần OPTIONS preflight khi client gửi phương thức/headers khiến trình duyệt phải preflight. Kiểm tra cả `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và `Access-Control-Allow-Credentials` nếu liên quan; browser có thể chặn response dù `curl` đọc được. Test phải phản ánh hợp đồng CORS thật của ứng dụng.

## 7. Ví dụ chạy được: mô phỏng thư viện bổ sung WebFlux beans

Ví dụ dưới đây dùng một cấu hình mang profile `vendor` để **mô phỏng bean mà thư viện có thể đóng góp**. Đây là một thí nghiệm local giúp quan sát trước/sau, không tuyên bố mô phỏng mọi cơ chế của một starter ngoài thực tế.

Hai bean được thêm khi bật profile `vendor`:
- Một `WebFilter` thêm header `X-Library: enabled`.
- Một `WebFluxConfigurer` khai báo CORS cho route `/probe`.

Không có `@EnableWebFlux`, nên các tiện ích auto-config của Boot được giữ.

### 7.1. Tạo Maven project, Java 17+

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-bean-drift</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

File `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,conditions,beans,configprops,mappings
~~~

Các Actuator endpoint ở đây chỉ nên thử trong local kín. Ứng dụng không khai báo Spring Security trong ví dụ; điều này không phải cấu hình an toàn để đưa trực tiếp ra Internet.

File `src/main/java/example/diag/BeanDriftApplication.java`:

~~~java
package example.diag;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BeanDriftApplication {

    public static void main(String[] args) {
        SpringApplication.run(BeanDriftApplication.class, args);
    }

    @Bean
    ApplicationRunner beanEvidence(ConfigurableApplicationContext context) {
        return args -> {
            System.out.println("LIBRARY_FILTER="
                    + context.containsBean("vendorHeaderFilter"));
            System.out.println("LIBRARY_CORS="
                    + context.containsBean("vendorCorsConfigurer"));
        };
    }
}

@RestController
class ProbeController {

    @GetMapping(path = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> probe() {
        return Mono.just("ok");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("vendor")
class SimulatedVendorLibraryConfiguration {

    @Bean
    WebFilter vendorHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders().set("X-Library", "enabled");
            return chain.filter(exchange);
        };
    }

    @Bean
    WebFluxConfigurer vendorCorsConfigurer() {
        return new WebFluxConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/probe")
                        .allowedOrigins("https://client.example")
                        .allowedMethods("GET");
            }
        };
    }
}
~~~

Trong file Java trên, có đúng một public class trùng tên file. Các class package-private nằm cùng package được `@SpringBootApplication` scan. `SimulatedVendorLibraryConfiguration` chỉ được kích hoạt khi profile `vendor` active. Import `Component` không cần thiết cho code này và có thể xóa; nó không thay đổi cách chương trình chạy.

### 7.2. Chạy baseline

Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Các dòng do `ApplicationRunner` in ra:

~~~text
LIBRARY_FILTER=false
LIBRARY_CORS=false
~~~

Ở terminal khác:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

HTTP status dự kiến là **200**, body **`ok`**. Vì chưa có vendor filter/configurer, response không có `X-Library: enabled` và không có `Access-Control-Allow-Origin: https://client.example` do cấu hình vendor trong ví dụ. Các header khác phụ thuộc container.

### 7.3. Chạy candidate với bean từ “thư viện”

Dừng instance baseline rồi chạy cùng project với profile vendor:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=vendor
~~~

Dòng do `ApplicationRunner` in ra:

~~~text
LIBRARY_FILTER=true
LIBRARY_CORS=true
~~~

Gửi lại request:

~~~bash
curl -i -H "Origin: https://client.example" http://localhost:8080/probe
~~~

Các đặc điểm dự kiến:
- HTTP **200**, body **`ok`** không đổi.
- Header **`X-Library: enabled`** xuất hiện.
- Header CORS **`Access-Control-Allow-Origin: https://client.example`** xuất hiện với Origin hợp lệ.

Thí nghiệm chứng minh sự khác biệt có thể đến từ **bean mới trong context**, dù controller và endpoint không đổi. Khi phân tích starter thật, hãy thay “bật profile vendor” bằng thay đổi dependency có kiểm soát rồi so sánh cùng kiểu bằng chứng.

### 7.4. Xác minh qua Actuator

Với môi trường local từ ví dụ:

~~~bash
curl -s http://localhost:8080/actuator/beans
curl -s http://localhost:8080/actuator/conditions
curl -s http://localhost:8080/actuator/mappings
~~~

Trong candidate, tìm `vendorHeaderFilter` và `vendorCorsConfigurer`. Trong baseline, hai bean đó không tồn tại. `conditions` cho biết quyết định auto-configuration của Boot; việc bật một bean additive có thể không làm `WebFluxAutoConfiguration` ngừng match. `mappings` cho thấy `GET /probe` vẫn được đăng ký.

**Đây là điểm quan trọng:** cùng một thay đổi hành vi HTTP nhưng `conditions` có thể không báo back-off vì chỉ có bean bổ sung trong filter/configurer chain. Đừng chờ condition report tự chỉ ra mọi biến đổi ở runtime.

## 8. Thử nghiệm thêm bean làm mặc định rút lui

Thí nghiệm trên chứng minh **additive contribution**. Để nghiên cứu **back-off**, hãy nhìn vào một auto-configuration có điều kiện `@ConditionalOnMissingBean`. Quy tắc vận hành tổng quát:

~~~text
Trước:
  Không có bean loại Policy
  -> VendorDefaultAutoConfiguration tạo defaultPolicy
  -> /actuator/conditions thể hiện điều kiện match

Sau:
  Một starter khác hoặc ứng dụng thêm bean loại Policy
  -> Điều kiện MissingBean không còn thỏa
  -> defaultPolicy không được tạo
  -> Bean Policy mới được dùng tại injection point
~~~

Sơ đồ là khái niệm. Trong Spring Boot thực, các điều kiện được đánh giá trong lúc đăng ký bean definitions theo thứ tự auto-config được xử lý. Không nên áp dụng các điều kiện `@ConditionalOnBean`/`@ConditionalOnMissingBean` một cách tùy tiện trong những `@Configuration` có thứ tự không được kiểm soát; trong starter, dùng mô hình auto-configuration và ordering chính thức của Boot.

Để chứng minh ở ứng dụng thật:
1. Lấy entry tương ứng trong `/actuator/conditions`, ghi tên auto-config method cùng thông báo điều kiện.
2. Lấy bean name/type thay thế từ `/actuator/beans`.
3. Tìm source của bean mới trong jar, `@Bean` method, `@Import` hoặc auto-config imports.
4. Thực hiện request/codec/serialization test tương ứng.
5. Nếu loại bỏ library khỏi classpath làm điều kiện match trở lại và HTTP hành xử như baseline, đây là bằng chứng mạnh về quan hệ nhân quả.

Nếu hai bean cùng type xuất hiện nhưng không có qualifier/primary, có thể phát sinh lỗi **NoUniqueBeanDefinitionException** thay vì “im lặng chọn cái khác”. Nếu hai bean cố định nghĩa cùng tên trong cấu hình cấm overriding, ứng dụng có thể **không khởi động**. Không đánh đồng xung đột bean name, injection ambiguity và conditional back-off.

## 9. Trường hợp điển hình: thư viện thêm Spring Security

Thêm security starter vào một ứng dụng WebFlux có thể làm mặc định truy cập endpoint thay đổi: một URL trước đó mở có thể yêu cầu authentication, tùy cấu hình đang có. Điều này bắt nguồn từ security auto-configuration và reactive filter chain, không phải từ việc controller tự đổi business logic.

Các bước kiểm tra:
- Kiểm tra `spring-boot-starter-security` có vào runtime classpath như dependency trực tiếp hay transitive không.
- Xem bean `SecurityWebFilterChain`, `WebFilterChainProxy` và cấu hình security liên quan.
- Đọc report cho các auto-config có điều kiện về security; không đoán theo tên package đơn lẻ.
- Gửi cùng request có và không có `Authorization` header, kiểm tra 401, 403, redirect hoặc kết quả khác.
- Không tắt security toàn cục chỉ để làm test 200; định nghĩa chính sách rõ ràng bằng security configuration và viết integration tests.

WebFlux `WebFilter` thông thường và Spring Security `WebFilterChainProxy` có thể tương tác qua order. Nhưng order của WebFilter bên ngoài **khác** thứ tự các security filters bên trong security chain. Khi một request bị chặn trước controller, `@RestControllerAdvice` không nhất thiết chịu trách nhiệm tạo response security. Hãy phân biệt authentication entry point và access denied handler của Spring Security.

## 10. Trường hợp: codecs/JSON đổi khi classpath có thêm thư viện

Spring WebFlux dùng `HttpMessageReader` và `HttpMessageWriter`, được điều phối qua codec configuration. Spring Boot cung cấp cấu hình mặc định dựa trên thư viện trong classpath và các `CodecCustomizer`.

Một module JSON/Jackson, custom deserializer hoặc codec customizer được thêm vào có thể thay đổi:
- Các media type đọc/ghi được hỗ trợ.
- Cách serialize enum, thời gian, null hoặc field đặc biệt.
- Giới hạn dữ liệu được gom vào bộ nhớ trong một lần decode.
- Cách xử lý codec errors, `415 Unsupported Media Type`, `406 Not Acceptable`, `400 Bad Request` hoặc `DataBufferLimitException`, tùy nơi lỗi xảy ra.

Đừng suy luận chỉ từ việc `CodecCustomizer` xuất hiện: cần xem nó thực sự gọi phương thức nào. Ví dụ dưới đây là fragment trong một `WebFluxConfigurer`, không phải một class đầy đủ:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

Thao tác này điều chỉnh dung lượng tối đa cho một số thao tác decode có gom dữ liệu vào RAM; nó không phải giới hạn kích thước toàn HTTP request ở mọi tình huống. Với thư viện cung cấp `CodecCustomizer`, cần xác minh cấu hình cuối cùng và test đúng payload.

**Không bật `registerDefaults(false)` trên `CodecConfigurer` nếu chưa chủ động đăng ký thay thế đầy đủ các reader/writer cần thiết.** Một customizer vô tình vô hiệu hóa codec mặc định có thể khiến endpoint JSON đột ngột thất bại.

## 11. Trường hợp: thêm route, error handler hoặc filter làm thay đổi cách xử lý

### WebFilter và thời điểm xử lý

Giá trị order nhỏ hơn thường chạy sớm hơn ở nhánh đi vào. Một filter có thể set status/headers, tiếp tục `chain.filter(exchange)`, hoặc trả phản hồi ngay mà không gọi chain. Nếu thư viện thêm filter chặn `/api/**`, request không vào controller dù mapping vẫn còn trong Actuator.

Đối với response đã commit, filter hay exception handler không thể thay status/header đã gửi. Hãy kiểm tra `exchange.getResponse().isCommitted()`, sử dụng `beforeCommit` khi thực sự cần chuẩn bị header, tránh set header bắt buộc trong `doFinally` sau khi body kết thúc.

### WebExceptionHandler

Một `WebExceptionHandler` mới có thể chặn một số lỗi trước error handler khác. Kiểm tra `@Order`/`Ordered`, loại exception được xử lý và nó trả `Mono.empty()`/publisher hoàn thành hay `Mono.error(ex)` để chuyển tiếp. Không bắt mọi lỗi rồi luôn trả status 200 vì điều đó che giấu sự cố.

### RouterFunction và HandlerMapping

Một thư viện thêm `RouterFunction` hoặc handler mapping có thể tạo route mới, đổi thứ tự mapping, hoặc làm conflict. Dùng `/actuator/mappings` và request thực để xác minh route hiệu lực. Functional route filter (`HandlerFilterFunction`) chỉ áp dụng cho router functions được bọc, còn `WebFilter` áp dụng ở mức WebFlux application; không thay thế lẫn nhau.

## 12. Kiểm thử hồi quy trong CI và môi trường tích hợp

Mục tiêu là biến giả thuyết “dependency mới có thể đổi default” thành kiểm chứng có thể chạy lại.

### 12.1. Kiểm thử hợp đồng HTTP

Với ứng dụng WebFlux có test dependency, sử dụng `WebTestClient` để khẳng định không chỉ 200 mà cả status, headers và body. Ví dụ fragment trong lớp test có `WebTestClient client` được cấu hình với application:

~~~java
client.get()
        .uri("/probe")
        .header("Origin", "https://client.example")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Library", "enabled")
        .expectHeader().valueEquals(
                "Access-Control-Allow-Origin", "https://client.example")
        .expectBody(String.class).isEqualTo("ok");
~~~

Đây là assertion cho **candidate profile vendor** của ví dụ; baseline không có hai header ấy. Với test tích hợp, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và cấu hình WebTestClient phù hợp; kiểm tra đúng profile bằng `@ActiveProfiles("vendor")`.

### 12.2. Kiểm thử khác biệt về bean definitions

Có thể khẳng định một bean thực sự hiện diện bằng Spring Test:

~~~java
assertThat(context.containsBean("vendorHeaderFilter")).isTrue();
assertThat(context.containsBean("vendorCorsConfigurer")).isTrue();
~~~

Đây là fragment trong test đã có `ApplicationContext context` và AssertJ. Chỉ kiểm tra bean có mặt vẫn **không đủ**: cần test status/header/behavior tương ứng. Nếu cần kiểm thử điều kiện auto-configuration của starter độc lập, Spring Boot cung cấp `ApplicationContextRunner` và `ReactiveWebApplicationContextRunner`/các test runner theo phiên bản; trong test cần khởi tạo đúng auto-config và environment để tránh tạo ra kết luận sai vì context chưa chứa hạ tầng WebFlux thực.

### 12.3. Lập baseline khi nâng thư viện

Cho mỗi lần nâng version/starter:
1. Giữ một manifest runtime dependencies của baseline và candidate.
2. Chạy smoke test trên status, security, CORS, JSON và những URL quan trọng.
3. Đọc condition report nếu có sự khác biệt.
4. So sánh bean inventory của những type nhạy cảm; tránh assert toàn bộ số bean vì Spring Boot nâng version có thể bổ sung bean hợp lệ.
5. Phân biệt thay đổi dự kiến đã có migration guide với hồi quy ngoài ý muốn.
6. Nếu tính năng mới yêu cầu thay đổi mặc định, ghi rõ hợp đồng mới và cập nhật tests có chủ đích.

Để test đúng, một project chỉ dùng `@WebFluxTest` sẽ không scan mọi `@Component` và mọi thư viện auto-config như một full application. Khi nghi vấn nằm ở bean thứ ba, **ưu tiên full `@SpringBootTest` với đúng dependency và profile** hoặc import rõ configuration cần kiểm tra.

## 13. Biện pháp sửa an toàn theo từng loại nguyên nhân

| Phát hiện | Hướng sửa ưu tiên | Tránh làm |
|---|---|---|
| Thư viện thêm WebFilter không mong muốn | Dùng điều kiện/property do thư viện cung cấp hoặc cấu hình filter chain/order | Tắt toàn bộ WebFlux |
| Starter bật security theo mặc định | Định nghĩa reactive security policy và test 401/403 có chủ đích | Mở tất cả endpoint để lấy lại 200 |
| `WebFluxConfigurer` đổi CORS | Điều chỉnh/exclude bean config cụ thể, xác minh preflight | Gán `allowedOrigins("*")` tùy tiện với credentials |
| `@EnableWebFlux` bị import ngoài ý muốn | Bỏ annotation khỏi cấu hình nếu muốn giữ Boot auto-config | Cố bổ sung từng bean mặc định mà chưa hiểu hậu quả |
| `CodecCustomizer` thay codec | Sửa/customize codec tối thiểu, kiểm thử JSON và payload lớn | Vô hiệu hóa tất cả codec mặc định |
| Một bean làm auto-config back off | Xem tên/type/conditions, đổi chiến lược registration hoặc rõ ràng override | Bật bean definition overriding như giải pháp đầu tiên |
| Thư viện thêm route | Điều chỉnh router order, path/matcher hoặc module routing | Xóa controller đang hoạt động mà không có test |
| `WebExceptionHandler` đổi lỗi | Chỉ bắt exception đúng loại và tôn trọng committed response | Trả chung 200/400 cho mọi Throwable |
| App chạy MVC thay vì WebFlux | Rà soát dependencies và web application type | Giả định chỉ cần WebClient là đủ |

**Ưu tiên sửa đúng tại nguyên nhân:** property chính thức của starter, điều kiện tạo bean, qualifier/order/matcher hoặc cấu hình Spring WebFlux được Boot hỗ trợ. `spring.autoconfigure.exclude` có thể vô hiệu hóa một auto-config cụ thể khi thực sự cần, nhưng đó là thao tác phạm vi rộng và có thể bỏ luôn các bean quan trọng khác. Phải xem danh sách bean/conditions thay đổi sau khi exclude.

## 14. Chẩn đoán khi ứng dụng không khởi động

Không phải mọi thay đổi mặc định đều biểu hiện bằng HTTP 401 hoặc khác JSON. Một starter có thể khiến ứng dụng fail startup.

Các loại lỗi đáng phân biệt:

- **BeanDefinitionOverrideException:** có bean cùng tên được đăng ký trong điều kiện không cho overriding; tìm cả hai nguồn khai báo. Không “sửa nhanh” bằng bật `spring.main.allow-bean-definition-overriding=true` khi chưa giải thích xung đột.
- **NoUniqueBeanDefinitionException:** nhiều bean cùng type đủ điều kiện injection; sử dụng đúng `@Qualifier`, `@Primary` hoặc thiết kế một bean duy nhất, theo yêu cầu thực tế.
- **NoSuchBeanDefinitionException:** default bean rút lui nhưng một thành phần vẫn đòi dependency không còn tồn tại; kiểm tra conditions và import chain.
- **Ambiguous mapping:** route annotation hoặc functional route trùng nhau, thứ tự/handler không được giải quyết đúng; xem mappings và code đăng ký.
- **ClassNotFoundException/NoClassDefFoundError:** dependency version/classpath không tương thích, khác với lỗi back-off hợp lệ.
- **Stack trace khi tạo codec/mapper:** Java configuration từ library có thể tạo bean lỗi trước khi runtime bắt đầu nhận request.

Đọc **root cause** ở cuối cause chain và so với condition report; không kết luận mọi lỗi Spring context là do “auto-config không nhận bean”.

## 15. Những sai lầm thường gặp

1. **“Thêm bean thì Boot luôn tự tắt default.”** Sai: có bean dạng additive như `WebFilter`, `WebFluxConfigurer`.
2. **“Có WebClient nghĩa là server WebFlux.”** Sai: MVC cũng có thể dùng WebClient.
3. **“@EnableWebFlux chỉ cần để kích hoạt Spring Boot WebFlux.”** Sai: annotation này chuyển quyền kiểm soát nhiều phần cấu hình khỏi Boot.
4. **“@Primary quyết định WebFilter chạy trước.”** Sai: `@Order`/`Ordered` và cách lắp ráp chain mới liên quan.
5. **“Điều kiện match nghĩa là endpoint chắc chắn hoạt động như mong đợi.”** Sai: còn filter, routing, codecs, security và response writer.
6. **“Thấy thêm Security starter nên lỗi 401 là lỗi controller.”** Sai: request có thể bị security filter chặn trước.
7. **“Chỉ test HTTP 200 là đủ.”** Sai: headers, CORS preflight, content type và JSON có thể đổi.
8. **“Đã thấy bean trong /actuator/beans nghĩa là bean ấy xử lý request.”** Sai: nó còn phải được runtime dùng và matcher đúng.
9. **“Dùng @WebFluxTest luôn giống production context.”** Sai: test slice thường loại một số bean/cấu hình ngoài phạm vi.
10. **“Actuator /conditions đủ để tìm mọi thay đổi.”** Sai: các bean additive có thể đổi behavior mà không làm auto-config back off.
11. **“Có thể công khai /actuator/env/beans để debug production.”** Sai: endpoint có dữ liệu nội bộ, cần giới hạn và bảo vệ.
12. **“Chỉ cần xóa thư viện khi có khác biệt.”** Không luôn phù hợp: thư viện có thể cần cho security/codec; cấu hình lại đúng mức và thêm test.
13. **“Cùng property file thì môi trường giống nhau.”** Sai: profile, environment variables, classpath và auto-config conditions có thể khác.
14. **“Bật allow-bean-definition-overriding giúp tìm root cause.”** Nó có thể che khuất xung đột thay vì giải quyết.
15. **“Thêm custom codec nào cũng an toàn.”** Có thể vô hiệu hóa default readers/writers hoặc đổi memory behavior.

## 16. Checklist điều tra trước khi merge thay đổi dependency

- [ ] Đã xác nhận ứng dụng chạy đúng `WebApplicationType.REACTIVE`, không nhầm MVC.
- [ ] Đã ghi danh sách dependency trực tiếp và transitive trước/sau.
- [ ] Đã tái lập request lỗi với cùng profile/property/headers/body.
- [ ] Đã đọc auto-configuration conditions, đặc biệt nhánh `@ConditionalOnMissingBean`.
- [ ] Đã tìm bean mới qua `/actuator/beans` hoặc `ApplicationContext` và ghi nguồn khai báo.
- [ ] Đã phân loại bean là additive, back-off, injection selection hoặc thay đổi order.
- [ ] Đã kiểm tra thư viện có import `@EnableWebFlux` hoặc `WebFluxConfigurationSupport` không.
- [ ] Đã kiểm tra `WebFilter`, `WebExceptionHandler`, `WebFluxConfigurer`, codecs, routing và security.
- [ ] Đã đọc các property có hiệu lực, không chỉ file cấu hình gốc.
- [ ] Đã xác nhận HTTP status/headers/body và CORS preflight bằng request thực.
- [ ] Đã có test trong full application context nếu thư viện cấu hình qua auto-config.
- [ ] Đã chọn phương án sửa nhỏ nhất và đo lại trước/sau.
- [ ] Không expose Actuator endpoints nhạy cảm ra public để phục vụ debug.
- [ ] Đã lưu tài liệu về quyết định bean/configuration mới và hành vi mong đợi.

## 17. Kết luận

Khi thêm một thư viện khiến hành vi Spring WebFlux thay đổi, đừng bắt đầu bằng cách vô hiệu hóa auto-configuration. Hãy **xác nhận runtime, so sánh dependency, đọc điều kiện cấu hình, tìm bean mới, xác định cách bean ấy được dùng, rồi kiểm chứng bằng HTTP request thực**. Bean do thư viện thêm có thể bổ sung trực tiếp vào filter chain, ghi đè cấu hình qua order/DI hoặc khiến một mặc định rút lui theo `@ConditionalOnMissingBean`. `WebFluxConfigurer` thường là cách mở rộng giữ các tiện ích của Spring Boot; `@EnableWebFlux` mang ý nghĩa cấu hình chủ động hơn. Một thay đổi chỉ được xem là đã hiểu khi có bằng chứng cả ở **bean/conditions** lẫn **runtime response**, và một test đủ cụ thể để ngăn hồi quy.

## Tài liệu tham khảo

- Spring Boot 3.5 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html
- Spring Boot 3.5 — Actuator endpoints: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Framework 6 — WebFlux Config: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
