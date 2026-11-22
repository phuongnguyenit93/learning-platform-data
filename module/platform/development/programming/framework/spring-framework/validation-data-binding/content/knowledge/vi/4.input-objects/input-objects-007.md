# Tách đối tượng tạo mới, cập nhật và tìm kiếm

Trong ứng dụng Spring Framework, **cùng một thực thể nghiệp vụ không có nghĩa là mọi request nên dùng chung một kiểu dữ liệu đầu vào**. Tạo mới, cập nhật và tìm kiếm có mục đích, tập trường được phép gửi, quy tắc bắt buộc và cách xử lý khác nhau. Thiết kế các kiểu **input object** riêng giúp Spring MVC bind đúng dữ liệu, Bean Validation áp dụng đúng ràng buộc và service không vô tình nhận các trường mà người gọi không được thay đổi.

Ví dụ xuyên suốt là quản lý sách. Hệ thống lưu một `Book` có `id`, `title`, `author`, `price`, `stock`. Khách hàng API có thể thêm sách, sửa các thuộc tính được cho phép hoặc lọc danh sách sách. Ba hành động đó sẽ sử dụng ba kiểu riêng: `BookCreateRequest`, `BookUpdateRequest` và `BookSearchQuery`.

## 1. Vì sao cần tách ba loại đối tượng đầu vào?

Hãy xem cách tiếp cận dùng một `Book` cho tất cả endpoint:

~~~java
// Ví dụ thiết kế cần tránh: bind trực tiếp request lên persistence entity.
@PostMapping("/books")
void create(@RequestBody Book book) { /* ... */ }

@PutMapping("/books/{id}")
void update(@PathVariable long id, @RequestBody Book book) { /* ... */ }

@GetMapping("/books")
List<Book> search(Book book) { /* ... */ }
~~~

Nếu `Book` có cả `id`, `createdAt`, `ownerId`, `approved` hoặc quan hệ JPA, kiểu dữ liệu dùng chung sẽ làm mờ câu hỏi: *người gọi được phép quyết định trường nào?* Khi thêm field vào entity về sau, bề mặt dữ liệu được deserialize/bind cũng có thể thay đổi ngoài ý muốn.

Các khác biệt thường gặp:

| Khía cạnh | Tạo mới | Cập nhật | Tìm kiếm |
|---|---|---|---|
| Mục đích | Cung cấp dữ liệu tạo bản ghi | Thay đổi bản ghi đã tồn tại | Xây dựng điều kiện truy vấn |
| HTTP thường dùng | `POST /api/books` | `PUT /api/books/{id}` (hoặc `PATCH` với hợp đồng riêng) | `GET /api/books?...` |
| Đầu vào chính | JSON body | Path ID + JSON body | Query string |
| ID bản ghi | Server tạo, không để client tự gán | Lấy từ đường dẫn, cần kiểm tra quyền | Chỉ là bộ lọc nếu chức năng cho phép |
| Thuộc tính bắt buộc | Các giá trị để tạo bản ghi hợp lệ | Các giá trị theo hợp đồng cập nhật | Thường đa số tùy chọn, có mặc định |
| Validation | Ví dụ: tên/giá/stock khi tạo | Ví dụ: trường cập nhật phải hợp lệ | Ví dụ: trang ≥ 0, kích thước trang có giới hạn |
| Kết quả | Tạo một resource, thường `201 Created` | Trả bản ghi đã cập nhật hoặc `204 No Content` | Trả danh sách/trang kết quả |
| Đối tượng phù hợp | `BookCreateRequest` | `BookUpdateRequest` | `BookSearchQuery` |

Đây là **hợp đồng đầu vào** theo use case, thường còn gọi là request DTO, command object hoặc search criteria. `DTO` không phải thực thể được JPA quản lý. Đối tượng kết quả gửi cho client (ví dụ `BookResponse`) cũng nên được thiết kế riêng vì danh sách trường trả ra không nhất thiết giống danh sách trường nhận vào.

## 2. Luồng dữ liệu chuẩn qua ranh giới Spring MVC

~~~text
                 HTTP request
                      |
          +-----------+------------+
          |           |            |
        POST          PUT          GET
        JSON          JSON      query params
          |           |            |
          v           v            v
    CreateRequest UpdateRequest SearchQuery
          |           |            |
       JSON body    JSON body   @ModelAttribute
       deserialize  deserialize  data binding
          |           |            |
     @Valid /      @Valid /     @Valid /
     validation    validation   BindingResult
          |           |            |
          v           v            v
   Create service Update service Search service
          |           |            |
     tạo Entity   tải Entity,   tạo tiêu chí
     gán trường   kiểm quyền,    truy vấn
     cho phép     gán trường     có phân trang
                  cho phép
          |           |            |
          +-----------+------------+
                      |
                   Response DTO
~~~

Ở tầng HTTP cần tách hai cơ chế:

- Với JSON `@RequestBody`, một `HttpMessageConverter` (thường sử dụng Jackson) đọc body và tạo Java object; `@Valid` kích hoạt Bean Validation khi cấu hình thích hợp.
- Với query parameter hoặc form `@ModelAttribute`, Spring MVC sử dụng cơ chế **data binding** cho các property/constructor parameter, có chuyển kiểu và có thể ghi lỗi vào `BindingResult`. `@InitBinder` có thể cấu hình `WebDataBinder` cho đối tượng đó.
- **`WebDataBinder.setAllowedFields(...)` không phải bộ lọc thuộc tính JSON của `@RequestBody`.** Với JSON, thiết kế request DTO chỉ chứa field được phép và áp dụng cấu hình Jackson/chính sách đầu vào phù hợp.
- Validation của DTO không thay thế kiểm tra quyền cập nhật bản ghi, kiểm tra tính tồn tại, quy tắc nghiệp vụ, giao dịch hoặc kiểm soát đồng thời ở service.

## 3. Ví dụ Java 17 chạy độc lập để thấy các hợp đồng khác nhau

Đây là ví dụ **thuần Java**, chưa dùng Spring hoặc database, minh họa ba đối tượng phục vụ ba hành động khác nhau. Lưu tệp `RequestRolesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

public class RequestRolesDemo {

    record CreateBook(
            String title,
            String author,
            BigDecimal price,
            int initialStock) {}

    record UpdateBook(
            String title,
            BigDecimal price,
            int stock) {}

    record SearchBooks(
            String keyword,
            int page,
            int size) {}

    static final class Book {
        private final long id;              // Chỉ server cấp
        private final String author;         // Cố định sau khi tạo
        private String title;
        private BigDecimal price;
        private int stock;

        Book(long id, CreateBook request) {
            this.id = id;
            this.title = request.title();
            this.author = request.author();
            this.price = request.price();
            this.stock = request.initialStock();
        }

        void update(UpdateBook request) {
            this.title = request.title();
            this.price = request.price();
            this.stock = request.stock();
        }

        boolean matches(SearchBooks query) {
            return title.toLowerCase(Locale.ROOT)
                    .contains(query.keyword().toLowerCase(Locale.ROOT));
        }

        String summary() {
            return id + " | " + title + " | " + author + " | "
                    + price.toPlainString() + " | stock=" + stock;
        }
    }

    public static void main(String[] args) {
        CreateBook create = new CreateBook(
                "Java Basics", "An", new BigDecimal("120.00"), 3);
        Book book = new Book(101L, create);
        System.out.println("CREATED: " + book.summary());

        UpdateBook update = new UpdateBook(
                "Java Advanced", new BigDecimal("150.00"), 5);
        book.update(update);
        System.out.println("UPDATED: " + book.summary());

        SearchBooks search = new SearchBooks("java", 0, 20);
        System.out.println("SEARCH_MATCH: " + book.matches(search));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac RequestRolesDemo.java
java RequestRolesDemo
~~~

Kết quả chính xác:

~~~text
CREATED: 101 | Java Basics | An | 120.00 | stock=3
UPDATED: 101 | Java Advanced | An | 150.00 | stock=5
SEARCH_MATCH: true
~~~

Quan sát: request tạo có `author` và `initialStock`, request cập nhật có `stock` nhưng không nhận `id` hay thay `author`; request tìm kiếm chỉ mang điều kiện, `page` và `size`. Phương thức `matches` chỉ minh họa lọc theo từ khóa; ví dụ thuần Java này **chưa thực hiện phân trang**. Ứng dụng thực tế phải áp dụng phân trang trong service/repository.

Đối với Spring, giữ ý tưởng đó nhưng thêm binding, validation, mapping và xử lý lỗi ở các lớp tương ứng.

## 4. Đối tượng tạo mới: dữ liệu cần thiết để xây bản ghi

Trong dự án Spring MVC có `spring-webmvc` và Jakarta Bean Validation (với Spring Boot thường là `spring-boot-starter-web` và `spring-boot-starter-validation`), có thể viết record bất biến:

Tệp `BookCreateRequest.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookCreateRequest(
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 80) String author,
        @NotNull @DecimalMin("0.00") BigDecimal price,
        @NotNull @Min(0) Integer initialStock) {
}
~~~

Ví dụ JSON hợp lệ:

~~~json
{
  "title": "Spring in Practice",
  "author": "Mai",
  "price": 180000.00,
  "initialStock": 12
}
~~~

**Ý nghĩa hợp đồng:**

1. `title` và `author` không được null, rỗng hoặc chỉ chứa khoảng trắng; giới hạn độ dài để phù hợp quy tắc lưu trữ.
2. `price` bắt buộc có giá trị và không âm; `BigDecimal` phù hợp hơn `double` cho giá tiền dạng thập phân. Trong nghiệp vụ thực tế còn cần quy tắc đơn vị tiền, độ chính xác và giới hạn giá trị.
3. `initialStock` phải xuất hiện, không âm. Dùng `Integer` thay vì `int` để phân biệt trường bị thiếu (null) với số 0; `@Min(0)` một mình **không bắt null**.
4. DTO **không có** `id`, `ownerId`, `createdAt`, `approved` hay `version`. Những giá trị này phải được xác định bởi server và chính sách nghiệp vụ.
5. Record thích hợp cho request JSON bất biến. Với request `@ModelAttribute`, JavaBean có setter hoặc constructor binding được hỗ trợ là các lựa chọn khác; không bắt buộc dùng cùng một mẫu cho mọi nguồn đầu vào.

`@Valid` kiểm tra constraint trên record khi controller nhận JSON. Các lỗi như thiếu `title` hoặc `price < 0` thường khiến Spring MVC trả lỗi HTTP 400 nếu controller không tự xử lý `BindingResult`. JSON sai cấu trúc hoặc sai kiểu nghiêm trọng có thể phát sinh lỗi đọc body trước khi Bean Validation chạy, nên cần phân biệt hai loại lỗi.

## 5. Đối tượng cập nhật: chỉ trường cho phép sửa, tách ID khỏi body

Hệ thống giả định `author` là thông tin được cố định sau khi tạo; người dùng chỉ được sửa tiêu đề, giá và tồn kho qua thao tác cập nhật đầy đủ các trường có thể sửa.

Tệp `BookUpdateRequest.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookUpdateRequest(
        @NotBlank @Size(max = 120) String title,
        @NotNull @DecimalMin("0.00") BigDecimal price,
        @NotNull @Min(0) Integer stock) {
}
~~~

Request:

~~~http
PUT /api/books/101
Content-Type: application/json

{"title":"Spring Advanced","price":210000.00,"stock":9}
~~~

Sự khác biệt có chủ ý:

- `BookCreateRequest` dùng `initialStock` và nhận `author` khi bản ghi chưa tồn tại.
- `BookUpdateRequest` dùng `stock` là lượng tồn kho mới và **không có `author`** vì hợp đồng này không cho sửa tác giả.
- `id=101` lấy từ `@PathVariable`, dùng để xác định bản ghi; body không có quyền đổi khóa định danh.
- Đối với **PUT theo hợp đồng này**, cả `title`, `price` và `stock` đều bắt buộc. Nếu người dùng muốn chỉ thay giá, cần thiết kế thêm hợp đồng cập nhật từng phần thích hợp, chẳng hạn PATCH; không tự biến PUT thành PATCH chỉ vì field bị bỏ trống.

Bản ghi hiện có được truy xuất và kiểm tra trước khi thay đổi, ví dụ ở service:

~~~java
// Đoạn trong service/repository của dự án, không phải chương trình độc lập.
Book entity = repository.findById(bookId)
        .orElseThrow(() -> new BookNotFoundException(bookId));

authorization.checkCanEdit(currentUser, entity);

entity.setTitle(request.title().trim());
entity.setPrice(request.price());
entity.setStock(request.stock());

repository.save(entity);
~~~

Các kiểu `Book`, `BookNotFoundException`, `repository`, `authorization` và `currentUser` ở đây là thành phần của ứng dụng được tích hợp, **không phải API có sẵn của Spring**. Điểm quan trọng là service chỉ gán những field được hợp đồng cập nhật cho phép, sau khi xác định đúng bản ghi và quyền người gọi.

Nếu tồn kho phải được quản lý bằng giao dịch nhập/xuất riêng, hãy loại `stock` khỏi DTO cập nhật thông tin sách và cung cấp thao tác tồn kho riêng. Ranh giới chính xác do use case quyết định.

## 6. Đối tượng tìm kiếm: tiêu chí tùy chọn, mặc định và giới hạn truy vấn

Search request **không tạo hay sửa entity**. Nó mô tả điều kiện lọc và phân trang. Trong Spring MVC, query string thường được bind thuận tiện qua `@ModelAttribute` vào một đối tượng chuyên dụng.

Tệp `BookSearchQuery.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public class BookSearchQuery {

    @Size(max = 120)
    private String keyword;

    @DecimalMin("0.00")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    private BigDecimal maxPrice;

    @Min(0)
    private int page = 0;

    @Min(1)
    @Max(100)
    private int size = 20;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public BigDecimal getMinPrice() {
        return minPrice;
    }

    public void setMinPrice(BigDecimal minPrice) {
        this.minPrice = minPrice;
    }

    public BigDecimal getMaxPrice() {
        return maxPrice;
    }

    public void setMaxPrice(BigDecimal maxPrice) {
        this.maxPrice = maxPrice;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }

    public int getSize() {
        return size;
    }

    public void setSize(int size) {
        this.size = size;
    }
}
~~~

Ví dụ:

~~~http
GET /api/books?keyword=Spring&minPrice=100000&maxPrice=250000&page=0&size=20
~~~

Các điểm cần hiểu:

- `keyword`, `minPrice` và `maxPrice` là **bộ lọc tùy chọn**; giá trị null có thể có nghĩa “không áp dụng điều kiện” theo quy ước của service.
- `page=0`, `size=20` là mặc định khi client không cung cấp tham số tương ứng. `@Min`, `@Max` kiểm tra giới hạn khi giá trị được bind.
- Spring sẽ cố chuyển query string sang `BigDecimal` / `int`. Với `size=abc`, quá trình binding có thể sinh lỗi type mismatch; cần kiểm tra `BindingResult` trước khi thực hiện truy vấn.
- `@DecimalMin("0.00")` không bắt buộc số phải có mặt; dùng thêm `@NotNull` nếu bộ lọc thực sự bắt buộc.
- **Ràng buộc liên trường**: nếu cả `minPrice` và `maxPrice` có mặt thì `minPrice <= maxPrice`. Annotation trên từng trường chưa bảo đảm điều kiện đó; cần custom constraint cấp class hoặc kiểm tra rõ ràng tại ranh giới truy vấn.
- Nên chuẩn hóa `keyword` (trim, giới hạn độ dài, chính sách tìm kiếm không phân biệt hoa/thường nếu cần) trong tầng chuyển đổi tiêu chí. Không tự ghép trực tiếp chuỗi query người dùng vào SQL.
- Truy vấn có thể rất tốn tài nguyên; áp giới hạn `size`, sử dụng thứ tự sắp xếp ổn định, index cần thiết và các chính sách tối ưu khác. Nếu hỗ trợ `sort`, chỉ cho chọn từ danh sách field sắp xếp được phép.

Không thêm các field như `title`, `author`, `price` vào search object chỉ vì chúng tồn tại trong entity. Chỉ khai báo những điều kiện mà API thực sự hỗ trợ, có ý nghĩa rõ ràng khi bỏ trống.

## 7. Kết nối ba input object với Spring MVC controller

Dưới đây là ví dụ **mã tích hợp trong ứng dụng Spring MVC**, giả định một `BookService` đã được viết và đăng ký làm bean. Các DTO ở mục 4–6 có package `example.books.api`.

Tệp `BookResponse.java`, kết quả tách khỏi đầu vào:

~~~java
package example.books.api;

import java.math.BigDecimal;

public record BookResponse(
        long id,
        String title,
        String author,
        BigDecimal price,
        int stock) {
}
~~~

Tệp `BookService.java`, hợp đồng cho tầng nghiệp vụ:

~~~java
package example.books.api;

import java.util.List;

public interface BookService {
    BookResponse create(BookCreateRequest request);
    BookResponse update(long bookId, BookUpdateRequest request);
    List<BookResponse> search(BookSearchQuery query);
}
~~~

Tệp `BookController.java`:

~~~java
package example.books.api;

import java.net.URI;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @InitBinder("filters")
    void bindSearchFields(WebDataBinder binder) {
        binder.setAllowedFields(
                "keyword", "minPrice", "maxPrice", "page", "size");
    }

    @PostMapping
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody BookCreateRequest request) {
        BookResponse created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @PutMapping("/{id}")
    public BookResponse update(
            @PathVariable long id,
            @Valid @RequestBody BookUpdateRequest request) {
        return service.update(id, request);
    }

    @GetMapping
    public ResponseEntity<?> search(
            @Valid @ModelAttribute("filters") BookSearchQuery query,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<Map<String, String>> details =
                    errors.getFieldErrors().stream()
                            .map(error -> Map.of(
                                    "field", error.getField(),
                                    "code", String.valueOf(error.getCode())))
                            .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", details));
        }

        if (query.getMinPrice() != null
                && query.getMaxPrice() != null
                && query.getMinPrice().compareTo(query.getMaxPrice()) > 0) {
            return ResponseEntity.badRequest().body(Map.of(
                    "errors", List.of(Map.of(
                            "field", "maxPrice",
                            "code", "range.invalid"))));
        }

        return ResponseEntity.ok(service.search(query));
    }
}
~~~

Đoạn controller và các kiểu được khai báo đầy đủ về mặt API Java 17+, nhưng **để khởi động thành ứng dụng thực sự** vẫn cần Spring Boot/Spring MVC configuration, Bean Validation provider, một bean triển khai `BookService`, persistence hoặc dữ liệu thử, và xử lý lỗi nghiệp vụ. Không có sẵn repository hay database trong những đoạn code trên. Ví dụ Java thuần ở mục 3 mới là chương trình độc lập có thể chạy chỉ bằng `javac` / `java`.

### Những chi tiết quan trọng của controller

**Tạo mới:** `@RequestBody` deserialize JSON vào `BookCreateRequest`. `@Valid` kiểm tra constraint; nhánh thành công trả `201 Created` kèm `Location` và `BookResponse`. `service.create(...)` chịu trách nhiệm cấp ID, gán thuộc tính được phép và lưu.

**Cập nhật:** URL `/api/books/{id}` chỉ định resource. DTO chỉ có các trường được phép sửa; `service.update(...)` chịu trách nhiệm kiểm tra tồn tại, quyền, phiên bản và cập nhật đúng thuộc tính. Nếu ID không tồn tại, service/controller cần chuyển thành `404`; nếu có xung đột phiên bản thì có thể phản hồi `409 Conflict` tùy hợp đồng API.

**Tìm kiếm:** `@ModelAttribute("filters")` nhận query string. `@InitBinder("filters")` giới hạn các property được phép bind qua cơ chế `WebDataBinder`. Tham số `BindingResult` nằm **ngay sau** `@ModelAttribute`; nhờ đó controller có thể đọc các lỗi binding/validation và trả 400 thay vì đi vào repository. Kiểm tra khoảng giá chạy sau khi dữ liệu đơn lẻ hợp lệ.

**Giới hạn ví dụ về lỗi:** JSON sai cú pháp và validation lỗi trên `@RequestBody` thông thường được Spring MVC xử lý qua cơ chế exception; `BindingResult` đặt bên cạnh `BookSearchQuery` trong ví dụ chỉ xử lý local các lỗi của *search model attribute*. Để phản hồi lỗi JSON theo một cấu trúc nhất quán, ứng dụng nên có `@RestControllerAdvice` phù hợp. Mẫu `Map` lỗi ở đây chỉ minh họa hợp đồng lỗi, không phải định dạng tự động của Spring.

## 8. Phân biệt PUT và PATCH khi thiết kế cập nhật

Tách DTO cho create/update/search **chưa đủ** nếu cập nhật đầy đủ và cập nhật một phần bị trộn vào nhau.

**PUT** thường biểu diễn việc gửi trạng thái mong muốn của resource theo hợp đồng endpoint. Trong ví dụ, những thuộc tính *được phép sửa qua hợp đồng PUT* đều là trường bắt buộc. `null` hoặc thiếu trường sẽ không được âm thầm hiểu là “giữ nguyên”.

**PATCH** diễn đạt một tập thay đổi. Khi hỗ trợ PATCH, phải phân biệt rõ:

| JSON gửi lên | Ý nghĩa có thể cần |
|---|---|
| Không có key `title` | Giữ nguyên tiêu đề |
| `"title": null` | Có thể là yêu cầu xóa giá trị, hoặc sai theo hợp đồng |
| `"title": ""` | Yêu cầu đặt tiêu đề rỗng; có thể bị validation từ chối |
| `"title": "Mới"` | Đặt tiêu đề thành `"Mới"` |

Nếu định nghĩa DTO PATCH dạng `String title` rồi dùng Jackson thông thường, cả “không có key” và “key có giá trị null” đều có thể thành `null`, làm mất thông tin về **sự hiện diện** của trường. Hãy dùng hợp đồng PATCH có mô hình presence rõ ràng (ví dụ JSON Merge Patch theo RFC 7396, JSON Patch theo RFC 6902, hoặc một kiểu wrapper thể hiện `absent/null/value`), rồi chỉ gán những field thực sự được gửi và hợp lệ.

**Không biến mọi field nullable thành hợp đồng PATCH**. Một trường có thể tùy chọn khi tạo, nhưng bắt buộc khi PUT, và có ba trạng thái riêng khi PATCH. Nếu hỗ trợ PATCH, nên có DTO/cơ chế binding dành riêng cho PATCH thay vì tái sử dụng `BookUpdateRequest` một cách mơ hồ.

Đối với cập nhật đồng thời, nên xem xét `version`, optimistic locking (ví dụ JPA `@Version`) hoặc `ETag`/`If-Match`, để hai người sửa cùng bản ghi không âm thầm ghi đè lẫn nhau. `version` không nên trở thành một field có thể tùy ý ghi lên entity chỉ nhờ binding.

## 9. Validation phù hợp với từng hành động

Các annotation như `@NotNull`, `@NotBlank`, `@Size`, `@Min` chỉ có ý nghĩa đúng khi đặt trong **ngữ cảnh use case**.

| Quy tắc | Create | Update | Search |
|---|---|---|---|
| Tên sách | Bắt buộc, không rỗng | Bắt buộc trong PUT đã định nghĩa | Không có field `title`; dùng `keyword` tùy chọn |
| Tác giả | Bắt buộc ở create | Không cho sửa bằng endpoint này | Không cho lọc theo tác giả trong API ví dụ |
| Giá | `price` bắt buộc, ≥ 0 | `price` bắt buộc, ≥ 0 | `minPrice`/`maxPrice` tùy chọn và ≥ 0 |
| Tồn kho | `initialStock` bắt buộc, ≥ 0 | `stock` bắt buộc, ≥ 0 | Không có field tồn kho trong bộ lọc ví dụ |
| Phân trang | Không áp dụng | Không áp dụng | `page` ≥ 0, `size` trong [1,100] |
| Quy tắc liên trường | Có thể có tùy nghiệp vụ | Có thể khác create | `minPrice <= maxPrice` nếu cả hai xuất hiện |

Một lớp với nhiều validation group như `Create.class` và `Update.class` có thể phù hợp khi cấu trúc đầu vào thực sự giống nhau. Tuy nhiên, nếu field được phép, ý nghĩa dữ liệu và nguồn binding khác nhau, **ba kiểu riêng rõ ràng hơn**. Group validation chỉ thay đổi tập constraint được áp dụng; nó **không tự tạo giới hạn các thuộc tính được phép deserialize/bind** và không thay thế authorization.

Nếu entity có constraint tầng persistence (ví dụ một cột không được null), vẫn cần validation ở request DTO nhằm cung cấp thông báo dễ hiểu và ngăn dữ liệu sai trước khi chạm transaction. Service/domain cũng phải bảo vệ invariants vì có thể được gọi từ job, message consumer, CLI hay code nội bộ ngoài HTTP.

## 10. Mapping DTO sang entity: chỉ gán những trường thuộc hợp đồng

Quy tắc thực hành:

**Create:** tạo entity mới, gán đúng trường do create DTO cung cấp; sinh ID, timestamps, owner và trạng thái mặc định ở server. Trong một hệ thống thật, service có thể chạy trong transaction để bảo đảm trạng thái lưu nhất quán.

**Update:** tải entity theo ID từ URL, kiểm tra quyền và các điều kiện nghiệp vụ, rồi gán từng field cho phép. Không tạo một entity mới từ body rồi `save` đè toàn bộ khi điều đó làm mất các giá trị server-owned.

**Search:** biến search DTO thành câu truy vấn/read model; không chuyển nó thành entity rồi lưu. `page` và `size` là metadata cho truy vấn, không phải thuộc tính của `Book`.

Ví dụ mapping có chủ đích:

~~~java
// Mã minh họa trong service: giả định entity và repository tồn tại.
Book createEntity(BookCreateRequest request, long currentOwnerId) {
    Book book = new Book();
    book.setTitle(request.title().trim());
    book.setAuthor(request.author().trim());
    book.setPrice(request.price());
    book.setStock(request.initialStock());
    book.setOwnerId(currentOwnerId); // Danh tính từ server
    return book;                       // ID/timestamps do persistence quản lý
}

void applyUpdate(Book entity, BookUpdateRequest request) {
    entity.setTitle(request.title().trim());
    entity.setPrice(request.price());
    entity.setStock(request.stock());
    // Không động đến id, author, ownerId, createdAt...
}
~~~

Code trên **không chạy độc lập** vì các API `Book` và cơ chế persistence phụ thuộc ứng dụng. Đối tượng request bất biến giúp tránh sửa dữ liệu đầu vào sau khi validate; bản thân việc mapping vẫn phải dựa trên field whitelist và chính sách nghiệp vụ. Có thể dùng MapStruct để giảm code lặp, nhưng phải cấu hình rõ field đích được map, đặc biệt khi cập nhật entity hiện có.

Nếu trước đây dùng `BeanUtils.copyProperties(request, entity)` hoặc mapper tự động lên toàn bộ property theo tên, cần xem xét thật kỹ các field mới xuất hiện về sau, property lồng nhau, giá trị null và đối tượng quan hệ. Những tiện ích đó không thay thế một hợp đồng field được phép.

## 11. Lỗi thường gặp và cách khắc phục

### 11.1. Dùng entity JPA làm `@ModelAttribute` hoặc `@RequestBody`

Rủi ro: request có thể chạm các thuộc tính khác dự kiến, làm lộ trường nội bộ hoặc thay đổi quan hệ không mong muốn. Khắc phục: dùng request DTO theo use case và giới hạn field binding; không xuất entity trực tiếp làm response khi có dữ liệu nhạy cảm hoặc quan hệ phức tạp.

### 11.2. Dùng một DTO với quá nhiều field tùy chọn

Khi `id`, `keyword`, `page`, `title`, `price` đều nullable trong cùng lớp, code rất khó phân biệt dữ liệu thiếu, không áp dụng, giá trị hợp lệ và yêu cầu thay đổi. Khắc phục: định nghĩa sự hiện diện và bắt buộc của field theo từng hành động.

### 11.3. Dùng `@NotNull` cho trường tìm kiếm tùy chọn

Khi không truyền `minPrice`, truy vấn có thể hợp lệ. `@NotNull` ở đây khiến API từ chối một yêu cầu đúng. Chỉ áp dụng validation phù hợp với semantics của search.

### 11.4. Tưởng `@InitBinder.setAllowedFields` cũng chặn JSON

`@InitBinder` điều chỉnh data binding cho model attribute qua `WebDataBinder`. JSON `@RequestBody` được đọc bởi `HttpMessageConverter`; hãy dùng kiểu request dành riêng với các property được phép và chính sách deserialization rõ ràng. Không phụ thuộc vào khả năng Jackson tự bỏ qua unknown field để thay thế kiểm soát quyền.

### 11.5. Bỏ qua `BindingResult` khi search

Ví dụ `GET /api/books?page=abc` có thể tạo lỗi chuyển kiểu. Nếu không kiểm tra lỗi mà chạy truy vấn với dữ liệu được bind một phần, service có thể xử lý sai. Đặt `BindingResult` sát sau `@ModelAttribute` và từ chối truy vấn khi có lỗi. Với JSON, xử lý lỗi đọc body/validation qua exception mapping phù hợp.

### 11.6. Cập nhật entity từ body trước khi kiểm tra quyền

DTO chỉ giới hạn **hình dạng dữ liệu**, không xác nhận người gọi có được sửa `bookId` hay không. Service phải kiểm tra authorization theo người gọi và bản ghi cụ thể trước khi thay đổi hoặc lưu.

### 11.7. Cho tìm kiếm truy vấn vô hạn

Request `size=1000000` hoặc sort theo mọi cột có thể gây tải hệ thống lớn. Hạn chế kích thước trang, số điều kiện và danh sách sort field; chuyển câu truy vấn thành tham số chuẩn bằng repository/query builder, không nối SQL từ input.

### 11.8. Dùng một kiểu cập nhật cho cả PUT và PATCH

Nếu request bỏ `price`, nó có nghĩa “không cập nhật giá” hay “giá bằng null”? Nếu không có hợp đồng rõ ràng, hệ thống dễ xóa dữ liệu hoặc giữ dữ liệu trái kỳ vọng. Tạo mô hình PATCH có dấu hiệu field hiện diện nếu thật sự cần cập nhật một phần.

## 12. Kiểm thử ranh giới giữa ba kiểu đầu vào

Các tình huống nên được kiểm tra bằng Spring MVC test (ví dụ `MockMvc`) kết hợp kiểm thử service:

| Request | Điều cần kiểm tra |
|---|---|
| `POST /api/books` với đủ field hợp lệ | Trả `201`, tạo bản ghi đúng, ID do server cấp |
| POST thiếu `title` hoặc `initialStock` | Validation từ chối; service không lưu |
| POST có field server-owned như `ownerId` | Field đó không điều khiển entity; có thể từ chối unknown JSON theo cấu hình API |
| `PUT /api/books/101` với dữ liệu hợp lệ | Chỉ `title`, `price`, `stock` được cập nhật; `author`/`ownerId` giữ nguyên |
| PUT thiếu `price` | Bị từ chối vì hợp đồng PUT yêu cầu giá |
| PUT với ID không tồn tại | `404` theo chính sách API, không tạo bản ghi mới ngầm |
| PUT với người gọi không có quyền | `403` hoặc xử lý từ chối theo chính sách bảo mật, không ghi database |
| GET không có query params | Dùng bộ lọc rỗng, `page=0`, `size=20` |
| GET với `size=0` / `size=1000` | Validation từ chối |
| GET với `minPrice=300&maxPrice=100` | Ràng buộc liên trường từ chối |
| GET với `page=abc` | Bắt được lỗi type mismatch qua `BindingResult`, không chạy truy vấn |
| GET hợp lệ | Không cập nhật dữ liệu; kết quả tuân theo filter và pagination thực tế |

Để kiểm tra kỹ, dùng spy/mock service hoặc repository xác nhận **không phát sinh thao tác ghi** với tìm kiếm và với request create/update không hợp lệ. Đồng thời kiểm tra field bị chặn hoặc không hỗ trợ không thể tự biến thành dữ liệu nội bộ của entity.

## 13. Quy tắc chọn kiểu đầu vào

Khi thiết kế một endpoint mới, lần lượt xác định:

1. **Hành động là gì?** Tạo mới, cập nhật đầy đủ, cập nhật một phần hay truy vấn? Mỗi thao tác nên có hợp đồng rõ.
2. **Dữ liệu đến từ đâu?** Body JSON qua `@RequestBody`, query/form qua `@ModelAttribute`, path qua `@PathVariable`; mỗi nguồn có đường binding và lỗi tương ứng.
3. **Client được phép cung cấp field nào?** Chỉ khai báo field đó trên DTO; server sở hữu ID, user identity, timestamps, role và các giá trị nội bộ.
4. **Thiếu và null có nghĩa gì?** Bắt buộc cho create/PUT; tùy chọn cho search; PATCH phải phân biệt “không gửi” với “đặt null” khi nghiệp vụ yêu cầu.
5. **Kiểm tra ở lớp nào?** Bean Validation cho cấu trúc/giới hạn input; service/domain cho quyền, quan hệ liên trường, tồn tại bản ghi, đồng thời và invariants.
6. **Kết quả trả ra gồm gì?** Dùng response DTO có trường phù hợp, không phải mặc định đưa nguyên entity hoặc request object về client.

**Ý tưởng cốt lõi:** `BookCreateRequest` diễn đạt *cần gì để tạo*, `BookUpdateRequest` diễn đạt *được phép thay đổi gì*, còn `BookSearchQuery` diễn đạt *được phép hỏi gì*. Việc tách chúng giúp data binding và validation rõ nghĩa, giảm lỗi cập nhật ngoài ý muốn, đồng thời cho phép từng endpoint phát triển mà không ép toàn bộ hệ thống thay đổi cùng một lớp đầu vào.

### Tài liệu tham khảo

- [Spring Framework — Data Binding trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
