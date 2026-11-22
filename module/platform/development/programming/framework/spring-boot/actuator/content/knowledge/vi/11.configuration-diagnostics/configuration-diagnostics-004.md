# Phân biệt cấu hình đã khai báo với giá trị thực tế đã được liên kết

Trong một ứng dụng Spring Boot, dòng `timeout: 1s` trong YAML chỉ cho biết một nơi đã khai báo cấu hình. Nó chưa đủ để kết luận đối tượng Java đang giữ giá trị nào, và càng chưa đủ để kết luận thư viện thực hiện mỗi yêu cầu với thời gian chờ bao nhiêu.

Để chẩn đoán đúng, cần lần theo đường đi của một thuộc tính: **nơi khai báo → giá trị được chọn trong môi trường cấu hình → giá trị đã liên kết vào đối tượng Java → cách thành phần sử dụng đối tượng đó**. Trong bài này, “liên kết” (binding) là quá trình Spring Boot lấy thuộc tính cấu hình và chuyển chúng thành dữ liệu của đối tượng, thường thông qua `@ConfigurationProperties`.

Bài tập trung vào cách dùng Actuator để phân biệt các lớp bằng chứng này trong Spring Boot 3.3.x. Ví dụ chạy độc lập sử dụng Java 21 và Spring Boot 3.3.13.

## 1. Bốn câu hỏi cần tách riêng

Giả sử tệp `application.yml` có:

```yaml
demo:
  client:
    timeout: 1s
```

Khi triển khai, tiến trình lại được khởi động với:

```text
--demo.client.timeout=5s
```

Một lớp cấu hình khai báo trường kiểu `Duration`. Lúc này các phát biểu sau có thể đồng thời đúng:

| Lớp cần quan sát | Câu hỏi | Kết quả trong tình huống này |
| --- | --- | --- |
| Khai báo ở nguồn | Trong tệp YAML đã viết gì? | `1s` |
| Môi trường cấu hình `Environment` | Với khóa đó, ứng dụng đang phân giải ra giá trị nào? | Chuỗi `5s`, do đối số dòng lệnh ghi đè |
| Đối tượng đã liên kết | Trường kiểu `Duration` đang chứa gì? | `Duration` bằng 5 giây, có thể biểu diễn thành `PT5S` |
| Thành phần thực thi | Máy khách HTTP có thực sự dùng giá trị này không? | Cần kiểm tra chỗ xây dựng máy khách và hành vi thực tế |

Sự khác nhau giữa `1s` và `5s` liên quan đến **nguồn và độ ưu tiên**. Sự khác nhau giữa `5s` và `PT5S` liên quan đến **kiểu dữ liệu và cách biểu diễn**. Một máy khách vẫn dùng thời gian chờ cũ dù đối tượng cấu hình đã đúng lại là vấn đề **áp dụng cấu hình tại nơi sử dụng**.

Đừng gom ba trường hợp này thành kết luận chung “Spring không nhận cấu hình”.

## 2. Vì sao chỉ mở YAML chưa đủ?

Một khóa có thể được khai báo ở nhiều nơi: cấu hình đóng gói trong JAR, tệp bên ngoài, cấu hình theo profile, biến môi trường, thuộc tính hệ thống JVM và đối số dòng lệnh.

Trong một lần chạy thông thường của ví dụ này, khi cùng một khóa xuất hiện ở cả ba nguồn sau, thứ tự ưu tiên từ cao xuống thấp là:

```text
Đối số dòng lệnh > biến môi trường > application.yml đóng gói
```

Đây là phần thứ tự cần dùng cho thí nghiệm, không phải toàn bộ danh sách nguồn của Spring Boot. Các nguồn phục vụ kiểm thử hoặc cơ chế tùy chỉnh còn có quy tắc riêng.

Một giá trị viết trong `application-prod.yml` cũng không có tác dụng chỉ vì tệp tồn tại: profile tương ứng phải được kích hoạt và tệp phải được nạp vào đúng tiến trình. Sửa bản YAML trong thư mục mã nguồn không chứng minh JAR đang chạy đã chứa bản sửa đó.

Với thuộc tính scalar như `demo.client.timeout`, Spring chọn đầu vào theo độ ưu tiên rồi chuyển kiểu khi liên kết. Nếu đầu vào có độ ưu tiên cao nhất là một chuỗi sai định dạng, không nên kỳ vọng Spring bỏ qua nó để lấy giá trị hợp lệ từ nguồn thấp hơn.

Tham chiếu về nguồn, thứ tự ưu tiên và liên kết: [Externalized Configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

## 3. `env` và `configprops` trả lời hai câu hỏi khác nhau

### 3.1. `env`: nguồn cấu hình và giá trị được phân giải

Hai đường dẫn hữu ích:

```text
GET /actuator/env
GET /actuator/env/demo.client.timeout
```

Truy vấn một khóa giúp tập trung vào thông tin đang cần chẩn đoán. Với phản hồi cho một thuộc tính:

- `property.value` cho biết giá trị được phân giải.
- `property.source` cho biết nguồn được chọn.
- `propertySources` cho biết các nguồn theo thứ tự ưu tiên; một nguồn có thể không chứa khóa đang hỏi.
- `origin`, khi được cung cấp, giúp lần về tệp và vị trí khai báo.

Một giá trị ưu tiên thấp vẫn có thể xuất hiện trong danh sách nguồn. Việc nhìn thấy `1s` ở một nguồn YAML không có nghĩa nó đang thắng đối số `5s`.

`env` không đọc trường `timeout` từ đối tượng Java. Nó cũng không chứng minh thuộc tính tùy ý nào cũng đã được một bean sử dụng. Đầu vào trong `Environment` có thể là chuỗi hoặc kiểu do nguồn cung cấp; đừng coi toàn bộ phản hồi là đối tượng cấu hình đã chuyển kiểu.

Cấu trúc chính thức: [Environment endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 3.2. `configprops`: đối tượng `@ConfigurationProperties`

Hai đường dẫn tương ứng:

```text
GET /actuator/configprops
GET /actuator/configprops/demo.client
```

Trong phản hồi, tìm trong `contexts → <context-id> → beans → <bean-name>` đối tượng có `prefix = demo.client`. Không giả định tên context hoặc tên bean luôn giống một JSON chụp từ ứng dụng khác.

Các trường cần đối chiếu:

| Trường | Ý nghĩa khi chẩn đoán |
| --- | --- |
| `prefix` | Tiền tố cấu hình của đối tượng |
| `properties` | Giá trị của các thuộc tính trên bean được báo cáo |
| `inputs` | Giá trị đầu vào và nguồn gốc được ghi nhận khi liên kết, nếu có |

Ví dụ, `properties.timeout` có thể biểu diễn giá trị `Duration`, trong khi `inputs.timeout.value` vẫn thể hiện đầu vào `5s`. Với một giá trị mặc định trong mã, bean có thể có giá trị nhưng không có đầu vào bên ngoài tương ứng trong `inputs`.

`configprops` không phải danh sách toàn bộ biến trong ứng dụng. Một trường chỉ nhận `@Value`, một thuộc tính chỉ đọc bằng `Environment`, hoặc cấu hình nội bộ của thư viện không tự trở thành bean `@ConfigurationProperties` để xuất hiện ở đây. Phản hồi cũng không phải bản ghi đầy đủ mọi lần thay đổi cấu hình trong quá khứ.

Cấu trúc chính thức: [Configuration Properties endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

## 4. Thí nghiệm chạy độc lập

Thí nghiệm có hai thuộc tính:

- `timeout`: có giá trị YAML là `1s`, có thể bị ghi đè; kiểu Java là `Duration`.
- `maxAttempts`: mặc định bằng `3` tại tham số khởi tạo; YAML không khai báo khóa tương ứng.

Nhờ vậy có thể quan sát cả **giá trị đã bị ghi đè** lẫn **giá trị tồn tại trên bean dù không có khóa bên ngoài**.

### 4.1. Cấu trúc dự án

Tạo một thư mục riêng với cấu trúc:

```text
actuator-binding-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── DemoApplication.java
        └── resources/
            └── application.yml
```

Dùng JDK 21 và Maven 3.6.3 trở lên. Lệnh đóng gói lần đầu cần truy cập kho Maven để tải phụ thuộc.

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>learning</groupId>
    <artifactId>actuator-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
```

Ví dụ không thêm Spring Security để tập trung vào bằng chứng cấu hình. Máy chủ chỉ lắng nghe địa chỉ loopback trong cấu hình bên dưới.

### 4.3. `src/main/java/learning/actuator/DemoApplication.java`

```java
package learning.actuator;

import java.time.Duration;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(DemoApplication.DemoClientProperties.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printConfiguration(
            Environment environment,
            DemoClientProperties properties) {
        return args -> {
            System.out.println("DEMO env.timeout="
                    + environment.getProperty("demo.client.timeout"));
            System.out.println("DEMO bound.timeout=" + properties.timeout());
            System.out.println("DEMO bound.timeoutMillis="
                    + properties.timeout().toMillis());
            System.out.println("DEMO env.max-attempts="
                    + environment.getProperty("demo.client.max-attempts"));
            System.out.println("DEMO bound.maxAttempts="
                    + properties.maxAttempts());
        };
    }

    @ConfigurationProperties(prefix = "demo.client")
    public record DemoClientProperties(
            @DefaultValue("2s") Duration timeout,
            @DefaultValue("3") int maxAttempts) {
    }
}
```

`@EnableConfigurationProperties` đăng ký record làm bean cấu hình. Với record một hàm khởi tạo này, Spring Boot dùng liên kết qua hàm khởi tạo; không cần thêm `@Component`, setter hay `@ConstructorBinding`.

`@DefaultValue` cung cấp giá trị khi thiếu thuộc tính cần liên kết. Mặc định `2s` thuộc quá trình tạo đối tượng cấu hình, không phải thao tác thêm khóa `demo.client.timeout` vào `Environment`. Vì vậy một lệnh đọc `Environment` không tự nhìn thấy mặc định này.

`ApplicationRunner` đọc trực tiếp cả `Environment` và bean để tạo bằng chứng dễ kiểm tra. Đây là mã in giá trị demo không nhạy cảm; không áp dụng cách in toàn bộ cấu hình vào log của hệ thống thật.

### 4.4. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18080

spring:
  application:
    name: actuator-binding-demo

demo:
  client:
    timeout: 1s

management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: always
```

`exposure.include` làm các endpoint có thể truy cập qua HTTP; `show-values` điều khiển việc hiển thị giá trị trong phản hồi. Hai thiết lập có chức năng khác nhau.

Ở đây dùng `always` trên máy cá nhân để quan sát dữ liệu demo và giới hạn máy chủ ở `127.0.0.1`. Trên hệ thống thật, cần bảo vệ quyền truy cập và chọn chính sách hiển thị phù hợp. Nếu có `SanitizingFunction` tùy chỉnh, giá trị vẫn có thể bị che.

### 4.5. Biên dịch và chạy lần đầu

Tại thư mục chứa `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-binding-demo-1.0.0.jar
```

Đảm bảo không có biến môi trường, thuộc tính JVM hoặc tệp cấu hình bên ngoài khác ghi đè nhóm `demo.client`. Nếu cổng `18080` đang được dùng, chọn một cổng khác bằng `--server.port=<port>` và đổi URL khi gọi endpoint.

Ngoài log khởi động của Spring Boot, chương trình in chính xác năm dòng bắt đầu bằng `DEMO`:

```text
DEMO env.timeout=1s
DEMO bound.timeout=PT1S
DEMO bound.timeoutMillis=1000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

Ý nghĩa:

1. YAML cung cấp `1s`, nên lệnh đọc môi trường trả về chuỗi đó.
2. Bean nhận `Duration` một giây; `Duration.toString()` biểu diễn nó thành `PT1S`.
3. `toMillis()` xác nhận ý nghĩa thời gian là `1000` mili giây.
4. Khóa `demo.client.max-attempts` không có trong các nguồn của thí nghiệm, nên lệnh đọc môi trường trả về `null`.
5. Record vẫn nhận số nguyên `3` từ `@DefaultValue`.

Giá trị `null` ở dòng thứ tư không chứng minh bean thiếu cấu hình. Nó chỉ cho biết phép tra cứu khóa đó trong môi trường không tìm thấy giá trị.

## 5. Dùng Actuator đối chiếu với bean

Trong cửa sổ terminal thứ hai:

```shell
curl "http://127.0.0.1:18080/actuator/env/demo.client.timeout"
curl "http://127.0.0.1:18080/actuator/configprops/demo.client"
```

Trên Windows PowerShell, dùng `curl.exe` thay cho `curl` nếu tên `curl` đang là bí danh của lệnh PowerShell.

Với lần chạy mặc định:

- `env` cho biết giá trị được chọn là `1s`; kiểm tra nguồn gốc để thấy nó đến từ cấu hình YAML.
- `configprops` có bean với `prefix = demo.client`; các thuộc tính trên bean phản ánh thời gian chờ một giây và số lần thử bằng ba.
- `inputs.timeout` giúp truy ngược đầu vào đã dùng. Đối với mặc định `maxAttempts`, không kỳ vọng có một đầu vào YAML chứa số `3`.

Không đối chiếu JSON bằng cách so sánh nguyên văn với log. Một bên là chuỗi nguồn, một bên là giá trị đã chuyển kiểu được endpoint tuần tự hóa. Cách biểu diễn kiểu thời gian, tên bean, tên nguồn, context và vị trí dòng phụ thuộc phản hồi thực tế. Hãy đối chiếu **đúng thuộc tính, đúng kiểu và cùng ý nghĩa giá trị**.

Nếu endpoint không trả được giá trị rõ ràng, chưa có đủ bằng chứng để kết luận hai phía khác nhau. Chuỗi `******` biểu thị dữ liệu bị che, không phải giá trị bí mật đã được liên kết thành sáu dấu sao.

## 6. Ghi đè bằng dòng lệnh: YAML giữ nguyên, bean thay đổi

Dừng tiến trình trước bằng `Ctrl+C`, rồi khởi động lại:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=5s
```

Năm dòng `DEMO` lúc này là:

```text
DEMO env.timeout=5s
DEMO bound.timeout=PT5S
DEMO bound.timeoutMillis=5000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

Gọi lại hai endpoint ở phần trước. Khi đối chiếu:

| Bằng chứng | Điều cần tìm |
| --- | --- |
| Tệp YAML | Vẫn khai báo `1s` |
| `env/demo.client.timeout` | Giá trị được chọn là `5s`, đến từ đối số dòng lệnh |
| Danh sách nguồn trong `env` | Có thể vẫn thấy nguồn YAML chứa `1s` với ưu tiên thấp hơn |
| `configprops/demo.client` | Bean phản ánh thời gian chờ năm giây |
| Log đọc bean | `PT5S` và `5000` mili giây |

Đây là một kết quả liên kết đúng. YAML không bị sửa; đầu vào có ưu tiên cao hơn đã thắng.

Trong lần chạy này, phần đối tượng mang prefix `demo.client` có dạng sau; đã bỏ các lớp bao `contexts` và `beans` để tập trung vào dữ liệu cần đọc:

```json
{
  "prefix": "demo.client",
  "properties": {
    "maxAttempts": 3,
    "timeout": "PT5S"
  },
  "inputs": {
    "maxAttempts": {},
    "timeout": {
      "value": "5s",
      "origin": "\"demo.client.timeout\" from property source \"commandLineArgs\""
    }
  }
}
```

`properties.timeout` là giá trị trên bean, còn `inputs.timeout.value` là đầu vào đã dùng. Đối tượng rỗng tại `inputs.maxAttempts` đi cùng giá trị bean bằng `3`, vì thuộc tính này dùng mặc định trong mã.

Có thể đổi cả hai thuộc tính trong cùng lần khởi động:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=5s --demo.client.max-attempts=7
```

Hai dòng cuối sẽ là:

```text
DEMO env.max-attempts=7
DEMO bound.maxAttempts=7
```

Tên khóa `max-attempts` và thành phần record `maxAttempts` khác hình thức nhưng liên kết được nhờ quy tắc tên linh hoạt (relaxed binding). Khi viết khóa trong tệp hoặc đối số, ưu tiên dạng chuẩn chữ thường và dấu gạch nối. Không suy luận rằng mọi phép thay dấu hoặc đổi tên đều được hỗ trợ ở mọi API đọc cấu hình.

## 7. Hai thí nghiệm giúp tránh kết luận sai

### 7.1. Có giá trị trên bean dù không có khóa bên ngoài

Dừng tiến trình. Xóa riêng khối:

```yaml
demo:
  client:
    timeout: 1s
```

Giữ các phần cấu hình còn lại, đóng gói lại bằng `mvn clean package`, rồi chạy JAR mà không truyền đối số `demo.client.*`.

Năm dòng kết quả là:

```text
DEMO env.timeout=null
DEMO bound.timeout=PT2S
DEMO bound.timeoutMillis=2000
DEMO env.max-attempts=null
DEMO bound.maxAttempts=3
```

Đối tượng lấy mặc định `2s` và `3` trong mã. Khóa không xuất hiện trong `Environment` vẫn có thể đi cùng một thuộc tính bean có giá trị hợp lệ. Khi tra khóa không tồn tại qua endpoint `env`, không kỳ vọng một mục chứa mặc định chỉ được khai báo bằng `@DefaultValue`.

Khôi phục khối YAML và đóng gói lại trước khi làm thí nghiệm tiếp theo nếu muốn trở về cấu hình ban đầu.

### 7.2. Có khóa trong môi trường chưa có nghĩa là liên kết thành công

Dừng tiến trình rồi chạy:

```shell
java -jar target/actuator-binding-demo-1.0.0.jar --demo.client.timeout=abc
```

`abc` không chuyển được thành `Duration` của ví dụ. Với thiết lập mặc định này, tạo bean cấu hình thất bại và ứng dụng không khởi động thành công. Không có năm dòng `DEMO` từ runner vì runner chỉ chạy sau khi context đã được tạo thành công.

Đừng kỳ vọng YAML `1s` hay `@DefaultValue("2s")` tự cứu đầu vào sai định dạng có ưu tiên cao hơn. Mặc định dành cho trường hợp thiếu đầu vào không đồng nghĩa với cơ chế bỏ qua mọi dữ liệu lỗi.

Khi ứng dụng thất bại ở giai đoạn này, chẩn đoán bằng lỗi khởi động và nguyên nhân lồng nhau của quá trình liên kết. Một endpoint Actuator của ứng dụng chưa khởi động thành công không phải nguồn quan sát có thể dựa vào. Nội dung đầy đủ của thông báo lỗi có thể thay đổi theo phiên bản; cần xác định khóa `demo.client.timeout`, kiểu đích `Duration` và đầu vào gây lỗi.

## 8. Quy trình chẩn đoán trong ứng dụng thật

### Bước 1: Xác định đúng tiến trình và thuộc tính

Ghi lại phiên bản JAR, môi trường triển khai, profile đang hoạt động, tên khóa chuẩn, prefix, kiểu Java và bean dự kiến nhận cấu hình. Nếu có nhiều bản sao ứng dụng, bảo đảm các lần quan sát hướng đến cùng một bản sao.

Cùng URL qua bộ cân bằng tải chưa bảo đảm hai lần gọi đã vào cùng tiến trình. Đối chiếu một phản hồi `env` của bản sao A với `configprops` của bản sao B có thể tạo ra chênh lệch không liên quan đến liên kết.

### Bước 2: Kiểm tra giá trị môi trường và nguồn thắng

Gọi `env/<property.name>`, tìm nguồn được chọn và nguồn gốc nếu có. Nếu khác YAML dự kiến, kiểm tra đối số khởi động, biến môi trường, profile và tệp ngoài trước.

Một khóa sai chính tả vẫn có thể tồn tại trong môi trường nhưng không khớp thuộc tính nào của lớp cấu hình. Sự hiện diện của khóa không chứng minh có nơi tiêu thụ nó.

### Bước 3: Kiểm tra đúng bean cấu hình

Gọi `configprops/<prefix>`, tìm đúng context và bean. Đối chiếu `properties` với `inputs`, kiểu đích và mặc định trong mã.

Nếu không thấy bean, kiểm tra nó đã được đăng ký bằng `@EnableConfigurationProperties` hoặc quét bằng `@ConfigurationPropertiesScan` chưa; sau đó kiểm tra prefix và cách ứng dụng thật nhận dữ liệu. Đừng vội đổi giá trị YAML khi vấn đề nằm ở việc chưa có bean cần liên kết.

### Bước 4: So sánh theo ý nghĩa, không chỉ theo chuỗi

`5000ms`, `5s` và `PT5S` đều có thể biểu thị cùng một `Duration`. Với một trường `Duration` không có `@DurationUnit`, số trần như `5000` mặc định được hiểu theo mili giây; với trường `int` thì số đó chỉ là số nguyên, không tự mang ý nghĩa thời gian.

Luôn đọc kiểu đích và quy tắc đơn vị. Không áp dụng quy tắc của `Duration` cho tất cả thuộc tính chứa chữ “timeout”.

### Bước 5: Lần đến nơi sử dụng cấu hình

Ví dụ mã rút gọn sau cho thấy một nguyên nhân thường gặp:

```java
// Minh họa tại nơi xây dựng máy khách; không phải chương trình độc lập.
var client = java.net.http.HttpClient.newBuilder()
        .connectTimeout(java.time.Duration.ofSeconds(1))
        .build();
```

Dù bean đã liên kết thành năm giây, đoạn mã trên vẫn truyền một giây vào bộ dựng. Actuator phản ánh đúng bean nhưng chưa chứng minh thư viện đang dùng bean đó.

Cần kiểm tra giá trị thực sự được truyền vào API, thời điểm tạo máy khách và ý nghĩa thuộc tính. Chẳng hạn, thời gian chờ kết nối không đồng nghĩa với giới hạn tổng thời gian của một yêu cầu. Nếu bean có nhiều bản hoặc thành phần giữ bản sao giá trị, phải xác định đúng đối tượng được sử dụng.

Một phép đo thời gian đơn lẻ cũng chịu ảnh hưởng của mạng, thử lại và nhiều giới hạn khác. Dùng bằng chứng tại nơi cấu hình thành phần cùng thí nghiệm hành vi phù hợp, thay vì quy mọi độ trễ về một khóa.

## 9. Những giới hạn cần nhớ khi đọc bằng chứng

| Hiện tượng | Điều có thể kết luận | Việc cần kiểm tra thêm |
| --- | --- | --- |
| YAML có khóa nhưng `env` trả giá trị khác | Giá trị trong tệp đó không phải giá trị đang được phân giải | Nguồn thắng, profile, JAR và bản sao ứng dụng |
| `env` có giá trị, `configprops` không có bean mong đợi | Chưa quan sát được bean `@ConfigurationProperties` cần tìm | Đăng ký bean, prefix, context, cơ chế `@Value` hoặc đọc trực tiếp |
| `env` không có khóa, bean vẫn có giá trị | Có thể có mặc định tại lớp cấu hình | Tham số khởi tạo hoặc giá trị khởi tạo trường |
| Nguồn ghi `5s`, bean biểu diễn `PT5S` | Có thể cùng một giá trị sau chuyển kiểu | Kiểu dữ liệu và đơn vị |
| Giá trị hiển thị `******` | Dữ liệu quan sát đã bị che | Chính sách hiển thị và quyền truy cập |
| Bean đúng nhưng hành vi chưa đúng | Liên kết chưa đủ để chứng minh việc áp dụng | Nơi sử dụng, giá trị cố định, bản sao, thời điểm tạo thành phần |
| Không thể truy cập endpoint | Chưa quan sát được dữ liệu qua HTTP | Exposure, base path, cổng quản trị, xác thực và trạng thái khởi động |

Thêm hai giới hạn về thời điểm:

- Chỉnh tệp cấu hình sau khi ứng dụng đã chạy không mặc nhiên nạp lại `Environment`, liên kết lại bean hoặc tạo lại máy khách. Spring Boot thuần trong ví dụ này không cung cấp cơ chế tự cập nhật toàn bộ chuỗi đó.
- Nếu ứng dụng bổ sung cơ chế cập nhật cấu hình động, giá trị môi trường hiện tại và bean từng được tạo trước đó có thể thuộc các thời điểm khác nhau. Cần kiểm tra quy tắc cập nhật của cơ chế cụ thể. Các lệnh `GET` Actuator đang dùng ở bài này là thao tác đọc, không phải lệnh áp dụng lại cấu hình.

Đối với thuộc tính do thư viện sử dụng, cũng cần kiểm tra điều kiện tạo bean: cấu hình liên kết đúng không đồng nghĩa một auto-configuration đã được áp dụng hoặc bean tự động đó đang được chọn thay cho bean do ứng dụng tự định nghĩa.

Theo [quy tắc che giá trị của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization), giá trị mặc định bị che; `show-values` và quyền xem phải được xem xét riêng với việc cho phép truy cập endpoint. Không bật hiển thị rộng chỉ để xử lý một lần chẩn đoán trên môi trường công khai.

## 10. Tự kiểm tra bằng bằng chứng

Thực hiện các lần chạy sau, mỗi lần dừng tiến trình trước rồi mới chạy lần kế tiếp:

1. YAML `1s`, không truyền đối số: dự đoán `Environment`, `Duration` và số mili giây.
2. Giữ YAML, thêm `--demo.client.timeout=2500ms`: giải thích vì sao YAML vẫn ghi `1s` nhưng bean mang thời gian hai giây rưỡi.
3. Không khai báo `max-attempts`: giải thích vì sao log môi trường in `null` nhưng bean trả về `3`.
4. Thêm `--demo.client.max-attempts=7`: xác định đầu vào nào thay mặc định.
5. Truyền `--demo.client.timeout=abc`: dự đoán giai đoạn thất bại và chọn nguồn bằng chứng phù hợp.

Đáp án cốt lõi: lần 1 là `1s → PT1S → 1000`; lần 2 là `2500ms → PT2.5S → 2500`; lần 3 dùng mặc định của record; lần 4 dùng đối số có giá trị `7`; lần 5 thất bại khi liên kết sang `Duration`.

Sau mỗi lần chạy thành công, đối chiếu `env`, `configprops` và log đọc bean. Khi phát biểu “ứng dụng đã nhận cấu hình”, hãy nói rõ đang chứng minh **nguồn nào được chọn**, **bean nào đã nhận giá trị**, hay **thành phần nào đã sử dụng giá trị đó**.
