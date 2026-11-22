# Truy cập field và các property được expose trong SpEL

## 1. Property access trong SpEL là gì?

Spring Expression Language (SpEL) cho phép đọc và, trong trường hợp property có thể ghi, cập nhật dữ liệu của một object thông qua tên property trong biểu thức. Thay vì gọi getter hoặc setter trực tiếp trong Java, ta có thể viết một đường dẫn như:

~~~text
customer.name
order.total
product.sku
account.active
~~~

SpEL cần một object gốc (root object) hoặc một evaluation context để biết phải tìm property trên object nào. Parser phân tích tên property thành một biểu thức; khi gọi getValue, property accessor trong evaluation context sẽ tìm cách đọc giá trị. Khi gọi setValue, accessor cần hỗ trợ ghi vào property đích.

Ví dụ cơ bản:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan");

Expression expression = parser.parseExpression("name");
String name = expression.getValue(customer, String.class);

System.out.println(name); // Lan
~~~

Trong ví dụ này, customer là root object và name là property được truy cập. Không cần thêm tiền tố # vì name được tìm trên root object. Tiền tố # được dùng khi tham chiếu variable trong EvaluationContext, ví dụ #customerName.

## 2. JavaBean property: getter và setter

Một JavaBean thường expose property thông qua các phương thức getter và setter theo quy ước đặt tên:

- getName() cung cấp giá trị của property name.
- setName(String name) cập nhật property name.
- isActive() thường được dùng làm getter cho property Boolean active.
- setActive(boolean active) cập nhật property active.

Ví dụ:

~~~java
public class Customer {
    private String name;
    private boolean active;

    public Customer(String name) {
        this.name = name;
        this.active = true;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Có thể đọc các property mà không gọi getter trực tiếp:

~~~java
Customer customer = new Customer("Lan");

Expression nameExpression = parser.parseExpression("name");
Expression activeExpression = parser.parseExpression("active");

String name = nameExpression.getValue(customer, String.class);
Boolean active = activeExpression.getValue(customer, Boolean.class);
~~~

SpEL phân giải name thông qua property accessor. Với JavaBean thông thường, getter là giao diện đọc property và setter là giao diện ghi property. Điều này cho phép class giữ field ở chế độ private trong khi vẫn expose một API property rõ ràng.

Tên property trong biểu thức là tên logic của property, không phải tên phương thức. Viết name, không viết getName() để đọc JavaBean property. Nếu muốn gọi một method như một method, biểu thức dùng cú pháp gọi method với dấu ngoặc, ví dụ getName(); tuy nhiên, khi mục đích là truy cập property, nên dùng tên property.

## 3. Truy cập field trực tiếp

SpEL cũng có thể truy cập field khi property accessor đang dùng cho phép và field có thể được truy cập. Với ReflectivePropertyAccessor mặc định trong StandardEvaluationContext, việc phân giải property có thể dùng accessor method hoặc field tương ứng. Getter/setter theo quy ước JavaBean thường là giao diện nên ưu tiên khi class đã expose property như vậy; field là một đường truy cập khác khi phù hợp.

Ví dụ với public field:

~~~java
public class Product {
    public String sku;
    public int quantity;

    public Product(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}

Product product = new Product("SKU-100", 4);

Expression skuExpression = parser.parseExpression("sku");
Expression quantityExpression = parser.parseExpression("quantity");

String sku = skuExpression.getValue(product, String.class);
Integer quantity = quantityExpression.getValue(product, Integer.class);
~~~

Trong trường hợp field là private, khả năng truy cập phụ thuộc vào property accessor, quyền truy cập reflection và giới hạn của runtime/module. Không nên dựa vào việc SpEL đọc được một field private như một cam kết rằng field đó là API ổn định của class. Với code ứng dụng, JavaBean getter/setter hoặc một property accessor được thiết kế rõ ràng thường dễ bảo trì hơn.

Field và property không hoàn toàn đồng nghĩa:

- Field là thành viên dữ liệu được khai báo trong class.
- Property là tên truy cập dữ liệu được expose qua getter/setter hoặc property accessor.
- Một property có thể không có field cùng tên; getter có thể tính toán giá trị từ nhiều field.
- Một field có thể tồn tại nhưng không được expose qua accessor mà evaluation context đang cho phép.

## 4. Đọc property từ root object

Khi truyền một object trực tiếp vào getValue, object đó trở thành root object của lần đánh giá:

~~~java
public class Order {
    private String code;
    private double total;

    public Order(String code, double total) {
        this.code = code;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public double getTotal() {
        return total;
    }
}

Order order = new Order("ORD-1001", 1250.0);

Expression codeExpression = parser.parseExpression("code");
Expression totalExpression = parser.parseExpression("total");

String code = codeExpression.getValue(order, String.class);
Double total = totalExpression.getValue(order, Double.class);
~~~

Có thể đọc property lồng nhau bằng dấu chấm:

~~~text
customer.name
customer.address.city
order.customer.email
~~~

Ví dụ:

~~~java
Expression cityExpression =
        parser.parseExpression("customer.address.city");

String city = cityExpression.getValue(order, String.class);
~~~

Đường dẫn chỉ đánh giá được nếu mỗi property trung gian tồn tại và cung cấp object phù hợp. Nếu customer hoặc address là null, truy cập tiếp theo có thể phát sinh lỗi evaluation.

## 5. Dùng EvaluationContext để cung cấp root object

Thay vì truyền root object vào từng lần gọi getValue, có thể đặt root object trong StandardEvaluationContext:

~~~java
Customer customer = new Customer("Lan");

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);
~~~

Context còn cho phép đặt variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("prefix", "Customer");

Expression expression =
        parser.parseExpression("#prefix + ': ' + name");

String label = expression.getValue(context, String.class);
System.out.println(label); // Customer: Lan
~~~

Trong cùng một expression:

- name được phân giải từ root object.
- #prefix được phân giải từ variable tên prefix.
- #root đại diện cho root object hiện tại.
- #this đại diện cho object đang được xử lý ở vị trí hiện tại trong các cấu trúc expression như collection selection/projection.

Phân biệt property của root object với variable giúp tránh nhầm lẫn khi một tên có thể xuất hiện ở cả hai nơi.

## 6. Ghi property bằng setValue

Nếu property có thể ghi, Expression hỗ trợ cập nhật giá trị bằng setValue:

~~~java
Customer customer = new Customer("Lan");

Expression nameExpression = parser.parseExpression("name");
nameExpression.setValue(customer, "Minh");

System.out.println(customer.getName()); // Minh
~~~

Có thể dùng evaluation context thay cho root object trực tiếp:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Expression activeExpression = parser.parseExpression("active");
activeExpression.setValue(context, false);

System.out.println(customer.isActive()); // false
~~~

Khả năng ghi phụ thuộc vào property accessor và object đích. Một JavaBean property có setter phù hợp thường có thể được cập nhật. Property chỉ có getter, field final, object bất biến hoặc accessor chỉ đọc có thể không cho phép ghi. Khi không thể ghi, SpEL phát sinh lỗi evaluation thay vì tự tạo một setter hoặc thay đổi thiết kế của class.

Chỉ dùng setValue khi ứng dụng chủ đích thay đổi trạng thái object. Một expression đọc property có thể được dùng để tính toán; một expression ghi property là thao tác có side effect và cần được kiểm soát rõ.

## 7. Truy cập property của object lồng nhau

SpEL hỗ trợ đường dẫn property qua nhiều cấp object:

~~~java
public class Address {
    private String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private String name;
    private Address address;

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

Customer customer = new Customer("Lan", new Address("Da Nang"));

Expression expression =
        parser.parseExpression("address.city");

String city = expression.getValue(customer, String.class);
System.out.println(city); // Da Nang
~~~

Mỗi đoạn sau dấu chấm là một property access trên object được trả về từ đoạn trước. Điều này giúp biểu thức ngắn gọn, nhưng cũng có nghĩa dữ liệu phải có cấu trúc phù hợp. Nếu một property không tồn tại hoặc một object trung gian null, cần xử lý trường hợp đó.

## 8. Null-safe property access

SpEL cung cấp toán tử null-safe navigation ?. để tránh truy cập property trên target null:

~~~java
Expression expression =
        parser.parseExpression("address?.city");

String city = expression.getValue(customer, String.class);
~~~

Nếu address là null, address?.city trả về null thay vì cố đọc city trên một object không tồn tại.

Với đường dẫn nhiều cấp, hãy dùng null-safe operator ở từng chặng có thể null:

~~~text
customer?.address?.city
~~~

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("address?.city ?: 'Unknown city'");

String cityOrDefault = expression.getValue(customer, String.class);
~~~

Ở đây ?. xử lý trường hợp address là null; Elvis operator ?: cung cấp chuỗi mặc định nếu kết quả bên trái không có giá trị phù hợp. Null-safe operator không tự biến mọi property trong một đường dẫn thành an toàn; hãy xác định rõ object nào có thể null và đặt ?. ở vị trí tương ứng.

## 9. Truy cập Map, List và array

Map, List và array có cách truy cập phần tử riêng. Với Map, dùng key trong dấu ngoặc vuông; với List và array, dùng index:

~~~java
Expression mapExpression = parser.parseExpression("['city']");
Expression listExpression = parser.parseExpression("items[0]");
Expression arrayExpression = parser.parseExpression("codes[1]");
~~~

Nếu root object là một Map, có thể dùng:

~~~java
Map<String, Object> data = new HashMap<>();
data.put("city", "Da Nang");

Expression expression = parser.parseExpression("['city']");
String city = expression.getValue(data, String.class);
~~~

Với object có property items là List, items[0] truy cập phần tử đầu tiên của property đó. Cú pháp indexer không giống property access bằng dấu chấm. Dùng customer.name để đọc property name; dùng map['name'] để đọc giá trị theo key name trong Map.

## 10. PropertyAccessor và cách SpEL phân giải property

SpEL dùng interface PropertyAccessor để xác định cách đọc/ghi property trên object. Accessor có thể cho biết nó hỗ trợ loại target nào, property nào có thể đọc và property nào có thể ghi.

Các phương thức cốt lõi của một accessor gồm:

- getSpecificTargetClasses(): khai báo loại target mà accessor hỗ trợ; có thể trả về null nếu áp dụng rộng.
- canRead(...) và read(...): kiểm tra và thực hiện việc đọc.
- canWrite(...) và write(...): kiểm tra và thực hiện việc ghi.

StandardEvaluationContext mặc định sử dụng reflective property accessor để thao tác trên object Java. Có thể thêm accessor riêng khi cần expose dữ liệu theo quy ước khác, ví dụ object đến từ thư viện bên ngoài hoặc một cấu trúc dữ liệu đặc thù:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.addPropertyAccessor(customPropertyAccessor);
~~~

Khi có nhiều accessor, thứ tự và khả năng hỗ trợ target/property ảnh hưởng đến accessor được dùng. Accessor tùy chỉnh nên giới hạn rõ target type và các property được phép để tránh mở rộng quyền truy cập ngoài dự kiến.

## 11. SimpleEvaluationContext và giới hạn property access

StandardEvaluationContext cung cấp các khả năng SpEL đầy đủ hơn, bao gồm reflection và các resolver có thể được cấu hình. Nếu ứng dụng chỉ cần data binding hoặc truy cập property có giới hạn, có thể cân nhắc SimpleEvaluationContext.

Ví dụ tạo context cho data binding chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Hoặc context cho data binding đọc/ghi:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Context loại này được thiết kế để giới hạn một số khả năng của SpEL so với StandardEvaluationContext. Chọn builder phù hợp với quyền cần thiết: chỉ đọc khi biểu thức chỉ cần xem dữ liệu; đọc/ghi khi thực sự cần cập nhật property. Nếu cần custom property accessor, có thể cấu hình builder với accessor tương ứng.

Đừng coi việc dùng SimpleEvaluationContext là thay thế cho kiểm soát dữ liệu đầu vào. Hãy chỉ bật các khả năng cần thiết cho expression và tránh đánh giá chuỗi do người dùng không tin cậy gửi lên với context có quyền truy cập rộng.

## 12. Getter có thể thực thi code

Khi SpEL đọc một JavaBean property, accessor có thể gọi getter. Getter không nhất thiết chỉ trả về một field; nó có thể tính toán, truy vấn dữ liệu hoặc thực thi code khác.

~~~java
public class Account {
    public BigDecimal getAvailableBalance() {
        // Có thể tính toán từ nhiều field hoặc trạng thái khác.
        return calculateAvailableBalance();
    }
}
~~~

Biểu thức availableBalance có thể gọi getter tương ứng. Vì vậy, property access không phải lúc nào cũng là thao tác đọc bộ nhớ đơn giản. Tránh đặt side effect nặng hoặc hành vi bất ngờ trong getter được dùng bởi expression. Với các thao tác cần thay đổi trạng thái, hãy dùng method có tên mô tả rõ hành động và gọi ở tầng Java phù hợp.

## 13. Lỗi thường gặp

**Dùng tên method thay vì tên property**

Với JavaBean getter getName(), property thường được truy cập bằng name. Dùng getName() nếu thật sự muốn gọi method; không cần dùng tên method để đọc property.

**Property không được expose hoặc accessor không hỗ trợ**

Nếu không có getter, field phù hợp hoặc property accessor hỗ trợ target, SpEL không thể phân giải tên property. Kiểm tra object gốc, tên property và evaluation context được sử dụng.

**Truy cập qua null**

Một đoạn đường dẫn lồng nhau có thể thất bại khi object trung gian null. Dùng null-safe operator ở những chặng có thể null hoặc kiểm tra điều kiện trước.

**Cố ghi vào property chỉ đọc**

setValue cần property accessor có thể ghi. Getter-only property hoặc accessor chỉ đọc không thể tự động được cập nhật.

**Nhầm property với Map key hoặc collection index**

Dùng dấu chấm cho property path, dấu ngoặc vuông cho Map key, List/array index. Cú pháp phù hợp giúp parser phân giải đúng dữ liệu.

**Mở rộng quyền truy cập quá mức**

StandardEvaluationContext có thể hỗ trợ reflection, method resolution và type access tùy cấu hình. Với biểu thức không đáng tin cậy, hãy giới hạn evaluation context và accessor.

## 14. Ví dụ tổng hợp

Ví dụ sau đọc property của root object, property lồng nhau và dùng null-safe access cùng giá trị mặc định:

~~~java
public class Address {
    private String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private String name;
    private Address address;

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

ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", new Address("Da Nang"));

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);
context.setVariable("prefix", "Customer");

Expression expression = parser.parseExpression(
        "#prefix + ': ' + name + ' / ' + (address?.city ?: 'Unknown')");

String description = expression.getValue(context, String.class);
System.out.println(description);
// Customer: Lan / Da Nang
~~~

Nếu address là null, phần address?.city trả về null và Elvis operator cung cấp Unknown. Property name vẫn được đọc từ root object customer, còn #prefix đến từ variable trong context.

## 15. Ghi nhớ

- SpEL đọc property qua PropertyAccessor; StandardEvaluationContext mặc định có reflective property access.
- JavaBean property thường được expose qua getter và setter; tên trong expression là tên property như name, không phải getName().
- Field có thể được truy cập nếu accessor và runtime cho phép; không nên coi field nội bộ là API ổn định.
- Root object được truy cập trực tiếp; variables trong context dùng tiền tố #.
- Dấu chấm dùng cho property path; dấu ngoặc vuông dùng cho Map key và collection/array index.
- setValue chỉ hoạt động khi property accessor cho phép ghi.
- Dùng ?. cho object trung gian có thể null và ?: khi cần giá trị mặc định.
- Chọn SimpleEvaluationContext khi cần giới hạn quyền truy cập; không đánh giá expression không tin cậy với context đầy đủ quyền.
