# Tham số kiểu, đối số kiểu, biến kiểu và kiểu tham số hóa trong Java

## 1. Mục tiêu và bức tranh tổng quát

Generics cho phép mô tả quan hệ giữa các kiểu ngay trong khai báo lớp, interface, constructor và phương thức. Thay vì viết một cấu trúc dữ liệu chỉ thao tác với Object rồi ép kiểu ở nơi sử dụng, ta khai báo một “chỗ trống” cho kiểu và để trình biên dịch kiểm tra các thao tác đối với kiểu đó.

Sau bài này, bạn cần nhận diện chính xác bốn thuật ngữ **type parameter**, **type argument**, **type variable**, **parameterized type**; đọc được khai báo generic lồng nhau, phân biệt generic class với generic method, hiểu wildcard/bound là gì và biết điểm nào chỉ tồn tại ở thời gian biên dịch.

Một ví dụ ngắn:

~~~java
class Box<T> {
    T value;
}

Box<String> title = new Box<>();
~~~

- **Box<T>** trong dòng khai báo: **T** được khai báo là *tham số kiểu* (type parameter), đồng thời tạo ra *biến kiểu* (type variable) tên T trong phạm vi của lớp.
- **Box<String>** tại nơi sử dụng: **String** là *đối số kiểu* (type argument) được truyền vào vị trí T; toàn bộ **Box<String>** là một *kiểu tham số hóa* (parameterized type).
- **new Box<>()**: toán tử kim cương (**diamond operator**) cho phép Java suy luận đối số kiểu từ ngữ cảnh gán, ở đây là String.
- Tên **Box** là tên khai báo lớp generic; dùng **Box** không kèm đối số trong một ngữ cảnh kiểu thường tạo ra *raw type*, cần phân biệt với **Box<?>**.

Bốn khái niệm liên hệ với nhau nhưng trả lời bốn câu hỏi khác nhau: **khai báo vị trí nhận kiểu ở đâu?** (type parameter), **tên kiểu đại diện bên trong khai báo là gì?** (type variable), **kiểu nào được đưa vào vị trí đó?** (type argument), và **kiểu hình thành sau khi áp dụng đối số kiểu là gì?** (parameterized type).

## 2. Tham số kiểu — type parameter

*Tham số kiểu* xuất hiện trong danh sách dấu ngoặc nhọn góc ngay sau tên lớp/interface, hoặc ngay trước kiểu trả về của phương thức generic. Nó khai báo một tên đại diện cho kiểu sẽ được sử dụng thống nhất tại các vị trí liên quan.

~~~java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
~~~

**K** và **V** là hai tham số kiểu độc lập; cú pháp khai báo của chúng là **<K, V>**. Trình biên dịch dùng mối quan hệ này để bảo đảm phương thức key() trả về đúng kiểu đối với cặp cụ thể, và phương thức value() tương tự. Việc dùng hai chữ khác nhau thể hiện chúng không bắt buộc phải cùng kiểu.

Các vị trí khai báo thường gặp:

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Lớp generic | class Box<T> | T thuộc khai báo lớp |
| Interface generic | interface Repository<ID, E> | ID và E thuộc interface |
| Phương thức generic | static <T> T identity(T value) | T chỉ thuộc phương thức |
| Constructor generic | <U> Holder(U source) | U thuộc constructor |
| Tham số có cận trên | <T extends Number> | T phải thỏa ràng buộc Number |
| Nhiều cận trên | <T extends Number & Comparable<T>> | T phải thỏa cả hai ràng buộc |

Trong cú pháp phương thức, **<T>** đặt **trước kiểu trả về**. Ví dụ **static <T> T identity(T value)** có tham số kiểu T, trả về T và nhận vào một giá trị kiểu T. Nếu viết **static T identity(T value)** trong một lớp không khai báo T, trình biên dịch không biết T là gì.

Danh sách tham số kiểu cũng biểu diễn ràng buộc:

~~~java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }
}
~~~

Ở đây **T extends Number** nghĩa là kiểu đưa vào phải là Number hoặc một subtype của Number, ví dụ Integer hoặc Double. Từ khóa extends áp dụng cho cả lớp lẫn interface trong giới hạn generic; không có cú pháp **<T implements Runnable>**. Khi có nhiều cận, cận là class (nếu có) phải đứng đầu; những cận sau là interface, nối bằng dấu **&**. Không thể khai báo hai cận là hai class khác nhau.

Quy ước tên hay gặp: **T** (Type), **E** (Element), **K** (Key), **V** (Value), **R** (Result), **U** (một kiểu khác). Đây chỉ là quy ước, không phải từ khóa Java. Có thể dùng tên dài hơn, nhưng một tên dễ nhận diện giúp đọc chữ ký API nhanh hơn.

## 3. Biến kiểu — type variable

*Biến kiểu* là tên **T**, **K**, **V** hoặc tên khác được khai báo bởi type parameter. Nó được dùng như một **kiểu** bên trong phạm vi hợp lệ, không phải một biến chứa giá trị lúc chạy.

~~~java
class CacheEntry<K, V> {
    private K key;
    private V cachedValue;

    CacheEntry(K key, V cachedValue) {
        this.key = key;
        this.cachedValue = cachedValue;
    }

    V read() {
        return cachedValue;
    }
}
~~~

Trong ví dụ này, K và V dùng ở vị trí kiểu của field, tham số constructor và kiểu trả về. Chúng không phải hai đối tượng runtime tên K và V; không thể gán **T = String** hay in T như một giá trị chỉ vì đã khai báo **<T>**. Khi dùng CacheEntry<String, Integer>, trình biên dịch kiểm tra key thuộc String và cachedValue thuộc Integer.

Phạm vi (scope) rất quan trọng:

- Type variable khai báo trên lớp dùng được trong các instance field, instance method và phần khai báo kiểu thích hợp của lớp.
- Type variable khai báo bởi một phương thức chỉ tồn tại trong chữ ký/thân phương thức đó; hai phương thức cùng đặt tên **T** có thể có hai type variable khác nhau.
- Một thành viên static của lớp generic không được dùng trực tiếp T thuộc lớp, vì static thuộc về lớp nói chung chứ không thuộc riêng Box<String> hay Box<Integer>. Phương thức static muốn dùng T phải **tự khai báo** tham số kiểu của mình.

~~~java
class Helper<T> {
    T echo(T input) {          // T của lớp
        return input;
    }

    static <U> U identity(U input) { // U riêng của phương thức static
        return input;
    }
}
~~~

Có một điểm dễ nhầm: **type parameter** nhấn mạnh *vị trí khai báo* **<T>**, còn **type variable** nhấn mạnh *tên T đã được khai báo và dùng như một kiểu*. Chúng có quan hệ chặt chẽ nhưng không phải “type variable” là một kiểu được truyền vào.

Thậm chí cùng một ký hiệu T có thể giữ hai vai trò ở hai tầng: trong **class Box<T>**, T là tên của type parameter; trong **List<T> values**, T là *type variable* đang được dùng làm *type argument* cho generic interface List. Vai trò của một biểu thức phụ thuộc **ngữ cảnh xuất hiện**, không chỉ phụ thuộc ký tự nó chứa.

## 4. Đối số kiểu — type argument

*Đối số kiểu* nằm trong **<...> tại nơi sử dụng một kiểu generic**. Nó chỉ rõ kiểu mà một vị trí tham số kiểu phải đại diện ở cách sử dụng đó.

~~~java
Pair<String, Integer> age = new Pair<>("Lan", 24);
Pair<Long, Long> range = new Pair<>(100L, 200L);
java.util.List<String> names = java.util.List.of("An", "Binh");
java.util.Map<String, java.util.List<Integer>> marks =
        java.util.Map.of("java", java.util.List.of(8, 9));
~~~

Đọc lần lượt:

- Pair<String, Integer> có **String** là đối số cho K, **Integer** là đối số cho V.
- Pair<Long, Long> truyền cùng một kiểu Long vào hai vị trí *khác nhau*; không có quy tắc buộc K khác V.
- List<String> truyền String cho tham số E của List<E>.
- Map<String, List<Integer>> truyền String cho K và **cả kiểu List<Integer>** cho V; bên trong List<Integer> lại có Integer làm đối số kiểu.
- Đối số kiểu thông thường là kiểu tham chiếu (reference type), bao gồm interface, class, array type và kiểu tham số hóa. **List<int>** là lỗi; dùng **List<Integer>**. **List<int[]>** lại hợp lệ vì int[] là reference type.

Không chỉ tên lớp cụ thể mới là type argument. Wildcard cũng là một dạng đối số kiểu:

~~~java
java.util.List<?> unknown;
java.util.List<? extends Number> numbers;
java.util.List<? super Integer> integerConsumers;
~~~

Ở đây **?**, **? extends Number**, **? super Integer** là các *wildcard type arguments*. Chúng mô tả một tập những kiểu có thể tương thích, không khai báo một biến kiểu mang tên mới. **?** không phải tên khác của T, và không thể khai báo **class Box<?>** thay cho **class Box<T>**.

Khi thấy **<T>**, hãy hỏi nó đang **khai báo** tên T hay **truyền** T làm đối số cho một generic type khác: **class Box<T>** khai báo; **List<T>** bên trong Box lại đang dùng T làm đối số.

## 5. Kiểu tham số hóa — parameterized type

*Parameterized type* hình thành khi dùng một khai báo generic với danh sách type argument, ví dụ **List<String>**, **Map<String, Integer>**, **Box<T>**, **List<?>**. Khái niệm này nói đến **toàn bộ kiểu**, còn type argument chỉ nói đến thành phần được truyền vào.

| Biểu thức | Phân loại | Lý do |
| --- | --- | --- |
| List<E> trong khai báo interface List<E> | Generic interface declaration với tham số kiểu E | Đang giới thiệu E |
| List<String> | Parameterized type | Dùng List với đối số String |
| Map<String, List<Integer>> | Parameterized type lồng nhau | V là một parameterized type khác |
| List<T> trong một lớp có <T> | Parameterized type sử dụng type variable | T đã có phạm vi và được truyền vào List |
| List<?> | Parameterized type dùng wildcard | Không biết chính xác đối số kiểu |
| List (không có ngoặc góc trong vị trí kiểu) | Raw type | Bỏ qua đối số kiểu của List |
| String | Kiểu lớp thông thường | String không phải generic class |

Phân biệt **generic type declaration** và **parameterized type**: **interface List<E>** là khai báo generic; **List<String>** là một cách sử dụng đã truyền đối số. Một generic declaration có thể có nhiều kiểu tham số hóa hợp lệ và chúng khác nhau về kiểm tra kiểu ở thời gian biên dịch.

Đừng hiểu “parameterized type” là một lớp vật lý riêng được Java tạo ra cho từng đối số. Ở JVM, cơ chế type erasure khiến ArrayList<String> và ArrayList<Integer> đều thường dùng cùng runtime class ArrayList; phần generic chủ yếu bảo đảm quan hệ kiểu trong mã nguồn và các kiểm tra/chuyển kiểu cần thiết do compiler chèn vào.

## 6. Ví dụ chạy độc lập: xác định từng vai trò

Lưu thành **GenericTermsDemo.java**:

~~~java
import java.util.List;

public class GenericTermsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <E> E first(List<E> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return items.get(0);
    }

    public static void main(String[] args) {
        Box<String> greeting = new Box<>("Java generics");
        List<Integer> versions = List.of(17, 21);

        String message = greeting.get();
        int firstVersion = first(versions);

        System.out.println(message);
        System.out.println(firstVersion);
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 GenericTermsDemo.java
java GenericTermsDemo
~~~

Stdout:

~~~text
Java generics
17
~~~

Giải thích từng bước:

1. **Box<T>** khai báo một type parameter T; **T value**, **Box(T value)** và **T get()** dùng type variable T trong lớp.
2. **Box<String>** là parameterized type, String là đối số kiểu. Phép gán kết quả get() cho String được kiểm tra khi biên dịch.
3. **new Box<>** suy luận String nhờ bên trái phép gán; dấu **<>** ở constructor không khai báo một type parameter mới.
4. **<E> E first(List<E> items)** khai báo một generic method. **E** là type variable của phương thức; **List<E>** là parameterized type dùng E làm đối số.
5. Từ đối số **List<Integer>**, compiler suy luận E là Integer khi gọi first(versions). Integer được auto-unbox để gán vào **int firstVersion**.
6. **List.of(17, 21)** tạo danh sách không cho thay đổi cấu trúc, có kiểu phần tử Integer; đây là đặc tính của factory List.of, không phải thuộc tính chung của mọi List<Integer>.

Nếu thay câu lệnh bằng **String invalid = first(versions);**, trình biên dịch báo lỗi kiểu vì Integer không thể được dùng làm String; generics giúp lỗi được phát hiện sớm.

## 7. Generic class, generic method và generic constructor

Lớp generic khai báo tham số kiểu ngay sau tên lớp; các instance member dùng được tham số này. Phương thức generic có **danh sách tham số kiểu riêng**, đứng trước kiểu trả về, kể cả khi lớp chứa nó không generic.

~~~java
class Samples<T> {
    T stored;

    Samples(T stored) {
        this.stored = stored;
    }

    T get() {
        return stored;           // Dùng T của lớp; bản thân get() không khai báo <T>
    }

    <U> U select(U candidate) {
        return candidate;        // U chỉ thuộc phương thức select()
    }

    static <R> R same(R value) {
        return value;            // R do chính phương thức static khai báo
    }
}
~~~

Một constructor cũng có thể khai báo type parameter độc lập:

~~~java
class Receipt<T> {
    private final T value;

    <U> Receipt(U original, java.util.function.Function<U, T> converter) {
        this.value = converter.apply(original);
    }

    T get() { return value; }
}

// Ví dụ sử dụng:
// Receipt<Integer> receipt = new Receipt<>("42", Integer::parseInt);
~~~

T của Receipt thuộc lớp; U của constructor mô tả kiểu dữ liệu đầu vào, có thể khác T. **Receipt<Integer>** là parameterized type của lớp, trong khi lời gọi constructor còn cần compiler suy luận U là String.

Cần tách ba thao tác dễ giống nhau về hình dạng: khai báo **<T>**; sử dụng kiểu **Box<T>** trong phạm vi T đã có; và suy luận đối số bởi diamond **new Box<>()**. Chúng không thay thế lẫn nhau.

## 8. Ràng buộc type variable và wildcard: hai cơ chế khác nhau

Có hai kiểu giới hạn cần đọc đúng:

**Ràng buộc cho type parameter** viết khi khai báo generic: **<T extends Number>**, **<T extends Number & Comparable<T>>**. Nó đặt điều kiện lên T và cho phép thân hàm sử dụng các API của cận đã biết, ví dụ Number.doubleValue() hoặc Comparable.compareTo().

**Wildcard bound** viết ở nơi sử dụng kiểu: **List<? extends Number>** hoặc **List<? super Integer>**. Nó cho phép nhận một nhóm parameterized types mà không cần đặt tên biến kiểu cụ thể cho từng danh sách.

~~~java
import java.util.ArrayList;
import java.util.List;

public class BoundsAndVarianceDemo {
    static <T extends Number & Comparable<T>> T largest(List<T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        T maximum = items.get(0);
        for (T item : items) {
            if (item.compareTo(maximum) > 0) {
                maximum = item;
            }
        }
        return maximum;
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number value : source) {
            total += value.doubleValue();
        }
        return total;
    }

    static void addTwo(List<? super Integer> target) {
        target.add(2);
        target.add(4);
    }

    public static void main(String[] args) {
        System.out.println(largest(List.of(3, 8, 5)));
        System.out.println(sum(List.of(1, 2, 3)));

        List<Number> destination = new ArrayList<>();
        addTwo(destination);
        System.out.println(destination);
    }
}
~~~

Lưu thành **BoundsAndVarianceDemo.java**, chạy:

~~~bash
javac -encoding UTF-8 BoundsAndVarianceDemo.java
java BoundsAndVarianceDemo
~~~

Stdout:

~~~text
8
6.0
[2, 4]
~~~

Giải thích: trong largest, T là một kiểu cụ thể thống nhất được suy luận là Integer và có compareTo; còn trong sum, dấu **? extends Number** cho phép nhận List<Integer>, List<Double> hoặc List<Number>. Có thể đọc phần tử tối thiểu như Number, nhưng không thể thêm một Integer mới một cách an toàn vì kiểu phần tử thực tế có thể là Double. Trong addTwo, **? super Integer** có thể đại diện cho Integer, Number hoặc Object; vì vậy thêm Integer an toàn, nhưng lấy phần tử ra chỉ bảo đảm kiểu Object.

Quy tắc gợi nhớ **PECS** (Producer Extends, Consumer Super): nguồn sản sinh phần tử dùng **? extends T** khi phù hợp; đích tiêu thụ phần tử dùng **? super T**. Đây là hướng dẫn thiết kế API, không phải một luật cú pháp bắt mọi danh sách chỉ được đọc hoặc chỉ được ghi. Với **List<?>**, có thể đọc dưới kiểu Object; không thể thêm phần tử khác null vì kiểu thực tế chưa biết.

Nếu một phương thức cần **liên kết cùng một kiểu** giữa nhiều tham số hoặc giữa đầu vào và đầu ra, type variable có tên thường biểu đạt được quan hệ tốt hơn wildcard. Ví dụ **static <T> T choose(T a, T b)** trả về kiểu được compiler suy luận từ cả hai đối số; một chữ ký chỉ dùng **?** không thể dùng wildcard làm tên kiểu trả về độc lập.

## 9. Bất biến (invariance): không suy diễn quan hệ sai

Mặc dù **Integer extends Number**, điều đó **không** có nghĩa **List<Integer> extends List<Number>**. Generic parameterization mặc định là *invariant*.

Đoạn sau không biên dịch:

~~~java
import java.util.List;

// Chỉ minh họa lỗi kiểu; không phải chương trình runnable.
List<Integer> integers = List.of(1, 2);
List<Number> numbers = integers;  // Compile-time error
~~~

Nếu phép gán trên được cho phép, ai đó có thể thêm Double vào numbers rồi đọc nó như Integer từ integers, làm mất an toàn kiểu. Khi muốn *đọc Number từ nhiều loại danh sách*, dùng **List<? extends Number>**. Khi muốn *ghi Integer vào nhiều loại danh sách đích*, dùng **List<? super Integer>**.

Tương tự, **List<String>** không phải subtype của **List<Object>**, dù String là subtype của Object. Một phương thức nhận **List<Object>** được phép thêm bất kỳ Object nào; phương thức đó không thể làm như vậy với một List<String>.

Ví dụ đối chiếu những chữ ký:

| Chữ ký | Nhận List<Integer>? | Có thể thêm Integer? | Kiểu đọc tối thiểu |
| --- | --- | --- | --- |
| List<Integer> | Có | Có (nếu list cho phép sửa) | Integer |
| List<Number> | Không | Có | Number |
| List<? extends Number> | Có | Không, trừ null | Number |
| List<? super Integer> | Có | Có (nếu list cho phép sửa) | Object |
| List<?> | Có | Không, trừ null | Object |

Khả năng biên dịch thao tác **add** không bảo đảm đối tượng danh sách có thể thay đổi ở runtime: List.of(...) vẫn ném UnsupportedOperationException nếu gọi add, dù tham số kiểu hợp lệ.

## 10. Type inference: khi không viết rõ đối số kiểu

Java thường suy luận kiểu generic từ kiểu biến nhận, tham số được truyền, ràng buộc generic và ngữ cảnh biểu thức.

~~~java
java.util.List<String> a = new java.util.ArrayList<String>();
java.util.List<String> b = new java.util.ArrayList<>();
java.util.List<Integer> c = java.util.List.of(1, 2, 3);
java.util.Map<String, java.util.List<Integer>> d = new java.util.HashMap<>();
~~~

Hai dòng đầu tạo cùng kiểu tham số hóa **List<String>** ở phía biến; dòng thứ hai dùng diamond để tránh lặp String. Trong **List.of(1, 2, 3)**, các literal int được boxing thành Integer và generic factory suy luận kiểu phù hợp. Kiểu tĩnh của biến bên trái vẫn quan trọng: ví dụ biến khai báo **List<String>** không tự trở thành **ArrayList<String>**, dù đối tượng là ArrayList.

Có thể chỉ rõ type argument khi gọi generic method nếu cần:

~~~java
String x = java.util.Objects.<String>requireNonNull("ok");
~~~

Phần **<String>** sau dấu chấm ở đây là **explicit method type argument**, không khai báo type parameter. Tương tự, **var names = java.util.List.of("A", "B");** suy luận kiểu biến từ initializer, không loại bỏ quy tắc generic. Dùng type inference khi rõ nghĩa; viết rõ kiểu khi nó giúp người đọc hiểu ý định hoặc giải quyết suy luận không đúng mong đợi.

## 11. Raw type và type erasure

Một **raw type** dùng tên generic mà không truyền type arguments, chẳng hạn **List** thay vì **List<String>** hoặc **List<?>**. Raw type chủ yếu dành cho tương thích mã Java cũ, bỏ qua phần kiểm tra kiểu cần thiết và có thể gây cảnh báo *unchecked*.

~~~java
// Minh họa rủi ro, không khuyến khích chạy:
java.util.List<String> safe = new java.util.ArrayList<>();
java.util.List raw = safe;      // Raw type
raw.add(123);                  // Unchecked call; gây heap pollution
String value = safe.get(0);    // ClassCastException khi chạy
~~~

Khác biệt với **List<?>**: List<?> vẫn thể hiện một danh sách có kiểu phần tử chưa biết và compiler ngăn thêm giá trị tùy ý; raw List làm mất nhiều kiểm tra đó. Hãy tránh raw type trong code mới; nếu phải làm việc với API cũ, giới hạn vùng unchecked và kiểm tra dữ liệu ở biên.

**Type erasure** là cơ chế Java dùng để hiện thực generics. Khi biên dịch, phần lớn type variables được thay bằng cận trên (hoặc Object nếu không có cận), compiler thêm cast cần thiết và có thể tạo bridge method để giữ tính đa hình. Do đó generic không tạo class riêng cho mỗi type argument.

Lưu thành **ErasureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List<Integer> counts = new ArrayList<>();

        System.out.println(words.getClass().equals(counts.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac ErasureDemo.java
java ErasureDemo
~~~

Stdout:

~~~text
true
~~~

Hai đối tượng đều là ArrayList ở runtime. Tuy nhiên, **đừng kết luận toàn bộ thông tin generic đều bị xóa khỏi mọi metadata**: chữ ký generic được lưu trong một số metadata của class/method và reflection có thể đọc chúng. Điều thường không thể làm chỉ từ một đối tượng ArrayList bất kỳ là khôi phục chắc chắn type argument String hay Integer của biến đã trỏ tới nó.

Hệ quả thực hành:

- Không viết **new T()** hoặc **new T[10]** với một type variable thông thường: runtime không có class cụ thể của T để khởi tạo trực tiếp. Thường truyền **Supplier<T>** hay **Class<T>** hoặc một factory nếu cần tạo đối tượng.
- Không tạo trực tiếp **new List<String>[10]**: array kiểm tra thành phần ở runtime trong khi parameterized type này không reifiable. Có thể dùng collection of collections thay thế.
- Không dùng **List<String>.class** hoặc **instanceof List<String>** để kiểm tra đối số kiểu của một instance. **List.class** và **instanceof List<?>** là những hình thức hợp lệ trong tình huống tương ứng.
- Không khai báo hai overload chỉ khác nhau bởi **List<String>** và **List<Integer>** cùng vị trí tham số vì sau erasure chúng có cùng signature.
- Cảnh báo **unchecked** là dấu hiệu compiler không chứng minh được an toàn kiểu; đừng tùy tiện che bằng @SuppressWarnings khi chưa kiểm soát cast/nguồn dữ liệu.

## 12. Lỗi nhận diện thường gặp và cách sửa

**Nhầm type parameter với type argument.** Trong **class Result<T>**, T được khai báo; trong **Result<String>**, String được truyền vào. Trong **List<T>** xuất hiện bên trong khai báo Result<T>, T đã được khai báo ở ngoài và đang đóng vai trò đối số cho List.

**Tưởng T là giá trị runtime.** T là tên kiểu ở thời gian biên dịch. Nó không giữ đối tượng Class tương ứng; cần một **Class<T>**, Supplier<T> hoặc factory được truyền riêng khi API đòi hỏi thông tin tạo/kiểm tra runtime.

**Dùng type variable ngoài scope.** Viết static T transform(T x) trong lớp Generic<T> là không hợp lệ nếu T chỉ thuộc lớp. Sửa thành **static <U> U transform(U x)** hoặc dùng method instance với T thuộc lớp.

**Nhầm wildcard với khai báo tham số kiểu.** **List<?>** biểu diễn một dạng sử dụng danh sách, không khai báo tên để dùng lại. **<T> void copy(List<T> a, List<T> b)** liên kết hai danh sách cùng kiểu T; trong khi **void inspect(List<?> a)** thích hợp khi chỉ cần một danh sách có kiểu bất kỳ.

**Dùng List<Object> thay cho List<?>.** Hàm chỉ cần duyệt mọi loại danh sách có thể nhận List<?>; List<Object> không nhận List<String>. Muốn thao tác với một kiểu phần tử chung, hãy cân nhắc generic method hoặc bounded wildcard.

**Tin rằng diamond thay đổi ý nghĩa kiểu.** **new Box<>()** không tạo raw Box; nó yêu cầu compiler suy luận type arguments từ ngữ cảnh. **new Box()** mới là lời gọi constructor qua raw type trong ngữ cảnh đó.

**Bỏ qua khả năng thay đổi của collection.** Type argument mô tả kiểu phần tử, không mô tả danh sách có sửa được hay không. Ví dụ List.of trả về unmodifiable list.

**Bỏ qua cảnh báo unchecked.** Một phép gán/gọi thông qua raw API có thể biên dịch nhưng thất bại muộn với ClassCastException; xử lý ở nơi chuyển dữ liệu từ kiểu không bảo đảm sang kiểu generic cụ thể.

## 13. Quy trình đọc một chữ ký generic

Khi gặp một API phức tạp, hãy đọc theo thứ tự:

1. Tìm **phần khai báo tham số kiểu**: ví dụ **<T extends Number>** hoặc **<K, V>**. Xác định scope (class hay method) và bounds.
2. Tìm nơi type variable xuất hiện trong **tham số đầu vào, kiểu trả về và kiểu lồng nhau** để biết API ràng buộc các vị trí ra sao.
3. Tại điểm gọi, xác định **type arguments thực** hoặc kiểu mà compiler sẽ suy luận.
4. Xem **parameterized type toàn phần** và kiểm tra invariance, wildcard upper/lower bound nếu có.
5. Phân biệt điều **compiler bảo đảm** với điều cần kiểm tra ở runtime (erasure, raw type, collection mutability).

Ví dụ chữ ký:

~~~java
static <T extends Number> void collect(
        java.util.List<? extends T> input,
        java.util.List<? super T> output) {
    output.addAll(input);
}
~~~

- **<T extends Number>**: khai báo type parameter T, cận trên Number.
- **List<? extends T>**: parameterized type dùng upper-bounded wildcard, cho phép đọc những phần tử được bảo đảm tương thích T.
- **List<? super T>**: parameterized type dùng lower-bounded wildcard, là đích có thể nhận T.
- **T** xuất hiện trong wildcard bounds là *type variable* đã khai báo bên ngoài; nó không phải một type parameter mới.
- **output.addAll(input)** hợp lệ do wildcard và signature của addAll phối hợp để kiểm tra mối quan hệ kiểu.

## 14. Tự kiểm tra

**Câu 1.** Trong **class Mapper<S, R>**, phần nào là type parameters? Trong **Mapper<String, Integer>**, phần nào là type arguments và phần nào là parameterized type?

**Đáp án:** S và R là type parameters; chúng tạo type variables S, R. String và Integer là type arguments; toàn bộ Mapper<String, Integer> là parameterized type.

**Câu 2.** Tại sao **List<Number> n = new ArrayList<Integer>();** không biên dịch dù Integer kế thừa Number?

**Đáp án:** List bất biến theo type argument; cần List<Number> thực sự, hoặc dùng **List<? extends Number>** nếu mục tiêu là đọc Number từ danh sách Integer.

**Câu 3.** Trong **static <T> List<T> singleton(T value)**, T ở ba vị trí là gì?

**Đáp án:** T trong **<T>** là tên type parameter được khai báo; T trong **List<T>** là type variable đang được dùng làm type argument của List; T ở **(T value)** là type variable dùng làm kiểu của tham số value. Toàn bộ List<T> là parameterized type.

**Câu 4.** Phương thức muốn thêm Integer vào cả List<Integer> lẫn List<Number> cần tham số nào?

**Đáp án:** **List<? super Integer>**; vì cả Integer và Number đều là supertype (theo nghĩa bằng hoặc rộng hơn) của Integer. Phương thức có thể gọi add(Integer), nhưng không được giả định phần tử đọc ra chắc chắn là Integer.

**Câu 5.** So sánh **List**, **List<?>** và **List<String>**.

**Đáp án:** List là raw type thiếu type arguments và làm giảm type safety; List<?> là parameterized type với wildcard chưa biết kiểu phần tử; List<String> là parameterized type có đối số String và compiler kiểm tra các phần tử theo String.

Khi đã phân biệt rõ *khai báo tham số*, *tên biến kiểu*, *đối số truyền vào* và *kiểu được tạo thành*, các khái niệm tiếp theo như generic API, giới hạn kiểu, variance qua wildcard và type erasure trở nên dễ đọc hơn: chúng đều xây trên quan hệ giữa bốn thành phần cốt lõi này.
