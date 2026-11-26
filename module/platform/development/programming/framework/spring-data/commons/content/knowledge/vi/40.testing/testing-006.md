# Kiểm thử Page, Slice, Sort, Limit và trường hợp kết quả rỗng

## Mục tiêu và phạm vi

Trong Spring Data Commons, `Page`, `Slice`, `Sort`, `Pageable` và `Limit` mô tả những hợp đồng truy xuất khác nhau. Kiểm thử đúng cần xác nhận cả dữ liệu trả về lẫn ý nghĩa của metadata, thay vì chỉ kiểm tra danh sách không rỗng.

Sau bài học này, bạn có thể:

- Thiết kế dữ liệu kiểm thử phát hiện sai offset, sai thứ tự và sai giới hạn.
- Phân biệt metadata của `Page` với thông tin điều hướng của `Slice`.
- Kiểm tra sắp xếp nhiều trường và xử lý các giá trị trùng nhau.
- Kiểm tra giới hạn hữu hạn, không giới hạn và kết quả ít hơn giới hạn.
- Phân biệt tập kết quả rỗng với một trang rỗng nằm ngoài phạm vi.
- Tách kiểm thử logic ứng dụng khỏi kiểm thử tích hợp repository của từng store.

Ví dụ tích hợp dùng Spring Data JPA để minh họa. Các abstraction thuộc Commons nhưng việc tạo truy vấn, áp dụng giới hạn, sắp xếp null, collation và hỗ trợ từng chữ ký repository thuộc module store. Chỉ áp dụng ví dụ khi bộ thư viện của dự án có `Limit` và store hỗ trợ chữ ký tương ứng.

## 1. Xác định hợp đồng cần quan sát

| Kiểu hoặc tham số | Điều cần kiểm tra | Điều không nên tự suy ra |
|---|---|---|
| `Page<T>` | Nội dung, số trang yêu cầu, kích thước, tổng số phần tử và số trang | Mọi lần gọi luôn chạy đúng hai query |
| `Slice<T>` | Nội dung và khả năng có lát tiếp theo | Có sẵn tổng số phần tử hoặc tổng số trang |
| `Sort` | Thứ tự theo property và hướng sắp xếp | Thứ tự luôn xác định khi các khóa sắp xếp trùng nhau |
| `Pageable` | Page index, page size, offset và sort được truyền đúng | Page index bắt đầu từ 1 |
| `Limit` | Số phần tử tối đa khi có giới hạn | Mang theo offset, tổng số hoặc metadata trang |
| Kết quả rỗng | Nội dung rỗng và metadata đúng với nguyên nhân rỗng | Mọi kết quả rỗng đều có tổng số bằng 0 |

Một kiểm thử chỉ dùng `assertThat(result).isNotNull()` gần như không xác nhận được các hợp đồng trên.

Với truy vấn trả collection, `Page` hoặc `Slice`, hãy kiểm tra biểu diễn rỗng mà repository cam kết. Không dùng `null` thay cho một tập rỗng trong mock rồi coi đó là hành vi chuẩn của repository.

## 2. Chọn đúng tầng kiểm thử

### 2.1. Unit test cho logic của ứng dụng

Dùng mock repository để kiểm tra các trách nhiệm như:

- Service tạo đúng `PageRequest`.
- Page index từ HTTP được chuyển về quy ước nội bộ đúng.
- Các trường được phép sắp xếp đã được kiểm tra.
- DTO giữ đúng metadata của một `Page`.
- Ứng dụng xử lý trang rỗng mà vẫn giữ tổng số phần tử.
- Giới hạn đầu vào không hợp lệ bị từ chối theo quy tắc ứng dụng.

Mock không xác minh derived query, SQL, offset ở database hoặc store có hỗ trợ `Limit` hay không.

### 2.2. Integration test cho repository thực

Dùng repository được framework tạo cùng backend kiểm thử để xác nhận:

- Điều kiện lọc đúng.
- Phân trang và sắp xếp được thực thi đúng.
- Metadata phản ánh dữ liệu thực.
- Giới hạn không làm trả dư phần tử.
- Mapping và kiểu kết quả hoạt động với store đã chọn.

Đối với hành vi phụ thuộc backend như null ordering, phân biệt hoa thường hoặc query đặc thù, cần môi trường tương ứng với backend mục tiêu. Database thay thế trong bộ nhớ không tự chứng minh hành vi của database khác.

### 2.3. Không kiểm thử lại framework một cách rời rạc

Tạo `PageImpl` rồi kiểm tra getter của chính nó thường không xác minh logic ứng dụng. `PageImpl` hữu ích làm dữ liệu đầu vào cho một test mapping hoặc response thực sự.

Tương tự, xác nhận `Sort.by("price")` chứa property `price` chưa chứng minh repository sắp xếp theo giá. Hãy kiểm tra kết quả của truy vấn thực ở tầng tích hợp.

## 3. Dữ liệu kiểm thử phải tạo được khác biệt

Dùng bộ dữ liệu sau:

| ID | Tên | Category | Giá |
|---|---|---|---:|
| 101 | Cable | accessory | 10.00 |
| 102 | Mouse | accessory | 20.00 |
| 103 | Stand | accessory | 20.00 |
| 104 | Hub | accessory | 30.00 |
| 105 | Charger | accessory | 40.00 |
| 201 | Notebook | stationery | 5.00 |

Các đặc điểm được chọn có chủ đích:

- Năm phần tử khớp `accessory` tạo được trang đầu, giữa và cuối với page size bằng 2.
- Giá của ID 102 và 103 bằng nhau, giúp kiểm tra khóa phụ.
- ID 201 có giá nhỏ hơn các sản phẩm khác nhưng thuộc category khác, giúp phát hiện lỗi thiếu điều kiện lọc.
- Giá trị ID được kiểm soát để expected result rõ ràng.
- Số phần tử không chia hết cho kích thước trang, giúp kiểm tra trang cuối thiếu phần tử.

Với sort `price ASC, id ASC`, thứ tự mong đợi là:

```text
101, 102, 103, 104, 105
```

Không lấy thứ tự insert làm expected order. Khi query không có `ORDER BY` hoặc cơ chế sắp xếp tương đương của store, không nên dựa vào thứ tự vật lý của bản ghi.

## 4. Model và repository cho ví dụ JPA

Entity tối thiểu dùng riêng cho ví dụ:

```java
import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "paging_product")
public class PagingProduct {

    @Id
    private Long id;

    private String name;
    private String category;
    private BigDecimal price;

    protected PagingProduct() {
    }

    public PagingProduct(
            Long id,
            String name,
            String category,
            BigDecimal price) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
```

Repository:

```java
import java.util.List;

import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<PagingProduct, Long> {

    Page<PagingProduct> findByCategory(
            String category,
            Pageable pageable);

    Slice<PagingProduct> findAllByCategory(
            String category,
            Pageable pageable);

    List<PagingProduct> findByCategory(
            String category,
            Sort sort);

    List<PagingProduct> findByCategory(
            String category,
            Sort sort,
            Limit limit);
}
```

Các phương thức truy vấn cùng property `category`, nhưng thể hiện những hợp đồng kết quả khác nhau. Tên `findAllByCategory` được dùng để có chữ ký riêng cho phương thức trả `Slice`.

Không truyền đồng thời `Pageable` với `Sort` hoặc `Limit` vào cùng một query method theo cách trùng trách nhiệm. `Pageable` đã mang thông tin phân trang và có thể mang sort. Hãy xác định chữ ký hợp lệ theo module đang dùng.

## 5. Khung integration test và fixture

Ví dụ dùng JUnit Jupiter, AssertJ và Spring Boot test context. Profile `repository-test` phải được cấu hình trỏ tới database kiểm thử riêng, có schema phù hợp. Các annotation dưới đây không tự tạo cấu hình database đó.

Đây là ví dụ giáo trình; khi áp dụng vào dự án, dùng cơ chế khởi tạo context và backend kiểm thử đã được dự án lựa chọn.

```java
import java.math.BigDecimal;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("repository-test")
@Transactional
class ProductRepositoryPagingTest {

    @Autowired
    ProductRepository products;

    @Autowired
    EntityManager entityManager;

    private final Sort stableSort = Sort.by(
            Sort.Order.asc("price"),
            Sort.Order.asc("id"));

    @BeforeEach
    void seed() {
        products.deleteAllInBatch();
        entityManager.clear();

        persist(105L, "Charger", "accessory", "40.00");
        persist(102L, "Mouse", "accessory", "20.00");
        persist(201L, "Notebook", "stationery", "5.00");
        persist(101L, "Cable", "accessory", "10.00");
        persist(104L, "Hub", "accessory", "30.00");
        persist(103L, "Stand", "accessory", "20.00");

        entityManager.flush();
        entityManager.clear();
    }

    private void persist(
            Long id,
            String name,
            String category,
            String price) {

        entityManager.persist(new PagingProduct(
                id,
                name,
                category,
                new BigDecimal(price)));
    }

    @Test
    void firstPageHasExpectedContentAndMetadata() {
        Page<PagingProduct> page = products.findByCategory(
                "accessory",
                PageRequest.of(0, 2, stableSort));

        assertThat(page.getContent())
                .extracting(PagingProduct::getId)
                .containsExactly(101L, 102L);

        assertThat(page.getNumber()).isZero();
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getNumberOfElements()).isEqualTo(2);
        assertThat(page.getTotalElements()).isEqualTo(5);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.isFirst()).isTrue();
        assertThat(page.isLast()).isFalse();
        assertThat(page.hasPrevious()).isFalse();
        assertThat(page.hasNext()).isTrue();
    }
}
```

Các phương thức kiểm thử ở phần sau được thêm vào cùng lớp này, dùng chung fixture và `stableSort`.

Lệnh xóa fixture chỉ dành cho database kiểm thử đã cô lập. Không chạy lớp test với cấu hình kết nối dữ liệu thật của ứng dụng.

### Vì sao flush rồi clear?

Trong ví dụ JPA:

- Flush làm dữ liệu fixture được đồng bộ xuống database trong transaction hiện tại.
- Clear loại các entity khỏi persistence context.
- Các query sau đó đọc lại dữ liệu theo truy vấn đang kiểm tra, giảm việc vô tình chỉ quan sát trạng thái object đã có trong bộ nhớ.

Flush không phải commit. Các kiểm thử trên xác minh truy vấn trong transaction kiểm thử, không tự chứng minh hành vi sau commit, khóa cạnh tranh hoặc kết nối giữa nhiều transaction.

Đối với store khác, cần dùng cách chuẩn bị và cô lập dữ liệu tương ứng; không mang `EntityManager` sang mọi module.

## 6. Kiểm thử Page ở đầu, giữa và cuối

Với năm phần tử và page size bằng 2:

| Page index | Nội dung mong đợi | Number of elements | Has previous | Has next |
|---:|---|---:|---|---|
| 0 | 101, 102 | 2 | false | true |
| 1 | 103, 104 | 2 | true | true |
| 2 | 105 | 1 | true | false |

Page index của `PageRequest` bắt đầu từ 0. Với các trang trên, total elements là 5 và total pages là 3.

Ví dụ trang giữa:

```java
@Test
void middlePageUsesTheCorrectOffset() {
    Page<PagingProduct> page = products.findByCategory(
            "accessory",
            PageRequest.of(1, 2, stableSort));

    assertThat(page.getContent())
            .extracting(PagingProduct::getId)
            .containsExactly(103L, 104L);

    assertThat(page.getNumber()).isEqualTo(1);
    assertThat(page.getSize()).isEqualTo(2);
    assertThat(page.getNumberOfElements()).isEqualTo(2);
    assertThat(page.getTotalElements()).isEqualTo(5);
    assertThat(page.getTotalPages()).isEqualTo(3);
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isTrue();
}
```

Ví dụ trang cuối:

```java
@Test
void lastPageCanContainFewerItemsThanThePageSize() {
    Page<PagingProduct> page = products.findByCategory(
            "accessory",
            PageRequest.of(2, 2, stableSort));

    assertThat(page.getContent())
            .extracting(PagingProduct::getId)
            .containsExactly(105L);

    assertThat(page.getSize()).isEqualTo(2);
    assertThat(page.getNumberOfElements()).isEqualTo(1);
    assertThat(page.getTotalElements()).isEqualTo(5);
    assertThat(page.getTotalPages()).isEqualTo(3);
    assertThat(page.isLast()).isTrue();
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isFalse();
}
```

`getSize()` biểu diễn kích thước trang, còn `getNumberOfElements()` biểu diễn số phần tử thực có trên trang. Không thay thế hai giá trị này cho nhau khi tạo response.

## 7. Hai loại Page rỗng cần kiểm thử riêng

### 7.1. Không có bản ghi nào khớp điều kiện

```java
@Test
void unmatchedCategoryHasZeroTotal() {
    Page<PagingProduct> page = products.findByCategory(
            "missing",
            PageRequest.of(0, 2, stableSort));

    assertThat(page.getContent()).isEmpty();
    assertThat(page.hasContent()).isFalse();
    assertThat(page.getNumber()).isZero();
    assertThat(page.getSize()).isEqualTo(2);
    assertThat(page.getNumberOfElements()).isZero();
    assertThat(page.getTotalElements()).isZero();
    assertThat(page.getTotalPages()).isZero();
    assertThat(page.hasPrevious()).isFalse();
    assertThat(page.hasNext()).isFalse();
}
```

### 7.2. Có dữ liệu nhưng yêu cầu trang vượt phạm vi

```java
@Test
void pageBeyondTheEndIsEmptyButKeepsTheTotal() {
    Page<PagingProduct> page = products.findByCategory(
            "accessory",
            PageRequest.of(3, 2, stableSort));

    assertThat(page.getContent()).isEmpty();
    assertThat(page.hasContent()).isFalse();
    assertThat(page.getNumber()).isEqualTo(3);
    assertThat(page.getSize()).isEqualTo(2);
    assertThat(page.getNumberOfElements()).isZero();
    assertThat(page.getTotalElements()).isEqualTo(5);
    assertThat(page.getTotalPages()).isEqualTo(3);
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isFalse();
}
```

Điểm khác biệt quan trọng:

```text
Không có kết quả khớp:
    content = []
    totalElements = 0

Trang vượt phạm vi:
    content = []
    totalElements = 5
```

Nếu service thấy content rỗng rồi tạo một response có total bằng 0, nó sẽ làm sai trường hợp thứ hai.

Ứng dụng có thể chọn từ chối trang vượt phạm vi hoặc trả trang rỗng. Đó là hợp đồng ở lớp ứng dụng; kiểm thử cần xác nhận lựa chọn đó và không gán nhầm nó thành lỗi “không có dữ liệu trong toàn bộ tập”.

## 8. Kiểm thử Slice bằng nội dung và khả năng đi tiếp

`Slice` không cung cấp tổng số phần tử. Mục tiêu thường là biết có thể yêu cầu lát tiếp theo hay không.

```java
@Test
void firstSliceReportsThatMoreDataExists() {
    Slice<PagingProduct> slice = products.findAllByCategory(
            "accessory",
            PageRequest.of(0, 2, stableSort));

    assertThat(slice.getContent())
            .extracting(PagingProduct::getId)
            .containsExactly(101L, 102L);

    assertThat(slice.getNumber()).isZero();
    assertThat(slice.getSize()).isEqualTo(2);
    assertThat(slice.getNumberOfElements()).isEqualTo(2);
    assertThat(slice.isFirst()).isTrue();
    assertThat(slice.hasPrevious()).isFalse();
    assertThat(slice.hasNext()).isTrue();
}
```

Lát cuối:

```java
@Test
void finalSliceReportsNoMoreData() {
    Slice<PagingProduct> slice = products.findAllByCategory(
            "accessory",
            PageRequest.of(2, 2, stableSort));

    assertThat(slice.getContent())
            .extracting(PagingProduct::getId)
            .containsExactly(105L);

    assertThat(slice.getNumberOfElements()).isEqualTo(1);
    assertThat(slice.hasPrevious()).isTrue();
    assertThat(slice.hasNext()).isFalse();
    assertThat(slice.isLast()).isTrue();
}
```

Kết quả không khớp:

```java
@Test
void emptySliceHasNoNextSlice() {
    Slice<PagingProduct> slice = products.findAllByCategory(
            "missing",
            PageRequest.of(0, 2, stableSort));

    assertThat(slice.getContent()).isEmpty();
    assertThat(slice.getNumberOfElements()).isZero();
    assertThat(slice.hasPrevious()).isFalse();
    assertThat(slice.hasNext()).isFalse();
}
```

Không gọi hoặc giả lập metadata tổng số như thể đó là hợp đồng của `Slice`. Nếu giao diện cần tổng số trang, việc đổi từ `Page` sang `Slice` phải đi kèm thay đổi hợp đồng ứng dụng.

### Vì sao phải có trường hợp đủ đúng một lát?

Một lát có đúng hai phần tử chưa chứng minh còn lát tiếp theo. Nếu toàn bộ tập chỉ có hai phần tử, `hasNext()` phải là false.

Các implementation hỗ trợ Slice thường có thể đọc thêm một phần tử để nhận biết còn dữ liệu, nhưng không nên cố định thuật toán nội bộ đó thành hợp đồng chung cho mọi store.

## 9. Ma trận số lượng quanh biên page size

Gọi page size hoặc slice size là `k`, với `k > 0`. Bộ trường hợp hữu ích gồm:

| Số phần tử khớp N | Nội dung trang/lát đầu | Has next |
|---:|---:|---|
| 0 | 0 phần tử | false |
| 1 | 1 phần tử | false nếu k lớn hơn hoặc bằng 1 |
| k - 1 | k - 1 phần tử, với k lớn hơn 1 | false |
| k | k phần tử | false |
| k + 1 | k phần tử | true |
| 2k | k phần tử ở trang đầu | true; trang thứ hai đầy nhưng không có trang tiếp |
| 2k + 1 | k phần tử ở trang đầu | true; có trang cuối chỉ một phần tử |

Khi chọn `k = 2`, một số giá trị N trùng nhau; không cần tạo các test trùng chỉ vì tên hàng khác nhau. Điều cần giữ là đủ các hành vi khác biệt.

Ví dụ xác nhận một lát đầy vẫn có thể là lát cuối:

```java
@Test
void aFullSliceCanStillBeTheLastSlice() {
    persist(301L, "A", "exact", "1.00");
    persist(302L, "B", "exact", "2.00");
    persist(303L, "C", "exact", "3.00");
    persist(304L, "D", "exact", "4.00");
    entityManager.flush();
    entityManager.clear();

    Slice<PagingProduct> slice = products.findAllByCategory(
            "exact",
            PageRequest.of(1, 2, stableSort));

    assertThat(slice.getContent())
            .extracting(PagingProduct::getId)
            .containsExactly(303L, 304L);

    assertThat(slice.getNumberOfElements()).isEqualTo(2);
    assertThat(slice.hasNext()).isFalse();
}
```

Kiểm thử này phát hiện lỗi ứng dụng suy luận `hasNext = content.size() == pageSize`.

## 10. Kiểm thử Sort phải kiểm tra thứ tự chính xác

### 10.1. Nhiều trường với hướng khác nhau

```java
@Test
void sortUsesDirectionAndSecondaryProperty() {
    Sort sort = Sort.by(
            Sort.Order.desc("price"),
            Sort.Order.asc("id"));

    var result = products.findByCategory(
            "accessory",
            sort);

    assertThat(result)
            .extracting(PagingProduct::getId)
            .containsExactly(
                    105L, 104L, 102L, 103L, 101L);
}
```

Dùng `containsExactly` ở đây vì thứ tự là điều đang kiểm tra. `containsExactlyInAnyOrder` sẽ không phát hiện lỗi đảo thứ tự.

Hai phần tử có cùng giá 20.00 được phân biệt bằng `id ASC`. Nếu chỉ sort theo giá, không nên viết test bắt database luôn trả ID 102 trước ID 103.

### 10.2. Khi chủ động không yêu cầu thứ tự

```java
@Test
void unsortedQueryChecksMembershipWithoutInventingAnOrder() {
    var result = products.findByCategory(
            "accessory",
            Sort.unsorted());

    assertThat(result)
            .extracting(PagingProduct::getId)
            .containsExactlyInAnyOrder(
                    101L, 102L, 103L, 104L, 105L);
}
```

Test này xác nhận đúng tập phần tử và không áp đặt một thứ tự mà query không cam kết.

### 10.3. Những quy tắc cần kiểm tra với store mục tiêu

Nếu nghiệp vụ phụ thuộc vào các trường hợp sau, hãy có fixture và expected result tương ứng:

- Giá trị null đứng đầu hay cuối.
- Phân biệt chữ hoa và chữ thường.
- Dấu tiếng Việt, locale và collation.
- Property lồng nhau.
- Sort trên trường được tính toán hoặc projection.
- Tên property không hợp lệ.

Không mặc định `ignoreCase` hoặc một null handling hint được tất cả backend áp dụng giống nhau. Cũng không cố định một loại exception ở cùng một thời điểm cho mọi module.

Nếu API chỉ cho phép một tập trường sắp xếp, unit test lớp chuyển đổi đầu vào cần xác nhận danh sách cho phép đó. Integration test repository kiểm tra phần dịch sort đã hợp lệ thành hành vi lưu trữ thực tế.

## 11. Kiểm thử tính liên tục giữa các trang

Khi dữ liệu không thay đổi và sort có khóa phân biệt ổn định, các trang liên tiếp phải ghép thành đúng tập đã sắp xếp.

```java
@Test
void consecutivePagesHaveNoGapOrDuplicateForStableData() {
    java.util.List<Long> actual = new java.util.ArrayList<>();

    for (int pageNumber = 0; pageNumber < 3; pageNumber++) {
        Page<PagingProduct> page = products.findByCategory(
                "accessory",
                PageRequest.of(pageNumber, 2, stableSort));

        page.getContent().stream()
                .map(PagingProduct::getId)
                .forEach(actual::add);
    }

    assertThat(actual)
            .containsExactly(101L, 102L, 103L, 104L, 105L);

    assertThat(actual).doesNotHaveDuplicates();
}
```

Điều kiện “dữ liệu không thay đổi” rất quan trọng. Với offset pagination, dữ liệu được thêm hoặc xóa giữa các lần đọc có thể làm phần tử dịch sang trang khác dù sort đã có khóa phụ.

Một test trên fixture tĩnh không chứng minh tính ổn định khi có cập nhật đồng thời. Nếu sản phẩm cần duyệt dữ liệu đang thay đổi, phải xác định thêm isolation, snapshot hoặc chiến lược scroll/keyset phù hợp với khả năng của store.

## 12. Kiểm thử Limit theo số lượng và thứ tự

`Limit` biểu diễn giới hạn số phần tử, không phải một trang.

### 12.1. Giới hạn nhỏ hơn số kết quả

```java
@Test
void finiteLimitReturnsTheFirstMatchingItemsInRequestedOrder() {
    var result = products.findByCategory(
            "accessory",
            stableSort,
            Limit.of(2));

    assertThat(result)
            .extracting(PagingProduct::getId)
            .containsExactly(101L, 102L);
}
```

Chỉ kiểm tra `size <= 2` chưa đủ. Một implementation bị lỗi trả list rỗng cũng thỏa điều kiện đó. Fixture có đủ dữ liệu cho phép kiểm tra cả số lượng chính xác lẫn những phần tử phải được chọn.

### 12.2. Giới hạn lớn hơn số kết quả

```java
@Test
void finiteLimitDoesNotPadTheResult() {
    var result = products.findByCategory(
            "accessory",
            stableSort,
            Limit.of(10));

    assertThat(result)
            .extracting(PagingProduct::getId)
            .containsExactly(101L, 102L, 103L, 104L, 105L);
}
```

Kết quả chỉ có năm phần tử. Không có khái niệm bù phần tử để đạt giới hạn.

### 12.3. Không giới hạn và kết quả rỗng

```java
@Test
void unlimitedReturnsAllMatchingItems() {
    var result = products.findByCategory(
            "accessory",
            stableSort,
            Limit.unlimited());

    assertThat(result)
            .extracting(PagingProduct::getId)
            .containsExactly(101L, 102L, 103L, 104L, 105L);
}

@Test
void finiteLimitCanReturnAnEmptyList() {
    var result = products.findByCategory(
            "missing",
            stableSort,
            Limit.of(2));

    assertThat(result).isEmpty();
}
```

`Limit.unlimited()` không có nghĩa truy vấn toàn bộ store; điều kiện lọc vẫn phải được áp dụng.

Cũng không dùng `Limit.of(2)` để diễn đạt “trang thứ hai”. Muốn offset hoặc điều hướng trang phải chọn abstraction tương ứng.

### 12.4. Số 0 và số âm thuộc hợp đồng nào?

Không viết test mặc định rằng `Limit.of(0)` hoặc số âm luôn bị constructor của Commons từ chối theo cùng một cách. Abstraction `Limit` không nên được coi là bộ kiểm tra toàn bộ quy tắc đầu vào của ứng dụng; ý nghĩa và khả năng áp dụng còn phụ thuộc thao tác và store.

Nếu API nghiệp vụ yêu cầu giới hạn từ 1 đến một ngưỡng cụ thể, hãy kiểm tra quy tắc đó ở lớp tiếp nhận yêu cầu trước khi tạo truy vấn.

Kiểm thử nên nói rõ: “ứng dụng từ chối limit không dương”, thay vì khẳng định một hành vi validation phổ quát của mọi repository.

Không kết hợp tùy tiện `Top` hoặc `First`, `Pageable` và `Limit` để tạo một test mơ hồ về cơ chế nào chịu trách nhiệm giới hạn. Chọn một hợp đồng rõ ràng cho từng phương thức.

## 13. Kiểm thử unpaged khác với trang có kích thước lớn

`Pageable.unpaged()` biểu diễn không phân trang. Nó không chỉ là một `PageRequest` với kích thước rất lớn.

```java
@Test
void unpagedQueryReturnsAllMatchingItems() {
    Page<PagingProduct> page = products.findByCategory(
            "accessory",
            Pageable.unpaged());

    assertThat(page.getContent())
            .extracting(PagingProduct::getId)
            .containsExactlyInAnyOrder(
                    101L, 102L, 103L, 104L, 105L);

    assertThat(page.getTotalElements()).isEqualTo(5);
}
```

Ví dụ không yêu cầu sort nên chỉ kiểm tra tập phần tử.

Khi viết mã ứng dụng xử lý `Pageable`, hãy kiểm tra `isPaged()` hoặc `isUnpaged()` trước khi dùng các thông tin chỉ có ý nghĩa với phân trang. Không mặc định mọi implementation unpaged cho phép truy cập page number, page size hoặc offset như một request phân trang thông thường.

Không dùng unpaged trên fixture nhỏ để kết luận API có thể tải không giới hạn an toàn ở môi trường thật. Đó là vấn đề tài nguyên và hợp đồng truy xuất cần được xét riêng.

## 14. Kiểm thử mapping DTO mà không làm mất metadata

Một service thường chuyển `Page<Entity>` thành `Page<DTO>`:

```java
Page<ProductRow> result = source.map(product ->
        new ProductRow(
                product.getId(),
                product.getName()));
```

Đoạn mã giả định `ProductRow` là DTO được định nghĩa trong ứng dụng.

Khi logic này thuộc service cần kiểm tra, hãy xác nhận:

- Mỗi entity được chuyển đúng trường.
- Nội dung giữ đúng thứ tự.
- Page number, size và thông tin sort được giữ theo hợp đồng.
- Total elements và total pages không bị tính lại từ số phần tử của trang.
- Trang rỗng vượt phạm vi vẫn giữ total lớn hơn 0.

Lỗi dễ gặp:

```text
source.content.size() = 0
source.totalElements = 5

service tự tạo response:
    items = []
    totalElements = items.size() = 0
```

Unit test cần cho repository mock trả một Page có content rỗng, page request nằm ngoài phạm vi và total bằng 5. Sau đó kiểm tra response của service vẫn giữ total bằng 5.

Nếu dùng `PageImpl` làm fixture, hãy tạo dữ liệu và total phù hợp với tình huống. Constructor của nó có thể điều chỉnh total trong một số trường hợp để giảm bất nhất ở trang cuối; không dựa vào fixture mâu thuẫn rồi quy lỗi cho service.

## 15. Count query và chi phí truy vấn là một hợp đồng riêng

Kiểm thử nội dung và metadata không cần mặc định số câu lệnh database.

Các điểm cần phân biệt:

- `Page` thường cần biết tổng số kết quả, nhưng implementation có thể suy ra total ở một số trường hợp và bỏ qua count query.
- `Slice` thường giúp tránh yêu cầu tổng số, nhưng không phải lời hứa rằng mọi store thực thi đúng một câu lệnh theo cùng thuật toán.
- Một list với `Limit` không có metadata total.
- Một query phức tạp có join hoặc `distinct` cần kiểm tra total không bị đếm sai theo số dòng trung gian.

Nếu dự án có yêu cầu hiệu năng cụ thể, hãy có kiểm thử hoặc quan sát riêng trên store mục tiêu. Nêu rõ bạn đang kiểm tra hợp đồng truy vấn của implementation nào.

Không làm một test chức năng thất bại chỉ vì implementation tối ưu bỏ qua count query trong khi nội dung và metadata vẫn đúng.

Với query khai báo và count query tùy biến, nên có dữ liệu khiến lỗi dễ lộ: nhiều bản ghi liên quan cho cùng một entity, điều kiện lọc loại bớt entity và trang cuối không đầy.

## 16. Cô lập dữ liệu và transaction để kết quả có thể lặp lại

Một test phân trang cần biết chính xác có bao nhiêu phần tử khớp. Dữ liệu còn sót từ test trước có thể làm sai total hoặc `hasNext`.

Các nguyên tắc thực tế:

- Dùng database, schema hoặc namespace dành riêng cho kiểm thử.
- Tạo fixture rõ ràng cho từng test hoặc nhóm test.
- Không phụ thuộc thứ tự chạy test.
- Nếu chạy song song, tránh để hai test cùng xóa hoặc ghi chung fixture.
- Dùng rollback hoặc cleanup phù hợp với mô hình transaction của store.
- Không mặc định rollback test ở một luồng sẽ xóa dữ liệu được ghi bởi HTTP request, thread khác hoặc reactive pipeline độc lập.
- Với store có độ trễ hiển thị dữ liệu, dùng cơ chế chờ theo điều kiện có thời hạn nếu hợp đồng yêu cầu; không dùng một khoảng ngủ cố định để che trạng thái chưa sẵn sàng.

Các ví dụ trong bài dùng transaction kiểm thử JPA. Không sao chép giả định đó sang MongoDB, R2DBC hoặc một hệ thống tìm kiếm mà chưa kiểm tra cơ chế tương ứng.

Nếu muốn xác minh hành vi sau commit hoặc giữa hai transaction độc lập, cần thiết kế test riêng cho ranh giới đó. Một test đang chạy trong transaction bao ngoài không tự kiểm tra được mọi hành vi production.

## 17. Các lỗi assertion cần tránh

| Assertion hoặc cách làm | Vì sao chưa đủ hoặc sai? | Cách kiểm tra phù hợp |
|---|---|---|
| Chỉ kiểm tra result khác null | Không xác nhận dữ liệu, thứ tự hay metadata | Kiểm tra từng phần của hợp đồng |
| Kiểm tra size bằng page size cho mọi trang | Trang cuối có thể thiếu phần tử | Phân biệt size yêu cầu và số phần tử thực |
| Thấy list rỗng thì total phải bằng 0 | Trang vượt phạm vi vẫn có total lớn hơn 0 | Tạo hai test rỗng riêng |
| Dùng any-order cho test sort | Không phát hiện sai thứ tự | Kiểm tra thứ tự ID chính xác |
| Giả định insert order là query order | Backend không cam kết nếu không có sort | Yêu cầu sort hoặc chỉ kiểm tra membership |
| Suy ra hasNext từ việc trang đầy | Trang cuối có thể đầy đúng kích thước | Kiểm tra trường hợp N bằng k và 2k |
| Dùng mock để xác nhận query hỗ trợ Limit | Mock không thực thi query | Có integration test với module store |
| Chỉ kiểm tra số phần tử không vượt limit | Kết quả rỗng sai cũng có thể pass | Kiểm tra đúng các phần tử mong đợi |
| Mặc định Page luôn chạy một count query | Implementation có thể tối ưu | Tách test chức năng với yêu cầu hiệu năng |
| Chuyển Page sang list rồi quên total | Làm mất hợp đồng phân trang | Kiểm tra DTO và metadata của response |

Expected result nên được xác định từ fixture và yêu cầu nghiệp vụ. Không dùng chính phương thức repository đang kiểm tra để tạo expected result, vì cùng một lỗi có thể xuất hiện ở cả hai phía.

## 18. Bài thực hành

Với một repository được store mục tiêu hỗ trợ:

1. Chuẩn bị ít nhất năm bản ghi khớp và một bản ghi không khớp điều kiện.
2. Tạo ít nhất hai bản ghi trùng khóa sắp xếp chính.
3. Kiểm tra trang đầu, giữa và cuối với page size bằng 2.
4. Kiểm tra không có kết quả và yêu cầu trang vượt phạm vi như hai tình huống khác nhau.
5. Kiểm tra Slice với N bằng k và N bằng k + 1.
6. Kiểm tra sort tăng, giảm và khóa phụ.
7. Kiểm tra `Limit.of(1)`, một limit lớn hơn tập kết quả và `Limit.unlimited()`.
8. Kiểm tra một query có Limit nhưng không có bản ghi khớp.
9. Kiểm tra unpaged mà không áp đặt thứ tự chưa được yêu cầu.
10. Viết unit test cho service mapping trang rỗng có total lớn hơn 0.
11. Ghi rõ hành vi nào đã được kiểm tra trên backend thật và hành vi nào chỉ được mock ở lớp ứng dụng.

Với mỗi test, hãy trả lời: nếu implementation bỏ điều kiện lọc, đảo sort, bỏ offset hoặc tính total bằng content size, test nào sẽ thất bại?

## 19. Những điều cần nắm vững

Một bộ kiểm thử tốt cho phân trang và giới hạn cần dữ liệu có chủ đích, thứ tự rõ ràng và assertion phù hợp với từng abstraction.

`Page` cần được kiểm tra cả nội dung và tổng số. `Slice` cần được kiểm tra khả năng đi tiếp, đặc biệt ở biên một lát đầy. `Sort` cần expected order chính xác khi thứ tự được cam kết. `Limit` cần xác nhận phần dữ liệu được chọn, không chỉ số lượng tối đa.

Kết quả rỗng là một phần bình thường của hợp đồng truy vấn. Điều quan trọng là phân biệt vì sao nó rỗng và giữ đúng metadata mà người gọi dựa vào.
