# Truyền trace qua RestTemplateBuilder, RestClient.Builder và WebClient.Builder

## 1. Vì sao HTTP thành công nhưng trace vẫn bị đứt?

Giả sử dịch vụ `checkout` gọi dịch vụ `inventory` để kiểm tra tồn kho. Phản hồi HTTP trả về đúng dữ liệu, nhưng trên hệ thống truy vết lại có hai trace riêng: một của checkout, một của inventory.

Nguyên nhân có thể là **ngữ cảnh truy vết chưa được truyền qua lời gọi HTTP**. Truyền ngữ cảnh nghĩa là lấy thông tin của trace hiện tại, ghi vào header yêu cầu đi ra, rồi để dịch vụ nhận đọc thông tin đó và nối phần xử lý của nó vào cùng trace.

Luồng mong muốn:

~~~text
checkout: nhận yêu cầu
└── checkout: gọi HTTP sang inventory
    └── inventory: xử lý yêu cầu nhận được
~~~

Trong ứng dụng Spring Boot 3.3 dùng Micrometer Tracing, cách thông thường là tạo HTTP client từ **builder do Spring Boot tự cấu hình**:

- `RestTemplateBuilder` cho `RestTemplate`.
- `RestClient.Builder` cho `RestClient`.
- `WebClient.Builder` cho `WebClient`.

Spring Boot hướng dẫn sử dụng những builder này để có tích hợp truyền trace qua mạng. Nếu tự tạo client và bỏ qua cấu hình tương ứng, việc truyền tự động không được thiết lập theo đường tích hợp này. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.propagating-traces).

HTTP client thực hiện được yêu cầu và HTTP client được nối vào cơ chế truy vết là hai điều cần kiểm tra riêng.

## 2. Cơ chế từ observation đến header HTTP

### 2.1. Vai trò của builder

Builder do Boot cung cấp đã nhận các bộ tùy biến cần thiết. Khi tạo client, các bộ tùy biến quan sát nối client với `ObservationRegistry` của ứng dụng và quy ước quan sát HTTP tương ứng.

Các bộ tùy biến của Actuator gồm:

| Client | Bộ tùy biến quan sát |
| --- | --- |
| RestTemplate | `ObservationRestTemplateCustomizer` |
| RestClient | `ObservationRestClientCustomizer` |
| WebClient | `ObservationWebClientCustomizer` |

Các API này cấu hình việc ghi nhận observation của client. [RestTemplate customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/client/ObservationRestTemplateCustomizer.html), [RestClient customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/client/ObservationRestClientCustomizer.html), [WebClient customizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/web/reactive/client/ObservationWebClientCustomizer.html).

Khi ứng dụng có cấu hình tracing phù hợp, bộ xử lý truy vết dùng ngữ cảnh client để tạo span và đưa thông tin truyền ngữ cảnh vào yêu cầu HTTP.

~~~text
Builder được Boot cấu hình
        |
        v
HTTP client dùng ObservationRegistry của ứng dụng
        |
        v
Lời gọi HTTP tạo observation phía client
        |
        v
Bộ xử lý tracing tạo span và ghi header ngữ cảnh
        |
        v
Dịch vụ nhận đọc header, tạo span phía server
~~~

Builder không phải bộ tự sinh và gửi trace độc lập. Registry, tracing bridge, các bộ xử lý và cấu hình phía nhận vẫn cần hoạt động.

### 2.2. Trace ID giữ nguyên; span ID thay đổi theo công việc

Một cấu trúc thường gặp:

~~~text
Trace T
├── server span S1 tại checkout
│   └── client span S2 tại checkout
│       └── server span S3 tại inventory
~~~

Ba span cùng trace ID `T` nhưng có span ID khác nhau.

Với W3C Trace Context, yêu cầu từ checkout sang inventory mang header dạng:

~~~http
traceparent: 00-11111111111111111111111111111111-2222222222222222-01
~~~

Đây là **giá trị minh họa cấu trúc**, không phải header cố định để đưa vào cấu hình:

- `1111...` là trace ID.
- `2222...` là mã span của bên đang gửi ngữ cảnh, ở sơ đồ là client span S2.
- Dịch vụ inventory tạo server span S3 mới; không dùng lại span ID của S2 làm span ID riêng.
- Cờ `01` có bit sampled được đặt; nó không phải xác nhận dữ liệu đã được lưu ở backend.

Định dạng header và quan hệ các trường được quy định bởi W3C Trace Context. [W3C Trace Context](https://www.w3.org/TR/trace-context/).

Không kỳ vọng span ID trong log của hai dịch vụ phải giống nhau. Điều cần đối chiếu là trace ID và quan hệ cha–con.

## 3. Điều kiện để việc truyền trace hoạt động

| Điều kiện | Ý nghĩa |
| --- | --- |
| Client nhận cấu hình quan sát | Lời gọi được nối vào registry phù hợp |
| Có tracing bridge và các bộ xử lý tương ứng | Observation có thể tham gia cơ chế tracing |
| Có ngữ cảnh cha đúng lúc thực thi | Lời gọi nối vào trace đang xử lý, thay vì trở thành một nhánh gốc khác |
| Định dạng phát/nhận tương thích | Header do bên gọi ghi được bên nhận hiểu |
| Dịch vụ nhận có tích hợp quan sát phía server | Yêu cầu nhận được tham gia trace |
| Đường xuất trace hoạt động | Có thể tìm được dữ liệu trên Collector/backend |

Nếu lời gọi xuất phát từ tác vụ không có trace cha, client vẫn có thể tạo trace mới theo cấu hình. Điều đó không tự là lỗi; cần đối chiếu với ranh giới xử lý mong muốn.

Nếu có observation HTTP nhưng thiếu bộ xử lý tracing, ứng dụng có thể ghi metric mà chưa có header truy vết. Ngược lại, có header đi ra chưa chứng minh dữ liệu đã được xuất tới backend.

### 3.1. Dependency và thư viện client

Các ví dụ tích hợp dưới đây giả định ứng dụng Spring Boot 3.3 hiện có:

- `RestTemplate` và `RestClient` cần Spring Web trên classpath.
- `WebClient` cần Spring WebFlux cùng HTTP client connector phù hợp.
- Actuator và một cấu hình tracing tương thích đã được cài đặt.
- Registry và builder tương ứng được Spring quản lý.

Trong Boot 3.3, tự cấu hình RestTemplate và RestClient có điều kiện không phải ứng dụng web reactive. Vì vậy, trong ứng dụng WebFlux, không mặc định rằng hai builder chặn đều hiện diện chỉ vì đã thêm Spring Web. Chọn nhánh client phù hợp và kiểm tra các bean có hiệu lực. [RestTemplateAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestTemplateAutoConfiguration.html), [RestClientAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html).

Ví dụ một bộ dependency tracing dùng OpenTelemetry và xuất tới Zipkin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

Đây là phần tracing bổ sung cho ứng dụng có sẵn; nó không tự cung cấp toàn bộ thư viện cho cả ba HTTP client. Với WebClient, có thể dùng starter WebFlux để nhận thư viện và connector; cần giữ lựa chọn kiến trúc server phù hợp với ứng dụng.

Cấu hình thử nghiệm tương ứng:

~~~properties
spring.application.name=checkout
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
~~~

Địa chỉ endpoint được hiểu từ nơi JVM chạy. Cấu hình này chỉ là một ví dụ về đường xuất; cơ chế truyền ngữ cảnh HTTP không yêu cầu mọi ứng dụng phải chọn Zipkin.

## 4. Tạo ba client từ builder được tiêm

### 4.1. Cấu hình client

Ví dụ `InventoryClients.java` dưới đây là **lớp tích hợp vào ứng dụng Boot**, không phải chương trình độc lập. Ví dụ dành cho ứng dụng Servlet có đủ thư viện và cả ba builder tương ứng. Khi chỉ dùng một loại client, chỉ giữ phần cấu hình cần thiết; không mặc định toàn bộ lớp này áp dụng nguyên dạng cho mọi ứng dụng WebFlux.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryClients {
    @Bean
    RestTemplate stockTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://inventory:8081").build();
    }

    @Bean
    RestClient stockRestClient(RestClient.Builder builder) {
        return builder.baseUrl("http://inventory:8081").build();
    }

    @Bean
    WebClient stockWebClient(WebClient.Builder builder) {
        return builder.baseUrl("http://inventory:8081").build();
    }
}
~~~

Các tham số builder do Spring tiêm vào phương thức `@Bean`. Việc thêm base URL vẫn đi tiếp từ builder đã được Boot cấu hình.

Địa chỉ `http://inventory:8081` là ví dụ tên dịch vụ trong mạng triển khai. Khi thử trên máy cá nhân, thay bằng địa chỉ mà JVM truy cập được. Trong ứng dụng thật, nên đưa địa chỉ dịch vụ đích vào cấu hình môi trường.

Spring Boot cung cấp builder cho WebClient và RestClient theo phạm vi prototype để mỗi điểm tiêm nhận một builder có thể tùy biến. [Spring Boot 3.3: Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html).

### 4.2. RestTemplate: thực thi đồng bộ qua client đã tạo

Ví dụ phương thức trong một thành phần đã được tiêm bean `stockTemplate`:

~~~java
String available = stockTemplate.getForObject(
        "/stock/{sku}", String.class, "SKU-1");
~~~

`rootUri` từ builder được dùng với đường dẫn tương đối bắt đầu bằng `/`. Giữ mẫu URI `/stock/{sku}` thay vì tự ghép mọi mã sản phẩm vào một chuỗi URL khi có thể dùng biến URI.

RestTemplate chặn luồng gọi cho đến khi hoàn tất thao tác. Nếu lời gọi chạy trong scope của yêu cầu HTTP hoặc observation nghiệp vụ hiện hành, cơ chế tracing có cơ hội liên kết client span với ngữ cảnh đó.

### 4.3. RestClient: chuỗi gọi đồng bộ

Với bean `stockRestClient`:

~~~java
String available = stockRestClient.get()
        .uri("/stock/{sku}", "SKU-1")
        .retrieve()
        .body(String.class);
~~~

Đây cũng là lời gọi chặn. Hãy hoàn tất cách đọc phản hồi phù hợp với API đang dùng; không bỏ dở một đối tượng phản hồi rồi coi thao tác đã được xử lý trọn vẹn.

Tên `RestClient.Builder` có thể gây nhầm với `RestClient.builder()`: kiểu tham số được Spring tiêm có thể mang cấu hình Boot, còn gọi phương thức static để tạo một builder mới không tự lấy các bộ tùy biến của ứng dụng.

### 4.4. WebClient: trả về Mono trong luồng reactive

Ví dụ phương thức trong thành phần đã được tiêm bean `stockWebClient`:

~~~java
import reactor.core.publisher.Mono;

public Mono<String> available(String sku) {
    return stockWebClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(String.class);
}
~~~

Đây là đoạn phương thức tích hợp, không phải một tệp Java chạy độc lập.

Trong WebFlux, trả về Mono để framework thực hiện subscription trong chuỗi xử lý yêu cầu. Chỉ xây dựng đối tượng Mono thường chưa thực hiện cuộc gọi mạng. Vì vậy thời điểm tạo chuỗi và thời điểm gửi HTTP có thể khác nhau.

Không tự gọi `subscribe()` trong service chỉ để “ép gửi trace” nếu phương thức có thể trả chuỗi về cho bên gọi. Subscription riêng có thể tách vòng đời, xử lý lỗi và ngữ cảnh khỏi yêu cầu đang xử lý.

Trong môi trường chặn, có thể có điểm gọi `block()` được thiết kế rõ ràng. Không đặt lời gọi chặn vào luồng xử lý non-blocking của WebFlux.

### 4.5. Tùy biến từ builder hiện có

`RestTemplateBuilder` có API theo kiểu trả về builder mới. Cần sử dụng kết quả của lời gọi tùy biến:

~~~java
RestTemplate client = builder
        .rootUri("http://inventory:8081")
        .build();
~~~

`RestClient.Builder` và `WebClient.Builder` là các builder có trạng thái. Nếu cần tạo nhiều biến thể từ một builder đã giữ lại, có thể clone builder để tách các thay đổi. Không dùng chung một builder đang bị sửa đồng thời giữa nhiều luồng.

Sau khi tạo client, tái sử dụng client theo thiết kế ứng dụng; không cần tạo builder/client mới cho từng yêu cầu chỉ để có trace ID mới.

## 5. Các cách làm mất cấu hình quan sát

Những biểu thức sau tự tạo client/builder bên ngoài cấu hình Boot:

~~~java
new RestTemplate();
RestClient.builder().build();
WebClient.builder().build();
WebClient.create();
~~~

Chúng không tự nhận các bộ tùy biến chỉ vì mã đang chạy bên trong một ứng dụng Spring Boot.

Có thể cấu hình thủ công registry và các thành phần liên quan khi xây dựng hạ tầng riêng. Tuy nhiên, đó là một công việc cấu hình có chủ đích, không phải hành vi tự có của các biểu thức trên.

### 5.1. Dùng annotation Bean không tự bổ sung mọi cấu hình

Ví dụ:

~~~java
@Bean
RestTemplate stockTemplate() {
    return new RestTemplate();
}
~~~

Việc đăng ký đối tượng làm bean không đồng nghĩa rằng nó đã được dựng qua RestTemplateBuilder của Boot. Hãy kiểm tra cách đối tượng được tạo.

Tương tự, tự khai báo một bean builder thay thế builder mặc định có thể làm mất các customizer nếu không áp dụng chúng. Khi chỉ cần thêm cấu hình chung, cân nhắc điểm mở rộng phù hợp như `RestTemplateCustomizer`, `RestClientCustomizer` hoặc `WebClientCustomizer` thay vì xây lại toàn bộ builder.

### 5.2. Không tự giữ một traceparent dùng chung

Không đặt một giá trị `traceparent` cố định vào `defaultHeader` của client dùng chung.

Header phải được tạo từ ngữ cảnh của từng lần thực thi. Một giá trị lưu từ yêu cầu trước có thể nối các giao dịch không liên quan vào cùng trace hoặc làm sai quan hệ span khi xử lý đồng thời.

Cũng không chỉ sao chép nguyên header traceparent nhận được vào mọi yêu cầu đi ra rồi coi đó là tương đương với tích hợp client. Khi có client span, phần mã span truyền đi cần phản ánh client span tương ứng.

### 5.3. Không bọc lại HTTP chỉ để tự truyền header

Nếu client đã được quan sát và tracing hoạt động, không cần thêm một interceptor tự sinh trace ID hoặc một observation cùng mục đích chỉ để ghi header.

Một observation nghiệp vụ có ranh giới riêng có thể hữu ích, nhưng nó phải bổ sung ý nghĩa. Cơ chế client vẫn phụ trách phần quan sát và truyền ngữ cảnh HTTP.

## 6. WebClient và ngữ cảnh khi đổi luồng

### 6.1. Thời điểm thực thi quan trọng hơn nơi viết mã

Ví dụ về một lỗi thiết kế:

~~~text
Mở một scope trong luồng A
    |
    v
Chỉ xây dựng Mono
    |
    v
Đóng scope
    |
    v
Mono được subscribe sau đó ở luồng B
~~~

Không thể suy ra rằng ngữ cảnh ThreadLocal của luồng A vẫn còn hiện hành khi HTTP được gửi ở luồng B.

Trong chuỗi reactive, Reactor Context gắn với subscription là cơ chế ngữ cảnh quan trọng. Khi cần chuyển đổi giữa ThreadLocal và Reactor Context, cần dùng cơ chế truyền ngữ cảnh phù hợp. [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/).

### 6.2. Cấu hình tự động khi cần tương tác ThreadLocal/Reactor

Spring Boot 3.3 có thuộc tính:

~~~properties
spring.reactor.context-propagation=auto
~~~

Nó bật cơ chế tự động khôi phục ngữ cảnh theo tích hợp Reactor tương ứng. Mặc định không phải mọi giá trị ThreadLocal đều tự được khôi phục trong reactive operator. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Đây không phải thuộc tính biến mọi executor, thread tự tạo hoặc subscription tách rời thành cùng một trace. Cần có các thành phần truyền ngữ cảnh tương ứng và đặt đúng ranh giới thực thi.

Reactor có cơ chế `contextCapture` để chụp các giá trị ThreadLocal đã đăng ký tại thời điểm subscription và đưa vào Reactor Context. Không hiểu nhầm nó là chụp ngữ cảnh tại thời điểm viết hoặc lắp ráp chuỗi. [Reactor: Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).

Đối với service trả về Mono cho WebFlux, ưu tiên giữ chuỗi xử lý liên tục và kiểm chứng quan hệ trace tại thời điểm subscription. Không sửa lỗi mất ngữ cảnh bằng cách đặt sẵn header của một trace cũ.

### 6.3. RestTemplate/RestClient cũng có thể mất ngữ cảnh khi đổi luồng

Hai client đồng bộ không tự giải quyết việc truyền ngữ cảnh của công việc bao ngoài khi mã bị đưa sang executor mới.

Nếu tạo một thread rồi gọi client ở đó, cần kiểm tra ngữ cảnh có được chuyển sang thread này hay không. Builder được cấu hình đúng vẫn có thể tạo một client span thuộc trace mới nếu ngữ cảnh cha mong muốn đã bị mất trước lúc gọi.

## 7. Kiểm tra định dạng truyền ngữ cảnh ở hai đầu

Builder đúng chưa đủ nếu định dạng header phía gọi và phía nhận không tương thích.

Ví dụ định hướng cho hệ thống nhận nhiều định dạng nhưng phát W3C:

~~~properties
management.tracing.propagation.consume=W3C,B3,B3_MULTI
management.tracing.propagation.produce=W3C
~~~

Cấu hình thực tế phải được thống nhất với các dịch vụ lân cận. Nếu dùng thuộc tính chung `management.tracing.propagation.type`, cần hiểu nó có thể ghi đè cấu hình chi tiết nhận/phát tương ứng.

Cùng một Collector hoặc backend không tự nối các trace có ngữ cảnh không được truyền đúng. Việc gửi span về backend và việc truyền header trên cuộc gọi nghiệp vụ là hai đường dữ liệu khác nhau.

Cũng cần tách việc lấy mẫu khỏi việc truyền ngữ cảnh. Trace không được chọn ghi nhận đầy đủ vẫn có thể có ngữ cảnh được truyền; việc không tìm thấy trace trên giao diện không tự chứng minh rằng HTTP không mang header.

## 8. Thí nghiệm chạy được: kiểm tra client nhận cấu hình quan sát

### 8.1. Phạm vi bằng chứng

Thí nghiệm dùng Spring Boot **3.3.0**, Spring Framework **6.1.8** và Micrometer Observation **1.13.0**. Mã đã được biên dịch bằng `javac --release 17` và chạy trên JDK 21.

Nó kiểm tra trực tiếp hai bộ tùy biến Actuator cho client chặn:

- RestTemplateBuilder sau khi nhận `ObservationRestTemplateCustomizer`.
- RestClient.Builder sau khi nhận `ObservationRestClientCustomizer`.
- RestTemplate tự tạo làm trường hợp đối chiếu.

Các yêu cầu được trả lời bằng MockRestServiceServer, không cần mở cổng mạng. Công cụ này hỗ trợ gắn vào cả RestTemplate và RestClient.Builder. [Javadoc MockRestServiceServer 6.1.8](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html).

**Thí nghiệm xác minh observation client bắt đầu và quan hệ observation cha. Nó không cài tracing bridge, không xác minh header traceparent, không kiểm thử WebClient và không gửi trace tới backend.** Phần cấu hình WebClient ở trên là ví dụ tích hợp theo API và tài liệu; kiểm chứng toàn tuyến cần thêm bước ở phần 9.

Ta cấu hình customizer trực tiếp để nhìn rõ tác dụng của nó. Trong ứng dụng Boot thông thường, dùng builder được tiêm như phần 4.

### 8.2. Dependency

Tạo `pom.xml` cho thí nghiệm độc lập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>builder-observation-probe</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

`spring-test` nằm ở classpath của chương trình vì chính hàm main dùng công cụ kiểm thử. Trong ứng dụng thông thường, thư viện kiểm thử được đặt ở phạm vi kiểm thử phù hợp.

### 8.3. Mã Java đầy đủ

Lưu `BuilderObservationProbe.java` cạnh `pom.xml`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.actuate.metrics.web.client.ObservationRestClientCustomizer;
import org.springframework.boot.actuate.metrics.web.client.ObservationRestTemplateCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.observation.ClientRequestObservationContext;
import org.springframework.http.client.observation.DefaultClientRequestObservationConvention;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;

import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

public class BuilderObservationProbe {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        Recorder recorder = new Recorder();
        registry.observationConfig().observationHandler(recorder);
        var convention = new DefaultClientRequestObservationConvention();

        RestTemplate template = new RestTemplateBuilder(
                new ObservationRestTemplateCustomizer(registry, convention)).build();
        MockRestServiceServer templateServer = MockRestServiceServer.bindTo(template).build();
        expectStock(templateServer);
        measure("RestTemplateBuilder", registry, recorder,
                () -> template.getForObject(
                        "http://inventory.test/stock/{sku}", String.class, "SKU-1"));
        templateServer.verify();

        RestClient.Builder builder = RestClient.builder();
        new ObservationRestClientCustomizer(registry, convention).customize(builder);
        MockRestServiceServer clientServer = MockRestServiceServer.bindTo(builder).build();
        RestClient client = builder.build();
        expectStock(clientServer);
        measure("RestClient.Builder", registry, recorder,
                () -> client.get().uri("http://inventory.test/stock/{sku}", "SKU-1")
                        .retrieve().body(String.class));
        clientServer.verify();

        RestTemplate raw = new RestTemplate();
        MockRestServiceServer rawServer = MockRestServiceServer.bindTo(raw).build();
        expectStock(rawServer);
        measure("new RestTemplate", registry, recorder,
                () -> raw.getForObject(
                        "http://inventory.test/stock/{sku}", String.class, "SKU-1"));
        rawServer.verify();
    }

    private static void expectStock(MockRestServiceServer server) {
        server.expect(request -> {
            if (request.getMethod() != HttpMethod.GET
                    || !"http://inventory.test/stock/SKU-1".equals(request.getURI().toString())) {
                throw new AssertionError("Unexpected request");
            }
        }).andRespond(withSuccess("8", MediaType.TEXT_PLAIN));
    }

    private static void measure(String label, ObservationRegistry registry,
            Recorder recorder, Supplier<String> call) {
        recorder.parents.clear();
        String body = Observation.createNotStarted("business.checkout", registry)
                .observe(call);
        String parent = recorder.parents.isEmpty() ? "none" : recorder.parents.get(0);
        System.out.println(label + " body=" + body + " clientStarted="
                + recorder.parents.size() + " parent=" + parent);
    }

    static class Recorder implements ObservationHandler<Observation.Context> {
        final List<String> parents = new ArrayList<>();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            if (context instanceof ClientRequestObservationContext) {
                parents.add(context.getParentObservation() == null ? "none"
                        : context.getParentObservation().getContextView().getName());
            }
        }
    }
}
~~~

`Recorder` ghi nhận callback `onStart` của ngữ cảnh HTTP client. Trường `clientStarted` trong stdout là số lần bắt đầu được ghi nhận ở mỗi lần thử, không phải số trace đã được xuất.

Các lần gọi chạy đồng bộ và tuần tự. Danh sách trong Recorder chỉ phục vụ thí nghiệm, không phải cấu trúc thu thập dùng cho nhiều yêu cầu đồng thời trong môi trường thực tế.

### 8.4. Biên dịch và chạy

PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out BuilderObservationProbe.java
java -cp "out;lib/*" BuilderObservationProbe
~~~

Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out BuilderObservationProbe.java
java -cp "out:lib/*" BuilderObservationProbe
~~~

Lần đầu cần tải dependency nếu máy chưa có sẵn.

### 8.5. Stdout đã kiểm chứng

~~~text
RestTemplateBuilder body=8 clientStarted=1 parent=business.checkout
RestClient.Builder body=8 clientStarted=1 parent=business.checkout
new RestTemplate body=8 clientStarted=0 parent=none
~~~

Kết quả cho thấy:

- Hai client có customizer đều phát ra observation HTTP client trong registry được chỉ định.
- Observation client nhận `business.checkout` làm cha trong lần thực thi đồng bộ.
- Cùng một phản hồi `8` vẫn được trả về với `new RestTemplate()`, nhưng không có observation client trong registry của thí nghiệm. `parent=none` ở dòng này nghĩa là không có bản ghi client để đọc parent, không phủ nhận observation nghiệp vụ đã được mở cho lần thử.
- Thành công về dữ liệu HTTP không tự xác nhận thành công về quan sát/truy vết.

Không cần mở backend để kiểm tra bước nối registry này. Tuy nhiên, để kết luận trace đã truyền qua HTTP và được dịch vụ tiếp theo nối vào cùng trace, vẫn cần kiểm chứng bên dưới.

## 9. Kiểm chứng truyền trace toàn tuyến cho cả ba client

### 9.1. Kịch bản hai dịch vụ

Chuẩn bị một luồng rõ ràng:

~~~text
Yêu cầu thử nghiệm
        |
        v
checkout
        |
        | lần lượt dùng một trong ba client
        v
inventory
~~~

Dùng ba lần thử độc lập với cùng thao tác nghiệp vụ:

1. Checkout gọi bằng RestTemplate tạo từ builder được tiêm.
2. Checkout gọi bằng RestClient tạo từ builder được tiêm.
3. Checkout gọi bằng WebClient tạo từ builder được tiêm và thực thi trong chuỗi/subscription phù hợp.

Đảm bảo cả checkout và inventory có quan sát phía server, tracing và định dạng truyền ngữ cảnh tương thích. Không coi việc chỉ cài tracing ở bên gọi là cấu hình đầy đủ cho cả hệ thống.

### 9.2. Ba mức kiểm tra

| Mức | Điều cần quan sát | Kết luận có thể rút ra |
| --- | --- | --- |
| 1. Tích hợp client | Có observation phía client trong registry đúng | Client đã được nối vào cơ chế quan sát |
| 2. Header trên HTTP | Yêu cầu tới inventory có header ngữ cảnh hợp lệ theo định dạng đã chọn | Chặng HTTP mang ngữ cảnh |
| 3. Trace phía nhận | Span server của inventory có cùng trace ID, đúng liên kết với span client | Dịch vụ nhận đã nối xử lý vào trace mong muốn |

Sau đó mới kiểm tra backend đã nhận và lưu dữ liệu để tìm kiếm. Log có trace ID hoặc header có mặt không phải xác nhận rằng exporter đã gửi thành công.

Với W3C, cần đối chiếu trace ID của S1/S2/S3 và quan hệ S1 → S2 → S3. Không yêu cầu cả ba span ID giống nhau.

### 9.3. Những tình huống cần thử thêm

- Một lời gọi thành công.
- Một phản hồi lỗi HTTP có xử lý lỗi theo thiết kế ứng dụng.
- Một trường hợp không kết nối được hoặc timeout.
- WebClient được subscribe trong luồng reactive thật.
- Trường hợp đổi executor/thread nếu ứng dụng có thực hiện.
- Các lần thử đồng thời để phát hiện việc giữ header/ngữ cảnh của yêu cầu cũ.

Nếu dùng kiểm thử Spring Boot, cần hiểu cách cấu hình observability của loại kiểm thử đang dùng. Không mặc định rằng mọi thành phần xuất dữ liệu đều được bật giống khi chạy ứng dụng thật.

### 9.4. Mẫu URI giúp đọc metric và trace

Ưu tiên lời gọi có mẫu ổn định:

~~~java
client.get()
        .uri("/stock/{sku}", sku)
        .retrieve()
        .body(String.class);
~~~

Phần giá trị thay đổi được truyền bằng biến URI. Điều này giữ ý nghĩa loại thao tác rõ hơn và hỗ trợ quy ước quan sát dùng mẫu URI.

Không tự đặt tên observation hoặc nhãn metric bằng trace ID, mã đơn hàng hay URL chứa mọi định danh. Header truy vết phục vụ liên kết ngữ cảnh, không phải nhãn để chia metric thành từng giao dịch.

## 10. Chẩn đoán trace bị đứt

| Hiện tượng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| HTTP thành công nhưng không có observation client | Cách tạo client và registry | Dùng builder được tiêm; kiểm tra customizer không bị bỏ |
| Có observation client nhưng không có header tracing | Bridge/bộ xử lý tracing và định dạng phát | Kiểm tra cấu hình tracing, không chỉ metric |
| Header tới inventory nhưng inventory tạo trace riêng | Định dạng nhận và tích hợp phía server | Kiểm tra consume, header hợp lệ và cơ chế trích ngữ cảnh |
| WebClient chưa gửi yêu cầu | Mono đã có subscription chưa | Giữ chuỗi thực thi đúng; không dùng subscribe riêng để chữa ngữ cảnh |
| WebClient có client span nhưng parent không như mong muốn | Ngữ cảnh tại thời điểm subscription | Kiểm tra Reactor Context, ThreadLocal và ranh giới đổi luồng |
| RestTemplate/RestClient mất parent sau khi chuyển executor | Ngữ cảnh của thread thực thi lời gọi | Dùng cơ chế truyền ngữ cảnh phù hợp cho executor |
| Hai yêu cầu không liên quan có cùng header được đặt tay | Default header hoặc dữ liệu giữ trong singleton | Bỏ giá trị tracing cố định, để cơ chế tracing tạo theo từng lần gọi |
| Đã dùng Bean nhưng vẫn không có tích hợp | Bean được dựng bằng cách nào | Phân biệt đăng ký bean và dựng qua builder đã cấu hình |
| Không thấy trace ở giao diện dù ngữ cảnh đúng | Lấy mẫu, đường xuất và bộ lọc tìm kiếm | Tách kiểm tra truyền header khỏi việc lưu dữ liệu |
| Xuất hiện các lớp span có cùng mục đích | Interceptor/annotation/agent bọc trùng | Xác định cơ chế sở hữu điểm đo trước khi thêm lớp bọc mới |

Một trình tự chẩn đoán hiệu quả là: **cách tạo client → observation client → ngữ cảnh cha → header đi ra → cách phía nhận đọc header → đường xuất và tìm kiếm trace**.

## 11. Bài tập tự kiểm chứng

1. Trong một ứng dụng Boot hiện có, tìm nơi tạo ba loại HTTP client. Phân biệt builder được tiêm với builder được tạo bằng lời gọi static.
2. Chạy chương trình thí nghiệm và giải thích vì sao cả ba lần đều có body bằng `8` nhưng chỉ hai lần có observation client trong registry được cấu hình.
3. Đổi một client từ `new RestTemplate()` sang builder được tiêm. Kiểm tra lần lượt observation, header và trace phía nhận.
4. Với WebClient, xác định chính xác nơi thực hiện subscription. Giải thích điều gì xảy ra nếu scope cha đã đóng trước thời điểm đó.
5. Kiểm tra header W3C ở dịch vụ nhận và chỉ ra trường trace ID, trường mã span phía gửi. Đối chiếu với span ID mới của phía nhận.
6. Thực hiện hai yêu cầu đồng thời và xác minh không có một traceparent cố định bị dùng chung do cấu hình thủ công.
7. Nếu chỉ có log trace ID ở checkout, liệt kê những bước còn thiếu để kết luận inventory đã nối đúng vào trace và backend đã lưu dữ liệu.

Tạo client từ builder đã được Boot cấu hình giúp giữ đường tích hợp quan sát. Việc truyền trace hoàn chỉnh còn cần ngữ cảnh đúng thời điểm thực thi, header tương thích và cơ chế quan sát hoạt động ở dịch vụ nhận.
