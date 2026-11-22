# Ứng dụng nền tảng có Commons, Context và Actuator tối thiểu

> **Chương:** Thực hành tổng hợp  
> **Module:** SPRING_CLOUD_CORE

Bài thực hành xây dựng một ứng dụng Spring Boot nhỏ để ghép ba phần nền tảng của Spring Cloud: **Commons** cung cấp abstraction discovery và thông tin feature, **Context** quản lý cấu hình có thể làm mới, còn **Actuator** cung cấp endpoint quan sát và thao tác quản trị. Ứng dụng có một REST API trả lời lời chào từ cấu hình, một API đọc danh sách instance tĩnh qua `DiscoveryClient`, một bean `@RefreshScope` và bộ endpoint phục vụ kiểm tra.

Ta dùng `SimpleDiscoveryClient` để chạy bài tập mà không cần dựng Eureka hoặc Consul. Cấu hình mẫu có một instance `catalog-provider` với URI `http://localhost:8091`; việc đọc danh sách này không gọi mạng tới cổng 8091. Mục tiêu là kiểm tra abstraction và metadata discovery. Khi cần đăng ký động, health-aware discovery hoặc load balancing, có thể thay implementation bằng provider tương ứng.

Dự án dùng cặp phiên bản GA tương thích tại thời điểm biên soạn: Spring Boot **4.1.2**, Spring Cloud **2025.1.4** và Java **17 trở lên**. Spring Cloud 2025.1.x hỗ trợ Boot 4.0.x và Boot 4.1.x từ 2025.1.2. Khi thực hiện trên thời điểm khác, hãy chọn cặp phiên bản từ ma trận compatibility chính thức thay vì tự ghép hai phiên bản độc lập.

## 1. Kết quả cần đạt

Sau khi hoàn thành, ứng dụng có các khả năng:

| Thành phần | Việc thực hiện | Bằng chứng kiểm tra |
| --- | --- | --- |
| Spring Cloud Commons | Inject DiscoveryClient, đọc service và instance | GET /api/platform/discovery |
| SimpleDiscoveryClient | Đọc instance từ cấu hình tĩnh | Có catalog-provider trong response |
| Features endpoint | Khai báo và quan sát feature của ứng dụng | GET /actuator/features |
| Spring Cloud Context | Dùng @RefreshScope cho service đọc cấu hình | Greeting thay đổi sau refresh |
| @ConfigurationProperties | Bind cấu hình có kiểu Duration | GET /actuator/configprops |
| Spring Boot Actuator | Kiểm tra health và cấu hình | GET /actuator/health |
| Kiểm thử tích hợp | Kiểm tra API, discovery và refresh | mvn test |

Luồng chính:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["GreetingController"]
    B --> C["GreetingService"]
    C --> D["RefreshScope proxy"]
    D --> E["CatalogProperties"]
    E --> F["Environment"]

    G["DiscoveryController"] --> H["DiscoveryClient"]
    H --> I["SimpleDiscoveryClient"]
    I --> J["Static instance properties"]

    K["Actuator"] --> L["health / features / configprops"]
    K --> M["refresh"]
    M --> D
    M --> E
~~~

## 2. Tạo project và quản lý phiên bản

Tạo một Maven project với cấu trúc sau:

~~~text
platform-core-lab/
├── pom.xml
├── config/
│   └── lab-overrides.yml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/platform/
    │   │       ├── PlatformCoreLabApplication.java
    │   │       ├── config/
    │   │       │   ├── CatalogProperties.java
    │   │       │   └── FeatureConfiguration.java
    │   │       ├── service/
    │   │       │   └── GreetingService.java
    │   │       └── web/
    │   │           ├── GreetingController.java
    │   │           └── DiscoveryController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-lab.yml
    └── test/
        └── java/
            └── com/example/platform/
                └── PlatformCoreLabApplicationTest.java
~~~

### 2.1. POM với Spring Cloud BOM

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>platform-core-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>platform-core-lab</name>
    <description>Spring Cloud Commons, Context and Actuator lab</description>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.4</spring-cloud.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-commons</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-context</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

Các dependency được chọn theo vai trò:

- `spring-cloud-commons`: DiscoveryClient, ServiceInstance, HasFeatures, SimpleDiscoveryClient và Features Actuator endpoint.
- `spring-cloud-context`: @RefreshScope, RefreshScope và các cơ chế cập nhật Environment/rebind.
- `spring-boot-starter-actuator`: Health, Environment, Configuration Properties và các endpoint quản trị của Spring Boot.
- `spring-boot-starter-webmvc`: REST controller chạy trên Spring MVC.
- `spring-boot-starter-webmvc-test`: công cụ kiểm thử MVC trong Spring Boot 4.

Spring Cloud BOM quản lý phiên bản các module Cloud cùng release train. Không khai báo version riêng cho spring-cloud-commons hoặc spring-cloud-context nếu BOM đã quản lý chúng.

Nếu dự án hiện tại đang dùng Spring Boot 3.5.x, chọn Spring Cloud 2025.0.x tương ứng và dùng starter web/test mà phiên bản Boot đó hỗ trợ. Không trộn dependency từ ví dụ Boot 4 vào một project Boot 3 mà chưa điều chỉnh.

## 3. Tạo ứng dụng Spring Boot

Tạo file src/main/java/com/example/platform/PlatformCoreLabApplication.java:

~~~java
package com.example.platform;

import com.example.platform.config.CatalogProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CatalogProperties.class)
public class PlatformCoreLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlatformCoreLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kích hoạt component scanning và auto-configuration. `@EnableConfigurationProperties` đăng ký bean `CatalogProperties` để Spring Boot bind các giá trị có prefix `catalog`.

Trong bài này không cần `@EnableDiscoveryClient` để tạo một registry cụ thể. Khi không có implementation discovery dựa trên registry trong classpath, Spring Cloud Commons có thể cung cấp `SimpleDiscoveryClient` từ cấu hình tĩnh. Nếu thêm Eureka hoặc Consul sau này, provider sẽ cung cấp implementation tương ứng.

## 4. Khai báo cấu hình có kiểu bằng ConfigurationProperties

Tạo file src/main/java/com/example/platform/config/CatalogProperties.java:

~~~java
package com.example.platform.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String greeting;
    private Duration timeout = Duration.ofSeconds(2);

    public String getGreeting() {
        return greeting;
    }

    public void setGreeting(String greeting) {
        this.greeting = greeting;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Class này dùng JavaBean binding với getter/setter. `Duration` giúp ứng dụng biểu diễn timeout bằng kiểu thời gian thay vì giữ chuỗi tự do. Cách binding mutable này phù hợp để minh họa quá trình rebind của Spring Cloud Context.

Không dùng constructor binding hoặc Java Record cho bean cần refresh trong bài tập này. Các object dùng constructor binding, bao gồm Java Record được đánh dấu `@ConfigurationProperties`, không được refresh theo cơ chế rebind thông thường của Spring Cloud Context.

## 5. Tạo service có RefreshScope

Tạo file src/main/java/com/example/platform/service/GreetingService.java:

~~~java
package com.example.platform.service;

import java.time.Duration;

import com.example.platform.config.CatalogProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Service;

@Service
@RefreshScope
public class GreetingService {

    private final String greeting;
    private final Duration timeout;

    public GreetingService(CatalogProperties properties) {
        this.greeting = properties.getGreeting();
        this.timeout = properties.getTimeout();
    }

    public GreetingResponse currentGreeting() {
        return new GreetingResponse(greeting, timeout.toString());
    }

    public record GreetingResponse(String message, String timeout) {
    }
}
~~~

`@RefreshScope` tạo một proxy cho bean. Khi refresh, Spring Cloud xóa target bean đã cache; lần gọi tiếp theo sẽ khởi tạo target mới. `CatalogProperties` được rebind theo Environment trước khi service target mới được sử dụng.

Trong ví dụ, service chụp greeting và timeout vào field ngay lúc constructor chạy. Vì vậy, chỉ rebind `CatalogProperties` chưa làm target đang cache thay đổi snapshot. Sau khi refresh scope bị xóa, lần gọi tiếp theo tạo target mới và đọc các giá trị đã cập nhật. Cách này giúp nhìn thấy rõ tác dụng của `@RefreshScope` trong bài thực hành.

Ở đây chỉ `GreetingService` được đưa vào refresh scope. Không nên đánh dấu tất cả bean trong ứng dụng là refreshable. Chỉ chọn bean có cấu hình thay đổi lúc chạy và có lifecycle khởi tạo lại an toàn.

## 6. Tạo REST API đọc cấu hình

Tạo file src/main/java/com/example/platform/web/GreetingController.java:

~~~java
package com.example.platform.web;

import com.example.platform.service.GreetingService;
import com.example.platform.service.GreetingService.GreetingResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public GreetingResponse greeting() {
        return greetingService.currentGreeting();
    }
}
~~~

Controller không đọc trực tiếp Environment. Nó gọi service qua proxy `RefreshScope`, nhờ đó việc thay đổi cấu hình và tái tạo target bean được quản lý tại tầng service.

## 7. Dùng DiscoveryClient để xem instance

Tạo file src/main/java/com/example/platform/web/DiscoveryController.java:

~~~java
package com.example.platform.web;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/platform")
public class DiscoveryController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery")
    public Map<String, List<String>> discoverySnapshot() {
        Map<String, List<String>> result = new TreeMap<>();

        for (String serviceId : discoveryClient.getServices()) {
            List<String> instances = discoveryClient.getInstances(serviceId)
                    .stream()
                    .map(ServiceInstance::getUri)
                    .map(Object::toString)
                    .toList();

            result.put(serviceId, instances);
        }

        return result;
    }
}
~~~

Controller phụ thuộc interface `DiscoveryClient`, không phụ thuộc trực tiếp vào Eureka hoặc Consul. Nó lấy service ID, sau đó đọc danh sách `ServiceInstance` tương ứng và trả về URI.

`DiscoveryClient` là abstraction để truy vấn discovery. Nó không tự thực hiện load balancing và cũng không tự gửi request tới URI. Muốn chọn instance cho request HTTP, cần bổ sung Spring Cloud LoadBalancer hoặc một cơ chế định tuyến khác.

## 8. Khai báo feature cho Features Endpoint

Tạo file src/main/java/com/example/platform/config/FeatureConfiguration.java:

~~~java
package com.example.platform.config;

import com.example.platform.service.GreetingService;
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    HasFeatures discoveryFeature() {
        return HasFeatures.abstractFeatures(DiscoveryClient.class);
    }

    @Bean
    HasFeatures catalogGreetingFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature("Catalog greeting", GreetingService.class));
    }
}
~~~

Spring Cloud Commons cung cấp Features endpoint. Abstract feature dùng interface hoặc abstract class để xác định bean implementation, ví dụ `DiscoveryClient`. Named feature dùng tên và class đại diện cho capability của ứng dụng.

Khai báo `HasFeatures` nên đặt trong cấu hình có điều kiện phù hợp với feature thật. Không khai báo một feature là enabled nếu implementation chưa được tạo hoặc chưa được kích hoạt.

## 9. Cấu hình application.yml

Tạo file src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: platform-core-lab
  cloud:
    features:
      enabled: true
    discovery:
      client:
        simple:
          instances:
            catalog-provider:
              - uri: http://localhost:8091
                metadata:
                  environment: local

catalog:
  greeting: "Xin chào từ cấu hình mặc định"
  timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Cấu hình `spring.cloud.discovery.client.simple.instances` tạo một service ID `catalog-provider` với một instance. Đây là danh sách tĩnh do ứng dụng cung cấp.

Có thể biểu diễn cùng property bằng file application.properties như sau:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-provider[0].uri=http://localhost:8091
~~~

Không cần khởi động service tại cổng 8091 để kiểm tra `DiscoveryClient.getServices()` và `getInstances()`. `SimpleDiscoveryClient` chỉ trả metadata đã cấu hình. Nếu muốn kiểm tra kết nối thật, hãy tạo provider service hoặc thay bằng registry-backed discovery implementation.

### 9.1. Tạo profile lab để thử refresh

Không bật thao tác ghi Environment trong cấu hình mặc định. Tạo riêng file src/main/resources/application-lab.yml:

~~~yaml
server:
  address: 127.0.0.1

spring:
  config:
    import: file:./config/lab-overrides.yml

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - configprops
          - refresh
~~~

Profile `lab` chỉ bind web server vào loopback và import thêm một file cấu hình nằm ngoài classpath. Tạo file `config/lab-overrides.yml` ở thư mục gốc project:

~~~yaml
catalog:
  greeting: "Xin chào từ file lab-overrides"
~~~

Khi chạy profile lab, giá trị trong file này ghi đè greeting mặc định. Trong lúc ứng dụng đang chạy, có thể sửa file rồi gọi `/actuator/refresh`; Config Data refresher sẽ nạp lại các nguồn cấu hình và làm mới bean trong refresh scope.

Đường dẫn file tương đối được phân giải từ working directory. Khi chạy JAR từ thư mục khác, hãy cung cấp đường dẫn phù hợp hoặc cấu hình một location rõ ràng. Đây là cấu hình phục vụ bài tập local. Không dùng profile này trên mạng dùng chung hoặc production; bảo vệ endpoint refresh bằng authentication/authorization và giới hạn management network.

## 10. Chạy ứng dụng

Kiểm tra Java và Maven:

~~~bash
java -version
mvn -version
~~~

Chạy test và build:

~~~bash
mvn clean test
mvn package
~~~

Khởi động profile lab:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=lab
~~~

Nếu ứng dụng khởi động thành công, server lắng nghe tại `127.0.0.1:8080`. Kiểm tra log startup để xác nhận Spring Boot tạo web context, Spring Cloud Context và discovery client.

Có thể xem dependency Spring Cloud thực tế:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

Lệnh này giúp kiểm tra Commons và Context được đưa vào runtime classpath, đồng thời phát hiện phiên bản transitive không như dự kiến.

## 11. Kiểm tra các API của ứng dụng

### 11.1. Đọc lời chào

Gửi request:

~~~bash
curl http://127.0.0.1:8080/api/catalog/greeting
~~~

Kết quả mong đợi:

~~~json
{
  "message": "Xin chào từ cấu hình mặc định",
  "timeout": "PT2S"
}
~~~

`PT2S` là biểu diễn ISO-8601 của `Duration.ofSeconds(2)`.

### 11.2. Đọc danh sách discovery

~~~bash
curl http://127.0.0.1:8080/api/platform/discovery
~~~

Kết quả mong đợi:

~~~json
{
  "catalog-provider": [
    "http://localhost:8091"
  ]
}
~~~

Đây là kết quả từ `SimpleDiscoveryClient`, không phải kết quả đăng ký từ Eureka/Consul và cũng không chứng minh service tại cổng 8091 đang hoạt động.

### 11.3. Kiểm tra Actuator

Health:

~~~bash
curl http://127.0.0.1:8080/actuator/health
~~~

Features:

~~~bash
curl http://127.0.0.1:8080/actuator/features
~~~

Configuration properties:

~~~bash
curl http://127.0.0.1:8080/actuator/configprops
~~~

`features` cho biết feature được khai báo và implementation được nhận diện. `configprops` cho biết các bean `@ConfigurationProperties` và trạng thái binding. Các giá trị nhạy cảm được Actuator sanitization theo mặc định; trong cấu hình lab, `show-values` cũng được đặt rõ thành `never`.

## 12. Thử thay đổi Config Data và refresh bean

Trong profile lab, greeting được import từ file `config/lab-overrides.yml`. Mở file khi ứng dụng đang chạy và đổi nội dung thành:

~~~yaml
catalog:
  greeting: "Xin chào sau refresh"
~~~

Lưu file rồi yêu cầu Spring Cloud Context làm mới Environment và refresh scope:

~~~bash
curl -X POST http://127.0.0.1:8080/actuator/refresh
~~~

Đọc lại API:

~~~bash
curl http://127.0.0.1:8080/api/catalog/greeting
~~~

Kết quả mong đợi:

~~~json
{
  "message": "Xin chào sau refresh",
  "timeout": "PT2S"
}
~~~

Lời chào đã đổi vì Config Data refresher đọc lại file import, `CatalogProperties` nhận giá trị mới và target `GreetingService` được tạo lại qua refresh scope. Endpoint refresh không phải file watcher; thay đổi chỉ được đọc lại khi ta gọi refresh hoặc khi ứng dụng nhận một refresh event phù hợp. Với Config Server hoặc nguồn cấu hình khác, cần cấu hình integration và quy trình phát sự kiện tương ứng.

## 13. Kiểm thử tích hợp bằng MockMvc

Tạo file src/test/java/com/example/platform/PlatformCoreLabApplicationTest.java:

~~~java
package com.example.platform;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features,configprops,refresh",
        "spring.cloud.refresh.additional-property-sources-to-retain=testOverride"
})
@AutoConfigureMockMvc
class PlatformCoreLabApplicationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ConfigurableEnvironment environment;

    @Test
    void returnsGreetingFromConfiguration() throws Exception {
        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Xin chào từ cấu hình mặc định"))
                .andExpect(jsonPath("$.timeout").value("PT2S"));
    }

    @Test
    void exposesConfiguredDiscoveryInstances() throws Exception {
        mockMvc.perform(get("/api/platform/discovery"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("catalog-provider")))
                .andExpect(content().string(containsString("http://localhost:8091")));
    }

    @Test
    void exposesSpringCloudFeatures() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").isArray())
                .andExpect(jsonPath("$.disabled").isArray());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void refreshesScopedServiceFromRetainedPropertySource() throws Exception {
        environment.getPropertySources().addFirst(new MapPropertySource(
                "testOverride",
                Map.of("catalog.greeting", "Xin chào sau refresh")));

        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Xin chào từ cấu hình mặc định"));

        mockMvc.perform(post("/actuator/refresh"))
                .andExpect(status().is2xxSuccessful());

        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Xin chào sau refresh"));
    }
}
~~~

Các test kiểm tra bốn hành vi: binding cấu hình ban đầu, discovery tĩnh, Features endpoint và cập nhật bean qua refresh. `@DirtiesContext` làm Spring Test loại context sau test refresh để thay đổi Environment không ảnh hưởng test khác.

Test refresh thêm một property source có tên `testOverride` vào Environment. Thuộc tính `spring.cloud.refresh.additional-property-sources-to-retain` yêu cầu ContextRefresher giữ nguồn này khi dựng lại Config Data Environment; nhờ vậy test mô phỏng một nguồn cấu hình runtime và kiểm tra được endpoint refresh.

Chạy:

~~~bash
mvn test
~~~

Nếu test refresh nhận 404, kiểm tra `management.endpoints.web.exposure.include` có chứa `refresh` và dependency `spring-cloud-context` đã có trong classpath. Nếu nhận 403, kiểm tra security/CSRF của cấu hình test. Nếu greeting không đổi, xác nhận tên property source `testOverride` trùng với giá trị `spring.cloud.refresh.additional-property-sources-to-retain` và service đang được inject qua proxy `@RefreshScope`.

## 14. Quan sát vòng đời và vai trò của từng module

| Module | Thành phần trong project | Vai trò |
| --- | --- | --- |
| Spring Cloud Commons | DiscoveryClient, ServiceInstance, HasFeatures, SimpleDiscoveryClient | API chung để truy vấn discovery và công bố feature |
| Spring Cloud Context | @RefreshScope, RefreshScope | Quản lý target bean có thể làm mới |
| Spring Boot Configuration | @ConfigurationProperties, Environment | Bind và quản lý giá trị cấu hình |
| Spring Boot Actuator | health, features, configprops, refresh | Quan sát và thao tác quản trị |
| Spring MVC | REST controllers | Cung cấp API thử nghiệm |

Khi một request gọi `/api/catalog/greeting`, controller gọi proxy của `GreetingService`. Proxy lấy target hiện tại từ refresh scope. Target đọc `CatalogProperties`, bean này nhận giá trị được bind từ Environment.

Khi thực hiện refresh, Context làm mới các bean có scope tương ứng. Lần gọi tiếp theo qua proxy tạo target mới. Các bean singleton khác không tự động được tạo lại chỉ vì một bean có `@RefreshScope`.

## 15. Mở rộng sang registry thật

Bài tập dùng `SimpleDiscoveryClient` để tránh yêu cầu hạ tầng ngoài. Khi cần discovery động, có thể thêm provider như Eureka hoặc Consul.

Ví dụ khi chọn Eureka Client:

- Thêm dependency `spring-cloud-starter-netflix-eureka-client` với version do Spring Cloud BOM quản lý.
- Cấu hình URL Eureka Server.
- Bỏ cấu hình `spring.cloud.discovery.client.simple.instances` nếu không còn dùng static discovery.
- Giữ controller phụ thuộc `DiscoveryClient`; không cần viết lại logic đọc instance theo API của provider.

Ví dụ cấu hình client:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~

Đây là phần mở rộng, không thuộc project tối thiểu. Eureka Server phải đang chạy và client cần đăng ký/heartbeat thành công trước khi danh sách instance phản ánh trạng thái động.

Nếu cần client-side load balancing, thêm Spring Cloud LoadBalancer và viết một bài test riêng cho việc chọn instance. `DiscoveryClient` chỉ trả danh sách instance; nó không tự phân phối request.

## 16. Bảo vệ Actuator khi đưa ra ngoài máy local

Trong profile lab, server được bind vào `127.0.0.1` và chỉ expose endpoint refresh cùng các endpoint đọc cần cho bài tập. Không dùng cấu hình này làm mặc định production.

Khi triển khai thật:

- Chỉ expose `health` và các endpoint cần thiết cho vận hành.
- Giữ `configprops` ở chế độ sanitization; chỉ expose `env` nếu có nhu cầu chẩn đoán rõ ràng.
- Không bật thao tác ghi Environment qua Actuator nếu không có quy trình thay đổi cấu hình được kiểm soát.
- Bảo vệ `POST /actuator/refresh` bằng authentication và authorization.
- Đặt management endpoint trên network/port được giới hạn.
- Ghi audit log cho thao tác thay đổi Environment và refresh.
- Không đưa credential vào response, log hoặc feature metadata.

Spring Boot mặc định chỉ expose `health` qua HTTP. Việc một endpoint có trong classpath không đồng nghĩa endpoint đó tự động được mở ra ngoài.

## 17. Tiêu chí hoàn thành

Project được xem là hoàn thành khi:

- [ ] `mvn clean test` chạy thành công.
- [ ] Ứng dụng khởi động với Spring Boot và Spring Cloud BOM tương thích.
- [ ] `GET /api/catalog/greeting` trả greeting và timeout.
- [ ] `GET /api/platform/discovery` hiển thị `catalog-provider`.
- [ ] `GET /actuator/features` trả danh sách enabled/disabled.
- [ ] `GET /actuator/health` trả trạng thái UP.
- [ ] `GET /actuator/configprops` hiển thị bean cấu hình với giá trị đã sanitization.
- [ ] Profile lab import file `config/lab-overrides.yml` từ bên ngoài classpath.
- [ ] Sau khi sửa file và POST refresh, greeting trả giá trị mới.
- [ ] Không expose endpoint ghi cấu hình trên địa chỉ mạng công khai.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được DiscoveryClient | Commons không có implementation hoặc auto-configuration bị loại | Kiểm tra spring-cloud-commons và điều kiện SimpleDiscoveryClient |
| Discovery trả danh sách rỗng | Cấu hình service ID/instance sai prefix hoặc index | Kiểm tra spring.cloud.discovery.client.simple.instances |
| Features endpoint trả 404 | Chưa expose features hoặc feature endpoint bị disable | Kiểm tra exposure và spring.cloud.features.enabled |
| Refresh endpoint trả 404 | Chưa có Spring Cloud Context hoặc chưa expose refresh | Kiểm tra dependency spring-cloud-context và management exposure |
| Greeting không đổi sau refresh | File import không được nạp lại hoặc bean không qua refresh proxy | Kiểm tra `spring.config.import`, đường dẫn file, `@RefreshScope` và log refresh |
| Configprops không hiển thị secret | Actuator đang sanitization | Đây là hành vi bảo vệ mặc định |
| Lỗi compatibility verifier | Boot và Cloud release train không tương thích | Chọn BOM theo ma trận chính thức |
| Discovery URI có nhưng không gọi được | SimpleDiscoveryClient chỉ chứa metadata tĩnh | Khởi động provider service hoặc dùng registry thật |
| Test refresh ảnh hưởng test khác | Context bị giữ lại sau khi thay Environment | Dùng @DirtiesContext hoặc tách test context |

## 19. Bài tập mở rộng

Sau khi hoàn thành project tối thiểu, có thể mở rộng theo từng bước:

1. Thêm Eureka hoặc Consul và thay SimpleDiscoveryClient bằng provider thật.
2. Bổ sung Spring Cloud LoadBalancer để chọn instance từ danh sách discovery.
3. Thêm một health indicator riêng cho dependency mà nghiệp vụ cần.
4. Chuyển greeting sang Config Server và kiểm tra refresh khi remote property thay đổi.
5. Viết test để xác nhận bean singleton không tự tạo lại khi chỉ refresh một bean khác.
6. Thêm Spring Security cho management endpoint và test role được phép POST refresh.
7. Đo số lần khởi tạo target GreetingService trước/sau refresh bằng log hoặc counter test.
8. Thử profile khác nhau và xác nhận @ConfigurationProperties nhận đúng giá trị.

Mỗi phần mở rộng nên có test riêng. Không đưa thêm registry, broker hoặc LoadBalancer vào project ban đầu nếu mục tiêu chỉ là hiểu Commons, Context và Actuator.

## 20. Kết luận

Ứng dụng này ghép ba nền tảng cốt lõi của **SPRING_CLOUD_CORE** trong một project nhỏ: Commons cung cấp `DiscoveryClient` và Features endpoint; Context cung cấp `@RefreshScope` để làm mới bean; Spring Boot Actuator cung cấp health, configprops và các endpoint quản trị. `SimpleDiscoveryClient` giúp kiểm tra discovery mà không cần dựng registry, còn profile lab import file cấu hình ngoài classpath để quan sát Config Data refresh trên máy local.

Khi chuyển sang production, thay discovery tĩnh bằng provider thật nếu cần đăng ký động, bổ sung LoadBalancer nếu cần chọn instance và bảo vệ mọi endpoint quản trị. Giữ BOM tương thích, kiểm thử hành vi refresh và chỉ expose các endpoint thực sự cần thiết.

## Tài liệu tham khảo

- [Spring Cloud Release Trains — Compatibility Matrix](https://spring.io/projects/spring-cloud)
- [Spring Cloud Commons — Common Abstractions and Features Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Context — Refresh Scope and Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
