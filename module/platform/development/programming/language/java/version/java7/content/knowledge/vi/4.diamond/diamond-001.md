# Tham số kiểu ở nơi khai báo và nơi tạo đối tượng: Diamond `<>` trong Java

**Ngữ cảnh:** Java 7 — Diamond (`<>`)  
**Trọng tâm:** Phân biệt tham số kiểu được **khai báo** trong một lớp/interface/phương thức generic, đối số kiểu được **chỉ định** tại vị trí sử dụng và kiểu được **suy luận** khi tạo đối tượng. Những khái niệm này vẫn là nền tảng khi dùng Java 17, 21 hoặc JDK mới hơn.

Khi viết `List<String> names = new ArrayList<>();`, dấu `<>` ở vế phải được gọi là **diamond operator**. Nó giúp tránh lặp lại `String` mà vẫn giữ kiểm tra kiểu trong lúc biên dịch. Dấu `<>` **không** biến danh sách thành “không có kiểu”; trình biên dịch suy ra kiểu phù hợp từ ngữ cảnh.

## 1. Bức tranh tổng thể: ba vị trí cần phân biệt

Xét khai báo:

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

Và cách sử dụng:

```java
Box<String> title = new Box<>("Java");
```

| Vị trí | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| **Nơi định nghĩa lớp** | `class Box<T>` | `T` là **type parameter** (tham số kiểu hình thức): một ký hiệu đại diện kiểu dữ liệu mà người dùng lớp sẽ chọn. |
| **Nơi khai báo biến** | `Box<String> title` | `String` là **type argument** (đối số kiểu thực tế), xác định `T` của biến `title` là `String` trong kiểm tra kiểu. |
| **Nơi gọi constructor** | `new Box<>("Java")` | `<>` yêu cầu trình biên dịch **suy luận** đối số kiểu phù hợp, thay vì viết lặp `new Box<String>("Java")`. |
| **Nơi đọc giá trị** | `String text = title.get()` | `get()` có kiểu trả về `String` theo hợp đồng generic, không cần cast. |

Hình dung luồng thông tin về kiểu:

```text
Định nghĩa kiểu:    Box<T>            T là chỗ dành cho một kiểu
                          |
Sử dụng kiểu:       Box<String>       T được ràng buộc với String
                          |
Tạo đối tượng:      new Box<>("Java") Trình biên dịch suy ra String
                          |
Đọc kết quả:        title.get()       Được kiểm tra như String
```

**Cốt lõi:** `<T>` ở phần định nghĩa **khai báo tên tham số kiểu**; `<String>` ở phần sử dụng **cung cấp đối số kiểu cụ thể**; `<>` khi khởi tạo **nhờ trình biên dịch tìm đối số kiểu** từ ngữ cảnh. Ba dạng viết trông gần giống nhau nhưng không thể thay thế tùy tiện.

## 2. Khai báo tham số kiểu: `<T>`, `<E>`, `<K, V>`

### 2.1. Định nghĩa một lớp generic

`class Box<T>` định nghĩa một lớp có tham số kiểu `T`. Ở bên trong lớp, `T` có thể làm kiểu trường, tham số phương thức và kiểu trả về. Khi viết `Box<String>`, trình biên dịch kiểm tra việc truyền `String` vào và nhận `String` ra theo hợp đồng.

Tên `T` chỉ là **tên ký hiệu**, không phải từ khóa bắt buộc. Các quy ước dễ đọc gồm `T` (Type), `E` (Element), `K` (Key), `V` (Value), `R` (Result). Đối với miền nghiệp vụ phức tạp, có thể dùng tên có ý nghĩa hơn, như `<Request, Response>`.

Một lớp có thể có nhiều tham số kiểu:

```java
final class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
```

Khi dùng `Pair<String, Integer> pair = new Pair<>("retry", 3);`, trình biên dịch suy ra **cả hai** đối số kiểu: `K = String`, `V = Integer`.

### 2.2. Generic interface và generic method

Một **interface** cũng có thể khai báo tham số kiểu, chẳng hạn `interface Repository<ID, Entity>`. Lớp triển khai có thể giữ generic (`class MemoryRepo<ID, Entity> implements Repository<ID, Entity>`) hoặc cố định một số đối số kiểu (`class UserRepo implements Repository<Long, User>`). Quyết định này ảnh hưởng đến hợp đồng của toàn bộ API, độc lập với việc dùng diamond ở constructor.

Phương thức generic có danh sách tham số kiểu riêng:

```java
static <T> T first(java.util.List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("List must not be empty");
    }
    return values.get(0);
}
```

Đây là **đoạn minh họa** đặt trong một lớp, chưa phải chương trình `main` độc lập. Dấu `<T>` **trước kiểu trả về** khai báo tham số kiểu của phương thức. Khi gọi `String firstName = first(List.of("Lan", "Minh"));`, trình biên dịch suy luận `T` cho lời gọi phương thức. Đây là **generic method type inference**, khác với dấu diamond của biểu thức `new`, dù cùng dựa trên suy luận kiểu.

### 2.3. Giới hạn kiểu `extends`

Nếu một API chỉ xử lý số, có thể khai báo `class Measure<T extends Number>`. Khi đó `T` phải là `Number` hoặc kiểu con phù hợp. Diamond **không bỏ qua giới hạn này**:

```java
Measure<Integer> ok = new Measure<>(6);
// Measure<String> wrong = new Measure<>("six"); // Không hợp lệ.
```

Hai dòng trên là **minh họa** khi lớp `Measure<T extends Number>` tồn tại; ví dụ chạy hoàn chỉnh ở phần 4. Ràng buộc có thể dùng cả interface, như `<T extends Comparable<T>>`. Từ khóa `extends` ở giới hạn kiểu generic biểu diễn quan hệ thỏa ràng buộc, bao gồm cả interface.

## 3. Diamond `<>` ở nơi tạo đối tượng

### 3.1. So sánh khai báo đầy đủ và cách viết ngắn

Cả hai phép khởi tạo sau có cùng ý nghĩa kiểm tra kiểu:

```java
java.util.List<String> a = new java.util.ArrayList<String>();
java.util.List<String> b = new java.util.ArrayList<>();
```

Trong cách thứ hai, trình biên dịch đã biết vế trái là `List<String>`, vì vậy nó suy ra đối số kiểu của `ArrayList` là `String`. Diamond được giới thiệu từ **Java 7** và vẫn là cách viết chuẩn, phổ biến khi đối số kiểu ở vế phải đã rõ từ ngữ cảnh.

Ví dụ khác:

```java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
java.util.Set<Long> ids = new java.util.HashSet<>();
Pair<String, Integer> item = new Pair<>("retry", 3);
```

Đây là **các khai báo minh họa** trong phạm vi lớp có định nghĩa `Pair` ở trên. Với `HashMap<K, V>`, trình biên dịch suy luận đồng thời `K = String` và `V = Integer`. Với `Pair<>`, lập luận tương tự áp dụng cho lớp generic tự viết.

**Diamond chỉ là cách viết gọn tại lời gọi constructor** của kiểu generic. Nó không thay việc thiết kế type parameter ở lớp/interface, không tự khai báo các type parameter mới và không có nghĩa là tắt kiểm tra kiểu.

### 3.2. Vì sao diamond khác raw type?

So sánh:

| Cú pháp | Có kiểm tra kiểu generic? | Đánh giá |
| --- | --- | --- |
| `List<String> a = new ArrayList<String>();` | Có | Hợp lệ, nhưng lặp đối số kiểu. |
| `List<String> a = new ArrayList<>();` | Có | **Ưu tiên** khi target type đã rõ. |
| `List<String> a = new ArrayList();` | Gọi constructor bằng **raw type**, có thể phát sinh unchecked conversion warning | Tránh viết mã mới theo cách này. |
| `List a = new ArrayList();` | Biến và constructor đều raw | Mất nhiều bảo vệ kiểu; thường chỉ gặp ở mã cũ cần sửa. |

**`new ArrayList<>()` và `new ArrayList()` không tương đương.** Với diamond, biên dịch giữ hợp đồng generic. Với raw type, trình biên dịch không thể kiểm tra đầy đủ và có thể chấp nhận thao tác khiến dữ liệu sai kiểu đi vào collection rồi thất bại ở chỗ đọc.

Việc một chương trình raw type vẫn biên dịch **không** chứng minh nó an toàn. Khi gặp cảnh báo `unchecked`, nên tìm nguồn dữ liệu và thay raw type bằng kiểu generic chính xác, không che cảnh báo bằng cast hoặc `@SuppressWarnings` nếu chưa chứng minh được điều kiện an toàn.

### 3.3. Suy luận dựa trên ngữ cảnh

JDK hiện đại có thể dùng **target type** từ nhiều vị trí để kiểm tra và suy luận kiểu trong biểu thức:

```java
// A. Từ kiểu của biến:
java.util.List<String> words = new java.util.ArrayList<>();

// B. Từ kiểu trả về của phương thức:
static java.util.List<String> emptyWords() {
    return new java.util.ArrayList<>();
}

// C. Từ kiểu tham số của phương thức:
static void acceptWords(java.util.List<String> values) {
    System.out.println(values.size());
}
static void call() {
    acceptWords(new java.util.ArrayList<>());
}
```

Các đoạn này **minh họa thành viên phương thức trong một lớp**, không chạy độc lập. Trong trường hợp A, kiểu đích ở vế trái là `List<String>`. Trong B, kiểu trả về phương thức là `List<String>`. Trong C, vị trí truyền đối số yêu cầu `List<String>`. Khả năng suy luận cụ thể còn phụ thuộc các quy tắc của phiên bản Java đang dùng; khi viết code mới trên **JDK 17+**, đây đều là tình huống sử dụng bình thường.

Trình biên dịch kết hợp ràng buộc từ target type, các đối số constructor và khai báo generic. Nếu không thể chọn kiểu đáp ứng tất cả ràng buộc, **biên dịch thất bại**; diamond không cố ép kiểu sai thành đúng.

## 4. Ví dụ hoàn chỉnh: lớp generic, diamond và nhiều đối số kiểu

Lưu tệp `DiamondBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DiamondBasicsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Minh");

        Box<Integer> score = new Box<>(42);

        Map<String, Integer> lengths = new LinkedHashMap<>();
        for (String name : names) {
            lengths.put(name, name.length());
        }

        System.out.println(names);
        System.out.println(score.get());
        System.out.println(lengths);
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 DiamondBasicsDemo.java
java DiamondBasicsDemo
```

Kết quả chính xác:

```text
[Lan, Minh]
42
{Lan=3, Minh=4}
```

Giải thích dòng quan trọng:

- `List<String> names`: đối số kiểu tại **nơi khai báo biến** là `String`. `new ArrayList<>()` suy ra cùng kiểu mà không lặp lại `String`.
- `Box<Integer> score = new Box<>(42)`: lớp định nghĩa `<T>`, còn biến này ràng buộc `T = Integer`. Số nguyên `42` được boxing thành đối tượng `Integer` theo hợp đồng generic.
- `Map<String, Integer> lengths = new LinkedHashMap<>()`: suy ra hai đối số kiểu. Chọn `LinkedHashMap` để kết quả duyệt theo thứ tự thêm vào có thể dự đoán được; việc dùng diamond không liên quan đến thứ tự collection.

Nếu thử viết `names.add(123);`, trình biên dịch báo lỗi kiểu. Hệ thống xác định lỗi này **trước khi chương trình chạy**. Tương tự, `String text = score.get();` không hợp lệ vì `get()` ở đây trả về `Integer`.

## 5. Ví dụ hoàn chỉnh: suy luận kiểu trong generic method và nested generics

Lưu tệp `InferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InferenceDemo {
    static <T> List<T> one(T item) {
        List<T> result = new ArrayList<>();
        result.add(item);
        return result;
    }

    static List<String> emptyWords() {
        return new ArrayList<>();
    }

    static void appendWord(List<String> target) {
        target.add("done");
    }

    public static void main(String[] args) {
        List<String> words = one("hello");
        List<String> empty = emptyWords();

        List<String> target = new ArrayList<>();
        appendWord(target);

        List<List<String>> groups = new ArrayList<>();
        groups.add(new ArrayList<>());
        groups.get(0).add("nested");

        System.out.println(words);
        System.out.println(empty.size());
        System.out.println(target);
        System.out.println(groups);
    }
}
```

```bash
javac -encoding UTF-8 InferenceDemo.java
java InferenceDemo
```

```text
[hello]
0
[done]
[[nested]]
```

Ở `one`, `<T>` **khai báo generic method**, còn `List<T> result = new ArrayList<>()` là **diamond inference** của constructor. Ở `List<List<String>> groups`, type argument của danh sách ngoài là `List<String>`. Khi gọi `groups.add(new ArrayList<>())`, Java dùng ngữ cảnh để tạo phần tử đúng kiểu `List<String>`.

Sự kết hợp này hữu ích khi xây dựng collection lồng nhau. Cần phân biệt đúng cấp: `List<List<String>>` là danh sách của **các danh sách chuỗi**, không phải một `List<String>` đơn lẻ. Có thể truyền `new ArrayList<>()` vào phương thức nhận `List<String>` nếu cú pháp và khả năng suy luận của phiên bản Java đang dùng cho phép.

## 6. `var` và diamond: đừng làm mất thông tin kiểu

Từ **Java 10**, từ khóa `var` cho phép trình biên dịch suy luận kiểu của **biến cục bộ** từ biểu thức khởi tạo. Đây là cơ chế suy luận **kiểu của biến**, còn diamond là suy luận **đối số kiểu tại constructor**. Kết hợp chúng mà không có thêm thông tin kiểu có thể dẫn đến kết quả khác dự định.

So sánh:

```java
List<String> a = new ArrayList<>();  // String từ vế trái
var b = new ArrayList<String>();     // ArrayList<String> từ vế phải
var c = new ArrayList<>();           // ArrayList<Object> khi thiếu ràng buộc cụ thể
```

Đây là **ví dụ cú pháp**, giả sử đã import `List` và `ArrayList`. Trường hợp `c`, trình biên dịch không có `List<String>` ở bên trái để dựa vào, nên suy ra `Object` cho đối số kiểu trong ngữ cảnh này. Gọi `c.add("text")` rồi `c.add(42)` đều hợp lệ, dù người viết có thể tưởng collection chỉ chứa chuỗi.

Lưu `VarDiamondDemo.java`:

```java
import java.util.ArrayList;

public class VarDiamondDemo {
    public static void main(String[] args) {
        var typed = new ArrayList<String>();
        typed.add("safe");

        var broad = new ArrayList<>();
        broad.add("text");
        broad.add(42);

        System.out.println(typed);
        System.out.println(broad);
    }
}
```

```bash
javac -encoding UTF-8 VarDiamondDemo.java
java VarDiamondDemo
```

```text
[safe]
[text, 42]
```

**Khuyến nghị cho mã mới:**

- Khi muốn thể hiện hợp đồng qua interface và kiểu phần tử: `List<String> names = new ArrayList<>();`.
- Khi dùng `var` hợp lý và muốn giữ đúng phần tử: `var names = new ArrayList<String>();`.
- Tránh `var names = new ArrayList<>();` khi thực sự cần `String`; kiểu được suy luận không tự thay đổi khi thêm phần tử về sau.
- `var` không phải kiểu động và không tắt generic type checking: kiểu biến được xác định **ở compile time**.

Sự rõ ràng thường quan trọng hơn việc giảm thêm vài ký tự. Chọn cách viết cho người đọc biết collection thực sự chứa gì ngay tại nơi tạo.

## 7. Ràng buộc kiểu và diamond không làm “rộng” hợp đồng

### 7.1. Generic bounded type

Lưu `BoundedDiamondDemo.java`:

```java
public class BoundedDiamondDemo {
    static final class Measure<T extends Number> {
        private final T amount;

        Measure(T amount) {
            this.amount = amount;
        }

        double twice() {
            return amount.doubleValue() * 2;
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

    public static void main(String[] args) {
        Measure<Integer> measure = new Measure<>(6);
        Pair<String, Integer> pair = new Pair<>("tasks", 3);

        System.out.println(measure.twice());
        System.out.println(pair.key() + ":" + pair.value());
    }
}
```

```bash
javac -encoding UTF-8 BoundedDiamondDemo.java
java BoundedDiamondDemo
```

```text
12.0
tasks:3
```

`Measure<T extends Number>` chỉ chấp nhận đối số kiểu thỏa giới hạn `Number`; `new Measure<>(6)` suy ra kiểu tương thích với `Measure<Integer>`. `Pair<K,V>` có hai type parameter, nên diamond có thể suy luận đồng thời cả hai. Các lệnh sai kiểu vẫn là lỗi biên dịch, dù phần tạo đối tượng không ghi đối số kiểu một cách tường minh.

### 7.2. Generic invariance

`Integer` là subtype của `Number`, nhưng **`List<Integer>` không phải subtype của `List<Number>`**:

```java
java.util.List<Integer> ints = new java.util.ArrayList<>();
// java.util.List<Number> nums = ints; // Không hợp lệ.
```

Diamond không làm thay đổi quy tắc bất biến này. Hai khai báo sau lại hợp lệ vì cùng một đối số kiểu `Number` được dùng theo hợp đồng:

```java
java.util.List<Number> nums = new java.util.ArrayList<>();
nums.add(10);
nums.add(2.5);
```

Nếu một phương thức chỉ đọc số mà không thêm phần tử, có thể dùng `List<? extends Number>`; nếu phương thức cần đưa `Integer` vào danh sách do caller cung cấp, cân nhắc `List<? super Integer>`. Đó là quy tắc thiết kế **wildcard**, độc lập với diamond; không dùng `<>` như một cách để lách những ràng buộc này.

### 7.3. `int` không phải type argument

Type argument của generics là **reference type**. Vì vậy `List<int>` không hợp lệ; sử dụng `List<Integer>`, `List<Long>`... theo nhu cầu. Auto-boxing/unboxing giúp chuyển đổi với số nguyên thủy trong nhiều biểu thức, nhưng collection lưu đối tượng wrapper và có chi phí bộ nhớ/boxing tương ứng.

## 8. Những giới hạn cần hiểu trên Java hiện đại

Generics của Java chủ yếu dựa trên **type erasure**. Đối số kiểu được kiểm tra trong quá trình biên dịch, nhưng không tự tạo ra một class runtime riêng cho từng kiểu. Ví dụ `new ArrayList<String>()` và `new ArrayList<Integer>()` dùng cùng lớp runtime `ArrayList`.

Hệ quả thực tế:

- Không thể kiểm tra `value instanceof List<String>` như một phép kiểm tra type argument tại runtime; có thể kiểm tra `value instanceof List<?>` và kiểm chứng phần tử theo hợp đồng dữ liệu.
- Không thể viết `new T()` trực tiếp chỉ dựa vào type parameter `T`; khi cần tạo đối tượng, truyền factory/constructor hoặc công cụ biểu diễn kiểu thích hợp.
- Không tạo trực tiếp mảng `new List<String>[10]`; với tập phần tử động, thường dùng `List<List<String>>` hoặc cấu trúc có kiểm tra thích hợp.
- Diamond không tự kiểm chứng JSON, dữ liệu reflection hoặc giá trị thô đi qua ranh giới hệ thống. Nếu đầu vào chưa đáng tin, phải validate cấu trúc và kiểu khi giải mã.
- Kiểu ở vế trái nên đủ thông tin để người đọc thấy API muốn gì; thông thường ưu tiên khai báo theo interface, chẳng hạn `Map<String, Integer> map = new HashMap<>();`, nếu không cần đặc tính riêng của lớp thực thi.

Có một số giới hạn cú pháp cần nhớ:

| Viết sai hoặc dễ nhầm | Lý do |
| --- | --- |
| `class Box<> { ... }` | `<>` không khai báo tham số kiểu của lớp. Phải đặt tên, ví dụ `class Box<T>`. |
| `List<> names = new ArrayList<>();` | Phía khai báo kiểu phải xác định type argument hoặc dùng cú pháp hợp lệ khác; không đặt diamond ở đó. |
| `new ArrayList<String><>()` | Không thể vừa ghi đối số kiểu cụ thể vừa đặt diamond cho cùng constructor. |
| `List<String> words = new ArrayList<Integer>();` | Type argument hai phía mâu thuẫn, compile error. |
| `Box<String> title = new Box<>(123);` | Giá trị constructor không thỏa kiểu được yêu cầu nếu `Box(T value)`. |
| `new T()` | Type parameter không phải một class constructor có thể gọi trực tiếp. |

**Dùng diamond với anonymous class:** hỗ trợ đã được mở rộng trong các phiên bản Java sau Java 7 (từ Java 9, có điều kiện về kiểu suy luận). Với mã viết mới trên JDK 17+, không cần tạo anonymous class chỉ để dùng diamond; ưu tiên cú pháp đơn giản, lambda khi hợp với functional interface, hoặc lớp/record rõ ràng khi cần. Việc nhắc đến khả năng này không làm thay đổi hợp đồng phổ biến `new ArrayList<>()`.

## 9. Lựa chọn cú pháp khi viết API và gọi constructor

| Mục tiêu | Cú pháp khuyến nghị | Lý do |
| --- | --- | --- |
| Một collection chuỗi thông thường | `List<String> names = new ArrayList<>();` | Hợp đồng rõ ở vế trái, constructor gọn. |
| Map có khóa `String`, giá trị `Integer` | `Map<String, Integer> counts = new HashMap<>();` | Suy luận cả `K` và `V`. |
| Một lớp bao dữ liệu generic | `Box<Integer> score = new Box<>(42);` | Type argument rõ, constructor không lặp. |
| Biến cục bộ suy luận bằng `var` | `var names = new ArrayList<String>();` | Không vô tình suy ra `Object` khi cần `String`. |
| Danh sách rỗng bất biến | `List<String> empty = List.of();` | API factory hiện đại khi không cần thêm phần tử; đây là suy luận generic của **phương thức**, không phải diamond. |
| Một tập giá trị bất biến | `Set<String> modes = Set.of("read", "write");` | Không cần `new HashSet<>()` nếu thực sự không cần thay đổi tập. |

**Đừng dùng diamond chỉ vì có thể:** nếu cần dữ liệu bất biến, `List.of(...)`/`Set.of(...)` thường diễn đạt ý định tốt hơn và tránh mutable state. Nếu cần collection thay đổi được, `new ArrayList<>()`, `new HashMap<>()` và các cấu trúc tương ứng vẫn là cách viết phù hợp.

## 10. Lỗi thường gặp và cách xử lý

### “Tôi viết `<>` nhưng compiler không biết kiểu”

Kiểm tra xem tại nơi gọi constructor có **target type** hoặc **constructor arguments** đủ rõ không. Ví dụ `var items = new ArrayList<>();` không cung cấp kiểu phần tử cụ thể, nên suy ra `Object`; chỉnh thành `List<String> items = new ArrayList<>();` hoặc `var items = new ArrayList<String>();`.

### “Tôi muốn `List<Number>` nhưng đang có `List<Integer>`”

Vấn đề là **invariance**, không phải thiếu diamond. Chọn đúng hợp đồng: nếu phải lưu `Number` hỗn hợp, khởi tạo `List<Number>`; nếu chỉ đọc các loại số, nhận `List<? extends Number>`; nếu cần sao chép giá trị, có thể chuyển từng phần tử sang collection mới có kiểu đích.

### “Dùng diamond rồi vẫn bị `ClassCastException`”

Hãy kiểm tra nơi dữ liệu đi vào có dùng **raw type**, unchecked cast, reflection hoặc dữ liệu bên ngoài được chuyển đổi không an toàn không. Generics không thể thay runtime validation ở ranh giới. Diamond giúp suy luận kiểu khi **biên dịch** chứ không giám sát mọi phần tử tại runtime.

### “Tôi phải viết generic thế nào trong một lớp có method static?”

Type parameter ở `class Box<T>` thuộc **instance/class API**, không tự dùng được từ ngữ cảnh static như một `T` chưa xác định. Một static generic method tự khai báo `<T>`, chẳng hạn `static <T> Box<T> of(T value)`. Khi viết `Box.of("hello")`, compiler suy luận type argument của **method**, còn `new Box<>(value)` bên trong dùng diamond cho constructor.

### “Có nên để raw type cho ngắn hơn diamond?”

Không. Cú pháp `new ArrayList()` có thể dẫn đến unchecked warnings và giảm kiểm tra kiểu. Diamond `new ArrayList<>()` đã ngắn mà vẫn có generic type inference; hãy dùng kiểu đầy đủ khi target type cần rõ hoặc khi inference không cho kết quả đúng.

## 11. Bài tập thực hành

**Bài 1 — Đọc cú pháp theo ba vị trí.** Cho `class Result<T>` và `Result<String> r = new Result<>("OK");`. Chỉ ra `T` là type parameter, `String` là type argument, và `<>` là yêu cầu suy luận tại constructor. Viết lại lời gọi constructor bằng đối số kiểu tường minh rồi kiểm tra tính tương đương.

**Bài 2 — Tạo class hai tham số kiểu.** Viết `Pair<K, V>` với field, constructor và getter, sau đó tạo `Pair<String, Long>` bằng diamond. Chứng minh trình biên dịch ngăn truyền giá trị `String` cho nơi cần `Long`.

**Bài 3 — Dùng interface ở nơi khai báo.** Tạo `List<String>`, `Set<Integer>`, `Map<String, Integer>` bằng diamond. Thử thêm phần tử đúng/sai kiểu, ghi lại thao tác nào được compiler chấp nhận.

**Bài 4 — So sánh với `var`.** Chạy `VarDiamondDemo`, rồi đổi thành `var broad = new ArrayList<String>();`. Thử thêm số `42` và giải thích vì sao lúc này có compile error.

**Bài 5 — Generic method và constructor.** Viết `static <T> List<T> singleton(T value)`, dùng `List<T> list = new ArrayList<>();` trong thân hàm. Gọi với `String` và `Integer`; xác định phép suy luận ở lời gọi phương thức và phép suy luận trong constructor.

**Bài 6 — Ranh giới kiểu.** Thiết kế hàm nhận `List<? extends Number>` để tính tổng `doubleValue()`. Giải thích tại sao có thể truyền `List<Integer>` và `List<Double>`, nhưng không thể gán một `List<Integer>` trực tiếp vào `List<Number>`.

## 12. Checklist ghi nhớ

- **Ở nơi định nghĩa:** `class Box<T>`, `interface Repo<K, V>` và `static <T> ...` khai báo **type parameter**.
- **Ở nơi sử dụng:** `Box<String>`, `Map<String, Integer>` cung cấp **type argument**; đây là hợp đồng kiểu cần rõ.
- **Ở nơi tạo đối tượng:** `new Box<>()`, `new HashMap<>()` dùng **diamond** để compiler suy ra đối số kiểu theo ngữ cảnh.
- **Diamond khác raw type:** `new ArrayList<>()` giữ kiểm tra generic; `new ArrayList()` dùng raw constructor và có nguy cơ unchecked warning.
- **Đừng kết hợp `var` + diamond mù mờ:** `var xs = new ArrayList<>()` thường suy ra `ArrayList<Object>`; hãy chỉ rõ kiểu phần tử khi cần.
- **Ràng buộc vẫn có hiệu lực:** `extends`, invariance, tham số kiểu có giới hạn và type erasure không biến mất vì diamond.
- **Ưu tiên API hiện hành:** với collection cần sửa, dùng generic + diamond; với dữ liệu bất biến, cân nhắc factory `List.of`/`Set.of`.
