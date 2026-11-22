# Builder do Spring Boot quản lý và những tùy chỉnh được áp dụng

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** HTTP client

## 1. Bài toán: cùng một HTTP client, tại sao cấu hình không giống nhau?

Một service Spring Boot gọi API bên ngoài qua HTTP. Nhóm phát triển muốn mọi outbound request có tracing/metrics, timeout hợp lý, message converter/codec nhất quán và một header nhận diện. Nhưng kết quả quan sát có thể trái ngược:

- Một component nhận **RestClient.Builder** từ Spring, tạo client và có đầy đủ header do hệ thống thêm.
- Component khác viết **RestClient.create(...)**, gửi được request nhưng thiếu header hoặc instrumentation mà ứng dụng đã cấu hình.
- Một nơi dùng **WebClient.Builder** được inject, nơi khác gọi **WebClient.create()**; hai client có thể dùng connector, codecs hoặc customizers khác nhau.
- Một service dùng **RestTemplateBuilder** và nhìn thấy thay đổi từ **RestTemplateCustomizer**, nhưng **new RestTemplate()** không có cùng tùy chỉnh.
- Một cấu hình **@Bean RestTemplateBuilder** được viết để thêm timeout nhưng vô tình thay thế builder của Spring Boot và làm mất các customizers mặc định.

Vấn đề cốt lõi không phải Spring Boot tự áp chính sách cho **mọi object HTTP client trong JVM**. Spring Boot cung cấp **các builder đã được auto-configure**; những client được tạo **qua đúng builder** mới nhận các cấu hình tương ứng. Việc **đăng ký customizer**, **phạm vi của builder**, **thứ tự tùy chỉnh** và **cách tạo client** quyết định cấu hình cuối cùng.

Bài học tập trung vào ba nhóm quan trọng của Spring Boot **3.3.x** với Spring Framework 6.1 và Java 17+:

1. **RestClient.Builder** → **RestClient** dạng imperative/synchronous; thường là lựa chọn mới cho luồng blocking.
2. **RestTemplateBuilder** → **RestTemplate** dạng imperative/synchronous, hữu ích khi duy trì ứng dụng đã dùng RestTemplate.
3. **WebClient.Builder** → **WebClient** dạng reactive, non-blocking I/O khi sử dụng đúng luồng Reactor.

Hiểu rõ Spring Boot quản lý phần nào, những tùy chỉnh nào được áp dụng, cái gì bị mất khi tự tạo builder, cách kiểm thử và ranh giới với HTTP server.

## 2. Spring Boot quản lý builder, không đồng nghĩa quản lý mọi client

Tài liệu chính thức **Spring Boot 3.3 – Calling REST Services** nêu:

| API client | Spring Boot tự tạo gì khi dependency phù hợp? | Đặc điểm builder | Customizer tương ứng |
| --- | --- | --- | --- |
| **RestClient** | **RestClient.Builder** đã cấu hình, scope **prototype** | **Stateful**: thay đổi một builder ảnh hưởng những client được build sau đó từ chính builder ấy | **RestClientCustomizer** |
| **RestTemplate** | **RestTemplateBuilder**, không mặc định có một **RestTemplate** bean dùng chung | Kiểu **immutable/functional**: mỗi phương thức cấu hình trả builder mới | **RestTemplateCustomizer** |
| **WebClient** | **WebClient.Builder** đã cấu hình, scope **prototype** | **Stateful**: thay đổi một builder ảnh hưởng những client được build sau đó từ chính builder ấy | **WebClientCustomizer** |

**Spring Boot không tự tạo một RestTemplate singleton để tất cả service dùng.** Bạn inject **RestTemplateBuilder**, rồi tạo RestTemplate với cấu hình của thành phần cần sử dụng. Tương tự, Boot tạo builder cho RestClient/WebClient; nếu dự án muốn một client riêng với base URL và authentication cụ thể, hãy tạo client đó trong **@Configuration** bằng builder được inject.

**Builder prototype** không có nghĩa mỗi lần gọi **build()** nó sẽ reset. Nó nghĩa Spring có thể cung cấp **một builder instance mới khi bean đó được yêu cầu từ container**, ví dụ các injection points khác nhau. Nếu một singleton giữ một WebClient.Builder và thay baseUrl nhiều lần, các lần build tiếp theo từ builder ấy vẫn chịu thay đổi. Ngược lại, RestTemplateBuilder trả một đối tượng builder mới cho mỗi bước cấu hình, giúp giảm rủi ro mutate chung.

**Client cuối cùng không nhất thiết là bean được Boot quản lý.** Bạn có thể tạo:

~~~java
RestClient client = injectedRestClientBuilder
        .baseUrl("https://service.example.test")
        .build();
~~~

Client này là object Java do code bạn build. Nếu muốn inject **RestClient** qua @Autowired ở nơi khác, hãy đăng ký nó thành **@Bean RestClient** hoặc tạo service chịu trách nhiệm sử dụng client. Không suy ra chỉ vì Spring Boot có RestClient.Builder bean thì sẽ có RestClient bean duy nhất.

## 3. Pipeline auto-configuration và nơi customizer can thiệp

Một mô hình thực dụng:

~~~text
Dependencies + Spring Boot auto-configuration
     |
     +--> HTTP client/request factory/connector detection
     +--> HttpMessageConverters / Codec configuration
     +--> SSL bundle, resource factories neu duoc cau hinh
     +--> Observation/metrics/tracing hooks neu co
     |
     v
Spring-managed Builder
     |
     +--> RestClientCustomizer / WebClientCustomizer (tren builder)
     +--> RestTemplateCustomizer (tren RestTemplate khi build)
     |
     v
Local customizations o service/@Bean
     |  baseUrl, default headers, filters, timeouts...
     v
.build()
     |
     v
Outbound HTTP client -> Request -> Response
~~~

**Tầng nào đã cấu hình gì?**

- **Spring Framework** định nghĩa các API RestClient, RestTemplate, WebClient và những HTTP transports tương ứng.
- **Spring Boot auto-configuration** chọn các default có ích dựa vào classpath và các beans đang có, đưa vào builder, đặc biệt converters/codecs và HTTP transport phù hợp.
- **Customizer beans** giúp module hoặc thư viện nội bộ thêm quy tắc chung vào các builder/client được Boot tạo.
- **Local builder calls** giúp từng upstream service đặt base URL, authentication, timeouts hoặc headers khác nhau.
- **Client object đã build** được dùng thực hiện request; thay đổi một builder sau khi client được build **không phải** cơ chế cấu hình lại tất cả client đã tồn tại.

Mục đích thiết kế là **cấu hình một lần ở đúng mức phạm vi**, không sao chép các interceptor và timeout vào từng service. Nhưng phải tránh global customizer chứa bí mật riêng của một upstream, vì nó có thể áp dụng cho **mọi client** thuộc cùng nhóm API.

## 4. RestClient.Builder do Boot quản lý

**RestClient** được Spring Framework 6.1 giới thiệu dưới dạng fluent **imperative** API. Trong Spring Boot 3.3, khi REST client support hiện diện, Boot tạo **prototype RestClient.Builder bean**, cấu hình **HttpMessageConverters** và **ClientHttpRequestFactory** thích hợp.

Cách phổ biến trong service:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Caller", "orders")
                .build();
    }

    public ProductView findById(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductView.class);
    }

    public record ProductView(long id, String name) {}
}
~~~

Đây là **service minh họa**, không chạy độc lập vì **catalog.example.test** là domain ví dụ và cần dự án Spring Boot chứa endpoint phù hợp. Trong ví dụ runnable ở phần 9, ta gọi một endpoint localhost để kiểm được header thật.

Điểm quan trọng:

- **RestClient.Builder** được Spring inject vào constructor. Bạn thêm baseUrl và header **cục bộ** cho client này.
- **.build()** tạo RestClient có thể sử dụng nhiều lần; không cần tạo client mới cho từng request.
- **.retrieve().body(ProductView.class)** giải mã JSON bằng converters thích hợp nếu server trả body đúng.
- Các HTTP status lỗi (4xx/5xx) có thể gây exception theo cơ chế retrieve; muốn error mapping riêng cần dùng **onStatus(...)** hoặc xử lý exception theo hợp đồng API.
- URL ví dụ cần được thay bằng cấu hình environment thực trong ứng dụng production; không hardcode secrets hoặc host không kiểm soát.

### RestClientCustomizer cho tùy chỉnh toàn ứng dụng

Một bean:

~~~java
package com.example.catalog;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogRestClientCustomization {

    @Bean
    RestClientCustomizer addClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Platform-Client", "spring-boot-service");
    }
}
~~~

Spring Boot tự nhận các bean **RestClientCustomizer** và áp dụng chúng cho **RestClient.Builder do Boot auto-configure**. Kết quả: các RestClient được build từ những builder này sẽ có default header trên, trừ khi cấu hình request cụ thể hoặc cơ chế ghi đè phù hợp thay đổi nó.

**Không phải mọi RestClient trên classpath đều được customizer áp dụng.** Ví dụ:

~~~java
// Tao client qua static factory cua Spring Framework:
RestClient raw = RestClient.create("https://example.test");
~~~

Đường này **không đi qua builder auto-configure của Spring Boot**, nên không thừa hưởng **RestClientCustomizer** hay toàn bộ Boot auto-configuration/observation. Nó vẫn là một RestClient hợp lệ theo Spring Framework và có defaults riêng; vấn đề là **khác cấu hình dự kiến của ứng dụng**.

**RestClient.Builder là stateful**. Nếu một singleton có cùng một builder và gọi **baseUrl(A).build()**, rồi **baseUrl(B).build()**, nó có thể vô tình áp các tùy chỉnh cũ còn giữ trên builder B. Nếu cần nhiều client khác nhau trong cùng scope, có thể **builder.clone()** trước khi chỉnh riêng:

~~~java
RestClient first = builder.clone()
        .baseUrl("https://service-a.example.test").build();
RestClient second = builder.clone()
        .baseUrl("https://service-b.example.test").build();
~~~

Đây là đoạn ví dụ **trong constructor hoặc factory đã nhận builder**, không phải class Java độc lập. Builder clone giúp tách mutations, nhưng vẫn giữ cấu hình gốc/Boot defaults của builder tại thời điểm clone.

## 5. WebClient.Builder do Boot quản lý

**WebClient** dùng fluent reactive API với **Mono**/**Flux**, thường dựa trên Reactor Netty khi có starter WebFlux. Spring Boot 3.3 tạo **prototype WebClient.Builder** đã cấu hình, hỗ trợ việc chọn **ClientHttpConnector**, đồng bộ HTTP codecs và có thể chia sẻ tài nguyên HTTP phù hợp với server reactive.

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogClient {

    private final WebClient client;

    public ReactiveCatalogClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Caller", "reactive-orders")
                .build();
    }

    public Mono<ProductView> findById(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductView.class);
    }

    public record ProductView(long id, String name) {}
}
~~~

Đây cũng là **minh họa API**, không là ứng dụng hoàn chỉnh. Để dùng WebClient, cần dependency **spring-webflux** hoặc **spring-boot-starter-webflux**, kể cả khi server chính chạy Servlet Spring MVC. Thêm WebFlux chỉ để sử dụng WebClient **không mặc nhiên biến toàn bộ server MVC thành Reactive WebFlux**; Boot thường chọn Servlet nếu có cả spring-webmvc và spring-webflux.

### WebClientCustomizer

~~~java
package com.example.catalog;

import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientCustomization {

    @Bean
    WebClientCustomizer clientHeader() {
        return builder -> builder.defaultHeader(
                "X-Platform-Client", "reactive-service");
    }
}
~~~

Tương tự RestClient, **WebClientCustomizer** có phạm vi **WebClient.Builder do Boot cấu hình**, không tự chỉnh một WebClient đã được tạo từ **WebClient.create()** hoặc **WebClient.builder()** gọi thủ công.

**WebClient.Builder cũng stateful.** Hãy inject tại các component cần cấu hình riêng; khi tạo nhiều clients từ cùng builder, clone:

~~~java
WebClient blue = builder.clone()
        .baseUrl("https://blue.example.test").build();
WebClient green = builder.clone()
        .baseUrl("https://green.example.test").build();
~~~

Điểm cần hiểu thêm: **API reactive không tự bảo đảm mọi xử lý hoàn toàn non-blocking**. Nếu gọi **.block()** trên Netty event loop hoặc thực hiện công việc blocking nặng trong reactive pipeline, bạn có thể gây nghẽn; tránh điều đó trong ứng dụng WebFlux. Với ứng dụng MVC, WebClient có thể được dùng để gọi async và controller có thể trả **Mono** do MVC hỗ trợ reactive return types; đừng xem việc có WebClient làm server MVC trở thành non-blocking end-to-end.

## 6. RestTemplateBuilder và RestTemplateCustomizer

Spring Boot **không tự cung cấp một RestTemplate bean chung**, bởi những instance thường cần được thiết lập khác nhau theo upstream. Nó tạo **RestTemplateBuilder** có converters và **ClientHttpRequestFactory** phù hợp.

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyCatalogClient {
    private final RestTemplate template;

    public LegacyCatalogClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("https://catalog.example.test")
                .setConnectTimeout(Duration.ofSeconds(2))
                .setReadTimeout(Duration.ofSeconds(5))
                .build();
    }

    public ProductView findById(long id) {
        return template.getForObject(
                "/products/{id}", ProductView.class, id);
    }

    public record ProductView(long id, String name) {}
}
~~~

Đoạn minh họa dành cho ứng dụng có builder được Spring inject và upstream thật. **rootUri** chỉ được áp dụng với URI template phù hợp, thường là URI path bắt đầu bằng **/**; nó không có cùng semantics với **baseUrl** của RestClient/WebClient trong mọi trường hợp.

**Sự khác biệt quan trọng:** mỗi lời gọi như **builder.rootUri(...)** hoặc **setReadTimeout(...)** trả về **một RestTemplateBuilder mới**; builder cũ không bị mutate. Do đó:

~~~java
RestTemplateBuilder configured = builder.setReadTimeout(
        Duration.ofSeconds(5));

// builder != configured ve object instance.
// build tu builder goc khong tu dong nhan readTimeout=5s.
RestTemplate oldPolicy = builder.build();
RestTemplate newPolicy = configured.build();
~~~

Đây là đoạn code minh họa bên trong một component đã nhận **builder**, không phải chương trình độc lập. Nó dạy sự khác biệt giữa **functional builder** và **stateful builder**.

### RestTemplateCustomizer có thời điểm áp dụng khác

**RestTemplateCustomizer** nhận **RestTemplate object** sau khi builder cấu hình nó, ví dụ thêm interceptor:

~~~java
package com.example.catalog;

import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyClientCustomization {

    @Bean
    RestTemplateCustomizer identifyOutgoingCalls() {
        return template -> template.getInterceptors().add(
                (request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Platform-Client", "legacy-template");
                    return execution.execute(request, body);
                });
    }
}
~~~

Customizer được Boot nhận vào **RestTemplateBuilder auto-configured**, rồi được áp dụng khi **build()** ra RestTemplate. Một RestTemplate tạo bằng **new RestTemplate()** không tự nhận nó. Bạn cũng có thể chỉnh **message converters, error handler, request factory, interceptors**, nhưng phải hiểu tác động của từng bước; đừng thay cả danh sách converters khi chỉ cần thêm một converter.

**Cẩn thận với phương thức thay thế và bổ sung:**

- **RestTemplateBuilder.customizers(...)** thay danh sách customizer đã cấu hình trên builder.
- **RestTemplateBuilder.additionalCustomizers(...)** thêm customizer mà không chủ động xoá danh sách trước đó.
- **RestTemplateBuilder.messageConverters(...)** thay danh sách converters; **additionalMessageConverters(...)** thêm vào danh sách.
- Tương tự, **interceptors(...)** và **additionalInterceptors(...)** có semantics khác nhau.

Một lời gọi mang nghĩa **replace** có thể làm mất các customizers của Boot/Actuator, dù bạn chỉ định thêm một interceptor. Khi muốn bổ sung hành vi, ưu tiên phương thức **additional...** hoặc đăng ký một bean customizer ở scope phù hợp.

## 7. Tùy chỉnh cục bộ và toàn cục: nên đặt vào đâu?

| Loại chính sách | Nơi nên cấu hình | Lý do |
| --- | --- | --- |
| Base URL của upstream catalog | Builder trong **@Bean CatalogRestClient** hoặc service riêng | Chỉ thuộc catalog, không áp lên billing/payments. |
| Header **X-Service-Name** chung | **RestClientCustomizer**, **WebClientCustomizer**, hoặc RestTemplateCustomizer theo API | Có thể dùng chung cho mọi outgoing requests cần nhận diện. |
| Header Authorization cho một upstream | Client riêng, request filter riêng, hoặc credential provider gắn với upstream đó | Tránh lộ token cho hostname khác. |
| Connect/read/response timeout khác nhau theo upstream | Builder/request factory/connector riêng của client | Phụ thuộc SLA của upstream và retry policy. |
| Metrics/tracing HTTP client | Dùng builder do Spring Boot cấu hình với Actuator/observation khi đã bật | Tránh bỏ lỡ instrumentation bởi static factories. |
| JSON converters/codecs chung | Auto-configuration và customizers có kiểm soát | Thống nhất serialization, nhưng tránh phá cấu hình mặc định. |
| Proxy chỉ cho một upstream | Client request factory/connector riêng | Không vô tình route mọi outbound traffic qua proxy. |
| SSL trust bundle mTLS cho upstream nội bộ | SSL bundle theo client, không tắt certificate verification | Khóa/cert và trust policy khác nhau theo đích. |
| Logging outbound headers | Filter/interceptor có redact và whitelist | Không log Authorization/Cookie/PII hoặc payload nhạy cảm. |

**Global customizer không phải "mọi thứ càng nhiều càng tốt".** Nếu thêm một default Authorization header toàn cục, request có thể gửi token ấy tới bất kỳ host nào do client cùng builder gọi. Đây là lỗi rò rỉ credential nghiêm trọng; giữ credential trong client được cấu hình cho **một target/trust boundary**.

**Local customization** không làm mất global customizers nếu bạn tiếp tục dùng Boot-managed builder. Nhưng nếu local call thay thế toàn bộ connector, converters hoặc filters, có thể vô tình phủ quyết một phần nền tảng. Nên thử tích hợp để xác nhận chính xác hành vi.

### Vấn đề thứ tự customizers

Nhiều customizer beans có thể cùng tồn tại. Spring hỗ trợ **@Order** hoặc **Ordered** cho một số collection beans; mức độ ảnh hưởng cụ thể phụ thuộc cơ chế auto-configure và API mà customizer gọi.

Nếu hai customizers cùng gọi **defaultHeader("X-Flag", ...)**, không nên đoán bừa "customizer B luôn thắng" vì **merge/replace semantics** của builder và độ ưu tiên theo order có thể khác. Thay vì tranh chấp cùng một cấu hình, nên có **một owner rõ ràng**; nếu cần thứ tự, dùng explicit ordering và integration test trên request thật.

## 8. Điều gì xảy ra khi tự tạo builder hoặc client?

Đây là phần dễ gây sai nhất.

| Cách tạo | Có nhận Boot auto-configuration/customizers? | Ghi chú |
| --- | --- | --- |
| Inject **RestClient.Builder** rồi build | **Có**, trong điều kiện auto-configure tương ứng hoạt động | Cách ưu tiên cho RestClient. |
| Gọi **RestClient.create()** hoặc **RestClient.builder()** thủ công | **Không tự động** | Spring Framework tạo builder/client với mặc định riêng, bỏ qua Boot-managed customizers. |
| Inject **WebClient.Builder** rồi build | **Có** | Cách ưu tiên cho WebClient. |
| Gọi **WebClient.create()** hoặc **WebClient.builder()** thủ công | **Không tự động** | Có thể bỏ qua codec/resource/observability customizers của Boot. |
| Inject **RestTemplateBuilder** rồi build | **Có** | Chạy RestTemplateCustomizers từ builder Boot. |
| Gọi **new RestTemplate()** hoặc **new RestTemplateBuilder()** thủ công | **Không tự động** | Không thừa hưởng những customizers của Boot nếu không áp dụng chúng thủ công. |
| Tạo một **@Bean RestTemplateBuilder** tùy chỉnh không dùng configurer | **Có thể làm Boot back off** và bỏ customizers của Boot | Dùng RestTemplateBuilderConfigurer khi thật sự cần thay builder. |
| Tạo một **@Bean RestClient.Builder** tùy chỉnh không dùng configurer | **Có thể thay** prototype builder auto-configured và thiếu Boot defaults | Dùng RestClientBuilderConfigurer theo Spring Boot 3.3 khi cần. |
| Tạo một **@Bean WebClient.Builder** hoàn toàn mới | **Có thể làm auto-configure back off**, không tự có customizers | Ưu tiên inject builder Boot; hoặc áp dụng các WebClientCustomizers có chủ đích. |

**Boot auto-configuration có điều kiện**: loại bean nào được tạo phụ thuộc classpath, properties và những user-defined beans sẵn có. Không suy rằng mọi project đều có đủ ba builder. Ví dụ **WebClient.Builder** đòi module WebFlux/HTTP client tương ứng trên classpath.

### Khi buộc phải thay RestTemplateBuilder bean

Đoạn dưới là **phương án nâng cao thay thế**, không đặt vào cùng demo phần 9 (vì demo đã dùng default builder). Đoạn này cần nằm trong **một Java @Configuration class riêng** với imports đúng:

~~~java
package com.example.alternative;

import java.time.Duration;

import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomRestTemplateBuilderConfiguration {
    @Bean
    RestTemplateBuilder restTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {
        return configurer.configure(new RestTemplateBuilder())
                .setConnectTimeout(Duration.ofSeconds(3))
                .setReadTimeout(Duration.ofSeconds(5));
    }
}
~~~

**RestTemplateBuilderConfigurer** là cách Spring Boot 3.3 cho phép bạn **giữ các defaults/customizers tương thích** rồi thêm chính sách timeout, thay vì tự tạo new RestTemplateBuilder rỗng không kế thừa cấu hình. Những lời gọi setConnectTimeout/setReadTimeout trong Boot 3.3 có tiền tố **set**; đừng copy cú pháp của phiên bản Spring Boot khác mà chưa kiểm tra API.

### Khi buộc phải thay RestClient.Builder bean

**RestClientBuilderConfigurer** của Spring Boot 3.3 có phương thức **configure(RestClient.Builder)** để thêm các default Boot. Ví dụ cấu hình prototype thay thế (đặt vào **một project riêng**, không dùng chung với demo):

~~~java
package com.example.alternative;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CustomRestClientBuilderConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    RestClient.Builder restClientBuilder(
            RestClientBuilderConfigurer configurer) {
        return configurer.configure(RestClient.builder())
                .defaultHeader("X-Platform", "learning");
    }
}
~~~

Đặt **@Scope(PROTOTYPE)** nếu muốn giữ tính tách biệt giữa các injection points như builder Boot mặc định. Việc tự tạo một singleton stateful builder rồi mutate baseUrl ở nhiều nơi có thể làm lẫn config giữa upstream.

**Không mặc định có một WebClientBuilderConfigurer giống hệt RestClientBuilderConfigurer** với cùng API trên mọi version. Nếu thay WebClient.Builder auto-configure, bạn phải tự xem và giữ lại các **WebClientCustomizer**, codec/connector/resource setup và observation liên quan; lựa chọn an toàn hơn vẫn là inject builder đã được Boot tạo.

## 9. Demo chạy được: ba client cùng truy cập một endpoint

Demo này kiểm chứng sự khác biệt giữa **global customizer** và **local customization** trên **RestClient**, **RestTemplate** và **WebClient**.

### 9.1. Project và dependencies

Dùng Spring Boot **3.3.13**, Java 17+ và Maven. Thêm **spring-boot-starter-web** và **spring-boot-starter-webflux** trong cùng ứng dụng để có đủ API; khi cả hai có trên classpath, Boot mặc định chạy **Servlet Spring MVC/Tomcat**, WebFlux được dùng ở đây để cung cấp WebClient.

Có thêm **spring-boot-starter-actuator** để có thể quan sát HTTP client metrics khi cấu hình endpoint phù hợp. Đây là thành phần **tùy chọn** cho mục tiêu HTTP client builder, không bắt buộc trong mọi dự án.

Cấu trúc:

~~~text
managed-http-clients/
  pom.xml
  src/main/
    java/com/example/clients/
      ManagedClientsApplication.java
      OutboundClientConfiguration.java
    resources/
      application.properties
  src/test/
    java/com/example/clients/
      ManagedClientBuilderTests.java
~~~

Tạo **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>managed-http-clients</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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

### 9.2. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=managed-http-clients

# Chi de quan sat metrics tren may hoc.
management.endpoints.web.exposure.include=health,metrics
~~~

**Quan trọng:** trong demo, các HTTP clients sẽ gọi lại chính server ở localhost:8080 để không phụ thuộc API ngoài. Trên production cần thay localhost bằng URL từ cấu hình environment, thiết lập DNS/TLS và tách quyền truy cập.

Không expose toàn bộ Actuator endpoints ra internet. Nếu bật **metrics** endpoint ở production, phải bảo vệ quyền truy cập hoặc dùng kênh nội bộ theo chính sách giám sát.

### 9.3. Main class, remote endpoint và gateway endpoints

Tạo **src/main/java/com/example/clients/ManagedClientsApplication.java**:

~~~java
package com.example.clients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ManagedClientsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagedClientsApplication.class, args);
    }
}

// DTO duoc JSON serializer/deserializer xu ly cho ca ba clients.
record EchoResponse(String global, String local) {}

@RestController
class DownstreamEchoController {

    @GetMapping("/remote/echo")
    EchoResponse echo(
            @RequestHeader(value = "X-Global", defaultValue = "missing")
                    String global,
            @RequestHeader(value = "X-Local", defaultValue = "missing")
                    String local) {
        return new EchoResponse(global, local);
    }
}

@RestController
class GatewayController {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;

    GatewayController(RestClient restClient,
            RestTemplate restTemplate,
            WebClient webClient) {
        this.restClient = restClient;
        this.restTemplate = restTemplate;
        this.webClient = webClient;
    }

    @GetMapping("/gateway/restclient")
    EchoResponse restClientEcho() {
        return restClient.get()
                .uri("/remote/echo")
                .retrieve()
                .body(EchoResponse.class);
    }

    @GetMapping("/gateway/resttemplate")
    EchoResponse restTemplateEcho() {
        return restTemplate.getForObject(
                "/remote/echo", EchoResponse.class);
    }

    @GetMapping("/gateway/webclient")
    Mono<EchoResponse> webClientEcho() {
        return webClient.get()
                .uri("/remote/echo")
                .retrieve()
                .bodyToMono(EchoResponse.class);
    }
}
~~~

**Giải thích runnable:**

- Chỉ **ManagedClientsApplication** là public top-level class, khớp tên file. Controller và record package-private cùng package được scan/đọc bởi Boot, dùng được với Java 17.
- **DownstreamEchoController** trả đúng những giá trị header mà server **thật sự nhận**. Đây là phép thử có thể quan sát, không phải đoán config trong builder.
- **GatewayController** dùng các client đã tạo từ builder được Boot quản lý. Hai endpoint RestClient/RestTemplate xử lý đồng bộ. Endpoint WebClient trả **Mono<EchoResponse>**, MVC với ReactiveAdapterRegistry phù hợp có thể xử lý reactive return type; điều đó không biến server MVC thành WebFlux.
- Demo gọi một endpoint **trên cùng Tomcat :8080** để dễ kiểm thử. Với lượng concurrent requests lớn, tự gọi cùng server có thể tiêu tốn thêm worker threads; **không dùng topology loopback này làm mô hình production**.
- Nếu network upstream thật trả 404/500 hoặc timeout, các phương thức retrieve/getForObject có thể ném exception; cần chính sách error handling riêng khi đem vào hệ thống thật.

### 9.4. Configuration: ba global customizers và ba local clients

Tạo **src/main/java/com/example/clients/OutboundClientConfiguration.java**:

~~~java
package com.example.clients;

import java.time.Duration;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class OutboundClientConfiguration {

    // GLOBAL: ap dung cho RestClient.Builder do Spring Boot tao.
    @Bean
    RestClientCustomizer restClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Global", "restclient-global");
    }

    // GLOBAL: ap dung cho RestTemplate xay qua RestTemplateBuilder.
    @Bean
    RestTemplateCustomizer restTemplateHeader() {
        return template -> template.getInterceptors().add(
                (request, body, execution) -> {
                    request.getHeaders().set(
                            "X-Global", "resttemplate-global");
                    return execution.execute(request, body);
                });
    }

    // GLOBAL: ap dung cho WebClient.Builder do Spring Boot tao.
    @Bean
    WebClientCustomizer webClientHeader() {
        return builder -> builder.defaultHeader(
                "X-Global", "webclient-global");
    }

    // LOCAL: chi client RestClient nay co baseUrl/X-Local nay.
    @Bean
    RestClient restClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8080")
                .defaultHeader("X-Local", "restclient-local")
                .build();
    }

    // LOCAL: timeout, rootUri, X-Local cho RestTemplate nay.
    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://localhost:8080")
                .setConnectTimeout(Duration.ofSeconds(2))
                .setReadTimeout(Duration.ofSeconds(5))
                .defaultHeader("X-Local", "resttemplate-local")
                .build();
    }

    // LOCAL: baseUrl va X-Local chi cho WebClient nay.
    @Bean
    WebClient webClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8080")
                .defaultHeader("X-Local", "webclient-local")
                .build();
    }
}
~~~

**Cấu hình này cho thấy hai lớp thật:**

- **X-Global** thuộc customizers tương ứng; nó được Boot đưa vào client do Boot-managed builder tạo.
- **X-Local** chỉ thuộc client được tạo cho gateway cụ thể, không tự xuất hiện ở RestClient/WebClient/RestTemplate khác.
- RestTemplate dùng interceptor vì **RestTemplateCustomizer** tác động lên RestTemplate sau bước cấu hình builder; không phải API RestClient.Builder.
- Timeout RestTemplate là cục bộ, không sửa WebClient hay RestClient. **Timeout của HTTP client không phải cùng một property với server connection timeout**.
- Với WebClient, builder của Boot có thể chia sẻ Reactor Netty HTTP resources và dùng codecs/observation phù hợp; tự tạo **WebClient.create()** không thừa hưởng đầy đủ những customizations đó.

### 9.5. Chạy và xem kết quả

Từ thư mục chứa **pom.xml**:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Sau khi server nghe cổng 8080, gọi từ một terminal khác:

~~~bash
curl -fsS http://localhost:8080/gateway/restclient
curl -fsS http://localhost:8080/gateway/resttemplate
curl -fsS http://localhost:8080/gateway/webclient
~~~

Body logic dự kiến (thứ tự field JSON có thể khác):

~~~json
{"global":"restclient-global","local":"restclient-local"}
~~~

~~~json
{"global":"resttemplate-global","local":"resttemplate-local"}
~~~

~~~json
{"global":"webclient-global","local":"webclient-local"}
~~~

Nếu cả ba response lần lượt đúng giá trị, ta xác nhận:

1. Client RestClient nhận **RestClientCustomizer** riêng.
2. RestTemplate tạo từ builder nhận **RestTemplateCustomizer** riêng.
3. WebClient nhận **WebClientCustomizer** riêng.
4. Các **local settings** được áp dụng độc lập theo từng client.

Đừng cố cho rằng kết quả thành công chứng minh mọi tính năng observation, retry, TLS hoặc pooling đã cấu hình đúng: header test chỉ chứng minh **những tùy chỉnh đã kiểm**.

### 9.6. Quan sát Actuator HTTP client metrics

Vì demo thêm actuator và expose **metrics** trên localhost, sau một vài HTTP calls có thể thử:

~~~bash
curl -fsS http://localhost:8080/actuator/metrics/http.client.requests
~~~

Trong Spring Boot 3.3, **HTTP client observation/metrics** cho RestClient, RestTemplate và WebClient được hỗ trợ khi tạo client qua những **auto-configured builders**. Với Actuator/Micrometer configuration thích hợp, metric thường có tên **http.client.requests**.

Số lượng measurements/tags phụ thuộc request đã thực hiện, auto-configuration, metric registry và tracing/observation context. Nếu không thấy tên metric, kiểm actuator dependency, endpoint exposure, builder source và observation settings; không tuyên bố metric chắc chắn xuất hiện trong mọi cấu hình.

**Metrics HTTP client không thay thế logs lỗi, distributed tracing hoặc kiểm request headers.** Mục tiêu ở đây là chỉ ra một lợi ích của việc tạo client qua Boot-managed builder thay vì static factory.

## 10. Integration test không cần gọi service ngoài

Thay vì chỉ kiểm context có bean, có thể kiểm **request thật mà client định gửi**. Spring test cung cấp **MockRestServiceServer** để mô phỏng HTTP request của RestClient/RestTemplate; WebClient có thể được kiểm qua một **ExchangeFunction stub**.

Tạo **src/test/java/com/example/clients/ManagedClientBuilderTests.java**:

~~~java
package com.example.clients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@SpringBootTest
class ManagedClientBuilderTests {

    @Autowired
    ApplicationContext context;

    @Test
    void restClientAndWebClientBuildersArePrototype() {
        RestClient.Builder firstRest =
                context.getBean(RestClient.Builder.class);
        RestClient.Builder secondRest =
                context.getBean(RestClient.Builder.class);
        assertNotSame(firstRest, secondRest);

        WebClient.Builder firstWeb =
                context.getBean(WebClient.Builder.class);
        WebClient.Builder secondWeb =
                context.getBean(WebClient.Builder.class);
        assertNotSame(firstWeb, secondWeb);
    }

    @Test
    void restTemplateBuilderChangesReturnNewBuilder() {
        RestTemplateBuilder original =
                context.getBean(RestTemplateBuilder.class);
        RestTemplateBuilder changed =
                original.setReadTimeout(Duration.ofSeconds(3));
        assertNotSame(original, changed);
    }

    @Test
    void restClientCustomizerIsApplied() {
        RestClient.Builder builder =
                context.getBean(RestClient.Builder.class);

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();
        RestClient client = builder
                .baseUrl("https://upstream.example.test")
                .build();

        server.expect(requestTo("https://upstream.example.test/ping"))
                .andExpect(header("X-Global", "restclient-global"))
                .andRespond(withSuccess(
                        "{\"global\":\"ok\",\"local\":\"test\"}",
                        MediaType.APPLICATION_JSON));

        EchoResponse body = client.get()
                .uri("/ping")
                .retrieve()
                .body(EchoResponse.class);

        assertEquals("ok", body.global());
        server.verify();
    }

    @Test
    void restTemplateCustomizerIsApplied() {
        RestTemplate template = context
                .getBean(RestTemplateBuilder.class)
                .rootUri("https://upstream.example.test")
                .build();

        MockRestServiceServer server =
                MockRestServiceServer.createServer(template);

        server.expect(requestTo("https://upstream.example.test/ping"))
                .andExpect(header("X-Global", "resttemplate-global"))
                .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

        String result = template.getForObject("/ping", String.class);
        assertEquals("ok", result);
        server.verify();
    }

    @Test
    void webClientCustomizerIsApplied() {
        WebClient.Builder builder =
                context.getBean(WebClient.Builder.class);

        WebClient client = builder
                .exchangeFunction(request -> {
                    assertEquals("webclient-global",
                            request.headers().getFirst("X-Global"));
                    return Mono.just(ClientResponse.create(HttpStatus.OK)
                            .header(HttpHeaders.CONTENT_TYPE,
                                    MediaType.TEXT_PLAIN_VALUE)
                            .body("ok")
                            .build());
                })
                .build();

        String body = client.get()
                .uri("https://upstream.example.test/ping")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        assertEquals("ok", body);
    }
}
~~~

**Giải thích test:**

- **@SpringBootTest** khởi tạo application context với các bean builder/customizer đang có; vì không chạy server HTTP thật, chúng ta không gọi các bean gateway đã build từ localhost 8080 trong tests này.
- **RestClient.Builder/WebClient.Builder** được lấy hai lần từ Spring context để kiểm prototype. Một singleton đã inject builder từ trước vẫn giữ instance của chính nó; prototype **không** tự thay đổi field sau injection.
- **RestTemplateBuilder** trả đối tượng khác khi đặt read timeout.
- **MockRestServiceServer.bindTo(RestClient.Builder)** và **createServer(RestTemplate)** dùng mock request factory để kiểm outbound headers, không gửi yêu cầu đến hostname ví dụ.
- **WebClient.Builder.exchangeFunction(...)** tạo stub nhận **ClientRequest**; test trực tiếp header do customizer thêm mà không dùng network.
- **block(Duration...)** chỉ dùng trong **JUnit test** để lấy kết quả; trong reactive production path, tránh block Netty event loop.
- Có thể mở rộng test để xác nhận **local config** và error handling, nhưng phần global header đã có một phép kiểm riêng cho mỗi API.

Nếu cần kiểm **timeout, DNS, TLS, pool, proxy hoặc streaming thực**, mock tests là chưa đủ: phải dùng server test thật và latency/failure injection phù hợp, không đoán hành vi connector từ mock response.

## 11. SSL bundles, timeout, connector và request factory

Spring Boot 3.3 có **SSL bundles** để tách cấu hình trust material và client certificate khỏi code. Với RestClient hoặc WebClient được Boot auto-configure, có thể inject **RestClientSsl** hoặc **WebClientSsl** và gọi **builder.apply(ssl.fromBundle("..."))**, khi bundle đã được khai báo.

Ví dụ cục bộ cho RestClient 3.3 (đặt trong service đã nhận hai dependency, **không phải chương trình độc lập**):

~~~java
RestClient secureClient = restClientBuilder
        .baseUrl("https://internal.example.test")
        .apply(restClientSsl.fromBundle("internal"))
        .build();
~~~

Trong Spring Boot 3.3, **RestClientSsl** ở package **org.springframework.boot.autoconfigure.web.client**, còn **WebClientSsl** ở **org.springframework.boot.autoconfigure.web.reactive.function.client**. Dùng SSL bundles thật từ application config/secret store; không tắt certificate/hostname verification để "sửa SSL".

**Timeout không giống nhau giữa các API:**

- **RestTemplateBuilder.setConnectTimeout(...)** và **setReadTimeout(...)** ở Boot 3.3 áp dụng lên request factory tương ứng.
- **RestClient.Builder** của Spring Framework cần request factory cấu hình timeout/HTTP client thích hợp; không giả định nó có tất cả tiện ích giống RestTemplateBuilder ở cùng version.
- **WebClient** thường dùng **ClientHttpConnector** (ví dụ Reactor Netty) có connect/response timeout, pool và event loop semantics riêng. Muốn override connector phải xét việc mất hoặc thay đổi tài nguyên HTTP được Boot chia sẻ.
- **Read timeout**, **response timeout**, **connect timeout**, **TLS handshake timeout**, **connection pool acquire timeout** và deadline toàn request là các khái niệm khác nhau. Đừng tuyên bố cấu hình một timeout duy nhất bảo đảm mọi call luôn kết thúc trong X giây.

Đối với RestClient trên Boot 3.3 có thể dùng **ClientHttpRequestFactorySettings** và **ClientHttpRequestFactories**:

~~~java
// Vi du ben trong mot constructor da inject cac dependencies.
ClientHttpRequestFactorySettings settings =
        ClientHttpRequestFactorySettings.DEFAULTS
                .withConnectTimeout(Duration.ofSeconds(2))
                .withReadTimeout(Duration.ofSeconds(5));
ClientHttpRequestFactory factory =
        ClientHttpRequestFactories.get(settings);

RestClient client = builder
        .baseUrl("https://internal.example.test")
        .requestFactory(factory)
        .build();
~~~

Đoạn này cần imports **org.springframework.boot.web.client.ClientHttpRequestFactorySettings**, **ClientHttpRequestFactories** và **org.springframework.http.client.ClientHttpRequestFactory**, cùng **java.time.Duration**. Nó cho thấy **factory tùy chỉnh được đưa vào builder trước build**, không phải chỉ viết một property server và mong client tự nhận.

**Chú ý nhánh phiên bản:** API tổ chức HTTP client settings/request factory thay đổi giữa Spring Boot **3.3**, **3.4**, **3.5** và **4.x**. Khi áp dụng vào dự án, tra cứu đúng Javadoc của version hiện tại. Không copy ví dụ dùng **spring.http.clients.\*** hoặc **ClientHttpRequestFactoryBuilder** của dòng Boot mới rồi giả định property/class có sẵn trong Boot 3.3.

## 12. Chọn HTTP transport: phụ thuộc classpath

Builder do Boot quản lý không đồng nghĩa dùng một transport bất biến. Trong Spring Boot 3.3:

**RestClient và RestTemplate** lựa chọn request factory theo classpath và điều kiện cấu hình, ưu tiên ví dụ **Apache HttpClient**, **Jetty HttpClient**, **OkHttp (deprecated)**, rồi **simple JDK HttpURLConnection** theo danh sách tài liệu chính thức của nhánh 3.3.

**WebClient** có thể chọn reactive connector dựa trên classpath, với thứ tự tài liệu 3.3 là **Reactor Netty**, **Jetty RS Client**, **Apache HttpClient**, rồi **JDK HttpClient**.

**Không chọn HTTP library chỉ từ tên class RestClient.** Nếu thay dependencies, default transport có thể đổi, ảnh hưởng pool, proxy, timeout, TLS và performance. Đừng chỉ benchmark trên laptop rồi bỏ qua container deployment có dependency khác.

Với WebClient/reactor-netty, Boot có thể quản lý shared resource factories. Nếu bạn tự tạo **new ReactorClientHttpConnector(HttpClient.create())** cho từng client, bạn có thể không chia sẻ cấu hình tài nguyên như dự kiến. Khi cần tuning, tạo **một connector được quản lý** và kiểm lifecycle/disposal, thay vì tạo event loops/pools vô hạn.

**HTTP/2** ở outbound client cũng là đặc tính của transport và peer, **không được bật tự động cho mọi request** chỉ vì server Spring Boot có **server.http2.enabled=true**. HTTP server configuration và HTTP client configuration thuộc hai đường kết nối khác nhau.

## 13. Quan sát, metrics/tracing và filters

Tài liệu Spring Boot Actuator 3.3 nói rằng instrumentation HTTP client cho **RestTemplate**, **WebClient** và **RestClient** được áp dụng khi **inject auto-configured builder rồi tạo client**. Nếu dùng static factory và không áp dụng customizers tương ứng, request có thể thiếu **Observation/metrics/tracing** mà bạn kỳ vọng.

Theo cấu hình Actuator/Micrometer phù hợp, tên metric thường là **http.client.requests**. Các tags hợp lệ có thể gồm method, URI template, status và outcome. Tránh đưa **user ID, raw URL có dữ liệu nhạy cảm, token hoặc high-cardinality input** vào low-cardinality metric tags.

### Filters/interceptors có thể thấy khác nhau

- **RestClient** có **ClientHttpRequestInterceptor** hoặc request interceptors theo API thích hợp; khi customizer gắn vào builder, nó có thể ảnh hưởng mọi instance build sau đó.
- **RestTemplate** có **ClientHttpRequestInterceptor** trên template object; customizer áp dụng khi build. Cách thêm/cài danh sách interceptors ảnh hưởng thứ tự thực thi.
- **WebClient** dùng **ExchangeFilterFunction**/filters trong reactive pipeline; chúng phải tôn trọng **Mono/Flux** semantics và không block event loop.

Ví dụ minh họa riêng cho WebClient filter, không đưa trực tiếp vào demo cùng tên configuration:

~~~java
WebClient client = builder
        .filter((request, next) -> {
            // Khong log Authorization/Cookie hoac body nhay cam.
            System.out.println("calling " + request.method());
            return next.exchange(request);
        })
        .build();
~~~

Đây là snippet trong scope đã có **WebClient.Builder builder**. Filter nên ghi log có cấu trúc, redact thông tin nhạy cảm và không làm I/O blocking trong reactive chain. Trên production, không nên log tất cả URL/raw headers tùy ý.

### Khác biệt customizer và request-time customization

Một global customizer thường chạy **khi builder được tạo/chuẩn bị**, còn interceptor/filter chạy **mỗi request**. Ví dụ:

~~~text
Start application / inject builder:
  RestClientCustomizer -> add default header
  WebClientCustomizer  -> add filter
  RestTemplateCustomizer -> attach interceptor after build

At request time:
  Client -> interceptor/filter -> HTTP transport -> upstream
~~~

Đừng viết customizer tạo một token ngắn hạn rồi đóng băng token đó trong default header vĩnh viễn. Với token xoay vòng, nên dùng credential provider hoặc request filter lấy token hợp lệ vào **lúc gửi request**, có xử lý refresh/expiration và giới hạn host.

## 14. Bẫy stateful builder và cách tránh rò cấu hình

### 14.1. RestClient.Builder và WebClient.Builder stateful

Ví dụ xấu ở một singleton:

~~~java
// builder la field shared cua singleton.
RestClient a = builder.baseUrl("https://a.example.test")
        .defaultHeader("Authorization", "Bearer token-a")
        .build();

RestClient b = builder.baseUrl("https://b.example.test").build();
// Builder b co the van giu default Authorization cua a.
~~~

Nếu cùng một builder bị mutate cho nhiều upstream, các default headers/filters/error handlers được thêm trước có thể tiếp tục được giữ. **Đây là rủi ro rò credential**, không chỉ sai URL.

Cách hợp lý:

~~~java
RestClient a = builder.clone()
        .baseUrl("https://a.example.test")
        .defaultHeader("X-Caller", "A").build();

RestClient b = builder.clone()
        .baseUrl("https://b.example.test")
        .defaultHeader("X-Caller", "B").build();
~~~

Lưu ý cả hai vẫn dùng cấu hình **gốc** của builder; clone **không xoá** bất kỳ global sensitive header nào đã được thêm trước đó. Vì vậy token cụ thể nên gắn ở request/filter riêng của client, không ở global builder cho mọi host.

### 14.2. RestTemplateBuilder immutable

Với RestTemplateBuilder:

~~~java
RestTemplateBuilder first = builder
        .rootUri("https://a.example.test");

RestTemplateBuilder second = builder
        .rootUri("https://b.example.test");
// first va second duoc cau hinh rieng tu builder goc.
~~~

Các builder mới có thể tạo RestTemplate khác nhau mà không mutate **builder gốc**. Tuy nhiên **client object** RestTemplate sau build có nhiều setters/mutable state; không nên thay config của một RestTemplate đang được các threads sử dụng đồng thời.

### 14.3. Prototype scope và singleton injection

Nếu có:

~~~java
@Service
class SharedClientFactory {
    private final WebClient.Builder builder;

    SharedClientFactory(WebClient.Builder builder) {
        this.builder = builder;
    }
}
~~~

Đây là một singleton giữ **một** prototype builder đã được inject vào thời điểm tạo singleton. Mỗi lần gọi builder trong cùng factory **không phải một prototype instance mới**. Muốn mỗi lần tạo client nhận builder mới từ container, có thể inject **ObjectProvider<WebClient.Builder>** và lấy instance tại lúc cần, hoặc clone builder đang giữ.

**Không cần lấy một builder mới cho mọi HTTP request.** Thường build client **một lần khi khởi tạo service** và tái sử dụng object. Tăng số client/connection pools vô tội vạ vừa tốn tài nguyên vừa làm khó quan sát.

## 15. SSL, proxy, authentication và tính đúng khi ra production

Một vài nguyên tắc áp dụng từ bài học:

1. **Chỉ đưa secret vào client dành cho upstream cần secret.** Không tạo global RestClientCustomizer đặt cùng Authorization cho mọi service.
2. **Không tắt TLS certificate verification/hostname checking** để giải quyết lỗi trust; cấu hình **SSL bundle** có CA/truststore và client certificate phù hợp.
3. **Proxy configuration** thuộc HTTP transport; chọn đúng nơi đặt policy cho mỗi client, không áp dụng proxy nhạy cảm lên toàn JVM nếu không cần.
4. **Connect/read/response timeout** phải giới hạn theo SLO và budget của request; nếu có retry, giới hạn số lần, backoff, idempotency và deadline tổng.
5. **Retry không tự đến từ builder**: nếu cần Resilience4j/Spring Retry hay filter retry, thiết kế ở lớp phù hợp; không retry POST không idempotent một cách mù quáng.
6. **CORS không phải vấn đề cho server-to-server RestClient/WebClient** theo nghĩa browser CORS enforcement. Nếu API bên ngoài trả 403, kiểm authentication/authorization, WAF và hợp đồng API; không tự cho rằng cần CORS header.
7. **Chọn đủ HTTP client dependencies**; classpath có thể làm thay đổi connector/factory Boot chọn, khiến metric/performance/TLS khác nhau.
8. **Dùng correlation/trace context** theo framework/observability integration, không tự sinh một global header và cho rằng distributed tracing đã hoàn chỉnh.
9. **Giữ cấu hình client tập trung theo tên upstream**, tránh một builder singleton bị mutate luân phiên cho nhiều host.
10. **Test behavior thay vì chỉ test bean tồn tại.** Một bean RestClient.Builder có mặt không chứng minh request đã có timeout/header/tracing policy.

## 16. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân điển hình | Hướng khắc phục |
| --- | --- | --- |
| Không tìm thấy bean **RestTemplate** để @Autowired | Boot cung cấp RestTemplateBuilder, không tự tạo một RestTemplate singleton | Tạo RestTemplate từ builder trong service hoặc khai báo @Bean RestTemplate. |
| WebClient.Builder không inject được | Thiếu WebFlux client dependency hoặc auto-config không hoạt động | Thêm spring-webflux/starter-webflux, kiểm condition report. |
| Client có request nhưng thiếu header toàn cục | Dùng RestClient.create/WebClient.create/new RestTemplate hoặc custom builder bỏ customizers | Inject Boot builder, tạo client từ đó, kiểm request thật. |
| RestClientCustomizer không tác dụng lên WebClient | Sai nhóm customizer | Dùng WebClientCustomizer cho WebClient.Builder. |
| RestTemplateCustomizer không tác dụng lên RestClient | Customizer chỉ dành cho RestTemplate | Dùng RestClientCustomizer. |
| Một client bị gửi token của upstream khác | Tái sử dụng stateful builder và mutate Authorization/baseUrl | Clone hoặc tách builder/client theo upstream, không global secret. |
| Mất metrics sau refactor | Thay builder auto-configure bằng static factory | Kiểm client creation path, actuator/observation, customizers. |
| Mất customizers sau khi tự khai báo RestTemplateBuilder bean | Auto-configuration backs off, không dùng RestTemplateBuilderConfigurer | Dùng configurer hoặc inject builder auto-configured thay vì thay thế. |
| Không thay đổi config như kỳ vọng với RestTemplateBuilder | Bỏ qua đối tượng builder mới trả về bởi setter | Gán/chaining kết quả rồi gọi build trên builder đó. |
| WebClient còn dùng baseUrl cũ | Cùng một stateful builder bị mutate nhiều lần trong singleton | Clone trước cấu hình riêng, build client ổn định. |
| Timeout cấu hình trong server.* nhưng outbound call không bị giới hạn | Server timeout không phải HTTP client timeout | Cấu hình request factory/connector của client. |
| Chạy MVC nhưng lại có WebClient | Thêm WebFlux cho client không mặc định đổi server stack | Xác nhận web application type, server/connector thực. |
| Code từ Boot 4.x không compile trên 3.3 | API/properties đã đổi version | Đọc đúng Javadoc/version và dùng Boot 3.3-specific APIs. |
| Mock test PASS nhưng TLS/proxy lỗi ở production | Mock bỏ qua network, SSL, DNS, pooling | Bổ sung integration/network tests trên topology thực. |
| Gọi RestClient trong Netty event loop làm chậm | RestClient là blocking client | Dùng WebClient reactive hoặc offload blocking theo kiến trúc phù hợp. |

## 17. Câu hỏi vận dụng và câu trả lời

**Câu 1.** Spring Boot 3.3 có tự tạo một RestTemplate bean singleton cho mọi service không?  
**Không.** Nó tự cấu hình **RestTemplateBuilder** để bạn tạo RestTemplate theo nhu cầu.

**Câu 2.** Builder nào của Boot 3.3 là prototype và stateful?  
**RestClient.Builder** và **WebClient.Builder**. RestTemplateBuilder có hành vi functional, trả đối tượng mới khi cấu hình.

**Câu 3.** Vì sao RestClient.create() có thể thiếu metrics/header dù @Bean RestClientCustomizer đã có?  
Vì static factory không dùng **Boot-managed RestClient.Builder**, nên không tự nhận customizers và instrumentation.

**Câu 4.** RestTemplateCustomizer áp dụng khi nào?  
Nó được **RestTemplateBuilder auto-configured** sử dụng khi tạo/configure RestTemplate, không tự thay mọi RestTemplate đã tồn tại.

**Câu 5.** Một singleton inject prototype WebClient.Builder, sau đó mutate baseUrl nhiều lần. Có phải mỗi lần gọi build có builder mới không?  
**Không.** Singleton giữ cùng một instance đã inject; nên tạo client riêng có kiểm soát hoặc clone builder.

**Câu 6.** Thêm Authorization cho upstream A ở global WebClientCustomizer rồi dùng builder đó để gọi B có nguy hiểm không?  
**Có.** Header bí mật có thể bị gửi sang sai upstream. Cấu hình credential cục bộ theo trust boundary.

**Câu 7.** Tại sao nên dùng RestTemplateBuilderConfigurer khi cần override @Bean RestTemplateBuilder?  
Để giữ những defaults/customizers do Boot thiết lập thay vì tạo builder rỗng.

**Câu 8.** Tại sao test bean tồn tại không đủ?  
Có thể bean tồn tại nhưng request cuối không có header, timeout hoặc instrumentation; cần test outbound request thực tế hoặc mock HTTP client boundary.

**Câu 9.** Có thể dùng WebClient trong Spring MVC không?  
**Có**, với WebFlux client dependency; điều đó không mặc định biến server MVC thành reactive server.

**Câu 10.** Global customizer được áp vào tất cả client objects trong JVM?  
**Không.** Nó tác động tới đúng loại builder do Boot cấu hình và những client được tạo qua builder đó.

**Câu 11.** Khi thay transport library trong pom.xml, HTTP client behavior có thể đổi không?  
**Có.** Boot tự phát hiện connector/request factory theo classpath; pooling/timeout/TLS có thể thay đổi.

**Câu 12.** Nếu cần SSL/mTLS cho service A nhưng không cần cho B, nên chỉnh ở đâu?  
Trên builder/client **riêng của service A** với SSL bundle phù hợp, không nới lỏng global TLS validation.

## 18. Checklist áp dụng vào dự án thật

- [ ] Xác định HTTP client được dùng: RestClient, RestTemplate hay WebClient; có dùng đúng dependency không.
- [ ] Dùng **constructor injection** với builder auto-configured của Spring Boot khi có thể.
- [ ] Tạo client ổn định theo từng upstream, không build/mutate cùng builder trong mọi request.
- [ ] Đặt **global cross-cutting defaults** vào customizer đúng API; **base URL, token, TLS, timeout riêng** đặt cục bộ.
- [ ] Phân biệt **prototype stateful builders** và **functional RestTemplateBuilder**.
- [ ] Không vô ý dùng **RestClient.create/WebClient.create/new RestTemplate** khi cần Boot customizers.
- [ ] Không tạo custom builder @Bean thay auto-configure nếu không cần; nếu bắt buộc, giữ configurer/customizers.
- [ ] Tránh thay toàn bộ converters, interceptors hoặc connector khi chỉ cần bổ sung một phần nhỏ.
- [ ] Xác nhận **observation/metrics/tracing** hoạt động bằng instrumented client và chỉ báo phù hợp.
- [ ] Test outbound request headers, serialization, HTTP error handling, timeout và SSL trên client phù hợp.
- [ ] Rà soát nguy cơ token leakage từ global defaultHeader hoặc stateful builder dùng chung.
- [ ] Kiểm HTTP transport được chọn theo classpath và lifecycle của connection pool/event loop.
- [ ] Xác nhận API/properties đúng version Spring Boot (đặc biệt 3.3 so với 3.4/4.x).
- [ ] Kiểm lỗi mạng thật và proxy/TLS/redirect ở production; mock tests không thay thế tất cả.
- [ ] Thực hiện code review để mỗi upstream có cấu hình và trust boundary rõ ràng.

## 19. Tài liệu chính thống

- **Spring Boot 3.3.13 – Calling REST Services:** https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html — RestClient.Builder prototype, WebClient.Builder prototype, RestTemplateBuilder, ba customizers, cách tránh bypass auto-configuration.
- **Spring Boot 3.3.13 – RestTemplateBuilder Javadoc:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html — setReadTimeout, setConnectTimeout, rootUri, additionalCustomizers, converters, interceptors.
- **Spring Boot 3.3.13 – RestClientBuilderConfigurer Javadoc:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientBuilderConfigurer.html — configure builder thay thế trên nền defaults của Boot.
- **Spring Boot 3.3.13 – WebClientCustomizer package:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/package-summary.html
- **Spring Boot 3.3 – Metrics / HTTP Client Metrics:** https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html — instrumentation thông qua builders auto-configured và metric http.client.requests.
- **Spring Framework 6.1 – REST Clients:** https://docs.spring.io/spring-framework/reference/integration/rest-clients.html — RestClient, WebClient, RestTemplate, transport, conversion.
- **Spring Framework 6.1 – MockRestServiceServer API:** https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html — bindTo(RestClient.Builder), createServer(RestTemplate).
