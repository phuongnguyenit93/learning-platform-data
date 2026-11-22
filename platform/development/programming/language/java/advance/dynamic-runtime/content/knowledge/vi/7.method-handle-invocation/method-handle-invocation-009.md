# 7.9. Ngoại lệ Throwable từ đích gọi và khác biệt với cơ chế bọc của reflection

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao `MethodHandle.invokeExact(...)`, `MethodHandle.invoke(...)` và `invokeWithArguments(...)` có thể truyền **trực tiếp** `Throwable` do phương thức đích ném ra.
2. Phân biệt ngoại lệ do **đích gọi** với lỗi phát sinh ở bước lookup, kiểm tra chữ ký, chuyển đổi đối số, quyền truy cập và liên kết lời gọi.
3. Mô tả chính xác cách `java.lang.reflect.Method.invoke(...)` bọc ngoại lệ từ đích trong `InvocationTargetException` và cách truy xuất nguyên nhân bằng `getCause()`.
4. Nhận biết sự khác biệt với checked exception, unchecked exception và `Error`; xử lý ngoại lệ đúng khi xây dựng adapter hoặc framework.
5. Viết mã Java 17+ có thể chạy để so sánh hai đường gọi và tránh mất stack trace/cause.

**Phạm vi:** Bài tập trung vào việc **gọi method handle** (chương 7) và đối chiếu trực tiếp với cơ chế reflection. Việc tạo handle qua `Lookup` chỉ được nhắc tới ở mức đủ để làm rõ nguồn ngoại lệ.

## 1. Vấn đề: lỗi thực sự đến từ đâu?

Giả sử phương thức nghiệp vụ sau có thể thất bại:

```java
public static String read(String key) throws java.io.IOException {
    if (key.isBlank()) {
        throw new java.io.IOException("empty key");
    }
    return "value:" + key;
}
```

Đây là một **phương thức minh họa**, chưa phải chương trình Java độc lập.

Một lời gọi thông thường `read("")` có thể ném `IOException` trực tiếp. Nhưng nếu framework gọi phương thức này gián tiếp, ngoại lệ mà lớp bên ngoài nhìn thấy còn phụ thuộc **API được dùng để thực hiện lời gọi**:

- `MethodHandle.invokeExact(...)` hoặc `invoke(...)`: khi đích thực sự ném `IOException`, đối tượng `IOException` đó truyền qua lời gọi handle **không bị API method handle tự động bọc** trong `InvocationTargetException`.
- `Method.invoke(...)`: nếu phương thức đích ném `IOException`, caller nhận **`InvocationTargetException`**, với `getCause()` là `IOException` gốc.
- Một lỗi xuất hiện **trước khi đích chạy** (không tìm thấy method, sai signature, sai đối số, thiếu quyền truy cập...) phải được xử lý riêng; không được mặc định xem mọi exception bắt được đều là lỗi nghiệp vụ.

Hình dung hai đường đi:

```text
Method handle:
caller -> invokeExact/invoke -> method đích -> IOException
caller bắt IOException

Core reflection:
caller -> Method.invoke -> method đích -> IOException
caller bắt InvocationTargetException
                                  |
                                  +-- getCause() -> IOException
```

Đối tượng wrapper của reflection giúp phân biệt “lời gọi phản chiếu thất bại vì **đích đã ném lỗi**” với lỗi do chính API reflection ném. Ngược lại, method handle có mô hình gần với lời gọi thông thường hơn: lỗi của đích đi thẳng tới caller, nhưng caller phải biết cách phân loại nguồn lỗi.

## 2. `Throwable` là gì trong đường gọi method handle?

`java.lang.Throwable` là lớp gốc của cây throwable trong Java; hai nhánh quan trọng là `Error` và `Exception`. `RuntimeException` nằm dưới `Exception`.

| Nhóm | Ví dụ | Ý nghĩa trong lời gọi động |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `Exception` | Với lời gọi tĩnh, compiler thường yêu cầu khai báo/bắt theo chữ ký method; với handle, API invocation đã khai báo `throws Throwable` |
| Unchecked exception | `IllegalStateException`, `IllegalArgumentException`, `NullPointerException` | Có thể đến từ chính đích hoặc do adapter/invocation API gây ra |
| `Error` | `AssertionError`, `LinkageError`, `OutOfMemoryError` | Cũng là `Throwable`; không nên bắt rồi nuốt mọi `Error` trong luồng production |
| Invocation/linkage failure | `WrongMethodTypeException`, `ClassCastException`, `NoSuchMethodException`, `IllegalAccessException` | Cần phân biệt phát sinh ở call site/lookup/adaptation hay do đích tự ném |

**Lưu ý:** Một lớp exception như `IllegalArgumentException` có thể do **code nghiệp vụ cố ý ném**, cũng có thể do API gọi báo đối số không hợp lệ. Chỉ nhìn tên class của exception thường chưa đủ kết luận nguồn.

### 2.1. Vì sao lời gọi handle khai báo `throws Throwable`?

Trong Java SE 17, các phương thức **signature-polymorphic** `MethodHandle.invokeExact` và `MethodHandle.invoke` được khai báo `throws Throwable`. Handle có thể trỏ tới nhiều mục tiêu rất khác nhau và JVM không mã hóa toàn bộ danh sách checked exceptions vào `MethodType`.

Khi viết:

```java
String result = (String) handle.invokeExact("ready");
```

Đây là **dòng mã minh họa** trong phương thức có biến `MethodHandle handle` loại `(String)String`. Compiler biết biểu thức gọi handle có thể ném `Throwable` vì khai báo API, cho dù mục tiêu cụ thể chỉ khai báo `throws IOException` hoặc không khai báo checked exception nào. Vì vậy phương thức chứa lời gọi phải xử lý phù hợp bằng `try/catch` hoặc khai báo `throws Throwable`.

Không nên suy luận rằng vì API khai báo `throws Throwable` nên nó sẽ luôn tạo thêm một `Throwable` wrapper. **Khai báo throws và hành vi bọc exception là hai việc khác nhau.**

### 2.2. “Truyền trực tiếp” nghĩa là gì?

Nếu thân method đích thực hiện `throw original;`, lời gọi handle trực tiếp đưa throwable đó ra caller, không tự tạo `InvocationTargetException` để bọc. Điều này bao gồm:

- checked exception (`IOException`);
- unchecked exception (`IllegalStateException`);
- `Error` (`AssertionError` trong ví dụ kiểm chứng).

Bạn có thể `catch (IOException ex)` ngay ở caller khi biết đích có khả năng phát sinh loại lỗi đó. Nếu code bắt `Throwable` để chẩn đoán, cần hiểu rằng nó sẽ bắt luôn `Error` và những throwable không nên tiếp tục xử lý tùy tiện.

### 2.3. `invokeExact` và `invoke` có cùng quy tắc truyền lỗi đích?

Có. Cả hai truyền throwable do target ném ra trực tiếp. Điểm khác nhau chính là **kiểu gọi**:

- `invokeExact` yêu cầu call-site descriptor (kiểu tĩnh của đối số và kết quả tại nơi gọi) trùng khớp với `handle.type()`; mismatch có thể ném `WrongMethodTypeException` **trước khi** vào đích.
- `invoke` cho phép những chuyển đổi kiểu được hợp đồng method handle hỗ trợ, tương tự thích nghi bằng `asType`. Nếu conversion không hợp lệ, caller nhận lỗi từ quá trình adaptation/conversion, cũng **không phải** `InvocationTargetException`.
- `invokeWithArguments` thuận tiện khi đối số ở dạng `Object[]`/`List<?>`, và cũng khai báo `throws Throwable`. Nó có bước thích nghi đối số/kết quả với những chi phí và lỗi chuyển đổi tương ứng; không nên giả định mọi exception từ lời gọi này đều do thân method đích.

Một handle còn có thể được tạo từ các combinator như `filterArguments`, `catchException`, `throwException` hoặc các adapter tùy chỉnh. Lúc đó **toàn bộ pipeline handle** là mục tiêu quan sát, và logic tự xây có thể cố ý thay đổi exception. Khẳng định “không có wrapper `InvocationTargetException` mặc định” áp dụng cho **hành vi gọi handle chuẩn**, chứ không ngăn code của bạn chủ động bọc lỗi.

## 3. Reflection bọc lỗi đích bằng `InvocationTargetException`

`java.lang.reflect.Method.invoke(Object receiver, Object... args)` gọi method qua metadata của class. Nó khai báo những lỗi phản chiếu như `IllegalAccessException`, `IllegalArgumentException` và `InvocationTargetException`.

Khi **phương thức đích thực sự ném throwable**, `Method.invoke` ném `InvocationTargetException`. Wrapper này là **checked exception** (kế thừa `ReflectiveOperationException`), còn throwable gốc nằm trong cause.

```java
try {
    Object value = reflectedMethod.invoke(null, "bad");
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // Xử lý dựa trên loại exception thực sự của phương thức đích.
}
```

Đây là **đoạn minh họa**: `reflectedMethod` phải là đối tượng `Method` của một static method nhận `String`. Với method instance, tham số receiver là instance phù hợp thay vì `null`.

### 3.1. `getCause()` hay `getTargetException()`?

Cả hai truy cập throwable gốc trong `InvocationTargetException`. `getTargetException()` là API lịch sử có trước cơ chế cause-chaining chung; **`getCause()` được ưu tiên** trong mã mới.

Nếu cần phân loại:

```java
Throwable cause = ex.getCause();
if (cause instanceof java.io.IOException io) {
    // Lỗi I/O thực sự từ đích.
} else if (cause instanceof IllegalStateException state) {
    // Lỗi trạng thái thực sự từ đích.
}
```

Đây là đoạn minh họa nằm trong `catch (InvocationTargetException ex)`. Pattern matching cho `instanceof` hỗ trợ từ Java 16 nên chạy được trên Java 17. Một wrapper do code khác tự tạo có thể có cause `null`; khi unwrap trong thư viện tổng quát, hãy tính tới trường hợp bất thường này.

### 3.2. Reflection bọc cả unchecked exception và Error từ đích?

Có. Một method phản chiếu ném `IllegalStateException` hoặc `AssertionError` thì `Method.invoke` vẫn dùng `InvocationTargetException` để báo **đích đã ném lỗi**. Không được hiểu rằng chỉ checked exception mới bị bọc.

Tuy nhiên, **không phải mọi throwable xuất hiện khi thực hiện `Method.invoke` đều được bọc**. Ví dụ: truyền sai đối số có thể gây `IllegalArgumentException` từ API reflection trước khi đích chạy; receiver `null` với instance method gây `NullPointerException`; khởi tạo static class thất bại có thể gây `ExceptionInInitializerError`. Phải đọc hợp đồng API và phân biệt lớp xảy ra lỗi.

## 4. Bảng đối chiếu MethodHandle và Method.invoke

| Tình huống | `MethodHandle.invokeExact/invoke` | `Method.invoke` |
| --- | --- | --- |
| Target ném `IOException` | Caller nhận `IOException` trực tiếp | Caller nhận `InvocationTargetException`, `getCause()` là `IOException` |
| Target ném `IllegalStateException` | `IllegalStateException` trực tiếp | `InvocationTargetException` chứa `IllegalStateException` |
| Target ném `AssertionError` | `AssertionError` trực tiếp | `InvocationTargetException` chứa `AssertionError` |
| Call-site type không khớp handle | Có thể `WrongMethodTypeException`, chưa chạy target | Không có `invokeExact`; API phản chiếu kiểm tra đối số bằng quy tắc riêng |
| Đối số sai với `Method.invoke` | Handle có thể lỗi do kiểu/chuyển đổi trước target | `IllegalArgumentException` trực tiếp, không mặc định có wrapper |
| Tìm method sai tên/chữ ký | `Lookup.find...` có thể ném `NoSuchMethodException`/`IllegalAccessException` trước khi có handle | `Class.getMethod(...)` có thể ném `NoSuchMethodException` trước khi có `Method` |
| Kiểu kết quả | Xác định bởi `MethodType` và call-site descriptor | API trả `Object`; void target cho `null`; primitive return được boxing |
| Kiểm soát checked exception ở caller | API `invokeExact/invoke` khai báo `throws Throwable` | API `Method.invoke` khai báo `InvocationTargetException` và lỗi phản chiếu khác |
| Khi log lỗi nghiệp vụ | Ghi nhận throwable nguyên gốc; không unwrap một wrapper không tồn tại | Unwrap một lớp `InvocationTargetException` tại boundary phù hợp, giữ nguyên cause |

Cấu trúc này có tác động trực tiếp đến monitoring: cùng một lỗi nghiệp vụ có **top-level exception class** khác nhau tùy framework dùng MethodHandle hay core reflection. Nếu hệ thống đếm lỗi theo tên class trên cùng, reflection dễ gom nhiều lỗi thật dưới nhãn `InvocationTargetException`. Hãy nhóm theo **root/target cause có kiểm soát** và vẫn giữ thông tin về boundary gọi.

## 5. Ví dụ Java 17+ chạy độc lập: so sánh cả ba nhóm Throwable

Lưu file **`ThrowableCallDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ThrowableCallDemo {
    public static String work(String kind) throws IOException {
        switch (kind) {
            case "checked":
                throw new IOException("disk");
            case "runtime":
                throw new IllegalStateException("state");
            case "error":
                throw new AssertionError("assertion");
            default:
                return "ok:" + kind;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle handle = MethodHandles.lookup()
                .findStatic(ThrowableCallDemo.class, "work", type);
        Method reflected = ThrowableCallDemo.class.getMethod("work", String.class);

        System.out.println("handleType=" + handle.type());
        System.out.println("mh-ok=" + (String) handle.invokeExact("ready"));
        System.out.println("reflect-ok=" + reflected.invoke(null, "ready"));

        for (String kind : new String[]{"checked", "runtime", "error"}) {
            try {
                String ignored = (String) handle.invokeExact(kind);
            } catch (Throwable ex) {
                System.out.println("mh-" + kind + "="
                        + ex.getClass().getSimpleName() + ":" + ex.getMessage());
            }

            try {
                Object ignored = reflected.invoke(null, kind);
            } catch (InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                System.out.println("reflect-" + kind + "="
                        + ex.getClass().getSimpleName()
                        + ",cause=" + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }
        }

        try {
            Object wrongResult = handle.invokeExact("ready");
        } catch (WrongMethodTypeException ex) {
            System.out.println("mh-wrong-type=" + ex.getClass().getSimpleName());
        }
        try {
            reflected.invoke(null, 42);
        } catch (IllegalArgumentException ex) {
            System.out.println("reflect-bad-args=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 ThrowableCallDemo.java
java ThrowableCallDemo
```

**Stdout chính xác:**

```text
handleType=(String)String
mh-ok=ok:ready
reflect-ok=ok:ready
mh-checked=IOException:disk
reflect-checked=InvocationTargetException,cause=IOException:disk
mh-runtime=IllegalStateException:state
reflect-runtime=InvocationTargetException,cause=IllegalStateException:state
mh-error=AssertionError:assertion
reflect-error=InvocationTargetException,cause=AssertionError:assertion
mh-wrong-type=WrongMethodTypeException
reflect-bad-args=IllegalArgumentException
```

### 5.1. Vì sao hai đường gọi thành công đều giống nhau?

`work("ready")` trả `"ok:ready"`. Handle có kiểu `(String)String`. `Method.invoke(null, "ready")` nhận `null` receiver vì `work` là **static method**; giá trị trả về là `Object` chứa reference `String`, nên khi nối chuỗi vẫn hiển thị kết quả giống nhau.

### 5.2. Vì sao checked `IOException` đi trực tiếp qua handle?

Trong thân `work("checked")`, method ném `new IOException("disk")`. `invokeExact` không tạo `InvocationTargetException`; `catch (Throwable ex)` nhận chính `IOException`, vì vậy dòng `mh-checked=IOException:disk`. Reflection thì bắt `InvocationTargetException` ở vòng ngoài; cause là `IOException:disk`. Kết quả tương tự với `IllegalStateException` và `AssertionError`.

Đoạn demo **cố ý bắt `Throwable`** để quan sát cả checked exception, runtime exception và `Error` trong một vòng lặp. **Không sao chép chiến lược bắt rồi tiếp tục chạy này vào production**, đặc biệt với những `Error` nghiêm trọng hoặc lỗi khiến trạng thái ứng dụng không đáng tin.

### 5.3. Hai lỗi cuối không do thân `work` ném

- `Object wrongResult = handle.invokeExact("ready")` đặt kiểu kết quả của call site là `Object`, trong khi handle trả `String`. `invokeExact` yêu cầu kiểu chính xác nên ném `WrongMethodTypeException` trước khi đích thực thi. Nếu dùng `String result = (String) handle.invokeExact("ready")`, kiểu yêu cầu là `String` và call thành công.
- `reflected.invoke(null, 42)` truyền `Integer` khi phương thức đích khai báo `String`, nên reflection ném `IllegalArgumentException`. Không có `InvocationTargetException` vì đích không được chạy.

Đây là lý do **không phân loại lỗi chỉ bằng API đã gọi**. Hãy hỏi: lỗi phát sinh khi tìm method, khi kiểm tra/chuyển đổi kiểu, trong code của đích, hay tại lớp wrapper do ứng dụng xây thêm?

## 6. Nguồn lỗi: chia thành các pha rõ ràng

### 6.1. Pha A — Lookup và kiểm tra quyền

Ví dụ:

```java
MethodHandle handle = MethodHandles.lookup().findStatic(
        SomeClass.class,
        "operation",
        MethodType.methodType(String.class, String.class));
```

Đây là **đoạn minh họa**, `SomeClass` chỉ là tên tượng trưng. Lúc này chưa gọi target. Nếu method không tồn tại hoặc chữ ký không đúng, `Lookup` có thể ném `NoSuchMethodException`; nếu không đủ quyền, có thể ném `IllegalAccessException`. Khi một `Method` được lấy qua `Class.getMethod(...)`, việc resolve sai tên/chữ ký cũng ném `NoSuchMethodException` ngay tại bước lookup.

Những lỗi này thuộc **cấu hình, classpath, module/access hoặc cách tạo adapter**, không phải lỗi của lời gọi nghiệp vụ. Nên xác thực lúc khởi động và báo tên method cùng descriptor được yêu cầu.

### 6.2. Pha B — Kiểm tra call site, conversion và liên kết

Với method handle:

- `invokeExact` có thể ném `WrongMethodTypeException` nếu kiểu tham số/kiểu trả về tại nơi gọi không đúng.
- `invoke` hoặc handle đã được thích nghi bằng `asType` có thể ném `ClassCastException`, `NullPointerException`, `WrongMethodTypeException` hoặc lỗi liên quan tùy conversion và cách gọi.
- Nếu target chưa được thực thi, đây là lỗi tại ranh giới gọi. Đừng báo “method nghiệp vụ ném exception” khi thực chất adapter truyền sai kiểu.

Với `Method.invoke`:

- Truyền sai receiver, số lượng/kiểu đối số có thể gây `IllegalArgumentException`; receiver `null` khi gọi instance method có thể gây `NullPointerException`.
- Không đủ quyền truy cập gây `IllegalAccessException`.
- Static class initialization thất bại có thể gây `ExceptionInInitializerError`.

Những lỗi này thường xảy ra bên ngoài thân phương thức đích, nên không theo quy tắc bọc `InvocationTargetException` dành cho throwable **do chính đích ném**.

### 6.3. Pha C — Target thực sự chạy và ném Throwable

Trong pha này, khác biệt trung tâm mới phát huy:

- **MethodHandle:** throwable đi qua trực tiếp, trừ khi pipeline adapter do bạn tạo đã cố ý bắt/đổi nó.
- **Reflection:** `Method.invoke` trình bày throwable của target qua `InvocationTargetException`.

Một method target cũng có thể tự ném `ClassCastException`, `IllegalArgumentException` hoặc `WrongMethodTypeException`, vì đó đều là các type có thể ném từ code Java. Vì vậy muốn xác định nguồn khi type bị trùng, cần dựa trên **đường gọi, stack trace, bối cảnh và vị trí kiểm tra**. Ngoại lệ cùng class không nhất thiết xuất phát từ cùng pha.

## 7. Xử lý exception hợp lý trong adapter production

### 7.1. Giữ đúng hợp đồng checked exception

Giả sử một boundary có hợp đồng chỉ công khai `IOException`, trong khi handle gọi thực tế được cấu hình để thực hiện `String work(String) throws IOException`. Có thể chuyển `throws Throwable` về hợp đồng rõ hơn:

```java
static String viaHandle(MethodHandle handle, String key) throws IOException {
    try {
        return (String) handle.invokeExact(key);
    } catch (IOException expected) {
        throw expected;
    } catch (RuntimeException | Error unchecked) {
        throw unchecked;
    } catch (Throwable unexpectedChecked) {
        throw new IllegalStateException(
                "Unexpected checked Throwable from handle", unexpectedChecked);
    }
}
```

**Đây là method minh họa**, cần đặt trong class có import `MethodHandle` và `IOException`; không phải file độc lập. Nó giả định `handle.type()` là `(String)String`. Quy tắc:

1. Cho checked exception dự kiến (`IOException`) truyền nguyên vẹn.
2. Truyền runtime exception và `Error` ra ngoài, không che thành “lỗi I/O”.
3. Với một checked `Throwable` khác ngoài hợp đồng, bọc ở boundary theo chính sách rõ ràng và **giữ cause gốc**.

Một ứng dụng khác có thể chủ động công bố `throws Throwable`, định nghĩa exception miền riêng hoặc trả một kiểu `Result`; lựa chọn tùy contract. Nhưng đừng dùng `catch (Throwable ignored)` để biến mọi lỗi thành `null` hay một mã trạng thái thành công.

### 7.2. Bóc wrapper reflection đúng một lớp tại boundary

Với `Method` tương ứng, có thể viết:

```java
static String viaReflection(Method method, String key) throws IOException {
    try {
        return (String) method.invoke(null, key);
    } catch (InvocationTargetException wrapper) {
        Throwable cause = wrapper.getCause();

        if (cause instanceof IOException io) {
            throw io;
        }
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        if (cause instanceof Error error) {
            throw error;
        }
        throw new IllegalStateException(
                "Unexpected checked Throwable from target", cause);
    } catch (IllegalAccessException access) {
        throw new IllegalStateException("Cannot access target method", access);
    }
}
```

Đây là method minh họa trong class đã import `Method`, `InvocationTargetException` và `IOException`. Cần bảo đảm `method` là static method trả `String` nhận `String`, và đầu vào/đường gọi đã được xác thực. `IllegalArgumentException` do truyền sai đối số vẫn được ném trực tiếp, không chạy vào `catch (InvocationTargetException)`.

Tại boundary, việc unwrap đúng `InvocationTargetException` giúp chính sách lỗi xử lý cùng một `IOException` như bên method handle. Nếu catch/rethrow cause mà không đổi object, stack trace của cause vẫn mô tả vị trí gốc; nếu đổi sang exception khác, hãy truyền cause vào constructor để bảo toàn thông tin.

### 7.3. Không unwrap vô điều kiện mọi `cause`

Nên hỏi **wrapper được tạo bởi API nào?**

- `InvocationTargetException` đến từ `Method.invoke` là wrapper chuẩn của core reflection cho lỗi target.
- `CompletionException` và `ExecutionException` có hợp đồng wrapper riêng trong xử lý bất đồng bộ.
- `UndeclaredThrowableException` có thể phát sinh ở proxy khi một checked throwable không được khai báo trong interface.
- `InvocationTargetException` cũng có thể **do chính code nghiệp vụ ném**. Nếu một method handle gọi target vốn ném `InvocationTargetException`, caller handle nhận chính loại đó; không có bằng chứng API method handle đã tự bọc.
- Framework hoặc callback có thể chủ động thêm wrapper. Phải kiểm tra hợp đồng của tầng đó trước khi chọn cách unwrap.

Tránh vòng lặp “bóc `getCause()` đến tận cùng” mà không giữ thông tin boundary: các lớp wrapper đôi khi chứa ngữ cảnh nghiệp vụ cần thiết. Ưu tiên unwrap ở nơi bạn biết chính xác nguồn wrapper và ghi đủ thông tin chẩn đoán.

### 7.4. Bảo toàn thông tin khi log và chuyển lỗi

Thông thường một log đủ ích lợi nên mô tả:

- tên module/class/method và `handle.type()` hoặc method signature;
- input context an toàn (ID request, loại thao tác), không ghi bí mật hoặc dữ liệu nhạy cảm;
- **loại throwable thực** và thông điệp, kể cả `cause` sau khi unwrap reflection;
- stack trace của throwable gốc, các wrapper liên quan và thời điểm xảy ra lỗi (lookup, adaptation hay target).

Nếu chuyển checked exception thành exception không kiểm tra, dùng constructor nhận cause, ví dụ `new IllegalStateException("Invocation failed", original)`. Không tạo `new RuntimeException(original.getMessage())` rồi vứt mất stack trace gốc. Không dựa chỉ vào `InvocationTargetException.getMessage()` vì nhiều wrapper không có detail message hữu ích.

Trong môi trường có retry, phân biệt **lỗi nghiệp vụ có thể retry** (ví dụ I/O tạm thời) với **lỗi cấu hình/kiểu không thể tự hồi phục** (sai method signature, thiếu quyền) để tránh retry vô hạn.

## 8. Những trường hợp đặc biệt

### 8.1. `Error` và throwable nguy hiểm

Ví dụ dùng `AssertionError` để kiểm tra cơ chế bọc mà không làm hỏng JVM. Trong thực tế, `OutOfMemoryError`, `StackOverflowError` và các lỗi runtime nghiêm trọng không nên bị nuốt chỉ để “không làm gián đoạn request”. `catch (Throwable)` ở boundary có thể cần cho cleanup/telemetry cực kỳ cẩn thận nhưng thông thường phải rethrow theo chính sách phù hợp.

### 8.2. Đích ném checked exception mà người gọi không khai báo

Method handle cho phép một target có thể ném checked exception vì `invokeExact/invoke` khai báo `throws Throwable`. Điều đó không đồng nghĩa mọi tầng bên ngoài đều được phép tùy ý ném checked exception không có trong hợp đồng Java. Ở adapter với signature chặt hơn, hãy bắt, khai báo hoặc chuyển lỗi một cách có chủ đích và bảo toàn cause.

Với reflection, compiler cũng không tự suy ra `IOException` từ đối tượng `Method`: caller chỉ thấy các checked exceptions của `Method.invoke`, trong đó có `InvocationTargetException`, rồi tự giải quyết cause theo hợp đồng ứng dụng.

### 8.3. Method handle lấy từ reflection

`lookup.unreflect(method)` tạo một handle tương ứng với `Method` theo quyền truy cập. **Lúc gọi handle được tạo thành công**, nó dùng semantics invocation của **method handle**, không tự động thừa hưởng wrapper `InvocationTargetException` của `Method.invoke`. Nhưng bản thân target có thể chủ động ném exception kiểu đó, và quá trình `unreflect` có thể gặp lỗi quyền truy cập riêng.

### 8.4. Proxy hoặc framework có thể thêm wrapper của riêng mình

Khi lời gọi đi qua dynamic proxy, interceptor, transaction layer hoặc async layer, exception có thể được biến đổi theo hợp đồng của từng lớp. Ví dụ JDK dynamic proxy có thể bọc một checked exception chưa khai báo trong `UndeclaredThrowableException`. Đây là **một lớp khác** với `Method.invoke` và không làm thay đổi nguyên tắc method handle chuẩn truyền lỗi target trực tiếp.

### 8.5. Khi target trả về bình thường

Với target trả về `void`, `Method.invoke` trả `null`; method handle có signature trả `void` yêu cầu caller sử dụng nó theo contract call-site tương ứng, không ép kiểu kết quả thành `Object` tại `invokeExact`. Nếu target chạy xong bình thường, không có exception để truyền hay bọc. Tránh nhầm việc `Method.invoke` boxing/đóng gói giá trị trả về với việc **bọc exception**: đó là hai cơ chế khác nhau.

## 9. Checklist khi debug một lỗi invocation

1. **Đã tìm được target chưa?** Nếu chưa, kiểm tra tên method, `MethodType`, receiver, module access và các exception lookup.
2. **Call-site có khớp không?** Đối với `invokeExact`, kiểm tra kiểu tĩnh của tham số và **kiểu kết quả** tại biểu thức gọi, rồi đối chiếu `handle.type()`.
3. **Target đã chạy chưa?** Nếu không, xem lại conversion/bounds/access hoặc exception khi khởi tạo class.
4. **Lời gọi dùng API nào?** `MethodHandle.invokeExact/invoke` hay `Method.invoke`? Chỉ giải `InvocationTargetException` khi đúng boundary reflection hoặc wrapper đó được tạo có chủ ý.
5. **Có exception gốc trong cause không?** Nếu reflection wrapper, lấy `getCause()`, giữ stack trace; nếu handle, thường bắt trực tiếp throwable target.
6. **Lỗi được phân loại đúng chưa?** Checked domain error, runtime programming error, `Error`, lookup failure và conversion failure có chính sách khác nhau.
7. **Có lớp framework nào thay đổi lỗi không?** Proxy, asynchronous execution hoặc adapter có thể thêm wrapper; đừng quy mọi wrapper cho method handle.
8. **Có mất thông tin không?** Tránh bỏ `cause`, thay stack trace bằng message, log lặp ở mọi layer hoặc làm rò rỉ dữ liệu nhạy cảm.

## 10. Sai lầm thường gặp

- **“MethodHandle lúc nào cũng ném `InvocationTargetException` giống reflection.”** Sai. Handle chuẩn truyền throwable của target trực tiếp.
- **“`throws Throwable` nghĩa là mọi lỗi đều được wrap trong `Throwable`.”** Sai. Đây là khai báo khả năng ném, không phải một hành động bọc lỗi.
- **“`Method.invoke` chỉ wrap checked exception.”** Sai. Nó cũng bọc unchecked exception và `Error` do target ném.
- **“Bất cứ lỗi nào khi `Method.invoke` đều là `InvocationTargetException`.”** Sai. Sai argument, receiver, quyền truy cập hoặc class initialization có đường lỗi riêng.
- **“`WrongMethodTypeException` chắc chắn do nghiệp vụ ném.”** Sai. Nó thường báo mismatch giữa call site và handle trước khi target chạy, dù code target cũng có thể tự ném loại này.
- **“Chỉ cần log tên lớp `InvocationTargetException`.”** Không đủ. Cần cause thực và ngữ cảnh lời gọi.
- **“Có thể bắt `Throwable` và bỏ qua cho ứng dụng chạy tiếp.”** Nguy hiểm. Điều này có thể che `Error` nghiêm trọng và khiến dữ liệu sai trạng thái.
- **“Cứ unwrap đến root cause là luôn đúng.”** Không hẳn. Các wrapper có thể ghi nhận ngữ cảnh quan trọng, và không phải mọi `cause` là một wrapper thuần kỹ thuật.
- **“Đổi sang `Lookup.unreflect` vẫn giữ semantics của `Method.invoke`.”** Sai. Handle thu được hoạt động theo phương thức gọi method handle, còn exception liên quan lookup/access là một pha khác.

## 11. Bài tập và đáp án

### Bài 1 — Dự đoán exception

Một method đích ném `new java.io.FileNotFoundException("missing")`. Caller dùng `invokeExact` có kiểu call site đúng và target đã chạy; caller còn lại dùng `Method.invoke`.

**Đáp án:** Caller handle nhận `FileNotFoundException` trực tiếp. Caller reflection nhận `InvocationTargetException` với `getCause()` là `FileNotFoundException`. `FileNotFoundException` là một checked exception con của `IOException`.

### Bài 2 — Xác định pha lỗi

Handle có kiểu `(String)String`; code viết `Object result = handle.invokeExact("x");` và gặp `WrongMethodTypeException` dù target không có lỗi.

**Đáp án:** Kiểu kết quả tại call site là `Object`, khác `String`. Lỗi phát sinh ở bước kiểm tra signature **trước khi target chạy**. Sửa thành `String result = (String) handle.invokeExact("x");` nếu đúng với contract thực của handle.

### Bài 3 — Reflection bọc hay không?

Khi `method.invoke(null, Integer.valueOf(3))` gọi method chỉ nhận `String` thì gặp `IllegalArgumentException`. Có nên truy `((InvocationTargetException) ex).getCause()` không?

**Đáp án:** Không. `IllegalArgumentException` ở đây đến từ API reflection khi kiểm tra argument. Không phải `InvocationTargetException`; cast như vậy sẽ sai.

### Bài 4 — Thiết kế adapter

Một service công khai `String load(String key) throws IOException` nhưng bên dưới gọi handle. Hãy viết adapter để:
- cho `IOException` truyền nguyên vẹn;
- không nuốt `RuntimeException` và `Error`;
- chuyển checked `Throwable` khác sang một exception có ngữ cảnh và giữ nguyên cause.

**Gợi ý:** Dùng mẫu `viaHandle` ở mục 7.1. Viết thêm một integration test có target ném `IOException` và một test cho call-site mismatch.

### Bài 5 — Tìm root cause không mất context

Một framework dùng reflection, catch `InvocationTargetException` rồi ném `new RuntimeException("failed")`. Vì sao việc debug khó hơn?

**Đáp án:** Framework đã đánh rơi `getCause()`, gồm kiểu lỗi thật, message và stack trace gốc. Cần ít nhất dùng `new RuntimeException("failed", wrapper.getCause())`, đồng thời giữ thông tin method/cấu hình trong message hoặc structured log.

## Tài liệu chính thức

- [Java SE 17 — MethodHandle: invokeExact, invoke và Exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — java.lang.reflect.Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java SE 17 — Throwable và cause chaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)

## Kết luận

**MethodHandle** gọi đích với semantics truyền `Throwable` trực tiếp: checked exception, unchecked exception và `Error` của target đi ra caller không có wrapper `InvocationTargetException` mặc định. **Core reflection** dùng `Method.invoke` để bọc throwable do target ném trong `InvocationTargetException`; caller truy xuất lỗi gốc bằng `getCause()`. Khi xây dựng framework hoặc adapter, hãy phân loại **lookup → conversion/call-site → target**, bảo toàn cause/stack trace và áp dụng chính sách checked exception đúng hợp đồng thay vì gom mọi lỗi invocation vào một nhóm.
