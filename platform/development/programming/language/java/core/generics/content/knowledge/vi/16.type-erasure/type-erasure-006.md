# Vì sao `Box<String>` và `Box<Integer>` dùng cùng lớp lúc chạy?

## Mục tiêu học tập

Khi học Java generics, ta thường thấy hai biến có hai kiểu khác nhau:

```java
Box<String> words = new Box<>("Java");
Box<Integer> numbers = new Box<>(42);
```

Ở **mã nguồn**, `Box<String>` và `Box<Integer>` là hai kiểu tham số hóa khác nhau, được trình biên dịch kiểm tra theo những ràng buộc khác nhau. Tuy nhiên, nếu cả hai đối tượng đều được tạo bằng chính lớp `Box`, câu lệnh `words.getClass() == numbers.getClass()` lại cho kết quả `true`.

Bài này giúp bạn:

- Giải thích nguyên nhân bằng **type erasure** và cơ chế nạp lớp của JVM.
- Phân biệt **kiểu tham số hóa tại thời điểm biên dịch**, **runtime class của đối tượng Box**, **runtime class của giá trị nằm trong Box** và **metadata generic**.
- Quan sát một chương trình Java 17 chạy thực tế, kiểm tra `javap` và `java.lang.reflect`.
- Hiểu tại sao cùng một lớp runtime vẫn có thể bảo đảm `Box<String>` không được nhận `Integer` khi biên dịch.
- Nhận diện các trường hợp ngoại lệ dễ gây nhầm lẫn: lớp con của `Box<String>`, nhiều class loader, đối tượng `null`, raw type và type token truyền tường minh.

## 1. Đặt vấn đề: một lớp khai báo, nhiều cách dùng có tham số kiểu

Ta khai báo lớp generic:

```java
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
```

`T` là **tham số kiểu** được khai báo trong định nghĩa lớp. `Box<String>` và `Box<Integer>` là hai cách **tham số hóa kiểu** `Box<T>` bằng các đối số kiểu khác nhau; chúng không phải hai lớp Java độc lập được viết hoặc sinh ra với mã nguồn `class BoxString` và `class BoxInteger`.

Ví dụ các phép gán được compiler xem xét như sau:

```java
Box<String> words = new Box<>("Java");
words.set("Generics");       // Hợp lệ: String phù hợp với T = String.
// words.set(123);          // Lỗi biên dịch: int/Integer không phải String.

Box<Integer> numbers = new Box<>(42);
numbers.set(100);           // Hợp lệ: Integer.
// numbers.set("wrong");    // Lỗi biên dịch.
```

Dù loại đối số được kiểm tra khi biên dịch, Java không tạo một runtime class riêng ứng với mỗi `T` cụ thể. Đây là đặc tính quan trọng của cách Java triển khai generics, khác với việc chuyên biệt hóa lớp cho từng kiểu tham số ở một số ngôn ngữ hoặc mô hình khác.

Cần phân biệt:

| Thành phần | Ví dụ | Bản chất |
| --- | --- | --- |
| Lớp generic được khai báo | `Box<T>` | Một định nghĩa lớp |
| Kiểu tham số hóa trong mã nguồn | `Box<String>` | Trình biên dịch biết phần tử của `Box` là `String` |
| Một kiểu tham số hóa khác | `Box<Integer>` | Trình biên dịch biết phần tử của `Box` là `Integer` |
| Runtime class của hai đối tượng tạo trực tiếp bằng `new Box<>(...)` | `Box.class` | Cùng một đối tượng `Class` trong cùng ngữ cảnh class loader |
| Giá trị nằm bên trong | `"Java"` và `42` (được boxing thành `Integer`) | Hai đối tượng có kiểu thực lần lượt là `String` và `Integer` |

**Cùng runtime class không đồng nghĩa hai biến tham chiếu cùng một đối tượng.** `words` và `numbers` vẫn trỏ tới hai `Box` được tạo riêng, mỗi hộp có trạng thái của nó.

## 2. Lý do: Java generic sử dụng type erasure

Với `class Box<T>` không bound, những vị trí dùng `T` thường có JVM descriptor dạng `Object`, thay vì sinh `Box$String` hay `Box$Integer`:

```java
static class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

| Thành phần của `Box<T>` | Erased JVM descriptor |
| --- | --- |
| `T value` | `Ljava/lang/Object;` |
| `Box(T)` | `(Ljava/lang/Object;)V` |
| `T get()` | `()Ljava/lang/Object;` |

Đây là **cơ chế giải thích cùng runtime class**. Khi sử dụng `Box<String>` và `Box<Integer>`, compiler vẫn kiểm tra kiểu các lời gọi, và có thể chèn cast ở caller. Không nên hiểu `Box<String>` là `Box<Object>` ở **source-level type system**. Phần tiếp theo kiểm chứng class identity trực tiếp bằng `getClass()`/`Box.class` và `javap`.

## 3. Chương trình Java 17: chứng minh cùng runtime class

Tạo tệp `SameRuntimeClassDemo.java` (toàn bộ nội dung sau biên dịch độc lập với Java 17+):

```java
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;

public final class SameRuntimeClassDemo {
    static class Box<T> {
        private T value;

        Box(T value) { this.value = value; }
        T get() { return value; }
        void set(T value) { this.value = value; }
    }

    static final class StringBox extends Box<String> {
        StringBox(String value) { super(value); }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        Box<Integer> numbers = new Box<>(42);

        System.out.println("same class: " + (words.getClass() == numbers.getClass()));
        System.out.println("class equals Box.class: " + (words.getClass() == Box.class));
        System.out.println("runtime name: " + words.getClass().getName());
        System.out.println("actual values: " + words.get().getClass().getSimpleName()
                + ", " + numbers.get().getClass().getSimpleName());
        System.out.println("values: " + words.get().toUpperCase()
                + " / " + (numbers.get() + 1));

        Class<?> clazz = words.getClass();
        TypeVariable<?> parameter = clazz.getTypeParameters()[0];
        System.out.println("declared parameter: " + parameter.getName());
        System.out.println("declared bound: "
                + Arrays.toString(parameter.getBounds()));

        Type superclass = StringBox.class.getGenericSuperclass();
        System.out.println("subclass generic parent: " + superclass.getTypeName());
        System.out.println("subclass shares Box.class: "
                + (new StringBox("X").getClass() == words.getClass()));
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac SameRuntimeClassDemo.java
java SameRuntimeClassDemo
```

**Stdout đã kiểm tra bằng `javac` và `java`:**

```text
same class: true
class equals Box.class: true
runtime name: SameRuntimeClassDemo$Box
actual values: String, Integer
values: JAVA / 43
declared parameter: T
declared bound: [class java.lang.Object]
subclass generic parent: SameRuntimeClassDemo$Box<java.lang.String>
subclass shares Box.class: false
```

Đọc và lý giải:

1. **`same class: true`**: hai đối tượng đều là instance trực tiếp của runtime class `SameRuntimeClassDemo$Box`. Toán tử `==` so sánh hai tham chiếu `Class`; kết quả `true` chứng minh hai lời gọi lấy cùng một đối tượng mô tả runtime class.
2. **`class equals Box.class: true`**: `Box.class` là class literal của lớp khai báo `Box`. Không có `Box<String>.class` dành riêng cho tham số kiểu `String`.
3. **`runtime name: SameRuntimeClassDemo$Box`**: lớp lồng tĩnh có tên binary chứa ký tự `$`. Tên không kèm `<String>` hay `<Integer>`.
4. **`actual values: String, Integer`**: cùng kiểu hộp không làm thay đổi loại đối tượng được giữ trong mỗi instance. Một hộp chứa `String`, hộp kia chứa `Integer`.
5. **`values: JAVA / 43`**: compiler vẫn hỗ trợ sử dụng `String.toUpperCase()` và phép tính trên `Integer` theo đúng kiểu do generic khai báo.
6. **`declared parameter: T`**: reflection nhận được **tên tham số kiểu được khai báo ở class**, không trả lại lời gọi `Box<String>` của biến `words`.
7. **`declared bound: [class java.lang.Object]`**: `T` không khai báo ràng buộc, nên bound tương ứng là `Object`.
8. **`subclass generic parent: ...Box<java.lang.String>`**: lớp con `StringBox` khai báo cố định quan hệ kế thừa `extends Box<String>`, nên metadata của chính lớp con có thể mô tả `String`. Đây là thông tin **trên khai báo lớp con**, không phải bằng chứng rằng mỗi lần tạo `Box<String>` sinh runtime class mới.
9. **`subclass shares Box.class: false`**: `StringBox` là một lớp con **thực sự khác lớp** `Box`; `StringBox.class != Box.class` là kết quả đúng và không mâu thuẫn với quy tắc xóa kiểu.

Ví dụ dùng `Box` không `final` chỉ để cho phép khai báo lớp con `StringBox`; chính điều đó giúp chỉ ra sự khác biệt giữa **tham số hóa** và **kế thừa**.

## 4. Kiểm tra tệp class với `javap`

Trong ví dụ trên, `Box` là lớp lồng tĩnh, nên `javac` tạo tệp tương ứng có tên binary `SameRuntimeClassDemo$Box`. Sau khi biên dịch, chạy:

```bash
javap -s -p 'SameRuntimeClassDemo$Box'
```

Đặt tên lớp trong dấu nháy đơn khi dùng Bash hoặc PowerShell để tránh trình bao xử lý ký tự `$`. Đoạn kết quả chính **đã kiểm chứng bằng `javap`**:

```text
class SameRuntimeClassDemo$Box<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  SameRuntimeClassDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;

  void set(T);
    descriptor: (Ljava/lang/Object;)V
}
```

Bên trái, `javap` có thể hiển thị chữ ký generic như `T get()`. Bên phải, descriptor mà JVM sử dụng cho phương thức tương ứng là `()Ljava/lang/Object;`. Class file có thể lưu **generic Signature metadata** cùng với descriptor; metadata này giúp công cụ/reflection hiển thị khai báo `T` nhưng **không tạo một biến thể runtime riêng cho từng đối số kiểu**.

Cách đọc phần quan trọng:

- `Ljava/lang/Object;` đại diện cho kiểu tham chiếu `java.lang.Object`.
- `(Ljava/lang/Object;)V` có một tham số `Object`, trả về `void`.
- `()Ljava/lang/Object;` không có tham số, trả về `Object`.

Bạn có thể chạy thêm:

```bash
javap -c -p SameRuntimeClassDemo
```

Khi phương thức `main` gọi `words.get()` ở ngữ cảnh cần `String`, bytecode có thể bao gồm:

```text
invokevirtual ... Box.get:()Ljava/lang/Object;
checkcast     ... class java/lang/String
```

Các chỉ số constant pool, offset và cách hiển thị tên lớp tùy bản `javac`/`javap`; phần đáng chú ý là **`get` trả `Object` ở descriptor**, sau đó compiler chèn **`checkcast String`** khi kiểu cụ thể cần dùng là `String`.

Tại sao chỉ có một `Box.class` lại chạy được cho nhiều kiểu? Bởi JVM không phải giải quyết mỗi tham số kiểu thành một class mới; nó dùng bytecode erased của `Box`, còn compiler chịu trách nhiệm áp dụng ràng buộc generic tại các điểm gọi.

## 5. Cùng lớp runtime nhưng vẫn có kiểm tra kiểu an toàn

Nếu JVM chỉ thấy phương thức `set(Object)`, vì sao `words.set(123)` bị từ chối ở source?

Vì compiler biết biến `words` được khai báo là `Box<String>`. Do đó, theo cách nhìn của trình biên dịch, các phép thao tác thông thường trên biến ấy tương ứng với:

- `set(String)` theo kiểu nguồn đã thay `T = String`;
- `String get()` theo kiểu nguồn;
- đối số `Integer` truyền vào `set` sẽ vi phạm ràng buộc kiểu ở **thời điểm biên dịch**.

Sau khi bytecode được tạo, JVM có thể thực thi các lời gọi erased. Ví dụ, khi lấy kết quả của `get()` gán vào biến `String`, compiler chèn một cast tương ứng. Nếu chương trình không dùng các đường đi dữ liệu không an toàn, bảo đảm compile time giúp cast đó thành công.

**Điều không đúng:** “vì JVM thấy `Object` nên compiler cũng cho phép `words.set(new Object())`”. Java có hai mức khác nhau: kiểm tra kiểu generic của mã nguồn và kiểu erased trong bytecode.

### Type erasure không làm `Box<String>` trở thành `Box<Object>`

Phép gán sau **không hợp lệ**:

```java
Box<String> strings = new Box<>("one");
// Box<Object> objects = strings; // Lỗi biên dịch.
```

Java generics **bất biến** (*invariant*): `String` là con của `Object` không kéo theo `Box<String>` là subtype của `Box<Object>`. Nếu phép gán đó hợp lệ, người dùng có thể đưa một `Object` không phải chuỗi vào hộp vốn được hứa chỉ chứa `String`.

Khi cần tham chiếu đọc dữ liệu từ nhiều loại `Box` mà không phụ thuộc `T` cụ thể, `Box<?>` có thể phù hợp:

```java
Box<?> unknown = new Box<>("hello");
Object value = unknown.get();
// unknown.set("another"); // Không biên dịch: T cụ thể không được biết.
// unknown.set(null);      // Hợp lệ về kiểu; cách xử lý null tùy API.
```

`Box<?>` cho phép đọc giá trị như `Object`, nhưng compiler không thể cho phép ghi một đối tượng không phải `null` khi không biết tham số kiểu thực. Quy tắc này vẫn tồn tại dù các biến thể `Box` dùng chung runtime class.

## 6. Reflection đọc được gì — và không đọc được gì?

Hai phương thức reflection dễ bị nhầm lẫn:

```java
Class<?> clazz = words.getClass();
System.out.println(clazz.getTypeParameters()[0].getName()); // T
```

`getTypeParameters()` mô tả **tham số kiểu khai báo trong phần định nghĩa lớp**. Ký tự `T` xuất hiện trong khai báo `class Box<T>` và có thể được lưu trong metadata; reflection không kết luận riêng đối tượng `words` đã nhận `String` tại điểm khai báo biến.

Ngược lại:

```java
System.out.println(StringBox.class.getGenericSuperclass().getTypeName());
```

có thể trả về `SameRuntimeClassDemo$Box<java.lang.String>` vì chính lớp `StringBox` được biên dịch từ câu lệnh `extends Box<String>`. Metadata của **khai báo kế thừa** mang thông tin đó.

Ba câu hỏi khác nhau:

| Câu hỏi | API thường dùng | Điều nhận được |
| --- | --- | --- |
| Đối tượng này là instance của lớp runtime nào? | `obj.getClass()` | `Class<?> ` của runtime class thực |
| Lớp generic khai báo tên tham số kiểu nào? | `Box.class.getTypeParameters()` | `T`, các bound |
| Lớp con khai báo kiểu cha generic nào? | `StringBox.class.getGenericSuperclass()` | Có thể thấy `Box<String>` từ metadata lớp con |

**Không thể dựa riêng vào `new Box<String>("X").getClass()` để khôi phục `String` như một tham số runtime đã được gắn vào `Class` của Box.** Với `Box<Integer>`, phương thức ấy trả về cùng `Box.class` trong cùng ngữ cảnh nạp lớp.

Cũng không nên cố suy luận kiểu `T` bằng `box.get().getClass()`. Cách đó chỉ cho biết **kiểu đối tượng hiện đang nằm trong hộp**, có thể vắng mặt nếu giá trị là `null`, và không phải bằng chứng tổng quát về khai báo `Box<T>`.

## 7. Khi thật sự cần thông tin kiểu ở runtime: truyền `Class<T>`

Type erasure không cấm ứng dụng lưu metadata một cách **tường minh**. Nếu API cần kiểm tra đối tượng đến từ bên ngoài có đúng kiểu mong muốn, hãy nhận một **type token** `Class<T>` rồi lưu nó trong từng instance.

Ví dụ `TypeTokenDemo.java` sau biên dịch và chạy độc lập với Java 17+:

```java
import java.util.Objects;

public final class TypeTokenDemo {
    static final class Box<T> {
        private final Class<T> type;
        private T value;

        Box(Class<T> type, T value) {
            this.type = Objects.requireNonNull(type);
            this.value = type.cast(value);
        }

        Class<T> type() { return type; }
        T get() { return value; }

        void setFromObject(Object candidate) {
            value = type.cast(candidate);
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>(String.class, "Hi");
        Box<Integer> number = new Box<>(Integer.class, 7);

        System.out.println("same Box class: "
                + (text.getClass() == number.getClass()));
        System.out.println("saved tokens: " + text.type().getSimpleName()
                + ", " + number.type().getSimpleName());

        try {
            text.setFromObject(8);
        } catch (ClassCastException ex) {
            System.out.println("rejected: " + ex.getClass().getSimpleName());
        }
    }
}
```

Lệnh:

```bash
javac TypeTokenDemo.java
java TypeTokenDemo
```

Stdout đã kiểm chứng:

```text
same Box class: true
saved tokens: String, Integer
rejected: ClassCastException
```

Điều thay đổi so với ví dụ đầu:

- Các instance vẫn thuộc **cùng class `TypeTokenDemo$Box`**.
- Mỗi đối tượng chứa **một field dữ liệu `type`**, được truyền từ `String.class` hoặc `Integer.class`. Sự khác nhau về token thuộc **trạng thái từng đối tượng**, không phải do JVM tự khôi phục generic của `Box<T>`.
- `Class.cast` kiểm tra đối tượng nhận vào theo token; khi `Box<String>` nhận một `Integer` qua `setFromObject`, nó phát sinh `ClassCastException`.
- `Class<T>` dùng thuận tiện cho các kiểu runtime có `Class` token như `String`, `Integer`. Nó không thể giữ trọn tham số lồng nhau của một kiểu như `List<String>` chỉ bằng `List.class`; nếu cần kiểu generic phức tạp, phải có metadata kiểu khác (chẳng hạn `Type`/`ParameterizedType` phù hợp).

Có thể chọn thiết kế không cho phép thay đổi giá trị qua `Object` khi ứng dụng chỉ cần API generic có kiểm tra kiểu ở compile time. Type token hữu ích khi nhận dữ liệu động, reflect, deserialize hoặc tương tác với API không mang đủ tham số generic.

## 8. Các hệ quả thường gặp

Các cách sử dụng `Box<String>` và `Box<Integer>` có cùng runtime class dẫn đến một số giới hạn, nhưng chúng không làm mất compile-time type checking:

| Tình huống | Kết quả trên Java 17 | Vì sao |
| --- | --- | --- |
| `obj instanceof Box<?>` | Hợp lệ | Chỉ kiểm tra runtime class `Box` |
| `obj instanceof Box<String>` với `obj: Object` | Bị từ chối | Runtime không biết đối số generic `String` |
| `new Box<String>[2]` | Bị từ chối | Component type không reifiable |
| Hai overload `f(Box<String>)` và `f(Box<Integer>)` | Bị từ chối | Trùng erasure |
| Gán `Box<Integer>` vào `Box<String>` | Bị từ chối | Generic type invariance |
| Raw alias/unchecked cast | Có cảnh báo hoặc nguy cơ runtime | Bỏ qua bảo đảm kiểu ở source |

Trường hợp `Box<String>` và `Box<Integer>` vẫn có thể mang **giá trị object thực khác class**; `getClass()` của chính giá trị trong hộp không làm cho class của hộp trở nên specialized. Nếu cần validation ở runtime, truyền `Class<T>` token như chương trình kế tiếp, nhưng nhớ rằng token không tự kiểm tra type arguments lồng sâu như `List<String>`.

## 9. Ba nhầm lẫn quan trọng cần gỡ

**Nhầm lẫn A — “Cùng `Box.class` nghĩa là cùng đối tượng”.**

Sai. Hai lời gọi `new Box<>(...)` tạo hai đối tượng `Box` khác nhau dù cùng class. So sánh:

```java
Box<String> x = new Box<>("A");
Box<String> y = new Box<>("A");
System.out.println(x == y);                    // false
System.out.println(x.getClass() == y.getClass()); // true
```

`==` trên `x`, `y` kiểm tra **danh tính instance**. `==` trên kết quả `getClass()` kiểm tra **danh tính Class**.

**Nhầm lẫn B — “Xóa kiểu `T` thành `Object` nghĩa là mất lớp thật của `String`”.**

Sai. Đối tượng `String` vẫn thuộc `String.class`. Compiler/JVM có thể dùng `Object` trong chữ ký erased của hộp vì mọi đối tượng `String` cũng là `Object`. Thông tin **đối số generic của hộp** mất khỏi runtime descriptor, không phải lớp thực của từng đối tượng tham chiếu.

**Nhầm lẫn C — “Reflection in được `Box<String>` thì chắc JVM có lớp `Box<String>` riêng”.**

Sai. Reflection đọc được thông tin generic của **khai báo** (ví dụ một lớp con thực sự viết `extends Box<String>`) vì class file có thể lưu metadata `Signature`. Nó không khẳng định có lớp runtime chuyên biệt cho mỗi cách dùng `new Box<String>(...)`.

**Một giới hạn nâng cao về class loader:** câu “hai `Box` dùng cùng `Class`” ngầm giả định chúng được tạo từ cùng định nghĩa lớp do cùng ngữ cảnh nạp lớp xác định. Trong JVM, hai class loader khác nhau có thể định nghĩa hai lớp có cùng tên binary nhưng là hai runtime class khác nhau. Điều đó là quy tắc về **class identity và class loading**, độc lập với việc `Box<String>` hay `Box<Integer>` chọn đối số generic nào.

## 10. Câu hỏi tự luyện

**Câu 1.** Với hai biến cùng tạo trực tiếp bằng `new Box<>(...)`:

```java
Box<String> a = new Box<>("Hello");
Box<Integer> b = new Box<>(10);
```

Dự đoán `a == b` và `a.getClass() == b.getClass()`.

**Giải thích:** trong ví dụ hai biến có kiểu nguồn không tương thích trực tiếp, việc viết `a == b` có thể bị compiler báo là hai kiểu incomparable. Để kiểm tra danh tính instance một cách hợp lệ trong bài này, ép hai phía về `Object` hoặc lưu chúng trong `Object` trước. Khi đó hai instance khác nhau nên kết quả là `false`; còn hai `getClass()` là cùng `Box.class` nên `true`.

**Câu 2.** Vì sao `Box<T>.get()` có thể có descriptor `()Ljava/lang/Object;`, trong khi `String text = box.get();` hợp lệ khi `box` là `Box<String>`?

**Đáp án:** type erasure khiến method descriptor trả `Object`; compiler kiểm tra kiểu nguồn và chèn cast sang `String` tại điểm sử dụng khi cần.

**Câu 3.** `Box<String>` và `Box<Integer>` giống nhau ở điều gì và khác nhau ở điều gì?

**Đáp án:** nếu cùng được tạo trực tiếp bằng lớp `Box`, chúng giống nhau về runtime class; chúng khác về kiểu tham số hóa được compiler kiểm tra và có thể khác về giá trị, trạng thái và các token được truyền vào từng instance.

**Câu 4.** Nếu khai báo `class StringBox extends Box<String>` rồi gọi `new StringBox("A").getClass()`, kết quả có bằng `new Box<>("A").getClass()` không?

**Đáp án:** không. `StringBox` là lớp con riêng biệt, có runtime class riêng, không phải một biến thể tự sinh từ việc truyền `String` làm đối số generic.

**Câu 5.** Vì sao `Box.class.getTypeParameters()` không trả về `String` cho một biến được khai báo là `Box<String>`?

**Đáp án:** API đó đọc danh sách tham số kiểu **của khai báo class `Box<T>`**, không đọc thông tin đối số kiểu được chọn trong khai báo biến cụ thể.

**Câu 6.** Thiết kế `Box<T>` sao cho chương trình từ chối đưa một đối tượng không đúng kiểu vào hộp khi dữ liệu đến từ nguồn `Object`.

**Gợi ý:** truyền một `Class<T>` tường minh vào constructor, lưu trong field, dùng `type.cast(candidate)` tại biên nhận dữ liệu. Phân biệt field token của **instance** và đối tượng `Class` của chính `Box`.

## Tự tổng kết bằng một mô hình chính xác

- **Mã nguồn:** `Box<String>` và `Box<Integer>` là hai kiểu tham số hóa khác nhau; compiler bảo vệ những thao tác bình thường với `T` theo đối số kiểu đã cung cấp.
- **Bytecode:** các vị trí dùng tham số `T` không giới hạn trong `Box<T>` có erased type là `Object`; JVM dùng định nghĩa lớp `Box` chung.
- **Đối tượng:** mỗi lần `new` vẫn tạo một instance riêng; giá trị bên trong vẫn có runtime class thật như `String`, `Integer`.
- **Reflection:** có thể biết lớp runtime và đọc generic metadata khai báo, nhưng `Box.class` không tự cung cấp đối số `String` hay `Integer` của mọi instance.
- **Thiết kế API:** nếu logic chạy thực sự phải biết kiểu cụ thể, truyền token/metadata đúng mục đích; đừng dựa vào `getClass()` của hộp để suy ra tham số generic.

Điểm then chốt: `Box<String>` và `Box<Integer>` **chia sẻ lớp runtime vì Java dùng type erasure**, trong khi an toàn kiểu generic chủ yếu được kiểm tra lúc biên dịch.
