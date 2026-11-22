# Tham số hóa và generic trong hệ kiểu

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường phải làm việc với nhiều loại dữ liệu: số, chuỗi, ngày giờ, tiền tệ, đối tượng miền, danh sách và kết quả của các phép tính. Nếu mỗi kiểu dữ liệu đều cần một cấu trúc hoặc hàm riêng, hệ thống sẽ có nhiều mã lặp và khó mở rộng. Ngược lại, nếu dùng một kiểu quá tổng quát cho mọi giá trị, hệ thống mất khả năng kiểm tra kiểu và có thể phát hiện lỗi quá muộn.

**Tham số hóa kiểu** (*type parameterization*) cho phép một kiểu hoặc thành phần được định nghĩa với một hay nhiều tham số kiểu. Khi sử dụng, người viết cung cấp kiểu cụ thể cho các tham số đó. **Generic** là cơ chế phổ biến để khai báo và sử dụng những kiểu hoặc hàm có tham số kiểu.

Ví dụ, thay vì tạo riêng các kiểu danh sách cho số nguyên, chuỗi và khách hàng, ta có thể định nghĩa một kiểu danh sách tổng quát:

~~~java
List<Integer> numbers;
List<String> names;
List<Customer> customers;
~~~

Trong cả ba trường hợp, cấu trúc List được tái sử dụng; tham số trong dấu ngoặc nhọn xác định kiểu phần tử. Cơ chế này giúp tăng khả năng tái sử dụng, giữ thông tin kiểu và hỗ trợ phát hiện lỗi trước khi chương trình chạy.

Trong DSL, tham số hóa có thể xuất hiện ở kiểu dữ liệu, biểu thức, hàm, bộ chuyển đổi, node AST, schema hoặc thành phần thực thi. Thiết kế generic cần cân bằng giữa khả năng tái sử dụng và độ phức tạp của hệ kiểu. Một DSL không nhất thiết phải hỗ trợ mọi tính năng generic của ngôn ngữ lập trình đa dụng; nó chỉ nên cung cấp mức tham số hóa phù hợp với miền và người dùng.

## 1. Kiểu tham số hóa và generic là gì?

### 1.1. Kiểu thông thường

Một kiểu thông thường mô tả một tập giá trị và những phép toán hợp lệ trên các giá trị đó. Ví dụ:

~~~text
Integer
String
Boolean
Customer
Order
~~~

Nếu có kiểu Order, hệ thống có thể định nghĩa các thuộc tính như mã đơn hàng, tổng tiền và trạng thái. Kiểu Customer mô tả khách hàng và các thuộc tính liên quan.

Một kiểu thông thường thường cố định cấu trúc và kiểu dữ liệu của các thành phần bên trong. Khi cần cùng một cấu trúc cho nhiều kiểu phần tử, nếu không có generic, nhóm phát triển có thể phải tạo nhiều kiểu gần giống nhau.

### 1.2. Tham số kiểu

Tham số kiểu (*type parameter*) là một tên đại diện cho một kiểu chưa được xác định tại thời điểm khai báo. Ví dụ:

~~~text
List<T>
~~~

T là tham số kiểu. Khi sử dụng List<Integer>, T được thay bằng Integer; khi sử dụng List<Customer>, T được thay bằng Customer.

Có thể hình dung:

~~~text
Generic declaration: List<T>
                         |
             +-----------+-----------+
             |                       |
             v                       v
      List<Integer>           List<Customer>
          T = Integer              T = Customer
~~~

Tham số kiểu thường được đặt tên bằng chữ in hoa hoặc tên có ý nghĩa như T, E, K, V, R. Đây chỉ là quy ước đặt tên; ngữ nghĩa được xác định bởi vị trí tham số và các ràng buộc của nó.

### 1.3. Khai báo generic và kiểu đã tham số hóa

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Khai báo generic | Định nghĩa một cấu trúc có tham số kiểu | List<T> |
| Tham số kiểu | Biến kiểu được dùng trong khai báo | T |
| Kiểu đối số (*type argument*) | Kiểu cụ thể được truyền vào tham số | Integer |
| Kiểu đã tham số hóa | Kiểu generic sau khi cung cấp đối số kiểu | List<Integer> |
| Kiểu thô (*raw type*) | Cách dùng generic mà bỏ qua tham số kiểu trong Java | List |

Khai báo generic là khuôn mẫu. Kiểu đã tham số hóa là một cách sử dụng khuôn mẫu với kiểu cụ thể.

### 1.4. Generic không phải kiểu dữ liệu động

Generic không có nghĩa là biến có thể nhận tùy ý mọi kiểu. Ví dụ, List<Integer> mô tả danh sách các phần tử Integer. Hệ thống kiểu có thể ngăn việc thêm String vào danh sách đó.

~~~java
List<Integer> scores = new ArrayList<>();
scores.add(95);
scores.add(88);
// scores.add("excellent"); // lỗi kiểu khi biên dịch
~~~

Đây là điểm khác biệt với một danh sách chứa Object mà không có ràng buộc cụ thể. Generic giúp giữ lại thông tin kiểu của phần tử và kiểm tra cách sử dụng.

## 2. Vì sao cần tham số hóa?

### 2.1. Tái sử dụng cấu trúc

Một cấu trúc dữ liệu như danh sách, tập hợp, cặp khóa-giá trị hoặc kết quả có thể được dùng với nhiều kiểu dữ liệu.

Không có generic, nhóm phát triển có thể phải tạo:

~~~text
IntegerList
StringList
CustomerList
OrderList
~~~

Những kiểu này thường lặp lại cùng logic thêm, xóa, tìm kiếm và duyệt phần tử. Generic cho phép dùng một định nghĩa:

~~~text
List<T>
~~~

và thay đổi kiểu phần tử theo nhu cầu.

### 2.2. Giữ thông tin kiểu

Một API tổng quát có thể trả về Object, buộc người gọi phải ép kiểu:

~~~java
Object value = values.get(0);
Customer customer = (Customer) value;
~~~

Nếu dùng generic:

~~~java
Customer customer = customers.get(0);
~~~

Kiểu phần tử được giữ trong chữ ký của API. Trình biên dịch có thể kiểm tra phép gán và lời gọi phương thức, giúp giảm ép kiểu thủ công và lỗi ClassCastException.

### 2.3. Biểu diễn quan hệ giữa các kiểu

Generic không chỉ mô tả một kiểu phần tử. Nó còn có thể thể hiện quan hệ giữa đầu vào và đầu ra.

Ví dụ, một hàm chuyển đổi có thể nhận T và trả về R:

~~~java
R map(T value, Function<T, R> converter)
~~~

Chữ ký cho biết kiểu kết quả phụ thuộc vào kiểu đầu ra của converter. Nhờ vậy, hệ kiểu có thể giữ quan hệ này qua nhiều lời gọi mà không cần ép kiểu.

### 2.4. Tái sử dụng thuật toán

Một thuật toán tìm kiếm, sắp xếp, ánh xạ hoặc kiểm tra có thể hoạt động với nhiều kiểu, miễn là kiểu đó đáp ứng những thao tác mà thuật toán cần.

Ví dụ, thuật toán tìm giá trị lớn nhất cần biết cách so sánh hai phần tử. Tham số kiểu có thể bị ràng buộc bởi một interface so sánh, thay vì yêu cầu mọi đối tượng đều có cùng kiểu cụ thể.

### 2.5. Kiểm tra lỗi sớm

Generic giúp đưa một số lỗi từ thời điểm chạy về thời điểm phân tích hoặc biên dịch. Nếu một hàm yêu cầu List<Customer>, việc truyền List<Order> có thể bị từ chối trước khi chương trình thực thi.

Điều này đặc biệt hữu ích trong DSL có các biểu thức lồng nhau hoặc nhiều bước chuyển đổi dữ liệu. Hệ kiểu có thể phát hiện sự không tương thích ngay tại nơi gọi.

## 3. Khai báo generic type

### 3.1. Generic class

Trong Java, một lớp có thể khai báo tham số kiểu:

~~~java
public class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
~~~

Box<T> có thể chứa một giá trị thuộc kiểu T. Khi tạo đối tượng:

~~~java
Box<String> title = new Box<>("DSL");
Box<Integer> count = new Box<>(3);
~~~

Trong Box<String>, T là String. Trong Box<Integer>, T là Integer.

### 3.2. Generic interface

Interface cũng có thể tham số hóa:

~~~java
public interface Repository<T, ID> {
    T findById(ID id);
    void save(T entity);
    void deleteById(ID id);
}
~~~

Repository<T, ID> mô tả một kho lưu trữ cho kiểu thực thể T và kiểu định danh ID.

Một triển khai cụ thể:

~~~java
public final class CustomerRepository
        implements Repository<Customer, Long> {

    @Override
    public Customer findById(Long id) {
        // Tìm khách hàng theo định danh
        return null;
    }

    @Override
    public void save(Customer entity) {
        // Lưu khách hàng
    }

    @Override
    public void deleteById(Long id) {
        // Xóa theo định danh
    }
}
~~~

Interface cho phép tái sử dụng hợp đồng mà không buộc mọi miền phải dùng cùng kiểu thực thể hoặc cùng kiểu ID.

### 3.3. Nhiều tham số kiểu

Một generic có thể có nhiều tham số:

~~~java
public record Pair<K, V>(K key, V value) {}
~~~

Pair<String, Integer> có khóa kiểu String và giá trị kiểu Integer.

Một kiểu kết quả có thể dùng hai tham số:

~~~text
Result<T, E>
~~~

Trong đó T là kiểu dữ liệu khi thành công, E là kiểu lỗi. Một cách mô hình hóa có thể có hai nhánh Success<T> và Failure<E>.

### 3.4. Tham số kiểu có thể xuất hiện ở trường và phương thức

Trong một lớp generic, tham số kiểu có thể được dùng cho:

- Trường dữ liệu.
- Tham số và kiểu trả về của phương thức.
- Kiểu phần tử trong danh sách.
- Đối tượng được tạo hoặc truyền cho thành phần khác.
- Kiểu của một interface được triển khai.

Mọi vị trí sử dụng T phải tuân theo ràng buộc mà khai báo generic đặt ra.

### 3.5. Quy ước đặt tên tham số kiểu

Một số quy ước thường gặp:

| Tên | Ý nghĩa thường dùng |
|---|---|
| T | Type, một kiểu tổng quát |
| E | Element, phần tử của collection |
| K | Key, khóa |
| V | Value, giá trị |
| R | Result hoặc Return, kiểu kết quả |
| ID | Kiểu định danh |

Với generic phức tạp, tên có ý nghĩa có thể dễ đọc hơn một chuỗi ký tự đơn. Điều quan trọng là tên không che khuất vai trò của tham số và được dùng nhất quán.

## 4. Generic method và generic function

### 4.1. Phương thức có tham số kiểu riêng

Một phương thức có thể khai báo tham số kiểu độc lập với tham số kiểu của lớp:

~~~java
public static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("List is empty");
    }
    return values.get(0);
}
~~~

Ký hiệu <T> đứng trước kiểu trả về cho biết phương thức khai báo tham số kiểu T. Khi gọi:

~~~java
String name = first(List.of("Lan", "Minh"));
Integer score = first(List.of(90, 85));
~~~

Trình biên dịch suy luận T từ đối số và ngữ cảnh sử dụng.

### 4.2. Generic function trong DSL

Một DSL có thể cho phép khai báo hàm tổng quát:

~~~text
function first<T>(items: List<T>): T {
    return items[0]
}
~~~

Hàm nhận một danh sách phần tử kiểu T và trả về một phần tử cùng kiểu T. Khi gọi:

~~~text
first<Integer>(scores)
first<Customer>(customers)
~~~

Đối số kiểu có thể được ghi tường minh. Một DSL cũng có thể hỗ trợ suy luận kiểu để người dùng chỉ cần viết:

~~~text
first(scores)
~~~

Khi đó, type checker xác định T dựa trên kiểu của scores.

### 4.3. Hàm biến đổi giữa hai kiểu

Một hàm chuyển đổi thường có hai tham số kiểu:

~~~java
public static <T, R> List<R> map(
        List<T> source,
        Function<T, R> converter) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(converter.apply(item));
    }
    return result;
}
~~~

Ví dụ:

~~~java
List<String> names = List.of("Lan", "Minh");
List<Integer> lengths = map(names, String::length);
~~~

Ở đây T là String và R là Integer. Chữ ký thể hiện quan hệ giữa danh sách nguồn, hàm chuyển đổi và danh sách kết quả.

### 4.4. Generic method trong lớp không generic

Một lớp không cần tham số kiểu vẫn có thể chứa generic method:

~~~java
public class TypeUtilities {
    public static <T> T identity(T value) {
        return value;
    }
}
~~~

Tham số kiểu thuộc về phương thức, không thuộc về lớp. Mỗi lời gọi có thể suy luận T khác nhau.

## 5. Ràng buộc tham số kiểu

### 5.1. Vì sao cần ràng buộc?

Một hàm generic có thể cần thực hiện thao tác trên T. Nhưng nếu T là bất kỳ kiểu nào, hệ thống không thể biết T có hỗ trợ thao tác đó hay không.

Ví dụ, thuật toán tìm phần tử lớn nhất cần so sánh hai phần tử. Không phải mọi kiểu đều có phép so sánh thứ tự tự nhiên.

Ràng buộc tham số kiểu (*type bound* hoặc *constraint*) mô tả những điều kiện mà đối số kiểu phải đáp ứng.

### 5.2. Upper bound

Trong Java, upper bound giới hạn kiểu đối số phải là một kiểu con của lớp hoặc interface được chỉ định:

~~~java
public static <T extends Number> double sumAsDouble(
        List<T> values) {
    double total = 0;
    for (T value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

T extends Number cho phép gọi doubleValue() vì mọi kiểu T được chấp nhận đều kế thừa Number.

Trong Java, từ khóa extends được dùng cả với lớp và interface khi khai báo bound.

### 5.3. Nhiều bound

Một tham số kiểu có thể bị ràng buộc bởi nhiều kiểu:

~~~java
public static <T extends Number & Comparable<T>> T max(
        T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

T phải vừa là Number vừa triển khai Comparable<T>. Trong cú pháp Java, nếu có lớp cha thì lớp phải đứng đầu, sau đó mới đến các interface.

### 5.4. Bound theo quan hệ giữa các tham số

Ràng buộc có thể mô tả quan hệ giữa nhiều tham số kiểu:

~~~java
public static <T, R> R convert(
        T source,
        Function<? super T, ? extends R> converter) {
    return converter.apply(source);
}
~~~

Ở đây kiểu của converter liên quan đến T và R. Type checker phải bảo đảm giá trị truyền vào có thể được hàm nhận và kết quả có thể được gán cho kiểu R.

### 5.5. Constraint trong type system của DSL

Một DSL có thể dùng cú pháp ràng buộc riêng:

~~~text
function maximum<T where T supports Comparable<T>>(
    values: List<T>
): T
~~~

Ý nghĩa là T phải hỗ trợ phép so sánh với một giá trị cùng kiểu T. Cú pháp minh họa không phải chuẩn chung; DSL cần định nghĩa rõ khái niệm supports, cách kiểm tra và thông báo lỗi khi kiểu không đáp ứng.

Ràng buộc có thể dựa trên:

- Kế thừa hoặc triển khai interface.
- Có một tập phương thức hoặc thuộc tính.
- Hỗ trợ một phép toán cụ thể.
- Có thể chuyển đổi sang kiểu khác.
- Thỏa một điều kiện kiểu giữa các tham số.

Không nên biến mọi yêu cầu nghiệp vụ thành bound kiểu. Một điều kiện như “khách hàng đã xác minh” thường là điều kiện giá trị hoặc quyền ở runtime, không phải thuộc tính của kiểu Customer nói chung.

## 6. Wildcard và kiểu biến thiên trong Java

### 6.1. Wildcard là gì?

Wildcard (?) biểu diễn một kiểu chưa biết trong một vị trí sử dụng generic. Nó thường được dùng để viết API linh hoạt hơn mà không cần đặt tên tham số kiểu.

Ví dụ:

~~~java
List<?> values;
~~~

List<?> là danh sách của một kiểu phần tử chưa biết. Có thể đọc phần tử dưới dạng Object, nhưng không thể thêm một giá trị tùy ý ngoài null vì compiler không biết kiểu thực tế của danh sách.

### 6.2. Upper-bounded wildcard

~~~java
List<? extends Number> numbers;
~~~

Kiểu phần tử của danh sách là một kiểu con nào đó của Number. Có thể đọc phần tử như Number:

~~~java
Number value = numbers.get(0);
~~~

Nhưng không thể thêm một Integer tùy ý, vì danh sách thực tế có thể là List<Double>.

### 6.3. Lower-bounded wildcard

~~~java
List<? super Integer> destinations;
~~~

Kiểu phần tử là Integer hoặc một kiểu cha của Integer, chẳng hạn Number hoặc Object. Có thể thêm Integer:

~~~java
destinations.add(10);
~~~

Khi đọc, kiểu an toàn chung chỉ là Object vì danh sách có thể được khai báo với kiểu phần tử là Object.

### 6.4. Quy tắc PECS

Một quy tắc ghi nhớ thường dùng là PECS:

- **Producer Extends:** nếu cấu trúc chủ yếu cung cấp giá trị để đọc, dùng extends.
- **Consumer Super:** nếu cấu trúc chủ yếu nhận giá trị để ghi, dùng super.

Ví dụ:

~~~java
public static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}

public static void addDefaults(
        List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
~~~

PECS là hướng dẫn thiết kế API, không phải quy tắc thay thế cho việc hiểu kiểu thực tế. Với API vừa đọc vừa ghi, cần cân nhắc dùng tham số kiểu có tên hoặc tách thành các phương thức riêng.

### 6.5. Invariance của generic trong Java

Trong Java, dù Integer là kiểu con của Number, List<Integer> không phải kiểu con của List<Number>.

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // không hợp lệ
~~~

Nếu phép gán đó được cho phép, người nhận có thể thêm Double vào danh sách ban đầu chỉ chứa Integer. Vì vậy, generic class trong Java là invariant theo tham số kiểu, trừ khi wildcard được dùng để mô tả quan hệ đọc/ghi phù hợp.

### 6.6. Variance nói chung

Trong hệ kiểu, variance mô tả cách quan hệ subtype giữa các kiểu đối số ảnh hưởng đến quan hệ subtype giữa các kiểu generic.

| Loại | Ý nghĩa | Mô tả khái quát |
|---|---|---|
| Covariance | Giữ cùng chiều quan hệ subtype | Nếu A là subtype của B, Container<A> có thể là subtype của Container<B> |
| Contravariance | Đảo chiều quan hệ subtype | Nếu A là subtype của B, Consumer<B> có thể là subtype của Consumer<A> |
| Invariance | Không suy ra quan hệ subtype | Container<A> và Container<B> không thay thế trực tiếp cho nhau |

Java thể hiện variance chủ yếu qua wildcard ở vị trí sử dụng. Một số ngôn ngữ khác cho phép khai báo variance ngay trên tham số kiểu của lớp hoặc interface.

## 7. Generic và hệ kiểu của DSL

### 7.1. Tham số hóa kiểu miền

Một DSL có thể định nghĩa kiểu collection tổng quát:

~~~text
List<T>
Set<T>
Map<K, V>
Optional<T>
~~~

Những kiểu này có thể dùng với kiểu miền:

~~~text
List<Order>
Map<CustomerId, Customer>
Optional<Payment>
~~~

Type checker cần biết số lượng tham số kiểu, vị trí của chúng và những ràng buộc áp dụng.

### 7.2. Generic expression

Một node biểu thức có thể giữ kiểu kết quả:

~~~text
Expression<T>
~~~

Literal số nguyên có kiểu Expression<Integer>; tham chiếu đến khách hàng có kiểu Expression<Customer>. Một node so sánh có thể nhận hai biểu thức tương thích và trả về Expression<Boolean>.

Ví dụ:

~~~text
greaterThan<T>(
    left: Expression<T>,
    right: Expression<T>
): Expression<Boolean>
~~~

Hàm này yêu cầu hai vế có cùng kiểu T. Nếu DSL cho phép so sánh khác kiểu, cần một quy tắc chuyển đổi hoặc quan hệ kiểu rõ ràng.

### 7.3. Generic function trong rule engine

Một rule engine có thể định nghĩa hàm chuyển đổi tổng quát:

~~~text
map<T, R>(
    values: List<T>,
    transform: Function<T, R>
): List<R>
~~~

Khi áp dụng:

~~~text
map<Order, Money>(orders, order -> order.total)
~~~

Kết quả là List<Money>. Nếu type inference đủ khả năng, người dùng có thể bỏ các đối số kiểu tường minh.

### 7.4. Generic cho kết quả và lỗi

Một DSL gọi dịch vụ có thể cần biểu diễn thành công hoặc thất bại:

~~~text
Result<T, E>
~~~

Ví dụ:

~~~text
Result<Customer, LookupError>
Result<Payment, PaymentError>
~~~

Kiểu này giữ được kiểu dữ liệu thành công và kiểu lỗi. Nó cũng giúp người viết biết phải xử lý cả hai nhánh thay vì dùng một giá trị null không rõ nguyên nhân.

### 7.5. Generic cho schema và AST node

Trong implementation của DSL, generic có thể giúp giữ kiểu dữ liệu của node:

~~~java
public interface Expression<T> {
    T evaluate(EvaluationContext context);
}
~~~

Một literal:

~~~java
public final class LiteralExpression<T> implements Expression<T> {
    private final T value;

    public LiteralExpression(T value) {
        this.value = value;
    }

    @Override
    public T evaluate(EvaluationContext context) {
        return value;
    }
}
~~~

Expression<Integer> có thể được dùng ở nơi cần biểu thức số nguyên; Expression<Boolean> có thể được dùng làm điều kiện. Thiết kế này đưa một phần bảo đảm kiểu vào cấu trúc AST và giảm ép kiểu trong interpreter.

Tuy nhiên, khi AST được tạo động từ văn bản, parser vẫn cần semantic analyzer để xác định kiểu. Generic trong Java source code không tự động chứng minh rằng nội dung DSL của người dùng hợp lệ.

## 8. Suy luận kiểu (type inference)

### 8.1. Khái niệm

Suy luận kiểu là quá trình hệ thống tự xác định đối số kiểu dựa trên ngữ cảnh, đối số hàm, kiểu biểu thức hoặc ràng buộc.

Ví dụ Java:

~~~java
List<String> names = List.of("Lan", "Minh");
~~~

Trình biên dịch có thể suy luận kiểu phần tử là String từ ngữ cảnh đích.

Một lời gọi generic method:

~~~java
String firstName = first(names);
~~~

Compiler có thể suy ra T là String.

### 8.2. Suy luận từ đối số

Với hàm:

~~~text
function identity<T>(value: T): T
~~~

Khi gọi:

~~~text
identity("hello")
~~~

Type checker suy luận T là String từ kiểu của đối số.

### 8.3. Suy luận từ nhiều đối số

Với hàm:

~~~text
function choose<T>(left: T, right: T): T
~~~

Nếu một đối số là Integer và một đối số là Decimal, hệ kiểu phải xác định có kiểu chung nào phù hợp hay không. Tùy quy tắc, nó có thể suy ra Number, Decimal hoặc từ chối vì không có phép chuyển đổi ngầm được cho phép.

Suy luận kiểu không nên tự động chuyển đổi dữ liệu theo cách làm mất độ chính xác hoặc thay đổi ý nghĩa miền.

### 8.4. Suy luận từ kiểu trả về và ngữ cảnh

Một số hệ kiểu dùng cả kiểu đích để suy luận tham số generic. Ví dụ:

~~~text
let result: List<Customer> = emptyList()
~~~

Ngữ cảnh cho biết kiểu phần tử cần là Customer dù lời gọi không có đối số cung cấp thông tin đó.

Nếu có nhiều nghiệm thỏa mãn, hệ kiểu cần quy tắc chọn rõ hoặc yêu cầu người dùng ghi kiểu tường minh.

### 8.5. Khi nào cần ghi kiểu tường minh?

Ghi kiểu tường minh hữu ích khi:

- Suy luận không đủ thông tin.
- Có nhiều kiểu chung có thể chọn.
- Muốn làm rõ ý định cho người đọc.
- Cần chọn một overload hoặc nhánh generic cụ thể.
- Một phép chuyển đổi có thể gây mất dữ liệu.

DSL nên hỗ trợ cả suy luận và cách ghi kiểu rõ ràng ở những vị trí quan trọng.

## 9. Giới hạn và khó khăn của generic

### 9.1. Độ phức tạp của chữ ký

Một chữ ký có nhiều tham số và bound có thể khó đọc:

~~~java
<T extends Comparable<? super T>, R extends Serializable>
Map<R, List<T>> transform(...)
~~~

Generic giúp diễn đạt quan hệ kiểu chính xác nhưng cũng có thể làm API khó hiểu. Nên dùng tên tham số có ý nghĩa, tách phương thức phức tạp và tránh thêm bound không cần thiết.

### 9.2. Suy luận kiểu có thể mơ hồ

Khi có nhiều overload, nhiều bound hoặc kiểu chung phức tạp, compiler có thể không suy luận được. Người dùng phải ghi kiểu tường minh hoặc thay đổi cách biểu diễn.

DSL cần thông báo lỗi nêu rõ tham số kiểu nào chưa xác định và các ràng buộc nào mâu thuẫn.

### 9.3. Tương thích với kiểu động

Một số DSL cho phép biến có kiểu xác định ở runtime hoặc dữ liệu không có schema cố định. Khi đó, generic tĩnh có thể khó áp dụng hoàn toàn.

Có thể dùng kiểu động ở ranh giới nhập dữ liệu, sau đó xác thực và chuyển sang kiểu đã biết trước khi thực hiện phép toán miền.

### 9.4. Chi phí cho compiler và type checker

Generic làm tăng công việc của bộ phân tích kiểu: thay thế tham số, giải ràng buộc, suy luận, kiểm tra subtype và phát hiện đệ quy kiểu.

Với DSL nhỏ, hệ thống có thể chỉ cần generic đơn giản và số lượng bound hạn chế. Những tính năng nâng cao nên được thêm khi có nhu cầu thực tế và công cụ chẩn đoán phù hợp.

### 9.5. Erasure trong Java

Java sử dụng type erasure cho generic. Thông tin tham số kiểu chủ yếu được kiểm tra ở thời điểm biên dịch và bị xóa hoặc thay thế bằng bound trong bytecode.

Ví dụ, List<String> và List<Integer> đều dùng cùng lớp runtime List. Vì vậy:

~~~java
List<String> names = new ArrayList<>();
List<Integer> scores = new ArrayList<>();
~~~

Ở runtime, không thể dùng phép kiểm tra thông thường như:

~~~java
// if (value instanceof List<String>) { ... }
~~~

vì tham số kiểu không được giữ đầy đủ để kiểm tra theo cách đó.

Erasure giúp duy trì khả năng tương thích với mã Java cũ nhưng đặt ra một số giới hạn:

- Không thể tạo trực tiếp một đối tượng T bằng new T().
- Không thể tạo mảng có thành phần T một cách tổng quát.
- Không thể overload chỉ dựa trên List<String> và List<Integer> vì chữ ký sau erasure trùng nhau.
- Không thể kiểm tra instanceof với kiểu tham số hóa cụ thể như List<String>.

### 9.6. Raw type và unchecked operation

Java vẫn cho phép dùng raw type để tương thích với mã cũ:

~~~java
List values = new ArrayList();
values.add("hello");
values.add(42);
~~~

Raw type bỏ qua thông tin kiểu. Khi lấy phần tử, người gọi có thể phải ép kiểu và có nguy cơ lỗi runtime. Compiler thường phát cảnh báo unchecked để chỉ ra rằng bảo đảm kiểu đã bị suy yếu.

Trong mã mới, nên dùng generic type đầy đủ và xử lý cảnh báo unchecked tại ranh giới có kiểm soát.

### 9.7. Generic và primitive type trong Java

Java generic dùng kiểu tham chiếu, vì vậy không thể viết trực tiếp List<int>. Cần dùng wrapper như Integer, Long hoặc Double.

~~~java
List<Integer> scores = new ArrayList<>();
~~~

Việc boxing và unboxing có thể tạo thêm chi phí hoặc gây NullPointerException khi unbox một giá trị null. Với dữ liệu số lượng lớn, có thể cân nhắc cấu trúc chuyên biệt cho primitive nếu hiệu năng yêu cầu.

## 10. Reified generic và erased generic

### 10.1. Erased generic

Với erased generic, thông tin kiểu tham số không còn đầy đủ ở runtime. Java là ví dụ phổ biến.

Ưu điểm:

- Tương thích với mô hình runtime cũ.
- Không cần tạo một lớp runtime riêng cho mọi đối số kiểu.
- Giảm một phần chi phí triển khai generic ở runtime.

Giới hạn là runtime không thể kiểm tra trực tiếp mọi tham số kiểu và một số thao tác cần type token hoặc metadata bổ sung.

### 10.2. Reified generic

Với reified generic, thông tin kiểu tham số được giữ ở runtime ở mức độ mà ngôn ngữ quy định. Điều này có thể hỗ trợ kiểm tra kiểu hoặc thao tác runtime theo đối số kiểu.

Một số ngôn ngữ và cơ chế cụ thể hỗ trợ reification theo những cách khác nhau. Không nên giả định mọi generic language đều giữ toàn bộ thông tin kiểu ở runtime.

### 10.3. Type token và metadata

Trong Java, khi cần giữ thông tin kiểu tham số ở runtime, có thể dùng một đối tượng đại diện kiểu như Type hoặc một lớp token chuyên dụng. Một số thư viện dùng anonymous subclass để nắm generic type trong metadata.

Ví dụ khái niệm:

~~~java
TypeToken<List<String>> token = new TypeToken<>() {};
~~~

Đây là kỹ thuật của thư viện, không phải tính năng làm thay đổi type erasure của Java. Nó chỉ cung cấp metadata kiểu mà thư viện có thể đọc.

## 11. Generic, subtype và nguyên tắc thay thế

### 11.1. Quan hệ subtype

Nếu Dog là subtype của Animal, một đối tượng Dog có thể được dùng ở nơi cần Animal:

~~~java
Animal pet = new Dog();
~~~

Nhưng với generic invariant trong Java:

~~~java
List<Dog> dogs = new ArrayList<>();
// List<Animal> animals = dogs; // không hợp lệ
~~~

Nếu được phép, người nhận có thể thêm Cat vào danh sách chỉ dành cho Dog. Điều đó phá vỡ tính an toàn kiểu.

### 11.2. Producer và consumer

Một generic type có thể sản xuất giá trị T để người dùng đọc, tiêu thụ giá trị T để người dùng ghi, hoặc làm cả hai.

- Producer chỉ trả dữ liệu T thường có thể dùng covariance.
- Consumer chỉ nhận dữ liệu T thường có thể dùng contravariance.
- Thành phần vừa đọc vừa ghi thường cần invariance hoặc một thiết kế API khác.

Trong Java, wildcard giúp mô tả các vị trí này:

~~~java
void readAnimals(List<? extends Animal> source)
void addDogs(List<? super Dog> destination)
~~~

### 11.3. Variance declaration ở các ngôn ngữ khác

Một số ngôn ngữ cho phép khai báo variance ngay trên tham số kiểu của interface hoặc lớp. Ví dụ, một interface chỉ sản xuất T có thể được khai báo covariant.

Khi thiết kế DSL, cần quyết định variance ở vị trí khai báo hay vị trí sử dụng. Cách khai báo variance có thể làm API gọn hơn, nhưng type checker phải bảo đảm tham số kiểu chỉ được dùng ở những vị trí phù hợp.

## 12. Generic trong mô hình và API của DSL

### 12.1. Collection type

DSL thường cần các kiểu collection:

~~~text
List<T>
Set<T>
Map<K, V>
Sequence<T>
~~~

Mỗi kiểu cần định nghĩa:

- Số lượng và vai trò tham số kiểu.
- Thứ tự phần tử có được giữ không.
- Phần tử trùng lặp có được phép không.
- Kiểu khóa có yêu cầu hash hoặc equality không.
- Các phép toán có làm thay đổi collection không.

Không nên chỉ đặt tên generic mà không định nghĩa ngữ nghĩa collection.

### 12.2. Optional và Result

Một kiểu Optional<T> biểu diễn giá trị có thể vắng mặt. Result<T, E> biểu diễn kết quả có thể thành công hoặc thất bại.

~~~text
Optional<Customer>
Result<Payment, PaymentError>
~~~

Các kiểu này làm rõ những khả năng trong hợp đồng API. Chúng giúp tránh dùng null cho nhiều ý nghĩa khác nhau như “không có dữ liệu”, “không tìm thấy” và “lỗi xử lý”.

### 12.3. Function type

Một DSL có thể biểu diễn kiểu hàm:

~~~text
Function<T, R>
Predicate<T>
Comparator<T>
~~~

Function<T, R> nhận T và trả R; Predicate<T> nhận T và trả Boolean; Comparator<T> so sánh hai giá trị T theo một quy tắc.

Những kiểu hàm này hỗ trợ higher-order function như map, filter và sort.

### 12.4. Generic type cho biểu thức

Khi DSL có type-safe AST, Expression<T> mô tả một biểu thức tạo ra giá trị kiểu T.

~~~text
Expression<Integer>
Expression<Money>
Expression<Boolean>
~~~

Một toán tử số học có thể nhận Expression<Number> theo quy tắc kiểu được DSL định nghĩa. Một điều kiện trong rule engine thường yêu cầu Expression<Boolean>.

Type checker có thể phát hiện việc dùng Expression<Money> ở vị trí cần Boolean trước khi thực thi.

### 12.5. Generic cho adapter và provider

Một adapter có thể được định nghĩa theo kiểu dữ liệu đầu vào và đầu ra:

~~~text
Adapter<Request, Response>
Converter<Source, Target>
Repository<Entity, Id>
~~~

Điều này giúp các module khác nhau triển khai cùng một hợp đồng mà vẫn giữ kiểu miền cụ thể.

### 12.6. Generic và schema động

Nếu DSL hỗ trợ schema được tải từ bên ngoài, type parameter có thể được xác định khi biên dịch hoặc khi nạp schema. Cần quyết định:

- Kiểu có được cố định trong mỗi chương trình không?
- Schema có thể thay đổi giữa hai lần thực thi không?
- Chương trình đã biên dịch có cần kiểm tra lại khi schema thay đổi không?
- Tham số kiểu được lưu trong tài liệu hay chỉ tồn tại trong bộ nhớ?

Nếu kiểu phụ thuộc vào schema động, runtime cần có cách xác thực rằng schema thực tế vẫn phù hợp với kiểu mà chương trình đã được kiểm tra.

## 13. Type inference và generic trong compiler của DSL

### 13.1. Các bước khái quát

Một type checker có hỗ trợ generic thường cần:

1. Thu thập tham số kiểu và bound từ khai báo.
2. Phân tích kiểu của các đối số thực tế.
3. Tạo ràng buộc giữa tham số kiểu và kiểu đã biết.
4. Giải các ràng buộc để tìm kiểu phù hợp.
5. Kiểm tra bound và quan hệ subtype.
6. Thay tham số kiểu bằng nghiệm trong kiểu kết quả.
7. Báo lỗi nếu không có nghiệm hoặc có nhiều nghiệm không thể phân giải.

Ví dụ:

~~~text
function identity<T>(value: T): T
identity(42)
~~~

Type checker tạo ràng buộc T = Integer và suy ra kết quả Integer.

### 13.2. Unification

Unification là một kỹ thuật tìm phép thay thế cho biến kiểu để làm cho hai biểu thức kiểu tương thích.

Ví dụ, với:

~~~text
List<T> = List<String>
~~~

nghiệm đơn giản là T = String.

Với kiểu lồng nhau:

~~~text
Map<String, List<T>> = Map<String, List<Customer>>
~~~

hệ thống có thể suy ra T = Customer bằng cách so sánh cấu trúc tương ứng.

Một DSL đơn giản có thể dùng unification cơ bản. Nếu hỗ trợ subtype, variance, overload và generic đệ quy, thuật toán suy luận sẽ phức tạp hơn.

### 13.3. Ràng buộc subtype

Không phải lúc nào hai kiểu cũng cần bằng nhau. Một lời gọi có thể yêu cầu kiểu đối số là subtype của bound:

~~~text
T <: Number
~~~

Ký hiệu này đọc là T là subtype của Number. Type checker cần giải các quan hệ subtype cùng với những ràng buộc bằng nhau hoặc chuyển đổi.

### 13.4. Suy luận thất bại

Ví dụ, hàm:

~~~text
function sameType<T>(left: T, right: T): T
~~~

được gọi với Integer và Customer. Nếu hai kiểu không có kiểu chung được phép hoặc không có chuyển đổi hợp lệ, suy luận phải thất bại.

Thông báo tốt nên nêu:

- Tham số kiểu đang được suy luận.
- Các kiểu đã thu thập từ từng đối số.
- Ràng buộc bị mâu thuẫn.
- Cách sửa, chẳng hạn chuyển đổi rõ ràng hoặc dùng một kiểu chung.

### 13.5. Giới hạn suy luận để dễ hiểu

Suy luận càng mạnh càng có thể làm cú pháp ngắn, nhưng cũng khó giải thích lỗi. Một DSL hướng người dùng có thể giới hạn suy luận trong các trường hợp dễ dự đoán và yêu cầu khai báo kiểu rõ ở ranh giới quan trọng.

## 14. Higher-kinded types và mức trừu tượng cao hơn

### 14.1. Type constructor

Một generic type như List<T> có thể được xem là một type constructor: nó nhận một kiểu T và tạo ra một kiểu mới List<T>.

Tương tự:

~~~text
Optional<T>
Result<T, E>
Map<K, V>
~~~

### 14.2. Tham số hóa theo type constructor

Trong một số hệ kiểu nâng cao, tham số có thể đại diện cho một type constructor chứ không chỉ một kiểu cụ thể. Đây là ý tưởng của higher-kinded types.

Ví dụ khái niệm:

~~~text
Functor<F>
  map<A, B>(value: F<A>, transform: Function<A, B>): F<B>
~~~

F là một constructor nhận một tham số kiểu. List, Optional hoặc một kiểu container khác có thể cung cấp cấu trúc phù hợp nếu đáp ứng hợp đồng.

### 14.3. Khi nào cần?

Higher-kinded types hỗ trợ trừu tượng hóa các thao tác chung trên nhiều loại container. Tuy nhiên, nó làm hệ kiểu và thông báo lỗi phức tạp hơn.

Một DSL nghiệp vụ thông thường có thể không cần tính năng này. Chỉ nên cân nhắc khi miền hoặc thư viện nền tảng thực sự có các phép toán chung trên nhiều type constructor và nhóm phát triển có khả năng duy trì công cụ tương ứng.

## 15. Generic và đệ quy kiểu

### 15.1. Cấu trúc đệ quy

Một kiểu có thể chứa các giá trị cùng kiểu hoặc kiểu generic liên quan:

~~~text
Tree<T>
  Leaf(value: T)
  Branch(left: Tree<T>, right: Tree<T>)
~~~

Tree<Integer> là cây chứa số nguyên; Tree<Customer> là cây chứa khách hàng.

### 15.2. Generic recursive type trong AST

Một biểu thức có thể chứa các biểu thức con cùng kiểu:

~~~text
Expression<T>
  Literal<T>
  Conditional<T>
  FunctionCall<T>
~~~

Một node điều kiện có thể chứa biểu thức Boolean và hai nhánh có cùng kiểu kết quả T. Type checker cần bảo đảm hai nhánh tương thích.

### 15.3. Ràng buộc đệ quy

Một số khai báo yêu cầu tham số kiểu tự tham chiếu qua interface:

~~~java
public interface Comparable<T> {
    int compareTo(T other);
}
~~~

Kiểu T được so sánh với một giá trị cùng kiểu T. Đây là một dạng ràng buộc đệ quy thường gặp trong generic.

Khi DSL hỗ trợ ràng buộc kiểu đệ quy, cần giới hạn thuật toán kiểm tra để tránh đệ quy vô hạn hoặc tiêu tốn tài nguyên bất thường.

## 16. Generic và hiệu năng

### 16.1. Generic không đồng nghĩa với chậm

Generic chủ yếu là cơ chế trừu tượng và kiểm tra kiểu. Chi phí runtime phụ thuộc vào ngôn ngữ, cách biên dịch và kiểu dữ liệu được dùng.

Trong Java, type erasure có nghĩa nhiều kiểu tham số hóa dùng cùng một lớp runtime. Tuy vậy, boxing/unboxing, dispatch qua interface hoặc cấu trúc dữ liệu tổng quát vẫn có thể ảnh hưởng hiệu năng.

### 16.2. Specialized generic

Một số ngôn ngữ hoặc runtime có thể sinh mã chuyên biệt cho từng kiểu đối số, ví dụ một phiên bản cho số nguyên và một phiên bản cho số thực. Cách này có thể tránh boxing hoặc cho phép tối ưu sâu hơn, nhưng có thể làm tăng kích thước mã và thời gian biên dịch.

### 16.3. Chọn theo nhu cầu miền

Trong DSL xử lý dữ liệu lớn, kiểu generic có thể giúp tái sử dụng pipeline. Nếu hiệu năng trở thành vấn đề, cần đo đạc trước khi chọn specialization, primitive collection hoặc backend riêng.

Không nên hy sinh tính rõ ràng của hệ kiểu chỉ dựa trên giả định rằng generic luôn tạo chi phí đáng kể.

## 17. Thiết kế generic cho DSL

### 17.1. Bắt đầu từ các quan hệ kiểu thực sự cần

Hãy xác định những cấu trúc cần tái sử dụng và mối quan hệ kiểu mà DSL phải giữ. Ví dụ, List<T> có thể cần thiết; một hệ thống higher-kinded type đầy đủ có thể không.

### 17.2. Giới hạn số tham số

Nhiều tham số kiểu làm chữ ký khó đọc. Mỗi tham số nên đại diện cho một vai trò khác nhau và có tên hoặc tài liệu rõ.

### 17.3. Dùng bound có mục đích

Chỉ thêm bound khi thuật toán cần một khả năng cụ thể. Tránh ràng buộc kiểu quá mạnh làm loại trừ những kiểu có thể hoạt động hợp lệ.

### 17.4. Quy định variance

Nếu DSL có subtype, cần xác định generic invariant, covariant hay contravariant ở đâu. Không nên để người dùng suy đoán rằng List<Dog> có thể thay cho List<Animal>.

### 17.5. Thiết kế type inference có giới hạn

Suy luận nên dễ dự đoán. Khi không thể suy luận duy nhất, hệ thống cần yêu cầu ghi kiểu tường minh và giải thích ràng buộc bị thiếu.

### 17.6. Tích hợp với kiểu động ở ranh giới

Dữ liệu từ JSON, API hoặc người dùng có thể chưa có kiểu tĩnh. Nên xác thực và chuyển đổi dữ liệu đó vào kiểu miền trước khi dùng trong các biểu thức generic.

### 17.7. Diagnostic theo khái niệm của DSL

Thay vì chỉ báo lỗi type variable T không thỏa bound, thông báo nên giải thích kiểu thực tế, kiểu mong đợi và thao tác miền đang yêu cầu.

### 17.8. Tài liệu hóa bằng ví dụ cụ thể

Mỗi generic API nên có ví dụ với nhiều kiểu đối số, trường hợp suy luận, trường hợp bị từ chối và cách giải quyết.

## 18. Ví dụ tổng hợp: generic trong DSL xử lý đơn hàng

Giả sử DSL cần biểu diễn pipeline đọc đơn hàng, chuyển đổi dữ liệu và tạo kết quả.

### 18.1. Các kiểu cơ bản

~~~text
Order
Customer
Money
PaymentError
~~~

### 18.2. Các kiểu generic

~~~text
List<T>
Optional<T>
Result<T, E>
Function<T, R>
~~~

### 18.3. Khai báo hàm tổng quát

~~~text
function map<T, R>(
    values: List<T>,
    transform: Function<T, R>
): List<R>
~~~

### 18.4. Sử dụng

~~~text
let orders: List<Order> = loadOrders()

let totals: List<Money> =
    map(orders, order -> order.total)
~~~

Từ kiểu đầu vào List<Order> và kiểu trả về của biểu thức order.total là Money, type checker suy ra:

- T = Order.
- R = Money.
- Kết quả là List<Money>.

### 18.5. Kết quả có lỗi

~~~text
function loadPayment(
    orderId: OrderId
): Result<Payment, PaymentError>
~~~

Người gọi cần xử lý hai nhánh:

~~~text
match loadPayment(order.id) {
    Success(payment) -> confirm(payment)
    Failure(error) -> recordFailure(error)
}
~~~

Generic giúp giữ kiểu Payment ở nhánh thành công và PaymentError ở nhánh thất bại. Cấu trúc này làm hợp đồng hàm rõ hơn một kết quả không kiểu hoặc giá trị null.

### 18.6. Ràng buộc kiểu

Nếu một hàm cần sắp xếp danh sách:

~~~text
function sort<T where T supports Comparable<T>>(
    values: List<T>
): List<T>
~~~

Type checker chỉ chấp nhận T nếu có khả năng so sánh phù hợp. Nếu Order không có thứ tự tự nhiên, người dùng cần truyền Comparator<Order> hoặc chọn một thuộc tính sắp xếp cụ thể.

## 19. Những lỗi thường gặp khi sử dụng generic

### 19.1. Dùng Object thay cho kiểu tham số hóa

Việc dùng Object cho mọi giá trị làm mất thông tin kiểu và tăng nhu cầu ép kiểu. Nên dùng generic khi cấu trúc có thể giữ một quan hệ kiểu rõ ràng.

### 19.2. Dùng raw type

Raw type bỏ qua kiểm tra generic và có thể làm lỗi xuất hiện ở runtime. Mã mới nên giữ tham số kiểu đầy đủ.

### 19.3. Nhầm subtype với generic subtype

Integer là subtype của Number không có nghĩa List<Integer> là subtype của List<Number> trong Java. Cần hiểu invariance và wildcard.

### 19.4. Dùng wildcard ở mọi nơi

Wildcard có thể làm chữ ký khó hiểu nếu không có nhu cầu variance thực tế. Nếu cần quan hệ giữa nhiều vị trí, một tham số kiểu có tên thường rõ hơn.

### 19.5. Ràng buộc quá mạnh

Một hàm chỉ cần đọc giá trị nhưng yêu cầu kiểu cụ thể không cần thiết sẽ hạn chế khả năng tái sử dụng. Hãy ràng buộc theo năng lực cần dùng, không theo một lớp triển khai cụ thể nếu có thể dùng interface.

### 19.6. Suy luận kiểu mơ hồ

Nếu nhiều kiểu có thể thỏa mãn, không nên để compiler chọn ngầm một kiểu có thể làm mất dữ liệu. Cần yêu cầu kiểu tường minh hoặc quy tắc chuyển đổi rõ.

### 19.7. Mong đợi generic còn đầy đủ ở runtime trong Java

Type erasure làm mất thông tin tham số kiểu ở runtime. Khi cần kiểm tra hoặc deserialize kiểu generic, cần metadata hoặc type token phù hợp.

### 19.8. Dùng generic cho điều kiện giá trị

Generic mô tả quan hệ giữa các kiểu, không thay thế mọi điều kiện nghiệp vụ. “Đơn hàng đã thanh toán” là trạng thái giá trị; “T triển khai Comparable” là ràng buộc kiểu. Cần đặt quy tắc ở đúng lớp.

## 20. Câu hỏi tự đánh giá

1. Tham số kiểu khác đối số kiểu như thế nào?
2. Vì sao List<T> có thể thay thế nhiều lớp danh sách chuyên biệt?
3. Generic method khác generic class ở điểm nào?
4. Bound giúp type checker bảo đảm điều gì?
5. Phân biệt upper-bounded và lower-bounded wildcard trong Java.
6. PECS có ý nghĩa gì khi thiết kế API?
7. Vì sao List<Integer> không thể gán cho List<Number> trong Java?
8. Type inference sử dụng những thông tin nào để xác định tham số kiểu?
9. Type erasure tạo ra những giới hạn gì?
10. Khi nào DSL nên dùng generic đơn giản và khi nào cần variance hoặc higher-kinded type?

## Kết luận

Tham số hóa và generic cho phép định nghĩa kiểu, hàm và cấu trúc dữ liệu có thể tái sử dụng với nhiều kiểu cụ thể mà vẫn giữ được quan hệ kiểu. Tham số kiểu tạo ra khuôn mẫu; đối số kiểu xác định cách sử dụng cụ thể. Bound giới hạn những kiểu được phép, type inference có thể tự suy ra kiểu, còn variance mô tả cách quan hệ subtype tương tác với generic.

Trong DSL, generic có thể xuất hiện ở collection, kết quả, hàm, biểu thức, AST node, repository và adapter. Mức hỗ trợ cần phù hợp với mục tiêu của ngôn ngữ. Một hệ kiểu hữu ích nên có chữ ký dễ hiểu, ràng buộc vừa đủ, suy luận dự đoán được, diagnostic rõ và quy tắc tương thích với dữ liệu động. Khi thiết kế đúng, generic giúp DSL tái sử dụng cấu trúc mà vẫn bảo vệ tính nhất quán của kiểu dữ liệu.
