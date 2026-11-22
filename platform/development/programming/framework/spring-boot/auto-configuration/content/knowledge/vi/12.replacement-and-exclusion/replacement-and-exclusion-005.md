# spring.autoconfigure.exclude qua tệp cấu hình và tham số khởi động

## 1. Bài toán: loại trừ một auto-configuration mà không sửa mã nguồn

**Spring Boot Auto-configuration** tự đăng ký các cấu hình và bean dựa trên thư viện trong classpath, các bean đã có và các điều kiện môi trường. Phần lớn thời gian đây là hành vi mong muốn, nhưng một triển khai cụ thể có thể cần **loại trừ** một lớp auto-configuration.

Ví dụ:
- Dự án chỉ xử lý tệp nhưng vô tình kéo thêm thư viện JDBC; bạn không muốn Spring Boot tự cấu hình datasource.
- Một dịch vụ dùng cấu hình JSON tự kiểm soát và muốn tắt phần cấu hình Jackson mặc định của Spring Boot.
- Khi chẩn đoán lỗi khởi động, bạn muốn thử loại trừ có kiểm soát một auto-configuration mà không xây lại mã Java cho từng môi trường.

Thuộc tính chuẩn dành cho mục đích này là:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Giá trị là **tên lớp đầy đủ (fully qualified class name, FQCN)** của auto-configuration cần bỏ qua. Ví dụ trên dành cho **Spring Boot 3.x**, nơi \`DataSourceAutoConfiguration\` nằm trong gói \`org.springframework.boot.autoconfigure.jdbc\`. **Spring Boot 4.x đã sắp xếp lại một số gói auto-configuration**, nên luôn đối chiếu tên lớp với phiên bản dự án.

Có thể khai báo \`spring.autoconfigure.exclude\` trong \`application.properties\`, \`application.yml\`/\`application.yaml\`, tệp cấu hình theo profile, **hoặc truyền bằng tham số khởi động** như \`--spring.autoconfigure.exclude=...\`. Cùng một cơ chế loại trừ được sử dụng dù giá trị đến từ nguồn cấu hình nào.

**Kết quả mong đợi:** auto-configuration có tên trong danh sách loại trừ sẽ không được áp dụng thông qua cơ chế auto-configuration của Spring Boot. Điều này **không đồng nghĩa** với xóa mọi bean thuộc một kiểu, gỡ dependency khỏi classpath hay vô hiệu hóa tất cả auto-configuration khác.

## 2. Cơ chế: loại trừ ở bước chọn lớp auto-configuration

Khi khởi động, Spring Boot xác định các lớp auto-configuration ứng viên, xem xét điều kiện và danh sách loại trừ, rồi nhập những lớp được chọn vào ApplicationContext. \`@EnableAutoConfiguration\` (được \`@SpringBootApplication\` bao hàm) hỗ trợ một khóa đặc biệt:

~~~java
org.springframework.boot.autoconfigure.EnableAutoConfiguration
        .EXCLUDE_PROPERTY
~~~

Hằng số trên có giá trị **\`spring.autoconfigure.exclude\`**.

Mô hình tư duy:

~~~text
Các lớp auto-configuration ứng viên
                  |
                  v
Đọc exclude từ annotation và thuộc tính Environment
                  |
                  v
Loại những auto-configuration được nêu tên
                  |
                  v
Đánh giá những điều kiện của các cấu hình còn lại
                  |
                  v
Đăng ký các bean phù hợp vào ApplicationContext
~~~

Đây là mô hình giải thích, không phải trích nguyên văn mã nội bộ của Spring Boot.

Cần tách bạch:

| Đối tượng | \`spring.autoconfigure.exclude\` có tác động không? |
| --- | --- |
| Một lớp auto-configuration được Spring Boot nhập tự động | **Có**, nếu nêu đúng tên lớp |
| Một \`@Component\` được component scan tìm thấy | **Không trực tiếp** |
| Một bean tạo thủ công bằng \`@Bean\` trong cấu hình ứng dụng | **Không trực tiếp** |
| Một bean người dùng tự định nghĩa cùng kiểu với bean auto-config | **Không tự xóa** bean người dùng |
| Một dependency trong \`pom.xml\`/\`build.gradle\` | **Không** loại dependency khỏi classpath |
| Tất cả những auto-configuration khác | **Không** bị tắt hàng loạt |

Vì vậy, chỉ dùng thuộc tính này khi đối tượng cần loại trừ **thực sự là auto-configuration**. Nếu vẫn thấy một bean tồn tại, hãy kiểm tra xem nó được tạo bởi cấu hình khác hoặc do người dùng định nghĩa hay không.

## 3. Khai báo trong application.properties

Với **Spring Boot 3.5.x**, có thể đặt trong \`src/main/resources/application.properties\`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Khi ứng dụng khởi động với tệp này, Spring Boot sẽ không tự nhập \`DataSourceAutoConfiguration\` qua auto-configuration.

### Loại trừ nhiều lớp cùng lúc

Dùng **danh sách tên lớp, cách nhau bằng dấu phẩy**:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Đây là hai tên lớp tách biệt, không phải một tên lớp dài.

Các điểm cần chú ý:
1. **Dùng FQCN**, ví dụ \`org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration\`, không chỉ \`DataSourceAutoConfiguration\`.
2. **Chỉ sử dụng các lớp auto-configuration của phiên bản đang chạy.** Tên gói có thể khác giữa các dòng Spring Boot.
3. Nếu chỉ muốn vô hiệu hóa một tính năng theo nghiệp vụ, đôi khi đã có một thuộc tính chuyên biệt như \`spring.*.enabled\` hoặc điều kiện bean thích hợp; loại trừ toàn bộ auto-configuration là lựa chọn phạm vi rộng hơn.
4. Thường nên khai báo property **một lần** chứa đầy đủ danh sách, thay vì viết trùng cùng một khóa ở nhiều dòng và giả định chúng sẽ tự cộng dồn.

**Không viết theo tên bean:**

~~~properties
# Sai: đối tượng được liệt kê phải là lớp auto-configuration.
spring.autoconfigure.exclude=dataSource
~~~

\`dataSource\` trong ví dụ chỉ là tên bean, không phải FQCN của một lớp auto-configuration.

## 4. Khai báo trong application.yml hoặc application.yaml

Cùng ví dụ một lớp, dùng cấu trúc YAML:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Ví dụ hai lớp:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
      - org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

YAML hỗ trợ danh sách nên cách này dễ đọc và ít sai dấu phẩy khi có nhiều lớp. Cả \`application.yml\` và \`application.yaml\` đều là các đuôi tệp YAML được Spring Boot hỗ trợ.

Có thể viết dạng scalar phân tách dấu phẩy, nhưng dạng **danh sách YAML** thường rõ ràng hơn:

~~~yaml
spring:
  autoconfigure:
    exclude: org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

**Chú ý thụt lề:** \`autoconfigure\` là cấp con của \`spring\`, còn \`exclude\` là cấp con của \`autoconfigure\`. Đây là property \`spring.autoconfigure.exclude\`, **không phải** \`spring.auto-configuration.exclude\` hay \`spring.autocofiguration.exclude\`.

Nếu cùng vị trí chứa cả \`application.properties\` và \`application.yaml\`, Spring Boot có quy tắc ưu tiên nguồn cấu hình; tài liệu khuyến nghị nhất quán một định dạng để tránh khó đoán giá trị hiệu lực. Với hai định dạng ở cùng vị trí, tệp \`.properties\` được ưu tiên.

## 5. Truyền tham số trực tiếp khi khởi động ứng dụng

Với JAR thực thi do Spring Boot đóng gói:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Cú pháp quan trọng:
- \`java -jar target/my-app.jar\` khởi động ứng dụng, thay tên JAR bằng artifact thực tế.
- \`--spring.autoconfigure.exclude=...\` là **application argument** do \`SpringApplication\` nhận và thêm vào \`Environment\`.
- Dấu \`--\` mở đầu tên thuộc tính; dùng \`=\` để chỉ định giá trị.
- **Không** đặt đối số \`--spring.autoconfigure.exclude\` trước \`-jar\` rồi mong Java launcher hiểu nó như JVM option.

### Loại trừ nhiều lớp qua command line

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Trong một số shell hoặc môi trường CI, đặt toàn bộ đối số trong dấu nháy để tránh những thao tác diễn giải của shell:

~~~bash
java -jar target/my-app.jar "--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration"
~~~

### Khởi động bằng Maven Spring Boot Plugin

Nếu dự án dùng Maven với \`spring-boot-maven-plugin\`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
~~~

Trên Windows PowerShell có Maven Wrapper trong dự án:

~~~powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration'
~~~

Trên hệ điều hành khác có Maven Wrapper, thay \`mvn\` bằng \`./mvnw\`. Cấu trúc \`spring-boot.run.arguments\` là **thuộc tính điều khiển plugin Maven**, còn chuỗi bắt đầu bằng \`--spring.autoconfigure.exclude\` mới là đối số được chuyển đến ứng dụng.

### Phân biệt application argument với JVM system property

Cũng có thể đặt property bằng \`-D\` trước \`-jar\`:

~~~bash
java -Dspring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration -jar target/my-app.jar
~~~

Dạng trên tạo **JVM system property**; dạng sau \`java -jar ... --spring.autoconfigure.exclude=...\` tạo **Spring Boot command-line property**. Cả hai có thể đi vào \`Environment\`, nhưng nằm ở các nguồn cấu hình có thứ tự ưu tiên khác nhau. Theo mặc định, đối số ứng dụng \`--...\` có độ ưu tiên cao hơn JVM system property và tệp application.

## 6. Quy tắc ưu tiên khi có cả file và command line

Spring Boot tổng hợp cấu hình từ nhiều nguồn: \`application.properties\`/\`application.yaml\`, tệp theo profile, biến môi trường, JVM system properties và đối số command line.

**Mặc định, tham số \`--spring.autoconfigure.exclude=...\` ưu tiên hơn giá trị khai báo trong application.properties/application.yaml.** Đây là cách dùng cùng một JAR nhưng thay hành vi theo môi trường triển khai.

Ví dụ trong \`application.properties\`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Khi khởi động **không truyền** \`spring.autoconfigure.exclude\` trên command line, giá trị hiệu lực là danh sách có \`JacksonAutoConfiguration\`.

Nếu chạy:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

thì command line đưa ra giá trị property ưu tiên cao hơn. **Không nên giả định rằng Spring Boot sẽ tự nối hai danh sách thành \`JacksonAutoConfiguration,DataSourceAutoConfiguration\`**. Khi một thuộc tính danh sách được định nghĩa lại ở nguồn ưu tiên cao hơn, binding danh sách dùng giá trị từ nguồn thắng, không mặc nhiên hợp nhất tất cả mục ở nguồn thấp hơn.

Muốn giữ cả hai loại trừ, hãy khai báo **đầy đủ hai tên ở nguồn ưu tiên cao nhất**:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration,org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**Ngoại lệ cần phân biệt:** loại trừ khai báo bằng \`@SpringBootApplication(exclude=...)\` hoặc \`@EnableAutoConfiguration(exclude=...)\` thuộc metadata annotation; loại trừ qua property được kết hợp với các loại trừ annotation trong quá trình chọn auto-configuration. Vì vậy, command line ghi đè **giá trị property** không có nghĩa xóa loại trừ đã hard-code bằng annotation.

Spring Boot cho phép tắt tự động chuyển ứng dụng arguments vào \`Environment\` bằng \`SpringApplication.setAddCommandLineProperties(false)\`. Trong cấu hình tùy biến như vậy, không thể mặc định cho rằng \`--spring.autoconfigure.exclude\` sẽ được xử lý như bình thường.

## 7. Tệp theo profile và cấu hình triển khai

Có thể giới hạn loại trừ vào từng profile. Ví dụ chỉ không muốn khởi tạo JDBC auto-configuration khi chạy profile \`local\`.

Trong \`src/main/resources/application-local.properties\`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Kích hoạt profile:

~~~bash
java -jar target/my-app.jar --spring.profiles.active=local
~~~

Khi \`local\` hoạt động, Spring Boot sẽ xét cấu hình của \`application-local.properties\` cùng các nguồn cấu hình khác; thuộc tính này có thể ghi đè danh sách cùng khóa ở \`application.properties\`.

Ví dụ YAML theo profile trong \`application-local.yaml\`:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Có thể dùng \`application-prod.properties\` hoặc các nguồn ngoài JAR cho môi trường khác. Nếu cần triển khai nhiều môi trường dùng cùng artifact, **command line, cấu hình gắn ngoài và profile** giúp thay đổi danh sách mà không thay source Java.

**Bẫy danh sách:** nếu \`application.properties\` loại trừ A và \`application-local.properties\` loại trừ B, profile thường chọn giá trị danh sách B thay vì tự cộng A + B. Nếu muốn cả hai trong profile local, hãy khai báo A và B ở danh sách dành cho local.

## 8. Ví dụ chạy thực tế với Java 17 và Spring Boot 3.5

Để quan sát trực tiếp sự khác nhau, dùng **JacksonAutoConfiguration**. Spring Boot 3.5 tạo \`com.fasterxml.jackson.databind.ObjectMapper\` mặc định khi Jackson có mặt và không có bean ObjectMapper do ứng dụng tự cung cấp. Vì thế việc loại trừ lớp auto-configuration có thể được kiểm chứng qua sự có mặt/vắng mặt của bean này.

### 8.1 Tạo dự án Maven nhỏ

Tạo \`pom.xml\`:

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
    <artifactId>exclusion-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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

Ví dụ cố định **Spring Boot 3.5.7** để tên gói và kiểu Jackson được xác định. Trong dự án thật, dùng phiên bản Boot được quản lý và đã kiểm thử, tránh sao chép version cố định vào một dự án có parent khác.

Tạo tệp \`src/main/java/example/ExclusionDemoApplication.java\`:

~~~java
package example;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class ExclusionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExclusionDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner printJacksonState(ApplicationContext context) {
        return args -> {
            boolean exists =
                    context.getBeanNamesForType(ObjectMapper.class).length > 0;
            System.out.println("OBJECT_MAPPER_PRESENT=" + exists);
        };
    }
}
~~~

**Mã có thể biên dịch và chạy** khi sử dụng đúng cấu trúc Maven nói trên. \`CommandLineRunner\` chạy sau khi context đã khởi tạo và in xem có Spring bean loại \`ObjectMapper\` hay không.

### 8.2 Chạy không loại trừ

Để \`src/main/resources/application.properties\` trống hoặc chưa khai báo \`spring.autoconfigure.exclude\`, chạy:

~~~bash
mvn spring-boot:run
~~~

Dòng chẩn đoán kỳ vọng trong console:

~~~text
OBJECT_MAPPER_PRESENT=true
~~~

Vì starter JSON đưa Jackson lên classpath và Jackson auto-configuration tạo \`ObjectMapper\` mặc định cho ứng dụng mẫu.

### 8.3 Loại trừ bằng application.properties

Thêm vào \`src/main/resources/application.properties\`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Chạy lại:

~~~bash
mvn spring-boot:run
~~~

Dòng chẩn đoán kỳ vọng:

~~~text
OBJECT_MAPPER_PRESENT=false
~~~

Điều kiện quan sát này đúng với **dự án mẫu không có ObjectMapper tự định nghĩa và không có cấu hình khác tạo ObjectMapper**. Nếu có \`@Bean ObjectMapper\` riêng thì điều kiện vẫn có thể loại trừ Jackson auto-configuration, nhưng dòng in sẽ là \`true\` vì có bean tự định nghĩa.

### 8.4 Loại trừ bằng tham số khởi động

Xóa dòng exclude trong file hoặc tạm để file trống, đóng gói:

~~~bash
mvn -DskipTests package
~~~

Khởi động JAR và truyền exclude:

~~~bash
java -jar target/exclusion-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Dòng chẩn đoán kỳ vọng:

~~~text
OBJECT_MAPPER_PRESENT=false
~~~

Khởi động lại **không truyền exclude**, khi file vẫn trống:

~~~bash
java -jar target/exclusion-demo-0.0.1-SNAPSHOT.jar
~~~

Dòng chẩn đoán kỳ vọng:

~~~text
OBJECT_MAPPER_PRESENT=true
~~~

Console còn có log của Spring Boot/Maven; chỉ hai dòng \`OBJECT_MAPPER_PRESENT=...\` ở trên được dùng như tín hiệu kiểm chứng trực tiếp.

### 8.5 Cùng ứng dụng, nhiều cách cấp giá trị

| Nguồn cung cấp exclude | Giá trị được đặt ở đâu? | Thay đổi hành vi khi nào? |
| --- | --- | --- |
| \`application.properties\` | Tệp cấu hình | Khi chạy lại ứng dụng với cấu hình hiệu lực mới |
| \`application.yml\` | Tệp YAML | Khi chạy lại với nội dung mới |
| \`application-local.properties\` | Tệp riêng profile | Khi profile \`local\` được kích hoạt lúc chạy |
| \`java -jar ... --spring.autoconfigure.exclude=...\` | Đối số ứng dụng | Khi khởi động tiến trình với đối số mới |
| \`java -Dspring.autoconfigure.exclude=... -jar ...\` | JVM system property | Khi khởi động JVM với property đó |

**Không có tác dụng thời gian thực:** việc thêm tên lớp vào file sau khi context đã khởi động **không tự gỡ bean đã được tạo**. Cần khởi động lại ứng dụng hoặc dùng một cơ chế khởi tạo context mới có chủ đích.

## 9. Kiểm thử tự động bằng ApplicationContextRunner

Để kiểm chứng property mà không phải khởi động một máy chủ web, Spring Boot cung cấp \`ApplicationContextRunner\`. Bài test tạo một context có \`@EnableAutoConfiguration\`, sau đó thử cả khi có và không có property exclude.

Tạo \`src/test/java/example/ExcludeAutoConfigurationTests.java\` trong dự án ở mục 8:

~~~java
package example;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ExcludeAutoConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void mapperExistsWithoutExclusion() {
        runner.run(context ->
                assertThat(context).hasSingleBean(ObjectMapper.class));
    }

    @Test
    void propertyExcludesJacksonAutoConfiguration() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                + "org.springframework.boot.autoconfigure.jackson."
                + "JacksonAutoConfiguration")
            .run(context ->
                assertThat(context).doesNotHaveBean(ObjectMapper.class));
    }
}
~~~

**Lưu ý:** để test đầu có ý nghĩa, dự án mẫu cần có Jackson starter và **không đặt exclude mặc định trong \`application.properties\`** hoặc những nguồn cấu hình khác của môi trường test. Test tạo hai context tách biệt và chỉ bật exclusion trong trường hợp thứ hai.

Chạy test:

~~~bash
mvn test -Dtest=ExcludeAutoConfigurationTests
~~~

Kết quả kỳ vọng: **2 test PASS**. \`ApplicationContextRunner\` mô phỏng property trong \`Environment\`; test thứ hai chứng minh chính cơ chế \`spring.autoconfigure.exclude\` loại Jackson auto-configuration. Để kiểm chứng cách shell truyền \`--...\`, vẫn nên chạy thêm ví dụ khởi động JAR ở mục 8.4, bởi \`withPropertyValues(...)\` không phải parser của command line.

## 10. So sánh với exclude trên annotation Java

Cách khác là dùng \`exclude\` ngay trên \`@SpringBootApplication\`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApplication {
}
~~~

Đây chỉ là **đoạn minh họa khai báo class**, không phải chương trình độc lập có \`main\`. Trong Spring Boot 3.5, class \`DataSourceAutoConfiguration\` có FQCN nêu trên.

Nếu muốn ghi tên lớp dạng chuỗi, chẳng hạn với dependency tùy chọn:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExampleApplication {
}
~~~

So sánh:

| Cách loại trừ | Khi nào phù hợp? | Điểm cần chú ý |
| --- | --- | --- |
| \`@SpringBootApplication(exclude = ...)\` | Quyết định gắn cố định với mã ứng dụng | Phải sửa/rebuild code để thay đổi |
| \`@SpringBootApplication(excludeName = "...")\` | Cần nêu FQCN dạng chuỗi | Tên phải đúng phiên bản |
| \`spring.autoconfigure.exclude\` trong file | Cấu hình riêng cho triển khai/profile | Có thể bị nguồn ưu tiên cao hơn ghi đè |
| \`--spring.autoconfigure.exclude=...\` | Thử nghiệm và triển khai dùng cùng JAR | Phải truyền đầy đủ danh sách mong muốn |

Với \`@EnableAutoConfiguration\` trực tiếp, thuộc tính \`exclude\` và \`excludeName\` cũng có ý nghĩa tương tự. Exclusions từ annotation và từ property có thể cùng được áp dụng: **loại trừ bằng property không hoàn tác loại trừ bằng annotation**.

## 11. Tên lớp phụ thuộc phiên bản Spring Boot

Tên FQCN là một phần đặc biệt quan trọng vì \`spring.autoconfigure.exclude\` nhận **chuỗi tên lớp**, không nhận alias hay tên ngắn.

| Auto-configuration | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| JDBC DataSource | \`org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration\` | \`org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration\` |
| Jackson | \`org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration\` | \`org.springframework.boot.jackson.autoconfigure.JacksonAutoConfiguration\` |

Ví dụ **Spring Boot 3.5.x**:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Ví dụ **Spring Boot 4.x**:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration
~~~

Do có thay đổi cấu trúc và dependency mặc định giữa các phiên bản, **không sao chép nguyên tên lớp của Boot 3 sang Boot 4** và không dự đoán kết quả tạo bean Jackson của Boot 4 theo ví dụ chạy trên Boot 3.5. Tra Javadoc/version BOM của dự án trước khi sử dụng.

Việc loại trừ một tên không phải auto-configuration hợp lệ hoặc loại đã đổi gói có thể khiến ứng dụng báo lỗi hoặc không có hiệu quả mong muốn, tùy lớp có tồn tại và cách framework kiểm tra danh sách loại trừ. Khi gặp lỗi, kiểm tra log thực tế; đừng dựa vào việc thiếu class mà cho rằng nó đã được vô hiệu hóa thành công.

## 12. Khi exclude là giải pháp đúng và khi cần cách khác

**Nên dùng** khi bạn chắc chắn một auto-configuration cụ thể không phù hợp ở môi trường chạy và muốn tắt toàn bộ cấu hình đó. Ví dụ máy chủ tự cung cấp JDBC DataSource theo một cơ chế khác và không muốn auto-configuration mặc định tranh quyền tạo datasource.

**Cân nhắc cách khác** nếu chỉ cần:
- Thay một bean mặc định: có thể đăng ký \`@Bean\` theo hợp đồng của Spring Boot để auto-configuration tự \`back off\` thông qua \`@ConditionalOnMissingBean\`.
- Bật/tắt tính năng theo nghiệp vụ: ưu tiên một property chuyên biệt (nếu có) hoặc \`@ConditionalOnProperty\` trên bean của ứng dụng.
- Không muốn một dependency xuất hiện trong artifact: sửa dependency trong Maven/Gradle; loại trừ auto-configuration **không** giảm kích thước/thành phần của JAR.
- Ngăn một lớp \`@Component\` bị scan: điều chỉnh package scan hoặc dùng bộ lọc scan phù hợp, vì \`spring.autoconfigure.exclude\` không nhắm vào component scan.

**Ảnh hưởng phụ:** loại trừ một auto-configuration có thể làm vắng những bean mà phần còn lại của ứng dụng đang phụ thuộc. Nếu có \`@Autowired ObjectMapper\` bắt buộc nhưng bạn exclude JacksonAutoConfiguration mà không tự định nghĩa mapper khác, ứng dụng có thể thất bại khi khởi động. Loại trừ cần được kiểm thử cùng các dependency tiêu thụ bean.

## 13. Chẩn đoán loại trừ có thật sự được áp dụng không

### Kiểm tra hiệu lực bằng Conditions Evaluation Report

Chạy JAR với \`--debug\` và thuộc tính exclude:

~~~bash
java -jar target/my-app.jar --debug --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Báo cáo điều kiện (**Conditions Evaluation Report**) giúp nhìn thấy những auto-configuration được match, không match hoặc bị loại trừ. Nó hữu ích hơn việc đoán theo việc một bean có mặt hay không.

Nếu ứng dụng sử dụng Spring Boot Actuator và endpoint chẩn đoán được bật/expose, \`/actuator/conditions\` cho biết thêm tình trạng condition; cần bảo vệ endpoint theo chính sách vận hành.

### Kiểm tra giá trị property thực sự được resolve

Khi kết quả không như mong đợi, rà soát:
1. Có cấu hình \`spring.autoconfigure.exclude\` trong \`application.properties\` hoặc YAML không?
2. Có tệp profile, tệp cấu hình bên ngoài JAR, environment variable hoặc JVM system property ghi đè không?
3. Có đối số ứng dụng \`--spring.autoconfigure.exclude=...\` được truyền tới **đúng tiến trình Java** không?
4. Tên lớp đã đúng phiên bản Spring Boot chưa?
5. Bean còn tồn tại có phải do một auto-configuration khác hoặc \`@Bean\` của người dùng tạo không?

Với Actuator đã được cấu hình và cho phép truy cập, \`/actuator/env\` có thể hỗ trợ điều tra nguồn giá trị; không nên công khai thông tin cấu hình vận hành không cần thiết.

**Đặc biệt:** không mặc định tin rằng hai danh sách \`spring.autoconfigure.exclude\` từ hai nguồn cấu hình sẽ tự cộng dồn. Khi bị ghi đè, hãy đặt toàn bộ tên cần exclude trong một giá trị nguồn thắng.

## 14. Những lỗi thường gặp

| Lỗi | Hiệu ứng có thể gặp | Cách khắc phục |
| --- | --- | --- |
| Dùng tên ngắn \`DataSourceAutoConfiguration\` | Không tìm đúng lớp auto-configuration | Dùng FQCN |
| Dùng FQCN Boot 3 trong dự án Boot 4 | Sai gói của class | Tra Javadoc đúng phiên bản |
| Ghi \`spring.auto-configure.exclude\` | Thuộc tính không đúng | Ghi chính xác \`spring.autoconfigure.exclude\` |
| Đặt \`--...\` trước \`-jar\` | Java launcher không xử lý như application argument | Đặt sau tên JAR |
| Tưởng CLI thêm vào danh sách trong file | Danh sách trong file có thể bị ghi đè | Truyền đủ mọi tên trong CLI |
| Exclude một \`@Component\` tự định nghĩa | Bean vẫn được scan | Điều chỉnh component scan hoặc cấu hình bean |
| Exclude Jackson rồi vẫn inject \`ObjectMapper\` mà không có nguồn khác | Ứng dụng có thể lỗi vì thiếu bean | Cung cấp bean thay thế hoặc bỏ exclude |
| Thêm tên class mới vào file mà không restart | Context đang chạy không tự thay đổi | Khởi động lại với cấu hình mới |
| Exclude một lớp được dùng bởi auto-config khác | Phát sinh lỗi phụ thuộc | Kiểm thử startup và các chức năng liên quan |

## 15. Bài tập thực hành

1. Trong dự án ví dụ mục 8, khởi động khi \`application.properties\` **không** chứa exclude. Quan sát \`OBJECT_MAPPER_PRESENT=true\`.
2. Thêm \`spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration\`, khởi động lại và xác nhận \`false\`.
3. Xóa property trong file, chạy JAR với đối số \`--spring.autoconfigure.exclude=...\` và xác nhận vẫn \`false\`.
4. Trong file ghi exclude Jackson; sau đó khởi động với command line chỉ exclude \`DataSourceAutoConfiguration\`. Kiểm tra xem \`ObjectMapper\` xuất hiện trở lại hay không. Giải thích bằng quy tắc nguồn ưu tiên cao hơn ghi đè danh sách property.
5. Chạy \`mvn test -Dtest=ExcludeAutoConfigurationTests\` khi đã dọn các exclude mặc định. Giải thích vì sao hai context trong test cho kết quả khác nhau.

**Câu hỏi tự kiểm tra:** \`spring.autoconfigure.exclude\` có loại bỏ mọi bean thuộc một kiểu bất kể nguồn tạo không?

**Đáp án:** Không. Nó loại trừ lớp auto-configuration được nêu tên. Bean được cấu hình thủ công hoặc tạo bởi nguồn khác có thể vẫn tồn tại.

**Câu hỏi tự kiểm tra:** \`@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)\` và một tham số CLI không exclude datasource thì kết quả ra sao?

**Đáp án:** Loại trừ đã khai báo bằng annotation vẫn còn. CLI chỉ điều chỉnh giá trị property, không hoàn tác annotation.

## 16. Tài liệu chính thức để đối chiếu

- Spring Boot Reference — Auto-configuration, phần Disabling Specific Auto-configuration Classes: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.5 Javadoc — \`EnableAutoConfiguration\`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot 3.5 Javadoc — \`DataSourceAutoConfiguration\`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 4 Javadoc — \`DataSourceAutoConfiguration\`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/autoconfigure/DataSourceAutoConfiguration.html
