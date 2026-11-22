# Tổ chức nhiều thành phần bằng composite health contributor

## 1. Từ một phép kiểm tra đến một cây sức khỏe

Giả sử chức năng mua hàng cần kho hàng và hai kết nối thanh toán theo khu vực. Nếu chỉ trả về một trạng thái `DOWN`, người vận hành biết chức năng đang có vấn đề nhưng chưa biết nhánh nào hỏng. Nếu đưa mọi phép kiểm tra lên cùng một cấp, cấu trúc kết quả lại khó phản ánh quan hệ giữa chúng.

Một **bộ đóng góp sức khỏe tổng hợp (composite health contributor)** tổ chức nhiều thành phần có tên thành một cây. Mỗi lá thực hiện một phép kiểm tra; mỗi nút tổng hợp chứa các thành phần con. Khi đọc health, Actuator đi qua cây, lấy kết quả từ các lá và tổng hợp trạng thái cho từng nhánh.

Bài này dùng Spring Boot 3.3.x và Java 17 trở lên; ví dụ dự án chọn JDK 21. Mục tiêu là tạo được cây health, đọc đúng kết quả và tránh nhầm cấu trúc cây với chính sách đánh giá sức khỏe.

Cây sẽ xây dựng:

```text
health
└── commerce
    ├── inventory
    └── payments
        ├── eu
        └── us
```

- `commerce`: nhánh phục vụ mua hàng.
- `inventory`: phép kiểm tra kho hàng.
- `payments`: nhánh chứa các phép kiểm tra thanh toán.
- `eu`, `us`: hai lá thanh toán độc lập.

Tên khu vực chỉ là ví dụ. Chương trình mô phỏng trạng thái bằng cấu hình, không gọi kho hàng, ngân hàng hay dịch vụ bên ngoài.

## 2. Các kiểu dữ liệu có vai trò gì?

| Kiểu | Vai trò trong bài |
| --- | --- |
| `HealthContributor` | Kiểu chung để đăng ký một thành phần vào hệ thống health. |
| `HealthIndicator` | Lá cung cấp kết quả `Health` qua phương thức `health()`. |
| `CompositeHealthContributor` | Nút chứa các `HealthContributor` con có tên; con có thể tiếp tục là một composite. |
| `Health` | Kết quả của một phép kiểm tra, gồm `status` và có thể có `details`. |
| `CompositeHealth` | Kết quả tổng hợp chứa trạng thái và các kết quả thành phần. |
| `StatusAggregator` | Chính sách chọn trạng thái tổng hợp từ các trạng thái con. |

`HealthIndicator` là functional interface nên có thể viết bằng lambda. `CompositeHealthContributor` cung cấp việc duyệt các con và tìm con theo tên; nó không có phương thức `health()` để gọi giống một indicator. Xem [API HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) và [API CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Cần phân biệt hai phía:

```text
Cấu trúc dùng để thực hiện kiểm tra        Kết quả sau khi thực hiện
HealthIndicator                    -->  Health
CompositeHealthContributor         -->  CompositeHealth
```

Do đó, không trả một `CompositeHealth` từ phương thức `@Bean` với mong đợi Spring tự coi đó là bộ kiểm tra. Đối tượng kết quả không thay thế cho đối tượng thực hiện kiểm tra. [API CompositeHealth](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealth.html) mô tả phía kết quả này.

Một điều dễ nhầm khác: đặt nhiều giá trị vào `Health.up().withDetail(...)` chỉ tạo dữ liệu chi tiết của một lá. Những giá trị ấy không tự trở thành các thành phần health có thể truy vấn và tổng hợp riêng.

## 3. Dự án chạy đầy đủ

### 3.1. Cấu trúc tệp

Tạo một thư mục độc lập với cấu trúc:

```text
composite-health-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── health/
        │           └── CompositeHealthApplication.java
        └── resources/
            └── application.properties
```

Hai dependency cần thiết là Web và Actuator. Không cần cơ sở dữ liệu, Docker hoặc Spring Security cho thí nghiệm cục bộ này.

Nội dung `pom.xml`:

```xml
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
    <artifactId>composite-health-demo</artifactId>
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

Phiên bản được cố định để thí nghiệm có thể tái lập trong dòng Spring Boot 3.3. Khi áp dụng vào dự án khác, dùng phiên bản vá đã được dự án phê duyệt thay vì sao chép số phiên bản một cách máy móc.

### 3.2. Khai báo một composite chứa composite

Nội dung `src/main/java/example/health/CompositeHealthApplication.java`:

```java
package example.health;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class CompositeHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompositeHealthApplication.class, args);
    }

    @Bean(name = "commerce")
    CompositeHealthContributor commerce(
            @Value("${demo.inventory-up:true}") boolean inventoryUp,
            @Value("${demo.payment-eu-up:false}") boolean paymentEuUp) {

        HealthIndicator inventory = () -> simulated("inventory", inventoryUp);
        HealthIndicator eu = () -> simulated("eu", paymentEuUp);
        HealthIndicator us = () -> simulated("us", true);

        Map<String, HealthContributor> paymentChildren = new LinkedHashMap<>();
        paymentChildren.put("eu", eu);
        paymentChildren.put("us", us);
        CompositeHealthContributor payments =
                CompositeHealthContributor.fromMap(paymentChildren);

        Map<String, HealthContributor> commerceChildren = new LinkedHashMap<>();
        commerceChildren.put("inventory", inventory);
        commerceChildren.put("payments", payments);
        return CompositeHealthContributor.fromMap(commerceChildren);
    }

    private static Health simulated(String check, boolean available) {
        Health.Builder builder = available ? Health.up() : Health.down();
        return builder.withDetail("check", check)
                .withDetail("mode", "simulation")
                .build();
    }
}
```

Có bốn điểm cần đọc theo thứ tự:

1. Ba biến `inventory`, `eu`, `us` là ba `HealthIndicator`. Lambda chỉ thực hiện khi `health()` được gọi; việc tạo lambda chưa thực hiện kiểm tra.
2. `paymentChildren` ánh xạ tên con tới đối tượng thực hiện kiểm tra. `fromMap` tạo nhánh `payments` từ ánh xạ đó.
3. `commerceChildren` chứa cả một lá và một composite, nên kiểu giá trị là `HealthContributor`, không phải `HealthIndicator`.
4. Chỉ `commerce` được khai báo là bean. Các lá và nhánh `payments` được truy cập thông qua cây này.

`LinkedHashMap` giúp mã thể hiện thứ tự thêm các con một cách rõ ràng. Phần mềm đọc JSON phải dựa vào tên thuộc tính, không dựa vào vị trí hay thứ tự trường trong phản hồi.

Ở đây không có kết nối thanh toán thật. Hàm `simulated` chỉ xây dựng kết quả ổn định để tập trung quan sát cấu trúc cây.

### 3.3. Cấu hình cho thí nghiệm cục bộ

Nội dung `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always

demo.inventory-up=true
demo.payment-eu-up=false
```

`show-components` điều khiển việc hiển thị cây thành phần; `show-details` điều khiển dữ liệu chi tiết của các phép kiểm tra. Hai tùy chọn hiển thị không làm thay đổi kết quả kiểm tra.

Cấu hình `always` ở đây phục vụ quan sát trên máy cá nhân. Khi đưa vào môi trường vận hành, chọn quyền xem và chính sách truy cập phù hợp; không đưa thông tin bí mật vào `details`. Tài liệu [Health Information và Health Groups](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health) giải thích các thuộc tính hiển thị, ánh xạ trạng thái HTTP và nhóm health.

### 3.4. Biên dịch và chạy

Từ thư mục có `pom.xml`, dùng JDK 21 và Maven:

```shell
mvn clean package
java -jar target/composite-health-demo-1.0.0.jar
```

Đây là ứng dụng có dependency Spring Boot, vì vậy không dùng `javac CompositeHealthApplication.java` đơn lẻ với classpath trống. Maven giải quyết dependency và tạo JAR chạy được. Lần build đầu cần tải dependency nếu máy chưa có bộ nhớ đệm.

Mở terminal khác:

```shell
curl -i http://127.0.0.1:8080/actuator/health/commerce
```

Trên Windows PowerShell, có thể dùng `curl.exe` để gọi đúng chương trình curl. Nhật ký khởi động có thời gian và thông tin môi trường nên không có một stdout cố định cho toàn bộ tiến trình.

Với cấu hình trên, mã HTTP là **503**, phần thân JSON có cấu trúc sau; khoảng trắng và thứ tự trường có thể khác:

```json
{
  "status": "DOWN",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "check": "inventory",
        "mode": "simulation"
      }
    },
    "payments": {
      "status": "DOWN",
      "components": {
        "eu": {
          "status": "DOWN",
          "details": {
            "check": "eu",
            "mode": "simulation"
          }
        },
        "us": {
          "status": "UP",
          "details": {
            "check": "us",
            "mode": "simulation"
          }
        }
      }
    }
  }
}
```

Phản hồi này cho biết đường đi tới nguyên nhân là `commerce → payments → eu`. Chỉ nhìn `commerce.status` sẽ không đủ để biết lá nào gây ra trạng thái đó.

Nếu gọi `/actuator/health`, kết quả có thể chứa thêm các indicator do Spring Boot tự cấu hình, chẳng hạn `diskSpace` hoặc `ping`. Vì thế, không dùng JSON của riêng nhánh `commerce` làm mẫu cố định cho toàn bộ ứng dụng.

## 4. Trạng thái tổng hợp được tạo như thế nào?

Trong ví dụ, quá trình đánh giá có thể hiểu theo từng tầng:

```text
eu = DOWN, us = UP
        |
        v
payments = DOWN

inventory = UP, payments = DOWN
        |
        v
commerce = DOWN
```

Composite cung cấp cấu trúc và tên các con; chính sách tổng hợp quyết định trạng thái đại diện. Trong Spring Boot 3.3, thứ tự mặc định của `SimpleStatusAggregator` ưu tiên `DOWN`, rồi `OUT_OF_SERVICE`, `UP`, `UNKNOWN`. Bộ tổng hợp chọn trạng thái được ưu tiên cao nhất trong các trạng thái nó nhận biết. Đây không phải phép lấy đa số. Có mười lá `UP` và một lá `DOWN` vẫn có thể cho kết quả `DOWN`. [API SimpleStatusAggregator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

Với chính sách mặc định và chỉ hai trạng thái `UP`/`DOWN` của bài:

| inventory | eu | us | payments | commerce |
| --- | --- | --- | --- | --- |
| UP | DOWN | UP | DOWN | DOWN |
| UP | UP | UP | UP | UP |
| DOWN | UP | UP | UP | DOWN |
| DOWN | DOWN | UP | DOWN | DOWN |

Kết quả ở từng hàng là dự đoán từ chính sách đánh giá, không phải do tên `inventory` hay `payments` có ý nghĩa đặc biệt với Spring.

Để chạy trường hợp mọi lá đều `UP`, dừng tiến trình cũ bằng Ctrl+C rồi chạy:

```shell
java -jar target/composite-health-demo-1.0.0.jar --demo.payment-eu-up=true
```

Khi đó, `/actuator/health/commerce` trả `status=UP` và HTTP **200**.

Tiếp tục thử trường hợp kho hàng hỏng nhưng thanh toán hoạt động:

```shell
java -jar target/composite-health-demo-1.0.0.jar --demo.payment-eu-up=true --demo.inventory-up=false
```

Lúc này `payments` là `UP`, còn `commerce` là `DOWN` và HTTP **503**. Hai tham số là giá trị đọc lúc khởi tạo bean; thay đổi tệp cấu hình không tự làm bean đang chạy cập nhật trạng thái. Phải khởi động lại để thí nghiệm chuyển sang bộ giá trị khác.

Đừng suy ra rằng mọi trạng thái ngoài `UP` đều có HTTP 503. Theo ánh xạ mặc định, `DOWN` và `OUT_OF_SERVICE` ánh xạ sang 503; trạng thái chưa có ánh xạ, bao gồm `UNKNOWN`, có thể trả 200. Nếu tự cấu hình status order hoặc HTTP mapping, kết quả phải được đánh giá theo cấu hình đó.

## 5. Tên thành phần chính là đường đi trong cây

Với ví dụ ban đầu, có thể truy vấn các mức sau:

| Đường dẫn | Đối tượng đang quan sát | Kết quả mặc định của ví dụ |
| --- | --- | --- |
| `/actuator/health/commerce` | Toàn bộ nhánh mua hàng | DOWN, HTTP 503 |
| `/actuator/health/commerce/inventory` | Lá kho hàng | UP, HTTP 200 |
| `/actuator/health/commerce/payments` | Nhánh thanh toán | DOWN, HTTP 503 |
| `/actuator/health/commerce/payments/eu` | Lá thanh toán EU | DOWN, HTTP 503 |
| `/actuator/health/commerce/payments/us` | Lá thanh toán US | UP, HTTP 200 |

Tên bean ngoài cùng được cố định bằng `@Bean(name = "commerce")`. Các đoạn phía sau lấy từ khóa của từng map. Lá `eu` không phải một bean cấp gốc, nên `/actuator/health/eu` không phải đường dẫn của nó.

Việc truy cập đường dẫn con còn phụ thuộc quyền hiển thị thành phần và cấu hình bảo mật. Đường dẫn sai hoặc thành phần không được hiển thị có thể dẫn tới 404; 401/403 cần kiểm tra lớp xác thực/phân quyền trước. Không coi mọi lỗi HTTP là bằng chứng một dependency đã hỏng.

Mã nguồn [HealthEndpointSupport của Spring Boot 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java) thể hiện cách tìm contributor theo từng đoạn đường dẫn và tổng hợp các kết quả.

### Truy cập bằng Java khi đã có composite

Đoạn sau là mã minh họa đặt trong một phương thức đã nhận biến `commerce` kiểu `CompositeHealthContributor`, không phải chương trình độc lập:

```java
HealthContributor paymentsNode = commerce.getContributor("payments");
if (paymentsNode instanceof CompositeHealthContributor payments) {
    HealthContributor euNode = payments.getContributor("eu");
    if (euNode instanceof HealthIndicator euIndicator) {
        Health result = euIndicator.health();
        System.out.println(result.getStatus().getCode());
    }
}
```

Với cây ban đầu, dòng được in là:

```text
DOWN
```

`getContributor("payments/eu")` trên `commerce` không thay cho hai bước tìm kiếm: khóa trực tiếp của nó là `inventory` và `payments`. Đường dẫn HTTP được endpoint tách thành các đoạn; API tìm con trực tiếp dùng tên con ở cấp hiện tại.

Không ép kiểu mọi `HealthContributor` thành `HealthIndicator`: nhánh `payments` là composite và phép ép kiểu đó sẽ thất bại.

## 6. Đóng gói nhiều phép kiểm tra mà vẫn giữ trách nhiệm rõ ràng

Một thiết kế dễ bảo trì thường tách hai việc:

- **Lá** biết cách kiểm tra một dependency cụ thể và chuyển kết quả thành `Health`.
- **Composite** biết các lá thuộc nhánh nào, tên của chúng là gì và cấu trúc phân cấp ra sao.

Trong ứng dụng thật, có thể thay lambda bằng một lớp `HealthIndicator` nhận client qua constructor. Composite vẫn tổ chức các đối tượng đó theo map. Không cần gom toàn bộ mã kết nối, xử lý lỗi và quy tắc đặt tên vào một phương thức khổng lồ.

API có hai dạng factory hữu ích:

```java
CompositeHealthContributor.fromMap(contributors);
CompositeHealthContributor.fromMap(resources, resource -> toIndicator(resource));
```

Đây là minh họa chữ ký sử dụng: `contributors` chứa sẵn contributor; `resources` chứa tài nguyên, còn `toIndicator` là hàm do ứng dụng cung cấp để chuyển từng tài nguyên thành contributor. Hai dòng trên không phải mã chạy độc lập và không có sẵn hàm `toIndicator` trong Spring.

Không thực hiện một phép kiểm tra mạng rồi lưu cố định kết quả `Health` ngay khi dựng cây. Cần giữ đối tượng có khả năng thực hiện phép kiểm tra ở lần đọc health phù hợp. Trong bài, boolean được cố định có chủ ý để mô phỏng; đó không phải cách phát hiện kết nối thật đã hồi phục.

### Tránh đăng ký trùng các lá

Nếu vừa đánh dấu một indicator là `@Component`, vừa đưa cùng đối tượng vào composite, indicator đó có thể xuất hiện ở cấp gốc và bên trong nhánh. Việc đọc health có thể thực hiện cùng phép kiểm tra nhiều lần.

Khi muốn một lá chỉ thuộc composite:

- Tạo lá trong factory của composite như ví dụ; hoặc
- Dùng đối tượng hỗ trợ không triển khai `HealthContributor` làm bean, rồi tạo indicator bao quanh nó trong composite.

Nếu lá cần tồn tại ở nhiều góc nhìn vì có mục đích riêng, phải chấp nhận và kiểm soát chi phí đánh giá. Đừng dùng việc xuất hiện nhiều nơi làm cơ chế nhân bản trạng thái mà không kiểm tra tác động.

### Tên và cấu trúc cần ổn định

Chọn tên ngắn, có ý nghĩa vận hành và ổn định giữa các lần triển khai. Trong cùng một map, mỗi tên chỉ ánh xạ tới một con; `put` lần nữa với cùng khóa thay thế giá trị trước đó, không tạo hai lá trùng tên.

Tránh tên chứa dấu `/`, tên lấy từ dữ liệu người dùng, hoặc số lượng con tăng không giới hạn. Đổi khóa map cũng đổi đường dẫn quan sát và có thể làm hỏng dashboard hoặc cấu hình group đang tham chiếu tên cũ.

Cây có thể chứa nhiều tầng nhưng phải hữu hạn, không tự tham chiếu. Không sửa map hoặc danh sách con đồng thời trong khi endpoint đang duyệt nếu chưa thiết kế cơ chế đồng bộ rõ ràng. Factory từ map phù hợp nhất với cấu trúc được dựng ổn định; không mặc định coi nó là một registry động an toàn cho nhiều luồng.

Spring có `HealthContributorRegistry` để đăng ký hoặc gỡ contributor ở thời điểm chạy, nhưng quản lý registry động là trách nhiệm riêng. Thêm một phần tử vào map bên ngoài không phải hợp đồng đảm bảo cho việc đăng ký động. [API HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html).

## 7. Composite và health group giải quyết hai nhu cầu khác nhau

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Biểu diễn `commerce` chứa `inventory` và `payments` | Composite contributor |
| Tạo một góc nhìn chỉ bao gồm một số contributor đã có | Health group |
| Tính trạng thái từ các trạng thái con | Status aggregator |
| Đổi trạng thái thành HTTP 200/503 hoặc mã khác | HTTP status mapper |
| Hiển thị hoặc ẩn dữ liệu con/chi tiết | Show-components, show-details và quyền truy cập |

Composite là cấu trúc. Group chọn thành phần và chính sách cho một góc nhìn. Tạo group không tự tạo indicator mới và không làm các dependency thực sự độc lập với nhau.

Sau khi chạy xong ví dụ cơ bản, có thể thêm vào `application.properties`:

```properties
management.endpoint.health.group.checkout.include=commerce
management.endpoint.health.group.usOnly.include=commerce/payments/us
```

Khởi động lại ứng dụng với trạng thái ban đầu:

- `/actuator/health/checkout` xét toàn bộ `commerce`, nên vẫn `DOWN`.
- `/actuator/health/usOnly` chỉ xét lá US, nên là `UP`, dù lá EU bên ngoài tập được chọn đang `DOWN`.

Khi cấu hình group chọn một lá lồng nhau, dùng tên đầy đủ `commerce/payments/us`. Viết `include=us` sẽ nhắm tới ID cấp gốc không tồn tại trong ví dụ. Việc có thêm group cũng có thể làm phản hồi chứa trường `groups`; không so khớp nguyên văn JSON của cấu hình mở rộng với mẫu JSON trước đó.

Chỉ loại một dependency khỏi group sau khi xác định rõ nó không quyết định khả năng phục vụ của góc nhìn đó. Tạo group bỏ qua EU chỉ thay câu hỏi đang hỏi hệ thống; nó không sửa kết nối EU.

Bài này không thay đổi cấu hình liveness/readiness. Khi muốn đưa nhánh vào các probe đó, cần đánh giá ý nghĩa phục vụ và hậu quả vận hành trước, thay vì mặc định đưa toàn bộ dependency ngoài vào mọi probe.

## 8. Chi phí thực thi và lỗi cần phòng tránh

### Composite không tự tạo cơ chế song song

Đối với cây đồng bộ trong ví dụ, endpoint đi qua các contributor và lấy kết quả của các indicator. Việc gom nhiều lá vào một composite không tự biến các lời gọi chặn thành tác vụ song song hay tự cấp timeout cho chúng.

Nếu ba phép kiểm tra nối tiếp mất 200 ms, 300 ms và 400 ms, thời gian dành cho chúng có thể xấp xỉ 900 ms, chưa tính chi phí khác. Đây là ước lượng cho cách thực thi nối tiếp, không phải cam kết độ trễ của Spring.

Khi thay mô phỏng bằng client thật:

- Đặt thời hạn chờ kết nối, đọc và chờ tài nguyên ở lớp client phù hợp.
- Giữ phép kiểm tra nhẹ, có thể gọi lặp lại và không thực hiện giao dịch nghiệp vụ.
- Chuyển lỗi dự kiến thành kết quả health có ý nghĩa; tránh để một exception không được xử lý biến việc đọc health thành lỗi bất ngờ.
- Không cho mỗi lần đọc health tự retry dài hoặc ghi dữ liệu vào hệ thống phụ thuộc.
- Phân biệt kiểm tra đang chậm với kiểm tra đã thất bại; ngưỡng ghi cảnh báo không thay thế cho timeout của client.

Ví dụ dùng lambda trực tiếp không có lớp bắt exception bổ sung. Khi viết kiểm tra thực tế, `AbstractHealthIndicator` là một lựa chọn để quản lý việc dựng kết quả và xử lý exception theo hợp đồng của lớp đó; cần hiểu rõ hành vi trước khi thay thế.

### Cây reactive dùng hệ kiểu riêng

Với luồng reactive, các kiểu tương ứng là `ReactiveHealthIndicator`, `ReactiveHealthContributor` và `CompositeReactiveHealthContributor`; lá cung cấp `Mono<Health>`. Factory composite reactive nhận các contributor reactive. Không truyền một map đồng bộ vào factory reactive rồi mong nó tự hiểu mọi kiểu.

Một phép gọi mạng chặn không tự thành bất đồng bộ chỉ vì được đặt trong lambda tạo `Mono`. Chọn client, cách lập lịch và chính sách timeout phù hợp với luồng thực thi. Phần này chỉ nêu ranh giới để tránh trộn hệ kiểu; ví dụ chạy của bài là Spring MVC đồng bộ. [API CompositeReactiveHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeReactiveHealthContributor.html).

### Đừng coi cấu trúc đẹp là chính sách đúng

Một composite không mặc định hiểu “hai vùng thanh toán chỉ cần một vùng hoạt động”. Với chính sách `DOWN` thắng `UP`, một vùng hỏng vẫn làm nhánh thanh toán `DOWN`.

Nếu hệ thống thực sự vẫn phục vụ nhờ chuyển vùng hoặc phương án dự phòng, phải định nghĩa rõ điều kiện phục vụ và biểu diễn nó bằng các indicator, group hoặc chính sách tổng hợp phù hợp. Không đặt tên composite là `highAvailability` rồi suy ra rằng Spring sẽ tự tính điều kiện “ít nhất một vùng còn sống”.

Tương tự, composite rỗng hoặc group không chọn được lá không chứng minh chức năng hoạt động. Cần phát hiện cấu hình thiếu, thay vì dựa vào một trạng thái tổng quát mà bỏ qua việc không có phép kiểm tra thực sự.

## 9. Chẩn đoán nhanh khi kết quả khác dự kiến

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Chỉ thấy `status`, không thấy cây | Show-components, show-details, quyền xem và cấu hình group. |
| Nhánh con trả 404 | Đường dẫn đầy đủ, chính tả khóa map, cây đã đăng ký và quyền hiển thị thành phần. |
| Một lá xuất hiện ở gốc lẫn trong composite | Lá có đồng thời là bean tự đăng ký hay không. |
| Các lá đa số UP nhưng nhánh DOWN | Chính sách tổng hợp; không áp dụng quy tắc biểu quyết đa số. |
| Health chậm sau khi thêm nhiều con | Chi phí từng lá, timeout client, số lần kiểm tra và việc đăng ký trùng. |
| Thay cấu hình nhưng trạng thái mô phỏng chưa đổi | Ví dụ đọc boolean lúc khởi tạo; dừng tiến trình cũ và chạy lại. |
| Group không khởi tạo được | Tên contributor được include/exclude có tồn tại theo đường dẫn đầy đủ không. |
| Ép kiểu contributor gây lỗi | Đối tượng là indicator hay composite; kiểm tra kiểu trước khi gọi API của lá. |

Nếu phản hồi chứa nhiều thành phần ngoài mẫu, kiểm tra classpath và auto-configuration trước. Một dependency mới có thể thêm indicator khác; đừng xóa các indicator hữu ích chỉ để phản hồi giống tài liệu.

## 10. Thực hành tự kiểm chứng

1. Chạy nguyên ví dụ. Xác nhận lá EU, nhánh payments và nhánh commerce cùng `DOWN`; lá US vẫn `UP`.
2. Khởi động lại với `--demo.payment-eu-up=true`. Xác nhận payments và commerce chuyển sang `UP`.
3. Khởi động lại với EU hoạt động nhưng kho hàng hỏng. Giải thích vì sao payments `UP` mà commerce `DOWN`.
4. Thêm một lá `refunds` vào `paymentChildren` trước khi tạo composite, với phép kiểm tra mô phỏng `UP`. Xác định đường dẫn của lá mới là `/actuator/health/commerce/payments/refunds`.
5. Thêm group `usOnly` như trên. Giải thích vì sao group này có thể `UP` trong khi commerce `DOWN`, và vì sao kết quả đó không chứng minh toàn bộ thanh toán đã phục hồi.
6. Đổi `show-components` và `show-details` sang `never`, khởi động lại rồi so sánh endpoint gốc với đường dẫn con. Tách vấn đề hiển thị khỏi trạng thái kiểm tra.

Hoàn thành bài khi bạn có thể tự dựng cây từ các contributor, chỉ đúng đường đi tới một lá, giải thích cách tổng hợp trạng thái và lựa chọn được giữa thay cấu trúc composite với tạo một góc nhìn health group.
