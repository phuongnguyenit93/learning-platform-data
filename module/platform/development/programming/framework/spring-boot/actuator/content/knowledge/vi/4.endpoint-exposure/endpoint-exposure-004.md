# Cấu hình danh sách include và exclude cho JMX

Một endpoint Actuator có thể được công bố qua nhiều kênh quản trị. Với **JMX (Java Management Extensions)**, endpoint được trình bày dưới dạng **MBean**, tức đối tượng quản trị được đăng ký trong một `MBeanServer`. Công cụ hoặc chương trình JMX tìm đối tượng này bằng tên quản trị, thay vì gọi URL HTTP.

Bài này giải thích cách chọn endpoint đưa ra qua JMX bằng hai thuộc tính:

- `management.endpoints.jmx.exposure.include`: danh sách mã endpoint được chọn để công bố.
- `management.endpoints.jmx.exposure.exclude`: danh sách mã endpoint bị loại khỏi kênh JMX.

Phạm vi là **Spring Boot 3.3.x**. Ví dụ thực hành dùng **Spring Boot 3.3.13, Java 21 và Gradle 8.5**, với cơ chế tự cấu hình JMX mặc định của Spring Boot.

## 1. Hiểu quan hệ giữa endpoint, JMX và MBean

Hãy hình dung ứng dụng có ba khả năng quản trị: `health`, `info` và `metrics`. Bạn muốn người vận hành xem sức khỏe và thông tin ứng dụng qua JMX, nhưng không đưa endpoint đọc số liệu lên kênh đó.

Cấu hình lựa chọn là:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

Nếu các điều kiện tạo endpoint đều được đáp ứng, tập được công bố qua JMX là `health` và `info`. `metrics` được chọn trong `include` rồi bị loại bởi `exclude`.

Ba quyết định cần phân biệt:

| Quyết định | Cấu hình liên quan | Câu hỏi được trả lời |
| --- | --- | --- |
| Bật hỗ trợ JMX của Spring | `spring.jmx.enabled` | Spring có tự cấu hình cơ chế xuất MBean không? |
| Bật một endpoint Actuator | `management.endpoint.<id>.enabled` | Endpoint đó có được phép hoạt động không? |
| Công bố endpoint qua JMX | `management.endpoints.jmx.exposure.include/exclude` | Endpoint nào được xuất qua kênh JMX? |

Các điều kiện khác như thư viện phụ thuộc và bean cần thiết vẫn phải thỏa mãn. Danh sách công bố không tạo ra một endpoint vốn không tồn tại.

### 1.1. Hai giá trị mặc định dễ bị nhầm

Trong Spring Boot 3.3:

- `spring.jmx.enabled` mặc định là `false`.
- `management.endpoints.jmx.exposure.include` mặc định là `health`; `exclude` không có mã loại trừ mặc định.

Vì vậy, “JMX mặc định chọn `health`” không có nghĩa một ứng dụng chưa bật JMX đã tự xuất endpoint đó. Đây là giá trị mặc định của hai cấu hình khác nhau. [Phụ lục cấu hình Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

## 2. Viết danh sách đúng cú pháp

### 2.1. Dạng Properties

```properties
spring.jmx.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

Mỗi phần tử là **mã endpoint**, chẳng hạn `health`, không phải:

- URL như `/actuator/health`.
- Tên lớp như `HealthEndpoint`.
- Tên MBean như `org.springframework.boot:type=Endpoint,name=Health`.

Cấu hình tập endpoint dùng nhánh số nhiều `management.endpoints`. Khóa `management.endpoint.health.enabled` dùng số ít vì cấu hình riêng một endpoint.

### 2.2. Dạng YAML tương đương

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - metrics
```

Danh sách YAML làm rõ từng phần tử khi có nhiều endpoint. Cũng có thể viết dạng chuỗi phân cách bằng dấu phẩy:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
        exclude: "metrics"
```

Khối ngắn trên chỉ minh họa cách viết danh sách; thiết lập `spring.jmx.enabled=true` vẫn cần có trong cấu hình hiệu lực.

### 2.3. Danh sách tự đặt thay cho lựa chọn mặc định

Nếu đặt:

```properties
management.endpoints.jmx.exposure.include=info
```

thì danh sách chọn là `info`. Đừng tự cộng thêm `health` chỉ vì đó là giá trị mặc định khi chưa cấu hình.

Nếu muốn cả hai, viết rõ:

```properties
management.endpoints.jmx.exposure.include=health,info
```

Danh sách này không biểu diễn thứ tự thực hiện hoặc thứ tự bắt buộc hiển thị trong công cụ JMX. Bài thực hành sẽ chủ động sắp xếp tên trước khi in để có đầu ra ổn định.

## 3. Quy tắc chọn: include trước, exclude thắng khi trùng

Có thể dùng mô hình tập hợp sau để suy luận:

```text
Các endpoint đủ điều kiện công bố qua JMX
        → giữ các mã được include chọn
        → bỏ các mã nằm trong exclude
        → đăng ký MBean cho các endpoint còn lại
```

Đây là mô hình giải thích kết quả, không phải mô tả chi tiết thứ tự mọi phương thức nội bộ.

Giả sử `health`, `info` và `metrics` đều được bật, hỗ trợ JMX và đáp ứng phụ thuộc:

| include | exclude | Kết quả trong ba endpoint đang xét |
| --- | --- | --- |
| `health,info` | Không đặt | `health,info` |
| `health,info` | `info` | `health` |
| `info` | Không đặt | `info` |
| `health` | `metrics` | `health` |
| `*` | `info` | `health,metrics` |
| `health,info` | `*` | Không có endpoint nào |

Một mã xuất hiện trong `exclude` không thể được “cứu lại” bằng cách thêm mã đó lần nữa vào `include`. Quy tắc này là ưu tiên giữa hai danh sách, không phụ thuộc dòng nào đứng sau trong tệp. [Quy tắc công bố endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

### 3.1. Dấu sao chọn tất cả

Ví dụ cấu hình JMX:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: "*"
        exclude:
          - env
          - beans
```

Dấu sao phải được đặt trong dấu nháy trong YAML. Nếu để `*` trần, trình phân tích YAML có thể hiểu đó là cú pháp tham chiếu bí danh, thay vì chuỗi chọn tất cả.

“Tất cả” ở đây là các endpoint đủ điều kiện trên kênh JMX. Nó không bật endpoint đã bị tắt, không thay thế thư viện còn thiếu và không biến endpoint chỉ dành cho HTTP thành endpoint JMX.

Khi cần một tập cố định, ghi rõ từng mã giúp nhìn ngay được những gì sẽ công bố. Với `include="*"`, một endpoint mới đủ điều kiện sau khi thêm phụ thuộc cũng có thể lọt vào tập lựa chọn.

### 3.2. Loại toàn bộ endpoint khỏi JMX

```properties
management.endpoints.jmx.exposure.exclude=*
```

Dòng này loại các endpoint Actuator khỏi kênh JMX, kể cả khi chúng xuất hiện trong `include`. Nó không đồng nghĩa tắt mọi MBean trong JVM, cũng không tự tắt công bố Actuator qua HTTP. [Cách ngừng công bố endpoint JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

## 4. JMX và HTTP có danh sách công bố riêng

Ví dụ:

```properties
spring.jmx.enabled=true

management.endpoint.health.enabled=true
management.endpoint.info.enabled=true

management.endpoints.jmx.exposure.include=health,info
management.endpoints.web.exposure.include=health
```

Với các điều kiện phù hợp:

| Endpoint | JMX | HTTP |
| --- | --- | --- |
| `health` | Được chọn | Được chọn |
| `info` | Được chọn | Không được chọn |

Nếu bổ sung `management.endpoints.jmx.exposure.exclude=info`, chỉ lựa chọn JMX của `info` thay đổi. Nếu đặt `management.endpoint.info.enabled=false`, quyết định bật của endpoint thay đổi và endpoint đó không được công bố qua các kênh.

Một URL không xuất hiện trong HTTP không chứng minh MBean tương ứng cũng vắng mặt. Muốn kiểm tra kênh JMX, hãy quan sát đúng `MBeanServer` và miền tên đang dùng.

### 4.1. Miền tên giúp tìm đúng MBean

Tên mặc định của endpoint `health` có dạng:

```text
org.springframework.boot:type=Endpoint,name=Health
```

Có thể đổi miền tên của các endpoint Actuator:

```properties
management.endpoints.jmx.domain=learning.actuator
```

Khi đó tên tương ứng trong trường hợp thông thường là:

```text
learning.actuator:type=Endpoint,name=Health
```

Đổi miền tên không đổi mã endpoint trong danh sách: vẫn dùng `health`. Nếu ứng dụng có nhiều ngữ cảnh Spring và gặp trùng tên, `spring.jmx.unique-names=true` là một cấu hình liên quan cần xem xét. [Tên MBean và miền JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

## 5. Thực hành hoàn chỉnh: in danh sách MBean được đăng ký

Ta sẽ cố định miền `learning.actuator`, truy vấn các MBean có `type=Endpoint`, lấy thuộc tính tên `name` rồi sắp xếp trước khi in. Phép kiểm tra này diễn ra trong chính tiến trình ứng dụng, không cần mở cổng JMX từ xa.

Dự án mẫu chỉ có Web và Actuator, không thêm Spring Security, exporter tùy biến hoặc nhiều ngữ cảnh Spring. Phần Web giữ ứng dụng chạy và cho phép đối chiếu rằng thay đổi JMX không tự thay đổi HTTP. Các đầu ra dưới đây là **kết quả mong đợi với đúng dự án mẫu**.

### 5.1. Các tệp cần có

```text
jmx-exposure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/JmxExposureApplication.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'jmx-exposure-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Tệp `src/main/java/example/JmxExposureApplication.java`:

```java
package example;

import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JmxExposureApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmxExposureApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectActuatorMBeans(ObjectProvider<MBeanServer> servers) {
        return args -> {
            MBeanServer server = servers.getIfAvailable();
            if (server == null) {
                System.out.println("ACTUATOR_MBEANS=<none>");
                return;
            }

            ObjectName pattern = new ObjectName(
                    "learning.actuator:type=Endpoint,*");
            Set<ObjectName> names = server.queryNames(pattern, null);

            String result = names.stream()
                    .map(name -> name.getKeyProperty("name"))
                    .sorted()
                    .collect(Collectors.joining(","));

            System.out.println("ACTUATOR_MBEANS="
                    + (result.isEmpty() ? "<none>" : result));
        };
    }
}
```

`MBeanServer.queryNames` trả về tập tên phù hợp với mẫu truy vấn. Mẫu `learning.actuator:type=Endpoint,*` giới hạn miền và loại MBean, đồng thời cho phép có thêm các thuộc tính tên khác. Mã dùng `sorted()` vì tập kết quả không bảo đảm thứ tự in mong muốn. [API truy vấn MBean của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html#queryNames(javax.management.ObjectName,javax.management.QueryExp))

`ObjectProvider` giúp chương trình vẫn khởi động khi cấu hình mẫu không cung cấp bean `MBeanServer`. Trong chương trình này, `<none>` có nghĩa không có tên endpoint phù hợp để báo cáo, hoặc không có bean máy chủ để truy vấn. Nó không có nghĩa toàn JVM không còn MBean.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087

spring.jmx.enabled=true
management.endpoints.jmx.domain=learning.actuator

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
management.endpoints.web.exposure.include=health
```

Mặc định chung được đặt thành tắt và chỉ bật rõ ba endpoint đang học. Vì thế ví dụ không phụ thuộc việc các endpoint khác mặc định bật hay tắt. Danh sách HTTP chỉ chứa `health`.

### 5.2. Biên dịch và chạy trường hợp A

Cần JDK 21, Gradle 8.5 và kết nối để tải phụ thuộc lần đầu. Tại thư mục dự án:

```powershell
gradle bootJar
java -jar build/libs/jmx-exposure-demo-1.0.0.jar
```

Nếu dự án đã có Gradle Wrapper 8.5, thay lệnh đầu bằng `.\gradlew.bat bootJar`. Mã có phụ thuộc Spring nên dùng Gradle để biên dịch và đóng gói, thay vì gọi `javac` một mình.

Trong stdout khi khởi động, dòng do chương trình mẫu in là:

```text
ACTUATOR_MBEANS=Health,Info
```

Lý do:

- Cả ba endpoint đã được bật rõ.
- `include` chọn cả ba mã.
- `exclude` loại `metrics`.
- Chương trình lấy phần `name` của MBean và sắp xếp, nên in `Health,Info`.

Phân biệt chữ hoa trong đầu ra với mã cấu hình: danh sách vẫn viết `health,info`, không đổi thành `Health,Info`.

### 5.3. Trường hợp B: chứng minh exclude ưu tiên

Dừng trường hợp A bằng `Ctrl+C`, rồi chạy lại cùng JAR:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoints.jmx.exposure.exclude=info
```

Tham số dòng lệnh thay giá trị danh sách `exclude` của lần chạy này thành chỉ `info`; nó không nối thêm `info` vào giá trị `metrics` trong tệp.

Đầu ra mong đợi:

```text
ACTUATOR_MBEANS=Health,Metrics
```

`info` vẫn có mặt trong `include` nhưng bị loại. `metrics` không còn trong danh sách loại trừ hiệu lực nên được công bố.

### 5.4. Trường hợp C: danh sách include thay cho mặc định hoặc danh sách cũ

Dừng trường hợp B rồi chạy:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoints.jmx.exposure.include=info
```

Lần chạy mới không kế thừa tham số dòng lệnh của lần chạy B. `exclude=metrics` trong tệp lại có hiệu lực; `include` của lần này chỉ là `info`.

Đầu ra mong đợi:

```text
ACTUATOR_MBEANS=Info
```

Không có `Health` trong dòng kết quả, vì `health` không nằm trong danh sách JMX hiệu lực. Điều đó không tắt endpoint `health` trên HTTP.

Trong cửa sổ PowerShell thứ hai:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/health
```

Với ứng dụng mẫu đang khỏe, đầu ra mong đợi là:

```text
200
```

Phép đối chiếu cho thấy hai kênh có lựa chọn công bố độc lập. Trạng thái sức khỏe thật sự vẫn có thể ảnh hưởng mã HTTP, nên không suy rộng `200` cho mọi môi trường.

### 5.5. Trường hợp D: loại tất cả khỏi JMX

Dừng trường hợp C rồi chạy:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar "--management.endpoints.jmx.exposure.exclude=*"
```

Đầu ra mong đợi:

```text
ACTUATOR_MBEANS=<none>
```

Ở đây `spring.jmx.enabled` vẫn là `true`. Kết quả rỗng do bộ chọn loại toàn bộ endpoint Actuator khỏi JMX. Gọi lại `/actuator/health` vẫn được xử lý qua HTTP trong điều kiện mẫu.

### 5.6. Trường hợp E: include không bật lại endpoint đã tắt

Dừng trường hợp D rồi chạy:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --management.endpoint.info.enabled=false
```

Lần này dùng lại các danh sách trong tệp: chọn `health,info,metrics`, loại `metrics`. Tuy nhiên `info` bị tắt ở cấp endpoint.

Đầu ra mong đợi:

```text
ACTUATOR_MBEANS=Health
```

`include` không ghi đè `enabled=false`.

### 5.7. Trường hợp F: tắt cơ chế JMX của Spring

Dừng trường hợp E rồi chạy:

```powershell
java -jar build/libs/jmx-exposure-demo-1.0.0.jar --spring.jmx.enabled=false
```

Trong dự án mẫu không có cấu hình máy chủ hoặc exporter khác, đầu ra mong đợi là:

```text
ACTUATOR_MBEANS=<none>
```

Việc các mã vẫn được khai báo trong `include` không tự bật lại hỗ trợ JMX.

### 5.8. Bảng kiểm chứng

Mỗi dòng là một lần khởi động mới, dùng tệp mẫu cộng với đúng tham số của trường hợp đó:

| Trường hợp | Thay đổi so với tệp mẫu | Dòng stdout mong đợi |
| --- | --- | --- |
| A | Không đổi | `ACTUATOR_MBEANS=Health,Info` |
| B | `exclude=info` | `ACTUATOR_MBEANS=Health,Metrics` |
| C | `include=info` | `ACTUATOR_MBEANS=Info` |
| D | `exclude=*` | `ACTUATOR_MBEANS=<none>` |
| E | `info.enabled=false` | `ACTUATOR_MBEANS=Health` |
| F | `spring.jmx.enabled=false` | `ACTUATOR_MBEANS=<none>` |

Các tên trong bảng chỉ là kết quả truy vấn miền Actuator của ví dụ; không phải danh sách toàn bộ MBean của JVM.

## 6. Kiểm tra bằng công cụ JMX và hiểu giới hạn của exposure

Nếu có JConsole trong JDK, có thể mở `jconsole`, kết nối tới tiến trình Java cục bộ của dự án mẫu rồi tìm miền `learning.actuator` trong phần MBeans. Chọn đúng tiến trình đang chạy và bảo đảm quyền truy cập cục bộ phù hợp; thông thường công cụ và ứng dụng cần chạy dưới cùng tài khoản hệ điều hành.

Sau mỗi lần khởi động lại ứng dụng, cần kết nối lại đúng tiến trình. Nếu không tìm thấy tiến trình do môi trường không hỗ trợ attach, phép truy vấn trong `ApplicationRunner` vẫn là cách quan sát của bài. [Giám sát JMX cục bộ với Java 21](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html)

Hai phạm vi cần hiểu đúng:

1. `spring.jmx.enabled=true` và các danh sách Actuator phục vụ việc đăng ký/công bố MBean của Spring. Chúng không tự cấu hình đầy đủ một kết nối JMX từ xa; phía JVM có thiết lập quản trị từ xa riêng.
2. `include` và `exclude` chọn endpoint, không phải danh sách người dùng được phép gọi. Nếu dùng kết nối JMX từ xa, cơ chế xác thực, phân quyền và bảo vệ kết nối thuộc cấu hình JMX tương ứng. Quy tắc HTTP trong `SecurityFilterChain` không tự bảo vệ một kết nối JMX riêng.

Không cần mở cổng quản trị từ xa để hoàn thành các thí nghiệm trong bài.

## 7. Chẩn đoán khi danh sách quan sát khác dự kiến

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Không thấy MBean Actuator nào | `spring.jmx.enabled`, miền truy vấn, tiến trình đang kết nối và `exclude=*` |
| Thiếu một endpoint đã include | Có bị exclude không; endpoint có bật và đủ thư viện/bean cần thiết không |
| Vẫn thấy MBean `java.lang` sau khi exclude tất cả | Đó là miền khác; danh sách này chỉ điều khiển endpoint Actuator qua JMX |
| Endpoint có trên HTTP nhưng không có trên JMX | So sánh hai danh sách công bố độc lập |
| Không thấy `health` sau khi include chỉ `info` | Danh sách hiệu lực đã thay lựa chọn mặc định |
| Danh sách trong tệp đúng nhưng kết quả khác | Kiểm tra profile, tham số dòng lệnh và nguồn cấu hình ghi đè |
| Có lỗi trùng tên MBean | Kiểm tra nhiều ngữ cảnh, miền tên và cấu hình tên duy nhất |

Một thuộc tính có thể được cung cấp từ tệp, biến môi trường hoặc dòng lệnh. Chẳng hạn, biến môi trường cho danh sách chọn là `MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE`. Với cách khởi động chuẩn, tham số `--management.endpoints.jmx.exposure.include=info` ghi đè giá trị cùng khóa trong tệp. Cần xem **danh sách có hiệu lực**, không chỉ văn bản trong một tệp. [Nguồn và thứ tự ưu tiên cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

Việc đổi tệp của một ứng dụng Spring Boot thông thường không tự làm mới ngay tập MBean đang đăng ký. Trong các thí nghiệm này, luôn dừng tiến trình và khởi động lại với cấu hình mới.

Ngoài ra, một endpoint chỉ được loại khỏi JMX vẫn có thể được tạo để phục vụ kênh khác. Nếu nó không được công bố ở bất kỳ kênh phù hợp nào, điều kiện tự cấu hình cũng có thể không thỏa mãn. Vì vậy không suy ra “bean chắc chắn còn” hoặc “bean chắc chắn mất” chỉ từ một danh sách JMX.

## 8. Bài tập tự kiểm tra

Dùng dự án mẫu và dự đoán trước khi chạy:

1. Đổi `include` thành `health,info`, `exclude` thành `health`. Những tên nào còn trong dòng stdout?
2. Đặt `include=*`, giữ mặc định chung tắt và chỉ bật ba endpoint mẫu. Vì sao dấu sao không tạo thêm endpoint khác?
3. Giữ `include=health,info,metrics` nhưng tắt `info` và loại `metrics`. Phân biệt hai lý do khiến hai tên này vắng mặt.
4. Đặt `exclude=*` cho JMX rồi kiểm tra lại URL `health`. Giải thích vì sao kết quả hai kênh khác nhau.
5. Đổi miền Actuator thành `study.actuator` nhưng chưa sửa mẫu truy vấn Java. Vì sao kết quả truy vấn cũ có thể rỗng dù MBean vẫn được đăng ký ở miền mới?

Đáp án ngắn cho câu 1 là `Info`. Với câu 2, chỉ endpoint đã bật, tương thích JMX và đủ điều kiện mới có thể được chọn. Câu 3 có hai nguyên nhân riêng: `info` bị tắt ở cấp endpoint, còn `metrics` bị loại khỏi kênh JMX. Câu 4 cần đối chiếu danh sách `web` và `jmx`. Câu 5 yêu cầu cập nhật miền của `ObjectName` hoặc tìm đúng miền trong công cụ quản trị.
