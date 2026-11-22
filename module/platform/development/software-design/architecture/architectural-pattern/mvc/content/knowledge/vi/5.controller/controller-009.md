# Xử lý yêu cầu không hợp lệ hoặc hành động không được hỗ trợ

## 1. Vai trò của Controller khi xử lý lỗi

Trong kiến trúc Model–View–Controller, **Controller** tiếp nhận HTTP request, phối hợp với tầng nghiệp vụ và chọn response phù hợp. Một request không phải lúc nào cũng hợp lệ hoặc có thể thực hiện. Dữ liệu có thể sai định dạng, tài nguyên có thể không tồn tại, người dùng có thể thiếu quyền, HTTP method có thể không được endpoint hỗ trợ, hoặc hành động nghiệp vụ có thể không hợp lệ với trạng thái hiện tại.

Controller cần chuyển những tình huống đó thành phản hồi nhất quán để người dùng hoặc client hiểu điều gì đã xảy ra. Việc xử lý lỗi tốt có ba mục tiêu:

- **Đúng ngữ nghĩa:** mã HTTP và nội dung phản hồi mô tả chính xác loại vấn đề.
- **Có thể khắc phục:** người dùng biết dữ liệu nào cần sửa, quyền nào còn thiếu hoặc thao tác nào không thể thực hiện.
- **An toàn:** phản hồi không làm lộ stack trace, câu truy vấn, thông tin xác thực hoặc chi tiết nội bộ.

Controller không nên tự chứa toàn bộ quy tắc phát hiện lỗi. Router, lớp bảo mật, binding/validation, Model, Service và cơ sở dữ liệu đều có thể phát hiện những loại lỗi khác nhau. Controller hoặc cơ chế xử lý ngoại lệ chung có nhiệm vụ ánh xạ chúng thành response phù hợp.

## 2. Nhận diện lỗi theo từng giai đoạn của request

Một request web đi qua nhiều bước. Vị trí phát hiện lỗi giúp xác định thành phần chịu trách nhiệm:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Routing]
    B -->|Không có route phù hợp| E1[404 Not Found]
    B -->|Route có nhưng method không hỗ trợ| E2[405 Method Not Allowed]
    B --> C[Security filter]
    C -->|Chưa xác thực / thiếu quyền| E3[401 hoặc 403]
    C --> D[Binding và validation]
    D -->|Body sai cú pháp / kiểu dữ liệu| E4[400 Bad Request]
    D -->|Dữ liệu không đạt ràng buộc| E5[400 hoặc 422]
    D --> F[Controller]
    F --> G[Service / Model]
    G -->|Không tìm thấy tài nguyên| E6[404 Not Found]
    G -->|Xung đột trạng thái nghiệp vụ| E7[409 Conflict]
    G --> H[Repository / Database]
    H -->|Lỗi bất ngờ| E8[500 Internal Server Error]
    H --> I[Response thành công]
~~~

Sơ đồ thể hiện luồng khái niệm. Thứ tự và thành phần thực tế phụ thuộc framework. Ví dụ, trong Spring Security, một số lỗi xác thực hoặc CSRF được xử lý ở security filter chain trước khi request đến Controller; `@ControllerAdvice` của Spring MVC không tự động bắt mọi lỗi phát sinh ở lớp đó.

### Các nhóm lỗi thường gặp

1. **Lỗi định tuyến:** URL không khớp endpoint hoặc HTTP method không được hỗ trợ.
2. **Lỗi xác thực và phân quyền:** danh tính không hợp lệ hoặc người dùng không được phép thực hiện thao tác.
3. **Lỗi binding và validation:** dữ liệu không thể chuyển đổi hoặc không đáp ứng ràng buộc đầu vào.
4. **Lỗi nghiệp vụ:** thao tác mâu thuẫn với quy tắc hoặc trạng thái hiện tại của miền.
5. **Lỗi lưu trữ và hạ tầng:** cơ sở dữ liệu, dịch vụ phụ thuộc hoặc hệ thống gặp sự cố.

Phân loại đúng giúp tránh việc trả cùng một mã `400` cho mọi lỗi hoặc biến lỗi hệ thống thành một thông báo “không tìm thấy dữ liệu”.

## 3. Chọn mã HTTP phù hợp

HTTP status code là một phần của hợp đồng giữa server và client. Client có thể dựa vào mã này để quyết định hiển thị lỗi, yêu cầu đăng nhập, thử lại hay thay đổi request.

| Mã | Tên | Khi nào sử dụng |
|---|---|---|
| `400` | Bad Request | Request sai cú pháp, không thể binding hoặc dữ liệu đầu vào không hợp lệ theo hợp đồng API |
| `401` | Unauthorized | Request cần xác thực nhưng thông tin xác thực bị thiếu hoặc không hợp lệ; thường đi cùng `WWW-Authenticate` khi phù hợp |
| `403` | Forbidden | Đã xác định được người gọi nhưng họ không có quyền thực hiện hành động |
| `404` | Not Found | Route hoặc tài nguyên được yêu cầu không tồn tại; đôi khi dùng để che giấu sự tồn tại của tài nguyên theo chính sách bảo mật |
| `405` | Method Not Allowed | Tài nguyên có endpoint nhưng HTTP method được gửi không được hỗ trợ; response cần có header `Allow` |
| `406` | Not Acceptable | Server không thể tạo representation phù hợp với header `Accept` của client |
| `409` | Conflict | Request hợp lệ về cú pháp nhưng xung đột với trạng thái hiện tại, ví dụ ISBN đã được dùng hoặc sách không thể được mượn ở trạng thái hiện tại |
| `412` | Precondition Failed | Điều kiện trong request header như `If-Match` không được đáp ứng |
| `415` | Unsupported Media Type | Server không hỗ trợ định dạng được gửi qua `Content-Type` |
| `422` | Unprocessable Content | Nội dung có cú pháp và media type được hiểu nhưng chỉ dẫn bên trong không thể xử lý theo ngữ nghĩa |
| `429` | Too Many Requests | Client gửi quá nhiều request trong khoảng thời gian được giới hạn |
| `500` | Internal Server Error | Lỗi không dự kiến xảy ra ở phía server và không có ánh xạ lỗi cụ thể an toàn hơn |
| `501` | Not Implemented | Server chưa hỗ trợ chức năng cần thiết để đáp ứng request; không dùng thay cho lỗi một route không hỗ trợ method |

### Phân biệt những mã dễ nhầm

**400 và 422:** `400` thường được dùng khi request sai cú pháp, binding thất bại hoặc validation đầu vào không đạt. `422` mô tả nội dung đã được phân tích nhưng không thể xử lý theo ngữ nghĩa. Với lỗi kiểm tra trường, nhiều API chọn `400`; một số API chọn `422`. Điều quan trọng là tài liệu API phải quy định nhất quán và client không phải đoán.

**405 và 409:** `405` nói rằng endpoint không chấp nhận HTTP method được gửi. `409` nói rằng hành động hoặc cập nhật xung đột với trạng thái hiện tại của tài nguyên. Ví dụ, `DELETE /books/123` không được route hỗ trợ có thể trả `405`; còn `POST /loans/123/return` khi phiếu mượn đã được trả có thể trả `409` nếu nghiệp vụ không cho phép trả lần nữa.

**403 và 409:** `403` là vấn đề quyền của người gọi. `409` là vấn đề trạng thái nghiệp vụ. Không nên trả `409` chỉ vì người dùng thiếu quyền, hoặc trả `403` cho một trạng thái nghiệp vụ không cho phép.

**404 và danh sách rỗng:** trang danh sách không có kết quả tìm kiếm vẫn là response thành công với collection rỗng. Trang chi tiết cho một ID không tồn tại thường là `404`. Không dùng `404` cho mọi danh sách rỗng.

## 4. Kiểm tra dữ liệu đầu vào

Dữ liệu request đến từ bên ngoài hệ thống và cần được xem là không đáng tin cậy. Kiểm tra đầu vào thường có nhiều lớp:

- **Binding và chuyển đổi kiểu:** kiểm tra dữ liệu có thể chuyển thành kiểu mong đợi hay không, ví dụ UUID, ngày tháng hoặc số nguyên.
- **Validation cấu trúc:** kiểm tra trường bắt buộc, độ dài, định dạng, giới hạn số và quan hệ giữa các trường.
- **Validation nghiệp vụ:** kiểm tra điều kiện phụ thuộc vào Model hoặc dữ liệu hiện có, ví dụ ngày kết thúc phải sau ngày bắt đầu.

Validation ở biểu mẫu giúp phản hồi sớm và thân thiện. Quy tắc nghiệp vụ quan trọng vẫn cần được bảo vệ ở tầng Model/Service để những luồng khác như API hoặc tác vụ nền không thể bỏ qua.

### Ví dụ Form DTO với Bean Validation

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookForm(
        @NotBlank(message = "Tiêu đề không được để trống")
        @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự")
        String title,

        @NotBlank(message = "ISBN không được để trống")
        String isbn
) {}
~~~

Controller Spring MVC có thể nhận form như sau:

~~~java
@PostMapping("/books")
public String createBook(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult bindingResult,
        Model model) {
    if (bindingResult.hasErrors()) {
        model.addAttribute("pageTitle", "Thêm sách");
        return "books/new";
    }

    bookService.createBook(form.title(), form.isbn());
    return "redirect:/books";
}
~~~

`BindingResult` phải đứng ngay sau tham số được kiểm tra để Spring đưa lỗi binding/validation vào đó. Khi có lỗi, Controller trả lại View biểu mẫu cùng các lỗi trường; không gọi Service để tạo sách. Nếu dùng `@RequestBody @Valid` cho API và không khai báo `BindingResult` để tự xử lý, Spring thường phát sinh `MethodArgumentNotValidException`, có thể được xử lý tập trung.

Không nên chỉ dựa vào `@NotBlank` để bảo vệ quy tắc nghiệp vụ. `Book` hoặc Value Object `Isbn` vẫn phải bảo đảm những điều kiện miền quan trọng, vì đối tượng có thể được tạo từ nhiều nguồn khác nhau.

## 5. Xử lý hành động không được hỗ trợ

Cụm từ “hành động không được hỗ trợ” có thể chỉ nhiều tình huống khác nhau. Hãy xác định hành động bị từ chối ở tầng nào:

### HTTP method không được endpoint hỗ trợ

Giả sử ứng dụng chỉ định nghĩa `GET /books/{id}` và `PUT /books/{id}`. Nếu client gửi `DELETE /books/{id}`, server nên trả `405 Method Not Allowed` và cho biết các method được hỗ trợ bằng header `Allow`, ví dụ `Allow: GET, PUT`.

Trong Spring MVC, lỗi method không được hỗ trợ thường được framework nhận diện thông qua `HttpRequestMethodNotSupportedException` và xử lý thành `405`. Nếu tùy biến response, cần giữ đúng status và header `Allow` để client biết các method hợp lệ.

### Hành động nghiệp vụ không phù hợp với trạng thái hiện tại

Một endpoint có thể tồn tại nhưng hành động không hợp lệ với đối tượng. Ví dụ:

- Không thể mượn sách đang được người khác mượn.
- Không thể trả một phiếu mượn đã được đóng.
- Không thể hủy đơn hàng đã giao.
- Không thể xuất bản bài viết đang bị khóa kiểm duyệt.

Đây là lỗi nghiệp vụ. Service hoặc Model phát hiện và ném lỗi miền có ý nghĩa, sau đó lớp xử lý ngoại lệ ánh xạ thành `409 Conflict` hoặc `422 Unprocessable Content` tùy ngữ nghĩa và hợp đồng API.

### Hành động bị từ chối do quyền truy cập

Nếu người dùng không được phép xóa sách, server phải từ chối thao tác ngay cả khi giao diện không hiển thị nút xóa. Đây là vấn đề phân quyền, thường trả `403 Forbidden` hoặc `404` nếu chính sách bảo mật cố ý không tiết lộ tài nguyên.

### Route hoặc tài nguyên không tồn tại

Nếu URL không có route tương ứng hoặc ID không đại diện cho tài nguyên hiện có, response thường là `404 Not Found`. Không tạo một action giả hoặc trả `200 OK` với nội dung lỗi để che giấu việc định tuyến thất bại.

## 6. Tổ chức xử lý ngoại lệ trong MVC

Controller nên giữ vai trò điều phối. Nếu mỗi action tự bắt nhiều loại ngoại lệ, mã sẽ lặp lại và dễ tạo response không nhất quán. Framework MVC thường cung cấp hai cơ chế:

- **Xử lý cục bộ:** action hoặc Controller khai báo cách xử lý cho một lỗi đặc thù chỉ liên quan đến chức năng đó.
- **Xử lý tập trung:** một thành phần như `@ControllerAdvice` hoặc `@RestControllerAdvice` ánh xạ các lỗi phổ biến thành response dùng chung.

### Ví dụ xử lý lỗi API bằng Spring

Spring Framework 6 hỗ trợ `ProblemDetail` để tạo response theo định dạng Problem Details cho HTTP APIs (RFC 9457). Một `@RestControllerAdvice` có thể chuyển các ngoại lệ nghiệp vụ và validation thành response có cấu trúc:

~~~java
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            BookNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy sách.");
        problem.setTitle("Không tìm thấy tài nguyên");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(InvalidBookStateException.class)
    public ResponseEntity<ProblemDetail> handleInvalidState(
            InvalidBookStateException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Không thể thực hiện thao tác với trạng thái hiện tại.");
        problem.setTitle("Xung đột trạng thái nghiệp vụ");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> handleValidation(
            MethodArgumentNotValidException exception) {
        var errors = exception.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", Objects.requireNonNullElse(
                                error.getDefaultMessage(), "Giá trị không hợp lệ")))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Một hoặc nhiều trường dữ liệu cần được kiểm tra.");
        problem.setTitle("Dữ liệu không hợp lệ");
        problem.setProperty("errors", errors);
        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Ví dụ giả định các ngoại lệ nghiệp vụ đã được định nghĩa. Trong ứng dụng thực tế, cần bổ sung import cho các kiểu miền tương ứng và có thể bổ sung handler cho lỗi binding, `404`, `405`, `415` hoặc lỗi đặc thù khác. Spring MVC đã có các cơ chế mặc định cho nhiều lỗi HTTP; chỉ tùy biến khi cần định dạng phản hồi thống nhất, đồng thời phải bảo toàn status và header giao thức quan trọng.

Response validation có thể có dạng:

~~~json
{
  "type": "https://api.example.test/problems/validation-error",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường dữ liệu cần được kiểm tra.",
  "instance": "/api/books",
  "errors": [
    { "field": "title", "message": "Tiêu đề không được để trống" },
    { "field": "isbn", "message": "ISBN không hợp lệ" }
  ]
}
~~~

Client có thể dựa vào `status` để phân loại lỗi và dựa vào `errors` để gắn thông báo với trường tương ứng. Không nên đưa giá trị nhạy cảm người dùng đã gửi vào response lỗi hoặc phản chiếu nguyên văn nội dung độc hại.

### Trả View lỗi cho ứng dụng HTML

Với ứng dụng render HTML phía máy chủ, lỗi validation thường được trả lại chính biểu mẫu để người dùng sửa. Lỗi không tìm thấy hoặc lỗi hệ thống có thể dùng trang lỗi riêng. Một `@ControllerAdvice` có thể trả `ModelAndView` và đặt status phù hợp:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.servlet.ModelAndView;

@ControllerAdvice
public class PageExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ModelAndView handleBookNotFound(BookNotFoundException exception) {
        ModelAndView view = new ModelAndView("errors/404");
        view.setStatus(HttpStatus.NOT_FOUND);
        view.addObject("message", "Sách bạn yêu cầu không tồn tại.");
        return view;
    }

    @ExceptionHandler(InvalidBookStateException.class)
    public ModelAndView handleInvalidBookState(InvalidBookStateException exception) {
        ModelAndView view = new ModelAndView("errors/409");
        view.setStatus(HttpStatus.CONFLICT);
        view.addObject("message",
                "Không thể thực hiện thao tác với trạng thái hiện tại.");
        return view;
    }
}
~~~

Trong ứng dụng dùng đồng thời HTML và JSON, cần tránh một handler toàn cục luôn trả HTML cho API hoặc luôn trả JSON cho trình duyệt. Có thể tách advice theo package/controller, dùng content negotiation hoặc cấu hình handler theo loại endpoint.

## 7. Giữ hợp đồng lỗi nhất quán

Một hợp đồng lỗi tốt nên cho client biết:

- Mã HTTP và mã lỗi nghiệp vụ ổn định nếu cần phân biệt các trường hợp.
- Tiêu đề hoặc thông điệp ngắn, có thể hiển thị cho người dùng.
- Trường nào không hợp lệ và lý do ở mức an toàn.
- Request hoặc correlation ID để hỗ trợ tra cứu log khi cần.
- Hướng khắc phục hoặc hành động tiếp theo nếu xác định được.

Thông điệp dành cho người dùng không nên là tên class ngoại lệ hoặc câu SQL. Ví dụ, `DuplicateIsbnException` là tên hữu ích trong mã nguồn; thông điệp có thể hiển thị là “ISBN này đã được sử dụng cho một cuốn sách khác”.

Với API, nên giữ cấu trúc JSON ổn định và dùng `application/problem+json` cho Problem Details. Không trả status `200 OK` cho một request thất bại chỉ để client đọc một trường `success: false`; điều đó làm mất ý nghĩa của HTTP và gây khó khăn cho proxy, cache, monitoring và client chuẩn.

Với biểu mẫu HTML, nên giữ các giá trị an toàn mà người dùng đã nhập để tránh nhập lại từ đầu. Không phản hồi lại mật khẩu, token, dữ liệu thanh toán hoặc trường nhạy cảm. Sau khi POST thành công, mô hình Post/Redirect/Get (PRG) giúp tránh gửi lại thao tác khi người dùng tải lại trang.

## 8. Bảo mật trong xử lý lỗi

Thông tin lỗi có thể giúp kẻ tấn công hiểu cấu trúc hệ thống nếu được trả quá chi tiết. Hãy áp dụng các nguyên tắc sau:

**Không trả stack trace cho client.** Stack trace, tên package, đường dẫn file, câu SQL và thông tin cấu hình chỉ nên nằm trong log nội bộ có kiểm soát.

**Không tin dữ liệu đầu vào khi ghi log.** Giới hạn độ dài, làm sạch ký tự điều khiển và tránh log mật khẩu, access token, session ID hoặc dữ liệu cá nhân không cần thiết.

**Không dùng exception để thay thế kiểm soát quyền.** Một endpoint phải kiểm tra quyền trên tài nguyên ở phía server mỗi lần được gọi. Ẩn nút trên View không phải biện pháp phân quyền.

**Giữ thông báo đủ rõ nhưng không tiết lộ dữ liệu.** Với tài nguyên nhạy cảm, chính sách có thể trả `404` thay vì xác nhận tài nguyên tồn tại nhưng người dùng không có quyền xem. Quyết định này cần nhất quán để không tạo kênh dò tìm tài nguyên.

**Xử lý lỗi CSRF và xác thực đúng tầng.** Trong Spring Security, lỗi bị chặn ở filter chain cần được xử lý bằng `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` phù hợp; không giả định mọi request đều đến ControllerAdvice.

**Không nuốt lỗi bất ngờ.** Bắt `Exception` chung rồi trả danh sách rỗng hoặc trang thành công sẽ che giấu sự cố. Hãy ghi log có correlation ID, trả `500` an toàn và cho phép hệ thống giám sát phát hiện lỗi.

## 9. Kiểm thử xử lý lỗi

Kiểm thử nên bao phủ cả mã HTTP, nội dung response, header và việc không thực hiện tác động nghiệp vụ khi request không hợp lệ.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Thiếu trường bắt buộc | Trả lỗi validation; Service không được gọi |
| UUID hoặc ngày sai định dạng | Binding thất bại và response phù hợp, thường là `400` |
| JSON sai cú pháp | Trả `400`, không lộ parser stack trace |
| `Content-Type` không hỗ trợ | Trả `415` |
| HTTP method không được hỗ trợ | Trả `405` và có header `Allow` |
| Không đăng nhập | Trả `401` theo cơ chế xác thực |
| Không đủ quyền | Trả `403` hoặc `404` theo chính sách bảo mật |
| ID không tồn tại | Trả `404` |
| Hành động xung đột trạng thái | Trả `409` hoặc `422` theo hợp đồng |
| Lỗi ngoài dự kiến | Trả `500` an toàn; log nội bộ có thông tin tương quan |

**Unit test cho Model/Service** kiểm tra quy tắc nghiệp vụ và ngoại lệ được ném ra. **Test Controller** kiểm tra status, view hoặc body, header và việc gọi Service. **Integration test** kiểm tra route, filter bảo mật, binding, exception handler và cơ sở dữ liệu trong một luồng gần với thực tế.

Với lỗi do ràng buộc dữ liệu ở cơ sở dữ liệu, nên có kiểm thử tích hợp cho trường hợp xung đột đồng thời hoặc unique constraint. Chỉ kiểm tra một lần gọi `existsBy...` không chứng minh hệ thống tránh được hai request cùng ghi một giá trị.

## 10. Những sai lầm thường gặp

- **Trả `200 OK` cho mọi tình huống:** client không phân biệt được thành công và thất bại bằng giao thức.
- **Dùng `400` cho mọi lỗi:** lỗi quyền, tài nguyên, method và xung đột nghiệp vụ có ngữ nghĩa khác nhau.
- **Nhầm `405` với hành động nghiệp vụ bị từ chối:** một bên là HTTP method, bên kia là trạng thái miền.
- **Để Controller bắt và xử lý mọi ngoại lệ:** logic lặp lại và response không nhất quán.
- **Chỉ validate ở giao diện:** API hoặc tác vụ nền có thể gửi dữ liệu bỏ qua giao diện.
- **Trả nguyên văn exception hoặc stack trace:** làm lộ thông tin nội bộ và đôi khi dữ liệu nhạy cảm.
- **Nuốt lỗi rồi trả collection rỗng:** khiến người dùng hiểu sai trạng thái dữ liệu và làm mất dấu sự cố.
- **Chỉ ẩn nút thao tác:** request trực tiếp vẫn có thể đến server nếu endpoint không kiểm tra quyền.
- **Không kiểm thử header và status:** ví dụ response `405` thiếu `Allow` hoặc lỗi validation lại trả status thành công.

## 11. Kết luận

Controller là điểm điều phối request và response, nhưng lỗi có thể được phát hiện ở nhiều tầng của ứng dụng. Hãy phân biệt lỗi cú pháp và validation, lỗi xác thực/phân quyền, lỗi định tuyến hoặc HTTP method, lỗi không tìm thấy tài nguyên, xung đột nghiệp vụ và lỗi hệ thống. Mỗi loại cần mã HTTP, thông điệp và cơ chế xử lý phù hợp.

Khi thiết kế luồng lỗi MVC, hãy xác định thành phần nào có đủ thông tin để phát hiện vấn đề, nơi nào chịu trách nhiệm chuyển lỗi thành response, dữ liệu nào được phép tiết lộ và cách client có thể khắc phục. Một hợp đồng lỗi nhất quán giúp giao diện dễ sử dụng, API dễ tích hợp và hệ thống dễ vận hành.
