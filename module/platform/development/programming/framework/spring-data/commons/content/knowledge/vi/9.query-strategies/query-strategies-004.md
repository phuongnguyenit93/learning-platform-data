# Phạm vi @Query, ngôn ngữ truy vấn và cú pháp bind theo store

Trong Spring Data, hai repository cùng kế thừa `Repository` hoặc `CrudRepository` không có nghĩa là chúng dùng chung một ngôn ngữ truy vấn. Nhiều module cung cấp annotation có cùng tên đơn giản `@Query`, nhưng ngôn ngữ, placeholder và cách ánh xạ kết quả của chúng khác nhau.

Trong phạm vi Spring Data Commons, điều cần nắm là ranh giới giữa abstraction dùng chung và khả năng do từng store cung cấp. Một yêu cầu như “tìm đơn hàng của tenant theo trạng thái” có thể được viết bằng JPQL, SQL, bộ lọc MongoDB, CQL, Cypher hoặc Elasticsearch Query DSL; mỗi cách có những điều kiện riêng.

Sau bài này, bạn cần có khả năng:

- Xác định `@Query` thuộc module nào bằng tên import đầy đủ.
- Phân biệt ngôn ngữ truy vấn, placeholder và hình dạng kết quả.
- Chọn cách bind giá trị đúng cho store, nhất là tham số theo vị trí và theo tên.
- Nhận ra yêu cầu cần API dựng truy vấn hoặc repository fragment.
- Chuyển yêu cầu nghiệp vụ sang store khác mà vẫn xem xét mô hình dữ liệu và khả năng truy vấn.

## 1. Ranh giới giữa Commons và module của store

Spring Data Commons cung cấp các abstraction như repository, metadata phương thức truy vấn, `Pageable`, `Sort`, `Page` và các cơ chế hỗ trợ dùng chung. Module của store kết nối những abstraction đó với hệ thống lưu trữ.

Không có annotation `org.springframework.data.repository.Query` làm ngôn ngữ truy vấn chung cho mọi store. Những import dưới đây là các kiểu khác nhau:

```java
// JPQL hoặc SQL native trong Spring Data JPA
import org.springframework.data.jpa.repository.Query;

// SQL trong Spring Data JDBC
import org.springframework.data.jdbc.repository.query.Query;

// SQL trong Spring Data R2DBC
import org.springframework.data.r2dbc.repository.Query;

// Bộ lọc tài liệu trong Spring Data MongoDB
import org.springframework.data.mongodb.repository.Query;
```

Một file Java chỉ import annotation phù hợp với repository đang khai báo; không dán đồng thời các import cùng tên trên vào một file.

Ngược lại, annotation sau thuộc phần dùng chung:

```java
import org.springframework.data.repository.query.Param;
```

Sự tồn tại của `@Param` không làm `:name` trở thành cú pháp hợp lệ trong mọi chuỗi truy vấn. Store phải hỗ trợ cơ chế bind theo tên tương ứng.

Đường đi của một lời gọi có thể hình dung như sau:

```text
Lời gọi phương thức repository
        ↓
Metadata phương thức và tham số
        ↓
Bộ xử lý truy vấn của module store
        ↓
Phân tích truy vấn → bind giá trị → thực thi
        ↓
Ánh xạ kết quả sang entity/document/projection/kiểu trả về
```

Một phương thức đúng chữ ký Java vẫn có thể thất bại khi phân tích ngôn ngữ, bind tham số, thực thi trên store hoặc ánh xạ kết quả.

## 2. Đặt @Query trong chiến lược truy vấn

| Cách tiếp cận | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Derived query | Module tạo truy vấn từ tên phương thức | Điều kiện đơn giản, tên phương thức còn dễ đọc |
| Truy vấn khai báo | Cung cấp truy vấn bằng cơ chế như `@Query` hoặc named query mà module hỗ trợ | Cần thể hiện rõ và kiểm soát cấu trúc truy vấn tĩnh |
| Repository fragment/API của store | Tự triển khai truy vấn bằng template hoặc client phù hợp | Bộ lọc thay đổi nhiều, cấu trúc động hoặc cần khả năng đặc thù |

Query lookup strategy quyết định repository tìm truy vấn khai báo hay tạo truy vấn từ tên phương thức. Những tên như `CREATE`, `USE_DECLARED_QUERY`, `CREATE_IF_NOT_FOUND` mô tả cách tìm/tạo truy vấn; khả năng cấu hình cụ thể thuộc module đang dùng.

Query lookup strategy không dịch JPQL thành bộ lọc MongoDB hoặc SQL thành Cypher. Khi chọn một truy vấn khai báo, bạn vẫn phải viết đúng ngôn ngữ mà store hỗ trợ.

Không nên thêm `@Query` chỉ vì cho rằng nó mặc nhiên nhanh hơn derived query. Hiệu năng phụ thuộc truy vấn thực tế, index, lượng dữ liệu và kế hoạch thực thi của hệ thống lưu trữ.

## 3. Bản đồ ngôn ngữ và placeholder theo store

Bảng dưới mô tả các cách dùng tiêu biểu, không cam kết mọi module hỗ trợ toàn bộ biến thể của nhau.

| Module | Annotation `@Query` | Nội dung truy vấn | Bind tiêu biểu |
|---|---|---|---|
| JPA | `org.springframework.data.jpa.repository.Query` | JPQL mặc định; SQL khi chọn native | `?1`, `?2`; `:tenantId` với `@Param` |
| JDBC | `org.springframework.data.jdbc.repository.query.Query` | SQL theo hệ quản trị quan hệ | `:tenantId` với `@Param` |
| R2DBC | `org.springframework.data.r2dbc.repository.Query` | SQL theo hệ quản trị quan hệ | `:tenantId`; bind marker native phụ thuộc driver |
| MongoDB | `org.springframework.data.mongodb.repository.Query` | Bộ lọc dạng JSON | `?0`, `?1` |
| Cassandra | `org.springframework.data.cassandra.repository.Query` | CQL | `?0`, `?1`; hoặc `:tenantId` với `@Param` |
| Neo4j | `org.springframework.data.neo4j.repository.query.Query` | Cypher | `$tenantId` với `@Param` |
| Elasticsearch | `org.springframework.data.elasticsearch.annotations.Query` | Query clause JSON của Query DSL | `?0`, `?1` trong mẫu truy vấn |

Hai chi tiết dễ nhầm:

1. Vị trí tham số JPQL bắt đầu từ `?1`; các mẫu MongoDB, Cassandra và Elasticsearch ở trên dùng `?0` cho đối số đầu tiên.
2. Dấu `$` không mang cùng nghĩa ở mọi nơi: `$tenantId` là tham số Cypher, `$gte` là toán tử MongoDB, còn `$1` có thể là bind marker của driver PostgreSQL trong ngữ cảnh SQL.

Với những store khác, chẳng hạn Redis, không suy ra rằng có thể dùng SQL, JPQL hoặc JSON như các ví dụ chỉ vì repository cũng thuộc Spring Data. Phải bắt đầu từ cơ chế truy vấn mà module đó thực sự cung cấp.

## 4. Hiểu đúng việc bind tham số

### 4.1. Bind giá trị không phải thay cấu trúc truy vấn

Bind là truyền giá trị vào vị trí tham số mà module hỗ trợ. Giá trị có thể là chuỗi, số, thời điểm, collection hoặc kiểu được converter xử lý; khả năng cụ thể phụ thuộc store và vị trí sử dụng.

Ví dụ:

```sql
where tenant_id = :tenantId
```

Không suy ra rằng cách tương tự sẽ thay được tên bảng hoặc cột:

```sql
-- Không dùng bind giá trị để chọn tên bảng hoặc tên cột.
select * from :tableName where :columnName = :value
```

Trong JPQL, `order by :sortProperty` cũng không phải cách chọn thuộc tính sắp xếp theo tên. Truyền chuỗi `"createdAt"` không làm tham số trở thành định danh.

Nếu cần thay cấu trúc, hãy dùng `Sort` khi loại truy vấn đó hỗ trợ, API dựng truy vấn hoặc repository fragment. Tên trường và hướng sắp xếp từ bên ngoài phải được giới hạn trong tập ứng dụng cho phép.

### 4.2. Bind theo tên và theo vị trí có hợp đồng riêng

Với module hỗ trợ named parameter, có thể thể hiện ánh xạ rõ ràng:

```java
@Param("tenantId") String tenantId
```

Nếu truy vấn dùng `:tenantId` nhưng annotation ghi `@Param("tenant")`, tên không khớp. Tên biến Java tình cờ đúng không sửa được annotation sai.

Một số cơ chế có thể phát hiện tên tham số từ metadata biên dịch, chẳng hạn khi bật `-parameters`. Dùng `@Param` tường minh giúp thấy rõ hợp đồng và tránh phụ thuộc không cần thiết vào cấu hình biên dịch.

Với positional parameter, thay đổi thứ tự đối số phương thức có thể làm thay đổi ý nghĩa bind. Hai tham số cùng kiểu `String` đặc biệt dễ bị đổi chỗ mà trình biên dịch không phát hiện.

### 4.3. Dấu nháy phụ thuộc ngữ cảnh

Trong JPQL, SQL và CQL, không bọc placeholder như một chuỗi literal:

```sql
-- Sai nếu mục tiêu là bind giá trị:
where tenant_id = ':tenantId'
```

Dạng này có thể so sánh với chuỗi literal `:tenantId` thay vì tham số.

Tuy nhiên, không áp dụng máy móc quy tắc đó cho mọi annotation JSON. Mẫu Elasticsearch thường viết tham số chuỗi là `"?0"`; MongoDB thường dùng `?0` trực tiếp ở vị trí giá trị. Cần hiểu placeholder trong đúng parser của module.

### 4.4. Kiểu, null và collection

- `String` chứa UUID không nhất thiết được xử lý giống đối số Java kiểu `UUID`.
- Enum có thể được lưu thành chuỗi, số hoặc kiểu đặc thù theo mapping.
- Timestamp cần phù hợp múi giờ và độ chính xác khi ghi dữ liệu.
- Trong SQL/JPQL, `field = :value` không tự biến thành `field is null` khi đối số bằng `null`.
- MongoDB có quy tắc riêng cho giá trị `null` và trường không tồn tại.
- Collection trong `IN` cần được module hỗ trợ; danh sách rỗng cần chính sách rõ ràng ở ứng dụng.

Hành vi xử lý `null` của derived query không phải quy tắc tự viết lại mọi chuỗi `@Query`.

## 5. Spring Data JPA: JPQL mặc định, SQL khi chọn native

Các ví dụ trong bài là những đoạn độc lập theo store. Giả sử entity/document, repository scanning và kết nối đã được cấu hình. Không dùng nguyên một lớp domain cho mọi module mà bỏ qua mapping riêng.

Với JPA, giả sử entity có tên `PurchaseOrder`, gồm các thuộc tính Java `id`, `tenantId`, `status`, `createdAt`, `total`. Trong ví dụ, `status` có kiểu `String`. Entity được ánh xạ tới bảng `purchase_order`, với các cột như `tenant_id`, `created_at`.

### 5.1. JPQL dùng entity và thuộc tính

```java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface JpaOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        order by o.createdAt desc
        """)
    List<PurchaseOrder> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status
    );
}
```

Các text block trong bài dùng cú pháp Java hỗ trợ text block; đổi thành chuỗi thông thường nếu dự án sử dụng cú pháp Java cũ hơn.

Điểm cần quan sát:

- `PurchaseOrder` là tên entity JPA, có thể được tùy chỉnh bằng `@Entity(name = ...)`.
- `tenantId`, `status`, `createdAt` là các thuộc tính entity.
- `:tenantId`, `:status` là tên tham số.
- Không thay `PurchaseOrder` bằng `purchase_order` nếu vẫn dùng JPQL.

Một phiên bản bind theo vị trí:

```java
@Query("""
    select o from PurchaseOrder o
    where o.tenantId = ?1 and o.status = ?2
    """)
List<PurchaseOrder> findOrdersByPosition(String tenantId, String status);
```

Đối số đầu tiên gắn với `?1`. Khi đổi thứ tự tham số phương thức, phải cập nhật truy vấn tương ứng. Không trộn named parameter và positional parameter trong cùng truy vấn để tìm cách bù cho nhau.

### 5.2. SQL native dùng bảng và cột

```java
@Query(value = """
    select po.id
    from purchase_order po
    where po.tenant_id = :tenantId
      and po.status = :status
    """, nativeQuery = true)
List<Long> findOrderIdsNative(
    @Param("tenantId") String tenantId,
    @Param("status") String status
);
```

Ở đây, `purchase_order`, `tenant_id` là định danh trong cơ sở dữ liệu. Hàm, kiểu dữ liệu và cú pháp giới hạn kết quả chịu ràng buộc của hệ quản trị. Ví dụ chỉ chọn một cột ID và giả định nó được ánh xạ thành `Long`.

Khả năng bind named parameter trong native query thuộc bối cảnh Spring Data JPA và JPA provider đang dùng. Không coi đó là đảm bảo cho mọi cách gọi native SQL qua mọi provider.

Nếu trả về entity, DTO hoặc projection, tập cột và alias phải khớp cơ chế ánh xạ. SQL chạy được trong công cụ quản trị cơ sở dữ liệu chưa chứng minh repository ánh xạ được kết quả.

### 5.3. Phân trang là hợp đồng bổ sung

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query(
    value = """
        select o from PurchaseOrder o
        where o.tenantId = :tenantId and o.status = :status
        """,
    countQuery = """
        select count(o) from PurchaseOrder o
        where o.tenantId = :tenantId and o.status = :status
        """
)
Page<PurchaseOrder> findOrderPage(
    @Param("tenantId") String tenantId,
    @Param("status") String status,
    Pageable pageable
);
```

`Pageable` điều khiển truy vấn, không phải giá trị nghiệp vụ để bind bằng `:pageable`. Muốn trả về `Page`, cần có cách xác định tổng số phần tử; truy vấn phức tạp cần chú ý cách đếm.

Không sao chép `countQuery` từ JPA sang annotation store khác chỉ vì cùng tên `@Query`. Native query phức tạp, phép nhóm, `distinct` hoặc join cần xem riêng về số dòng và cách áp dụng sắp xếp.

### 5.4. Truy vấn cập nhật có yêu cầu riêng

Trong Spring Data JPA, `update` hoặc `delete` khai báo qua `@Query` cần cơ chế modifying tương ứng, thường là `@Modifying`, cùng ranh giới transaction phù hợp. Bulk update còn có thể khiến dữ liệu trong persistence context không đồng bộ với cơ sở dữ liệu.

Chỉ thêm `@Query("update ...")` vào phương thức trả về entity không làm nó tự trở thành thao tác cập nhật hợp lệ. Annotation và hợp đồng thực thi modifying query cũng thuộc từng module.

## 6. Spring Data JDBC: @Query chứa SQL

Giả sử aggregate `PurchaseOrder` có mapping đúng tới bảng và cột tương ứng:

```java
import java.util.List;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface JdbcOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        select id, tenant_id, status, created_at, total
        from purchase_order
        where tenant_id = :tenantId
          and status = :status
        order by created_at desc
        """)
    List<PurchaseOrder> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status
    );
}
```

Đây là SQL. Viết `select o from PurchaseOrder o` như ví dụ JPA là sai ngữ cảnh.

Khi trả về aggregate, các cột phải đáp ứng mapping và constructor được dùng để tạo đối tượng. Nếu chỉ lấy vài cột, cần thiết kế kiểu kết quả hoặc cơ chế ánh xạ phù hợp.

Với SQL tự khai báo, không suy ra rằng thêm `Pageable`, `Sort` hoặc `Limit` vào chữ ký là module tự viết lại SQL. Phải xác định khả năng của loại query và phiên bản đang dùng. Nếu tự triển khai pagination, cú pháp giới hạn kết quả và cách tính tổng cũng phải phù hợp hệ quản trị.

## 7. Spring Data R2DBC: SQL với thực thi reactive

R2DBC dùng SQL trong `@Query`, nhưng thuộc module khác và có hợp đồng thực thi reactive:

```java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface R2dbcOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    @Query("""
        select id, tenant_id, status, created_at, total
        from purchase_order
        where tenant_id = :tenantId
          and status = :status
        order by created_at desc
        """)
    Flux<PurchaseOrder> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status
    );
}
```

Cần tách hai vấn đề:

- **Ngôn ngữ:** SQL phụ thuộc hệ quản trị, tên bảng, tên cột và kiểu dữ liệu.
- **Thực thi:** `Flux` biểu diễn luồng kết quả reactive; điều đó không làm SQL trở thành ngôn ngữ mới.

Named parameter của truy vấn repository có thể được hạ xuống bind marker tương ứng của driver. Trong ngữ cảnh driver PostgreSQL có thể gặp `$1`, `$2`; driver khác có thể dùng hình thức khác. Không áp dụng `$1` tùy tiện cho JPQL hoặc coi nó là `$tenantId` của Cypher.

Đổi `List<T>` sang `Flux<T>` cũng không đủ để chuyển repository JDBC thành R2DBC. Cần đúng module, kết nối, mapping, transaction và chuỗi xử lý reactive.

## 8. Spring Data MongoDB: JSON mô tả bộ lọc tài liệu

Giả sử `PurchaseOrderDocument` có các trường `tenantId`, `status`, `createdAt`, và `createdAt` được ánh xạ phù hợp sang thời điểm lưu trong MongoDB:

```java
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface MongoOrderRepository
        extends MongoRepository<PurchaseOrderDocument, String> {

    @Query("""
        {
          'tenantId': ?0,
          'status': ?1,
          'createdAt': { '$gte': ?2 }
        }
        """)
    List<PurchaseOrderDocument> findOrders(
        String tenantId,
        String status,
        Instant createdFrom
    );
}
```

Trong mẫu này:

- `?0` bind `tenantId`, đối số đầu tiên.
- `?1` bind `status`.
- `?2` bind `createdFrom` qua cơ chế chuyển đổi phù hợp.
- `$gte` là toán tử “lớn hơn hoặc bằng” của MongoDB.
- Các thuộc tính được xử lý theo mapping tài liệu của module; nếu đổi tên trường lưu trữ, phải xét mapping tương ứng.

Đây là mẫu do Spring Data xử lý, không phải tài liệu JSON hoàn chỉnh để gửi nguyên văn khi còn `?0` hoặc dấu nháy đơn. Parser JSON thuần không thay thế cho việc hiểu cú pháp annotation.

Ví dụ sai ngữ cảnh:

```java
// Sai: JPQL nằm trong annotation MongoDB.
@Query("select o from PurchaseOrder o where o.tenantId = :tenantId")
```

Thêm `@Param("tenantId")` cũng không mặc nhiên cho phép viết `:tenantId` như SQL. Placeholder trong ví dụ MongoDB trên là `?0`, `?1`, `?2`.

Thuộc tính `fields` có thể chọn trường trả về, nhưng không phải mệnh đề `select` của JPQL. Trả về một phần tài liệu cần phối hợp với projection hoặc kiểu kết quả phù hợp, nhất là khi constructor yêu cầu trường bị loại bỏ.

Nếu cần pipeline aggregation, hãy dùng cơ chế aggregation mà module hỗ trợ. Bộ lọc `@Query` không phải nơi chứa tùy ý mọi dạng lệnh MongoDB.

## 9. Spring Data Cassandra: CQL bị ràng buộc bởi mô hình khóa

CQL trông gần SQL, nhưng truy vấn đọc còn phụ thuộc partition key, clustering key và cách tổ chức dữ liệu.

Giả sử có bảng phục vụ tìm đơn hàng theo tenant và trạng thái:

```sql
CREATE TABLE orders_by_tenant_status (
    tenant_id text,
    status text,
    created_at timestamp,
    order_id uuid,
    total decimal,
    PRIMARY KEY ((tenant_id, status), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

`(tenant_id, status)` là composite partition key. Truy vấn cung cấp đủ hai thành phần đó và giới hạn theo clustering column `created_at`:

```java
import java.time.Instant;
import java.util.List;

import org.springframework.data.cassandra.repository.Query;

// Đặt trong Cassandra repository đã cấu hình,
// với entity và khóa được ánh xạ đúng tới bảng ở trên.
@Query("""
    select * from orders_by_tenant_status
    where tenant_id = ?0
      and status = ?1
      and created_at >= ?2
    """)
List<OrderByTenantStatus> findRecentOrders(
    String tenantId,
    String status,
    Instant createdFrom
);
```

Một cách biểu diễn theo tên:

```java
import org.springframework.data.repository.query.Param;

@Query("""
    select * from orders_by_tenant_status
    where tenant_id = :tenantId
      and status = :status
      and created_at >= :createdFrom
    """)
List<OrderByTenantStatus> findRecentOrdersByName(
    @Param("tenantId") String tenantId,
    @Param("status") String status,
    @Param("createdFrom") Instant createdFrom
);
```

Hai phương thức minh họa cùng một cách truy cập; không cần giữ cả hai trong ứng dụng nếu không có nhu cầu riêng.

Bind đúng chỉ giải quyết cách truyền giá trị. Nó không làm truy vấn thiếu partition key trở thành lựa chọn hiệu quả. Nếu cần tìm toàn bộ đơn hàng của tenant bất kể trạng thái, phải xem lại mô hình bảng hoặc phương án truy vấn; không mặc định thêm `ALLOW FILTERING` sẽ giải quyết được thiết kế.

## 10. Spring Data Neo4j: Cypher dùng tham số $name

Giả sử graph có node mang label `PurchaseOrder`, với các thuộc tính `tenantId`, `status`, `createdAt`:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface GraphOrderRepository
        extends Neo4jRepository<PurchaseOrderNode, Long> {

    @Query("""
        MATCH (o:PurchaseOrder)
        WHERE o.tenantId = $tenantId
          AND o.status = $status
        RETURN o
        ORDER BY o.createdAt DESC
        """)
    List<PurchaseOrderNode> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status
    );
}
```

Các điểm phân biệt:

- `MATCH`, `WHERE`, `RETURN` là cấu trúc Cypher.
- `:PurchaseOrder` trong mẫu node biểu diễn label, không phải named parameter SQL.
- `$tenantId`, `$status` là tham số giá trị.
- `@Param` nối tên trong phương thức với tên tham số Cypher.

Nếu domain có relationship, chỉ `RETURN o` không đồng nghĩa đã lấy đủ node và relationship để dựng toàn bộ aggregate. Custom query phải trả về hình dạng kết quả phù hợp mapping của Spring Data Neo4j.

Không coi `$label` hoặc `$relationshipType` là cách thay cấu trúc graph dùng phổ quát ở mọi phiên bản Cypher. Khi cần label hoặc loại relationship động, phải dùng đúng khả năng của phiên bản đang chạy và cơ chế dựng truy vấn được hỗ trợ.

## 11. Spring Data Elasticsearch: JSON của Query DSL

Giả sử `PurchaseOrderSearchDocument` được ánh xạ vào index phù hợp, trong đó `tenantId`, `status` là các trường `keyword` để so khớp chính xác:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface SearchOrderRepository
        extends ElasticsearchRepository<PurchaseOrderSearchDocument, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              { "term": { "tenantId": "?0" } },
              { "term": { "status": "?1" } }
            ]
          }
        }
        """)
    List<PurchaseOrderSearchDocument> findOrders(
        String tenantId,
        String status
    );
}
```

Ở đây:

- Chuỗi là một query clause JSON của Elasticsearch Query DSL.
- `?0`, `?1` tham chiếu đối số phương thức trong mẫu truy vấn.
- Placeholder của giá trị chuỗi được đặt trong chuỗi JSON theo cú pháp mẫu của module.
- `term` dùng với giả định các trường đã được mapping thành `keyword`.

Không tùy ý thêm lớp bọc `{"query": ...}` hoặc thuộc tính của toàn bộ search request vào vị trí đang nhận query clause. Cấu trúc annotation chờ đợi phải khớp API của module.

Nếu trường là `text` có analyzer, kết quả của `term` và truy vấn full-text như `match` có thể rất khác. Bind thành công không bù được việc chọn sai loại truy vấn so với index mapping.

JSON MongoDB và JSON Query DSL Elasticsearch là hai ngôn ngữ khác nhau. Cùng dùng dấu ngoặc nhọn không làm `{ 'status': ?0 }` và `{ "term": { "status": "?0" } }` thay thế trực tiếp cho nhau.

## 12. Biểu thức trong truy vấn không phải cơ chế portable

Một số module hỗ trợ biểu thức trong chuỗi truy vấn, có thể liên quan SpEL hoặc evaluation context do Spring Data cung cấp. Phạm vi hỗ trợ, delimiter, biến có sẵn và thời điểm đánh giá phụ thuộc module, phiên bản.

Ví dụ, Spring Data JPA có cơ chế tham chiếu tên entity trong truy vấn hỗ trợ biểu thức:

```java
@Query("select e from #{#entityName} e where e.tenantId = :tenantId")
List<PurchaseOrder> findForTenant(@Param("tenantId") String tenantId);
```

`#{#entityName}` được giải quyết trong ngữ cảnh JPA, còn `:tenantId` vẫn là tham số giá trị. Không sao chép nguyên biểu thức đó sang SQL JDBC, CQL hoặc JSON và mong module khác hiểu cùng nghĩa.

Các dạng `#{...}`, `?#{...}`, `:#{...}` không phải ba cách viết tương đương ở mọi store. Khi cần biểu thức, phải xác định:

1. Annotation cụ thể có hỗ trợ dạng biểu thức đó không.
2. Biểu thức tạo giá trị hay tham gia tạo cấu trúc truy vấn.
3. Những biến và đối tượng nào có trong evaluation context.
4. Đầu vào người dùng đi vào tham số giá trị hay bị ghép vào mã biểu thức.

Không nhận một đoạn biểu thức tùy ý từ request rồi ghép vào truy vấn. Với nhiều điều kiện tùy chọn, API dựng truy vấn hoặc repository fragment thường dễ thể hiện và kiểm soát hơn một chuỗi biểu thức dài.

## 13. Những khả năng không thể suy ra chỉ từ @Query

### 13.1. Pagination và sorting không đồng nhất

`Pageable`, `Sort` là các kiểu dùng chung, nhưng cách áp dụng chúng vào truy vấn khai báo thuộc module. Có trường hợp dùng offset, có trường hợp cần cursor hoặc paging state; truy vấn đếm có thể tốn kém hoặc không phù hợp.

Khi thiết kế API, cần xác định:

- Người gọi cần tổng số phần tử hay chỉ cần biết còn trang tiếp theo.
- Store và loại query hỗ trợ kiểu trả về nào.
- Thứ tự kết quả có ổn định không; có cần khóa phân xử khi nhiều bản ghi cùng giá trị sắp xếp không.
- Điều kiện, sắp xếp và giới hạn kết quả được áp dụng bằng cơ chế nào.

Không gán khả năng của `Page<T>` trong truy vấn JPA cho mọi repository cùng kế thừa abstraction của Commons.

### 13.2. Projection phải khớp hình dạng kết quả

| Ngữ cảnh | Điều phải xem xét |
|---|---|
| JPQL | Entity, scalar, interface projection hoặc constructor expression phù hợp |
| SQL native/JDBC/R2DBC | Cột, alias, kiểu dữ liệu và cơ chế tạo đối tượng |
| MongoDB | Trường được chọn và yêu cầu của projection/constructor |
| Neo4j | Node, relationship và cấu trúc bản ghi trả về |
| Elasticsearch | Trường document và cách ánh xạ search result |

Truy vấn bind đúng nhưng thiếu dữ liệu cho constructor vẫn có thể lỗi khi ánh xạ. Ngược lại, kiểu kết quả chỉ có vài thuộc tính không tự chứng minh store đã giảm lượng dữ liệu cần đọc hoặc truyền về.

### 13.3. Tenant và phân quyền là điều kiện nghiệp vụ

Tham số hóa truyền giá trị theo cơ chế của module; nó không tự áp dụng phân quyền. Trong các ví dụ, `tenantId` nằm trực tiếp trong điều kiện để thể hiện phạm vi cần đọc.

Trong ứng dụng nhiều tenant, phương thức có đối số tên `tenantId` chưa chứng minh dữ liệu đã được cô lập. Phải có điều kiện thật trong truy vấn hoặc cơ chế cô lập tương ứng đã được thiết kế. Nguồn giá trị tenant cũng phải phù hợp ngữ cảnh đã xác thực.

Nếu truy vấn dữ liệu và truy vấn đếm có điều kiện khác nhau, kết quả phân trang còn có thể tiết lộ số bản ghi ngoài phạm vi người gọi được phép xem.

### 13.4. Binding không quyết định index và chi phí truy vấn

Truy vấn không nối chuỗi thủ công vẫn có thể chậm do thiếu index, đọc quá nhiều partition, sort lớn hoặc chọn sai trường tìm kiếm. Kiểm tra binding và đánh giá mô hình truy cập dữ liệu không thay thế nhau.

Với `LIKE`, bind chuỗi không loại bỏ ý nghĩa đặc biệt của `%`, `_`. Nếu cần tìm literal chứa các ký tự đó, phải có quy tắc escape phù hợp ngôn ngữ và hệ quản trị. Giá trị dùng làm regex hoặc search expression cũng có ngữ nghĩa riêng của toán tử nhận nó.

## 14. Chẩn đoán lỗi theo từng lớp

| Biểu hiện | Câu hỏi cần kiểm tra | Ví dụ nguyên nhân |
|---|---|---|
| Repository không tạo được hoặc truy vấn không parse được | Đúng import và ngôn ngữ chưa? | SQL trong `@Query` JPA nhưng chưa chọn native |
| Không bind được tham số | Tên, chỉ số và số đối số có khớp không? | `?0` trong JPQL; `:status` nhưng `@Param("state")` |
| Cơ sở dữ liệu báo không có bảng/cột | Có dùng đúng tên của lớp đang truy vấn không? | `tenantId` thay cho `tenant_id` trong SQL |
| Truy vấn chạy nhưng không có kết quả | Kiểu và ngữ nghĩa toán tử có đúng không? | `term` không phù hợp mapping hoặc mục đích tìm kiếm |
| Lỗi tạo đối tượng kết quả | Có đủ cột/trường và alias theo mapping không? | Chỉ chọn ID nhưng trả về aggregate cần nhiều dữ liệu |
| Truy vấn Cassandra không phù hợp | Điều kiện có khớp partition/clustering key không? | Bỏ thành phần partition key |
| Có dữ liệu ngoài tenant | Tenant có thật sự nằm trong điều kiện không? | Có đối số tenant nhưng truy vấn không dùng |
| Phân trang sai hoặc chậm | Giới hạn, đếm và sắp xếp có phù hợp không? | Count query thiếu điều kiện; kỳ vọng tự rewrite SQL |

Lỗi có thể xuất hiện khi tạo repository hoặc khi thực thi phương thức, tùy module và loại query. Khởi động ứng dụng thành công chưa chứng minh mọi truy vấn và biến thể tham số đều đúng.

Khi thực hành trong một dự án, nên kiểm chứng các trường hợp có kết quả, không có kết quả, dữ liệu tenant khác, giá trị có dấu nháy, cùng giá trị biên thực sự được API cho phép như `null` hoặc collection rỗng. Mục đích là kiểm chứng hợp đồng với store thực tế và mapping, không chỉ kiểm tra chuỗi có chứa tên tham số.

## 15. Bài tập vận dụng

### Bài tập 1: Đọc import trước khi đọc truy vấn

```java
import org.springframework.data.jpa.repository.Query;

@Query("select * from purchase_order where tenant_id = ?0")
List<PurchaseOrder> findOrders(String tenantId);
```

Hãy chỉ ra các giả định sai và đề xuất hai hướng sửa.

**Gợi ý lời giải:** Annotation ở chế độ JPQL mặc định, nhưng chuỗi viết theo SQL và dùng chỉ số bắt đầu từ `0`. Có thể chuyển sang JPQL với tên entity/thuộc tính và `?1`; hoặc chọn native query, dùng SQL đúng hệ quản trị và cơ chế bind phù hợp, đồng thời bảo đảm tập cột ánh xạ được sang kết quả.

### Bài tập 2: Chuyển yêu cầu sang MongoDB

Yêu cầu: tìm đơn hàng của tenant, có trạng thái xác định, được tạo từ một thời điểm trở đi. Vì sao không thể đổi import từ JPA sang MongoDB rồi giữ nguyên chuỗi JPQL?

**Gợi ý lời giải:** Giữ ý nghĩa nghiệp vụ và các giá trị cần truyền, nhưng viết lại thành bộ lọc tài liệu với `?0`, `?1`, `?2` và `$gte`; xem lại mapping thời gian, tên trường, index và kiểu kết quả. Repository dùng chung không cung cấp bộ dịch JPQL sang MongoDB.

### Bài tập 3: Chọn cấu trúc sắp xếp

API nhận `sortField` từ request. Lập trình viên viết `order by :sortField` rồi bind chuỗi `"createdAt"`. Cách này có chọn được thuộc tính sắp xếp không?

**Gợi ý lời giải:** Đây là tham số giá trị, không phải cách chọn định danh. Giới hạn trường được phép sắp xếp, sau đó áp dụng qua `Sort` được hỗ trợ hoặc API dựng truy vấn/fragment phù hợp. Kiểm tra riêng khả năng áp dụng sort cho loại query đang dùng.

### Bài tập 4: Cassandra bind đúng nhưng truy vấn không phù hợp

Với bảng `orders_by_tenant_status` ở trên, phương thức chỉ lọc `tenant_id = ?0` và `created_at >= ?1`. Đổi sang named parameter có giải quyết được vấn đề không?

**Gợi ý lời giải:** Truy vấn thiếu `status`, một thành phần composite partition key. Đổi cách viết placeholder không sửa mô hình truy cập. Cần xem lại bảng phục vụ use case hoặc phương án phù hợp với đặc tính Cassandra.

## 16. Những điều cần ghi nhớ

- Import đầy đủ quyết định `@Query` thuộc store nào; Commons không cung cấp một ngôn ngữ `@Query` chung.
- JPQL dùng entity và thuộc tính; SQL dùng bảng và cột; các store khác có ngôn ngữ riêng.
- Placeholder không portable: phân biệt `?1`, `?0`, `:name`, `$name` và bind marker của driver.
- Bind giá trị không thay tên bảng, tên cột, label hoặc cấu trúc truy vấn theo một quy tắc chung.
- Pagination, count query, projection, modifying query và biểu thức đều phải xét theo module và loại query.
- Khi chuyển store, hãy thiết kế lại truy vấn theo mô hình dữ liệu và khả năng store, rồi kiểm chứng thực thi và ánh xạ kết quả.
