# hasErrors, hasFieldErrors, getFieldErrors và getGlobalErrors trong Spring

## 1. Bối cảnh: một đối tượng có thể có nhiều loại lỗi

Khi Spring nhận form, chuyển kiểu và kiểm tra dữ liệu, kết quả không chỉ là “đúng” hoặc “sai”. Một đối tượng đầu vào có thể chứa:

- **Lỗi thuộc tính (field error):** liên quan đến một thuộc tính cụ thể, ví dụ **email** rỗng, **quantity** nhỏ hơn 1 hoặc chuỗi **"abc"** không thể chuyển thành **Integer**.
- **Lỗi toàn đối tượng (global/object error):** liên quan đến quy tắc áp dụng cho cả đối tượng, thường cần phối hợp nhiều thuộc tính, ví dụ **startDay** lớn hơn **endDay**. Lỗi này không nhất thiết được gắn riêng vào một trường.
- **Cả hai cùng lúc:** một form vừa thiếu tên vừa có khoảng thời gian không hợp lệ.

Spring cung cấp giao diện **org.springframework.validation.Errors** để ghi và truy vấn những lỗi đó. **BindingResult** kế thừa **Errors**, bổ sung thông tin liên quan quá trình data binding. Trong Spring MVC, một đối số **BindingResult** đặt đúng vị trí cho phép controller xử lý kết quả bind và validation của một model attribute.

Bốn phương thức trọng tâm của bài:

1. **hasErrors()** — có *bất kỳ* lỗi nào không?
2. **hasFieldErrors()** / **hasFieldErrors(String field)** — có lỗi thuộc tính nào không, hoặc thuộc tính cụ thể có lỗi không?
3. **getFieldErrors()** / **getFieldErrors(String field)** — lấy danh sách lỗi thuộc tính.
4. **getGlobalErrors()** — lấy danh sách lỗi toàn đối tượng.

Các phương thức này **chỉ đọc những lỗi đã được ghi nhận trên đối tượng Errors hiện tại**. Chúng không tự chạy converter, tự kiểm tra annotation, truy vấn lỗi ở nơi khác hay tự sửa dữ liệu.

## 2. Bảng đối chiếu chính xác bốn phương thức

| API | Kiểu trả về | Phạm vi được xét | Sử dụng khi |
| --- | --- | --- | --- |
| **hasErrors()** | boolean | Mọi lỗi (field **và** global) | Quyết định có nên tiếp tục xử lý hay hiển thị form lỗi |
| **hasFieldErrors()** | boolean | Mọi lỗi của các field | Kiểm tra có ít nhất một thuộc tính sai |
| **hasFieldErrors("email")** | boolean | Lỗi trên field **email** | Hiển thị trạng thái lỗi cạnh một ô nhập |
| **getFieldErrors()** | List<FieldError> | Tất cả lỗi field, trên mọi thuộc tính | Dựng danh sách lỗi chi tiết theo từng trường |
| **getFieldErrors("email")** | List<FieldError> | Những lỗi được gắn với field **email** | Hiển thị nhiều thông báo của cùng một trường |
| **getGlobalErrors()** | List<ObjectError> | Chỉ lỗi toàn đối tượng | Hiển thị thông báo về quy tắc liên trường hoặc toàn form |

**Điều cốt lõi:** **hasErrors() == true** không kéo theo **hasFieldErrors() == true**. Chỉ cần một lỗi toàn đối tượng đã đủ để **hasErrors()** trả **true**.

**getFieldErrors()** và **getGlobalErrors()** luôn là các nhóm độc lập về phạm vi: **getFieldErrors()** không bao gồm lỗi global; **getGlobalErrors()** không trả các **FieldError** đã được ghi như lỗi của một field.

Nếu cần API bổ trợ, **hasGlobalErrors()** kiểm tra có lỗi global, **getGlobalError()** lấy lỗi global đầu tiên (hoặc null), **getFieldError("email")** lấy lỗi đầu tiên của field (hoặc null), **getAllErrors()** trả cả hai nhóm dưới dạng **List<ObjectError>**, và **getErrorCount()** đếm tất cả lỗi.

### Bảng chân trị với các tổ hợp lỗi

| Trạng thái của Errors | hasErrors() | hasFieldErrors() | getFieldErrors().size() | getGlobalErrors().size() |
| --- | --- | --- | --- | --- |
| Không có lỗi | false | false | 0 | 0 |
| Chỉ 2 lỗi field | true | true | 2 | 0 |
| Chỉ 1 lỗi global | true | false | 0 | 1 |
| 2 lỗi field + 1 lỗi global | true | true | 2 | 1 |

Số lượng trong bảng là ví dụ; một field có thể có nhiều **FieldError** và một đối tượng có thể có nhiều **ObjectError**. Không được mặc định mỗi field chỉ có một lỗi.

## 3. Lỗi field và lỗi global hình thành như thế nào?

**Errors.rejectValue(field, code, message)** ghi nhận một lỗi gắn với tên thuộc tính. Ví dụ:

~~~java
errors.rejectValue("customerName", "required", "Customer name is required");
errors.rejectValue("quantity", "positive", "Quantity must be positive");
~~~

**Errors.reject(code, message)** ghi nhận một lỗi cấp đối tượng, chẳng hạn:

~~~java
errors.reject("date.order", "Start day must not exceed end day");
~~~

Đây là các câu lệnh minh họa bên trong một **Validator** hoặc đoạn code đã có đối tượng **Errors**; chúng không phải chương trình độc lập. **code** là mã lỗi dùng trong cơ chế phân giải thông báo (MessageSource/MessageCodesResolver), còn **message** là thông báo mặc định. Khi đọc lỗi qua **getCode()**, có thể gặp mã đã được mở rộng thêm tên object/field, vì vậy không nên xây dựng API chỉ dựa vào giả định rằng **getCode()** luôn đúng nguyên văn mã ngắn được truyền vào **rejectValue**.

**Lỗi binding:** khi DataBinder không thể gán giá trị thô vào kiểu Java (ví dụ **age=abc** với thuộc tính **Integer age**), **BindingResult** cũng có thể chứa một **FieldError** có mã thường gặp là **typeMismatch** và **isBindingFailure() == true**. Đây là lỗi của thuộc tính, nên được **hasFieldErrors()** và **getFieldErrors()** tính đến dù nó chưa phải lỗi Bean Validation.

**Lỗi Bean Validation:** các ràng buộc như **@NotBlank**, **@Min**, **@NotNull** (khi validator được kích hoạt) thường tạo lỗi field nếu gắn với thuộc tính. Ràng buộc ở cấp class có thể tạo lỗi global nếu đường dẫn vi phạm thuộc cấp đối tượng; custom validator cũng có thể chọn **rejectValue** để gắn lỗi về một trường cụ thể. Vì thế hãy xem **lỗi thực tế được ghi ở đâu**, không suy luận máy móc từ tên annotation.

Về kiểu Java:

- **FieldError** kế thừa **ObjectError** và bổ sung **getField()**, **getRejectedValue()**, **isBindingFailure()**.
- **ObjectError** biểu diễn lỗi cấp đối tượng và có **getObjectName()**, **getCode()**, **getCodes()**, **getDefaultMessage()**.
- **Errors** và **BindingResult** biểu diễn lỗi của **một đối tượng đích đã chọn**, không phải bộ tổng hợp mọi lỗi của toàn bộ request hay toàn ứng dụng.

## 4. Ví dụ Java 17+ có thể chạy: ba trạng thái lỗi

Ví dụ sau dùng **Spring Framework 6.2.18** và Java 17+. Nó tạo ba đối tượng đặt hàng, gọi validator theo cơ chế **DataBinder**, rồi dùng cả bốn API để phân biệt lỗi thuộc tính và lỗi toàn đối tượng.

Cấu trúc thư mục:

~~~text
errors-methods-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ErrorsMethodsDemo.java
~~~

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>errors-methods-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                    <mainClass>demo.ErrorsMethodsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo file **src/main/java/demo/ErrorsMethodsDemo.java**:

~~~java
package demo;

import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.Validator;

public final class ErrorsMethodsDemo {

    public static void main(String[] args) {
        show("MIXED", new OrderForm(" ", 0, 9, 7));
        show("GLOBAL_ONLY", new OrderForm("Mai", 2, 9, 7));
        show("VALID", new OrderForm("Mai", 2, 5, 7));
    }

    private static void show(String title, OrderForm form) {
        DataBinder binder = new DataBinder(form, "orderForm");
        binder.setValidator(new OrderValidator());
        binder.validate();

        // BindingResult kế thừa Errors: các phương thức cần học
        // đều có thể được gọi thông qua giao diện Errors.
        Errors errors = binder.getBindingResult();

        System.out.println("[" + title + "]");
        System.out.println("hasErrors=" + errors.hasErrors());
        System.out.println("hasFieldErrors=" + errors.hasFieldErrors());
        System.out.println("hasFieldErrors(customerName)="
                + errors.hasFieldErrors("customerName"));
        System.out.println("hasFieldErrors(startDay)="
                + errors.hasFieldErrors("startDay"));
        System.out.println("getFieldErrors().size="
                + errors.getFieldErrors().size());
        System.out.println("getFieldErrors(customerName).size="
                + errors.getFieldErrors("customerName").size());
        System.out.println("getGlobalErrors().size="
                + errors.getGlobalErrors().size());

        for (FieldError error : errors.getFieldErrors()) {
            System.out.println("FIELD " + error.getField()
                    + ": " + error.getDefaultMessage());
        }
        for (ObjectError error : errors.getGlobalErrors()) {
            System.out.println("GLOBAL: " + error.getDefaultMessage());
        }
    }

    public static final class OrderForm {
        private String customerName;
        private Integer quantity;
        private int startDay;
        private int endDay;

        public OrderForm(String customerName, Integer quantity,
                         int startDay, int endDay) {
            this.customerName = customerName;
            this.quantity = quantity;
            this.startDay = startDay;
            this.endDay = endDay;
        }

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public int getStartDay() {
            return startDay;
        }

        public void setStartDay(int startDay) {
            this.startDay = startDay;
        }

        public int getEndDay() {
            return endDay;
        }

        public void setEndDay(int endDay) {
            this.endDay = endDay;
        }
    }

    private static final class OrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return OrderForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderForm form = (OrderForm) target;

            if (form.getCustomerName() == null
                    || form.getCustomerName().isBlank()) {
                errors.rejectValue("customerName", "required",
                        "Customer name is required");
            }

            if (form.getQuantity() == null
                    || form.getQuantity() < 1) {
                errors.rejectValue("quantity", "positive",
                        "Quantity must be positive");
            }

            if (form.getStartDay() > form.getEndDay()) {
                errors.reject("date.order",
                        "Start day must not exceed end day");
            }
        }
    }
}
~~~

Ở thư mục chứa **pom.xml**, chạy (cần Maven và JDK 17+, và quyền tải dependencies ở lần chạy đầu):

~~~bash
mvn -q compile exec:java
~~~

Kết quả mong đợi, **không tính log của Maven nếu môi trường bật thêm logging**:

~~~text
[MIXED]
hasErrors=true
hasFieldErrors=true
hasFieldErrors(customerName)=true
hasFieldErrors(startDay)=false
getFieldErrors().size=2
getFieldErrors(customerName).size=1
getGlobalErrors().size=1
FIELD customerName: Customer name is required
FIELD quantity: Quantity must be positive
GLOBAL: Start day must not exceed end day
[GLOBAL_ONLY]
hasErrors=true
hasFieldErrors=false
hasFieldErrors(customerName)=false
hasFieldErrors(startDay)=false
getFieldErrors().size=0
getFieldErrors(customerName).size=0
getGlobalErrors().size=1
GLOBAL: Start day must not exceed end day
[VALID]
hasErrors=false
hasFieldErrors=false
hasFieldErrors(customerName)=false
hasFieldErrors(startDay)=false
getFieldErrors().size=0
getFieldErrors(customerName).size=0
getGlobalErrors().size=0
~~~

**Giải thích từng trạng thái:**

- **MIXED:** **customerName** trống và **quantity** bằng 0 tạo hai **FieldError** qua **rejectValue**. **startDay=9, endDay=7** vi phạm quan hệ giữa hai trường, tạo một **ObjectError** qua **reject**. Vì thế **hasErrors()** và **hasFieldErrors()** đều true, danh sách field có 2 phần tử và danh sách global có 1 phần tử.
- **GLOBAL_ONLY:** tên và số lượng hợp lệ, nhưng khoảng ngày vẫn sai. **hasErrors()** true dù **hasFieldErrors()** false. Điều này giải thích vì sao chỉ kiểm tra **hasFieldErrors()** sẽ bỏ sót lỗi cần hiển thị.
- **VALID:** không có lỗi ở bất kỳ nhóm nào. Mọi phép đếm bằng 0 và các phép kiểm tra đều false.
- Trong **MIXED**, **hasFieldErrors("startDay")** là false mặc dù ngày bắt đầu góp phần gây lỗi. Lý do: validator dùng **reject(...)** cho quy tắc liên trường, nên lỗi nằm ở nhóm **global**, không phải **FieldError** của startDay.

Bài mẫu chủ động chạy **binder.validate()**. Nó không dùng HTTP hoặc binding giá trị từ chuỗi, vì trọng tâm là các API đọc lỗi; khi ứng dụng thật nhận request, lỗi chuyển kiểu có thể được ghi nhận thêm trong cùng **BindingResult**.

## 5. Áp dụng vào Spring MVC

Trong controller Spring MVC nhận form, dùng **BindingResult** ngay sau tham số **@ModelAttribute** đang được validate:

~~~java
// Đoạn nằm trong @Controller/@RestController của một ứng dụng Spring MVC;
// cần OrderRequest, @Valid và các import phù hợp.
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("orderRequest") OrderRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        // Có thể là FieldError, ObjectError hoặc cả hai.
        for (FieldError fieldError : result.getFieldErrors()) {
            String field = fieldError.getField();
            String message = fieldError.getDefaultMessage();
            // Chuyển thành thông báo phù hợp cho đúng trường.
        }

        for (ObjectError globalError : result.getGlobalErrors()) {
            String message = globalError.getDefaultMessage();
            // Hiển thị ở phần thông báo chung của form.
        }

        return "orders/form";
    }

    return "orders/success";
}
~~~

Đây là **đoạn minh họa tích hợp**, chưa phải một controller hoàn chỉnh để biên dịch độc lập: cần khai báo lớp **OrderRequest**, view tương ứng, import, validator và ràng buộc liên trường nếu muốn thực sự sinh lỗi global. **@Valid** kích hoạt Bean Validation trong ngữ cảnh hỗ trợ; nó không tự tạo ra lỗi toàn đối tượng chỉ vì dữ liệu có nhiều trường.

Một mẫu điều kiện thường gặp:

~~~java
if (result.hasErrors()) {
    if (result.hasFieldErrors("email")) {
        // Hiển thị lỗi tại ô email.
    }
    if (!result.getGlobalErrors().isEmpty()) {
        // Hiển thị lỗi chung cho cả form.
    }
    return "form";
}
~~~

Tại sao **hasErrors()** nên là phép kiểm tra bao ngoài? Vì nhánh chỉ có lỗi global vẫn phải ngăn quy trình xử lý tiếp tục. Một ứng dụng cần bổ sung phân loại mã lỗi, bản địa hóa, xử lý ngữ cảnh và kiểm soát thông tin hiển thị, thay vì đưa thẳng mọi message nội bộ ra API.

**Lưu ý thứ tự tham số:** trong Spring MVC, một **Errors/BindingResult** nhận lỗi của tham số model cần đứng **ngay sau** tham số đó. Nếu đặt không đúng chỗ hoặc không khai báo, Spring có thể xử lý/đẩy lỗi theo cơ chế ngoại lệ thay vì cho controller tự đọc như trên. Không lấy nhầm **BindingResult** của đối tượng A để quyết định đối tượng B có lỗi.

## 6. Đọc và trình bày danh sách lỗi đúng cách

### 6.1. getFieldErrors() khác getFieldErrors("field")

**getFieldErrors()** lấy tất cả lỗi field trên đối tượng hiện tại. Một trường có thể xuất hiện nhiều lần nếu nó có nhiều ràng buộc thất bại; không coi kích thước danh sách là số lượng trường bị lỗi.

**getFieldErrors("email")** chỉ lấy lỗi được gắn cho field **email**. Nếu không có lỗi tương ứng, danh sách rỗng; vì vậy có thể duyệt danh sách an toàn mà không cần kiểm tra null. Trên các triển khai chuẩn của Spring, có thể hỗ trợ tên field lồng nhau hoặc mẫu ghép trường, nhưng khi hiển thị một ô nhập cụ thể nên ưu tiên tên thuộc tính đã biết như **address.street**.

Ví dụ nếu có 3 **FieldError** nhưng phân bố là email có 2 lỗi và age có 1 lỗi:

~~~text
getFieldErrors().size()          = 3
getFieldErrors("email").size()   = 2
getFieldErrors("age").size()     = 1
hasFieldErrors("phone")          = false
~~~

Con số này là minh họa giả định, không phải kết quả bổ sung của chương trình ở phần 4.

Nếu chỉ muốn lỗi đầu tiên trên một trường để giữ UI gọn, dùng **getFieldError("email")**, nhưng phải xử lý khả năng trả **null**. Dùng **getFieldErrors("email")** khi muốn cho người dùng xem toàn bộ vi phạm có liên quan đến trường đó.

### 6.2. getGlobalErrors() dùng cho thông báo ở cấp form

Một lỗi toàn đối tượng có thể đến từ quy tắc liên trường như “ngày kết thúc phải sau ngày bắt đầu”, “ít nhất một phương thức liên hệ phải được cung cấp”, hoặc lỗi được ghi bằng **Errors.reject(...)**.

**getGlobalErrors()** trả về **List<ObjectError>** và không chuyển những lỗi này thành **FieldError** một cách tự động. Nếu yêu cầu trải nghiệm người dùng cần tô đỏ cả hai ô ngày, code giao diện cần một quy tắc ánh xạ hợp lệ từ mã lỗi toàn đối tượng đến các trường liên quan, hoặc validator cần ghi lỗi field cụ thể bằng **rejectValue**. Đừng giả định **hasFieldErrors("startDay")** sẽ true khi chỉ có lỗi global.

Để kết hợp danh sách lỗi chung, **getAllErrors()** trả danh sách chứa cả **ObjectError** và **FieldError**. Khi cần hai vùng hiển thị riêng, vẫn nên dùng trực tiếp **getFieldErrors()** và **getGlobalErrors()**.

### 6.3. Kết hợp với BindingResult của lỗi chuyển đổi kiểu

Khi một form gửi **quantity=abc** nhưng Java property là **Integer quantity**, binder có thể ghi **FieldError** do **typeMismatch**. Ví dụ:

~~~java
for (FieldError error : bindingResult.getFieldErrors("quantity")) {
    if (error.isBindingFailure()) {
        // Giá trị gửi tới chưa chuyển/gán được đúng kiểu.
    } else {
        // Lỗi ràng buộc/validation trên field, tùy nguồn lỗi.
    }
}
~~~

Đây là đoạn minh họa trong môi trường đã có **BindingResult**, không phải chương trình chạy độc lập. **hasFieldErrors("quantity")** vẫn true cho trường hợp typeMismatch; phương thức này **không phân biệt nguyên nhân** của field error. Nếu cần phân biệt lỗi chuyển kiểu với lỗi Bean Validation, kiểm tra **FieldError.isBindingFailure()**, mã lỗi, hoặc loại ngoại lệ đúng giai đoạn.

Đối với **@RequestBody** JSON, nếu converter không giải tuần tự được JSON thành đối tượng thì controller có thể chưa nhận được một **BindingResult** như trong form; lỗi đọc body thường đi theo **HttpMessageNotReadableException**. Vì vậy bốn phương thức trên chỉ có ý nghĩa **khi đã có Errors/BindingResult tương ứng**; chúng không thay thế việc bắt lỗi giải tuần tự.

## 7. Cách thiết kế API/UI trả lỗi có cấu trúc

Một response hữu ích có thể tách lỗi trường và lỗi toàn đối tượng. Ví dụ ý tưởng JSON cho trường hợp MIXED:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customerName",
      "message": "Tên khách hàng không được để trống."
    },
    {
      "field": "quantity",
      "message": "Số lượng phải lớn hơn 0."
    }
  ],
  "globalErrors": [
    {
      "message": "Ngày bắt đầu không được sau ngày kết thúc."
    }
  ]
}
~~~

Đây là **đề xuất hợp đồng phản hồi**, không phải JSON Spring mặc định trả về và không phải kết quả của chương trình console. Khi triển khai:

1. Chỉ gọi nghiệp vụ ghi dữ liệu khi **!result.hasErrors()** và các kiểm tra cần thiết khác đã thành công.
2. Phân phối **getFieldErrors()** theo tên field để UI đặt thông báo cạnh điều khiển nhập phù hợp.
3. Hiển thị **getGlobalErrors()** ở vùng thông báo cấp form, hoặc ánh xạ mã lỗi liên trường ra UI nếu sản phẩm có quy ước rõ ràng.
4. Dùng mã lỗi ổn định và cơ chế **MessageSource** cho bản địa hóa nếu ứng dụng phục vụ nhiều ngôn ngữ.
5. Không phản hồi nguyên trạng **getRejectedValue()** đối với mật khẩu, token, thông tin nhạy cảm; không mặc định mọi **getDefaultMessage()** đều an toàn để hiển thị cho khách.
6. Không dựa vào thứ tự phần tử như một cam kết nghiệp vụ. Nếu ưu tiên thông báo cần cố định, hãy định nghĩa rõ thứ tự ở lớp trình bày.

Nếu chỉ kiểm tra **hasFieldErrors()** rồi trả thành công, hệ thống có thể chấp nhận trường hợp **GLOBAL_ONLY** trong ví dụ, dù yêu cầu “ngày bắt đầu không được lớn hơn ngày kết thúc” đang bị vi phạm.

## 8. Kiểm thử theo nhóm lỗi

Với validator và controller thật, nên kiểm tra các trạng thái sau:

| Trường hợp | hasErrors() | hasFieldErrors() | getFieldErrors() | getGlobalErrors() |
| --- | --- | --- | --- | --- |
| Tất cả trường hợp lệ, quy tắc liên trường hợp lệ | false | false | Rỗng | Rỗng |
| Chỉ customerName rỗng | true | true | Có lỗi customerName | Rỗng |
| Chỉ quantity không hợp lệ | true | true | Có lỗi quantity | Rỗng |
| Chỉ startDay > endDay và validator dùng reject(...) | true | false | Rỗng | Có lỗi quan hệ ngày |
| Vừa thiếu customerName vừa sai khoảng ngày | true | true | Có lỗi customerName | Có lỗi quan hệ ngày |
| quantity không thể chuyển kiểu từ chuỗi | true nếu binder ghi lỗi | true nếu binder ghi lỗi field | Có thể có FieldError typeMismatch | Tùy lỗi khác |

Cần kiểm tra thêm rằng **getFieldErrors("customerName")** không chứa lỗi quantity, và **hasFieldErrors("startDay")** có thể false khi vi phạm ngày chỉ được ghi ở cấp global. Khi dùng **@Valid** với Spring MVC, kiểm tra rằng **BindingResult** đặt ngay sau đúng đối số và validator có thực sự chạy. Nếu có custom validator cấp đối tượng, cần kích hoạt nó bằng cấu hình phù hợp; Spring không tự tạo lỗi global cho mọi phép so sánh liên trường.

## 9. Những nhầm lẫn phổ biến

**Nhầm 1: hasErrors() và hasFieldErrors() tương đương.** Sai: một lỗi global làm **hasErrors()** true nhưng **hasFieldErrors()** có thể false.

**Nhầm 2: getFieldErrors() lấy mọi lỗi.** Sai: danh sách này chỉ có **FieldError**. Nếu cần mọi lỗi, dùng **getAllErrors()**; nếu cần lỗi toàn đối tượng, dùng **getGlobalErrors()**.

**Nhầm 3: lỗi liên trường luôn hiển thị như lỗi của từng field.** Sai: điều đó phụ thuộc validator ghi lỗi bằng **reject(...)** hay **rejectValue(...)**, hoặc cách constraint cung cấp đường dẫn lỗi.

**Nhầm 4: hasFieldErrors("name") trả về thông báo.** Sai: đây là boolean. Dùng **getFieldErrors("name")** để duyệt thông tin **FieldError** hoặc **getFieldError("name")** cho lỗi đầu tiên.

**Nhầm 5: getFieldErrors().size() là số trường bị sai.** Sai: một trường có thể tạo nhiều **FieldError**.

**Nhầm 6: chỉ có lỗi @Valid mới xuất hiện trong BindingResult.** Sai: lỗi binding/chuyển kiểu cũng có thể được ghi vào đó và xuất hiện trong danh sách field errors.

**Nhầm 7: dùng getGlobalErrors() làm nơi chứa mọi ngoại lệ HTTP.** Sai: **Errors** là thông tin lỗi liên quan đối tượng đích. Lỗi đọc JSON, không tìm thấy endpoint hoặc lỗi hạ tầng có đường xử lý khác.

**Nhầm 8: dùng getDefaultMessage() không cần kiểm tra.** Sai: thông báo có thể không được cung cấp hoặc chứa chi tiết không nên đưa ra ngoài. Nên chuẩn hóa mã/thông báo tại lớp trình bày API.

## 10. Câu hỏi tự kiểm tra

1. Form có một lỗi **reject("date.order", "...")**, không có **rejectValue**: **hasErrors()** và **hasFieldErrors()** trả gì? **getGlobalErrors().size()** là bao nhiêu?
2. Một field có ba constraint cùng thất bại: **getFieldErrors("field").size()** có bắt buộc bằng 1 không?
3. Nếu controller chỉ dùng **if (result.hasFieldErrors()) return "form"**, trường hợp lỗi nào có thể lọt qua?
4. Muốn hiển thị toàn bộ lỗi của field **email**, nên dùng **hasFieldErrors("email")** hay **getFieldErrors("email")**?
5. Với form có **age=abc** nhưng Java khai báo **Integer age**, tại sao **getFieldErrors("age")** có thể chứa lỗi ngay cả trước khi ràng buộc **@Min** được xét?
6. Khi lỗi là quy tắc liên quan hai trường, cần làm gì để UI biết những ô nào phải được đánh dấu?

**Đáp án hướng dẫn:** (1) **true**, **false**, **1**; (2) không, có thể nhiều lỗi; (3) chỉ có lỗi global; (4) **getFieldErrors("email")**; (5) binder ghi **typeMismatch** dưới dạng field error; (6) ánh xạ lỗi global theo quy ước UI hoặc ghi thêm lỗi field phù hợp.

## 11. Tham khảo API Spring chính thức

- [Errors — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/Errors.html).
- [BindingResult — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/BindingResult.html).
- [FieldError — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/FieldError.html).
- [ObjectError — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/ObjectError.html).
- [Validation, Data Binding and Type Conversion — Spring Reference](https://docs.spring.io/spring-framework/reference/core/validation.html).
- [Spring MVC @ModelAttribute — Spring Reference](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).

**Quy tắc chốt:** dùng **hasErrors()** để quyết định có lỗi bất kỳ, **hasFieldErrors(...)** để kiểm tra lỗi thuộc tính, **getFieldErrors(...)** để lấy chi tiết lỗi từng trường, và **getGlobalErrors()** để giữ nguyên những lỗi thuộc toàn đối tượng. Luôn phân biệt dữ liệu lỗi đã được ghi trên **Errors** với việc chính framework có chạy binding/validation thành công hay chưa.