# Bảng ngoại lệ Reflection trong Java và thông tin cần kiểm tra

## 1. Mục đích và phạm vi

Khi dùng Java Reflection để tìm lớp, tra cứu `Method`/`Field`/`Constructor`, đọc metadata hay thực thi phương thức, các lỗi thường thuộc **những giai đoạn khác nhau**. Nếu nhìn thấy một tên exception rồi sửa ngẫu nhiên bằng `setAccessible(true)`, thay overload hoặc bắt mọi `Exception`, bạn có thể che mất nguyên nhân thực sự.

Bài này cung cấp bảng tra cứu thực dụng: **lỗi xuất hiện ở API nào, nguyên nhân thường gặp, cần kiểm tra thông tin gì, cách xử lý phù hợp**. Ví dụ chạy bằng Java 17+.

Cần phân biệt:

- **Lỗi tra cứu:** chưa lấy được metadata đích (ví dụ `ClassNotFoundException`, `NoSuchMethodException`).
- **Lỗi quyền hoặc đối số khi gọi:** đã tìm được metadata nhưng lời gọi không hợp lệ (`IllegalAccessException`, `IllegalArgumentException`, `NullPointerException`).
- **Lỗi bên trong phương thức đích:** Java reflection bọc Throwable được target ném bằng `InvocationTargetException`; xem `getCause()`.
- **Lỗi module, class initialization hoặc JVM linking:** có thể là runtime exception hay `Error`, **không nhất thiết** thuộc `ReflectiveOperationException`.

Không phải mọi loại Throwable đều cần “bắt cho bằng được”. Mục tiêu là nhận diện lỗi lập trình/cấu hình từ sớm, truyền đạt lỗi dữ liệu rõ ràng và không che ngoại lệ nghiệp vụ.

## 2. Bảng tra cứu nhanh: lỗi → vị trí → thông tin cần xem

| Exception / Error | Hay gặp ở đâu | Điều cần kiểm tra đầu tiên |
| --- | --- | --- |
| `ClassNotFoundException` (checked) | `Class.forName("...")`, `ClassLoader.loadClass` | Tên nhị phân đầy đủ, classpath/module path, class loader dùng để nạp |
| `NoSuchMethodException` (checked) | `getMethod`, `getDeclaredMethod`, `getConstructor`, `getDeclaredConstructor` | Tên, **đúng dãy kiểu tham số**, public/declared, kế thừa, kiểu sau erasure |
| `NoSuchFieldException` (checked) | `getField`, `getDeclaredField` | Tên field, phân biệt public/declared, lớp đang tra cứu |
| `IllegalAccessException` (checked) | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | Modifier, declaring class, caller/module, khả năng truy cập Java và JPMS |
| `InaccessibleObjectException` (runtime) | `setAccessible(true)` khi yêu cầu bỏ qua access checks | Package được `opens` cho module caller chưa; có cần truy cập member non-public không |
| `SecurityException` (runtime) | Một số thao tác tra cứu/đổi accessibility, môi trường kiểm soát quyền | Quyền phản chiếu và chính sách môi trường (nếu có), tránh giả định vượt quyền |
| `IllegalArgumentException` (runtime) | `invoke`/`set`/`newInstance` | Receiver đúng loại, số lượng/thứ tự/kiểu đối số, primitive conversion, varargs |
| `NullPointerException` (runtime) | Gọi **instance** method trên receiver `null`, một số thao tác với null | Receiver hay giá trị bị thiếu? Method là static hay instance? |
| `InvocationTargetException` (checked) | `Method.invoke`, `Constructor.newInstance` | `getCause()`; stack trace và message của ngoại lệ target, không chỉ wrapper |
| `InstantiationException` (checked) | `Constructor.newInstance` với lớp trừu tượng | Đích có abstract? Kiểu có thể khởi tạo trực tiếp không? |
| `ExceptionInInitializerError` (`Error`) | Khởi tạo static của lớp, có thể bị kích hoạt khi tải/gọi | Static initializer/static fields, **cause**, trạng thái khởi tạo lớp |
| `LinkageError` (`Error`) | Tải/liên kết lớp | JAR/class phiên bản lệch, xung đột dependencies, binary compatibility |
| `WrongMethodTypeException` (runtime) | `MethodHandle.invokeExact/invoke` | `handle.type()`, kiểu tĩnh từng đối số **và kiểu kết quả tại call site** |
| `UndeclaredThrowableException` (runtime) | JDK dynamic proxy chuyển checked exception không được khai báo | `getUndeclaredThrowable()`, hợp đồng `throws` trên interface, logic handler |
| `StackOverflowError` (`Error`) | Handler của proxy/reflective dispatch quay lại chính nó | Chuỗi frame lặp, `method.invoke(proxy, args)`, logging `proxy.toString()` |

Bảng trên tổng hợp **tình huống thường gặp**, không phải liệt kê đầy đủ mọi throwable mà các API có thể ném. Một số ngoại lệ còn có nhiều nguyên nhân khác; luôn đọc tài liệu API và stack trace thực tế.

## 3. Tra cứu class, method, field và constructor

### 3.1. ClassNotFoundException: không tìm thấy lớp

```java
Class<?> type = Class.forName("com.example.Tool");
```

Khi bị `ClassNotFoundException`, kiểm tra:

1. Tên có đúng dạng **binary name** (`com.example.Tool`) không? Với nested class, tên nhị phân thường chứa `$` (ví dụ `Outer$Inner`).
2. Class có thực sự nằm trong artifact đã build và classpath/module path hiện tại không?
3. Class đang được yêu cầu bởi **class loader nào**? Cùng tên nhưng class loader khác nhau có thể đại diện cho lớp runtime khác nhau.
4. Với JPMS, module chứa class có được resolve vào module graph không? Đừng tự kết luận `ClassNotFoundException` luôn đồng nghĩa “quên JAR”.

`Class.forName(String)` cũng kích hoạt khởi tạo lớp theo semantics của overload này; lỗi ở static initializer có thể phát sinh `ExceptionInInitializerError`, còn lỗi linking có thể phát sinh `LinkageError`. Chúng **không phải** `ClassNotFoundException`. Khi cần tra cứu mà không chủ ý khởi tạo class, có overload:

```java
// Mảnh code trong ngữ cảnh có ClassLoader loader:
Class<?> type = Class.forName("com.example.Tool", false, loader);
```

Tham số `false` yêu cầu không khởi tạo lớp ngay ở bước này; thao tác sau đó vẫn có thể kích hoạt initialization.

### 3.2. NoSuchMethodException: sai tên hoặc chữ ký

```java
Method m = Service.class.getMethod("save", int.class, String.class);
```

`getMethod` tìm phương thức **public**, bao gồm public method được kế thừa. `getDeclaredMethod` tìm method **khai báo trực tiếp trong chính class**, kể cả private, nhưng không tự tìm inherited method. Dãy kiểu tham số phải khớp chính xác sau erasure; `int.class` khác `Integer.class` và `List.class` không biểu diễn riêng `List<String>`.

Khi lỗi, ghi nhận:

- `declaring class`/class đang tra cứu và `getName()`.
- Tên method, **số lượng, thứ tự và `Class<?>` từng tham số**; không chỉ tên method.
- API lookup dùng `getMethod` hay `getDeclaredMethod`, và method có bị kế thừa/không public không.
- Có overload hoặc bridge/synthetic method do generic/compilation tạo ra không.
- Kiểu return **không tham gia vào tham số của `getMethod`**; sau khi resolve, kiểm tra riêng `method.getReturnType()` nếu hợp đồng cần.

Đừng dùng `getMethods()[0]` hoặc chọn “phương thức đầu tiên trùng tên” để né `NoSuchMethodException`.

### 3.3. NoSuchFieldException: sai scope tra cứu

`getField("code")` tìm public field, bao gồm field được kế thừa theo quy tắc Reflection. `getDeclaredField("code")` tìm field được khai báo ngay trên class, kể cả non-public; tìm thấy metadata private **không tự cấp quyền đọc/ghi**.

Kiểm tra tên chính xác, class khai báo, field được kế thừa hay khai báo trực tiếp, Modifier và liệu class metadata có đúng runtime class cần thao tác không. Field không có tham số như Method, nhưng kiểu field (`field.getType()`), static/instance và final cần được kiểm tra trước `get/set`.

### 3.4. Constructor: đúng arity chưa chắc khởi tạo được

```java
Constructor<?> ctor = type.getDeclaredConstructor(String.class, int.class);
Object obj = ctor.newInstance("x", 3);
```

Tra cứu có thể ném `NoSuchMethodException`; gọi constructor có thể ném `InstantiationException` (ví dụ lớp abstract), `IllegalAccessException`, `IllegalArgumentException` và `InvocationTargetException` do thân constructor ném ngoại lệ. `ExceptionInInitializerError` cũng có thể xảy ra nếu static initialization của lớp thất bại.

Đừng nhầm `Class.newInstance()` với `Constructor.newInstance()`. `Class.newInstance()` đã deprecated; `Constructor.newInstance` cho phép phân biệt ngoại lệ target qua `InvocationTargetException` rõ ràng hơn.

## 4. Đã tìm được Method nhưng invoke thất bại

Giả sử có:

```java
Method m = Worker.class.getMethod("repeat", String.class, int.class);
Object out = m.invoke(new Worker(), "go", 2);
```

Khi lỗi, cần lần lượt kiểm tra:

| Cần kiểm tra | API hoặc cách kiểm tra | Vì sao |
| --- | --- | --- |
| Đã resolve đúng method? | `m.getName()`, `m.getDeclaringClass()` | Tránh gọi nhầm class/overload |
| Method static hay instance? | `Modifier.isStatic(m.getModifiers())` | Static có thể dùng receiver `null`; instance cần receiver hợp lệ |
| Receiver đúng loại? | `m.getDeclaringClass().isInstance(target)` cho instance | Sai receiver có thể dẫn đến `IllegalArgumentException` |
| Receiver có null? | `target == null` | Instance invoke trên receiver null ném `NullPointerException` |
| Arity và kiểu? | `m.getParameterCount()`, `m.getParameterTypes()` | Sai số/thứ tự/kiểu đối số thường là `IllegalArgumentException` |
| Accessibility? | `m.getModifiers()`, `m.canAccess(target)` nếu hợp lệ | Có thể gặp `IllegalAccessException`; `canAccess` đòi receiver phù hợp với trường hợp instance |
| Có varargs? | `m.isVarArgs()` | `Method.invoke` vẫn nhận mảng argument đúng vị trí; cần đóng gói array đích |
| Kết quả có đúng? | `m.getReturnType()` | `void` trả `null` qua `Method.invoke`, primitive result được boxing |
| Target có tự ném lỗi? | `InvocationTargetException.getCause()` | Nguyên nhân thực nằm trong target |

**Chuyển đổi số:** `Method.invoke` cho phép một số phép unboxing và **widening primitive** phù hợp, nhưng không tùy ý narrowing và không parse `"2"` thành `int`. Một công cụ nhận dữ liệu String phải áp dụng converter tường minh **trước khi invoke**.

**Varargs:** Khi phương thức đích khai báo `String... items`, tham số cuối ở cấp Reflection là `String[]`. `Method.invoke` là varargs API nhưng không có nghĩa tự xử lý danh sách đối số user thành varargs của target theo mọi hình dạng. Hãy xây dựng một `Object[]` có phần tử cuối là `String[]` đúng kiểu, truyền mảng argument một cách chủ đích và kiểm thử.

**Access:** `getDeclaredMethod` tìm thấy private method nhưng `Method.invoke` có thể vẫn ném `IllegalAccessException`. Kiểm tra class/module và thiết kế API trước khi quyết định có cần quyền truy cập sâu. `setAccessible(true)` không phải cách sửa chung cho mọi exception.

## 5. Lỗi bên trong target: InvocationTargetException

Đây là khác biệt quan trọng nhất trong debug Reflection:

```java
try {
    Object result = method.invoke(target, args);
    // Xử lý result.
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // Ghi log/chuyển tiếp theo chính sách của ứng dụng.
    throw original;
}
```

Đoạn là **mảnh code bên trong phương thức khai báo `throws Throwable`**. Khi method target thực sự chạy và ném `IOException`, `IllegalStateException` hay thậm chí `Error`, `Method.invoke` có thể bọc Throwable từ target bằng `InvocationTargetException`. `ex.getCause()` (hoặc `getTargetException()`) cho biết lỗi thật.

Phân biệt:

- `IllegalArgumentException` **ném trực tiếp từ `Method.invoke`**: thường là receiver/argument không đúng; target có thể chưa được thực thi.
- `InvocationTargetException` có cause là `IllegalArgumentException`: chính **method target** đã ném lỗi đó trong phần thực thi của mình.
- `InvocationTargetException` có cause là checked exception: đừng xóa cause hoặc tự động phân loại thành lỗi parser.
- Với logging, cần xem **stack trace và message của cause**; log wrapper một mình có thể bỏ qua frame hữu ích.

Nếu wrapper có nhiều tầng, có thể kiểm tra chuỗi `getCause()` nhưng không được tự động làm mất ranh giới nghiệp vụ, retry một hành động có side effect hoặc tiết lộ stack trace nhạy cảm cho caller.

## 6. Ví dụ Java 17+ chạy độc lập: bảng lỗi bằng thực nghiệm

Lưu toàn bộ mã dưới đây trong `ReflectionExceptionDemo.java`. Nó tạo các trường hợp lỗi **có chủ đích, bắt được và in nhãn ổn định**, không cần kích hoạt lỗi JPMS hay StackOverflowError khó kiểm soát.

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionExceptionDemo {
    public static class Worker {
        public String repeat(String word, int times) {
            return word.repeat(times);
        }
        public void fail() throws IOException {
            throw new IOException("storage unavailable");
        }
    }

    public static abstract class AbstractJob {
        public AbstractJob() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Worker.class;
        Method repeat = type.getMethod("repeat", String.class, int.class);
        System.out.println("method=" + repeat.getName());
        System.out.println("parameters=" + repeat.getParameterCount());
        System.out.println("return=" + repeat.getReturnType().getSimpleName());
        System.out.println("static=" + Modifier.isStatic(repeat.getModifiers()));
        System.out.println("success=" + repeat.invoke(new Worker(), "go", 2));

        try {
            type.getMethod("repeat", int.class, int.class);
        } catch (NoSuchMethodException ex) {
            System.out.println("lookup: " + ex.getClass().getSimpleName());
        }
        try {
            type.getField("missing");
        } catch (NoSuchFieldException ex) {
            System.out.println("field: " + ex.getClass().getSimpleName());
        }
        try {
            repeat.invoke(new Worker(), "go", "2");
        } catch (IllegalArgumentException ex) {
            System.out.println("arguments: " + ex.getClass().getSimpleName());
        }
        try {
            repeat.invoke(null, "go", 2);
        } catch (NullPointerException ex) {
            System.out.println("receiver: " + ex.getClass().getSimpleName());
        }
        try {
            Method hidden = ExternalHelper.class.getDeclaredMethod("secret");
            hidden.invoke(new ExternalHelper());
        } catch (IllegalAccessException ex) {
            System.out.println("access: " + ex.getClass().getSimpleName());
        }
        try {
            Method fail = type.getMethod("fail");
            fail.invoke(new Worker());
        } catch (InvocationTargetException ex) {
            System.out.println("target: " + ex.getCause().getClass().getSimpleName());
            System.out.println("message=" + ex.getCause().getMessage());
        }
        try {
            Constructor<AbstractJob> ctor = AbstractJob.class.getDeclaredConstructor();
            ctor.newInstance();
        } catch (InstantiationException ex) {
            System.out.println("construct: " + ex.getClass().getSimpleName());
        }
        try {
            Class.forName("missing.example.NotOnClasspath");
        } catch (ClassNotFoundException ex) {
            System.out.println("load: " + ex.getClass().getSimpleName());
        }
    }
}

class ExternalHelper {
    private String secret() {
        return "hidden";
    }
}
```

Biên dịch và chạy:

```bash
javac ReflectionExceptionDemo.java
java ReflectionExceptionDemo
```

Stdout đã kiểm chứng bằng JDK:

```text
method=repeat
parameters=2
return=String
static=false
success=gogo
lookup: NoSuchMethodException
field: NoSuchFieldException
arguments: IllegalArgumentException
receiver: NullPointerException
access: IllegalAccessException
target: IOException
message=storage unavailable
construct: InstantiationException
load: ClassNotFoundException
```

**Vì sao ví dụ đáng chú ý?**

1. Tra cứu `repeat` với `(String,int)` đúng, còn tra cứu `(int,int)` ném `NoSuchMethodException` dù trùng tên.
2. `getField("missing")` thất bại ở bước tra cứu field, không liên quan đến bước invocation.
3. Truyền `"2"` thay cho `int` khi gọi `repeat` gây `IllegalArgumentException`; Reflection không parse String thành số nguyên.
4. Receiver `null` đối với instance method `repeat` gây `NullPointerException`; static method có quy tắc receiver khác.
5. `ExternalHelper.secret` là phương thức `private` của **lớp top-level khác**; `getDeclaredMethod` tìm được metadata, nhưng code ở `ReflectionExceptionDemo` không được invoke nếu chưa có quyền.
6. `Worker.fail()` thực thi thật và ném `IOException`; Reflective API bọc vào `InvocationTargetException` nên mẫu lấy `getCause()`.
7. `AbstractJob` là abstract; tra cứu constructor được nhưng `newInstance` không thể tạo instance, phát sinh `InstantiationException`.
8. `Class.forName` với tên không tồn tại ném `ClassNotFoundException`.

Đây là những lỗi **dự kiến trong bài demo**. Trong ứng dụng thật, nên phân loại lỗi để xử lý thay vì cứ cho phép caller gây hàng loạt lỗi rồi mới bắt.

## 7. Chẩn đoán lỗi truy cập và JPMS đúng API

Khi đã có `Method`, `Field` hoặc `Constructor` nhưng thao tác thất bại, tách **quyền truy cập hiện tại** khỏi **việc yêu cầu bỏ qua access checks**:

| Dấu hiệu | Điều cần làm rõ |
| --- | --- |
| `IllegalAccessException` tại `invoke/get/set/newInstance` | Caller, declaring class, modifier, runtime package/nest và module; thành viên có thật nhưng chưa được phép thao tác |
| `member.canAccess(receiver) == false` | Access check hiện tại không qua; với static member/constructor dùng `null`, instance cần receiver đúng kiểu |
| `member.trySetAccessible() == false` | Không bật được suppression theo ranh giới module; phương thức này báo `false` khi không thể bật, thay vì tự động ném `InaccessibleObjectException` |
| `InaccessibleObjectException` từ `setAccessible(true)` | Package thuộc named module chưa `opens` cho caller (hoặc điều kiện cấp quyền khác không thỏa) |
| `SecurityException` khi đổi access | Chính sách runtime từ chối quyền liên quan, khác lỗi `opens` |

`exports` cho phép dùng public API theo quy tắc Java/JPMS; **deep reflection** tới private members từ module khác thường cần `opens` đúng package và caller. `getDeclaredMethod` chỉ tìm metadata, không tự cho phép invoke. Ví dụ: mở `java.base/java.lang` để đọc private member JDK chỉ vì lỗi truy cập thường là dấu hiệu cần chọn public API phù hợp hơn.

Sau khi giải quyết access, vẫn phải kiểm tra receiver, arity và kiểu tham số: `setAccessible(true)` không sửa `IllegalArgumentException`, `NoSuchMethodException` hoặc lỗi do target ném. Bảng phân quyền theo package, nest và module được trình bày riêng trong bài chuyên về access; bảng ở đây dùng để **khoanh vùng exception** trong luồng debug.

## 8. Không gộp Method.invoke với MethodHandle và Dynamic Proxy

Cùng nằm trong hệ sinh thái reflective/dynamic invocation, nhưng **cơ chế ném lỗi khác nhau**.

### 8.1. MethodHandle: WrongMethodTypeException

Với `MethodHandle`, chữ ký nằm trong `handle.type()`. `invokeExact` yêu cầu kiểu đối số và kiểu kết quả **tại call site** trùng chính xác. `invoke` cho phép thích nghi kiểu hợp lệ; nếu không thể thích nghi sẽ ném `WrongMethodTypeException`. Nếu cast tham chiếu thất bại ở runtime có thể thấy `ClassCastException`.

Ví dụ minh họa, chưa phải chương trình độc lập:

```java
// h có MethodType (long,long)long.
long ok = (long) h.invokeExact(1L, 2L);
long bad = (long) h.invokeExact(1, 2L); // WrongMethodTypeException
```

Đừng xử lý `WrongMethodTypeException` bằng cách catch `InvocationTargetException`: đó là loại exception khác và không đại diện cho lỗi do `Method.invoke` bọc target.

### 8.2. Dynamic proxy: UndeclaredThrowableException

Với JDK dynamic proxy, `InvocationHandler.invoke` có thể ném `Throwable`. Nếu handler ném một **checked exception** không được khai báo trong `throws` của phương thức interface, proxy có thể bọc nó thành `UndeclaredThrowableException`. Kiểm tra:

- Method thuộc interface nào, `getExceptionTypes()` khai báo những checked exception gì.
- Handler có unwrap, chuyển đổi hoặc ném checked exception ngoài hợp đồng không.
- `UndeclaredThrowableException.getUndeclaredThrowable()` hoặc `getCause()` để thấy lỗi gốc.
- Nếu có `StackOverflowError`, rà soát handler gọi lại `method.invoke(proxy, args)` hoặc log chính proxy gây `toString()` re-entry.

`InvocationTargetException` có thể xuất hiện **bên trong handler** nếu handler dùng `Method.invoke(target, args)`, còn `UndeclaredThrowableException` là wrapper mà dynamic proxy tạo khi checked exception không hợp đồng đi ra caller. Không đánh đồng hai tầng.

### 8.3. Generic metadata có thể lỗi riêng

Khi đọc `getGenericParameterTypes()` hoặc `getGenericReturnType()`, một số API có thể gặp `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc `GenericSignatureFormatError` vì type signature không resolve hay không hợp lệ. Điều đó không nhất thiết nghĩa là method không tồn tại. Nếu công cụ phụ thuộc generic metadata, hãy ghi nhận chữ ký raw và generic, module/classpath của kiểu tham chiếu, không tự tạo giá trị thay thế sai.

## 9. Checklist điều tra lỗi theo thứ tự

Khi nhận một log Reflective Invocation lỗi, nên thu thập thông tin có cấu trúc:

1. **Giai đoạn:** class load, lookup, accessibility, mapping input, invocation, target execution, hay initialization?
2. **Ngoại lệ thật và cause:** `ex.getClass().getName()`, `ex.getMessage()`, `ex.getCause()`; với `InvocationTargetException`, xem trực tiếp cause.
3. **Class identity:** `type.getName()`, `type.getModule()`, `type.getClassLoader()` nếu thích hợp. Hai lớp cùng tên nhưng class loader khác nhau không phải cùng kiểu.
4. **Method/field signature:** tên, declaring class, modifier, kiểu tham số theo thứ tự, kiểu trả về hoặc kiểu field, `isVarArgs()`.
5. **Receiver:** null hay không; runtime class thực tế qua `receiver.getClass()` (chỉ gọi khi khác null); có tương thích declaring class không.
6. **Arguments:** số lượng, kiểu runtime có thể hiển thị dưới dạng tên kiểu, vị trí sai, primitive/wrapper và converter đã chạy chưa. Với null, cần schema để biết kiểu mong đợi.
7. **Access/module:** public/private, package, `module-info.java`, `exports/opens`, caller module và `canAccess(...)` phù hợp.
8. **Giao ước API:** method nào được phép gọi, caller có quyền không, lỗi dữ liệu cần báo gì, có transaction/side effect khi target đã chạy không.
9. **Stack trace:** frame nào lặp lại hoặc nằm trong target; đừng chỉ nhìn dòng wrapper ngoài cùng.
10. **Tái hiện:** viết test tối thiểu với class/method/arguments tương đương, chặn input sai trước invocation.

Có thể dùng helper ghi **metadata** sau để hỗ trợ debug; đây là mảnh code nằm trong phương thức có biến `Method method` và đã import `Arrays`, `Modifier`:

```java
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("method=" + method.getName());
System.out.println("static=" + Modifier.isStatic(method.getModifiers()));
System.out.println("parameters=" +
        java.util.Arrays.toString(method.getParameterTypes()));
System.out.println("returns=" + method.getReturnType().getTypeName());
System.out.println("varargs=" + method.isVarArgs());
```

**Bảo vệ dữ liệu:** không log nguyên credentials, token, mật khẩu, request body chứa thông tin nhạy cảm hoặc nguyên argument values trong hệ thống production nếu không được phép. Ghi tên kiểu, index, error code và correlation ID thường đủ để điều tra phần lớn lỗi mapping.

## 10. Nguyên tắc xử lý và phản hồi lỗi

Không nên viết:

```java
try {
    // Tìm Method, chuyển đổi dữ liệu, invoke...
} catch (Exception ignored) {
    return null; // Sai: mất nguyên nhân, biến lỗi thành kết quả giả.
}
```

Thay vào đó, xác định **ranh giới lỗi**:

| Nhóm | Cách xử lý phù hợp |
| --- | --- |
| Lỗi cấu hình/không tìm được method trong hợp đồng tin cậy | Fail-fast khi khởi tạo, sửa tên/chữ ký/dependency |
| Lỗi dữ liệu caller: arity, kiểu, định dạng | Validate/convert trước invocation, báo tham số và kiểu cần nhập |
| Lỗi quyền/module | Xem lại thiết kế public API và quyền; chỉ mở package khi có chủ đích và được cho phép |
| Lỗi target | Lấy cause từ `InvocationTargetException`, xử lý theo hợp đồng nghiệp vụ |
| Lỗi JVM/linkage/initialization nghiêm trọng | Ghi đủ bối cảnh, xử lý ở ranh giới hệ thống phù hợp; không tự động nuốt `Error` |
| Lỗi dynamic proxy/MethodHandle | Chẩn đoán theo chữ ký handler/call site riêng, không ép vào cơ chế Method.invoke |

**Không retry mù quáng** khi target đã được gọi: phương thức có thể ghi dữ liệu, gửi yêu cầu mạng hoặc thực hiện side effect trước khi ném exception. Chỉ retry nếu hợp đồng nghiệp vụ cho phép và có cơ chế idempotency/transaction tương ứng.

## 11. Lỗi thường gặp

1. Cứ gặp `NoSuchMethodException` là gọi `getDeclaredMethods()[0]`, dễ chọn sai overload hoặc sai quyền.
2. Chỉ so tên method, bỏ qua tham số `int.class` so với `Integer.class`.
3. Thấy private member là gọi `setAccessible(true)` mà không xét module/thiết kế API.
4. Tưởng `Method.invoke` parse được `String` sang primitive hoặc DTO.
5. Không phân biệt static/instance và truyền receiver null hoặc sai kiểu.
6. Bắt `InvocationTargetException` nhưng chỉ log wrapper, bỏ mất `getCause()`.
7. Catch tất cả `Throwable` rồi tiếp tục như chưa có lỗi, che `Error` nghiêm trọng.
8. Tưởng `ReflectiveOperationException` bao phủ `InaccessibleObjectException`, `SecurityException`, `WrongMethodTypeException` hay `LinkageError`.
9. Gọi `Class.forName` rồi cho rằng mọi thất bại đều là “class chưa có”: initialization/linkage cũng là các khả năng cần phân biệt.
10. Với proxy, gọi lại chính proxy trong handler dẫn đến `StackOverflowError`.
11. Cho rằng phương thức tìm được qua `getDeclaredMethod` thì chắc chắn invoke được.
12. In toàn bộ đối số/request để debug mà không cân nhắc lộ thông tin nhạy cảm.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `getMethod("save", int.class)` ném `NoSuchMethodException` dù code có `save(Integer)`. Vì sao?

Vì `int.class` khác `Integer.class`; lookup theo **chữ ký kiểu chính xác**. Boxing không giúp `getMethod` tự chọn overload.

**Câu 2.** `getDeclaredMethod("secret")` tìm được nhưng `invoke` ném `IllegalAccessException`. Đây có phải lỗi “không tồn tại method” không?

Không. Metadata tìm thấy, nhưng caller không có quyền gọi. Cần kiểm visibility/module/thiết kế quyền.

**Câu 3.** Target ném `IOException` khi `Method.invoke` gọi nó. Bắt exception nào ở tầng reflection để tìm `IOException`?

Bắt `InvocationTargetException`, lấy `getCause()` hoặc `getTargetException()`.

**Câu 4.** `Method.invoke(target, "5")` gọi method nhận `int` có tự chuyển chuỗi thành số không?

Không. Phải parse tường minh trước và chuyển giá trị `Integer` hợp lệ vào `Object[]`.

**Câu 5.** `Class.forName` ném `ExceptionInInitializerError`. Có nên sửa bằng cách thêm JAR như khi `ClassNotFoundException` không?

Không mặc định. `ExceptionInInitializerError` chỉ ra lỗi khi thực hiện static initialization. Hãy xem cause và mã static initializer.

**Câu 6.** `setAccessible(true)` ném `InaccessibleObjectException`. Việc method `private` được tìm thấy có chứng minh module cho truy cập sâu không?

Không. Tìm metadata và quyền truy cập sâu là hai việc khác nhau; xem quy tắc JPMS `opens` và lựa chọn API công khai.

**Câu 7.** Proxy ném `UndeclaredThrowableException` thay vì checked exception của handler. Cần xem gì?

Xem cause/`getUndeclaredThrowable()` và checked exceptions khai báo ở interface method.

**Câu 8.** `WrongMethodTypeException` khi `invokeExact` có cần kiểm kiểu kết quả không?

Có. Kiểu kết quả **tại call site** cũng phải khớp với `MethodHandle.type()`, bên cạnh kiểu đối số.

## 13. Ghi nhớ

**Xác định giai đoạn xảy ra lỗi trước, rồi đối chiếu đúng metadata và hợp đồng.** `NoSuchMethodException` gợi ý lỗi tra cứu chữ ký; `IllegalAccessException` gợi ý quyền truy cập; `IllegalArgumentException` tại `Method.invoke` thường gợi ý receiver/argument; `InvocationTargetException` báo rằng target đã ném Throwable và **cause mới là vấn đề cần điều tra**. Lỗi JPMS, MethodHandle và dynamic proxy có cơ chế riêng.

Tài liệu Java 17 để tra cứu trực tiếp:

- [Class (getMethod/getField/forName)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)