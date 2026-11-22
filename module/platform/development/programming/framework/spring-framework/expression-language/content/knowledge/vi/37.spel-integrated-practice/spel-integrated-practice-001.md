# Đánh giá property của root object và xử lý null-safe trong Spring Expression Language

Trong Spring Expression Language (SpEL), root object là đối tượng mặc định mà expression sử dụng khi đọc property hoặc gọi method mà không có tiền tố biến. Ví dụ, nếu root object là Customer, biểu thức name hoặc address.city được đánh giá trên Customer.

Trong ứng dụng thực tế, property lồng nhau có thể trả về null. Nếu biểu thức tiếp tục truy cập property trên giá trị null, evaluation sẽ thất bại. SpEL cung cấp null-safe navigation bằng toán tử ?. để bỏ qua thao tác truy cập khi receiver ngay trước toán tử là null.

Khi viết expression, cần xác định rõ property nào thuộc root object, object trung gian nào có thể null và đặt toán tử null-safe tại từng đoạn có rủi ro. Có thể kết hợp với kiểm tra null, toán tử Elvis hoặc toán tử điều kiện để tạo kết quả mặc định phù hợp.

## 1. Root object là điểm bắt đầu của property access

Khi tạo StandardEvaluationContext với một object, object đó trở thành root object:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser =
    new SpelExpressionParser();

Expression expression =
    parser.parseExpression("name");

String name =
    expression.getValue(context, String.class);
~~~

Với root object là Customer, biểu thức name đọc property name trên Customer. SpEL thường sử dụng getter JavaBean như getName() hoặc isActive() thông qua PropertyAccessor mặc định của context.

Có thể tham chiếu root object một cách tường minh bằng #root:

~~~spel
#root.name
#root.membershipLevel
~~~

Ở cấp ngoài cùng, name và #root.name đều chỉ property name của root object. Cách viết có #root hữu ích khi biểu thức phức tạp và cần phân biệt dữ liệu gốc với object hiện tại trong một thao tác lồng nhau.

## 2. Phân biệt root property với variable

Một tên property không có tiền tố # thường được tra cứu trên object hiện tại. Một tên có tiền tố # được tra cứu trong không gian biến của EvaluationContext.

Ví dụ:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("minimumLevel", "SILVER");
~~~

Expression:

~~~spel
membershipLevel == #minimumLevel
~~~

Trong đó:

- membershipLevel là property trên root object Customer.
- #minimumLevel là biến được đăng ký bằng setVariable.
- #root.membershipLevel là cách viết tường minh để đọc property từ root.

Không nên nhầm #customer với root object chỉ vì biến có tên giống kiểu hoặc property. #customer chỉ tồn tại nếu ứng dụng đăng ký variable customer trong EvaluationContext.

## 3. Đường dẫn property nhiều cấp

SpEL cho phép nối property bằng dấu chấm:

~~~spel
customer.address.city
~~~

Mỗi đoạn tiếp theo được đọc trên object mà đoạn trước trả về. Nếu root object là Order, quá trình có thể là:

| Đoạn expression | Object nhận thao tác |
|---|---|
| customer | Order |
| address | Customer |
| city | Address |

Vì vậy, receiver của city không phải Order mà là Address. Khi expression lỗi ở đoạn cuối, cần kiểm tra object trung gian thực tế thay vì chỉ xem root object.

Ví dụ với JavaBean:

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

public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
~~~

Với root object là Order, expression có thể đọc:

~~~spel
customer.address.city
~~~

Miễn là customer và address đều khác null và property có thể được truy cập.

## 4. Điều gì xảy ra khi property trung gian là null?

Giả sử Order có customer nhưng customer chưa có address:

~~~java
Customer customer = new Customer();
customer.setAddress(null);

Order order = new Order();
order.setCustomer(customer);
~~~

Biểu thức:

~~~spel
customer.address.city
~~~

đọc được customer, sau đó address trả về null. SpEL không thể đọc city trên một receiver null, vì vậy evaluation phát sinh lỗi.

Đây là lỗi runtime khi truy cập property, không phải lỗi cú pháp. Expression có thể parse thành công nhưng thất bại khi getValue được gọi với dữ liệu có object trung gian null.

Null ở property cuối cũng cần được phân biệt với null ở receiver. Nếu address tồn tại nhưng getCity() trả về null, expression customer.address.city có thể đánh giá thành công và kết quả chỉ đơn giản là null. Lỗi xảy ra khi một thao tác tiếp theo cố truy cập property hoặc gọi method trên giá trị null đó.

## 5. Null-safe navigation với toán tử ?.

Toán tử ?. kiểm tra receiver ngay bên trái. Nếu receiver là null, thao tác property hoặc method tương ứng được bỏ qua và kết quả của đoạn đó là null.

Ví dụ:

~~~spel
customer?.address
~~~

Nếu customer null, biểu thức trả về null thay vì cố đọc address trên null. Nếu customer tồn tại, SpEL đọc property address như bình thường.

Có thể dùng với root object:

~~~spel
#root?.customer
~~~

Nếu root object null, biểu thức trả về null. Nếu root object tồn tại, SpEL tiếp tục đọc customer.

Null-safe navigation hữu ích khi dữ liệu đến từ API, database, form hoặc object được tạo theo điều kiện, nơi một số property lồng nhau có thể chưa được khởi tạo.

## 6. Đặt ?. tại từng cấp có thể null

Một điểm quan trọng là null-safe operator chỉ bảo vệ thao tác ngay sau nó. Trong compound expression, các đoạn còn lại vẫn được đánh giá. Vì vậy, nếu nhiều object trung gian có thể null, cần đặt ?. ở từng đoạn tương ứng.

Ví dụ:

~~~spel
customer?.address.city
~~~

Biểu thức này bảo vệ trường hợp customer null khi đọc address. Nhưng nếu customer tồn tại và address là null, phần .city tiếp theo vẫn có thể thất bại.

Nếu cả customer và address đều có thể null, hãy viết:

~~~spel
customer?.address?.city
~~~

Tương tự, với root object:

~~~spel
#root?.customer?.address?.city
~~~

Chuỗi thao tác được bảo vệ ở từng cấp:

1. Nếu root object null, kết quả là null.
2. Nếu root có nhưng customer null, kết quả là null.
3. Nếu customer có nhưng address null, kết quả là null.
4. Nếu cả đường dẫn tồn tại, SpEL trả về city.

Không nên chỉ đặt một toán tử null-safe ở đầu đường dẫn rồi giả định mọi property phía sau đều được bảo vệ.

## 7. Dùng null-safe navigation với method call

Toán tử ?. cũng có thể bảo vệ lời gọi method:

~~~spel
customer?.getName()
customer?.calculateDiscount(#amount)
~~~

Nếu customer null, SpEL không gọi method và trả về null. Nếu customer tồn tại, method được tìm và gọi như bình thường.

Nếu method trả về một object khác có thể null, cần tiếp tục bảo vệ các thao tác sau:

~~~spel
customer?.getAddress()?.getCity()
~~~

Trong biểu thức này:

- customer?.getAddress() bảo vệ receiver customer.
- ?.getCity() bảo vệ kết quả getAddress() nếu nó null.

Null-safe navigation không xử lý method không tồn tại, overload không phù hợp hoặc exception được ném ra bên trong method. Nó chỉ xử lý trường hợp receiver của thao tác null.

## 8. Dùng #root rõ ràng trong expression có nhiều object

Khi expression có nhiều tầng hoặc collection, viết #root giúp thể hiện rõ dữ liệu nào luôn thuộc object gốc.

Ví dụ root object là OrderInput, có property customer và minimumTotal:

~~~spel
#root.customer?.address?.city
#root.minimumTotal
~~~

Trong selection:

~~~spel
orders.?[#this.total >= #root.minimumTotal]
~~~

#root vẫn là OrderInput, còn #this là Order đang được kiểm tra. Nếu cần đọc customer của từng order, có thể viết:

~~~spel
orders.?[#this.customer?.address?.city == #root.requiredCity]
~~~

Nếu phần tử order cũng có thể null:

~~~spel
orders.?[#this?.customer?.address?.city == #root.requiredCity]
~~~

Điều kiện này bảo vệ phần tử hiện tại trước khi đọc customer. Các đoạn tiếp theo cũng được bảo vệ khi customer hoặc address có thể null.

## 9. Dùng toán tử Elvis để cung cấp giá trị mặc định

Nếu kết quả property có thể null và ứng dụng cần một giá trị thay thế, có thể dùng toán tử Elvis ?:.

Ví dụ:

~~~spel
customer?.address?.city ?: 'Unknown'
~~~

Nếu đường dẫn trả về null, kết quả là Unknown. Nếu city có giá trị, expression trả về city. Theo ngữ nghĩa Elvis của SpEL, chuỗi rỗng cũng được xem là giá trị thiếu và có thể dẫn đến nhánh mặc định.

Có thể dùng với root property:

~~~spel
#root?.customer?.name ?: 'Guest'
~~~

Elvis phù hợp khi chỉ cần một fallback đơn giản. Nó không bắt exception từ property không tồn tại, method không tương thích, index ngoài phạm vi hoặc lỗi bên trong getter.

Nếu muốn phân biệt null với chuỗi rỗng, hãy dùng điều kiện tường minh thay vì dựa vào Elvis.

## 10. Dùng toán tử điều kiện khi cần quy tắc rõ ràng

Toán tử ternary cho phép chọn kết quả theo điều kiện:

~~~spel
customer != null ? customer.name : 'Guest'
~~~

Nếu root object có thể null:

~~~spel
#root != null ? #root.customer?.name : 'Guest'
~~~

Có thể kiểm tra thêm property:

~~~spel
customer != null && customer.address != null
    ? customer.address.city
    : 'Unknown'
~~~

Toán tử && đánh giá ngắn mạch: nếu customer null, vế kiểm tra address không được đánh giá. Nếu customer tồn tại nhưng address null, nhánh truy cập city không được chọn.

Ternary phù hợp khi fallback phụ thuộc nhiều điều kiện hoặc cần phân biệt những trạng thái khác nhau. Với đường dẫn chỉ cần trả về một giá trị mặc định khi null, null-safe navigation kết hợp Elvis thường ngắn gọn hơn.

## 11. Phân biệt null với giá trị rỗng

Null-safe navigation xử lý object null. Nó không tự coi mọi giá trị "không có nội dung" là null.

Các trường hợp cần phân biệt:

| Giá trị property | Ý nghĩa | Hành vi khi đọc |
|---|---|---|
| null | Không có object/giá trị | Kết quả null nếu property đọc thành công |
| Chuỗi rỗng | String tồn tại nhưng không có ký tự | Trả về chuỗi rỗng |
| Collection rỗng | Collection tồn tại nhưng không có phần tử | Trả về collection rỗng |
| Số 0 | Giá trị số hợp lệ | Trả về 0 |
| Boolean false | Giá trị Boolean hợp lệ | Trả về false |

Ví dụ:

~~~spel
customer?.name
~~~

Nếu customer tồn tại và name là chuỗi rỗng, kết quả là chuỗi rỗng. Null-safe operator không thay chuỗi rỗng bằng null.

Nếu cần fallback cả khi chuỗi rỗng, Elvis của SpEL có thể phù hợp:

~~~spel
customer?.name ?: 'Anonymous'
~~~

Nếu cần xử lý collection rỗng, phải kiểm tra kích thước hoặc isEmpty() riêng; null-safe navigation không biến collection rỗng thành null.

## 12. Kết hợp null-safe với indexer

Khi property trả về array, List hoặc Map, có thể cần bảo vệ cả collection và phần tử lấy ra.

Với Spring Framework 6.2 trở lên, null-safe indexer có cú pháp ?.[]:

~~~spel
#root?.addresses?.[0]?.city
~~~

Trong ví dụ này:

- #root?.addresses bảo vệ root object và property addresses.
- ?. [0] (viết liền thành ?.[0]) là null-safe indexer bảo vệ collection khi nó null.
- ?.city bảo vệ phần tử nếu phần tử được lấy ra là null.

Cú pháp thực tế phải viết liền, không có khoảng trắng:

~~~spel
#root?.addresses?.[0]?.city
~~~

Null-safe indexer không xử lý collection rỗng hoặc index ngoài phạm vi. Nếu addresses tồn tại nhưng không có phần tử ở vị trí 0, thao tác index vẫn có thể phát sinh lỗi.

Với phiên bản Spring trước 6.2, có thể kiểm tra null và kích thước trước khi index:

~~~spel
#root.addresses != null && !#root.addresses.isEmpty()
    ? #root.addresses[0].city
    : null
~~~

Cần bổ sung kiểm tra phần tử null nếu phần tử đầu tiên cũng có thể null.

## 13. Dùng null-safe trong selection và projection

Selection và projection thay đổi object hiện tại theo từng phần tử. Trong predicate hoặc biểu thức projection, #this đại diện phần tử đang được xử lý.

Ví dụ lọc những đơn hàng có customer và address hợp lệ:

~~~spel
#root.orders.?[
    #this?.customer?.address?.city == #root.requiredCity
]
~~~

Nếu order null, phần tử không được chọn vì vế trái trả về null và không bằng requiredCity. Nếu customer hoặc address null, chuỗi null-safe cũng trả về null.

Projection có thể tạo danh sách tên thành phố:

~~~spel
#root.orders.![#this?.customer?.address?.city]
~~~

Nếu một order hoặc object lồng bên trong null, vị trí tương ứng trong kết quả có thể là null. Projection không tự loại bỏ các kết quả null.

Nếu cần bỏ các phần tử không có city, có thể kết hợp selection trước projection:

~~~spel
#root.orders.?[
    #this?.customer?.address?.city != null
].![customer.address.city]
~~~

Selection bảo đảm chỉ giữ các order có đường dẫn city khác null trước khi projection đọc giá trị.

## 14. Root object null và cách xử lý

Root object có thể null nếu ứng dụng tạo context mà không cung cấp object hoặc truyền root null. Trong trường hợp này, biểu thức truy cập property trực tiếp:

~~~spel
name
~~~

không có receiver hợp lệ và evaluation có thể thất bại.

Nếu muốn biểu thức trả về null khi root null, có thể tham chiếu tường minh:

~~~spel
#root?.name
~~~

Hoặc dùng giá trị mặc định:

~~~spel
#root?.name ?: 'Unknown'
~~~

Trong Java, nên quyết định rõ root object có bắt buộc hay không. Nếu expression luôn yêu cầu một root object hợp lệ, hãy kiểm tra đầu vào trước khi gọi getValue. Nếu root là tùy chọn, dùng null-safe expression và định nghĩa kết quả null theo hợp đồng ứng dụng.

Không nên dùng null-safe navigation để che giấu một root object bắt buộc nhưng bị thiếu do lỗi khởi tạo dữ liệu.

## 15. Property accessor quyết định cách đọc property

SpEL không truy cập mọi property bằng một quy tắc cố định. EvaluationContext cung cấp PropertyAccessor để tìm và đọc property trên object hiện tại.

StandardEvaluationContext có accessor reflection mặc định, hỗ trợ truy cập property theo các quy ước Java phổ biến như getter và field có thể truy cập. Ứng dụng cũng có thể đăng ký PropertyAccessor tùy chỉnh cho kiểu domain hoặc cấu trúc dữ liệu riêng.

Nếu property tồn tại trong source nhưng expression không đọc được, cần kiểm tra:

- Root object hoặc receiver hiện tại có đúng kiểu runtime không?
- Getter hoặc field có thể được truy cập không?
- Tên property có đúng không?
- PropertyAccessor nào đang được đăng ký?
- Object trung gian có null không?

Null-safe navigation chỉ bỏ qua thao tác khi receiver null. Nó không sửa tên property sai và không làm một accessor không hỗ trợ property trở nên hỗ trợ.

## 16. Phân biệt null-safe access với lỗi property

Có ba tình huống khác nhau:

**Receiver null:**

~~~spel
customer?.name
~~~

Nếu customer null, kết quả là null.

**Property không tồn tại:**

~~~spel
customer?.unknownProperty
~~~

Nếu customer tồn tại nhưng không có property hoặc accessor tương ứng, evaluation vẫn có thể thất bại. Null-safe operator không bỏ qua lỗi property trên một object khác null.

**Getter ném exception:**

~~~spel
customer?.displayName
~~~

Nếu customer tồn tại nhưng getter displayName ném exception, exception đó vẫn có thể truyền ra ngoài. Null-safe operator không bắt exception bên trong getter.

Phân biệt ba trường hợp này giúp tránh dùng ?. như một cơ chế bắt lỗi tổng quát.

## 17. Đánh giá từng đoạn để tìm property null

Khi một đường dẫn lồng nhau thất bại, có thể tách expression thành từng đoạn để xem object nào trả về null.

Ví dụ:

~~~spel
customer
customer.address
customer.address.city
~~~

Trong Java:

~~~java
Object customerValue =
    parser.parseExpression("customer")
          .getValue(context);

Object addressValue =
    parser.parseExpression("customer.address")
          .getValue(context);

Object cityValue =
    parser.parseExpression("customer.address.city")
          .getValue(context);
~~~

Có thể kiểm tra giá trị trung gian:

~~~java
private static String describe(Object value) {
    return value == null
        ? "null"
        : value.getClass().getName();
}
~~~

Nếu customerValue có kiểu Customer nhưng addressValue là null, điểm cần xử lý là dữ liệu hoặc getter address. Nếu addressValue tồn tại nhưng city lỗi, kiểm tra accessor và property city trên kiểu runtime của Address.

Dùng cùng EvaluationContext giúp giữ nguyên root object, variables và accessor trong quá trình cô lập lỗi.

## 18. Lựa chọn cách xử lý null theo yêu cầu

Không phải mọi property null đều cần thay bằng giá trị mặc định. Hãy xác định hợp đồng kết quả mong muốn:

| Nhu cầu | Cách viết gợi ý |
|---|---|
| Trả null nếu receiver null | customer?.name |
| Đọc nhiều cấp có thể null | customer?.address?.city |
| Trả giá trị mặc định khi null | customer?.name ?: 'Guest' |
| Chọn giữa hai nhánh rõ ràng | customer != null ? customer.name : 'Guest' |
| Kiểm tra nhiều điều kiện | customer != null && customer.active |
| Root object có thể null | #root?.customer?.name |
| Bỏ phần tử collection thiếu property | Selection kiểm tra null trước projection |

Tránh dùng giá trị mặc định một cách tùy tiện nếu null mang ý nghĩa nghiệp vụ riêng. Ví dụ, null có thể biểu thị dữ liệu chưa được xác minh, trong khi chuỗi "Unknown" có thể bị hiểu là một giá trị thực.

## 19. Ví dụ hoàn chỉnh: đánh giá root property có thể null

Giả sử một ứng dụng tạo thông báo từ thông tin khách hàng:

~~~java
public class Address {
    private final String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private final String name;
    private final Address address;

    public Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }
}

public class CustomerInput {
    private final Customer customer;

    public CustomerInput(Customer customer) {
        this.customer = customer;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Tạo root object có address null:

~~~java
Customer customer =
    new Customer("Linh", null);

CustomerInput input =
    new CustomerInput(customer);

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

ExpressionParser parser =
    new SpelExpressionParser();
~~~

Đọc thành phố an toàn:

~~~java
Expression cityExpression =
    parser.parseExpression(
        "#root?.customer?.address?.city"
    );

String city =
    cityExpression.getValue(context, String.class);
~~~

Kết quả là null, không phát sinh lỗi chỉ vì address null.

Có thể tạo thông báo mặc định:

~~~java
Expression messageExpression =
    parser.parseExpression(
        "Customer #{#root?.customer?.name ?: 'Guest'} lives in #{#root?.customer?.address?.city ?: 'Unknown'}.",
        new TemplateParserContext()
    );

String message =
    messageExpression.getValue(
        context,
        String.class
    );
~~~

Kết quả:

~~~text
Customer Linh lives in Unknown.
~~~

Ví dụ cho thấy root object được tham chiếu tường minh, từng property có thể null được bảo vệ và Elvis cung cấp fallback tại vị trí cần thiết.

## 20. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Property không có tiền tố # luôn là variable.**  
Ở cấp ngoài cùng, tên không có # thường được tra cứu trên root object hoặc active object. Variable được tham chiếu bằng #name.

**Nhầm lẫn 2: #root và #this luôn giống nhau.**  
Ở cấp ngoài cùng chúng thường trùng nhau. Trong selection và projection, #this là phần tử hiện tại còn #root giữ object gốc.

**Nhầm lẫn 3: Một ?. ở đầu property path bảo vệ mọi cấp sau.**  
Mỗi receiver có thể null cần được bảo vệ tại đúng đoạn, ví dụ customer?.address?.city.

**Nhầm lẫn 4: Null-safe navigation bắt mọi lỗi property.**  
Nó chỉ xử lý receiver null. Property không tồn tại, accessor không hỗ trợ hoặc getter ném exception vẫn có thể gây lỗi.

**Nhầm lẫn 5: Collection rỗng giống collection null.**  
Collection rỗng là object hợp lệ. Null-safe property access không tự biến collection rỗng thành null.

**Nhầm lẫn 6: Elvis bắt được exception.**  
Elvis chọn fallback cho giá trị null hoặc chuỗi rỗng theo ngữ nghĩa SpEL; nó không bắt lỗi property, method hay index.

**Nhầm lẫn 7: Null-safe indexer và property navigation là cùng một cú pháp.**  
Property/method dùng ?.; null-safe indexer ?.[] được hỗ trợ từ Spring Framework 6.2.

**Nhầm lẫn 8: Dùng fallback luôn là lựa chọn tốt.**  
Null có thể mang ý nghĩa nghiệp vụ. Chỉ thay bằng Unknown hoặc giá trị mặc định khi hợp đồng ứng dụng yêu cầu.

## 21. Ghi nhớ

- Root object là đối tượng mặc định để SpEL đọc property và gọi method.
- StandardEvaluationContext có thể nhận root object qua constructor hoặc setRootObject; overload getValue cũng có thể nhận root cho một lần đánh giá.
- Property path được đánh giá từng cấp; receiver của property cuối là object mà cấp trước trả về.
- Tên property không có # thường được đọc trên root/active object; #name đọc variable trong EvaluationContext.
- #root luôn giữ root object ban đầu; #this có thể thay đổi trong selection và projection.
- Null-safe navigation ?. bỏ qua property hoặc method call khi receiver ngay trước nó là null.
- Đặt ?. tại từng cấp có thể null, ví dụ #root?.customer?.address?.city.
- Null-safe navigation không xử lý property sai, accessor không hỗ trợ hoặc exception từ getter/method.
- Elvis ?: và ternary có thể tạo fallback; chọn cách phù hợp với ý nghĩa của null và chuỗi rỗng.
- Null-safe indexer ?.[] là tính năng riêng từ Spring Framework 6.2; nó không làm index ngoài phạm vi trở nên hợp lệ.
- Trong selection/projection, bảo vệ cả phần tử null và các property lồng nhau khi cần.
- Khi debug, đánh giá từng đoạn property path, kiểm tra giá trị và kiểu runtime, rồi xác định PropertyAccessor và receiver tại điểm lỗi.

Khi đánh giá property của root object, hãy bắt đầu từ root, lần theo từng receiver trong property path và xác định đoạn nào có thể trả về null. Dùng null-safe navigation ở từng cấp có rủi ro, rồi chọn rõ kết quả null hay giá trị mặc định theo yêu cầu nghiệp vụ.
