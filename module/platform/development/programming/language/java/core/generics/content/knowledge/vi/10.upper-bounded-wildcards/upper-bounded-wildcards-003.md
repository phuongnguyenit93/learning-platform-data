# Đọc phần tử theo giới hạn trên với wildcard `? extends` trong Java Generics

## 1. Mục tiêu của bài học

Trong Java, `? extends UpperBound` là **wildcard có giới hạn trên** (*upper-bounded wildcard*). Nó diễn đạt rằng phần tử của một kiểu generic có thể thuộc **một kiểu cụ thể chưa biết**, nhưng kiểu cụ thể ấy chắc chắn là `UpperBound` hoặc một subtype của `UpperBound`.

Nhờ bảo đảm đó, ta có thể **đọc phần tử dưới dạng `UpperBound`** mà không cần cast không kiểm tra:

~~~java
List<Integer> integers = List.of(10, 20);
List<? extends Number> numbers = integers;

Number first = numbers.get(0); // Hợp lệ: Integer là Number.
~~~

Kết quả `get(0)` có thể là `Integer`, `Double` hoặc một subtype khác của `Number`; compiler chỉ cam kết nó **gán an toàn cho `Number`**. Đây là cơ chế trọng tâm của bài học. Ta sẽ phân biệt giữa “biết giới hạn trên” và “biết chính xác loại phần tử”, hiểu vì sao đọc được nhưng không tự do ghi thêm, rồi dùng nguyên tắc đó để viết API Java 17+.

## 2. Cách hiểu chính xác `List<? extends Number>`

Xét một nguồn có kiểu phần tử cụ thể nhưng được nhìn qua wildcard:

~~~java
List<Integer> integers = List.of(1, 2, 3);
List<? extends Number> source = integers;
Number first = source.get(0);
~~~

Compiler coi element type của `source` là một kiểu **chưa biết** (wildcard capture) nhưng có upper bound `Number`. Vì thế `get(0)` đọc được thành `Number`, còn không được mặc nhiên gán vào `Integer`: một lời gọi khác có thể nhận `List<Double>`.

Ở bài **đọc theo giới hạn trên**, trọng tâm không chỉ là xác định subtype nào được chấp nhận, mà còn là **những hành vi của `Number` có thể gọi an toàn sau khi lấy phần tử**, cách duyệt, ranh giới null/heap pollution và nhu cầu giữ subtype bằng generic method.

## 3. Compiler cho phép đọc dưới kiểu nào?

| Kiểu danh sách được khai báo | Kiểu an toàn khi đọc bằng `get(...)` | Ghi chú |
| --- | --- | --- |
| `List<Integer>` | `Integer` | Type argument cụ thể đã biết. |
| `List<Number>` | `Number` | Có thể chứa nhiều subtype của `Number`. |
| `List<? extends Number>` | `Number` | Phần tử thuộc một subtype *chưa biết* của `Number`. |
| `List<? extends Integer>` | `Integer` | Kiểu đọc an toàn là `Integer`; bản thân `Integer` là final. |
| `List<? extends CharSequence>` | `CharSequence` | Có thể gọi các phương thức của `CharSequence`, ví dụ `length()`. |
| `List<?>` | `Object` | Wildcard không giới hạn tương ứng với giới hạn trên `Object`. |

Mã minh họa các phép đọc hợp lệ:

~~~java
List<? extends Number> numbers = List.of(3, 5);
Number number = numbers.get(0);
double value = numbers.get(1).doubleValue(); // Method của Number.

List<? extends CharSequence> names = List.of("Java", "Generics");
CharSequence name = names.get(0);
int length = names.get(1).length();

List<?> unknown = List.of("A", "B");
Object element = unknown.get(0);
~~~

Nhưng không thể tự ý gán kết quả từ giới hạn rộng sang subtype cụ thể:

~~~java
List<? extends Number> numbers = List.of(3, 5);

// KHÔNG biên dịch: Number không thể bảo đảm là Integer.
Integer integer = numbers.get(0);

// KHÔNG biên dịch: kết quả đọc từ List<?> chỉ được bảo đảm là Object.
String string = List.of("A").stream().findFirst().orElse("");
// Dòng trên độc lập là hợp lệ vì Stream<String>, KHÔNG phải ví dụ của List<?>.
~~~

Ở tình huống thứ hai, ví dụ sai chính xác cần xét là:

~~~java
List<?> unknown = List.of("A", "B");
String value = unknown.get(0); // KHÔNG biên dịch: cần Object hoặc kiểm tra kiểu.
~~~

Không nên sử dụng `(Integer) numbers.get(0)` chỉ vì mình nhìn thấy danh sách ban đầu được tạo từ `Integer` ở một nơi nào đó. Nếu API chỉ hứa `Number`, hãy thiết kế người dùng API phụ thuộc vào `Number`, hoặc dùng cấu trúc type parameter để giữ thông tin `Integer` khi thực sự cần.

## 4. Những phép toán đọc an toàn trên `? extends`

### 4.1. Gọi phương thức của giới hạn trên

~~~java
static double sum(List<? extends Number> numbers) {
    double result = 0.0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
~~~

Đoạn trên là một **phương thức minh họa cần đặt trong lớp Java và import `java.util.List`**. Nó nhận được nhiều danh sách cụ thể:

~~~java
sum(List.of(1, 2, 3));   // List<Integer> -> 6.0
sum(List.of(1.5, 2.5)); // List<Double>  -> 4.0
~~~

Ta dùng `doubleValue()` bởi vì `Number` công bố phương thức ấy. Đây là phép chuyển đổi giá trị số có thể mất độ chính xác với kiểu như `BigDecimal`; trong ứng dụng tiền tệ, hãy sử dụng kiểu nghiệp vụ cụ thể và phép tính chính xác thay vì giả định tổng bằng `double` luôn phù hợp.

### 4.2. `get`, for-each, iterator và stream đều tôn trọng giới hạn trên

~~~java
List<? extends Number> numbers = List.of(1, 2, 3);

Number a = numbers.get(0);
for (Number n : numbers) {
    System.out.println(n.intValue());
}
java.util.Iterator<? extends Number> it = numbers.iterator();
Number b = it.next();

double total = numbers.stream()
        .mapToDouble(Number::doubleValue)
        .sum();
~~~

Từng cách truy xuất đều dựa trên **cùng một bảo đảm**: phần tử đọc được là subtype của `Number`. `mapToDouble(Number::doubleValue)` hoạt động vì mỗi phần tử có thể được nhìn như một `Number`.

Không cần chèn `(Number)` thủ công. Compiler đã kiểm tra tính tương thích tĩnh cho toàn bộ thao tác trong phạm vi kiểu generic hợp lệ.

### 4.3. Dùng giới hạn trên là interface

Không chỉ class như `Number`, giới hạn trên có thể là một interface:

~~~java
static void printLengths(List<? extends CharSequence> values) {
    for (CharSequence text : values) {
        System.out.println(text.length());
    }
}
~~~

Hàm nhận `List<String>` hoặc danh sách các kiểu khác thực thi `CharSequence` (chẳng hạn `StringBuilder`), rồi chỉ sử dụng API do `CharSequence` bảo đảm.

## 5. Vì sao đọc được nhưng không thêm phần tử tùy ý?

Chữ ký `List<? extends Number>` **cho phép lấy giá trị theo upper bound**, nhưng không công bố element type chính xác để chèn một `Integer` hoặc `Double` mới:

~~~java
List<Double> actual = new ArrayList<>(List.of(1.5));
List<? extends Number> numbers = actual;
Number first = numbers.get(0);
// numbers.add(5); // Lỗi biên dịch: kiểu ẩn có thể không nhận Integer.
~~~

Một `Number` đọc ra là hợp lệ vì mọi subtype của `Number` đều có thể sử dụng như `Number`. Chiều ngược lại không đúng: một `Integer` không bảo đảm thuộc *mọi* subtype ẩn.

Ngoại lệ `add(null)` chỉ là sự cho phép ở **tầng type checking**, không bảo đảm collection hỗ trợ mutation hoặc null. `clear()` vẫn có thể biên dịch. Khi cần chứng minh quy tắc không thêm `T`, capture helper và chiến lược chuyển sang `? super T`, hãy xem bài chuyên đề liền sau; bài hiện tại tập trung vào phép **đọc an toàn và các giới hạn khi sử dụng giá trị đọc**.

## 6. Ví dụ Java 17+ hoàn chỉnh: đọc từ nhiều kiểu Number

Tạo tệp **ReadUpperBoundDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReadUpperBoundDemo {
    static double total(List<? extends Number> numbers) {
        double sum = 0;
        for (Number number : numbers) {
            sum += number.doubleValue();
        }
        return sum;
    }

    static <T extends Number> T firstTyped(List<? extends T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4, 6));
        List<Double> doubles = List.of(1.5, 2.5);

        List<? extends Number> view = integers;
        Number first = view.get(0);
        System.out.println("first: " + first);
        System.out.println("int total: " + total(integers));
        System.out.println("double total: " + total(doubles));

        Integer typed = firstTyped(integers);
        System.out.println("typed first: " + typed);

        List<? extends Integer> narrow = integers;
        Integer exact = narrow.get(1);
        System.out.println("narrow: " + exact);

        List<? extends Number> mutableView = integers;
        mutableView.remove(1);
        System.out.println("after remove: " + integers);

        List<? extends Number> nullable = new ArrayList<Integer>();
        nullable.add(null);
        System.out.println("null entry: " + nullable.get(0));

        List<?> unknown = List.of("hello");
        Object value = unknown.get(0);
        System.out.println("unknown: " + value);
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac --release 17 -Xlint:all ReadUpperBoundDemo.java
java ReadUpperBoundDemo
~~~

**Stdout chính xác** (mẫu đã biên dịch bằng `javac --release 17 -Xlint:all`, không phát sinh unchecked warning):

~~~text
first: 2
int total: 12.0
double total: 4.0
typed first: 2
narrow: 4
after remove: [2, 6]
null entry: null
unknown: hello
~~~

Giải thích từng phần:

1. `List<Integer>` gán được cho `List<? extends Number>`; giá trị `get(0)` đọc an toàn dưới dạng `Number`.
2. `total` nhận cả `List<Integer>` và `List<Double>`; chỉ dùng phương thức của `Number`.
3. `firstTyped` giữ liên hệ kiểu `T` ở giá trị trả về nên `Integer typed = firstTyped(integers)` không cần cast.
4. `List<? extends Integer>` cho phép đọc như `Integer` vì đó là giới hạn trên chính xác hơn.
5. `remove(1)` làm biến đổi **danh sách gốc** thông qua một reference wildcard; giới hạn trên không biến list thành immutable.
6. `add(null)` được compiler chấp nhận với một `ArrayList` mutable, nhưng người dùng API phải xử lý trường hợp phần tử đọc ra là `null`.
7. `List<?>` cho phép đọc tối thiểu như `Object`.

## 7. Làm thế nào để giữ được kiểu phần tử cụ thể khi cần?

Nếu mã chỉ khai báo:

~~~java
List<? extends Number> view = List.of(1, 2, 3);
Number first = view.get(0);  // Bảo đảm Number.
~~~

Thì việc giá trị runtime tình cờ là `Integer` **không nâng hợp đồng của `view` thành `List<Integer>`**. Dòng sau là lỗi biên dịch:

~~~java
Integer exact = view.get(0); // KHÔNG hợp lệ nếu không cast.
~~~

Nếu API của bạn thực sự cần giữ mối liên hệ giữa kiểu đầu vào và kiểu trả về, hãy khai báo **type parameter có tên**:

~~~java
static <T extends Number> T firstTyped(List<? extends T> values) {
    return values.get(0);
}

List<Integer> ints = List.of(10, 20);
Integer firstInteger = firstTyped(ints); // T suy luận phù hợp với Integer.
~~~

Khi gọi `firstTyped` bằng một biến đã bị mở rộng thành `List<? extends Number>`, compiler vẫn không được phép hứa một `Integer` cụ thể. Type parameter chỉ giữ lại **những liên hệ kiểu mà đầu vào thật sự còn biểu diễn được**; nó không phục hồi bằng chứng đã bị mất.

Nếu thực sự cần xử lý riêng một subtype, có thể dùng kiểm tra runtime rõ ràng:

~~~java
Number item = view.get(0);
if (item instanceof Integer integer) {
    System.out.println(integer + 1);
}
~~~

Đây là nhánh xử lý theo kiểu thực tế của **một phần tử**. Nó không chứng minh rằng *toàn bộ* danh sách có kiểu `List<Integer>`, vì mã có thể dùng collection chứa phần tử không đồng nhất hoặc đã chịu tác động từ raw/unchecked API.

## 8. Trường hợp giới hạn trên là `Object` và so sánh với `? super`

`List<?>` là dạng ngắn của `List<? extends Object>` xét về ý nghĩa wildcard không giới hạn. Do đó `get` trên `List<?>` được xem là `Object`:

~~~java
List<?> anything = List.of("A", 1, 2.5);
Object first = anything.get(0);
~~~

Khi API chỉ muốn in mọi phần tử hoặc kiểm tra `equals`/`toString`, `List<?>` có thể là lựa chọn rõ ràng nhất. Không cần tự ràng buộc `Number` nếu thuật toán chẳng dùng đặc điểm nào của `Number`.

Trong khi đó, với **wildcard giới hạn dưới**:

~~~java
List<? super Integer> sink = new ArrayList<Number>();
sink.add(42);             // Hợp lệ.
Object value = sink.get(0); // Chỉ bảo đảm Object.
~~~

`? super Integer` mô tả một **kiểu bao chứa Integer** chưa biết (có thể là `Integer`, `Number` hoặc `Object`). Việc đọc từ đó chỉ bảo đảm `Object`. Bảng so sánh nhanh:

| Kiểu view | Đọc an toàn thành | Thêm `Integer` |
| --- | --- | --- |
| `List<Integer>` | `Integer` | Có, nếu list hỗ trợ sửa. |
| `List<Number>` | `Number` | Có, nếu list hỗ trợ sửa. |
| `List<? extends Number>` | `Number` | Không, vì subtype cụ thể chưa biết. |
| `List<? super Integer>` | `Object` | Có, nếu list hỗ trợ sửa. |
| `List<?>` | `Object` | Không, trừ `null`. |

PECS là hướng dẫn chọn **tham số API**: đầu vào chủ yếu cung cấp giá trị để đọc → `extends`; đầu vào chủ yếu nhận giá trị để ghi → `super`. Không nên hiểu PECS là quy tắc cấm đọc từ `super` hay cấm tất cả thao tác biến đổi trên `extends`.

## 9. Khi nào đọc phần tử có thể gặp lỗi?

### 9.1. Danh sách rỗng hoặc chỉ số không hợp lệ

`List<? extends Number> numbers = List.of();` vẫn hoàn toàn hợp lệ. Nhưng `numbers.get(0)` ném `IndexOutOfBoundsException`. Wildcard không bảo đảm một collection có phần tử.

Hãy duyệt for-each, kiểm tra `isEmpty()` hoặc kiểm soát chỉ số đúng nếu cần đọc vị trí cố định.

### 9.2. Giá trị `null`

Một collection cho phép `null` có thể chứa `null` dù khai báo kiểu `List<? extends Number>`:

~~~java
List<? extends Number> numbers = new ArrayList<Integer>();
numbers.add(null);
Number n = numbers.get(0); // n == null
// n.doubleValue();          // Ném NullPointerException nếu bỏ comment.
~~~

An toàn về **kiểu** không đồng nghĩa **non-null**. Chỉ gọi phương thức trên giá trị sau khi hiểu rõ hợp đồng nullability của API.

### 9.3. Heap pollution từ mã raw/unchecked

Một chương trình có thể phá bảo đảm tĩnh của generics bằng raw type hoặc unchecked conversion:

~~~java
List raw = new ArrayList<String>();
raw.add("not-a-number");               // Raw API: cảnh báo unchecked.
List<? extends Number> claimed = raw;  // Unchecked conversion.
Number n = claimed.get(0);             // Có thể ClassCastException ở runtime.
~~~

Đây là **đoạn phản ví dụ có chủ đích**, không phải mẫu nên đưa vào sản xuất. Khi đọc như `Number`, compiler/JVM có thể phải kiểm tra kiểu runtime do type erasure. Nếu raw list thật sự chứa `String`, kiểm tra đó sẽ thất bại. Việc này không có nghĩa `? extends Number` mất an toàn: lỗi đến từ chỗ trước đó đã bỏ qua kiểm tra generic bằng raw/unchecked code.

### 9.4. Giới hạn trên không bảo đảm mọi phương thức của subtype

~~~java
List<? extends Number> values = List.of(1, 2);
Number a = values.get(0);

// KHÔNG biên dịch vì Number không có phương thức compareTo(Integer).
int result = values.get(0).compareTo(2);
~~~

`Integer` có các phương thức riêng, nhưng kiểu chung `Number` không hứa toàn bộ chúng. Chỉ dựa vào API của giới hạn trên, hoặc dùng kiểu generic chặt hơn khi thuật toán đòi quan hệ bổ sung.

## 10. Thiết kế phương thức nhận dữ liệu: nên dùng chữ ký nào?

| Nhu cầu | Chữ ký phù hợp | Lý do |
| --- | --- | --- |
| Tính tổng các số, chỉ đọc | `double total(List<? extends Number> input)` | Nhận nhiều danh sách số khác nhau, chỉ cần phương thức từ `Number`. |
| Lấy một số và giữ kiểu subtype ở nơi gọi | `<T extends Number> T first(List<? extends T> input)` | Ràng buộc kết quả vào `T` của caller. |
| Duyệt mọi giá trị không phụ thuộc kiểu | `void print(List<?> input)` | `Object` đã đủ. |
| Ghi các giá trị `Integer` vào collection | `void fill(List<? super Integer> target)` | Có thể chèn Integer, không cần đọc dưới dạng Number. |
| Phải bổ sung `Integer` và `Double` vào cùng list | `void appendBoth(List<Number> target)` (hoặc API đích phù hợp) | Cần một contract chấp nhận các Number, không thể ghi tùy ý qua `? extends`. |

Nếu có một `List<Integer>` mà cần tạo **danh sách mới** cho phép chèn nhiều subtype `Number`, hãy tạo bản sao:

~~~java
List<Integer> ints = List.of(1, 2);
List<Number> mixed = new ArrayList<>(ints);
mixed.add(2.5);
~~~

Đây là **copy constructor an toàn**, không phải cast hoặc thay đổi quan hệ subtyping. `List<Integer>` nguồn vẫn là danh sách riêng.

## 11. Những nhầm lẫn phổ biến và cách tự kiểm tra

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “`? extends Number` chỉ chứa `Number`, không nhận `Integer`.” | Nó được thiết kế để nhận cả `Number` và các subtype như `Integer`, `Double`. |
| “Đã gán `List<Integer>` vào `List<? extends Number>` thì `get` trả về `Integer` theo biến view.” | Biến view chỉ bảo đảm kết quả đọc có thể dùng như `Number`. |
| “Có thể thêm bất kỳ `Number` vì bound là `Number`.” | Không: compiler không biết subtype cụ thể của wildcard. |
| “`? extends` tạo danh sách chỉ đọc/bất biến.” | Không: vẫn có thể `remove`/`clear` nếu implementation hỗ trợ; `add(null)` cũng hợp lệ về kiểu. |
| “Nếu đọc được `Number` thì chắc chắn không có `null`.” | Phần tử có thể là `null` nếu collection cho phép. |
| “Cần cast `(Number) numbers.get(i)` để an toàn.” | Cast thủ công không cần thiết; type system đã bảo đảm upper bound trong mã generic an toàn. |
| “`List<?>` và `List<? extends Number>` đọc được cùng kiểu.” | `List<?>` chỉ bảo đảm `Object`; `List<? extends Number>` bảo đảm `Number`. |

**Câu hỏi ôn tập**

1. Tại sao `List<Double>` truyền được vào `total(List<? extends Number>)`? **Vì `Double <: Number` và wildcard cho phép type argument thuộc subtype của `Number`.**
2. Tại sao `Number n = values.get(0)` hợp lệ với `values` kiểu `List<? extends Number>`? **Vì kiểu capture của phần tử chắc chắn là subtype của `Number`.**
3. Tại sao không được `values.add(10)`? **Vì kiểu phần tử cụ thể có thể là `Double` hoặc subtype khác không nhận `Integer`.**
4. `List<? extends Number>` có phải danh sách immutable? **Không.** Wildcard chỉ hạn chế những thao tác ghi bị mất an toàn về kiểu.
5. Khi dùng `List<?>`, kiểu an toàn để nhận `get(0)` là gì? **`Object`.**
6. Nếu muốn kết quả `get` giữ type `Integer` khi caller truyền `List<Integer>`, nên làm gì? **Dùng chữ ký có tham số kiểu `<T extends Number> T firstTyped(List<? extends T>)` hoặc dùng thẳng `List<Integer>` khi API chuyên biệt.**

## 12. Tài liệu chuẩn

- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): ý nghĩa upper-bounded wildcard và containment.
- [JLS Java SE 17 §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): quan hệ subtype với parameterized types.
- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): cách compiler xử lý kiểu chưa biết do wildcard biểu diễn.
- [Oracle Java Tutorials — Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html): mô hình dùng wildcard `extends` để xử lý các danh sách con của một kiểu chung.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `get`, `add`, `remove`, `clear` và ngoại lệ khi truy cập/sửa danh sách.
