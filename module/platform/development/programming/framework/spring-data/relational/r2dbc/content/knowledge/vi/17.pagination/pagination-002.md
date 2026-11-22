# Truy vấn theo Pageable, Sort và giới hạn của từng API

Khi một bảng có nhiều dữ liệu, ứng dụng không nên tải tất cả bản ghi về chỉ để hiển thị một trang. Spring Data R2DBC cung cấp nhiều cách điều khiển tập kết quả: sắp xếp bằng `Sort`, biểu diễn yêu cầu trang bằng `Pageable`, giới hạn số hàng bằng `limit` và bỏ qua một số hàng đầu bằng `offset`. Các API này có phạm vi hỗ trợ và ý nghĩa khác nhau.

Điểm quan trọng là phân biệt **mô tả trang** với **thao tác giới hạn truy vấn**. `Pageable` chứa số trang, kích thước trang và thứ tự sắp xếp; `Sort` chỉ mô tả thứ tự; `limit` và `offset` tác động trực tiếp lên truy vấn. Không phải mọi phương thức reactive repository đều có sẵn `findAll(Pageable)` hoặc trả về `Page<T>`. Với Spring Data R2DBC, có thể dùng `R2dbcEntityTemplate` để chuyển thông tin trang thành một `Query` có sort, limit và offset.

## 1. Vì sao cần phân trang và sắp xếp?

Giả sử bảng `product` có hàng trăm nghìn bản ghi. Nếu endpoint gọi:

~~~java
return productRepository.findAll();
~~~

ứng dụng có thể phải tiêu thụ toàn bộ kết quả. Điều này làm tăng lượng dữ liệu truyền qua mạng, thời gian xử lý, tài nguyên database và công việc ở tầng ứng dụng.

Phân trang giới hạn số hàng cần lấy cho một lần yêu cầu. Sắp xếp xác định thứ tự ổn định để người dùng có thể đi từ trang này sang trang tiếp theo.

Một trang thường có:

- **Page number:** số thứ tự trang, thường bắt đầu từ 0 trong Spring Data.
- **Page size:** số phần tử tối đa mong muốn trong một trang.
- **Sort:** một hoặc nhiều thuộc tính dùng để sắp xếp.
- **Offset:** số hàng bỏ qua trước khi lấy trang hiện tại.
- **Limit:** số hàng tối đa cần trả về.

Với phân trang offset, công thức thường dùng:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Ví dụ trang thứ 3 (page number 2) với kích thước 20 có offset bằng 40 và limit bằng 20.

## 2. Phân biệt Pageable, Sort, limit và offset

| Thành phần | Chứa thông tin gì? | Tác động |
| --- | --- | --- |
| `Pageable` | Trang, kích thước trang và Sort | Mô tả yêu cầu phân trang ở tầng ứng dụng |
| `Sort` | Thuộc tính, hướng tăng/giảm và thứ tự phụ | Xác định thứ tự kết quả |
| `limit` | Số hàng tối đa | Giới hạn số hàng database trả về |
| `offset` | Số hàng cần bỏ qua | Xác định vị trí bắt đầu của trang |

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
        2,
        20,
        Sort.by(Sort.Order.desc("createdAt"))
);
~~~

Đối tượng này mô tả trang số 2, kích thước 20, sắp xếp theo `createdAt` giảm dần. Bản thân việc tạo `Pageable` không chạy truy vấn. Tầng truy cập dữ liệu cần sử dụng các thông tin trong đó để xây dựng SQL hoặc Query.

## 3. Sort trong reactive repository

`Sort` mô tả thứ tự của kết quả. Nó có thể sắp xếp theo một thuộc tính:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "name");
~~~

Hoặc nhiều thuộc tính:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
~~~

Trong reactive repository, `ReactiveSortingRepository` cung cấp phương thức `findAll(Sort sort)`:

~~~java
public interface ProductRepository
        extends ReactiveSortingRepository<Product, Long> {
}

Flux<Product> products =
        productRepository.findAll(
                Sort.by(Sort.Order.asc("name"))
        );
~~~

Phương thức này sắp xếp kết quả nhưng không tự giới hạn số hàng. Nếu bảng có 500.000 sản phẩm, `findAll(sort)` vẫn có thể phát tất cả 500.000 sản phẩm theo thứ tự yêu cầu.

Một số repository query method cũng có thể hỗ trợ sắp xếp động bằng tham số `Sort`, tùy loại query và phiên bản Spring Data. Có thể dùng `OrderBy` trong tên phương thức nếu thứ tự cố định:

~~~java
Flux<Product> findByStatusOrderByCreatedAtDesc(String status);
~~~

Hãy phân biệt sắp xếp với phân trang: Sort không phải Pageable và không đặt giới hạn kết quả.

## 4. Giới hạn của Pageable trong reactive repository

`ReactiveCrudRepository` không cung cấp phương thức CRUD chuẩn `findAll(Pageable)` tương tự một số repository đồng bộ kế thừa `PagingAndSortingRepository`. `ReactiveSortingRepository` cung cấp `findAll(Sort)`, nhưng phương thức đó chỉ sắp xếp.

Một `Page<T>` thường chứa danh sách nội dung cùng tổng số phần tử và tổng số trang. Để tạo metadata đó, hệ thống thường phải thực hiện thêm truy vấn đếm. Với reactive repository, không nên giả định mọi query method đều có thể trả `Page<T>` hoặc rằng chỉ cần thêm tham số `Pageable` là Spring Data tự thực hiện cả truy vấn dữ liệu lẫn count.

Khả năng nhận `Pageable` như tham số trong query method và các kiểu trả về hỗ trợ có thể phụ thuộc phiên bản Spring Data, loại repository và cách khai báo query. Hãy kiểm tra API/tài liệu của đúng phiên bản đang dùng trước khi dựa vào nó. Cách triển khai tường minh và dễ kiểm soát trong Spring Data R2DBC là:

1. Nhận `Pageable` ở service hoặc controller.
2. Chuyển `pageSize`, `offset` và `sort` thành `Query` hoặc SQL.
3. Trả nội dung trang dưới dạng `Flux<T>` hoặc thu thập một trang có giới hạn.
4. Nếu cần tổng số phần tử, chạy thêm truy vấn `count` trả `Mono<Long>`.

Không nhầm `Pageable` là cơ chế tự động phân trang ở mọi API. Nó là đối tượng mô tả yêu cầu; API truy cập dữ liệu phải thực sự áp dụng giới hạn và thứ tự đó.

## 5. Dùng R2dbcEntityTemplate với Query, Sort, limit và offset

`R2dbcEntityTemplate` cho phép mô tả điều kiện, sắp xếp và phân trang bằng `Query`:

~~~java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        ))
        .limit(20)
        .offset(40);

Flux<Product> products = template.select(Product.class)
        .matching(query)
        .all();
~~~

Trong ví dụ:

- `Criteria` chỉ chọn sản phẩm có trạng thái ACTIVE.
- `sort(...)` sắp xếp theo ngày tạo giảm dần, sau đó theo ID tăng dần.
- `limit(20)` yêu cầu tối đa 20 hàng.
- `offset(40)` bỏ qua 40 hàng đầu tiên.
- `all()` phát các entity phù hợp dưới dạng `Flux<Product>`.

Đây là cách áp dụng trực tiếp các thông tin phân trang vào truy vấn R2DBC. Database chỉ cần trả về phần kết quả của trang, thay vì toàn bộ bảng.

## 6. Chuyển Pageable thành Query

Có thể nhận `Pageable` từ tầng gọi và chuyển các trường của nó thành Query:

~~~java
public Flux<Product> findActiveProducts(Pageable pageable) {
    Criteria criteria = Criteria.where("status").is("ACTIVE");

    Query query = Query.query(criteria)
            .sort(pageable.getSort())
            .limit(pageable.getPageSize())
            .offset(pageable.getOffset());

    return template.select(Product.class)
            .matching(query)
            .all();
}
~~~

Service này giữ logic lọc theo trạng thái và áp dụng trang do caller yêu cầu. `Pageable.getOffset()` trả về vị trí bắt đầu của trang; `getPageSize()` là giới hạn số hàng; `getSort()` là thứ tự.

Nếu ứng dụng muốn cho phép client không truyền sort, có thể áp dụng thứ tự mặc định:

~~~java
Sort effectiveSort = pageable.getSort().isSorted()
        ? pageable.getSort()
        : Sort.by(Sort.Order.desc("createdAt"));
~~~

Nên thêm một thuộc tính duy nhất làm tiêu chí phụ để thứ tự không thay đổi tùy ý khi nhiều hàng có cùng giá trị sort. Ví dụ `createdAt DESC, id ASC`.

## 7. Kiểm tra giới hạn trang ở tầng API

Không nên tin trực tiếp kích thước trang do client gửi. Một request có thể yêu cầu hàng triệu hàng và gây áp lực lên database hoặc bộ nhớ.

Ví dụ giới hạn page size:

~~~java
private Pageable normalize(Pageable requested) {
    int maxPageSize = 100;
    int pageSize = Math.min(requested.getPageSize(), maxPageSize);

    Sort sort = requested.getSort().isSorted()
            ? requested.getSort()
            : Sort.by(Sort.Order.desc("createdAt"));

    return PageRequest.of(
            requested.getPageNumber(),
            pageSize,
            sort
    );
}
~~~

Trong thực tế, cần xác nhận page number không âm, page size dương và offset không vượt giới hạn phù hợp của hệ thống. `PageRequest.of(...)` cũng kiểm tra một số giá trị không hợp lệ và có thể ném `IllegalArgumentException`.

Giới hạn 100 chỉ là ví dụ. Giá trị tối đa nên dựa trên payload, độ rộng entity, latency và khả năng database.

## 8. Sort động và an toàn truy vấn

Sort thường được xây dựng từ thuộc tính entity. Nếu client gửi `sort=name,asc`, ứng dụng có thể chuyển nó thành `Sort`. Tuy nhiên, không nên cho client truyền tùy ý tên cột hoặc biểu thức SQL.

Hãy whitelist trường được phép sắp xếp:

~~~java
private static final Set<String> ALLOWED_SORTS =
        Set.of("name", "price", "createdAt");

private Sort safeSort(String property, Sort.Direction direction) {
    if (!ALLOWED_SORTS.contains(property)) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    return Sort.by(new Sort.Order(direction, property));
}
~~~

Các giá trị dữ liệu trong điều kiện truy vấn cần được bind. Tên thuộc tính sort là một phần cấu trúc truy vấn nên phải được kiểm soát bằng whitelist. Không nối trực tiếp chuỗi sort của client vào SQL.

Khi dùng `DatabaseClient` với SQL tự viết, tham số bind thường không thể thay thế tên cột hoặc từ khóa `ASC`/`DESC`. Hãy ánh xạ lựa chọn sort đã được kiểm tra thành một trong các biểu thức SQL cố định.

## 9. Tạo Page response với nội dung và tổng số phần tử

Nếu API cần tổng số bản ghi phù hợp bộ lọc, cần chạy hai truy vấn:

1. Truy vấn lấy nội dung của trang.
2. Truy vấn đếm tổng số hàng thỏa điều kiện, không có limit và offset.

Có thể định nghĩa response riêng:

~~~java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages
) {}
~~~

Ví dụ service:

~~~java
public Mono<PageResult<Product>> findProductPage(
        Pageable pageable) {

    Criteria criteria = Criteria.where("status").is("ACTIVE");
    Query pageQuery = Query.query(criteria)
            .sort(pageable.getSort())
            .limit(pageable.getPageSize())
            .offset(pageable.getOffset());
    Query countQuery = Query.query(criteria);

    Mono<List<Product>> content = template
            .select(Product.class)
            .matching(pageQuery)
            .all()
            .collectList();

    return content.flatMap(items ->
            template.count(countQuery, Product.class)
                    .map(total -> new PageResult<>(
                            items,
                            pageable.getPageNumber(),
                            pageable.getPageSize(),
                            total,
                            total == 0 ? 0 :
                                    (total + pageable.getPageSize() - 1)
                                            / pageable.getPageSize()
                    ))
    );
}
~~~

Ở đây, nội dung trang được thu thập thành một List có giới hạn bởi page size. Truy vấn count dùng cùng điều kiện lọc nhưng không mang sort, limit hoặc offset. Việc tính totalPages dùng phép chia làm tròn lên.

Không nên gọi `collectList()` trên một truy vấn không có giới hạn. Trong ví dụ, nó chỉ thu thập tối đa một trang đã bị giới hạn bởi Query.

Hai truy vấn dữ liệu và count có thể nhìn thấy trạng thái khác nhau nếu dữ liệu thay đổi giữa hai lần thực thi. Nếu nghiệp vụ cần snapshot nhất quán, hãy cân nhắc transaction và isolation level phù hợp với database. Một transaction không tự động bảo đảm snapshot giống nhau ở mọi mức isolation.

## 10. Page, Slice và Flux khác nhau thế nào?

| Kiểu | Nội dung | Tổng số phần tử? | Cách dùng |
| --- | --- | --- | --- |
| `Flux<T>` | Phát các phần tử theo luồng | Không | Truy vấn nhiều kết quả, có thể không giới hạn nếu query không giới hạn |
| `Mono<List<T>>` | Một danh sách hoàn chỉnh | Không tự có tổng số | Thu thập một tập đã được giới hạn |
| `Page<T>` | Nội dung trang và metadata tổng | Có | Thường cần count query bổ sung |
| `Slice<T>` | Nội dung trang và thông tin còn trang tiếp theo | Không cần tổng toàn bộ | Có thể kiểm tra thêm một phần tử để xác định hasNext |
| `Pageable` | Mô tả yêu cầu trang | Không | Dùng làm input để tạo query |

Với reactive R2DBC, cách trả về phổ biến là `Flux<T>` cho dữ liệu và một `Mono<Long>` riêng cho count khi cần. Có thể kết hợp hai kết quả thành một DTO trang ở tầng service.

Nếu không cần tổng số phần tử, có thể tránh count query bằng cách lấy nhiều hơn page size một hàng:

~~~java
public record PageSlice<T>(
        List<T> content,
        int page,
        int size,
        boolean hasNext
) {}
~~~

~~~java
public Mono<PageSlice<Product>> findProductSlice(Pageable pageable) {
    int size = pageable.getPageSize();

    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    )
            .sort(pageable.getSort())
            .limit(size + 1L)
            .offset(pageable.getOffset());

    return template.select(Product.class)
            .matching(query)
            .all()
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > size;
                List<Product> content = hasNext
                        ? rows.subList(0, size)
                        : rows;

                return new PageSlice<>(
                        content,
                        pageable.getPageNumber(),
                        size,
                        hasNext
                );
            });
}
~~~

Truy vấn lấy tối đa `size + 1` hàng. Nếu có hàng thừa, trang hiện tại có trang tiếp theo. Cách này tránh count toàn bộ bảng nhưng chỉ cung cấp `hasNext`, không cung cấp tổng số trang.

## 11. Phân trang với DatabaseClient

Khi cần SQL cụ thể, có thể áp dụng limit và offset trong câu lệnh:

~~~java
public Flux<ProductSummary> findPage(
        int page,
        int size,
        String status) {

    long offset = (long) page * size;

    return databaseClient.sql("""
            SELECT id, name, price
            FROM product
            WHERE status = :status
            ORDER BY created_at DESC, id ASC
            LIMIT :limit OFFSET :offset
            """)
            .bind("status", status)
            .bind("limit", size)
            .bind("offset", offset)
            .map((row, metadata) -> new ProductSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class)
            ))
            .all();
}
~~~

Ví dụ dùng cú pháp LIMIT/OFFSET phổ biến ở PostgreSQL và một số database khác. Cú pháp phân trang có thể khác theo hệ quản trị; với SQL tự viết, ứng dụng chịu trách nhiệm dùng dialect đúng. Nếu muốn Spring Data xử lý mapping và dialect, cân nhắc `R2dbcEntityTemplate`.

## 12. Giới hạn của từng API

Không phải API nào cũng cung cấp đủ cả sort, page và count:

| API | Sort | Limit/offset | Count metadata |
| --- | --- | --- | --- |
| `ReactiveCrudRepository.findAll()` | Không có tham số sort | Không có tham số page chuẩn | Không |
| `ReactiveSortingRepository.findAll(Sort)` | Có | Không tự cung cấp page size/offset | Không |
| Derived query với `Top/First` | Có thể kết hợp thứ tự cố định trong tên method hoặc Sort tùy hỗ trợ | Giới hạn cố định theo tên method | Không |
| `R2dbcEntityTemplate` + `Query` | Có `Sort` | Có `limit` và `offset` | Có thể gọi count riêng |
| `DatabaseClient` | Viết trong SQL | Viết trong SQL theo dialect | Cần query count riêng |
| R2DBC SPI | Điều khiển ở mức statement/query | Tự triển khai SQL/driver-specific | Tự xử lý result |

### ReactiveCrudRepository

`findAll()` lấy tất cả kết quả; không nhận `Pageable` hoặc `Sort` như một tham số của phương thức chuẩn.

### ReactiveSortingRepository

`findAll(Sort)` sắp xếp kết quả nhưng không giới hạn số lượng. Nó không tương đương `findAll(Pageable)`.

### Derived query Top và First

Nếu giới hạn là cố định, tên phương thức có thể thể hiện ý định:

~~~java
Flux<Product> findTop10ByStatusOrderByCreatedAtDesc(String status);

Mono<Product> findFirstByStatusOrderByPriceAsc(String status);
~~~

Đây là giới hạn cố định trong định nghĩa query, không phải phân trang động tùy theo số trang của người dùng.

### R2dbcEntityTemplate

Template cung cấp khả năng ghép điều kiện, Sort, limit và offset trong Query. Đây là lựa chọn thuận tiện khi cần phân trang động theo tham số.

### DatabaseClient

DatabaseClient cho phép kiểm soát SQL đầy đủ. Đổi lại, ứng dụng cần tự quản lý dialect, tên cột, bind, projection và count query.

## 13. Offset pagination và chi phí ở trang sâu

Offset pagination dễ hiểu:

~~~sql
SELECT id, name
FROM product
ORDER BY id
LIMIT 20 OFFSET 10000;
~~~

Database cần xác định và bỏ qua 10.000 hàng trước khi trả 20 hàng tiếp theo. Với offset rất lớn, chi phí có thể tăng đáng kể tùy execution plan và index. Một số database vẫn phải duyệt nhiều hàng bị bỏ qua.

Offset pagination cũng có thể gây trùng hoặc bỏ sót dữ liệu khi bảng thay đổi giữa các request:

1. Người dùng lấy trang 0.
2. Một hàng mới được chèn ở đầu thứ tự.
3. Người dùng lấy trang 1 với offset cũ.
4. Một hàng có thể xuất hiện lại hoặc bị bỏ qua vì vị trí các hàng đã dịch chuyển.

Nếu dữ liệu ít thay đổi và số trang không quá sâu, offset vẫn đơn giản và phù hợp. Với bảng lớn hoặc luồng dữ liệu liên tục thay đổi, cân nhắc keyset pagination.

## 14. Keyset pagination (seek pagination)

Keyset pagination dùng giá trị của hàng cuối trang trước làm cursor cho trang tiếp theo. Thay vì bỏ qua N hàng, truy vấn yêu cầu các hàng đứng sau cursor theo thứ tự đã chọn.

Ví dụ sắp xếp `created_at DESC, id ASC`. Cursor cuối trang trước gồm `lastCreatedAt` và `lastId`. Điều kiện trang tiếp theo:

~~~sql
SELECT id, name, created_at
FROM product
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at DESC, id ASC
LIMIT :limit;
~~~

ID là tiêu chí phụ duy nhất giúp thứ tự xác định khi nhiều hàng có cùng created_at. Cần bảo đảm điều kiện cursor phản ánh đúng hướng sort của từng thuộc tính.

Keyset thường phù hợp với nút “Load more” hoặc duyệt tuần tự dữ liệu lớn. Nó không thuận tiện để nhảy thẳng đến trang số 500 vì không có offset. API thường trả cursor tiếp theo thay vì page number.

Một cursor nên chứa đủ giá trị sort của hàng cuối và có thể được mã hóa/kiểm tra để client không tự sửa điều kiện. Khi cursor là dữ liệu client gửi lại, cần xác thực và bind như các tham số khác.

## 15. Index và thứ tự sắp xếp

Sort và filter có thể khiến database phải sắp xếp nhiều hàng nếu không có index phù hợp. Ví dụ:

~~~sql
SELECT id, name, created_at
FROM product
WHERE status = 'ACTIVE'
ORDER BY created_at DESC, id ASC
LIMIT 20;
~~~

Có thể xem xét index ghép:

~~~sql
CREATE INDEX idx_product_status_created_id
    ON product(status, created_at DESC, id ASC);
~~~

Index phù hợp có thể hỗ trợ lọc và thứ tự, nhưng thiết kế thực tế phụ thuộc database, cardinality, selectivity và các truy vấn khác. Mỗi index làm tăng chi phí ghi và dung lượng lưu trữ. Hãy dùng EXPLAIN/EXPLAIN ANALYZE trên database mục tiêu để xác nhận.

Nếu sort theo nhiều cột, thứ tự các cột trong index có ý nghĩa. Một index bắt đầu bằng created_at có thể không tối ưu cho truy vấn lọc status rồi sắp xếp created_at.

## 16. Thứ tự ổn định và giá trị null

Không nên phân trang theo một cột có thể trùng mà không thêm khóa phụ duy nhất. Ví dụ:

~~~sql
ORDER BY created_at DESC
~~~

Nếu nhiều hàng có cùng created_at, database có thể trả chúng theo thứ tự khác nhau giữa các lần chạy. Nên dùng:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Khi sort theo cột nullable, vị trí của NULL có thể khác theo database hoặc cú pháp. Nếu thứ tự NULL quan trọng, hãy chỉ định quy tắc rõ ràng theo dialect, chẳng hạn NULLS FIRST/LAST nếu database hỗ trợ. Khi dùng Query/Sort, hãy kiểm tra SQL được sinh và hành vi thực tế của driver/database.

## 17. Phân trang trong controller WebFlux

Controller có thể nhận page và size từ query parameter, tạo Pageable rồi gọi service:

~~~java
@GetMapping("/products")
public Flux<Product> findProducts(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    Pageable pageable = PageRequest.of(
            page,
            Math.min(size, 100),
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.asc("id")
            )
    );

    return productService.findProducts(pageable);
}
~~~

Ví dụ trả trực tiếp Flux nên response chứa các phần tử của trang nhưng không có tổng số trang. Nếu cần metadata, service có thể trả `Mono<PageResult<Product>>` hoặc `Mono<PageSlice<Product>>` như các ví dụ trước.

Trong ứng dụng thực tế, nên kiểm tra page và size trước khi gọi `PageRequest.of`, xử lý tham số âm/không hợp lệ và whitelist sort field nếu cho client chọn sort.

## 18. Không dùng Flux.take() thay cho giới hạn SQL

Có thể viết:

~~~java
return productRepository.findAll()
        .take(20);
~~~

Kết quả phía subscriber chỉ nhận tối đa 20 phần tử, nhưng `take(20)` là toán tử Reactor ở tầng ứng dụng. Nó không phải cách diễn đạt rõ ràng để database thực thi LIMIT 20. Tùy driver và cách hủy subscription, database/driver có thể đã đọc hoặc buffer thêm dữ liệu trước khi cancellation được xử lý.

Khi mục tiêu là giới hạn số hàng được truy vấn, hãy đặt limit ở Query hoặc SQL:

~~~java
Query query = Query.empty()
        .sort(Sort.by("id"))
        .limit(20);

return template.select(Product.class)
        .matching(query)
        .all();
~~~

`take` vẫn hữu ích để giới hạn một luồng ở tầng ứng dụng, nhưng không thay thế limit phía database khi tối ưu truy vấn.

## 19. Kiểm thử sort và pagination

Integration test nên kiểm tra:

1. Kết quả có đúng số phần tử tối đa của page size.
2. Offset chọn đúng đoạn dữ liệu.
3. Thứ tự tăng/giảm được áp dụng đúng.
4. Thứ tự phụ duy nhất giúp các hàng có giá trị sort trùng vẫn ổn định.
5. Bộ lọc được giữ nguyên giữa truy vấn content và count.
6. Trang cuối có ít phần tử hơn page size hoặc rỗng khi vượt phạm vi.
7. Page size bị giới hạn ở tầng API.
8. Keyset cursor không lặp hoặc bỏ sót hàng trong tập dữ liệu ổn định.
9. Dữ liệu thay đổi giữa các request có hành vi đúng với yêu cầu nhất quán.

Ví dụ kiểm thử:

~~~java
StepVerifier.create(productService.findProducts(
                PageRequest.of(0, 2,
                        Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id")))
        ))
        .expectNextMatches(product -> product.name().equals("Alpha"))
        .expectNextMatches(product -> product.name().equals("Beta"))
        .verifyComplete();
~~~

Test cần chuẩn bị dữ liệu có thứ tự xác định, bao gồm trường hợp trùng giá trị sort. Chạy trên database mục tiêu để xác nhận dialect, null ordering, index và mapping.

## 20. Các nhầm lẫn thường gặp

1. **Nghĩ Pageable tự động phân trang mọi reactive repository.** Phải xác nhận API hỗ trợ và áp dụng limit/offset thật sự.
2. **Nghĩ Sort giới hạn số hàng.** Sort chỉ sắp xếp; không có page size.
3. **Nghĩ findAll(Sort) chỉ trả một trang.** Phương thức có thể phát toàn bộ kết quả đã sắp xếp.
4. **Nghĩ Page và Flux giống nhau.** Page cần metadata tổng; Flux chỉ phát dữ liệu theo luồng.
5. **Dùng collectList() trên truy vấn không giới hạn.** Có thể tải toàn bộ bảng vào bộ nhớ.
6. **Dùng take() thay cho LIMIT.** take giới hạn tiêu thụ ở Reactor, không thay thế giới hạn truy vấn database.
7. **Sort theo cột không duy nhất.** Các trang có thể trùng hoặc thiếu hàng do thứ tự không ổn định.
8. **Cho client truyền tên cột tùy ý.** Whitelist sort field để tránh cấu trúc SQL không an toàn.
9. **Offset rất lớn.** Chi phí bỏ qua hàng có thể tăng; cân nhắc keyset pagination.
10. **Đếm tổng trong mọi request.** Count query có thể tốn chi phí; chỉ chạy khi UI thực sự cần tổng số trang.
11. **Content query và count query dùng filter khác nhau.** Metadata trang sẽ không khớp nội dung.
12. **Không giới hạn page size.** Client có thể yêu cầu tập kết quả quá lớn.

## Quy tắc lựa chọn nhanh

- Dùng `Sort` khi chỉ cần sắp xếp kết quả.
- Dùng `ReactiveSortingRepository.findAll(Sort)` nếu cần lấy tất cả entity theo thứ tự.
- Dùng `Top/First` cho giới hạn cố định được xác định trong query method.
- Dùng `R2dbcEntityTemplate` với `Query.sort(...).limit(...).offset(...)` cho phân trang động.
- Dùng `Pageable` như đối tượng mô tả yêu cầu trang, rồi chuyển các trường của nó thành Query nếu repository API không hỗ trợ trực tiếp.
- Dùng `Mono<Long>` count riêng và ghép với nội dung khi cần tổng số phần tử.
- Dùng `size + 1` để xác định `hasNext` khi không cần count toàn bộ.
- Dùng `DatabaseClient` khi cần SQL/dialect tùy chỉnh và tự quản lý count query.
- Dùng keyset pagination cho tập dữ liệu lớn hoặc thay đổi thường xuyên.
- Luôn giới hạn page size, whitelist sort field và thêm thứ tự phụ duy nhất.

`Pageable`, `Sort`, `limit` và `offset` giải quyết những phần khác nhau của việc phân trang. Sort xác định thứ tự; limit và offset giới hạn phần dữ liệu database trả về; Pageable đóng gói các thông tin trang để tầng ứng dụng truyền xuống. Với Spring Data R2DBC, cần chú ý giới hạn của từng repository API và không giả định có sẵn `findAll(Pageable)` hay `Page<T>` cho mọi query reactive. Dùng Query của R2dbcEntityTemplate hoặc SQL qua DatabaseClient giúp kiểm soát rõ giới hạn, count và thứ tự, đồng thời giữ dữ liệu ở dạng reactive.
