# Hàm tùy biến (customizer) và cách giữ các mặc định còn lại

Spring Boot cung cấp nhiều cấu hình mặc định để ứng dụng có thể khởi động nhanh: web server, bộ chuyển đổi JSON, HTTP client builder, message converter, MVC infrastructure và nhiều thành phần khác. Khi cần thay đổi một chi tiết, cách an toàn thường là **tùy biến đối tượng hoặc builder mà Spring Boot đã chuẩn bị**, chỉ chỉnh phần cần thiết và để các cấu hình còn lại tiếp tục hoạt động.

Đây là mục đích của mẫu **customizer**: một callback nhận một đối tượng cấu hình hoặc builder, rồi thay đổi một vài thuộc tính trước khi đối tượng được sử dụng. Trong Spring Boot, nhiều extension point được thiết kế dưới dạng interface có phương thức `customize(...)`. Ứng dụng có thể đăng ký customizer dưới dạng bean; Spring Boot sẽ thu thập và áp dụng nó tại giai đoạn cấu hình thích hợp.

Ví dụ, nếu chỉ muốn bật pretty print cho JSON, ta có thể đăng ký một `Jackson2ObjectMapperBuilderCustomizer` để bật đúng một feature. Không cần tự tạo toàn bộ `ObjectMapper`. Nếu chỉ muốn đổi port web server, ta có thể dùng `WebServerFactoryCustomizer` để sửa port của factory mà Boot đang cấu hình, thay vì tự xây dựng toàn bộ server factory.

Bài học này tập trung vào cách customizer hoạt động, những extension point phổ biến, thứ tự áp dụng nhiều customizer và cách tránh vô tình thay thế các mặc định có ích của Spring Boot.

## 1. Customizer là gì?

**Customizer** là một thành phần nhận một đối tượng đã được tạo hoặc chuẩn bị bởi framework, sau đó điều chỉnh đối tượng đó theo nhu cầu ứng dụng. Nó thường biểu diễn một hành động cấu hình nhỏ, có mục tiêu cụ thể.

Có thể hình dung:

~~~text
Spring Boot chuẩn bị builder / factory
                 |
                 v
        Áp dụng customizer
                 |
                 v
        Đối tượng đã tùy biến
                 |
                 v
        Build / khởi tạo / sử dụng
~~~

Ví dụ tổng quát bằng Java:

~~~java
public interface Customizer<T> {
    void customize(T target);
}
~~~

Đây là hình minh họa một contract generic, không phải khẳng định mọi API customizer của Spring Boot đều dùng đúng interface này. Nhiều API có interface chuyên biệt, ví dụ `WebServerFactoryCustomizer<T>` hoặc `Jackson2ObjectMapperBuilderCustomizer`.

Một customizer thường có những đặc điểm:

- Nhận một đối tượng mục tiêu, chẳng hạn builder, factory hoặc client.
- Chỉ thực hiện thay đổi có liên quan tới trách nhiệm của nó.
- Không tự sở hữu toàn bộ quá trình tạo đối tượng.
- Được gọi tại một thời điểm xác định trong quá trình cấu hình.
- Có thể được đăng ký như bean để framework tự tìm và áp dụng.

### Customizer khác với factory method như thế nào?

Factory method tạo ra một đối tượng:

~~~java
@Bean
public PaymentClient paymentClient() {
    return new PaymentClient();
}
~~~

Customizer điều chỉnh đối tượng mà một cơ chế khác sẽ tạo hoặc cung cấp:

~~~java
@Bean
public PaymentClientCustomizer paymentClientCustomizer() {
    return client -> client.setConnectTimeout(Duration.ofSeconds(3));
}
~~~

`PaymentClientCustomizer` ở ví dụ thứ hai là interface giả định của ứng dụng. Nó minh họa cách tách hành động cấu hình khỏi việc tạo đối tượng.

Factory trả về instance; customizer thường nhận target và thay đổi nó. Hai cơ chế có thể kết hợp, nhưng chúng giải quyết hai trách nhiệm khác nhau.

## 2. Vì sao nên tùy biến thay vì tự tạo lại toàn bộ?

Giả sử Spring Boot đang cấu hình Jackson để xử lý JSON. Cấu hình mặc định có thể bao gồm:

- Module hỗ trợ kiểu dữ liệu Java.
- Cách phát hiện và đăng ký module.
- Naming strategy và các thiết lập liên quan.
- Các tích hợp với Spring MVC message converters.
- Các customizer khác do ứng dụng hoặc thư viện cung cấp.

Nếu ứng dụng tự tạo một `ObjectMapper` mới:

~~~java
@Bean
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

bean do ứng dụng cung cấp có thể khiến auto-configuration mặc định của Boot nhường chỗ. Mapper mới có thể không còn nhận toàn bộ cấu hình mà Boot đã áp dụng cho builder mặc định, trừ khi ứng dụng tự cấu hình lại các phần cần thiết.

Nếu mục tiêu chỉ là bật pretty print, customizer thường phù hợp hơn:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder ->
            builder.featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            );
}
~~~

Customizer thay đổi một feature trên builder do Spring Boot sử dụng. Các module và cấu hình mặc định khác vẫn có cơ hội được áp dụng.

### Giữ mặc định không có nghĩa không thay đổi gì

Khi dùng customizer, ứng dụng vẫn thay đổi cấu hình. Điều quan trọng là **thay đổi có giới hạn**: chỉ sửa thuộc tính cần thiết, không thay thế toàn bộ object graph hoặc toàn bộ cơ chế auto-configuration.

Một quy tắc thực dụng:

> Nếu nhu cầu chỉ là điều chỉnh một vài thuộc tính, hãy tìm extension point hoặc builder customizer trước khi khai báo một bean thay thế hoàn chỉnh.

## 3. Customizer được Spring Boot tìm và áp dụng như thế nào?

Một customizer thường được đăng ký như bean:

~~~java
@Configuration
public class JsonConfiguration {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> {
            // Điều chỉnh builder tại đây.
        };
    }
}
~~~

Spring Boot có thể thu thập các bean có kiểu customizer tương ứng rồi áp dụng chúng khi cấu hình builder hoặc factory.

Luồng khái quát:

~~~text
ApplicationContext
       |
       +--> customizer A
       |
       +--> customizer B
       |
       +--> customizer C
                |
                v
      Spring Boot thu thập customizers
                |
                v
       Áp dụng theo contract / thứ tự
                |
                v
       Builder hoặc factory hoàn chỉnh
                |
                v
       Tạo thành phần runtime
~~~

Không phải mọi customizer trong hệ sinh thái đều được áp dụng theo cùng một cơ chế. Mỗi extension point có thể có cách thu thập, thứ tự và thời điểm gọi riêng. Vì vậy, khi sử dụng một interface cụ thể, cần hiểu contract của chính interface đó.

### Customizer thường được áp dụng lúc khởi động

Customizer của web server factory, Jackson builder hoặc HTTP client thường được áp dụng trong giai đoạn cấu hình ứng dụng. Nó không phải callback được gọi cho mỗi HTTP request.

Nếu cần thay đổi hành vi theo dữ liệu request, hãy dùng controller, interceptor, filter, strategy hoặc API runtime phù hợp. Không dùng customizer khởi động để lưu trạng thái riêng của từng người dùng.

## 4. Tùy biến web server mà giữ cấu hình mặc định

Spring Boot có thể tự cấu hình embedded web server dựa trên starter và cấu hình ứng dụng. Nếu chỉ cần đổi một thuộc tính của server factory, có thể dùng `WebServerFactoryCustomizer`.

Ví dụ:

~~~java
package com.example.store.config;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebServerConfiguration {

    @Bean
    public WebServerFactoryCustomizer<ConfigurableWebServerFactory>
            webServerCustomizer() {

        return factory -> factory.setPort(8081);
    }
}
~~~

Customizer trên chỉ thay đổi port. Các cấu hình khác do Spring Boot và server factory cung cấp vẫn có thể tiếp tục được áp dụng, chẳng hạn SSL, compression, error handling hoặc các thiết lập server khác nếu chúng được cấu hình ở nơi phù hợp.

Trong một ứng dụng đơn giản, nếu chỉ cần đổi port, cấu hình property thường rõ ràng hơn:

~~~yaml
server:
  port: 8081
~~~

Dùng customizer khi cần gọi API của factory để tùy biến một chi tiết chưa có property phù hợp, hoặc cần thực hiện cấu hình bằng Java.

### Tùy biến Tomcat-specific

Nếu ứng dụng dùng embedded Tomcat và cần thay đổi một thuộc tính connector, có thể dùng kiểu factory cụ thể:

~~~java
@Bean
public WebServerFactoryCustomizer<TomcatServletWebServerFactory>
        tomcatCustomizer() {

    return factory -> factory.addConnectorCustomizers(connector -> {
        connector.setMaxParameterCount(1000);
    });
}
~~~

Ví dụ này phụ thuộc Tomcat và API của phiên bản tương ứng. Nếu ứng dụng chuyển sang Jetty hoặc Undertow, customizer Tomcat-specific không còn phù hợp. Với cấu hình có thể dùng trên nhiều server, ưu tiên interface tổng quát `ConfigurableWebServerFactory`.

### Đừng tự thay WebServerFactory nếu chỉ cần chỉnh một thuộc tính

Một bean factory tự tạo có thể khiến Boot auto-configuration nhường chỗ, tùy loại bean và điều kiện cấu hình. Khi đó ứng dụng phải chịu trách nhiệm cho nhiều thiết lập mà trước đây Boot cung cấp.

Hãy tự hỏi:

- Có property chuẩn nào giải quyết được nhu cầu không?
- Có `WebServerFactoryCustomizer` tương ứng không?
- Có thể chỉnh đúng thuộc tính trên factory hiện có không?
- Có thật sự cần thay embedded server hoặc factory không?

## 5. Tùy biến Jackson mà giữ cấu hình JSON của Spring Boot

Spring Boot sử dụng Jackson trong nhiều ứng dụng để chuyển đổi JSON. Thay vì tự khai báo `ObjectMapper` mới cho một thay đổi nhỏ, có thể dùng `Jackson2ObjectMapperBuilderCustomizer`.

Ví dụ bật pretty print:

~~~java
package com.example.store.config;

import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonConfiguration {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder
                .featuresToEnable(
                        SerializationFeature.INDENT_OUTPUT
                );
    }
}
~~~

Customizer này yêu cầu builder bật feature `SerializationFeature.INDENT_OUTPUT`. Các cấu hình khác mà Spring Boot đã chuẩn bị cho Jackson vẫn có cơ hội được áp dụng trong quá trình builder được cấu hình, trừ khi có customizer hoặc cấu hình khác thay đổi chúng.

Có thể điều chỉnh thêm một feature:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
    return builder -> builder
            .featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            )
            .featuresToDisable(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            );
}
~~~

Để dùng đoạn này, cần import `DeserializationFeature`. Ví dụ chỉ minh họa API; lựa chọn bỏ qua field JSON không biết có ảnh hưởng tới validation hợp đồng API và khả năng phát hiện client gửi sai dữ liệu. Không nên bật/tắt feature chỉ vì muốn request “dễ chạy hơn”; hãy căn cứ yêu cầu API.

### Customizer có thể bổ sung module

Jackson builder cũng hỗ trợ đăng ký module hoặc cấu hình naming/serialization theo API tương ứng. Khi cần module tùy chỉnh, có thể đưa module vào builder hoặc đăng ký bean `Module` theo cơ chế mà Boot hỗ trợ.

Điểm quan trọng là nên tận dụng builder do Boot quản lý. Nếu tự tạo mapper mới, cần xác minh các module, naming strategy, date/time handling và message converter integration đã được cấu hình lại đầy đủ.

### Khi nào nên tạo ObjectMapper riêng?

Có những trường hợp cần một mapper chuyên biệt, ví dụ:

- Một định dạng file nội bộ khác với JSON API.
- Một giao thức bên thứ ba có quy tắc serialization riêng.
- Một tác vụ export cần naming strategy khác.
- Một mapper chỉ dùng trong một module và không thay thế mapper HTTP toàn ứng dụng.

Khi đó, có thể tạo bean có qualifier hoặc dùng builder riêng với tên rõ ràng. Đừng vô tình thay mapper mặc định toàn ứng dụng khi nhu cầu chỉ giới hạn ở một use case.

## 6. Tùy biến MVC mà vẫn giữ Spring Boot MVC defaults

Spring MVC có interface `WebMvcConfigurer` để ứng dụng bổ sung một số cấu hình MVC. Dù tên interface không có chữ “Customizer”, nó cung cấp các callback cấu hình tương tự.

Ví dụ thêm interceptor:

~~~java
package com.example.store.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfiguration implements WebMvcConfigurer {

    private final RequestAuditInterceptor auditInterceptor;

    public MvcConfiguration(RequestAuditInterceptor auditInterceptor) {
        this.auditInterceptor = auditInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(auditInterceptor)
                .addPathPatterns("/api/**");
    }
}
~~~

Trong Spring Boot MVC, việc cung cấp một `WebMvcConfigurer` thường cho phép bổ sung callback mà vẫn giữ cơ chế auto-configuration MVC. Đây là cách phù hợp khi chỉ muốn thêm interceptor, formatter, CORS mapping hoặc một số tùy chỉnh MVC khác.

### Vì sao @EnableWebMvc có thể làm mất mặc định?

Nếu thêm `@EnableWebMvc`, ứng dụng chuyển sang chủ động cấu hình Spring MVC và có thể khiến `WebMvcAutoConfiguration` của Spring Boot back off do điều kiện không còn thỏa. Khi đó, ứng dụng có thể phải tự cấu hình các phần mà Boot trước đó cung cấp.

Nếu chỉ cần thêm một interceptor hoặc converter, thường không cần `@EnableWebMvc`. Dùng `WebMvcConfigurer` để bổ sung cấu hình thường giữ được nhiều mặc định hơn.

Điều này không có nghĩa `@EnableWebMvc` luôn sai. Nó phù hợp khi ứng dụng thực sự muốn tự kiểm soát cấu hình MVC. Nhưng đó là quyết định thay đổi phạm vi trách nhiệm cấu hình, không phải cách đơn giản để thêm một callback.

### Chỉ bổ sung converter khi thật sự cần

`WebMvcConfigurer` có các callback như `extendMessageConverters` và `configureMessageConverters`. Hai phương thức có ý nghĩa khác nhau:

- `extendMessageConverters` cho phép chỉnh hoặc bổ sung converter sau khi danh sách mặc định đã được thiết lập.
- `configureMessageConverters` có thể tham gia cấu hình danh sách converter theo cách ảnh hưởng tới mặc định.

Nếu mục tiêu là **giữ converter mặc định và thêm một converter**, thường nên cân nhắc `extendMessageConverters`. Hãy kiểm tra contract của phiên bản Spring Framework đang dùng và thứ tự converter, vì converter đứng trước có thể nhận xử lý trước converter khác.

## 7. Tùy biến RestTemplate qua builder và customizer

Spring Boot cung cấp `RestTemplateBuilder` để tạo `RestTemplate` với cấu hình phù hợp. Thay vì tự gọi `new RestTemplate()`, nên inject builder:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    public RestTemplate partnerRestTemplate(
            RestTemplateBuilder builder
    ) {
        return builder.build();
    }
}
~~~

Builder do Boot cung cấp có thể đã tích hợp message converters, request factory, customizers và cấu hình liên quan. Dùng builder giúp ứng dụng kế thừa những thiết lập đó.

Một customizer có thể điều chỉnh các instance được tạo từ builder:

~~~java
@Bean
public RestTemplateCustomizer partnerRestTemplateCustomizer() {
    return restTemplate -> {
        // Thêm interceptor hoặc error handler cần thiết.
    };
}
~~~

`RestTemplateCustomizer` là extension point của Spring Boot dành cho việc tùy biến `RestTemplate`. Những customizer được Boot áp dụng cho builder/instance theo cơ chế tương ứng của phiên bản.

Nếu tạo `RestTemplate` bằng `new RestTemplate()`, ứng dụng có thể bỏ qua các cấu hình từ builder mà Boot đã chuẩn bị. Khi cần một client đặc biệt, hãy bắt đầu từ builder và điều chỉnh thêm:

~~~java
@Bean
public RestTemplate partnerRestTemplate(
        RestTemplateBuilder builder
) {
    return builder
            .additionalCustomizers(
                    restTemplate -> {
                        // Tùy biến riêng cho partner client.
                    }
            )
            .build();
}
~~~

API builder có thể thay đổi nhẹ giữa các phiên bản Spring Boot. Hãy dùng phương thức có trong phiên bản dự án đang chạy.

### Một client hay nhiều client?

Nếu ứng dụng có nhiều đối tác với timeout, authentication hoặc error handling khác nhau, có thể tạo nhiều bean `RestTemplate` với tên/qualifier rõ ràng, mỗi bean được build từ `RestTemplateBuilder`. Không cần thay thế builder toàn cục chỉ vì một đối tác có yêu cầu riêng.

## 8. WebClient và các builder reactive

Với ứng dụng reactive, Spring Boot có thể cung cấp `WebClient.Builder` đã được cấu hình. Nên inject builder thay vì tự tạo builder độc lập nếu muốn giữ các thiết lập chung như codec, observation hoặc connector mà Boot cung cấp.

Ví dụ:

~~~java
@Configuration
public class ReactiveClientConfiguration {

    @Bean
    public WebClient catalogWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example")
                .build();
    }
}
~~~

Nếu nhiều bean cùng inject một builder mutable và tự thay đổi builder đó, cần hiểu builder có được chia sẻ hay clone theo cơ chế cấu hình của phiên bản Spring Boot. Trong các phiên bản hỗ trợ builder prototype hoặc clone, hãy dùng cách được tài liệu của phiên bản chỉ định để tránh thay đổi cấu hình dùng chung ngoài ý muốn.

Một customizer chuyên biệt như `WebClientCustomizer` có thể được sử dụng khi cần điều chỉnh cấu hình chung cho các WebClient builder mà Boot quản lý. Với cấu hình riêng cho một client, có thể tùy biến builder ngay tại factory method của client đó.

### Đừng tự tạo WebClient khi đã có builder cấu hình sẵn

~~~java
WebClient client = WebClient.create();
~~~

Cách này hợp lệ trong Spring WebFlux thuần, nhưng có thể không sử dụng các cấu hình được Spring Boot đưa vào `WebClient.Builder`. Nếu ứng dụng cần giữ các mặc định/quan sát/codec của Boot, hãy dùng builder được inject.

## 9. Tùy biến theo property trước, dùng code khi cần

Spring Boot cung cấp nhiều property chuẩn cho các nhu cầu phổ biến:

~~~yaml
server:
  port: 8081
  compression:
    enabled: true

spring:
  jackson:
    serialization:
      indent-output: true
~~~

Nếu một property đã biểu đạt chính xác nhu cầu, nên ưu tiên cấu hình đó vì:

- Dễ thay đổi giữa môi trường mà không sửa code.
- Dễ nhìn thấy trong file cấu hình.
- Có thể được kiểm tra và quản lý qua profile hoặc config source.
- Ít phụ thuộc vào API cụ thể của implementation.

Customizer phù hợp khi property không đủ biểu đạt hoặc cần gọi API của đối tượng mục tiêu. Ví dụ, một thiết lập connector đặc thù của Tomcat có thể cần customizer Java.

### Chọn đúng công cụ

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Đổi port web server | `server.port` |
| Bật compression | `server.compression.enabled` |
| Bật pretty print JSON | `spring.jackson.serialization.indent-output` hoặc Jackson customizer |
| Thêm interceptor MVC | `WebMvcConfigurer` |
| Chỉnh một thuộc tính web server không có property phù hợp | `WebServerFactoryCustomizer` |
| Điều chỉnh các RestTemplate được tạo từ Boot builder | `RestTemplateCustomizer` |
| Tạo một RestTemplate riêng theo đối tác | Inject `RestTemplateBuilder`, rồi build riêng |
| Điều chỉnh Jackson builder theo Java logic | `Jackson2ObjectMapperBuilderCustomizer` |

Một property chuẩn thường là lựa chọn dễ vận hành nhất. Customizer là bước tiếp theo khi cần tùy biến có kiểm soát bằng API.

## 10. Nhiều customizer cùng áp dụng: thứ tự có ý nghĩa

Một ứng dụng có thể có nhiều customizer cùng tác động lên một target. Ví dụ:

- Customizer A bật compression.
- Customizer B thay đổi port.
- Customizer C cấu hình connector.
- Customizer D điều chỉnh giới hạn header.

Nếu mỗi customizer chỉnh một thuộc tính riêng, chúng thường có thể cùng tồn tại. Nhưng nếu hai customizer cùng gọi setter trên một thuộc tính, kết quả phụ thuộc thứ tự áp dụng.

Ví dụ:

~~~java
@Bean
@Order(10)
WebServerFactoryCustomizer<ConfigurableWebServerFactory> firstCustomizer() {
    return factory -> factory.setPort(8081);
}

@Bean
@Order(20)
WebServerFactoryCustomizer<ConfigurableWebServerFactory> secondCustomizer() {
    return factory -> factory.setPort(9090);
}
~~~

Trong extension point có hỗ trợ ordering, customizer được sắp xếp theo order tương ứng. Với ví dụ minh họa này, customizer có order 20 chạy sau và có thể ghi đè port thành 9090.

Không nên dựa vào thứ tự ngẫu nhiên của bean discovery. Nếu nhiều customizer có thể ghi đè cùng một thuộc tính, hãy:

1. Tập trung quyền sở hữu thuộc tính vào một customizer.
2. Dùng `Ordered` hoặc `@Order` nếu extension point hỗ trợ.
3. Tránh để nhiều cấu hình môi trường cùng sửa một giá trị.
4. Kiểm tra kết quả cuối cùng trong context hoặc log khởi động.

### Không phải mọi customizer đều có cùng quy tắc ordering

Một số extension point của Boot thu thập customizer bằng ordered stream hoặc comparator; một số API khác có contract riêng. Không thể suy ra mọi interface có tên *Customizer* đều tự động tôn trọng `@Order`. Hãy xem API cụ thể và cách framework áp dụng collection đó.

### @Order khác với dependency order

`@Order` thường sắp xếp thành phần trong một collection hoặc callback chain. Nó không tạo bean dependency, không đảm bảo bean khác được khởi tạo trước, và không thay thế `@DependsOn`.

Nếu customizer cần một bean khác, khai báo dependency qua constructor hoặc factory method. Đừng dựa vào thứ tự customizer để bảo đảm một bean instance đã được tạo.

## 11. Tùy biến cộng dồn và tùy biến thay thế

Không phải mọi API đều áp dụng thay đổi theo cùng cách.

**Tùy biến cộng dồn**: thêm một interceptor, converter, connector customizer hoặc module vào danh sách hiện có. Kết quả có thể bao gồm cả thành phần mặc định và thành phần mới.

**Tùy biến thay thế**: gọi setter để thay một giá trị đã có, ví dụ thay port, timeout hoặc naming strategy. Giá trị mới có thể ghi đè giá trị trước.

Ví dụ:

~~~java
factory.addConnectorCustomizers(connector -> {
    // Bổ sung một hành động cấu hình connector.
});
~~~

thường mang ý nghĩa bổ sung callback vào danh sách customizer.

Trong khi:

~~~java
factory.setPort(8081);
~~~

thay đổi một giá trị đơn. Nếu một customizer khác gọi `setPort(9090)` sau đó, giá trị cuối có thể là 9090.

Với builder, các phương thức như `additionalInterceptors` thường mang ý nghĩa bổ sung; các phương thức như `baseUrl` hoặc `connectTimeout` thường thiết lập giá trị. Tên API có thể khác giữa phiên bản, nên hãy đọc contract thay vì giả định mọi method đều additive.

## 12. Cách giữ các mặc định còn lại

Đây là phần quan trọng nhất khi viết customizer. Một thay đổi nhỏ có thể vô tình làm mất cấu hình lớn nếu ta tạo một bean thay thế toàn bộ.

### Nguyên tắc 1: dùng builder/factory được inject

Ví dụ:

~~~java
@Bean
public RestTemplate partnerTemplate(RestTemplateBuilder builder) {
    return builder
            .build();
}
~~~

Builder do Boot cung cấp có thể đã chứa các cấu hình chung. Dùng builder đó giữ lại các thiết lập được framework tích hợp.

### Nguyên tắc 2: chỉ sửa thuộc tính cần thiết

~~~java
@Bean
public WebServerFactoryCustomizer<ConfigurableWebServerFactory>
        serverCustomizer() {
    return factory -> factory.setPort(8081);
}
~~~

Không cần tự tạo factory mới nếu chỉ muốn đổi port.

### Nguyên tắc 3: ưu tiên extension point bổ sung

Với MVC, implement `WebMvcConfigurer` và override đúng callback cần thiết. Tránh bật `@EnableWebMvc` nếu mục tiêu là bổ sung một interceptor nhưng vẫn muốn Boot giữ auto-configuration.

Với Jackson, dùng builder customizer thay vì thay toàn bộ `ObjectMapper` nếu chỉ cần một feature.

### Nguyên tắc 4: không thay thế bean mặc định một cách vô ý

Nhiều auto-configuration của Spring Boot sử dụng điều kiện như `@ConditionalOnMissingBean`. Khi ứng dụng tự khai báo bean cùng kiểu, cấu hình mặc định có thể back off. Điều này hữu ích khi muốn thay hoàn toàn implementation, nhưng nguy hiểm nếu chỉ muốn chỉnh một thuộc tính.

Trước khi tạo bean thay thế, hãy tìm xem Boot có customizer, builder, configurer hoặc property tương ứng không.

### Nguyên tắc 5: giữ cấu hình riêng ở đúng phạm vi

Một customizer global có thể ảnh hưởng tất cả client hoặc server factory thuộc extension point đó. Nếu chỉ một integration cần timeout riêng, hãy tạo client riêng từ builder thay vì thay đổi customizer toàn cục.

### Nguyên tắc 6: không ghi đè cấu hình môi trường một cách bất ngờ

Nếu customizer luôn gọi `setPort(8081)`, nó có thể ghi đè giá trị `server.port` theo môi trường tùy thứ tự áp dụng. Nếu muốn property là nguồn cấu hình chính, đừng thêm setter cố định trong customizer. Nếu cần Java logic có điều kiện, hãy đọc `Environment` hoặc cấu hình typed properties một cách rõ ràng.

## 13. Ví dụ: customizer chỉ bổ sung một header mặc định cho RestTemplate

Giả sử ứng dụng gọi API đối tác và muốn thêm một header nhận diện ứng dụng. Có thể dùng `RestTemplateCustomizer`:

~~~java
@Configuration
public class PartnerHttpConfiguration {

    @Bean
    public RestTemplateCustomizer applicationHeaderCustomizer() {
        return restTemplate -> {
            restTemplate.getInterceptors().add(
                    new ApplicationHeaderInterceptor("store-service")
            );
        };
    }

    @Bean
    public RestTemplate partnerRestTemplate(
            RestTemplateBuilder builder
    ) {
        return builder.build();
    }
}
~~~

`ApplicationHeaderInterceptor` là class do ứng dụng định nghĩa, triển khai `ClientHttpRequestInterceptor` và thêm header vào request. Ví dụ này minh họa việc bổ sung interceptor mà không tự tạo một RestTemplate độc lập.

Nếu header chỉ áp dụng cho đối tác A, không nên đăng ký customizer toàn cục áp dụng mọi RestTemplate. Thay vào đó, có thể gắn interceptor cho builder của riêng client đó:

~~~java
@Bean
public RestTemplate partnerARestTemplate(
        RestTemplateBuilder builder
) {
    return builder
            .additionalInterceptors(
                    new ApplicationHeaderInterceptor("store-service")
            )
            .build();
}
~~~

Như vậy, cấu hình chung từ Boot builder vẫn được sử dụng, còn thay đổi riêng chỉ ảnh hưởng client A.

## 14. Ví dụ: thêm interceptor MVC mà giữ mặc định

Giả sử ứng dụng muốn ghi nhận audit cho các API dưới `/api/**`. Ta có thể tạo interceptor và đăng ký qua `WebMvcConfigurer`:

~~~java
@Component
public class RequestAuditInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) {
        // Ghi nhận metadata phù hợp của request.
        return true;
    }
}
~~~

~~~java
@Configuration
public class AuditMvcConfiguration implements WebMvcConfigurer {

    private final RequestAuditInterceptor interceptor;

    public AuditMvcConfiguration(RequestAuditInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}
~~~

Cấu hình này bổ sung interceptor vào MVC. Không cần tự khai báo lại handler mapping, message converter, exception resolver hoặc toàn bộ MVC infrastructure.

Trong ứng dụng thật, interceptor không nên ghi log toàn bộ body hoặc dữ liệu nhạy cảm một cách tùy tiện. Nếu cần đọc/ghi request body, cần cân nhắc buffering, giới hạn kích thước và filter phù hợp.

## 15. Ví dụ: tùy biến Jackson nhưng không làm mất module Java Time

Một ứng dụng dùng Jackson để serialize kiểu `LocalDateTime`. Spring Boot có thể cấu hình module Java Time trong mapper mặc định.

Nếu tự tạo:

~~~java
@Bean
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

mapper này có thể không nhận được module/cấu hình mà Boot đã chuẩn bị, dẫn đến hành vi ngày giờ khác dự kiến.

Thay vào đó, nếu chỉ muốn định dạng output dễ đọc:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder
            .featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            );
}
~~~

Hãy để Boot tiếp tục tạo mapper từ builder đã được cấu hình. Nếu thực sự cần một mapper độc lập, hãy đăng ký nó với tên/qualifier riêng và chủ động thêm module, naming strategy, date/time format cùng các cấu hình cần thiết.

Không nên cho rằng mọi mapper trong ứng dụng đều dùng cùng cấu hình chỉ vì có một customizer. Một module có thể tự tạo mapper bằng `new ObjectMapper()` và không sử dụng builder của Boot.

## 16. Khi customizer không được áp dụng như mong đợi

Một số nguyên nhân thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Customizer không chạy | Bean không được đăng ký hoặc package ngoài component scan | Kiểm tra component scan, `@Bean` configuration và điều kiện |
| Customizer chạy nhưng không thấy tác dụng | Đang tùy biến builder/factory không được bean thực tế sử dụng | Kiểm tra nơi tạo đối tượng |
| Giá trị bị thay đổi lại | Customizer khác chạy sau và ghi đè | Kiểm tra thứ tự, `@Order` và setter trùng |
| Mặc định Boot biến mất | Ứng dụng đã cung cấp bean thay thế làm auto-configuration back off | Kiểm tra `@ConditionalOnMissingBean` và condition report |
| Chỉ một client được tùy biến nhưng các client khác cũng thay đổi | Customizer global tác động mọi instance trong extension point | Chuyển sang builder/client riêng |
| Property không có hiệu lực | Customizer code ghi đè property hoặc thứ tự áp dụng khác dự kiến | Kiểm tra cấu hình cuối cùng và customizer order |
| MVC defaults biến mất | Đã bật `@EnableWebMvc` hoặc thay cấu hình MVC toàn phần | Dùng `WebMvcConfigurer` nếu chỉ cần bổ sung |
| Jackson behavior khác giữa API và file export | Hai ObjectMapper được tạo từ các nguồn khác nhau | Kiểm tra bean nào được inject và mapper nào được dùng |

### Kiểm tra customizer có thực sự là bean

Nếu dùng:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder.featuresToEnable(
            SerializationFeature.INDENT_OUTPUT
    );
}
~~~

thì lớp cấu hình chứa phương thức `@Bean` phải được Spring xử lý. Nếu package nằm ngoài vùng component scan và không được import, bean customizer không được đăng ký.

### Kiểm tra bean thực tế có dùng builder/factory đó không

Có thể ứng dụng có hai `ObjectMapper` hoặc hai `RestTemplate`. Customizer chỉ tác động vào đường tạo đối tượng mà extension point của nó quản lý. Một client được tạo thủ công bằng `new RestTemplate()` không nhất thiết nhận customizer của Boot builder.

### Kiểm tra thứ tự và giá trị cuối

Nếu nhiều customizer cùng thay đổi một thuộc tính, hãy xem thứ tự áp dụng. Đừng chỉ kiểm tra một customizer có được gọi hay không; cần kiểm tra giá trị cuối cùng sau toàn bộ chuỗi cấu hình.

## 17. Customizer và @ConditionalOnMissingBean

Spring Boot thường cung cấp cấu hình mặc định theo kiểu “nếu ứng dụng chưa có bean phù hợp thì tạo bean này”. Ví dụ khái niệm:

~~~java
@Bean
@ConditionalOnMissingBean(ReportFormatter.class)
public ReportFormatter reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

Nếu ứng dụng tự khai báo `ReportFormatter`, bean mặc định có thể không được đăng ký. Đây là cơ chế override toàn bộ bean, không phải customizer.

Nếu nhu cầu chỉ là thay đổi một thuộc tính của formatter, một extension point customizer có thể tốt hơn. Nếu cần thay hẳn thuật toán, implementation hoặc contract, khai báo bean riêng là phù hợp.

| Nhu cầu | Nên cân nhắc |
|---|---|
| Thay một vài option của object Boot quản lý | Customizer |
| Bổ sung một interceptor hoặc callback | Extension point additive |
| Thay toàn bộ implementation | Bean thay thế / cấu hình riêng |
| Tạo một instance riêng cho một use case | Factory method từ builder |
| Tắt một auto-configuration không cần thiết | Cấu hình exclude hoặc condition |
| Tạo nhiều instance theo dữ liệu runtime | Factory/registry nghiệp vụ |

### Customizer cũng có thể được đăng ký có điều kiện

Nếu customizer chỉ phù hợp với một môi trường, có thể dùng `@Profile` hoặc `@ConditionalOnProperty`:

~~~java
@Bean
@Profile("dev")
public Jackson2ObjectMapperBuilderCustomizer developmentJsonCustomizer() {
    return builder -> builder.featuresToEnable(
            SerializationFeature.INDENT_OUTPUT
    );
}
~~~

Khi profile dev không active, customizer không được đăng ký. Tuy nhiên, hãy đảm bảo cấu hình đó thực sự chỉ nên áp dụng ở dev; không dùng profile để che một cấu hình production bắt buộc.

## 18. Customizer nên nhỏ, tập trung và có thể kiểm thử

Một customizer tốt thường có một trách nhiệm rõ. Ví dụ:

- Một customizer chỉ cấu hình compression cho server.
- Một customizer chỉ thêm module hoặc feature cho Jackson.
- Một customizer chỉ thêm interceptor cho HTTP client.
- Một customizer chỉ điều chỉnh connector property cụ thể.

Không nên tạo một customizer khổng lồ thay đổi nhiều hệ thống không liên quan. Cũng không nên chia thành nhiều customizer nhỏ đến mức cùng ghi đè một thuộc tính và khó hiểu thứ tự.

### Tránh side effect trong customize

Không nên thực hiện network call, query database hoặc khởi động tác vụ nghiệp vụ trong callback customizer. Callback thường chạy trong giai đoạn khởi động hoặc build đối tượng; side effect có thể làm startup chậm và khó lặp lại.

Customizer nên chủ yếu điều chỉnh metadata/option của target. Việc mở connection thật nên do lifecycle của client/server hoặc bean sở hữu resource đảm nhiệm.

### Kiểm thử bằng cách quan sát target đã được cấu hình

Với customizer của ứng dụng, có thể kiểm thử trực tiếp hành động lên một builder/factory hoặc khởi tạo context nhỏ để xác nhận bean customizer được áp dụng.

Ví dụ kiểm thử một customizer giả định:

~~~java
@Test
void appliesOnlyRequestedSetting() {
    TestServerFactory factory = new TestServerFactory();

    WebServerFactoryCustomizer<TestServerFactory> customizer =
            target -> target.setPort(8081);

    customizer.customize(factory);

    assertEquals(8081, factory.getPort());
    assertEquals(true, factory.isCompressionEnabled());
}
~~~

`TestServerFactory` ở đây là đối tượng giả định cho bài test, không phải class Spring Boot. Mục tiêu là kiểm tra customizer chỉ thay đổi port và không làm mất giá trị compression đã có. Với extension point thật, có thể dùng factory/builder tương ứng hoặc Spring context test để xác nhận framework áp dụng bean.

## 19. Cách quyết định giữa property, customizer và bean thay thế

Có thể dùng chuỗi quyết định sau:

~~~text
Nhu cầu chỉ thay một giá trị cấu hình phổ biến?
              |
          Có  |  Không
          |        |
          v        v
       Property   Có extension point / builder
       chuẩn?     customizer phù hợp?
                    |
                Có  |  Không
                |        |
                v        v
           Customizer   Có thật sự cần thay
           có chọn lọc? toàn bộ bean không?
                           |
                       Có  |  Không
                       |       |
                       v       v
                 Bean thay thế  Xem lại API/
                 có chủ đích   cấu hình hiện có
~~~

Ví dụ:

- Đổi port: property.
- Bật pretty print: property hoặc Jackson customizer.
- Thêm interceptor MVC: `WebMvcConfigurer`.
- Tùy biến connector Tomcat: customizer chuyên biệt.
- Thay thuật toán thanh toán: bean implementation riêng.
- Tạo HTTP client riêng cho một đối tác: builder được Boot cung cấp, rồi build riêng.

## 20. Checklist giữ mặc định khi tùy biến

Trước khi viết cấu hình, hãy tự kiểm tra:

1. **Mặc định nào đang được Spring Boot cung cấp?** Xác định bean/builder/factory cụ thể.
2. **Chỉ cần thay đổi thuộc tính nào?** Tránh thay cả bean nếu chỉ cần một setter.
3. **Có property chuẩn không?** Nếu có, ưu tiên property cho cấu hình vận hành thông thường.
4. **Có customizer/configurer extension point không?** Tìm API đúng cho thành phần đang dùng.
5. **Customizer tác động global hay local?** Nếu chỉ một client cần thay đổi, đừng đăng ký customizer toàn cục.
6. **Nhiều customizer có thể ghi đè nhau không?** Xác định thứ tự và quyền sở hữu từng thuộc tính.
7. **Có vô tình làm auto-configuration back off không?** Kiểm tra `@ConditionalOnMissingBean` và bean type.
8. **Có cần giữ builder do Boot cung cấp không?** Tránh tạo đối tượng bằng constructor mặc định khi Boot đã cấu hình builder.
9. **Có đang thay thế MVC/WebFlux toàn phần không?** Tránh bật annotation enable nếu chỉ muốn bổ sung callback.
10. **Có thể kiểm thử kết quả cuối không?** Kiểm tra target sau khi mọi customizer đã chạy.

## Kết luận

Customizer là cách mở rộng cấu hình theo hướng **thay đổi đúng phần cần thiết trên builder hoặc factory mà framework đã chuẩn bị**. Spring Boot có nhiều extension point như `WebServerFactoryCustomizer`, `Jackson2ObjectMapperBuilderCustomizer`, `RestTemplateCustomizer` và callback cấu hình MVC. Chúng cho phép ứng dụng bổ sung hoặc chỉnh một số thiết lập mà vẫn tận dụng phần lớn mặc định của Boot.

Để giữ các mặc định còn lại, hãy ưu tiên property chuẩn, inject builder/factory do Boot cung cấp, dùng customizer nhỏ và tránh tự khai báo bean thay thế khi không cần. Khi có nhiều customizer, kiểm soát thứ tự và những thuộc tính bị ghi đè. Chỉ thay toàn bộ bean hoặc bật cấu hình framework thủ công khi thật sự muốn nhận trách nhiệm cấu hình lớn hơn.
