# Phân biệt lỗi không khám phá được ứng viên auto-configuration và điều kiện của ứng viên không thỏa mãn

## 1. Vấn đề và mục tiêu

Một câu báo lỗi thường gặp trong Spring Boot là: **“Đã thêm starter hoặc viết @AutoConfiguration, nhưng bean mong đợi vẫn không xuất hiện.”** Triệu chứng đó có thể đến từ ít nhất hai giai đoạn rất khác nhau:

- **Không khám phá được ứng viên (candidate discovery failure):** Spring Boot không tìm thấy lớp auto-configuration trong danh sách ứng viên của lần chạy này. Nếu không có một cơ chế import khác, lớp cấu hình không tham gia pipeline auto-configuration để điều kiện của nó được đánh giá.
- **Ứng viên đã được khám phá nhưng điều kiện không thỏa mãn (condition mismatch):** Spring Boot biết đến lớp cấu hình, nhưng một hoặc nhiều `@Conditional` tại lớp hay phương thức `@Bean` không khớp; phần cấu hình hoặc bean tương ứng không được đăng ký.

Cả hai có thể dẫn đến cùng một kết quả: `ApplicationContext` không có bean mong đợi. Vì vậy, **“không có bean” không đủ để kết luận “không tải được auto-configuration”**.

Sau bài học, bạn có thể xác định đúng giai đoạn lỗi, hiểu bằng chứng nào đủ mạnh cho từng trường hợp, kiểm tra classpath và metadata, đọc `ConditionEvaluationReport`, phân biệt thêm exclusions và bean back-off, cũng như thực hành trên dự án Java 17+ chạy được.

Phạm vi thuộc nhóm **Khám phá ứng viên** của Spring Boot auto-configuration. Bài tập trung vào chuỗi chẩn đoán từ **tài nguyên imports → tên lớp ứng viên → lọc/loại trừ → điều kiện → bean definition**. Nó không biến mọi nguyên nhân khởi động lỗi thành một lỗi khám phá.

## 2. Bản đồ vòng đời: kiểm tra lỗi ở đúng chỗ

Khi ứng dụng có `@SpringBootApplication` (bao gồm `@EnableAutoConfiguration`), có thể hiểu luồng chính như sau:

~~~text
Dependency / JAR trên runtime classpath
        |
        v
Tài nguyên META-INF/spring/
org.springframework.boot.autoconfigure.AutoConfiguration.imports
        |
        v
Đọc các fully qualified class names
        |
        +---- Không thấy tài nguyên / không có tên lớp mong đợi
        |          -> Ứng viên không được công bố/không được khám phá
        |
        v
AutoConfigurationImportSelector
        |
        +---- Exclusion / filter chọn ứng viên
        |          -> Có thể bị loại khỏi danh sách import
        |
        v
Xử lý lớp @AutoConfiguration được chọn
        |
        +---- Điều kiện cấp lớp không khớp
        |          -> Bỏ qua cấu hình
        |
        v
Xử lý các @Bean trong cấu hình
        |
        +---- Điều kiện cấp @Bean không khớp
        |          -> Bỏ qua riêng bean definition đó
        |
        v
Đăng ký bean definitions hợp lệ
        |
        v
Khởi tạo bean theo IoC container
        |
        +---- Lỗi constructor / dependency / lifecycle?
                   -> Lỗi tạo bean, không phải lỗi discovery
~~~

Sơ đồ nhằm chỉ rõ **các cổng quyết định**, không cam kết tất cả annotation điều kiện đều được chạy vào cùng một thời điểm hoặc mọi filter đều để lại cùng một dòng log. Spring Boot có các bước lọc ứng viên và Spring Framework có các pha phân tích/đăng ký cấu hình khác nhau.

Ba câu hỏi phải tách riêng:

1. **Có class trong classpath không?** Kiểm tra dependency và nội dung JAR.
2. **Class có được đăng ký làm ứng viên auto-configuration không?** Kiểm tra tệp `AutoConfiguration.imports` đúng classpath của tiến trình.
3. **Ứng viên được chọn có thỏa điều kiện để đăng ký bean không?** Kiểm tra `@Conditional`, exclusions, properties, bean hiện có và condition report.

Có tên lớp trong metadata **chưa đủ** để bảo đảm bean tồn tại. Có tên lớp trong source code **chưa đủ** để bảo đảm Spring Boot biết lớp đó là một ứng viên.

## 3. Nhận diện lỗi “không khám phá được ứng viên”

Trong Spring Boot 3.x, thư viện thường công bố các lớp tự cấu hình qua tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tệp chứa **một tên lớp đầy đủ trên mỗi dòng**:

~~~text
com.example.feature.autoconfigure.FeatureAutoConfiguration
~~~

Ví dụ dự án Maven đặt tệp tại:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Các lỗi điển hình:

- **Không tạo tệp imports:** class có `@AutoConfiguration` nhưng không được liệt kê trên runtime classpath.
- **Sai vị trí hoặc tên:** đặt dưới `src/main/java`, `src/test/resources`, thư mục `META-INF` sai cấp, thiếu chữ `AutoConfiguration`, sai chữ hoa/chữ thường.
- **Sai FQCN:** đổi package hoặc class nhưng quên cập nhật một dòng trong imports file.
- **Sai artifact/classpath:** dự án đã build module chứa metadata nhưng ứng dụng thực tế không có module đó trong dependency runtime, hoặc đang chạy một JAR cũ.
- **Nhầm cơ chế phiên bản:** sao chép đoạn đăng ký `EnableAutoConfiguration` trong `spring.factories` từ dự án Boot cũ cho Boot 3.x. Spring Boot 2.7 giới thiệu imports file; với Boot 3.x, cần theo cách đăng ký phù hợp với phiên bản đó.
- **Vô tình dựa vào component scan:** trong ứng dụng khác, class tự cấu hình nằm ngoài vùng quét mặc định; chỉ annotation `@AutoConfiguration` trên class không làm Spring Boot tự tìm class.
- **Tài nguyên bị lọc khi build:** custom resource configuration, packaging plugin hoặc bước phát hành đã bỏ tệp khỏi JAR.

### Bằng chứng chẩn đoán mạnh

**Bằng chứng 1 — artifact có chứa file không?** Với JAR thư viện thông thường:

~~~bash
jar tf path/to/feature-autoconfigure.jar
~~~

Tìm entry:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Với Spring Boot executable JAR chứa auto-configuration trong module ứng dụng, đường dẫn thường là:

~~~text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu metadata nằm trong JAR dependency, nó thường ở bên trong JAR lồng tại `BOOT-INF/lib`, vì thế cần kiểm tra chính dependency đó. `jar tf` chỉ liệt kê entry, **không** hiển thị nội dung file.

**Bằng chứng 2 — đọc nội dung metadata.** Xác minh dòng tương ứng với tên đầy đủ của class thực tế. Nếu không có dòng này trong một tài nguyên imports nào trên runtime classpath, Boot sẽ không khám phá class qua cơ chế imports tiêu chuẩn. Dòng còn sai FQCN có thể gây lỗi đọc/tải class thay vì im lặng bỏ qua; không nên đánh đồng mọi tình huống sai metadata.

**Bằng chứng 3 — ứng dụng thật có bật auto-configuration không?** Thường `@SpringBootApplication` đã bật; một context dùng `@Configuration` tối giản hoặc test chỉ nạp một số cấu hình có thể không tự chạy cơ chế khám phá ứng viên. Kiểm tra setup khởi động thay vì chỉ nhìn JAR.

**Bằng chứng 4 — đúng classloader và phiên bản?** Trong môi trường multi-module, test slices, custom `ApplicationContext` hoặc một ứng dụng đã đóng gói, runtime classpath có thể khác classpath IDE. Thử build clean và quan sát chính artifact được chạy.

Không nên dùng riêng sự **vắng mặt của tên lớp trong condition report** làm chứng cứ tuyệt đối cho lỗi discovery: lớp cũng có thể đã bị loại bởi exclusion/filter, hoặc báo cáo bị giới hạn bởi môi trường/phiên bản. Kết luận phải dựa trên nhiều dấu hiệu, đặc biệt metadata và runtime classpath.

## 4. Nhận diện trường hợp “ứng viên có nhưng condition không khớp”

Giả sử Boot đã phát hiện:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureAutoConfiguration {
    // Các @Bean nếu điều kiện lớp phù hợp.
}
~~~

Đoạn này **chỉ minh họa annotation**, không phải chương trình độc lập. Nếu `demo.feature.enabled=false` hoặc khóa không tồn tại và `matchIfMissing` không được bật, điều kiện trên lớp không khớp. Tệp imports vẫn đúng, nhưng cấu hình không đăng ký bean mong đợi.

Một auto-configuration thực tế có thể chứa các điều kiện:

| Điều kiện | Cần kiểm tra | Kết quả nếu không khớp |
| --- | --- | --- |
| `@ConditionalOnClass` | Class/API bắt buộc có trên classpath hay không | Bỏ qua cấu hình hoặc bean cần thư viện đó. |
| `@ConditionalOnMissingClass` | Một class cụ thể có vắng hay không | Không dùng nhánh cấu hình dành cho trường hợp vắng class. |
| `@ConditionalOnProperty` | Giá trị property cuối cùng trong `Environment`, `havingValue`, `matchIfMissing` | Bỏ qua cấu hình/bean khi property không phù hợp. |
| `@ConditionalOnBean` | Bean tiền đề đã được xử lý và có mặt tại thời điểm xét không | Bỏ qua phần cấu hình phụ thuộc tiền đề. |
| `@ConditionalOnMissingBean` | Đã có bean phù hợp do ứng dụng hoặc cấu hình khác khai báo chưa | **Back off**: không đăng ký bean mặc định tương ứng. |
| `@ConditionalOnWebApplication` | Loại ứng dụng web phù hợp không | Bỏ qua phần chỉ dành cho môi trường web. |
| `@ConditionalOnResource` | Tài nguyên bắt buộc có không | Bỏ qua cấu hình cần tài nguyên đó. |

Điều kiện cấp **lớp** có thể không khớp trong khi điều kiện cấp `@Bean` chưa cần xét; hoặc lớp được chấp nhận nhưng một phương thức `@Bean` bên trong bị bỏ qua. Vì thế cần đọc **đúng dòng/đúng phương thức** của condition report, không chỉ nhìn tên class.

### Chú ý @ConditionalOnMissingBean

`@ConditionalOnMissingBean` là trường hợp dễ bị chẩn đoán sai. Nếu ứng dụng đã cung cấp bean phù hợp, Spring Boot cố ý **lùi bước** để tránh tạo thêm mặc định. Đây thường là hành vi đúng, không phải lỗi không khám phá được ứng viên.

Điều kiện bean nhìn vào những bean definitions đã được xử lý tại thời điểm đánh giá; không kiểm tra trước mọi bean sẽ có trong tương lai. Boot xử lý auto-configuration theo pha deferred để dành cơ hội cho bean do ứng dụng khai báo trước. Nếu bạn viết điều kiện dựa vào bean trong `@Configuration` tùy ý, không thể mặc định rằng thứ tự cũng giống auto-configuration.

### Chú ý thứ tự PropertySource

`@ConditionalOnProperty` hỏi giá trị từ `Environment`. Một giá trị ở `application.properties` có thể bị ghi đè bằng command-line, biến môi trường hoặc system property theo thứ tự ưu tiên. Khi thấy condition không khớp, hãy đọc giá trị **đã phân giải tại thời điểm condition được đánh giá**, không chỉ xem một file.

## 5. Exclusion/filter: trường hợp thứ ba cần tách biệt

Một ứng viên có thể được **công bố** trong imports file nhưng bị **loại trừ khỏi danh sách áp dụng** qua `@SpringBootApplication(exclude = ...)`, `excludeName` hoặc `spring.autoconfigure.exclude`.

Ví dụ:

~~~properties
spring.autoconfigure.exclude=com.example.feature.autoconfigure.FeatureAutoConfiguration
~~~

Đây chỉ là ví dụ property chứa tên class minh họa. Nếu class thực tế tồn tại và được đăng ký đúng, exclusion vẫn làm Boot không áp dụng nó.

Điểm khác với condition mismatch: exclusion là **quyết định bỏ lớp khỏi việc import auto-configuration**, còn condition mismatch là điều kiện trên cấu hình/bean được đánh giá không đạt. Một số bộ lọc tối ưu hóa có thể loại ứng viên sớm trước khi Spring phân tích lớp đầy đủ. Không nên ép mọi trường hợp “không vào context” thành một trong hai nhãn nếu bằng chứng cho thấy nó là exclusion, filter hoặc lỗi load class.

Trong báo cáo nên ghi cụ thể:

- `NOT_DISCOVERED`: thiếu metadata/classpath hoặc auto-configuration không được bật.
- `DISCOVERED_BUT_CONDITION_FALSE`: có metadata và biết chính xác điều kiện không khớp.
- `EXCLUDED_OR_FILTERED`: bị exclude hoặc loại trong bước lựa chọn ứng viên.
- `REGISTERED_BUT_CREATION_FAILED`: có bean definition nhưng tạo bean thất bại.
- `INSUFFICIENT_EVIDENCE`: chưa biết rõ nguyên nhân; cần bổ sung điều tra.

Những nhãn trên là **mẫu ghi chép khi chẩn đoán**, không phải status do Spring Boot tự in ra.

## 6. Thực hành Java 17+ với Spring Boot 3.5.0

Ta sẽ xây một dự án Maven nhỏ để tạo ra **cùng triệu chứng không có bean** từ hai nguyên nhân khác nhau:

1. Lớp được đăng ký trong imports file nhưng condition property không khớp.
2. Bỏ imports file trong bản sao dự án, khiến Boot không khám phá auto-configuration, dù class Java vẫn được đóng gói.

Ví dụ còn có trường hợp hợp lệ và back-off do người dùng cung cấp bean. Đây là **một ứng dụng chạy độc lập với Maven và Java 17+**, không cần web server, database hay module ngoài.

### 6.1. Cây thư mục

~~~text
candidate-diagnosis/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/GreetingService.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/GreetingAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` nằm trong `com.example.app`; lớp auto-configuration ở package ngang hàng `com.example.autoconfig`. Spring Boot component scan mặc định bắt đầu từ `com.example.app` nên sẽ không quét lớp auto-configuration; việc nó được đưa vào thực sự phụ thuộc imports metadata.

### 6.2. pom.xml

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
    <artifactId>candidate-diagnosis</artifactId>
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

### 6.3. GreetingService.java

Đặt tại `src/main/java/com/example/api/GreetingService.java`:

~~~java
package com.example.api;

public interface GreetingService {
    String greeting();
}
~~~

Chỉ có interface trên classpath không tạo bean. Chúng ta sẽ dùng một bean mặc định từ auto-configuration và một bean do ứng dụng cung cấp.

### 6.4. GreetingAutoConfiguration.java

Đặt tại `src/main/java/com/example/autoconfig/GreetingAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "AUTO";
    }
}
~~~

Điều kiện trên class kiểm tra `demo.feature.enabled=true`. Vì `matchIfMissing=false` là mặc định, property vắng cũng làm điều kiện không khớp. `@ConditionalOnMissingBean(GreetingService.class)` tại `@Bean` còn có thể làm bean mặc định lùi bước nếu ứng dụng đã cung cấp `GreetingService`.

### 6.5. AutoConfiguration.imports

Tạo đúng tệp:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung chính xác một dòng:

~~~text
com.example.autoconfig.GreetingAutoConfiguration
~~~

Cú pháp là **một FQCN mỗi dòng**; không thêm `.class`, `.java` hay key theo kiểu `spring.factories`.

### 6.6. DemoApplication.java

Đặt tại `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.GreetingService;
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
            prefix = "demo.override",
            name = "enabled",
            havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printResult(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("SERVICE="
                    + (service == null ? "ABSENT" : service.greeting()));
        };
    }
}
~~~

`ObjectProvider` giúp ứng dụng chạy bình thường ngay cả khi không có `GreetingService`, nhờ đó ta quan sát cùng stdout `SERVICE=ABSENT` của hai lỗi khác nhau. Ví dụ bảo đảm có tối đa một bean `GreetingService` trong các trường hợp trình bày; nếu tự thêm nhiều bean cùng kiểu mà không đánh dấu primary hoặc qualifier, `getIfAvailable()` có thể báo lỗi không duy nhất.

### 6.7. application.properties

Đặt tại `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Không thêm `demo.feature.enabled` hay `demo.override.enabled` vào file; dùng command-line để điều khiển từng tình huống.

### 6.8. Build và chạy các trường hợp

Cài JDK 17+ và Maven, đứng tại thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true
~~~

Dòng do ví dụ in ra:

~~~text
SERVICE=AUTO
~~~

Giải thích: imports file đăng ký ứng viên, điều kiện trên lớp khớp và chưa có `GreetingService` do người dùng tạo; bean mặc định được đăng ký.

**Trường hợp condition không khớp, metadata vẫn đúng:**

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=false
~~~

Dòng do chương trình in:

~~~text
SERVICE=ABSENT
~~~

Lớp `GreetingAutoConfiguration` vẫn là ứng viên được công bố nhưng `@ConditionalOnProperty` không khớp, nên bean mặc định không tồn tại. Với cấu hình mẫu, nếu không truyền `--demo.feature.enabled` thì property vắng và kết quả cũng `SERVICE=ABSENT`.

**Trường hợp ứng dụng có bean riêng nên auto-configuration lùi bước:**

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true --demo.override.enabled=true
~~~

Dòng do chương trình in:

~~~text
SERVICE=CUSTOM
~~~

Lớp auto-configuration có thể được chọn nhưng `@ConditionalOnMissingBean` khiến bean mặc định không được đăng ký. Đây là hành vi mong muốn, khác lỗi không khám phá ứng viên.

**Thử không có imports file:** Trong **một bản sao dự án dùng để thí nghiệm**, bỏ riêng tệp `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, giữ các class Java và file còn lại. Sau đó build sạch để tránh bản sao resource cũ còn lưu trong `target/classes`:

~~~bash
mvn -q clean package -DskipTests
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=true
~~~

Dòng do chương trình in:

~~~text
SERVICE=ABSENT
~~~

Lúc này property đã đúng nhưng không có tên `GreetingAutoConfiguration` trong metadata được nạp qua imports; lớp nằm ngoài component scan. Boot không tự tìm nó qua cơ chế chuẩn. Hãy khôi phục imports file sau thí nghiệm.

**Điểm cần nhớ:** hai lần chạy `SERVICE=ABSENT` có thể xuất phát từ hai nguyên nhân: metadata thiếu hoặc điều kiện property sai. Chỉ quan sát stdout không phân biệt được; phải kiểm tra **tài nguyên imports/classpath** và **condition report**.

### 6.9. Bảng so sánh kết quả

| Trạng thái runtime | Metadata imports có tên lớp? | `demo.feature.enabled` | Điều kiện và ứng viên | Stdout chương trình |
| --- | --- | --- | --- | --- |
| Bình thường | Có | `true` | Điều kiện khớp, không có bean tùy chỉnh | `SERVICE=AUTO` |
| Condition mismatch | Có | `false` | Ứng viên được công bố nhưng điều kiện lớp không khớp | `SERVICE=ABSENT` |
| App override | Có | `true` | `@ConditionalOnMissingBean` không khớp vì có bean ứng dụng | `SERVICE=CUSTOM` |
| Discovery failure trong bản sao | Không | `true` | Boot không nhận auto-configuration từ imports | `SERVICE=ABSENT` |

## 7. Dùng Condition Evaluation Report đúng cách

Spring Boot có **Condition Evaluation Report** để cho biết điều kiện auto-configuration nào khớp hoặc không khớp. Khi điều tra, hãy bật debug và bảo đảm mức log đủ cao để nhìn báo cáo:

~~~bash
java -jar target/candidate-diagnosis-1.0.0.jar \
  --demo.feature.enabled=false \
  --debug \
  --logging.level.root=INFO
~~~

Lệnh này phù hợp shell có ký tự nối dòng `\` như Bash. Trên Windows PowerShell, có thể viết cùng một lệnh trên **một dòng**:

~~~powershell
java -jar target/candidate-diagnosis-1.0.0.jar --demo.feature.enabled=false --debug --logging.level.root=INFO
~~~

Trong báo cáo điều kiện, tìm tên `GreetingAutoConfiguration` và lý do property `demo.feature.enabled` không khớp. Với bản build giữ imports file, có thể xuất hiện mục negative match tương ứng. Sau đó chạy `--demo.feature.enabled=true` để đối chiếu khi điều kiện được thỏa mãn.

Khi **bỏ imports file** rồi build sạch, `GreetingAutoConfiguration` không còn được công bố qua metadata. Việc không thấy nó trong danh sách positive/negative matches là dấu hiệu cần điều tra về discovery, nhưng **không phải bằng chứng duy nhất**: exclusions, filters, logging và hình thức khởi tạo context cũng ảnh hưởng thứ xuất hiện trong report.

Condition report nói về **kết quả điều kiện**; nó không thể thay thế kiểm tra **JAR chứa đúng metadata**.

### Bốn câu hỏi khi đọc report

1. **Tên lớp auto-configuration có xuất hiện không?** Nếu có, đọc đúng điều kiện và quyết định; nếu không, kiểm tra metadata/runtime và exclusions trước.
2. **Điều kiện cấp lớp hay cấp phương thức?** Một class positive chưa đảm bảo bean `@Bean` dương tính; xem cả `Class#beanMethod` khi có.
3. **Điều kiện dựa vào gì?** Classpath, property, web context, bean có sẵn hay tài nguyên?
4. **Đang chẩn đoán đúng context?** Test slice (`@WebMvcTest`, `@DataJpaTest`), app chính, management context hoặc test context tùy biến có thể có tập cấu hình khác nhau.

Với dự án có Actuator và quyền truy cập phù hợp, endpoint `/actuator/conditions` cũng có thể hỗ trợ xem điều kiện. Nó chỉ hiện diện khi dependency, cấu hình expose và bảo mật cho phép; không giả định endpoint công khai trong mọi ứng dụng.

## 8. Kiểm tra metadata ở artifact cuối

Sau khi build ví dụ có imports file, chạy:

~~~bash
jar tf target/candidate-diagnosis-1.0.0.jar
~~~

Trong Spring Boot executable JAR, tìm tài nguyên:

~~~text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Với JAR thư viện Maven không repackaging thành executable JAR, entry cần tìm thường là:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trong multi-module project, class có thể nằm ở module `feature-autoconfigure` nhưng ứng dụng chỉ thêm module `feature-starter`; hãy xác nhận starter thực sự kéo module auto-config vào runtime. Đừng chỉ nhìn source tree của module khác.

Để đối chiếu cả **nội dung** file, mở artifact bằng công cụ ZIP/JAR hoặc trích riêng tài nguyên ở một thư mục kiểm tra. Đừng nhầm việc thấy entry với việc tên FQCN trong file đúng. Một metadata entry có thể chứa một tên class cũ sau refactor.

Các thao tác chỉ kiểm tra file chưa cho biết điều kiện có khớp. Vì thế bước tiếp theo luôn là **đọc report và thuộc tính/môi trường thực tế**.

## 9. Quy trình chẩn đoán theo quyết định

Dùng trình tự sau khi bean mặc định không xuất hiện:

**Bước 1 — Xác định đúng bean và auto-configuration dự kiến.** Tìm class cấu hình thực sự cung cấp bean, phương thức `@Bean`, tên và type bean. Không suy ra từ tên starter rằng chắc chắn có bean.

**Bước 2 — Kiểm tra runtime dependency.** Xem `mvn dependency:tree` hoặc `./gradlew dependencies --configuration runtimeClasspath` (tên configuration phù hợp với dự án). Đảm bảo thư viện chứa class và metadata nằm trong ứng dụng đang chạy, không chỉ test classpath hoặc compile-only.

**Bước 3 — Kiểm tra imports resource.** Tìm tệp đúng tên trong JAR đúng phiên bản, đọc FQCN thực tế. Nếu không có metadata, ghi nhận lỗi discovery/packaging và sửa dependency hoặc resource.

**Bước 4 — Kiểm tra auto-configuration được bật và không bị exclude.** `@SpringBootApplication` thường bao gồm `@EnableAutoConfiguration`; nhưng ứng dụng có thể cố ý loại trừ cấu hình cụ thể. Ghi nhận sự khác biệt giữa “không công bố ứng viên” và “công bố nhưng bị exclude”.

**Bước 5 — Đọc Condition Evaluation Report.** Nếu condition không khớp, trích chính xác annotation và dữ kiện: thiếu class, property giá trị không đúng, bean có/không, môi trường web. Không chữa bằng thêm imports file nếu thực ra condition đã giải thích được vấn đề.

**Bước 6 — Đối chiếu các property sources và profiles.** Giá trị `application.properties` có thể bị override bởi profile-specific config, environment variable, JVM property hoặc command-line. Tìm giá trị cuối đã dùng để đánh giá, đặc biệt `havingValue` và `matchIfMissing`.

**Bước 7 — Kiểm tra bean definition và lỗi khởi tạo.** Nếu condition khớp nhưng bean vẫn thiếu, kiểm tra bean method, scope, bean name, cấu hình phụ thuộc và exception chain. Bean tạo thất bại là một giai đoạn khác; không nên gọi là discovery failure.

**Bước 8 — Thử tái hiện tối thiểu.** Dùng ứng dụng ở phần 6, thay đổi đúng một yếu tố giữa các lần chạy: imports resource, giá trị property hoặc bean ứng dụng. Cách so sánh này tạo bằng chứng nguyên nhân rõ hơn log đầy đủ của hệ thống lớn.

Có thể ghi ngắn kết quả điều tra:

~~~text
Expected bean: com.example.api.GreetingService
Auto-config class: com.example.autoconfig.GreetingAutoConfiguration
Artifact / classpath: candidate-diagnosis-1.0.0.jar
Imports resource: PRESENT | ABSENT | UNKNOWN
FQCN in resource: PRESENT | ABSENT | UNKNOWN
Excluded: YES | NO | UNKNOWN
Condition class/method: MATCH | NO_MATCH | NOT_EVALUATED | UNKNOWN
Bean definition: PRESENT | ABSENT | UNKNOWN
Root cause: discovery | exclude/filter | condition | creation | needs evidence
~~~

Các giá trị trên là mẫu ghi chép để tránh kết luận quá sớm; chúng **không** phải kết quả tự động của một công cụ Boot cụ thể.

## 10. Lỗi phổ biến và cách sửa đúng tầng

| Phát hiện | Suy luận phù hợp | Cách sửa |
| --- | --- | --- |
| `@AutoConfiguration` có trong code, imports file không có | Thiếu đăng ký ứng viên qua cơ chế chuẩn | Thêm resource đúng đường dẫn và FQCN, build/publish lại. |
| Imports file có trong thư viện nhưng không có trên runtime classpath ứng dụng | Lỗi dependency/packaging | Thêm dependency runtime đúng module, kiểm tra artifact được chạy. |
| Imports file hợp lệ nhưng app exclude class | Bị loại trừ có chủ đích hoặc nhầm cấu hình | Xem `exclude` / `spring.autoconfigure.exclude`, chỉ bỏ khi phù hợp. |
| Class trong report với `@ConditionalOnClass` không khớp | Đã tham gia đánh giá nhưng thiếu class cần thiết | Thêm dependency đúng hoặc chấp nhận bỏ qua nhánh tùy chọn. |
| Class trong report với `@ConditionalOnProperty` không khớp | Giá trị property không đáp ứng | Kiểm tra tên key, giá trị, profiles, precedence, `matchIfMissing`. |
| Method `@Bean` bị `@ConditionalOnMissingBean` bỏ qua | Bean phù hợp đã hiện diện | Nếu bean ứng dụng là chủ đích, giữ nguyên; nếu không, tìm bean cạnh tranh. |
| Report positive nhưng startup thất bại ở constructor | Đăng ký thành công nhưng tạo bean lỗi | Đọc exception chain và sửa dependency/initialization. |
| Không thấy class trong report | Chưa đủ bằng chứng kết luận | Kiểm tra imports, exclusions, filters, context và debug logging. |
| ApplicationContextRunner thử trực tiếp class và pass | Chỉ chứng minh cấu hình hoạt động khi đưa trực tiếp vào context | Thêm kiểm tra artifact/khám phá thực sự qua classpath. |

### Vì sao “thêm starter” có thể đánh lừa?

Starter thường là tập dependency thuận tiện. Thêm starter chỉ thay đổi **classpath**; auto-configuration còn cần metadata, lựa chọn ứng viên và các điều kiện. Một starter thiếu module auto-config hoặc đóng gói sai metadata sẽ dẫn tới vấn đề discovery; một starter đúng nhưng thiếu service/configuration property lại có thể dẫn tới condition mismatch. Chẩn đoán phải bắt đầu từ **vị trí bean được kỳ vọng tạo ra**, không bắt đầu bằng giả định mọi starter luôn tạo mọi bean.

### Vì sao không nên sửa bằng @ComponentScan quá rộng?

Nếu phát hiện auto-configuration không được đăng ký, việc quét rộng sang package của thư viện có thể làm class được coi là một cấu hình Spring thông thường và che đi lỗi metadata; đồng thời có thể kích hoạt ngoài ý muốn nhiều component khác. Cách sửa phù hợp là **đưa class vào đúng imports file** và bảo đảm resource nằm trên runtime classpath.

### Vì sao không nên sửa bằng cách bỏ hết @Conditional?

Điều kiện tồn tại để tránh cấu hình tích hợp khi class hoặc bean tiền đề không có, và để dành ưu tiên cho cấu hình ứng dụng. Xóa điều kiện có thể tạo lỗi khởi động hoặc hai bean cạnh tranh. Hãy xác minh mục đích điều kiện trước khi thay đổi.

## 11. Câu hỏi tự kiểm tra

1. **Ứng dụng không có bean X có chứng minh Spring Boot không tìm được auto-configuration X không?** Không; điều kiện cấp lớp hoặc `@Bean` có thể không khớp, bị exclude hoặc tạo bean thất bại.
2. **Lớp có `@AutoConfiguration` nhưng không nằm trong imports file thì sao?** Boot không tự khám phá nó qua metadata auto-configuration chuẩn chỉ vì có annotation.
3. **Một class xuất hiện với negative match trong condition report nói lên điều gì?** Ít nhất một điều kiện không khớp tại cấu hình/bean được báo cáo; cần đọc chi tiết lý do.
4. **Một class không có tên trong report có chứng minh metadata bị thiếu không?** Không; cần kiểm tra classpath, imports file, exclusions, filters và dạng context.
5. **`@ConditionalOnMissingBean` không khớp có luôn là bug không?** Không; có thể chính là hành vi back-off khi ứng dụng cung cấp bean.
6. **Classpath có chứa class có đủ để auto-configuration được đăng ký không?** Không; còn cần metadata imports hoặc một cơ chế import phù hợp.
7. **Nếu metadata đúng nhưng `demo.feature.enabled=false` thì bean của demo có xuất hiện không?** Không; điều kiện lớp từ chối cấu hình, chương trình in `SERVICE=ABSENT`.
8. **Nếu metadata bị bỏ trong bản sao nhưng property là `true` thì sao?** Class không được khám phá qua imports và `GreetingService` mặc định vắng, cũng in `SERVICE=ABSENT`.
9. **Phân biệt lỗi tạo bean với lỗi discovery thế nào?** Điều tra bean definition và exception chain; nếu class/definition đã tham gia và lỗi ở constructor/dependency, đó là bước sau discovery.
10. **Trong multi-module project nên kiểm tra ở đâu?** Ở JAR và runtime classpath của chính ứng dụng đang chạy, không chỉ trong mã nguồn của module có annotation.

## Tài liệu tham khảo chính thức

- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — `ConditionEvaluationReport` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Framework — `DeferredImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html

**Điểm cốt lõi:** thiếu bean chỉ là **triệu chứng**. Muốn tìm đúng nguyên nhân, phải chứng minh Spring Boot có tìm được ứng viên từ metadata hay không, xem lớp có bị loại trừ không, đọc điều kiện thực tế và kiểm tra bean definition/khởi tạo. Khi xác định đúng giai đoạn, giải pháp thường rõ ràng: sửa resource/classpath nếu không khám phá được; sửa điều kiện hoặc cấu hình nếu candidate đã được tìm thấy nhưng không khớp.