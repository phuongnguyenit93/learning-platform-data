# Khóa ghép: kiểm tra hỗ trợ theo phiên bản và lựa chọn mô hình thay thế

Khóa chính ghép (composite primary key) là khóa gồm từ hai cột trở lên. Ví dụ, một dòng hàng trong đơn mua có thể được định danh bằng cặp `(order_id, line_no)`: số thứ tự dòng chỉ có ý nghĩa bên trong một đơn hàng, vì vậy `line_no` không duy nhất trên toàn bảng.

Các hệ quản trị cơ sở dữ liệu quan hệ hỗ trợ khóa chính ghép ở cấp SQL. Tuy nhiên, khả năng tạo bảng với khóa ghép không đồng nghĩa mọi framework mapping đều có thể ánh xạ khóa đó trực tiếp thành ID của entity. Với Spring Data Relational và Spring Data R2DBC, cần kiểm tra đúng phiên bản đang dùng, cách phiên bản đó biểu diễn ID và các thao tác Repository được hỗ trợ.

Khi khả năng mapping trực tiếp không đáp ứng nhu cầu, có thể giữ khóa ghép ở database nhưng dùng một khóa thay thế (surrogate key) làm ID entity, kết hợp `UNIQUE` để bảo vệ tính duy nhất nghiệp vụ. Một lựa chọn khác là giữ schema có khóa ghép và thao tác bằng SQL qua `DatabaseClient`. Mỗi cách phù hợp với một loại yêu cầu khác nhau.

## 1. Khóa ghép là gì?

Khóa chính xác định duy nhất một hàng trong bảng. Với khóa đơn, một cột là đủ để nhận diện hàng. Với khóa ghép, phải kết hợp nhiều cột mới xác định được một hàng.

Ví dụ, bảng `order_line` lưu các dòng của đơn hàng:

```sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_order(id),
    FOREIGN KEY (product_id) REFERENCES product(id)
);
```

Trong bảng này:

- `order_id` cho biết dòng hàng thuộc đơn nào.
- `line_no` là số thứ tự của dòng trong chính đơn đó.
- Một đơn có thể có dòng `1`, `2`, `3` và đơn khác cũng có các số dòng tương tự.
- Cặp `(order_id, line_no)` phải duy nhất, trong khi từng cột riêng lẻ không nhất thiết duy nhất.

Ví dụ dữ liệu:

| order_id | line_no | product_id | quantity |
|---:|---:|---:|---:|
| 1001 | 1 | 501 | 2 |
| 1001 | 2 | 502 | 1 |
| 1002 | 1 | 501 | 3 |

Hai hàng có `line_no = 1` vẫn hợp lệ vì `order_id` khác nhau. Nhưng không thể có hai hàng cùng `(order_id = 1001, line_no = 1)`.

Khóa ghép thường xuất hiện trong bảng liên kết many-to-many, bảng chi tiết phụ thuộc vào cha, bảng dữ liệu theo tenant hoặc những miền nghiệp vụ có khóa tự nhiên gồm nhiều thành phần.

## 2. Phân biệt hỗ trợ của database và hỗ trợ của Spring Data

Cần tách hai câu hỏi:

1. **Database có cho phép định nghĩa và thực thi khóa chính ghép không?** Các hệ quản trị quan hệ phổ biến hỗ trợ khai báo nhiều cột trong `PRIMARY KEY`, tạo unique index tương ứng và dùng các cột đó trong foreign key.
2. **Phiên bản Spring Data Relational đang dùng có ánh xạ khóa ghép trực tiếp thành ID entity và hỗ trợ các thao tác cần thiết không?** Câu trả lời phụ thuộc phiên bản framework và cách mapping được triển khai.

Spring Data R2DBC không phải JPA/Hibernate. Không nên suy luận rằng một cách khai báo ID của JPA, chẳng hạn `@EmbeddedId` hoặc `@IdClass`, sẽ tự động hoạt động trong Spring Data R2DBC. Các annotation và quy tắc mapping của mỗi framework có thể khác nhau.

Vì Spring Data Relational được phát triển qua nhiều release train, cần đọc tài liệu và ghi chú phát hành của đúng phiên bản được resolve trong ứng dụng. Không nên chỉ xem phiên bản Spring Boot trong `build.gradle` hoặc `pom.xml`: Boot quản lý nhiều module Spring Data và dependency bắc cầu, do đó phiên bản thực tế có thể khác với suy đoán từ một khai báo riêng lẻ.

## 3. Kiểm tra khả năng hỗ trợ theo phiên bản

Trước khi thiết kế entity dùng khóa ghép trực tiếp, hãy xác định phiên bản thực tế và xác minh đầy đủ hành vi cần dùng.

### Bước 1 — Xác định phiên bản Spring Data được resolve

Nếu dự án dùng Gradle, có thể xem dependency tree của runtime:

```bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-data-r2dbc \
  --configuration runtimeClasspath
```

Nếu dự án dùng Maven:

```bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.data:spring-data-relational,org.springframework.data:spring-data-r2dbc
```

Ghi nhận cả phiên bản `spring-data-relational`, `spring-data-r2dbc` và Spring Boot BOM đang quản lý chúng. Nếu có nhiều phiên bản được kéo vào, cần xác định phiên bản cuối cùng trên runtime classpath và lý do chọn phiên bản đó.

### Bước 2 — Đọc tài liệu đúng release train

Tra tài liệu tham chiếu Spring Data Relational của đúng phiên bản đã resolve, đặc biệt phần mô tả định danh entity, mapping metadata, persistence và Repository. Đọc release notes hoặc migration guide khi tính năng được bổ sung hay thay đổi giữa các phiên bản.

Không dùng tài liệu của nhánh `current` để kết luận cho một dự án đang dùng phiên bản cũ. Một ví dụ trong tài liệu mới nhất có thể dựa trên API chưa tồn tại trong release train của dự án.

### Bước 3 — Xác minh toàn bộ vòng đời entity

Ngay cả khi tài liệu nói có hỗ trợ composite ID, vẫn cần kiểm tra những thao tác mà ứng dụng thực sự dùng:

- Mapping các thành phần của ID thành đúng các cột trong bảng.
- Đọc entity bằng ID ghép và truyền đúng kiểu ID cho `findById`.
- Insert entity mới có ID được gán từ trước.
- Phân biệt entity mới với entity đã tồn tại khi gọi `save`.
- Update và delete theo toàn bộ các thành phần của khóa.
- Mapping foreign key tham chiếu tới khóa ghép, nếu schema có trường hợp đó.
- Hành vi optimistic locking, auditing và custom conversion nếu ứng dụng sử dụng.
- Cách xử lý giá trị null, kiểu dữ liệu khác nhau và quy tắc đặt tên cột.

Một tính năng có thể hỗ trợ đọc theo khóa ghép nhưng vẫn có giới hạn ở generated ID, entity state detection hoặc một thao tác Repository cụ thể. Vì vậy, chỉ xác nhận rằng code biên dịch là chưa đủ.

### Bước 4 — Viết integration test trên driver thật

Tạo một bảng thử nghiệm có khóa ghép trong đúng hệ quản trị và driver của dự án. Kiểm tra insert, read, update, delete, duplicate key và transaction. Nếu chỉ dùng H2 để kiểm tra trong khi production chạy PostgreSQL hoặc SQL Server, cần thêm kiểm thử trên database production tương ứng vì kiểu dữ liệu, SQL và driver có thể khác nhau.

## 4. Những điều cần cân nhắc khi chọn khóa ghép

Khóa ghép phù hợp khi toàn bộ thành phần của khóa là một định danh tự nhiên, ổn định và có ý nghĩa trong miền dữ liệu.

Ví dụ phù hợp:

- `order_id + line_no`: số dòng chỉ duy nhất trong một đơn hàng.
- `tenant_id + external_code`: mã do hệ thống bên ngoài cung cấp và chỉ duy nhất trong từng tenant.
- `student_id + course_id`: một sinh viên chỉ có một bản ghi đăng ký cho một môn học trong một kỳ, nếu nghiệp vụ định nghĩa như vậy.
- `country_code + local_number`: số điện thoại được định danh theo mã quốc gia và số nội địa, nếu đây là quy tắc định danh được chọn.

Khóa ghép có một số lợi ích:

- Thể hiện trực tiếp quy tắc duy nhất trong database.
- Không cần thêm một cột ID nhân tạo nếu các thành phần tự nhiên đã đủ ổn định.
- Có thể làm rõ phạm vi định danh, chẳng hạn một mã chỉ duy nhất trong tenant hoặc trong aggregate cha.
- Thuận tiện cho một số bảng liên kết, nơi chính cặp khóa ngoại là định danh của hàng.

Nhưng cũng có các chi phí:

- Mọi truy vấn định danh phải mang đủ các thành phần khóa.
- Foreign key từ bảng khác phải chứa tất cả cột của khóa ghép.
- Index và join có thể lớn hơn khi khóa gồm nhiều cột hoặc cột có kích thước lớn.
- Nếu một thành phần khóa thay đổi, thao tác cập nhật phức tạp và có thể ảnh hưởng tới các bảng tham chiếu.
- Một số framework, thư viện cache, API hoặc công cụ mapping có thể xử lý ID ghép khó hơn ID đơn.

Không nên dùng một trường có thể thay đổi như tên hiển thị, email hoặc trạng thái làm thành phần khóa chính chỉ vì hiện tại nó có vẻ duy nhất. Khóa chính nên ổn định trong suốt vòng đời hàng.

## 5. Mô hình thay thế phổ biến: surrogate key và unique constraint

Khi Spring Data R2DBC hoặc một thư viện tích hợp cần ID đơn giản, mô hình thay thế phổ biến là thêm một khóa thay thế, thường là `BIGINT` identity hoặc UUID. Quy tắc duy nhất nghiệp vụ vẫn được giữ bằng `UNIQUE(order_id, line_no)`.

Schema:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_line_order_line_no UNIQUE (order_id, line_no)
);
```

Ở đây có hai loại định danh với mục đích khác nhau:

- `id` là khóa kỹ thuật đơn, dùng để nhận diện entity trong ứng dụng và làm ID cho Spring Data Repository.
- `(order_id, line_no)` là khóa duy nhất nghiệp vụ, bảo đảm một đơn không có hai dòng cùng số thứ tự.

Unique constraint được database thực thi nên vẫn bảo vệ dữ liệu khi có nhiều request đồng thời. Chỉ kiểm tra trước bằng Java như `existsByOrderIdAndLineNo(...)` không đủ để bảo đảm duy nhất: hai transaction có thể cùng kiểm tra thấy chưa tồn tại rồi cùng insert. Constraint ở database là lớp bảo vệ cuối cùng; ứng dụng cần xử lý lỗi vi phạm unique constraint phù hợp.

### Entity với ID đơn

Ví dụ entity theo mô hình surrogate key:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public record OrderLine(
    @Id Long id,
    Long orderId,
    Integer lineNo,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
```

Repository có thể dùng ID đơn cho các thao tác CRUD và vẫn tìm theo khóa nghiệp vụ:

```java
public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {

    Mono<OrderLine> findByOrderIdAndLineNo(Long orderId, Integer lineNo);

    Flux<OrderLine> findByOrderIdOrderByLineNo(Long orderId);
}
```

Tên method derived query sử dụng thuộc tính entity, không nhất thiết phải trùng tên cột SQL. Mapping context chuyển `orderId` và `lineNo` sang các cột tương ứng theo quy ước hoặc annotation mapping.

Mô hình này thường dễ tích hợp với `ReactiveCrudRepository`, `R2dbcEntityTemplate`, các API nhận một ID và các thư viện khác. Đổi lại, database có thêm một cột khóa và một unique index cho quy tắc nghiệp vụ.

## 6. Dùng khóa ghép trong truy vấn SQL qua DatabaseClient

Nếu schema hiện tại phải giữ composite primary key, ứng dụng vẫn có thể thao tác bằng SQL rõ ràng. `DatabaseClient` hỗ trợ bind từng thành phần của khóa và ánh xạ kết quả thành DTO hoặc domain object.

Ví dụ tìm một dòng hàng:

```java
public Mono<OrderLineView> findLine(Long orderId, Integer lineNo) {
    return databaseClient.sql("""
            SELECT order_id, line_no, product_id, quantity, unit_price
            FROM order_line
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .map((row, metadata) -> new OrderLineView(
            row.get("order_id", Long.class),
            row.get("line_no", Integer.class),
            row.get("product_id", Long.class),
            row.get("quantity", Integer.class),
            row.get("unit_price", BigDecimal.class)
        ))
        .one();
}
```

Update và delete cũng phải dùng đủ các thành phần khóa:

```java
public Mono<Long> updateQuantity(
        Long orderId,
        Integer lineNo,
        Integer quantity) {

    return databaseClient.sql("""
            UPDATE order_line
            SET quantity = :quantity
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("quantity", quantity)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .fetch()
        .rowsUpdated();
}

public Mono<Long> deleteLine(Long orderId, Integer lineNo) {
    return databaseClient.sql("""
            DELETE FROM order_line
            WHERE order_id = :orderId
              AND line_no = :lineNo
            """)
        .bind("orderId", orderId)
        .bind("lineNo", lineNo)
        .fetch()
        .rowsUpdated();
}
```

Với cách này, có thể ánh xạ kết quả vào projection mà không yêu cầu Repository phải biểu diễn composite ID. Tuy nhiên, lớp truy cập dữ liệu phải tự quản lý SQL, bind parameter, mapping và các thao tác cần thiết. Cần dùng bind parameter cho giá trị đầu vào, không ghép chuỗi dữ liệu người dùng vào SQL.

## 7. Giữ khóa ghép ở database nhưng biểu diễn khóa nghiệp vụ thành value object

Ngay cả khi entity dùng surrogate ID, cặp khóa nghiệp vụ vẫn có thể được biểu diễn thành một kiểu Java riêng để tránh truyền nhiều tham số rời rạc và thể hiện ý nghĩa miền dữ liệu.

```java
public record OrderLineKey(Long orderId, Integer lineNo) {}
```

Service có thể nhận một `OrderLineKey`:

```java
public Mono<OrderLine> findLine(OrderLineKey key) {
    return repository.findByOrderIdAndLineNo(key.orderId(), key.lineNo());
}
```

Value object này không nhất thiết phải là primary key được Spring Data ánh xạ. Nó chỉ gom các thành phần của khóa nghiệp vụ trong code. Entity vẫn dùng `id` đơn làm `@Id`, còn database giữ unique constraint cho cặp khóa.

Nếu phiên bản Spring Data Relational hỗ trợ mapping một value object hoặc embedded object thành nhiều cột, có thể cân nhắc dùng tính năng đó cho các trường dữ liệu ghép. Nhưng mapping nhiều cột thành thuộc tính không tự chứng minh rằng thuộc tính đó được hỗ trợ làm primary key. Hai khả năng này phải được xác minh riêng theo tài liệu của phiên bản.

## 8. Khi nào nên chọn từng mô hình?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Phiên bản Spring Data đã xác nhận hỗ trợ composite ID và test đủ vòng đời | Composite ID trực tiếp | Giữ mô hình entity sát với khóa chính database |
| Cần tương thích Repository CRUD đơn giản hoặc nhiều thư viện khác | Surrogate key + unique constraint | ID đơn dễ truyền, lưu cache và tích hợp |
| Schema hiện hữu bắt buộc giữ composite PK, query chuyên biệt | `DatabaseClient` với đầy đủ thành phần khóa | Giữ nguyên schema và kiểm soát SQL trực tiếp |
| Cần gom nhiều thành phần khóa trong API nghiệp vụ | Value object khóa nghiệp vụ | Giảm nhầm thứ tự tham số và thể hiện ngữ nghĩa |
| Bảng liên kết đơn giản, chỉ dùng trong một vài query | Composite PK ở database và query chuyên biệt | Không cần ép mọi bảng thành aggregate Repository |

Không có một lựa chọn tối ưu cho mọi hệ thống. Hãy xét số lượng bảng tham chiếu khóa, khả năng thay đổi thành phần khóa, API cần cung cấp, yêu cầu tương thích và độ phức tạp vận hành.

## 9. Các rủi ro khi dùng khóa ghép

### Thành phần khóa bị thay đổi

Khóa chính nên ổn định. Nếu `line_no` được dùng làm một phần khóa, đổi số thứ tự dòng có thể tương đương xóa một định danh cũ và tạo định danh mới. Nếu các bảng khác tham chiếu `(order_id, line_no)`, thao tác này còn ảnh hưởng tới foreign key. Nếu số thứ tự chỉ phục vụ hiển thị và có thể thay đổi, nên cân nhắc dùng ID đơn làm khóa chính rồi đặt unique constraint theo quy tắc phù hợp.

### Foreign key phải mang đủ thành phần

Nếu một bảng khác tham chiếu tới `order_line`, foreign key phải chứa toàn bộ cột của primary key ghép. Điều này làm schema và join phức tạp hơn khi khóa có nhiều thành phần. Nếu nhiều bảng cần tham chiếu tới cùng một hàng, surrogate key có thể đơn giản hóa quan hệ.

### Thứ tự cột trong index

Index ghép có thứ tự cột. Index trên `(order_id, line_no)` thường phù hợp với điều kiện lọc theo `order_id` hoặc cả hai cột, nhưng không nhất thiết tối ưu cho truy vấn chỉ lọc theo `line_no`. Nếu có access pattern khác, cần index bổ sung theo workload thực tế.

### Phát sinh ID và nhận diện entity mới

Khóa ghép thường được ứng dụng gán từ dữ liệu nghiệp vụ thay vì database tự sinh một giá trị đơn. Vì vậy cần kiểm tra cách Spring Data xác định entity mới hay đã tồn tại khi ID đã có giá trị trước khi gọi `save`. Nếu framework xác định trạng thái entity dựa trên ID hoặc một chiến lược khác, entity mới với ID đã gán có thể cần cơ chế xác định newness phù hợp theo phiên bản. Không nên giả định `save` luôn thực hiện `INSERT` chỉ vì object vừa được tạo trong Java.

Với mô hình surrogate key dùng identity, ID có thể để `null` trước khi insert; đây là luồng phổ biến mà Spring Data hỗ trợ rõ ràng. Quy tắc nghiệp vụ vẫn được bảo vệ bởi unique constraint.

### Lỗi trùng khóa khi có nhiều request

Kiểm tra tồn tại trước khi insert không thay thế được unique constraint. Hai request đồng thời có thể cùng vượt qua bước kiểm tra. Hãy để database bảo vệ tính duy nhất và ánh xạ lỗi vi phạm constraint thành phản hồi nghiệp vụ phù hợp, chẳng hạn báo dòng hàng đã tồn tại.

## 10. Chuyển từ composite primary key sang surrogate key

Với một hệ thống đã chạy, không nên đổi khóa chỉ bằng cách thêm cột ID rồi xóa primary key cũ ngay lập tức. Cần lập kế hoạch migration theo các bảng tham chiếu và luồng triển khai.

Một quy trình tổng quát có thể gồm:

1. Thêm cột surrogate ID với chiến lược sinh giá trị phù hợp.
2. Backfill ID cho toàn bộ hàng hiện có và bảo đảm không có giá trị trùng hoặc null.
3. Tạo unique constraint trên bộ cột khóa nghiệp vụ cũ, ví dụ `(order_id, line_no)`.
4. Tạo index và cột tham chiếu mới cho các bảng con đang tham chiếu composite key.
5. Cập nhật ứng dụng để đọc/ghi bằng ID mới, đồng thời giữ các truy vấn theo khóa nghiệp vụ khi cần.
6. Chuyển dữ liệu tham chiếu và kiểm tra số hàng, orphan, duplicate cùng tính nhất quán.
7. Chuyển foreign key sang ID mới sau khi mọi ứng dụng đã dùng cột mới.
8. Chỉ loại bỏ primary key cũ khi không còn consumer phụ thuộc và đã có kế hoạch rollback.

Trình tự cụ thể phụ thuộc database, kích thước bảng, yêu cầu không downtime và cách phát hành ứng dụng. Với bảng lớn, cần cân nhắc tạo index online/concurrently nếu hệ quản trị hỗ trợ và chia nhỏ quá trình backfill để tránh khóa bảng lâu.

## 11. Kiểm thử khóa ghép và mô hình thay thế

Một bộ integration test nên kiểm tra các trường hợp sau trên database tương ứng:

- Hai hàng có cùng thành phần thứ nhất nhưng khác thành phần thứ hai được phép lưu.
- Hai hàng trùng toàn bộ khóa bị database từ chối.
- Truy vấn bằng đủ thành phần khóa trả đúng một hàng.
- Truy vấn thiếu một thành phần không vô tình trả về nhiều hàng khi code kỳ vọng một hàng.
- Update và delete chỉ tác động đúng hàng.
- Foreign key tới khóa ghép chấp nhận cặp hợp lệ và từ chối cặp không hợp lệ.
- `save` phân biệt insert và update đúng với chiến lược ID của phiên bản Spring Data đang dùng.
- Transaction rollback khi một thao tác ghi trong aggregate thất bại.
- Các kiểu dữ liệu trong ID được bind và mapping chính xác qua driver production.

Với mô hình surrogate key, bổ sung kiểm tra rằng unique constraint vẫn ngăn cặp khóa nghiệp vụ trùng nhau, kể cả khi hai request chạy đồng thời. Kiểm tra Repository CRUD theo ID đơn và derived query theo các thành phần business key.

## 12. Ví dụ hoàn chỉnh: chọn surrogate key cho dòng hàng

Giả sử ứng dụng cần các thao tác:

- Tải toàn bộ dòng hàng theo `order_id`, sắp xếp theo `line_no`.
- Tìm một dòng theo `(order_id, line_no)`.
- Cập nhật số lượng một dòng.
- Các module khác đôi khi cần tham chiếu một dòng hàng bằng ID.

Mô hình dùng surrogate key có thể đáp ứng các nhu cầu đó:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_line_order_line_no UNIQUE (order_id, line_no)
);

CREATE INDEX idx_order_line_order_line_no
    ON order_line (order_id, line_no);
```

Entity và repository:

```java
@Table("order_line")
public record OrderLine(
    @Id Long id,
    Long orderId,
    Integer lineNo,
    Long productId,
    Integer quantity,
    BigDecimal unitPrice
) {}

public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {

    Flux<OrderLine> findByOrderIdOrderByLineNo(Long orderId);

    Mono<OrderLine> findByOrderIdAndLineNo(Long orderId, Integer lineNo);
}
```

Tầng nghiệp vụ có thể dùng một kiểu định danh có ý nghĩa:

```java
public record OrderLineKey(Long orderId, Integer lineNo) {}

public Mono<OrderLine> getLine(OrderLineKey key) {
    return orderLineRepository.findByOrderIdAndLineNo(
        key.orderId(),
        key.lineNo()
    );
}
```

Trong ví dụ này, `id` giúp Repository sử dụng CRUD chuẩn; `OrderLineKey` giúp code nghiệp vụ biểu diễn định danh tự nhiên; unique constraint giữ đúng quy tắc của database. Nếu sau này số dòng thay đổi, ứng dụng cần xác định rõ liệu đó là cập nhật thuộc tính nghiệp vụ hay thay đổi định danh. Với ID thay thế, việc thay đổi `line_no` không làm thay đổi ID kỹ thuật của hàng.

## 13. Quy trình ra quyết định

Khi gặp một bảng có composite primary key, có thể đi theo trình tự:

**Bước 1 — Xác định lý do khóa ghép tồn tại.** Các cột là định danh tự nhiên ổn định hay chỉ là một quy tắc duy nhất nghiệp vụ?

**Bước 2 — Xác định phiên bản framework thực tế.** Dùng dependency insight hoặc dependency tree để tìm Spring Data Relational và Spring Data R2DBC đã resolve.

**Bước 3 — Đọc tài liệu theo phiên bản.** Xác minh composite ID mapping, kiểu ID, Repository API và các giới hạn liên quan.

**Bước 4 — Xác định API cần dùng.** Ứng dụng cần `findById`, `save`, `deleteById` hay chỉ cần query theo bộ cột bằng SQL?

**Bước 5 — So sánh phương án.** Cân nhắc composite ID trực tiếp, surrogate ID cộng unique constraint, hoặc SQL tùy chỉnh qua `DatabaseClient`.

**Bước 6 — Tạo integration test.** Kiểm tra insert/read/update/delete, duplicate key, entity newness, transaction và driver thực tế.

**Bước 7 — Ghi lại quyết định.** Nêu lý do chọn mô hình, phiên bản đã kiểm chứng, constraint cần giữ và những giới hạn cần theo dõi khi nâng cấp framework.

## 14. Kết luận

Khóa ghép là một tính năng của mô hình quan hệ ở cấp database, nhưng mapping thành ID entity trong Spring Data Relational là vấn đề phụ thuộc phiên bản và API. Cần kiểm tra dependency thực tế, tài liệu đúng release train và toàn bộ vòng đời Repository trước khi chọn composite ID trực tiếp.

Nếu cần một ID đơn giản và khả năng tích hợp CRUD ổn định, surrogate key kết hợp unique constraint thường là lựa chọn thực dụng: database vẫn bảo vệ khóa nghiệp vụ, còn Spring Data dùng ID đơn để quản lý entity. Nếu schema bắt buộc giữ khóa ghép hoặc truy vấn có tính chuyên biệt, `DatabaseClient` cho phép bind đầy đủ các thành phần khóa và ánh xạ kết quả theo nhu cầu. Quyết định nên dựa trên access pattern, tính ổn định của khóa, yêu cầu tương thích và integration test trên đúng driver/database.
