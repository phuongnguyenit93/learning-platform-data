# Method không tồn tại hoặc không thể truy cập trong Spring Expression Language

Spring Expression Language (SpEL) cho phép gọi phương thức Java ngay trong biểu thức, ví dụ \`customer.calculateDiscount(10)\` hoặc \`name.toUpperCase()\`. Khi đánh giá lời gọi, SpEL phải tìm được phương thức phù hợp trên đối tượng đích, xác định cách truyền đối số và thực thi phương thức đó.

Nếu phương thức không tồn tại, không có overload nào phù hợp, hoặc phương thức không thể được truy cập trong môi trường hiện tại, quá trình đánh giá sẽ thất bại. Hiểu chuỗi xử lý này giúp phân biệt lỗi cú pháp với lỗi phân giải phương thức và lỗi xảy ra bên trong chính phương thức Java.

## 1. Cú pháp gọi phương thức trong SpEL

Một lời gọi phương thức có dạng:

~~~spel
methodName(argument1, argument2, ...)
~~~

Nếu phương thức thuộc một property lồng nhau, biểu thức dùng dấu chấm:

~~~spel
customer.calculateDiscount(10)
product.getName()
name.toUpperCase()
~~~

Nếu không có đối tượng đứng trước dấu chấm, phương thức được tìm trên đối tượng hiện tại, thường là root object của EvaluationContext.

Ví dụ lớp Java:

~~~java
public class Customer {
    public String greeting() {
        return "Hello";
    }

    public String formatName(String name) {
        return name.toUpperCase();
    }
}
~~~

Có thể gọi hai phương thức trên root object:

~~~java
Customer customer = new Customer();

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression("greeting()")
    .getValue(context, String.class);

String formatted = parser.parseExpression("formatName('Linh')")
    .getValue(context, String.class);
~~~

Kết quả lần lượt là \`Hello\` và \`LINH\`.

## 2. SpEL tìm phương thức như thế nào?

Khi đánh giá một method call, SpEL sử dụng các \`MethodResolver\` được đăng ký trong EvaluationContext. Resolver có nhiệm vụ tìm một phương thức phù hợp với tên phương thức và các đối số của biểu thức.

Trong \`StandardEvaluationContext\`, SpEL cung cấp \`ReflectiveMethodResolver\` mặc định. Resolver này tìm phương thức Java thông qua reflection và xem xét các yếu tố như tên, kiểu đối số, overload và các chuyển đổi kiểu được hỗ trợ.

Có thể mô tả luồng xử lý:

~~~text
Biểu thức: customer.calculateDiscount(10)
                   |
                   v
Đánh giá object customer
                   |
                   v
Đánh giá các đối số
                   |
                   v
MethodResolver tìm phương thức phù hợp
                   |
             +-----+-----+
             |           |
          Tìm thấy    Không tìm thấy
             |           |
             v           v
       MethodExecutor   Evaluation error
             |
             v
       Gọi phương thức
             |
        +----+----+
        |         |
     Thành công  Phương thức ném lỗi
        |         |
        v         v
    Giá trị trả  Invocation error
    về
~~~

Khi tìm được phương thức, resolver trả về một \`MethodExecutor\` để thực hiện lời gọi. Nếu không tìm được phương thức thích hợp, SpEL không thể tiếp tục đánh giá lời gọi đó.

## 3. Các nguyên nhân thường gặp khiến method không được tìm thấy

### 3.1. Sai tên phương thức

Tên phương thức trong SpEL phải khớp với tên phương thức Java mà resolver có thể tìm thấy. Java phân biệt chữ hoa và chữ thường.

Ví dụ lớp có:

~~~java
public String getName() {
    return name;
}
~~~

Biểu thức gọi:

~~~spel
getname()
~~~

không khớp với tên \`getName()\`. Nếu muốn đọc JavaBean property, thường nên dùng:

~~~spel
name
~~~

Nếu muốn gọi phương thức trực tiếp, phải viết đúng tên:

~~~spel
getName()
~~~

### 3.2. Phương thức không tồn tại trên object đích

Giả sử root object là Customer nhưng lớp này không có phương thức \`calculateTax()\`. Biểu thức:

~~~spel
calculateTax()
~~~

không thể được phân giải trên Customer nếu context không có resolver tùy chỉnh cung cấp cách xử lý khác.

Cần kiểm tra đúng kiểu runtime của object đích, đặc biệt khi root object được truyền qua interface, lớp cha hoặc một proxy.

### 3.3. Không có overload phù hợp với số lượng đối số

Giả sử lớp chỉ định nghĩa:

~~~java
public String format(String value) {
    return value.trim();
}
~~~

Nhưng biểu thức gọi:

~~~spel
format()
~~~

Lời gọi có số lượng đối số khác với chữ ký phương thức. Resolver không tìm được ứng viên phù hợp và evaluation thất bại.

Tương tự, nếu phương thức yêu cầu hai đối số nhưng biểu thức truyền một hoặc ba đối số, không có overload phù hợp thì lời gọi không thể thực hiện.

### 3.4. Kiểu đối số không tương thích

Ví dụ:

~~~java
public String repeat(String value, int count) {
    return value.repeat(count);
}
~~~

Biểu thức:

~~~spel
repeat('A', 'many')
~~~

truyền chuỗi \`many\` cho vị trí cần số nguyên. SpEL có thể sử dụng TypeConverter để chuyển đổi đối số khi chuyển đổi được hỗ trợ, nhưng chuỗi không biểu diễn được số nguyên sẽ không chuyển đổi thành công.

Khi kiểm tra lỗi, hãy đối chiếu kiểu runtime của từng đối số với kiểu tham số Java và xem context có converter phù hợp hay không.

### 3.5. Phương thức nằm trên một object khác

Biểu thức:

~~~spel
calculateDiscount(10)
~~~

gọi phương thức trên object hiện tại. Nếu phương thức thực sự thuộc một property khác, cần chỉ rõ đường dẫn:

~~~spel
customer.calculateDiscount(10)
~~~

Nếu root object không phải Customer và không có phương thức tương ứng, lời gọi không thể được giải quyết như mong đợi.

## 4. Phương thức tồn tại nhưng không thể truy cập

Tìm được tên và chữ ký phương thức chưa đủ. SpEL còn phải có khả năng truy cập phương thức đó trong môi trường Java đang chạy.

### 4.1. Phương thức không public

Ví dụ:

~~~java
class Customer {
    private String internalCode() {
        return "C-100";
    }
}
~~~

Biểu thức gọi:

~~~spel
internalCode()
~~~

không nên được kỳ vọng sẽ hoạt động với cấu hình truy cập reflection mặc định. Phương thức không public có thể không được resolver cho phép truy cập hoặc không thể gọi từ vị trí thực thi.

Đối với lời gọi từ SpEL, nên cung cấp phương thức public trên một kiểu có thể truy cập:

~~~java
public class Customer {
    public String getCode() {
        return "C-100";
    }
}
~~~

### 4.2. Lớp khai báo không thể truy cập

Một phương thức có thể được khai báo public nhưng lớp chứa nó lại không thể truy cập từ mã thực thi SpEL, chẳng hạn lớp package-private trong package khác hoặc kiểu bị giới hạn bởi cấu trúc module Java.

Trong trường hợp này, reflection có thể không gọi được phương thức dù tên và modifier của phương thức có vẻ phù hợp.

Hãy kiểm tra cả khả năng truy cập của lớp khai báo, không chỉ modifier của method.

### 4.3. Giới hạn reflection và Java module

Các giới hạn truy cập của JVM, module system hoặc môi trường triển khai có thể ngăn reflection truy cập thành viên. Một lời gọi hoạt động trong môi trường phát triển có thể gặp vấn đề khi chạy trong môi trường module hoặc runtime có cấu hình truy cập chặt hơn.

Khi gặp lỗi truy cập, cần xem exception gốc để xác định đó là vấn đề phân giải method, quyền truy cập reflection hay lỗi do phương thức thực thi.

## 5. Overload và lựa chọn phương thức

Java cho phép nhiều phương thức cùng tên nhưng khác danh sách tham số:

~~~java
public class Formatter {
    public String format(String value) {
        return value.trim();
    }

    public String format(Integer value) {
        return String.valueOf(value);
    }
}
~~~

Các biểu thức sau có thể chọn overload tương ứng:

~~~spel
format('  Spring  ')
format(42)
~~~

Resolver phải chọn phương thức tương thích với đối số mà SpEL đánh giá được. Kiểu đối số, khả năng chuyển đổi và quy tắc lựa chọn overload đều có thể ảnh hưởng đến kết quả.

Nếu có nhiều overload gần tương đương hoặc chuyển đổi kiểu gây mơ hồ, hãy làm rõ kiểu đầu vào, điều chỉnh chữ ký phương thức hoặc truyền giá trị có kiểu rõ ràng từ context.

Ví dụ, có thể đặt biến Java đúng kiểu trước khi đánh giá:

~~~java
context.setVariable("count", Integer.valueOf(3));

Expression expression =
    parser.parseExpression("formatter.format(#count)");
~~~

Cách này giúp kiểu của đối số được xác định rõ hơn.

## 6. EvaluationContext có thể giới hạn method invocation

MethodResolver là thành phần của EvaluationContext. Vì vậy, loại context và các resolver được đăng ký quyết định những phương thức nào có thể được gọi.

### StandardEvaluationContext

\`StandardEvaluationContext\` hỗ trợ khả năng phân giải phương thức reflection mặc định và có thể được cấu hình thêm. Đây là lựa chọn linh hoạt khi biểu thức cần gọi các phương thức Java phù hợp với ứng dụng.

### SimpleEvaluationContext

\`SimpleEvaluationContext\` được thiết kế cho các trường hợp cần giới hạn tính năng, thường gặp trong data binding. Builder cho phép chọn những khả năng được hỗ trợ và đăng ký resolver phù hợp.

Nếu dùng một context có giới hạn nhưng không đăng ký MethodResolver cần thiết, một method call có thể không được phân giải dù phương thức tồn tại trên lớp Java.

Vì vậy, khi method không được tìm thấy, cần kiểm tra danh sách resolver của context chứ không chỉ kiểm tra source code của object.

## 7. Phương thức trên property lồng nhau

Một lời gọi có thể đi qua nhiều property trước khi gọi phương thức:

~~~spel
order.customer.getName()
~~~

SpEL cần thực hiện lần lượt:

1. Đọc property \`customer\` trên root object order.
2. Nhận object Customer từ getter tương ứng.
3. Tìm phương thức \`getName()\` trên object Customer.
4. Gọi phương thức và nhận giá trị trả về.

Nếu customer là null, bước tìm và gọi phương thức không thể diễn ra trên một object hợp lệ. Nếu property customer không tồn tại, lỗi xảy ra ngay ở bước truy cập property.

Có thể dùng null-safe navigation để bảo vệ phần đường dẫn có khả năng null:

~~~spel
order.customer?.getName()
~~~

Khi đối tượng bên trái toán tử null-safe là null, phần gọi tương ứng trả về null. Null-safe navigation không tạo ra một phương thức còn thiếu và cũng không giải quyết vấn đề chữ ký hoặc quyền truy cập.

## 8. Gọi static method và phương thức trên bean

### Static method

Có thể tham chiếu kiểu Java bằng \`T(...)\` rồi gọi static method:

~~~spel
T(java.lang.Math).abs(-10)
~~~

Nếu không tìm thấy kiểu hoặc method static phù hợp, evaluation có thể thất bại. Cần kiểm tra tên đầy đủ của kiểu, method và kiểu đối số.

### Bean method

Trong context có BeanResolver phù hợp, biểu thức có thể gọi phương thức trên bean:

~~~spel
@environment.getProperty('app.name')
~~~

Nếu bean không được giải quyết, bean không có phương thức tương ứng hoặc context không hỗ trợ bean reference, lời gọi không thể hoàn tất.

Cú pháp bean reference không tự động hoạt động trong mọi EvaluationContext. Resolver phải được cấu hình và bean phải có thể được truy cập trong môi trường ứng dụng.

## 9. Phân biệt lỗi method resolution và lỗi bên trong method

Có hai nhóm lỗi quan trọng:

**Method resolution/access error:**

- Không có method với tên yêu cầu.
- Không có overload phù hợp với số lượng hoặc kiểu đối số.
- Method không thể truy cập.
- Context không cung cấp resolver cho loại lời gọi đó.

Trong nhóm này, SpEL chưa thực hiện thành công lời gọi phương thức.

**Method invocation error:**

- SpEL tìm được phương thức và gọi được phương thức.
- Nhưng chính phần thân phương thức ném exception khi chạy.

Ví dụ:

~~~java
public BigDecimal calculateDiscount(BigDecimal amount) {
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Amount must be non-negative");
    }
    return amount.multiply(new BigDecimal("0.10"));
}
~~~

Với đầu vào âm, method đã được tìm thấy và được gọi; lỗi phát sinh từ logic bên trong phương thức.

Hai nhóm lỗi cần cách xử lý khác nhau. Với lỗi resolution, kiểm tra tên, chữ ký, kiểu đối số, quyền truy cập và resolver. Với lỗi invocation, xem exception gốc và dữ liệu đầu vào của phương thức.

## 10. Cách điều tra khi SpEL báo method không tồn tại hoặc không thể truy cập

Có thể lần theo các bước sau:

1. **Xác định object đích:** root object hoặc property đứng trước dấu chấm có đúng kiểu runtime không?
2. **Kiểm tra tên method:** chữ hoa, chữ thường và tên phương thức có chính xác không?
3. **Kiểm tra số đối số:** số lượng đối số trong biểu thức có khớp với một overload không?
4. **Kiểm tra kiểu đối số:** giá trị thực tế có tương thích với kiểu tham số không? Có cần TypeConverter không?
5. **Kiểm tra khả năng truy cập:** method và lớp khai báo có thể được reflection truy cập không?
6. **Kiểm tra context:** MethodResolver nào đang được đăng ký? Context có chủ ý giới hạn method invocation không?
7. **Xem exception gốc:** lỗi xảy ra khi tìm method hay trong lúc thực thi method?

Không nên chỉ đổi tên phương thức hoặc thêm overload một cách phỏng đoán. Hãy dùng kiểu runtime, chữ ký và exception để xác định đúng nguyên nhân.

## 11. Ví dụ hoàn chỉnh: method tồn tại và được gọi thành công

~~~java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String formatGreeting(String prefix) {
        return prefix + name.toUpperCase();
    }
}
~~~

Đánh giá bằng SpEL:

~~~java
Customer customer = new Customer("Linh");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("prefix", "Hello, ");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("formatGreeting(#prefix)");

String result =
    expression.getValue(context, String.class);

System.out.println(result);
~~~

Kết quả:

~~~text
Hello, LINH
~~~

Trong ví dụ này:

- Root object là Customer.
- Biến prefix được lấy từ EvaluationContext.
- SpEL tìm method public \`formatGreeting(String)\`.
- MethodResolver xác định phương thức phù hợp.
- Phương thức được gọi và trả về String.
- getValue trả kết quả theo kiểu String được yêu cầu.

Nếu đổi biểu thức thành \`formatGreeting()\`, không còn overload phù hợp về số lượng đối số và evaluation thất bại. Nếu thay đổi thân phương thức để ném exception, lỗi sẽ thuộc giai đoạn invocation thay vì resolution.

## 12. Ghi nhớ

- Method call trong SpEL có dạng \`methodName(arguments)\` hoặc \`object.methodName(arguments)\`.
- SpEL sử dụng MethodResolver để tìm phương thức phù hợp trên object đích.
- StandardEvaluationContext cung cấp ReflectiveMethodResolver mặc định; context giới hạn có thể cần resolver được đăng ký rõ ràng.
- Sai tên, sai số lượng đối số, kiểu đối số không tương thích và overload mơ hồ đều có thể làm method resolution thất bại.
- Phương thức hoặc lớp khai báo không thể truy cập cũng có thể khiến lời gọi thất bại.
- Lỗi resolution khác với exception được ném ra từ bên trong phương thức đã được gọi.
- Property lồng nhau, root object, bean reference và static method đều có thể tham gia vào một lời gọi nếu context hỗ trợ.
- Khi debug, hãy kiểm tra object đích, tên method, chữ ký, kiểu đối số, resolver và exception gốc.

Khi một method call trong SpEL thất bại, hãy lần theo đường đi từ object đích đến resolver, xác định chữ ký mà biểu thức yêu cầu và kiểm tra quyền truy cập trước khi kết luận phương thức thực sự không tồn tại.
