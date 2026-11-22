# Kế thừa constraint từ lớp cha và interface trong Bean Validation

## 1. Bài toán: lớp con có còn bị ràng buộc bởi lớp cha không?

Trong ứng dụng Spring Framework, các lớp DTO, entity và service thường được tổ chức theo hệ thống kế thừa Java. Một lớp con có thể kế thừa thuộc tính của lớp cha, cài đặt interface, ghi đè getter hoặc override phương thức service. Vấn đề là **những annotation validation đặt ở lớp cha hoặc interface có còn hiệu lực khi kiểm tra đối tượng lớp con hay không?**

**Có** đối với các ràng buộc bean phù hợp: Jakarta Bean Validation xét các constraint được khai báo trên field, getter và class của **superclass** và **interface** trong hệ thống kiểu khi gọi `Validator.validate(subclassInstance)`. Ràng buộc ở lớp con được cộng thêm; chúng không mặc nhiên xóa các constraint kế thừa. Các vị trí có `@Valid` trong cây đối tượng cũng có thể được thừa hưởng và dùng để cascade.

Nhưng **method validation** có quy định nghiêm ngặt hơn. Khi ghi đè hoặc triển khai một phương thức:

- Không được **tăng điều kiện tiên quyết cho tham số** (`precondition`) trong subtype: theo chuẩn, subtype không được tự thêm hoặc khai báo lại constraint trên tham số của phương thức đã override/implement, kể cả `@Valid` trên tham số.
- Có thể **bổ sung constraint trên giá trị trả về** (`postcondition`) ở subtype, nhưng vẫn phải tuân thủ quy tắc về `@Valid` trên return value và trường hợp kế thừa song song từ nhiều interface.
- Đặt annotation trên phương thức **không có nghĩa validation tự chạy mỗi khi gọi method**. Cần `ExecutableValidator`, tích hợp Spring method validation hoặc cơ chế gọi tương đương.

Tài liệu này tập trung vào **“Kế thừa constraint từ lớp cha và interface”**, thuộc nhóm **“Kiểm tra lồng nhau”**, nên đồng thời làm rõ sự kết hợp giữa kế thừa type và `@Valid` khi một bean chứa các đối tượng con.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Biết constraint nào được lấy từ superclass/interface khi validate instance của subclass.
2. Phân biệt constraint ở field, getter, class, parameter và return value.
3. Viết getter override mà không vô tình làm mất constraint của interface/lớp cha.
4. Giải thích `@Valid` kế thừa và tại sao null không được cascade.
5. Thiết kế method interface đúng nguyên tắc thay thế Liskov (LSP).
6. Tránh `ConstraintDeclarationException` khi mở rộng interface hoặc override method.
7. Viết test kiểm tra bean validation và executable validation bằng Jakarta Validator, đồng thời hiểu điểm kích hoạt tương ứng của Spring.

## 2. Quy tắc kế thừa cho bean constraints

Giả sử:

~~~text
                  Identifiable (interface)
                      getCode()
                          |
                          v
                  BaseAccount (class)
                    id, address
                          |
                       extends
                          |
                          v
                   CustomerAccount
                      email, age
~~~

Khi đối tượng thực tế là `CustomerAccount`, việc gọi:

~~~java
Set<ConstraintViolation<CustomerAccount>> errors =
    validator.validate(customerAccount);
~~~

sẽ sử dụng metadata ràng buộc phù hợp từ toàn bộ hệ thống type, không chỉ những annotation viết trực tiếp trên khai báo `CustomerAccount`.

| Vị trí constraint | Có thể kế thừa khi validate lớp con? | Ví dụ |
| --- | --- | --- |
| Field trong superclass | **Có** | `@NotBlank private String id;` trong `BaseAccount`. |
| Getter của superclass | **Có** | `@Size(min=3) public String getCode()`. |
| Getter khai báo trong interface | **Có** | `@Email String getEmail();`. |
| Class-level constraint trên superclass/interface | **Có** | `@ValidBaseRecord` gắn trên type và hỗ trợ target `TYPE`. |
| `@Valid` đặt trên thuộc tính superclass | **Có** | `@Valid private Address address;`. |
| Constraint field riêng của subclass | **Có, cộng thêm** | `@Min(18) private int age;`. |
| Constraint trên tham số method | **Có quy tắc override riêng** | Interface định nghĩa `void save(@NotNull Input input)`. |
| Constraint trên return value method | **Có quy tắc override riêng** | Interface `@NotNull Result load()`. |
| Constructor constraints | Không “kế thừa constructor” theo Java | Chỉ kiểm tra constraint được khai báo trên constructor cụ thể. |

Bean Validation chuẩn **không phụ thuộc việc annotation Java có `@Inherited` hay không để áp dụng các quy tắc trên**. `@Inherited` trong Java chỉ có ý nghĩa nhất định đối với annotation trên class và không tự giải quyết việc thừa hưởng constraint ở interface/getter/method. Provider Bean Validation phải áp dụng quy tắc metadata và validation của chính chuẩn.

**Kết luận:** Việc một khai báo Java không hiện annotation khi bạn nhìn vào source code lớp con **không chứng minh constraint đó đã biến mất**. Hãy xem cả interface và superclass hoặc truy vấn metadata thông qua `Validator.getConstraintsForClass(...)`.

## 3. Field constraints từ superclass

Một field được ràng buộc ở lớp cha vẫn được xét khi validate instance của lớp con.

~~~java
import jakarta.validation.constraints.NotBlank;

class BaseEntity {
    @NotBlank(message = "id is required")
    private String id;

    BaseEntity(String id) {
        this.id = id;
    }
}

class UserEntity extends BaseEntity {
    private int level;

    UserEntity(String id, int level) {
        super(id);
        this.level = level;
    }
}
~~~

Đây là **đoạn khai báo minh họa**: khi `Validator.validate(new UserEntity("", 1))` chạy trong một ứng dụng đã có provider, constraint `@NotBlank` được khai báo trong `BaseEntity` vẫn áp dụng cho dữ liệu của đối tượng `UserEntity`.

Bạn **không cần lặp lại `@NotBlank` trên lớp con**. Việc lặp annotation vì tưởng lớp cha không được kiểm tra vừa tăng chi phí bảo trì, vừa có thể tạo vi phạm trùng lặp nếu đặt ràng buộc trên nhiều vị trí cùng property.

### Constraint từ nhiều cấp superclass

~~~text
AuditedEntity
    @NotNull createdAt
       |
       v
CatalogEntity
    @NotBlank code
       |
       v
ProductEntity
    @Positive price
~~~

`Validator.validate(productEntity)` có thể kiểm tra cả ba ràng buộc tương ứng, miễn là chúng thuộc nhóm validation đang thực thi và các giá trị/property có thể được truy cập theo mô hình Bean Validation. Không chỉ xét superclass trực tiếp.

**Đừng nhầm với Java field hiding.** Nếu subclass khai báo một field mới trùng tên field lớp cha, đó là **hai field riêng biệt**, không phải override field. Bean Validation có thể quan sát metadata khác nhau trên các field đó. Việc dùng field hiding trong DTO/entity dễ gây mơ hồ giữa dữ liệu được bind, serialize và validate; nên tránh thiết kế này. Dùng tên thuộc tính rõ ràng và xác định vị trí constraint nhất quán.

### Field và getter cùng khai báo constraint

Ví dụ:

~~~java
class Product {
    @NotBlank
    private String code;

    @NotBlank
    public String getCode() {
        return code;
    }
}
~~~

Hai ràng buộc được khai báo **hai lần** ở hai access points. Khi code rỗng, có thể xuất hiện nhiều constraint violation cùng property. Thường nên thống nhất sử dụng **field-level** hoặc **getter-level** cho một quy tắc, trừ khi có mục đích thực sự khác nhau. Điều này càng quan trọng trong hierarchy khi superclass dùng getter constraint nhưng subclass lại thêm field constraint cùng ý nghĩa.

## 4. Getter constraint từ superclass vẫn có hiệu lực khi override

Giả sử superclass công bố một hợp đồng về giá trị trả về của JavaBean getter:

~~~java
import jakarta.validation.constraints.Size;

class Document {
    private final String code;

    Document(String code) {
        this.code = code;
    }

    @Size(min = 3, max = 8)
    public String getCode() {
        return code;
    }
}

class SpecialDocument extends Document {
    SpecialDocument(String code) {
        super(code);
    }

    @Override
    public String getCode() {
        return super.getCode();
    }
}
~~~

`@Size` trên `Document.getCode()` là **property constraint**. Nó vẫn được áp dụng khi validate `SpecialDocument` ngay cả khi phương thức override ở subclass **không lặp lại annotation**. Ví dụ giá trị `"X"` (độ dài 1) không đạt `@Size(min=3)`.

**Có hai điều kiện cần phân biệt:**

- Khi gọi `validator.validate(specialDocument)`, getter constraint là thành phần của **bean/property validation**.
- Không thể suy luận rằng chỉ cần gọi `specialDocument.getCode()` thì `@Size` tự chạy và ném lỗi. Đây vẫn là lời gọi Java thông thường.

### Nếu subclass bổ sung getter constraint?

Ví dụ superclass có `@Size(min=3)`; subclass thêm một ràng buộc riêng lên getter phù hợp:

~~~java
class StrictDocument extends Document {
    StrictDocument(String code) {
        super(code);
    }

    @Override
    @Pattern(regexp = "[A-Z0-9]+")
    public String getCode() {
        return super.getCode();
    }
}
~~~

Đây là đoạn minh họa cần import `jakarta.validation.constraints.Pattern`. Đối tượng `StrictDocument` có thể bị kiểm tra **cả `@Size` kế thừa và `@Pattern` được thêm**. `@Pattern` không “ghi đè” `@Size`. Việc thêm constraint trên **return value** của method là loại thay đổi có thể hợp lệ theo quy tắc method inheritance; ở đây getter cũng là một bean property. Không được từ đó suy ra rằng có thể tự do thêm constraint vào **tham số** của method override (quy tắc khác hoàn toàn).

### Getter access khác field access

Getter constraint kiểm tra **giá trị getter trả về**; field constraint kiểm tra field được ràng buộc. Nếu getter biến đổi hoặc tính toán dữ liệu (ví dụ trả String đã normalize), kết quả có thể khác raw field. Vì vậy:

- Đảm bảo getter không có side effect và không gọi hạ tầng tốn kém khi provider đọc property.
- Chọn nơi khai báo nhất quán với dữ liệu muốn validate.
- Không đặt thêm constraint trên getter override chỉ để “giữ lại” constraint của superclass.

## 5. Constraint từ interface: lớp implement vẫn phải đáp ứng

Java không kế thừa field instance từ interface, nhưng interface có thể khai báo **getter constraint**, method parameter constraints và return-value constraints. Bean Validation thu thập các constraint phù hợp từ interface.

Ví dụ:

~~~java
import jakarta.validation.constraints.Email;

interface ContactView {
    @Email(message = "email is invalid")
    String getEmail();
}

class Customer implements ContactView {
    private final String email;

    Customer(String email) {
        this.email = email;
    }

    @Override
    public String getEmail() {
        return email;
    }
}
~~~

Khi một `Customer` được validate với `Validator.validate(...)`, `@Email` được khai báo trên `ContactView.getEmail()` vẫn áp dụng. `Customer.getEmail()` không cần lặp lại `@Email`.

Điều này hữu ích nếu nhiều implementation phải giữ một hợp đồng dữ liệu chung:

~~~text
                ContactView
              @Email getEmail()
                 /       \
                /         \
          Customer       Partner
             |              |
        getEmail()      getEmail()
~~~

Cả hai implementation đều có thể được kiểm tra theo ràng buộc trên interface. Nếu subclass còn kế thừa ràng buộc từ superclass, Bean Validation kết hợp metadata của các tuyến type thích hợp, không chọn một nguồn duy nhất.

### Interface getter constraint không phải activation của Spring AOP

Với `Validator.validate(customer)`, không cần `@Validated` trên interface chỉ để Bean Validation hiểu `@Email`. `@Validated` của Spring thường phục vụ việc **chọn group/điểm kích hoạt method validation** trong cơ chế Spring; nó không thay thế annotation constraint. Tương tự, annotation Bean Validation trên interface tự nó không làm Java hay Spring chạy validation mỗi lần gọi getter hoặc service method.

### Class-level constraint từ interface

Một constraint do dự án tạo với `@Target(TYPE)` có thể đặt trên interface:

~~~java
@ValidCustomerContract
interface CustomerContract {
    String getCustomerCode();
}

class CustomerRecord implements CustomerContract {
    @Override
    public String getCustomerCode() {
        return "C123";
    }
}
~~~

Đây chỉ là **đoạn minh họa**; `@ValidCustomerContract` cần là constraint annotation hợp lệ có `ConstraintValidator` và nhóm tương ứng. Khi validate instance `CustomerRecord`, constraint cấp type khai báo trên interface có thể được xét theo chuẩn. Thực tế nên dùng class-level constraint khi điều kiện phụ thuộc nhiều property, không nhét toàn bộ quy tắc cross-field vào một getter.

## 6. Liên hệ với kiểm tra lồng nhau: @Valid cũng được kế thừa

`@Valid` không tự xác minh thuộc tính bắt buộc; nó đánh dấu vị trí cần **cascade validation** vào đối tượng con không null. Điểm đánh dấu này có thể nằm trong superclass hoặc interface, và vẫn có ý nghĩa khi validate bean con kế thừa.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

class Address {
    @NotBlank
    String city;
}

class BaseProfile {
    @Valid
    @NotNull
    Address address;
}

class PremiumProfile extends BaseProfile {
    @NotBlank
    String membershipCode;
}
~~~

Với `PremiumProfile`:

- Nếu `address` khác null và `address.city` trắng, Bean Validation đi theo `@Valid` kế thừa ở `BaseProfile.address` và phát sinh vi phạm có property path dạng `address.city`.
- Nếu `address == null`, `@Valid` **bỏ qua null**; `@NotNull` trên thuộc tính base mới từ chối null.
- Nếu `membershipCode` trắng, constraint riêng của subclass cũng được xét.
- Nếu có nhiều violation, `Set<ConstraintViolation<PremiumProfile>>` không đảm bảo thứ tự.

**Kế thừa constraint** và **cascade** là hai cơ chế độc lập nhưng bổ trợ:

~~~text
PremiumProfile instance
    |
    +-- @NotNull / @Valid address   (khai báo trên BaseProfile)
    |       |
    |       +-- Address.city @NotBlank
    |
    +-- membershipCode @NotBlank   (khai báo trên PremiumProfile)
~~~

Nếu bỏ `@Valid` trên base, bean con `Address` không tự động được duyệt chỉ vì tồn tại field `address`. Nếu bỏ `@NotNull`, null address vẫn được phép về mặt constraint cascade. Đây là hai lỗi thiết kế phổ biến trong mô hình đối tượng nhiều cấp.

### Cascade qua getter của interface

~~~java
interface HasAddress {
    @Valid
    Address getAddress();
}

class Employee implements HasAddress {
    private Address address;

    @Override
    public Address getAddress() {
        return address;
    }
}
~~~

Đây là đoạn minh họa sử dụng lớp `Address` và import `@Valid`. Khi validate bean `Employee`, provider có thể cascade qua property getter được đánh dấu `@Valid` trên interface. Nếu muốn bắt buộc có địa chỉ, khai báo thêm `@NotNull` ở nơi quy định hợp đồng. Không cần lặp `@Valid` trên getter override chỉ để kế thừa; với return value của executable method, đánh dấu `@Valid` lặp lại trong một dòng kế thừa còn có thể **vi phạm chuẩn** (xem mục 11).

## 7. Phân biệt bean property validation với executable method validation

Đây là ranh giới kỹ thuật quan trọng khi làm việc với interface/superclass.

| Hành động | API/điểm kích hoạt | Áp dụng constraint nào? |
| --- | --- | --- |
| Kiểm tra trạng thái một object | `Validator.validate(bean)` | Field, getter, class-level, cascade `@Valid` phù hợp với groups và hierarchy. |
| Kiểm tra một property của bean | `Validator.validateProperty(bean, "name")` | Constraints trên property; không cascade `@Valid` theo chuẩn. |
| Kiểm tra một giá trị giả lập | `Validator.validateValue(Type.class, "name", value)` | Constraints trên property giả lập; không cần bean instance và không cascade. |
| Kiểm tra tham số một method call | `validator.forExecutables().validateParameters(...)` | Constraints parameter/cross-parameter trên executable, kể cả kế thừa hợp lệ. |
| Kiểm tra giá trị method trả về | `validator.forExecutables().validateReturnValue(...)` | Return-value constraints và cascade tương ứng từ hierarchy. |
| Spring service method validation | Proxy/AOP và/hoặc `MethodValidationPostProcessor` | Dùng metadata executable; cần thực sự kích hoạt và gọi qua cơ chế phù hợp. |
| Spring MVC request DTO | `@Valid @RequestBody` hoặc `@ModelAttribute` ... | Thường dùng bean validation và Spring BindingResult/Errors. |

**Không đánh đồng:** `@NotBlank` trên `User.getName()` phục vụ bean property validation; `@NotBlank` trên tham số `Service.register(String name)` phục vụ method-parameter validation. Chuẩn nêu getter không mặc định được xem là constrained method cho cơ chế executable validation; việc kiểm tra getter như property vẫn hoàn toàn hợp lệ.

Một interface service có annotation:

~~~java
interface OrderService {
    void submit(@NotNull Order input);
}
~~~

không tự làm cho `new OrderServiceImpl().submit(null)` ném lỗi. Để ràng buộc method chạy, phải kích hoạt `ExecutableValidator` hoặc Spring method-validation integration có cấu hình phù hợp.

## 8. Nguyên tắc Liskov và quy tắc override method parameter

Trong hệ thống kế thừa, subtype phải có thể thay thế supertype mà không làm lời gọi hợp lệ trước đó bị từ chối bất ngờ. Jakarta Bean Validation áp dụng nguyên tắc này lên method constraints:

- **Tham số = precondition** của người gọi.
- **Giá trị trả về = postcondition** mà implementation bảo đảm.

### 8.1. Hợp lệ: khai báo parameter constraint ở interface, không lặp lại trong implementation

~~~java
import jakarta.validation.constraints.NotBlank;

interface SearchService {
    String search(@NotBlank String query);
}

class SearchServiceImpl implements SearchService {
    @Override
    public String search(String query) {
        return "result";
    }
}
~~~

Hợp đồng tham số được đặt ở interface; implementation **không cần và không được khai báo lại** constraint trên tham số của method override theo quy tắc portable. Method validation của `SearchServiceImpl.search(...)` vẫn thấy `@NotBlank` từ interface.

### 8.2. Không hợp lệ: subtype tự thêm parameter constraint

~~~java
interface LegacySearch {
    String search(String query);
}

class StrictSearch implements LegacySearch {
    @Override
    public String search(@NotBlank String query) { // KHÔNG HỢP LỆ
        return "result";
    }
}
~~~

Annotation này làm thay đổi điều kiện đầu vào mà client của `LegacySearch` không dự kiến. Một Bean Validation provider tuân chuẩn phải báo `ConstraintDeclarationException` khi phát hiện khai báo method constraints không hợp lệ. Đây là **ví dụ cố ý sai**; không trộn vào dự án runnable ở phần sau.

### 8.3. Lặp lại @NotBlank trên override vẫn là vi phạm

~~~java
interface CheckedSearch {
    String search(@NotBlank String query);
}

class CheckedSearchImpl implements CheckedSearch {
    @Override
    public String search(@NotBlank String query) { // KHÔNG HỢP LỆ
        return "result";
    }
}
~~~

Dù cùng một annotation, việc khai báo constraint trên tham số ở subtype **vẫn vi phạm quy tắc override**. “Lặp lại để rõ ràng” không làm lời khai báo hợp lệ. Nên giữ method parameter constraints ở nguồn hợp đồng cao nhất phù hợp, thường là interface/superclass nơi method được định nghĩa.

### 8.4. @Valid trên parameter override cũng chịu giới hạn

~~~java
interface PaymentProcessor {
    void process(Payment payment);
}

class PaymentProcessorImpl implements PaymentProcessor {
    @Override
    public void process(@Valid Payment payment) { // KHÔNG HỢP LỆ
    }
}
~~~

Đây là đoạn minh họa cố ý sai, cần lớp `Payment`. Tự thêm `@Valid` ở tham số của method override cũng làm tăng precondition/cascade so với hợp đồng gốc. Nếu muốn validate sâu `Payment`, thiết kế `@Valid` ở tham số của interface/superclass ngay từ đầu hoặc tạo một method riêng với hợp đồng mới.

**Chú ý:** Quy tắc override method parameter không phủ định việc subclass có thể **bổ sung field/getter constraints của chính nó** ở bean validation. Hai lớp kiểm tra khác nhau và phải phân biệt.

## 9. Quy tắc return value: có thể tăng bảo đảm, không được xóa ràng buộc cũ

Ngược với precondition, subtype có thể làm **postcondition chặt hơn** mà vẫn an toàn cho client của interface.

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

interface TokenProvider {
    @NotNull(message = "token is required")
    String create();
}

class SecureTokenProvider implements TokenProvider {
    @Override
    @Size(min = 8, message = "token is too short")
    public String create() {
        return "123"; // Ví dụ cố ý trả giá trị không đạt @Size.
    }
}
~~~

Đây là **đoạn minh họa cấu trúc hợp lệ** nhưng implementation trả giá trị sai quy tắc để giải thích kết quả:

- Ràng buộc `@NotNull` của interface vẫn áp dụng.
- `@Size(min=8)` ở implementation được **bổ sung**, không thay thế `@NotNull`.
- Khi gọi `ExecutableValidator.validateReturnValue(...)` với `"123"`, `@Size` thất bại, `@NotNull` đạt.
- Khi gọi Java `create()` bình thường mà không kích hoạt method validation, provider không tự chạy và không tự ném exception.

Đừng hiểu “subclass được thêm return-value constraint” thành “được xóa annotation cũ”: không khai báo lại constraint trong source code subclass **không xóa** constraint interface/superclass.

Nếu một implementation thực sự cần hợp đồng return value yếu hơn, có thể đó là một phương thức khác hoặc một interface khác; không nên dựa vào override để thay đổi nghĩa hợp đồng đã công bố.

## 10. Nhiều interface song song: bẫy với parameter constraints

Một class có thể implement nhiều interface không nằm trên cùng một nhánh kế thừa:

~~~java
interface SearchA {
    void search(@NotBlank String query);
}

interface SearchB {
    void search(String query);
}

class CombinedSearch implements SearchA, SearchB {
    @Override
    public void search(String query) {
    }
}
~~~

Đây là **ví dụ cố ý không hợp lệ về phương diện method constraints** dù mã Java có thể biên dịch. Jakarta Bean Validation quy định: nếu một method được thừa hưởng từ các **kiểu song song không có quan hệ kế thừa** (ví dụ hai interface độc lập), **không được khai báo parameter constraints hoặc cascade parameter `@Valid` cho method đó ở bất kỳ nhánh nào**. Ở đây `SearchA.search` có `@NotBlank` nên vi phạm quy tắc.

Điều gây bất ngờ: **kể cả chỉ một trong hai interface có constraint**, cấu trúc trên vẫn không portable. Một vài provider có cấu hình riêng cho phép quy tắc nới lỏng, nhưng điều đó không còn là hợp đồng Jakarta Bean Validation portable.

Hướng thiết kế:

1. Đặt hợp đồng parameter method vào **một interface gốc duy nhất**, các interface khác thật sự kế thừa interface đó nếu phù hợp.
2. Tách method thành hai nghiệp vụ/tên khác nhau để tránh một method có hai nguồn hợp đồng đối nghịch.
3. Giữ parameter constraint ở tầng dịch vụ khác nếu phải tích hợp các interface bên ngoài không thể thay đổi; không dựa vào cơ chế provider-specific nếu muốn di động.
4. Viết test metadata và `ExecutableValidator` cho các class implement nhiều interface; không dừng ở kết luận “Java compile được”.

### Thừa hưởng interface theo một nhánh thì sao?

~~~java
interface BaseQuery {
    void search(@NotBlank String query);
}

interface ExtendedQuery extends BaseQuery {
    // Không cần khai báo lại search hoặc tham số @NotBlank.
}

class QueryImpl implements ExtendedQuery {
    @Override
    public void search(String query) {
    }
}
~~~

Với một tuyến kế thừa hợp lệ, method parameter constraint ở `BaseQuery` vẫn có thể được thực thi trên `QueryImpl` qua executable validation. `ExtendedQuery` và implementation không được thêm constraint lên tham số method đó.

## 11. @Valid trên return value: đừng đánh dấu cascade hai lần trong cùng tuyến kế thừa

Theo chuẩn, subtype có thể khai báo return-value cascade `@Valid` khi supertype chưa khai báo. Tuy nhiên **không được đánh dấu return value cho cascade hơn một lần trong cùng tuyến class/interface hierarchy**.

Ví dụ cố ý sai:

~~~java
interface AddressGateway {
    @Valid
    Address load();
}

class DefaultAddressGateway implements AddressGateway {
    @Override
    @Valid // KHÔNG HỢP LỆ: @Valid đã ở return value interface.
    public Address load() {
        return new Address();
    }
}
~~~

Đây là đoạn minh họa; `Address` cần có trong dự án và `@Valid` được import. Về Java, cách viết không nhất thiết gây lỗi biên dịch, nhưng provider phải phát hiện khai báo cascade trả về lặp lại theo quy tắc kế thừa và có thể ném `ConstraintDeclarationException` khi metadata/executable validation được truy cập.

Cách đúng:

~~~java
interface AddressGateway {
    @Valid
    Address load();
}

class DefaultAddressGateway implements AddressGateway {
    @Override
    public Address load() {
        return new Address();
    }
}
~~~

Ở đây `@Valid` từ interface vẫn được áp dụng. Khi validate return value khác null, các constraint của `Address` được cascade. Nếu method trả `null`, bản thân `@Valid` không từ chối null; hãy kết hợp `@NotNull` trên return-value contract nếu dữ liệu bắt buộc hiện diện.

Có thể **bổ sung các return-value constraints khác** trong subtype nếu hợp lệ, nhưng không lặp `@Valid` một cách tùy ý. Các cấu hình provider cho phép nới lỏng quy tắc là đặc thù và cần test rõ.

## 12. Chương trình runnable Java 17: kế thừa từ superclass, interface và method constraints

Để quan sát đầy đủ mà không cần khởi tạo web server, ta chạy một dự án Maven **Java 17** sử dụng **Jakarta Bean Validation 3.0**, provider **Hibernate Validator 8.0.6.Final**. Phiên bản 8.0.6.Final là bản phát hành của dòng 8.0 và dùng namespace `jakarta.validation.*`. Các ví dụ cố ý sai ở mục 8, 10 và 11 **không được thêm vào dự án này**.

Cấu trúc:

~~~text
constraint-inheritance-demo/
├── pom.xml
└── src/
    ├── main/java/demo/InheritanceDemo.java
    └── test/java/demo/InheritanceDemoTest.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constraint-inheritance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency `org.hibernate.validator:hibernate-validator` cung cấp provider; Jakarta API được đưa vào qua quan hệ dependency. `org.glassfish.expressly:expressly` là một implementation của Jakarta Expression Language dùng cho message interpolation khi chạy độc lập Java SE. Trong ứng dụng Spring Boot đã dùng starter validation và BOM, thường nên để Boot quản lý versions để tránh không tương thích.

### 12.1. Tệp src/main/java/demo/InheritanceDemo.java

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.executable.ExecutableValidator;

public class InheritanceDemo {

    interface EmailView {
        @Email(message = "email invalid")
        String getEmail();
    }

    static final class Address {
        @NotBlank(message = "city required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static class BaseMember {
        @NotBlank(message = "id required")
        private final String id;

        @NotNull(message = "address required")
        @Valid
        private final Address address;

        private final String code;

        BaseMember(String id, String code, Address address) {
            this.id = id;
            this.code = code;
            this.address = address;
        }

        @Size(min = 3, max = 8,
              message = "code length must be 3..8")
        public String getCode() {
            return code;
        }
    }

    static final class Member extends BaseMember implements EmailView {
        @Min(value = 18, message = "age must be at least 18")
        private final int age;

        private final String email;

        Member(String id, String code, Address address,
               String email, int age) {
            super(id, code, address);
            this.email = email;
            this.age = age;
        }

        @Override
        public String getEmail() {
            return email;
        }

        // Override getter; @Size của superclass vẫn được áp dụng.
        @Override
        public String getCode() {
            return super.getCode();
        }
    }

    interface LookupService {
        @NotNull(message = "result required")
        String find(
            @NotBlank(message = "query required") String query);
    }

    static final class LookupServiceImpl implements LookupService {
        @Override
        @Size(min = 3, message = "result too short")
        public String find(String query) {
            return "x";
        }
    }

    static Member invalidMember() {
        return new Member(
            "", "X", new Address(""), "wrong-email", 16);
    }

    static Member validMember() {
        return new Member(
            "ID-7", "C123", new Address("Ha Noi"),
            "member@example.com", 20);
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Member>> errors =
                validator.validate(invalidMember());

            System.out.println("beanErrors=" + errors.size());
            errors.stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .forEach(System.out::println);

            System.out.println(
                "validBeanErrors=" +
                validator.validate(validMember()).size());

            LookupServiceImpl service = new LookupServiceImpl();
            Method method = LookupServiceImpl.class
                .getMethod("find", String.class);

            ExecutableValidator executable =
                validator.forExecutables();

            var parameterErrors = executable.validateParameters(
                service, method, new Object[]{""});

            var returnErrors = executable.validateReturnValue(
                service, method, "x");

            System.out.println(
                "parameterErrors=" + parameterErrors.size());
            System.out.println(
                "returnErrors=" + returnErrors.size());
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InheritanceDemo
~~~

Stdout do chương trình tạo ra (Maven/provider có thể phát log ngoài các dòng này):

~~~text
beanErrors=5
address.city: city required
age: age must be at least 18
code: code length must be 3..8
email: email invalid
id: id required
validBeanErrors=0
parameterErrors=1
returnErrors=1
~~~

### 12.2. Giải thích năm lỗi bean

1. `BaseMember.id` có `@NotBlank` trong **superclass**; instance Member có `id=""` → 1 lỗi.
2. `BaseMember.getCode()` có `@Size(min=3,max=8)`; Member override getter không kèm annotation, nhưng `code="X"` vẫn không đủ dài → 1 lỗi.
3. `EmailView.getEmail()` có `@Email` từ **interface**; Member triển khai getter trả `"wrong-email"` → 1 lỗi.
4. `Member.age` có `@Min(18)` ở **subclass**; `age=16` → 1 lỗi.
5. `BaseMember.address` có `@Valid`; bean Address tồn tại nhưng `city=""` bị `@NotBlank` → 1 lỗi.

Tổng 5. `validMember()` thỏa những ràng buộc trên nên `validBeanErrors=0`.

Với `LookupService`:

- Interface khai báo tham số `@NotBlank` trên `find(String query)`.
- Implementation **không lặp** constraint ở tham số, nhưng `ExecutableValidator.validateParameters(...)` vẫn phát hiện query rỗng → `parameterErrors=1`.
- Interface khai báo return `@NotNull`; implementation **bổ sung** `@Size(min=3)` cho return value.
- `"x"` khác null nên đạt `@NotNull`, nhưng có độ dài 1 nên thất bại `@Size(min=3)` → `returnErrors=1`.

Chương trình không dùng Spring MVC/AOP; nó gọi trực tiếp Jakarta Validator để chứng minh metadata kế thừa. Hai cơ chế validation được tách bạch: `validate(bean)` cho bean state; `forExecutables()` cho method parameters/return value. Việc sắp xếp `sorted()` chỉ nhằm có stdout ổn định vì `Set` không cam kết thứ tự.

## 13. JUnit 5: kiểm chứng inheritance, nested @Valid và executable constraints

Tệp `src/test/java/demo/InheritanceDemoTest.java`:

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class InheritanceDemoTest {

    @Test
    void inheritsSuperclassAndInterfaceConstraints() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var errors = validator.validate(
                InheritanceDemo.invalidMember());

            assertEquals(5, errors.size());

            Set<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertEquals(
                Set.of("id", "code", "email", "age", "address.city"),
                paths);
        }
    }

    @Test
    void getterConstraintSurvivesOverride() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var member = new InheritanceDemo.Member(
                "ID-7", "X",
                new InheritanceDemo.Address("Ha Noi"),
                "member@example.com", 20);

            var errors = validator.validate(member);

            assertEquals(1, errors.size());
            assertEquals("code",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void inheritedCascadeRequiresNonNullChild() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var member = new InheritanceDemo.Member(
                "ID-7", "C123", null,
                "member@example.com", 20);

            var errors = validator.validate(member);

            // @Valid không tạo Address mới; @NotNull của base báo lỗi.
            assertEquals(1, errors.size());
            assertEquals("address",
                errors.iterator().next()
                    .getPropertyPath().toString());
        }
    }

    @Test
    void executableConstraintsAreInherited()
            throws NoSuchMethodException {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var impl = new InheritanceDemo.LookupServiceImpl();

            Method method = InheritanceDemo.LookupServiceImpl.class
                .getMethod("find", String.class);

            var executable = validator.forExecutables();

            var paramErrors = executable.validateParameters(
                impl, method, new Object[]{""});
            var returnErrors = executable.validateReturnValue(
                impl, method, "x");

            assertEquals(1, paramErrors.size());
            assertEquals(1, returnErrors.size());

            assertEquals("query required",
                paramErrors.iterator().next().getMessage());

            assertEquals("result too short",
                returnErrors.iterator().next().getMessage());
        }
    }

    @Test
    void validSubtypeHasNoBeanViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            assertTrue(validator.validate(
                InheritanceDemo.validMember()).isEmpty());
        }
    }

    @Test
    void metadataExposesInheritedProperties() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var metadata = validator.getConstraintsForClass(
                InheritanceDemo.Member.class);

            assertNotNull(
                metadata.getConstraintsForProperty("id"));
            assertNotNull(
                metadata.getConstraintsForProperty("code"));
            assertNotNull(
                metadata.getConstraintsForProperty("email"));
        }
    }
}
~~~

Lệnh:

~~~bash
mvn test
~~~

Với project mẫu đầy đủ, kỳ vọng **6 test thành công**. Các test kiểm tra tập path thay vì dựa vào “lỗi đầu tiên”; riêng những test chỉ có một lỗi mới dùng `iterator().next()`. Test về method validation được gọi **tường minh** qua `ExecutableValidator`, nên không cần giả định một proxy Spring đang chạy.

### Vì sao kiểm tra metadata?

`Validator.getConstraintsForClass(Member.class)` trả `BeanDescriptor` chứa thông tin constraint cho type trong hệ thống kế thừa. `getConstraintsForProperty("email")` giúp xác minh rằng constraint từ interface không mất; tương tự `id` từ field superclass và `code` từ getter superclass. Điều này hữu ích khi refactor type hierarchy, vì unit test không chỉ nhìn source code ở lớp con.

Có thể kiểm tra chi tiết annotation qua `PropertyDescriptor.getConstraintDescriptors()` để phát hiện thay đổi vô tình trong hợp đồng. Không nên tự duyệt Java reflection annotation trên *mỗi method declared ở subclass* rồi kết luận rằng không có annotation; Bean Validation metadata có nguồn rộng hơn Java `getDeclaredAnnotations()` trên một member cụ thể.

## 14. Kết hợp group validation với các constraint kế thừa

Constraint kế thừa vẫn chịu quy tắc **group**. Mặc định, `Validator.validate(bean)` kiểm tra nhóm `jakarta.validation.groups.Default` cùng các quy tắc kế thừa/group sequence áp dụng.

Ví dụ:

~~~java
interface UpdateChecks {}

class BaseCommand {
    @NotNull
    Long id;
}

class UpdateCommand extends BaseCommand {
    @NotBlank(groups = UpdateChecks.class)
    String changeReason;
}
~~~

Đây là đoạn khai báo minh họa. Khi gọi `validator.validate(updateCommand)`, `@NotNull` thuộc Default của superclass được xét, còn `@NotBlank(groups=UpdateChecks.class)` chưa chắc được xét vì không thuộc Default. Khi gọi:

~~~java
validator.validate(
    updateCommand,
    jakarta.validation.groups.Default.class,
    UpdateChecks.class);
~~~

cả hai nhóm được yêu cầu kiểm tra. Không có bảo đảm thứ tự nếu không dùng `@GroupSequence`. Với các interface định nghĩa group, Java interface inheritance có thể ảnh hưởng **group inheritance**, nhưng cần phân biệt nó với **constraint declarations đặt trên Java interfaces**; đây là hai khái niệm liên quan nhưng không đồng nhất.

### Group conversion trong cascade

Đối với một đối tượng con được kế thừa qua `@Valid`, Bean Validation còn hỗ trợ `@ConvertGroup` để chuyển group khi đi theo đường cascade. Ví dụ một base type có `@Valid` cho `Address`; subtype kế thừa quan hệ đó, nên quy tắc cascade/group conversion phù hợp có thể ảnh hưởng constraint nào chạy trên Address. Nếu áp dụng group conversion, hãy đặt ở nơi quy định quan hệ cascade và kiểm thử với các group thực tế.

Đừng thêm `@Valid` hoặc `@ConvertGroup` ở getter override chỉ để “bù” cho việc không thấy annotation trên subclass. Trước hết hãy xem metadata và tuân thủ quy tắc khai báo return-value cascade trong hierarchy.

## 15. Kích hoạt method validation trong Spring Framework và Spring Boot

Jakarta Bean Validation là API/chuẩn; Spring cung cấp điểm tích hợp để gọi nó đúng lúc. Cách thường gặp là `@Validated` của Spring kết hợp method-validation infrastructure.

Trong ứng dụng Spring Boot 3 (phiên bản thực tế cần phù hợp BOM), dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là một dependency **dùng trong project Spring Boot đã cấu hình dependency management**, không dùng một mình như `pom.xml` độc lập ở mục 12. Với Spring Framework thuần, cần cấu hình provider và `MethodValidationPostProcessor` khi muốn AOP method validation.

Ví dụ interface service khai báo hợp đồng:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public interface CustomerService {
    @NotNull
    String lookup(
        @NotBlank String customerCode);
}
~~~

Implementation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CustomerServiceImpl implements CustomerService {

    @Override
    public String lookup(String customerCode) {
        return customerCode;
    }
}
~~~

Đây là **các đoạn tích hợp**, không phải ứng dụng Spring Boot chạy độc lập. Khi Spring method validation được kích hoạt và lời gọi đi qua bean/proxy phù hợp, ràng buộc trên tham số và return value **từ interface** có thể được kiểm tra. Không lặp `@NotBlank` trên tham số method override.

Lưu ý:

- `@Validated` cho Spring biết việc kích hoạt/phạm vi method validation trong cơ chế tương ứng; nó không thay thế `@NotBlank` hoặc `@NotNull`.
- Nếu gọi nội bộ `this.lookup(...)` trong cùng instance, lời gọi có thể **không đi qua AOP proxy**; không tự tin rằng method validation xảy ra nếu cơ chế là proxy-based.
- Proxy kiểu JDK và class-based có chi tiết riêng về interface/method visibility. Hãy test lời gọi **qua bean Spring** trong configuration thực tế.
- Spring MVC 6.1+ có built-in method validation cho controller; lỗi trực tiếp trên parameter/return value có thể xuất hiện dưới dạng `HandlerMethodValidationException`. Với `@Valid @RequestBody` kiểm tra object, lỗi thường là `MethodArgumentNotValidException` khi không dùng `BindingResult`/`Errors` nhận lỗi và không có method validation cấp method thay thế.
- Service method validation AOP thường có thể ném `ConstraintViolationException`, hoặc exception thích ứng của Spring khi cấu hình tùy chọn. Không coi tất cả exception Spring validation là cùng một loại.
- Nếu interface method chỉ dùng `@Valid` trên tham số, vẫn phải thực thi method validation để cascade; việc object có `@Valid` trong source code không tự xác nhận khi gọi Java.

### Cách kiểm thử trong ứng dụng Spring

Viết một integration test lấy `CustomerService` từ Spring context và gọi `lookup("")`. Khẳng định lỗi validation theo cơ chế được cấu hình, không nhất thiết phụ thuộc mọi dự án đều dùng cùng loại exception. Ngoài ra, kiểm thử `lookup("C123")` thành công. Đừng chỉ `new CustomerServiceImpl()` rồi gọi method để kết luận Spring method validation thất bại — đối tượng đó không phải bean do Spring quản lý, nên thường không có interceptor/proxy.

## 16. Metadata API giúp kiểm tra kế thừa và điều tra lỗi

Ngoài `validate(...)`, Bean Validation có metadata API để truy vấn các constraint mà provider nhìn thấy:

~~~java
BeanDescriptor descriptor =
    validator.getConstraintsForClass(Member.class);

PropertyDescriptor emailDescriptor =
    descriptor.getConstraintsForProperty("email");

boolean constrained =
    emailDescriptor != null
        && emailDescriptor.hasConstraints();
~~~

Đây là **đoạn minh họa** cần imports `jakarta.validation.metadata.BeanDescriptor`, `PropertyDescriptor` và các biến `validator`, `Member`. `Member` có thể khai báo ở dự án mẫu dưới dạng `InheritanceDemo.Member`.

Nếu một property chỉ có cascade `@Valid` mà không có constraint trực tiếp trên giá trị của chính property, `PropertyDescriptor.hasConstraints()` không nhất thiết phản ánh toàn bộ ý nghĩa cascade. Metadata còn cho biết property có được `isCascaded()` hay không và các `CascadableDescriptor`/container-element metadata liên quan. Vì vậy không dùng mỗi `hasConstraints()` để kết luận “không có validation” trong mọi tình huống.

Ở cấp method, dùng `BeanDescriptor.getConstraintsForMethod(name, parameterTypes...)` và `MethodDescriptor.getParameterDescriptors()`/`getReturnValueDescriptor()` để xem contract. Các constraint parameter từ interface và return constraints thêm ở subtype có thể được tổng hợp trong metadata executable. Đây là công cụ tốt để phát hiện việc refactor làm sai hợp đồng mà chưa chạy request HTTP.

### Hình dung cách xác minh

~~~text
validator.getConstraintsForClass(Subtype.class)
             |
             +-- PropertyDescriptor("id")
             |      từ field superclass
             |
             +-- PropertyDescriptor("code")
             |      từ getter superclass
             |
             +-- PropertyDescriptor("email")
             |      từ getter interface
             |
             +-- PropertyDescriptor("address")
             |      @Valid cascade / @NotNull
             |
             +-- MethodDescriptor("find", String.class)
                    parameter constraints từ interface
                    return constraints từ interface + implementation
~~~

Tách bean-property metadata và executable metadata là cách chống nhầm lẫn đặc biệt hữu ích khi source code sử dụng một hệ thống nhiều interface và override.

## 17. Những lỗi thường gặp khi kế thừa constraint

| Lỗi thiết kế | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lặp `@NotBlank` trên getter override vì nghĩ mất constraint ở interface | Constraint của interface đã được kế thừa khi validate. | Giữ nguồn hợp đồng ở interface; xác minh qua `Validator.validate`. |
| Đặt constraint ở superclass nhưng chỉ nhìn annotation subclass khi debug | Subclass source không phản ánh toàn bộ metadata provider. | Kiểm tra hierarchy và `getConstraintsForClass`. |
| Dùng Java reflection `getDeclaredAnnotations()` để xác định tất cả Bean Validation constraints | Bỏ sót superclass/interface và metadata provider. | Dùng Bean Validation metadata API. |
| Override field trùng tên field ở superclass | Java field hiding không phải override, metadata/binding dễ lệch. | Tránh field hiding và thống nhất access strategy. |
| Gắn cùng constraint trên field và getter không cần thiết | Có thể tạo vi phạm trùng hoặc kết quả khác nếu getter biến đổi. | Chọn vị trí constraint rõ ràng. |
| Thêm `@NotBlank` trên method parameter ở implementation | Vi phạm nguyên tắc không tăng precondition. | Khai báo ở interface/supertype nơi method được định nghĩa. |
| Lặp nguyên parameter annotation ở subtype | Dù giống constraint cũ, vẫn vi phạm quy tắc portable. | Không lặp, provider sẽ kế thừa. |
| Thêm `@Valid` ở parameter override | Cũng có thể tăng precondition do cascade mới. | Định nghĩa cascade parameter ở nguồn hợp đồng gốc. |
| Hai interface độc lập cùng có method, một bên khai báo parameter constraint | Vi phạm quy tắc parallel types. | Tái cấu trúc hợp đồng hoặc tách method. |
| Gắn `@Valid` trên return value ở cả interface và method override | Cấm lặp cascade return trong cùng một tuyến hierarchy. | Đặt `@Valid` một lần ở nơi phù hợp. |
| Nghĩ bỏ annotation ở return method override sẽ xóa constraint interface | Metadata thừa hưởng vẫn áp dụng. | Thiết kế hợp đồng mới nếu cần nghĩa khác. |
| Chỉ dùng `@Valid` mà mong field nested null bị từ chối | Cascade bỏ qua null. | Thêm `@NotNull` nếu bắt buộc hiện diện. |
| Chỉ dùng `@NotNull` trên bean con, nghĩ thuộc tính con đã được kiểm tra | `@NotNull` không cascade. | Kết hợp `@Valid` khi cần kiểm tra sâu. |
| Gọi method Java bình thường mà không kích hoạt executable validation | Annotation method không chạy tự động. | Cấu hình Spring AOP/method validation hoặc gọi `ExecutableValidator`. |
| Chỉ test bean `validate(...)` rồi cho rằng method parameter được kiểm tra | Hai đường API riêng biệt. | Test `forExecutables()` và integration Spring. |
| Dựa vào `ConstraintViolation` theo thứ tự của Set | Set không cam kết thứ tự. | Sort theo path/code khi hiển thị hoặc test. |
| Bắt mọi `ConstraintDeclarationException` và trả 400 như lỗi người dùng | Thường là lỗi khai báo metadata/cấu hình server, không phải input sai. | Sửa code/constraint hierarchy và giám sát lỗi hạ tầng. |
| Trộn `javax.validation.*` với provider `jakarta.validation.*` | Không đồng bộ namespace giữa Spring 5/6 và Hibernate Validator. | Đồng bộ dependency và imports đúng version. |
| Kỳ vọng `@Validated` trên interface là “tạo ra” bean constraints | `@Validated` là annotation tích hợp Spring, không phải constraint data. | Phân biệt activation với constraint declarations. |

## 18. Checklist triển khai an toàn

1. Xác định object được validate là class nào và các superclass/interface liên quan.
2. Với **bean state**, rà field, getter, class-level constraints ở toàn bộ hierarchy.
3. Chọn field-level/getter-level strategy nhất quán; tránh field hiding.
4. Xác định `@Valid` nằm ở đâu và có cần `@NotNull` cho object con không.
5. Với **method parameters**, đặt constraint ở interface/supertype gốc và không lặp lại trong override.
6. Kiểm tra các phương thức implement từ **nhiều interface song song** trước khi đặt parameter constraints.
7. Với **method return value**, có thể thêm postcondition nhưng không lặp cascade `@Valid` dọc cùng hierarchy.
8. Xác định group: Default, custom group, group sequence và group conversion (nếu có).
9. Kiểm tra Bean Validation metadata bằng `getConstraintsForClass(...)`, `getConstraintsForProperty(...)` và method descriptors khi cần.
10. Viết test riêng cho `Validator.validate(...)` và `ExecutableValidator` vì chúng không tương đương.
11. Nếu dùng Spring, xác minh có provider/starter, `@Validated`/method-validation infrastructure được kích hoạt đúng và lời gọi đi qua bean/proxy.
12. Kiểm tra kiểu exception thực tế ở boundary: data binding, method validation, invalid metadata có thể khác nhau.
13. Kiểm tra property path của nested violations, xử lý Set không thứ tự và không trả raw `invalidValue` nhạy cảm.
14. Xem lại các phương thức override sau mỗi lần refactor interface để tránh `ConstraintDeclarationException`.

### Câu hỏi tự kiểm tra

1. Một getter `@Email` nằm trong interface; class implement không lặp annotation. `Validator.validate(instance)` có áp dụng `@Email` không?
2. Lớp con override getter `@Size` của lớp cha nhưng không ghi `@Size` ở override. Constraint có còn hiệu lực không?
3. Vì sao `@NotNull` trên `BaseProfile.address` khác `@Valid` trên cùng field?
4. Interface method chưa có parameter constraint; implementation có thể thêm `@NotBlank` vào parameter override không?
5. Interface đã có `@NotBlank` trên parameter; implementation lặp đúng annotation đó có hợp lệ theo chuẩn không?
6. Một class implement hai interface độc lập cùng khai báo method; một interface có parameter constraint. Đây có phải cấu trúc method constraints portable không?
7. Subtype có được thêm `@Size` trên return value method nếu supertype đã có `@NotNull` không?
8. Interface đã có `@Valid` trên return value; subclass có được đặt `@Valid` lần nữa trên method override không?
9. Gọi trực tiếp `new ServiceImpl().find("")` có tự chạy Bean Validation cho method parameter không?
10. Vì sao `Validator.validate(bean)` không đủ để xác nhận parameter constraints trên service method?
11. API nào giúp xem constraints kế thừa mà không chỉ đọc annotation trực tiếp của subclass?

**Đáp án:** (1) Có; (2) còn hiệu lực; (3) `@NotNull` cấm thiếu object, `@Valid` yêu cầu validate sâu object đã hiện diện; (4) không theo quy tắc portable; (5) không; (6) không; (7) có, đó là tăng postcondition; (8) không, cấm lặp cascade return trong cùng tuyến; (9) không, cần activation; (10) bean validation và executable validation khác nhau; (11) `Validator.getConstraintsForClass(...)` và Bean Validation metadata API.

## 19. Tài liệu tham khảo chính thức

- Jakarta Bean Validation 3.0 Specification — *Constraint declaration and validation process*, *Method constraints in inheritance hierarchies*, *Validation routine*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/ExecutableValidator.html
- Jakarta Bean Validation 3.0 API — `ConstraintDeclarationException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintDeclarationException.html
- Hibernate Validator 8.0 Reference Guide — *Inheritance hierarchies*, *Method constraints*, *Cascaded validation*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 releases and Maven coordinates: https://hibernate.org/validator/releases/8.0/
- Spring Framework — Java Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — MethodValidationPostProcessor Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
