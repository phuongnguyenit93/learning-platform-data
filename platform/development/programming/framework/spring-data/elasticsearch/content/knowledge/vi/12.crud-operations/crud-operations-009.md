# Kiểm soát index đích bằng IndexCoordinates khi dùng Operations

Spring Data Elasticsearch thường lấy tên index mặc định từ annotation @Document của entity. Cách này thuận tiện khi mọi document của một loại đều nằm trong cùng một index. Nhưng với dữ liệu được phân vùng theo tháng, tenant, môi trường hoặc một quy tắc nghiệp vụ khác, một entity có thể cần được ghi và đọc từ nhiều index.

ElasticsearchOperations hỗ trợ truyền IndexCoordinates vào từng thao tác. Nhờ đó service có thể quyết định index đích tại thời điểm thực hiện CRUD, thay vì phụ thuộc hoàn toàn vào tên index mặc định trong entity metadata.

IndexCoordinates là đối tượng mô tả index hoặc alias mà một thao tác sẽ sử dụng. Nó không tự tạo index, không thay đổi mapping của entity và không lưu lựa chọn đó vào object Java. Muốn thao tác đọc lại đúng document, ứng dụng phải dùng đúng index hoặc alias tương ứng.

## 1. Index mặc định từ entity metadata

Một entity thường khai báo index bằng @Document:

~~~java
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

    @Field(type = FieldType.Long)
    private Long totalInCents;

    // constructors, getters and setters
}
~~~

Khi gọi thao tác không truyền IndexCoordinates:

~~~java
operations.save(order);

Order saved = operations.get(
    order.getId(),
    Order.class
);

boolean exists = operations.exists(
    order.getId(),
    Order.class
);
~~~

Spring Data sử dụng index metadata của Order, trong ví dụ là orders. Đây là cách phù hợp khi entity luôn thao tác trên một index logic cố định.

Nếu cần ghi một đơn hàng vào orders-2026-11, có thể truyền index đích trực tiếp:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

operations.save(order, target);
~~~

Lúc này thao tác save dùng index được chỉ định trong target. Tên index mặc định trên @Document vẫn là metadata của entity và vẫn được dùng cho những thao tác khác không truyền coordinates.

Hai cách gọi có ý nghĩa khác nhau:

| Cách gọi | Index được chọn |
|---|---|
| operations.save(order) | Index mặc định trong @Document |
| operations.save(order, coordinates) | Index/alias trong IndexCoordinates |
| operations.get(id, Order.class) | Index mặc định trong @Document |
| operations.get(id, Order.class, coordinates) | Index/alias được truyền rõ ràng |

Hãy thống nhất cách chọn index giữa các thao tác ghi, đọc, kiểm tra tồn tại, đếm và xóa. Ghi vào một index nhưng đọc từ index mặc định là nguyên nhân phổ biến khiến ứng dụng tưởng document đã mất.

## 2. IndexCoordinates là gì?

IndexCoordinates thuộc package:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
~~~

Tạo coordinates cho một index:

~~~java
IndexCoordinates index =
    IndexCoordinates.of("orders-2026-11");
~~~

Có thể dùng tên alias:

~~~java
IndexCoordinates index =
    IndexCoordinates.of("orders-write");
~~~

Và với thao tác đọc nhiều index, có thể chỉ định nhiều tên index:

~~~java
IndexCoordinates indexes = IndexCoordinates.of(
    "orders-2026-10",
    "orders-2026-11",
    "orders-2026-12"
);
~~~

IndexCoordinates chỉ mang thông tin đích. Elasticsearch mới là nơi phân giải tên index hoặc alias và thực hiện request.

Nên phân biệt ba khái niệm:

- **Entity metadata**: mô tả domain type, ID, field mapping và index mặc định.
- **IndexCoordinates**: chỉ định index/alias cho một lần gọi Operations.
- **IndexOperations**: API quản lý index như kiểm tra tồn tại, tạo index, mapping, settings, refresh và xóa index.

IndexCoordinates không phải một lệnh tạo index. Truyền một tên index chưa tồn tại vào save không thay thế quy trình provisioning và mapping cần thiết.

## 3. Ghi document vào index được chọn

Ví dụ service chọn index theo tháng nghiệp vụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class MonthlyOrderService {

    private static final DateTimeFormatter MONTH_FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public MonthlyOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    private IndexCoordinates indexFor(LocalDate businessDate) {
        String indexName =
            "orders-" + businessDate.format(MONTH_FORMAT);

        return IndexCoordinates.of(indexName);
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(order, indexFor(businessDate));
    }
}
~~~

Ví dụ:

- Đơn hàng có ngày nghiệp vụ 2026-11-13 được ghi vào orders-2026-11.
- Đơn hàng có ngày nghiệp vụ 2026-12-02 được ghi vào orders-2026-12.

Entity Order vẫn được dùng để chuyển đổi object thành document. IndexCoordinates quyết định nơi document được ghi trong lần gọi đó.

Nên chọn ngày nghiệp vụ một cách nhất quán. Nếu dữ liệu đến từ nhiều múi giờ, hãy xác định timezone trước khi chuyển timestamp thành tháng. Không nên lấy ngày mặc định trên máy chủ nếu quy tắc nghiệp vụ dùng một múi giờ khác.

### 3.1. Ghi nhiều document vào cùng index

Operations cũng có các overload ghi collection nhận IndexCoordinates. Ví dụ minh họa:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

List<Order> orders = loadOrdersForNovember();

operations.save(orders, target);
~~~

Tất cả document trong collection được gửi tới index đã chọn. Nếu mỗi document thuộc một tháng khác nhau, hãy nhóm theo tháng và ghi từng nhóm vào index tương ứng, hoặc thực hiện từng thao tác với coordinates được tính từ dữ liệu.

Đừng gom document thuộc nhiều partition vào một lệnh ghi nhưng chỉ truyền một index đích chung nếu quy tắc lưu trữ yêu cầu chúng nằm ở các index khác nhau.

## 4. Đọc document theo ID từ đúng index

Sau khi ghi vào index động, thao tác get cũng phải nhận cùng coordinates:

~~~java
public Order findById(String id, LocalDate businessDate) {
    IndexCoordinates target = indexFor(businessDate);

    return operations.get(
        id,
        Order.class,
        target
    );
}
~~~

Một ID Elasticsearch chỉ cần duy nhất trong phạm vi index. Hai index khác nhau có thể cùng chứa document có _id là O-1001.

Ví dụ:

~~~text
orders-2026-10
    _id = O-1001
    customerId = C-10

orders-2026-11
    _id = O-1001
    customerId = C-25
~~~

Nếu chỉ biết ID mà không biết index, ứng dụng chưa có đủ thông tin để xác định duy nhất document. Cần lưu partition key cùng ID, tra cứu một registry phù hợp hoặc đọc qua alias bao phủ các index cần thiết.

Không nên giả định ID tự động duy nhất trên tất cả index.

### 4.1. Tạo một hàm chọn index dùng chung

Để tránh logic ghép tên index rải rác, đặt quy tắc chọn index vào một thành phần riêng:

~~~java
@Component
public class OrderIndexResolver {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    public IndexCoordinates forDate(LocalDate businessDate) {
        String name = "orders-" + businessDate.format(FORMAT);
        return IndexCoordinates.of(name);
    }
}
~~~

Service dùng cùng resolver cho save, get, exists và delete:

~~~java
@Service
public class OrderService {

    private final ElasticsearchOperations operations;
    private final OrderIndexResolver indexResolver;

    public OrderService(
            ElasticsearchOperations operations,
            OrderIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public Order save(Order order, LocalDate date) {
        return operations.save(order, indexResolver.forDate(date));
    }

    public Order find(String id, LocalDate date) {
        return operations.get(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }

    public boolean exists(String id, LocalDate date) {
        return operations.exists(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }

    public String delete(String id, LocalDate date) {
        return operations.delete(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }
}
~~~

Tên method và overload có thể khác giữa các thế hệ Spring Data Elasticsearch. Đối chiếu chữ ký API với dependency thực tế của project. Nguyên tắc thiết kế là dùng một resolver thống nhất để mọi thao tác nhắm tới cùng partition.

## 5. Kiểm tra tồn tại và xóa theo IndexCoordinates

Khi document nằm trong index động, exists và delete cũng cần chỉ định index đích.

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

boolean found = operations.exists(
    "O-1001",
    Order.class,
    target
);

if (found) {
    operations.delete(
        "O-1001",
        Order.class,
        target
    );
}
~~~

Nếu bỏ coordinates, Spring Data có thể kiểm tra hoặc xóa document trong index mặc định của entity, không phải index tháng 11.

Đây là lý do cần truyền cùng một quy tắc index vào toàn bộ CRUD path:

| Thao tác | API Operations có coordinates |
|---|---|
| Ghi một object | save(entity, indexCoordinates) |
| Ghi collection | save(entities, indexCoordinates) |
| Đọc theo ID | get(id, entityClass, indexCoordinates) |
| Kiểm tra theo ID | exists(id, entityClass, indexCoordinates) |
| Xóa theo ID | delete(id, entityClass, indexCoordinates) |
| Tìm kiếm | search(query, entityClass, indexCoordinates) |
| Đếm | count(query, entityClass, indexCoordinates) |

Hãy kiểm tra overload có sẵn trong version Spring Data Elasticsearch đang dùng. Một số API có thể thay đổi tên tham số hoặc kiểu trả về giữa các phiên bản.

### 5.1. Xóa document khác với xóa index

Cần phân biệt:

~~~java
// Xóa một document theo ID:
operations.delete(id, Order.class, target);

// Quản lý/xóa cả index:
operations.indexOps(target).delete();
~~~

Lệnh thứ nhất xóa document được xác định bởi ID và index. Lệnh thứ hai xóa toàn bộ index được chỉ định. Không dùng IndexOperations.delete() khi chỉ muốn xóa một document.

## 6. Search trên index được chỉ định

Có thể tìm kiếm trong một index động:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

Query query = new CriteriaQuery(
    new Criteria("customerId").is("C-100")
);

SearchHits<Order> hits = operations.search(
    query,
    Order.class,
    target
);
~~~

Ở đây:

- Query mô tả điều kiện tìm kiếm.
- Order.class cho biết kiểu Java dùng để chuyển đổi kết quả.
- IndexCoordinates chỉ định index/alias được tìm kiếm.

Nếu cần tìm dữ liệu qua nhiều tháng, có thể truyền nhiều index:

~~~java
IndexCoordinates history = IndexCoordinates.of(
    "orders-2026-09",
    "orders-2026-10",
    "orders-2026-11"
);

SearchHits<Order> hits = operations.search(
    query,
    Order.class,
    history
);
~~~

Điều này phù hợp khi mapping giữa các index tương thích. Nếu field cùng tên nhưng khác kiểu giữa các index, query, sort hoặc aggregation có thể lỗi hoặc cho kết quả không như mong đợi.

Nên giới hạn số index cần tìm kiếm. Truy vấn wildcard hoặc danh sách quá rộng có thể làm Elasticsearch phải fan out tới nhiều shard và tăng latency.

### 6.1. Count trên index động

Để đếm document theo điều kiện trong một index:

~~~java
long total = operations.count(
    query,
    Order.class,
    IndexCoordinates.of("orders-2026-11")
);
~~~

Nếu cần đếm toàn bộ document trong index, dùng query match-all theo API của phiên bản Spring Data:

~~~java
long total = operations.count(
    Query.findAll(),
    Order.class,
    IndexCoordinates.of("orders-2026-11")
);
~~~

Khi đếm qua nhiều index, truyền coordinates bao gồm đúng các index cần tính. Kết quả là số document trong phạm vi index được phân giải.

Count/Search phụ thuộc refresh visibility. Document vừa ghi có thể chưa xuất hiện trong query cho tới lần refresh tiếp theo. Nếu nghiệp vụ cần kết quả ngay sau khi ghi, hãy xác định refresh policy phù hợp.

## 7. Dùng alias làm index đích

Ứng dụng có thể thao tác qua alias thay vì tên index vật lý:

~~~java
IndexCoordinates writeTarget =
    IndexCoordinates.of("orders-write");

operations.save(order, writeTarget);
~~~

Alias giúp ứng dụng giữ một tên logic ổn định trong khi index vật lý thay đổi theo rollover hoặc migration.

Ví dụ:

~~~text
orders-write  ---> orders-2026-11
orders-read   ---> orders-2026-09
              ---> orders-2026-10
              ---> orders-2026-11
~~~

Ứng dụng ghi qua orders-write và đọc lịch sử qua orders-read.

Một alias đọc có thể trỏ tới nhiều index. Alias ghi cần có write index rõ ràng nếu nó trỏ tới nhiều index. Nếu alias không có write index phù hợp, request ghi có thể bị Elasticsearch từ chối.

Kiểm tra alias bằng REST API:

~~~http
GET /_cat/aliases?v
~~~

Có thể xem metadata của alias:

~~~http
GET /_alias/orders-write
~~~

IndexCoordinates chỉ mang tên alias. Elasticsearch quyết định alias đó trỏ tới index nào và index nào nhận ghi.

## 8. Quản lý index và mapping trước khi ghi

IndexCoordinates không tự tạo index hoặc bảo đảm mapping phù hợp. Với index động, ứng dụng hoặc quy trình provisioning cần tạo index trước khi sử dụng.

Có thể kiểm tra và quản lý index bằng IndexOperations:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

IndexOperations indexOperations =
    operations.indexOps(target);

if (!indexOperations.exists()) {
    indexOperations.create();

    Document mapping =
        operations.indexOps(Order.class).createMapping();

    indexOperations.putMapping(mapping);
}
~~~

Ví dụ này tạo index và áp dụng mapping được sinh từ entity Order. Nếu entity có analyzer, normalizer, custom settings hoặc mapping phức tạp, cần provision đầy đủ settings và mapping trước khi ghi.

Trong các phiên bản hỗ trợ, có thể dùng API tạo index kèm mapping như createWithMapping() trên IndexOperations. Hãy kiểm tra API của phiên bản đang dùng và bảo đảm settings của entity cũng được áp dụng khi cần.

### 8.1. Không để mọi request cùng tạo index

Mẫu kiểm tra rồi tạo:

~~~java
if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

có thể gặp race condition nếu nhiều request đầu tiên chạy đồng thời. Một request tạo thành công, request còn lại nhận lỗi vì index đã tồn tại.

Trong hệ thống production, nên quản lý index creation qua migration, startup provisioning có đồng bộ hoặc một thành phần quản trị riêng. Nếu vẫn tạo ở runtime, hãy xử lý riêng lỗi already-exists và không bỏ qua các lỗi quyền, mapping hay kết nối.

Không nên tạo index mới ở mỗi lần save mà không có chiến lược quản lý số lượng index và lifecycle.

### 8.2. Mapping phải tương thích giữa các index

Cùng một entity có thể được ghi vào nhiều index, nhưng mỗi index phải có mapping tương thích với dữ liệu và query của entity.

Ví dụ, nếu Order.totalInCents là Long:

~~~json
{
  "properties": {
    "totalInCents": {
      "type": "long"
    }
  }
}
~~~

Nếu một index cũ khai báo field này là keyword, việc ghi hoặc query qua entity có thể gặp lỗi hoặc semantics không đồng nhất.

Khi thay đổi mapping, hãy tạo index mới và migrate dữ liệu theo kế hoạch thay vì cho rằng thay đổi annotation Java sẽ cập nhật mọi index hiện có.

## 9. IndexCoordinates và Repository

Repository thông thường sử dụng index metadata của entity:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

Các lời gọi:

~~~java
orderRepository.save(order);
orderRepository.findById(id);
orderRepository.deleteById(id);
~~~

không nhận IndexCoordinates cho từng thao tác. Chúng sử dụng index được xác định từ metadata và repository configuration.

Nếu cần chọn index theo từng request, ElasticsearchOperations là abstraction phù hợp hơn:

~~~java
operations.save(order, target);
operations.get(id, Order.class, target);
~~~

Có thể dùng cả repository và Operations trong cùng ứng dụng:

- Repository phục vụ CRUD trên index logic cố định.
- Operations phục vụ luồng cần chọn index động hoặc query tùy chỉnh.
- Cả hai có thể dùng chung mapping metadata và client nếu được cấu hình như vậy.

Không nên kỳ vọng gọi repository sau khi đã save bằng IndexCoordinates sẽ tự biết document nằm ở index động nào. Nếu dùng hai abstraction, phải xác định rõ index mà mỗi thao tác sẽ sử dụng.

## 10. Chọn index theo tenant

Một trường hợp thường gặp là phân vùng dữ liệu theo tenant:

~~~java
public Order saveForTenant(String tenantId, Order order) {
    String validatedTenant = validateTenantId(tenantId);

    IndexCoordinates target = IndexCoordinates.of(
        "orders-" + validatedTenant
    );

    return operations.save(order, target);
}
~~~

Phần tenant cần được kiểm tra và lấy từ ngữ cảnh đã xác thực. Không nối trực tiếp chuỗi do HTTP client gửi lên vào tên index.

Ví dụ validator đơn giản:

~~~java
private String validateTenantId(String tenantId) {
    if (tenantId == null ||
            !tenantId.matches("[a-z0-9-]{1,40}")) {
        throw new IllegalArgumentException("Invalid tenant id");
    }

    return tenantId;
}
~~~

Validator chỉ kiểm tra định dạng. Service vẫn cần xác nhận người dùng hiện tại có quyền truy cập tenant đó.

Index riêng cho tenant không tự động tạo thành ranh giới bảo mật hoàn chỉnh. Tài khoản Elasticsearch, authorization ở tầng ứng dụng, kiểm tra tenant và quy tắc truy cập phải được thiết kế cùng nhau.

Nếu có hàng chục nghìn tenant, tạo index riêng cho mỗi tenant có thể làm tăng số shard và chi phí quản trị. Hãy cân nhắc dùng index chung với tenant field và filter bắt buộc, hoặc phân vùng theo nhóm tenant nếu phù hợp với tải và yêu cầu cô lập.

## 11. Tên index và dữ liệu đầu vào

Tên index động thường được ghép từ prefix cố định và một phần dữ liệu như tenant hoặc tháng:

~~~java
String indexName = "orders-" + yearMonth;
IndexCoordinates target = IndexCoordinates.of(indexName);
~~~

Một số nguyên tắc:

- Dùng chữ thường.
- Giới hạn ký tự và độ dài.
- Không đưa khoảng trắng hoặc ký tự bị Elasticsearch cấm vào tên index.
- Không để tên bắt đầu bằng ký tự bị cấm như -, _ hoặc +.
- Không cho phép client tùy ý truyền wildcard nếu nghiệp vụ không yêu cầu.
- Không cho phép user tự chọn index ngoài phạm vi được cấp quyền.
- Dùng cùng một quy tắc đặt tên cho ghi, đọc, backup và retention.

Không coi việc validate tên index là authorization. Một tên hợp lệ vẫn có thể trỏ tới dữ liệu mà người dùng không được phép truy cập.

## 12. Xử lý ID và routing

IndexCoordinates chọn index hoặc alias. Nó không thay thế routing key của document.

Elasticsearch có thể dùng custom routing để xác định shard. Nếu document được ghi với routing value, các thao tác get, exists hoặc delete cần dùng cùng routing value để định vị đúng document.

Ví dụ REST API:

~~~http
GET /orders-2026-11/_doc/O-1001?routing=tenant-a
~~~

Nếu ứng dụng dùng routing theo tenant, hãy quản lý cả index target và routing value trong cùng một context nghiệp vụ. Không giả định IndexCoordinates chứa routing.

Ngoài ra, cùng một ID có thể xuất hiện ở nhiều index. Một thao tác get với đúng ID nhưng sai index vẫn có thể trả về không tìm thấy hoặc một document khác có cùng ID.

Nên giữ đủ thông tin để xác định document, chẳng hạn ID, partition date/tenant và routing key nếu hệ thống sử dụng chúng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Save thành công nhưng get trả null | Đọc bằng index mặc định thay vì index động | Dùng cùng IndexCoordinates cho cả ghi và đọc |
| exists trả false dù document đã ghi | Sai index, alias hoặc routing | Kiểm tra index thực tế, alias và routing |
| Delete không xóa document mong muốn | Delete dùng index mặc định hoặc ID trùng ở index khác | Truyền đúng coordinates và xác nhận ID |
| Index không tồn tại | Chưa provisioning index đích | Kiểm tra exists và quy trình tạo index/mapping |
| Lỗi mapper khi ghi | Mapping index đích không tương thích entity | Đọc mapping của index thực tế |
| Search không thấy document mới | Chưa refresh | Refresh trong test hoặc xem lại refresh policy |
| Search nhiều index báo lỗi | Mapping khác nhau giữa các index | So sánh mapping và thống nhất schema |
| Ghi qua alias bị từ chối | Alias nhiều index nhưng không có write index | Kiểm tra alias và is_write_index |
| Tenant có thể truy cập index khác | Dùng input không được authorization kiểm tra | Lấy tenant từ principal và kiểm tra quyền |
| Repository không tìm thấy document đã ghi bằng Operations | Repository vẫn dùng index từ @Document | Dùng Operations với coordinates hoặc thiết kế alias/index thống nhất |

## 14. Quy trình debug khi dữ liệu không nằm ở index mong muốn

Khi save hoặc get có kết quả bất thường, hãy xác định index thực tế ở từng thao tác.

**Bước 1 — Xác định index mặc định của entity**

Kiểm tra @Document(indexName = ...) và cấu hình mapping liên quan.

**Bước 2 — Xác định coordinates được truyền**

Ghi log tên index/alias do resolver trả về. Tránh ghi dữ liệu nhạy cảm hoặc thông tin xác thực vào log.

**Bước 3 — Kiểm tra index và alias trên Elasticsearch**

~~~http
GET /_cat/indices?v
GET /_cat/aliases?v
~~~

Xác nhận tên index có tồn tại và alias phân giải đúng.

**Bước 4 — Đọc document trực tiếp theo index**

~~~http
GET /orders-2026-11/_doc/O-1001
~~~

Nếu document tồn tại ở index khác, logic chọn index của ứng dụng có thể không nhất quán.

**Bước 5 — Kiểm tra mapping**

~~~http
GET /orders-2026-11/_mapping?pretty
~~~

So sánh kiểu field với metadata của entity.

**Bước 6 — Kiểm tra toàn bộ CRUD path**

Đảm bảo save, get, exists, search, count và delete đều dùng cùng quy tắc chọn index. Nếu một thao tác cố ý dùng alias hoặc nhiều index, ghi rõ khác biệt đó trong service.

## 15. Ví dụ tổng hợp: service quản lý đơn hàng theo tháng

Ví dụ dưới đây gom việc chọn index vào một resolver và dùng nó cho các thao tác CRUD:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
class OrderIndexResolver {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    IndexCoordinates forDate(LocalDate date) {
        return IndexCoordinates.of(
            "orders-" + date.format(FORMAT)
        );
    }
}

@Service
public class OrderStore {

    private final ElasticsearchOperations operations;
    private final OrderIndexResolver indexResolver;

    public OrderStore(
            ElasticsearchOperations operations,
            OrderIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(
            order,
            indexResolver.forDate(businessDate)
        );
    }

    public Order find(String id, LocalDate businessDate) {
        return operations.get(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }

    public boolean exists(String id, LocalDate businessDate) {
        return operations.exists(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }

    public String delete(String id, LocalDate businessDate) {
        return operations.delete(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }
}
~~~

Ví dụ này giả định index theo tháng đã được tạo với mapping tương thích trước khi service ghi dữ liệu. Nó cũng giả định ngày nghiệp vụ đã được chuẩn hóa theo timezone của hệ thống.

Nếu cần tìm kiếm lịch sử qua nhiều tháng, service có thể tạo coordinates gồm các index được phép đọc và gọi search với cùng domain type. Không nên dùng một index pattern quá rộng khi chỉ cần vài tháng dữ liệu.

## 16. Bảng tra cứu nhanh

| Nhu cầu | Cách dùng |
|---|---|
| Dùng index mặc định từ entity | operations.save(entity) |
| Ghi vào index được chọn | operations.save(entity, coordinates) |
| Đọc theo ID ở index cụ thể | operations.get(id, Entity.class, coordinates) |
| Kiểm tra tồn tại ở index cụ thể | operations.exists(id, Entity.class, coordinates) |
| Xóa document theo ID | operations.delete(id, Entity.class, coordinates) |
| Search trên index được chọn | operations.search(query, Entity.class, coordinates) |
| Count trên index được chọn | operations.count(query, Entity.class, coordinates) |
| Quản lý index đích | operations.indexOps(coordinates) |
| Đọc nhiều index | IndexCoordinates.of(indexA, indexB, ...) |
| Ghi qua alias | IndexCoordinates.of("write-alias") với write index được cấu hình |

IndexCoordinates cho phép ElasticsearchOperations chọn index hoặc alias tường minh ở từng lần gọi. Hãy dùng cùng một quy tắc chọn index cho save, get, exists và delete; dùng alias để tách tên logic khỏi index vật lý; quản lý mapping/lifecycle trước khi ghi; và kiểm soát tenant, routing cùng quyền truy cập ở tầng ứng dụng. Khi cần định tuyến dữ liệu động theo từng thao tác, việc truyền coordinates rõ ràng giúp service biết chính xác document đang được đọc hoặc ghi ở đâu.

