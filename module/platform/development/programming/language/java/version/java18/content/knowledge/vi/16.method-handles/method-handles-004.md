# MethodHandles.lookup() và findStatic(): tạo handle đến method static có chữ ký xác định

> **Chương:** MethodHandle  
> **Áp dụng:** Java 18 trở lên và các JDK hiện đại hỗ trợ `java.lang.invoke.MethodHandles`, `MethodHandle`, `MethodType`. Các API này đã tồn tại trước Java 18 và tiếp tục hữu ích; bài học không coi chúng là tính năng mới xuất hiện ở Java 18.

## 1. Bài toán: gọi method static khi chỉ biết thông tin ở runtime

Giả sử một thư viện cần gọi method `twice(long)` của một lớp được cấu hình trước. Thư viện biết **lớp sở hữu, tên method, kiểu trả về và kiểu tham số**, nhưng muốn tạo đối tượng đại diện cho lời gọi để sử dụng lại.

API `java.lang.invoke` cho phép biểu diễn lời gọi đó bằng một `MethodHandle`. Một handle chứa khả năng gọi đích đã được liên kết, trong khi `MethodType` mô tả chính xác chữ ký lời gọi. Để tìm **method static**, điểm vào cơ bản là:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType type = MethodType.methodType(long.class, long.class);
MethodHandle handle = lookup.findStatic(
        Calculator.class, "twice", type);
```

Điều này trả lời ba câu hỏi độc lập:

1. **Ai được phép tìm?** Đối tượng `Lookup` mang quyền truy cập gắn với lớp nơi `MethodHandles.lookup()` được gọi.
2. **Tìm method nào?** `findStatic` nhận lớp khai báo/được tra cứu, tên method và một `MethodType`.
3. **Gọi bằng chữ ký nào?** `MethodHandle.type()` cho biết kiểu phương thức của handle; `invokeExact` yêu cầu chữ ký tại vị trí gọi khớp chính xác.

Bài này tập trung vào lời gọi tĩnh. Với instance method, constructor hoặc field, dùng API tìm kiếm khác, chẳng hạn `findVirtual`, `findConstructor`, `findGetter` hoặc `findStaticGetter` tùy loại thành viên. Không dùng `findStatic` để tìm constructor hoặc field.

## 2. Từ khai báo Java sang `MethodType`

Xét các khai báo:

```java
public static long twice(long value) {
    return value * 2;
}

public static String label(int value) {
    return "number=" + value;
}

public static String label(String value) {
    return "text=" + value;
}
```

Chữ ký phải được mô tả theo **thứ tự: kiểu trả về trước, các kiểu tham số sau**:

| Method nguồn | `MethodType` chính xác |
| --- | --- |
| `static long twice(long)` | `MethodType.methodType(long.class, long.class)` |
| `static String label(int)` | `MethodType.methodType(String.class, int.class)` |
| `static String label(String)` | `MethodType.methodType(String.class, String.class)` |
| `static void reset()` | `MethodType.methodType(void.class)` |
| `static int sum(int, int)` | `MethodType.methodType(int.class, int.class, int.class)` |
| `static String join(String...)` | `MethodType.methodType(String.class, String[].class)` |

`MethodType.methodType(returnType, parameterTypes...)` **không nhận tên method**, chỉ biểu diễn kiểu lời gọi. `void.class` mô tả kiểu trả về `void`. Kiểu nguyên thủy như `int.class` khác lớp bọc `Integer.class`; `String...` được khai báo trong bytecode dưới dạng một tham số mảng `String[]`.

**`findStatic` yêu cầu kiểu trả về và các kiểu tham số khớp chữ ký method cần tìm.** Không thể tìm `twice(long)` bằng `MethodType.methodType(long.class, int.class)` với kỳ vọng bước tra cứu tự chuyển `int` sang `long`. Chuyển đổi kiểu khi gọi qua `invoke` là câu chuyện khác với phân giải method ở bước lookup.

## 3. Vai trò của `MethodHandles.lookup()`

`MethodHandles.lookup()` tạo một `MethodHandles.Lookup` gắn với **lớp gọi thực sự của `lookup()`**. Lookup kiểm tra quyền Java và quy tắc truy cập module khi tạo handle. Ví dụ:

- Một method `public static` trong lớp mà lookup có quyền truy cập có thể được tìm bằng `findStatic` với đúng chữ ký.
- Method `private static` của **chính lớp tạo `Lookup`** có thể được tìm bằng lookup có quyền private tương ứng.
- `Lookup` tạo ở lớp A không tự có quyền gọi method private của lớp top-level B chỉ vì hai lớp được lưu trong cùng tệp `.java` hoặc cùng package.
- Với named module, `public` không đồng nghĩa mọi module đều gọi được: việc lớp/package có được truy cập còn phụ thuộc quan hệ module, `exports` và quyền của lookup.

Đừng coi `Lookup` là một công cụ bỏ qua encapsulation. Nếu hệ thống cần quyền truy cập sâu có kiểm soát giữa các module, hãy thiết kế API và khai báo module rõ ràng; `MethodHandles.privateLookupIn(...)` là API công khai cho một số trường hợp phù hợp nhưng vẫn chịu kiểm tra quyền/module, không phải cơ chế vượt qua giới hạn.

```text
Nơi gọi MethodHandles.lookup()
            |
            v
     Lookup (quyền của caller)
            |
            v
findStatic(owner, name, MethodType)
            |
        kiểm tra
    - method có tồn tại?
    - là static và đúng chữ ký?
    - caller có quyền truy cập?
            |
            v
   MethodHandle đã liên kết
            |
            v
  invokeExact(...) / invoke(...)
```

Điểm cần nhớ về bảo mật: handle được tạo thành công đại diện cho khả năng gọi method tương ứng; vì vậy không nên vô tình cung cấp `Lookup` có quyền cao hoặc handle nhạy cảm cho mã không đáng tin cậy. Quy tắc kiểm tra quyền lúc tạo handle khác với việc kiểm tra kiểu lời gọi khi thực thi.

## 4. Ví dụ hoàn chỉnh: tìm method static và kiểm chứng chữ ký

Tạo một tệp duy nhất `StaticHandleDemo.java` dưới đây. Ví dụ dùng lớp chính và một lớp top-level khác để kiểm tra quyền private mà không bị nhầm bởi quyền truy cập giữa các lớp cùng nest.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class StaticHandleDemo {
    public static long twice(long value) {
        return value * 2;
    }

    public static String label(int value) {
        return "number=" + value;
    }

    public static String label(String value) {
        return "text=" + value;
    }

    private static String privateTag(int value) {
        return "tag-" + value;
    }

    public static long fail(long value) {
        throw new IllegalArgumentException("target-" + value);
    }

    @FunctionalInterface
    interface ThrowingAction {
        void run() throws Throwable;
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectFailure(
            Class<? extends Throwable> expected, ThrowingAction action)
            throws Throwable {
        Throwable actual = null;
        try {
            action.run();
        } catch (Throwable error) {
            actual = error;
        }
        if (actual == null || !expected.isInstance(actual)) {
            String observed = actual == null
                    ? "no exception" : actual.getClass().getName();
            throw new AssertionError(
                    "expected=" + expected.getName()
                    + ", observed=" + observed, actual);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // 1. Tìm method static với kiểu (long)long chính xác.
        MethodType twiceType = MethodType.methodType(
                long.class, long.class);
        MethodHandle twiceHandle = lookup.findStatic(
                StaticHandleDemo.class, "twice", twiceType);
        check(twiceHandle.type().equals(twiceType),
                "handle.type must match twiceType");

        long result = (long) twiceHandle.invokeExact(21L);
        check(result == 42L, "twice result");

        // 2. Phân biệt hai overload bằng MethodType.
        MethodHandle labelInt = lookup.findStatic(
                StaticHandleDemo.class, "label",
                MethodType.methodType(String.class, int.class));
        MethodHandle labelString = lookup.findStatic(
                StaticHandleDemo.class, "label",
                MethodType.methodType(String.class, String.class));

        String fromInt = (String) labelInt.invokeExact(7);
        String fromString = (String) labelString.invokeExact("hi");
        check(fromInt.equals("number=7"), "int overload");
        check(fromString.equals("text=hi"), "String overload");

        // 3. Lookup tạo ở lớp này có thể tìm private static của nó.
        MethodHandle privateHandle = lookup.findStatic(
                StaticHandleDemo.class, "privateTag",
                MethodType.methodType(String.class, int.class));
        String tag = (String) privateHandle.invokeExact(5);
        check(tag.equals("tag-5"), "own private static method");

        // 4. Public static của một lớp top-level khác trong package.
        MethodHandle ping = lookup.findStatic(
                HelperMethods.class, "ping",
                MethodType.methodType(String.class));
        String pong = (String) ping.invokeExact();
        check(pong.equals("pong"), "helper method");

        // 5. invoke có thể thích nghi int -> long; invokeExact thì không.
        long adapted = (long) twiceHandle.invoke(21);
        check(adapted == 42L, "adapted invocation");

        expectFailure(NoSuchMethodException.class, () ->
                lookup.findStatic(
                        StaticHandleDemo.class, "twice",
                        MethodType.methodType(long.class, int.class)));

        expectFailure(IllegalAccessException.class, () ->
                lookup.findStatic(
                        HelperMethods.class, "hidden",
                        MethodType.methodType(String.class)));

        expectFailure(WrongMethodTypeException.class, () -> {
            long unused = (long) twiceHandle.invokeExact(21);
        });

        MethodHandle failing = lookup.findStatic(
                StaticHandleDemo.class, "fail",
                MethodType.methodType(long.class, long.class));
        expectFailure(IllegalArgumentException.class, () -> {
            long unused = (long) failing.invokeExact(1L);
        });

        System.out.println("PASS: lookup, findStatic, invokeExact, invoke");
        System.out.println("PASS: wrong signature, access, call-site type, target exception");
        System.out.println("java=" + Runtime.version());
    }
}

// Đây là một lớp top-level riêng biệt, không cùng nest với lớp chính.
class HelperMethods {
    public static String ping() {
        return "pong";
    }

    private static String hidden() {
        return "secret";
    }
}
```

### 4.1. Biên dịch và chạy

Chạy từ thư mục chứa `StaticHandleDemo.java` với JDK 18 trở lên:

```bash
javac StaticHandleDemo.java
java StaticHandleDemo
```

Trong ví dụ này, hai lớp cùng ở **unnamed package/module**, nhưng vẫn là hai lớp top-level khác nhau. `lookup()` được gọi bên trong `StaticHandleDemo.main`, nên có quyền truy cập `privateTag` của `StaticHandleDemo`, không có quyền truy cập `hidden` của `HelperMethods`.

Đầu ra **dự kiến** nếu các ca kiểm chứng đều đạt (phiên bản Java thực tế sẽ khác):

```text
PASS: lookup, findStatic, invokeExact, invoke
PASS: wrong signature, access, call-site type, target exception
java=<phien-ban-JDK-thuc-te>
```

Đây là kết quả mẫu để đối chiếu, không phải log biên dịch/chạy đã được thu trong tài liệu. Nếu bất kỳ điều kiện nào sai, chương trình ném `AssertionError` thay vì in đủ ba dòng `PASS`.

### 4.2. Vì sao `invokeExact` cần phép ép kiểu ở vị trí trả về?

`invokeExact` là phương thức có *signature polymorphism*: chữ ký tại vị trí gọi được hình thành từ **kiểu biên dịch** của các đối số và kiểu kết quả mà biểu thức yêu cầu. Trong ví dụ:

```java
long value = (long) twiceHandle.invokeExact(21L);
```

Vị trí gọi có kiểu `(long)long`, khớp với `twiceHandle.type()`. Nếu vô tình truyền `21` (kiểu `int`) thay cho `21L` (kiểu `long`), vị trí gọi trở thành `(int)long` và `invokeExact` không tự chuyển sang `(long)long`: `WrongMethodTypeException` được phát sinh.

Ngay cả khi các đối số đúng, **kiểu kết quả của vị trí gọi** cũng phải khớp. Ví dụ, viết `twiceHandle.invokeExact(21L);` như một biểu thức độc lập khiến vị trí gọi có kết quả `void`; nó không khớp handle trả `long`. Vì vậy nên khai báo biến kết quả hoặc ép kiểu trả về tường minh, đặc biệt khi đọc một handle từ cấu hình động.

Ngược lại:

```java
long value = (long) twiceHandle.invoke(21);
```

`invoke` có thể thực hiện một số chuyển đổi kiểu được phép theo quy tắc `MethodHandle.asType` (ở đây `int` sang `long`). Khả năng thích nghi không có nghĩa mọi kiểu đều hợp lệ: chuyển đổi thiếu tương thích hoặc không đáp ứng chữ ký vẫn gây lỗi. Khi muốn phát hiện sai chữ ký thật sớm và tránh chuyển đổi ngầm, dùng `invokeExact` là lựa chọn dễ kiểm soát.

## 5. Ba nhóm lỗi phải phân biệt

| Giai đoạn | Ví dụ | Kiểu lỗi cần nhận diện | Ý nghĩa |
| --- | --- | --- | --- |
| **Lookup** | `findStatic` với tên không tồn tại hoặc sai `MethodType` | `NoSuchMethodException` | Không tìm thấy static method khớp mô tả |
| **Kiểm tra quyền** | Lookup ở lớp A tìm private method của lớp top-level B | `IllegalAccessException` | Thành viên có thể tồn tại nhưng lookup không có quyền |
| **Gọi handle** | Handle `(long)long`, `invokeExact` tại vị trí `(int)long` | `WrongMethodTypeException` | Chữ ký call site không tương thích với handle |
| **Thân method đích** | Method đã được gọi và ném `IllegalArgumentException` | Ngoại lệ đích được truyền trực tiếp | Lỗi xuất phát từ nghiệp vụ của method |

Trong lời gọi qua `MethodHandle`, ngoại lệ mà method đích ném được truyền theo hợp đồng của method handles; **không tự bọc thành `InvocationTargetException` như `Method.invoke`**. Vì vậy, cách phân loại lỗi khi chuyển từ reflection sang method handles phải được cập nhật có chủ đích.

Trường hợp `findStatic` được yêu cầu đối với một instance method cũng không tạo ra một lời gọi instance hợp lệ. Muốn gọi instance method, cần `findVirtual` (hoặc một API phù hợp khác) và xử lý receiver trong `MethodType`/chữ ký handle theo quy tắc tương ứng.

## 6. `findStatic` khác `findVirtual` và `findConstructor` thế nào?

| Phương thức tìm | Đích cần tìm | Đặc điểm của handle trả về |
| --- | --- | --- |
| `lookup.findStatic(C.class, "m", type)` | Static method `C.m` | Không có tham số receiver |
| `lookup.findVirtual(C.class, "m", type)` | Instance method ảo | Thường có receiver kiểu `C` đứng đầu danh sách tham số của handle |
| `lookup.findConstructor(C.class, constructorType)` | Constructor của `C` | Kết quả handle là đối tượng `C`; kiểu tìm constructor quy định return `void` |
| `lookup.findStaticGetter(C.class, "f", FieldType.class)` | Static field | Handle đọc một field, không phải gọi method |

Ví dụ minh họa sự khác biệt về hình dạng type:

```java
// Static: public static int plus(int a, int b)
MethodType staticType = MethodType.methodType(
        int.class, int.class, int.class);
// findStatic(...).type() thường là (int,int)int.

// Instance: public int plus(int value)
MethodType virtualType = MethodType.methodType(int.class, int.class);
// findVirtual(C.class, "plus", virtualType).type() có
// tham số receiver đứng đầu, dạng (C,int)int.
```

Ở đây `C` là ký hiệu cho lớp ví dụ, không phải khai báo Java hoàn chỉnh. Mục đích là thấy **kiểu của method đích khi tra cứu** và **kiểu handle sau khi tìm** có thể khác nhau đối với instance method vì receiver; với `findStatic` không có receiver được thêm.

## 7. Quyền module và cách thiết kế API

Với ứng dụng JPMS, lookup ở module A chỉ có thể tìm member của module B khi các quy tắc truy cập Java và module cho phép. Public method của public class trong một package mà module B `exports` cho A là trường hợp thường gặp.

Ví dụ module cung cấp public API:

```java
module example.provider {
    exports example.provider.api;
}
```

Module gọi API có thể khai báo quan hệ đọc:

```java
module example.client {
    requires example.provider;
}
```

Khi triển khai thực tế, `example.provider.api` cần chứa class và method public mà client tìm bằng `findStatic`, đồng thời client cần nhận diện đúng `MethodType`. Những khai báo trên chỉ là ví dụ về module path; nội dung thực tế của class và module phải có mặt khi biên dịch.

Đối với private member của module khác, **không** trông chờ `lookup()` của client tự có quyền truy cập. Có thể cần thiết kế API public, factory được cung cấp bởi module sở hữu, hoặc cơ chế `privateLookupIn` với điều kiện module/package cho phép; `opens` không đồng nghĩa bỏ qua mọi kiểm tra quyền. Khi phân phối handle cho bên khác, cân nhắc vì handle đó đại diện cho quyền gọi member đã liên kết.

## 8. Sử dụng handle an toàn và hiệu quả

### 8.1. Lưu handle sau khi tìm

Nếu nhiều lần gọi cùng một static method với cùng chữ ký, việc lưu `MethodHandle` đã tìm thường giảm nhu cầu lặp lại lookup:

```java
private static final MethodHandle TWICE;

static {
    try {
        TWICE = MethodHandles.lookup().findStatic(
                StaticHandleDemo.class, "twice",
                MethodType.methodType(long.class, long.class));
    } catch (NoSuchMethodException | IllegalAccessException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đoạn này minh họa cách lưu metadata **trong lớp có phương thức phù hợp**; khi sao chép sang lớp khác, cần thay lớp sở hữu và đối chiếu quyền truy cập. Không suy ra rằng `static final` luôn giúp mọi kiểu workload chạy nhanh hơn một mức cố định. JIT, cách giữ metadata và phân bố đích gọi quyết định hiệu năng thực tế; dùng benchmark phù hợp để đánh giá.

### 8.2. Không làm sai hợp đồng vì thay API

- Định nghĩa chữ ký ở một vị trí rõ ràng; kiểm tra `handle.type()` khi ánh xạ thông tin động sang handle.
- Với overload, dùng đúng `MethodType` thay vì đoán từ tên method. Sai kiểu trả về cũng là sai chữ ký khi tìm handle.
- Chỉ chia sẻ `Lookup`/handle cho thành phần được phép sử dụng chức năng đó; handle là một năng lực gọi, không chỉ là tên method.
- Phân biệt ngoại lệ tra cứu, truy cập, sai kiểu tại vị trí gọi và ngoại lệ do method đích ném.
- Nếu chuyển từ `Method.invoke` sang handle, kiểm tra lại hành vi boxing, widening, varargs, giá trị trả về và cách truyền ngoại lệ. Hai API không tương đương hoàn toàn.
- Tránh API nội bộ `jdk.internal.*`, `sun.*` hoặc các thủ thuật mở package của JDK; tập trung vào `java.lang.invoke` công khai còn được hỗ trợ.

## 9. Bảng kiểm chứng để áp dụng trong dự án

| ID | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| H01 | `findStatic` đúng lớp, tên, `(long)long` | Có handle, `handle.type()` bằng type đã khai báo |
| H02 | `invokeExact(21L)` với kết quả ép `long` | Trả `42L` |
| H03 | Hai overload `label(int)` và `label(String)` | Hai handle có kiểu khác nhau, gọi ra giá trị đúng |
| H04 | `findStatic` với tham số `int` trong khi method nhận `long` | `NoSuchMethodException` |
| H05 | Tìm private static của chính lớp tạo lookup | Thành công nếu lookup có quyền tương ứng |
| H06 | Tìm private static của lớp top-level khác bằng lookup không đủ quyền | `IllegalAccessException` |
| H07 | `invokeExact(21)` (kiểu `int`) với handle `(long)long` | `WrongMethodTypeException` |
| H08 | `invoke(21)` với handle `(long)long` | Kết quả `42L` nhờ chuyển đổi được phép |
| H09 | Static method đích ném `IllegalArgumentException` | Ngoại lệ này truyền trực tiếp, không bị bọc bằng `InvocationTargetException` |

Khi chạy trên JDK đích, ghi rõ phiên bản JDK, câu lệnh, module/classpath, trạng thái PASS/FAIL và exception type của mỗi ca. Không dựa trên chuỗi thông báo lỗi hoặc stack trace nội bộ làm tiêu chí ổn định, vì chúng có thể thay đổi theo runtime.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `MethodType.methodType(long.class, int.class)` không tìm được `static long twice(long)` dù `int` có thể được mở rộng sang `long` khi gọi?
2. Quyền của `MethodHandles.lookup()` được xác định bởi lớp nào? Điều gì xảy ra nếu helper library gọi `lookup()` thay cho mã ứng dụng?
3. `findStatic` với hai overload cùng tên sẽ phân biệt bằng tham số nào?
4. Vì sao `long result = (long) handle.invokeExact(21L)` khác với `handle.invokeExact(21L);`?
5. Vì sao lời gọi `handle.invoke(21)` có thể thành công trong trường hợp `handle.invokeExact(21)` thất bại?
6. Khi method đích ném `IllegalArgumentException`, cách ngoại lệ xuất hiện qua `MethodHandle` khác `Method.invoke` ra sao?
7. Nếu phải gọi private static method ở một named module khác, cần xem xét quyền truy cập và thiết kế module nào?

**Ghi nhớ:** Với `findStatic`, bộ ba **lớp sở hữu + tên method + `MethodType` chính xác** xác định mục tiêu tra cứu; `MethodHandles.lookup()` quyết định quyền tìm; `invokeExact` kiểm tra kiểu tại vị trí gọi. Đây là các hợp đồng công khai còn có giá trị trên JDK hiện đại. Tham khảo Javadoc của `MethodHandles.Lookup.findStatic`, `MethodType`, `MethodHandle.invokeExact`/`invoke` trên đúng bản JDK đang sử dụng.
