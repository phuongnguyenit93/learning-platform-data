# Quan sát HTTP client được tạo từ builder do Spring Boot quản lý

## 1. Phân biệt yêu cầu đi vào và yêu cầu đi ra

Giả sử ứng dụng nhận một yêu cầu đặt hàng, rồi gọi HTTP tới dịch vụ tồn kho. Có hai hoạt động khác nhau cần quan sát: xử lý yêu cầu tại ứng dụng của bạn và thực hiện yêu cầu đi ra tới dịch vụ khác.

```text
Người dùng -> Ứng dụng đặt hàng -> Dịch vụ tồn kho
              phía HTTP server    phía HTTP client
              http.server.requests
              cho yêu cầu vào     http.client.requests
                                  cho yêu cầu đi ra
```

`http.server.requests` không thay thế phép đo client. Thời gian xử lý yêu cầu vào có thể chứa nhiều bước nghiệp vụ, chờ hàng đợi và nhiều lời gọi ra ngoài; timer của một client đo hoạt động ở ranh giới client theo vòng đời quan sát của nó.

Spring Boot Actuator tích hợp quan sát cho `RestClient`, `RestTemplate` và `WebClient`. Điều kiện thực hành quan trọng là **lấy builder do Boot tự cấu hình, rồi tạo client từ builder đó**. Một đối tượng có kiểu `RestClient` hoặc được khai báo thành bean chưa tự chứng minh nó đang dùng cấu hình quan sát của Boot.

Ví dụ đầy đủ trong bài được kiểm chứng với **Boot 3.3.13, Spring Framework 6.1.21, Micrometer 1.13.15 và Java 17**. Đây là bộ phiên bản tái hiện thí nghiệm trong dòng Boot 3.3; không phải chỉ dẫn nâng riêng một thư viện hoặc lựa chọn bản vá triển khai cho mọi dự án.

## 2. Builder giữ vai trò gì trong luồng quan sát?

Trong Boot 3.3, cơ chế tích hợp dựa trên Micrometer Observation. Boot cung cấp các customizer gắn `ObservationRegistry` và quy ước quan sát thích hợp vào builder/client. Khi lời gọi được thực thi, Spring tạo observation; handler metrics chuyển các quan sát phù hợp thành meter.

```text
Builder được Boot cấu hình
  -> client mang ObservationRegistry + observation convention
  -> thực thi lời gọi HTTP
  -> observation bắt đầu / kết thúc / ghi lỗi khi phù hợp
  -> handler metrics ghi vào MeterRegistry
  -> đọc http.client.requests hoặc xuất sang hệ thống giám sát
```

`ObservationRegistry` tổ chức observation và các handler. `MeterRegistry` quản lý các meter. Chỉ có một bean registry bất kỳ hoặc một biến counter không thay thế việc client phải được nối đúng vào luồng này.

| Client | Builder cần lấy từ Spring | Đặc điểm sử dụng |
| --- | --- | --- |
| `RestClient` | `RestClient.Builder` | API đồng bộ theo chuỗi thao tác |
| `RestTemplate` | `RestTemplateBuilder` | API đồng bộ quen thuộc, builder nằm trong gói Boot |
| `WebClient` | `WebClient.Builder` | API phản ứng; tạo pipeline chưa đồng nghĩa đã gửi yêu cầu |

Các customizer tương ứng của Boot gồm `ObservationRestClientCustomizer`, `ObservationRestTemplateCustomizer` và `ObservationWebClientCustomizer`. Không cần thêm một interceptor đo thủ công chỉ để lặp lại chức năng tích hợp này. [HTTP client metrics của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.http-clients), [HttpClientObservationsAutoConfiguration 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/web/client/HttpClientObservationsAutoConfiguration.java).

### 2.1. Có metrics không đòi phải có hệ thống tracing

Observation có thể phục vụ metrics, tracing hoặc các handler phù hợp. Để có timer HTTP client trong ứng dụng dùng Actuator, không bắt buộc phải cấu hình một hệ thống nhận trace từ xa. Ngược lại, thấy metric cũng chưa chứng minh trace đã được tạo, lấy mẫu và gửi đi.

Thông tin ít giá trị phân biệt (low cardinality) có thể đi vào nhãn metrics; thông tin nhiều giá trị phân biệt được xử lý theo cơ chế quan sát tương ứng và không mặc nhiên trở thành tag của timer. Không đưa request ID, mã đơn hoặc toàn bộ URL thay đổi liên tục vào tags để tìm từng lượt gọi. [Quan sát, metrics và traces trong Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 2.2. “Spring quản lý client” chưa đủ nếu bỏ qua builder đã cấu hình

Các cách tạo trực tiếp sau không tự có cấu hình Observation của Boot:

```java
RestClient directRestClient = RestClient.create();
RestTemplate directRestTemplate = new RestTemplate();
WebClient directWebClient = WebClient.create();
```

Đó là các API hợp lệ, nhưng nếu không tự áp dụng cấu hình tương đương thì client có thể không ghi metrics vào registry của ứng dụng. Đưa một client tạo theo cách này vào phương thức `@Bean` không tự khôi phục các customizer đã bị bỏ qua ở giai đoạn xây dựng.

Tương tự, `new RestTemplateBuilder()`, `RestClient.builder()` hoặc `WebClient.builder()` tạo riêng không đồng nghĩa builder được Boot tiêm. Với tình huống đặc biệt cần builder riêng, phải áp dụng configurer/customizer tương ứng một cách có kiểm soát và kiểm chứng kết quả; tiêm builder sẵn có thường làm nguồn cấu hình rõ hơn.

## 3. Tạo client từ builder được tiêm

Trong ứng dụng Boot có các phụ thuộc cho client tương ứng, một cấu hình minh họa:

```java
package example.clients;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryClientConfiguration {
    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder.clone()
            .baseUrl("https://inventory.example")
            .build();
    }

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
            .rootUri("https://inventory.example")
            .build();
    }

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder.clone()
            .baseUrl("https://inventory.example")
            .build();
    }
}
```

Đây là cấu hình tích hợp cho dự án Boot, không phải một chương trình độc lập có main. `inventory.example` là địa chỉ mẫu; thí nghiệm chạy độc lập bên dưới dùng phản hồi giả lập trong bộ nhớ và không liên hệ máy chủ này.

Trong ứng dụng thực, không bắt buộc tạo cả ba loại client cho cùng một tác vụ. Cấu hình trên đặt cạnh nhau để chỉ rõ builder và cách giữ cấu hình quan sát cho từng API.

`RestClient.Builder` và `WebClient.Builder` có thể giữ trạng thái khi cấu hình. `clone()` giúp tách biến thể trước khi đặt base URL hoặc thêm tùy chỉnh, đồng thời giữ thiết lập đã có. `RestTemplateBuilder` dùng kiểu cấu hình trả về builder mới; cần sử dụng giá trị trả về của các phương thức cấu hình.

Không thay builder được tiêm bằng một builder mới ở giữa phương thức rồi kỳ vọng vẫn giữ ObservationRegistry, conventions, codecs hoặc những customizer khác. Cũng không đặt lại observation registry thành NOOP khi mục tiêu là thu thập metrics.

### 3.1. RestClient: gọi bằng mẫu URI

```java
String item = inventoryRestClient.get()
    .uri("/items/{id}", 7)
    .retrieve()
    .body(String.class);
```

Đoạn này nằm trong thành phần đã được tiêm `inventoryRestClient`. Lời gọi đồng bộ hoàn tất hoặc ném lỗi theo cách xử lý phản hồi của client. Khi đọc/đóng phản hồi đúng theo API, observation có vòng đời để kết thúc và xuất hiện trong metrics.

### 3.2. RestTemplate: giữ mẫu và biến URI

```java
String item = inventoryRestTemplate.getForObject(
    "/items/{id}", String.class, 7);
```

Không cần tự đo lại bằng một timer cùng tên bao quanh mỗi lời gọi. Nếu còn đo thời gian của cả nghiệp vụ, dùng một tên và ranh giới khác để phân biệt ý nghĩa của hai phép đo.

### 3.3. WebClient: cần có subscription thật sự

```java
Mono<String> pending = inventoryWebClient.get()
    .uri("/items/{id}", 7)
    .retrieve()
    .bodyToMono(String.class);

// Trả pending cho tầng WebFlux xử lý để pipeline được subscribe,
// hoặc thực thi nó ở ranh giới thích hợp của chương trình.
```

Đoạn minh họa cần import `reactor.core.publisher.Mono`. Chỉ tạo `pending` chưa gửi yêu cầu HTTP. Nếu không có subscription, không thể yêu cầu một mẫu timer của lời gọi chưa thực thi xuất hiện.

Trong controller phản ứng, thường trả `Mono` cho framework; không thêm `subscribe()` chỉ để “bật metrics”, vì có thể tạo một lần gọi tách khỏi vòng đời yêu cầu và xử lý lỗi đang mong muốn. `block()` trong chương trình kiểm chứng ở cuối bài chỉ dùng trên main của chương trình đồng bộ, không phải gợi ý chặn luồng xử lý phản ứng của WebFlux.

Một pipeline lạnh có thể thực hiện lại lời gọi khi được subscribe lần nữa. Vì vậy subscribe hai lần hoặc đặt retry ở vị trí gây thực thi lại có thể tạo nhiều lần quan sát. Cần hiểu vòng đời thực thi, không chỉ đếm số lần mã đã tạo ra một biến `Mono`.

## 4. Chọn mẫu URI để metrics có ý nghĩa

So sánh hai cách gọi:

```java
// Giữ một mẫu có biến để nhóm nhiều mã đơn:
client.get().uri("/items/{id}", id).retrieve().body(String.class);

// Ghép dữ liệu biến thiên vào chuỗi trước khi gọi:
client.get().uri("/items/" + id).retrieve().body(String.class);
```

Đây là minh họa với biến `client` đã cấu hình base URL và biến `id`. Mẫu `/items/{id}` giúp convention giữ một chiều `uri` ổn định cho nhiều ID. Ghép trước chuỗi có thể làm dữ liệu cụ thể trở thành nhiều mẫu khác nhau, tăng số tổ hợp nhãn và chi phí meter.

Nếu truyền một `URI` đã dựng sẵn hoặc một biến thể API không giữ thông tin mẫu, convention có thể không còn biết mẫu ban đầu; khi đó `uri` có thể là giá trị thay thế như `none`, tùy client và phiên bản. Không suy rằng client đã lỗi chỉ vì tag uri không chứa một đường dẫn cụ thể.

Nên kiểm tra nhãn thực tế và ưu tiên overload chuỗi có biến URI cho tình huống cần nhóm theo mẫu. Không mặc định mọi hàm `uri(...)` hoặc một hàm tự ghép URL đều giữ metadata quan sát giống nhau.

Boot có cơ chế giới hạn số giá trị tag uri của HTTP client, nhưng giới hạn là lớp bảo vệ; nó không tự thiết kế lại nhóm dữ liệu cho bạn và có thể từ chối meter vượt ngưỡng. Sửa cách tạo URI có ý nghĩa hơn việc chỉ tăng giới hạn khi danh tính đang tăng không kiểm soát.

## 5. Đọc metric http.client.requests

### 5.1. Ghi nhận và công khai endpoint là hai việc khác nhau

Client có thể ghi metrics trong ứng dụng dù endpoint metrics chưa được đưa ra HTTP. Khi muốn chẩn đoán qua Actuator trong ứng dụng web, cấu hình ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Quyền truy cập và URL/cổng quản trị vẫn theo cấu hình ứng dụng. Công khai endpoint không tự gửi một request đi ra và không sửa một client đã tạo bằng builder không được cấu hình.

Thông thường cần ít nhất một lời gọi được thực thi và đi đến giai đoạn ghi nhận trước khi timer tương ứng xuất hiện. Hãy tạo một lượt thử có kiểm soát, chờ nó kết thúc, rồi kiểm tra:

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/metrics/http.client.requests
```

Các lệnh áp dụng cho ứng dụng web có endpoint tại URL đó, không phải chương trình kiểm chứng không mở cổng ở phần sau. Trên PowerShell có alias `curl`, dùng `curl.exe` để chạy đúng cú pháp.

Tên mặc định là `http.client.requests`; có thể đổi bằng `management.observations.http.client.requests.name`. Nếu dự án đã đổi tên, hãy khám phá danh sách thực tế thay vì kết luận instrumentation mất vì URL cũ trả 404.

### 5.2. Đọc các chiều phân loại

Các convention HTTP client tiêu chuẩn thường cung cấp các chiều sau; đọc `availableTags` để xác nhận tập thực tế của dự án/phiên bản:

| Tag | Ý nghĩa cần giữ rõ |
| --- | --- |
| `method` | Phương thức HTTP, chẳng hạn GET |
| `uri` | Mẫu URI khi được giữ, hoặc giá trị thay thế khi không có mẫu |
| `client.name` | Tên host đích theo convention, không mặc định là tên bean client hoặc tên nghiệp vụ dịch vụ |
| `status` | Mã trạng thái phản hồi khi có; có thể có nhãn đặc biệt cho tình huống không đọc được phản hồi |
| `outcome` | Nhóm kết quả suy từ phản hồi hoặc giá trị chưa xác định |
| `exception` | Thông tin loại ngoại lệ theo observation context/convention, không phải nội dung lỗi đầy đủ |

Handler hoặc cấu hình khác còn có thể thêm nhãn như `error` và tags dùng chung. Không ép mọi ứng dụng phải chỉ có đúng sáu tags trên. `client.name=inventory.example` trong thí nghiệm là host của URI giả lập; nó không tự đổi thành một tên nghiệp vụ như “kho hàng”.

Không có phản hồi HTTP khác với phản hồi HTTP 503. Các nhãn đặc biệt như `CLIENT_ERROR` hoặc `IO_ERROR` là quy ước ở tầng quan sát, không phải mã HTTP số hoặc bằng chứng rằng server đã trả một HTTP 4xx. [Convention đồng bộ của Framework 6.1.21](https://github.com/spring-projects/spring-framework/blob/v6.1.21/spring-web/src/main/java/org/springframework/http/client/observation/DefaultClientRequestObservationConvention.java).

`RestTemplate`/`RestClient` dùng convention trong gói `org.springframework.http.client.observation`; `WebClient` dùng giao diện convention của gói `org.springframework.web.reactive.function.client`. Khi tùy chỉnh, không lấy bean của giao diện bên này rồi mặc định bên kia cũng sử dụng nó.

### 5.3. Đọc phép đo và lọc đúng nhóm

Vì đây là timer, thường có COUNT, TOTAL_TIME và MAX. COUNT của các mẫu kết thúc không tự là số lượt mỗi giây; các trường thời lượng phải đọc cùng đơn vị được báo cáo. Không dùng timer client làm toàn bộ thời gian một giao dịch nghiệp vụ.

Có thể lọc theo các tags thực tế, ví dụ:

```bash
curl -s -G http://127.0.0.1:8080/actuator/metrics/http.client.requests --data-urlencode "tag=client.name:inventory.example" --data-urlencode "tag=uri:/items/{id}" --data-urlencode "tag=status:200"
```

Ba tham số tag được áp dụng đồng thời. Nếu gọi một tên mà có nhiều bộ tags, endpoint có thể trả dữ liệu gộp; không lọc thì một COUNT có thể chứa nhiều host, phương thức hoặc kết quả.

Tên bean hoặc loại Java của client không mặc nhiên là một tag phân biệt. Hai client khác nhau có cùng các nhãn chuẩn có thể ghi vào cùng nhóm timer. Khi kiểm chứng, dùng chênh lệch trước–sau từng pha hoặc một convention ít chiều có ý nghĩa; không tự thêm ID đối tượng Java vào tag.

## 6. Chương trình kiểm chứng cả ba builder, không dùng mạng

Thí nghiệm tạo một Spring application context có tự cấu hình Boot và lấy các builder từ context. `MockRestServiceServer` cung cấp phản hồi cho hai client đồng bộ; `exchangeFunction` cung cấp phản hồi trong bộ nhớ cho WebClient.

Không có DNS/TLS/server thật trong thí nghiệm. Nó kiểm tra đường nối builder → observation → meter, mẫu URI và thời điểm thực thi; không đo hiệu năng mạng, retry ở transport, pool kết nối hay thời gian thật của dịch vụ tồn kho.

Tạo dự án Gradle có wrapper và JDK 17 khả dụng:

```text
managed-http-client-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/example/client/ManagedHttpClientDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'managed-http-client-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework:spring-webflux'
    implementation 'org.springframework:spring-test'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
    implementation 'org.hamcrest:hamcrest'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.client.ManagedHttpClientDemo'
}
```

BOM Boot 3.3.13 giữ các thư viện cùng bộ phiên bản đã kiểm chứng; không trộn tùy ý Spring Framework/Micrometer cũ với một BOM khác rồi kỳ vọng mọi chi tiết vòng đời đo giống nhau.

`spring-test` và Hamcrest nằm ở cấu hình implementation **chỉ vì đây là một chương trình main phục vụ kiểm chứng** có dùng công cụ giả lập. Trong dự án sản phẩm, các công cụ kiểm thử này thường nằm ở phạm vi test; không thêm chúng vào runtime chỉ để bật metrics. `httpclient5` cung cấp một request factory cho đường xây dựng client đồng bộ trong thí nghiệm; phản hồi thực tế vẫn bị thay bằng factory giả lập trước khi gọi.

`src/main/java/example/client/ManagedHttpClientDemo.java`:

```java
package example.client;

import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

public class ManagedHttpClientDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class DemoConfiguration {
        @Bean
        ClientHttpConnector noNetworkConnector() {
            return (method, uri, callback) -> Mono.error(
                new AssertionError("A real connection must not be used in this demo"));
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("demo", Map.of(
                "management.metrics.use-global-registry", false)));
        context.register(DemoConfiguration.class);
        context.refresh();

        try {
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            require(count(registry) == 0, "No client calls yet");

            RestClient.Builder managedBuilder =
                context.getBean(RestClient.Builder.class).clone();
            MockRestServiceServer managedServer =
                MockRestServiceServer.bindTo(managedBuilder).build();
            managedServer.expect(requestTo("https://inventory.example/items/7"))
                .andRespond(withSuccess("item-7", MediaType.TEXT_PLAIN));
            managedServer.expect(requestTo("https://inventory.example/items/8"))
                .andRespond(withSuccess("item-8", MediaType.TEXT_PLAIN));
            managedServer.expect(requestTo("https://inventory.example/items/9"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

            RestClient managed = managedBuilder.build();
            require("item-7".equals(managed.get()
                .uri("https://inventory.example/items/{id}", 7)
                .retrieve().body(String.class)), "First body");
            require("item-8".equals(managed.get()
                .uri("https://inventory.example/items/{id}", 8)
                .retrieve().body(String.class)), "Second body");
            require(count(registry, "status", "200") == 2, "Two successful calls");
            System.out.println("restClient.success=" + count(registry, "status", "200"));

            try {
                managed.get().uri("https://inventory.example/items/{id}", 9)
                    .retrieve().body(String.class);
                throw new AssertionError("Expected HTTP 503");
            }
            catch (RestClientResponseException exception) {
                require(exception.getStatusCode().value() == 503, "Expected 503");
            }
            managedServer.verify();
            require(count(registry, "status", "503") == 1, "503 recorded");
            require(count(registry, "uri", "/items/{id}") == 3,
                "One URI template for all three calls");
            System.out.println("restClient.status503="
                + count(registry, "status", "503"));
            System.out.println("restClient.templateCalls="
                + count(registry, "uri", "/items/{id}"));

            long beforeRaw = count(registry);
            RestClient.Builder rawBuilder = RestClient.builder();
            MockRestServiceServer rawServer =
                MockRestServiceServer.bindTo(rawBuilder).build();
            rawServer.expect(requestTo("https://inventory.example/items/20"))
                .andRespond(withSuccess("raw", MediaType.TEXT_PLAIN));
            require("raw".equals(rawBuilder.build().get()
                .uri("https://inventory.example/items/{id}", 20)
                .retrieve().body(String.class)), "Raw body");
            rawServer.verify();
            require(count(registry) == beforeRaw, "Raw builder has no Boot observation setup");
            System.out.println("raw.added=" + (count(registry) - beforeRaw));

            RestTemplate template = context.getBean(RestTemplateBuilder.class)
                .requestFactory(SimpleClientHttpRequestFactory.class)
                .rootUri("https://inventory.example")
                .build();
            MockRestServiceServer templateServer =
                MockRestServiceServer.bindTo(template).build();
            templateServer.expect(requestTo("https://inventory.example/items/30"))
                .andRespond(withSuccess("template", MediaType.TEXT_PLAIN));
            long beforeTemplate = count(registry);
            require("template".equals(template.getForObject(
                "/items/{id}", String.class, 30)), "RestTemplate body");
            templateServer.verify();
            require(count(registry) == beforeTemplate + 1, "RestTemplate observation");
            System.out.println("restTemplate.added="
                + (count(registry) - beforeTemplate));

            WebClient web = context.getBean(WebClient.Builder.class).clone()
                .baseUrl("https://inventory.example")
                .exchangeFunction(request -> Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header("Content-Type", "text/plain")
                    .body("reactive").build()))
                .build();

            long beforeReactive = count(registry);
            Mono<String> pending = web.get().uri("/items/{id}", 40)
                .retrieve().bodyToMono(String.class);
            require(count(registry) == beforeReactive, "Assembly is not execution");
            System.out.println("webClient.beforeSubscribe="
                + (count(registry) - beforeReactive));

            require("reactive".equals(pending.block()), "First subscription");
            require(count(registry) == beforeReactive + 1, "First observation");
            System.out.println("webClient.afterSubscribe="
                + (count(registry) - beforeReactive));

            require("reactive".equals(pending.block()), "Second subscription");
            require(count(registry) == beforeReactive + 2, "Second observation");
            System.out.println("webClient.afterSecondSubscribe="
                + (count(registry) - beforeReactive));

            require(count(registry) == 6, "Expected six observed exchanges");
            System.out.println("observed.total=" + count(registry));
            System.out.println("OBSERVATION_PASS");
        }
        finally {
            context.close();
        }
    }

    private static long count(MeterRegistry registry, String... tags) {
        return registry.find("http.client.requests").tags(tags).timers()
            .stream().mapToLong(Timer::count).sum();
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Khởi chạy tại thư mục dự án:

```bash
./gradlew -q run --console=plain
```

Trên Windows PowerShell dùng `.\gradlew.bat -q run --console=plain`. Các lớp phụ thuộc được Gradle giải quyết; nếu dùng `javac`/`java` trực tiếp phải có đầy đủ classpath ở cả hai bước.

Kết quả của thí nghiệm trên bộ phiên bản nêu đầu bài:

```text
restClient.success=2
restClient.status503=1
restClient.templateCalls=3
raw.added=0
restTemplate.added=1
webClient.beforeSubscribe=0
webClient.afterSubscribe=1
webClient.afterSecondSubscribe=2
observed.total=6
OBSERVATION_PASS
```

### 6.1. Ba lượt RestClient và một mẫu URI

Hai lượt đầu nhận HTTP 200; lượt thứ ba nhận 503 và đi qua cơ chế ném lỗi của `retrieve()`. Phần kiểm tra bắt ngoại lệ để chương trình tiếp tục, đồng thời xác nhận nhóm `status=503` vẫn có một mẫu.

Ba URL có ID 7, 8, 9 đều được gọi bằng mẫu `/items/{id}`, nên bộ lọc theo uri đó đếm được 3. Bắt ngoại lệ ở mã gọi không tự xóa mẫu đã được quan sát. Tuy nhiên, các tags ngoại lệ cụ thể vẫn phụ thuộc chỗ lỗi được đưa vào observation context; không dùng riêng exception tag để thay mọi phân loại lỗi.

### 6.2. Client tạo riêng vẫn trả được nội dung nhưng không thêm mẫu

Client `rawBuilder` vẫn nhận phản hồi giả lập và trả chuỗi `raw`, nhưng không được tạo từ builder của Boot và không tự áp dụng customizer. `raw.added=0` chứng minh việc gọi thành công không đồng nghĩa đã nối metrics vào registry đang kiểm tra.

Đây là một đối chứng có kiểm soát, không phải quy tắc rằng API tạo trực tiếp không bao giờ có thể quan sát được. Nó có thể được cấu hình thủ công với ObservationRegistry/customizer tương đương; lúc đó cần kiểm chứng cấu hình đó riêng.

### 6.3. Tùy chỉnh RestTemplate không làm mất cấu hình đã được giữ

RestTemplate được lấy từ `RestTemplateBuilder` của context rồi đặt root URI và request factory. Nó vẫn thêm đúng một mẫu khi gọi. Điều cần giữ là nguồn builder và đường áp dụng customizer, không phải tránh mọi tùy chỉnh client.

### 6.4. WebClient được đếm theo thực thi

Trước subscription, chênh lệch bằng 0. Hai lần `block()` trong main gây hai subscription vào pipeline lạnh, nên chênh lệch lần lượt là 1 và 2.

Bean `noNetworkConnector` làm một lần kết nối thật trong thí nghiệm trở thành lỗi; `exchangeFunction` đã cung cấp phản hồi giả lập. Cấu hình này chỉ phục vụ kiểm chứng và không thuộc cấu hình client sản phẩm.

### 6.5. Tổng 6 là số mẫu đã được kiểm tra, không phải hằng số mọi ứng dụng

```text
RestClient:   2 mẫu 200 + 1 mẫu 503 = 3
RestTemplate: 1 mẫu                 = 1
WebClient:    2 subscription        = 2
Client raw:   không được nối đo     = 0
Tổng quan sát                      = 6
```

`OBSERVATION_PASS` nghĩa các điều kiện assert của thí nghiệm đạt trên cấu hình đã nêu. Nó không chứng minh mọi lời gọi HTTP trong một ứng dụng khác đã được quan sát, hoặc tracing/exporter đã được cấu hình.

## 7. Những ranh giới cần hiểu trước khi dùng số liệu

### 7.1. Observation không tự cấu hình timeout hoặc retry

Có timer không nghĩa client đã có giới hạn thời gian phù hợp. Timeout, request factory/connector, pool, retry và chính sách xử lý lỗi là các cấu hình liên quan nhưng độc lập.

Các tầng thực thi có thể có cách xử lý nhiều lần gửi khác nhau. Ví dụ resubscribe một pipeline WebClient có thể thực thi lại observation; một cơ chế retry ẩn ở transport không mặc nhiên tương ứng với cùng cách đếm. Muốn hiểu số mẫu, cần kiểm tra retry ở tầng nào và điểm quan sát bao quanh phạm vi nào.

### 7.2. Thời lượng client không phải mọi loại “độ trễ”

Mẫu timer hoàn tất theo vòng đời observation của client và cách dùng API. Với phản hồi dạng stream, việc đọc/đóng body và cancellation có ảnh hưởng tới vòng đời tài nguyên; không tự giả định một con số luôn bao gồm toàn bộ thời gian xử lý nghiệp vụ hoặc mọi byte của mọi kiểu body.

Các lời gọi thông thường trong bài dùng `body(String.class)`/`getForObject()`/`bodyToMono()` và lấy kết quả để có luồng thực thi rõ ràng. Nếu dùng API mức thấp như exchange hoặc trả phản hồi chưa được tiêu thụ, phải quản lý vòng đời theo hợp đồng API và kiểm tra tín hiệu tương ứng.

### 7.3. Metrics và traces là những bằng chứng khác nhau

Không thấy trace có thể liên quan handler tracing, sampling, context propagation hoặc exporter; không mặc định sửa bằng cách tạo thêm counter. Thấy `http.client.requests` cũng không xác minh trace context đã được truyền tới phía đích.

Các header chứa thông tin xác thực, URL đầy đủ và dữ liệu người dùng không nên được biến thành tags chỉ để debug từng lời gọi. Giữ các chiều metrics hữu hạn và dùng nguồn chẩn đoán chi tiết thích hợp với chính sách dữ liệu của ứng dụng.

## 8. Khi không thấy http.client.requests

| Điều cần kiểm tra | Câu hỏi cụ thể |
| --- | --- |
| Nguồn client | Client thực sự được build từ builder Boot tiêm hay được tạo bằng API tĩnh/new ở một nhánh khác? |
| Tự cấu hình và lớp phụ thuộc | Loại client/builder có thật sự tồn tại trong context hiện tại không? Các điều kiện tự cấu hình có phù hợp không? |
| ObservationRegistry và handler | Registry đang hoạt động và có handler metrics không, hay cấu hình đã bị thay bằng NOOP? |
| Thực thi thật | Với WebClient đã có subscription chưa? Chương trình có chỉ tạo Mono rồi bỏ đó không? |
| Vòng đời lời gọi | Lời gọi đã đi đến lúc observation ghi nhận chưa? Phản hồi/luồng đang còn mở không? |
| Tên metric | Có đổi `management.observations.http.client.requests.name` không? |
| Filters/predicates | Observation hoặc meter bị từ chối theo cấu hình không? Đã vượt giới hạn URI tags chưa? |
| Registry được đọc | Metrics có vào registry ứng dụng mà endpoint dùng không, hay đang kiểm tra một registry khác? |
| HTTP endpoint | Có đang gặp lỗi quyền/đường dẫn web exposure thay vì thiếu meter không? |

Không thêm `@Timed` cho mọi phương thức hoặc một interceptor đo riêng như bước sửa đầu tiên. Nó có thể tạo một phép đo khác ranh giới hoặc làm số liệu khó hiểu hơn, trong khi nguyên nhân chỉ là builder không đúng hoặc chưa subscribe.

Trong ứng dụng phản ứng, các điều kiện tự cấu hình cho client đồng bộ có thể khác với ứng dụng không phản ứng. Không giả định chỉ thêm một kiểu builder vào chữ ký constructor thì Spring chắc chắn luôn cung cấp nó ở mọi loại ứng dụng. Hãy kiểm tra bean/điều kiện thực tế.

## 9. Khi số mẫu lớn hơn số lượt gọi dự kiến

Trước tiên kiểm tra số lần thực thi thật: một pipeline được subscribe lại, retry của ứng dụng, một thao tác nghiệp vụ gọi nhiều downstream hoặc cùng một phép thử được chạy nhiều lần. Sau đó kiểm tra có tự gắn thêm lớp instrumentation hay đăng ký handler trùng lặp không.

Cuối cùng, đối chiếu chính xác bản vá Boot/Framework/Micrometer với một phép thử nhỏ có số phản hồi được kiểm soát. Chi tiết vòng đời quan sát có thể khác giữa các bản vá; không chia COUNT cho 2 hoặc bỏ mẫu bằng một filter để làm khớp con số mong muốn mà chưa xác định nguyên nhân.

Ví dụ trong bài cố định bộ phiên bản và kiểm tra chênh lệch sau từng pha. Nếu sửa cấu hình hoặc phiên bản làm assert không còn khớp, cần tìm lý do trước khi thay số kỳ vọng. Giữ nguyên quản lý phụ thuộc đồng bộ của Boot thay vì tự nâng/hạ một thư viện để né kết quả kiểm tra.

## 10. Tự kiểm tra

1. Một `RestClient` được khai báo thành bean nhưng bên trong phương thức tạo dùng `RestClient.create()`. Vì sao chưa thể khẳng định nó có cấu hình quan sát của Boot?
2. Viết cách tạo từng loại client từ ba builder tương ứng; nêu khi nào cần giữ giá trị builder trả về hoặc tạo bản clone.
3. Thay mẫu `/items/{id}` bằng cách ghép ID vào chuỗi rồi quan sát tag uri. Điều gì có thể xảy ra với số tổ hợp nhãn?
4. Tạo một Mono WebClient nhưng không trả nó cho framework, không subscribe và không block. Có nên đợi một mẫu request đi ra xuất hiện không?
5. Trong main đồng bộ, subscribe cùng pipeline lạnh hai lần. Vì sao có thể có hai mẫu dù biến Mono chỉ được tạo một lần?
6. Một lời gọi nhận 503 và mã gọi bắt ngoại lệ. Nêu vì sao vẫn cần xem status/outcome và không mặc định mẫu lỗi đã bị xóa.
7. Nếu có `http.server.requests` nhưng không có `http.client.requests`, bạn sẽ kiểm tra những ranh giới nào trước khi thêm instrumentation thủ công?
8. Vì sao một timer client có dữ liệu chưa chứng minh timeout, retry, tracing và exporter đều được cấu hình đúng?

Quan sát HTTP client đáng tin bắt đầu từ **builder đúng nguồn, luồng thực thi thật, mẫu URI có kiểm soát và phép đối chiếu số mẫu theo từng pha**, rồi mới dùng dữ liệu để điều tra hệ thống.
