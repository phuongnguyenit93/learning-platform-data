# Page, Slice và chi phí truy vấn đếm tổng

Trong **Spring Data Couchbase**, một API danh sách có thể trả 20 khách hàng, nhưng để hiển thị nhãn “Trang 1/12.435” hệ thống còn cần biết **tổng số khách hàng khớp điều kiện lọc**. Truy vấn lấy 20 hàng và truy vấn đếm tất cả hàng khớp điều kiện là hai bài toán khác nhau. Trên tập dữ liệu lớn, chính việc tính tổng có thể tạo thêm độ trễ và chi phí đáng kể.

Spring Data cung cấp hai kiểu kết quả phân trang phổ biến:

- **`Page<T>`**: trả nội dung trang và metadata về **tổng số phần tử, tổng số trang**.
- **`Slice<T>`**: trả nội dung trang và thông tin **có trang tiếp theo hay không**; không cần tổng số toàn bộ tập kết quả.

Bài học thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Ta sẽ kết hợp Spring Data repository, document mapping, SQL++, `CouchbaseTemplate`/SDK, secondary index và API reactive để hiểu khi nào chọn `Page`, `Slice` hoặc truy vấn giới hạn tự quản. Mục tiêu là bảo đảm **đúng dữ liệu, đúng hợp đồng API và chi phí vận hành có thể dự đoán**, thay vì mặc nhiên yêu cầu `COUNT(*)` cho mọi lần tải danh sách.

Sau bài này, bạn có thể:

1. Giải thích metadata của `Page`, `Slice`, `List` và `Pageable`.
2. Viết repository method phân trang cho Spring Data Couchbase.
3. Phân tích vì sao `Page` có thể cần truy vấn `COUNT`, còn `Slice` thường dùng kỹ thuật `pageSize + 1`.
4. Viết SQL++ dữ liệu và SQL++ đếm có cùng điều kiện lọc.
5. Phân biệt chi phí `COUNT` với chi phí `LIMIT/OFFSET`, đọc kế hoạch `EXPLAIN` và đánh giá covering index.
6. Quyết định khi nào cần tổng chính xác, tổng trì hoãn, tổng ước lượng hoặc không cần tổng.
7. Xử lý sắp xếp ổn định, keyset pagination, truy vấn sau ghi và thay đổi đồng thời.

## 1. Bài toán: một API, hai truy vấn tiềm ẩn

Giả sử hệ thống lưu document khách hàng trong bucket `shop`, scope `crm`, collection `customers`. Mỗi document có một ID riêng và body:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "tier": "GOLD",
  "address": {
    "city": "Đà Nẵng"
  }
}
~~~

Màn hình quản trị có ba yêu cầu thường gặp:

| Nhu cầu giao diện | Thông tin cần biết | Hợp đồng phù hợp |
| --- | --- | --- |
| Hiển thị “20 khách hàng”, nút “Tải thêm” | Danh sách và có hàng tiếp theo không | `Slice` |
| Hiển thị “Trang 3/257”, số bản ghi kết quả | Danh sách và tổng chính xác | `Page` |
| Export hoặc xử lý từng lô có cursor riêng | Lô hiện tại, vị trí tiếp theo | Keyset/cursor hoặc streaming phù hợp |
| Widget “Có bao nhiêu khách hàng đang hoạt động?” | Chỉ tổng số | Truy vấn `COUNT` riêng |

Với dữ liệu lớn, truy vấn lấy trang có thể nhanh nếu dùng index theo điều kiện lọc và sắp xếp. Tuy nhiên truy vấn đếm có thể phải xét rất nhiều index entries hoặc document trước khi có kết quả, tùy index và kế hoạch thực thi.

Ví dụ dữ liệu 2.000.000 khách hàng, 700.000 đang hoạt động: giao diện hiển thị 20 hàng nhưng có thể cần tính đúng tổng `700000`. Không thể suy ra chi phí đếm từ kích thước trang 20, và cũng không nên khẳng định mỗi `COUNT` đều quét toàn bộ document; Query Engine có thể dùng index/count optimization thích hợp.

## 2. `Pageable` là yêu cầu, `Page` và `Slice` là kết quả

`Pageable` chứa thông tin **trang muốn đọc**: số trang, kích thước trang, thứ tự sắp xếp. Trong Spring Data, trang đầu là **trang số 0**.

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("fullName"),
            Sort.Order.asc("id"))
);
~~~

Cần phân biệt:

- `request.getPageNumber()`: số trang zero-based, ví dụ `0`.
- `request.getPageSize()`: số lượng phần tử yêu cầu, ví dụ `20`.
- `request.getOffset()`: số phần tử đứng trước trang, với trang thứ ba (`pageNumber = 2`) là `40`.
- `request.getSort()`: quy tắc sắp xếp cần được ánh xạ đúng sang đường truy vấn tương ứng.

Khi tạo `Pageable` cho entity có `@Field` đổi tên thuộc tính hoặc `@Id` ánh xạ document key, cần kiểm tra SQL++ sinh ra. Trong SQL++ viết tay, thứ tự phụ theo ID được biểu diễn chắc chắn hơn bằng `META(c).id` thay vì giả định field `c.id` tồn tại trong JSON.

### Metadata của `Page`

~~~java
Page<Customer> page = repository.findByActiveTrue(request);

List<Customer> content = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();

boolean hasNext = page.hasNext();
Pageable next = page.nextPageable();
~~~

`Page` triển khai các thông tin của `Slice` và bổ sung tổng:

- `getContent()`: phần tử trong trang hiện tại.
- `getNumber()`, `getSize()`, `getNumberOfElements()`: metadata của trang.
- `getTotalElements()`: tổng phần tử khớp điều kiện trên toàn tập theo kết quả đếm.
- `getTotalPages()`: số trang suy ra từ tổng và kích thước trang.
- `hasNext()`: còn trang sau hay không theo metadata có sẵn.

### Metadata của `Slice`

~~~java
Slice<Customer> slice = repository.findByActive(true, request);

List<Customer> content = slice.getContent();
boolean hasNext = slice.hasNext();
Pageable next = slice.nextPageable();
~~~

`Slice` vẫn có `getNumber()`, `getSize()`, `getContent()` và `hasNext()`, nhưng **không có `getTotalElements()` hoặc `getTotalPages()`**. Đây là khác biệt về **hợp đồng dữ liệu**, không chỉ cách đặt tên.

## 3. Ví dụ Spring Data Couchbase repository

Giả sử entity được ánh xạ sang collection của Couchbase:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;
    private boolean active;

    // Constructor/getter/setter theo mapping dự án.
}
~~~

Một repository có thể khai báo **ba phương thức có hợp đồng trả về khác nhau**:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    // Dành cho UI cần tổng số phần tử và tổng số trang.
    Page<Customer> findByActiveTrue(Pageable pageable);

    // Dành cho UI chỉ cần biết có trang kế tiếp không.
    Slice<Customer> findByActive(boolean active, Pageable pageable);

    // Chỉ cần nội dung của phạm vi được yêu cầu.
    List<Customer> findByActiveFalse(Pageable pageable);
}
~~~

Các phương thức trên sử dụng query derivation của Spring Data Couchbase. Với `Page` và `Slice`, Spring Data tạo giới hạn phạm vi từ `Pageable` khi cơ chế repository và query path của phiên bản đó hỗ trợ.

**Lưu ý Java:** không thể khai báo hai phương thức chỉ khác kiểu trả về nhưng cùng tên và cùng tham số; ví dụ `Page<Customer> findByActiveTrue(Pageable)` và `Slice<Customer> findByActiveTrue(Pageable)` trong cùng interface là chữ ký trùng nhau. Các tên trong ví dụ được chọn khác nhau để hợp lệ.

### Gọi từ service

~~~java
Pageable pageable = PageRequest.of(
    0, 20, Sort.by("fullName").ascending()
);

Page<Customer> page =
        repository.findByActiveTrue(pageable);

Slice<Customer> slice =
        repository.findByActive(true, pageable);

List<Customer> list =
        repository.findByActiveFalse(pageable);
~~~

Ở production, nên có thứ tự ổn định và thêm khóa phụ duy nhất khi cần (chẳng hạn document key). Đường `Sort.by("id")` phải được kiểm tra cách ánh xạ ở Spring Data Couchbase; nếu cần kiểm soát hoàn toàn, dùng SQL++ `ORDER BY c.fullName, META(c).id` tường minh.

### Có thể dùng `PagingAndSortingRepository` không?

Spring Data Couchbase hỗ trợ pagination theo N1QL/SQL++ và các repository có phương thức `findAll(Pageable)` phù hợp. Tuy nhiên quan hệ kế thừa của các repository interface thay đổi theo các đời Spring Data; ở các bản mới, `PagingAndSortingRepository` là một fragment có thể kết hợp với CRUD repository. Hãy kiểm tra interface thực sự được dùng trong dependency của dự án thay vì suy luận rằng mọi `CrudRepository` đều đã có `findAll(Pageable)`.

## 4. `Page` có thể phát sinh thêm `COUNT`

Để tạo `Page`, Spring Data cần xác định tổng số phần tử khớp điều kiện, nếu không thể suy ra từ kết quả hiện có.

Ví dụ ý tưởng của hai truy vấn tương ứng:

~~~sql
-- Lấy 20 khách hàng đang hoạt động cho trang đầu.
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20 OFFSET 0;
~~~

~~~sql
-- Đếm tất cả khách hàng khớp cùng bộ lọc.
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Truy vấn dữ liệu có `LIMIT`/`OFFSET`; truy vấn đếm **không được mang LIMIT/OFFSET của trang** nếu mục tiêu là tổng của cả tập đã lọc. Điều kiện lọc phải tương đương, bao gồm các ràng buộc loại entity, scope/collection, tenant, trạng thái và quyền xem dữ liệu.

Không nên phát biểu “`Page` luôn chạy đúng hai truy vấn” như một quy luật tuyệt đối:

- Spring Data thường cần truy vấn `COUNT` để có tổng.
- Một số trường hợp có thể **suy ra tổng** từ lượng kết quả thực tế (chẳng hạn trang đầu có ít phần tử hơn page size) và bỏ truy vấn đếm; cơ chế chính xác phụ thuộc đường repository/phiên bản.
- `Page` được dựng bởi ứng dụng có thể dùng tổng đã được cung cấp từ nguồn khác.
- Một truy vấn tùy biến, grouping, join hoặc aggregation có thể có cách đếm riêng hoặc không áp dụng được đếm suy ra mặc định.

Điều cần kiểm chứng là **số câu SQL++ thực sự gửi đến Couchbase** và thời gian riêng của data query/count query, không chỉ kiểu Java được khai báo.

## 5. `Slice` thường dùng kỹ thuật `pageSize + 1`

`Slice` chỉ cần biết có phần tử tiếp theo không. Với `pageSize = 20`, phương pháp phổ biến là hỏi tối đa **21 hàng**:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 21 OFFSET 0;
~~~

Ý tưởng:

1. Query nhận tối đa 21 row.
2. Nếu nhận **21 row**, trả 20 row đầu và đặt `hasNext = true`.
3. Nếu nhận **từ 0 đến 20 row**, trả toàn bộ và đặt `hasNext = false`.
4. Không thực hiện `COUNT(1)` chỉ để tìm tổng.

Ví dụ với page size 3:

| Số hàng query trả (giới hạn 4) | Số hàng đưa vào `Slice` | `hasNext` |
| ---: | ---: | --- |
| 0 | 0 | false |
| 1 | 1 | false |
| 3 | 3 | false |
| 4 | 3 | true |

`Slice` được Spring Data Commons mô tả theo cơ chế look-ahead này. Việc tối ưu do module cụ thể phát sinh ra sao cần quan sát SQL++ ở bản Spring Data Couchbase đang dùng.

**Một yêu cầu quan trọng:** Nếu query có `LIMIT 20` đúng bằng page size rồi suy `hasNext = false` từ việc nhận đủ 20 row, kết luận sẽ sai. Muốn biết còn trang tiếp theo, phải có hàng dư, câu query tồn tại trang kế tiếp, hoặc một cơ chế cursor đáng tin cậy.

### `Slice` không đồng nghĩa với truy vấn rẻ mọi lúc

`Slice` tránh nhu cầu `COUNT` cho metadata tổng, nhưng vẫn chịu chi phí:

- Lọc/sắp xếp để tìm các row phù hợp.
- `OFFSET` khi người dùng chuyển đến trang xa.
- Network và ánh xạ dữ liệu của trang, dù chỉ hơn một hàng.
- Index scan consistency hoặc sort khi query plan chưa phù hợp.

Nếu người dùng nhảy đến trang 100.000, `Slice` dùng offset vẫn có thể chậm. Bỏ COUNT chỉ giải quyết **một** phần của chi phí phân trang.

## 6. `List<T>` với `Pageable` khác gì `Slice<T>`?

Nếu mục tiêu chỉ là lấy một danh sách giới hạn, repository có thể trả `List<T>` cùng tham số `Pageable`:

~~~java
List<Customer> findByActiveFalse(Pageable pageable);
~~~

Đường trả `List` thường chỉ áp dụng giới hạn/sắp xếp/phạm vi mà không sinh metadata tổng của `Page`; cũng không tự cung cấp `hasNext` của `Slice`.

So sánh:

| Tiêu chí | `Page<T>` | `Slice<T>` | `List<T>` + `Pageable` |
| --- | --- | --- | --- |
| Nội dung trang | Có | Có | Có |
| Biết trang hiện tại | Có | Có | Caller giữ `Pageable` |
| Có `hasNext()` | Có | Có | Không sẵn |
| Có tổng số phần tử | Có | Không | Không |
| Có tổng số trang | Có | Không | Không |
| Cơ chế có thể phát sinh `COUNT` | Có | Thường không | Thường không |
| Thường cần nhìn trước 1 hàng | Không bắt buộc | Có | Không tự động |
| UI phù hợp | Bảng có phân trang theo tổng | “Tải thêm”, infinite scroll | Danh sách giới hạn đơn giản |

Bảng trên mô tả hợp đồng và hành vi điển hình của Spring Data. Hãy xác minh đường repository tùy chỉnh và các phiên bản thư viện nếu cần cam kết chính xác số query.

## 7. Đếm tổng ở SQL++ tốn gì?

Một câu `COUNT(1)` thường trông rất ngắn:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Nhưng chi phí của nó phụ thuộc vào:

- **Độ chọn lọc của điều kiện:** có bao nhiêu document hoặc index entries được xét?
- **Index:** có secondary index phù hợp để lọc và đếm từ index không?
- **Cấu trúc truy vấn:** có `DISTINCT`, `JOIN`, `GROUP BY`, `UNNEST`, phép tính hoặc hàm đắt tiền không?
- **Số lượng dữ liệu:** đếm một tập rất lớn có thể cần nhiều công việc dù payload trả về chỉ một số.
- **Mức nhất quán:** cấu hình query scan consistency có thể ảnh hưởng độ trễ và độ mới.
- **Tải của hệ thống:** tài nguyên Query/Index Service, số truy vấn đồng thời, số trang được yêu cầu mỗi giây.

Đừng nhầm **kết quả trả chỉ vài byte** với **chi phí tính ra kết quả**. Truy vấn count có thể trả `{"total": 700000}` nhưng để có số đó hệ thống đã xử lý nhiều entries.

Mặt khác, không đúng khi nói mọi `COUNT` đều phải đọc toàn bộ body document. SQL++ optimizer có thể dùng index scan hoặc các tối ưu đếm khi query/index phù hợp. Vì vậy phải xem kế hoạch thực thi cụ thể.

### `COUNT(1)` khác `COUNT(c.email)` thế nào?

Trong SQL++, `COUNT(1)` đếm các hàng đầu vào của aggregation theo bộ lọc, bởi biểu thức `1` luôn có giá trị. `COUNT(c.email)` đếm các hàng có giá trị `email` **không phải `NULL`/`MISSING`**; vì vậy tổng có thể nhỏ hơn khi dữ liệu không đồng nhất.

~~~sql
SELECT COUNT(1) AS allActive,
       COUNT(c.email) AS withEmail
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Không được thay count toàn bộ kết quả bằng `COUNT(field)` nếu field có thể vắng/null. `COUNT(DISTINCT c.email)` lại là bài toán khác: đếm **số giá trị email khác nhau**, không phải số document khách hàng.

## 8. Bộ lọc trong data query và count query phải giống nhau

Giả sử hệ thống multi-tenant và một collection chứa nhiều loại document. Truy vấn dữ liệu lọc:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
  AND c.type = "customer"
ORDER BY c.fullName, META(c).id
LIMIT $limit OFFSET $offset;
~~~

Count tương ứng phải dùng cùng predicate:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
  AND c.type = "customer";
~~~

Nếu count bỏ `tenantId` hoặc `type`, UI hiển thị số lượng sai và có thể vô tình tiết lộ thông tin tổng hợp ngoài phạm vi được phép. Với Spring Data Couchbase, filter discriminator có thể do cơ chế `#n1ql.filter`/mapping cung cấp cho các query entity; query `@Query` tự viết phải kiểm chứng nó có được áp dụng phù hợp.

Đối với query có `JOIN`, `UNNEST` hoặc `DISTINCT`, số hàng sau join có thể **khác số entity duy nhất**. Không lấy `COUNT(1)` của nguồn gốc rồi suy ra tổng số hàng của một query nhóm/phân biệt mà không phân tích cấu trúc.

### Count đúng nhưng có thể không khớp nội dung trang tức thời

Hai câu SQL++ thường là hai thao tác đọc độc lập. Nếu có insert/delete hoặc update thay đổi bộ lọc giữa lúc lấy trang và lúc đếm, tổng có thể **khác với trạng thái tập dữ liệu tạo nên trang**.

Điều này không tự động là lỗi của Spring Data. Khi yêu cầu một snapshot nhất quán tuyệt đối giữa dữ liệu trang và tổng, cần nghiên cứu cách đọc transactional/snapshot phù hợp với Couchbase Server, không được mặc nhiên cho rằng hai query riêng lẻ cùng nhìn một thời điểm.

## 9. Tối ưu COUNT bắt đầu từ index và `EXPLAIN`

Ví dụ tạo index cho điều kiện lọc và sắp xếp của danh sách:

~~~sql
CREATE INDEX ix_customer_active_name
ON `shop`.`crm`.`customers` (active, fullName);
~~~

Sau đó kiểm tra **hai kế hoạch**, bởi query dữ liệu và query đếm có mục tiêu tối ưu khác nhau.

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20 OFFSET 0;
~~~

~~~sql
EXPLAIN
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Khi đọc `EXPLAIN`/query profile, hãy xác định:

1. Query chọn index nào và có quét nhiều entries không?
2. Có bước `Fetch` document body không, hay index có đủ dữ liệu để cover?
3. Có bước sort riêng, filter sau index hoặc aggregation tốn tài nguyên không?
4. Có tối ưu hóa đếm tại indexer (nếu kế hoạch/phiên bản hỗ trợ) không?
5. `LIMIT`/`OFFSET` có được đẩy xuống indexer không, hay phải xử lý ở Query Service?
6. Latency của truy vấn đếm là bao nhiêu và ảnh hưởng thế nào đến p95/p99 API?

`COUNT` không cần tất cả các trường hiển thị của query dữ liệu; có thể một index hẹp cho filter/đếm đã đủ. Ngược lại, một covering index để trả đủ field hiển thị có thể rộng hơn và làm tăng chi phí lưu trữ, ghi, cập nhật index. **Không thêm index chỉ vì count chậm khi chưa xem kế hoạch.**

### `LIMIT/OFFSET` pushdown không được bảo đảm

Couchbase có thể đẩy phân trang xuống Index Service trong những trường hợp nhất định. Nếu query dùng nhiều index, `JOIN` hoặc `ORDER BY` không khớp thứ tự index, Query Service có thể phải xử lý nhiều dữ liệu hơn. Vì vậy `LIMIT 20` không tự chứng minh query rẻ, đặc biệt với `OFFSET` rất lớn.

## 10. Spring Data `@Query` kết hợp `Pageable`: tránh ghi lặp phân trang

Khi viết inline query N1QL/SQL++ cho repository có `Pageable` hoặc `Sort`, Spring Data Couchbase có thể tự ghép điều kiện sắp xếp/phân trang vào câu query.

Mẫu query entity điển hình:

~~~java
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND active = $1")
Page<Customer> searchByActive(boolean active, Pageable pageable);
~~~

Trong trường hợp này, hãy **để `Pageable` thực hiện phân trang** và không tự đặt `ORDER BY`, `LIMIT`, `OFFSET` trong chuỗi query inline. Tài liệu Spring Data Couchbase cảnh báo việc trộn các clause này với tham số pageable/sort có thể tạo SQL++ sai cú pháp vì các clause được thêm lần nữa.

Với truy vấn dẫn xuất, Spring Data biết predicate và có thể dựng truy vấn đếm phù hợp cho `Page` trong các tình huống hỗ trợ. Với câu query tùy chỉnh phức tạp (JOIN, GROUP, DISTINCT, alias, aggregation), phải kiểm tra:

- Câu SQL++ thực tế được tạo cho **data query**.
- Câu SQL++ thực tế (nếu có) dùng cho **count query**.
- `COUNT` là tổng của **kết quả nghiệp vụ**, không nhầm với số document nguồn.
- Kết quả được map đúng kiểu (entity/projection/DTO).
- Có filter loại entity và tenant phù hợp.

Nếu không thể suy ra count đúng từ query phức tạp, hãy tách logic truy vấn dữ liệu và count vào custom repository/service với SQL++ tường minh; đừng dựa vào count tự sinh mà chưa có integration test.

## 11. Tự triển khai `Slice` bằng SQL++ để kiểm soát số query

Khi cần projection gọn và bảo đảm không phát sinh truy vấn tổng, có thể dùng Couchbase Java SDK trong custom repository.

Định nghĩa DTO:

~~~java
public record CustomerCard(String id, String fullName, String email) {}
~~~

Ví dụ hàm đọc trang có look-ahead:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;
import org.springframework.data.domain.Sort;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Hàm minh họa đặt trong một service/custom repository có Cluster.
public Slice<CustomerCard> loadActiveSlice(
        Cluster cluster, int pageNumber, int pageSize) {

    if (pageNumber < 0 || pageSize < 1 || pageSize > 200) {
        throw new IllegalArgumentException("Invalid paging request");
    }

    Pageable pageable = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by("fullName").ascending()
                .and(Sort.by("id").ascending()));

    String statement = """
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = TRUE
        ORDER BY c.fullName, META(c).id
        LIMIT $limit OFFSET $offset
        """;

    JsonObject parameters = JsonObject.create()
            .put("limit", pageSize + 1)
            .put("offset", pageable.getOffset());

    QueryResult queryResult = cluster.query(
            statement,
            queryOptions().parameters(parameters));

    List<CustomerCard> fetched = queryResult.rowsAsObject()
            .stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("fullName"),
                    row.getString("email")))
            .toList();

    boolean hasNext = fetched.size() > pageSize;
    List<CustomerCard> content = hasNext
            ? fetched.subList(0, pageSize)
            : fetched;

    return new SliceImpl<>(content, pageable, hasNext);
}
~~~

Mã minh họa giả định hệ thống có `Cluster` được cấu hình, DTO hợp lệ, và chỉ cho phép sort cố định theo tên và document key. Metadata `Sort` trong `PageRequest` được giữ tương ứng với `ORDER BY` thực thi; method không cho caller tùy ý chọn sort khác.

**Điểm cần nhớ:**

- Query chỉ lấy ba trường đã chọn, không gửi body entity đầy đủ.
- `LIMIT` bằng `pageSize + 1` để xác định `hasNext`.
- Không có câu `COUNT` trong đường xử lý này.
- `SliceImpl` là kết quả Spring Data có `hasNext`, `getContent`, `nextPageable`.
- `pageSize` có giới hạn để tránh request trả quá nhiều dữ liệu.
- Dù không count, `OFFSET` vẫn đắt khi `pageNumber` lớn.
- Query SDK ở ví dụ cần được kiểm thử với index, consistency và mapping của ứng dụng; việc ánh xạ dữ liệu không tự được Spring Data converter bảo đảm.

### Muốn `Page` từ SQL++ SDK thì sao?

Cần có một tổng phù hợp rồi dựng `PageImpl`:

~~~java
// Đoạn minh họa sau khi đã có content của trang và total từ COUNT.
// Hai query dữ liệu và đếm phải dùng cùng bộ lọc nghiệp vụ.
Page<CustomerCard> page = new PageImpl<>(
        content,
        pageable,
        total
);
~~~

Nếu yêu cầu tổng chính xác, cần chạy count query hoặc sử dụng một nguồn tổng được kiểm soát nhất quán. Cách tự dựng `PageImpl` **không làm count miễn phí**; nó chỉ chuyển trách nhiệm lấy `total` sang ứng dụng. Với dữ liệu biến động giữa hai query, phải chấp nhận hoặc xử lý vấn đề nhất quán.

## 12. Kỹ thuật bỏ hoặc trì hoãn `COUNT`

Không phải endpoint nào cũng cần tổng số bản ghi **ngay mỗi request**.

### 12.1. Chuyển UI sang “Tải thêm”

Nếu UX chỉ cần nút **Tải thêm**, dùng `Slice` và `hasNext`. Đây thường là giải pháp đơn giản nhất vì loại bỏ toàn bộ nhu cầu count trong từng lần chuyển trang.

### 12.2. Chỉ đếm khi người dùng yêu cầu

Ví dụ trang danh sách mở nhanh với `Slice`; người dùng có nút “Xem tổng số kết quả”. Khi bấm mới gọi endpoint count riêng. Cách này giữ đường tải danh sách nhanh mà vẫn đáp ứng tính năng cần tổng.

### 12.3. Cache count theo bộ lọc

Với những bộ lọc phổ biến và dữ liệu không cần chính xác đến từng giây, có thể cache count theo:

- Tenant/quyền truy cập và tập filter đã chuẩn hóa.
- Loại entity, trạng thái và các điều kiện truy vấn.
- Thời điểm tính và TTL cache.

Phải xác định chính sách invalidation hoặc thời hạn chấp nhận dữ liệu cũ. Không sử dụng cùng một số tổng cho các tenant khác nhau hoặc các bộ lọc khác nhau.

### 12.4. Dùng tổng ước lượng và nói rõ tính chất ước lượng

Một dashboard có thể chỉ cần “khoảng 700 nghìn khách hàng”. Số này có thể đến từ cơ chế thống kê/aggregation đã thiết kế riêng. **Không gắn nhãn “tổng chính xác”** cho số ước lượng hoặc số không được đồng bộ với predicate hiện tại.

### 12.5. Một số trường hợp có thể suy tổng từ kết quả trang

Nếu trang đầu nhận ít hơn `pageSize` (và không có vấn đề lọc ở phía client), tổng có thể được suy ra từ dữ liệu trả về. Một số cơ chế của Spring Data tận dụng điều này để tránh chạy `COUNT`.

Đây là một **tối ưu theo tình huống**, không phải giải pháp thay thế count khi tập kết quả có nhiều trang. Hãy xác minh hành vi thật trên query path đang dùng.

## 13. `OFFSET` lớn: chuyển sang keyset pagination khi phù hợp

Bỏ count chưa xử lý vấn đề `OFFSET` lớn. Đối với danh sách tăng dần theo `fullName` và document key, có thể dùng **keyset pagination**:

~~~sql
-- Trang đầu.
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 21;
~~~

Sau khi hiển thị 20 bản ghi, client giữ giá trị sắp xếp của **hàng thứ 20** làm cursor:

~~~json
{
  "afterFullName": "Trần Minh",
  "afterId": "customer::42"
}
~~~

Query cho trang tiếp theo:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND (
      c.fullName > $afterFullName
      OR (
          c.fullName = $afterFullName
          AND META(c).id > $afterId
      )
  )
ORDER BY c.fullName, META(c).id
LIMIT 21;
~~~

Ý nghĩa:

- Truy vấn trang kế tiếp tìm những bản ghi **đứng sau cặp giá trị cursor** theo đúng thứ tự.
- `META(c).id` làm khóa phân xử vì tên có thể trùng.
- Không cần biết tổng số trang và không phải bỏ qua `OFFSET` tăng dần.
- Index và query plan phải phù hợp với điều kiện range, thứ tự và phép OR; **không tự khẳng định keyset luôn nhanh hơn** trong mọi truy vấn.
- Cần thống nhất cách xử lý `NULL`/`MISSING` trong field sắp xếp.
- Nếu document được chèn/xóa hoặc sửa `fullName` giữa các lần đọc, vẫn có thể xảy ra thay đổi tập kết quả; keyset không tự tạo snapshot toàn phiên.
- Với cursor đưa ra API công khai, cần kiểm tra định dạng, scope/tenant và các điều kiện lọc tương ứng; không tin tưởng input tùy ý.

Với yêu cầu UI nhảy thẳng đến “trang 1.500”, keyset không tiện như trang số tuyệt đối. Cần chọn theo nhu cầu điều hướng thực tế.

## 14. COUNT, Page/Slice và tính nhất quán của Couchbase

Couchbase Query Service dùng secondary index và có các lựa chọn về scan consistency. Một query lấy trang rồi một query count **không đương nhiên là một snapshot giao dịch**.

Ví dụ sau khi khách hàng mới được thêm:

1. Query trang chạy với một mức scan consistency và thấy một tập dữ liệu.
2. Có document mới được ghi thành công.
3. Query count chạy sau và thấy số tổng khác thời điểm query trang.

Ngược lại, nếu index chưa bắt kịp thay đổi theo chính sách consistency hiện hành, cả query trang hoặc count có thể chưa thấy thay đổi vừa ghi. Nếu nghiệp vụ yêu cầu read-after-write, cần chọn scan consistency theo khả năng của SDK/Spring Data và chấp nhận ảnh hưởng độ trễ.

Điều quan trọng:

- `REQUEST_PLUS` có thể chờ index cập nhật tới thời điểm yêu cầu, có lợi cho nhu cầu nhìn thấy thay đổi gần đây nhưng có thêm chi phí chờ.
- Cấu hình consistency thích hợp **không tự bảo đảm** hai câu query độc lập nhìn cùng một snapshot khi dữ liệu tiếp tục biến động.
- Một bảng quản trị thường có thể chấp nhận count chênh rất nhỏ; một báo cáo kiểm toán có thể đòi hỏi cơ chế snapshot/transaction hoặc pipeline tổng hợp riêng.
- Không dùng CAS để biến kết quả trang hoặc `COUNT` thành một snapshot của toàn collection. CAS bảo vệ phiên bản **một document** khi mutation, không thay thế điều kiện nhất quán của query tổng.

### TTL và count

Document có TTL có thể hết hạn trong lúc người dùng duyệt danh sách. Vì vậy `getTotalElements()` của `Page` biểu thị tổng mà hệ thống tính được tại thời điểm truy vấn đếm theo consistency phù hợp, **không phải cam kết tổng tồn tại vĩnh viễn**. UI không nên coi `totalPages` là một bất biến khi dữ liệu có insert/delete/TTL.

## 15. Khi phân trang kết hợp projection

Một row chỉ cần ID, tên và email:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20 OFFSET 0;
~~~

Projection giảm **kích thước mỗi row**, còn `Slice` tránh count và `LIMIT` giới hạn **số row**. Đây là ba cách tối ưu hóa khác nhau:

| Tối ưu | Tác động chính | Không giải quyết |
| --- | --- | --- |
| Chọn ít field bằng SQL++ projection | Payload, JSON mapping | Chi phí count và offset lớn |
| Dùng `Slice` thay `Page` | Không cần total/count cho hasNext | Sort, scan, offset, query không cover |
| Dùng keyset thay offset lớn | Giảm công việc bỏ qua các trang trước trong nhiều trường hợp | Cần cursor, index phù hợp, dữ liệu biến động |
| Covering index phù hợp | Có thể giảm `Fetch` body và hỗ trợ filter/sort | Không miễn phí lưu trữ và write amplification |
| Cache count | Giảm số lần tính tổng | Tổng có thể cũ, cần chính sách invalidation |

Nếu repository trả interface projection/DTO, cần kiểm tra SQL++ thực tế có chọn ít field hay materialize entity rồi mới tạo projection. Việc khai báo `Slice<CustomerSummary>` không tự làm query index-only. Kiểm thử dữ liệu, câu query và kế hoạch thực thi là ba việc riêng.

## 16. API reactive: không tự giải quyết chi phí COUNT

Spring Data Couchbase có reactive repository/template và Couchbase Java SDK có reactive API. Trong WebFlux, cần tránh chặn event-loop trong lúc đợi query hoặc count.

Ví dụ ý tưởng dùng reactive query path:

~~~java
// Pseudocode: cụ thể hóa API theo SDK/phiên bản đang dùng.
Mono<List<CustomerCard>> firstTwentyOne = queryActiveRowsReactive(21);

Mono<Slice<CustomerCard>> firstSlice = firstTwentyOne
    .map(rows -> {
        boolean hasNext = rows.size() > 20;
        List<CustomerCard> content =
                rows.subList(0, Math.min(rows.size(), 20));
        return new SliceImpl<>(
                content,
                PageRequest.of(0, 20),
                hasNext);
    });
~~~

Pseudocode này diễn tả phép look-ahead: query reactive trả tối đa 21 row, sau đó gói thành `Slice`. Tên `queryActiveRowsReactive` là hàm ứng dụng tự xây dựng, không phải API có sẵn của SDK.

Nếu UI cần `Page` với tổng, reactive service cũng phải tổ chức **đường đếm** phù hợp. Truy vấn reactive không làm `COUNT` rẻ hơn; nó thay đổi mô hình xử lý bất đồng bộ và quản lý luồng. Đặc biệt không nên khẳng định mọi phiên bản reactive repository hỗ trợ trực tiếp `Mono<Page<T>>` hoặc `Mono<Slice<T>>`; cần kiểm tra return type và chức năng phân trang được phiên bản Spring Data Couchbase cung cấp.

## 17. Bảng lựa chọn cho thiết kế sản phẩm

| Yêu cầu nghiệp vụ | Kiểu nên bắt đầu | Lưu ý chính |
| --- | --- | --- |
| Danh sách có nút “Tải thêm” | `Slice<T>` | `pageSize + 1`; không cần total |
| Bảng cho phép nhảy đến trang cuối theo tổng | `Page<T>` | Cần count đúng và chi phí chấp nhận được |
| Dashboard chỉ hiện một con số | Count query riêng | Không trả cả trang chỉ để lấy total |
| Autocomplete lấy tối đa 10 gợi ý | `List<T>` hoặc giới hạn query | Không cần count/page metadata |
| Export hàng triệu bản ghi | Cursor/keyset/streaming | Giới hạn bộ nhớ, timeout, không tải tất cả một lần |
| Danh sách truy cập trang rất sâu | Keyset và cursor nếu UX cho phép | Đảm bảo thứ tự xác định và index phù hợp |
| Báo cáo group/distinct có total phức tạp | Custom data query + count đúng ngữ nghĩa | Không tin count tự động nếu chưa test |
| Giao diện cần tổng gần đúng | Slice + total ước lượng độc lập | Ghi rõ thời điểm và độ chính xác |
| Dữ liệu liên tục thêm/xóa | Slice hoặc page với chính sách consistency rõ | Không kỳ vọng total cố định giữa các request |

Điều quyết định là **UI thực sự cần thông tin gì**. Nếu không hiển thị tổng, đừng buộc hệ thống phải tính tổng trên mỗi request.

## 18. Những lỗi thường gặp

### Lỗi 1 — “Page luôn nhanh vì chỉ lấy 20 hàng”

`Page` có thể kèm `COUNT` độc lập trên toàn tập đã lọc. Độ trễ tổng có thể bị chi phối bởi count, index scan hoặc sort; đo riêng từng query.

### Lỗi 2 — “Slice luôn chỉ chạy đúng một query và luôn nhanh”

Hợp đồng `Slice` tránh tổng, nhưng triển khai cụ thể và query path có thể khác; ở page sâu, `OFFSET` vẫn làm tăng chi phí. Kiểm tra SQL++ thật và profile.

### Lỗi 3 — “20 hàng trả về nên total = 20”

`getNumberOfElements()` là số hàng trong trang, không phải `getTotalElements()`. Với `Slice` không có total. Không dùng số hàng của một trang đầy để suy tổng.

### Lỗi 4 — “COUNT lấy cùng LIMIT với data query”

Count dùng để tính tổng toàn tập **không được mang `LIMIT/OFFSET` của trang**, trừ khi nghiệp vụ thực sự muốn đếm chính phạm vi đó. Thử riêng trường hợp trang đầu, trang giữa và cuối.

### Lỗi 5 — “Đổi Page sang Slice xong vẫn giữ UI ‘Trang x/y’”

`Slice` không biết `y`. Cần sửa hợp đồng API và UI, hoặc cung cấp một endpoint/count nguồn riêng. Không tự bịa tổng từ `hasNext`.

### Lỗi 6 — “Query data lọc tenant, query count thì không”

Tổng sẽ sai, và có thể lộ thông tin số lượng ngoài quyền. Cả hai query phải cùng điều kiện nghiệp vụ, discriminator và quyền truy cập.

### Lỗi 7 — “Có ORDER BY nên phân trang ổn định”

Nếu sort theo `fullName` mà nhiều document trùng tên, thứ tự giữa chúng có thể không xác định. Thêm khóa phụ duy nhất như `META(c).id`, đồng thời vẫn xét thay đổi đồng thời.

### Lỗi 8 — “Count đúng thì dữ liệu trang luôn nhất quán”

Hai query độc lập có thể quan sát thời điểm khác nhau. TTL và mutation còn có thể thay tổng giữa các request. Xác định mức chênh lệch chấp nhận được cho API.

### Lỗi 9 — “COUNT là quét toàn bộ body”

Kế hoạch đếm có thể dùng index và tối ưu tại indexer. Cần `EXPLAIN` và số đo thay vì suy luận từ cú pháp `COUNT`.

### Lỗi 10 — “@Query + Pageable tự động chấp nhận LIMIT/OFFSET viết tay”

Spring Data Couchbase có thể tự thêm `ORDER BY/LIMIT/OFFSET` cho inline query có pageable/sort; tự viết các clause đó trùng lặp dễ tạo SQL++ sai. Hãy chọn một nơi duy nhất kiểm soát phân trang.

## 19. Quy trình kiểm chứng và tối ưu thực tế

1. **Làm rõ hợp đồng UI:** cần total chính xác, chỉ `hasNext` hay chỉ một danh sách giới hạn?
2. **Chọn kiểu kết quả:** `Page`, `Slice` hoặc `List`/cursor; xác định API response tương ứng.
3. **Đặt page size hợp lý:** giới hạn tối đa ở API; chặn page âm, size 0, size quá lớn và offset vượt khả năng hệ thống.
4. **Chọn thứ tự xác định:** sắp xếp theo field nghiệp vụ rồi ID khi cần; kiểm tra Spring Data mapping hoặc SQL++ tường minh.
5. **Kiểm tra query data:** payload, projection, predicate, LIMIT/OFFSET và index plan.
6. **Kiểm tra query count:** có chạy không, chạy bao nhiêu lần, filter có khớp query data không, latency/scan thế nào?
7. **Xem `EXPLAIN` cho cả hai:** index, `Fetch`, sort, count optimization và pagination pushdown.
8. **Đo bằng workload có ý nghĩa:** trang đầu, trang giữa, offset sâu, bộ lọc ít/nhiều kết quả, concurrent requests; xem p50/p95/p99.
9. **Thử dữ liệu biến động:** insert/delete, update thay bộ lọc, TTL expiration và read-after-write.
10. **Cân nhắc loại bỏ COUNT nếu không cần:** Slice, lazy count, cache/ước lượng và sửa UI rõ ràng.
11. **Tối ưu trang sâu:** keyset/cursor phù hợp và index theo điều kiện/sort.
12. **Cố định hành vi bằng integration test:** xác nhận count đúng ngữ nghĩa, `hasNext` đúng, không rò rỉ tenant và số query phù hợp kỳ vọng.

### Bộ ca kiểm thử tối thiểu

| Dữ liệu ban đầu, `pageSize = 3` | Kỳ vọng ở `Page` | Kỳ vọng ở `Slice` |
| --- | --- | --- |
| 0 bản ghi | total = 0, content rỗng | content rỗng, `hasNext=false` |
| 2 bản ghi | total = 2, trang đầu có 2 | trang đầu có 2, `hasNext=false` |
| 3 bản ghi | total = 3, một trang | trang đầu có 3, `hasNext=false` |
| 4 bản ghi | total = 4, hai trang | trang đầu có 3, `hasNext=true` |
| 7 bản ghi, request trang 1 | total = 7, trang 1 có 3 | trang 1 có 3, `hasNext=true` |
| 7 bản ghi, request trang 2 | total = 7, trang cuối có 1 | trang 2 có 1, `hasNext=false` |

Đây là kỳ vọng logic trong một tập dữ liệu không thay đổi giữa các lần đọc. Với dữ liệu đồng thời, bài test phải quy định scan consistency và cách xử lý count thay đổi.

## 20. Bài tập thực hành

Xây dựng hai endpoint từ cùng collection `customers`:

- `GET /customers?page=0&size=20` trả dữ liệu danh sách cùng `totalElements`/`totalPages` dành cho bảng quản trị.
- `GET /customers/feed?page=0&size=20` trả dữ liệu và `hasNext`, **không** tính tổng chỉ để hiển thị nút “Tải thêm”.

Yêu cầu:

1. Tạo 41 document hoạt động, một số trùng `fullName` và một số thiếu `email`.
2. Dùng repository method trả `Page<Customer>` cho endpoint quản trị, `Slice<Customer>` cho feed.
3. Xác nhận trang đầu `size=20` có `hasNext=true`; trang số 2 chỉ có 1 bản ghi và `hasNext=false`.
4. Kiểm tra total của `Page`, query SQL++ dữ liệu và count thực tế; ghi lại số query được chạy.
5. Thử `@Query` có `Pageable` nhưng **không** tự viết ORDER BY/LIMIT/OFFSET trong chuỗi inline query.
6. Viết biến thể custom SDK chỉ `SELECT` ID/tên/email, lấy `size+1` và trả `SliceImpl`.
7. Dùng `EXPLAIN` so sánh data query và count query trước/sau khi cân nhắc index.
8. Chạy thử page sâu để thấy vấn đề `OFFSET`, sau đó viết keyset query dùng `fullName` và `META(c).id`.
9. Chèn/xóa document giữa truy vấn trang và count; ghi lại hợp đồng UX khi total không còn khớp tức thời.
10. Nếu dùng reactive service, kiểm tra pipeline không block và tổng có được tính chỉ khi cần.

### Câu hỏi tự kiểm tra

1. `Page` có metadata nào mà `Slice` không có?
2. Vì sao `Slice` cần lấy `pageSize+1` hàng?
3. Tại sao không thể suy total từ 20 row của một trang đầy?
4. Khi nào `Page` có thể bỏ qua câu `COUNT`?
5. Có những trường hợp nào `COUNT` có thể được tính từ index thay vì đọc mọi document body?
6. Vì sao `OFFSET` lớn vẫn chậm dù đã đổi từ `Page` sang `Slice`?
7. Trong dữ liệu multi-tenant, data query và count query phải chia sẻ những predicate nào?
8. Vì sao `Page` và count query riêng vẫn không tự tạo snapshot thống nhất?
9. Khi nào keyset pagination phù hợp hơn trang số tuyệt đối?
10. Vì sao API chỉ có nút “Tải thêm” không nên tính tổng trên mọi request?

## 21. Tài liệu chính thức và lưu ý theo phiên bản

- [Spring Data Couchbase — Query Methods](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): `Pageable`, `Page`, `Slice`, `List` và chi phí query đếm.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): N1QL/SQL++, repository phân trang và lưu ý inline `@Query` kết hợp `Pageable`/`Sort`.
- [Spring Data Couchbase — Query Return Types](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-return-types-reference.html): kiểu trả về `Page` và `Slice`.
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): cấu trúc result, count query và look-ahead.
- [Couchbase Server — Index Pushdowns](https://docs.couchbase.com/server/current/indexes/index_pushdowns.html): điều kiện optimizer có thể đẩy LIMIT/OFFSET xuống Index Service.
- [Couchbase SQL++ — LIMIT Clause](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html): giới hạn kết quả.
- [Couchbase SQL++ — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): phân tích kế hoạch truy vấn.

Tính năng của repository, tối ưu hóa đếm và chiến lược sinh query có thể thay đổi giữa các phiên bản **Spring Data Couchbase, Couchbase Java SDK và Couchbase Server**. Hãy đối chiếu dependency thực tế và đo câu SQL++ chạy trên hệ thống trước khi cam kết về số query hay chi phí.

> **Ghi nhớ:** `Page` trả **nội dung + tổng** nên có thể phải trả giá cho `COUNT`. `Slice` trả **nội dung + hasNext** bằng cách xem thêm một hàng và thường không cần count. Dù chọn kiểu nào, hiệu năng thực tế còn phụ thuộc điều kiện lọc, index, `OFFSET`, kích thước projection, tính nhất quán và yêu cầu của giao diện.
