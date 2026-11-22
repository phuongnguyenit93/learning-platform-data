# Index name động bằng biểu thức và IndexCoordinates

Trong Spring Data Elasticsearch, một entity thường được ánh xạ tới một index thông qua annotation `@Document`. Cách khai báo đơn giản nhất là dùng một tên cố định:

```java
@Document(indexName = "orders")
public class Order {
    // fields
}
```

Cách này phù hợp khi mọi document của entity đều được lưu trong cùng một index. Tuy nhiên, có những ứng dụng cần chọn index theo môi trường triển khai, tenant, ngày tạo dữ liệu hoặc một quy tắc phân vùng. Khi đó cần hiểu hai cơ chế riêng:

- **Biểu thức trong `@Document(indexName = ...)`** cho phép tên index được xác định bằng cấu hình hoặc Spring Expression Language (SpEL) khi Spring Data xây dựng metadata của entity.
- **`IndexCoordinates`** cho phép truyền index đích rõ ràng vào từng thao tác của `ElasticsearchOperations`, nhờ đó một entity có thể được ghi, đọc hoặc tìm kiếm trên các index khác nhau tùy theo ngữ cảnh của request.

Hai cơ chế này giải quyết hai nhu cầu khác nhau. Biểu thức annotation thích hợp với tên index ổn định theo cấu hình ứng dụng; `IndexCoordinates` thích hợp khi index đích cần thay đổi theo từng thao tác. Không nên dùng biểu thức annotation như một cách lấy tenant hiện tại cho mỗi request, vì metadata của entity thường được tạo và giữ lại trong vòng đời ứng dụng.

## 1. Index name trong metadata của entity

Spring Data Elasticsearch sử dụng mapping metadata để chuyển đổi object Java thành document Elasticsearch. Annotation `@Document` cung cấp các thông tin cấp entity, trong đó có tên index.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Double)
    private Double total;

    // constructors, getters and setters
}
```

Với khai báo trên, Spring Data dùng index `orders` làm index mặc định của entity `Order`. Những thao tác repository thông thường như:

```java
orderRepository.save(order);
orderRepository.findById("O-1001");
orderRepository.findAll();
```

được thực hiện theo metadata của entity. Repository không nhận một tham số index đích riêng cho mỗi lần gọi; tên index được xác định từ cấu hình mapping của entity và cơ chế repository.

Đây là lựa chọn phù hợp nếu:

- Ứng dụng có một index logic cho entity.
- Mỗi môi trường có thể cấu hình một tên index khác nhau khi khởi động.
- Repository là abstraction chính và không cần chọn index theo từng request.
- Việc phân vùng được quản lý bằng alias hoặc cơ chế index của Elasticsearch.

Khi cần một entity được lưu vào nhiều index theo thời gian hoặc theo tenant, chỉ thay đổi giá trị `@Document` không đủ để biểu diễn lựa chọn động theo từng lần gọi. Khi đó nên chuyển sang thao tác có chỉ định `IndexCoordinates`.

## 2. Dùng SpEL trong thuộc tính indexName

Spring Data Elasticsearch hỗ trợ biểu thức trong `indexName` của `@Document`. Biểu thức được viết theo cú pháp Spring Expression Language, đặt trong `#{...}`.

Ví dụ, tạo một bean cung cấp tên index theo cấu hình triển khai:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component("indexNameProvider")
public class IndexNameProvider {

    private final String ordersIndex;

    public IndexNameProvider(
            @Value("${app.elasticsearch.orders-index:orders}") String ordersIndex) {
        this.ordersIndex = ordersIndex;
    }

    public String ordersIndex() {
        return ordersIndex;
    }
}
```

Sau đó tham chiếu bean trong annotation:

```java
@Document(indexName = "#{@indexNameProvider.ordersIndex()}")
public class Order {
    // fields
}
```

Trong ví dụ:

- `@Value("${app.elasticsearch.orders-index:orders}")` đọc property `app.elasticsearch.orders-index`; nếu không có thì dùng `orders`.
- `@indexNameProvider` tham chiếu Spring bean có tên `indexNameProvider`.
- `ordersIndex()` trả về tên index được dùng trong mapping metadata.

Có thể cấu hình theo từng môi trường:

```yaml
# application.yml
app:
  elasticsearch:
    orders-index: orders
```

```yaml
# application-prod.yml
app:
  elasticsearch:
    orders-index: orders-prod
```

Khi chạy với profile production, Spring nạp property tương ứng và metadata của entity sử dụng tên index đã được cấu hình.

### 2.1. Phân biệt placeholder và SpEL

Trong ví dụ trên có hai cú pháp khác nhau:

| Cú pháp | Cơ chế | Ví dụ |
|---|---|---|
| `${...}` | Spring property placeholder | `${app.elasticsearch.orders-index:orders}` |
| `#{...}` | Spring Expression Language | `#{@indexNameProvider.ordersIndex()}` |

Placeholder lấy giá trị từ cấu hình như `application.yml`, biến môi trường hoặc property source. SpEL có thể tính một biểu thức, gọi method trên bean hoặc tham chiếu giá trị trong Spring context.

Có thể kết hợp hai cơ chế: bean nhận property qua `@Value`, sau đó annotation gọi bean bằng SpEL. Cách này giúp phần cấu hình tên index nằm ở một nơi và entity vẫn giữ metadata dễ đọc.

### 2.2. Thời điểm đánh giá biểu thức

Một điểm quan trọng là biểu thức trong `@Document` thuộc metadata của entity. Spring Data thường xây dựng và cache metadata trong vòng đời application context. Vì vậy, hãy coi tên index từ biểu thức annotation là một giá trị cấu hình ổn định cho ứng dụng đang chạy.

Không nên viết bean có method đọc tenant hiện tại từ request context rồi dùng method đó trong `@Document`, với kỳ vọng mỗi request sẽ nhận một index khác nhau. Metadata có thể đã được đánh giá trước đó và dùng chung giữa các request. Kết quả có thể là tất cả request sử dụng cùng index, hoặc hành vi phụ thuộc vào thời điểm metadata được khởi tạo.

Nếu index cần thay đổi theo tenant, ngày hoặc một thuộc tính của từng thao tác, hãy tính tên index ở service và truyền bằng `IndexCoordinates`.

### 2.3. Khi nào nên dùng biểu thức annotation?

Biểu thức annotation phù hợp với các giá trị ổn định như:

- Tên index khác nhau giữa môi trường local, test, staging và production.
- Tên index có suffix theo một cấu hình triển khai.
- Tên index được cung cấp từ một bean cấu hình ở thời điểm khởi tạo ứng dụng.

Không dùng nó làm cơ chế phân tuyến request động theo tenant hoặc user. Cũng không nên đưa dữ liệu đầu vào từ request trực tiếp vào biểu thức SpEL; tên index cần được xác định và kiểm soát bởi ứng dụng.

## 3. IndexCoordinates là gì?

`IndexCoordinates` là kiểu dữ liệu của Spring Data Elasticsearch đại diện cho một hoặc nhiều index name mà một thao tác sẽ nhắm tới. Thay vì lấy index đích ngầm từ `@Document`, code có thể truyền rõ index cần sử dụng.

Import:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
```

Tạo một đối tượng:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-11");
```

Giá trị `orders-2026-11` là tên index mà thao tác sẽ sử dụng. `IndexCoordinates` không tự tạo index, không lưu document và không thực hiện truy vấn; nó chỉ mô tả đích index cho các API nhận tham số này.

Các overload trong `ElasticsearchOperations` cho phép truyền coordinates tường minh. Ví dụ:

```java
operations.save(order, coordinates);

operations.get("O-1001", Order.class, coordinates);

operations.search(query, Order.class, coordinates);

operations.delete("O-1001", Order.class, coordinates);
```

Tên method hoặc overload có thể khác theo thế hệ Spring Data Elasticsearch mà dự án sử dụng. Hãy kiểm tra API của dependency thực tế nếu project đang dùng một phiên bản cũ. Nguyên tắc chung vẫn là: chọn index bằng `IndexCoordinates` ở thao tác cần định tuyến động.

## 4. Dùng IndexCoordinates để ghi vào index động

Giả sử ứng dụng lưu đơn hàng theo tháng. Một service có thể xác định index dựa trên ngày nghiệp vụ:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {

    private static final DateTimeFormatter INDEX_MONTH =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public OrderSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(Order order, LocalDate businessDate) {
        String indexName = "orders-" + businessDate.format(INDEX_MONTH);
        IndexCoordinates coordinates = IndexCoordinates.of(indexName);

        return operations.save(order, coordinates);
    }
}
```

Ví dụ:

- Đơn hàng có ngày nghiệp vụ 2026-11-13 được ghi vào `orders-2026-11`.
- Đơn hàng có ngày nghiệp vụ 2026-12-02 được ghi vào `orders-2026-12`.

Cùng một class `Order` vẫn được dùng để chuyển đổi document. `IndexCoordinates` quyết định document được ghi vào index nào ở lần gọi đó.

Trong thực tế, nên dùng ngày nghiệp vụ đã được xác định rõ, có timezone thống nhất. Không nên tùy tiện lấy ngày trên máy chủ nếu dữ liệu có thể đến từ nhiều múi giờ hoặc cần quy tắc chốt ngày theo nghiệp vụ.

### 4.1. Đọc lại từ đúng index

Khi ghi theo index tháng, thao tác đọc theo ID cũng phải xác định đúng index:

```java
public Order findById(String id, LocalDate businessDate) {
    String indexName = "orders-" + businessDate.format(INDEX_MONTH);
    IndexCoordinates coordinates = IndexCoordinates.of(indexName);

    return operations.get(id, Order.class, coordinates);
}
```

ID của document chỉ cần duy nhất trong phạm vi index. Hai index khác nhau có thể chứa document cùng `_id`. Vì vậy, chỉ có ID không phải lúc nào cũng đủ để xác định document; ứng dụng cần biết index hoặc có một quy tắc tìm kiếm phù hợp.

Nếu không biết ngày tạo đơn hàng, có thể tìm trên alias hoặc tập index phù hợp thay vì đoán một index tháng.

## 5. Tìm kiếm trên index được chọn tại runtime

Cũng có thể xác định index đích cho Search API:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<Order> searchOrders(
        Query query,
        String tenantIndex) {

    IndexCoordinates coordinates = IndexCoordinates.of(tenantIndex);

    return operations.search(query, Order.class, coordinates);
}
```

Ở đây:

- `Query` mô tả điều kiện tìm kiếm.
- `Order.class` cho biết kiểu Java cần chuyển đổi kết quả.
- `IndexCoordinates` chỉ định index hoặc các index được tìm kiếm.

Có thể dùng cùng query trên nhiều index nếu mapping tương thích:

```java
IndexCoordinates coordinates = IndexCoordinates.of(
    "orders-2026-10",
    "orders-2026-11",
    "orders-2026-12"
);

SearchHits<Order> hits =
    operations.search(query, Order.class, coordinates);
```

Hoặc dùng một index pattern nếu API và quyền của Elasticsearch cho phép:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-*");
```

Truy vấn nhiều index cần chú ý tính nhất quán của mapping. Nếu cùng một field có kiểu khác nhau giữa các index, truy vấn, sort hoặc aggregation có thể lỗi hoặc cho kết quả không mong muốn. Khi cần tìm kiếm xuyên nhiều index, hãy duy trì mapping tương thích hoặc dùng alias được quản lý rõ ràng.

## 6. Kết hợp entity metadata và IndexCoordinates

Một entity có thể vẫn khai báo metadata chuẩn:

```java
@Document(indexName = "orders")
public class Order {
    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Double)
    private Double total;
}
```

Trong service, có thể dùng metadata của class để chuyển đổi object, nhưng chọn index đích bằng coordinates:

```java
IndexCoordinates target = IndexCoordinates.of("orders-2026-11");

Order saved = operations.save(order, target);
```

Hai thành phần có vai trò riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `@Document` | Khai báo metadata của entity, ví dụ tên index mặc định và tùy chọn mapping. |
| `@Id`, `@Field` | Mô tả cách thuộc tính Java được ánh xạ vào document và field. |
| `IndexCoordinates` | Chỉ định index đích cho một thao tác cụ thể. |
| `ElasticsearchOperations` | Thực hiện save, get, search, delete và các thao tác khác. |

Không nên nhầm tên index mặc định trong annotation với index được truyền vào một overload có `IndexCoordinates`. Khi gọi overload tường minh, coordinates là thông tin chọn đích của thao tác đó.

## 7. Repository và giới hạn khi dùng index động

Spring Data Elasticsearch repository rất thuận tiện khi một entity có một index logic ổn định:

```java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
```

Các method như `save`, `findById`, `findAll` sử dụng mapping metadata của `Order`. Repository thông thường không cung cấp tham số `IndexCoordinates` cho từng lần gọi.

Nếu cần định tuyến theo tenant hoặc thời gian, có thể giữ repository cho các thao tác trên index cố định và tạo service riêng dùng `ElasticsearchOperations` cho luồng động. Ví dụ:

```java
@Service
public class TenantOrderService {

    private final ElasticsearchOperations operations;

    public TenantOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(String tenantId, Order order) {
        String indexName = "orders-" + validateTenantId(tenantId);
        return operations.save(
            order,
            IndexCoordinates.of(indexName)
        );
    }

    private String validateTenantId(String tenantId) {
        if (tenantId == null || !tenantId.matches("[a-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenant id");
        }
        return tenantId;
    }
}
```

Đây là ví dụ minh họa việc định tuyến theo tenant. Ứng dụng thật cần lấy tenant từ danh tính đã xác thực và quyền truy cập của người dùng, sau đó kiểm tra tenant có thuộc phạm vi được phép hay không. Không tin một chuỗi tenant tùy ý do client gửi lên.

Không cần tạo một repository Java riêng cho mỗi tenant. Có thể dùng một service chung và truyền index đích đã được kiểm tra. Cách này giảm số lượng bean và tránh việc cấu hình repository phụ thuộc vào số tenant.

## 8. Tạo index và mapping khi dùng IndexCoordinates

`IndexCoordinates` chỉ định tên index, nhưng không đảm bảo index đó đã tồn tại. Nếu ứng dụng ghi vào một index chưa được tạo, kết quả phụ thuộc cấu hình auto-create của Elasticsearch và quyền của tài khoản; không nên dựa vào việc Elasticsearch tự tạo index với mapping mặc định.

Một quy trình quản lý index động thường cần:

1. Tạo tên index hợp lệ.
2. Kiểm tra index đã tồn tại hay chưa.
3. Nếu chưa, tạo index với settings và mapping đúng.
4. Ghi document bằng `ElasticsearchOperations` cùng `IndexCoordinates`.

Ví dụ khung thao tác kiểm tra/tạo index:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-11");
IndexOperations indexOps = operations.indexOps(coordinates);

if (!indexOps.exists()) {
    indexOps.create();
}
```

Đoạn code trên chỉ minh họa việc kiểm tra và tạo index. Trong ứng dụng thực tế, cần thiết lập mapping trước khi ghi dữ liệu. Có thể tạo mapping từ metadata của entity rồi gửi vào `IndexOperations` gắn với coordinates đích, tùy API của phiên bản Spring Data đang dùng:

```java
Document mapping = operations.indexOps(Order.class).createMapping();

IndexOperations targetIndexOps = operations.indexOps(coordinates);
if (!targetIndexOps.exists()) {
    targetIndexOps.create();
    targetIndexOps.putMapping(mapping);
}
```

Trong ví dụ, mapping được sinh từ entity `Order`, còn `targetIndexOps` thao tác trên index động. Kiểm tra chữ ký method của phiên bản Spring Data cụ thể nếu API có khác biệt. Với hệ thống production, quy trình tạo index/mapping thường nên được quản lý tập trung hoặc thực hiện trước khi luồng ghi bắt đầu.

### 8.1. Tránh race condition khi nhiều request cùng tạo index

Nếu nhiều request đầu tiên cùng kiểm tra một index chưa tồn tại, chúng có thể đồng thời cố tạo index. Một request tạo thành công, request còn lại nhận lỗi index đã tồn tại.

Không nên coi lỗi đó luôn là lỗi nghiêm trọng hoặc bỏ qua mọi lỗi tạo index. Cần phân biệt phản hồi “resource already exists” với lỗi quyền, mapping, kết nối hoặc cấu hình. Một cách an toàn hơn là quản lý index creation bằng bước khởi tạo có đồng bộ, migration job hoặc một thành phần provisioning riêng.

### 8.2. Không dựa vào createIndex của @Document cho mọi index động

`@Document(createIndex = true)` gắn với metadata của entity và index được xác định từ metadata đó. Khi code dùng `IndexCoordinates` để ghi vào nhiều index khác nhau, đừng giả định annotation sẽ tự tạo từng index động cùng mapping tương ứng.

Hãy chủ động quản lý lifecycle cho các index động, bao gồm settings, mapping, alias, rollover, retention và quyền truy cập.

## 9. IndexCoordinates và alias

Một alias là tên logic trỏ tới một hoặc nhiều index thật. Thay vì để ứng dụng biết tên index vật lý, có thể cho ứng dụng thao tác qua alias:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-write");
operations.save(order, coordinates);
```

Với đọc dữ liệu, alias có thể trỏ tới nhiều index:

```java
IndexCoordinates readCoordinates = IndexCoordinates.of("orders-read");
SearchHits<Order> hits =
    operations.search(query, Order.class, readCoordinates);
```

Điều này hữu ích khi dữ liệu được chia theo tháng nhưng ứng dụng cần tìm kiếm trên toàn bộ lịch sử. Alias giúp tách tên logic mà ứng dụng sử dụng khỏi tên index vật lý.

Cần lưu ý:

- Alias dùng cho ghi phải có một write index rõ ràng nếu nó trỏ tới nhiều index.
- Alias đọc có thể trỏ tới nhiều index, nhưng mapping của các index nên tương thích.
- Việc chuyển alias sang index mới cần được thực hiện có kiểm soát để tránh ghi nhầm hoặc đọc thiếu dữ liệu.
- `IndexCoordinates` chỉ mang tên alias; Elasticsearch quyết định alias đó phân giải tới index nào.

Với dữ liệu thời gian, alias kết hợp rollover và Index Lifecycle Management (ILM) thường dễ vận hành hơn việc tự tính index theo ngày ở mọi nơi trong code. Data stream cũng là lựa chọn phù hợp cho một số workload append-oriented và time-series.

## 10. Quy tắc đặt tên index động

Tên index thường được ghép từ prefix và một phần định danh như tenant hoặc tháng. Cần kiểm soát phần động để tránh tên không hợp lệ hoặc truy cập sai phạm vi dữ liệu.

Ví dụ:

```java
String indexName = "orders-" + yearMonth;
IndexCoordinates coordinates = IndexCoordinates.of(indexName);
```

Các nguyên tắc:

- Dùng chữ thường.
- Giới hạn ký tự cho phép và độ dài.
- Không đưa khoảng trắng hoặc ký tự bị Elasticsearch cấm vào tên index.
- Không cho phép tên bắt đầu bằng các ký tự bị cấm như `-`, `_` hoặc `+`.
- Không nối trực tiếp dữ liệu chưa kiểm tra từ HTTP request.
- Không cho phép user tự chọn wildcard nếu nghiệp vụ không cho phép truy vấn nhiều index.
- Giữ quy tắc đặt tên nhất quán giữa ghi, đọc, backup và retention.

Ví dụ validator đơn giản cho phần tenant:

```java
private String validateTenantId(String tenantId) {
    if (tenantId == null || !tenantId.matches("[a-z0-9-]{1,40}")) {
        throw new IllegalArgumentException("Invalid tenant id");
    }
    return tenantId;
}
```

Sau đó ứng dụng tự ghép prefix cố định:

```java
String indexName = "orders-" + validateTenantId(tenantId);
```

Cách này tránh việc người dùng truyền một tên index bất kỳ hoặc một wildcard để truy cập dữ liệu ngoài tenant của họ. Việc xác thực định dạng tên vẫn phải đi cùng kiểm tra quyền truy cập tenant.

## 11. Chọn chiến lược index theo bài toán

Không phải cứ có nhiều tenant hoặc dữ liệu lớn là phải tạo một index cho mỗi tenant hay mỗi ngày. Mỗi chiến lược có chi phí vận hành riêng.

| Chiến lược | Ví dụ | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|---|
| Một index cố định | `orders` | Dữ liệu vừa phải, mapping và quyền truy cập thống nhất. | Đơn giản; cần thiết kế shard và lifecycle phù hợp. |
| Index theo môi trường | `orders-dev`, `orders-prod` | Cô lập dữ liệu giữa môi trường. | Cấu hình rõ ràng, tránh ghi nhầm môi trường. |
| Index theo thời gian | `orders-2026-11` | Dữ liệu tăng liên tục, cần retention theo thời gian. | Quản lý số lượng index, mapping và truy vấn nhiều index. |
| Index theo tenant | `orders-tenant-a` | Cần mức cô lập dữ liệu hoặc lifecycle riêng theo tenant. | Quá nhiều tenant có thể tạo quá nhiều shard/index và tăng chi phí quản trị. |
| Alias hoặc data stream | `orders-read`, `orders-write` | Cần tên logic ổn định, rollover hoặc tìm kiếm trên nhiều backing index. | Phải quản lý alias, write index, template và lifecycle. |

Với số lượng tenant lớn, index riêng cho mỗi tenant có thể tạo ra nhiều shard nhỏ và tăng gánh nặng cluster. Có thể cân nhắc dùng chung index với field tenant và filter bắt buộc, hoặc kết hợp chiến lược phân vùng theo nhóm tenant. Quyết định này liên quan tới bảo mật, dung lượng, tải và yêu cầu vận hành; không chỉ là lựa chọn cú pháp API.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ghi vẫn vào index mặc định dù đã có logic tenant | Đang gọi repository hoặc overload không nhận `IndexCoordinates`. | Kiểm tra method thực tế được gọi và truyền coordinates vào thao tác. |
| SpEL trả về tên index không mong đợi | Property/profile sai hoặc bean cung cấp tên chưa đúng. | Kiểm tra property đã nạp, bean name và thời điểm metadata được khởi tạo. |
| Tenant khác nhau nhưng cùng dùng một index | Dùng tenant context trong `@Document` như thể nó được đánh giá mỗi request. | Chuyển lựa chọn tenant sang service và `IndexCoordinates`. |
| Index động chưa tồn tại | Coordinates chỉ định tên, không tự tạo index. | Provision index và mapping trước khi ghi. |
| Document ghi được nhưng tìm kiếm không thấy | Đọc ở index khác hoặc alias chưa trỏ tới index mới. | Ghi log index đích, kiểm tra alias và truy vấn trực tiếp. |
| Truy vấn nhiều index báo lỗi mapping | Cùng field có kiểu hoặc cấu trúc khác nhau. | Kiểm tra mapping từng index và thống nhất schema. |
| Ghi qua alias lỗi | Alias trỏ nhiều index nhưng không có write index phù hợp. | Kiểm tra alias và cấu hình write index. |
| Có thể truy cập index của tenant khác | Tên index lấy từ input mà không kiểm tra quyền. | Lấy tenant từ principal đã xác thực và áp dụng authorization ở service. |
| Nhiều request đồng thời lỗi khi tạo index | Race condition trong bước kiểm tra và tạo. | Dùng provisioning đồng bộ hoặc xử lý riêng lỗi already-exists. |

Khi debug, hãy ghi nhận index hoặc alias thực tế mà request dùng. Biết query đúng nhưng chưa biết nó chạy trên index nào thì vẫn chưa đủ để khoanh vùng lỗi.

## 13. Ví dụ tổng hợp: service lưu và tìm đơn hàng theo tháng

Ví dụ sau kết hợp entity metadata, service chọn index và `IndexCoordinates`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class MonthlyOrderService {

    private static final DateTimeFormatter MONTH_FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public MonthlyOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    private IndexCoordinates indexFor(LocalDate date) {
        String indexName = "orders-" + date.format(MONTH_FORMAT);
        return IndexCoordinates.of(indexName);
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(order, indexFor(businessDate));
    }

    public Order findById(String id, LocalDate businessDate) {
        return operations.get(id, Order.class, indexFor(businessDate));
    }

    public SearchHits<Order> search(
            Query query,
            LocalDate businessDate) {
        return operations.search(query, Order.class, indexFor(businessDate));
    }
}
```

Điểm chính của thiết kế:

- Quy tắc tính index nằm trong một method `indexFor`, tránh ghép tên rải rác trong nhiều method.
- Cùng một entity `Order` được dùng cho nhiều index.
- Mỗi thao tác nhận index đích rõ ràng.
- Service chịu trách nhiệm xác định ngày nghiệp vụ và index tương ứng.
- Lifecycle và mapping của từng index cần được provision phù hợp trước khi sử dụng.

Trong ứng dụng thật, nếu cần tìm một đơn hàng mà không biết tháng, có thể tra một khoá định tuyến riêng, tìm qua alias hoặc truy vấn một tập index được giới hạn. Không nên mở wildcard quá rộng nếu dữ liệu lớn hoặc quyền truy cập không cho phép.

## 14. Tóm tắt lựa chọn API

| Nhu cầu | Cách thực hiện |
|---|---|
| Một index cố định cho entity | `@Document(indexName = "orders")` |
| Tên index theo cấu hình môi trường lúc ứng dụng khởi động | Dùng property hoặc SpEL trong `@Document(indexName = ...)` |
| Chọn index theo tenant trong từng request | Tính tên đã kiểm tra trong service và dùng `IndexCoordinates.of(...)` |
| Chọn index theo tháng/ngày | Tính index từ ngày nghiệp vụ rồi truyền coordinates |
| Ghi hoặc đọc qua alias | Truyền tên alias vào `IndexCoordinates` |
| Search nhiều index | Tạo coordinates với nhiều tên hoặc pattern được kiểm soát |
| Quản lý index động | Dùng `IndexOperations` cùng coordinates, tạo mapping và lifecycle có chủ đích |

Biểu thức SpEL giúp metadata entity nhận tên index từ cấu hình ổn định. `IndexCoordinates` giúp từng thao tác chọn index đích ở runtime. Khi cần phân vùng theo tenant hoặc thời gian, hãy đặt quy tắc chọn index trong service, xác thực đầu vào, truyền coordinates rõ ràng và quản lý index/mapping/alias như một phần của lifecycle dữ liệu.

