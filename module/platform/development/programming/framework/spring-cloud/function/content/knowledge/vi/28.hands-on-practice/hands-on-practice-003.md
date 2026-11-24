# Ghép chuỗi kiểm tra và xử lý đơn hàng

## 1. Bài toán thực hành

Trong module **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), một chức năng nghiệp vụ được biểu diễn thành `Supplier`, `Function` hoặc `Consumer`, được `FunctionCatalog` quản lý để có thể dùng lại qua HTTP, hệ thống sự kiện hoặc serverless. Khi nghiệp vụ gồm nhiều bước, thay vì đặt toàn bộ logic trong một bean khổng lồ, ta có thể **ghép các hàm nhỏ với nhau** (*function composition*).

Hệ thống bán hàng trong bài nhận đơn gồm mã đơn, khách hàng, các dòng hàng và mã giảm giá. Ta cần:

1. **Kiểm tra và chuẩn hóa** dữ liệu đầu vào: mã đơn, mã khách hàng, SKU, số lượng, đơn giá, coupon.
2. **Tính tiền:** cộng giá từng dòng, tính giảm giá 10% với coupon `VIP10`, xác định tổng cần thanh toán.
3. **Hoàn tất đơn:** tạo biên nhận có cấu trúc rõ ràng.
4. **Ghi audit:** chỉ khi chuỗi xử lý hoàn tất thành công.

Mỗi bước nhận một kiểu Java cụ thể, trả một kiểu cụ thể:

~~~text
JSON / message / direct call
            |
            v
       OrderRequest
            |
            v
   validateOrder (Function)
            |
            v
      ValidatedOrder
            |
            v
    priceOrder (Function)
            |
            v
       PricedOrder
            |
            v
   completeOrder (Function)
            |
            v
       OrderReceipt
          /       \
         v         v
 formatReceipt   auditReceipt
  (Function)     (Consumer)
         |         |
         v         v
    String       side effect
~~~

Chuỗi chính được biểu diễn bằng Spring Cloud Function:

~~~properties
spring.cloud.function.definition=validateOrder|priceOrder|completeOrder
~~~

Với một lời gọi qua `FunctionCatalog`, ta cũng có thể tra cứu trực tiếp định nghĩa trên:

~~~java
Function<OrderRequest, OrderReceipt> pipeline =
        catalog.lookup("validateOrder|priceOrder|completeOrder");
~~~

> **Mục tiêu trọng tâm:** Ghép ba bean `Function` theo đúng thứ tự và tương thích kiểu. Đây không phải ba request HTTP riêng, cũng không tự động tạo ba topic. Spring Cloud Function trình bày chuỗi thành **một hàm logic** với input của bước đầu và output của bước cuối.

### Kết quả học tập

Sau khi hoàn thành, bạn sẽ:

- Tạo ứng dụng Java 17 với các `@Bean` có generic đầy đủ.
- Dùng `record` làm hợp đồng đầu vào, dữ liệu trung gian và biên nhận.
- Kiểm thử từng stage độc lập, rồi kiểm thử composition qua `FunctionCatalog`.
- Hiểu thứ tự xử lý, lỗi validation, overflow của tiền và điều kiện bỏ qua downstream.
- Ghép `Supplier|Function` thành supplier và `Function|Consumer` thành consumer.
- Chạy HTTP adapter, thử composition bằng URL và kiểm tra JSON output.
- Phân biệt test logic, catalog và adapter; biết cách mở rộng sang Spring Cloud Stream/serverless.

## 2. Công cụ và phiên bản

Ví dụ dùng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0 (Northfields)**. Theo thông báo phát hành Spring Cloud, release train 2025.0.0 tương thích với Spring Boot 3.5.0. Cặp version này giúp lab có mốc tái hiện cụ thể; với dự án thật nên chọn các bản vá được hỗ trợ trong cùng nhánh tương thích thay vì giữ bản phát hành đầu tiên.

Chuẩn bị:

- JDK, Maven và IDE có hỗ trợ Java/Spring.
- Cổng `8080` còn trống cho thử HTTP hoặc đổi port trong `application.yml`.
- `curl` hoặc Postman để gửi request JSON.
- Không cần Kafka, RabbitMQ, database hay tài khoản cloud cho phần lab bắt buộc.

**Giới hạn quan trọng:** Audit trong bài chỉ ghi vào bộ nhớ, chưa xử lý giao dịch database, thanh toán thật, tồn kho, xác thực khách hàng hay chống gửi đơn trùng. Đây là lab **composition và validation**, không phải hệ thống order production.

## 3. Cấu trúc dự án

Tạo thư mục `order-composition-lab`:

~~~text
order-composition-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orderlab/
    │   │   ├── OrderLabApplication.java
    │   │   ├── OrderLine.java
    │   │   ├── OrderRequest.java
    │   │   ├── ValidatedOrder.java
    │   │   ├── PricedOrder.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderOperations.java
    │   │   ├── OrderAuditStore.java
    │   │   └── OrderFunctions.java
    │   └── resources/application.yml
    └── test/java/com/example/orderlab/
        ├── OrderOperationsTest.java
        ├── OrderFunctionCatalogTest.java
        └── OrderHttpTest.java
~~~

Tất cả Java files dùng package `com.example.orderlab`. `OrderLabApplication` cùng package giúp Spring Boot scan các lớp cấu hình và component liên quan.

## 4. Khởi tạo Maven và Spring Cloud Function

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-composition-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>order-composition-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
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
~~~

**Ý nghĩa dependency:**

| Artifact | Vai trò |
| --- | --- |
| `spring-boot-starter-web` | Spring MVC/Tomcat và Jackson JSON cho HTTP |
| `spring-cloud-function-web` | `FunctionCatalog` và web adapter xuất các functional bean thành endpoint |
| `spring-boot-starter-test` | JUnit Jupiter, Spring Boot Test, MockMvc |
| `spring-cloud-dependencies` | BOM quản lý version Spring Cloud Function cùng release train |

Trong phần unit/catalog test **không cần broker**. Nếu chỉ muốn kiểm thử catalog mà không có web, có thể bỏ web dependency và dùng `spring-cloud-function-context`; ở lab này giữ web để thử composition qua HTTP.

## 5. Xây dựng hợp đồng dữ liệu cho từng bước

Tách rõ kiểu dữ liệu giúp **compiler** phát hiện stage ghép sai, thay vì dùng `Function<Object,Object>` hoặc trao đổi raw JSON qua mọi bước.

### 5.1. OrderLine.java — một dòng hàng

~~~java
package com.example.orderlab;

public record OrderLine(
        String sku,
        int quantity,
        long unitPriceVnd) {
}
~~~

### 5.2. OrderRequest.java — request ban đầu

~~~java
package com.example.orderlab;

import java.util.List;

public record OrderRequest(
        String orderId,
        String customerId,
        List<OrderLine> lines,
        String couponCode) {
}
~~~

`couponCode` có thể là `null` hoặc chuỗi trống, với ý nghĩa **không dùng coupon**. Mã đơn, khách hàng và danh sách dòng hàng bắt buộc theo chính sách của lab; việc chuyển JSON thành record có thể hoàn tất dù trường sai về nghiệp vụ, nên validation phải chạy ở bước kế tiếp.

### 5.3. ValidatedOrder.java — dữ liệu đã được kiểm tra

~~~java
package com.example.orderlab;

import java.util.List;

public record ValidatedOrder(
        String orderId,
        String customerId,
        List<OrderLine> lines,
        String couponCode) {
}
~~~

`ValidatedOrder` có cấu trúc gần `OrderRequest`, nhưng thể hiện **một lời cam kết về quy trình**: chỉ những request qua `validateOrder` mới tạo ra kiểu này trong pipeline chuẩn. Nó không phải cơ chế bảo mật tuyệt đối vì Java vẫn cho phép code khác gọi constructor của record. Nếu cần áp đặt invariant mạnh, có thể chọn class với constructor/factory kiểm soát.

### 5.4. PricedOrder.java — kết quả tính tiền

~~~java
package com.example.orderlab;

public record PricedOrder(
        String orderId,
        String customerId,
        long subtotalVnd,
        long discountVnd,
        long payableVnd) {
}
~~~

Vì các giá trị là **số nguyên VND**, không có sai số floating-point khi nhân/cộng số lượng và đơn giá. Trong miền tiền tệ có phần thập phân, cần `BigDecimal`, quy tắc làm tròn và đơn vị cụ thể.

### 5.5. OrderReceipt.java — kết quả cuối

~~~java
package com.example.orderlab;

public record OrderReceipt(
        String orderId,
        String customerId,
        String status,
        long subtotalVnd,
        long discountVnd,
        long payableVnd) {
}
~~~

`status = "ACCEPTED"` trong ví dụ chỉ có nghĩa **đơn hợp lệ và đã được tính tiền**. Nó không có nghĩa tiền đã được thanh toán hoặc hàng đã được xuất kho. Đừng nhầm trạng thái nghiệp vụ với HTTP status hoặc acknowledgment của message broker.

### 5.6. Ví dụ JSON đầu vào

~~~json
{
  "orderId": " O-101 ",
  "customerId": " C-009 ",
  "lines": [
    { "sku": " pen ", "quantity": 2, "unitPriceVnd": 300000 },
    { "sku": " notebook ", "quantity": 1, "unitPriceVnd": 150000 }
  ],
  "couponCode": " vip10 "
}
~~~

Đầu vào có khoảng trắng và chữ thường để thể hiện vai trò của validation/normalization. Kết quả sau pipeline dự kiến:

~~~json
{
  "orderId": "O-101",
  "customerId": "C-009",
  "status": "ACCEPTED",
  "subtotalVnd": 750000,
  "discountVnd": 75000,
  "payableVnd": 675000
}
~~~

## 6. Viết nghiệp vụ thuần Java theo từng stage

Tạo `OrderOperations.java`:

~~~java
package com.example.orderlab;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class OrderOperations {

    private OrderOperations() {
    }

    public static ValidatedOrder validate(OrderRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("order request is required");
        }

        String orderId = requiredCode(request.orderId(), "orderId");
        String customerId = requiredCode(
                request.customerId(), "customerId");

        if (request.lines() == null || request.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "lines must contain at least one item");
        }

        List<OrderLine> safeLines = new ArrayList<>();
        Set<String> seenSkus = new HashSet<>();

        for (OrderLine line : request.lines()) {
            if (line == null) {
                throw new IllegalArgumentException(
                        "lines must not contain null");
            }

            String sku = requiredCode(line.sku(), "sku");
            if (!seenSkus.add(sku)) {
                throw new IllegalArgumentException(
                        "duplicate sku: " + sku);
            }
            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (line.unitPriceVnd() <= 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd must be positive");
            }
            safeLines.add(new OrderLine(
                    sku, line.quantity(), line.unitPriceVnd()));
        }

        String coupon = request.couponCode() == null
                ? ""
                : request.couponCode().trim().toUpperCase(Locale.ROOT);
        if (!coupon.isEmpty() && !coupon.equals("VIP10")) {
            throw new IllegalArgumentException(
                    "unsupported coupon code");
        }

        return new ValidatedOrder(
                orderId,
                customerId,
                List.copyOf(safeLines),
                coupon);
    }

    public static PricedOrder price(ValidatedOrder order) {
        long subtotal = 0L;
        for (OrderLine line : order.lines()) {
            long itemTotal = Math.multiplyExact(
                    line.unitPriceVnd(), line.quantity());
            subtotal = Math.addExact(subtotal, itemTotal);
        }

        // Chính sách của lab: VIP10 giảm 10%, làm tròn xuống đơn vị VND.
        long discount = order.couponCode().equals("VIP10")
                ? subtotal / 10
                : 0L;
        long payable = Math.subtractExact(subtotal, discount);

        return new PricedOrder(
                order.orderId(),
                order.customerId(),
                subtotal,
                discount,
                payable);
    }

    public static OrderReceipt complete(PricedOrder priced) {
        return new OrderReceipt(
                priced.orderId(),
                priced.customerId(),
                "ACCEPTED",
                priced.subtotalVnd(),
                priced.discountVnd(),
                priced.payableVnd());
    }

    public static String format(OrderReceipt receipt) {
        return "ORDER=" + receipt.orderId()
                + ";STATUS=" + receipt.status()
                + ";PAYABLE=" + receipt.payableVnd();
    }

    private static String requiredCode(
            String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " must not be blank");
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

### 6.1. Phân tích các quy tắc kiểm tra

| Quy tắc | Input bị từ chối | Vì sao? |
| --- | --- | --- |
| `orderId` và `customerId` bắt buộc | `null`, khoảng trắng | Không thể xác định đơn/khách hàng |
| `lines` không rỗng | Danh sách `null` hoặc không phần tử | Đơn không có hàng |
| Mỗi dòng có `sku` | Mã SKU trống hoặc null | Không thể xác định mặt hàng |
| SKU không trùng sau chuẩn hóa | `"pen"` và `" PEN "` | Tránh tính trùng một mã hàng trong mô hình lab |
| `quantity > 0` | 0 hoặc số âm | Không thể đặt số lượng không hợp lệ |
| `unitPriceVnd > 0` | 0 hoặc số âm | Chính sách giá của lab |
| Coupon hợp lệ | Khác rỗng nhưng không phải `VIP10` | Tránh âm thầm bỏ mã không được hỗ trợ |
| Tổng tiền không overflow | Tích hoặc tổng vượt `long` | Không được wrap-around thành số sai |

Các quy tắc được **công bố rõ cho lab**, không phải bắt buộc cho mọi hệ thống bán hàng. Ví dụ, đơn giá 0 hoặc SKU trùng có thể hợp lệ ở một nghiệp vụ khác; khi đó thay chính sách và cập nhật test.

### 6.2. Vì sao List.copyOf và Math.*Exact?

`List.copyOf(safeLines)` tạo danh sách không cho phép sửa bằng các thao tác `add/remove` thông thường, tránh việc downstream làm thay đổi tập dữ liệu đã validate. Bản thân `OrderLine` là record nên các trường trong mỗi dòng cũng không bị gán lại.

`Math.multiplyExact`, `Math.addExact` và `Math.subtractExact` ném `ArithmeticException` khi overflow. Nếu dùng phép toán thông thường trên `long`, overflow có thể tạo giá trị âm hoặc sai mà không báo lỗi. Trong production, cần quyết định cách biểu diễn lỗi này thành response/event và áp dụng giới hạn giá trị phù hợp.

### 6.3. Trách nhiệm của mỗi stage

- `validate`: chuyển `OrderRequest` chưa tin cậy thành `ValidatedOrder`.
- `price`: chỉ xử lý `ValidatedOrder`, không tự đọc JSON hoặc kiểm lại mọi trường.
- `complete`: tạo `OrderReceipt` chứa thông tin kết quả.
- `format`: chuyển biên nhận thành chuỗi để hiển thị; không tính tiền lần nữa.

Một stage **không cần biết** stage trước đến từ HTTP, message broker hay unit test. Đây là điểm tạo khả năng tái sử dụng.

## 7. Đăng ký từng stage thành Spring functional bean

### 7.1. AuditStore.java

Tạo `OrderAuditStore.java`:

~~~java
package com.example.orderlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class OrderAuditStore {

    private final CopyOnWriteArrayList<OrderReceipt> entries =
            new CopyOnWriteArrayList<>();

    public void record(OrderReceipt receipt) {
        entries.add(receipt);
    }

    public List<OrderReceipt> snapshot() {
        return List.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

Kho trên chỉ dành cho bài thực hành và test; dữ liệu mất khi ứng dụng khởi động lại. `CopyOnWriteArrayList` không phù hợp với tải ghi lớn. Với thông tin đơn hàng có thể nhạy cảm, cần kiểm soát truy cập, retention và audit bền vững trong hệ thống thật.

### 7.2. OrderFunctions.java

~~~java
package com.example.orderlab;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Supplier<OrderRequest> demoOrder() {
        return () -> new OrderRequest(
                " O-101 ",
                " C-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrder() {
        return OrderOperations::validate;
    }

    @Bean
    public Function<ValidatedOrder, PricedOrder> priceOrder() {
        return OrderOperations::price;
    }

    @Bean
    public Function<PricedOrder, OrderReceipt> completeOrder() {
        return OrderOperations::complete;
    }

    @Bean
    public Function<OrderReceipt, String> formatReceipt() {
        return OrderOperations::format;
    }

    @Bean
    public Consumer<OrderReceipt> auditReceipt(
            OrderAuditStore auditStore) {
        return auditStore::record;
    }
}
~~~

**Chữ ký chính xác quyết định cách ghép:**

| Bean | Interface | Kiểu vào | Kiểu ra |
| --- | --- | --- | --- |
| `demoOrder` | `Supplier<OrderRequest>` | Không có | `OrderRequest` |
| `validateOrder` | `Function<OrderRequest,ValidatedOrder>` | `OrderRequest` | `ValidatedOrder` |
| `priceOrder` | `Function<ValidatedOrder,PricedOrder>` | `ValidatedOrder` | `PricedOrder` |
| `completeOrder` | `Function<PricedOrder,OrderReceipt>` | `PricedOrder` | `OrderReceipt` |
| `formatReceipt` | `Function<OrderReceipt,String>` | `OrderReceipt` | `String` |
| `auditReceipt` | `Consumer<OrderReceipt>` | `OrderReceipt` | Không có payload nghiệp vụ |

Hợp đồng được thể hiện ngay trên generic, nên người đọc thấy `validateOrder|priceOrder|completeOrder` có thể nối tuần tự. `FunctionCatalog` có thể tận dụng thông tin kiểu để chuẩn hóa lời gọi và chuyển đổi message ở biên adapter.

### 7.3. Entry point và cấu hình

Tạo `OrderLabApplication.java`:

~~~java
package com.example.orderlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderLabApplication.class, args);
    }
}
~~~

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-composition-lab
  cloud:
    function:
      single-function-fallback-enabled: false

server:
  port: 8080
~~~

Trong lab, **không đặt sẵn** `spring.cloud.function.definition` để có thể thử các hàm và composition bằng tên qua `FunctionCatalog`/HTTP. Khi triển khai một pipeline cố định trên Spring Cloud Stream, ta sẽ đặt `definition` rõ ràng ở phần mở rộng.

## 8. Quy tắc composition của Spring Cloud Function

Spring Cloud Function cho phép ghép các bean theo thứ tự bằng `|` (pipe) hoặc `,` (comma):

~~~text
validateOrder|priceOrder|completeOrder
~~~

Một số trường hợp:

| Định nghĩa | Kiểu function tổng hợp | Ý nghĩa |
| --- | --- | --- |
| `validateOrder|priceOrder` | `Function<OrderRequest,PricedOrder>` | Kiểm tra rồi tính tiền |
| `validateOrder|priceOrder|completeOrder` | `Function<OrderRequest,OrderReceipt>` | Chuỗi xử lý đơn đầy đủ |
| `validateOrder|priceOrder|completeOrder|formatReceipt` | `Function<OrderRequest,String>` | Trả chuỗi biên nhận |
| `demoOrder|validateOrder|priceOrder|completeOrder` | `Supplier<OrderReceipt>` | Không có input; lấy đơn mẫu rồi xử lý |
| `validateOrder|priceOrder|completeOrder|auditReceipt` | `Consumer<OrderRequest>` | Nhận đơn, xử lý và audit; không trả biên nhận |
| `auditReceipt|completeOrder` | Không thể ghép hợp lệ | Consumer không tạo payload cho stage sau |

Đây là những quy tắc **hợp đồng hàm** của composition, không phải routing dựa vào nội dung đơn. `a|b` nghĩa là kết quả của `a` chuyển sang `b`; nó không tự tạo hai nhánh song song hoặc hai output binding.

### 8.1. Lưu ý về thứ tự

~~~text
ĐÚNG:
OrderRequest -> validateOrder -> ValidatedOrder
             -> priceOrder -> PricedOrder
             -> completeOrder -> OrderReceipt

SAI:
OrderRequest -> priceOrder
  (priceOrder đòi ValidatedOrder, không phải OrderRequest)
~~~

Các bước có thể có tác dụng phụ trong đời thực, nên đổi thứ tự không chỉ gây lỗi kiểu mà còn có thể thay đổi kết quả nghiệp vụ. Đặt validation trước việc tính tiền, kiểm tra tồn kho hay lưu đơn giúp loại bỏ dữ liệu sai sớm.

### 8.2. Composition không phải một giao dịch

Ghép ba function thành một pipeline **không** cung cấp atomicity, distributed transaction hoặc rollback. Nếu stage sau thất bại sau khi stage trước đã ghi vào database, framework không tự phục hồi thay bạn. Trong lab, ba bước chính đều không có side effect; `auditReceipt` được đặt **ở cuối** để chỉ ghi nhận khi có biên nhận thành công.

## 9. Test logic độc lập trước khi khởi động Spring

Tạo `OrderOperationsTest.java`:

~~~java
package com.example.orderlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

class OrderOperationsTest {

    private OrderRequest validInput() {
        return new OrderRequest(
                " o-101 ",
                " c-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @Test
    void validateNormalizesIdsSkusAndCoupon() {
        ValidatedOrder validated =
                OrderOperations.validate(validInput());

        assertEquals("O-101", validated.orderId());
        assertEquals("C-009", validated.customerId());
        assertEquals("PEN", validated.lines().get(0).sku());
        assertEquals("NOTEBOOK", validated.lines().get(1).sku());
        assertEquals("VIP10", validated.couponCode());
    }

    @Test
    void priceComputesSubtotalDiscountAndPayable() {
        PricedOrder priced = OrderOperations.price(
                OrderOperations.validate(validInput()));

        assertEquals(750_000L, priced.subtotalVnd());
        assertEquals(75_000L, priced.discountVnd());
        assertEquals(675_000L, priced.payableVnd());
    }

    @Test
    void completesAndFormatsReceipt() {
        PricedOrder priced = OrderOperations.price(
                OrderOperations.validate(validInput()));
        OrderReceipt receipt = OrderOperations.complete(priced);

        assertEquals("ACCEPTED", receipt.status());
        assertEquals("O-101", receipt.orderId());
        assertEquals(
                "ORDER=O-101;STATUS=ACCEPTED;PAYABLE=675000",
                OrderOperations.format(receipt));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(" ", "C-1", List.of(), null)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(
                                "O-2", "C-1",
                                List.of(new OrderLine("X", 0, 100L)),
                                null)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(
                                "O-3", "C-1",
                                List.of(new OrderLine("X", 1, 100L)),
                                "UNKNOWN")));
    }

    @Test
    void rejectsDuplicateSkusAfterNormalization() {
        OrderRequest invalid = new OrderRequest(
                "O-4", "C-1",
                List.of(
                        new OrderLine("pen", 1, 100L),
                        new OrderLine(" PEN ", 1, 100L)),
                null);
        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(invalid));
    }

    @Test
    void rejectsOverflowInsteadOfReturningWrongMoney() {
        OrderRequest big = new OrderRequest(
                "O-5", "C-1",
                List.of(new OrderLine("X", 2, Long.MAX_VALUE)),
                null);
        ValidatedOrder validated = OrderOperations.validate(big);

        assertThrows(ArithmeticException.class,
                () -> OrderOperations.price(validated));
    }

    @Test
    void createsUnmodifiableValidatedLineList() {
        ValidatedOrder validated = OrderOperations.validate(validInput());
        assertTrue(validated.lines().size() == 2);
        assertThrows(UnsupportedOperationException.class,
                () -> validated.lines().add(
                        new OrderLine("NEW", 1, 100L)));
    }
}
~~~

Unit test chỉ chứng minh Java logic: kiểu đầu vào, phép tính, validation và ngoại lệ. Nó **không** chứng minh bean được Spring đăng ký hoặc composition được `FunctionCatalog` xây dựng đúng.

### 9.1. Vì sao test overflow?

Nếu một request chứa số lượng `2` và đơn giá `Long.MAX_VALUE`, `Math.multiplyExact` ném `ArithmeticException` thay vì trả tiền âm do overflow. Trong một hệ thống thật, ta nên thêm giới hạn nghiệp vụ trước phép tính và ánh xạ lỗi cho API/message; test ở đây chứng minh không âm thầm tính sai.

### 9.2. Phân biệt validation và deserialization

JSON thiếu `lines` có thể được Jackson deserialize thành `null` (tùy cấu hình), sau đó `validate` từ chối. JSON sai cú pháp hoặc trường có kiểu không hợp lệ có thể bị converter từ chối **trước khi** function được gọi. Vì vậy trong production cần tách **lỗi đọc dữ liệu** và **lỗi quy tắc nghiệp vụ**.

## 10. Kiểm thử chuỗi qua FunctionCatalog

Tạo `OrderFunctionCatalogTest.java`:

~~~java
package com.example.orderlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
        classes = OrderLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private OrderAuditStore auditStore;

    private OrderRequest validInput() {
        return new OrderRequest(
                " o-101 ",
                " c-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void allThreeStagesAreAvailableByName() {
        Function<OrderRequest, ValidatedOrder> validate =
                catalog.lookup("validateOrder");
        Function<ValidatedOrder, PricedOrder> price =
                catalog.lookup("priceOrder");
        Function<PricedOrder, OrderReceipt> complete =
                catalog.lookup("completeOrder");

        assertNotNull(validate);
        assertNotNull(price);
        assertNotNull(complete);

        ValidatedOrder validated = validate.apply(validInput());
        PricedOrder priced = price.apply(validated);
        OrderReceipt receipt = complete.apply(priced);

        assertEquals(750_000L, priced.subtotalVnd());
        assertEquals("ACCEPTED", receipt.status());
        assertEquals(675_000L, receipt.payableVnd());
    }

    @Test
    void compositionProducesSameReceiptAsManualChain() {
        Function<OrderRequest, OrderReceipt> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder");

        assertNotNull(pipeline);

        OrderReceipt receipt = pipeline.apply(validInput());

        assertEquals(new OrderReceipt(
                "O-101", "C-009", "ACCEPTED",
                750_000L, 75_000L, 675_000L), receipt);
        assertTrue(auditStore.snapshot().isEmpty());
    }

    @Test
    void compositionCanAddAFormattingStage() {
        Function<OrderRequest, String> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|formatReceipt");

        assertNotNull(pipeline);
        assertEquals(
                "ORDER=O-101;STATUS=ACCEPTED;PAYABLE=675000",
                pipeline.apply(validInput()));
    }

    @Test
    void supplierCanStartAComposition() {
        Supplier<OrderReceipt> supplier =
                catalog.lookup(
                        "demoOrder|validateOrder|priceOrder"
                        + "|completeOrder");

        assertNotNull(supplier);
        assertEquals(675_000L, supplier.get().payableVnd());
    }

    @Test
    void compositionEndingInConsumerRecordsReceipt() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|auditReceipt");

        assertNotNull(pipeline);
        pipeline.accept(validInput());

        assertEquals(1, auditStore.snapshot().size());
        assertEquals(
                675_000L,
                auditStore.snapshot().get(0).payableVnd());
    }

    @Test
    void invalidOrderStopsBeforeConsumer() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|auditReceipt");
        assertNotNull(pipeline);

        OrderRequest invalid = new OrderRequest(
                "O-BAD", "C-1",
                List.of(new OrderLine("PEN", -1, 100L)),
                null);

        assertThrows(RuntimeException.class,
                () -> pipeline.accept(invalid));
        assertTrue(auditStore.snapshot().isEmpty());
    }
}
~~~

### 10.1. Kết quả của các test

| Test | Cái gì được xác minh? |
| --- | --- |
| `allThreeStagesAreAvailableByName` | Các bean đã đăng ký vào catalog, có thể gọi độc lập |
| `compositionProducesSameReceiptAsManualChain` | `a|b|c` nối đúng thứ tự, ra đúng tổng tiền |
| `compositionCanAddAFormattingStage` | Output `OrderReceipt` nối được với `Function<OrderReceipt,String>` |
| `supplierCanStartAComposition` | `Supplier|Function|Function|Function` tạo supplier tổng hợp |
| `compositionEndingInConsumerRecordsReceipt` | `Function|Consumer` có hợp đồng consumer và side effect |
| `invalidOrderStopsBeforeConsumer` | Validation lỗi thì consumer cuối chuỗi không được gọi |

**Điều chưa được chứng minh:** HTTP đã expose URL, Kafka đã nhận message hoặc database đã commit giao dịch. Đây là bài test ở **mức Spring context và FunctionCatalog**.

### 10.2. Vì sao test qua FunctionCatalog quan trọng?

~~~java
// Chỉ kiểm tra logic thuần: gọi thủ công.
OrderReceipt direct = OrderOperations.complete(
        OrderOperations.price(
                OrderOperations.validate(request)));

// Kiểm tra composition do Spring Cloud Function cung cấp.
Function<OrderRequest, OrderReceipt> pipeline =
        catalog.lookup("validateOrder|priceOrder|completeOrder");
OrderReceipt composed = pipeline.apply(request);
~~~

Ở trường hợp thứ hai, ta kiểm tra cả **bean registration, lookup, wrapper và thứ tự composition**. `FunctionCatalog` có thể trả về một instance được instrumented, nên không nên so `pipeline.getClass()` với class của bean gốc để đánh giá kết quả. Hãy kiểm tra hành vi và hợp đồng.

### 10.3. Bảo đảm test Consumer không bị nhiễu

`OrderAuditStore` là singleton trong Spring context. `@BeforeEach` xóa dữ liệu để các test thông thường không phụ thuộc thứ tự chạy. Nếu chạy test **song song**, nhiều test vẫn có thể truy cập chung store; khi đó cần test isolation tốt hơn, mock bean theo test hoặc tắt parallel execution cho nhóm này.

Ngoài ra, `FunctionCatalog` có thể xây dựng wrapper/lambda composite lazily. Vì thế hãy tra cứu rồi **gọi** hàm mới assert kết quả, thay vì chỉ dựa trên danh sách tên của catalog.

## 11. Cấu hình composition bằng spring.cloud.function.definition

Trong test vừa rồi, ta tra cứu chuỗi trực tiếp:

~~~java
catalog.lookup("validateOrder|priceOrder|completeOrder");
~~~

Khi một adapter như Spring Cloud Stream cần chọn pipeline duy nhất, có thể đặt cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
~~~

Khi đó adapter xử lý chuỗi composition như **một function** có:

~~~text
Input:  OrderRequest
Output: OrderReceipt
~~~

Đừng nhầm `spring.cloud.function.definition` với tên một bean Java có thật: `validateOrder|priceOrder|completeOrder` là **một định nghĩa composition**, còn `validateOrder`, `priceOrder` và `completeOrder` là các bean độc lập.

### 11.1. Dùng dấu phẩy và dấu pipe

`FunctionCatalog` và các adapter hỗ trợ biểu diễn `a|b` hoặc `a,b` cho composition trong các ngữ cảnh được tài liệu mô tả. Ở cấu hình YAML, dùng `|` trong chuỗi có dấu ngoặc kép giúp tránh nhầm với ký hiệu block scalar của YAML khi có khoảng trắng.

Trong URL HTTP, dấu phẩy thường tiện hơn `|` vì một số shell hiểu `|` là ký tự pipeline:

~~~text
/validateOrder,priceOrder,completeOrder
~~~

**Không nhầm dấu chấm phẩy `;` với dấu phẩy**: trong một số cấu hình `spring.cloud.function.definition` của web adapter, `;` dùng để **chọn nhiều function hoặc composition được expose**, không phải nối output sang input.

### 11.2. Function Catalog không bảo đảm kiểu chỉ vì có dấu pipe

Ví dụ:

~~~text
priceOrder|validateOrder
~~~

không phải pipeline hợp lý vì output `PricedOrder` của `priceOrder` không tương thích input `OrderRequest` của `validateOrder`. Type conversion có thể tham gia trong một số trường hợp framework hỗ trợ, nhưng không nên kỳ vọng converter sẽ “biến” các DTO nghiệp vụ bất kỳ thành nhau.

Chữ ký generic chính xác của từng bean và test composition giúp tránh lỗi này ngay trước khi triển khai adapter.

## 12. Kiểm thử HTTP adapter bằng MockMvc

Với `spring-boot-starter-web` và `spring-cloud-function-web` trong `pom.xml`, Spring Cloud Function web adapter có thể export các functional bean thành HTTP endpoint. Một lời gọi **POST** tới composition sẽ chạy cả chuỗi và serialize `OrderReceipt` thành JSON.

Tạo `OrderHttpTest.java`:

~~~java
package com.example.orderlab;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderLabApplication.class)
@AutoConfigureMockMvc
class OrderHttpTest {

    @Autowired
    private MockMvc mvc;

    private static final String VALID_ORDER_JSON = """
            {
              "orderId": " O-101 ",
              "customerId": " C-009 ",
              "lines": [
                {"sku": " pen ", "quantity": 2,
                 "unitPriceVnd": 300000},
                {"sku": " notebook ", "quantity": 1,
                 "unitPriceVnd": 150000}
              ],
              "couponCode": " vip10 "
            }
            """;

    @Test
    void postExecutesFullCompositionOverHttp() throws Exception {
        mvc.perform(post(
                        "/validateOrder,priceOrder,completeOrder")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(VALID_ORDER_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("O-101"))
                .andExpect(jsonPath("$.customerId").value("C-009"))
                .andExpect(jsonPath("$.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.subtotalVnd").value(750000))
                .andExpect(jsonPath("$.discountVnd").value(75000))
                .andExpect(jsonPath("$.payableVnd").value(675000));
    }
}
~~~

**Mục tiêu của test HTTP khác test catalog:**

- URL thực sự được web adapter ánh xạ tới composition.
- JSON đầu vào chuyển thành `OrderRequest`.
- Validation và tính tiền chạy trong một invocation.
- `OrderReceipt` được trả thành JSON đúng schema.

Chỉ test dữ liệu hợp lệ tại đây. Với dữ liệu sai, một `IllegalArgumentException` do stage validation ném ra **không mặc nhiên biến thành HTTP 400 có cấu trúc mong muốn**. Để cung cấp API public, cần thiết kế và kiểm thử error mapping (ví dụ `@ControllerAdvice` trong một web layer phù hợp hoặc cơ chế handler mà adapter hỗ trợ).

### 12.1. Không đưa audit trước khi validation

Nếu thay pipeline thành một chuỗi có consumer audit ở đầu, nó sẽ không còn hợp đồng phù hợp để tiếp tục xử lý vì consumer không trả output. Với pipeline kết thúc bằng `auditReceipt`, audit chỉ được gọi **sau khi** các bước tạo biên nhận hoàn thành.

Tuy vậy, điều này **không** biến audit thành giao dịch atomic. Nếu kho audit thật bị lỗi sau khi đã tính đơn, cần thiết kế retry/idempotency hoặc transaction/outbox tùy yêu cầu.

## 13. Chạy thử ứng dụng và gửi HTTP request

Trong thư mục `order-composition-lab`:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Sau khi ứng dụng chạy trên `http://localhost:8080`, mở terminal khác để gửi yêu cầu.

### 13.1. POST một đơn hàng hợp lệ

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "orderId": " O-101 ",
    "customerId": " C-009 ",
    "lines": [
      {"sku":" pen ","quantity":2,"unitPriceVnd":300000},
      {"sku":" notebook ","quantity":1,"unitPriceVnd":150000}
    ],
    "couponCode":" vip10 "
  }'
~~~

Kết quả nghiệp vụ dự kiến là JSON `OrderReceipt` với `payableVnd = 675000`. HTTP status với một lời gọi `Function` thành công theo web adapter là **200 OK**.

### 13.2. Lấy đơn mẫu bằng Supplier

~~~bash
curl -i "http://localhost:8080/demoOrder"
~~~

`demoOrder` là `Supplier<OrderRequest>` trả DTO mẫu. Nó **không** tạo database record và không tự gửi sự kiện lên broker. JSON output của Supplier chưa được validate/normalize, nên có thể còn khoảng trắng trong các trường theo cấu hình demo.

### 13.3. Thử composition bắt đầu bằng Supplier

~~~bash
curl -i \
  "http://localhost:8080/demoOrder,validateOrder,priceOrder,completeOrder" \
  -H "Accept: application/json"
~~~

Composition có `Supplier` ở đầu vẫn không cần request payload; khi adapter hỗ trợ đường gọi đó, kết quả nghiệp vụ là biên nhận `675000` VND. Nếu phiên bản web adapter có quy tắc export khác, hãy kiểm tra cấu hình `definition` và test endpoint thực tế.

### 13.4. Thử kết quả dạng chuỗi

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder,formatReceipt" \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  --data-binary '{
    "orderId":"O-102",
    "customerId":"C-010",
    "lines":[{"sku":"PEN","quantity":1,"unitPriceVnd":100000}],
    "couponCode":null
  }'
~~~

Giá trị nghiệp vụ dự kiến:

~~~text
ORDER=O-102;STATUS=ACCEPTED;PAYABLE=100000
~~~

`Accept: text/plain` là yêu cầu content negotiation của client; **hãy kiểm tra cả header Content-Type trong response** chứ không suy chỉ từ kiểu Java String.

### 13.5. Một đơn bị từ chối

Thử gửi đơn có `quantity = -1`:

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "orderId":"O-BAD",
    "customerId":"C-010",
    "lines":[{"sku":"PEN","quantity":-1,"unitPriceVnd":100000}],
    "couponCode":null
  }'
~~~

Stage `validateOrder` phải từ chối dữ liệu này bằng exception. **Mã HTTP cụ thể và nội dung lỗi không được cố định trong bài**, vì còn tùy web adapter và cấu hình exception handling. Trong một API production cần chuẩn hóa lỗi (mã trạng thái 4xx hợp lý, mã lỗi nghiệp vụ, correlation ID, không làm lộ stack trace) rồi kiểm thử đúng hợp đồng đó.

**Lưu ý shell:** Các lệnh `--data-binary '...'` và dấu `\` xuống dòng dùng cú pháp Bash/Git Bash. Trên Windows PowerShell, sử dụng `curl.exe` với cú pháp quoting phù hợp hoặc `Invoke-RestMethod`.

## 14. Đưa pipeline vào Spring Cloud Stream

Spring Cloud Stream dùng `spring.cloud.function.definition` để chọn function/chuỗi composition và tạo **input/output binding** với binder (Kafka/RabbitMQ...). Dự án Maven trong bài **chưa** chứa Stream binder, vì vậy phần này là bước mở rộng, không thể chạy chỉ với `pom.xml` hiện tại.

Giả sử chọn:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
~~~

Pipeline vẫn chỉ có **một đầu vào và một đầu ra**:

~~~text
orders.received
       |
       v
   input binding
       |
       v
 validateOrder|priceOrder|completeOrder
       |
       v
   output binding
       |
       v
orders.receipts
~~~

### 14.1. Tên binding cho composition

Theo quy tắc Spring Cloud Stream, tên binding mặc định được tạo từ **tên function tổng hợp**, ví dụ:

~~~text
validateOrder|priceOrder|completeOrder-in-0
validateOrder|priceOrder|completeOrder-out-0
~~~

Các tên này khá dài. Có thể dùng `spring.cloud.stream.function.bindings` để đổi sang tên rõ ràng rồi cấu hình destination:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
    stream:
      function:
        bindings:
          "validateOrder|priceOrder|completeOrder-in-0": orderInput
          "validateOrder|priceOrder|completeOrder-out-0": orderOutput
      bindings:
        orderInput:
          destination: orders.received
          group: order-processors
          content-type: application/json
        orderOutput:
          destination: orders.receipts
          content-type: application/json
~~~

**Giải thích:**

- `orderInput` và `orderOutput` là tên binding đã ánh xạ.
- `orders.received` và `orders.receipts` là destination trên binder, không phải tên bean.
- `-in-0` và `-out-0` có chỉ số **0** vì pipeline có một input và một output.
- Dù pipeline có ba stage, nó không tự tạo **ba** cổng input/output.

Khi chạy messaging thật, cần thêm dependency Spring Cloud Stream và binder tương ứng, cấu hình broker, kiểm thử serialize/deserialize, retry, DLQ, idempotency và khả năng quan sát.

### 14.2. Hợp đồng lỗi trong messaging

Với imperative function, Spring Cloud Stream có thể áp dụng error handling/retry quanh lần xử lý message, tùy binder/cấu hình. Nếu `validateOrder` ném exception, **không có OrderReceipt hợp lệ** để phát ra output thông thường. Cách broker retry, chuyển DLQ hay ACK thông điệp tùy adapter; không được mặc định một exception tự tạo biên nhận từ chối hoặc gửi sự kiện lỗi.

Một chiến lược production có thể là:

- Tách dữ liệu **không hợp lệ vĩnh viễn** ra một sự kiện từ chối có schema riêng.
- Retry hữu hạn cho lỗi tạm thời như kết nối dịch vụ.
- Dùng idempotency key là order ID/transaction ID, kiểm soát xử lý lại.
- Theo dõi số bản ghi thất bại và đo latency từng bước.

Đây là những phần bổ sung vào kiến trúc messaging, không phải tác dụng tự động của `FunctionCatalog`.

## 15. Vì sao không nhúng validation vào controller?

Giả sử chỉ triển khai:

~~~java
@PostMapping("/orders")
public OrderReceipt create(@RequestBody OrderRequest request) {
    // validate, tính tiền, tạo biên nhận trong controller...
}
~~~

Cách này có thể chạy HTTP nhưng làm logic khó dùng lại khi ứng dụng muốn xử lý đơn từ Kafka hoặc một Lambda event. Trong lab, cùng nghiệp vụ được đặt trong:

~~~java
Function<OrderRequest, ValidatedOrder>
Function<ValidatedOrder, PricedOrder>
Function<PricedOrder, OrderReceipt>
~~~

Web/controller là **adapter**: nó nhận request, bảo đảm auth/validation giao tiếp và gọi pipeline. Spring Cloud Stream là adapter khác: nó nhận message, chuyển payload và gọi **cùng các stage**. Không cần copy logic tính tiền vào ba đường xử lý.

### 15.1. Đừng coi exception là một giá trị kết quả

`IllegalArgumentException` từ validation là **luồng điều khiển lỗi**, không phải `OrderReceipt`. Trong composition, exception thường ngắt lời gọi trước khi stage tiếp theo chạy. Nếu nghiệp vụ phải tạo một **response từ chối có cấu trúc**, có thể thiết kế một result type:

~~~java
public record OrderDecisionResult(
        boolean accepted,
        OrderReceipt receipt,
        String rejectionReason) {
}
~~~

Với kiểu như trên, mỗi stage phải có hợp đồng rõ cho cả success và failure; có thể triển khai bằng các hàm xử lý một result wrapper hoặc một stage bao ngoài pipeline. **Không** đơn giản thay output `ValidatedOrder` thành `null` để biểu diễn từ chối rồi mong `priceOrder` tự hiểu null.

### 15.2. Lưu ý transaction, side effect và replay

Composition giống phép nối `Function.andThen` theo logic, **không phải** một giao dịch cơ sở dữ liệu hoặc distributed saga:

- Nếu audit ghi thành công nhưng HTTP response bị mất, client có thể gọi lại.
- Nếu message broker gửi lại một event, việc xử lý có thể bị lặp.
- Nếu bước thanh toán thật có side effect, retry toàn pipeline có thể tạo giao dịch trùng.
- Nếu kiểm tra tồn kho và trừ tồn kho là hai thao tác độc lập, có thể xảy ra race condition.

Trong hệ thống production, cần bổ sung **idempotency, transactional outbox, optimistic locking hoặc workflow/saga** tùy bài toán; đừng giả định Spring Cloud Function tự giải quyết những vấn đề này.

## 16. Bài tập nâng cao

### Bài A — Thêm stage xác thực mã khách hàng

Viết `Function<ValidatedOrder, ValidatedOrder> verifyCustomer` kiểm tra mã khách bắt đầu bằng `C-`. Ghép:

~~~text
validateOrder|verifyCustomer|priceOrder|completeOrder
~~~

**Tiêu chí:** đầu ra của `verifyCustomer` vẫn là `ValidatedOrder`, hợp kiểu với `priceOrder`. Unit test phải có khách hợp lệ và không hợp lệ. Không đặt lời gọi blocking tới database thật trong lab nếu chưa thiết kế dependency/retry.

### Bài B — Coupon VIP20 có giới hạn

Đổi nghiệp vụ để nhận `VIP20`, giảm 20% nhưng tối đa 100.000 VND:

~~~text
subtotal=750000  ->  20%=150000  ->  discount=100000
payable=650000
~~~

**Yêu cầu:** cập nhật validation, pricing và test cả trường hợp chạm trần. Không nên dùng `double` cho phép tính tiền nguyên VND; dùng phép nguyên, giới hạn số và `Math.*Exact` khi cần.

### Bài C — Chọn một định nghĩa pipeline khác

Thử:

~~~text
validateOrder|priceOrder|completeOrder|formatReceipt
~~~

**Câu hỏi:** generic input/output của function tổng hợp là gì? Nó có còn trả `OrderReceipt` không?

**Kỳ vọng:** `Function<OrderRequest,String>`. Kết quả cuối là chuỗi biên nhận. Dùng test catalog để chứng minh; đừng suy output theo stage đầu.

### Bài D — Test không gọi downstream sau lỗi

Tạo một `Consumer<OrderReceipt>` giả lập có bộ đếm số lần gọi. Ghép sau `completeOrder` và gửi một đơn lỗi:

~~~text
validateOrder|priceOrder|completeOrder|countAudit
~~~

**Yêu cầu:** counter phải vẫn bằng 0 sau request bị từ chối. Dùng object quan sát được (AtomicInteger hoặc test double). Không chỉ assert exception rồi kết luận chắc chắn consumer chưa chạy.

### Bài E — Sự kiện từ chối có cấu trúc

Thay vì ném exception với dữ liệu người dùng sai, thiết kế một `OrderProcessingResult` gồm `Accepted(receipt)` và `Rejected(reason)`. So sánh hai phương án:

- **Exception:** thuận tiện cho lỗi hạ tầng/unexpected state, nhưng phải ánh xạ lỗi ở adapter.
- **Result type:** dễ đưa outcome nghiệp vụ vào JSON hoặc event, nhưng từng stage phải hiểu/truyền tiếp trường hợp rejected.

**Lưu ý:** `sealed interface`/records của Java có thể giúp biểu diễn kết quả, nhưng JSON polymorphism cần cơ chế serialize/deserialize riêng khi đi qua ranh giới adapter.

### Bài F — Sơ đồ triển khai nhiều giao thức

Vẽ một sơ đồ:

~~~text
HTTP ----------\
Kafka ----------> parse -> validate -> price -> complete -> adapter output
Serverless ----/
~~~

Ghi rõ thành phần nào phụ thuộc giao thức và thành phần nào có thể dùng chung. Phân tích cách đảm bảo lỗi, auth và retries khi chuyển từ HTTP sang event-driven.

## 17. Lỗi phổ biến và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `mvn test` thiếu dependency | Sai Spring Boot/Cloud BOM hoặc Maven chưa tải artifact | Kiểm tra `pom.xml` và version matrix |
| `catalog.lookup(...)` trả null | Bean không được scan, tên sai hoặc definition sai | Kiểm tra `@Configuration`, package và tên `@Bean` |
| `priceOrder|validateOrder` thất bại | Chữ ký generic không tương thích | Kiểm tra bảng input/output từng stage |
| Pipeline trả DTO sai | Stage đổi thứ tự hoặc dữ liệu trung gian sai | Unit test từng stage rồi catalog test |
| Tính tiền âm bất thường | Số học overflow hoặc dữ liệu chưa validate | Dùng `Math.*Exact`, giới hạn dữ liệu |
| Coupon `vip10` không được áp dụng | Chưa chuẩn hóa giá trị hoặc thay quy tắc | Xem `validate` và `price` |
| JSON vào được nhưng thiếu `lines` | Deserialization tạo null/empty hoặc input không đầy đủ | Test JSON thật và validation |
| Test HTTP lỗi 404 | Web adapter không active, URL composition sai, definition lọc endpoint | Kiểm tra dependency/log/mapping |
| HTTP lỗi 500 với đơn sai | Exception chưa được map thành lỗi 4xx phù hợp | Xây error handling riêng cho adapter |
| Audit có bản ghi trùng | Test state chưa xóa hoặc xử lý event lặp | Cô lập test/idempotency |
| Tưởng composition tạo ba topic | Nhầm số stage với số binding | Xem hợp đồng input đầu/output cuối |
| Broker không nhận output | Chưa thêm binder hoặc đặt sai destination | Viết Stream integration test |
| Dùng `Consumer` ở giữa chuỗi | Consumer không trả payload | Đặt Consumer ở cuối hoặc thiết kế lại stage |
| Thời gian xử lý tăng bất thường | Stage gọi IO blocking/retry toàn pipeline | Tách IO, đặt timeout và quan sát latency |
| Log chứa thông tin đơn nhạy cảm | Log raw payload không kiểm soát | Log metadata cần thiết, không lưu PII tùy tiện |

### Quy trình debug có thứ tự

1. Chạy `java -version`, `mvn -version`.
2. Chạy `mvn test` và sửa unit test nghiệp vụ trước.
3. Test riêng `validate`, `price`, `complete`.
4. Xác nhận Spring tạo các bean với tên được dùng trong definition.
5. Test `catalog.lookup("validateOrder|priceOrder|completeOrder")`.
6. Test supplier composition và consumer side effect nếu dùng.
7. Test HTTP request JSON với endpoint composite.
8. Sau cùng mới kiểm tra binder/serverless trigger nếu mở rộng.

## 18. Tiêu chí hoàn thành bài

| Tiêu chí | Bằng chứng |
| --- | --- |
| Tách 3 stage | Bean `validateOrder`, `priceOrder`, `completeOrder` có generic đúng |
| Validate input | Từ chối thiếu ID, dòng hàng rỗng, SKU trùng, lượng/giá không hợp lệ |
| Tính tiền chính xác | `750000 - 75000 = 675000` |
| Phòng overflow | Test `Math.multiplyExact` thất bại có kiểm soát |
| Composition đúng | `catalog.lookup("validateOrder|priceOrder|completeOrder")` trả biên nhận đúng |
| Supplier composition | `demoOrder|...` tạo `Supplier<OrderReceipt>` |
| Consumer composition | `...|auditReceipt` gọi audit sau xử lý thành công |
| Dừng khi lỗi | Đơn không hợp lệ không đi đến consumer |
| HTTP adapter | MockMvc và `curl` cho JSON response dự kiến |
| Biết giới hạn | Composition không tự có transaction, retry hay binder |

**Tóm tắt:** Hãy xây từng `Function` có một trách nhiệm và generic rõ ràng, kiểm thử từng stage trước, sau đó ghép qua `FunctionCatalog`. Composition cho ta một hàm tổng hợp có kiểu vào/ra của toàn chuỗi, nhưng không tự tạo giao dịch hay bảo đảm giao nhận. Khi cần đổi giao thức, logic tính tiền và validation vẫn có thể tái sử dụng; adapter đảm nhiệm mapping, serialization, lỗi và kết nối hạ tầng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Chuỗi `validateOrder|priceOrder|completeOrder` nhận và trả kiểu gì?

**Đáp án:** `Function<OrderRequest,OrderReceipt>`. Kiểu đầu vào là của stage đầu, kiểu đầu ra là của stage cuối.

**Câu 2.** Nếu đảo thành `priceOrder|validateOrder`, vì sao không hợp lý?

**Đáp án:** `priceOrder` nhận `ValidatedOrder` và trả `PricedOrder`, trong khi `validateOrder` cần `OrderRequest`. Hai stage không tương thích kiểu theo hợp đồng nghiệp vụ.

**Câu 3.** Nếu kết thúc pipeline bằng `auditReceipt`, kết quả là `Function<OrderRequest,OrderReceipt>` hay `Consumer<OrderRequest>`?

**Đáp án:** `Consumer<OrderRequest>`, vì consumer cuối không có payload nghiệp vụ đầu ra.

**Câu 4.** Ghép `demoOrder|validateOrder|priceOrder|completeOrder` có cần input JSON không?

**Đáp án:** Không. Stage đầu là `Supplier<OrderRequest>` tạo input, do đó pipeline tổng hợp là `Supplier<OrderReceipt>`.

**Câu 5.** Vì sao không chỉ dùng phép nhân `unitPrice * quantity` trên kiểu `long`?

**Đáp án:** Có thể overflow và tạo kết quả sai âm thầm. `Math.multiplyExact` giúp phát hiện overflow bằng exception.

**Câu 6.** Khi `validateOrder` ném `IllegalArgumentException`, có tạo ra `OrderReceipt` không?

**Đáp án:** Không theo luồng thành công. Exception làm gián đoạn lời gọi trước `priceOrder`/`completeOrder`. Adapter quyết định cách thể hiện lỗi.

**Câu 7.** Spring Cloud Function composition có tự tạo ba output binding vì có ba stage không?

**Đáp án:** Không. Một chuỗi `Function<OrderRequest,OrderReceipt>` có một input và một output logic. Spring Cloud Stream bind pipeline như một function tổng hợp.

**Câu 8.** MockMvc test trả 200 có chứng minh đơn đã thanh toán thành công?

**Đáp án:** Không. Lab chỉ validate, tính tiền và tạo biên nhận `ACCEPTED`; không có payment gateway hay database transaction.

**Câu 9.** Cần làm gì khi muốn xử lý đơn từ Kafka thay vì HTTP?

**Đáp án:** Bổ sung Spring Cloud Stream/binder, cấu hình `spring.cloud.function.definition` và binding/destination, kiểm thử JSON, retry, DLQ và idempotency. Không cần sao chép lại logic `OrderOperations`.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, FunctionCatalog và Function Composition](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications và HTTP composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Cloud Stream — Binding names và function composition](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud 2025.0.0 — Release announcement và Spring Boot 3.5.0 compatibility](https://spring.io/blog/2025/05/29/spring-cloud-2025-0-0-is-abvailable/)
- [Java 17 — Function, Supplier, Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java 17 — Math.multiplyExact, addExact, subtractExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
