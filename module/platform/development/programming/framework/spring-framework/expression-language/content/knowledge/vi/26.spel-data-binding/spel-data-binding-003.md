# Read-write data binding và cập nhật object

SpEL có thể đọc và cập nhật thuộc tính của một object thông qua EvaluationContext. Khi chỉ cần đọc dữ liệu, context có thể được cấu hình ở chế độ read-only. Khi cần ghi giá trị, SimpleEvaluationContext.forReadWriteDataBinding() cung cấp property accessor phục vụ truy cập đọc/ghi theo phạm vi giới hạn của data binding.

Cập nhật object bằng SpEL thường được thực hiện qua Expression.setValue(context, value) hoặc overload có root object. Cách này phù hợp khi ứng dụng đã xác định object đích và muốn dùng một property path trong biểu thức để đọc hoặc ghi một giá trị. Cần xác định rõ property nào được phép ghi, kiểu dữ liệu đích, trạng thái mutable của object và cách xử lý lỗi.

## 1. Read-write data binding trong SpEL

EvaluationContext kiểm soát cách SpEL truy cập property và các khả năng khác khi đánh giá biểu thức. SimpleEvaluationContext được thiết kế cho các use case data binding cần một tập tính năng giới hạn.

Có thể tạo context hỗ trợ đọc và ghi property:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

Context này cấu hình property accessor cho data binding theo chế độ read-write. Biểu thức có thể đọc property và ghi vào property có thể ghi thông qua accessor được cung cấp.

Nếu chỉ cần đọc:

~~~java
EvaluationContext readOnly =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Context read-only phù hợp với biểu thức hiển thị hoặc lọc dữ liệu. Context read-write dành cho tình huống cần cập nhật object. Hãy chọn đúng chế độ theo thao tác thực tế của biểu thức.

## 2. Đọc property từ root object

Khi tạo context, có thể cung cấp object làm root object. Biểu thức property không có tiền tố biến sẽ được phân giải trên root object đó.

Ví dụ:

~~~java
public class Profile {

    private String displayName;
    private int age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Đọc property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
profile.setDisplayName("Lan");
profile.setAge(25);

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression nameExpression =
        parser.parseExpression("displayName");

String name = nameExpression.getValue(
        context,
        profile,
        String.class
);
~~~

Overload getValue nhận context, root object và kiểu kết quả. Root object trong lần đánh giá này là profile. Có thể dùng cùng một Expression với các object khác nhau nếu property path của chúng tương thích.

## 3. Cập nhật property bằng Expression.setValue

Expression.setValue cho phép ghi giá trị vào property được chỉ định bởi biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile();
profile.setDisplayName("Lan");

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression nameExpression =
        parser.parseExpression("displayName");

nameExpression.setValue(context, profile, "Minh");

System.out.println(profile.getDisplayName()); // Minh
~~~

Biểu thức displayName xác định property đích. Giá trị mới được truyền riêng qua setValue. Cách viết này giữ dữ liệu đầu vào trong Java và để chuỗi SpEL chỉ mô tả đường dẫn property.

Nếu root object đã được gắn với StandardEvaluationContext hoặc một context thích hợp khác, có thể dùng overload setValue(context, value). Khi dùng SimpleEvaluationContext không gắn root object, hãy truyền root object cho overload tương ứng.

Việc parse biểu thức chưa làm thay đổi object. Thay đổi xảy ra khi setValue được gọi và property accessor thực hiện thao tác ghi.

## 4. Đọc lại giá trị sau khi cập nhật

Sau khi ghi, có thể dùng cùng Expression để đọc lại property:

~~~java
nameExpression.setValue(context, profile, "Minh");

String updatedName = nameExpression.getValue(
        context,
        profile,
        String.class
);

System.out.println(updatedName); // Minh
~~~

Đọc lại giúp ứng dụng lấy giá trị hiện tại từ object. Nếu property có setter chuẩn hóa dữ liệu hoặc có logic ở accessor, giá trị đọc lại có thể phản ánh trạng thái sau khi cập nhật.

Không nên giả định mọi setter đều chỉ gán trực tiếp. Setter có thể kiểm tra điều kiện, chuẩn hóa chuỗi, cập nhật property liên quan hoặc ném exception. Hãy thiết kế setter sao cho hành vi cập nhật rõ ràng và có thể kiểm thử trong Java.

## 5. Cập nhật property lồng nhau

Property path có thể đi qua nhiều object:

~~~text
address.city
customer.profile.displayName
settings.notification.emailEnabled
~~~

Ví dụ:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class Customer {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Cập nhật city:

~~~java
Customer customer = new Customer();
Address address = new Address();
customer.setAddress(address);

Expression cityExpression =
        parser.parseExpression("address.city");

cityExpression.setValue(context, customer, "Da Nang");
~~~

Các object trung gian trong đường dẫn phải tồn tại và có thể truy cập. Nếu customer.address là null, SpEL không tự tạo Address mới chỉ vì biểu thức yêu cầu ghi address.city. Ứng dụng cần khởi tạo object trung gian trước hoặc cập nhật toàn bộ object con bằng một thao tác riêng.

Với property path dài, hãy kiểm tra từng mắt xích để biết object nào có thể null và property nào có setter.

## 6. Ghi vào Map theo key

Indexer có thể dùng để cập nhật entry của Map nếu Map mutable và context cho phép thao tác ghi.

Ví dụ:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "light");

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression themeExpression =
        parser.parseExpression("#settings['theme']");

context.setVariable("settings", settings);

themeExpression.setValue(context, "dark");

System.out.println(settings.get("theme")); // dark
~~~

Indexer #settings['theme'] xác định value theo key theme. Khi key đã tồn tại, việc ghi cập nhật value của entry. Với Map mutable, có thể tạo entry mới bằng thao tác ghi vào key chưa có nếu implementation và property accessor hỗ trợ.

Map không thể sửa đổi hoặc Map được bọc trong một view chỉ đọc có thể từ chối thao tác. Khi ghi Map từ biểu thức, hãy xác định kiểu key, kiểu value và quyền mutable của Map.

Nếu key được tính từ biến, có thể dùng biểu thức động:

~~~text
#settings[#selectedKey]
~~~

Khi đó selectedKey phải được đăng ký trong context và có kiểu phù hợp với key của Map.

## 7. Cập nhật phần tử trong List hoặc array

Indexer theo vị trí có thể truy cập phần tử trong List hoặc array. Nếu phần tử là object có property ghi được, có thể kết hợp indexer với property path:

~~~text
items[0].name
addresses[1].city
~~~

Ví dụ:

~~~java
Expression firstName =
        parser.parseExpression("items[0].name");

firstName.setValue(context, rootObject, "New name");
~~~

Đường dẫn yêu cầu List có phần tử ở index tương ứng và phần tử đó có property name có thể ghi. Việc ghi vào index đã tồn tại khác với thao tác thêm phần tử mới vào List.

Indexer không tự mở rộng List để tạo các vị trí chưa tồn tại. Nếu index vượt phạm vi hoặc collection không hỗ trợ cập nhật, thao tác có thể thất bại. Hãy thêm hoặc thay đổi cấu trúc collection trong Java trước khi dùng SpEL để cập nhật một phần tử cụ thể.

Với array, kích thước cố định. Có thể cập nhật phần tử hiện có nếu kiểu component và quyền truy cập cho phép, nhưng không thể dùng indexer để tăng kích thước array.

## 8. Chuyển đổi kiểu khi ghi property

Property đích có thể có kiểu khác với object giá trị được truyền vào setValue. SpEL dùng TypeConverter của EvaluationContext để chuyển đổi nếu có converter phù hợp.

Ví dụ property age là Integer:

~~~java
public class Member {

    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Có thể ghi một giá trị String nếu TypeConverter hỗ trợ chuyển String sang Integer:

~~~java
Member member = new Member();

Expression ageExpression = parser.parseExpression("age");

ageExpression.setValue(context, member, "30");
~~~

Kết quả phụ thuộc converter được cấu hình và dữ liệu đầu vào. Chuỗi không phải số hợp lệ có thể gây lỗi chuyển đổi. Không nên dựa vào việc mọi kiểu đều tự động chuyển đổi.

Khi property có kiểu domain riêng, hãy cấu hình converter phù hợp hoặc chuyển đổi dữ liệu trong Java trước khi gọi setValue. Việc chuyển đổi kiểu không thay thế validation nghiệp vụ.

## 9. Cấu hình TypeConverter hoặc ConversionService

SimpleEvaluationContext.Builder cho phép cấu hình TypeConverter khi ứng dụng cần quy tắc chuyển đổi riêng.

Ví dụ sử dụng ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService)
                )
                .build();
~~~

Có thể đăng ký converter domain vào ConversionService trước khi tạo context. Khi SpEL ghi property, TypeConverter sẽ được dùng để chuyển giá trị sang kiểu đích nếu có converter phù hợp.

Hãy giữ converter tập trung vào chuyển đổi kiểu. Các quy tắc như tuổi phải dương, trạng thái được phép cập nhật hoặc giới hạn số tiền nên được kiểm tra ở validation hoặc service layer.

## 10. Property phải có khả năng ghi

Không phải mọi property đọc được đều có thể ghi. Để cập nhật thành công, property accessor phải tìm được cách ghi giá trị vào đích.

Các tình huống thường gặp:

- Property có getter và setter tương ứng.
- Property chỉ có getter nên chỉ đọc được.
- Setter không truy cập được với accessor hiện tại.
- Property là read-only hoặc được bảo vệ bởi cấu trúc object.
- Property path đi qua object trung gian null.
- Kiểu giá trị không thể chuyển sang kiểu property.

Ví dụ property chỉ có getter:

~~~java
public class ImmutableProfile {

    private final String name;

    public ImmutableProfile(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Biểu thức name có thể đọc giá trị, nhưng không có setter để cập nhật theo JavaBean property access thông thường. Với object bất biến, hãy tạo object mới bằng constructor, factory hoặc copy method trong Java thay vì cố ghi vào property.

## 11. Read-write context không có nghĩa là mọi hành động đều được phép

SimpleEvaluationContext.forReadWriteDataBinding() cung cấp khả năng đọc/ghi property theo một tập tính năng giới hạn. Nó không tự bật toàn bộ tính năng của StandardEvaluationContext.

SimpleEvaluationContext không hỗ trợ type reference T(...), constructor invocation, bean reference hoặc các tính năng method invocation rộng như context đầy đủ. Nếu use case cần những tính năng khác, hãy cân nhắc rõ phạm vi và cấu hình thay vì chuyển context một cách mặc định.

Read-write chỉ nói rằng property accessor được cấu hình cho phép ghi. Nó không có nghĩa mọi object hoặc mọi property trong ứng dụng đều nên được đưa vào context. Hãy cung cấp root object nhỏ và chỉ expose những dữ liệu mà biểu thức cần cập nhật.

## 12. Phân biệt cập nhật bằng SpEL với DataBinder của Spring

SpEL setValue ghi vào property path đã được chỉ định trong Expression. DataBinder hoặc WebDataBinder thực hiện quy trình binding dữ liệu đầu vào vào object theo tên field.

| Khía cạnh | SpEL read-write | DataBinder/WebDataBinder |
|---|---|---|
| Mục đích | Đọc hoặc ghi property theo biểu thức | Bind dữ liệu nguồn vào object |
| Đích cập nhật | Property path trong Expression | Field/property có tên trong dữ liệu binding |
| Kích hoạt | Gọi getValue hoặc setValue | Gọi quy trình bind của binder |
| Chuyển đổi kiểu | TypeConverter của EvaluationContext | ConversionService/property editor của binder |
| Validation | Không tự chạy validation | Có thể kết hợp Validator và Bean Validation |
| Lỗi | Exception trong lúc truy cập hoặc chuyển đổi | Có thể được ghi nhận trong BindingResult |
| Giới hạn field | Accessor và object được cấp cho context | Allowed/disallowed fields và cấu hình binder |

Nếu đang cập nhật một property cụ thể trong rule nội bộ, Expression.setValue có thể phù hợp. Nếu đang nhận form hoặc request data, DataBinder/WebDataBinder cung cấp quy trình binding và xử lý lỗi phù hợp hơn.

## 13. Kiểm soát field được phép cập nhật

Read-write context có thể ghi vào các property mà accessor cho phép trên object được cung cấp. Vì vậy, không nên đưa entity có nhiều trường nhạy cảm làm root object cho một biểu thức không đáng tin cậy.

Ví dụ một User có các property như displayName, role, enabled và accountBalance. Nếu biểu thức có thể ghi tùy ý, việc cấp cả User có thể cho phép thay đổi nhiều trường hơn use case dự định.

Một số nguyên tắc:

1. Dùng DTO hoặc command object chỉ chứa các property được phép cập nhật.
2. Không đưa entity hoặc object có nhiều trạng thái nội bộ vào context nếu không cần.
3. Chỉ dùng read-write context cho use case thực sự cần ghi.
4. Kiểm tra quyền cập nhật ở application/service layer.
5. Validate object sau khi cập nhật và trước khi lưu.
6. Không xem property accessor là cơ chế authorization nghiệp vụ.

Với dữ liệu từ người dùng, hãy kiểm soát cả property path mà họ được phép chọn. Không để người dùng tự do gửi tên property rồi dùng trực tiếp làm biểu thức ghi.

## 14. Cập nhật object có thể tạo side effect

Ghi property có thể gọi setter. Setter có thể thay đổi trạng thái khác, phát sinh event nội bộ hoặc ném exception. Nếu property path trỏ tới object được chia sẻ, thay đổi có thể được nhìn thấy từ nhiều nơi đang giữ cùng reference.

Hãy xác định rõ lifecycle của object trước khi cập nhật. Nếu object là dữ liệu tạm trong một request, cập nhật thường dễ kiểm soát hơn so với việc sửa một singleton hoặc object cache dùng chung.

Không nên dùng SpEL để thực hiện nhiều bước cập nhật nghiệp vụ phức tạp trong một biểu thức dài. Hãy chia thao tác thành các bước Java có tên rõ ràng để có thể kiểm soát transaction, authorization, validation và xử lý lỗi.

## 15. Xử lý lỗi khi đọc/ghi

Lỗi có thể xuất hiện ở nhiều bước:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy property | Sai tên hoặc object đích không có property | Kiểm tra property path và kiểu root object |
| Không thể ghi property | Property read-only hoặc không có setter phù hợp | Dùng writable property hoặc tạo object mới |
| Không thể đọc property | Accessor không hỗ trợ kiểu object hoặc property | Kiểm tra accessor và cấu hình context |
| Lỗi ở property lồng nhau | Object trung gian null | Khởi tạo object con trước khi cập nhật |
| Index ngoài phạm vi | List/array không có phần tử tại vị trí đó | Kiểm tra size và index trước khi ghi |
| Map từ chối cập nhật | Map immutable hoặc chỉ đọc | Dùng Map mutable nếu use case cần ghi |
| Conversion thất bại | Không có converter hoặc giá trị sai định dạng | Kiểm tra kiểu nguồn, kiểu đích và TypeConverter |
| Setter ném exception | Quy tắc trong setter từ chối giá trị | Xem cause gốc và kiểm tra invariant |
| Dữ liệu cập nhật nhưng không hợp lệ | Conversion thành công nhưng thiếu validation | Validate trước khi lưu |

ParseException thường chỉ ra lỗi cú pháp khi tạo Expression. EvaluationException hoặc SpelEvaluationException thường xuất hiện khi đánh giá, truy cập property, chuyển đổi hoặc ghi dữ liệu. Hãy tách hai giai đoạn khi chẩn đoán.

## 16. Ví dụ hoàn chỉnh: cập nhật object có kiểm soát

Ví dụ sau dùng một form object chỉ chứa các trường được phép cập nhật:

~~~java
public class ProfileForm {

    private String displayName;
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Tạo context và cập nhật:

~~~java
ExpressionParser parser = new SpelExpressionParser();

ProfileForm form = new ProfileForm();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();

Expression displayName =
        parser.parseExpression("displayName");

Expression age =
        parser.parseExpression("age");

displayName.setValue(context, form, "Lan Nguyen");
age.setValue(context, form, 30);

String savedName = displayName.getValue(
        context,
        form,
        String.class
);

Integer savedAge = age.getValue(
        context,
        form,
        Integer.class
);
~~~

Sau khi cập nhật, ứng dụng vẫn cần validate form theo quy tắc nghiệp vụ trước khi chuyển dữ liệu sang entity hoặc lưu database. Việc SpEL ghi được hai property chỉ xác nhận accessor và conversion đã thực hiện thao tác, không xác nhận toàn bộ object hợp lệ.

## 17. Ghi nhớ

SimpleEvaluationContext.forReadWriteDataBinding() tạo EvaluationContext với property access hỗ trợ đọc và ghi trong phạm vi data binding. Dùng Expression.setValue(context, rootObject, value) để cập nhật property path và getValue để đọc lại. Có thể cập nhật property lồng nhau, Map entry hoặc phần tử collection nếu object trung gian tồn tại, đích mutable và accessor hỗ trợ.

Việc ghi có thể cần TypeConverter để chuyển giá trị sang kiểu property. Property chỉ đọc, object trung gian null, index ngoài phạm vi hoặc collection bất biến đều có thể làm thao tác thất bại. Conversion không thay thế validation.

Read-write context không tự cung cấp toàn bộ khả năng của StandardEvaluationContext và không thay thế DataBinder/WebDataBinder. Hãy giới hạn object và property được expose, kiểm tra quyền ở service layer, validate sau cập nhật và xử lý lỗi tại ranh giới phù hợp.