# Lộ trình học từ dữ liệu thô đến đối tượng hợp lệ trong Spring Framework

Khi một ứng dụng Spring nhận yêu cầu HTTP, dữ liệu ban đầu chỉ là chuỗi trong URL, các trường biểu mẫu hoặc byte của JSON. Chưa có gì bảo đảm người gửi nhập đúng kiểu, đủ trường, đúng quy tắc hay có quyền thực hiện thao tác. Nhiệm vụ của lớp nhận yêu cầu là biến dữ liệu đó thành một đối tượng Java có cấu trúc, kiểm tra các quy tắc đầu vào và chỉ chuyển tiếp yêu cầu phù hợp sang nghiệp vụ.

**Mục tiêu của bài:** nhìn được toàn bộ hành trình từ HTTP request → phân giải tham số → gắn dữ liệu/chuyển kiểu → kiểm tra hợp lệ → xử lý lỗi → thực thi nghiệp vụ; phân biệt những lớp kiểm tra thường bị gọi chung là “validation”; biết học và kiểm thử từng chặng. “Đối tượng hợp lệ” ở đây là **đối tượng đầu vào hợp lệ theo hợp đồng của API**, chưa mặc nhiên là thực thể nghiệp vụ được phép lưu.

## 1. Bản đồ tổng thể

```text
Client gửi HTTP request
  │  Path/query/form là văn bản; JSON là nội dung HTTP body
  ▼
Spring MVC: DispatcherServlet chọn handler/controller
  ▼
Phân giải tham số của phương thức controller
  ├─ @RequestParam / @PathVariable: lấy giá trị đơn từ request
  ├─ @ModelAttribute: gắn query/form fields vào object
  │                   qua WebDataBinder và cơ chế chuyển đổi
  └─ @RequestBody: đọc body bằng HttpMessageConverter
                  (ví dụ Jackson chuyển JSON thành Java object)
  ▼
Đối tượng/tham số Java đã được tạo và chuyển kiểu
  ▼
Kiểm tra đầu vào khi được cấu hình/kích hoạt
  ├─ Lỗi đọc JSON hoặc chuyển kiểu: không tạo được đầu vào mong muốn
  ├─ @Valid / Jakarta Bean Validation: kiểm tra ràng buộc trên DTO
  └─ Lỗi được trả cho client hoặc thu vào BindingResult thích hợp
  ▼
Controller → service/domain
  ├─ Kiểm tra quy tắc nghiệp vụ, quyền truy cập, trạng thái hiện tại
  ├─ Thực hiện thao tác hợp lệ; bảo vệ bất biến dữ liệu
  └─ Ghi dữ liệu khi cần
  ▼
HTTP response (thành công hoặc lỗi có cấu trúc)
```

Đây là **sơ đồ tư duy**, không phải thứ tự nội bộ cố định cho mọi loại tham số. Chẳng hạn, `@RequestBody` dùng bộ đọc thông điệp (message converter) để giải mã JSON; `@ModelAttribute` dùng cơ chế data binding cho query/form. Không nên nghĩ rằng mọi request đều đi qua cùng một bộ chuyển đổi.

## 2. Bốn câu hỏi cần trả lời ở mỗi chặng

| Chặng | Câu hỏi | Ví dụ | Nếu không đạt |
| --- | --- | --- | --- |
| Đọc dữ liệu | Request có đọc/giải mã được không? | JSON bị thiếu dấu ngoặc | Lỗi đọc body, thông thường HTTP 400 |
| Binding/chuyển kiểu | Giá trị có chuyển thành kiểu Java đích không? | `page=abc` cần `Integer` | Lỗi chuyển kiểu/binding |
| Kiểm tra ràng buộc đầu vào | Các giá trị Java có đáp ứng hợp đồng của DTO không? | Email trống, tuổi dưới mức tối thiểu | Lỗi validation, thường HTTP 400 tại API |
| Kiểm tra nghiệp vụ | Hành động có được phép trong trạng thái hiện tại không? | Email đã tồn tại, người dùng sửa tài nguyên không thuộc quyền | Service/domain từ chối theo quy tắc; mã HTTP tùy trường hợp |

Đầu tiên phải *tạo được giá trị Java*, sau đó mới có thể kiểm tra các ràng buộc áp dụng trên giá trị đó. Nhưng “đã qua `@Valid`” không có nghĩa là dữ liệu đã được xác thực nguồn gốc, người gọi đã được phân quyền hoặc không còn xung đột trong cơ sở dữ liệu.

## 3. Nhận đúng loại dữ liệu trước khi kiểm tra

### 3.1. URL, query parameter và biểu mẫu

Ví dụ yêu cầu `GET /products?page=2` mang chuỗi `"2"`. Nếu controller khai báo `@RequestParam Integer page`, Spring phải chuyển chuỗi đó thành số nguyên trước khi gọi phương thức. `page=abc` không thể chuyển thành `Integer` hợp lệ.

Với nhiều trường liên quan, `@ModelAttribute` có thể gắn dữ liệu query/form vào một đối tượng như `SearchForm` gồm `keyword`, `page`, `sort`. Spring MVC sử dụng `WebDataBinder` kết hợp cơ chế chuyển đổi như `ConversionService`, `Converter`/`Formatter`. Kiểu ngày, số và cách trình bày theo locale có thể cần cấu hình hoặc annotation tương ứng, chẳng hạn `@DateTimeFormat`.

Với form MVC, khai báo `@Valid @ModelAttribute SearchForm form, BindingResult errors` (đặt `BindingResult` **ngay sau** tham số cần bắt lỗi) cho phép controller kiểm tra lỗi binding/validation và trả lại form cùng thông báo cụ thể. `BindingResult` không phải biến toàn cục dùng được cho mọi tham số bất kỳ.

### 3.2. JSON request body

Với `Content-Type: application/json` và `@RequestBody RegistrationRequest request`, Spring MVC chọn `HttpMessageConverter` phù hợp; trong cấu hình phổ biến với Jackson, JSON được giải mã thành DTO Java. Ví dụ:

```json
{
  "name": "Lan",
  "email": "lan@example.com",
  "age": 20
}
```

Nếu JSON hỏng cú pháp, một trường không thể giải mã thành kiểu yêu cầu hoặc body không đọc được, lỗi xảy ra **trước khi** các constraint như `@Min` có thể kiểm tra DTO hoàn chỉnh. Trong Spring MVC, lỗi đọc body điển hình là `HttpMessageNotReadableException` và thường được xử lý thành HTTP 400.

**Điểm cần phân biệt:** `@RequestBody` yêu cầu đọc/giải mã body; `@Valid` yêu cầu kiểm tra ràng buộc của đối tượng sau khi giải mã thành công. Chỉ dùng một trong hai annotation không tự động thực hiện cả hai việc.

## 4. Từ đối tượng Java đến DTO hợp lệ

Jakarta Bean Validation mô tả các ràng buộc bằng annotation trên đối tượng Java. Khi có trình triển khai validation (chẳng hạn Hibernate Validator), Spring có thể kích hoạt chúng qua `@Valid` hoặc cơ chế validation thích hợp.

| Ràng buộc | Điều được kiểm tra | Điều **không** được bảo đảm |
| --- | --- | --- |
| `@NotNull` | Giá trị khác `null` | Chuỗi không rỗng |
| `@NotBlank` | Chuỗi không `null` và có ký tự không phải khoảng trắng | Chuỗi đã được chuẩn hóa/loại bỏ khoảng trắng thừa |
| `@Size(min=..., max=...)` | Độ dài chuỗi/kích thước collection nằm trong giới hạn | Ý nghĩa nghiệp vụ |
| `@Email` | Chuỗi theo quy tắc định dạng email của validator | Email tồn tại hoặc thuộc người dùng |
| `@Min(18)` | Giá trị số ít nhất là 18 | Giá trị không `null` |
| `@Valid` trên trường lồng nhau | Yêu cầu đi tiếp vào đối tượng lồng nhau | Đối tượng lồng nhau bắt buộc tồn tại nếu không có `@NotNull` |

Hai ràng buộc thường phải phối hợp: `@NotBlank @Email String email` để vừa yêu cầu nhập, vừa kiểm tra định dạng; `@NotNull @Min(18) Integer age` để vừa yêu cầu có tuổi, vừa kiểm tra giá trị. Dùng `Integer` thay cho `int` giúp phân biệt “không gửi tuổi” (`null`) với giá trị số 0.

Trong Spring Boot 3 / Spring Framework 6, dùng namespace **`jakarta.validation.*`**, không dùng `javax.validation.*` của thế hệ cũ. Với ứng dụng Spring Boot có Bean Validation, dependency thường dùng là `spring-boot-starter-validation`; `spring-boot-starter-web` cung cấp thành phần Spring MVC và JSON phổ biến.

## 5. Ví dụ thực hành: một endpoint nhận JSON, gắn kiểu và kiểm tra DTO

Giả sử có một dự án Spring Boot hỗ trợ Java 17 trở lên và đã bật plugin/dependency management của Spring Boot. Bổ sung các dependency tương ứng trong `build.gradle` của dự án:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Tạo tệp `src/main/java/demo/validation/ValidationDemoApplication.java` với nội dung đầy đủ sau. Các `record` và controller cùng một tệp dùng quyền truy cập mặc định của package; tên tệp khớp với lớp `public`:

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}

record RegistrationRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}

record RegistrationResponse(String name, String email) {}

@RestController
@RequestMapping("/registrations")
class RegistrationController {
    @PostMapping
    ResponseEntity<RegistrationResponse> register(
            @Valid @RequestBody RegistrationRequest request) {
        // Chỉ trả kết quả minh họa; chưa tạo tài khoản trong cơ sở dữ liệu.
        RegistrationResponse response =
                new RegistrationResponse(request.name(), request.email());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Chạy ứng dụng bằng `./gradlew bootRun` trong dự án đã cấu hình Spring Boot, hoặc chạy cấu hình tương đương từ IDE. Gửi yêu cầu hợp lệ:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":20}'
```

Với cổng mặc định 8080, phản hồi mong đợi có trạng thái **201 Created** và phần thân JSON tương ứng:

```json
{"name":"Lan","email":"lan@example.com"}
```

Đi theo từng chặng: Spring tìm phương thức `register` → Jackson tạo `RegistrationRequest` từ JSON → Bean Validation kiểm tra tên/email/tuổi vì có `@Valid` → controller chỉ được gọi khi yêu cầu qua những kiểm tra đó → ứng dụng tạo `RegistrationResponse`. Ví dụ chưa lưu dữ liệu và không kiểm tra trùng email, nên chưa phải luồng đăng ký người dùng hoàn chỉnh.

Thử body không đáp ứng hợp đồng:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"   ","email":"khong-phai-email","age":16}'
```

JSON này **đọc được** và tạo được DTO, nhưng `@NotBlank`, `@Email`, `@Min` đều vi phạm. Với Spring MVC thông thường, validation của `@Valid @RequestBody` dẫn tới `MethodArgumentNotValidException` và **HTTP 400 Bad Request**. Hình dạng JSON lỗi mặc định phụ thuộc phiên bản/cấu hình xử lý lỗi của ứng dụng; không nên giả định một mẫu body cố định.

Để thấy chặng lỗi khác, thử `"age":"abc"`: Jackson không thể chuyển chuỗi chữ thành `Integer` và request thường bị từ chối ở bước đọc/chuyển kiểu, trước khi kiểm tra `@Min`. Nếu bỏ hẳn `age`, `Integer age` có thể là `null` và bị `@NotNull` từ chối trong bước Bean Validation.

## 6. Lỗi validation được xử lý ở đâu?

**Đường API JSON:** Khi controller khai báo `@Valid @RequestBody` và không tự nhận lỗi để xử lý, Spring MVC thường trả HTTP 400 cho yêu cầu không thỏa ràng buộc DTO. Có thể dùng `@RestControllerAdvice` và `@ExceptionHandler` để tạo mẫu lỗi nhất quán, ví dụ gồm mã lỗi, danh sách `field`/`message` và mã truy vết. Không cần đưa toàn bộ dữ liệu người dùng gửi vào log hoặc phản hồi, nhất là thông tin nhạy cảm.

**Đường form MVC:** Khi dùng `@Valid @ModelAttribute` cùng `BindingResult` đứng sát ngay sau đối tượng, controller có thể kiểm tra `errors.hasErrors()` và hiển thị lại biểu mẫu. Cơ chế này tiện cho giao diện nhập liệu cần chỉ rõ trường sai. Nếu không xử lý trực tiếp, cách Spring chuyển lỗi thành phản hồi sẽ phụ thuộc chữ ký phương thức, cấu hình và kiểu endpoint.

Khi thiết kế phản hồi lỗi, cần phân biệt ít nhất ba trường hợp:

1. **Body không đọc được/chuyển kiểu thất bại:** giải thích cú pháp hoặc kiểu dữ liệu cần gửi, tránh báo nhầm là vi phạm quy tắc nghiệp vụ.
2. **DTO không thỏa constraint:** chỉ rõ trường và quy tắc công khai, không lộ bí mật hay giá trị nhạy cảm.
3. **Nghiệp vụ từ chối:** đưa ra lỗi phù hợp như xung đột dữ liệu hoặc thiếu quyền; mã HTTP và nội dung phải do hợp đồng API quyết định.

Không dựa vào thứ tự các thông báo validation để viết test, vì thứ tự duyệt các constraint không phải một hợp đồng ổn định.

## 7. DTO hợp lệ vẫn chưa phải trạng thái nghiệp vụ hợp lệ

Giả sử JSON có email đúng định dạng và tuổi ít nhất 18. Những câu hỏi sau **chưa** được Bean Validation đơn giản trả lời: email đã được đăng ký chưa, người gọi có quyền tạo tài khoản cho tổ chức này không, tài khoản hiện tại có bị khóa không, có giới hạn số yêu cầu hay không?

Các kiểm tra phụ thuộc cơ sở dữ liệu, danh tính và quy tắc nghiệp vụ thuộc về service/domain cùng cơ chế bảo mật của ứng dụng. Nếu hai request cùng đăng ký một email, chỉ kiểm tra “chưa tồn tại” trước khi ghi cũng chưa đủ để tránh tranh chấp; ràng buộc unique ở cơ sở dữ liệu và cách xử lý xung đột vẫn cần thiết.

Đừng dùng entity lưu trữ làm `@RequestBody` chỉ để tiện gắn dữ liệu: client có thể thử truyền những trường nội bộ như `id`, `role`, `status` mà API không có ý định cho sửa. DTO đầu vào chỉ khai báo trường client được phép cung cấp; tầng ứng dụng quyết định cách ánh xạ sang đối tượng nghiệp vụ. Với form binding, cần đặc biệt lưu ý các thuộc tính có thể được gắn từ tên trường và dùng cách ràng buộc phù hợp để tránh nhận thừa trường.

## 8. Lộ trình học và kiểm chứng theo từng bước

| Bước học | Nắm vững điều gì? | Thí nghiệm tự kiểm tra |
| --- | --- | --- |
| 1. Nguồn dữ liệu HTTP | Phân biệt path, query, form, JSON body và content type | Đổi body JSON thành JSON sai cú pháp |
| 2. Phân giải tham số | Chọn đúng `@RequestParam`, `@PathVariable`, `@ModelAttribute`, `@RequestBody` | Đổi query `page=2` thành `page=abc` |
| 3. Binding và chuyển kiểu | Kiểu Java đích, converter/formatter, lỗi khi không chuyển được | Đổi `age` từ số thành chuỗi chữ |
| 4. Bean Validation | `@Valid`, constraint, nested validation, cách bật validator | Lần lượt bỏ `age`, để `name` chỉ có khoảng trắng |
| 5. Phản hồi lỗi | Phân biệt lỗi đọc dữ liệu, binding, constraint và nghiệp vụ | Quan sát HTTP status, kiểm tra controller có được gọi không |
| 6. Ranh giới nghiệp vụ | DTO khác entity; quyền, trạng thái và tính nhất quán khi lưu | Đề xuất chỗ kiểm tra email trùng và unique constraint |
| 7. Kiểm thử hợp đồng | Trường hợp thành công, thiếu trường, sai kiểu, sai ràng buộc | Tạo test MVC xác nhận 201/400 và không lộ dữ liệu nhạy cảm |

**Cách ôn nhanh:** với mỗi request, hãy tự trả lời theo thứ tự: dữ liệu đến từ đâu → Spring giải mã/gắn vào kiểu nào → ràng buộc nào chạy → nếu lỗi thì dừng ở đâu → nếu qua thì nghiệp vụ còn phải kiểm tra gì. Nếu trả lời được chuỗi này cho cả JSON và form, bạn đã nắm nền tảng để học sâu data binding, conversion, Bean Validation và xử lý ngoại lệ trong Spring.

## 9. Những nhầm lẫn thường gặp

- **Tưởng `@RequestBody` là validation:** annotation này xử lý đọc body; cần `@Valid` cùng hạ tầng Bean Validation để chạy các constraint trên DTO.
- **Tưởng `@Valid` biến mọi chuỗi thành đúng kiểu:** lỗi JSON/chuyển kiểu có thể xảy ra trước khi đối tượng được kiểm tra.
- **Chỉ dùng `@Email` để bắt buộc nhập email:** kết hợp với `@NotBlank` khi trường bắt buộc.
- **Dùng `int` cho trường cần phân biệt “không gửi”:** cân nhắc `Integer` và `@NotNull` để phản hồi rõ hơn.
- **Dùng nhầm `javax.validation` trong Spring Boot 3:** dùng `jakarta.validation` và bảo đảm có provider phù hợp.
- **Cho rằng request qua validation là được phép ghi DB:** vẫn cần xác thực/phân quyền, kiểm tra quy tắc miền và ràng buộc dữ liệu.
- **Giả định mọi lỗi đều có cùng exception hoặc JSON mặc định:** phân biệt lỗi message conversion, binding, constraint và nghiệp vụ; thống nhất hợp đồng lỗi theo ứng dụng.
- **Cho client gắn trực tiếp vào entity:** dùng DTO đầu vào để xác định rõ các trường được chấp nhận.

**Tự đánh giá:** Với `POST /registrations`, JSON `{"name":"Lan","email":"lan@example.com","age":"khong-ro"}` sẽ thất bại ở khâu giải mã/chuyển kiểu; JSON `{"name":" ","email":"lan@example.com","age":20}` tạo được DTO nhưng không vượt qua `@NotBlank`; JSON hợp lệ toàn bộ chỉ đủ điều kiện vào controller, nơi service vẫn phải quyết định có được thực hiện thao tác hay không.
