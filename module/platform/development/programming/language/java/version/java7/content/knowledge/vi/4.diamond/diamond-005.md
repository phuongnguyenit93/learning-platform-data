# Diamond trong Java: Tham số kiểu của lớp và của constructor

## 1. Vì sao cần phân biệt hai loại tham số kiểu?

Trong Java, **generic class** (lớp có tham số kiểu) và **generic constructor** (hàm tạo có tham số kiểu riêng) là hai khái niệm độc lập. Chúng có thể xuất hiện cùng nhau trong một lớp, nhưng mỗi tham số kiểu có **nơi khai báo, phạm vi và mục đích riêng**.

- **Tham số kiểu của lớp** được khai báo ngay sau tên lớp: `class Box<T>`. Nó mô tả kiểu dữ liệu gắn với một đối tượng thuộc lớp đó, chẳng hạn `Box<String>`.
- **Tham số kiểu của constructor** được khai báo ngay trước tên hàm tạo: `<U> Box(U input)`. Nó dành riêng cho lời gọi hàm tạo đó và không tự trở thành tham số kiểu của lớp.
- **Diamond operator** `<>` trong `new Box<>(...)` yêu cầu trình biên dịch **suy luận tham số kiểu của lớp**. Nếu constructor cũng có tham số kiểu riêng, trình biên dịch có thể **suy luận tham số kiểu constructor một cách độc lập** từ các đối số.
- `T`, `U` chỉ là tên theo quy ước của các *type variables* (biến kiểu). Tên này không phải giá trị runtime; chữ `T` thường viết cho kiểu của lớp, còn `U` để thể hiện kiểu độc lập của constructor.

Diamond xuất hiện từ Java 7 và vẫn là cú pháp được dùng thường xuyên trong Java hiện đại, gồm Java 17+. Bài này tập trung vào cách nó tương tác với tham số kiểu của **lớp** và của **constructor**.

## 2. Thuật ngữ: type parameter và type argument

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

- `T` trong `class Box<T>` là **type parameter**: tham số kiểu do lớp khai báo.
- `String` trong `Box<String>` là **type argument**: kiểu cụ thể được truyền vào khi sử dụng lớp.
- `new Box<String>("hello")` chỉ định tường minh type argument `String`.
- `new Box<>("hello")` dùng diamond: lập trình viên không viết lại `String` ở vế `new`, trình biên dịch phải suy luận kiểu tương ứng.
- `Box(T value)` sử dụng `T` từ lớp. Constructor này **không khai báo tham số kiểu mới**, vì trước tên `Box` không có đoạn `<U>`.

Ví dụ:

```java
Box<String> text = new Box<>("hello");
Box<Integer> number = new Box<>(42);

String first = text.get();      // được kiểm tra kiểu ở lúc biên dịch
Integer second = number.get();  // không cần ép kiểu thủ công
```

Trong hai lời gọi trên, `T` của đối tượng thứ nhất là `String`, của đối tượng thứ hai là `Integer`. Diamond chỉ thay thế cách viết type arguments ở vế phải; **không làm mất ràng buộc kiểu**.

**Phân biệt:** `Box<String>` là *parameterized type* (kiểu đã áp dụng type argument); `Box<T>` là biểu thức dùng type parameter trong phạm vi khai báo lớp.

## 3. Tham số kiểu của lớp: `class Box<T>`

Tham số kiểu `T` được khai báo tại lớp và dùng trong những thành phần thuộc phạm vi của lớp, chẳng hạn trường dữ liệu của đối tượng, kiểu tham số, giá trị trả về của phương thức instance và các constructor.

```java
final class Repository<T> {
    private T current;

    Repository(T initial) { // dùng T của lớp; constructor này không generic riêng
        current = initial;
    }

    T get() {
        return current;
    }

    void set(T replacement) {
        current = replacement;
    }
}
```

```java
Repository<String> names = new Repository<>("Lan");
names.set("Minh");
String value = names.get();

// names.set(100); // lỗi biên dịch: cần String, không thể truyền int/Integer
```

Với `Repository<String>`, trình biên dịch gắn các thao tác dùng `T` với kiểu `String`. **Không được khai báo tham số kiểu nguyên thủy** như `Repository<int>`; sử dụng wrapper `Integer` hoặc các kiểu tham chiếu khác. 

Tham số kiểu của lớp cũng có thể có *bound*:

```java
class NumericBox<T extends Number> {
    private final T number;

    NumericBox(T number) {
        this.number = number;
    }

    double valueAsDouble() {
        return number.doubleValue();
    }
}
```

```java
NumericBox<Integer> a = new NumericBox<>(42);
NumericBox<Double> b = new NumericBox<>(3.5);

// NumericBox<String> invalid = new NumericBox<>("abc");
// Sai: String không thỏa ràng buộc T extends Number.
```

Trong một lớp generic, `T` **không thể được dùng trực tiếp ở ngữ cảnh static** như `static T shared;`, bởi một thành viên static là chung cho mọi kiểu hiện thực hóa. Một phương thức static có thể **khai báo tham số kiểu riêng** (ví dụ `static <U> U identity(U value)`), nhưng `U` đó không phải `T` của lớp.

## 4. Tham số kiểu riêng của constructor: `<U> Box(...)`

Một constructor có thể tự khai báo type parameter ngay **trước tên constructor**; nếu có modifier như `public` thì modifier đứng trước danh sách type parameters.

```java
final class Parcel<T> {
    private final T value;
    private final String tag;

    public <U extends CharSequence> Parcel(T value, U tag) {
        this.value = value;
        this.tag = tag.toString();
    }

    public T value() {
        return value;
    }

    public String tag() {
        return tag;
    }
}
```

Ở đây có hai biến kiểu độc lập:

| Biến kiểu | Nơi khai báo | Mục đích và phạm vi |
| --- | --- | --- |
| `T` | `class Parcel<T>` | Kiểu dữ liệu của `value`, dùng cho trường và phương thức instance của lớp |
| `U` | `<U extends CharSequence> Parcel(...)` | Kiểu đối số `tag` trong **lần gọi constructor**, có ràng buộc `CharSequence` |
| `String` / `Integer` | Tại chỗ dùng `Parcel<String>`, `Parcel<Integer>` | Type arguments cụ thể áp dụng cho `T` |
| `String` / `StringBuilder` | Suy luận từ đối số `tag` khi gọi constructor | Type arguments khả dĩ áp dụng cho `U` |

`<U extends CharSequence>` buộc đối số `tag` thuộc kiểu triển khai `CharSequence`, vì vậy bên trong constructor có thể gọi `toString()` và các thao tác tương ứng. Nhưng `U` **không tồn tại như type parameter của lớp** ngoài phạm vi constructor: không thể tạo trường cấp lớp `private U other;` chỉ nhờ constructor đã khai báo `U`.

Hình dung ý nghĩa:

```java
Parcel<Integer> p1 = new Parcel<>(42, "id");
Parcel<String> p2 = new Parcel<>("book", new StringBuilder("v2"));
```

- Đối với `p1`, **class type parameter** `T` được suy luận/ấn định là `Integer`; **constructor type parameter** `U` được suy luận phù hợp với `String`.
- Đối với `p2`, `T` là `String`; `U` được suy luận phù hợp với `StringBuilder`.
- `U` không buộc phải giống `T`. Constructor có thể đọc dữ liệu phụ trợ kiểu khác với dữ liệu mà đối tượng chứa.
- Một constructor **không generic** chỉ đơn thuần dùng `T` từ lớp (như `Box(T value)`) vẫn làm việc được với diamond; **không phải mọi constructor của lớp generic đều là generic constructor**.

### 4.1. Lớp thường vẫn có thể có generic constructor

Generic constructor **không yêu cầu lớp chứa nó phải là generic**:

```java
final class Printer {
    private final String text;

    public <U> Printer(U item) {
        text = String.valueOf(item);
    }

    public String text() {
        return text;
    }
}
```

```java
Printer one = new Printer(99);        // U được suy luận phù hợp với Integer
Printer two = new Printer("hello");   // U được suy luận phù hợp với String
```

`Printer` không có tham số kiểu cấp lớp, nên không có chỗ để viết `new Printer<>()`. Constructor lại có `<U>` và trình biên dịch vẫn suy luận `U` từ đối số truyền vào. Điều này cho thấy **generic constructor** và **diamond** là hai cơ chế khác nhau.

### 4.2. Bounded type parameter của constructor

Có thể đặt bound riêng cho tham số kiểu constructor:

```java
final class Measurement<T> {
    private final T id;
    private final double magnitude;

    public <U extends Number> Measurement(T id, U reading) {
        this.id = id;
        this.magnitude = reading.doubleValue();
    }
}
```

```java
Measurement<String> ok = new Measurement<>("A1", 12.5);

// Measurement<String> invalid = new Measurement<>("A1", "12.5");
// Lỗi: String không thỏa U extends Number.
```

Ở đây `T` là `String` từ đối tượng `Measurement<String>`, còn `U` phải thuộc họ `Number` theo khai báo của constructor. Diamond không bỏ qua được các ràng buộc kiểu này.

## 5. Diamond suy luận kiểu của lớp như thế nào?

### 5.1. Nhìn vào kiểu đích của phép gán

```java
List<String> names = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
Parcel<Number> parcel = new Parcel<>(3.5, "decimal");
```

Với `List<String> names = new ArrayList<>();`, kiểu đích từ vế trái giúp trình biên dịch biết type argument `E` của `ArrayList<E>` phải phù hợp với `String`. Do đó có thể viết `new ArrayList<>()` thay vì lặp lại `new ArrayList<String>()`.

Với `Parcel<Number> parcel = new Parcel<>(3.5, "decimal");`:

- Kiểu đích đóng góp ràng buộc `T = Number` cho class `Parcel<T>`.
- Đối số `3.5` (được boxing thành `Double`) tương thích với tham số `T` là `Number`.
- Đối số `"decimal"` được dùng để suy luận type parameter `U` của constructor; nó thỏa `CharSequence`.
- Kiểu tĩnh của `parcel.value()` là `Number`, không phải mặc nhiên `Double` chỉ vì giá trị được truyền là 3.5.

Trình biên dịch kết hợp **ngữ cảnh kiểu đích**, **đối số constructor**, **type bounds** và các quy tắc suy luận của Java. Không có quy tắc đơn giản rằng diamond “luôn lấy kiểu từ đối số đầu tiên” hoặc “luôn lấy kiểu từ vế trái”.

### 5.2. Tại sao `var` có thể làm suy luận khác đi?

`var` (có từ Java 10 và vẫn được dùng hiện nay) để trình biên dịch suy ra kiểu của biến local từ **biểu thức khởi tạo**. Nó không tự cung cấp kiểu đích cụ thể như `List<String>`.

```java
List<String> typed = new ArrayList<>(); // E là String
var inferred = new ArrayList<>();       // E là Object trong ví dụ này

typed.add("Lan");
inferred.add("Lan");
inferred.add(42);                      // hợp lệ: List<Object>

// List<String> other = inferred;       // lỗi: ArrayList<Object> không là List<String>
```

Với `new ArrayList<>()` không có đối số nào ràng buộc `E` và không có target type xác định kiểu phần tử, trình biên dịch có thể suy luận `Object`. Ngược lại:

```java
var value = new Box<>(42); // class T suy luận thành Integer từ đối số 42
```

Mục tiêu không phải tránh `var`, mà là **đừng cho rằng diamond luôn suy luận đúng kiểu nghiệp vụ nếu ngữ cảnh không cung cấp đủ thông tin**. Khi cần một kiểu chính xác, hãy viết rõ kiểu đích hoặc các type arguments.

### 5.3. Suy luận kiểu trong lời gọi phương thức và `return`

Không chỉ phép gán, các ngữ cảnh target typing khác cũng có thể giúp suy luận kiểu:

```java
static List<String> emptyNames() {
    return new ArrayList<>();
}

static void useStrings(List<String> names) {
    System.out.println(names.size());
}

// Khi gọi trong một phương thức:
useStrings(new ArrayList<>());
```

Đây là hành vi hiện hành của Java 17+; một số tình huống suy luận dựa trên target type đã được mở rộng qua các phiên bản Java. Bài học cốt lõi là **đánh giá kiểu theo ngữ cảnh đang biên dịch**, không dựa vào việc chương trình sẽ làm gì với đối tượng sau đó.

## 6. Cách viết tường minh type arguments của constructor

Nếu constructor generic khai báo `<U>`, trình biên dịch thường suy luận được `U`, nên cách phổ biến nhất vẫn là:

```java
Parcel<Integer> parcel = new Parcel<>(7, "tag");
```

Khi cần chỉ định **tường minh type argument của constructor**, vị trí cú pháp là **ngay sau từ khóa `new`, trước tên lớp**:

```java
Parcel<Integer> explicit = new <String> Parcel<Integer>(7, "tag");
```

Cách đọc:

- `<String>` **ngay sau `new`** là type argument cho tham số `U` của **constructor**.
- `<Integer>` **sau `Parcel`** là type argument cho tham số `T` của **lớp**.
- `7` là đối số thực tế cho tham số giá trị kiểu `T`; `"tag"` là đối số cho `U`.
- Hai cặp dấu góc có **vị trí và nhiệm vụ khác nhau**.

**Quy tắc rất quan trọng:** Trong một biểu thức tạo đối tượng, nếu bạn viết **tường minh type arguments của constructor** sau `new` thì **không được dùng diamond cho type arguments của lớp**.

```java
Parcel<Integer> valid = new <String> Parcel<Integer>(7, "tag");

// Parcel<Integer> invalid = new <String> Parcel<>(7, "tag");
// Lỗi biên dịch: không được kết hợp explicit constructor type arguments với <>.
```

Nguyên nhân nằm ở quy tắc suy luận kiểu của Java: suy luận type arguments của lớp có thể ảnh hưởng ràng buộc với các type arguments constructor; ngữ pháp/ngữ nghĩa Java không cho tổ hợp trên. Với mã thông thường, **để trình biên dịch suy luận cả hai** bằng `new Parcel<>(7, "tag")` là lựa chọn ngắn gọn, rõ và giữ được an toàn kiểu.

Đừng nhầm `new <String> Parcel<Integer>(...)` với `new Parcel<String>(...)`: cùng chữ `String` nhưng nằm ở **vị trí khác**, nên tham gia **hệ tham số kiểu khác**.

## 7. Chương trình Java 17+ đầy đủ và kết quả

Đây là một chương trình minh họa cùng lúc: class type parameter `T`, constructor type parameter `U`, diamond, constructor generic của lớp thường và type argument constructor tường minh.

Lưu thành tệp **`DiamondConstructorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondConstructorDemo {

    static final class Parcel<T> {
        private final T value;
        private final String tag;

        public <U extends CharSequence> Parcel(T value, U tag) {
            this.value = value;
            this.tag = tag.toString();
        }

        public T value() {
            return value;
        }

        public String tag() {
            return tag;
        }
    }

    static final class Printer {
        private final String text;

        public <U> Printer(U item) {
            this.text = String.valueOf(item);
        }

        public String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        Parcel<Integer> a = new Parcel<>(42, "id");
        Parcel<String> b = new Parcel<>("book", new StringBuilder("v2"));
        Parcel<Number> c = new Parcel<>(3.5, "decimal");

        Parcel<Integer> explicit =
                new <String> Parcel<Integer>(7, "tag");

        Printer p = new Printer(99);
        List<String> names = new ArrayList<>();
        names.add("Lan");

        System.out.println(a.value() + ":" + a.tag());
        System.out.println(b.value() + ":" + b.tag());
        System.out.println(c.value() + ":" + c.tag());
        System.out.println(explicit.value() + ":" + explicit.tag());
        System.out.println("printer=" + p.text());
        System.out.println("name=" + names.get(0));
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac DiamondConstructorDemo.java
java DiamondConstructorDemo
```

**Stdout chính xác:**

```text
42:id
book:v2
3.5:decimal
7:tag
printer=99
name=Lan
```

Giải thích kết quả:

1. `a`: kiểu lớp `T = Integer`, constructor nhận `tag` kiểu `String` phù hợp `U extends CharSequence`.
2. `b`: kiểu lớp `T = String`, đối số `tag` dùng `StringBuilder`, vẫn hợp lệ vì `StringBuilder implements CharSequence`.
3. `c`: kiểu đích `Parcel<Number>` giúp chọn `T = Number`; `Double` của 3.5 tương thích với `Number`.
4. `explicit`: viết tường minh cả hai type arguments, gồm `U = String` ngay sau `new` và `T = Integer` sau tên `Parcel`.
5. `Printer`: lớp không generic nhưng constructor generic, `U` được suy luận từ `99`.
6. `ArrayList<>`: type argument `String` đến từ biến đích `List<String>`.

Chương trình trên đã dùng đúng dạng API và cú pháp vẫn được hỗ trợ trong Java hiện đại; không cần dependency hoặc thư viện ngoài JDK.

## 8. Phạm vi type parameter và tính an toàn kiểu

### 8.1. Class type parameter sống lâu hơn một lời gọi constructor

Type parameter `T` của lớp có thể xuất hiện ở chữ ký trường dữ liệu, constructor và phương thức instance:

```java
final class Holder<T> {
    private final T item;

    Holder(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}
```

`Holder<String>` bảo đảm `get()` có kiểu tĩnh `String`. Ngược lại, type parameter `U` của một constructor chỉ thuộc **phạm vi khai báo constructor đó**; nó không làm cho một lớp thường thành `Holder<U>` hoặc biến trường của lớp thành kiểu `U`.

Không viết `<T>` lại trước tên constructor trừ khi bạn **thực sự muốn khai báo một type parameter mới**: tên trùng với type parameter của lớp có thể che khuất tên cũ và khiến API khó hiểu. Dùng tên `U`, `V` cho tham số kiểu bổ sung sẽ giúp người đọc phân biệt.

### 8.2. Generic type có tính bất biến

Hai kiểu `Holder<String>` và `Holder<Object>` không có quan hệ kế thừa trực tiếp chỉ vì `String extends Object`:

```java
Holder<String> strings = new Holder<>("hello");

// Holder<Object> objects = strings; // lỗi biên dịch: generic invariance
```

Diamond không thay đổi tính bất biến đó. Khi thiết kế API nhận nhiều kiểu, sử dụng wildcard có bound (`? extends T` hoặc `? super T`) đúng vai trò; không ép kiểu bừa để né lỗi biên dịch.

### 8.3. Generics bị xóa kiểu tại runtime

Java generics chủ yếu kiểm tra an toàn kiểu ở **lúc biên dịch**. Thông tin type argument không tạo ra lớp runtime riêng biệt cho từng `T`:

```java
System.out.println(
        new ArrayList<String>().getClass()
        == new ArrayList<Integer>().getClass()); // true
```

Bởi vậy:

- `<>` **không tạo một loại đối tượng runtime mới**. Nó là cú pháp hỗ trợ suy luận kiểu tại compile time.
- Không thể kiểm tra đối tượng bằng `instanceof ArrayList<String>` vì kiểu có type argument cụ thể đó không phải kiểu dùng được cho phép kiểm tra runtime như vậy. Khi cần kiểm tra dạng runtime, có thể dùng kiểu reifiable như `ArrayList<?>` rồi kiểm tra nội dung theo hợp đồng API.
- Constructor generic cũng không lưu “kiểu `U` đã suy luận” như một giá trị runtime để truy vấn trực tiếp.

## 9. Những lỗi thường gặp khi dùng diamond và constructor

### Lỗi 1: Nhầm `new Box()` với `new Box<>()`

```java
List<String> safe = new ArrayList<>();

// List<String> raw = new ArrayList(); // raw type, có thể cảnh báo unchecked
```

`new ArrayList()` sử dụng **raw type**; thông tin type arguments bị bỏ qua ở lời gọi, có thể sinh cảnh báo từ `javac -Xlint:rawtypes,unchecked` và làm yếu kiểm tra kiểu. `new ArrayList<>()` yêu cầu suy luận kiểu và giữ cách dùng generic phù hợp với ngữ cảnh.

### Lỗi 2: Tưởng constructor generic phải được định nghĩa trên generic class

```java
final class Report {
    public <U> Report(U source) {
        System.out.println(source);
    }
}

Report report = new Report(42);
```

Hợp lệ. `Report` không phải generic class; `U` chỉ là constructor type parameter. Vì lớp không có type parameters, **không viết** `new Report<>()`.

### Lỗi 3: Viết diamond ở nơi khai báo kiểu hoặc cố dùng khi cần explicit constructor type

```java
// class Box<> { }                         // sai: khai báo generic cần tên tham số kiểu
// Parcel<Integer> p = new <String> Parcel<>(7, "tag"); // sai: không thể kết hợp
```

Trong khai báo lớp dùng `class Box<T>`. Trong tạo đối tượng dùng `new Box<>(...)` khi muốn compiler suy luận class type arguments.

### Lỗi 4: Hiểu nhầm tên type parameter là tên kiểu cụ thể

`<T>` và `<U>` trong khai báo là **biến kiểu**, không tự đại diện cho một lớp Java có tên `T` hay `U`. Còn `<String>` và `<Integer>` ở biểu thức sử dụng là **type arguments**.

Việc đổi tên type parameter từ `T` thành `E` trong toàn bộ phạm vi khai báo không làm đổi ý nghĩa kiểu, nếu không gây xung đột.

### Lỗi 5: Nghĩ kiểu constructor `U` phải trùng kiểu lớp `T`

Trong `Parcel<T>`, constructor nhận `(T value, U tag)` và ràng buộc `U extends CharSequence`; `Parcel<Integer>` hoàn toàn có thể nhận chuỗi `"tag"`. Hai tham số kiểu có vai trò độc lập.

### Lỗi 6: Thiếu ngữ cảnh suy luận khi dùng diamond

`var list = new ArrayList<>();` không tự hiểu ý định chứa `String`. Nếu mong muốn một danh sách chuỗi, viết `List<String> list = new ArrayList<>();` hoặc cung cấp kiểu cụ thể như `new ArrayList<String>()`.

### Lỗi 7: Cho rằng compiler cho phép tất cả sự kết hợp cú pháp

`new <String> Parcel<Integer>(7, "tag")` hợp lệ cho generic constructor; `new <String> Parcel<>(7, "tag")` không hợp lệ. Đây là lỗi compile-time do quy tắc Java, không phải hạn chế riêng của IDE.

### Lỗi 8: Tưởng diamond suy luận kiểu dựa trên code chạy sau đó

Suy luận diễn ra tại **biểu thức khởi tạo**, sử dụng kiểu đích, đối số và các ràng buộc liên quan. Những lệnh xảy ra sau `new` không thay đổi kiểu đã suy luận cho đối tượng vừa tạo.

## 10. Bài tập và đáp án

**Bài 1.** Trong `class Pair<K,V>`, đoạn `Pair<String,Integer> p = new Pair<>("age", 20);` có hai loại type parameter nào?  
**Đáp án:** `K` và `V` **đều là type parameters của lớp `Pair`**; `String` và `Integer` là type arguments của lớp. Nếu constructor không tự khai báo `<U>`, nó không có type parameter riêng.

**Bài 2.** `class C<T> { <U> C(U value) {} }` và `C<Integer> c = new C<>("hello");`: compiler suy luận gì?  
**Đáp án:** `T` của lớp là `Integer` nhờ kiểu đích; `U` của constructor được suy luận phù hợp `String` từ `"hello"`. `T` không nhất thiết liên quan đến `U`.

**Bài 3.** Với `Parcel<T>` ở phần ví dụ, `new <String> Parcel<Integer>(7, "tag")` và `new Parcel<>(7, "tag")` có điều gì khác về mặt cú pháp?  
**Đáp án:** Biểu thức đầu chỉ định tường minh `U = String` và `T = Integer`. Biểu thức sau để compiler suy luận type arguments từ ngữ cảnh và đối số; cả hai đều có thể tạo đối tượng `Parcel<Integer>` trong ngữ cảnh phù hợp.

**Bài 4.** `new <String> Parcel<>(7, "tag")` có hợp lệ không?  
**Đáp án:** Không. Nếu đã truyền explicit constructor type arguments sau `new`, không được dùng `<>` thay class type arguments trong cùng biểu thức.

**Bài 5.** Tại sao `var items = new ArrayList<>();` không mang kiểu `ArrayList<String>` chỉ vì sau đó gọi `items.add("a")`?  
**Đáp án:** Do suy luận diễn ra tại `new ArrayList<>()` mà không có ngữ cảnh kiểu đích `String` hoặc đối số constructor ràng buộc `E`; kết quả ở đây là `ArrayList<Object>`. Việc thêm phần tử sau không làm thay đổi kiểu của biến.

**Bài 6.** Một lớp không khai báo `<T>` có thể khai báo `public <U> MyClass(U value)` không?  
**Đáp án:** Có. Đây là generic constructor trong lớp không generic, `U` có phạm vi riêng của constructor.

## 11. Tổng hợp kiến thức và tài liệu chính thức

| Vấn đề | Quy tắc chính |
| --- | --- |
| `class Container<T>` | `T` là type parameter của lớp; dùng trong chữ ký các thành phần instance và constructor |
| `<U> Container(U input)` | `U` là type parameter riêng của constructor, chỉ tồn tại trong phạm vi constructor |
| `Container<String> x` | `String` là type argument cụ thể cho `T` của lớp |
| `new Container<>(...)` | `<>` yêu cầu suy luận type arguments của lớp từ ngữ cảnh; type arguments của constructor (nếu có) được suy luận riêng |
| `new <String> Container<Integer>(...)` | `String` truyền cho generic constructor; `Integer` truyền cho generic class |
| `new <String> Container<>(...)` | Không hợp lệ: explicit constructor type arguments không được kết hợp với diamond |
| `new Container(...)` | Raw type khi `Container` là generic class; cần tránh vì làm mất kiểm tra kiểu |
| Runtime | Type erasure: diamond/type arguments không tạo lớp runtime riêng cho từng kiểu |

**Ghi nhớ:** **Class type parameters** xác định kiểu của đối tượng, **constructor type parameters** mô tả phần kiểu chỉ thuộc lời gọi khởi tạo. **Diamond** giúp trình biên dịch suy luận type arguments của **lớp**; nếu constructor cũng generic, type arguments của nó được giải quyết độc lập theo cùng hệ thống kiểm tra kiểu. Dùng `<>` khi có đủ ngữ cảnh, và giữ khai báo generic rõ ràng để tận dụng an toàn kiểu của Java.

Nguồn đặc tả hiện hành:

- [Java Language Specification, `8.8.4 — Generic Constructors](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.8.4).
- [Java Language Specification, `15.9 — Class Instance Creation Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.9).
- [Java Language Specification, `18 — Type Inference](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-18.html).