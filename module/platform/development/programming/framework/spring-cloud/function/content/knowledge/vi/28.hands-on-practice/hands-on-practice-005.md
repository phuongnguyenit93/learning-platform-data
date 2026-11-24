# Bổ sung metadata và kiểm chứng quy tắc truyền header

## 1. Bài toán thực hành

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đóng gói thành `Supplier`, `Function` hoặc `Consumer` và được `FunctionCatalog` quản lý để có thể tái sử dụng qua HTTP, hệ thống sự kiện hoặc serverless. Khi một hàm nhận dữ liệu, đôi khi payload chưa đủ để xử lý hoặc truy vết: ứng dụng còn cần **metadata** như mã tương quan, nguồn gửi, loại nội dung và dấu vết xử lý.

Ví dụ một hệ thống nhận yêu cầu đơn hàng:

~~~json
{
  "orderId": "O-501",
  "amountVnd": 750000,
  "source": "PARTNER-A"
}
~~~

Payload mô tả **đơn hàng**. Header mô tả **ngữ cảnh của message**:

| Header | Ý nghĩa | Dùng trong lab |
| --- | --- | --- |
| `correlationId` | Liên kết nhiều message/lần xử lý thuộc cùng một luồng nghiệp vụ | Giữ nguyên từ input tới output |
| `sourceSystem` | Hệ thống nguồn đã gửi message | Giữ để truy vết nguồn |
| `contentType` | Định dạng payload, ví dụ JSON | Đặt lại đúng kiểu cho output |
| `receivedBy` | Thành phần đã nhận/enrich message | Thêm ở stage đầu |
| `processedBy` | Thành phần đã tạo kết quả | Thêm ở stage xử lý |
| `authorization` | Thông tin xác thực nhạy cảm nếu có | Không copy vào output |

Ta sẽ tạo pipeline:

~~~text
Message<OrderRequest>
  payload + correlationId + sourceSystem
                |
                v
          enrichMetadata
       - giữ correlationId
       - giữ sourceSystem
       - thêm receivedBy
       - contentType = application/json
                |
                v
          processOrder
       - đọc OrderRequest
       - tạo OrderReceipt
       - giữ metadata được phép
       - thêm processedBy
                |
                v
         formatReceipt
       - đổi payload thành String
       - giữ correlationId
       - contentType = text/plain
                |
                v
Message<String>
~~~

**Mục tiêu của bài:** học cách thêm metadata, kiểm soát header được truyền giữa các bước và kiểm thử bằng Spring Messaging cùng `FunctionCatalog`. Ta sẽ chủ động chọn header cần giữ; không dựa vào giả định rằng mọi header từ producer đều phải được chuyển tiếp.

Sau bài này, bạn có thể:

1. Phân biệt payload, message headers và metadata nghiệp vụ.
2. Tạo message mới bằng `MessageBuilder`.
3. Giữ một tập header cho phép (*allowlist*) qua từng stage.
4. Thay `contentType` khi thay đổi kiểu payload.
5. Giữ `correlationId` để theo dõi luồng xử lý.
6. Không vô tình chuyển tiếp header nhạy cảm hoặc header nội bộ.
7. Kiểm tra header bằng JUnit và `FunctionCatalog`.
8. Phân biệt kiểm thử catalog với kiểm thử header mapping của HTTP/binder.

> **Phạm vi:** Lab dùng Java 17, Spring Boot và Spring Cloud Function trong một application context. Không cần broker, database hoặc cloud account. Các lệnh Maven là dành cho người học chạy trong dự án mẫu; bài không yêu cầu chạy build trên máy tạo nội dung.

## 2. Payload và metadata khác nhau thế nào?

Một Spring `Message<T>` có hai thành phần:

- **Payload:** dữ liệu chính mà function xử lý, kiểu `T`.
- **Headers:** metadata mô tả message và ngữ cảnh truyền tải.

~~~text
Message<OrderRequest>
  +--------------------------------------+
  | Headers                              |
  |  correlationId = "corr-501"          |
  |  sourceSystem  = "partner-a"         |
  |  contentType   = application/json    |
  +--------------------------------------+
  | Payload                              |
  |  OrderRequest("O-501", 750000, ...)  |
  +--------------------------------------+
~~~

Không nên đưa mọi thứ vào header. Ví dụ:

| Thông tin | Vị trí phù hợp | Lý do |
| --- | --- | --- |
| Mã đơn hàng | Payload | Là dữ liệu nghiệp vụ cần validate và lưu |
| Số tiền | Payload | Ảnh hưởng trực tiếp nghiệp vụ |
| Mã tương quan | Header | Metadata dùng để liên kết nhiều message |
| Content type | Header | Mô tả cách đọc payload |
| Thành phần đã xử lý | Header | Thông tin quan sát/trace |
| Token bí mật | Security context/secure transport | Không nên phát tán qua message output hoặc log |
| Quyền của người dùng | Security context đã xác thực | Không tin một header tự khai do producer gửi |

**Nguyên tắc:** header bổ sung ngữ cảnh cho payload, không thay thế schema nghiệp vụ. Nếu một trường là điều kiện để tính tiền, phê duyệt hay lưu đơn, hãy đặt nó trong payload và kiểm tra bằng kiểu dữ liệu/validation rõ ràng.

## 3. Quy tắc truyền header cần kiểm chứng

Trong một pipeline có nhiều function, cần phân biệt ba việc:

1. **Function có nhận được Message không?** Nếu chữ ký là `Function<OrderRequest, OrderReceipt>`, hàm nhận payload theo kiểu đã khai báo; nó không trực tiếp đọc headers như một tham số độc lập.
2. **Function có trả Message không?** Nếu chữ ký là `Function<Message<OrderRequest>, Message<OrderReceipt>>`, function có thể đọc headers và tạo message đầu ra có metadata.
3. **Adapter/binder có giữ header trên đường truyền không?** Việc này còn phụ thuộc adapter, broker và cấu hình header mapping; test catalog không tự chứng minh được điều đó.

### 3.1. Dùng Message<T> khi nghiệp vụ cần metadata

Chữ ký chỉ nhận payload:

~~~java
Function<OrderRequest, OrderReceipt>
~~~

phù hợp khi logic chỉ cần dữ liệu đơn hàng.

Chữ ký nhận message:

~~~java
Function<Message<OrderRequest>, Message<OrderReceipt>>
~~~

phù hợp khi function cần đọc hoặc ghi metadata. Không phải function nào cũng nên nhận `Message<?>`: nếu không dùng header, kiểu payload trực tiếp thường đơn giản và dễ tái sử dụng hơn.

### 3.2. Header không phải Map có thể sửa trực tiếp

`MessageHeaders` là cấu trúc header bất biến. Không nên viết:

~~~java
// Không sửa trực tiếp MessageHeaders của message đầu vào.
input.getHeaders().put("processedBy", "order-processor");
~~~

Thay vào đó, tạo message mới bằng `MessageBuilder`:

~~~java
Message<OrderReceipt> output = MessageBuilder
        .withPayload(receipt)
        .setHeader("correlationId", correlationId)
        .build();
~~~

Việc tạo message mới giúp ta **chủ động chọn payload và metadata** cho stage tiếp theo.

### 3.3. Sao chép tất cả headers hay chỉ một số?

Spring Messaging cung cấp các API như `MessageBuilder.fromMessage(...)` và `copyHeaders(...)` để sao chép header. Điều này tiện trong trường hợp thật sự muốn chuyển tiếp toàn bộ metadata.

~~~java
Message<?> output = MessageBuilder
        .withPayload(newPayload)
        .copyHeaders(input.getHeaders())
        .build();
~~~

Nhưng trong một ứng dụng có nhiều producer/adapter, copy toàn bộ headers có thể vô tình đưa theo:

- Header xác thực hoặc dữ liệu nhạy cảm.
- Header nội bộ của binder/framework không có ý nghĩa ở output.
- Header content type cũ không còn phù hợp với payload mới.
- Header routing không nên ảnh hưởng tới stage tiếp theo.

Lab sẽ dùng **allowlist header**: chỉ sao chép các tên đã được ứng dụng cho phép, rồi thiết lập lại content type cho output. Cách này làm rõ hợp đồng giữa các stage.

## 4. Chuẩn bị dự án Maven

Lab dùng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0** làm mốc minh họa cho các dependency. Đây là cấu hình tham khảo để các đoạn mã có cùng hệ phiên bản; khi tạo dự án mới, hãy chọn bản vá được hỗ trợ và BOM tương thích với Spring Boot của dự án.

Tạo thư mục `message-metadata-lab`:

~~~text
message-metadata-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/metadata/
    │   │   ├── MetadataLabApplication.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderPolicy.java
    │   │   ├── HeaderNames.java
    │   │   ├── HeaderPolicy.java
    │   │   └── OrderMessageFunctions.java
    │   └── resources/application.yml
    └── test/java/com/example/metadata/
        ├── OrderPolicyTest.java
        ├── HeaderPolicyTest.java
        └── MessageMetadataCatalogTest.java
~~~

Các class nằm trong package `com.example.metadata` để Spring Boot scan được cấu hình và functional bean.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>message-metadata-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>message-metadata-lab</name>

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
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
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

Dependency:

| Artifact | Vai trò |
| --- | --- |
| `spring-boot-starter` | Spring ApplicationContext |
| `spring-cloud-function-context` | `FunctionCatalog` và functional bean |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test và assertion |

Không cần web adapter hoặc binder cho các test trong bài. Nếu sau này chạy qua HTTP hoặc broker, bổ sung adapter và integration test phù hợp.

## 5. Tạo payload nghiệp vụ

### 5.1. OrderRequest.java

~~~java
package com.example.metadata;

public record OrderRequest(
        String orderId,
        long amountVnd,
        String source) {
}
~~~

### 5.2. OrderReceipt.java

~~~java
package com.example.metadata;

public record OrderReceipt(
        String orderId,
        String status,
        long amountVnd) {
}
~~~

Payload là record có kiểu rõ ràng. Header không cần chứa lại `orderId` hay `amountVnd` vì những trường này đã thuộc schema nghiệp vụ.

### 5.3. OrderPolicy.java

~~~java
package com.example.metadata;

import java.util.Locale;

public final class OrderPolicy {

    private OrderPolicy() {
    }

    public static OrderReceipt process(OrderRequest order) {
        if (order == null) {
            throw new IllegalArgumentException("order is required");
        }
        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (order.source() == null || order.source().isBlank()) {
            throw new IllegalArgumentException("source is required");
        }
        if (order.amountVnd() <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        return new OrderReceipt(
                order.orderId().trim().toUpperCase(Locale.ROOT),
                "ACCEPTED",
                order.amountVnd());
    }
}
~~~

Đây là logic nghiệp vụ thuần Java. Nó không nhận `Message<?>`, không đọc `correlationId` và không phụ thuộc Spring. Nếu sau này đổi HTTP sang Kafka hoặc serverless, quy tắc xử lý đơn vẫn có thể dùng lại.

**Lưu ý locale:** Với mã định danh có thể chứa chữ cái cần chuẩn hóa, nên dùng `toUpperCase(Locale.ROOT)` thay vì phụ thuộc locale mặc định của máy. Bài giữ đoạn code ngắn; có thể bổ sung locale rõ ràng trong bài tập.

## 6. Khai báo tên header và chính sách allowlist

### 6.1. HeaderNames.java

~~~java
package com.example.metadata;

public final class HeaderNames {

    private HeaderNames() {
    }

    public static final String CORRELATION_ID = "correlationId";
    public static final String SOURCE_SYSTEM = "sourceSystem";
    public static final String RECEIVED_BY = "receivedBy";
    public static final String PROCESSED_BY = "processedBy";
    public static final String AUTHORIZATION = "authorization";
}
~~~

Tập trung tên header giúp tránh lỗi chính tả giữa producer, function và test. `correlationId` là **mã tương quan của luồng xử lý**, không đồng nghĩa với `MessageHeaders.ID` là định danh của một message cụ thể.

### 6.2. HeaderPolicy.java

~~~java
package com.example.metadata;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HeaderPolicy {

    private HeaderPolicy() {
    }

    @SafeVarargs
    public static <T> MessageBuilder<T> withAllowedHeaders(
            Message<?> input,
            T payload,
            String... allowedNames) {

        MessageBuilder<T> builder = MessageBuilder.withPayload(payload);

        for (String name : allowedNames) {
            Object value = input.getHeaders().get(name);
            if (value != null) {
                builder.setHeader(name, value);
            }
        }

        return builder;
    }
}
~~~

Hàm này:

1. Tạo một message mới với payload mới.
2. Duyệt danh sách tên header được phép.
3. Chỉ copy header có giá trị khác `null`.
4. Không copy tự động toàn bộ header từ input.

Vì vậy, dù producer gửi thêm `authorization`, `spring.cloud.function.definition` hoặc một header nội bộ không được liệt kê, chúng không tự xuất hiện trong message đầu ra.

**Lưu ý:** `@SafeVarargs` hợp lệ ở đây vì method là `static` và dùng varargs `String` (kiểu reifiable). Có thể bỏ annotation này nếu muốn code tối giản; nó không thay đổi hành vi.

### 6.3. Tại sao không copy tất cả header?

Giả sử message input có:

~~~text
correlationId = corr-501
sourceSystem  = partner-a
authorization = Bearer secret-token
debug         = true
spring.cloud.function.definition = internalAdmin
~~~

Output chỉ nên giữ metadata cần thiết:

~~~text
correlationId = corr-501
sourceSystem  = partner-a
receivedBy    = order-intake-v1
processedBy   = order-processor-v1
contentType   = application/json
~~~

Header `authorization` không được phát tán tiếp. Header `debug` và routing definition cũng không cần thiết cho payload kết quả. Đây là lý do ta sử dụng allowlist.

## 7. Xây dựng các function có nhận và trả Message

Tạo `OrderMessageFunctions.java`:

~~~java
package com.example.metadata;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeTypeUtils;

@Configuration(proxyBeanMethods = false)
public class OrderMessageFunctions {

    @Bean
    public Function<Message<OrderRequest>, Message<OrderRequest>>
            enrichMetadata() {

        return input -> {
            OrderRequest order = input.getPayload();

            MessageBuilder<OrderRequest> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            order,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.SOURCE_SYSTEM);

            builder.setHeader(
                    HeaderNames.RECEIVED_BY,
                    "order-intake-v1");
            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON);

            return builder.build();
        };
    }

    @Bean
    public Function<Message<OrderRequest>, Message<OrderReceipt>>
            processOrder() {

        return input -> {
            OrderReceipt receipt =
                    OrderPolicy.process(input.getPayload());

            MessageBuilder<OrderReceipt> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            receipt,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.SOURCE_SYSTEM,
                            HeaderNames.RECEIVED_BY);

            builder.setHeader(
                    HeaderNames.PROCESSED_BY,
                    "order-processor-v1");
            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON);

            return builder.build();
        };
    }

    @Bean
    public Function<Message<OrderReceipt>, Message<String>>
            formatReceipt() {

        return input -> {
            OrderReceipt receipt = input.getPayload();
            String text = "ORDER=" + receipt.orderId()
                    + ";STATUS=" + receipt.status()
                    + ";AMOUNT=" + receipt.amountVnd();

            MessageBuilder<String> builder =
                    HeaderPolicy.withAllowedHeaders(
                            input,
                            text,
                            HeaderNames.CORRELATION_ID,
                            HeaderNames.RECEIVED_BY,
                            HeaderNames.PROCESSED_BY);

            builder.setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.TEXT_PLAIN);

            return builder.build();
        };
    }
}
~~~

### 7.1. Phân tích stage enrichMetadata

Chữ ký:

~~~java
Function<Message<OrderRequest>, Message<OrderRequest>>
~~~

Stage nhận payload đơn hàng cùng headers, sau đó tạo message mới. Nó:

- Giữ `correlationId` và `sourceSystem` nếu có.
- Thêm `receivedBy` do server kiểm soát.
- Đặt `contentType` là `application/json`.
- Không giữ `authorization` hoặc routing header không nằm trong allowlist.

Stage này không thay đổi dữ liệu đơn hàng; nó chỉ bổ sung metadata.

### 7.2. Phân tích stage processOrder

Chữ ký:

~~~java
Function<Message<OrderRequest>, Message<OrderReceipt>>
~~~

Stage gọi `OrderPolicy.process` với payload. Sau khi tạo biên nhận, nó copy ba header được phép và thêm `processedBy`. Đây là nơi đổi kiểu payload từ `OrderRequest` thành `OrderReceipt`.

### 7.3. Phân tích stage formatReceipt

Chữ ký:

~~~java
Function<Message<OrderReceipt>, Message<String>>
~~~

Stage đổi payload thành chuỗi văn bản, vì vậy nó đổi `contentType` sang `text/plain`. Nếu giữ nguyên `application/json` trong khi output là plain text, consumer phía sau có thể chọn converter sai hoặc diễn giải body không đúng.

### 7.4. Vì sao mỗi stage phải chủ động copy header?

Mỗi stage tạo một message đầu ra mới. Bằng cách sử dụng `HeaderPolicy.withAllowedHeaders`, ta viết rõ:

- Metadata nào được chuyển qua.
- Metadata nào bị loại bỏ.
- Header nào cần thay đổi khi kiểu payload thay đổi.

Nếu stage sau không copy `correlationId`, metadata đó sẽ không còn trong message đầu ra do stage đó tạo. Vì vậy, quy tắc truyền header là **một phần của hợp đồng mỗi stage**, cần được test thay vì suy đoán.

## 8. Khởi tạo Spring Boot

Tạo `MetadataLabApplication.java`:

~~~java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MetadataLabApplication.class, args);
    }
}
~~~

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: message-metadata-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Không cần khai báo `spring.cloud.function.definition` trong phần test catalog: ta muốn tra cứu từng function và chuỗi composition trực tiếp qua `FunctionCatalog`. Khi đưa pipeline vào một adapter cụ thể, cấu hình function/binding sẽ được bổ sung ở bước triển khai.

## 9. Unit test cho logic nghiệp vụ

Tạo `OrderPolicyTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderPolicyTest {

    @Test
    void processesValidOrder() {
        OrderReceipt result = OrderPolicy.process(
                new OrderRequest("O-501", 750_000L, "PARTNER-A"));

        assertEquals(
                new OrderReceipt("O-501", "ACCEPTED", 750_000L),
                result);
    }

    @Test
    void rejectsMissingOrderId() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.process(
                        new OrderRequest(" ", 100L, "PARTNER-A")));
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderPolicy.process(
                        new OrderRequest("O-502", 0L, "PARTNER-A")));
    }
}
~~~

Unit test này không cần Spring. Nó chứng minh quy tắc nghiệp vụ độc lập với message metadata.

## 10. Unit test cho HeaderPolicy và MessageHeaders

Tạo `HeaderPolicyTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class HeaderPolicyTest {

    @Test
    void copiesOnlyAllowedHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("input")
                .setHeader(HeaderNames.CORRELATION_ID, "corr-501")
                .setHeader(HeaderNames.SOURCE_SYSTEM, "partner-a")
                .setHeader(HeaderNames.AUTHORIZATION, "secret-token")
                .setHeader("debug", true)
                .build();

        Message<String> output = HeaderPolicy
                .withAllowedHeaders(
                        input,
                        "output",
                        HeaderNames.CORRELATION_ID,
                        HeaderNames.SOURCE_SYSTEM)
                .build();

        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
        assertNull(output.getHeaders().get("debug"));
    }

    @Test
    void messageHeadersAreNotMutable() {
        Message<String> message = MessageBuilder
                .withPayload("payload")
                .build();

        assertThrows(UnsupportedOperationException.class,
                () -> message.getHeaders().put("newHeader", "value"));
    }

    @Test
    void sourceMessageIsNotChangedWhenOutputIsBuilt() {
        Message<String> input = MessageBuilder
                .withPayload("before")
                .setHeader(HeaderNames.CORRELATION_ID, "corr-502")
                .build();

        Message<String> output = HeaderPolicy
                .withAllowedHeaders(
                        input,
                        "after",
                        HeaderNames.CORRELATION_ID)
                .build();

        assertEquals("before", input.getPayload());
        assertEquals("after", output.getPayload());
        assertEquals("corr-502",
                input.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("corr-502",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
    }
}
~~~

Ba test này kiểm chứng ba quy tắc:

1. Header chỉ được copy nếu tên nằm trong allowlist.
2. `MessageHeaders` của message hiện tại không thể sửa trực tiếp.
3. Xây message đầu ra không làm thay đổi payload hoặc header của message đầu vào.

Không assert `MessageHeaders.ID` hoặc `timestamp` phải giữ nguyên. Đây là metadata do Spring quản lý cho từng message; khi tạo message mới, chúng có thể được tạo lại. `correlationId` là header nghiệp vụ/trace riêng, cần được giữ theo hợp đồng mà ứng dụng định nghĩa.

## 11. Kiểm thử FunctionCatalog và composition

Tạo `MessageMetadataCatalogTest.java`:

~~~java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
        classes = MetadataLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MessageMetadataCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    private Message<OrderRequest> inputMessage() {
        return MessageBuilder
                .withPayload(new OrderRequest(
                        "O-501", 750_000L, "PARTNER-A"))
                .setHeader(HeaderNames.CORRELATION_ID, "corr-501")
                .setHeader(HeaderNames.SOURCE_SYSTEM, "partner-a")
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON)
                .setHeader(HeaderNames.AUTHORIZATION, "secret-token")
                .setHeader(
                        "spring.cloud.function.definition",
                        "internalFunction")
                .build();
    }

    @Test
    void enrichesMetadataWithoutChangingPayload() {
        Function<Message<OrderRequest>, Message<OrderRequest>> function =
                catalog.lookup("enrichMetadata");
        assertNotNull(function);

        Message<OrderRequest> input = inputMessage();
        Message<OrderRequest> output = function.apply(input);

        assertEquals(input.getPayload(), output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertEquals("order-intake-v1",
                output.getHeaders().get(HeaderNames.RECEIVED_BY));
        assertEquals(
                MimeTypeUtils.APPLICATION_JSON,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
        assertNull(output.getHeaders().get(
                "spring.cloud.function.definition"));
    }

    @Test
    void processOrderPreservesAllowedMetadataAndAddsProcessor() {
        Function<Message<OrderRequest>, Message<OrderReceipt>> function =
                catalog.lookup("processOrder");
        assertNotNull(function);

        Message<OrderReceipt> output =
                function.apply(inputMessage());

        assertEquals(
                new OrderReceipt("O-501", "ACCEPTED", 750_000L),
                output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("partner-a",
                output.getHeaders().get(HeaderNames.SOURCE_SYSTEM));
        assertEquals("order-processor-v1",
                output.getHeaders().get(HeaderNames.PROCESSED_BY));
        assertEquals(
                MimeTypeUtils.APPLICATION_JSON,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        assertNull(output.getHeaders().get(HeaderNames.AUTHORIZATION));
    }

    @Test
    void compositionCarriesCorrelationAcrossStages() {
        Function<Message<OrderRequest>, Message<OrderReceipt>> pipeline =
                catalog.lookup("enrichMetadata|processOrder");
        assertNotNull(pipeline);

        Message<OrderReceipt> output =
                pipeline.apply(inputMessage());

        assertEquals("O-501", output.getPayload().orderId());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("order-intake-v1",
                output.getHeaders().get(HeaderNames.RECEIVED_BY));
        assertEquals("order-processor-v1",
                output.getHeaders().get(HeaderNames.PROCESSED_BY));
    }

    @Test
    void fullCompositionUpdatesContentTypeWhenPayloadChanges() {
        Function<Message<OrderRequest>, Message<String>> pipeline =
                catalog.lookup(
                        "enrichMetadata|processOrder|formatReceipt");
        assertNotNull(pipeline);

        Message<String> output = pipeline.apply(inputMessage());

        assertEquals(
                "ORDER=O-501;STATUS=ACCEPTED;AMOUNT=750000",
                output.getPayload());
        assertEquals("corr-501",
                output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals(
                MimeTypeUtils.TEXT_PLAIN,
                output.getHeaders().get(MessageHeaders.CONTENT_TYPE));
    }

    @Test
    void missingOptionalCorrelationIdStaysAbsent() {
        Message<OrderRequest> input = MessageBuilder
                .withPayload(new OrderRequest(
                        "O-502", 100_000L, "DIRECT"))
                .build();

        Function<Message<OrderRequest>, Message<OrderReceipt>> function =
                catalog.lookup("processOrder");
        Message<OrderReceipt> output = function.apply(input);

        assertNull(output.getHeaders().get(HeaderNames.CORRELATION_ID));
        assertEquals("O-502", output.getPayload().orderId());
    }
}
~~~

### 11.1. Kết quả cần quan sát

| Test | Payload | Header được kiểm tra |
| --- | --- | --- |
| `enrichesMetadataWithoutChangingPayload` | Giữ nguyên `OrderRequest` | `correlationId`, `sourceSystem`, `receivedBy`, `contentType` |
| `processOrderPreservesAllowedMetadataAndAddsProcessor` | `OrderRequest → OrderReceipt` | Giữ correlation/source; thêm `processedBy` |
| `compositionCarriesCorrelationAcrossStages` | `OrderRequest → OrderReceipt` | Metadata từ stage đầu tới stage sau |
| `fullCompositionUpdatesContentTypeWhenPayloadChanges` | `OrderRequest → String` | `correlationId` còn; `contentType` đổi sang text/plain |
| `missingOptionalCorrelationIdStaysAbsent` | Tạo biên nhận hợp lệ | Không tự tạo correlation ID giả |

Test qua `FunctionCatalog` quan trọng vì nó kiểm tra các bean đã được Spring nhận diện và chuỗi function được compose. Nếu chỉ gọi `new OrderMessageFunctions().processOrder()`, ta bỏ qua phần đăng ký bean và wrapper của catalog.

### 11.2. Tại sao không assert mọi header của input đều xuất hiện ở output?

Vì đây là chủ đích của allowlist. Message input trong test có `authorization` và routing header; output **không** được giữ hai header đó. Nếu assert mọi header đều bằng nhau, test sẽ khuyến khích sao chép metadata một cách không kiểm soát.

### 11.3. Tại sao content type phải đổi ở stage cuối?

`processOrder` trả `OrderReceipt`, vẫn là dữ liệu cấu trúc được serialize thành JSON. `formatReceipt` trả `String` văn bản thuần. Nếu stage cuối giữ `application/json`, adapter có thể diễn giải chuỗi như JSON body và gây lỗi hoặc kết quả không đúng hợp đồng.

Content type là **metadata của payload hiện tại**, không phải một giá trị bất biến cần copy nguyên vẹn từ message đầu tiên.

## 12. Hiểu các loại header quan trọng

### 12.1. correlationId và message ID

| Thuộc tính | `MessageHeaders.ID` | `correlationId` |
| --- | --- | --- |
| Ý nghĩa | Định danh một message cụ thể | Liên kết nhiều message/lần xử lý |
| Phạm vi | Thường thay đổi khi tạo message mới | Có thể giữ qua nhiều stage |
| Nguồn | Spring Messaging quản lý | Ứng dụng hoặc hệ thống upstream |
| Có nên dùng làm business key? | Không | Không thay thế order ID |
| Chính sách | Không cố ép giữ ID qua output | Giữ nếu có và được phép |

Một request có thể tạo nhiều message: input, validated event, receipt event. Mỗi message có ID riêng, nhưng cùng `correlationId` để log/tracing có thể liên kết chúng.

### 12.2. contentType

Spring Messaging dùng header `contentType` (hằng `MessageHeaders.CONTENT_TYPE`) để mô tả định dạng payload. Một số giá trị thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `application/json` | Payload JSON |
| `text/plain` | Văn bản thuần |
| `application/octet-stream` | Byte payload không có schema text cụ thể |
| `application/vnd.example.order+json` | JSON theo media type riêng của ứng dụng |

Khi đổi kiểu payload, hãy đánh giá content type mới. Đừng copy header cũ nếu nó không còn mô tả payload đầu ra.

### 12.3. sourceSystem và receivedBy

`sourceSystem` có thể cho biết message đến từ đối tác nào. Nhưng nếu producer tự đặt header, giá trị đó chỉ là **khai báo của producer** cho tới khi được xác thực/đối chiếu.

`receivedBy` và `processedBy` trong lab do server đặt để đánh dấu thành phần xử lý. Chúng là metadata quan sát, không phải bằng chứng bảo mật hoặc xác nhận giao dịch.

### 12.4. Header nội bộ và header nhạy cảm

Không nên chuyển tiếp tùy tiện:

- `authorization`, access token, cookie hoặc API key.
- Header định tuyến có thể khiến stage sau gọi function khác.
- Header binder/framework chỉ có ý nghĩa ở một adapter.
- Header debug chứa dữ liệu nội bộ.
- Dữ liệu cá nhân hoặc payload lớn được nhét vào header.

Allowlist trong `HeaderPolicy` giúp giảm rủi ro này. Tuy nhiên, nếu cần bảo mật thực sự, phải có authentication/authorization và chính sách xử lý secret ở tầng thích hợp.

## 13. Quy tắc truyền header qua các adapter

Kiểm thử catalog xác nhận **logic tạo message trong ứng dụng**. Khi đi qua HTTP hoặc broker, header còn phải được adapter ánh xạ từ/đến transport.

| Đường đi | Cần kiểm chứng |
| --- | --- |
| Java gọi trực tiếp function | Message và header có đúng kiểu trong memory |
| FunctionCatalog composition | Mỗi stage có giữ header theo allowlist |
| HTTP request → function | HTTP header nào được chuyển thành message header; content type/body |
| Function → HTTP response | Header nào được đưa ra HTTP response, header nào bị lọc |
| Spring Cloud Stream input | Binder có chuyển custom header và content type đúng |
| Spring Cloud Stream output | Header nào được serialize/transport; header nào bị loại |
| Serverless event | Event attribute/header có được adapter ánh xạ đúng không |

**Không có quy tắc phổ quát rằng mọi header luôn được truyền qua mọi adapter.** Broker có giới hạn kiểu dữ liệu và kích thước header; HTTP có quy tắc tên/header hop-by-hop; serverless có schema event riêng. Phải viết integration test ở đúng adapter/binder đang dùng.

### 13.1. Header qua Spring Cloud Stream

Khi triển khai một function nhận `Message<OrderRequest>` và trả `Message<OrderReceipt>`, binding có thể được cấu hình như sau (đây là ví dụ mở rộng; lab hiện chưa thêm binder):

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichMetadata|processOrder"
    stream:
      bindings:
        "enrichMetadata|processOrder-in-0":
          destination: orders.in
          group: order-processors
          content-type: application/json
        "enrichMetadata|processOrder-out-0":
          destination: orders.receipts
          content-type: application/json
~~~

Trong hệ thống thực, cần kiểm tra header mapping của binder. Một header trong Java message không đảm bảo broker lưu/khôi phục được cùng kiểu Java object. Ưu tiên giá trị header đơn giản, có thể biểu diễn trên transport như String, số hoặc kiểu được binder hỗ trợ.

Nếu cần giữ custom header, test gửi message vào input binding rồi đọc message output để xác nhận `correlationId` và `sourceSystem` còn nguyên. Đồng thời kiểm tra `authorization` và routing header không xuất hiện ngoài ý muốn.

### 13.2. Header qua HTTP

Với web adapter, HTTP request header có thể được ánh xạ vào message header, nhưng việc ánh xạ và response propagation cần kiểm tra theo adapter/version. Không nên mặc định mọi header request được echo lại trong response.

Một HTTP integration test nên gửi:

~~~http
POST /processOrder
Content-Type: application/json
X-Correlation-Id: corr-501
X-Source-System: partner-a
~~~

Adapter hoặc lớp chuyển đổi của ứng dụng cần map tên HTTP sang header nội bộ `correlationId`/`sourceSystem`. Test sau đó xác nhận output message/response giữ đúng metadata được phép. Lab test trực tiếp Spring `Message` nên **chưa** chứng minh mapping HTTP này.

### 13.3. Header qua serverless

Event từ Lambda, Azure Functions hoặc Google Cloud Functions có thể mang metadata trong event attributes, request context hoặc message attributes. Adapter chịu trách nhiệm ánh xạ chúng thành message headers hoặc input DTO. Cần test đúng loại event và adapter đã chọn; không giả định một HTTP header tùy ý tồn tại trên mọi event trigger.

## 14. Bổ sung header mới mà không phá hợp đồng cũ

Khi cần thêm `schemaVersion` hoặc `processingRegion`, đừng copy tất cả header. Hãy mở rộng allowlist và test:

~~~java
MessageBuilder<OrderReceipt> builder =
        HeaderPolicy.withAllowedHeaders(
                input,
                receipt,
                HeaderNames.CORRELATION_ID,
                HeaderNames.SOURCE_SYSTEM,
                "schemaVersion");

builder.setHeader("processingRegion", "ap-southeast-1");
~~~

Trước khi thêm, cần quyết định:

1. Header là metadata của **input**, hay do server tạo?
2. Có cần đi qua mọi stage không?
3. Có được gửi qua broker/HTTP không?
4. Có chứa thông tin nhạy cảm hoặc định danh cá nhân không?
5. Consumer cũ có thể bỏ qua header mới không?

Đối với version schema, có thể dùng content type/versioned schema hoặc một header version có hợp đồng rõ ràng. Không dựa vào header tùy ý để thay đổi class deserialize mà không kiểm soát allowlist và type metadata.

## 15. Xử lý header thiếu hoặc sai kiểu

Trong ví dụ, `correlationId` và `sourceSystem` là metadata tùy chọn. Nếu thiếu, helper không copy; pipeline vẫn xử lý payload. Nếu nghiệp vụ yêu cầu correlation ID bắt buộc, hãy kiểm tra riêng và từ chối message trước khi xử lý.

Ví dụ một validator:

~~~java
public static String requireCorrelationId(Message<?> message) {
    Object value = message.getHeaders().get(
            HeaderNames.CORRELATION_ID);

    if (!(value instanceof String correlationId)
            || correlationId.isBlank()) {
        throw new IllegalArgumentException(
                "correlationId header is required");
    }
    return correlationId;
}
~~~

Không ép kiểu trực tiếp:

~~~java
// Có thể ClassCastException nếu producer gửi header kiểu khác.
String id = (String) message.getHeaders().get("correlationId");
~~~

Kiểu header cần được xác minh trước khi sử dụng. Với metadata bắt buộc, lỗi nên được thể hiện rõ và adapter phải có chính sách từ chối/retry/quarantine phù hợp.

## 16. Bảo mật và tính đúng đắn của metadata

Header là dữ liệu đi cùng message, không tự động trở thành dữ liệu đáng tin cậy. Một producer có thể gửi:

~~~text
sourceSystem = "trusted-bank"
tenantId = "tenant-admin"
authorization = "Bearer fake"
~~~

Nếu ứng dụng dùng các giá trị này để quyết định quyền, sẽ tạo ra lỗ hổng. Các nguyên tắc:

- **Không dùng sourceSystem do producer tự khai làm bằng chứng xác thực.** Xác minh danh tính producer ở ingress.
- **Không tin tenantId header để phân quyền.** Dùng identity/tenant context đã được xác thực.
- **Không chuyển tiếp authorization/token** nếu output không có lý do bảo mật rõ ràng.
- **Không log toàn bộ headers** vì có thể chứa token, cookie hoặc dữ liệu cá nhân.
- Giới hạn số lượng, kích thước và kiểu header có thể nhận.
- Chỉ truyền metadata cần thiết cho stage tiếp theo.
- Dùng `correlationId` để quan sát/truy vết, không làm khóa cấp quyền.

Allowlist header là chính sách **truyền dữ liệu**. Nó không thay thế authentication, authorization, encryption hoặc kiểm soát quyền trên broker.

## 17. Chạy kiểm thử

Trong thư mục `message-metadata-lab`:

~~~bash
java -version
mvn -version
mvn test
~~~

Các nhóm test cần pass:

| Nhóm | Kết quả |
| --- | --- |
| `OrderPolicyTest` | Logic xử lý đơn đúng |
| `HeaderPolicyTest` | Copy header theo allowlist, MessageHeaders bất biến |
| `MessageMetadataCatalogTest` | Metadata đi qua function và composition đúng |

Nếu test catalog lỗi, kiểm tra package scan, tên bean và kiểu generic `Message<T>`. Nếu test adapter lỗi, kiểm tra riêng header mapping, content type và cấu hình transport.

## 18. Bài tập mở rộng

### Bài A — Bắt buộc correlationId

Sửa `enrichMetadata` để từ chối message thiếu `correlationId` hoặc có giá trị không phải String.

**Yêu cầu:**

- Viết test thiếu header.
- Viết test header rỗng.
- Viết test header là số.
- Chứng minh function không gọi `processOrder` khi metadata bắt buộc không hợp lệ.

### Bài B — Thêm schemaVersion

Producer gửi header `schemaVersion`. Hãy quyết định phiên bản hợp lệ, ví dụ `"1"` và `"2"`, rồi chỉ giữ header đó trong output.

**Yêu cầu:** test version hợp lệ, version không hỗ trợ và trường hợp header bị thiếu. Không dùng header này để tự tải class hoặc thực thi code.

### Bài C — Thêm metadata xử lý

Thêm `processedAt` (ISO-8601 UTC) và `processingRegion`. Dùng `Clock` được inject để test thời gian xác định, không dựa vào `Instant.now()` trong assertion.

**Yêu cầu:** chỉ server được tạo hai header này; producer gửi giá trị giả phải bị ghi đè hoặc loại bỏ theo policy.

### Bài D — Header allowlist theo từng stage

Tạo bảng cho ba stage:

| Stage | Header giữ | Header thêm | Header bỏ |
| --- | --- | --- | --- |
| `enrichMetadata` | correlationId, sourceSystem | receivedBy, contentType | authorization |
| `processOrder` | correlationId, sourceSystem, receivedBy | processedBy, contentType | authorization |
| `formatReceipt` | correlationId, receivedBy, processedBy | contentType=text/plain | sourceSystem nếu không cần |

**Yêu cầu:** hiện thực đúng bảng và test từng stage. Giải thích tại sao header có thể bị bỏ ở stage cuối.

### Bài E — Kiểm thử Spring Cloud Stream header mapping

Thêm Spring Cloud Stream Test Binder hoặc broker test phù hợp. Gửi message chứa `correlationId` và `sourceSystem` vào input binding, rồi đọc output binding.

**Yêu cầu:** kiểm tra header nào được giữ, kiểu dữ liệu sau transport, content type và việc loại bỏ `authorization`. Test catalog hiện tại không thay thế bài này.

### Bài F — Chuyển metadata từ HTTP header

Thêm web adapter. Map `X-Correlation-Id` sang `correlationId` và `X-Source-System` sang `sourceSystem` bằng adapter/controller/filter phù hợp.

**Yêu cầu:** gửi request HTTP, kiểm tra output header/response; thử thiếu header, header không hợp lệ và header nhạy cảm. Nêu rõ phần nào do web adapter tự làm và phần nào do ứng dụng chủ động map.

## 19. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Header không xuất hiện ở output | Stage tạo message mới nhưng không copy header | Dùng allowlist và test từng stage |
| Header cũ tồn tại nhưng sai content type | Copy toàn bộ header từ message trước | Đặt lại `MessageHeaders.CONTENT_TYPE` theo payload mới |
| `MessageHeaders.put` ném exception | Headers là cấu trúc bất biến | Tạo message mới bằng `MessageBuilder` |
| Header nhạy cảm xuất hiện ở output | Dùng `copyHeaders` không giới hạn | Dùng allowlist, loại token/cookie |
| `correlationId` bị mất ở stage thứ hai | Stage đó không giữ header trong allowlist | Kiểm tra policy của từng stage |
| `correlationId` thay đổi bất ngờ | Dùng message ID thay cho correlation ID hoặc adapter tạo metadata mới | Phân biệt ID message và ID luồng |
| Header có kiểu sai gây ClassCastException | Ép kiểu trước khi kiểm tra | Dùng `instanceof` và validation |
| Catalog test pass nhưng broker mất header | Binder/transport không map header như kỳ vọng | Viết integration test qua binder |
| HTTP request header không đến function | Adapter không map header tùy chỉnh hoặc tên khác nhau | Map rõ ràng và test HTTP thật |
| Payload JSON nhưng content type là text/plain | Header bị giữ từ stage cũ | Cập nhật content type tại stage đổi payload |
| Dùng sourceSystem để phân quyền | Tin header do producer tự khai | Dùng identity đã xác thực |
| Test lúc pass lúc fail | Shared state hoặc test chạy song song | Cô lập test data, không dùng mutable singleton tùy tiện |

### 19.1. Trình tự debug

1. Kiểm tra payload trước khi xử lý.
2. In/inspect **chỉ các header an toàn** tại input.
3. Kiểm tra danh sách header allowlist của stage đầu.
4. Kiểm tra output của stage đầu, đặc biệt correlation và content type.
5. Lặp lại ở từng stage trong composition.
6. Tra cứu và gọi pipeline qua `FunctionCatalog`.
7. Nếu lỗi chỉ xảy ra qua HTTP/broker, kiểm tra header mapping của adapter/binder.
8. Kiểm tra output không chứa token hoặc header routing ngoài ý muốn.

## 20. Tiêu chí hoàn thành

| Tiêu chí | Minh chứng |
| --- | --- |
| Phân biệt payload và headers | `OrderRequest` chứa dữ liệu đơn; `MessageHeaders` chứa metadata |
| Message immutable | Test sửa trực tiếp header bị từ chối |
| Có allowlist | `HeaderPolicy` chỉ copy tên được cho phép |
| Thêm metadata | `receivedBy` và `processedBy` do server tạo |
| Giữ correlation | `correlationId` đi qua composition |
| Cập nhật content type | JSON chuyển sang text/plain ở stage cuối |
| Loại header nhạy cảm | `authorization` không xuất hiện ở output |
| Catalog composition | `enrichMetadata|processOrder|formatReceipt` chạy đúng |
| Hiểu adapter boundary | Phân biệt test catalog với HTTP/binder integration test |
| Bảo mật metadata | Không tin header để xác thực hoặc phân quyền |

**Tóm tắt:** Payload mô tả dữ liệu nghiệp vụ; headers mô tả ngữ cảnh của message. Khi một function cần metadata, hãy nhận `Message<T>` và tạo message đầu ra bằng `MessageBuilder`. Chọn rõ header được giữ, header được tạo mới và header phải loại bỏ. Mỗi stage trong composition phải kiểm chứng hợp đồng metadata của chính nó; khi đi qua HTTP, broker hoặc serverless, cần test riêng cách adapter ánh xạ headers.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `OrderRequest` và `MessageHeaders` có vai trò gì khác nhau?

**Đáp án:** `OrderRequest` chứa payload nghiệp vụ như mã đơn và số tiền. `MessageHeaders` chứa metadata như correlation ID, content type và nguồn gửi.

**Câu 2.** Vì sao một hàm cần đọc header nên khai báo `Function<Message<OrderRequest>, ...>`?

**Đáp án:** Vì hàm nhận cả payload lẫn metadata. Chữ ký chỉ nhận `OrderRequest` không cung cấp message headers cho function.

**Câu 3.** Có nên dùng `MessageBuilder.copyHeaders(input.getHeaders())` ở mọi stage không?

**Đáp án:** Không mặc định. Nó có thể mang theo token, routing header hoặc content type cũ. Nên chọn header theo allowlist.

**Câu 4.** Vì sao `correlationId` cần được giữ nhưng `MessageHeaders.ID` không nhất thiết giữ nguyên?

**Đáp án:** Correlation ID liên kết nhiều message trong cùng luồng. Message ID nhận diện một message cụ thể và có thể được tạo mới khi tạo output message.

**Câu 5.** Khi payload đổi từ `OrderReceipt` sang `String`, header nào cần xem xét cập nhật?

**Đáp án:** `contentType` phải đổi sang dạng phù hợp, ví dụ `text/plain`; không giữ `application/json` nếu output không còn là JSON.

**Câu 6.** Vì sao không dùng `sourceSystem` hoặc `tenantId` do producer gửi để quyết định quyền?

**Đáp án:** Producer có thể tự khai báo hoặc giả mạo header. Phân quyền phải dựa trên identity đã xác thực ở tầng bảo mật.

**Câu 7.** Catalog test chứng minh `correlationId` đi qua function composition. Nó có chứng minh Kafka giữ header đó không?

**Đáp án:** Không. Cần test qua binder/broker thật hoặc Test Binder để xác minh header mapping và transport.

**Câu 8.** Nếu stage đầu copy header đúng nhưng stage thứ hai tạo message mới mà không copy, chuyện gì xảy ra?

**Đáp án:** Header không được giữ trong output của stage thứ hai. Quy tắc truyền metadata cần được thực hiện và kiểm thử ở từng stage.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, FunctionCatalog và Message](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — Message và MessageHeaders](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html)
- [Spring Framework — MessageBuilder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework — MessageHeaders API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Cloud Stream — Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream — User-defined Message Converters](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-user-defined-message-converters.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Function interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
