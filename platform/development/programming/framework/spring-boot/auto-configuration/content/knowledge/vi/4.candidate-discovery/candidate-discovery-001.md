# Đăng ký auto-configuration bằng META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

## 1. Mục tiêu và vấn đề cần giải quyết

Một thư viện có thể cung cấp lớp `@AutoConfiguration` để ứng dụng Spring Boot tự nhận cấu hình mặc định khi thêm thư viện vào classpath. Nhưng **chỉ viết annotation trên class không khiến Spring Boot tự tìm được class đó**. Trong cơ chế Spring Boot hiện đại, tác giả thư viện còn phải đăng ký **tên lớp đầy đủ** trong một tệp tài nguyên đặc biệt:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đây là **đường dẫn tương đối tính từ gốc classpath của JAR** chứa auto-configuration. Trong dự án Maven hoặc Gradle thông thường, mã nguồn tài nguyên cần đặt tại:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Khi biên dịch/đóng gói, tài nguyên phải thật sự có mặt trong output runtime. Trong một JAR thư viện thông thường, đường dẫn bên trong JAR là `META-INF/spring/...imports`. Trong executable Spring Boot JAR, tài nguyên của module ứng dụng thường nằm dưới `BOOT-INF/classes/META-INF/spring/...imports`; tài nguyên của JAR thư viện đi kèm nằm trong JAR lồng dưới `BOOT-INF/lib`.

Sau bài học, bạn sẽ biết vì sao Spring Boot cần tệp này, cách ghi đúng từng dòng, xây ví dụ Java 17+ có thể chạy, quan sát kết quả có hoặc thiếu metadata, và tìm lỗi khi auto-configuration không được kích hoạt.

**Phạm vi:** chỉ tập trung cơ chế *đăng ký và phát hiện ứng viên auto-configuration*. Các điều kiện `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và thứ tự cấu hình được giải thích trong giới hạn cần thiết, vì **đăng ký ứng viên chưa bảo đảm bean được tạo**.

## 2. Vai trò của tệp AutoConfiguration.imports

Spring Boot tìm các tệp tài nguyên có tên chính xác `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trên classpath. Mỗi JAR thư viện có thể chứa một tệp riêng. Boot tổng hợp các lớp auto-configuration được khai báo, sau đó áp dụng quy trình chọn, loại trừ, sắp xếp và điều kiện để quyết định những cấu hình nào tham gia context.

Nội dung tệp là **văn bản thuần**, ví dụ:

~~~text
com.example.invoice.autoconfigure.InvoiceAutoConfiguration
com.example.invoice.autoconfigure.InvoiceWebAutoConfiguration
~~~

Quy tắc:

1. **Mỗi dòng là một fully qualified class name (FQCN)**, gồm package và tên class Java. Không ghi tên ngắn như `InvoiceAutoConfiguration` nếu class nằm trong package.
2. **Không thêm `.class`**, không ghi cú pháp `import ...;`, không dùng JSON, XML, YAML hoặc `key=value` như `spring.factories`.
3. Dòng bắt đầu bằng ký tự `#` có thể dùng làm chú thích:

   ~~~text
   # Auto-configuration cho dịch vụ hóa đơn
   com.example.invoice.autoconfigure.InvoiceAutoConfiguration
   ~~~

4. Tên file phân biệt chữ hoa/chữ thường trên những hệ thống file tương ứng: phải đúng `AutoConfiguration.imports`; không dùng `autoconfiguration.imports` hoặc `AutoConfiguration.import`.
5. Đường dẫn `META-INF/spring` phải nằm **trong tài nguyên được đóng gói**, không chỉ tồn tại trong cây mã nguồn.
6. Nếu auto-configuration là lớp lồng không phải top-level, tên nhị phân dùng `$` giữa tên lớp bao ngoài và lớp lồng, ví dụ `com.example.Outer$NestedAutoConfiguration`. Trong thư viện thực, ưu tiên top-level class để dễ quản lý.

Cơ chế này **không phải tệp đăng ký bean trực tiếp**. Tệp liệt kê **lớp cấu hình ứng viên**, không liệt kê tên phương thức `@Bean`, interface dịch vụ hay class implementation sẽ được tạo.

### So sánh với các tệp dễ nhầm

| Tệp hoặc cơ chế | Vai trò |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Đăng ký các **lớp auto-configuration ứng viên** trong Spring Boot hiện đại. |
| `META-INF/spring.factories` | Một cơ chế metadata dạng properties được dùng cho nhiều Spring Boot extension như `EnvironmentPostProcessor` và `ApplicationContextInitializer`; các hướng dẫn auto-configuration cũ từng dùng `EnableAutoConfiguration` ở đây. |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata tối ưu hóa việc lọc một số auto-configuration; thường được tạo bởi annotation processor, **không thay thế imports file**. |
| `META-INF/spring-configuration-metadata.json` | Metadata gợi ý tên/kiểu/ý nghĩa `@ConfigurationProperties` cho IDE và công cụ; **không đăng ký auto-configuration**. |
| `@ComponentScan` | Quét component của ứng dụng trong các package cụ thể; **không phải cơ chế đúng để phát hiện thư viện auto-configuration**. |
| `@Import(SomeConfiguration.class)` | Import một cấu hình cụ thể ở vị trí được chỉ định; không phải cách công bố toàn bộ ứng viên của một starter cho Boot. |

Spring Boot 2.7 đã giới thiệu cơ chế imports file; với Spring Boot 3.x, đây là cơ chế chuẩn để khai báo auto-configuration. Nếu tham khảo dự án Spring Boot 2.x cũ dùng `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories`, hãy kiểm tra chính xác phiên bản và lộ trình chuyển đổi trước khi áp dụng. **Không kết luận rằng mọi mục đích dùng `spring.factories` đều lỗi thời**: những extension khác vẫn dùng cơ chế đó ở những phiên bản phù hợp.

## 3. Dòng chảy: tệp metadata tham gia khởi động khi nào?

Ở ứng dụng có `@SpringBootApplication` hoặc `@EnableAutoConfiguration`, cơ chế auto-configuration được bật. Có thể hình dung luồng:

~~~text
Ứng dụng gọi SpringApplication.run(...)
       |
       v
@SpringBootApplication
  └── @EnableAutoConfiguration
       |
       v
AutoConfigurationImportSelector (DeferredImportSelector)
       |
       +-- Tìm tài nguyên AutoConfiguration.imports trên classpath
       +-- Đọc danh sách tên lớp ứng viên từ các JAR
       +-- Áp dụng exclusions, filters và ordering
       |
       v
Spring xử lý các lớp @AutoConfiguration được chọn
       |
       +-- @ConditionalOnClass, @ConditionalOnProperty, ...
       +-- @Bean + @ConditionalOnMissingBean, ...
       |
       v
Đăng ký những bean definitions hợp lệ
       |
       v
Bean factory tạo các bean cần thiết theo vòng đời Spring
~~~

Bốn khái niệm cần tách:

- **Classpath có JAR:** điều này chỉ chứng minh thư viện đã được cung cấp cho ứng dụng. Chưa chắc có metadata imports.
- **Tìm được imports entry:** Boot biết tên một auto-configuration ứng viên. Chưa chắc lớp được chọn sau bước lọc và exclude.
- **Lớp auto-configuration được chọn và điều kiện khớp:** Spring có thể đăng ký bean definitions do lớp đó khai báo.
- **Bean thực sự tồn tại và khởi tạo thành công:** còn phụ thuộc điều kiện tại `@Bean`, sự hiện diện của bean khác, dependency, scope và lỗi runtime.

`AutoConfigurationImportSelector` triển khai `DeferredImportSelector` nên các auto-configuration được xử lý ở pha import trì hoãn, sau cấu hình thông thường của ứng dụng. Điều này giúp các điều kiện dựa trên bean, đặc biệt `@ConditionalOnMissingBean`, có cơ hội nhận ra bean do ứng dụng cung cấp trước khi đăng ký mặc định. “Deferred” ở đây **không có nghĩa tải tài nguyên ở thread nền, chờ request đầu tiên hoặc khởi tạo bean sau khi ứng dụng sẵn sàng**.

### Vì sao một JAR có thể có nhiều dòng imports?

Một thư viện có thể tích hợp nhiều phần tùy chọn. Chẳng hạn, một cấu hình cho core service và một cấu hình chỉ dành cho web servlet. Tác giả có thể liệt kê cả hai lớp làm **ứng viên** rồi áp dụng điều kiện thích hợp trên từng lớp. Nếu không có thư viện web cần thiết, cấu hình web có thể bị bỏ qua. Mỗi dòng trong imports file không phải công tắc “bật vô điều kiện”.

## 4. Cấu trúc và đặt package đúng cách

Một cách tổ chức minh họa:

~~~text
invoice-spring-boot/
├── pom.xml
└── src/main/
    ├── java/
    │   └── com/example/invoice/
    │       ├── api/InvoiceFormatter.java
    │       └── autoconfigure/InvoiceAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Khi ứng dụng sử dụng thư viện này, chỉ cần thêm dependency chứa auto-configuration và có bật auto-configuration; Boot sẽ nhìn thấy metadata trên classpath. Trong dự án lớn, có thể chia một module `invoice-spring-boot-autoconfigure` chứa code/metadata và một module `invoice-spring-boot-starter` gom dependencies phù hợp; **không bắt buộc chia module** nếu bài toán nhỏ.

Lớp cấu hình thường viết:

~~~java
package com.example.invoice.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.example.invoice.api.InvoiceFormatter")
public class InvoiceAutoConfiguration {

    // Các @Bean tùy chọn phù hợp được định nghĩa tại đây.
}
~~~

Đây là snippet minh họa cơ chế annotation; phần thân chưa có `@Bean` và không tạo bean nào. Có annotation trên class nhưng chưa có entry trong imports file thì ứng dụng bên ngoài **chưa được bảo đảm** sẽ phát hiện cấu hình này theo cơ chế auto-configuration.

**Khuyến nghị từ tài liệu Spring Boot:** để auto-configuration trong package chuyên biệt và **không nằm trong vùng bị component scanning quét**. Không tự thêm `@ComponentScan` vào auto-configuration để lấy các bean một cách khó kiểm soát; khi cần import cấu hình cụ thể, dùng `@Import` có chủ đích. Tách package giúp điều kiện và thứ tự Boot điều phối hoạt động đúng mục đích.

### Tại sao đừng nhầm “file hiện diện” với “file có hiệu lực”?

Ví dụ tệp tồn tại tại `src/test/resources/META-INF/spring/...` nhưng không nằm trong main runtime artifact; khi chạy JAR phát hành, Boot sẽ không thấy nó. Tương tự, viết metadata đúng trong module A nhưng ứng dụng không phụ thuộc module A ở runtime thì metadata cũng vắng trên classpath. Vấn đề là **classpath của tiến trình đang chạy**, không phải chỉ trạng thái file trong IDE.

## 5. Ví dụ Java 17+ hoàn chỉnh: một file metadata, ba kết quả bean

Ta tạo một ứng dụng Spring Boot nhỏ, trong đó:

- `@AutoConfiguration` nằm ngoài package component scan của ứng dụng.
- `AutoConfiguration.imports` đăng ký chính xác tên lớp.
- Auto-configuration thêm `MessageService` mặc định nếu chưa có bean cùng loại.
- Ứng dụng có thể bật bean riêng; auto-configuration phải lùi bước.
- Có thể tắt auto-configuration mẫu bằng property để chứng minh entry trong imports file **không đồng nghĩa luôn tạo bean**.

Mọi mã đều độc lập trong project ví dụ. Dùng **Spring Boot 3.5.0, JDK 17+ và Maven**.

### 5.1. Cấu trúc dự án

~~~text
auto-imports-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/MessageService.java
    │   ├── app/DemoApplication.java
    │   └── autoconfigure/MessageAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Package của lớp ứng dụng là `com.example.app`; package của auto-configuration là `com.example.autoconfigure`. Component scan mặc định từ `com.example.app` **không** quét `com.example.autoconfigure`. Tập tin imports chính là yếu tố đưa cấu hình mẫu vào ứng dụng.

### 5.2. pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>auto-imports-demo</artifactId>
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

`spring-boot-starter` cung cấp những thành phần cốt lõi để chạy Spring Boot không cần web server. Ví dụ không cần database, HTTP endpoint hoặc service bên ngoài.

### 5.3. MessageService.java

Tệp `src/main/java/com/example/api/MessageService.java`:

~~~java
package com.example.api;

public interface MessageService {
    String message();
}
~~~

Chỉ có interface trong `classpath` không tự tạo bean. Nó đóng vai trò type chung cho bean ứng dụng và bean mặc định.

### 5.4. MessageAutoConfiguration.java

Tệp `src/main/java/com/example/autoconfigure/MessageAutoConfiguration.java`:

~~~java
package com.example.autoconfigure;

import com.example.api.MessageService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageService.class)
    public MessageService defaultMessageService() {
        return () -> "AUTO";
    }
}
~~~

Giải thích:

- `@AutoConfiguration` công bố đây là lớp cấu hình tự động.
- `@ConditionalOnProperty` trên lớp cho phép áp dụng khi `demo.auto=true` hoặc khi khóa này vắng mặt; `--demo.auto=false` làm điều kiện không khớp.
- `@ConditionalOnMissingBean(MessageService.class)` tại phương thức `@Bean` bảo đảm bean mặc định chỉ được đăng ký khi chưa có bean `MessageService` phù hợp trong context ở thời điểm điều kiện được đánh giá.
- Phương thức trả về một lambda Java triển khai interface `MessageService`. Output `AUTO` là dữ liệu do ví dụ quy định, không phải bean đặc biệt có sẵn trong Boot.

### 5.5. Tạo đúng AutoConfiguration.imports

Tạo tệp văn bản **không có phần mở rộng bổ sung** tại đường dẫn:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung đầy đủ, duy nhất một dòng:

~~~text
com.example.autoconfigure.MessageAutoConfiguration
~~~

Điểm dễ sai:

- Tên class trong file phải trùng hoàn toàn với `package com.example.autoconfigure;` và tên `public class MessageAutoConfiguration`.
- Không thêm `.java` hay `.class`.
- Không viết `org.springframework.boot.autoconfigure.EnableAutoConfiguration=\` ở đầu tệp; đó là cú pháp của một cơ chế legacy khác.
- Tệp phải được sao chép vào output main resources để có mặt khi chạy JAR.

### 5.6. DemoApplication.java

Tệp `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.MessageService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "custom",
            havingValue = "true"
    )
    MessageService customMessageService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner report(ObjectProvider<MessageService> services) {
        return args -> {
            MessageService service = services.getIfAvailable();
            System.out.println("MESSAGE_SERVICE="
                    + (service == null ? "NONE" : service.message()));
        };
    }
}
~~~

`customMessageService` là bean do ứng dụng cung cấp khi `demo.custom=true`. `ObjectProvider` cho phép lấy bean nếu có và trả về `null` khi không có bean; vì thế lần chạy không có bean nào vẫn in `NONE` và không làm khởi động thất bại chỉ vì tiêm bắt buộc.

### 5.7. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Bỏ phần lớn banner/log khởi động để quan sát stdout từ chương trình rõ ràng hơn. Trong cấu hình mẫu không có giá trị `demo.auto` hoặc `demo.custom` ở file; ta truyền qua command-line cho từng tình huống.

### 5.8. Đóng gói và chạy

Cài JDK 17+ và Maven. Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/auto-imports-demo-1.0.0.jar
~~~

Dòng stdout do chương trình tự in:

~~~text
MESSAGE_SERVICE=AUTO
~~~

Lý do: imports file khiến Boot phát hiện `MessageAutoConfiguration`; không có `demo.custom` nên bean ứng dụng không được tạo; điều kiện auto mặc định cho phép và `@ConditionalOnMissingBean` khớp.

Chạy khi ứng dụng cung cấp bean tùy chỉnh:

~~~bash
java -jar target/auto-imports-demo-1.0.0.jar --demo.custom=true
~~~

Dòng stdout:

~~~text
MESSAGE_SERVICE=CUSTOM
~~~

Auto-configuration có thể được phát hiện và áp dụng, nhưng bean `defaultMessageService` lùi bước vì bean ứng dụng cùng type đã được khai báo.

Chạy khi tắt cấu hình mặc định và không bật tùy chỉnh:

~~~bash
java -jar target/auto-imports-demo-1.0.0.jar --demo.auto=false
~~~

Dòng stdout:

~~~text
MESSAGE_SERVICE=NONE
~~~

Auto-configuration ứng viên có tên trong imports file nhưng không vượt qua điều kiện property; context không có `MessageService`.

Chạy khi tắt mặc định nhưng bật bean ứng dụng:

~~~bash
java -jar target/auto-imports-demo-1.0.0.jar --demo.auto=false --demo.custom=true
~~~

Dòng stdout:

~~~text
MESSAGE_SERVICE=CUSTOM
~~~

Bean ứng dụng hoạt động độc lập với việc auto-configuration mẫu có khớp điều kiện hay không.

| Tình huống | Auto-configuration được phát hiện? | Điều kiện bean mặc định | Bean cuối cùng |
| --- | --- | --- | --- |
| Chạy mặc định | Có, nếu imports file được đóng gói đúng | Khớp | `AUTO` |
| `--demo.custom=true` | Có | `@ConditionalOnMissingBean` không khớp | `CUSTOM` |
| `--demo.auto=false` | Có | Cấu hình bị loại bởi property | Không có |
| `--demo.auto=false --demo.custom=true` | Có | Cấu hình bị loại bởi property | `CUSTOM` |

Điều quan trọng: **bốn lần chạy đều giữ nguyên imports file**. Việc biến đổi kết quả chứng minh “đã đăng ký ứng viên” khác với “chắc chắn tồn tại bean”.

### 5.9. Thí nghiệm kiểm tra thiếu imports file

Để đối chiếu vai trò của tệp metadata, trong một **bản sao riêng** của dự án mẫu hãy tạm bỏ tệp `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, build lại từ đầu rồi chạy mặc định:

~~~bash
mvn -q clean package -DskipTests
java -jar target/auto-imports-demo-1.0.0.jar
~~~

Khi class `MessageAutoConfiguration` không bị component scan quét và không còn metadata đăng ký, kết quả kỳ vọng là:

~~~text
MESSAGE_SERVICE=NONE
~~~

Vẫn có class `MessageAutoConfiguration` trong artifact nhưng Boot không tự chọn nó thông qua cơ chế imports. Sau thí nghiệm, khôi phục tệp imports và build lại để đưa dự án về cấu hình bình thường.

**Lưu ý an toàn khi thử nghiệm:** chỉ làm thí nghiệm này trên dự án ví dụ hoặc bản sao, vì gỡ metadata trong thư viện sản xuất sẽ làm các ứng dụng sử dụng thư viện mất auto-configuration đã công bố.

## 6. Kiểm tra thực tế tài nguyên sau khi build

Nên xác minh bằng **artifact cuối**, thay vì tin rằng IDE đã copy resource.

Với JAR vừa tạo:

~~~bash
jar tf target/auto-imports-demo-1.0.0.jar
~~~

Đây là lệnh liệt kê nhiều entry, nên không có stdout ngắn cố định. Trong executable JAR do `spring-boot-maven-plugin` đóng gói, tìm đường dẫn:

~~~text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Với một **JAR thư viện thường** không được repackaging thành executable JAR, tìm:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu không tìm thấy:

1. Xác nhận nguồn nằm dưới `src/main/resources`, không phải `src/test/resources`.
2. Kiểm tra tên tệp, package thư mục và chữ hoa/chữ thường.
3. Xem phần `<resources>` trong Maven hoặc thiết lập `sourceSets` của Gradle có vô tình loại metadata không.
4. Đảm bảo lệnh build đang chạy ở module chứa auto-configuration; với multi-module project, không lấy nhầm JAR của module starter rỗng thay vì module autoconfigure.
5. Đảm bảo module đúng nằm trên **runtime classpath** của ứng dụng thật. Dependency `test` hoặc `provided` có thể không xuất hiện ở nơi cần thiết tùy cách đóng gói.
6. Kiểm tra tên FQCN trong file và class tương ứng sau khi đổi package hoặc refactor.

Để thấy **nội dung** file được đóng gói, một cách kiểm tra là mở JAR bằng công cụ ZIP/JAR hoặc dùng `jar xf` trong thư mục kiểm tra riêng rồi đọc đúng tài nguyên. Lệnh `jar tf` chỉ cho thấy tên entry, không hiển thị nội dung.

### Trường hợp Maven nhiều module

Với kiến trúc hai module:

~~~text
my-feature/
├── feature-autoconfigure/
│   ├── src/main/java/.../FeatureAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── feature-spring-boot-starter/
    └── pom.xml  (khai báo dependency tới feature-autoconfigure)
~~~

Phải bảo đảm:

- Metadata đi cùng **JAR chứa auto-configuration** hoặc một JAR nằm trên classpath runtime và tên class cũng khả dụng.
- Starter cung cấp đúng dependencies để ứng dụng kéo được module auto-configuration vào runtime.
- Thêm starter vào ứng dụng làm các tài nguyên imports của dependency được Boot thấy; không bắt buộc mỗi starter phải có imports file riêng nếu file nằm đúng trong module mà starter kéo theo.
- Nếu thư viện có các dependency tùy chọn, dùng điều kiện như `@ConditionalOnClass` để tránh tham chiếu class không có; không cố ép toàn bộ optional libraries thành required chỉ để phát hiện config.

## 7. Phát hiện ứng viên không đồng nghĩa điều kiện luôn khớp

Tệp imports chỉ là **một bước trong pipeline**. Các nguyên nhân bean không xuất hiện dù metadata đúng gồm:

### Lớp bị loại trừ

Ứng dụng có thể loại một auto-configuration bằng `exclude`, `excludeName` trên `@SpringBootApplication`/`@EnableAutoConfiguration` hoặc bằng `spring.autoconfigure.exclude`. Khi đó Boot biết lớp ứng viên nhưng không áp dụng lớp bị exclude. Dùng loại trừ khi có lý do, không coi đây là cách khắc phục metadata.

Ví dụ cấu hình loại trừ **lớp thật của dự án mẫu**:

~~~properties
spring.autoconfigure.exclude=com.example.autoconfigure.MessageAutoConfiguration
~~~

Với `demo.custom` vắng mặt, đây cũng sẽ làm `MessageService` mặc định không được đăng ký dù imports file vẫn tồn tại. Nếu cần chạy demo nhiều lần, không lưu property exclude cố định mà có thể truyền bằng command-line.

### Điều kiện lớp không khớp

`@ConditionalOnClass` hoặc `@ConditionalOnProperty` trên auto-configuration có thể loại lớp. Điều kiện phù hợp giúp thư viện an toàn khi những công nghệ phụ thuộc không có sẵn.

### Điều kiện tại @Bean không khớp

Lớp auto-configuration có thể được xử lý nhưng một phương thức `@Bean` bị bỏ qua, ví dụ do `@ConditionalOnMissingBean` tìm thấy bean ứng dụng. Trong ví dụ, `--demo.custom=true` tạo tình huống này.

### Lỗi tạo bean khác với lỗi phát hiện metadata

Nếu definition đã được đăng ký nhưng constructor bean ném exception hoặc thiếu dependency bắt buộc, context có thể không khởi động thành công. Lỗi này cần phân tích exception chain; nó không chứng minh file imports không hoạt động.

### Lỗi tên package khi import

Một tên FQCN sai có thể dẫn đến lỗi khi Boot cố đọc hoặc tải thông tin cấu hình, tùy pha xử lý; đừng kỳ vọng Boot luôn bỏ qua im lặng. Sửa đúng tên class trong metadata, và tránh suy luận chỉ từ thông điệp ngắn đầu tiên trong stack trace.

## 8. Debug bằng condition report và kiểm tra classpath

Khi nghi vấn “lớp đã đăng ký nhưng không có bean”, hãy đi theo thứ tự:

1. **Xem JAR và runtime classpath** để chắc chắn imports file nằm trong artifact đã chạy.
2. **Đọc nội dung imports file** xem có đúng FQCN, có dòng bị viết sai hay vừa đổi package không.
3. **Xác nhận bật auto-configuration** qua `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.
4. **Kiểm tra exclusions** của ứng dụng.
5. **Xem Condition Evaluation Report** để biết lớp hoặc bean bị loại bởi điều kiện nào.
6. **Kiểm tra bean trong context** để phân biệt lớp được chọn với bean đã tạo.
7. **Nếu vẫn lỗi**, đối chiếu phiên bản Spring Boot, dependency graph và dấu vết startup.

Đối với ví dụ ở phần 5, có thể bật debug logging bằng:

~~~bash
java -jar target/auto-imports-demo-1.0.0.jar --debug --logging.level.root=INFO
~~~

Tìm `MessageAutoConfiguration` hoặc `MessageAutoConfiguration#defaultMessageService` trong condition report. Nội dung báo cáo có thể khác theo phiên bản và điều kiện, nên không giả định chuỗi log cố định. Các mục “negative matches” nhiều khi là kết quả bình thường của quá trình chọn cấu hình.

Bạn cũng có thể dùng `ApplicationContextRunner` trong kiểm thử auto-configuration để tạo context nhỏ với các bean/properties khác nhau. Tuy nhiên, nếu kiểm thử bằng cách **chỉ định trực tiếp lớp auto-configuration** trong `AutoConfigurations.of(...)`, bài test đó **không tự chứng minh imports file đã được đóng gói/được khám phá**. Cần thêm một kiểm tra tài nguyên đóng gói hoặc một smoke test khởi động ứng dụng sử dụng dependency thật.

Một số thư viện có thể dùng `spring-boot-autoconfigure-processor` để tạo `spring-autoconfigure-metadata.properties`, hỗ trợ lọc sớm điều kiện nhằm cải thiện startup. Không nhầm tệp được processor tạo ra với danh sách `AutoConfiguration.imports` phải được công bố.

## 9. Các lỗi thường gặp khi đăng ký metadata

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Có class `@AutoConfiguration` nhưng bean không có | Chưa tạo imports file hoặc runtime không chứa file | Kiểm tra `src/main/resources`, JAR và classpath. |
| Có imports file nhưng Boot không đọc | Sai tên tệp, sai vị trí `META-INF/spring`, file ở `src/test/resources` | Sửa đường dẫn và đóng gói lại. |
| Dòng metadata không tìm được class | Sai FQCN, đổi package nhưng quên sửa file | Đồng bộ package, class name và nội dung metadata. |
| Class được nạp nhưng bean mặc định không có | Điều kiện lớp/bean không khớp | Xem condition report, nhất là `@ConditionalOnMissingBean` và properties. |
| Ứng dụng vẫn chạy dù thiếu imports file | Class vô tình được component scan/`@Import` trực tiếp | Đặt auto-configuration ở package riêng, chỉ phát hiện qua imports. |
| Build thành công nhưng chạy JAR khác không nhận cấu hình | Module chứa metadata không nằm trên runtime classpath | Kiểm tra dependency graph và artifact được phát hành. |
| Dùng ví dụ cũ trong `spring.factories` cho Boot 3+ | Áp dụng cơ chế đăng ký auto-configuration legacy | Chuyển danh sách class sang tệp `AutoConfiguration.imports`. |
| Chuyển tên lớp cấu hình làm thứ tự/exclude bị sai | External code vẫn tham chiếu tên cũ | Cân nhắc `AutoConfiguration.replacements` khi đổi tên trong thư viện đã phát hành. |

### Đổi tên một auto-configuration đã phát hành

Nếu thư viện đã công khai lớp `OldAutoConfiguration` và các ứng dụng phụ thuộc lớp đó trong excludes/ordering, đổi package không chỉ là sửa imports file. Spring Boot hỗ trợ tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Trong đó có thể ánh xạ tên cũ sang tên mới:

~~~properties
com.example.old.OldAutoConfiguration=com.example.newpkg.NewAutoConfiguration
~~~

Khi chuyển đổi, imports file chỉ nên trỏ tới tên mới. Đây là cơ chế dành cho **tương thích khi thay thế tên lớp auto-configuration** trong phiên bản hỗ trợ; không dùng tệp replacements để đăng ký ứng viên mới. Ví dụ về tên class trong đoạn này minh họa format, không phải các lớp có sẵn trong Spring Boot.

## 10. Thực hành kiểm tra kiến thức

### Tình huống A: Một ứng dụng dùng hai thư viện

Thư viện A có `AConfig` trong imports file và thư viện B có `BConfig` trong imports file. Khi hai JAR đều trên classpath, Boot có thể thu thập ứng viên từ **cả hai tài nguyên**. Không cần tự nối hai tệp thành một tệp ở ứng dụng. Nhưng việc Bean A/Bean B có tồn tại còn tùy điều kiện và exclusions.

### Tình huống B: Chỉ thêm @AutoConfiguration mà chưa tạo imports file

Với ứng dụng ngoài package của class cấu hình, class không được tìm chỉ nhờ annotation; cần metadata imports trên runtime classpath hoặc một cơ chế import chủ đích khác. Với thư viện auto-configuration, đường đi chuẩn là **imports file**.

### Tình huống C: Nội dung imports file đúng nhưng Bean vẫn bị bỏ qua

Đọc `@ConditionalOnProperty`/`@ConditionalOnClass` ở cấp lớp và `@ConditionalOnMissingBean` ở phương thức. Nếu ứng dụng đã có bean cùng type, bean mặc định nên lùi bước. Đây có thể là hành vi đúng.

### Tình huống D: Đặt imports file cùng thư mục với java source

`src/main/java/META-INF/spring/...` không phải vị trí tài nguyên chuẩn của Maven. Hãy dùng `src/main/resources/META-INF/spring/...` để quá trình build sao chép đúng.

### Tình huống E: Muốn thêm một auto-configuration cho web

Thêm FQCN của cấu hình web vào imports file, và dùng điều kiện như classpath/web environment để cấu hình đó chỉ áp dụng khi phù hợp. Không tạo mặc định vô điều kiện chỉ vì thư viện có một entry mới.

### Tình huống F: Muốn kiểm thử việc Boot khám phá file

Test chỉ gọi thủ công `new MessageAutoConfiguration()` hoặc `AutoConfigurations.of(MessageAutoConfiguration.class)` chưa đủ để chứng minh metadata trong artifact. Hãy kiểm tra JAR và chạy một ứng dụng thử có bật auto-configuration, không quét package chứa cấu hình một cách thủ công.

## 11. Checklist trước khi phát hành thư viện

- [ ] Lớp auto-configuration là một `@AutoConfiguration` hợp lệ và chứa điều kiện phù hợp với ứng dụng sử dụng.
- [ ] Lớp được đặt trong package riêng, không nằm trong vùng bị component scan quét.
- [ ] Tệp nằm chính xác tại `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- [ ] Nội dung tệp có **một FQCN chính xác trên mỗi dòng**, không có `.class` hoặc cấu trúc properties sai kiểu.
- [ ] Tệp được đóng gói trong JAR và có mặt trên runtime classpath khi ứng dụng kéo dependency.
- [ ] Đã kiểm tra hai trường hợp: không có bean của người dùng và có bean của người dùng; bean mặc định chỉ xuất hiện khi điều kiện cho phép.
- [ ] Đã kiểm tra trường hợp thiếu optional dependency hoặc property không khớp không khiến thư viện lỗi không cần thiết.
- [ ] Không nhầm auto-configuration imports với `spring-configuration-metadata.json`, `spring-autoconfigure-metadata.properties` hoặc extension registrations khác.
- [ ] Có cách chẩn đoán bằng condition report, kiểm tra artifact và version compatibility.
- [ ] Nếu đổi tên lớp đã phát hành, xử lý tương thích ordering/excludes bằng cơ chế replacements khi phù hợp.

## 12. Tự kiểm tra

**1. Tệp AutoConfiguration.imports đăng ký bean hay lớp cấu hình?** — Đăng ký **tên lớp auto-configuration ứng viên**; bean được quyết định về sau.

**2. Đường dẫn đầy đủ trong dự án Maven là gì?** — `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**3. Nội dung mỗi dòng là gì?** — Fully qualified Java class name, ví dụ `com.example.autoconfigure.MessageAutoConfiguration`.

**4. Nếu class có `@AutoConfiguration` nhưng không có imports file thì sao?** — Annotation tự nó không khiến lớp được Boot phát hiện thông qua cơ chế auto-configuration chuẩn.

**5. Vì sao không đặt auto-configuration trong package component scan?** — Để lớp chỉ được Boot nhập qua metadata và điều phối đúng conditions/ordering.

**6. Nếu tệp được tìm thấy nhưng `@ConditionalOnMissingBean` không khớp thì sao?** — Bean mặc định tương ứng không được đăng ký; đây có thể là kết quả đúng vì ứng dụng đã cung cấp bean.

**7. Có thể có nhiều AutoConfiguration.imports trên classpath không?** — Có; các JAR khác nhau có thể đóng góp danh sách ứng viên riêng.

**8. `spring-autoconfigure-metadata.properties` có thay thế imports file không?** — Không; metadata đó phục vụ tối ưu hóa việc kiểm tra điều kiện.

**9. Vì sao phải xem JAR sau build?** — Vì tệp trong source tree chưa chứng minh file nằm trên runtime classpath của artifact thật.

**10. Khi đổi tên lớp đã phát hành, điều gì có thể bị ảnh hưởng?** — Exclusions/ordering dựa trên tên cũ; cần cân nhắc replacements metadata theo phiên bản Spring Boot.

## Tài liệu chính thức

- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — @AutoConfiguration API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot — Using @SpringBootApplication: https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html

**Ghi nhớ:** Để Boot phát hiện một auto-configuration từ thư viện, phải **đặt đúng tài nguyên imports trên classpath và ghi đúng FQCN của lớp cấu hình**. Imports file chỉ giúp Boot tìm **ứng viên**; điều kiện và quá trình xây dựng context mới quyết định bean nào thật sự có mặt.