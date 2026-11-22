# Giá trị null, giới hạn thao tác trên T và kiểu Object mặc định trong Java Generics

## 1. Mục tiêu

Khi viết **class Box<T>** hoặc **static <T> T identity(T value)**, ta chưa chỉ rõ T là String, Integer, Number hay kiểu nào khác. Đây là lý do Java chỉ cho phép một số thao tác chắc chắn hợp lệ với mọi kiểu mà T có thể đại diện.

Ba câu hỏi nền tảng của bài học:

1. **T có thể nhận null không?** Có. Các type arguments của generics Java thông thường là kiểu tham chiếu, và null có thể được gán cho biến kiểu tham chiếu tương ứng; không có cam kết “không null” mặc định.
2. **Với T không có ràng buộc tường minh, được gọi những phương thức nào?** Chủ yếu là các phương thức khả dụng từ Object, vì T có cận trên ngầm định là Object. Không thể giả định T có API của String, Number hoặc một interface riêng.
3. **T có phải chính là Object không?** Không. T là một **biến kiểu** (*type variable*) giữ quan hệ kiểu giữa nhiều vị trí trong khai báo. Cận trên Object cho biết các thao tác tối thiểu được phép; nó không thay T bằng Object trong hệ thống kiểm tra kiểu ở mã nguồn.

Bài dùng Java 17+; các chương trình có nhãn tệp và lệnh chạy là ví dụ độc lập, còn đoạn được ghi “minh họa lỗi biên dịch” cố ý không biên dịch.

## 2. T không ràng buộc có cận trên Object mặc định

Xét khai báo:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Trong **class Box<T>**, ký hiệu T khai báo một type parameter **không có bound tường minh** (*unbounded type parameter*). Về cận trên, Java hiểu tương đương với:

~~~java
class Box<T extends Object> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Ở đây **extends Object** là cận trên tường minh; viết ra cũng không làm T trở thành Object. Java cho phép đối số kiểu thuộc một kiểu tham chiếu bất kỳ tương thích với cận, ví dụ String, Integer, StringBuilder, một interface type, một array type hoặc một parameterized type. **Box<String>** và **Box<Integer>** là hai cách dùng hợp lệ của cùng khai báo.

Ví dụ sử dụng trong một phương thức:

~~~java
Box<String> text = new Box<>("hello");
Box<Integer> count = new Box<>(42);
Box<int[]> numbers = new Box<>(new int[] { 1, 2, 3 });

String s = text.get();
Integer n = count.get();
int[] a = numbers.get();
~~~

Ngược lại, **Box<int>** không hợp lệ: int là primitive type, không thể trực tiếp làm type argument của generic class. Dùng kiểu wrapper **Integer** hoặc một kiểu tham chiếu khác.

**Cận trên Object mặc định** có hai ý nghĩa cần tách:

- **Ở nguồn Java:** compiler chỉ có thể tin rằng mọi giá trị T đều tương thích với Object và có những API bảo đảm bởi cận trên đó. Trong một cách sử dụng cụ thể Box<String>, compiler vẫn biết get() có kiểu tĩnh String.
- **Trong việc hiện thực generics:** unbounded T thường bị *type erasure* thành Object trong bytecode. Việc xóa kiểu phục vụ khả năng tương thích runtime; nó không xóa kiểm tra kiểu của source code trước khi biên dịch.

Một generic declaration không tự cung cấp hành vi chuyên biệt cho T. Muốn compiler cho phép gọi một phương thức của Number hoặc CharSequence, phải khai báo bound thích hợp hoặc cung cấp một thao tác bên ngoài cho T.

## 3. Null với type parameter T

Trong Java, **null** là giá trị tham chiếu đặc biệt biểu thị không trỏ đến đối tượng. Null có thể được chuyển đổi sang một kiểu tham chiếu, trong đó có kiểu biểu diễn bởi T trong generics thông thường.

~~~java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }

    void clear() {
        value = null; // Hợp lệ với T là kiểu tham chiếu
    }

    boolean isNull() {
        return value == null;
    }
}
~~~

Sau đây đều có thể biên dịch khi class Holder đã được khai báo:

~~~java
Holder<String> name = new Holder<>(null);
Holder<Integer> size = new Holder<>(null);
Holder<Number> amount = new Holder<>(null);

String text = name.value;   // text nhận null
Integer number = size.value; // number nhận null
~~~

Dù type argument là Integer, giá trị **null** không phải là một số nguyên 0. Integer là wrapper/reference type, và mọi tham chiếu Integer vẫn có thể null.

Giới hạn bằng **extends** không mặc nhiên loại trừ null:

~~~java
class NumberHolder<T extends Number> {
    T value;

    NumberHolder(T value) {
        this.value = value;
    }
}

// Trong thân phương thức:
// NumberHolder<Integer> n = new NumberHolder<>(null); // Hợp lệ
~~~

Bound Number chỉ giới hạn **kiểu** mà T được phép biểu diễn. Nó không cam kết **giá trị thực tế** luôn tồn tại. Tương tự, **<T extends Comparable<T>>**, **<T extends CharSequence>** hay **<T extends Runnable>** không tự tạo ra một ràng buộc non-null.

### Truyền null vào generic method

Một generic method có thể nhận null làm đối số:

~~~java
static <T> T echo(T input) {
    return input;
}
~~~

Lời gọi **String result = echo(null)** có thể hợp lệ; compiler dùng ngữ cảnh kiểu đích để suy luận T phù hợp và kết quả nhận được là null. Cũng có thể chỉ rõ kiểu để diễn đạt ý định:

~~~java
String name = GenericNullDemo.<String>echo(null);
~~~

Dòng trên minh họa lời gọi tường minh khi **echo** là static method có thể truy cập trong class tên GenericNullDemo. Dấu **<String>** ở lời gọi là method type argument; **<T>** trước kiểu trả về trong khai báo là type parameter.

Không nên giả định null tự cho biết một kiểu cụ thể duy nhất. Trong biểu thức có overload hoặc type inference phức tạp, null có thể khiến việc chọn phương thức trở nên mơ hồ hoặc khiến compiler cần thông tin kiểu bổ sung. Khi đó, kiểu biến đích, type witness hoặc cast có thể giúp làm rõ; giải pháp tùy chữ ký đang dùng.

## 4. Kiểm tra null an toàn trên T

Do T là kiểu tham chiếu, ta có thể so sánh với null bằng **==** hoặc **!=**:

~~~java
static <T> boolean missing(T value) {
    return value == null;
}

static <T> boolean present(T value) {
    return value != null;
}
~~~

Hai phép so sánh này không cần bound. Khi biến T không null, **==** giữa hai tham chiếu kiểm tra chúng có trỏ đến cùng đối tượng hay không; nó **không** tương đương với so sánh nội dung bằng equals.

Kiểu sử dụng phổ biến khi cần đọc thuộc tính của T:

~~~java
static <T> String describe(T value) {
    if (value == null) {
        return "(không có giá trị)";
    }
    return value.getClass().getSimpleName() + ": " + value;
}
~~~

Nhánh if tránh gọi **getClass()** trên null. Biểu thức nối String với value dùng chuyển đổi sang chuỗi theo ngữ nghĩa string concatenation; không chứng minh T có bất kỳ phép toán số học nào.

Nếu cần so sánh nội dung và cả hai giá trị có thể null, dùng **Objects.equals(a, b)**:

~~~java
import java.util.Objects;

class Equality {
    static <T> boolean same(T left, T right) {
        return Objects.equals(left, right);
    }
}
~~~

**Objects.equals** trả true khi cả hai đều null, false khi chỉ một bên null, còn khi cả hai khác null thì gọi equals theo hợp đồng của đối tượng bên trái. Nó tránh NullPointerException do trực tiếp gọi **left.equals(right)** khi left có thể null.

Lưu ý rằng equals(Object) không có chữ ký generic bảo đảm hai đối số thuộc cùng kiểu; type parameter T trong ví dụ same thể hiện mối quan hệ của hai tham số ở mức suy luận của compiler, nhưng Object.equals(Object) vẫn chấp nhận bất kỳ Object nào.

### Null khác với “không có phần tử”

Một generic container tự thiết kế có thể dùng null như tín hiệu “chưa có dữ liệu”, nhưng đây là **quy ước API**, không phải quy tắc của generics.

~~~java
final class Slot<T> {
    private T item;

    void put(T value) {
        item = value;
    }

    boolean hasNonNullValue() {
        return item != null;
    }
}
~~~

Nếu API cần phân biệt **“chưa được gán”** với **“đã gán giá trị null”**, chỉ nhìn item == null là không đủ. Phải thêm cờ trạng thái hoặc dùng một mô hình biểu diễn có/không có giá trị phù hợp. Ví dụ:

~~~java
final class NullableSlot<T> {
    private boolean assigned;
    private T value;

    void put(T value) {
        this.value = value;
        this.assigned = true;
    }

    boolean isAssigned() {
        return assigned;
    }

    T get() {
        if (!assigned) {
            throw new IllegalStateException("Chưa gán");
        }
        return value;
    }
}
~~~

Một NullableSlot đã gọi put(null) vẫn có isAssigned() == true và get() trả null; nó khác trạng thái chưa từng gọi put. Đừng nhầm khả năng lưu null của generic type với chính sách biểu diễn dữ liệu của một container.

## 5. Những thao tác Object mặc định cho T

Với **T không bound tường minh**, các thành viên public của Object có thể được gọi qua biến T nếu thỏa điều kiện truy cập. Những phương thức thường hữu ích nhất là **toString()**, **equals(Object)**, **hashCode()** và **getClass()**.

~~~java
static <T> String asText(T value) {
    return value.toString();
}

static <T> boolean matches(T value, Object other) {
    return value.equals(other);
}

static <T> int hash(T value) {
    return value.hashCode();
}

static <T> Class<?> runtimeClass(T value) {
    return value.getClass();
}
~~~

Những phương thức này đều **có thể biên dịch** với T không bound. Tuy nhiên, nếu truyền null thì từng phương thức trên sẽ ném **NullPointerException** tại thời điểm gọi. “Phương thức được phép gọi trên T” là vấn đề **kiểu tĩnh**; “receiver có null không” là vấn đề **giá trị runtime**.

Object còn có các phương thức public liên quan tới đồng bộ như wait() và notify(), nhưng đây không phải API nên dùng chỉ vì T có cận Object. Các phương thức protected như clone() không tự trở thành callable công khai ở mọi ngữ cảnh; giới hạn truy cập Java vẫn áp dụng.

Bảng thao tác mẫu:

| Biểu thức trong nơi có T không bound | Biên dịch? | Điều kiện/ý nghĩa |
| --- | --- | --- |
| value == null | Có | Kiểm tra tham chiếu |
| value != null | Có | Kiểm tra tham chiếu |
| Object o = value | Có | T có cận trên Object |
| String s = value.toString() | Có | Object có toString(); null gây NPE |
| int h = value.hashCode() | Có | Object có hashCode(); null gây NPE |
| boolean b = value.equals(other) | Có | Object có equals(Object); null gây NPE |
| Class<?> c = value.getClass() | Có | Object có getClass(); null gây NPE |
| value.length() | Không | Object không khai báo length() |
| value.intValue() | Không | Object không khai báo intValue() |
| value.compareTo(other) | Không | Object không khai báo compareTo() |
| value + 1 | Không với phép cộng số tổng quát | Không biết T là kiểu số |
| new T() | Không | Không được khởi tạo trực tiếp type variable |
| T.class | Không | Type variable không dùng trong class literal |
| new T[3] | Không | Generic array creation |
| value instanceof T | Không | T thông thường không reifiable ở runtime |

**getClass()** trả về class thật của đối tượng tại runtime (khi khác null), không phải thông tin chắc chắn về type argument T của cách khai báo biến. Ví dụ khi một T thực tế chứa ArrayList<String>, getClass() trả class ArrayList; không thể suy ra từ đó riêng type argument String đã dùng tại nguồn.

### toString và String.valueOf khác nhau khi null

**value.toString()** sẽ ném NullPointerException nếu value là null. Trong khi đó **String.valueOf(value)** là lựa chọn null-safe: nhận một tham chiếu Object và trả chuỗi **"null"** khi đối số null.

~~~java
static <T> String safeToText(T value) {
    return String.valueOf(value);
}
~~~

Nếu cần nhãn riêng khi vắng dữ liệu, hãy kiểm tra:

~~~java
static <T> String display(T value) {
    return value == null ? "(trống)" : value.toString();
}
~~~

Đừng lạm dụng toString() cho logic nghiệp vụ hay phép so sánh: nó chủ yếu phục vụ biểu diễn chuỗi và có thể được override với định dạng không ổn định.

## 6. Vì sao compiler không cho gọi API của String hoặc Number trên T?

Xem mã cố ý lỗi:

~~~java
// Minh họa lỗi biên dịch; không lưu thành một chương trình để chạy.
class InvalidOperations<T> {
    int size(T value) {
        return value.length();    // Lỗi: T có thể không phải CharSequence
    }

    double convert(T value) {
        return value.doubleValue(); // Lỗi: T có thể không phải Number
    }

    T plus(T a, T b) {
        return a + b;             // Lỗi: không có phép cộng số học tổng quát cho T
    }
}
~~~

Ngay cả khi **chỉ định dùng InvalidOperations<String>**, class phải tự hợp lệ với **mọi type argument** đáp ứng bound của T. Không thể biên dịch một thân generic class chỉ dựa vào ý định sẽ dùng với một subtype duy nhất.

Tương tự, trình biên dịch không suy ra phương thức từ cách đặt tên T. **T** không phải viết tắt của “Text”, **N** không tự mang Number, và **V** không cho phép phép cộng. Chỉ có khai báo kiểu/bound và các phương thức được bảo đảm bởi chúng mới quyết định thao tác hợp lệ.

Một trường hợp đặc biệt cần đọc đúng: phép nối chuỗi **value + "!"** có thể biên dịch với T vì đây là **string concatenation** có toán hạng String, không phải phép cộng số học trên T. Nó không chứng minh value hỗ trợ toán tử cộng.

### Cách 1: thêm bound phù hợp

Muốn gọi **length()** trên một chuỗi ký tự tổng quát:

~~~java
static <T extends CharSequence> int lengthOf(T value) {
    return value.length();
}
~~~

CharSequence khai báo length(), nên compiler biết T có phương thức đó. Chẳng hạn String và StringBuilder đều implement CharSequence.

Muốn đọc biểu diễn số:

~~~java
static <T extends Number> double doubled(T value) {
    return value.doubleValue() * 2.0;
}
~~~

Number cung cấp doubleValue(); lấy về double rồi nhân 2.0 là hợp lệ. Nhưng **value + value** vẫn không phải toán tử generic hợp lệ: bound Number không biến T thành primitive type và không định nghĩa overload toán tử +.

Muốn so sánh theo thứ tự với cùng kiểu T:

~~~java
static <T extends Comparable<T>> T max(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

T phải implement Comparable<T>, vì vậy compiler cho phép gọi compareTo(T). **max("a", "z")** hợp lệ với String, còn một class không implement Comparable phù hợp sẽ không thể làm type argument.

### Cách 2: đưa hành vi vào như một tham số

Không phải kiểu nào cũng có thứ tự “tự nhiên”. Nếu không muốn ràng buộc T implement Comparable, hãy nhận **Comparator<? super T>**:

~~~java
static <T> T maxBy(T left, T right,
                   java.util.Comparator<? super T> comparator) {
    return comparator.compare(left, right) >= 0 ? left : right;
}
~~~

Comparator được truyền vào cung cấp hành vi so sánh; bản thân T vẫn không bound. Đây là một cách thiết kế generic API thường linh hoạt hơn khi cùng một kiểu có nhiều tiêu chí so sánh (độ dài, tên, thứ tự ưu tiên).

Cũng có thể nhận **Function<T, R>**, **Predicate<T>**, **Supplier<T>**, hoặc interface do chính bạn định nghĩa để cung cấp những thao tác mà Object không có. Sự lựa chọn giữa bound và truyền strategy phụ thuộc quan hệ thật của API.

### Cách 3: nhiều bound khi cần kết hợp API

~~~java
static <T extends Number & Comparable<T>> T largerNumber(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
~~~

T phải là subtype của Number **và** implement Comparable<T>. Number là class bound, đứng trước interface bound. Trong thân có thể dùng cả **doubleValue()** và **compareTo()**. **&** nối bounds; khác dấu phẩy giữa nhiều type parameters.

Khi cận là interface duy nhất:

~~~java
static <T extends Runnable> void runTask(T action) {
    action.run();
}
~~~

Java vẫn dùng từ khóa **extends**, không dùng **implements** trong khai báo type parameter. Dù có bound, **action có thể null** và lời gọi action.run() sẽ NPE.

## 7. T không phải Object: quan hệ kiểu mạnh hơn Object

Phân biệt ba chữ ký:

~~~java
static Object passObject(Object value) {
    return value;
}

static <T> T passGeneric(T value) {
    return value;
}

static <T> Object passGenericAsObject(T value) {
    return value;
}
~~~

- **passObject(Object)** nhận Object và chỉ bảo đảm kết quả tĩnh Object. Khi gọi với String, code gọi sau thường cần cast nếu muốn nhận String.
- **passGeneric(T)** biểu diễn **cùng một T** ở đầu vào và đầu ra. Khi compiler suy luận T là String, giá trị trả về có kiểu tĩnh String mà không cần cast thủ công tại nơi gọi.
- **passGenericAsObject(T)** dùng T ở tham số nhưng **đã làm mất quan hệ kiểu ở kiểu trả về** vì khai báo Object. Đó thường là thiết kế dư thừa nếu T không đóng góp vào quan hệ nào khác.

Ví dụ ở nơi gọi:

~~~java
// Những phương thức bên trên nằm trong class có thể gọi được.
Object a = passObject("Java");
String b = passGeneric("Java");
// String c = passObject("Java"); // Compile-time error: Object không tự gán cho String
~~~

Đặc biệt, từ cận trên Object **không** được suy ra có thể gán mọi Object vào một biến T bất kỳ:

~~~java
// Minh họa compile-time error:
static <T> T wrong() {
    Object any = new Object();
    return any; // Lỗi: Object không bảo đảm là T
}
~~~

Với một lời gọi mà T được chọn là String, Object tùy ý không nhất thiết là String. Gán **T vào Object** là an toàn; gán **Object vào T** đòi hỏi kiểm tra/chuyển kiểu phù hợp. Nếu buộc dùng cast không kiểm tra từ Object sang T, có thể nhận cảnh báo unchecked và phát sinh lỗi ở runtime. Tránh dùng cast để che lấp sự thiếu vắng quan hệ kiểu.

Một nhầm lẫn tương tự là gọi **List<T>** giống **List<Object>**. Khi T là String, List<String> không phải subtype của List<Object> vì các generic types như List là **invariant** theo đối số kiểu. Dùng **List<?>** hoặc bounded wildcard khi muốn thể hiện linh hoạt nơi sử dụng, thay vì tự ý thay T bằng Object.

## 8. Giá trị null và các phép gọi dẫn đến NullPointerException

Giả sử T là Integer:

~~~java
static <T extends Number> double asDouble(T input) {
    return input.doubleValue();
}
~~~

Gọi **asDouble(null)** vẫn có thể biên dịch nhưng sẽ NPE tại **input.doubleValue()**. Việc thêm extends Number cung cấp API, không kiểm tra giá trị runtime.

Với giá trị wrapper có auto-unboxing, lỗi còn có thể xảy ra ngay cả khi code không trực tiếp gọi phương thức:

~~~java
Integer wrapped = null;
// int primitive = wrapped; // Biên dịch được nhưng runtime NPE khi unboxing
~~~

Tương tự, **Box<Integer>** có thể chứa null; lấy Integer ra rồi gán cho int có thể NPE do unboxing. Không nên đánh đồng “generic type argument là Integer” với “luôn có số nguyên hợp lệ”.

**Một số cách bảo vệ khi sử dụng T:**

- Kiểm tra **if (value == null)** trước khi truy cập thành viên hoặc unboxing.
- Dùng **Objects.requireNonNull(value, "value")** tại ranh giới API nếu contract yêu cầu có giá trị. Hàm này trả lại chính tham chiếu khi không null, còn khi null ném NullPointerException với thông điệp.
- Nếu null là một trạng thái hợp lệ, mô tả rõ contract và dùng điều kiện để xử lý nó. Không nên âm thầm áp dụng quy tắc non-null cho mọi generic API.
- Có thể dùng **Optional<T>** ở ngữ cảnh biểu diễn “có/không có giá trị” phù hợp, nhưng Optional không cho phép chính giá trị bên trong là null. **Optional.ofNullable(value)** biến null thành Optional.empty().
- Nếu yêu cầu null-safety ở thời gian biên dịch, Java 17 chuẩn không tự áp đặt điều đó cho mọi T; có thể dùng các annotation/tool phân tích nullness của dự án và tuân theo hợp đồng của framework, nhưng chúng không phải phép bảo đảm tự động chỉ nhờ cú pháp <T>.

### Hàm trả về T và chính sách non-null

~~~java
static <T> T required(T value) {
    return java.util.Objects.requireNonNull(value, "value");
}

static <T> T orElse(T value, T fallback) {
    if (value != null) {
        return value;
    }
    return java.util.Objects.requireNonNull(fallback, "fallback");
}
~~~

**required** giữ kiểu kết quả T mà đồng thời kiểm tra đầu vào khác null. **orElse** trả value nếu có, nếu không thì trả fallback và yêu cầu fallback khác null. Hai phương thức thể hiện chính sách rõ ràng trong runtime; type parameter T vẫn giữ quan hệ kiểu tĩnh giữa input và output.

Với tham số kiểu không bound, **Objects.requireNonNull** là một công cụ đặc biệt thuận tiện: nó được khai báo dạng generic và giữ nguyên kiểu tĩnh của biểu thức sau kiểm tra, không cần ép kiểu về T.

## 9. Ví dụ chạy độc lập: null, Object và quan hệ kiểu T

Lưu thành **NullAndObjectDemo.java**:

~~~java
import java.util.Objects;

public class NullAndObjectDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }

        boolean isEmpty() {
            return value == null;
        }
    }

    static <T> String describe(T value) {
        if (value == null) {
            return "(null)";
        }
        return value.getClass().getSimpleName() + ":" + value.toString();
    }

    static <T> boolean same(T left, T right) {
        return Objects.equals(left, right);
    }

    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        Box<String> greeting = new Box<>(null);
        System.out.println(greeting.isEmpty());
        System.out.println(describe(greeting.get()));

        greeting.set("Java");
        String message = echo(greeting.get());
        System.out.println(describe(message));

        System.out.println(same("ok", "ok"));
        System.out.println(same(null, "ok"));
        System.out.println(describe(21));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 NullAndObjectDemo.java
java NullAndObjectDemo
~~~

Stdout:

~~~text
true
(null)
String:Java
true
false
Integer:21
~~~

Giải thích:

1. Box<T> không yêu cầu có giá trị ban đầu. Box<String>(null) hợp lệ; isEmpty kiểm tra chính xác **value == null**.
2. describe được gọi với null và trả chuỗi **"(null)"**, tránh getClass()/toString() trên receiver null.
3. Sau set("Java"), echo là generic method trả cùng kiểu T đã nhận, nên compiler cho phép gán kết quả cho String.
4. Các lời gọi same dùng Objects.equals, có thể xử lý null ở một hoặc cả hai phía.
5. Với literal 21, kiểu generic được suy luận phù hợp với Integer do autoboxing; describe nhận một đối tượng Integer, gọi Object.getClass() và Object.toString() (được Integer override), cho kết quả **Integer:21**.

**Tính runnable:** tệp chỉ có một public class trùng tên file; các nested classes và methods đều được khai báo đầy đủ. Stdout không phụ thuộc hashCode hay định dạng ngẫu nhiên.

## 10. Ví dụ chạy độc lập: cần bound để gọi phương thức chuyên biệt

Lưu thành **BoundedOperationsDemo.java**:

~~~java
import java.util.Comparator;

public class BoundedOperationsDemo {
    static <T extends CharSequence> int characters(T value) {
        return value.length();
    }

    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2.0;
    }

    static <T extends Number & Comparable<T>> T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T> T chooseLarger(T first, T second,
                              Comparator<? super T> comparator) {
        return comparator.compare(first, second) >= 0 ? first : second;
    }

    public static void main(String[] args) {
        System.out.println(characters("Java"));
        System.out.println(characters(new StringBuilder("generic")));
        System.out.println(twice(3));
        System.out.println(maximum(5, 9));
        System.out.println(chooseLarger("ant", "tiger",
                Comparator.comparingInt(String::length)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BoundedOperationsDemo.java
java BoundedOperationsDemo
~~~

Stdout:

~~~text
4
7
6.0
9
tiger
~~~

Phân tích:

- **T extends CharSequence** cho phép gọi length() trên cả String và StringBuilder.
- **T extends Number** cho phép gọi doubleValue() và phép nhân trên giá trị double thu được; bản thân T vẫn không dùng được trực tiếp trong phép nhân generic.
- **T extends Number & Comparable<T>** cho phép compareTo; Integer đáp ứng cả hai cận.
- **chooseLarger** không ràng buộc T phải Comparable vì Comparator được đưa vào như một tham số; Comparator so sánh chuỗi theo độ dài và chọn tiger.
- Cả bốn phương thức vẫn có thể gặp NPE nếu nhận null tại nơi gọi phương thức receiver chưa kiểm tra. Trong ví dụ chạy, mọi đối số được sử dụng đều khác null.

## 11. Ví dụ chạy độc lập: bắt buộc có giá trị

Lưu thành **NullPolicyDemo.java**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullPolicyDemo {
    static <T> T requireValue(T value) {
        return Objects.requireNonNull(value, "value");
    }

    static <T> T withFallback(T value, T fallback) {
        return value != null
                ? value
                : Objects.requireNonNull(fallback, "fallback");
    }

    static <T> Optional<T> optionalOf(T value) {
        return Optional.ofNullable(value);
    }

    public static void main(String[] args) {
        System.out.println(requireValue("ready"));
        System.out.println(withFallback(null, "guest"));
        System.out.println(optionalOf(null).isEmpty());
        System.out.println(optionalOf("Java").orElse("other"));

        try {
            requireValue(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NullPolicyDemo.java
java NullPolicyDemo
~~~

Stdout:

~~~text
ready
guest
true
Java
value
~~~

**requireValue** và **withFallback** giữ lại T ở kiểu trả về; Objects.requireNonNull từ chối null thay vì giả định T đã được kiểm tra bởi hệ thống generic. **Optional.ofNullable(null).isEmpty()** trả true, còn Optional.ofNullable("Java") giữ chuỗi "Java". Thông báo exception được xác định rõ trong source qua **Objects.requireNonNull(value, "value")**.

## 12. Type erasure: Object mặc định không có nghĩa runtime biết T

Với generic type không bound, compiler hiện thực nhiều thao tác theo erasure; cận ngầm định Object là một nguyên nhân khiến bytecode thường xử lý tham chiếu kiểu Object. Tuy nhiên, Java compiler cũng chèn cast cần thiết tại các nơi sử dụng có thông tin type arguments.

Ví dụ:

~~~java
class Container<T> {
    T item;

    Container(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}

// Ở nơi gọi:
// Container<String> x = new Container<>("hello");
// String s = x.get();
~~~

Về ý tưởng, compiler kiểm tra ở nguồn rằng get() trả đúng String trong cách sử dụng Container<String>, dù mã sau erasure có thể cần cast về String khi lấy kết quả. Người lập trình không phải thêm cast trong source đúng kiểu.

Không thể dựa vào T để tự khởi tạo đối tượng hoặc tạo mảng của T:

~~~java
// Minh họa lỗi biên dịch, không chạy:
class Factory<T> {
    // T create() { return new T(); } // Lỗi
    // T[] createArray() { return new T[4]; } // Lỗi
    // Class<T> type() { return T.class; } // Lỗi
}
~~~

Nguyên nhân là T không phải một class token cụ thể có thể dùng trực tiếp trong các biểu thức trên ở runtime. Nếu cần tạo T, hãy nhận một factory hoặc Supplier<T>. Nếu cần kiểm tra kiểu runtime, có thể nhận Class<T> từ người gọi khi thiết kế API phù hợp.

Ví dụ hợp lệ với Supplier:

~~~java
import java.util.function.Supplier;

class GenericFactory<T> {
    private final Supplier<? extends T> supplier;

    GenericFactory(Supplier<? extends T> supplier) {
        this.supplier = supplier;
    }

    T create() {
        return supplier.get();
    }
}

// Trong một phương thức:
// GenericFactory<StringBuilder> factory =
//         new GenericFactory<>(StringBuilder::new);
// StringBuilder builder = factory.create();
~~~

Compiler cho phép supplier.get() được dùng làm T vì **? extends T** thể hiện kiểu kết quả có thể gán cho T. Tạo object thực tế là trách nhiệm của Supplier. Một Supplier vẫn có thể trả null nếu hợp đồng của nó cho phép; generics tự nó không cấm.

Một lỗi khác là **value instanceof T**, do kiểu T nhìn chung không có biểu diễn runtime cần thiết để kiểm tra đúng type argument. Thay vào đó, có thể kiểm tra **value instanceof String** trong những ngữ cảnh hợp lệ vì String là class cụ thể; hoặc dùng **Class<T>.isInstance(value)** nếu caller cung cấp Class<T>. Kiểm tra runtime chỉ dựa trên class cũng không thể kiểm tra đầy đủ List<String> hay các type arguments lồng nhau.

## 13. Những lỗi và ngộ nhận thường gặp

### Sai lầm 1: “T mặc định là Object nên bất kỳ Object nào cũng gán được vào T”

~~~java
// Mã minh họa lỗi:
static <T> T badReturn() {
    Object value = "text";
    return value; // Compile-time error
}
~~~

Đúng là **T có thể chuyển thành Object** (T là subtype của bound Object). Chiều ngược lại không được đảm bảo. Một lời gọi có thể yêu cầu T = Integer, trong khi Object đang chứa String.

### Sai lầm 2: “T extends Number thì T không thể null”

~~~java
static <T extends Number> double magnitude(T n) {
    return n.doubleValue();
}
~~~

**magnitude(null)** có thể biên dịch và NPE lúc chạy. Bound kiểm soát kiểu, không xác nhận receiver khác null.

### Sai lầm 3: “T có Object methods nên gọi toString trên null vẫn an toàn”

~~~java
static <T> String unsafeText(T value) {
    return value.toString();
}
~~~

Mã biên dịch, nhưng truyền null gây NPE. Dùng **String.valueOf(value)** hoặc kiểm tra trước tùy mục đích.

### Sai lầm 4: “Có thể gọi phương thức của String vì thường truyền String”

~~~java
class NotAlwaysString<T> {
    // int length(T value) { return value.length(); } // Compile-time error
}
~~~

Không có bound nên value có thể thuộc kiểu không có length(). Cần **<T extends CharSequence>** nếu muốn tính độ dài của CharSequence, hoặc khai báo phương thức nhận String nếu API thật sự chỉ thao tác với String.

### Sai lầm 5: “T có thể cộng trực tiếp như số”

~~~java
class Numeric<T extends Number> {
    // T add(T a, T b) { return a + b; } // Compile-time error
}
~~~

Number không khai báo toán tử + cho T. Phải chuyển sang kiểu số cụ thể hoặc nhận một phép cộng dưới dạng hàm; lưu ý chuyển sang double có thể mất độ chính xác với số lớn.

### Sai lầm 6: “Objects.equals(a, b) và a == b giống nhau”

Hai biểu thức khác semantics: **==** kiểm tra cùng tham chiếu hoặc null; **Objects.equals** kiểm tra bằng equals nếu thích hợp và null-safe. Với những object bằng nội dung nhưng khác instance, Objects.equals có thể trả true còn == trả false.

### Sai lầm 7: “Null và generic có thể thay nhau biểu diễn tính tùy chọn”

Một Slot<T> cho phép null chỉ chứng tỏ có thể lưu null. Nó không cho biết “chưa có dữ liệu” có phải cùng nghĩa với “giá trị được chọn là null” hay không. API phải quy định rõ trạng thái và lỗi/giá trị trả về.

### Sai lầm 8: “Giữ T là đủ để biết chính xác type arguments ở runtime”

Erasure khiến thông tin kiểu thành phần không tồn tại như một class chuyên biệt cho mỗi List<String> hay List<Integer>. Một Object chứa List không cho phép dùng getClass() để xác minh trực tiếp đối số kiểu String. Nếu cần kiểm tra phần tử, duyệt và xác nhận chúng theo chính sách phù hợp.

### Sai lầm 9: “Muốn bỏ NPE chỉ cần cast T”

Cast không làm một giá trị null biến thành object; cast null sang một reference type vẫn cho null. Nó cũng không tạo ra method mới cho unbounded T trong chữ ký generic. Dùng kiểm tra null và bound/strategy thích hợp.

### Sai lầm 10: “Object có toString nên có thể dùng toString để ép API generic làm mọi thứ”

toString chỉ tạo một dạng biểu diễn; parse, so sánh, tính toán và truy cập thuộc tính domain cần API/contract riêng. Khi thiết kế generic method, hãy khai báo giới hạn kiểu hoặc truyền hàm thao tác, thay vì dựa trên định dạng chuỗi.

## 14. Quy tắc thiết kế generic API có liên quan đến null

Không có một chính sách null duy nhất cho mọi generic API. Điều quan trọng là đưa chính sách vào contract và thực thi nhất quán:

| Yêu cầu | Cách biểu diễn |
| --- | --- |
| Cho phép không có giá trị | Chấp nhận null và xử lý rõ ràng, hoặc dùng một kiểu trạng thái thích hợp |
| Tuyệt đối yêu cầu đầu vào có giá trị | Objects.requireNonNull tại ranh giới API |
| Muốn biểu diễn có/không có giá trị rõ ràng | Optional<T> nếu hợp với kiểu API; không lưu null bên trong Optional |
| Muốn dùng phương thức của một interface | <T extends InterfaceName> |
| Muốn dùng các phương thức số | <T extends Number> hoặc API toán học cụ thể |
| Muốn so sánh nhưng T không có Comparable | Truyền Comparator<? super T> |
| Muốn tạo object T | Truyền Supplier<? extends T> hoặc factory |
| Muốn kiểm tra class cụ thể của T | Truyền Class<T> khi cần; chú ý giới hạn của type erasure |

Ví dụ về một API từ chối null ngay khi khởi tạo:

~~~java
import java.util.Objects;

class NonNullBox<T> {
    private final T value;

    NonNullBox(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    T get() {
        return value;
    }
}
~~~

Dù T là unbounded type variable, class này xây dựng invariant riêng: sau khi constructor thành công, field value không null. Đây là bảo đảm từ **logic constructor và field final** (trong phạm vi code mẫu), không phải từ cú pháp **<T>**.

Nếu API cho phép null, cần kiểm tra trước khi gọi bất cứ instance method nào trên receiver đó. Đặc biệt, một bound như Comparable, Runnable hoặc Number cho phép compiler gọi phương thức tương ứng, nhưng receiver null vẫn dẫn đến NPE.

## 15. Tự kiểm tra

**Câu 1.** Với **class Box<T>**, T có cận trên mặc định là gì? Có được tự viết **Box<int>** không?

**Đáp án:** T có cận trên Object nếu không khai báo bound tường minh. **Box<int>** không hợp lệ; dùng Box<Integer> hoặc một kiểu tham chiếu khác.

**Câu 2.** Trong **static <T> boolean empty(T x) { return x == null; }**, phương thức có cần **T extends Object** không?

**Đáp án:** Không. T đã có cận Object ngầm định; so sánh với null hợp lệ vì T được dùng như reference type.

**Câu 3.** Vì sao **static <T> int length(T value) { return value.length(); }** không biên dịch? Cách sửa tối thiểu nếu muốn chấp nhận String và StringBuilder?

**Đáp án:** Object không có length(). Thêm bound: **static <T extends CharSequence> int length(T value) { return value.length(); }**. Vẫn phải xử lý null nếu đầu vào có thể null.

**Câu 4.** **T extends Number** có cho phép biểu thức **a + b** với hai biến T không?

**Đáp án:** Không. T là reference type variable, còn Number không định nghĩa toán tử cộng generic. Có thể dùng doubleValue() rồi cộng dưới kiểu double nếu yêu cầu cho phép.

**Câu 5.** Có thể gán **Object x = t** nếu t có kiểu T không bound? Có thể gán ngược **T t = x** một cách tổng quát không?

**Đáp án:** Có thể gán T sang Object. Không thể gán tùy ý Object sang T vì T có thể là subtype cụ thể của Object.

**Câu 6.** Tại sao **String.valueOf(value)** thường an toàn hơn **value.toString()** nếu value có thể null?

**Đáp án:** String.valueOf(Object) chuyển null thành chuỗi "null"; gọi trực tiếp toString trên receiver null ném NullPointerException.

**Câu 7.** So sánh **value == null**, **value.equals(other)** và **Objects.equals(value, other)**.

**Đáp án:** Phép == null kiểm tra thiếu tham chiếu; value.equals dùng logic equals của object nhưng gây NPE khi value null; Objects.equals null-safe và so sánh nội dung dựa trên equals khi các đối tượng khác null.

**Câu 8.** Tại sao **new T()** không hợp lệ? Nên làm gì nếu hàm generic cần tạo đối tượng mới?

**Đáp án:** Type erasure không cung cấp constructor cụ thể của T ở runtime. Nhận Supplier<T> hoặc một factory thích hợp để caller cung cấp cách tạo.

**Câu 9.** Đoạn **class Box<T extends Number> { T n; }** có thể có n == null không?

**Đáp án:** Có. Giới hạn kiểu bằng Number không biến thành bảo đảm non-null.

**Câu 10.** Khi nào nên dùng **<T extends Comparable<T>>**, khi nào nên truyền Comparator?

**Đáp án:** Dùng bound nếu API yêu cầu T có thứ tự tự nhiên qua Comparable<T>; truyền Comparator<? super T> nếu muốn cho phép so sánh tùy chiến lược hoặc với kiểu không implement Comparable phù hợp.

## 16. Ghi nhớ để áp dụng

Với type parameter **T không bound**, compiler biết tối thiểu rằng T phù hợp với **Object**. Điều này đủ cho kiểm tra null, gán từ T sang Object và gọi các phương thức Object khả dụng trên receiver không null. Nó **không** đủ để gọi length(), compareTo(), doubleValue(), tạo new T() hoặc thực hiện phép cộng số học tổng quát.

Null là một vấn đề độc lập với bounds: **T**, **T extends Number** và **T extends Comparable<T>** đều có thể nhận null khi ngữ cảnh cho phép. Nếu cần một invariant khác null, hãy thể hiện nó trong hợp đồng API và kiểm tra ở đúng ranh giới. Khi cần thao tác chuyên biệt, thêm **extends** cho đúng interface/class hoặc cung cấp một hàm/strategy làm việc với T. Giữ được sự phân biệt này giúp khai báo generics vừa linh hoạt, vừa an toàn kiểu và dễ suy luận.
