# #root và object gốc của phép đánh giá

Trong SpEL, object gốc là đối tượng mà biểu thức bắt đầu đọc dữ liệu hoặc gọi method khi được đánh giá. SpEL cung cấp biến đặc biệt #root để tham chiếu object gốc này ở bất kỳ vị trí nào trong biểu thức. Biến #this đại diện cho đối tượng đang được đánh giá tại vị trí hiện tại và có thể thay đổi khi biểu thức đi vào một collection operation như selection hoặc projection.

Hiểu rõ sự khác nhau giữa #root và #this giúp biểu thức truy cập đúng dữ liệu, nhất là khi làm việc với object lồng nhau, collection, method call và nhiều cấp xử lý. Đồng thời, cần phân biệt object gốc với các biến được đăng ký trong EvaluationContext: root object là đối tượng nền của lượt đánh giá, còn context variables là dữ liệu được tham chiếu bằng tên biến có tiền tố #.

## 1. Object gốc là gì?

Khi tạo EvaluationContext, ứng dụng có thể cung cấp một object làm root object. Nếu biểu thức dùng property hoặc method mà không có tiền tố biến, SpEL sẽ tìm chúng trên object hiện tại, thường là root object ở đầu lượt đánh giá.

Ví dụ, lớp Customer:

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

Có thể đặt một Customer làm root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);

System.out.println(name); // Lan
~~~

Trong ví dụ này, biểu thức name được phân giải trên root object customer. Không cần viết customer.name vì customer đã là object gốc của context.

Root object có thể là một domain object, DTO, Map, collection hoặc một object khác mà ứng dụng muốn biểu thức làm việc cùng. Hãy chọn object có phạm vi dữ liệu vừa đủ cho biểu thức.

## 2. Tham chiếu tường minh bằng #root

Biến #root luôn trỏ đến root object của lượt đánh giá. Có thể dùng nó để viết rõ nguồn dữ liệu, ngay cả khi biểu thức đang ở trong một ngữ cảnh lồng nhau.

~~~text
#root.name
#root.age
#root.isAdult()
~~~

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "#root.name + ' (' + #root.age + ')'"
);

String description = expression.getValue(context, String.class);
~~~

Kết quả là chuỗi mô tả được tạo từ các thuộc tính của root object.

Trong biểu thức đơn giản chỉ làm việc với root object, name và #root.name thường cùng tham chiếu một property. Viết #root tường minh có ích khi biểu thức có nhiều object, nhiều collection operation hoặc tên property trùng nhau và cần chỉ rõ dữ liệu nào thuộc object gốc.

#root là một biến đặc biệt do SpEL cung cấp, không cần gọi setVariable("root", ...). Không nên tự tạo một context variable tên root để thay thế biến đặc biệt này.

## 3. Khác biệt giữa #root và #this

Hai biến đặc biệt này có mục đích khác nhau:

| Biến | Ý nghĩa | Phạm vi |
|---|---|---|
| #root | Object gốc của lượt đánh giá | Giữ tham chiếu tới root object |
| #this | Object đang được đánh giá tại vị trí hiện tại | Có thể thay đổi trong biểu thức lồng nhau |

Ở đầu biểu thức, khi chưa chuyển sang một ngữ cảnh đánh giá collection hoặc một object khác, #this thường trỏ tới cùng object với #root.

Ví dụ:

~~~text
#root.name
#this.name
name
~~~

Nếu root object là Customer, ba cách trên đều có thể đọc property name trong ngữ cảnh ban đầu.

Sự khác biệt trở nên rõ ràng khi SpEL đánh giá từng phần tử của collection. Trong predicate của selection hoặc biểu thức projection, #this là phần tử hiện tại, còn #root vẫn là object gốc ban đầu.

## 4. #this thay đổi trong selection

Giả sử root object là một Department có danh sách Employee và một mã phòng ban:

~~~java
public class Department {

    private final String code;
    private final List<Employee> employees;

    public Department(String code, List<Employee> employees) {
        this.code = code;
        this.employees = employees;
    }

    public String getCode() {
        return code;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}
~~~

Có thể lọc nhân viên theo mã phòng ban gốc:

~~~text
employees.?[#this.departmentCode == #root.code]
~~~

Trong predicate:

- #this là Employee đang được kiểm tra.
- #root là Department ban đầu.
- #this.departmentCode đọc mã phòng ban trên nhân viên hiện tại.
- #root.code đọc mã phòng ban trên object gốc.

Ví dụ Java:

~~~java
Expression expression = parser.parseExpression(
        "employees.?[#this.departmentCode == #root.code]"
);

List<?> result = expression.getValue(context, List.class);
~~~

Nếu viết #root.departmentCode bên trong predicate, biểu thức sẽ tìm property departmentCode trên Department, không phải trên Employee. Đây là lỗi thường gặp khi nhầm object gốc với phần tử hiện tại.

Khi predicate chỉ có một collection và không có tên property trùng nhau, có thể bỏ #this và viết trực tiếp departmentCode. Dùng #this tường minh giúp biểu thức dễ đọc hơn khi có nhiều cấp dữ liệu.

## 5. #this trong projection

Projection dùng toán tử .![...] để tạo collection kết quả từ từng phần tử của collection nguồn. Trong biểu thức projection, #this là phần tử hiện tại đang được chuyển đổi.

Ví dụ:

~~~text
employees.![#this.name]
~~~

Mỗi Employee được thay bằng giá trị name tương ứng. #root vẫn giữ tham chiếu tới Department ban đầu.

Có thể kết hợp dữ liệu của phần tử hiện tại với dữ liệu của root object:

~~~text
employees.![#root.code + '-' + #this.name]
~~~

Kết quả là danh sách chuỗi gồm mã phòng ban và tên từng nhân viên.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "employees.![#root.code + '-' + #this.name]"
);

List<?> labels = expression.getValue(context, List.class);
~~~

Cách viết này hữu ích khi kết quả projection cần ghép dữ liệu của phần tử với metadata của object gốc. Nếu biểu thức chỉ cần property của phần tử hiện tại, #this giúp thể hiện rõ rằng giá trị được lấy từ từng phần tử.

## 6. Root object và context variables là hai nguồn khác nhau

EvaluationContext có thể chứa root object và các biến riêng. Cú pháp truy cập khác nhau:

- Property trên root object: name hoặc #root.name.
- Context variable: #currentUser, #minimumAge hoặc #settings.
- Property của biến object: #currentUser.name.

Ví dụ:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("label", "Customer");

Expression expression = parser.parseExpression(
        "#root.age >= #minimumAge and #root.name != null"
);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Ở đây customer là root object. minimumAge và label là context variables được đăng ký riêng.

Không nên nhầm tên property với tên biến. Viết age truy cập property age trên object hiện tại; viết #age tham chiếu biến tên age trong context. Nếu chưa đăng ký biến age, biểu thức #age không tự động đọc property age của root object.

Có thể đặt một object làm biến mà không thay đổi root object:

~~~java
context.setVariable("reviewer", anotherCustomer);
~~~

Sau đó biểu thức có thể so sánh #root.name với #reviewer.name. Cách này giúp biểu thức làm việc với nhiều object nhưng vẫn giữ một root object rõ ràng.

## 7. Chọn root object khi gọi getValue

Có thể cung cấp root object ngay khi tạo context:

~~~java
EvaluationContext context =
        new StandardEvaluationContext(customer);
~~~

Cũng có thể truyền root object cho từng lần đánh giá thông qua overload của Expression:

~~~java
Expression expression = parser.parseExpression("name");

String first = expression.getValue(
        context,
        customer,
        String.class
);

String second = expression.getValue(
        context,
        anotherCustomer,
        String.class
);
~~~

Overload có root object cho phép tái sử dụng một Expression với các root object khác nhau. Root object được truyền cho lần gọi getValue đó là object gốc của lượt đánh giá tương ứng.

Cách này hữu ích khi biểu thức có cùng cấu trúc nhưng cần chạy trên nhiều bản ghi. Hãy bảo đảm mỗi lượt đánh giá nhận đúng object và context variables tương ứng.

Nếu context giữ biến phụ thuộc vào một root object cụ thể, khi thay root object cần cập nhật những biến liên quan để tránh dùng dữ liệu không đồng bộ.

## 8. Thay đổi root object trong EvaluationContext

Với StandardEvaluationContext, có thể đặt hoặc thay root object bằng API tương ứng:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);
~~~

Sau đó, các biểu thức không có tiền tố biến sẽ được phân giải trên customer và #root cũng trỏ tới customer.

Có thể thay root object khi cần dùng lại context theo một luồng tuần tự:

~~~java
context.setRootObject(anotherCustomer);
~~~

Tuy nhiên, không nên chia sẻ cùng một context mutable giữa nhiều request hoặc nhiều luồng nếu root object và variables có thể thay đổi. Một lượt đánh giá có thể nhìn thấy root object của lượt khác nếu context bị cập nhật đồng thời.

Thông thường, tạo context riêng cho từng lượt xử lý hoặc từng request giúp ranh giới dữ liệu rõ ràng và dễ kiểm soát hơn.

## 9. Root object có thể là Map hoặc collection

Root object không bắt buộc phải là một JavaBean. Nếu root là Map, có thể truy cập key trực tiếp hoặc thông qua #root:

~~~java
Map<String, Object> data = new HashMap<>();
data.put("name", "Lan");
data.put("active", true);

StandardEvaluationContext context =
        new StandardEvaluationContext(data);
~~~

Các biểu thức:

~~~text
name
#root['name']
#root['active']
~~~

đều truy cập dữ liệu từ Map gốc theo cách phù hợp với property/indexer resolution.

Nếu root object là List, có thể dùng indexer hoặc collection operation:

~~~text
#root[0]
#root.?[#this != null]
~~~

Trong selection trên root List, #this là phần tử hiện tại, còn #root vẫn là List gốc.

Hãy xác định kiểu root object trước khi viết biểu thức. Cú pháp truy cập property, key hoặc index phụ thuộc vào kiểu object và property accessor mà EvaluationContext cung cấp.

## 10. Root object trong biểu thức lồng nhau

Một biểu thức có thể đi qua nhiều cấp property hoặc collection. Khi đó, #this phản ánh object đang được đánh giá ở cấp hiện tại, còn #root tiếp tục tham chiếu object ban đầu.

Ví dụ root object là Company, chứa departments và mỗi Department chứa employees:

~~~text
departments.?[
    #this.employees.?[
        #this.active and #root.name == 'Acme'
    ].size() > 0
]
~~~

Trong selection ngoài, #this là Department. Trong selection bên trong, #this là Employee đang xét. #root vẫn là Company ban đầu.

Biểu thức lồng nhau có thể khó đọc vì cùng một biến #this thay đổi theo từng cấp. Hãy dùng #root khi cần truy cập dữ liệu gốc, và dùng #this tường minh tại những nơi có thể nhầm cấp object.

Nếu logic quá sâu, hãy chuyển một phần điều kiện thành method thuần có tên mô tả rõ ý nghĩa hoặc chuẩn bị dữ liệu trước khi đánh giá.

## 11. Root object không phải BeanResolver hoặc bean trong Spring

Root object là đối tượng được đặt làm nền cho một lượt đánh giá. Nó không đồng nghĩa với Spring bean và cũng không tự động cho phép truy cập mọi bean trong ApplicationContext.

Muốn gọi bean theo tên trong SpEL, EvaluationContext cần có BeanResolver phù hợp. Ví dụ, một context thủ công có thể được cấu hình bằng BeanFactoryResolver:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

Sau khi có resolver, biểu thức có thể tham chiếu bean bằng cú pháp @beanName. Đây là cơ chế riêng với việc truy cập root object bằng #root.

Tương tự, method trên root object có thể được gọi theo tên method, còn method trên bean cần được phân giải thông qua bean resolver và object bean tương ứng.

Hãy phân biệt rõ root object, context variables và Spring beans để tránh đưa quá nhiều object vào context hoặc giả định rằng một object đã là root thì mọi bean khác cũng tự truy cập được.

## 12. Null và root object

Nếu root object là null, những biểu thức đọc property hoặc gọi method trên root có thể thất bại khi đánh giá:

~~~text
#root.name
isActive()
~~~

Hãy kiểm tra root object trước khi đánh giá hoặc chuẩn hóa dữ liệu đầu vào. Có thể dùng API Java để xác nhận object không null trước khi gọi getValue.

Với một biến context có thể null, có thể kiểm tra riêng:

~~~text
#reviewer == null
#reviewer != null and #reviewer.active
~~~

Không nên nhầm #root == null với việc một property trên root có giá trị null. Root object có thể tồn tại trong khi một hoặc nhiều property của nó là null.

Trong collection operation, phần tử hiện tại #this cũng có thể null. Hãy kiểm tra #this trước khi truy cập property của phần tử.

## 13. Tác dụng phụ và phạm vi truy cập

Root object xác định phần dữ liệu và hành vi mà biểu thức có thể tiếp cận. Nếu root object là một service hoặc object có nhiều method thay đổi trạng thái, biểu thức có thể thực hiện các hành động vượt xa một phép đọc dữ liệu đơn giản.

Một số nguyên tắc thực hành:

1. Chọn root object nhỏ, chỉ chứa dữ liệu cần thiết.
2. Dùng DTO hoặc projection object cho biểu thức chỉ đọc.
3. Đưa dữ liệu bổ sung qua context variables có tên rõ ràng.
4. Tránh đặt repository, payment service hoặc object có quyền ghi rộng làm root nếu không cần.
5. Giữ method được gọi từ biểu thức thuần và ít side effect.
6. Tạo context riêng cho từng lượt đánh giá nếu root object hoặc variables thay đổi.
7. Không dựa vào #root để kiểm soát authorization; kiểm tra quyền trong application/service layer.

Nếu biểu thức đến từ nguồn không đáng tin cậy, hãy giới hạn PropertyAccessor, MethodResolver, TypeLocator, BeanResolver và những khả năng khác mà context cung cấp. Chỉ thay đổi root object không phải là một sandbox bảo mật.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Property không được tìm thấy | Root object không có property đó hoặc context dùng root khác | Kiểm tra object được truyền vào getValue |
| #root trả về object không mong đợi | Overload getValue đã nhận root object khác | Kiểm tra root object của từng lần đánh giá |
| #this thay đổi trong predicate | #this là phần tử hiện tại của collection operation | Dùng #root để tham chiếu object gốc |
| #variable không đọc được property root | Nhầm context variable với property trên root | Dùng tên property hoặc #root.property |
| Biến có giá trị cũ sau khi đổi root | Context variable không được cập nhật theo root mới | Cập nhật variables liên quan hoặc tạo context mới |
| Gọi method trên root bị lỗi | Method không tồn tại, không truy cập được hoặc resolver không phù hợp | Kiểm tra object, method và MethodResolver |
| Truy cập bean bằng @name thất bại | Context chưa có BeanResolver | Cấu hình resolver phù hợp nếu use case cần |
| Lỗi khi truy cập sâu | Root, property trung gian hoặc #this là null | Kiểm tra null trước khi đọc tiếp |

Khi debug, hãy xác nhận root object thực tế, sau đó kiểm tra riêng giá trị của #root, #this và các biến đã đăng ký. Có thể đánh giá từng phần nhỏ trước khi ghép thành biểu thức lồng nhau.

## 15. Ghi nhớ

#root tham chiếu object gốc của lượt đánh giá; #this tham chiếu object đang được đánh giá tại vị trí hiện tại. Ở đầu biểu thức, hai biến thường cùng trỏ tới root object. Trong selection và projection, #this chuyển sang phần tử hiện tại, còn #root vẫn giữ object gốc.

Root object được cung cấp khi tạo EvaluationContext, đặt bằng setRootObject hoặc truyền vào overload getValue cho từng lần đánh giá. Context variables là dữ liệu riêng, được truy cập bằng tên có tiền tố #; chúng không tự thay đổi khi root object thay đổi. Root object cũng không đồng nghĩa với Spring bean được truy cập qua BeanResolver.

Hãy chọn root object có phạm vi vừa đủ, dùng #this cho phần tử hiện tại và #root cho dữ liệu gốc, kiểm tra null ở từng cấp và tạo context phù hợp cho mỗi lượt đánh giá. Cách phân biệt rõ các nguồn dữ liệu này giúp biểu thức SpEL dễ đọc, dễ kiểm thử và dễ kiểm soát quyền truy cập.