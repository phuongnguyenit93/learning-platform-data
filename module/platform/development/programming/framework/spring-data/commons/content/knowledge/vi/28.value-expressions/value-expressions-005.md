# Biểu thức trong truy vấn khai báo và cú pháp bind riêng từng store

## 1. Vai trò của biểu thức trong truy vấn khai báo

Trong module `SPRING_DATA_COMMONS`, **biểu thức giá trị** giúp tính giá trị từ tham số phương thức, cấu hình hoặc ngữ cảnh mà hạ tầng cung cấp. Khi dùng với truy vấn khai báo, biểu thức có thể lấy một phần dữ liệu từ đối tượng đầu vào rồi đưa kết quả vào vị trí bind của truy vấn.

Ví dụ, service truyền một bộ lọc gồm trạng thái sản phẩm và số lượng tồn kho tối thiểu. Repository lấy hai giá trị này để truy vấn. Ý định nghiệp vụ giống nhau, nhưng cách viết truy vấn phụ thuộc store:

- JPA thường dùng JPQL với entity và thuộc tính Java.
- MongoDB dùng query document với các toán tử của MongoDB.
- JDBC và R2DBC dùng SQL, đi kèm cách bind mà module và driver hỗ trợ.

Spring Data Commons cung cấp abstraction dùng chung cho biểu thức; nó không thống nhất JPQL, SQL và JSON thành một ngôn ngữ truy vấn. Cú pháp `@Query` phải được đọc cùng module cung cấp annotation đó.

Mục tiêu của bài là xác định đúng nguồn dữ liệu của biểu thức, phân biệt bind giá trị với thay thế nội dung truy vấn và viết đúng cú pháp theo store. Những quyết định này cũng ảnh hưởng đến derived queries, phân trang, sắp xếp, projection và các phần mở rộng repository trong một ứng dụng thực tế.

## 2. Ba lớp cú pháp cần tách biệt

### 2.1. Ngôn ngữ truy vấn của store

Đây là lớp mô tả dữ liệu cần tìm:

```text
JPQL:    select p from Product p where p.status = ...
SQL:     SELECT id, status, stock FROM product WHERE status = ...
MongoDB: { 'status': ... }
```

`Product` trong JPQL là tên entity, không nhất thiết là tên bảng. `product` trong SQL là tên bảng theo schema và dialect đang dùng. Key trong query MongoDB phải phù hợp với mapping của document.

### 2.2. Biểu thức được đánh giá trong ứng dụng

Hai dạng thường gặp trong value expressions:

| Dạng | Ý nghĩa |
| --- | --- |
| `#{...}` | Biểu thức SpEL được đánh giá với một evaluation context |
| `${...}` | Property placeholder được phân giải từ cấu hình |

Chẳng hạn, `#{#filter.status()}` đọc trạng thái từ một biến trong context, còn `${inventory.default-status:ACTIVE}` tham chiếu cấu hình với giá trị dự phòng. Dấu `#` trước tên biến thuộc cú pháp SpEL; tên property cấu hình trong `${...}` không cần dấu này.

Spring Data mô tả value expressions là sự kết hợp SpEL và property placeholder. Khả năng sử dụng tại annotation và cách đánh dấu bind phải theo tài liệu module cụ thể. [Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html).

### 2.3. Cú pháp đánh dấu giá trị cần bind

Khi biểu thức cung cấp một giá trị cho điều kiện truy vấn, module có thể yêu cầu tiền tố như `:#{...}` hoặc `?#{...}`. Tiền tố này là một phần của cú pháp query binding, không phải phép toán nằm bên trong SpEL.

Ví dụ:

```text
:#{#filter.status()}
│ └─ biểu thức SpEL lấy giá trị từ biến filter
└─── dấu nhận diện bind theo cú pháp module đang dùng
```

Tương tự, `?0`, `?1`, `:status` và `$1` không phải bốn cách viết có thể thay thế tùy ý. Chúng thuộc các cơ chế bind khác nhau.

## 3. Bảng đối chiếu cú pháp theo store

| Module | Bind tham số thông thường | Ví dụ bind kết quả SpEL | Điểm cần nhớ |
| --- | --- | --- | --- |
| Spring Data JPA | `:status`, `?1` | `:#{#filter.status()}`, `?#{[0]}` | Tham số vị trí JPQL bắt đầu từ 1; chỉ số argument trong biểu thức bắt đầu từ 0 |
| Spring Data MongoDB | `?0` | `?#{[0]}` | Query dạng JSON/BSON; argument đầu tiên là `?0` |
| Spring Data JDBC | `:status` | `:#{#filter.status()}` | Query SQL; module dùng named parameters |
| Spring Data R2DBC | `:status`; native marker tùy driver | `:#{[0]}` | Khi kết hợp SpEL với tham số thông thường, dùng named notation để tránh sai thứ tự bind |

Các dạng trong bảng được minh họa trong tài liệu từng module: [JPA](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html), [MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html), [JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html), [R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html).

Không áp dụng bảng như một cam kết cho mọi phiên bản lịch sử. Khi chuyển module hoặc nâng phiên bản, xác nhận lại cú pháp, nguồn evaluation context và giới hạn của query parser đang dùng.

Đặc biệt, trong một ví dụ JPA có đúng một tham số, `?1` và `?#{[0]}` có thể cùng lấy dữ liệu từ argument đầu tiên. Hai con số khác nhau vì một bên là chỉ số tham số JPQL, một bên là truy cập mảng argument của biểu thức.

## 4. Một bộ lọc dùng để so sánh các module

Dùng record sau làm đầu vào cho các ví dụ độc lập:

```java
import java.util.Objects;

public record ProductFilter(String status, int minStock) {

    public ProductFilter {
        Objects.requireNonNull(status, "Status is required");
        if (status.isBlank()) {
            throw new IllegalArgumentException("Status must not be blank");
        }
        if (minStock < 0) {
            throw new IllegalArgumentException("Minimum stock must be non-negative");
        }
    }
}
```

Lời gọi minh họa:

```java
ProductFilter filter = new ProductFilter("ACTIVE", 10);
```

Ý định truy vấn là tìm sản phẩm có `status` bằng `ACTIVE` và `stock` lớn hơn hoặc bằng `10`. Record giữ dữ liệu đầu vào; nó không chứa mã SpEL do người dùng cung cấp.

Mỗi ví dụ bên dưới thuộc một ứng dụng hoặc module cấu hình riêng. `Product`, `MongoProduct` và `ProductRow` là các model tương ứng với store, có mapping hợp lệ cho ID, trạng thái và tồn kho. Các đoạn mã tập trung vào khai báo truy vấn, không nhằm tạo một ứng dụng chứa đồng thời cả bốn loại repository.

## 5. JPA: bind giá trị và tham chiếu tên entity

### 5.1. Lấy dữ liệu từ đối tượng tham số

```java
import java.util.List;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface ProductJpaRepository extends Repository<Product, Long> {

    @Query("""
        select p from Product p
        where p.status = :#{#filter.status()}
          and p.stock >= :#{#filter.minStock()}
        """)
    List<Product> search(@Param("filter") ProductFilter filter);
}
```

Ở đây:

- `Product` là entity JPA có các thuộc tính Java `status` và `stock`.
- `@Param("filter")` đặt tên tham số để biểu thức tham chiếu rõ ràng.
- `#filter.status()` cho kết quả `String`; `#filter.minStock()` cho kết quả số.
- Kết quả được dùng như giá trị tham số; không phải đoạn JPQL do người dùng viết.

`@Param` là annotation của Commons để bind tham số phương thức bằng tên. Ví dụ khai báo tên tường minh để không phụ thuộc việc tên tham số Java có được giữ lại trong quá trình biên dịch hay không. [Param](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/Param.html).

Nếu service đã tách được hai giá trị, truy vấn có thể chỉ dùng `:status` và `:minStock` với hai tham số bình thường. Không cần thêm SpEL khi việc lấy giá trị không có lợi ích cụ thể.

### 5.2. Tên entity thuộc một cơ chế khác

Trong các trường hợp JPA hỗ trợ template tên entity, có thể gặp:

```java
@Query("select p from #{#entityName} p where p.status = :status")
List<Product> findConfiguredStatus(@Param("status") String status);
```

`#{#entityName}` xuất hiện ở vị trí tên entity trong văn bản JPQL. Nó khác `:#{...}` dùng để tạo giá trị bind. Biến `entityName` phục vụ context template này; không mặc nhiên có cùng tập biến trong context biểu thức của tham số. [JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html).

Không dùng `:tableName` hoặc `:entityName` như một tham số thông thường rồi kỳ vọng database/provider coi chuỗi truyền vào là tên bảng hoặc entity. Giá trị bind đại diện dữ liệu, còn identifier thuộc cấu trúc truy vấn.

### 5.3. Property placeholder trong query được hỗ trợ

Ở các phiên bản JPA hỗ trợ cú pháp value expression tương ứng, tài liệu minh họa property placeholder làm giá trị bind. Có thể áp dụng ý tưởng đó cho cấu hình trạng thái mặc định:

```java
@Query("select p from Product p where p.status = ?${inventory.default-status:ACTIVE}")
List<Product> findWithDefaultStatus();
```

Nguồn của giá trị là `Environment`, không phải argument tên `inventory`. Giá trị dự phòng `ACTIVE` cũng là dữ liệu bind. Việc application có property này không bảo đảm mọi module `@Query` đều hiểu cùng cú pháp; kiểm tra hỗ trợ của phiên bản được dùng.

Không nhầm property cấu hình với ngữ cảnh theo người dùng. Một trạng thái mặc định toàn ứng dụng khác với tenant hoặc quyền truy cập của một request cụ thể.

## 6. MongoDB: biểu thức nằm trong query document

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductMongoRepository
        extends MongoRepository<MongoProduct, String> {

    @Query("""
        {
          'status': ?#{[0].status()},
          'stock': { '$gte': ?#{[0].minStock()} }
        }
        """)
    List<MongoProduct> search(ProductFilter filter);
}
```

Trong khai báo này, `[0]` là argument `ProductFilter` đầu tiên. `'$gte'` là toán tử MongoDB được viết cố định trong query; biểu thức cung cấp giá trị số cho toán tử đó.

Nếu phương thức chỉ nhận một trạng thái, bind thông thường đã đủ:

```java
@Query("{ 'status': ?0 }")
List<MongoProduct> findByExplicitStatus(String status);
```

Không viết `?1` vì nghĩ rằng mọi Spring Data repository đều đánh số từ 1. Đối với phương thức trên, `?0` mới tham chiếu argument đầu tiên.

Tài liệu MongoDB hỗ trợ biểu thức tạo predicate value hoặc cấu trúc con, đồng thời khuyến nghị để biểu thức tạo toàn bộ giá trị bind thay vì nhúng vào giữa một chuỗi BSON. [MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

Ví dụ nên tránh như một quy ước thiết kế:

```java
// Ghép biểu thức vào giữa một BSON string làm việc quoting khó kiểm soát.
@Query("{ 'status': 'prefix-?#{[0]}' }")
List<MongoProduct> findWithEmbeddedExpression(String suffix);
```

Nếu thật sự cần giá trị có tiền tố, hãy tính một giá trị hoàn chỉnh trong service rồi bind nó, hoặc để một biểu thức tin cậy tạo trọn giá trị ở vị trí được module hỗ trợ. Không tự nối chuỗi JSON từ dữ liệu đầu vào rồi chuyển nó thành cấu trúc query.

Một số API cho phép truyền đối tượng cấu trúc như document hoặc map. Khi chọn thiết kế đó, phải xác định rõ kiểu và các toán tử được phép; khả năng bind một giá trị String không có nghĩa mọi cấu trúc BSON đều mang cùng hợp đồng.

## 7. JDBC: named parameters và SQL

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface ProductJdbcRepository
        extends CrudRepository<ProductRow, Long> {

    @Query("""
        SELECT id, status, stock
        FROM product
        WHERE status = :#{#filter.status()}
          AND stock >= :#{#filter.minStock()}
        """)
    List<ProductRow> search(@Param("filter") ProductFilter filter);
}
```

Đây là SQL, nên tên bảng và các cột phải đúng với schema. Bộ cột được chọn cũng cần đủ để mapper tạo `ProductRow`; biểu thức bind đúng không khắc phục được một kết quả thiếu cột mà constructor bắt buộc cần.

Spring Data JDBC mô tả dạng biểu thức có tiền tố `:` như bind variable: kết quả SpEL được gán vào một biến bind. Module này sử dụng named parameters. Tài liệu cũng phân biệt dạng biểu thức thay thế nội dung query, có thời điểm đánh giá khác với biểu thức tham số. [JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html).

Vì vậy, không đổi `:#{#filter.status()}` thành `?#{[0]}` bằng cách sao chép từ MongoDB. Cũng không lấy cú pháp `?` của JDBC driver thuần làm bằng chứng rằng annotation query của Spring Data JDBC hỗ trợ cùng cách khai báo.

Nếu cần tên bảng được tính từ metadata mapping, sử dụng đúng cơ chế template mà phiên bản JDBC hỗ trợ. Không lấy tên bảng tùy ý từ request và đặt vào vị trí này.

## 8. R2DBC: named notation và native bind marker

```java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface ProductR2dbcRepository
        extends ReactiveCrudRepository<ProductRow, Long> {

    @Query("""
        SELECT id, status, stock
        FROM product
        WHERE status = :#{[0].status()}
          AND stock >= :#{[0].minStock()}
        """)
    Flux<ProductRow> search(ProductFilter filter);
}
```

Ở đây tiếp tục dùng mảng argument `[0]`, nhưng marker phía ngoài là `:`. Query không dùng `?#{...}` như ví dụ MongoDB.

Một khai báo khác kết hợp giá trị tính bằng biểu thức với named parameter thông thường:

```java
import org.springframework.data.repository.query.Param;

@Query("""
    SELECT id, status, stock
    FROM product
    WHERE status = :#{#filter.status()}
      AND stock >= :minStock
    """)
Flux<ProductRow> searchWithThreshold(
        @Param("filter") ProductFilter filter,
        @Param("minStock") int minStock);
```

R2DBC có native bind marker tùy driver, chẳng hạn `$1` trong một số khai báo dành cho PostgreSQL. Khi kết hợp SpEL với tham số thông thường, tài liệu khuyến nghị named notation thay cho native markers để giữ đúng thứ tự bind. [R2DBC Query Methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html).

Sự tồn tại của `Flux` không làm các marker trở nên giống MongoDB reactive hoặc JPA. Không đưa tác vụ blocking vào biểu thức chỉ vì nó trả về một giá trị nhỏ. Khi truy vấn cần context reactive, phải sử dụng cơ chế context/extension được module hỗ trợ, thay vì giả định dữ liệu trong `ThreadLocal` của lúc tạo pipeline vẫn tồn tại lúc thực thi.

## 9. Bind giá trị khác với thay thế cấu trúc query

Xét yêu cầu tìm sản phẩm theo trạng thái:

```text
Dữ liệu:             ACTIVE
Toán tử cố định:     status = ...
Identifier cố định:  status
```

Bind `ACTIVE` vào vị trí dữ liệu phù hợp. Nhưng truyền chuỗi `status = 'ACTIVE'` vào một bind parameter không biến chuỗi đó thành một predicate mới.

| Mong muốn | Cách xử lý phù hợp |
| --- | --- |
| So sánh trạng thái với giá trị đầu vào | Bind một String |
| Lấy ngưỡng từ thuộc tính của DTO | Biểu thức lấy thuộc tính rồi bind kết quả |
| Bỏ hoặc thêm nhiều predicate tùy bộ lọc | Query builder, Criteria, Specification hoặc fragment theo hỗ trợ của store |
| Đổi trường sắp xếp từ tùy chọn giao diện | Ánh xạ tùy chọn sang trường được phép và dùng cơ chế sort được hỗ trợ |
| Đổi tên bảng hoặc collection | Thiết kế mapping/template riêng của store, với nguồn cấu hình tin cậy |
| Trả một projection khác | Chọn khai báo truy vấn, kiểu trả về và mapping phù hợp |

Không cố biểu diễn toàn bộ ngôn ngữ lọc trong một biểu thức ba ngôi dài. Khi số tổ hợp điều kiện tăng, truy vấn tạo bằng API chuyên dụng thường làm điều kiện, kiểu dữ liệu và giới hạn của store rõ hơn.

Đồng thời, phân biệt hai nơi thực thi:

```text
Biểu thức SpEL: được đánh giá trong ứng dụng Java.
JPQL/SQL/MongoDB query: được xử lý bởi provider và/hoặc database.
```

`stock >= :#{#filter.minStock()}` không có nghĩa SpEL duyệt từng bản ghi rồi kiểm tra tồn kho. Nó tính ngưỡng; việc lọc bản ghi thuộc query của store.

## 10. Evaluation context, kiểu dữ liệu và vòng đời

### 10.1. Biến chỉ tồn tại khi context cung cấp

`#filter`, mảng argument, `#entityName` và các hàm mở rộng không phải một tập biến toàn cục dùng chung cho mọi annotation. Context đánh giá quy định biến, root object và khả năng truy cập property/method. [SpEL Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html).

Các tiện ích như `principal` hoặc hàm tenant cần cơ chế tích hợp tương ứng. Việc có một bean security trong ứng dụng không đủ để kết luận mọi query expression đều truy cập được nó.

Khi dữ liệu context quyết định phạm vi truy cập, xử lý trường hợp thiếu dữ liệu phải rõ ràng. Không dùng fallback “mọi tenant” hoặc bỏ predicate vì một biến không được cung cấp. Giá trị tenant do client truyền vào cũng không tự trở thành tenant đã được xác thực chỉ vì được bind đúng cú pháp.

### 10.2. Kết quả biểu thức cần đúng kiểu

Với bộ lọc minh họa, kết quả mong muốn là `String` và số nguyên. Nếu biểu thức vô tình tạo chuỗi `"10"` thay cho số `10`, khả năng chuyển đổi và cách so sánh phụ thuộc mapper, provider hoặc driver. Không dựa vào việc một database tự ép kiểu để xem đó là hợp đồng chung của Spring Data.

Tương tự, một collection dùng cho điều kiện `IN` không có nghĩa module có thể thay nó vào mọi dạng danh sách hoặc mọi vị trí trong query. Cần xem cách bind collection của đúng store và ý nghĩa khi collection rỗng.

### 10.3. Parse biểu thức khác với đánh giá ra giá trị

Một đối tượng `ValueExpression` biểu diễn chuỗi đã parse và được đánh giá với `ValueEvaluationContext` cung cấp cho lần đánh giá. Kết quả có thể null hoặc thay đổi theo context. [ValueExpression](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpression.html).

Có thể hình dung đường bind theo các bước trách nhiệm:

```text
Query và biểu thức tin cậy
  -> nhận diện phần template và phần bind
  -> lấy argument/context của lần thực thi
  -> tính các giá trị cần bind
  -> bind theo cơ chế module/provider/driver
  -> thực thi query và ánh xạ kết quả
```

Sơ đồ không khẳng định mọi loại template đều được đánh giá lại ở mỗi lần gọi. Một số template cấu trúc có thể được đánh giá trước lần thực thi đầu tiên, trong khi biểu thức giá trị tham số được tính cho lần chạy. Phải xác định loại biểu thức đang dùng trước khi dựa vào một thời điểm đánh giá.

Cache phần đã parse không đồng nghĩa cache kết quả theo người dùng trước đó. Nếu ứng dụng tự xây lớp mở rộng, không lưu giá trị của một request vào field dùng chung rồi tái sử dụng cho request khác. Với query chứa cả phần dữ liệu và phần đếm, cũng không giả định chúng chỉ làm phát sinh một lần đánh giá hay một lần gọi hàm phụ trợ.

## 11. Các tình huống dễ đúng cú pháp nhưng sai hành vi

### 11.1. Null không tự tạo điều kiện tùy chọn

Một biểu thức trả null không tự làm predicate biến mất. Trong SQL/JPQL, so sánh bằng null không tương đương `IS NULL`. MongoDB có quy tắc riêng về null và thuộc tính vắng mặt.

Nếu bộ lọc cho phép bỏ trạng thái, hãy công bố rõ “bỏ trạng thái” nghĩa là không lọc, tìm trạng thái null hay báo dữ liệu thiếu. Ví dụ chính dùng constructor của `ProductFilter` để từ chối status null và tránh việc query phải suy đoán ý nghĩa này.

### 11.2. Bind tham số không xóa ý nghĩa wildcard

Một chuỗi được bind an toàn vẫn có thể chứa `%` hoặc `_` mang ý nghĩa trong `LIKE`, hoặc ký tự có ý nghĩa với regex khi query sử dụng regex. Đây là vấn đề ngữ nghĩa của toán tử, khác việc coi dữ liệu thành mã biểu thức.

Nếu yêu cầu là tìm ký tự theo nghĩa đen, cần chính sách escape đúng với toán tử và store. Không sao chép hàm escape của context JPA sang MongoDB rồi giả định nó xử lý được regex. Nếu dùng derived query thay cho query khai báo, vẫn cần kiểm tra hợp đồng xử lý giá trị của module đó.

### 11.3. Page và count phải cùng phạm vi lọc

JPA `@Query` có thể khai báo `countQuery` để phục vụ phân trang. Query lấy nội dung và query đếm phải giữ cùng điều kiện nghiệp vụ, đặc biệt khi dùng biểu thức cho tenant hoặc trạng thái. [JPA Query API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/Query.html).

Không suy rằng thêm `Pageable` vào mọi phương thức có query String sẽ khiến mọi store tự viết lại query. Với JDBC/R2DBC, phải kiểm tra giới hạn query khai báo của module. Biểu thức bind không tự thêm pagination, sort hoặc mapping projection.

### 11.4. Biểu thức không thay thế auditing và transaction

Tính một giá trị thời gian hoặc username trong query không tự kích hoạt đầy đủ quy trình auditing của entity. Một query cập nhật trực tiếp cũng có thể đi theo đường khác với việc lưu entity. Cần dùng đúng khả năng callback, auditing và transaction của store thay vì suy từ abstraction biểu thức.

## 12. Giữ biểu thức tin cậy và dễ bảo trì

Tách rõ **chuỗi biểu thức** với **giá trị đầu vào**:

```text
Chuỗi biểu thức do ứng dụng định nghĩa: :#{#filter.status()}
Giá trị client cung cấp:               ACTIVE
```

Không đưa một chuỗi client nhập vào parser SpEL để “hỗ trợ lọc linh hoạt”. Một giá trị đầu vào nhìn giống `#{...}` vẫn nên được giữ là dữ liệu khi hợp đồng chỉ nhận status; không đánh giá lại nó thành biểu thức. Cũng không ghép đầu vào thành một đoạn JPQL, SQL hoặc JSON rồi coi đó là cách bind.

Nên giữ các method được biểu thức gọi là các phép lấy hoặc tính dữ liệu nhỏ, không có tác dụng phụ. Nếu biểu thức gọi dịch vụ từ xa, ghi dữ liệu hoặc phụ thuộc trạng thái thay đổi trong quá trình chạy, query trở nên khó dự đoán và khó kiểm chứng. Chuyển việc chuẩn bị dữ liệu về service khi logic đã vượt quá vai trò lấy tham số.

Khi điều kiện đơn giản, ưu tiên bind trực tiếp. Khi cần lấy thuộc tính của một đầu vào có cấu trúc, biểu thức ngắn làm khai báo rõ hơn. Khi cần thay đổi cấu trúc query theo nhiều nhánh, dùng cơ chế xây query hoặc fragment phù hợp với store.

## 13. Hướng thực hành và chẩn đoán

Có thể dùng cùng bộ dữ liệu cho bốn ví dụ, trong bốn môi trường tích hợp tương ứng:

| Sản phẩm | Trạng thái | Tồn kho |
| --- | --- | --- |
| A | ACTIVE | 5 |
| B | ACTIVE | 10 |
| C | ACTIVE | 25 |
| D | DISABLED | 40 |

Với `ProductFilter("ACTIVE", 10)`, kết quả mong muốn là B và C. Với `ProductFilter("ACTIVE", 20)`, chỉ còn C. Không phụ thuộc thứ tự kết quả nếu query chưa công bố sort.

Một đợt kiểm chứng sau khi cấu hình ứng dụng nên bao phủ:

1. Hai lần gọi liên tiếp có bộ lọc khác nhau, để phát hiện giá trị bind bị giữ lại.
2. Trường hợp ngưỡng bằng đúng tồn kho, để phân biệt `>=` với `>`.
3. Argument đầu tiên và argument thứ hai, để phát hiện nhầm `?1`, `?0` và `[0]`.
4. Giá trị có ký tự đặc biệt, để bảo đảm hợp đồng nhận dữ liệu được giữ nguyên.
5. Kiểu trả về và mapping cột/field, để phân biệt lỗi bind với lỗi ánh xạ kết quả.
6. Pagination/count và context theo người dùng nếu sản phẩm thực tế sử dụng các tính năng ấy.

Các điểm chẩn đoán thường gặp:

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không nhận diện query annotation hoặc parser xử lý sai ngôn ngữ | Kiểm tra import `@Query` và module repository |
| Không tìm được biến `filter` | Kiểm tra `@Param`, cách giữ tên tham số và context |
| Lỗi truy cập argument hoặc lấy nhầm giá trị | Phân biệt chỉ số query bind với chỉ số mảng argument |
| Biểu thức cho kết quả đúng nhưng database báo lỗi kiểu | Kiểm tra kiểu kết quả, mapper và kiểu đích của store |
| Query chạy nhưng thiếu hoặc thừa bản ghi | Kiểm tra null, toán tử, wildcard và điều kiện nghiệp vụ |
| Kết quả đúng nhưng số lượng trong Page sai | Đối chiếu predicate giữa content query và count query |
| Chỉ lỗi khi đổi driver R2DBC | Kiểm tra native markers và việc trộn chúng với SpEL |

Thử biểu thức bằng một parser độc lập chỉ xác nhận một phần cú pháp và evaluation context do bài thử cung cấp. Nó không chứng minh annotation query được module nhận diện, tham số được bind đúng hoặc database hiểu query cuối cùng.

Khi đọc một khai báo `@Query`, hãy xác định lần lượt: module cung cấp annotation, ngôn ngữ query, nguồn của từng giá trị, marker bind và kiểu kết quả. Cách đọc này giúp sử dụng abstraction biểu thức của Spring Data Commons trong đúng phạm vi, đồng thời giữ rõ những phần phụ thuộc khả năng của từng kho dữ liệu.
