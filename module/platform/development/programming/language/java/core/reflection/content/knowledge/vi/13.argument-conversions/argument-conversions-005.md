# Số lượng đối số và IllegalArgumentException khi gọi Java Reflection

Khi gọi method hoặc constructor bằng Reflection, số lượng và kiểu đối số phải khớp **đúng chữ ký đã chọn**. Trong mã nguồn Java thông thường, trình biên dịch có thể phân giải overload, đóng gói varargs và kiểm tra nhiều phép chuyển đổi. Nhưng với `java.lang.reflect.Method.invoke(...)` và `Constructor.newInstance(...)`, bạn đã chọn một executable cụ thể rồi mới truyền dữ liệu. Reflection không tự tìm lại overload, không tự parse String sang số, không bỏ đối số thừa và không tự thêm đối số bị thiếu.

Bài này tập trung vào cách kiểm tra **số lượng đối số**, nguyên nhân dẫn đến `IllegalArgumentException`, quy tắc chuyển đổi cho từng formal parameter và cách phân biệt lỗi của Reflection với lỗi ném từ thân method đích.

## 1. Bước tìm method khác bước invoke

Ví dụ method đích:

```java
class Calculator {
    public long add(int left, long right) {
        return left + right;
    }
}
```

Bước tra cứu:

```java
java.lang.reflect.Method method =
        Calculator.class.getMethod("add", int.class, long.class);
```

Bước thực thi:

```java
Calculator calculator = new Calculator();
Object value = method.invoke(calculator, 2, 5L); // Long(7)
```

Các đoạn trên là code minh họa ghép với nhau, cần xử lý `NoSuchMethodException`, `IllegalAccessException` và `InvocationTargetException` tại phương thức gọi. Hai kiểu formal parameter là `int` và `long`, vì vậy method nhận **chính xác hai đối số** sau receiver. `Method.invoke` có chữ ký:

```java
Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
```

Trong đó:

- `obj` là **receiver** cho instance method; nó **không tính vào** số formal parameter của method. Với static method có thể truyền `null` làm receiver.
- `args` là một mảng các đối số thực tế; mỗi phần tử ứng với một formal parameter theo thứ tự. Kiểu return là `Object`; giá trị primitive được boxed, method trả `void` cho kết quả `null`.
- `Method.getParameterCount()` trả về số formal parameter, còn `Method.getParameterTypes()` trả về các kiểu theo thứ tự. Với `add(int,long)`, hai giá trị này tương ứng `2` và mảng `[int.class,long.class]`.

Nếu không tìm thấy chữ ký ở bước `getMethod(...)`, ngoại lệ là `NoSuchMethodException`. Khi đã tìm ra method nhưng truyền sai đối số cho `invoke(...)`, ngoại lệ thường là `IllegalArgumentException`. Hai lỗi thuộc hai bước khác nhau.

## 2. Sai số lượng: thiếu một, thừa một hoặc nhầm receiver

Với `add(int,long)`:

| Lời gọi | Kết quả | Lý do |
| --- | --- | --- |
| `method.invoke(calculator, 2, 5L)` | Hợp lệ, trả `Long(7)` | Hai slot đúng kiểu |
| `method.invoke(calculator, 2)` | `IllegalArgumentException` | Thiếu một slot |
| `method.invoke(calculator, 2, 5L, 8L)` | `IllegalArgumentException` | Thừa một slot |
| `method.invoke(new Object(), 2, 5L)` | `IllegalArgumentException` | Receiver không tương thích với declaring class |
| `method.invoke(null, 2, 5L)` | `NullPointerException` | Receiver null cho instance method |
| `method.invoke(calculator, 2, "5")` | `IllegalArgumentException` | String không tự parse sang `long` |

Các lời gọi trên đều là code minh họa khi `method` và `calculator` đã được khai báo. **Số lượng receiver + số đối số không phải số formal parameters**: `getParameterCount()` của `add` vẫn là 2, mặc dù `Method.invoke` xuất hiện thêm receiver ở vị trí đầu.

Method đích không có parameter cần `method.invoke(receiver)` hoặc cung cấp mảng actual args rỗng. Trong khi đó, `method.invoke(receiver, (Object) null)` **truyền một slot chứa null**, không phải zero slot.

## 3. Ví dụ Java 17+ chạy được, có đầu ra chính xác

Lưu toàn bộ chương trình sau dưới tên `ReflectionArgumentDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionArgumentDemo {
    public static class Calculator {
        public long add(int left, long right) {
            return left + right;
        }

        public String join(String prefix, String... items) {
            return prefix + ":" + String.join(",", items);
        }

        public int fail(int value) {
            throw new IllegalArgumentException("business rule");
        }
    }

    private static void attempt(
            String label, Method method, Object receiver, Object... args) {
        try {
            Object result = method.invoke(receiver, args);
            System.out.println(label + " -> " + result);
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> IllegalArgumentException");
        } catch (IllegalAccessException ex) {
            System.out.println(label + " -> IllegalAccessException");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> target "
                    + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Calculator calculator = new Calculator();

        Method add = Calculator.class.getMethod(
                "add", int.class, long.class);

        System.out.println("parameter count: " + add.getParameterCount());
        attempt("correct", add, calculator, 2, 5L);
        attempt("missing", add, calculator, 2);
        attempt("extra", add, calculator, 2, 5L, 8L);
        attempt("string", add, calculator, 2, "5");
        attempt("null primitive", add, calculator, null, 5L);
        attempt("narrowing", add, calculator, 2L, 5L);
        attempt("widening", add, calculator, (byte) 2, 5);
        attempt("wrong receiver", add, new Object(), 2, 5L);

        Method join = Calculator.class.getMethod(
                "join", String.class, String[].class);
        System.out.println("join varargs: " + join.isVarArgs());
        attempt("packed", join, calculator, "tag",
                (Object) new String[] {"A", "B"});
        attempt("spread", join, calculator, "tag", "A", "B");

        Method fail = Calculator.class.getMethod("fail", int.class);
        attempt("target throws", fail, calculator, 4);
    }
}
```

Chạy:

```bash
javac ReflectionArgumentDemo.java
java ReflectionArgumentDemo
```

Stdout:

```text
parameter count: 2
correct -> 7
missing -> IllegalArgumentException
extra -> IllegalArgumentException
string -> IllegalArgumentException
null primitive -> IllegalArgumentException
narrowing -> IllegalArgumentException
widening -> 7
wrong receiver -> IllegalArgumentException
join varargs: true
packed -> tag:A,B
spread -> IllegalArgumentException
target throws -> target IllegalArgumentException
```

Giải thích kết quả:

1. `correct`: Integer unbox thành int, Long unbox thành long; method trả primitive long và Reflection boxing kết quả vào `Long`.
2. `missing`, `extra`: không đúng số lượng formal parameters, nên Reflection không gọi method.
3. `string`: Reflection không chạy `Long.parseLong("5")`.
4. `null primitive`: không thể unbox null thành primitive int.
5. `narrowing`: truyền `Long` vào vị trí `int` cần phép thu hẹp không được hỗ trợ.
6. `widening`: Byte unbox rồi widen đến int; Integer unbox rồi widen đến long; trả 7.
7. `wrong receiver`: `new Object()` không là instance `Calculator`.
8. `packed`: slot cuối chứa một `String[]` đúng kiểu formal parameter của method varargs.
9. `spread`: đưa ba slot cho method thực tế có hai formal parameters; Reflection không tự pack.
10. `target throws`: thân method `fail` **đã được gọi** và tự ném `IllegalArgumentException`, được `Method.invoke` bọc trong `InvocationTargetException`. Vì thế helper in thêm tiền tố `target` để phân biệt.

## 4. Constructor.newInstance có quy tắc tương tự

Đối với constructor được chọn qua `Class.getConstructor(...)` hoặc `getDeclaredConstructor(...)`, gọi `Constructor.newInstance(Object... initargs)` cần đúng số lượng và kiểu theo formal parameters của constructor.

Ví dụ minh họa:

```java
public static class Ticket {
    private final int number;

    public Ticket(int number) {
        this.number = number;
    }

    @Override
    public String toString() {
        return "Ticket(" + number + ")";
    }
}
```

Lớp lồng static này cần đặt trong một outer class khi biên dịch. Gọi:

```java
java.lang.reflect.Constructor<Ticket> ctor =
        Ticket.class.getConstructor(int.class);

Ticket ticket = ctor.newInstance(7);
System.out.println(ticket); // Ticket(7)
```

`ctor.newInstance()` thiếu đối số; `ctor.newInstance("7")` sai kiểu; `ctor.newInstance(7L)` cần thu hẹp long xuống int. Những trường hợp đó đều dẫn tới `IllegalArgumentException` trực tiếp từ Reflection.

Nếu code trong constructor **tự ném exception**, `Constructor.newInstance` bọc exception gốc bằng `InvocationTargetException`. Nếu class là abstract, khởi tạo bằng constructor có thể gây `InstantiationException`; nếu không được phép truy cập constructor, có thể gặp `IllegalAccessException`.

Trường hợp **non-static inner class** đáng chú ý: một constructor có thể cần tham số ẩn biểu diễn enclosing instance. Vì vậy công cụ tổng quát không nên đếm parameter chỉ bằng mắt trên source; hãy dùng `Constructor.getParameterCount()` và `getParameterTypes()` của executable thực tế.

## 5. Phân biệt ngoại lệ khi khám phá, chuẩn bị và gọi

| Ngoại lệ | Nguồn điển hình | Cách xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | Tra cứu bằng tên/chữ ký thất bại trước lúc invoke | Kiểm tra tên method, `Class<?>`, mức truy cập và formal parameter types |
| `IllegalArgumentException` trực tiếp | Sai số slot, kiểu, unboxing/widening hoặc receiver sai loại | So sánh actual args với metadata executable |
| `NullPointerException` | Receiver null của instance method hoặc lỗi khác ở mã người gọi | Kiểm tra receiver; không nhầm với lỗi do thân method |
| `IllegalAccessException` | Thành viên không có quyền truy cập hợp lệ | Kiểm tra accessibility và JPMS |
| `InaccessibleObjectException` | Cố bật deep reflection bằng `setAccessible(true)` nhưng module không mở | Dùng API public hoặc khai báo `opens` hợp lệ cho code sở hữu |
| `InvocationTargetException` | Method/constructor **đã thực thi** và ném exception | Xem `getCause()` |
| `ExceptionInInitializerError` | Khởi tạo class trong lúc gọi thất bại | Kiểm tra static initializer và cause |
| `ClassCastException` | Code người gọi ép sai kiểu `Object` đã trả về | Kiểm tra return type và cast |

Nhấn mạnh khác biệt quan trọng:

```java
// Truyền sai tham số: Reflection trực tiếp ném IllegalArgumentException.
method.invoke(receiver, "not-an-int");

// Đúng tham số nhưng code của method đích tự ném IllegalArgumentException:
// Method.invoke sẽ ném InvocationTargetException chứa cause đó.
```

Đây là code minh họa, giả định `method` yêu cầu một tham số int. Nếu chỉ bắt `IllegalArgumentException` trực tiếp từ `invoke`, bạn không tự động bắt được `IllegalArgumentException` do method đích ném. Muốn ghi nhận lỗi nghiệp vụ, bắt `InvocationTargetException` và xem `getCause()`.

Với `Method.invoke`, code xử lý cơ bản:

```java
try {
    Object result = method.invoke(receiver, actualArgs);
} catch (IllegalArgumentException ex) {
    // Lỗi receiver hoặc danh sách actual arguments.
} catch (IllegalAccessException ex) {
    // Lỗi quyền truy cập Reflection.
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable targetFailure = ex.getCause();
    // Lỗi xảy ra bên trong method đã được gọi.
}
```

Đây là đoạn minh họa, phụ thuộc `method`, `receiver`, `actualArgs` do ứng dụng cung cấp. Code production nên giữ stack trace/cause thay vì chỉ in tên exception.

## 6. Kiểm tra trước khi invoke nhưng không tái hiện bừa bãi compiler

Có thể kiểm tra arity sớm:

```java
int formalCount = method.getParameterCount();
Class<?>[] formalTypes = method.getParameterTypes();
boolean varargs = method.isVarArgs();

Object[] actualArgs = {2, 5L};
if (actualArgs.length != formalCount) {
    throw new IllegalArgumentException(
            "Expected " + formalCount + " args, got " + actualArgs.length);
}
```

Đây là đoạn minh họa dùng method `add`. Thực tế phải xử lý mảng `actualArgs` có thể null, kiểm tra từng vị trí và xác nhận receiver tương thích. Khi formal type là reference, có thể xét `expectedType.isInstance(value)`; khi formal type là primitive, `Class.isInstance(wrapper)` không thay cho quy tắc unboxing/widening, nên cần mapping nếu chủ động validate.

Kiểm tra trước quan trọng nhưng không thay thế hoàn toàn `invoke`: một receiver có thể null, quyền truy cập có thể bị từ chối, hoặc method đích có thể ném exception. Một adapter nhận dữ liệu từ CLI/HTTP/JSON nên tự parse và validate trước, sau đó **chọn overload rõ ràng** theo chữ ký mong muốn.

Khi tạo thông báo lỗi cho người dùng, nên ghi cụ thể tên method, số lượng cần/có, vị trí tham số và kiểu mong đợi. Không nên phụ thuộc chính xác `IllegalArgumentException.getMessage()` của JDK, vì thông điệp có thể khác giữa các bản runtime.

## 7. Câu hỏi tự kiểm tra

Giả sử `Method m` đại diện `Calculator.add(int,long)` ở mục 3:

- `m.invoke(c, 1, 2L)`: **hợp lệ**, kết quả `Long(3)`.
- `m.invoke(c, 1)`: **IllegalArgumentException**, vì thiếu một đối số.
- `m.invoke(c, 1, 2L, 3L)`: **IllegalArgumentException**, vì thừa một đối số.
- `m.invoke(c, 1, "2")`: **IllegalArgumentException**, vì String không tự parse thành long.
- `m.invoke(c, (byte)1, 2)`: **hợp lệ** nhờ primitive widening.
- `m.invoke(c, 1L, 2L)`: **IllegalArgumentException**, vì formal parameter đầu cần int và không tự narrow long.
- `m.invoke(null, 1, 2L)`: **NullPointerException**, do method không static mà receiver null.
- `Calculator.fail(4)` tự ném `IllegalArgumentException`: Reflection bọc trong **InvocationTargetException**.
- `Calculator.join(String,String...)` cần mấy formal parameters? **Hai**: String và String[].
- Muốn truyền array cho method đích varargs bằng Reflection, cách nào rõ ràng? **`(Object) new String[] {"A","B"}`** ở slot array cuối.

**Ghi nhớ:** xác định đúng executable, đếm đúng **formal parameters**, kiểm tra **receiver**, tính tương thích của từng đối số và tự đóng gói mảng varargs. Khi xảy ra lỗi, phân biệt `IllegalArgumentException` trực tiếp do Reflection phát hiện đối số không hợp lệ với `InvocationTargetException` chứa lỗi từ method/constructor đích.

### Tài liệu chính thức

- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [JLS 17 — Method Invocation Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3)