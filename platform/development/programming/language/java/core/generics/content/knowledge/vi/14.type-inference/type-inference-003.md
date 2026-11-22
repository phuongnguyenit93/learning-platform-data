# Diamond và suy luận kiểu khi khởi tạo đối tượng trong Java Generics

## 1. Diamond `<>` là gì?

Khi tạo đối tượng của một lớp generic, Java có thể **suy luận đối số kiểu** từ ngữ cảnh và các đối số của constructor. Cặp dấu ngoặc nhọn góc rỗng `<>` được gọi là **diamond operator** (toán tử diamond). Cú pháp này có từ Java 7; mục đích chính là tránh viết lặp những đối số kiểu đã đủ thông tin để trình biên dịch tìm ra.

```java
// Viết đầy đủ đối số kiểu bên trái và bên phải
List<String> names = new ArrayList<String>();

// Diamond: compiler suy luận kiểu của đối tượng mới
List<String> names = new ArrayList<>();
```

Hai dòng là **hai cách khai báo tương đương**, cần chọn một dòng khi đặt trong chương trình thực tế. Trong dòng thứ hai, `javac` dùng ngữ cảnh `List<String>` để suy luận rằng đối tượng được tạo phù hợp với `ArrayList<String>`.

Điểm cần nhớ:

- Diamond là `<>` xuất hiện **sau tên lớp generic khi tạo đối tượng**, chẳng hạn `new ArrayList<>()`, `new HashMap<>()` hoặc `new Box<>(value)`.
- `<>` yêu cầu compiler **suy luận đối số kiểu**, không có nghĩa “không dùng generics”, cũng không có nghĩa “kiểu phần tử luôn là `Object`”.
- Diamond **khác raw type**. `new ArrayList()` bỏ đối số kiểu và có thể làm mất kiểm tra kiểu; `new ArrayList<>()` vẫn tham gia kiểm tra generics.
- Diamond **khác wildcard `<?>`**. `?` mô tả đối số kiểu không biết ở một kiểu được sử dụng, còn `<>` yêu cầu suy luận các đối số kiểu để thực hiện phép tạo đối tượng.

Đối số kiểu được kiểm tra chủ yếu khi **biên dịch**. Diamond không tự thêm kiểm tra từng phần tử tại runtime; Java Generics vẫn hoạt động theo cơ chế *type erasure*.

## 2. Mối quan hệ giữa kiểu đích và biểu thức `new`

Khi có một kiểu mong đợi ở vị trí chứa biểu thức `new`, compiler có thể dùng kiểu đó làm **target type** (kiểu đích). Các ngữ cảnh có target type gồm phép gán, khởi tạo biến, truyền đối số vào phương thức và trả kết quả từ một phương thức.

Ví dụ phổ biến nhất:

```java
List<Integer> numbers = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
Set<Long> ids = new HashSet<>();
```

Các khai báo cần import các lớp từ `java.util`. Có thể đọc dòng đầu như sau:

1. Biến bên trái cần một `List<Integer>`.
2. Biểu thức bên phải đang tạo `ArrayList<E>` và dùng diamond.
3. Compiler suy luận `E = Integer` để phép gán hợp lệ.
4. Bên gọi nhận một danh sách có thể thêm `Integer`, nhưng không thể thêm một `String` tùy ý.

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10);
// numbers.add("ten"); // Lỗi biên dịch
```

Diamond giảm lặp cú pháp, **không** làm thay đổi các quy tắc bất biến (*invariance*) của Java Generics. Vì `Integer` kế thừa `Number` không có nghĩa `List<Integer>` là kiểu con của `List<Number>`.

```java
List<Integer> ints = new ArrayList<>();
// List<Number> nums = ints; // Lỗi: generic invariant
```

### Kiểu đích không nhất thiết bằng đúng lớp ở vế phải

```java
Collection<String> words = new ArrayList<>();
Iterable<Integer> input = new ArrayList<>();
Map<String, List<Integer>> grouped = new HashMap<>();
```

`ArrayList<E>` thực hiện `Collection<E>` và `Iterable<E>`; `HashMap<K,V>` thực hiện `Map<K,V>`. Diamond dùng thông tin kiểu mong đợi qua quan hệ kiểu tương thích, không chỉ sao chép nguyên tên lớp ở vế trái.

## 3. So sánh viết tường minh, diamond và raw type

| Cách viết | Ý nghĩa | An toàn kiểu |
|---|---|---|
| `new ArrayList<String>()` | Nêu tường minh `E = String` | Có |
| `new ArrayList<>()` với đích `List<String>` | Suy luận `E = String` từ ngữ cảnh | Có |
| `new ArrayList()` | Dùng raw `ArrayList`, không khai báo đối số kiểu | Bỏ kiểm tra generic ở những thao tác raw; có thể có cảnh báo `unchecked` |
| `new ArrayList<?>()` | Cố dùng wildcard làm đối số kiểu trong phép tạo đối tượng | Không hợp lệ |
| `new ArrayList` | Thiếu `()` cho constructor trong Java thông thường | Không hợp lệ |

Đặt hai dòng sau cạnh nhau:

```java
List<String> safe = new ArrayList<>();
List<String> unsafe = new ArrayList(); // Unchecked conversion
```

Dòng thứ hai có thể biên dịch với cảnh báo vì vế phải là raw type. Khi dùng `javac -Xlint:rawtypes,unchecked`, compiler có thể chỉ ra vị trí mất thông tin kiểu. Một ví dụ về rủi ro raw type:

```java
List raw = new ArrayList();
raw.add(42);
List<String> assumedStrings = raw; // Unchecked conversion
// String s = assumedStrings.get(0); // Có thể ném ClassCastException
```

Đây là **mã minh họa không an toàn**. Với diamond, quá trình suy luận và kiểm tra tham số kiểu diễn ra ở compile time, nên không cần mở rủi ro này chỉ để tránh lặp tên `String`.

## 4. Diamond dùng thông tin từ constructor

Compiler không chỉ nhìn kiểu đích. Nó còn có thể dùng các **đối số truyền cho constructor** và ràng buộc của constructor để suy luận đối số kiểu.

Ví dụ:

```java
ArrayList<String> copy = new ArrayList<>(List.of("Lan", "Minh"));
```

Constructor `ArrayList(Collection<? extends E>)` nhận một collection các phần tử có kiểu phù hợp với `E`. Lời gọi `List.of("Lan", "Minh")` cung cấp các chuỗi; kiểu đích `ArrayList<String>` cũng ràng buộc `E` là `String`. Các thông tin này nhất quán với nhau.

Khi đích là kiểu rộng hơn:

```java
List<Number> numbers = new ArrayList<>(List.of(1, 2.5));
```

Compiler giải các ràng buộc từ **kiểu đích `List<Number>`** và các đối số constructor. Kết quả có thể là `ArrayList<Number>`, vì các giá trị `Integer` và `Double` đều gán được cho `Number`. Điều đó không biến `ArrayList<Integer>` thành subtype của `ArrayList<Number>`.

Với lớp generic tự định nghĩa:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Có thể tạo:

```java
Box<String> a = new Box<>("Java");
Box<Integer> b = new Box<>(21);
```

Ở đây, constructor nhận `T`, trong khi target type nói rõ `T` là `String` hoặc `Integer`. Hai nguồn ràng buộc phối hợp để compiler chọn kiểu phù hợp.

**Lưu ý:** Compiler tìm kiểu thỏa các ràng buộc của toàn biểu thức, chứ không đơn giản “đọc chữ bên trái rồi dán vào diamond” trong mọi trường hợp. Nếu constructor, cận kiểu hoặc kiểu đích mâu thuẫn, chương trình có thể không biên dịch.

## 5. Khi khởi tạo với `var`, constructor phải tự cung cấp thông tin kiểu

`var` làm compiler suy luận kiểu của biến từ initializer, nên thiếu một kiểu đích như `List<String>` để định hướng diamond. Kết quả phụ thuộc chữ ký constructor và các đối số:

```java
var mixed = new ArrayList<>();             // ArrayList<Object>.
mixed.add("hello");
mixed.add(123);

var words = new ArrayList<>(List.of("A", "B")); // ArrayList<String>.
// words.add(3); // Lỗi: Integer không là String.

var fixed = new ArrayList<String>();      // ArrayList<String>.
```

Ở dòng đầu, constructor không có đối số ràng buộc E; cận trên mặc định Object dẫn đến `ArrayList<Object>`. Ở dòng thứ hai, constructor `ArrayList(Collection<? extends E>)` nhận nguồn String, nên E được xác định hữu ích dù không có target type bên trái. **Các lệnh add về sau không làm E được suy luận lại.**

| Khai báo | Kiểu tĩnh |
| --- | --- |
| `List<String> a = new ArrayList<>()` | `List<String>` |
| `var b = new ArrayList<String>()` | `ArrayList<String>` |
| `var c = new ArrayList<>()` | `ArrayList<Object>` |
| `var d = new ArrayList<>(List.of("x"))` | `ArrayList<String>` |

Đây là một nhánh đặc biệt của **suy luận constructor với diamond**: hãy xem ràng buộc ở đúng biểu thức `new`. Nếu mục tiêu là danh sách String rỗng, nên viết `List<String> list = new ArrayList<>()` hoặc `var list = new ArrayList<String>()`.

## 6. Diamond trong lời gọi phương thức

Biểu thức tạo đối tượng với diamond có thể xuất hiện trực tiếp ở vị trí **đối số của một phương thức**. Khi phương thức yêu cầu một kiểu cụ thể, compiler có thể dùng kiểu tham số hình thức làm target type.

```java
static void acceptStrings(List<String> input) {
    System.out.println(input.size());
}

static void example() {
    acceptStrings(new ArrayList<>());
}
```

`new ArrayList<>()` được kiểm tra trong ngữ cảnh yêu cầu `List<String>`; compiler có thể suy luận `E = String`. Việc danh sách lúc tạo đang rỗng không làm compiler mặc định suy luận `Object` trong trường hợp này.

Một ví dụ với tham số generic:

```java
static <T> void addDefault(List<T> values, T element) {
    values.add(element);
}

static void example() {
    addDefault(new ArrayList<>(), "Java");
}
```

Compiler có thể suy luận kiểu `T` để lời gọi hợp lệ, dựa vào thông tin từ cả tham số danh sách và đối số `"Java"`. Với API có nhiều overload hoặc các ràng buộc phức tạp, kiểu suy luận có thể ít hiển nhiên hơn; khi đó khai báo biến rõ kiểu trước khi gọi sẽ dễ đọc và dễ chẩn đoán hơn.

Không nên diễn giải mọi `new ArrayList<>()` là `ArrayList<Object>`: nó chỉ có thể suy luận như vậy trong **ngữ cảnh thiếu ràng buộc cụ thể**, chẳng hạn `var list = new ArrayList<>()` với constructor không đối số.

## 7. Diamond trong câu lệnh `return`

Kiểu trả về của một phương thức cũng có thể tạo target type.

```java
static List<String> emptyNames() {
    return new ArrayList<>();
}
```

Compiler kiểm tra `new ArrayList<>()` theo kiểu trả về `List<String>`. Không phải viết `return new ArrayList<String>();`.

Với phương thức generic:

```java
static <T> List<T> emptyList() {
    return new ArrayList<>();
}
```

Trong thân phương thức, `T` là một type parameter có tên; biểu thức diamond được suy luận sao cho kết quả phù hợp `List<T>`. Bên gọi có thể dùng:

```java
List<Integer> ints = emptyList();
List<String> texts = emptyList();
```

Ở ví dụ `emptyList`, phần suy luận **tại lời gọi phương thức** và phần suy luận **tại biểu thức tạo đối tượng** là hai bước liên quan nhưng khác nhau:

1. `emptyList()` là lời gọi phương thức generic, có thể dựa vào kiểu đích để tìm `T`.
2. `new ArrayList<>()` nằm trong thân phương thức, được kiểm tra theo kiểu trả về `List<T>` đã khai báo.

Đừng kết luận rằng một đối tượng `ArrayList` ở runtime chứa được thông tin đầy đủ của `T`; generics vẫn bị erasure.

## 8. Khởi tạo cấu trúc generic lồng nhau

Diamond đặc biệt hữu ích khi kiểu đích dài và lồng nhau:

```java
Map<String, List<Integer>> groups =
        new HashMap<String, List<Integer>>();
```

Có thể viết gọn:

```java
Map<String, List<Integer>> groups = new HashMap<>();
groups.put("even", new ArrayList<>());
```

Ở biểu thức bên ngoài, compiler dùng target type `Map<String, List<Integer>>` để xác định `K = String` và `V = List<Integer>`. Ở lời gọi `put`, tham số giá trị yêu cầu `List<Integer>`, nên `new ArrayList<>()` tiếp tục suy luận phần tử là `Integer`.

Một ví dụ có dữ liệu:

```java
Map<String, List<Integer>> groups = new HashMap<>();
groups.put("even", new ArrayList<>(List.of(2, 4)));
groups.put("odd", new ArrayList<>(List.of(1, 3)));

// groups.put("wrong", new ArrayList<>(List.of("x"))); // Không hợp kiểu
```

Diamond bỏ lặp cú pháp, nhưng compiler vẫn kiểm tra **từng tầng generic**. `Map<String, List<Integer>>` không chấp nhận `List<String>` ở vị trí giá trị.

Nên đặt tên biến rõ ràng khi nhiều lớp generic lồng nhau làm việc đọc khó khăn. Diamond làm giảm văn bản lặp, không loại bỏ nhu cầu thiết kế kiểu có ý nghĩa.

## 9. Ví dụ Java 17 hoàn chỉnh

Tạo tệp `DiamondInferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DiamondInferenceDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static void printStrings(List<String> input) {
        System.out.println("Argument: " + input);
    }

    static List<String> copyWords(List<String> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println("Names: " + names);

        var scores = new ArrayList<Integer>();
        scores.add(3);
        scores.add(5);
        System.out.println("Scores: " + scores);

        var mixed = new ArrayList<>();
        mixed.add("text");
        mixed.add(42);
        System.out.println("Mixed inference: " + mixed);

        Map<String, List<Integer>> groups = new HashMap<>();
        groups.put("even", new ArrayList<>(List.of(2, 4)));
        System.out.println("Even: " + groups.get("even"));

        Box<String> greeting = new Box<>("Hello");
        var inferredBox = new Box<>("Hi");
        System.out.println("Greeting: " + greeting.get());
        System.out.println("Inferred box: " + inferredBox.get());

        List<String> copied = copyWords(List.of("red", "blue"));
        System.out.println("Copied: " + copied);

        printStrings(new ArrayList<>(List.of("A", "B")));
    }
}
```

Biên dịch bằng JDK 17 hoặc mới hơn:

```bash
javac DiamondInferenceDemo.java
java DiamondInferenceDemo
```

**Stdout chính xác:**

```text
Names: [Lan]
Scores: [3, 5]
Mixed inference: [text, 42]
Even: [2, 4]
Greeting: Hello
Inferred box: Hi
Copied: [red, blue]
Argument: [A, B]
```

Đọc chương trình theo ngữ cảnh:

1. `names` có target type `List<String>`, nên `new ArrayList<>()` suy luận phần tử `String`.
2. `scores` dùng `var`, nhưng kiểu `Integer` đã nằm trong `new ArrayList<Integer>()`, nên biến có kiểu `ArrayList<Integer>`.
3. `mixed` dùng `var` và diamond của constructor không tham số; compiler không có dấu hiệu cụ thể hơn và suy luận `ArrayList<Object>`. `add("text")` và `add(42)` đều an toàn đối với `Object`.
4. `groups` dùng hai tầng suy luận: `HashMap<>` từ kiểu khai báo và `ArrayList<>(List.of(2,4))` từ tham số của `put` và các giá trị đầu vào.
5. `greeting` suy luận `Box<String>` nhờ target type và constructor. `inferredBox` không có target type tường minh nhưng constructor nhận `String`, nên biến có kiểu `Box<String>`.
6. `copyWords` cho thấy diamond trong biểu thức `return`; `printStrings` cho thấy diamond ở vị trí đối số phương thức.

Ví dụ chủ động dùng `ArrayList` mutable ở những nơi thêm phần tử. `List.of(...)` cung cấp dữ liệu nguồn bất biến, nhưng constructor `new ArrayList<>(source)` tạo danh sách mới có thể sửa; hai thứ có hành vi mutation khác nhau.

## 10. Diamond không phải wildcard

Hai cú pháp nhìn gần giống nhưng phục vụ mục đích khác nhau:

```java
List<?> unknown;              // Wildcard: kiểu phần tử chưa biết
List<String> known = new ArrayList<>(); // Diamond: suy luận String
```

`?` xuất hiện trong **đối số kiểu của một kiểu generic được sử dụng**, để biểu diễn kiểu chưa biết theo hợp đồng. `<>` xuất hiện khi **tạo đối tượng** để cho compiler suy luận đối số kiểu. Không thể viết:

```java
// List<?> wrong = new ArrayList<?>(); // Không hợp lệ
// List<String> wrong2 = new ArrayList<? extends String>(); // Không hợp lệ
```

Ngay cả khi đích dùng wildcard, vế phải khi tạo đối tượng vẫn cần diamond hoặc một đối số kiểu cụ thể:

```java
List<?> view = new ArrayList<String>();
List<?> inferredView = new ArrayList<>();
```

Ở `inferredView`, ngữ cảnh `List<?>` không xác định một kiểu phần tử duy nhất. Compiler chọn một kiểu phù hợp với các ràng buộc; không được dựa vào việc nó nhất thiết là `String`. Để tạo danh sách `String` chắc chắn, viết `new ArrayList<String>()` hoặc cung cấp ngữ cảnh đủ rõ như `List<String> names = new ArrayList<>()`.

## 11. Diamond và constructor generic là hai cơ chế độc lập

Đối số kiểu của **lớp** và đối số kiểu của **constructor generic** có thể là hai thứ khác nhau.

Ví dụ lớp `Entry<T>`:

```java
final class Entry<T> {
    private final T value;

    <U> Entry(T value, U marker) {
        this.value = value;
        System.out.println("Marker: " + marker);
    }

    T get() {
        return value;
    }
}
```

Với:

```java
Entry<String> item = new Entry<>("Java", 2026);
```

`T` là tham số kiểu của lớp `Entry<T>`, được ràng buộc thành `String`. `U` là tham số kiểu riêng của constructor, được suy luận từ `2026` (một `Integer` sau boxing). Diamond `<>` đại diện **đối số kiểu của lớp cần suy luận**; nó không ghi lại `<U>` ở vị trí tham số của constructor.

Đây là đoạn minh họa khai báo lớp/khởi tạo, chưa có `main` nên không phải chương trình độc lập. Nếu muốn gọi constructor generic với type argument tường minh trong Java, cú pháp cụ thể khác với diamond; thông thường không cần làm vậy nếu suy luận đủ tốt.

Bài học là: compiler có thể giải nhiều biến kiểu trong cùng một biểu thức `new`, song mỗi biến có **nguồn khai báo và ràng buộc riêng**.

## 12. Giới hạn cú pháp và lỗi phổ biến

### Diamond chỉ phù hợp với lớp generic

```java
List<String> xs = new ArrayList<>(); // Hợp lệ
String text = new String("Hello");  // Hợp lệ, không cần diamond
// String bad = new String<>();     // Không hợp lệ: String không generic
```

Không thể viết diamond thay cho việc khai báo type parameter mới:

```java
// class Box<> { }                  // Không hợp lệ
class GenericBox<T> { }            // Khai báo type parameter có tên

// static <> void method() { }     // Không hợp lệ
static <T> T identity(T value) { return value; } // Ví dụ khai báo đúng
```

Hai khai báo `GenericBox` và `identity` là các ví dụ ngữ pháp riêng; trong chương trình thực tế hãy đặt phương thức trong một lớp phù hợp.

### Không thể áp dụng diamond cho mảng generic

Java không cho tạo trực tiếp nhiều dạng mảng của kiểu generic có đối số không reifiable:

```java
// List<String>[] lists = new ArrayList<>[10]; // Không hợp lệ
```

Lý do là mảng theo dõi kiểu phần tử runtime theo cách khác với generics đã bị erasure. Với tập hợp generic thông thường, hãy cân nhắc `List<List<String>>`:

```java
List<List<String>> lists = new ArrayList<>();
```

### Diamond không bảo đảm mọi phép gán đều hợp kiểu

```java
List<String> strings = new ArrayList<>();
// List<Integer> integers = strings; // Không biên dịch
// List<Number> numbers = new ArrayList<String>(); // Không biên dịch
```

Diamond không sửa được một quan hệ generic không tương thích. Compiler không tự biến `List<String>` thành `List<Number>` hay `List<Integer>` khi ràng buộc kiểu mâu thuẫn.

### Không viết wildcard ngay trong phép tạo đối tượng

```java
// new ArrayList<?>()                  // Không hợp lệ
// new ArrayList<? extends Number>()   // Không hợp lệ
List<? extends Number> values = new ArrayList<Integer>(); // Hợp lệ
```

Wildcard biểu diễn hợp đồng khi **sử dụng kiểu**. Biểu thức `new` cần suy luận một kiểu cụ thể có thể thỏa ràng buộc, hoặc chỉ rõ đối số kiểu thích hợp.

## 13. Diamond với anonymous class: khác biệt Java 7 và Java 9+

Trong Java 7–8, diamond không được dùng với việc khởi tạo lớp ẩn danh (*anonymous class*). Từ Java 9, Java cho phép diamond với anonymous class **khi kiểu được suy luận là denotable** (có thể biểu diễn phù hợp trong Java source).

Ví dụ tương thích Java 17:

```java
List<String> names = new ArrayList<>() {
    @Override
    public boolean add(String item) {
        return super.add(item.trim());
    }
};
names.add("  Lan  ");
System.out.println(names); // [Lan]
```

Đây là đoạn minh họa, cần import `java.util.List` và `java.util.ArrayList` và đặt trong một phương thức. Việc override `add` dùng đúng kiểu `String` đã suy luận từ `List<String>` ở bên trái.

Khi dùng diamond trong anonymous class, Java áp thêm ràng buộc cho các phương thức **non-private** mới khai báo trong thân anonymous class: chúng phải override/implement phương thức từ supertype. Nếu cần định nghĩa phương thức mới không override, hãy kiểm tra quy tắc này hoặc dùng named class; đừng giả định mọi anonymous class với diamond đều hợp lệ.

Điểm cần nhớ cho Java 17 là: diamond **có thể** dùng với anonymous class trong những trường hợp phù hợp, nhưng không phải là thay thế cú pháp phổ quát cho mọi tình huống.

## 14. Cách chẩn đoán lỗi suy luận diamond

Khi compiler thông báo `incompatible types`, `cannot infer type arguments` hoặc `inference variable ... has incompatible bounds`, hãy làm theo thứ tự:

1. **Xác định target type**: biểu thức `new C<>()` có đang được gán cho biến `List<String>`, truyền vào một tham số `Collection<Number>`, hay đứng trong `return` với kiểu trả về cụ thể?
2. **Xem constructor đang chọn**: là constructor không đối số, constructor nhận `Collection<? extends E>`, hay overload khác? Những giá trị truyền vào cũng đóng góp ràng buộc.
3. **Ghi rõ biến kiểu cần suy luận**: ví dụ `ArrayList<E>` cần tìm `E`; `HashMap<K,V>` cần tìm `K` và `V`.
4. **Tìm mâu thuẫn**: đích yêu cầu `String` nhưng dữ liệu hoặc overload yêu cầu kiểu không phù hợp? Có đang nhầm `List<Integer>` là `List<Number>`?
5. **Nếu dùng `var`**, nhớ không có một khai báo đích rõ kiểu ở bên trái. Kiểm tra kiểu của biểu thức khởi tạo trước khi suy luận về các lời gọi `add` tiếp theo.
6. **Thử nêu tường minh đối số kiểu ở bên phải** để làm rõ ý định: `new ArrayList<String>()`. Nếu vẫn báo lỗi, nhiều khả năng bản thân các ràng buộc không tương thích.
7. **Ưu tiên chữ ký/kiểu rõ ràng** khi biểu thức có quá nhiều tầng generic hoặc overload. Không dùng raw type hay unchecked cast để “bắt compiler im lặng”.

Ví dụ một lỗi dễ gặp:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(10); // Lỗi: int boxing thành Integer, không gán được cho String
```

Nguyên nhân không nằm ở diamond; nó đã suy luận `String` đúng. Lời gọi thêm `Integer` vi phạm hợp đồng của `List<String>`.

Ví dụ khác:

```java
var values = new ArrayList<>();
values.add(10);
values.add("Lan");
```

Trường hợp này **không lỗi** vì `values` đã có kiểu `ArrayList<Object>`. Nếu muốn cấm chuỗi, phải cung cấp kiểu đích hoặc khai báo kiểu phần tử rõ ràng ngay khi khởi tạo.

## 15. Bài tập tự kiểm tra

Hãy đoán kiểu tĩnh và kết quả biên dịch:

```java
// A
List<String> a = new ArrayList<>();

// B
var b = new ArrayList<>();

// C
var c = new ArrayList<>(List.of(1, 2, 3));

// D
Map<String, List<Integer>> d = new HashMap<>();
d.put("odd", new ArrayList<>(List.of(1, 3)));

// E
List<Number> e = new ArrayList<>(List.of(1, 2.5));

// F
List<?> f = new ArrayList<String>();
```

Câu hỏi:

1. Vì sao `a.add("x")` hợp lệ còn `a.add(1)` không hợp lệ?
2. `b.add("x")` và `b.add(1)` có biên dịch không? `b` có phải raw type không?
3. `c` thường được suy luận là danh sách phần tử kiểu gì? Có thể thêm `String` vào `c` không?
4. Tại sao `d.put("odd", new ArrayList<>(List.of(1,3)))` hợp lệ?
5. Tại sao `e` chứa được cả phần tử `Integer` và `Double`?
6. `f.add("x")` có hợp lệ không? Dấu `?` trong `List<?>` khác `<>` ở biểu thức tạo đối tượng như thế nào?

**Đáp án:**

1. `a` có kiểu `List<String>`; target type khiến diamond suy luận `String`. `Integer` không gán được cho `String`.
2. Cả hai đều biên dịch vì `b` là `ArrayList<Object>`. `b` **không** phải raw type.
3. `c` được suy luận thành `ArrayList<Integer>` từ collection đầu vào `List.of(1,2,3)`; một `String` không phù hợp.
4. Kiểu của `d` là `Map<String,List<Integer>>`. Phương thức `put` đòi giá trị `List<Integer>` và constructor lồng nhau tạo danh sách phần tử `Integer`.
5. Target type `List<Number>` cho phép constructor tạo danh sách có tham số `Number`; `Integer` và `Double` đều là các kiểu con của `Number`.
6. `f.add("x")` không biên dịch vì wildcard `?` không tiết lộ kiểu phần tử thật. `<?>` nói “kiểu ẩn chưa biết” trong khai báo; `<>` bảo compiler suy luận đối số kiểu khi tạo đối tượng.

## 16. Tóm tắt cách áp dụng

Dùng **diamond `<>`** khi tạo đối tượng generic mà compiler đã có đủ ràng buộc từ kiểu đích, đối số constructor hoặc ngữ cảnh gọi phương thức. Nó giữ kiểm tra an toàn kiểu và làm mã bớt lặp. Với `var`, chú ý kiểu có thể được suy luận rộng hơn dự định nếu khởi tạo bằng `new ArrayList<>()` không đối số; hãy cung cấp kiểu rõ ràng khi muốn giới hạn phần tử.

Khi khó hiểu một kết quả suy luận, truy ngược **target type → constructor arguments → type parameters cần suy luận → ràng buộc tương thích**. Diamond không thay thế cho việc hiểu Generics, invariance và wildcard; nó chỉ giao việc suy luận kiểu hợp lệ cho compiler.