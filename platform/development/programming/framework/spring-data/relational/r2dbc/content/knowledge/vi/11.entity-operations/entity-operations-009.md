# Sử dụng giao diện thao tác theo từng bước để biểu đạt truy vấn

Spring Data R2DBC cung cấp `R2dbcEntityTemplate` với giao diện thao tác theo từng bước (fluent API). Thay vì ghép một câu SQL dài, ứng dụng có thể mô tả truy vấn bằng các bước có ý nghĩa: chọn kiểu entity, xây dựng điều kiện, sắp xếp, giới hạn kết quả và chọn cách tiêu thụ publisher. Cùng một phong cách API cũng được dùng để insert, update và delete.

Fluent API phù hợp khi truy vấn cần được xây dựng linh hoạt theo tham số đầu vào, nhưng vẫn muốn giữ mapping entity của Spring Data. Nó nằm ở mức trừu tượng cao hơn `DatabaseClient`: ứng dụng làm việc với entity, thuộc tính và `Query`/`Criteria`, còn Spring Data chuyển các mô tả đó thành câu lệnh phù hợp với database.

## 1. R2dbcEntityTemplate trong kiến trúc truy cập dữ liệu

`R2dbcEntityTemplate` là abstraction của Spring Data Relational dùng để thao tác với entity qua R2DBC. Nó dựa trên `DatabaseClient` và `MappingR2dbcConverter` để thực thi SQL, bind tham số và chuyển đổi giữa hàng dữ liệu với đối tượng Java.

Có thể chọn mức API theo nhu cầu:

| API | Mục đích |
| --- | --- |
| Reactive repository | Các thao tác CRUD và truy vấn theo tên phương thức |
| `R2dbcEntityTemplate` fluent API | Xây dựng truy vấn entity theo từng bước bằng `Query`, `Criteria`, `Sort` |
| `DatabaseClient` | Thực thi SQL tùy chỉnh và ánh xạ kết quả theo ý muốn |
| R2DBC SPI | Điều khiển kết nối, statement và result ở mức thấp |

Fluent API giúp tránh phải tự quản lý kết nối và ánh xạ từng `Row` trong những truy vấn entity thông thường. Nó vẫn giữ mô hình reactive: các thao tác trả về `Mono` hoặc `Flux` và được thực thi khi publisher được subscribe.

## 2. Cấu hình và inject R2dbcEntityTemplate

Trong ứng dụng Spring Boot có starter R2DBC và driver phù hợp, Spring thường tự cấu hình `DatabaseClient`, mapping infrastructure và `R2dbcEntityTemplate`.

Có thể inject template vào service:

```java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final R2dbcEntityTemplate template;

    public ProductQueryService(R2dbcEntityTemplate template) {
        this.template = template;
    }
}
```

Nếu dự án cần tự cấu hình nhiều `ConnectionFactory` hoặc nhiều database, cần tạo template tương ứng và gắn đúng converter, mapping context cùng transaction manager. Với ứng dụng chỉ có một database, nên tận dụng auto-configuration nếu nó đáp ứng yêu cầu.

Ví dụ entity:

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        String status,
        BigDecimal price
) {}
```

Tên thuộc tính Java được Spring Data ánh xạ sang cột theo quy tắc mapping và metadata. Có thể dùng `@Column` khi tên cột khác quy tắc mặc định.

## 3. Các bước cơ bản của fluent API

Với thao tác đọc, cách diễn đạt thường có dạng:

```java
template.select(Product.class)
        .matching(query(Criteria.where("status").is("ACTIVE")))
        .all();
```

Mỗi bước có vai trò riêng:

1. `select(Product.class)` xác định kiểu entity cần đọc.
2. `matching(query(...))` cung cấp điều kiện truy vấn.
3. `all()` yêu cầu phát tất cả kết quả phù hợp dưới dạng `Flux<Product>`.

Các bước được nối thành một biểu thức dễ đọc. Kiểu kết quả vẫn reactive: `all()` trả publisher nhiều phần tử; ứng dụng có thể tiếp tục dùng `map`, `filter`, `take`, `collectList` hoặc trả `Flux` cho WebFlux.

Với các thao tác khác, cấu trúc tương tự:

```java
template.insert(Product.class).using(product);

template.update(Product.class)
        .matching(query(Criteria.where("id").is(id)))
        .apply(Update.update("status", "ARCHIVED"));

template.delete(Product.class)
        .matching(query(Criteria.where("id").is(id)))
        .all();
```

Fluent API mô tả ý định theo từng bước; publisher chỉ thực hiện công việc khi được tiêu thụ.

## 4. Xây dựng Query bằng Criteria

`Query` biểu diễn các điều kiện, sắp xếp và giới hạn của truy vấn. `Criteria` mô tả một điều kiện trên thuộc tính entity.

Các phép so sánh thường dùng:

| Criteria | Ý nghĩa |
| --- | --- |
| `is(value)` | Bằng giá trị |
| `not().is(value)` | Phủ định điều kiện bằng giá trị |
| `greaterThan(value)` | Lớn hơn |
| `greaterThanOrEquals(value)` | Lớn hơn hoặc bằng |
| `lessThan(value)` | Nhỏ hơn |
| `lessThanOrEquals(value)` | Nhỏ hơn hoặc bằng |
| `in(values)` | Thuộc một tập giá trị |
| `notIn(values)` | Không thuộc tập giá trị |
| `like(pattern)` | So khớp theo mẫu |
| `isNull()` | Giá trị null |
| `isNotNull()` | Giá trị khác null |

Ví dụ tìm sản phẩm đang hoạt động:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

Flux<Product> products = template.select(Product.class)
        .matching(query)
        .all();
```

Tên trong `Criteria.where(...)` thường là tên thuộc tính persistent của entity, không nhất thiết là tên cột SQL đã viết hoa/thường hoặc tên cột vật lý sau mapping. Spring Data dùng metadata để chuyển thuộc tính thành cột phù hợp.

### Kết hợp nhiều điều kiện AND

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("price").greaterThanOrEquals(new BigDecimal("100"))
        .and("name").like("%keyboard%");

Query query = Query.query(criteria);
```

Các điều kiện nối bằng `and` đều phải đúng để hàng được chọn.

### Kết hợp điều kiện OR

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("FEATURED");

Query query = Query.query(criteria);
```

Điều kiện trên lấy sản phẩm có trạng thái ACTIVE hoặc FEATURED. Với biểu thức phức tạp có nhiều nhóm AND/OR, hãy tạo các nhóm `Criteria` rõ ràng và xác nhận SQL được sinh ra đáp ứng đúng thứ tự logic mà nghiệp vụ yêu cầu.

## 5. Xây dựng truy vấn động từ tham số

Một trường hợp phổ biến là màn hình tìm kiếm cho phép người dùng chọn một số bộ lọc tùy chọn. Không nên tạo nhiều phương thức repository cho mọi tổ hợp điều kiện. Có thể bắt đầu từ một điều kiện bắt buộc rồi bổ sung `Criteria` khi tham số có giá trị:

```java
public Flux<Product> searchProducts(
        String status,
        BigDecimal minimumPrice,
        String namePart) {

    Criteria criteria = Criteria.where("status").is(status);

    if (minimumPrice != null) {
        criteria = criteria.and("price")
                .greaterThanOrEquals(minimumPrice);
    }

    if (namePart != null && !namePart.isBlank()) {
        criteria = criteria.and("name")
                .like("%" + namePart + "%");
    }

    Query query = Query.query(criteria);

    return template.select(Product.class)
            .matching(query)
            .all();
}
```

Ở đây, trạng thái là điều kiện bắt buộc; giá tối thiểu và phần tên chỉ được thêm khi người dùng cung cấp. Các giá trị được đưa vào Criteria để Spring Data xử lý như tham số truy vấn. Không nên nối trực tiếp giá trị đầu vào vào chuỗi SQL.

Nếu mọi điều kiện đều tùy chọn, hãy thiết kế rõ cách tạo nhóm điều kiện ban đầu theo API của phiên bản Spring Data đang dùng. Tránh tự ghép các đoạn SQL hoặc tên cột từ dữ liệu không tin cậy. Với truy vấn động có nhiều nhánh, tách hàm xây dựng Criteria sẽ giúp service dễ đọc hơn.

Lưu ý rằng tham số giá trị có thể bind an toàn, nhưng tên thuộc tính dùng để sắp xếp hoặc tên cột động là một phần cấu trúc truy vấn. Nếu client được phép chọn trường sort, hãy ánh xạ qua danh sách trường được cho phép thay vì truyền nguyên văn chuỗi tùy ý.

## 6. Sắp xếp, giới hạn và phân trang

`Query` có thể kết hợp với `Sort`, `limit` và `offset`:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(Sort.Order.desc("price")))
        .limit(20)
        .offset(40);

Flux<Product> page = template.select(Product.class)
        .matching(query)
        .all();
```

Truy vấn trên lấy tối đa 20 sản phẩm bắt đầu từ vị trí offset 40, sắp xếp giá giảm dần. Trong ứng dụng thực tế, nên thêm một tiêu chí phụ ổn định, chẳng hạn ID, để các hàng có cùng giá vẫn có thứ tự xác định:

```java
Sort sort = Sort.by(
        Sort.Order.desc("price"),
        Sort.Order.asc("id")
);
```

Offset pagination tiện cho các màn hình có số trang, nhưng offset lớn có thể khiến database phải bỏ qua nhiều hàng trước khi trả kết quả. Với tập dữ liệu lớn hoặc thay đổi liên tục, có thể cân nhắc keyset pagination: dùng giá trị của hàng cuối trang trước (ví dụ `price` và `id`) làm điều kiện truy vấn trang tiếp theo.

Khi xây dựng API phân trang, cần kiểm soát `pageSize` và `offset` để tránh client yêu cầu một lượng dữ liệu quá lớn. Không nên mặc định `collectList()` toàn bộ kết quả khi truy vấn không có giới hạn.

## 7. Đọc tất cả, lấy một kết quả hoặc lấy phần tử đầu

Với fluent select, `all()` trả về `Flux<T>` để tiêu thụ toàn bộ các hàng phù hợp:

```java
public Flux<Product> findActiveProducts() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    return template.select(Product.class)
            .matching(query)
            .all();
}
```

Nếu chỉ cần một phần tử đầu tiên, có thể giới hạn truy vấn hoặc dùng toán tử trên publisher:

```java
public Mono<Product> findCheapestActiveProduct() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    )
            .sort(Sort.by(Sort.Order.asc("price")))
            .limit(1);

    return template.select(Product.class)
            .matching(query)
            .all()
            .next();
}
```

`next()` lấy phần tử đầu tiên mà Flux phát ra và hoàn tất. Đặt `limit(1)` trong Query giúp database chỉ cần trả tối đa một hàng. Nếu nghiệp vụ yêu cầu kiểm tra dữ liệu thực sự duy nhất, hãy bảo đảm uniqueness bằng constraint và dùng API có ngữ nghĩa phù hợp; lấy phần tử đầu tiên không chứng minh chỉ có một hàng.

## 8. Insert theo từng bước

Fluent insert bắt đầu bằng kiểu entity và kết thúc bằng entity cần lưu:

```java
public Mono<Product> createProduct(
        String name,
        BigDecimal price) {

    Product product = new Product(
            null,
            name,
            "ACTIVE",
            price
    );

    return template.insert(Product.class)
            .using(product);
}
```

`insert(Product.class)` xác định kiểu entity và mapping metadata. `using(product)` cung cấp object cần insert. Publisher trả entity đã lưu, có thể chứa ID do database sinh.

Với entity bất biến như record, hãy sử dụng instance được phát ra từ publisher:

```java
return template.insert(Product.class)
        .using(product)
        .map(saved -> saved.id());
```

Insert tường minh hữu ích khi nghiệp vụ chắc chắn đang tạo bản ghi mới. Nếu muốn Spring Data chọn insert hoặc update theo trạng thái entity, có thể dùng `repository.save(entity)`; hai API biểu đạt ý định khác nhau.

## 9. Update theo điều kiện

Fluent update sử dụng `matching(Query)` để xác định hàng cần cập nhật và `apply(Update)` để mô tả các trường cần thay đổi:

```java
public Mono<Long> archiveProduct(Long id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
    );

    Update update = Update.update("status", "ARCHIVED");

    return template.update(Product.class)
            .matching(query)
            .apply(update);
}
```

Kết quả là số hàng được cập nhật dưới dạng publisher. Nếu ID không khớp hàng nào, số hàng cập nhật có thể là 0.

Có thể thay đổi nhiều trường trong một lần:

```java
Update update = Update.update("status", "ACTIVE")
        .set("price", new BigDecimal("129.00"));
```

Điều kiện update cần được giới hạn cẩn thận. Nếu Query không có điều kiện đủ hẹp, nhiều hàng có thể bị cập nhật. Với thao tác theo ID, thường nên dùng tiêu chí khóa chính. Với thao tác hàng loạt, hãy thể hiện rõ điều kiện nghiệp vụ và kiểm tra số hàng bị ảnh hưởng.

Fluent update thay đổi các cột được chỉ định, không cần tải toàn bộ entity lên rồi gọi `save`. Điều này hữu ích cho những thao tác cập nhật một vài trường hoặc cập nhật theo điều kiện.

## 10. Delete theo điều kiện

Fluent delete dùng cùng mô hình:

```java
public Mono<Long> deleteProduct(Long id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
    );

    return template.delete(Product.class)
            .matching(query)
            .all();
}
```

`all()` thực thi thao tác xóa cho các hàng phù hợp và trả số hàng bị ảnh hưởng. Tên `all()` ở đây có nghĩa áp dụng cho toàn bộ hàng khớp với Query; vì vậy cần đặc biệt cẩn thận nếu điều kiện trống hoặc rộng hơn dự kiến.

Ví dụ xóa sản phẩm đã ngừng kinh doanh:

```java
public Mono<Long> deleteArchivedProducts() {
    Query query = Query.query(
            Criteria.where("status").is("ARCHIVED")
    );

    return template.delete(Product.class)
            .matching(query)
            .all();
}
```

Nếu database có foreign key tham chiếu sản phẩm, lệnh xóa có thể bị từ chối hoặc kích hoạt hành vi constraint đã cấu hình. Fluent API không bỏ qua quy tắc toàn vẹn dữ liệu của database.

## 11. Kết hợp fluent API với reactive operators

Kết quả từ template là publisher nên có thể kết hợp với các toán tử Reactor:

```java
public Flux<ProductSummary> findActiveSummaries() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    return template.select(Product.class)
            .matching(query)
            .all()
            .map(product -> new ProductSummary(
                    product.id(),
                    product.name(),
                    product.price()
            ))
            .filter(summary -> summary.price().signum() > 0);
}
```

Ở đây, template tạo `Flux<Product>`; `map` chuyển entity sang DTO; `filter` giữ lại những phần tử thỏa điều kiện bổ sung. Nếu điều kiện có thể biểu diễn trong SQL, thường nên đưa nó vào `Criteria` để database lọc trước, giảm lượng dữ liệu truyền về ứng dụng.

Nếu cần ghép kết quả từ hai publisher độc lập, có thể dùng `Mono.zip` hoặc toán tử phù hợp. Nếu cần truy vấn thứ hai phụ thuộc vào giá trị của truy vấn đầu, dùng `flatMap`. Không dùng `block()` để lấy giá trị trung gian trong service reactive.

## 12. Fluent API và DatabaseClient: chọn mức trừu tượng phù hợp

Không phải mọi truy vấn đều nên dùng fluent entity API. Chọn công cụ theo cấu trúc dữ liệu và mục đích:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| CRUD thông thường theo ID | Reactive repository |
| Tìm entity với điều kiện động | `R2dbcEntityTemplate` + `Query`/`Criteria` |
| Insert/update/delete theo điều kiện | Fluent operations của template |
| SQL JOIN phức tạp hoặc CTE | `DatabaseClient` |
| Projection tùy chỉnh không ánh xạ trực tiếp thành entity | `DatabaseClient` hoặc truy vấn chuyên biệt |
| Kiểm soát statement và result ở mức thấp | R2DBC SPI |

Ví dụ `DatabaseClient` khi cần JOIN:

```java
public Flux<ProductSummary> findProductSummaries() {
    return databaseClient.sql("""
            SELECT p.id, p.name, p.price, c.name AS category_name
            FROM product p
            JOIN category c ON c.id = p.category_id
            WHERE p.status = :status
            ORDER BY p.name
            """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new ProductSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class),
                    row.get("category_name", String.class)
            ))
            .all();
}
```

Truy vấn JOIN này phù hợp với read model có trường từ nhiều bảng. Fluent entity API tập trung vào một entity và mapping metadata của nó; `DatabaseClient` phù hợp hơn khi cần kiểm soát rõ SQL và cấu trúc kết quả.

## 13. Tên thuộc tính, tên cột và mapping

Khi viết Criteria, Sort hoặc Update, cần dùng tên thuộc tính persistent của entity theo metadata Spring Data. Ví dụ entity có thuộc tính `createdAt` ánh xạ sang cột `created_at`; trong Query và Sort thường dùng `createdAt`, còn SQL viết tay trong `DatabaseClient` dùng tên cột database `created_at`.

Ví dụ:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(Sort.Order.desc("createdAt")));
```

Nếu dùng sai tên thuộc tính, mapping có thể không tìm được property hoặc tạo SQL không như mong đợi. Khi tên cột là từ khóa của database hoặc khác quy tắc đặt tên mặc định, dùng `@Column` để khai báo mapping rõ ràng.

## 14. Giao dịch và nhiều thao tác fluent

Nếu một use case cần nhiều thao tác ghi phải commit hoặc rollback cùng nhau, có thể đặt chúng trong reactive transaction:

```java
@Transactional
public Mono<Product> createProductAndAudit(Product product) {
    return template.insert(Product.class)
            .using(product)
            .flatMap(saved ->
                    auditTemplate.insert(ProductAudit.class)
                            .using(new ProductAudit(
                                    null,
                                    saved.id(),
                                    "CREATED"
                            ))
                            .thenReturn(saved)
            );
}
```

Ví dụ giả định hai template dùng cùng database và transaction manager reactive phù hợp. Publisher phải được trả về trong cùng pipeline để transaction manager quản lý vòng đời reactive. Không gọi `subscribe()` bên trong phương thức transactional vì việc đó tách thao tác khỏi publisher mà transaction manager đang theo dõi.

## 15. Các lỗi thường gặp khi dùng fluent API

1. **Quên tiêu thụ publisher.** Tạo biểu thức fluent chưa có nghĩa SQL đã được thực thi; cần trả publisher cho framework hoặc subscribe ở ranh giới phù hợp.
2. **Dùng tên cột thay cho tên thuộc tính trong Criteria.** Query entity dùng metadata mapping; hãy xác nhận tên property.
3. **Tạo điều kiện động bằng nối SQL.** Dùng Criteria và bind giá trị; tránh SQL injection.
4. **Cho client truyền tên sort tùy ý.** Whitelist thuộc tính được phép sắp xếp.
5. **Update hoặc delete với điều kiện quá rộng.** Kiểm tra Query trước khi thực thi thao tác ghi.
6. **Dùng `next()` như kiểm tra uniqueness.** Nó chỉ lấy phần tử đầu tiên; uniqueness cần constraint hoặc kiểm tra số lượng phù hợp.
7. **Phân trang offset rất lớn.** Cân nhắc keyset pagination khi dữ liệu lớn.
8. **Gom toàn bộ Flux thành List không giới hạn.** Đặt limit hoặc phân trang theo nhu cầu.
9. **Dùng template cho truy vấn JOIN quá phức tạp.** Cân nhắc DatabaseClient nếu SQL và projection là trọng tâm.
10. **Tự subscribe trong service.** Giữ publisher xuyên suốt để framework phối hợp lỗi, cancellation và transaction.

## Quy trình lựa chọn thao tác

- Chọn entity class bằng `select`, `insert`, `update` hoặc `delete`.
- Với truy vấn đọc, mô tả điều kiện bằng `Query` và `Criteria`.
- Thêm `Sort`, `limit` và `offset` nếu cần sắp xếp hoặc phân trang.
- Kết thúc select bằng `all()` để nhận `Flux`; dùng toán tử phù hợp nếu chỉ cần một kết quả.
- Với insert, cung cấp entity bằng `using(...)`.
- Với update, xác định hàng bằng `matching(query)` rồi mô tả thay đổi bằng `apply(update)`.
- Với delete, xác định rõ các hàng cần xóa bằng `matching(query)` rồi gọi `all()`.
- Giữ publisher reactive và dùng `DatabaseClient` khi cần SQL tùy chỉnh hoặc JOIN phức tạp.

Fluent API của Spring Data R2DBC giúp truy vấn được biểu đạt thành những bước có ý nghĩa và có thể kết hợp theo tham số đầu vào. `Query` và `Criteria` mô tả điều kiện, `Sort` và giới hạn điều khiển tập kết quả, còn các bước `select`, `insert`, `update`, `delete` thể hiện rõ thao tác trên entity. Khi chọn đúng mức trừu tượng và giữ publisher reactive xuyên suốt, mã truy cập dữ liệu dễ đọc, dễ mở rộng và vẫn tận dụng được mapping cùng cơ chế thực thi của Spring Data.
