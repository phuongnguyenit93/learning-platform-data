# SpEL trong binding property của object

## 1. Binding property bằng SpEL là gì?

Spring Expression Language (SpEL) không chỉ đọc property của object mà còn có thể ghi giá trị vào property nếu property accessor cho phép ghi.

Ví dụ, với một object Customer có property name:

    ExpressionParser parser = new SpelExpressionParser();

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(customer, "Lan");

Sau khi expression được đánh giá, property name của customer nhận giá trị Lan.

SpEL có thể thực hiện việc này thông qua API setValue hoặc toán tử assignment trong expression. Cách dùng setValue thường rõ ràng hơn khi giá trị mới đến từ Java code.

Cần phân biệt hai hoạt động:

- **Property access để đọc:** lấy giá trị từ object, ví dụ name hoặc address.city.
- **Property binding để ghi:** cập nhật giá trị vào object, ví dụ setValue(..., "Lan").

Việc ghi phụ thuộc vào PropertyAccessor, khả năng writable của property và chuyển đổi kiểu dữ liệu.

## 2. Property expression và root object

Khi expression không có prefix # hoặc @, SpEL thường giải quyết tên property tương đối với root object.

Ví dụ:

    public class Customer {
        private String name;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

Thiết lập root object:

    Customer customer = new Customer();

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("name");

Đọc property:

    String currentName =
        expression.getValue(context, String.class);

Ghi property:

    expression.setValue(context, "Lan");

    // customer.getName() == "Lan"

Ở đây name là property của root object customer. Không cần viết #customer vì object đã được đặt làm root.

Cũng có thể truyền root object trực tiếp vào overload của Expression:

    Expression expression =
        parser.parseExpression("name");

    expression.setValue(context, customer, "Lan");

Cách này hữu ích khi cùng một expression được sử dụng trên nhiều object khác nhau.

## 3. Ghi property bằng Expression.setValue

API setValue là cách trực tiếp để gán một giá trị vào property expression.

Cú pháp:

    expression.setValue(context, rootObject, newValue);

Hoặc khi context đã có root object:

    expression.setValue(context, newValue);

Ví dụ:

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        context,
        customer,
        "Da Nang"
    );

SpEL thực hiện việc truy cập property theo đường dẫn và ghi giá trị vào property cuối cùng.

Có thể kiểm tra property có writable trước khi gán:

    if (cityExpression.isWritable(context, customer)) {
        cityExpression.setValue(
            context,
            customer,
            "Da Nang"
        );
    }

isWritable giúp xác định expression có thể ghi vào target theo accessor hiện tại hay không. Nó không thay thế validation dữ liệu, kiểm tra quy tắc nghiệp vụ hoặc xử lý lỗi chuyển đổi kiểu khi setValue thực sự chạy.

Nếu property không thể ghi, SpEL có thể phát sinh EvaluationException hoặc exception chuyên biệt của quá trình truy cập property.

## 4. Điều kiện để property có thể được ghi

Một property chỉ có thể được cập nhật nếu PropertyAccessor hiện tại hỗ trợ thao tác write trên target đó.

Với JavaBean thông thường, property thường có getter và setter:

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

Trong reflective property access, SpEL có thể nhận diện property qua getter/setter và các public field được hỗ trợ.

Những trường hợp có thể không ghi được:

- Property chỉ có getter và không có setter phù hợp.
- Property là immutable hoặc không có cơ chế ghi được accessor hỗ trợ.
- PropertyAccessor hiện tại chỉ cho phép đọc.
- Target object không đúng kiểu mà accessor hỗ trợ.
- Giá trị mới không chuyển đổi được sang kiểu property.
- Object trung gian trong đường dẫn là null.

Không nên suy luận rằng đọc được một property thì chắc chắn ghi được property đó. Read và write là hai khả năng riêng.

## 5. Binding property lồng nhau

SpEL hỗ trợ đường dẫn property nhiều cấp bằng dấu chấm.

Ví dụ object model:

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

Nếu customer đã có address, có thể ghi city:

    Expression cityExpression =
        parser.parseExpression("address.city");

    cityExpression.setValue(
        context,
        customer,
        "Da Nang"
    );

Đường dẫn address.city có nghĩa:

1. Đọc property address trên Customer.
2. Lấy object Address được trả về.
3. Ghi property city trên object Address đó.

Mỗi bước trung gian phải trả về object phù hợp để bước tiếp theo được thực hiện.

## 6. Xử lý object trung gian null

Nếu address đang null, SpEL không có object Address để ghi city theo đường dẫn thông thường.

Ví dụ:

    Customer customer = new Customer();
    customer.setAddress(null);

    Expression expression =
        parser.parseExpression("address.city");

    expression.setValue(
        new StandardEvaluationContext(customer),
        "Da Nang"
    );

Trong cấu hình mặc định, thao tác này có thể thất bại vì address là null.

Có hai hướng xử lý:

**Khởi tạo object trước khi binding:**

    customer.setAddress(new Address());

    expression.setValue(
        new StandardEvaluationContext(customer),
        "Da Nang"
    );

**Cấu hình SpEL auto-grow null references:**

    SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

    ExpressionParser parser =
        new SpelExpressionParser(configuration);

Cấu hình trên bật tự khởi tạo null references và tự mở rộng collection theo khả năng SpEL hỗ trợ. Khi bật, SpEL có thể tạo object trung gian nếu kiểu property có thể được khởi tạo phù hợp.

Auto-grow không phải phép màu tạo được mọi object. Kiểu dữ liệu cần có cách khởi tạo phù hợp, và việc tạo object có thể có tác dụng phụ. Hãy bật rõ ràng khi cần, đồng thời kiểm soát index và kích thước collection nếu dữ liệu đầu vào có thể thay đổi.

Không nhầm auto-grow của SpEL với auto-grow của DataBinder. Đây là hai cơ chế cấu hình độc lập.

## 7. Binding phần tử List và Map

Indexer cho phép ghi vào phần tử collection hoặc Map.

Ví dụ với List:

    public class Customer {
        private List<String> tags =
            new ArrayList<>();

        public List<String> getTags() {
            return tags;
        }

        public void setTags(List<String> tags) {
            this.tags = tags;
        }
    }

Ghi phần tử đầu tiên:

    Expression tagExpression =
        parser.parseExpression("tags[0]");

    tagExpression.setValue(
        context,
        customer,
        "premium"
    );

Ví dụ với Map:

    Expression themeExpression =
        parser.parseExpression("preferences['theme']");

    themeExpression.setValue(
        context,
        customer,
        "dark"
    );

Các đường dẫn lồng nhau cũng có thể kết hợp indexer:

    addresses[0].city
    attributes['displayName']

Target collection hoặc Map phải tồn tại và thao tác index/key phải phù hợp với dữ liệu thực tế, trừ khi parser được cấu hình auto-grow cho trường hợp được hỗ trợ.

Với List hoặc array, index bắt đầu từ 0. Với Map, giá trị trong ngoặc vuông là key.

## 8. Chuyển đổi kiểu khi binding

Giá trị mới không nhất thiết có cùng kiểu Java với property đích. SpEL sử dụng TypeConverter trong EvaluationContext để chuyển đổi khi có thể.

Ví dụ property boolean nằm trong List:

    public class Preferences {
        public List<Boolean> flags =
            new ArrayList<>();
    }

    Preferences preferences = new Preferences();
    preferences.flags.add(true);

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    parser.parseExpression("flags[0]")
        .setValue(context, preferences, "false");

Giá trị String "false" được chuyển thành Boolean false thông qua conversion service của Spring.

SpEL cũng nhận biết generic type trong những trường hợp phù hợp. Nếu property là List<Boolean>, conversion service có thể chuyển từng giá trị đầu vào sang Boolean để giữ đúng kiểu phần tử.

Nếu conversion không được hỗ trợ hoặc dữ liệu sai định dạng, evaluation có thể thất bại.

Không nên dựa vào chuyển đổi ngầm mà chưa xác định format, locale và miền giá trị. Với dữ liệu từ form hoặc API, hãy kiểm tra dữ liệu đầu vào trước khi binding.

## 9. SimpleEvaluationContext cho data binding

Nếu use case chỉ cần đọc hoặc ghi property dữ liệu, không cần toàn bộ khả năng của SpEL, có thể dùng SimpleEvaluationContext.

Đọc property:

    SimpleEvaluationContext readOnlyContext =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

Ghi property:

    SimpleEvaluationContext readWriteContext =
        SimpleEvaluationContext
            .forReadWriteDataBinding()
            .build();

Ví dụ:

    Customer customer = new Customer();

    Expression nameExpression =
        parser.parseExpression("name");

    nameExpression.setValue(
        readWriteContext,
        customer,
        "Lan"
    );

forReadWriteDataBinding() bật khả năng đọc và ghi property thông qua DataBindingPropertyAccessor.

SimpleEvaluationContext chỉ cung cấp một tập tính năng SpEL giới hạn. Nó không hỗ trợ type references, constructor invocation hoặc bean references như StandardEvaluationContext.

Nếu mục tiêu là property binding trên object dữ liệu, đây thường là lựa chọn phù hợp hơn context đầy đủ. Tuy nhiên, nó không tự bảo đảm an toàn cho mọi expression hoặc mọi object được expose. Getter, setter và custom accessor vẫn có thể có tác dụng phụ.

## 10. Phân biệt SpEL binding với Spring DataBinder

Một điểm rất dễ nhầm: Spring DataBinder không phải là SpEL parser.

Hai cơ chế đều có thể ghi property vào object, nhưng cách hoạt động khác nhau.

| Tiêu chí | SpEL Expression.setValue | Spring DataBinder |
| --- | --- | --- |
| Đầu vào | Expression string và giá trị mới | PropertyValues hoặc dữ liệu binding |
| Cú pháp | SpEL property expression | Property path theo JavaBeans |
| Ví dụ | address.city | address.city |
| Thực thi | Expression và EvaluationContext | DataBinder cùng BeanWrapper/property access |
| Chuyển đổi kiểu | TypeConverter trong EvaluationContext | ConversionService/PropertyEditor của binding |
| Mục đích | Đánh giá expression và đọc/ghi theo expression | Bind dữ liệu đầu vào vào target object |
| Validation | Không tự chạy validation nghiệp vụ | Có thể tích hợp Validator và BindingResult |

Cú pháp address.city trông giống nhau, nhưng không có nghĩa DataBinder đánh giá toàn bộ ngôn ngữ SpEL.

DataBinder xử lý property paths theo quy ước JavaBeans. Nó không tự hiểu các cú pháp SpEL như:

    #customer.name
    @pricingService
    name ?: 'Guest'
    new com.example.Customer()

Nếu ứng dụng nhận dữ liệu form hoặc request từ người dùng và muốn cập nhật DTO, DataBinder thường là công cụ phù hợp hơn việc tự parse chuỗi expression.

## 11. Ví dụ sử dụng DataBinder cho object

Giả sử form object:

    public class CustomerForm {
        private String displayName;
        private Address address;

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

Có thể bind property values:

    CustomerForm form = new CustomerForm();

    DataBinder binder = new DataBinder(form);

    binder.setAllowedFields(
        "displayName",
        "address.city"
    );

    MutablePropertyValues values =
        new MutablePropertyValues();

    values.add("displayName", "Lan");
    values.add("address.city", "Da Nang");

    binder.bind(values);

    BindingResult result =
        binder.getBindingResult();

Trong ví dụ này, DataBinder nhận property paths và giá trị tương ứng. Nó sử dụng cơ chế property binding của Spring để cập nhật object.

Với standard DataBinder, auto-grow nested paths được bật mặc định trong các cấu hình thông thường; có thể thay đổi bằng setAutoGrowNestedPaths(false). Auto-grow collection cũng có giới hạn cấu hình để tránh tạo collection quá lớn từ index đầu vào.

Nếu cần kiểm tra lỗi binding, hãy đọc BindingResult. Binding error và validation error có thể được xử lý trước khi lưu object.

## 12. Giới hạn field được phép binding

Khi binding dữ liệu từ request không tin cậy, không nên cho phép người dùng cập nhật mọi property của một entity lớn.

Ví dụ entity có thể chứa:

- id hoặc ownerId.
- role và quyền quản trị.
- trạng thái thanh toán.
- thông tin nội bộ.
- quan hệ tới object khác.
- audit field như createdBy hoặc approvedBy.

Nếu bind toàn bộ property paths mà không giới hạn, người dùng có thể gửi thêm field ngoài form dự kiến. Đây là nhóm rủi ro mass assignment hoặc over-posting.

Với DataBinder, khai báo allow-list:

    binder.setAllowedFields(
        "displayName",
        "address.city"
    );

Chỉ các property paths được cho phép mới được bind.

Với SpEL, hãy giữ expression property path do ứng dụng kiểm soát:

    Expression expression =
        parser.parseExpression("displayName");

Không lấy nguyên chuỗi expression tùy ý do người dùng gửi lên rồi parse và evaluate.

Nếu cần chọn field động, ánh xạ tên field bên ngoài sang một danh sách expression đã được định nghĩa trước:

    Map<String, Expression> writableProperties = ...;

Sau đó chỉ lấy expression từ allow-list của ứng dụng, không parse trực tiếp chuỗi bất kỳ từ request.

## 13. Validation sau khi binding

Binding chỉ là bước chuyển giá trị đầu vào vào object. Nó không chứng minh dữ liệu hợp lệ về nghiệp vụ.

Ví dụ:

    age = -10

Có thể gán thành công vào property kiểu int, nhưng vẫn sai quy tắc nghiệp vụ.

Tương tự:

    email = 'not-an-email'

Có thể ghi thành công vào String property nhưng không phải địa chỉ email hợp lệ.

Sau khi binding, hãy thực hiện validation:

- Kiểm tra required field.
- Kiểm tra miền giá trị và giới hạn số.
- Kiểm tra định dạng email, số điện thoại hoặc mã.
- Kiểm tra quan hệ giữa các field.
- Kiểm tra quyền cập nhật object theo người dùng hiện tại.
- Kiểm tra trạng thái nghiệp vụ trước khi lưu.

DataBinder có thể tích hợp Validator và trả lỗi qua BindingResult. Với SpEL setValue, ứng dụng cần gọi Validator hoặc logic kiểm tra riêng sau khi cập nhật object.

Không nên coi việc setValue thành công là validation pass.

## 14. Binding có tác dụng phụ

setValue cập nhật object ngay khi được gọi. Nếu setter có logic bổ sung, logic đó cũng có thể chạy.

Ví dụ setter có thể:

- Chuẩn hóa dữ liệu.
- Cập nhật field khác.
- Ghi audit.
- Gọi callback.
- Thực hiện kiểm tra hoặc tương tác ngoài dự kiến.

Nếu expression thực hiện nhiều phép gán, một phép gán có thể đã thay đổi object trước khi phép tiếp theo thất bại. SpEL không tự tạo transaction hoặc rollback cho chuỗi assignment.

Với dữ liệu nghiệp vụ quan trọng, hãy cân nhắc:

- Bind vào DTO trung gian.
- Validate toàn bộ DTO.
- Chuyển dữ liệu hợp lệ qua service.
- Cập nhật entity trong transaction.
- Ghi audit và áp dụng quyền ở tầng nghiệp vụ.

Không nên dùng expression để thay thế một quy trình cập nhật nghiệp vụ phức tạp.

## 15. Phân biệt property path với expression do người dùng nhập

Một property path như:

    address.city

chỉ xác định vị trí property cần đọc hoặc ghi.

Một SpEL expression có thể làm nhiều hơn:

    #customer.address.city = #newCity

    @customerService.update(#customerId, #newCity)

    new com.example.Address()

Vì vậy, nếu người dùng chỉ cần chọn field cần cập nhật, hãy nhận property identifier hoặc form field theo một allow-list. Đừng yêu cầu họ gửi một SpEL expression tổng quát.

Đối với dữ liệu không tin cậy:

- Không parse và evaluate expression tùy ý.
- Không expose service, bean hoặc object có quyền rộng.
- Không cho phép method invocation hoặc constructor nếu use case không cần.
- Dùng DTO chỉ chứa các property có thể bind.
- Dùng allowedFields trong DataBinder.
- Giới hạn nested path và auto-grow collection.
- Kiểm tra kiểu dữ liệu, validation và quyền cập nhật.

SimpleEvaluationContext có thể giới hạn tính năng so với StandardEvaluationContext, nhưng không nên xem nó là ranh giới bảo mật tuyệt đối.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Property không writable | Không có setter hoặc accessor chỉ đọc | Kiểm tra setter và PropertyAccessor |
| Nested path thất bại | Object trung gian null | Khởi tạo object hoặc cấu hình auto-grow có kiểm soát |
| Index vượt giới hạn | List/array không có phần tử tương ứng | Kiểm tra index hoặc giới hạn auto-grow |
| Conversion error | Giá trị không chuyển đổi được sang kiểu property | Kiểm tra TypeConverter và định dạng đầu vào |
| SimpleEvaluationContext từ chối ghi | Dùng read-only builder | Chọn forReadWriteDataBinding() nếu cần ghi |
| Bean hoặc constructor expression không hoạt động | SimpleEvaluationContext không hỗ trợ các tính năng đầy đủ đó | Chỉ dùng context đầy đủ khi use case tin cậy và cần thiết |
| DataBinder không hiểu #variable hoặc @bean | DataBinder xử lý property path, không parse SpEL | Dùng đúng API cho đúng loại expression |
| Field ngoài dự kiến bị cập nhật | Binding không có allow-list | Cấu hình setAllowedFields và DTO hẹp |
| Binding thành công nhưng dữ liệu sai nghiệp vụ | Chưa chạy validation | Validate sau khi bind |
| Object thay đổi một phần khi lỗi | Assignment đã thực hiện trước khi bước sau thất bại | Bind vào DTO trung gian và cập nhật có kiểm soát |

Khi debug, xác định lỗi thuộc bước nào:

1. Parse expression.
2. Kiểm tra writable property.
3. Truy cập root object và nested object.
4. Chuyển đổi kiểu.
5. Ghi giá trị.
6. Validate object sau binding.

Nếu dùng DataBinder, kiểm tra BindingResult và property paths được phép thay vì tìm lỗi trong SpEL parser.

## 17. Những điểm cần nhớ

- SpEL có thể ghi property thông qua Expression.setValue().
- Property expression được giải quyết tương đối với root object hoặc object được tham chiếu qua variable.
- Có thể kiểm tra isWritable() trước khi ghi.
- PropertyAccessor phải hỗ trợ write; đọc được property không đồng nghĩa ghi được.
- Nested property, List index và Map key có thể được dùng làm đường dẫn ghi.
- Object trung gian null cần được khởi tạo hoặc cấu hình auto-grow phù hợp.
- TypeConverter của EvaluationContext hỗ trợ chuyển đổi giá trị khi có thể.
- SimpleEvaluationContext.forReadWriteDataBinding() cho phép read/write property với tập tính năng giới hạn.
- Spring DataBinder là cơ chế property binding riêng, không phải SpEL parser.
- DataBinder dùng property paths theo JavaBeans và có thể giới hạn bằng setAllowedFields().
- Binding không thay thế validation nghiệp vụ.
- Không parse expression tùy ý do người dùng cung cấp; dùng DTO, allow-list và context có phạm vi quyền hẹp.
- setValue làm thay đổi object ngay lập tức và không tự cung cấp transaction hoặc rollback.

Khi cần ghi property bằng SpEL, hãy dùng expression do ứng dụng kiểm soát, chọn đúng EvaluationContext và kiểm tra writable, conversion cùng object trung gian. Khi mục tiêu là bind form hoặc request vào DTO, hãy dùng DataBinder với allow-list và validation. Hai cách có thể cùng thao tác trên JavaBean nhưng phục vụ hai loại luồng dữ liệu khác nhau.

## Tài liệu tham khảo

- Spring Framework Reference — Evaluation and Expression.setValue: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Reference — Model Design and Allowed Fields: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html
- Spring Framework Javadoc — DataBindingPropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html
