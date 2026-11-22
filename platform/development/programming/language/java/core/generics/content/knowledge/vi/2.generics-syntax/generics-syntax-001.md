# Khai báo một hoặc nhiều tham số kiểu trong Java Generics

## 1. Mục tiêu

Java Generics cho phép khai báo một lớp, interface, record, phương thức hoặc constructor có **một hay nhiều tham số kiểu** (*type parameters*). Các tham số kiểu là tên đại diện cho kiểu dữ liệu sẽ được lựa chọn khi dùng API. Chúng giúp trình biên dịch kiểm tra mối quan hệ giữa giá trị đầu vào, giá trị lưu trữ và kết quả trả về mà không cần ép kiểu thủ công.

Sau bài này, bạn có thể:

- Viết đúng cú pháp **<T>**, **<K, V>**, **<I, O>** cho từng loại khai báo.
- Nhận ra đâu là vị trí **khai báo** tham số kiểu và đâu là vị trí **truyền đối số kiểu**.
- Phân biệt tham số kiểu thuộc class với tham số kiểu riêng của method/constructor.
- Hiểu tính độc lập, thứ tự, phạm vi và ràng buộc cơ bản của nhiều tham số kiểu.
- Áp dụng cú pháp Java 17+ trong một chương trình biên dịch, chạy được và tránh các lỗi thường gặp.

Đầu tiên, so sánh hai khai báo:

~~~java
class Box<T> {
    private T value;
}

class Pair<K, V> {
    private K key;
    private V value;
}
~~~

**Box<T>** khai báo **một** tham số kiểu T. **Pair<K, V>** khai báo **hai** tham số kiểu K và V. Một chữ như T, K hoặc V chỉ là *tên* của type parameter: nó không tự đại diện cho String, Integer hay một class nào cho đến khi xuất hiện ở ngữ cảnh sử dụng cụ thể.

## 2. Ngữ pháp khai báo: dấu ngoặc nhọn góc

Dạng cơ bản:

~~~text
class TênLớp<T> { ... }
class TênLớp<K, V> { ... }
interface TênInterface<I, O> { ... }
record TênRecord<A, B>(A first, B second) { ... }

<T> KiểuTrảVề tênPhươngThức(... ) { ... }
<A, B> KiểuTrảVề tênPhươngThức(... ) { ... }
~~~

Các nguyên tắc cú pháp:

1. Danh sách type parameters nằm trong **<...>** và được ngăn cách bằng **dấu phẩy**. Không có dấu phẩy sau tham số cuối: **<K, V>** hợp lệ; **<K, V,>** không hợp lệ.
2. Mỗi tên type parameter phải là định danh Java hợp lệ, phân biệt chữ hoa/chữ thường. Ví dụ T và t là hai tên khác nhau, dù quy ước thường viết T, E, K, V bằng chữ hoa.
3. Trong một danh sách, các tên phải **khác nhau**: **<T, T>** không hợp lệ vì khai báo trùng tên.
4. Dấu ngoặc trong khai báo class/interface/record đi **ngay sau tên** loại; danh sách của generic method đi **trước kiểu trả về**; danh sách của generic constructor đi **trước tên constructor**.
5. Có thể khai báo một, hai, ba hoặc nhiều tham số kiểu, không có giới hạn cú pháp cố định là chỉ một T; hãy dùng đúng số lượng cần thiết để biểu diễn các quan hệ kiểu có ý nghĩa.
6. Danh sách type parameters là phần khai báo **kiểu**, không phải danh sách tham số nhận giá trị. Ví dụ constructor **Pair(K key, V value)** có hai tham số giá trị tên key và value, còn **class Pair<K, V>** có hai tham số kiểu K và V.

Một ví dụ dễ đọc:

~~~java
class Triple<A, B, C> {
    private final A first;
    private final B second;
    private final C third;

    Triple(A first, B second, C third) {
        this.first = first;
        this.second = second;
        this.third = third;
    }

    A first() { return first; }
    B second() { return second; }
    C third() { return third; }
}
~~~

A, B và C là ba tên kiểu độc lập; chúng có thể được gán cùng kiểu hoặc các kiểu khác nhau tại từng cách sử dụng Triple. Độ phức tạp không tự động tăng chất lượng API: nếu tất cả thuộc tính luôn cùng kiểu và có vai trò giống nhau, một tham số kiểu T có thể biểu diễn tốt hơn ba tên độc lập.

## 3. Khai báo một tham số kiểu cho class

Khai báo phổ biến nhất là **class Box<T>**: một kiểu T được dùng nhất quán cho giá trị đưa vào, lưu trữ và lấy ra.

~~~java
class Box<T> {
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
}
~~~

Trong phần **class Box<T>**, T được **khai báo**. Sau đó:

- **private T value**: field thuộc kiểu T.
- **Box(T value)**: tham số giá trị của constructor phải có kiểu T.
- **T get()**: phương thức trả về T.
- **void set(T value)**: phương thức nhận giá trị thuộc T.

Khi sử dụng, ta truyền *type argument* vào chỗ đã khai báo:

~~~java
// Minh họa trong thân phương thức hoặc khối lệnh:
Box<String> label = new Box<>("Java");
Box<Integer> counter = new Box<>(10);

String text = label.get();
Integer number = counter.get();
~~~

**String** và **Integer** ở đây là *đối số kiểu* (*type arguments*), còn **Box<String>** và **Box<Integer>** là những *kiểu tham số hóa* (*parameterized types*). Việc khai báo class chỉ viết một lần; compiler áp dụng quan hệ kiểu của nó cho nhiều cách sử dụng.

**new Box<>()** dùng *diamond operator*: đối số kiểu của constructor được suy luận từ ngữ cảnh. Phía khai báo **class Box<T>** vẫn cần nêu rõ tên T; không thể khai báo class bằng **class Box<>**.

Trong Java, tham số kiểu mặc định dùng một kiểu tham chiếu. **Box<int>** là lỗi, cần **Box<Integer>**; **Box<String>**, **Box<int[]>** và **Box<List<String>>** đều có thể hợp lệ nếu những kiểu được sử dụng đã được khai báo hoặc import đúng.

## 4. Khai báo nhiều tham số kiểu cho class

Khai báo **<K, V>** thường mô tả hai kiểu có vai trò khác nhau, ví dụ khóa và giá trị. Mỗi tên được phân tách bằng dấu phẩy, và mỗi vị trí có ý nghĩa riêng.

~~~java
class Entry<K, V> {
    private final K key;
    private final V value;

    Entry(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
~~~

Khi sử dụng:

~~~java
// Minh họa trong thân phương thức hoặc khối lệnh:
Entry<String, Integer> age = new Entry<>("Lan", 20);
Entry<Long, Long> interval = new Entry<>(100L, 200L);

String name = age.key();    // K là String
Integer years = age.value(); // V là Integer
~~~

**Thứ tự theo vị trí** rất quan trọng. Với **Entry<String, Integer>**, K tương ứng String và V tương ứng Integer; đảo thành **Entry<Integer, String>** tạo một parameterized type khác, trong đó vai trò hai kiểu cũng đảo ngược.

**K và V không bắt buộc phải khác nhau**. Entry<Long, Long> hoàn toàn hợp lệ vì hai *tham số* K, V là hai vị trí khác nhau, dù hai *đối số* truyền vào trùng Long.

Nhiều tham số kiểu có thể lồng nhau:

~~~java
class Table<K, V> {
    private java.util.Map<K, java.util.List<V>> rows =
            new java.util.HashMap<>();
}
~~~

Trong **class Table<K, V>**, chỉ **K và V** được khai báo mới. Biểu thức **Map<K, List<V>>** đang dùng K và V làm type arguments cho hai generic types đã có là Map và List; không có khai báo K/V bổ sung bên trong Map hay List.

### Khi nào dùng một T, khi nào dùng nhiều tên?

- **Box<T>** phù hợp khi mọi thao tác gắn với cùng một kiểu giá trị.
- **Pair<A, B>** phù hợp khi muốn mang theo hai giá trị mà mỗi bên có thể có kiểu riêng.
- **Mapper<I, O>** phù hợp khi kiểu nhận vào có thể khác kiểu trả ra.
- **Repository<ID, E>** phù hợp khi kiểu khóa định danh có vai trò khác kiểu thực thể.
- **Triple<A, B, C>** chỉ nên xuất hiện khi thật sự có ba vai trò kiểu cần được biểu diễn.

Một thiết kế với nhiều tham số kiểu sẽ khó đọc nếu người dùng không hiểu vai trò của từng tên. Ưu tiên tên hoặc tài liệu API rõ nghĩa và giữ số lượng tham số kiểu vừa đủ.

## 5. Khai báo type parameters trên interface và record

Generics không chỉ dành cho class. Interface có thể khai báo một hoặc nhiều tham số kiểu:

~~~java
@FunctionalInterface
interface Converter<I, O> {
    O convert(I input);
}
~~~

I biểu diễn kiểu dữ liệu đi vào; O biểu diễn kiểu kết quả. Một triển khai sử dụng cụ thể:

~~~java
// Minh họa trong thân phương thức hoặc khối lệnh:
Converter<String, Integer> parser = Integer::parseInt;
Integer value = parser.convert("42");
~~~

Tại khai báo interface, I và O chưa được xác định thành kiểu cụ thể. Khi gán Converter<String, Integer>, mối quan hệ trở thành “nhận String, trả Integer”. Phương thức convert không cần tự viết **<I, O>**, vì đã có hai type variables từ interface.

Java 17 hỗ trợ generic record với cú pháp tương tự:

~~~java
record Point<X, Y>(X x, Y y) {}
~~~

**Point<X, Y>** khai báo hai tham số kiểu cho record; các thành phần x và y dùng các tên đó làm kiểu. Ví dụ **Point<Integer, Integer> point = new Point<>(3, 5)** là hợp lệ. Record tự cung cấp constructor, accessor, equals, hashCode và toString theo đặc tả record. Generic record không làm thay đổi cách khai báo danh sách **<X, Y>**.

Khai báo có thể thêm ràng buộc cho từng tham số (xem mục 9), và một interface generic cũng có thể được triển khai với đối số cụ thể hoặc truyền tiếp các type variables:

~~~java
class StringLength implements Converter<String, Integer> {
    @Override
    public Integer convert(String input) {
        return input.length();
    }
}

class DelegatingConverter<I, O> implements Converter<I, O> {
    private final Converter<I, O> delegate;

    DelegatingConverter(Converter<I, O> delegate) {
        this.delegate = delegate;
    }

    @Override
    public O convert(I input) {
        return delegate.convert(input);
    }
}
~~~

Trong StringLength, String/Integer là type arguments cụ thể. Trong DelegatingConverter, **<I, O>** là khai báo mới của class, và **implements Converter<I, O>** truyền hai type variables ấy làm đối số cho interface. Tên I/O ở hai khai báo không phải một “biến toàn cục”; chúng liên kết với nhau thông qua chữ ký implements.

## 6. Khai báo generic method: dấu <...> nằm trước kiểu trả về

Generic method tự khai báo type parameters của nó, không phụ thuộc vào việc lớp chứa nó có generic hay không. Cú pháp đúng:

~~~java
static <T> T identity(T value) {
    return value;
}

static <A, B> String format(A first, B second) {
    return String.valueOf(first) + " / " + String.valueOf(second);
}

static <T> void show(T value) {
    System.out.println(value);
}
~~~

Trật tự thành phần khi khai báo phương thức static là **static → <T> → kiểu trả về → tên phương thức → (tham số giá trị)**. Với instance method, bỏ static hoặc đặt modifiers như public ở trước **<T>**:

~~~java
public <E> E choose(E first, E second) {
    return first;
}
~~~

**<E>** mới là danh sách tham số kiểu. **E** kế tiếp là kiểu trả về; **E first** và **E second** là các tham số giá trị có kiểu E.

Đây là lỗi rất thường gặp:

~~~java
// Mã minh họa sai cú pháp/ngữ cảnh:
static T identity(T value) {
    return value;
}
~~~

Nếu T chưa được khai báo ở phạm vi hợp lệ thì compiler không thể tìm thấy kiểu T. Chỉnh thành **static <T> T identity(T value)**. Phần khai báo **<T>** cần có ngay cả khi compiler có thể suy luận T khi gọi phương thức.

Với nhiều tham số kiểu, mỗi tên có thể gắn vào kiểu trả về hoặc tham số khác nhau:

~~~java
static <K, V> java.util.Map<K, V> singletonMap(K key, V value) {
    return java.util.Map.of(key, value);
}
~~~

**K** và **V** được khai báo cho phương thức; Map<K, V> là kiểu trả về dùng hai tên đã khai báo; K key và V value là hai tham số giá trị. Khi gọi **singletonMap("ready", true)**, compiler thường suy luận K là String và V là Boolean.

Đối số kiểu của method có thể **được suy luận** hoặc **ghi tường minh**:

~~~java
// Giả sử đang ở cùng class với phương thức static identity:
String a = identity("abc");
String b = GenericMethods.<String>identity("abc");
~~~

Lời gọi có **<String>** sau tên class/dấu chấm truyền *method type argument* String; nó không phải khai báo type parameter mới. Để lời gọi ở ví dụ này biên dịch, phương thức identity phải được khai báo là static trong class tên GenericMethods và có thể truy cập tại vị trí gọi.

## 7. Phạm vi khai báo: tham số kiểu của class và của method

Quan sát một class vừa có type parameter ở cấp class, vừa có generic method riêng:

~~~java
class Holder<T> {
    private final T stored;

    Holder(T stored) {
        this.stored = stored;
    }

    T read() {
        return stored;
    }

    <U> U echo(U input) {
        return input;
    }

    static <R> R same(R input) {
        return input;
    }
}
~~~

Có ba type variables giữ ba vai trò:

- **T** được khai báo ở **Holder<T>**; dùng trong instance field stored, constructor và instance method read().
- **U** được khai báo bởi **<U> U echo(...)**; U chỉ có phạm vi tại method echo và có thể khác hoàn toàn T.
- **R** được khai báo bởi **static <R> R same(...)**; đây là type parameter của static method, không phải T của Holder.

Không thể dùng trực tiếp T của class generic trong **static field** hoặc **static method** như sau:

~~~java
class Wrong<T> {
    // static T cached;          // Compile-time error
    // static T reuse(T input) { // Compile-time error
    //     return input;
    // }
}
~~~

Lý do: thành viên static gắn với class Wrong chung, trong khi các cách sử dụng Wrong<String> và Wrong<Integer> đều là cùng một class ở runtime. Nếu cần generic static method, tự khai báo **static <U> U reuse(U input)**. Nếu cần sử dụng T của class, dùng instance method.

Một class generic chứa instance method **T read()** không có nghĩa read là *generic method* tự khai báo tham số mới: read chỉ **sử dụng** T đã được class khai báo. Generic method đích thực có danh sách type parameters của **chính phương thức**.

Phạm vi tên cũng giải thích tại sao không nên đặt trùng tên gây rối. Ví dụ phương thức **<T> T convert(T x)** bên trong class **Wrapper<T>** có một T riêng, có thể che tên T của class trong phạm vi phương thức. Phần mềm vẫn có thể biên dịch tùy cách dùng, nhưng nên dùng tên khác như U để tránh hiểu lầm về quan hệ kiểu.

## 8. Generic constructor với một hoặc nhiều tham số kiểu

Constructor có thể khai báo một danh sách type parameters **riêng**, ngay trước tên constructor, kể cả khi class không generic:

~~~java
class Receipt {
    private final String description;

    <T> Receipt(T source) {
        description = String.valueOf(source);
    }

    String description() {
        return description;
    }
}
~~~

Ở đây **<T> Receipt(T source)** là generic constructor của một class không generic. T chỉ được dùng trong constructor; **Receipt** không trở thành parameterized type chỉ vì constructor generic. Cách dùng **new Receipt(123)** hoặc **new Receipt("invoice")** đều hợp lệ.

Một class generic vẫn có thể có generic constructor với một type parameter **khác** của class:

~~~java
class Parsed<T> {
    private final T value;

    <S> Parsed(S raw, java.util.function.Function<S, T> parser) {
        value = parser.apply(raw);
    }

    T get() {
        return value;
    }
}
~~~

Ví dụ **Parsed<Integer> n = new Parsed<>("12", Integer::parseInt)**: **T** của class là Integer; **S** của constructor được suy luận thành String từ đối số raw và method reference. Đây là minh họa đặt trong một phương thức hợp lệ, với class Parsed hiện diện trong phạm vi.

Với nhiều tham số của constructor:

~~~java
class Summary {
    private final String text;

    <A, B> Summary(A left, B right) {
        text = left + " | " + right;
    }

    String text() {
        return text;
    }
}
~~~

Trong **<A, B> Summary(A left, B right)**, A và B là type parameters *của constructor*, độc lập với việc Summary không phải generic class. Phương thức text() trả về String cố định.

Khi cần giữ quan hệ kiểu trong **toàn bộ trạng thái và API** của đối tượng, khai báo tham số ở cấp class; khi chỉ cần linh hoạt đầu vào của **một lần tạo đối tượng**, generic constructor có thể phù hợp. Việc đặt type parameter ở đâu quyết định phạm vi sử dụng được tên đó.

## 9. Ràng buộc từng tham số kiểu bằng extends

Theo mặc định, một type parameter không khai báo bound tường minh có cận trên là **Object**. Ta có thể giới hạn tập đối số kiểu bằng **extends**.

Một tham số có cận:

~~~java
class Metric<T extends Number> {
    private final T number;

    Metric(T number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}
~~~

**T extends Number** yêu cầu T là Number hoặc subtype của Number. Do vậy Metric<Integer> và Metric<Double> hợp lệ, Metric<String> không hợp lệ. Compiler biết T có các phương thức của Number, nên gọi **number.doubleValue()** được kiểm tra an toàn.

Hai tham số có cận riêng:

~~~java
class IndexedValue<K extends Comparable<K>, V extends Number> {
    private final K key;
    private final V value;

    IndexedValue(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
~~~

**K extends Comparable<K>** là một cận interface cho K; **V extends Number** là cận class cho V. Mỗi vị trí phải thỏa bound tương ứng, không dùng cùng một bound cho cả hai tham số.

Một tham số có **nhiều cận trên**:

~~~java
static <T extends Number & Comparable<T>> T maximum(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

Cú pháp dùng **&** để nối các cận của *cùng một T*, còn dùng **dấu phẩy** để phân tách *những tham số kiểu khác nhau*. Đây là sự khác biệt cần nhớ:

| Cú pháp | Ý nghĩa |
| --- | --- |
| <A, B> | Khai báo hai tham số kiểu độc lập A và B |
| <T extends Number> | Một tham số T có cận Number |
| <K extends Comparable<K>, V> | Hai tham số; chỉ K có cận tường minh |
| <T extends Number & Comparable<T>> | Một T phải thỏa cả Number và Comparable<T> |
| <A extends Number, B extends Number> | Hai tham số, mỗi tham số có cận Number |

Khi có cận class và interface, cận class nếu hiện diện phải đứng trước các cận interface; không thể khai báo hai class bounds khác nhau. Dùng **extends** cho cả class bound lẫn interface bound, không viết **<T implements Comparable<T>>**. Không được khai báo lower bound bằng **<T super Number>**; **super** xuất hiện trong *wildcard type argument*, ví dụ List<? super Integer>, chứ không phải khai báo type parameter.

### Quan hệ giữa nhiều tham số kiểu

Một tham số có thể tham chiếu đến tham số khác trong bound. Ví dụ:

~~~java
class Registry<K, V extends java.io.Serializable> {
    // K không có cận tường minh; V phải thực thi Serializable.
}

class DirectedPair<A, B extends A> {
    private final A source;
    private final B detail;

    DirectedPair(A source, B detail) {
        this.source = source;
        this.detail = detail;
    }
}
~~~

Ở DirectedPair, B phải là A hoặc subtype của A. Bound như vậy thể hiện quan hệ kiểu mà compiler kiểm tra; nếu không có ràng buộc thật sự cần thiết, dùng <A, B> đơn giản sẽ rõ ràng hơn.

## 10. Ví dụ chạy hoàn chỉnh: một, hai và nhiều type parameters

Lưu thành tệp **GenericDeclarationsDemo.java**. Đây là một chương trình độc lập trên Java 17+:

~~~java
public class GenericDeclarationsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class Pair<K, V> {
        private final K key;
        private final V value;

        Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() {
            return key;
        }

        V value() {
            return value;
        }
    }

    @FunctionalInterface
    interface Converter<I, O> {
        O convert(I input);
    }

    static <T> T first(T left, T right) {
        return left;
    }

    static <A, B> Pair<B, A> swap(Pair<A, B> original) {
        return new Pair<>(original.value(), original.key());
    }

    public static void main(String[] args) {
        Box<String> language = new Box<>("Java");
        Pair<String, Integer> release = new Pair<>("version", 21);

        Pair<Integer, String> swapped = swap(release);
        Converter<String, Integer> parser = Integer::parseInt;

        System.out.println(language.get());
        System.out.println(release.key() + ": " + release.value());
        System.out.println(swapped.key() + " -> " + swapped.value());
        System.out.println(first("left", "right"));
        System.out.println(parser.convert("17") + 4);
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file:

~~~bash
javac -encoding UTF-8 GenericDeclarationsDemo.java
java GenericDeclarationsDemo
~~~

Stdout chính xác:

~~~text
Java
version: 21
21 -> version
left
21
~~~

Các điểm cần quan sát:

1. **Box<T>** khai báo **một** tham số kiểu. Trong Box<String>, String là đối số kiểu gắn cho T.
2. **Pair<K, V>** khai báo **hai** tham số kiểu. Pair<String, Integer> thiết lập K = String, V = Integer.
3. **Converter<I, O>** là interface với hai tham số kiểu khác vai trò. Converter<String, Integer> nhận chuỗi và trả Integer.
4. **static <T> T first(...)** tự khai báo T; không phụ thuộc T của Box.
5. **static <A, B> Pair<B, A> swap(Pair<A, B> original)** khai báo A, B để diễn tả quan hệ giữa *kiểu đầu vào* và *kiểu đầu ra*. Trong lời gọi swap(release), compiler suy luận A = String, B = Integer; kiểu trả về là Pair<Integer, String>.
6. Toán tử kim cương **new Pair<>(...)** nhờ ngữ cảnh constructor/kiểu đích mà không cần lặp danh sách đối số kiểu.
7. **Integer::parseInt** được chọn làm cách triển khai Converter<String, Integer>; expression **parser.convert("17") + 4** dùng phép unboxing từ Integer ra int để cộng 4.

Chú ý: trường hợp **Pair<String, Integer>** không tạo ra một class mới ở runtime cho mỗi tổ hợp kiểu; generics kiểm tra an toàn kiểu chủ yếu lúc biên dịch.

## 11. Ví dụ chạy hoàn chỉnh: giới hạn nhiều tham số

Lưu thành **BoundedParametersDemo.java**:

~~~java
public class BoundedParametersDemo {
    static final class NumberPair<A extends Number, B extends Number> {
        private final A left;
        private final B right;

        NumberPair(A left, B right) {
            this.left = left;
            this.right = right;
        }

        double sum() {
            return left.doubleValue() + right.doubleValue();
        }
    }

    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        NumberPair<Integer, Double> pair = new NumberPair<>(3, 2.5);
        Integer best = larger(7, 12);

        System.out.println(pair.sum());
        System.out.println(best);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BoundedParametersDemo.java
java BoundedParametersDemo
~~~

Stdout chính xác:

~~~text
5.5
12
~~~

Tại **NumberPair<A extends Number, B extends Number>**, hai type parameters có hai bound được khai báo riêng. Integer và Double đều là subtype của Number nên cách sử dụng **NumberPair<Integer, Double>** hợp lệ.

Trong **<T extends Number & Comparable<T>>**, chỉ có **một** T nhưng nó thỏa hai cận. Tại lời gọi larger(7, 12), hai giá trị int được boxing thành Integer; kiểu được suy luận là Integer, vốn vừa là Number vừa hiện thực Comparable<Integer>. Vì thế lời gọi compareTo hợp lệ.

## 12. Type parameter khác type argument và wildcard ở đâu?

Khi đọc dấu ngoặc góc, luôn xét **vị trí xuất hiện**:

~~~java
class Repository<ID, E> {                  // Khai báo type parameters
    java.util.List<E> items;                // E là type argument của List

    void save(E entity) {}                  // E là kiểu tham số giá trị
}

// Trong thân phương thức hoặc khối lệnh:
// Repository<Long, String> repo;             // Long/String là type arguments
// java.util.List<?> unknown;                // ? là wildcard type argument
~~~

- **<ID, E>** ngay sau Repository là danh sách **type parameters** được khai báo.
- **List<E>** là một **parameterized type** sử dụng E đã khai báo. Tại vị trí List<E>, E giữ vai trò *type argument* cho List.
- **Repository<Long, String>** là một parameterized type khác: Long và String là hai type arguments thay cho ID và E.
- **List<?>** biểu thị danh sách có kiểu phần tử chưa biết. Dấu **?** không khai báo tên mới, không thể đem **?** dùng như T và không thể khai báo **class Repository<?>**.

**Tên tham số kiểu** có thể dùng như kiểu trong field, parameter, return type hoặc các generic type lồng nhau trong phạm vi hợp lệ. **Đối số kiểu** cho biết cách một generic type cụ thể được sử dụng.

Một ví dụ đối chiếu thêm:

~~~java
static <T> java.util.List<T> singleton(T value) {
    return java.util.List.of(value);
}
~~~

Trong chữ ký trên, **<T>** là khai báo; **List<T>** là kiểu tham số hóa mà đối số là type variable T; **T value** dùng T làm kiểu của tham số giá trị. Việc T xuất hiện nhiều lần chính là cách biểu diễn rằng kiểu phần tử đầu ra phải liên hệ với kiểu của giá trị đầu vào.

## 13. Tên và thứ tự tham số kiểu: ghi nhớ để đọc cú pháp

Tên tham số kiểu là **quy ước giúp đọc vai trò**, không phải từ khóa của Java. Trong một danh sách `<...>`, mỗi tên được khai báo một lần; ở nơi sử dụng, các type arguments được gán **theo vị trí**. Ví dụ `Pair<String, Integer>` khác `Pair<Integer, String>` dù cùng sử dụng hai kiểu, và `Pair<String, String>` vẫn hợp lệ.

| Tên thường gặp | Vai trò gợi nhớ |
| --- | --- |
| `T` | Kiểu tổng quát |
| `E` | Phần tử của collection |
| `K`, `V` | Khóa và giá trị |
| `I`, `O` hoặc `R` | Đầu vào, đầu ra hoặc kết quả |
| `U`, `S` | Một kiểu khác với `T` khi cần phân biệt |

Tên `K`, `V` không tự áp đặt bound hay bắt hai kiểu phải khác nhau. Dùng **cùng một biến kiểu** khi cần ràng buộc những vị trí phải có cùng quan hệ kiểu; dùng nhiều tên khi các vị trí thực sự độc lập. Bài về quy ước tên phân tích chi tiết việc chọn ký hiệu ngắn hay tên mô tả, phạm vi và Javadoc; ở đây chỉ cần nắm cú pháp khai báo và thứ tự type arguments.

## 14. Những lỗi biên dịch thường gặp

### Quên dấu phẩy hoặc khai báo trùng tên

~~~java
// Ví dụ sai, chỉ minh họa:
class Bad<A B> {}       // Thiếu dấu phẩy
class Bad2<T, T> {}     // Khai báo trùng tên T
class Bad3<K, V,> {}    // Dấu phẩy thừa
~~~

Sửa thành **class Good<A, B> {}** hoặc những danh sách tên duy nhất khác.

### Viết tham số kiểu sai chỗ trong generic method

~~~java
// Sai: compiler chưa có khai báo T:
class Broken {
    // static T copy(T value) { return value; }
}

// Đúng:
class Correct {
    static <T> T copy(T value) {
        return value;
    }
}
~~~

Dấu **<T>** của method phải nằm trước kiểu trả về.

### Cho rằng type parameters là các giá trị runtime

~~~java
class Example<T> {
    // T = String;       // Sai: T không phải biến giá trị
    // T item = new T(); // Sai: không thể new trực tiếp một type variable
}
~~~

Type variable mô tả kiểu tĩnh, không giữ đối tượng Class<T> tại runtime. Khi cần tạo T, có thể truyền một Supplier<T> hoặc factory phù hợp; khi cần biết Class<T>, phải có tham chiếu Class<T> từ nguồn khác.

### Dùng raw type thay cho khai báo đầy đủ

~~~java
java.util.List<String> safe = new java.util.ArrayList<>();
java.util.List raw = safe; // Raw type: mất thông tin type argument
~~~

Dùng **List<String>** khi biết kiểu phần tử hoặc **List<?>** khi chưa biết. Raw type có thể dẫn đến unchecked operation và lỗi cast ở runtime.

### Truyền sai số lượng type arguments

~~~java
class Pair<A, B> {}

// Sai: Pair<String> chỉ cung cấp một đối số cho hai tham số.
// Đúng: Pair<String, Integer> hoặc Pair<String, String>.
~~~

Số đối số kiểu thông thường phải tương ứng số tham số được khai báo. **new Pair<>()** là cú pháp suy luận đối số kiểu ở lời gọi constructor; nó không biến Pair thành generic class chỉ có một tham số.

### Dùng primitive trực tiếp

~~~java
// List<int> bad; // Sai: int là primitive type
java.util.List<Integer> good = java.util.List.of(1, 2);
~~~

Generic type arguments cho kiểu tham chiếu; primitive thường dùng wrapper tương ứng (int → Integer, long → Long, boolean → Boolean). Mảng của primitive như **int[]** là reference type và có thể làm đối số kiểu, ví dụ List<int[]>.

### Nhầm extends và implements trong cận

~~~java
// Sai: class Bad<T implements Runnable> {}
// Đúng:
class Task<T extends Runnable> {
    private final T action;

    Task(T action) {
        this.action = action;
    }

    void run() {
        action.run();
    }
}
~~~

Dù Runnable là interface, generic bound vẫn dùng từ khóa **extends**.

### Cho rằng tham số kiểu hỗ trợ phép toán bất kỳ

~~~java
class Numbers<T extends Number> {
    T add(T a, T b) {
        // return a + b; // Sai: không có toán tử + tổng quát cho T
        throw new UnsupportedOperationException("Chưa định nghĩa phép cộng cho T");
    }
}
~~~

Cận **Number** bảo đảm các phương thức như doubleValue(), không làm toán tử **+** hoạt động trực tiếp trên type variable T. Nếu bài toán cần số học, phải lựa chọn phép chuyển đổi hoặc giao diện phép toán phù hợp.

### Nhầm thứ tự hai kiểu và kỳ vọng compiler tự đảo

~~~java
// Giả sử class Pair<K,V> và các accessor đã có:
Pair<String, Integer> source = new Pair<>("x", 1);
// Pair<Integer, String> wrong = source; // Sai: khác parameterized type.
~~~

Kiểu Pair<String, Integer> không tự động trở thành Pair<Integer, String> bởi tên K/V linh hoạt. Muốn đảo hai vị trí, cần tạo một giá trị mới với hai type arguments ở thứ tự tương ứng.

## 15. Kiểm tra nhanh kiến thức

**Câu 1:** Phần nào khai báo hai type parameters trong **class Pair<K, V>**? **Pair<String, Integer>** giữ vai trò gì?

**Đáp án:** **<K, V>** là danh sách khai báo hai tham số kiểu. Pair<String, Integer> là parameterized type, với String làm type argument cho K và Integer cho V.

**Câu 2:** Vì sao **class Pair<T, T>** không hợp lệ, nhưng **Pair<String, String>** lại hợp lệ?

**Đáp án:** Không được khai báo hai tham số kiểu trùng tên trong cùng một danh sách; hai vị trí type arguments của cách sử dụng thì có thể cùng là String.

**Câu 3:** Khác nhau giữa **class Holder<T> { T get() {...} }** và **static <T> T identity(T value)** là gì?

**Đáp án:** T của get() thuộc phạm vi class Holder<T>; method get không khai báo type parameter mới. Ngược lại identity là generic method tự khai báo T nên dùng được cả trong class không generic.

**Câu 4:** Trong **<T extends Number & Comparable<T>>**, có bao nhiêu tham số kiểu và bao nhiêu bound?

**Đáp án:** Một tham số kiểu T, có hai cận Number và Comparable<T>. Dấu **&** nối các cận, khác dấu phẩy giữa nhiều tham số kiểu.

**Câu 5:** Gọi phương thức **static <A, B> Pair<B, A> swap(Pair<A, B> input)** với Pair<String, Integer> thì kiểu kết quả là gì?

**Đáp án:** Pair<Integer, String>. Compiler suy luận A = String, B = Integer từ input, sau đó thay vị trí trong kiểu trả về Pair<B, A>.

**Câu 6:** **Converter<I, O>** nhận String và trả Integer thì khai báo biến ở vị trí sử dụng thế nào?

**Đáp án:** **Converter<String, Integer>**. I tương ứng String và O tương ứng Integer, theo đúng thứ tự khai báo.

## 16. Checklist trước khi hoàn thành một khai báo generic

Trước khi viết hoặc review một khai báo có dấu ngoặc góc, hãy tự hỏi:

1. Các kiểu có thực sự cần tùy biến không? Một T có đủ hay các vai trò K, V hoặc I, O cần độc lập?
2. Danh sách **<...>** đã đặt đúng vị trí theo class, interface, record, method hay constructor chưa?
3. Tên tham số có duy nhất trong danh sách và dễ hiểu không?
4. Type variable có được dùng trong phạm vi hợp lệ và thể hiện đúng quan hệ kiểu của các field, tham số, kết quả không?
5. Các bounds bằng extends đã đúng thứ tự và có thực sự cần không?
6. Tại nơi sử dụng, type arguments có đủ số lượng, đúng thứ tự và thỏa bound không?
7. Cú pháp dùng type argument, diamond, wildcard hay raw type đã được phân biệt với cú pháp **khai báo** chưa?

Điểm cốt lõi của cú pháp là **<T>** giới thiệu một tên kiểu dùng lại ở nhiều vị trí; **<K, V>** giới thiệu hai tên kiểu độc lập. Chính phạm vi và cách tái sử dụng các tên này quyết định compiler kiểm tra mối quan hệ giữa các giá trị trong chương trình.
