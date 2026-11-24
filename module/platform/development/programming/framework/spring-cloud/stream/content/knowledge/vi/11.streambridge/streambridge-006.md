# Giới hạn bộ nhớ đệm destination động và kiểm soát số lượng đích

`StreamBridge` cho phép ứng dụng gửi message tới destination được xác định tại thời điểm chạy. Cách này hữu ích khi một yêu cầu HTTP, một sự kiện từ hệ thống ngoài hoặc một quy tắc nghiệp vụ quyết định message cần đi tới đâu. Tuy nhiên, nếu mỗi giá trị đầu vào có thể tạo ra một destination mới, ứng dụng sẽ phải quản lý số lượng binding động và tài nguyên broker có thể tăng nhanh.

Spring Cloud Stream cung cấp hai cơ chế kiểm soát quan trọng: giới hạn bộ nhớ đệm binding đầu ra động bằng `spring.cloud.stream.dynamic-destination-cache-size`, và giới hạn tên destination được phép bind bằng `spring.cloud.stream.dynamic-destinations`. Cơ chế cache kiểm soát lượng binding được giữ trong bộ nhớ của ứng dụng; danh sách cho phép kiểm soát destination nào được phép bind động. Hai cơ chế giải quyết hai vấn đề khác nhau và nên được dùng cùng với quy tắc định tuyến có giới hạn.

## 1. Destination động xuất hiện khi nào?

Với một output binding đã khai báo trước, ứng dụng biết tên binding và destination ngay từ lúc cấu hình. `StreamBridge` có thể gửi dữ liệu qua binding đó mà không cần tạo binding mới cho mỗi lần gửi.

Khi đích gửi chỉ được xác định lúc chạy, ứng dụng có thể gọi `StreamBridge.send(...)` bằng tên destination chưa có binding. Spring Cloud Stream tạo output binding động cho đích đó và lưu binding trong cache để những lần gửi tiếp theo có thể tái sử dụng.

Ví dụ một API nhận sự kiện và chọn destination theo vùng:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

public record OrderCreated(String orderId) {}

@Service
public class OrderPublisher {

    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, OrderCreated event) {
        return streamBridge.send(destination, event);
    }
}
```

Trong ví dụ, tham số đầu tiên của `send` là tên binding hoặc destination mà `StreamBridge` sẽ sử dụng. Nếu tên đó chưa phải binding được khai báo, nó có thể được xử lý như destination động. Không nên đưa trực tiếp một chuỗi tùy ý từ request bên ngoài vào tham số này; phần sau sẽ xây dựng lớp ánh xạ và kiểm soát đầu vào.

## 2. Phân biệt binding cache và tài nguyên broker

Khi một destination động được dùng, có hai lớp tài nguyên cần phân biệt:

| Lớp | Ví dụ | Cơ chế quản lý |
| --- | --- | --- |
| Binding/channel phía ứng dụng | Output binding và message channel mà `StreamBridge` dùng để gửi | Cache động của Spring Cloud Stream giữ một số binding để tái sử dụng và loại bỏ mục cũ khi vượt giới hạn |
| Destination phía broker | Topic Kafka, exchange/queue RabbitMQ hoặc topic Pulsar | Binder và broker quản lý provisioning, quyền truy cập, vòng đời và việc xóa tài nguyên |

Cache động không phải là danh sách topic tối đa mà broker được phép có. Khi một mục bị loại khỏi cache, binding đó có thể cần được tạo lại nếu ứng dụng gửi tới destination ấy lần nữa. Việc loại binding khỏi cache không đồng nghĩa topic, exchange, queue hay topic Pulsar tương ứng đã bị xóa khỏi broker.

Do đó, tăng cache size không phải cách xử lý trực tiếp cho việc có quá nhiều topic hoặc queue. Muốn kiểm soát số lượng tài nguyên broker, cần giới hạn destination hợp lệ, thiết kế vòng đời tài nguyên và cấu hình provisioning phù hợp với binder.

## 3. Cache động có giới hạn và cơ chế LRU

Spring Cloud Stream dùng cache tự loại bỏ cho các output binding động. Kích thước mặc định là **10**. Cache sử dụng chính sách Least Recently Used (LRU): khi đạt giới hạn và cần đưa một destination mới vào, mục ít được sử dụng gần đây nhất có thể bị loại khỏi cache.

Thuộc tính cấu hình:

```yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 32
```

Giá trị `32` là ví dụ, không phải mức khuyến nghị cho mọi ứng dụng. Kích thước phù hợp phụ thuộc số destination thường xuyên được sử dụng, số instance ứng dụng, tần suất chuyển đích và chi phí tạo lại binding.

Ví dụ, nếu một instance thường xuyên gửi tới 8 destination và cache có kích thước 10, phần lớn các binding có thể được tái sử dụng. Nếu instance luân phiên giữa 100 destination với cache kích thước 10, nhiều binding sẽ bị loại và phải tạo lại khi được dùng lần sau. Hiện tượng này làm tăng chi phí khởi tạo, provisioning hoặc kết nối, tùy binder.

### Cách chọn cache size

Hãy bắt đầu từ *working set* — số destination khác nhau mà một instance thực sự sử dụng thường xuyên trong một khoảng thời gian đại diện:

1. Đo số destination hoạt động trong giờ cao điểm.
2. Xác định số đích được truy cập lặp lại thường xuyên và số đích chỉ dùng một lần.
3. Chọn cache đủ lớn cho tập đích hoạt động thường xuyên, có dự phòng hợp lý.
4. Theo dõi tần suất tạo lại binding và mức sử dụng bộ nhớ sau khi triển khai.
5. Điều chỉnh theo số instance và mức độ phân tán traffic.

Không nhất thiết phải đặt cache bằng tổng số destination có thể tồn tại. Một hệ thống có danh sách cho phép 500 đích nhưng mỗi instance chỉ sử dụng ổn định 20 đích trong một khoảng thời gian có thể chọn cache theo working set, sau khi đo kiểm tra chi phí eviction và tạo lại binding.

## 4. Giới hạn destination được phép bind động

Thuộc tính `spring.cloud.stream.dynamic-destinations` cho phép khai báo danh sách destination có thể được bind động. Nếu danh sách được cấu hình, chỉ những destination có tên trong danh sách mới được phép bind. Nếu để trống hoặc không cấu hình, mặc định không giới hạn bằng allowlist này.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders-north
        - orders-central
        - orders-south
        - orders-international
      dynamic-destination-cache-size: 16
```

Danh sách trên giới hạn các tên có thể bind động. Cache có kích thước 16 giữ các binding được sử dụng gần đây; allowlist chỉ có 4 tên trong ví dụ nên cache không bị đầy do riêng các đích hợp lệ này.

Nếu allowlist có nhiều đích hơn cache size, điều đó vẫn hợp lệ: ứng dụng chỉ được bind các tên trong allowlist, còn cache giữ một tập con các binding được dùng gần đây. Khi đích đã bị eviction được gọi lại, binding có thể phải được tạo lại.

Allowlist là một lớp kiểm soát quan trọng, nhưng vẫn cần kiểm tra đầu vào trong code. Nó không thay thế xác thực người gọi, phân quyền theo tenant hoặc kiểm tra xem người dùng có quyền phát tới một vùng dữ liệu cụ thể hay không.

## 5. Ánh xạ đầu vào bên ngoài sang tập destination cố định

Một lỗi thiết kế phổ biến là nối trực tiếp giá trị request vào tên topic:

```java
// Không nên: giá trị đầu vào có thể tạo ra vô hạn tên destination.
String destination = "orders-" + request.tenantId();
streamBridge.send(destination, event);
```

Nếu `tenantId` có thể là bất kỳ chuỗi nào, số lượng tên đích tiềm năng không có giới hạn. Người gọi cũng có thể vô tình hoặc cố ý tạo ra destination ngoài phạm vi nghiệp vụ.

Thay vào đó, ánh xạ một khóa nghiệp vụ đã xác thực sang tập tên đích được quản lý:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class RegionalOrderPublisher {

    private static final Map<String, String> DESTINATIONS = Map.of(
            "north", "orders-north",
            "central", "orders-central",
            "south", "orders-south"
    );

    private final StreamBridge streamBridge;

    public RegionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String region, OrderCreated event) {
        String destination = DESTINATIONS.get(region);
        if (destination == null) {
            throw new IllegalArgumentException("Unsupported region: " + region);
        }

        return streamBridge.send(destination, event);
    }
}
```

Với cách này, `region` chỉ có thể chọn một trong ba destination đã định nghĩa. Cấu hình allowlist cũng chỉ cần chứa ba tên tương ứng. Nếu có thêm vùng mới, nhóm phát triển cập nhật mapping, allowlist, quyền broker và quy trình provisioning trong cùng một thay đổi có thể review.

Trong ứng dụng nhiều tenant, không nhất thiết phải tạo một destination cho mỗi tenant. Có thể dùng một destination chung và đưa `tenantId` vào payload hoặc header để consumer phân vùng xử lý. Chỉ chọn mô hình một destination mỗi tenant khi có yêu cầu rõ về cô lập dữ liệu, quyền truy cập, retention, throughput hoặc vòng đời riêng.

## 6. Cấu hình hoàn chỉnh cho StreamBridge

Ví dụ sau kết hợp allowlist và cache size với service ánh xạ vùng ở trên:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders-north
        - orders-central
        - orders-south
      dynamic-destination-cache-size: 16
      bindings:
        orders-north:
          content-type: application/json
        orders-central:
          content-type: application/json
        orders-south:
          content-type: application/json
```

Các binding có thể được tạo động khi `StreamBridge` gửi lần đầu tới tên tương ứng. Tùy cách khai báo binding và phiên bản Spring Cloud Stream, có thể cấu hình thêm các thuộc tính producer hoặc binder riêng cho từng đích. Nếu một tập đích đã biết và cần được khởi tạo sẵn lúc ứng dụng khởi động, cân nhắc khai báo output binding tường minh thay vì chờ lần gửi đầu tiên.

Tên binding/destination mà code truyền vào `send` phải thống nhất với tên được allowlist và cấu hình. Hãy kiểm tra chính xác tên thực tế được binder sử dụng, nhất là khi ứng dụng có nhiều binder hoặc nhiều cluster.

## 7. Chọn giữa binding cố định và destination động

Không phải mọi trường hợp định tuyến đều cần tạo destination động.

| Tình huống | Cách phù hợp | Lý do |
| --- | --- | --- |
| Chỉ gửi tới một topic audit | Output binding cố định | Tên đích biết trước, không cần cache động |
| Gửi tới 3 vùng đã biết | Các output binding cố định hoặc StreamBridge với allowlist | Tập đích nhỏ và ổn định |
| Gửi tới một tập destination thay đổi theo cấu hình quản trị | StreamBridge động với allowlist được cập nhật có kiểm soát | Đích thay đổi nhưng vẫn có thể giới hạn |
| Mỗi request có thể tự tạo tên đích tùy ý | Không cho phép trực tiếp; cần ánh xạ hoặc từ chối | Tránh cardinality không giới hạn và lạm dụng tài nguyên |
| Chỉ cần phân biệt tenant trong cùng luồng | Một destination chung, tenant ID trong payload/header | Tránh tạo quá nhiều topic hoặc queue |

Với tập destination hữu hạn và ổn định, binding cố định giúp cấu hình rõ ràng, dễ kiểm tra quyền và quan sát. Dynamic destination phù hợp khi lựa chọn đích thực sự chỉ biết ở runtime và lợi ích của nó lớn hơn chi phí quản lý binding.

## 8. Cache size không phải giới hạn số tenant hay giới hạn tổng topic

Ba con số thường bị nhầm lẫn:

- **Cache size:** số binding động tối đa được giữ trong cache của một instance ứng dụng.
- **Allowlist size:** số destination mà ứng dụng được phép bind động theo cấu hình.
- **Broker destination count:** tổng số topic, exchange, queue hoặc tài nguyên tương ứng đang tồn tại trên broker.

Ví dụ, cấu hình cache size 20 và allowlist 100 tên có nghĩa một instance có thể chỉ giữ tối đa 20 binding gần đây trong cache, nhưng vẫn có thể sử dụng luân phiên các tên nằm trong allowlist. Tùy binder và quyền provisioning, các tài nguyên broker đã được tạo có thể vẫn tồn tại sau khi binding bị loại khỏi cache.

Nếu yêu cầu nghiệp vụ giới hạn tổng số tenant, tổng số topic hoặc tổng số queue, cần thực hiện giới hạn ở tầng quản lý nghiệp vụ và broker. Không dùng cache size như một bộ đếm tenant hoặc một cơ chế quota tài nguyên.

## 9. Tác động khi chạy nhiều instance

Cache động nằm trong tiến trình ứng dụng. Khi triển khai nhiều replica, mỗi replica có cache riêng và có thể giữ những binding khác nhau tùy traffic mà nó nhận được.

Nếu cache size là 32 và dịch vụ chạy 5 replica, tổng số binding đang được giữ trong bộ nhớ trên toàn bộ các replica có thể lớn hơn 32; con số cấu hình áp dụng theo từng instance, không phải một cache chia sẻ toàn cụm. Vì thế, capacity planning cần xét cả số replica và working set của mỗi replica.

Khi autoscaling tạo hoặc dừng instance, cache của instance mới bắt đầu rỗng; các destination được gọi lần đầu trên instance đó có thể cần khởi tạo binding. Điều này có thể làm tăng chi phí bind trong giai đoạn scale-out. Cần quan sát thời gian tạo binding và khả năng provisioning của broker trong tình huống này.

## 10. Lưu ý về broker provisioning và vòng đời destination

Việc `StreamBridge` tạo binding không bảo đảm mọi broker luôn tự tạo tài nguyên theo cùng một cách. Binder có thể provision destination tự động nếu được cấu hình và có quyền phù hợp, hoặc yêu cầu tài nguyên đã được tạo trước.

Với Kafka, destination thường là topic; việc tạo topic có thể phụ thuộc cấu hình broker, quyền ACL và chính sách quản trị. Với RabbitMQ, binder làm việc với exchange, queue và binding giữa chúng; số queue có thể tăng theo group hoặc cấu hình consumer. Với Pulsar, destination thường là topic và subscription có vòng đời riêng.

Eviction khỏi cache của ứng dụng không nên được dùng như tín hiệu xóa tài nguyên broker. Nếu cần xóa topic, queue hoặc subscription, hãy dùng quy trình provisioning/deprovisioning riêng có kiểm soát, xem xét retention, consumer đang hoạt động và khả năng khôi phục dữ liệu.

## 11. An toàn và phân quyền khi chọn destination

Dynamic destination tạo ra một ranh giới quan trọng: dữ liệu đầu vào có thể ảnh hưởng nơi message được gửi. Hãy thiết kế lớp định tuyến như một phần của chính sách truy cập:

1. Xác thực người gọi trước khi chấp nhận yêu cầu gửi.
2. Kiểm tra người gọi có quyền phát tới vùng, tenant hoặc loại sự kiện tương ứng.
3. Ánh xạ giá trị bên ngoài sang tên destination nội bộ đã định nghĩa.
4. Từ chối tên không nằm trong mapping và allowlist.
5. Không cho client gửi trực tiếp tên topic, exchange hoặc queue nếu họ không được phép quản lý routing.
6. Cấu hình ACL/credential ở broker theo nguyên tắc quyền tối thiểu.
7. Ghi log quyết định định tuyến bằng mã vùng hoặc mã đích đã chuẩn hóa, tránh ghi payload nhạy cảm.

Allowlist ở `spring.cloud.stream.dynamic-destinations` giới hạn destination được bind động trong framework. Nó không tự xác thực người dùng và không thay thế ACL của Kafka, RabbitMQ hoặc Pulsar.

## 12. Theo dõi eviction và hiệu năng

Cache quá nhỏ so với working set có thể gây churn: binding liên tục bị loại rồi tạo lại. Cache quá lớn lại giữ nhiều binding và tài nguyên trong tiến trình hơn mức cần thiết. Cần theo dõi các dấu hiệu sau:

- Số destination động khác nhau được dùng trong một khoảng thời gian.
- Tần suất tạo binding mới và thời gian bind thành công.
- Tần suất eviction hoặc dấu hiệu một destination thường xuyên phải tạo lại.
- Mức sử dụng heap và số channel/binding đang hoạt động.
- Tỷ lệ gửi thất bại, độ trễ gửi và lỗi provisioning từ broker.
- Số topic, queue, exchange hoặc subscription thực tế trên broker.

Không nên chỉ tăng cache size khi thấy latency tăng. Trước tiên hãy xác định latency đến từ việc tạo lại binding, kết nối broker, serialization, broker quá tải hay lỗi mạng. Nếu nguyên nhân là số lượng destination tăng không kiểm soát, hãy giảm cardinality bằng mapping và allowlist.

## 13. Kiểm thử giới hạn destination

Nên có kiểm thử cho cả lớp ánh xạ nghiệp vụ và hành vi gửi:

### Unit test cho mapping

Kiểm tra khóa hợp lệ trả về đúng tên destination, còn khóa không hợp lệ bị từ chối. Đây là cách phát hiện sớm lỗi định tuyến và ngăn đầu vào tùy ý trở thành tên destination.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.function.StreamBridge;

record OrderCreated(String orderId) {}

class RegionalOrderPublisherTest {

    @Test
    void rejectsUnknownRegion() {
        StreamBridge bridge = org.mockito.Mockito.mock(StreamBridge.class);
        RegionalOrderPublisher publisher = new RegionalOrderPublisher(bridge);

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("unknown", new OrderCreated("O-1")));
    }
}
```

Đoạn mã là khung minh họa; constructor và record của dự án cần khớp với model thực tế. Có thể bổ sung test xác minh vùng hợp lệ gọi `streamBridge.send` đúng destination.

### Kiểm thử cấu hình allowlist

Khởi tạo application context với danh sách `dynamic-destinations` và xác minh gửi tới destination nằm trong danh sách hoạt động, còn tên ngoài danh sách bị từ chối khi binder thực hiện bind động. Kiểm thử này nên chạy với phiên bản Spring Cloud Stream và binder mà ứng dụng sử dụng.

### Kiểm thử cache và broker

Trong integration test, gửi luân phiên tới số destination lớn hơn cache size, sau đó gửi lại destination đã dùng trước đó. Xác minh ứng dụng vẫn gửi được và quan sát chi phí tạo lại binding. Không dùng test binder để kết luận tài nguyên broker được tạo/xóa đúng, vì provisioning và vòng đời tài nguyên cần được kiểm tra với broker thật hoặc môi trường tương đương.

## 14. Quy trình lựa chọn và vận hành

Khi thiết kế một luồng dùng destination động, hãy thực hiện theo trình tự:

1. Xác định có thật sự cần destination động hay có thể dùng output binding cố định.
2. Xác định tập destination hợp lệ và ai có quyền thay đổi tập đó.
3. Ánh xạ dữ liệu đầu vào sang destination chuẩn hóa; từ chối giá trị không hợp lệ.
4. Cấu hình `spring.cloud.stream.dynamic-destinations` để giới hạn tên có thể bind.
5. Đo working set và chọn `spring.cloud.stream.dynamic-destination-cache-size` phù hợp.
6. Xác định binder có tự provision destination không và quyền broker cần có.
7. Kiểm thử eviction, tạo lại binding, lỗi gửi và scale-out.
8. Theo dõi cache churn, heap, latency và số tài nguyên broker.
9. Quản lý việc tạo/xóa tài nguyên broker bằng quy trình riêng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages: StreamBridge and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Configuration Properties — dynamic-destination-cache-size và dynamic-destinations](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)

Hãy đối chiếu tài liệu của release train mà dự án đang sử dụng trước khi áp dụng cấu hình vào production, vì thuộc tính và hành vi binder có thể thay đổi giữa các phiên bản.

## Kết luận

`spring.cloud.stream.dynamic-destination-cache-size` giới hạn số output binding động được giữ trong cache LRU của mỗi instance; mặc định là 10. `spring.cloud.stream.dynamic-destinations` giới hạn tên destination được phép bind động khi được cấu hình. Cache size, allowlist size và tổng tài nguyên broker là ba khái niệm riêng. Kết hợp allowlist, ánh xạ đầu vào sang tập đích hữu hạn, capacity planning theo working set và quản lý provisioning riêng giúp `StreamBridge` định tuyến linh hoạt mà vẫn kiểm soát được bộ nhớ, hiệu năng và số lượng destination.
