# Chuyển đổi JSON sang POJO hoặc Java record

Trong một luồng message, broker thường lưu hoặc truyền payload dưới dạng byte. Ứng dụng Java lại muốn làm việc với các kiểu dữ liệu có cấu trúc như `OrderCreated`, `Customer` hay `OrderLine`. Spring Cloud Stream kết hợp binder, thông tin kiểu của hàm và message converter để chuyển payload JSON thành đối tượng Java trước khi gọi hàm xử lý. Ở chiều ngược lại, đối tượng Java được chuyển thành JSON khi gửi message ra broker.

Quá trình này giúp code nghiệp vụ không phải tự đọc từng byte hoặc gọi `ObjectMapper` ở mọi consumer. Để chuyển đổi đúng, producer và consumer cần thống nhất hợp đồng JSON, kiểu dữ liệu đích và `content-type`. Trong module `SPRING_CLOUD_STREAM`, kiến thức này áp dụng cho mô hình hàm `Supplier`/`Function`/`Consumer` và các binder Kafka, RabbitMQ hoặc Pulsar.

Bài thuộc chương **Chuyển đổi dữ liệu**. Ta sẽ đi từ cấu trúc JSON đến POJO và Java record, cấu hình binding, xử lý trường lồng nhau, kiểm soát schema và chẩn đoán lỗi chuyển đổi.

## 1. Từ JSON trên broker đến đối tượng Java

Giả sử producer gửi sự kiện đơn hàng dưới dạng JSON:

```json
{
  "orderId": "ORD-2026-0042",
  "total": 1250000.50,
  "createdAt": "2026-11-24T08:30:00Z",
  "customer": {
    "customerId": "CUS-018",
    "name": "Nguyen An"
  },
  "items": [
    {
      "sku": "COFFEE-01",
      "quantity": 2,
      "unitPrice": 250000.25
    },
    {
      "sku": "TEA-03",
      "quantity": 3,
      "unitPrice": 250000.00
    }
  ]
}
```

Payload trên có các trường đơn giản (`orderId`, `total`), trường thời gian (`createdAt`), object lồng nhau (`customer`) và mảng object (`items`). Trong ứng dụng, ta muốn truy cập dữ liệu bằng phương thức Java có kiểu rõ ràng, chẳng hạn `event.customer().name()` hoặc `event.items().get(0).sku()`.

Luồng chuyển đổi tổng quát:

```text
Producer
  Java object
      |
      v
  Message converter (JSON)
      |
      v
  JSON bytes ----------------------> Broker
                                       |
                                       v
                                Binder nhận message
                                       |
                                       v
                                Content type + target type
                                       |
                                       v
                                JSON message converter
                                       |
                                       v
                                POJO / Java record
                                       |
                                       v
                                Function / Consumer
```

Các bước quan trọng ở phía nhận:

1. Binder nhận message từ topic, queue hoặc subscription và chuyển nó thành Spring `Message`.
2. Framework xác định kiểu nội dung, thường qua header `contentType` hoặc cấu hình `content-type` của binding.
3. Kiểu đầu vào của hàm cung cấp thông tin về kiểu Java mà ứng dụng mong muốn.
4. Message converter phù hợp đọc JSON và tạo đối tượng Java.
5. Spring Cloud Stream gọi hàm với payload đã chuyển đổi.

Ở chiều gửi, converter thực hiện quá trình ngược lại: lấy payload Java, serialize thành JSON theo content type rồi chuyển message cho binder gửi đến broker. Chi tiết converter và cấu hình có thể thay đổi theo phiên bản framework, nhưng nguyên tắc là content type mô tả định dạng payload còn kiểu tham số của hàm mô tả kiểu dữ liệu ứng dụng muốn nhận.

## 2. `content-type` cho biết payload là JSON

Spring Cloud Stream dùng content type để chọn cách chuyển đổi message. Với JSON, giá trị phổ biến là `application/json`. Có thể khai báo trên từng binding:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          content-type: application/json
```

Binding đầu vào `processOrder-in-0` đọc message từ destination `orders.created` và khai báo payload có định dạng JSON. Nếu hàm nhận `OrderCreated`, converter sẽ cố gắng tạo đối tượng kiểu đó từ JSON.

Với hàm có đầu ra, có thể khai báo content type cho binding output:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

`content-type` có thể được biểu diễn trong cấu hình YAML bằng dạng kebab-case; Spring Boot ánh xạ nó tới thuộc tính Java tương ứng. Trong một số luồng, message cũng có thể mang header `contentType`. Cần bảo đảm metadata gửi đi và cấu hình binding không mâu thuẫn, đặc biệt khi cùng destination phục vụ nhiều kiểu message.

Không nên suy ra rằng mọi payload đều là JSON chỉ vì file cấu hình có đuôi `.yml` hoặc vì producer đang dùng Java. Broker thường chỉ lưu bytes và metadata; producer/consumer phải thống nhất định dạng thực tế.

## 3. Ánh xạ JSON sang POJO

POJO (Plain Old Java Object) là lớp Java thông thường dùng để biểu diễn dữ liệu. Một DTO có thể có constructor mặc định, getter/setter và các trường tương ứng với thuộc tính JSON.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public class OrderCreated {

    private String orderId;
    private BigDecimal total;
    private Instant createdAt;
    private Customer customer;
    private List<OrderLine> items;

    public OrderCreated() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }

    public List<OrderLine> getItems() {
        return items;
    }

    public void setItems(List<OrderLine> items) {
        this.items = items;
    }
}
```

Các kiểu lồng nhau cũng cần có cấu trúc phù hợp:

```java
import java.math.BigDecimal;

class Customer {
    private String customerId;
    private String name;

    public Customer() {}

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}

class OrderLine {
    private String sku;
    private int quantity;
    private BigDecimal unitPrice;

    public OrderLine() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
```

Jackson thường được dùng để serialize và deserialize JSON trong ứng dụng Spring. Với POJO, converter dựa trên constructor và thuộc tính Java mà Jackson nhận diện được. Getter/setter, constructor và tên thuộc tính phải tương thích với cách cấu hình mapper. Không cần tự tạo `ObjectMapper` trong từng consumer nếu converter của framework đã xử lý payload.

## 4. Ánh xạ JSON sang Java record

Java record là lựa chọn gọn cho DTO bất biến. Record khai báo các thành phần dữ liệu ngay trong phần header; compiler tạo constructor canonical, accessor và các phương thức `equals`, `hashCode`, `toString`.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant createdAt,
    Customer customer,
    List<OrderLine> items
) {}

public record Customer(
    String customerId,
    String name
) {}

public record OrderLine(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
```

Với Jackson được Spring Boot cấu hình tương thích, JSON có thể được ánh xạ vào record theo tên thành phần. Ví dụ, trường JSON `orderId` được truyền vào thành phần `orderId`; object `customer` được chuyển thành record `Customer`; mỗi phần tử trong `items` thành một `OrderLine`.

Record phù hợp với message DTO vì dữ liệu thường được tạo một lần khi deserialize và không cần setter để thay đổi từng trường. Nếu cần biến đổi, có thể tạo record mới với giá trị đã cập nhật. Record cũng làm rõ hợp đồng đầu vào của hàm và giúp compiler kiểm tra kiểu dữ liệu.

Các điểm cần chú ý:

- Tên JSON phải khớp với tên thành phần record hoặc có annotation ánh xạ tương ứng.
- Trường bắt buộc, nullable và giá trị mặc định cần được quy định rõ trong hợp đồng.
- Kiểu primitive như `int` không thể biểu diễn `null`; nếu trường có thể vắng mặt, cân nhắc kiểu wrapper như `Integer` và kiểm tra nghiệp vụ.
- Record không tự kiểm tra dữ liệu hợp lệ. Sau khi deserialize, ứng dụng vẫn cần validation cho mã đơn, số lượng, giá trị tiền và các quy tắc nghiệp vụ.
- Record yêu cầu Java 16 trở lên trong dạng chuẩn; kiểm tra phiên bản Java của ứng dụng trước khi dùng.

## 5. Dùng POJO hoặc record trong hàm Spring Cloud Stream

Khi kiểu đầu vào được khai báo cụ thể, framework có thể chuyển payload thành kiểu đó trước khi gọi hàm. Ví dụ consumer nhận record:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConsumers {

    @Bean
    Consumer<OrderCreated> processOrder() {
        return event -> {
            System.out.println("Order: " + event.orderId());
            System.out.println("Customer: " + event.customer().name());
            System.out.println("Item count: " + event.items().size());
        };
    }
}
```

Binding đầu vào mặc định của hàm là `processOrder-in-0`. Cấu hình:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          content-type: application/json
```

Consumer nhận `OrderCreated`, không phải chuỗi JSON. Việc deserialize được thực hiện ở ranh giới message trước khi hàm nghiệp vụ chạy. Nếu JSON không thể ánh xạ vào record, lỗi chuyển đổi xảy ra trước khi code bên trong lambda được thực thi.

Nếu muốn đọc cả payload và headers, dùng `Message<T>`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderCreated>> processOrderMessage() {
    return message -> {
        OrderCreated order = message.getPayload();
        String correlationId = message.getHeaders()
            .get("correlationId", String.class);

        System.out.printf("Order %s, correlation %s%n",
            order.orderId(), correlationId);
    };
}
```

`Message<T>` giữ ranh giới rõ ràng: `getPayload()` trả về đối tượng nghiệp vụ đã chuyển đổi, còn `getHeaders()` chứa metadata vận chuyển hoặc truy vết. Không nên nhét correlation ID, trace ID hoặc thông tin định tuyến vào payload nếu chúng chỉ là metadata của message.

## 6. Serialize đối tượng Java thành JSON ở đầu ra

Ở chiều gửi, một `Function` có thể nhận DTO rồi tạo DTO khác. Spring Cloud Stream serialize kết quả theo content type của binding đầu ra:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;

record OrderAccepted(String orderId, String status) {}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
```

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-acceptance
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Hàm trả về `OrderAccepted`; converter serialize record thành JSON và binder gửi tới destination `orders.accepted`. Consumer ở phía sau có thể khai báo `OrderAccepted` làm kiểu đầu vào để deserialize. Nhờ vậy, các hàm nghiệp vụ làm việc với kiểu Java thay vì tự ghép chuỗi JSON.

## 7. Ánh xạ tên trường và cấu trúc JSON

Trong thực tế, tên trường JSON không phải lúc nào cũng giống tên Java. Ví dụ API bên ngoài gửi `customer_id` trong khi Java dùng `customerId`. Có thể dùng annotation Jackson để khai báo ánh xạ:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record Customer(
    @JsonProperty("customer_id") String customerId,
    String name
) {}
```

Khi JSON có:

```json
{
  "customer_id": "CUS-018",
  "name": "Nguyen An"
}
```

Jackson ánh xạ `customer_id` vào thành phần `customerId`. Annotation cũng có thể dùng với POJO. Nếu toàn hệ thống có quy tắc snake_case, có thể cấu hình naming strategy tập trung cho `ObjectMapper`; hãy thống nhất cách cấu hình ở producer và consumer, tránh dùng annotation và global strategy theo cách mâu thuẫn.

Các object và array lồng nhau cần có kiểu Java tương ứng. Ví dụ `List<OrderLine>` giúp converter biết mỗi phần tử của mảng `items` cần được tạo thành `OrderLine`. Nếu khai báo kiểu thô như `List` hoặc `Map` không tham số, ứng dụng có thể mất thông tin kiểu phần tử và phải ép kiểu khi sử dụng.

## 8. Kiểu số, ngày giờ và enum

Chọn kiểu Java phù hợp với ý nghĩa của dữ liệu:

| JSON | Kiểu Java thường dùng | Lưu ý |
|---|---|---|
| Chuỗi mã định danh | `String` hoặc `UUID` | UUID cần đúng định dạng; mã có số 0 ở đầu nên giữ dạng chuỗi |
| Số tiền | `BigDecimal` | Tránh dùng `double` cho phép tính tiền cần độ chính xác thập phân |
| Số lượng | `int` hoặc `Integer` | Dùng wrapper nếu cần phân biệt thiếu trường với giá trị 0 |
| Thời điểm tuyệt đối | `Instant` | JSON nên dùng chuỗi ISO-8601 có offset hoặc `Z` |
| Ngày nghiệp vụ | `LocalDate` | Chỉ dùng khi dữ liệu là ngày, không đại diện thời điểm |
| Trạng thái cố định | `enum` | Cần quy định cách xử lý giá trị enum mới hoặc không nhận diện |

Ví dụ payload:

```json
{
  "orderId": "ORD-42",
  "total": 1250000.50,
  "createdAt": "2026-11-24T08:30:00Z",
  "deliveryDate": "2026-11-27",
  "status": "PENDING"
}
```

Record tương ứng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

public record OrderSnapshot(
    String orderId,
    BigDecimal total,
    Instant createdAt,
    LocalDate deliveryDate,
    OrderStatus status
) {}

enum OrderStatus {
    PENDING,
    ACCEPTED,
    CANCELLED
}
```

Spring Boot thường tự cấu hình Jackson hỗ trợ các kiểu ngày giờ Java khi dependency tương ứng có mặt. Dù vậy, format ngày giờ vẫn phải thống nhất. Nếu producer gửi timestamp dạng số epoch nhưng consumer mong chuỗi ISO-8601, conversion có thể thất bại hoặc tạo giá trị không như mong đợi. Hãy ghi rõ format trong hợp đồng và kiểm thử bằng payload thực.

## 9. Trường thiếu, trường thừa và schema evolution

Producer và consumer có thể được triển khai ở những thời điểm khác nhau. Producer phiên bản mới có thể thêm trường JSON; consumer cũ có thể chưa biết trường đó. Ngược lại, consumer mới có thể mong đợi một trường mà producer cũ chưa gửi.

Các trường hợp cần xem xét:

| Thay đổi JSON | Rủi ro | Cách thiết kế |
|---|---|---|
| Thêm trường tùy chọn | Consumer cũ có thể từ chối trường không biết, tùy cấu hình mapper | Quy định chính sách unknown property; có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)` khi phù hợp |
| Thêm trường bắt buộc | Consumer mới không nhận được giá trị từ producer cũ | Dùng giá trị mặc định hợp lệ, nullable có kiểm soát hoặc version schema mới |
| Đổi tên trường | Consumer cũ không tìm thấy tên cũ | Duy trì alias/compatibility trong giai đoạn chuyển đổi |
| Đổi kiểu dữ liệu | Deserialize có thể lỗi hoặc mất thông tin | Tránh đổi kiểu trực tiếp; phát hành trường mới hoặc phiên bản hợp đồng mới |
| Xóa trường | Consumer cũ có thể còn phụ thuộc | Ngừng sử dụng trước, theo dõi consumer rồi mới loại bỏ |

Để bỏ qua trường JSON chưa biết trong một DTO cụ thể, có thể dùng:

```java
import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreated(
    String orderId,
    BigDecimal total
) {}
```

Chính sách này hữu ích khi consumer chỉ cần một phần hợp đồng và có thể an toàn bỏ qua trường mới. Tuy nhiên, không nên bật bỏ qua mọi trường một cách máy móc. Nếu trường mới chứa dữ liệu thiết yếu cho nghiệp vụ, bỏ qua nó có thể làm hệ thống xử lý sai mà không báo lỗi.

Trường thiếu có thể trở thành `null`, giá trị mặc định của kiểu primitive hoặc gây lỗi tùy constructor, kiểu Java và cấu hình Jackson. Vì vậy, hãy kiểm tra các trường bắt buộc sau deserialize. Có thể dùng Jakarta Bean Validation với `@NotBlank`, `@NotNull`, `@Positive` và gọi validator ở tầng ứng dụng, nhưng validation nghiệp vụ cần được đặt tại nơi phù hợp với luồng xử lý.

## 10. DTO message nên tách khỏi entity lưu trữ

Không nên mặc định dùng entity JPA làm payload message. Entity có thể chứa quan hệ lazy, trường nội bộ, annotation persistence hoặc dữ liệu nhạy cảm không nên truyền qua broker. Một DTO riêng giúp kiểm soát hợp đồng JSON:

```java
public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant createdAt
) {}
```

Trong service, chuyển entity sang DTO trước khi trả về output binding. Cách này giảm phụ thuộc giữa schema database và schema message, tránh serialize proxy/lazy relationship và hạn chế lộ dữ liệu nội bộ. DTO cũng cho phép giữ tương thích khi cấu trúc entity thay đổi.

## 11. Lỗi chuyển đổi thường gặp

Lỗi deserialize thường xuất hiện trước khi hàm nghiệp vụ được gọi. Một số tình huống phổ biến:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không chuyển được JSON thành record | Tên trường không khớp, kiểu dữ liệu sai hoặc constructor không nhận được giá trị cần thiết | Kiểm tra JSON, record component và annotation |
| `Cannot deserialize value` | JSON gửi chuỗi nhưng Java mong số, object hoặc enum | Sửa hợp đồng hoặc định nghĩa converter phù hợp |
| Lỗi ngày giờ | Format timestamp không đúng hoặc thiếu hỗ trợ kiểu thời gian | Chuẩn hóa ISO-8601 và kiểm tra Jackson Java Time support |
| Lỗi do trường mới | Consumer từ chối unknown property | Thống nhất schema evolution và chính sách unknown fields |
| Giá trị bị `null` | Producer không gửi trường, tên trường khác hoặc trường bị loại khi serialize | Kiểm tra payload thực và validation sau conversion |
| Consumer nhận `String` thay vì DTO | Kiểu hàm khai báo `String`, content type hoặc converter không phù hợp | Kiểm tra function signature, content type và headers |
| Output không phải JSON như mong muốn | Binding output thiếu content type phù hợp hoặc payload đã là chuỗi JSON | Kiểm tra kiểu payload và converter để tránh serialize hai lần |

Khi chẩn đoán, hãy kiểm tra message gốc, content type, target type của hàm và exception của converter. Không chỉ xem log trong lambda, vì lỗi có thể xảy ra trước khi lambda được gọi.

## 12. Không parse JSON thủ công nếu converter đã làm việc

Một cách dễ mắc lỗi là khai báo consumer nhận `String`, sau đó gọi `ObjectMapper.readValue` ở từng hàm:

```java
// Chỉ nên dùng khi ứng dụng thực sự cần nhận raw JSON string.
Consumer<String> processRawJson = json -> {
    // Tự parse JSON ở đây
};
```

Nếu payload đã là JSON và hàm biết kiểu đích, nên khai báo trực tiếp `Consumer<OrderCreated>` hoặc `Function<OrderCreated, Result>`. Framework có thể chuyển đổi payload ở ranh giới binding, giúp code ngắn hơn và kiểu dữ liệu rõ hơn.

Parse thủ công vẫn có chỗ dùng: ứng dụng cần kiểm tra raw payload trước khi chọn schema, xử lý nhiều cấu trúc JSON khác nhau trên cùng một destination hoặc dùng một converter đặc thù. Trong trường hợp đó, cần quản lý lỗi parse, encoding, schema version và bảo mật dữ liệu rõ ràng.

Tránh serialize JSON hai lần. Nếu đã có chuỗi JSON rồi lại gửi chuỗi đó như một payload JSON, converter có thể tạo JSON string chứa escaped JSON thay vì object JSON mong muốn. Hãy quyết định payload là object Java hay raw JSON string và cấu hình content type tương ứng.

## 13. Kiểm thử chuyển đổi JSON

Nên kiểm thử ít nhất ba lớp:

1. **Kiểm thử DTO:** xác nhận JSON mẫu chuyển thành POJO/record với đúng giá trị, kiểu số, ngày giờ, object lồng nhau và danh sách.
2. **Kiểm thử function:** xác nhận hàm nghiệp vụ nhận đúng kiểu Java và tạo output đúng.
3. **Kiểm thử binding tích hợp:** xác nhận binder, content type, destination và message converter phối hợp đúng với broker hoặc binder test.

Ví dụ kiểm thử Jackson cho record:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderCreatedJsonTest {

    private final ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

    @Test
    void readsOrderJsonIntoRecord() throws Exception {
        String json = """
            {
              "orderId": "ORD-42",
              "total": 1250.50,
              "createdAt": "2026-11-24T08:30:00Z",
              "customer": {
                "customerId": "CUS-018",
                "name": "Nguyen An"
              },
              "items": []
            }
            """;

        OrderCreated order = objectMapper.readValue(json, OrderCreated.class);

        assertEquals("ORD-42", order.orderId());
        assertEquals("CUS-018", order.customer().customerId());
        assertEquals(new BigDecimal("1250.50"), order.total());
    }
}
```

Ví dụ trên kiểm tra Jackson trực tiếp, không thay thế integration test Spring Cloud Stream. Integration test cần gửi message có `content-type: application/json` vào binding và xác nhận function nhận được DTO đúng. Cũng nên kiểm tra payload sai định dạng, thiếu trường bắt buộc, trường thừa, enum lạ và timestamp không hợp lệ.

## 14. Quy trình triển khai hợp đồng JSON

Khi tạo một luồng JSON giữa các dịch vụ:

1. Thiết kế schema message với tên trường, kiểu dữ liệu, trường bắt buộc và format ngày giờ rõ ràng.
2. Tạo POJO hoặc Java record đại diện cho payload; dùng DTO riêng cho hợp đồng truyền tin.
3. Khai báo kiểu đầu vào/đầu ra cụ thể trong `Supplier`, `Function` hoặc `Consumer`.
4. Cấu hình `content-type: application/json` cho binding phù hợp.
5. Xác nhận producer serialize đúng và consumer deserialize được bằng payload mẫu.
6. Quy định cách xử lý trường thiếu, trường thừa, giá trị null và phiên bản schema.
7. Validate dữ liệu sau conversion trước khi thực hiện nghiệp vụ.
8. Kiểm thử binding với binder hoặc broker thực tế, bao gồm cả payload lỗi.
9. Theo dõi lỗi conversion, DLQ và thay đổi schema trong quá trình triển khai.

## 15. Tự kiểm tra

- [ ] Giải thích được vai trò của `content-type` trong lựa chọn message converter.
- [ ] Mô tả được cách JSON được chuyển thành POJO hoặc Java record trước khi gọi hàm.
- [ ] Viết được record có object lồng nhau và `List` phần tử.
- [ ] Phân biệt payload Java đã chuyển đổi với raw JSON string và message headers.
- [ ] Chọn được `BigDecimal`, `Instant`, `LocalDate` và kiểu wrapper phù hợp.
- [ ] Biết dùng annotation Jackson để ánh xạ tên trường JSON.
- [ ] Phân tích được tác động của trường thiếu, trường thừa và thay đổi schema.
- [ ] Thiết kế được kiểm thử DTO, function và binding tích hợp.

## Kết luận

Spring Cloud Stream dùng content type, kiểu đầu vào/đầu ra của hàm và message converter để chuyển JSON thành POJO hoặc Java record trước khi thực thi logic nghiệp vụ. POJO phù hợp khi cần cấu trúc có thể thay đổi; record phù hợp với DTO bất biến và hợp đồng kiểu rõ ràng. Để luồng message ổn định, producer và consumer phải thống nhất tên trường, kiểu dữ liệu, format ngày giờ và chính sách schema evolution. Hãy kiểm thử payload thực ở cả mức Jackson lẫn binding, đồng thời xử lý rõ dữ liệu thiếu, thừa hoặc không hợp lệ.
