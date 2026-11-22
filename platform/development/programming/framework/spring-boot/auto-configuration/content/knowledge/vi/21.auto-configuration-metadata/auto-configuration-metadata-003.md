# Metadata hỗ trợ lọc ứng viên sớm và tối ưu chi phí xử lý cấu hình

## 1. Metadata giải quyết vấn đề gì?

Một ứng dụng Spring Boot có thể kéo theo hàng chục hoặc hàng trăm auto-configuration từ Spring Boot, Spring projects và starter bên thứ ba. Spring cần đọc danh sách ứng viên, xác định cấu hình nào phù hợp với classpath và môi trường hiện tại, rồi mới phân tích cấu hình được chọn để đăng ký bean definitions.

Nếu mọi ứng viên đều phải được đọc và phân tích đầy đủ trước khi biết chúng không phù hợp, startup sẽ tốn thêm công việc. Ví dụ, ứng dụng không dùng thư viện tìm kiếm nhưng auto-configuration tích hợp tìm kiếm vẫn nằm trong danh sách ứng viên của một starter. Nếu có thể xác định sớm class thư viện tìm kiếm không tồn tại, Spring Boot có thể loại cấu hình đó trước khi đọc bytecode của lớp auto-configuration.

Spring Boot hỗ trợ cơ chế này bằng **auto-configuration metadata**:

- Annotation processor thu thập một số điều kiện tĩnh từ mã nguồn auto-configuration trong lúc biên dịch.
- Processor ghi metadata vào file `META-INF/spring-autoconfigure-metadata.properties` trong artifact.
- Khi khởi động, các `AutoConfigurationImportFilter` có thể dùng metadata để loại ứng viên không khớp trước khi bytecode của cấu hình được đọc.
- Các ứng viên còn lại tiếp tục qua quy trình phân tích cấu hình và đánh giá condition thông thường.

Mục tiêu là giảm lượng cấu hình phải xử lý trong startup. Metadata là **tối ưu hóa đường đi**, không phải cơ chế thay thế `@Conditional` và cũng không phải nơi đăng ký bean.

Bài học dùng **Spring Boot 3.3.13 và Java 17+**, tập trung vào việc tạo metadata, cách Spring sử dụng metadata, cách kiểm tra JAR và cách test một auto-configuration có điều kiện.

## 2. Phân biệt ba loại metadata dễ nhầm

Spring Boot có nhiều file chứa chữ “metadata”, nhưng chúng có mục đích khác nhau:

| File | Vai trò | Ai sử dụng? |
|---|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Liệt kê tên các auto-configuration candidate trong JAR | `AutoConfigurationImportSelector` tìm ứng viên |
| `META-INF/spring-autoconfigure-metadata.properties` | Lưu một số điều kiện/order metadata để lọc ứng viên sớm | Auto-configuration import filters và sorter |
| `META-INF/spring-configuration-metadata.json` | Mô tả property của `@ConfigurationProperties`, kiểu dữ liệu, default value, description và hints | IDE, tooling và developer khi viết application config |

Ba file không thể thay thế nhau:

- Thiếu `AutoConfiguration.imports`: Spring Boot không có danh sách để tự khám phá auto-configuration theo cơ chế imports.
- Thiếu `spring-autoconfigure-metadata.properties`: cấu hình vẫn có thể được đánh giá bằng condition thông thường, nhưng mất cơ hội lọc sớm dựa trên metadata được sinh.
- Thiếu `spring-configuration-metadata.json`: ứng dụng vẫn bind property nếu code đúng, nhưng IDE có thể thiếu completion và tài liệu gợi ý.

**Điểm quan trọng:** `spring-boot-autoconfigure-processor` tạo auto-configuration metadata; `spring-boot-configuration-processor` tạo configuration property metadata. Tên gần giống nhau nhưng artifact và nhiệm vụ khác nhau.

## 3. Quy trình lọc ứng viên diễn ra khi nào?

Ở mức khái niệm, quy trình Spring Boot có thể biểu diễn như sau:

~~~text
@EnableAutoConfiguration
        |
        v
Đọc các file AutoConfiguration.imports trên runtime classpath
        |
        v
Tập hợp candidate class names và áp dụng exclusions
        |
        v
Đọc spring-autoconfigure-metadata.properties
        |
        v
AutoConfigurationImportFilter kiểm tra metadata
        |
        +---- Condition tĩnh không thể khớp
        |          |
        |          v
        |     Loại candidate sớm
        |
        +---- Candidate còn phù hợp
                   |
                   v
        Sắp thứ tự và phân tích configuration
                   |
                   v
        Đánh giá các condition còn lại
                   |
                   v
        Đăng ký bean definitions
                   |
                   v
        Khởi tạo bean theo dependency và lifecycle
~~~

`AutoConfigurationImportFilter` được thiết kế để loại nhanh các auto-configuration trước khi bytecode của chúng được đọc. Phương thức `match(...)` nhận danh sách tên class và `AutoConfigurationMetadata`, rồi trả về một mảng boolean tương ứng với các candidate; phần tử `false` sẽ không được import.

Có thể hiểu metadata như một **bản tóm tắt điều kiện có thể kiểm tra sớm**. Spring không cần phân tích toàn bộ class chỉ để biết một điều kiện tĩnh như class bắt buộc không có trên classpath.

Quy trình thực tế có nhiều bước nội bộ hơn sơ đồ. Metadata không tự quyết định mọi condition và cũng không trực tiếp tạo bean. Sau khi lọc, các configuration còn lại vẫn phải đi qua quá trình xử lý cấu hình chuẩn.

## 4. Metadata được tạo ở thời điểm biên dịch

### 4.1. Annotation processor của Spring Boot

Artifact cần dùng trong module chứa auto-configuration là:

`org.springframework.boot:spring-boot-autoconfigure-processor`

Đây là Java annotation processor. Khi compiler xử lý các lớp auto-configuration, processor thu thập những annotation/thuộc tính mà nó hỗ trợ và tạo file:

`META-INF/spring-autoconfigure-metadata.properties`

Nên khai báo processor trong **module autoconfigure**, nơi các lớp `@AutoConfiguration` được biên dịch. Không cần đưa processor vào runtime classpath của ứng dụng tiêu thụ.

Processor chỉ thu thập được metadata từ các annotation và thông tin mà nó hiểu. Không được giả định mọi `@Conditional`, mọi property condition hoặc mọi `@Bean` method đều có thể được quyết định hoàn toàn ở bước lọc sớm.

### 4.2. Cấu hình Maven

Với Spring Boot 3.3, tài liệu chính thức hướng dẫn dùng Maven Compiler Plugin phiên bản 3.12.0 trở lên và khai báo processor trong `annotationProcessorPaths`.

Ví dụ phần `build` trong `pom.xml` của module auto-configuration, giả định project dùng Spring Boot 3.3.13 và Java 17:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Module cũng cần dependency compile-time cho annotation/API mà nó dùng, thường là `spring-boot-autoconfigure`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>
~~~

Khi dùng Spring Boot parent/BOM, version của dependency runtime thường được quản lý tập trung. Trong `annotationProcessorPaths`, khai báo version processor tương ứng với version Boot của project để tránh sinh metadata bằng một phiên bản khác.

Nếu project dùng Lombok hoặc annotation processor khác, thêm chúng vào cùng danh sách `annotationProcessorPaths` và kiểm tra thứ tự processor theo hướng dẫn của từng công cụ. Đừng vô tình loại processor hiện có khi thay cấu hình compiler.

### 4.3. Cấu hình Gradle

Với Gradle, đặt processor trong configuration `annotationProcessor`:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Ví dụ giả định Spring Boot BOM hoặc dependency management plugin đã quản lý version. Nếu project chưa dùng BOM, cần khai báo version 3.3.13 đồng nhất cho các artifact Spring Boot.

Không khai báo processor trong `implementation` chỉ để compiler tìm thấy nó. `annotationProcessor` thể hiện đúng vai trò compile-time và tránh đưa processor vào dependency runtime không cần thiết.

### 4.4. Processor không phải dependency runtime của consumer

Consumer cần các class runtime mà starter cung cấp, ví dụ auto-configuration API, service API và thư viện tích hợp thực tế. Consumer không cần chạy annotation processor của starter mỗi lần khởi động.

Đường đi là:

1. Module auto-configuration biên dịch và sinh metadata.
2. Metadata được đóng gói vào JAR của module.
3. Starter/consumer đưa JAR đó lên runtime classpath.
4. Spring Boot đọc metadata khi xử lý auto-configuration candidates.

Nếu processor không chạy, các `@Conditional` vẫn có thể được đánh giá bằng cơ chế chuẩn. Vấn đề là ứng dụng không có bản metadata được tạo để hỗ trợ tối ưu lọc sớm.

## 5. Ví dụ auto-configuration có dependency tùy chọn

Giả sử thư viện Acme Search chỉ hoạt động khi SDK bên ngoài có class:

`com.vendor.search.SearchClient`

Starter muốn cung cấp `SearchFacade` mặc định nếu SDK có mặt và ứng dụng chưa tự cung cấp facade.

### 5.1. API của starter

Tệp `src/main/java/com/acme/search/SearchFacade.java`:

~~~java
package com.acme.search;

public interface SearchFacade {

    String provider();
}
~~~

### 5.2. Auto-configuration

Tệp `src/main/java/com/acme/search/autoconfigure/SearchAutoConfiguration.java`:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchFacade;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchFacade.class)
    DefaultSearchFacade searchFacade() {
        return new DefaultSearchFacade();
    }

    static class DefaultSearchFacade implements SearchFacade {

        @Override
        public String provider() {
            return "starter-default";
        }
    }
}
~~~

Điều kiện class-level `@ConditionalOnClass` mô tả rằng auto-configuration chỉ phù hợp khi SDK có trên classpath. Việc dùng `name` giúp cấu hình tham chiếu class tùy chọn bằng tên, không buộc chữ ký method của auto-configuration phải trực tiếp dùng type có thể vắng mặt.

`@ConditionalOnMissingBean` trên bean method thể hiện hợp đồng back-off: nếu ứng dụng đã cung cấp `SearchFacade`, bean mặc định không được đăng ký. Điều kiện này vẫn cần được đánh giá theo trạng thái bean definitions trong context; không nên xem nó là một điều kiện tĩnh có thể luôn giải quyết chỉ từ metadata compile-time.

### 5.3. Đăng ký candidate

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

~~~text
com.acme.search.autoconfigure.SearchAutoConfiguration
~~~

File này đưa tên auto-configuration vào danh sách candidate. Processor metadata không thay thế file imports.

## 6. Kiểm tra metadata trong artifact đã build

Sau khi build module auto-configuration:

~~~bash
mvn clean package
~~~

Kiểm tra JAR có các file cần thiết:

~~~bash
jar tf target/search-autoconfigure-1.0.0.jar
~~~

Trong danh sách, tìm:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

File đầu tiên phải chứa tên lớp `SearchAutoConfiguration`. File thứ hai được processor tạo từ metadata điều kiện/order mà nó nhận diện được. Nội dung chính xác phụ thuộc các annotation có trong module và phiên bản processor.

Trên PowerShell có thể lọc danh sách:

~~~powershell
jar tf target/search-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports|spring-autoconfigure-metadata.properties"
~~~

Nếu muốn đọc nội dung metadata được đóng gói, trích xuất đúng entry từ JAR:

~~~powershell
jar xf target/search-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content META-INF/spring-autoconfigure-metadata.properties
~~~

Đây là file generated output. Không nên sửa file này bằng tay để điều khiển runtime. Hãy sửa annotation/processor configuration trong source rồi build lại artifact.

### 6.1. Nếu file metadata không xuất hiện

Kiểm tra theo thứ tự:

1. `spring-boot-autoconfigure-processor` đã nằm trong `annotationProcessorPaths` hoặc Gradle `annotationProcessor` chưa?
2. Processor có cùng version với Spring Boot đang dùng không?
3. Compiler có vô tình chạy với `-proc:none` hoặc cấu hình tắt annotation processing không?
4. Auto-configuration class có annotation/condition mà processor hỗ trợ không?
5. Bạn đang kiểm tra JAR của đúng module và đúng lần build không?
6. Resource có bị đóng gói sai hoặc bị loại bởi build plugin không?

Một project có thể không sinh file metadata hữu ích nếu không có condition nào mà processor nhận diện được. Việc file không xuất hiện không tự chứng minh auto-configuration imports bị hỏng.

## 7. Kiểm thử hành vi khi class tùy chọn có hoặc không có

Metadata là tối ưu hóa nội bộ. Kiểm thử ứng dụng vẫn cần xác nhận hành vi đúng khi class có mặt, class vắng mặt và khi người dùng thay bean mặc định.

### 7.1. Tạo class marker trong test

Trong project test, tạo class giả lập SDK:

Tệp `src/test/java/com/vendor/search/SearchClient.java`:

~~~java
package com.vendor.search;

public final class SearchClient {
}
~~~

Class này chỉ là marker test để mô phỏng SDK có trên test classpath. Trong ứng dụng thật, class sẽ đến từ dependency SDK bên ngoài.

### 7.2. Integration test đi qua auto-configuration imports

Tệp `src/test/java/com/acme/search/autoconfigure/SearchAutoConfigurationTests.java`:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchFacade;
import com.vendor.search.SearchClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestApplication.class);

    @Test
    void createsDefaultWhenOptionalSdkIsPresent() {
        this.runner.run(context -> {
            assertThat(context).hasSingleBean(SearchFacade.class);
            assertThat(context.getBean(SearchFacade.class).provider())
                    .isEqualTo("starter-default");
        });
    }

    @Test
    void skipsAutoConfigurationWhenOptionalSdkIsMissing() {
        this.runner
                .withClassLoader(new FilteredClassLoader(SearchClient.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean(SearchFacade.class));
    }

    @Test
    void userFacadeMakesDefaultBackOff() {
        this.runner
                .withUserConfiguration(UserSearchConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(SearchFacade.class);
                    assertThat(context.getBean(SearchFacade.class).provider())
                            .isEqualTo("user");
                });
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSearchConfiguration {

        @Bean
        SearchFacade customSearchFacade() {
            return () -> "user";
        }
    }
}
~~~

Test application dùng `@EnableAutoConfiguration`, không dùng `AutoConfigurations.of(SearchAutoConfiguration.class)`. Nhờ đó Spring Boot đi qua cơ chế khám phá candidate từ file `AutoConfiguration.imports` của JAR/test resources.

`FilteredClassLoader` mô phỏng tình huống SDK không có trên runtime classpath. Khi đó condition class không khớp và `SearchFacade` mặc định không được đăng ký. Test user bean xác nhận auto-configuration nhường quyền cho cấu hình ứng dụng.

### 7.3. Chạy test

Với Maven:

~~~bash
mvn test
~~~

Kết quả mong đợi: ba test PASS.

| Test | SDK class | User bean | Kết quả |
|---|---|---|---|
| `createsDefaultWhenOptionalSdkIsPresent` | Có | Không | Có `SearchFacade` mặc định |
| `skipsAutoConfigurationWhenOptionalSdkIsMissing` | Không | Không | Không có `SearchFacade` |
| `userFacadeMakesDefaultBackOff` | Có | Có | Chỉ dùng facade của ứng dụng |

Các test xác nhận auto-configuration discovery và condition behavior. Chúng không đo thời gian startup và cũng không tự chứng minh processor đã tạo metadata. Để xác nhận phần metadata, cần kiểm tra artifact như phần trước.

## 8. Metadata giúp tối ưu chi phí ở đâu?

Giả sử runtime classpath có 100 candidate auto-configuration, trong đó 30 cấu hình phụ thuộc thư viện không có mặt. Nếu các điều kiện tĩnh tương ứng đã được ghi trong metadata, Spring có thể loại một số candidate ngay ở giai đoạn filter, trước khi đọc bytecode từng cấu hình.

Lợi ích đến từ việc giảm công việc cần làm:

- Ít auto-configuration class phải được đọc/parse hơn.
- Ít cấu hình không liên quan đi sâu vào quá trình xử lý configuration.
- Ít metadata/class loading và condition processing cho các candidate đã chắc chắn không phù hợp.
- Startup có thể giảm chi phí, nhất là ứng dụng có nhiều starter và nhiều auto-configuration tùy chọn.

Không nên đưa ra con số phần trăm cải thiện chung. Mức tiết kiệm phụ thuộc số candidate, số condition có thể lọc sớm, classloader, kích thước dependency graph, môi trường chạy và các chi phí startup khác.

Metadata cũng không giúp giảm trực tiếp thời gian thực thi request, tốc độ truy vấn database hoặc chi phí khởi tạo một bean đã được chọn. Nó tập trung vào giai đoạn lựa chọn và xử lý auto-configuration khi context khởi động.

## 9. Giới hạn: metadata không đánh giá thay mọi condition

Metadata là bản ghi một phần thông tin có thể dùng sớm. Nhiều condition vẫn cần context, Environment hoặc bean definitions hiện tại:

- `@ConditionalOnMissingBean` cần biết bean phù hợp đã được đăng ký hay chưa.
- `@ConditionalOnBean` phụ thuộc trạng thái BeanFactory và thứ tự definitions đã được xử lý.
- `@ConditionalOnProperty` cần giá trị hiệu lực trong Environment.
- `@ConditionalOnResource` cần kiểm tra resource theo resource loader.
- `@ConditionalOnExpression` cần đánh giá SpEL; đặc biệt không tham chiếu bean trong expression vì có thể làm bean khởi tạo quá sớm.

Một số loại condition có thể được processor ghi metadata để filter sớm; các condition khác được đánh giá trong giai đoạn xử lý configuration thông thường. Không được giả định mọi annotation `@Conditional` đều được đưa vào metadata hoặc một candidate bị metadata giữ lại chắc chắn sẽ tạo bean.

### 9.1. Phân biệt lọc sớm với kết quả condition cuối

Có ba tình huống khác nhau:

| Tình huống | Ý nghĩa |
|---|---|
| Candidate bị metadata filter loại | Spring không import auto-configuration đó trong lần xử lý này |
| Candidate vượt qua filter nhưng condition thông thường không khớp | Cấu hình/bean vẫn bị loại ở giai đoạn đánh giá condition |
| Bean definition được đăng ký nhưng instance khởi tạo lỗi | Lỗi nằm ở dependency, constructor, factory method, binding hoặc lifecycle |

Condition Evaluation Report hữu ích để giải thích condition match/no-match. Nhưng chỉ nhìn report không đủ để kết luận metadata đã tạo ra mức tiết kiệm thời gian cụ thể.

### 9.2. Metadata không thay thế thiết kế condition đúng

Hãy viết auto-configuration với các condition thể hiện đúng hợp đồng:

- Dùng `@ConditionalOnClass` để cô lập tích hợp với dependency tùy chọn.
- Dùng `@ConditionalOnMissingBean` cho bean mặc định mà ứng dụng có quyền thay thế.
- Dùng `@ConditionalOnProperty` khi tính năng phụ thuộc property cấu hình.
- Tách nested configuration khi cần bảo vệ chữ ký method khỏi class tùy chọn không có trên classpath.
- Cung cấp return type cụ thể cho `@Bean` method để bean condition có đủ type metadata.

Processor chỉ giúp Boot kiểm tra sớm phần có thể kiểm tra; nó không sửa được một auto-configuration có điều kiện sai hoặc dependency được khai báo thiếu.

## 10. Tách auto-configuration metadata khỏi configuration property metadata

Một lỗi đặt tên phổ biến là nhầm hai annotation processor:

### `spring-boot-autoconfigure-processor`

- Thu thập một số condition/order metadata của auto-configuration.
- Tạo `META-INF/spring-autoconfigure-metadata.properties`.
- Hỗ trợ cơ chế lọc candidate sớm trong quá trình import auto-configuration.
- Được khai báo trong Maven `annotationProcessorPaths` hoặc Gradle `annotationProcessor`.

### `spring-boot-configuration-processor`

- Đọc các class/field/method được đánh dấu `@ConfigurationProperties`.
- Tạo `META-INF/spring-configuration-metadata.json`.
- Cung cấp mô tả property, kiểu dữ liệu, default value và gợi ý cho IDE.
- Giúp developer viết `application.yml`/`application.properties` thuận tiện hơn.

Một starter có thể cần **cả hai**: một processor để tối ưu auto-configuration filtering, một processor để cung cấp property hints cho IDE. Chúng tạo hai file khác nhau và phục vụ hai giai đoạn khác nhau.

## 11. Đo và đánh giá hiệu quả một cách đáng tin cậy

Để biết metadata có đáng giá trong project cụ thể:

1. Build artifact với `spring-boot-autoconfigure-processor` được bật.
2. Kiểm tra JAR có `META-INF/spring-autoconfigure-metadata.properties`.
3. Xác nhận các condition quan trọng của auto-configuration đã được processor ghi nhận.
4. Chạy cùng một ứng dụng với cùng dependency graph, cùng JDK, cùng cấu hình và cùng môi trường.
5. Đo nhiều lần startup process mới, bỏ các lần warm-up nếu có và so sánh median thay vì chọn một lần nhanh nhất.
6. Nếu cần phân tích sâu, dùng Java Flight Recorder hoặc công cụ startup profiling để xem class loading, configuration parsing và các chi phí khác.
7. Kiểm tra kết quả condition và bean cuối cùng không đổi giữa các lần build.

Không so sánh một lần chạy trên máy nóng với một lần chạy trên máy lạnh, hoặc thay đổi đồng thời dependency/property rồi quy toàn bộ chênh lệch cho metadata.

Với ứng dụng nhỏ chỉ có vài auto-configuration, chênh lệch có thể rất nhỏ. Với starter ecosystem lớn, nhiều optional integration và nhiều candidate không phù hợp, lọc sớm có thể giảm đáng kể công việc phân tích cấu hình.

## 12. Lỗi thường gặp

- **Nhầm `AutoConfiguration.imports` với `spring-autoconfigure-metadata.properties`:** một file liệt kê candidate; file còn lại hỗ trợ filter các candidate đó.
- **Dùng nhầm `spring-boot-configuration-processor`:** processor này sinh property metadata cho IDE, không thay thế auto-configuration processor.
- **Khai báo processor trong runtime `implementation`:** dùng annotation processor configuration riêng để giữ đúng scope compile-time.
- **Chỉ build source nhưng không kiểm tra JAR:** file generated có thể không nằm trong artifact cuối cùng do cấu hình compiler/resource/package.
- **Tự viết metadata properties bằng tay:** format và key là chi tiết generated; sửa annotation/processor setup rồi build lại.
- **Nghĩ mọi condition đều được lọc sớm:** chỉ một phần metadata được processor ghi nhận; các condition cần Environment/BeanFactory vẫn phải chạy ở giai đoạn phù hợp.
- **Nghĩ metadata quyết định bean cuối cùng:** metadata chỉ hỗ trợ loại candidate; bean conditions và bean registration vẫn có quy trình riêng.
- **Dùng test `AutoConfigurations.of(...)` rồi kết luận đã kiểm tra imports metadata:** cách test đó hữu ích cho logic condition, nhưng không thay thế integration test đi qua `@EnableAutoConfiguration` và imports resource.
- **Không đồng bộ version processor với Boot:** metadata sinh bởi version khác có thể gây khó chẩn đoán; giữ cùng version.
- **Tắt annotation processing:** compiler option như `-proc:none` khiến processor không chạy.
- **Bỏ processor khi module có nhiều auto-configuration tùy chọn:** chức năng vẫn có thể đúng, nhưng mất cơ hội lọc sớm.
- **Đưa dependency tùy chọn vào runtime không chủ đích:** classpath condition luôn thấy class nếu dependency thực tế được đóng gói; kiểm tra dependency scopes và starter composition.
- **Đo startup bằng một lần chạy:** nhiễu từ JIT, filesystem cache, process scheduling và môi trường có thể lớn hơn chênh lệch metadata.

## 13. Quy trình kiểm tra một starter trong dự án thật

1. Xác định module nào chứa `@AutoConfiguration`.
2. Kiểm tra module đó khai báo `spring-boot-autoconfigure-processor` đúng compile-time configuration.
3. Kiểm tra `AutoConfiguration.imports` liệt kê đúng class candidate.
4. Build sạch artifact.
5. Dùng `jar tf` xác nhận cả imports resource và `spring-autoconfigure-metadata.properties`.
6. Dùng `ApplicationContextRunner` hoặc integration test để kiểm tra classpath present/missing và user bean back-off.
7. Dùng `FilteredClassLoader` mô phỏng dependency tùy chọn vắng mặt.
8. Dùng condition report khi cần giải thích kết quả cuối.
9. Nếu quan tâm performance, đo startup nhiều lần với môi trường và dependency graph được kiểm soát.
10. Ghi rõ kết luận nào là bằng chứng về correctness, kết luận nào là bằng chứng về metadata generation và kết luận nào là số đo performance.

Ba bằng chứng cuối cùng phải tách bạch: **test behavior** chứng minh condition hoạt động; **JAR inspection** chứng minh metadata được đóng gói; **startup measurement** mới cho biết mức cải thiện thực tế.

## 14. Câu hỏi tự kiểm tra

1. `AutoConfiguration.imports` và `spring-autoconfigure-metadata.properties` khác nhau thế nào? **Imports liệt kê candidate; metadata hỗ trợ lọc sớm candidate không phù hợp.**
2. Artifact nào tạo `spring-autoconfigure-metadata.properties`? **`spring-boot-autoconfigure-processor`.**
3. Processor nên được khai báo ở đâu? **Trong module chứa auto-configuration, qua Maven `annotationProcessorPaths` hoặc Gradle `annotationProcessor`.**
4. Metadata có thay thế `@ConditionalOnClass` không? **Không.** Annotation thể hiện điều kiện; metadata là bản ghi compile-time để hỗ trợ filter sớm.
5. Nếu metadata file không có, auto-configuration có chắc chắn không hoạt động không? **Không.** Condition thông thường vẫn có thể được đánh giá; cơ hội lọc sớm bị mất.
6. `@ConditionalOnMissingBean` có phải lúc nào cũng được quyết định chỉ từ metadata compile-time không? **Không.** Nó phụ thuộc bean definitions trong context.
7. `spring-boot-configuration-processor` tạo file nào? **`META-INF/spring-configuration-metadata.json`**, dùng cho property hints/tooling.
8. `AutoConfigurationImportFilter` nhận dữ liệu gì? **Danh sách auto-configuration class names và `AutoConfigurationMetadata`; trả về kết quả match để xác định candidate nào được import.**
9. `FilteredClassLoader` kiểm tra điều gì trong bài? **Mô phỏng optional SDK không có trên classpath và xác nhận auto-configuration không tạo bean.**
10. Test PASS có chứng minh startup nhanh hơn bao nhiêu không? **Không.** Test chứng minh correctness; phải đo startup có kiểm soát để đánh giá performance.
11. Có nên sửa trực tiếp `spring-autoconfigure-metadata.properties` trong JAR? **Không.** File là generated output; sửa source/processor config rồi build lại.
12. Tại sao nên tách class-level `@ConditionalOnClass` khỏi method signature phụ thuộc thư viện tùy chọn? **Để class tùy chọn không bị JVM nạp trước khi condition có cơ hội bảo vệ cấu hình.**

## 15. Tài liệu tham khảo chính thức (Spring Boot 3.3.13)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): annotation processor, metadata file, cách cấu hình Maven/Gradle và auto-configuration lifecycle.
- [AutoConfigurationImportFilter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html): filter có thể loại auto-configuration trước khi bytecode được đọc.
- [AutoConfigurationImportSelector API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): lựa chọn và lọc các auto-configuration candidates.
- [AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): khai báo lớp auto-configuration.
- [Condition Annotations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/package-summary.html): các condition dùng để quyết định cấu hình có phù hợp hay không.
- [Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html): property metadata dùng cho IDE và tooling.
