# asVarargsCollector() và asFixedArity(): kiểm soát hành vi varargs thay vì suy đoán như lời gọi Java thường

## 1. Bài toán: cùng một kiểu handle, hai cách gọi khác nhau

Trong Java, dấu `...` ở khai báo phương thức là cú pháp *varargs*. Ví dụ `void log(String... messages)` được biên dịch với tham số cuối có kiểu mảng `String[]`; trình biên dịch Java có thể gom các đối số riêng lẻ vào một mảng tại vị trí gọi.

Với `java.lang.invoke.MethodHandle`, cần thêm một khái niệm khác: **handle có chế độ nhận số lượng đối số biến thiên** (*variable-arity method handle*, hay *varargs collector*). Các API công khai còn được hỗ trợ trên JDK hiện đại giúp kiểm soát trực tiếp chế độ này:

- `asVarargsCollector(arrayType)`: tạo handle có khả năng thu gom các đối số cuối thành mảng khi được gọi theo đường hỗ trợ chuyển đổi số lượng đối số.
- `asFixedArity()`: lấy phiên bản handle có số tham số cố định; tham số cuối vẫn là mảng nhưng không tự gom các đối số rời.
- `isVarargsCollector()`: quan sát handle hiện có đang ở chế độ varargs collector hay không.
- `type()`: kiểm tra `MethodType` của handle, bao gồm tham số cuối là kiểu mảng.

Đây là nội dung **Lookup và adapter** của module `JAVA_VERSION_JAVA18`, nơi người học kiểm chứng hợp đồng `MethodHandle` thay vì suy luận từ cú pháp lời gọi Java thông thường. Java 18 có thay đổi nội bộ Core Reflection qua JEP 416, nhưng quy tắc về kiểu và khả năng thích ứng của MethodHandle trong bài vẫn cần dùng trên các JDK hiện đại.

**Điều cần nhớ trước tiên:** hai handle có thể cùng `type()` mà khác `isVarargsCollector()`, dẫn đến khả năng gọi bằng `invoke(...)` khác nhau. Phải kiểm tra **kiểu handle**, **chế độ variable arity** và **loại invocation** cùng lúc.

## 2. Tách ba khái niệm: mảng cuối, varargs collector và cách gọi

Xét phương thức Java:

```java
static String render(String prefix, String[] items) {
    return prefix + ":" + java.util.Arrays.toString(items);
}
```

Phương thức này **không khai báo `String...`**. Chữ ký JVM của nó vẫn có tham số cuối `String[]`:

```text
render(String, String[]) -> String
```

Sau khi lấy handle bằng `findStatic(...)`, kiểu handle là:

```text
(String, String[])String
```

Ở trạng thái fixed arity, để gọi handle cần một `String` và một **mảng `String[]`**. Chúng ta có thể chuyển handle đó thành varargs collector mà không sửa mã của `render`:

```java
MethodHandle variable = fixed.asVarargsCollector(String[].class);
```

Đối với handle này, một lời gọi thích hợp bằng `invoke(...)` có thể truyền:

```java
(String) variable.invoke("P", "a", "b"); // gom "a", "b" vào String[]
```

Điểm khác biệt:

| Khái niệm | Câu hỏi giải đáp | Giá trị trong ví dụ |
|---|---|---|
| Tham số cuối là mảng | Handle đích nhận kiểu gì? | `String[]` |
| `isVarargsCollector()` | Handle có chấp nhận mở rộng số đối số bằng bộ gom mảng không? | `true` sau `asVarargsCollector(...)` |
| `invoke(...)` | Có được thích ứng kiểu và số đối số theo hợp đồng handle không? | Có thể gom phần dư thành mảng với variable-arity handle |
| `invokeExact(...)` | Chữ ký tại điểm gọi có trùng **chính xác** `type()` không? | Phải truyền một `String[]` thực sự, không tự gom hai `String` |
| `asFixedArity()` | Có bỏ khả năng thu gom varargs không? | Có; kiểu vẫn có tham số cuối `String[]` |

Vì vậy **có tham số cuối là mảng không đồng nghĩa handle tự nhận các đối số rời**. Và **handle có khả năng varargs cũng không khiến `invokeExact()` tự thu gom đối số**.

## 3. Ví dụ đầy đủ: chủ động bật và tắt chế độ varargs

Lưu ví dụ sau thành `VarargsHandleDemo.java`. Mã sử dụng API `java.lang.invoke` và `java.util.Arrays` có sẵn trên các JDK hiện đại.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public final class VarargsHandleDemo {
    // Cố ý khai báo String[], không khai báo String...
    public static String render(String prefix, String[] items) {
        return prefix + ":" + Arrays.toString(items);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType signature = MethodType.methodType(
                String.class, String.class, String[].class);

        MethodHandle fixed = lookup.findStatic(
                VarargsHandleDemo.class, "render", signature);

        // Tạo phiên bản hỗ trợ thu gom các đối số cuối.
        MethodHandle variable = fixed.asVarargsCollector(String[].class);

        // Đổi lại chế độ fixed arity.
        MethodHandle fixedAgain = variable.asFixedArity();

        System.out.println(fixed.type());               // (String,String[])String
        System.out.println(variable.type());            // (String,String[])String
        System.out.println(fixedAgain.type());          // (String,String[])String

        System.out.println(fixed.isVarargsCollector());        // false
        System.out.println(variable.isVarargsCollector());     // true
        System.out.println(fixedAgain.isVarargsCollector());   // false

        System.out.println(fixed.type().equals(variable.type())); // true

        String[] values = {"x", "y"};

        // Fixed arity: truyền đúng mảng String[].
        String a = (String) fixed.invokeExact("P", values);
        System.out.println(a); // P:[x, y]

        // Variable arity + invoke: thu gom hai String riêng lẻ.
        String b = (String) variable.invoke("P", "a", "b");
        System.out.println(b); // P:[a, b]

        // Không có đối số sau prefix: thu gom thành String[] rỗng.
        String c = (String) variable.invoke("P");
        System.out.println(c); // P:[]

        // Khi điểm gọi truyền String[] đúng kiểu, dùng mảng sẵn có.
        String d = (String) variable.invokeExact("P", values);
        System.out.println(d); // P:[x, y]

        // Sau asFixedArity(), vẫn có thể dùng chính mảng String[].
        String e = (String) fixedAgain.invokeExact("P", values);
        System.out.println(e); // P:[x, y]
    }
}
```

Các giá trị kỳ vọng thể hiện hai thuộc tính độc lập:

- `fixed.type()`, `variable.type()` và `fixedAgain.type()` đều là `(String,String[])String`.
- Chỉ `variable.isVarargsCollector()` trả `true`, cho phép đường `invoke(...)` thích ứng từ `(String,String,String)String` hoặc `(String)String` sang tham số mảng cuối.

`asVarargsCollector(...)` tạo một **handle thích ứng**, không thay đổi định nghĩa của phương thức Java gốc. `asFixedArity()` cũng không chuyển tham số `String[]` thành nhiều tham số `String`; nó chỉ bỏ khả năng gom động của handle có variable arity.

## 4. Tại sao `invokeExact()` không tự gom các đối số?

`MethodHandle.invokeExact(...)` là một phương thức *signature-polymorphic*. Trình biên dịch phát ra chữ ký của điểm gọi từ **kiểu tĩnh** của các đối số và **kiểu kết quả được biểu thức yêu cầu**. Khi chạy, chữ ký đó phải khớp chính xác với `MethodHandle.type()`.

Với handle `variable` của ví dụ, `type()` vẫn là:

```text
(String, String[])String
```

Dòng sau là hợp lệ vì truyền đúng một `String[]`:

```java
String[] values = {"a", "b"};
String ok = (String) variable.invokeExact("P", values);
```

Dòng sau **không hợp lệ khi chạy**, dù handle đang có `isVarargsCollector() == true`:

```java
// Điểm gọi yêu cầu (String,String,String)String,
// không khớp với (String,String[])String.
String bad = (String) variable.invokeExact("P", "a", "b");
```

Kết quả là `WrongMethodTypeException`. `invokeExact` không thực hiện việc thu gom phần dư thành mảng. Cờ variable arity có ý nghĩa đối với các đường gọi hỗ trợ thích ứng, điển hình là `invoke(...)`.

### Một ví dụ lỗi có thể kiểm tra bằng mã

Đặt đoạn mã sau bên trong `main` sau khi đã tạo `variable`:

```java
try {
    String unused = (String) variable.invokeExact("P", "a", "b");
    System.out.println(unused);
} catch (java.lang.invoke.WrongMethodTypeException expected) {
    System.out.println("invokeExact: wrong method type");
}
```

Phép gọi `invokeExact(...)` thất bại **trước khi chạy `render(...)`** vì chữ ký điểm gọi không tương thích. Muốn truyền hai phần tử rời, dùng:

```java
String result = (String) variable.invoke("P", "a", "b");
```

Hoặc chuẩn bị mảng rõ ràng và giữ `invokeExact(...)`:

```java
String result = (String) variable.invokeExact(
        "P", new String[] {"a", "b"});
```

Khi viết framework, đây là lý do không nên suy luận rằng cách gọi gần giống `render("P", "a", "b")` trong Java thông thường sẽ luôn hoạt động với `invokeExact`. Hành vi được quyết định bởi **`MethodType` và cơ chế invocation**.

## 5. `asFixedArity()` loại bỏ điều gì, giữ lại điều gì?

`asFixedArity()` trả một handle tương ứng nhưng không có khả năng variable-arity collection. Nó giữ ngữ nghĩa thực thi của mục tiêu và giữ kiểu mảng cuối trong ví dụ. Có thể dùng khi framework cần bảo đảm **số tham số tại điểm gọi cố định**, vì bên gọi đã chuẩn bị đầy đủ đối số (bao gồm mảng cuối).

```java
MethodHandle fixedAgain = variable.asFixedArity();

String[] items = {"one", "two"};

String ok = (String) fixedAgain.invokeExact("P", items);
// P:[one, two]
```

Nhưng gọi fixed handle với ba `String` riêng lẻ sẽ không được biến đổi thành `String[]`:

```java
try {
    String invalid = (String) fixedAgain.invoke("P", "one", "two");
    System.out.println(invalid);
} catch (java.lang.invoke.WrongMethodTypeException expected) {
    System.out.println("fixed arity: no collection");
}
```

**So sánh kết quả:**

| Cách gọi | `variable` | `fixedAgain` |
|---|---|---|
| `invokeExact("P", String[])` với kết quả cast `String` | Thành công | Thành công |
| `invoke("P", "a", "b")` | Gom thành `String[]` rồi gọi | Không tự gom; không khớp chữ ký |
| `invoke("P")` | Gom thành mảng rỗng | Thiếu đối số mảng |
| `type()` | `(String,String[])String` | `(String,String[])String` |
| `isVarargsCollector()` | `true` | `false` |

Một lời gọi `invoke(...)` thông thường vẫn có những phép chuyển đổi kiểu `asType(...)` cho phép; `asFixedArity()` không có nghĩa mọi chuyển đổi bị cấm. Nó chỉ không hỗ trợ **tự động thay đổi số lượng đối số bằng cách thu gom varargs**. Khi cần kiểu khớp tuyệt đối, sử dụng `invokeExact(...)` và kiểm tra `type()`.

## 6. Đối số cuối đã là mảng: không tự suy đoán việc đóng gói

Trường hợp dễ nhầm nhất là caller **đã có `String[]`**, nhưng lại cho rằng variable-arity handle chắc chắn sẽ coi cả mảng như **một phần tử** hoặc chắc chắn bung mảng ra thành nhiều phần tử.

Đúng hơn, cần xét **chữ ký tại điểm gọi** và kiểu mảng cuối được yêu cầu.

```java
String[] values = {"x", "y"};

// Điểm gọi (String,String[])String: mảng được dùng trực tiếp.
String directArray =
        (String) variable.invokeExact("P", values);
```

Với `invoke(...)`, khi điểm gọi có kiểu phù hợp với tham số mảng cuối, có thể truyền trực tiếp mảng thay vì thu gom các phần tử:

```java
String directArray =
        (String) variable.invoke("P", values);
```

Trong tình huống này, `render(...)` nhận một `String[]` có hai phần tử `x` và `y`. Ngược lại:

```java
String collected =
        (String) variable.invoke("P", "x", "y");
```

đòi hỏi bộ gom tạo một mảng tham số cuối từ hai chuỗi riêng lẻ.

### Lưu ý khi dùng `invokeWithArguments(...)`

`invokeWithArguments(...)` nhận các giá trị qua danh sách hoặc varargs `Object...` và dùng cơ chế thích ứng tổng quát hơn `invokeExact(...)`. Cú pháp Java ở nơi gọi `invokeWithArguments(Object...)` có thể tự xử lý mảng theo quy tắc varargs của **chính phương thức này**, làm mã khó đọc nếu truyền trực tiếp một mảng tham chiếu.

Khi dữ liệu đã ở trong một mảng hoặc danh sách động, hãy xác định rõ đó là **danh sách các đối số của handle** hay **một đối số duy nhất có kiểu mảng**. Dùng biến trung gian đúng kiểu hoặc overload nhận `List<?>` khi phù hợp, kiểm chứng kết quả trên JDK đang dùng và tránh suy đoán theo cú pháp dấu `...`. Đặc biệt, `invokeWithArguments` không phải công cụ thay thế tương đương cho mọi đường gọi `invokeExact` trong hot path: cách chuyển kiểu, phân bổ đối tượng và hiệu năng có thể khác.

## 7. Khác biệt với `asCollector(arrayType, arrayLength)`

`asVarargsCollector(...)` hỗ trợ **nhiều số lượng đối số** tại những lời gọi thích ứng. Ngược lại, `asCollector(arrayType, arrayLength)` tạo một handle có **số tham số cuối được xác định khi tạo adapter**.

Ví dụ từ cùng `fixed`:

```java
MethodHandle exactlyTwo = fixed.asCollector(String[].class, 2);

System.out.println(exactlyTwo.type());
// (String,String,String)String

System.out.println(exactlyTwo.isVarargsCollector());
// false

String result = (String) exactlyTwo.invokeExact("P", "a", "b");
System.out.println(result);
// P:[a, b]
```

Cách hoạt động:

```text
fixed:        (String, String[])String
                   |
                   | asCollector(String[].class, 2)
                   v
exactlyTwo:   (String, String, String)String
                   |
                   | invokeExact("P", "a", "b")
                   v
             render("P", new String[] {"a", "b"})
```

So sánh:

| API | Khi nào xác định số phần tử cần gom? | Kiểu của handle trả về | Tự nhận số đối số biến thiên khi gọi `invoke`? |
|---|---|---|---|
| `asVarargsCollector(String[].class)` | Theo điểm gọi thích ứng | Trong ví dụ vẫn là `(String,String[])String` | Có |
| `asCollector(String[].class, 2)` | Ngay lúc tạo adapter: `2` phần tử | `(String,String,String)String` | Không; handle này có arity cố định |
| `asFixedArity()` | Không tạo collector mới | Giữ kiểu của handle hiện tại | Không |

Có thể dùng `asSpreader(...)` để tạo adapter ở chiều ngược: nhận một mảng và phân rã nó thành số đối số đã định sẵn cho handle đích. Với `exactlyTwo`:

```java
MethodHandle acceptsArray =
        exactlyTwo.asSpreader(String[].class, 2);

System.out.println(acceptsArray.type());
// (String,String[])String

String[] values = {"x", "y"};
String text = (String) acceptsArray.invokeExact("P", values);
System.out.println(text); // P:[x, y]
```

`asCollector` và `asSpreader` là những adapter hữu ích cho framework có chữ ký cố định. Chúng **khác về ý nghĩa** với chế độ varargs collector, ngay cả khi cùng mục tiêu cuối là chuyển giữa mảng và các phần tử riêng lẻ.

## 8. Phương thức Java khai báo `String...` và handle nhận được từ Lookup

Đến đây, ví dụ cố ý khai báo `String[]` để bắt đầu với handle fixed arity. Còn nếu phương thức đích khai báo varargs ở **mã Java gốc** thì sao?

```java
public static String declaredVarargs(String prefix, String... items) {
    return prefix + ":" + java.util.Arrays.toString(items);
}
```

Ở mức bytecode và `MethodType`, tham số cuối vẫn là `String[]`. Tuy nhiên, metadata của phương thức có cờ varargs. Khi lấy handle bằng `Lookup.findStatic(...)` cho một phương thức được khai báo là varargs, handle trả về có thể dùng trực tiếp ở chế độ variable arity theo hợp đồng Lookup:

```java
MethodHandle fromVarargsDeclaration =
        MethodHandles.lookup().findStatic(
                VarargsHandleDemo.class,
                "declaredVarargs",
                MethodType.methodType(
                        String.class, String.class, String[].class));

System.out.println(fromVarargsDeclaration.type());
// (String,String[])String

System.out.println(fromVarargsDeclaration.isVarargsCollector());
// true
```

Đoạn mã giả định phương thức `declaredVarargs` được thêm vào chính lớp `VarargsHandleDemo`. Các API tìm hoặc chuyển từ metadata reflection, chẳng hạn `unreflect(...)`, cũng cần được kiểm chứng cờ variable arity theo hợp đồng của thành viên đích. Vì thế:

- Không suy ra trạng thái varargs chỉ từ việc nhìn thấy tham số cuối là `String[]`.
- Kiểm tra `isVarargsCollector()` trên **handle thực tế**.
- Khi giao diện framework yêu cầu arity cố định, dùng `asFixedArity()` một cách tường minh.
- Khi muốn nhận danh sách phần tử riêng lẻ và handle chưa phải varargs collector, dùng `asVarargsCollector(...)` với kiểu mảng cuối hợp lệ.

### Không nhầm với overload resolution của Java

Khi viết `declaredVarargs("P", "a", "b")` bằng lời gọi Java thông thường, **trình biên dịch** biết danh sách overload và có thể dùng quy tắc varargs của ngôn ngữ Java để chọn lời gọi.

Khi dùng `MethodHandle`, handle đã xác định **một phương thức đích** ở bước tra cứu. `asVarargsCollector(...)` chỉ thay đổi cách biến đối số tại điểm gọi thành tham số mảng cuối; nó **không tìm lại overload khác** dựa trên số lượng hoặc kiểu đối số mới. Nếu cần target khác, phải có handle trỏ tới target đó.

## 9. Điều kiện áp dụng và các nhóm lỗi

`asVarargsCollector(arrayType)` chỉ áp dụng được khi cấu trúc kiểu của handle cho phép dùng kiểu mảng được chỉ định ở tham số cuối. Trong ví dụ, handle có tham số cuối `String[]` và dùng `String[].class` nên điều kiện phù hợp.

Không thể coi mọi handle đều có thể đổi thành varargs collector tùy ý:

```java
MethodHandle twice = MethodHandles.lookup().findStatic(
        MathOps.class,
        "twice",
        MethodType.methodType(int.class, int.class));

// Không hợp lệ nếu muốn dùng int[] để gom nhưng target
// không có tham số cuối thích hợp làm nơi nhận mảng.
// twice.asVarargsCollector(int[].class);
```

Đoạn này chỉ minh họa điều kiện kiểu; lớp `MathOps` giả định có phương thức static tương ứng. Trong chương trình thực tế, khi yêu cầu không đáp ứng điều kiện của `asVarargsCollector`, thao tác tạo adapter có thể ném `IllegalArgumentException`.

### Phân loại lỗi theo giai đoạn

| Giai đoạn | Vấn đề | Triệu chứng thường gặp |
|---|---|---|
| Tìm handle | Sai tên, sai kiểu tham số hoặc thiếu quyền | `NoSuchMethodException`, `IllegalAccessException` |
| Tạo varargs collector | Kiểu mảng yêu cầu không hợp lệ hoặc không tương thích với tham số cuối | `IllegalArgumentException` |
| Tạo collector có số phần tử cố định | `arrayLength` không hợp lệ hoặc kiểu không thích hợp | `IllegalArgumentException` |
| Gọi `invokeExact` | Số/kiểu tham số hoặc kiểu kết quả tại điểm gọi không trùng `type()` | `WrongMethodTypeException` |
| Gọi `invoke` trên fixed handle | Muốn tự gom nhiều đối số vào một mảng nhưng handle không có khả năng đó | Thường `WrongMethodTypeException` |
| Chuyển kiểu khi gọi/adapt | Giá trị không chuyển thành kiểu phần tử yêu cầu | Có thể `ClassCastException` hoặc ngoại lệ chuyển kiểu phù hợp |
| Chạy phương thức đích | Chính `render`/logic đích ném lỗi | Ngoại lệ từ target được truyền tới caller |

Với MethodHandle, `invokeExact(...)`/`invoke(...)` nhìn chung truyền ngoại lệ do phương thức đích ném **trực tiếp**, không tự bọc như `Method.invoke(...)` thường bọc trong `InvocationTargetException`. Cần phân biệt lỗi ở adapter với lỗi của nghiệp vụ đích.

**Không dùng `asFixedArity()` để bỏ qua kiểm tra quyền:** quyền tìm member được xác định khi tạo handle bằng `Lookup`, còn các adapter này chỉ điều chỉnh khả năng gọi. Chúng cũng không thay đổi lớp đích, trạng thái của đối tượng hay tính thread-safe của logic được gọi.

## 10. Tình huống ứng dụng: framework gọi plugin với mảng đối số

Giả sử một framework có API:

```java
interface TaskInvoker {
    String execute(String category, String[] arguments) throws Throwable;
}
```

Framework nhận một `MethodHandle` trỏ tới `(String,String[])String`. Nếu tầng gọi đã xây dựng mảng từ dữ liệu JSON hoặc giao thức RPC, nên giữ **arity cố định**:

```java
MethodHandle stable = incomingHandle.asFixedArity();

String[] arguments = {"--verbose", "--dry-run"};
String value = (String) stable.invokeExact("build", arguments);
```

Cách này giúp hợp đồng “category + một mảng arguments” dễ kiểm chứng, không phụ thuộc bên gọi vô tình truyền từng phần tử riêng lẻ hoặc nhầm giữa một giá trị và danh sách các giá trị. Nếu hệ thống cần API tiện dụng để gọi từ code có nhiều đối số rời, có thể cung cấp riêng một varargs collector:

```java
MethodHandle flexible =
        stable.asVarargsCollector(String[].class);

String value = (String) flexible.invoke(
        "build", "--verbose", "--dry-run");
```

Hai cách có thể gọi **cùng logic đích**, nhưng mang hợp đồng tham số khác nhau tại điểm gọi. Việc lựa chọn chế độ dựa trên hình dạng dữ liệu ở ranh giới API, không phải dựa trên kỳ vọng rằng varargs luôn nhanh hơn hoặc luôn dễ dùng hơn. Với code gọi thường xuyên, cần cache handle/adapter phù hợp và đo trên JDK đang vận hành; không suy luận con số hiệu năng từ tên phương thức.

## 11. Bộ kiểm chứng hợp đồng trên JDK hiện tại

Có thể xây dựng kiểm thử cho lớp `VarargsHandleDemo` từ phần 3 bằng những điều kiện quan sát được sau:

| Ca kiểm chứng | Thao tác | Kỳ vọng |
|---|---|---|
| Kiểu handle ban đầu | `fixed.type()` | `(String,String[])String` |
| Chế độ ban đầu | `fixed.isVarargsCollector()` | `false` do `render` khai báo `String[]` |
| Bật varargs collector | `fixed.asVarargsCollector(String[].class)` | `isVarargsCollector() == true` |
| Kiểu sau khi bật | So sánh `fixed.type()` và `variable.type()` | Bằng nhau trong ví dụ |
| Gọi 0 phần tử sau prefix | `(String) variable.invoke("P")` | `P:[]` |
| Gọi 2 phần tử rời | `(String) variable.invoke("P","a","b")` | `P:[a, b]` |
| Gọi với mảng | `(String) variable.invokeExact("P", values)` | Đọc đúng phần tử của mảng |
| Sai `invokeExact` | `(String) variable.invokeExact("P","a","b")` | `WrongMethodTypeException` |
| Tắt varargs collection | `variable.asFixedArity()` | `isVarargsCollector() == false` |
| Fixed nhận nhiều phần tử rời | `(String) fixedAgain.invoke("P","a","b")` | Không được gom, báo lỗi kiểu |
| Collector số phần tử cố định | `fixed.asCollector(String[].class, 2)` | `type() == (String,String,String)String` |
| Phương thức Java khai báo `String...` | Lookup tới `declaredVarargs` | Kiểm tra `isVarargsCollector() == true` |

Một vài assertion trực tiếp, giả định đã có `fixed`, `variable` và `fixedAgain`:

```java
if (fixed.isVarargsCollector()) {
    throw new AssertionError("fixed must not be varargs");
}
if (!variable.isVarargsCollector()) {
    throw new AssertionError("variable must collect varargs");
}
if (fixedAgain.isVarargsCollector()) {
    throw new AssertionError("asFixedArity must disable collection");
}
if (!variable.type().equals(fixed.type())) {
    throw new AssertionError("Unexpected method type");
}

String text = (String) variable.invoke("P", "a", "b");
if (!"P:[a, b]".equals(text)) {
    throw new AssertionError(text);
}
```

Khi chạy thử cần xử lý `Throwable` theo ngữ cảnh test. Nếu target đã qua nhiều adapter (`asType`, `bindTo`, `asCollector`), hãy in `handle.type()` và `isVarargsCollector()` **sau từng bước**. Đây là cách kiểm chứng rõ ràng hơn việc nhìn vào mã Java đích rồi suy đoán trạng thái của handle.

## 12. Câu hỏi tự kiểm tra

1. Hai handle đều có kiểu `(String,String[])String`. Tại sao một handle chấp nhận `invoke("P","a","b")` còn handle kia không?
2. Vì sao `variable.invokeExact("P","a","b")` vẫn có thể ném `WrongMethodTypeException` dù `variable.isVarargsCollector()` là `true`?
3. `asFixedArity()` có thay tham số cuối `String[]` thành `String` không? Nó thực sự bỏ khả năng gì?
4. `asCollector(String[].class, 2)` khác `asVarargsCollector(String[].class)` ở thời điểm quyết định số phần tử gom như thế nào?
5. Nếu phương thức Java khai báo `String...`, ta nên kiểm tra đặc tính nào của handle từ `findStatic` thay vì suy đoán theo chữ ký mảng?
6. Khi hệ thống đã có mảng đối số từ JSON, tại sao handle fixed arity thường tạo hợp đồng đầu vào dễ kiểm chứng hơn?

**Ghi nhớ:** `asVarargsCollector()` điều chỉnh khả năng **gom các đối số cuối khi gọi theo cơ chế thích ứng**; `asFixedArity()` đưa handle về **arity cố định**. Cả hai đều cần được hiểu cùng `handle.type()`, `isVarargsCollector()` và lựa chọn `invoke` hoặc `invokeExact`. Varargs của mã nguồn Java và variable-arity MethodHandle có liên quan nhưng **không thể đánh đồng**.
