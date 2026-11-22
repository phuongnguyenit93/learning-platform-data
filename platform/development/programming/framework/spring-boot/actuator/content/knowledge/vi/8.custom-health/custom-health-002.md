# Định danh indicator từ tên bean và tổ chức đường dẫn thành phần

## 1. Từ một bean Java đến một đường dẫn health

Khi thêm một `HealthIndicator` vào ứng dụng Spring Boot, ta không cần viết một controller riêng cho phép kiểm tra đó. Actuator thu thập các bean health, đăng ký chúng dưới những tên xác định và dùng các tên ấy để xây dựng cây thành phần.

Ví dụ:

```text
Bean: inventoryHealthIndicator
    -> ID ở gốc: inventory
    -> đường dẫn: /actuator/health/inventory
```

Hiểu đúng bước chuyển này giúp trả lời ba câu hỏi:

1. Vì sao tên trong JSON ngắn hơn tên bean?
2. Vì sao một đối tượng con nằm trong composite có đường dẫn nhiều đoạn?
3. Vì sao một tên tồn tại trong mã Java nhưng URL mình đoán vẫn trả `404`?

Bài dùng **Spring Boot 3.3.0 và JDK 21** để cố định ví dụ. Quy tắc và các kiểu API được trình bày thuộc nhánh **3.3.x**, với cấu hình registry tiêu chuẩn của Actuator.

### 1.1. Bốn lớp tên cần phân biệt

| Lớp tên | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên bean Spring | `inventoryHealthIndicator` | Định danh bean trong container |
| ID contributor ở gốc | `inventory` | Khóa tra cứu trong registry health |
| Tên con trong composite | `primary` | Khóa tra cứu dưới một contributor cha |
| Đường dẫn HTTP | `/actuator/health/checkout/payment/primary` | Đường đi từ endpoint đến một nút trong cây |

Tên lớp Java, tên phương thức, bí danh (alias), tên trong dữ liệu `details` và ID của contributor có liên hệ với nhau, nhưng không phải lúc nào cũng là cùng một chuỗi.

Cấu trúc package như `example.health.payment` không tự tạo đường dẫn `/health/payment`. Cây health được xác định bởi các contributor đăng ký và quan hệ composite, không phải cây thư mục mã nguồn.

## 2. ID ở gốc được suy ra từ tên bean

### 2.1. Tên bean đến từ đâu?

Với một phương thức `@Bean` không chỉ định tên, tên phương thức là tên bean:

```java
@Bean
HealthIndicator searchHealthIndicator() {
    return () -> Health.up().build();
}
```

Tên bean là `searchHealthIndicator`. Theo quy ước đặt tên health, ID ở gốc là `search`.

Nếu chỉ định tên rõ ràng, tên đó được dùng thay tên phương thức:

```java
@Bean(name = "inventoryHealthIndicator")
HealthIndicator supplyProbe() {
    return () -> Health.up().build();
}
```

Bean mang tên `inventoryHealthIndicator`, nên ID health là `inventory`. Tên phương thức `supplyProbe` không tạo ra một thành phần health cùng tên.

Các đoạn trên nằm trong một lớp cấu hình Spring và cần import `Bean`, `Health`, `HealthIndicator`. Quy tắc tên mặc định và tên tường minh của `@Bean` được mô tả trong [API Spring Framework 6.1.8](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/annotation/Bean.html).

Với một lớp được quét bằng `@Component`, tên bean mặc định thường được suy ra từ tên lớp. Chẳng hạn lớp `InventoryHealthIndicator` thông thường tạo bean `inventoryHealthIndicator` rồi được định danh health là `inventory`. Nếu `@Component` có tên tường minh, cần xét tên bean đã chỉ định đó.

### 2.2. Quy tắc bỏ hậu tố

Trong cơ chế đặt tên chuẩn, `HealthContributorNameFactory` chuyển tên bean thành tên contributor. Các ví dụ kiểm chứng trong bài:

| Tên bean đầu vào | ID contributor |
| --- | --- |
| `searchHealthIndicator` | `search` |
| `inventoryHealthIndicator` | `inventory` |
| `checkoutHealthContributor` | `checkout` |
| `inventory` | `inventory` |
| `inventoryHealthIndicatorV2` | `inventoryHealthIndicatorV2` |
| `searchhealthindicator` | `search` |
| `InventoryHealthIndicator` | `Inventory` |

Điểm cần đọc đúng:

- Hậu tố `HealthIndicator` hoặc `HealthContributor` được bỏ khỏi tên bean khi phù hợp.
- Không cắt một chuỗi nằm giữa tên: `inventoryHealthIndicatorV2` không kết thúc bằng hậu tố đó nên được giữ nguyên.
- Trong phiên bản thử nghiệm, phép so khớp hậu tố không phân biệt chữ hoa/chữ thường. Điều này **không có nghĩa toàn bộ ID được đổi sang chữ thường**: `InventoryHealthIndicator` vẫn tạo `Inventory`.
- Phần tên còn lại là tên được dùng để tra cứu. Đừng tự đổi `inventory` thành `Inventory` trong URL.

Tài liệu hướng dẫn mô tả quy tắc bỏ hậu tố `HealthIndicator`; bảng ở trên được kiểm chứng thêm bằng API đặt tên của Spring Boot 3.3.0 trong chương trình ở mục 8. [Quy ước định danh HealthIndicator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

### 2.3. Alias không tự tạo thêm ID health

Một bean có thể có tên chính và alias:

```java
@Bean(name = {"inventoryHealthIndicator", "stockAlias"})
HealthIndicator supplyProbe() {
    return () -> Health.up().build();
}
```

Trong container, có thể tra cứu cùng bean bằng tên `stockAlias`. Nhưng với cơ chế thu thập bean và registry chuẩn trong thí nghiệm:

```text
Bean chính: inventoryHealthIndicator
Alias Spring: stockAlias
ID health: inventory
```

`/actuator/health/inventory` tồn tại, còn `/actuator/health/stockAlias` không tự xuất hiện. Alias phục vụ tra cứu bean Spring; nó không phải một khai báo bổ sung endpoint.

Điều này đặc biệt cần nhớ khi đổi tên: thêm alias của tên cũ không tự bảo đảm URL health cũ tiếp tục tồn tại.

### 2.4. Tránh hai tên bean rút thành cùng một ID

Hai bean tên `inventory` và `inventoryHealthIndicator` có thể cùng dẫn đến ID `inventory`. Hai tên bean khác nhau chưa bảo đảm hai ID health khác nhau.

Hãy thiết kế ID duy nhất sau bước chuyển tên, thay vì dựa vào khác biệt của hậu tố. Khi kiểm tra một cấu hình thật, đối chiếu các ID trong registry để chắc rằng mọi phép kiểm tra mong muốn đều có tên riêng rõ ràng.

`@Primary` hoặc `@Qualifier` phục vụ lựa chọn bean khi tiêm phụ thuộc; chúng không phải công cụ tự đổi ID health. Không coi `@Primary` là cách chọn một indicator duy nhất để thay thế toàn bộ tập contributor của endpoint.

## 3. Contributor đơn và contributor tổng hợp

`HealthContributor` là kiểu chung của các thành phần cung cấp health. Hai dạng cần phân biệt:

| Kiểu | Vai trò | Có nút con để đi tiếp trong cây? |
| --- | --- | --- |
| `HealthIndicator` | Thực hiện phép kiểm tra và trả `Health` | Không |
| `CompositeHealthContributor` | Chứa các contributor có tên | Có |

Một composite là cấu trúc các phép kiểm tra, không phải một `Health` đã tính sẵn. Khi cần dựng kết quả, Actuator duyệt các contributor rồi tạo dữ liệu health tương ứng. [API HealthContributor 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributor.html)

### 3.1. Tên con lấy từ khóa map

Có thể tạo composite bằng `CompositeHealthContributor.fromMap`:

```java
HealthIndicator database = () -> Health.up().build();
HealthIndicator cache = () -> Health.up().build();

CompositeHealthContributor checkout =
        CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "database", database,
                        "cache", cache));
```

Đây là đoạn dựng đối tượng, cần import `java.util.Map` và các kiểu health. Để nó trở thành contributor ở gốc theo cơ chế thu thập chuẩn, phải trả nó từ một bean hoặc đăng ký nó qua registry.

Nếu bean gốc tên `checkoutHealthContributor`, cây là:

```text
checkout
├── database
└── cache
```

Các khóa `database` và `cache` là **tên con được cung cấp trực tiếp**, không được suy lại từ tên biến Java.

`fromMap` nhận một map từ tên sang `HealthContributor`; giá trị có thể là indicator hoặc một composite khác. [API CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html)

### 3.2. Quy tắc tên gốc không tự áp dụng lại cho khóa con

Giả sử map dùng khóa:

```java
"cacheHealthIndicator"
```

Tên con vẫn là `cacheHealthIndicator`. Không tự bỏ hậu tố để biến nó thành `cache`.

Vì vậy hai bước này khác nhau:

```text
Tên bean gốc checkoutHealthContributor -> checkout

Khóa con trong map cacheHealthIndicator -> cacheHealthIndicator
```

Ví dụ hoàn chỉnh bên dưới cố ý giữ một khóa con có hậu tố để chứng minh sự khác biệt. Khi thiết kế thực tế, thường nên chọn tên con ngắn gọn như `cache` ngay trong map.

### 3.3. Ghép composite để tạo nhiều cấp

Cây sau có một composite lồng trong composite:

```text
checkout
├── database
├── cacheHealthIndicator
└── payment
    ├── primary
    └── backup
```

`checkout` và `payment` là nút tổng hợp. `database`, `cacheHealthIndicator`, `primary` và `backup` là các lá thực hiện phép kiểm tra.

Các lá trong ví dụ được tạo bằng phương thức trợ giúp không gắn `@Bean`. Nhờ vậy chúng chỉ được đưa vào cây qua map của composite, không đồng thời được thu thập thành những contributor ở gốc.

Nếu chủ động khai báo một lá là bean riêng rồi lại đưa nó vào composite, nó có thể xuất hiện ở cả hai vị trí. Hãy quyết định rõ mình muốn một nút ở gốc, một nút con hay cả hai; đừng vô tình tạo hai đường quan sát cùng phép kiểm tra.

## 4. Đường dẫn là đường đi qua cây contributor

Với base path mặc định, endpoint health ở `/actuator/health`. Các đoạn tiếp theo là những tên mà registry và composite có thể tra cứu:

```text
/actuator/health/{root-id}/{child-name}/{grandchild-name}
```

Ví dụ cây ở mục 3:

| Đường dẫn | Nút được đọc |
| --- | --- |
| `/actuator/health` | Kết quả tổng của hệ thống |
| `/actuator/health/checkout` | Nhánh checkout |
| `/actuator/health/checkout/payment` | Nhánh payment trong checkout |
| `/actuator/health/checkout/payment/primary` | Lá primary |
| `/actuator/health/checkout/payment/backup` | Lá backup |

Cơ chế xử lý lần lượt tra cứu mỗi tên trên các đối tượng chứa contributor có tên. Nó không phân tích package Java để tìm các cấp của đường dẫn. [Mã xử lý cây trong HealthEndpointSupport 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java)

### 4.1. Không thêm components vào URL

JSON có thể hiển thị:

```json
{
  "status": "UP",
  "details": {
    "target": "inventory-store"
  }
}
```

Đây là phản hồi của một lá `inventory` trong ví dụ. Trường `target` là dữ liệu chi tiết, không phải nút con; `/actuator/health/inventory/target` không trở thành đường dẫn health.

Tương tự, `components` trong JSON của một nút tổng hợp là tên trường biểu diễn dữ liệu. Đường dẫn đến payment vẫn là:

```text
/actuator/health/checkout/payment
```

không phải:

```text
/actuator/health/components/checkout/components/payment
```

Muốn có một đoạn con thực sự, phải tổ chức nó bằng một contributor có tên trong composite.

### 4.2. Nút cha và lá có thể có trạng thái khác nhau

Nếu `payment/primary` là `UP` còn `payment/backup` là `DOWN`, bộ tổng hợp mặc định có thể làm `payment` và `checkout` báo `DOWN`, trong khi đường dẫn riêng đến `primary` vẫn báo `UP`.

Vì thế việc một URL lá trả thành công không có nghĩa toàn bộ cây đã khỏe. Hãy xác định đang đọc một lá, một nhánh hay toàn hệ thống.

## 5. Ứng dụng HTTP chạy được

Ứng dụng này không gọi cơ sở dữ liệu hoặc dịch vụ thanh toán thật. Các kết quả cố định giúp quan sát tên và đường dẫn mà không bị ảnh hưởng bởi hạ tầng ngoài.

### 5.1. Cấu trúc tệp

```text
health-path-demo/
├── pom.xml
└── src/main/
    ├── java/example/healthpaths/HealthPathApplication.java
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
    <artifactId>health-path-demo</artifactId>
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

`src/main/java/example/healthpaths/HealthPathApplication.java`:

```java
package example.healthpaths;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthPathApplication.class, args);
    }

    @Bean
    public HealthIndicator searchHealthIndicator() {
        return up("search-service");
    }
    
    @Bean(name = {"inventoryHealthIndicator", "stockAlias"})
    public HealthIndicator supplyProbe() {
        return up("inventory-store");
    }
    
    @Bean("checkoutHealthContributor")
    public CompositeHealthContributor checkoutTree() {
        CompositeHealthContributor payment = CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "primary", up("payment-primary"),
                        "backup", (HealthIndicator) () -> Health.down()
                                .withDetail("target", "payment-backup").build()));
        return CompositeHealthContributor.fromMap(
                Map.<String, HealthContributor>of(
                        "database", up("checkout-database"),
                        "payment", payment,
                        "cacheHealthIndicator", up("checkout-cache")));
    }
    
    private static HealthIndicator up(String target) {
        return () -> Health.up().withDetail("target", target).build();
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=health-path-demo
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.probes.enabled=false
management.health.livenessstate.enabled=false
management.health.readinessstate.enabled=false
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.group.dependencies.include=checkout
```

Mục đích các cấu hình:

- Loại indicator tự cấu hình và probes khỏi thí nghiệm để chỉ quan sát cây do mã mẫu tạo.
- Cho phép nhìn thành phần và chi tiết trong môi trường thử cục bộ.
- Tạo nhóm `dependencies` có thành viên là nhánh `checkout`.

Các bean trong ví dụ không gắn điều kiện theo `management.health.defaults.enabled` nên vẫn được tạo. Không hiểu công tắc đó là lệnh xóa mọi bean health tự khai báo.

Trong ứng dụng triển khai thực, chọn lại chính sách hiển thị phù hợp với quyền người gọi. Các giá trị `always` ở đây giúp quan sát bài thử, không phải yêu cầu công khai chi tiết health.

### 5.2. Cây nhận được

```text
HealthContributorRegistry
├── checkout                    bean: checkoutHealthContributor
│   ├── cacheHealthIndicator    UP
│   ├── database                UP
│   └── payment
│       ├── primary             UP
│       └── backup              DOWN
├── inventory                   bean: inventoryHealthIndicator
└── search                      bean: searchHealthIndicator
```

Thứ tự hiển thị các khóa JSON không phải hợp đồng của ví dụ; không dùng thứ tự map để suy ra thứ tự kiểm tra hoặc mức ưu tiên trạng thái.

`stockAlias` có trong container dưới dạng alias của bean inventory nhưng không trở thành một contributor riêng ở gốc.

### 5.3. Đóng gói và chạy

Tại thư mục chứa `pom.xml`, với Maven và JDK 21:

```powershell
mvn -q package
java -jar target/health-path-demo-1.0.0.jar
```

Chờ ứng dụng khởi động thành công. Mở terminal khác và gọi một lá:

```powershell
curl.exe -sS http://localhost:8080/actuator/health/inventory
```

Nội dung JSON:

```json
{"status":"UP","details":{"target":"inventory-store"}}
```

Các lệnh PowerShell dùng `curl.exe` để tránh alias `curl` của một số phiên bản. Với Bash, dùng chương trình `curl` tương ứng.

Lấy riêng mã HTTP của primary:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/checkout/payment/primary
```

Stdout:

```text
200
```

Kiểm tra backup:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/checkout/payment/backup
```

Stdout:

```text
503
```

`NUL` là đích bỏ phần thân trên Windows; trên Linux/macOS thay bằng `/dev/null`. Không dùng `--fail` khi mục tiêu là quan sát cả phản hồi lỗi và phần thân của nó.

### 5.4. Bảng đường dẫn đúng và sai

Với cấu hình mẫu và truy cập trực tiếp ứng dụng:

| Phần sau `/actuator/health` | Kết quả HTTP | Trạng thái health nếu có |
| --- | --- | --- |
| Không có phần sau | `503` | `DOWN` |
| `/search` | `200` | `UP` |
| `/inventory` | `200` | `UP` |
| `/Inventory` | `404` | Không có kết quả health tại đường dẫn đó |
| `/inventoryHealthIndicator` | `404` | Đang dùng tên bean thay vì ID |
| `/stockAlias` | `404` | Alias không tự tạo đường dẫn |
| `/inventory/target` | `404` | `target` chỉ là khóa trong details |
| `/checkout` | `503` | `DOWN` |
| `/checkout/payment` | `503` | `DOWN` |
| `/checkout/payment/primary` | `200` | `UP` |
| `/checkout/payment/backup` | `503` | `DOWN` |
| `/checkout/cacheHealthIndicator` | `200` | `UP` |
| `/checkout/cache` | `404` | Khóa con thực tế có cả hậu tố |
| `/components/checkout` | `404` | `components` không phải nút gốc |

Các mã này được đối chiếu bằng lớp mở rộng HTTP thực của health trong chương trình ở mục 8. Nếu ứng dụng có Spring Security, proxy hoặc base path khác, phải xét thêm những lớp đó trước khi so sánh URL.

## 6. Nhóm health tạo thêm phạm vi, không thay cây thành phần

Cấu hình trong ứng dụng mẫu:

```properties
management.endpoint.health.group.dependencies.include=checkout
```

tạo nhóm `dependencies`. Một đường dẫn thuộc nhóm có dạng:

```text
/actuator/health/dependencies/checkout/payment/primary
                 nhóm       gốc      con     cháu
```

`dependencies` là tên nhóm. `checkout` vẫn là ID contributor ở gốc; không bỏ đoạn này chỉ vì nhóm đã chọn checkout.

| Đường dẫn | Kết quả trong ví dụ |
| --- | --- |
| `/actuator/health/dependencies` | Tổng của nhóm, `503 DOWN` |
| `/actuator/health/dependencies/checkout/payment/primary` | Lá primary trong nhóm, `200 UP` |
| `/actuator/health/dependencies/payment/primary` | `404` vì thiếu cấp checkout |

Một nhóm là một cách chọn tập contributor để quan sát. Nó không chuyển bean checkout thành bean con của một đối tượng Java mới.

Spring Boot hỗ trợ chọn cả composite hoặc một thành phần theo tên đầy đủ như `checkout/payment` trong cấu hình nhóm. [Health groups của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups)

### 6.1. Dùng ID/path trong cấu hình nhóm

Khi viết `include` hoặc `exclude`, dùng tên contributor thực tế, không dùng tên lớp hoặc tên bean dài:

```properties
management.endpoint.health.group.dependencies.include=checkout
```

khác với việc tự đoán:

```properties
management.endpoint.health.group.dependencies.include=checkoutHealthContributor
```

Tên sau không tồn tại dưới dạng ID gốc trong ví dụ. Cơ chế kiểm tra thành viên nhóm có thể báo lỗi lúc khởi động khi tham chiếu contributor không có thật.

Cũng nên giữ tên nhóm khác tên contributor ở gốc. Trong xử lý chuẩn, đoạn đầu được xét như tên nhóm trước khi được dùng như đường đi của hệ thống; trùng tên có thể làm URL không còn mang nghĩa bạn dự định. Không dùng trùng tên để mô phỏng quan hệ cha–con.

### 6.2. Thay base path không đổi ID

Nếu cấu hình:

```properties
management.endpoints.web.base-path=/manage
```

đường dẫn mẫu trở thành:

```text
/manage/health/checkout/payment/primary
```

`checkout/payment/primary` vẫn là cùng đường đi trong cây. Base path là vị trí xuất bản các endpoint; nó không đổi tên bean hoặc ID contributor.

Nếu có management port, context path hoặc proxy phía trước, hãy xác định địa chỉ ứng dụng thực tế đang công bố. Không thêm các tiền tố mạng ấy vào tên bean để cố làm URL khớp.

## 7. Vì sao contributor có thật vẫn có thể trả 404?

### 7.1. show-components chi phối đường dẫn thành phần

Trong Spring Boot 3.3, nếu người gọi không được hiển thị component theo chính sách của nhóm đang truy cập, truy vấn một đường dẫn con có thể không được trả kết quả, dù contributor vẫn đăng ký.

Thử dừng ứng dụng rồi chạy:

```powershell
java -jar target/health-path-demo-1.0.0.jar --management.endpoint.health.show-components=never
```

Cấu hình `show-details=always` của tệp vẫn giữ nguyên, nhưng:

```text
/actuator/health             -> 503 DOWN
/actuator/health/inventory   -> 404
```

Phép kiểm tra health tổng vẫn tính các trạng thái. `404` ở đường dẫn con không đủ để kết luận bean inventory đã bị tắt.

Trong mã xử lý, cờ cho phép hiển thị component được xét trước khi đi đến một nút không phải gốc của phạm vi đang truy cập. [HealthEndpointSupport 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java)

### 7.2. show-details là chính sách khác

Dừng ứng dụng trước rồi chạy:

```powershell
java -jar target/health-path-demo-1.0.0.jar --management.endpoint.health.show-components=always --management.endpoint.health.show-details=never
```

`/actuator/health/inventory` vẫn truy cập được và trả `200`, nhưng không công khai trường `details`:

```json
{"status":"UP"}
```

Tách riêng hai câu hỏi:

- Người gọi có được nhìn và truy cập component hay không?
- Nếu đã được đọc kết quả đó, người gọi có được xem dữ liệu chi tiết hay không?

Với `when-authorized`, còn phải xét danh tính, vai trò và chính sách của đúng nhóm. Bài không mặc định mọi người gọi đều có quyền chỉ vì bean đã có trong container.

### 7.3. Không quy mọi 404 cho một lỗi đặt tên

Khi gặp `404`, kiểm tra theo thứ tự hữu ích:

1. Đang gọi đúng host, cổng, base path và endpoint health chưa?
2. Đoạn đầu có đang chọn một nhóm health hay không?
3. ID gốc thực tế là gì sau bước chuyển tên bean?
4. Từng đoạn con có đúng khóa composite, đúng chữ hoa/chữ thường không?
5. Người gọi có được nhìn component trong phạm vi đó không?
6. Contributor có thuộc nhóm đang truy cập không?

Một lớp bảo mật hoặc proxy cũng có thể làm kết quả quan sát khác với phản hồi trực tiếp của Actuator. Khi chẩn đoán, phân biệt registry, dữ liệu hiển thị và phản hồi HTTP.

## 8. Chương trình Java kiểm chứng tên, alias và đường dẫn

Chương trình sau dựng ApplicationContext nhỏ, dùng cơ chế đăng ký health và nhóm của Spring Boot, rồi gọi `HealthEndpointWebExtension` để kiểm tra phản hồi.

Nó **không mở socket HTTP**. Các dòng `200`, `503`, `404` là mã của `WebEndpointResponse` do lớp mở rộng HTTP của health trả về. Bởi vậy nó kiểm chứng trực tiếp quy tắc Actuator, còn ứng dụng ở mục 5 dùng để thử thêm qua mạng thật.

Tạo `experiments/HealthPathExperiment.java` ngoài `src/main/java` của dự án mẫu, để không thêm một main khác vào JAR Spring Boot:

```java
import java.time.Duration;
import java.util.Map;
import java.util.TreeSet;
import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.endpoint.ApiVersion;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.boot.actuate.endpoint.web.WebServerNamespace;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthContributorNameFactory;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthEndpointGroups;
import org.springframework.boot.actuate.health.HealthEndpointWebExtension;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.NamedContributor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class HealthPathExperiment {
    @Configuration(proxyBeanMethods = false)
    static class Indicators {
        @Bean
        public HealthIndicator searchHealthIndicator() {
            return up("search-service");
        }
        
        @Bean(name = {"inventoryHealthIndicator", "stockAlias"})
        public HealthIndicator supplyProbe() {
            return up("inventory-store");
        }
        
        @Bean("checkoutHealthContributor")
        public CompositeHealthContributor checkoutTree() {
            CompositeHealthContributor payment = CompositeHealthContributor.fromMap(
                    Map.<String, HealthContributor>of(
                            "primary", up("payment-primary"),
                            "backup", (HealthIndicator) () -> Health.down()
                                    .withDetail("target", "payment-backup").build()));
            return CompositeHealthContributor.fromMap(
                    Map.<String, HealthContributor>of(
                            "database", up("checkout-database"),
                            "payment", payment,
                            "cacheHealthIndicator", up("checkout-cache")));
        }
        
        private static HealthIndicator up(String target) {
            return () -> Health.up().withDetail("target", target).build();
        }
    }

    static AnnotationConfigApplicationContext context(
            String showComponents, String showDetails) {
        var context = new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("experiment", Map.of(
                        "management.endpoint.health.show-components", showComponents,
                        "management.endpoint.health.show-details", showDetails,
                        "management.endpoint.health.group.dependencies.include", "checkout")));
        context.register(Indicators.class, HealthEndpointAutoConfiguration.class);
        context.refresh();
        return context;
    }

    static HealthEndpointWebExtension extension(
            AnnotationConfigApplicationContext context) {
        return new HealthEndpointWebExtension(
                context.getBean(HealthContributorRegistry.class),
                context.getBean(HealthEndpointGroups.class), Duration.ofSeconds(10));
    }

    static void inspect(HealthEndpointWebExtension extension, String... path) {
        var response = extension.health(ApiVersion.V3, WebServerNamespace.SERVER,
                SecurityContext.NONE, false, path);
        String status = response.getBody() == null ? "-"
                : response.getBody().getStatus().getCode();
        String route = "/actuator/health"
                + (path.length == 0 ? "" : "/" + String.join("/", path));
        System.out.println(route + " -> " + response.getStatus() + " " + status);
    }

    public static void main(String[] args) {
        for (String name : java.util.List.of("searchHealthIndicator",
                "inventoryHealthIndicator", "checkoutHealthContributor",
                "inventory", "inventoryHealthIndicatorV2", "searchhealthindicator",
                "InventoryHealthIndicator")) {
            System.out.println("name " + name + " -> "
                    + HealthContributorNameFactory.INSTANCE.apply(name));
        }
        try (var context = context("always", "always")) {
            var registry = context.getBean(HealthContributorRegistry.class);
            var names = new TreeSet<String>();
            for (NamedContributor<HealthContributor> item : registry) {
                names.add(item.getName());
            }
            System.out.println("roots=" + names);
            System.out.println("aliasBean=" + context.containsBean("stockAlias"));
            System.out.println("aliasContributor="
                    + (registry.getContributor("stockAlias") != null));
            var extension = extension(context);
            inspect(extension);
            inspect(extension, "search");
            inspect(extension, "inventory");
            inspect(extension, "Inventory");
            inspect(extension, "inventory", "target");
            inspect(extension, "inventoryHealthIndicator");
            inspect(extension, "stockAlias");
            inspect(extension, "checkout");
            inspect(extension, "checkout", "payment");
            inspect(extension, "checkout", "payment", "primary");
            inspect(extension, "checkout", "payment", "backup");
            inspect(extension, "checkout", "cacheHealthIndicator");
            inspect(extension, "checkout", "cache");
            inspect(extension, "components", "checkout");
            inspect(extension, "dependencies");
            inspect(extension, "dependencies", "checkout", "payment", "primary");
            inspect(extension, "dependencies", "payment", "primary");
        }
        try (var context = context("never", "always")) {
            System.out.println("hidden-components:");
            inspect(extension(context));
            inspect(extension(context), "inventory");
        }
        try (var context = context("always", "never")) {
            System.out.println("hidden-details:");
            inspect(extension(context), "inventory");
        }
    }
}
```

Biên dịch và chạy trong PowerShell tại thư mục chứa `pom.xml`:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$healthPathClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $healthPathClasspath experiments/HealthPathExperiment.java
java -cp "$healthPathClasspath;experiments" HealthPathExperiment
```

Trên Linux/macOS, dùng `:` phân cách classpath và cú pháp đọc tệp phù hợp với shell.

Các dòng stdout do chương trình tạo:

```text
name searchHealthIndicator -> search
name inventoryHealthIndicator -> inventory
name checkoutHealthContributor -> checkout
name inventory -> inventory
name inventoryHealthIndicatorV2 -> inventoryHealthIndicatorV2
name searchhealthindicator -> search
name InventoryHealthIndicator -> Inventory
roots=[checkout, inventory, search]
aliasBean=true
aliasContributor=false
/actuator/health -> 503 DOWN
/actuator/health/search -> 200 UP
/actuator/health/inventory -> 200 UP
/actuator/health/Inventory -> 404 -
/actuator/health/inventory/target -> 404 -
/actuator/health/inventoryHealthIndicator -> 404 -
/actuator/health/stockAlias -> 404 -
/actuator/health/checkout -> 503 DOWN
/actuator/health/checkout/payment -> 503 DOWN
/actuator/health/checkout/payment/primary -> 200 UP
/actuator/health/checkout/payment/backup -> 503 DOWN
/actuator/health/checkout/cacheHealthIndicator -> 200 UP
/actuator/health/checkout/cache -> 404 -
/actuator/health/components/checkout -> 404 -
/actuator/health/dependencies -> 503 DOWN
/actuator/health/dependencies/checkout/payment/primary -> 200 UP
/actuator/health/dependencies/payment/primary -> 404 -
hidden-components:
/actuator/health -> 503 DOWN
/actuator/health/inventory -> 404 -
hidden-details:
/actuator/health/inventory -> 200 UP
```

Các log thư viện nếu có không thuộc những dòng kết quả này. Dấu `-` sau `404` nghĩa là phản hồi thử nghiệm không chứa đối tượng kết quả health, không phải một trạng thái health mới.

Chương trình đối chiếu ba mặt của cùng thiết kế:

- Tên bean chuyển thành ID như thế nào.
- Alias có tồn tại trong Spring nhưng có trở thành contributor riêng không.
- Các đoạn đường dẫn, nhóm và chính sách hiển thị có cho truy cập nút mong muốn không.

## 9. Đặt tên để cây health dễ vận hành

### 9.1. Cố định tên công khai khi cần giữ hợp đồng

Nếu URL `/actuator/health/inventory` đã được hệ thống giám sát sử dụng, thay tên phương thức `@Bean` không có tên tường minh có thể làm đổi ID.

Muốn đổi tên phương thức mà giữ tên công khai:

```java
@Bean(name = "inventoryHealthIndicator")
HealthIndicator checkWarehouseAvailability() {
    return () -> Health.up().build();
}
```

ID vẫn là `inventory` vì tên bean tường minh không đổi. Tương tự, giữ ổn định các khóa map khi muốn giữ nguyên đường dẫn con.

Khi đổi ID có chủ đích, rà soát:

- URL mà công cụ giám sát đang gọi.
- `include`/`exclude` của các nhóm.
- Hướng dẫn vận hành và các phép thử đường dẫn.
- Những thành phần khác đang tra cứu trực tiếp registry.

Không dựa vào alias bean như một cơ chế tự động duy trì hai URL health.

### 9.2. Chọn tên theo vai trò quan sát

Tên tốt giải thích nút đang kiểm tra cái gì, ví dụ `checkout/database` hoặc `checkout/payment/primary`. Tránh đưa tên lớp triển khai dài, giá trị thay đổi theo từng lần khởi động hoặc dữ liệu người dùng vào ID.

Để thể hiện phân cấp, dùng composite thật. Không đặt một tên bean chứa nhiều dấu `/` rồi trông chờ Actuator tự tạo từng cấp, và không dùng một map trong `details` thay cho composite.

Nếu nhiều nhánh cùng có con tên `primary` thì không nhất thiết xung đột, vì đường dẫn đầy đủ khác nhau, ví dụ `checkout/payment/primary` và `reporting/database/primary`. Điều cần giữ duy nhất là tên trong cùng phạm vi cha.

### 9.3. Không kéo dài cây nếu không giúp chẩn đoán

Composite hữu ích khi một miền có nhiều phép kiểm tra liên quan và cần xem tổng lẫn từng phần. Một phép kiểm tra đơn không cần thêm nhiều lớp cha chỉ để làm URL trông có cấu trúc.

Hãy chọn độ sâu giúp người vận hành tìm được nguyên nhân: nhánh nào hỏng, lá nào hỏng và kết quả đó đang ảnh hưởng phạm vi nào.

## 10. Thực hành tự kiểm tra

1. Đổi tên phương thức `supplyProbe` trong dự án mẫu nhưng giữ `@Bean(name=...)`. Dự đoán URL inventory có đổi hay không rồi kiểm tra.
2. Bỏ tên tường minh trên bean inventory. Xác định tên bean mới, ID mới và URL mới trước khi khởi động lại.
3. Đổi khóa con `cacheHealthIndicator` thành `cache`. Kiểm tra đường dẫn cũ và mới; giải thích vì sao thay đổi này khác với quy tắc bỏ hậu tố tên bean.
4. Thêm một lá `secondary` dưới `payment`, không khai báo nó thành bean ở gốc. Kiểm tra rằng cây có đường dẫn con mới nhưng không tự có `/actuator/health/secondary`.
5. Giữ contributor inventory trong registry, lần lượt ẩn chi tiết và ẩn component. Đối chiếu sự khác nhau ở JSON và mã phản hồi đường dẫn con.
6. Viết một bảng cho cây health của ứng dụng: tên bean chính, ID gốc, tên con, đường dẫn đầy đủ, nhóm có sử dụng và người gọi được phép quan sát.

Khi dự đoán một URL, hãy đi theo chuỗi **tên bean chính → ID gốc → khóa từng composite → phạm vi nhóm → chính sách hiển thị**. Chuỗi đó cho biết vì sao một đường dẫn tồn tại và vì sao người gọi cụ thể có thể hoặc không thể đọc nó.
