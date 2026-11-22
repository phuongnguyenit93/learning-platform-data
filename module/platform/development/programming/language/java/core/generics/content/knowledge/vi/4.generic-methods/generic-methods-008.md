# Thiết kế phương thức tạo đối tượng không phụ thuộc ép kiểu trong Java Generics

## 1. Mục tiêu và động cơ

Khi một API cần tạo đối tượng nhưng người gọi phải liên tục ép kiểu từ Object sang String, Integer hoặc kiểu nghiệp vụ, đó thường là dấu hiệu quan hệ kiểu giữa dữ liệu đầu vào và kết quả trả về chưa được mô tả rõ. **Generic factory method** (phương thức tạo đối tượng có tham số kiểu) cho phép chuyển quan hệ ấy thành hợp đồng do trình biên dịch kiểm tra.

So sánh cách thiết kế:

~~~java
// Thiết kế dựa vào Object, chỉ minh họa:
static Object oldBox(Object value) {
    return value;
}

// Tại nơi gọi:
String text = (String) oldBox("Java");
~~~

Ép kiểu trong ví dụ này có thể biên dịch nhưng nếu giá trị thực tế không tương thích, lỗi chỉ xuất hiện lúc chạy. Một generic method biểu diễn mối quan hệ “nhận T, trả T” trực tiếp:

~~~java
static <T> T identity(T value) {
    return value;
}

// Tại nơi gọi:
String text = identity("Java");
~~~

Trong thực tế, một factory thường tạo **một đối tượng mới có chứa T**, chẳng hạn Box<T>, Pair<K,V> hoặc một collection, thay vì đơn thuần trả lại đầu vào. Điểm chính là **kiểu kết quả được mô tả từ type parameters và các tham số đầu vào**, không đòi người gọi thực hiện cast thủ công.

Bài này hướng dẫn bạn:

- Viết cú pháp **static <T> Box<T> of(T value)** và phân biệt T của method với T của class.
- Dùng suy luận kiểu (*type inference*) và kiểu đích (*target typing*) để nhận kết quả có kiểu chính xác.
- Tạo các đối tượng generic chứa một hoặc nhiều type parameters bằng constructor và diamond operator.
- Thiết kế factory nhận **Supplier<? extends T>**, **Function<? super S, ? extends T>**, hoặc **Class<T>** khi không có sẵn một giá trị T.
- Phân biệt một API thật sự an toàn kiểu với cast bị giấu sau chữ ký generic.
- Xử lý bound, wildcard, null, bất biến của generics và lỗi runtime mà generics không thể tự ngăn.

Các ví dụ đầy đủ hướng đến Java 17 trở lên, có tên tệp, lệnh biên dịch/chạy và stdout xác định.

## 2. Generic factory method là gì?

Factory method là phương thức tạo hoặc cung cấp đối tượng theo một hợp đồng được công bố. Khi phương thức **tự khai báo một hay nhiều type parameters**, ta có generic factory method.

Ví dụ một class lưu giữ giá trị:

~~~java
final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

Đọc chữ ký **static <U> Box<U> of(U value)**:

1. **<U>** đứng trước kiểu trả về, khai báo một type parameter **của method of**.
2. **Box<U>** là kiểu kết quả: một Box được tham số hóa bằng U.
3. **U value** cho compiler biết giá trị đầu vào và type argument của Box có quan hệ cùng U.
4. **new Box<>(value)** gọi constructor đã biết của Box, dùng diamond để suy luận type argument. Nó **không** tạo một đối tượng của một lớp chưa biết tên U.
5. Constructor private giới hạn cách tạo Box từ ngoài class, khiến factory là điểm vào được kiểm soát.

Một lời gọi:

~~~java
// Minh họa bên trong phương thức:
Box<String> message = Box.of("hello");
Box<Integer> quantity = Box.of(12);
~~~

Compiler suy luận U từ các đối số và ngữ cảnh: message là Box<String>, quantity là Box<Integer>. **Không cần (Box<String>)** ở chỗ nhận kết quả.

Một chi tiết cú pháp: T là tham số kiểu của **class Box<T>**, trong khi U là tham số kiểu riêng của static method of. Static method không được dùng trực tiếp T thuộc class:

~~~java
// Sai trong một generic class:
static Box<T> of(T value) { ... }
~~~

Nếu T chỉ được khai báo bởi Box<T>, static method phải tự khai báo type parameter, như **static <U> Box<U> of(U value)**. Bạn có thể dùng lại tên T ở static method nếu muốn (**static <T> Box<T> of(T value)**); đó vẫn là T **riêng của method**, không phải T của class.

## 3. Tại sao cách trả Object rồi cast lại nguy hiểm?

Một API:

~~~java
static Object createValue(String text) {
    return text;
}
~~~

chỉ cam kết kết quả là Object. Caller phải viết **(String) createValue("x")**. Nếu implementation về sau trả Integer mà vẫn hợp chữ ký Object, cast ở caller có thể ném ClassCastException.

Một sai lầm tinh vi hơn là “ngụy trang” cast trong generic method:

~~~java
@SuppressWarnings("unchecked")
static <T> T unsafeCreate() {
    return (T) "actually a String";
}
~~~

Chữ ký trông generic, nhưng **không có đầu vào, bound hoặc factory chứng minh kết quả thuộc T**. Lời gọi **Integer number = unsafeCreate()** có thể biên dịch, rồi thất bại khi giá trị String được kiểm tra như Integer tại runtime. Phương thức đã chuyển một rủi ro unchecked từ caller vào implementation, **không tạo ra an toàn kiểu**.

Nguyên tắc thiết kế: một generic factory trả T hoặc một kiểu chứa T cần có **nguồn đảm bảo T**. Nguồn đó có thể là một tham số đã có kiểu T, một Supplier<? extends T>, một phép biến đổi Function<S,T>, một constructor đã biết của lớp generic chứa T, hoặc một Class<T> kết hợp kiểm tra/khởi tạo runtime thích hợp.

**Không thể suy ra và tạo một instance bất kỳ của T chỉ từ chữ ký <T> T create()**. Type parameter là ràng buộc ở source code, không phải một đối tượng Class mà JVM tự cung cấp cho phương thức.

## 4. Cú pháp chính xác và vai trò của type inference

Mẫu phổ biến:

~~~java
static <T> Box<T> box(T value) {
    return new Box<>(value);
}

static <K, V> Pair<K, V> pair(K key, V value) {
    return new Pair<>(key, value);
}
~~~

Những khai báo trên giả định Box<T> và Pair<K,V> đã được định nghĩa với constructor tương ứng. Chúng không phải một chương trình độc lập; chương trình hoàn chỉnh nằm ở mục tiếp theo.

Giải thích các vị trí dấu ngoặc góc:

| Biểu thức | Vai trò |
| --- | --- |
| **<T>** trước **Box<T>** | Khai báo type parameter cho method |
| **Box<T>** làm kiểu trả về | Dùng T làm type argument của Box |
| **T value** | Dùng type variable T làm kiểu của tham số giá trị |
| **new Box<>(value)** | Constructor invocation với diamond, suy luận đối số kiểu |
| **Box<String> b = box("x")** | Caller nhận một parameterized type với String |
| **Factory.<String>box("x")** | Caller chỉ định tường minh method type argument String |

Compiler xem chữ ký method, các đối số, bound và kiểu đích để suy luận T. Với **pair("lang", 21)**, kiểu suy luận thông thường là Pair<String, Integer>. Phép boxing chuyển literal int sang Integer khi cần type argument tham chiếu.

Cần phân biệt **generic factory method** và **constructor**. Constructor tên giống class, không khai báo kiểu trả về; static factory có tên riêng, một kiểu trả về và có thể chứa logic validate, cache, chọn implementation hoặc chuyển đổi trước khi trả đối tượng.

Không phải factory nào cũng cần generic: nếu một phương thức luôn tạo StringBuilder không mang quan hệ kiểu với input, **static StringBuilder createBuilder()** đơn giản đã đủ.

## 5. Ví dụ chạy độc lập: factory cho Box<T> và Pair<K,V>

Lưu tệp **GenericFactoryDemo.java**:

~~~java
public class GenericFactoryDemo {
    record Box<T>(T value) {}

    record Pair<K, V>(K key, V value) {}

    static <T> Box<T> box(T value) {
        return new Box<>(value);
    }

    static <K, V> Pair<K, V> pair(K key, V value) {
        return new Pair<>(key, value);
    }

    public static void main(String[] args) {
        Box<String> language = box("Java");
        Box<Integer> version = box(21);
        Pair<String, Integer> release = pair("jdk", 17);

        Box<Number> number = GenericFactoryDemo.<Number>box(3);

        System.out.println(language.value());
        System.out.println(version.value());
        System.out.println(release.key() + ":" + release.value());
        System.out.println(number.value());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 GenericFactoryDemo.java
java GenericFactoryDemo
~~~

Stdout chính xác:

~~~text
Java
21
jdk:17
3
~~~

Giải thích:

- **record Box<T>** là một generic record. Factory box(T) tạo Box<T> mà không cần cast.
- **pair(K,V)** kết nối chính xác hai type arguments độc lập vào Pair<K,V>; type arguments của result không bị ép thành Object.
- **Box<String> language** khiến chương trình gọi value() nhận String tĩnh; **Box<Integer> version** nhận Integer.
- **GenericFactoryDemo.<Number>box(3)** cung cấp **explicit type witness**: T được chọn là Number, 3 được boxing thành Integer và gán cho Number. Dữ liệu thực tế bên trong vẫn là một Integer, nhưng kiểu result được công bố là Box<Number>.
- Nếu bỏ type witness, **Box<Number> number = box(3)** cũng là một ví dụ mà compiler có thể suy luận kiểu phù hợp nhờ ngữ cảnh gán. Type witness có ích khi muốn chỉ rõ một lựa chọn kiểu mà không dựa hoàn toàn vào suy luận.

Tại đây, tên record và method chỉ phục vụ ví dụ. Một API có thể chọn những tên dễ hiểu hơn như **of**, **from**, **create**, **empty**, **copyOf** hoặc **parse**, tùy ngữ nghĩa từng factory.

## 6. Dùng phương thức tĩnh để tạo một instance của generic class

Một cách thường dùng là đặt method factory ngay trong class:

~~~java
final class Envelope<T> {
    private final T content;

    private Envelope(T content) {
        this.content = content;
    }

    public T content() {
        return content;
    }

    public static <U> Envelope<U> of(U content) {
        return new Envelope<>(content);
    }
}
~~~

Caller có thể viết:

~~~java
// Minh họa trong thân phương thức:
Envelope<String> text = Envelope.of("hello");
Envelope<Integer> count = Envelope.of(8);
~~~

Đây là **static generic factory method**. Nó tránh cần gọi **new Envelope<String>(...)** trực tiếp, giữ nơi khởi tạo tập trung, đồng thời có thể kiểm tra dữ liệu:

~~~java
public static <U> Envelope<U> nonNull(U content) {
    return new Envelope<>(java.util.Objects.requireNonNull(content, "content"));
}
~~~

Phiên bản nonNull chỉ khác về hợp đồng null. Nó vẫn không cast hoặc đánh mất U. **Objects.requireNonNull** có overload generic giữ nguyên kiểu tĩnh của tham số.

Nếu muốn cho phép null, factory **ofNullable** có thể được đặt tên và thiết kế riêng; tuy nhiên không được suy ra chỉ từ tên rằng kết quả của mọi factory là Optional<T>. Một factory trả chính Envelope<U> thì tên, return type và hợp đồng phải nhất quán.

Khi constructor cần kiểm soát chặt tính hợp lệ hoặc cách chọn implementation, static factory thường hữu ích hơn chỉ expose constructor. Tuy vậy, factory không tự làm mọi object bất biến hoặc thread-safe; những đặc tính đó phụ thuộc cấu trúc đối tượng, field và implementation.

## 7. Nhiều tham số kiểu: từ dữ liệu đầu vào đến đối tượng kết quả

Generic factory có thể khai báo nhiều type parameters để biểu diễn nhiều vai trò:

~~~java
record Entry<K, V>(K key, V value) {}

static <K, V> Entry<K, V> entry(K key, V value) {
    return new Entry<>(key, value);
}
~~~

Caller:

~~~java
// Minh họa:
Entry<String, Integer> e = entry("age", 20);
Entry<Long, String> other = entry(5L, "value");
~~~

K và V được suy luận riêng. Với e, K là String và V là Integer; với other, K là Long, V là String. Không cần cast ở phương thức trả về hay caller.

Có thể sử dụng type parameters đầu vào/đầu ra:

~~~java
static <I, O> O convert(I input,
                         java.util.function.Function<? super I, ? extends O> mapper) {
    return mapper.apply(input);
}
~~~

**Function<? super I, ? extends O>** cho phép bộ biến đổi nhận được I hoặc một kiểu rộng hơn I, và trả được O hoặc một subtype của O. Đây là dạng variance hữu ích để factory/chuyển đổi không ép caller viết lambda chỉ đúng một kiểu tuyệt đối.

Trong một lời gọi:

~~~java
// Minh họa trong phương thức:
Integer length = convert("Java", String::length);
~~~

Compiler suy luận I = String, O phù hợp với Integer; String::length trả int và được boxing thành Integer trong Function.

Khi thiết kế, hãy tự hỏi **mỗi type parameter xuất hiện tại đâu**. Nếu method tự khai báo <T> nhưng T không kết nối được với bất kỳ tham số đầu vào, kiểu đích hay nguồn tạo thực tế, đó là dấu hiệu chữ ký có thể tạo cảm giác an toàn giả.

## 8. Dùng Supplier khi factory phải tự tạo T mà không có sẵn giá trị T

Có những lúc caller muốn method tạo một đối tượng mới thay vì đóng gói đối tượng có sẵn. Java không cho phép viết **new T()** với type variable T vì thông tin constructor cụ thể không thể suy ra từ T tại runtime. Thay vào đó, caller cung cấp một **Supplier** tạo object.

~~~java
static <T> T create(java.util.function.Supplier<? extends T> supplier) {
    return supplier.get();
}
~~~

Từ bên trong, compiler biết **supplier.get()** trả một kiểu là T hoặc subtype của T nên gán được cho T. Người dùng có thể truyền constructor reference:

~~~java
// Minh họa:
StringBuilder builder = create(StringBuilder::new);
~~~

Không có cast. Static type của kết quả được xác lập qua Supplier và ngữ cảnh kiểu đích. Cách tiếp cận này cũng tránh phải yêu cầu mọi T có public no-arg constructor.

Bạn có thể thêm các điều kiện runtime:

~~~java
static <T> T createNonNull(
        java.util.function.Supplier<? extends T> supplier) {
    java.util.Objects.requireNonNull(supplier, "supplier");
    return java.util.Objects.requireNonNull(supplier.get(), "created object");
}
~~~

Factory ở đây bảo đảm khác null **sau khi hàm thành công**; nó không bảo đảm constructor reference/lambda không ném exception, không tạo object mới cho mỗi lần gọi, hoặc không có tác dụng phụ. Những điều đó phụ thuộc Supplier do caller cung cấp.

## 9. Ví dụ chạy độc lập: Supplier và Function

Lưu thành **SupplierFactoryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    interface Animal {
        String sound();
    }

    static final class Dog implements Animal {
        @Override
        public String sound() {
            return "woof";
        }
    }

    static <T> T create(Supplier<? extends T> supplier) {
        Objects.requireNonNull(supplier, "supplier");
        return Objects.requireNonNull(supplier.get(), "result");
    }

    static <T> List<T> createMany(int count, Supplier<? extends T> supplier) {
        if (count < 0) {
            throw new IllegalArgumentException("Negative count");
        }
        List<T> result = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            result.add(create(supplier));
        }
        return result;
    }

    static <S, T> T convert(S source,
                            Function<? super S, ? extends T> mapper) {
        return Objects.requireNonNull(mapper, "mapper").apply(source);
    }

    public static void main(String[] args) {
        Animal first = create(Dog::new);
        List<Animal> group = createMany(2, Dog::new);
        Integer length = convert("Java", String::length);

        System.out.println(first.sound());
        System.out.println(group.size());
        System.out.println(group.get(0).sound());
        System.out.println(length);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SupplierFactoryDemo.java
java SupplierFactoryDemo
~~~

Stdout:

~~~text
woof
2
woof
4
~~~

Những điểm cần quan sát:

1. **Dog::new** là constructor reference; nó cung cấp cách tạo Dog. Method create không biết hoặc yêu cầu new T().
2. **Animal first** được gán từ một factory dùng Supplier<Dog>. Generic bound **? extends T** cho phép kết quả là subtype của kiểu đích.
3. **List<Animal> group = createMany(2, Dog::new)** giữ kiểu phần tử công bố là Animal dù object được tạo là Dog.
4. **convert("Java", String::length)** gắn kiểu nguồn String và kiểu kết quả Integer; không cần **(Integer)** hoặc **(String)** tại chỗ chuyển đổi.
5. createMany() từ chối số lượng âm; phần kiểm tra này thuộc contract factory, không do generics quyết định.
6. Supplier có thể trả null; create kiểm tra và từ chối trường hợp đó. Function trong convert thì không kiểm tra giá trị kết quả là null, nên method chỉ cam kết về kiểu tĩnh chứ không mặc nhiên cam kết non-null.

Để có một sản phẩm API hoàn chỉnh, cần xác định rõ factory tạo mới mỗi lần hay được phép tái sử dụng, null được chấp nhận hay không, và checked/unchecked exceptions có thể thoát ra theo đường nào.

## 10. Dùng Class<T> khi cần tạo hoặc kiểm tra kiểu tại runtime

Có tình huống cần biết class cụ thể để khởi tạo hoặc xác minh một Object. **Class<T>** là một *type token* có quan hệ generic với T.

Trường hợp cần kiểm tra một Object có đúng kiểu mong muốn:

~~~java
static <T> T checked(Object source, Class<T> type) {
    return type.cast(source);
}
~~~

**Class.cast** thực hiện kiểm tra cast ở runtime dựa trên class token. Caller:

~~~java
// Minh họa:
String label = checked("Java", String.class);
Integer answer = checked(42, Integer.class);
~~~

Ở đây không có cast tại caller và cũng không có unchecked cast trong method. Nếu source không là instance tương thích, **type.cast(source)** ném ClassCastException. Lưu ý **Class.cast(null)** trả null; nó không phải kiểm tra non-null.

Một dạng cần tạo đối tượng qua reflection:

~~~java
static <T> T construct(Class<T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
~~~

Phương thức dùng Class<T> để tìm constructor không tham số và gọi nó. Nó chỉ hoạt động nếu constructor phù hợp có thể truy cập trong bối cảnh runtime; không phải mọi T đều có no-arg constructor. Reflection có thể ném các exception liên quan đến constructor, truy cập hoặc khởi tạo. Trường hợp đơn giản có constructor cụ thể, **Supplier<T>** thường rõ ràng và dễ kiểm thử hơn reflection.

**Class<T> không khôi phục đầy đủ type arguments lồng nhau**: ở runtime, **List<String>** và **List<Integer>** có thể là cùng class ArrayList. Không có class literal **List<String>.class**. Nếu cần mô tả type phức tạp ở runtime, phải dùng cơ chế type token/Type chuyên dụng và quy trình kiểm tra phù hợp, nằm ngoài bảo đảm đơn thuần của Class<T>.

## 11. Ví dụ chạy độc lập: type token và tạo đối tượng không cast

Lưu thành **ClassTokenFactoryDemo.java**:

~~~java
public class ClassTokenFactoryDemo {
    static <T> T checked(Object value, Class<T> type) {
        return type.cast(value);
    }

    static <T> T construct(Class<T> type)
            throws ReflectiveOperationException {
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        String language = checked("Java", String.class);
        System.out.println(language);

        try {
            Integer invalid = checked("not an integer", Integer.class);
            System.out.println(invalid);
        } catch (ClassCastException exception) {
            System.out.println("type mismatch");
        }

        StringBuilder builder = construct(StringBuilder.class);
        builder.append("created");
        System.out.println(builder);
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ClassTokenFactoryDemo.java
java ClassTokenFactoryDemo
~~~

Stdout:

~~~text
Java
type mismatch
created
~~~

Giải thích:

- **checked("Java", String.class)** trả String; quan hệ giữa Class<String> và return type T được compiler kiểm tra.
- **checked("not an integer", Integer.class)** biên dịch nhưng Class.cast phát hiện type mismatch lúc chạy. Chương trình bắt ClassCastException và in một thông báo cố định.
- **construct(StringBuilder.class)** hoạt động vì StringBuilder có constructor không tham số thích hợp; return type StringBuilder được suy ra từ Class<StringBuilder>.
- Reflection có thể không phù hợp nếu class abstract, interface, không có no-arg constructor, constructor không thể truy cập, hoặc constructor ném exception. Đây không phải factory tạo “mọi T” một cách thần kỳ.

Type token hữu ích khi dữ liệu đầu vào ban đầu chỉ có kiểu Object (ví dụ hệ thống plugin, parser runtime, tích hợp reflection) và cần kiểm tra an toàn. Với dữ liệu đã có generic type đầy đủ ở compile time, nên ưu tiên giữ quan hệ kiểu từ đầu hơn là chuyển thành Object rồi kiểm tra lại.

## 12. Phân biệt factory trả T và factory trả Container<T>

Hai chữ ký trông giống nhau nhưng có khả năng khác nhau:

~~~java
static <T> T create(Supplier<? extends T> supplier) {
    return supplier.get();
}

static <T> Box<T> wrap(T value) {
    return new Box<>(value);
}
~~~

**create** yêu cầu có một nguồn tạo ra chính T (Supplier). Nó không thể tự new T() chỉ từ chữ ký. **wrap** có thể dùng new Box<>(...) vì class Box là một kiểu đã được biết, có constructor tương ứng; T chỉ quyết định *kiểu phần tử bên trong Box*.

Một sai lầm dễ gặp:

~~~java
// Cố ý sai, không biên dịch:
static <T> T impossible() {
    // return new T();
    return null;
}
~~~

Dòng return null sẽ biên dịch, nhưng không phải một factory hữu ích và không tạo đối tượng. Phần **new T()** bị comment vì Java không cho phép khởi tạo type variable trực tiếp. Câu hỏi thiết kế thực sự là *nguồn nào bảo đảm giá trị trả về đúng T?*

Generic factory cũng có thể trả interface của một implementation cụ thể:

~~~java
interface Repository<ID, E> {
    E find(ID id);
}

class MapRepository<ID, E> implements Repository<ID, E> {
    private final java.util.Map<ID, E> values;

    MapRepository(java.util.Map<ID, E> values) {
        this.values = values;
    }

    @Override
    public E find(ID id) {
        return values.get(id);
    }
}

class RepositoryFactory {
    static <ID, E> Repository<ID, E> fromMap(
            java.util.Map<ID, E> data) {
        return new MapRepository<>(data);
    }
}
~~~

Factory công bố **Repository<ID,E>** thay vì class cụ thể **MapRepository<ID,E>**. Caller có thể lập trình theo interface với đúng type arguments, không cần cast giữa implementation và interface. Lưu ý Map.get có thể trả null khi không thấy key, nên quan hệ kiểu an toàn không đồng nghĩa với non-null.

## 13. Target typing và gọi method bằng đối số kiểu tường minh

Thông thường compiler suy luận type arguments từ method arguments và kiểu đích:

~~~java
static <T> java.util.List<T> one(T element) {
    return java.util.List.of(element);
}
~~~

Trong một phương thức:

~~~java
java.util.List<String> names = one("An");
java.util.List<Number> amounts = one(3);
~~~

Compiler có thể dùng cả kiểu của expression đầu vào và kiểu đích List<Number> để chọn T phù hợp. Điều này không có nghĩa runtime đã thay đổi kiểu thực của số 3: boxing tạo Integer và value đó có thể được xem như Number.

Khi muốn thể hiện type argument rõ ràng, dùng **explicit method type argument** sau dấu chấm:

~~~java
java.util.List<Number> amounts = SomeFactories.<Number>one(3);
~~~

Đoạn trên là minh họa với giả định method **one** có thể truy cập trong class SomeFactories. Cách ghi **<Number>** không khai báo tham số mới; nó chỉ chọn T tại điểm gọi.

### Khi dùng var

~~~java
var words = java.util.List.of("A", "B");
var numbers = java.util.List.of(1, 2);
~~~

Compiler suy luận kiểu tĩnh từ initializer. Trong ví dụ này, words là List<String>, numbers là List<Integer>. Không vì dùng var mà bỏ qua generic type safety.

Với factory không có tham số cung cấp kiểu, cần chú ý ngữ cảnh:

~~~java
static <T> java.util.List<T> emptyMutableList() {
    return new java.util.ArrayList<>();
}
~~~

Các cách dùng:

~~~java
java.util.List<String> names = emptyMutableList();
var unknown = emptyMutableList();
~~~

Ở lần đầu, kiểu đích giúp suy luận T là String. Ở lần dùng var, nếu không có ràng buộc đầu vào/đích khác, compiler thường suy luận upper bound Object cho T, nên unknown có kiểu List<Object>. Đây là lý do target typing có thể làm khác kết quả suy luận; API cần được đọc cùng ngữ cảnh.

Đừng cố khắc phục một API có quan hệ kiểu sai bằng cast: nếu caller phải ép **(List<String>)**, hãy kiểm tra trước liệu chữ ký generic đã cung cấp đúng liên hệ giữa đầu vào và đầu ra hay chưa.

## 14. Factory tạo collection: giữ kiểu phần tử và xử lý variance

Factory sao chép collection là ví dụ thực tế của method dùng type parameter T và wildcard.

~~~java
static <T> java.util.List<T> mutableCopy(
        java.util.Collection<? extends T> source) {
    return new java.util.ArrayList<>(source);
}
~~~

**Collection<? extends T>** cho phép đọc các phần tử thuộc T hoặc subtype của T. Ví dụ source là List<Integer>, caller có thể yêu cầu kết quả List<Number>. **ArrayList<>(source)** có constructor nhận collection tương thích và tạo một danh sách mới.

Nếu method nhận **Collection<T>** thay cho **Collection<? extends T>**, nó có thể kém linh hoạt khi muốn chuyển các phần tử subtype thành collection của supertype. Mặc dù Integer extends Number, **List<Integer> không phải List<Number>** do invariant generics.

Đối với một bản sao không cho phép sửa cấu trúc, có thể dùng **List.copyOf**:

~~~java
static <T> java.util.List<T> immutableCopy(
        java.util.Collection<? extends T> source) {
    return java.util.List.copyOf(source);
}
~~~

**List.copyOf** tạo hoặc tái sử dụng một unmodifiable list phù hợp; nó từ chối phần tử null. Nếu cần bảo đảm snapshot độc lập với sự thay đổi của nguồn, hãy xem hợp đồng cụ thể của factory và đối tượng nguồn, thay vì chỉ suy đoán từ tên "copy". Unmodifiable không có nghĩa các object phần tử bên trong trở nên immutable.

## 15. Ví dụ chạy độc lập: copy collection an toàn kiểu

Lưu thành **CollectionFactoryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionFactoryDemo {
    static <T> List<T> mutableCopy(Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T> List<T> immutableCopy(Collection<? extends T> source) {
        return List.copyOf(source);
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2);
        List<Number> numbers = mutableCopy(source);
        numbers.add(3.5);

        List<Number> fixed = immutableCopy(source);

        System.out.println(numbers);
        System.out.println(fixed);
        System.out.println(source);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CollectionFactoryDemo.java
java CollectionFactoryDemo
~~~

Stdout:

~~~text
[1, 2, 3.5]
[1, 2]
[1, 2]
~~~

**Điểm cần kiểm tra:** source có kiểu List<Integer> nhưng cả mutableCopy và immutableCopy có thể trả List<Number> nhờ chữ ký generic và ngữ cảnh gán. Không có cast không kiểm tra. **numbers.add(3.5)** hợp lệ vì numbers được công bố là List<Number>; source vẫn chỉ chứa 1, 2. Danh sách fixed do List.copyOf tạo không cho thêm phần tử, dù nó cũng có kiểu tĩnh List<Number>.

### Null và collection factory

**new ArrayList<>(source)** chấp nhận phần tử null nếu collection nguồn chứa null; nhưng **List.copyOf(source)** ném NullPointerException khi nguồn null hoặc có phần tử null. Đừng giả định mọi factory generic có cùng chính sách null. Tên method, hợp đồng và tài liệu API cần nêu rõ.

**Collections.emptyList()** và **List.of()** là các ví dụ factory generic tiêu chuẩn trả collection rỗng. Chúng có thể suy luận kiểu phần tử từ kiểu đích:

~~~java
java.util.List<String> emptyA = java.util.Collections.emptyList();
java.util.List<Integer> emptyB = java.util.List.of();
~~~

Cả hai hợp lệ mà không cần cast. Tuy nhiên, list do List.of trả về không cho sửa cấu trúc, nên phải chọn factory theo yêu cầu mutability.

## 16. Factory có bounds: giới hạn kiểu đầu vào đúng nhu cầu

Một factory đôi khi cần API cụ thể trên T. Nếu method chỉ chuyển một giá trị T vào Box<T>, thường không cần bound. Nếu cần dùng Number.doubleValue() hoặc Comparable.compareTo(), khai báo bound:

~~~java
record Measured<T extends Number>(T original, double amount) {}

static <T extends Number> Measured<T> measured(T number) {
    return new Measured<>(number, number.doubleValue());
}
~~~

Với **measured(12)**, T được suy luận Integer và result là Measured<Integer>. **measured("12")** không hợp lệ vì String không phải subtype của Number.

Nhiều bounds:

~~~java
static <T extends Number & Comparable<T>> T greater(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

Dấu **&** nối class bound Number với interface bound Comparable<T>; compiler cho phép gọi compareTo, điều mà unbounded T không bảo đảm.

Khi method muốn so sánh theo nhiều chiến lược, có thể **nhận Comparator<? super T>** thay vì buộc T implements Comparable<T>:

~~~java
static <T> T choose(
        T left, T right, java.util.Comparator<? super T> comparator) {
    return comparator.compare(left, right) >= 0 ? left : right;
}
~~~

Comparator cung cấp logic so sánh qua một đối số rõ ràng. Điều này giúp factory/selection method hoạt động với kiểu không có natural ordering. Nhờ type parameter T, kết quả vẫn giữ liên hệ với kiểu các đối số được chọn, không cần cast.

### Bounds trong factory trả interface

Một factory có thể che implementation nhưng vẫn giữ bounds:

~~~java
interface SortedHolder<T> {
    T greatest();
}

class SingleSortedHolder<T extends Comparable<? super T>>
        implements SortedHolder<T> {
    private final T value;

    SingleSortedHolder(T value) {
        this.value = value;
    }

    @Override
    public T greatest() {
        return value;
    }
}

class SortedHolders {
    static <T extends Comparable<? super T>> SortedHolder<T> of(T value) {
        return new SingleSortedHolder<>(value);
    }
}
~~~

Bound của method đủ để constructor/class implementation có thể được áp dụng đúng T. Trả **SortedHolder<T>** giúp caller phụ thuộc vào hợp đồng interface. Với giá trị null, code vẫn có thể tạo holder nếu constructor cho phép; Comparable bound không tự cấm null.

## 17. API thiết kế đúng không có unchecked cast

Một phương thức generic giữ quan hệ kiểu tốt nhất khi **phần thân cũng có bằng chứng kiểu** từ compiler. Các ví dụ:

~~~java
static <T> java.util.Optional<T> optional(T value) {
    return java.util.Optional.ofNullable(value);
}

static <T> java.util.List<T> singleton(T value) {
    return java.util.List.of(value);
}

static <K, V> java.util.Map<K, V> singletonMap(K key, V value) {
    return java.util.Map.of(key, value);
}
~~~

Các phương thức đều không có **(T)** hoặc **@SuppressWarnings("unchecked")**. Compiler biết:

- **Optional.ofNullable** trả Optional<T> theo giá trị đầu vào; nhận null thì trả Optional.empty().
- **List.of(value)** trả một danh sách một phần tử với type argument tương ứng, nhưng **không chấp nhận null**.
- **Map.of(key, value)** trả map bất biến về cấu trúc với type arguments K,V; key/value null bị từ chối.

Điều quan trọng là không phải factory nào cũng chấp nhận null như nhau. Cần nêu rõ contract ngay khi đặt tên và chọn implementation.

Phương thức sau vẫn thiếu bằng chứng kiểu:

~~~java
// Chống chỉ định; chỉ minh họa:
@SuppressWarnings("unchecked")
static <T> java.util.List<T> unsoundList() {
    return (java.util.List<T>) (java.util.List<?>) java.util.List.of("A");
}
~~~

Nếu caller gán sang List<Integer>, dữ liệu String bên trong có thể gây ClassCastException khi lấy phần tử dưới kiểu Integer. Phương thức đã giấu unchecked cast, không thực hiện chuyển đổi String thành Integer.

Một cast có kiểm tra runtime như **Class<T>.cast** là trường hợp khác: nó dùng class token để xác minh tính tương thích tại runtime và ném exception nếu không hợp lệ. Tuy nhiên Class<T> không đủ để kiểm tra mọi parameterized type lồng nhau do erasure.

## 18. Một ví dụ nghiệp vụ: factory tạo response có kiểu

Giả sử ứng dụng cần gói dữ liệu và trạng thái thành một kết quả chung. Một generic record là lựa chọn cô đọng:

~~~java
record Response<T>(boolean success, T data, String message) {}

class Responses {
    static <T> Response<T> success(T data) {
        return new Response<>(true, data, "OK");
    }

    static <T> Response<T> failure(String message) {
        return new Response<>(false, null, message);
    }
}
~~~

Với success(data), compiler suy luận T từ data. Với failure(message), không có đầu vào T nên **kiểu đích** hoặc type witness có vai trò quan trọng:

~~~java
// Minh họa trong phương thức:
Response<String> one = Responses.success("saved");
Response<String> two = Responses.failure("not found");
Response<Integer> three = Responses.<Integer>failure("invalid");
~~~

Chữ ký **failure(String message)** có thể trả Response<T> với data = null, vì null gán được cho kiểu tham chiếu T. Nó **không tự tạo một T**, và contract cần nêu rõ dữ liệu vắng mặt khi success = false. API như vậy thể hiện quan hệ kiểu ở kết quả mà không cần caller ép cast.

Một vấn đề thiết kế là cho phép **success(null)** không. Nếu success có ý nghĩa “có dữ liệu”, có thể dùng Objects.requireNonNull(data) khi tạo Response. Nếu null là trạng thái hợp lệ, cần biểu diễn rõ điều kiện và tránh đồng nhất null với lỗi. Generics không quyết định chính sách nghiệp vụ này.

## 19. Suy luận kiểu không thay thế kiểm tra thiết kế API

Một factory có thể biên dịch nhưng vẫn gây hiểu nhầm:

~~~java
static <T> T fallback(T preferred, T alternative) {
    return preferred != null ? preferred : alternative;
}
~~~

Phương thức có type parameter T liên hệ hai đối số với kiểu trả về. Nhưng caller có thể truyền **String** và **Integer**, khiến compiler suy luận một supertype chung. Khi đó kiểu kết quả không nhất thiết là kiểu cụ thể mà người viết mong đợi.

Ví dụ an toàn:

~~~java
String name = fallback(null, "anonymous");
~~~

Ví dụ cần xem lại ý đồ:

~~~java
Object mixed = fallback("text", 123);
~~~

Java có thể chọn một kiểu chung phù hợp để kết quả gán được vào Object. Đây không phải vi phạm an toàn kiểu; nó chỉ cho thấy **generic method không bảo đảm hai tham số runtime có cùng class**. Nếu nghiệp vụ yêu cầu cùng loại chặt chẽ hơn, cần thiết kế hợp đồng/đầu vào phù hợp và có thể thêm kiểm tra ở ranh giới.

Cũng không nên mặc định rằng viết **var result = factory(...)** luôn cho kiểu mong muốn. Kiểu suy luận phụ thuộc vào initializer; ở những factory chỉ có return-type T mà không có thông tin đầu vào, kiểu đích tường minh có thể làm kết quả rõ ràng hơn.

## 20. Null, exception và mutability trong phương thức tạo đối tượng

**An toàn kiểu** và **chính sách runtime** là hai chiều độc lập. Một generic factory có thể trả đúng Box<String> nhưng vẫn chứa null; một List<Integer> được tạo đúng kiểu có thể không cho phép add; Supplier<T> có thể ném exception.

Nên quyết định rõ những hợp đồng sau khi thiết kế:

| Câu hỏi | Hướng xử lý |
| --- | --- |
| Đầu vào null có hợp lệ? | Dùng requireNonNull hoặc cho phép và ghi rõ |
| Factory có thể trả null? | Cân nhắc tránh null hoặc công bố rõ; Optional khi phù hợp |
| Tạo object mới mỗi lần? | Mô tả nếu là yêu cầu; factory có thể cache hoặc tái sử dụng |
| Constructor có tác dụng phụ? | Supplier và reflection có thể chạy logic constructor |
| Kết quả có mutable? | Xác định qua kiểu/implementation, không qua T |
| Có lỗi checked khi reflection? | Khai báo/thực thi xử lý ReflectiveOperationException phù hợp |
| Có cần kiểm tra kiểu runtime? | Class<T>.cast khi kiểm tra class cụ thể; hiểu giới hạn erasure |
| Kiểu nào được trả ra? | Chữ ký nên giữ type parameters có quan hệ với input/result |

Ví dụ API nhận Supplier nhưng muốn cấm kết quả null:

~~~java
static <T> T newRequired(java.util.function.Supplier<? extends T> factory) {
    java.util.Objects.requireNonNull(factory, "factory");
    return java.util.Objects.requireNonNull(factory.get(), "factory returned null");
}
~~~

Nếu factory.get() tạo một object hợp lệ, return type giữ T; nếu trả null, method ném NPE với thông báo đã khai báo. Đây là một bảo đảm do code thực thi, không phải tính chất tự phát của cú pháp <T>.

Với Optional.ofNullable, null được mã hóa thành Optional.empty() thay vì throw. Hai cách có contract khác nhau; không có một quy tắc áp dụng cho mọi factory.

## 21. Cách đọc và tự xây dựng một generic factory method

Khi gặp yêu cầu “tạo object nhưng không ép kiểu”, hãy làm theo trình tự:

1. **Xác định kết quả cần tạo.** Đó là chính T, một Box<T>, một List<T>, Pair<K,V>, một interface Repository<K,V> hay một response có kiểu?
2. **Tìm nguồn đảm bảo type arguments.** Giá trị đầu vào T, Supplier<T>, Function<S,T>, collection nguồn, type token Class<T>, hoặc implementation có sẵn?
3. **Khai báo type parameters đúng vị trí.** Với static method: **static <T> ReturnType method(...)**. Nếu nhiều quan hệ kiểu độc lập, khai báo <K,V> hoặc <S,T>.
4. **Gắn type variables vào chữ ký đầu vào và kết quả.** Ví dụ <T> Box<T> of(T value) hay <S,T> T map(S source, Function<? super S, ? extends T> mapper).
5. **Viết implementation mà compiler tự chứng minh được kiểu.** Dùng new Box<>(value), supplier.get(), function.apply(), Class.cast... Tránh unchecked cast hay raw type.
6. **Thử lời gọi qua kiểu đích cụ thể.** Gán sang Box<String>, Box<Integer>, List<Number>... và xem compiler kiểm tra được không.
7. **Quy định chính sách runtime.** Null, mutability, số lượng object được tạo, exception và giới hạn reflection.
8. **Chỉ rõ đối số kiểu khi cần.** Dùng TypeName.<T>method(...) hoặc biến đích tường minh nếu suy luận không biểu đạt ý định.

Một chữ ký nên khiến người đọc nhận ra điều gì được bảo đảm. Ví dụ **<T> Box<T> of(T value)** nói trực tiếp rằng Box mang cùng kiểu với value. **<T> T create()** không có nguồn T chỉ nên xuất hiện khi implementation có một cơ chế thực sự bảo đảm kiểu trả ra; nếu thiếu, hãy thêm Supplier hoặc Class token thích hợp.

## 22. Những lỗi thường gặp

### Lỗi 1 — Quên khai báo <T> ở static factory

~~~java
class BadBox<T> {
    // Sai: static method không được dùng trực tiếp T của class.
    // static BadBox<T> of(T value) { return new BadBox<>(); }
}
~~~

Sửa thành **static <U> BadBox<U> of(U value)** với constructor đúng chữ ký. T của class không thuộc phạm vi dùng được của static context theo cách đó.

### Lỗi 2 — Tin rằng return type T cho phép new T()

~~~java
// Sai, chỉ minh họa:
static <T> T create() {
    // return new T();
    return null;
}
~~~

Type erasure khiến T không cung cấp constructor cụ thể. Dùng Supplier<? extends T> hoặc Class<T> kèm reflection có điều kiện, tùy contract.

### Lỗi 3 — Giấu cast bằng @SuppressWarnings("unchecked")

~~~java
@SuppressWarnings("unchecked")
static <T> T misleading(Object value) {
    return (T) value;
}
~~~

Đây chỉ là cast không được compiler xác minh. Caller vẫn có thể yêu cầu T không phù hợp với object, dẫn đến runtime failure. Nếu kiểu đích cần kiểm tra, nhận **Class<T>** và dùng **type.cast(value)**.

### Lỗi 4 — Trả Object thay vì giữ type parameter

~~~java
static Object wrap(Object input) {
    return input;
}
~~~

Phương thức này làm mất type relationship cần thiết cho caller. Nếu yêu cầu giữ kiểu đầu vào làm kiểu trả về, dùng **static <T> T identity(T input)** hoặc một container có **<T> Box<T> of(T input)**.

### Lỗi 5 — Dùng raw type ở bên trong factory

~~~java
// Không khuyến khích:
static <T> java.util.List<T> broken() {
    java.util.List raw = new java.util.ArrayList();
    // return raw; // Unchecked conversion.
    return new java.util.ArrayList<>();
}
~~~

Raw type làm giảm type safety. Hãy khai báo trực tiếp **List<T> result = new ArrayList<>()**, hoặc tạo và trả new ArrayList<T>() với đúng quan hệ kiểu.

### Lỗi 6 — Đồng nhất generic type với tính thay đổi được của collection

**List<T>** chỉ nói kiểu phần tử. **List.of(...)** trả unmodifiable list; **new ArrayList<>(...)** trả mutable list. Factory phải chọn đúng implementation theo nhu cầu, không dựa riêng vào ký hiệu T.

### Lỗi 7 — Quên kiểm tra null

**List.of(value)**, **Map.of(key,value)** và **List.copyOf(source)** có thể ném NPE với null theo hợp đồng. Trong khi **Optional.ofNullable(value)** cố ý chấp nhận null. Caller không thể suy ra chính sách null chỉ bằng type parameter T.

### Lỗi 8 — Nhầm Class<T> với khả năng xác minh mọi kiểu lồng nhau

**Class<List<String>>** không có class literal tương ứng; thông thường chỉ có **List.class** mang thông tin raw class. Class<T>.cast kiểm tra class runtime, không tự xác nhận kiểu phần tử String của một List tùy ý.

### Lỗi 9 — Viết wildcard ở vị trí tham số kiểu chưa có nguồn xác định

Wildcard dùng tại nơi sử dụng các kiểu generic, ví dụ **List<? extends Number>**, và có quy tắc đọc/ghi riêng. Không khai báo method như **static <?> ...** để thay cho **static <T> ...**. Muốn đặt tên mối quan hệ giữa input và result, hãy khai báo type parameter T.

### Lỗi 10 — Lạm dụng một T cho hai vai trò không liên quan

Nếu factory nhận kiểu nguồn S và trả kiểu đích T sau phép biến đổi, dùng **<S,T>** thường rõ hơn một T ép hai phía cùng kiểu. Ví dụ **<S,T> T convert(S value, Function<? super S, ? extends T> mapper)** diễn đạt đúng chuyển đổi khác kiểu.

## 23. Tự kiểm tra

**Câu 1.** Trong **static <T> Box<T> of(T value)**, <T> đầu tiên, Box<T> và T value giữ vai trò gì?

**Đáp án:** <T> khai báo type parameter của method; Box<T> dùng T làm type argument của container trả về; T value là tham số giá trị kiểu T. Chữ ký liên kết kiểu của value và kiểu phần tử của Box.

**Câu 2.** Vì sao **String text = Box.of("Java").value()** có thể làm việc mà không cần cast?

**Đáp án:** Compiler suy luận type argument của generic factory và Box từ đối số "Java"/ngữ cảnh, nên value() có kiểu tĩnh String. Không phải chuyển từ Object một cách không kiểm tra.

**Câu 3.** Tại sao **static <T> T create() { return new T(); }** không hợp lệ?

**Đáp án:** Java không cho phép tạo instance của type variable bằng new T() do type erasure và vì không có constructor được bảo đảm cho mọi T. Cần một nguồn tạo như Supplier<T> hoặc Class<T> với điều kiện khởi tạo phù hợp.

**Câu 4.** Khác biệt giữa **Supplier<T>** và **Class<T>** đối với factory là gì?

**Đáp án:** Supplier cung cấp một hành vi tạo T do caller chỉ rõ; Class<T> mang runtime class token, có thể dùng cho kiểm tra cast hoặc reflection. Cả hai đều có giới hạn/hợp đồng riêng; Class<T> không thể tự xác minh type arguments lồng nhau.

**Câu 5.** Trong **static <K,V> Pair<K,V> pair(K k,V v)**, gọi pair("x", 1) thường suy luận ra kiểu gì?

**Đáp án:** Pair<String, Integer>, vì literal 1 được boxing thành Integer.

**Câu 6.** Tại sao **@SuppressWarnings("unchecked")** không tự khiến một factory trả T trở nên type-safe?

**Đáp án:** Annotation chỉ ẩn cảnh báo; cast chưa được chứng minh có thể thất bại lúc chạy. Factory an toàn cần mối quan hệ kiểu thực giữa đầu vào/nguồn tạo và kết quả.

**Câu 7.** Vì sao method **mutableCopy(Collection<? extends T>)** có thể giúp tạo List<Number> từ List<Integer>?

**Đáp án:** Upper-bounded wildcard cho phép collection nguồn chứa T hoặc subtype của T; constructor ArrayList sao chép các phần tử vào danh sách có kiểu kết quả T được compiler suy luận từ ngữ cảnh.

**Câu 8.** **List.copyOf** có cùng hợp đồng null và mutability với **new ArrayList<>(source)** không?

**Đáp án:** Không. List.copyOf trả unmodifiable list và không chấp nhận phần tử null. ArrayList mới có thể chứa null và cho phép sửa cấu trúc.

**Câu 9.** Với **static <T> Response<T> failure(String message)** chỉ lưu null vào data, làm sao gán cho Response<String>?

**Đáp án:** Dùng **Response<String> r = Responses.failure("error")** nhờ target typing, hoặc **Responses.<String>failure("error")**. Factory không tạo String; nó tạo Response được tham số hóa bằng kiểu mong muốn với data null.

**Câu 10.** Khi nào nên giữ kiểu trả về là một interface generic thay vì implementation class?

**Đáp án:** Khi caller chỉ cần hợp đồng của interface và muốn thay implementation về sau. Ví dụ **Repository<K,V> fromMap(Map<K,V>)** giữ đầy đủ type arguments mà không buộc caller phụ thuộc MapRepository.

## 24. Ghi nhớ cốt lõi

Một generic factory method **an toàn kiểu** không chỉ có ký hiệu **<T>** trong chữ ký; nó phải có cách xác minh hoặc tạo ra đối tượng tương thích với T. Các dạng **<T> Box<T> of(T value)**, **<T> T create(Supplier<? extends T>)**, **<S,T> T convert(S, Function<? super S,? extends T>)** và **<T> T checked(Object, Class<T>)** thể hiện bốn cách giữ hoặc xác lập quan hệ kiểu mà không yêu cầu caller cast.

Hãy ưu tiên để compiler chứng minh phần lớn quan hệ từ chữ ký và implementation; chỉ dùng kiểm tra runtime khi dữ liệu thực sự bắt đầu ngoài hệ thống kiểu (như Object từ nguồn không tin cậy). Định nghĩa riêng chính sách null, exception, mutability và vòng đời object. Với cách thiết kế đó, caller đọc được ngay kết quả sẽ mang kiểu gì, còn sai lệch kiểu được phát hiện sớm thay vì bị che trong một phép ép kiểu không kiểm tra.
