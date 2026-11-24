# Tùy biến PartitionKeyExtractorStrategy và PartitionSelectorStrategy

Spring Cloud Stream hỗ trợ phân vùng message để các sự kiện có cùng đặc điểm được xử lý bởi cùng một partition. Điều này hữu ích khi hệ thống cần giữ thứ tự tương đối theo một thực thể nghiệp vụ, chia tải giữa nhiều instance hoặc duy trì trạng thái cục bộ cho từng nhóm dữ liệu.

Hai strategy đảm nhiệm hai bước khác nhau trong quá trình gửi message. PartitionKeyExtractorStrategy đọc Spring Message và trích xuất khóa phân vùng; PartitionSelectorStrategy nhận khóa đó cùng số lượng partition rồi quyết định chỉ số partition đích. Khi biểu thức SpEL không đủ để mô tả quy tắc nghiệp vụ, bạn có thể triển khai hai interface này thành bean và chọn bean bằng tên trong cấu hình output binding.

Bài học trình bày cách thiết kế khóa ổn định, cài đặt hai strategy, cấu hình producer và consumer, cùng các lưu ý khi dùng Kafka, RabbitMQ hoặc Pulsar.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt nhiệm vụ trích xuất partition key và chọn partition.
- Cài đặt PartitionKeyExtractorStrategy và PartitionSelectorStrategy bằng Java.
- Đăng ký strategy thành Spring bean và chọn bean qua partitionKeyExtractorName, partitionSelectorName.
- Cấu hình partitionCount trên output binding và partitioned trên input binding khi cần.
- Thiết kế khóa để các sự kiện cùng một thực thể được gửi đến cùng partition.
- Hiểu sự khác nhau giữa phân vùng ở Kafka, RabbitMQ và Pulsar.
- Kiểm thử tính ổn định, miền chỉ số và phân phối của partition selector.
- Nhận biết tác động khi thay đổi số partition hoặc thuật toán chọn partition.

## 1. Hai bước trong quá trình phân vùng

Khi producer gửi một message qua output binding có bật partitioning, Spring Cloud Stream cần xác định message thuộc partition nào. Quá trình này có hai bước:

1. **Trích xuất khóa:** lấy thông tin từ message để tạo một giá trị đại diện cho nhóm dữ liệu cần được xử lý cùng nhau.
2. **Chọn partition:** chuyển khóa thành chỉ số partition nằm trong phạm vi từ 0 đến partitionCount - 1.

~~~mermaid
flowchart LR
    A["Spring Message<br/>payload + headers"] --> B["PartitionKeyExtractorStrategy"]
    B --> C["Partition key"]
    C --> D["PartitionSelectorStrategy"]
    D --> E["Partition index"]
    E --> F["Binder"]
    F --> G["Broker partition / queue"]
~~~

Ví dụ, hệ thống xử lý đơn hàng cần tất cả sự kiện của cùng một đơn hàng đi đến cùng partition. Extractor có thể lấy tenantId và orderId từ payload để tạo khóa kết hợp. Selector chuyển khóa đó thành một chỉ số trong số partition đã cấu hình.

Hai interface có hợp đồng:

~~~java
public interface PartitionKeyExtractorStrategy {
    Object extractKey(Message<?> message);
}

public interface PartitionSelectorStrategy {
    int selectPartition(Object key, int partitionCount);
}
~~~

PartitionKeyExtractorStrategy nhận toàn bộ Spring Message nên có thể đọc payload hoặc headers. PartitionSelectorStrategy không nhận message; nó chỉ nhận khóa đã trích xuất và số partition. Việc tách hai bước giúp thay đổi cách lấy khóa mà không phải viết lại thuật toán phân phối, hoặc thay thuật toán phân phối mà không thay đổi hợp đồng dữ liệu của message.

## 2. Khi nào cần tùy biến strategy?

Spring Cloud Stream hỗ trợ cấu hình đơn giản bằng biểu thức:

- partitionKeyExpression trích xuất khóa từ message bằng SpEL.
- partitionSelectorExpression tính chỉ số partition từ khóa.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          producer:
            partitionKeyExpression: payload.orderId
            partitionSelectorExpression: 'T(java.lang.Math).floorMod(#root.hashCode(), 6)'
            partitionCount: 6
~~~

Với một khóa đơn giản như orderId, biểu thức thường đủ dùng. Tuy nhiên, logic thực tế có thể phức tạp hơn:

- Khóa được tạo từ nhiều trường, chẳng hạn tenantId kết hợp orderId.
- Message có nhiều dạng payload và mỗi dạng dùng một trường khóa khác nhau.
- Khóa nằm trong header nếu message được tạo bởi một bước xử lý trước đó.
- Cần chuẩn hóa khóa trước khi băm, ví dụ loại bỏ khoảng trắng hoặc chuẩn hóa mã định danh.
- Cần dùng thuật toán phân phối tùy chỉnh để đáp ứng quy tắc nghiệp vụ hoặc tương thích với hệ thống hiện hữu.

Khi biểu thức trở nên khó đọc, khó kiểm thử hoặc cần tái sử dụng, hãy triển khai hai strategy thành bean.

## 3. PartitionKeyExtractorStrategy: trích xuất khóa

PartitionKeyExtractorStrategy nhận Message<?> và trả về một Object làm partition key. Giá trị trả về cần ổn định, không null và có thể được selector xử lý nhất quán.

Ví dụ message sự kiện đơn hàng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String tenantId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Ta muốn mọi sự kiện của một đơn hàng trong cùng tenant đi vào một partition. Có thể định nghĩa khóa kết hợp:

~~~java
public record OrderPartitionKey(
    String tenantId,
    String orderId
) {}
~~~

Cài đặt extractor:

~~~java
import org.springframework.cloud.stream.binder.PartitionKeyExtractorStrategy;
import org.springframework.messaging.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartitionStrategyConfiguration {

    @Bean
    PartitionKeyExtractorStrategy orderPartitionKeyExtractor() {
        return message -> {
            if (!(message.getPayload() instanceof OrderCreated event)) {
                throw new IllegalArgumentException(
                    "Payload phải là OrderCreated"
                );
            }

            if (event.tenantId() == null || event.tenantId().isBlank()
                    || event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException(
                    "tenantId và orderId là bắt buộc để phân vùng"
                );
            }

            return new OrderPartitionKey(
                event.tenantId(),
                event.orderId()
            );
        };
    }
}
~~~

Extractor đọc payload, kiểm tra kiểu dữ liệu và xác thực các trường cần thiết trước khi tạo khóa. Nếu message không có khóa hợp lệ, ví dụ ném exception giúp lỗi xuất hiện rõ tại producer thay vì âm thầm phân phối message theo một giá trị fallback không nhất quán.

### Có thể trích xuất khóa từ header

Nếu producer trước đó đã đặt partition key trong header, extractor có thể đọc header:

~~~java
@Bean
PartitionKeyExtractorStrategy headerPartitionKeyExtractor() {
    return message -> {
        Object key = message.getHeaders().get("partitionKey");

        if (key == null || key.toString().isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu header partitionKey"
            );
        }

        return key.toString();
    };
}
~~~

Cách này hữu ích khi nhiều loại payload cùng tuân theo một hợp đồng header. Tuy nhiên, header phải được đặt và kiểm soát bởi producer đáng tin cậy. Nếu message đến từ bên ngoài, cần xác thực giá trị header và không sử dụng metadata chưa được kiểm tra làm căn cứ phân vùng nghiệp vụ.

### Nguyên tắc thiết kế partition key

Một partition key tốt cần đáp ứng:

- **Ổn định:** cùng một thực thể phải tạo ra cùng khóa qua các lần gửi.
- **Có ý nghĩa:** khóa phản ánh thực thể cần giữ thứ tự hoặc trạng thái, ví dụ orderId, accountId hoặc deviceId.
- **Không null:** message thiếu trường khóa cần được xử lý theo chính sách rõ ràng.
- **Phân phối hợp lý:** khóa không nên khiến phần lớn message dồn vào một partition.
- **Nhất quán giữa producer:** mọi instance producer phải dùng cùng quy tắc chuẩn hóa và tạo khóa.

Không nên đưa thời điểm hiện tại, số ngẫu nhiên hoặc ID sinh riêng cho mỗi lần gửi vào partition key nếu mục tiêu là gom sự kiện của cùng một thực thể. Những giá trị đó làm các message liên quan bị phân tán sang nhiều partition.

## 4. PartitionSelectorStrategy: chọn chỉ số partition

PartitionSelectorStrategy nhận khóa đã trích xuất và số lượng partition. Nó phải trả về một chỉ số hợp lệ trong khoảng từ 0 đến partitionCount - 1.

Với khóa OrderPartitionKey, ta có thể tạo chuỗi kết hợp tenantId và orderId, sau đó dùng hash để phân phối:

~~~java
import org.springframework.cloud.stream.binder.PartitionSelectorStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartitionSelectorConfiguration {

    @Bean
    PartitionSelectorStrategy tenantAwarePartitionSelector() {
        return (key, partitionCount) -> {
            if (partitionCount < 1) {
                throw new IllegalArgumentException(
                    "partitionCount phải lớn hơn 0"
                );
            }

            if (!(key instanceof OrderPartitionKey orderKey)) {
                throw new IllegalArgumentException(
                    "Partition key phải là OrderPartitionKey"
                );
            }

            String stableKey =
                orderKey.tenantId() + ":" + orderKey.orderId();

            return Math.floorMod(stableKey.hashCode(), partitionCount);
        };
    }
}
~~~

Math.floorMod giúp kết quả luôn không âm ngay cả khi hashCode trả về số âm. Selector cần trả về một chỉ số hợp lệ; không trả về partitionCount, số âm hoặc một giá trị phụ thuộc trạng thái cục bộ của instance.

### Phân biệt selector mặc định và selector tùy chỉnh

Nếu không cấu hình selector tùy chỉnh, Spring Cloud Stream thường dùng phép tính dựa trên hashCode của khóa modulo partitionCount. Strategy tùy chỉnh cho phép thay đổi cách phân phối, nhưng cần giữ kết quả xác định.

Ví dụ với partitionCount = 6:

| Khóa | Chỉ số minh họa |
|---|---:|
| tenant-a:order-100 | 2 |
| tenant-a:order-101 | 3 |
| tenant-b:order-100 | 5 |
| tenant-a:order-100 (gửi lại) | 2 |

Bảng chỉ minh họa nguyên tắc; chỉ số thực tế phụ thuộc hash của chuỗi và partitionCount. Điều quan trọng là cùng khóa, cùng thuật toán và cùng partitionCount phải cho cùng chỉ số trên mọi producer instance.

### Không nên dùng thuật toán không ổn định

Tránh các cách chọn partition dựa trên:

- Random hoặc round-robin nếu cần giữ thứ tự theo khóa.
- Thời gian hiện tại hoặc biến đếm chỉ tồn tại trong một instance.
- Identity hash hoặc thông tin bộ nhớ của object.
- Cấu hình cục bộ khác nhau giữa các producer instance.

Nếu producer A chọn partition 1 cho order-100 nhưng producer B chọn partition 4 cho cùng order-100, các sự kiện của đơn hàng có thể được xử lý song song và sai thứ tự.

## 5. Đăng ký và chọn bean trong Spring Cloud Stream

Cả hai strategy cần được đăng ký như Spring bean. Tên mặc định của bean là tên phương thức @Bean, trong ví dụ:

- orderPartitionKeyExtractor
- tenantAwarePartitionSelector

Cấu hình output binding sử dụng hai tên này:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders
          producer:
            partitionCount: 6
            partitionKeyExtractorName: orderPartitionKeyExtractor
            partitionSelectorName: tenantAwarePartitionSelector
~~~

Các thuộc tính có ý nghĩa:

| Thuộc tính | Vai trò |
|---|---|
| partitionCount | Số partition mục tiêu mà producer dùng để tính chỉ số |
| partitionKeyExtractorName | Tên bean triển khai PartitionKeyExtractorStrategy |
| partitionSelectorName | Tên bean triển khai PartitionSelectorStrategy |

Các thuộc tính này nằm dưới producer của output binding. Tên binding phải khớp với tên output thực tế của Supplier hoặc Function đang phát message.

Nếu Application Context chỉ có một bean của mỗi strategy type, framework có thể tự tìm bean phù hợp. Khi có nhiều bean cùng loại, hãy chỉ định rõ tên để tránh chọn nhầm. Tên trong cấu hình phải khớp chính xác tên bean đã đăng ký.

### Hai cặp thuộc tính loại trừ lẫn nhau

Với nguồn trích xuất khóa, chỉ chọn một trong hai:

- partitionKeyExpression
- partitionKeyExtractorName

Với thuật toán chọn partition, chỉ chọn một trong hai:

- partitionSelectorExpression
- partitionSelectorName

Không cấu hình đồng thời hai cách trong cùng một cặp. Nếu đã dùng custom extractor, không thêm partitionKeyExpression cho cùng output binding. Nếu đã dùng custom selector, không thêm partitionSelectorExpression.

Thuộc tính cũ partitionKeyExtractorClass và partitionSelectorClass đã bị loại bỏ trong các phiên bản Spring Cloud Stream hiện hành. Hãy dùng tên bean với partitionKeyExtractorName và partitionSelectorName; không sao chép cấu hình class cũ từ tài liệu phiên bản trước.

## 6. Cấu hình producer và consumer đầu cuối

Partitioning cần được cấu hình ở cả phía phát và phía nhận. Producer quyết định chỉ số partition; consumer phải được tổ chức để đọc đúng các partition tương ứng.

Ví dụ output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders
          producer:
            partitionCount: 6
            partitionKeyExtractorName: orderPartitionKeyExtractor
            partitionSelectorName: tenantAwarePartitionSelector
~~~

Đối với input binding, cấu hình partitioned cùng instanceCount và instanceIndex khi binder cần cơ chế gán partition theo instance:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      instanceCount: 3
      instanceIndex: 0
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          consumer:
            partitioned: true
~~~

instanceCount là tổng số instance tham gia xử lý phân vùng. instanceIndex là chỉ số duy nhất của từng instance, nằm trong khoảng từ 0 đến instanceCount - 1. Ví dụ trên biểu diễn instance đầu tiên trong cụm ba instance. Khi triển khai ba replica, mỗi replica phải nhận instanceIndex khác nhau: 0, 1 và 2; không dùng cùng một giá trị cho tất cả replica.

Cách dùng instanceIndex và instanceCount phụ thuộc binder. Với Kafka binder, autoRebalanceEnabled mặc định là true nên Kafka tự phân phối partition trong consumer group; hai thuộc tính instance này thường không cần thiết cho cơ chế rebalance mặc định. Nếu tắt autoRebalanceEnabled và giao việc gán partition cho binder, cần cấu hình hai thuộc tính này và bảo đảm có đủ partition cho số instance. Với RabbitMQ, binder dùng queue riêng cho từng partition và instance index tham gia xác định queue mà instance đọc.

Không dùng một giá trị instanceIndex cố định trong file cấu hình chung cho mọi replica. Hãy cấp giá trị theo từng instance từ nền tảng triển khai hoặc cơ chế quản lý cấu hình của ứng dụng.

## 7. Tác động của partitionCount

partitionCount là số lượng partition mà selector dùng để tính chỉ số. Giá trị phải lớn hơn 1 để kích hoạt partitioning ở output binding.

Số partition ảnh hưởng tới:

- Mức song song tối đa của consumer group.
- Khả năng phân phối tải giữa các instance.
- Số lượng queue hoặc partition mà broker cần quản lý.
- Mức độ phân tán của khóa.
- Thứ tự xử lý và trạng thái cục bộ của ứng dụng.

Không nên tăng partitionCount tùy tiện. Với thuật toán hash modulo, khi số partition thay đổi, nhiều khóa có thể chuyển sang partition khác. Các message cũ của một thực thể có thể nằm ở partition cũ trong khi message mới đi vào partition mới. Nếu hệ thống phụ thuộc thứ tự theo khóa hoặc giữ state theo partition, thay đổi này cần kế hoạch chuyển đổi.

Với Kafka, partitionCount trong cấu hình producer được xem như một gợi ý; số partition thực tế của topic có thể lớn hơn và binder sử dụng giá trị lớn hơn giữa số đã cấu hình và số partition của topic. Hãy kiểm tra số partition thật trên topic, không chỉ nhìn giá trị trong YAML.

Với RabbitMQ, binder có thể provision queue cho từng partition. Tăng số partition có thể làm thay đổi số queue và cách gán queue cho instance. Cần kiểm tra topology thực tế trước khi triển khai.

Với Pulsar, topic có thể là partitioned topic và client có các cơ chế routing theo key. Cách binder ánh xạ partitioning abstraction của Spring Cloud Stream sang partitioned topic phụ thuộc phiên bản binder và cấu hình. Hãy kiểm tra khả năng của binder cụ thể và xác nhận partition thực tế trên broker.

## 8. Khác biệt giữa Kafka, RabbitMQ và Pulsar

Spring Cloud Stream cung cấp abstraction chung nhưng broker có mô hình phân vùng khác nhau.

| Broker | Cấu trúc phân vùng | Cách consumer nhận dữ liệu |
|---|---|---|
| Kafka | Topic gồm các partition có thứ tự riêng | Consumer group phân phối partition cho các member |
| RabbitMQ | Binder có thể mô phỏng partition bằng queue riêng | Mỗi instance nhận queue/partition theo cấu hình |
| Pulsar | Topic có thể được chia thành nhiều partition | Subscription và consumer type quyết định phân phối |

### Kafka

Kafka partition là đơn vị lưu trữ có thứ tự. Các message trong cùng partition được đọc theo offset tăng dần. Nếu producer dùng cùng partition key cho các sự kiện của một đơn hàng, các sự kiện đó có thể đi vào cùng partition và giữ thứ tự ghi trong partition.

PartitionKeyExtractorStrategy và PartitionSelectorStrategy của Spring Cloud Stream xác định partition đích ở lớp binder. Không nên nhầm partition key nội bộ của abstraction với Kafka record key: cách binder ánh xạ hai khái niệm này phụ thuộc binder và phiên bản. Nếu ứng dụng cần Kafka record key cho compaction hoặc logic native khác, hãy cấu hình và kiểm thử riêng record key theo hỗ trợ của Kafka binder.

Consumer group phân phối partition cho các member. Một partition tại một thời điểm chỉ được gán cho một consumer member trong cùng group, nhưng nhiều group độc lập có thể đọc cùng topic.

### RabbitMQ

RabbitMQ không tổ chức queue theo partition như Kafka. Rabbit binder có thể mô phỏng partitioning bằng cách tạo queue cho từng partition và định tuyến message tới queue tương ứng. Cấu hình instanceCount và instanceIndex giúp từng instance nhận phần dữ liệu được giao.

Queue topology, tên queue và routing được binder quản lý. Hãy kiểm tra số queue và binding trên RabbitMQ Management UI sau khi ứng dụng khởi động. Không giả định partitionCount trong YAML đồng nghĩa với một trường partition native bên trong AMQP message.

### Pulsar

Pulsar hỗ trợ partitioned topic và các kiểu subscription như Exclusive, Shared, Failover và Key_Shared. Các cơ chế này có ngữ nghĩa phân phối và thứ tự riêng. Partition key của Pulsar có thể ảnh hưởng routing và ordering, trong khi PartitionSelectorStrategy của Spring Cloud Stream trả về chỉ số partition theo abstraction chung.

Khi dùng Pulsar binder, hãy xác minh phiên bản binder hỗ trợ cách ánh xạ partitioning đang chọn. Nếu cần bảo đảm sự kiện cùng key được xử lý theo thứ tự, kiểm tra cả partitioned topic, key/ordering key và subscription type; không chỉ dựa vào việc cấu hình hai strategy trong ứng dụng.

## 9. Thiết kế khóa để giữ thứ tự theo thực thể

Partitioning thường được dùng để đưa các message liên quan đến cùng một partition. Ví dụ:

- Sự kiện OrderCreated, OrderPaid và OrderShipped dùng orderId.
- Sự kiện cập nhật tài khoản dùng accountId.
- Dữ liệu cảm biến dùng deviceId.
- Sự kiện nhiều tenant dùng khóa kết hợp tenantId và aggregateId.

Nếu chỉ dùng tenantId, mọi message của một tenant có thể tập trung vào một partition và gây nóng partition. Nếu chỉ dùng orderId nhưng orderId không duy nhất giữa tenant, hai tenant có thể vô tình chia sẻ cùng khóa. Khóa kết hợp giúp xác định đúng phạm vi thực thể.

Một quy tắc đơn giản:

~~~java
String partitionKey = tenantId + ":" + aggregateId;
~~~

Cần chuẩn hóa cách tạo khóa. Ví dụ, tenant-a:order-100 và TENANT-A:ORDER-100 có thể bị xem là hai khóa khác nhau nếu không thống nhất chữ hoa/thường. Nếu mã định danh có khoảng trắng, hãy quy định có trim hay không ở mọi producer.

### Giữ thứ tự không đồng nghĩa xử lý đúng một lần

Partitioning giúp các message liên quan được đưa tới cùng partition; nó không tự bảo đảm exactly-once processing. Consumer vẫn có thể nhận lại message do retry, rebalance hoặc sự cố trước khi xác nhận. Handler cần idempotent nếu tác động nghiệp vụ không được phép lặp.

Ngoài ra, thứ tự được bảo đảm trong phạm vi partition theo ngữ nghĩa broker, không phải thứ tự toàn cục giữa mọi partition. Nếu các sự kiện của cùng thực thể bị chọn sang partition khác do thuật toán hoặc partitionCount thay đổi, thứ tự theo thực thể không còn được duy trì qua ranh giới đó.

## 10. Kiểm thử hai strategy

Nên kiểm thử extractor và selector độc lập trước khi kiểm thử broker.

### Kiểm thử extractor

Xác minh:

- Payload đúng kiểu được trích xuất thành khóa mong đợi.
- Các message cùng tenantId và orderId tạo cùng khóa.
- Message thiếu tenantId hoặc orderId bị từ chối theo chính sách.
- Payload sai kiểu không bị ép kiểu hoặc xử lý âm thầm.
- Header key được đọc đúng nếu dùng header-based extractor.

### Kiểm thử selector

Với một tập khóa và partitionCount, xác minh:

- Kết quả luôn nằm trong khoảng 0 đến partitionCount - 1.
- Cùng khóa và cùng partitionCount luôn cho cùng chỉ số.
- Thay đổi partitionCount có thể làm thay đổi chỉ số; đây là hành vi cần kiểm soát.
- Phân phối trên tập khóa đại diện không bị lệch quá mức ngoài dự kiến.
- Selector từ chối key sai kiểu và partitionCount không hợp lệ.

Ví dụ unit test cho selector:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class TenantAwarePartitionSelectorTest {

    private final PartitionSelectorStrategy selector =
        (key, count) -> {
            OrderPartitionKey orderKey = (OrderPartitionKey) key;
            String value = orderKey.tenantId() + ":" + orderKey.orderId();
            return Math.floorMod(value.hashCode(), count);
        };

    @Test
    void sameKeyAlwaysSelectsSamePartition() {
        OrderPartitionKey key =
            new OrderPartitionKey("tenant-a", "order-100");

        int first = selector.selectPartition(key, 6);
        int second = selector.selectPartition(key, 6);

        assertEquals(first, second);
        assertTrue(first >= 0 && first < 6);
    }
}
~~~

Unit test không chứng minh binder gửi tới đúng partition trên broker. Cần thêm broker integration test để xác minh mapping thực tế.

## 11. Kiểm thử end-to-end với nhiều instance

Một bài kiểm thử thực tế nên gồm:

1. Khởi động broker và tạo destination với số partition dự kiến.
2. Khởi động producer có custom extractor và selector.
3. Khởi động ít nhất hai consumer instance cùng group.
4. Gửi nhiều sự kiện cho cùng một orderId.
5. Gửi sự kiện cho nhiều orderId và tenant khác nhau.
6. Kiểm tra các sự kiện cùng khóa đi tới cùng partition.
7. Kiểm tra các consumer instance nhận các partition theo cơ chế binder.
8. Dừng một consumer và quan sát rebalance hoặc queue assignment.
9. Khởi động lại consumer và kiểm tra message chưa xử lý được tiếp nhận theo chính sách broker.
10. So sánh phân phối thực tế với phân phối dự kiến.

Với Kafka, quan sát partition và offset của record; với RabbitMQ, quan sát queue theo partition và consumer; với Pulsar, quan sát partitioned topic, subscription và consumer assignment. Hãy dùng công cụ quản trị hoặc client có thể xác định partition thực tế của message.

Không nên kiểm thử chỉ bằng cách đếm message mỗi consumer nhận được. Phân phối không nhất thiết cân bằng tuyệt đối trong một mẫu nhỏ, đặc biệt khi một số khóa có tần suất cao hơn. Hãy kiểm tra quan hệ giữa khóa và partition trước, sau đó mới đánh giá tải giữa instance.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không kích hoạt partitioning | Chưa đặt partitionCount lớn hơn 1 | Cấu hình partitionCount trên output binding |
| Không tìm thấy extractor bean | Tên bean trong cấu hình không đúng | Đối chiếu partitionKeyExtractorName với tên @Bean |
| Không tìm thấy selector bean | Tên bean sai hoặc bean không được đăng ký | Kiểm tra partitionSelectorName và Application Context |
| Key luôn null | Extractor đọc sai payload/header hoặc message thiếu trường | Xác thực hợp đồng message và kiểm thử extractor |
| Selector trả partition ngoài phạm vi | Thuật toán không chuẩn hóa kết quả | Dùng Math.floorMod và kiểm tra partitionCount |
| Các sự kiện cùng thực thể đi khác partition | Khóa không ổn định hoặc producer dùng thuật toán khác nhau | Chuẩn hóa key và đồng bộ cấu hình trên mọi producer |
| Một partition nhận quá nhiều message | Key có cardinality thấp hoặc một thực thể phát quá nhiều | Đánh giá lại khóa và hot-key strategy |
| Consumer không nhận đủ partition | instanceCount/index sai hoặc broker assignment không phù hợp | Kiểm tra consumer.partitioned, group và cấu hình binder |
| Đổi partitionCount làm đổi vị trí key | Hash modulo phụ thuộc số partition | Lập kế hoạch migration và xử lý state |
| Kafka topic có số partition khác cấu hình | partitionCount là gợi ý; topic đã tồn tại với số partition khác | Kiểm tra topic thực tế và chính sách provisioning |
| RabbitMQ tạo queue không như mong đợi | Binder partitioning hoặc instance index chưa đúng | Kiểm tra queue topology và binding trên broker |
| Pulsar không giữ ordering như mong muốn | Subscription type hoặc key/partition mapping không phù hợp | Kiểm tra binder version, topic và subscription type |

Khi điều tra lỗi, kiểm tra theo thứ tự: output binding đã bật partitioning chưa, extractor trả về key nào, selector trả chỉ số nào, partitionCount thực tế là bao nhiêu, binder ánh xạ chỉ số ra sao và consumer có được gán đúng partition hay không.

## 13. Bài thực hành: phân vùng sự kiện đơn hàng

Tạo một producer phát sự kiện OrderCreated và consumer cập nhật kho:

1. Khai báo OrderCreated có eventId, tenantId, orderId, total và occurredAt.
2. Tạo OrderPartitionKey gồm tenantId và orderId.
3. Cài đặt orderPartitionKeyExtractor để đọc payload và tạo khóa.
4. Cài đặt tenantAwarePartitionSelector dùng Math.floorMod để trả chỉ số hợp lệ.
5. Đăng ký hai strategy bằng @Bean với tên rõ ràng.
6. Cấu hình output binding orderEvents-out-0 có partitionCount bằng 6, partitionKeyExtractorName và partitionSelectorName.
7. Cấu hình consumer inventory với destination orders và group inventory.
8. Nếu binder cần gán partition theo instance, cấu hình partitioned, instanceCount và instanceIndex phù hợp.
9. Gửi nhiều sự kiện có cùng orderId và xác minh chúng vào cùng partition.
10. Gửi sự kiện của nhiều tenant và order khác nhau để đánh giá phân phối.
11. Chạy nhiều consumer instance và quan sát cách binder phân công partition.
12. Thay partitionCount trong môi trường thử nghiệm và ghi nhận những khóa bị chuyển partition.
13. Viết kiểm thử cho key null, payload sai kiểu, selector sai kiểu và partitionCount không hợp lệ.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Extractor bean | Đọc đúng Message và trả khóa ổn định |
| Selector bean | Trả chỉ số trong miền hợp lệ |
| Bean name | Cấu hình khớp tên bean |
| Producer binding | Có partitionCount lớn hơn 1 |
| Strategy selection | Không khai báo đồng thời expression và custom name trong cùng cặp |
| Consumer assignment | Instance index/count phù hợp binder |
| Same-key behavior | Cùng thực thể được gửi tới cùng partition |
| Distribution | Tải không dồn ngoài dự kiến |
| Broker mapping | Partition hoặc queue thực tế khớp thiết kế |
| Change management | Có kế hoạch khi thay số partition hoặc thuật toán |

## Kết luận

PartitionKeyExtractorStrategy và PartitionSelectorStrategy cho phép tách quy tắc phân vùng thành hai bước có thể kiểm thử và tái sử dụng. Extractor lấy khóa từ Spring Message; selector chuyển khóa thành chỉ số partition trong phạm vi đã cấu hình. Spring Cloud Stream đăng ký các strategy thành bean và chọn chúng bằng partitionKeyExtractorName, partitionSelectorName trên output binding.

Thiết kế khóa ổn định theo thực thể nghiệp vụ, giữ thuật toán nhất quán giữa producer và kiểm tra ánh xạ của binder trên broker thật. Partitioning hỗ trợ giữ thứ tự trong phạm vi partition và chia tải, nhưng không tự bảo đảm exactly-once hoặc thứ tự toàn cục. Mỗi thay đổi về partitionCount, thuật toán hoặc cách gán consumer cần được kiểm thử và triển khai có kế hoạch.

## Tài liệu tham khảo

- [Spring Cloud Stream – Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)

