# Chọn thành phần con của composite indicator và kiểm tra thành viên hợp lệ

Bài này dùng Spring Boot 3.3.13 và Java 21. Mục tiêu là chọn đúng nhánh trong cây kiểm tra sức khỏe, hiểu trạng thái của nhóm sau khi chọn, và phát hiện cấu hình tham chiếu tới thành viên không tồn tại.

## 1. Hiểu bài toán: một cây kiểm tra, nhiều mục đích quan sát

Một ứng dụng có thể kiểm tra nhiều hệ thống phụ thuộc. Riêng một hệ thống lại có nhiều thành phần: chẳng hạn dịch vụ thanh toán có nút chính và bản sao. Nếu gom tất cả vào một trạng thái chung, lỗi ở bản sao có thể che mất câu trả lời mà ta thực sự cần: luồng xử lý đơn hàng còn sử dụng được các thành phần bắt buộc hay không?

Trong Actuator, một phép kiểm tra ở lá thường triển khai `HealthIndicator` và trả về `Health`. Một nút chứa nhiều phép kiểm tra được biểu diễn bằng `CompositeHealthContributor`. Nhóm sức khỏe (health group) chọn các thành viên từ cây này để có một kết quả phục vụ mục đích riêng. `CompositeHealthContributor.fromMap(...)` tạo nút ghép từ các phần tử có tên trong một `Map`. [API CompositeHealthContributor 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Xét cây minh họa sau; các trạng thái được cố định để dễ kiểm chứng:

```text
backends                         CompositeHealthContributor
├── inventory                    HealthIndicator → UP
└── billing                      CompositeHealthContributor
    ├── primary                  HealthIndicator → UP
    └── replica                  HealthIndicator → DOWN
```

`backends` là ID cấp gốc. `inventory` và `billing` là tên con trực tiếp của nó; `primary` và `replica` là tên con của `billing`. Tên nút và trạng thái là hai thông tin khác nhau: `replica` vẫn tồn tại hợp lệ dù đang báo `DOWN`.

Ba câu hỏi có thể cần ba tập thành viên khác nhau:

| Mục đích | Các lá cần xét | Kết quả trong ví dụ |
| --- | --- | --- |
| Luồng đặt hàng `checkout` | `inventory` và `billing/primary` | `UP` |
| Quan sát đầy đủ nhánh `billing` | `primary` và `replica` | `DOWN` |
| Chỉ quan sát phần bắt buộc của `billing` | Chọn `billing`, rồi loại `replica` | `UP` |

Nhóm không tạo bản sao của phép kiểm tra và không thay đổi kết quả gốc. Nó xác định tập thành viên tham gia vào kết quả của chính nhóm đó.

## 2. Đường dẫn thành viên đi từ gốc tới nút cần chọn

Đường dẫn cấu hình nối các tên nút bằng dấu `/`:

```text
backends
backends/inventory
backends/billing
backends/billing/primary
backends/billing/replica
```

`backends/billing` chỉ một nút ghép; `backends/billing/primary` chỉ một lá. Nếu chọn nút ghép, các lá bên dưới nó thuộc phạm vi lựa chọn, trừ phần bị loại bởi `exclude`. Spring Boot hỗ trợ chọn hoặc loại một phần của composite bằng đường dẫn đầy đủ. [Health Groups — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

Đường dẫn này bắt đầu từ registry của health contributor. Khi đi xuống một cấp, framework tra tên con trong đối tượng chứa các thành viên có tên; `NamedContributors.getContributor(name)` trả về `null` nếu không tìm thấy. [API NamedContributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

Vì vậy cần phân biệt các chuỗi sau:

| Chuỗi | Ý nghĩa hoặc vấn đề |
| --- | --- |
| `backends/billing/primary` | Đường dẫn thành viên đúng trong cây minh họa |
| `primary` | Chỉ tìm contributor cấp gốc mang tên `primary`; không tự tìm mọi lá có tên này |
| `backends.billing.primary` | Không biểu diễn ba cấp trong cây bằng cú pháp dấu `/` |
| `/actuator/health/backends/billing/primary` | URL truy vấn, không phải giá trị thành viên để đưa vào `include` |
| `com.example.health.PrimaryHealthIndicator` | Tên lớp Java, không phải đường dẫn trong registry |
| `backends/billing/primary/status` | `status` là dữ liệu kết quả; không phải contributor con của lá `primary` |

Không lấy các khóa trình bày JSON như `components` hay `details` làm một đoạn của đường dẫn. Chẳng hạn `components/backends/components/billing` không phải đường dẫn thành viên.

Trong ví dụ chạy bên dưới, bean được đặt tên rõ ràng là `backends`, còn tên con lấy trực tiếp từ khóa của `Map`. Khi làm việc với contributor có sẵn trong ứng dụng khác, hãy kiểm tra ID thực tế được đăng ký thay vì suy ra từ tên lớp.

## 3. Dùng include và exclude để chọn đúng tập kiểm tra

### 3.1. Chọn riêng hai lá

Đoạn cấu hình sau tạo nhóm `checkout`:

```properties
management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primary
```

Hai mục trong `include` là hai đường dẫn độc lập. Dấu phẩy phân cách các thành viên; dấu `/` phân cách các cấp của một đường dẫn. Nhóm này không lấy lá `replica`.

Bản YAML tương đương với đúng cấu hình trên là:

```yaml
management:
  endpoint:
    health:
      group:
        checkout:
          include:
            - "backends/inventory"
            - "backends/billing/primary"
```

Chọn một dạng cấu hình cho ứng dụng để tránh các khai báo trùng nhau. Trong tệp `.properties`, có thể viết đường dẫn trực tiếp như ví dụ, không cần đặt dấu nháy quanh giá trị.

### 3.2. Chọn cả nhánh

```properties
management.endpoint.health.group.billing.include=backends/billing
```

Với cây đang xét, nhóm `billing` lấy cả `primary` và `replica`. Vì có `replica=DOWN`, nhóm này báo `DOWN` khi dùng cơ chế tổng hợp trạng thái mặc định.

### 3.3. Chọn nhánh rồi loại một lá

```properties
management.endpoint.health.group.billingPrimary.include=backends/billing
management.endpoint.health.group.billingPrimary.exclude=backends/billing/replica
```

`exclude` loại phần đã khớp dù nó nằm dưới nhánh được `include`. Ở đây chỉ còn `primary` tham gia vào kết quả `billingPrimary`. Không cần sửa `HealthIndicator` của `replica` để đạt được cách quan sát này.

### 3.4. Chọn rộng và chọn rõ từng lá có hệ quả khác nhau

Giả sử sau này thêm lá `backends/billing/archive`. Nhóm chọn cả `backends/billing` sẽ nhận thêm lá đó, trừ khi có quy tắc loại phù hợp. Nhóm chỉ liệt kê `backends/billing/primary` vẫn có phạm vi hẹp hơn. Đây là quyết định thiết kế: nhóm cần theo dõi toàn bộ nhánh, hay cần một tập phụ thuộc được xác định rõ?

Giá trị `*` dùng để chọn tất cả cũng tạo phạm vi rộng. Trong YAML phải đặt `"*"` trong dấu nháy. Bài này dùng đường dẫn cụ thể để làm rõ thành viên nào cần thiết; không suy diễn các mẫu như `backends/*/primary` là cú pháp tìm kiếm đường dẫn được hỗ trợ.

Cũng cần tách hai cấu hình dễ nhầm: `management.endpoints.web.exposure.include=health` đưa endpoint health ra HTTP, còn `management.endpoint.health.group.checkout.include=...` chọn thành viên bên trong nhóm. Chọn thành viên không tự thiết lập toàn bộ cơ chế truy cập HTTP.

## 4. Kiểm tra thành viên hợp lệ diễn ra khi nào?

### 4.1. Mặc định kiểm tra lúc khởi động

```properties
management.endpoint.health.validate-group-membership=true
```

Trong Spring Boot 3.3, thuộc tính này mặc định là `true`. Nó áp dụng ở cấp health endpoint, không nằm dưới một nhóm cụ thể. Nếu nhóm tham chiếu contributor không tồn tại trong `include` hoặc `exclude`, kiểm tra mặc định làm khởi động thất bại. [Danh mục thuộc tính Actuator 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator.management.endpoint.health.validate-group-membership).

Với đường dẫn cụ thể `backends/billing/primary`, có thể hiểu thao tác kiểm tra là:

```text
registry
  → tìm backends
  → tìm billing trong backends
  → tìm primary trong billing
  → xác nhận tìm thấy contributor cuối cùng
```

Thiếu một tên ở bất kỳ cấp nào đều làm đường dẫn không hợp lệ. Nếu cố đi tiếp qua một lá, chẳng hạn thêm `/status` sau `primary`, đường dẫn cũng không hợp lệ vì lá đó không chứa contributor con.

Cơ chế kiểm tra của phiên bản này chạy sau khi các singleton được khởi tạo, duyệt cấu hình nhóm và tra đường dẫn trong registry. Nó không gọi phép kiểm tra sức khỏe để quyết định tên thành viên có hợp lệ hay không. [Mã nguồn bộ kiểm tra trong HealthEndpointConfiguration 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 4.2. Hợp lệ về thành viên và khỏe mạnh là hai điều khác nhau

| Trường hợp | Kiểm tra thành viên | Khi truy vấn nhóm |
| --- | --- | --- |
| `backends/billing/primary` tồn tại, trả `UP` | Qua | Thành viên đóng góp `UP` |
| `backends/billing/replica` tồn tại, trả `DOWN` | Qua | Thành viên đóng góp `DOWN` nếu được chọn |
| Gõ nhầm `backends/billing/primray` | Không qua với kiểm tra mặc định | Ứng dụng không khởi động thành công |
| Tên trong `exclude` không tồn tại | Cũng không qua với kiểm tra mặc định | Cần sửa tên hoặc điều chỉnh cấu hình môi trường |

Qua kiểm tra thành viên chỉ chứng minh đường dẫn tồn tại tại thời điểm kiểm tra. Nó không chứng minh nhóm đã bao phủ đủ các phụ thuộc theo yêu cầu nghiệp vụ. Ví dụ, chỉ chọn `inventory` là một cấu hình hợp lệ về tên, nhưng có thể thiếu phép kiểm tra thanh toán mà luồng đặt hàng cần.

### 4.3. Tắt kiểm tra không sửa thành viên bị thiếu

```properties
management.endpoint.health.validate-group-membership=false
```

Giá trị `false` bỏ qua cổng kiểm tra thành viên khi khởi động. Nó không đăng ký contributor còn thiếu, không sửa lỗi chính tả và không biến kết quả `DOWN` thành `UP`.

Với `include=backends/inventory,backends/billing/primray`, nếu tắt kiểm tra thì nhóm có thể vẫn trả `UP` nhờ `inventory`, trong khi phép kiểm tra `primary` dự định chọn đã bị bỏ sót. Kết quả xanh đó không đủ để kết luận cấu hình đúng.

Trong ứng dụng có contributor phụ thuộc profile, thư viện hoặc điều kiện tạo bean, cần phối hợp cấu hình nhóm với môi trường thực tế. Ưu tiên khai báo tập thành viên phù hợp từng profile và giữ kiểm tra bật. Nếu có thiết kế đăng ký contributor động sau thời điểm kiểm tra, việc bỏ kiểm tra phải đi kèm cơ chế xác nhận riêng rằng tập thành viên cần thiết thực sự xuất hiện.

## 5. Ví dụ đầy đủ có thể chạy độc lập

Ví dụ dưới đây là một dự án Maven riêng để học cơ chế, không cần cơ sở dữ liệu hay dịch vụ bên ngoài. Các indicator trả trạng thái cố định; chúng không thực hiện kết nối tới hệ thống thật. Cần JDK 21, Maven và kết nối mạng cho lần tải thư viện đầu tiên.

### 5.1. Cấu trúc tệp

```text
composite-health-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/health/CompositeHealthDemoApplication.java
    └── resources/application.properties
```

### 5.2. pom.xml

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
    <groupId>com.example</groupId>
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

Phiên bản 3.3.13 được ghi rõ để đối chiếu hành vi trong bài. `spring-boot-starter-web` cung cấp ứng dụng web Servlet; `spring-boot-starter-actuator` cung cấp health endpoint. Không thêm Spring Security vào dự án tối thiểu này.

### 5.3. CompositeHealthDemoApplication.java

```java
package com.example.health;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompositeHealthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompositeHealthDemoApplication.class, args);
    }

    @Bean(name = "backends")
    CompositeHealthContributor backends() {
        Map<String, HealthContributor> billing = new LinkedHashMap<>();
        billing.put("primary", fixed(true));
        billing.put("replica", fixed(false));

        Map<String, HealthContributor> backends = new LinkedHashMap<>();
        backends.put("inventory", fixed(true));
        backends.put("billing", CompositeHealthContributor.fromMap(billing));
        return CompositeHealthContributor.fromMap(backends);
    }

    private static HealthIndicator fixed(boolean available) {
        return () -> available ? Health.up().build() : Health.down().build();
    }
}
```

`fixed(true)` tạo lá `UP`; `fixed(false)` tạo lá `DOWN`. Hai lần gọi `fromMap(...)` tạo hai cấp nút ghép. Các biến `billing` và `backends` có kiểu `Map<String, HealthContributor>` nên có thể chứa cả lá lẫn nút ghép. Các lá bên trong map không phải những bean riêng được đăng ký thêm ở cấp gốc.

`LinkedHashMap` giúp việc đọc cấu trúc khởi tạo thuận tiện; thứ tự thuộc tính trong JSON không phải hợp đồng cần dựa vào. Điều cần kiểm tra là tên thành viên, cấu trúc lồng nhau và trạng thái.

### 5.4. application.properties

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.validate-group-membership=true
management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primary
management.endpoint.health.group.billing.include=backends/billing
management.endpoint.health.group.billingPrimary.include=backends/billing
management.endpoint.health.group.billingPrimary.exclude=backends/billing/replica
```

`server.address=127.0.0.1` giới hạn ví dụ ở máy cục bộ. `show-components=always` cho phép quan sát cấu trúc thành viên trong phản hồi. Đây là điều kiện quan sát của ví dụ; bản thân nó không chọn thành viên. Trong hệ thống triển khai thực tế, cấu hình hiển thị và quyền truy cập cần phù hợp với thông tin được phép công bố.

### 5.5. Biên dịch và chạy

Tại thư mục chứa `pom.xml`, chạy:

```shell
mvn clean package
java -jar target/composite-health-demo-1.0.0.jar
```

Giữ tiến trình ứng dụng đang chạy rồi mở terminal thứ hai. Mặc định ví dụ dùng cổng 8080. Nếu cổng đã được dùng, có thể thêm `--server.port=8081` khi chạy và đổi URL tương ứng. Đây là chương trình dùng thư viện Spring nên cần biên dịch với classpath do Maven quản lý; chạy `javac` trần cho một tệp sẽ thiếu các dependency.

## 6. Quan sát kết quả sau khi chọn thành viên

### 6.1. Nhóm checkout giữ các nút cha để biểu diễn cây

Truy vấn:

```shell
curl -i http://127.0.0.1:8080/actuator/health/checkout
```

Trong PowerShell, có thể dùng `curl.exe -i ...` để gọi đúng chương trình curl. Kết quả mong đợi có mã HTTP `200`; phần thân JSON dưới đây được xuống dòng cho dễ đọc, không yêu cầu thứ tự các thuộc tính:

```json
{
  "status": "UP",
  "components": {
    "backends": {
      "status": "UP",
      "components": {
        "billing": {
          "status": "UP",
          "components": {
            "primary": {
              "status": "UP"
            }
          }
        },
        "inventory": {
          "status": "UP"
        }
      }
    }
  }
}
```

Nhóm vẫn giữ `backends` và `billing` làm các nút tổ chức. Việc chọn một lá không làm lá đó tự chuyển thành thành viên cấp gốc trong JSON. `replica` không có trong cây kết quả của `checkout`.

Actuator lọc các đóng góp theo thành viên của nhóm rồi tổng hợp trạng thái trên phần còn lại. Vì vậy, `billing` bên trong kết quả `checkout` báo `UP`: tại góc nhìn này chỉ có `primary`. Đây là kết quả của nhánh đã lọc. [Mã nguồn HealthEndpointSupport 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 6.2. So sánh cùng cây ở ba nhóm

```shell
curl -i http://127.0.0.1:8080/actuator/health/billing
curl -i http://127.0.0.1:8080/actuator/health/billingPrimary
```

| URL | Thành viên lá tham gia | Trạng thái | Mã HTTP mặc định trong ví dụ |
| --- | --- | --- | --- |
| `/actuator/health/checkout` | `inventory`, `primary` | `UP` | `200` |
| `/actuator/health/billing` | `primary`, `replica` | `DOWN` | `503` |
| `/actuator/health/billingPrimary` | `primary` | `UP` | `200` |

Bảng giả định không thay đổi bộ tổng hợp trạng thái hoặc ánh xạ trạng thái sang mã HTTP. Tập thành viên, quy tắc tổng hợp và mã HTTP là ba lớp cần phân biệt khi chẩn đoán một ứng dụng đã tùy biến.

Thử truy vấn lá không thuộc nhóm:

```shell
curl -i http://127.0.0.1:8080/actuator/health/checkout/backends/billing/replica
```

Với cấu hình hiển thị thành phần của ví dụ, kết quả là HTTP `404`. Contributor `replica` có tồn tại trong cây chung, nhưng không phải thành viên của `checkout`. Vì thế không thể chỉ nhìn một mã `404` rồi kết luận bean chưa được tạo; phải xét cả nhóm đang truy vấn và quyền hiển thị.

## 7. Thử lỗi cấu hình để thấy cổng kiểm tra hoạt động

### 7.1. Sai một tên ở include

Dừng ứng dụng bằng Ctrl+C. Khởi động lại với một tham số ghi đè cố ý viết sai `primary` thành `primray`:

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.group.checkout.include=backends/billing/primray
```

Ứng dụng khởi động thất bại. Thông báo chẩn đoán chứa nội dung sau; dấu thời gian và phần log bao quanh phụ thuộc môi trường:

```text
Included health contributor 'backends/billing/primray' in group 'checkout' does not exist
```

Sửa đường dẫn về `backends/billing/primary` hoặc khôi phục cấu hình gốc. Không cần thay đổi phép kiểm tra của `primary`, vì lỗi nằm ở tên thành viên.

### 7.2. Sai tên ở exclude cũng là lỗi

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.group.billingPrimary.exclude=backends/billing/repilca
```

Ở lần chạy này, `replica` bị viết thành `repilca`. Ứng dụng cũng khởi động thất bại. Điều này hữu ích vì nếu âm thầm bỏ qua tên loại sai, thành viên dự định loại có thể vẫn tham gia và làm nhóm báo trạng thái ngoài ý muốn.

### 7.3. Đối chứng khi tắt kiểm tra

Chạy một tiến trình mới với cả hai tham số sau:

```shell
java -jar target/composite-health-demo-1.0.0.jar --management.endpoint.health.validate-group-membership=false --management.endpoint.health.group.checkout.include=backends/inventory,backends/billing/primray
```

Ứng dụng có thể khởi động và `checkout` trả HTTP `200`, `status=UP`, nhưng phần `components.backends.components` chỉ còn `inventory`. Tên gõ sai không tạo ra phép kiểm tra thanh toán. Đây là minh chứng rằng tắt kiểm tra thành viên có thể che mất lỗi cấu hình.

Dừng tiến trình thử nghiệm và chạy lại lệnh gốc không có tham số ghi đè để trở về cấu hình hợp lệ.

## 8. Chẩn đoán lỗi theo đúng lớp

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Khởi động thất bại vì thành viên không tồn tại | Kiểm tra từng đoạn `/`, ID cấp gốc, khóa map con, profile và điều kiện tạo contributor |
| Tên trong exclude gây lỗi khởi động | Đối chiếu cây thực tế; exclude cũng yêu cầu tên tồn tại khi bật kiểm tra mặc định |
| Nhóm UP nhưng thiếu một phép kiểm tra cần thiết | Đối chiếu tập lá thực tế với yêu cầu; kiểm tra có tắt validation hoặc chọn phạm vi quá hẹp hay không |
| Nhóm DOWN vì một lá không cần thiết | Rà lại ý nghĩa của nhóm và cách chọn cả nhánh; sửa tập thành viên nếu yêu cầu thực sự cho phép |
| Không thấy components trong JSON | Kiểm tra show-components và quyền quan sát; việc ẩn cây không tự chứng minh nhóm rỗng |
| URL con trả 404 | Kiểm tra đường dẫn, thành viên của nhóm và quyền hiển thị; phân biệt với contributor chưa tồn tại |
| Một nhóm UP, nhóm khác DOWN trên cùng nhánh | So sánh tập lá đã chọn trước khi nghi ngờ phép tổng hợp |

Đổi `show-components` hoặc `show-details` chỉ để quan sát không phải cách sửa tên thành viên. Đổi mã HTTP cũng không sửa tập kiểm tra. Cách xử lý tốt bắt đầu từ câu hỏi nhóm cần đại diện điều gì, rồi đối chiếu cây contributor với cấu hình.

Trong ngữ cảnh probe, chỉ thêm các thành viên có ý nghĩa với quyết định mà probe sẽ kích hoạt. Ví dụ dùng nhóm riêng `checkout` để tập trung vào kỹ thuật chọn nhánh; không tự gắn nó thành liveness hay readiness cho mọi hệ thống.

## 9. Thực hành và tự kiểm tra

1. Đổi `checkout.include` thành `backends/billing`. Dự đoán kết quả rồi chạy lại. Với dữ liệu cố định trong ví dụ, nhóm sẽ có cả `primary` và `replica`, báo `DOWN`/503.
2. Giữ lựa chọn cả nhánh ở câu 1 và thêm `checkout.exclude=backends/billing/replica` dưới đúng tiền tố `management.endpoint.health.group`. Nhóm còn `primary`, báo `UP`/200.
3. Đổi giá trị include thành `backends/billing/primary/status`. Với kiểm tra thành viên mặc định, ứng dụng không khởi động thành công vì không thể đi qua lá `primary` để tìm contributor `status`.
4. Giữ nguyên ví dụ gốc nhưng cho `fixed(false)` của `replica` thành `fixed(true)`. Kiểm tra thành viên vẫn qua như trước; nhóm `billing` đổi từ `DOWN` sang `UP`. Thay đổi này thuộc kết quả phép kiểm tra, không thuộc tính hợp lệ của tên.
5. Giải thích vì sao tắt kiểm tra rồi thấy `checkout=UP` chưa chứng minh nhóm đầy đủ. Câu trả lời cần chỉ ra phép kiểm tra dự định chọn có thể đã không tham gia.

Trước khi dùng một nhóm làm tín hiệu vận hành, cần xác nhận đường dẫn tồn tại, tập lá đúng yêu cầu, trạng thái tổng hợp phù hợp và khả năng quan sát cho phép kiểm chứng cấu hình. Trong ví dụ này, điều quyết định là chọn đúng `backends/billing/primary` và giữ cơ chế phát hiện tên sai khi khởi động.
