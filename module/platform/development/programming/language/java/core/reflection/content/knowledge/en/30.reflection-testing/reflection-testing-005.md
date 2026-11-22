# Kiểm thử lỗi của mã đích được giữ qua `InvocationTargetException`

## 1. Mục tiêu của bài kiểm thử

Khi gọi một phương thức bằng Java Reflection, `Method.invoke(receiver, args...)` có thể thất bại ở **hai tầng khác nhau**:

1. **Tầng reflection**: không tìm được phương thức, không đủ quyền, sai receiver hoặc đối số. Đây là lỗi trong quá trình chuẩn bị/điều phối lời gọi.
2. **Tầng mã đích**: phương thức đã thực sự được gọi và chính phần thân của nó ném exception hay error.

Ở tầng thứ hai, `Method.invoke` gói `Throwable` do **phương thức đích** ném vào một `java.lang.reflect.InvocationTargetException`. Đối tượng gốc có thể lấy lại bằng `getCause()` hoặc `getTargetException()`. Một bài kiểm thử tốt phải chứng minh cả **đúng loại wrapper**, **đúng đối tượng nguyên nhân gốc** và **đúng nội dung/cause chain**; nếu chỉ so chuỗi message của wrapper thì rất dễ bỏ sót lỗi.

Ví dụ kỳ vọng cốt lõi:

```java
Method method = Target.class.getDeclaredMethod("fail");
try {
    method.invoke(null);
    throw new AssertionError("Expected InvocationTargetException");
} catch (InvocationTargetException e) {
    Throwable original = e.getCause();
    // Kiểm tra type, message và/hoặc identity của original.
}
```

Đoạn trên là **mẫu minh họa**, cần đặt trong ngữ cảnh có import, lớp `Target` và xử lý các checked exceptions còn lại. Ví dụ có thể chạy độc lập ở mục 5.

## 2. Hợp đồng của `Method.invoke` và wrapper

Chữ ký rút gọn:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
```

Các hành vi cần phân biệt:

| Điều kiện | Lỗi quan sát khi gọi reflection | `InvocationTargetException`? |
| --- | --- | --- |
| Mã đích ném `IllegalStateException` | `InvocationTargetException` chứa `IllegalStateException` | Có |
| Mã đích ném checked `IOException` | `InvocationTargetException` chứa `IOException` | Có |
| Mã đích ném `AssertionError` | `InvocationTargetException` chứa `AssertionError` | Có |
| Mã đích ném `IllegalArgumentException` | `InvocationTargetException` chứa `IllegalArgumentException` | Có |
| Caller truyền sai kiểu/số lượng đối số cho `Method.invoke` | Thường là `IllegalArgumentException` trực tiếp | Không |
| Không có quyền truy cập tới phương thức | `IllegalAccessException`, hoặc lỗi khi cố mở quyền | Không |
| Tra phương thức không tồn tại qua `getDeclaredMethod` | `NoSuchMethodException` tại **bước tra cứu**, chưa có invoke | Không |
| Mã đích chạy thành công | Kết quả được trả về (hoặc `null` cho phương thức `void`) | Không |

Với `Method.invoke`, **exception do target ném** được bao trong `InvocationTargetException` kể cả khi nó là unchecked exception hoặc `Error`. Việc `Method.invoke` trả về `Object` không làm thay đổi danh tính exception gốc.

`InvocationTargetException` kế thừa `ReflectiveOperationException`. `getTargetException()` là API lịch sử; trong mã mới, `getCause()` biểu đạt quan hệ nguyên nhân nhất quán với `Throwable`. Với wrapper do `Method.invoke` tạo ra sau khi target ném lỗi, hai hàm trả về cùng đối tượng target throwable.

Các trường hợp biên: nếu JVM hoặc môi trường thất bại **trước khi** chuyển điều khiển vào mã đích (ví dụ lỗi liên kết hoặc tải lớp), không nên mặc định mọi `Throwable` nhìn thấy đều là lỗi target đã được gói. Hãy xác nhận thao tác và loại ngoại lệ thực tế.

## 3. Những điều phải assert để bảo đảm "được giữ nguyên"

Với một lời gọi mà bạn **chủ động tạo ra** exception ở target, nên kiểm tra theo mức tăng dần:

- **Wrapper đúng loại:** `assertThrows(InvocationTargetException.class, () -> method.invoke(...))`.
- **Có nguyên nhân gốc:** `assertNotNull(wrapper.getCause())`.
- **Đúng loại nguyên nhân:** ví dụ `assertInstanceOf(IllegalStateException.class, wrapper.getCause())` hoặc kiểm tra exact class khi hợp đồng yêu cầu.
- **Danh tính của Throwable:** nếu test giữ sẵn tham chiếu đến object đã ném, `assertSame(original, wrapper.getCause())`. Đây là bằng chứng mạnh hơn so sánh message: wrapper giữ **chính Throwable ban đầu**, không tự tạo đối tượng khác thay cho nó.
- **Cùng đối tượng qua API:** `assertSame(wrapper.getCause(), wrapper.getTargetException())`.
- **Message/cause chain:** khi thuộc hợp đồng được kiểm thử, xác nhận `original.getMessage()` và `original.getCause()`; không chỉ assert các chuỗi hình thành từ wrapper.
- **Nguồn phát sinh:** nếu thực sự cần, kiểm tra phương thức trên stack trace của nguyên nhân hoặc dùng dấu hiệu do target đặt ra để chứng minh thân đã chạy. Tránh phụ thuộc đường dẫn file, số dòng và thứ tự toàn bộ stack frames vốn có thể thay đổi.

**Lưu ý về `assertSame`:** trong test minh họa, target gán tham chiếu đến exception vừa tạo cho trường test fixture trước khi ném. Đây là cách kiểm tra identity. Trong production, không nên giữ Throwable trong biến static toàn cục chỉ để log; kiểm thử có thể dùng fixture có phạm vi nhỏ, và các test này chạy tuần tự để tránh ghi đè tham chiếu.

## 4. Cách kiểm thử một phương thức thật qua reflection

Các bước kiểm thử hợp lý:

1. Tạo target có hành vi ném lỗi **xác định**. Tách tình huống checked, unchecked và `Error` nếu hợp đồng bao quát cả ba.
2. Lấy đúng `Method` bằng `getDeclaredMethod(name, parameterTypes...)` hoặc `getMethod(...)`. Nếu phương thức `static`, truyền receiver `null`; với instance method, tạo receiver đúng lớp.
3. Gọi qua `Method.invoke` bên trong một hàm kiểm thử cho phép ném `Throwable`.
4. Bắt/khẳng định `InvocationTargetException` rồi đọc `getCause()`. So sánh **reference** nếu fixture lưu original; kiểm tra type và message.
5. Kiểm tra các tình huống reflection lỗi **trước lời gọi** bằng một test khác để không vô tình gộp hai tầng lỗi.
6. Nếu ứng dụng có wrapper helper để unwrap và ném lại nguyên nhân, kiểm thử riêng helper đó: bên gọi phải thấy nguyên nhân gốc chứ không còn `InvocationTargetException`.

Không nên tạo lại `new IllegalStateException(message)` trong mã test rồi gọi `assertSame` với exception của target: đó là **hai object khác nhau** dù trùng loại và message. Cũng không nên so `wrapper.getMessage()` với message nghiệp vụ; wrapper và nguyên nhân là hai tầng khác nhau.

## 5. Ví dụ Java 17+ độc lập: test runtime, checked, Error, cause chain và unwrap

Lưu file `InvocationTargetExceptionDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationTargetExceptionDemo {
    static final class Target {
        static Throwable lastThrown;
        static boolean called;

        public static void failRuntime() {
            IllegalStateException original =
                    new IllegalStateException("runtime failure");
            lastThrown = original;
            throw original;
        }

        public static void failChecked() throws IOException {
            IOException original = new IOException("checked failure");
            lastThrown = original;
            throw original;
        }

        public static void failError() {
            AssertionError original = new AssertionError("error failure");
            lastThrown = original;
            throw original;
        }

        public static void failIllegalArgument() {
            IllegalArgumentException original =
                    new IllegalArgumentException("inside target");
            lastThrown = original;
            throw original;
        }

        public static void failWithCause() {
            IOException root = new IOException("root cause");
            IllegalStateException original =
                    new IllegalStateException("outer cause", root);
            lastThrown = original;
            throw original;
        }

        public static void acceptInt(int number) {
            called = true;
        }
    }

    @FunctionalInterface
    interface ThrowingAction {
        void run() throws Throwable;
    }

    static <T extends Throwable> T expectThrows(
            Class<T> expectedType, ThrowingAction action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!expectedType.isInstance(actual)) {
                throw new AssertionError(
                        "Expected " + expectedType.getName()
                                + ", got " + actual.getClass().getName(),
                        actual);
            }
            return expectedType.cast(actual);
        }
        throw new AssertionError(
                "Expected exception: " + expectedType.getName());
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void verifyTargetFailure(
            String methodName, Class<? extends Throwable> causeType)
            throws Exception {
        Method method = Target.class.getDeclaredMethod(methodName);
        Target.lastThrown = null;

        InvocationTargetException wrapper = expectThrows(
                InvocationTargetException.class,
                () -> method.invoke(null));

        Throwable original = wrapper.getCause();
        require(original != null, "Missing target cause");
        require(causeType.isInstance(original), "Wrong target type");
        require(original == Target.lastThrown, "Original identity lost");
        require(wrapper.getTargetException() == original,
                "Different target exception");
    }

    static Object invokeUnwrapped(Method method, Object receiver,
            Object... arguments) throws Throwable {
        try {
            return method.invoke(receiver, arguments);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    public static void main(String[] args) throws Exception {
        verifyTargetFailure(
                "failRuntime", IllegalStateException.class);
        System.out.println("runtime=wrapped,preserved");

        verifyTargetFailure("failChecked", IOException.class);
        System.out.println("checked=wrapped,preserved");

        verifyTargetFailure("failError", AssertionError.class);
        System.out.println("error=wrapped,preserved");

        verifyTargetFailure(
                "failIllegalArgument", IllegalArgumentException.class);
        System.out.println("targetIllegalArg=wrapped");

        Method chained = Target.class.getDeclaredMethod("failWithCause");
        InvocationTargetException wrapper = expectThrows(
                InvocationTargetException.class,
                () -> chained.invoke(null));
        Throwable original = wrapper.getCause();
        require(original == Target.lastThrown, "Cause identity changed");
        require(original.getCause() instanceof IOException,
                "Nested cause type changed");
        require("root cause".equals(original.getCause().getMessage()),
                "Nested cause message changed");
        System.out.println("nestedCause=preserved");

        Method accepting = Target.class.getDeclaredMethod(
                "acceptInt", int.class);
        Target.called = false;
        expectThrows(IllegalArgumentException.class,
                () -> accepting.invoke(null, "not an int"));
        require(!Target.called, "Target should not have run");
        System.out.println("badArguments=directIllegalArgumentException");

        Method failing = Target.class.getDeclaredMethod("failRuntime");
        IllegalStateException escaped = expectThrows(
                IllegalStateException.class,
                () -> invokeUnwrapped(failing, null));
        require(escaped == Target.lastThrown, "Unwrap lost identity");
        System.out.println("unwrap=originalCause");
    }
}
```

Chạy trong thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 InvocationTargetExceptionDemo.java
java InvocationTargetExceptionDemo
```

Stdout mong đợi:

```text
runtime=wrapped,preserved
checked=wrapped,preserved
error=wrapped,preserved
targetIllegalArg=wrapped
nestedCause=preserved
badArguments=directIllegalArgumentException
unwrap=originalCause
```

Mỗi dòng chỉ được in **sau khi mọi assertion tương ứng thành công**. Nếu một giả định sai, chương trình ném `AssertionError` và sẽ không in dòng báo kết quả của bước đó. Hàm `expectThrows` cố tình dùng một harness tối giản không phụ thuộc thư viện ngoài; trong dự án có JUnit 5, dùng `org.junit.jupiter.api.Assertions.assertThrows` sẽ chuẩn hơn.

### Vì sao ví dụ này có giá trị kiểm chứng?

- `verifyTargetFailure` kiểm tra cùng lúc wrapper, type, **identity** và sự thống nhất `getCause()`/`getTargetException()` cho unchecked, checked, `Error` và lỗi `IllegalArgumentException` từ **bên trong target**.
- `failWithCause` xác nhận **chuỗi nguyên nhân gốc** bên trong target không biến mất khi được thêm wrapper reflection.
- `acceptInt` làm rõ một `IllegalArgumentException` xuất hiện do **gọi reflection sai tham số** thì là ngoại lệ trực tiếp, target không chạy và không có `InvocationTargetException`.
- `invokeUnwrapped` mô phỏng code adapter đã quyết định trả lại nguyên nhân nghiệp vụ. Kiểm thử khẳng định bên gọi nhận được **chính exception gốc**, không có wrapper thứ hai và không bị thay bằng đối tượng cùng loại nhưng khác identity.

Trong ví dụ, fixture lưu `Target.lastThrown` dạng `static`. Vì main chạy tuần tự và reset fixture trước các trường hợp, điều này an toàn cho mô hình học tập; test thực tế chạy song song nên dùng fixture độc lập hoặc cơ chế phối hợp tránh tranh chấp trạng thái.

## 6. Cách viết tương đương bằng JUnit 5

Nếu dự án đã cấu hình **JUnit Jupiter**, một test đơn có thể viết như sau. Đoạn dưới đây **thuộc một test class cùng package**, tham chiếu đến lớp `InvocationTargetExceptionDemo.Target` của ví dụ phía trên; cần đưa dependency JUnit Jupiter vào build trước khi biên dịch test.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReflectionExceptionTest {
    @Test
    void preservesOriginalException() throws Exception {
        Method method =
                InvocationTargetExceptionDemo.Target.class
                        .getDeclaredMethod("failRuntime");

        InvocationTargetException wrapper = assertThrows(
                InvocationTargetException.class,
                () -> method.invoke(null));

        Throwable original = wrapper.getCause();
        assertNotNull(original);
        assertInstanceOf(IllegalStateException.class, original);
        assertSame(InvocationTargetExceptionDemo.Target.lastThrown,
                original);
        assertSame(original, wrapper.getTargetException());
        assertEquals("runtime failure", original.getMessage());
    }

    @Test
    void wrongArgumentFailsBeforeTarget() throws Exception {
        Method method =
                InvocationTargetExceptionDemo.Target.class
                        .getDeclaredMethod("acceptInt", int.class);

        InvocationTargetExceptionDemo.Target.called = false;
        assertThrows(IllegalArgumentException.class,
                () -> method.invoke(null, "bad argument"));
        assertFalse(InvocationTargetExceptionDemo.Target.called);
    }
}
```

Bài test này không phải chương trình có `main` độc lập; thực thi bằng runner của JUnit 5, ví dụ Gradle với `test { useJUnitPlatform() }` khi môi trường dự án đã khai báo dependency phù hợp.

**Không** nên viết `assertThrows(IllegalStateException.class, () -> method.invoke(null))` cho test đầu tiên: lời gọi reflection làm xuất hiện `InvocationTargetException` ở phía caller; `IllegalStateException` nằm trong `getCause()`.

Nếu test tác vụ bất đồng bộ, áp dụng đúng ranh giới: xác định có future/async wrapper khác (`ExecutionException`, `CompletionException`) trước hay không. Đừng mặc nhiên kết luận rằng mọi Throwable từ thread khác đều đi qua `InvocationTargetException`.

## 7. Kiểm thử stack trace và cause chain không quá mong manh

`InvocationTargetException` và exception gốc có thể có **hai stack trace khác nhau**:

- Wrapper gắn với tầng reflection tại thời điểm gọi.
- Cause giữ stack trace khi Throwable gốc được tạo/ném trong target.

Để kiểm tra điều có ý nghĩa, ưu tiên assert các thông tin ổn định: exception class, message nghiệp vụ, reference identity khi có fixture, và `getCause()`. Khi phải kiểm tra stack, chỉ xác nhận nó chứa frame của phương thức đích:

```java
// Đoạn minh họa nằm trong test đã có Throwable original:
boolean containsTarget = java.util.Arrays.stream(
        original.getStackTrace())
        .anyMatch(frame -> frame.getMethodName()
                .equals("failRuntime"));
if (!containsTarget) {
    throw new AssertionError("Target stack frame missing");
}
```

Không nên so toàn bộ `StackTraceElement[]`, số dòng source hoặc tên implementation nội bộ của reflection, bởi JVM/JDK hoặc trình tối ưu có thể làm thay đổi các chi tiết này. Nếu target chỉnh stack bằng `setStackTrace`, tắt stack trace hoặc tái sử dụng exception có stack cũ, đó là đặc điểm riêng của target cần được test theo hợp đồng, không phải lý do để mọi test phải ép cùng kết quả.

`Throwable.getCause()` có thể lại chứa một exception khác do target tạo; phải phân biệt:

```text
InvocationTargetException    ← wrapper do reflection tạo
  └─ IllegalStateException   ← chính exception mã đích ném
       └─ IOException        ← nguyên nhân sâu hơn do mã đích gắn vào
```

Lúc truy nguyên nhân, **không bỏ qua** tầng wrapper mà không ghi ngữ cảnh `Method` nào được gọi, nhưng cũng không để wrapper che mất loại lỗi nghiệp vụ bên trong.

## 8. Lỗi phổ biến khi viết test và adapter

| Sai sót | Hậu quả | Cách kiểm tra/sửa |
| --- | --- | --- |
| `assertThrows(TargetException.class, () -> method.invoke(...))` | Test bắt sai tầng ngoại lệ | Assert `InvocationTargetException`, rồi kiểm tra `getCause()` |
| Chỉ so message wrapper | Không chứng minh được Throwable gốc | Assert type, message của cause, và identity nếu có fixture |
| Gọi sai overload/tham số mà tưởng target ném lỗi | `IllegalArgumentException` trực tiếp | Kiểm tra dấu hiệu thân target đã chạy |
| Tra method sai rồi trộn `NoSuchMethodException` vào test invoke | Không test được đường thực thi target | Tách test lookup và test invoke |
| Dùng `getCause().getCause()` không kiểm tra | Có thể `NullPointerException` nếu cause chain ngắn | Assert từng tầng theo contract |
| Nuốt `InvocationTargetException` hoặc chỉ log wrapper | Mất bối cảnh lỗi nghiệp vụ | Ghi cause, giữ stack và bối cảnh method; quyết định unwrap rõ ràng |
| Unwrap bằng `new RuntimeException(original.getMessage())` | Mất danh tính, kiểu và stack gốc | Ném lại `original` khi API cho phép, hoặc dùng `new RuntimeException("context", original)` để giữ cause |
| Test với một trường `static lastThrown` trong bộ test chạy song song | Race làm assert identity không ổn định | Fixture riêng, tuần tự hoặc đồng bộ phù hợp |
| Gọi private method mà chưa cấp quyền | Test thất bại ở tầng access | Dùng public target để test wrapper; kiểm tra private access trong bài test riêng |
| Assert nguyên cả stack trace | Test giòn, lệ thuộc JDK | Kiểm tra frame/đặc tính cần thiết |
| Cho rằng mọi cách gọi động đều bọc lỗi bằng wrapper này | Phân tích sai với `MethodHandle.invokeExact` hoặc lời gọi Java trực tiếp | Phân biệt API; kiểm thử riêng quy tắc exception của từng API |

### Khi xây helper unwrap, giữ nguyên Throwable

`Method.invoke` trả về ngoại lệ wrapper để phân biệt code reflection với exception bên trong target. Một adapter có thể muốn **chủ động** đưa exception đích trở lại ranh giới nghiệp vụ:

```java
static Object invokeAndRethrow(
        Method method, Object target, Object... arguments)
        throws Throwable {
    try {
        return method.invoke(target, arguments);
    } catch (InvocationTargetException e) {
        throw e.getCause();
    }
}
```

Đây là đoạn minh họa cần import `Method`/`InvocationTargetException`, không phải chương trình đầy đủ. Việc khai báo `throws Throwable` làm rõ rằng cause có thể là checked exception, unchecked exception **hoặc `Error`**. Trong code ứng dụng thực tế, caller cần chính sách chuyển tiếp, khai báo checked exceptions và log phù hợp. Không bao giờ bắt mọi `Throwable` rồi tiếp tục im lặng sau một lỗi nghiêm trọng.

Nếu interface adapter chỉ khai báo một loại checked exception hẹp, có thể cần ánh xạ ngoại lệ theo hợp đồng đó. Khi phải bọc lại, luôn đặt original làm **cause** thay vì chỉ sao chép message.

## 9. Trường hợp API khác: đừng áp dụng máy móc

- `Constructor.newInstance(...)` cũng có thể ném `InvocationTargetException` khi constructor đích ném exception, nhưng các lỗi trước khi chạy constructor cần tách riêng.
- `MethodHandle.invoke` và `invokeExact` không tuân theo quy tắc wrapper `InvocationTargetException` của `Method.invoke`; chúng có hợp đồng riêng và thường đưa Throwable trực tiếp tới caller.
- Reflection call có thể đi qua proxy/adapters khác: tầng bên ngoài (ví dụ dynamic proxy, future) có thể thêm wrapper riêng. Test phải xác định **lớp nào tạo wrapper** và kiểm tra đúng tầng.
- `InvocationTargetException` tự nó cũng là một class có constructor công khai; nếu chính target chủ động ném một object loại này qua `Method.invoke`, sẽ có **wrapper bên ngoài** và target exception ở tầng bên trong. Đừng phân loại nguyên nhân chỉ bằng tên class nếu không biết chuỗi gọi.

## 10. Checklist cho kiểm thử regression

Trước khi chốt test:

1. Đã chứng minh phương thức đích thực sự được gọi và ném lỗi dự kiến?
2. Đã assert wrapper `InvocationTargetException` ở bên ngoài?
3. `getCause()` khác `null`, đúng type, message và **cùng Throwable** khi có reference?
4. `getTargetException()` có cùng identity với `getCause()`?
5. Cause chain sâu hơn được giữ khi target thiết lập nguyên nhân?
6. Đã có test riêng về receiver/argument sai để tránh nhầm lỗi reflection với lỗi target?
7. Với helper unwrap, đã xác nhận exception gốc được đưa ra và không bị tạo lại?
8. Test chạy ổn trên Java 17+, không phụ thuộc chi tiết stack trace dễ thay đổi?
9. Nếu dùng JUnit 5, runner và dependency đã được khai báo; nếu dùng harness độc lập, stdout khớp đúng?
10. Có tránh chia sẻ trạng thái test khiến kết quả sai khi chạy song song?

## 11. Tự kiểm tra

**Câu 1.** Mã trong target gọi `throw new IllegalArgumentException("bad")`. Caller dùng `Method.invoke` bắt lỗi gì?

**Đáp án:** `InvocationTargetException` ở ngoài, còn `IllegalArgumentException` chính là `getCause()`.

**Câu 2.** Caller truyền `String` vào tham số `int` của `Method.invoke` và target chưa chạy. Có `InvocationTargetException` không?

**Đáp án:** Không; đây là lỗi argument của reflection, thường là `IllegalArgumentException` trực tiếp.

**Câu 3.** `getCause()` và `getTargetException()` của wrapper do `Method.invoke` tạo có trả hai bản sao exception không?

**Đáp án:** Không. Chúng trả cùng đối tượng exception đích; có thể kiểm bằng `==` hoặc JUnit `assertSame`.

**Câu 4.** Target ném một `IOException` có cause là `IllegalStateException`. Wrapper có mất cause chain không?

**Đáp án:** Không. Wrapper mới trỏ tới `IOException`; bản thân `IOException` vẫn giữ quan hệ cause đã thiết lập.

**Câu 5.** Nếu adapter cần ném lại lỗi gốc, nên làm gì?

**Đáp án:** Bắt `InvocationTargetException` rồi `throw e.getCause()` khi chữ ký API cho phép; nếu buộc phải bọc lại, luôn gắn cause gốc.

**Ghi nhớ:** Với `Method.invoke`, hãy **kiểm thử hai tầng**: wrapper `InvocationTargetException` mô tả cơ chế reflection, còn `getCause()` là exception/error do mã đích thật sự ném. Test chất lượng xác nhận **type, identity, message, cause chain và ranh giới trước/sau khi target chạy**.

Tham khảo: [Java 17 `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)), [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).