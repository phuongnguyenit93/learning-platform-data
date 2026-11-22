# Read-only data binding và dữ liệu nguồn trong Spring Expression Language (SpEL)

Spring Expression Language (SpEL) có thể đọc property từ một đối tượng dữ liệu được cung cấp khi đánh giá biểu thức. Trong những trường hợp chỉ cần tra cứu hoặc tính toán từ dữ liệu đầu vào, ứng dụng có thể dùng SimpleEvaluationContext với chế độ read-only data binding.

Cách cấu hình này giúp biểu thức truy cập property theo cơ chế data binding và giới hạn các khả năng nâng cao của SpEL. Nó phù hợp với những biểu thức cần đọc dữ liệu từ DTO, object cấu hình hoặc mô hình dữ liệu phục vụ báo cáo mà không cần thay đổi property của đối tượng nguồn.

Điểm cần nhớ là read-only property access chỉ giới hạn thao tác truy cập property thông qua context. Nó không tự biến toàn bộ object graph thành dữ liệu bất biến: nếu getter trả về một List hoặc object có thể thay đổi, mã Java khác vẫn có thể sửa đối tượng đó. Vì vậy, cần thiết kế dữ liệu nguồn và phạm vi biểu thức một cách có chủ đích.

## 1. Read-only data binding là gì?

Data binding là cách ánh xạ tên property trong biểu thức tới dữ liệu của một đối tượng. Ví dụ, khi root object có getter getName() và getAge(), SpEL có thể đánh giá các biểu thức:

~~~text
name
age >= 18
name + ' - ' + age
~~~

Read-only data binding cho phép đọc những property được accessor hỗ trợ, đồng thời không cung cấp quyền ghi property qua cơ chế binding đó.

Một trường hợp sử dụng phổ biến là đánh giá quy tắc hoặc tạo nội dung hiển thị từ dữ liệu đầu vào:

- Đọc trạng thái của tài khoản để quyết định có hiển thị một chức năng hay không.
- Tính một nhãn từ tên, trạng thái và ngày hiệu lực.
- Lọc hoặc chiếu một collection để tạo dữ liệu báo cáo.
- Đọc các trường cấu hình đã được ứng dụng chuẩn bị sẵn.

Nếu biểu thức chỉ cần đọc dữ liệu, việc chọn context read-only giúp thu hẹp khả năng mà biểu thức có thể sử dụng.

## 2. Dữ liệu nguồn và root object

Dữ liệu nguồn là đối tượng hoặc mô hình dữ liệu mà ứng dụng truyền vào khi đánh giá biểu thức. Trong SpEL, đối tượng này thường đóng vai trò root object.

Ví dụ, lớp CustomerSource chỉ cung cấp các getter:

~~~java
public class CustomerSource {
    private final String name;
    private final int age;
    private final boolean active;

    public CustomerSource(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Tạo dữ liệu nguồn:

~~~java
CustomerSource source =
        new CustomerSource("Lan", 25, true);
~~~

Khi đánh giá biểu thức name, SpEL tìm property name trên root object source. Biểu thức không cần ghi tiền tố biến:

~~~text
name
age >= 18
active and age >= 18
~~~

Có thể tham chiếu tường minh đến root object bằng #root:

~~~text
#root.name
#root.age >= 18
~~~

Root object là dữ liệu được cung cấp cho lần đánh giá. Nó không phải EvaluationContext và cũng không phải ExpressionParser.

## 3. Tạo SimpleEvaluationContext ở chế độ read-only

Spring cung cấp SimpleEvaluationContext để đánh giá biểu thức với một tập tính năng giới hạn. Với trường hợp chỉ cần đọc property theo quy tắc data binding, có thể dùng builder forReadOnlyDataBinding():

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("name");

CustomerSource source =
        new CustomerSource("Lan", 25, true);

String name = expression.getValue(
        context,
        source,
        String.class
);
~~~

Trong ví dụ:

1. forReadOnlyDataBinding() tạo builder dành cho property access chỉ đọc.
2. build() tạo SimpleEvaluationContext.
3. parseExpression("name") phân tích biểu thức.
4. getValue(context, source, String.class) đánh giá biểu thức với source làm root object và yêu cầu kết quả String.

SimpleEvaluationContext được thiết kế cho những tình huống không cần toàn bộ tính năng của StandardEvaluationContext. Cấu hình read-only data binding cung cấp property accessor phù hợp cho việc đọc dữ liệu.

## 4. Vì sao dùng SimpleEvaluationContext?

StandardEvaluationContext cung cấp nhiều khả năng đánh giá, có thể bao gồm truy cập property, gọi method, biến, function, bean resolver và type locator. Những khả năng này hữu ích cho biểu thức nội bộ có yêu cầu đầy đủ, nhưng có thể rộng hơn mức cần thiết khi chỉ đọc dữ liệu.

SimpleEvaluationContext cho phép ứng dụng chọn tập tính năng nhỏ hơn. Chế độ read-only data binding phù hợp khi:

- Biểu thức chỉ cần đọc JavaBean property.
- Không cần ghi ngược dữ liệu vào đối tượng nguồn.
- Không cần tham chiếu bean hoặc type.
- Không cần tạo object từ biểu thức.
- Muốn giới hạn khả năng đánh giá trong một luồng data binding.

Context giới hạn không phải sandbox tuyệt đối. Ứng dụng vẫn cần kiểm soát root object, dữ liệu mà getter trả về và các khả năng bổ sung nếu tự cấu hình builder.

## 5. Đọc property lồng nhau từ dữ liệu nguồn

Dữ liệu nguồn thường chứa các object lồng nhau. SpEL có thể đọc property qua nhiều cấp nếu accessor hỗ trợ các property tương ứng.

Ví dụ:

~~~java
public class AddressSource {
    private final String city;
    private final String country;

    public AddressSource(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}

public class CustomerProfile {
    private final String name;
    private final AddressSource address;

    public CustomerProfile(String name, AddressSource address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public AddressSource getAddress() {
        return address;
    }
}
~~~

Đánh giá property lồng nhau:

~~~java
CustomerProfile source = new CustomerProfile(
        "An",
        new AddressSource("Da Nang", "VN")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression cityExpression =
        parser.parseExpression("address.city");

String city = cityExpression.getValue(
        context,
        source,
        String.class
);
~~~

Biểu thức address.city đọc property address từ root object rồi đọc city từ object AddressSource được trả về.

Read-only áp dụng cho thao tác property access do context cung cấp. Nếu object lồng nhau có setter hoặc collection mutable, không nên suy luận rằng toàn bộ object graph đã trở thành immutable. Hãy cung cấp các DTO hoặc view object chỉ chứa dữ liệu cần thiết.

## 6. Dùng collection làm dữ liệu nguồn

Dữ liệu nguồn có thể chứa List hoặc Map. SpEL hỗ trợ truy cập phần tử, selection và projection khi các property cần thiết có thể được đọc.

Ví dụ lớp OrderSource:

~~~java
public class OrderSource {
    private final String code;
    private final String status;
    private final BigDecimal total;

    public OrderSource(String code, String status, BigDecimal total) {
        this.code = code;
        this.status = status;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

public class OrderReportSource {
    private final List<OrderSource> orders;

    public OrderReportSource(List<OrderSource> orders) {
        this.orders = Collections.unmodifiableList(
                new ArrayList<>(orders)
        );
    }

    public List<OrderSource> getOrders() {
        return orders;
    }
}
~~~

Tạo context và lọc dữ liệu:

~~~java
OrderReportSource source = new OrderReportSource(
        Arrays.asList(
                new OrderSource("A-100", "PAID", new BigDecimal("120.00")),
                new OrderSource("A-101", "PENDING", new BigDecimal("80.00")),
                new OrderSource("A-102", "PAID", new BigDecimal("250.00"))
        )
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID'].![total]"
);

List<?> paidTotals = expression.getValue(
        context,
        source,
        List.class
);
~~~

Biểu thức selection giữ các đơn có status là PAID. Projection tạo danh sách total của các đơn đã chọn.

Collections được trả về từ getter cũng là một phần của dữ liệu nguồn. Dùng defensive copy và wrapper không sửa đổi như Collections.unmodifiableList có thể giúp tránh thay đổi ngoài ý muốn từ mã Java khác. Tuy nhiên, wrapper không làm các object bên trong trở thành immutable; cần thiết kế cả phần tử collection nếu muốn dữ liệu nguồn ổn định.

## 7. Read-only property access và thao tác ghi

Trong chế độ read-only data binding, property accessor được cấu hình để đọc property. Biểu thức gán như sau không phải mục đích của context:

~~~text
name = 'New name'
~~~

Tương tự, mã Java gọi setValue() để ghi property sẽ không có quyền ghi thông qua read-only accessor. Tùy vị trí và cách đánh giá, thao tác ghi có thể phát sinh lỗi SpEL vì property không writable.

Ví dụ minh họa ý định read-only:

~~~java
Expression expression = parser.parseExpression("name");

String currentName = expression.getValue(
        context,
        source,
        String.class
);

// Không dùng context read-only để ghi:
// expression.setValue(context, source, "New name");
~~~

Nếu ứng dụng thực sự cần cập nhật dữ liệu, hãy dùng một luồng ghi riêng với validation và quyền phù hợp. Không nên chuyển sang context có quyền ghi chỉ để làm cho một biểu thức đọc dữ liệu hoạt động.

Read-only binding cũng không ngăn một getter tự nó có tác dụng phụ. Getter nên trả về dữ liệu và tránh thực hiện thao tác ghi, gọi dịch vụ bên ngoài hoặc thay đổi trạng thái.

## 8. Read-only không đồng nghĩa với immutable

Đây là điểm quan trọng khi thiết kế dữ liệu nguồn.

Read-only property accessor giới hạn việc gán property thông qua SpEL. Nó không bảo đảm:

- Field bên trong đối tượng không thể thay đổi bởi mã Java khác.
- Getter chỉ trả về giá trị bất biến.
- List hoặc Map được trả về không thể sửa đổi.
- Các phần tử bên trong collection không thể thay đổi.
- Getter không thực hiện tác dụng phụ.

Ví dụ, getter sau trả về trực tiếp một List mutable:

~~~java
public List<String> getRoles() {
    return roles;
}
~~~

Biểu thức có thể chỉ đọc property roles, nhưng đối tượng List trả về vẫn có thể mutable nếu mã Java khác giữ tham chiếu và thay đổi nó.

Có thể giảm rủi ro bằng cách tạo bản sao không sửa đổi:

~~~java
public List<String> getRoles() {
    return Collections.unmodifiableList(new ArrayList<>(roles));
}
~~~

Với object lồng nhau, dùng DTO chỉ đọc hoặc trả về các giá trị bất biến phù hợp. Mục tiêu là kiểm soát dữ liệu mà biểu thức nhìn thấy, không chỉ cấu hình quyền ghi property ở tầng SpEL.

## 9. Dùng biến cùng dữ liệu nguồn

EvaluationContext có thể cung cấp biến để biểu thức kết hợp dữ liệu từ root object với một giá trị bổ sung. Với SimpleEvaluationContext, chỉ dùng các khả năng được API và builder của context hỗ trợ; không giả định context có mọi chức năng của StandardEvaluationContext.

Khi cần truyền một ngưỡng hoặc tham số vào biểu thức, có thể đưa nó vào dữ liệu nguồn như một property:

~~~java
public class EligibilitySource {
    private final int age;
    private final int minimumAge;

    public EligibilitySource(int age, int minimumAge) {
        this.age = age;
        this.minimumAge = minimumAge;
    }

    public int getAge() {
        return age;
    }

    public int getMinimumAge() {
        return minimumAge;
    }
}
~~~

Biểu thức:

~~~text
age >= minimumAge
~~~

Cách này làm các đầu vào hiển thị rõ ràng trong source object. Nếu ứng dụng cần biến EvaluationContext, hãy cấu hình biến bằng API phù hợp và kiểm tra rằng loại SimpleEvaluationContext đang dùng hỗ trợ đúng thao tác đó.

Đối với biểu thức cấu hình có nhiều đầu vào, một source DTO có tên property rõ ràng thường dễ hiểu và dễ kiểm thử.

## 10. Null và dữ liệu nguồn không đầy đủ

Dữ liệu nguồn có thể chứa null ở root object, property hoặc object lồng nhau. Cần xác định rõ hành vi khi dữ liệu thiếu.

Ví dụ, nếu address có thể null, biểu thức:

~~~text
address.city
~~~

có thể phát sinh lỗi khi address là null. Có thể dùng safe navigation:

~~~text
address?.city
~~~

Safe navigation trả về null khi phần bên trái là null, thay vì tiếp tục truy cập property.

Ở phía Java, kiểm tra root object trước khi đánh giá nếu nó có thể null:

~~~java
if (source == null) {
    throw new IllegalArgumentException("Source data is required");
}

String city = parser.parseExpression("address?.city")
        .getValue(context, source, String.class);
~~~

Khi kết quả có thể null, kiểu nhận và logic phía sau cần cho phép null. Không nên mặc định null tương đương chuỗi rỗng, số 0 hoặc false.

Với collection có thể null, dùng safe navigation phù hợp và xử lý kết quả null riêng với collection rỗng. Hai trạng thái này có ý nghĩa khác nhau: null có thể biểu thị dữ liệu chưa được cung cấp, còn collection rỗng biểu thị đã có collection nhưng không có phần tử.

## 11. Kiểm soát dữ liệu nguồn trước khi đánh giá

Dữ liệu nguồn quyết định những property mà biểu thức có thể đọc. Vì vậy, nên chuẩn bị một object có cấu trúc nhỏ, rõ ràng và phù hợp với mục đích của biểu thức.

Một số nguyên tắc:

1. Chỉ đưa vào các property cần thiết cho biểu thức.
2. Ưu tiên DTO hoặc read model thay vì truyền trực tiếp entity có nhiều quan hệ.
3. Dùng getter đơn giản, không có tác dụng phụ.
4. Trả về collection không sửa đổi hoặc bản sao khi phù hợp.
5. Xác định rõ property nào có thể null.
6. Kiểm tra và chuẩn hóa dữ liệu đầu vào trước khi đánh giá.
7. Không đưa thông tin nhạy cảm hoặc hành vi không cần thiết vào source object.
8. Dùng một SimpleEvaluationContext có cấu hình tối thiểu phù hợp với biểu thức.

Nếu biểu thức được người dùng cấu hình, hãy xem cả tên property và cấu trúc source object là một phần của giao diện cấu hình. Thay đổi DTO có thể làm biểu thức cũ không còn hoạt động, vì vậy nên quản lý schema và kiểm thử các biểu thức quan trọng.

## 12. Phân biệt SimpleEvaluationContext và StandardEvaluationContext

| Tiêu chí | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Mục tiêu | Đánh giá với tập tính năng được giới hạn | Cung cấp môi trường đánh giá đầy đủ hơn |
| Property access | Chọn accessor phù hợp qua builder | Có accessor mặc định và có thể mở rộng |
| Read-only binding | Có builder forReadOnlyDataBinding() | Cần cấu hình accessor và quyền ghi phù hợp |
| Method invocation | Không bật mặc định trong cấu hình tối giản | Có resolver method theo cấu hình mặc định |
| Bean reference và type access | Không cung cấp các khả năng đầy đủ này | Có thể cấu hình BeanResolver và TypeLocator |
| Trường hợp dùng | Data binding, biểu thức đọc dữ liệu có giới hạn | Biểu thức nội bộ cần resolver và khả năng nâng cao |

Chọn SimpleEvaluationContext khi biểu thức chỉ cần đọc dữ liệu và tập tính năng giới hạn đáp ứng được yêu cầu. Chọn StandardEvaluationContext khi cần cấu hình resolver, function, bean reference hoặc những khả năng nâng cao khác.

Không nên chọn context chỉ dựa trên tên. Hãy xác định chính xác property, method, function và nguồn dữ liệu mà biểu thức cần truy cập.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không đọc được property | Root object không có getter hoặc accessor không hỗ trợ property. | Kiểm tra source DTO, tên property và accessor. |
| Gán property trong read-only context | Accessor được cấu hình chỉ đọc. | Dùng luồng cập nhật riêng hoặc context cho phép ghi khi nghiệp vụ thực sự cần. |
| Nghĩ dữ liệu nguồn đã immutable | Read-only access không làm object lồng nhau bất biến. | Dùng DTO chỉ đọc, defensive copy và collection không sửa đổi. |
| Getter có tác dụng phụ | Việc đọc property có thể thực thi mã trong getter. | Giữ getter đơn giản và chỉ trả dữ liệu. |
| Truy cập property lồng nhau khi object null | Một cấp trong đường dẫn property không tồn tại. | Kiểm tra null hoặc dùng safe navigation. |
| Nhầm null với collection rỗng | Hai trạng thái biểu thị dữ liệu khác nhau. | Xác định hợp đồng dữ liệu và xử lý riêng. |
| Đưa toàn bộ entity vào source object | Biểu thức có thể nhìn thấy quá nhiều dữ liệu và quan hệ. | Tạo DTO hoặc read model tối thiểu. |
| Mong SimpleEvaluationContext hỗ trợ mọi SpEL feature | Context này cố ý giới hạn tính năng. | Kiểm tra builder và chọn context theo khả năng cần dùng. |
| Collection được trả về vẫn có thể bị sửa | Getter trả về tham chiếu tới collection mutable. | Trả về bản sao hoặc wrapper không sửa đổi; cân nhắc cả khả năng thay đổi phần tử. |
| Dùng read-only như cơ chế bảo mật duy nhất | Context không tự kiểm soát mọi nguồn truy cập ngoài object graph. | Giới hạn root object, property accessor và các tính năng được bật. |

## 14. Ví dụ hoàn chỉnh: đánh giá quy tắc trên dữ liệu nguồn chỉ đọc

Ví dụ dưới đây tạo một source object nhỏ và đánh giá nhiều biểu thức mà không thay đổi dữ liệu nguồn.

~~~java
public class AccountSource {
    private final String status;
    private final int age;
    private final BigDecimal balance;

    public AccountSource(
            String status,
            int age,
            BigDecimal balance) {
        this.status = status;
        this.age = age;
        this.balance = balance;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}

AccountSource source = new AccountSource(
        "ACTIVE",
        25,
        new BigDecimal("1500.00")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

ExpressionParser parser = new SpelExpressionParser();

Boolean activeAdult = parser.parseExpression(
        "status == 'ACTIVE' and age >= 18"
).getValue(context, source, Boolean.class);

BigDecimal balance = parser.parseExpression(
        "balance"
).getValue(context, source, BigDecimal.class);
~~~

Biểu thức đầu trả về Boolean cho biết tài khoản đang hoạt động và chủ tài khoản đủ tuổi theo điều kiện ví dụ. Biểu thức thứ hai đọc balance từ source object.

Các giá trị được đọc từ object được truyền vào. Không có thao tác gán property trong những biểu thức này.

## 15. Ghi nhớ

- Dữ liệu nguồn là object hoặc data model được truyền vào khi SpEL đánh giá biểu thức.
- Root object cung cấp property mà biểu thức truy cập trực tiếp.
- SimpleEvaluationContext.forReadOnlyDataBinding() tạo context dành cho việc đọc property theo data binding.
- Có thể truyền source object qua getValue(context, source, resultType).
- Read-only property access không cấp quyền ghi property thông qua accessor đó.
- Read-only không đồng nghĩa immutable: object lồng nhau và collection trả về vẫn có thể mutable.
- Ưu tiên source DTO nhỏ, getter đơn giản và collection không sửa đổi khi phù hợp.
- Dùng safe navigation và xử lý null theo hợp đồng dữ liệu.
- SimpleEvaluationContext giới hạn tính năng; không giả định nó hỗ trợ toàn bộ khả năng của StandardEvaluationContext.
- Chọn context tối thiểu đáp ứng yêu cầu và chỉ cung cấp dữ liệu mà biểu thức cần đọc.
