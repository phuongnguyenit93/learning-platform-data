# @ConditionalOnWarDeployment và @ConditionalOnNotWarDeployment trong Spring Boot

## Mục tiêu học tập

Khi xây dựng **auto-configuration**, cùng một ứng dụng Spring Boot có thể được chạy theo hai cách rất khác nhau: triển khai WAR vào **servlet container bên ngoài** (ví dụ một Tomcat do môi trường vận hành quản lý), hoặc **tự khởi động embedded server** từ `java -jar`. Hai annotation `@ConditionalOnWarDeployment` và `@ConditionalOnNotWarDeployment` cho phép chọn phần cấu hình phù hợp với cách ứng dụng **thực sự đang khởi động**.

Sau bài học, bạn có thể:

- Giải thích điều kiện nào khớp trong traditional WAR deployment, trong embedded-server deployment và trong non-web application.
- Phân biệt **định dạng tệp JAR/WAR** với **mô hình triển khai**; đặc biệt hiểu trường hợp một executable WAR chạy bằng `java -jar`.
- Đặt annotation đúng ở class cấu hình hoặc trên phương thức `@Bean`, đồng thời không nhầm với `@ConditionalOnWebApplication`.
- Viết một phép kiểm tra nhỏ cho cả hai nhánh và đọc Condition Evaluation Report khi kết quả thực tế khác dự đoán.

## 1. Bối cảnh: cùng là ứng dụng web nhưng nơi sở hữu servlet container khác nhau

### Traditional WAR deployment

Ứng dụng được đóng gói thành WAR để **triển khai vào servlet container độc lập**, ví dụ `webapps/myapp.war` của Tomcat ngoài ứng dụng. Container tạo và cung cấp `ServletContext`; cơ chế khởi động dành cho WAR thường đi qua lớp kế thừa `SpringBootServletInitializer`.

Ở mô hình này, ứng dụng **không tự sở hữu quá trình tạo và khởi động** embedded servlet server. Các thiết lập thuộc phần khởi động container cần được phối hợp với hệ thống bên ngoài, thay vì giả định Spring Boot sẽ tạo một server mới.

### Embedded-server deployment

Ứng dụng tự khởi động server bằng luồng `SpringApplication.run(...)`. Cách chạy phổ biến nhất là executable JAR chứa embedded Tomcat/Jetty/Undertow; ngoài ra **executable WAR** cũng có thể chạy với `java -jar app.war`, dùng embedded server bên trong.

Vì vậy, câu hỏi quan trọng của hai annotation **không phải** “artifact có đuôi `.war` hay `.jar`?”, mà là “Spring Boot đang được khởi động theo **traditional WAR deployment**, hay theo một cách khác?”.

## 2. Ý nghĩa chính xác của hai annotation

Cả hai annotation thuộc package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

Cú pháp sử dụng:

~~~java
@ConditionalOnWarDeployment
@ConditionalOnNotWarDeployment
~~~

Mỗi annotation là một điều kiện Spring Boot dựa trên `@Conditional`, có thể đặt trên **class cấu hình** hoặc **phương thức `@Bean`**. Cả hai không có tham số bắt buộc.

- **`@ConditionalOnWarDeployment`**: khớp khi ứng dụng được chạy theo cơ chế WAR truyền thống và được servlet container ngoài ứng dụng khởi tạo. Với ứng dụng chạy bằng embedded server, điều kiện này **không khớp**.
- **`@ConditionalOnNotWarDeployment`**: khớp khi **không** ở mô hình traditional WAR deployment. Với ứng dụng chạy embedded server, điều kiện này **khớp**. Nó còn có thể khớp với ứng dụng không phải web, vì điều kiện chỉ nói “không phải traditional WAR”.

Hai annotation mang ý nghĩa **đối nhau** theo cùng một phép xác định deployment. Việc dùng chúng trên hai `@Bean` hoặc hai nhóm cấu hình cho phép ứng dụng chọn đúng một nhánh theo môi trường.

### Bảng kết quả cần nhớ

| Tình huống khởi động | `@ConditionalOnWarDeployment` | `@ConditionalOnNotWarDeployment` |
| --- | --- | --- |
| WAR triển khai vào Tomcat/Jetty servlet container **bên ngoài** | **Khớp** | Không khớp |
| Executable JAR chạy `java -jar app.jar` với embedded Tomcat | Không khớp | **Khớp** |
| Executable WAR chạy `java -jar app.war` với embedded server | Không khớp | **Khớp** |
| Ứng dụng servlet dùng embedded Undertow/Jetty | Không khớp | **Khớp** |
| Ứng dụng CLI hoặc non-web không có servlet container | Không khớp | **Khớp** |
| Ứng dụng reactive không triển khai WAR truyền thống | Không khớp | **Khớp** |

**Điểm dễ nhầm:** `@ConditionalOnNotWarDeployment` **không đồng nghĩa** với “chỉ chạy trên executable JAR” hoặc “chỉ chạy trên ứng dụng web có embedded Tomcat”. Nó chỉ loại trừ traditional WAR deployment. Nếu bean chỉ có nghĩa trong ứng dụng servlet, hãy bổ sung điều kiện riêng cho **servlet web application**.

## 3. Spring Boot nhận biết traditional WAR như thế nào?

Spring Boot dùng `OnWarDeploymentCondition` để đánh giá hai annotation. Về cơ chế ở Spring Boot 3.x, điều kiện quan sát **context đang được xây dựng**: có phải `WebApplicationContext` được cung cấp trong lúc xử lý điều kiện, và `ServletContext` của nó đã có hay chưa. Một `ServletContext` được container bên ngoài cung cấp khi traditional WAR bắt đầu là dấu hiệu để khớp nhánh WAR.

Với embedded server, bean definitions và auto-configuration được xử lý **trước khi** embedded server hoàn tất khởi động và tạo servlet context cho quá trình phục vụ request. Vì vậy nhánh traditional WAR không khớp, dù sau khi server chạy, ứng dụng vẫn có `ServletContext`.

Diễn tiến rút gọn:

1. Spring Boot tạo application context và đọc các lớp cấu hình/auto-configuration.
2. Khi gặp `@ConditionalOnWarDeployment` hoặc `@ConditionalOnNotWarDeployment`, framework kiểm tra trạng thái triển khai hiện tại.
3. Nhánh tương ứng được phép đăng ký các bean definitions; nhánh còn lại bị bỏ qua.
4. Context tiếp tục khởi tạo bean, rồi ứng dụng hoàn thành vòng đời khởi động.

**Lưu ý về thời điểm:** annotation là **điều kiện đăng ký bean lúc xây dựng context**. Chúng không thay đổi kết quả theo từng request; không chờ đến lần đầu dùng bean; không quan sát lại trạng thái server sau khi ứng dụng đã khởi động.

Không nên tự mô phỏng quy tắc này bằng cách suy ra từ `server.port`, biến môi trường `APP_MODE`, hoặc tên file JAR/WAR. Các giá trị đó không chứng minh ai đang sở hữu servlet container.

## 4. Ví dụ sử dụng trong auto-configuration

Giả sử một thư viện cần cung cấp `DeploymentPolicy` tương ứng với nơi chạy ứng dụng. Trong cấu hình thực tế, ta có thể đăng ký hai implementation khác nhau:

~~~java
package example.deployment.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWarDeployment;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWarDeployment;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class DeploymentPolicyAutoConfiguration {

    @Bean
    @ConditionalOnWarDeployment
    DeploymentPolicy externalContainerPolicy() {
        return new DeploymentPolicy("external-container");
    }

    @Bean
    @ConditionalOnNotWarDeployment
    DeploymentPolicy selfManagedPolicy() {
        return new DeploymentPolicy("self-managed");
    }

    public record DeploymentPolicy(String mode) {
    }
}
~~~

Đoạn trên là **lớp production độc lập** nếu lưu tại `src/main/java/example/deployment/autoconfigure/DeploymentPolicyAutoConfiguration.java` và dự án có dependency Spring Boot auto-configuration. Khi chạy đúng mô hình, một trong hai method bean được chọn theo điều kiện. Ở đây `DeploymentPolicy` chỉ minh họa quyết định cấu hình; nó **không** tự tạo servlet container hay thay đổi cấu hình Tomcat.

Nếu đây là một auto-configuration do thư viện cung cấp, cần đăng ký tên class trong tệp:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
example.deployment.autoconfigure.DeploymentPolicyAutoConfiguration
~~~

Trong Spring Boot 3.x, đây là cơ chế chuẩn để Boot phát hiện auto-configuration của thư viện. Khi kiểm tra hai nhánh, cũng cần bảo đảm lớp cấu hình thực sự được nạp; nếu thiếu file imports thì cả hai bean đều không xuất hiện dù điều kiện đúng.

### Đặt annotation ở class hay ở bean?

Có thể chọn cả một nhóm bean dành riêng cho WAR:

~~~java
@AutoConfiguration
@ConditionalOnWarDeployment
public class ExternalContainerAutoConfiguration {
    // Các @Bean liên quan chỉ được xử lý trong traditional WAR.
}
~~~

Ngược lại, nếu cùng class chứa nhiều bean độc lập thì nên đặt annotation trên **phương thức cụ thể**. Điều kiện trên class có thể vô tình loại bỏ các bean vốn vẫn cần chạy ở cả hai mô hình.

### Phân biệt với kiểm tra loại ứng dụng web

`@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)` chỉ nói ứng dụng là **servlet web application**; cả traditional WAR và servlet embedded đều có thể thỏa.

Nếu bean chỉ dành cho **servlet embedded** (không muốn tạo trong CLI hoặc WebFlux), ta có thể kết hợp hai điều kiện:

~~~java
@Bean
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnNotWarDeployment
ServletOnlyCustomizer servletOnlyCustomizer() {
    return new ServletOnlyCustomizer();
}
~~~

Đây là **đoạn minh họa**, giả sử `ServletOnlyCustomizer` là một class riêng do ứng dụng định nghĩa và import `ConditionalOnWebApplication` từ cùng package điều kiện. Mỗi annotation kiểm tra một khía cạnh khác nhau: **loại ứng dụng** và **mô hình triển khai**.

## 5. Ví dụ kiểm chứng Java 17+ / Spring Boot 3.3 / JUnit 5

Ví dụ sau có thể lưu thành **một tệp test hoàn chỉnh**. Test thứ nhất tạo `ApplicationContext` không mang servlet context nên nhánh **NotWar** khớp. Test thứ hai cung cấp `MockServletContext` **trước khi refresh context**, mô phỏng điều kiện của một servlet context đã được container cung cấp, vì vậy nhánh **War** khớp.

**Tệp:** `src/test/java/example/deployment/WarDeploymentConditionsTest.java`

~~~java
package example.deployment;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnNotWarDeployment;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWarDeployment;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockServletContext;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class WarDeploymentConditionsTest {

    @Test
    void ordinaryContextMatchesNotWar() {
        try (var context =
                     new AnnotationConfigApplicationContext(DeploymentConfiguration.class)) {

            assertThat(context.containsBean("externalWarPolicy")).isFalse();
            assertThat(context.containsBean("otherDeploymentPolicy")).isTrue();
            assertThat(context.getBean(DeploymentPolicy.class).mode())
                    .isEqualTo("not-war");
        }
    }

    @Test
    void contextWithServletContextAtEvaluationMatchesWar() {
        try (var context = new AnnotationConfigWebApplicationContext()) {
            context.setServletContext(new MockServletContext());
            context.register(DeploymentConfiguration.class);
            context.refresh();

            assertThat(context.containsBean("externalWarPolicy")).isTrue();
            assertThat(context.containsBean("otherDeploymentPolicy")).isFalse();
            assertThat(context.getBean(DeploymentPolicy.class).mode())
                    .isEqualTo("war");
        }
    }

    interface DeploymentPolicy {
        String mode();
    }

    @Configuration(proxyBeanMethods = false)
    static class DeploymentConfiguration {

        @Bean
        @ConditionalOnWarDeployment
        DeploymentPolicy externalWarPolicy() {
            return () -> "war";
        }

        @Bean
        @ConditionalOnNotWarDeployment
        DeploymentPolicy otherDeploymentPolicy() {
            return () -> "not-war";
        }
    }
}
~~~

Dependency mẫu trong `build.gradle` **của một dự án Spring Boot đã cấu hình plugin/BOM quản lý version**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` cung cấp Spring Web và Servlet API; `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và `MockServletContext` thông qua Spring Test. Với Spring Boot 3.3, sử dụng Java 17+.

Chạy trong thư mục dự án chứa bài test:

~~~bash
# Linux / macOS
./gradlew test --tests "example.deployment.WarDeploymentConditionsTest"

# Windows
gradlew.bat test --tests "example.deployment.WarDeploymentConditionsTest"
~~~

**Kết quả kỳ vọng:** hai test PASS. Test thứ nhất tìm đúng bean `otherDeploymentPolicy` và giá trị `not-war`; test thứ hai tìm đúng bean `externalWarPolicy` và giá trị `war`. Không có lệnh `System.out.println`, do đó không có stdout cố định để đối chiếu; log Gradle phụ thuộc cấu hình chạy test.

**Giới hạn của test:** `MockServletContext` chỉ tái tạo **điều kiện mà annotation quan sát trong một context mô phỏng**. Nó không khởi động Tomcat bên ngoài và không chứng minh rằng file WAR đã được deploy đúng trong môi trường thật. Vì vậy, trước khi phát hành, vẫn nên kiểm tra traditional WAR trên servlet container dự kiến triển khai.

## 6. Hiểu đúng trường hợp “WAR nhưng chạy embedded”

Một Spring Boot **executable WAR** có thể dùng theo hai cách:

~~~text
A. Tomcat ngoài ứng dụng nhận file app.war
   -> container ngoài tạo ServletContext và khởi động ứng dụng
   -> @ConditionalOnWarDeployment: khớp
   -> @ConditionalOnNotWarDeployment: không khớp

B. java -jar app.war
   -> ứng dụng tự chạy embedded servlet server
   -> @ConditionalOnWarDeployment: không khớp
   -> @ConditionalOnNotWarDeployment: khớp
~~~

Cùng một artifact nhưng **đường khởi động** khác nhau nên kết quả điều kiện khác nhau. Chỉ nhìn thấy `bootWar` trong Gradle hoặc đuôi `.war` trong đường dẫn deploy không đủ để kết luận.

Với triển khai WAR truyền thống, lớp khởi động có thể kế thừa `SpringBootServletInitializer` (ví dụ bên dưới chỉ minh họa kiểu khởi động; để chạy cần các dependency và cấu hình đóng gói WAR phù hợp):

~~~java
@SpringBootApplication
public class MyApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(MyApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

Đoạn này cần import `SpringApplication`, `SpringBootApplication`, `SpringApplicationBuilder` và `SpringBootServletInitializer` từ các package Spring Boot tương ứng. `configure(...)` phục vụ nhánh servlet container ngoài; `main(...)` phục vụ nhánh chạy trực tiếp. Đối với Gradle, đóng gói WAR thường dùng plugin `war` và dependency container dưới `providedRuntime` theo hướng dẫn Spring Boot, tránh đóng vai trò sở hữu container khi nó đã được cung cấp bên ngoài.

**Không nên** gắn annotation chỉ dựa trên yêu cầu “dùng WAR” nếu thực tế vẫn khởi chạy bằng embedded server. Hãy mô tả chính xác đường triển khai mong muốn.

## 7. Các lỗi thường gặp

1. **Đồng nhất `@ConditionalOnWarDeployment` với tên file `*.war`.** Sai vì executable WAR chạy `java -jar` không phải traditional WAR. Kiểm tra cách ứng dụng được khởi động thực tế.
2. **Nghĩ `@ConditionalOnNotWarDeployment` chỉ chạy trên JAR.** Sai vì executable WAR chạy embedded cũng khớp; non-web context cũng khớp.
3. **Dùng `@ConditionalOnWebApplication` thay cho điều kiện WAR.** Annotation web chỉ xác định context web; không phân biệt external container và embedded servlet server.
4. **Gắn `@ConditionalOnNotWarDeployment` lên bean phụ thuộc servlet mà không xét CLI/WebFlux.** Kết hợp `@ConditionalOnWebApplication(type = SERVLET)` và các điều kiện classpath khi cần.
5. **Đánh giá điều kiện sau khi server đã khởi động rồi dự đoán ngược.** Conditions được tính trong lúc đăng ký bean, không phải trong lúc xử lý request. ServletContext có thể được tạo sau mốc đó trong embedded deployment.
6. **Quên đăng ký auto-configuration của thư viện.** Không có bean có thể do class chưa được import chứ không phải vì annotation quyết định sai.
7. **Thử mô phỏng WAR bằng cách đổi `server.port` hay `spring.main.web-application-type`.** Các thuộc tính này không tạo ra traditional external-container deployment.
8. **Test nhánh WAR bằng một context thường không có servlet context.** Muốn mô phỏng nhánh WAR, cung cấp một `ServletContext` vào một `WebApplicationContext` **trước khi** condition được xử lý, hoặc chạy integration test trong servlet container ngoài.

Để tìm nguyên nhân tại runtime, bật `--debug` khi khởi động Spring Boot và đọc **Condition Evaluation Report**. Tìm `OnWarDeploymentCondition`, phần matched/unmatched và cấu hình bị loại. Với thư viện, xác minh thêm rằng tên auto-configuration có trong `AutoConfiguration.imports`.

## 8. Câu hỏi luyện tập

**Câu 1.** Một executable WAR chạy bằng `java -jar demo.war` với embedded Tomcat. `@ConditionalOnWarDeployment` có khớp không?

**Đáp án:** Không. Đây là embedded deployment, mặc dù artifact là WAR.

**Câu 2.** Một servlet application được Tomcat bên ngoài khởi động sau khi triển khai `demo.war`. Annotation nào khớp?

**Đáp án:** `@ConditionalOnWarDeployment`. Nhánh `@ConditionalOnNotWarDeployment` không khớp.

**Câu 3.** Một chương trình chỉ dùng Spring ApplicationContext, không có servlet web server. `@ConditionalOnNotWarDeployment` có khớp không?

**Đáp án:** Có. “Không phải traditional WAR” bao gồm cả non-web context; annotation này không tự giới hạn phạm vi servlet.

**Câu 4.** Có thể thay `@ConditionalOnWarDeployment` bằng `@ConditionalOnWebApplication(type = SERVLET)` để phát hiện Tomcat bên ngoài không?

**Đáp án:** Không. Servlet web application có thể chạy với cả embedded server lẫn traditional WAR. Hai điều kiện trả lời hai câu hỏi khác nhau.

**Câu 5.** Vì sao không thể xác định nhánh WAR bằng cách nhìn tên artifact `app.war`?

**Đáp án:** Vì cùng một executable WAR có thể được triển khai vào servlet container ngoài hoặc chạy trực tiếp với embedded server; cách khởi động quyết định nhánh phù hợp.

## 9. Ghi nhớ để áp dụng

- **`@ConditionalOnWarDeployment`** dành cho cấu hình chỉ hợp lệ khi ứng dụng là **traditional WAR được triển khai vào servlet container bên ngoài**.
- **`@ConditionalOnNotWarDeployment`** dành cho cấu hình chỉ hợp lệ khi ứng dụng **không** ở chế độ traditional WAR; bao gồm embedded deployment, executable WAR chạy trực tiếp và non-web context.
- Điều kiện được quyết định trong quá trình xây dựng `ApplicationContext`, không dựa vào đuôi file và không thay đổi theo request.
- Chọn phạm vi annotation phù hợp ở class hoặc bean; kết hợp `@ConditionalOnWebApplication` nếu logic yêu cầu đúng servlet web application.
- Xác nhận cả hai nhánh bằng test, sau đó kiểm tra trên servlet container thật nếu ứng dụng dự kiến triển khai WAR truyền thống.

### Tài liệu tham khảo

- [Spring Boot 3.3 Javadoc — ConditionalOnWarDeployment](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWarDeployment.html).
- [Spring Boot 3.3 Javadoc — ConditionalOnNotWarDeployment](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnNotWarDeployment.html).
- [Spring Boot 3.3 Reference — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
- [Spring Boot Reference — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html).
