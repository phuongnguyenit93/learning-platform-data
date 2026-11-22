# Vai trò của HealthContributor, HealthIndicator và CompositeHealthContributor

## 1. Mô hình nền tảng: một cây gồm nhánh và lá

Một ứng dụng có thể cần kiểm tra bộ nhớ đệm, nhiều kết nối cơ sở dữ liệu, các hệ thống thanh toán hoặc nhiều hàng đợi. Nếu chỉ trả một trạng thái chung, người vận hành khó biết thành phần nào có vấn đề. Nếu mỗi kiểm tra lại tự viết một endpoint riêng, việc tổ chức và tổng hợp kết quả dễ trở nên rời rạc.

Spring Boot Actuator tổ chức các nguồn thông tin sức khỏe thành một **cây**:

- **Nút lá** thực hiện một phép đánh giá và tạo kết quả sức khỏe.
- **Nút nhánh** chứa các nguồn thông tin con có tên, có thể gồm cả nhánh khác.
- Hạ tầng của health endpoint duyệt cây, lấy các kết quả và tổng hợp trạng thái theo chính sách.

Ba kiểu trong đề bài phục vụ đúng mô hình đó:

| Kiểu | Vai trò | Câu hỏi nó trả lời |
| --- | --- | --- |
| `HealthContributor` | Hợp đồng chung để nhận diện thành phần tham gia cây sức khỏe | Đối tượng này có tham gia cung cấp thông tin sức khỏe không? |
| `HealthIndicator` | Nút lá cung cấp kết quả kiểm tra | Kết quả của phép đánh giá này là gì? |
| `CompositeHealthContributor` | Nút nhánh tổ chức các contributor có tên | Những thành phần con nào thuộc nhánh này? |

Bài dùng Java 21 và Spring Boot 3.3.13. Các kiểu đang xét thuộc hợp đồng kiểm tra đồng bộ trong gói `org.springframework.boot.actuate.health`.

## 2. HealthContributor: kiểu chung, không phải một phép kiểm tra

`HealthContributor` là giao diện đánh dấu. Bản rút gọn để nhìn quan hệ kiểu:

```java
public interface HealthContributor {
}
```

Nó không khai báo phương thức `health()`. Vì vậy, một biến có kiểu tĩnh là HealthContributor không thể được gọi `health()` chỉ dựa vào hợp đồng này.

Đối với mô hình health của Boot 3.3, contributor phải cung cấp một trong hai hợp đồng có ý nghĩa: HealthIndicator hoặc CompositeHealthContributor. Chỉ tạo một lớp triển khai HealthContributor rỗng không cung cấp cách để endpoint lấy kết quả hay duyệt thành phần con.

Vì sao cần kiểu chung này? Một nhánh cần chứa cả nút lá lẫn nhánh con trong cùng một tập hợp. `Map<String, HealthContributor>` diễn đạt được điều đó mà không phải ép mọi thành phần thành cùng một kiểu lá.

Quan hệ cơ bản:

```text
HealthContributor
    ^
    |
    +-- HealthIndicator
    |       Nút lá: health() tạo một Health
    |
    +-- CompositeHealthContributor
            Nút nhánh: truy cập và duyệt contributor con
```

Đây là quan hệ kiểu, không phải thứ tự thực thi. HealthContributor không đứng ở một “bước trước” HealthIndicator trong một quy trình.

Xem định nghĩa [HealthContributor 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributor.html).

## 3. HealthIndicator: nơi thực sự đánh giá một điều kiện sức khỏe

HealthIndicator mở rộng HealthContributor và có phương thức chính `Health health()`. Giao diện này là giao diện hàm, nên có thể triển khai bằng lambda.

Ví dụ ngắn sau là một khai báo sử dụng các import Health và HealthIndicator, không phải chương trình độc lập:

```java
HealthIndicator localCheck = () ->
        Health.up().withDetail("probe", "local-demo").build();
```

Khi gọi `localCheck.health()`, kết quả là một đối tượng Health gồm trạng thái và có thể có dữ liệu chi tiết. Với kiểm tra thật, logic có thể hỏi một client kết nối, đọc trạng thái bộ tài nguyên hoặc thực hiện một thao tác kiểm tra nhỏ.

Một HealthIndicator nên biểu diễn một đánh giá có ý nghĩa vận hành. Nó có thể cần nhiều thao tác bên trong; không có quy tắc “mỗi lệnh gọi phải thành một HealthIndicator”. Nếu cần thể hiện nhiều thành phần con riêng biệt trên cây, đó là lý do xem xét composite.

### 3.1. HealthIndicator là nguồn; Health là kết quả

Hai đối tượng có trách nhiệm khác nhau:

- HealthIndicator giữ logic tạo thông tin sức khỏe.
- Health là kết quả của một lần đánh giá.

Tạo một Health rồi giữ nó mãi không tự làm kết quả thay đổi khi hệ thống phụ thuộc đổi trạng thái. Trong ví dụ đầy đủ, indicator đọc trạng thái mô phỏng **bên trong lambda**, mỗi lần được gọi, thay vì tính trước Health khi khởi tạo bean.

### 3.2. getHealth(boolean) và chi tiết hiển thị

HealthIndicator còn có phương thức mặc định `getHealth(boolean includeDetails)`. Tham số này cho biết có đưa chi tiết vào kết quả hay không.

Với triển khai mặc định, gọi `getHealth(false)` vẫn thực hiện `health()`, rồi loại chi tiết khỏi kết quả. Nó không có nghĩa “bỏ qua phép kiểm tra”, cũng không tự là một bộ nhớ đệm kết quả.

Bộ kiểm thử trong bài dùng một bộ đếm để xác nhận hành vi này: chi tiết bị loại nhưng số lần thực hiện vẫn tăng.

### 3.3. Khi phép kiểm tra có thể ném ngoại lệ

HealthIndicator không mặc nhiên biến mọi đoạn mã của bạn thành một phép kiểm tra chịu lỗi. Nếu tự triển khai bằng lambda và để ngoại lệ thoát ra, không nên giả định luôn nhận được một Health DOWN đúng ý.

`AbstractHealthIndicator` là lớp cơ sở hỗ trợ xây dựng Health và xử lý Exception từ `doHealthCheck` thành trạng thái DOWN. Đây là lựa chọn khi quy ước “ngoại lệ của phép kiểm tra đồng nghĩa DOWN” phù hợp với thiết kế. Cần kiểm soát dữ liệu ngoại lệ được đưa vào chi tiết và thời gian chờ của client thật.

Xem [HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) và [AbstractHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

## 4. CompositeHealthContributor: cấu trúc chứa các nguồn thông tin con

CompositeHealthContributor cũng là HealthContributor, nhưng trọng tâm của nó là **các contributor con có tên**, không phải một phương thức trả Health của riêng nó.

Nó hỗ trợ:

- Lấy thành phần con trực tiếp qua `getContributor(name)`.
- Duyệt các phần tử có tên qua `iterator()` hoặc `stream()`.
- Tạo composite từ một map bằng `CompositeHealthContributor.fromMap(...)`.

Ví dụ, cùng một nhánh thanh toán có thể chứa nhánh ngân hàng và một kiểm tra hàng đợi:

```text
payments                    CompositeHealthContributor
├── banks                   CompositeHealthContributor
│   ├── bankA               HealthIndicator
│   └── bankB               HealthIndicator
└── queue                   HealthIndicator
```

Map của payments chứa cả một composite và một indicator. Kiểu HealthContributor cho phép mô tả hai loại đối tượng con đó trong cùng một cấu trúc.

### 4.1. Tạo composite không đồng nghĩa chạy kiểm tra

`fromMap` tạo đối tượng tổ chức các contributor. Việc tạo composite hoặc lấy một đối tượng con không tự gọi `health()` của nút lá.

Hạ tầng endpoint mới dùng cấu trúc này để lấy thông tin khi cần đánh giá. Tần suất thực hiện còn phụ thuộc cách gọi và cấu hình của hệ thống; bản thân việc “là composite” không đặt lịch kiểm tra nền hay tự lưu kết quả.

### 4.2. Tên con là khóa của đúng nhánh đó

`getContributor("banks")` trên payments lấy nhánh banks. Muốn lấy bankB trong mã Java, lấy banks trước, rồi gọi `banks.getContributor("bankB")`.

Không mặc nhiên gọi `payments.getContributor("banks/bankB")`: phương thức này tra một tên con trực tiếp, không phải trình phân tích đường dẫn. Endpoint HTTP có thể xử lý nhiều đoạn đường dẫn để duyệt cây; đó là trách nhiệm khác với một lần tra khóa.

Hai nhánh khác nhau có thể dùng cùng một tên con nếu tên được hiểu trong phạm vi từng nhánh. Tuy nhiên, các tên trong cùng map cần phân biệt, ổn định và không chứa dữ liệu bí mật.

### 4.3. Composite không tự định nghĩa chính sách tổng hợp

Một composite chứa bankA và bankB không tự khẳng định rằng chỉ cần một ngân hàng hoạt động là cả nhánh UP. Nếu dùng chính sách tổng hợp mặc định, một nút DOWN trong ví dụ sẽ làm nhánh và gốc DOWN.

Nếu nghiệp vụ cần quy tắc như “còn ít nhất một tuyến thanh toán khả dụng”, phải thiết kế rõ một đánh giá hoặc chính sách tổng hợp phù hợp. Không suy ra quy tắc dự phòng đó chỉ từ việc đặt hai indicator vào cùng composite.

Xem [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html) và [NamedContributors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/NamedContributors.html).

## 5. Phân biệt cây nguồn với cây kết quả

Tên gần giống nhau dễ gây nhầm:

| Nguồn/logic | Kết quả được tính | Điều cần phân biệt |
| --- | --- | --- |
| HealthIndicator | Health | Phép đánh giá khác với dữ liệu do phép đánh giá tạo ra |
| CompositeHealthContributor | CompositeHealth | Cấu trúc nguồn con khác với cấu trúc kết quả con |
| HealthContributor | HealthComponent là kiểu chung phía kết quả | Hai hệ kiểu phục vụ hai phía khác nhau |

CompositeHealth có trạng thái và tập các HealthComponent con. Nó không phải một CompositeHealthContributor để tiếp tục thực hiện phép kiểm tra.

Luồng tổng quát:

```text
Bean HealthContributor
        |
HealthContributorRegistry
        |
Hạ tầng HealthEndpoint duyệt nhánh và gọi indicator ở lá
        |
Health ở lá; CompositeHealth/HealthComponent ở phía kết quả
        |
StatusAggregator chọn trạng thái tổng hợp
        |
Chính sách hiển thị + ánh xạ trạng thái sang HTTP
```

Sơ đồ mô tả trách nhiệm, không phải cam kết một thứ tự gọi từng nút lá cụ thể. Không xây logic phụ thuộc vào việc bankA luôn được gọi trước bankB.

Trong Boot 3.3, trạng thái tổng hợp dùng StatusAggregator. Với UP và DOWN trong bài, DOWN chi phối trạng thái các nhánh cha. Mã HTTP lại được quyết định qua cơ chế ánh xạ riêng; mặc định DOWN ánh xạ sang 503. HealthIndicator không trực tiếp trả một đối tượng HTTP ResponseEntity.

Xem [CompositeHealth](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealth.html) và [Health Information của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

## 6. Registry nối các bean với gốc của cây

HealthContributorRegistry giữ các contributor có tên ở tầng gốc. Boot thông thường phát hiện các bean contributor và tạo registry phù hợp.

Điều này không có nghĩa mọi đối tượng con do bạn tạo trong một phương thức Java đều trở thành bean Spring hoặc tự xuất hiện ở gốc. Nếu bankB chỉ nằm trong map của banks thì đường đến nó đi qua payments → banks → bankB.

Đối với HealthIndicator được Boot đăng ký từ bean, tên định danh bỏ hậu tố `HealthIndicator` nếu có. Trong ví dụ:

| Nguồn tên | Định danh dùng trên cây |
| --- | --- |
| Bean `cacheHealthIndicator` | cache |
| Bean composite có tên tường minh `payments` | payments |
| Khóa `banks` trong map của payments | banks, trong nhánh payments |
| Khóa `bankB` trong map của banks | bankB, trong nhánh banks |

Không áp dụng máy móc quy tắc rút hậu tố của bean gốc cho mọi khóa tự đặt trong mọi map.

Registry cũng cho phép đăng ký và gỡ contributor trong lúc chạy. Đó là thay đổi tập thành phần được theo dõi; không phải cùng thao tác với đổi kết quả UP/DOWN của một indicator đã có. Phần kiểm thử sẽ thêm một contributor tạm rồi gỡ bằng `finally`.

Xem [HealthContributorRegistry](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthContributorRegistry.html).

## 7. Ví dụ đầy đủ: nhánh thanh toán có hai ngân hàng

Cây cần tạo:

```text
Gốc do HealthEndpoint trình bày
├── cache                         HealthIndicator
└── payments                      CompositeHealthContributor
    ├── banks                     CompositeHealthContributor
    │   ├── bankA                 HealthIndicator
    │   └── bankB                 HealthIndicator
    └── queue                     HealthIndicator
```

Các tên ngân hàng, hàng đợi và bộ nhớ đệm trong ví dụ đều là **mô phỏng**. Chúng giúp quan sát cấu trúc và cách tổng hợp; không chứng minh đã có kết nối đến ngân hàng hay hạ tầng bên ngoài.

bankB đọc một cờ trạng thái. Khi cờ là false, nó trả DOWN. Các nút lá khác trả UP để việc lan truyền trạng thái dễ quan sát.

### 7.1. Cấu trúc dự án

```text
health-contributor-tree/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── HealthTreeApplication.java
    │   │   ├── LabDependencyState.java
    │   │   └── HealthTreeConfiguration.java
    │   └── resources/application.yml
    └── test/java/example/
        ├── HealthTreeTest.java
        └── HiddenHealthTreeTest.java
```

### 7.2. pom.xml

Dùng JDK 21 và Maven 3.6.3+. Không cần cơ sở dữ liệu, Docker hay hệ thống thanh toán thật.

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
    <artifactId>health-contributor-tree</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 7.3. src/main/java/example/HealthTreeApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthTreeApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthTreeApplication.class, args);
    }
}
```

### 7.4. src/main/java/example/LabDependencyState.java

```java
package example;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LabDependencyState {
    private final AtomicBoolean bankBUp;

    public LabDependencyState(@Value("${demo.bank-b-up:true}") boolean initiallyUp) {
        this.bankBUp = new AtomicBoolean(initiallyUp);
    }

    public boolean isBankBUp() {
        return bankBUp.get();
    }

    public void setBankBUp(boolean up) {
        bankBUp.set(up);
    }
}
```

AtomicBoolean cho phép các lần đọc và cập nhật cờ mô phỏng nhìn thấy giá trị một cách an toàn. Phương thức setter chỉ được gọi trong mã kiểm thử của bài; không có API HTTP thay đổi cờ.

Cấu hình `demo.bank-b-up` quyết định trạng thái ban đầu. Một kiểm tra thực tế sẽ lấy tín hiệu từ hệ thống cần đánh giá, thay cho cờ này.

### 7.5. src/main/java/example/HealthTreeConfiguration.java

```java
package example;

import java.util.LinkedHashMap;

import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HealthTreeConfiguration {
    @Bean
    HealthIndicator cacheHealthIndicator() {
        return () -> Health.up()
                .withDetail("scope", "in-memory-demo")
                .build();
    }

    @Bean("payments")
    CompositeHealthContributor payments(LabDependencyState state) {
        HealthIndicator bankA = () -> Health.up()
                .withDetail("probe", "simulated")
                .build();

        HealthIndicator bankB = () -> {
            if (state.isBankBUp()) {
                return Health.up()
                        .withDetail("probe", "simulated")
                        .build();
            }
            return Health.down()
                    .withDetail("reason", "simulated-unavailable")
                    .build();
        };

        var banks = new LinkedHashMap<String, HealthContributor>();
        banks.put("bankA", bankA);
        banks.put("bankB", bankB);

        HealthIndicator queue = () -> Health.up()
                .withDetail("probe", "simulated")
                .build();

        var payments = new LinkedHashMap<String, HealthContributor>();
        payments.put("banks", CompositeHealthContributor.fromMap(banks));
        payments.put("queue", queue);
        return CompositeHealthContributor.fromMap(payments);
    }
}
```

Những điểm cần đối chiếu với mô hình:

- Bean `cacheHealthIndicator` là một nút lá và được đưa vào registry với định danh cache.
- Bean có tên payments là một composite ở gốc.
- banks và queue là đối tượng con nằm trong map của payments.
- bankA và bankB là đối tượng con nằm trong map của banks.
- Các indicator con không được khai báo thêm bằng `@Bean`, nên chúng không tự trở thành các mục độc lập ở gốc.
- LinkedHashMap giúp giữ thứ tự duyệt đã chọn trong cấu trúc nguồn của ví dụ. Không dựa vào thứ tự thuộc tính JSON làm hợp đồng sức khỏe.

HealthContributor được dùng làm kiểu giá trị của map. Nếu đổi map thành `Map<String, HealthIndicator>`, bạn không thể đặt nhánh banks kiểu CompositeHealthContributor vào map đó; đó chính là lý do cần kiểu chung cho cả nhánh và lá.

### 7.6. src/main/resources/application.yml

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: always
      show-components: always
  health:
    defaults:
      enabled: false

demo:
  bank-b-up: true
```

`management.health.defaults.enabled: false` tắt các indicator mặc định được tự cấu hình để cây minh họa tập trung vào cache và payments. Nó không tự xóa các contributor tùy chỉnh do chúng ta khai báo. Đây là lựa chọn để quan sát ví dụ; hệ thống thật cần quyết định rõ những kiểm tra hạ tầng nào phải giữ.

Hai thuộc tính show-details và show-components được bật để nhìn thấy cây và dữ liệu mẫu. Máy chủ chỉ lắng nghe tại 127.0.0.1. Cấu hình hiển thị toàn bộ chi tiết này phục vụ học tại máy cá nhân; không suy ra rằng nên công bố mọi chi tiết sức khỏe ở một cửa vào công khai.

## 8. Chạy và quan sát kết quả

Tại thư mục chứa pom.xml:

```bash
mvn clean test
mvn spring-boot:run
```

Hoặc đóng gói và chạy JAR:

```bash
mvn package
java -jar target/health-contributor-tree-1.0.0.jar
```

Chỉ chạy một phiên ứng dụng trên cổng 8080. Đây là ứng dụng Spring có dependency, nên dùng Maven để giải quyết classpath; gọi riêng `javac` trên một tệp không tự có các thư viện cần thiết.

### 8.1. Trạng thái ban đầu: tất cả UP

```bash
curl -sS http://127.0.0.1:8080/actuator/health
```

Nội dung JSON tương ứng với cây mẫu, trình bày lại cho dễ đọc; thứ tự thuộc tính không phải điều kiện so khớp:

```json
{
  "status": "UP",
  "components": {
    "cache": {
      "status": "UP",
      "details": {
        "scope": "in-memory-demo"
      }
    },
    "payments": {
      "status": "UP",
      "components": {
        "banks": {
          "status": "UP",
          "components": {
            "bankA": {
              "status": "UP",
              "details": {
                "probe": "simulated"
              }
            },
            "bankB": {
              "status": "UP",
              "details": {
                "probe": "simulated"
              }
            }
          }
        },
        "queue": {
          "status": "UP",
          "details": {
            "probe": "simulated"
          }
        }
      }
    }
  }
}
```

Các mục `components` biểu diễn kết quả của các nhánh; `details` trong ví dụ là dữ liệu do từng indicator lá thêm vào Health. Chúng không phải hai tên thay thế cho cùng một thứ.

Các URL minh họa việc đi theo cây:

```text
/actuator/health
/actuator/health/cache
/actuator/health/payments
/actuator/health/payments/banks
/actuator/health/payments/banks/bankB
```

Đường dẫn bankB chứa đầy đủ các tên từ gốc. Không có contributor gốc tên bankB trong mô hình này, nên không suy ra đường `/actuator/health/bankB` tương đương.

### 8.2. Chuyển bankB sang DOWN

Dừng phiên hiện tại rồi chạy lại với cờ mô phỏng false:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.bank-b-up=false"
```

Nếu dùng JAR:

```bash
java -jar target/health-contributor-tree-1.0.0.jar --demo.bank-b-up=false
```

Kiểm tra nút bankB:

```bash
curl -sS http://127.0.0.1:8080/actuator/health/payments/banks/bankB
```

Nội dung:

```json
{"status":"DOWN","details":{"reason":"simulated-unavailable"}}
```

Trạng thái của cây lúc này:

```text
cache: UP
payments: DOWN
  banks: DOWN
    bankA: UP
    bankB: DOWN
  queue: UP
Gốc: DOWN
```

bankA và queue không tự biến thành DOWN. Kết quả tổng hợp của các nhánh cha thay đổi vì có kết quả con DOWN theo chính sách đang dùng.

Các lệnh sau dành cho Bash; trên PowerShell dùng `curl.exe` và đổi `/dev/null` thành `NUL`:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/payments/banks/bankA
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/payments/banks/bankB
```

Kết quả khi bankB đang DOWN:

```text
503
200
503
```

Đây là kết quả HTTP của health endpoint với ánh xạ mặc định trong bài. Mã 503 không được viết trực tiếp vào lambda HealthIndicator.

### 8.3. Ẩn cấu trúc không đồng nghĩa ngừng kiểm tra

Sau khi đóng phiên cũ, có thể chạy JAR với cây bị ẩn:

```bash
java -jar target/health-contributor-tree-1.0.0.jar --demo.bank-b-up=false --management.endpoint.health.show-details=never --management.endpoint.health.show-components=never
```

GET đến gốc vẫn trả 503, nhưng nội dung chỉ còn:

```json
{"status":"DOWN"}
```

bankB vẫn được đánh giá, trạng thái vẫn được tổng hợp. Chỉ có chính sách trình bày thay đổi. Hai kiểm thử riêng ở phần sau xác nhận điều này.

## 9. Kiểm thử cấu trúc nguồn, kết quả và endpoint

Các lớp sau dùng đầy đủ ngữ cảnh Spring Boot cùng MockMvc. Chúng kiểm tra registry, hợp đồng Java và việc xử lý yêu cầu qua health endpoint trong cùng tiến trình, không mở cổng mạng thật.

Cách kiểm tra này phù hợp để chứng minh vai trò ba kiểu và cấu trúc kết quả. Nó không xác minh firewall, TLS hoặc một hệ thống ngân hàng thật; các contributor của bài vốn là mô phỏng.

### 9.1. src/test/java/example/HealthTreeTest.java

```java
package example;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.CompositeHealth;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HealthTreeTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    HealthContributorRegistry registry;

    @Autowired
    HealthEndpoint endpoint;

    @Autowired
    LabDependencyState state;

    @BeforeEach
    void startWithBankBUp() {
        state.setBankBUp(true);
    }

    @AfterEach
    void restoreBankB() {
        state.setBankBUp(true);
    }

    @Test
    void registryHoldsBothKindsOfContributor() {
        assertThat(registry.getContributor("cache")).isInstanceOf(HealthIndicator.class);
        assertThat(registry.getContributor("payments"))
                .isInstanceOf(CompositeHealthContributor.class);
        assertThat(registry.getContributor("cacheHealthIndicator")).isNull();
    }

    @Test
    void compositePreservesNestedNamesInsteadOfFlatteningThem() {
        var payments = (CompositeHealthContributor) registry.getContributor("payments");
        var banks = (CompositeHealthContributor) payments.getContributor("banks");

        assertThat(payments.stream().map(named -> named.getName()).toList())
                .containsExactly("banks", "queue");
        assertThat(banks.getContributor("bankA")).isInstanceOf(HealthIndicator.class);
        assertThat(banks.getContributor("bankB")).isInstanceOf(HealthIndicator.class);
        assertThat(registry.getContributor("bankB")).isNull();
        assertThat(payments.getContributor("banks/bankB")).isNull();
    }

    @Test
    void indicatorCreatesHealthAndCanOmitDetails() {
        var executions = new AtomicInteger();
        HealthIndicator indicator = () -> {
            executions.incrementAndGet();
            return Health.up().withDetail("probe", "demo").build();
        };

        Health result = indicator.getHealth(false);
        assertThat(result.getStatus()).isEqualTo(Status.UP);
        assertThat(result.getDetails()).isEmpty();
        assertThat(executions.get()).isEqualTo(1);
    }

    @Test
    void constructingACompositeDoesNotRunItsIndicator() {
        var executions = new AtomicInteger();
        HealthIndicator indicator = () -> {
            executions.incrementAndGet();
            return Health.up().build();
        };

        var composite = CompositeHealthContributor.fromMap(Map.of("leaf", indicator));
        assertThat(executions.get()).isZero();
        var leaf = (HealthIndicator) composite.getContributor("leaf");
        assertThat(executions.get()).isZero();
        assertThat(leaf.health().getStatus()).isEqualTo(Status.UP);
        assertThat(executions.get()).isEqualTo(1);
    }

    @Test
    void healthEndpointReturnsResultObjectsRatherThanContributors() {
        var result = endpoint.health();
        assertThat(result).isInstanceOf(CompositeHealth.class);
        assertThat(result).isNotInstanceOf(CompositeHealthContributor.class);
    }

    @Test
    void allUpTreeIsVisibleOverTheEndpoint() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.cache.status").value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankA.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankB.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.queue.status").value("UP"));
    }

    @Test
    void downLeafPropagatesThroughItsAncestors() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components.cache.status").value("UP"))
                .andExpect(jsonPath("$.components.payments.status").value("DOWN"))
                .andExpect(jsonPath("$.components.payments.components.banks.status").value("DOWN"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankA.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.payments.components.banks.components.bankB.status")
                        .value("DOWN"));
    }

    @Test
    void individualLeafPathsKeepTheirOwnStatus() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health/payments/banks/bankA"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
        mvc.perform(get("/actuator/health/payments/banks/bankB"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"));
    }

    @Test
    void registryCanAddAndRemoveATopLevelContributor() throws Exception {
        HealthIndicator temporary = () -> Health.up().build();
        registry.registerContributor("temporary", temporary);
        try {
            mvc.perform(get("/actuator/health"))
                    .andExpect(jsonPath("$.components.temporary.status").value("UP"));
        }
        finally {
            registry.unregisterContributor("temporary");
        }
        assertThat(registry.getContributor("temporary")).isNull();
    }
}
```

Các phép thử quan trọng:

- Registry có cả một indicator và một composite, đúng vai trò của kiểu chung.
- Tên cache được chuẩn hóa từ bean cacheHealthIndicator; bankB không tự xuất hiện ở gốc.
- Lấy một khóa con không tự phân tích chuỗi `banks/bankB` thành đường dẫn.
- Tạo composite chưa thực hiện nút lá.
- `getHealth(false)` vẫn thực hiện indicator dù chi tiết bị loại.
- Đối tượng endpoint trả về thuộc phía kết quả, không phải contributor.
- Khi bankB DOWN, chỉ trạng thái các nhánh cha và gốc bị tổng hợp thành DOWN; bankA vẫn UP.
- Registry có thể thêm contributor ở gốc và được dọn lại sau kiểm thử.

Cờ mô phỏng được khôi phục trước và sau mỗi phương thức. Phép thêm contributor cũng gỡ trong finally. Nếu đổi cách chạy các test có trạng thái chung sang song song, cần tổ chức lại việc cô lập trạng thái; không để các test cùng sửa một cờ rồi dựa vào thứ tự ngẫu nhiên.

### 9.2. src/test/java/example/HiddenHealthTreeTest.java

```java
package example;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "management.endpoint.health.show-details=never",
        "management.endpoint.health.show-components=never"
})
@AutoConfigureMockMvc
class HiddenHealthTreeTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    LabDependencyState state;

    @AfterEach
    void restoreBankB() {
        state.setBankBUp(true);
    }

    @Test
    void healthyTreeCanBeDisplayedAsStatusOnly() throws Exception {
        state.setBankBUp(true);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void hiddenTreeStillComputesTheDownStatus() throws Exception {
        state.setBankBUp(false);
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }
}
```

Chạy:

```bash
mvn clean test
```

Bộ ví dụ có 11 phương thức kiểm thử: 9 trong HealthTreeTest và 2 trong HiddenHealthTreeTest. Điều kiện thành công là không có failure, error hoặc skipped. Không cần khớp toàn bộ log hay thời gian chạy.

Hai phép thử ẩn chi tiết rất quan trọng: chính sách trình bày không được làm người học hiểu rằng các nút con đã bị xóa khỏi registry hoặc không còn ảnh hưởng trạng thái gốc.

## 10. Khi nào chọn indicator, khi nào chọn composite?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Một phép đánh giá tạo một trạng thái có ý nghĩa | HealthIndicator |
| Nhiều kết nối cần được nhìn riêng dưới cùng một tên cha | CompositeHealthContributor chứa các indicator |
| Một hệ con có nhiều nhánh nhỏ hơn | CompositeHealthContributor có composite con |
| Một quy tắc nghiệp vụ đánh giá khả năng phục vụ từ nhiều tín hiệu | HealthIndicator cho quy tắc đó, hoặc chính sách tổng hợp được thiết kế rõ |
| Thêm/bỏ thành phần đang được theo dõi ở tầng gốc | HealthContributorRegistry |
| Cùng cây nguồn nhưng cần một góc nhìn vận hành chọn lọc | Xem xét Health Group, không đồng nhất nó với composite |

Không cần tạo composite chỉ để chứa đúng một leaf nếu cấu trúc đó không mang ý nghĩa. Ngược lại, trả một Health duy nhất với một map details khổng lồ không tương đương một composite: các mục details không tự trở thành các contributor con có thể duyệt và kiểm tra theo hợp đồng cây.

### 10.1. Composite và Health Group khác nhau

Composite là cấu trúc do các contributor tạo ra, chẳng hạn payments/banks/bankB. Health Group là một góc nhìn được cấu hình để chọn những contributor hoặc thành phần phù hợp cho một mục đích.

Ví dụ, việc có nhánh payments không tự làm nó thành readiness hoặc liveness. Các quyết định vận hành đó cần thiết kế riêng. Đặc biệt, gom các kiểm tra hệ thống bên ngoài vào một composite không có nghĩa toàn bộ nhánh đó nên được dùng làm tín hiệu khởi động lại ứng dụng.

Bài tập trung vào cấu trúc và trách nhiệm ba kiểu, nên không thêm chính sách probe hoặc một hệ thống dự phòng ngân hàng vào ví dụ.

### 10.2. Đặt tên và tránh kiểm tra trùng lặp

Nếu vừa khai báo bankB là bean ở gốc vừa đặt cùng đối tượng đó trong composite, bạn có thể vô tình trình bày và đánh giá cùng một nguồn ở hai vị trí. Hãy quyết định vị trí mà người vận hành cần thấy, thay vì đăng ký ở nhiều chỗ chỉ để “chắc chắn được phát hiện”.

Giữ cây không có vòng tham chiếu, tên con rõ ràng và số tầng vừa đủ. Một cây quá sâu hoặc tên chứa ký tự dùng làm dấu phân đoạn đường dẫn làm việc truy cập, cấu hình nhóm và chẩn đoán khó hơn.

### 10.3. Thời gian chờ và lỗi của phép kiểm tra thật

Indicator thường được gọi trong một yêu cầu kiểm tra sức khỏe. Một lời gọi mạng không có timeout có thể giữ yêu cầu lâu dù cấu trúc composite được thiết kế đúng.

Giới hạn thời gian và lựa chọn thao tác kiểm tra phải được thiết kế ở client/cơ chế thực thi thích hợp. Cảnh báo “indicator chậm” không tự là một cơ chế hủy lời gọi mạng. Không thực hiện thao tác thay đổi dữ liệu nghiệp vụ chỉ để biết một tài nguyên còn hoạt động.

## 11. Liên hệ với ứng dụng Reactive

Boot có một hệ kiểu tương ứng cho kiểm tra Reactive:

| Đồng bộ trong bài | Hợp đồng Reactive tương ứng |
| --- | --- |
| HealthContributor | ReactiveHealthContributor |
| HealthIndicator | ReactiveHealthIndicator |
| CompositeHealthContributor | CompositeReactiveHealthContributor |

Trong hợp đồng Reactive, `ReactiveHealthIndicator.health()` trả `Mono<Health>`. Vai trò nguồn chung, nút lá và nút nhánh vẫn có sự phân biệt tương tự.

Không chỉ đổi tên interface rồi giữ một lời gọi mạng chặn luồng bên trong và cho rằng nó đã trở thành kiểm tra không chặn. Khi làm ứng dụng WebFlux, chọn hợp đồng phù hợp và kiểm tra cơ chế thích ứng của registry/endpoint đang dùng. Ví dụ đầy đủ trong bài cố ý dùng hệ đồng bộ của Spring MVC để làm rõ ba kiểu được hỏi.

Xem [Reactive Health Indicators của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive).

## 12. Lỗi thường gặp

| Hiểu nhầm hoặc hiện tượng | Cách hiểu đúng |
| --- | --- |
| Gọi health() trên biến HealthContributor | Kiểu đánh dấu không có phương thức đó; cần hợp đồng HealthIndicator ở nút lá |
| Chỉ triển khai HealthContributor rỗng | Chưa cung cấp hành vi lá hoặc nhánh mà mô hình endpoint yêu cầu |
| HealthIndicator trả chính đối tượng contributor | Phương thức health() phải trả Health |
| CompositeHealthContributor có health() riêng giống indicator | Nó tổ chức các contributor con; hạ tầng endpoint thực hiện việc lấy và tổng hợp kết quả |
| CompositeHealth và CompositeHealthContributor là một | Một bên là dữ liệu kết quả, một bên là nguồn có cấu trúc |
| fromMap chạy kiểm tra ngay | Tạo composite không tự gọi health của các lá |
| Đặt hai indicator vào composite nghĩa là chỉ cần một UP | Chính sách tổng hợp không tự suy ra quy tắc dự phòng nghiệp vụ |
| Mỗi đối tượng con đều tự thành bean gốc | Các đối tượng trong map chỉ ở vị trí do bạn tổ chức, trừ khi còn được đăng ký riêng |
| Không thấy components nghĩa là không có cây nguồn | Kiểm tra show-components và show-details trước khi kết luận |
| DOWN đồng nghĩa indicator trực tiếp trả HTTP 503 | Trạng thái Health và ánh xạ HTTP là hai trách nhiệm khác nhau |
| Khóa con có thể luôn tra bằng đường phân đoạn | getContributor tra tên con trực tiếp; endpoint mới xử lý đường dẫn nhiều đoạn |
| UP chứng minh mọi thao tác nghiệp vụ đều đúng | UP chỉ phản ánh các điều kiện mà các phép kiểm tra đang thực sự đánh giá |

## 13. Thực hành tự kiểm tra

1. Chạy 11 kiểm thử và chỉ ra biến nào là nguồn kiểm tra, biến nào là dữ liệu kết quả.
2. Thêm một bankC trong map banks. Giải thích vì sao nó nằm dưới payments/banks thay vì tự trở thành contributor gốc.
3. Chuyển bankB thành một bean gốc trong dự án thực hành và đồng thời giữ nó trong composite. Quan sát cấu trúc rồi quyết định có cần hai vị trí đó không.
4. Tắt hiển thị components và details. Chứng minh bankB DOWN vẫn ảnh hưởng trạng thái tổng hợp.
5. Trước khi thay cờ mô phỏng bằng một client thật, xác định điều kiện UP/DOWN, timeout, dữ liệu chi tiết được phép lộ và lý do cần lá riêng hay nhánh riêng.

Bạn nắm đúng mô hình khi có thể phân biệt **kiểu chung tham gia cây**, **nút lá thực hiện đánh giá**, **nút nhánh tổ chức nguồn con** và **cây kết quả do endpoint trình bày**, rồi giải thích được đường đi từ một lá DOWN đến trạng thái tổng hợp.
