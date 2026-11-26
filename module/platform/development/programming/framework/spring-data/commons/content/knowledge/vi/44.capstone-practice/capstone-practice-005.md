# Thêm Sort, Page, Slice và scrolling theo hỗ trợ

## Mục tiêu và phạm vi

Bài thực hành bổ sung các cách đọc dữ liệu có giới hạn cho một danh mục sản phẩm. Bạn cần chọn hợp đồng theo nhu cầu client, áp dụng thứ tự rõ ràng và chỉ triển khai scrolling khi module store thực sự hỗ trợ.

Spring Data Commons cung cấp Sort, Pageable, Page, Slice, Window và ScrollPosition. Việc tạo query và thực thi vẫn thuộc module store.

Sau bài thực hành, bạn cần giải thích được:

- Vì sao một query phải có thứ tự xác định khi phân trang.
- Khi nào client cần Page, khi nào chỉ cần Slice.
- Window dùng offset khác Window dùng keyset như thế nào.
- Cách tiếp tục từ kết quả cuối mà không lặp phần tử trên tập dữ liệu tĩnh.
- Điều gì cần thay đổi nếu store không hỗ trợ một chữ ký scrolling.
- Cách xác nhận nội dung, metadata và giới hạn đầu vào.

Nhánh tham chiếu dùng JPA với derived query và projection được module hỗ trợ. Các đoạn mã là khung thực hành; dự án còn cần cấu hình ứng dụng, database kiểm thử, schema và dependency tương thích.

## 1. Đề bài và hợp đồng đầu ra

Danh mục cần phục vụ ba nhu cầu:

| Nhu cầu | Hợp đồng |
|---|---|
| Bảng quản trị có tổng số | Page |
| Danh sách có nút tải tiếp, không cần total | Slice |
| Duyệt tuần tự theo vị trí đã đọc | Window, nếu store hỗ trợ |

Bổ sung một truy vấn xem trước tối đa năm sản phẩm để thực hành Sort mà không tạo endpoint tải toàn bộ dữ liệu.

Quy tắc đầu vào của bài:

- Category phải có giá trị.
- Page index bắt đầu từ 0.
- Page size từ 1 đến 100.
- Page index tối đa 1000 cho các endpoint theo số trang.
- Sort chỉ cho phép id, title, price hoặc createdAt.
- Direction chỉ nhận asc hoặc desc.
- Khi khóa chính chưa là id, thêm id ASC làm khóa phụ.
- Nhánh keyset scrolling dùng thứ tự cố định createdAt DESC, id DESC.
- Không cho client tự bật unpaged qua query parameter.

Các giới hạn là quyết định của bài thực hành, không phải toàn bộ giá trị mặc định của Spring Data web.

## 2. Kiểm tra khả năng của store trước khi thêm phương thức

Trước khi đăng ký repository, cần lập bảng khả năng của nhánh triển khai:

| Khả năng | Cần xác nhận |
|---|---|
| Derived query theo category | Module tạo được query trên property tương ứng |
| Dynamic Sort | Property và hướng sort được hỗ trợ |
| Pageable trả Page | Có nội dung và total đúng theo query |
| Pageable trả Slice | Có hasNext đúng mà không yêu cầu total |
| Projection CatalogRow | Kiểu kết quả được mapping đúng |
| Window với ScrollPosition | Loại query và phiên bản module hỗ trợ scrolling |
| Keyset | Sort, kiểu khóa và projection đáp ứng yêu cầu của module |

Có class Window trên classpath chưa đủ để kết luận store hỗ trợ mọi query scrolling.

Nếu nhánh không hỗ trợ Window:

- Giữ Page hoặc Slice nếu các khả năng đó được hỗ trợ.
- Không đăng ký query method Window không hợp lệ chỉ để API trông đồng nhất.
- Ghi rõ chức năng cursor chưa có trong nhánh đó.
- Nếu cần adapter tùy biến, thiết kế và kiểm tra semantics của adapter riêng.

Không tạo cursor giả bằng cách đổi tên page number thành token rồi mô tả đó là keyset.

## 3. Mô hình dữ liệu tham chiếu

Entity JPA tối thiểu:

```java
import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_item")
public class CatalogItem {

    @Id
    private Long id;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private Instant createdAt;

    protected CatalogItem() {
    }

    public CatalogItem(
            Long id,
            String category,
            String title,
            BigDecimal price,
            Instant createdAt) {
        this.id = id;
        this.category = category;
        this.title = title;
        this.price = price;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getCategory() {
        return category;
    }

    public String getTitle() {
        return title;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

ID trong fixture được gán để expected result dễ kiểm tra. Chính sách cấp ID của ứng dụng thật có thể khác và cần mapping phù hợp.

Projection dùng cho các thao tác đọc:

```java
import java.math.BigDecimal;
import java.time.Instant;

public interface CatalogRow {

    Long getId();

    String getTitle();

    BigDecimal getPrice();

    Instant getCreatedAt();
}
```

Projection chứa cả id và createdAt vì nhánh keyset cần những giá trị này để tạo vị trí tiếp tục.

Không bỏ các khóa cần thiết khỏi projection ở tầng query. Sau khi repository có đủ dữ liệu và position, tầng HTTP có thể chuyển nội dung thành DTO công khai.

## 4. Fixture có thể phát hiện lỗi sort và offset

Dùng tập dữ liệu:

| ID | Category | Title | Price | CreatedAt |
|---:|---|---|---:|---|
| 101 | book | A | 10.00 | 2026-01-01T00:00:00Z |
| 102 | book | B | 20.00 | 2026-01-01T00:00:00Z |
| 103 | book | C | 20.00 | 2026-01-02T00:00:00Z |
| 104 | book | D | 30.00 | 2026-01-02T00:00:00Z |
| 105 | book | E | 40.00 | 2026-01-03T00:00:00Z |
| 201 | accessory | Other | 1.00 | 2026-01-04T00:00:00Z |

Expected order:

```text
book, price ASC, id ASC:
    101, 102, 103, 104, 105

book, createdAt DESC, id DESC:
    105, 104, 103, 102, 101
```

Dữ liệu có:

- Hai bản ghi trùng price.
- Hai nhóm trùng createdAt.
- Một bản ghi category khác có giá thấp hơn để phát hiện lỗi lọc.
- Năm phần tử khớp để trang cuối không đầy khi size bằng 2.

Không dùng thứ tự insert như bằng chứng query có sort. Cố ý insert fixture khác thứ tự expected để test dễ phát hiện thiếu ORDER BY.

## 5. Repository đọc với Sort, Page và Slice

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.Repository;

public interface CatalogReadRepository
        extends Repository<CatalogItem, Long> {

    List<CatalogRow> findTop5ByCategory(
            String category,
            Sort sort);

    Page<CatalogRow> findByCategory(
            String category,
            Pageable pageable);

    Slice<CatalogRow> findAllByCategory(
            String category,
            Pageable pageable);
}
```

Ba phương thức phục vụ ba hợp đồng khác nhau:

- Preview có giới hạn tối đa 5.
- Page có total.
- Slice có thông tin điều hướng nhưng không có total.

Tên findAllByCategory tạo chữ ký riêng cho query trả Slice. Điều kiện lọc vẫn là category.

Không thêm cả Pageable và Sort như hai tham số trùng trách nhiệm vào cùng query method. Với Page và Slice, đưa Sort vào PageRequest.

Interface chỉ công khai hợp đồng đọc cần dùng trong bài. Nó không tự cấu hình quyền truy cập hoặc transaction chỉ đọc.

## 6. Tạo Sort từ danh sách trường cho phép

```java
import java.util.Set;

import org.springframework.data.domain.Sort;

public final class CatalogSortPolicy {

    private static final Set<String> FIELDS =
            Set.of("id", "title", "price", "createdAt");

    private CatalogSortPolicy() {
    }

    public static Sort build(
            String field,
            String direction) {

        if (!FIELDS.contains(field)) {
            throw new IllegalArgumentException(
                    "Unsupported sort field");
        }

        Sort.Direction order = switch (direction) {
            case "asc" -> Sort.Direction.ASC;
            case "desc" -> Sort.Direction.DESC;
            default -> throw new IllegalArgumentException(
                    "Unsupported sort direction");
        };

        Sort sort = Sort.by(new Sort.Order(order, field));

        if (!"id".equals(field)) {
            sort = sort.and(Sort.by(Sort.Order.asc("id")));
        }

        return sort;
    }
}
```

Lớp tiếp nhận request cần gán default và kiểm tra tham số thiếu hoặc null trước khi gọi chính sách trên.

Ví dụ default của endpoint theo trang có thể là price ASC; nhánh scrolling vẫn dùng thứ tự riêng cố định như đã công bố.

Không truyền tùy ý chuỗi như customer.secret hoặc một property path bất kỳ từ client vào repository.

Nếu tên trường API khác property lưu trữ, thay tập tên trực tiếp bằng một bảng ánh xạ cho phép. Không để việc đổi tên entity vô tình đổi hợp đồng công khai.

Khóa id phụ làm thứ tự xác định trên dữ liệu tĩnh. Nó không tự giữ nguyên kết quả giữa các request nếu dữ liệu đang thay đổi.

## 7. Thêm service cho Page và Slice

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class CatalogReadService {

    private final CatalogReadRepository catalog;

    public CatalogReadService(
            CatalogReadRepository catalog) {
        this.catalog = catalog;
    }

    public Page<CatalogRow> page(
            String category,
            int page,
            int size,
            String sortField,
            String direction) {

        return catalog.findByCategory(
                requireCategory(category),
                request(page, size, sortField, direction));
    }

    public Slice<CatalogRow> slice(
            String category,
            int page,
            int size,
            String sortField,
            String direction) {

        return catalog.findAllByCategory(
                requireCategory(category),
                request(page, size, sortField, direction));
    }

    private Pageable request(
            int page,
            int size,
            String field,
            String direction) {

        if (page < 0 || page > 1000) {
            throw new IllegalArgumentException(
                    "Page is outside the allowed range");
        }

        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Size is outside the allowed range");
        }

        Sort sort = CatalogSortPolicy.build(field, direction);

        return PageRequest.of(page, size, sort);
    }

    private String requireCategory(String category) {
        if (category == null || category.isBlank()) {
            throw new IllegalArgumentException(
                    "Category is required");
        }

        return category.strip();
    }
}
```

Các exception ở đây thể hiện precondition của ví dụ service. Tầng HTTP cần chuyển đúng lỗi đầu vào thành response theo hợp đồng ứng dụng; không bắt mọi IllegalArgumentException phát sinh ở mọi tầng rồi coi đó đều là lỗi client.

Test web cũng cần xác nhận request sai không gọi tầng dữ liệu.

Không lấy size từ client rồi tự gọi Pageable.unpaged khi size vượt mức. Vượt giới hạn phải được xử lý theo chính sách đã chọn.

## 8. Thiết kế JSON riêng cho Page và Slice

Ví dụ DTO:

```java
import java.math.BigDecimal;

public record CatalogItemResponse(
        Long id,
        String title,
        BigDecimal price) {
}
```

```java
import java.util.List;

public record CatalogPageResponse(
        List<CatalogItemResponse> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}
```

```java
import java.util.List;

public record CatalogSliceResponse(
        List<CatalogItemResponse> items,
        int page,
        int size,
        boolean hasNext) {
}
```

Các bước mapping:

```text
Page:
    map content sang CatalogItemResponse
    giữ number, size, totalElements, totalPages, hasNext

Slice:
    map content sang CatalogItemResponse
    giữ number, size, hasNext
    không tự tạo total
```

Ví dụ Page đầu với price ASC, size bằng 2:

```json
{
  "items": [
    {"id": 101, "title": "A", "price": 10.00},
    {"id": 102, "title": "B", "price": 20.00}
  ],
  "page": 0,
  "size": 2,
  "totalElements": 5,
  "totalPages": 3,
  "hasNext": true
}
```

Slice cùng vị trí có thể có cùng items và hasNext nhưng không có totalElements hoặc totalPages.

Nếu client thật sự cần total, không thay Page bằng Slice rồi gán total bằng số phần tử đã đọc tới hiện tại.

## 9. Kiểm tra các trang biên và kết quả rỗng

Với category book, price ASC, id ASC và size bằng 2:

| Page index | IDs | Số phần tử | Total | Has next |
|---:|---|---:|---:|---|
| 0 | 101, 102 | 2 | 5 | true |
| 1 | 103, 104 | 2 | 5 | true |
| 2 | 105 | 1 | 5 | false |
| 3 | Rỗng | 0 | 5 | false |

Không có category khớp ở page 0:

```text
items = []
totalElements = 0
totalPages = 0
hasNext = false
```

Trang vượt phạm vi ở category book:

```text
items = []
page = 3
totalElements = 5
totalPages = 3
hasNext = false
```

Hai tình huống đều rỗng nhưng khác ý nghĩa. Mapping response không được biến total của trang vượt phạm vi thành 0.

Với Slice, hãy kiểm tra nội dung và hasNext; không gọi các getter tổng số mà hợp đồng không cung cấp.

Cần thêm trường hợp tập kết quả có đúng size phần tử: một lát đầy vẫn có thể là lát cuối.

## 10. Bổ sung repository scrolling trong nhánh được hỗ trợ

Chỉ đăng ký interface sau khi đã xác nhận module và loại query hỗ trợ:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.Repository;

public interface CatalogScrollRepository
        extends Repository<CatalogItem, Long> {

    Window<CatalogRow>
            findFirst2ByCategoryOrderByCreatedAtDescIdDesc(
                    String category,
                    ScrollPosition position);
}
```

First2 được chọn để fixture nhỏ cũng tạo được nhiều window. Khi áp dụng vào workload thật, chọn kích thước có giới hạn phù hợp và cập nhật query/hợp đồng tương ứng.

Điều kiện của nhánh keyset:

- createdAt và id không null.
- Sort cố định createdAt DESC, id DESC.
- Projection chứa cả hai khóa.
- Query nhận đúng category ở mọi lần tiếp tục.
- Module có thể trích xuất và áp dụng keyset position cho chữ ký này.

Nếu cấu hình scrolling là tùy chọn, cần tách phạm vi đăng ký repository tương ứng. Một cờ tắt service không đủ nếu repository method không được hỗ trợ vẫn bị scan và khởi tạo.

Trong cấu hình dùng nhiều package scan, bảo đảm một scan rộng khác không vô tình đăng ký lại nhánh tùy chọn.

Không đánh dấu repository scrolling thật bằng NoRepositoryBean rồi coi đó là một implementation hoạt động; annotation đó chỉ loại nó khỏi đích tạo repository bean riêng.

## 11. Duyệt keyset từ initial position

Ví dụ xử lý nội bộ:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void visitBooks() {
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<CatalogRow> window =
                scrolling.findFirst2ByCategoryOrderByCreatedAtDescIdDesc(
                        "book",
                        position);

        if (window.isEmpty()) {
            break;
        }

        for (CatalogRow row : window.getContent()) {
            processOne(row);
        }

        if (!window.hasNext()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Đoạn mã giả định scrolling được inject và processOne đã được định nghĩa.

Expected windows trên fixture tĩnh:

```text
Window 1:
    105, 104
    hasNext = true

Window 2:
    103, 102
    hasNext = true

Window 3:
    101
    hasNext = false
```

Vị trí tiếp tục là vị trí sau phần tử cuối đã đọc, không phải chỉ số trang mới.

Không gọi positionAt(-1) trên window rỗng. Không lấy vị trí từ một phần tử chưa xử lý rồi coi đó là checkpoint hoàn tất.

### Nếu chọn offset scrolling

Window cũng có thể được dùng với offset position khi module hỗ trợ. Nó vẫn là scrolling theo offset, không trở thành keyset chỉ vì kiểu kết quả là Window.

Phải phân biệt initial offset position với position trỏ tới offset cụ thể. Vì position có tính exclusive, không mặc định ScrollPosition.offset() và ScrollPosition.offset(0) bắt đầu cùng một chỗ.

## 12. Hiểu điều kiện tiếp tục và index

Với createdAt DESC, id DESC, continuation sau khóa T, I có dạng khái niệm:

```sql
WHERE category = :category
  AND (
      created_at < :last_created_at
      OR (
          created_at = :last_created_at
          AND id < :last_id
      )
  )
ORDER BY created_at DESC, id DESC
```

Phần giới hạn kết quả cần theo cú pháp backend; framework của module thực hiện việc chuyển đổi khi query hỗ trợ.

Một index để đánh giá trên database phù hợp có thể là:

```sql
CREATE INDEX idx_catalog_category_created_id
ON catalog_item (category, created_at DESC, id DESC);
```

Đây là ví dụ thiết kế, không phải bằng chứng index chắc chắn tối ưu cho mọi workload.

Cần quan sát execution plan, độ chọn lọc của category và các điều kiện khác. Nếu có tenant, phải đưa tenant vào predicate truy cập thực tế và đánh giá index tương ứng.

Sort động theo price có thể cần chiến lược index khác với scrolling theo createdAt. Không giả định một index đáp ứng tốt mọi tiêu chí mà endpoint cho phép.

## 13. Đưa scrolling ra HTTP mà không lộ hợp đồng nội bộ

Endpoint cursor có thể có hình dạng:

```text
GET /catalog/scroll?category=book

GET /catalog/scroll?category=book&cursor=opaque-token
```

Response minh họa window đầu:

```json
{
  "items": [
    {"id": 105, "title": "E", "price": 40.00},
    {"id": 104, "title": "D", "price": 30.00}
  ],
  "hasNext": true,
  "nextCursor": "opaque-token"
}
```

Adapter HTTP phải:

1. Dùng initial keyset position khi không có cursor.
2. Giải mã hoặc tra cứu cursor theo hợp đồng của ứng dụng.
3. Xác nhận cursor phù hợp category và sort cố định.
4. Gọi repository bằng vị trí được chấp nhận.
5. Lấy position từ phần tử cuối khi cần tạo cursor tiếp.
6. Trả nextCursor rỗng hoặc không có theo quy tắc đã công bố khi hết dữ liệu.

Không serialize ScrollPosition tùy ý rồi coi đó là định dạng API bền vững.

Cursor cần ràng buộc với query, phiên bản định dạng và phạm vi truy cập liên quan. Có thể dùng token tham chiếu phía server hoặc token có kiểm tra tính toàn vẹn. Base64 đơn thuần không bảo đảm dữ liệu token chưa bị sửa.

Cursor không thay thế authorization. Mọi request vẫn phải áp dụng điều kiện tenant và quyền truy cập từ nguồn đáng tin cậy.

Trong bài thực hành, codec cursor là một phần cần triển khai và kiểm tra ở adapter; vòng lặp nội bộ ở phần trước không tự hoàn thành endpoint HTTP này.

## 14. Integration test cho nhánh tham chiếu

Nhóm test dưới đây dành cho cấu hình JPA đã xác nhận hỗ trợ cả repository đọc và scrolling. Với nhánh không hỗ trợ scrolling, tách các test Window khỏi nhóm baseline và không đăng ký repository đó.

Khung fixture:

```java
import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("catalog-repository-test")
@Transactional
class CatalogPaginationTest {

    @Autowired
    CatalogReadRepository reads;

    @Autowired
    CatalogScrollRepository scrolling;

    @Autowired
    EntityManager entityManager;

    private final Sort priceOrder = Sort.by(
            Sort.Order.asc("price"),
            Sort.Order.asc("id"));

    @BeforeEach
    void seed() {
        entityManager.createQuery(
                "delete from CatalogItem")
                .executeUpdate();
        entityManager.clear();

        persist(105L, "book", "E", "40.00", "2026-01-03");
        persist(102L, "book", "B", "20.00", "2026-01-01");
        persist(201L, "accessory", "Other", "1.00", "2026-01-04");
        persist(101L, "book", "A", "10.00", "2026-01-01");
        persist(104L, "book", "D", "30.00", "2026-01-02");
        persist(103L, "book", "C", "20.00", "2026-01-02");

        entityManager.flush();
        entityManager.clear();
    }

    private void persist(
            Long id,
            String category,
            String title,
            String price,
            String date) {

        entityManager.persist(new CatalogItem(
                id,
                category,
                title,
                new BigDecimal(price),
                Instant.parse(date + "T00:00:00Z")));
    }

    @Test
    void previewUsesFilterAndStableSort() {
        var rows = reads.findTop5ByCategory(
                "book",
                priceOrder);

        assertThat(rows)
                .extracting(CatalogRow::getId)
                .containsExactly(101L, 102L, 103L, 104L, 105L);
    }

    @Test
    void middlePageHasExpectedContentAndTotal() {
        Page<CatalogRow> page = reads.findByCategory(
                "book",
                PageRequest.of(1, 2, priceOrder));

        assertThat(page.getContent())
                .extracting(CatalogRow::getId)
                .containsExactly(103L, 104L);

        assertThat(page.getNumber()).isEqualTo(1);
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getTotalElements()).isEqualTo(5);
        assertThat(page.getTotalPages()).isEqualTo(3);
    }

    @Test
    void finalSliceHasNoNextSlice() {
        var slice = reads.findAllByCategory(
                "book",
                PageRequest.of(2, 2, priceOrder));

        assertThat(slice.getContent())
                .extracting(CatalogRow::getId)
                .containsExactly(105L);

        assertThat(slice.hasNext()).isFalse();
    }

    @Test
    void emptyPageBeyondTheEndKeepsTotal() {
        var page = reads.findByCategory(
                "book",
                PageRequest.of(3, 2, priceOrder));

        assertThat(page.getContent()).isEmpty();
        assertThat(page.getTotalElements()).isEqualTo(5);
        assertThat(page.getTotalPages()).isEqualTo(3);
    }
}
```

Profile kiểm thử phải trỏ tới database riêng, schema phù hợp và dữ liệu được cô lập. Không dùng phần xóa fixture với dữ liệu ứng dụng thật.

Flush rồi clear làm query đọc lại dữ liệu thay vì chỉ quan sát các object đang có trong persistence context.

Các ví dụ kiểm tra query trong transaction test. Chúng không tự xác minh hành vi giữa nhiều request có cập nhật đồng thời.

## 15. Kiểm tra Window không lặp, không thiếu trên dữ liệu tĩnh

Thêm test sau vào lớp của nhánh hỗ trợ scrolling:

```java
@Test
void keysetWindowsVisitEveryMatchingItemOnce() {
    java.util.List<Long> ids =
            new java.util.ArrayList<>();

    ScrollPosition position = ScrollPosition.keyset();

    int windowsRead = 0;

    while (true) {
        Window<CatalogRow> window =
                scrolling.findFirst2ByCategoryOrderByCreatedAtDescIdDesc(
                        "book",
                        position);

        windowsRead++;

        assertThat(windowsRead)
                .as("Scrolling must make progress")
                .isLessThanOrEqualTo(4);

        if (window.isEmpty()) {
            break;
        }

        assertThat(window.size()).isLessThanOrEqualTo(2);

        window.getContent().stream()
                .map(CatalogRow::getId)
                .forEach(ids::add);

        if (!window.hasNext()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }

    assertThat(ids)
            .containsExactly(105L, 104L, 103L, 102L, 101L);

    assertThat(ids).doesNotHaveDuplicates();
}
```

Giới hạn số vòng trong test giúp phát hiện continuation không tiến triển thay vì để test chạy vô hạn. Expected result vẫn đến từ fixture, không được tạo bằng chính query đang kiểm tra.

Cần bổ sung các trường hợp:

- Category không có kết quả.
- Tập khớp có đúng một window đầy.
- Nhiều bản ghi cùng createdAt.
- Cursor không hợp lệ.
- Cursor dùng lại với category khác.
- Cursor hết hạn nếu ứng dụng có quy tắc hết hạn.
- Nhánh không hỗ trợ scrolling không vô tình đăng ký query Window.

Trong test cursor ở tầng HTTP, dùng codec thật hoặc adapter được kiểm tra riêng. Một mock codec luôn trả initial position không xác minh được continuation.

## 16. Kiểm thử web và validation tách khỏi repository

Integration test repository không kiểm tra query parameter hoặc JSON HTTP.

Nhóm kiểm thử web cần xác nhận:

| Request hoặc kết quả | Assertion quan trọng |
|---|---|
| Không có page/size | Dùng default đã công bố |
| Page âm, size bằng 0 hoặc vượt 100 | Bị xử lý đúng trước khi truy vấn |
| Sort property không được cho phép | Không chuyển chuỗi tùy ý xuống repository |
| Sort price ASC | Service nhận thêm id ASC |
| Trang cuối chỉ có một phần tử | size vẫn giữ kích thước yêu cầu |
| Không có kết quả | items là array rỗng |
| Trang vượt phạm vi | total của Page không bị đặt lại bằng 0 |
| Slice | Không có metadata total giả |
| Cursor request | Không cho đổi sort hoặc filter trái hợp đồng |
| Nhánh không có scrolling | API thể hiện khả năng thực tế theo thiết kế |

Nếu dùng Spring Data web resolver, cần kiểm tra cấu hình thật. Resolver có thể chuẩn hóa một số đầu vào thay vì tự trả HTTP 400; chính sách từ chối của ứng dụng phải được thực thi ở vị trí phù hợp.

MockMvc hoặc công cụ web tương ứng giúp kiểm tra binding và response. Gọi trực tiếp method service với PageRequest tự tạo không xác minh được bước chuyển query parameter.

## 17. So sánh chi phí của các nhánh

Với cùng category và dữ liệu đại diện, quan sát:

- Query lấy nội dung.
- Công việc xác định total của Page.
- Offset khi page index tăng.
- Keyset predicate của Window.
- Số trường được projection lấy.
- Thời gian giữ connection và bộ nhớ.

Các kết luận cần tránh:

```text
Page luôn chạy đúng hai query.
Slice luôn nhanh ở mọi độ sâu.
Window luôn là keyset.
Projection luôn chỉ đọc đúng vài cột.
Page size nhỏ nghĩa backend chỉ xử lý vài bản ghi.
```

Page có thể tối ưu bỏ count trong một số trường hợp. Slice dùng PageRequest vẫn có offset. Window dùng offset vẫn có thể chịu chi phí bỏ qua nhiều phần tử.

Keyset với index phù hợp có thể cải thiện duyệt sâu, nhưng không thay thế việc xem execution plan và điều kiện lọc.

Không lấy một phép đo trên sáu bản ghi fixture để kết luận hiệu năng production. Fixture nhỏ phục vụ tính đúng; workload lớn và đại diện phục vụ đánh giá chi phí.

## 18. Dữ liệu thay đổi và checkpoint

Các expected order trong bài dựa trên tập dữ liệu tĩnh.

Khi dữ liệu thay đổi:

- Insert/delete trước offset có thể làm phần tử dịch trang.
- Sửa createdAt có thể làm phần tử đổi vị trí trong keyset order.
- Query count và content có thể quan sát các trạng thái khác nhau.
- Cursor cũ có thể không còn phù hợp với filter hoặc quyền truy cập hiện tại.

Nếu dùng scrolling cho job có tác dụng phụ, cần xác định checkpoint biểu diễn điều gì:

```text
Đã đọc tới đây
```

khác với:

```text
Đã xử lý và ghi nhận bền vững tới đây
```

Tiến trình dừng sau xử lý nhưng trước checkpoint có thể khiến phần tử được xử lý lại. Window không tự cung cấp bảo đảm đúng một lần.

Nếu cần tập dữ liệu cố định, phải thiết kế snapshot, mốc chặn hoặc cơ chế chọn công việc phù hợp với backend và nghiệp vụ. Một khóa sort duy nhất không tự tạo snapshot.

## 19. Tiêu chí hoàn thành bài thực hành

Bài được hoàn thành khi bạn có thể chứng minh:

- Các trường sort chỉ được chọn từ hợp đồng cho phép.
- Query có khóa phụ để xử lý giá trị trùng nhau.
- Page giữ đúng total và metadata ở các trang biên.
- Slice có hasNext đúng mà không tạo total giả.
- Preview có giới hạn rõ ràng.
- Nhánh Window chỉ được đăng ký ở cấu hình hỗ trợ.
- Initial position và continuation được sử dụng đúng.
- Duyệt hết fixture tĩnh không lặp, không thiếu và có kết thúc.
- Cursor HTTP được xử lý theo ngữ cảnh query và quyền truy cập.
- Có kiểm thử ở cả tầng web và repository cho trách nhiệm tương ứng.
- Phần đánh giá hiệu năng phân biệt count, offset và keyset.

Không cần dùng mọi abstraction cho cùng một endpoint. Mỗi nhánh tồn tại để đáp ứng một nhu cầu client cụ thể.

## 20. Những điều cần nắm vững

Sort xác định thứ tự. Page phục vụ nhu cầu tổng số. Slice cung cấp nội dung và khả năng đi tiếp. Window biểu diễn nhóm kết quả cùng vị trí scrolling, còn hiệu quả duyệt sâu phụ thuộc chiến lược offset hay keyset và khả năng store.

Một bài thực hành hoàn chỉnh cần gắn các abstraction với validation, DTO, query thực và các trường hợp biên. Chọn đúng khả năng được hỗ trợ quan trọng hơn việc làm mọi repository có cùng một danh sách phương thức.
