# Tránh quét package rộng hoặc thực hiện công việc nặng trong lớp cấu hình

## 1. Mục tiêu

Spring Boot tự phát hiện component và tự cấu hình nhiều hạ tầng. Cơ chế này giúp giảm boilerplate, nhưng phạm vi package scan và nội dung của configuration class ảnh hưởng trực tiếp đến quá trình khởi động.

Hai nguồn chi phí cần kiểm soát:

- **Quét package quá rộng:** Spring phải xem xét nhiều class hơn mức cần thiết, tạo thêm candidate, có thể đăng ký bean ngoài ý muốn và làm context khó hiểu.
- **Công việc nặng trong configuration:** constructor, static initializer, factory method hoặc callback khởi tạo có thể gọi mạng, truy vấn database, đọc nhiều file hay chạy phép tính lớn. Các tác vụ đó kéo dài quá trình refresh ApplicationContext và làm startup phụ thuộc vào hệ thống bên ngoài.

Bài học này hướng dẫn cách chọn package scan có giới hạn, tổ chức auto-configuration bằng imports và @Import, giữ factory method nhẹ, trì hoãn khởi tạo bean khi phù hợp, đặt công việc vào đúng giai đoạn lifecycle và đo startup để xác nhận hiệu quả.

Ví dụ sử dụng **Spring Boot 3.5.16, Spring Framework 6.2 và Java 17+**.

## 2. Startup gồm nhiều giai đoạn

Một lần khởi động Spring Boot thường thực hiện các công việc sau:

~~~text
SpringApplication.run(...)
          |
          v
Đọc Environment và Config Data
          |
          v
Phân tích configuration classes
          |
          v
Component scan và tìm auto-configuration candidates
          |
          v
Đánh giá conditions, tạo bean definitions
          |
          v
Khởi tạo singleton beans và dependency graph
          |
          v
Lifecycle callbacks
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent và trạng thái READY
~~~

| Giai đoạn | Chi phí có thể phát sinh | Hướng kiểm soát |
| --- | --- | --- |
| Component scan | Đọc metadata của nhiều class, xử lý nhiều candidate | Thu hẹp base package và filter |
| Configuration parsing | Nhiều lớp cấu hình, import lồng nhau, condition phức tạp | Chia configuration theo chức năng, import tường minh |
| Bean definition | Nhiều bean, nhiều condition và dependency | Chỉ đăng ký bean thật sự cần |
| Bean instantiation | Constructor, factory method, dependency khởi tạo dây chuyền | Giữ factory method nhẹ, dùng lazy/provider có chủ đích |
| Initialization callbacks | @PostConstruct, InitializingBean, SmartInitializingSingleton | Không đặt I/O hoặc tác vụ dài trong callback |
| Runner | Khởi tạo dữ liệu, gọi service ngoài trước khi ứng dụng READY | Đặt timeout, kiểm soát thứ tự và readiness |

Quét package rộng chủ yếu làm tăng công việc phát hiện và xử lý candidate. Constructor hoặc factory method nặng làm tăng thời gian khởi tạo bean. Hai vấn đề có thể cùng xuất hiện nhưng cần xử lý ở đúng giai đoạn.

Không nên tối ưu bằng cảm giác. Hãy ghi nhận thời gian startup, xác định giai đoạn chậm và đo lại sau khi thay đổi.

## 3. Vì sao component scan quá rộng gây tốn kém?

@SpringBootApplication kết hợp cấu hình ứng dụng, auto-configuration và component scan. Nếu không chỉ định package, component scan bắt đầu từ package chứa lớp được đánh dấu và đi xuống các package con.

Ví dụ:

~~~text
com.example.orders
├── OrdersApplication.java
├── web
│   ├── OrderController.java
│   └── HealthController.java
├── service
│   └── OrderService.java
├── persistence
│   └── OrderRepository.java
├── integration
│   └── PaymentGateway.java
└── configuration
    └── OrdersConfiguration.java
~~~

Nếu OrdersApplication nằm trong com.example.orders, phạm vi scan mặc định thường phù hợp với các package con của ứng dụng.

Ngược lại, nếu đặt lớp main ở package rất cao như com, phạm vi scan có thể bao phủ nhiều module hoặc thư viện hơn mức cần thiết.

### 3.1. Tránh default package

Default package là package của class không có khai báo package.

Ví dụ không nên dùng:

~~~java
@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Spring Boot cảnh báo default package có thể khiến các annotation như @ComponentScan, @ConfigurationPropertiesScan, @EntityScan và @SpringBootApplication phải đọc class từ mọi JAR trên classpath.

Hãy dùng package theo quy ước tên miền đảo ngược, ví dụ:

~~~java
package com.example.orders;
~~~

### 3.2. Đặt lớp main ở package gốc của ứng dụng

Cấu trúc phổ biến:

~~~text
com.example.orders
├── OrdersApplication.java
├── customer
│   ├── CustomerController.java
│   ├── CustomerService.java
│   └── CustomerRepository.java
└── order
    ├── OrderController.java
    ├── OrderService.java
    └── OrderRepository.java
~~~

Khai báo:

~~~java
package com.example.orders;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Cách này giúp phạm vi scan mặc định bao phủ package ứng dụng mà không cần liệt kê từng package con.

## 4. Giới hạn component scan bằng marker class

Khi ứng dụng có nhiều module và chỉ muốn scan một số package, dùng thuộc tính scanBasePackageClasses.

~~~java
package com.example.orders;

import com.example.orders.application.ApplicationComponents;
import com.example.orders.web.WebComponents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
        scanBasePackageClasses = {
                ApplicationComponents.class,
                WebComponents.class
        })
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Tạo marker class trong từng package:

~~~java
package com.example.orders.application;

public final class ApplicationComponents {

    private ApplicationComponents() {
    }
}
~~~

~~~java
package com.example.orders.web;

public final class WebComponents {

    private WebComponents() {
    }
}
~~~

Spring scan package chứa các marker class và các package con của chúng.

Lợi ích:
- Type-safe: IDE/compiler hỗ trợ khi refactor package.
- Không phải ghi package name dưới dạng chuỗi.
- Dễ nhìn ra package nào được scan.
- Marker class không cần chứa logic nghiệp vụ.

### 4.1. scanBasePackageClasses chỉ điều khiển component scan

scanBasePackageClasses là alias cho base package của @ComponentScan. Nó không tự điều khiển việc tìm JPA entity hoặc Spring Data repository.

Nếu package entity và repository nằm ngoài phạm vi mặc định, cấu hình riêng:

~~~java
@SpringBootApplication(
        scanBasePackageClasses = {
                ApplicationComponents.class,
                WebComponents.class
        })
@EntityScan(basePackageClasses = OrderEntityMarker.class)
@EnableJpaRepositories(basePackageClasses = OrderRepositoryMarker.class)
public class OrdersApplication {
}
~~~

| Annotation | Phạm vi |
| --- | --- |
| @ComponentScan | Component như @Component, @Service, @Controller, @Configuration |
| @EntityScan | JPA entity packages |
| @EnableJpaRepositories | Spring Data JPA repository packages |

Đừng mở rộng component scan chỉ để tìm entity hoặc repository. Hãy dùng đúng cơ chế dành cho từng loại.

## 5. Auto-configuration không cần component scan package thư viện

Auto-configuration của Spring Boot được phát hiện bằng imports riêng. Trong Spring Boot 3.x, thư viện đăng ký auto-configuration trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung:

~~~text
com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

Không cần thêm @ComponentScan("com.example.catalog") chỉ để Spring tìm thấy các lớp cấu hình của thư viện.

Dùng @Import cho các configuration class cần thiết:

~~~java
@AutoConfiguration
@Import({
        CatalogClientConfiguration.class,
        CatalogMetricsConfiguration.class
})
public class CatalogAutoConfiguration {
}
~~~

Mỗi configuration khai báo bean thuộc trách nhiệm của nó:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }
}
~~~

Vì @AutoConfiguration luôn dùng proxyBeanMethods = false, không gọi trực tiếp một @Bean method khác như phương thức Java để lấy bean. Hãy khai báo dependency qua tham số method:

~~~java
@Bean
CatalogService catalogService(CatalogClient catalogClient) {
    return new CatalogService(catalogClient);
}
~~~

### 5.1. Tránh component scan rộng trong starter

Không nên viết:

~~~java
@AutoConfiguration
@ComponentScan("com.example")
public class ExampleAutoConfiguration {
}
~~~

Phạm vi này có thể quét cả component do ứng dụng tiêu thụ sở hữu, tạo bean trùng hoặc kéo cấu hình không liên quan vào context.

Nếu auto-configuration cần một vài cấu hình nội bộ, dùng @Import. Nếu integration chỉ cần khi classpath có thư viện tương ứng, cô lập bằng nested configuration và condition:

~~~java
@AutoConfiguration
public class ExampleAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ExampleTransport.class)
    static class TransportConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ExampleTransport exampleTransport() {
            return new ExampleTransport();
        }
    }
}
~~~

Không để class tùy chọn bị tham chiếu trực tiếp trong configuration không có condition bảo vệ nếu dependency đó có thể vắng mặt.

## 6. Configuration class nên khai báo cấu hình, không chạy nghiệp vụ

Configuration class có nhiệm vụ mô tả bean definitions và dependency. Nó không phải nơi thích hợp để:
- Gọi HTTP API hoặc mở socket.
- Truy vấn database để tải dữ liệu ban đầu.
- Đọc và phân tích hàng nghìn file.
- Quét thư mục hoặc classpath bằng logic tự viết.
- Chạy migration thủ công ngoài cơ chế chuyên dụng.
- Chờ dịch vụ ngoài bằng vòng lặp retry không giới hạn.
- Khởi chạy thread không được quản lý.
- Thực hiện phép tính lớn chỉ để quyết định cách tạo bean.

Những công việc đó có thể làm context refresh chậm hoặc thất bại vì sự cố hệ thống bên ngoài.

### 6.1. Giữ constructor và static initializer nhẹ

Không nên đặt I/O hoặc phép tính lớn trong constructor của configuration class hay static initializer. Các lớp cấu hình có thể được load và xử lý trong giai đoạn phân tích cấu hình, trước khi bean nghiệp vụ được tạo.

Constructor nên chỉ lưu dependency hoặc thiết lập trạng thái cục bộ cần thiết.

### 6.2. @Bean method chỉ nên tạo và nối object

Ví dụ không tốt:

~~~java
@Bean
CatalogClient catalogClient() throws Exception {
    CatalogClient client = new CatalogClient();

    // Kết nối dịch vụ bên ngoài ngay trong lúc tạo bean.
    client.connect();
    client.downloadAllCatalogItems();
    client.rebuildLocalIndex();

    return client;
}
~~~

Nếu remote API chậm, database đang bảo trì hoặc dữ liệu quá lớn, quá trình khởi động ứng dụng sẽ bị kéo dài.

Ví dụ tốt hơn:

~~~java
@Bean
@ConditionalOnMissingBean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(
            properties.getEndpoint(),
            properties.getTimeout());
}
~~~

Factory method chỉ tạo object từ cấu hình. Việc gọi mạng, tải dữ liệu hoặc thực hiện query được thực hiện khi ứng dụng thật sự cần client.

Điều này không có nghĩa mọi constructor đều miễn phí. Hãy kiểm tra thư viện bên thứ ba: constructor có thể tự khởi động connection pool hoặc thực hiện discovery. Nếu vậy, cân nhắc API factory/lifecycle phù hợp của thư viện.

## 7. Truyền dependency qua tham số thay vì gọi trực tiếp @Bean method

Một configuration class có thể chứa nhiều bean method:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }

    @Bean
    CatalogService catalogService(CatalogClient catalogClient) {
        return new CatalogService(catalogClient);
    }
}
~~~

Dependency được thể hiện qua tham số của catalogService.

Không viết:

~~~java
@Bean
CatalogService catalogService() {
    return new CatalogService(catalogClient(new CatalogProperties()));
}
~~~

Đoạn code trên tự gọi factory method và tự tạo properties object. Nó bỏ qua dependency injection, có thể tạo instance ngoài ý muốn và không tôn trọng bean lifecycle hoặc bean thay thế do ứng dụng cung cấp.

Trong @Configuration(proxyBeanMethods = false) và @AutoConfiguration, lời gọi trực tiếp giữa @Bean method không được proxy để tra bean trong container. Hãy dùng tham số method hoặc constructor injection.

## 8. Trì hoãn khởi tạo bean đắt tiền

Nếu một bean chưa cần ngay khi ứng dụng khởi động, có thể cân nhắc @Lazy và ObjectProvider.

### 8.1. Dùng @Lazy trên bean cụ thể

~~~java
@Bean
@Lazy
@ConditionalOnMissingBean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(properties.getEndpoint());
}
~~~

Bean được tạo khi có yêu cầu truy cập thay vì khởi tạo ngay trong giai đoạn tạo singleton mặc định.

Phù hợp khi bean chỉ được dùng ở một số luồng hiếm, khởi tạo tốn tài nguyên và có thể chấp nhận lỗi khởi tạo xuất hiện ở lần sử dụng đầu.

### 8.2. Dùng ObjectProvider để thể hiện việc truy cập có điều kiện

~~~java
@Component
public class CatalogFacade {

    private final ObjectProvider<CatalogClient> catalogClients;

    public CatalogFacade(ObjectProvider<CatalogClient> catalogClients) {
        this.catalogClients = catalogClients;
    }

    public URI getEndpoint() {
        CatalogClient client = this.catalogClients.getObject();
        return client.getEndpoint();
    }
}
~~~

Inject ObjectProvider<CatalogClient> không buộc Spring tạo CatalogClient ngay. Bean được yêu cầu khi code gọi getObject().

| Phương thức | Hành vi |
| --- | --- |
| getObject() | Lấy bean; ném exception nếu không tìm thấy hoặc không xác định được bean phù hợp |
| getIfAvailable() | Trả về bean nếu có, nếu không thì trả null |
| getIfUnique() | Trả về bean nếu chỉ có một candidate phù hợp |
| orderedStream() | Lấy các bean phù hợp theo thứ tự Spring |

Không gọi getObject() ngay trong constructor của component nếu mục tiêu là trì hoãn việc tạo bean.

### 8.3. Lazy initialization toàn ứng dụng

Spring Boot hỗ trợ:

~~~properties
spring.main.lazy-initialization=true
~~~

Khi bật, bean được tạo khi cần thay vì tạo toàn bộ trong startup. Điều này có thể giảm thời gian khởi động, nhưng có các đánh đổi:
- Lỗi cấu hình có thể chỉ xuất hiện ở request hoặc tác vụ đầu tiên.
- Lần truy cập đầu có thể chậm hơn.
- Bộ nhớ vẫn phải đủ cho toàn bộ bean khi chúng được khởi tạo.
- Bean quan trọng có thể chưa được kiểm tra cho tới khi có traffic.

Ưu tiên trì hoãn những bean cụ thể có lý do rõ ràng. Chỉ bật lazy initialization toàn ứng dụng sau khi đã đo startup và kiểm thử lỗi khởi tạo.

## 9. Đặt công việc nặng vào đúng giai đoạn lifecycle

Có những tác vụ bắt buộc phải chạy khi ứng dụng khởi động, ví dụ kiểm tra schema, xác nhận cấu hình bắt buộc hoặc khởi tạo dữ liệu cục bộ thiết yếu.

Nếu công việc phải hoàn thành trước khi ứng dụng nhận traffic, có thể dùng ApplicationRunner hoặc CommandLineRunner:

~~~java
@Component
public class CatalogStartupCheck implements ApplicationRunner {

    private final CatalogHealthClient healthClient;

    public CatalogStartupCheck(CatalogHealthClient healthClient) {
        this.healthClient = healthClient;
    }

    @Override
    public void run(ApplicationArguments args) {
        this.healthClient.verifyWithTimeout(Duration.ofSeconds(3));
    }
}
~~~

Đây là ví dụ minh họa; verifyWithTimeout cần được triển khai với timeout hữu hạn và xử lý lỗi phù hợp.

Runner được gọi sau khi SpringApplication đã khởi động context nhưng trước khi SpringApplication.run(...) hoàn tất. Vì vậy nó phù hợp với tác vụ phải chạy trước traffic, nhưng thời gian chạy vẫn ảnh hưởng thời điểm ứng dụng READY.

Nếu có nhiều runner cần thứ tự, dùng Ordered hoặc @Order. Không dựa vào thứ tự khai báo source file.

### 9.1. Công việc không bắt buộc trước traffic

Nếu việc tải cache hoặc đồng bộ dữ liệu có thể chạy sau khi ứng dụng sẵn sàng:
- Dùng TaskExecutor do Spring quản lý.
- Đặt timeout và giới hạn retry.
- Có log, metric và trạng thái hoàn thành.
- Xử lý trường hợp tác vụ thất bại hoặc bị chạy lại.
- Quản lý shutdown để không bỏ dở tài nguyên.
- Nếu traffic phụ thuộc kết quả warm-up, biểu diễn dependency đó qua readiness.

Không tự tạo thread bằng new Thread() trong @Bean method rồi bỏ mặc nó. Thread cần lifecycle, exception handling, giới hạn tài nguyên và cơ chế shutdown.

### 9.2. Không dùng @PostConstruct cho tác vụ dài

@PostConstruct, InitializingBean.afterPropertiesSet() và callback khởi tạo chạy trong quá trình tạo bean. Nếu đặt HTTP call, database scan hoặc xử lý lớn ở đây, chúng vẫn chặn startup.

Dùng callback khởi tạo cho kiểm tra trạng thái cục bộ ngắn. Chuyển tác vụ nghiệp vụ có thời gian chạy đáng kể sang runner hoặc background workflow phù hợp.

## 10. Ví dụ chạy được: package scan có giới hạn và client khởi tạo lazy

Ví dụ sau là ứng dụng Spring Boot tối giản:
- Main application giới hạn component scan bằng marker class.
- Auto-configuration được phát hiện từ AutoConfiguration.imports.
- Properties được đăng ký tường minh.
- Client mặc định được đánh dấu lazy.
- Component chỉ nhận ObjectProvider, không tạo client trong constructor.
- Runner in một dòng xác nhận client chưa được yêu cầu.

### 10.1. Cấu trúc dự án

~~~text
scan-and-startup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/demo/
        │   ├── DemoApplication.java
        │   ├── components/
        │   │   ├── ComponentsPackage.java
        │   │   ├── CatalogFacade.java
        │   │   └── StartupReporter.java
        │   ├── catalog/
        │   │   ├── CatalogClient.java
        │   │   └── CatalogProperties.java
        │   └── autoconfigure/
        │       └── CatalogAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 10.2. Maven configuration

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scan-and-startup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 10.3. Main application và marker package

File DemoApplication.java:

~~~java
package com.example.demo;

import com.example.demo.components.ComponentsPackage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication(scanBasePackageClasses = ComponentsPackage.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }
}
~~~

File components/ComponentsPackage.java:

~~~java
package com.example.demo.components;

public final class ComponentsPackage {

    private ComponentsPackage() {
    }
}
~~~

Component scan chỉ nhắm vào package com.example.demo.components và package con. Lớp main vẫn là primary source của ứng dụng; auto-configuration được xử lý qua cơ chế riêng.

### 10.4. Properties class

File catalog/CatalogProperties.java:

~~~java
package com.example.demo.catalog;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.catalog")
public class CatalogProperties {

    private URI endpoint = URI.create("https://catalog.example.test");

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

### 10.5. Client có constructor nhẹ

File catalog/CatalogClient.java:

~~~java
package com.example.demo.catalog;

import java.net.URI;

public final class CatalogClient {

    private final URI endpoint;

    public CatalogClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI getEndpoint() {
        return this.endpoint;
    }
}
~~~

Client chỉ giữ endpoint cấu hình. Constructor không gọi mạng, mở database hoặc tải catalog.

Trong ứng dụng thực tế, các phương thức thực hiện HTTP request hoặc đọc dữ liệu mới là nơi thực hiện I/O, với timeout và xử lý lỗi phù hợp.

### 10.6. Auto-configuration đăng ký bean lazy

File autoconfigure/CatalogAutoConfiguration.java:

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.catalog.CatalogClient;
import com.example.demo.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @Lazy
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }
}
~~~

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.example.demo.autoconfigure.CatalogAutoConfiguration
~~~

Auto-configuration không cần component scan. Spring Boot phát hiện nó qua imports file.

### 10.7. Component nhận ObjectProvider

File components/CatalogFacade.java:

~~~java
package com.example.demo.components;

import java.net.URI;

import com.example.demo.catalog.CatalogClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

@Component
public class CatalogFacade {

    private final ObjectProvider<CatalogClient> catalogClients;

    public CatalogFacade(ObjectProvider<CatalogClient> catalogClients) {
        this.catalogClients = catalogClients;
    }

    public URI getEndpoint() {
        CatalogClient client = this.catalogClients.getObject();
        return client.getEndpoint();
    }
}
~~~

Khi CatalogFacade được tạo, Spring chỉ inject ObjectProvider. Client chưa được yêu cầu. Khi một luồng nghiệp vụ gọi getEndpoint(), getObject() mới yêu cầu bean.

### 10.8. Runner không yêu cầu client

File components/StartupReporter.java:

~~~java
package com.example.demo.components;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "ApplicationRunner ran; CatalogClient has not been requested.");
    }
}
~~~

File application.properties có thể chứa:

~~~properties
demo.catalog.endpoint=https://catalog.internal.example
~~~

### 10.9. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Dòng output do ứng dụng tự in:

~~~text
ApplicationRunner ran; CatalogClient has not been requested.
~~~

Các log startup khác của Spring Boot vẫn xuất hiện. Trong ví dụ này, StartupReporter không gọi CatalogFacade.getEndpoint(), nên CatalogClient lazy chưa được yêu cầu.

Khi một component nghiệp vụ gọi:

~~~java
URI endpoint = catalogFacade.getEndpoint();
~~~

Spring mới tạo CatalogClient nếu nó chưa tồn tại.

Ví dụ minh họa việc trì hoãn khởi tạo bean. Nó không thay thế việc trì hoãn kết nối mạng: nếu constructor client thật sự mở socket hoặc khởi tạo pool, phần chi phí đó sẽ xảy ra khi bean được tạo lần đầu. Thiết kế tốt vẫn cần giữ constructor nhẹ và thực hiện I/O khi có thao tác sử dụng rõ ràng.

## 11. Tương thích Spring AOT và native image

Spring AOT kiểm tra ApplicationContext ở thời điểm build để tạo mã khởi tạo, bytecode và runtime hints cần thiết. Mục tiêu là chuyển một phần công việc phát hiện và xử lý cấu hình từ runtime sang build time.

Điều này hỗ trợ startup và GraalVM native image, nhưng cũng đặt ra các ràng buộc.

### 11.1. Bean graph phải xác định được ở build time

Với AOT/native image:
- Classpath được cố định và xác định ở thời điểm build.
- Bean graph không thể thay đổi tùy ý lúc runtime.
- Profile và property ảnh hưởng đến việc bean có được tạo hay không cần được chọn phù hợp ở build time.
- Condition như @ConditionalOnProperty không thể được dùng để thay đổi bean graph tùy ý sau khi AOT đã tạo mã.
- Một số cách đăng ký bean động bằng instance supplier hoặc đăng ký singleton trực tiếp không thể được chuyển đổi AOT như bean definition thông thường.

Ưu tiên:
- @Configuration và @AutoConfiguration tường minh.
- @Bean method có return type chính xác.
- @Import cho configuration đã biết.
- Condition có hợp đồng rõ ràng.
- Bean definition được khai báo qua cơ chế Spring tiêu chuẩn.

Tránh dùng BeanFactory.registerSingleton(...) trong runtime để thêm bean mà AOT không thể biết trước.

### 11.2. RuntimeHints cho reflection và resource

Native image cần biết trước các hoạt động có tính động như reflection, đọc resource theo tên được tạo ở runtime, serialization và tạo JDK proxy.

Spring tự suy ra nhiều hints từ code và annotation, nhưng thư viện có thể cần bổ sung.

Ví dụ thư viện đọc schema từ classpath theo pattern:

~~~java
package com.example.demo.autoconfigure;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("catalog/schemas/*.json");
    }
}
~~~

Đăng ký hints gần component cần chúng:

~~~java
@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

Chỉ khai báo resource pattern khi code thật sự cần tải các file đó ở runtime. Không đăng ký hàng loạt resource hoặc reflection hints không cần thiết.

Có thể kiểm thử hints bằng RuntimeHintsPredicates để xác nhận resource, reflection hoặc proxy cần thiết đã được khai báo.

### 11.3. Tránh dynamic scanning và điều kiện thay đổi bean graph ở runtime

Một ứng dụng dựa vào package scan cố định vẫn có thể tham gia AOT. Vấn đề là phạm vi scan nên ổn định và phù hợp với ứng dụng.

Tránh:
- Xây dựng package name động từ environment rồi scan tùy ý.
- Tìm class tùy ý trên classpath và tự đăng ký bean khi runtime.
- Đăng ký singleton trực tiếp vào bean factory sau khi context đã tạo.
- Dùng property condition để mong native image thay đổi bean graph sau build.
- Khai báo bean bằng type quá chung khiến AOT không xác định được kiểu thực tế.

AOT không cấm mọi reflection hoặc component scan. Hãy dùng API Spring được hỗ trợ, khai báo hints cho hành vi động mà framework không thể tự suy ra và kiểm tra artifact AOT/native bằng test phù hợp.

## 12. Đo và phân tích startup

Spring Boot cung cấp ApplicationStartup để ghi lại các bước khởi động. Ví dụ:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

Nếu ứng dụng có Actuator, có thể cấu hình endpoint startup để xem các bước đã được ghi nhận. Endpoint cần được expose theo chính sách quản trị của ứng dụng.

Một lựa chọn khác là Java Flight Recorder:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=30s -jar target/my-app.jar
~~~

JFR giúp quan sát class loading, thread activity, CPU hot spots, allocation và garbage collection.

### 12.1. Quy trình tối ưu có kiểm chứng

1. Ghi thời gian startup baseline trong cùng môi trường.
2. Bật BufferingApplicationStartup hoặc JFR.
3. Xác định giai đoạn chậm: scan, configuration parsing, bean creation hay runner.
4. Kiểm tra package scan và số bean candidate.
5. Tìm constructor, @Bean, @PostConstruct và runner có I/O hoặc xử lý dài.
6. Chỉ thay đổi một nhóm nguyên nhân trong mỗi lượt.
7. Chạy lại với cùng profile, classpath, JVM options và dữ liệu.
8. So sánh thời gian startup, thời gian readiness và latency ở lần truy cập đầu.
9. Kiểm tra lỗi cấu hình bị trì hoãn khi dùng lazy initialization.
10. Chạy AOT/native build và smoke test nếu ứng dụng cần triển khai theo hình thức đó.

Không chỉ đo thời gian đến log Started. Với hệ thống phục vụ traffic, cần quan sát thêm thời điểm readiness và thời gian phản hồi request đầu tiên.

## 13. Bảng lựa chọn giải pháp

| Vấn đề | Giải pháp ưu tiên | Điều cần lưu ý |
| --- | --- | --- |
| Main class nằm trong package quá cao | Chuyển vào root package hoặc giới hạn scan bằng marker class | Kiểm tra entity/repository scan riêng |
| Auto-configuration quét package thư viện | Dùng @Import và imports file | Không scan package ứng dụng tiêu thụ |
| Properties class bị scan quá rộng | Dùng @EnableConfigurationProperties hoặc giới hạn @ConfigurationPropertiesScan | Đăng ký đúng properties type cần dùng |
| @Bean method gọi API bên ngoài | Chuyển I/O sang thao tác sử dụng hoặc lifecycle rõ ràng | Có timeout và xử lý lỗi |
| Bean chỉ dùng ở một số luồng | @Lazy và/hoặc ObjectProvider | Kiểm thử lỗi ở lần truy cập đầu |
| Nhiều bean không cần thiết được tạo khi startup | Cân nhắc lazy initialization | Đo lại memory và first-request latency |
| Tác vụ bắt buộc trước traffic | ApplicationRunner hoặc CommandLineRunner | Runner kéo dài thời điểm READY |
| Warm-up không bắt buộc trước traffic | Executor/lifecycle được quản lý | Có readiness, log, metric và shutdown |
| Native image thiếu resource/reflection | RuntimeHintsRegistrar và @ImportRuntimeHints | Chỉ đăng ký hints thực sự cần |

## 14. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt main class trong default package | Scan có thể đọc class từ mọi JAR | Dùng package tên miền đảo ngược |
| Đặt main class ở package com hoặc package vendor quá cao | Scan nhiều module ngoài phạm vi ứng dụng | Chọn root package của ứng dụng |
| Dùng @ComponentScan("com") | Phạm vi scan quá rộng và dễ có bean ngoài ý muốn | Dùng marker class hoặc package cụ thể |
| Dùng scanBasePackageClasses để tìm JPA entity | Entity scan không được điều khiển bởi thuộc tính này | Dùng @EntityScan |
| Dùng component scan trong starter để tìm auto-configuration | Quét cả package của ứng dụng tiêu thụ | Đăng ký qua AutoConfiguration.imports |
| Gọi HTTP trong constructor configuration | Context startup phụ thuộc mạng ngoài | Tách I/O khỏi configuration |
| Truy vấn DB trong @Bean method | Startup chậm hoặc fail khi DB chưa sẵn sàng | Dùng bean nhẹ và lifecycle phù hợp |
| Đưa công việc nặng vào @PostConstruct | Bean creation bị chặn | Dùng runner hoặc background workflow |
| Bật lazy initialization toàn cục mà không kiểm thử | Lỗi khởi tạo xuất hiện muộn, request đầu chậm | Ưu tiên lazy bean cụ thể |
| Inject trực tiếp bean nặng dù chỉ dùng đôi khi | Dependency có thể được tạo ngay khi component được tạo | Dùng ObjectProvider |
| Dùng proxyBeanMethods=false nhưng gọi trực tiếp @Bean method | Có thể tạo instance mới ngoài container | Inject dependency qua tham số |
| Tạo thread bằng new Thread() trong configuration | Khó quản lý lỗi và shutdown | Dùng executor/lifecycle do Spring quản lý |
| Đăng ký bean động bằng registerSingleton khi dùng AOT | Bean graph khó được xử lý ở build time | Khai báo bean definition tiêu chuẩn |
| Bỏ qua runtime hints cho resource/reflection động | Native image có thể thiếu resource hoặc member cần truy cập | Đăng ký hints và kiểm thử |
| Chỉ đo thời gian đến log Started | Bỏ sót runner và first-request latency | Đo cả READY và request đầu |

## 15. Checklist trước khi hoàn tất một auto-configuration

### Package và scanning

- [ ] Main application nằm trong package tên miền đảo ngược, ở vị trí hợp lý.
- [ ] Không có class trong default package.
- [ ] Component scan có phạm vi vừa đủ.
- [ ] Dùng marker class khi cần giới hạn scan rõ ràng.
- [ ] Entity và repository có scan configuration riêng khi cần.
- [ ] Auto-configuration được đăng ký qua imports file.
- [ ] Không có @ComponentScan rộng trong starter.

### Configuration và lifecycle

- [ ] Constructor và static initializer không thực hiện I/O hoặc xử lý lớn.
- [ ] @Bean method chủ yếu tạo object và nối dependency.
- [ ] Dependency được truyền qua constructor hoặc method parameter.
- [ ] Không gọi trực tiếp @Bean method khi configuration dùng proxyBeanMethods=false.
- [ ] Tác vụ bắt buộc trước traffic có timeout và thứ tự rõ ràng.
- [ ] Tác vụ nền dùng executor/lifecycle được quản lý.
- [ ] Lazy initialization chỉ được bật ở phạm vi có lý do và đã kiểm thử.

### AOT và startup measurement

- [ ] Bean graph có thể xác định ở build time.
- [ ] Không đăng ký singleton động mà AOT không thể xử lý.
- [ ] Return type của @Bean method đủ cụ thể.
- [ ] Runtime hints được khai báo cho reflection/resource/proxy cần thiết.
- [ ] Có baseline startup và kết quả đo sau tối ưu.
- [ ] Đã kiểm tra thời gian readiness và first-request latency.
- [ ] Native image hoặc AOT artifact đã được smoke test nếu là mục tiêu triển khai.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao default package có thể làm Spring Boot scan quá rộng?

**Đáp án:** Vì các annotation scan có thể phải đọc class từ mọi JAR trên classpath khi không có package gốc giới hạn phạm vi.

**Câu 2.** scanBasePackageClasses khác gì scanBasePackages?

**Đáp án:** Cả hai đều chỉ định package cho component scan. scanBasePackageClasses dùng class marker nên type-safe hơn chuỗi package name.

**Câu 3.** scanBasePackageClasses có điều khiển JPA entity và repository scan không?

**Đáp án:** Không. Dùng @EntityScan và @EnableJpaRepositories cho các phạm vi đó.

**Câu 4.** Vì sao auto-configuration của starter nên dùng @Import thay component scan rộng?

**Đáp án:** @Import đưa đúng configuration class cần thiết vào context, tránh quét component của ứng dụng tiêu thụ hoặc package không liên quan.

**Câu 5.** Vì sao không nên gọi HTTP trong @Bean method?

**Đáp án:** Factory method chạy trong quá trình tạo bean; network I/O có thể kéo dài hoặc làm context startup thất bại khi dịch vụ ngoài không sẵn sàng.

**Câu 6.** ObjectProvider<T> giúp trì hoãn khởi tạo như thế nào?

**Đáp án:** Component có thể nhận provider mà chưa yêu cầu bean T. Bean chỉ được lấy khi code gọi getObject().

**Câu 7.** ApplicationRunner có chạy sau khi ứng dụng đã READY hoàn toàn không?

**Đáp án:** Không. Runner được gọi trước khi SpringApplication.run(...) hoàn tất và có thể ảnh hưởng thời điểm ứng dụng sẵn sàng nhận traffic.

**Câu 8.** Vì sao lazy initialization có thể làm lỗi xuất hiện muộn?

**Đáp án:** Bean chưa được tạo trong startup. Nếu cấu hình bean sai, lỗi chỉ xuất hiện khi bean được truy cập lần đầu.

**Câu 9.** AOT yêu cầu gì đối với điều kiện tạo bean?

**Đáp án:** Bean graph cần được xác định ở build time. Profile và property ảnh hưởng sự tồn tại của bean phải phù hợp với cấu hình đã dùng để AOT processing.

**Câu 10.** Khi nào cần RuntimeHints?

**Đáp án:** Khi ứng dụng hoặc thư viện có hành vi động mà framework không thể suy ra, chẳng hạn reflection, đọc resource theo pattern, serialization hoặc JDK proxy.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Structuring Your Code: https://docs.spring.io/spring-boot/3.5/reference/using/structuring-your-code.html
- Spring Boot 3.5 API — SpringBootApplication: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.5 API — AutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.5 Reference — SpringApplication, lazy initialization, runners và startup tracking: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 Reference — Configuration Classes: https://docs.spring.io/spring-boot/3.5/reference/using/configuration-classes.html
- Spring Framework 6.2 — Using the Configuration annotation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html
- Spring Framework 6.2 — Composing Java-based Configurations: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html
- Spring Boot 3.5 — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/3.5/reference/packaging/aot.html
- Spring Boot 3.5 — Introducing GraalVM Native Images and Spring AOT: https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/introducing-graalvm-native-images.html
- Spring Boot 3.5 — Advanced Native Images Topics and Runtime Hints: https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/advanced-topics.html
