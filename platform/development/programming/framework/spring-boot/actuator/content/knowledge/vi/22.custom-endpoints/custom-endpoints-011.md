# Lựa chọn @WebEndpoint hoặc @JmxEndpoint khi chỉ hỗ trợ một công nghệ

Endpoint Actuator là một điểm quản trị của ứng dụng, còn HTTP và JMX là hai cách để công cụ vận hành gọi điểm quản trị đó. Việc một endpoint tồn tại trong mã Java không có nghĩa nó phải được công bố trên cả hai kênh.

Khi yêu cầu thiết kế chỉ hỗ trợ một công nghệ, `@WebEndpoint` hoặc `@JmxEndpoint` thể hiện giới hạn ấy ngay trên kiểu endpoint. Ngược lại, nếu endpoint có thể dùng chung nhưng mỗi môi trường chỉ muốn mở một kênh, `@Endpoint` kết hợp cấu hình exposure thường phù hợp hơn.

Bài này tập trung vào cách chọn annotation, quan hệ của nó với cấu hình và cách chứng minh endpoint chỉ xuất hiện trên đúng kênh. Ví dụ dùng Spring Boot 3.3 và JDK 21; mã Java không sử dụng tính năng preview.

## 1. Phân biệt endpoint và công nghệ công bố

Hãy hình dung một thao tác quản trị có hai lớp:

- **Nội dung thao tác:** đọc trạng thái, cung cấp thông tin hoặc thực hiện một hành động quản trị.
- **Kênh gọi:** nhận yêu cầu HTTP hay nhận lời gọi tới một MBean trong JMX.

`@ReadOperation`, `@WriteOperation` và `@DeleteOperation` mô tả thao tác theo mô hình Actuator. Annotation trên lớp xác định endpoint được phép tham gia vào kênh nào.

| Annotation trên lớp | Có thể công bố qua HTTP | Có thể công bố qua JMX | Ý nghĩa thiết kế |
| --- | --- | --- | --- |
| `@Endpoint` | Có | Có | Endpoint không bị giới hạn vào một trong hai công nghệ |
| `@WebEndpoint` | Có | Không | Chỉ cung cấp endpoint qua HTTP |
| `@JmxEndpoint` | Không | Có | Chỉ cung cấp endpoint qua JMX |

“Có thể” trong bảng là khả năng hỗ trợ. Endpoint còn phải được đăng ký thành bean, được bật và được đưa vào cấu hình công bố phù hợp; HTTP cũng cần hạ tầng ứng dụng web.

[API `WebEndpoint` của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html) xác định phạm vi HTTP, còn [API `JmxEndpoint`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html) xác định phạm vi JMX.

Ví dụ: một endpoint chỉ dành cho JConsole không tự có URL `/actuator/...`. Việc gọi bằng `curl` không phải cách kiểm chứng đầy đủ cho endpoint đó.

## 2. Chọn theo yêu cầu cố định hay chính sách triển khai

### 2.1. Chọn @WebEndpoint khi hợp đồng quản trị chỉ có HTTP

Dùng `@WebEndpoint` khi công cụ sử dụng endpoint là chương trình gọi HTTP và nhóm phát triển chủ động không cung cấp hợp đồng JMX cho chức năng này.

Ví dụ: công cụ vận hành của một hệ thống chỉ đọc thông báo triển khai bằng HTTP. Nhóm phát triển muốn endpoint ấy tiếp tục chỉ có HTTP ngay cả khi một môi trường khác bật JMX cho ứng dụng.

Đây là một quyết định về phạm vi hỗ trợ. Không nên chọn annotation này chỉ vì hiện tại chưa có người dùng JMX, nếu endpoint thực chất vẫn được thiết kế để dùng chung.

### 2.2. Chọn @JmxEndpoint khi hợp đồng quản trị chỉ có JMX

Dùng `@JmxEndpoint` khi chức năng được cung cấp cho công cụ quản trị JVM qua MBean và không có hợp đồng HTTP.

Ví dụ: nhóm vận hành dùng công cụ JMX hiện có để đọc thông báo của JVM. Endpoint này cần xuất hiện trong danh sách MBean, nhưng không được trở thành một URL quản trị khi ai đó mở rộng danh sách HTTP exposure.

Một ứng dụng chỉ dùng JMX không cần thêm web starter chỉ để công bố endpoint đó. Dự án thực hành bên dưới có web starter vì nó so sánh hai kênh trong cùng ứng dụng.

### 2.3. Chọn @Endpoint và exposure khi giới hạn tùy môi trường

Nếu chức năng dùng được qua cả hai công nghệ nhưng production chỉ muốn mở HTTP, giới hạn đó có thể là **chính sách triển khai**, không phải giới hạn của bản thân chức năng.

Khi ấy có thể giữ `@Endpoint`, đưa ID vào danh sách HTTP và loại ID khỏi JMX. Môi trường khác vẫn có thể lựa chọn ngược lại mà không đổi annotation hay biên dịch lại mã.

Một câu hỏi hữu ích trước khi chọn là: “Nếu ngày mai cần kênh còn lại, ta chỉ muốn đổi cấu hình hay thực sự phải thiết kế và cam kết thêm một hợp đồng sử dụng?”

## 3. Annotation và exposure là hai điều kiện khác nhau

Có thể diễn đạt quá trình công bố một endpoint như sau:

```text
Endpoint đã là bean
        |
        v
Endpoint được bật
        |
        v
Annotation cho phép công nghệ đang xét
        |
        v
Công nghệ đó đã sẵn sàng và exposure cho phép ID
        |
        v
Endpoint được công bố trên kênh tương ứng
```

Sơ đồ mô tả các điều kiện cần hiểu, không khẳng định thứ tự gọi nội bộ của tất cả thành phần Spring Boot.

Các cấu hình thường gặp trong Spring Boot 3.3:

| Cấu hình | Vai trò |
| --- | --- |
| `management.endpoint.<id>.enabled` | Bật hoặc tắt endpoint có ID tương ứng |
| `management.endpoints.web.exposure.include` | Các ID được chọn để công bố qua HTTP |
| `management.endpoints.web.exposure.exclude` | Các ID bị loại khỏi HTTP |
| `spring.jmx.enabled` | Bật hỗ trợ quản lý JMX của Spring Boot |
| `management.endpoints.jmx.exposure.include` | Các ID được chọn để công bố qua JMX |
| `management.endpoints.jmx.exposure.exclude` | Các ID bị loại khỏi JMX |

Khi cùng một ID nằm trong cả `include` và `exclude` của một kênh, `exclude` được ưu tiên. [Tài liệu endpoint Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) mô tả riêng enablement và exposure.

**Exposure không chuyển đổi công nghệ của endpoint.** Thêm ID của `@JmxEndpoint` vào HTTP `include` không tạo ra bản HTTP của endpoint. Tương tự, thêm ID của `@WebEndpoint` vào JMX `include` không tạo MBean cho nó.

Ở phía JMX, Spring Boot mặc định không bật tính năng quản lý này; cấu hình `spring.jmx.enabled=true` là một điều kiện cần khi dùng cơ chế tự cấu hình trong bài thực hành. Nó không có nghĩa toàn bộ JMX của JVM và mọi thư viện đều do thuộc tính này điều khiển. Xem [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 4. Thực hành: so sánh ba loại endpoint trong cùng ứng dụng

Mục tiêu thí nghiệm là quan sát cùng lúc:

- `webnotice`: chỉ HTTP.
- `jvmnotice`: chỉ JMX.
- `sharednotice`: hỗ trợ cả hai để làm đối chứng.

Các thao tác chỉ trả thông báo cố định, giúp tách hành vi công bố endpoint khỏi xử lý nghiệp vụ.

### 4.1. Cấu trúc và cấu hình build

Đây là dự án mẫu độc lập, dùng Gradle 8.x và JDK 21. Phiên bản Spring Boot `3.3.0` được cố định để tái hiện hành vi trong dòng 3.3; đây không phải tuyên bố về phiên bản mới nhất.

```text
transport-endpoint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/actuatortech/
    │   └── TransportEndpointApplication.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'transport-endpoint-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Web starter cung cấp hạ tầng HTTP cho thí nghiệm. Actuator starter cung cấp mô hình endpoint và cơ chế công bố endpoint. BOM quản lý phiên bản dependency.

### 4.2. Một tệp Java hoàn chỉnh

Lưu đúng đường dẫn `src/main/java/example/actuatortech/TransportEndpointApplication.java`:

```java
package example.actuatortech;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.jmx.annotation.JmxEndpoint;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TransportEndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransportEndpointApplication.class, args);
    }

    @Bean
    WebNoticeEndpoint webNoticeEndpoint() {
        return new WebNoticeEndpoint();
    }

    @Bean
    JvmNoticeEndpoint jvmNoticeEndpoint() {
        return new JvmNoticeEndpoint();
    }

    @Bean
    SharedNoticeEndpoint sharedNoticeEndpoint() {
        return new SharedNoticeEndpoint();
    }

    @Bean
    ApplicationRunner inspectJmx(MBeanServer server) {
        return args -> {
            ObjectName jvm = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Jvmnotice");
            ObjectName web = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Webnotice");
            ObjectName shared = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Sharednotice");
            System.out.println("jvmnotice registered=" + server.isRegistered(jvm));
            System.out.println("webnotice registered=" + server.isRegistered(web));
            System.out.println("sharednotice registered=" + server.isRegistered(shared));
            if (server.isRegistered(jvm)) {
                Object result = server.invoke(
                        jvm, "notice", new Object[0], new String[0]);
                System.out.println("jvmnotice result=" + result);
            }
        };
    }

    @WebEndpoint(id = "webnotice")
    public static class WebNoticeEndpoint {
        @ReadOperation
        public Map<String, String> notice() {
            return Map.of("channel", "http");
        }
    }

    @JmxEndpoint(id = "jvmnotice")
    public static class JvmNoticeEndpoint {
        @ReadOperation
        public String notice() {
            return "jmx-ready";
        }
    }

    @Endpoint(id = "sharednotice")
    public static class SharedNoticeEndpoint {
        @ReadOperation
        public String notice() {
            return "shared-ready";
        }
    }
}
```

Những điểm cần đọc trong mã:

1. Ba lớp endpoint dùng ba annotation khác nhau và ba ID khác nhau.
2. Mỗi đối tượng được đăng ký bằng `@Bean`; không chỉ khai báo annotation trên một lớp rồi chờ Spring tự tạo đối tượng.
3. Các thao tác đều dùng `@ReadOperation`, vì nội dung là đọc thông tin.
4. `ApplicationRunner` chỉ là phần kiểm chứng: nó xem MBean đã được đăng ký hay chưa và gọi trực tiếp một thao tác JMX.
5. `javax.management` là package JMX của JDK, vẫn dùng tên này trên Java 21; không đổi import thành `jakarta.management`.

`Map` trả về từ `webnotice` giúp quan sát phản hồi HTTP dạng JSON. Việc `jvmnotice` trả về `String` giúp tập trung vào lời gọi thao tác JMX; không có JSON hay mã trạng thái HTTP trong lời gọi `MBeanServer.invoke` đó.

### 4.3. application.properties

```properties
server.address=127.0.0.1

spring.jmx.enabled=true
management.endpoints.jmx.domain=learning.actuator

management.endpoints.web.exposure.include=health,webnotice,sharednotice
management.endpoints.jmx.exposure.include=health,jvmnotice,sharednotice
```

Domain JMX được đặt rõ để chương trình kiểm chứng dùng các `ObjectName` ổn định. Ví dụ giả định một context của bài thực hành, không bật cơ chế tạo tên duy nhất tùy context.

Phần kiểm chứng `ApplicationRunner` cần bean `MBeanServer`, nên giữ `spring.jmx.enabled=true` khi chạy đúng nguyên mẫu. Nếu rút gọn dự án thành ví dụ chỉ HTTP và tắt JMX, hãy bỏ cả bean kiểm chứng JMX; nó không phải một phần bắt buộc của endpoint.

Không có Spring Security trong dependency của nguyên mẫu. Nếu ghép mã vào ứng dụng đã có bảo mật, quyền truy cập HTTP còn phụ thuộc cấu hình bảo mật của ứng dụng đó.

### 4.4. Khởi chạy

Từ thư mục gốc dự án mẫu, tạo Gradle Wrapper bằng Gradle 8.x đang cài nếu chưa có:

```shell
gradle wrapper --gradle-version 8.5
```

Windows PowerShell:

```powershell
.\gradlew.bat clean bootRun
```

Linux/macOS:

```shell
./gradlew clean bootRun
```

Ngoài log khởi động thông thường, phần kiểm chứng JMX in đúng các dòng sau:

```text
jvmnotice registered=true
webnotice registered=false
sharednotice registered=true
jvmnotice result=jmx-ready
```

`jvmnotice` có MBean và lời gọi `notice` thành công. `webnotice` không được đăng ký thành MBean Actuator tương ứng. `sharednotice` có mặt vì annotation dùng chung và exposure JMX đều cho phép.

## 5. Kiểm tra HTTP và JMX bằng đúng công cụ

### 5.1. HTTP

Mở terminal khác. Trên Windows dùng `curl.exe`; trên Linux/macOS thay bằng `curl`:

```shell
curl.exe -s "http://127.0.0.1:8080/actuator/webnotice"
curl.exe -i "http://127.0.0.1:8080/actuator/jvmnotice"
curl.exe -s "http://127.0.0.1:8080/actuator/sharednotice"
```

Với nguyên mẫu đang chạy:

| Endpoint | Kết quả HTTP |
| --- | --- |
| `/actuator/webnotice` | 200; thân phản hồi `{"channel":"http"}` |
| `/actuator/jvmnotice` | 404; không có thao tác HTTP tương ứng |
| `/actuator/sharednotice` | 200; thân phản hồi `shared-ready` |

Phản hồi từ `sharednotice` ở đây là chuỗi văn bản, không phải một đối tượng JSON. Không suy ra rằng mọi `@ReadOperation` đều trả về cùng một dạng nội dung.

Mã 404 của `jvmnotice` là kết quả được mong đợi trong nguyên mẫu. Trong ứng dụng khác, một mã 404 đơn lẻ chưa đủ chứng minh nguyên nhân; còn phải xét đường dẫn, cổng, exposure và các lớp trung gian.

### 5.2. JMX

Chương trình đã kiểm tra bằng `MBeanServer` bên trong cùng tiến trình, nên không cần cấu hình kết nối JMX từ xa.

Nếu dùng JConsole và môi trường cho phép gắn vào tiến trình Java cục bộ, chọn tiến trình của ứng dụng rồi xem domain `learning.actuator`, nhóm `type=Endpoint`. Trong cấu hình mẫu:

| ObjectName | Được đăng ký |
| --- | --- |
| `learning.actuator:type=Endpoint,name=Jvmnotice` | Có |
| `learning.actuator:type=Endpoint,name=Webnotice` | Không |
| `learning.actuator:type=Endpoint,name=Sharednotice` | Có |

Ở MBean `Jvmnotice`, gọi operation `notice` không có tham số sẽ nhận chuỗi `jmx-ready`.

Phân biệt ID và tên đối tượng: cấu hình exposure dùng ID `jvmnotice`, còn tên MBean mặc định trong thí nghiệm có phần `name=Jvmnotice`. Không lấy nguyên URL HTTP làm tên MBean. Việc tùy biến domain hoặc cơ chế đặt tên sẽ làm `ObjectName` khác đi.

## 6. Thí nghiệm exposure: cấu hình không vượt qua giới hạn annotation

### 6.1. Đưa cả ba ID vào cả hai danh sách

Thay hai dòng exposure trong dự án mẫu bằng:

```properties
management.endpoints.web.exposure.include=health,webnotice,jvmnotice,sharednotice
management.endpoints.jmx.exposure.include=health,webnotice,jvmnotice,sharednotice
```

Khởi động lại ứng dụng rồi kiểm tra lại. Kết quả vẫn là:

| Endpoint | HTTP | MBean JMX |
| --- | --- | --- |
| `webnotice` | Có | Không |
| `jvmnotice` | Không | Có |
| `sharednotice` | Có | Có |

Thí nghiệm này kiểm tra trực tiếp ý nghĩa “chỉ hỗ trợ một công nghệ”. Danh sách `include` chọn trong tập endpoint phù hợp; nó không biến một loại endpoint thành loại khác.

Trong nguyên mẫu, hai annotation chuyên biệt đặt giới hạn ở cấp kiểu. Không cần xếp chồng thêm `@Endpoint` trên cùng lớp để “bật” kênh còn lại. Hãy chọn một mô hình rõ ràng cho mỗi lớp endpoint.

### 6.2. Giữ @Endpoint nhưng chỉ công bố HTTP theo môi trường

Giữ `SharedNoticeEndpoint` dùng `@Endpoint`, và thêm:

```properties
management.endpoints.jmx.exposure.exclude=sharednotice
```

Ngay cả khi `sharednotice` vẫn nằm trong JMX `include`, MBean tương ứng không được công bố do `exclude` được ưu tiên. Trong khi đó, HTTP `/actuator/sharednotice` vẫn trả `shared-ready`.

Dòng stdout của phần kiểm chứng thay đổi thành `sharednotice registered=false`. Không cần đổi mã của endpoint. Đây là ví dụ giới hạn theo cấu hình, khác với thay annotation thành `@WebEndpoint`.

Khi endpoint thực sự không hỗ trợ JMX trong thiết kế, dùng `@WebEndpoint` giúp thể hiện quyết định đó rõ hơn việc chỉ dựa vào một file cấu hình ở một môi trường.

## 7. Những điều annotation chuyên biệt không tự giải quyết

### 7.1. Không thay thế đăng ký bean và mô hình thao tác

`@WebEndpoint` hoặc `@JmxEndpoint` vẫn cần một đối tượng do Spring quản lý. Trong bài thực hành, `@Bean` đảm nhiệm việc đó. Các phương thức cũng phải được đánh dấu bằng annotation thao tác Actuator phù hợp; một phương thức `public` thông thường không tự trở thành thao tác quản trị.

Nếu thao tác có tham số Java và cần ánh xạ theo tên, vẫn phải bảo đảm metadata tên tham số được giữ khi biên dịch. Việc đổi công nghệ công bố không loại bỏ những yêu cầu chung của mô hình endpoint.

### 7.2. @WebEndpoint không đồng nghĩa với @RestController

`@WebEndpoint` vẫn nằm trong mô hình thao tác Actuator. Nó không có nghĩa được tùy ý áp dụng toàn bộ cách ánh xạ của controller Spring MVC, như thêm `@GetMapping` rồi trông chờ Actuator xử lý như một controller thông thường.

Chọn HTTP không đồng nghĩa chỉ chọn Servlet. Endpoint Actuator qua web có thể được tích hợp với hạ tầng web được hỗ trợ, chẳng hạn Spring MVC hoặc WebFlux, tùy ứng dụng. Nếu cần xử lý yêu cầu đặc thù của một framework, hãy kiểm tra cơ chế tích hợp tương ứng thay vì giả định annotation này tự cung cấp mọi kiểu tham số HTTP.

### 7.3. Không đồng nghĩa với phân quyền hay mở cổng từ xa

`@JmxEndpoint` làm endpoint chỉ thuộc kênh JMX, không tự tạo một kết nối JMX từ xa và không tự quy định ai được gọi MBean. Việc quản lý kết nối JMX từ xa là cấu hình riêng của môi trường JVM.

Tương tự, `@WebEndpoint` không tự bảo vệ URL bằng xác thực. Giới hạn công nghệ và kiểm soát quyền truy cập là hai quyết định cần được xem xét riêng. Một bộ lọc bảo mật HTTP không tự kiểm soát lời gọi JMX.

### 7.4. Không phải annotation mở rộng endpoint có sẵn

Nếu đã có một endpoint dùng chung và chỉ muốn thay đổi cách một số thao tác được biểu diễn trên một công nghệ, cần phân biệt với `@EndpointWebExtension` và `@EndpointJmxExtension`.

`@WebEndpoint`/`@JmxEndpoint` khai báo endpoint chuyên biệt. Annotation extension gắn phần mở rộng với một endpoint đã có. Không cần tạo thêm một endpoint mới và nhân đôi nghiệp vụ chỉ vì muốn tùy biến lớp công bố. [Phần Implementing Custom Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom) trình bày các lựa chọn này.

## 8. Cách kiểm thử quyết định chỉ hỗ trợ một công nghệ

Một bài kiểm thử chỉ gọi trực tiếp `new JvmNoticeEndpoint().notice()` sẽ chứng minh giá trị trả về, nhưng chưa chứng minh endpoint không bị công bố qua HTTP.

Với yêu cầu giới hạn công nghệ, nên kiểm tra cả **sự hiện diện trên kênh được hỗ trợ** và **sự vắng mặt trên kênh còn lại**:

| Yêu cầu | Bằng chứng cần có |
| --- | --- |
| Endpoint chỉ HTTP | Yêu cầu HTTP thành công; MBean tương ứng không được đăng ký |
| Endpoint chỉ JMX | MBean tồn tại và gọi thao tác được; không có ánh xạ HTTP tương ứng |
| Exposure không đổi loại endpoint | Đưa ID vào danh sách kênh còn lại nhưng kết quả công bố không đổi |
| @Endpoint giới hạn theo môi trường | Đổi exposure làm thay đổi kênh công bố mà không đổi mã |

Có thể dùng MockMvc cho phía HTTP của ứng dụng Spring MVC và `MBeanServer` cho JMX trong cùng lượt kiểm tra. Không cần mở kết nối JMX từ xa chỉ để chứng minh việc đăng ký MBean.

Khi thử nhiều application context trong cùng JVM, hãy đóng context sau mỗi ca hoặc cấu hình tên/domain riêng để tránh va chạm `ObjectName`. Nếu dùng cơ chế tên duy nhất, kiểm thử phải tra cứu tên thực tế thay vì cố định một tên không còn đúng.

## 9. Lỗi thường gặp và cách đối chiếu

| Hiện tượng | Điều cần xem lại |
| --- | --- |
| @JmxEndpoint không có URL dù đã thêm vào HTTP include | Đây là giới hạn công nghệ của annotation, không phải lỗi thiếu URL |
| @WebEndpoint không xuất hiện trong JConsole | Kiểm tra lại kỳ vọng: endpoint này không được công bố qua JMX |
| Endpoint không xuất hiện ở đâu | Đăng ký bean, annotation thao tác, enablement, exposure và hạ tầng cần thiết |
| MBean JMX không xuất hiện dù annotation đúng | `spring.jmx.enabled`, exposure JMX, domain/tên đối tượng và lỗi đăng ký |
| HTTP trả 401/403 | Chính sách xác thực/phân quyền của ứng dụng, không chỉ annotation endpoint |
| Endpoint dùng @Endpoint xuất hiện thêm qua JMX ở môi trường khác | Xem đây là khả năng được thiết kế hay một giới hạn cố định cần thể hiện trong mã |
| Thay annotation rồi công cụ vận hành không gọi được | Hợp đồng công nghệ đã thay đổi; cần kiểm tra và cập nhật bên gọi |

Đừng dùng một thao tác quản trị HTTP thất bại để kết luận JMX cũng không hoạt động, hoặc suy luận ngược lại. Hai kênh có cấu hình công bố và cơ chế truy cập khác nhau.

## 10. Bài tập quyết định

Với mỗi tình huống, chọn annotation và nêu lý do:

1. Một chức năng quản trị có hợp đồng chính thức chỉ qua HTTP; bật JMX cho các chức năng khác không được làm chức năng này xuất hiện thành MBean.
2. Một công cụ quản trị JVM chỉ gọi MBean; hệ thống không cam kết URL cho chức năng đó.
3. Cùng chức năng được dùng qua HTTP ở staging và JMX ở production, tùy chính sách triển khai.
4. Đã có endpoint dùng chung, chỉ muốn thay cách biểu diễn một thao tác ở phía HTTP.

Đối chiếu:

1. `@WebEndpoint`: thể hiện giới hạn hỗ trợ HTTP ngay trong kiểu endpoint.
2. `@JmxEndpoint`: thể hiện giới hạn hỗ trợ JMX.
3. `@Endpoint` và cấu hình exposure theo môi trường: chức năng vẫn hỗ trợ hai công nghệ.
4. Xem xét `@EndpointWebExtension` cho endpoint đã có, thay vì mặc định tạo thêm endpoint độc lập.

Trước khi chốt lựa chọn, hãy viết rõ tên công cụ sẽ gọi, công nghệ được cam kết và cách kiểm tra endpoint không xuất hiện ở kênh ngoài phạm vi. Đó là cơ sở để chọn annotation và xây dựng bằng chứng kiểm thử phù hợp.
