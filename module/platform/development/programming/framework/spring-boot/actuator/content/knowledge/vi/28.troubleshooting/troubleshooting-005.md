# Tìm nguyên nhân health group có thành viên không tồn tại hoặc ánh xạ status sai

## 1. Xác định lỗi nằm ở bước nào

Một nhóm kiểm tra sức khỏe (health group) chọn một tập thành phần kiểm tra để trả lời một câu hỏi cụ thể, chẳng hạn “ứng dụng đã sẵn sàng phục vụ chưa?”. Để chẩn đoán đúng, hãy tách ba bước:

```text
Chọn các thành viên thực sự đã được đăng ký
    -> lấy trạng thái của từng thành viên
    -> tổng hợp thành trạng thái của nhóm bằng StatusAggregator
    -> đổi trạng thái của nhóm thành mã HTTP bằng HttpCodeStatusMapper
```

**Tên thành viên**, **trạng thái sức khỏe** và **mã HTTP** là ba loại dữ liệu khác nhau. Ví dụ, `billing` là tên thành viên, `DOWN` là trạng thái và `503` là mã HTTP.

Bài này dùng **Spring Boot 3.3.13 và Java 21**. Nhóm `ready` trong ví dụ là nhóm tự định nghĩa, không phải tên bắt buộc của Spring Boot.

| Dấu hiệu | Bước cần kiểm tra trước |
| --- | --- |
| Ứng dụng không khởi động, thông báo một contributor không tồn tại | Tên và điều kiện đăng ký thành viên |
| Thành viên báo `DOWN`, nhóm lại báo `UP` | Tập thành viên và thứ tự tổng hợp trạng thái |
| Nhóm báo `DOWN`, HTTP lại là 200 | Ánh xạ trạng thái sang mã HTTP |
| Gọi một đường dẫn nhóm nhận 404 | Tên nhóm, đường dẫn và cấu hình endpoint; chưa thể kết luận ánh xạ status sai |

Không sửa cả ba bước cùng lúc. Một lần thay đổi có kiểm soát sẽ cho biết nguyên nhân nào thực sự ảnh hưởng kết quả.

## 2. Thành viên không tồn tại: kiểm tra danh sách được đăng ký

### 2.1. Phân biệt tên bean, ID thành viên và tên nhóm

Giả sử ứng dụng đăng ký bean:

```java
@Bean
HealthIndicator billingHealthIndicator() {
    return () -> Health.up().build();
}
```

Đây là mảnh mã minh họa; cần đặt trong lớp cấu hình và có các import tương ứng. Chương trình đầy đủ nằm ở mục 5.

Với quy ước đặt tên của Spring Boot, hậu tố `HealthIndicator` được bỏ khi xác định ID của indicator. Bean trên có ID `billing`. Nhóm dùng ID đó:

```properties
management.endpoint.health.group.ready.include=billing
```

Không thay `billing` bằng tên lớp, `billingHealthIndicator` hoặc URL `/actuator/health/billing` chỉ vì chúng cùng nhắc đến một kiểm tra. `ready` là tên nhóm; nó cũng không tự trở thành tên contributor. Quy tắc ID được mô tả trong [phần viết HealthIndicator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

Đối với contributor tổng hợp, phải kiểm tra cây thành viên. Chẳng hạn, nếu thực sự có composite `storage` với nhánh con `primary`, đường dẫn thành viên là `storage/primary`. Không tự đổi thành `storage.primary` hoặc `primary` khi chúng không được đăng ký như vậy.

### 2.2. Đọc thông báo lỗi theo ba dữ kiện

Cấu hình:

```properties
management.endpoint.health.group.ready.include=billing,ghost
```

Nếu không có contributor `ghost`, phần mô tả lỗi của ví dụ sẽ có:

```text
Included health contributor 'ghost' in group 'ready' does not exist
```

Ba dữ kiện cần lấy ra:

- `Included`: tên sai nằm trong danh sách `include`.
- `ghost`: contributor cần đối chiếu với danh sách đăng ký thực tế.
- `ready`: nhóm đang chứa cấu hình sai.

Danh sách `exclude` cũng được kiểm tra. Loại trừ một tên không tồn tại có thể làm khởi động thất bại, thay vì luôn được bỏ qua:

```text
Excluded health contributor 'ghost' in group 'ready' does not exist
```

Trong cơ chế mặc định của phiên bản này, kiểm tra diễn ra khi khởi tạo hạ tầng health; bộ kiểm tra đi từng đoạn của đường dẫn contributor. Có thể đối chiếu [HealthEndpointGroupMembershipValidator trong mã nguồn 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 2.3. Vì sao tên có vẻ đúng nhưng vẫn không tồn tại?

| Nguyên nhân thường gặp | Bằng chứng nên tìm | Cách xử lý theo nguyên nhân |
| --- | --- | --- |
| Sai chính tả, sai chữ hoa/thường hoặc dùng tên bean thay ID | Tên thực tế trong registry hoặc log chẩn đoán | Sửa tên trong đúng nhóm |
| Indicator tự động chưa đủ điều kiện tạo | Thiếu phụ thuộc, bean nền hoặc điều kiện tự cấu hình không khớp | Bổ sung điều kiện cần thiết nếu kiểm tra đó thuộc thiết kế |
| Indicator bị tắt bằng cấu hình | Giá trị cấu hình đang có hiệu lực | Bật lại đúng indicator hoặc sửa phạm vi nhóm |
| Bean tùy chỉnh chỉ tồn tại ở một profile | Profile đang chạy và điều kiện trên bean | Đồng bộ cấu hình nhóm với profile |
| Đường dẫn vào composite sai | Cấu trúc contributor thực tế | Dùng đúng đường dẫn cha/con |
| Sao chép nhóm từ môi trường khác | Danh sách phụ thuộc và bean khác nhau giữa hai môi trường | Viết cấu hình nhóm phù hợp từng môi trường |

Ví dụ, tên `db` không tự tạo một `DataSource`; tên `redis` cũng không tự thêm thư viện Redis. Tên trong nhóm chỉ lựa chọn các kiểm tra đã có.

Khi cần kiểm chứng tại chỗ, `HealthContributorRegistry` cung cấp các contributor đã được đăng ký và có thể duyệt danh sách này bằng mã chẩn đoán. Xem [API HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html). Không suy danh sách thực tế chỉ từ các starter bạn nhớ đã khai báo.

### 2.4. Tắt validation không tạo ra thành viên bị thiếu

Có thể bỏ kiểm tra khởi động bằng:

```properties
management.endpoint.health.validate-group-membership=false
```

Nhưng thuộc tính này **không đăng ký contributor mới, không đổi tên và không thực hiện kiểm tra bị thiếu**. Nếu nhóm vô tình bỏ mất một phụ thuộc quan trọng, ứng dụng khởi động được chưa có nghĩa nhóm đang kiểm tra đủ.

Ưu tiên sửa tên, điều kiện tạo bean hoặc cấu hình theo môi trường. Chỉ bỏ kiểm tra thành viên khi thiết kế thực sự cho phép contributor vắng mặt và bạn đã xác minh nhóm còn kiểm tra đúng những gì cần thiết. Không dùng nó để che một lỗi sao chép cấu hình.

## 3. Trạng thái thành viên đúng nhưng trạng thái nhóm sai

`StatusAggregator` chọn trạng thái tổng hợp theo thứ tự ưu tiên đã cấu hình. Đây không phải bỏ phiếu theo đa số: một thành viên `DOWN` vẫn có thể quyết định trạng thái nhóm dù các thành viên khác đều `UP`.

Với bộ tổng hợp mặc định của Spring Boot 3.3.13, thứ tự là `DOWN`, `OUT_OF_SERVICE`, `UP`, `UNKNOWN`. Bộ tổng hợp chỉ xét các trạng thái có trong thứ tự nó biết; nếu không có trạng thái nào phù hợp, kết quả là `UNKNOWN`. Cơ chế này có thể kiểm tra trong [SimpleStatusAggregator](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Giả sử `billing` trả trạng thái tùy chỉnh `FATAL`, còn `cache` trả `UP`. Nếu bộ tổng hợp chưa biết `FATAL`, trạng thái đó có thể bị bỏ qua và nhóm trả `UP`.

Chỉ thêm ánh xạ `fatal=503` chưa giải quyết được: bộ ánh xạ nhận **trạng thái đã tổng hợp của nhóm**, không tự đi tìm mọi trạng thái con.

Cấu hình thứ tự cho nhóm:

```properties
management.endpoint.health.group.ready.status.order=fatal,down,out-of-service,unknown,up
```

Đây là chính sách ví dụ: đặt `FATAL` trước `DOWN`, và chọn `UNKNOWN` ưu tiên hơn `UP`. Hãy chọn thứ tự theo ý nghĩa vận hành của hệ thống; đừng hiểu đây là bản sao nguyên vẹn thứ tự mặc định.

Khi tự đặt thứ tự, ghi đủ các trạng thái nhóm cần xử lý. Ví dụ, chỉ đặt `fatal,up` có thể khiến một `DOWN` không còn được xét như mong muốn. Tương tự, đặt `up` trước `down` có thể chọn `UP` khi cả hai cùng xuất hiện.

Nếu trạng thái nhóm sai, hãy xác minh **cả thành viên đã chọn lẫn bộ tổng hợp** trước khi chỉnh mã HTTP.

## 4. Nhóm báo DOWN nhưng HTTP là 200

### 4.1. Mặc định và bẫy khi thêm ánh xạ tùy chỉnh

Với bộ ánh xạ mặc định:

| Trạng thái nhóm | Mã HTTP |
| --- | --- |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UP` | 200 |
| `UNKNOWN` | 200 |
| Trạng thái chưa được ánh xạ | 200 |

Trong Spring Boot 3.3, khai báo ánh xạ tùy chỉnh làm mất các ánh xạ mặc định `DOWN` và `OUT_OF_SERVICE` nếu bạn không khai báo lại. Đây là lý do một cấu hình trông như “chỉ thêm FATAL” lại có thể thay đổi hành vi của `DOWN`.

Cấu hình thiếu:

```properties
management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Nếu nhóm đang tổng hợp thành `DOWN`, bảng tùy chỉnh trên không có `DOWN`; kết quả ánh xạ là 200.

Cấu hình đầy đủ cho chính sách ví dụ:

```properties
management.endpoint.health.group.ready.status.http-mapping.fatal=503
management.endpoint.health.group.ready.status.http-mapping.down=503
management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

Các phép thử ở mục 6 kiểm tra trực tiếp bằng `HttpCodeStatusMapper`; API của bộ ánh xạ được mô tả tại [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 4.2. Phân biệt cấu hình toàn cục với cấu hình riêng nhóm

Hai phạm vi khác nhau:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Khi nhóm không có cấu hình hay bean riêng cho chức năng tương ứng, nó kế thừa bộ tổng hợp/bộ ánh xạ dùng chung. Nhưng khi nhóm đã có bảng ánh xạ riêng không rỗng, đừng giả định bảng đó được ghép từng khóa với bảng toàn cục. Trong ví dụ trên, `ready` có thể ánh xạ `DOWN` thành 200 dù toàn cục có `down=503`.

Cách sửa là khai báo đầy đủ bảng cần dùng ở nhóm, hoặc bỏ bảng riêng nếu muốn nhóm dùng chính sách chung. Kiểm tra tương tự cho `status.order`.

Ngoài properties, hãy tìm các bean `StatusAggregator`, `HttpCodeStatusMapper` và bean có `@Qualifier("ready")`. Một bean tùy chỉnh có thể quyết định hành vi thực tế thay cho bộ được tạo từ properties. Cách chọn cấu hình và bean được thể hiện trong [AutoConfiguredHealthEndpointGroups](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

## 5. Ứng dụng tối giản để tái hiện

Chuẩn bị JDK 21 và Maven. Ví dụ dùng hai kiểm tra giả lập, không kết nối cơ sở dữ liệu hay bộ nhớ đệm bên ngoài. Trạng thái được truyền bằng cấu hình để tái hiện từng tình huống một cách xác định.

Cây file:

```text
health-group-lab/
├── pom.xml
└── src/main/
    ├── java/example/HealthGroupLabApplication.java
    └── resources/application.properties
```

Nội dung đầy đủ của `pom.xml`:

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
    <groupId>example</groupId>
    <artifactId>health-group-lab</artifactId>
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

Nội dung đầy đủ của `HealthGroupLabApplication.java`:

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthEndpointGroups;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthGroupLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupLabApplication.class, args);
    }

    @Bean
    HealthIndicator billingHealthIndicator(
            @Value("${lab.billing-status:UP}") String status) {
        return () -> Health.status(status).build();
    }

    @Bean
    HealthIndicator cacheHealthIndicator(
            @Value("${lab.cache-status:UP}") String status) {
        return () -> Health.status(status).build();
    }

    @Bean
    @ConditionalOnProperty(name = "lab.report", havingValue = "true")
    ApplicationRunner report(
            HealthEndpoint endpoint,
            HealthEndpointGroups groups,
            ConfigurableApplicationContext context) {
        return args -> {
            var health = endpoint.healthForPath("ready");
            var group = groups.get("ready");
            System.out.println("ready.status=" + health.getStatus().getCode());
            System.out.println("ready.http=" + group.getHttpCodeStatusMapper()
                    .getStatusCode(health.getStatus()));
            SpringApplication.exit(context);
        };
    }
}
```

Nội dung `src/main/resources/application.properties`:

```properties
server.port=8183
management.endpoints.web.exposure.include=health
management.endpoint.health.group.ready.include=billing,cache
management.endpoint.health.group.ready.show-components=always
management.endpoint.health.group.ready.show-details=always
```

Hai bean có ID `billing` và `cache`. Các thuộc tính `lab.*` là công tắc giả lập do ví dụ tự định nghĩa, không phải thuộc tính chuẩn của Actuator.

Bean `report` chỉ được tạo khi truyền `--lab.report=true`. Nó lấy kết quả nhóm qua `healthForPath("ready")`, in trạng thái và mã do bộ ánh xạ của chính nhóm trả về, rồi đóng ứng dụng. Phương thức này thuộc [API HealthEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

Đóng gói từ thư mục chứa `pom.xml`:

```shell
mvn package
```

Maven chuẩn bị classpath và tạo JAR chạy được; không biên dịch riêng file này bằng một lệnh `javac` thiếu các phụ thuộc Spring.

Chạy chế độ HTTP bình thường:

```shell
java -jar target/health-group-lab-1.0.0.jar
```

Từ terminal khác:

```shell
curl -i http://localhost:8183/actuator/health/ready
```

Với trạng thái mặc định của hai kiểm tra, nhóm trả `UP` và mã HTTP 200. Phần thân JSON có dạng:

```json
{
  "status": "UP",
  "components": {
    "billing": { "status": "UP" },
    "cache": { "status": "UP" }
  }
}
```

Thứ tự trường JSON không phải điều kiện kiểm tra. Cấu hình hiển thị thành phần/chi tiết trong ví dụ phục vụ chẩn đoán cục bộ; khi áp dụng vào hệ thống thật, giữ chính sách hiển thị phù hợp.

Dừng bằng Ctrl+C trước khi đổi cấu hình và khởi chạy trường hợp khác. Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là alias.

## 6. Các phép thử tách riêng nguyên nhân

Để tập trung vào cấu hình mà không cần mở cổng HTTP, ví dụ có chế độ báo cáo trong tiến trình. Các lệnh dưới đây tắt máy chủ web, bật hạ tầng JMX để duy trì tính sẵn sàng của endpoint và gọi health bằng API Java.

**`ready.http` là mã do bộ ánh xạ trả về, không phải kết quả của một yêu cầu mạng.** Khi kiểm tra triển khai thật, vẫn cần kiểm tra cả HTTP trực tiếp và đường đi qua proxy/bảo mật.

Mỗi lệnh là một lần chạy độc lập. Các tùy chọn tắt banner và logging giúp stdout thành công chỉ còn hai dòng của chương trình.

### 6.1. Mốc đối chứng

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true
```

Stdout:

```text
ready.status=UP
ready.http=200
```

### 6.2. Thành viên không tồn tại

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --management.endpoint.health.group.ready.include=billing,ghost
```

Ứng dụng khởi động thất bại. Phần mô tả lỗi chứa:

```text
Included health contributor 'ghost' in group 'ready' does not exist
```

Đây là lỗi cấu hình trước khi ứng dụng phục vụ bình thường, không phải phản hồi health HTTP 500. Sửa `ghost` thành contributor hợp lệ hoặc bỏ yêu cầu kiểm tra đó nếu thiết kế cho phép.

Để tái hiện lỗi danh sách loại trừ, chạy một lần riêng với:

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --management.endpoint.health.group.ready.exclude=ghost
```

Lần này phần mô tả nêu `Excluded` như mục 2.2.

### 6.3. DOWN với bộ ánh xạ mặc định

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=DOWN
```

Stdout:

```text
ready.status=DOWN
ready.http=503
```

`cache=UP` không làm mất ảnh hưởng của `billing=DOWN`.

### 6.4. Chỉ thêm ánh xạ FATAL và vô tình mất DOWN

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=DOWN --management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Stdout:

```text
ready.status=DOWN
ready.http=200
```

Trạng thái nhóm vẫn đúng; lỗi nằm ở bảng ánh xạ.

Để sửa, chạy lại lệnh trên và thêm **hai tùy chọn khác tên**:

```text
--management.endpoint.health.group.ready.status.http-mapping.down=503
--management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

Đặt hai tùy chọn vào cùng lệnh, phân cách bằng khoảng trắng. Không chạy chúng như hai chương trình độc lập. Stdout sau sửa:

```text
ready.status=DOWN
ready.http=503
```

### 6.5. Có ánh xạ FATAL nhưng chưa có thứ tự tổng hợp

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=FATAL --management.endpoint.health.group.ready.status.http-mapping.fatal=503
```

Stdout:

```text
ready.status=UP
ready.http=200
```

Trong phép thử này, `FATAL` chưa nằm trong thứ tự bộ tổng hợp biết, còn `cache` trả `UP`. Bộ ánh xạ nhận `UP`, nên khóa `fatal` chưa có cơ hội được dùng.

Cấu hình đầy đủ cả hai bước:

```shell
java -jar target/health-group-lab-1.0.0.jar --spring.main.web-application-type=none --spring.jmx.enabled=true --spring.main.banner-mode=off --logging.level.root=OFF --lab.report=true --lab.billing-status=FATAL --management.endpoint.health.group.ready.status.order=fatal,down,out-of-service,unknown,up --management.endpoint.health.group.ready.status.http-mapping.fatal=503 --management.endpoint.health.group.ready.status.http-mapping.down=503 --management.endpoint.health.group.ready.status.http-mapping.out-of-service=503
```

Stdout:

```text
ready.status=FATAL
ready.http=503
```

**Điểm phân biệt:** sửa thứ tự tổng hợp làm thay đổi `ready.status`; sửa bảng HTTP chỉ làm thay đổi mã ánh xạ cho trạng thái đã chọn.

## 7. Quy trình chẩn đoán trong ứng dụng thật

1. **Xác định thời điểm lỗi.** Nếu khởi động thất bại vì contributor không tồn tại, xử lý thông báo validation trước. Nếu ứng dụng đã chạy, ghi lại cả tên nhóm, trạng thái JSON và mã HTTP.
2. **Xác minh cấu hình có hiệu lực.** Kiểm tra profile, file ngoài JAR, biến môi trường và tham số khởi chạy. Một giá trị trong mã nguồn có thể bị nguồn khác ghi đè; xem [thứ tự nguồn cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
3. **Đối chiếu thành viên thật.** Kiểm tra ID trong registry, điều kiện tạo bean và đường dẫn composite. Phân biệt “không có kiểm tra” với “có kiểm tra nhưng đang DOWN”.
4. **So sánh trạng thái con với trạng thái nhóm.** Khi cần, cho phép xem thành phần qua chính sách chẩn đoán hiện có. Nếu một trạng thái bị bỏ qua, kiểm tra tập thành viên và `status.order`.
5. **So sánh trạng thái nhóm với HTTP.** Khi nhóm đã là `DOWN` nhưng HTTP 200, tìm bảng ánh xạ tùy chỉnh thiếu khóa, phạm vi nhóm/toàn cục và bean `HttpCodeStatusMapper`.
6. **Kiểm tra đường đi của yêu cầu.** Nếu mã từ ứng dụng khác mã quan sát bên ngoài, kiểm tra proxy, gateway, bộ lọc bảo mật và cấu hình probe. Không quy mọi khác biệt cho Actuator.
7. **Sửa một nguyên nhân rồi kiểm chứng lại.** Giữ một trường hợp khỏe, một trường hợp hỏng và trạng thái tùy chỉnh quan trọng. Kiểm tra cả nội dung trạng thái lẫn mã HTTP; chỉ kiểm tra “khác 500” là chưa đủ.

Kết quả health gốc `/actuator/health` và nhóm `/actuator/health/ready` có thể khác nhau vì tập thành viên hoặc chính sách tổng hợp khác nhau. Đó chưa phải lỗi: phải đối chiếu đúng nhóm mà bộ kiểm tra bên ngoài đang gọi.

Các tên gần giống nhau cũng cần tách rõ. `readiness` có thể là tên nhóm probe, còn `readinessState` là ID của một kiểm tra trạng thái sẵn sàng. Nếu dùng các thành phần probe tự động, kiểm tra điều kiện kích hoạt tương ứng; đừng thay thế tên này bằng tên kia trong danh sách thành viên.

## 8. Các cách sửa dễ che mất lỗi

- **Tắt validation để ứng dụng khởi động:** có thể làm mất kiểm tra bắt buộc mà không tạo ra contributor bị thiếu.
- **Đổi mọi mã HTTP thành 200:** có thể khiến bộ cân bằng tải tiếp tục gửi yêu cầu tới ứng dụng không sẵn sàng.
- **Chỉ thêm `fatal=503`:** chưa xử lý thứ tự tổng hợp và có thể làm mất ánh xạ lỗi mặc định.
- **Sửa bảng toàn cục rồi bỏ qua bảng của nhóm:** nhóm có cấu hình riêng vẫn có thể giữ hành vi khác.
- **Dùng `show-details` để chữa trạng thái:** thuộc tính hiển thị giúp quan sát; nó không tự sửa thành viên, bộ tổng hợp hay bảng HTTP.
- **Đồng nhất UNKNOWN với khỏe:** mặc định có thể ánh xạ thành 200, nhưng ý nghĩa kiểm tra vẫn là chưa xác định. Chính sách vận hành phải quyết định có chấp nhận trạng thái ấy hay không.

## 9. Tự kiểm tra

**A. Nhóm tham chiếu `billingHealthIndicator` nhưng registry chỉ có `billing`. Cần đổi HTTP mapping không?**

Không. Sửa ID thành viên trong nhóm; chưa đến bước tổng hợp hay ánh xạ HTTP.

**B. JSON của nhóm là `DOWN`, HTTP là 200, nhóm có riêng `fatal=503`. Kiểm tra gì trước?**

Kiểm tra bảng HTTP của chính nhóm và khai báo lại `down`/`out-of-service` theo chính sách mong muốn.

**C. Thành viên trả `FATAL`, nhóm trả `UP` dù có `fatal=503`.**

Kiểm tra `status.order` và việc thành viên có nằm trong nhóm. Bộ ánh xạ chỉ nhận trạng thái tổng hợp.

**D. `down=503` ở toàn cục nhưng nhóm vẫn đổi DOWN thành 200.**

Tìm bảng hoặc bean ánh xạ riêng của nhóm. Không giả định cấu hình riêng được ghép từng khóa với cấu hình chung.

**E. Tắt kiểm tra thành viên và ứng dụng khởi động thành công. Đã chứng minh phụ thuộc quan trọng đang được kiểm tra chưa?**

Chưa. Cần xác minh contributor thực sự được đăng ký, nằm trong nhóm và tác động đúng đến trạng thái cũng như mã HTTP.
