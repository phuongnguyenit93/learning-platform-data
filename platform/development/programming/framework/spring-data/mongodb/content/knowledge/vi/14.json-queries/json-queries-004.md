# Thiết lập sort, collation và hint theo khả năng của phiên bản

## 1. Mục tiêu và tình huống sử dụng

Trong MongoDB, cùng một bộ lọc có thể trả các document theo thứ tự khác nhau nếu không chỉ định sắp xếp. Ngay cả khi đã dùng `sort`, thứ tự của chuỗi tiếng Việt có thể khác kỳ vọng nếu không khai báo quy tắc so sánh ngôn ngữ. Khi dữ liệu lớn, MongoDB còn phải chọn index và kế hoạch thực thi thích hợp; đôi lúc cần dùng `hint` để kiểm chứng một index cụ thể.

Trong module **SPRING_DATA_MONGODB**, chúng ta truy vấn MongoDB bằng `MongoRepository`, annotation `@Query` hoặc `MongoTemplate`. Bài thuộc chương **Truy vấn JSON**, tập trung vào ba tùy chọn gắn trực tiếp với truy vấn:

- **`sort`:** Thứ tự trả kết quả, bao gồm khóa phá hòa để phân trang ổn định.
- **`collation`:** Quy tắc so sánh chuỗi theo ngôn ngữ và độ mạnh so sánh, ảnh hưởng cả tìm kiếm và thứ tự.
- **`hint`:** Yêu cầu MongoDB dùng một index cụ thể trong những thao tác có hỗ trợ, thường để kiểm thử hoặc khi đã có bằng chứng về kế hoạch tốt hơn.

Các API, annotation và thuộc tính khả dụng có thể khác theo phiên bản Spring Data MongoDB, MongoDB Java driver và server. Vì vậy, bên cạnh cách viết, bài này nhấn mạnh **cách kiểm tra khả năng của phiên bản và BSON thực tế được gửi**. Hiểu đúng ba tùy chọn này cũng giúp đánh giá index, phân trang, kiểm thử và chẩn đoán hiệu năng thay vì chỉ tối ưu theo cảm giác.

Sau bài học, bạn có thể:

1. Viết truy vấn JSON và repository có thứ tự sắp xếp rõ ràng, tránh phụ thuộc thứ tự tự nhiên của collection.
2. Áp dụng `collation` phù hợp cho dữ liệu tiếng Việt, nhận biết ảnh hưởng đến index và phép so sánh.
3. Dùng `hint` theo tên index hoặc key pattern trong mongosh, sau đó áp dụng qua Spring Data khi phiên bản hỗ trợ.
4. Phân biệt tùy chọn tĩnh của `@Query` với `Sort`/`Pageable` hoặc `Query` lập trình động.
5. Kiểm tra `explain("executionStats")`, nhận diện tình huống sort không tận dụng index hoặc hint làm truy vấn tệ hơn.

## 2. Dữ liệu mẫu và ba nhu cầu truy vấn

Giả sử hệ thống quản lý đơn hàng của nhiều cửa hàng, mỗi cửa hàng có `tenantId` riêng. Mọi truy vấn nghiệp vụ phải ràng buộc tenant của người dùng đã xác thực.

```javascript
db.orders.insertMany([
  {
    _id: "order-001",
    tenantId: "tenant-a",
    customerName: "An",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    totalAmountVnd: NumberLong("120000")
  },
  {
    _id: "order-002",
    tenantId: "tenant-a",
    customerName: "Ân",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    totalAmountVnd: NumberLong("150000")
  },
  {
    _id: "order-003",
    tenantId: "tenant-a",
    customerName: "Đức",
    status: "PAID",
    createdAt: ISODate("2026-11-19T10:00:00Z"),
    totalAmountVnd: NumberLong("250000")
  },
  {
    _id: "order-004",
    tenantId: "tenant-a",
    customerName: "Bình",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-20T07:00:00Z"),
    totalAmountVnd: NumberLong("200000")
  },
  {
    _id: "order-005",
    tenantId: "tenant-b",
    customerName: "An",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    totalAmountVnd: NumberLong("500000")
  }
]);
```

Đây là dữ liệu minh họa cho môi trường test, không phải script nên chạy nguyên trạng trên collection production. Ba nhu cầu cần giải quyết:

| Mã | Yêu cầu | Filter | Sort và tùy chọn |
| --- | --- | --- | --- |
| Q1 | 20 đơn chờ giao mới nhất của tenant | `tenantId + status` | `createdAt DESC, _id DESC` |
| Q2 | Danh sách tên khách của tenant theo thứ tự tiếng Việt | `tenantId` | `customerName ASC, _id ASC`; collation tiếng Việt |
| Q3 | So sánh hiệu năng của hai index cho Q1 | Như Q1 | Giữ filter/sort, lần lượt kiểm thử hint |

Q1 và Q2 là **nghiệp vụ thực**. Q3 là **hoạt động chẩn đoán**, không có nghĩa ứng dụng nên gắn hint cố định vào mọi query.

## 3. Sort trong truy vấn JSON của MongoDB

### 3.1. Thứ tự tăng và giảm

Trong MongoDB, `1` nghĩa là tăng dần và `-1` là giảm dần:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Với dữ liệu mẫu, Q1 có thứ tự `order-004`, `order-002`, `order-001`. Hai đơn sau có cùng `createdAt` nên thứ tự được quyết định bằng `_id DESC`.

**Vì sao thêm `_id`?** Chỉ sắp theo `createdAt` không bảo đảm thứ tự nhất quán của các document có cùng thời điểm. Nếu cần phân trang, khóa phá hòa ổn định giúp tránh tình huống bản ghi chuyển vị trí ngẫu nhiên giữa các lần gọi. Không nên coi thứ tự trả về không có `sort` là một contract của ứng dụng.

MongoDB cũng cho phép sắp theo nhiều trường, nhưng cần nhớ **thứ tự khai báo các khóa**: trường đầu là mức ưu tiên chính, các trường tiếp theo phân biệt khi khóa trước bằng nhau.

### 3.2. Sắp theo trường lồng nhau

Nếu document có `shippingAddress.city`, có thể:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ "shippingAddress.city": 1, _id: 1 });
```

Trước khi áp dụng, phải xác minh field BSON thật. Nếu domain Java đổi tên qua `@Field("city_name")` thì đường dẫn vật lý có thể là `shippingAddress.city_name`. Trong mongosh và JSON BSON thô, phải dùng tên **lưu trong database**.

### 3.3. Giá trị thiếu, null và kiểu khác nhau

Sort theo một field không bảo đảm field đó có mặt ở mọi document. MongoDB có quy tắc so sánh BSON giữa kiểu và giá trị; document thiếu trường hoặc có giá trị `null` có thể xuất hiện ở vị trí không như nghiệp vụ mong đợi.

Khi ứng dụng yêu cầu «đơn có thời gian tạo hợp lệ», hãy xác định ràng buộc dữ liệu và xử lý document không có `createdAt` thay vì chỉ thêm `sort`. Đặc biệt, dữ liệu pha trộn BSON Date với String ngày tháng không có cùng semantics sắp xếp.

## 4. Sort trong MongoTemplate và repository

### 4.1. Mô hình Java được ánh xạ

Ví dụ Java 17+:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String customerName,
    String status,
    Instant createdAt,
    long totalAmountVnd
) {}
```

Property `id` được ánh xạ vào BSON `_id`; các trường còn lại trong ví dụ có cùng tên Java và BSON. Mô hình này phục vụ bài học sort/collation/hint; ứng dụng thực tế cần validation, phân quyền, state transition và những invariant khác.

### 4.2. MongoTemplate: Query.with(Sort)

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchService {
    private final MongoTemplate mongoTemplate;

    public OrderSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<OrderDocument> readyToShip(String tenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is("READY_TO_SHIP")
        );
        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ));
        query.limit(20);
        return mongoTemplate.find(query, OrderDocument.class);
    }
}
```

Khi `Query` được thực thi với `OrderDocument.class`, metadata mapping giúp chuyển property `id` thành `_id`. Nếu dùng `MongoTemplate.find(query, Document.class, "orders")` hoặc driver trực tiếp, đừng tự giả định mọi trường Java sẽ được dịch giống khi có domain type.

### 4.3. Repository: sort tĩnh trong @Query

Với Spring Data MongoDB có hỗ trợ thuộc tính `sort` của annotation `@Query`:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderQueueRepository
    extends Repository<OrderDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        sort = "{ 'createdAt': -1, '_id': -1 }"
    )
    List<OrderDocument> findQueue(
        String tenantId,
        String status
    );
}
```

Lưu ý: phương thức này không có giới hạn số lượng kết quả; nó chỉ minh họa **sort tĩnh**. Trong ứng dụng production, nên cung cấp `Pageable` hoặc giới hạn kết quả theo use case để tránh tải toàn bộ hàng đợi.

`?0` và `?1` là **placeholder cho tham số** do cơ chế query annotation binding xử lý. Không ghép chuỗi đầu vào người dùng để tạo JSON query thủ công. Tên `tenantId`/`status` phải nằm trong truy vấn ngay từ đầu để dữ liệu tenant khác không bị trả về.

### 4.4. Repository: sort động và Pageable

Với nhu cầu sắp xếp linh hoạt, định nghĩa repository có `Pageable`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderPageRepository
    extends Repository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    Slice<OrderDocument> findQueue(
        String tenantId,
        String status,
        Pageable pageable
    );
}
```

Ở service:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest page = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

var result = orderPageRepository.findQueue(
    authenticatedTenantId,
    "READY_TO_SHIP",
    page
);
```

`Slice` phù hợp khi chỉ cần biết còn dữ liệu trang kế tiếp thay vì tổng số bản ghi; `Page` có thể thực hiện truy vấn đếm bổ sung. Tuy vậy, offset lớn vẫn có thể tốn tài nguyên, nên với danh sách rất sâu có thể dùng keyset/cursor pagination.

**Không mặc định trộn sort tĩnh và sort động rồi đoán thứ tự ưu tiên.** Khi method dùng cả `@Query(sort=...)` và `Sort`/`Pageable`, cơ chế kết hợp có thể phụ thuộc hành vi của phiên bản cụ thể. Hãy chọn một nguồn thứ tự rõ ràng cho từng query, kiểm tra BSON thực thi và viết integration test.

## 5. Collation: quy tắc so sánh chuỗi theo ngôn ngữ

### 5.1. Vì sao sort mặc định chưa đủ cho tên người?

Thứ tự mặc định kiểu so sánh nhị phân (simple collation) không phải lúc nào cũng phản ánh thứ tự mong muốn của người dùng khi sắp xếp tên tiếng Việt, chữ hoa/chữ thường hay dấu. MongoDB hỗ trợ **collation** dựa trên quy tắc locale, cho phép xác định cách so sánh chuỗi.

Ví dụ:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 });
```

`locale: "vi"` yêu cầu quy tắc tiếng Việt. `strength: 2` thường so sánh đến mức phân biệt dấu nhưng không phân biệt chữ hoa/thường theo mức độ mạnh tương ứng. Thứ tự cụ thể cần được kiểm chứng bằng fixture tên tiếng Việt, vì các trường hợp `đ/Đ`, dấu thanh, dấu phụ và chữ ghép có quy tắc ngôn ngữ riêng.

### 5.2. Một số tùy chọn collation thường gặp

| Thuộc tính | Ví dụ | Ý nghĩa chính |
| --- | --- | --- |
| `locale` | `"vi"`, `"en"`, `"simple"` | Ngôn ngữ/quy tắc so sánh; simple dùng so sánh nhị phân |
| `strength` | `1`, `2`, `3` | Độ mạnh phân biệt chữ cơ bản, dấu, hoa/thường theo tầng so sánh |
| `caseLevel` | `true` | Thêm phân biệt hoa/thường trong các trường hợp strength thấp |
| `numericOrdering` | `true` | Xét thứ tự số đối với các chuỗi chữ số liên tiếp theo quy tắc ICU |
| `normalization` | `true` | Xử lý các dạng chuẩn hóa Unicode theo cơ chế collation |

Ví dụ sắp xếp `"Sản phẩm 2"` và `"Sản phẩm 10"`:

```javascript
db.products.find({ tenantId: "tenant-a" })
  .sort({ displayName: 1 })
  .collation({
    locale: "vi",
    numericOrdering: true
  });
```

Với numeric ordering, chuỗi số được xét theo giá trị số trong những giới hạn được hỗ trợ, nên `"2"` có thể xếp trước `"10"`. Đây không phải lý do để lưu số tiền hoặc số lượng dạng String; dữ liệu số nghiệp vụ nên có BSON numeric type thích hợp.

### 5.3. Collation ảnh hưởng cả so sánh equality

Collation không chỉ đổi thứ tự sort. Nó có thể thay đổi việc một điều kiện **so sánh String** có coi hai giá trị là tương đương hay không:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  customerName: "An"
}).collation({
  locale: "vi",
  strength: 1
});
```

Với strength thấp, một số khác biệt về hoa/thường hoặc dấu có thể được bỏ qua theo quy tắc locale. Điều này rất hữu ích cho tìm kiếm tên thân thiện nhưng **không nên áp dụng tự động cho mọi field**, đặc biệt là mã đơn, tên đăng nhập hoặc định danh có yêu cầu so sánh chính xác.

Hai lưu ý quan trọng:

- Một collation thường áp dụng cho **toàn operation** trong phạm vi được hỗ trợ, không phải tự đặt strength riêng cho từng field của cùng một `find`.
- `$regex` không có cùng ngữ nghĩa «case-insensitive theo collation» như equality dựa trên collation. Đừng coi index dùng collation là giải pháp tự động tối ưu mọi truy vấn regex.

## 6. Chọn index tương thích với collation

### 6.1. Index mặc định và index có collation khác nhau

MongoDB index được tạo với collation cụ thể hoặc theo collation mặc định của collection. Ví dụ index phục vụ Q2:

```javascript
db.orders.createIndex(
  { tenantId: 1, customerName: 1, _id: 1 },
  {
    name: "ix_orders_tenant_customer_vi",
    collation: { locale: "vi", strength: 2 }
  }
);
```

Truy vấn dùng cùng quy tắc:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 })
  .limit(20);
```

Đây là một **ứng viên hợp lý** để MongoDB lấy kết quả theo thứ tự mong muốn mà không phải sort thêm trên tập dữ liệu lớn. Tuy nhiên, lựa chọn thực tế phụ thuộc query planner, dữ liệu và index khác; phải xác minh bằng `explain`.

### 6.2. Vì sao query và index phải khớp collation?

Một index trên chuỗi lưu khóa theo quy tắc so sánh lúc tạo index. Nếu query yêu cầu collation khác, MongoDB có thể không sử dụng index đó cho một số so sánh chuỗi hoặc sort. Trong một số trường hợp, **prefix không phải String** của compound index vẫn có ích cho filter, nhưng không có nghĩa phần sort theo String sẽ được index hỗ trợ.

| Tình huống | Kỳ vọng cần kiểm tra |
| --- | --- |
| Query `locale: "vi", strength: 2`; index cùng cấu hình | Có thể dùng index cho so sánh/sort chuỗi phù hợp |
| Query simple; index dùng `vi/strength: 2` | Có thể không dùng được phần index phục vụ thứ tự chuỗi mong muốn |
| Query `vi/strength: 1`; index `vi/strength: 2` | Khác quy tắc, không tự coi là tương đương |
| Query có filter số và sort chuỗi | Có thể tận dụng một phần index tùy key pattern; phải xem plan |

Nếu tạo index mới trùng key pattern nhưng khác collation, cần tên index khác và kiểm tra các ràng buộc của phiên bản/server. Mỗi index tốn dung lượng và chi phí khi ghi; không tạo tất cả tổ hợp locale/strength chỉ vì ứng dụng có thể chọn nhiều ngôn ngữ.

**Unique index cũng bị ảnh hưởng:** Ràng buộc unique theo collation có thể coi một số String là tương đương. Trước khi áp dụng unique index collation cho email/mã, phải xác định chính xác chính sách phân biệt hoa/thường và dấu, dữ liệu trùng đã tồn tại, phạm vi tenant và yêu cầu sharding nếu có.

## 7. Hint: yêu cầu server dùng một index

### 7.1. Hint không phải sort và không phải tạo index

`hint` cung cấp cho server một chỉ dẫn lựa chọn index trong các operation hỗ trợ. Nó **không tạo index**, không bảo đảm index đó phù hợp filter hoặc sort và không thay thế collation.

Đề xuất index cho Q1:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "ix_orders_tenant_status_recent" }
);
```

Chạy query bình thường:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Ép thử index đã biết theo **tên**:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20);
```

Hoặc theo **key pattern** tương ứng trong mongosh:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint({ tenantId: 1, status: 1, createdAt: -1, _id: -1 })
  .limit(20);
```

Các hình thức hint có thể khác nhau giữa API driver, kiểu thao tác và phiên bản. Khi dùng Spring Data, nên ưu tiên **tên index** đã quản lý rõ ràng nếu API nhận hint dưới dạng String; với key pattern, xác minh cách API của phiên bản diễn giải chuỗi JSON.

### 7.2. Khi nào nên dùng hint?

Một số tình huống chính đáng:

1. **Chẩn đoán:** So sánh `explain("executionStats")` của truy vấn tự chọn index với truy vấn bị ép index.
2. **Regression có bằng chứng:** Có một query shape quan trọng mà planner thường chọn plan kém trong một phân bố dữ liệu cụ thể.
3. **Kiểm tra migration index:** Đánh giá index mới trước khi quyết định giữ, thay thế hay loại bỏ index cũ.

Những tình huống **không nên** mặc định hint: muốn «truy vấn chắc chắn nhanh», chưa đo trên dữ liệu đại diện, index thường xuyên đổi tên, hoặc có nhiều tenant với phân bố dữ liệu rất khác nhau.

Hint sai có thể làm tăng số khóa/document đọc, buộc sort tốn tài nguyên hoặc gây lỗi nếu index được chỉ định không tồn tại hay không phù hợp ràng buộc của operation. Phải có test và quy trình vận hành khi đổi/xóa index được tham chiếu bởi hint.

## 8. MongoTemplate: cấu hình sort, collation, hint cùng một Query

Với các phiên bản Spring Data MongoDB cung cấp `Query.withHint(...)` và `Query.collation(...)`, có thể cấu hình ở cấp `Query`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class CustomerNameSearch {
    private final MongoTemplate template;

    public CustomerNameSearch(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> sortedCustomers(String tenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
        );
        query.with(Sort.by(
            Sort.Order.asc("customerName"),
            Sort.Order.asc("id")
        ));
        query.collation(
            Collation.of("vi")
                .strength(Collation.ComparisonLevel.secondary())
        );
        query.withHint("ix_orders_tenant_customer_vi");
        query.limit(20);
        return template.find(query, OrderDocument.class);
    }
}
```

Ở đây:

- `Sort.by(...)` sử dụng **property Java**. Field `id` được mapper dịch thành `_id`.
- `Collation.of("vi").strength(...)` tương ứng ý định `locale: "vi", strength: 2`.
- `withHint("ix_orders_tenant_customer_vi")` chỉ định tên index đã có; không tạo index.
- `limit(20)` giới hạn số document trả về. Không thể chỉ dựa vào `limit` để thay thế phân trang thực tế.

Không nên copy nguyên mẫu rồi bắt mọi query đều dùng hint này: index chỉ phù hợp nếu filter, sort và collation tương ứng. Với query theo status/thời gian ở Q1, index và hình dạng truy vấn khác.

### 8.1. JSON query dưới dạng BasicQuery

Để tiếp tục chủ đề «Truy vấn JSON», Spring Data MongoDB có `BasicQuery` cho trường hợp muốn diễn đạt filter bằng chuỗi JSON:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.BasicQuery;

BasicQuery query = new BasicQuery(
    "{ 'tenantId': 'tenant-a', 'status': 'READY_TO_SHIP' }"
);
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.withHint("ix_orders_tenant_status_recent");
query.limit(20);
```

Ví dụ dùng **chuỗi JSON cố định**. Với tham số người dùng, ưu tiên `Criteria`/`Query` hoặc placeholder của repository để tránh tự ghép giá trị không được escape, lẫn kiểu BSON và nguy cơ biến dạng filter. Trong `BasicQuery`, cần phân biệt tên trường vật lý với property Java khi đọc kết quả theo domain type.

## 9. @Query: sort, collation và hint theo phiên bản

### 9.1. Ba thuộc tính khai báo trong annotation

Ở những phiên bản Spring Data MongoDB hỗ trợ các phần tử annotation này, có thể định nghĩa một truy vấn tĩnh:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderNameRepository
    extends Repository<OrderDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0 }",
        sort = "{ 'customerName': 1, '_id': 1 }",
        collation = "{ 'locale': 'vi', 'strength': 2 }",
        hint = "ix_orders_tenant_customer_vi"
    )
    Slice<OrderDocument> findCustomers(
        String tenantId,
        Pageable pageable
    );
}
```

Ví dụ gọi với `PageRequest.of(0, 20)` **không chứa dynamic sort** để dành quyền quyết định thứ tự cho `sort` tĩnh trong annotation. Đừng giả định phương thức trên biên dịch được với mọi thế hệ thư viện: kiểm tra API thực tế của `org.springframework.data.mongodb.repository.Query` trong bản Spring Data đang dùng. Nếu `collation` hoặc `hint` chưa có hoặc cách diễn giải không như mong muốn, dùng `MongoTemplate` theo mục 8 để kiểm soát rõ hơn.

Trong hệ thống có index migration thường xuyên, việc nhúng tên index vào annotation làm code phụ thuộc cấu trúc database. Chỉ sử dụng hint tĩnh khi đó là quyết định đã đo và được quản lý cùng migration index.

### 9.2. Ưu tiên cách viết nào?

| Nhu cầu | Cách thể hiện thường phù hợp |
| --- | --- |
| Filter/sort cố định, đơn giản | Repository `@Query(sort = "...")` khi phiên bản hỗ trợ |
| Sort do người dùng chọn trong danh sách cho phép | `Pageable`/`Sort` qua repository hoặc `Query.with(Sort)` |
| Collation cố định cho một nghiệp vụ | `@Query(collation = "...")` nếu có; hoặc `Query.collation(...)` |
| Collation tùy locale đã kiểm soát | Xây `Collation` trong service và dùng `MongoTemplate` |
| Hint phục vụ chẩn đoán | Mongosh `hint(...)` + `explain(...)`, sau đó cân nhắc `Query.withHint(...)` |
| Query JSON có biểu thức phức tạp | `@Query` có placeholder hoặc `BasicQuery`/`MongoTemplate` với test rõ ràng |
| Aggregation pipeline | API aggregation và tùy chọn riêng; không suy ra `@Query` áp dụng cho mọi stage |

Quan trọng hơn cú pháp là **kiểm chứng hành vi của phiên bản**: method có tồn tại không, query được mã hóa thế nào, sort động/tĩnh kết hợp ra sao, và collation có đúng bằng collation của index không.

## 10. Các giới hạn theo phiên bản cần kiểm tra

Không nên coi tài liệu của một phiên bản Spring Data hiện đại là bảo đảm cho một dự án dùng thư viện cũ. Bốn lớp phiên bản có thể ảnh hưởng đến kết quả:

| Lớp | Điều cần kiểm tra |
| --- | --- |
| MongoDB server | Có hỗ trợ collation, hint và tùy chọn đó trên operation cụ thể không? |
| MongoDB Java driver | Method cấu hình của `FindIterable`/các API khác có nhận sort, collation, hint như mong muốn không? |
| Spring Data MongoDB | `Query.collation`, `Query.withHint`, thuộc tính `sort`/`collation`/`hint` của `@Query` có sẵn không? |
| Spring Boot/autoconfiguration | Phiên bản dependency thực tế và cách tạo `MongoTemplate`/repository có dùng cùng mapping hay không? |

MongoDB server hỗ trợ **collation từ phiên bản 3.4 trở lên**. Đây là mốc khả năng của server, không có nghĩa mọi phiên bản Spring Data MongoDB trước/sau mốc đó đều có cú pháp annotation giống nhau. Tương tự, hint ở mức server và hint trong annotation repository là **hai lớp API riêng**.

### 10.1. Quy trình xác nhận tương thích

1. Ghi nhận phiên bản MongoDB server, Spring Data MongoDB, Spring Boot và driver của môi trường thực tế.
2. Kiểm tra chữ ký method/annotation từ **đúng artifact version đã khóa** trong dự án, không chỉ tham khảo ví dụ của phiên bản mới hơn.
3. Viết integration test nhỏ cho filter, sort, collation và hint qua repository/template.
4. Quan sát query thực tế tại database và chạy cùng truy vấn trong mongosh.
5. Dùng `explain("executionStats")` để xác minh index và sort; không lấy việc mã Java chạy không lỗi làm bằng chứng hiệu năng.
6. Sau khi nâng cấp, chạy lại test với tên có dấu, key có cùng giá trị sort, query thiếu index và dữ liệu tenant lớn.

Nếu một thuộc tính annotation không được hỗ trợ, Java compiler sẽ báo lỗi ở phần tử annotation không tồn tại; nếu server không hỗ trợ tùy chọn, lỗi có thể xảy ra lúc thực thi. Đừng dùng những ngoại lệ này như một «cơ chế tự fallback» không được thiết kế.

### 10.2. Không suy rộng sang mọi thao tác

Các ví dụ trên chủ yếu áp dụng cho **find query**. `countDocuments`, `distinct`, `findAndModify`, update, delete hoặc aggregation có bộ tùy chọn và giới hạn riêng; một số lệnh hoặc phiên bản không nhận sort/collation/hint giống nhau. Khi chuyển từ `find` sang operation khác, hãy đọc API của operation đó và kiểm tra server hỗ trợ, thay vì bê nguyên chú thích `@Query`.

## 11. Kết hợp sort, collation và index cho hiệu năng

### 11.1. Query shape quyết định thứ tự khóa index

Với Q1:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Ứng viên index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Hai field đầu được lọc bằng equality, sau đó là thứ tự sort. Điều này thường phù hợp nguyên tắc **Equality–Sort–Range (ESR)** khi lập kế hoạch compound index. Tuy nhiên, đó là heuristic, không phải bảo đảm planner chọn index đó hoặc nó luôn nhanh nhất.

Với Q2, query cần collation tiếng Việt và sort theo `customerName` nên một index Q1 không giải quyết trực tiếp vấn đề. Đây là lý do không thể chỉ tạo «một index cho tất cả các truy vấn».

### 11.2. Dấu hiệu một sort tốn tài nguyên

Nếu query không thể lấy dữ liệu theo thứ tự từ index, server có thể phải sort riêng. Trên tập dữ liệu lớn, điều này tốn CPU/bộ nhớ và trong một số tình huống có thể spill hoặc bị giới hạn tài nguyên. Chỉ nhìn `nReturned = 20` chưa đủ: MongoDB có thể phải xử lý nhiều document trước khi trả 20 kết quả đó.

Một trường hợp dễ bỏ sót: index đúng key pattern nhưng **sai collation**. Khi sort theo String dùng locale `vi` mà index được tạo với simple collation, MongoDB có thể phải sort riêng dù developer nhìn thấy index chứa field `customerName`.

### 11.3. Dùng hint như thí nghiệm có kiểm soát

So sánh hai plan:

```javascript
// Để MongoDB tự chọn index.
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

// Yêu cầu thử index đã biết.
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20)
  .explain("executionStats");
```

Để kết luận, không chỉ so số mili-giây của một lần chạy. Dùng tập dữ liệu đại diện, kiểm tra số khóa và document được duyệt, sort stage, nhiều phân bố tenant và trạng thái phổ biến/hiếm. Khi dùng `explain`, cơ chế thống kê và cache kế hoạch có những khác biệt so với chạy truy vấn sản xuất thông thường; nên kết hợp benchmark/monitoring ở mức ứng dụng.

## 12. Đọc kết quả explain đúng cách

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| `winningPlan` | Server chọn chiến lược nào? |
| `IXSCAN` / `COLLSCAN` | Có scan index hay quét collection? |
| `indexName` | Index thực sự được dùng có đúng tên được hint/đề xuất không? |
| Stage `SORT` hoặc tương đương | Có cần sort riêng hay tận dụng thứ tự index? |
| `totalKeysExamined` | Server duyệt bao nhiêu khóa index? |
| `totalDocsExamined` | Bao nhiêu document phải được đọc/kiểm tra? |
| `nReturned` | Bao nhiêu kết quả được trả? |
| `executionTimeMillis` | Độ trễ quan sát được trong điều kiện đo này là bao nhiêu? |

Plan có thể được hiển thị theo những cấu trúc khác nhau giữa các phiên bản server/query engine. Vì vậy không nên viết test chuyên môn dựa vào duy nhất một đường dẫn JSON của `winningPlan` khi hệ thống có kế hoạch nâng cấp.

**Ví dụ diễn giải:** Q1 trả 20 document nhưng `totalDocsExamined` rất cao và xuất hiện sort riêng. Đây là tín hiệu nên xem lại filter/index/sort. Ngược lại, nếu hint khiến `totalKeysExamined` tăng mạnh, index bị ép có thể kém hơn lựa chọn tự nhiên của planner.

### 12.1. Hint không sửa query sai

Nếu filter dùng sai `tenantId`, sai kiểu BSON `createdAt` hoặc sai collation khi so sánh tên, hint không khắc phục được kết quả sai. Thứ tự điều tra hợp lý:

```text
Filter đúng dữ liệu và quyền truy cập?
    ↓
Sort keys và hướng sắp xếp đúng?
    ↓
Collation đúng ngôn ngữ/strength?
    ↓
Index phù hợp và collation khớp?
    ↓
Explain tự chọn plan
    ↓
Thử hint nếu có mục tiêu chẩn đoán rõ
```

## 13. Phân trang ổn định và sort do người dùng chọn

### 13.1. Offset pagination và khóa phá hòa

Khi gọi các trang:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20)
  .limit(20);
```

Thêm `_id` bảo đảm thứ tự giữa các document có cùng `createdAt`, nhưng **không cố định snapshot** khi dữ liệu được chèn/xóa trong lúc người dùng phân trang. Trang theo offset vẫn có thể lặp hoặc bỏ qua document nếu có thay đổi đồng thời. Với dữ liệu lớn hoặc được cập nhật liên tục, cân nhắc cursor/keyset pagination.

### 13.2. Một ví dụ cursor phân trang

Giả sử sort giảm dần theo `createdAt`, rồi `_id`. Cursor của trang trước là:

```javascript
const lastCreatedAt = ISODate("2026-11-18T08:00:00Z");
const lastId = "order-002";

db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Ví dụ dùng `_id` String. Nếu ID có BSON ObjectId, cursor và filter phải dùng kiểu BSON tương ứng. Collation cũng có thể ảnh hưởng thứ tự và điều kiện cursor khi khóa phân trang là String chịu quy tắc so sánh ngôn ngữ. Không được dùng một sort ở trang đầu rồi đổi collation hoặc sort key giữa các trang.

### 13.3. Kiểm soát dynamic sort từ API

Nếu người dùng chọn sort từ giao diện, hãy giới hạn danh sách field được phép như `createdAt`, `totalAmountVnd` hoặc `customerName`, xác định hướng sort và thêm khóa phá hòa. Tránh đưa một JSON sort hoặc field path bất kỳ từ client trực tiếp xuống repository/template.

Việc giới hạn sort giúp:

- Ngăn truy vấn dựa trên field nội bộ/nhạy cảm mà API không công bố.
- Tránh sort không có index trên các field không dùng trong sản phẩm.
- Giữ hợp đồng phân trang ổn định.
- Chọn collation phù hợp khi sort theo tên thay vì theo thời gian/số.

## 14. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có `sort` nhưng kết quả thay đổi thứ tự | Dựa vào thứ tự tự nhiên của collection | Khai báo sort tường minh theo use case |
| Hai record cùng `createdAt` đổi vị trí | Thiếu khóa phá hòa | Thêm `_id` hoặc khóa ổn định khác |
| Tên có dấu xếp không hợp lý | So sánh simple/binary | Xác định `locale` và `strength` đúng nghiệp vụ |
| Query nhanh với sort số nhưng chậm với sort tên | Index chưa phục vụ collation/sort chuỗi | Kiểm tra collation của query và index |
| `@Query(collation=...)` không biên dịch | Spring Data version không có phần tử annotation | Xác nhận version, cân nhắc `MongoTemplate` |
| `@Query(hint=...)` chạy lỗi | Index không tồn tại hoặc tùy chọn không được hỗ trợ | Kiểm tra index, driver/server và thao tác |
| Hint khiến truy vấn chậm hơn | Ép index không phù hợp | Bỏ hint hoặc thử lại với plan có bằng chứng |
| Query trả ít hơn dự kiến | Collation/equality hoặc BSON type khác kỳ vọng | Kiểm tra filter thực và dữ liệu thật |
| Sort trên nhiều trang bị trùng/bỏ sót | Offset với dữ liệu thay đổi đồng thời | Dùng keyset phù hợp; cân nhắc snapshot consistency |
| `Sort.by("id")` không giống mongosh `_id` | Lẫn tên property và tên field BSON | Kiểm tra mapping metadata và query gửi |
| Query JSON từ tham số user bị lỗi | Ghép String JSON không an toàn/sai escape | Dùng placeholder hoặc `Criteria` |
| Index hint không xuất hiện như mong đợi | API/operation/version không áp dụng như dự tính | Kiểm tra plan thực tế và khả năng của phiên bản |

## 15. Bài thực hành có lời giải

### Bài 1 — Sort hàng đợi ổn định

**Đề bài:** Lấy tối đa 20 đơn chờ giao của `tenant-a` theo thời gian mới nhất. Nhiều document có thể cùng `createdAt`.

**Lời giải:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Khóa `_id` làm tie-break. Nếu truy vấn quan trọng và collection lớn, cân nhắc compound index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` rồi đo `explain`.

### Bài 2 — Sort tiếng Việt

**Đề bài:** Danh sách tên khách cần so sánh theo tiếng Việt và có phân biệt dấu ở mức secondary.

**Lời giải:**

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 });
```

Để tăng tốc, cần index có cấu hình collation tương ứng và đo bằng dữ liệu thật. Thử fixture như `An`, `Ân`, `Bình`, `Đức`; không tự áp thứ tự nhị phân như chuẩn ngôn ngữ.

### Bài 3 — Tại sao index tên khách chưa được dùng?

**Đề bài:** Collection có index `{ tenantId: 1, customerName: 1 }` nhưng được tạo bằng simple collation. Query sort tên với `locale: "vi", strength: 2` vẫn có stage sort.

**Lời giải:** Query dùng quy tắc so sánh khác với index đối với String, nên index simple có thể không dùng được để đáp ứng thứ tự tên tiếng Việt. Tạo index collation thích hợp nếu workload cần; không sửa bằng cách tắt collation để «dùng được index» khi đó làm sai yêu cầu nghiệp vụ.

### Bài 4 — Thử hint để so sánh plan

**Đề bài:** Một index tên `ix_orders_tenant_status_recent` đã tồn tại. Hãy yêu cầu server dùng index đó và xem kế hoạch thực thi.

**Lời giải:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20)
  .explain("executionStats");
```

So sánh với cùng truy vấn **không hint**. Nếu hint làm tăng keys/docs examined, cần xem lại giả thuyết thay vì giữ hint vì «chắc chắn dùng index».

### Bài 5 — Chọn repository hay MongoTemplate

**Đề bài:** Một màn hình cố định luôn sắp theo thời gian; màn hình khác cho phép nhân viên đổi locale giữa vài giá trị đã duyệt và thử index khi chẩn đoán.

**Lời giải:** Màn hình có query cố định có thể dùng `@Query(sort = "...")` với `Pageable` giới hạn, tùy phiên bản. Màn hình cần thay đổi runtime nên dùng `MongoTemplate` để tạo `Query`, `Sort`, `Collation` và tùy chọn hint một cách có kiểm soát, kiểm tra version và có integration test cho mỗi locale được hỗ trợ.

### Bài 6 — Vì sao không phải mọi sort đều cần hint?

**Đề bài:** Q1 có index tốt, planner đã chọn index đó và `explain` cho thấy scan thấp, không có sort tốn tài nguyên. Có nên thêm `@Query(hint = "...")`?

**Lời giải:** Không có lý do rõ ràng. Hint làm tăng sự phụ thuộc vào tên/index cụ thể và có thể gây lỗi khi migration index. Nếu plan đã tốt, nên giữ truy vấn đơn giản và tiếp tục đo thay vì cố định index không cần thiết.

### Bài 7 — Sort và phân trang

**Đề bài:** Ứng dụng chỉ sort theo `createdAt DESC`; hai đơn có cùng thời gian. Người dùng thấy kết quả lặp khi chuyển trang.

**Lời giải:** Thêm khóa phá hòa như `_id DESC`, giữ nguyên sort trên mọi trang. Nếu vẫn lặp khi có chèn/xóa đồng thời, đánh giá cursor/keyset pagination thay vì chỉ dựa vào offset. Cursor phải mang đủ các sort key và dùng kiểu BSON/độ mạnh collation nhất quán.

## 16. Checklist trước khi bàn giao truy vấn

| Câu hỏi review | Bằng chứng cần xác nhận |
| --- | --- |
| Query có filter đúng tenant/owner không? | Query BSON và test phân quyền |
| Sort keys/hướng sort có thể hiện nghiệp vụ không? | `sort` tường minh và test thứ tự |
| Có khóa phá hòa ổn định không? | `_id` hoặc khóa duy nhất thích hợp |
| Có giới hạn kết quả/phân trang không? | `limit`, `Slice`/`Pageable` hoặc cursor |
| Collation có thật sự cần không? | Yêu cầu ngôn ngữ và fixture so sánh |
| Locale/strength có chính xác không? | Test tên có dấu/hoa thường/case |
| Index được tạo với collation nào? | Kết quả `getIndexes()` và migration |
| Hint có bằng chứng lợi ích không? | So sánh `explain` với query không hint |
| Có nguy cơ index bị đổi/xóa không? | Quy trình migration/triển khai đồng bộ |
| Phiên bản Spring Data hỗ trợ thuộc tính nào? | API của dependency thực tế, compile/integration test |
| Server/driver có hỗ trợ tùy chọn trên operation đó? | Thử trên cùng loại operation trong môi trường test |
| Sort động có whitelist không? | Kiểm soát field/chiều sort ở service |
| Query JSON có binding tham số đúng không? | Placeholder/Criteria, không ghép chuỗi tùy tiện |
| Có đo trên dữ liệu đủ đại diện không? | Keys/docs examined, sort stage, độ trễ và tải |

### Ghi nhớ

1. `sort` quyết định thứ tự; thêm khóa phá hòa để ổn định kết quả, đặc biệt khi phân trang.
2. `collation` quyết định cách so sánh chuỗi, không chỉ cách hiển thị; query và index cần dùng quy tắc tương thích nếu muốn tận dụng index cho so sánh/sort.
3. `hint` là công cụ điều khiển kế hoạch index **có điều kiện**, không phải cách sửa một query sai hoặc lời bảo đảm về hiệu năng.
4. `@Query`, `MongoTemplate` và mongosh có **cú pháp và phạm vi hỗ trợ khác nhau**. Luôn xác minh với đúng Spring Data, driver và MongoDB server của dự án.
5. Kiểm tra kết quả và hiệu năng độc lập: test đúng dữ liệu, test thứ tự, kiểm tra collation, sau đó dùng `explain("executionStats")` để đánh giá kế hoạch thực thi.
