# Lựa chọn đối tượng đích và cách khởi tạo trong Spring Framework Data Binding

## 1. Đối tượng đích là gì, và vì sao phải chọn đúng?

Trong Spring MVC, dữ liệu do client gửi lên thường bắt đầu ở dạng chuỗi như `displayName=Lan&age=21`. **Đối tượng đích** (binding target) là object Java mà `WebDataBinder` sẽ đưa các giá trị ấy vào, sau khi xác định tên thuộc tính, kiểu dữ liệu, quy tắc chuyển đổi và các trường được phép ghi.

Ví dụ, với tham số `@ModelAttribute("signupForm") SignupForm form`, Spring phải xác định **object `signupForm` nào** sẽ được sử dụng trước khi bind dữ liệu. Object đó có thể đã tồn tại trong Model/Session, được cung cấp bởi một phương thức tạo Model, được chuyển đổi từ một giá trị trong request, hoặc được Spring khởi tạo mới. Chọn sai object có thể dẫn tới ghi đè dữ liệu cũ, bind nhầm trường hoặc vô tình cho phép client sửa thuộc tính nhạy cảm.

Phân biệt ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Nguồn dữ liệu** | Giá trị client cung cấp; không tin cậy mặc định | `email=lan@example.com`, `age=21` |
| **Đối tượng đích** | Instance Java hiện có hoặc mới tạo để nhận giá trị | `SignupForm`, `ProfileForm` |
| **Binder** | Thành phần điều phối constructor/property binding, conversion và lỗi | `WebDataBinder` trong MVC, `DataBinder` ở tầng core |

Bài này nói về giai đoạn **xác định instance và khởi tạo trước/trong khi bind** của luồng Spring MVC dùng `@ModelAttribute`, đồng thời liên hệ với API `DataBinder` ở tầng Spring Core. `@RequestBody` đi qua cơ chế đọc body và `HttpMessageConverter` (ví dụ deserialize JSON), vì vậy không nên mặc nhiên áp dụng cùng quy tắc chọn model attribute cho `@RequestBody`.

## 2. Từ handler parameter đến đối tượng cụ thể

Luồng tư duy khi Spring MVC xử lý một tham số `@ModelAttribute`:

```text
HTTP request
   |
   v
Handler method đã được xác định
   |
   v
Resolver nhận diện tham số @ModelAttribute
   |
   v
Xác định tên attribute và kiểu Java cần nhận
   |
   v
Tìm/nhận đối tượng đích hiện có trong Model
   |                          \
   | Có                       | Chưa có
   v                          v
Dùng instance đó       Xem nguồn có thể cung cấp object
                              | (ví dụ Converter từ path variable)
                              v
                        Nếu cần, khởi tạo object mới
   \                          /
    v                        v
      Tạo/cấu hình WebDataBinder
                |
                v
   Constructor binding khi cần tạo target
   Property binding khi được cho phép
                |
                v
   BindingResult + validation (nếu được yêu cầu)
                |
                v
      Truyền argument vào controller
```

Sơ đồ trên thể hiện **các khả năng lựa chọn**, không phải cam kết một thứ tự thuật toán bất biến cho mọi phiên bản Spring, mọi resolver và mọi cấu hình. Điểm cốt lõi: khi target đã tồn tại, binder làm việc với instance đó; khi target chưa có, Spring phải tìm cách cung cấp/khởi tạo nó.

### 2.1. Xác định tên trước khi tra cứu

* `@ModelAttribute("profileForm") ProfileForm form` yêu cầu tên model attribute là `profileForm`. Đây là cách dễ kiểm soát nhất khi ghép với phương thức `@ModelAttribute`, `@InitBinder` hoặc `@SessionAttributes`.
* Với `@ModelAttribute ProfileForm form`, Spring suy ra tên theo quy ước của kiểu đối tượng. Không nên giả định tên biến Java luôn quyết định tên attribute; nên khai báo tên rõ ràng ở luồng nhiều model object.
* Một tham số kiểu phức tạp không được resolver khác xử lý có thể được coi là `@ModelAttribute` ngầm định. Viết annotation tường minh giúp người đọc và xử lý AOT/native image dễ suy luận hơn.
* Nếu là tham số đơn giản như `String` hoặc `int`, Spring MVC thường dùng cách phân giải như `@RequestParam`; nếu là `@RequestBody` thì dùng đường xử lý body riêng.

### 2.2. Các con đường có thể cung cấp target

| Nguồn object | Khi nào xuất hiện | Ý nghĩa cho giai đoạn khởi tạo |
| --- | --- | --- |
| **Model của request** | `Model.addAttribute("name", object)` hoặc phương thức `@ModelAttribute("name")` đã thêm object | Tái sử dụng instance có sẵn, không cần tạo bản mới cho tham số đó |
| **`@SessionAttributes` của controller** | Thuộc tính được controller khai báo và được quản lý qua nhiều request | Khôi phục object vào model trong workflow; cần quản lý vòng đời session |
| **`Converter<String, T>`** | Tên attribute khớp một giá trị request/path variable và có converter tương thích | Tạo/lấy `T` từ giá trị chuỗi (có thể tra cứu object trong service) |
| **Constructor của lớp đích** | Không có instance phù hợp được cung cấp | Spring khởi tạo mới bằng constructor rỗng hoặc constructor mang dữ liệu, tùy thiết kế lớp |
| **Caller cung cấp target cho `DataBinder`** | Sử dụng `DataBinder` trực tiếp ngoài cơ chế argument resolver | Caller quyết định object có sẵn hoặc cấu hình type để `construct` |

**Model object không đồng nghĩa với JPA entity:** một `@ModelAttribute` có thể là DTO đầu vào, command object hoặc object domain. Dùng DTO chuyên biệt thường dễ giới hạn input hơn.

## 3. Dùng lại target đã tồn tại

### 3.1. Phương thức `@ModelAttribute` chuẩn bị Model

Phương thức mang `@ModelAttribute` ở mức method trong `@Controller`/`@ControllerAdvice` có thể được gọi trước handler để bổ sung dữ liệu vào Model. Ví dụ sau là **đoạn minh họa bên trong một controller có sẵn**, giả định `profileService` và `ProfileForm` đã được định nghĩa:

```java
@ModelAttribute("profileForm")
public ProfileForm loadProfile(@PathVariable("id") long id) {
    return profileService.loadEditableForm(id);
}

@InitBinder("profileForm")
public void restrictProfileFields(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "city");
}

@PostMapping("/profiles/{id}")
public String saveProfile(
        @PathVariable("id") long id,
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-edit";
    }
    profileService.updateProfile(id, form.getDisplayName(), form.getCity());
    return "redirect:/profiles/" + id;
}
```

Trong request `POST /profiles/42`, `loadProfile` lấy form hiện hành của hồ sơ 42 và gắn tên `profileForm` vào Model. Handler nhận lại **chính instance đó** để bind các thuộc tính được cho phép, thay vì tạo một form rỗng rồi hy vọng ID từ client cho biết nên sửa bản ghi nào. `BindingResult` đứng ngay sau tham số tương ứng để handler xử lý lỗi bind.

Cần phân biệt rõ: Model của request `GET` không tự động tồn tại trong `POST` kế tiếp. Để lấy lại object mỗi request, có thể dùng phương thức nạp model như trên; để duy trì trạng thái qua nhiều request trong một wizard, cân nhắc `@SessionAttributes`. Với dữ liệu persisted, service phải kiểm tra quyền truy cập vào ID ở phía server.

### 3.2. Target được quản lý qua `@SessionAttributes`

`@SessionAttributes("wizardForm")` ở cấp controller dùng để giữ một model attribute qua nhiều request trong cùng workflow. Khi session attribute được khôi phục vào Model, binder có thể làm việc với object đó. Khi hoàn thành quy trình, gọi `SessionStatus.setComplete()` để xóa các attribute do annotation này quản lý.

```java
@Controller
@SessionAttributes("wizardForm")
class WizardController {
    @ModelAttribute("wizardForm")
    WizardForm newWizardForm() {
        return new WizardForm();
    }

    @PostMapping("/wizard/finish")
    String finish(@ModelAttribute("wizardForm") WizardForm form,
                  BindingResult errors,
                  SessionStatus status) {
        if (errors.hasErrors()) {
            return "wizard";
        }
        status.setComplete();
        return "done";
    }
}
```

Đây là ví dụ tích hợp cần có lớp `WizardForm` và cấu hình MVC. `@SessionAttributes` phục vụ model theo phạm vi controller, khác với `@SessionAttribute` dùng để đọc một thuộc tính session đã tồn tại. Không nên biến session thành kho lưu mọi dữ liệu form dài hạn.

### 3.3. Lấy object qua `Converter`

Nếu handler khai báo `@ModelAttribute("account") Account account` với route `/accounts/{account}`, Spring MVC có thể dùng `Converter<String, Account>` đã đăng ký để chuyển giá trị path variable `account` sang `Account`. Converter có thể gọi service để nạp đối tượng cần xử lý.

**Điều kiện quan trọng:** tên attribute phải khớp tên request/path variable phù hợp và phải có converter tương thích. Sự tồn tại của một `Converter<String, Account>` không có nghĩa Spring tự động tìm account theo bất kỳ trường ID nào. Quyền truy cập, trường được bind và trạng thái object sau khi lấy vẫn là trách nhiệm thiết kế của ứng dụng.

## 4. Khi chưa có instance: hai kiểu khởi tạo chính

### 4.1. Constructor rỗng rồi property binding

Với JavaBean mutable có constructor không tham số và setter, Spring có thể tạo object rỗng rồi gán từng thuộc tính được phép:

```java
public class ProfileForm {
    private String displayName;
    private String city;

    public ProfileForm() { }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { this.displayName = value; }

    public String getCity() { return city; }
    public void setCity(String value) { this.city = value; }
}
```

Đối với request `displayName=Lan&city=Da%20Nang` và target `ProfileForm` mới, sau property binding ta có `displayName = "Lan"` và `city = "Da Nang"`. Các giá trị có thể cần conversion nếu kiểu đích là `int`, `LocalDate` hoặc enum.

**Lưu ý:** constructor không tham số chỉ giải quyết việc tạo object; dữ liệu vào các setter là một bước riêng. `setAllowedFields(...)` giới hạn property nào được phép cập nhật; Spring không tự hiểu một setter là “nhạy cảm”. Nếu binder được cấu hình chế độ chỉ cho phép declarative binding mà không khai báo allowed fields, property binding bị bỏ qua.

### 4.2. Constructor binding cho object bất biến

Với một `record` hoặc lớp có constructor dữ liệu rõ ràng, Spring lấy tham số request theo **tên tham số constructor**, chuyển đổi kiểu rồi truyền vào constructor. Đây là cách thích hợp cho form input được thiết kế bất biến. Ví dụ đầy đủ dưới đây là file `SignupController.java` trong **ứng dụng Spring MVC đã cấu hình web**, dùng Java 17+ và Spring Framework 6.1+:

```java
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.*;

@RestController
public class SignupController {

    public record SignupForm(String email, int age) {}

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(path = "/signup",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public String signup(@ModelAttribute("signupForm") SignupForm form,
                         BindingResult errors) {
        if (errors.hasErrors()) {
            return "INVALID";
        }
        return form.email() + " / " + form.age();
    }
}
```

Ví dụ gọi endpoint khi ứng dụng đang chạy:

```http
POST /signup HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&age=21
```

Với input hợp lệ và không có validator bổ sung, response body là:

```text
lan@example.com / 21
```

Giải thích: `SignupForm` không có setter; Spring ghép `email` và `age` vào constructor của record, chuyển `"21"` thành `int`. `@InitBinder("signupForm")` bật `declarativeBinding` để không thực hiện property binding tự do. Không có field `role` trong constructor nên client không thể tạo ra một thuộc tính `role` chỉ bằng việc gửi thêm `role=ADMIN`.

Khi dùng **class** có constructor nhiều tham số, cần bảo đảm tên tham số có thể được Spring đọc (ví dụ biên dịch Java với `-parameters`); Java record lưu thông tin component thuận lợi cho kiểu này. Có thể dùng `@BindParam("display-name")` trên tham số constructor để map key từ request khác tên biến. Nếu lớp có nhiều constructor, lựa chọn constructor chịu quy tắc Spring và cấu trúc lớp; nên ưu tiên một data constructor rõ ràng hoặc cấu hình khởi tạo tường minh để tránh mơ hồ.

Constructor binding có thể khởi tạo cả object lồng nhau; nó cũng hỗ trợ cấu trúc `List`, `Map` và array theo các dạng input được Spring hỗ trợ. Dù vậy, độ sâu và kích thước input từ client vẫn cần được thiết kế, giới hạn và kiểm thử phù hợp.

### 4.3. Dùng `DataBinder` trực tiếp khác gì trong MVC?

Ở Spring Core, caller có thể truyền target đã có bằng `new DataBinder(existingObject, "profileForm")` rồi gọi `bind(PropertyValues)`. Nếu muốn binder **tự tạo target** qua constructor binding (API từ Spring 6.1), caller khởi tạo binder với target `null`, cấu hình `targetType` qua `setTargetType(ResolvableType)`, rồi gọi `construct(ValueResolver)`. Sau đó kiểm tra `getBindingResult()` và `getTarget()`.

```text
Có target từ trước:
  DataBinder(existing, "name") -> bind(propertyValues)

Muốn tạo target bằng constructor:
  DataBinder(null, "name")
      -> setTargetType(...)
      -> construct(valueResolver)
      -> getTarget()/getBindingResult()
      -> bind(...) nếu cần và được cho phép
```

Đây là **sơ đồ gọi API**, không phải một file Java độc lập có thể chạy. Trong controller MVC, resolver và `WebDataBinderFactory` đảm nhiệm phần lớn việc chọn/khởi tạo, nên ứng dụng thường không phải tự gọi chuỗi API này.

## 5. Một target có thể bị bind theo những cách nào?

Cần phân biệt **tạo target** với **điền/ghi đè dữ liệu**:

| Trạng thái lúc binder bắt đầu | Constructor binding | Property binding |
| --- | --- | --- |
| Target chưa tồn tại và được tạo qua data constructor | Đọc input tương ứng với tham số constructor để tạo object | Có thể chạy tiếp nếu object có property phù hợp và cấu hình cho phép |
| Target mới tạo bằng constructor rỗng | Tạo instance không tham số | Setter/JavaBean property nhận các input được phép |
| Target được lấy sẵn từ Model/Session/service/Converter | Không cần chạy constructor lần nữa trên instance đó | Có thể gán đè property được phép nếu bật binding |
| `@ModelAttribute(binding = false)` | Đối tượng vẫn phải được cung cấp/khởi tạo phù hợp | Bỏ qua binding từ request cho tham số này |

Theo mặc định, `DataBinder` hỗ trợ cả constructor binding và property binding. Khi đặt `binder.setDeclarativeBinding(true)`, constructor binding vẫn được hỗ trợ, còn property binding chỉ được thực hiện khi có `allowedFields`. Điều này rất khác với suy nghĩ “đã dùng constructor thì chắc chắn mọi setter đều bị khóa”.

Việc tự động tạo object lồng nhau qua đường property (auto-grow nested paths), nếu được cấu hình và khả thi, cũng không giống việc xây dựng object lồng nhau qua constructor. Không phụ thuộc vào auto-grow để tạo các domain entity phức tạp hoặc đi qua tập thuộc tính không được dự kiến trước.

## 6. Chọn target an toàn khi xử lý biểu mẫu cập nhật

### 6.1. Không bind nguyên request vào entity giàu quyền

Giả sử entity `User` có `displayName`, `role`, `enabled`, `ownerId`. Nếu lấy entity từ database rồi property bind trực tiếp tất cả request parameters, client có thể cố gửi:

```text
displayName=Lan&role=ADMIN&enabled=true
```

Nếu ứng dụng vô tình cho phép ghi các thuộc tính này, nguy cơ **mass assignment/over-posting** xuất hiện. Việc tìm đúng entity theo ID không khiến việc bind mọi field trở nên an toàn.

Ưu tiên:

1. Tạo một DTO chỉ chứa field đầu vào được chấp nhận, tốt nhất là object bất biến với constructor rõ ràng.
2. Với property binding, giới hạn trường bằng `@InitBinder` và `setAllowedFields("displayName", "city")`; tránh wildcard quá rộng.
3. Với ứng dụng phù hợp Spring 6.1+, dùng `setDeclarativeBinding(true)` để constructor binding được áp dụng mà setter binding không tự do.
4. Chọn target persisted và kiểm tra quyền truy cập theo ID ở service; sau đó chỉ copy các trường đã kiểm tra từ DTO vào entity.
5. Khi chỉ cần đọc object từ Model, dùng `@ModelAttribute(binding = false)` để không cho request tự sửa nó. **Không** nhầm `binding=false` với lệnh bỏ qua việc lấy object.

Ví dụ kết hợp một DTO đầu vào với đối tượng được nạp an toàn trong controller (các lớp dịch vụ/domain được giả định đã có):

```java
@ModelAttribute("account")
Account loadAccount(@PathVariable("id") long id) {
    return accountService.findEditableById(id);
}

@PostMapping("/accounts/{id}/name")
String changeName(@ModelAttribute("nameForm") NameForm input,
                  BindingResult errors,
                  @ModelAttribute(value = "account", binding = false)
                  Account account) {
    if (errors.hasErrors()) {
        return "change-name";
    }
    accountService.changeDisplayName(account, input.displayName());
    return "redirect:/accounts/" + account.getId();
}
```

Ở đây `NameForm` nên là DTO/record chỉ nhận `displayName`. Object `account` được tìm ở phía server nhưng không bị bind từ request, nhờ đó hai trách nhiệm “xác định bản ghi” và “nhận dữ liệu người dùng được phép nhập” được tách rõ. Authorization vẫn cần kiểm tra ở service.

### 6.2. Những trường hợp thường gặp

| Tình huống | Target nên chọn | Hệ quả |
| --- | --- | --- |
| Đăng ký mới | DTO/record mới, constructor binding | Mỗi request có instance riêng; chỉ nhận tham số đã khai báo |
| Form sửa hồ sơ | DTO cập nhật nạp từ service, hoặc DTO mới với ID được xử lý phía server | Không để client tự quyết định quyền sửa hay ID tồn tại |
| Wizard nhiều bước | Model attribute được quản lý bởi `@SessionAttributes` khi phù hợp | Tái sử dụng trạng thái, cần `SessionStatus.setComplete()` khi xong |
| Path variable đại diện một domain object | Converter tương thích hoặc phương thức nạp Model | Cần kiểm tra quyền, tồn tại và giới hạn field trước khi cập nhật |
| Chỉ dùng object để đọc dữ liệu | Model attribute với `binding=false` | Không đổ request parameter vào object đọc |
| JSON body vào REST endpoint | `@RequestBody` + message conversion | Luồng tạo object qua deserialize body, khác `@ModelAttribute` |

## 7. Lỗi trong giai đoạn tạo target và giai đoạn bind

**Không tìm được cách khởi tạo.** Class không có constructor được Spring hỗ trợ, constructor có tham số nhưng metadata tên không đọc được, hoặc loại abstract/interface không có cách tạo phù hợp. Kiểm tra thiết kế DTO, constructor, `-parameters`, `@BindParam` và nguồn target từ Model. Tránh kết luận sai rằng client đã thiếu tất cả field khi lỗi thực tế là ở cấu hình constructor.

**Không chuyển đổi được giá trị.** Ví dụ `age=abc` cho `int age` gây lỗi chuyển kiểu; nếu binder có thể biểu diễn lỗi, xem `BindingResult` và mã như `typeMismatch`. Không sử dụng object vừa bind như dữ liệu hợp lệ khi `errors.hasErrors()`. Lỗi tạo instance không phải lúc nào cũng quy về một loại exception duy nhất; handler và phiên bản Spring quyết định cách xử lý cụ thể.

**Chọn nhầm attribute.** `@ModelAttribute("form")` không cùng tên với object được thêm dưới `"profileForm"`, nên Spring có thể không tìm thấy object mong muốn và đi theo đường tạo object mới. Dùng tên tường minh, nhất quán giữa factory method, handler, binder và session annotation.

**Form GET và POST dùng hai instance khác nhau.** Model theo từng HTTP request; object thêm vào Model khi render GET không mặc nhiên còn ở POST. Nạp lại từ service hoặc dùng cơ chế state có vòng đời rõ ràng.

**Đặt sai `BindingResult`.** Nếu cần xử lý lỗi của một `@ModelAttribute` tại controller, đặt `BindingResult` ngay sau tham số đó. Với validation qua `@Valid`/`@Validated`, thiếu `BindingResult` tương ứng có thể khiến Spring ném exception theo cấu hình validation.

**Binder nhận quá nhiều field.** Request chứa tên property không mong muốn; việc target được nạp đúng không ngăn property binding sửa các field khác. Kiểm tra `setAllowedFields`, `declarativeBinding`, DTO và những field bị suppressed.

**Nhầm với lưu dữ liệu.** Binding chỉ chuẩn bị object cho handler. Nó không có nghĩa tự động gọi `repository.save(...)`, commit transaction hoặc xác nhận tính hợp lệ của quyền nghiệp vụ; các quyết định đó vẫn thuộc service/application.

## 8. Quy trình tự kiểm tra khi xây dựng một endpoint

1. Xác định handler parameter đang dùng `@ModelAttribute` hay `@RequestBody`; nếu là `@ModelAttribute`, ghi rõ tên attribute.
2. Hỏi: object mong muốn đã ở Model (bao gồm phương thức factory/session) hay cần được tạo mới?
3. Nếu tạo mới, chọn mutable bean với constructor rỗng và setter **hoặc** immutable DTO/record với data constructor; đảm bảo Spring đọc được tên tham số.
4. Nếu dùng object có sẵn, hỏi có thật sự cho client cập nhật object đó không; nếu không, tắt binding hoặc dùng DTO đầu vào riêng.
5. Cấu hình các trường được phép bind bằng `@InitBinder` và các converter/formatter cần thiết; kiểm tra ảnh hưởng của nested/indexed input.
6. Thêm `BindingResult` đúng vị trí nếu handler chủ động xử lý lỗi và thiết kế validation phù hợp.
7. Kiểm thử tối thiểu ba trường hợp: request hợp lệ; request sai kiểu/thiếu dữ liệu bắt buộc; request cố thêm field nhạy cảm ngoài allowlist.
8. Nếu có session-based workflow, kiểm tra request tiếp theo có nhận đúng object hay không và session được làm sạch khi hoàn tất.

**Tự giải thích luồng bằng một câu hỏi:** với `POST /profiles/42` có `displayName=Lan`, instance `ProfileForm` đến từ đâu, constructor nào đã chạy (nếu có), ai cho phép gán `displayName`, và dữ liệu sai nằm trong `BindingResult` nào? Trả lời được cả bốn điểm là đã xác định đúng giai đoạn lựa chọn và khởi tạo target.

## Tài liệu tham khảo

- Spring Framework Reference — `@ModelAttribute` method arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — `@ModelAttribute` methods and Model initialization: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html
- Spring Framework Reference — MVC Data Binding and model design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — Core Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Reference — `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — `@SessionAttributes`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
