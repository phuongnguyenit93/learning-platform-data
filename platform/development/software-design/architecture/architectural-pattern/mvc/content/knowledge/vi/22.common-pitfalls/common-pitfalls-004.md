# Truyền đối tượng lưu trữ trực tiếp ra giao diện không kiểm soát

Trong ứng dụng **Model–View–Controller (MVC)**, dữ liệu từ database thường đi qua repository, service hoặc use case trước khi được trình bày cho người dùng. Một lỗi thiết kế phổ biến là đưa thẳng đối tượng lưu trữ (chẳng hạn JPA entity) vào template hoặc trả entity trực tiếp từ REST endpoint. Cách làm này có vẻ nhanh vì không cần tạo lớp chuyển đổi, nhưng nó khiến cấu trúc database vô tình trở thành hợp đồng giao diện và có thể làm lộ dữ liệu nội bộ, mở đường cho cập nhật ngoài ý muốn, phát sinh truy vấn ORM khó kiểm soát hoặc tạo phụ thuộc vòng giữa các lớp.

Bài học thuộc chương **Sai lầm thường gặp**. Trọng tâm là nhận diện và khắc phục việc truyền đối tượng lưu trữ trực tiếp ra giao diện mà không kiểm soát. Ta sẽ phân biệt persistence entity với domain model, request DTO, response DTO và ViewModel; phân tích các rủi ro về bảo mật, binding, serialization, lazy loading, N+1 query, hiệu năng và coupling; sau đó xây dựng ranh giới dữ liệu rõ ràng bằng projection, DTO và mapping. Ví dụ sử dụng Java, Spring MVC, Spring Data JPA và Jackson.

## 1. Phân biệt đối tượng lưu trữ với dữ liệu trình bày

Một đối tượng lưu trữ được thiết kế để biểu diễn dữ liệu theo cách persistence layer cần. Với JPA, entity thường có:

- Khóa định danh và các thuộc tính được ánh xạ vào cột.
- Quan hệ OneToMany, ManyToOne, OneToOne hoặc ManyToMany.
- Trạng thái quản lý bởi persistence context.
- Annotation và quy tắc vòng đời phục vụ ORM.
- Những trường chỉ dùng nội bộ như tenant ID, audit fields hoặc trạng thái xử lý.

Giao diện có mục đích khác. Một màn hình chi tiết sách có thể chỉ cần tên, tác giả, mô tả và ngày xuất bản. API công khai có thể cần mã sách, tên, giá và trạng thái có thể mua. Form cập nhật có thể chỉ cho phép thay đổi tiêu đề và mô tả. Những hợp đồng này không nhất thiết trùng với cấu trúc entity.

| Kiểu dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Persistence Entity | Ánh xạ và quản lý dữ liệu lưu trữ | BookEntity |
| Domain Model | Biểu diễn khái niệm và quy tắc nghiệp vụ | Book, Money, ISBN |
| Request DTO | Nhận dữ liệu từ form hoặc API | UpdateBookRequest |
| Response DTO | Công bố dữ liệu qua API | BookResponse |
| ViewModel | Cung cấp dữ liệu cho một màn hình | BookDetailViewModel |
| Projection | Chỉ đọc một tập trường cần thiết từ query | BookSummary |

Các kiểu này có thể chia sẻ một số giá trị, nhưng chúng có vòng đời và trách nhiệm khác nhau. Không nên mặc định rằng một entity có thể đồng thời làm request, response và ViewModel mà không tạo ra rủi ro.

### 1.1. Model của Spring MVC không phải JPA Entity

Spring MVC có đối tượng org.springframework.ui.Model để Controller đưa dữ liệu cho View:

~~~java
model.addAttribute("book", book);
~~~

Ở đây, Model là một vùng chứa attribute của request render. book là giá trị được đặt vào đó; nó có thể là entity, DTO hoặc ViewModel.

Việc Spring gọi vùng chứa này là Model không có nghĩa entity được truyền vào tự động trở thành một mô hình trình bày an toàn. Cần xem kiểu dữ liệu cụ thể và những trường View có thể truy cập.

## 2. Vì sao truyền entity thẳng ra giao diện có vẻ tiện?

Một Controller có thể viết rất ngắn:

~~~java
@GetMapping("/books/{id}")
public String detail(@PathVariable UUID id, Model model) {
    BookEntity book = bookRepository.findById(id)
        .orElseThrow(BookNotFoundException::new);

    model.addAttribute("book", book);
    return "books/detail";
}
~~~

Template có thể truy cập trực tiếp các thuộc tính:

~~~html
<h1>BOOK_TITLE</h1>
<p>AUTHOR_NAME</p>
<p>BOOK_PRICE</p>
~~~

Các placeholder trên đại diện cho giá trị được template bind từ object. Với cách truyền entity, template biết cấu trúc entity và quan hệ ORM. Nếu entity thay đổi, template có thể phải sửa theo. Nếu template truy cập một quan hệ lazy, việc render có thể kích hoạt truy vấn database. Nếu entity có thêm trường nội bộ, dữ liệu đó có thể trở nên truy cập được từ View hoặc serializer.

Tương tự, REST Controller trả entity trực tiếp:

~~~java
@GetMapping("/api/books/{id}")
public BookEntity getBook(@PathVariable UUID id) {
    return bookRepository.findById(id)
        .orElseThrow(BookNotFoundException::new);
}
~~~

Jackson có thể serialize các thuộc tính mà nó nhìn thấy. Hợp đồng API khi đó bị gắn chặt với entity và mapping ORM.

Vấn đề cốt lõi không phải là số dòng code. Vấn đề là **ranh giới dữ liệu giữa persistence và presentation không được định nghĩa rõ**.

## 3. Rủi ro lộ dữ liệu nội bộ

Entity thường chứa nhiều thuộc tính hơn giao diện cần. Một ví dụ:

~~~java
@Entity
public class BookEntity {
    @Id
    private UUID id;

    private String title;
    private String description;
    private BigDecimal price;
    private String currencyCode;
    private boolean published;

    private UUID tenantId;
    private String internalReviewNote;
    private String supplierReference;
    private Instant createdAt;
    private Instant updatedAt;
}
~~~

Màn hình người mua chỉ cần id, title, description, price và published. Nếu trả toàn bộ entity, các trường nội bộ có thể bị đưa vào HTML hoặc JSON khi template/serializer truy cập chúng.

Các trường dễ bị lộ gồm:

- Ghi chú nội bộ hoặc nội dung kiểm duyệt.
- ID tenant, owner hoặc thông tin phân quyền.
- Mã tham chiếu nhà cung cấp.
- Trạng thái xử lý nội bộ.
- Dữ liệu audit không dành cho người dùng.
- Thông tin xác thực hoặc dữ liệu nhạy cảm nếu entity thiết kế sai.

Không phải mọi trường đều tự động xuất hiện trong HTML. Rủi ro phụ thuộc template, serializer, getter, cấu hình và cách dữ liệu được truyền. Nhưng đưa entity qua ranh giới làm tăng bề mặt có thể bị truy cập và khiến việc kiểm soát field trở nên phụ thuộc vào từng nơi sử dụng.

### 3.1. Nguyên tắc allowlist dữ liệu đầu ra

Hãy xác định trước màn hình hoặc API được phép công bố trường nào. Ví dụ:

~~~java
public record BookDetailViewModel(
    UUID id,
    String title,
    String description,
    BigDecimal price,
    boolean published
) {}
~~~

ViewModel chỉ có các thuộc tính cần thiết. Trường tenantId, internalReviewNote và supplierReference không nằm trong hợp đồng nên không thể vô tình được render qua object này.

Cách tiếp cận allowlist an toàn hơn việc cố gắng chặn từng trường nhạy cảm trong một entity ngày càng lớn.

## 4. Rủi ro mass assignment và cập nhật ngoài ý muốn

Truyền entity trực tiếp vào View đã là coupling; nhận dữ liệu form trực tiếp vào entity còn tạo thêm rủi ro **mass assignment** (binding quá nhiều trường).

Ví dụ không nên dùng:

~~~java
@PostMapping("/books/{id}")
public String update(
    @PathVariable UUID id,
    @ModelAttribute BookEntity book
) {
    bookRepository.save(book);
    return "redirect:/books/" + id;
}
~~~

Client có thể gửi thêm các field mà form không hiển thị, nếu binder cho phép bind chúng:

~~~text
title=Java
published=true
tenantId=another-tenant
internalReviewNote=approved
~~~

Khi đó, dữ liệu do người dùng kiểm soát có thể ghi đè trạng thái nội bộ hoặc thuộc tính không thuộc quyền cập nhật của họ. Ẩn một input bằng CSS hoặc không render nó trong form không phải biện pháp phân quyền.

### 4.1. Dùng request DTO chỉ chứa trường được phép sửa

~~~java
public record UpdateBookRequest(
    @NotBlank
    @Size(max = 160)
    String title,

    @Size(max = 4000)
    String description
) {}
~~~

Controller nhận DTO:

~~~java
@PostMapping("/books/{id}")
public String update(
    @PathVariable UUID id,
    @Valid @ModelAttribute("form") UpdateBookRequest form,
    BindingResult errors,
    RedirectAttributes redirectAttributes
) {
    if (errors.hasErrors()) {
        return "books/edit";
    }

    updateBookUseCase.update(
        new UpdateBookCommand(id, form.title(), form.description())
    );

    redirectAttributes.addFlashAttribute("message", "Đã cập nhật sách.");
    return "redirect:/books/" + id;
}
~~~

Use case tải đối tượng hiện có, kiểm tra quyền và chỉ cập nhật các thuộc tính được phép:

~~~java
public record UpdateBookCommand(
    UUID bookId,
    String title,
    String description
) {}

@Transactional
public void update(UpdateBookCommand command) {
    BookEntity book = repository.findById(command.bookId())
        .orElseThrow(BookNotFoundException::new);

    authorization.requireCanEdit(book);

    book.changeDetails(command.title(), command.description());
}
~~~

Ví dụ minh họa ý tưởng. Entity không được tạo mới từ toàn bộ request và lưu đè. Server quyết định tenant, owner, trạng thái xuất bản và các field được bảo vệ.

### 4.2. DTO không thay thế authorization

Một DTO chỉ loại bỏ những field không được nhận. Nó không tự xác nhận người dùng có quyền sửa tài nguyên.

Use case vẫn cần:

- Xác thực danh tính và vai trò.
- Kiểm tra người dùng có quyền trên đúng bản ghi hay không.
- Kiểm tra tenant hoặc phạm vi dữ liệu.
- Kiểm tra trạng thái nghiệp vụ có cho phép cập nhật không.
- Thực hiện thay đổi qua hành vi/domain method phù hợp.

Không dựa vào việc người dùng không thấy nút hoặc field trên form để bảo vệ endpoint.

## 5. Quan hệ ORM có thể tạo vòng lặp serialization

Entity thường có quan hệ hai chiều:

~~~java
@Entity
public class AuthorEntity {
    @OneToMany(mappedBy = "author")
    private List<BookEntity> books;
}

@Entity
public class BookEntity {
    @ManyToOne
    private AuthorEntity author;
}
~~~

Khi serializer duyệt AuthorEntity, nó có thể đi đến books, mỗi BookEntity lại đi ngược về author, rồi tiếp tục lặp. Kết quả có thể là:

- Lỗi phát hiện vòng tham chiếu.
- JSON lồng quá sâu hoặc payload rất lớn.
- Tải dữ liệu không cần thiết.
- Hợp đồng API thay đổi theo quan hệ ORM.
- Thông tin của các đối tượng liên quan bị lộ ngoài dự kiến.

Các annotation như JsonManagedReference, JsonBackReference hoặc JsonIgnore có thể điều chỉnh hành vi Jackson trong một trường hợp cụ thể. Chúng không giải quyết triệt để việc entity đang đóng vai trò API contract. Thêm hoặc đổi quan hệ có thể làm thay đổi JSON theo cách khó lường.

### 5.1. Chọn hình dạng response có chủ đích

Thay vì trả toàn bộ Author và Book entity, API có thể trả cấu trúc rõ ràng:

~~~java
public record AuthorSummaryResponse(
    UUID id,
    String name
) {}

public record BookDetailResponse(
    UUID id,
    String title,
    AuthorSummaryResponse author
) {}
~~~

Nếu màn hình chỉ cần tên tác giả, không cần trả danh sách sách của tác giả. Response chỉ chứa dữ liệu mà client cần cho use case đó.

## 6. Lazy loading và truy vấn phát sinh khi render

JPA/Hibernate có thể tải quan hệ theo kiểu lazy. Khi entity đi ra khỏi repository, một thuộc tính quan hệ có thể chưa được tải. Nếu template hoặc serializer đọc thuộc tính đó, ORM có thể thực hiện truy vấn bổ sung.

Ví dụ template duyệt danh sách sách và đọc tên tác giả:

~~~html
<ul>
  <li>
    <span>BOOK_TITLE</span>
    <span>AUTHOR_NAME</span>
  </li>
</ul>
~~~

Nếu author là quan hệ lazy và mỗi sách có một tác giả khác nhau, quá trình render có thể kích hoạt nhiều truy vấn. Đây là một dạng N+1 query: một truy vấn lấy danh sách và thêm nhiều truy vấn để lấy dữ liệu liên quan.

### 6.1. Open Session in View không làm rủi ro biến mất

Một số ứng dụng bật Open Session in View (OSIV), giữ persistence context mở trong suốt quá trình render response. Điều này có thể giúp template truy cập lazy relation mà không gặp LazyInitializationException, nhưng nó cũng cho phép truy vấn database phát sinh trong giai đoạn trình bày.

Hệ quả:

- Số query phụ thuộc vào template và cách serializer duyệt object.
- Thời gian phản hồi khó dự đoán.
- N+1 có thể chỉ xuất hiện với một dữ liệu hoặc màn hình cụ thể.
- View vô tình trở thành nơi kích hoạt persistence.
- Lỗi database có thể xảy ra muộn trong lúc render.

Tắt OSIV có thể làm lộ những truy cập lazy chưa được thiết kế, nhưng không tự động giải quyết mọi vấn đề. Cần xác định dữ liệu nào được tải trong use case/query layer và trả về cấu trúc đã sẵn sàng cho presentation.

### 6.2. Dùng projection hoặc fetch plan rõ ràng

Nếu màn hình cần tên sách và tên tác giả, query có thể chọn đúng hai nhóm trường:

~~~java
public record BookRow(
    UUID id,
    String title,
    String authorName
) {}
~~~

~~~java
@Query("""
    select new com.example.books.BookRow(
        b.id,
        b.title,
        a.name
    )
    from BookEntity b
    join b.author a
    where b.published = true
    order by b.title asc, b.id asc
    """)
List<BookRow> findPublishedBookRows();
~~~

Query trả về projection thay vì entity có quan hệ lazy. View không thể vô tình kích hoạt việc tải toàn bộ graph của entity.

Khi cần entity để thực hiện cập nhật nghiệp vụ, có thể dùng repository/entity trong transaction rồi chuyển kết quả sang DTO trước khi rời application boundary.

## 7. Coupling giữa schema database và giao diện

Nếu template truy cập trực tiếp book.author.name, giao diện phụ thuộc vào cấu trúc quan hệ entity. Khi thay đổi cách lưu tác giả, tách bảng, đổi tên thuộc tính hoặc thay ORM, template có thể phải sửa theo dù yêu cầu nghiệp vụ không thay đổi.

Tương tự, nếu REST API serialize entity trực tiếp, thay đổi persistence có thể vô tình làm thay đổi:

- Tên field JSON.
- Kiểu dữ liệu.
- Quan hệ lồng nhau.
- Giá trị null hoặc cách biểu diễn ngày giờ.
- Số lượng dữ liệu trả về.
- Hành vi khi thêm quan hệ mới.

### 7.1. DTO tạo hợp đồng ổn định

ViewModel và response DTO cho phép giao diện giữ tên và cấu trúc theo ngữ nghĩa của use case:

~~~java
public record BookDetailViewModel(
    UUID bookId,
    String displayTitle,
    String authorDisplayName,
    String formattedPrice,
    boolean canEdit
) {}
~~~

Persistence có thể đổi từ một bảng sang nhiều bảng hoặc từ JPA sang một nguồn dữ liệu khác. Nếu mapping vẫn tạo ra ViewModel tương thích, template không cần biết chi tiết đó.

Không nên đưa mọi format hiển thị vào domain model. Chuỗi tiền tệ đã định dạng có thể thuộc ViewModel; giá trị tiền tệ chuẩn vẫn nên giữ dạng số và currency code ở tầng nghiệp vụ.

## 8. Phân biệt input model và output model

Một sai lầm khác là dùng chung một DTO cho cả request và response. Input và output có mục đích khác nhau:

- Input mô tả những gì client được phép yêu cầu hoặc thay đổi.
- Output mô tả những gì server quyết định công bố.
- ViewModel mô tả dữ liệu một màn hình cần để render.

Ví dụ:

~~~java
public record CreateBookRequest(
    @NotBlank String title,
    @NotBlank String isbn
) {}

public record BookResponse(
    UUID id,
    String title,
    String isbn,
    String status
) {}

public record BookEditViewModel(
    UUID id,
    String title,
    String isbn,
    List<String> validationMessages
) {}
~~~

CreateBookRequest không có id, tenantId, createdAt hoặc status vì server quyết định các giá trị đó. BookResponse có thể công bố trạng thái theo hợp đồng API. BookEditViewModel có thể bổ sung dữ liệu phục vụ form.

### 8.1. Vì sao không dùng một DTO chung?

Một DTO chung thường tích lũy field tùy chọn:

~~~java
public class BookDto {
    private UUID id;
    private String title;
    private String isbn;
    private UUID tenantId;
    private String internalNote;
    private Boolean published;
    private Instant createdAt;
    private String formattedPrice;
}
~~~

Cùng một lớp có thể được dùng ở create, update, detail, list và admin. Theo thời gian, khó biết field nào được phép gửi, field nào được phép nhận và field nào chỉ dành cho vai trò quản trị.

Tách DTO theo use case giúp hợp đồng nhỏ, rõ và dễ kiểm thử hơn. Không cần tạo class mới cho mọi endpoint nếu ngữ nghĩa thực sự giống nhau; nhưng cần tránh một kiểu dữ liệu khổng lồ đại diện cho tất cả các luồng.

## 9. Mapping dữ liệu tại đúng ranh giới

Mapping chuyển dữ liệu từ mô hình này sang mô hình khác. Vị trí mapping nên phản ánh trách nhiệm:

| Chuyển đổi | Vị trí phù hợp |
|---|---|
| HTTP request → Request DTO | Web adapter / binding |
| Request DTO → Command | Controller hoặc request mapper |
| Command → Domain behavior | Application service |
| Persistence Entity → Projection/DTO | Query adapter hoặc repository |
| Use case result → ViewModel | Presentation adapter hoặc mapper |
| Use case result → Response DTO | REST adapter |

Không để template tự chuyển entity thành response hoặc tự gọi repository. Cũng không để domain entity biết cách render HTML, JSON hay format theo locale.

### 9.1. Mapping thủ công

Với số trường ít, mapping thủ công thường dễ đọc:

~~~java
BookDetailViewModel toViewModel(BookEntity book, boolean canEdit) {
    return new BookDetailViewModel(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName(),
        priceFormatter.format(book.getPrice()),
        canEdit
    );
}
~~~

Hàm này nên chạy khi dữ liệu cần thiết đã được tải và trong phạm vi transaction phù hợp nếu còn truy cập entity managed. Tốt hơn nữa, query có thể trả projection để không cần duyệt quan hệ lazy trong mapper.

### 9.2. Dùng MapStruct khi mapping lặp lại

MapStruct có thể sinh code mapping ở compile time. Nó hữu ích khi nhiều DTO có cấu trúc tương tự và mapping có quy tắc rõ.

~~~java
@Mapper(componentModel = "spring")
public interface BookResponseMapper {
    BookResponse toResponse(BookEntity entity);
}
~~~

Không nên cho mapper tự động copy tất cả field nhạy cảm chỉ vì tên thuộc tính trùng nhau. Hãy cấu hình field được phép ánh xạ rõ ràng và review generated behavior. Với field quyền hạn, tenant hoặc trạng thái nghiệp vụ, mapping tự động không thay thế authorization.

## 10. Ví dụ hoàn chỉnh: HTML MVC với ViewModel

Một query service có thể trả projection cho màn hình:

~~~java
public record BookDetailData(
    UUID id,
    String title,
    String description,
    String authorName,
    BigDecimal price,
    String currencyCode,
    boolean published
) {}
~~~

Repository lấy các trường cần thiết:

~~~java
public interface BookQueryRepository extends Repository<BookEntity, UUID> {
    @Query("""
        select new com.example.books.BookDetailData(
            b.id, b.title, b.description, a.name,
            b.price, b.currencyCode, b.published
        )
        from BookEntity b
        join b.author a
        where b.id = :id
          and b.tenantId = :tenantId
        """)
    Optional<BookDetailData> findDetail(
        @Param("id") UUID id,
        @Param("tenantId") UUID tenantId
    );
}
~~~

Application service kiểm tra phạm vi dữ liệu và tạo kết quả:

~~~java
@Service
public class GetBookDetailService {
    private final BookQueryRepository books;
    private final CurrentUser currentUser;

    public GetBookDetailService(
        BookQueryRepository books,
        CurrentUser currentUser
    ) {
        this.books = books;
        this.currentUser = currentUser;
    }

    @Transactional(readOnly = true)
    public BookDetailData get(UUID id) {
        return books.findDetail(id, currentUser.tenantId())
            .orElseThrow(BookNotFoundException::new);
    }
}
~~~

Controller chỉ điều phối và chuẩn bị dữ liệu cho View:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final GetBookDetailService getBookDetail;

    public BookController(GetBookDetailService getBookDetail) {
        this.getBookDetail = getBookDetail;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        BookDetailData book = getBookDetail.get(id);
        model.addAttribute("book", book);
        return "books/detail";
    }
}
~~~

Template dùng đúng những trường đã công bố:

~~~html
<article>
  <h1>BOOK_TITLE</h1>
  <p>AUTHOR_NAME</p>
  <p>BOOK_DESCRIPTION</p>
  <p>BOOK_PRICE</p>
</article>
~~~

Các placeholder đại diện cho binding trong template thật. Trong ví dụ này, BookDetailData là projection/DTO chỉ đọc. Nó không phải entity được quản lý bởi JPA. Template không thể duyệt các quan hệ persistence ngoài hợp đồng.

Transactional(readOnly = true) được đặt ở use case/query service theo chính sách transaction của ứng dụng. Nếu repository trả projection hoàn chỉnh, việc render không cần persistence context mở để tải thêm quan hệ.

## 11. Ví dụ REST API với response DTO

REST adapter cũng cần hợp đồng đầu ra riêng:

~~~java
public record BookResponse(
    UUID id,
    String title,
    String authorName,
    BigDecimal price,
    String currency,
    boolean published
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookApiController {
    private final GetBookDetailService getBookDetail;

    public BookApiController(GetBookDetailService getBookDetail) {
        this.getBookDetail = getBookDetail;
    }

    @GetMapping("/{id}")
    public BookResponse get(@PathVariable UUID id) {
        BookDetailData data = getBookDetail.get(id);

        return new BookResponse(
            data.id(),
            data.title(),
            data.authorName(),
            data.price(),
            data.currencyCode(),
            data.published()
        );
    }
}
~~~

Ví dụ minh họa cách chuyển dữ liệu. Trong ứng dụng thực tế, currency phải đến từ dữ liệu nghiệp vụ hoặc cấu hình hợp lệ; không hardcode một currency nếu sản phẩm hỗ trợ nhiều loại tiền. Trạng thái published cũng cần phản ánh quy tắc nghiệp vụ thực tế thay vì đồng nhất máy móc với khả năng mua.

Response DTO tạo hợp đồng JSON có chủ đích. Có thể version API hoặc bổ sung field mà không buộc thay đổi entity và schema database.

## 12. Bảo mật ở ranh giới presentation

DTO giúp giới hạn field, nhưng an toàn dữ liệu còn phụ thuộc vào cách query và authorization được áp dụng.

### 12.1. Lọc theo quyền trước khi trả dữ liệu

Không truy vấn một entity bất kỳ rồi chỉ ẩn một số field ở template nếu người dùng không được phép xem bản ghi đó. Use case cần kiểm tra quyền truy cập bản ghi hoặc thêm scope vào query.

Ví dụ:

~~~sql
SELECT id, title, description
FROM books
WHERE id = :book_id
  AND tenant_id = :current_tenant;
~~~

current_tenant phải lấy từ ngữ cảnh xác thực phía server. Không dùng tenant ID do client gửi làm căn cứ duy nhất. Với tài nguyên không tồn tại hoặc không thuộc quyền, ứng dụng áp dụng chính sách 403/404 nhất quán.

### 12.2. Phân quyền ở mức field

Một số màn hình admin có thể được phép xem dữ liệu nội bộ mà màn hình người dùng thường không được phép xem. Có thể tạo các response/ViewModel riêng theo use case hoặc role thay vì đưa toàn bộ entity ra rồi hy vọng template không hiển thị field nhạy cảm.

Nếu field nhạy cảm không được query hoặc không có trong DTO, nguy cơ vô tình render sẽ giảm. Tuy vậy, quyền xem vẫn cần được kiểm tra ở server.

### 12.3. Escape output và chống XSS

Dùng DTO không tự động chống Cross-Site Scripting (XSS). Dữ liệu do người dùng nhập vẫn cần được encode theo ngữ cảnh khi render HTML.

Với Thymeleaf, ưu tiên th:text cho nội dung văn bản thông thường; tránh th:utext nếu chưa sanitize HTML theo một chính sách rõ ràng. Không coi việc dữ liệu nằm trong entity hoặc DTO là bằng chứng nó an toàn để đưa vào HTML, JavaScript hay URL.

## 13. Hiệu năng và lượng dữ liệu trả về

Truyền entity đầy đủ có thể làm payload lớn, kéo theo quan hệ không cần thiết và tăng chi phí serialization. DTO/projection giúp chọn đúng trường, nhưng cần thiết kế query phù hợp.

Các nguyên tắc:

- Chỉ select các cột màn hình cần.
- Dùng pagination cho danh sách lớn.
- Tránh fetch toàn bộ collection chỉ để hiển thị số lượng.
- Dùng aggregate query khi chỉ cần count hoặc tổng.
- Xác định fetch plan rõ ràng cho use case.
- Đo số query và phát hiện N+1.
- Không trả blob hoặc nội dung lớn nếu giao diện không cần.
- Tránh serialize entity graph sâu.

Ví dụ, nếu màn hình chỉ cần số lượng sách của một tác giả, có thể truy vấn COUNT thay vì tải toàn bộ danh sách sách rồi gọi size().

### 13.1. Projection không có nghĩa query luôn nhanh

Một DTO được map từ entity sau khi tải toàn bộ graph vẫn có thể tốn chi phí tương tự. Muốn giảm I/O, cần projection ngay ở query layer hoặc fetch plan được đo và kiểm soát.

Hãy xem SQL được sinh ra, số query, số dòng đọc và thời gian thực thi. Không đánh giá hiệu năng chỉ từ số field trong DTO.

## 14. Cache và hợp đồng dữ liệu

Nếu cache response hoặc ViewModel, cache key cần chứa các yếu tố ảnh hưởng đến dữ liệu được công bố:

- ID tài nguyên.
- Tenant hoặc phạm vi quyền.
- Locale nếu dữ liệu đã được dịch/định dạng.
- Role hoặc nhóm quyền nếu output khác nhau theo quyền.
- Phiên bản representation khi hợp đồng thay đổi.

Không cache cùng một response nhạy cảm cho nhiều người dùng nếu nội dung phụ thuộc quyền. DTO không tự làm cache an toàn; cache vẫn phải tôn trọng authorization và chính sách dữ liệu riêng tư.

## 15. Những cách khắc phục không đủ

Một số giải pháp có thể giảm triệu chứng nhưng không thay thế việc định nghĩa hợp đồng dữ liệu.

| Cách làm | Vì sao chưa đủ | Hướng xử lý |
|---|---|---|
| Thêm JsonIgnore cho từng field | Dễ bỏ sót field mới và gắn cấu hình API vào entity | Dùng response DTO allowlist |
| Dùng JsonManagedReference/JsonBackReference | Chỉ xử lý một phần vòng tham chiếu | Thiết kế response graph rõ ràng |
| Bật OSIV để template đọc lazy relation | Có thể che N+1 và query phát sinh khi render | Query projection/fetch plan trước khi render |
| Ẩn field bằng CSS hoặc không đặt input trong form | Client vẫn có thể gửi field trực tiếp | Request DTO và authorization server-side |
| Chỉ dùng Valid trên entity | Validation không quyết định field nào client được phép thay đổi | Input DTO theo use case |
| Copy entity sang DTO sau khi tải toàn bộ graph | Vẫn có thể phát sinh nhiều query và payload lớn | Projection hoặc fetch đúng dữ liệu |
| Dùng một DTO cho mọi endpoint | Field và quyền input/output bị trộn | DTO theo hợp đồng và use case |
| Dùng mapper tự động không cấu hình | Có thể copy field nhạy cảm hoặc field ngoài ý muốn | Allowlist mapping và test |

## 16. Kiểm thử ranh giới persistence và presentation

Test nên xác nhận những field nào được nhận, những field nào được trả và việc render không kích hoạt truy vấn ngoài dự kiến.

### 16.1. Kiểm thử request DTO và mass assignment

- Gửi request có tenantId, ownerId, published hoặc field nội bộ ngoài DTO.
- Xác nhận field ngoài hợp đồng không thể cập nhật trạng thái entity.
- Xác nhận người dùng không có quyền không thể sửa bản ghi.
- Xác nhận validation field hợp lệ và thông báo lỗi phù hợp.
- Xác nhận giá trị server quản lý được tạo hoặc giữ ở server.

Không chỉ test form HTML; gửi request trực tiếp bằng HTTP client để mô phỏng client độc hại.

### 16.2. Kiểm thử response DTO và data exposure

- Xác nhận JSON chỉ có field công khai.
- Xác nhận không có password hash, internal note, tenant secret hoặc audit data.
- Xác nhận ViewModel chỉ chứa field màn hình cần.
- Xác nhận response không vô tình serialize quan hệ entity.
- Xác nhận dữ liệu giữa hai tenant không bị trộn.
- Xác nhận field nhạy cảm được loại bỏ ở query/mapping layer.

Có thể dùng JSONPath hoặc so sánh schema để kiểm tra allowlist. Test nên kiểm tra cả việc field nhạy cảm không xuất hiện, không chỉ xác nhận field mong đợi có mặt.

### 16.3. Kiểm thử ORM và hiệu năng

- Đếm số query cho màn hình danh sách.
- Phát hiện N+1 khi render thuộc tính liên quan.
- Kiểm tra query projection chỉ select các cột cần thiết.
- Kiểm tra template không truy cập repository hoặc lazy relation.
- Kiểm tra response lớn không tải toàn bộ collection.
- Kiểm tra hành vi khi OSIV bật/tắt theo cấu hình triển khai.
- Dùng dữ liệu đại diện để đo query plan và thời gian phản hồi.

### 16.4. Ví dụ test không lộ field nội bộ

~~~java
@Test
void responseDoesNotExposeInternalFields() throws Exception {
    mockMvc.perform(get("/api/books/{id}", BOOK_ID))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").exists())
        .andExpect(jsonPath("$.tenantId").doesNotExist())
        .andExpect(jsonPath("$.internalReviewNote").doesNotExist())
        .andExpect(jsonPath("$.supplierReference").doesNotExist());
}
~~~

Test minh họa kiểm tra hợp đồng JSON. Cần cấu hình fixture có các field nội bộ thực sự tồn tại trong entity để test bảo đảm response không làm lộ chúng.

## 17. Khi nào có thể dùng entity trực tiếp?

Không phải mọi lần truyền entity đều nguy hiểm như nhau. Trong một công cụ nội bộ nhỏ, màn hình chỉ đọc, dữ liệu không nhạy cảm và entity được thiết kế đúng cho phạm vi đó, việc dùng entity trực tiếp có thể là một lựa chọn tạm thời có chủ đích.

Tuy nhiên, trước khi chọn cách này cần xác nhận:

- Entity không chứa field nhạy cảm hoặc field ngoài quyền người dùng.
- View không kích hoạt lazy loading ngoài dự kiến.
- Không có quan hệ vòng hoặc graph lớn khi serialize.
- Không bind request vào entity để cập nhật.
- Giao diện không trở thành hợp đồng công khai phụ thuộc schema.
- Có test bảo vệ nếu entity thay đổi.
- Chi phí bảo trì thấp hơn lợi ích của việc tạo DTO riêng.

Với API công khai, dữ liệu nhiều tenant, màn hình có phân quyền field, form cập nhật hoặc hệ thống có nhiều loại client, DTO/ViewModel/projection thường là lựa chọn rõ ràng và an toàn hơn.

Không cần tạo DTO cho mọi object nội bộ. Hãy tạo ranh giới nơi dữ liệu đi qua một hợp đồng bên ngoài: HTTP request/response, template, message hoặc cache dùng chung.

## 18. Checklist trước khi đưa dữ liệu ra giao diện

- [ ] Xác định kiểu dữ liệu đang truyền là entity, domain object, DTO hay ViewModel.
- [ ] Chỉ công bố những field cần thiết cho màn hình hoặc API.
- [ ] Không đưa password, token, tenant secret, internal note hoặc audit field ra output.
- [ ] Không binding trực tiếp request vào persistence entity.
- [ ] Tách input DTO và output DTO theo hợp đồng.
- [ ] Kiểm tra authorization trên tài nguyên và field nhạy cảm ở server.
- [ ] Không để template hoặc serializer duyệt entity graph không kiểm soát.
- [ ] Tránh lazy loading và N+1 trong lúc render.
- [ ] Dùng projection/fetch plan phù hợp với query.
- [ ] Mapping đặt ở ranh giới web, application hoặc persistence tương ứng.
- [ ] Output được encode đúng ngữ cảnh để giảm nguy cơ XSS.
- [ ] Cache key tôn trọng tenant, role, locale và phiên bản representation.
- [ ] Có test cho mass assignment, data exposure, quan hệ vòng và số query.
- [ ] Review hợp đồng DTO khi schema hoặc giao diện thay đổi.

Truyền đối tượng lưu trữ trực tiếp ra giao diện không kiểm soát làm mờ ranh giới giữa database và presentation. Nó có thể khiến dữ liệu nội bộ bị lộ, cho phép client cập nhật field ngoài ý muốn, tạo truy vấn ORM khi render và khóa giao diện vào cấu trúc persistence. Bằng cách dùng request DTO, response DTO, ViewModel và projection theo đúng use case, ứng dụng MVC giữ được hợp đồng dữ liệu nhỏ, rõ và có thể kiểm thử. Entity vẫn phục vụ persistence và domain behavior ở phía server; View chỉ nhận dữ liệu mà nó cần để trình bày.
