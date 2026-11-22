# Phân biệt kiểu nguyên thủy với kiểu bao khi dữ liệu bị thiếu

Khi Spring Framework nhận dữ liệu từ form, query parameter hoặc JSON, điều quan trọng không chỉ là **dữ liệu được chuyển sang kiểu Java nào**, mà còn là **ứng dụng có nhận biết được trường đó chưa được gửi hay không**. Hai khai báo nhìn rất giống nhau — `int quantity` và `Integer quantity`, `boolean enabled` và `Boolean enabled` — có thể dẫn đến quyết định nghiệp vụ khác nhau khi đầu vào thiếu trường.

Phạm vi bài này là **đối tượng đầu vào (input DTO/form)** trong Spring Data Binding và validation. Cần phân biệt ba tình huống: *không cung cấp trường*, *cung cấp giá trị thực (kể cả 0 hoặc false)* và *cung cấp null/chuỗi rỗng*. Cách xử lý chi tiết còn phụ thuộc đường nhận dữ liệu, cấu hình binder/converter và JSON deserializer.

## 1. Khác biệt nền tảng của Java

Kiểu nguyên thủy (primitive) là kiểu dữ liệu Java lưu trực tiếp một giá trị thuộc miền của nó; kiểu bao (wrapper) là kiểu tham chiếu, ngoài giá trị còn có khả năng mang `null`.

| Kiểu nguyên thủy | Kiểu bao | Giá trị mặc định của **trường instance** khi không khởi tạo | Ý nghĩa khi dùng làm input |
| --- | --- | --- | --- |
| `int` | `Integer` | `0` / `null` | `int` không biểu diễn được “chưa cung cấp”; `Integer` có thể là `null`. |
| `long` | `Long` | `0L` / `null` | Cùng vấn đề với số lượng, ID, hạn mức, thời gian tính bằng số. |
| `double` | `Double` | `0.0d` / `null` | Số 0 có thể là giá trị có nghĩa; wrapper giúp tách khỏi trường vắng mặt. |
| `boolean` | `Boolean` | `false` / `null` | `false` có thể là lựa chọn rõ ràng của người dùng, khác với “chưa chọn”. |
| `char` | `Character` | `'\u0000'` / `null` | Ký tự NUL mặc định không phải dấu hiệu đáng tin cho dữ liệu bị thiếu. |

Ví dụ với một JavaBean mới tạo, chưa có initializer và chưa được bind:

~~~java
class Input {
    int count;          // 0
    Integer countBox;   // null
    boolean confirmed;  // false
    Boolean confirmBox; // null
}
~~~

**Giá trị mặc định ở bảng là của trường instance/array element.** Biến cục bộ primitive không được Java tự gán mặc định để có thể sử dụng ngay; nó phải được gán trước khi đọc. Ngoài ra, trường đã được constructor, field initializer hoặc logic khác đặt giá trị sẽ giữ giá trị đó nếu binder không thay đổi nó. Vì vậy “thiếu dữ liệu” **không luôn đồng nghĩa** “trường primitive bằng 0”; 0 chỉ là giá trị mặc định của trường primitive trong đối tượng mới, không được khởi tạo rõ ràng.

### Vì sao `0` và `false` không thể đóng vai trò `null`?

Xét hai yêu cầu gửi đến một API tạo đơn:

- Request A **không gửi** thuộc tính `quantity`.
- Request B gửi rõ ràng `quantity=0`.

Nếu bind cả hai vào trường `int quantity` của JavaBean mới, cuối cùng cả hai đều có thể mang `0`. Chỉ nhìn `quantity` thì không còn biết người dùng đã gửi 0 hay chưa gửi gì. Với `Integer quantity`, trong trường hợp bind theo thuộc tính thông thường, A để lại `null` còn B mang `0`, nên việc kiểm tra bắt buộc nhập trở nên trực tiếp hơn.

Tương tự, nếu checkbox hoặc JSON gửi `false` thì đây có thể là lựa chọn hợp lệ. Trường `boolean` có giá trị `false` ngay cả khi chưa nhận dữ liệu; trong một biểu mẫu bắt buộc trả lời có/không, `Boolean` mới cho phép biểu diễn trạng thái chưa trả lời (`null`).

## 2. Spring bind thế nào khi trường không có trong dữ liệu nguồn?

Trong **setter/property binding** vào một JavaBean đã được tạo, `DataBinder` chỉ cập nhật các thuộc tính có giá trị đầu vào tương ứng. Một thuộc tính **không xuất hiện** trong tập giá trị bind thường **giữ nguyên trạng thái đang có**:

~~~text
Dữ liệu đầu vào không có "quantity"
                     |
                     v
            DataBinder / WebDataBinder
                     |
            Không gán thuộc tính đó
                     |
           +---------+---------+
           |                   |
    int quantity        Integer quantity
      (mới tạo)            (mới tạo)
           |                   |
           0                  null
~~~

Điều này khác với việc request **có trường** nhưng trường mang giá trị rỗng hoặc sai kiểu. Khi đó Spring có thể gọi converter, gán `null` cho wrapper, hoặc tạo lỗi `typeMismatch` cho primitive, tùy loại trường và cơ chế conversion. Không nên kết luận “mọi chuỗi rỗng đều thành 0” hay “mọi chuỗi rỗng đều thành null”.

Nếu JavaBean đã có `quantity = 5` trước khi bind thì request thiếu `quantity` có thể khiến nó vẫn bằng 5, kể cả khi kiểu là `Integer`. **Giá trị sau bind không phải bằng chứng duy nhất về sự hiện diện của field trong request.**

## 3. Chương trình Java 17+ minh họa với Spring `DataBinder`

Ví dụ chạy độc lập bên dưới sử dụng hai DTO có cùng tên thuộc tính nhưng khác kiểu. Các dữ liệu mẫu được đưa vào `MutablePropertyValues`, tương tự tập cặp tên/giá trị mà binder có thể nhận từ một form. Không có web server trong ví dụ.

Cấu trúc thư mục:

~~~text
primitive-wrapper-input/
├── pom.xml
└── src/main/java/example/PrimitiveWrapperInputDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>primitive-wrapper-input</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.PrimitiveWrapperInputDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/example/PrimitiveWrapperInputDemo.java`:

~~~java
package example;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PrimitiveWrapperInputDemo {

    public static class PrimitiveInput {
        private int quantity;
        private boolean enabled;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    public static class WrapperInput {
        private Integer quantity;
        private Boolean enabled;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }
    }

    private static <T> T bind(T target, Map<String, String> values) {
        DataBinder binder = new DataBinder(target);
        binder.bind(new MutablePropertyValues(values));
        BindingResult result = binder.getBindingResult();

        if (result.hasErrors()) {
            throw new IllegalStateException("Bind thất bại: " + result);
        }
        return target;
    }

    public static void main(String[] args) {
        var absentPrimitive = bind(new PrimitiveInput(), Map.of());
        var absentWrapper = bind(new WrapperInput(), Map.of());

        var explicitPrimitive = bind(
                new PrimitiveInput(),
                Map.of("quantity", "0", "enabled", "false"));
        var explicitWrapper = bind(
                new WrapperInput(),
                Map.of("quantity", "0", "enabled", "false"));

        var positiveWrapper = bind(
                new WrapperInput(),
                Map.of("quantity", "3", "enabled", "true"));

        System.out.println("primitive/absent: "
                + absentPrimitive.getQuantity() + ", "
                + absentPrimitive.isEnabled());
        System.out.println("wrapper/absent: "
                + absentWrapper.getQuantity() + ", "
                + absentWrapper.getEnabled());
        System.out.println("primitive/explicit: "
                + explicitPrimitive.getQuantity() + ", "
                + explicitPrimitive.isEnabled());
        System.out.println("wrapper/explicit: "
                + explicitWrapper.getQuantity() + ", "
                + explicitWrapper.getEnabled());
        System.out.println("wrapper/positive: "
                + positiveWrapper.getQuantity() + ", "
                + positiveWrapper.getEnabled());
    }
}
~~~

Với **JDK 17+**, Maven và quyền tải dependencies nếu chưa có cache, tại thư mục `primitive-wrapper-input` chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả in bởi chương trình:

~~~text
primitive/absent: 0, false
wrapper/absent: null, null
primitive/explicit: 0, false
wrapper/explicit: 0, false
wrapper/positive: 3, true
~~~

Hai dòng đầu minh họa **trường không được gửi**. Hai dòng tiếp theo minh họa **người dùng thực sự gửi 0 và false**. Kiểu nguyên thủy cho cùng một trạng thái sau bind ở hai kịch bản; kiểu bao tách được chúng khi field ban đầu là `null`. Dòng cuối cho thấy wrapper vẫn chứa giá trị bình thường khi có dữ liệu.

Ví dụ dùng Spring `DataBinder` với **property binding trên JavaBean mới**; không đại diện cho mọi hành vi của JSON deserialization, constructor binding, field initializer, custom editor hoặc form checkbox marker.

## 4. Phân biệt “không có”, “rỗng”, `null` và sai kiểu

Đây là điểm dễ gây bug nhất khi nối form/REST với DTO Java:

| Đầu vào thực tế | Ý nghĩa | Kết quả đáng quan tâm |
| --- | --- | --- |
| Không có khóa `quantity` trong tập giá trị bind | Field vắng mặt | Property binder thường không gán: primitive giữ giá trị sẵn có (mặc định `0` ở bean mới), wrapper giữ giá trị sẵn có (mặc định `null`). |
| Có `quantity=0` | Người dùng cung cấp số 0 | Cả `int` lẫn `Integer` có thể chứa `0` sau chuyển đổi thành công. |
| Có `enabled=false` | Người dùng chọn false | Cả `boolean` lẫn `Boolean` có thể chứa `false`; wrapper phân biệt với `null` trước đó. |
| Có `quantity=` (chuỗi rỗng từ form) | Có trường nhưng thiếu giá trị số | Wrapper số có thể được chuyển thành `null`; primitive có thể phát sinh lỗi bind/conversion. Phải kiểm tra `BindingResult`. |
| Có `quantity=abc` | Giá trị không đổi được thành số | Thường là lỗi chuyển kiểu; không sử dụng giá trị mặc định còn lại như thể input hợp lệ. |
| JSON gửi `"quantity": null` | Gửi `null` một cách tường minh | Wrapper nhận `null` theo cấu hình phổ biến; xử lý primitive phụ thuộc Jackson và cấu hình null coercion. |
| JSON không chứa `quantity` | Thuộc tính không xuất hiện | Với POJO setter binding thông thường, giữ mặc định của trường; constructor/record và custom deserializer có thể khác. |

### JSON với `@RequestBody`: thận trọng với primitive

`@RequestBody` thường đọc JSON qua Jackson trong Spring MVC. Với cách cấu hình Jackson phổ biến, JSON `null` vào một thuộc tính primitive của JavaBean có thể trở thành mặc định primitive (`0`, `false`). Tùy cấu hình, Jackson có thể từ chối việc này; ví dụ bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` sẽ từ chối **JSON null tường minh** cho primitive.

Không nên mặc định rằng chỉ cần bật tùy chọn trên thì JSON **thiếu hẳn khóa** cũng bị từ chối. Kiểm tra sự hiện diện của property, quy tắc constructor và các đặc điểm của deserializer có cơ chế riêng. Với bean có setter thông thường, property không có trong JSON thường không được gán.

Khi request JSON có cấu trúc sai hoặc kiểu không thể đọc, Spring có thể ném `HttpMessageNotReadableException` trước khi controller chạy. Trường hợp đó **không có nghĩa** là validation đã chạy và `BindingResult` đã báo lỗi.

### Form với `@ModelAttribute`: lưu ý checkbox

HTML thường **không gửi field checkbox khi checkbox không được chọn**. Nếu bind vào `boolean enabled` mới tạo, bạn có thể nhận `false` nhưng không biết liệu người dùng đã chủ động gửi false hay chưa. Một số cơ chế của Spring form binding thêm field marker (tiền tố mặc định `_`) để biểu thị checkbox có mặt trên form và hỗ trợ reset giá trị khi checkbox không được chọn. Field marker có thể khiến binder chủ động gán giá trị thay vì chỉ giữ nguyên trường vắng mặt.

Do đó, để phân biệt “chưa trả lời” với “trả lời không”, phải thiết kế cách truyền dữ liệu và quy tắc bắt buộc trả lời rõ ràng; **chỉ đổi `boolean` sang `Boolean` không đủ** nếu tầng HTML/client đã gộp mất hai trạng thái trước khi gửi.

### Query parameter khác với thuộc tính DTO

Với một tham số controller đơn lẻ:

~~~java
// Đoạn trích Spring MVC, không phải chương trình độc lập.
@GetMapping("/search")
public String search(
        @RequestParam(required = false) Integer page) {
    return page == null ? "not-specified" : "page-" + page;
}
~~~

`@RequestParam(required = false) Integer page` có thể nhận `null` khi tham số bị thiếu. Ngược lại, `@RequestParam int page` mặc định là bắt buộc: Spring có thể báo lỗi thiếu tham số **trước khi** thân phương thức được thực thi. Nếu luôn muốn dùng mặc định, khai báo rõ `@RequestParam(defaultValue = "1") int page`; giá trị mặc định được dùng khi tham số vắng mặt hoặc rỗng theo ngữ nghĩa của annotation.

Điều này không mâu thuẫn với mặc định `0` của trường `int` trong DTO: **cơ chế resolve tham số trực tiếp** và **cơ chế bind thuộc tính JavaBean** là hai đường xử lý khác nhau.

## 5. Bean Validation: làm sao bắt lỗi “chưa gửi”?

Đừng trông chờ `@NotNull` bắt trường primitive bị bỏ trống. Primitive luôn mang một giá trị sau khi đối tượng được tạo, nên ràng buộc `@NotNull` trên `int` hoặc `boolean` **không giúp phát hiện field vắng mặt**. Nếu người dùng phải cung cấp số lượng dương, cách khai báo rõ ý nghĩa thường là:

~~~java
// DTO minh họa; cần Jakarta Bean Validation + provider.
public class CreateOrderForm {
    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Positive
    private Integer quantity;

    @jakarta.validation.constraints.NotNull
    private Boolean newsletterEnabled;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Boolean getNewsletterEnabled() {
        return newsletterEnabled;
    }

    public void setNewsletterEnabled(Boolean newsletterEnabled) {
        this.newsletterEnabled = newsletterEnabled;
    }
}
~~~

Các quy tắc có tác dụng khác nhau:

- `@NotNull Integer quantity`: từ chối giá trị `null`, chẳng hạn thuộc tính vẫn `null` khi không được bind.
- `@Positive Integer quantity`: từ chối `0` và số âm; theo Bean Validation, `null` được xem là hợp lệ đối với riêng ràng buộc `@Positive`, nên cần kết hợp `@NotNull` nếu trường bắt buộc.
- `@NotNull Boolean newsletterEnabled`: buộc người dùng cung cấp giá trị true **hoặc false** khi cơ chế bind giữ được sự phân biệt field vắng mặt và field đã nhập.
- Nếu điều kiện nghiệp vụ bắt buộc **phải là true**, dùng `@AssertTrue`; nhưng annotation này cũng không tự từ chối `null`, nên thường cần thêm `@NotNull` khi muốn vừa bắt buộc gửi vừa bắt buộc chấp thuận.

Đặt `@NotNull` trên `boolean` không có tác dụng bắt buộc chọn. Đặt `@Min(1)` hoặc `@Positive` trên primitive `int` có thể bắt mặc định `0` là lỗi, nhưng vẫn **không phân biệt được** người dùng không gửi số với người dùng cố ý gửi `0`. Điều đó có thể đủ khi cả hai đều là input không hợp lệ; nó không phù hợp nếu cần báo lỗi hoặc áp dụng nghiệp vụ khác nhau cho hai trường hợp.

### Controller phải chặn nhánh không hợp lệ

~~~java
// Đoạn trích trong Spring MVC @Controller đã có orderService và view.
@PostMapping("/orders")
public String create(
        @Valid @ModelAttribute("order") CreateOrderForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "orders/new";
    }

    // Validation đã kiểm tra quantity và newsletterEnabled khác null.
    orderService.create(
            form.getQuantity(),
            form.getNewsletterEnabled());
    return "redirect:/orders";
}
~~~

Đối với Spring Boot 3.x, Bean Validation annotations ở namespace `jakarta.validation.*` và cần Bean Validation provider, thường được cung cấp bởi `spring-boot-starter-validation`. `@Valid` phải được kích hoạt tại điểm vào phù hợp; nếu chỉ tạo DTO Java mới mà không chạy validation thì annotations **không tự sinh lỗi**.

`BindingResult` phải đứng **ngay sau** tham số `@Valid @ModelAttribute` tương ứng. Trong trường hợp lỗi, nhánh `return` xảy ra trước `orderService.create(...)`. Khi sử dụng `@Valid @RequestBody`, việc validation và báo lỗi có chi tiết riêng; nếu không có tham số `BindingResult` liền kề, Spring MVC thường trả lỗi qua `MethodArgumentNotValidException` và cơ chế exception handling.

## 6. Chọn kiểu nào cho từng mục đích?

Không có quy tắc “DTO nào cũng bắt buộc dùng wrapper”. Kiểu phù hợp phụ thuộc vào việc **trạng thái chưa cung cấp** có ý nghĩa trong contract hay không.

| Mục đích của field | Kiểu thường phù hợp | Lý do |
| --- | --- | --- |
| Số lượng bắt buộc phải nhập, phải dương | `@NotNull @Positive Integer quantity` | Tách thiếu/`null` khỏi `0`, xác thực được cả hiện diện và giá trị. |
| Số lượng có thể bỏ trống, service quyết định mặc định | `Integer quantity` | `null` diễn đạt “không chỉ định”; `0` là giá trị được gửi rõ ràng. |
| Cờ bắt buộc chọn “Có/Không”, cả hai đều hợp lệ | `@NotNull Boolean enabled` | Có ba trạng thái trước validation: chưa chọn, true, false. |
| Cờ phải được đồng ý là true | `@NotNull @AssertTrue Boolean consent` | Buộc có câu trả lời và câu trả lời phải là true. |
| Trạng thái nội bộ đã có mặc định false, không cần biết người dùng có gửi không | `boolean active` | `false` là giá trị thực sự hợp lệ của mô hình. |
| Bộ đếm nội bộ luôn có giá trị số và không bao giờ vắng mặt | `int attempts` | Không cần wrapper chỉ để có khả năng `null` vô ích. |
| JSON PATCH: thiếu = giữ nguyên, `null` = xóa, giá trị = thay đổi | Kiểu biểu diễn **cả sự hiện diện và giá trị** | Chỉ `Integer`/`Boolean` không thể biểu diễn đủ ba trạng thái. |

### Trường hợp cập nhật từng phần (PATCH)

Đây là tình huống mà wrapper **cũng chưa đủ**. Xét hai JSON:

~~~json
{}
~~~

và:

~~~json
{"nickname": null}
~~~

Nếu cả hai được deserialize vào cùng DTO có trường `String nickname` mặc định `null` thì đọc `nickname == null` không biết người gọi muốn **không đổi nickname** hay **xóa nickname**. Với `Integer age`, `Boolean enabled` cũng tương tự.

Để hỗ trợ đúng contract PATCH, cần theo dõi riêng **field có xuất hiện hay không**. Các cách gồm đọc một `JsonNode` và dùng `has("nickname")` (khác với `hasNonNull(...)`), dùng kiểu trạng thái chuyên cho patch, hoặc cơ chế deserializer có đánh dấu sự hiện diện. Sau đó nghiệp vụ phải phân nhánh rõ:

~~~text
Không có field   -> Giữ nguyên dữ liệu đang có
Có field = null  -> Xóa/reset nếu contract cho phép
Có field = value -> Kiểm tra và cập nhật giá trị
~~~

Không dùng `null` của wrapper để tùy tiện suy ra cả hai hành động đầu tiên. Đối với PUT/create, thiếu trường có thể bị từ chối; đối với PATCH, thiếu trường thường mang nghĩa giữ nguyên theo contract, nên validate cũng phải bám sát thao tác.

## 7. Các lỗi thường gặp

**Lỗi 1 — Xem `0` là dấu hiệu thiếu dữ liệu.**

~~~java
int quantity = form.getQuantity();
if (quantity == 0) {
    // Không thể biết người dùng bỏ trống hay đã gửi đúng số 0.
}
~~~

Nếu `0` là giá trị hợp lệ, việc suy ra “chưa nhập” sẽ từ chối nhầm dữ liệu. Nếu `0` không hợp lệ, `@Positive` có thể chặn cả hai, nhưng nguyên nhân chính xác vẫn không phân biệt được với primitive.

**Lỗi 2 — Dùng `@NotNull` trên primitive để bắt buộc nhập.**

~~~java
@NotNull
private int quantity; // annotation này không phát hiện field vắng mặt
~~~

Cách sửa thường là `@NotNull Integer quantity` kèm ràng buộc giá trị phù hợp. Đừng đổi kiểu mà quên cập nhật getter/setter, mapper và các điểm unboxing.

**Lỗi 3 — Unboxing wrapper trước khi validation chạy.**

~~~java
Integer quantity = form.getQuantity();
int units = quantity; // NullPointerException nếu quantity == null
~~~

Chỉ chuyển sang primitive khi đã xác minh giá trị khác `null`, ví dụ sau validation thành công hoặc sau khi áp dụng default rõ ràng:

~~~java
int units = quantity == null ? 1 : quantity;
~~~

Dòng cuối chỉ đúng nếu **contract cho phép mặc định bằng 1**; không được âm thầm thay giá trị bắt buộc phải nhập.

**Lỗi 4 — Định nghĩa giá trị mặc định tại field rồi vẫn mong phát hiện thiếu.**

~~~java
private Integer quantity = 0; // Thiếu field vẫn cho quantity == 0.
~~~

Wrapper không tự bảo toàn dấu hiệu thiếu khi ứng dụng đã khởi tạo nó. Nếu cần bắt buộc người dùng gửi, đừng tự đặt giá trị khiến `@NotNull` luôn vượt qua.

**Lỗi 5 — Bỏ qua lỗi conversion và tiếp tục nghiệp vụ.**

Chuỗi `"abc"` không thể đổi thành `Integer`, hoặc chuỗi rỗng không thể đổi thành primitive tùy converter. Ngay cả khi thuộc tính đích vẫn mang mặc định, binder có thể đã ghi `FieldError`. Phải kiểm tra `BindingResult.hasErrors()` trước khi gọi service.

**Lỗi 6 — Cho rằng JSON null, field vắng mặt và chuỗi rỗng luôn giống nhau.**

Các kiểu đầu vào đi qua đường chuyển đổi khác nhau. Hãy kiểm thử riêng `{}`, `{"quantity":null}`, `{"quantity":0}` và dạng form `quantity=`. Khi thêm custom converter, field marker, constructor binding hoặc đổi cấu hình Jackson, cần kiểm thử lại.

**Lỗi 7 — Áp dụng một DTO tạo mới cho cập nhật từng phần.**

Một wrapper `null` có thể là “chưa nhập” trong create nhưng là “xóa” hoặc “không đổi” trong patch. Dùng DTO/contract theo từng use case; bảo toàn trạng thái field có mặt.

## 8. Kiểm thử hành vi đầu vào, không chỉ kiểu Java

Tối thiểu nên kiểm thử các trường hợp dưới đây tại chính điểm vào đang dùng (`DataBinder`, `@ModelAttribute`, `@RequestParam` hoặc `@RequestBody`), vì chúng không có cùng đường bind:

| Ca kiểm thử | Với đầu vào bắt buộc `Integer quantity` | Với đầu vào bắt buộc `Boolean enabled` |
| --- | --- | --- |
| Bỏ hẳn trường | Báo lỗi bắt buộc nếu dùng `@NotNull` và không có initializer/default | Báo lỗi bắt buộc nếu dùng `@NotNull` và có thể bảo toàn trạng thái vắng mặt |
| Gửi `null` thực sự (JSON) | Báo lỗi bắt buộc hoặc lỗi đọc request theo cấu hình | Báo lỗi bắt buộc hoặc lỗi đọc request theo cấu hình |
| Gửi `0` / `false` | `0` bị từ chối nếu dùng `@Positive`, không bị từ chối chỉ bởi `@NotNull` | `false` hợp lệ nếu chỉ cần người dùng chọn Có/Không |
| Gửi `1` / `true` | Hợp lệ về các ràng buộc `@NotNull @Positive` | Hợp lệ về `@NotNull` |
| Gửi chuỗi rỗng / sai kiểu | Kiểm tra conversion error và thông điệp thực tế | Kiểm tra conversion/field marker theo đường nhận dữ liệu |

Ở mức controller, kiểm tra cả **HTTP status/response field error** lẫn việc **service không được gọi khi input không hợp lệ**. Với create bắt buộc có `quantity`, cần một test chứng minh request không chứa `quantity` không tạo được đơn; không chỉ test `quantity = -1`. Với PATCH, cần kiểm tra phân biệt vắng mặt và null bằng kết quả trên dữ liệu đang lưu.

## 9. Quy tắc thực hành cần nhớ

1. Khi cần biểu diễn **chưa cung cấp**, ưu tiên wrapper như `Integer`, `Long`, `Boolean` trong input DTO, và không khởi tạo mặc định nếu muốn dùng `null` để báo thiếu.
2. Khi bắt buộc có dữ liệu, dùng validation thực sự: `@NotNull` để kiểm tra hiện diện ở mức giá trị, kết hợp `@Positive`/`@Min` hoặc `@AssertTrue` khi cần kiểm tra nội dung. Luôn chạy validation và đọc kết quả trước nghiệp vụ.
3. Không dùng `0` hoặc `false` làm dấu hiệu thiếu nếu đó có thể là lựa chọn hợp lệ.
4. Phân biệt **thuộc tính không có**, **giá trị rỗng**, **JSON null** và **conversion error** theo đường nhận request đang triển khai. Không suy rộng từ một kiểu binding cho mọi kiểu khác.
5. Đối với **PATCH ba trạng thái**, hãy theo dõi sự hiện diện của field riêng biệt; wrapper một mình không đủ.
6. Chỉ dùng primitive ở ranh giới input khi contract thực sự cho phép mặc định tự nhiên, hoặc khi cơ chế resolve/validate đã bảo đảm không cần phân biệt đầu vào vắng mặt.

Tài liệu tham khảo Spring và Jakarta để đối chiếu trong triển khai:

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — `@ModelAttribute` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — `@RequestParam` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — `@RequestBody` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Jakarta Validation — Built-in Constraint Definitions](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#builtinconstraints)
