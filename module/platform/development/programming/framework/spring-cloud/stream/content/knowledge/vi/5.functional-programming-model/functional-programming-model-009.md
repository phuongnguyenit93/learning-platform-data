# Phân biệt nhiều hàm độc lập với một chuỗi hàm xử lý

Một ứng dụng Spring Cloud Stream có thể khai báo nhiều bean hàm cùng lúc. Tuy nhiên, có nhiều hàm trong một ứng dụng không đồng nghĩa chúng tự động nối tiếp nhau. Một số hàm có thể xử lý các luồng message độc lập; một số khác có thể được ghép thành một chuỗi, trong đó đầu ra của hàm trước trở thành đầu vào của hàm sau.

Sự khác biệt này ảnh hưởng trực tiếp đến số binding được tạo, destination cần cấu hình, cách message đi qua ứng dụng, phạm vi lỗi và khả năng mở rộng. Trong mô hình hàm `Supplier`/`Function`/`Consumer` của module `SPRING_CLOUD_STREAM`, cần hiểu rõ khi nào khai báo nhiều hàm độc lập và khi nào định nghĩa một pipeline xử lý bằng Spring Cloud Function composition. Các binding sau đó kết nối logic ứng dụng với Kafka, RabbitMQ hoặc Pulsar thông qua binder.

Bài thuộc chương **Mô hình hàm** và tập trung vào câu hỏi: nhiều hàm được kích hoạt cùng lúc khác gì với một chuỗi hàm xử lý? Ta sẽ dùng ví dụ xử lý đơn hàng để thấy rõ hai cách tổ chức.

## 1. Hai cách tổ chức hàm

Giả sử một hệ thống nhận sự kiện `OrderPlaced`. Sau khi đơn hàng được tạo, hệ thống cần cập nhật tồn kho, gửi thông báo và ghi số liệu phân tích. Có hai cách nhìn khác nhau:

**Nhiều hàm độc lập:** mỗi hàm thực hiện một trách nhiệm riêng và nhận dữ liệu từ binding của chính nó. Chúng có thể cùng đọc một destination nhưng thuộc các nhóm consumer độc lập, hoặc đọc các destination khác nhau. Không có quan hệ gọi nối tiếp giữa các hàm chỉ vì chúng nằm trong cùng ứng dụng.

```text
                         orders.placed
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
      inventoryUpdater  orderNotifier    orderMetrics
             |                |                |
             v                v                v
       Update stock      Send notice      Record metric
```

**Một chuỗi hàm xử lý (composition):** các hàm được ghép theo thứ tự. Giá trị trả về của hàm trước được truyền trực tiếp làm đối số cho hàm sau. Chuỗi thường có một binding đầu vào và một binding đầu ra nếu kết quả cuối cùng là một `Function`.

```text
orders.placed
     |
     v
normalizeOrder
     |
     v
validateOrder
     |
     v
enrichOrder
     |
     v
orders.ready
```

Điểm khác biệt cốt lõi: nhiều hàm độc lập là nhiều điểm xử lý riêng; composition là một pipeline logic có các bước phụ thuộc đầu ra của bước trước.

## 2. Nhiều hàm độc lập trong cùng ứng dụng

Spring Cloud Function cho phép ứng dụng có nhiều bean `Supplier`, `Function` hoặc `Consumer`. Khi muốn kích hoạt nhiều hàm độc lập, liệt kê tên các hàm trong `spring.cloud.function.definition`, phân tách bằng dấu chấm phẩy (`;`). Dấu chấm phẩy có nghĩa là các định nghĩa riêng biệt cùng được kích hoạt; nó không biểu thị việc truyền kết quả từ hàm này sang hàm khác.

Ví dụ có ba consumer độc lập:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

@Configuration
class OrderConsumers {

    @Bean
    Consumer<OrderPlaced> inventoryUpdater() {
        return event -> {
            System.out.println("Update inventory for " + event.orderId());
        };
    }

    @Bean
    Consumer<OrderPlaced> orderNotifier() {
        return event -> {
            System.out.println("Notify customer for " + event.orderId());
        };
    }

    @Bean
    Consumer<OrderPlaced> orderMetrics() {
        return event -> {
            System.out.println("Record order metric: " + event.total());
        };
    }
}
```

Cấu hình kích hoạt cả ba hàm:

```yaml
spring:
  cloud:
    function:
      definition: inventoryUpdater;orderNotifier;orderMetrics
    stream:
      bindings:
        inventoryUpdater-in-0:
          destination: orders.placed
          group: inventory-projection
          content-type: application/json
        orderNotifier-in-0:
          destination: orders.placed
          group: order-notification
          content-type: application/json
        orderMetrics-in-0:
          destination: orders.placed
          group: order-metrics
          content-type: application/json
```

Mỗi consumer có binding đầu vào riêng theo quy ước `<functionName>-in-0`. Cả ba binding cùng đọc destination `orders.placed`, nhưng dùng group khác nhau để mỗi trách nhiệm nhận được luồng message độc lập. Nếu tất cả cùng dùng một consumer group trên Kafka, các instance sẽ chia partition trong cùng group thay vì mỗi hàm nhận đầy đủ mọi record. Với RabbitMQ và Pulsar, cần cấu hình queue hoặc subscription riêng tương ứng với từng nhóm.

Các hàm này không gọi lẫn nhau. `inventoryUpdater` không đợi `orderNotifier`; `orderMetrics` không nhận kết quả của hai hàm còn lại. Mỗi hàm có thể được mở rộng, quan sát, thử lại và triển khai theo nhu cầu của trách nhiệm riêng, trong giới hạn của cách ứng dụng và binder được triển khai.

### Khi nào chọn cách độc lập?

Chọn nhiều hàm độc lập khi:

- Nhiều bộ phận cần phản ứng với cùng một sự kiện nhưng không phụ thuộc kết quả của nhau.
- Một consumer có thể chậm hoặc tạm dừng mà không cần chặn các consumer khác.
- Mỗi trách nhiệm có yêu cầu tải, quyền truy cập, retry hoặc thời gian lưu message khác nhau.
- Muốn tách luồng xử lý để theo dõi lỗi và mở rộng từng trách nhiệm.

Ví dụ, dịch vụ thông báo không nên làm chậm việc cập nhật tồn kho chỉ vì nhà cung cấp email tạm thời không khả dụng. Hai trách nhiệm có thể tiêu thụ cùng sự kiện qua hai nhóm độc lập, với chính sách retry riêng.

## 3. Một chuỗi hàm xử lý bằng composition

Composition ghép nhiều hàm tương thích thành một hàm logic. Trong Spring Cloud Function, toán tử pipe (`|`) thể hiện thứ tự ghép: hàm bên trái chạy trước, kết quả được truyền cho hàm bên phải.

Giả sử quy trình xử lý đơn hàng gồm ba bước:

1. Chuẩn hóa mã đơn và dữ liệu đầu vào.
2. Kiểm tra điều kiện nghiệp vụ.
3. Bổ sung thông tin định tuyến hoặc nhãn xử lý.

Mỗi bước có thể được viết thành một `Function` riêng:

```java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

record NormalizedOrder(String orderId, long total) {}

record ValidatedOrder(String orderId, long total) {}

record EnrichedOrder(String orderId, long total, String processingLane) {}

@Configuration
class OrderPipelineFunctions {

    @Bean
    Function<OrderPlaced, NormalizedOrder> normalizeOrder() {
        return event -> new NormalizedOrder(
            event.orderId().trim().toUpperCase(Locale.ROOT),
            event.total()
        );
    }

    @Bean
    Function<NormalizedOrder, ValidatedOrder> validateOrder() {
        return event -> {
            if (event.orderId().isBlank() || event.total() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            return new ValidatedOrder(event.orderId(), event.total());
        };
    }

    @Bean
    Function<ValidatedOrder, EnrichedOrder> enrichOrder() {
        return event -> new EnrichedOrder(
            event.orderId(),
            event.total(),
            event.total() >= 10_000_000 ? "priority" : "standard"
        );
    }
}
```

Chữ ký kiểu dữ liệu cho thấy đầu ra và đầu vào liền kề tương thích:

| Bước | Kiểu đầu vào | Kiểu đầu ra |
|---|---|---|
| `normalizeOrder` | `OrderPlaced` | `NormalizedOrder` |
| `validateOrder` | `NormalizedOrder` | `ValidatedOrder` |
| `enrichOrder` | `ValidatedOrder` | `EnrichedOrder` |

Khai báo composition:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|validateOrder|enrichOrder
    stream:
      bindings:
        'normalizeOrder|validateOrder|enrichOrder-in-0':
          destination: orders.placed
          group: order-pipeline
          content-type: application/json
        'normalizeOrder|validateOrder|enrichOrder-out-0':
          destination: orders.enriched
          content-type: application/json
```

Trong cấu hình này, `normalizeOrder|validateOrder|enrichOrder` là một định nghĩa hàm đã ghép. Binding đầu vào nhận `OrderPlaced`; các hàm trung gian truyền dữ liệu trực tiếp trong pipeline; binding đầu ra phát `EnrichedOrder`. Những bước ở giữa không tự tạo topic hoặc queue riêng và không tự publish kết quả trung gian ra broker.

### Điều kiện để ghép hàm

Các hàm phải có chữ ký dữ liệu tương thích. Nếu `normalizeOrder` trả về `NormalizedOrder`, hàm kế tiếp phải nhận kiểu dữ liệu đó hoặc một kiểu mà quá trình chuyển đổi được hỗ trợ. Khi ghép nhiều hàm, cần kiểm tra:

- Kiểu đầu ra của bước trước tương thích với kiểu đầu vào của bước sau.
- Các bước có thứ tự rõ ràng và không phụ thuộc ngầm vào trạng thái bên ngoài.
- Hàm xử lý lỗi theo quy ước thống nhất; lỗi ở một bước làm pipeline hiện tại thất bại.
- Việc chuyển đổi payload và headers có chủ đích, đặc biệt khi dùng `Message<T>` thay vì chỉ dùng payload.
- Các bước có chi phí xử lý phù hợp với việc chạy trong cùng một luồng xử lý.

Composition thích hợp cho các bước biến đổi hoặc kiểm tra có quan hệ tuần tự. Nếu mỗi bước cần lưu trạng thái, retry độc lập hoặc có thể được triển khai riêng, cân nhắc tách thành các ứng dụng hoặc luồng message riêng.

## 4. Dấu phân cách `;` và `|` không có cùng ý nghĩa

Đây là điểm dễ nhầm nhất khi khai báo nhiều hàm:

| Cú pháp | Ý nghĩa | Mô hình thực thi |
|---|---|---|
| `inventoryUpdater;orderNotifier;orderMetrics` | Kích hoạt nhiều hàm độc lập | Mỗi hàm có binding riêng; không tự truyền kết quả giữa các hàm |
| `normalizeOrder|validateOrder|enrichOrder` | Ghép các hàm thành một pipeline | Đầu ra mỗi bước được truyền vào bước kế tiếp |
| `normalizeOrder|validateOrder;orderNotifier` | Một pipeline và một hàm độc lập | Pipeline được ghép; `orderNotifier` là định nghĩa riêng |

Không dùng dấu chấm phẩy khi muốn kết quả của hàm A đi vào hàm B. Cũng không dùng pipe chỉ vì muốn nhiều consumer cùng đọc một sự kiện. Pipe tạo quan hệ tuần tự; nhiều consumer độc lập cần destination và group/subscription phù hợp.

Ví dụ kết hợp cả hai cách:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|validateOrder;orderMetrics
    stream:
      bindings:
        'normalizeOrder|validateOrder-in-0':
          destination: orders.placed
          group: order-validation
        'normalizeOrder|validateOrder-out-0':
          destination: orders.validated
        orderMetrics-in-0:
          destination: orders.placed
          group: order-metrics
```

Pipeline `normalizeOrder|validateOrder` nhận và phát message qua hai binding của pipeline. `orderMetrics` độc lập đọc sự kiện từ `orders.placed`. Hai đường xử lý không phụ thuộc việc pipeline đã hoàn tất hay chưa.

## 5. Binding name và destination trong hai mô hình

Binding name được sinh từ tên hàm hoặc tên composition. Destination do cấu hình quyết định. Vì thế, nhiều hàm độc lập thường tạo nhiều binding, còn một chuỗi hàm thường có một cặp binding ở hai đầu nếu là composition `Function` sang `Function`.

| Mô hình | Binding đầu vào | Binding đầu ra | Destination minh họa |
|---|---|---|---|
| Ba consumer độc lập | `inventoryUpdater-in-0`, `orderNotifier-in-0`, `orderMetrics-in-0` | Không có với `Consumer` | Cùng `orders.placed` nhưng group riêng |
| Một function độc lập | `calculateRisk-in-0` | `calculateRisk-out-0` | `orders.placed` → `orders.risk-scored` |
| Chuỗi ba function | `normalizeOrder|validateOrder|enrichOrder-in-0` | `normalizeOrder|validateOrder|enrichOrder-out-0` | `orders.placed` → `orders.enriched` |

Nếu tên binding composition chứa ký tự `|`, nên đặt key YAML trong dấu nháy để tránh nhầm lẫn với cú pháp YAML. Cấu hình cụ thể cần giữ đúng tên binding mà framework tạo từ định nghĩa hàm.

## 6. Dữ liệu trung gian có đi qua broker không?

Trong composition, các bước gọi nhau trong cùng pipeline. Ví dụ `normalizeOrder` trả về `NormalizedOrder` và `validateOrder` nhận ngay giá trị đó. Message trung gian không cần được serialize, publish lên topic rồi consumer khác đọc lại.

```text
Một lần nhận message
        |
        v
  deserialize input
        |
        v
  normalizeOrder
        |  NormalizedOrder (in-memory)
        v
  validateOrder
        |  ValidatedOrder (in-memory)
        v
  enrichOrder
        |
        v
  serialize output
        |
        v
  publish orders.enriched
```

Điều này giảm số lần qua broker và phù hợp với chuỗi biến đổi ngắn. Đổi lại, các bước có chung vòng đời xử lý message. Nếu bước thứ hai lỗi, pipeline chưa tạo kết quả cuối; binder xử lý lỗi ở ranh giới binding theo cấu hình retry, acknowledgement và DLQ. Không có một điểm commit độc lập cho từng hàm trung gian chỉ vì chúng được viết thành các bean riêng.

Nếu cần message trung gian được lưu giữ, quan sát độc lập hoặc có thể phát lại từ một mốc, hãy tạo destination và binding rõ ràng cho từng chặng. Khi đó kiến trúc chuyển thành nhiều bước messaging nối qua broker, thay vì composition trong bộ nhớ.

## 7. Supplier, Function và Consumer trong pipeline

Ba kiểu hàm biểu diễn ba vai trò:

- `Supplier<T>` tạo dữ liệu và không nhận đối số đầu vào từ binding.
- `Function<T, R>` nhận dữ liệu và trả về dữ liệu đã biến đổi.
- `Consumer<T>` nhận dữ liệu và hoàn thành một tác vụ mà không tạo output từ hàm.

Composition có thể kết hợp các vai trò nếu hợp đồng kiểu và mục đích luồng phù hợp. Ví dụ một supplier tạo sự kiện, function chuẩn hóa rồi consumer ghi nhận kết quả. Tuy nhiên, để dễ quan sát và cấu hình, bài này dùng chuỗi `Function` làm ví dụ chính. Với pipeline có `Supplier` hoặc `Consumer` ở đầu/cuối, cần kiểm tra chữ ký và cách Spring Cloud Function diễn giải định nghĩa hàm trong phiên bản đang dùng.

Không nên biến mọi thao tác thành một chuỗi dài. Một consumer có tác dụng phụ như gửi email hoặc trừ tồn kho có thể cần retry và kiểm soát giao nhận riêng. Đưa nó vào composition dài có nghĩa lỗi của bước này làm thất bại cả lần xử lý message ở pipeline. Nếu tác vụ cần vận hành độc lập, hãy phát một sự kiện hoặc command để consumer riêng nhận.

## 8. Fan-out không phải là composition

Fan-out là một message được phân phối cho nhiều bên nhận độc lập. Composition là dữ liệu đi tuần tự qua nhiều bước. Hai mô hình giải quyết hai nhu cầu khác nhau:

| Nhu cầu | Cách tổ chức phù hợp | Ví dụ |
|---|---|---|
| Nhiều bên cần biết đơn hàng đã tạo | Fan-out đến nhiều group/queue/subscription | Kho, phân tích và thông báo cùng nhận `OrderPlaced` |
| Dữ liệu cần chuẩn hóa rồi kiểm tra rồi bổ sung | Composition | `normalizeOrder|validateOrder|enrichOrder` |
| Một bước cần phát một sự kiện nghiệp vụ mới để nhiều bên phản ứng | Function phát output đến destination, rồi nhiều consumer độc lập nhận | `OrderValidated` được phát đến kho và phân tích |
| Một tác vụ nền cần retry và vận hành riêng | Consumer độc lập trên destination riêng | Dịch vụ gửi email nhận `NotificationRequested` |

Không nên ghép `updateInventory|sendEmail|recordMetrics` nếu ba việc không cần dùng kết quả của nhau. Một chuỗi như vậy sẽ khiến gửi email chậm hoặc lỗi có thể ảnh hưởng việc ghi metric và cập nhật tồn kho. Hãy phát sự kiện chung rồi để từng consumer đảm nhận trách nhiệm riêng.

## 9. Lỗi và khả năng phục hồi

Mô hình tổ chức hàm quyết định nơi lỗi xuất hiện và phạm vi retry:

**Với các hàm độc lập:** mỗi binding có luồng nhận và chính sách lỗi riêng theo cấu hình binder. Lỗi trong `orderNotifier` không nhất thiết ảnh hưởng đến `inventoryUpdater`, nếu hai consumer thực sự dùng group/queue/subscription độc lập.

**Với composition:** lỗi ở bất kỳ bước nào có thể làm lần gọi pipeline thất bại. Binder nhìn thấy kết quả xử lý của toàn bộ function đã ghép. Khi retry, pipeline có thể chạy lại từ đầu; các bước có tác dụng phụ phải idempotent hoặc được thiết kế để không lặp tác động.

Ví dụ, nếu `normalizeOrder` và `validateOrder` chỉ biến đổi dữ liệu thuần, chạy lại thường không gây tác dụng phụ. Nếu `enrichOrder` gọi một dịch vụ tính phí hoặc ghi database, cần xử lý idempotency và transaction rõ ràng. Không nên giả định framework tự tạo transaction bao trùm mọi bước và mọi dịch vụ ngoài.

Một số nguyên tắc:

- Giữ các bước composition càng thuần càng tốt: cùng đầu vào cho kết quả nhất quán và không tạo tác dụng phụ ngoài dự kiến.
- Đặt timeout và retry cho dependency bên ngoài ở đúng tầng, với giới hạn và backoff.
- Dùng event ID hoặc idempotency key ổn định khi một pipeline có thể được giao lại.
- Nếu một bước có lỗi dữ liệu không thể sửa bằng retry, đưa message vào DLQ hoặc luồng cách ly theo chính sách.
- Nếu một trách nhiệm cần replay riêng, cân nhắc tách nó thành consumer độc lập với destination và group riêng.

## 10. Kiểm thử hai mô hình

Kiểm thử cần xác nhận cả logic hàm và cách framework kết nối binding:

| Kiểm thử | Nhiều hàm độc lập | Composition |
|---|---|---|
| Kiểm tra logic | Gọi từng consumer/function riêng | Kiểm tra từng bước và kết quả pipeline |
| Binding | Xác nhận mỗi hàm có binding riêng | Xác nhận binding đầu/cuối của tên composition |
| Luồng message | Mỗi hàm nhận message theo destination/group của nó | Đầu ra bước trước được truyền cho bước sau |
| Lỗi | Lỗi một consumer không làm dừng consumer độc lập khác | Lỗi một bước làm thất bại lần gọi pipeline |
| Giao nhận | Kiểm tra retry/DLQ cho từng binding | Kiểm tra retry/DLQ ở ranh giới pipeline và tác dụng phụ bị lặp |

Ví dụ kiểm thử đơn vị cho các bước composition có thể gọi từng bean và kiểm tra kiểu dữ liệu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class OrderPipelineFunctionsTest {

    @Test
    void normalizesOrderId() {
        var result = new OrderPipelineFunctions()
            .normalizeOrder()
            .apply(new OrderPlaced(" ord-42 ", 500_000));

        assertEquals("ORD-42", result.orderId());
    }
}
```

Với integration test, dùng binder test hoặc broker thật phù hợp để kiểm tra destination, group và binding được tạo đúng. Mock trực tiếp các hàm chỉ chứng minh logic Java; nó không chứng minh message thực sự đi qua broker như mong đợi. Khi kiểm tra nhiều consumer độc lập, cần xác minh mỗi group nhận được bản tin của riêng nó. Khi kiểm tra composition, cần xác minh một message đầu vào tạo đúng output cuối cùng và không phát sinh các destination trung gian ngoài thiết kế.

## 11. Chọn mô hình theo yêu cầu nghiệp vụ

Trước khi chọn cách khai báo, hãy trả lời các câu hỏi:

1. Các bước có cần kết quả của nhau không? Nếu có, composition có thể phù hợp.
2. Các trách nhiệm có thể chạy độc lập không? Nếu có, hãy tách thành nhiều hàm độc lập.
3. Một bước lỗi có nên chặn các bước còn lại không? Nếu không, đừng đặt chúng trong cùng pipeline đồng bộ.
4. Có cần lưu giữ hoặc phát lại kết quả trung gian không? Nếu có, hãy tạo destination rõ ràng.
5. Các bước có yêu cầu mở rộng, retry, quyền truy cập hoặc lịch triển khai khác nhau không? Nếu có, tách binding hoặc dịch vụ phù hợp.
6. Dữ liệu đầu ra của bước trước có tương thích với đầu vào bước sau không? Nếu không, cần một bước chuyển đổi rõ ràng hoặc một hợp đồng message khác.

| Tiêu chí | Nhiều hàm độc lập | Chuỗi hàm composition |
|---|---|---|
| Quan hệ giữa bước | Không phụ thuộc kết quả của nhau | Bước sau dùng output bước trước |
| Số binding | Mỗi hàm có binding riêng theo vai trò | Thường một input và một output cho function composition |
| Broker hop giữa các bước | Mỗi hàm có thể nhận từ destination riêng hoặc chung | Không có hop broker giữa các bước nội bộ |
| Lỗi | Có thể cô lập theo binding | Một bước lỗi làm pipeline hiện tại thất bại |
| Mở rộng | Tách theo consumer group/queue/subscription | Mở rộng pipeline như một đơn vị tiêu thụ |
| Dùng khi | Fan-out, tác vụ độc lập | Biến đổi tuần tự, kiểm tra tuần tự |

## 12. Quy trình cấu hình và xác minh

Khi xây dựng ứng dụng Spring Cloud Stream có nhiều hàm, thực hiện theo các bước sau:

1. Liệt kê bean hàm và vai trò của từng bean (`Supplier`, `Function`, `Consumer`).
2. Vẽ luồng dữ liệu: hàm nào độc lập, hàm nào cần ghép tuần tự.
3. Dùng dấu `;` cho nhiều định nghĩa độc lập; dùng `|` cho composition theo thứ tự.
4. Xác định binding name được tạo ra từ từng hàm hoặc composition.
5. Gán destination, group và content type cho mỗi binding phù hợp với broker.
6. Nếu nhiều consumer cần nhận cùng một sự kiện, cấp group/queue/subscription độc lập cho từng trách nhiệm.
7. Kiểm tra kiểu dữ liệu giữa các bước composition và quy tắc xử lý exception.
8. Kiểm thử binding, luồng message, retry, DLQ và khả năng chạy lặp an toàn.
9. Quan sát lag, throughput và lỗi theo từng binding để xác định nơi cần mở rộng.

## 13. Tự kiểm tra

- [ ] Giải thích được vì sao nhiều bean hàm trong cùng ứng dụng không tự động nối tiếp nhau.
- [ ] Phân biệt ý nghĩa của `;` và `|` trong `spring.cloud.function.definition`.
- [ ] Xác định được binding name của các hàm độc lập và của một function composition.
- [ ] Mô tả được cách nhiều consumer độc lập cùng nhận một destination bằng group riêng.
- [ ] Giải thích được cách output của function trước trở thành input của function sau.
- [ ] Biết dữ liệu trung gian trong composition được truyền trong ứng dụng và không tự động qua broker.
- [ ] Phân tích được phạm vi lỗi và retry của hai mô hình.
- [ ] Chọn được fan-out hoặc composition theo quan hệ phụ thuộc nghiệp vụ.

## Kết luận

Nhiều hàm độc lập được kích hoạt bằng các định nghĩa tách biệt và mỗi hàm có binding riêng; chúng không tự truyền kết quả cho nhau. Composition dùng pipe (`|`) để ghép các hàm tương thích thành một pipeline, trong đó dữ liệu đi tuần tự từ bước này sang bước kế tiếp. Dấu chấm phẩy (`;`) phân tách nhiều định nghĩa độc lập. Chọn đúng mô hình giúp xác định binding, destination, group, phạm vi lỗi và cách mở rộng phù hợp. Với Spring Cloud Stream, hãy dùng composition cho các bước biến đổi có quan hệ tuần tự và dùng consumer độc lập cho các trách nhiệm cần phản ứng, phục hồi hoặc mở rộng riêng.
