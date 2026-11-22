# application/x-www-form-urlencoded và binding dữ liệu form

Không phải mọi request gửi dữ liệu lên API đều dùng JSON. Nhiều biểu mẫu web truyền dữ liệu theo định dạng `application/x-www-form-urlencoded`, trong đó các trường được mã hóa thành những cặp tên và giá trị. Ví dụ, form đăng ký có thể gửi `email=dev%40example.com&plan=pro` trong phần body của HTTP request.

Trong Spring Boot, Spring MVC có thể bind dữ liệu form vào các tham số phương thức hoặc một đối tượng command bằng `@RequestParam` và `@ModelAttribute`. springdoc-openapi cho phép mô tả request body này trong đặc tả OpenAPI để Swagger UI hiển thị đúng loại nội dung, các trường, ràng buộc và ví dụ cho người tích hợp.

Bài học này đi từ cấu trúc form-urlencoded đến binding, validation, mô tả OpenAPI và kiểm thử. Nội dung tập trung vào Spring MVC trên Servlet stack; với WebFlux, cách truy cập form data có một số khác biệt về API và cần đối chiếu theo phiên bản framework.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích cách mã hóa dữ liệu của `application/x-www-form-urlencoded` và phân biệt nó với JSON hoặc multipart.
- Gửi form data bằng trình duyệt, curl và HTTP client.
- Bind các trường form vào tham số hoặc DTO trong Spring MVC.
- Áp dụng Bean Validation và xử lý lỗi dữ liệu form.
- Mô tả request body form-urlencoded bằng OpenAPI và springdoc-openapi.
- Kiểm tra đặc tả được sinh ra cùng hành vi HTTP thực tế.
- Nhận biết các lưu ý về ký tự đặc biệt, trường lặp, CSRF và dữ liệu nhạy cảm.

## 1. application/x-www-form-urlencoded là gì?

`application/x-www-form-urlencoded` là một media type dùng để gửi dữ liệu form dưới dạng chuỗi các cặp `name=value`, phân tách bằng ký tự `&`. Tên và giá trị được URL-encode để những ký tự đặc biệt không phá vỡ cấu trúc:

~~~http
POST /api/subscriptions HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded
Accept: application/json

email=dev%40example.com&plan=pro&note=Spring+Boot
~~~

Trong ví dụ:

- `email` có giá trị `dev@example.com`; ký tự `@` được mã hóa thành `%40`.
- `plan` có giá trị `pro`.
- `note` có giá trị `Spring Boot`; dấu cách được biểu diễn bằng dấu cộng trong dạng mã hóa form thông dụng.

Định dạng này phù hợp với các biểu mẫu có các trường văn bản, lựa chọn, checkbox và dữ liệu dạng chuỗi hoặc số đơn giản. Nó không phải JSON: server không nhận một object JSON trong body, mà nhận một tập tham số form đã mã hóa.

### Cấu trúc dữ liệu sau khi giải mã

Chuỗi form:

~~~text
email=dev%40example.com&plan=pro&note=Spring+Boot
~~~

Được hiểu thành các cặp:

| Tên trường | Giá trị sau giải mã |
|---|---|
| email | dev@example.com |
| plan | pro |
| note | Spring Boot |

Tên và giá trị được giải mã theo quy tắc URL encoding. Dấu cộng trong dữ liệu form biểu diễn dấu cách; nếu giá trị thực sự chứa dấu cộng, client phải mã hóa nó thành `%2B`. Ví dụ, số điện thoại hoặc chuỗi có ký tự cộng cần được encode đúng để server không hiểu nhầm dấu cộng thành dấu cách.

### Content-Type và Accept

Hai header có vai trò khác nhau:

- `Content-Type` mô tả định dạng body mà client gửi lên. Với form-urlencoded, giá trị là `application/x-www-form-urlencoded`.
- `Accept` cho biết client muốn nhận response ở định dạng nào, ví dụ `application/json`.

Một endpoint có thể nhận form-urlencoded nhưng trả JSON. Vì vậy, request có thể mang `Content-Type: application/x-www-form-urlencoded` và `Accept: application/json` cùng lúc.

## 2. Trình duyệt gửi form như thế nào?

Một HTML form cơ bản:

~~~html
<form method="post"
      action="/api/subscriptions"
      enctype="application/x-www-form-urlencoded">
    <label>
        Email
        <input type="email" name="email" required>
    </label>

    <label>
        Gói dịch vụ
        <select name="plan">
            <option value="basic">Basic</option>
            <option value="pro">Pro</option>
        </select>
    </label>

    <label>
        Ghi chú
        <input type="text" name="note">
    </label>

    <button type="submit">Đăng ký</button>
</form>
~~~

Với form POST thông thường, trình duyệt gửi các trường thành body và đặt Content-Type phù hợp với enctype. `application/x-www-form-urlencoded` là dạng mặc định của HTML form khi không chỉ định enctype khác. Việc đặt enctype tường minh giúp người đọc thấy rõ định dạng mà endpoint mong đợi.

Tên trong thuộc tính `name` là tên tham số server nhận được. Thuộc tính `id` và nội dung hiển thị trong `label` không quyết định tên trường được gửi. Nếu input không có `name`, giá trị của nó thường không được gửi trong form submission.

Nếu form dùng `method="get"`, trình duyệt đưa các trường vào query string của URL thay vì gửi body form-urlencoded. Bài học này tập trung vào form POST có body.

## 3. Gửi form bằng curl

Khi kiểm tra API, dùng `--data-urlencode` để curl mã hóa từng trường:

~~~bash
curl -i -X POST http://localhost:8080/api/subscriptions \
  -H "Accept: application/json" \
  --data-urlencode "email=dev@example.com" \
  --data-urlencode "plan=pro" \
  --data-urlencode "note=Spring Boot và OpenAPI"
~~~

Khi dùng `--data-urlencode`, curl sẽ gửi body theo định dạng form-urlencoded và thiết lập Content-Type tương ứng. Lựa chọn này giúp xử lý đúng dấu cách, dấu tiếng Việt và ký tự đặc biệt.

Có thể tự gửi chuỗi đã encode:

~~~bash
curl -i -X POST http://localhost:8080/api/subscriptions \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "email=dev%40example.com&plan=pro&note=Spring+Boot"
~~~

Với cách thứ hai, người viết phải tự bảo đảm chuỗi được mã hóa đúng. Không ghép giá trị do người dùng nhập vào chuỗi form mà bỏ qua URL encoding; dấu `&`, `=`, `+` hoặc ký tự Unicode có thể làm sai dữ liệu.

## 4. Bind form vào tham số bằng @RequestParam

Trong Spring MVC, `@RequestParam` có thể lấy giá trị từ request parameters. Với Servlet stack, request parameters bao gồm query parameters và dữ liệu form-urlencoded đã được container phân tích. Vì thế, annotation này phù hợp với endpoint có một vài trường đơn giản:

~~~java
@RestController
@RequestMapping("/api/subscriptions")
public class SubscriptionController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public SubscriptionResponse create(
            @RequestParam String email,
            @RequestParam String plan,
            @RequestParam(required = false) String note) {

        return subscriptionService.create(email, plan, note);
    }
}
~~~

Spring lấy các giá trị theo tên tham số. Nếu trường bắt buộc không có mặt, request có thể bị từ chối do thiếu tham số. Với trường tùy chọn, đặt `required = false` hoặc dùng kiểu có thể biểu diễn giá trị vắng mặt.

Có thể chỉ định tên trường tường minh:

~~~java
@RequestParam(name = "email") String email
~~~

Nên chỉ định tên khi tên tham số Java khác tên field form hoặc khi muốn hợp đồng ổn định dù cấu hình biên dịch thay đổi. Không dựa vào việc compiler lưu tên tham số nếu dự án chưa bật metadata tương ứng.

### Giá trị mặc định và kiểu dữ liệu

`@RequestParam` có thể chuyển đổi chuỗi sang các kiểu Java cơ bản:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public SearchResponse search(
        @RequestParam String keyword,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) Boolean includeArchived) {

    return searchService.search(keyword, page, size, includeArchived);
}
~~~

Nếu client gửi giá trị không chuyển đổi được, chẳng hạn `page=abc` cho tham số kiểu int, Spring MVC có thể trả lỗi binding trước khi gọi service. Hãy xác định status code và schema lỗi mà API muốn công bố cho trường hợp này.

Lưu ý rằng `@RequestParam` trong Spring MVC nhận cả query parameters lẫn form data. Nếu cùng một tên xuất hiện ở query string và body, ứng dụng có thể nhìn thấy giá trị trong tập request parameters đã hợp nhất. Nếu cần ranh giới rõ ràng giữa dữ liệu body và query, hãy thiết kế tên trường tránh trùng và kiểm thử trường hợp gửi trùng; không nên mặc định rằng annotation này chỉ đọc body.

## 5. Bind nhiều trường vào DTO bằng @ModelAttribute

Khi form có nhiều trường, dùng DTO giúp gom dữ liệu và tách hợp đồng request khỏi controller. `@ModelAttribute` yêu cầu Spring bind các request parameters vào thuộc tính hoặc constructor của đối tượng:

~~~java
public class SubscriptionForm {

    private String email;
    private String plan;
    private String note;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPlan() {
        return plan;
    }

    public void setPlan(String plan) {
        this.plan = plan;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Controller:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Valid @ModelAttribute SubscriptionForm form) {

    SubscriptionResponse created = subscriptionService.create(form);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Với Java hiện đại và phiên bản Spring hỗ trợ constructor binding cho record, có thể biểu diễn DTO ngắn gọn bằng record:

~~~java
public record SubscriptionForm(
    String email,
    String plan,
    String note
) {}
~~~

`@ModelAttribute` giúp controller nhận một đối tượng đã được bind từ các request parameters. Trong Spring MVC, model attribute có thể được tạo từ constructor hoặc bằng cách gọi setter. Với object có setter, chỉ nên đưa vào DTO những trường client được phép thay đổi; tránh bind trực tiếp entity persistence có nhiều thuộc tính nhạy cảm.

### Chọn @RequestParam hay @ModelAttribute?

| Tình huống | Cách dùng phù hợp |
|---|---|
| Một hoặc hai trường đơn giản | `@RequestParam` |
| Nhiều trường thuộc cùng một biểu mẫu | `@ModelAttribute` với DTO |
| Cần validation theo DTO | `@Valid @ModelAttribute` |
| Cần gom nhiều giá trị cùng tên | `MultiValueMap<String, String>` hoặc collection phù hợp |
| Nhận file cùng các trường form | `multipart/form-data` và `MultipartFile` |

Không nên dùng `@RequestBody` với một DTO JSON cho form-urlencoded rồi kỳ vọng Spring tự bind như JSON. `@RequestBody` hướng đến đọc body qua HttpMessageConverter; với form trên Servlet stack, Spring MVC thường dùng request parameters và data binding qua `@RequestParam` hoặc `@ModelAttribute`. Tránh đọc cùng request body bằng nhiều cơ chế khác nhau.

## 6. Validation dữ liệu form

Dữ liệu form vẫn cần kiểm tra ở server. Validation HTML trong trình duyệt chỉ hỗ trợ trải nghiệm nhập liệu; client có thể bỏ qua hoặc gửi request trực tiếp.

Ví dụ DTO có Bean Validation:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(name = "SubscriptionForm", description = "Dữ liệu form đăng ký")
public record SubscriptionForm(
    @NotBlank
    @Email
    @Schema(description = "Địa chỉ email", example = "dev@example.com")
    String email,

    @NotBlank
    @Schema(description = "Mã gói đăng ký", example = "pro",
            allowableValues = {"basic", "pro"})
    String plan,

    @Size(max = 250)
    @Schema(description = "Ghi chú không bắt buộc", example = "Liên hệ vào buổi chiều")
    String note
) {}
~~~

Controller dùng `@Valid`:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Valid @ModelAttribute SubscriptionForm form) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(subscriptionService.create(form));
}
~~~

Dự án cần dependency Bean Validation tương ứng, thường là `spring-boot-starter-validation`. Spring sẽ kiểm tra ràng buộc trước khi gọi service. Nếu dữ liệu không hợp lệ, exception hoặc BindingResult sẽ được xử lý theo cơ chế validation của Spring MVC.

### Xử lý lỗi binding và validation

Với `@ModelAttribute`, nếu cần tự quyết định response ngay trong controller, đặt `BindingResult` ngay sau tham số được validate:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<?> create(
        @Valid @ModelAttribute SubscriptionForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        Map<String, String> errors = bindingResult.getFieldErrors().stream()
            .collect(Collectors.toMap(
                FieldError::getField,
                error -> error.getDefaultMessage() == null
                    ? "Giá trị không hợp lệ"
                    : error.getDefaultMessage(),
                (first, ignored) -> first
            ));

        return ResponseEntity.badRequest()
            .body(new ApiError("VALIDATION_FAILED", errors));
    }

    SubscriptionResponse created = subscriptionService.create(form);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Đoạn mã minh họa cần kiểu `ApiError` và import phù hợp. Nếu không đặt BindingResult ngay sau model attribute, Spring thường chuyển lỗi binding/validation thành exception để xử lý tập trung. Một `@RestControllerAdvice` có thể chuẩn hóa response lỗi cho nhiều endpoint.

Hãy phân biệt lỗi thiếu trường, lỗi chuyển đổi kiểu và lỗi nghiệp vụ. Ví dụ email sai định dạng là validation; mã gói không tồn tại có thể là lỗi nghiệp vụ; người dùng không có quyền đăng ký gói là lỗi phân quyền. Chọn status code và error code ổn định cho từng nhóm.

## 7. Nhiều giá trị cho cùng một tên trường

HTML form có thể gửi nhiều giá trị cho cùng một name, thường gặp ở checkbox hoặc lựa chọn nhiều mục:

~~~html
<label><input type="checkbox" name="topics" value="spring"> Spring</label>
<label><input type="checkbox" name="topics" value="java"> Java</label>
<label><input type="checkbox" name="topics" value="api"> API</label>
~~~

Body có thể có dạng:

~~~text
topics=spring&topics=java&topics=api
~~~

Spring MVC có thể bind các giá trị lặp vào collection:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public PreferencesResponse save(
        @RequestParam List<String> topics) {
    return preferencesService.save(topics);
}
~~~

Nếu cần giữ mọi giá trị cùng tên hoặc xử lý form động, có thể nhận `MultiValueMap<String, String>`. Cần quy định rõ trường nào được lặp, có cho phép danh sách rỗng hay không và giới hạn số lượng phần tử.

Với checkbox HTML, trình duyệt thường chỉ gửi những checkbox được chọn. Nếu không có giá trị nào được chọn, key có thể hoàn toàn vắng mặt. DTO hoặc controller cần quy định cách hiểu trường bị thiếu, ví dụ danh sách rỗng hay lỗi validation.

## 8. Mô tả form-urlencoded trong OpenAPI

Trong OpenAPI, request body form-urlencoded được khai báo trong `requestBody.content` với media type chính xác là `application/x-www-form-urlencoded`. Schema thường là object với các property tương ứng trường form:

~~~yaml
paths:
  /api/subscriptions:
    post:
      summary: Đăng ký gói dịch vụ
      requestBody:
        required: true
        description: Dữ liệu đăng ký được gửi dưới dạng form
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required:
                - email
                - plan
              properties:
                email:
                  type: string
                  format: email
                  example: dev@example.com
                plan:
                  type: string
                  enum: [basic, pro]
                note:
                  type: string
                  maxLength: 250
            examples:
              subscription:
                summary: Đăng ký gói Pro
                value:
                  email: dev@example.com
                  plan: pro
                  note: Liên hệ vào buổi chiều
      responses:
        '201':
          description: Đã tạo đăng ký
        '400':
          description: Dữ liệu form không hợp lệ
~~~

Trong Swagger UI, request body sẽ được trình bày như các trường form thay vì một ô JSON đơn. Người tích hợp có thể biết tên field, kiểu dữ liệu, trường bắt buộc, giới hạn và ví dụ.

### Schema và encoding

Với các trường scalar thông thường, OpenAPI có thể dùng cách serialize form mặc định. Nếu cần quy định cách mã hóa một property phức tạp, có thể khai báo `encoding`:

~~~yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          topics:
            type: array
            items:
              type: string
      encoding:
        topics:
          style: form
          explode: true
~~~

Với `style: form` và `explode: true`, một mảng thường được biểu diễn bằng cách lặp lại key, ví dụ `topics=spring&topics=java`. Encoding Object cho phép mô tả cách serialize property khi mặc định không đủ rõ. Hãy kiểm tra output của công cụ client generator vì mức hỗ trợ serialization có thể khác nhau.

Không nhầm encoding của OpenAPI với charset hoặc content type của toàn bộ request. Encoding ở đây mô tả cách biểu diễn từng property trong media type form.

## 9. Khai báo request body form-urlencoded bằng springdoc-openapi

Springdoc có thể suy luận nhiều thông tin từ mapping, tham số và DTO. Tuy nhiên, với `@ModelAttribute`, tùy phiên bản và cách khai báo, các thuộc tính có thể được biểu diễn như parameters. Nếu hợp đồng cần thể hiện rõ đây là một request body form-urlencoded, hãy khai báo media type và schema tường minh bằng annotation OpenAPI.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SubscriptionController {

    @Operation(
        summary = "Đăng ký gói dịch vụ",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Các trường của biểu mẫu đăng ký",
            required = true,
            content = @Content(
                mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                schema = @Schema(implementation = SubscriptionForm.class)
            )
        )
    )
    @PostMapping(
        path = "/api/subscriptions",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<SubscriptionResponse> create(
            @Valid @ModelAttribute SubscriptionForm form) {

        SubscriptionResponse created = subscriptionService.create(form);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
~~~

Ở đây có hai annotation cùng tên RequestBody nhưng vai trò khác nhau:

- `io.swagger.v3.oas.annotations.parameters.RequestBody` nằm trong thuộc tính `requestBody` của `@Operation`, dùng để mô tả hợp đồng OpenAPI.
- `@ModelAttribute` của Spring MVC bind các request parameters vào DTO lúc chạy.

Không thay `@ModelAttribute` bằng annotation `@RequestBody` của Spring chỉ để Swagger UI hiển thị một body. Việc đó thay đổi cơ chế đọc dữ liệu của ứng dụng và có thể không phù hợp với cách Servlet container phân tích form.

Sau khi chạy ứng dụng, mở `/v3/api-docs` và xác nhận operation có `requestBody.content.application/x-www-form-urlencoded` với schema SubscriptionForm. Nếu springdoc đồng thời tạo các query parameters trùng với trường form, hãy điều chỉnh cách mô tả parameter của model attribute theo phiên bản đang dùng và kiểm tra lại JSON sinh ra. Đặc tả cuối cùng phải có đúng một cách diễn đạt rõ ràng cho dữ liệu body.

Với phiên bản springdoc đang suy luận `@ModelAttribute` thành các parameters riêng, có thể ẩn phần suy luận đó trên tham số Spring bằng `@Parameter(hidden = true)` trong khi vẫn giữ requestBody được khai báo tường minh trong `@Operation`:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@Operation(
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = SubscriptionForm.class)
        )
    )
)
@PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<SubscriptionResponse> create(
        @Parameter(hidden = true)
        @Valid @ModelAttribute SubscriptionForm form) {
    // Xử lý form và trả response.
}
~~~

Đây là cách xử lý tùy theo kết quả đặc tả thực tế, không phải annotation bắt buộc cho mọi dự án. Kiểm tra JSON sinh ra để chắc chắn requestBody vẫn còn và các field không bị lặp ở parameters.

### Mô tả response cùng request body

Có thể kết hợp request body với các response thành công và lỗi:

~~~java
@Operation(
    summary = "Đăng ký gói dịch vụ",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = SubscriptionForm.class)
        )
    )
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đã tạo đăng ký",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = SubscriptionResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu form không hợp lệ",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
~~~

Đây là phần annotation bổ sung cho operation ở ví dụ trước. Hãy bảo đảm response thực tế có cùng status, media type và body schema như mô tả. Annotation chỉ tạo metadata OpenAPI, không tự thay đổi response HTTP.

## 10. Kiểm tra cấu trúc OpenAPI được sinh ra

Một operation form-urlencoded đúng thường có cấu trúc tương tự:

~~~yaml
paths:
  /api/subscriptions:
    post:
      requestBody:
        required: true
        content:
          application/x-www-form-urlencoded:
            schema:
              $ref: '#/components/schemas/SubscriptionForm'
      responses:
        '201':
          description: Đã tạo đăng ký
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SubscriptionResponse'
        '400':
          description: Dữ liệu form không hợp lệ
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

Hãy kiểm tra các điểm sau trong JSON/YAML:

- Request body có media type `application/x-www-form-urlencoded`.
- Schema là object với tên field đúng như form HTML và DTO.
- Trường bắt buộc nằm trong `required`; trường tùy chọn không bị đánh dấu nhầm.
- Kiểu dữ liệu, format, enum và giới hạn khớp với validation.
- Response có status code, media type và schema đúng.
- Không xuất hiện query parameter trùng với các field đã được mô tả trong body, trừ khi API thực sự nhận chúng cả ở query.

Swagger UI nên hiển thị các trường form tương ứng. Nếu giao diện vẫn hiện một ô JSON, hãy kiểm tra content type trong OpenAPI JSON trước; Swagger UI chỉ render theo đặc tả được cung cấp.

### Khác biệt giữa requestBody và parameters

Form-urlencoded POST có body trong OpenAPI:

~~~yaml
requestBody:
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        properties:
          email:
            type: string
~~~

Query parameter nằm trong URL và được khai báo ở parameters:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
~~~

Một request có thể có cả query parameter lẫn form body. Ví dụ `POST /api/subscriptions?source=campaign` có thể nhận `source` ở query và `email`, `plan` trong body. Hãy mô tả chúng ở đúng vị trí để client gửi request chính xác.

## 11. Phân biệt form-urlencoded với multipart/form-data và JSON

Chọn media type theo dạng dữ liệu:

| Định dạng | Cấu trúc | Dùng khi nào |
|---|---|---|
| `application/x-www-form-urlencoded` | Các cặp key/value đã URL-encode | Biểu mẫu có trường văn bản, số, lựa chọn |
| `multipart/form-data` | Nhiều part, mỗi part có header riêng | Form có file hoặc dữ liệu nhị phân |
| `application/json` | Object hoặc array JSON | API trao đổi cấu trúc dữ liệu lồng nhau |

Với form có file, dùng `multipart/form-data`:

~~~java
@PostMapping(
    path = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public DocumentResponse upload(
        @RequestPart("title") String title,
        @RequestPart("file") MultipartFile file) {
    return documentService.upload(title, file);
}
~~~

OpenAPI mô tả multipart với media type `multipart/form-data` và schema có property tương ứng. Không dùng `application/x-www-form-urlencoded` để gửi file nhị phân thông thường.

JSON phù hợp hơn khi body có object lồng sâu, kiểu dữ liệu phức tạp hoặc cấu trúc cần biểu diễn rõ ràng. Form-urlencoded phù hợp với form HTML truyền thống và các API yêu cầu định dạng key/value. Đừng chọn media type chỉ vì controller có thể bind dữ liệu; hãy chọn theo hợp đồng mà client cần gửi.

## 12. Các lưu ý khi binding dữ liệu form

### Tránh bind trực tiếp entity

Không nên bind toàn bộ entity persistence từ request:

~~~java
// Không nên: client có thể gửi thêm trường không dự kiến của entity.
public ResponseEntity<?> update(@ModelAttribute UserEntity user) {
    // ...
}
~~~

Hãy dùng DTO chỉ chứa trường client được phép gửi. Nếu entity có các thuộc tính như role, accountStatus, ownerId hoặc internalFlag, binding tự động có thể tạo ra rủi ro mass assignment nếu các trường đó bị thay đổi ngoài ý muốn.

~~~java
public record UpdateProfileForm(
    @NotBlank String displayName,
    @Email String contactEmail
) {}
~~~

Controller chỉ nhận các trường được định nghĩa trong DTO:

~~~java
@PostMapping(
    path = "/api/profile",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
public ProfileResponse updateProfile(
        @Valid @ModelAttribute UpdateProfileForm form) {
    return profileService.updateCurrentUser(form);
}
~~~

### Kiểm soát trường được bind

Với DTO có setter và data binder tùy chỉnh, Spring MVC cho phép cấu hình allowed fields thông qua `@InitBinder`. Đây là một lớp bảo vệ bổ sung khi cần giới hạn chính xác thuộc tính được bind:

~~~java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "contactEmail");
}
~~~

Tên đối tượng trong `@InitBinder` phải khớp với tên model attribute. Ví dụ có thể đặt tên tường minh bằng `@ModelAttribute("profileForm")`. Dù có allowed fields, vẫn nên dùng DTO riêng có bề mặt dữ liệu nhỏ; không dùng binder như lý do để bind entity lớn.

### Giá trị rỗng, thiếu và checkbox

Các trạng thái sau có thể khác nhau:

- Trường không xuất hiện trong body.
- Trường xuất hiện nhưng giá trị rỗng, ví dụ `note=`.
- Trường xuất hiện với khoảng trắng, ví dụ `note=+++`.
- Trường xuất hiện nhiều lần với cùng tên.

Quy tắc validation như `@NotNull`, `@NotBlank` và `@NotEmpty` xử lý các tình huống khác nhau. `@NotBlank` phù hợp với chuỗi không được rỗng hoặc chỉ chứa khoảng trắng. Với collection, cần quy định riêng danh sách thiếu có nghĩa là không chọn mục nào hay là request không hợp lệ.

### Chuyển đổi kiểu và định dạng ngày giờ

Form truyền giá trị dưới dạng chuỗi. Spring cần chuyển đổi chuỗi sang kiểu đích. Với ngày tháng, số thập phân hoặc enum, hãy quy định định dạng rõ ràng và kiểm thử cả giá trị hợp lệ lẫn sai định dạng. Ví dụ:

~~~java
public record BookingForm(
    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate startDate,
    @NotNull
    Integer guestCount
) {}
~~~

Trong OpenAPI, mô tả ngày là string với format date; số lượng khách là integer với minimum phù hợp. Đừng để client đoán định dạng ngày từ locale của trình duyệt hoặc máy chủ.

## 13. Bảo mật khi nhận form data

Form-urlencoded thường xuất hiện trong ứng dụng trình duyệt dùng cookie phiên. Khi đó, cần chú ý các điểm sau:

- Bật và sử dụng CSRF protection của Spring Security cho các request thay đổi trạng thái được trình duyệt gửi bằng cookie. Không tắt CSRF chỉ để làm form hoạt động.
- Dùng HTTPS để bảo vệ dữ liệu trên đường truyền. URL encoding không phải mã hóa bảo mật.
- Không đặt mật khẩu, token hoặc dữ liệu nhạy cảm trong query string. Body form không tự động an toàn: proxy, log ứng dụng hoặc hệ thống giám sát vẫn có thể ghi lại body.
- Giới hạn kích thước request, số trường và độ dài giá trị để tránh request quá lớn.
- Chỉ bind các trường client được phép điều khiển; không tin role, owner hoặc trạng thái quyền do form gửi lên.
- Tránh ghi toàn bộ form vào log nếu có thông tin cá nhân hoặc bí mật.

Nếu API được gọi bởi client không dùng cookie mà dùng bearer token, cần cấu hình xác thực phù hợp. Cách xử lý CSRF phụ thuộc cơ chế xác thực và bối cảnh trình duyệt; hãy tuân theo mô hình bảo mật của ứng dụng thay vì tắt bảo vệ một cách rộng rãi.

## 14. Kiểm thử endpoint form-urlencoded

Kiểm thử cần xác minh cả binding và phản hồi. Với Spring MVC, MockMvc có thể mô phỏng request parameters cùng content type:

~~~java
@WebMvcTest(SubscriptionController.class)
class SubscriptionControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    SubscriptionService subscriptionService;

    @Test
    void acceptsFormUrlEncodedFields() throws Exception {
        given(subscriptionService.create(any(SubscriptionForm.class)))
            .willReturn(new SubscriptionResponse(42L, "dev@example.com", "pro"));

        mockMvc.perform(post("/api/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("email", "dev@example.com")
                .param("plan", "pro")
                .param("note", "Spring Boot"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void rejectsInvalidEmail() throws Exception {
        mockMvc.perform(post("/api/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "not-an-email")
                .param("plan", "pro"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Đây là ví dụ kiểm tra binding qua request parameters của MockMvc; `.param(...)` thiết lập tham số trong mock request và không tự kiểm chứng cách một trình duyệt URL-encode raw body. Để xác nhận toàn bộ đường đi của body form-urlencoded, hãy bổ sung kiểm thử tích hợp gửi chuỗi body thực bằng HTTP client hoặc chạy ứng dụng trên cổng ngẫu nhiên.

Ví dụ request thực:

~~~bash
curl -i http://localhost:8080/api/subscriptions -H "Content-Type: application/x-www-form-urlencoded" -H "Accept: application/json" --data-urlencode "email=dev@example.com" --data-urlencode "plan=pro" --data-urlencode "note=Spring Boot & OpenAPI"
~~~

Kiểm tra status `201`, Content-Type response, body JSON và các giá trị đã được giải mã đúng. Tiếp theo gửi dữ liệu thiếu, sai email, plan không nằm trong enum, ký tự tiếng Việt, dấu cộng, dấu &, trường lặp và body sai media type để xác nhận hành vi lỗi.

### Kiểm tra đặc tả springdoc

Trong cùng test context, có thể gọi endpoint OpenAPI và kiểm tra content type:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/subscriptions'].post.requestBody.content['application/x-www-form-urlencoded']"
    ).exists());
~~~

Đường dẫn JSONPath trên minh họa việc xác nhận media type. Có thể kiểm tra sâu hơn schema properties, required và response code. Nếu ứng dụng có GroupedOpenApi, hãy gọi đúng endpoint tài liệu của nhóm chứa operation.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nhận `415 Unsupported Media Type` | Client gửi Content-Type không được endpoint chấp nhận | Gửi `application/x-www-form-urlencoded` và khai báo `consumes` đúng |
| DTO không nhận được giá trị | Tên field form không khớp tên property hoặc binder không tạo được DTO | Kiểm tra name, getter/setter hoặc constructor binding |
| Dấu cộng biến thành dấu cách | Dấu cộng chưa được encode khi nó là dữ liệu thật | Mã hóa dấu cộng thành `%2B` |
| Ký tự `&` làm tách trường | Giá trị chưa được URL-encode | Dùng `--data-urlencode` hoặc encoder của client |
| Danh sách checkbox bị thiếu | Trình duyệt không gửi checkbox chưa chọn | Quy định rõ trường vắng mặt tương ứng danh sách rỗng hay lỗi |
| Swagger UI hiển thị body như JSON | OpenAPI content chưa khai báo form-urlencoded | Kiểm tra `requestBody.content` trong `/v3/api-docs` |
| Các field form xuất hiện thành query parameters | Springdoc suy luận `@ModelAttribute` theo cách khác dự kiến | Khai báo requestBody tường minh và kiểm tra đặc tả cuối |
| Validation không chạy | Thiếu `@Valid`, constraint hoặc dependency validation | Bổ sung Bean Validation và kiểm tra handler |
| Request bị từ chối do CSRF | Token CSRF thiếu hoặc không hợp lệ | Gửi token theo cơ chế Spring Security; giữ bảo vệ CSRF |
| Trường ngoài ý muốn bị cập nhật | Bind trực tiếp entity hoặc DTO có quá nhiều setter | Dùng request DTO riêng và giới hạn trường được phép bind |

## 16. Bài thực hành tổng hợp

Xây dựng endpoint đăng ký nhận bản tin:

1. Tạo `SubscriptionForm` gồm email, plan, note và danh sách topics.
2. Dùng `@NotBlank`, `@Email`, `@Size` và enum/validation phù hợp.
3. Tạo endpoint POST với `consumes = application/x-www-form-urlencoded`.
4. Bind DTO bằng `@ModelAttribute` và trả `201 Created` khi tạo đăng ký.
5. Xử lý lỗi binding và validation thành response lỗi nhất quán.
6. Khai báo request body OpenAPI với media type form-urlencoded, schema và ví dụ.
7. Xác nhận Swagger UI hiển thị đúng trường, enum và trường bắt buộc.
8. Gửi request bằng curl với dấu cách, tiếng Việt, dấu cộng và dấu &.
9. Viết test MockMvc cho dữ liệu hợp lệ, thiếu trường và sai định dạng.
10. Kiểm tra CSRF nếu endpoint được gọi từ trình duyệt dùng session cookie.
11. So sánh OpenAPI JSON với request/response thực tế và sửa mọi điểm không khớp.

### Tiêu chí hoàn thành

- [ ] Endpoint chỉ nhận đúng media type đã công bố.
- [ ] Spring bind đúng các field form vào DTO hoặc tham số.
- [ ] Ký tự đặc biệt và Unicode được URL-encode/giải mã chính xác.
- [ ] Trường bắt buộc, tùy chọn và trường lặp được xử lý theo quy ước rõ ràng.
- [ ] Bean Validation chạy ở server và trả lỗi có cấu trúc.
- [ ] OpenAPI khai báo `application/x-www-form-urlencoded` trong requestBody.
- [ ] Swagger UI hiển thị form fields thay vì một body JSON.
- [ ] Test xác minh binding, validation, status và response body.
- [ ] Không có dữ liệu nhạy cảm bị lộ qua DTO, log hoặc query string.

## Tiếp tục học

Sau bài này, hãy học tiếp multipart/form-data cho upload file, request body JSON và cách mô tả encoding/example trong OpenAPI. Khi thiết kế endpoint nhận form, hãy đối chiếu ba phần: tên field HTML, DTO/binding của Spring MVC và schema requestBody trong đặc tả. Khi cả ba thống nhất, client có thể gửi đúng dữ liệu và tài liệu API phản ánh chính xác hành vi của ứng dụng.
