# Bật hoặc tắt từng indicator và các indicator mặc định

## 1. Ta đang bật hoặc tắt điều gì?

Một `HealthIndicator` là một phép kiểm tra trả về thông tin sức khỏe, chẳng hạn dung lượng đĩa còn đủ hay có lấy được kết nối cơ sở dữ liệu hay không. Spring Boot Actuator có thể tự tạo các indicator khi ứng dụng đáp ứng điều kiện cấu hình.

Khi yêu cầu “tắt kiểm tra cơ sở dữ liệu”, cần xác định đúng ý định:

- Không đăng ký phép kiểm tra cơ sở dữ liệu vào tập health tự cấu hình.
- Giữ phép kiểm tra nhưng không đưa nó vào một nhóm health cụ thể.
- Vẫn tính kết quả nhưng không công khai chi tiết cho người gọi.
- Không cho truy cập endpoint health qua HTTP.

Đó là các thao tác khác nhau. Bài này tập trung vào **điều kiện tạo và đăng ký indicator**, đặc biệt là hai dạng cấu hình:

```properties
management.health.<key>.enabled=true
management.health.defaults.enabled=false
```

`<key>` là chỗ biểu diễn tên khóa cần thay bằng một tên thật như `db`, `diskspace` hoặc `ping`; không chép nguyên dấu `<...>` vào tệp cấu hình.

Ví dụ và chương trình đối chiếu dùng **Spring Boot 3.3.0, JDK 21**. Những tên lớp/gói và nhận xét về probes trong bài thuộc nhánh **3.3.x**; khi chuyển nhánh phiên bản, cần đối chiếu lại cấu hình tương ứng.

### 1.1. Vì sao phải chọn tập phép kiểm tra?

Giả sử ứng dụng có cơ sở dữ liệu dùng cho tính năng phụ. Khi dịch vụ cơ sở dữ liệu gặp lỗi, indicator của nó có thể làm health tổng báo lỗi. Trước khi bỏ phép kiểm tra, cần trả lời: ứng dụng có còn thực hiện được chức năng mà người dùng đang cần hay không?

Một cấu hình tốt thể hiện rõ những điều kiện nào được theo dõi. Nếu chỉ muốn một nhóm phục vụ định tuyến bỏ qua một phụ thuộc, nên xem xét thành viên của nhóm đó trước khi tắt phép kiểm tra trên toàn ứng dụng. Ngược lại, nếu một phép kiểm tra tự cấu hình không phù hợp với môi trường đang chạy, có thể tắt riêng nó.

Tắt một indicator **không sửa chữa tài nguyên bị lỗi**, không biến kết quả của nó thành `UP` và không dừng tài nguyên bên dưới. Chẳng hạn, `management.health.db.enabled=false` không có nghĩa là bean `DataSource` bị tắt.

## 2. Khóa bật/tắt, tên bean và tên thành phần

### 2.1. Dùng đúng khóa được Spring Boot hỗ trợ

Một số ví dụ trong Spring Boot 3.3:

| Khóa cấu hình | Ý nghĩa phép kiểm tra | Điều kiện thực tế cần có |
| --- | --- | --- |
| `diskspace` | Dung lượng đĩa | Cấu hình kiểm tra dung lượng đĩa |
| `ping` | Trả trạng thái `UP` | Không cần kết nối đến dịch vụ ngoài |
| `db` | Lấy kết nối JDBC | Có `DataSource` phù hợp |
| `redis` | Kết nối Redis | Có các kiểu thư viện và bean kết nối phù hợp |
| `rabbit` | Kết nối RabbitMQ | Có hạ tầng kết nối tương ứng |
| `mail` | Kết nối máy chủ thư | Có cấu hình gửi thư phù hợp |

Các khóa này được liệt kê trong [tài liệu health của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.auto-configured-health-indicators).

Không suy luận rằng thêm dòng `management.health.redis.enabled=true` sẽ tự tạo Redis, tự cài thư viện hoặc tự bổ sung cấu hình kết nối. Công tắc này chỉ là một điều kiện; cấu hình tự động còn có các điều kiện về lớp, bean và tài nguyên.

`ping` cũng không chứng minh mọi chức năng nghiệp vụ hoạt động. Một endpoint chỉ còn `ping` có thể vẫn báo `UP` dù ứng dụng chưa kiểm tra bất kỳ phụ thuộc quan trọng nào.

### 2.2. Phân biệt ba tên của disk space

| Nơi dùng | Tên trong ví dụ Spring Boot 3.3 |
| --- | --- |
| Khóa bật/tắt | `management.health.diskspace.enabled` |
| Bean do cấu hình tự động tạo | `diskSpaceHealthIndicator` |
| ID thành phần trong registry/JSON/nhóm | `diskSpace` |

Trong mã nguồn, cấu hình dung lượng đĩa gắn điều kiện `@ConditionalOnEnabledHealthIndicator("diskspace")` và tạo bean tên `diskSpaceHealthIndicator` khi chưa có bean trùng tên. Đó là lý do cần dùng đúng khóa cấu hình thay vì tự ghép tên bean thành một property. [DiskSpaceHealthContributorAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/system/DiskSpaceHealthContributorAutoConfiguration.java)

Với bean tự khai báo `catalogHealthIndicator`, ID thông thường là `catalog`. Tuy nhiên, việc có ID `catalog` **không tự làm phát sinh** cơ chế đọc `management.health.catalog.enabled`; bean phải có điều kiện sử dụng khóa đó.

## 3. Cơ chế ưu tiên: cấu hình riêng trước, mặc định chung sau

Với indicator dùng `@ConditionalOnEnabledHealthIndicator("key")`, có thể đọc quy tắc như sau:

```text
Có management.health.key.enabled?
    Có  -> dùng giá trị riêng đó.
    Không -> dùng management.health.defaults.enabled nếu có.
             Nếu cũng không có -> mặc định cho phép.
```

Điều kiện này là một phần trong cơ chế cấu hình tự động, không phải một bộ lọc xóa mọi bean health sau khi chúng đã được tạo. Lớp điều kiện của Spring Boot dùng tiền tố `management.health.` để xét indicator. [OnEnabledHealthIndicatorCondition 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/OnEnabledHealthIndicatorCondition.java)

### 3.1. Bảng ưu tiên

Bảng sau xét các giá trị **có hiệu lực trong Spring Environment** sau khi các nguồn cấu hình đã được áp dụng:

| `defaults.enabled` | `<key>.enabled` | Điều kiện cho indicator đó |
| --- | --- | --- |
| Không khai báo | Không khai báo | Cho phép |
| `true` | Không khai báo | Cho phép |
| `false` | Không khai báo | Không cho phép |
| Không khai báo | `true` | Cho phép |
| Không khai báo | `false` | Không cho phép |
| `true` | `true` | Cho phép |
| `true` | `false` | Không cho phép |
| `false` | `true` | Cho phép |
| `false` | `false` | Không cho phép |

“Cho phép” chưa đủ để khẳng định bean chắc chắn xuất hiện: những điều kiện cấu hình tự động khác vẫn phải thỏa mãn.

Hai hệ quả cần nhớ:

1. `defaults.enabled=false` **không phải lệnh cấm tuyệt đối**: một công tắc riêng `true` có thể bật lại indicator.
2. `defaults.enabled=true` **không ép mọi indicator được bật**: công tắc riêng `false` vẫn thắng.

Các cấu hình tự động sử dụng annotation này được liệt kê trong [API ConditionalOnEnabledHealthIndicator của nhánh 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/class-use/ConditionalOnEnabledHealthIndicator.html). Chương trình ở mục 7 kiểm chứng trực tiếp quy tắc ưu tiên bằng thư viện **3.3.0**.

### 3.2. Tắt riêng một indicator

```properties
management.health.diskspace.enabled=false
```

Các indicator khác vẫn theo cấu hình của chúng. Không cần đặt `defaults.enabled=true` chỉ để giữ hành vi mặc định.

Ví dụ khác:

```properties
management.health.db.enabled=false
management.health.redis.enabled=true
```

Ý nghĩa là không cho cấu hình tự động tạo phép kiểm tra JDBC, đồng thời cho phép cấu hình tự động tạo phép kiểm tra Redis nếu các điều kiện còn lại thỏa mãn. Các công tắc này không thay đổi khả năng ứng dụng sử dụng JDBC hoặc Redis trong nghiệp vụ.

### 3.3. Tắt theo mặc định rồi chọn lại

```properties
management.health.defaults.enabled=false
management.health.ping.enabled=true
management.health.diskspace.enabled=true
```

Đây là cách khai báo tập phép kiểm tra tự cấu hình một cách chủ động. `ping` và `diskspace` được cho phép; indicator khác thuộc cơ chế mặc định chung sẽ không được cho phép nếu chưa có công tắc riêng.

Tương đương bằng YAML:

```yaml
management:
  health:
    defaults:
      enabled: false
    ping:
      enabled: true
    diskspace:
      enabled: true
```

Trong cùng một tệp YAML, gộp các phần này dưới **một** khóa `management`. Không tạo nhiều khóa `management` trùng nhau rồi trông chờ chúng được hợp nhất theo ý muốn.

Danh sách properties chính thức là nơi kiểm tra tên và ý nghĩa công tắc theo phiên bản. [Application properties của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

## 4. Bean tự khai báo có chịu công tắc mặc định không?

Câu trả lời phụ thuộc vào **điều kiện trên mã tạo bean**, không chỉ vào việc bean triển khai `HealthIndicator`.

### 4.1. Bean không có điều kiện bật/tắt

Đoạn sau nằm trong một lớp cấu hình Spring:

```java
@Bean
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Chỉ thêm cấu hình sau không tự loại bean đó:

```properties
management.health.defaults.enabled=false
management.health.catalog.enabled=false
```

Không có đoạn mã nào trên bean mẫu đọc hai công tắc ấy. Spring Boot không coi mọi tên sau `management.health.` là một lệnh xóa bean health tương ứng.

Điều này cũng quan trọng khi tự cung cấp bean thay thế một indicator có sẵn. Cấu hình `enabled=false` có thể ngăn đường tạo bean tự động, nhưng một bean do ứng dụng chủ động tạo bằng đường khác vẫn có thể tồn tại.

### 4.2. Cho bean một công tắc riêng của ứng dụng

```java
@Bean
@ConditionalOnProperty(prefix = "demo.health.catalog", name = "enabled",
        havingValue = "true", matchIfMissing = true)
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Các import cho đoạn trên:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
```

Với điều kiện này:

- Không khai báo `demo.health.catalog.enabled`: bean được tạo vì `matchIfMissing=true`.
- Giá trị `true`: bean được tạo.
- Giá trị `false`: bean không được tạo.
- `management.health.defaults.enabled` không tham gia điều kiện riêng này.

`havingValue="true"` và `matchIfMissing=true` là những lựa chọn được viết rõ trong mã, không phải mặc định chung của annotation. [API ConditionalOnProperty 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)

### 4.3. Cho bean dùng quy tắc management.health

Nếu muốn bean `catalog` tham gia cùng cơ chế ưu tiên ở mục 3, dùng **thay cho annotation ở mục 4.2**:

```java
@Bean
@ConditionalOnEnabledHealthIndicator("catalog")
HealthIndicator catalogHealthIndicator() {
    return () -> Health.up().build();
}
```

Import bổ sung:

```java
import org.springframework.boot.actuate.autoconfigure.health.ConditionalOnEnabledHealthIndicator;
```

Khi đó:

```properties
management.health.defaults.enabled=false
management.health.catalog.enabled=true
```

sẽ cho phép tạo bean `catalog`, còn:

```properties
management.health.catalog.enabled=false
```

sẽ không cho phép tạo bean đó dù mặc định chung đang là `true`.

Không giữ đồng thời hai annotation nếu không chủ ý yêu cầu **cả hai điều kiện** phải thỏa mãn. Hai cách trên là hai thiết kế thay thế, với hai không gian cấu hình khác nhau.

## 5. Thí nghiệm trên ứng dụng HTTP

Ta tạo một ứng dụng chỉ có Web, Actuator và một indicator tự khai báo. Mục tiêu là quan sát **tập ID đang được đăng ký**, tách khỏi việc một phép kiểm tra có đang báo `UP` hay `DOWN`.

### 5.1. Tệp dự án

```text
indicator-demo/
├── pom.xml
└── src/main/
    ├── java/example/indicators/IndicatorDemoApplication.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>indicator-demo</artifactId>
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

`src/main/java/example/indicators/IndicatorDemoApplication.java`:

```java
package example.indicators;

import java.util.TreeSet;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IndicatorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IndicatorDemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo.health.catalog", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    HealthIndicator catalogHealthIndicator() {
        return () -> Health.up().withDetail("source", "local-demo").build();
    }

    @Bean
    ApplicationRunner printContributors(HealthContributorRegistry registry) {
        return args -> {
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println("contributors=" + names);
        };
    }
}
```

Indicator `catalog` cố ý trả một kết quả cục bộ cố định để thí nghiệm không cần hệ thống bên ngoài. Trong một ứng dụng thực, thay phần kiểm tra bằng điều kiện có ý nghĩa; không dùng kết quả cố định này làm bằng chứng nghiệp vụ đã hoạt động.

`src/main/resources/application.properties`:

```properties
spring.application.name=indicator-demo
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=never
management.endpoint.health.probes.enabled=false
management.health.livenessstate.enabled=false
management.health.readinessstate.enabled=false
```

Ba công tắc cuối tách probes và các indicator trạng thái vòng đời khỏi thí nghiệm. Chúng không phải yêu cầu tắt probes trên ứng dụng thực.

`show-components=always` chỉ dùng để dễ quan sát tên thành phần trong ví dụ cục bộ. Khi triển khai, chọn chính sách hiển thị và quyền truy cập phù hợp. `show-details=never` giữ thông tin chi tiết của phép kiểm tra ngoài phản hồi; nó không ngăn phép kiểm tra chạy.

### 5.2. Đóng gói và xem tập mặc định

Tại thư mục chứa `pom.xml`:

```powershell
mvn -q package
java -jar target/indicator-demo-1.0.0.jar
```

Sau khi khởi động, tìm dòng do `ApplicationRunner` in ra, tách khỏi các log khác:

```text
contributors=[catalog, diskSpace, ping]
```

Danh sách được sắp xếp bằng `TreeSet` nên không phụ thuộc thứ tự bean xuất hiện. Dòng này chứng minh **sự hiện diện trong registry**, không khẳng định mọi indicator đều trả `UP`.

Trong PowerShell trên Windows, mở terminal khác và đọc các ID qua HTTP:

```powershell
$healthSnapshot = curl.exe -sS http://localhost:8080/actuator/health | ConvertFrom-Json
$healthSnapshot.components.PSObject.Properties.Name | Sort-Object
```

Kết quả tên thành phần:

```text
catalog
diskSpace
ping
```

Gọi `curl.exe` để tránh alias `curl` của một số phiên bản PowerShell. Không dùng `--fail` trong phép quan sát này: nếu dung lượng đĩa thực tế làm health báo lỗi, ta vẫn cần đọc được phần thân phản hồi.

### 5.3. Tắt riêng diskspace

Dừng tiến trình bằng `Ctrl+C` rồi chạy:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.diskspace.enabled=false
```

Dòng ứng dụng in:

```text
contributors=[catalog, ping]
```

`diskSpace` không còn trong tập đăng ký. `ping` và `catalog` vẫn có mặt. Ứng dụng không đổi tên `diskSpace`, không đổi kết quả của nó thành `UP`; đường tạo indicator tự động này đã bị vô hiệu hóa.

### 5.4. Tắt mặc định chung

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false
```

Dòng ứng dụng in:

```text
contributors=[catalog]
```

`diskSpace` và `ping` không được tạo theo cơ chế mặc định. `catalog` còn lại vì nó sử dụng công tắc `demo.health.catalog.enabled` của riêng ứng dụng, với `matchIfMissing=true`.

### 5.5. Bật lại ping dù mặc định chung là false

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --management.health.ping.enabled=true
```

Dòng ứng dụng in:

```text
contributors=[catalog, ping]
```

Thử chiều ngược lại:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=true --management.health.ping.enabled=false
```

Dòng ứng dụng in:

```text
contributors=[catalog, diskSpace]
```

Công tắc riêng được xét trước trong cả hai chiều.

### 5.6. Tắt đúng công tắc của bean tự khai báo

Lệnh sau **chưa tắt catalog** của ứng dụng mẫu:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --management.health.catalog.enabled=false
```

Dòng ứng dụng in vẫn là:

```text
contributors=[catalog]
```

Muốn tắt bean theo đúng annotation đang dùng:

```powershell
java -jar target/indicator-demo-1.0.0.jar --management.health.defaults.enabled=false --demo.health.catalog.enabled=false
```

Dòng ứng dụng in:

```text
contributors=[]
```

Danh sách rỗng chỉ cho thấy không còn contributor trong thí nghiệm. Không dùng nó làm bằng chứng ứng dụng đã kiểm tra đầy đủ các điều kiện để phục vụ người dùng.

Mỗi lệnh trên là **một lần khởi động riêng**. Dừng lần trước trước khi chạy lần sau để không trùng cổng `8080`.

## 6. Phân biệt tắt indicator với các cấu hình gần giống

| Mục tiêu | Cấu hình/cơ chế | Hệ quả cần hiểu |
| --- | --- | --- |
| Ngăn tạo một indicator tự cấu hình | `management.health.<key>.enabled=false` | Indicator thuộc đường cấu hình đó không được đăng ký |
| Đổi mặc định cho nhóm indicator có hỗ trợ | `management.health.defaults.enabled=false` | Công tắc riêng và các đường tạo bean khác vẫn phải được xét |
| Không đưa contributor vào một nhóm | `management.endpoint.health.group.<group>.exclude` | Contributor vẫn có thể tồn tại và tham gia health tổng/nhóm khác |
| Không hiển thị chi tiết | `management.endpoint.health.show-details=never` | Không đồng nghĩa ngăn phép kiểm tra thực thi |
| Không hiển thị thành phần | `management.endpoint.health.show-components=never` | JSON không đủ để kết luận contributor đã bị loại |
| Không cho endpoint được dùng | `management.endpoint.health.enabled=false` | Thao tác ở cấp endpoint, không phải công tắc riêng của từng phép kiểm tra |
| Không xuất bản endpoint qua HTTP | `management.endpoints.web.exposure.exclude=health` | Điều khiển khả năng tiếp cận HTTP, không phải kết quả phép kiểm tra |
| Chặn người gọi bằng bảo mật | Quy tắc xác thực/phân quyền | Phản hồi bị chặn không chứng minh indicator đã bị tắt |

Ví dụ loại `diskSpace` khỏi **một nhóm tự đặt tên**:

```properties
management.endpoint.health.group.traffic.include=*
management.endpoint.health.group.traffic.exclude=diskSpace
```

Nhóm `traffic` có thể bỏ qua phép kiểm tra này trong khi health tổng vẫn có `diskSpace`. Với YAML, cần viết `include: "*"` vì dấu `*` có ý nghĩa riêng trong YAML.

Nếu một nhóm `include` chỉ định contributor đã bị tắt hoặc chưa được tạo, cơ chế kiểm tra thành viên của nhóm có thể làm khởi động thất bại. Hãy sửa tập thành viên hoặc điều kiện tạo contributor cho nhất quán thay vì mặc định tắt kiểm tra hợp lệ của nhóm.

### 6.1. Giới hạn với probes và các đường cấu hình riêng

Không coi `management.health.defaults.enabled=false` là công tắc đóng mọi cơ chế health. Trong Spring Boot 3.3, probes có đường cấu hình riêng qua `management.endpoint.health.probes.enabled` và có thể được tự kích hoạt khi phát hiện Kubernetes.

Cấu hình probes có thể tạo các indicator `livenessState` và `readinessState` bằng cơ chế của nó. Vì vậy, chỉ nhìn `defaults.enabled` rồi kết luận mọi indicator đều vắng mặt là không đủ. [AvailabilityProbesAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/availability/AvailabilityProbesAutoConfiguration.java)

Bài chỉ dùng các cờ này để cô lập thí nghiệm. Việc thiết kế ý nghĩa liveness/readiness và tác động tới khởi động lại hoặc định tuyến cần được quyết định theo yêu cầu vận hành riêng.

### 6.2. Thời điểm áp dụng cấu hình

Các điều kiện tạo bean được đánh giá khi dựng ApplicationContext. Với ứng dụng mẫu, sửa một tệp properties sau khi ứng dụng đã chạy không tự tạo lại hoặc loại bỏ indicator; hãy khởi động lại với cấu hình mới.

Spring Boot có API quản lý registry ở thời điểm chạy, nhưng đó là một cơ chế khác. Không hiểu công tắc cấu hình trong bài là một API bật/tắt trực tiếp cho mỗi yêu cầu HTTP.

## 7. Chương trình Java kiểm chứng chín kịch bản

Chương trình sau dựng ApplicationContext nhỏ với đúng các cấu hình health cần kiểm tra. Nó không mở web server và không cần JDBC, Redis hoặc dịch vụ ngoài.

Hai lớp cấu hình con giúp đối chiếu:

- `CustomIndicators`: công tắc `demo.health.catalog.enabled`, độc lập với mặc định health.
- `ManagedCustomIndicators`: công tắc `management.health.catalog.enabled`, có xét mặc định health.

Tạo `experiments/IndicatorSwitchDemo.java` bên cạnh dự án mục 5, **ngoài** `src/main/java` để không thêm main thứ hai vào JAR Spring Boot:

```java
import java.util.Map;
import java.util.TreeSet;
import org.springframework.boot.actuate.autoconfigure.health.ConditionalOnEnabledHealthIndicator;
import org.springframework.boot.actuate.autoconfigure.health.HealthContributorAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.system.DiskSpaceHealthContributorAutoConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class IndicatorSwitchDemo {
    @Configuration(proxyBeanMethods = false)
    static class CustomIndicators {
        @Bean
        @ConditionalOnProperty(prefix = "demo.health.catalog",
                name = "enabled", havingValue = "true", matchIfMissing = true)
        HealthIndicator catalogHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ManagedCustomIndicators {
        @Bean
        @ConditionalOnEnabledHealthIndicator("catalog")
        HealthIndicator catalogHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    static void run(String label, Class<?> customConfig,
                    Map<String, Object> properties) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("experiment", properties));
            context.register(customConfig,
                    DiskSpaceHealthContributorAutoConfiguration.class,
                    HealthContributorAutoConfiguration.class,
                    HealthEndpointAutoConfiguration.class);
            context.refresh();
            HealthContributorRegistry registry =
                    context.getBean(HealthContributorRegistry.class);
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println(label + "=" + names);
        }
    }

    public static void main(String[] args) {
        run("default", CustomIndicators.class, Map.of());
        run("diskspace-off", CustomIndicators.class,
                Map.of("management.health.diskspace.enabled", false));
        run("defaults-off", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false));
        run("ping-opt-in", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.ping.enabled", true));
        run("custom-key-ignored", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.catalog.enabled", false));
        run("custom-off", CustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "demo.health.catalog.enabled", false));
        run("managed-defaults-off", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", false));
        run("managed-opt-in", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", false,
                        "management.health.catalog.enabled", true));
        run("managed-explicit-off", ManagedCustomIndicators.class,
                Map.of("management.health.defaults.enabled", true,
                        "management.health.catalog.enabled", false));
    }
}
```

Lấy classpath Maven, biên dịch và chạy trong PowerShell trên Windows:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$indicatorDemoClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $indicatorDemoClasspath experiments/IndicatorSwitchDemo.java
java -cp "$indicatorDemoClasspath;experiments" IndicatorSwitchDemo
```

Trên Linux/macOS, dùng dấu `:` phân cách classpath và cú pháp shell tương ứng.

Các dòng stdout do chương trình tạo:

```text
default=[catalog, diskSpace, ping]
diskspace-off=[catalog, ping]
defaults-off=[catalog]
ping-opt-in=[catalog, ping]
custom-key-ignored=[catalog]
custom-off=[]
managed-defaults-off=[]
managed-opt-in=[catalog]
managed-explicit-off=[diskSpace, ping]
```

Các log của thư viện, nếu có, không thuộc những dòng kết quả trên. Danh sách được sắp xếp để dễ đối chiếu.

### 7.1. Cách đọc kết quả

1. `default` và `diskspace-off` cho thấy tắt riêng không ảnh hưởng contributor còn lại.
2. `defaults-off` loại hai indicator tự cấu hình nhưng không loại custom bean dùng công tắc riêng.
3. `ping-opt-in` xác nhận `true` riêng có thể bật lại sau `false` chung.
4. `custom-key-ignored` cho thấy đặt một property không được điều kiện của bean đọc sẽ không tự tắt bean.
5. `custom-off` tắt bean bằng công tắc mà mã của nó thực sự dùng.
6. `managed-defaults-off` và `managed-opt-in` cho thấy custom bean có thể tham gia cơ chế mặc định chung nếu được gắn annotation tương ứng.
7. `managed-explicit-off` xác nhận `false` riêng thắng `true` chung.

Đây là kiểm chứng sự hiện diện trong registry bằng API framework. Trong ứng dụng thực, vẫn cần kiểm tra thêm profile, nguồn cấu hình có hiệu lực, các starter đang dùng, bean tự cung cấp và tập thành viên của từng nhóm.

## 8. Chẩn đoán khi cấu hình không cho kết quả mong muốn

| Hiện tượng | Khả năng cần kiểm tra | Cách kiểm tra có ích |
| --- | --- | --- |
| Đặt `defaults=false` nhưng một indicator vẫn có mặt | Có công tắc riêng `true`, bean tự khai báo hoặc đường cấu hình riêng | Tìm nơi tạo bean và điều kiện của chính nó |
| Đặt `redis=true` nhưng không có Redis health | Thiếu thư viện/bean kết nối hoặc cấu hình tự động không thỏa điều kiện khác | Kiểm tra phụ thuộc và báo cáo điều kiện cấu hình |
| Đặt `management.health.catalog.enabled=false` mà catalog còn | Bean không dùng quy tắc đó | Đối chiếu annotation trên bean; không suy từ ID |
| JSON không có `components` | Chính sách hiển thị đang ẩn thành phần | Đọc registry hoặc bật hiển thị phù hợp trong môi trường thử |
| Có tên trong registry nhưng health báo `DOWN` | Indicator đã được tạo và phép kiểm tra trả lỗi | Phân tích kết quả kiểm tra, không coi công tắc bật là lệnh ép `UP` |
| Tắt `db` rồi ứng dụng vẫn lỗi kết nối trong nghiệp vụ | Công tắc health không tắt mã sử dụng cơ sở dữ liệu | Sửa kết nối hoặc đường nghiệp vụ |
| Khởi động lỗi sau khi tắt một indicator | Nhóm đang yêu cầu thành viên không còn tồn tại | Kiểm tra `group.*.include/exclude` và tên ID |
| Sửa properties nhưng lần chạy không đổi | Tệp/profile không được nạp, giá trị bị nguồn khác ghi đè hoặc chưa khởi động lại | Kiểm tra cấu hình có hiệu lực và lệnh khởi động |

Có thể khởi động ứng dụng mẫu với `--debug` để xem báo cáo điều kiện cấu hình trong log:

```powershell
java -jar target/indicator-demo-1.0.0.jar --debug --management.health.diskspace.enabled=false
```

Báo cáo giúp phân biệt “đường cấu hình không khớp điều kiện” với “bean đã tạo nhưng bị ẩn khỏi JSON”. Không cần mở thêm endpoint `env` hoặc `conditions` công khai chỉ để thực hiện bài thử này.

## 9. Thực hành và tiêu chí tự kiểm tra

1. Chỉ bằng cấu hình của ứng dụng mẫu, tạo tập `[catalog, diskSpace]`. Dự đoán công tắc nào phải tắt, rồi đối chiếu dòng `contributors`.
2. Tạo tập `[ping]` bằng cách tắt mặc định chung, bật riêng `ping` và tắt `catalog` bằng công tắc của ứng dụng. Kiểm tra registry lẫn HTTP.
3. Thay annotation của `catalog` bằng `@ConditionalOnEnabledHealthIndicator("catalog")`. Chạy lại `defaults=false` và `catalog=true`; giải thích vì sao công tắc `demo.health.catalog.enabled` không còn là công tắc điều khiển bean.
4. Giữ `diskSpace` trong registry nhưng loại nó khỏi nhóm `traffic`. Phân biệt kết quả đó với việc đặt `management.health.diskspace.enabled=false`.
5. Giải thích vì sao chỉ còn `ping` và HTTP thành công chưa đủ để khẳng định ứng dụng truy cập được cơ sở dữ liệu.
6. Với một indicator thực tế muốn tắt, ghi rõ nó kiểm tra điều kiện nào, ai đang dùng tín hiệu đó và còn tín hiệu nào thay thế sau khi tắt.

Khi xem một thay đổi bật/tắt, hãy đối chiếu ba bằng chứng: **giá trị cấu hình có hiệu lực, điều kiện tạo bean và tập contributor thực tế**. Chúng giúp giải thích chính xác ứng dụng đã ngừng kiểm tra điều gì, thay vì chỉ dựa vào một phản hồi JSON nhìn có vẻ khỏe.
