# Root object trong StandardEvaluationContext của Spring Expression Language (SpEL)

Trong Spring Expression Language (SpEL), **root object** là đối tượng gốc mà biểu thức dùng làm điểm bắt đầu khi phân giải các property và method không có tiền tố biến. `StandardEvaluationContext` lưu root object cùng các thành phần cần thiết để đánh giá biểu thức, chẳng hạn property accessor, method resolver, biến, hàm và type converter.

Khi một biểu thức như `name` được đánh giá, SpEL tìm property `name` trên root object hiện tại. Nếu biểu thức dùng `#root`, nó tham chiếu tường minh đến đối tượng gốc. Hiểu đúng vai trò của root object giúp kiểm soát dữ liệu đầu vào, tái sử dụng biểu thức và tránh nhầm lẫn với đối tượng hiện hành `#this`.

## 1. Root object là gì?

Root object là đối tượng được đặt làm ngữ cảnh gốc khi SpEL đánh giá một biểu thức. Những property hoặc method được tham chiếu trực tiếp, không có tiền tố `#`, thường được phân giải từ đối tượng này.

Ví dụ, có lớp Customer:

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isAdult() {
        return age >= 18;
    }
}
~~~

Tạo một Customer và dùng nó làm root object:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String name = parser.parseExpression("name")
        .getValue(context, String.class);

Boolean adult = parser.parseExpression("isAdult()")
        .getValue(context, Boolean.class);
~~~

Trong hai biểu thức:

- `name` được phân giải từ root object `customer`.
- `isAdult()` gọi method trên root object.
- `getValue(context, ...)` đánh giá biểu thức trong context đã cấu hình.

Root object không phải bản thân chuỗi biểu thức và cũng không phải `ExpressionParser`. Nó là dữ liệu mà biểu thức bắt đầu truy cập.

## 2. Tạo StandardEvaluationContext với root object

`StandardEvaluationContext` thuộc package `org.springframework.expression.spel.support`. Cách đơn giản nhất để đặt root object là truyền đối tượng vào constructor:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);
~~~

Context sẽ giữ đối tượng customer làm root object cho các lần đánh giá sử dụng context đó.

Cũng có thể tạo context trước rồi đặt root object sau:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);
~~~

Hai cách trên đều thiết lập root object. Cách dùng constructor phù hợp khi đối tượng gốc đã có sẵn lúc tạo context. `setRootObject(...)` hữu ích khi cần thay root object sau khi context được tạo.

Có thể lấy root object hiện tại thông qua:

~~~java
TypedValue root = context.getRootObject();
Object value = root.getValue();
~~~

`getRootObject()` trả về `TypedValue`, không trả trực tiếp đối tượng dưới dạng `Object`. Gọi `getValue()` trên TypedValue để lấy đối tượng được bọc bên trong.

## 3. Đánh giá biểu thức bằng root object trong context

Sau khi tạo context, truyền context vào `getValue(...)`:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(
                new Customer("Lan", 25)
        );

Expression expression = parser.parseExpression("age >= 18");

Boolean result = expression.getValue(context, Boolean.class);

// result == true
~~~

Trong ví dụ, biểu thức không cần ghi tên biến hoặc truyền customer trực tiếp vào từng lời gọi. SpEL dùng root object được lưu trong context để phân giải `age`.

Một context có thể được dùng cho nhiều biểu thức:

~~~java
Expression nameExpression = parser.parseExpression("name");
Expression ageExpression = parser.parseExpression("age");
Expression adultExpression = parser.parseExpression("isAdult()");

String name = nameExpression.getValue(context, String.class);
Integer age = ageExpression.getValue(context, Integer.class);
Boolean adult = adultExpression.getValue(context, Boolean.class);
~~~

Cách này hữu ích khi một nhóm biểu thức cùng làm việc trên một đối tượng nghiệp vụ. Parser có thể phân tích từng chuỗi thành Expression; context cung cấp root object và môi trường đánh giá chung.

Nếu muốn đánh giá cùng một Expression trên các đối tượng khác nhau, có thể thay root object trong context hoặc truyền root object riêng qua overload phù hợp của `getValue(...)`.

## 4. Thay đổi root object bằng setRootObject

`setRootObject(...)` cho phép đổi đối tượng gốc của context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression = parser.parseExpression("name");

context.setRootObject(new Customer("Lan", 25));
String firstName = expression.getValue(context, String.class);

context.setRootObject(new Customer("Minh", 31));
String secondName = expression.getValue(context, String.class);
~~~

Cùng một Expression được đánh giá hai lần trên hai root object khác nhau. Lần đầu kết quả là Lan; lần sau kết quả là Minh.

Điều này cho phép tái sử dụng biểu thức khi cấu trúc property mà biểu thức yêu cầu vẫn tương thích giữa các đối tượng. Nếu root object mới không có property hoặc method mà biểu thức tham chiếu, quá trình đánh giá có thể thất bại.

Khi context được chia sẻ giữa nhiều luồng hoặc nhiều yêu cầu, cần tránh thay đổi root object dùng chung theo cách khiến các lần đánh giá ảnh hưởng lẫn nhau. Trong ứng dụng đồng thời, tạo context riêng cho từng đơn vị công việc hoặc quản lý vòng đời context rõ ràng.

## 5. #root và #this khác nhau như thế nào?

SpEL cung cấp hai biến đặc biệt quan trọng:

- `#root` luôn tham chiếu đến root object của lần đánh giá hiện tại.
- `#this` tham chiếu đến đối tượng đang là ngữ cảnh đánh giá hiện hành tại vị trí biểu thức được thực hiện.

Khi biểu thức chỉ truy cập trực tiếp root object, `#root` và `#this` thường cùng trỏ đến một đối tượng:

~~~text
name
#root.name
#this.name
~~~

Ví dụ:

~~~java
Expression expression = parser.parseExpression("#root.name");

String name = expression.getValue(context, String.class);
~~~

Trong biểu thức đơn giản này, `#root.name` đọc property name của root object.

Sự khác biệt trở nên rõ ràng trong các biểu thức lồng nhau như selection và projection. Khi SpEL duyệt collection, `#this` trở thành phần tử hiện tại, còn `#root` vẫn tham chiếu đối tượng gốc ban đầu.

Ví dụ, giả sử root object là CustomerReport có property customers:

~~~java
public class CustomerReport {
    private final List<Customer> customers;
    private final String region;

    public CustomerReport(List<Customer> customers, String region) {
        this.customers = customers;
        this.region = region;
    }

    public List<Customer> getCustomers() {
        return customers;
    }

    public String getRegion() {
        return region;
    }
}
~~~

Biểu thức:

~~~text
customers.?[#this.age >= 18].![#this.name + ' - ' + #root.region]
~~~

Trong selection, `#this` là Customer đang được kiểm tra. Trong projection, `#this` là Customer đang được biến đổi. `#root.region` vẫn lấy region từ CustomerReport bên ngoài.

Phân biệt hai biến này đặc biệt hữu ích khi biểu thức có collection lồng nhau hoặc cần kết hợp dữ liệu từ root object với dữ liệu của từng phần tử.

## 6. Root object và biến trong EvaluationContext

Root object và biến là hai cơ chế truy cập dữ liệu khác nhau.

| Cú pháp | Nguồn dữ liệu |
|---|---|
| `name` | Property hoặc method được phân giải từ root object hiện tại |
| `#root.name` | Property name của root object, tham chiếu tường minh |
| `#minimumAge` | Biến minimumAge được đăng ký trong EvaluationContext |
| `#this.name` | Property name của đối tượng hiện hành tại vị trí đánh giá |

Đăng ký biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("region", "South");

Expression expression = parser.parseExpression(
        "age >= #minimumAge"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Trong biểu thức này, `age` lấy từ root object, còn `#minimumAge` lấy từ biến trong context.

Có thể dùng biến cùng với root object:

~~~text
#root.age >= #minimumAge and #root.region == #region
~~~

Tên biến sau dấu `#` được đăng ký bằng `setVariable(...)`. Nếu biến chưa được đăng ký hoặc giá trị không có kiểu phù hợp, biểu thức có thể không đánh giá được như mong đợi.

## 7. Root object có thể là một đối tượng miền nghiệp vụ

Root object không bắt buộc phải là một lớp được tạo riêng cho SpEL. Nó có thể là bất kỳ đối tượng nào có những property hoặc method mà biểu thức cần truy cập.

Ví dụ, có thể dùng đối tượng cấu hình:

~~~java
public class FeatureSettings {
    private final boolean checkoutEnabled;
    private final int maximumItems;

    public FeatureSettings(boolean checkoutEnabled, int maximumItems) {
        this.checkoutEnabled = checkoutEnabled;
        this.maximumItems = maximumItems;
    }

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }

    public int getMaximumItems() {
        return maximumItems;
    }
}

FeatureSettings settings = new FeatureSettings(true, 20);

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

Boolean enabled = parser.parseExpression("checkoutEnabled")
        .getValue(context, Boolean.class);

Integer limit = parser.parseExpression("maximumItems")
        .getValue(context, Integer.class);
~~~

Root object có thể là DTO, entity, object cấu hình, đối tượng báo cáo hoặc một object chuyên cung cấp dữ liệu cho biểu thức.

Nên chỉ cung cấp những đối tượng và property mà biểu thức thực sự cần. Điều này làm rõ dữ liệu đầu vào và giảm bề mặt truy cập không cần thiết.

## 8. Root object và property/method resolution

Khi biểu thức truy cập property hoặc method trên root object, SpEL sử dụng các thành phần của EvaluationContext để phân giải cách truy cập.

`StandardEvaluationContext` mặc định hỗ trợ các cơ chế truy cập phản chiếu cho Java object thông thường. Có thể mở rộng bằng PropertyAccessor hoặc MethodResolver tùy trường hợp.

Ví dụ, nếu root object là Customer:

~~~text
name
age
isAdult()
~~~

SpEL có thể đọc property qua accessor phù hợp và gọi method nếu method resolver cho phép.

Nếu property không tồn tại, getter không phù hợp hoặc method không thể được phân giải, quá trình đánh giá có thể phát sinh lỗi. Khi đó, kiểm tra:

- Root object thực tế được đặt trong context.
- Tên property và method trong biểu thức.
- Getter, setter hoặc method công khai của lớp.
- PropertyAccessor và MethodResolver được đăng ký.
- Kiểu kết quả mà mã Java yêu cầu.

Không nên coi việc đặt root object là bảo đảm mọi property hoặc method đều có thể truy cập. Quyền truy cập còn phụ thuộc vào cấu trúc đối tượng và cấu hình context.

## 9. Root object và getValue(rootObject)

Ngoài việc lưu root object trong StandardEvaluationContext, các overload của Expression cho phép truyền root object trực tiếp khi đánh giá.

Ví dụ:

~~~java
Expression expression = parser.parseExpression("name");

Customer customer = new Customer("Lan", 25);

String name = expression.getValue(customer, String.class);
~~~

Cách này phù hợp khi chỉ cần đánh giá một biểu thức trên một root object và không cần cấu hình thêm biến, resolver hoặc accessor.

Khi cần cấu hình nhiều thành phần của EvaluationContext, hãy tạo StandardEvaluationContext và đặt root object vào đó:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.addPropertyAccessor(new CustomerPropertyAccessor());

Boolean eligible = parser.parseExpression(
        "age >= #minimumAge"
).getValue(context, Boolean.class);
~~~

Không nên nhầm overload `getValue(rootObject, ...)` với việc truyền EvaluationContext. Một overload nhận object gốc trực tiếp; overload khác nhận context đã cấu hình. Chọn overload theo môi trường đánh giá mà biểu thức cần.

## 10. Root object trong collection, selection và projection

Trong biểu thức collection, đối tượng hiện hành có thể thay đổi khi SpEL duyệt từng phần tử.

Giả sử root object là CustomerReport có danh sách customers và property region. Có thể lọc khách hàng trưởng thành rồi tạo chuỗi kết hợp tên và khu vực:

~~~text
customers.?[#this.age >= 18].![#this.name + ' - ' + #root.region]
~~~

Cách đánh giá:

1. Root object ban đầu là CustomerReport.
2. `customers` lấy collection từ root object.
3. Trong selection, `#this` là Customer hiện tại.
4. Các Customer có age từ 18 trở lên được giữ lại.
5. Trong projection, `#this.name` lấy tên từng Customer.
6. `#root.region` lấy region từ CustomerReport gốc.

Nếu dùng nhầm `#this.region` trong projection, SpEL sẽ tìm region trên Customer hiện tại. Kết quả có thể sai hoặc phát sinh lỗi nếu Customer không có property đó.

Khi viết biểu thức lồng nhau, hãy dùng `#root` cho dữ liệu thuộc đối tượng gốc và `#this` cho phần tử đang được xử lý.

## 11. Root object và SimpleEvaluationContext

`StandardEvaluationContext` cung cấp nhiều khả năng đánh giá, bao gồm property access, method invocation, biến, hàm và các resolver có thể cấu hình.

Trong các trường hợp cần giới hạn tính năng, Spring có `SimpleEvaluationContext`. Context này cho phép chọn phạm vi property access và khả năng gọi method phù hợp với nhu cầu data binding.

Ví dụ dùng SimpleEvaluationContext với property accessor:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

String name = parser.parseExpression("name")
        .getValue(context, customer, String.class);
~~~

Trong ví dụ, root object được truyền trực tiếp cho lần đánh giá. SimpleEvaluationContext cũng có thể được tạo với các property accessor được chỉ định qua builder tương ứng.

Chọn StandardEvaluationContext khi cần khả năng đánh giá đầy đủ. Chọn SimpleEvaluationContext khi có thể giới hạn chức năng và muốn kiểm soát rõ hơn những thao tác biểu thức được phép thực hiện.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Biểu thức không tìm thấy property | Root object chưa được đặt hoặc không có property tương ứng. | Kiểm tra constructor/setRootObject và tên property. |
| Nhầm #root với #this | Trong selection/projection, #this là phần tử hiện tại. | Dùng #root cho đối tượng gốc và #this cho phần tử đang duyệt. |
| Đăng ký biến nhưng quên dấu # | Biến trong SpEL được tham chiếu bằng cú pháp #variable. | Dùng đúng tên biến với tiền tố #. |
| Thay root object nhưng biểu thức vẫn lỗi | Đối tượng mới không có property/method mà biểu thức yêu cầu. | Đảm bảo các root object có cấu trúc tương thích. |
| Dùng getRootObject() như trả về Object | Phương thức trả về TypedValue. | Gọi getValue() trên TypedValue. |
| Dùng context chung rồi thay root object giữa nhiều luồng | Các lần đánh giá có thể nhìn thấy root object thay đổi ngoài dự kiến. | Tạo context riêng cho từng luồng hoặc đơn vị công việc. |
| Cho rằng root object mở mọi quyền truy cập | Accessor và resolver vẫn quyết định property/method nào được hỗ trợ. | Kiểm tra cấu hình EvaluationContext. |
| Dùng StandardEvaluationContext cho biểu thức không đáng tin cậy | Context có thể cung cấp nhiều khả năng truy cập mạnh. | Giới hạn root object và cân nhắc SimpleEvaluationContext. |

## 13. Ghi nhớ

- Root object là đối tượng gốc mà SpEL dùng để phân giải property và method không có tiền tố biến.
- Có thể đặt root object bằng constructor StandardEvaluationContext(rootObject) hoặc setRootObject(...).
- getRootObject() trả về TypedValue; gọi getValue() để lấy đối tượng bên trong.
- `#root` luôn tham chiếu root object; `#this` tham chiếu đối tượng hiện hành và có thể thay đổi trong selection/projection.
- Biến được đăng ký bằng setVariable(...) và tham chiếu qua cú pháp #variable.
- Một Expression có thể được đánh giá trên các root object khác nhau nếu chúng đáp ứng cấu trúc mà biểu thức yêu cầu.
- Có thể truyền root object trực tiếp vào getValue(...) hoặc lưu nó trong EvaluationContext.
- PropertyAccessor và MethodResolver vẫn quyết định cách property và method được truy cập.
- Chọn StandardEvaluationContext hoặc SimpleEvaluationContext theo phạm vi tính năng cần thiết.
