# Page, count, Sort hoặc ScrollPosition trả dữ liệu sai kỳ vọng

## 1. Tách lỗi dữ liệu, metadata và vị trí tiếp tục

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, “phân trang trả sai” có thể chỉ nhiều vấn đề khác nhau:

- Đúng bản ghi nhưng sai thứ tự.
- Đúng nội dung trang nhưng total không đúng.
- Trang đầu bị bỏ qua vì nhầm chỉ số.
- Một bản ghi xuất hiện ở hai trang.
- Scrolling mất phần tử đầu tiên.
- Cursor không tiếp tục đúng khi filter hoặc sort thay đổi.

Các hiện tượng đó cần được kiểm tra tại những lớp khác nhau: yêu cầu đầu vào, query nội dung, query count, thứ tự và trạng thái scrolling.

Một cách phân tích:

~~~text
Filter + page/size hoặc ScrollPosition + Sort
                       |
                       v
             Query thực tế của store
                       |
                       v
        Content + metadata hoặc Window
                       |
                       v
          Mapper / API / giao diện sử dụng
~~~

Đừng bắt đầu bằng cách cộng hoặc trừ một đơn vị trong nhiều lớp cùng lúc. Trước tiên cần ghi nhận giá trị tại đúng ranh giới.

Bài dùng **Java 17 và Spring Data JPA/Commons 3.5** để minh họa. Các khả năng truy vấn, count và scrolling phải được đối chiếu lại khi dùng store hoặc phiên bản khác.

## 2. Đọc đúng metadata của Page

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getNumber()` | Chỉ số trang hiện tại |
| `getSize()` | Kích thước trang được yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại |
| `getTotalElements()` | Tổng số phần tử của tập kết quả phù hợp |
| `getTotalPages()` | Tổng số trang theo metadata hiện có |
| `hasNext()` | Có trang tiếp theo theo metadata hay không |

Ví dụ có 7 kết quả phù hợp, kích thước trang 3:

| Page number | Content kỳ vọng | Number of elements | Total elements | Total pages |
| --- | --- | --- | --- | --- |
| 0 | 3 phần tử đầu | 3 | 7 | 3 |
| 1 | 3 phần tử tiếp | 3 | 7 | 3 |
| 2 | 1 phần tử cuối | 1 | 7 | 3 |

Ở trang cuối, size vẫn có thể là 3 nhưng numberOfElements là 1. Đây không phải lỗi.

Trang vượt phạm vi có thể rỗng dù total vẫn lớn hơn 0. Không dùng riêng `isLast()` để kết luận chỉ số được yêu cầu chính là chỉ số của trang cuối hợp lệ.

`Page` có metadata tổng; `Slice` tập trung vào một phần kết quả cùng khả năng đi tiếp; `Window` cung cấp vị trí để tiếp tục scrolling. Không lấy các kiểu này thay thế nhau mà giữ nguyên mọi kỳ vọng về total.

## 3. Mô hình tái hiện nhỏ và có thứ tự rõ ràng

Các public type sau đặt trong các file Java riêng cùng package `example.feed`. Ứng dụng đã có cấu hình JPA, repository và database test phù hợp.

### 3.1. Entity minh họa

~~~java
package example.feed;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "feed_item")
public class FeedItem {

    @Id
    private Long id;

    @Column(name = "tenant_key", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String status;

    private String title;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected FeedItem() {
    }

    public FeedItem(
            Long id,
            String tenantId,
            String status,
            String title,
            Instant createdAt) {

        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.title = title;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

ID được fixture gán trực tiếp để dễ đối chiếu. Trong ứng dụng khác có thể dùng chiến lược ID khác; yêu cầu là có khóa phân biệt ổn định.

### 3.2. Repository

~~~java
package example.feed;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface FeedRepository
        extends JpaRepository<FeedItem, Long> {

    Page<FeedItem> findByTenantIdAndStatus(
            String tenantId,
            String status,
            Pageable pageable);

    @Query(
            value = """
                    select f
                      from FeedItem f
                     where f.tenantId = :tenantId
                       and f.status = :status
                    """,
            countQuery = """
                    select count(f)
                      from FeedItem f
                     where f.tenantId = :tenantId
                       and f.status = :status
                    """)
    Page<FeedItem> search(
            @Param("tenantId") String tenantId,
            @Param("status") String status,
            Pageable pageable);

    Window<FeedItem>
    findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
            String tenantId,
            String status,
            ScrollPosition position);
}
~~~

Method Page có thể dùng Pageable để nhận sort động. Method Window dùng query derivation, giới hạn ba phần tử và thứ tự cố định.

Không gắn `@Query` dạng chuỗi vào method Window rồi mặc định mọi khả năng scrolling vẫn được hỗ trợ. Phần giới hạn theo module được trình bày ở mục 9.

## 4. Chỉ số trang và offset: xác định nơi chuyển đổi

### 4.1. PageRequest dùng chỉ số từ 0

~~~java
PageRequest.of(0, 20); // Trang đầu
PageRequest.of(1, 20); // Trang thứ hai
~~~

Với PageRequest thông thường:

~~~text
offset = pageNumber × pageSize
~~~

`PageRequest.of(1, 20)` không có nghĩa bắt đầu tại phần tử thứ nhất. Nó yêu cầu trang có chỉ số 1, tương ứng bỏ qua 20 phần tử của tập đã lọc và sắp xếp.

Page number phải không âm và page size phải lớn hơn 0. Xem [PageRequest của Commons 3.5](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/domain/PageRequest.java).

### 4.2. Giao diện đếm từ 1 chỉ nên chuyển đổi một lần

Nếu API công khai chủ ý nhận trang đầu là 1, hãy chuyển sang chỉ số nội bộ tại một ranh giới rõ ràng.

Ví dụ helper nhận số trang của giao diện:

~~~java
package example.feed;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public final class FeedPaging {

    private FeedPaging() {
    }

    public static Pageable fromUi(
            int uiPage,
            int size,
            String sortKey,
            Sort.Direction direction) {

        if (uiPage < 1 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "Trang hoặc kích thước không hợp lệ");
        }

        String property = switch (sortKey) {
            case "created" -> "createdAt";
            case "title" -> "title";
            default -> throw new IllegalArgumentException(
                    "Không hỗ trợ khóa sắp xếp");
        };

        Sort sort = Sort.by(direction, property)
                .and(Sort.by(direction, "id"));

        return PageRequest.of(uiPage - 1, size, sort);
    }
}
~~~

Helper này dành cho đầu vào đếm từ 1 chưa được chuyển đổi. Nếu web argument resolver hoặc lớp khác đã chuyển sang chỉ số từ 0, không trừ thêm lần nữa.

Cũng cần kiểm tra page size thực tế sau khi áp dụng giới hạn của API. Một request size=100 nhưng resolver giới hạn còn 20 có thể làm caller diễn giải sai offset nếu chỉ nhìn request gốc.

### 4.3. Không trộn đơn vị

Những giá trị sau khác nhau:

- Page number: số trang theo quy ước nội bộ.
- Offset: số phần tử bị bỏ qua trong tập kết quả.
- Vị trí scrolling: ranh giới dùng để tiếp tục.
- Chỉ số trong một Window: vị trí cục bộ của phần tử trong Window đó.

Nếu client gửi offset=40, không truyền thẳng 40 vào tham số pageNumber với kỳ vọng lấy từ phần tử 40.

## 5. Count phải đếm cùng một tập logic với content

### 5.1. Kiểm tra lại predicate

Trong method search, query nội dung và countQuery đều có tenantId và status.

Một lỗi thường gặp là query nội dung lọc tenant, trạng thái và quyền hiển thị, nhưng query count chỉ đếm mọi bản ghi của tenant. Content có thể đúng trong khi total quá lớn.

Lập bảng đối chiếu:

| Thành phần | Query content | Query count |
| --- | --- | --- |
| Tenant | Phải tương ứng | Phải tương ứng |
| Trạng thái | Phải tương ứng | Phải tương ứng |
| Điều kiện quyền/visibility | Phải tương ứng | Phải tương ứng |
| Join làm thay đổi tập root | Cần phân tích | Cần phân tích tương ứng |
| Group hoặc distinct | Xác định đơn vị kết quả | Đếm đúng đơn vị đó |
| Sort | Cần cho thứ tự content | Thường không phải điều kiện đếm |

Không lấy repository.count() không có filter làm total cho một query đã lọc, trừ khi đó chính là hợp đồng mong muốn.

### 5.2. Đếm root khác đếm dòng join

Nếu một đối tượng gốc có nhiều bản ghi con, join có thể tạo nhiều dòng cho cùng root.

Khi màn hình hiển thị các root duy nhất, count cần phản ánh số root phù hợp. Một phép đếm dòng join không tự bằng số root đó.

Với query có DISTINCT hoặc GROUP BY, cần xác định rõ “một phần tử” là entity, giá trị khác nhau hay một nhóm. Không suy tên method countDistinct... luôn biểu đạt đúng loại distinct mà nghiệp vụ cần.

Native query phức tạp hoặc query có cấu trúc đặc biệt có thể cần countQuery riêng hay implementation tùy chỉnh. Đừng thay toàn bộ SELECT bằng count(*) một cách máy móc.

### 5.3. Page không luôn chạy COUNT

Có những đường thực thi suy ra total từ content và Pageable để tránh COUNT khi đã đủ thông tin. Việc không thấy COUNT trong log chưa tự chứng minh metadata bị lỗi.

Cơ chế tối ưu có thể xem tại [PageableExecutionUtils](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/support/PageableExecutionUtils.java).

Nếu query join, việc khử trùng hoặc xử lý sau truy vấn làm số phần tử không còn phản ánh đúng hình dạng mà cơ chế phân trang giả định, cần phân tích cả query lẫn bước tạo Page. Không kết luận chỉ từ một trang ngắn.

### 5.4. Đừng tự làm mất metadata khi map

Cách dễ sai:

~~~java
new PageImpl<>(
        mappedContent,
        pageable,
        mappedContent.size());
~~~

Kích thước content của một trang không phải tổng số phần tử phù hợp.

Nếu chỉ chuyển đổi một-một, có thể giữ metadata bằng:

~~~java
Page<FeedCard> cards = page.map(item ->
        new FeedCard(item.getId(), item.getTitle()));
~~~

Ví dụ trên giả định ứng dụng có record `FeedCard(Long id, String title)`.

Nếu lọc bớt phần tử trong Java sau khi query xong, giữ total cũ cũng có thể sai. Điều kiện quyết định tập kết quả nên được biểu đạt ở query hoặc trong thiết kế phân trang phù hợp.

`PageImpl` còn có thể điều chỉnh total dựa vào content của trang cuối để giảm bất nhất; vì vậy total sau khi bọc không phải lúc nào cũng là bản sao nguyên giá trị đầu vào. Xem [API PageImpl](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/domain/PageImpl.html).

## 6. Sort: đúng property, đúng chiều và có khóa phân biệt

### 6.1. Property Java khác tên cột

Entity có property `createdAt` được map sang cột `created_at`. Với query theo domain model, sort thông thường sử dụng:

~~~java
Sort.by("createdAt");
~~~

Không tự đổi thành `Sort.by("created_at")` chỉ vì database dùng tên cột đó.

Với JPQL tùy chỉnh, sort còn có thể tham chiếu alias hợp lệ trong query. Quy tắc không giống việc truyền nguyên một biểu thức SQL tùy ý vào tên property.

### 6.2. Sort cần được gắn vào Pageable thực sự được dùng

Các đối tượng cấu hình thường trả một đối tượng mới khi thay đổi.

~~~java
Sort sort = Sort.by("createdAt").ascending();
sort = sort.and(Sort.by("id").ascending());

Pageable pageable = PageRequest.of(0, 3, sort);
~~~

Nếu tạo một Sort riêng nhưng vẫn gọi repository bằng Pageable cũ không có Sort, query chưa nhận cấu hình mới.

Tương tự, gọi một phương thức tạo PageRequest mới rồi bỏ giá trị trả về không làm request cũ thay đổi.

### 6.3. Khóa bằng nhau cần thứ tự phân biệt

Nếu nhiều bản ghi cùng createdAt, chỉ sort theo createdAt chưa xác định thứ tự giữa chúng.

Một thứ tự rõ ràng cho ví dụ:

~~~java
Sort.by("createdAt").ascending()
        .and(Sort.by("id").ascending());
~~~

ID là khóa phụ phân biệt. Đối với offset pagination, thiếu thứ tự đủ xác định có thể khiến cùng dữ liệu tĩnh vẫn được chia trang khác kỳ vọng.

Sort.unsorted() không có nghĩa backend tự sắp theo ID hoặc thứ tự insert.

### 6.4. Kiểm tra collation, null và biểu thức

Thứ tự chuỗi chịu ảnh hưởng collation và khả năng của store. Dữ liệu có dấu, hoa thường hoặc số nằm trong chuỗi có thể không theo thứ tự mà giao diện đang giả định.

`nullsFirst`, `nullsLast` và ignoreCase cần được đánh giá theo store/query; null handling trong Sort là một chỉ dẫn, không phải bảo đảm mọi backend đều áp dụng giống nhau. Xem [Sort của Commons](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/domain/Sort.java).

JPA có quy tắc kiểm tra property/path và cơ chế `JpaSort.unsafe` cho một số trường hợp biểu thức. Đó không phải cách sửa chung cho tên property sai. Xem [Using Sort của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html#jpa.query-methods.sorting).

## 7. ScrollPosition là ranh giới tiếp tục, không phải số trang

### 7.1. Initial position khác vị trí phần tử đầu

Hai lời gọi có ý nghĩa khác nhau:

~~~java
ScrollPosition.offset();
ScrollPosition.offset(0);
~~~

- `offset()`: vị trí khởi đầu, chưa trỏ đến phần tử cụ thể.
- `offset(0)`: vị trí của phần tử ở offset 0.

Scrolling coi vị trí đã cho là **exclusive**: bắt đầu sau vị trí đó. Vì vậy, dùng offset(0) để mong lấy từ phần tử đầu có thể làm mất phần tử đầu tiên.

| Giá trị | Ý định trong ví dụ |
| --- | --- |
| `ScrollPosition.offset()` | Bắt đầu từ đầu |
| `ScrollPosition.offset(0)` | Tiếp tục sau phần tử đầu |
| `ScrollPosition.keyset()` | Bắt đầu keyset scrolling |
| `window.positionAt(window.size() - 1)` | Vị trí phần tử cuối của Window hiện tại |

Các factory method được mô tả trong [API ScrollPosition](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/domain/ScrollPosition.html).

### 7.2. Lấy vị trí từ Window vừa đọc

Một vòng lặp theo ý nghĩa “xử lý hết Window rồi đi tiếp”:

~~~java
ScrollPosition position = ScrollPosition.offset();

while (true) {
    Window<FeedItem> window = repository
            .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                    "north",
                    "OPEN",
                    position);

    if (window.isEmpty()) {
        break;
    }

    for (FeedItem item : window) {
        consume(item);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
~~~

Đoạn trên giả định repository và hàm consume đã có trong nơi gọi. Nó minh họa việc di chuyển vị trí, không phải cam kết snapshot cho cả quá trình.

Không lấy `positionAt(0)` sau khi đã xử lý cả Window: cửa sổ tiếp theo sẽ bắt đầu sau phần tử đầu, có thể đọc lại những phần tử còn lại vừa xử lý.

Không gọi `positionAt(size - 1)` trên Window rỗng. Và không tự cộng page size vào keyset position như cách tính offset.

Window cung cấp vị trí của phần tử trong kết quả của chính nó; API có thể báo lỗi khi index không hợp lệ hoặc không thể tạo position. Xem [Window của Commons](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/domain/Window.java).

### 7.3. Keyset phải có đủ khóa để xác định ranh giới

Với thứ tự tăng dần theo createdAt rồi id, ranh giới logic sau một phần tử có khóa (t, k) có thể diễn giải:

~~~text
createdAt > t
OR
(createdAt = t AND id > k)
~~~

Các điều kiện tenant/status vẫn phải giữ bên ngoài nhóm ranh giới này.

Chỉ giữ t mà bỏ k có thể bỏ sót bản ghi có cùng thời gian với phần tử cuối Window trước. Với thứ tự giảm dần, hướng so sánh cũng phải tương ứng; không dùng nguyên dấu lớn hơn cho mọi sort.

Framework có cơ chế tạo keyset position từ kết quả. Ưu tiên sử dụng vị trí do Window cung cấp thay vì tự dựng một map thiếu khóa.

### 7.4. Null và projection thiếu khóa

Keyset filtering cần các property sort không null theo khả năng đang được mô tả trong dòng Commons/JPA này. Một field nullable có thể làm việc tái dựng điều kiện tiếp tục không đúng kỳ vọng.

Trong ví dụ, createdAt được khai báo không null và ID phân biệt các dòng.

Nếu Window trả projection, cần có các thuộc tính dùng để lấy khóa, bao gồm khóa phân biệt mà cơ chế scrolling yêu cầu. Một DTO chỉ có title không đủ cho keyset dựa trên createdAt và id.

Đừng làm tròn hoặc đổi kiểu giá trị khóa trong quá trình lưu và khôi phục cursor. Phải dùng giá trị tương ứng với dữ liệu thực tế của store. Xem [Scrolling của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/scrolling.html).

### 7.5. Không tái sử dụng cursor cho một truy vấn khác

Cursor chỉ có ý nghĩa cùng filter, sort, direction và mô hình dữ liệu tương ứng.

Nếu caller đổi tenant, status hoặc thứ tự sắp xếp, cần bắt đầu lại hoặc xử lý theo một hợp đồng cursor có kiểm tra điều kiện gốc. Không dùng vị trí cũ rồi coi kết quả lạ là lỗi của repository.

Một API cursor nên có cách ràng buộc position với cấu hình truy vấn và phiên bản định dạng của nó. Đây là hợp đồng ứng dụng; ScrollPosition không tự đóng gói mọi điều kiện HTTP của ứng dụng.

## 8. Dữ liệu thay đổi có thể làm các lần đọc không cùng ảnh chụp

### 8.1. Offset có thể dịch khi có insert/delete

Giả sử trang đầu đọc A, B, C. Trước lúc đọc trang hai, có một bản ghi được chèn trước A hoặc một bản ghi trước ranh giới bị xóa.

Offset của lần đọc tiếp theo vẫn là một con số, nhưng các vị trí trong tập kết quả đã dịch. Kết quả có thể lặp hoặc bỏ sót bản ghi so với danh sách quan sát ban đầu.

Sort ổn định giải quyết thứ tự của dữ liệu đang được xét; nó không đóng băng tập dữ liệu giữa các request.

### 8.2. Keyset không tự là snapshot

Keyset giúp tiếp tục theo giá trị khóa thay vì bỏ qua một số dòng. Tuy nhiên, nếu một bản ghi đổi giá trị sort hoặc đổi trạng thái khớp filter trong lúc duyệt, nó vẫn có thể đi qua ranh giới theo cách khác trước.

Không coi cursor là một snapshot token của database chỉ vì nó chứa keyset.

Với tác vụ xuất dữ liệu cần tập kết quả nhất quán, phải xác định chính sách như snapshot phù hợp, tập ID đã chốt hoặc một tiêu chí nghiệp vụ tương ứng. Mỗi lựa chọn có chi phí và giới hạn riêng.

Một mốc createdAt tối đa có thể giúp giới hạn bản ghi mới theo quy tắc đã chọn, nhưng không tự ngăn mọi thay đổi status, xóa hoặc cập nhật dữ liệu cũ.

### 8.3. Content và count có thể quan sát các thời điểm khác nhau

Nếu content query và count query là hai statement, cập nhật đồng thời có thể làm chúng không phản ánh cùng trạng thái.

Cùng nằm trong một transaction không tự bảo đảm mọi statement đều thấy cùng snapshot ở mọi isolation level. Chẳng hạn PostgreSQL Read Committed cho phép các statement liên tiếp nhìn thấy các trạng thái committed khác nhau. Xem [Transaction Isolation của PostgreSQL 17](https://www.postgresql.org/docs/17/transaction-iso.html).

Trước khi đổi query hoặc ép total về một con số, hãy xác định có thay đổi dữ liệu giữa hai lần quan sát không.

Nếu yêu cầu bắt buộc content và total nhất quán tuyệt đối, cần thiết kế cơ chế phù hợp với backend và cách thực thi thật; không chỉ thêm readOnly=true rồi suy ra yêu cầu đã được đáp ứng.

## 9. Đối chiếu khả năng của module và query đang dùng

### 9.1. JPA 3.5

Trong dòng JPA minh họa, Scroll API hỗ trợ các hình thức được module mô tả, gồm query methods, Query by Example và Querydsl.

Tài liệu 3.5 nêu chưa hỗ trợ scrolling với string-based query methods hoặc stored procedure query methods. Vì vậy, method Window trong ví dụ dùng query derivation; method có `@Query` chỉ phục vụ Page.

Xem [Scrolling Large Query Results của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html#jpa.query-methods.scrolling).

Có class ScrollPosition trong dependency Commons không đồng nghĩa mọi query implementation của mọi module đều xử lý được nó.

### 9.2. MongoDB

Khi total sai, cần phân biệt count theo filter với count ước lượng của toàn collection, đồng thời kiểm tra skip/limit và filter mà đoạn code tùy chỉnh thực sự đưa vào thao tác đếm.

Spring Data MongoDB phân biệt countDocuments và estimatedCount theo API/cấu hình. Xem [Counting Documents](https://docs.spring.io/spring-data/mongodb/reference/4.5/mongodb/template-document-count.html).

Không lấy một giá trị ước lượng toàn collection làm total chính xác của danh sách đã lọc tenant/status nếu hợp đồng yêu cầu số khớp filter.

### 9.3. JDBC, R2DBC và module khác

Đối chiếu riêng hỗ trợ Pageable, Sort, Window và query tùy chỉnh của phiên bản đang chạy. Đừng sao chép một method signature từ JPA sang module khác rồi suy rằng query, count hoặc cursor có cùng ngữ nghĩa và mức hỗ trợ.

Với reactive, còn phải bảo đảm pipeline đã được subscribe và kết quả quan sát không phải một publisher chưa thực thi.

## 10. Integration test tái hiện các ranh giới

### 10.1. Fixture cố ý có khóa thời gian trùng

Các ID 1–7 thuộc north/OPEN. Tạo từng cặp cùng createdAt để ranh giới Window cắt ngang một nhóm có thời gian bằng nhau.

Thêm bản ghi south/OPEN và north/CLOSED để phát hiện thiếu filter. Nếu chỉ tạo đúng dữ liệu cần trả về, một query thiếu điều kiện vẫn có thể vượt qua test.

### 10.2. Test metadata, initial offset và keyset

~~~java
package example.feed;

import java.time.Instant;
import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class FeedPagingTest {

    @Autowired
    private FeedRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @BeforeEach
    void seed() {
        Instant base = Instant.parse(
                "2025-01-01T00:00:00Z");

        for (long id = 1; id <= 7; id++) {
            entityManager.persist(new FeedItem(
                    id,
                    "north",
                    "OPEN",
                    "Item " + id,
                    base.plusSeconds((id - 1) / 2)));
        }

        entityManager.persist(new FeedItem(
                8L, "south", "OPEN", "Other tenant", base));

        entityManager.persist(new FeedItem(
                9L, "north", "CLOSED", "Other status", base));

        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void lastPageKeepsRequestedSizeAndFilteredTotal() {
        Sort sort = Sort.by("createdAt").ascending()
                .and(Sort.by("id").ascending());

        var firstPage = repository.search(
                "north",
                "OPEN",
                PageRequest.of(0, 3, sort));

        assertThat(firstPage.getTotalElements()).isEqualTo(7);

        var page = repository.search(
                "north",
                "OPEN",
                PageRequest.of(2, 3, sort));

        assertThat(page.getContent())
                .extracting(FeedItem::getId)
                .containsExactly(7L);

        assertThat(page.getNumber()).isEqualTo(2);
        assertThat(page.getSize()).isEqualTo(3);
        assertThat(page.getNumberOfElements()).isEqualTo(1);
        assertThat(page.getTotalElements()).isEqualTo(7);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.hasNext()).isFalse();
    }

    @Test
    void initialOffsetDiffersFromPositionZero() {
        var initial = repository
                .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        "north",
                        "OPEN",
                        ScrollPosition.offset());

        var afterFirst = repository
                .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        "north",
                        "OPEN",
                        ScrollPosition.offset(0));

        assertThat(initial.getContent())
                .extracting(FeedItem::getId)
                .containsExactly(1L, 2L, 3L);

        assertThat(afterFirst.getContent())
                .extracting(FeedItem::getId)
                .containsExactly(2L, 3L, 4L);
    }

    @Test
    void keysetKeepsRowsSharingBoundaryTimestamp() {
        var first = repository
                .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        "north",
                        "OPEN",
                        ScrollPosition.keyset());

        var second = repository
                .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        "north",
                        "OPEN",
                        first.positionAt(first.size() - 1));

        var third = repository
                .findFirst3ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        "north",
                        "OPEN",
                        second.positionAt(second.size() - 1));

        assertThat(Stream.of(first, second, third)
                .flatMap(window ->
                        window.getContent().stream())
                .map(FeedItem::getId)
                .toList())
                .containsExactly(
                        1L, 2L, 3L, 4L, 5L, 6L, 7L);

        assertThat(first.hasNext()).isTrue();
        assertThat(second.hasNext()).isTrue();
        assertThat(third.hasNext()).isFalse();
    }
}
~~~

Ví dụ giả định database test riêng, không có seed ngoài fixture. Các lần chạy test được cô lập theo cấu hình test JPA.

Test đầu kiểm tra total ở trang đầy và metadata ở trang cuối; chỉ kiểm tra số phần tử hiện tại sẽ bỏ sót lỗi tổng.

Test thứ hai bảo vệ khác biệt initial position với offset 0. Test thứ ba cố ý có cùng timestamp ở hai phía ranh giới, nên có thể phát hiện thiếu khóa phân biệt.

Các test này dùng dữ liệu tĩnh. Kiểm tra insert/delete hoặc thay sort key trong khi duyệt cần kịch bản giao dịch và thời điểm riêng, không được suy ra từ bộ test tĩnh.

## 11. Bảng chẩn đoán theo biểu hiện

| Biểu hiện | Điểm cần kiểm tra |
| --- | --- |
| Trang đầu trống hoặc bắt đầu quá muộn | UI đếm từ 1, chuyển đổi nhiều lần, nhầm page với offset |
| Size hiển thị lớn hơn số dòng ở trang cuối | Phân biệt size với numberOfElements |
| Content đúng nhưng total quá lớn | Count thiếu filter hoặc đếm dòng join |
| Total bằng số phần tử trang hiện tại | Tự tạo PageImpl với total sai |
| Metadata thay đổi sau map | Có lọc/khử trùng hoặc dựng lại Page không đúng |
| Không thấy COUNT trong log | Tối ưu suy total, query cache hoặc đường thực thi thực tế |
| Bản ghi lặp qua các trang trên dữ liệu tĩnh | Sort không đủ xác định, xung đột thứ tự hoặc sai ranh giới |
| Bản ghi lặp/mất khi có cập nhật | Offset dịch hoặc sort/filter thay đổi giữa các lần đọc |
| Sort bị báo không có property | Nhầm tên cột với property/alias hoặc dùng sai kiểu trả về |
| Bỏ mất bản ghi đầu khi scroll | Dùng offset(0) thay cho initial offset |
| Scroll đọc lại phần cuối Window cũ | Lấy position ở phần tử đầu thay vì phần tử cuối đã xử lý |
| Keyset mất dòng cùng thời gian | Thiếu khóa phân biệt hoặc thay đổi/làm tròn khóa |
| Keyset không lấy được position | Projection thiếu sort key, null key hoặc query không hỗ trợ |
| Cursor chỉ sai sau khi đổi filter | Tái sử dụng position của truy vấn cũ |
| Query chạy trên một store nhưng không trên store khác | Khác hỗ trợ API, collation, count hoặc mapping |

Khi đọc log, giữ cả tham số bind liên quan, filter thực tế, thứ tự ORDER BY và giới hạn/offset. Với count tùy chỉnh, quan sát riêng statement đếm thay vì chỉ query nội dung.

Không dùng việc tăng page size hoặc trả toàn bộ dữ liệu như cách che lỗi. Nó có thể làm hiện tượng khó thấy hơn nhưng không sửa hợp đồng phân trang.

## 12. Quy trình xác định và sửa đúng nguyên nhân

1. Ghi rõ tập kết quả mong đợi và đơn vị một phần tử: root, projection hay nhóm.
2. Xác minh filter, page number, size, sort và position sau mọi bước chuyển đổi.
3. Dùng fixture nhỏ có trùng khóa sort cùng bản ghi không khớp filter.
4. Đối chiếu query nội dung với query count hoặc cách suy total.
5. Với scrolling, phân biệt initial position và vị trí phần tử, rồi kiểm tra khóa tiếp tục.
6. Tách dữ liệu tĩnh khỏi thay đổi đồng thời để không trộn hai nguyên nhân.
7. Giữ test hồi quy cho content, metadata và chuỗi ID qua các lần đọc.

Kết quả đúng cần một hợp đồng nhất quán từ query đến caller. Page không tự sửa count sai, Sort không tự đóng băng dữ liệu và ScrollPosition không tự mô tả mọi điều kiện của truy vấn ứng dụng. Khi xác định rõ vai trò của từng abstraction và khả năng của store, các sai khác thường có thể được tái hiện rồi xử lý tại đúng lớp.
