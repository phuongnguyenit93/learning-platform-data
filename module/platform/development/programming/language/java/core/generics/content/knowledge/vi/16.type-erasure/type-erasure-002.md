# Xóa tham số generic không có giới hạn về `Object` trong Java

## Mục tiêu học tập

Bài này tập trung vào **type erasure (xóa kiểu)** đối với một tham số kiểu generic **không khai báo giới hạn** như `<T>`. Sau khi học, bạn có thể:

- Giải thích tại sao `T` không có `extends ...` được xóa thành `java.lang.Object` trong dạng bytecode của field, tham số phương thức và kiểu trả về trực tiếp sử dụng `T`.
- Phân biệt kiểm tra kiểu lúc **biên dịch** với kiểu trong **method descriptor của JVM**.
- Tìm bằng chứng bằng `javap` và reflection, kể cả lý do reflection vẫn có thể đọc ký hiệu `T` từ metadata.
- Giải thích chỗ trình biên dịch thêm phép ép kiểu khi lấy giá trị generic; nhận diện nguy cơ `ClassCastException` khi phá vỡ an toàn kiểu.
- Nhận biết những hạn chế điển hình do type erasure gây ra và tránh hiểu nhầm về `List<String>` so với `List<Integer>`.

## 1. Từ generic ở mã nguồn đến chương trình chạy

Xét một lớp generic:

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` là **tham số kiểu** (*type parameter*) do lớp `Box` khai báo. Trong `Box<T>`, `T` không có giới hạn tường minh: không có `T extends Number`, `T extends Comparable<T>` hay giao diện tương tự.

Ở mã nguồn, người dùng có thể khai báo:

```java
Box<String> name = new Box<>("Lan");
String value = name.get();
```

Trình biên dịch xác nhận `name.get()` có kiểu biểu thức `String` và cấm, chẳng hạn, `name` nhận một đối tượng `Integer` qua phương thức `set(T)` nếu có khai báo phương thức ấy.

Nhưng thông tin `String` của `Box<String>` không tạo ra một lớp máy ảo riêng tên `Box<String>`. Java generics sử dụng **type erasure**: trình biên dịch biểu diễn những vị trí dùng tham số kiểu bằng kiểu có thể tồn tại trong JVM descriptor, đồng thời chèn một số phép kiểm tra/cast cần thiết để bảo toàn ngữ nghĩa ở phía người gọi.

Quy tắc trọng tâm của bài:

> Khi xóa một tham số kiểu không có giới hạn như `T`, kiểu được dùng thay thế là **`Object`**.

Điều này mô tả **cách biên dịch khai báo/tham chiếu kiểu**, không phải một hành động chuyển đối tượng `String` thành đối tượng `Object` mới. Chuỗi `"Lan"` vẫn thực sự là một đối tượng `String` lúc chạy.

## 2. `<T>` và `<T extends Object>`

Hai dạng dưới đây có cùng giới hạn trên hiệu dụng đối với `T`:

```java
class Unbounded<T> {
    T value;
}

class ExplicitObject<T extends Object> {
    T value;
}
```

Theo quy tắc type erasure:

| Vị trí dùng `T` | Mã nguồn | Kiểu xóa trong descriptor |
| --- | --- | --- |
| Field | `T value` | `java.lang.Object value` |
| Tham số | `void set(T value)` | `void set(Object value)` |
| Giá trị trả về | `T get()` | `Object get()` |
| Phương thức generic | `static <T> T echo(T x)` | `Object echo(Object x)` |
| Giá trị bên trong `List<T>` | `List<T> items` | Bản thân tham số là `java.util.List` (kiểu đối số `T` bị xóa) |

Trường hợp cuối cần chú ý: toàn bộ tham số `List<T>` trở thành descriptor của **`List`**, không phải descriptor `Object`; chính `T` ở vị trí đối số kiểu bị xóa khỏi descriptor. Nếu `T` xuất hiện trực tiếp như tham số hoặc kiểu trả về, vị trí ấy được thay bằng `Object`.

Để đối chiếu ở mức quy tắc: nếu khai báo `<T extends Number>` thì erasure của `T` là `Number`, không còn là `Object`. Với nhiều giới hạn như `<T extends Runnable & AutoCloseable>`, erasure của `T` dựa trên **giới hạn đầu tiên** là `Runnable`. Bài này tập trung vào trường hợp `<T>` không giới hạn.

## 3. Ví dụ Java 17 chạy được, có bằng chứng từ reflection

Tạo đúng tệp `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

public final class ErasureDemo {
    static final class Box<T> {
        private T value;

        Box(T value) { this.value = value; }

        T get() { return value; }

        void set(T value) { this.value = value; }
    }

    static <T> T echo(T value) {
        return value;
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box<String> textBox = new Box<>("Java");
        String text = textBox.get();
        System.out.println("value: " + text.toUpperCase());
        System.out.println("echo: " + echo(123));
        System.out.println("first: " + first(List.of("A", "B")));

        Field field = Box.class.getDeclaredField("value");
        Method method = ErasureDemo.class
                .getDeclaredMethod("echo", Object.class);
        System.out.println("field type: " + field.getType().getTypeName());
        System.out.println("field generic type: "
                + field.getGenericType().getTypeName());
        System.out.println("echo parameter: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("echo return: "
                + method.getReturnType().getTypeName());
        System.out.println("echo generic return: "
                + method.getGenericReturnType().getTypeName());
        System.out.println("same class: "
                + textBox.getClass().equals(new Box<>(7).getClass()));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên, từ thư mục chứa tệp:

```bash
javac ErasureDemo.java
java ErasureDemo
```

**Kết quả thực tế đã kiểm tra:**

```text
value: JAVA
echo: 123
first: A
field type: java.lang.Object
field generic type: T
echo parameter: java.lang.Object
echo return: java.lang.Object
echo generic return: T
same class: true
```

Đọc từng điểm:

1. `Box<String>` cho phép gán `textBox.get()` vào `String` ở mã nguồn. JVM lại biết `Box.get()` trả về `Object`; trình biên dịch chèn một phép `checkcast String` ở phía người gọi.
2. `echo(123)` dùng autoboxing từ `int` thành `Integer`. `T` được suy luận hợp lý tại compile time, nhưng method descriptor của `echo` vẫn dùng `Object`.
3. `first(List<T>)` minh họa kiểu tham số được xóa là `List`, còn kết quả `T` được xóa thành `Object`. Ở vị trí cần dùng kết quả như chuỗi, có thể xuất hiện cast tương ứng.
4. `field.getType()` và `method.getReturnType()` báo **kiểu khai báo bị xóa** trong runtime descriptor: `Object`.
5. `getGenericType()` và `getGenericReturnType()` có thể báo **`T`** vì class file còn chứa thông tin khai báo generic phục vụ reflection.
6. Hai biểu thức `new Box<>("Java")` và `new Box<>(7)` tạo đối tượng của **cùng runtime class `Box`**, cho nên dòng cuối in `true`.

Lưu ý: `Box.class` và `ErasureDemo.class` là các class literal hợp lệ. Không có class literal riêng dành cho `Box<String>` hoặc `Box<Integer>`.

## 4. Xác minh bằng `javap`: nhìn descriptor thật

Sau khi biên dịch tệp trên, dùng lệnh sau. Cú pháp đặt dấu nháy quanh tên nested class tùy shell: trong Bash, dùng dấu nháy đơn để tránh `$` bị diễn giải; trong PowerShell, cách viết bên dưới cũng hợp lệ.

```bash
javap -s -p 'ErasureDemo$Box'
javap -s -p ErasureDemo
```

Trích đoạn **đã xác minh bằng `javap`** (chỉ những thành phần liên quan):

```text
final class ErasureDemo$Box<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  ErasureDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;

  void set(T);
    descriptor: (Ljava/lang/Object;)V
}
```

Với `ErasureDemo`:

```text
static <T> T echo(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

static <T> T first(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/lang/Object;
```

**Cách đọc descriptor:** `Ljava/lang/Object;` là kiểu tham chiếu `java.lang.Object`; `Ljava/util/List;` là `java.util.List`; `V` là `void`. Trong descriptor của phương thức, phần nằm giữa `(` và `)` là danh sách kiểu tham số; phần sau `)` là kiểu trả về.

`javap` vẫn in `T` ở chữ ký hiển thị trong một số chế độ vì thông tin **generic signature** của khai báo có thể được ghi kèm class file. Điều quyết định lời gọi ở mức JVM là phần `descriptor` đã xóa kiểu. Không nhầm chữ ký hiển thị `T get()` với descriptor `()Ljava/lang/Object;`.

Muốn nhìn thấy phép ép kiểu được compiler chèn, chạy:

```bash
javap -c -p ErasureDemo
```

Trong bytecode phương thức `main`, đoạn gọi `textBox.get()` có chuỗi lệnh tương tự:

```text
invokevirtual ... Box.get:()Ljava/lang/Object;
checkcast     ... class java/lang/String
astore_2
```

Các chỉ số constant pool, số dòng bytecode và tên lớp được `javap` viết tắt có thể thay đổi theo compiler/cấu trúc chương trình, nhưng `get` trả `Object` rồi `checkcast String` là điểm cần kiểm tra. Đoạn trích minh họa này thuộc chương trình đã biên dịch ở trên.

## 5. Tại sao lập trình viên vẫn được bảo vệ về kiểu?

Trong Java, generics đưa kiểm tra kiểu vào **compile time**. Ví dụ:

```java
Box<String> box = new Box<>("OK");
box.set("Java");  // Hợp lệ.
// box.set(42);   // Lỗi biên dịch: Integer không phù hợp với String.
String s = box.get();
```

Chữ ký `set(T)` của `Box<String>` được trình biên dịch hiểu là cần `String` tại điểm gọi. Khi xuống bytecode, `set` nhận `Object` nhưng tính đúng đắn được đảm bảo bởi những lời gọi Java có kiểm tra kiểu. Tương tự, `get` trả `Object` ở descriptor nhưng compiler thêm cast khi phía nhận cần `String`.

Cách hình dung gần đúng (chỉ **minh họa mô hình biên dịch**, không phải mã mà compiler bắt buộc sinh lại dưới dạng source Java):

```java
final class BoxErased {
    private Object value;

    BoxErased(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }

    void set(Object value) {
        this.value = value;
    }
}

// Mô phỏng tại chỗ gọi:
// BoxErased box = new BoxErased("Java");
// String s = (String) box.get();
```

Ở chương trình thật, compiler không nhất thiết tạo một lớp `BoxErased`; ví dụ chỉ làm hiện rõ các vị trí `T` được thay bằng `Object`. Lớp gốc `Box` đã được biên dịch trực tiếp với descriptor phù hợp.

Việc xóa tham số kiểu góp phần giúp các API dùng generics tương tác với lớp và mã Java đời trước. Nhưng đó không phải một bảo đảm rằng bất kỳ đường đi dữ liệu nào ở runtime cũng tuyệt đối an toàn: cast vẫn có thể thất bại nếu một lời gọi bỏ qua kiểm tra kiểu thông qua raw type hoặc thao tác không an toàn khác.

## 6. Khi raw type làm hỏng giả định của compiler

Đây là ví dụ **cố tình không an toàn** để quan sát giới hạn của erasure:

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeRawDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;              // Raw type: mất đối số kiểu String.
        raw.add(42);                  // Cảnh báo unchecked của compiler.

        try {
            String first = words.get(0); // Cast sang String lúc đọc.
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("Runtime failure: " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy bằng:

```bash
javac -Xlint:unchecked UnsafeRawDemo.java
java UnsafeRawDemo
```

Stdout dự kiến:

```text
Runtime failure: ClassCastException
```

Lệnh `javac -Xlint:unchecked` cũng đưa ra cảnh báo biên dịch về `raw.add(42)`; văn bản cảnh báo cụ thể thay đổi theo JDK và không thuộc stdout của ứng dụng.

Diễn biến: `raw` và `words` tham chiếu **cùng một** `ArrayList`; do raw type, lời gọi `add(42)` lọt qua với cảnh báo. Khi đọc lại qua `List<String>`, compiler kỳ vọng `String` và sinh cast; đối tượng thực là `Integer`, nên phát sinh `ClassCastException`. Lỗi này không chứng minh rằng generic vô hiệu: nó cho thấy **bỏ qua cảnh báo và phá vỡ kiểu hóa** khiến bảo đảm compile time không còn đầy đủ.

Trong dự án thông thường, tránh raw types, unchecked casts tùy tiện và trộn dữ liệu generic với API không an toàn. Không dùng `@SuppressWarnings("unchecked")` để che một vấn đề chưa có bằng chứng an toàn.

## 7. Những giới hạn trực tiếp từ việc `T` bị xóa

### 7.1. Không thể phân biệt các tham số kiểu bằng `instanceof`

Sai:

```java
// if (value instanceof List<String>) { } // Không biên dịch.
```

Vì đối số kiểu `String` của `List<String>` không được hiện thực hóa thành runtime subtype riêng. Có thể kiểm tra phần kiểu còn tồn tại:

```java
if (value instanceof List<?>) {
    // Chỉ biết đó là một List; chưa thể khẳng định
    // tất cả phần tử là String.
}
```

Đoạn minh họa trên giả định `value` là biến tham chiếu đã khai báo, chẳng hạn `Object value`.

### 7.2. Không có `T.class` hoặc `new T()`

Đoạn sau không hợp lệ:

```java
class Factory<T> {
    // Class<T> type = T.class;        // Lỗi.
    // T value = new T();              // Lỗi.
    // T[] items = new T[10];          // Lỗi.
}
```

Khi `T` không được hiện thực hóa thành một `Class` cụ thể trong JVM, không thể dùng `T` ở các biểu thức cần lớp runtime cụ thể như trên.

Nếu cần tạo đối tượng, truyền một `Supplier<? extends T>`; nếu cần một `Class<T>`, truyền token tường minh:

```java
static <T> T make(java.util.function.Supplier<? extends T> supplier) {
    return supplier.get();
}

// Ví dụ gọi trong ngữ cảnh có phương thức make:
// StringBuilder builder = make(StringBuilder::new);
```

Đây là đoạn mã minh họa cần được đặt trong một lớp và có chỗ gọi phù hợp.

### 7.3. Không thể overload chỉ nhờ khác đối số generic

Hai phương thức sau xung đột **name clash**, vì sau erasure cả hai có cùng dạng tham số `List`:

```java
// Không thể cùng khai báo trong một lớp:
void show(List<String> strings) { /* ... */ }
void show(List<Integer> integers) { /* ... */ }
```

Tương tự, trong cùng một lớp, `void receive(Object x)` và `<T> void receive(T x)` có cùng danh sách tham số bị xóa là `(Object)`, nên không thể dùng chúng làm hai overload riêng.

Cách xử lý: chọn tên phương thức rõ mục đích (`showStrings`, `showIntegers`), hoặc thiết kế **một** generic method có hành vi phù hợp, hoặc truyền thêm chiến lược/metadata tường minh.

### 7.4. Không suy ra `T` cụ thể từ chính đối tượng `Box<T>`

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(10);
// a.getClass().equals(b.getClass()) == true
```

Một đối tượng `Box<String>` không mang thẻ runtime ghi rằng nó đã được khởi tạo với `String` theo cách một runtime class riêng sẽ có. Reflection có thể đọc **khai báo** `Box<T>` và metadata generic trên field/phương thức, nhưng nhìn vào `a.getClass()` không đủ để suy luận tham số kiểu cụ thể `String` ở nơi đã tạo `a`.

Không lẫn điều này với `a.get()`: giá trị trả về vẫn là đối tượng `String` thực và có thể gọi `a.get().getClass()` để biết lớp của **giá trị đang có**. Kết quả đó không chứng minh lớp `Box` giữ tham số kiểu `T` cụ thể qua mọi trường hợp; hộp có thể rỗng hoặc chứa `null`.

## 8. Generic signature không mâu thuẫn với type erasure

Một field khai báo `T value` trong `Box<T>` không bound có hai cách nhìn hợp lệ:

- **Descriptor JVM**: field có kiểu `Object` (mã `Ljava/lang/Object;`).
- **Generic `Signature` metadata**: vẫn có thể lưu tên biến kiểu `T` và khai báo generic của lớp.

Vì vậy, `Field.getType()` có thể trả `Object.class`, còn `Field.getGenericType()` có thể là `TypeVariable`. Đây không phải hai runtime classes cho `Box<String>` và `Box<Integer>`, cũng không bảo đảm biết đối số kiểu của từng object. Bài cuối chương giải thích chi tiết cơ chế `Signature`; tại đây điều cần chứng minh là **erasure của unbounded `T` vẫn là `Object`**.

## 9. So sánh trước/sau xóa kiểu: nắm đúng phạm vi

| Câu hỏi | Trước erasure ở mã nguồn | Sau erasure/ở runtime |
| --- | --- | --- |
| Có thể gọi `box.set(42)` với `Box<String>`? | Compiler báo lỗi | JVM chỉ thấy descriptor `set(Object)`, nhưng chương trình hợp lệ đã được kiểm tra lúc biên dịch |
| `T get()` không giới hạn trở thành gì? | `T` | Descriptor trả `Object` |
| `<T> T echo(T)` trở thành gì? | Phương thức generic | Descriptor `(Object)Object` |
| `<T> T first(List<T>)`? | Nhận `List<T>`, trả `T` | Descriptor `(List)Object` |
| Có `Box<String>.class` riêng? | Cú pháp class literal như vậy không hợp lệ | Một `Box.class` dùng chung |
| `String` có bị đổi thành `Object` khi lưu trong `Box`? | Không | Không; đối tượng vẫn là `String` |
| Có thể biết tên tham số khai báo là `T` không? | Có | Có thể qua generic signature/reflection |
| Cast lấy `String` khi `get()` trả erased `Object`? | Compiler hiểu kiểu biểu thức là `String` | Compiler có thể chèn `checkcast String` |

Không nên tưởng tượng quá trình xóa kiểu là thay mọi chữ `String` trong chương trình bằng `Object`. Quy tắc ở đây tác động đến **tham số generic và các vị trí dùng tham số generic**. Một biến trực tiếp khai báo `String s` vẫn có descriptor `String` khi thích hợp; đối tượng thực vẫn giữ lớp thực của nó.

## 10. Tự luyện: đọc, dự đoán và sửa lỗi

**Bài 1 — Dự đoán descriptor.** Với:

```java
static <T> T choose(T x, T y) {
    return x;
}
```

Hỏi: tham số và kiểu trả về ở descriptor là gì? **Đáp án:** `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;`.

**Bài 2 — Tham số chứa `T`.** Với:

```java
static <T> T tail(java.util.List<T> items) {
    return items.get(items.size() - 1);
}
```

Hỏi: descriptor của `tail` là gì? **Đáp án:** `(Ljava/util/List;)Ljava/lang/Object;`. `List` giữ loại container, đối số generic `T` bị xóa khỏi descriptor.

**Bài 3 — Kiểu cụ thể có biến mất khỏi đối tượng?** Cho `Box<String> x = new Box<>("Hello");`. Hỏi `x.get().getClass().getName()` cho biết gì? **Đáp án:** `java.lang.String`, vì giá trị thật vẫn là chuỗi; kết quả không cho biết một runtime class riêng dành cho `Box<String>`.

**Bài 4 — Reflection.** Với field `T value` không giới hạn, tại sao `getType()` báo `Object` nhưng `getGenericType()` có thể báo `T`? **Đáp án:** descriptor erased và metadata generic signature phản ánh hai lớp thông tin khác nhau.

**Bài 5 — Thiết kế API.** Bạn muốn lớp generic tạo `T` mới nhưng `new T()` không hợp lệ. Hãy viết hàm nhận `Supplier<? extends T>` rồi gọi `get()`. Kiểm tra tại sao cách này làm quyết định tạo đối tượng trở nên tường minh.

**Bài 6 — Dự đoán lỗi.** Giải thích vì sao hai overload `show(List<String>)` và `show(List<Integer>)` trong cùng lớp bị từ chối. **Đáp án:** cùng danh sách kiểu tham số `List` sau erasure; không thể phân biệt overload bằng đối số generic vốn bị xóa.

## Ghi nhớ

**Tham số generic không có giới hạn `<T>` có erasure là `Object`.** Điều đó biểu hiện trực tiếp ở bytecode descriptor của field, tham số và giá trị trả về dùng `T`; với `List<T>`, descriptor giữ `List` và xóa đối số kiểu. Java vẫn kiểm tra tương thích kiểu tại thời điểm biên dịch, có thể thêm cast ở phía dùng dữ liệu và giữ generic signature để reflection đọc lại khai báo. Dù không có runtime class `Box<String>` riêng, các đối tượng như `String` được lưu bên trong vẫn là `String` thật.
