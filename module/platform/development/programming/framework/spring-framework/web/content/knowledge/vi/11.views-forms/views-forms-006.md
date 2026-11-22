# Redirect, forward và mẫu Post/Redirect/Get trong Spring MVC

## 1. Vì sao cần phân biệt redirect, forward và Post/Redirect/Get?

Trong ứng dụng web dùng **Spring MVC** và các biểu mẫu HTML, sau khi xử lý một HTTP request, controller có thể:

1. Trả về một **view** để render ngay trong response hiện tại.
2. **Redirect**: yêu cầu trình duyệt gửi một request mới tới URL khác.
3. **Forward**: chuyển cùng request sang một tài nguyên/handler khác trong server qua Servlet `RequestDispatcher`.
4. Áp dụng **Post/Redirect/Get (PRG)**: xử lý dữ liệu của `POST`, sau đó redirect tới một `GET` để người dùng xem kết quả an toàn hơn khi refresh.

Ba hành vi này không tương đương. Nhầm lẫn có thể dẫn tới người dùng vô tình gửi biểu mẫu lần nữa, mất thông báo thành công, để lộ dữ liệu trên URL hoặc có các test trả HTTP status không như mong đợi.

Ví dụ người dùng mở form tạo sách tại `GET /books/new`, nhập tiêu đề rồi nhấn nút “Lưu”. Nếu handler `POST /books` ghi vào database rồi **trả HTML thành công trực tiếp cho POST**, nút Refresh có thể khiến trình duyệt cảnh báo resubmit form. PRG đổi bước hiển thị kết quả thành một GET riêng, ví dụ `GET /books/42`.

**Phạm vi:** Spring Web MVC **Servlet stack**, controller trả view (Thymeleaf/JSP) và browser form. Các ví dụ đầy đủ dùng **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**. Khái niệm redirect của HTTP cũng liên quan REST API, nhưng đây không phải cơ chế điều hướng tự động của SPA JavaScript hoặc Spring WebFlux.

## 2. Ba luồng xử lý HTTP nhìn từ client

### 2.1. Render một view ngay

```text
Browser                    Spring MVC
   | GET /books/new              |
   |---------------------------->|
   |                             | controller return "books/new"
   | 200 OK + HTML               | -> ViewResolver -> Thymeleaf
   |<----------------------------|
   |
Address bar: /books/new
```

Không có chuyển hướng. Controller chỉ định **tên view** `books/new`; Thymeleaf render HTML. Trình duyệt vẫn hiển thị URL ban đầu.

Nếu controller xử lý `POST` và cũng trả `"books/result"` trực tiếp, response ấy thuộc request POST; refresh trang có thể dẫn đến trình duyệt đề nghị gửi lại POST.

### 2.2. Redirect: có hai request độc lập

```text
Browser                           Spring MVC
   | POST /books                        |
   |---------------------------------->|
   |                                    | validate + save
   | 302 Found                          |
   | Location: /books/42                |
   |<----------------------------------|
   |                                    |
   | GET /books/42                      |
   |---------------------------------->|
   |                                    | load + render detail view
   | 200 OK + HTML                      |
   |<----------------------------------|
   |
Address bar: /books/42
```

Controller có thể trả `"redirect:/books/42"`. Spring MVC xử lý prefix đặc biệt `redirect:`, tạo redirect view để trả status `3xx` và header `Location` cho browser. Browser quyết định có theo redirect và gửi request mới không; `curl` không tự theo redirect trừ khi yêu cầu `-L`.

**Một redirect không phải forward:** request GET mới có request parameters, headers, body và lifecycle riêng. Những object request-scoped, `Model` cũ, `BindingResult` cũ không tự động đi theo. Cần lưu dữ liệu cần thiết bằng URL params hoặc flash attributes tùy ý nghĩa.

### 2.3. Forward: cùng request được chuyển bên trong server

```text
Browser                          Spring MVC / Servlet
   | GET /books/forward-demo              |
   |------------------------------------->|
   |                                       | handler A
   |                                       | return "forward:/books/forward-target"
   |                                       | RequestDispatcher.forward(...)
   |                                       | handler B / target resource
   | 200 OK + HTML từ đích                 | (không HTTP 3xx)
   |<-------------------------------------|
   |
Address bar: /books/forward-demo
```

`forward:` trong Spring MVC tạo chuyển tiếp nội bộ bằng Servlet `RequestDispatcher.forward()` khi được một `UrlBasedViewResolver` phù hợp xử lý. Browser **không nhận Location redirect**, không tự gửi request mới và thanh địa chỉ vẫn hiển thị URL gốc.

Trong forward, request và response vẫn thuộc cùng vòng đời dispatch của Servlet. Các request attributes có thể được chia sẻ cho tài nguyên đích; bộ lọc/interceptor có thể có cách chạy khác tùy `DispatcherType.FORWARD`, mapping và container. Đây **không** là cách truy cập host ở bên ngoài bằng trình duyệt.

### So sánh ngắn

| Tiêu chí | Render view trực tiếp | Redirect | Forward |
| --- | --- | --- | --- |
| Trình duyệt tạo request mới? | Không | **Có**, nếu nó theo redirect | Không |
| HTTP response trung gian | `200` hoặc status của handler | `3xx` + `Location` | Không có `3xx` từ forward |
| URL trên thanh địa chỉ | Giữ URL gốc | Đổi sang URL đích | Giữ URL gốc |
| Request method đến đích | Không có request đích | Tùy `3xx` và client; PRG thường sang GET | Giữ request hiện tại (vd POST vẫn POST) |
| Request attributes | Có trong request hiện tại | Không tự mang theo | Có thể dùng lại |
| Model & flash data | Model render view ngay | URL attrs / flash attrs | Dữ liệu truyền qua request attributes/model tùy view |
| Tới domain khác | Không | Có thể, nếu cho phép | Không |
| Phù hợp sau POST thành công | Có thể gây resubmit | **Có, theo PRG** | Không thay được PRG |

## 3. Redirect trong Spring MVC: hai cách triển khai

### 3.1. Trả logical view name bắt đầu bằng redirect:

Controller dùng `@Controller` (không phải `@RestController`) có thể trả chuỗi:

```java
@PostMapping("/books")
public String create() {
    // Ghi dữ liệu thành công, đã nhận được ID 42.
    return "redirect:/books/42";
}
```

Đây là **method minh họa**, cần đặt trong class controller với annotations/imports. `redirect:` là **view name prefix**, không phải text để gửi làm HTTP response body. Nếu method thuộc `@RestController`, một `String` thông thường được xử lý như **response body**, nên client có thể thấy đúng chữ `redirect:/books/42` thay vì được điều hướng.

Đối với `redirect:/books/42`, `RedirectView` thường dùng HTTP `302 Found` theo mặc định tương thích HTTP/1.0 của Spring MVC 6.1. Browser hiện đại thường làm GET khi theo `302` sau POST, nhưng nếu cần semantics **rõ ràng bắt buộc GET**, HTTP `303 See Other` là lựa chọn phù hợp hơn (xem mục 4).

Spring MVC nhận diện prefix `redirect:` qua view resolution infrastructure, nên tên này **khác** `"books/42"` (được coi là tên template). URL tương đối, dấu `/`, context path và reverse proxy có thể ảnh hưởng URL Location cuối cùng. Hãy kiểm tra behavior với `server.servlet.context-path` nếu ứng dụng được triển khai dưới context khác `/`.

### 3.2. Trả RedirectView khi cần tùy chỉnh status

```java
@GetMapping("/go")
public RedirectView go() {
    RedirectView view = new RedirectView("/books/42");
    view.setContextRelative(true);
    view.setHttp10Compatible(false);
    return view;
}
```

Đây cũng là snippet nằm trong controller, với import `org.springframework.web.servlet.view.RedirectView`. Cờ `http10Compatible=false` làm `RedirectView` dùng **`303 See Other` mặc định** trong đường HTTP/1.1 thay vì dựa vào `sendRedirect` với 302. Cũng có thể thiết lập `setStatusCode(HttpStatus.SEE_OTHER)` trong cấu hình thích hợp.

Đối với PRG cần `303`, logic điển hình là sau POST lưu dữ liệu thành công rồi trả `RedirectView` hướng tới URL GET. Tuy nhiên không nên trộn tùy ý giữa `Model` và `RedirectView`; nên dùng `RedirectAttributes` để kiểm soát những giá trị được xuất lên URL/flash.

### 3.3. Với REST API không render view

Đối với một endpoint JSON thuần, HTTP redirect vẫn có thể trả bằng `ResponseEntity<Void>`:

```java
return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create("/api/orders/42"))
        .build();
```

Đây là snippet trong method trả `ResponseEntity<Void>`, cần imports `HttpStatus`, `ResponseEntity` và `java.net.URI`. `303` cho client biết nên dùng GET để truy cập representation khác. Không mặc định mọi `fetch()`/HTTP client sẽ tự điều hướng UI như browser; client JavaScript có cơ chế redirect/fetch riêng. REST API tạo resource cũng thường trả `201 Created` và `Location`; lựa chọn status phải theo contract ứng dụng, không ép mọi API viết JSON sang PRG.

## 4. Hiểu đúng 301, 302, 303, 307 và 308

| HTTP status | Ngữ nghĩa chính | Phương thức của request tiếp theo |
| --- | --- | --- |
| `301 Moved Permanently` | Resource được chuyển lâu dài | Với POST, một số user agent **có thể đổi sang GET** theo quy tắc HTTP |
| `302 Found` | Redirect tạm thời | Với POST, browser thường đổi GET, nhưng không nên dựa vào đó như bảo đảm phương thức |
| `303 See Other` | Xem resource/confirmation khác sau request trước | **Client thực hiện retrieval request (thường GET)**; phù hợp PRG |
| `307 Temporary Redirect` | Redirect tạm thời, bảo toàn method và body | **Không đổi method** theo semantics HTTP |
| `308 Permanent Redirect` | Redirect lâu dài, bảo toàn method và body | **Không đổi method** theo semantics HTTP |

**Với POST ghi dữ liệu, không dùng 307/308 làm cơ chế PRG**: client sẽ gửi POST đến URL mới và vẫn có nguy cơ thực hiện write ngoài ý định. `302` là lựa chọn mặc định phổ biến trong Spring MVC, nhưng `303` diễn tả ý định POST thành công → xem GET rõ ràng hơn.

Với URL GET cũ được chuyển lâu dài sang GET mới, `301/308` có thể phù hợp, nhưng việc cache redirect và bảo toàn method cần được cân nhắc. Không chọn mã redirect chỉ dựa trên số hàng `3xx`.

**Không được suy luận:** “HTTP 302 chắc chắn luôn GET”. HTTP client và các trường hợp method khác nhau có hành vi khác. Contract tests nên xác nhận server gửi đúng `Location` và status; browser/integration tests riêng nên xác nhận user agent thực sự theo đường bạn mong muốn.

## 5. Post/Redirect/Get (PRG): giải quyết form resubmission

### 5.1. Vấn đề khi trả view trực tiếp từ POST

Luồng **không có PRG**:

```text
GET /books/new -> form
POST /books   -> lưu sách và trả HTML thành công ngay
Refresh       -> có thể gửi lại POST /books
                  -> tạo bản ghi trùng / thanh toán trùng / xử lý lần nữa
```

Nếu form chỉ trình bày thông tin không thay đổi server thì rủi ro thấp, nhưng với tạo đơn, chuyển tiền, đặt hàng, đăng ký tài khoản, việc gửi lại có thể gây hậu quả. Browser hiện đại đôi khi cảnh báo trước resubmit, nhưng không được coi cảnh báo UI là rào chắn nghiệp vụ.

### 5.2. PRG đổi trang cuối thành GET

```text
1. GET /books/new
   -> HTML form

2. POST /books với title=Clean+Code
   -> validate
   -> nếu hợp lệ: lưu sách ID 42
   -> HTTP 302 (hoặc 303), Location: /books/42

3. GET /books/42
   -> lấy sách vừa lưu
   -> render view chi tiết, HTTP 200

4. Refresh
   -> GET /books/42
   -> không chạy lại POST /books
```

Đây là **mẫu tương tác hai bước cho thao tác write thành công**. URL GET cuối cùng có thể lưu bookmark, chia sẻ, refresh, và về mặt HTTP là truy vấn một resource đã có.

**PRG không bảo đảm exactly-once processing.** Người dùng có thể double-click gửi hai POST trước khi nhận redirect; proxy/client retry hoặc timeout trước redirect cũng có thể tạo hai yêu cầu. Với giao dịch quan trọng cần **idempotency key**, unique constraints, transactional guards, optimistic locking hoặc các biện pháp tương ứng. PRG chủ yếu giải quyết UX và trường hợp refresh form response sau POST, không thay thế cơ chế chống xử lý trùng ở server.

### 5.3. Thành công redirect, thất bại validation thì render lại form

Quy tắc thường dùng:

- **POST hợp lệ:** save → redirect tới GET.
- **POST không hợp lệ:** giữ `BindingResult` và object form trong **cùng request**, trả lại tên view form để hiển thị lỗi; không cần redirect.
- **GET chi tiết:** đọc dữ liệu mới từ service/database rồi render; không trông đợi toàn bộ form object từ request POST vẫn tồn tại.

Vì `BindingResult` là dữ liệu request/model, tự redirect khi validation fail sẽ làm mất lỗi trừ khi bạn **chủ động** vận chuyển form và binding errors qua flash/session. Cách trực tiếp là `return "books/new"` khi có errors.

## 6. RedirectAttributes: dữ liệu trên URL và flash attributes

Spring MVC hỗ trợ `org.springframework.web.servlet.mvc.support.RedirectAttributes` để kiểm soát dữ liệu đi theo redirect. Có hai nhánh **phải phân biệt**:

```java
redirectAttributes.addAttribute("id", book.id());
redirectAttributes.addFlashAttribute(
        "success", "Đã tạo sách thành công");
return "redirect:/books/{id}";
```

Đây là đoạn trong POST handler, không phải chương trình Java độc lập.

### 6.1. addAttribute: URL path/query

`addAttribute("id", 42)` có thể điền placeholder `{id}` của `redirect:/books/{id}`, tạo Location `/books/42`. Nếu còn primitive/string redirect attributes không dùng để expand URL, Spring có thể biến chúng thành **query parameters**.

Ví dụ:

```java
redirectAttributes.addAttribute("tab", "details");
return "redirect:/books/{id}";
```

Nếu `id=42` đã có và cả `tab` được thêm, URL có thể thành `/books/42?tab=details`. URL-encoded query phù hợp với dữ liệu **không nhạy cảm** có ý nghĩa điều hướng. Không dùng query params cho password, token, thông tin thẻ, session secrets hoặc thông báo nội bộ không muốn lưu browser history/proxy logs.

Lưu ý Spring MVC có hành vi lịch sử về việc đưa **default model attributes** vào URL khi redirect: những giá trị đơn giản trong model có thể thành query parameters nếu không kiểm soát. Khai báo `RedirectAttributes` và chỉ add những trường cần thiết giúp giảm rủi ro. Với ứng dụng phức tạp có thể xét tùy chọn `ignoreDefaultModelOnRedirect` trong `RequestMappingHandlerAdapter`, nhưng không nên sửa cấu hình toàn cục nếu chưa kiểm tra tác động.

### 6.2. addFlashAttribute: dữ liệu tạm cho GET tiếp theo

`addFlashAttribute("success","Đã tạo sách")` lưu tạm thông báo thành công vào output flash map. Sau redirect, Spring đặt dữ liệu flash vào model của request đích khi khớp; template có thể đọc `${success}`.

Ưu điểm:

- Không để thông báo trong URL, browser history và log truy cập.
- Không phải gửi cả dữ liệu vừa tạo qua query string.
- Thích hợp cho thông báo một lần kiểu “Đã lưu”, “Cập nhật thành công”.

Giới hạn cần nhớ:

- Flash attributes **thường được lưu tạm trong HTTP session** và được lấy ra khi request đích khớp; không phải cơ sở dữ liệu.
- Sau khi được tiêu thụ, message không có bảo đảm tồn tại khi refresh lần thứ hai hoặc mở bookmark về sau.
- Spring dùng `FlashMap` / `FlashMapManager`. RedirectView có thể “đóng dấu” path/query target lên flash map để giảm việc request khác lấy nhầm, nhưng **không loại bỏ hoàn toàn race conditions** nếu có request đồng thời ở nhiều tab hoặc polling.
- Không lưu đối tượng nghiệp vụ lớn, mật khẩu, token hoặc kết quả cần độ bền vững cao trong flash.
- Với session phân tán/multiple instances, cấu hình lưu session phải phù hợp; flash không thay database.
- Nếu client tắt/mất session cookie hoặc redirect tới môi trường khác không chia sẻ session, flash message có thể không đến đích.

### 6.3. Flash không phải session attribute dài hạn

`@SessionAttributes` và `HttpSession` dùng cho bài toán state qua nhiều request; flash dùng cho trao đổi tạm của một redirect. Nếu muốn thông báo bền vững hoặc kiểm tra quyền resource, GET đích phải truy cập service/database. Không coi flash là chứng cứ rằng người dùng đã được phép xem resource.

## 7. Ví dụ Spring Boot hoàn chỉnh: form, redirect, flash và forward

Ví dụ này có một ứng dụng Spring MVC hoạt động với Java 17 và Maven, gồm:

- `GET /books/new`: hiển thị form HTML.
- `POST /books`: validate title; thành công tạo sách trong bộ nhớ và trả `redirect:/books/{id}`.
- `GET /books/{id}`: render trang chi tiết, hiển thị flash message khi vừa redirect.
- `GET /books/forward-demo`: đặt một request attribute rồi forward nội bộ tới `/books/forward-target`.
- `GET /books/forward-target`: render view dựa trên request attribute.

Demo dùng in-memory `ConcurrentHashMap` và `AtomicLong` chỉ để chạy độc lập, **không phải persistence production**. Với hệ thống thật phải dùng service/repository, transactions, authorization, CSRF protection (nếu có web login/session) và idempotency cho thao tác quan trọng.

### 7.1. Cấu trúc project

```text
prg-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/prg/
    │   │   ├── PrgDemoApplication.java
    │   │   ├── BookCatalog.java
    │   │   ├── BookForm.java
    │   │   └── BookController.java
    │   └── resources/templates/books/
    │       ├── new.html
    │       ├── detail.html
    │       └── forward-target.html
    └── test/java/example/prg/
        └── BookControllerTests.java
```

Mỗi public Java class phải được lưu đúng tên file và package như cây thư mục.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>prg-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/prg/PrgDemoApplication.java`**

```java
package example.prg;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrgDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrgDemoApplication.class, args);
    }
}
```

### 7.2. Catalog lưu trong bộ nhớ

**`BookCatalog.java`**

```java
package example.prg;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    public record Book(long id, String title) {}

    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    public Book create(String title) {
        long id = sequence.incrementAndGet();
        Book book = new Book(id, title);
        books.put(id, book);
        return book;
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }
}
```

`AtomicLong` tạo ID tăng theo từng instance; `ConcurrentHashMap` an toàn cho truy cập đồng thời trong phạm vi demo. Khi restart server, dữ liệu biến mất. Đừng dùng cách này để triển khai đơn hàng thật: cần lưu bền vững, kiểm soát concurrency, transaction và quy tắc duplicate/idempotency.

### 7.3. Form DTO với Bean Validation

**`BookForm.java`**

```java
package example.prg;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class BookForm {
    @NotBlank
    @Size(max = 80)
    private String title;

    public BookForm() {}

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Đây là **input DTO** riêng của form, không phải database entity. `@NotBlank` từ chối chuỗi rỗng hoặc toàn whitespace, `@Size(max=80)` đặt giới hạn. `@Valid @ModelAttribute` sẽ chạy validation khi POST được bind, và `BindingResult` cho controller đọc các lỗi.

### 7.4. Controller: POST hợp lệ redirect, POST sai render lại form

**`BookController.java`**

```java
package example.prg;

import example.prg.BookCatalog.Book;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("bookForm", new BookForm());
        return "books/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("bookForm") BookForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "books/new";
        }

        Book book = catalog.create(form.getTitle().strip());

        redirectAttributes.addAttribute("id", book.id());
        redirectAttributes.addFlashAttribute(
                "success", "Đã tạo sách thành công");

        return "redirect:/books/{id}";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        Book book = catalog.find(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Book not found"));
        model.addAttribute("book", book);
        return "books/detail";
    }

    @GetMapping("/forward-demo")
    public String forwardDemo(HttpServletRequest request) {
        request.setAttribute("forwardMarker", "from-first-handler");
        return "forward:/books/forward-target";
    }

    @GetMapping("/forward-target")
    public String forwardTarget(
            HttpServletRequest request, Model model) {
        Object marker = request.getAttribute("forwardMarker");
        model.addAttribute("marker",
                marker == null ? "none" : marker);
        return "books/forward-target";
    }
}
```

Các điểm cần quan sát trong file:

1. `@Controller` (không phải `@RestController`) để `String` được hiểu là **view name**.
2. `@Valid @ModelAttribute("bookForm")` nhận dữ liệu form, không yêu cầu JSON body. `BindingResult` đứng **ngay sau** đối tượng cần validate.
3. Khi lỗi, controller trả `"books/new"` trong **POST hiện tại** để Thymeleaf lấy `BindingResult` và hiển thị lỗi. Không tạo sách và không redirect.
4. Khi hợp lệ, `catalog.create` chạy **một lần trong request POST**, tạo ID.
5. `addAttribute("id", id)` phục vụ placeholder `{id}`; `addFlashAttribute("success",...)` giữ notification một lần.
6. `"redirect:/books/{id}"` tạo 3xx + Location; browser theo đến `GET /books/{id}`.
7. `detail` nạp lại dữ liệu bằng ID, không lấy Book từ flash. Flash `success` được Spring tự đưa vào model của GET tương ứng.
8. `forwardDemo` đặt request attribute và `forward:` chuyển cùng request tới handler thứ hai; `forwardTarget` nhận `marker` rồi render view.
9. Nếu ID không có, `ResponseStatusException` cho phản hồi `404` theo cấu hình Spring Boot. Template `detail` không được render với object giả.
10. URL `/books/new` và `/books/forward-demo` cụ thể hơn pattern `/books/{id}`; Spring chọn mapping phù hợp, không cần viết điều kiện `id` thủ công cho các path cố định.

Trong hệ thống thật, `@ControllerAdvice` hoặc error view có thể được dùng để trình bày `404` nhất quán; điều này nằm ngoài trọng tâm PRG.

### 7.5. Template form Thymeleaf

**`src/main/resources/templates/books/new.html`**

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Tạo sách</title>
</head>
<body>
    <h1>Tạo sách</h1>
    <form th:action="@{/books}" th:object="${bookForm}"
          method="post">
        <label for="title">Tiêu đề</label>
        <input id="title" type="text" th:field="*{title}"
               maxlength="80" required>
        <p th:if="${#fields.hasErrors('title')}"
           th:errors="*{title}">Lỗi tiêu đề</p>
        <button type="submit">Lưu</button>
    </form>
</body>
</html>
```

Các biểu thức `th:object="${bookForm}"` và `th:field="*{title}"` kết nối template với model/form DTO; Spring MVC + Thymeleaf có tích hợp lấy BindingResult. HTML `required` và `maxlength` hỗ trợ trải nghiệm người dùng, **không thay thế** Bean Validation phía server (client có thể bỏ qua mọi kiểm tra HTML).

### 7.6. Template chi tiết và flash message

**`src/main/resources/templates/books/detail.html`**

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chi tiết sách</title>
</head>
<body>
    <p th:if="${success}" th:text="${success}">
        Thông báo
    </p>
    <h1 th:text="${book.title}">Tiêu đề sách</h1>
    <p>
        ID: <span th:text="${book.id}">0</span>
    </p>
    <a th:href="@{/books/new}">Tạo sách khác</a>
</body>
</html>
```

Khi vừa redirect sau POST hợp lệ, GET đầu tiên thường thấy flash `success`. Khi refresh GET hoặc truy cập link chi tiết trực tiếp, phần thông báo không bắt buộc xuất hiện vì flash đã được tiêu thụ; thông tin sách vẫn đến từ `catalog.find(id)`.

Với Thymeleaf, `th:text` escape HTML output thông thường; không dùng `th:utext` cho nội dung do user nhập trừ khi đã có chiến lược sanitize phù hợp. Đây là một lợi ích của template escaping, nhưng không thay authorization hay các quy tắc bảo mật.

### 7.7. Template minh họa forward

**`src/main/resources/templates/books/forward-target.html`**

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Forward target</title>
</head>
<body>
    <h1>Forward đã tới đích</h1>
    <p th:text="${marker}">none</p>
</body>
</html>
```

Mở `GET /books/forward-demo`. Controller ban đầu đặt request attribute `forwardMarker`. Đường `forward:/books/forward-target` thực hiện chuyển tiếp nội bộ; handler đích đọc attribute và đưa `marker` vào view. Browser vẫn hiển thị URL `/books/forward-demo`; không có Location 302.

**Tại sao không dùng forward sau POST tạo sách?** Forward **giữ method POST**, khiến trang cuối vẫn là kết quả của POST ban đầu, không tạo request GET mới. Refresh có thể resubmit POST hoặc browser cảnh báo. PRG phải dùng redirect.

## 8. Kiểm tra thủ công bằng browser và curl

Từ thư mục `prg-demo`, cần cài Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh là các bước **chạy tuần tự**; `mvn test` kết thúc rồi mới chạy `mvn spring-boot:run`. Ví dụ mặc định sử dụng `localhost:8080` nếu không thay `server.port`.

### 8.1. Xem form

Truy cập browser:

```text
http://localhost:8080/books/new
```

Dự kiến response `200 OK` với form có trường `title`. Chưa có database nên form không hiển thị danh sách sách; nó chỉ tạo một bản ghi in-memory khi POST.

### 8.2. POST hợp lệ: quan sát redirect mà không tự follow

```bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Clean Code'
```

Dự kiến có:

```http
HTTP/1.1 302
Location: http://localhost:8080/books/1
```

Spring/container có thể ghi `Location` thành URL tuyệt đối hoặc tương đối theo cấu hình, reverse proxy, context path. Phần chắc chắn cần test ở mức hợp đồng là **3xx và đích `/books/1`**, không phải bắt buộc host/định dạng Location y nguyên trong mọi môi trường. Với instance sạch, ID đầu tiên là `1`; nếu trước đó đã tạo sách, ID sẽ lớn hơn.

Browser tự follow redirect khi submit form. `curl` **mặc định không theo redirect**; dùng `curl -L` nếu muốn follow và quan sát response cuối. Khi POST qua curl, tránh ép `-X POST` kết hợp `-L` nếu đang kiểm tra việc đổi method, vì option `-X` khiến cách hiển thị/gửi method khác hành vi tự động mong muốn. Dùng:

```bash
curl -i -L \
  -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Domain-Driven Design' \
  http://localhost:8080/books
```

`-c/-b` giúp lưu/gửi session cookie giữa các requests do curl theo redirect, cần thiết nếu muốn nhận flash attribute qua session. Nếu nghi ngờ chuyển POST sang GET không đúng với client/tool, kiểm tra redirect method bằng `curl -v` và status; với PRG nghiêm ngặt, dùng 303 như mục 10.

### 8.3. GET trang chi tiết

Sau khi xác định ID được tạo, gọi:

```bash
curl -i http://localhost:8080/books/1
```

Response `200 OK` có HTML chứa sách ID 1 **nếu sách đã được tạo trong instance hiện tại**. Nếu chưa tạo hoặc server restart, `/books/1` có thể trả `404`, đúng với in-memory catalog demo.

### 8.4. POST không hợp lệ

```bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=   '
```

Dự kiến HTTP `200 OK` với view form có thông báo lỗi validation của `@NotBlank`, **không** có header `Location` redirect và **không** có bản ghi mới. Mẫu này có thể không gửi status `400` vì form HTML truyền thống thường render lỗi trong cùng trang `200`; với REST JSON API thì thường nên trả `400` theo contract.

### 8.5. Forward nội bộ

```bash
curl -i http://localhost:8080/books/forward-demo
```

Response dự kiến `200 OK`, không có redirect 3xx; HTML có chữ `from-first-handler`. `curl` không cần `-L` vì request không phát sinh redirect ra client. Thanh địa chỉ browser giữ `/books/forward-demo`.

## 9. Kiểm thử với MockMvc

`MockMvc` kiểm tra status, view name, redirect location, flash map và forward dispatch mà không cần một HTTP server port thật. Với ví dụ Thymeleaf có thể dùng `@SpringBootTest` để nạp đủ application context, renderer và bean `BookCatalog`.

**`src/test/java/example/prg/BookControllerTests.java`**

```java
package example.prg;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormRendersView() throws Exception {
        mvc.perform(get("/books/new"))
           .andExpect(status().isOk())
           .andExpect(view().name("books/new"))
           .andExpect(model().attributeExists("bookForm"));
    }

    @Test
    void validPostRedirectsAndStoresFlashMessage() throws Exception {
        mvc.perform(post("/books")
                    .param("title", "Clean Code"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrlPattern("/books/*"))
           .andExpect(flash().attribute(
                    "success", "Đã tạo sách thành công"));
    }

    @Test
    void invalidPostRendersFormWithBindingError() throws Exception {
        mvc.perform(post("/books")
                    .param("title", "   "))
           .andExpect(status().isOk())
           .andExpect(view().name("books/new"))
           .andExpect(model().attributeHasFieldErrors(
                    "bookForm", "title"));
    }

    @Test
    void forwardDoesNotReturnRedirectStatus() throws Exception {
        mvc.perform(get("/books/forward-demo"))
           .andExpect(status().isOk())
           .andExpect(forwardedUrl("/books/forward-target"));
    }

    @Test
    void missingBookReturnsNotFound() throws Exception {
        mvc.perform(get("/books/999999999"))
           .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
mvn test
```

Nếu tất cả 5 test methods pass, Maven kết thúc thành công với exit code `0` và có thông tin đại ý `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. Thứ tự log, thời gian và cấu trúc report cụ thể phụ thuộc môi trường.

**Lưu ý về MockMvc forward:** Matcher `forwardedUrl(...)` kiểm tra URL mà MVC đã chuyển tiếp, **không đồng nghĩa** nó tự chạy lại toàn bộ request tới controller B giống một browser và servlet container thật. Nếu muốn kiểm tra HTML do target thực sự render qua forward, chạy integration test với embedded server `RANDOM_PORT` và HTTP client/browser.

**Lưu ý về flash:** Assertion `flash().attribute(...)` kiểm tra output flash map của response redirect. Để kiểm tra message xuất hiện trong request GET tiếp theo, test phải mô phỏng redirect **và duy trì flash/session đúng cách**, không tự cho rằng `MockMvc` đã follow redirect như browser. Trong hệ thống quan trọng, bổ sung một integration test giữa hai request để bảo vệ flash behavior.

## 10. Cách dùng 303 See Other rõ ràng cho PRG

Trong chương trình mẫu, `return "redirect:/books/{id}"` thường dẫn đến 302. Nếu API cần bảo đảm chuẩn HTTP method switching rõ ràng, sau khi lưu thành công có thể trả `RedirectView` cấu hình 303.

Snippet **thay thế logic sau khi tạo sách** trong POST handler:

```java
RedirectView redirect =
        new RedirectView("/books/" + book.id());
redirect.setContextRelative(true);
redirect.setHttp10Compatible(false);
redirect.setExposeModelAttributes(false);
return redirect;
```

Đoạn này cần thay **return type của method từ `String` sang `RedirectView` hoặc `View`**, và import `org.springframework.web.servlet.view.RedirectView`. Đây không phải một patch có thể thêm bên dưới `return "redirect:..."` mà không chỉnh method; cần làm theo phương án riêng. `RedirectAttributes.addFlashAttribute(...)` vẫn được xử lý khi return là một `RedirectView` thích hợp do Spring MVC, nhưng sau khi tắt expose model, URL phải được dựng rõ như ở snippet.

Một lựa chọn API-oriented khác là trả `ResponseEntity.status(HttpStatus.SEE_OTHER).location(...).build()`. Nếu bạn đang phục vụ HTML form với view + flash, `RedirectView` thường thuận tiện hơn. **Đừng đổi 302 sang 307/308** khi mục tiêu là GET sau POST.

## 11. Redirect và forward: lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Browser hiện chữ `redirect:/books/1` | Controller là `@RestController`/`@ResponseBody` | Dùng `@Controller` trả view name, hoặc trả HTTP redirect rõ bằng `ResponseEntity` |
| Refresh tạo record thứ hai | POST trả view ngay hoặc client gửi lại POST | Dùng PRG; thêm idempotency/transaction/unique constraint cho logic quan trọng |
| GET sau redirect không có dữ liệu từ POST | Redirect là request mới | GET tra database/service bằng ID; dữ liệu hiển thị tạm dùng flash |
| Flash message không hiện | Client không follow Location, không giữ session cookie, flash đã tiêu thụ | Test HTTP client/session và đường redirect |
| Flash message đôi khi biến mất giữa các tab | FlashMap có giới hạn về concurrency/race | Không dùng flash cho state bền vững, giảm request cạnh tranh |
| Form lỗi validation mất sau redirect | `BindingResult` thuộc request cũ | Khi invalid, render lại form; nếu phải redirect, truyền binding errors một cách có chủ đích |
| Thông tin nhạy cảm xuất hiện trong Location | `addAttribute` thêm query param vào redirect | Dùng ID an toàn, flash cho message tạm, không đặt secrets trên URL |
| Redirect tới URL sai khi dùng context path | URL tương đối/absolute hoặc proxy config sai | Kiểm tra context path, forwarded headers, `RedirectView.contextRelative` |
| Return `forward:` không chạy như mong đợi | View resolver không hỗ trợ prefix hoặc resource không dispatch được | Kiểm tra `UrlBasedViewResolver` và mapping Servlet đích |
| Refresh vẫn là POST sau forward | Forward giữ request/method | Dùng redirect cho PRG |
| Redirect 307/308 giữ POST ở destination | Hai status giữ method/body | Dùng 303 hoặc 302 tùy yêu cầu PRG |
| Browser báo redirect loop | A redirect tới B và B redirect về A | Kiểm tra auth guards/mapping, Location chain và cookie |
| Trang chi tiết không thấy flash sau bookmark/refresh | Flash chỉ dùng một lần | Lấy dữ liệu chính từ service; message chỉ là notification |
| Open redirect sang domain lạ | Đưa trực tiếp `next`/`returnUrl` của client vào `redirect:` | Allowlist đích nội bộ, xác minh URI và chuẩn hóa |
| POST thành công nhưng GET trả 404 | Chưa commit dữ liệu, read-after-write delay, sai ID, mất memory state | Kiểm tra transactions, consistency, persistence, đường Location |
| Spring Security báo 403 khi submit form | CSRF token thiếu hoặc không đúng | Bật CSRF đúng policy, đưa token vào HTML form và test với CSRF |

### Dùng POST/Redirect/Get với Spring Security

Trong project mẫu không thêm `spring-boot-starter-security` nên không có CSRF filter do Spring Security tự cài. Trong ứng dụng có đăng nhập bằng session/cookie và Spring Security, POST thay đổi trạng thái thường được bảo vệ bằng **CSRF token**. Khi dùng Thymeleaf với Spring Security tích hợp, Spring có thể hỗ trợ chèn token vào form; vẫn cần kiểm tra markup thực và test `MockMvc` có `csrf()` tương ứng. Không tắt CSRF chỉ để làm cho ví dụ PRG chạy.

**PRG không thay authorization**: GET `/books/{id}` phải kiểm tra quyền đối với sách nếu đó là tài nguyên riêng tư. Thông báo flash “đã lưu” không chứng minh người đang GET có quyền xem nội dung.

### Open redirect: rủi ro bảo mật quan trọng

Không làm như sau:

```java
// PHẢN VÍ DỤ: redirect đến URL client tự gửi vào mà chưa xác minh.
@GetMapping("/go")
public String unsafe(@RequestParam String next) {
    return "redirect:" + next;
}
```

Kẻ tấn công có thể dựng đường dẫn redirect đến trang giả mạo. Nếu phải nhận đích từ client, xác minh đích theo **allowlist** host/path, chỉ cho đường nội bộ đáng tin, chuẩn hóa và từ chối `//external.example`, scheme bất thường, URL encoding nhiều lần hoặc biến thể bypass. Tốt nhất lưu server-controlled destination key rồi map tới URL cố định, thay vì nhận raw target URL.

## 12. Phân biệt PRG với idempotency và transaction

PRG tạo request GET sau POST, nhưng trong hệ thống phân tán **POST có thể chạy hai lần trước redirect**. Một luồng thanh toán cần nhiều lớp bảo vệ:

```text
Browser -> POST /payments (Idempotency-Key: unique-operation-id)
             |
             v
      Check existing operation / uniqueness
             |
        +----+---------+
        |              |
        v              v
   first request    duplicate request
   transactional    return prior result
   write                 |
        |----------------|
        v
   303 See Other
   Location: /payments/{id}
        |
        v
   GET /payments/{id}
```

Mô hình này chỉ là ý tưởng; không có code thanh toán runnable ở bài. Key phải có scope theo principal/operation, lưu bền vững đủ lâu, xử lý races và consistent replay. Nếu client gửi hai request có body khác nhau cùng key, server cần quy tắc báo lỗi phù hợp. Unique constraint ở database thường bảo vệ invariant tốt hơn check-then-insert không có transaction.

Đối với form CRUD bình thường, PRG + unique constraint có thể đủ. Với thanh toán, đặt vé, chuyển tiền, order placement, cần idempotency key và giao dịch đúng nghiệp vụ. Không nhầm “refresh GET không resubmit POST” với “server đảm bảo không bao giờ xử lý POST trùng”.

## 13. Chọn cách nào cho từng yêu cầu?

| Tình huống | Cách nên dùng |
| --- | --- |
| GET trang HTML hoặc hiển thị lỗi form ngay | Trả view name thông thường |
| POST biểu mẫu hợp lệ, tạo resource và chuyển sang trang chi tiết | **PRG: redirect** |
| POST biểu mẫu không hợp lệ và cần hiển thị lỗi binding | Trả lại cùng view, giữ `BindingResult` |
| Cần thông báo thành công một lần sau redirect | `RedirectAttributes.addFlashAttribute` |
| Cần ID hoặc filter hiển thị công khai ở URL | `RedirectAttributes.addAttribute` |
| Cần chuyển tiếp cùng request sang servlet/handler nội bộ | `forward:...` khi thật sự cần |
| Cần trình duyệt chắc chắn dùng GET sau write | HTTP **303 See Other** |
| Cần redirect tạm nhưng bảo toàn POST method/body | `307` cho yêu cầu chuyên biệt; **không dùng cho PRG** |
| Cần chuyển URL GET cũ sang URL mới lâu dài | Cân nhắc `301/308` và ảnh hưởng cache/method |
| REST JSON tạo resource rồi trả JSON | `201 Created` + `Location` thường phù hợp |
| Cần chống POST trùng nghiêm ngặt | Idempotency/DB constraint/transaction **ngoài PRG** |

## 14. Bài tập tự kiểm tra

1. Khi handler `@Controller` trả `"redirect:/books/42"`, browser nhận gì? Nó có tạo request mới không?
2. Khi handler trả `"forward:/books/forward-target"`, URL trên thanh địa chỉ và HTTP method của request đích thay đổi thế nào?
3. Vì sao PRG giảm rủi ro resubmit sau refresh nhưng không thay idempotency key?
4. Trong `RedirectAttributes`, `addAttribute` khác `addFlashAttribute` ở vị trí và thời gian tồn tại dữ liệu?
5. Vì sao validation fail nên trả lại view form thay vì mặc định redirect?
6. Vì sao `303` diễn đạt mục tiêu PRG tốt hơn `307`?
7. Một method nằm trong `@RestController` trả string `"redirect:/books/42"`. Điều gì có thể xảy ra?
8. Nếu flash success message biến mất sau refresh GET, đây có phải lỗi cần sửa bằng cách lưu flash lâu dài không?
9. Khi controller dùng `return "redirect:/books/{id}"`, `addAttribute("id",42)` có mục đích gì?
10. Nếu client gửi `?next=https://untrusted.example` và server ghép vào redirect URL, rủi ro gì?
11. Tại sao `GET /books/42` nên tự tải thông tin sách từ service thay vì phụ thuộc `BookForm` của POST?
12. Khi test `forwardedUrl` bằng `MockMvc`, điều đó có khẳng định toàn bộ HTML đích đã được render qua Servlet container thật không?

**Gợi ý trả lời:** (1) HTTP 3xx + Location, client theo tạo request mới. (2) URL browser không đổi, cùng request/method được chuyển nội bộ. (3) Hai POST vẫn có thể đến trước redirect. (4) Attribute dùng URL/path/query, flash ở vùng lưu tạm (thường session) cho request đích. (5) BindingResult còn trong request hiện tại. (6) 303 yêu cầu retrieval/GET, 307 giữ method. (7) Có thể trả chuỗi làm body thay vì redirect. (8) Không, flash thiết kế tạm một lần. (9) Điền placeholder `{id}`. (10) Open redirect/phishing. (11) GET là contract độc lập/bookmarkable. (12) Không; cần integration test thực cho full forward dispatch.

## 15. Tài liệu tham khảo

- [Spring Framework 6.1 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Framework 6.1 — Flash Attributes](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/flash-attributes.html)
- [Spring Framework — View Resolution, Redirecting và Forwarding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Framework 6.1 — RedirectView Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html)
- [Spring Framework 6.1 — RedirectAttributes Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/support/RedirectAttributes.html)
- [Spring Framework — MVC Model và View](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-methods.html)
- [Spring Boot 3.3 — Spring MVC and Thymeleaf](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [RFC 9110 — HTTP Semantics, redirection 3xx](https://www.rfc-editor.org/rfc/rfc9110.html)

**Tóm tắt:** Redirect trả về hướng đi mới để client tự gửi request mới; forward chuyển tiếp nội bộ trong server; PRG là quy trình *POST lưu thành công → 3xx redirect → GET hiển thị*. Trong Spring MVC, `redirect:`, `forward:`, `RedirectAttributes` và các view resolvers cung cấp cơ chế triển khai. Dùng flash cho thông báo ngắn hạn, dùng service/database cho dữ liệu thật, và luôn kết hợp validation, authorization, CSRF/idempotency khi bài toán có yêu cầu bảo mật hoặc xử lý trùng.
