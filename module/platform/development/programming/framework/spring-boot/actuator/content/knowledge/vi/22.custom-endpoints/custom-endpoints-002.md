# Định nghĩa endpoint bằng @Endpoint và đăng ký bean

## 1. Endpoint tùy chỉnh dùng để làm gì?

Giả sử ứng dụng có một bộ nhớ đệm danh mục sản phẩm. Khi vận hành, ta muốn biết bộ nhớ đệm đang chứa bao nhiêu mục mà không trả về toàn bộ dữ liệu sản phẩm.

Một endpoint quản trị nhỏ có thể trả về:

```json
{"name":"catalog","entries":2}
```

Đây là thông tin về trạng thái nội bộ của ứng dụng, phù hợp để minh họa một **Actuator endpoint tùy chỉnh**. API để khách hàng tìm hoặc mua sản phẩm vẫn có hợp đồng nghiệp vụ riêng.

`@Endpoint` đánh dấu một kiểu là endpoint của Actuator. Các phương thức thao tác như `@ReadOperation` được bộ thích ứng công nghệ xử lý để có thể công bố qua HTTP, JMX hoặc công nghệ phù hợp. [Spring Boot 3.3: Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)

Có ba việc phải tách rõ ngay từ đầu:

1. **Định nghĩa endpoint:** lớp mang `@Endpoint`, có ID và phương thức thao tác.
2. **Đăng ký bean:** Spring phải quản lý một đối tượng của lớp đó.
3. **Công bố truy cập:** cấu hình cho phép công nghệ như HTTP tiếp cận endpoint.

Một lớp có annotation nhưng chưa thành bean không tương đương với một URL đang hoạt động.

## 2. Mỗi annotation chịu trách nhiệm gì?

| Thành phần | Trách nhiệm trong ví dụ |
| --- | --- |
| `@Endpoint(id = "catalogcache")` | Xác định endpoint Actuator có ID `catalogcache` |
| `@ReadOperation` | Đánh dấu thao tác đọc mà Actuator nhận diện |
| `@Bean` | Đăng ký đối tượng trả về từ phương thức với Spring |
| `@Configuration` | Chứa cấu hình tạo các bean của ví dụ |
| `@Component` | Một lựa chọn đăng ký qua quét thành phần, thay cho phương thức `@Bean` tương ứng |
| `management.endpoints.web.exposure.include` | Chọn những ID được công bố qua HTTP |

`@Endpoint` tự nó không phải `@Component`. Đặt lớp trong package được quét mà chỉ thêm `@Endpoint` chưa phải cách đăng ký bean. Bài dùng `@Bean` để nhìn rõ nơi tạo đối tượng và nơi cung cấp phụ thuộc.

Spring cho phép phương thức `@Bean` nhận các phụ thuộc qua tham số; container sẽ cung cấp bean phù hợp. [Spring Framework: sử dụng @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

### 2.1. Đừng nhầm bean name, endpoint ID và tên phương thức thao tác

Trong ví dụ hoàn chỉnh:

| Tên | Giá trị | Vai trò |
| --- | --- | --- |
| Kiểu Java | `CatalogCacheEndpoint` | Lớp triển khai |
| Bean name | `catalogCacheEndpoint` | Tên bean mặc định từ phương thức `@Bean` |
| Endpoint ID | `catalogcache` | Định danh Actuator |
| Phương thức thao tác | `read()` | Mã đọc thông tin |
| URL mặc định của ví dụ | `/actuator/catalogcache` | Đường dẫn HTTP từ base path và ID |

Đổi tên `read()` thành `snapshot()` không tự biến URL thành `/actuator/snapshot`. Tương tự, đặt bean name khác không phải cách đổi endpoint ID.

ID nên ngắn, ổn định và chỉ gồm chữ, số; theo hợp đồng `EndpointId`, nó bắt đầu bằng chữ thường. `catalogcache` đáp ứng quy tắc đó. Không đặt ID thành một đường dẫn như `/catalog/cache`. [Spring Boot 3.3: EndpointId](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/EndpointId.html)

## 3. Ví dụ chạy đầy đủ với Spring Boot 3.3 và Java 21

Ví dụ sau là một dự án Maven độc lập, dùng Java 21. Nó có dữ liệu mẫu bất biến gồm hai mục, một endpoint chỉ đọc và hai kiểm thử tích hợp.

Thông tin `entries=2` được tính từ kích thước Map của bộ nhớ đệm mẫu. Endpoint không giả lập một con số lấy từ hệ thống sản xuất.

### 3.1. Cấu trúc tệp

```text
actuator-endpoint-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/actuator/
    │   │   ├── ActuatorEndpointDemoApplication.java
    │   │   ├── CatalogCache.java
    │   │   ├── CatalogCacheEndpoint.java
    │   │   └── EndpointConfiguration.java
    │   └── resources/application.properties
    └── test/
        └── java/example/actuator/CatalogCacheEndpointTest.java
```

Lớp khởi động và cấu hình cùng nằm trong `example.actuator`. `@SpringBootApplication` bao gồm cơ chế quét thành phần để phát hiện cấu hình trong phạm vi của nó. [Spring Boot 3.3: SpringBootApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)

### 3.2. pom.xml

```xml
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
    <groupId>example</groupId>
    <artifactId>actuator-endpoint-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Ba phụ thuộc phục vụ ba việc:

- `spring-boot-starter-web`: ứng dụng HTTP dùng Spring MVC.
- `spring-boot-starter-actuator`: hạ tầng khám phá và công bố endpoint Actuator.
- `spring-boot-starter-test`: kiểm thử tích hợp, chỉ dùng trong phạm vi test.

Parent của Boot quản lý phiên bản các thư viện liên quan. Không cần tự ghim một phiên bản khác cho riêng Actuator trong ví dụ này.

### 3.3. Lớp khởi động

Nội dung `ActuatorEndpointDemoApplication.java`:

```java
package example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorEndpointDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorEndpointDemoApplication.class, args);
    }
}
```

### 3.4. Đối tượng giữ trạng thái cần quan sát

Nội dung `CatalogCache.java`:

```java
package example.actuator;

import java.util.Map;

public final class CatalogCache {
    private final Map<String, String> entries;

    public CatalogCache(Map<String, String> entries) {
        this.entries = Map.copyOf(entries);
    }

    public int entryCount() {
        return entries.size();
    }
}
```

`Map.copyOf(...)` giữ một bản Map không sửa được qua đối tượng này. `entryCount()` trả về số mục của dữ liệu mẫu, còn endpoint không cần biết các mã sản phẩm cụ thể.

Trong ứng dụng thật, có thể thay đối tượng mẫu bằng dịch vụ thống kê trạng thái đang vận hành. Hãy giữ việc thu thập dữ liệu ở dịch vụ phù hợp; lớp endpoint chỉ chuyển thông tin cần công bố thành kết quả rõ ràng.

### 3.5. Lớp endpoint

Nội dung `CatalogCacheEndpoint.java`:

```java
package example.actuator;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;

@Endpoint(id = "catalogcache")
public final class CatalogCacheEndpoint {
    private final CatalogCache cache;

    public CatalogCacheEndpoint(CatalogCache cache) {
        this.cache = cache;
    }

    @ReadOperation
    public CacheSnapshot read() {
        return new CacheSnapshot("catalog", cache.entryCount());
    }

    public record CacheSnapshot(String name, int entries) {
    }
}
```

Các chi tiết cần đọc đúng:

- `@Endpoint` được import từ `org.springframework.boot.actuate.endpoint.annotation`.
- `@ReadOperation` đánh dấu phương thức đọc, không phải `@GetMapping`.
- Constructor nhận `CatalogCache`; nó không tự tạo thêm một bộ nhớ đệm khác.
- `CacheSnapshot` là record chứa đúng dữ liệu công bố.
- Lớp chưa mang `@Component`; việc đăng ký bean được làm ở cấu hình kế tiếp.

Với công bố HTTP, thao tác đọc được ánh xạ sang GET. Record có giá trị trả về sẽ được chuyển thành nội dung phản hồi JSON trong cấu hình web của ví dụ. [Spring Boot 3.3: thao tác endpoint và HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints)

Không cần thêm `@RestController` hoặc `@RequestMapping` vào lớp này để tạo URL Actuator.

### 3.6. Đăng ký bean và cung cấp phụ thuộc

Nội dung `EndpointConfiguration.java`:

```java
package example.actuator;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class EndpointConfiguration {
    @Bean
    public CatalogCache catalogCache() {
        return new CatalogCache(Map.of(
                "A100", "Notebook",
                "B200", "Pencil"));
    }

    @Bean
    public CatalogCacheEndpoint catalogCacheEndpoint(CatalogCache cache) {
        return new CatalogCacheEndpoint(cache);
    }
}
```

Spring thực hiện hai bước:

1. Gọi phương thức `catalogCache()` để đăng ký bean dữ liệu mẫu.
2. Cung cấp bean đó cho tham số `cache` của phương thức `catalogCacheEndpoint(...)`, rồi quản lý endpoint được trả về.

Lệnh `new CatalogCacheEndpoint(cache)` ở đây có tác dụng đăng ký vì **kết quả của phương thức @Bean** được container tiếp nhận. Một lệnh `new` tương tự trong mã tùy ý, không trả về qua cơ chế đăng ký, chỉ tạo một đối tượng Java bình thường.

Cấu hình dùng `proxyBeanMethods = false` và nhận phụ thuộc bằng tham số. Không cần gọi trực tiếp `catalogCache()` bên trong phương thức còn lại để tìm phụ thuộc.

Nên khai báo kiểu trả về cụ thể là `CatalogCacheEndpoint`, để kiểu bean thể hiện rõ cho cơ chế khám phá. Không có lợi ích học tập nào khi đổi thành `Object` rồi che mất thông tin kiểu.

### 3.7. Cho phép endpoint xuất hiện qua HTTP

Nội dung `application.properties`:

```properties
spring.application.name=actuator-endpoint-demo
server.address=127.0.0.1
server.port=8080

management.endpoint.catalogcache.enabled=true
management.endpoints.web.exposure.include=health,catalogcache
```

Ở đây:

- Ứng dụng lắng nghe trên loopback `127.0.0.1` để thử cục bộ.
- Thuộc tính `enabled=true` xác định endpoint `catalogcache` được bật.
- Danh sách HTTP exposure có `catalogcache`.
- Base path giữ mặc định `/actuator`.

Được bật và được công bố là hai điều kiện riêng. Theo cấu hình mặc định Boot 3.3, chỉ `health` được công bố qua HTTP; vì vậy không thể bỏ qua danh sách exposure rồi mong mọi endpoint mới tự có URL truy cập được. [Spring Boot 3.3: công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

Danh sách ở ví dụ có `health` và `catalogcache`; không cần mở tất cả endpoint để kiểm chứng một endpoint mới.

## 4. Từ bean đến phản hồi HTTP: điều gì đã diễn ra?

```text
EndpointConfiguration được Spring phát hiện
    --> tạo bean CatalogCache
    --> tạo bean CatalogCacheEndpoint
    --> Actuator nhận diện @Endpoint và @ReadOperation
    --> kiểm tra bật endpoint và công bố HTTP
    --> tạo ánh xạ GET /actuator/catalogcache
    --> gọi read()
    --> trả CacheSnapshot thành JSON
```

Phương thức `read()` không cần nhận request HTTP hoặc tự viết JSON. Nó thể hiện thao tác quản trị; bộ thích ứng HTTP đảm nhận việc gọi và chuyển kết quả.

Điều này cũng giải thích vì sao lớp endpoint nên giữ hợp đồng thao tác đơn giản. Việc bổ sung tham số đầu vào, thao tác ghi/xóa hoặc kiểu endpoint chuyên cho web là các bước mở rộng riêng; không cần đưa chúng vào để đăng ký một endpoint chỉ đọc.

### 4.1. Ba chốt cần kiểm tra độc lập

| Chốt | Câu hỏi | Bằng chứng trong ví dụ |
| --- | --- | --- |
| Bean | Có đúng một đối tượng endpoint được Spring quản lý không? | `getBeansOfType(CatalogCacheEndpoint.class)` có một phần tử |
| Khám phá | Actuator web có nhận diện ID không? | `WebEndpointsSupplier` có `catalogcache` |
| HTTP | Request đúng đường dẫn có gọi được thao tác không? | GET trả 200 và dữ liệu mẫu đúng |

Một lần gọi `new CatalogCacheEndpoint(...).read()` thành công chỉ kiểm tra phương thức Java. Nó chưa chứng minh Spring đã đăng ký bean, Actuator đã khám phá hay HTTP đã ánh xạ.

Tương tự, nhìn thấy một bean trong container chưa đủ kết luận request qua HTTP được phép truy cập. Nếu ứng dụng có Spring Security, quy tắc truy cập còn được áp dụng riêng; cấu hình exposure không cấp quyền cho người gọi.

## 5. Biên dịch, kiểm thử và chạy

Cần JDK 21, Maven và mạng tải phụ thuộc trong lần đầu. Chạy các lệnh sau tại thư mục chứa `pom.xml`.

### 5.1. Kiểm thử và đóng gói

Sau khi thêm lớp test ở mục 6:

```shell
mvn verify
```

Lệnh này biên dịch mã chính, chạy kiểm thử và đóng gói ứng dụng. Spring Boot Maven plugin tạo JAR chạy được:

```text
target/actuator-endpoint-demo-1.0.0.jar
```

Dự án dùng thư viện Spring và máy chủ web nhúng, nên Maven chuẩn bị classpath và đóng gói thay cho việc gọi `javac` trên một tệp đơn lẻ.

### 5.2. Khởi động JAR

```shell
java -jar target/actuator-endpoint-demo-1.0.0.jar
```

Nếu cổng 8080 đang được dùng, có thể chọn cổng khác:

```shell
java -jar target/actuator-endpoint-demo-1.0.0.jar --server.port=18080
```

Khi đổi cổng, dùng cùng cổng đó trong lệnh HTTP tiếp theo. Log khởi động có thời gian, PID và thông tin môi trường thay đổi theo lần chạy; không coi toàn bộ log là stdout cố định.

### 5.3. Gọi endpoint

Trong một terminal khác:

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/catalogcache
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là bí danh của lệnh PowerShell khác.

Nội dung phản hồi:

```json
{"name":"catalog","entries":2}
```

Đây là kết quả từ hai mục dữ liệu mẫu trong `EndpointConfiguration`. Thứ tự thành viên JSON và khoảng trắng không phải phần hợp đồng cần so sánh; giá trị của `name`, `entries` và mã HTTP mới là trọng tâm kiểm chứng.

Dừng tiến trình ứng dụng bằng Ctrl+C khi thử xong.

## 6. Kiểm thử bean, khám phá và đường dẫn

Nội dung `CatalogCacheEndpointTest.java`:

```java
package example.actuator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogCacheEndpointTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private WebEndpointsSupplier webEndpoints;

    @Autowired
    private MockMvc http;

    @Test
    void registeredEndpointIsDiscoveredAndServesItsSnapshot() throws Exception {
        assertThat(context.getBeansOfType(CatalogCacheEndpoint.class))
                .hasSize(1);
        assertThat(context.getBean("catalogCacheEndpoint"))
                .isInstanceOf(CatalogCacheEndpoint.class);
        assertThat(webEndpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .contains("catalogcache");

        http.perform(get("/actuator/catalogcache")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("catalog"))
                .andExpect(jsonPath("$.entries").value(2));
    }

    @Test
    void endpointIdIsNotAnOrdinaryControllerRoute() throws Exception {
        http.perform(get("/catalogcache"))
                .andExpect(status().isNotFound());
    }
}
```

Test nạp Spring context và dùng MockMvc để đi qua hạ tầng xử lý request của Spring MVC mà không mở máy chủ hay cổng mạng. Vì vậy nó kiểm tra ánh xạ và phản hồi ở tầng MVC, chưa kiểm chứng kết nối TCP hoặc quá trình chạy JAR độc lập. [Spring Framework: MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

Hai test xác nhận hai việc:

- Bean đúng tên, đúng kiểu được đăng ký, được Actuator khám phá và phục vụ dữ liệu qua đường dẫn quản trị.
- ID `catalogcache` không tự tạo đường dẫn controller thông thường `/catalogcache` trong ứng dụng mẫu.

Test thứ hai có ý nghĩa trong dự án mẫu không khai báo controller tương ứng. Trong một ứng dụng khác, nếu có controller riêng ánh xạ `/catalogcache`, kết quả đường dẫn đó phải xét theo controller ấy.

Các assertion về JSON giúp tránh chấm “đạt” chỉ vì endpoint trả 200 nhưng dữ liệu không đúng. Kiểm tra bean và khám phá giúp khoanh vùng nguyên nhân nếu bước HTTP thất bại.

## 7. Cách đăng ký khác: @Component

Nếu muốn quét thành phần tự đăng ký endpoint, có thể thêm `@Component` vào lớp endpoint. Khi chọn cách này, **bỏ phương thức @Bean tạo endpoint tương ứng**; vẫn giữ bean `CatalogCache` để cung cấp phụ thuộc.

Phiên bản lớp endpoint thay thế sẽ là:

```java
package example.actuator;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "catalogcache")
public final class CatalogCacheEndpoint {
    private final CatalogCache cache;

    public CatalogCacheEndpoint(CatalogCache cache) {
        this.cache = cache;
    }

    @ReadOperation
    public CacheSnapshot read() {
        return new CacheSnapshot("catalog", cache.entryCount());
    }

    public record CacheSnapshot(String name, int entries) {
    }
}
```

Đây là phương án thay thế cho lớp endpoint và cách đăng ký ở trên. Trong `EndpointConfiguration`, chỉ giữ phương thức tạo `CatalogCache`; bỏ phương thức tạo `CatalogCacheEndpoint` để endpoint không bị đăng ký hai lần.

Chọn cách theo nhu cầu:

| Cách đăng ký | Phù hợp khi |
| --- | --- |
| `@Bean` trong cấu hình | Muốn nhìn rõ cách tạo endpoint, cấu hình phụ thuộc hoặc đăng ký lớp không tự mang stereotype |
| `@Component` trên lớp | Endpoint là thành phần do ứng dụng sở hữu và nằm trong vùng component scan |

Không dùng đồng thời hai cách để tạo hai bean endpoint cùng ID. Đổi tên bean cũng không tạo ra hai định danh Actuator độc lập: ID vẫn là `catalogcache`.

Nếu thêm `@Component` nhưng lớp nằm ngoài vùng quét, Spring vẫn có thể không tạo bean. Cần đưa cấu hình/lớp vào phạm vi quét hoặc import cấu hình phù hợp, thay vì sửa đường dẫn HTTP một cách ngẫu nhiên.

## 8. Lỗi thường gặp và cách kiểm tra

| Biểu hiện | Điều cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Có lớp @Endpoint nhưng không có bean | Thiếu `@Bean` hoặc stereotype được quét | Đăng ký bằng một cơ chế rõ ràng |
| Có @Bean nhưng không thấy endpoint | Lớp cấu hình chưa được nạp | Kiểm tra package, component scan hoặc import |
| Endpoint không có thao tác đọc | Phương thức thiếu `@ReadOperation` hoặc import nhầm | Dùng annotation Actuator đúng package |
| GET /actuator/catalogcache trả 404 | Bean, thao tác, enabled, exposure, base path và cổng | Kiểm tra theo thứ tự thay vì chỉ đổi URL |
| GET /catalogcache trả 404 | Đang dùng ID như URL controller | Gọi đường dẫn Actuator của ví dụ |
| Lỗi trùng endpoint lúc khởi động | Hai bean có cùng ID, thường do giữ cả @Bean lẫn @Component | Chỉ giữ một đăng ký cho endpoint này |
| Lỗi phụ thuộc CatalogCache | Không có bean đúng kiểu hoặc có nhiều ứng viên không rõ | Sửa việc cung cấp phụ thuộc trước khi thử HTTP |
| HTTP 401 hoặc 403 | Quy tắc xác thực/phân quyền đang áp dụng | Kiểm tra cấu hình bảo mật phù hợp |
| HTTP 200 nhưng số mục sai | Endpoint đang đọc một đối tượng dữ liệu khác hoặc logic đếm sai | Kiểm tra bean được tiêm và dữ liệu nguồn |

Trong ứng dụng thật, đường dẫn còn có thể bị ảnh hưởng bởi base path quản trị, context path hoặc cổng quản trị riêng. Bảng trên dùng các giá trị mặc định của dự án mẫu; không suy ra mọi ứng dụng đều có cùng URL đầy đủ.

Endpoint tùy chỉnh nên trả về thông tin cần thiết cho quan sát. Ví dụ chỉ công bố tên và số mục, tránh trả trực tiếp toàn bộ Map hoặc đối tượng dịch vụ với những dữ liệu không chủ định công bố.

## 9. Thực hành để hiểu đúng việc đăng ký

Thực hiện từng thay đổi riêng, khởi động lại và quan sát kết quả:

1. **Đổi tên phương thức thao tác** từ `read()` thành `snapshot()`. Giữ ID và annotation. Đường dẫn Actuator vẫn dựa trên `catalogcache`.
2. **Đổi bean name** bằng `@Bean("internalCatalogEndpoint")` trên phương thức tạo endpoint. Cập nhật assertion tên bean trong test, rồi kiểm tra URL không đổi.
3. **Bỏ riêng @Bean của endpoint**, giữ lớp `@Endpoint` không có `@Component`. Kiểm tra container không còn bean endpoint được tạo theo cấu hình đó.
4. **Khôi phục bean nhưng chỉ công bố health qua HTTP**. Kiểm tra riêng sự tồn tại bean và việc endpoint không còn trong tập web được công bố.
5. **Đổi endpoint ID** sang `catalogsummary`. Cập nhật cả danh sách exposure, thuộc tính enabled và đường dẫn trong test; không chỉ đổi tên lớp.
6. **Chọn cách @Component** và bỏ phương thức `@Bean` tương ứng. Kiểm tra endpoint được đăng ký đúng một lần.

Câu hỏi tự kiểm tra:

- `@Endpoint` có tự thay thế `@Component` không? **Không.**
- Phương thức `@Bean` có thể nhận dịch vụ phụ thuộc qua tham số không? **Có.**
- Tên bean có mặc định quyết định đường dẫn Actuator không? **Không; đường dẫn quản trị dựa trên endpoint ID và cấu hình web liên quan.**
- Gọi trực tiếp phương thức Java có chứng minh endpoint đã truy cập được qua HTTP không? **Không.**
- Có thể đăng ký bean đúng mà endpoint vẫn chưa được công bố qua HTTP không? **Có.**

Hoàn thành bài khi có thể chỉ rõ nơi định nghĩa endpoint, nơi Spring tạo bean và nơi cho phép HTTP công bố endpoint đó.
