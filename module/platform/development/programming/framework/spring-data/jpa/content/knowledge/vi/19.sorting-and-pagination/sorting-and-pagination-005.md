# Phân biệt List, Slice và Page

Spring Data JPA hỗ trợ nhiều kiểu kết quả cho repository query. Khi truy vấn danh sách dữ liệu, bạn có thể trả về **List**, **Slice** hoặc **Page**. Cả ba đều chứa kết quả, nhưng lượng metadata và chi phí truy vấn khác nhau.

- **List** chỉ trả về các phần tử. Nếu kết hợp với **Pageable**, kết quả được giới hạn theo trang nhưng không có thông tin về trang tiếp theo hoặc tổng số bản ghi.
- **Slice** trả về một lát dữ liệu cùng thông tin điều hướng như **hasNext()** và **hasPrevious()**, nhưng không tính tổng số bản ghi.
- **Page** cung cấp nội dung cùng tổng số phần tử và tổng số trang. Để có tổng số, Spring Data thường cần thực hiện thêm count query.

Chọn đúng kiểu trả về giúp tránh truy vấn đếm không cần thiết, giảm tải database và cung cấp đúng thông tin mà API cần. Bài này dùng cùng một mô hình Book để so sánh ba kiểu kết quả, cách truyền Pageable, cách sắp xếp ổn định và cách xử lý tập dữ liệu lớn.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Đây là các phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. So sánh nhanh List, Slice và Page

| Tiêu chí | List | Slice | Page |
|---|---|---|---|
| Nội dung kết quả | Có | Có | Có |
| Giới hạn theo Pageable | Có, nếu truyền Pageable | Có | Có |
| Biết có trang tiếp theo | Không | Có, qua **hasNext()** | Có, qua **hasNext()** |
| Biết tổng số phần tử | Không | Không | Có, qua **getTotalElements()** |
| Biết tổng số trang | Không | Không | Có, qua **getTotalPages()** |
| Count query | Không cần cho List có Pageable | Không cần | Thường cần, trừ khi framework suy ra được |
| Chi phí | Thấp về metadata | Thường thấp hơn Page | Có thể cao hơn do count |
| Phù hợp | Lấy danh sách đơn giản hoặc một đoạn dữ liệu | Duyệt từng lát, chỉ cần biết còn dữ liệu không | UI cần tổng số bản ghi/trang và điều hướng đầy đủ |

Cả **Slice** và **Page** đều kế thừa abstraction **Slice** của Spring Data; Page bổ sung thông tin tổng số. Một Page có thể cung cấp mọi thông tin điều hướng cơ bản của Slice, nhưng phải tính thêm tổng số kết quả.

Hãy chọn theo nhu cầu thực tế:

- Nếu chỉ cần một danh sách giới hạn, dùng List với Pageable.
- Nếu cần nút “Tiếp theo” nhưng không cần biết tổng số trang, dùng Slice.
- Nếu giao diện phải hiển thị “trang 2 trên 15” hoặc “có 1.245 kết quả”, dùng Page.

## 2. Pageable điều khiển trang và kích thước

**Pageable** mô tả trang cần lấy, kích thước trang và thông tin sắp xếp.

Ví dụ tạo yêu cầu trang:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

Ý nghĩa:

- **0** là chỉ số trang đầu tiên (zero-based).
- **20** là số phần tử tối đa trên một trang.

Trang tiếp theo:

~~~java
Pageable nextPage = PageRequest.of(1, 20);
~~~

Trong Spring Data, page index bắt đầu từ 0:

| Giá trị page | Trang hiển thị với người dùng |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 2 | 3 |
| 3 | 4 |

Không nhầm page index với số thứ tự trang thường hiển thị trên giao diện. Nếu API nhận số trang bắt đầu từ 1, cần chuyển về chỉ số bắt đầu từ 0 trước khi tạo PageRequest.

Kích thước trang phải là số dương. API cũng nên giới hạn kích thước tối đa để client không yêu cầu hàng trăm nghìn bản ghi trong một lần gọi.

## 3. Repository mẫu dùng cả ba kiểu kết quả

Giả sử entity Book có các thuộc tính **id**, **title**, **status**, **createdAt** và **authorId** hoặc quan hệ author phù hợp.

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    Page<Book> findByStatus(
        BookStatus status,
        Pageable pageable
    );

    Slice<Book> findByAuthorId(
        Long authorId,
        Pageable pageable
    );

    List<Book> findByTitleContainingIgnoreCase(
        String keyword,
        Pageable pageable
    );
}
~~~

Các phương thức dùng cùng điều kiện truy vấn nhưng khác kiểu kết quả:

- **findByStatus** trả Page vì use case cần tổng số sách theo trạng thái.
- **findByAuthorId** trả Slice vì giao diện chỉ cần tải tiếp nếu còn sách.
- **findByTitleContainingIgnoreCase** trả List vì caller chỉ cần một đoạn kết quả giới hạn và không cần metadata điều hướng.

Tên thuộc tính trong derived query phải khớp với model entity thực tế. Ví dụ **findByAuthorId** phù hợp khi đường dẫn thuộc tính có thể được phân tích thành quan hệ author và ID; nếu entity dùng tên field khác, hãy đổi method cho đúng hoặc khai báo query tường minh.

## 4. List với Pageable: chỉ lấy dữ liệu cần thiết

Khi repository method trả về List và nhận Pageable:

~~~java
List<Book> books =
    bookRepository.findByTitleContainingIgnoreCase(
        "spring",
        PageRequest.of(0, 20)
    );
~~~

Spring Data áp dụng giới hạn và offset tương ứng với Pageable. Kết quả chỉ chứa tối đa 20 phần tử của trang được yêu cầu.

List không cung cấp:

- Tổng số phần tử thỏa điều kiện.
- Tổng số trang.
- hasNext() hoặc hasPrevious().
- Page number và page size như metadata kết quả.

Vì không cần tổng số, List với Pageable không cần count query để tính tổng. Đây là lựa chọn gọn khi một tác vụ chỉ cần một đoạn kết quả.

Nếu method trả về List mà không truyền Pageable, repository có thể trả toàn bộ kết quả phù hợp. Với bảng lớn, tránh dùng truy vấn không giới hạn nếu caller chỉ cần một số bản ghi.

### Hạn chế của List với Pageable

Caller không thể biết chắc có trang tiếp theo chỉ từ List. Nếu nhận đủ page size, có thể còn dữ liệu, nhưng cũng có thể đó chính xác là trang cuối cùng. Nếu nhận ít hơn page size thì thường có thể suy ra không còn kết quả ở truy vấn đó, nhưng cách kiểm tra này không thay thế metadata Slice trong các tình huống cần điều hướng rõ ràng.

Nếu luồng xử lý phải lặp qua nhiều trang và cần biết còn dữ liệu hay không, Slice thường phù hợp hơn.

## 5. Slice: biết còn dữ liệu mà không đếm tổng

Slice chứa nội dung trang và metadata điều hướng. Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **getContent()** | Danh sách phần tử trong lát hiện tại |
| **getNumber()** | Chỉ số trang hiện tại, bắt đầu từ 0 |
| **getSize()** | Kích thước trang được yêu cầu |
| **getNumberOfElements()** | Số phần tử thực tế trong lát |
| **hasNext()** | Có lát tiếp theo hay không |
| **hasPrevious()** | Có lát trước hay không |
| **nextPageable()** | Pageable cho lát tiếp theo |
| **previousPageable()** | Pageable cho lát trước |

Ví dụ:

~~~java
Slice<Book> slice =
    bookRepository.findByAuthorId(
        authorId,
        PageRequest.of(0, 20)
    );

for (Book book : slice.getContent()) {
    System.out.println(book.getTitle());
}

if (slice.hasNext()) {
    Pageable next = slice.nextPageable();
    // Có thể dùng next để tải lát tiếp theo.
}
~~~

Để xác định có dữ liệu tiếp theo, Spring Data thường yêu cầu thêm một phần tử ngoài page size. Ví dụ page size là 20, query có thể lấy tối đa 21 hàng. Nếu hàng thứ 21 tồn tại, **hasNext()** là true; hàng bổ sung không được đưa vào content của lát hiện tại.

Cách này tránh phải chạy count query chỉ để biết còn dữ liệu hay không. Chi phí vẫn có thể tăng theo truy vấn chính, nhưng thường thấp hơn việc tính tổng số toàn bộ kết quả.

### Duyệt tất cả các Slice

~~~java
Pageable pageable = PageRequest.of(0, 100);
Slice<Book> slice;

do {
    slice = bookRepository.findByAuthorId(authorId, pageable);

    process(slice.getContent());

    pageable = slice.nextPageable();
} while (slice.hasNext());
~~~

Trong code thực tế, nên bảo đảm vòng lặp dừng khi không còn dữ liệu và xử lý lỗi truy vấn phù hợp. Nếu dữ liệu thay đổi trong lúc duyệt, kết quả giữa các lát có thể thay đổi theo transaction isolation và cách sắp xếp.

## 6. Page: có tổng số phần tử và tổng số trang

Page mở rộng thông tin của Slice bằng tổng số kết quả:

~~~java
Page<Book> page =
    bookRepository.findByStatus(
        BookStatus.PUBLISHED,
        PageRequest.of(0, 20)
    );
~~~

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **getContent()** | Nội dung trang |
| **getNumber()** | Chỉ số trang hiện tại |
| **getSize()** | Kích thước trang yêu cầu |
| **getNumberOfElements()** | Số phần tử trong trang hiện tại |
| **getTotalElements()** | Tổng số phần tử phù hợp với điều kiện query |
| **getTotalPages()** | Tổng số trang |
| **hasNext()** | Có trang tiếp theo |
| **isFirst()** / **isLast()** | Trang đầu hoặc trang cuối |

Ví dụ kết quả:

~~~text
number        = 0
size          = 20
numberOfElements = 20
totalElements = 245
totalPages    = 13
hasNext       = true
~~~

Nếu page size là 20 và tổng số phần tử là 245, tổng số trang là 13. Trang cuối có thể chứa ít hơn 20 phần tử.

Nếu không có bản ghi phù hợp, Page có content rỗng, **getTotalElements()** bằng 0 và **getTotalPages()** bằng 0.

Nếu yêu cầu một page index vượt quá trang cuối, Page thường trả content rỗng nhưng vẫn có thể chứa tổng số kết quả được tính từ count query.

## 7. Vì sao Page thường cần count query?

Để trả về **getTotalElements()**, framework phải biết tổng số bản ghi thỏa điều kiện, không chỉ số bản ghi của trang hiện tại. Spring Data thường thực hiện:

1. Một truy vấn lấy content với limit/offset.
2. Một count query để đếm tổng số kết quả.

Ví dụ về SQL ở mức ý tưởng:

~~~sql
SELECT id, title, status, created_at
FROM books
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;

SELECT COUNT(*)
FROM books
WHERE status = 'PUBLISHED';
~~~

Count query có thể tốn kém nếu điều kiện lọc phức tạp, join nhiều bảng, dùng DISTINCT hoặc truy vấn trên tập dữ liệu lớn.

Spring Data có thể suy ra tổng số từ content trong một số trường hợp, ví dụ trang đầu có ít phần tử hơn page size. Vì vậy không phải mọi lời gọi Page đều nhất thiết thực thi count query. Tuy nhiên, khi thiết kế hiệu năng, hãy giả định Page có thể cần một truy vấn đếm và kiểm tra SQL thực tế.

Nếu giao diện không cần tổng số, dùng Slice có thể tránh chi phí này.

## 8. Khai báo countQuery cho JPQL phức tạp

Với query method đơn giản, Spring Data thường tự tạo count query. Với JPQL có join, distinct hoặc cấu trúc phức tạp, nên khai báo count query rõ ràng.

Ví dụ:

~~~java
@Query(
    value = """
        select b
        from Book b
        join b.author a
        where b.status = :status
          and a.active = true
        """,
    countQuery = """
        select count(b)
        from Book b
        join b.author a
        where b.status = :status
          and a.active = true
        """
)
Page<Book> findActiveAuthorBooks(
    @Param("status") BookStatus status,
    Pageable pageable
);
~~~

Count query phải đếm đúng số entity logic mà content query trả về. Nếu join collection làm một Book xuất hiện nhiều lần, có thể cần:

~~~sql
select count(distinct b.id)
~~~

Trong JPQL, dùng **count(distinct b.id)** nếu điều đó phù hợp với cấu trúc truy vấn. Đừng chỉ sao chép nguyên query content rồi thay SELECT bằng COUNT mà không xem cardinality của join.

## 9. Phân trang native query

Native query có thể trả về Page, nhưng với truy vấn phức tạp nên khai báo **countQuery** riêng:

~~~java
@Query(
    value = """
        SELECT b.id, b.title, b.status, b.created_at
        FROM books b
        WHERE b.status = :status
        ORDER BY b.created_at DESC, b.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM books b
        WHERE b.status = :status
        """,
    nativeQuery = true
)
Page<Book> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Câu query content phải trả về đủ các cột cần thiết theo mapping Book. Tên cột trong SQL là tên vật lý của database; hãy kiểm tra mapping và alias nếu tên khác nhau.

Với native query có GROUP BY, count query cần đếm số nhóm được trả về, không phải tổng số hàng nguồn. Với join có thể nhân dòng, cần COUNT DISTINCT theo ID entity hoặc một count query tương ứng với logic thực tế.

Không giả định Spring Data luôn suy ra được count query đúng cho mọi native SQL. Kiểm thử cả content query và count query trên database đích.

## 10. Sắp xếp cùng Pageable

Pageable có thể mang theo Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
~~~

Truy vấn được sắp xếp theo thời gian tạo giảm dần, sau đó theo ID giảm dần.

Thêm thuộc tính duy nhất như **id** làm tie-breaker để thứ tự ổn định khi nhiều hàng có cùng createdAt. Nếu không có thứ tự ổn định, các trang có thể bị lặp hoặc bỏ sót phần tử ngay cả khi dữ liệu không thay đổi, tùy database và execution plan.

Tên thuộc tính trong Sort thường là property path của entity, ví dụ **createdAt**, không phải tên cột vật lý **created_at**. Với native query, khả năng áp dụng dynamic sort phụ thuộc cách Spring Data xử lý query và phiên bản; hãy khai báo ORDER BY trong SQL nếu cần kiểm soát tường minh.

Không đưa trực tiếp chuỗi sort tùy ý từ client vào native SQL. Hãy giới hạn các trường sort được phép trong API để tránh lỗi và giữ truy vấn dễ dự đoán.

## 11. Dùng Page.map() để chuyển sang DTO

Không cần tự tạo Page mới chỉ để chuyển entity thành DTO. **Page.map()** giữ lại metadata phân trang và ánh xạ từng phần tử.

DTO:

~~~java
public record BookSummary(
    Long id,
    String title,
    BookStatus status
) {
    public static BookSummary from(Book book) {
        return new BookSummary(
            book.getId(),
            book.getTitle(),
            book.getStatus()
        );
    }
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public Page<BookSummary> findPublishedBooks(Pageable pageable) {
    return bookRepository
        .findByStatus(BookStatus.PUBLISHED, pageable)
        .map(BookSummary::from);
}
~~~

Kết quả vẫn có **getTotalElements()**, **getTotalPages()**, **hasNext()** và các metadata khác. Chỉ content được chuyển từ Book sang BookSummary.

Nếu DTO cần dữ liệu từ association LAZY, hãy tải đúng fetch plan trong query hoặc dùng DTO projection trực tiếp. Không gọi getter association trong mapper một cách thiếu kiểm soát vì có thể tạo N+1.

## 12. Ví dụ API nhận Pageable

Spring MVC có thể bind các query parameter phổ biến thành Pageable khi Spring Data web support được cấu hình.

Controller:

~~~java
@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public Page<BookSummary> search(
            @RequestParam(required = false) String keyword,
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            ) Pageable pageable) {

        return bookService.search(keyword, pageable);
    }
}
~~~

Request ví dụ:

~~~text
GET /books?keyword=spring&page=0&size=20&sort=createdAt,desc
~~~

Các tham số thường gặp:

- **page**: chỉ số trang bắt đầu từ 0.
- **size**: số phần tử tối đa mỗi trang.
- **sort**: thuộc tính và hướng sắp xếp; có thể truyền nhiều tham số sort.

**@PageableDefault** đặt giá trị mặc định khi client không truyền page/size/sort. Hãy giới hạn page size tối đa và chỉ cho phép các thuộc tính sort mà API hỗ trợ. Nếu API hiển thị số trang bắt đầu từ 1, chuyển đổi rõ ràng ở lớp biên thay vì thay đổi ngầm semantics của Pageable.

## 13. Chọn List, Slice hay Page theo use case

| Use case | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Dropdown nhỏ, danh sách luôn giới hạn | List | Chỉ cần content |
| API tải thêm từng phần | Slice | Biết có dữ liệu tiếp theo, không cần tổng |
| Giao diện có số trang/tổng kết quả | Page | Cần totalElements và totalPages |
| Batch đọc từng nhóm để xử lý | Slice hoặc List với Pageable | Không cần count toàn bộ |
| Báo cáo cần tổng số bản ghi | Page | Có metadata tổng |
| Tìm kiếm lớn, count query rất đắt | Slice | Tránh count nếu UI không cần tổng |
| Lấy tất cả bản ghi nhỏ đã được giới hạn nghiệp vụ | List | Đơn giản, nhưng phải kiểm soát kích thước |

Không có kiểu trả về tốt nhất trong mọi trường hợp. Hãy hỏi caller cần thông tin gì trước khi chọn kiểu kết quả.

## 14. Offset pagination và dữ liệu lớn

PageRequest thường dùng offset pagination. Trang càng sâu, database có thể phải bỏ qua nhiều hàng trước khi trả kết quả. Ví dụ trang 5.000 với page size 20 có offset 99.980.

Offset pagination tiện cho giao diện có thể nhảy tới trang bất kỳ, nhưng có hai vấn đề:

- Offset lớn có thể tốn thời gian vì database phải xử lý/bỏ qua nhiều hàng.
- Nếu bản ghi được thêm hoặc xóa giữa hai lần gọi, vị trí các hàng thay đổi; người dùng có thể thấy bản ghi lặp hoặc bị bỏ qua giữa các trang.

Giảm rủi ro bằng cách:

- Dùng thứ tự ổn định, có khóa duy nhất làm tie-breaker.
- Giữ page size hợp lý.
- Dùng Slice khi không cần tổng số.
- Với luồng duyệt dữ liệu lớn theo một chiều, cân nhắc keyset/scroll pagination nếu phiên bản Spring Data và truy vấn hỗ trợ.

Keyset pagination tiếp tục từ giá trị của các khóa sắp xếp cuối cùng thay vì nhảy tới một offset lớn. Nó phù hợp cho “tải thêm” hoặc batch tuần tự, nhưng không tiện cho việc nhảy trực tiếp đến trang bất kỳ. Cần chọn khóa sắp xếp có tính ổn định và có index phù hợp.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang đầu bị bỏ qua | Dùng page index bắt đầu từ 1 thay vì 0 | Chuyển số trang API về zero-based |
| Page query chậm | Count query phức tạp hoặc đếm trên nhiều join | Dùng Slice nếu không cần tổng; tối ưu countQuery |
| Tổng số phần tử sai | Count query đếm dòng join thay vì entity duy nhất | Dùng count distinct hoặc count query đúng logic |
| List trả quá nhiều dữ liệu | Không truyền Pageable hoặc không giới hạn kết quả | Dùng Pageable và giới hạn page size |
| Không biết có trang tiếp theo với List | List không có metadata điều hướng | Dùng Slice |
| Sort không hoạt động | Tên sort dùng tên cột thay vì property hoặc query native không hỗ trợ như mong đợi | Kiểm tra property path và khai báo ORDER BY phù hợp |
| Kết quả lặp/thiếu giữa các trang | Thứ tự không ổn định hoặc dữ liệu thay đổi giữa request | Thêm tie-breaker duy nhất; cân nhắc keyset |
| Client yêu cầu page size quá lớn | Không giới hạn input Pageable | Đặt page size tối đa ở API |
| Page tổng trang sai với GROUP BY | Count query không đếm số nhóm | Viết countQuery đếm nhóm phù hợp |

## 16. Checklist lựa chọn và triển khai

- [ ] Xác định caller có cần tổng số bản ghi và tổng số trang không.
- [ ] Dùng List nếu chỉ cần content và kết quả đã được giới hạn.
- [ ] Dùng Slice nếu cần biết còn trang tiếp theo nhưng không cần tổng số.
- [ ] Dùng Page nếu giao diện cần totalElements/totalPages.
- [ ] Nhớ page index của Spring Data bắt đầu từ 0.
- [ ] Giới hạn page size và kiểm tra tham số sort.
- [ ] Thêm tie-breaker duy nhất để thứ tự ổn định.
- [ ] Khai báo countQuery khi JPQL/native query phức tạp.
- [ ] Kiểm tra JOIN có làm count bị nhân dòng không.
- [ ] Dùng Page.map() khi chuyển entity sang DTO.
- [ ] Đo SQL và thời gian count query trên dữ liệu gần thực tế.
- [ ] Cân nhắc keyset/scroll khi offset lớn và luồng đọc tuần tự.

## 17. Kết luận

**List** chỉ trả về content; khi dùng với Pageable, nó giới hạn kết quả nhưng không cung cấp metadata điều hướng. **Slice** bổ sung thông tin có trang tiếp theo hay không mà không cần đếm tổng số bản ghi. **Page** cung cấp tổng số phần tử và tổng số trang, thường phải thực hiện count query để có các giá trị đó.

Hãy dùng Slice cho luồng tải tiếp, Page cho giao diện cần tổng số, và List khi chỉ cần một tập kết quả giới hạn. Kết hợp Pageable với sort ổn định, countQuery đúng và page size hợp lý để giữ truy vấn dễ hiểu và hiệu năng có thể dự đoán.