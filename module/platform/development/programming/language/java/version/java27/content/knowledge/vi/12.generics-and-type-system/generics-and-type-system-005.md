# Type erasure và giới hạn kiểu tại runtime

Trong Java 27, **generics** giúp trình biên dịch kiểm tra các ràng buộc kiểu như `List<String>`, `Map<String, Integer>` hay `Box<T>` trước khi chương trình chạy. Tuy nhiên, phần lớn thông tin về **type arguments** không được lưu trong từng đối tượng để JVM có thể kiểm tra như một kiểu độc lập tại runtime. Cơ chế này gọi là **type erasure** (xóa kiểu).

Hiểu type erasure giúp trả lời những câu hỏi thực tế: vì sao `List<String>` và `List<Integer>` dùng cùng một lớp tại runtime; tại sao không thể thử tổng quát `instanceof List<String>`; vì sao generic array khó tạo; `ClassCastException` có thể xuất hiện dù mã đã dùng generics; và làm thế nào để xác thực phần tử an toàn khi nhận dữ liệu không tin cậy.

Bài thuộc chương **Generics và hệ thống kiểu** của module **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Toàn bộ quy tắc chính được đối chiếu với Java Language Specification (JLS) Java SE 27. Các giải pháp đều sử dụng API và cú pháp chính thức còn hiệu lực, không dựa vào kỹ thuật legacy để phát triển mã mới.

## 1. Generics kiểm tra điều gì trước khi chạy?

Xét đoạn mã:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("Java");

// names.add(27); // Lỗi biên dịch: Integer không tương thích String.

String first = names.get(0);
```

`List<String>` cho trình biên dịch biết:

1. Khi gọi `add`, giá trị được truyền vào phải tương thích với `String`.
2. Khi gọi `get`, biểu thức có kiểu tĩnh `String`; người dùng API không phải tự viết ép kiểu thông thường.
3. Các thao tác không đúng hợp đồng kiểu được phát hiện **trước khi chạy**, miễn luồng dữ liệu tuân thủ an toàn kiểu và không qua unchecked operation.

Điều này **không** có nghĩa đối tượng `ArrayList` đang lưu một trường runtime tự mô tả rằng “tôi là `ArrayList<String>`”. JVM vẫn có class runtime của đối tượng, nhưng thông thường không có type argument `String` của từng lần tạo instance.

## 2. Type erasure là gì?

Theo JLS §4.6, erasure là phép ánh xạ từ các kiểu có thể chứa type parameters hoặc type arguments sang những kiểu **không còn được tham số hóa**. Một số quy tắc quan trọng:

| Kiểu trong mã nguồn | Kiểu sau erasure | Giải thích |
|---|---|---|
| `List<String>` | `List` | Loại bỏ type argument |
| `Map<String, Integer>` | `Map` | Loại bỏ tất cả type arguments |
| `Box<T>` | `Box` | Bỏ tham số kiểu của generic class |
| `T` với `<T>` | `Object` | Type variable không có bound tường minh |
| `T` với `<T extends Number>` | `Number` | Bound bên trái được dùng |
| `T` với `<T extends Number & Comparable<T>>` | `Number` | Lấy erasure của **bound đầu tiên** |
| `List<String>[]` | `List[]` | Erasure áp dụng cả phần tử kiểu mảng |

Erasure không phải thao tác tìm và xóa chuỗi `<...>` trong mọi tệp nguồn. Trình biên dịch còn phải giải quyết gọi phương thức, kiểm tra kiểu, thêm ép kiểu cần thiết và đôi khi tạo **bridge methods** để bảo toàn cơ chế override. Một phần thông tin generic trên khai báo có thể vẫn được lưu dưới dạng metadata trong class file; mục 9 giải thích ngoại lệ này.

### 2.1. Type variable không có bound

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Về mặt khái niệm, sau erasure, trường `value` và các thao tác liên quan đến `T` được biểu diễn bằng `Object`. Đây là mô hình để **hiểu**, không phải mã Java thực sự mà trình biên dịch sinh lại thành một tệp nguồn mới:

```java
// Mô phỏng để hiểu erasure, KHÔNG phải bản dịch do javac xuất ra.
class BoxErased {
    private final Object value;

    BoxErased(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

Khi sử dụng `Box<String>`, trình biên dịch biết kết quả có kiểu `String` và có thể chèn kiểm tra cast ở điểm sử dụng tương ứng khi bytecode làm việc với `Object`.

### 2.2. Type variable có bound

```java
static <T extends Number & Comparable<T>> double twice(T value) {
    return value.doubleValue() * 2;
}
```

Erasure của `T` ở đây là `Number`, vì `Number` đứng đầu danh sách bound. Nhờ đó, mã đã biên dịch vẫn gọi được `Number.doubleValue()`. Các bound còn lại được dùng để kiểm tra tính hợp lệ của `T` trong quá trình biên dịch.

Nếu muốn sử dụng một phương thức chỉ nằm trên bound tiếp theo, trình biên dịch bảo đảm việc truy cập phù hợp thông qua các kiểm tra/cast cần thiết; không có một “lớp runtime hợp nhất” mới được tạo cho `Number & Comparable<T>`.

## 3. `List<String>` và `List<Integer>` có cùng runtime class

Hai lần sử dụng cùng một generic class với type arguments khác nhau **không** tạo ra hai phiên bản class JVM độc lập:

```java
import java.util.ArrayList;
import java.util.List;

List<String> words = new ArrayList<>();
List<Integer> scores = new ArrayList<>();

System.out.println(words.getClass() == scores.getClass()); // true
System.out.println(words.getClass().getName());            // java.util.ArrayList
```

`getClass()` phản ánh lớp runtime của đối tượng, trong cả hai trường hợp đều là `java.util.ArrayList`. Nó không cho biết đối tượng được tạo ban đầu dưới biến `List<String>` hay `List<Integer>`.

Một hệ quả quan trọng: **generic class không tự động được chuyên biệt hóa thành một class runtime mới cho mỗi type argument**. JVM/JIT vẫn có thể thực hiện các tối ưu hóa riêng trong quá trình thực thi, nhưng đó không phải một cơ chế bảo đảm rằng mỗi `T` có lớp generic riêng.

Điều này khác với cách JVM quản lý kiểu của **mảng**: một mảng `String[]` có runtime component type là `String`, còn `List<String>` thường không mang type argument `String` trên từng đối tượng.

## 4. Reifiable và non-reifiable types

JLS §4.7 gọi những kiểu có đủ thông tin để nhận diện tại runtime là **reifiable types**. Type arguments cụ thể của nhiều generic types bị erasure, khiến chúng trở thành **non-reifiable types**.

| Kiểu | Reifiable? | Ý nghĩa |
|---|---|---|
| `String` | Có | Lớp không generic |
| `String[]` | Có | Mảng có kiểu phần tử reifiable |
| `List<?>` | Có | Generic type chỉ chứa unbounded wildcard |
| `List<String>` | **Không** | Type argument cụ thể `String` không được kiểm tra đầy đủ tại runtime |
| `Map<String, Integer>` | **Không** | Hai type arguments cụ thể bị erasure |
| Type variable `T` | **Không** | Kiểu thực của tham số không có sẵn trong mọi lần chạy |
| `List<?>[]` | Có | Kiểu phần tử `List<?>` là reifiable |

**Reifiable** là thuật ngữ về khả năng biểu diễn/kiểm tra kiểu tại runtime, không đồng nghĩa “tất cả phần tử của một collection được xác thực tự động”. Ví dụ, `List<?>` cho phép biết giá trị có dạng `List`, nhưng không xác nhận các phần tử là `String` hay `Integer`.

## 5. Giới hạn của `instanceof` và pattern matching

Nếu giá trị đầu vào được khai báo bằng `Object`, bạn không thể dùng type argument cụ thể của một `List` để kiểm tra trực tiếp nội dung qua `instanceof`:

```java
Object input = java.util.List.of("Java", "JVM");

// Không hợp lệ với input kiểu Object:
// if (input instanceof java.util.List<String>) { ... }
```

Bạn có thể kiểm tra kiểu collection theo cách **an toàn về reifiability**:

```java
static boolean isNonEmptyList(Object input) {
    if (input instanceof java.util.List<?> items) {
        return !items.isEmpty();
    }
    return false;
}
```

`List<?> items` bảo đảm đối tượng có kiểu tương thích với `List`, **không** bảo đảm mọi phần tử là `String`. Muốn xác minh phần tử, hãy kiểm tra từng phần tử:

```java
static boolean isStringList(Object input) {
    if (!(input instanceof java.util.List<?> items)) {
        return false;
    }
    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Mã trên chấp nhận danh sách rỗng (vì không có phần tử sai kiểu); đó là một quyết định hợp lý theo nghĩa “mọi phần tử, nếu có, đều là chuỗi”. Nếu dữ liệu phải chứa ít nhất một chuỗi, cần thêm điều kiện `!items.isEmpty()`.

**Độ chính xác về ngôn ngữ:** Java hiện đại có những ngữ cảnh `instanceof` với kiểu tham số hóa được phép khi **kiểu tĩnh của biểu thức** khiến phép kiểm tra an toàn. Không nên suy diễn rằng mọi cú pháp `instanceof SomeGeneric<...>` đều bị cấm tuyệt đối. Tuy nhiên, không có phép kiểm tra tổng quát nào trên một `Object` để JVM tự xác minh mọi type argument của `List<String>` từ các đối tượng phần tử. Quy tắc dùng `List<?>` rồi kiểm tra nội dung vẫn là cách thích hợp cho dữ liệu chưa rõ kiểu.

## 6. Vì sao không tạo trực tiếp mảng generic?

Mảng Java có component type được kiểm tra tại runtime. Generics lại cho phép type arguments không reifiable. Nếu tạo tùy ý `new List<String>[10]`, chương trình có thể đưa một `List<Integer>` vào mảng dưới một tham chiếu mảng rộng hơn mà JVM không phát hiện được type argument sai.

Vì vậy, các cách viết sau không hợp lệ:

```java
// Không biên dịch:
// java.util.List<String>[] groups = new java.util.List<String>[10];

// Trong class generic có type variable T:
// T[] array = new T[10];
```

Khi cần giữ nhiều danh sách, lựa chọn thông thường là **collection lồng nhau**:

```java
java.util.List<java.util.List<String>> groups =
        new java.util.ArrayList<>();
groups.add(java.util.List.of("Java", "JVM"));
groups.add(java.util.List.of("JDK", "JLS"));
```

`new List<?>[10]` là một trường hợp khác: phần tử `List<?>` reifiable, vì vậy cú pháp đó có thể hợp lệ. Tuy nhiên, vẫn không cung cấp thông tin runtime rằng mọi phần tử của danh sách bên trong đều là `String`.

### 6.1. So sánh với kiểm tra gán phần tử của mảng

```java
Object[] values = new String[1];
// values[0] = 42; // Khi chạy sẽ ném ArrayStoreException.
```

Mảng thật sự biết component type `String` nên JVM có thể chặn phép gán `Integer` vào mảng đó. Một `List<String>` thông thường không có cơ chế kiểm tra type argument ở mỗi lời gọi runtime nếu an toàn kiểu đã bị phá vỡ qua unchecked operation.

## 7. Vì sao không dùng `new T()` hoặc `T.class`?

Trong class hoặc generic method nhận tham số `T`, type erasure khiến JVM không nhất thiết biết constructor hay class runtime của `T`:

```java
class Factory<T> {
    // Không hợp lệ:
    // T value = new T();
    // Class<T> type = T.class;
}
```

Để tạo giá trị một cách minh bạch, hãy truyền **factory** từ bên ngoài, chẳng hạn `Supplier<T>`:

```java
import java.util.function.Supplier;

static <T> T create(Supplier<? extends T> factory) {
    return factory.get();
}

StringBuilder text = create(StringBuilder::new);
text.append("Java 27");
```

Ở đây, bên gọi quyết định cách khởi tạo `T`; hàm generic không giả định rằng mọi kiểu đều có constructor không tham số. Nếu cần runtime class, một lựa chọn khác là truyền `Class<T>`, nhưng `Class<T>` chỉ đại diện cho kiểu runtime **có thể biểu diễn** như `String.class`, chứ không giữ nguyên tùy ý `List<String>` trong một class literal.

Ngoài ra, không thể khai báo một trường `static T shared;` trong class `Container<T>`, vì thành phần static thuộc về class dùng chung chứ không thuộc một instantiation `Container<String>` riêng. Một static **generic method** tự khai báo `<T>` của chính nó thì vẫn hợp lệ:

```java
static <T> T identity(T value) {
    return value;
}
```

## 8. Heap pollution và `ClassCastException` đến từ đâu?

**Heap pollution** xảy ra khi một biến có kiểu tham số hóa trỏ tới dữ liệu không thực sự đáp ứng kiểu đã khai báo. Nó thường liên quan tới raw types, unchecked casts hoặc thao tác varargs/array không an toàn.

Ví dụ sau **có chủ ý minh họa mã không an toàn**, không phải mẫu nên dùng trong codebase mới:

```java
import java.util.ArrayList;
import java.util.List;

List<String> words = new ArrayList<>();

List raw = words;  // Raw type, không nên dùng trong mã mới.
raw.add(27);       // Unchecked warning khi biên dịch.

String word = words.get(0); // ClassCastException tại runtime.
```

Vì sao lỗi xuất hiện **khi đọc** chứ không phải lúc `add`? `ArrayList` sau erasure chỉ nhận một tham chiếu `Object` ở vị trí đó; thông tin “danh sách chỉ chứa `String`” không được JVM kiểm tra tự động từ type argument của instance. Khi kết quả `get(0)` được dùng như `String`, cast cần thiết thất bại.

**Raw type** vẫn tồn tại trong ngôn ngữ để tương tác với những API chưa tham số hóa, nhưng không nên được dùng như mô hình thiết kế mới. Trình biên dịch cảnh báo `unchecked` vì không thể chứng minh thao tác giữ hợp đồng kiểu.

Để xem rõ warning khi biên dịch:

```bash
javac -Xlint:unchecked Example.java
```

Một cast từ `Object` sang `List<String>` cũng không thể xác thực phần tử:

```java
Object source = java.util.List.of(10, 20);

// Có thể đưa ra unchecked warning:
// List<String> strings = (List<String>) source;
// String text = strings.get(0); // Có thể ClassCastException.
```

Không nên chữa vấn đề bằng cách thêm `@SuppressWarnings("unchecked")` rộng khắp. Chỉ chặn warning ở phạm vi nhỏ nhất **sau khi** có bằng chứng hoặc kiểm tra bảo đảm phép chuyển đổi thực sự an toàn.

### 8.1. Varargs của kiểu không reifiable

Tham số biến độ dài `List<String>...` được triển khai qua mảng, trong khi `List<String>` không reifiable. Điều này có thể tạo khe hở an toàn kiểu:

```java
// Ví dụ minh họa nguy cơ: KHÔNG viết mã mới theo cách này.
static void unsafe(java.util.List<String>... batches) {
    Object[] array = batches;
    array[0] = java.util.List.of(42);
    String value = batches[0].get(0); // ClassCastException.
}
```

Compiler có thể cảnh báo về tham số varargs của non-reifiable type và lời gọi tương ứng. Trong phương thức thực sự an toàn, `@SafeVarargs` cho phép lập trình viên cam kết rằng việc dùng mảng varargs không gây heap pollution hoặc lộ mảng theo cách nguy hiểm. Annotation **không** làm JVM tự kiểm tra type arguments.

Ví dụ sử dụng an toàn trong phương thức `static`:

```java
import java.util.ArrayList;
import java.util.List;

@SafeVarargs
static <T> List<T> flatten(List<? extends T>... batches) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> batch : batches) {
        result.addAll(batch);
    }
    return List.copyOf(result);
}
```

Hàm không sửa cấu trúc mảng varargs, không đưa giá trị sai kiểu vào đó và không để mảng thoát ra ngoài. Chỉ sử dụng `@SafeVarargs` sau khi đã rà soát thật sự an toàn. Trong mã đơn giản, cũng có thể tránh varargs non-reifiable bằng cách nhận `List<? extends List<? extends T>>`.

## 9. Reflection: generic metadata vẫn có thể được giữ trên khai báo

Erasure **không có nghĩa** mọi chữ ký generic đều biến mất khỏi class file. Compiler có thể lưu thông tin khai báo kiểu ở metadata như `Signature` attribute. Reflection hỗ trợ đọc các khai báo như `List<String>` ở trường, phương thức hoặc superclass đã tham số hóa.

```java
import java.lang.reflect.Field;
import java.util.List;

class Repository {
    List<String> tags = List.of("java");
}

Field field = Repository.class.getDeclaredField("tags");

System.out.println(field.getType().getTypeName());
System.out.println(field.getGenericType().getTypeName());
```

Kết quả dự kiến:

```text
java.util.List
java.util.List<java.lang.String>
```

Hai truy vấn thể hiện hai góc nhìn khác nhau:

- `getType()` trả về kiểu class/interface ở runtime, sau erasure đối với khai báo này.
- `getGenericType()` có thể trả về `ParameterizedType` ghi nhận thông tin type argument **trên khai báo** `tags`.

Thông tin đó **không chứng minh** rằng mọi phần tử đang nằm trong instance của `tags` đều là `String`. Reflection đọc metadata của cấu trúc khai báo; nó không tự kiểm chứng dữ liệu thực tế trong một collection tại thời điểm chạy. Đặc biệt, khi chỉ có một đối tượng `ArrayList` bất kỳ, `object.getClass()` không thể suy ra type argument tùy ý của biến đã từng trỏ tới nó.

## 10. Giữ kiểm tra kiểu tại runtime bằng `Class<T>`

Khi nhận đầu vào từ nguồn có kiểu không chắc chắn (JSON đã parse, plugin, dữ liệu reflection, kết quả API cũ), ta có thể truyền **runtime type token** `Class<T>` và kiểm tra từng phần tử bằng `Class.cast`.

```java
import java.util.ArrayList;
import java.util.List;

static <T> List<T> checkedCopy(Iterable<?> source, Class<T> type) {
    List<T> output = new ArrayList<>();
    for (Object item : source) {
        output.add(type.cast(item));
    }
    return List.copyOf(output);
}

List<String> titles =
        checkedCopy(List.of("JDK", "JVM"), String.class);
```

Với phần tử không phải `String`, `String.class.cast(...)` ném `ClassCastException` **ngay tại điểm kiểm tra**; kết quả không bị gán nhãn kiểu sai âm thầm. `Class.cast(null)` trả về `null`, nhưng `List.copyOf(...)` sẽ không cho phép phần tử `null`, vì vậy thiết kế này còn có ràng buộc dữ liệu không null. Có thể thay cách sao chép nếu hợp đồng muốn chấp nhận `null`.

**Giới hạn:** `Class<T>` hoạt động phù hợp khi `T` là kiểu có class token cụ thể như `String`, `Integer` hay một lớp ứng dụng. Nó không biểu diễn đầy đủ kiểu lồng nhau như `List<String>`. Với dữ liệu lồng nhiều cấp, phải kiểm tra đệ quy hoặc dùng thư viện/định dạng dữ liệu có hệ thống type descriptor phù hợp; descriptor chỉ hướng dẫn xử lý dữ liệu chứ không khiến JVM tự khôi phục type arguments đã bị xóa khỏi từng instance.

### 10.1. Sử dụng collection có kiểm tra phần tử

Java vẫn cung cấp các wrapper kiểm tra kiểu khi thêm phần tử qua wrapper:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> names =
        Collections.checkedList(new ArrayList<>(), String.class);
names.add("Java"); // Hợp lệ.
```

Wrapper này kiểm tra các thao tác thêm qua chính nó. Nó không thể tự động làm sạch phần tử sai kiểu **đã có sẵn** trước khi bọc, và không bảo vệ khi mã khác còn giữ một alias tới collection gốc rồi chèn dữ liệu trực tiếp. Đối với dữ liệu đầu vào chưa tin cậy, **kiểm tra và sao chép vào collection mới** thường dễ kiểm soát hơn.

## 11. Bridge method: tại sao override vẫn hoạt động sau erasure?

Giả sử generic superclass khai báo một phương thức nhận `T`, còn subclass gắn `T` thành `String`:

```java
class Handler<T> {
    void handle(T value) {
        System.out.println("Base: " + value);
    }
}

class StringHandler extends Handler<String> {
    @Override
    void handle(String value) {
        System.out.println("String: " + value);
    }
}

Handler<String> handler = new StringHandler();
handler.handle("Java");
```

Kết quả là `String: Java`. Sau erasure, phương thức của `Handler` có chữ ký nhận `Object`, còn phương thức cụ thể trong `StringHandler` nhận `String`. Compiler có thể sinh một **bridge method** trong `StringHandler` để giữ nguyên tính đa hình:

```java
// Minh họa ý tưởng bridge, KHÔNG phải mã nguồn được viết thêm.
// void handle(Object value) {
//     handle((String) value);
// }
```

Bridge method là chi tiết do compiler tạo trong bytecode, không phải API mà người lập trình nên gọi trực tiếp. Có thể quan sát nó bằng `javap -c -v StringHandler` hoặc reflection với `Method.isBridge()`. Đừng dựa vào bridge methods để thực hiện logic nghiệp vụ.

### 11.1. Hai overload có cùng erasure không thể cùng tồn tại

Một hệ quả khác của erasure là **name clash**:

```java
// Không hợp lệ vì cả hai có erasure là process(List):
// void process(List<String> names) { ... }
// void process(List<Integer> numbers) { ... }
```

Hãy đổi tên theo mục đích (`processNames`, `processNumbers`), dùng tham số bổ sung phân biệt rõ ràng hoặc thiết kế một generic method thống nhất. Đừng cố chọn overload theo type argument, vì runtime không có hai chữ ký JVM khác nhau chỉ nhờ `String` so với `Integer` ở đây.

## 12. Phân biệt `List<Object>`, `List<?>` và wildcard có bound

Erasure không khiến các kiểu generic trở thành tùy ý thay thế cho nhau tại **compile time**. Java generics nhìn chung là **invariant**:

```java
List<String> strings = List.of("A");
// List<Object> objects = strings; // Không biên dịch.
List<?> unknown = strings;        // Hợp lệ.
```

| Kiểu khai báo | Có thể đọc | Có thể thêm |
|---|---|---|
| `List<Object>` | `Object` | Mọi đối tượng phù hợp `Object` |
| `List<?>` | `Object` | Không thể thêm giá trị non-null theo cách tổng quát |
| `List<? extends Number>` | `Number` | Không thể thêm một `Number` bất kỳ vì subtype cụ thể không rõ |
| `List<? super Integer>` | `Object` | Có thể thêm `Integer` |

Các ràng buộc này được **trình biên dịch** áp dụng dù runtime erasure có thể đều là `List`. Wildcard không tự kiểm tra “mọi phần tử là Number” nếu chương trình đã đi qua alias sai kiểu hoặc thao tác unchecked.

Khi thiết kế API, hãy tận dụng type parameters và wildcard để biểu diễn đúng quyền đọc/ghi; chỉ thêm runtime validation khi dữ liệu đến từ bên ngoài ranh giới an toàn kiểu.

## 13. Ví dụ hoàn chỉnh chạy trên Java 27

Lưu tệp `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class Repository {
        List<String> tags = List.of("Java");
    }

    static <T> List<T> checkedCopy(Iterable<?> input, Class<T> type) {
        List<T> output = new ArrayList<>();
        for (Object item : input) {
            output.add(type.cast(item));
        }
        return List.copyOf(output);
    }

    static String describe(Object value) {
        if (value instanceof List<?> items) {
            return "List có " + items.size() + " phần tử";
        }
        return "Không phải List";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(27);

        System.out.println(text.getClass() == number.getClass());
        System.out.println(describe(List.of("JVM", "JDK")));

        List<String> valid = checkedCopy(List.of("A", "B"), String.class);
        System.out.println(valid);

        try {
            checkedCopy(List.of("A", 42), String.class);
        } catch (ClassCastException ex) {
            System.out.println("Đã chặn phần tử sai kiểu");
        }

        Field field = Repository.class.getDeclaredField("tags");
        System.out.println(field.getType().getTypeName());
        System.out.println(field.getGenericType().getTypeName());
    }
}
```

Chạy:

```bash
java --version
java ErasureDemo.java
```

Kết quả:

```text
true
List có 2 phần tử
[A, B]
Đã chặn phần tử sai kiểu
java.util.List
java.util.List<java.lang.String>
```

Mẫu này minh họa ba điều **khác nhau**: cùng runtime class cho nhiều instantiation của `Box<T>`; `instanceof List<?>` chỉ xác nhận lớp collection; và thông tin generic của **khai báo trường** vẫn có thể đọc bằng reflection. Hàm `checkedCopy` cho phép xác thực từng phần tử thực tế khi cần.

## 14. Những lỗi thường gặp và phương án thay thế

| Sai lầm / tình huống | Vì sao có vấn đề? | Cách xử lý |
|---|---|---|
| Cho rằng `new ArrayList<String>()` mang runtime class khác `new ArrayList<Integer>()` | Cả hai sử dụng cùng generic class sau erasure | Dựa vào kiểm tra tĩnh và xác thực dữ liệu khi qua ranh giới tin cậy |
| Tưởng `instanceof List<?>` bảo đảm phần tử là `String` | Wildcard không lưu type argument cụ thể | Duyệt và kiểm tra các phần tử |
| Cast trực tiếp `Object` sang `List<String>` | Chỉ kiểm tra được phần reifiable; có thể có unchecked warning | Kiểm tra và sao chép từng phần tử với `Class<T>` |
| Tạo `new T()` hoặc `new T[10]` | Không có class/array component type runtime tùy ý cho `T` | Truyền `Supplier<T>`, token kiểu hoặc dùng collection |
| Tạo `new List<String>[10]` | Non-reifiable array creation bị cấm | Dùng `List<List<String>>` |
| Trộn raw type với parameterized type | Có thể gây heap pollution và `ClassCastException` | Không dùng raw type trong thiết kế mới; xử lý interop riêng |
| Chặn toàn bộ unchecked warnings | Che giấu rủi ro không kiểm tra được tại runtime | Kiểm tra nguồn dữ liệu và thu hẹp phạm vi suppression |
| Đánh dấu `@SafeVarargs` cho phương thức làm rò mảng hoặc ghi sai kiểu | Annotation chỉ là lời cam kết, không tự sửa lỗi | Rà soát varargs hoặc đổi API không dùng non-reifiable array |
| Dùng `getClass()` để đoán type arguments | Class của instance không giữ type arguments thông thường | Reflection đọc khai báo, hoặc truyền runtime type token |
| Overload chỉ khác `List<String>` và `List<Integer>` | Name clash sau erasure | Tách tên hoặc thay đổi thiết kế chữ ký |
| Hiểu `final` collection hay `List<String>` như bảo đảm dữ liệu runtime | `final` chỉ ngăn gán lại tham chiếu, generics chủ yếu kiểm tra tĩnh | Phân biệt tính bất biến, an toàn kiểu và kiểm tra runtime |

## 15. Checklist khi làm việc với generics và runtime

1. **Điều kiện compile-time hay runtime?** Nếu chỉ cần gọi API generic đúng kiểu, để compiler kiểm tra. Nếu nhận `Object` hoặc dữ liệu ngoài hệ thống, cần xác thực runtime.
2. **Kiểu cần kiểm tra có reifiable không?** `String` và `List<?>` có thể dùng trực tiếp trong kiểm tra phù hợp; `List<String>` không thể được xác thực tổng quát chỉ bằng `instanceof` trên `Object`.
3. **Có warning unchecked không?** Mỗi cảnh báo là nơi cần tìm hiểu nguồn dữ liệu và lý do cast an toàn, không phải chỉ để tắt.
4. **Có dùng generic array hoặc varargs non-reifiable không?** Ưu tiên `List<T>`; nếu cần varargs, kiểm tra nguy cơ heap pollution.
5. **Có cần bảo đảm kiểu từng phần tử không?** Truyền `Class<T>` và kiểm tra từng phần tử, hoặc dùng chiến lược xác thực kiểu lồng nhau phù hợp.
6. **Reflection có đang trả về metadata khai báo chứ không phải sự thật về dữ liệu?** Không dùng `ParameterizedType` trên một trường để suy rằng collection chứa đúng tất cả phần tử đã khai báo.
7. **Subtype có làm thay đổi chữ ký sau erasure không?** Hiểu bridge method và tránh overload trùng erasure.

Nguyên tắc tổng kết: **generics bảo vệ cấu trúc kiểu chủ yếu tại thời điểm biên dịch; JVM vẫn kiểm tra các class và phép cast có thể biểu diễn tại runtime, nhưng không thể tự xác thực toàn bộ type arguments đã bị erasure.** Khi dữ liệu đi qua ranh giới không đáng tin cậy, bổ sung kiểm tra runtime tại chỗ, thay vì kỳ vọng `List<String>` tự bảo vệ mọi phần tử.

## 16. Tài liệu tham khảo chính thức

- [Java SE 27 — JLS §4.6: Type Erasure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.6): định nghĩa erasure cho parameterized types, type variables, arrays và phương thức.
- [Java SE 27 — JLS §4.7: Reifiable Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.7): phân biệt kiểu có đầy đủ thông tin runtime và kiểu không reifiable.
- [Java SE 27 — JLS §4.8: Raw Types](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.8): ý nghĩa và giới hạn của raw types.
- [Java SE 27 — JLS §4.12.2: Variables of Reference Type](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.12.2): heap pollution và nguy cơ từ thao tác unchecked.
- [Java SE 27 — JLS §15.20.2: The instanceof Operator](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.20.2): các ràng buộc đối với kiểm tra kiểu.
- [Java SE 27 — JLS §10: Arrays](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-10.html): giới hạn generic array creation và runtime array store checks.
- [Java SE 27 — java.lang.Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html): `Class.cast` và kiểm tra kiểu bằng class token.
- [Java SE 27 — java.util.Collections.checkedList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)): wrapper có kiểm tra kiểu phần tử khi ghi.
