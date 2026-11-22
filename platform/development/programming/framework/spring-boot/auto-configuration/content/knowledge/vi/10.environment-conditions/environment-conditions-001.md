# @ConditionalOnResource: kiểm tra tài nguyên classpath hoặc hệ thống tệp

## 1. Mục tiêu và bối cảnh

Trong Spring Boot Auto Configuration, một cấu hình đôi khi chỉ có ý nghĩa nếu ứng dụng **thực sự có một tài nguyên cần thiết**: tệp mẫu được đóng gói vào JAR, tệp định nghĩa adapter trên classpath, hay tệp cấu hình/tín hiệu nằm ngoài ứng dụng trên hệ thống tệp. Annotation **@ConditionalOnResource** cho phép quyết định **có đăng ký cấu hình hoặc bean hay không** dựa trên sự hiện diện của tài nguyên đó.

Sau bài học, người học cần có thể:

1. Giải thích lúc nào @ConditionalOnResource được đánh giá và vì sao nó ảnh hưởng đến việc đăng ký bean.
2. Viết đường dẫn đúng cho classpath và đường dẫn filesystem dùng tiền tố file:.
3. Áp dụng annotation trên @Configuration/@AutoConfiguration hoặc trên riêng một phương thức @Bean.
4. Hiểu điều kiện nhiều tài nguyên, kiểm tra tồn tại khác với đọc/kiểm tra nội dung, và hậu quả khi tệp thay đổi sau khởi động.
5. Chạy ví dụ Java 17+ để kiểm chứng bean có hoặc không được đăng ký, rồi chẩn đoán bằng condition report.

Phân biệt ngay từ đầu: @ConditionalOnResource trả lời **“tài nguyên đã tồn tại lúc Spring xét cấu hình chưa?”**, không phải “Spring có đọc và phân tích nội dung tệp đúng không?” hoặc “tệp có tồn tại ở mọi thời điểm suốt quá trình chạy không?”.

## 2. Khái niệm và cơ chế

**Annotation:** org.springframework.boot.autoconfigure.condition.ConditionalOnResource, thuộc Spring Boot (không phải annotation của Java hoặc Spring Framework cơ bản).

Cách dùng cơ bản:

~~~java
@Bean
@ConditionalOnResource(resources = "classpath:demo/ready.flag")
FeatureService featureService() {
    return new FeatureService();
}
~~~

Đây là **phương thức minh họa đặt trong một class @Configuration hoặc @AutoConfiguration**; FeatureService là kiểu ứng dụng tự định nghĩa.

Trong khi xử lý các bean definition, Spring Boot đánh giá điều kiện với **ResourceLoader** của Spring. Nó diễn giải từng resource location và kiểm tra tài nguyên có tồn tại hay không. Khi điều kiện khớp, định nghĩa cấu hình/bean được chấp nhận để xử lý; khi không khớp, định nghĩa gắn với annotation bị bỏ qua.

~~~text
Khởi tạo ApplicationContext
    |
    v
Đọc cấu hình và xử lý các định nghĩa bean
    |
    v
Gặp @ConditionalOnResource(resources = ...)
    |
    +-- Mọi tài nguyên được yêu cầu đều tồn tại?
          |
          +-- Có  ---> Điều kiện MATCH ---> Đăng ký cấu hình/bean
          |
          +-- Không ---> Điều kiện NO MATCH ---> Bỏ qua cấu hình/bean
    |
    v
Khởi tạo các bean phù hợp, giải quyết dependency và hoàn tất startup
~~~

Những điểm cơ bản:

- **Điều kiện là một cổng đăng ký bean.** Nếu không match, bean có điều kiện không xuất hiện trong ApplicationContext.
- **Không tự đọc nội dung.** Một tệp tồn tại nhưng rỗng hoặc sai định dạng vẫn có thể khiến điều kiện match; code tạo bean phải tự đọc/kiểm tra khi cần.
- **Không tự theo dõi filesystem.** Thêm/xóa tệp sau khi điều kiện đã được đánh giá không tự đăng ký hoặc hủy bean đang chạy. Thông thường phải khởi tạo lại ApplicationContext/khởi động lại ứng dụng để đánh giá lại.
- **Không biến điều kiện thành một health check.** Resource tồn tại lúc startup chưa đảm bảo luôn đọc được trong tương lai hoặc dịch vụ sử dụng resource luôn sẵn sàng.
- **Khi yêu cầu nhiều resource, tất cả đều phải tồn tại** để điều kiện khớp (quan hệ AND, không phải OR).

## 3. Cú pháp và nơi đặt annotation

### 3.1. Trên phương thức @Bean

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {
    @Bean
    @ConditionalOnResource(resources = "classpath:reports/default-template.txt")
    ReportRenderer reportRenderer() {
        return new ReportRenderer();
    }
}
~~~

Đây là **mẫu cấu hình minh họa**: cần các import Spring phù hợp và các class ReportRenderer của ứng dụng. Chỉ bean reportRenderer chịu điều kiện; các bean khác trong ReportConfiguration (nếu có) vẫn được xét bình thường.

### 3.2. Trên class cấu hình

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(resources = "classpath:reports/default-template.txt")
class ReportFeatureConfiguration {
    @Bean
    ReportRenderer reportRenderer() {
        return new ReportRenderer();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
~~~

Đây cũng là **mẫu minh họa**, không phải chương trình Java độc lập. Khi thiếu resource, **cả cấu hình này bị loại khỏi quá trình đăng ký**, do đó cả hai phương thức @Bean trong cấu hình không được đăng ký thông qua class này.

Trong thư viện auto-configuration, vị trí trên class thường dùng khi **toàn bộ một tính năng** cần resource; vị trí trên @Bean phù hợp khi **chỉ một bean tùy chọn** phụ thuộc vào resource.

### 3.3. Nhiều tài nguyên trong resources

~~~java
@ConditionalOnResource(resources = {
    "classpath:features/schema.json",
    "classpath:features/rules.json"
})
~~~

Điều kiện trên chỉ khớp khi **cả schema.json lẫn rules.json** tồn tại. Nếu thiếu một trong hai, cấu hình/bean bị loại. Đây **không phải danh sách ứng viên để chọn một**, cũng không kiểm tra JSON có hợp lệ hay không.

## 4. Phân biệt tài nguyên classpath và filesystem

| Vị trí | Cú pháp điển hình | Tài nguyên thực sự nằm ở đâu? | Khi nào nên dùng? |
| --- | --- | --- | --- |
| Classpath | classpath:features/ready.flag | Bên trong các thư mục và JAR trên classpath lúc chạy | Tính năng phụ thuộc tệp đóng gói cùng ứng dụng hoặc thư viện |
| Linux/macOS filesystem | file:/opt/myapp/config/feature.flag | Tệp tại đường dẫn tuyệt đối trên máy chạy | Tài nguyên được triển khai, mount hoặc quản lý bên ngoài JAR |
| Windows filesystem | file:///C:/myapp/config/feature.flag | Tệp trên ổ C của máy chạy | Cùng tình huống filesystem nhưng đường dẫn theo Windows |
| Không có tiền tố | features/ready.flag | Phụ thuộc cách ResourceLoader/ApplicationContext diễn giải | Không khuyến khích cho cấu hình cần phân biệt rõ classpath và disk |

**Classpath:** Trong dự án Maven/Gradle thông thường, tệp đặt ở src/main/resources/features/ready.flag sẽ được copy vào classpath đầu ra và đóng gói trong JAR. Khi dùng annotation:

~~~java
@ConditionalOnResource(resources = "classpath:features/ready.flag")
~~~

Spring tìm **resource ở classpath lúc chạy**. Không cần và không nên giả định có file độc lập tại đường dẫn src/main/resources khi JAR đã triển khai. Tệp cùng tên cũng có thể đến từ một dependency JAR, nên thư viện nên dùng tên/path đủ đặc trưng để tránh vô tình match do trùng tên.

**Filesystem:** Với:

~~~java
@ConditionalOnResource(resources = "file:/opt/myapp/config/feature.flag")
~~~

Spring kiểm tra đường dẫn filesystem bên ngoài ứng dụng. Tệp đó **không tự được đóng gói vào JAR**. Trên Windows có thể dùng cú pháp file:///C:/myapp/config/feature.flag cho một đường dẫn tuyệt đối. Đường dẫn tuyệt đối minh bạch hơn đường dẫn tương đối, bởi working directory khi chạy từ IDE, CI, Docker, systemd hoặc java -jar có thể khác nhau.

**Lưu ý về ký hiệu:** classpath: chỉ một location cụ thể trong ví dụ này; file: chỉ URL tài nguyên filesystem. Không mặc định rằng cú pháp quét nhiều resource **classpath*:** hay wildcard kiểu **/*.json** được @ConditionalOnResource xử lý như cơ chế tìm nhiều tệp. Annotation kiểm tra resource location được ResourceLoader trả về; muốn tìm và đếm các resource bằng mẫu, cần ResourcePatternResolver hoặc condition tùy chỉnh phù hợp.

**Bảng so sánh triển khai:**

| Tình huống | classpath: | file: |
| --- | --- | --- |
| Tệp được đóng gói trong ứng dụng JAR | Phù hợp | Không, trừ khi cũng được copy thành tệp riêng trên disk |
| Thay đổi một file ngoài JAR rồi khởi động lại | Không tự dùng bản ngoài JAR | Phù hợp nếu trỏ đúng path |
| Chạy trong container | Phụ thuộc nội dung image/JAR | Phụ thuộc volume/mount và quyền truy cập |
| Dùng cùng đường dẫn trên các hệ điều hành | Tương đối dễ vì slash và tên resource | Phải chú ý cú pháp path của hệ điều hành |
| Dùng nội dung như java.io.File | Không an toàn khi resource nằm bên trong JAR | Thường có thể quy về file thực, nếu thích hợp |

Khi cần **đọc dữ liệu từ classpath JAR**, ưu tiên Spring Resource.getInputStream() thay vì Resource.getFile(), vì mục tiêu có thể nằm bên trong JAR và không phải một File độc lập.

## 5. Ví dụ Java 17+ chạy được: kiểm tra classpath và đăng ký bean

Ví dụ sau cung cấp một ứng dụng Spring Boot tối thiểu, không cần database hoặc web server. Nó kiểm tra ba bean:

- **readyFeature**: tạo khi classpath có features/ready.flag.
- **optionalFeature**: tạo khi classpath có features/optional.flag.
- **combinedFeature**: chỉ tạo khi cả hai file cùng có mặt.

### 5.1. Cấu trúc dự án

~~~text
resource-condition-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/resourcecondition/
        │       └── ResourceConditionApplication.java
        └── resources/
            └── features/
                └── ready.flag
~~~

**Không tạo features/optional.flag trong lượt chạy đầu tiên**.

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resource-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

Parent Spring Boot quản lý version các thư viện. spring-boot-starter cung cấp ApplicationContext và auto-configuration cơ bản; spring-boot-maven-plugin dùng để khởi động/đóng gói JAR có thể chạy.

### 5.3. ResourceConditionApplication.java

Tạo file **src/main/java/com/example/resourcecondition/ResourceConditionApplication.java**:

~~~java
package com.example.resourcecondition;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@SpringBootApplication
public class ResourceConditionApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ResourceConditionApplication.class, args)) {
            System.out.println("readyFeature=" + context.containsBean("readyFeature"));
            System.out.println("optionalFeature=" + context.containsBean("optionalFeature"));
            System.out.println("combinedFeature=" + context.containsBean("combinedFeature"));
        }
    }
}

record FeatureMarker(String source) {
}

@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @ConditionalOnResource(resources = "classpath:features/ready.flag")
    FeatureMarker readyFeature() {
        return new FeatureMarker("ready");
    }

    @Bean
    @ConditionalOnResource(resources = "classpath:features/optional.flag")
    FeatureMarker optionalFeature() {
        return new FeatureMarker("optional");
    }

    @Bean
    @ConditionalOnResource(resources = {
        "classpath:features/ready.flag",
        "classpath:features/optional.flag"
    })
    FeatureMarker combinedFeature() {
        return new FeatureMarker("both");
    }
}
~~~

**Điểm cần hiểu trong mã:**

1. @SpringBootApplication kích hoạt cấu hình ứng dụng; FeatureConfiguration nằm cùng package nên được component scan xử lý.
2. @ConditionalOnResource được gắn cho từng phương thức @Bean. Không có bean được tạo bởi phương thức bị loại khỏi đăng ký.
3. context.containsBean("...") kiểm tra bean name **thực tế** trong ApplicationContext. Nó không chỉ kiểm tra giá trị property.
4. record FeatureMarker là kiểu Java 17 dùng làm giá trị demo; không có cơ chế “bí mật” trong bean. Mục đích của ví dụ là quan sát registration.

### 5.4. Tệp tài nguyên bắt buộc

Tạo file **src/main/resources/features/ready.flag** với nội dung:

~~~text
present
~~~

Giá trị present **không được annotation phân tích**; tệp tồn tại là đủ để xét điều kiện. Không có file features/optional.flag trong lượt chạy đầu.

### 5.5. Chạy thử và kết quả

Ở thư mục resource-condition-demo, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Sau các log Spring Boot, ba dòng do chương trình in ra là:

~~~text
readyFeature=true
optionalFeature=false
combinedFeature=false
~~~

Lý giải từng dòng:

- ready.flag nằm trên classpath, nên readyFeature được đăng ký.
- optional.flag chưa tồn tại, nên optionalFeature không được đăng ký.
- combinedFeature yêu cầu **cả ready.flag và optional.flag**; thiếu optional.flag khiến điều kiện không match.

Bây giờ thêm file **src/main/resources/features/optional.flag** (nội dung bất kỳ, ví dụ present), dừng ứng dụng và chạy lại cùng lệnh. Ba dòng trở thành:

~~~text
readyFeature=true
optionalFeature=true
combinedFeature=true
~~~

Xóa cả hai file nguồn và chạy lại sẽ khiến cả ba điều kiện không match, với kết quả:

~~~text
readyFeature=false
optionalFeature=false
combinedFeature=false
~~~

Muốn kiểm chứng khi chạy bằng JAR đóng gói:

~~~bash
mvn package
java -jar target/resource-condition-demo-1.0.0.jar
~~~

**Quan trọng:** Phải build lại JAR sau khi thêm/xóa file trong src/main/resources. Sửa trực tiếp thư mục nguồn sau khi đã đóng gói **không** thay đổi classpath bên trong JAR đã build.

## 6. Kiểm tra filesystem: tài nguyên ngoài JAR

Ví dụ tiếp theo mô phỏng một tệp marker do người triển khai đặt vào máy chủ. Đặt cấu hình sau trong cùng package với ứng dụng (có thể tạo **src/main/java/com/example/resourcecondition/FileFeatureConfiguration.java**):

~~~java
package com.example.resourcecondition;

import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class FileFeatureConfiguration {
    @Bean
    @ConditionalOnResource(resources = "file:/opt/resource-demo/feature.flag")
    FileFeature fileFeature() {
        return new FileFeature();
    }
}

final class FileFeature {
}
~~~

Đây là **tệp Java hoàn chỉnh để thêm vào dự án mẫu**. Đường dẫn file:/opt/resource-demo/feature.flag dành cho hệ thống kiểu Linux. Để thử trên Linux, có thể tạo file trước khi khởi động:

~~~bash
mkdir -p /opt/resource-demo
touch /opt/resource-demo/feature.flag
mvn spring-boot:run
~~~

Tùy quyền trên máy, có thể cần chọn thư mục tuyệt đối khác mà tài khoản chạy ứng dụng có quyền đọc. Khi file tồn tại, bean fileFeature được đăng ký; khi file thiếu, bean không được đăng ký. Để kiểm tra ngay trong chương trình, thêm dòng sau trong khối try ở phương thức main:

~~~java
System.out.println("fileFeature=" + context.containsBean("fileFeature"));
~~~

Đoạn một dòng này **phụ thuộc biến context trong ví dụ ở mục 5**, không phải chương trình Java độc lập. Với đường dẫn hiện diện, dòng tương ứng là fileFeature=true; khi không hiện diện, là fileFeature=false.

Trên Windows, đổi chuỗi annotation sang URL tuyệt đối phù hợp, ví dụ:

~~~java
@ConditionalOnResource(resources = "file:///C:/resource-demo/feature.flag")
~~~

và tạo tệp **C:\resource-demo\feature.flag** trước khi chạy. Đây là thay đổi path trong annotation, không phải việc tạo một bean khác. Nếu triển khai bằng Docker, đường dẫn phải tồn tại **bên trong filesystem của container**; tệp chỉ có trên máy host nhưng không được mount vào container sẽ không thỏa điều kiện.

**Không nhầm với classpath:** Có file src/main/resources/features/ready.flag không có nghĩa file:/opt/resource-demo/feature.flag tồn tại. Ngược lại, mount một file ngoài JAR cũng không tự khiến classpath:features/ready.flag xuất hiện.

### 6.1. Điều gì xảy ra nếu xóa file sau khi ứng dụng đã chạy?

Giả sử lúc startup file:/opt/resource-demo/feature.flag có mặt: fileFeature được đăng ký. Sau đó file bị xóa:

- Spring **không tự hủy** fileFeature.
- Spring **không tự đánh giá lại** @ConditionalOnResource để quyết định đăng ký hoặc loại bỏ bean.
- Nếu phương thức của bean cần đọc file sau đó, thao tác đọc có thể thất bại vì file đã mất.

Để thử nhánh “không có file”, hãy khởi động lại ApplicationContext sau khi xóa file, và kiểm tra bean name. Nếu cần hệ thống phản ứng tức thì với thay đổi file, phải thiết kế cơ chế theo dõi hoặc reload riêng; @ConditionalOnResource không thay thế cơ chế đó.

## 7. Kiểm tra tồn tại không có nghĩa là tệp hợp lệ

Một resource có thể hiện diện nhưng:

- Nội dung rỗng hoặc sai định dạng JSON/YAML/XML.
- Là đường dẫn thư mục thay vì tệp mà chương trình dự kiến đọc.
- Bị thay đổi/xóa giữa lúc điều kiện được xét và lúc bean thực sự mở luồng đọc.
- Không đủ quyền đọc trong runtime, hoặc phụ thuộc mạng/volume chưa ổn định.
- Có cùng tên classpath trong dependency JAR khác, khiến điều kiện match ngoài dự kiến.

Vì vậy, khi nội dung **thực sự cần thiết**, hãy kiểm tra và xử lý lỗi ngay trong code sử dụng tài nguyên. Ví dụ sau minh họa một @Bean đọc tệp văn bản classpath đúng cách:

~~~java
@Bean
@ConditionalOnResource(resources = "classpath:features/message.txt")
String featureMessage(org.springframework.core.io.ResourceLoader loader)
        throws java.io.IOException {
    var resource = loader.getResource("classpath:features/message.txt");
    try (var input = resource.getInputStream()) {
        String content = new String(
                input.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8
        ).trim();
        if (content.isEmpty()) {
            throw new IllegalStateException("Message file is empty");
        }
        return content;
    }
}
~~~

Đây là **phương thức minh họa cần đặt trong class cấu hình**; không cần chuyển tài nguyên classpath thành java.io.File. Condition giúp tránh gọi phương thức tạo bean khi resource không tồn tại; phương thức vẫn phải xử lý nội dung rỗng và IOException nếu tài nguyên có vấn đề.

**Quy tắc thiết kế:** Nếu thiếu tệp nghĩa là tính năng không nên được bật, dùng điều kiện để bỏ qua bean. Nếu tệp là dữ liệu **bắt buộc** để ứng dụng hoạt động đúng, cần lỗi cấu hình rõ ràng và fail-fast thay vì âm thầm tắt thành phần quan trọng. Điều kiện chỉ phù hợp khi vắng mặt tài nguyên là trạng thái được thiết kế và xử lý hợp lệ.

## 8. Dùng trong auto-configuration của một thư viện

Ví dụ minh họa một thư viện chỉ đăng ký bộ xử lý mẫu khi classpath có resource của module:

~~~java
package com.example.library;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnResource;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:META-INF/example-library/adapter-template.txt")
public class AdapterAutoConfiguration {
    @Bean
    public AdapterService adapterService() {
        return new AdapterService();
    }
}
~~~

**AdapterService là class do thư viện cung cấp** và phải tồn tại cùng source; đoạn trên minh họa cấu hình thư viện, không phải toàn bộ project độc lập. Để Spring Boot 3 tự nạp auto-configuration của JAR thư viện, đăng ký tên class trong:

**META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.AdapterAutoConfiguration
~~~

Khi ứng dụng tiêu thụ thêm dependency thư viện:

- Nếu resource META-INF/example-library/adapter-template.txt có trên classpath, class cấu hình đủ điều kiện để cung cấp AdapterService.
- Nếu resource không có, cả AdapterAutoConfiguration bị loại bởi condition.
- Một resource hiện diện trên classpath cũng có thể đến từ **JAR dependency khác**; nếu đó không phải điều mong muốn, cần chọn tên path được namespace rõ ràng hoặc một điều kiện có thêm ràng buộc.

Có thể kết hợp nhiều điều kiện **AND** ở cùng một cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.library.AdapterService")
@ConditionalOnResource(
        resources = "classpath:META-INF/example-library/adapter-template.txt")
class AdapterOptionalAutoConfiguration {
    // Các phương thức @Bean của module tùy chọn
}
~~~

Đây là đoạn **minh họa cấu hình**, không phải class đầy đủ để biên dịch nguyên xi. Cả class và resource đều phải phù hợp. Trong dự án thật, vẫn phải bảo đảm các class được tham chiếu trực tiếp chỉ được load khi dependency tương ứng tồn tại; điều kiện không thay thế quản lý dependency.

## 9. So sánh với các điều kiện Spring Boot khác

| Annotation | Điều kiện quan tâm | Ví dụ mục tiêu |
| --- | --- | --- |
| @ConditionalOnResource | Có resource tại một location được chỉ rõ? | Chỉ đăng ký template renderer khi có tệp template |
| @ConditionalOnClass | Có class trên classpath? | Bật adapter khi dependency Java được cài |
| @ConditionalOnProperty | Property có giá trị thỏa yêu cầu? | Bật tính năng bằng feature.enabled=true |
| @ConditionalOnBean | Có bean phù hợp đã được xử lý? | Chỉ tạo metrics adapter nếu service chính tồn tại |
| @ConditionalOnMissingBean | Chưa có bean phù hợp đã được xử lý? | Cung cấp bean mặc định khi người dùng chưa tự cấu hình |
| @Profile | Profile Spring hiện tại có khớp không? | Chỉ tạo bean cho môi trường dev/prod |

**Dùng đúng công cụ:**

- Muốn **bật/tắt có chủ đích** bằng cấu hình vận hành? Thường chọn @ConditionalOnProperty.
- Muốn kiểm tra **thư viện Java/API** có trên classpath? Chọn @ConditionalOnClass.
- Muốn kiểm tra **tệp/tài nguyên vật lý** có sẵn? Chọn @ConditionalOnResource.
- Muốn quyết định theo **bean do người dùng cung cấp**? Chọn @ConditionalOnBean hoặc @ConditionalOnMissingBean.
- Muốn đọc một file cấu hình và merge property vào Spring Environment? Dùng cơ chế nạp cấu hình thích hợp như spring.config.import hoặc @PropertySource khi phù hợp; @ConditionalOnResource **không tự nạp property** từ file.

**Ví dụ phân biệt:** feature.audit.enabled=false nhưng classpath:features/audit.flag tồn tại. @ConditionalOnResource trên file này vẫn có thể match vì nó kiểm tra **tồn tại file**, không kiểm tra property feature.audit.enabled. Muốn cả hai điều kiện, có thể đặt thêm @ConditionalOnProperty trên cấu hình/bean; điều kiện chung là AND.

## 10. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân hay gặp | Kiểm tra/cách sửa |
| --- | --- | --- |
| File nằm trong src/main/resources nhưng condition không match | File chưa được copy vào runtime classpath/JAR, hoặc sai tên/path/chữ hoa-thường | Xem target/classes, nội dung JAR và chuỗi classpath: thực tế |
| Chạy từ IDE được, chạy JAR không được | Đường dẫn không prefix phụ thuộc working directory; file có trong source tree nhưng không đóng gói | Dùng classpath: cho tài nguyên đóng gói, file: tuyệt đối cho tài nguyên bên ngoài |
| file: match trên máy dev nhưng không match trong container | Tệp chỉ tồn tại trên host; volume chưa mount hoặc path trong container khác | Xem filesystem bên trong container và quyền trên đường dẫn đích |
| Có resource nhưng bean bị bỏ qua | Có điều kiện bổ sung khác không match, resource sai location, hoặc annotation ở class bao ngoài | Xem condition report và nơi đặt annotation |
| Bean tồn tại dù tệp đã bị xóa khi ứng dụng đang chạy | Condition chỉ xét khi tạo context, không có watcher tự động | Khởi động lại context; nếu cần dynamic reload, thiết kế riêng |
| File tồn tại nhưng khởi tạo bean vẫn lỗi | Resource có nội dung sai/không đọc được; condition không kiểm tra schema hay parsing | Bổ sung validation/exception rõ ràng trong code bean |
| Dùng classpath*: hoặc wildcard nhưng kết quả không như mong muốn | @ConditionalOnResource kiểm tra location cụ thể, không phải API quét tài nguyên theo pattern | Dùng resource path cụ thể hoặc custom Condition + ResourcePatternResolver |
| Một đường dẫn điều kiện dùng được trên Linux nhưng không trên Windows | URL/path filesystem không portable | Dùng path tuyệt đối phù hợp OS, hoặc cấu hình điều kiện riêng |

### 10.1. Bật Condition Evaluation Report

Trong dự án Maven mẫu, có thể chạy:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Hoặc với JAR đã đóng gói:

~~~bash
java -jar target/resource-condition-demo-1.0.0.jar --debug
~~~

Spring Boot có thể xuất **Condition Evaluation Report** giúp phân biệt điều kiện khớp và không khớp, bao gồm lý do thiếu resource nếu đối tượng cấu hình được đưa vào báo cáo. Tùy mức logging và cách ứng dụng khởi động, phần thông tin cụ thể có thể được trình bày khác nhau. Đừng chỉ đoán dựa trên việc một bean vắng mặt; đọc cả thông tin condition và các điều kiện khác trên class/method.

### 10.2. Kiểm tra resource bằng chính ResourceLoader

Khi cần chẩn đoán đường dẫn, có thể dùng đoạn sau trong một bean/service đã có ResourceLoader:

~~~java
var resource =
        resourceLoader.getResource("classpath:features/ready.flag");
System.out.println(resource.exists());
~~~

Đây là **đoạn minh họa**, biến resourceLoader phải được inject hoặc khai báo trước. ResourceLoader diễn giải location theo Spring; không thay thế trực tiếp bằng Files.exists(Path.of("src/main/resources/...")) vì đó là đường dẫn **trong source tree**, không nhất thiết còn hiện diện khi chạy từ JAR.

## 11. Tình huống thực tế: chọn thiết kế phù hợp

**Tình huống A: plugin dùng template tùy chọn.** Nếu muốn chỉ đăng ký plugin khi file template của nó được đóng gói cùng dependency, classpath: với @ConditionalOnResource rất phù hợp. Nếu template không có, code gọi plugin cũng phải chịu được việc không có bean đó; nếu không, startup sẽ lỗi vì dependency thiếu.

**Tình huống B: ứng dụng có file license/config do vận hành mount vào container.** Nếu việc thiếu file có nghĩa tính năng **tùy chọn** phải bị tắt, có thể dùng file: và condition. Nếu file là điều kiện **bắt buộc** để ứng dụng hoạt động, fail-fast với thông báo cấu hình rõ hơn. Kiểm tra file path bên trong container, không chỉ trên host.

**Tình huống C: cấu hình bật/tắt có chủ đích nhưng resource luôn có sẵn.** Chỉ kiểm tra resource không thể thay thế flag; chọn @ConditionalOnProperty hoặc kết hợp property và resource.

**Tình huống D: cần phản ứng khi file xuất hiện trong lúc app chạy.** @ConditionalOnResource không tự thay đổi bean graph sau startup. Có thể thiết kế watcher, refresh hoặc application-managed state riêng; đừng nhầm startup condition với dynamic feature toggle.

## 12. Câu hỏi tự đánh giá

**Câu 1.** Có file src/main/resources/features/a.flag trong dự án nhưng JAR được build trước khi file được thêm. @ConditionalOnResource(resources = "classpath:features/a.flag") có chắc match khi chạy JAR cũ không?  
**Đáp án:** Không. Classpath lúc chạy JAR cũ không tự đổi theo source tree; phải build lại artifact chứa file.

**Câu 2.** Annotation yêu cầu resources = {"classpath:a.txt", "classpath:b.txt"}. Chỉ a.txt tồn tại. Điều kiện khớp không?  
**Đáp án:** Không. Mọi resource trong danh sách đều phải tồn tại.

**Câu 3.** @ConditionalOnResource đặt trên class @Configuration và thiếu file. Hai @Bean trong class có được đăng ký không?  
**Đáp án:** Không qua class cấu hình đó, vì cả class bị condition loại.

**Câu 4.** File chứa JSON sai cú pháp nhưng đường dẫn tồn tại. @ConditionalOnResource có chắc loại bean không?  
**Đáp án:** Không. Nó chỉ kiểm tra sự hiện diện, không parse JSON; logic tạo/đọc bean phải kiểm tra và báo lỗi nếu cần.

**Câu 5.** Đã tạo file trên máy host nhưng app chạy trong container vẫn báo điều kiện false. Kiểm tra gì?  
**Đáp án:** Kiểm tra file đã mount vào container chưa, đường dẫn file: trong container có đúng không và tài khoản chạy app có truy cập được không.

**Câu 6.** Một bean đã tạo, sau đó xóa tệp từng làm condition match. Bean có tự biến mất không?  
**Đáp án:** Không. @ConditionalOnResource được đánh giá trong quá trình tạo context, không tự reload sau thay đổi runtime.

**Câu 7.** Mục tiêu là bật/tắt feature bằng application.properties dù file luôn nằm trong JAR. Dùng gì?  
**Đáp án:** @ConditionalOnProperty, hoặc kết hợp nếu vừa cần flag vừa cần file. @ConditionalOnResource riêng lẻ không kiểm tra ý định bật/tắt của property.

## 13. Ghi nhớ và tài liệu tra cứu

- **classpath:** kiểm tra tài nguyên trên runtime classpath, thường được đóng gói từ src/main/resources hoặc nằm trong dependency JAR.
- **file:** kiểm tra tài nguyên ở filesystem, phải dùng đường dẫn phù hợp nơi chương trình thực sự chạy.
- **@ConditionalOnResource** quyết định đăng ký class cấu hình/@Bean **dựa trên tồn tại resource**, không xác nhận nội dung hợp lệ và không giám sát file suốt runtime.
- **Nhiều resource = tất cả đều cần hiện diện.** Nếu thiếu một resource, điều kiện không match.
- **Chẩn đoán theo hai bước:** kiểm tra location resource trong môi trường chạy, rồi xem Condition Evaluation Report và mọi điều kiện liên quan.

Tài liệu chính thức để tra cứu thêm:

- Spring Boot, ConditionalOnResource API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html
- Spring Framework, Resource và ResourceLoader: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Boot Reference, Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
