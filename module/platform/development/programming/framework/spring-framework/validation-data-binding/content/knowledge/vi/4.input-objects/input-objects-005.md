# Phân biệt không có trường, null, chuỗi rỗng và chuỗi trắng trong Spring Validation & Data Binding

## 1. Vì sao phải phân biệt bốn trạng thái?

Khi nhận dữ liệu đầu vào, cùng một thuộc tính `displayName` có thể rơi vào bốn tình huống khác nhau:

1. **Không có trường (absent/missing)**: dữ liệu đầu vào **không hề khai báo khóa** `displayName`. Ví dụ JSON `{}`.
2. **Có trường và giá trị null (explicit null)**: khóa tồn tại nhưng giá trị của nó là JSON `null` hoặc Java `null`. Ví dụ `{"displayName": null}`.
3. **Có trường và chuỗi rỗng (empty string)**: giá trị thực sự là chuỗi có độ dài bằng 0, `""`.
4. **Có trường và chuỗi trắng (blank/whitespace-only string)**: chuỗi có ít nhất một ký tự nhưng toàn ký tự được xem là khoảng trắng theo quy tắc đang áp dụng, ví dụ `"   "` hoặc chuỗi chứa tab.

Cả bốn trường hợp đều có thể không phù hợp với một trường bắt buộc, nhưng **chúng không có cùng ý nghĩa đối với binding, cập nhật dữ liệu, mặc định hóa, kiểm lỗi và API contract**. Nếu gộp chúng quá sớm, hệ thống có thể không còn biết người dùng bỏ qua trường, chủ động yêu cầu xóa giá trị, hay đã nhập một giá trị không hợp lệ.

Ví dụ: ở API cập nhật một phần hồ sơ, dữ liệu `{}` có thể có nghĩa “giữ nguyên tên”; `{"displayName": null}` có thể có nghĩa “xóa tên”; `{"displayName": ""}` có thể là yêu cầu đặt tên thành chuỗi rỗng (thường cần từ chối); `{"displayName": "   "}` là đầu vào chỉ có khoảng trắng (thường cũng cần từ chối). Đây là **quy tắc do API định nghĩa**, không phải cách Spring tự động diễn giải mọi PATCH.

### Bảng nhận diện tại nguồn

| Dữ liệu đầu vào | Khóa có hiện diện? | Giá trị Java/JSON tại nguồn | Phân loại |
| --- | --- | --- | --- |
| `{}` | Không | Không có giá trị để đọc | `ABSENT` |
| `{"displayName": null}` | Có | `null` | `NULL` |
| `{"displayName": ""}` | Có | `""` (length = 0) | `EMPTY` |
| `{"displayName": "   "}` | Có | Chuỗi 3 dấu cách | `BLANK` |
| `{"displayName": "\t"}` | Có | Chuỗi chứa ký tự tab sau khi parse JSON | `BLANK` |
| `{"displayName": " Linh "}` | Có | Chuỗi chứa chữ và dấu cách | `VALUE` |
| `{"displayName": 123}` | Có | Giá trị kiểu số | **Sai kiểu mong đợi**, không được tùy tiện gọi là chuỗi rỗng |

Các trạng thái `EMPTY` và `BLANK` trong bảng được đặt **loại trừ nhau**: `EMPTY` là `length == 0`; `BLANK` ở đây nghĩa là **không rỗng và chỉ chứa whitespace**. Trong Java, `"".isBlank()` cũng trả về `true`, vì vậy cần kiểm tra `isEmpty()` trước nếu muốn chia thành bốn trạng thái riêng.

## 2. Ở Java: null, empty và blank là những phép kiểm khác nhau

Với `String value`:

- `value == null`: biến tham chiếu không trỏ tới đối tượng `String`; không được gọi `value.isEmpty()` hoặc `value.isBlank()` trước khi kiểm tra null.
- `value.isEmpty()`: đúng khi `value.length() == 0`, chỉ phản ánh độ dài.
- `value.isBlank()` (Java 11+): đúng khi chuỗi rỗng **hoặc** tất cả code point của chuỗi được xem là whitespace theo `Character.isWhitespace`.
- `value.trim().isEmpty()`: phụ thuộc quy tắc `String.trim()` (loại bỏ ký tự đầu/cuối có mã ≤ U+0020), không đồng nhất với `String.isBlank()` cho mọi Unicode.
- `value.strip().isEmpty()`: dùng quy tắc whitespace dựa trên `Character.isWhitespace` tương tự `isBlank()`; không nên giả định mọi ký tự có vẻ như “khoảng trắng” trong mọi ngôn ngữ đều được Java phân loại như nhau.

**Đặc biệt:** Ký tự non-breaking space `U+00A0` có thể nhìn giống một dấu cách nhưng `Character.isWhitespace` trong Java không xem nó như dấu cách thông thường. Khi xử lý dữ liệu đa ngôn ngữ, cần xác định quy tắc Unicode của sản phẩm và kiểm thử các ký tự cụ thể. Không thay thế quy tắc nghiệp vụ bằng một phép `trim` tùy tiện.

### Ví dụ Java 17+ hoàn chỉnh: giữ riêng sự hiện diện của khóa

Tạo tệp `PresenceDemo.java`:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PresenceDemo {

    static String classify(Map<String, String> input, String key) {
        if (!input.containsKey(key)) {
            return "ABSENT";
        }

        String value = input.get(key);

        if (value == null) {
            return "NULL";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "VALUE";
    }

    public static void main(String[] args) {
        Map<String, String> input = new HashMap<>();
        input.put("explicitNull", null);
        input.put("empty", "");
        input.put("whitespace", " \t ");
        input.put("withText", " Linh ");

        for (String key : List.of(
                "missing", "explicitNull", "empty", "whitespace", "withText")) {
            System.out.println(key + " => " + classify(input, key));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PresenceDemo.java
java PresenceDemo
~~~

Stdout chính xác:

~~~text
missing => ABSENT
explicitNull => NULL
empty => EMPTY
whitespace => BLANK
withText => VALUE
~~~

Điểm mấu chốt là **`Map.get("missing") == null` và `Map.get("explicitNull") == null` đều đúng**. Chỉ `containsKey(...)` mới phân biệt được “không có khóa” với “có khóa chứa null”. Dùng `Map.of(...)` để tạo map có giá trị null cũng không phù hợp vì các factory `Map.of` không chấp nhận null; ví dụ cố ý sử dụng `HashMap`.

Hàm `classify` biểu diễn trạng thái của **dữ liệu nguồn** khi nguồn còn giữ thông tin hiện diện. Một thuộc tính `String` đơn lẻ trên JavaBean chỉ có thể mang giá trị `null` hoặc một chuỗi; tự nó không thể diễn đạt được “trường đã xuất hiện trong yêu cầu hay chưa”.

## 3. HTTP form/query và JSON khác nhau ngay từ cách biểu diễn

### 3.1. Query string và HTML form

Với tham số `nickname` trong một ứng dụng web:

| Request | Quan sát ở dữ liệu tham số | Có biểu diễn JSON null trực tiếp không? |
| --- | --- | --- |
| `GET /profile` | Không có tham số `nickname` | Không |
| `GET /profile?nickname=` | Có `nickname`, giá trị chuỗi rỗng | Không |
| `GET /profile?nickname` | Thông thường được parser HTTP thể hiện thành giá trị rỗng; không nên dựa vào việc thiếu dấu `=` để đại diện null | Không |
| `GET /profile?nickname=%20%20` | Có tham số, giá trị hai dấu cách sau URL decode | Không |
| `GET /profile?nickname=null` | Có tham số, giá trị là chuỗi bốn chữ `"null"` | Không |

Trong `application/x-www-form-urlencoded`, phía gửi thao tác với chuỗi và cặp key-value. Từ `null` mà Java hiểu không phải là giá trị wire format tiêu chuẩn cho trường form. Nếu frontend bỏ thuộc tính khỏi biểu mẫu, đó là **missing**; nếu gửi `nickname=`, đó là **empty**. Với checkbox không được chọn, trình duyệt có thể không gửi tên trường; giá trị mặc định của một form control phụ thuộc HTML và mã frontend.

Spring MVC có thể bind form/query bằng `@RequestParam` hoặc `@ModelAttribute`. Đừng nhầm `required = true` của `@RequestParam` với `@NotBlank`: `required` chủ yếu kiểm việc có tham số, còn `@NotBlank` kiểm nội dung chuỗi qua validation. Chuyển kiểu cũng có thể khiến giá trị rỗng trở thành null cho một số kiểu đích, ảnh hưởng cách Spring đánh giá “missing after conversion”.

Ví dụ:

~~~java
@GetMapping("/search")
String search(
        @RequestParam(name = "term", required = false) String term) {
    return term == null ? "NO_VALUE" : "TEXT[" + term + "]";
}
~~~

Đây là **mảnh code đặt trong Spring MVC controller**, cần các import từ `org.springframework.web.bind.annotation` và ứng dụng Spring Web. Nó minh họa một tham số String tùy chọn; **không** bảo đảm giữ được mọi chi tiết về sự hiện diện của nguồn sau các converter/editor được cấu hình. Nếu cần phân biệt chính xác, hãy đọc cả danh sách tham số ở boundary, ví dụ `@RequestParam MultiValueMap<String, String> params` rồi dùng `params.containsKey("term")`, trước khi gộp thành một String.

`@RequestParam(defaultValue = "guest")` dùng giá trị mặc định khi tham số **không được gửi hoặc có giá trị rỗng**, vì vậy có thể cố ý gộp missing và empty. `required = false`/`Optional<String>` làm tham số không bắt buộc, nhưng không thay thế được cơ chế lưu lại trạng thái “field có xuất hiện” cho mọi kiểu dữ liệu. Nếu API cần phân biệt, đừng trông chờ `defaultValue` hoặc `Optional` giữ đủ bốn trạng thái.

### 3.2. JSON có null riêng biệt

JSON phân biệt một member không xuất hiện với member xuất hiện có literal `null`. HTTP body:

~~~json
{}
~~~

và:

~~~json
{"nickname": null}
~~~

là hai document khác nhau. Tương tự:

~~~json
{"nickname": ""}
~~~

khác với:

~~~json
{"nickname": " \t "}
~~~

Ở ví dụ cuối, `\t` được escape hợp lệ trong JSON; sau parse, chuỗi chứa dấu cách và tab.

Trong Spring MVC, `@RequestBody` được `HttpMessageConverter` (thường qua Jackson) đọc và chuyển thành Java object. Nếu đích là DTO:

~~~java
public class ProfileRequest {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

thì với cấu hình Jackson thông thường, nếu `nickname` ban đầu là null, cả hai body `{}` và `{"nickname": null}` có thể dẫn đến `request.getNickname() == null`. Tại thời điểm này, thông tin **member có hiện diện không** đã mất. Nếu property có giá trị khởi tạo khác null hoặc Jackson được cấu hình khác (constructor, null-handling, setter), kết quả có thể khác; không quy mọi DTO thành một luật cố định.

**Cần phân biệt cả “không có body” với “body JSON là `{}`”**: `@RequestBody(required = true)` kiểm sự có mặt của body, không đồng nghĩa với việc mọi member trong JSON object đều bắt buộc.

### 3.3. Giữ nguyên bốn trạng thái bằng JsonNode tại boundary

Khi semantics của PATCH hoặc API yêu cầu tách missing khỏi explicit null, có thể đọc JSON dạng cây. Ví dụ **mảnh controller Spring MVC**, cần Spring Web cùng Jackson và các import tương ứng:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class InputStateController {

    @PostMapping("/input-state")
    String inputState(@RequestBody JsonNode body) {
        if (body == null || !body.isObject()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Expected JSON object");
        }

        if (!body.has("nickname")) {
            return "ABSENT";
        }

        JsonNode node = body.get("nickname");
        if (node.isNull()) {
            return "NULL";
        }
        if (!node.isTextual()) {
            return "WRONG_TYPE";
        }

        String text = node.textValue();
        if (text.isEmpty()) {
            return "EMPTY";
        }
        return text.isBlank() ? "BLANK" : "VALUE";
    }
}
~~~

Kết quả trả về của method đối với từng JSON object:

| Body | Chuỗi trả về |
| --- | --- |
| `{}` | `ABSENT` |
| `{"nickname": null}` | `NULL` |
| `{"nickname": ""}` | `EMPTY` |
| `{"nickname": " \t "}` | `BLANK` |
| `{"nickname": "Linh"}` | `VALUE` |
| `{"nickname": 7}` | `WRONG_TYPE` |

Dùng `body.has("nickname")` để kiểm presence, `node.isNull()` để nhận biết JSON null và `node.isTextual()` để tránh âm thầm biến số/boolean/object thành chuỗi. Với Jackson tree, `body.path("nickname")` trả node dạng missing khi không có member, trong khi `get("nickname")` trả Java null khi không có member; `NullNode` đại diện explicit JSON null. Không dùng `node.asText()` để phân biệt trước khi kiểm kiểu, vì conversion có thể làm mất ý nghĩa ban đầu.

Ví dụ dùng nguyên tên thuộc tính `nickname` trong controller, test và hợp đồng API để trạng thái không bị nhầm do đổi alias.

## 4. Khi dữ liệu đi qua DataBinder, trạng thái có thể thay đổi

Spring `DataBinder` hỗ trợ constructor binding và property binding. Trong trường hợp property binding của một mutable JavaBean:

- **Không có field trong nguồn**: binder không nhận thao tác gán cho property đó; giá trị hiện tại của object thường được giữ nguyên.
- **Có field với chuỗi rỗng**: nếu property kiểu `String` và chưa đăng ký custom editor/converter thay thế, chuỗi `""` thường được gán như một String rỗng.
- **Có field toàn khoảng trắng**: vẫn là một String có nội dung, trừ khi có quy tắc làm sạch/chuyển đổi.
- **Có field với Java null**: nguồn như `MutablePropertyValues` có thể chứa null; đối tượng đích nhận null tùy kiểu property và cấu hình binding. Điều này khác cơ chế form HTML.
- **Có lỗi chuyển kiểu**: ví dụ `age=abc` khi đích là số nguyên, binder có thể ghi `FieldError` với mã lỗi kiểu `typeMismatch`; đây không phải một trong bốn trạng thái hợp lệ của String.

Cẩn thận với DTO có mặc định:

~~~java
class DisplayForm {
    private String nickname = "Anonymous";

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

Nếu binder chỉ bind các property xuất hiện trong dữ liệu nguồn, một property `nickname` bị bỏ qua sẽ giữ `"Anonymous"`. Nếu nguồn chứa `nickname=""`, setter có thể nhận `""` và ghi đè giá trị mặc định. Nếu giá trị rỗng được custom editor biến thành null, setter có thể nhận null. **Cần quan sát cấu hình binder và giá trị trước/sau binding**, không suy đoán chỉ từ kiểu `String`.

### StringTrimmerEditor thay đổi semantics ra sao?

Spring cung cấp `StringTrimmerEditor`, nhưng **không tự động đăng ký cho mọi field String**. Ví dụ đăng ký theo controller:

~~~java
@InitBinder
void registerTrimming(WebDataBinder binder) {
    binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
}
~~~

Đây là mảnh code trong Spring MVC controller, cần `@InitBinder`, `WebDataBinder` và `org.springframework.beans.propertyeditors.StringTrimmerEditor`. Tham số `true` yêu cầu chuyển chuỗi rỗng **sau khi trim** thành null.

Với editor này, tùy dữ liệu đầu vào:

| Giá trị trước custom editor | Giá trị String sau editor |
| --- | --- |
| `""` | `null` |
| `"   "` | `null` |
| `"  Linh  "` | `"Linh"` |
| `"Linh"` | `"Linh"` |

Vì có biến đổi, validator nhận dữ liệu **sau binding** có thể không còn xác định được lỗi ban đầu là `EMPTY` hay `BLANK`. Editor cũng **không tự đánh dấu một field vắng mặt thành explicit null**, và không phải cơ chế mặc định của deserialization `@RequestBody` JSON. `StringTrimmerEditor` có quy tắc trim riêng; đừng suy luận nó đồng nhất với mọi định nghĩa Unicode whitespace trong validation.

Không đăng ký trim toàn cục nếu hệ thống phải giữ nguyên khoảng trắng có ý nghĩa (chẳng hạn dữ liệu mã hóa/ký số, văn bản cần giữ định dạng hay bí mật người dùng). Hãy quyết định theo từng nhóm field hoặc use case, và nếu cần báo lỗi chính xác cho raw input, kiểm tra/ghi nhận sự hiện diện trước khi chuẩn hóa.

## 5. Jakarta Bean Validation kiểm tra giá trị, không tự lưu presence

Đây là phần thường gây nhầm lẫn nhất khi dùng Spring Validation. Các constraint chạy trên **giá trị Java mà validator nhìn thấy**, không biết một property trong JSON từng được gửi hay bị bỏ qua nếu thông tin đó không được giữ lại.

Với thuộc tính kiểu `String`, hành vi của các annotation chuẩn cơ bản:

| Constraint | `null` | `""` | `"   "` | `"Linh"` | Mục đích |
| --- | --- | --- | --- | --- | --- |
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ | Hợp lệ | Bắt buộc có **giá trị khác null** |
| `@NotEmpty` | Không hợp lệ | Không hợp lệ | Hợp lệ | Hợp lệ | Khác null và độ dài lớn hơn 0 |
| `@NotBlank` | Không hợp lệ | Không hợp lệ | Không hợp lệ | Hợp lệ | Chuỗi có ít nhất một ký tự không phải whitespace |
| `@Size(min = 1)` | Hợp lệ | Không hợp lệ | Hợp lệ | Hợp lệ | Kiểm độ dài khi giá trị khác null |
| `@Pattern(regexp = "...")` | Thường hợp lệ với null theo constraint chuẩn | Tùy biểu thức | Tùy biểu thức | Tùy biểu thức | Kiểm pattern khi có chuỗi |

Trong bảng, “hợp lệ” chỉ xét **một constraint đang nêu** và điều kiện giá trị phù hợp; những constraint khác vẫn có thể không hợp lệ. Với `@NotBlank`, định nghĩa “blank” của Bean Validation/provider và các quy tắc Unicode cụ thể cần được kiểm thử theo provider/version đang dùng; đừng mặc định chuẩn hóa chuỗi bằng `String.trim()` sẽ mô phỏng mọi trường hợp.

Ví dụ DTO cho yêu cầu tạo mới (một phần class Java):

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName
) {}
~~~

Khi ứng dụng Spring đã tích hợp Bean Validation provider, ví dụ Hibernate Validator:

~~~java
@PostMapping("/profiles")
void create(@Valid @RequestBody CreateProfileRequest request) {
    // Chỉ tiếp tục khi request đã vượt qua ràng buộc đầu vào.
}
~~~

Đoạn controller là mảnh code, cần các import Web MVC và `jakarta.validation.Valid`. Nếu Jackson ánh xạ `{}` và `{"displayName":null}` cùng thành `displayName == null`, `@NotBlank` sẽ từ chối cả hai, nhưng **không cho biết nguyên nhân là missing hay explicit null**. `@NotBlank` cũng từ chối `""` và chuỗi chỉ whitespace. Nếu API chỉ cần thông báo “tên không được để trống”, gộp các lỗi này có thể chấp nhận. Nếu API cần thông báo riêng cho missing/null hoặc semantics PATCH, cần giữ thông tin presence từ nguồn.

**Quan trọng về kích hoạt validation:** annotation như `@NotBlank` chỉ là khai báo; Bean Validation cần một provider và điểm kích hoạt như `@Valid @RequestBody` / `@Validated` trong luồng Spring phù hợp hoặc lời gọi `jakarta.validation.Validator.validate(...)`. Tự gọi `new CreateProfileRequest(null)` **không tự động ném lỗi**. `@Nullable` là chỉ dẫn nullability, không phải lệnh validate nội dung; `Optional<String>` không tự giải quyết phân biệt missing với explicit null.

### Các trạng thái và message có thể cần khác nhau

Với yêu cầu tạo mới, contract có thể định nghĩa:

| Trạng thái nguồn | Chính sách ví dụ | Thông báo ví dụ |
| --- | --- | --- |
| `ABSENT` | Từ chối | `displayName is required` |
| `NULL` | Từ chối | `displayName must not be null` |
| `EMPTY` | Từ chối | `displayName must not be empty` |
| `BLANK` | Từ chối | `displayName must contain text` |
| `VALUE` | Kiểm tra thêm giới hạn độ dài, ký tự hợp lệ, quy tắc miền | Chấp nhận hoặc trả lỗi tương ứng |

Đây là **ví dụ chính sách API**, không phải thông điệp mặc định bắt buộc của Jakarta Validator hay Spring. Hệ thống có thể chọn một mã lỗi chung cho những trường không hợp lệ, miễn là hợp đồng rõ ràng và nhất quán.

## 6. Tạo mới, thay thế toàn bộ và cập nhật một phần

Bốn trạng thái đặc biệt quan trọng khi endpoint thay đổi dữ liệu.

### 6.1. POST tạo mới

Thông thường, một trường bắt buộc phải có giá trị thực. Có thể dùng `@NotBlank`/`@NotNull` trên DTO; với trường tùy chọn, có thể áp dụng mặc định do sản phẩm quy định. Nếu cần phân biệt khách hàng “bỏ qua” với “chủ động gửi null” để thống kê, audit hoặc thông báo, phải đọc raw JSON/tree/presence trước khi DTO làm mất khác biệt.

### 6.2. PUT thay thế

PUT thường mang kỳ vọng thay thế trạng thái biểu diễn của resource theo contract. Cần quy định rõ field thiếu trong một representation đầy đủ được xem là lỗi, đặt mặc định hay bỏ qua. Không suy luận `null` và `absent` sẽ tương đương chỉ vì DTO sau Jackson cùng nhận null. Riêng id và các field máy chủ quản lý không nên cho client thay đổi qua binding.

### 6.3. PATCH cập nhật một phần

Đối với một contract PATCH do ứng dụng định nghĩa, có thể chọn:

| Trạng thái đầu vào | Hành động minh họa |
| --- | --- |
| `ABSENT` | Giữ nguyên giá trị hiện có |
| `NULL` | Xóa giá trị, nếu trường cho phép xóa |
| `EMPTY` | Từ chối hoặc chấp nhận đặt chuỗi rỗng theo contract |
| `BLANK` | Từ chối hoặc chuẩn hóa theo quy tắc field |
| `VALUE` | Kiểm tra và cập nhật giá trị mới |

Cách dùng `Map.containsKey` để giữ hai trạng thái đầu tiên:

~~~java
// Minh họa logic trong service/adapter sau khi parse JSON thành Map.
if (patch.containsKey("displayName")) {
    Object raw = patch.get("displayName");

    if (raw == null) {
        profile.clearDisplayName(); // Chỉ khi hợp đồng cho phép xóa.
    } else if (raw instanceof String text && !text.isBlank()) {
        profile.setDisplayName(text);
    } else {
        throw new IllegalArgumentException("Invalid displayName");
    }
}
~~~

Mảnh code này phụ thuộc contract của `profile` và biến `patch`, không phải một chương trình độc lập. Nhờ `containsKey`, nhánh không có khóa không chạm đến giá trị cũ. Đừng dùng `patch.getOrDefault("displayName", null)` nếu cần phân biệt missing với explicit null vì hai đường cùng cho null.

Nếu API dùng **JSON Merge Patch (RFC 7396)**, một member vắng mặt có nghĩa không thay đổi, còn `null` có ý nghĩa xóa member theo chuẩn merge patch. Nếu API dùng JSON Patch (RFC 6902), yêu cầu được biểu diễn bằng danh sách thao tác như `add`, `replace`, `remove`, nên semantics khác. Không tự gọi mọi endpoint HTTP PATCH là JSON Merge Patch; hãy khai báo Content-Type và quy tắc cập nhật rõ ràng.

**Không nên dùng trực tiếp entity làm PATCH DTO**: một entity với property nullable có thể không còn phân biệt “không gửi” và “gửi null”, gây xóa dữ liệu ngoài ý muốn hoặc cập nhật các thuộc tính client không được quyền ghi. Tách payload, validate những field có mặt, rồi map sang domain với danh sách field cho phép.

## 7. Quy trình kiểm tra đúng thứ tự

Đối với một field từ JSON hoặc nguồn dạng map, trình tự có thể là:

~~~text
Đọc dữ liệu nguồn
    |
    +-- key không tồn tại ---------> ABSENT (chọn giữ nguyên / lỗi thiếu)
    |
    +-- key tồn tại
           |
           +-- null --------------> NULL (xóa / lỗi null)
           |
           +-- sai kiểu ----------> TYPE ERROR
           |
           +-- String
                 |
                 +-- length == 0 --> EMPTY
                 |
                 +-- chỉ whitespace -> BLANK
                 |
                 +-- có ký tự khác whitespace -> VALUE
                       |
                       +-- kiểm độ dài, pattern, domain rule
~~~

Một chính sách xử lý tốt thường thực hiện tuần tự:

1. **Giữ presence ở ranh giới nhập:** dùng `JsonNode.has(...)`, `Map.containsKey(...)` hoặc lớp đại diện ba trạng thái (missing / explicit null / value). Đừng xóa presence trước khi xác định semantics.
2. **Kiểm kiểu dữ liệu:** phân biệt JSON number/boolean/object với String; không tự động biến mọi kiểu thành văn bản nếu API không yêu cầu.
3. **Quyết định có chuẩn hóa không:** trim, Unicode normalization, đổi chữ hoa/thường phải là hành vi có chủ đích cho từng field, không phải một phương thuốc chung.
4. **Áp constraint phù hợp:** `@NotBlank` với trường bắt buộc có chữ; `@NotEmpty` khi chấp nhận whitespace nhưng không chấp nhận độ dài 0; `@NotNull` khi giá trị có thể là chuỗi rỗng hợp lệ.
5. **Áp quy tắc nghiệp vụ trong service/domain:** ví dụ tên hiển thị duy nhất, quyền sửa hồ sơ, trạng thái được phép cập nhật. Constraint tại controller không thay thế các bất biến này.
6. **Trả lỗi theo contract:** phần xử lý HTTP (Spring MVC, WebFlux) đổi lỗi thành response; consumer/CLI có thể trả kết quả riêng. Trong bản ghi audit, cân nhắc không lưu raw secret hay dữ liệu nhạy cảm.

Nếu đã dùng `@Valid @RequestBody`, lỗi constraint trên object có thể thành `MethodArgumentNotValidException`. Nếu method validation áp dụng vì constraint trực tiếp trên method parameter, có thể là `HandlerMethodValidationException` (Spring MVC hiện đại). Với form/model attribute, `BindingResult` có thể chứa cả lỗi binding và validation. Lỗi malformed JSON hoặc sai kiểu khi deserialization có thể xảy ra **trước** khi Bean Validation được gọi. Vì vậy không gán mọi lỗi đầu vào thành “lỗi @NotBlank”.

## 8. Kiểm thử bốn trạng thái ở ranh giới API

Kiểm thử một field không chỉ bằng “hợp lệ” và “không hợp lệ”. Dùng tối thiểu các dữ liệu sau, theo định nghĩa API:

| Ca kiểm thử | JSON body | Kỳ vọng khi giữ raw presence |
| --- | --- | --- |
| T1 | `{}` | `ABSENT` |
| T2 | `{"displayName": null}` | `NULL` |
| T3 | `{"displayName": ""}` | `EMPTY` |
| T4 | `{"displayName": "   "}` | `BLANK` |
| T5 | `{"displayName": "\t"}` | `BLANK` |
| T6 | `{"displayName": "  An  "}` | `VALUE`, quyết định trim theo contract |
| T7 | `{"displayName": 5}` | `TYPE ERROR` nếu contract chỉ chấp nhận String |
| T8 | `{"displayName": false}` | `TYPE ERROR` |
| T9 | `{"displayName": []}` | `TYPE ERROR` |
| T10 | `{"displayName": "\u00a0"}` | Kiểm Unicode theo quy tắc whitespace thực tế đã chọn |

T10 có non-breaking space thông qua JSON escape. Một test nên chứng minh chính sách Unicode của ứng dụng thay vì tự động mặc định nó giống dấu cách thường.

Với form, kiểm thử thêm `?displayName=`, `?displayName=%20%20` và thiếu hoàn toàn tham số; nếu sử dụng `@RequestParam(defaultValue=...)` hãy xác nhận hai ca missing và empty cùng kích hoạt default như thiết kế. Với `StringTrimmerEditor(true)`, thử string rỗng và whitespace để xác nhận thời điểm chúng trở thành null. Với PATCH, kiểm thử hai request liên tiếp: không gửi field phải giữ giá trị hiện có, còn gửi null xử lý theo quyền xóa giá trị đã được công bố.

Kiểm cả **đầu vào chưa normalize**, **giá trị sau binding/deserialization** và **kết quả validation**. Chỉ kiểm DTO cuối cùng không đủ để xác nhận rằng API giữ được sự khác biệt giữa absent và explicit null.

## 9. Những lỗi triển khai thường gặp

1. **Dùng `value == null` để kết luận key vắng mặt.** Đối với map/tree, cần kiểm `containsKey`/`has` trước. Một key có mặt nhưng chứa null không tương đương với key không tồn tại.
2. **Gọi `isEmpty()` khi value có thể null.** Tránh `NullPointerException` bằng cách xử lý null trước, sau đó mới xét độ dài/whitespace.
3. **Dùng `isBlank()` rồi gọi chuỗi rỗng là “blank” trong mọi thông báo.** Theo Java, `"".isBlank() == true`, nhưng để chia rõ bốn trường hợp nên ưu tiên `isEmpty()` trước `isBlank()`.
4. **Nhầm `@NotNull` với `@NotBlank`.** `@NotNull` cho phép `""` và `"   "`. `@NotEmpty` cho phép `"   "`. Với trường bắt buộc có chữ thường chọn `@NotBlank`.
5. **Dùng `@Size(min=1)` thay cho required.** Constraint này có thể cho qua null; muốn từ chối null phải phối hợp thêm constraint tương ứng.
6. **Mặc định rằng JSON null và missing luôn được giữ lại trong DTO.** Với bean String nullable, hai trạng thái thường cùng trở thành Java null. Muốn giữ sự khác biệt, thiết kế đại diện presence ngay lúc parse.
7. **Bật `StringTrimmerEditor(true)` rồi muốn phản hồi chính xác empty hay whitespace từ DTO đã bind.** Thông tin đã biến đổi; cần kiểm trước normalization nếu loại lỗi quan trọng.
8. **Xem chuỗi `"null"`, `"undefined"` hoặc `"N/A"` là Java null.** Đây là chuỗi ký tự bình thường, chỉ có nghĩa đặc biệt nếu contract quy định.
9. **Dùng `@RequestParam(defaultValue=...)` khi cần giữ nguyên presence.** Giá trị mặc định được dùng cho missing hoặc empty, nên hai trạng thái có thể bị gộp.
10. **Trộn các loại PATCH.** JSON Merge Patch có semantics explicit null cụ thể; JSON Patch dùng thao tác rõ ràng; một endpoint PATCH tự định nghĩa không tự nhiên có cùng luật.
11. **Chuẩn hóa toàn cục mà không xét nghiệp vụ.** Khoảng trắng ở đầu/cuối có thể là dữ liệu có ý nghĩa; tên, mật khẩu, mã và văn bản không mặc nhiên dùng cùng một quy tắc.
12. **Không kiểm sai kiểu.** JSON number, boolean, array/object không phải “chuỗi rỗng”. Trả lỗi đúng kiểu thay vì cố biến thành String có thể che lấp lỗi của client.

## 10. Ghi nhớ khi thiết kế một đối tượng đầu vào

- **Presence là thông tin của cấu trúc nguồn**: phải có một cờ hiện diện/JSON tree/map hoặc wrapper thể hiện nó nếu ứng dụng cần phân biệt.
- **Null là một giá trị**: Java null và JSON null có ý nghĩa riêng, nhưng sau binding DTO có thể không biết null xuất hiện tường minh hay là mặc định do trường bị thiếu.
- **Empty nói về độ dài**: chuỗi `""` có độ dài 0; không tự động là null.
- **Blank nói về nội dung**: chuỗi có thể dài hơn 0 nhưng chỉ có whitespace; cách xác định whitespace phụ thuộc API/quy tắc Unicode được chọn.
- **Validation kiểm giá trị sau chuyển đổi**: `@NotNull`, `@NotEmpty` và `@NotBlank` giải quyết các yêu cầu khác nhau, không tự giải quyết sự hiện diện của field.
- **Binding và chuẩn hóa có thể làm mất thông tin**: xác định semantics trước khi đặt default value, trim, map sang DTO hoặc entity.
- **Hợp đồng cập nhật quyết định hành vi**: đặc biệt khi PATCH cần phân biệt không gửi field và chủ động gửi null.

## Tài liệu chuẩn để tra cứu

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — StringTrimmerEditor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html)
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
