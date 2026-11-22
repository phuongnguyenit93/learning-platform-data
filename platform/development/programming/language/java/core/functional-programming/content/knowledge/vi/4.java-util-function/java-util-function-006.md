# BiFunction, BiPredicate và BiConsumer trong Java

Trong gói **java.util.function**, Java cung cấp ba functional interface thường gặp khi một thao tác phải nhận **hai đầu vào**: **BiFunction**, **BiPredicate** và **BiConsumer**. Cả ba đều cho phép biểu diễn hành vi bằng lambda hoặc method reference, nhưng có hợp đồng đầu ra khác nhau. Nắm vững sự khác nhau này giúp thiết kế callback, xử lý Map, kết hợp quy tắc kiểm tra và tách phép tính khỏi tác dụng phụ.

Bài học áp dụng cho Java 17 trở lên, giải thích chữ ký generic, phương thức trừu tượng duy nhất (SAM), các default method, ví dụ thực tế, những giới hạn về kiểu, thứ tự đánh giá, hiệu năng và lỗi thường gặp.

## 1. Bản chất: hai tham số, ba kiểu hành vi

| Interface | Phương thức SAM | Hai đầu vào | Kết quả | Ví dụ |
| --- | --- | --- | --- | --- |
| **BiFunction<T, U, R>** | R apply(T t, U u) | T và U | R | Tính thành tiền từ số lượng và đơn giá |
| **BiPredicate<T, U>** | boolean test(T t, U u) | T và U | boolean | Kiểm tra số tồn kho có đáp ứng số lượng yêu cầu |
| **BiConsumer<T, U>** | void accept(T t, U u) | T và U | Không có giá trị trả về | Ghi log với mã hàng và số tiền |

Trong tên **Bi**, chữ **Bi** cho biết hàm nhận hai tham số. Hai tham số không bắt buộc cùng kiểu. Với BiFunction, đầu ra R có thể khác cả T lẫn U; với BiPredicate, kết quả luôn là boolean nguyên thủy; với BiConsumer, kết quả của phương thức SAM là void.

Cả ba đều được đánh dấu **@FunctionalInterface** trong Java và có thể được thực thi bằng lambda. Chúng là những **kiểu đích** (target types): compiler dựa vào T, U và R của phép gán/đối số để suy luận kiểu tham số lambda.

Ví dụ so sánh ngắn:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
    (a, b) -> a + b;
java.util.function.BiPredicate<Integer, Integer> greater =
    (a, b) -> a > b;
java.util.function.BiConsumer<String, Integer> print =
    (name, score) -> System.out.println(name + ": " + score);
~~~

Đây là **các đoạn minh họa đặt trong phương thức**, không phải chương trình chạy độc lập. Khi áp dụng:

~~~java
System.out.println(add.apply(4, 6));       // 10
System.out.println(greater.test(4, 6));    // false
print.accept("Lan", 9);                    // Lan: 9
~~~

Điểm quan trọng: không chỉ khác **kiểu kết quả**, chúng còn được dùng với **mục đích** khác nhau: biến đổi, quyết định điều kiện, hoặc thực hiện một hành động.

## 2. BiFunction<T, U, R>: biến hai đầu vào thành một kết quả

Chữ ký khái niệm:

~~~java
@FunctionalInterface
public interface BiFunction<T, U, R> {
    R apply(T t, U u);

    // Có default method andThen(...) để kết hợp kết quả.
}
~~~

- **T:** kiểu đối số thứ nhất.
- **U:** kiểu đối số thứ hai.
- **R:** kiểu giá trị trả về.
- **apply(t, u):** thực hiện phép tính/biến đổi.

Ví dụ cùng kiểu đầu vào và đầu ra:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
    (quantity, unitPrice) -> quantity * unitPrice;
System.out.println(multiply.apply(3, 20));  // 60
~~~

Ví dụ khác kiểu:

~~~java
BiFunction<String, Integer, String> repeat =
    (text, count) -> text.repeat(count);
System.out.println(repeat.apply("Ja", 3));   // JaJaJa
~~~

Để chạy các đoạn này trong một lớp Java, thêm import java.util.function.BiFunction và đặt chúng trong main; lưu ý String.repeat có từ Java 11 và không chấp nhận số lần âm.

BiFunction có thể tham chiếu đến một phương thức static nhận hai tham số:

~~~java
BiFunction<Integer, Integer, Integer> safeMultiply =
    Math::multiplyExact;
~~~

Math.multiplyExact(int, int) phát hiện tràn số int bằng ArithmeticException, khác với phép nhân int thông thường có thể tràn số mà không báo lỗi.

BiFunction cũng có thể dùng method reference tới constructor nhận hai tham số:

~~~java
record Product(String name, int price) {}

BiFunction<String, Integer, Product> newProduct =
    Product::new;
~~~

Dòng record là khai báo kiểu cần đặt ở vị trí hợp lệ (ví dụ cấp lớp hoặc trong phương thức); đoạn minh họa này cần đặt trong ngữ cảnh Java tương ứng. BiFunction trả một Product, không nhất thiết là kiểu của một trong hai đầu vào.

### 2.1. Kết hợp bằng andThen

BiFunction có default method **andThen(Function<? super R, ? extends V> after)**, thực hiện BiFunction trước rồi đưa **kết quả duy nhất R** vào Function sau đó:

~~~java
BiFunction<Integer, Integer, Integer> amount =
    (quantity, price) -> quantity * price;

BiFunction<Integer, Integer, String> labelled =
    amount.andThen(total -> "Total=" + total);

System.out.println(labelled.apply(2, 50)); // Total=100
~~~

Hình dung:

~~~text
T, U --BiFunction.apply--> R --Function.apply--> V
~~~

Điểm dễ nhầm: **andThen nhận Function có một tham số**, vì bước sau chỉ nhận kết quả R. Nó không nhận một BiFunction khác để xử lý lại hai đối số ban đầu.

Quy tắc thực thi:

- Lời gọi labelled.apply(t, u) trước tiên thực hiện amount.apply(t, u).
- Sau đó thực hiện Function sau với kết quả vừa tạo.
- Nếu hàm đầu ném ngoại lệ, hàm sau **không chạy**.
- Truyền after = null cho andThen gây NullPointerException tại lúc tạo phép kết hợp.
- andThen không tự xử lý null trong giá trị R; Function sau phải tự hỗ trợ null nếu cần.

### 2.2. Tách logic nghiệp vụ thành các phép biến đổi

BiFunction phù hợp khi kết quả có thể được **trả về như dữ liệu**, thay vì ghi trực tiếp vào biến bên ngoài:

~~~java
BiFunction<Integer, Integer, Integer> net =
    (gross, discount) -> gross - discount;

int finalAmount = net.apply(1000, 120);
~~~

Có thể truyền công thức giá vào một phương thức xử lý khác, thay đổi chính sách bằng cách thay BiFunction trong unit test, hoặc kết hợp với Function.andThen. Nên tránh sửa một biến dùng chung bên trong lambda nếu mục tiêu là phép tính có thể lặp lại.

## 3. BiPredicate<T, U>: kiểm tra điều kiện trên hai dữ liệu

Chữ ký khái niệm:

~~~java
@FunctionalInterface
public interface BiPredicate<T, U> {
    boolean test(T t, U u);

    // Default methods: and(...), or(...), negate().
}
~~~

BiPredicate nhận hai đầu vào rồi trả boolean. Hữu ích khi điều kiện phụ thuộc **quan hệ giữa hai giá trị**, ví dụ kiểm tra số hàng có sẵn so với số lượng đặt, khoảng điểm với ngưỡng tối thiểu, hoặc quyền của người dùng đối với tài nguyên.

~~~java
BiPredicate<Integer, Integer> sufficient =
    (available, requested) -> requested > 0 && available >= requested;

System.out.println(sufficient.test(5, 3));  // true
System.out.println(sufficient.test(2, 3));  // false
System.out.println(sufficient.test(5, -1)); // false
~~~

Điều kiện requested > 0 cho thấy việc viết một BiPredicate tốt không chỉ là so sánh hai giá trị mà còn làm rõ **hợp đồng hợp lệ** của yêu cầu.

### 3.1. Kết hợp điều kiện: and, or và negate

Các default method của BiPredicate:

- **and(other):** true khi điều kiện bên trái **và** điều kiện bên phải đều true.
- **or(other):** true khi **ít nhất một** điều kiện true.
- **negate():** đảo ngược kết quả của điều kiện hiện có.

~~~java
BiPredicate<Integer, Integer> enough =
    (available, requested) -> available >= requested;
BiPredicate<Integer, Integer> valid =
    (available, requested) -> requested > 0;

BiPredicate<Integer, Integer> accepted = enough.and(valid);
BiPredicate<Integer, Integer> rejected = accepted.negate();

System.out.println(accepted.test(5, 3)); // true
System.out.println(rejected.test(2, 3)); // true
~~~

Hai phép **and/or có short-circuit**:

- Với and, nếu predicate đầu trả false thì predicate sau không được gọi.
- Với or, nếu predicate đầu trả true thì predicate sau không được gọi.
- Với negate, predicate gốc được gọi rồi kết quả bị đảo; đối tượng predicate ban đầu không bị thay đổi.

Đặc tính short-circuit vừa có lợi cho hiệu năng vừa cho phép tránh một điều kiện chưa an toàn khi điều kiện kiểm tra trước chưa thỏa. Nhưng nó cũng là lý do không nên đặt tác dụng phụ như tăng biến đếm, ghi log, gửi thông báo bên trong các predicate kết hợp: số lần thực thi callback có thể khác tùy đầu vào và thứ tự ghép.

### 3.2. Ví dụ áp dụng giới hạn của hai giá trị

~~~java
BiPredicate<Integer, Integer> inRange =
    (value, upperBound) -> value >= 0 && value <= upperBound;
~~~

Một lần gọi inRange.test(7, 10) trả true. Đây là quan hệ giữa value và upperBound, không phải trường hợp Predicate<Integer> chỉ nhìn một đầu vào.

Khi điều kiện thực sự chỉ cần một dữ liệu, dùng **Predicate<T>**; không nên bịa thêm một đối số chỉ để dùng BiPredicate.

## 4. BiConsumer<T, U>: thực hiện hành động với hai tham số

Chữ ký khái niệm:

~~~java
@FunctionalInterface
public interface BiConsumer<T, U> {
    void accept(T t, U u);

    // Default method: andThen(BiConsumer<? super T, ? super U> after)
}
~~~

BiConsumer nhận hai đối số nhưng phương thức accept không trả kết quả. Ví dụ thường gặp là **in, ghi log, cập nhật dữ liệu, ghi audit, đẩy sự kiện** hoặc callback kết nối với một hệ thống bên ngoài.

~~~java
BiConsumer<String, Integer> printScore =
    (name, score) -> System.out.println(name + "=" + score);

printScore.accept("Mai", 10); // Mai=10
~~~

Không nên dùng BiConsumer khi cần lấy lại giá trị tính toán. Nếu bạn muốn biến hai đầu vào thành một kết quả, dùng BiFunction. Nếu muốn hỏi đúng/sai, dùng BiPredicate.

### 4.1. andThen của BiConsumer

BiConsumer.andThen nối hai hành động **theo thứ tự**: chạy consumer gốc rồi chạy consumer sau, với **cùng hai đối số**.

~~~java
BiConsumer<String, Integer> first =
    (name, score) -> System.out.println("A:" + name + ":" + score);
BiConsumer<String, Integer> second =
    (name, score) -> System.out.println("B:" + name + ":" + score);

BiConsumer<String, Integer> both = first.andThen(second);
both.accept("An", 8);
~~~

Stdout của đoạn mã:

~~~text
A:An:8
B:An:8
~~~

Nếu hành động đầu ném ngoại lệ, hành động sau **không được gọi**; andThen không tự rollback những tác dụng phụ đã xảy ra. Truyền after = null gây NullPointerException khi tạo chuỗi.

Điểm phân biệt với BiFunction.andThen: **BiConsumer.andThen nhận BiConsumer khác và cả hai cùng nhận T, U**, trong khi BiFunction.andThen nhận Function xử lý **kết quả R**.

### 4.2. BiConsumer và tính chất tác dụng phụ

Consumer là kiểu hành vi phù hợp với tác dụng phụ, nhưng không có nghĩa mọi lambda BiConsumer đều làm thay đổi trạng thái bên ngoài. Một lambda chỉ tính rồi bỏ kết quả vẫn có thể thuộc kiểu void-compatible nhưng thường không có giá trị thực tế.

Khi một BiConsumer sửa dữ liệu dùng chung, người viết cần xét:

- Có khả năng bị gọi nhiều lần hoặc gọi lại khi retry không?
- Có được gọi trên nhiều luồng không? Nếu có, dữ liệu đích có an toàn luồng không?
- Có phụ thuộc vào thứ tự hay tính nguyên tử của chuỗi hành động không?
- Nếu hành động thứ hai thất bại, hành động thứ nhất đã thực hiện được thì xử lý thế nào?

BiConsumer không đưa ra bảo đảm transaction, retry, idempotency hoặc thread-safety. Đây là trách nhiệm của API gọi nó và thiết kế ứng dụng.

## 5. So sánh default method của ba interface

| Interface | Default method quan trọng | Loại đối số nhận thêm | Đặc điểm |
| --- | --- | --- | --- |
| BiFunction<T,U,R> | andThen(after) | Function<? super R,? extends V> | Biến đổi kết quả R thành V |
| BiPredicate<T,U> | and(other), or(other), negate() | BiPredicate hoặc không có đối số | Kết hợp logic boolean; and/or short-circuit |
| BiConsumer<T,U> | andThen(after) | BiConsumer<? super T,? super U> | Thực hiện hai hành động tuần tự với cùng T, U |

Không có phương thức compose mặc định cho BiFunction hoặc BiConsumer như Function.compose, và không có andThen theo kiểu biến đổi kết quả cho BiPredicate. Khi cần API kết hợp phức tạp hơn, hãy tạo function trung gian rõ ràng hoặc tự khai báo interface phù hợp.

Cách nhớ theo mục đích: **BiFunction trả một giá trị; BiPredicate trả điều kiện; BiConsumer thực hiện hành động.**

## 6. Những API Java sử dụng BiFunction và BiConsumer

Các interface này hữu ích vượt ra ngoài ví dụ khai báo lambda độc lập. Java Collections Framework sử dụng chúng để đưa hành vi vào phương thức Map.

### 6.1. Map.forEach nhận BiConsumer

~~~java
java.util.Map<String, Integer> scores =
    new java.util.LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);

scores.forEach((name, score) ->
    System.out.println(name + "=" + score));
~~~

Stdout:

~~~text
An=8
Binh=9
~~~

BiConsumer nhận key và value tương ứng. Ví dụ dùng LinkedHashMap để dễ dự đoán thứ tự duyệt theo thứ tự chèn; không nên mặc định HashMap hoặc Map.of luôn duyệt theo thứ tự đã viết.

### 6.2. Map.compute và Map.computeIfPresent nhận BiFunction

~~~java
java.util.Map<String, Integer> inventory =
    new java.util.HashMap<>();
inventory.put("pen", 5);

inventory.computeIfPresent("pen", (key, oldCount) -> oldCount + 2);
System.out.println(inventory.get("pen")); // 7
~~~

Trong Map.computeIfPresent, BiFunction nhận **key (K)** và **giá trị hiện tại (V)** rồi trả giá trị V mới. Callback thường được gọi khi có mapping tới giá trị **không null**, theo hợp đồng của Map. Nếu callback trả null, mapping tương ứng có thể bị **xóa**, chứ không tự động trở thành một phép biến đổi giữ nguyên giá trị. Với Map.compute, callback có thể nhận giá trị cũ là null khi mapping chưa có hoặc ánh xạ tới null (tùy loại Map).

Vì các trường hợp null quan trọng, đừng vô tình đặt logic tùy ý vào compute/merge mà chưa kiểm tra hợp đồng của phương thức.

### 6.3. Map.merge: BiFunction nhận hai giá trị, không nhận key

~~~java
java.util.Map<String, Integer> totals =
    new java.util.HashMap<>();
totals.merge("book", 2, Integer::sum);
totals.merge("book", 3, Integer::sum);

System.out.println(totals.get("book")); // 5
~~~

Map.merge có tham số remappingFunction tương thích với **BiFunction<? super V, ? super V, ? extends V>**. Hai đối số callback ở đây là **giá trị cũ** và **giá trị muốn gộp**, không phải key và value. Nếu key chưa có mapping không-null, merge dùng giá trị cung cấp mà không cần gọi remappingFunction; nếu callback trả null khi được gọi, mapping bị xóa.

Cùng cú pháp lambda (a, b) -> a + b có thể có ý nghĩa khác trong compute và merge. Luôn đọc chữ ký API thực tế để biết **hai đối số đại diện cho gì**.

### 6.4. Map.replaceAll cũng dùng BiFunction

~~~java
java.util.Map<String, Integer> prices =
    new java.util.HashMap<>();
prices.put("a", 10);
prices.put("b", 20);

prices.replaceAll((key, oldPrice) -> oldPrice + 1);
~~~

Ở đây BiFunction nhận key và value cũ rồi trả value mới. replaceAll sửa nội dung Map; mặc dù callback có thể thuần, **lời gọi Map.replaceAll** vẫn gây tác dụng phụ trên Map. Cần phân biệt tính thuần của hàm callback với tính thuần của **toàn bộ lời gọi API**.

### 6.5. BiPredicate thường là quy tắc nghiệp vụ tự truyền

java.util.Map không có một API phổ thông tương đương forEach nhận trực tiếp BiPredicate để lọc theo key và value. Khi cần kiểm tra đồng thời hai yếu tố, ta có thể tự định nghĩa hàm:

~~~java
static <T, U> boolean check(
        T first,
        U second,
        java.util.function.BiPredicate<? super T, ? super U> rule) {
    return rule.test(first, second);
}
~~~

Dùng với dữ liệu cụ thể:

~~~java
boolean ok = check(5, 3,
    (available, requested) -> available >= requested);
~~~

Việc truyền BiPredicate vào phương thức có ích khi cần nhiều quy tắc thay thế nhau trong test, tạo chính sách xác thực hoặc kết hợp điều kiện.

## 7. Mối quan hệ với Function, Predicate, Consumer và BinaryOperator

Gói java.util.function có các interface một đầu vào tương ứng:

| Một đầu vào | Hai đầu vào |
| --- | --- |
| Function<T,R> | BiFunction<T,U,R> |
| Predicate<T> | BiPredicate<T,U> |
| Consumer<T> | BiConsumer<T,U> |

Một số interface khác cũng nhận hai giá trị nhưng có ràng buộc mạnh hơn:

**BinaryOperator<T>** là một specialization của BiFunction<T,T,T>, tức cả hai đầu vào và đầu ra phải cùng kiểu T.

~~~java
java.util.function.BinaryOperator<Integer> max = Integer::max;
System.out.println(max.apply(4, 9)); // 9
~~~

BinaryOperator thường phù hợp khi kết hợp hai giá trị cùng loại, ví dụ bộ cộng dồn cho reduce hoặc merge, và có các phương thức static như minBy/maxBy để tạo operator dựa trên Comparator.

**IntBinaryOperator** là functional interface chuyên biệt cho hai int nguyên thủy và trả int:

~~~java
java.util.function.IntBinaryOperator sum = Integer::sum;
System.out.println(sum.applyAsInt(4, 9)); // 13
~~~

IntBinaryOperator **không phải subinterface của BiFunction<Integer,Integer,Integer>**; nó có SAM riêng nhận/trả int nguyên thủy.

Nếu chỉ cần hai đầu vào kiểu Object và kết quả int nguyên thủy, có **ToIntBiFunction<T,U>**; tương tự có ToLongBiFunction và ToDoubleBiFunction. Nếu cần consumer nhận một đối tượng và một giá trị int nguyên thủy, có **ObjIntConsumer<T>** (cùng họ ObjLongConsumer, ObjDoubleConsumer).

Không tồn tại một interface tên **IntBiPredicate** trong gói java.util.function chuẩn. Khi muốn predicate hai tham số int mà tránh boxing, có thể tự tạo functional interface chuyên biệt:

~~~java
@FunctionalInterface
interface IntPairTest {
    boolean test(int left, int right);
}
~~~

BiPredicate<Integer,Integer> vẫn thích hợp cho nhiều bài toán, nhưng khi callback chạy ở vòng lặp nóng với khối lượng dữ liệu lớn, đánh giá chi phí boxing/unboxing và đo hiệu năng trước khi tối ưu.

## 8. Generics, type inference và phương thức tham chiếu

Ba interface đều là **generic interface có SAM không generic ở cấp phương thức**. T và U được khai báo trên interface, còn R chỉ có ở BiFunction. Bởi vậy lambda có thể nhận target type rõ ràng và compiler suy luận tham số lambda:

~~~java
java.util.function.BiFunction<String, Integer, String> format =
    (text, count) -> text + ":" + count;
~~~

Trong target trên, tham số text có kiểu String, count có kiểu Integer. Với method reference, chữ ký phương thức được tham chiếu cũng phải tương thích:

~~~java
java.util.function.BiPredicate<String, String> same =
    String::equals;
~~~

Dạng tham chiếu tới phương thức instance của đối tượng được truyền vào có thể hoạt động như (a, b) -> a.equals(b) khi target phù hợp; cụ thể String::equals có tham số thứ hai là Object, nhận String được.

### 8.1. Wildcards và variance

Khi viết API có tham số kiểu, khai báo wildcard theo hướng dùng dữ liệu:

~~~java
static <T, U> boolean passes(
        T left,
        U right,
        java.util.function.BiPredicate<? super T, ? super U> condition) {
    return condition.test(left, right);
}
~~~

Điều kiện có thể chấp nhận các kiểu cha của T và U, bởi nó **tiêu thụ** hai đầu vào. Tương tự, một API truyền BiConsumer vào thường có thể nhận BiConsumer<? super T,? super U>.

BiFunction vừa nhận hai giá trị, vừa tạo đầu ra nên dạng linh hoạt trong tham số API thường là:

~~~java
java.util.function.BiFunction<? super T, ? super U, ? extends R>
~~~

T, U dùng super vì hàm nhận dữ liệu; R dùng extends vì hàm tạo ra dữ liệu. Các đoạn chứa T, U, R ở đây là **mẫu chữ ký generic**, không phải câu lệnh Java độc lập.

Ví dụ tham số hóa quá rộng hoặc dùng raw type để né lỗi generic có thể làm mất kiểm tra kiểu tĩnh và phát sinh ClassCastException. Nên giữ type parameter rõ ràng hoặc sử dụng wildcard đúng với mục đích.

### 8.2. Boxing/unboxing và null

Với BiFunction<Integer,Integer,Integer>, kiểu Integer là wrapper: lambda (a,b) -> a+b thường unbox hai đầu vào thành int, cộng rồi box kết quả. Nếu a hoặc b là null, phép cộng sẽ ném NullPointerException.

BiPredicate<Integer,Integer> trả boolean nguyên thủy, nhưng hai đầu vào Integer vẫn có thể null; BiConsumer<String,Integer> có thể nhận null nếu caller truyền null và callback phải tự quyết định cách xử lý.

Không nên mặc định Java tự kiểm tra đầu vào, đổi null thành 0, hoặc bảo đảm không có tràn số. Với bài toán tiền tệ, cân nhắc BigDecimal và chính sách làm tròn; với int, Math.addExact hoặc Math.multiplyExact giúp phát hiện tràn.

### 8.3. Checked exceptions

SAM apply, test và accept của ba interface này **không khai báo checked exception**. Lambda ném trực tiếp IOException hoặc SQLException chưa xử lý sẽ không tương thích với các SAM đó.

Giải pháp phụ thuộc thiết kế: xử lý exception tại ranh giới thích hợp, trả một kiểu kết quả có thể biểu diễn lỗi, hoặc định nghĩa functional interface tùy chỉnh có throws phù hợp. Không nên bắt Exception một cách mù quáng rồi trả null/false, vì làm mất thông tin lỗi nghiệp vụ.

## 9. Chương trình Java 17+ chạy hoàn chỉnh

Bài toán: từ các dòng đặt hàng, dùng **BiPredicate** để quyết định có chấp nhận hay không, dùng **BiFunction** để tính và hiển thị số tiền, dùng **BiConsumer** để in audit và lưu sự kiện. Chương trình cố ý giữ hai hành động cuối riêng khỏi phép tính, giúp phân biệt hàm trả kết quả với tác dụng phụ.

Tạo file **BiInterfacesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;

public class BiInterfacesDemo {
    record OrderLine(String sku, int quantity, int unitPrice) {}

    public static void main(String[] args) {
        Map<String, Integer> stock = Map.of("book", 4, "pen", 2);
        List<OrderLine> lines = List.of(
            new OrderLine("book", 2, 100),
            new OrderLine("pen", 3, 10),
            new OrderLine("pen", 1, 10)
        );

        BiPredicate<Integer, Integer> enoughStock =
            (available, requested) -> requested > 0 && available >= requested;
        BiPredicate<Integer, Integer> withinLimit =
            (available, requested) -> requested <= 2;
        BiPredicate<Integer, Integer> accepted = enoughStock.and(withinLimit);

        BiFunction<Integer, Integer, Integer> lineAmount = Math::multiplyExact;
        BiFunction<Integer, Integer, String> displayAmount =
            lineAmount.andThen(value -> value + " VND");

        List<String> events = new ArrayList<>();
        BiConsumer<String, Integer> log =
            (sku, amount) -> System.out.println("sold:" + sku + "=" + amount);
        BiConsumer<String, Integer> record =
            (sku, amount) -> events.add(sku + "=" + amount);
        BiConsumer<String, Integer> logThenRecord = log.andThen(record);

        int total = 0;
        for (OrderLine line : lines) {
            int available = stock.getOrDefault(line.sku(), 0);
            if (!accepted.test(available, line.quantity())) {
                System.out.println("SKIP " + line.sku() + " x" + line.quantity());
                continue;
            }
            System.out.println(line.sku() + " -> "
                + displayAmount.apply(line.quantity(), line.unitPrice()));
            int amount = lineAmount.apply(line.quantity(), line.unitPrice());
            logThenRecord.accept(line.sku(), amount);
            total = Math.addExact(total, amount);
        }
        System.out.println("total=" + total);
        System.out.println("events=" + events);
        System.out.println("rejected=" + accepted.negate().test(2, 3));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac BiInterfacesDemo.java
java BiInterfacesDemo
~~~

Stdout **chính xác**:

~~~text
book -> 200 VND
sold:book=200
SKIP pen x3
pen -> 10 VND
sold:pen=10
total=210
events=[book=200, pen=10]
rejected=true
~~~

Giải thích theo luồng dữ liệu:

1. Với book, stock = 4 và requested = 2. Cả enoughStock lẫn withinLimit đều true. BiFunction tính 2 × 100 = 200 và andThen tạo chuỗi "200 VND".
2. BiConsumer logThenRecord in sự kiện book trước, rồi lưu "book=200" vào danh sách events. Phép in và phép thêm danh sách là **tác dụng phụ** được đặt ở vị trí rõ ràng.
3. Với dòng pen số lượng 3, stock = 2 nên enoughStock false; BiPredicate.and short-circuit, dòng được bỏ qua và không có sự kiện tương ứng.
4. Với dòng pen số lượng 1, cả hai điều kiện true; số tiền là 10. Tổng hai dòng được nhận là 200 + 10 = 210.
5. events là ArrayList được cập nhật bởi BiConsumer. Chương trình duyệt tuần tự, nên thứ tự hai phần tử là book rồi pen.
6. accepted.negate().test(2,3) là true, vì accepted.test(2,3) là false.

Ví dụ sử dụng **bảng stock cố định** để tập trung minh họa các callback, chưa phải hệ thống trừ kho thật. Khi xây dựng quy trình đặt hàng thực, cần cập nhật tồn kho một cách nhất quán, tính cả các đơn được chấp nhận trước đó, kiểm soát đồng thời và giao dịch. Không nên coi việc chỉ kiểm tra từng dòng với một snapshot stock là đủ để chống bán vượt số lượng.

Trong chương trình, displayAmount áp dụng lineAmount trước để in chuỗi, rồi code gọi lineAmount thêm một lần để lấy amount cho audit và tổng. Điều này an toàn cho phép nhân thuần đang dùng, nhưng trong nghiệp vụ thực nên **tính một lần rồi dùng lại kết quả** nếu phép tính tốn kém hoặc có tác dụng phụ.

## 10. Mẫu áp dụng khác trong ứng dụng

### 10.1. BiFunction cho phép tách chính sách tính toán

~~~java
static int priceAfter(
        int base,
        int discount,
        java.util.function.BiFunction<Integer, Integer, Integer> policy) {
    return policy.apply(base, discount);
}
~~~

Bằng cách truyền vào policy, caller có thể chọn một công thức giảm giá mà không sửa phương thức điều phối. Tuy nhiên, vì các tham số là Integer boxing, với số lượng phép tính lớn hãy cân nhắc IntBinaryOperator hoặc một kiểu dữ liệu nghiệp vụ rõ nghĩa. Nếu công thức tiền có thể làm tròn, xác định rõ thứ tự tính và đơn vị tiền.

### 10.2. BiPredicate để kiểm tra quan hệ giữa hai đối tượng

~~~java
record User(String id, String role) {}
record Resource(String ownerId, boolean publicAccess) {}

java.util.function.BiPredicate<User, Resource> canView =
    (user, resource) ->
        resource.publicAccess() || resource.ownerId().equals(user.id());
~~~

Đây là **đoạn minh họa** có thể đặt trong một phương thức cùng với định nghĩa record phù hợp. Nhu cầu chính của BiPredicate là một điều kiện gắn với **hai thực thể**. Trong hệ thống thực, quy tắc phân quyền còn phải xử lý null, authentication, tài nguyên không tồn tại và nhiều vai trò; ví dụ chỉ thể hiện một quan hệ đơn giản.

### 10.3. BiConsumer cho callback khi kết quả có key và value

~~~java
java.util.function.BiConsumer<String, Integer> audit =
    (key, value) -> System.out.println("Changed " + key + "=" + value);
~~~

BiConsumer có thể được truyền vào một phần xử lý đã quyết định xong dữ liệu, như gửi audit cho cặp mã sản phẩm/số lượng. Dùng BiConsumer khi hành động không cần trả kết quả. Nếu callback cần cho biết thành công/thất bại bằng một giá trị, cân nhắc BiFunction<T,U,Result> hoặc thiết kế một Result riêng, thay vì che giấu thất bại.

## 11. Những lỗi phổ biến khi dùng ba interface

**Lỗi 1 — Gọi sai phương thức SAM.** BiFunction gọi apply, BiPredicate gọi test, BiConsumer gọi accept. Ba tên tương ứng ba hợp đồng khác nhau, không có một hàm chung tên execute trong các interface chuẩn.

**Lỗi 2 — Nhầm BiFunction.andThen với BiConsumer.andThen.** BiFunction nhận Function để biến đổi **một kết quả R**; BiConsumer nhận BiConsumer và truyền **cả hai đối số T, U** vào từng hành động.

**Lỗi 3 — Dùng BiConsumer để tính dữ liệu.** Một lambda vừa cập nhật biến external total vừa không trả kết quả làm code phụ thuộc trạng thái chia sẻ, khó test và không an toàn khi chạy song song. Khi có thể, dùng BiFunction để trả kết quả và đặt tác dụng phụ ở bước riêng.

**Lỗi 4 — Đặt tác dụng phụ trong BiPredicate.** Vì and/or short-circuit, predicate bên phải có thể không chạy; không dùng chúng để bảo đảm gửi log hay tăng bộ đếm đúng số lần.

**Lỗi 5 — Hiểu sai tham số callback của Map.** Map.forEach nhận key và value; compute nhận key và oldValue; merge nhận oldValue và newValue. Cả ba đều nhận hai tham số nhưng ý nghĩa khác nhau.

**Lỗi 6 — Không xét null.** Map.compute và merge có các quy tắc đặc biệt khi callback trả null. Integer bị unbox từ null sẽ ném NullPointerException. Thiết kế cần nêu rõ dữ liệu có thể null hay không.

**Lỗi 7 — Cho rằng lambda tự thread-safe.** BiConsumer sửa ArrayList chung trong parallel stream có thể gây mất dữ liệu hoặc hỏng trạng thái. Các functional interface không tự đồng bộ hay cách ly tác dụng phụ.

**Lỗi 8 — Lạm dụng boxed types ở đường xử lý nóng.** BiFunction<Integer,Integer,Integer> có thể phát sinh boxing/unboxing. Cân nhắc IntBinaryOperator hoặc ToIntBiFunction phù hợp, đồng thời đo hiệu năng thực tế trước khi tối ưu.

**Lỗi 9 — Nhầm kiểu generic.** BiPredicate<T,U> không có tham số kiểu R vì đầu ra cố định boolean. BiConsumer<T,U> không có đầu ra. BiFunction<T,U,R> có ba tham số kiểu. Đừng sử dụng raw type để tránh phải khai báo đúng chữ ký.

**Lỗi 10 — Giả định mỗi callback chỉ chạy một lần.** Tùy API gọi callback, hành vi có thể được thực hiện lại theo luồng điều khiển nghiệp vụ; thứ tự gọi cũng có thể khác trong môi trường đồng thời. Thiết kế tác dụng phụ cần xét retry, exception, idempotency và transaction.

## 12. Tự kiểm tra

1. Khi cả hai đầu vào là Integer nhưng cần trả String, interface nào thích hợp nhất? Vì sao?
2. BiPredicate.and có gọi predicate thứ hai khi predicate thứ nhất false không? Điều đó ảnh hưởng gì nếu predicate thứ hai ghi log?
3. Trong BiFunction.andThen, hàm nhận ở bước sau có mấy tham số và kiểu đầu vào của nó lấy từ đâu?
4. Với Map.merge("x", 2, Integer::sum), callback Integer::sum có nhận key "x" không?
5. BiConsumer.andThen có tiếp tục chạy action thứ hai nếu action đầu ném exception không?
6. Vì sao BinaryOperator<Integer> phù hợp với phép cộng hai Integer, còn BiFunction<Integer,String,Long> phù hợp với kiểu bài toán khác?
7. Nếu tính tổng tiền hàng triệu lần bằng hai int, interface nguyên thủy nào có thể giúp hạn chế boxing?
8. Hãy xác định vị trí tác dụng phụ trong chương trình ví dụ và giải thích vì sao việc gộp hết chúng vào BiFunction không phải thiết kế tốt.

**Ghi nhớ:** chọn **BiFunction** để **trả kết quả từ hai đầu vào**, **BiPredicate** để **đánh giá điều kiện của hai đầu vào**, và **BiConsumer** để **thực hiện hành động với hai đầu vào**. Hiểu SAM, quy tắc kết hợp, generic, boxing, null và tác dụng phụ giúp ứng dụng bộ ba này đúng với API Java và yêu cầu nghiệp vụ.