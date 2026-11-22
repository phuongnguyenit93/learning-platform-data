# Xác định active object tại điểm truy cập lỗi trong Spring Expression Language

Khi một biểu thức Spring Expression Language (SpEL) truy cập property, gọi method hoặc lấy phần tử collection, thao tác luôn được thực hiện trên một object cụ thể tại vị trí đó. Object nhận thao tác được gọi là active object hoặc current evaluation object. Nếu expression có nhiều đoạn nối nhau, active object có thể thay đổi sau mỗi bước.

Muốn điều tra lỗi chính xác, cần xác định object nào đang nhận thao tác bị lỗi, kiểu runtime của object đó là gì và giá trị của đoạn đường dẫn ngay trước điểm lỗi. Hai tham chiếu quan trọng giúp làm việc này là:

- **#root:** root object của toàn bộ lần đánh giá.
- **#this:** object hiện tại tại vị trí đang được đánh giá; trong selection và projection, nó thường là phần tử đang được xử lý.

Không nên mặc định #root và #this luôn là cùng một object. Ở cấp ngoài cùng chúng thường trùng nhau, nhưng trong biểu thức lồng nhau hoặc xử lý collection, #this có thể thay đổi.

## 1. Active object là object nhận thao tác hiện tại

Xét expression:

~~~spel
customer.address.city
~~~

Giả sử root object là Order. SpEL lần lượt:

1. Đọc property customer trên Order.
2. Lấy object Customer trả về.
3. Đọc property address trên Customer.
4. Lấy object Address trả về.
5. Đọc property city trên Address.

Object nhận từng thao tác là:

| Đoạn expression | Active receiver |
|---|---|
| customer | Order |
| address | Customer |
| city | Address |

Nếu lỗi xảy ra khi đọc city, cần kiểm tra object Address thực tế và kiểu của nó. Việc chỉ kiểm tra root object Order có thể không tìm ra nguyên nhân, vì receiver tại điểm lỗi là object lồng bên trong.

Cùng nguyên tắc áp dụng cho lời gọi method và indexer:

~~~spel
customer.calculateDiscount(#amount)
items[0].name
settings['theme']
~~~

- calculateDiscount được gọi trên object Customer.
- Indexer [0] thao tác trên items; sau khi lấy phần tử, name được đọc trên object phần tử đó.
- Tra cứu theme được thực hiện trên Map settings.

## 2. Phân biệt #root và #this

SpEL cung cấp hai biến đặc biệt:

| Tham chiếu | Ý nghĩa |
|---|---|
| #root | Root object được đặt cho lần đánh giá |
| #this | Object hiện tại mà biểu thức đang đánh giá tại vị trí đó |

Ở cấp ngoài cùng, nếu context có root object là Order:

~~~spel
#root
#this
~~~

cả hai đều tham chiếu Order.

Nhưng khi đi vào selection hoặc projection trên collection, #this thay đổi theo từng phần tử; #root vẫn giữ root object ban đầu.

Ví dụ:

~~~spel
orders.?[#this.total >= #root.minimum]
~~~

Giả sử root object là OrderSelectionInput:

- #root là OrderSelectionInput.
- orders là collection lấy từ root.
- #this trong predicate là OrderSummary đang được kiểm tra.
- #root.minimum vẫn lấy ngưỡng từ object gốc.

Nếu nhầm #this với #root, expression có thể đọc property trên sai kiểu object và gây lỗi property access.

## 3. Xác định receiver trong property path lồng nhau

Khi lỗi xuất hiện trong một đường dẫn nhiều cấp, hãy chia expression thành các đoạn tăng dần.

Ví dụ:

~~~spel
customer.address.city
~~~

Thay vì chỉ đánh giá toàn bộ expression, lần lượt kiểm tra:

~~~spel
customer
customer.address
customer.address.city
~~~

Mỗi đoạn cho biết giá trị trả về từ bước trước. Nếu customer thành công nhưng customer.address trả về null, điểm cần điều tra là getter address hoặc dữ liệu của Customer. Nếu customer.address trả về một object nhưng city thất bại, receiver của city là object Address đó.

Có thể thực hiện bằng Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object customer =
    parser.parseExpression("customer")
          .getValue(context);

Object address =
    parser.parseExpression("customer.address")
          .getValue(context);

Object city =
    parser.parseExpression("customer.address.city")
          .getValue(context);
~~~

Nếu dòng đánh giá customer.address.city phát sinh exception, hai kết quả trung gian giúp xác định đoạn cuối cùng đã hoạt động thành công.

Dùng cùng EvaluationContext giúp giữ nguyên variables, accessors và resolver của lần đánh giá cần điều tra.

## 4. Kiểm tra kiểu runtime của active object

Kiểu khai báo trong source code không phải lúc nào cũng là kiểu object thực tế tại runtime. Object có thể là subclass, proxy, implementation khác của interface hoặc object được tạo bởi framework.

Có thể kiểm tra giá trị trung gian bằng Java:

~~~java
private static String describe(Object value) {
    if (value == null) {
        return "null";
    }

    return value.getClass().getName();
}
~~~

Sử dụng:

~~~java
Object customer =
    parser.parseExpression("customer")
          .getValue(context);

Object address =
    parser.parseExpression("customer.address")
          .getValue(context);

System.out.println("customer = " + describe(customer));
System.out.println("address = " + describe(address));
~~~

Kết quả có thể cho biết receiver là một implementation hoặc proxy cụ thể thay vì kiểu mà người viết expression đang nghĩ đến.

Khi cần biết object có null hay không, kiểm tra null trước khi gọi getClass(). Không gọi method trên giá trị null trong chính đoạn chẩn đoán.

## 5. Active object trong selection trên collection

Với selection, SpEL đánh giá điều kiện trên từng phần tử. Trong predicate, #this là phần tử hiện tại.

Ví dụ:

~~~spel
#orders.?[#this.total >= #root.minimum]
~~~

Luồng đánh giá:

~~~text
Root: OrderSelectionInput
  |
  +-- minimum
  |
  +-- orders
        |
        +-- OrderSummary thứ nhất  <-- #this
        +-- OrderSummary thứ hai   <-- #this
        +-- OrderSummary thứ ba    <-- #this
~~~

Nếu lỗi xảy ra trong #this.total, hãy kiểm tra kiểu và trạng thái của từng phần tử OrderSummary, không chỉ kiểu của collection orders.

Nếu collection chứa phần tử null, phép đọc #this.total có thể thất bại ở phần tử đó. Có thể bảo vệ predicate:

~~~spel
#orders.?[#this != null && #this.total >= #root.minimum]
~~~

Toán tử && đánh giá ngắn mạch. Khi #this là null, vế truy cập total không được thực hiện.

Một cách chẩn đoán khác là kiểm tra collection và từng phần tử ở Java trước khi đánh giá predicate:

~~~java
Object value =
    parser.parseExpression("#orders")
          .getValue(context);

if (value instanceof Collection<?> orders) {
    for (Object order : orders) {
        System.out.println(describe(order));
    }
}
~~~

Cách này cho thấy phần tử null hoặc các kiểu runtime không đồng nhất có thể là nguồn gây lỗi.

## 6. Active object trong projection

Projection dùng biểu thức trên từng phần tử và cũng thay đổi #this theo phần tử đang xử lý.

Ví dụ:

~~~spel
#orders.![#this.customer.name]
~~~

Trong mỗi lượt:

- #this là một Order đang được chiếu.
- #this.customer là Customer của order đó.
- name được đọc trên Customer.

Nếu lỗi xảy ra ở name, cần xác định customer của đúng phần tử hiện tại có null hay có kiểu khác dự kiến.

Có thể viết an toàn hơn nếu customer có thể null:

~~~spel
#orders.![#this.customer?.name]
~~~

Nếu chính phần tử order cũng có thể null, cần bảo vệ cả cấp đó:

~~~spel
#orders.![#this?.customer?.name]
~~~

Null-safe navigation chỉ bảo vệ những điểm có ?. tương ứng. Một toán tử null-safe ở đầu đường dẫn không tự động bảo vệ mọi property phía sau.

## 7. Active object trong Map selection và projection

Khi SpEL duyệt Map bằng selection hoặc projection, object hiện tại là entry của Map. Có thể truy cập key và value:

~~~spel
#scores.?[#this.value >= 80]
#scores.![#this.key]
~~~

Trong predicate:

- #this là Map.Entry hiện tại.
- #this.key là khóa của entry.
- #this.value là giá trị của entry.

Nếu expression cố đọc một property domain trực tiếp như #this.name, nhưng active object thực tế là Map.Entry, property đó có thể không tồn tại. Hãy kiểm tra kiểu receiver trước khi sửa tên property.

Ví dụ:

~~~spel
#scores.?[value >= #root.minimumScore]
~~~

Trong biểu thức này, value được tra cứu trên entry hiện tại, còn #root.minimumScore được tra cứu trên root object ban đầu.

## 8. Active object khi gọi method

Với lời gọi:

~~~spel
customer.calculateDiscount(#amount)
~~~

receiver của calculateDiscount là object được property customer trả về. Nếu customer null, method không thể được gọi. Nếu customer tồn tại nhưng runtime type không có method tương thích, lỗi nằm ở method resolution trên kiểu đó.

Có thể tách bước:

~~~spel
customer
customer.calculateDiscount(#amount)
~~~

Sau đó kiểm tra:

- customer có null không?
- Kiểu runtime của customer là gì?
- Method có tồn tại trên kiểu đó hoặc kiểu được resolver hỗ trợ không?
- Số lượng và kiểu đối số có phù hợp không?
- Có MethodResolver tùy chỉnh hoặc giới hạn quyền truy cập nào không?

Nếu method có overload, kiểu runtime của đối số cũng quan trọng. Một receiver đúng nhưng đối số không tương thích vẫn có thể làm method resolution thất bại.

Đối với method call không có receiver tường minh:

~~~spel
calculateDiscount(#amount)
~~~

method được tìm trên object hiện tại. Ở cấp ngoài cùng, đó thường là root object; bên trong các cấu trúc có active context riêng, cần xác định #this tại đúng vị trí.

## 9. Active object khi dùng indexer

Indexer có thể truy cập array, List hoặc Map:

~~~spel
items[0]
settings['theme']
orders[1].customer.name
~~~

Cần xác định receiver của chính thao tác index và receiver của property tiếp theo:

| Đoạn | Receiver |
|---|---|
| items[0] | Collection hoặc array items |
| settings['theme'] | Map settings |
| orders[1] | Collection orders |
| orders[1].customer | Phần tử tại index 1 |
| orders[1].customer.name | Customer của phần tử đó |

Nếu lỗi ở indexer, kiểm tra object nguồn, kiểu collection, chỉ số hoặc khóa và giới hạn index. Nếu index thành công nhưng property tiếp theo lỗi, hãy kiểm tra object phần tử mà indexer trả về.

Null-safe indexer có cú pháp ?.[] trong Spring Framework 6.2 trở lên:

~~~spel
#orders?.[0]
~~~

Nó bảo vệ trường hợp collection null. Nó không tự xử lý collection rỗng hoặc index ngoài phạm vi.

## 10. Đọc thông tin từ SpelEvaluationException

Khi evaluation thất bại, SpEL thường ném SpelEvaluationException hoặc exception liên quan. Thông tin exception có thể giúp xác định loại thao tác bị lỗi và vị trí trong expression.

Khi bắt lỗi, hãy giữ nguyên exception:

~~~java
try {
    Object result = expression.getValue(context);
} catch (SpelEvaluationException ex) {
    log.error(
        "SpEL evaluation failed: messageCode={}, position={}, inserts={}",
        ex.getMessageCode(),
        ex.getPosition(),
        Arrays.toString(ex.getInserts()),
        ex
    );
    throw ex;
}
~~~

Các thông tin hữu ích gồm:

- **Message code:** loại lỗi SpEL, chẳng hạn property không tồn tại hoặc method không được tìm thấy.
- **Position:** vị trí trong expression mà lỗi được báo cáo.
- **Inserts:** các giá trị ngữ cảnh được dùng để tạo thông báo lỗi.
- **Cause:** exception gốc nếu lỗi phát sinh từ accessor, converter, method hoặc thành phần khác.

API và nội dung message cụ thể có thể thay đổi theo phiên bản Spring. Hãy xem exception gốc và stack trace đầy đủ thay vì chỉ ghi message.

## 11. Đọc receiver từ thông báo lỗi

Thông báo SpEL thường chứa kiểu object mà thao tác không thực hiện được trên đó.

Ví dụ minh họa:

~~~text
Property or field 'city' cannot be found on object of type '...Address'
~~~

Thông báo cho biết property city đang được giải quyết trên object có kiểu runtime Address. Khi đó, cần kiểm tra:

- Address thực tế có property city không?
- Getter hoặc PropertyAccessor có thể truy cập property không?
- Object runtime có phải implementation khác dự kiến không?
- Tên property có viết đúng convention không?

Với lỗi method, thông báo có thể nêu tên method và kiểu object mà SpEL đang tìm method. Dùng kiểu đó để kiểm tra chữ ký, overload và quyền truy cập.

Thông báo lỗi không phải lúc nào cũng hiển thị toàn bộ object hoặc đường dẫn. Kết hợp message code với việc đánh giá từng đoạn trung gian sẽ cho kết quả đáng tin cậy hơn.

## 12. Không có API công khai chung để lấy active object sau khi lỗi đã xảy ra

Sau khi evaluation ném exception và stack đã unwound, không nên giả định EvaluationContext cung cấp một phương thức chung như getActiveObject() để trả receiver tại đúng AST node gây lỗi.

EvaluationContext cung cấp root object và các dịch vụ đánh giá. #this có ý nghĩa trong phạm vi expression đang chạy, nhưng không phải là một API để đọc trạng thái nội bộ của expression sau khi exception đã thoát ra ngoài.

Cách chẩn đoán ổn định là:

1. Lấy root object từ context.
2. Xác định đoạn expression bị lỗi.
3. Đánh giá riêng các đoạn đường dẫn trước điểm lỗi.
4. Kiểm tra giá trị và kiểu runtime của từng kết quả trung gian.
5. Nếu lỗi nằm trong selection/projection, kiểm tra phần tử hiện tại và dùng #this đúng phạm vi.
6. Giữ exception gốc để đọc message code, position và stack trace.

Không nên phụ thuộc vào lớp nội bộ của SpEL hoặc trạng thái evaluator không được công khai như một API ứng dụng.

## 13. Phân biệt lỗi parsing và lỗi truy cập runtime

Active object chỉ có ý nghĩa khi expression đang được đánh giá. Nếu chuỗi expression sai cú pháp và parseExpression thất bại, chưa có receiver runtime nào được truy cập.

Hai giai đoạn:

| Giai đoạn | Ví dụ lỗi | Cách điều tra |
|---|---|---|
| Parsing | Thiếu dấu ngoặc, toán tử hoặc delimiter | Kiểm tra cú pháp và vị trí trong chuỗi |
| Evaluation | Property không tồn tại, object null, method không phù hợp | Xác định active receiver và dữ liệu runtime |

Ví dụ:

~~~java
Expression expression =
    parser.parseExpression("customer.address.city");
~~~

Nếu dòng parseExpression thất bại, hãy kiểm tra cú pháp. Nếu parse thành công nhưng getValue(context) thất bại, hãy điều tra object graph và receiver tại điểm truy cập.

Việc phân biệt hai giai đoạn tránh mất thời gian kiểm tra dữ liệu runtime khi parser chưa tạo được Expression.

## 14. Kiểm tra PropertyAccessor và MethodResolver sau khi xác định receiver

Khi đã biết active object và kiểu runtime, hãy kiểm tra cơ chế truy cập tương ứng.

### Property access

Nếu lỗi ở:

~~~spel
customer.address.city
~~~

hãy kiểm tra PropertyAccessor đang được đăng ký trong EvaluationContext. StandardEvaluationContext thường có accessor reflection mặc định; ứng dụng cũng có thể đăng ký accessor tùy chỉnh.

Một property có thể tồn tại trong source nhưng accessor hiện tại không thể đọc hoặc ghi nó theo cấu hình đang dùng.

### Method invocation

Nếu lỗi ở:

~~~spel
customer.calculateDiscount(#amount)
~~~

hãy kiểm tra MethodResolver. StandardEvaluationContext thường có ReflectiveMethodResolver mặc định, nhưng context tùy chỉnh có thể giới hạn hoặc thay đổi việc tìm method.

Kiểu receiver là đầu mối đầu tiên; kiểu đối số và resolver quyết định method nào có thể được gọi.

## 15. Kiểm tra chuyển đổi kiểu khi lỗi xảy ra ở property hoặc method

Một số expression tìm đúng receiver và property/method nhưng thất bại khi chuyển đổi kiểu.

Ví dụ gán:

~~~spel
retryCount = 'five'
~~~

Receiver có thể đúng là RetrySettings và property retryCount có thể writable, nhưng TypeConverter không chuyển được chuỗi five sang Integer.

Tương tự, method có thể tồn tại nhưng đối số cần chuyển đổi sang kiểu tham số mà converter không hỗ trợ.

Khi đó cần kiểm tra:

- Kiểu đầu vào thực tế.
- Kiểu property hoặc tham số method yêu cầu.
- TypeConverter và ConversionService trong context.
- Giá trị có đúng định dạng không.

Đừng quy lỗi conversion thành lỗi active object. Receiver có thể hoàn toàn đúng; vấn đề nằm ở kiểu giá trị được truyền vào thao tác.

## 16. Ví dụ hoàn chỉnh: tìm receiver gây lỗi trong đường dẫn lồng nhau

Giả sử có các lớp:

~~~java
public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
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

Tạo object:

~~~java
Address address = new Address();
address.setCity("Ho Chi Minh City");

Customer customer = new Customer();
customer.setAddress(address);

Order order = new Order();
order.setCustomer(customer);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

ExpressionParser parser = new SpelExpressionParser();
~~~

Đánh giá từng đoạn:

~~~java
Object root =
    context.getRootObject().getValue();

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

Có thể kiểm tra:

~~~java
System.out.println(describe(root));
System.out.println(describe(customerValue));
System.out.println(describe(addressValue));
System.out.println(cityValue);
~~~

Kết quả cuối cùng là Ho Chi Minh City.

Nếu customer hoặc address bị đặt thành null, lần đánh giá đầu tiên không còn trả về object hợp lệ sẽ xác định nơi đường dẫn bị đứt. Nếu address tồn tại nhưng getter city hoặc PropertyAccessor có vấn đề, receiver cần kiểm tra là Address.

Ví dụ này minh họa cách cô lập từng đoạn đường dẫn thay vì suy đoán từ root object.

## 17. Ví dụ: xác định #this trong selection

Giả sử root object có danh sách đơn hàng và ngưỡng:

~~~java
public class OrderSelectionInput {
    private final List<OrderSummary> orders;
    private final BigDecimal minimum;

    public OrderSelectionInput(
            List<OrderSummary> orders,
            BigDecimal minimum) {
        this.orders = orders;
        this.minimum = minimum;
    }

    public List<OrderSummary> getOrders() {
        return orders;
    }

    public BigDecimal getMinimum() {
        return minimum;
    }
}
~~~

Expression:

~~~spel
orders.?[#this.total >= #root.minimum]
~~~

Để chẩn đoán:

1. Đánh giá orders riêng và kiểm tra collection có null không.
2. Kiểm tra từng phần tử có null không.
3. Xác nhận mỗi phần tử có getter total và kiểu trả về phù hợp.
4. Xác nhận root object có property minimum.
5. Kiểm tra kiểu của total và minimum nếu lỗi xảy ra trong phép so sánh.

Trong predicate, #this là OrderSummary đang được kiểm tra; #root vẫn là OrderSelectionInput. Nếu một phần tử có kiểu khác hoặc null, lỗi có thể chỉ xảy ra ở một lượt duyệt cụ thể.

## 18. Quy trình chẩn đoán theo loại lỗi

| Dấu hiệu | Active object cần kiểm tra | Thành phần tiếp theo |
|---|---|---|
| Property không tồn tại | Receiver ngay trước tên property | PropertyAccessor, getter, runtime class |
| Method không tìm thấy | Receiver trước dấu chấm hoặc current object | MethodResolver, chữ ký, kiểu đối số |
| Dereference null | Giá trị trả về của đoạn ngay trước | Dữ liệu null, null-safe navigation |
| Index lỗi | Array/List/Map nhận index | Kiểu collection, index/key, kích thước |
| Conversion lỗi | Receiver của property hoặc method call | TypeConverter, TypeDescriptor |
| Selection/projection lỗi | Phần tử hiện tại #this | Null phần tử, property và kiểu phần tử |
| Type reference lỗi | Không phải receiver property thông thường | TypeLocator, classloader |
| Parse error | Chưa có active object runtime | Cú pháp và delimiter |

Bảng này giúp chọn đúng hướng điều tra sau khi đọc thông báo lỗi. Đừng sửa PropertyAccessor khi lỗi thực chất đến từ TypeConverter hoặc một phần tử null trong collection.

## 19. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Active object luôn là root object.**  
Ở cấp ngoài cùng, #this thường trùng #root. Trong selection và projection, #this là phần tử hiện tại; trong đường dẫn lồng nhau, receiver của từng đoạn là object được đoạn trước trả về.

**Nhầm lẫn 2: Kiểu khai báo luôn là kiểu runtime.**  
Proxy, subclass hoặc implementation khác có thể làm kiểu thực tế khác với kiểu mà người viết expression dự đoán.

**Nhầm lẫn 3: Lỗi ở property cuối cùng nghĩa là root thiếu property đó.**  
Trong customer.address.city, receiver của city là Address, không phải Order.

**Nhầm lẫn 4: #this luôn có thể được dùng để lấy object gây lỗi sau khi exception thoát ra.**  
#this là tham chiếu trong phạm vi evaluation. Sau khi stack unwinds, hãy cô lập và đánh giá các đoạn trung gian để tìm receiver.

**Nhầm lẫn 5: Null-safe operator ở đầu đường dẫn bảo vệ toàn bộ phần còn lại.**  
Mỗi đoạn có thể null cần được bảo vệ tại vị trí tương ứng.

**Nhầm lẫn 6: Mọi lỗi truy cập đều là lỗi active object.**  
Lỗi còn có thể đến từ PropertyAccessor, MethodResolver, TypeConverter, index hoặc cú pháp parsing.

**Nhầm lẫn 7: Parse error cũng có active receiver.**  
Khi parse thất bại, expression chưa được đánh giá nên chưa có object runtime nhận thao tác.

## 20. Ghi nhớ

- Active object là object nhận thao tác tại vị trí hiện tại của expression.
- #root tham chiếu root object của toàn bộ lần đánh giá; #this tham chiếu object hiện tại.
- Trong selection và projection, #this thay đổi theo phần tử đang được xử lý.
- Với property path lồng nhau, receiver của mỗi đoạn là object được đoạn trước trả về.
- Khi lỗi xảy ra, đánh giá riêng các đoạn expression tăng dần để xác định receiver cuối cùng hoạt động thành công.
- Kiểm tra kiểu runtime bằng getClass() sau khi loại trừ null; đừng chỉ dựa vào kiểu khai báo.
- SpelEvaluationException có thể cung cấp message code, vị trí và thông tin chẩn đoán; giữ nguyên exception và stack trace.
- Không có API công khai chung để lấy active object sau khi evaluation đã ném lỗi; hãy cô lập đường dẫn và kiểm tra dữ liệu trung gian.
- Lỗi property, method, index, null và conversion cần kiểm tra các thành phần khác nhau trong EvaluationContext.
- Parse error xảy ra trước evaluation nên không có active receiver runtime.
- Dùng null-safe operator ở từng điểm có khả năng null và kiểm tra riêng phần tử null trong collection.

Khi điều tra một expression SpEL bị lỗi, hãy lần theo đường dẫn từ root đến thao tác thất bại, xác định object nhận từng property, method hoặc index, rồi kiểm tra kiểu runtime và cơ chế truy cập tương ứng. Phân biệt rõ #root với #this sẽ giúp tìm đúng receiver thay vì sửa nhầm root object hoặc một tầng không liên quan.
