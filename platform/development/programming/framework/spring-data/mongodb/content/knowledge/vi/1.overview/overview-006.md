# Lựa chọn MongoRepository, MongoTemplate hoặc driver trực tiếp

## 1. Vấn đề cần giải quyết

Khi xây dựng ứng dụng Java với **Spring Data MongoDB**, có ba cách thường gặp để làm việc với MongoDB:

- **`MongoRepository`**: mô tả thao tác dữ liệu qua interface repository gắn với một kiểu đối tượng miền (domain object).
- **`MongoTemplate`** (thông qua `MongoOperations`): viết truy vấn và thao tác dữ liệu bằng API của Spring Data MongoDB, có khả năng xây dựng truy vấn động, cập nhật một phần document, aggregation và nhiều thao tác nâng cao.
- **MongoDB Java Driver trực tiếp**: làm việc với `MongoClient`, `MongoDatabase`, `MongoCollection`, BSON `Document` và các API của driver, tự quản lý phần lớn chi tiết truy cập dữ liệu.

Ba lựa chọn này **không phải ba cơ sở dữ liệu khác nhau**. Chúng đều truy cập MongoDB, nhưng khác nhau về mức trừu tượng, cách biểu diễn dữ liệu, lượng mã phải duy trì và mức độ kiểm soát thao tác.

Mục tiêu của bài là biết **chọn công cụ phù hợp cho từng thao tác**, hiểu lúc nào cần chuyển sang cấp thấp hơn và tránh quyết định dựa trên nhận định đơn giản như “driver trực tiếp luôn nhanh hơn”. Các ví dụ sử dụng Spring Boot, Spring Data MongoDB kiểu đồng bộ (*imperative*) và MongoDB Java Sync Driver.

## 2. So sánh các lựa chọn

| Tiêu chí | MongoRepository | MongoTemplate | Driver trực tiếp |
|---|---|---|---|
| Cách viết chính | Khai báo interface và phương thức | Gọi API truy vấn/cập nhật của Spring Data | Gọi API MongoDB Java Driver |
| Đối tượng kết quả | Thường là entity, projection, DTO | Entity/DTO được Spring Data ánh xạ; có thể thao tác ở mức thấp hơn | BSON `Document` hoặc POJO khi tự cấu hình codec |
| Truy vấn phổ biến | Derived query, `@Query`, `@Aggregation`, phân trang | `Query`, `Criteria`, `Aggregation`, `Update` | `Filters`, `Aggregates`, `Updates`, BSON pipeline |
| Truy vấn thay đổi theo đầu vào | Làm được, nhưng phương thức đơn giản có thể trở nên khó bảo trì | Rất phù hợp | Làm được; phải tự quản lý nhiều chi tiết hơn |
| Cập nhật một phần, bulk, thao tác đặc thù | Có khả năng mở rộng bằng repository fragment hoặc cơ chế repository phù hợp | API trực tiếp, linh hoạt | Kiểm soát API driver ở mức thấp |
| Ánh xạ `@Document`, `@Field`, converter của Spring Data | Có | Có, khi thao tác qua cơ chế mapping của Spring Data | Không tự động áp dụng các annotation/converter đó |
| Chi phí bảo trì thường gặp | Thấp cho truy vấn gắn với entity | Trung bình; phải thiết kế lớp truy cập dữ liệu rõ ràng | Cao hơn vì tự xử lý BSON, cấu trúc collection và nhiều quy ước |
| Khi nên ưu tiên | CRUD và truy vấn thường xuyên theo mô hình miền | Truy vấn động, cập nhật có điều kiện, aggregation, bulk | Tính năng driver cụ thể, thao tác cấp thấp chưa được Spring Data đáp ứng tốt |

Lưu ý: **MongoRepository không bị giới hạn ở CRUD đơn giản**. Repository có thể dùng `@Query`, aggregation, projection và phương thức tùy biến. Tương tự, **MongoTemplate không loại bỏ Spring Data mapping**; nó vẫn có thể đọc/ghi cùng entity với repository. Mức trừu tượng cao không tự động đồng nghĩa với hiệu năng thấp hơn: cần đo truy vấn, index, lưu lượng mạng và chi phí chuyển đổi dữ liệu trong bối cảnh thực tế.

## 3. Cách ra quyết định

~~~mermaid
flowchart TD
    A["Cần thao tác dữ liệu MongoDB"] --> B{"Chủ yếu CRUD và truy vấn ổn định theo entity?"}
    B -->|"Có"| C["Ưu tiên MongoRepository"]
    B -->|"Không"| D{"Cần truy vấn động, aggregation, cập nhật có điều kiện hoặc bulk?"}
    D -->|"Có"| E["Ưu tiên MongoTemplate"]
    D -->|"Không"| F{"Cần API driver đặc thù hoặc mức điều khiển BSON/session cụ thể?"}
    F -->|"Có"| G["Dùng driver trực tiếp, giới hạn trong lớp chuyên biệt"]
    F -->|"Không"| H["Đánh giá lại yêu cầu; bắt đầu từ API đơn giản nhất đáp ứng được"]
    C --> I["Đo và kiểm tra query/index thực tế"]
    E --> I
    G --> I
    H --> I
~~~

Có thể áp dụng quy trình ngắn:

1. **Xác định nghiệp vụ và kiểu kết quả**: đang thao tác entity, báo cáo tổng hợp hay dữ liệu BSON thô?
2. **Viết ra loại truy vấn**: điều kiện cố định, điều kiện sinh động theo bộ lọc, cập nhật nhiều trường, aggregation pipeline hay lệnh driver đặc thù?
3. **Chọn API giữ mã dễ hiểu nhất**: repository cho truy vấn thông dụng, template cho thao tác phức tạp do ứng dụng kiểm soát, driver cho nhu cầu thực sự ở tầng driver.
4. **Kiểm chứng bằng dữ liệu và chỉ số**: index, `explain`, số document đọc, thời gian truy vấn, số lần gọi mạng và chi phí bảo trì.

Không bắt buộc chọn một API duy nhất cho cả service. Một module có thể dùng repository cho thao tác thông thường, template cho một báo cáo khó và driver trong một adapter riêng. Điều quan trọng là ranh giới trách nhiệm rõ ràng.

## 4. Ví dụ chung: truy vấn đơn hàng

Giả sử collection `orders` chứa document có `customerId`, `status`, `totalCents` và `createdAt`. Chức năng cần lấy **20 đơn mới nhất của một khách hàng với trạng thái PAID**.

Trong ứng dụng Spring Boot có dependency `spring-boot-starter-data-mongodb`, có thể cấu hình kết nối môi trường phát triển như sau:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
~~~

Trong môi trường thực tế, cấu hình URI và thông tin xác thực cần được cấp từ cấu hình bảo mật phù hợp, không đặt mật khẩu trực tiếp trong mã nguồn.

Định nghĩa entity dùng chung cho ví dụ repository và template:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private String id;
    private String customerId;
    private String status;
    private long totalCents;
    private Instant createdAt;

    public Order() {}

    public Order(String customerId, String status, long totalCents, Instant createdAt) {
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public long getTotalCents() { return totalCents; }
    public void setTotalCents(long totalCents) { this.totalCents = totalCents; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
~~~

Spring Data MongoDB sử dụng thông tin mapping để ánh xạ entity vào document. Trường `@Id` tương ứng với `_id` trong MongoDB; trong những trường hợp phù hợp, Spring Data có thể chuyển đổi giữa String và ObjectId. Với trường yêu cầu loại BSON cụ thể, cần xác định chiến lược ánh xạ một cách tường minh.

### 4.1. MongoRepository: dùng khi truy vấn gắn chặt với entity

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findTop20ByCustomerIdAndStatusOrderByCreatedAtDesc(
            String customerId, String status);
}
~~~

~~~java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderRepository orders;

    public OrderLookupService(OrderRepository orders) {
        this.orders = orders;
    }

    public List<Order> latestPaidOrders(String customerId) {
        return orders.findTop20ByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, "PAID");
    }
}
~~~

Spring Data phân tích tên phương thức để tạo điều kiện lọc, sắp xếp giảm dần theo `createdAt` và giới hạn 20 kết quả. Với các thao tác `save`, `findById`, `deleteById` và các truy vấn thường gặp, code tầng nghiệp vụ ngắn và dễ kiểm thử.

Repository cũng có thể biểu đạt câu truy vấn bằng annotation:

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderSearchRepository extends MongoRepository<Order, String> {
    @Query("{ 'status': ?0, 'totalCents': { $gte: ?1 } }")
    List<Order> findByStatusWithMinimumTotal(String status, long minimumCents);
}
~~~

Tránh kéo dài tên phương thức vô hạn khi bộ lọc có nhiều tổ hợp tùy chọn. Khi phải ghép điều kiện theo đầu vào, xây dựng một truy vấn duy nhất bằng `MongoTemplate` thường rõ ràng hơn. Nếu muốn giữ API repository cho bên gọi, có thể tạo **custom repository fragment** và triển khai truy vấn phức tạp trong fragment đó.

### 4.2. MongoTemplate: dùng khi cần chủ động xây dựng truy vấn

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderTemplateLookup {
    private final MongoTemplate template;

    public OrderTemplateLookup(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> latestPaidOrders(String customerId) {
        Query query = new Query(
                Criteria.where("customerId").is(customerId)
                        .and("status").is("PAID"));
        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(20);
        return template.find(query, Order.class);
    }
}
~~~

Kết quả vẫn là `List<Order>`, vẫn được chuyển đổi theo metadata và converter của Spring Data. Điểm khác biệt là code chủ động xây dựng `Query`, thuận tiện khi số điều kiện phụ thuộc dữ liệu đầu vào.

Ví dụ truy vấn động:

~~~java
public List<Order> search(String customerId, String optionalStatus, Long minimumCents) {
    Criteria criteria = Criteria.where("customerId").is(customerId);
    if (optionalStatus != null && !optionalStatus.isBlank()) {
        criteria = criteria.and("status").is(optionalStatus);
    }
    if (minimumCents != null) {
        criteria = criteria.and("totalCents").gte(minimumCents);
    }

    return template.find(new Query(criteria).limit(100), Order.class);
}
~~~

Đoạn trên là một phương thức bổ sung trong class đã có trường `template`. Giới hạn 100 giúp tránh truy vấn không kiểm soát trong ví dụ; với dữ liệu thực tế cần chiến lược phân trang, giới hạn tối đa và sort ổn định.

**Cập nhật nguyên tử theo điều kiện** cũng là một tình huống phù hợp với template. Ví dụ chỉ chuyển đơn từ `NEW` sang `PAID` nếu trạng thái hiện tại đúng như kỳ vọng:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

public boolean markPaidIfNew(String orderId) {
    Query query = new Query(
            Criteria.where("id").is(orderId).and("status").is("NEW"));
    Update update = new Update().set("status", "PAID");

    UpdateResult result = template.updateFirst(query, update, Order.class);
    return result.getModifiedCount() == 1;
}
~~~

Ở đây, cập nhật diễn ra trên server cho một document phù hợp; tránh mô hình đọc entity, sửa status rồi `save` mà không kiểm soát tranh chấp cập nhật. Trường `id` trong `Query` được mapping đến `_id` theo metadata của `Order`. Nếu yêu cầu nghiệp vụ phức tạp hơn, cần thiết kế thêm điều kiện phiên bản, tính idempotent và xử lý lỗi.

Ngoài `find` và `updateFirst`, `MongoTemplate` còn hỗ trợ `findAndModify`, `updateMulti`, `bulkOps` và aggregation thông qua `Aggregation`. Đây là lợi thế khi một thao tác không thể biểu đạt gọn bằng tên phương thức repository.

### 4.3. MongoDB Java Driver: dùng khi cần điều khiển tầng thấp

MongoDB Java Sync Driver làm việc trực tiếp với BSON và API của MongoDB. Ví dụ cùng truy vấn trên nhưng lấy kết quả dưới dạng `Document`:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.stereotype.Service;

@Service
public class RawOrderLookup {
    private final MongoCollection<Document> collection;

    public RawOrderLookup(MongoClient client) {
        // Trùng tên database và collection đã cấu hình cho các ví dụ.
        this.collection = client.getDatabase("shop").getCollection("orders");
    }

    public List<Document> latestPaidOrders(String customerId) {
        return collection.find(and(
                    eq("customerId", customerId),
                    eq("status", "PAID")))
                .sort(descending("createdAt"))
                .limit(20)
                .into(new ArrayList<>());
    }
}
~~~

Đây là driver **đồng bộ**. Trong ứng dụng Spring Boot thông thường, nên dùng `MongoClient` do container cấu hình và quản lý, tránh tạo một client mới cho từng request. Ví dụ này chỉ đọc BSON document; nếu muốn trả về `Order` phải tự áp dụng cách chuyển đổi phù hợp, chẳng hạn cấu hình POJO codec hoặc dùng cơ chế mapping do ứng dụng định nghĩa.

Driver trực tiếp phù hợp khi cần truy cập một API, BSON option hoặc đặc tính command mà abstraction đang dùng chưa hỗ trợ thuận tiện, hoặc khi đã đo và chứng minh lợi ích của một đường xử lý cấp thấp. Đổi lại, code phải tự quan tâm đến tên trường trong MongoDB, loại BSON, session, lỗi và tính nhất quán của dữ liệu trả về.

**Không nên mặc định rằng dùng driver sẽ nhanh hơn**. Với cùng câu lệnh được gửi đến server và cùng index, phần lớn thời gian có thể nằm ở việc MongoDB quét dữ liệu, sort hoặc truyền dữ liệu. Độ trễ cần được đo trước khi đổi API.

## 5. Ba lựa chọn có thể phối hợp như thế nào?

Ví dụ một hệ thống bán hàng có các nhu cầu:

| Nhu cầu | API khởi đầu hợp lý | Lý do |
|---|---|---|
Tạo đơn, xem đơn theo ID, liệt kê theo khách hàng | `MongoRepository` | Gắn trực tiếp với entity, quy tắc truy vấn ổn định |
Tìm đơn theo bộ lọc tùy chọn trên giao diện | `MongoTemplate` | Ghép `Criteria` theo tham số, không cần khai báo nhiều tổ hợp phương thức |
Chuyển trạng thái theo điều kiện, cập nhật hàng loạt | `MongoTemplate` | Dễ diễn đạt `Update`, bulk và kiểm tra số document bị tác động |
Báo cáo tổng hợp nhiều stage | `MongoTemplate` với `Aggregation`; hoặc `@Aggregation` khi pipeline ổn định | Dễ duy trì pipeline trong mã |
Thao tác driver rất chuyên biệt chưa có API Spring Data thích hợp | Driver trực tiếp | Kiểm soát chính xác API và BSON option |

Trong một ứng dụng, hai thành phần đầu thường sử dụng cùng `MongoDatabaseFactory` và cơ chế ánh xạ Spring Data. Tốt nhất nên đưa truy cập dữ liệu vào các lớp repository/adapter có ranh giới rõ ràng; service nghiệp vụ không cần biết đang dùng `MongoTemplate` hay driver.

Nếu dùng driver cùng repository/template, cần tránh các lỗi tích hợp sau:

- **Sai collection hoặc tên trường**: `@Document(collection = "orders")` và `@Field` chỉ được Spring Data xử lý trong đường mapping của nó. Driver làm việc với tên collection và tên BSON thực tế.
- **Khác kiểu dữ liệu**: `_id` có thể là `ObjectId` chứ không phải BSON String; ngày giờ, số thập phân và enum cũng cần chiến lược ánh xạ nhất quán.
- **Lệch vòng đời dữ liệu**: đường đi qua driver không tự động kích hoạt entity callbacks, auditing hay custom converters của Spring Data.
- **Khác session/transaction**: một lời gọi driver trực tiếp không được giả định tự tham gia session/transaction do Spring Data đang quản lý. Khi phối hợp phải truyền/quản lý đúng `ClientSession`, hoặc giữ thao tác nằm trong một abstraction đã quản lý transaction phù hợp.
- **Khác mô hình xử lý**: các API sync có thể chặn thread; nếu ứng dụng sử dụng WebFlux/reactive end-to-end, cần xem `ReactiveMongoRepository`, `ReactiveMongoTemplate` và Reactive Streams Driver thay vì gọi driver đồng bộ trong luồng reactive.

## 6. Những yếu tố quan trọng hơn việc chọn API

### 6.1. Thiết kế index theo truy vấn thực tế

Truy vấn ví dụ lọc `customerId` và `status` rồi sắp xếp `createdAt` giảm dần. Có thể cân nhắc một compound index phù hợp:

~~~javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });
~~~

Đây là index **ứng viên** cho truy vấn ví dụ, không phải khuyến nghị tạo index trên mọi collection. Cần kiểm tra tần suất đọc/ghi, tính chọn lọc, giới hạn dung lượng và kế hoạch thực thi. Annotation `@Indexed` hay `@CompoundIndex` trong entity không bảo đảm index được tự tạo ở mọi môi trường: cách triển khai index phụ thuộc cấu hình và chính sách migration/index management của dự án.

### 6.2. Quan sát truy vấn và phân trang

Thử lệnh MongoDB `explain` tại môi trường phù hợp:

~~~javascript
db.orders.find({ customerId: "c01", status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Kiểm tra `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và số document trả về. Khi lượng dữ liệu lớn, phân trang bằng `skip` sâu có thể tốn kém; hãy cân nhắc phân trang dựa trên giá trị sắp xếp (*keyset/cursor pagination*) với thứ tự ổn định và index tương ứng. Repository `Page<T>` có thể cần truy vấn đếm tổng số; nếu không cần tổng số phần tử, cân nhắc `Slice<T>` hoặc giới hạn kết quả.

### 6.3. Tính nguyên tử và transaction

Một thao tác cập nhật **một document** có thể được thực thi nguyên tử ở mức document và thường đủ cho nhiều nghiệp vụ. Transaction nhiều document là bài toán riêng; MongoDB transaction cần topology phù hợp (ví dụ replica set hoặc sharded cluster), session và transaction manager được cấu hình đúng. Không nên kỳ vọng `@Transactional` tự làm cho mọi lời gọi driver tùy ý tham gia cùng transaction.

### 6.4. Kiểm thử

- Với repository: kiểm tra truy vấn sinh ra từ tên phương thức, mapping entity, sort và giới hạn trên MongoDB thực.
- Với template: kiểm tra các nhánh bộ lọc tùy chọn, cập nhật có điều kiện, kết quả aggregation, đặc biệt là các trường hợp không khớp document.
- Với driver: kiểm tra kiểu BSON, mapping thủ công, cấu hình session và khả năng tương thích giữa các phiên bản MongoDB/driver.

`@DataMongoTest` có thể giúp tạo môi trường kiểm thử tập trung vào phần Spring Data MongoDB. Testcontainers với MongoDB thích hợp cho integration test cần hành vi database thực tế; cấu hình replica set khi kiểm thử transaction. Unit test mock một lệnh `Query` không thay thế được kiểm thử hành vi truy vấn và index thực.

## 7. Sai lầm thường gặp và cách tránh

| Nhận định hoặc cách làm | Vấn đề | Cách xử lý |
|---|---|---|
“Repository chỉ làm CRUD” | Bỏ qua `@Query`, `@Aggregation`, projections và custom fragments | Ưu tiên API repository khi truy vấn vẫn rõ ràng |
“Template không hỗ trợ entity mapping” | Đánh giá sai Spring Data | Dùng `find(query, Order.class)` và mapping metadata phù hợp |
“Driver luôn nhanh nhất” | Bỏ qua query plan, index, network và dữ liệu thực tế | Đo bằng profiling, `explain` và benchmark cùng điều kiện |
“Mọi thao tác đều nên ở driver” | Lặp mapping, validation và xử lý lỗi trong nhiều nơi | Cô lập driver trong adapter và chuẩn hóa model trả về |
“Đổi API là giải quyết được truy vấn chậm” | Truy vấn vẫn thiếu index hoặc quét nhiều document | Tối ưu query/index và kiểm tra execution plan |
“Repository và template không được dùng chung” | Tạo rào cản kiến trúc không cần thiết | Dùng chung mô hình miền, tổ chức ranh giới truy cập rõ |
“Gọi driver trong transaction Spring là tự tham gia” | Có thể thực thi ngoài session được quản lý | Xác định rõ đường transaction/session cho từng API |

## 8. Bài tập vận dụng

**Tình huống A.** Ứng dụng quản lý hồ sơ cần lưu, sửa, xóa hồ sơ và tìm theo email. Hãy chọn `MongoRepository` làm mặc định, bổ sung query method và kiểm tra index cho email (unique nếu nghiệp vụ yêu cầu).

**Tình huống B.** Trang quản trị cho phép lọc đơn theo nhiều tham số tùy chọn: khách hàng, trạng thái, khoảng tiền, ngày bắt đầu/kết thúc. Hãy xây dựng `Query` với `Criteria` trong `MongoTemplate`, cho phép sort và giới hạn kết quả. Kiểm thử ít nhất các trường hợp không có bộ lọc tùy chọn, có một bộ lọc và có nhiều bộ lọc.

**Tình huống C.** Một chức năng cần dùng một tùy chọn mới của MongoDB mà phiên bản Spring Data hiện tại chưa bọc thuận tiện. Hãy xác minh khả năng của driver tương thích, triển khai trong adapter riêng, giữ kiểu dữ liệu đầu ra ổn định và kiểm thử hành vi thực tế.

**Tình huống D.** Một truy vấn repository mất nhiều giây. Trước khi chuyển sang driver, hãy lấy execution plan, kiểm tra index, số document duyệt, sort, kích thước payload và số lần truy vấn. Chỉ thay API khi có nhu cầu chức năng hoặc lợi ích đo lường rõ ràng.

## 9. Ghi nhớ

**MongoRepository** là điểm xuất phát tốt cho CRUD và truy vấn rõ ràng theo entity. **MongoTemplate** phù hợp khi truy vấn hoặc cập nhật cần được lắp ghép và điều khiển trong mã ứng dụng. **MongoDB Java Driver trực tiếp** dành cho nhu cầu cấp thấp cụ thể cần toàn quyền với API/BSON. Có thể sử dụng cả ba trong cùng một hệ thống nếu quản lý thống nhất mapping, index, transaction và ranh giới truy cập dữ liệu. Tính đúng đắn, khả năng bảo trì và kết quả đo trên workload thực tế là tiêu chí quyết định.
