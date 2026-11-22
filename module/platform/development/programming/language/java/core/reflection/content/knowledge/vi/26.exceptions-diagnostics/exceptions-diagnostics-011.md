# Phân biệt lỗi ở công cụ Reflection với lỗi trong mã đích (Java)

## 1. Vì sao phải phân biệt hai nguồn lỗi?

Với Java Reflection, lời gọi nhìn giống `method.invoke(receiver, args)` nhưng thực tế trải qua hai lớp xử lý:

1. **Lớp hạ tầng Reflection**: tìm `Class`, tìm metadata của field/method/constructor, kiểm tra đối tượng nhận, quyền truy cập, số lượng và kiểu đối số, rồi điều phối lời gọi.
2. **Mã đích (target)**: thân method hoặc constructor được chạy và có thể trả kết quả hay ném exception/error vì chính logic nghiệp vụ.

Nếu lỗi xảy ra ở bước chuẩn bị/kiểm tra của Reflection, API thường ném **trực tiếp** exception tương ứng, như `NoSuchMethodException`, `IllegalAccessException` hoặc `IllegalArgumentException`. Nếu lời gọi đã vào thân method/constructor rồi mã đích ném ra `Throwable`, các API `Method.invoke` và `Constructor.newInstance` thường bọc lỗi đó trong **`InvocationTargetException`**.

Ví dụ hai trường hợp nhìn gần giống:

```java
// Sai số kiểu đối số: lỗi do Reflection kiểm tra trước lời gọi.
method.invoke(target, 123); // Nếu method nhận String: IllegalArgumentException.

// Kiểu đối số đúng nhưng bên trong method lại ném IllegalArgumentException.
// Kết quả của Method.invoke là InvocationTargetException;
// getCause() là IllegalArgumentException của chính method đích.
method.invoke(target, "invalid");
```

Đây là **mảnh code minh họa**; `method` và `target` phải được khai báo trong chương trình cụ thể. Không thể kết luận nguồn lỗi chỉ bằng từ khóa `IllegalArgumentException` trong log: cần xem **exception lớp ngoài, cause và giai đoạn xử lý**.

## 2. Sơ đồ luồng lỗi

```text
Class / tên thành viên / tham số
              |
              v
 [Reflection: tra cứu member]
      |                 |
   thất bại          tìm thấy
      |                 |
NoSuchMethodException  v
NoSuchFieldException   [Kiểm tra quyền, receiver, đối số]
                              |                 |
                           thất bại          hợp lệ
                              |                 |
                    IllegalAccessException     v
                    IllegalArgumentException [Khởi tạo lớp nếu cần]
                    NullPointerException       |
                                             [Chạy mã đích]
                                              /         \
                                        trả về         ném Throwable
                                          |                  |
                                      kết quả      InvocationTargetException
                                                        |
                                                    getCause()
                                                        |
                                                Throwable của mã đích
```

Sơ đồ là luồng **điển hình**, không phải danh sách đầy đủ mọi lỗi JVM. Đặc biệt, class initialization và linkage có thể thất bại trước khi thân method chạy; một số `Error` như `ExceptionInInitializerError` hoặc `LinkageError` có thể xuất hiện trực tiếp mà không qua `InvocationTargetException`. Do đó, đừng viết một khối `catch (InvocationTargetException)` rồi coi nó bao phủ mọi kiểu thất bại của Reflection.

## 3. Bảng phân loại theo nguồn phát sinh

| Dấu hiệu thấy được | Nơi phát sinh thường gặp | Cách hiểu/chẩn đoán |
|---|---|---|
| `ClassNotFoundException` | `Class.forName(name)` khi không tải được class theo tên | Tên/loader/classpath không tìm được lớp, chưa phải mã nghiệp vụ đích |
| `NoSuchMethodException` | `Class.getMethod`, `getDeclaredMethod`, `getConstructor`, `getDeclaredConstructor` | Không tìm được method/constructor theo phạm vi và danh sách **kiểu tham số** |
| `NoSuchFieldException` | `Class.getField` / `getDeclaredField` | Không tìm được field theo tên và phạm vi tra cứu |
| `IllegalAccessException` | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | Reflection tìm được metadata nhưng không có quyền thực hiện thao tác |
| `InaccessibleObjectException` | Ví dụ `AccessibleObject.setAccessible(true)` khi module không mở package thích hợp | Từ chối mở quyền truy cập sâu; đây là runtime exception của cơ chế truy cập |
| `IllegalArgumentException` trực tiếp | `Method.invoke` khi receiver không tương thích, sai số/kiểu đối số; `Field.get/set` dùng receiver/value không hợp lệ | Lỗi trong bước kiểm tra/call contract của Reflection |
| `NullPointerException` trực tiếp | `Method.invoke` trên instance method với receiver `null`; hoặc đối số bắt buộc của một API Reflection là `null` | Lỗi trước khi chạy thân method, tùy API và vị trí null |
| `InvocationTargetException` | `Method.invoke` hoặc `Constructor.newInstance` **sau khi mã đích ném lỗi** | Wrapper hạ tầng: dùng `getCause()` để nhận `Throwable` thực sự |
| `ExceptionInInitializerError` | Khởi tạo lớp thất bại do initializer ném exception không phải `Error` | Lỗi giai đoạn class initialization; có thể xảy ra trước thân method |
| `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError` | Class/linkage/runtime binary compatibility | Là `Error` cấp JVM; **khác** checked lookup exception có tên gần giống |
| `UndeclaredThrowableException` | Chẳng hạn dynamic proxy nhận checked exception từ `InvocationHandler` nhưng interface method không khai báo tương thích | Đặc thù cơ chế lời gọi JDK proxy; không phải wrapper mặc định của `Method.invoke` |

**Lưu ý:** `IllegalArgumentException`, `NullPointerException` hay `AssertionError` cũng có thể được **mã đích chủ động ném**. Trong trường hợp đó, khi gọi qua `Method.invoke`, chúng thường nằm **bên trong `InvocationTargetException.getCause()`**; không được phân loại đơn giản theo tên loại lỗi.

## 4. Hai giai đoạn dễ nhầm: tra cứu metadata và thực thi

Tra cứu:

```java
Class<?> type = Class.forName("java.lang.String");
java.lang.reflect.Method method = type.getMethod("substring", int.class);
```

Hai lời gọi trên tìm lớp và lấy metadata. Chúng **không chạy** thân `String.substring(...)`. Tên sai hoặc chữ ký không đúng có thể dẫn đến `ClassNotFoundException` hay `NoSuchMethodException`. Với `getDeclaredMethod`, không nên nhầm “declared” với “public”: nó chỉ tìm trong chính lớp đó và có thể tìm thấy thành viên private, nhưng tìm được chưa có nghĩa được phép gọi.

Thực thi:

```java
Object result = method.invoke("abcd", 2);
System.out.println(result); // cd
```

`Method.invoke` kiểm tra receiver và kiểu tham số, sau đó mới chạy thân method. Với method không có tham số có thể gọi `invoke(receiver)`. Với static method, đối số receiver của `invoke` có thể là `null`. Với instance method, receiver phải là một instance hợp lệ và không được null.

Với constructor, dùng `getDeclaredConstructor`/`getConstructor` để lấy metadata và `Constructor.newInstance(args)` để chạy thân constructor. `Class.newInstance()` đã deprecated và không có cùng hợp đồng bọc exception như `Constructor.newInstance()`; tránh dùng nó trong code mới.

## 5. Ví dụ Java 17+ hoàn chỉnh: từng nguồn lỗi được tách rõ

Tạo file **`ReflectionFaultsDemo.java`** chứa cả hai top-level class sau (chỉ `ReflectionFaultsDemo` là `public`):

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFaultsDemo {
    static class Broken {
        static int value = crash();
        static int crash() { throw new IllegalStateException("init failed"); }
        public static void ping() {}
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Target> type = Target.class;
        Target instance = new Target("ok");
        try {
            type.getMethod("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("lookup: " + e.getClass().getSimpleName());
        }

        Method hidden = type.getDeclaredMethod("hidden");
        try {
            hidden.invoke(instance);
        } catch (IllegalAccessException e) {
            System.out.println("access: " + e.getClass().getSimpleName());
        }

        Field secret = type.getDeclaredField("secret");
        try {
            secret.get(instance);
        } catch (IllegalAccessException e) {
            System.out.println("field access: " + e.getClass().getSimpleName());
        }

        Method greet = type.getMethod("greet", String.class);
        try {
            greet.invoke(instance, 42);
        } catch (IllegalArgumentException e) {
            System.out.println("wrong argument: " + e.getClass().getSimpleName());
        }

        try {
            greet.invoke(null, "Lan");
        } catch (NullPointerException e) {
            System.out.println("null receiver: " + e.getClass().getSimpleName());
        }

        System.out.println("success: " + greet.invoke(instance, "Lan"));

        for (String name : new String[]{"unchecked", "checked", "fatal"}) {
            try {
                type.getMethod(name).invoke(instance);
            } catch (InvocationTargetException e) {
                System.out.println(name + " target: " + e.getCause().getClass().getSimpleName());
            }
        }

        Constructor<Target> constructor = type.getConstructor(String.class);
        try {
            constructor.newInstance("bad");
        } catch (InvocationTargetException e) {
            System.out.println("constructor target: " + e.getCause().getClass().getSimpleName());
        }

        Class<?> broken = Class.forName(
            ReflectionFaultsDemo.Broken.class.getName(),
            false,
            ReflectionFaultsDemo.class.getClassLoader()
        );
        try {
            broken.getMethod("ping").invoke(null);
        } catch (ExceptionInInitializerError e) {
            System.out.println("initialization: " + e.getClass().getSimpleName());
        }
    }
}

class Target {
    private String secret = "hidden";

    public Target(String value) {
        if ("bad".equals(value)) {
            throw new IllegalStateException("constructor failed");
        }
    }
    private void hidden() {}
    public String greet(String name) { return "Hello, " + name; }
    public void unchecked() { throw new IllegalStateException("target bug"); }
    public void checked() throws IOException { throw new IOException("target IO"); }
    public void fatal() { throw new AssertionError("target error"); }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac ReflectionFaultsDemo.java
java ReflectionFaultsDemo
```

Stdout đã được kiểm tra:

```text
lookup: NoSuchMethodException
access: IllegalAccessException
field access: IllegalAccessException
wrong argument: IllegalArgumentException
null receiver: NullPointerException
success: Hello, Lan
unchecked target: IllegalStateException
checked target: IOException
fatal target: AssertionError
constructor target: IllegalStateException
initialization: ExceptionInInitializerError
```

### Phân tích kết quả theo giai đoạn

1. `getMethod("missing")` thất bại ngay khi **lookup** vì `Target` không có public method tương ứng, nên trả trực tiếp `NoSuchMethodException`.
2. `hidden` và `secret` thực sự tồn tại, vì `getDeclaredMethod` / `getDeclaredField` tìm được. Tuy nhiên, chúng là private members của **top-level class `Target` độc lập**; truy cập từ `ReflectionFaultsDemo` không được phép, nên `Method.invoke` và `Field.get` ném trực tiếp `IllegalAccessException`. Nếu chuyển `Target` thành nested class cùng nest với caller, kết quả quyền truy cập có thể khác.
3. `greet(String)` tồn tại nhưng truyền `42` (an `int` boxed thành `Integer`) không phù hợp với `String`. Reflection ném trực tiếp `IllegalArgumentException` trước khi chạy `Target.greet`.
4. Receiver `null` của `greet(String)` là không hợp lệ vì đây là instance method. `Method.invoke` ném trực tiếp `NullPointerException`. Nếu một **static** method được gọi bằng `invoke(null, ...)` thì tình huống khác.
5. Với receiver và argument hợp lệ, `greet` chạy bình thường và kết quả trả về qua `invoke`.
6. Các method `unchecked()`, `checked()`, `fatal()` cố ý ném `IllegalStateException`, `IOException` và `AssertionError`. `Method.invoke` bọc **cả runtime exception, checked exception và Error từ thân method đích** trong `InvocationTargetException`; `getCause()` cho ra đúng kiểu gốc.
7. Thân constructor `Target("bad")` ném `IllegalStateException`; `Constructor.newInstance` cũng bọc lỗi đích trong `InvocationTargetException`.
8. `Broken` được lấy `Class` với `initialize=false`, rồi gọi static method qua Reflection. Trước khi thân `ping` chạy, JVM phải khởi tạo lớp; initializer thất bại nên ném **`ExceptionInInitializerError`**. Đây là lỗi khởi tạo lớp, không phải method `ping` ném `InvocationTargetException`.

Ví dụ sử dụng Java syntax tương thích Java 17+ và đã chạy thành công. Nó không gọi `setAccessible(true)` vì mục tiêu là quan sát rõ ranh giới quyền truy cập của Reflection.

## 6. Cách đọc InvocationTargetException đúng cách

`InvocationTargetException` là một **checked exception của lớp Reflection**, nhưng nội dung quan trọng thường nằm trong `getCause()` (tương đương `getTargetException()` theo API cũ):

```java
try {
    Object result = method.invoke(receiver, arguments);
    // Chỉ tới đây khi method đích hoàn tất bình thường.
} catch (InvocationTargetException e) {
    Throwable original = e.getCause();
    // original xuất phát từ method đích.
    throw new IllegalStateException("Target method failed", original);
} catch (IllegalAccessException e) {
    // Lỗi quyền truy cập từ Reflection.
    throw new IllegalStateException("Cannot invoke the target method", e);
} catch (IllegalArgumentException e) {
    // Có thể là receiver/arguments không hợp lệ ở tầng Reflection.
    throw new IllegalArgumentException("Invalid reflective invocation", e);
}
```

Đây là **mảnh code minh họa** trong một phương thức có quyền throw runtime exceptions; `method`, `receiver`, `arguments` phải được định nghĩa. Nếu `original` là `InterruptedException`, `IOException` hoặc exception nghiệp vụ được phép xử lý tường minh, hãy xử lý đúng hợp đồng thay vì gộp tất cả vào một runtime exception.

**Không nên** log duy nhất `e.getMessage()`: wrapper có thể không nêu được nguyên nhân nghiệp vụ. Khi log, giữ stack trace của `cause`, tên operation, signature, target class và request/correlation ID phù hợp. Không in raw arguments chứa mật khẩu, access token hay dữ liệu nhạy cảm.

### Khi cần chuyển tiếp ngoại lệ gốc

Ở một API đã khai báo checked exception cụ thể, có thể gỡ `InvocationTargetException` rồi ném lại đúng loại: chẳng hạn `if (cause instanceof IOException io) throw io;` trong method có `throws IOException`. Với `RuntimeException` hoặc `Error`, quyết định truyền tiếp theo hợp đồng của tầng gọi; với checked exception bất ngờ, tạo wrapper **giữ cause**. Cách nhận diện từng kiểu và chính sách giữ stack trace được minh họa sâu ở bài về `InvocationTargetException` (hàng 299). Ở bài này, điều quan trọng là xác nhận mã đích **đã chạy** trước khi phân loại lỗi.

## 7. Field.get/set và method/constructor invoke không có cùng hành vi

Một trường hợp dễ sai là nghĩ *mọi* thao tác Reflection đều bọc lỗi mã đích trong `InvocationTargetException`. Thực tế:

- `Field.get(target)` / `Field.set(target, value)` chủ yếu kiểm tra quyền truy cập, receiver và kiểu dữ liệu rồi đọc/ghi field; chúng **không gọi thân method nghiệp vụ**, nên không có quy tắc bọc “exception của thân method” như `Method.invoke`.
- `Class.getMethod/getDeclaredMethod/getField/getDeclaredField` là các thao tác metadata lookup: có thể ném checked lookup exception nhưng **chưa gọi target method/constructor**.
- `Method.invoke` chạy thân method sau kiểm tra. Nếu chính thân method ném `Throwable`, thường nhận `InvocationTargetException`.
- `Constructor.newInstance` thực thi constructor. Nếu thân constructor ném exception/error, cũng thường nhận `InvocationTargetException`.
- `MethodHandles.Lookup`, `MethodHandle.invoke/invokeExact` và invocation trực tiếp có **hợp đồng khác**. Chẳng hạn exception từ target của `MethodHandle` không mặc định bị bọc bởi `InvocationTargetException`. Không áp quy tắc của `Method.invoke` cho toàn bộ Java invocation API.

Trước khi quyết định catch kiểu gì, phải đọc đúng API cụ thể đang được gọi và giai đoạn phát sinh lỗi.

## 8. Phân biệt lỗi trước khi mã đích chạy

Ngoài kiểm tra quyền và đối số, JVM có thể thất bại ở giai đoạn **tải, liên kết hoặc khởi tạo lớp**, trước khi method/constructor body chạy. Các tín hiệu quan trọng:

| Tín hiệu | Nơi kiểm tra trước |
| --- | --- |
| `ClassNotFoundException` | Tên binary, class loader và classpath của thao tác tìm class theo tên |
| `NoClassDefFoundError` | Dependency thiếu khi linkage, hoặc lần khởi tạo class trước đã thất bại |
| `ExceptionInInitializerError` | Cause gốc trong static initializer; đừng gộp vào `InvocationTargetException` của mã đích |
| `NoSuchMethodError`, `NoSuchFieldError`, `UnsupportedClassVersionError` | Class file và phiên bản phụ thuộc không tương thích runtime |

`Class.forName(name, false, loader)` có thể trì hoãn initialization lúc khám phá metadata, nhưng một lời gọi static sau đó vẫn có thể kích hoạt initializer và gặp lỗi. Bài 294 phân tích loading/linking và bài 300 phân tích riêng lỗi class initialization; bảng này dùng để **xác định tầng lỗi** trong luồng điều tra tổng hợp.

## 9. Trường hợp đặc biệt: JDK dynamic proxy và InvocationHandler

Trong `java.lang.reflect.Proxy`, lời gọi interface được chuyển vào `InvocationHandler.invoke`. Một handler có thể dùng Reflection để gọi target:

```java
// Mảnh code minh họa trong một InvocationHandler.
// targetMethod, realTarget và args do handler quản lý.
try {
    return targetMethod.invoke(realTarget, args);
} catch (InvocationTargetException e) {
    throw e.getCause(); // InvocationHandler.invoke cho phép throws Throwable.
}
```

Nếu handler không gỡ wrapper, client có thể nhìn thấy `InvocationTargetException` hoặc một wrapper khác phát sinh khi proxy cần áp quy tắc checked exceptions. Vì vậy một handler forwarding điển hình **unwrap `InvocationTargetException`** để đưa exception thực của target trở lại cơ chế dispatch proxy.

Với JDK dynamic proxy:

- Một checked exception do `InvocationHandler.invoke` ném ra mà **không phù hợp với `throws` của method interface** có thể được bọc trong `UndeclaredThrowableException`.
- Runtime exception và `Error` không cần được khai báo qua `throws`.
- Exception nhìn thấy ở client còn phụ thuộc implementation handler/framework và những lớp interception xếp chồng.

Không nhầm `UndeclaredThrowableException` với `InvocationTargetException`: cái đầu thuộc hợp đồng **proxy dispatch đối với checked exception không khai báo**, cái sau thuộc hợp đồng **Method.invoke/Constructor.newInstance khi mã đích ném lỗi**.

## 10. Quy trình chẩn đoán theo sự kiện

### Bước 1 — Xác định thao tác gây lỗi

Ghi tên API đang gọi: `Class.forName`, `getDeclaredMethod`, `Method.invoke`, `Field.get`, `Constructor.newInstance` hoặc `InvocationHandler.invoke`. Không chỉ dựa vào “stack trace có `java.lang.reflect`”.

### Bước 2 — Quan sát outer exception và chuỗi cause

- Nếu outer là `InvocationTargetException`, xem `getCause()` đầu tiên.
- Nếu outer là `IllegalAccessException` hoặc `IllegalArgumentException` ném trực tiếp từ invocation, kiểm tra quyền, receiver, parameter count/types.
- Nếu là `ExceptionInInitializerError` hoặc `LinkageError`, phân tích class init/dependency trước khi quy lỗi cho body.
- Nếu qua nhiều framework/proxy, có thể có nhiều tầng wrapper. Theo chuỗi `getCause()` một cách có giới hạn và có cơ chế chống vòng lặp.

### Bước 3 — So sánh actual với expected metadata

```java
System.out.println(method.toGenericString());
System.out.println(java.util.Arrays.toString(method.getParameterTypes()));
System.out.println(method.getDeclaringClass().getName());
```

Đây là **mảnh code minh họa**: `method` phải tồn tại trong ngữ cảnh. Có thể bổ sung loại và class loader của receiver, không log object hoặc tham số nhạy cảm. Lưu ý Reflection metadata có thể biểu thị bridge/synthetic method do compiler sinh ra.

### Bước 4 — Chọn hành động đúng với lỗi

| Nguồn lỗi | Hướng xử lý |
|---|---|
| Lookup: tên hoặc signature không khớp | Sửa tên, parameter classes, thứ tự, overload; chọn `get...` hay `getDeclared...` đúng phạm vi |
| Access: visibility hoặc JPMS | Dùng API public, điều chỉnh thiết kế/module exports/opens một cách có chủ đích |
| Invocation arguments: receiver/arity/types sai | Sửa đối tượng và argument list, bao gồm primitive/wrapper/varargs |
| Target exception từ `getCause()` | Xử lý theo hợp đồng nghiệp vụ, giữ cause và stack trace |
| Initialization/linkage | Sửa lỗi static initialization hoặc dependency/runtime version |
| Proxy wrappers | Xem handler, declared exceptions và lớp interception thực tế |

**Bước 5 — Test đúng cả hai đường đi.** Viết riêng test cho tình huống Reflection có metadata/arguments không hợp lệ và test target chủ động ném lỗi. Assert **outer exception và cause**; đừng chỉ so sánh chuỗi message vì message phụ thuộc implementation và môi trường.

## 11. Những lỗi phổ biến khi xử lý exception Reflection

1. **`catch (Exception ignored)` rồi trả `null`:** làm mất lỗi cấu hình và stack trace; ứng dụng sau đó có thể ném `NullPointerException` ở chỗ hoàn toàn khác.
2. **Bắt `IllegalArgumentException` và kết luận target sai:** nếu nó được ném trực tiếp từ `Method.invoke` thì thường là receiver/argument sai; nếu nó nằm trong `InvocationTargetException.getCause()` thì mới là lỗi target.
3. **Bắt mọi `InvocationTargetException` thành “Reflection bị hỏng”:** exception này thường chỉ báo **mã đích đã được gọi và ném lỗi**.
4. **Bỏ cause khi đổi exception:** `throw new RuntimeException("failed")` không giữ nguyên nguồn lỗi; dùng constructor nhận `cause` hoặc rethrow có chủ đích.
5. **Lẫn checked exception và `Error`:** `catch (Exception)` không bao `Error`; không nuốt `OutOfMemoryError`, `LinkageError` hoặc các lỗi JVM nặng bằng xử lý fallback chung.
6. **Cố gọi private method bằng `setAccessible(true)` vô điều kiện:** module mạnh có thể từ chối, và việc mở truy cập sâu có thể vi phạm thiết kế encapsulation.
7. **Đánh đồng proxy dispatch với Reflection invoke:** `UndeclaredThrowableException` không phải kết quả mặc định của mọi `Method.invoke`.
8. **Dựa vào chỉ một dòng log:** ưu tiên outer class, cause chain, operation, target metadata và thời điểm xảy ra lỗi.

## 12. Tự kiểm tra

1. `type.getMethod("run")` không tìm được method public `run()` thì exception chính là gì? — `NoSuchMethodException`, ở giai đoạn tra cứu.
2. `method.invoke(target, wrongArg)` với kiểu argument không hợp lệ? — Thường `IllegalArgumentException` **trực tiếp** từ Reflection.
3. `method.invoke(target)` gọi vào thân method và thân ném `IOException`? — `InvocationTargetException`; `getCause()` là `IOException`.
4. Nếu thân method ném `AssertionError`? — Nó vẫn có thể được `Method.invoke` bọc trong `InvocationTargetException`; kiểm tra `cause`.
5. `Field.get(receiver)` bị từ chối vì field private? — `IllegalAccessException` trực tiếp, không cần `InvocationTargetException`.
6. Static initializer thất bại trước thân method? — Có thể `ExceptionInInitializerError` trực tiếp; xử lý lỗi khởi tạo.
7. `NoSuchMethodError` có giống `NoSuchMethodException` không? — Không; một bên là `LinkageError`, một bên là checked Reflection lookup exception.

## 13. Ghi nhớ

- **Phân loại theo giai đoạn**: lookup, access/argument checks, class initialization/linkage, rồi mới tới thân method/constructor.
- **Phân loại theo lớp ngoài và `cause`**: `InvocationTargetException` là wrapper; `getCause()` thường cho biết exception của chính mã đích.
- **Không mọi lỗi Reflection đều được bọc**: `NoSuchMethodException`, `IllegalAccessException`, `IllegalArgumentException` và nhiều JVM `Error` có thể đi trực tiếp.
- **API khác nhau có hợp đồng khác nhau**: `Field.get`, `Method.invoke`, `Constructor.newInstance`, `MethodHandle` và dynamic proxy không hoàn toàn giống nhau.
- **Giữ ngữ cảnh chẩn đoán**: operation + signature + class/loader + cause chain, cùng cách xử lý riêng cho lỗi hạ tầng và lỗi nghiệp vụ.
