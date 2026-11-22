# Bao hành vi bằng MethodHandles.tryFinally

Một handle kết quả có cùng MethodType với target. Cleanup luôn được gọi sau khi target kết thúc. Nếu target thành công, tham số failure là null và result là giá trị target trả về. Nếu target ném exception, failure là exception đó; tham số result được đặt thành giá trị mặc định của kiểu trả về. Với target void, không có tham số result.

## 1. Cơ chế

`MethodHandles.tryFinally(target, cleanup)` là một method-handle combinator có từ Java 9. Nó tạo một MethodHandle mới bao quanh `target` bằng hành vi tương đương khối `try-finally`: gọi target, sau đó luôn gọi cleanup để thực hiện phần dọn dẹp hoặc ghi nhận kết quả, bất kể target kết thúc bình thường hay ném exception.

Combinator này hữu ích khi xây dựng pipeline MethodHandle động, nơi việc đo thời gian, ghi audit, giải phóng trạng thái phụ hoặc ghi nhận lỗi cần được gắn vào một handle mà không phải sửa method gốc. Nó không thay thế `try-with-resources` cho quản lý tài nguyên thông thường; hãy dùng nó khi cần ghép hành vi ở cấp MethodHandle.

```java
V target(A...);
V cleanup(Throwable failure, V result, A...);

V adapter(A... args) {
    V result = defaultValueOfV();
    Throwable failure = null;
    try {
        result = target(args);
    } catch (Throwable error) {
        failure = error;
        throw error;
    } finally {
        result = cleanup(failure, result, args);
    }
    return result;
}
```

Đây là pseudocode để hiểu giao thức. Với target trả về `void`, cleanup không nhận tham số result và cũng trả về `void`.

## 2. Chữ ký cleanup

| Target | Chữ ký cleanup |
|---|---|
| `(A...)V`, V khác void | `(Throwable, V, A...)V` |
| `(A...)void` | `(Throwable, A...)void` |

Ở đây `A...` là một prefix của danh sách tham số target. Cleanup có thể bỏ qua một hoặc nhiều tham số cuối của target, nhưng các tham số mà nó nhận phải giữ đúng thứ tự và kiểu tương ứng.

Target `(String, int)int` có thể ghép với cleanup `(Throwable, int, String)int`. Cleanup nhận exception, kết quả int và tham số String đầu tiên; nó bỏ qua tham số int cuối của target.

Các quy tắc:
1. Tham số đầu tiên của cleanup phải nhận được `Throwable`. Nên khai báo đúng kiểu `Throwable`, không thu hẹp thành `Exception` hoặc một exception cụ thể.
2. Nếu target không trả về void, tham số thứ hai của cleanup phải đúng kiểu trả về của target.
3. Các tham số tiếp theo của cleanup phải khớp với một prefix của tham số target.
4. Return type của cleanup phải giống return type của target.
5. Nếu chữ ký không khớp, `MethodHandles.tryFinally` ném `IllegalArgumentException`; đối số null dẫn đến `NullPointerException`.

Nên dùng `Throwable` cho tham số đầu cleanup vì target có thể ném cả `RuntimeException`, `Error` hoặc một loại Throwable khác. Nếu cleanup chỉ nhận `IOException`, một lỗi không thuộc kiểu đó có thể làm adapter ném `ClassCastException` trước khi cleanup xử lý được exception gốc.

## 3. Thành công, lỗi và cleanup

| Kết quả target | Tham số cleanup | Kết quả handle |
|---|---|---|
| Trả về bình thường | failure = null; result = giá trị target | Trả về giá trị cleanup trả về |
| Ném exception; cleanup bình thường | failure = exception; result = giá trị mặc định của kiểu trả về | Ném lại exception gốc |
| Ném exception; cleanup cũng ném exception | failure nhận exception gốc; result là giá trị mặc định | Ném exception do cleanup tạo ra |

Giá trị cleanup trả về sẽ trở thành kết quả của handle ghép khi target thành công. Nếu muốn giữ nguyên kết quả target, cleanup cần trả lại tham số result. Nếu cleanup trả một giá trị khác, nó có thể biến đổi kết quả bình thường của target.

Khi target đã ném exception, cleanup trả về bình thường không biến exception thành kết quả bình thường. Exception gốc vẫn được ném lại sau khi cleanup hoàn tất. Nếu cleanup ném exception mới, exception mới thay thế exception gốc; `tryFinally` không tự động gom exception gốc vào suppressed như try-with-resources.

## 4. Ví dụ chạy được

**Main.java**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    private static int parseAndMultiply(String input, int factor) {
        return Math.multiplyExact(Integer.parseInt(input), factor);
    }

    private static int fallback(NumberFormatException failure,
                                String input, int factor) {
        System.out.println("fallback input=" + input);
        return -1;
    }

    private static int cleanup(Throwable failure, int result, String input) {
        String status = failure == null
                ? "none" : failure.getClass().getSimpleName();
        System.out.println("cleanup input=" + input
                + ", failure=" + status
                + ", targetResult=" + result);
        return result;
    }

    private static int cleanupThrows(Throwable failure, int result, String input) {
        throw new IllegalStateException("cleanup failed");
    }

    private static void writeAudit(Throwable failure, String label) {
        String status = failure == null
                ? "none" : failure.getClass().getSimpleName();
        System.out.println("cleanup void target: " + label + ", failure=" + status);
    }

    private static void runTask(String label) {
        System.out.println("target void: " + label);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(
                Main.class, "parseAndMultiply",
                MethodType.methodType(int.class, String.class, int.class));
        MethodHandle cleanup = lookup.findStatic(
                Main.class, "cleanup",
                MethodType.methodType(
                        int.class, Throwable.class, int.class, String.class));
        MethodHandle guarded = MethodHandles.tryFinally(target, cleanup);

        int value = (int) guarded.invokeExact("21", 2);
        System.out.println("success result=" + value);

        try {
            int ignored = (int) guarded.invokeExact("oops", 2);
            throw new AssertionError("Expected NumberFormatException, got " + ignored);
        } catch (NumberFormatException expected) {
            System.out.println("propagated exception="
                    + expected.getClass().getSimpleName());
        }

        MethodHandle failingCleanup = lookup.findStatic(
                Main.class, "cleanupThrows",
                MethodType.methodType(
                        int.class, Throwable.class, int.class, String.class));
        MethodHandle guardedWithFailingCleanup =
                MethodHandles.tryFinally(target, failingCleanup);
        try {
            int ignored = (int) guardedWithFailingCleanup.invokeExact("oops", 2);
            throw new AssertionError("Expected cleanup failure, got " + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("cleanup failure replaced target exception="
                    + expected.getClass().getSimpleName());
        }

        MethodHandle fallback = lookup.findStatic(
                Main.class, "fallback",
                MethodType.methodType(int.class,
                        NumberFormatException.class, String.class, int.class));
        MethodHandle caught = MethodHandles.catchException(
                target, NumberFormatException.class, fallback);
        MethodHandle converted = MethodHandles.tryFinally(caught, cleanup);
        int fallbackValue = (int) converted.invokeExact("oops", 2);
        System.out.println("converted result=" + fallbackValue);

        MethodHandle voidTarget = lookup.findStatic(
                Main.class, "runTask",
                MethodType.methodType(void.class, String.class));
        MethodHandle voidCleanup = lookup.findStatic(
                Main.class, "writeAudit",
                MethodType.methodType(void.class, Throwable.class, String.class));
        MethodHandle guardedVoid = MethodHandles.tryFinally(voidTarget, voidCleanup);
        guardedVoid.invokeExact("refresh");
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả:

```text
cleanup input=21, failure=none, targetResult=42
success result=42
cleanup input=oops, failure=NumberFormatException, targetResult=0
propagated exception=NumberFormatException
cleanup failure replaced target exception=IllegalStateException
fallback input=oops
cleanup input=oops, failure=none, targetResult=-1
converted result=-1
target void: refresh
cleanup void target: refresh, failure=none
```

Trong ví dụ, target có MethodType `(String, int)int`. Cleanup có kiểu `(Throwable, int, String)int` nên nhận prefix String của target và bỏ qua đối số factor. Khi target ném lỗi, tham số result của cleanup là 0 vì return type là int.

## 5. Target void

Nếu target trả về `void`, cleanup không có tham số result. Chữ ký là `(Throwable, A...)void`:

```java
private static void runTask(String label) { }

private static void writeAudit(Throwable failure, String label) {
    // Ghi nhận trạng thái hoàn tất.
}

MethodHandle voidTarget = lookup.findStatic(
        Main.class, "runTask",
        MethodType.methodType(void.class, String.class));
MethodHandle voidCleanup = lookup.findStatic(
        Main.class, "writeAudit",
        MethodType.methodType(void.class, Throwable.class, String.class));

MethodHandle guardedVoid = MethodHandles.tryFinally(voidTarget, voidCleanup);
guardedVoid.invokeExact("refresh");
```

Cả hai handle đều phải trả về void. Cleanup chỉ nhận exception và các tham số đầu được chọn từ target.

## 6. Cleanup ném exception

Nếu target ném `NumberFormatException` nhưng cleanup ném `IllegalStateException`, caller nhận `IllegalStateException`. Đây là hành vi tương tự exception phát sinh trong khối finally thông thường làm lu mờ exception đang được truyền ra.

Vì vậy cleanup nên ngắn, có kiểm soát và tránh ném lỗi không cần thiết. Nếu cleanup thực hiện ghi log, đóng trạng thái phụ hoặc giải phóng tài nguyên, cần quyết định rõ cách xử lý lỗi cleanup để không che mất nguyên nhân chính.

## 7. Chuyển exception thành fallback

`tryFinally` không bắt và chuyển exception thành kết quả bình thường. Nếu muốn biến exception cụ thể thành fallback result, hãy dùng `catchException` để xử lý exception trước, rồi mới bọc handle đó bằng `tryFinally`.

```java
MethodHandle fallback = lookup.findStatic(
        Main.class, "fallback",
        MethodType.methodType(
                int.class, NumberFormatException.class, String.class, int.class));

MethodHandle caught = MethodHandles.catchException(
        target, NumberFormatException.class, fallback);

MethodHandle guarded = MethodHandles.tryFinally(caught, cleanup);
int value = (int) guarded.invokeExact("oops", 2);
```

`catchException` bắt `NumberFormatException` và gọi fallback trả về -1. Từ góc nhìn của `tryFinally`, handle `caught` đã hoàn tất bình thường với kết quả -1, nên cleanup nhận `failure = null` và `result = -1`. Exception khác kiểu không được handler xử lý vẫn truyền ra ngoài và được cleanup quan sát.

## 8. Thứ tự ghép combinator

- `tryFinally(target, cleanup)`: cleanup nhìn thấy exception do target ném.
- `tryFinally(catchException(target, E.class, handler), cleanup)`: nếu target ném E và handler trả về bình thường, cleanup nhìn thấy kết quả handler và failure = null.
- Nếu handler ném exception mới, cleanup nhìn thấy exception mới đó.
- Nếu cleanup ném exception, lỗi cleanup có thể thay thế lỗi mà target hoặc handler đang truyền ra.

Hãy thiết kế thứ tự ghép theo yêu cầu nghiệp vụ: cần ghi nhận exception gốc hay cần chuyển đổi nó trước. Viết rõ MethodType của từng handle và kiểm thử cả nhánh thành công lẫn nhánh lỗi.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Cleanup không nhận Throwable đầu tiên | Sai cấu trúc tham số | Thêm tham số đầu kiểu Throwable |
| Cleanup dùng Exception thay Throwable | Có thể không nhận được Error hoặc Throwable khác | Ưu tiên Throwable |
| Quên tham số result | Target có return type khác void | Thêm tham số thứ hai đúng kiểu return |
| Thêm result cho target void | Void không có giá trị kết quả | Chỉ nhận Throwable rồi đến các đối số |
| Cleanup trả sai kiểu | Return type target và cleanup không trùng | Dùng cùng return type |
| Cleanup nhận sai đối số target | Các đối số còn lại không phải prefix cùng kiểu | Giữ đúng thứ tự và kiểu; chỉ bỏ đối số cuối |
| Mong cleanup nuốt exception | tryFinally không chuyển exception thành normal return | Dùng catchException trước nếu cần fallback |
| Cleanup ném lỗi không chủ đích | Lỗi cleanup thay thế lỗi target | Xử lý lỗi cleanup có chủ đích |
| Nghĩ cleanup luôn nhận kết quả thật | Target đã ném exception | Với primitive/reference, cleanup nhận giá trị mặc định làm placeholder |

## 10. Khi nào nên dùng tryFinally?

Dùng `MethodHandles.tryFinally` khi cần ghép một thao tác dọn dẹp hoặc quan sát vào MethodHandle động, ví dụ ghi thời gian thực thi, ghi audit thành công/thất bại, khôi phục trạng thái phụ, hoặc xây dựng adapter cho framework cần biến đổi MethodHandle mà không sửa method gốc.

Nếu chỉ gọi một method bình thường và quản lý tài nguyên, cú pháp `try-finally` hoặc `try-with-resources` thường dễ đọc hơn. `tryFinally` phát huy giá trị khi hành vi cần được biểu diễn, ghép và truyền tiếp như một MethodHandle.

`MethodHandles.tryFinally` là combinator Java 9 dùng để bao một target handle bằng cleanup handle. Cleanup luôn được gọi và nhận exception cùng kết quả target (nếu có); exception gốc vẫn được truyền ra nếu cleanup kết thúc bình thường. Muốn chuyển exception thành fallback result, hãy dùng `catchException` trước `tryFinally`. Chữ ký cleanup phải khớp chính xác với return type, Throwable và prefix đối số của target.
