# Đánh giá tác động của phép chiếu đến SQL và chi phí ánh xạ

## 1. Phép chiếu là gì trong truy vấn dữ liệu?

Trong truy vấn quan hệ, **projection (phép chiếu)** là việc chọn một tập thuộc tính hoặc cột cần trả về, thay vì lấy toàn bộ dữ liệu của hàng. Trong SQL, danh sách cột sau SELECT thể hiện phép chiếu.

Ví dụ, một màn hình danh sách khách hàng chỉ hiển thị ID, tên và trạng thái. Ứng dụng không cần tải email, địa chỉ, ghi chú nội bộ hoặc những trường khác:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status;
~~~

Nếu dùng SELECT * thì database trả về mọi cột trong hàng, dù màn hình chỉ sử dụng ba trường. Khi số cột, độ dài dữ liệu hoặc số hàng tăng lên, phần dữ liệu dư thừa có thể làm tăng lượng dữ liệu truyền qua mạng, công việc giải mã của driver, chi phí chuyển đổi và bộ nhớ cần để tạo object.

Trong Spring Data R2DBC, phép chiếu có thể được biểu diễn qua interface projection, DTO/class projection hoặc SQL tường minh với DatabaseClient. Lựa chọn đúng giúp truy vấn chỉ lấy dữ liệu cần thiết và tạo ra kiểu kết quả phù hợp với mục đích sử dụng.

Tuy nhiên, phép chiếu không tự động làm mọi truy vấn nhanh hơn. Hiệu quả phụ thuộc vào câu SQL thực tế, query plan, index, số hàng, kích thước cột, driver và cách ứng dụng ánh xạ kết quả. Cần đánh giá cả phần database và phần mapping ở ứng dụng.

## 2. So sánh truy vấn lấy toàn bộ entity và truy vấn chiếu cột

Giả sử bảng customers có các cột:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL,
    address TEXT,
    internal_note TEXT,
    created_at TIMESTAMP NOT NULL
);
~~~

Màn hình danh sách chỉ cần ID, tên và trạng thái.

Truy vấn lấy toàn bộ cột:

~~~sql
SELECT *
FROM customers
WHERE status = :status
ORDER BY id;
~~~

Truy vấn có phép chiếu:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
ORDER BY id;
~~~

Hai câu lệnh có thể trả cùng số hàng, nhưng khối lượng dữ liệu mỗi hàng khác nhau. Nếu address và internal_note chứa nhiều văn bản, SELECT * có thể truyền thêm một lượng dữ liệu đáng kể mà caller không sử dụng.

| Khía cạnh | SELECT * | SELECT các cột cần thiết |
|---|---|---|
| Số cột trả về | Tất cả cột | Chỉ các cột được chọn |
| Dữ liệu truyền qua mạng | Có thể lớn hơn | Thường nhỏ hơn |
| Driver decode | Phải xử lý các cột được trả về | Ít cột hơn |
| Mapping | Có thể khởi tạo entity đầy đủ | Có thể tạo DTO nhỏ hơn |
| Bộ nhớ ứng dụng | Có thể giữ nhiều dữ liệu không cần thiết | Thường giảm nếu kết quả cũng nhỏ |
| Khả năng dùng covering index | Phụ thuộc index chứa đủ cột | Có thể thuận lợi hơn nếu index phù hợp |
| Rủi ro khi schema thêm cột | Kết quả SELECT * thay đổi theo schema | Danh sách cột ổn định và rõ ý định |

Phép chiếu rõ ràng cũng làm hợp đồng dữ liệu của truy vấn dễ hiểu hơn. Khi schema thêm một cột mới, truy vấn chỉ định cột sẽ không tự nhiên bắt đầu truyền thêm cột đó.

## 3. Phép chiếu ảnh hưởng đến hiệu năng ở những tầng nào?

Tác động của phép chiếu cần được nhìn từ database đến object Java.

~~~text
SQL SELECT list
      |
      v
Database execution plan
      |
      v
Các cột được trả về
      |
      v
Network / protocol
      |
      v
R2DBC Driver decode rows
      |
      v
Spring Data mapping / projection
      |
      v
DTO hoặc interface projection
      |
      v
Service / API response
~~~

### 3.1. Ở database

Database vẫn phải tìm những hàng thỏa điều kiện WHERE. Việc chọn ít cột không làm biến mất chi phí tìm hàng, lọc, join hoặc sắp xếp.

Tuy vậy, phép chiếu có thể giúp database:

- Không phải tạo và gửi những giá trị cột không cần thiết trong result set.
- Giảm kích thước kết quả cần truyền ra khỏi database.
- Có cơ hội dùng covering index nếu index chứa đủ cột cần cho điều kiện, thứ tự và danh sách SELECT.
- Giảm một số thao tác đọc heap/table trong những trường hợp query plan và database hỗ trợ index-only access.

Không nên kết luận rằng chọn ba cột luôn đọc ít page hơn chọn bảy cột. Với nhiều database, việc tìm hàng vẫn cần truy cập trang dữ liệu chứa hàng; lợi ích I/O phụ thuộc cấu trúc bảng, index, query plan, visibility hoặc storage engine.

### 3.2. Trên đường truyền dữ liệu

Mỗi hàng trả về càng rộng thì lượng byte database gửi đến ứng dụng càng lớn. Chênh lệch đặc biệt rõ khi có cột TEXT, JSON, BLOB hoặc những trường có nội dung dài.

Nếu truy vấn trả hàng trăm nghìn bản ghi, giảm kích thước mỗi hàng có thể làm giảm đáng kể network traffic và thời gian truyền kết quả. Ngược lại, với truy vấn chỉ trả một hàng nhỏ, khác biệt có thể không đáng kể.

### 3.3. Ở R2DBC driver

Driver cần đọc và giải mã những cột xuất hiện trong result set. Ít cột hơn có thể giảm số lần truy cập metadata/value, chuyển kiểu và tạo đối tượng giá trị trung gian.

Chi phí thực tế phụ thuộc driver, kiểu dữ liệu và cách ứng dụng đọc row. Một cột JSON lớn hoặc binary có thể tốn nhiều chi phí hơn một cột số nguyên, nên chỉ đếm số cột là chưa đủ để đánh giá.

### 3.4. Ở Spring Data mapping

Khi ánh xạ entity đầy đủ, Spring Data phải gán các thuộc tính tương ứng và có thể xử lý thêm các thành phần thuộc aggregate. Một projection nhỏ có thể giúp:

- Chỉ tạo những giá trị mà caller cần.
- Giảm số property phải chuyển đổi.
- Giảm số object hoặc cấu trúc kết quả phải giữ trong bộ nhớ.
- Tránh đưa các trường nhạy cảm hoặc không liên quan vào tầng service/API.

Với interface projection, Spring Data có thể dùng proxy để cung cấp getter cho các thuộc tính được chiếu. Với DTO projection, ứng dụng nhận một object có constructor và chỉ những trường được định nghĩa trong DTO.

### 3.5. Ở tầng service và API

Một DTO nhỏ thường làm rõ dữ liệu mà một use case cần. Service không phải tải entity đầy đủ rồi chuyển thành response object chỉ để bỏ đi phần lớn thuộc tính.

Điều này cũng giảm nguy cơ vô tình serialize các trường nội bộ khi trả response. Tuy nhiên, projection chỉ là một phần của kiểm soát dữ liệu; API vẫn cần DTO response phù hợp và authorization đúng.

## 4. Interface projection trong Spring Data R2DBC

Interface projection mô tả những thuộc tính mà caller cần đọc. Spring Data tạo projection phù hợp từ kết quả truy vấn.

Ví dụ:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getStatus();
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerSummary> findByStatus(String status);
}
~~~

Caller chỉ làm việc với những getter được khai báo:

~~~java
return customerRepository.findByStatus("ACTIVE")
        .map(summary -> new CustomerListItem(
                summary.getId(),
                summary.getName(),
                summary.getStatus()
        ));
~~~

Đây là **closed projection** vì các getter tương ứng với những property đã biết của entity. Spring Data có thể xác định những property cần thiết từ projection metadata và tối ưu phần dữ liệu được chọn trong những query method và phiên bản hỗ trợ cơ chế đó.

Dù vậy, hãy kiểm tra SQL thực tế. Không nên suy luận chỉ từ interface rằng database chắc chắn chỉ trả đúng ba cột, nhất là khi dùng câu SQL khai báo tường minh, projection lồng nhau hoặc tính năng mapping riêng.

### 4.1. Closed projection

Closed projection chỉ khai báo getter cho các property của target type:

~~~java
public interface CustomerNameAndStatus {
    String getName();
    String getStatus();
}
~~~

Vì tập property cần thiết được xác định trước, Spring Data có thông tin để tối ưu projection trong các query method được hỗ trợ. Đây là lựa chọn phù hợp khi cần một tập field nhỏ và cố định.

Tên getter phải tương ứng với property Java của entity. Nếu entity có property `email` nhưng cột database tên `email_address`, projection thường dùng getter `getEmail()`, còn mapping metadata chịu trách nhiệm ánh xạ property sang cột.

### 4.2. Open projection và biểu thức tính toán

Open projection có thể dùng biểu thức SpEL để tính giá trị từ target object:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {

    @Value("#{target.name + ' (' + target.status + ')'}")
    String getLabel();
}
~~~

Getter `getLabel()` không ánh xạ trực tiếp đến một property duy nhất; nó tính giá trị từ target. Vì dependency của expression có thể khó suy ra đầy đủ, cơ hội tối ưu cột có thể bị hạn chế và framework có thể cần target object với nhiều thuộc tính hơn.

Nếu phép tính chỉ kết hợp một vài trường đơn giản, hãy cân nhắc DTO projection hoặc tính toán trong query/service. Không nên dùng open projection chỉ để đổi tên một property nếu closed projection đã đáp ứng được.

### 4.3. Projection lồng nhau

Spring Data Commons hỗ trợ projection lồng nhau trong nhiều ngữ cảnh, nhưng với mô hình relational cần hiểu rõ aggregate boundary và cách dữ liệu được mapping. Không nên giả định getter lồng nhau sẽ kích hoạt lazy loading như JPA.

R2DBC không cung cấp lazy-loading proxy kiểu JPA. Nếu cần dữ liệu từ bảng khác, hãy xác định query JOIN/projection phù hợp hoặc truy vấn riêng và kết hợp publisher. Với Spring Data Relational, collection thuộc aggregate có thể cần thao tác đọc riêng theo mapping; projection của root không tự bảo đảm loại bỏ mọi chi phí đọc thành phần.

## 5. DTO hoặc class-based projection

DTO projection dùng một class hoặc record để mô tả hình dạng dữ liệu trả về. Đây là lựa chọn phù hợp khi cần kiểu kết quả rõ ràng, bất biến và có thể dùng trực tiếp trong API hoặc service.

Ví dụ:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String status
) {}
~~~

Một repository method có thể trả về projection:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

Với class-based projection, constructor parameter cần tương ứng với các property được chọn và mapping metadata. Record có constructor canonical với tên component rõ ràng, nên thường thuận tiện cho DTO projection.

Nếu class có nhiều constructor, Spring Data cần biết constructor nào được dùng làm persistence/projection constructor, ví dụ qua annotation phù hợp như `@PersistenceCreator` trong những trường hợp được hỗ trợ. Giữ DTO projection đơn giản sẽ làm mapping dễ đoán hơn.

### 5.1. DTO projection với SQL tường minh

Khi cần kiểm soát chính xác danh sách cột, có thể viết query tường minh:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    """)
Flux<CustomerSummary> findSummaryByStatus(
        @Param("status") String status
);
~~~

Danh sách SELECT chỉ gồm ba cột cần cho CustomerSummary. Tên cột phải khớp với schema và tên property/constructor parameter theo mapping; nếu khác nhau, dùng alias phù hợp.

Ví dụ cột `email_address` có thể được alias thành `email` nếu DTO dùng property `email` và mapping cần tên đó:

~~~sql
SELECT id, email_address AS email
FROM customers
WHERE id = :id;
~~~

Cú pháp alias này là SQL thông thường; cần xác nhận tên cột trả về mà driver cung cấp và cách mapping của phiên bản đang sử dụng.

### 5.2. DTO projection so với interface projection

| Tiêu chí | Interface projection | DTO/class projection |
|---|---|---|
| Mô tả kết quả | Interface với getter | Class hoặc record |
| Cách truy cập | Proxy thực hiện getter | Đọc field/accessor của object |
| Phép tính | Có thể dùng open projection/SpEL | Có thể tính trong constructor hoặc service |
| Tính bất biến | Phụ thuộc implementation/proxy | Record hoặc immutable class dễ biểu đạt |
| Mapping | Dựa trên property projection metadata | Dựa trên constructor/property mapping |
| Phù hợp | View nhỏ, đơn giản, getter-only | API result, read model, kết quả có cấu trúc rõ |

Không có lựa chọn nào luôn nhanh hơn trong mọi trường hợp. Chi phí proxy của interface thường nhỏ so với database/network trong nhiều ứng dụng, nhưng DTO constructor có thể dễ dự đoán và kiểm soát hơn. Hãy chọn theo hình dạng dữ liệu và đo khi hiệu năng là yêu cầu quan trọng.

## 6. Projection với DatabaseClient

DatabaseClient cho phép kiểm soát SQL và ánh xạ từng row thủ công. Đây là lựa chọn rõ ràng khi cần chắc chắn chỉ lấy những cột nào hoặc kết quả không tương ứng với một entity đầy đủ.

DTO:

~~~java
public record CustomerCard(
        Long id,
        String name,
        String status
) {}
~~~

Truy vấn:

~~~java
Flux<CustomerCard> cards =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerCard(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

Ở đây, SQL quyết định chính xác danh sách cột. Callback đọc từng giá trị và tạo CustomerCard. Không cần khôi phục một Customer đầy đủ nếu use case chỉ cần ba trường.

Ưu điểm:

- SQL SELECT list hiển thị rõ ngay trong code.
- Có thể dùng JOIN, aggregate function, alias hoặc database-specific expression.
- Có thể map kết quả sang DTO không phải entity.
- Không phụ thuộc việc query derivation có tối ưu projection hay không.

Đổi lại, lập trình viên phải tự chịu trách nhiệm mapping từng cột, nullability, kiểu dữ liệu và alias. Khi schema thay đổi, raw SQL và callback mapping cần được cập nhật đồng bộ.

## 7. Projection có thực sự làm SQL chỉ lấy các cột cần thiết?

Đây là điểm quan trọng khi đánh giá hiệu quả. Kiểu trả về DTO hoặc interface không phải bằng chứng duy nhất cho thấy câu SQL đã được thu hẹp.

### 7.1. Query method được suy ra từ tên

Với derived query và projection metadata, Spring Data có thể suy ra property cần thiết và giới hạn phần select trong những trường hợp được hỗ trợ.

Ví dụ:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

Nếu projection chỉ cần id, name và status, framework có thể tạo truy vấn chỉ chọn các cột tương ứng. Cần kiểm tra SQL thực tế theo phiên bản Spring Data và kiểu projection đang dùng.

### 7.2. Query viết bằng @Query

Với SQL tường minh, danh sách cột là trách nhiệm của người viết query. Ví dụ:

~~~java
@Query("""
    SELECT *
    FROM customers
    WHERE status = :status
    """)
Flux<CustomerSummary> findSummaryByStatus(String status);
~~~

Dù kiểu kết quả là CustomerSummary, câu SQL vẫn yêu cầu database trả tất cả cột vì SELECT * đã được khai báo. Projection có thể chỉ dùng một phần dữ liệu khi mapping, nhưng không nên giả định nó tự viết lại mọi raw SQL để bỏ cột.

Nếu muốn giảm dữ liệu trả về, hãy viết rõ:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
~~~

### 7.3. DatabaseClient

Với DatabaseClient, SQL và row mapping đều do ứng dụng kiểm soát. Callback chỉ đọc ba cột không có nghĩa database chỉ gửi ba cột nếu SQL vẫn là SELECT *.

Quy tắc thực hành: **kiểm tra SELECT list của SQL thực thi**, không chỉ nhìn kiểu trả về của method.

## 8. Projection ảnh hưởng thế nào đến chi phí ánh xạ?

Giả sử entity Customer có 20 property nhưng màn hình chỉ cần 3 property. Có hai cách:

1. Đọc đầy đủ Customer rồi chuyển thành DTO.
2. Truy vấn và ánh xạ trực tiếp thành CustomerSummary chỉ chứa 3 property.

Cách thứ hai có thể giảm công việc ở nhiều bước.

| Chi phí | Đọc entity đầy đủ rồi chuyển DTO | Projection trực tiếp |
|---|---|---|
| Giá trị được driver giải mã | Có thể gồm mọi cột đã SELECT | Chỉ các cột trong projection SQL |
| Property conversion | Nhiều property hơn | Ít property hơn |
| Object allocation | Entity và DTO trung gian | Thường chỉ DTO/projection cần thiết |
| Dữ liệu giữ trong heap | Có thể giữ entity rồi DTO trong pipeline | Thường giữ kết quả nhỏ hơn |
| Logic chuyển đổi | Mapping entity rồi mapping response | Mapping trực tiếp vào read model |
| Tính nhất quán mô hình | Dựa trên entity domain | Dựa trên read model cụ thể |

Chi phí object allocation có thể đáng kể khi số hàng lớn. Nhưng nếu query chỉ trả vài hàng, chênh lệch này có thể nhỏ hơn chi phí kết nối, round-trip và execution plan.

Interface projection có thể dùng proxy; DTO projection thường tạo instance qua constructor. Không nên kết luận proxy luôn chậm hoặc DTO luôn nhanh. Cần xem tổng chi phí và số lượng kết quả.

## 9. Projection và aggregate trong Spring Data Relational

Spring Data Relational tổ chức dữ liệu theo aggregate root và các thành phần thuộc aggregate. Projection cần được thiết kế theo use case, đồng thời tôn trọng ranh giới aggregate.

Ví dụ Order aggregate có:

- Order root: id, customerId, status, createdAt.
- OrderLine: sku, quantity, unitPrice.
- ShippingAddress: street, city, postalCode.

Một trang danh sách đơn hàng có thể chỉ cần:

~~~java
public record OrderListItem(
        Long id,
        String status,
        Instant createdAt
) {}
~~~

Không cần tải toàn bộ OrderLine và ShippingAddress nếu màn hình không sử dụng chúng.

Một trang chi tiết đơn hàng có thể cần thêm dòng hàng. Khi đó, có thể dùng query phù hợp để lấy root và dữ liệu dòng hàng, hoặc thực hiện các truy vấn riêng rồi kết hợp bằng Reactor.

Không nên giả định projection của Order root tự động tải hoặc bỏ tải mọi collection thuộc aggregate theo cách giống ORM lazy loading. R2DBC không cung cấp lazy-loading proxy kiểu JPA. Cần quan sát SQL và cách mapping aggregate của phiên bản đang sử dụng.

Nếu collection rất lớn, hãy cân nhắc một truy vấn phân trang riêng cho các dòng hàng thay vì tải toàn bộ aggregate chỉ để hiển thị một trang.

## 10. Projection không thay thế pagination và giới hạn số hàng

Projection giảm số cột mỗi hàng, nhưng không tự giảm số hàng được trả về.

Ví dụ:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

Nếu có một triệu khách hàng ACTIVE, Flux vẫn có thể phát ra một triệu projection. Mỗi projection nhỏ hơn entity đầy đủ, nhưng tổng lượng công việc vẫn có thể lớn.

Cần kết hợp projection với:

- **Limit:** giới hạn số hàng cho use case cần tập kết quả nhỏ.
- **Pagination:** chia kết quả thành từng trang.
- **Keyset pagination:** dùng khóa hoặc cặp khóa sắp thứ tự để lấy trang kế tiếp ổn định trên tập lớn.
- **Filtering:** đưa điều kiện lọc phù hợp xuống database.
- **Backpressure:** để downstream điều tiết tốc độ tiêu thụ trong reactive pipeline, trong phạm vi driver hỗ trợ.

Ví dụ SQL có giới hạn:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

OFFSET pagination dễ hiểu nhưng offset lớn có thể tốn chi phí vì database phải bỏ qua nhiều hàng. Với dữ liệu lớn và thứ tự ổn định, có thể dùng keyset:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
  AND id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
~~~

Câu SQL thứ hai lấy các hàng sau ID cuối của trang trước. Cần có thứ tự duy nhất và ổn định; nếu sort theo nhiều cột, cursor phải chứa đủ các giá trị để phân trang chính xác.

## 11. Projection và index: khi nào database có thể đọc ít dữ liệu hơn?

Phép chiếu có thể tạo điều kiện cho **covering index** hoặc index-only scan khi index chứa tất cả cột cần thiết cho query. Khi đó, database có thể lấy dữ liệu từ index mà không cần truy cập đầy đủ hàng trong bảng ở một số trường hợp.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_customers_status_cover
ON customers (status)
INCLUDE (id, name);
~~~

Truy vấn:

~~~sql
SELECT id, name
FROM customers
WHERE status = :status;
~~~

Index trên có cột status để lọc và lưu thêm id, name để trả kết quả. PostgreSQL có thể cân nhắc index-only scan tùy statistics, visibility map, cardinality và query plan.

Đây không phải cam kết rằng index sẽ luôn được dùng. Index có thể làm tăng dung lượng, chi phí INSERT/UPDATE/DELETE và công việc bảo trì. Không nên tạo covering index cho mọi projection; hãy dựa trên truy vấn quan trọng, tần suất chạy, selectivity và EXPLAIN.

Nếu truy vấn SELECT * cần nhiều cột không có trong index, database có thể phải truy cập heap/table để lấy các giá trị còn thiếu. Nhưng projection chỉ giúp khi query planner chọn được đường truy cập phù hợp.

## 12. Phép chiếu và join nhiều bảng

Một truy vấn hiển thị đơn hàng kèm tên khách hàng có thể dùng JOIN và projection:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    o.created_at,
    c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC;
~~~

DTO kết quả:

~~~java
public record OrderSummary(
        Long orderId,
        String status,
        Instant createdAt,
        String customerName
) {}
~~~

DatabaseClient mapping:

~~~java
Flux<OrderSummary> summaries =
        databaseClient.sql("""
                SELECT
                    o.id AS order_id,
                    o.status,
                    o.created_at,
                    c.name AS customer_name
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status = :status
                ORDER BY o.created_at DESC
                """)
            .bind("status", status)
            .map((row, metadata) -> new OrderSummary(
                    row.get("order_id", Long.class),
                    row.get("status", String.class),
                    row.get("created_at", Instant.class),
                    row.get("customer_name", String.class)
            ))
            .all();
~~~

Projection giúp trả đúng các trường mà màn hình cần, thay vì tải toàn bộ Order và Customer. Tuy nhiên, JOIN vẫn có chi phí riêng: database phải tìm và kết hợp hàng theo điều kiện join. Cần index phù hợp ở khóa join và kiểm tra query plan.

Với truy vấn báo cáo hoặc read model, DTO có thể không tương ứng với aggregate root nào. Đây là trường hợp phù hợp để dùng SQL tường minh và mapping kết quả riêng.

## 13. Nullability, alias và kiểu dữ liệu trong projection

Projection chỉ hoạt động đúng khi các cột trả về phù hợp với property hoặc constructor mà nó cần.

Cần kiểm tra:

- Tên cột hoặc alias có khớp với tên property/constructor parameter không?
- Kiểu Java có tương thích với kiểu do driver trả về không?
- Cột có thể NULL trong khi DTO dùng kiểu primitive không?
- JOIN có thể tạo cột null ở phía bảng được LEFT JOIN không?
- Alias có trùng nhau khi hai bảng cùng có cột id hoặc name không?

Ví dụ với LEFT JOIN:

~~~sql
SELECT
    o.id AS order_id,
    c.name AS customer_name
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id;
~~~

Nếu không có customer tương ứng, customer_name có thể là NULL. DTO nên dùng kiểu tham chiếu có thể null thay vì kiểu primitive.

Với DatabaseClient, callback cần đọc đúng kiểu driver hỗ trợ. Với repository projection, hãy đảm bảo alias phù hợp và kiểm thử mapping với dữ liệu có NULL.

## 14. Đo lường tác động của projection

Không nên đánh giá hiệu năng chỉ bằng việc câu SQL ngắn hơn hoặc DTO có ít field hơn. Cần quan sát ít nhất bốn khía cạnh:

### 14.1. SQL thực tế

Bật logging SQL có kiểm soát ở môi trường phát triển hoặc dùng công cụ quan sát truy vấn. Xác nhận:

- SELECT list có đúng các cột cần thiết không?
- Có query phụ nào được thực thi để tải collection hoặc dữ liệu liên quan không?
- Có JOIN không cần thiết không?
- Điều kiện WHERE và ORDER BY có đúng không?
- Query có bị gọi lặp lại theo từng hàng (N+1 pattern) không?

Không bật log bind values nhạy cảm trong production nếu không có cơ chế bảo vệ.

### 14.2. Query plan và thời gian database

Dùng EXPLAIN hoặc EXPLAIN ANALYZE theo database để xem:

- Sequential scan hay index scan được chọn.
- Có index-only scan hay không.
- Số hàng ước lượng so với thực tế.
- Chi phí join, sort và filter.
- Buffer/page được đọc và thời gian thực thi.

EXPLAIN ANALYZE thực thi câu query trên database; hãy dùng môi trường và dữ liệu phù hợp, đặc biệt khi query có tác động ghi.

### 14.3. Kích thước dữ liệu và thời gian truyền

So sánh số hàng, số cột, độ rộng dữ liệu và thời gian từ database đến ứng dụng. Những cột lớn như TEXT, JSON hoặc binary có thể tạo khác biệt lớn hơn nhiều cột số nhỏ.

### 14.4. Chi phí ứng dụng

Quan sát CPU, allocation, heap usage và thời gian mapping. Với tải cao, có thể dùng profiler hoặc benchmark trên cùng dữ liệu, cùng database, cùng pool và cùng concurrency để so sánh entity đầy đủ với projection.

Khi benchmark, giữ điều kiện tương đương: cùng bộ lọc, cùng số hàng, cùng index và cùng cách tiêu thụ Flux. Nếu một test chỉ tiêu thụ ba phần tử còn test kia tiêu thụ toàn bộ kết quả, số liệu không thể so sánh trực tiếp.

## 15. Những trường hợp projection không mang lại lợi ích như mong đợi

| Tình huống | Vì sao lợi ích hạn chế | Hướng xử lý |
|---|---|---|
| Query vẫn dùng SELECT * | Database vẫn trả mọi cột dù DTO chỉ dùng vài field | Viết SELECT list tường minh |
| Chỉ trả một vài hàng nhỏ | Chi phí database/network vốn đã thấp | Ưu tiên độ rõ ràng; không tối ưu quá sớm |
| WHERE rất tốn kém | Projection không loại bỏ chi phí lọc hoặc join | Xem query plan, index và điều kiện |
| Số hàng quá lớn | Giảm độ rộng hàng nhưng tổng số hàng vẫn cao | Thêm pagination, limit hoặc keyset |
| Open projection dùng expression phức tạp | Framework có thể không suy ra chính xác tập property cần thiết | Dùng closed projection hoặc DTO |
| JOIN tạo nhiều hàng trùng lặp | Projection không sửa được cardinality của JOIN | Kiểm tra join key, DISTINCT hoặc query aggregate phù hợp |
| Cột cần thiết không có trong index | Database vẫn phải truy cập bảng để lấy dữ liệu | Đánh giá index dựa trên workload |
| Mapping thủ công sai alias/kiểu | Ít cột nhưng kết quả không đúng hoặc phát sinh lỗi | Kiểm thử mapping và nullability |

## 16. Chọn projection theo use case

| Use case | Kiểu kết quả nên cân nhắc | Lý do |
|---|---|---|
| CRUD và cập nhật aggregate | Entity đầy đủ | Cần hành vi và trạng thái domain |
| Danh sách đơn giản cho API | Closed interface projection hoặc DTO | Chỉ cần vài property |
| Read model có cấu trúc ổn định | Record/class DTO | Kiểu kết quả rõ ràng, dễ serialize |
| Báo cáo JOIN nhiều bảng | DTO với DatabaseClient hoặc query projection | Kết quả không nhất thiết là entity |
| Chỉ cần đếm | Scalar count | Không cần tạo entity |
| Chỉ cần kiểm tra tồn tại | Boolean | Không cần tải hàng |
| Tải chi tiết aggregate | Entity hoặc DTO chi tiết | Cần dữ liệu theo use case |
| Dữ liệu lớn | Projection kết hợp pagination/keyset | Giảm cả độ rộng và số hàng mỗi lượt |

Một quy tắc thực tế là dùng entity cho thao tác domain cần thay đổi trạng thái hoặc bảo vệ invariant; dùng projection/DTO cho truy vấn đọc có mục đích rõ ràng; dùng scalar khi chỉ cần một giá trị.

## 17. Ví dụ service: tách entity ghi và projection đọc

Một ứng dụng có thể dùng entity cho thao tác tạo/cập nhật, nhưng dùng DTO cho danh sách:

~~~java
public record CustomerListItem(
        Long id,
        String name,
        String status
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, status
        FROM customers
        WHERE status = :status
        ORDER BY id
        """)
    Flux<CustomerListItem> findListItems(
            @Param("status") String status
    );
}
~~~

Service:

~~~java
public Flux<CustomerListItem> listActiveCustomers() {
    return customerRepository.findListItems("ACTIVE");
}
~~~

Với thao tác cập nhật, service vẫn dùng entity hoặc câu lệnh update có điều kiện phù hợp:

~~~java
public Mono<Customer> changeStatus(Long id, String status) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                Customer changed = new Customer(
                        customer.id(),
                        customer.name(),
                        customer.email(),
                        status
                );
                return customerRepository.save(changed);
            });
}
~~~

Ví dụ minh họa hai nhu cầu khác nhau: danh sách chỉ cần một read model nhỏ; cập nhật cần đọc và thay đổi entity theo quy tắc nghiệp vụ. Với thao tác chỉ đổi một cột và không cần kiểm tra domain state, có thể dùng template update hoặc SQL DML có điều kiện để tránh tải entity, nhưng phải giữ đúng invariant và concurrency policy.

## 18. Kiểm thử projection

Kiểm thử projection cần xác nhận cả dữ liệu trả về lẫn SQL thực tế.

Các trường hợp nên có:

- Closed projection trả đúng các property đã khai báo.
- DTO constructor nhận đúng cột và alias.
- Giá trị NULL được ánh xạ đúng.
- Cột có kiểu đặc thù được driver chuyển đúng kiểu Java.
- @Query có SELECT list chỉ gồm các cột cần thiết.
- JOIN không tạo duplicate hoặc sai cardinality ngoài dự kiến.
- Pagination trả trang ổn định và đúng thứ tự.
- Projection không vô tình đưa trường nội bộ vào response.
- Query plan và số liệu hiệu năng được đo trên dữ liệu có kích thước gần với workload thực tế.

Mock repository có thể kiểm tra service mapping nhưng không chứng minh database chỉ trả các cột đã chọn. Để xác nhận tác động đến SQL và driver, hãy dùng integration test với database tương thích hoặc Testcontainers và quan sát câu SQL được thực thi.

## 19. Quy trình đánh giá một phép chiếu

Khi muốn tối ưu một truy vấn hiện có, có thể đi theo trình tự:

1. Xác định caller thực sự sử dụng những field nào.
2. Xác định kết quả có cần là aggregate/entity hay chỉ là read model.
3. Tạo closed interface projection hoặc DTO với đúng các field cần thiết.
4. Với @Query hoặc DatabaseClient, viết SELECT list tường minh.
5. Xác nhận alias, kiểu dữ liệu và nullability.
6. Quan sát SQL thực thi để kiểm tra projection có thực sự giảm cột.
7. Đo số byte, thời gian database, thời gian mapping và bộ nhớ ứng dụng.
8. Kiểm tra query plan và index nếu database vẫn là nút thắt.
9. Kết hợp pagination khi số hàng lớn.
10. Giữ entity đầy đủ cho những thao tác cần domain behavior và invariant.

Không nên thay toàn bộ entity bằng projection chỉ vì projection có ít field hơn. Chọn kiểu kết quả dựa trên trách nhiệm của use case và dữ liệu thực sự cần thiết.

## 20. Kết luận

Projection giúp truy vấn chỉ trả về những cột mà một use case cần. Trong Spring Data R2DBC, có thể dùng closed interface projection, DTO/class projection hoặc DatabaseClient với SQL và row mapping tường minh. Nếu câu SQL chỉ chọn một số cột, ứng dụng có cơ hội giảm dữ liệu truyền qua mạng, công việc decode, conversion, object allocation và bộ nhớ.

Lợi ích không chỉ phụ thuộc kiểu trả về. Với query tường minh, SELECT list quyết định dữ liệu database trả về; DTO nhỏ không tự biến SELECT * thành truy vấn hẹp. Projection cũng không thay thế pagination, index, query plan hoặc thiết kế aggregate. Nó không nhất thiết làm giảm chi phí tìm hàng, join hay sort.

Đánh giá hiệu quả bằng SQL thực tế, query plan, kích thước kết quả và chi phí mapping trên workload tương đương. Dùng entity khi cần thao tác domain; dùng projection hoặc DTO cho read model; dùng scalar khi chỉ cần count hoặc exists. Cách chọn này giúp tầng dữ liệu lấy vừa đủ thông tin và làm rõ hợp đồng kết quả của từng truy vấn.

