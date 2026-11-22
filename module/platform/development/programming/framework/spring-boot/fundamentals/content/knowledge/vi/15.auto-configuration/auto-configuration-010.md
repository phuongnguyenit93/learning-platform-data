# Loại auto-configuration bằng annotation hoặc spring.autoconfigure.exclude

Spring Boot tự động cấu hình ứng dụng dựa trên dependency có trên classpath, các bean đã đăng ký, property trong Environment và loại ứng dụng đang chạy. Cơ chế này giúp một project có thể khởi động với ít cấu hình thủ công. Tuy nhiên, đôi khi một auto-configuration cụ thể không phù hợp: ứng dụng không dùng database, muốn tự quản lý một integration, hoặc cần loại một cấu hình mặc định gây xung đột.

`@ConditionalOnProperty` là annotation cho cấu hình theo property; còn bài học này tập trung vào **cách loại một auto-configuration class khỏi quá trình áp dụng**. Spring Boot cung cấp hai cách phổ biến:

- Khai báo loại trừ trên `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.
- Khai báo tên class trong property `spring.autoconfigure.exclude`.

Hai cách đều tác động đến danh sách auto-configuration mà Spring Boot xem xét. Chúng không xóa thư viện khỏi dependency graph và cũng không ngăn mọi cách khác đăng ký cùng bean. Muốn loại trừ đúng, trước hết cần hiểu auto-configuration class nào đang tạo bean và bean đó đến từ nguồn nào.

## 1. Auto-configuration được kích hoạt như thế nào?

Lớp main của ứng dụng Spring Boot thường có dạng:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp các chức năng chính:

- Đánh dấu lớp cấu hình gốc của ứng dụng.
- Bật component scanning theo package gốc và các package con.
- Bật cơ chế auto-configuration của Spring Boot.

Auto-configuration class được cung cấp bởi Spring Boot và các integration module. Boot khám phá các ứng viên theo metadata của chúng, rồi kiểm tra điều kiện như classpath, property, bean hiện có và loại application context.

Ví dụ, nếu ứng dụng có thư viện JDBC phù hợp và điều kiện cần thiết thỏa mãn, Boot có thể áp dụng auto-configuration liên quan đến `DataSource`. Nếu có web stack, Boot có thể cấu hình các thành phần phục vụ HTTP.

Quy trình khái quát:

```text
SpringApplication.run(...)
          │
          ▼
Tạo và chuẩn bị ApplicationContext
          │
          ▼
@EnableAutoConfiguration
          │
          ▼
Khám phá danh sách auto-configuration candidates
          │
          ▼
Áp dụng exclusions
          │
          ▼
Đánh giá conditions của candidates còn lại
          │
          ▼
Đăng ký các bean definitions phù hợp
          │
          ▼
Khởi tạo bean và hoàn tất context
```

Sơ đồ mô tả các bước ở mức khái niệm. Việc xử lý configuration classes và conditions có nhiều phase; không nên dùng sơ đồ này để suy ra thứ tự khởi tạo chính xác của mọi bean.

## 2. Khi nào cần loại auto-configuration?

Không nên loại auto-configuration chỉ vì bạn muốn hiểu rõ ứng dụng hơn. Spring Boot đã thiết kế nhiều auto-configuration để tự lùi lại khi người dùng cung cấp bean thay thế. Trước khi loại trừ, hãy xác định mục tiêu cụ thể.

Một số trường hợp hợp lý:

1. **Ứng dụng không dùng một công nghệ được auto-configure.** Ví dụ, project không cần cấu hình datasource mặc định.
2. **Ứng dụng tự quản lý integration đó.** Bạn muốn tạo bean hoặc cấu hình bằng thư viện khác, và auto-configuration mặc định không phù hợp.
3. **Một auto-configuration gây xung đột với kiến trúc hiện tại.** Điều kiện của nó vẫn thỏa nhưng ứng dụng không muốn các bean mặc định tương ứng.
4. **Một module dùng chung được tái sử dụng trong nhiều loại ứng dụng.** Một loại ứng dụng cần một auto-configuration, loại khác cần loại trừ nó.
5. **Cần giới hạn một cấu hình mặc định trong môi trường cụ thể.** Có thể chọn property exclusion ở profile hoặc cấu hình triển khai thích hợp.

Ví dụ: ứng dụng chỉ xử lý file và message, không kết nối database. Nếu dependency graph vô tình đưa JDBC vào, bạn có thể thấy datasource auto-configuration được xem xét. Loại trừ nó có thể làm rõ rằng ứng dụng không muốn Boot cấu hình datasource.

Tuy nhiên, nếu ứng dụng thực sự cần JPA hoặc JDBC, loại trừ datasource auto-configuration mà không cung cấp datasource thay thế có thể khiến context khởi động thất bại. Hãy hiểu các dependency downstream trước khi loại.

## 3. Cách thứ nhất: exclude trên @SpringBootApplication

Đây là cách trực tiếp, dễ đọc khi danh sách loại trừ là một phần cố định của cấu hình ứng dụng.

Ví dụ loại `DataSourceAutoConfiguration`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`exclude` nhận class literal của auto-configuration cần loại. Ưu điểm:

- IDE hỗ trợ import và điều hướng tới class.
- Compiler phát hiện class không tồn tại hoặc package sai.
- Refactor/rename có thể được IDE hỗ trợ.
- Ý định loại trừ được đặt ngay tại entry point của ứng dụng.

Có thể loại nhiều class cùng lúc:

```java
@SpringBootApplication(
    exclude = {
        DataSourceAutoConfiguration.class,
        SomeOtherAutoConfiguration.class
    }
)
public class DemoApplication {
    // main()
}
```

`SomeOtherAutoConfiguration` ở đây là tên minh họa. Hãy thay bằng một auto-configuration class thật sự có trong phiên bản Spring Boot và dependency của dự án.

**Lưu ý về ví dụ `DataSourceAutoConfiguration`:** import `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` thường gặp ở các dòng Spring Boot trước đây. Cấu trúc module và package có thể thay đổi giữa các major version. Hãy dùng class thực tế mà IDE/API reference của phiên bản đang dùng cung cấp; không sao chép package từ project khác mà chưa kiểm tra.

### 3.1. @SpringBootApplication đã bao gồm @EnableAutoConfiguration

Không cần thêm `@EnableAutoConfiguration` riêng chỉ để dùng `exclude`, vì `@SpringBootApplication` đã bao gồm chức năng này và expose thuộc tính loại trừ tương ứng.

Ví dụ sau thường là dư thừa:

```java
@SpringBootApplication
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
```

Hãy chọn một nơi cấu hình rõ ràng. Với ứng dụng Boot thông thường, `@SpringBootApplication(exclude = ...)` là cách dễ nhận biết nhất.

## 4. Cách thứ hai: exclude trên @EnableAutoConfiguration

Nếu ứng dụng không dùng `@SpringBootApplication` và bạn tự tổ chức cấu hình gốc, có thể bật auto-configuration trực tiếp:

```java
@Configuration
@ComponentScan("com.example.demo")
@EnableAutoConfiguration(
    exclude = DataSourceAutoConfiguration.class
)
public class ApplicationConfiguration {
}
```

Ví dụ này minh họa cách cấu hình Spring truyền thống: component scanning và auto-configuration được khai báo riêng.

Trong một ứng dụng Spring Boot mới, thường không cần tự viết lại cấu trúc như vậy. `@SpringBootApplication` đã gom các annotation phổ biến vào một điểm vào. Dùng `@EnableAutoConfiguration` riêng chủ yếu hữu ích khi bạn cần kiểm soát từng phần của cấu hình.

`exclude` của `@EnableAutoConfiguration` có cùng ý nghĩa: class được chỉ định bị loại khỏi danh sách auto-configuration được áp dụng.

## 5. Dùng excludeName khi muốn chỉ định class bằng tên

Ngoài `exclude`, Spring Boot cung cấp `excludeName`, nhận tên class đầy đủ dưới dạng String.

Ví dụ:

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
    // main()
}
```

Khác biệt:

| Thuộc tính | Kiểu | Cách chỉ định |
|---|---|---|
| `exclude` | `Class<?>[]` | `DataSourceAutoConfiguration.class` |
| `excludeName` | `String[]` | Tên đầy đủ của class |

`excludeName` hữu ích khi bạn không muốn tạo tham chiếu compile-time trực tiếp tới class cần loại, ví dụ class thuộc một integration tùy chọn mà module hiện tại không khai báo dependency compile trực tiếp.

Nhưng String không được compiler kiểm tra như class literal. Chính tả sai, package cũ hoặc class name không phù hợp chỉ có thể được phát hiện khi Spring Boot xử lý cấu hình. Vì vậy, hãy sao chép tên class từ API hoặc dependency thực tế và kiểm tra startup.

Có thể dùng `excludeName` trên `@EnableAutoConfiguration` tương tự:

```java
@EnableAutoConfiguration(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
@Configuration
public class ApplicationConfiguration {
}
```

Không dùng `excludeName` để chỉ định tên starter, artifact hoặc bean. Giá trị phải là **fully qualified class name của auto-configuration class**.

## 6. Cách thứ ba: property spring.autoconfigure.exclude

Nếu muốn danh sách loại trừ nằm trong file cấu hình thay vì annotation Java, dùng property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Spring Boot đọc danh sách class name này khi chuẩn bị auto-configuration. Ví dụ YAML tương đương:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Cả hai cách đều biểu diễn một danh sách auto-configuration class cần loại. Trong `application.properties`, nhiều class có thể được phân tách bằng dấu phẩy:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,com.example.integration.LegacyClientAutoConfiguration
```

Tên thứ hai chỉ là ví dụ giả định cho một class do thư viện cung cấp. Chỉ thêm class thực sự là auto-configuration candidate của ứng dụng.

### 6.1. Property có thể đặt theo profile

Nếu chỉ một môi trường cần loại cấu hình, có thể đặt property trong file profile-specific.

Ví dụ `application-local.yml`:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Khi profile `local` active, property exclusion này được nạp cùng các property source khác. Một profile khác không có khai báo này sẽ không nhận exclusion chỉ từ file `application-local.yml`.

Có thể kích hoạt profile qua cấu hình:

```properties
spring.profiles.active=local
```

hoặc tham số chạy:

```bash
java -jar app.jar --spring.profiles.active=local
```

Đây là cách hữu ích khi local/test không cần integration database, còn môi trường khác vẫn dùng auto-configuration đó. Nhưng hãy đảm bảo các bean phụ thuộc vào datasource cũng được cấu hình phù hợp trong từng profile.

### 6.2. Truyền exclusion qua command line

Property có thể được truyền khi khởi chạy ứng dụng:

```bash
java -jar app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Điều này cho phép thay đổi danh sách exclusion trong lần khởi chạy mà không sửa annotation Java hoặc đóng gói lại ứng dụng. Nó vẫn là quyết định lúc khởi động; thay đổi command line không làm context đang chạy tự cập nhật.

Với nhiều class, truyền danh sách theo cú pháp property list mà Spring Boot hỗ trợ, ví dụ phân tách bằng dấu phẩy. Khi dùng shell hoặc nền tảng triển khai, hãy bảo đảm dấu phẩy và dấu chấm không bị công cụ wrapper xử lý sai.

## 7. So sánh các cách loại trừ

| Cách | Ví dụ | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| `@SpringBootApplication(exclude = ...)` | Class literal trên lớp main | Type-safe, dễ tìm trong code | Danh sách gắn với mã nguồn và compile dependency. |
| `@EnableAutoConfiguration(exclude = ...)` | Class literal trên cấu hình gốc | Phù hợp khi cấu hình auto-configuration được khai báo riêng | Ít cần trong app Boot thông thường. |
| `excludeName` | Fully qualified class name dạng String | Không cần tham chiếu compile-time tới class | Không được compiler xác nhận tên class. |
| `spring.autoconfigure.exclude` | Property trong properties/YAML | Cấu hình ngoài code, có thể theo profile/command line | Cần kiểm tra giá trị hiệu lực trong Environment. |

Không có một lựa chọn luôn tốt nhất. Nếu exclusion là quy tắc cố định của kiến trúc ứng dụng, annotation thường dễ đọc. Nếu cần thay đổi theo profile hoặc môi trường triển khai, property thường phù hợp hơn. Nếu class tùy chọn không có trên compile classpath, `excludeName` hoặc property có thể tránh import trực tiếp.

## 8. Loại trừ auto-configuration không giống loại bỏ dependency

Giả sử build file khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

Starter và các thư viện transitive vẫn được Gradle/Maven resolve vào classpath. Nếu bạn loại `DataSourceAutoConfiguration`, Spring Boot sẽ không áp dụng auto-configuration class đó.

Điều này **không có nghĩa**:

- Dependency JDBC bị gỡ khỏi classpath.
- Các class JDBC không thể được ứng dụng sử dụng.
- Mọi auto-configuration liên quan database đều tự động bị loại.
- Bean `DataSource` do người dùng tự khai báo bị xóa.
- Một cấu hình database được `@Import` trực tiếp sẽ tự biến mất.

Loại trừ là thao tác trên **danh sách auto-configuration của Spring Boot**, không phải thao tác dependency management hoặc component scan.

Nếu muốn gỡ một thư viện không cần thiết, hãy sửa dependency trong Gradle/Maven. Nếu muốn giữ thư viện nhưng không muốn Boot tự cấu hình một phần, exclusion mới là cơ chế đúng.

## 9. Loại trừ auto-configuration không chặn component scan hoặc @Import

Giả sử bạn loại `DataSourceAutoConfiguration`:

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

Nhưng ứng dụng vẫn có cấu hình riêng:

```java
@Configuration(proxyBeanMethods = false)
public class ManualDatabaseConfiguration {

    @Bean
    public DataSource applicationDataSource() {
        return createDataSource();
    }

    private DataSource createDataSource() {
        // Chi tiết cấu hình được lược giản.
        throw new UnsupportedOperationException("Example only");
    }
}
```

Nếu `ManualDatabaseConfiguration` được component scan hoặc import, Spring vẫn xử lý nó. Exclusion không áp dụng cho bean method do ứng dụng tự viết.

Tương tự, một thư viện có thể được import trực tiếp bằng `@Import(SomeConfiguration.class)`. Nếu cấu hình ấy tự đăng ký bean, việc loại một auto-configuration class khác không chặn đường import đó.

Điều này rất quan trọng khi bạn thấy bean vẫn tồn tại sau exclusion. Hãy tìm **nguồn đăng ký bean**: auto-configuration, component scan, `@Bean`, `@Import`, hoặc đăng ký lập trình.

## 10. Loại một auto-configuration có thể ảnh hưởng đến nhiều bean

Một auto-configuration class có thể khai báo nhiều bean và cấu hình liên quan. Loại class đó có thể làm mất nhiều bean mặc định cùng lúc.

Ví dụ datasource auto-configuration có thể ảnh hưởng tới bean datasource mặc định và các thành phần phụ thuộc vào datasource. Nếu ứng dụng vẫn có auto-configuration khác cần `DataSource`, chúng có thể không match condition hoặc có thể báo thiếu dependency tùy cấu hình.

Vì vậy, trước khi loại một class:

1. Xác định bean nào được class đó cung cấp.
2. Xác định các auto-configuration khác phụ thuộc vào bean đó.
3. Xác định ứng dụng có tự cung cấp bean thay thế không.
4. Chạy ứng dụng và kiểm tra condition report sau thay đổi.
5. Kiểm tra các luồng nghiệp vụ phụ thuộc vào integration đó.

Không nên chỉ dựa vào tên class để kết luận exclusion là vô hại. Hãy đọc API/reference của phiên bản Boot và quan sát kết quả trong chính application context.

## 11. Khi nào nên override bean thay vì loại cả auto-configuration?

Nhiều auto-configuration của Spring Boot được thiết kế để **back off** khi người dùng cung cấp bean phù hợp, thường thông qua `@ConditionalOnMissingBean`.

Nếu bạn chỉ muốn thay một bean mặc định, có thể khai báo bean riêng. Ví dụ minh họa:

```java
@Configuration(proxyBeanMethods = false)
public class CustomClockConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Ví dụ này minh họa cách cung cấp bean do ứng dụng quản lý, không khẳng định mọi auto-configuration đều tạo bean `Clock`.

Quyết định:

- Nếu bạn chỉ muốn thay **một bean mặc định**, hãy xem auto-configuration có back off khi bean cùng type/name được cung cấp không.
- Nếu bạn muốn tắt **toàn bộ cấu hình mặc định** của một integration, exclusion có thể phù hợp.
- Nếu chỉ muốn tắt **một chức năng nhỏ** trong integration, tìm property chuyên biệt mà auto-configuration hỗ trợ trước khi loại cả class.

Nếu auto-configuration có property riêng để tắt một tính năng, dùng property đó thường giữ lại các bean hữu ích khác. Exclusion class rộng có thể làm mất nhiều cấu hình hơn nhu cầu.

## 12. Phân biệt tên auto-configuration class với tên starter

Một lỗi thường gặp là điền tên starter vào `spring.autoconfigure.exclude`.

Không đúng:

```properties
spring.autoconfigure.exclude=spring-boot-starter-jdbc
```

Đây là tên artifact/starter, không phải tên auto-configuration class.

Đúng về định dạng:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Giá trị cần là fully qualified class name. Tên class cụ thể phải tồn tại trong phiên bản dependency của project và phải là auto-configuration candidate.

Một starter có thể đưa nhiều auto-configuration class vào classpath. Nếu bạn chỉ muốn loại một phần, hãy xác định chính xác class cần loại thay vì đoán từ tên starter.

## 13. Xác định auto-configuration class cần loại

Đừng đoán class name từ tên dependency. Có một số cách xác định:

### 13.1. Dùng IDE

- Tìm class có tên `...AutoConfiguration`.
- Kiểm tra package và module chứa class.
- Đọc annotation `@AutoConfiguration` hoặc cấu trúc auto-configuration tương ứng của phiên bản.
- Xem các điều kiện và `@Bean` method mà class cung cấp.
- Kiểm tra class đó có thuộc dependency thực tế của project không.

Với `exclude = SomeAutoConfiguration.class`, IDE giúp import đúng class và compiler xác nhận kiểu.

### 13.2. Xem metadata trong dependency JAR

Các dòng Spring Boot hiện đại cung cấp danh sách auto-configuration qua metadata trong JAR, thường tại:

```text
META-INF/spring/
└── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Các dòng cũ hơn có cơ chế metadata khác, chẳng hạn `spring.factories` cho auto-configuration ở các phiên bản trước giai đoạn chuyển đổi. Hãy dùng tài liệu đúng với phiên bản Boot.

Tệp metadata cho biết class nào được công bố như auto-configuration candidate. Nó không tự chứng minh class đó đã match condition trong ứng dụng.

### 13.3. Dùng condition evaluation report

Chạy ứng dụng với `--debug` để xem auto-configuration nào được áp dụng hoặc không được áp dụng. Report giúp xác định class cần xem xét và lý do một điều kiện match/fail.

Đây thường là cách hiệu quả khi bạn biết integration nào gây ra bean nhưng chưa biết auto-configuration class chịu trách nhiệm.

## 14. Debug sau khi loại trừ

Sau khi thêm exclusion, đừng chỉ kiểm tra ứng dụng có khởi động hay không. Hãy xác nhận đúng auto-configuration đã bị loại và các phần khác vẫn hoạt động.

### Bật report bằng command line

```bash
java -jar app.jar --debug
```

Hoặc cấu hình:

```properties
debug=true
```

Spring Boot có thể in **conditions evaluation report**. Tìm phần auto-configuration bị loại hoặc không được áp dụng và lý do tương ứng.

Nếu dùng Actuator và đã cấu hình exposure phù hợp, endpoint `/actuator/conditions` có thể cung cấp thông tin điều kiện. Endpoint `/actuator/beans` có thể giúp kiểm tra bean nào đang tồn tại. Chỉ expose endpoint quản trị trong phạm vi được bảo vệ.

### Kiểm tra bean thực tế

Có thể truy vấn context:

```java
@Component
public class StartupInspector implements ApplicationRunner {

    private final ApplicationContext context;

    public StartupInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] dataSources =
                context.getBeanNamesForType(DataSource.class);

        System.out.println(
                "DataSource bean count: " + dataSources.length
        );
    }
}
```

Ví dụ này cần import `javax.sql.DataSource` từ JDK và giả định ứng dụng có kiểu datasource trên compile classpath. Nó chỉ quan sát bean theo type; nếu có datasource do ứng dụng tự khai báo, count vẫn có thể lớn hơn zero dù auto-configuration đã bị loại.

**Không dùng số lượng bean làm bằng chứng duy nhất cho exclusion.** Hãy kết hợp report, nguồn bean definition và cấu hình thực tế.

## 15. Kiểm thử exclusion bằng @SpringBootTest

Có thể truyền property exclusion cho test context:

```java
@SpringBootTest(properties = {
    "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
})
class AutoConfigurationExclusionTests {

    @Autowired
    ApplicationContext context;

    @Test
    void datasourceAutoConfigurationDoesNotProvideDataSource() {
        assertThat(context.getBeansOfType(DataSource.class))
                .isEmpty();
    }
}
```

Ví dụ giả định:

- Test dùng Spring Boot application context thật.
- Không có cấu hình khác tự khai báo `DataSource`.
- Tên class exclusion đúng với phiên bản Spring Boot đang dùng.
- Project có test dependencies cần thiết.

Nếu ứng dụng có `DataSource` thủ công, assertion trên không đúng dù auto-configuration đã bị loại. Khi đó, test cần kiểm tra bean hoặc condition cụ thể do auto-configuration cung cấp, thay vì khẳng định không có bất kỳ datasource nào.

Mục tiêu là kiểm tra **auto-configuration class không được áp dụng**, không phải cấm toàn bộ ứng dụng có bean cùng loại.

## 16. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng báo không thể exclude class | Tên chỉ định không phải auto-configuration candidate hoặc sai class name. | Kiểm tra metadata, package và version dependency. |
| `exclude = SomeClass.class` không biên dịch | Class không có trên compile classpath hoặc package đã đổi. | Kiểm tra dependency/version; cân nhắc `excludeName` nếu class là integration tùy chọn. |
| Dùng `spring.autoconfigure.exclude` nhưng bean vẫn tồn tại | Bean được đăng ký từ component scan, `@Bean`, `@Import` hoặc một auto-configuration khác. | Truy tìm nguồn bean definition. |
| Ứng dụng khởi động lỗi sau khi exclude | Bean khác phụ thuộc vào bean vừa bị loại. | Cung cấp bean thay thế, điều kiện hóa consumer hoặc giữ auto-configuration cần thiết. |
| Dùng tên starter trong property | Nhầm artifact name với auto-configuration class name. | Dùng fully qualified class name. |
| Exclusion chỉ có tác dụng ở local | Property đặt trong profile file chỉ active ở local. | Kiểm tra active profiles và property sources ở môi trường khác. |
| Thay đổi property nhưng context đang chạy không đổi | Exclusion được xử lý khi startup. | Khởi động lại context/app; dùng dynamic configuration khác nếu cần runtime toggle. |
| Exclude class của phiên bản khác | Package/class name đã thay đổi giữa major versions. | Dùng class/API reference của đúng Spring Boot version. |
| Tưởng dependency đã bị xóa | Exclusion chỉ bỏ auto-configuration, không sửa dependency graph. | Gỡ dependency riêng nếu mục tiêu là loại thư viện. |

## 17. Quy trình chọn và áp dụng exclusion

Khi cần loại một auto-configuration, có thể làm theo trình tự:

1. **Xác định bean hoặc behavior không mong muốn.** Thu thập log, condition report và bean type/name.
2. **Tìm auto-configuration class chịu trách nhiệm.** Kiểm tra metadata và source/API reference của đúng phiên bản.
3. **Kiểm tra có property hẹp hơn không.** Nếu chỉ cần tắt một feature, dùng property chuyên biệt khi có.
4. **Kiểm tra khả năng back-off.** Nếu chỉ muốn thay một bean, thử cung cấp bean phù hợp thay vì loại cả configuration.
5. **Chọn cách exclusion.** Dùng annotation cho quy tắc cố định; dùng property khi cần cấu hình theo profile hoặc môi trường.
6. **Xác minh dependency downstream.** Đảm bảo các bean cần thiết vẫn có nguồn cung cấp.
7. **Khởi động lại và xem condition report.** Xác nhận class bị loại đúng như dự định.
8. **Chạy test cho behavior liên quan.** Kiểm tra cả bean thay thế và các chức năng ứng dụng phụ thuộc.

Đừng thêm nhiều exclusion cùng lúc khi chưa biết class nào gây ra vấn đề. Mỗi exclusion rộng có thể làm thay đổi nhiều bean definitions.

## 18. Bài tập thực hành

### Bài tập A — Loại datasource bằng annotation

1. Tạo một Spring Boot project có dependency JDBC phù hợp.
2. Thêm `DataSourceAutoConfiguration.class` vào `@SpringBootApplication(exclude = ...)`, dùng đúng package của phiên bản project.
3. Chạy ứng dụng với `--debug`.
4. Quan sát condition report và kiểm tra datasource bean.
5. Thử inject `DataSource` vào một component; ghi nhận behavior nếu không có bean thay thế.

### Bài tập B — Loại datasource bằng property

1. Bỏ exclusion khỏi annotation.
2. Thêm fully qualified class name vào `spring.autoconfigure.exclude` trong `application.properties`.
3. Chạy lại và so sánh condition report.
4. Chuyển property sang `application-local.yml`, kích hoạt profile `local`, rồi thử với profile khác.

Mục tiêu là thấy hai cơ chế tạo ra cùng mục tiêu exclusion nhưng được khai báo ở hai nơi khác nhau.

### Bài tập C — Thử excludeName

Dùng `excludeName` với tên đầy đủ của auto-configuration class. So sánh với class literal `exclude`. Ghi lại sự khác biệt về compile-time checking và khả năng refactor.

### Bài tập D — Tự cung cấp bean thay thế

1. Bỏ exclusion.
2. Tạo bean thay thế cho một integration có `@ConditionalOnMissingBean`.
3. Xác nhận auto-configuration back off nếu điều kiện hỗ trợ.
4. So sánh với việc loại cả auto-configuration class.

Giải thích vì sao override một bean thường có phạm vi nhỏ hơn exclusion toàn class.

### Bài tập E — Phân biệt bean source

Sau khi loại một auto-configuration, tạo một bean cùng type bằng `@Bean` trong cấu hình ứng dụng. Kiểm tra nó vẫn xuất hiện. Giải thích vì sao exclusion không chặn component scan hoặc user configuration.

## 19. Nguyên tắc cần nhớ

1. **Exclusion loại auto-configuration class khỏi danh sách Boot áp dụng**, không xóa dependency khỏi classpath.
2. `@SpringBootApplication(exclude = ...)` là lựa chọn trực tiếp cho quy tắc cố định trong code.
3. `@EnableAutoConfiguration(exclude = ...)` phù hợp khi bạn khai báo auto-configuration riêng.
4. `excludeName` dùng fully qualified class name dạng String; cần kiểm tra tên vì compiler không xác nhận.
5. `spring.autoconfigure.exclude` đặt danh sách loại trừ trong `application.properties`, YAML, profile hoặc command line.
6. Exclusion không chặn component scan, `@Bean`, `@Import` hay một nguồn đăng ký bean độc lập khác.
7. Loại một auto-configuration có thể ảnh hưởng nhiều bean và các cấu hình phụ thuộc.
8. Nếu chỉ muốn thay một bean, kiểm tra `@ConditionalOnMissingBean` và khả năng override trước khi loại toàn class.
9. Class name/package có thể thay đổi giữa các dòng Spring Boot; dùng API reference và metadata của đúng phiên bản.
10. Xác minh bằng condition report và test behavior sau khi thay đổi.

Khi loại auto-configuration, hãy trả lời được ba câu hỏi: **class nào đang được áp dụng, vì sao muốn loại nó, và bean nào sẽ cung cấp chức năng còn cần thiết sau khi loại?** Chọn annotation khi quyết định thuộc cấu hình cố định của ứng dụng; chọn `spring.autoconfigure.exclude` khi quyết định cần nằm ở property theo môi trường.
