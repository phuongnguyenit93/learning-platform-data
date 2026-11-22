# 10.4 Đọc `Method`, receiver proxy và `args`; xử lý lời gọi không đối số

## 1. Mục tiêu và bối cảnh

**Dynamic proxy** của JDK (`java.lang.reflect.Proxy`) cho phép tạo một đối tượng triển khai một hay nhiều **interface** tại runtime. Mỗi lời gọi method được chuyển đến `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`, giúp framework thực hiện logging, tracing, phân quyền, caching hoặc ủy quyền sang đối tượng thật.

Một chi tiết nhỏ nhưng rất quan trọng: khi method **không có tham số**, `args` trong `InvocationHandler` thông thường là **`null`**, **không phải** mảng rỗng `new Object[0]`. Đọc `args.length`, duyệt `args` hoặc chuyển tiếp `args` mà không hiểu hợp đồng này có thể tạo lỗi `NullPointerException` hoặc ghi nhận sai.

Bài học tập trung vào ba đầu vào của handler:

- **`proxy`:** receiver là **chính đối tượng proxy** mà người gọi đã gọi method trên đó, không phải đối tượng nghiệp vụ thật.
- **`method`:** metadata kiểu `java.lang.reflect.Method` mô tả **method được gọi qua interface hoặc một trong các method của `Object`**.
- **`args`:** `Object[]` chứa các **đối số thực tế** được cung cấp cho method, hoặc `null` nếu method không có tham số.

Bạn sẽ học cách kiểm tra đúng các trường hợp không đối số, đối số `null`, varargs, xử lý `equals/hashCode/toString`, tránh đệ quy vô hạn, chuyển tiếp lời gọi bằng Reflection và bảo toàn ngoại lệ của nghiệp vụ. Các ví dụ dùng Java 17+.

> **Quy tắc cốt lõi:** Hãy coi `proxy`, `Method` và `args` là ba thông tin khác nhau. `proxy` chỉ ra *đối tượng nhận lời gọi*, `Method` chỉ ra *chữ ký method được gọi*, còn `args` chỉ ra *giá trị đối số* — với ngoại lệ đặc biệt `args == null` khi số tham số bằng 0.

## 2. Cách một lời gọi đi qua dynamic proxy

Giả sử có interface:

```java
interface Greeting {
    String hello();
    String greet(String name);
}
```

Một đối tượng proxy triển khai `Greeting` có thể được tạo như sau:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

Đoạn trên là **trích đoạn**, giả định đã có biến `handler` kiểu `InvocationHandler` và import `java.lang.reflect.Proxy`. Với lời gọi:

```java
String result = proxy.greet("An");
```

Luồng xử lý về mặt ý tưởng:

```text
Caller
  |
  | proxy.greet("An")
  v
JDK-generated proxy class
  |
  | handler.invoke(proxy, Method[greet(String)], Object[]{"An"})
  v
InvocationHandler
  |
  | kiểm tra Method + args; chọn xử lý
  | có thể gọi delegate.greet("An")
  v
Giá trị trả về từ handler
  |
  v
Proxy trả kết quả cho caller
```

Các chi tiết quan trọng:

1. Mã nguồn caller vẫn gọi `proxy.greet(...)` bằng cú pháp interface thông thường. Caller không trực tiếp gọi `handler.invoke(...)`.
2. JDK-generated proxy class giữ một `InvocationHandler`, xây metadata `Method` phù hợp và gọi handler cho hầu hết các method interface và các method `Object` quy định.
3. `InvocationHandler.invoke` **không tự động gọi implementation thật**. Handler phải tự quyết định trả giá trị, chuyển tiếp tới delegate, hoặc ném exception.
4. Khi có delegate, `proxy` và `delegate` là **hai object khác nhau**. Việc gọi nhầm `method.invoke(proxy, args)` bên trong handler sẽ quay lại handler và có thể lặp vô hạn.
5. Proxy JDK thực hiện giao diện **interface**, không biến một class nghiệp vụ bất kỳ thành subclass proxy giống một số thư viện bytecode khác.

### 2.1. Hợp đồng `InvocationHandler.invoke`

Chữ ký theo JDK:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

Phần ý nghĩa:

| Tham số | Kiểu runtime | Ý nghĩa | Cạm bẫy |
| --- | --- | --- | --- |
| `proxy` | `Object` | Đối tượng proxy thực sự nhận lời gọi | Không phải delegate; đừng gọi `proxy.toString()` để log một cách vô điều kiện trong handler |
| `method` | `Method` | Metadata method được gửi đến handler | `getDeclaringClass()` có thể là interface hoặc `Object`, không nhất thiết là proxy class hay delegate class |
| `args` | `Object[]` hoặc `null` | Các đối số của method được gọi | `null` khi method không đối số; phần tử `null` khi caller truyền giá trị null là chuyện khác |
| Return | `Object` | Kết quả handler trả lại để proxy chuyển về caller | Primitive return cần wrapper hợp lệ; void return bị bỏ qua |
| `throws Throwable` | Ngoại lệ | Handler có thể báo lỗi | Checked exception không được interface khai báo có thể bị proxy bọc thành `UndeclaredThrowableException` |

`Method` là **đối tượng metadata**, không phải đối tượng nghiệp vụ. Khi proxy triển khai interface `Greeting`, `method.getDeclaringClass()` cho `greet` thường là interface `Greeting.class`. `method.getDeclaringClass()==proxy.getClass()` không phải điều kiện đúng để nhận diện lời gọi.

## 3. Đọc `Method`: tên, chữ ký, owner và flags

Các API `Method` rất hữu ích trong handler:

| API | Dùng để làm gì? | Ví dụ / lưu ý |
| --- | --- | --- |
| `getName()` | Tên Java của method | `"greet"`, `"toString"`, `"equals"` |
| `getDeclaringClass()` | Kiểu khai báo method hiện được chuyển tới handler | Interface hoặc `Object.class`; với nhiều interface, còn phụ thuộc thứ tự và signature |
| `getParameterCount()` | Số tham số **khai báo** của method | `hello()` → 0; `greet(String)` → 1; `join(String...)` → **1** |
| `getParameterTypes()` | Mảng `Class<?>[]` của tham số sau erasure | `join(String...)` có `String[].class` |
| `getGenericParameterTypes()` | Kiểu generic nếu metadata có thông tin | Có thể trả về `TypeVariable`/`ParameterizedType` |
| `getReturnType()` | Kiểu trả về `Class<?>` | `void.class`, `int.class`, `String.class` |
| `isVarArgs()` | Method khai báo varargs Java? | `join(String...)` → true; không đồng nghĩa `args` có chiều dài tùy ý |
| `isDefault()` | Có phải default method của interface? | Có thể xử lý bằng `InvocationHandler.invokeDefault` trên Java 17+ |
| `getModifiers()` | Modifier flags của method | Có ích khi ghi metadata, không thay thế kiểm tra method signature |

Ví dụ một handler có thể log mà **không gọi method nghiệp vụ**:

```java
// Trích đoạn bên trong InvocationHandler.invoke(...).
System.out.println("method=" + method.getName());
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("params=" + method.getParameterCount());
System.out.println("return=" + method.getReturnType().getSimpleName());
System.out.println("varargs=" + method.isVarArgs());
```

**Không nên dispatch nghiệp vụ chỉ bằng `method.getName()`** nếu interface có overload. `find(String)` và `find(long)` cùng tên nhưng khác tham số. Sử dụng cả `getParameterTypes()` hoặc đối chiếu đầy đủ `Method` khi cần chính xác.

### 3.1. Owner là interface, không phải implementation

Với:

```java
interface Service { String ping(); }
final class ServiceImpl implements Service {
    public String ping() { return "pong"; }
}
```

Khi gọi `proxy.ping()`, tham số `method` có thể là `Service.class.getMethod("ping")`. Nó được khai báo tại interface, dù sau đó handler chọn chuyển tiếp sang `ServiceImpl`. Một số framework cần metadata annotation ở **interface**, một số cần annotation ở **implementation**; phải có policy tìm kiếm rõ ràng, không mặc định chúng giống nhau.

Với interface kế thừa, declaring class có thể là interface cha. Với nhiều interface khai báo cùng một chữ ký, xem mục 10 về lựa chọn `Method`. Vì vậy đừng dùng `method.getDeclaringClass()` như định danh duy nhất của "method nguồn" mà không xét tập interface được proxy triển khai.

### 3.2. Primitive và void

Giả sử interface có:

```java
int size();
void touch();
```

Nếu handler gọi delegate bằng `Method.invoke`, kết quả `int` sẽ được boxing thành `Integer` trong `Object` trả về. Proxy sẽ unbox khi trả từ `size()` cho caller. Nếu handler trả `null` từ method khai báo kiểu primitive, có thể phát sinh `NullPointerException` khi proxy cố unbox. Nếu trả sai wrapper type, có thể phát sinh `ClassCastException`.

Với `void touch()`, handler có thể trả `null`; trong mô hình proxy, giá trị trả về của handler dành cho method void không được caller sử dụng. **Không** nên coi handler trả `null` là bằng chứng rằng lời gọi nghiệp vụ thất bại: method void có thể đã chạy thành công.

## 4. `proxy` là receiver proxy, không phải delegate

Giả sử:

```java
TaskService service = (TaskService) Proxy.newProxyInstance(
        TaskService.class.getClassLoader(),
        new Class<?>[]{TaskService.class},
        new LoggingHandler(realService));
```

Tại `LoggingHandler.invoke(proxy, method, args)`:

- `proxy == service` về danh tính object (nếu `service` chính là receiver được gọi).
- `Proxy.isProxyClass(proxy.getClass())` thường đúng cho JDK proxy class.
- `method.getDeclaringClass()` thường là `TaskService.class` cho method nghiệp vụ, hoặc `Object.class` cho các method `toString`/`equals`/`hashCode`.
- `realService` là **delegate** do handler lưu trữ, không phải tham số `proxy`.

Một sai lầm nguy hiểm:

```java
// SAI: nếu Method có thể invoke trên proxy, việc này thường quay lại handler.
return method.invoke(proxy, args);
```

Ví dụ `method` đại diện cho `TaskService.ping()`. Gọi `method.invoke(proxy,args)` sẽ kích hoạt `proxy.ping()` một lần nữa; proxy lại gọi `handler.invoke(...)`; handler lại `method.invoke(proxy,args)`... và có thể dẫn tới `StackOverflowError`. **Không được gọi receiver proxy là delegate.**

Cách chuyển tiếp đúng khi có implementation tương ứng:

```java
Object[] forwarded = args == null ? new Object[0] : args;
return method.invoke(realService, forwarded);
```

Đây là **trích đoạn**; `realService` phải thực thi interface hoặc tương thích với `Method` được gọi. Với method không đối số, truyền mảng rỗng tới `Method.invoke` là cách rõ ràng và ổn định. Không dùng `method.invoke(proxy,...)`.

### 4.1. Log receiver mà không vô tình gọi lại handler

Cách log này có thể tái nhập handler:

```java
// RỦI RO: nối chuỗi gọi proxy.toString()!
System.out.println("proxy=" + proxy);

// RỦI RO TƯƠNG TỰ: formatter có thể gọi equals/hashCode/toString
// của chính proxy nếu đưa nó vào một cấu trúc dữ liệu cần so sánh.
```

Vì `toString()` trên dynamic proxy cũng đi qua `InvocationHandler`, việc log `proxy` từ bên trong `invoke` có thể kích hoạt **một lời gọi lồng nhau**. Nếu tiếp tục log theo cách đó, có thể lặp mãi.

Muốn xem danh tính object mà không gọi `toString()` của proxy, có thể log:

```java
// Trích đoạn bên trong handler.
System.out.println("proxyClass=" + proxy.getClass().getName());
System.out.println("identity=" + System.identityHashCode(proxy));
```

`System.identityHashCode` sử dụng identity hash code và **không gọi `proxy.hashCode()`**. Tuy nhiên tên class proxy được JDK sinh không nên được hard-code làm identifier ổn định giữa các lần chạy; bài thực hành bên dưới chỉ in boolean `Proxy.isProxyClass(...)`, tránh phụ thuộc tên class được sinh.

Với `args` chứa chính proxy (chẳng hạn `proxy.equals(proxy)`), chỉ gọi `Arrays.deepToString(args)` cũng có thể gọi `toString` của proxy và tái nhập. Formatter trong ví dụ chính sẽ nhận biết `value == proxy` và in `<self>` thay vì gọi `toString`.

## 5. `args == null` khi method không đối số

Đây là điểm quan trọng nhất của đề bài.

Theo hợp đồng `InvocationHandler.invoke`, **`args` là `null` nếu method không có tham số**. Những lời gọi sau thường đi vào handler với `args == null`:

```java
service.ping();
service.size();
service.touch();
service.toString();
service.hashCode();
```

Những method đó có `method.getParameterCount() == 0`. Trong lúc xử lý, đừng dùng:

```java
// SAI: NullPointerException nếu args == null.
int length = args.length;

// SAI: enhanced for không duyệt được null.
for (Object value : args) {
    System.out.println(value);
}

// SAI: không phù hợp cho method không tham số.
Object first = args[0];
```

### 5.1. Quy tắc bảo vệ null an toàn

Nếu chỉ cần đếm số đối số thực tế:

```java
int argc = args == null ? 0 : args.length;
```

Nếu cần duyệt hoặc chuyển tiếp:

```java
Object[] effectiveArgs = args == null ? new Object[0] : args;
for (Object value : effectiveArgs) {
    // Xử lý từng đối số.
}
```

Nếu cần log phần tử, hãy giữ sự khác biệt giữa **handler nhận null** và **handler nhận mảng trống** khi debug:

```java
String label = args == null ? "<null>" : Arrays.deepToString(args);
```

`Arrays.deepToString(args)` trong ví dụ này là **trích đoạn** và chỉ thích hợp khi các giá trị không gây tác dụng phụ khi chuyển thành chuỗi; nếu args chứa proxy hoặc object có `toString` nguy hiểm, cần formatter cẩn thận hơn.

Đừng biến "`args == null`" thành khẳng định rằng **caller đã truyền một tham số null**. Phải dùng cả `method.getParameterCount()` và nội dung của `args` để phân biệt.

### 5.2. Ba trường hợp khác nhau: 0 tham số, 1 tham số null và mảng rỗng

| Lời gọi | `method.getParameterCount()` | `args` tại handler | Giải thích |
| --- | --- | --- | --- |
| `service.ping()` | 0 | `null` | Method không khai báo tham số |
| `service.echo(null)` | 1 | `new Object[]{null}` theo cấu trúc | Method có một tham số, giá trị của nó là null |
| `service.join()` với `join(String...)` | 1 | `new Object[]{new String[0]}` theo cấu trúc | Varargs vẫn là **một tham số array** trong chữ ký đã biên dịch |
| `service.join((String[]) null)` | 1 | `new Object[]{null}` theo cấu trúc | Tham số array đã được caller truyền **null** |
| `service.equals(null)` | 1 | `new Object[]{null}` theo cấu trúc | `equals(Object)` có một tham số, không phải method không đối số |

Các dạng `new Object[]{...}` trong bảng là **minh họa cấu trúc dữ liệu**, không phải cam kết JDK tạo chính xác object bằng cách gọi constructor mảng như trong cú pháp. Điều quan trọng là **độ dài và nội dung mảng**.

Nếu muốn nhận biết "không đối số" một cách độc lập với hiện tượng mảng ở handler, hãy dùng `method.getParameterCount() == 0`; nếu muốn tránh NPE khi xử lý dữ liệu thực tế, dùng `args == null` guard.

### 5.3. Đừng kiểm tra `args.length == 0` trước khi kiểm tra `args == null`

Câu điều kiện sau **vẫn có thể ném NPE**:

```java
// SAI vì vế đầu đã truy cập args.length.
if (args.length == 0 || args == null) {
    // ...
}
```

Viết theo short-circuit đúng:

```java
if (args == null || args.length == 0) {
    // An toàn khi truy cập mảng.
}
```

Tuy nhiên, với JDK dynamic proxy, **mảng null và mảng rỗng không phải hai trường hợp mà caller điều khiển bằng cùng một method**. Khi chỉ muốn xác định method khai báo không tham số, `method.getParameterCount() == 0` là tiêu chí ngữ nghĩa tốt hơn.

## 6. Chuyển tiếp lời gọi sang delegate một cách đúng đắn

Một proxy ghi log thường có nhiệm vụ:

1. Nhận `Method` và các đối số từ proxy.
2. Quyết định có xử lý method đặc biệt (`equals/hashCode/toString`) hay không.
3. Chuẩn hóa `args` để dùng an toàn.
4. Gọi method trên **đối tượng triển khai thật** nếu phù hợp.
5. Trả đúng kết quả, không làm mất ngoại lệ nghiệp vụ.

Cấu trúc thường thấy:

```java
@Override
public Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable {

    // Các method của Object có thể cần chính sách riêng.
    if (method.getDeclaringClass() == Object.class) {
        return handleObjectMethod(proxy, method, args);
    }

    Object[] safe = args == null ? new Object[0] : args;
    try {
        return method.invoke(delegate, safe);
    } catch (InvocationTargetException ex) {
        throw ex.getCause();
    }
}
```

Đây là **trích đoạn**, chưa phải chương trình chạy độc lập: `delegate` và `handleObjectMethod` phải được định nghĩa. Nó minh họa hai điểm quan trọng:

- `method.invoke(delegate, safe)` **chuyển tiếp thật** sang object phù hợp; không tạo vòng lặp qua proxy.
- Khi method của delegate ném exception, Reflection bọc exception đích trong `InvocationTargetException`. Tháo lớp bọc bằng `ex.getCause()` sẽ giữ nguyên exception nghiệp vụ.

### 6.1. `Method.invoke` cũng dùng varargs Java: phải hiểu kiểu của `safe`

`Method.invoke` có chữ ký:

```java
Object invoke(Object obj, Object... args)
```

Ở đây `safe` là một `Object[]`. Khi viết `method.invoke(delegate, safe)`, Java dùng cả mảng đó làm danh sách đối số cho Reflection, **không** coi nó là "một Object argument" bất kể method target khai báo gì.

Với `join(String...)`, mảng `safe` của handler chứa **một phần tử**, và phần tử này là `String[]`. Vì vậy `method.invoke(delegate,safe)` truyền **một array parameter** đúng như method đã khai báo. Nếu vô tình thay `safe` bằng mảng chuỗi `String[]` ở bên trong, hoặc làm phẳng các phần tử theo số lượng varargs, method invocation có thể sai chữ ký.

Một lối viết cũng hợp lệ nhưng nên dùng có chủ đích cho zero-arg:

```java
method.invoke(delegate, new Object[0]);
```

Không dùng `method.invoke(delegate, (Object) safe)` khi muốn truyền danh sách arguments; cast như vậy có thể khiến `safe` trở thành **một** đối số thay vì cả danh sách.

### 6.2. Vì sao phải unwrap `InvocationTargetException`?

Giả sử delegate có method:

```java
public String fail() {
    throw new IllegalStateException("delegate failed");
}
```

Khi gọi qua `Method.invoke(delegate, ...)`, Reflection sẽ ném `InvocationTargetException` chứa `IllegalStateException` bên trong. Nếu handler giữ nguyên wrapper rồi ném ra, proxy có thể báo ngoại lệ khác với kỳ vọng, thậm chí `UndeclaredThrowableException` nếu checked exception không được chữ ký interface cho phép.

Trong handler đã khai báo `throws Throwable`, thông thường chuyển tiếp bằng:

```java
try {
    return method.invoke(delegate, safeArgs);
} catch (InvocationTargetException ex) {
    throw ex.getCause(); // Giữ nguyên ngoại lệ do method đích ném.
}
```

Đừng bọc lại thành `RuntimeException` một cách tùy ý nếu hợp đồng nghiệp vụ cần phân biệt checked exception hoặc identity của exception. Đặt chính sách logging riêng nếu cần, rồi vẫn bảo toàn exception nguyên gốc khi đúng mục tiêu.

### 6.3. Checked exception và `UndeclaredThrowableException`

Phương thức interface proxy có thể khai báo:

```java
String load() throws java.io.IOException;
```

Nếu handler ném `IOException` trong lời gọi `load`, exception đó được interface cho phép. Nhưng nếu handler ném **checked exception** không được chữ ký của method cho phép, JDK proxy có thể bọc nó trong `java.lang.reflect.UndeclaredThrowableException`. Đây là đặc tính hợp đồng proxy, không phải lỗi của `args`.

Một handler tốt cần phân biệt:

- Exception **nghiệp vụ** do delegate ném, lấy từ `InvocationTargetException.getCause()`.
- Exception **lookup/reflection** như `IllegalAccessException` hoặc `IllegalArgumentException` khi method/receiver không phù hợp.
- Exception **do proxy wrapper** khi checked exception nằm ngoài khai báo.
- Lỗi do handler tự xử lý null, log tái nhập hoặc ép kiểu sai.

## 7. Xử lý `toString`, `hashCode` và `equals`

Ba method public, non-final của `java.lang.Object` **được JDK proxy định tuyến tới `InvocationHandler`** theo cơ chế proxy. Chúng có thể được gọi gián tiếp bởi logger, `Set`, `Map`, debugger hoặc công cụ giám sát, dù code nghiệp vụ không gọi rõ ràng.

| Method | `getDeclaringClass()` thông thường | Số tham số khai báo | `args` trong handler |
| --- | --- | --- | --- |
| `toString()` | `Object.class` | 0 | `null` |
| `hashCode()` | `Object.class` | 0 | `null` |
| `equals(Object other)` | `Object.class` | 1 | Một phần tử; có thể là null hoặc chính proxy |

Do đó không thể viết `if (args==null) return null;` cho mọi method không đối số. `toString` cần trả `String`; `hashCode` cần trả wrapper tương ứng `int`; method nghiệp vụ khác có thể cần gọi delegate để có dữ liệu.

### 7.1. Quy ước identity-based cho proxy

Một chính sách đơn giản và tự nhất quán:

```java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "TaskServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.toString());
    };
}
```

Giải thích:

- `toString` trả chuỗi mô tả **mà không gọi lại `proxy.toString()`**.
- `hashCode` dùng `System.identityHashCode(proxy)`, tránh tự gọi lại `proxy.hashCode()`.
- `equals` dùng `proxy == args[0]`, tránh tự gọi lại `proxy.equals(other)`. Một đối số `null` cho kết quả `false`.
- Giữ **tính nhất quán giữa equals và hashCode** ở mức identity. Không trộn `equals` theo delegate với `hashCode` theo proxy nếu điều đó phá hợp đồng.

Chính sách khác (ví dụ so sánh theo business identity của delegate) có thể phù hợp, nhưng phải **thiết kế và kiểm thử nhất quán**. Không tự mặc định việc ủy quyền cả ba method Object cho delegate là đúng với mọi hệ thống; hai proxy khác nhau có thể dùng chung delegate mà vẫn cần danh tính proxy khác nhau.

### 7.2. Đừng gọi `String.valueOf(proxy)` hoặc `Arrays.deepToString(args)` vô điều kiện

Nếu `args[0]` chính là proxy ở `equals(proxy)`, formatter có thể gọi `proxy.toString()`, phát sinh một chu trình invocation lồng nhau. Ngay cả khi nó không lặp vô hạn, log không còn chỉ gồm **một dòng cho mỗi lời gọi gốc**.

Cách an toàn để xử lý self-reference:

```java
// Trích đoạn đơn giản bên trong formatter.
if (argument == proxy) {
    out.append("<self>");
} else if (argument instanceof String[] array) {
    out.append(Arrays.toString(array));
} else {
    out.append(argument);
}
```

Đoạn này vẫn có thể kích hoạt `toString` với những đối tượng khác, vì vậy formatter chuyên dùng trong production có thể chỉ ghi **type/identity**, redact dữ liệu nhạy cảm hoặc cắt độ sâu. Ví dụ chạy hoàn chỉnh có thêm nhận diện **proxy khác** để hạn chế reentry.

## 8. Ví dụ Java 17+ hoàn chỉnh: đọc đúng `Method`/`proxy`/`args`

Tạo file **`ProxyInvocationDemo.java`** với **toàn bộ mã** dưới đây. Chương trình cố ý có:

- Method không đối số: `ping()`, `size()`, `touch()` và `fail()`.
- Method có một đối số bình thường hoặc `null`: `echo(String)`.
- Method varargs với 2, 0 hoặc mảng null: `join(String...)`.
- Lời gọi `Object`: `toString()`, `equals(Object)`, `hashCode()`.
- Trả về `String`, `int` và `void`.
- Delegate ném exception để kiểm tra xử lý `InvocationTargetException`.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class ProxyInvocationDemo {
    public interface TaskService {
        String ping();
        String echo(String text);
        String join(String... values);
        int size();
        void touch();
        String fail();
    }

    public static final class RealTaskService implements TaskService {
        private int touches;

        @Override public String ping() {
            return "pong";
        }

        @Override public String echo(String text) {
            return text == null ? "<null>" : "echo:" + text;
        }

        @Override public String join(String... values) {
            return values == null ? "<null-array>" : String.join("|", values);
        }

        @Override public int size() {
            return 7;
        }

        @Override public void touch() {
            touches++;
        }

        @Override public String fail() {
            throw new IllegalStateException("delegate failed");
        }
    }

    public static final class LoggingHandler implements InvocationHandler {
        private final TaskService target;

        public LoggingHandler(TaskService target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            System.out.println("call " + method.getName()
                    + " owner=" + method.getDeclaringClass().getSimpleName()
                    + " argc=" + (args == null ? 0 : args.length)
                    + " args=" + describe(proxy, args)
                    + " varargs=" + method.isVarArgs()
                    + " proxy=" + Proxy.isProxyClass(proxy.getClass()));

            // Object methods có chính sách identity riêng.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "TaskServiceProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            // Zero-arg method có args=null, nên chuẩn hóa trước khi ủy quyền.
            Object[] safeArgs = args == null ? new Object[0] : args;
            try {
                return method.invoke(target, safeArgs);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }

        private static String describe(Object proxy, Object[] args) {
            if (args == null) return "<null>";

            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < args.length; i++) {
                if (i > 0) sb.append(", ");
                Object value = args[i];

                if (value == proxy) {
                    sb.append("<self>");
                } else if (value instanceof String[] a) {
                    sb.append(Arrays.toString(a));
                } else if (value != null
                        && Proxy.isProxyClass(value.getClass())) {
                    sb.append("<other-proxy>");
                } else {
                    sb.append(value);
                }
            }
            return sb.append("]").toString();
        }
    }

    public static void main(String[] args) {
        RealTaskService real = new RealTaskService();
        TaskService service = (TaskService) Proxy.newProxyInstance(
                TaskService.class.getClassLoader(),
                new Class<?>[]{TaskService.class},
                new LoggingHandler(real));

        System.out.println("ping=" + service.ping());
        System.out.println("echo=" + service.echo("Java"));
        System.out.println("echo null=" + service.echo(null));
        System.out.println("join many=" + service.join("a", "b"));
        System.out.println("join zero=" + service.join());
        System.out.println("join null-array="
                + service.join((String[]) null));
        System.out.println("size=" + service.size());

        service.touch();
        System.out.println("touches=" + real.touches);

        System.out.println("toString=" + service.toString());
        System.out.println("equals self=" + service.equals(service));
        System.out.println("equals null=" + service.equals(null));
        System.out.println("hash identity="
                + (service.hashCode() == System.identityHashCode(service)));

        try {
            service.fail();
        } catch (IllegalStateException ex) {
            System.out.println("fail=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }
}
```

Chạy tại thư mục chứa file, với JDK 17 trở lên:

```bash
javac ProxyInvocationDemo.java
java ProxyInvocationDemo
```

**Stdout chính xác đã được kiểm tra bằng biên dịch và chạy chương trình trên JDK:**

```text
call ping owner=TaskService argc=0 args=<null> varargs=false proxy=true
ping=pong
call echo owner=TaskService argc=1 args=[Java] varargs=false proxy=true
echo=echo:Java
call echo owner=TaskService argc=1 args=[null] varargs=false proxy=true
echo null=<null>
call join owner=TaskService argc=1 args=[[a, b]] varargs=true proxy=true
join many=a|b
call join owner=TaskService argc=1 args=[[]] varargs=true proxy=true
join zero=
call join owner=TaskService argc=1 args=[null] varargs=true proxy=true
join null-array=<null-array>
call size owner=TaskService argc=0 args=<null> varargs=false proxy=true
size=7
call touch owner=TaskService argc=0 args=<null> varargs=false proxy=true
touches=1
call toString owner=Object argc=0 args=<null> varargs=false proxy=true
toString=TaskServiceProxy
call equals owner=Object argc=1 args=[<self>] varargs=false proxy=true
equals self=true
call equals owner=Object argc=1 args=[null] varargs=false proxy=true
equals null=false
call hashCode owner=Object argc=0 args=<null> varargs=false proxy=true
hash identity=true
call fail owner=TaskService argc=0 args=<null> varargs=false proxy=true
fail=IllegalStateException:delegate failed
```

### 8.1. Phân tích các dòng quan trọng

- **`ping()`:** `argc=0 args=<null>`. Handler không được dùng `args.length` trực tiếp. `safeArgs` thành mảng rỗng khi gọi `method.invoke(target,safeArgs)` và trả `pong`.
- **`echo("Java")`:** `argc=1 args=[Java]`. `Method` chỉ rõ kiểu tham số là `String`; handler nhận mảng một phần tử.
- **`echo(null)`:** `argc=1 args=[null]`, **khác** với `args=<null>` của method không đối số. Chỉ có phần tử đầu mang giá trị null.
- **`join("a","b")`:** `method.isVarArgs()==true` nhưng `argc=1`. Đó là một `String[]` chứa hai phần tử, được formatter biểu diễn là `[[a, b]]`.
- **`join()`:** vẫn `argc=1`, phần tử đầu là `String[0]`; output `args=[[]]`. Đây không phải lời gọi method có 0 tham số về mặt chữ ký.
- **`join((String[])null)`:** vẫn `argc=1` nhưng phần tử duy nhất là array null, output `args=[null]`. Delegate có logic xử lý nên trả `<null-array>`.
- **`size()`:** handler nhận `args=null`, nhưng gọi delegate trả primitive `int`; Reflection boxing thành `Integer` rồi proxy unbox về `int` cho caller.
- **`touch()`:** handler gọi method void; delegate tăng bộ đếm. Kết quả handler nhận từ `Method.invoke` là null nhưng bên ngoài vẫn thấy `touches=1`.
- **`toString/hashCode`:** method thuộc `Object`, không có đối số; handler trả theo chính sách identity và không tự gọi `proxy.toString()/hashCode()`.
- **`equals(service)`:** array một phần tử chứa **chính proxy**. Formatter nhận diện self-reference, in `<self>` để tránh kích hoạt `toString` lồng nhau.
- **`fail()`:** delegate ném `IllegalStateException`, Reflection bọc nó; handler unwrap nên caller thấy chính `IllegalStateException` với message nguyên gốc.

### 8.2. Vì sao log ghi cả `owner` lẫn `proxy=true`?

`owner=TaskService` mô tả nơi khai báo `Method` được handler nhận. `proxy=true` dùng `Proxy.isProxyClass(proxy.getClass())` xác nhận receiver thuộc JDK-generated proxy class. Hai thông tin có thể cùng đúng vì **receiver runtime** và **declaring class của method** là hai khái niệm khác nhau.

### 8.3. Vì sao cần biến `target` riêng?

`target` trỏ tới `RealTaskService`, là object chứa logic nghiệp vụ. Handler chỉ gọi `method.invoke(target,safeArgs)`; điều này bảo đảm lời gọi đi đến implementation thật thay vì quay lại receiver proxy.

Trong ứng dụng có nhiều interface hoặc routing phức tạp, một `Method` có thể không phù hợp với mọi delegate: phải chọn một delegate implements đúng declaring interface (hoặc method có thể gọi trên nó) trước khi chuyển tiếp. Nếu không, `Method.invoke` có thể ném `IllegalArgumentException` do receiver không phù hợp.

## 9. Phân biệt varargs với method không đối số

Đây là nguồn lỗi đặc biệt phổ biến khi xem `Object[] args`.

Với method:

```java
String join(String... values);
```

Java biên dịch thành method có **một tham số `String[]`**, đánh dấu method là varargs. Khi caller viết:

```java
service.join();
service.join("x");
service.join("x", "y");
service.join((String[]) null);
```

handler vẫn nhận `method.getParameterCount()==1`, `method.isVarArgs()==true` và thường `args.length==1`. Phần tử `args[0]` là mảng `String[]` với 0, 1, 2 phần tử hoặc null tương ứng.

Một cách diễn giải:

```text
join()                    -> args = [String[0]]
join("x")                 -> args = [String[1]{"x"}]
join("x", "y")            -> args = [String[2]{"x","y"}]
join((String[]) null)     -> args = [null]
ping()                    -> args = null
echo(null)                -> args = [null]
```

**Chú ý:** Dạng trên chỉ mô tả cấu trúc, không phải output của `Arrays.toString`; output thật của chương trình đã nằm ở mục 8.

Nếu một framework muốn đo **số phần tử varargs**, phải kiểm tra `method.isVarArgs()`, xác định array cuối và xử lý giá trị `args[args.length-1]` theo kiểu array. **Không thể dùng `args.length` làm số phần tử varargs**.

Ví dụ trích đoạn dành riêng cho `String...`:

```java
if (method.isVarArgs() && args != null && args.length > 0) {
    Object last = args[args.length - 1];
    if (last instanceof String[] strings) {
        System.out.println("vararg elements=" + strings.length);
    } else if (last == null) {
        System.out.println("vararg array is null");
    }
}
```

Đoạn này **không bao quát mọi loại varargs**: `int...` dùng `int[]`, `Object...` dùng `Object[]`, generic varargs có thể erasure thành kiểu array khác. Đối với framework tổng quát, dùng `method.getParameterTypes()` để xác định **kiểu array cuối**, rồi cân nhắc `java.lang.reflect.Array.getLength(...)`/`Array.get(...)` sau khi kiểm tra null.

### 9.1. Vị trí null khi truyền một đối số có thể gây nhập nhằng

Nếu method nhận `String...` và caller viết `join(null)`, compiler có thể cảnh báo vì lời gọi phù hợp với cách hiểu **null array** hoặc **một phần tử null**. Viết rõ:

```java
join((String[]) null); // Truyền chính array tham số là null.
join((String) null);   // Truyền một phần tử String có giá trị null.
```

Hai lời gọi tạo cấu trúc `args` khác nhau. Trong ví dụ `TaskService`, `join((String[])null)` được xử lý an toàn; còn `join((String)null)` sẽ tạo mảng chứa một null, và `String.join` trong implementation có hành vi riêng (không nên tự suy diễn output mà chưa kiểm thử).

## 10. Default methods, overload và nhiều interface

### 10.1. Default method không tự động chạy chỉ vì có implementation trong interface

Khi proxy implement interface có **default method**, lời gọi vẫn đi qua `InvocationHandler.invoke`. Nếu handler muốn thực thi chính implementation default trên proxy, Java 17+ cung cấp API:

```java
InvocationHandler.invokeDefault(proxy, method, args);
```

Cần `method.isDefault()==true` và method thuộc interface thích hợp. Tránh gọi `method.invoke(proxy,args)` với mục đích chạy default body, vì nó có thể gọi lại handler.

Ví dụ **chạy độc lập** lưu thành **`ProxyDefaultDemo.java`**:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyDefaultDemo {
    public interface Greeting {
        default String hello() {
            return "hello-default";
        }
    }

    public static void main(String[] args) {
        Greeting greeting = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[]{Greeting.class},
                (proxy, method, arguments) -> {
                    System.out.println("isDefault=" + method.isDefault()
                            + " argc=" + (arguments == null
                                    ? 0 : arguments.length));

                    if (method.isDefault()) {
                        return InvocationHandler.invokeDefault(
                                proxy, method,
                                arguments == null
                                        ? new Object[0] : arguments);
                    }

                    throw new UnsupportedOperationException(
                            method.toString());
                });

        System.out.println("result=" + greeting.hello());
    }
}
```

Lệnh chạy:

```bash
javac ProxyDefaultDemo.java
java ProxyDefaultDemo
```

Stdout chính xác:

```text
isDefault=true argc=0
result=hello-default
```

Bài học từ ví dụ: default method `hello()` vẫn có `arguments==null` vì không có tham số. `invokeDefault` dùng mảng rỗng khi chuyển tiếp. Đây là lựa chọn **có chủ đích** để chạy implementation mặc định của interface; không cần dùng nếu handler đã có delegate thực thi method phù hợp.

### 10.2. Nhiều interface có cùng chữ ký

`Proxy.newProxyInstance` có thể nhận nhiều interface. Nếu các interface có các method trùng tên và danh sách tham số, proxy không thể phân biệt ý định chỉ nhờ việc caller cast receiver sang interface nào tại từng lời gọi. Theo hợp đồng `Proxy`, method được gửi tới handler có thể được chọn dựa trên **thứ tự các interface** trong danh sách proxy, thay vì luôn đúng với interface xuất hiện trong kiểu tĩnh của caller.

Vì thế:

- Không mặc định `method.getDeclaringClass()` luôn chính là interface mà code caller đã cast sang.
- Khi thiết kế dispatch dựa trên `Method`, phải xét các trùng lặp chữ ký và thứ tự interface của proxy.
- Các phương thức `equals`, `hashCode`, `toString` có quy tắc riêng và thường được trình bày với declaring class `Object.class`.
- Nếu các interface có method với cùng name+parameter types nhưng return types không tương thích, quá trình tạo proxy có thể thất bại.

Với trường hợp nhiều interface phức tạp, tốt nhất xây dựng một **bảng định tuyến nhất quán** từ signature hợp lệ đến hành vi mong muốn, thay vì suy diễn từ runtime receiver của từng lời gọi.

### 10.3. Overload khác nhau cần phân biệt đầy đủ

Ví dụ:

```java
interface Resolver {
    String resolve(String name);
    String resolve(long id);
}
```

Cả hai method có `getName()=="resolve"` nhưng `getParameterTypes()` khác. Nếu handler dùng switch chỉ theo name, nó có thể gửi sai đối số đến một delegate. Có thể nhận diện bằng full parameter list:

```java
// Trích đoạn bên trong handler, không phải chương trình độc lập.
if (method.getName().equals("resolve")
        && Arrays.equals(method.getParameterTypes(),
                         new Class<?>[]{String.class})) {
    // Nhánh resolve(String).
}
```

Trong production, cách thiết kế tốt hơn tùy framework: mapping bằng `Method`, signature được chuẩn hóa, hoặc metadata đã được chuẩn bị khi dựng proxy. **Không** gộp mọi method cùng tên rồi xóa overload.

## 11. Những lỗi và tình huống cần chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` khi truy cập `args.length` | Method không đối số, `args==null` | Guard `args==null` hoặc dùng `getParameterCount()` trước |
| Method không đối số bị handler cho là một đối số null | Nhầm `args==null` và `args[0]==null` | Phân biệt cấu trúc ở mục 5 |
| Varargs `join()` bị ghi là 0 tham số | Dùng số phần tử varargs thay cho parameter count | `Method.getParameterCount()==1`, `args[0]` là array rỗng |
| `StackOverflowError` hoặc log lặp mãi | Gọi `method.invoke(proxy,args)`/`proxy.toString()` từ handler | Dùng delegate thật; log identity thay vì `toString` của proxy |
| `IllegalArgumentException: object is not an instance of declaring class` | Chuyển tiếp method interface lên delegate không triển khai interface phù hợp | Xác định đúng delegate và signature |
| `UndeclaredThrowableException` | Handler đưa checked exception không được chữ ký method cho phép ra caller | Unwrap `InvocationTargetException`; tuân thủ checked exceptions của interface |
| `ClassCastException` hoặc `NullPointerException` tại proxy return | Handler trả sai wrapper hoặc `null` cho primitive-return method | Đảm bảo return type phù hợp với `Method.getReturnType()` |
| `equals`/`hashCode` hoạt động bất nhất | Một method theo identity, method kia theo business identity | Thiết kế nhất quán cả hai |
| `toString` gây gọi handler nhiều lần | Logger stringify receiver/args chứa proxy | Đổi sang identity-safe formatter |
| Default method không chạy như dự kiến | Handler chặn/không chuyển tiếp default body | Dùng policy riêng; cân nhắc `InvocationHandler.invokeDefault` Java 17+ |
| Phân loại nhầm overload | Dispatch chỉ theo `getName()` | Kết hợp tên và danh sách kiểu tham số |
| Runtime có nhiều interface trùng chữ ký | Coi `declaringClass` là interface mà caller cast tới | Xem thứ tự interfaces của proxy và chính sách dispatch |
| Không tạo được proxy | Class loader không nhìn thấy interface, interface không phù hợp hoặc quy tắc package/module | Kiểm tra `Proxy.newProxyInstance`, class loader, danh sách interfaces, modules |
| Handler thấy null nhưng không biết là trường hợp nào | Log không ghi metadata và cấu trúc args | Ghi `getParameterCount`, `isVarArgs`, trạng thái null và kiểu array cuối |

### 11.1. Checklist đọc log theo thứ tự

Với một sự cố trong `InvocationHandler`, nên làm lần lượt:

1. Xác định đây có phải JDK proxy bằng `Proxy.isProxyClass(proxy.getClass())`, không cần hard-code tên proxy class.
2. Ghi `method.getName()`, `method.getDeclaringClass()`, `method.getParameterTypes()` và `method.getReturnType()`.
3. Ghi riêng **`args==null`** và **`args.length` khi không null**. Không gọi `Arrays.deepToString(args)` với object có khả năng tái nhập handler mà không bảo vệ.
4. Nếu `method.getDeclaringClass()==Object.class`, áp dụng policy cho `equals/hashCode/toString`.
5. Nếu `method.isVarArgs()`, kiểm tra kiểu/giá trị **array cuối**, không diễn giải `args.length` thành số phần tử varargs.
6. Nếu chuyển tiếp, chọn đúng delegate rồi chuẩn hóa `args` và gọi `method.invoke(delegate,safeArgs)`.
7. Nếu delegate ném exception, unwrap `InvocationTargetException`; nếu caller thấy `UndeclaredThrowableException`, kiểm tra checked exception và chữ ký interface.
8. Nếu return type primitive, kiểm tra handler đã trả wrapper phù hợp chứ không phải null.
9. Test thêm đối số null, không đối số, varargs rỗng và `equals(proxy)` để tránh những lỗi ẩn trong kịch bản đơn giản.

### 11.2. Những lời gọi không nên dùng để debug trực tiếp

`System.out.println(proxy)` hoặc `String.format("proxy=%s", proxy)` trong handler có thể gọi `proxy.toString()`. Gắn `proxy` vào cấu trúc `HashMap` cũng có thể khiến `hashCode()`/`equals()` chạy qua handler. Sử dụng `System.identityHashCode(proxy)` hoặc chỉ ghi `proxy.getClass()` để tách quan sát metadata khỏi nghiệp vụ.

Không gọi `method.invoke(proxy, ...)` chỉ để “xem kết quả” của method mà handler đang xử lý; như đã giải thích, việc đó thường dẫn tới vòng lặp tự gọi.

## 12. Hướng dẫn kiểm thử handler trước khi dùng trong framework

Một bộ test nhỏ cần bao phủ những trường hợp có ý nghĩa khác nhau, không chỉ kiểm tra happy path:

| Test case | Lời gọi ví dụ | Kết quả handler cần nhận diện |
| --- | --- | --- |
| Không đối số trả reference | `ping()` | `getParameterCount()==0`, `args==null`, trả chuỗi |
| Không đối số trả primitive | `size()` | `args==null`, return phải tương thích `int` |
| Không đối số trả void | `touch()` | `args==null`, delegate chạy dù return null |
| Một tham số bình thường | `echo("Java")` | `args.length==1` và `args[0]="Java"` |
| Một tham số null | `echo(null)` | `args.length==1` và `args[0]==null` |
| Varargs có phần tử | `join("a","b")` | `isVarArgs()==true`, `args.length==1`, `args[0]` là `String[2]` |
| Varargs không phần tử | `join()` | `args.length==1`, `args[0]` là `String[0]` |
| Varargs array null | `join((String[])null)` | `args.length==1`, `args[0]==null` |
| Object `toString` | `proxy.toString()` | `Method` của `Object`, `args==null`, không tái nhập |
| Object `equals` | `proxy.equals(proxy)` | `args.length==1`, phần tử đầu là chính proxy |
| Object `hashCode` | `proxy.hashCode()` | `args==null`, không tự gọi lại proxy hashCode |
| Exception từ delegate | `fail()` | Exception nghiệp vụ đến caller sau khi unwrap |
| Default method | `hello()` trong interface default | Handler nhận `Method.isDefault()==true`, chọn policy thực thi |
| Overload | `resolve(String)` và `resolve(long)` | Không gộp hai method chỉ vì trùng tên |

Nếu một framework tự tạo proxy từ interface người dùng, nên test cả **hai kiểu caller**: code gọi qua interface và code kích hoạt lời gọi gián tiếp qua logging/collections. Nhiều bug recursion chỉ xuất hiện khi logging gọi `toString()` hoặc collection cần `hashCode()`, không xuất hiện khi test một method nghiệp vụ thuần túy.

## 13. Bài tập thực hành và lời giải

**Bài 1.** `interface Job { void run(); }`. Handler viết `System.out.println(args.length);`. Khi gọi `proxy.run()` chuyện gì xảy ra?  
**Giải:** `args==null` vì `run()` không có tham số, nên `args.length` ném `NullPointerException`. Viết `args == null ? 0 : args.length` hoặc dùng `method.getParameterCount()` để lấy số tham số khai báo.

**Bài 2.** `interface Job { void run(String value); }`. Caller gọi `proxy.run(null)`. `args` là null hay mảng một phần tử?  
**Giải:** Là mảng một phần tử với `args[0]==null`. Điều này **khác** method không đối số.

**Bài 3.** `interface Job { void run(String... values); }`. Gọi `proxy.run()` có làm `args==null` không?  
**Giải:** Không. Method có một tham số `String[]`, nên `args` có một phần tử là mảng rỗng trong lời gọi varargs bình thường.

**Bài 4.** Trong handler, `return method.invoke(proxy,args);` được dùng để chạy nghiệp vụ. Vì sao nguy hiểm?  
**Giải:** `proxy` là receiver của JDK-generated proxy; gọi method trên nó có thể quay lại cùng handler liên tục. Chuyển tiếp sang delegate thật hoặc xử lý lời gọi theo policy khác.

**Bài 5.** Một logger trong handler dùng `"receiver=" + proxy`. Vì sao có thể gây `StackOverflowError`?  
**Giải:** Nối chuỗi gọi `toString()` của proxy; `toString` lại vào handler, log lại receiver... Dùng identity-safe logging.

**Bài 6.** Handler chuyển tiếp `Method.invoke(delegate, safeArgs)`, delegate ném `IllegalStateException`. Cần xử lý gì?  
**Giải:** Reflection bọc trong `InvocationTargetException`; catch wrapper và `throw ex.getCause()` để giữ exception gốc.

**Bài 7.** Handler trả `null` cho `int count()`. Vì sao có thể lỗi?  
**Giải:** Proxy cần unbox kết quả sang `int`; `null` không thể unbox, dẫn tới `NullPointerException`. Phải trả wrapper kiểu `Integer` hợp lệ.

**Bài 8.** Cách phân biệt `get(String)` và `get(long)` khi cả hai có `getName()=="get"`?  
**Giải:** Dùng cả `method.getParameterTypes()` hoặc metadata `Method` chính xác, không dispatch chỉ theo tên.

**Bài 9.** Proxy triển khai hai interface cùng khai báo `void refresh()`. `method.getDeclaringClass()` có luôn là kiểu interface mà caller cast tới không?  
**Giải:** Không. JDK proxy có quy tắc chọn method khi nhiều interface có chữ ký trùng; thứ tự interfaces khi tạo proxy có thể quyết định Method trình cho handler.

**Bài 10.** Khi `method.isDefault()==true`, có thể gọi `method.invoke(proxy,args)` để chạy default body không?  
**Giải:** Không nên; gọi lại method trên proxy có thể tái nhập handler. Java 17+ cho phép dùng `InvocationHandler.invokeDefault(proxy, method, normalizedArgs)` trong trường hợp phù hợp.

**Bài 11.** Vì sao `System.identityHashCode(proxy)` an toàn hơn `proxy.hashCode()` trong handler?  
**Giải:** `System.identityHashCode` lấy identity hash code mà không gọi override `hashCode` trên proxy; `proxy.hashCode()` đi qua handler và có thể gây recursion.

**Bài 12.** Vì sao `method.getDeclaringClass()==TaskServiceImpl.class` không phải cách nhận diện mọi lời gọi nghiệp vụ?  
**Giải:** JDK proxy dùng metadata method từ interface/`Object`, không mặc định từ implementation class. Delegate class là nơi handler quyết định ủy quyền đến.

## 14. Tổng kết

Một handler bền vững cần tuân thủ các nguyên tắc:

- **`proxy` là receiver proxy**, không phải delegate và không nên được stringify vô điều kiện.
- **`Method` mô tả method được proxy gửi đến**, thường khai báo ở interface hoặc `Object`; hãy đọc `name`, `parameterTypes`, `returnType`, `isVarArgs`, `isDefault` và owner khi cần.
- **`args==null` với method không đối số**. Kiểm tra null trước khi đếm hoặc duyệt. Đừng nhầm với mảng chứa **một phần tử null**.
- **Varargs là một tham số array ở bytecode**. `join()` không biến `args` của handler thành null nếu method khai báo `String...`.
- **Đối xử riêng với `equals/hashCode/toString`** theo policy nhất quán; không gọi ngược vào proxy gây recursion.
- **Khi có delegate**, dùng `method.invoke(delegate, normalizedArgs)` và unwrap `InvocationTargetException`. Không gọi `method.invoke(proxy,...)` để tự chuyển tiếp.
- **Kiểm tra return types và checked exceptions**. Primitive-return method cần wrapper hợp lệ; checked exception ngoài khai báo có thể bị bọc.
- **Với default method**, có thể gọi `InvocationHandler.invokeDefault` trên Java 17+ nếu muốn thực thi default body.

Tóm lại, trước khi viết bất kỳ code nào xử lý `args`, luôn tự hỏi: *Method này khai báo bao nhiêu tham số? Tham số cuối có phải varargs array không? Receiver hiện tại là proxy hay delegate?* Trả lời đúng ba câu hỏi đó sẽ loại bỏ phần lớn lỗi của dynamic proxy handler.

### Tài liệu chính thức

- [Oracle Java SE 17 — `InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): hợp đồng của `invoke`, ba tham số, `args=null` khi không có đối số và `invokeDefault`.
- [Oracle Java SE 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): cơ chế tạo proxy, các method `Object`, class loader và trường hợp trùng chữ ký giữa interfaces.
- [Oracle Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getDeclaringClass`, `getParameterTypes`, `isVarArgs`, `isDefault` và `Method.invoke`.
- [Oracle Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper cho exception do method đích ném khi gọi bằng Reflection.
- [Oracle Java SE 17 — `UndeclaredThrowableException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): trường hợp proxy bọc checked exception ngoài chữ ký method.
