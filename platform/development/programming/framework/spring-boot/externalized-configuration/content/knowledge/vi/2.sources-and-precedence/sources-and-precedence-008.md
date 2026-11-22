# Nguồn cấu hình kiểm thử và thiết lập toàn cục của Devtools

## 1. Vì sao hai loại cấu hình này quan trọng?

Ứng dụng Spring Boot có thể lấy giá trị từ file cấu hình, biến môi trường, Java system properties và tham số dòng lệnh. Khi chạy **kiểm thử** hoặc phát triển trên máy cá nhân, Spring Boot còn bổ sung những nguồn có mục đích rất cụ thể:

- **Nguồn cấu hình kiểm thử (test property sources)** giúp mỗi lớp test thiết lập dữ liệu, endpoint, timeout hoặc cổng dịch vụ cần thiết mà không phải sửa cấu hình vận hành thật.
- **Thiết lập toàn cục của Spring Boot DevTools (DevTools global settings)** cho phép lập trình viên áp dụng một số tùy chỉnh phát triển chung cho các ứng dụng Spring Boot có DevTools hoạt động trên cùng máy.

Cả hai đều tham gia vào **Spring Environment**, nơi các **PropertySource** được sắp xếp theo độ ưu tiên. Khi có nhiều nguồn cùng định nghĩa một key, ứng dụng nhận giá trị từ nguồn có độ ưu tiên cao nhất tại thời điểm giá trị đó được giải quyết.

Ví dụ: **app.service-url** trong **application.yml** trỏ đến API của môi trường phát triển. Một integration test có thể thay key đó bằng URL của mock server hoặc container do test tự khởi tạo. Trong khi đó, tùy chỉnh **spring.devtools.restart.trigger-file** ở thư mục người dùng là lựa chọn phục vụ quy trình phát triển cá nhân và có thể dùng cho nhiều dự án.

**Cần phân biệt:** thay cấu hình của một bài test không có nghĩa là sửa cấu hình chạy production; thiết lập DevTools trên máy người phát triển cũng không phải cấu hình triển khai của artifact.

## 2. Các nguồn test nằm ở đâu trong thứ tự ưu tiên?

Tài liệu **Spring Boot 3.3 — Externalized Configuration** liệt kê các PropertySource theo thứ tự từ ưu tiên thấp đến cao. Trích ra phần liên quan tới bài học:

| Nguồn | Vai trò | Ghi chú về phạm vi |
| --- | --- | --- |
| **application.properties / application.yml**, kể cả file theo profile | Giá trị cơ sở của ứng dụng | Thuộc nhóm Config Data, có thể ghi đè bằng nguồn bên ngoài phù hợp |
| **Biến môi trường** | Cấu hình cấp bởi hệ điều hành hoặc nền tảng triển khai | Cao hơn file Config Data thông thường |
| **Java system properties** | Các giá trị cấp cho JVM | Thường viết bằng tùy chọn **-D** |
| **Tham số dòng lệnh** | Các key cấp khi khởi động ứng dụng | Ví dụ **--app.message=hello** |
| **properties của @SpringBootTest** hoặc test slice | Giá trị trực tiếp dành cho test | Chỉ tác động đến ApplicationContext của test đó |
| **@DynamicPropertySource** | Giá trị do test đăng ký động | Hữu ích khi port hoặc địa chỉ tài nguyên chỉ biết sau khi tài nguyên khởi tạo |
| **@TestPropertySource** | File hoặc giá trị inline dành cho test | Dùng để đặt cấu hình có chủ đích tại cấp lớp test |
| **DevTools global settings** | Cấu hình toàn cục cho các ứng dụng có DevTools hoạt động | Có mặt khi DevTools thực sự tham gia chạy ứng dụng |

Đây là **các nguồn liên quan được rút ra** từ danh sách của Spring Boot; danh sách đầy đủ còn có nguồn giá trị mặc định, **@PropertySource**, **random.***, JNDI, servlet init parameters và **SPRING_APPLICATION_JSON**.

Một chi tiết cần hiểu đúng: tài liệu Spring Boot 3.3 liệt kê **@DynamicPropertySource** và **@TestPropertySource** ở các vị trí liền nhau, trong khi tài liệu **Spring TestContext** mô tả dynamic properties có thể ghi đè test properties. Vì những cơ chế này có vòng đời đăng ký khác nhau, **không nên cho cùng một key cạnh tranh đồng thời ở hai annotation để xây dựng logic test**. Nếu cần kiểm chứng trường hợp cụ thể, hãy đọc thứ tự và giá trị thực tế trong **ConfigurableEnvironment** của test đang chạy.

Quan trọng hơn việc nhớ một sơ đồ là đặt giá trị tại **đúng phạm vi**: giá trị mặc định trong file, giá trị riêng test trong test, giá trị phát sinh theo runtime của test qua dynamic source, và thói quen phát triển cá nhân qua DevTools global settings.

## 3. Ví dụ nền tảng: một property trong ứng dụng

Giả sử dự án đã có Spring Boot 3.3, Java 21 và **spring-boot-starter-test**. Trong **src/main/resources/application.yml**, khai báo:

~~~yaml
app:
  message: "from-application"
  remote-url: "https://dev-api.example.invalid"
~~~

Một bean có thể đọc hai giá trị này từ **Environment**:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MessageReader {
    private final Environment environment;

    public MessageReader(Environment environment) {
        this.environment = environment;
    }

    public String message() {
        return environment.getProperty("app.message");
    }

    public String remoteUrl() {
        return environment.getProperty("app.remote-url");
    }
}
~~~

Trong ứng dụng chạy thông thường, **message()** trả về **from-application** nếu không có nguồn cấu hình ưu tiên cao hơn ghi đè. Trong test, ta sẽ thay giá trị đó mà không sửa file YAML của ứng dụng.

## 4. @SpringBootTest(properties): giá trị inline cho một test

**@SpringBootTest** khởi động ApplicationContext của Spring Boot. Thuộc tính **properties** cho phép cung cấp trực tiếp các key cần ghi đè cho context của test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "app.message=from-spring-boot-test",
    "app.remote-url=http://localhost:9999"
})
class InlineConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void usesInlineTestProperties() {
        assertEquals("from-spring-boot-test", reader.message());
        assertEquals("http://localhost:9999", reader.remoteUrl());
    }
}
~~~

**Giải thích:**

1. **application.yml** vẫn chứa giá trị gốc.
2. Khi test khởi động, Spring Boot thêm nguồn giá trị của **@SpringBootTest(properties=...)** vào Environment của test.
3. Những key cùng tên được giải quyết theo nguồn test, nên các assertion nhận giá trị inline.
4. Khi chạy JAR bình thường, các annotation của test không được dùng để đặt cấu hình production.

Cơ chế này phù hợp với **một vài property cố định**, ví dụ vô hiệu hóa lịch chạy trong test, đổi timeout hoặc thay endpoint test. Nếu nhiều lớp test cần chung một bộ cấu hình, cân nhắc file test riêng thay vì lặp lại nhiều chuỗi trong annotation.

Các annotation test slice như **@WebMvcTest** cũng có thuộc tính **properties**; chúng dùng ApplicationContext với phạm vi riêng của slice. Không cần khởi động toàn bộ ứng dụng nếu chỉ kiểm tra một lớp web đơn lẻ.

## 5. @TestPropertySource: nguồn cấu hình riêng của kiểm thử

**@TestPropertySource** thuộc Spring TestContext Framework. Nó cho phép khai báo:

- **locations**: file **.properties** nằm trong classpath hoặc vị trí tài nguyên được hỗ trợ.
- **properties**: các cặp key–value viết trực tiếp trong annotation.

Giả sử tạo file **src/test/resources/config/lesson-test.properties**:

~~~properties
app.message=from-test-file
app.remote-url=http://localhost:8089
~~~

Sau đó dùng trong test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@TestPropertySource(locations = "classpath:config/lesson-test.properties")
class FileConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void readsTestPropertyFile() {
        assertEquals("from-test-file", reader.message());
        assertEquals("http://localhost:8089", reader.remoteUrl());
    }
}
~~~

Kết quả này chứng minh test có thể thay nguồn đọc cấu hình mà không sửa **src/main/resources/application.yml**.

**Thứ tự bên trong @TestPropertySource:** nếu cùng một key được khai báo trong cả file ở **locations** và danh sách **properties** inline, giá trị inline có ưu tiên cao hơn. Ví dụ:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:config/lesson-test.properties",
    properties = "app.message=from-inline-test-property"
)
class OverrideInsideTestPropertySourceTest {
    // Với key app.message, inline property thắng file trên.
}
~~~

**Lưu ý về YAML:** **@TestPropertySource** không trực tiếp nạp tài liệu YAML bằng **locations** theo cơ chế mặc định. Không đổi đuôi file thành **.yml** rồi mặc nhiên coi nó được hỗ trợ giống **.properties**. Nếu muốn dùng file YAML theo profile, hãy sử dụng cơ chế Config Data của Spring Boot cùng **@ActiveProfiles**, trình bày ở phần tiếp theo.

**Lưu ý về chia sẻ context:** Spring TestContext có cơ chế cache ApplicationContext. Các cấu hình test khác nhau có thể dẫn đến context cache key khác nhau; không nên thay đổi thuộc tính toàn cục tùy tiện giữa các test và kỳ vọng context đã cache sẽ tự khởi tạo lại.

## 6. @ActiveProfiles("test") và application-test.yml khác gì @TestPropertySource?

Một cách phổ biến để tổ chức test là tạo **src/test/resources/application-test.yml**:

~~~yaml
app:
  message: "from-test-profile"
  remote-url: "http://localhost:8088"
~~~

Kích hoạt profile **test**:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {

    @Autowired
    MessageReader reader;

    @Test
    void readsProfileConfiguration() {
        assertEquals("from-test-profile", reader.message());
        assertEquals("http://localhost:8088", reader.remoteUrl());
    }
}
~~~

Điểm khác nhau nằm ở **cơ chế nạp và mức ưu tiên**:

| Cách cấu hình | Được nạp bằng gì? | Dùng khi nào? |
| --- | --- | --- |
| **application-test.yml** + **@ActiveProfiles("test")** | Hệ thống Config Data và profile của Spring Boot | Một bộ giá trị test được chia sẻ, có cấu trúc YAML |
| **@TestPropertySource(locations=...)** | Spring TestContext | Muốn thêm trực tiếp một file properties dành cho lớp test |
| **@TestPropertySource(properties=...)** | Spring TestContext | Muốn ghi đè key cụ thể ngay trong lớp test |
| **@SpringBootTest(properties=...)** | Bootstrap test của Spring Boot | Muốn vài giá trị inline cho một Spring Boot test |
| **@DynamicPropertySource** | Spring TestContext với supplier | Giá trị chưa biết khi viết test, ví dụ port của container |

**@ActiveProfiles** xác định profile đang hoạt động; nó không biến file **application-test.yml** thành một nguồn **@TestPropertySource**. File profile vẫn ở nhóm Config Data, nên một giá trị test inline phù hợp có thể ghi đè nó.

Tên profile **test** là quy ước, không bắt buộc. Đừng dựa vào việc file **application-test.yml** tồn tại để suy luận profile đã được kích hoạt; test phải thực sự chọn profile thông qua một cơ chế hợp lệ.

## 7. @DynamicPropertySource: giá trị sinh ra khi test chạy

Một số giá trị không thể viết cố định trong YAML:

- Cổng được cấp ngẫu nhiên cho database container.
- URL của mock HTTP server khởi tạo lúc test.
- Host và port do môi trường integration test cấp phát.
- Mã truy cập tạm thời do test fixture tạo ra.

**@DynamicPropertySource** đăng ký những key này với **DynamicPropertyRegistry**. Phương thức được đánh dấu phải là **static**, nhận một tham số **DynamicPropertyRegistry**, và đưa vào một **Supplier** cho từng property.

Ví dụ khi integration test sử dụng **Testcontainers** và PostgreSQL:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DynamicDatabaseConfigurationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithContainerDatabase() {
        // App được cấu hình để kết nối DB của container test.
    }
}
~~~

Đoạn mã giả định dự án đã cài **Testcontainers**, PostgreSQL JDBC driver, dependency phù hợp của Spring Data/JDBC và có Docker phục vụ integration test. Nó minh họa đường đi của cấu hình; để chạy thành công cần phần thiết lập datasource thực tế của dự án.

Khi container được cấp một cổng khác giữa hai lần chạy, supplier như **postgres::getJdbcUrl** vẫn cung cấp giá trị phù hợp với lần chạy hiện tại. Nếu hardcode port đó vào **application-test.yml**, bài test có thể bị lỗi hoặc truy cập sai tài nguyên.

**Chọn nguồn theo tính chất giá trị:** key tĩnh và dùng chung có thể ở file test; key phát sinh khi chạy test nên đến từ **@DynamicPropertySource**. Tránh định nghĩa trùng một key ở nhiều annotation khi không có yêu cầu cụ thể về override.

## 8. Thiết lập DevTools toàn cục là gì?

**Spring Boot DevTools** là module hỗ trợ quá trình phát triển, ví dụ tự khởi động lại ứng dụng khi classpath được cập nhật, LiveReload và các giá trị mặc định thuận tiện khi lập trình. Để dùng trong một dự án Gradle có Spring Boot plugin, thông thường thêm:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Khi DevTools hoạt động, Spring Boot 3.3 có thể đọc cấu hình toàn cục trong thư mục **$HOME/.config/spring-boot/** của người đang chạy ứng dụng. Ba tên file được hỗ trợ là:

- **spring-boot-devtools.properties**
- **spring-boot-devtools.yaml**
- **spring-boot-devtools.yml**

Chỉ cần chọn một định dạng phù hợp. Không cần đặt file đó trong repository của dự án, và không cần copy cùng một tùy chỉnh DevTools sang hàng loạt **application.yml**.

Ví dụ nội dung file **$HOME/.config/spring-boot/spring-boot-devtools.properties**:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
spring.devtools.livereload.enabled=false
~~~

Ý nghĩa:

- **spring.devtools.restart.trigger-file** chọn tên file kích hoạt lượt kiểm tra restart. File **.reloadtrigger** cần xuất hiện trên classpath, chẳng hạn **src/main/resources/.reloadtrigger** của từng dự án muốn sử dụng thiết lập đó. Việc cập nhật file trigger dẫn đến kiểm tra restart khi có thay đổi cần xử lý.
- **spring.devtools.livereload.enabled=false** tắt máy chủ LiveReload của DevTools nếu lập trình viên không sử dụng tiện ích cập nhật trang tương ứng.

Ví dụ tương đương bằng YAML:

~~~yaml
spring:
  devtools:
    restart:
      trigger-file: ".reloadtrigger"
    livereload:
      enabled: false
~~~

**Toàn cục** ở đây nghĩa là **trên máy và trong thư mục người dùng**, áp dụng cho những ứng dụng sử dụng DevTools ở nơi đó. Đây không phải là file cấu hình toàn cục của Spring Boot cho toàn bộ server, không phải cấu hình chung qua mạng và cũng không tự đồng bộ sang máy đồng nghiệp.

### Thư mục tìm kiếm và khả năng tùy chỉnh

Mặc định **$HOME** là home directory của người dùng. Có thể điều chỉnh vị trí bằng biến môi trường **SPRING_DEVTOOLS_HOME** hoặc Java system property **spring.devtools.home**.

Nếu không tìm thấy file DevTools trong **$HOME/.config/spring-boot/**, Spring Boot 3.3 còn kiểm tra file cũ **$HOME/.spring-boot-devtools.properties** để tương thích với các phiên bản trước. Với dự án mới, nên dùng đường dẫn **.config/spring-boot** được tài liệu hiện hành của dòng 3.3 mô tả.

### Giới hạn liên quan đến profile

File DevTools global **không hỗ trợ profile-specific variants** như **spring-boot-devtools-prod.properties**. Nó cũng không hỗ trợ các tài liệu kích hoạt bằng **spring.config.activate.on-profile** bên trong file global.

Đặc biệt, cố đặt **spring.profiles.active** trong global DevTools file không phải một cách hợp lệ để điều khiển việc nạp **application-{profile}.yml**. Profile phải được chọn từ cơ chế cấu hình ứng dụng phù hợp và đủ sớm, chẳng hạn môi trường chạy, tham số khởi động hoặc test annotation.

## 9. Vì sao DevTools global có thể khiến giá trị “bị ghi đè”?

Trong danh sách PropertySource của Spring Boot 3.3, **DevTools global settings** được liệt kê ở phần ưu tiên cao khi DevTools hoạt động. Điều đó giải thích vì sao lập trình viên có thể thấy thiết lập trên máy mình thắng giá trị tưởng như được khai báo trong file dự án.

Ví dụ:

**Trong application.yml của một dự án:**

~~~yaml
spring:
  devtools:
    livereload:
      enabled: true
~~~

**Trong global DevTools file của máy lập trình viên:**

~~~properties
spring.devtools.livereload.enabled=false
~~~

Trong phiên chạy mà DevTools và global settings thực sự hoạt động, cấu hình toàn cục có thể quyết định giá trị hiệu lực của key này. Một đồng nghiệp không có global file đó có thể quan sát hành vi khác, dù cùng checkout mã nguồn.

Điều cần làm khi gặp khác biệt giữa các máy là kiểm tra cả file dự án **lẫn cấu hình DevTools trong home directory**. Không nên sửa mã nguồn hoặc file production để “khắc phục” một tùy chọn phát triển chỉ tồn tại trên một máy.

**DevTools không dành cho production.** Với cấu hình Gradle **developmentOnly**, dependency này không được đóng gói vào executable JAR mặc định. Spring Boot cũng tự vô hiệu hóa DevTools ở một số kiểu chạy ứng dụng đã đóng gói như **java -jar**. Không nên cố bật DevTools trong production để tận dụng file cấu hình toàn cục của người phát triển.

## 10. Cách xác định nguồn thực sự đang cấp giá trị

Khi thấy một property có giá trị khác mong đợi, việc nhìn duy nhất **application.yml** không đủ. Trong Spring test, có thể kiểm tra **ConfigurableEnvironment** để xem những nguồn nào chứa key đó, theo thứ tự mà Environment đang dùng.

Ví dụ trong test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootTest(properties = "app.message=from-inline-test")
class PropertySourceInspectionTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Test
    void inspectMessageSource() {
        String key = "app.message";

        System.out.println("Resolved: " + environment.getProperty(key));

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object localValue = source.getProperty(key);
            if (localValue != null) {
                System.out.println(source.getName() + " => " + localValue);
            }
        }
    }
}
~~~

**Cách đọc kết quả:**

1. **getProperty(key)** cho biết giá trị cuối cùng được giải quyết.
2. **getPropertySources()** cho biết các nguồn theo thứ tự tìm kiếm của Environment.
3. Với một key có mặt ở nhiều nguồn, nguồn được xét trước và có giá trị hợp lệ thường quyết định kết quả.
4. Tên nguồn có thể phụ thuộc phiên bản Spring và cách ApplicationContext được dựng; không viết logic sản phẩm phụ thuộc vào một tên nguồn nội bộ cụ thể.

Chỉ sử dụng đoạn in giá trị này cho **key không nhạy cảm** như **app.message**. Tuyệt đối không in mật khẩu, token hoặc các key chứa bí mật vào log để debug thứ tự ưu tiên.

Nếu dự án dùng Spring Boot Actuator, endpoint **env** có thể hỗ trợ điều tra property source khi được cấu hình và bảo vệ phù hợp. Tránh công khai endpoint này cho người không có quyền; dữ liệu cấu hình có thể nhạy cảm.

## 11. Những nhầm lẫn thường gặp

**Nhầm @ActiveProfiles với @TestPropertySource.** Profile chọn tập file Config Data phù hợp; **@TestPropertySource** chủ động bổ sung nguồn cấu hình riêng của Spring TestContext. Hai cơ chế có thể dùng cùng nhau, nhưng không cùng bản chất.

**Cho rằng @TestPropertySource đọc YAML như application.yml.** Theo cơ chế mặc định, annotation này không hỗ trợ nạp YAML trực tiếp qua **locations**. Dùng **.properties** cho annotation hoặc **application-test.yml** cùng profile nếu muốn YAML.

**Đặt port cố định cho test container.** Cổng do Docker cấp có thể thay đổi. Dùng **@DynamicPropertySource** để đăng ký endpoint thực tế khi test chạy sẽ phản ánh đúng tài nguyên đang dùng.

**Phân tán cùng một key ở nhiều annotation.** Khi cùng key xuất hiện trong **@SpringBootTest(properties)**, **@TestPropertySource** và **@DynamicPropertySource**, việc hiểu test sẽ khó hơn. Chọn một nguồn rõ ràng cho mỗi key, rồi truy vết bằng Environment khi cần.

**Nghĩ DevTools global file thuộc repository.** Nó nằm trong home directory của mỗi người, có thể tác động tới nhiều dự án trên máy đó. Việc một đồng nghiệp không tái hiện được vấn đề có thể xuất phát từ thiết lập cá nhân.

**Nhầm global DevTools với cấu hình production.** DevTools phục vụ phát triển. Cấu hình của môi trường triển khai phải được cấp bằng cơ chế triển khai dành cho môi trường đó, không dựa vào một file DevTools trên laptop.

**Cố kích hoạt profile từ file global DevTools.** Các file global này không cung cấp cơ chế profile-specific; thay vào đó dùng **@ActiveProfiles** cho test hoặc nguồn cấp **spring.profiles.active** phù hợp khi khởi động ứng dụng.

## 12. Bài thực hành tự kiểm chứng

**Bài A — thay giá trị từ annotation test**

1. Đặt **app.message=from-application** trong **application.yml**.
2. Tạo test **@SpringBootTest(properties = "app.message=from-test")**.
3. Đọc giá trị bằng **Environment.getProperty("app.message")** và kiểm tra là **from-test**.
4. Chạy ứng dụng bình thường để nhận lại **from-application** khi không có override khác.

**Bài B — tách cấu hình test bằng file**

1. Tạo **src/test/resources/config/lesson-test.properties** với **app.message=from-file**.
2. Dùng **@TestPropertySource(locations = "classpath:config/lesson-test.properties")**.
3. Kiểm tra giá trị của **app.message** trong test.
4. Thêm **properties = "app.message=from-inline"** ngay trong annotation đó rồi quan sát giá trị mới.

**Bài C — dùng profile test**

1. Tạo **src/test/resources/application-test.yml** với **app.message=from-profile**.
2. Kích hoạt **@ActiveProfiles("test")** trên một lớp **@SpringBootTest**.
3. Kiểm tra **from-profile** được nạp từ Config Data.
4. Thử thêm một giá trị inline trong **@SpringBootTest(properties)** và quan sát override.

**Bài D — kiểm tra DevTools global**

1. Thêm dependency **spring-boot-devtools** trong cấu hình **developmentOnly**.
2. Tạo file **spring-boot-devtools.properties** trong thư mục **$HOME/.config/spring-boot/** với nội dung **spring.devtools.livereload.enabled=false**.
3. Khởi động ứng dụng ở chế độ phát triển có DevTools, kiểm tra thiết lập hiệu lực.
4. Thử tạm đổi giá trị ở file global rồi khởi động lại để thấy cấu hình cục bộ có tác động tới dự án.
5. Kiểm tra rằng thao tác này không sửa **application.yml** của dự án hoặc nội dung của JAR phát hành.

Trong các bài thực hành, chỉ thay các key phục vụ ví dụ; không cần tạo secret thật và không phụ thuộc vào dịch vụ production.

## 13. Ghi nhớ

- **Test properties** phục vụ một lần chạy hoặc ApplicationContext kiểm thử; chọn annotation hoặc file test tùy nhu cầu.
- **@SpringBootTest(properties)** phù hợp với override nhỏ, **@TestPropertySource** với tài nguyên/cặp key của test, **@DynamicPropertySource** với giá trị phát sinh khi test chạy.
- **@ActiveProfiles("test")** chọn cấu hình theo profile; file **application-test.yml** vẫn là Config Data.
- **DevTools global settings** là lựa chọn cấp người dùng trên máy phát triển, có hiệu lực khi DevTools hoạt động và không hỗ trợ cơ chế profile-specific.
- Khi có nhiều giá trị cho cùng key, **ConfigurableEnvironment** cho phép truy vết nguồn và giải thích kết quả thực tế.

**Tài liệu tham khảo chính thức:**

- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Developer Tools, Global Settings: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
