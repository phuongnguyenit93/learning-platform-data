# Phân biệt kiểu khai báo generic với từng cách sử dụng kiểu đó

Trong Java Generics, **khai báo một kiểu generic** và **sử dụng kiểu generic ấy với một đối số kiểu cụ thể** là hai việc khác nhau. Khi viết `class Box<T>`, ta định nghĩa một khuôn mẫu hợp đồng kiểu có tham số `T`. Khi viết `Box<String>` hoặc `Box<Integer>`, ta sử dụng cùng khuôn mẫu đó theo hai cách được kiểm tra kiểu khác nhau.

Nhận ra sự khác biệt này giúp đọc đúng cú pháp `<T>`, `<String>`, `<>`, biết nơi nào khai báo tham số kiểu, nơi nào truyền đối số kiểu và tránh nhầm rằng Java tạo ra một lớp JVM hoàn toàn mới mỗi lần sử dụng generic.

## 1. Một khai báo generic có thể được sử dụng theo nhiều cách

Định nghĩa lớp sau chỉ cần viết **một lần**:

```java
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
```

Đây là toàn bộ nội dung của tệp `Box.java`. `T` là một **tham số kiểu** (*type parameter*) được khai báo trong phần đầu của lớp: `Box<T>`. Nó biểu diễn một kiểu tham chiếu chưa được chốt trong khai báo. Mọi vị trí dùng `T` ở trường, constructor hoặc getter cùng tham chiếu tới tham số kiểu của lớp đó.

Ở mã sử dụng, ta có thể viết:

```java
Box<String> title = new Box<>("Java");
Box<Integer> year = new Box<>(2026);
Box<Double> ratio = new Box<>(0.75);
```

Đây là ba **cách sử dụng** một khai báo `Box<T>`. Trong từng kiểu tham số hóa (*parameterized type*):

- `Box<String>`: `String` là **đối số kiểu** (*type argument*) ứng với `T`.
- `Box<Integer>`: `Integer` là đối số kiểu ứng với cùng vị trí `T`.
- `Box<Double>`: `Double` là đối số kiểu khác; Java không yêu cầu tạo một khai báo lớp mới chỉ để đổi kiểu dữ liệu được lưu.

Các dòng trên là đoạn mã **trong một phương thức** và cần tệp `Box.java` ở cùng nơi biên dịch. Kết quả của `title.get()` có kiểu tĩnh `String`, còn `year.get()` có kiểu tĩnh `Integer`.

| Thành phần | Khai báo generic | Một cách sử dụng generic |
|---|---|---|
| Ví dụ | `class Box<T>` | `Box<String>` |
| Vai trò trong chương trình | Định nghĩa lớp và hợp đồng kiểu dùng lại | Chỉ định cách nhìn một kiểu generic tại điểm dùng |
| Tên trong ngoặc nhọn | `T` là **tham số kiểu** | `String` là **đối số kiểu** |
| Xuất hiện ở đâu? | Phần khai báo `class`, `interface` hoặc `record` generic | Kiểu biến, tham số, kết quả, `new`, kiểu cha được tham số hóa… |
| Số lần viết | Một khai báo có thể phục vụ nhiều nơi | Có thể dùng cùng kiểu generic với nhiều đối số khác nhau |
| Kiểm tra kiểu | Mô tả quan hệ giữa những vị trí dùng `T` | Trình biên dịch áp quan hệ đó cho đối số kiểu đã chọn |

**Điểm cốt lõi:** `Box<T>` là **khai báo** khi viết `class Box<T>`. `Box<String>` là **một kiểu được tham số hóa** khi dùng lớp ấy. Không nên gọi mọi chuỗi ký tự nằm giữa `<...>` là “khai báo generic”.

## 2. Đọc đúng bốn hình thức rất dễ bị nhầm

### 2.1. `class Box<T>`: khai báo tham số kiểu

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` được **giới thiệu** lần đầu trong phần khai báo lớp. Bên trong lớp này, trình biên dịch hiểu `T` là một tham số kiểu hợp lệ và cho phép dùng nó trong những thành phần instance tương ứng.

Nếu thay `T` bằng tên `E` nhất quán trong toàn bộ khai báo, ý nghĩa về cơ bản không đổi. Các tên `T`, `E`, `K` và `V` chỉ là quy ước đặt tên dễ đọc, không phải từ khóa đặc biệt.

### 2.2. `Box<String>`: sử dụng một đối số kiểu cụ thể

```java
// Đoạn minh họa đặt trong thân một phương thức:
Box<String> message;
```

Dòng này **khai báo biến** `message` có kiểu `Box<String>`; nó **không khai báo thêm một lớp generic mới** và cũng chưa tạo đối tượng vì chưa có `new`.

`String` là kiểu đã có. Nó được truyền ở vị trí đối số kiểu, còn tên `T` không cần xuất hiện tại nơi dùng.

### 2.3. `new Box<String>("hello")`: khởi tạo có đối số kiểu tường minh

```java
// Đoạn minh họa đặt trong thân một phương thức:
Box<String> message = new Box<String>("hello");
```

Hai vị trí `<String>` có chức năng liên quan nhưng khác nhau: bên trái diễn đạt kiểu của biến tham chiếu, bên phải chỉ định kiểu cho biểu thức khởi tạo đối tượng.

`"hello"` nằm trong ngoặc tròn là **đối số giá trị cho constructor**, không phải đối số kiểu. Nếu constructor nhận `T` thì, khi `T` tương ứng `String`, đối số giá trị phải có kiểu phù hợp với `String`.

### 2.4. `new Box<>("hello")`: khởi tạo dùng diamond

```java
// Đoạn minh họa đặt trong thân một phương thức:
Box<String> message = new Box<>("hello");
```

Dấu `<>` rỗng là **diamond operator**. Nó báo cho trình biên dịch tự suy luận đối số kiểu của biểu thức `new` dựa trên ngữ cảnh và đối số constructor. Ở đây kiểu đích `Box<String>` giúp suy luận `String`.

**Diamond không có nghĩa lớp được khai báo không còn tham số kiểu.** `Box` vẫn là lớp generic có khai báo `Box<T>`; Java chỉ rút gọn cách chỉ định đối số kiểu ở nơi sử dụng.

## 3. Một ví dụ chạy được: một khai báo, nhiều kiểu sử dụng

Lưu thành **`GenericDeclarationDemo.java`**:

```java
import java.util.List;

public class GenericDeclarationDemo {
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
        Box<String> language = new Box<>("Java");
        Box<Integer> quantity = new Box<>(12);
        Box<List<String>> topics = new Box<>(List.of("type", "generic"));

        String text = language.get();
        Integer count = quantity.get();
        List<String> names = topics.get();

        System.out.println(text.toUpperCase());
        System.out.println(count + 3);
        System.out.println(String.join(" / ", names));
        System.out.println(language.getClass() == quantity.getClass());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 GenericDeclarationDemo.java
java GenericDeclarationDemo
```

Kết quả chính xác của chương trình:

```text
JAVA
15
type / generic
true
```

Giải thích:

1. Chỉ có **một định nghĩa** lớp lồng `Box<T>`.
2. `Box<String>` yêu cầu getter được sử dụng như trả về `String`.
3. `Box<Integer>` yêu cầu getter được sử dụng như trả về `Integer`. Khi cộng `count + 3`, Java tự mở hộp (*unboxing*) giá trị `Integer` thành `int`.
4. `Box<List<String>>` dùng một **kiểu tham số hóa lồng nhau** làm đối số kiểu; `T` ứng với toàn bộ `List<String>`.
5. Biểu thức so sánh `getClass()` trả `true`: hai đối tượng vẫn có cùng lớp runtime `GenericDeclarationDemo.Box`. Điều đó phù hợp với cơ chế **type erasure** và không mâu thuẫn với việc compiler kiểm tra các cách sử dụng khác nhau.

Không có bước nào yêu cầu tạo các lớp `StringBox`, `IntegerBox` hoặc `ListBox` riêng biệt.

## 4. Một khai báo generic nhưng nhiều kiểu tĩnh khác nhau ở mã sử dụng

Hãy phân biệt **kiểu tĩnh của biến** với **lớp runtime của đối tượng**:

```java
// Đoạn minh họa trong một phương thức, đã có class Box<T>:
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(5);
```

Ở thời điểm biên dịch, `a` có kiểu `Box<String>` còn `b` có kiểu `Box<Integer>`. Vì thế:

```java
String first = a.get();
Integer second = b.get();

// Integer wrong = a.get(); // Lỗi biên dịch: String không gán được cho Integer
// String wrong2 = b.get(); // Lỗi biên dịch: Integer không gán được cho String
```

Các dòng lỗi ở trên được chú thích để minh họa hành vi trình biên dịch. Việc thay đối số kiểu làm thay đổi **hợp đồng kiểu ở nguồn Java** mà người sử dụng được phép gọi.

Tuy nhiên, tại runtime, `a` và `b` đều là các thể hiện của lớp `Box`. Khác biệt giữa `Box<String>` và `Box<Integer>` không đồng nghĩa JVM nạp hai định nghĩa lớp độc lập.

Một điều quan trọng khác: **khai báo biến không phải tạo đối tượng**.

```java
// Chỉ khai báo biến cục bộ:
Box<String> emptyReference;

// Tạo đối tượng và gán tham chiếu:
Box<String> initialized = new Box<>("ready");
```

Biến cục bộ `emptyReference` chưa được gán nên không thể đọc nó trước khi gán, dù kiểu `Box<String>` hoàn toàn hợp lệ. Khi sử dụng, cần phân biệt cú pháp kiểu, cú pháp khai báo biến và việc thực sự gọi constructor.

## 5. Khai báo nhiều tham số kiểu và dùng chúng theo đúng vị trí

Một kiểu generic không nhất thiết chỉ có một tham số:

```java
final class Pair<K, V> {
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
```

Trong **khai báo** `Pair<K, V>`, `K` và `V` là hai tham số kiểu riêng biệt. Ở **nơi sử dụng**:

```java
// Đoạn minh họa trong một phương thức:
Pair<String, Integer> stock = new Pair<>("book", 10);
Pair<Integer, String> directory = new Pair<>(404, "Not Found");
```

Với `Pair<String, Integer>`, `K = String` và `V = Integer`. Với `Pair<Integer, String>`, vị trí được hoán đổi. Trình biên dịch không tự suy luận rằng hai kiểu sử dụng đó là tương đương.

| Cách sử dụng | `K` ứng với | `V` ứng với | Kiểu `key()` | Kiểu `value()` |
|---|---|---|---|---|
| `Pair<String, Integer>` | `String` | `Integer` | `String` | `Integer` |
| `Pair<Integer, String>` | `Integer` | `String` | `Integer` | `String` |
| `Pair<String, String>` | `String` | `String` | `String` | `String` |

**Số lượng và thứ tự** đối số kiểu phải phù hợp khai báo. Không thể dùng `Pair<String>` nếu `Pair` yêu cầu hai tham số kiểu, và cũng không thể tạo `Pair<String, Integer, Long>` từ khai báo này.

### Ví dụ hoàn chỉnh cho `Pair<K, V>`

Lưu tệp **`PairUsageDemo.java`**:

```java
public class PairUsageDemo {
    static final class Pair<K, V> {
        private final K key;
        private final V value;

        Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() { return key; }
        V value() { return value; }
    }

    public static void main(String[] args) {
        Pair<String, Integer> stock = new Pair<>("book", 10);
        Pair<Integer, String> code = new Pair<>(404, "Not Found");

        System.out.println(stock.key() + "=" + stock.value());
        System.out.println(code.key() + ": " + code.value());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PairUsageDemo.java
java PairUsageDemo
```

`stdout`:

```text
book=10
404: Not Found
```

Đây tiếp tục là **một khai báo** `Pair<K, V>` với hai cách dùng có thứ tự đối số kiểu khác nhau.

## 6. Khai báo interface generic và các cách triển khai, sử dụng

Giao diện cũng có thể khai báo tham số kiểu:

```java
interface Reader<T> {
    T read();
}
```

`Reader<T>` là **khai báo interface generic**. Các kiểu sau là những **cách sử dụng**:

```java
// Đoạn minh họa trong phần khai báo lớp:
final class StringReader implements Reader<String> {
    @Override
    public String read() {
        return "Java";
    }
}

final class IntegerReader implements Reader<Integer> {
    @Override
    public Integer read() {
        return 21;
    }
}
```

Lớp `StringReader` cố định đối số kiểu của `Reader` thành `String`, còn `IntegerReader` cố định thành `Integer`. Cả hai thực hiện **cùng một khai báo** `Reader<T>` theo hai hợp đồng kiểu khác nhau.

Một lớp khác có thể tiếp tục là generic:

```java
final class FixedReader<T> implements Reader<T> {
    private final T value;

    FixedReader(T value) {
        this.value = value;
    }

    @Override
    public T read() {
        return value;
    }
}
```

Ở đây `FixedReader<T>` **khai báo tham số kiểu của chính lớp** và **chuyển tiếp tham số kiểu ấy** vào giao diện `Reader<T>`. Nơi sử dụng chọn:

```java
// Đoạn minh họa bên trong một phương thức:
Reader<String> title = new FixedReader<>("Java");
Reader<Integer> age = new FixedReader<>(20);
```

Vì thế, cần phân biệt ba trường hợp:

- `interface Reader<T>`: **khai báo** một interface generic.
- `class StringReader implements Reader<String>`: lớp thường **sử dụng** interface bằng đối số kiểu cụ thể.
- `class FixedReader<T> implements Reader<T>`: một **khai báo lớp generic mới**, đồng thời sử dụng interface generic qua tham số kiểu của lớp.

Việc giữ tên `T` ở lớp và interface không có nghĩa chúng tự động dùng chung một biến kiểu từ trước. Mỗi khai báo có phạm vi tham số kiểu riêng; biểu thức `implements Reader<T>` chỉ ra cách lớp mới liên kết tham số kiểu của mình với interface.

## 7. Khai báo phương thức generic cũng khác với lời gọi phương thức ấy

Generics không chỉ dùng ở lớp và interface. Một **phương thức generic** tự khai báo tham số kiểu ở phần đầu chữ ký:

```java
static <T> T echo(T value) {
    return value;
}
```

`<T>` trước kiểu trả về là **khai báo tham số kiểu của phương thức**. Các lời gọi sau là những **lần sử dụng** cùng phương thức:

```java
// Ví dụ bên trong một phương thức của lớp chứa echo:
String text = echo("Hi");
Integer number = echo(9);
```

Trình biên dịch suy luận `T = String` cho lời gọi đầu và `T = Integer` cho lời gọi sau. Không có một định nghĩa phương thức mới được tạo trong mã nguồn mỗi lần gọi.

Khi cần, có thể **chỉ định đối số kiểu tường minh** ngay trước tên phương thức:

```java
String text = GenericMethodDemo.<String>echo("Hi");
```

Cú pháp này khác với cú pháp tạo đối tượng `new Box<String>(...)`. Một phương thức `static` không được lấy trực tiếp tham số kiểu của lớp generic, nên thường cần tự khai báo `<U>` hoặc `<T>`.

### Chương trình chạy được

Lưu thành **`GenericMethodDemo.java`**:

```java
public class GenericMethodDemo {
    static <T> T echo(T value) {
        return value;
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Holder<U> of(U value) {
            return new Holder<>(value);
        }
    }

    public static void main(String[] args) {
        String a = echo("Java");
        Integer b = GenericMethodDemo.<Integer>echo(17);
        Holder<String> c = Holder.of("Generics");

        System.out.println(a);
        System.out.println(b + 1);
        System.out.println(c.get());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GenericMethodDemo.java
java GenericMethodDemo
```

`stdout`:

```text
Java
18
Generics
```

Đọc các vị trí:

- `class Holder<T>`: khai báo tham số kiểu của **lớp**.
- `static <U> Holder<U> of(U value)`: khai báo tham số kiểu riêng của **phương thức static**.
- `Holder<String> c`: sử dụng **lớp** với đối số kiểu `String`.
- `Holder.of("Generics")`: sử dụng **phương thức**; compiler suy luận `U` từ đối số và ngữ cảnh.

## 8. Ranh giới kiểu: một cách sử dụng không thể tùy ý biến thành cách sử dụng khác

Một hiểu nhầm lớn là tưởng rằng `Box<String>` sẽ là kiểu con của `Box<Object>` vì `String` là kiểu con của `Object`. Java generic mặc định **bất biến** (*invariant*):

```java
// Ví dụ đặt trong một phương thức, đã khai báo Box<T>:
Box<String> strings = new Box<>("hello");

// Box<Object> objects = strings; // Không biên dịch
```

Dù hai biến tham chiếu tới các cách tham số hóa của cùng lớp `Box`, Java không cho gán như trên. Nếu cho phép, những API có thao tác ghi theo `Object` có thể đưa đối tượng không phải chuỗi vào hộp vốn được cam kết chứa `String`.

Đối với collection, hậu quả càng rõ:

```java
import java.util.ArrayList;
import java.util.List;

// Đoạn minh họa trong một phương thức:
List<String> names = new ArrayList<>();
names.add("An");

// List<Object> values = names; // Không biên dịch
```

Nếu `List<Object> values = names` được phép, `values.add(123)` sẽ phá hợp đồng `List<String>` mà `names` cần giữ. Chính vì vậy trình biên dịch chặn ngay phép gán.

### Wildcard dùng khi không biết một đối số kiểu cụ thể

Một phương thức **chỉ đọc** giá trị trong hộp có thể chấp nhận:

```java
// Đặt trong một lớp đã có Box<T>:
static void print(Box<?> box) {
    System.out.println(box.get());
}
```

`Box<?>` vẫn là **một cách sử dụng** của kiểu `Box`, nhưng đối số kiểu là wildcard biểu thị một kiểu chưa biết. Nó không khai báo một tham số kiểu tên `?`, và không khẳng định giá trị bên trong là `String` hoặc `Integer`.

Các cách gọi `print(new Box<>("A"))` và `print(new Box<>(5))` đều hợp lệ. Vì kiểu cụ thể chưa biết, kết quả đọc ra có thể sử dụng an toàn như `Object`. Nếu API cần giữ quan hệ kiểu giữa nhiều tham số và giá trị trả về, một phương thức generic `<T>` có tên tham số kiểu riêng có thể diễn đạt quan hệ đó rõ hơn.

**Phân biệt:** `Box<T>` có thể là một cách sử dụng hợp lệ **bên trong phạm vi đã khai báo `T`**, như `class Container<T> { Box<T> box; }`. Ngoài phạm vi ấy, `T` không có nghĩa tự động. Không nên dùng chữ `T` như ký hiệu cho “kiểu bất kỳ” nếu chưa có khai báo hợp lệ.

## 9. Một khai báo có thể đặt giới hạn trên tham số kiểu

Khai báo sau yêu cầu `T` phải là `Number` hoặc kiểu con của nó:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }
}
```

Cách sử dụng hợp lệ:

```java
// Đoạn minh họa trong một phương thức:
NumericBox<Integer> whole = new NumericBox<>(4);
NumericBox<Double> decimal = new NumericBox<>(2.5);
```

Cách dùng không hợp lệ:

```java
// NumericBox<String> bad = new NumericBox<>("x"); // Sai giới hạn T extends Number
```

Ở đây **giới hạn được viết một lần trong khai báo** `NumericBox<T extends Number>`, sau đó áp dụng cho mọi đối số kiểu tại nơi dùng. `<T extends Number>` trong khai báo khác vai trò với `<Integer>` trong cách sử dụng.

Một điểm nữa: đối số kiểu phải là **kiểu tham chiếu**. Vì vậy `Box<int>` không hợp lệ; `Box<Integer>` mới hợp lệ. Java có thể tự đóng hộp số nguyên khi truyền giá trị vào đối tượng tham số hóa bởi `Integer`.

## 10. Diamond và `var`: cùng khai báo, nhưng kiểu được suy luận tại nơi dùng

Java thường suy luận đối số kiểu khi tạo đối tượng:

```java
import java.util.ArrayList;
import java.util.List;

// Trong một phương thức:
List<String> labels = new ArrayList<>();
```

Kiểu đích `List<String>` giúp biểu thức `new ArrayList<>()` được suy luận là `ArrayList<String>`. Đó vẫn là một lần **sử dụng lớp khai báo generic `ArrayList<E>`**, chứ không phải một khai báo kiểu mới.

Với `var`, cần chú ý ngữ cảnh:

```java
// Trong một phương thức:
var names = new ArrayList<String>();
var unknown = new ArrayList<>();
```

- `names` có kiểu tĩnh `ArrayList<String>` vì đối số kiểu của biểu thức khởi tạo đã nêu rõ.
- `unknown` có kiểu tĩnh `ArrayList<Object>` trong ngữ cảnh này, vì không có thông tin nào cụ thể hơn để suy luận tham số kiểu. Do đó `unknown.add("x")` và `unknown.add(123)` đều có thể biên dịch.

Cú pháp `var` **không tạo kiểu động**. Trình biên dịch vẫn chốt một kiểu tĩnh tại chỗ khai báo biến cục bộ. Nếu mục tiêu là danh sách chuỗi, hãy dùng `List<String> names = new ArrayList<>();` hoặc `var names = new ArrayList<String>();`.

## 11. Type erasure: các cách sử dụng không sinh các lớp JVM độc lập

Điểm dễ gây hiểu nhầm nhất nằm ở sự khác biệt giữa **hợp đồng kiểu ở compile time** và **lớp thực tế ở runtime**.

Giả sử:

```java
// Đoạn minh họa trong một phương thức:
Box<String> text = new Box<>("Java");
Box<Integer> number = new Box<>(42);

System.out.println(text.getClass() == number.getClass());
```

Kết quả là `true`. Java dùng cơ chế **type erasure** cho phần lớn thông tin tham số generic; cả hai đối tượng đều dùng cùng lớp runtime `Box`. Lúc biên dịch, compiler vẫn kiểm tra hai kiểu tham số hóa là khác nhau.

Điều này giải thích tại sao cú pháp sau **không hợp lệ**:

```java
// Object item = ...;
// if (item instanceof Box<String>) { } // Không biên dịch
```

JVM không giữ thông tin đối số kiểu theo cách có thể kiểm tra với `instanceof Box<String>`. Có thể dùng `instanceof Box<?>` để kiểm tra đối tượng có phải một `Box` hay không, nhưng kiểm tra ấy **không chứng minh** dữ liệu bên trong là `String`.

### Kiểu raw không đồng nghĩa một cách sử dụng được kiểm tra an toàn

Khi viết:

```java
// Trong một phương thức:
Box raw = new Box("Java");
```

`Box` không có đối số kiểu là **raw type**. Đây là dạng dành cho tương thích với mã Java cũ, làm mất một phần bảo vệ của generic và thường gây cảnh báo `rawtypes` hoặc `unchecked`.

Đừng nhầm:

| Biểu thức/kiểu | Ý nghĩa |
|---|---|
| `Box<T>` trong `class Box<T>` | Khai báo generic, giới thiệu tham số `T`. |
| `Box<String>` | Kiểu tham số hóa sử dụng đối số `String`. |
| `Box<?>` | Kiểu tham số hóa với đối số wildcard chưa biết. |
| `Box` | Raw type, bỏ thông tin đối số kiểu. |
| `new Box<>("value")` | Biểu thức tạo đối tượng với đối số kiểu được suy luận. |

Raw type có thể làm xuất hiện `ClassCastException` ở lúc đọc dữ liệu qua API được tham số hóa, đặc biệt nếu mã không an toàn đã đưa sai loại đối tượng vào cấu trúc dữ liệu. Generic giảm lỗi kiểu bằng kiểm tra biên dịch, nhưng không tự xác thực dữ liệu đến từ nguồn bên ngoài hoặc mã dùng cast không kiểm tra.

## 12. Các lỗi phổ biến khi phân biệt khai báo và sử dụng

| Đoạn mã hoặc suy nghĩ | Vấn đề | Cách hiểu đúng |
|---|---|---|
| “`Box<String>` là một lớp Java mới được định nghĩa.” | Chỉ là cách tham số hóa từ cùng khai báo `Box<T>`. | Định nghĩa lớp ở `class Box<T>`; sử dụng ở `Box<String>`. |
| “`T` trong `Box<T>` lúc nào cũng thay bằng `Object` trong mã nguồn.” | `T` là tham số kiểu có phạm vi và có thể có bound. | Ở mã sử dụng được kiểm tra kiểu, `Box<String>` mang hợp đồng `String`. |
| Viết `Box<T> b` ở phương thức không khai báo `T` | Tên `T` chưa có trong phạm vi. | Dùng kiểu cụ thể, wildcard hoặc khai báo tham số kiểu ở lớp/phương thức. |
| Viết `new Box<>()` rồi nghĩ không dùng generics | Diamond vẫn suy luận đối số kiểu. | Xác định kiểu đích hoặc kiểm tra kiểu được suy luận. |
| Nghĩ `Box<String>` là kiểu con của `Box<Object>` | Generic mặc định bất biến. | Không gán trực tiếp giữa hai kiểu tham số hóa đó. |
| Dùng `Box<int>` | Generics không nhận kiểu nguyên thủy làm đối số kiểu. | Dùng `Box<Integer>`. |
| Dùng `Box raw` như `Box<?>` | Raw type bỏ kiểm tra; wildcard vẫn bảo toàn nhiều quy tắc kiểu generic. | Dùng `Box<?>` khi đối số kiểu chưa biết. |
| Dùng `instanceof Box<String>` | Không thể kiểm tra đối số kiểu đó bằng `instanceof` do erasure. | Dùng `instanceof Box<?>` nếu chỉ cần biết đối tượng có phải Box. |
| Nghĩ mỗi đối số kiểu tạo lớp runtime riêng | Không đúng với cơ chế generics hiện tại của Java. | Một khai báo lớp được dùng với nhiều hợp đồng kiểu lúc biên dịch. |
| Dùng `var values = new ArrayList<>()` rồi mong `List<String>` | Không có kiểu đích buộc đối số kiểu là `String`. | Khai báo rõ đối số kiểu ở ít nhất một vị trí thích hợp. |

## 13. Checklist đọc và viết generic đúng

Khi thấy cú pháp có dấu `<...>`, hãy tự hỏi:

1. **Đang đứng tại khai báo hay nơi sử dụng?** Sau `class`/`interface` và trong `<T>` là khai báo tham số kiểu; trong `Box<String>` ở vị trí kiểu biến là đối số kiểu được cung cấp.
2. **Tên trong ngoặc nhọn có được khai báo chưa?** `T` là tên tham số kiểu, chỉ hợp lệ trong phạm vi khai báo thích hợp.
3. **Có bao nhiêu tham số kiểu, thứ tự ra sao?** Với `Pair<K,V>`, `Pair<String,Integer>` gắn theo đúng thứ tự.
4. **Giới hạn kiểu là gì?** Nếu khai báo `T extends Number` thì `String` không thể dùng làm đối số kiểu.
5. **Biểu thức có tạo đối tượng không?** `Box<String> ref;` chỉ khai báo biến; `new Box<>("x")` mới tạo đối tượng.
6. **Diamond có đủ ngữ cảnh suy luận chưa?** Kiểu đích rõ ràng làm mã dễ đọc, còn `var` có thể khiến suy luận ra `Object`.
7. **Có đang trộn các kiểu tham số hóa khác nhau không?** `Box<String>` không tự gán được cho `Box<Object>`.
8. **Có nhầm compile time với runtime không?** Một lớp runtime `Box` có thể được dùng với nhiều đối số kiểu ở mã nguồn.

### Tự kiểm tra

**Câu 1.** Chỉ ra đâu là khai báo tham số kiểu và đâu là sử dụng đối số kiểu:

```java
class Holder<T> {
    private final T value;

    Holder(T value) { this.value = value; }
    T get() { return value; }
}

// Trong một phương thức:
Holder<String> h = new Holder<>("Hello");
```

**Câu 2.** Tại sao cùng một lớp `Pair<K,V>` lại cho phép `Pair<String,Integer>` và `Pair<Integer,String>` nhưng không đồng nghĩa hai kiểu ấy hoán đổi được cho nhau?

**Câu 3.** `class StaticReader implements Reader<String>` có khai báo tham số kiểu trên chính lớp `StaticReader` không?

**Câu 4.** `Box<?>` và `Box` khác nhau thế nào?

**Câu 5.** Vì sao `new Box<>("x")` có thể suy luận thành `Box<String>`, còn `var list = new ArrayList<>()` thường suy luận đối số kiểu thành `Object`?

**Gợi ý đáp án:** (1) `<T>` sau `Holder` là khai báo, `<String>` trong `Holder<String>` là đối số kiểu, `<>` trong `new Holder<>()` là diamond để suy luận. (2) Các đối số kiểu gắn với những vị trí khác nhau; generic Java mặc định bất biến. (3) Không, `StaticReader` là lớp không generic và chỉ sử dụng giao diện `Reader<String>`. (4) `Box<?>` vẫn giữ một kiểu tham số hóa với đối số chưa biết; `Box` là raw type. (5) Trường hợp đầu có kiểu đích và đối số constructor, trường hợp sau thiếu thông tin để suy luận kiểu hẹp hơn.

**Ghi nhớ:** **Khai báo generic** xây dựng một hợp đồng kiểu sử dụng lại được, còn **mỗi cách sử dụng generic** chỉ định hoặc suy luận các đối số kiểu cho hợp đồng đó. Compiler phân biệt rõ `Box<String>`, `Box<Integer>` và `Box<?>` tại mã nguồn, dù các đối tượng của chúng thông thường vẫn có cùng một lớp runtime sau type erasure.
