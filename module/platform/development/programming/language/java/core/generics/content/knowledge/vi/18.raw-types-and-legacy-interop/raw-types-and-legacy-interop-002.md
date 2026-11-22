# Phân biệt raw type với kiểu thông thường không có tham số kiểu trong Java

## 1. Hai khái niệm dễ nhầm

Trong Java, **raw type (kiểu thô)** là cách sử dụng một tên kiểu **đã được khai báo là generic** nhưng **bỏ qua danh sách tham số kiểu** ở vị trí sử dụng.

Ví dụ, thư viện Java khai báo interface `List<E>`. Khi viết:

~~~java
List<String> names = new ArrayList<>(); // Kiểu tham số hóa: List<String>.
List rawNames = new ArrayList();        // Raw type: List và ArrayList.
~~~

`List` và `ArrayList` trong dòng thứ hai là **raw types**, bởi chính các kiểu được khai báo với type parameter nhưng nơi sử dụng lại bỏ chúng.

Trái lại, **kiểu không generic (non-generic type)** được khai báo ngay từ đầu mà **không có type parameter**:

~~~java
final class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

Viết `Person person = new Person("Lan");` là dùng một kiểu thông thường, **không phải raw type**. Không thể viết `Person<String>` vì `Person` không được khai báo là kiểu generic.

**Kết luận nền tảng:** muốn nhận diện raw type, phải xem **định nghĩa của kiểu đó có khai báo type parameter hay không**, rồi mới xem vị trí sử dụng có bỏ type argument hay không. Không thể chỉ dựa vào việc một tên kiểu có dấu `<...>` xuất hiện trong dòng code hay không.

## 2. Thuật ngữ cần phân biệt chính xác

- **Type parameter**: biến kiểu trong khai báo, ví dụ `T` ở `class Box<T>` hoặc `E` ở `interface List<E>`.
- **Type argument**: đối số kiểu khi sử dụng một kiểu generic, ví dụ `String` trong `Box<String>` và `List<String>`.
- **Parameterized type**: kiểu generic đã được cung cấp type argument, ví dụ `List<String>`, `List<Object>`, `List<?>`.
- **Raw type**: tên generic thiếu danh sách type argument trong ngữ cảnh sử dụng thích hợp, ví dụ `List`, `Map`, `Box` khi các khai báo tương ứng là generic.
- **Non-generic type**: khai báo lớp, interface hoặc kiểu vốn không nhận type argument, ví dụ `String`, `Integer` hoặc một lớp `LegacyRecord` không có `<T>`.
- **Type erasure**: cơ chế biên dịch làm phần lớn thông tin tham số generic không còn là thành phần của JVM method descriptor. Đây là cơ chế triển khai, **không đồng nghĩa raw type**.

Nói cách khác: *raw* mô tả cách sử dụng một **generic type**; *non-generic* mô tả bản thân một khai báo kiểu **không generic**.

## 3. So sánh bằng hai lớp tự định nghĩa

Xét hai khai báo:

~~~java
// Không generic: không khai báo tham số kiểu nào.
class LegacyBox {
    private final Object value;

    LegacyBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}

// Generic: khai báo type parameter T.
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

Cách dùng:

~~~java
LegacyBox ordinary = new LegacyBox("Java");
Object fromOrdinary = ordinary.get();

Box<String> typed = new Box<>("Generics");
String fromTyped = typed.get();

Box raw = new Box("Raw");
Object fromRaw = raw.get();
~~~

| Khía cạnh | `LegacyBox` | `Box<String>` | `Box` |
| --- | --- | --- | --- |
| Kiểu gốc khai báo `<T>`? | Không | Có | Có |
| Cách dùng là raw type? | Không | Không | Có |
| `get()` nhìn từ source trả gì? | Object theo khai báo | String nhờ T = String | Object sau erasure/bound mặc định |
| Có thể viết `<String>` cho kiểu này? | Không | Đã viết | Có thể sửa thành `Box<String>` |
| Ý nghĩa | API vốn không generic | API có thông tin kiểu cụ thể | API generic bị bỏ type arguments |
| Nguy cơ cảnh báo unchecked vì raw? | Không do bản thân kiểu này | Không nếu sử dụng đúng | Có thể có khi gọi thành viên nhận T hoặc chuyển sang dạng parameterized |

Cả `LegacyBox` và raw `Box` đều có thể cho ra Object khi gọi get, nhưng **lý do hoàn toàn khác nhau**. Với `LegacyBox`, phương thức được tác giả khai báo trả Object. Với raw `Box`, phương thức ban đầu trả T nhưng việc sử dụng raw làm mất phần đảm bảo kiểu tham số hóa tại compile time.

Không nên kết luận một kiểu là raw chỉ vì có phương thức trả Object. Rất nhiều lớp không generic có các API chủ ý dùng Object.

### Không phải “không thấy dấu <>” là raw

~~~java
String text = "hello";         // String không generic.
Integer number = 17;          // Integer không generic.
Runnable action = () -> {};   // Runnable không generic.
Object obj = new Object();    // Object không generic.
~~~

Các lớp/interface trên không khai báo type parameter, nên chúng là **non-generic types**. Không có type argument nào bị bỏ sót cả.

Lệnh `new ArrayList<>()` lại thuộc một trường hợp khác: **diamond operator** yêu cầu compiler suy luận các type arguments cho một kiểu generic. Nó không tương đương `new ArrayList()` dùng raw constructor type.

## 4. Ví dụ chạy đầy đủ trên Java 17+

Lưu toàn bộ chương trình sau vào **RawVsOrdinaryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawVsOrdinaryDemo {
    static final class NonGenericBox {
        private final Object value;

        NonGenericBox(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }
    }

    static final class GenericBox<T> {
        private final T value;

        GenericBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        NonGenericBox oldStyle = new NonGenericBox("plain");
        System.out.println("plain=" + oldStyle.get());

        GenericBox<String> typed = new GenericBox<>("typed");
        String text = typed.get();
        System.out.println("typed=" + text);

        // Bỏ tham số kiểu của GenericBox<T>: sử dụng raw type.
        GenericBox rawBox = new GenericBox("raw");
        Object fromRaw = rawBox.get();
        System.out.println("rawBox=" + fromRaw);

        List<String> words = new ArrayList<>();
        words.add("Java");

        // Raw List và List<String> cùng trỏ đến một ArrayList.
        List raw = words;
        raw.add(42);
        System.out.println("rawList=" + raw);

        Object first = words.get(0);
        System.out.println("first=" + first);

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("typedRead=ClassCastException");
        }

        // Wildcard vẫn là một parameterized type, không phải raw.
        List<?> unknown = words;
        System.out.println("wildcardSize=" + unknown.size());

        // Generics thông thường được triển khai bằng type erasure.
        System.out.println(
                "sameRuntimeClass=" +
                (typed.getClass() == rawBox.getClass())
        );
    }
}
~~~

Biên dịch để thấy các cảnh báo tại đúng chỗ dùng raw:

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked RawVsOrdinaryDemo.java
java RawVsOrdinaryDemo
~~~

Compiler có thể cảnh báo **rawtypes** tại các vị trí khai báo/khởi tạo `GenericBox` và `List` không có type arguments; cảnh báo **unchecked** xuất hiện ở các lời gọi có khả năng không an toàn như `raw.add(42)` hoặc constructor raw. Các cảnh báo biên dịch không thuộc stdout của chương trình.

Stdout của chương trình:

~~~text
plain=plain
typed=typed
rawBox=raw
rawList=[Java, 42]
first=Java
typedRead=ClassCastException
wildcardSize=2
sameRuntimeClass=true
~~~

Giải thích:

1. `NonGenericBox` dùng Object theo thiết kế gốc; không có raw generic nào trong kiểu này.
2. `GenericBox<String>` có thông tin kiểu String tại compile time, nên compiler kiểm tra `typed.get()` có thể dùng như String.
3. `GenericBox rawBox` bỏ type argument của `GenericBox<T>`; `get()` được nhìn theo chữ ký đã xóa, ở ví dụ này là Object.
4. `List raw = words` tạo **một tham chiếu raw** tới chính danh sách `List<String>` đang tồn tại; không tạo bản sao và không chuyển đổi phần tử.
5. `raw.add(42)` lọt qua kiểm tra generic theo đường raw kèm unchecked warning. Vì ArrayList chứa Integer ở vị trí thứ hai, lời gọi `words.get(1)` dùng kết quả như String sẽ ném ClassCastException.
6. `List<?> unknown` vẫn có type argument là wildcard `?`, nên **không phải raw**.
7. `typed.getClass() == rawBox.getClass()` cho `true`: raw và parameterized sử dụng cùng generic class ở runtime theo type erasure thông thường. Điều này **không** làm kiểu compile-time của các biến giống nhau.

Đoạn minh họa cố ý sử dụng raw type để giải thích rủi ro; trong code ứng dụng nên sửa nguồn raw thay vì bắt ClassCastException như một giải pháp dài hạn.

## 5. Raw type không phải List<Object>

Một lỗi quan trọng là cho rằng các khai báo sau tương đương:

~~~java
List raw;              // Raw type.
List<Object> objects;  // Parameterized type với E = Object.
List<?> unknown;       // Parameterized type với unbounded wildcard.
List<String> names;    // Parameterized type với E = String.
~~~

Chúng không tương đương.

### List<Object> vẫn được kiểm tra generic

~~~java
List<Object> objects = new ArrayList<>();
objects.add("Java");
objects.add(42);
Object value = objects.get(0);
~~~

`List<Object>` là một generic type với tham số kiểu xác định Object. Nó cho phép thêm String/Integer vì chúng đều là subtype của Object, nhưng **compiler vẫn kiểm tra theo E = Object**.

Trong khi đó, raw `List` bỏ thông tin E khi dùng các thành viên bị ảnh hưởng bởi erasure, tạo khả năng chuyển dữ liệu sai kiểu vào các collection vốn được sử dụng ở nơi khác với tham số cụ thể.

### List<?> giữ sự không chắc chắn về kiểu phần tử

~~~java
List<String> names = new ArrayList<>();
names.add("Java");
List<?> unknown = names;

Object value = unknown.get(0);
// unknown.add("Kotlin"); // Lỗi biên dịch.
~~~

`List<?>` là parameterized type: nó mô tả một `List` có kiểu phần tử nào đó chưa biết. Compiler không cho thêm một String tùy ý vì giá trị đó có thể không tương thích với kiểu phần tử thực. Có thể thêm `null` theo quy tắc chung của wildcard, nhưng collection cụ thể có thể không hỗ trợ thao tác sửa đổi.

Ngược lại:

~~~java
List raw = names;
raw.add(42); // Unchecked warning: có thể phá giả định của List<String>.
~~~

**List<?> thường là lựa chọn phù hợp khi chỉ cần đọc phần tử dưới dạng Object mà không biết kiểu cụ thể**, đặc biệt ở API chỉ đọc/quan sát danh sách.

### List<Object> không phải supertype của List<String>

Mặc dù String extends Object, Java generics nhìn chung **invariant**:

~~~java
List<String> names = new ArrayList<>();
// List<Object> wrong = names; // Không biên dịch.
List<?> acceptable = names;    // Hợp lệ.
List rawButUnsafe = names;     // Hợp lệ, raw usage.
~~~

Nếu `List<Object>` nhận được một `List<String>` rồi thêm Integer, tính đúng kiểu sẽ bị phá vỡ. Wildcard đại diện sự chưa biết một cách an toàn hơn; raw type chỉ tồn tại để phục vụ tương thích với mã cũ và các tình huống rất đặc thù.

## 6. Raw type khác với kiểu generic dùng diamond

Xem:

~~~java
List<String> a = new ArrayList<>();
var b = new ArrayList<String>();
var c = new ArrayList<>();
List raw = new ArrayList();
~~~

- `a` có kiểu tĩnh List<String>; biểu thức `new ArrayList<>()` dùng diamond và ngữ cảnh List<String> để suy luận E = String.
- `b` có kiểu ArrayList<String> được suy luận từ initializer ghi rõ String.
- `c` có kiểu ArrayList<Object> trong trường hợp constructor rỗng, không có thông tin khác để suy ra E; **đây vẫn là parameterized type**, không phải raw.
- `raw` dùng raw type List và raw construction ArrayList, thực sự bỏ qua các type arguments ở vị trí sử dụng.

Do đó, **không thể suy ra rằng dùng var cùng diamond là raw**. Ngay cả khi trình biên dịch suy luận E thành Object, `ArrayList<Object>` vẫn là generic có tham số kiểu.

Thêm một ví dụ:

~~~java
var inferred = new ArrayList<>(List.of("Java", "Kotlin"));
// ArrayList<String>, vì constructor nhận dữ liệu String.
~~~

Thông tin type argument có thể đến từ target type, các đối số constructor hoặc vị trí suy luận phù hợp. Raw type là **sự bỏ type arguments của generic type**, không phải bất kỳ trường hợp nào trình biên dịch tự suy luận kiểu.

## 7. Generic method không có nghĩa class là generic

Không nên đánh đồng hai khái niệm:

~~~java
final class Utilities {
    static <T> T same(T value) {
        return value;
    }
}
~~~

Lớp `Utilities` **không generic** vì bản thân class không có `<T>`. Nhưng phương thức `same` là một **generic method** khai báo tham số kiểu riêng.

Dùng:

~~~java
String result = Utilities.same("Java");
Integer number = Utilities.same(17);
~~~

Điều này bình thường và không sử dụng raw type. Không có cú pháp `Utilities<String>` vì Utilities không nhận tham số kiểu ở cấp class.

Một phương thức trả Object mà không generic:

~~~java
final class PlainFactory {
    static Object create() {
        return "Java";
    }
}
~~~

`PlainFactory` cũng là non-generic. Việc caller muốn ép một Object thành String là một tình huống kiểm tra/cast thông thường, không tự động là vấn đề raw type.

**Câu hỏi nhận diện:** dấu `<T>` nằm ở **khai báo class/interface** hay chỉ ở **khai báo phương thức**? Raw type được xác định dựa vào kiểu generic, không dựa vào việc class có một phương thức generic độc lập.

## 8. Một lớp con non-generic vẫn có thể kế thừa generic class

Ví dụ:

~~~java
class Base<T> {
    T value;

    Base(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

// FixedStringBox không khai báo tham số kiểu.
final class FixedStringBox extends Base<String> {
    FixedStringBox(String value) {
        super(value);
    }
}
~~~

`FixedStringBox` là **non-generic class**: không có danh sách tham số kiểu trong khai báo của chính nó. Tuy nhiên nó kế thừa `Base<String>`, nên:

~~~java
FixedStringBox box = new FixedStringBox("Java");
String text = box.get(); // Kiểu trả về được chuyên biệt là String.
~~~

Việc sử dụng `FixedStringBox` **không phải raw**, và compiler vẫn kiểm tra các thành viên đã được chuyên biệt hóa từ Base<String>.

Nếu thay superclass bằng dạng `extends Base` không có String, đó mới là **raw use of Base** tại mệnh đề kế thừa. Lớp con tự nó vẫn có thể không generic, nhưng việc kế thừa raw superclass làm mất thông tin kiểu của các thành viên generic liên quan.

Đây là phản ví dụ quan trọng đối với ngộ nhận “lớp nào từng đụng đến generic thì bắt buộc phải ghi `<...>` ở tên của chính nó”.

## 9. Cảnh báo rawtypes và unchecked có phải cùng một lỗi?

Hai nhóm cảnh báo thường đi cùng nhau nhưng không đồng nhất:

- **rawtypes**: bạn đã dùng một tên generic ở dạng raw, ví dụ `List raw;`.
- **unchecked**: compiler phát hiện thao tác liên quan đến generic mà khả năng an toàn kiểu không được chứng minh đầy đủ, ví dụ gọi `raw.add(42)` hoặc chuyển raw List sang List<String>.

Ví dụ cố ý gây cảnh báo:

~~~java
List raw = new ArrayList();
raw.add("Java");
List<String> strings = raw; // Unchecked conversion.
~~~

Lệnh gán raw List vào List<String> có thể được compiler chấp nhận kèm cảnh báo vì cơ chế tương thích với mã cũ. Nó **không kiểm tra mọi phần tử của danh sách ở runtime**. Nếu raw List đã chứa đối tượng không phải String thì lỗi có thể xuất hiện muộn khi lấy dữ liệu ra như String.

Đối với non-generic class:

~~~java
final class Plain {
    Object read() {
        return 42;
    }
}
~~~

Viết `Plain p = new Plain(); Object n = p.read();` không có lý do phát cảnh báo rawtypes hoặc unchecked chỉ vì Plain không dùng generic. Nếu ép `(String) p.read()`, đó là cast runtime có thể thất bại, một vấn đề riêng.

### Dùng đúng tùy chọn javac

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked YourFile.java
~~~

Lệnh trên yêu cầu javac đưa ra cảnh báo liên quan raw và unchecked. Số dòng và định dạng chẩn đoán thay đổi theo JDK và mã nguồn; không nên viết logic dựa trên chính xác từng dòng warning.

**Không nên ẩn hết cảnh báo** bằng `@SuppressWarnings({"rawtypes", "unchecked"})` trên cả file. Nếu buộc dùng API cũ, hãy giới hạn đoạn raw càng nhỏ càng tốt, kiểm tra dữ liệu trước khi chuyển sang kiểu tham số hóa, và chú thích giả định đã kiểm chứng.

## 10. Vì sao raw type xuất hiện trong Java?

Generics được thêm vào Java 5. Nhiều thư viện và ứng dụng đã có interface hoặc class dùng collection trước đó. Để hỗ trợ biên dịch và tương thích nhị phân với mã cũ, Java cho phép tên generic được dùng ở dạng raw.

~~~java
// Phong cách tiền generics:
List legacy = new ArrayList();

// Phong cách hiện đại:
List<String> modern = new ArrayList<>();
~~~

Raw type là một **cơ chế tương thích ngược có chủ đích**, không phải cú pháp bắt buộc cho mọi chương trình Java mới.

Điều này cũng giải thích vì sao trong bytecode generics phần lớn dùng type erasure. Nhưng hãy phân biệt: **type erasure xảy ra cả khi dùng generic đúng cách** như `List<String>`. Không thể nhìn vào bytecode descriptor trả Object rồi kết luận mã nguồn đã sử dụng raw type.

### Dùng cùng một runtime class không làm hai kiểu compile-time bằng nhau

Ví dụ trong chương trình chạy:

~~~java
GenericBox<String> typed = new GenericBox<>("A");
GenericBox raw = new GenericBox("B");
boolean sameClass = typed.getClass() == raw.getClass();
~~~

`sameClass` là true với generic class thông thường do erasure. Tuy nhiên biến typed vẫn được compiler kiểm tra như `GenericBox<String>`, còn raw bị mất thông tin tham số trong nhiều thao tác. Đây là **khác biệt compile-time** có hậu quả thực tế, dù `getClass()` trùng nhau.

## 11. Những trường hợp dễ gây hiểu lầm

### Trường hợp A: Class và Class<?> không giống nhau

`java.lang.Class<T>` là một generic class:

~~~java
Class rawClass = String.class; // Raw type.
Class<?> anyClass = String.class; // Parameterized type với wildcard.
Class<String> stringClass = String.class; // Parameterized type cụ thể.
~~~

`Class<?>` thường phù hợp khi xử lý metadata về một lớp chưa biết tham số kiểu. `Class` raw dễ làm mất kiểm tra kiểu liên quan. Việc `String.class` có kiểu `Class<String>` không biến `String` thành generic type.

### Trường hợp B: Mảng không phải raw generic

~~~java
String[] words = {"A", "B"};
int[] numbers = {1, 2};
~~~

Array types không có type parameter theo cách `List<E>` có. Dùng mảng String[] hay int[] không phải raw type. Mảng có cơ chế kiểm tra kiểu runtime khác generic; không nên đồng nhất hai cơ chế.

### Trường hợp C: Một non-generic interface có thể là functional interface

~~~java
Runnable task = () -> System.out.println("run");
task.run();
~~~

`Runnable` không có type parameter, nên không phải raw. Sự có mặt của lambda cũng không làm interface đó generic.

### Trường hợp D: Danh sách mất String vì suy luận Object, nhưng vẫn không raw

~~~java
var values = new ArrayList<>();
values.add("Java");
values.add(42);
~~~

`values` được suy luận là ArrayList<Object> trong trường hợp này. Đây là một parameterized type có E = Object. Việc add cả String lẫn Integer được cho phép **theo kiểm tra generic đúng kiểu Object**, không phải vì raw usage.

### Trường hợp E: Non-generic lớp con của generic superclass

~~~java
final class StringList extends ArrayList<String> {}
StringList list = new StringList();
list.add("Java");
// list.add(42); // Compiler từ chối.
~~~

`StringList` không có `<T>` ở khai báo của nó, nên dùng StringList không phải raw. Lớp này kế thừa ArrayList<String>, vì vậy phương thức add được chuyên biệt hóa thành add(String) ở mức kiểm tra Java source.

### Trường hợp F: Raw type không xóa hết mọi cấu trúc kiểu của chương trình

Câu “dùng raw thì mọi chỗ trở thành Object” là quá tổng quát. Các thành viên không dùng type parameter có thể giữ nguyên kiểu tường minh của chúng, và erasure của type parameter bị giới hạn như `T extends Number` là Number thay vì Object. Cần xem **chữ ký cụ thể sau erasure**, không mặc định mọi method/field đều có kiểu Object.

## 12. Cách sửa mã raw type khi gặp trong dự án

Khi nhìn thấy:

~~~java
List items = loadItems();
~~~

đừng vội thay bằng `List<String>` nếu chưa biết hợp đồng thực tế của dữ liệu. Có ba hướng xử lý:

**Trường hợp đã biết mọi phần tử đúng một kiểu cụ thể:** khai báo `List<String>`, chỉnh signature của `loadItems` và các điểm tạo dữ liệu để compiler kiểm tra kiểu từ đầu đến cuối.

**Trường hợp chỉ cần đọc nhưng kiểu phần tử chưa biết:** dùng `List<?>`, duyệt các phần tử như Object, kiểm tra kiểu tại nơi cần xử lý.

**Trường hợp nhận dữ liệu từ API cũ hoặc mã không đáng tin:** kiểm tra dữ liệu trước khi chuyển thành một collection có kiểu rõ ràng:

~~~java
static List<String> validatedCopy(List<?> source) {
    List<String> result = new ArrayList<>();

    for (Object element : source) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException("Only String is allowed");
        }
        result.add(text);
    }

    return result;
}
~~~

Mã trên hoạt động với Java 17+, dùng pattern matching cho instanceof và tạo danh sách mới chứa phần tử đã xác nhận là String. Nó từ chối null; nếu nghiệp vụ cho phép null, cần thiết kế một chính sách riêng.

Đây là hướng chuyển đổi an toàn hơn so với:

~~~java
@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) raw;
~~~

Phép cast từ raw List sang List<String> không xác nhận kiểu của từng phần tử, nên có thể khiến lỗi xuất hiện muộn khi đọc.

**Quy trình nâng cấp code cũ:**

1. Xác định declaration gốc: type đang dùng generic hay non-generic?
2. Với raw generic, tìm type argument đúng từ miền nghiệp vụ thay vì chọn Object một cách ngẫu nhiên.
3. Dùng `?` nếu type argument thực sự chưa biết và API không cần thêm phần tử.
4. Tìm các unchecked warnings, đường ghi dữ liệu và raw aliases có thể gây heap pollution.
5. Thay đổi từng API boundary có kiểm soát và kiểm tra việc đọc/ghi collection.
6. Với non-generic type phù hợp thiết kế, không cần “generic hóa” chỉ để loại cảnh báo vốn không tồn tại.

## 13. Bảng nhận diện nhanh

| Cú pháp | Khai báo kiểu gốc | Phân loại |
| --- | --- | --- |
| `String s` | String không có type parameter | Non-generic type |
| `Runnable r` | Runnable không có type parameter | Non-generic type |
| `LegacyBox x` | LegacyBox được khai báo không generic | Non-generic type |
| `List list` | List<E> có E nhưng bị bỏ tại nơi dùng | Raw type |
| `ArrayList list` | ArrayList<E> có E nhưng bị bỏ | Raw type |
| `List<Object> list` | List<E> với E = Object | Parameterized type |
| `List<?> list` | List<E> với wildcard type argument | Parameterized type |
| `var list = new ArrayList<>()` | Diamond suy luận ArrayList<Object> khi không có ràng buộc khác | Parameterized type, không raw |
| `class Fixed extends Base<String>` | Fixed không có type parameter, Base có | Fixed là non-generic class dùng parameterized superclass |
| `Class clazz` | Class<T> bị bỏ T | Raw type |
| `Class<?> clazz` | Class<T> với wildcard | Parameterized type |
| `String[] array` | Kiểu mảng của String | Array type, không raw |

Phân loại phải căn cứ **khai báo gốc và vị trí sử dụng**, không chỉ hình thức bên ngoài. Đặc biệt, `Object` xuất hiện sau erasure không đủ để kết luận một đoạn mã dùng raw type.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `class A {}` rồi `A a = new A();` có phải raw type không?

**Đáp án:** Không. A không khai báo type parameter nên vốn là non-generic type. Không có tham số generic nào bị bỏ.

**Câu 2.** `List<?> a = new ArrayList<String>();` có phải raw type không?

**Đáp án:** Biến a có kiểu parameterized `List<?>`, không raw. Tuy nhiên biểu thức `new ArrayList<String>()` cũng là parameterized constructor type; cả hai sử dụng generic, dù wildcard không tiết lộ phần tử cụ thể.

**Câu 3.** `var a = new ArrayList<>();` suy luận ArrayList<Object>. Có nên gọi a là raw type không?

**Đáp án:** Không. Object là type argument cụ thể do compiler suy luận; a vẫn thuộc kiểu `ArrayList<Object>`.

**Câu 4.** Một `class StringBox extends Box<String>` có phải generic class không?

**Đáp án:** Không nếu StringBox không tự khai báo type parameter. Nhưng nó kế thừa một parameterized superclass nên các phương thức generic được chuyên biệt hóa phù hợp với String.

**Câu 5.** Tại sao `List<Object>` không thể nhận một `List<String>` nhưng raw `List` có thể được gán từ `List<String>`?

**Đáp án:** Java generics invariant để tránh ghi phần tử sai kiểu. Raw List tồn tại để tương thích mã cũ và bỏ kiểm tra type argument tại những thao tác liên quan, nên cho phép alias có rủi ro.

**Câu 6.** `Class<String>`, `Class<?>` và `Class` phân biệt thế nào?

**Đáp án:** Hai dạng đầu là parameterized types (cụ thể và wildcard); dạng cuối là raw use của generic class `Class<T>`.

**Câu 7.** Vì sao một lớp non-generic trả Object không tự động là nguồn unchecked warning?

**Đáp án:** Trả Object là kiểu API được khai báo trực tiếp. Cảnh báo unchecked liên quan các thao tác generic không thể chứng minh an toàn, chẳng hạn raw conversion/call; non-generic class tự nó không có type argument bị bỏ.

## 15. Điều cần ghi nhớ

**Raw type = dùng một kiểu vốn generic mà bỏ type arguments. Non-generic type = khai báo kiểu vốn không có type parameters.** Hai trường hợp có thể cùng chứa các method trả Object nhưng có bản chất khác nhau.

Trong Java hiện đại, hãy ưu tiên `List<String>` khi biết chính xác kiểu phần tử, `List<?>` khi chỉ cần xử lý một danh sách chưa biết kiểu phần tử, và chỉ dùng raw generic ở phạm vi nhỏ khi tích hợp legacy code có lý do rõ ràng. Compiler và `-Xlint:rawtypes -Xlint:unchecked` giúp chỉ ra nơi thông tin kiểu bị bỏ qua, còn việc kiểm tra dữ liệu thật sự là cần thiết khi đi qua các ranh giới không an toàn.
