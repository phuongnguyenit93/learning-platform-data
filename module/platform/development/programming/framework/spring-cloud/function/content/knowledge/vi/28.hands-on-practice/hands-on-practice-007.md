# Công bố cùng một hàm qua HTTP và Spring Cloud Stream

## 1. Bài toán thực hành

**Spring Cloud Function** (**SPRING_CLOUD_FUNCTION**) cho phép phát triển logic nghiệp vụ có thể tái sử dụng bằng **Supplier**, **Function** và **Consumer**, độc lập với giao thức gọi. **FunctionCatalog** quản lý các hàm, hỗ trợ composition và chuyển đổi message; các adapter đưa cùng một hàm ra HTTP, hệ thống sự kiện hoặc môi trường serverless.

Trong bài này, ta xây dựng một chức năng xử lý đơn hàng:

- Nhận **OrderRequest**.
- Kiểm tra mã đơn, khách hàng, số lượng và đơn giá.
- Tính tổng tiền.
- Trả về **OrderReceipt**.

Ta muốn hai nhóm client gọi **cùng một bean nghiệp vụ**:

1. Ứng dụng web hoặc đối tác gửi HTTP **POST /processOrder**.
2. Một hệ thống khác phát message vào destination **orders.in** của RabbitMQ; Spring Cloud Stream chuyển payload vào cùng function và gửi kết quả tới **orders.receipts**.

~~~text
                   HTTP POST /processOrder
                           |
                           v
                    Spring Cloud Function
                      Web adapter
                           |
                           v
                  +-------------------+
                  | FunctionCatalog   |
                  |   processOrder    |
                  +---------+---------+
                            |
                            v
              Function<OrderRequest, OrderReceipt>
                            ^
                            |
                  +---------+---------+
                  | FunctionCatalog   |
                  |   processOrder    |
                  +---------+---------+
                            ^
                            |
                      Stream adapter
                            ^
                            |
                     RabbitMQ binder
                            ^
                            |
                    orders.in destination

Stream output:
processOrder-out-0 -> orders.receipts
~~~

**Điểm cần chứng minh:** HTTP adapter và Stream binder đều gọi cùng functional bean **processOrder**. Chúng có cách nhận dữ liệu, chuyển đổi payload, xử lý lỗi và xác nhận giao nhận riêng; phần logic nghiệp vụ vẫn dùng chung.

Sau bài này, bạn có thể:

- Tạo một **Function<OrderRequest, OrderReceipt>** có kiểu rõ ràng.
- Export function qua Spring Cloud Function Web adapter.
- Bind cùng function vào input/output destination qua Spring Cloud Stream.
- Dùng Test Binder để kiểm thử luồng message mà không cần broker bên ngoài.
- Gửi request HTTP và quan sát JSON response.
- Hiểu **processOrder-in-0**, **processOrder-out-0**, **content-type** và **function.definition**.
- Phân biệt HTTP response với broker acknowledgment, retry và DLQ.

## 2. Kiến trúc: một function, hai adapter

Trong Spring Cloud Function, bean nghiệp vụ không cần biết nó được gọi từ HTTP hay RabbitMQ. Ví dụ:

~~~java
Function<OrderRequest, OrderReceipt> processOrder
~~~

Web adapter nhận HTTP request, chuyển body thành **OrderRequest**, tra cứu function và trả kết quả qua HTTP response. Stream binder nhận message từ destination, chuyển payload thành **OrderRequest**, gọi function rồi chuyển **OrderReceipt** thành output message.

| Thành phần | HTTP | Spring Cloud Stream |
| --- | --- | --- |
| Điểm vào | POST /processOrder | processOrder-in-0 |
| Transport | HTTP request | RabbitMQ message |
| Chuyển đổi input | JSON body → OrderRequest | Message payload + content type → OrderRequest |
| Logic | processOrder | processOrder |
| Chuyển đổi output | OrderReceipt → JSON response | OrderReceipt → output message |
| Điểm ra | HTTP response | processOrder-out-0 |
| Lỗi | HTTP error mapping | Binder error handling/retry/DLQ |

Hai adapter không làm cho semantics của giao thức trở nên giống nhau. Một HTTP request có response trực tiếp; một message broker thường có acknowledgment, delivery retry và dead-letter policy.

## 3. Chuẩn bị môi trường

Lab sử dụng:

- **JDK 17**.
- **Maven 3.9+**.
- **Spring Boot 3.5.0**.
- **Spring Cloud 2025.0.0**, release train tương thích với Spring Boot 3.5.x.
- Docker (chỉ cần nếu muốn chạy RabbitMQ thật ở phần mở rộng).

Các version Spring Cloud được quản lý qua BOM. Với dự án mới, chọn bản vá đang được hỗ trợ trong cùng release train; không tự đặt version riêng cho từng artifact Spring Cloud.

Tạo thư mục **dual-adapter-order-lab**:

~~~text
dual-adapter-order-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dualadapter/
    │   │   ├── OrderLabApplication.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderProcessor.java
    │   │   └── OrderFunctions.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/dualadapter/
            ├── OrderProcessorTest.java
            ├── OrderFunctionCatalogTest.java
            ├── OrderHttpTest.java
            └── OrderStreamTest.java
~~~

Tất cả lớp Java dùng package **com.example.dualadapter**.

## 4. Khai báo dependency Maven

Tạo **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>dual-adapter-order-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>dual-adapter-order-lab</name>

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
        <!-- HTTP runtime -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
        </dependency>

        <!-- Event-driven runtime: RabbitMQ binder -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
        </dependency>

        <!-- Tests -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-stream-test-binder</artifactId>
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

Vai trò dependency:

| Artifact | Vai trò |
| --- | --- |
| spring-boot-starter-web | Spring MVC và embedded server cho HTTP |
| spring-cloud-function-web | Export functional bean qua HTTP |
| spring-cloud-starter-stream-rabbit | Spring Cloud Stream RabbitMQ binder |
| spring-boot-starter-test | JUnit 5, Spring Test và MockMvc |
| spring-cloud-stream-test-binder | Test input/output binding trong môi trường test |

Trong dự án này, Rabbit binder là adapter chạy thật; Test Binder được dùng trong test scope. Nếu dự án chỉ cần Kafka, thay Rabbit starter bằng binder Kafka tương ứng và giữ BOM quản lý version.

## 5. Tạo payload và kết quả nghiệp vụ

### 5.1. OrderRequest.java

~~~java
package com.example.dualadapter;

public record OrderRequest(
        String orderId,
        String customerId,
        int quantity,
        long unitPriceVnd) {
}
~~~

### 5.2. OrderReceipt.java

~~~java
package com.example.dualadapter;

public record OrderReceipt(
        String orderId,
        String customerId,
        String status,
        long totalVnd) {
}
~~~

Payload có kiểu cụ thể giúp cả HTTP adapter và Stream binder chuyển đổi vào cùng hợp đồng Java. Không nên dùng **Map<String,Object>** nếu schema đơn hàng đã xác định; kiểu rõ ràng giúp compiler và test phát hiện lỗi sớm.

## 6. Viết logic nghiệp vụ độc lập với adapter

Tạo **OrderProcessor.java**:

~~~java
package com.example.dualadapter;

import java.util.Locale;

public final class OrderProcessor {

    private OrderProcessor() {
    }

    public static OrderReceipt process(OrderRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("request is required");
        }
        if (request.orderId() == null || request.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (request.customerId() == null
                || request.customerId().isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (request.unitPriceVnd() <= 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must be positive");
        }

        long total = Math.multiplyExact(
                request.unitPriceVnd(),
                request.quantity());

        return new OrderReceipt(
                request.orderId().trim().toUpperCase(Locale.ROOT),
                request.customerId().trim().toUpperCase(Locale.ROOT),
                "ACCEPTED",
                total);
    }
}
~~~

Logic:

- Từ chối request null.
- Bắt buộc orderId và customerId.
- Số lượng và đơn giá phải dương.
- Dùng Math.multiplyExact để phát hiện overflow.
- Chuẩn hóa mã định danh bằng Locale.ROOT.
- Trả OrderReceipt có trạng thái ACCEPTED.

ACCEPTED trong lab có nghĩa là đơn đã qua kiểm tra và được tính tiền. Nó **không** có nghĩa payment gateway đã thu tiền, database đã commit hoặc kho đã giữ hàng.

## 7. Đăng ký đúng một functional bean

Tạo **OrderFunctions.java**:

~~~java
package com.example.dualadapter;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Function<OrderRequest, OrderReceipt> processOrder() {
        return OrderProcessor::process;
    }
}
~~~

Đây là bean nghiệp vụ duy nhất mà hai adapter cùng sử dụng:

~~~text
Bean name: processOrder
Input:     OrderRequest
Output:    OrderReceipt
Type:      Function<OrderRequest, OrderReceipt>
~~~

Không tạo một controller tự tính tiền và một Stream consumer tự tính tiền lần nữa. Controller/adapter chỉ đảm nhiệm giao thức và gọi function.

### 7.1. Khởi tạo ứng dụng

Tạo **OrderLabApplication.java**:

~~~java
package com.example.dualadapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderLabApplication.class, args);
    }
}
~~~

## 8. Cấu hình function và Stream bindings

Tạo **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: dual-adapter-order-lab
  cloud:
    function:
      definition: processOrder
      single-function-fallback-enabled: false
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-processors
          content-type: application/json
        processOrder-out-0:
          destination: orders.receipts
          content-type: application/json

server:
  port: 8080
~~~

### 8.1. Đọc cấu hình

| Thuộc tính | Ý nghĩa |
| --- | --- |
| spring.cloud.function.definition | Chọn function processOrder để Spring Cloud Stream bind |
| processOrder-in-0 | Input binding của function |
| destination: orders.in | Destination nhận đơn hàng |
| group: order-processors | Consumer group của Stream binding |
| content-type: application/json | Payload input được chuyển đổi từ JSON |
| processOrder-out-0 | Output binding của function |
| destination: orders.receipts | Destination phát biên nhận |

Với một Function<I,O> imperative, function có một input và một output, do đó tên binding lần lượt là processOrder-in-0 và processOrder-out-0. Chỉ số bắt đầu từ 0.

### 8.2. Tại sao definition là processOrder?

spring.cloud.function.definition cho Spring Cloud Stream biết function nào cần bind. Nó không tạo một bean mới. Bean processOrder vẫn chỉ được khai báo một lần trong OrderFunctions.

Nếu sau này thêm normalizeOrder hoặc auditOrder, chỉ function nằm trong definition mới được Stream adapter bind theo cấu hình hiện tại. HTTP adapter có quy tắc export riêng; cần kiểm thử endpoint cụ thể thay vì suy luận từ binding name.

### 8.3. Không khai báo URL trong Stream binding

orders.in và orders.receipts là destination của binder (exchange/queue hoặc topic tùy broker), không phải HTTP URL. HTTP endpoint được web adapter ánh xạ từ tên function.

## 9. Kiểm thử nghiệp vụ thuần Java

Tạo **OrderProcessorTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderProcessorTest {

    @Test
    void calculatesOrderTotal() {
        OrderReceipt result = OrderProcessor.process(
                new OrderRequest(" o-501 ", " c-10 ", 3, 250_000L));

        assertEquals(
                new OrderReceipt(
                        "O-501", "C-10", "ACCEPTED", 750_000L),
                result);
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderProcessor.process(
                        new OrderRequest("O-502", "C-10", 0, 100L)));
    }

    @Test
    void detectsLongOverflow() {
        assertThrows(ArithmeticException.class,
                () -> OrderProcessor.process(
                        new OrderRequest(
                                "O-503", "C-10", 2, Long.MAX_VALUE)));
    }
}
~~~

Unit test này xác nhận logic nghiệp vụ không phụ thuộc HTTP hay broker. Nếu test thất bại, sửa logic trước khi điều tra adapter.

## 10. Kiểm thử FunctionCatalog

Tạo **OrderFunctionCatalogTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootTest(
        classes = OrderLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(TestChannelBinderConfiguration.class)
class OrderFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void looksUpAndInvokesTheSharedFunction() {
        Function<OrderRequest, OrderReceipt> function =
                catalog.lookup("processOrder");

        assertNotNull(function);

        OrderReceipt result = function.apply(
                new OrderRequest("O-501", "C-10", 3, 250_000L));

        assertEquals(
                new OrderReceipt(
                        "O-501", "C-10", "ACCEPTED", 750_000L),
                result);
    }
}
~~~

Test catalog xác nhận Spring đăng ký bean và FunctionCatalog có thể tra cứu theo tên. Nó chưa xác nhận HTTP route hoặc Stream binding.

## 11. Kiểm thử HTTP adapter bằng MockMvc

Tạo **OrderHttpTest.java**:

~~~java
package com.example.dualadapter;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderLabApplication.class)
@AutoConfigureMockMvc
@Import(TestChannelBinderConfiguration.class)
class OrderHttpTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesTheFunctionAsAnHttpEndpoint() throws Exception {
        mvc.perform(post("/processOrder")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "orderId": "o-501",
                                  "customerId": "c-10",
                                  "quantity": 3,
                                  "unitPriceVnd": 250000
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("O-501"))
                .andExpect(jsonPath("$.customerId").value("C-10"))
                .andExpect(jsonPath("$.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.totalVnd").value(750000));
    }
}
~~~

### 11.1. Gửi HTTP request bằng curl

Sau khi chạy ứng dụng:

~~~bash
curl -i -X POST "http://localhost:8080/processOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "orderId": "o-501",
    "customerId": "c-10",
    "quantity": 3,
    "unitPriceVnd": 250000
  }'
~~~

Response body mong đợi:

~~~json
{
  "orderId": "O-501",
  "customerId": "C-10",
  "status": "ACCEPTED",
  "totalVnd": 750000
}
~~~

Web adapter nhận request, dùng content type để chuyển JSON thành OrderRequest, gọi function rồi serialize OrderReceipt thành JSON response.

**HTTP status:** lời gọi function thành công thường trả 200 OK. Lỗi validation không tự động có một error schema phù hợp; nếu đây là API public, cần bổ sung error mapping và test status/body theo hợp đồng đã chọn.

## 12. Kiểm thử Stream adapter bằng Test Binder

Spring Cloud Stream Test Binder tạo input/output destination trong bộ nhớ để kiểm thử luồng message. Nó không cần chạy RabbitMQ thật.

Tạo **OrderStreamTest.java**:

~~~java
package com.example.dualadapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
        classes = OrderLabApplication.class,
        properties = {
                "spring.cloud.function.definition=processOrder"
        })
@Import(TestChannelBinderConfiguration.class)
class OrderStreamTest {

    @Autowired
    private InputDestination input;

    @Autowired
    private OutputDestination output;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void receivesOrderMessageAndPublishesReceipt() throws Exception {
        byte[] payload = objectMapper.writeValueAsBytes(
                new OrderRequest("O-601", "C-20", 2, 125_000L));

        Message<byte[]> message = MessageBuilder
                .withPayload(payload)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .build();

        input.send(message, "processOrder-in-0");

        Message<byte[]> result =
                output.receive(1_000, "processOrder-out-0");
        assertNotNull(result);

        OrderReceipt receipt = objectMapper.readValue(
                result.getPayload(), OrderReceipt.class);

        assertEquals(
                new OrderReceipt(
                        "O-601", "C-20", "ACCEPTED", 250_000L),
                receipt);
    }
}
~~~

### 12.1. Test Binder đang chứng minh điều gì?

Test gửi message tới processOrder-in-0, rồi đọc kết quả ở processOrder-out-0. Nó kiểm tra:

- Stream adapter đã tạo binding theo tên function.
- Input message được chuyển thành OrderRequest.
- Cùng processOrder thực thi.
- Kết quả OrderReceipt được phát ra output binding.

Đây là integration test ở mức binder trong bộ nhớ. Nó **không** chứng minh RabbitMQ đã tạo exchange/queue, broker giữ message bền vững hoặc retry/DLQ đã hoạt động.

### 12.2. Vì sao dùng byte[] và content type?

Test mô phỏng một message JSON trên đường transport. Content-Type giúp message converter biết payload là JSON và chuyển đổi sang kiểu đích của function. Nếu gửi một Java object trực tiếp, test có thể bỏ qua một phần đường serialization mà producer thật sẽ sử dụng.

Trong ứng dụng thật, kiểm tra cả:

- Header contentType từ producer.
- Cấu hình content-type của binding.
- Kiểu payload sau conversion.
- Schema/version JSON.

## 13. Chạy ứng dụng với RabbitMQ thật

Sau khi các test unit, catalog, HTTP và Test Binder pass, có thể chạy RabbitMQ để quan sát transport thật.

### 13.1. Khởi động RabbitMQ

Nếu đã cài Docker:

~~~bash
docker run -d --name scf-rabbit \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:3-management
~~~

Management UI mặc định có thể truy cập tại http://localhost:15672 với tài khoản mặc định của image là guest/guest khi truy cập từ localhost. Không dùng thông tin mặc định này trong môi trường production.

Rabbit binder dùng kết nối localhost theo cấu hình mặc định của Spring Cloud Stream Rabbit binder. Nếu broker chạy ở máy khác hoặc dùng credentials riêng, cấu hình binder tương ứng trong application.yml.

### 13.2. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Ứng dụng vừa mở HTTP server, vừa khởi tạo Stream binding:

~~~text
HTTP:
POST /processOrder

RabbitMQ:
orders.in -> processOrder-in-0
processOrder-out-0 -> orders.receipts
~~~

Hai đường vào có thể gọi cùng bean processOrder. Không nên gửi cùng một đơn qua cả HTTP và RabbitMQ nếu nghiệp vụ có side effect thật mà chưa có idempotency key; trong lab, function chỉ tính kết quả nên không tạo giao dịch bên ngoài.

### 13.3. Gửi message qua RabbitMQ

Có thể dùng RabbitMQ Management UI để publish một message tới exchange/queue đã được binder tạo, hoặc dùng producer Spring Cloud Stream riêng. Ví dụ payload:

~~~json
{
  "orderId": "O-701",
  "customerId": "C-31",
  "quantity": 4,
  "unitPriceVnd": 50000
}
~~~

Đặt content type là application/json. Kết quả mong đợi ở destination orders.receipts:

~~~json
{
  "orderId": "O-701",
  "customerId": "C-31",
  "status": "ACCEPTED",
  "totalVnd": 200000
}
~~~

Trong một hệ thống thật, dùng producer có schema/version và correlation ID rõ ràng; tránh phụ thuộc việc nhập message thủ công qua giao diện quản trị.

## 14. Cấu hình adapter và profile triển khai

Có thể bật HTTP và Stream cùng lúc như cấu hình lab. Với hệ thống thực, đôi khi cần triển khai hai instance khác nhau:

- Instance HTTP chỉ có web adapter.
- Instance event processor có Stream binder.

Cùng một artifact và cùng một function bean có thể chạy trong hai profile/deployment khác nhau. Điều này cho phép scale độc lập theo tải HTTP và event, đồng thời giảm coupling vận hành.

### 14.1. Ví dụ profile chỉ chạy HTTP

Nếu triển khai HTTP-only, tạo biến thể ứng dụng không có dependency Rabbit binder (vẫn giữ web adapter và module chứa function). Không cần tạo lại hoặc sao chép lớp OrderProcessor/OrderFunctions. Cách tách dependency theo artifact/profile giúp HTTP deployment không phải khởi tạo kết nối broker.

### 14.2. Ví dụ profile chạy Stream

**application-stream.yml**:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.in
          group: order-processors
          content-type: application/json
        processOrder-out-0:
          destination: orders.receipts
          content-type: application/json
~~~

Nếu không muốn expose HTTP, có thể không đưa web dependency vào artifact Stream riêng hoặc triển khai gateway/network policy phù hợp. Chỉ đặt server.port=-1 không phải là cách thay thế cho việc thiết kế bề mặt public và dependency đúng.

Khi dùng chung một artifact có cả hai adapter, hãy xác minh bằng integration test rằng endpoint có tên function vẫn hoạt động khi Stream binding được bật. Theo quy tắc web mapping, các function trong catalog được ánh xạ theo tên ở URL; thuộc tính definition cũng có thể tạo mapping mặc định cho root path hoặc lọc tập function được export.

## 15. Xử lý lỗi khác nhau giữa HTTP và message broker

Function có thể ném IllegalArgumentException khi request sai. Nhưng hai adapter phải biểu diễn lỗi theo hợp đồng riêng.

| Vấn đề | HTTP | Spring Cloud Stream |
| --- | --- | --- |
| Input sai schema | Thường lỗi conversion trước khi gọi function | Message conversion error ở consumer |
| Validation nghiệp vụ | Cần map thành status 4xx và body lỗi | Có thể kích hoạt error handling/retry tùy cấu hình |
| Lỗi tạm thời | Client có thể retry request | Binder có retry policy |
| Lỗi không thể xử lý | Trả error response | Có thể chuyển DLQ/quarantine |
| Thành công | HTTP response | Output message và acknowledgment theo binder |

Không giả định:

- HTTP 200 tương đương message broker ACK.
- HTTP 500 tự động tạo DLQ.
- Function ném exception thì broker chắc chắn redeliver.
- Output message đã publish đồng nghĩa database transaction đã commit.

Hãy cấu hình và test từng adapter.

### 15.1. Idempotency khi cùng function được gọi từ hai giao thức

Một client có thể gửi HTTP request nhưng bị timeout, sau đó producer khác phát lại cùng đơn qua broker. Nếu function có side effect như ghi database hoặc gọi payment API, cùng nghiệp vụ có thể chạy hai lần.

Trong production:

1. Dùng một orderId hoặc idempotencyKey có quy tắc duy nhất.
2. Kiểm tra/ghi nhận trạng thái xử lý nguyên tử ở tầng persistence.
3. Không dựa vào correlation ID làm idempotency key nếu một luồng có nhiều thao tác khác nhau.
4. Thiết kế outbox khi cần phát event sau khi transaction commit.
5. Test cùng request được gửi lặp qua cả HTTP và Stream.

Lab chỉ tính tiền và trả receipt, không ghi database; vì vậy chưa triển khai idempotency storage.

## 16. Quan sát và vận hành

Hai adapter cần log và metrics có thể liên kết:

- orderId: định danh nghiệp vụ.
- correlationId: nối các bước xử lý trong một luồng.
- source: nguồn dữ liệu khai báo trong payload (cần xác minh nếu dùng cho policy).
- Adapter: HTTP hay Stream.
- Thời gian xử lý và kết quả.

Không log token, thông tin thanh toán nhạy cảm hoặc toàn bộ payload nếu không cần thiết. Dùng Micrometer/observation và tracing phù hợp với stack triển khai; không dùng log message thô làm hệ thống audit duy nhất.

Khi scale:

- HTTP có thể scale theo request concurrency và latency.
- Stream consumer scale theo partition/queue concurrency và khả năng downstream.
- Cùng một function không có nghĩa hai adapter phải có cùng tài nguyên, timeout hoặc retry.

## 17. Bài tập mở rộng

### Bài A — Thêm trường currency

Mở rộng OrderRequest với currency. Chỉ chấp nhận VND trong lab.

**Yêu cầu:**

- Update unit test.
- Gửi HTTP JSON có currency.
- Gửi message Test Binder có currency.
- Cả hai adapter gọi cùng logic và cho cùng kết quả.

### Bài B — Thêm correlation ID

Producer gửi correlationId qua HTTP header và message header. Thiết kế cách map metadata vào function hoặc log context.

**Yêu cầu:** kiểm tra ID được ghi nhận ở cả hai adapter; không đưa header xác thực vào output.

### Bài C — Thêm một Consumer audit

Tạo Consumer<OrderReceipt> auditOrder ghi nhận receipt sau xử lý. Xác định cách composition processOrder|auditOrder ảnh hưởng output:

- Kết quả pipeline trở thành consumer, không còn trả OrderReceipt như function ban đầu.
- Nếu vẫn cần output receipt, hãy thiết kế audit ở adapter hoặc tạo một function trả lại receipt sau side effect có chủ đích.

### Bài D — Chuyển từ RabbitMQ sang Kafka

Thay Rabbit binder bằng Kafka binder do BOM quản lý. Giữ nguyên OrderProcessor và processOrder.

**Yêu cầu:** cấu hình broker, destination, consumer group, serialization, retry/DLQ và kiểm thử message thực tế.

### Bài E — Chạy hai deployment độc lập

Tạo hai profile/container:

- HTTP deployment nhận request từ API gateway.
- Stream deployment nhận event từ RabbitMQ.

**Yêu cầu:** dùng cùng function code, scale độc lập, chỉ expose cổng phù hợp và giải thích cách quản lý version schema khi rolling deployment.

### Bài F — Kiểm thử lỗi ở cả hai adapter

Gửi quantity âm hoặc unitPriceVnd bằng 0:

- HTTP: xác định status/body lỗi.
- Stream: xác định retry, DLQ và acknowledgment.

**Yêu cầu:** viết hai integration test riêng; không dùng kết quả của một adapter để suy ra adapter còn lại.

## 18. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| POST /processOrder trả 404 | Web adapter chưa được thêm hoặc tên endpoint sai | Kiểm tra spring-cloud-function-web, mapping và log |
| HTTP nhận JSON nhưng function không được gọi | Content type hoặc schema không phù hợp | Kiểm tra Content-Type và record |
| Stream không tạo input binding | Sai spring.cloud.function.definition | Kiểm tra tên processOrder |
| Message vào nhưng không có output | Conversion/function lỗi hoặc output binding sai | Kiểm tra log, processOrder-out-0 và destination |
| FunctionCatalog.lookup trả null | Bean không được scan hoặc sai tên | Kiểm tra @Bean và package |
| Test Binder không tìm thấy destination | Binding name sai | Dùng processOrder-in-0/processOrder-out-0 |
| Test Binder không chuyển JSON | Thiếu content type hoặc gửi payload không phù hợp | Gắn application/json, kiểm tra byte[]/DTO |
| Rabbit binder không kết nối | Broker chưa chạy hoặc credentials sai | Kiểm tra port 5672 và binder environment |
| HTTP pass nhưng Stream fail | Binder/serialization/retry khác web adapter | Viết Stream integration test riêng |
| Message được xử lý hai lần | Delivery retry hoặc producer gửi duplicate | Thiết kế idempotency |
| Cùng function nhưng kết quả khác | Hai adapter cung cấp payload/schema khác nhau | So sánh JSON, content type và conversion |
| Error status không đúng kỳ vọng | Chưa cấu hình HTTP error mapping | Xác định API error contract |
| Broker không gửi DLQ | Chưa bật binder DLQ/retry policy | Kiểm tra cấu hình theo binder |
| Expose nhầm function khác | Adapter công bố nhiều bean ngoài dự kiến | Kiểm tra web routing và gateway/network policy |

### 18.1. Trình tự debug

1. Chạy java -version và mvn -version.
2. Chạy mvn test để xác minh nghiệp vụ thuần Java.
3. Test FunctionCatalog.lookup("processOrder").
4. Test HTTP bằng MockMvc.
5. Test Stream bằng Test Binder.
6. Chỉ sau đó mới chạy RabbitMQ thật.
7. Kiểm tra riêng output destination, error policy và duplicate delivery.

## 19. Tiêu chí hoàn thành

| Tiêu chí | Minh chứng |
| --- | --- |
| Một bean nghiệp vụ | Function<OrderRequest,OrderReceipt> processOrder chỉ khai báo một lần |
| HTTP adapter | POST /processOrder trả JSON receipt |
| Stream adapter | processOrder-in-0 nhận JSON và processOrder-out-0 phát receipt |
| Catalog | FunctionCatalog.lookup("processOrder") thành công |
| HTTP test | MockMvc xác nhận status và response fields |
| Stream test | Test Binder xác nhận input/output message |
| Cùng logic | HTTP và Stream tạo kết quả nghiệp vụ giống nhau |
| Hiểu content type | JSON được chuyển thành DTO ở cả hai adapter |
| Hiểu lỗi | Không nhầm HTTP response với broker ACK/retry/DLQ |
| Vận hành | Biết cấu hình profile, idempotency và quan sát |

**Tóm tắt:** Một functional bean có thể được dùng bởi nhiều adapter. Spring Cloud Function Web adapter biến function thành HTTP endpoint; Spring Cloud Stream binder kết nối cùng function với destination sự kiện. Payload và logic nghiệp vụ được tái sử dụng, còn content negotiation, binding, error handling, retry, acknowledgment và bảo mật vẫn cần cấu hình/test theo từng giao thức.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Bean nào được hai adapter dùng chung trong bài?

**Đáp án:** processOrder, có kiểu Function<OrderRequest, OrderReceipt>.

**Câu 2.** HTTP endpoint của function có tên gì?

**Đáp án:** POST /processOrder theo web adapter.

**Câu 3.** Tên input và output binding mặc định là gì?

**Đáp án:** processOrder-in-0 và processOrder-out-0.

**Câu 4.** spring.cloud.function.definition có tạo thêm function bean không?

**Đáp án:** Không. Nó chọn function definition cho adapter; bean nghiệp vụ vẫn được khai báo một lần.

**Câu 5.** Test Binder có cần RabbitMQ đang chạy không?

**Đáp án:** Không. Test Binder tạo binding trong bộ nhớ; Rabbit binder thật mới cần broker.

**Câu 6.** HTTP trả 200 có đồng nghĩa RabbitMQ đã ACK message không?

**Đáp án:** Không. Hai adapter có semantics thành công và xác nhận giao nhận khác nhau.

**Câu 7.** Vì sao phải đặt content-type: application/json cho Stream input?

**Đáp án:** Để message converter biết payload là JSON và chuyển thành OrderRequest.

**Câu 8.** Nếu function có side effect, cùng request đi qua HTTP và Stream có thể gây vấn đề gì?

**Đáp án:** Có thể xử lý trùng. Cần idempotency và transaction/outbox phù hợp.

**Câu 9.** Có thể chỉ test FunctionCatalog rồi kết luận cả HTTP và RabbitMQ hoạt động không?

**Đáp án:** Không. Cần test riêng web adapter, Stream binder và broker thực tế theo phạm vi triển khai.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model và FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Function — HTTP function mapping và filtering rules](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud — Release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Function API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html)
