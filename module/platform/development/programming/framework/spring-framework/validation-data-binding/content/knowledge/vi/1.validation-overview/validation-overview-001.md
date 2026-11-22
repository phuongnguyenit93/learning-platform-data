# Data binding là gì và vì sao cần gắn dữ liệu vào đối tượng?

Trong Spring Framework, **data binding (liên kết dữ liệu)** là quá trình đưa các giá trị đầu vào vào một đối tượng Java theo cấu trúc đã định nghĩa, đồng thời chuyển đổi kiểu dữ liệu khi cần. Đầu vào thường là tham số của HTTP request (query string, biểu mẫu HTML), nhưng cơ chế `DataBinder` của Spring cũng có thể dùng ngoài tầng web.

Mục tiêu là biến những cặp tên–giá trị rời rạc thành một đối tượng có kiểu rõ ràng để chương trình xử lý dễ đọc, nhất quán và kiểm soát được. Data binding **không tự bảo đảm** dữ liệu hợp lệ hoặc an toàn: chuyển đổi kiểu, kiểm tra ràng buộc và giới hạn trường được phép gán là những bước cần phân biệt.

## 1. Bài toán trước khi có data binding

Giả sử người dùng gửi biểu mẫu đăng ký hồ sơ:

~~~http
POST /profiles
Content-Type: application/x-www-form-urlencoded

displayName=Lan&age=23
~~~

Ở giao thức HTTP, `displayName` và `age` trước hết được truyền dưới dạng giá trị văn bản. Nhưng phần xử lý nghiệp vụ muốn làm việc với một đối tượng như sau:

~~~java
public record ProfileForm(String displayName, Integer age) {}
~~~

Nếu lấy từng tham số thủ công, controller phải gọi từng tên trường, tự đổi chuỗi thành số, xử lý thiếu giá trị và quản lý lỗi cho từng trường. Ví dụ minh họa:

~~~java
@PostMapping("/profiles-manual")
public void manual(
        @RequestParam("displayName") String displayName,
        @RequestParam("age") String ageText) {
    int age = Integer.parseInt(ageText);
    // Tự tạo đối tượng, tự xử lý lỗi nếu ageText không phải số.
}
~~~

Cách thủ công còn có thể chấp nhận với một vài tham số độc lập. Khi biểu mẫu gồm nhiều trường, địa chỉ lồng nhau, danh sách sản phẩm hoặc trường ngày tháng, số dòng mã lặp lại và khả năng sai tên, sai kiểu, bỏ sót lỗi tăng nhanh.

Data binding giải quyết phần việc chung đó: đối chiếu tên đầu vào với trường/đối số khởi tạo của đối tượng và chuyển giá trị sang kiểu cần thiết.

## 2. Dữ liệu được “gắn” vào đối tượng như thế nào?

Hãy xem phép ánh xạ đơn giản:

| Dữ liệu đầu vào | Thành phần của đối tượng | Kết quả mong muốn |
| --- | --- | --- |
| `displayName=Lan` | `ProfileForm.displayName` | Chuỗi `"Lan"` |
| `age=23` | `ProfileForm.age` | Số nguyên `23` |
| `address.city=Hue` | `address.city` của một đối tượng lồng nhau | Chuỗi `"Hue"` |
| `items[0].quantity=2` | Phần tử đầu của một danh sách đối tượng | Số nguyên `2` |

Hai cách binding chính trong Spring là:

- **Constructor binding:** lấy đầu vào theo tên tham số của constructor để **tạo** đối tượng. Rất phù hợp với `record` hoặc DTO bất biến, vì chỉ những thành phần khai báo trong constructor mới được nhận qua đường này.
- **Property binding:** lấy đầu vào theo tên property và dùng setter (theo quy ước JavaBeans) để **gán** vào đối tượng có thể thay đổi. Với nested property, Spring có thể đi theo đường dẫn thuộc tính phù hợp.

Theo cấu hình mặc định, `DataBinder` có thể áp dụng cả constructor binding và property binding. Kiểu đối tượng, cấu hình binder và cơ chế tích hợp cụ thể quyết định đường gán được sử dụng.

**Tên phải có ý nghĩa:** khóa `age` không tự động trở thành `birthYear`; nếu tên không khớp, cần khai báo cơ chế ánh xạ hoặc đổi thiết kế đầu vào. Việc chuyển `"23"` thành `Integer` là **type conversion**, một phần quan trọng trong quá trình bind.

## 3. Luồng xử lý trong Spring MVC

Ở controller có tham số `@ModelAttribute`, luồng xử lý điển hình là:

1. Trình duyệt gửi tham số form hoặc query tới endpoint.
2. Spring MVC tìm hoặc tạo model attribute (có thể qua constructor), và chuẩn bị một `WebDataBinder` cho request.
3. Binder ghép tên đầu vào với các tham số constructor/property có thể bind, rồi dùng cơ chế chuyển đổi kiểu nếu cần.
4. Lỗi binding, như `age=abc` khi trường đích là `Integer`, được ghi nhận trong kết quả binding.
5. Nếu có `@Valid` hoặc `@Validated` và validator được cấu hình, bước **validation** kiểm tra các ràng buộc nghiệp vụ/dữ liệu tiếp theo.
6. Controller sử dụng DTO đã nhận; nếu khai báo `BindingResult` ngay sau tham số cần bind thì có thể xử lý lỗi tại chỗ, sau đó mới chuyển dữ liệu hợp lệ sang service.

Sơ đồ khái quát:

~~~text
HTTP form / query
       |
       v
Spring MVC + WebDataBinder
  |  khớp tên, tạo/gán đối tượng
  |  chuyển String -> Integer, LocalDate, ...
       v
DTO / Form Object
       |
       +--> BindingResult: lỗi chuyển đổi/gán giá trị
       |
       +--> @Valid / @Validated (nếu bật): lỗi ràng buộc
       v
Controller -> Service -> nghiệp vụ
~~~

`DataBinder` là thành phần cốt lõi của Spring cho việc bind. `WebDataBinder` bổ sung tích hợp với môi trường web, còn `ConversionService`, `Converter` và `Formatter` hỗ trợ chuyển đổi hoặc định dạng giá trị. Từ góc nhìn lập trình viên MVC, `@ModelAttribute` giúp Spring thực hiện phần lớn công việc chuẩn bị đối tượng và binding.

## 4. Ví dụ thực tế: nhận form bằng một DTO có kiểu

Ví dụ sau là một class Java 17+ hoàn chỉnh về mặt cú pháp để đặt trong **dự án Spring Boot có Spring MVC và Bean Validation** (thường là các starter `spring-boot-starter-web` và `spring-boot-starter-validation`). Đây là class controller của ứng dụng, không phải chương trình Java độc lập có hàm `main`.

~~~java
package com.example.demo;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    // DTO chuyên dùng để nhận dữ liệu của biểu mẫu.
    public record ProfileForm(
            @NotBlank String displayName,
            @NotNull @Min(18) Integer age) {
    }

    public record ProfileResponse(String displayName, Integer age) {
    }

    @PostMapping(
            path = "/profiles",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute ProfileForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            List<String> errors = bindingResult.getFieldErrors().stream()
                    .map(error -> error.getField() + ": " + error.getCode())
                    .toList();
            return ResponseEntity.badRequest().body(errors);
        }

        return ResponseEntity.ok(
                new ProfileResponse(form.displayName(), form.age()));
    }
}
~~~

Khi chạy ứng dụng Spring Boot có class trên, có thể gửi request bằng terminal Bash:

~~~bash
curl -i -X POST "http://localhost:8080/profiles" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "displayName=Lan&age=23"
~~~

**Kết quả mong đợi:** HTTP `200 OK`, phần thân JSON chứa `displayName` là `"Lan"` và `age` là số `23` (thứ tự các trường JSON không phải cam kết của ví dụ).

Điều đã xảy ra:

- `@ModelAttribute ProfileForm form` yêu cầu Spring tạo và bind form object từ các tham số request. Với `record`, Spring có thể sử dụng constructor binding.
- Dù `age` được truyền bằng chuỗi `"23"` trong form, giá trị bên trong `form.age()` có kiểu `Integer`.
- `@Valid` yêu cầu kiểm tra `@NotBlank`, `@NotNull` và `@Min(18)` sau khi bind.
- `BindingResult` phải nằm **ngay sau** tham số `@ModelAttribute` tương ứng để controller nhận và xử lý lỗi.
- DTO nhận request tách biệt với entity lưu cơ sở dữ liệu. Service mới nên quyết định nghiệp vụ và cách lưu trữ.

Thử thay `age=17`: giá trị có thể chuyển sang số nhưng vi phạm `@Min(18)`, nên controller trả `400 Bad Request` và danh sách lỗi. Thử `age=abc`: chuyển chuỗi sang số thất bại, cũng sinh lỗi binding và trả `400` qua nhánh `BindingResult`. Chuỗi mã lỗi cụ thể trong phản hồi phụ thuộc loại lỗi và cấu hình validation.

Nếu không truyền `BindingResult` đúng vị trí, Spring MVC thường xử lý lỗi bằng cơ chế exception thay vì đi vào nhánh `hasErrors()` của controller. Việc xử lý exception có thể được cấu hình riêng ở ứng dụng.

## 5. Vì sao cần gắn dữ liệu vào đối tượng?

**Giảm mã chuyển đổi và gán thủ công.** Không phải lặp lại thao tác lấy từng giá trị HTTP, parse số/ngày và gọi setter ở mọi endpoint. Binder tái sử dụng một cơ chế nhất quán.

**Có kiểu dữ liệu rõ ràng.** Service nhận `ProfileForm` với `Integer age` thay vì `Map<String, String>` chứa toàn chuỗi. Kiểu dữ liệu cho phép IDE, trình biên dịch và người đọc hiểu cấu trúc đầu vào; lỗi chuyển đổi cũng được báo có hệ thống.

**Gom dữ liệu có liên quan.** Một yêu cầu “tạo hồ sơ” có thể được mô hình hóa thành một DTO; các trường lồng nhau như `address.city` hoặc phần tử danh sách như `items[0].quantity` được thể hiện đúng cấu trúc của bài toán.

**Dễ kiểm tra và phản hồi lỗi theo trường.** Binding cung cấp thông tin lỗi gán/chuyển kiểu; Bean Validation bổ sung các quy tắc như bắt buộc nhập, độ dài và giới hạn giá trị. UI có thể hiển thị lỗi ngay tại trường tương ứng.

**Tách trách nhiệm giữa các lớp.** Controller chịu trách nhiệm nhận và kiểm soát dữ liệu đầu vào; DTO mô tả hợp đồng request; service thực thi nghiệp vụ; entity thể hiện trạng thái lưu trữ. Nhờ đó thay đổi một biểu mẫu ít có lý do tác động trực tiếp tới mô hình cơ sở dữ liệu.

**Giúp chuẩn hóa luồng nhập dữ liệu.** Khi nhiều endpoint cùng làm việc với form hoặc query parameters, dùng cơ chế binding và conversion của framework thường dễ bảo trì hơn mỗi nơi tự viết bộ parse riêng.

Các lợi ích này không có nghĩa mọi request đều cần DTO phức tạp: với một tham số độc lập, `@RequestParam` vẫn phù hợp.

## 6. Phân biệt binding, conversion và validation

Ba khái niệm thường đi cùng nhau nhưng có vai trò khác nhau:

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Binding** | Dữ liệu đầu vào sẽ vào property/constructor parameter nào? | `age` -> `ProfileForm.age` |
| **Conversion** | Giá trị cần biến thành kiểu Java nào? | `"23"` -> `Integer 23` |
| **Validation** | Giá trị đã nhận có đạt quy tắc không? | `age >= 18`, `displayName` không rỗng |

Ví dụ `age=abc` là **lỗi chuyển đổi khi binding**; `age=17` là **lỗi validation** trong ví dụ trên. Đối tượng được tạo thành công không đồng nghĩa với dữ liệu đã hợp lệ về mặt nghiệp vụ; validation hợp lệ cũng không tự giải quyết các vấn đề ủy quyền như người dùng có được phép sửa hồ sơ của người khác hay không.

Để hỗ trợ kiểu đặc thù như mã định danh, tiền tệ hoặc ngày tháng, ứng dụng có thể cấu hình `Converter` hoặc `Formatter`. Việc parse nên nhất quán theo định dạng/locale đã quy định, không dựa vào phỏng đoán các chuỗi đầu vào.

## 7. Khi nào dùng @ModelAttribute, @RequestParam và @RequestBody?

| Trường hợp | Cách thường dùng | Lưu ý |
| --- | --- | --- |
| Một vài query/form parameter riêng lẻ | `@RequestParam` | Phù hợp với giá trị đơn như `page`, `size` |
| Form HTML hoặc nhóm tham số query biểu diễn một đối tượng | `@ModelAttribute` | Spring MVC dùng data binding vào DTO |
| JSON request body của REST API | `@RequestBody` | `HttpMessageConverter` (thường kết hợp Jackson) đọc JSON để tạo object |
| Một đoạn động trên URL | `@PathVariable` | Lấy giá trị từ route, ví dụ `/profiles/{id}` |

Ví dụ request JSON:

~~~http
POST /profiles-json
Content-Type: application/json

{"displayName":"Lan","age":23}
~~~

Trường hợp này thường khai báo `@Valid @RequestBody ProfileForm form`. JSON được giải mã bằng HTTP message converter, không phải cùng quy trình property binding form của `@ModelAttribute`; sau khi tạo object, validation vẫn có thể được áp dụng.

Một điểm dễ nhầm khác: **data binding không phải ORM/database mapping**. Binding nhận dữ liệu đầu vào vào object; JPA/Hibernate mapping quản lý quan hệ giữa object/entity và bảng cơ sở dữ liệu. Hai việc ở những ranh giới khác nhau của ứng dụng.

## 8. An toàn dữ liệu: chỉ bind những gì được phép

Dữ liệu từ HTTP request là **không đáng tin cậy**. Nếu gắn trực tiếp toàn bộ request lên entity có setter cho các thuộc tính nhạy cảm, kẻ tấn công có thể gửi thêm tham số như `role=ADMIN`, `isAdmin=true` hoặc `ownerId=...` để thử sửa những giá trị mà giao diện không hiển thị. Đây là rủi ro **mass assignment / over-posting**.

Các nguyên tắc thực tế:

1. Dùng **DTO dành riêng cho từng thao tác** (đăng ký, cập nhật hồ sơ, đổi mật khẩu...), chỉ có trường được phép nhận. DTO bất biến hoặc Java `record` giúp giới hạn tập tham số qua constructor.
2. Không dùng việc ẩn trường trên HTML làm biện pháp bảo mật. Server phải tự xác thực quyền truy cập và quyết định trường nào được cập nhật.
3. Khi bắt buộc dùng **property binding** với object có setter, đặt danh sách cho phép qua `WebDataBinder#setAllowedFields(...)`; tránh cho phép mọi property của entity.
4. Giới hạn kích thước và độ phức tạp của dữ liệu đầu vào theo yêu cầu hệ thống; xử lý lỗi conversion/validation rõ ràng.
5. Không coi DTO hợp lệ là đủ quyền thực hiện hành động. Service vẫn cần kiểm tra quy tắc nghiệp vụ và phân quyền.

Ví dụ minh họa khi một controller dùng **mutable form DTO** được đặt tên `profileForm`:

~~~java
@InitBinder("profileForm")
void restrictProfileFields(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "age");
}
~~~

Đoạn này cần import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`, đặt trong controller hoặc cấu hình advice phù hợp. Nó giới hạn **property binding**, không phải bộ lọc chung cho mọi đối số constructor. Vì vậy nên ưu tiên thiết kế DTO có đúng các trường chấp nhận được ngay từ đầu. `@InitBinder` và `@ControllerAdvice` là những điểm mở rộng của Spring MVC để cấu hình binder khi cần.

## 9. Những lỗi hiểu nhầm thường gặp

- **“Bind xong là dữ liệu hợp lệ.”** Sai. Binding làm việc với gán và chuyển kiểu; muốn kiểm tra ràng buộc cần validator và phải xử lý lỗi.
- **“Form gửi lên là Java object rồi.”** Sai. HTTP truyền dữ liệu theo cách mã hóa của request; Spring mới tạo/gán object theo hợp đồng của controller.
- **“@ModelAttribute xử lý mọi JSON giống @RequestBody.”** Sai. Hai annotation có cơ chế lấy dữ liệu và chuyển đổi khác nhau.
- **“Tên trường sai thì framework sẽ tự hiểu.”** Không nên dựa vào điều này. Tên, đường dẫn property, constructor parameter, converter và quy tắc binding phải tương thích.
- **“Có @Valid là tránh được mass assignment.”** Sai. Validation kiểm tra giá trị theo constraint; quyền cập nhật property và quyền thao tác tài nguyên là mối quan tâm riêng.
- **“Có thể đặt BindingResult ở bất kỳ vị trí nào.”** Sai. Với model attribute cần xử lý lỗi ngay trong controller, `BindingResult` phải đứng liền sau đối số được bind/validate.

## 10. Tự kiểm tra kiến thức

1. Với form `displayName=Lan&age=23`, hãy chỉ ra bước nào tìm property/constructor parameter, bước nào đổi `"23"` thành số và bước nào kiểm tra tuổi tối thiểu.
2. Nếu đổi `age` thành `abc`, điều gì xảy ra trước khi kiểm tra `@Min(18)`? Controller có thể lấy lỗi đó qua thành phần nào?
3. Nếu request gửi thêm `isAdmin=true` nhưng `ProfileForm` chỉ khai báo `displayName` và `age`, vì sao thiết kế DTO như vậy giảm bề mặt gán dữ liệu?
4. Khi client gửi JSON body, vì sao nên chọn `@RequestBody` thay vì giả định `@ModelAttribute` luôn xử lý cùng cách?

**Điểm cần nhớ:** Spring data binding nối dữ liệu đầu vào với cấu trúc Java object thông qua quy tắc tên và chuyển đổi kiểu. Nó giúp controller làm việc với dữ liệu có cấu trúc, giảm mã lặp và hỗ trợ xử lý lỗi; chất lượng đầu vào và quyền cập nhật vẫn phải được kiểm soát bằng validation, DTO phù hợp và kiểm tra nghiệp vụ.

### Tài liệu tham khảo chính thức

- Spring Framework — Data Binding (Core): https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring MVC — Data Binding và Model Design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring MVC — `@ModelAttribute` method arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html