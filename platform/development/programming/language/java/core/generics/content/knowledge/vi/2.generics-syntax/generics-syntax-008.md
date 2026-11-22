# Đọc chữ ký generic và theo dõi nơi ràng buộc từng biến kiểu trong Java

Một chữ ký generic có thể ngắn như `T get()` hoặc nhiều lớp như `<T, R> List<R> map(List<? extends T> source, Function<? super T, ? extends R> mapper)`. Điểm quyết định khi đọc không nằm ở việc thuộc tên `T`, `E`, `K`, `V`: đó chỉ là tên các **biến kiểu**. Quan trọng là xác định **nơi biến kiểu được khai báo, những vị trí nào dùng chung biến đó, giới hạn kiểu là gì và khi gọi API thì kiểu cụ thể được gán cho nó ra sao**.

Bài này hướng dẫn một phương pháp đọc chữ ký từng bước, từ generic class và generic method đến bounded type, wildcard, kiểu trả về, constructor và API Java Core. Các đoạn chương trình hoàn chỉnh dùng Java 17+; các chữ ký trích riêng được đánh dấu là mã minh họa.

## 1. Ba câu hỏi bắt buộc khi gặp một chữ ký

Với mỗi tên biến kiểu như `T`, hãy lần theo ba điểm:

1. **Khai báo ở đâu?** Tìm cặp dấu `<...>` khai báo biến kiểu: `class Box<T>`, `interface Converter<I, O>`, `static <T> T first(...)` hoặc constructor `<U> Box(U input)`. Một chữ cái `T` chỉ là type variable nếu nằm trong phạm vi khai báo hợp lệ.
2. **Ràng buộc ở những vị trí nào?** Ghi lại mọi vị trí `T` xuất hiện: trường, tham số, kiểu trả về, type argument lồng bên trong, cận của biến khác. Cùng một `T` trong cùng phạm vi đại diện cho **một lựa chọn kiểu liên kết**, không phải những kiểu được lựa chọn độc lập.
3. **Lựa chọn kiểu tại nơi sử dụng là gì?** Với `Box<String>` thì type parameter của `Box` được áp dụng như `String`. Với generic method, compiler suy luận từ đối số thực, ngữ cảnh gán và các ràng buộc, hoặc người gọi truyền type witness tường minh như `Utils.<String>identity("Java")`.

Một chữ ký thể hiện hợp đồng **compile time**. Kiểu thực tế của giá trị vẫn phải tuân thủ hợp đồng đó khi chương trình chạy; các đường đi raw/unchecked có thể phá vỡ bảo đảm tĩnh. Không cần tìm một “biến runtime tên T” trong đối tượng.

### Ví dụ mở đầu

```java
static <T> T identity(T value) {
    return value;
}
```

Chữ ký được tách thành:

- `static`: thành viên thuộc class.
- `<T>`: **khai báo biến kiểu T** dành riêng cho phương thức.
- `T` đứng trước tên `identity`: **kiểu trả về**, dùng biến kiểu đã khai báo.
- `T value`: **kiểu của tham số**, dùng chính biến kiểu đó.
- Khi gọi `String text = identity("Java");`, compiler có thể suy luận `T = String`. Khi gọi `Integer n = identity(7);`, compiler có thể suy luận `T = Integer` (giá trị `7` được boxing).

Chữ ký này nói: “phương thức nhận một `T` và trả một `T`”. Nó không bảo đảm giá trị trả về là cùng **đối tượng** với đầu vào đối với mọi cách cài đặt có chữ ký tương tự; tính đồng nhất đối tượng chỉ đúng nếu thân hàm thực hiện như ví dụ.

## 2. Phân biệt khai báo biến kiểu và truyền đối số kiểu

Hai dạng dấu ngoặc nhọn `<...>` trông tương tự nhưng có vai trò khác nhau:

| Cú pháp | Vai trò | Điều cần theo dõi |
| --- | --- | --- |
| `class Box<T>` | Khai báo type parameter của class | `T` có phạm vi trong các thành viên instance phù hợp của `Box` |
| `interface Pair<K, V>` | Khai báo hai type parameters | `K` và `V` độc lập cho đến khi chữ ký liên kết chúng |
| `Box<String>` | Sử dụng type argument cụ thể | Những vị trí `T` của `Box` được xem như `String` tại điểm dùng |
| `Map<String, Integer>` | Cung cấp hai type arguments | `K = String`, `V = Integer` |
| `<T> T read(...)` | Khai báo type parameter của method | `T` được suy luận/áp dụng riêng mỗi invocation |
| `Class<T>` | Dùng `T` làm type argument cho `Class` | `T` phải được khai báo ở phạm vi bao quanh |
| `List<?>` | Wildcard, nghĩa là một kiểu phần tử chưa biết | Không tạo một biến tên `T` cho người viết tự dùng |
| `new Box<>("a")` | Diamond inference ở constructor call | Compiler suy luận type argument từ ngữ cảnh/đối số |

Tên `T` không đặc biệt với JVM. Bạn có thể đặt tên `ITEM`, `ID`, `SOURCE` nếu rõ nghĩa và hợp cú pháp Java identifier. Quy ước thông dụng là `T` (type), `E` (element), `K` (key), `V` (value), `R` (result), `U` (kiểu bổ sung).

Nguyên tắc quan trọng: **hai khai báo có cùng tên chữ `T` nhưng ở các phạm vi khác nhau không tự ràng buộc với nhau**. Ngược lại, những lần xuất hiện của `T` trong **cùng một phạm vi khai báo** cùng chịu một tập ràng buộc. Khi tìm chỗ khai báo, đọc từ vị trí sử dụng ngược về cú pháp của phương thức, class hoặc interface bao quanh.

## 3. Cách đọc chữ ký generic class từ trái sang phải

Xét chương trình `SignatureClassDemo.java`:

```java
public class SignatureClassDemo {
    static final class Entry<K, V> {
        private final K key;
        private V value;

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

        void replace(V newValue) {
            value = newValue;
        }
    }

    public static void main(String[] args) {
        Entry<String, Integer> score = new Entry<>("Lan", 8);
        score.replace(9);

        String name = score.key();
        Integer points = score.value();

        System.out.println(name + ": " + points);
    }
}
```

Biên dịch và chạy:

```bash
javac SignatureClassDemo.java
java SignatureClassDemo
```

Kết quả `stdout`:

```text
Lan: 9
```

### Bước 1: xác định “bảng ký hiệu kiểu”

`Entry<K,V>` khai báo hai type parameters thuộc class:

| Biến kiểu | Khai báo | Những nơi ràng buộc trong class |
| --- | --- | --- |
| `K` | `Entry<K,V>` | `K key`, tham số `K key` của constructor, kiểu trả về `K` của `key()` |
| `V` | `Entry<K,V>` | `V value`, constructor `V value`, kiểu trả về `V` của `value()`, tham số `V newValue` của `replace(...)` |

### Bước 2: thay vào lời gọi cụ thể

`Entry<String, Integer>` khiến compiler kiểm tra các thành viên *như thể* chúng có kiểu:

```java
// Chỉ là hình dung về kiểu nguồn ở điểm sử dụng, không phải class mới.
Entry(String key, Integer value);
String key();
Integer value();
void replace(Integer newValue);
```

Không có bản sao mã class `EntryStringInteger` riêng. `score.replace("nine")` bị từ chối khi biên dịch. `score.replace(9)` được phép vì boxing chuyển `int` sang `Integer`.

### Bước 3: phân biệt thông tin kiểu và giá trị

`K` không phải biến lưu khóa, `V` không phải giá trị dữ liệu. `K`/`V` định nghĩa các **mối quan hệ kiểu**; `key`, `value` mới là các trường chứa dữ liệu. Một đối tượng `Entry<String,Integer>` có thể giữ các giá trị `"Lan"` và `9`, nhưng type arguments chỉ mô tả kiểu cho việc kiểm tra tại compile time.

### Bước 4: đọc constructor

`Entry(K key, V value)` dùng `K` và `V` đã khai báo ở class. Không có dấu `<K,V>` đặt trước constructor nên constructor này **không tự khai báo** cặp type parameters mới. Compiler kiểm tra constructor tương ứng với `Entry<String,Integer>` được tạo ở điểm gọi.

## 4. Cách đọc chữ ký generic method

Một generic method có type-parameter list riêng đặt **trước kiểu trả về**, sau các modifier (nếu có):

```java
public static <T> T first(java.util.List<T> values)
```

Phân tích: `public static` là modifier; `<T>` là khai báo type parameter; `T` trước `first` là kiểu trả về; `List<T>` dùng `T` để buộc phần tử đầu vào và kết quả cùng quan hệ kiểu.

### Chương trình hoàn chỉnh

Tạo `MethodSignatureDemo.java`:

```java
import java.util.List;

public class MethodSignatureDemo {
    static <T> T first(List<T> elements) {
        if (elements.isEmpty()) {
            throw new IllegalArgumentException("Empty");
        }
        return elements.get(0);
    }

    static <T> boolean contains(List<T> elements, T wanted) {
        return elements.contains(wanted);
    }

    public static void main(String[] args) {
        String a = first(List.of("A", "B"));
        Integer n = first(List.of(10, 20));

        System.out.println(a);
        System.out.println(n);
        System.out.println(contains(List.of("A", "B"), "B"));
    }
}
```

Chạy:

```bash
javac MethodSignatureDemo.java
java MethodSignatureDemo
```

`stdout`:

```text
A
10
true
```

Với `first(List.of("A", "B"))`, compiler suy luận `T` là `String`; với `first(List.of(10, 20))`, là `Integer`. Hai lời gọi không chia sẻ một “T chung toàn chương trình”. Sự ràng buộc diễn ra **riêng cho từng lần áp dụng generic method**.

Với `contains(List<T>, T)`, cùng biến `T` xuất hiện hai lần; compiler phải tìm cách suy luận type argument thỏa các ràng buộc ở lời gọi. **Không suy luận rằng compiler luôn bắt buộc cả hai biểu thức đầu vào có chính xác cùng một runtime class**: thuật toán inference có thể tìm ra supertype chung nếu chữ ký và ngữ cảnh cho phép. Nếu mục tiêu nghiệp vụ yêu cầu loại phần tử phải đồng nhất chặt chẽ, cần thiết kế API và validation phù hợp; generic inference không phải công cụ so sánh lớp runtime.

### Lỗi hay gặp: thiếu phần khai báo `<T>`

```java
// Sai nếu trong scope chưa hề có type parameter T:
// static T missing(T value) { return value; }

// Đúng:
static <T> T identity(T value) { return value; }
```

Trong generic class `Box<T>`, một **instance method** có thể dùng `T` của class mà không phải khai báo thêm. Nhưng `static` method không được sử dụng trực tiếp class-level `T` vì thành viên static thuộc class dùng chung, không thuộc một instantiation `Box<String>` nào.

## 5. Phân biệt type parameter của class và của method

Tạo `ScopeDemo.java`:

```java
public class ScopeDemo {
    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <R> R convert(java.util.function.Function<? super T, ? extends R> f) {
            return f.apply(value);
        }

        static <U> U echo(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<Integer> holder = new Holder<>(42);

        Integer original = holder.get();
        String label = holder.convert(n -> "ID-" + n);
        Boolean yes = Holder.echo(true);

        System.out.println(original);
        System.out.println(label);
        System.out.println(yes);
    }
}
```

Chạy:

```bash
javac ScopeDemo.java
java ScopeDemo
```

`stdout`:

```text
42
ID-42
true
```

Lần theo:

- `Holder<T>` khai báo `T` của **class**.
- Trường `value`, constructor `Holder(T value)` và instance method `T get()` dùng `T` thuộc class. Với `Holder<Integer>`, compiler dùng `Integer` ở những vị trí đó.
- `<R> R convert(...)` khai báo thêm `R` thuộc **method**. Trong `convert`, `T` xuất phát từ class (với receiver này là `Integer`), còn `R` được suy luận khi gọi method (ở ví dụ là `String`).
- `Function<? super T, ? extends R>` nhận hàm có khả năng xử lý giá trị `T` và tạo giá trị tương thích với `R`. Wildcard có ngữ nghĩa riêng; `?` không phải một biến kiểu có tên.
- `static <U> U echo(U value)` khai báo `U` riêng cho static method; phương thức này không phụ thuộc type argument `Integer` của `holder`. Có thể gọi `Holder.echo(true)` và compiler suy luận `U=Boolean`.

**Câu hỏi nhanh:** `get()` và `convert(...)` dùng chung biến kiểu nào? `echo(...)` có đọc `T` của class không? Nếu có hai lần gọi `convert` lần lượt trả `String` và `Long`, `R` được chọn theo từng lời gọi hay cố định trên object? (Đáp án: chung `T` của class; `echo` không dùng `T`; `R` thuộc từng lời gọi.)

### Generic constructor cũng có biến kiểu riêng

Một constructor có thể khai báo `<U>`, khác với biến kiểu của class. Ví dụ độc lập ở mức khai báo:

```java
class Container<T> {
    final T value;

    <U> Container(U source,
                  java.util.function.Function<? super U, ? extends T> convert) {
        this.value = convert.apply(source);
    }
}
```

Với `Container<Integer> x = new Container<>("123", Integer::parseInt);`, type parameter **class** là `T=Integer`, còn type parameter **constructor** `U` có thể suy luận là `String`. Constructor chuyển `U` sang `T`, nhờ đó giữ được quan hệ kiểu giữa dữ liệu đầu vào và trường kết quả.

Không đặt `<U>` là type argument cho class nếu nó đang được khai báo trước constructor. Chỗ đứng của phần khai báo là chìa khóa để đọc đúng scope.

## 6. Một phương pháp chú giải chữ ký dài

Xét chữ ký tự thiết kế:

```java
static <S, R> java.util.List<R> map(
        java.util.List<? extends S> source,
        java.util.function.Function<? super S, ? extends R> converter)
```

Đây là **chữ ký minh họa**, chưa có thân phương thức. Có thể lập bảng trước khi đọc logic:

| Ký hiệu | Được khai báo tại | Ràng buộc xuất hiện | Vai trò |
| --- | --- | --- | --- |
| `S` | `<S,R>` của method | `? extends S`, `? super S` | Kiểu đầu vào của phép biến đổi |
| `R` | `<S,R>` của method | `? extends R`, `List<R>` | Kiểu kết quả |
| `? extends S` | Wildcard trong `List` | Phụ thuộc `S` | Danh sách nguồn cung cấp phần tử tương thích `S` |
| `? super S` | Wildcard trong `Function` | Phụ thuộc `S` | Function nhận được giá trị `S` |
| `? extends R` | Wildcard trong `Function` | Phụ thuộc `R` | Function tạo giá trị tương thích `R` |

Cách đọc bằng tiếng Việt: “Phương thức nhận danh sách chứa các giá trị có thể đọc như `S`, cùng một phép biến đổi nhận được `S` và tạo ra `R`; kết quả là danh sách `R`.”

Bắt đầu từ **kết quả và mối quan hệ** rồi mới đọc sâu wildcard. Đừng cố gán cho từng ký hiệu `?` một loại cụ thể trong đầu; wildcard là một giới hạn khả năng, còn type parameter có tên là điểm nối các vị trí liên quan.

### Đặt các loại cụ thể vào bảng

Nếu lời gọi dùng `List<Integer>` và một hàm đổi số thành chuỗi, một cách suy luận hợp lệ là `S=Integer` và `R=String`. Khi đó:

- `List<Integer>` phù hợp với `List<? extends Integer>`.
- Hàm nhận `Integer` phù hợp với `Function<? super Integer, ? extends String>`.
- Kết quả `List<R>` có kiểu `List<String>`.

Phần type inference thật có thể có nhiều ứng viên rồi chọn theo các ràng buộc và ngữ cảnh. Mô hình thay `S=Integer`, `R=String` là cách đọc một invocation cụ thể, không phải thuật toán đầy đủ của `javac`.

## 7. Bounded type parameter: ràng buộc bắt đầu từ khai báo

Type parameter có thể mang **bound**. Nhìn ví dụ:

```java
static <T extends Number> double twice(T value)
```

Đọc `<T extends Number>` trước: chỉ nhận kiểu phù hợp với `Number`, giúp thân phương thức gọi `value.doubleValue()`.

### Chương trình hoàn chỉnh

Tạo `BoundSignatureDemo.java`:

```java
public class BoundSignatureDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static <T extends Comparable<? super T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(twice(1.25));
        System.out.println(larger("cat", "dog"));
    }
}
```

Chạy:

```bash
javac BoundSignatureDemo.java
java BoundSignatureDemo
```

`stdout`:

```text
6.0
2.5
dog
```

#### Đọc `<T extends Number>`

- `T` được khai báo tại method và bị **giới hạn** bởi `Number`.
- `T value` nhận giá trị có kiểu phù hợp bound.
- `double` là kiểu trả về cụ thể, **không** phải `T`. Do đó gọi `twice(Integer)` hay `twice(Double)` đều trả primitive `double`.
- `twice("3")` không thỏa bound và không biên dịch.

#### Đọc `<T extends Comparable<? super T>>`

- `T` được khai báo tại method, đồng thời xuất hiện ngay trong **bound của chính nó** (recursive bound).
- `Comparable<? super T>` nghĩa là giá trị kiểu `T` có thể so sánh với đối tượng `T` qua một interface `Comparable` chấp nhận `T` hoặc supertype phù hợp của `T`.
- `T a` và `T b` liên kết hai đối số với kiểu trả về `T`.
- `a.compareTo(b)` hợp lệ vì bound cho compiler chứng minh khả năng so sánh.

Điểm cần nắm ở bước đầu là “bound cung cấp những thao tác mà compiler cho phép trên `T`”. Nếu phần `Comparable<? super T>` còn khó, trước tiên tự viết biến thể đơn giản `<T extends Comparable<T>>` và thử với `String`; sau đó trở lại lower-bound wildcard để hiểu vì sao mẫu linh hoạt hơn tồn tại.

### Multiple bounds

Ví dụ cú pháp:

```java
<T extends Number & Comparable<T>>
```

`T` phải thỏa cả hai cận. Nếu có **cận class**, nó phải đứng đầu; các interface theo sau dấu `&`. `extends` xuất hiện ngay cả khi cận là interface. Một biến kiểu không có `extends` tường minh mặc định có bound `Object` theo mô hình type parameter thông thường.

Không đồng nhất `<T extends Number>` với `List<? extends Number>`:

- `<T extends Number>` **khai báo một biến kiểu có tên** `T` cùng cận trên.
- `List<? extends Number>` **sử dụng wildcard** tại vị trí type argument của `List`; nó không tạo tên `T` để người viết dùng ở nơi khác.

## 8. Type parameter và wildcard: hai loại “liên kết” khác nhau

Trong chữ ký, `T` có thể xuất hiện ở nhiều nơi để khẳng định một quan hệ; hai wildcard `?` không mặc nhiên cùng một loại.

### Ví dụ so sánh

```java
static <T> T chooseFirst(java.util.List<T> values)

static Object chooseFirstUnknown(java.util.List<?> values)
```

Đây là hai chữ ký minh họa, chưa có thân. Với `List<String>`:

- `chooseFirst` có thể trả kiểu tĩnh `String` vì `T` liên kết phần tử đầu vào và kết quả.
- `chooseFirstUnknown` chỉ hứa trả `Object` vì không liên kết kiểu trả về với wildcard.
- `List<?>` vẫn giữ kiểu an toàn khi **đọc**: lấy ra `Object` là an toàn; cố thêm phần tử khác `null` bằng `add` bị hạn chế ở compile time.

### Vì sao không đổi mọi `T` thành `?`?

Cú pháp như `? first(List<?> values)` là **không hợp lệ**: wildcard chỉ được dùng trong những vị trí type argument thích hợp, không dùng thay cho một return type độc lập. Nếu kiểu trả về phải phụ thuộc kiểu đầu vào, hãy khai báo type parameter và dùng cùng biến ở hai vị trí.

### Cùng một chữ ký có cả wildcard và T

Ví dụ:

```java
static <T> void copy(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source)
```

Phân tích:

- `T` được khai báo tại method.
- `source` là nơi **cung cấp** giá trị đọc được như `T`: `? extends T`.
- `destination` là nơi **nhận** giá trị `T`: `? super T`.
- Dù hai tham số là hai danh sách có type arguments khác nhau, chúng cùng **tham chiếu vào một `T`** để bảo đảm thao tác chuyển phần tử an toàn.
- Wildcard riêng của `source` và `destination` không phải hai lần định nghĩa `T` mới.

Mẫu này thể hiện quy tắc **PECS** (Producer Extends, Consumer Super). Đây là công cụ đọc chữ ký; không phải mệnh lệnh phải dùng wildcard trong mọi API. Nếu vừa đọc vừa ghi một danh sách với kiểu chính xác cần liên kết, `List<T>` có thể đơn giản hơn.

### Wildcard là kiểu chưa biết, không phải Object

`List<?>` không đồng nghĩa `List<Object>`. `List<Object>` chấp nhận thêm mọi đối tượng, còn `List<?>` giữ an toàn trước một loại phần tử cụ thể nhưng không được người gọi biết. Bất kể compiler có thể đọc phần tử `List<?>` dưới dạng `Object`, nó không cho phép thêm tùy ý một `Object`.

## 9. Đọc type arguments lồng nhau

Đừng chỉ nhìn một tầng `<...>`. Với:

```java
Map<String, List<Integer>>
```

Hãy đi từ ngoài vào trong:

1. `Map<K,V>` có hai type parameters; ở đây `K=String` và `V=List<Integer>`.
2. `List<E>` nằm bên trong `V`; ở đây `E=Integer`.
3. Phương thức `Map.put(K,V)`, sau khi áp dụng type arguments, yêu cầu khóa `String` và giá trị `List<Integer>`.
4. `Map.get(Object)` nhận `Object` làm key argument theo chữ ký thư viện, nhưng kiểu trả về của `get` vẫn là `V` (tức `List<Integer>`) đối với biến Map này; có thể trả `null` khi không có ánh xạ.

Tạo `NestedSignatureDemo.java`:

```java
import java.util.List;
import java.util.Map;

public class NestedSignatureDemo {
    public static void main(String[] args) {
        Map<String, List<Integer>> marks = Map.of(
                "Lan", List.of(8, 9),
                "Mai", List.of(7));

        List<Integer> lanMarks = marks.get("Lan");
        Integer first = lanMarks.get(0);

        System.out.println(lanMarks);
        System.out.println(first);
    }
}
```

Chạy `javac NestedSignatureDemo.java`, `java NestedSignatureDemo`:

```text
[8, 9]
8
```

Hãy lần ngược kiểu của `first`: `Map<String,List<Integer>>` → `get("Lan")` trả `List<Integer>` → `get(0)` trên List trả `Integer`. Nếu gọi `marks.put(...)` ở ví dụ, `Map.of` tạo immutable map nên việc sửa đổi sẽ ném `UnsupportedOperationException` tại runtime ngay cả khi kiểu của cặp khóa–giá trị hợp lệ. **Hợp lệ về generic type không đồng nghĩa object cho phép mutation.**

### Generic type không có nghĩa mọi tham số method đều là type argument

Trong `Map<K,V>`, phương thức `get(Object key)` cố ý nhận `Object` theo API. Người đọc phải tra chữ ký thực, không suy đoán thành `get(K key)`. Tương tự, `Collection<E>.contains(Object o)` nhận `Object`. Generic signature xác định những gì compiler bảo đảm; đừng suy diễn dựa trên một tên biến.

## 10. Trường hợp T có trong kiểu của lớp cha hoặc interface

Một class có thể **đóng cố định** type argument của interface cha:

```java
interface Reader<T> {
    T read();
}

class NameReader implements Reader<String> {
    @Override
    public String read() {
        return "Lan";
    }
}
```

Đây là mã khai báo minh họa. `Reader<T>` khai báo biến `T`; `NameReader implements Reader<String>` cung cấp type argument `String`, do đó method triển khai phải đáp ứng hợp đồng `String read()` tại mức mã nguồn.

Một class con cũng có thể **chuyển tiếp** type parameter:

```java
class IdentityReader<T> implements Reader<T> {
    private final T value;

    IdentityReader(T value) {
        this.value = value;
    }

    @Override
    public T read() {
        return value;
    }
}
```

Lần theo từ `IdentityReader<T>` (khai báo) đến `Reader<T>` (sử dụng) rồi tới `T read()`. Chữ `T` trong `Reader<T>` ở vế `implements` là **type argument** truyền cho interface, dù cùng tên với type parameter của class đang khai báo.

Ví dụ mở rộng: `class Result<T> extends Container<List<T>>` có nghĩa type parameter `T` của `Result` được lồng trong `List<T>` và cả `List<T>` làm type argument cấp cha `Container`. Muốn hiểu method thừa kế, phải lần theo từng ánh xạ type argument như vậy.

### Phân biệt override và overload khi đọc generic method

Nếu interface yêu cầu `T read()` và class triển khai `Reader<String>`, compiler kiểm tra method `String read()` theo hợp đồng đã chuyên biệt hóa. Sau type erasure, compiler có thể sinh bridge method để giữ đa hình; bạn không cần tự viết bridge. Trong khi đó hai overload `void use(List<String>)` và `void use(List<Integer>)` trong cùng class không phân biệt được sau erasure và bị lỗi name clash.

Điểm thực hành: khi một phương thức kế thừa “bỗng trả String”, đừng tìm `<String>` ngay trên method. Hãy lần từ interface/class cha qua `implements`/`extends` để biết biến kiểu được ràng buộc ở đâu.

## 11. Đọc một số chữ ký Java Core theo quy trình

Các chữ ký dưới đây được trình bày để đọc quan hệ kiểu. Một vài khai báo được rút gọn chỉ bỏ modifier/annotation không quyết định quan hệ kiểu; nếu cần tài liệu API chính xác của một phiên bản JDK, kiểm tra JavaDoc tương ứng.

### 11.1. `List<E>`: type parameter ở interface

Chữ ký liên quan:

```java
interface List<E> {
    boolean add(E element);
    E get(int index);
}
```

Đây là trích mô hình để đọc, không phải toàn bộ interface JDK.

Ánh xạ `List<String>` → `E=String`:

| Thành viên | Kiểu sau khi áp dụng `E=String` |
| --- | --- |
| `add(E element)` | Tham số được compiler xem là `String` |
| `E get(int index)` | Kết quả được compiler xem là `String` |
| `int index` | Vẫn là `int`, không phụ thuộc `E` |

`List<E>` chỉ khai báo **một** type parameter; nó không khai báo lại `E` trên từng method.

### 11.2. `Map<K,V>`: hai type parameters độc lập

Một số thành viên:

```java
V put(K key, V value);
V get(Object key);
Set<Map.Entry<K, V>> entrySet();
```

Với `Map<String, Integer>`:

- `put` nhận `String` và `Integer`, trả `Integer` (có thể `null` theo hành vi map).
- `get` nhận `Object`, trả `Integer` (cũng có thể `null`).
- `entrySet` trả `Set<Map.Entry<String, Integer>>`, gồm **hai tầng generic lồng**.

Nếu chưa rõ `Map.Entry<K,V>`, hãy lập bảng ánh xạ tiếp: `Entry.getKey()` có kiểu `K`, `Entry.getValue()` có kiểu `V`. Không thêm một type parameter mới ở `entrySet`; nó dùng cặp đã khai báo tại `Map`.

### 11.3. `Collections.copy`: PECS và một T nối hai list

Chữ ký method JDK:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

- `<T>` khai báo một type parameter của **method static**.
- `void`: method không trả phần tử nào; `T` chỉ liên kết hai tham số.
- `src` cung cấp phần tử như `T`; `dest` nhận `T`.
- Không giả định hành vi “append”: `Collections.copy` **thay** các vị trí hiện có của danh sách đích; danh sách đích phải có ít nhất số phần tử bằng source, nếu không ném `IndexOutOfBoundsException`.

Tạo `CopySignatureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class CopySignatureDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4);
        List<Number> target = new ArrayList<>(
                Arrays.asList(0, 0, 0));

        Collections.copy(target, source);
        System.out.println(target);
    }
}
```

Chạy:

```bash
javac CopySignatureDemo.java
java CopySignatureDemo
```

`stdout`:

```text
[2, 4, 0]
```

Tại invocation này, `T=Integer` là một lựa chọn hợp lệ: `List<Integer>` phù hợp `List<? extends Integer>`; `List<Number>` phù hợp `List<? super Integer>`. `Collections.copy` thay hai phần tử đầu, giữ phần tử thứ ba. Nếu dùng `List.of(0,0,0)` làm đích thì dù kích thước đủ, danh sách không hỗ trợ `set` và sẽ gây lỗi runtime; chữ ký generic không cam kết tính mutable.

### 11.4. `Comparator.comparing`: một method, hai biến kiểu

Chữ ký overload thường dùng trong JDK:

```java
public static <T, U extends Comparable<? super U>>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor)
```

Tách theo thứ tự:

1. `<T, U extends Comparable<? super U>>` khai báo hai type parameters thuộc **method**.
2. `U` có bound yêu cầu giá trị trích ra có thể so sánh; `T` không có bound tường minh.
3. `Function<? super T, ? extends U>` nhận một đối tượng kiểu `T` và cho ra key tương thích `U`.
4. `Comparator<T>` là kiểu trả về, nghĩa là một comparator dùng cho các đối tượng `T`; **không** phải `Comparator<U>`.
5. Với `Comparator.comparing(String::length)`, kiểu key có thể là `Integer` (`U=Integer`), còn loại đối tượng đem so sánh là `String` (`T=String`) khi ngữ cảnh đủ để inference xác định.

Để tránh các vấn đề target typing với method reference khi thử độc lập, có thể viết `Comparator.<String, Integer>comparing(String::length)` hoặc `Comparator.comparing((String s) -> s.length())`. Cách viết explicit type witness không tạo một generic class mới, chỉ làm rõ type arguments của **lời gọi method**.

Tạo `ComparatorSignatureDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorSignatureDemo {
    public static void main(String[] args) {
        Comparator<String> byLength =
                Comparator.comparing((String s) -> s.length());

        String longest = List.of("go", "java", "api")
                .stream()
                .max(byLength)
                .orElseThrow();

        System.out.println(longest);
    }
}
```

Chạy `javac ComparatorSignatureDemo.java` và `java ComparatorSignatureDemo`:

```text
java
```

Hãy ghi hai cột riêng: `T=String` đại diện đối tượng được so sánh; `U=Integer` đại diện khóa trích xuất để so sánh. Không đồng nhất `T` và `U` chỉ vì chúng cùng một method.

### 11.5. `Optional.map`: type parameter của class cộng type parameter của method

Chữ ký JDK:

```java
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper)
```

Chữ ký này là một **instance method bên trong `Optional<T>`**:

- `T` đến từ khai báo **class** `Optional<T>`; không phải do `map` khai báo.
- `<U>` là khai báo biến kiểu **của method `map`**.
- `mapper` nhận được kiểu `T` và tạo giá trị tương thích `U`.
- Kết quả `Optional<U>` giữ kiểu của giá trị được biến đổi, khác với `Optional<T>` đầu vào.

Tạo `OptionalSignatureDemo.java`:

```java
import java.util.Optional;

public class OptionalSignatureDemo {
    public static void main(String[] args) {
        Optional<Integer> length = Optional.of("Java")
                .map(String::length);

        System.out.println(length.orElse(0));
    }
}
```

Chạy `javac OptionalSignatureDemo.java`, `java OptionalSignatureDemo`:

```text
4
```

`Optional.of("Java")` tạo `Optional<String>`; tại invocation của `map`, `T=String` và `U=Integer`. Phương thức `map` trả `Optional<Integer>`; `orElse(0)` trả `Integer` rồi được in ra. Trường hợp mapper trả `null`, `Optional.map` tạo optional rỗng theo hợp đồng JDK, không tự chuyển thành `Optional<null>`.

## 12. Method type inference: ràng buộc tại nơi gọi

Tới đây cần tách **khai báo** và **áp dụng**. Với:

```java
static <T> T pick(T first, T second) {
    return first;
}
```

Chữ ký có một `T`, nhưng compiler không luôn suy luận kiểu chỉ dựa vào “lớp runtime của hai đối số phải bằng nhau”. Ví dụ `pick(10, 20)` có thể dùng `T=Integer`; một lời gọi với các giá trị khác loại có thể suy luận một supertype hoặc intersection type phù hợp, tùy ngữ cảnh. Vì vậy “cùng T” có nghĩa các biểu thức phải **cùng thỏa nghiệm ràng buộc cho type variable**, không nhất thiết phải cùng exact class.

### Ngữ cảnh mục tiêu có thể ảnh hưởng suy luận

```java
import java.util.Collections;
import java.util.List;

public class InferenceDemo {
    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        List<String> empty = Collections.emptyList();
        String word = InferenceDemo.<String>identity("typed");
        System.out.println(empty.size());
        System.out.println(word);
    }
}
```

Chạy `javac InferenceDemo.java` và `java InferenceDemo`:

```text
0
typed
```

`Collections.emptyList()` khai báo generic method `<T> List<T> emptyList()`; dù không có đối số truyền vào, kiểu đích `List<String>` giúp suy luận `T=String`. `InferenceDemo.<String>identity("typed")` truyền type witness minh thị. Nếu truyền kiểu không thỏa tham số method hoặc bound, compiler từ chối.

### Diamond và `var` không giống nhau

`List<String> words = new ArrayList<>();` suy luận type arguments cho constructor/class từ mục tiêu. `var words = new ArrayList<String>();` để compiler suy ra **kiểu biến cục bộ** từ initializer. `var` không khai báo type parameter mới; nó chỉ yêu cầu compiler suy ra một kiểu tĩnh tại điểm khai báo. Những biểu thức thiếu ngữ cảnh có thể khiến kiểu suy ra rộng hơn dự định; hãy xem kiểu mà IDE/compiler suy ra thay vì mặc định đoán là `String`.

### Overload resolution và generic

Khi có overload, compiler dùng kiểu tĩnh, inference, quy tắc applicability và specificity để chọn method. Không nên nhìn một `<T>` đơn lẻ rồi khẳng định overload được chọn trước khi xem các lời gọi và overload khác. Trong cùng class, hai method chỉ khác `List<String>`/`List<Integer>` sẽ xung đột do type erasure; generic không cho tạo overload kiểu đó.

## 13. Phạm vi (scope) và điểm ràng buộc: đừng nhầm nơi xuất hiện tên

Những vị trí khai báo thường gặp:

| Vị trí | Cú pháp | Phạm vi sử dụng tiêu biểu |
| --- | --- | --- |
| Class | `class Box<T> { ... }` | Thành viên instance và khai báo bên trong vùng scope phù hợp |
| Interface | `interface Repository<ID,E> { ... }` | Phương thức/kiểu trả về của interface và subtype áp dụng |
| Record | `record Pair<K,V>(K key, V value) {}` | Components, accessor và hành vi instance |
| Method | `<T> T method(T x)` | Tham số, return type, throws/implementation phù hợp |
| Constructor | `<U> Box(U x)` | Constructor đó |
| Generic supertype usage | `implements Reader<String>` | Ràng buộc `T` của `Reader<T>` thành `String` cho subtype |
| Type argument usage | `Class<T> token` | Dùng `T` đã có trong scope làm argument cho một generic khác |

Cách theo dõi thực tế bằng “sổ cái biến kiểu”:

```text
Chữ ký:
class Cache<K, V> {
    V put(K key, V value)
    <R> R convert(V value, Function<? super V, ? extends R> f)
}

Biến   Nơi khai báo    Ràng buộc trong chữ ký
K      Cache<K,V>      key của put
V      Cache<K,V>      value/return của put;
                      parameter value và input f của convert
R      <R> convert     output f và return của convert
```

Mã này là **sơ đồ chữ ký**, không phải class Java chạy độc lập. Khi đọc `Cache<String,Integer>`, điền `K=String`, `V=Integer`. Một invocation `convert` có thể chọn `R=String`, invocation khác có thể chọn `R=Long` trên cùng đối tượng `Cache<String,Integer>`. Đó là lý do phải ghi cột **nơi khai báo**, thay vì chỉ ghi “T là kiểu dữ liệu”.

### Cảnh báo về shadowing

Tên type parameter có thể gây hiểu lầm khi nhiều cấp scope dùng ký hiệu ngắn giống nhau. Trong code sản xuất nên chọn tên khác (`T` của class, `R` của method) để tránh đọc nhầm. Một biến kiểu khác tên **không** tự liên hệ với biến kiểu thứ nhất chỉ vì cả hai đều có bound `Object` hay cùng xuất hiện trong chữ ký.

Một lời gọi method có thể suy luận hai type parameters thành cùng một kiểu cụ thể, nhưng đó là **nghiệm của invocation**, không phải bằng chứng hai parameters được khai báo đồng nhất. Nếu người viết muốn một quan hệ kiểu đồng nhất cố định, dùng cùng một named type parameter ở các vị trí cần thiết.

## 14. Type erasure: theo dõi ràng buộc ở compile time, không suy ra “kiểu runtime T”

Trong Java, type variables và type arguments đa phần được xử lý bằng **type erasure**:

- `T` không có bound thường được xóa thành `Object`.
- `T extends Number` xóa về `Number`.
- Với multiple bounds, erasure của `T` dựa vào **cận đầu tiên**.
- Compiler có thể chèn cast và bridge method.
- `List<String>` và `List<Integer>` dùng cùng runtime class `ArrayList` nếu đều khởi tạo bằng `ArrayList`.

Tạo `SignatureRuntimeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SignatureRuntimeDemo {
    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();

        System.out.println(strings.getClass() == integers.getClass());
        System.out.println(strings instanceof List<?>);
    }
}
```

Chạy:

```bash
javac SignatureRuntimeDemo.java
java SignatureRuntimeDemo
```

`stdout`:

```text
true
true
```

Điều này không phủ nhận quan hệ kiểu mà compiler vừa kiểm tra. Nó chỉ cho thấy runtime object thông thường không lưu `String`/`Integer` làm type argument riêng để JVM kiểm tra trên từng collection.

Cần phân biệt metadata của **khai báo** với đối số kiểu của **một đối tượng**. `Field.getGenericType()` có thể đọc generic signature còn lưu trong class file của một trường; `new ArrayList<String>().getClass()` không tự trả về “ArrayList of String”. Trong API có liên quan reflection hoặc serialize dữ liệu, nhà phát triển đôi khi cung cấp `Class<T>`, `Type` hoặc type token để mang thêm mô tả kiểu vào runtime.

### Một ví dụ lỗi ràng buộc bị vượt qua

```java
List<String> labels = new ArrayList<>();
List raw = labels;
raw.add(17);
String label = labels.get(0);
```

Đoạn chỉ nhằm minh họa, cần import và đặt vào phương thức trước khi chạy. `raw.add(17)` gây unchecked warning nhưng có thể qua compiler; `labels.get(0)` khi dùng thành `String` có thể gây `ClassCastException` bởi cast runtime. Lần ngược từ nơi cast thất bại tới raw alias để tìm chỗ hợp đồng `List<String>` bị phá. Dùng `javac -Xlint:rawtypes -Xlint:unchecked` giúp phát hiện các đường đi nguy hiểm.

## 15. Những lỗi suy luận khi đọc chữ ký

| Cách đọc sai | Vì sao sai | Cách đọc đúng |
| --- | --- | --- |
| “`T` là một class cụ thể.” | `T` là biến kiểu khai báo tại source. | Tìm `<T>` và nơi truyền/suy luận type argument. |
| “Hai method cùng viết `<T>` thì cùng một T.” | Scope method độc lập. | Lập bảng riêng cho từng method. |
| “`List<?>` là `List<Object>`.” | Wildcard bảo vệ kiểu phần tử chưa biết. | Đọc ra `Object` an toàn; không được thêm tùy ý. |
| “`<T extends Number>` và `<? extends Number>` giống nhau.” | Một bên khai báo named type parameter, một bên dùng wildcard. | Xác định dấu `<...>` nằm ở vị trí khai báo hay argument. |
| “`List<Integer>` là `List<Number>`.” | Generic type arguments mặc định invariant. | Dùng `? extends Number` khi chỉ đọc nguồn. |
| “`? super Integer` cho đọc trực tiếp Integer.” | Loại danh sách có thể là `List<Object>`. | Kiểu đọc an toàn chung là `Object`. |
| “Method generic phải dùng `T` trong kiểu trả về.” | `<T>` có thể chỉ ràng buộc tham số, hoặc return là `void`. | Theo dõi tất cả vị trí `T` thực sự xuất hiện. |
| “`Map<K,V>.get` nhất định nhận `K`.” | API cụ thể có thể khai báo `get(Object)`. | Tra chữ ký thành viên; không suy đoán từ kiểu container. |
| “`static` method trong `Box<T>` tự dùng T của class.” | Class-level `T` thuộc ngữ cảnh instance; static không có instantiation riêng. | Khai báo riêng `static <U> U ...` nếu cần. |
| “Các giá trị truyền vào cùng T phải có cùng exact class.” | Type inference có thể chọn supertype phù hợp. | Đọc ràng buộc compile time; đừng đồng nhất với so sánh `getClass()`. |
| “`Collections.copy` nối danh sách.” | Chữ ký kiểu không mô tả đầy đủ hành vi. | Đọc thêm hợp đồng API về size/mutation/index. |
| “Không cần kiểm tra runtime vì đã có generic.” | Raw/unchecked/reflection/dữ liệu ngoài có thể phá hợp đồng. | Kiểm tra dữ liệu tại ranh giới và theo dõi warning. |

## 16. Quy trình đọc một chữ ký lạ trong sáu bước

Khi gặp một signature trong tài liệu hoặc IDE, hãy xử lý theo thứ tự sau:

1. **Chép nguyên chữ ký, giữ đủ các dấu `<...>`.** Tách modifier, tên class/method, kiểu trả về và danh sách tham số. Đừng bỏ cận `extends`/`super`.
2. **Đánh dấu mọi nơi khai báo.** Ghi `class/interface/record <...>`, `method <...>`, `constructor <...>`; phân biệt đó là type-parameter list hay type-argument list.
3. **Vẽ sổ cái cho từng biến kiểu có tên.** Với `K`, `V`, `T`, `U`, ghi bound (nếu có), nơi xuất hiện ở tham số, kiểu trả về, supertype và nested generic.
4. **Khoanh wildcard riêng.** Đọc `? extends X` là phần tử được cung cấp dưới cận `X`; `? super X` là nơi có thể tiêu thụ `X`; `?` là loại chưa biết. Sau đó nối wildcard về named type parameter `X` nếu có.
5. **Áp dụng một lời gọi có kiểu cụ thể.** Ghi rõ `K=String`, `V=Integer` hoặc nghiệm suy luận `T=Integer`, `R=String`. Dịch chữ ký thành kiểu mà caller nhìn thấy; tránh diễn đạt như JVM tạo class generic mới.
6. **Phân biệt giới hạn kiểu với hành vi runtime.** Chữ ký cho biết các phép gọi hợp lệ về kiểu; Javadoc hoặc thân implementation mới cho biết mutability, xử lý `null`, exception, copying và thứ tự.

Chỉ sau khi làm xong sáu bước mới bắt đầu tối ưu hoặc rút gọn API. Nhiều lỗi do đọc lướt `T` mà bỏ qua nơi khai báo ở class so với method.

## 17. Bài thực hành tự kiểm tra

### Bài 1 — Gạch chân nơi khai báo

Cho:

```java
class Store<K, V> {
    V get(K key) { return null; }
    <R> R convert(V value, java.util.function.Function<V, R> f) {
        return f.apply(value);
    }
}
```

Câu hỏi:

1. `K`, `V` và `R` được khai báo ở đâu?
2. Với `Store<String,Integer>`, `get` nhận gì và trả gì?
3. `convert` trên Store này có thể trả `String` không? Điều kiện gì cần cho `Function`?

Đáp án: `K,V` của class; `R` của method `convert`; `get` nhận `String` trả `Integer`; `convert` có thể trả `String` khi nhận function phù hợp kiểu `Function<Integer,String>`. Code minh họa method `get` hiện trả `null`; chữ ký không tự cung cấp lưu trữ thực tế.

### Bài 2 — Tìm nơi type inference hoạt động

Cho:

```java
static <T> java.util.List<T> one(T value) {
    return java.util.List.of(value);
}
```

Dự đoán kiểu biểu thức:

```java
java.util.List<String> a = one("X");
java.util.List<Integer> b = one(7);
```

Đáp án: `T=String` và `T=Integer` ở hai invocation. `List.of` không chấp nhận phần tử `null` theo hợp đồng runtime; kiểu generic `T` không phải một null-check tự động.

### Bài 3 — Phân biệt named type parameter và wildcard

Cho ba chữ ký:

```java
static <T> T first(java.util.List<T> list)
static Object any(java.util.List<?> list)
static void receive(java.util.List<? super Integer> list)
```

Câu hỏi: chữ ký nào liên kết kiểu trả về với phần tử; chữ ký nào chỉ đọc an toàn như `Object`; chữ ký nào cho thêm `Integer`? Đáp án: lần lượt `first`, `any`, `receive`. Đây là các **chữ ký trích**, không có thân nên không tự biên dịch như chương trình độc lập.

### Bài 4 — Lần theo kiểu lồng

Với `Map<String, List<Long>>`, hãy tự suy ra:

- `K=String`, `V=List<Long>`.
- `map.entrySet()` có kiểu `Set<Map.Entry<String,List<Long>>>`.
- `entry.getValue()` có kiểu `List<Long>`.
- `entry.getValue().get(0)` có kiểu `Long`.

Nếu nhầm `V=Long`, quay lại bước đọc từ ngoài vào trong.

### Bài 5 — Đọc method có hai biến kiểu và bound

Cho:

```java
static <T, U extends Comparable<? super U>>
java.util.Comparator<T> by(
        java.util.function.Function<? super T, ? extends U> extractor)
```

Hỏi biến nào là đối tượng cần so sánh, biến nào là khóa so sánh, bound nằm ở đâu, kiểu trả về là gì? Đáp án: `T` là kiểu đối tượng; `U` là key type; `U` có bound `Comparable<? super U>`; kết quả `Comparator<T>`. Chữ ký này mô phỏng quan hệ của `Comparator.comparing`, chưa có implementation.

## 18. Tóm tắt để áp dụng ngay

Mỗi khi đọc generic signature, hãy tạo một bản đồ ngắn theo mẫu:

```text
Định nghĩa:    <T, R extends SomeInterface> ...
Nguồn T:       class hay method? T xuất hiện ở đâu?
Nguồn R:       class hay method? bound của R là gì?
Wildcard:      ? extends T / ? super T / ?
Lời gọi:       T = kiểu nào, R = kiểu nào?
Kết quả:       caller nhận kiểu biểu thức nào?
Runtime:       chữ ký có hứa mutation/null/order/validation không?
```

Đọc `T` như **một quan hệ phải lần theo**, không như tên một kiểu bất kỳ. Đọc `<T>` như vị trí khai báo, `<String>` như một đối số kiểu khi dùng generic, và `<?>` như một type argument chưa biết. Với class-level và method-level type parameter, luôn đánh dấu rõ phạm vi; với chữ ký dài, lập bảng ràng buộc trước khi suy luận. Làm được điều đó, bạn có thể đi từ `List<E>` đến `Optional.map` hay `Comparator.comparing` mà vẫn hiểu đúng compiler đang bảo vệ điều gì.