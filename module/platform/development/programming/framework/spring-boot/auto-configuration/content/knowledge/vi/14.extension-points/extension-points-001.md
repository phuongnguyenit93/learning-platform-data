# Customizer và builder: tùy chỉnh bean nhưng giữ nguyên cấu hình mặc định của Spring Boot

## 1. Mục tiêu và bài toán

Spring Boot **Auto-configuration** không chỉ giúp ứng dụng có sẵn các bean cần thiết. Nó còn thiết lập nhiều mặc định quan trọng: HTTP message converters, cách chọn HTTP request factory, hỗ trợ JSON, quan sát (observability) khi có hạ tầng tương ứng, SSL, cấu hình theo property và những thành phần tích hợp khác.

Khi cần thêm một thay đổi nhỏ, chẳng hạn:
- Mọi HTTP client nội bộ đều gửi header `X-App-Client`.
- Một HTTP client gọi API bên ngoài dùng `baseUrl` riêng.
- JSON bỏ qua các trường `null`.
- Một `RestTemplate` có timeout riêng cho một dịch vụ.
- Thư viện starter muốn thêm hành vi chung nhưng cho phép ứng dụng tự thay đổi.

Giải pháp thường là **tận dụng builder do Boot cấp** hoặc **đăng ký bean customizer được Boot hỗ trợ**. Hai cơ chế này cho phép sửa một phần hành vi mà vẫn kế thừa cấu hình nền.

Nguyên tắc trung tâm:

> Hãy nhận builder đã được Spring Boot auto-configure, hoặc đóng góp customizer mà auto-configuration biết cách áp dụng. Chỉ thay thế toàn bộ builder/bean khi thực sự cần quyền kiểm soát sâu hơn.

Bài học sử dụng ví dụ chính với **Spring Boot 3.5.x, Java 17+**. API và package của một số lớp đã thay đổi trong Spring Boot 4.x; vì vậy tên import và cách cấu hình trong bài được gắn rõ với dòng 3.5.

## 2. Ba khái niệm cần phân biệt

### 2.1. Builder

**Builder** là đối tượng tạo ra một đối tượng khác sau khi người dùng thiết lập các tùy chọn. Ví dụ:

~~~java
// Ví dụ minh họa; không phải chương trình Java độc lập.
RestClient client = restClientBuilder
        .baseUrl("https://catalog.example.test")
        .defaultHeader("X-Team", "catalog")
        .build();
~~~

`RestClient.Builder` chứa cấu hình để sinh `RestClient`. Spring Boot 3.5 có thể tạo một bean builder **đã được cấu hình sẵn** qua `RestClientAutoConfiguration`.

Nếu chỉ cần thay `baseUrl` cho một client, ta cấu hình trên bản builder được inject rồi gọi `build()` thay vì tự tạo mọi thứ từ đầu.

### 2.2. Customizer

**Customizer** là callback nhận builder hoặc đối tượng đang được cấu hình, sau đó thực hiện chỉnh sửa có phạm vi rõ ràng. Ví dụ trong Spring Boot 3.5:

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;

// Đặt phương thức trong lớp @Configuration hoặc @SpringBootApplication.
@Bean
RestClientCustomizer addClientHeader() {
    return builder -> builder.defaultHeader("X-Team", "catalog");
}
~~~

Khi tạo **RestClient.Builder qua auto-configuration**, Boot áp dụng các `RestClientCustomizer` đã đăng ký. Điều này có thể bổ sung header mà không phải chép lại tất cả cấu hình HTTP nền.

Không phải cứ interface có tên `*Customizer` là Spring Boot tự tìm và áp dụng cho mọi đối tượng. Một customizer chỉ có tác dụng **nếu đúng auto-configuration hoặc builder thực sự thu thập và gọi nó**.

### 2.3. Configurer

**Configurer** là một lớp tiện ích biết cách đưa các mặc định của Spring Boot vào một builder do bạn tạo. Ví dụ `RestClientBuilderConfigurer` của Boot 3.5:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.web.client.RestClient;

// Đoạn minh họa trong một lớp cấu hình.
RestClient.Builder configured =
        configurer.configure(RestClient.builder());
~~~

Đây là cơ chế quan trọng khi bắt buộc phải tự định nghĩa bean builder. Nó giúp tránh bỏ sót những mặc định mà bạn không nhìn thấy chỉ qua một dòng `new` hoặc `builder()`.

## 3. Luồng auto-configuration và các điểm mở rộng

Mô hình đơn giản:

~~~text
Classpath + Environment + các bean ứng dụng
                      |
                      v
     Auto-configuration phù hợp được kích hoạt
                      |
                      v
       Boot chuẩn bị cấu hình mặc định
          /        |           \
         v         v            v
  HTTP factory  Converters   Observability/SSL...
          \        |           /
           \       v          /
       Builder được Boot cấu hình
                      |
                      v
       Customizer phù hợp được áp dụng
                      |
                      v
      Code ứng dụng thêm tùy chỉnh cục bộ
                      |
                      v
                  build()
                      |
                      v
                Bean/client sử dụng
~~~

Sơ đồ là cách hình dung, không mô tả tuyệt đối thứ tự từng callback nội bộ cho mọi loại builder. Thứ tự cụ thể giữa các customizer phụ thuộc framework, extension point và `@Order`/`Ordered` nếu chúng được hỗ trợ.

**Từ khóa cần nhớ:**
- **Mặc định (defaults):** do framework và các property chuẩn cung cấp.
- **Tùy chỉnh bổ sung (additive customization):** chỉ thêm phần bạn cần.
- **Thay thế (replacement):** cung cấp bean/builder riêng, có thể khiến auto-configuration dừng tạo đối tượng mặc định do `@ConditionalOnMissingBean`.
- **Phạm vi (scope):** tùy chỉnh chỉ cho một client hay toàn bộ client sử dụng cùng loại builder.

## 4. Chọn đúng cách tùy chỉnh

| Mục đích | Cách nên ưu tiên | Phạm vi |
| --- | --- | --- |
| Thay URL và header cho một HTTP client | Inject `RestClient.Builder`, cấu hình rồi `build()` | Client được tạo tại điểm sử dụng |
| Thêm header chung cho mọi `RestClient.Builder` do Boot cấp | Bean `RestClientCustomizer` | Các builder đi qua auto-configuration |
| Dùng JSON config mặc định + thêm một chính sách serialization | Property `spring.jackson.*` hoặc `Jackson2ObjectMapperBuilderCustomizer` | ObjectMapper được tạo qua builder auto-configured |
| Muốn cấp `RestTemplateBuilder` tùy biến toàn cục | `RestTemplateBuilderConfigurer.configure(new RestTemplateBuilder())` rồi thay phần cần thiết | Bean builder do ứng dụng cung cấp |
| Muốn tự cấp `RestClient.Builder` nhưng vẫn giữ defaults | `RestClientBuilderConfigurer.configure(RestClient.builder())` | Builder do ứng dụng cung cấp |
| Muốn thay hẳn một implementation không tương thích defaults | Định nghĩa bean mới và kiểm soát các dependency | Cần kiểm thử kỹ, có thể làm auto-config back off |

Nên tăng dần mức độ can thiệp: property chuẩn → builder cục bộ → customizer bean → configurer + builder riêng → bean thay thế hoàn toàn. Đây là thứ tự lựa chọn thực tiễn, **không phải** thứ tự xử lý cố định trong framework.

## 5. Ví dụ chạy được: giữ HTTP/JSON mặc định, thêm header chung

Ví dụ tạo một client HTTP gọi dịch vụ danh mục. Ta muốn:
1. Dùng `RestClient.Builder` do Spring Boot 3.5 cấp để giữ HTTP message converters và request factory phù hợp.
2. Thêm `X-App-Client: study-service` qua `RestClientCustomizer` dùng chung.
3. Đặt `baseUrl` riêng cho client danh mục.
4. Kiểm thử JSON response và header mà **không gọi internet**.

### 5.1. Cấu trúc dự án

~~~text
customizer-demo/
├── pom.xml
└── src/
    ├── main/java/example/ClientCustomizationApplication.java
    └── test/java/example/ClientCustomizationTests.java
~~~

Dùng Java 17+ và Maven; các tên file/class phải khớp với ví dụ.

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>customizer-demo</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-web` đưa Spring Web và hỗ trợ JSON theo mặc định của dòng Boot 3.5 vào ứng dụng. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và các công cụ `MockRestServiceServer` từ Spring Test.

Phiên bản ví dụ được cố định để các API tương thích. Với dự án thực tế, dùng bản vá Spring Boot đã được dự án quản lý và kiểm thử, tránh tự hạ phiên bản chỉ để giống bài.

### 5.3. Ứng dụng và customizer

Tệp `src/main/java/example/ClientCustomizationApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication(proxyBeanMethods = false)
public class ClientCustomizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClientCustomizationApplication.class, args);
    }

    @Bean
    RestClientCustomizer appClientHeaderCustomizer() {
        return builder ->
                builder.defaultHeader("X-App-Client", "study-service");
    }

    @Bean
    CatalogClient catalogClient(RestClient.Builder builder) {
        // Đây là RestClient.Builder mà Boot đã cấu hình.
        return new CatalogClient(
                builder.baseUrl("https://catalog.example.test").build());
    }

    public static final class CatalogClient {

        private final RestClient client;

        public CatalogClient(RestClient client) {
            this.client = client;
        }

        public Item find(long id) {
            return client.get()
                    .uri("/items/{id}", id)
                    .retrieve()
                    .body(Item.class);
        }

        public record Item(long id, String name) {
        }
    }
}
~~~

**Giải thích các điểm mấu chốt:**

- `RestClientCustomizer` là interface callback do Spring Boot hỗ trợ. Bean customizer được thu thập khi Boot cấu hình `RestClient.Builder`.
- `builder.defaultHeader(...)` bổ sung header mặc định, không yêu cầu viết lại HTTP message converters, request factory hay toàn bộ logic client.
- Tham số `RestClient.Builder builder` trong `catalogClient(...)` được **inject**, không do code ứng dụng gọi `RestClient.builder()` trực tiếp.
- `baseUrl(...)` là cấu hình **cục bộ cho client danh mục**.
- `build()` tạo ra `RestClient` cho `CatalogClient`; từ đó việc gọi API có thể dùng JSON mapping do các message converters được cấu hình.
- `https://catalog.example.test` là URL minh họa. Không gửi request ra mạng khi chạy test ở mục sau.

Boot 3.5 auto-configure `RestClient.Builder` với **prototype scope**. Về cơ bản, mỗi lần framework yêu cầu bean builder mới từ container sẽ nhận một bản builder tách biệt đã được cấu hình. Nhưng một singleton đã inject builder vào constructor **không tự nhận builder mới mỗi lần gọi phương thức** của singleton.

### 5.4. Kiểm thử: xác minh header và JSON mapping cùng tồn tại

Tệp `src/test/java/example/ClientCustomizationTests.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@SpringBootTest(
    classes = ClientCustomizationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ClientCustomizationTests {

    @Autowired
    RestClient.Builder bootBuilder;

    @Test
    void customHeaderAndDefaultJsonConverterWorkTogether() {
        RestClient.Builder localBuilder = bootBuilder.clone()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(localBuilder).build();

        server.expect(requestTo(
                    "https://catalog.example.test/items/42"))
                .andExpect(header("X-App-Client", "study-service"))
                .andRespond(withSuccess(
                        "{\"id\":42,\"name\":\"Pencil\"}",
                        MediaType.APPLICATION_JSON));

        ClientCustomizationApplication.CatalogClient client =
                new ClientCustomizationApplication.CatalogClient(
                        localBuilder.build());

        ClientCustomizationApplication.CatalogClient.Item item =
                client.find(42);

        assertThat(item).isEqualTo(
                new ClientCustomizationApplication.CatalogClient.Item(
                        42, "Pencil"));

        server.verify();
    }
}
~~~

Chạy trong thư mục dự án:

~~~bash
mvn test -Dtest=ClientCustomizationTests
~~~

Hoặc nếu dự án có Maven Wrapper:

~~~bash
./mvnw test -Dtest=ClientCustomizationTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=ClientCustomizationTests'
~~~

**Kết quả kỳ vọng:** test PASS. Mock server xác minh:
1. Client thực sự gọi URL đã thiết lập trên builder.
2. Request chứa header chung do `RestClientCustomizer` bổ sung.
3. JSON `{"id":42,"name":"Pencil"}` được chuyển thành record `Item` nhờ converter phù hợp, thay vì cần tự tạo mapper/converter bằng tay.

Test **không truy cập mạng thật**: `MockRestServiceServer.bindTo(localBuilder)` cài một request factory thử nghiệm vào builder cụ thể trước khi gọi `build()`. Kết quả không phụ thuộc việc domain ví dụ có tồn tại.

Một số log Spring Boot/Maven vẫn xuất hiện; bài học chỉ khẳng định test được kỳ vọng PASS, không bịa một đoạn stdout hoàn toàn cố định.

## 6. Builder do Boot cấp khác gì tự gọi builder()?

Giả sử có hai cách tạo client:

~~~java
// Cách A: dùng RestClient.Builder được Spring Boot inject.
CatalogClient createUsingBoot(RestClient.Builder bootBuilder) {
    return new CatalogClient(
            bootBuilder.baseUrl("https://catalog.example.test").build());
}

// Cách B: khởi tạo builder trực tiếp bằng Spring Framework.
CatalogClient createDirectly() {
    return new CatalogClient(
            RestClient.builder()
                    .baseUrl("https://catalog.example.test")
                    .build());
}
~~~

Đoạn trên là **minh họa**, giả định `CatalogClient` đã được import và hai phương thức nằm trong một class phù hợp.

**Cách A** kế thừa tùy chỉnh của Spring Boot. **Cách B** vẫn sử dụng các mặc định nội tại của Spring Framework, nhưng **không tự động kế thừa mọi cấu hình mà Boot đã bổ sung cho bean builder**, bao gồm các bean `RestClientCustomizer` của ứng dụng. Điều tương tự áp dụng với `RestClient.create()` khi không đi qua builder auto-configured.

Một số mặc định của Boot có thể bao gồm:
- `HttpMessageConverters` tích hợp với cấu hình của ứng dụng;
- `ClientHttpRequestFactory` phù hợp thư viện HTTP trong classpath;
- Customizer do ứng dụng hoặc integration của Boot đóng góp;
- Tích hợp observation/SSL khi module tương ứng khả dụng và được cấu hình.

Không khẳng định **mọi** hạng mục đều xuất hiện trong mọi dự án; điều đó phụ thuộc dependencies, điều kiện và cấu hình.

### Builder có trạng thái hay bất biến?

Đây là khác biệt dễ gây lỗi:

| Builder | Đặc tính quan trọng | Cách sử dụng an toàn |
| --- | --- | --- |
| `RestClient.Builder` | Có trạng thái; các lời gọi setter thay đổi builder | Dùng bản mới được inject hoặc `clone()` nếu cần nhiều cấu hình |
| `WebClient.Builder` | Có trạng thái tương tự | Sử dụng builder của Boot và `clone()` khi tạo nhiều biến thể |
| `RestTemplateBuilder` (Boot) | Phần lớn các phương thức cấu hình trả builder **mới** | Giữ lại giá trị trả về của lời gọi |

Ví dụ với `RestClient.Builder`:

~~~java
// Minh họa hai biến thể; bootBuilder là bean đã được inject.
RestClient orders = bootBuilder.clone()
        .baseUrl("https://orders.example.test")
        .build();

RestClient billing = bootBuilder.clone()
        .baseUrl("https://billing.example.test")
        .build();
~~~

Nếu thay đổi liên tục **cùng một** builder stateful rồi `build()`, các cấu hình có thể tích lũy và gây ảnh hưởng ngoài dự kiến. Clone giúp mỗi client có cấu hình riêng trong khi vẫn xuất phát từ defaults giống nhau.

## 7. Customizer toàn cục và tùy chỉnh cục bộ

Có ba phạm vi cần phân biệt:

**Cục bộ ở điểm sử dụng**:

~~~java
@Bean
CatalogClient catalogClient(RestClient.Builder builder) {
    RestClient client = builder
            .baseUrl("https://catalog.example.test")
            .defaultHeader("X-Catalog-Version", "v1")
            .build();
    return new CatalogClient(client);
}
~~~

Đây là đoạn minh họa khi `CatalogClient` đã được định nghĩa; khai báo trên một class cấu hình. Header catalog chỉ là quyết định của client được tạo từ builder này.

**Dùng chung cho các RestClient.Builder auto-configured**:

~~~java
@Bean
RestClientCustomizer complianceHeader() {
    return builder ->
            builder.defaultHeader("X-Client-Family", "internal");
}
~~~

Khi một `RestClient.Builder` đến từ Boot, callback được áp dụng; các builder mới mà framework tạo vẫn có thể nhận cùng chính sách này.

**Thay thế toàn bộ builder**:

~~~java
@Bean
RestClient.Builder restClientBuilder() {
    return RestClient.builder();
}
~~~

Đoạn cuối có rủi ro: một bean `RestClient.Builder` do người dùng cung cấp có thể khiến auto-configuration **back off**. Bạn có builder hoạt động, nhưng các customizer và mặc định của Boot có thể không còn được đưa vào theo cách thường thấy. Trong phần 9 sẽ có cách dùng `RestClientBuilderConfigurer` nếu thật sự phải tạo bean builder riêng.

**Quy tắc thiết kế:** phần thay đổi chỉ phục vụ một service thì giữ ở builder cục bộ; phần cấu hình có tính toàn ứng dụng thì dùng customizer phù hợp. Đừng đặt base URL của riêng một đối tác vào customizer toàn cục trừ khi thật sự mọi client đều dùng cùng đích.

## 8. Tùy chỉnh kiểu RestTemplateBuilder và RestTemplateCustomizer

Trong Spring Boot 3.5, `RestTemplate` vẫn được hỗ trợ cho ứng dụng blocking. Boot auto-configure **`RestTemplateBuilder`**, không nhất thiết tạo sẵn một singleton `RestTemplate` cho mọi ứng dụng.

Ví dụ cục bộ:

~~~java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

// Đoạn minh họa trong một service hoặc @Bean.
RestTemplate makePartnerTemplate(RestTemplateBuilder bootBuilder) {
    return bootBuilder
            .rootUri("https://partner.example.test")
            .connectTimeout(Duration.ofSeconds(3))
            .readTimeout(Duration.ofSeconds(5))
            .build();
}
~~~

Các phương thức như `rootUri`, `connectTimeout`, `readTimeout` trả về một `RestTemplateBuilder` mới. Viết `bootBuilder.connectTimeout(...);` rồi bỏ qua giá trị trả về có thể khiến cấu hình không được áp dụng vào `build()` của biến ban đầu.

### Dùng RestTemplateCustomizer

~~~java
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestInterceptor;

// Trong một lớp @Configuration.
@Bean
RestTemplateCustomizer addTrackingHeader() {
    ClientHttpRequestInterceptor interceptor =
            (request, body, execution) -> {
                request.getHeaders().add("X-Tracking", "training");
                return execution.execute(request, body);
            };

    return template -> template.getInterceptors().add(interceptor);
}
~~~

Bean `RestTemplateCustomizer` này có thể được áp dụng cho các `RestTemplate` được tạo bởi **`RestTemplateBuilder` do Boot auto-configure**. Nó bổ sung interceptor vào danh sách hiện có; thay toàn bộ danh sách có thể làm mất interceptor mà thư viện khác đã cài.

Mỗi customizer có mục đích/kiểu đối tượng cụ thể:
- `RestClientCustomizer` nhận `RestClient.Builder`;
- `RestTemplateCustomizer` nhận `RestTemplate`;
- `Jackson2ObjectMapperBuilderCustomizer` nhận `Jackson2ObjectMapperBuilder`;
- `WebClientCustomizer` nhận `WebClient.Builder` nếu dùng WebFlux.

Không thay `RestClientCustomizer` bằng `RestTemplateCustomizer` và trông đợi nó tự ảnh hưởng tới `RestClient`.

## 9. Khi cần tự cung cấp builder: dùng Configurer để giữ defaults

Trường hợp hiếm hơn: module của bạn yêu cầu **tự đăng ký bean `RestClient.Builder`**. Lúc này đừng chỉ viết `RestClient.builder()` rồi kết luận đã kế thừa cấu hình Spring Boot.

Với Spring Boot 3.5, dùng **`RestClientBuilderConfigurer`**:

~~~java
package example;

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
                .defaultHeader("X-Provided-Builder", "custom");
    }
}
~~~

Đây là một **lựa chọn cấu hình thay thế** cho bean builder mặc định, không đưa đồng thời vào dự án mẫu mục 5 nếu chưa có nhu cầu thay thế.

Tại sao:
1. `configurer.configure(RestClient.builder())` dùng bộ configurer của Boot để thiết lập defaults cho builder mới.
2. `defaultHeader(...)` thêm thay đổi của ứng dụng sau bước đó.
3. `@Scope(SCOPE_PROTOTYPE)` giữ ý tưởng cấp builder mới cho từng điểm yêu cầu từ container, gần với hành vi prototype mà Boot dùng cho `RestClient.Builder`.

**Không suy ra `@Scope("prototype")` làm builder hoàn toàn immutable:** bản thân builder vẫn stateful. Không nên cho nhiều luồng chia sẻ cùng một instance builder có chỉnh sửa đồng thời.

Ví dụ tương đương cho `RestTemplateBuilder`:

~~~java
import java.time.Duration;

import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;

// Đặt phương thức trong một lớp cấu hình Spring.
@Bean
RestTemplateBuilder restTemplateBuilder(
        RestTemplateBuilderConfigurer configurer) {

    return configurer.configure(new RestTemplateBuilder())
            .connectTimeout(Duration.ofSeconds(3))
            .readTimeout(Duration.ofSeconds(5));
}
~~~

Configurer giúp áp dụng các mặc định và customizer của Boot trước khi chỉnh timeout. Với `RestTemplateBuilder` thì mỗi phép cấu hình trả về builder mới và cần `return` builder đó.

**Ghi nhớ:** tên package của configurer/builder đã đổi ở Spring Boot 4.x, chẳng hạn `RestClientBuilderConfigurer` thuộc `org.springframework.boot.restclient.autoconfigure` ở dòng mới. Không copy import của 3.5 sang 4.x một cách máy móc.

## 10. Tùy chỉnh Jackson JSON: ví dụ Customizer khác

Nếu dự án Spring Boot 3.5 dùng Jackson 2 qua starter web, `Jackson2ObjectMapperBuilderCustomizer` là extension point để chỉnh `ObjectMapper` được xây qua builder của Boot.

Ví dụ loại bỏ field null khi serialize JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;

// Đặt trong @Configuration hoặc @SpringBootApplication.
@Bean
Jackson2ObjectMapperBuilderCustomizer omitNullJsonProperties() {
    return builder ->
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
}
~~~

Khi `JacksonAutoConfiguration` sử dụng `Jackson2ObjectMapperBuilder` do Boot cấu hình, callback tác động vào mapper được tạo từ builder ấy. Ứng dụng vẫn có thể kế thừa các thiết lập khác của Boot, ví dụ module được đăng ký và các `spring.jackson.*` property phù hợp.

Nếu chỉ cần điều chỉnh một tính năng mà Boot đã có property hỗ trợ, có thể dùng:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

Property là lựa chọn phù hợp cho cấu hình tĩnh; customizer hữu ích khi phải điều chỉnh thêm logic hoặc tùy chọn Java không tiện mô tả qua property.

**Phản ví dụ:**

~~~java
// Minh họa cách thay bean trực tiếp; KHÔNG phải cách được khuyên
// khi mục tiêu là giữ đầy đủ defaults của Boot.
@Bean
com.fasterxml.jackson.databind.ObjectMapper objectMapper() {
    return new com.fasterxml.jackson.databind.ObjectMapper();
}
~~~

Khi tự định nghĩa `ObjectMapper`, auto-configuration có thể không tạo mapper mặc định do `@ConditionalOnMissingBean`. Mapper tự tạo có thể thiếu module hoặc cấu hình mặc định của Boot. Nếu cần thay thế thật sự, phải có chủ đích xử lý lại các phần tích hợp liên quan.

**Phân biệt phiên bản:** Spring Boot 4.x mặc định ưu tiên Jackson 3 và `JsonMapper`; Jackson 2 ở dòng 4.x là hướng tương thích/migration. Extension point Jackson 2 kể trên được minh họa cho **Boot 3.5**, không dùng như lời khuyên mặc định cho mọi phiên bản mới.

## 11. Tùy chỉnh có điều kiện trong starter/auto-configuration của riêng bạn

Thư viện Spring Boot starter nên đóng góp bean khi thực sự cần, đồng thời cho phép ứng dụng ghi đè. Ví dụ phác thảo cho thư viện cung cấp client API danh mục:

~~~java
// Đoạn minh họa áp dụng với Spring Boot 3.5;
// giả định CatalogClient là kiểu public đã định nghĩa riêng.
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.web.client.RestClientAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@AutoConfiguration(after = RestClientAutoConfiguration.class)
@ConditionalOnClass(RestClient.class)
class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnBean(RestClient.Builder.class)
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(RestClient.Builder builder) {
        return new CatalogClient(
                builder.baseUrl("https://catalog.example.test").build());
    }
}
~~~

Ý nghĩa:
- `@AutoConfiguration(after=...)` đưa cấu hình này về sau auto-configuration cấp builder để hỗ trợ đánh giá điều kiện theo thứ tự bean definitions.
- `@ConditionalOnClass` tránh áp dụng khi API không có trên classpath.
- `@ConditionalOnBean(RestClient.Builder.class)` chỉ tạo client khi builder phù hợp có sẵn.
- `@ConditionalOnMissingBean(CatalogClient.class)` cho phép người dùng cung cấp client riêng và để thư viện **back off**.
- Chính client trong starter lấy builder đã được Boot cấu hình, nhờ vậy tiếp tục nhận các customizer của ứng dụng.

Trong starter thật, cần đăng ký FQCN của lớp auto-configuration ở `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Không phải mọi extension point đều cần một starter: ở ứng dụng thông thường, chỉ cần `@Bean` customizer trong class `@Configuration` đã thuộc component scan.

**Tránh thứ tự sai:** điều kiện `@ConditionalOnBean` nhạy với bean definitions có mặt tại lúc đánh giá. Đối với auto-configuration phụ thuộc builder của Boot, chỉ rõ thứ tự hoặc thiết kế điều kiện theo tài liệu tương ứng.

## 12. Thứ tự nhiều customizer và nguy cơ ghi đè

Giả sử có hai customizer cùng sửa một header, timeout hay một object mapper setting. Kết quả cuối có thể phụ thuộc thứ tự áp dụng hoặc việc API **thêm**, **thay thế** hay **hợp nhất** dữ liệu.

Thực hành tốt:
1. Dùng các thao tác bổ sung khi phù hợp, ví dụ thêm interceptor/header, thay vì đặt lại toàn bộ collection.
2. Nếu thứ tự là yêu cầu nghiệp vụ, sử dụng `@Order` hoặc `Ordered` khi extension point đó hỗ trợ sắp xếp. Kiểm tra Javadoc/source của đúng Boot version.
3. Kiểm thử sự tương tác giữa customizer của ứng dụng và thư viện như metrics/tracing/logging.
4. Tránh customizer đọc trạng thái mutable dùng chung rồi sửa không đồng bộ.
5. Đừng giả định thứ tự đăng ký `@Bean` trong source code chính là thứ tự callback.
6. Với cấu hình nhạy cảm như Authorization, đừng log toàn bộ header chứa token, cookie hoặc dữ liệu người dùng.

Ví dụ một customizer đặt header thường:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
@Order(100)
RestClientCustomizer commonHeader() {
    return builder ->
            builder.defaultHeader("X-Client-Group", "internal");
}
~~~

Đây là ví dụ dùng annotation để **khai báo thứ tự mong muốn**; cần kiểm tra thứ tự xử lý thực tế nếu các customizer khác cũng đụng đúng `X-Client-Group`. Giá trị `@Order` nhỏ hơn thông thường có độ ưu tiên cao hơn khi danh sách được sắp tăng, nhưng không nên suy đoán cơ chế merge/override header nếu chưa kiểm thử.

## 13. Cách kiểm tra defaults còn được giữ

Kiểm tra ít nhất hai tầng:

### Tầng hành vi

- **HTTP:** request có header do customizer thêm không?
- **JSON:** response JSON có được deserialize thành DTO không?
- **Tùy chỉnh cục bộ:** client A dùng URL/timeout riêng và client B không bị thay nhầm?
- **Tính mở rộng:** khi thêm customizer thứ hai, phần đã chạy trước đó còn hoạt động?
- **Không gọi mạng trong unit test:** dùng `MockRestServiceServer`, tránh phụ thuộc dịch vụ thật.
- **Lỗi cấu hình:** thử thiếu classpath dependency hoặc tắt auto-configuration để xác nhận bean được bảo vệ bằng condition phù hợp.

### Tầng metadata/diagnostics

Dùng `--debug` khi chạy Spring Boot:

~~~bash
java -jar target/customizer-demo-1.0.0.jar --debug
~~~

`Condition Evaluation Report` giúp kiểm tra auto-configuration nào match hoặc back off. Nếu tích hợp Spring Boot Actuator và expose endpoint phù hợp, `/actuator/conditions` cũng có thể hỗ trợ chẩn đoán. Không nhầm **condition match** với bằng chứng các customizer đã thật sự được áp dụng: phần sau nên xác nhận bằng test hành vi.

Khi nghi mất defaults sau khi tự định nghĩa builder, xem:
- Có bean `RestClient.Builder`/`RestTemplateBuilder` do người dùng tạo đang thay thế bean mặc định không?
- Builder có đi qua `RestClientBuilderConfigurer`/`RestTemplateBuilderConfigurer` không?
- Bạn có vô tình dùng `RestClient.create()` hoặc `RestClient.builder()` ngoài auto-config không?
- Customizer có nằm trong Spring context không?
- Có customizer phía sau ghi đè cùng setting không?

## 14. Lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `RestClientCustomizer` không thấy hiệu lực | Tạo client bằng `RestClient.create()` hay builder tự tạo | Inject builder của Boot hoặc dùng configurer |
| Header chung chỉ có ở một client | Header được đặt cục bộ | Tạo bean `RestClientCustomizer` nếu muốn toàn cục |
| Hai client có chung base URL ngoài ý muốn | Sử dụng lại builder stateful đã đổi | Inject builder mới hoặc `clone()` cho mỗi biến thể |
| `RestTemplateBuilder` không nhận timeout | Bỏ qua giá trị builder được trả về | Gán/lưu/return builder mới |
| JSON mapping thiếu module | Tự tạo `ObjectMapper` không qua auto-config | Dùng property, Jackson builder customizer hoặc cấu hình mapper đầy đủ |
| Khai báo bean builder rồi mất defaults | Auto-config back off hoặc builder riêng thiếu configurer | Dùng `RestClientBuilderConfigurer`/`RestTemplateBuilderConfigurer` |
| Customizer ảnh hưởng mọi HTTP client nhưng chỉ muốn một đối tác | Phạm vi callback toàn cục quá rộng | Chuyển cấu hình vào builder tại điểm sử dụng |
| Đặt nhiều customizer đè cùng key | Thứ tự hoặc semantics setter không rõ | Phân định trách nhiệm, dùng ordering khi được hỗ trợ và thêm test |
| Copy package Boot 3.5 sang Boot 4 | API đã đổi gói/tên hoặc JSON stack khác | Tra Javadoc cho đúng dòng version |
| Tưởng customizer tự động tác động đến bean tạo thủ công | Không có đoạn code nào thu thập/gọi customizer | Chọn builder được Boot cấp hoặc gọi configurer thích hợp |

## 15. Bài tập thực hành

**Bài tập 1 – Tùy chỉnh cục bộ:** Thêm client thứ hai gọi `https://billing.example.test`. Dùng `bootBuilder.clone()` và đặt header `X-Partner: billing`. Kiểm chứng header này không bị đưa vào client danh mục.

**Bài tập 2 – Tùy chỉnh toàn cục:** Thêm một `RestClientCustomizer` chỉ đặt `X-Trace-Demo: enabled`. Kiểm tra bằng `MockRestServiceServer` rằng client danh mục vẫn parse JSON đúng và nhận cả hai header chung.

**Bài tập 3 – Mất defaults:** Tạm xây `RestClient` bằng `RestClient.create()` trong một test độc lập. Quan sát rằng header của `RestClientCustomizer` không tự xuất hiện. Giải thích sự khác nhau giữa mặc định Spring Framework và cấu hình bổ sung bởi Spring Boot.

**Bài tập 4 – Configurer:** Tạo cấu hình builder riêng theo mục 9 và xác minh test header/JSON còn PASS. Chỉ dùng một phương án cấp bean builder tại một thời điểm để tránh những bean cạnh tranh ngoài dự kiến.

**Bài tập 5 – JSON:** Thêm `Jackson2ObjectMapperBuilderCustomizer` cấu hình bỏ qua null; serialize một record có thuộc tính nullable và đối chiếu kết quả trước/sau.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Spring Boot đã auto-configure `RestClient.Builder`. Muốn mỗi client dùng base URL khác nhau nhưng giữ converter mặc định, nên làm gì?

**Đáp án:** Inject builder được Boot cung cấp, dùng `baseUrl(...)` cục bộ và gọi `build()`. Nếu tạo nhiều biến thể từ cùng builder stateful, cân nhắc `clone()`.

**Câu 2.** Khi nào dùng `RestClientCustomizer`?

**Đáp án:** Khi muốn thêm một thay đổi dùng chung cho các `RestClient.Builder` mà Spring Boot xử lý, ví dụ header chung hoặc interceptor dùng chung, và muốn giữ cấu hình nền.

**Câu 3.** Tại sao `new ObjectMapper()` có thể làm mất hành vi mặc định?

**Đáp án:** Vì đối tượng được tạo trực tiếp không tự hưởng những module, property và customizer được auto-configuration gắn vào mapper của Boot.

**Câu 4.** Khi tự cấp bean `RestClient.Builder` thì cần làm gì để giữ defaults?

**Đáp án:** Dùng `RestClientBuilderConfigurer.configure(RestClient.builder())` rồi bổ sung phần cần thay đổi. Cân nhắc `prototype` khi cần hành vi cấp builder riêng như Boot mặc định.

**Câu 5.** `RestClient.Builder` và `RestTemplateBuilder` có cùng semantics không?

**Đáp án:** Không. `RestClient.Builder` có trạng thái và được mutate, còn `RestTemplateBuilder` theo phong cách trả một instance builder mới khi cấu hình.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Calling REST Services (RestClient, WebClient, RestTemplate customization): https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Boot 3.5 API — RestClientAutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
- Spring Boot 3.5 API — RestClientCustomizer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 API — RestClientBuilderConfigurer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientBuilderConfigurer.html
- Spring Boot 3.5 API — RestTemplateBuilderConfigurer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestTemplateBuilderConfigurer.html
- Spring Boot 3.5 API — Jackson2ObjectMapperBuilderCustomizer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html
- Spring Framework 6.2 API — MockRestServiceServer: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html
