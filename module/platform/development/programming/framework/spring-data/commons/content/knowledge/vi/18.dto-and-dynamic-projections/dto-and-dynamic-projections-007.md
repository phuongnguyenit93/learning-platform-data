# Collection và Page của projection

Trong chương **DTO và projection động** của Spring Data Commons (`SPRING_DATA_COMMONS`), projection xác định dữ liệu của **một phần tử**, còn `Collection`, `List`, `Slice` hoặc `Page` xác định cách tổ chức **nhiều phần tử** và metadata đi kèm.

Một query trả `Page<TicketRow>` vì vậy có hai hợp đồng: mỗi phần tử là một mô hình đọc `TicketRow`, còn toàn bộ kết quả mang thông tin phân trang và tổng số. Chọn đúng phần tử chưa đủ; container cũng phải phù hợp với nhu cầu của caller.

Bài học dùng ví dụ danh sách ticket. Khai báo query cụ thể được minh họa bằng Spring Data JPA; Commons định nghĩa các abstraction chung, còn khả năng kết hợp kiểu projection và kiểu trả về phải được xác nhận ở module store.

## 1. Tách kiểu phần tử khỏi container

Giả sử domain `SupportTicket` đã được mapping với các thuộc tính:

| Thuộc tính | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `tenantId` | `String` | Tenant sở hữu ticket. |
| `status` | `String` | Ví dụ `OPEN` hoặc `CLOSED`. |
| `title` | `String` | Tiêu đề hiển thị. |
| `createdAt` | `Instant` | Thời điểm tạo không null trong ví dụ. |

Một interface projection:

```java
import java.time.Instant;

public interface TicketView {

    Long getId();

    String getTitle();

    Instant getCreatedAt();
}
```

Một DTO record cho cùng nhóm thuộc tính, dùng Java 17:

```java
package example.ticket.read;

import java.time.Instant;

public record TicketRow(
    Long id,
    String title,
    Instant createdAt
) {}
```

Hai kiểu này khác cơ chế tạo phần tử: interface projection thường được biểu diễn bằng proxy, còn class-based projection được tạo bằng constructor.

Chúng đều có thể là kiểu phần tử trong một container được module hỗ trợ:

```text
List<TicketView>       -> danh sách interface projection
List<TicketRow>        -> danh sách DTO
Page<TicketView>       -> trang chứa interface projection
Page<TicketRow>        -> trang chứa DTO
```

Đổi `List` thành `Page` không biến DTO thành entity, cũng không làm interface projection tự có thêm thuộc tính domain.

## 2. Chọn Collection, List, Slice hay Page

| Kiểu trả về | Có dữ liệu phần tử? | Có thông tin còn phần tiếp? | Có tổng số toàn tập? |
| --- | --- | --- | --- |
| `Collection<P>` | Có. | Không có metadata phân trang riêng. | Không. |
| `List<P>` | Có, dưới dạng danh sách. | Không có metadata phân trang riêng. | Không. |
| `List<P>` với tham số `Pageable` | Có, trong phạm vi được query áp dụng. | Không có cờ riêng. | Không. |
| `Slice<P>` | Có, cho một phần dữ liệu. | Có, qua `hasNext()`. | Không có hợp đồng tổng số. |
| `Page<P>` | Có, cho một trang. | Có. | Có, qua metadata của page. |

Ở đây `P` đại diện cho kiểu projection, không phải một class đặc biệt phải khai báo.

Danh sách kiểu trả về chung và giới hạn theo từng store được nêu trong [Spring Data Commons: Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

Một collection tự nó không giới hạn số kết quả. Nếu không có điều kiện hoặc giới hạn thích hợp, query có thể trả toàn bộ dữ liệu khớp.

`List` giữ thứ tự của các phần tử đã nhận, nhưng muốn thứ tự query xác định thì vẫn cần sort. Không dựa vào thứ tự lưu vật lý hoặc một thứ tự tình cờ của store.

## 3. Khai báo các query có cùng projection nhưng khác hợp đồng

Ví dụ repository cho module hỗ trợ các dạng query dưới đây:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface TicketReadRepository
        extends Repository<SupportTicket, Long> {

    List<TicketRow> findAllByTenantIdAndStatus(
        String tenantId,
        String status
    );

    List<TicketRow> findListByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Slice<TicketRow> findSliceByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Page<TicketRow> findPageByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Page<TicketView> findViewsByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );
}
```

Ví dụ giả định import `TicketRow` từ `example.ticket.read` và các kiểu domain nằm trong package phù hợp.

Các phần `List`, `Slice`, `Page`, `Views` trong tên method ở đây là phần mô tả trước `By`. Chính kiểu trả về và tham số mới quyết định hợp đồng xử lý kết quả tương ứng, không phải việc trong tên có từ “Page”.

Đây là các query method riêng. Không đổi generic của một method CRUD kế thừa rồi giả định repository sẽ thực hiện một query projection mới.

Với JPA, derived query có thể dùng kiểu trả về để nhận diện interface hoặc DTO projection. Constructor của `TicketRow` cần khớp dữ liệu được chọn; không ép kiểu entity thành record ở caller.

## 4. Tạo Pageable với giới hạn và thứ tự rõ ràng

Một yêu cầu trang đầu gồm 20 ticket mới nhất:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<TicketRow> page =
    repository.findPageByTenantIdAndStatus(
        "ACME",
        "OPEN",
        request
    );
```

Theo [API PageRequest](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html), số trang bắt đầu từ 0, không được âm; kích thước trang phải dương.

Trong ví dụ:

- Trang 0 tương ứng phạm vi đầu tiên.
- Kích thước 20 là số phần tử mong muốn tối đa của trang dữ liệu thông thường.
- `createdAt` giảm dần xác định thứ tự chính.
- `id` giảm dần phân biệt các ticket có cùng thời điểm tạo.

Tên sort là thuộc tính query/domain phù hợp với module, không tự lấy từ tên nhãn hiển thị của DTO. Ví dụ đưa cả `createdAt` và `id` vào projection nên các khóa thứ tự cũng hiện diện trong mô hình đọc.

`Pageable` đã chứa sort. Không thêm một tham số `Sort` riêng vào cùng query để mô tả lại thứ tự đó.

Thứ tự có khóa phân biệt giúp các kết quả có thứ tự xác định khi dữ liệu không đổi. Nó không tự tạo snapshot qua nhiều lời gọi khi ticket đang được thêm, xóa hoặc cập nhật giữa các trang.

## 5. Đọc đúng metadata của Page

Các method quan trọng:

| Method | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử trên trang hiện tại. |
| `getNumber()` | Chỉ số trang hiện tại, bắt đầu từ 0. |
| `getSize()` | Kích thước trang theo yêu cầu/phạm vi page. |
| `getNumberOfElements()` | Số phần tử thực sự có trên trang này. |
| `getTotalElements()` | Tổng số phần tử khớp theo hợp đồng query. |
| `getTotalPages()` | Tổng số trang. |
| `hasNext()` | Có trang tiếp theo theo metadata hay không. |

Các tổng số và phép biến đổi page được định nghĩa trong [API Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html).

Giả sử dữ liệu không đổi, query khớp 53 ticket và page size là 20:

| Trang được yêu cầu | Số phần tử trên trang | Tổng số phần tử | Tổng số trang |
| ---: | ---: | ---: | ---: |
| 0 | 20 | 53 | 3 |
| 1 | 20 | 53 | 3 |
| 2 | 13 | 53 | 3 |
| 3, ngoài phạm vi dữ liệu | 0 | 53 | 3 |

Một trang rỗng không nhất thiết có nghĩa toàn bộ query không khớp dữ liệu. Có thể caller đã yêu cầu một vị trí ngoài phạm vi.

Không dùng `page.getContent().size()` hoặc `getNumberOfElements()` thay cho tổng số kết quả. Cũng không mặc định trang cuối phải có đúng page size.

Metadata mô tả tập dữ liệu theo điều kiện query, chẳng hạn tenant `ACME` và status `OPEN`; nó không phải tổng số mọi ticket trong store.

## 6. Projection nhẹ hơn không tự làm count query nhẹ hơn

Đối với `Page<P>`, ngoài query nội dung có giới hạn, hạ tầng thường cần xác định tổng số phần tử, chẳng hạn bằng count query.

Có hai công việc khác nhau:

```text
Query nội dung:
  chọn các thuộc tính cho projection
  áp dụng bộ lọc, thứ tự và phạm vi trang

Query tổng số:
  xác định số phần tử trong tập kết quả logic
  theo cùng điều kiện nghiệp vụ
```

Projection có thể giảm dữ liệu của mỗi phần tử nội dung. Nó không tự loại bỏ chi phí tính tổng, đặc biệt khi bộ lọc, join hoặc phép nhóm phức tạp.

Không cam kết mỗi lời gọi `Page` luôn thực hiện đúng hai query. Một số đường thực thi có thể suy ra tổng từ kích thước kết quả và thông tin trang để bỏ qua count. Cơ chế tối ưu đó được mô tả trong [PageableExecutionUtils](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/PageableExecutionUtils.html).

Nếu caller chỉ cần dữ liệu trong một phạm vi mà không cần tổng số, `List<P>` với `Pageable` có thể phù hợp. Nếu cần biết còn dữ liệu để tải tiếp, cân nhắc `Slice<P>`. Sự khác biệt này được trình bày trong [Paging, Iterating Large Results, Sorting & Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters).

Chọn container theo thông tin thực sự cần trả, không chọn `Page` chỉ vì giao diện hiển thị một nhóm dòng.

## 7. JPA: query nội dung và countQuery phải cùng phạm vi

Một khai báo tường minh cho DTO record:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface JpaTicketPageRepository
        extends Repository<SupportTicket, Long> {

    @Query(
        value = """
            select new example.ticket.read.TicketRow(
                t.id, t.title, t.createdAt
            )
            from SupportTicket t
            where t.tenantId = :tenantId
              and t.status = :status
            """,
        countQuery = """
            select count(t)
            from SupportTicket t
            where t.tenantId = :tenantId
              and t.status = :status
            """
    )
    Page<TicketRow> findRows(
        @Param("tenantId") String tenantId,
        @Param("status") String status,
        Pageable pageable
    );
}
```

`SupportTicket` trong ví dụ là tên entity JPA. Constructor expression dùng tên đầy đủ của record và thứ tự tham số tương ứng; đó là cú pháp JPA, không phải cú pháp query chung cho mọi store.

Ý nghĩa của thuộc tính `countQuery` được nêu trong [API Spring Data JPA Query](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/Query.html).

Những bất biến cần giữ:

- Nội dung và tổng số dùng cùng bộ lọc tenant.
- Nội dung và tổng số dùng cùng bộ lọc trạng thái.
- Count không bị giới hạn thành kích thước một trang.
- Phép đếm phải đếm cùng đơn vị kết quả logic với nội dung.

Không bỏ `status` khỏi count query chỉ vì nó không xuất hiện trong DTO. Thuộc tính không được hiển thị vẫn có thể là điều kiện chọn dữ liệu.

Không đưa constructor expression của DTO vào count query như thể nó là phần tử cần tạo để đếm.

### Khi query có join hoặc distinct

Giả sử một ticket có nhiều nhãn. Join sang nhãn có thể tạo nhiều hàng cho cùng ticket.

Nếu nội dung biểu diễn mỗi ticket một lần, query nội dung và count phải cùng duy trì ngữ nghĩa đó, chẳng hạn cần chọn và đếm distinct phù hợp. Không mặc định `count(*)` trên tập hàng join luôn là số ticket.

Ngược lại, nếu nội dung cố ý biểu diễn từng cặp ticket–nhãn, đơn vị đếm là cặp kết quả, không phải root ticket.

Việc dùng `Set` ở Java để loại trùng sau khi query không sửa được offset và total đã tính trên một tập hàng khác.

## 8. Page.map chuyển kiểu phần tử mà giữ cấu trúc trang

Khi đã có một page và cần tạo mô hình response khác theo quan hệ một-một, dùng `map`:

```java
public record TicketCard(
    Long id,
    String label
) {}
```

```java
Page<TicketCard> cards = page.map(row ->
    new TicketCard(
        row.id(),
        "#" + row.id() + " " + row.title()
    )
);
```

Một phần tử `TicketRow` tạo đúng một `TicketCard`. Thông tin trang và tổng số được chuyển tiếp theo implementation page thông thường; có thể xem cách làm trong [PageImpl.map, Commons 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/domain/PageImpl.java).

Đây là biến đổi kết quả đã nhận, không phải query projection mới. Nếu page ban đầu chứa entity đã tải rộng, `map` không làm query trước đó chọn ít cột hơn.

Converter nên chỉ sử dụng dữ liệu cần thiết. Nếu mỗi lần map lại gọi một repository khác, một phép đổi kiểu tưởng đơn giản có thể tạo thêm nhiều lượt truy cập store.

Hai kiểu generic khác nhau cũng không thể thay thế nhau bằng ép kiểu:

```text
Page<SupportTicket>
    không phải
Page<TicketRow>
```

Dùng query trả projection trực tiếp hoặc dùng hàm chuyển đổi phù hợp; không che khác biệt bằng raw type và unchecked cast.

## 9. getContent, filter và PageImpl có thể làm mất hợp đồng

### Lấy content là chọn bỏ metadata

Đoạn sau hợp lệ nếu caller chỉ cần list:

```java
List<TicketRow> rows = page.getContent();
```

Nhưng list đó không mang tổng số, số trang hoặc cờ trang tiếp theo. Nếu API cần các thông tin này thì phải trả kèm chúng hoặc giữ kiểu page phù hợp.

### Filter sau khi phân trang không phải query phân trang mới

Ví dụ lọc tiếp trên các dòng đã nhận:

```java
List<TicketRow> visible = page.getContent()
    .stream()
    .filter(row -> row.title().startsWith("Support"))
    .toList();
```

Giả sử page ban đầu có 20 dòng nhưng chỉ 3 dòng giữ lại. Không thể kết luận toàn bộ query chỉ có 3 dòng khớp hoặc lấy total cũ rồi gọi đó là total của tập đã lọc.

Nếu điều kiện này là tiêu chí lựa chọn của màn hình, nên đưa nó vào query nội dung và cách tính tổng tương ứng.

`Page` còn kế thừa một số phép toán từ `Streamable`; không phải mọi phép toán đó đều trả một `Page` mới với tổng số được tính lại. Cần kiểm tra kiểu trả về thực tế, không suy từ tên method `filter`.

### Không lấy số phần tử trang làm total giả

Thiết kế dễ sai:

```java
Page<TicketRow> rebuilt = new PageImpl<>(
    page.getContent(),
    page.getPageable(),
    page.getContent().size()
);
```

Số phần tử hiện tại không phải tổng số toàn tập. `PageImpl` có một số cách điều chỉnh total để giảm bất nhất ở trang cuối, nhưng nó không tự chạy query để tìm tổng thật.

Tương tự, `new PageImpl<>(page.getContent())` biểu diễn một page từ toàn bộ list đã đưa vào, không giữ ngữ cảnh phân trang ban đầu.

Nếu chỉ cần đổi mỗi phần tử mà không đổi tập kết quả, `page.map(...)` là cách diễn đạt trực tiếp hơn.

## 10. Projection động có thể kết hợp với Page

Một query có thể cho chọn kiểu phần tử khi gọi:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface DynamicTicketRepository
        extends Repository<SupportTicket, Long> {

    <T> Page<T> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable,
        Class<T> projectionType
    );
}
```

Caller có thể chọn DTO hoặc interface:

```java
Page<TicketRow> rows = repository.findByTenantIdAndStatus(
    "ACME",
    "OPEN",
    request,
    TicketRow.class
);

Page<TicketView> views = repository.findByTenantIdAndStatus(
    "ACME",
    "OPEN",
    request,
    TicketView.class
);
```

Mỗi lời gọi là một lần thực hiện query riêng; hai biến không phải hai cách nhìn tự động của cùng page đã lấy.

Phần `T` nối kiểu phần tử trả về với `Class<T>`. Nó không biến mọi class tùy ý thành projection hợp lệ. Kiểu đích vẫn phải có accessor hoặc constructor tương thích.

Quy tắc nhận diện tham số `Class<T>` cho dynamic projection được mô tả trong [Spring Data Commons: Dynamic Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projection.dynamic).

Khi là tham số chọn projection được hạ tầng nhận diện, `Class<T>` không mặc nhiên là một giá trị thông thường để bind vào query. Bộ lọc tenant, trạng thái và thông tin phân trang vẫn phải được truyền theo đúng hợp đồng.

Đối với use case công khai, service có thể chọn một kiểu trả về cố định để caller không phải biết các loại projection bên trong.

## 11. Service kiểm soát kích thước và thứ tự của trang

Ví dụ service trả page DTO cho màn hình ticket:

```java
import java.util.Objects;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TicketSearchService {

    private static final int MAX_PAGE_SIZE = 100;

    private final TicketReadRepository repository;

    public TicketSearchService(TicketReadRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<TicketRow> searchOpenTickets(
        String tenantId,
        int pageNumber,
        int pageSize
    ) {
        Objects.requireNonNull(tenantId, "tenantId");

        if (pageNumber < 0) {
            throw new IllegalArgumentException(
                "pageNumber must not be negative"
            );
        }

        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "pageSize must be between 1 and 100"
            );
        }

        PageRequest request = PageRequest.of(
            pageNumber,
            pageSize,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        return repository.findPageByTenantIdAndStatus(
            tenantId,
            "OPEN",
            request
        );
    }
}
```

Ví dụ giả định service là bean được gọi qua hạ tầng giao dịch đã cấu hình và repository JPA dùng transaction manager phù hợp.

Giới hạn 100 là chính sách minh họa của service, không phải hằng số nên áp cho mọi hệ thống. DTO ở đây chỉ có các giá trị đã đọc, không giữ collection hoặc quan hệ entity để truy cập về sau.

Một giao dịch đọc không tự bảo đảm content query và count query luôn nhìn cùng snapshot trong mọi cấu hình store và isolation. Cần đánh giá mức nhất quán mà use case yêu cầu khi dữ liệu đang thay đổi.

Page size còn chỉ giới hạn số phần tử root. Projection có nhánh collection lớn vẫn có thể tải nhiều dữ liệu liên quan hơn số dòng root thể hiện.

## 12. Khi chỉ cần tải tiếp, dùng Slice theo hợp đồng của nó

Nếu giao diện chỉ có nút “tải thêm”, một `Slice<TicketRow>` có thể đủ:

```java
Slice<TicketRow> slice =
    repository.findSliceByTenantIdAndStatus(
        "ACME",
        "OPEN",
        request
    );

render(slice.getContent());

if (slice.hasNext()) {
    Pageable nextRequest = slice.nextPageable();
    // Dùng nextRequest cho lần tải tiếp.
}
```

`render` là thao tác hiển thị của ứng dụng. Đoạn code không ngụ ý có một hàm tên đó trong Spring Data.

Kiểm tra `hasNext()` trước khi dùng `nextPageable()`, theo hợp đồng [API Slice](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Slice.html). Không dùng một `nextPageable` ở cuối tập dữ liệu như thể nó chắc chắn là yêu cầu trang kế tiếp có giới hạn.

Một số implementation lấy thêm một phần tử để biết còn dữ liệu, nhưng không nên coi đó là chiến lược bắt buộc của mọi module.

Nếu chỉ dùng `List<P>` với `Pageable`, một list có đúng page size chưa cho biết còn phần sau. Caller không nên tự khẳng định có hoặc không có trang kế tiếp chỉ từ trường hợp đó.

Nếu mục tiêu là duyệt tập dữ liệu rất lớn hoặc đi sâu qua nhiều vị trí, có thể cần đánh giá scrolling theo khả năng store. Đổi projection không loại bỏ chi phí của offset sâu.

## 13. Ví dụ Page trong bộ nhớ để quan sát metadata

Có thể tạo một page mẫu cho trang cuối của 53 ticket mà không cần store:

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.LongStream;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

List<TicketRow> content = LongStream.rangeClosed(41, 53)
    .mapToObj(id -> new TicketRow(
        id,
        "Ticket " + id,
        Instant.parse("2026-01-10T09:00:00Z")
    ))
    .toList();

Page<TicketRow> sample = new PageImpl<>(
    content,
    PageRequest.of(2, 20),
    53
);

Page<TicketCard> cards = sample.map(row ->
    new TicketCard(row.id(), row.title())
);

System.out.println(cards.getNumber());           // 2
System.out.println(cards.getSize());             // 20
System.out.println(cards.getNumberOfElements()); // 13
System.out.println(cards.getTotalElements());    // 53
System.out.println(cards.getTotalPages());       // 3
System.out.println(cards.hasNext());             // false
```

Ví dụ dùng `TicketRow` và `TicketCard` đã khai báo, với các import tương ứng. Giá trị total 53 được cung cấp từ dữ liệu giả định, không được suy từ list 13 phần tử.

Nó minh họa hành vi container và biến đổi phần tử. Nó không kiểm chứng selection của query, count query, mapping DTO hoặc hiệu năng của một store thật.

## 14. Thực hành chọn đúng hợp đồng kết quả

Với 53 ticket khớp bộ lọc tenant và trạng thái, page size 20, hãy phân tích:

| Tình huống | Điều cần xác định |
| --- | --- |
| Nhận `List<TicketRow>` không có giới hạn | Có thể đã tải toàn bộ tập kết quả. |
| Nhận list bằng query có `Pageable` | Có dữ liệu phạm vi đó, chưa có tổng số hay cờ next riêng. |
| Nhận page đầu | Phân biệt 20 phần tử hiện tại với total 53. |
| Nhận page 2 | Có 13 phần tử, vẫn là page size 20. |
| Nhận page 3 ngoài phạm vi | Content rỗng không có nghĩa total phải bằng 0. |
| Đổi page DTO sang page response | Dùng mapping một-một, giữ metadata. |
| Lọc bỏ 17 dòng sau khi đã lấy page | Chưa có page đúng cho tập điều kiện mới. |
| Query join tạo nhiều hàng cho một ticket | Xác định lại đơn vị nội dung và đơn vị đếm. |
| Dùng `Set` để xóa phần tử có giá trị bằng nhau | Không coi đó là cách sửa pagination hoặc count. |

Khi thực hành với module store thật, đối chiếu query nội dung, cách tính tổng và dữ liệu projection ở trang đầu, trang cuối, tập rỗng và trang ngoài phạm vi.

Một kết quả projection hoàn chỉnh cần thống nhất cả ba phần: kiểu dữ liệu của mỗi phần tử, phạm vi các phần tử được lấy và metadata mô tả tập kết quả. Chọn collection hay page theo đúng ba phần đó giúp caller sử dụng dữ liệu rõ ràng và tránh tự suy ra thông tin mà container không cung cấp.
