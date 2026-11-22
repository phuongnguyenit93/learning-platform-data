# Toán tử truy cập property và method

## Mục tiêu

Trong Spring Expression Language (SpEL), dấu chấm giúp đi từ đối tượng hiện tại tới property hoặc method của nó. Cú pháp này cho phép biểu thức đọc dữ liệu lồng nhau, gọi hành vi của object và kết hợp nhiều bước thành một kết quả. Để sử dụng an toàn, cần phân biệt truy cập property với gọi method, hiểu object nào đang được truy cập và biết EvaluationContext cho phép những thao tác nào.

Sau bài này, bạn có thể:

- Đọc property của root object và các object lồng nhau bằng cú pháp dấu chấm.
- Gọi instance method với hoặc không có tham số.
- Truy cập phần tử trong List, array và Map bằng toán tử chỉ số.
- Xử lý object có thể null bằng safe navigation.
- Đọc hoặc ghi property theo quyền mà EvaluationContext cho phép.
- Nhận diện và xử lý các lỗi property/method thường gặp.

## 1. Dấu chấm và đối tượng đang được truy cập

Dấu chấm (.) là cú pháp điều hướng trong SpEL. Phần bên trái xác định object hiện tại; phần bên phải xác định property cần đọc hoặc method cần gọi trên object đó.

Giả sử ứng dụng có model:

~~~java
public class Person {
    private String name;
    private Address address;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Nếu root object là một Person, các biểu thức sau có ý nghĩa:

| Biểu thức | Ý nghĩa |
|---|---|
| **name** | Đọc property name của root object |
| **address** | Đọc property address của root object |
| **address.city** | Đọc address, sau đó đọc city trên Address |
| **#root.name** | Đọc name bằng cách chỉ rõ root object |
| **#root.address.city** | Cùng đường dẫn lồng nhau, nhưng chỉ rõ root |

Khi root object đã được truyền vào lúc đánh giá, có thể tham chiếu trực tiếp property của root mà không cần viết #root. Dùng #root khi muốn làm rõ điểm bắt đầu hoặc khi biểu thức có nhiều bước điều hướng.

## 2. Property access: đọc thuộc tính của object

Property access dùng tên property, không cần viết tên getter:

~~~text
name
address.city
~~~

Với JavaBean, property name thường được ánh xạ tới getter getName(), còn property Boolean active thường được ánh xạ tới isActive() hoặc getter phù hợp. Vì vậy, name là cú pháp truy cập property; nó không phải lời gọi method được viết tắt một cách tùy ý.

SpEL thực hiện việc truy cập thông qua PropertyAccessor trong EvaluationContext. Với cấu hình mặc định phổ biến, accessor phản chiếu có thể sử dụng các JavaBean property và public field mà nó hỗ trợ. Ứng dụng cũng có thể đăng ký accessor riêng để ánh xạ property theo một quy tắc khác.

Ví dụ đọc property bằng Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("address.city");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

String city = expression.getValue(context, person, String.class);
~~~

Ở đây, person là root object. SpEL đọc property address, rồi đọc city từ object Address trả về. Kiểu kết quả String.class giúp thể hiện rõ kiểu mà ứng dụng mong đợi.

Tên property phải khớp với tên được accessor hỗ trợ. Nếu model đổi tên getter, đổi cấu trúc object hoặc accessor không còn cung cấp property đó, biểu thức có thể thất bại khi chạy dù mã Java vẫn biên dịch.

### Property lồng nhau

Có thể nối nhiều property bằng dấu chấm:

~~~text
order.customer.address.city
~~~

Mỗi bước sử dụng kết quả của bước trước. Biểu thức chỉ đánh giá được nếu từng object trung gian tồn tại và property tương ứng có thể truy cập. Nếu customer hoặc address có thể null, hãy xử lý rõ ràng thay vì giả định đường dẫn luôn đầy đủ.

### Property của Map, List và array

Khi dữ liệu nằm trong cấu trúc collection, SpEL hỗ trợ toán tử chỉ số:

~~~text
settings['theme']
items[0]
orders[0].total
matrix[0][1]
~~~

- Với Map, dùng khóa trong dấu ngoặc vuông, ví dụ settings['theme'].
- Với List hoặc array, dùng chỉ số bắt đầu từ 0, ví dụ items[0].
- Có thể tiếp tục điều hướng sau khi lấy phần tử, ví dụ orders[0].total.

Hãy kiểm tra Map có khóa được yêu cầu hay không, List/array có phần tử ở vị trí đó hay không và phần tử lấy ra có đúng kiểu dự kiến hay không. Truy cập chỉ số vượt phạm vi hoặc dùng khóa không tồn tại có thể dẫn tới lỗi hoặc giá trị không có như mong đợi tùy loại dữ liệu và accessor.

## 3. Method invocation: gọi phương thức của object

Để gọi method, viết tên method theo sau bởi cặp ngoặc đơn. Các tham số đặt trong ngoặc và phân tách bằng dấu phẩy:

~~~text
getName()
formatName('Nguyen')
calculateTotal(10, 2)
~~~

Nếu root object là Person, biểu thức getName() gọi method trên root. Có thể viết #root.getName() để chỉ rõ object nhận lời gọi.

Điểm khác nhau cần nhớ:

| Cú pháp | Loại thao tác |
|---|---|
| **name** | Đọc property name |
| **getName()** | Gọi method có tên getName |
| **address.city** | Đọc property city trên object address |
| **address.getCity()** | Gọi method getCity trên object address |
| **address.city.toUpperCase()** | Đọc city, sau đó gọi method trên giá trị trả về |

Property access và method invocation có thể dẫn tới cùng một giá trị trong một JavaBean, nhưng chúng là hai cách phân giải khác nhau. Property access phụ thuộc PropertyAccessor; method invocation phụ thuộc MethodResolver.

### Truyền đối số

Đối số có thể là literal, biến hoặc kết quả của một biểu thức khác:

~~~text
greet('Lan')
calculatePrice(#quantity, #unitPrice)
isAllowed(order.customer)
~~~

Chuỗi được đặt trong dấu nháy đơn. Biến trong EvaluationContext được tham chiếu bằng dấu #, ví dụ #quantity. Nếu method nhận nhiều tham số, thứ tự và kiểu đối số phải phù hợp với chữ ký method.

SpEL có thể phân giải method dựa trên tên và kiểu đối số; quá trình chuyển đổi kiểu có thể được thực hiện thông qua TypeConverter của context. Với method overload, hãy kiểm thử các kiểu đầu vào thực tế để chắc chắn SpEL chọn được method mong muốn. Không nên dựa vào một chuyển đổi ngầm mà ứng dụng không quy định rõ.

### Gọi method không tham số

Cặp ngoặc vẫn cần được viết ngay cả khi method không nhận tham số:

~~~text
customer.getName()
customer.isActive()
~~~

Viết customer.name nếu mục đích là đọc JavaBean property. Viết customer.getName() nếu mục đích là gọi chính method có tên đó. Cách viết thể hiện rõ ý định và giúp tránh nhầm lẫn khi class có accessor tùy chỉnh.

### Gọi method trong một đường dẫn

Một biểu thức có thể đọc property, gọi method rồi tiếp tục điều hướng:

~~~text
order.customer.getName().toUpperCase()
~~~

Đọc từ trái sang phải: lấy customer từ order, gọi getName, sau đó gọi toUpperCase trên String trả về. Mỗi bước phụ thuộc vào kết quả bước trước. Nếu một bước trả về null, bước tiếp theo có thể gây lỗi trừ khi được xử lý bằng safe navigation.

## 4. Safe navigation khi object có thể null

Toán tử safe navigation là **?.**. Nó cho phép truy cập property hoặc gọi method mà không ném lỗi chỉ vì object ở ngay bên trái toán tử là null. Khi object đó null, kết quả của bước truy cập là null.

Ví dụ:

~~~text
customer?.name
customer?.getName()
~~~

Nếu customer null, biểu thức trả về null cho bước truy cập tương ứng. Nếu customer có giá trị, SpEL tiếp tục đọc property hoặc gọi method như bình thường.

Với đường dẫn nhiều cấp, hãy đặt safe navigation tại từng điểm có thể null:

~~~text
order?.customer?.address?.city
~~~

Nếu chỉ order có thể null nhưng customer hoặc address cũng có thể null, việc chỉ viết order?.customer.address.city chưa diễn đạt đầy đủ các điểm cần bảo vệ. Hãy đánh giá khả năng null của từng object trung gian và dùng ?. tại đúng vị trí.

Safe navigation cũng áp dụng cho lời gọi method:

~~~text
customer?.getName()?.toUpperCase()
~~~

Ở đây, ?. thứ nhất bảo vệ lời gọi getName khi customer null; ?. thứ hai bảo vệ lời gọi toUpperCase khi kết quả getName null.

Đừng dùng safe navigation để che giấu dữ liệu bắt buộc. Nếu nghiệp vụ yêu cầu customer phải tồn tại, việc trả null có thể khiến điều kiện phía sau âm thầm không đáp ứng. Trong trường hợp đó, xác thực đầu vào và báo lỗi rõ ràng có thể phù hợp hơn.

## 5. Đọc và ghi property

Đọc property thường dùng getValue. Khi biểu thức trỏ tới một property có thể ghi, SpEL cũng hỗ trợ setValue, miễn là PropertyAccessor và EvaluationContext cho phép ghi.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression nameExpression = parser.parseExpression("name");

SimpleEvaluationContext readContext =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

String currentName =
    nameExpression.getValue(readContext, person, String.class);

SimpleEvaluationContext writeContext =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

nameExpression.setValue(writeContext, person, "Lan");
~~~

Context chỉ đọc phù hợp khi biểu thức chỉ cần đọc dữ liệu. Context read-write cho phép ghi theo cơ chế data binding được hỗ trợ. Nếu property không có setter hoặc accessor không hỗ trợ ghi, thao tác setValue sẽ thất bại.

Chỉ cho phép ghi khi đó là yêu cầu rõ ràng của ứng dụng. Với biểu thức đến từ cấu hình hoặc người dùng, quyền ghi property có thể làm thay đổi trạng thái object và tạo ra tác dụng phụ khó kiểm soát.

## 6. EvaluationContext quyết định khả năng truy cập

EvaluationContext cung cấp các thành phần dùng để phân giải property và method. Cấu hình context quyết định một biểu thức có thể đọc thuộc tính nào, gọi method nào và có được phép thay đổi object hay không.

**StandardEvaluationContext** thường dùng các cơ chế phản chiếu để truy cập property và phân giải method. Nó linh hoạt, có thể được mở rộng bằng PropertyAccessor, MethodResolver và các thành phần khác. Hãy cấu hình những khả năng cần thiết và kiểm soát nguồn biểu thức.

**SimpleEvaluationContext** phù hợp với data binding có phạm vi giới hạn hơn. Ví dụ đọc property:

~~~java
SimpleEvaluationContext readOnly =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Nếu một biểu thức cần gọi instance method trong SimpleEvaluationContext, có thể bật khả năng đó một cách tường minh:

~~~java
SimpleEvaluationContext methodContext =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
~~~

Không giả định rằng một method có thể gọi được trong mọi context. Biểu thức có thể chạy với StandardEvaluationContext nhưng thất bại trong SimpleEvaluationContext nếu instance method chưa được bật hoặc MethodResolver không cung cấp khả năng tương ứng.

Khi ứng dụng dùng custom PropertyAccessor hoặc MethodResolver, hãy dùng cùng cấu hình trong kiểm thử và trong luồng đánh giá thực tế. Điều này tránh tình trạng biểu thức hoạt động trong test nhưng thất bại khi triển khai.

## 7. Một ví dụ hoàn chỉnh

Giả sử Person có property name và method greet(String suffix):

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String greet(String suffix) {
        return "Xin chào " + name + suffix;
    }
}
~~~

Có thể đọc property và gọi method bằng SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();

Person person = new Person("Lan");

Expression propertyExpression = parser.parseExpression("name");
String name =
    propertyExpression.getValue(context, person, String.class);

Expression methodExpression = parser.parseExpression("greet('!')");
String greeting =
    methodExpression.getValue(context, person, String.class);
~~~

Kết quả mong đợi:

- name trả về Lan.
- greet('!') trả về Xin chào Lan!.

Ví dụ này cho thấy property access và method invocation có thể dùng chung một root object và một parser. Khả năng gọi method được bật tường minh trong SimpleEvaluationContext.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy property | Sai tên, getter không phù hợp hoặc accessor không hỗ trợ | Kiểm tra model, JavaBean property và PropertyAccessor |
| Property trung gian là null | Đường dẫn lồng nhau giả định object luôn tồn tại | Kiểm tra nullability và thêm safe navigation tại đúng bước |
| Không tìm thấy method | Sai tên, sai số lượng tham số hoặc method không được resolver hỗ trợ | Kiểm tra chữ ký method và MethodResolver |
| Method overload không được phân giải như mong muốn | Kiểu đối số hoặc chuyển đổi không rõ ràng | Kiểm thử kiểu đối số thực tế và cấu hình TypeConverter |
| Gọi method thất bại trong SimpleEvaluationContext | Instance method chưa được bật | Kiểm tra builder và cấu hình method resolver |
| Không thể ghi property | Property chỉ đọc hoặc accessor không hỗ trợ ghi | Kiểm tra setter, accessor và loại context |
| Lỗi khi dùng [0] | Collection rỗng hoặc chỉ số ngoài phạm vi | Kiểm tra kích thước và quy tắc dữ liệu trước khi truy cập |

Khi xử lý lỗi, hãy xác định biểu thức đầy đủ, root object, loại context và kiểu dữ liệu tại bước gây lỗi. Không chỉ nhìn vào chuỗi biểu thức: cùng một biểu thức có thể hoạt động với một context nhưng không hoạt động với context khác.

## 9. Thực hành tốt

- Dùng property syntax để đọc dữ liệu và method syntax khi thật sự cần gọi hành vi của object.
- Giữ đường dẫn property ngắn và dễ hiểu; nếu phải nối quá nhiều cấp, cân nhắc tạo property dẫn xuất hoặc phương thức có tên rõ ràng trong model/service.
- Dùng ?. cho các điểm có thể null, nhưng không thay thế xác thực dữ liệu bắt buộc bằng giá trị null im lặng.
- Kiểm tra collection và chỉ số trước khi truy cập phần tử.
- Kiểm thử method overload và chuyển đổi kiểu với các kiểu đối số thực tế.
- Chỉ bật instance method hoặc quyền ghi property khi biểu thức cần và nguồn biểu thức được kiểm soát.
- Tránh gọi method có tác dụng phụ như ghi database, gửi thông báo hoặc thay đổi trạng thái trong một biểu thức được đánh giá nhiều lần.
- Không đánh giá biểu thức do nguồn không đáng tin cung cấp bằng context có quyền truy cập rộng.
- Parse biểu thức một lần khi nạp hoặc cập nhật cấu hình rồi tái sử dụng Expression khi phù hợp.
- Khi refactor model, tìm các chuỗi SpEL tham chiếu tới property và method vì compiler Java không thể đảm bảo phát hiện mọi tham chiếu dạng chuỗi.

## 10. Checklist

Trước khi sử dụng một biểu thức có property hoặc method access, hãy kiểm tra:

- [ ] Root object và đường dẫn property đã được xác định rõ.
- [ ] Property name khớp với accessor và model thực tế.
- [ ] Các object trung gian có thể null đã được xử lý.
- [ ] Map key và collection index có quy tắc tồn tại rõ ràng.
- [ ] Method name, số lượng tham số và kiểu đối số phù hợp.
- [ ] EvaluationContext hỗ trợ property/method cần thiết.
- [ ] Quyền ghi property chỉ được bật khi thật sự cần.
- [ ] Các method được gọi không tạo tác dụng phụ ngoài ý muốn.
- [ ] Các trường hợp bình thường, null, collection rỗng và lỗi phân giải đã được kiểm thử.

## Kết luận

Dấu chấm trong SpEL cho phép điều hướng từ root object tới property hoặc method của object lồng nhau. Property access đọc dữ liệu thông qua PropertyAccessor; method invocation gọi hành vi thông qua MethodResolver. Khi kết hợp với toán tử chỉ số và safe navigation, biểu thức có thể mô tả đường dẫn dữ liệu khá linh hoạt. Muốn biểu thức dễ bảo trì, hãy làm rõ root object, kiểm soát EvaluationContext, xử lý null có chủ đích và kiểm thử cả tên property lẫn chữ ký method.
