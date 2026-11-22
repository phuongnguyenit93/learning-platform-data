# Property lồng nhau bằng chuỗi dấu chấm

Trong Spring Expression Language (SpEL), dấu chấm **.** dùng để truy cập property của object. Khi một object chứa object khác, có thể nối nhiều lần truy cập property thành một đường dẫn:

~~~text
#order.customer.address.city
~~~

Biểu thức trên lần lượt lấy biến order, đọc property customer, đọc tiếp address, rồi lấy city. Đây là cách viết thường gặp khi dữ liệu nghiệp vụ được tổ chức thành các object lồng nhau như đơn hàng, khách hàng, địa chỉ hoặc cấu hình.

Để đọc và viết các property path đúng cách, cần hiểu SpEL bắt đầu từ đâu, mỗi đoạn trong đường dẫn được phân giải như thế nào và điều gì xảy ra nếu một object trung gian là null.

## 1. Cấu trúc của một property path

Một property path đơn giản có dạng:

~~~text
object.property
~~~

Có thể nối nhiều property:

~~~text
order.customer.address.city
~~~

Mỗi dấu chấm biểu thị một bước truy cập:

1. Lấy object gốc.
2. Đọc property đầu tiên trên object đó.
3. Dùng giá trị vừa đọc làm object nhận cho bước kế tiếp.
4. Lặp lại cho đến property cuối cùng.

Ví dụ với mô hình Java:

~~~java
public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }
}

public class Customer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

Khi có một object Order, biểu thức:

~~~text
customer.address.city
~~~

có thể đọc thành:

- order.getCustomer()
- kết quả đó gọi getAddress()
- kết quả tiếp theo gọi getCity()

SpEL thường dùng cơ chế property access để phân giải property. Với JavaBean thông thường, property được đọc qua getter. Một property có thể được cung cấp bởi PropertyAccessor khác nếu evaluation context được cấu hình để hỗ trợ kiểu object đó.

Dấu chấm là toán tử truy cập property trong expression. Nó không có nghĩa là SpEL đang tìm một chuỗi key chứa dấu chấm trong một Map. Với Map, nên dùng cú pháp indexer theo key như phần sau.

## 2. Bắt đầu property path từ root object hoặc variable

SpEL có thể lấy object gốc từ EvaluationContext hoặc nhận root object trực tiếp khi gọi getValue().

### 2.1. Dùng root object

Nếu truyền một Order làm root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

String city = parser
        .parseExpression("customer.address.city")
        .getValue(order, String.class);
~~~

Trong expression này, customer là property của root object order. Vì vậy không cần thêm tiền tố #order.

### 2.2. Dùng biến trong EvaluationContext

Nếu đăng ký Order thành một biến:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);

String city = parser
        .parseExpression("#order.customer.address.city")
        .getValue(context, String.class);
~~~

Ký hiệu # truy cập variable trong EvaluationContext. Sau khi lấy được biến order, các dấu chấm tiếp tục truy cập property của object đó.

Hai cách viết có điểm bắt đầu khác nhau:

| Cách viết | Điểm bắt đầu | Khi nào dùng |
| --- | --- | --- |
| **customer.address.city** | Root object | Khi getValue() nhận trực tiếp object gốc |
| **#order.customer.address.city** | Variable tên order | Khi object được đăng ký trong EvaluationContext |
| **@orderService.defaultAddress.city** | Spring bean tên orderService | Khi context cho phép bean reference |

Không nên nhầm #order với @order. #order là variable được đưa vào EvaluationContext; @order là bean reference được phân giải qua BeanResolver của context.

## 3. Property lồng nhau trong object graph

### 3.1. Đọc nhiều cấp property

Giả sử Order có customer, Customer có address, và Address có city. Có thể đọc city bằng một expression duy nhất:

~~~text
#order.customer.address.city
~~~

Không cần gọi getter thủ công trong Java expression. SpEL phân giải từng property trong chuỗi.

Một số ví dụ tương tự:

~~~text
#employee.department.manager.name
#invoice.customer.billingAddress.postalCode
#product.category.parent.name
#applicationSettings.database.connectionTimeout
~~~

Property path càng dài thì càng phụ thuộc vào cấu trúc object ở từng bước. Nếu một class đổi tên property hoặc thay đổi kiểu trả về của getter, expression có thể cần được cập nhật.

### 3.2. Property có thể là getter, field hoặc custom accessor

Tên property trong SpEL thường là tên property logic của JavaBean, không nhất thiết là tên field:

~~~java
class Customer {
    private String fullName;

    public String getFullName() {
        return fullName;
    }
}
~~~

Expression dùng:

~~~text
#customer.fullName
~~~

chứ không cần viết getFullName(). Với reflective property access, Spring có thể đọc property thông qua getter và trong những trường hợp được hỗ trợ có thể truy cập field. Quyền truy cập thực tế phụ thuộc vào PropertyAccessor và EvaluationContext được sử dụng.

Nếu một kiểu dữ liệu không theo JavaBean convention, có thể cần đăng ký PropertyAccessor phù hợp. Không nên giả định rằng mọi method đều tự động trở thành property; một method thông thường cần được gọi bằng cú pháp method call, ví dụ:

~~~text
#customer.getDisplayName()
~~~

Nếu class có getter getDisplayName(), property style thường dễ đọc hơn:

~~~text
#customer.displayName
~~~

### 3.3. Property lồng nhau trong Java record

Với record:

~~~java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
~~~

Có thể truy cập component của record bằng property name:

~~~text
#customer.address.city
~~~

Record cung cấp accessor theo tên component. Spring có thể phân giải các property tương ứng thông qua cơ chế truy cập được hỗ trợ trong phiên bản framework đang dùng.

## 4. Điều gì xảy ra khi property trung gian là null?

Một property path thông thường giả định rằng object nhận ở mỗi bước đều tồn tại:

~~~text
#order.customer.address.city
~~~

Nếu order là null, SpEL không thể đọc customer. Nếu customer là null, không thể đọc address. Nếu address là null, không thể đọc city. Những trường hợp này có thể gây EvaluationException khi expression được đánh giá.

### 4.1. Dùng safe-navigation operator

SpEL cung cấp safe-navigation operator **?.** để truy cập property khi object nhận có thể null:

~~~text
#order?.customer?.address?.city
~~~

Nếu một object trung gian là null, phép truy cập tương ứng trả về null thay vì ném lỗi tại chính bước đó.

Cần đặt **?.** ở mỗi ranh giới mà object có thể null. Ví dụ:

~~~text
#order?.customer?.address?.city
~~~

bảo vệ lần lượt order, customer và address.

Không nên chỉ bảo vệ bước đầu rồi giả định các bước sau cũng tự động an toàn:

~~~text
#order?.customer.address.city
~~~

Safe navigation chỉ bảo vệ thao tác ngay sau nó. Nếu customer có thể null, phần truy cập address tiếp theo vẫn có thể lỗi. Hãy xác định rõ các điểm có thể null và dùng safe navigation ở từng điểm đó.

### 4.2. Kết hợp safe navigation với giá trị mặc định

Khi cần một giá trị mặc định, có thể kết hợp safe navigation với Elvis:

~~~text
#order?.customer?.address?.city ?: 'Unknown'
~~~

Expression trả về city khi đường dẫn tồn tại và city có giá trị. Nếu một bước trả về null hoặc city là chuỗi rỗng, Elvis cung cấp Unknown.

Có thể dùng cách này để xây dựng tên hiển thị:

~~~text
#employee?.department?.manager?.name ?: 'Unassigned'
~~~

Safe navigation xử lý object trung gian có thể null; Elvis xử lý kết quả cuối cùng thiếu giá trị.

### 4.3. Safe navigation không tự khởi tạo object

Khi customer hoặc address là null, safe navigation chỉ trả về null cho phép truy cập. Nó không tạo Customer, Address hay bất kỳ object nào để hoàn thiện đường dẫn.

Nếu cần khởi tạo object lồng nhau, hãy thực hiện trong Java service hoặc trong logic cấu hình có chủ đích. Property path chỉ đọc dữ liệu không tự làm đầy object graph.

## 5. Kết hợp dấu chấm với Map, List và array

Property path có thể kết hợp với indexer để truy cập cấu trúc dữ liệu lồng nhau. Dấu chấm và dấu ngoặc vuông đảm nhiệm hai vai trò khác nhau:

- Dấu chấm truy cập property của object.
- Dấu ngoặc vuông truy cập phần tử collection, array hoặc giá trị trong Map.

### 5.1. Truy cập Map theo key

Với Map, dùng key trong dấu ngoặc vuông:

~~~text
#order.attributes['priority']
#settings['database']['url']
~~~

Có thể tiếp tục đi vào property của object được lấy từ Map:

~~~text
#order.attributes['shippingAddress'].city
~~~

Trong ví dụ cuối, attributes là Map, shippingAddress là key, còn city là property của object được lưu tại key đó.

Nếu key không tồn tại, kết quả truy cập Map có thể là null. Khi đường dẫn còn tiếp tục, hãy xử lý null ở bước tiếp theo hoặc dùng safe navigation phù hợp với kiểu dữ liệu và phiên bản SpEL.

### 5.2. Truy cập phần tử List hoặc array

Dùng index bắt đầu từ 0:

~~~text
#order.lines[0].product.name
~~~

Expression lấy phần tử đầu tiên trong lines, đọc product rồi lấy name.

Có thể kết hợp property path với nhiều index:

~~~text
#matrix[0][1]
#departments[0].employees[2].name
~~~

Chỉ số phải nằm trong giới hạn hợp lệ. Nếu List rỗng, index vượt phạm vi hoặc array không có phần tử tương ứng, việc đánh giá có thể thất bại. Hãy kiểm tra kích thước trước khi truy cập nếu dữ liệu đầu vào không được bảo đảm.

### 5.3. Kết hợp property, Map và List

Một đường dẫn thực tế có thể đi qua nhiều kiểu dữ liệu:

~~~text
#response.data['orders'][0].customer.address.city
~~~

Cách phân giải:

1. Lấy variable response.
2. Đọc property data.
3. Lấy key orders trong Map.
4. Lấy phần tử có index 0.
5. Đọc customer.
6. Đọc address.
7. Đọc city.

Khi một expression kết hợp nhiều loại cấu trúc, hãy đọc lần lượt từ trái sang phải và xác định kiểu của giá trị sau mỗi bước. Cách này giúp tìm đúng vị trí gây lỗi khi một key, index hoặc property không tồn tại.

## 6. Dùng nested property path trong cấu hình Spring

SpEL được tích hợp ở nhiều điểm của Spring. Khi một annotation cung cấp object hoặc tham số vào EvaluationContext, có thể dùng property path để lấy sâu một giá trị cần thiết.

### 6.1. Tạo cache key từ property lồng nhau

Ví dụ cache theo ID của khách hàng trong đơn hàng:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "#order.customer.id"
)
public OrderSummary summarize(Order order) {
    // ...
}
~~~

Expression đọc customer rồi lấy id. Cần bảo đảm order và customer tồn tại khi cache key được đánh giá. Nếu customer có thể null, hãy định nghĩa key dự phòng rõ ràng:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "#order?.customer?.id ?: 'unknown'"
)
public OrderSummary summarize(Order order) {
    // ...
}
~~~

Với hệ thống nhiều tenant hoặc nhiều khách hàng, không nên gom các trường hợp thiếu ID vào cùng một key nếu điều đó có thể khiến dữ liệu cache bị chia sẻ sai phạm vi. Giá trị mặc định phải phù hợp với quy tắc định danh của ứng dụng.

### 6.2. Dùng trong Method Security

Có thể kiểm tra quyền truy cập dựa trên property lồng nhau của tham số:

~~~java
@PreAuthorize(
    "#order.customer.id == authentication.principal.customerId"
)
public Order findOrder(Order order) {
    // ...
}
~~~

Expression so sánh customer ID trong order với customer ID của principal đang đăng nhập. Đây là phép so sánh theo equality của SpEL.

Tên tham số như order cần được Spring phát hiện đúng. Tùy cách biên dịch, có thể cần bật tùy chọn Java -parameters hoặc dùng annotation cung cấp tên tham số theo cơ chế của Spring Security.

Nếu order hoặc customer có thể null, cần viết điều kiện an toàn và rõ ràng:

~~~java
@PreAuthorize(
    "#order != null and #order.customer != null and " +
    "#order.customer.id == authentication.principal.customerId"
)
~~~

SpEL dùng phép AND có short-circuit, nên vế sau chỉ được đánh giá khi các điều kiện trước đúng. Dù vậy, hãy bảo đảm context security cung cấp principal với cấu trúc như expression mong đợi.

### 6.3. Đọc property lồng nhau từ Spring bean

Có thể tham chiếu một bean rồi đọc các property lồng nhau của nó:

~~~java
@Value("#{ @appSettings.database.region }")
private String databaseRegion;
~~~

Ở đây **@appSettings** là bean reference; **database** và **region** là các property được truy cập tiếp theo. Cách này cần EvaluationContext có BeanResolver, như context do Spring thiết lập cho điểm tích hợp tương ứng.

Nếu chỉ đọc một giá trị cấu hình đơn giản, property placeholder thường phù hợp hơn. Dùng nested SpEL khi giá trị nằm trong object do bean cung cấp hoặc cần kết hợp nhiều phép truy cập.

## 7. Kiểm tra property path bằng SpEL parser

Có thể tạo một test nhỏ để kiểm tra đường dẫn lồng nhau:

~~~java
class NestedPropertyExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsNestedCityFromRootObject() {
        Address address = new Address("Da Nang");
        Customer customer = new Customer(address);
        Order order = new Order(customer);

        String city = parser
                .parseExpression("customer.address.city")
                .getValue(order, String.class);

        assertEquals("Da Nang", city);
    }

    @Test
    void readsNestedCityFromVariable() {
        Address address = new Address("Ha Noi");
        Customer customer = new Customer(address);
        Order order = new Order(customer);

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("order", order);

        String city = parser
                .parseExpression("#order.customer.address.city")
                .getValue(context, String.class);

        assertEquals("Ha Noi", city);
    }
}
~~~

Test đầu truyền Order làm root object. Test thứ hai đưa Order vào context dưới tên order rồi truy cập qua #order. Cả hai đều kiểm tra đường dẫn property được phân giải đến đúng giá trị cuối cùng.

Nên bổ sung test cho trường hợp customer hoặc address null nếu dữ liệu thực tế cho phép các trạng thái đó. Có thể kiểm tra expression dùng safe navigation:

~~~java
context.setVariable("order", orderWithMissingAddress);

String city = parser
        .parseExpression("#order?.customer?.address?.city ?: 'Unknown'")
        .getValue(context, String.class);

assertEquals("Unknown", city);
~~~

Khi kiểm tra một expression trong annotation, ngoài parser test còn cần test integration point để xác nhận module cung cấp đúng tham số, root object, bean resolver và quyền truy cập property.

## 8. Những lỗi thường gặp khi dùng property path lồng nhau

1. **Quên tiền tố biến:** dùng order.customer.city trong khi order chỉ được đăng ký là variable. Khi đó phải viết #order.customer.city.
2. **Nhầm variable với bean:** #order là variable; @order là bean reference và cần BeanResolver.
3. **Property trung gian null:** nếu customer hoặc address null, truy cập tiếp có thể gây EvaluationException.
4. **Chỉ dùng safe navigation ở bước đầu:** #order?.customer.address.city chưa bảo vệ customer và address nếu chúng có thể null.
5. **Nhầm Map key với property:** dùng #settings['region'] để truy cập key trong Map; dấu chấm dành cho property của object.
6. **Index không hợp lệ:** #items[0] có thể lỗi nếu collection rỗng hoặc index vượt giới hạn.
7. **Tên property không đúng:** SpEL phân giải tên property theo accessor; cần dùng đúng tên JavaBean/record component hoặc accessor tùy chỉnh.
8. **Getter gây side effect hoặc ném exception:** đọc property có thể gọi getter; getter nên ổn định và không thực hiện thao tác nghiệp vụ bất ngờ.
9. **Giả định mọi context có cùng quyền truy cập:** StandardEvaluationContext và SimpleEvaluationContext có khả năng truy cập khác nhau. SimpleEvaluationContext có thể giới hạn property accessor, method resolver và bean reference tùy cách xây dựng.

## 9. Ghi nhớ nhanh

- Dấu chấm **.** nối các lần truy cập property trong object graph.
- **customer.address.city** bắt đầu từ root object; **#order.customer.address.city** bắt đầu từ variable.
- **@beanName.property** bắt đầu từ bean reference khi context hỗ trợ BeanResolver.
- SpEL phân giải từng property từ trái sang phải; property ở bước sau được đọc trên object trả về từ bước trước.
- JavaBean property thường được đọc qua getter; accessor có thể được mở rộng bằng PropertyAccessor.
- Dùng **['key']** cho Map và **[index]** cho List/array.
- Object trung gian null có thể làm property path thất bại; dùng **?.** ở mỗi bước có thể null.
- Safe navigation không khởi tạo object và không tự bảo vệ các bước tiếp theo nếu không đặt ở đúng vị trí.
- Property path trong cache, security và các annotation khác dùng EvaluationContext riêng của integration point.
- Kiểm thử cả đường dẫn thành công, null ở giữa, key thiếu và index ngoài phạm vi.

## 10. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Properties, Arrays, Lists, Maps and Indexers](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
