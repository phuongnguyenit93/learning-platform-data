# 13.6 Thích nghi handle sang interface bằng MethodHandleProxies và giới hạn áp dụng

## 1. Khi MethodHandle cần được sử dụng như một interface

Trong Java, `MethodHandle` là một tham chiếu có kiểu đến phép gọi có thể thực thi, thường được tạo bằng `MethodHandles.Lookup` hoặc các combinator trong `MethodHandles`. Tuy nhiên, nhiều API Java **không nhận MethodHandle**; chúng yêu cầu một interface cụ thể như `Runnable`, `Callable<V>`, `Comparator<T>`, một callback của ứng dụng, hoặc một contract plugin.

Thay vì viết một lớp implementation trung gian chỉ để chuyển lời gọi, Java cung cấp:

```java
T adapter = MethodHandleProxies.asInterfaceInstance(
        InterfaceType.class, targetHandle);
```

Đây là **cú pháp minh họa**: `InterfaceType` phải là interface đáp ứng điều kiện của factory, còn `targetHandle` là `MethodHandle` có thể thích nghi với phương thức cần triển khai. Factory trả một object **implement interface được yêu cầu**, chuyển lời gọi phương thức trừu tượng của interface tới target handle.

Ví dụ ý tưởng: hệ thống dynamic runtime đã có `MethodHandle` kiểu `(long)String`, nhưng một SDK bên ngoài muốn interface:

```java
public interface IntToText {
    String apply(int value);
}
```

Nếu interface hợp lệ và conversion `int → long` được phép, `asInterfaceInstance` có thể cung cấp `IntToText` mà không phải tự viết class adapter.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Hiểu điều kiện của **single-method interface**, không đồng nhất máy móc với mọi cách dùng `@FunctionalInterface`.
2. Tạo wrapper bằng `MethodHandleProxies.asInterfaceInstance` và kiểm tra `isWrapperInstance`, `wrapperInstanceType`, `wrapperInstanceTarget`.
3. Giải thích **chuyển đổi từng chữ ký** theo `MethodHandle.asType`, hỗ trợ overload cùng tên/bridge methods và default methods.
4. Xử lý `WrongMethodTypeException`, `IllegalArgumentException`, `NullPointerException`, `UndeclaredThrowableException`.
5. Nêu ranh giới **public, non-sealed interface, single abstract method name**, kiểm tra quyền/capability, class loader, JPMS và trường hợp không nên dùng API.
6. Phân biệt phương pháp này với lambda Java, `LambdaMetafactory` và `Proxy.newProxyInstance`.

`MethodHandleProxies` xuất hiện từ **Java 7**. Ví dụ dùng **Java 17+** vì Java 17 có khái niệm `sealed interface` cần lưu ý trong điều kiện đầu vào.

## 2. API cốt lõi của MethodHandleProxies

Lớp `java.lang.invoke.MethodHandleProxies` cung cấp bốn phương thức static chính:

| API | Đầu vào | Ý nghĩa |
| --- | --- | --- |
| `<T> T asInterfaceInstance(Class<T> intfc, MethodHandle target)` | Kiểu interface và target handle | Tạo adapter implement interface, ủy quyền lời gọi phương thức theo target. |
| `boolean isWrapperInstance(Object x)` | Một object bất kỳ | Kiểm tra object có phải wrapper do `asInterfaceInstance` tạo ra không; `null` cho `false`. |
| `MethodHandle wrapperInstanceTarget(Object x)` | Wrapper hợp lệ | Thu lại handle **tương đương về hành vi** với target của wrapper. |
| `Class<?> wrapperInstanceType(Object x)` | Wrapper hợp lệ | Thu lại chính interface type mà factory đã dùng để tạo wrapper. |

Chỉ có `asInterfaceInstance` **tạo adapter**. Ba phương thức còn lại phục vụ kiểm tra/khôi phục metadata của wrapper.

**Đừng giả định** `wrapperInstanceTarget(x) == originalTarget` luôn đúng theo identity của object. Hợp đồng Javadoc bảo đảm handle khôi phục **tương đương về hành vi**, không yêu cầu trả đúng cùng object đã truyền vào factory. Khi muốn kiểm tra, dùng `type()` và gọi thử theo contract, không dùng `==` làm tiêu chí chính.

`wrapperInstanceTarget` và `wrapperInstanceType` **không** phải các hàm phân tích mọi lambda/adapter bất kỳ. Nếu đưa vào object không do `asInterfaceInstance` tạo, chúng ném `IllegalArgumentException`. Nên gọi `isWrapperInstance(x)` trước nếu nguồn object không tin cậy.

### 2.1. Ví dụ điển hình, chưa phải chương trình độc lập

```java
// Đoạn minh họa trong một method đã có đúng kiểu target.
IntToText adapter = MethodHandleProxies.asInterfaceInstance(
        IntToText.class, target);
String value = adapter.apply(42);
boolean recognized = MethodHandleProxies.isWrapperInstance(adapter);
```

Ở đây target phải có **số đối số/kiểu trả về** có thể thích nghi với `String apply(int)`. Nếu target không thể được chuyển, factory ném lỗi **trước khi tạo xong wrapper**; không có một adapter “bất kỳ kiểu nào cũng gọi được”.

## 3. Điều kiện của interface — phần dễ hiểu sai nhất

Javadoc Java SE 17 dùng khái niệm **single-method interface** (interface có **một tên phương thức trừu tượng duy nhất**). Khi xác định tên phương thức duy nhất, API **bỏ qua**:

- Các method public của `Object`: `toString`, `equals`, `hashCode`.
- Các method **default/non-abstract** của interface, vì chúng có implementation riêng.

Ngoài điều kiện tên phương thức, `intfc` phải:

1. Thực sự là **interface**, không phải class trừu tượng.
2. Có quyền truy cập **public** (không phải package-private/private interface).
3. **Không phải sealed interface** trên Java 17+.
4. Có một tên method trừu tượng duy nhất sau khi bỏ qua các trường hợp trên; những declaration trừu tượng có **cùng tên** vẫn có thể có nhiều descriptor do overload/bridge.
5. Có thể thích nghi `target` tới **tất cả** các chữ ký cần xử lý theo `MethodHandle.asType`.

### 3.1. Phân biệt “một tên method” với “đúng một declaration”

Hai interface minh họa:

```java
public interface Renderer {
    String render(int n);
    String render(long n);
    default String label() { return "DEFAULT"; }
}

public interface TwoNames {
    String render(int n);
    String format(int n);
}
```

Đây là **các khai báo minh họa**; trong file thực tế, nếu là top-level public types thì mỗi loại cần file Java tương ứng. Hoặc có thể đặt chúng làm **nested public interfaces** trong một public class như ví dụ runnable ở mục 6.

- `Renderer` có **hai declaration nhưng cùng tên `render`**. Nó *có thể* được chấp nhận bởi `MethodHandleProxies` nếu một target có thể adapt được đến **cả hai** method descriptors.
- `label()` là default method, không tính vào danh sách tên phương thức trừu tượng được factory cần triển khai.
- `TwoNames` có hai **tên trừu tượng khác nhau**: `render` và `format`, nên không hợp lệ.
- Các method Object như `equals(Object)` có thể được interface khai báo lại nhưng **không** làm nó mất tính single-method theo quy tắc này.

**Khác với `@FunctionalInterface`:** một interface có overload `render(int)` và `render(long)` thường **không phải functional interface hợp lệ cho lambda Java**, vì có hai abstract method signatures không tương đương; nhưng `MethodHandleProxies` cho phép **cùng một tên có nhiều descriptor** nếu target adapt được tới từng descriptor. Ngược lại, một `@FunctionalInterface` hợp lệ vẫn có thể không được `MethodHandleProxies` chấp nhận nếu interface không public hoặc là sealed.

Ví dụ thường gặp trong Java API: `Comparator` là một single-method interface theo cách đếm của `MethodHandleProxies` vì `compare` là tên method abstract cần triển khai, `equals` theo Object và các default methods khác không tính.

### 3.2. Vì sao sealed interface không được hỗ trợ?

Một `sealed interface` ràng buộc những lớp được phép implements qua `permits`. `MethodHandleProxies` tạo wrapper implementation do runtime quản lý; contract Java 17 yêu cầu interface **not sealed**. Khi đầu vào sealed, factory ném `IllegalArgumentException` thay vì lách qua `permits`.

Không thể sửa bằng `setAccessible(true)`, lookup có quyền private hoặc đổi class loader tùy ý. Đây là **giới hạn thiết kế của factory**; muốn adapter cho sealed hierarchy, cần implementation hợp lệ được liệt kê trong `permits` hoặc một API khác phù hợp.

### 3.3. Interface được implement đến mức nào?

Wrapper implement **interface được yêu cầu và các superinterface của nó**, không tự thêm mọi interface có cùng một phương thức. Do đó không thể giả định một wrapper `IntToText` cũng `instanceof Function<Integer,String>` chỉ vì hai API có ý tưởng tương tự.

Javadoc còn không bảo đảm factory tạo một object instance mới mỗi lần gọi: kết quả được định nghĩa theo **hành vi**, không theo identity. Tránh xây logic yêu cầu mọi lần `asInterfaceInstance` trả một identity hoàn toàn mới.

## 4. Cơ chế chuyển lời gọi: từ method interface đến target MethodHandle

Khi `adapter.method(args...)` được gọi:

1. JVM dispatch method interface qua wrapper.
2. Wrapper chuyển input về target handle **như thể gọi `target.invoke(...)`** (không bắt buộc `invokeExact`).
3. Một chuyển đổi tương đương `target.asType(interfaceMethodType)` được kiểm tra cho **từng method descriptor** lúc tạo adapter.
4. Nếu type thích nghi được, kết quả hoặc exception từ target được chuyển/truyền lại theo contract của interface.

Điều này giải thích vì sao target `(long)String` có thể phục vụ `String apply(int)`: input `int` được widen thành `long`. Nhưng target `()String` không thể tự nhận một tham số int nếu bạn chưa dùng combinator như `dropArguments` để bổ sung tham số giả.

### 4.1. So sánh một số phép chuyển

| Interface method | Target type | Kết quả |
| --- | --- | --- |
| `String apply(int)` | `(long)String` | Hợp lệ: int → long. |
| `String apply(long)` | `(long)String` | Hợp lệ: khớp chính xác. |
| `String apply(int)` | `()String` | Không hợp lệ: số tham số khác; `WrongMethodTypeException` khi tạo wrapper. |
| `int compute(int)` | `(int)int` | Hợp lệ: chữ ký trùng. |
| `String apply(String)` | `(int)String` | Không có chuyển String → int tự động theo `asType`; cần adapter/chuyển đổi riêng. |

Không phải **mọi** chuyển đổi Java đều được phép ở `MethodHandle.asType`: box/unbox, cast tham chiếu và widening primitive có quy tắc riêng; không tự parse chuỗi số, không tự bỏ đối số, không thể biến return type tùy ý. Với generic interface, Java erasure và bridge methods cũng ảnh hưởng descriptor runtime.

Khi target có thể throw exception, factory không thể dùng kiểu trả về để biết logic sẽ ném gì; ngoại lệ được xử lý ở lúc **gọi method trên wrapper**.

### 4.2. Overload cùng tên và bridge methods

Nếu interface khai báo `render(int)` và `render(long)`, factory xử lý **từng descriptor**. Target `(long)String` sẽ dùng adaptation:

```text
Renderer.render(int)  -> adapt (int)String  -> (long)String target
Renderer.render(long) -> adapt (long)String -> (long)String target
```

Trường hợp generic bridge method tương tự: class file có thể chứa bridge với descriptor khác, và API tính adaptation cho từng declaration. Điều kiện không phải “một method bytecode duy nhất”, mà là **một tên abstract method** với những descriptor chuyển được về target.

**Giới hạn:** nếu chỉ một overload không thể adapt, factory có thể ném `WrongMethodTypeException` ngay khi tạo, dù overload khác hoàn toàn phù hợp. Không dùng một target cho các overload có semantics khác nhau nếu chúng không thực sự có thể chia sẻ implementation.

## 5. Ví dụ Java 17 số 1 — tạo interface wrapper và lấy lại target

Tạo file **`MethodHandleProxiesBasicsDemo.java`**:

```java
import java.lang.invoke.*;

public class MethodHandleProxiesBasicsDemo {
    public interface IntToText {
        String apply(int value);
    }

    private static String format(long value) {
        return "value=" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesBasicsDemo.class,
                "format",
                MethodType.methodType(String.class, long.class));

        IntToText adapter =
                MethodHandleProxies.asInterfaceInstance(
                        IntToText.class, target);

        System.out.println("interface call: " + adapter.apply(7));
        System.out.println("instanceof: " + (adapter instanceof IntToText));
        System.out.println("recognized: "
                + MethodHandleProxies.isWrapperInstance(adapter));
        System.out.println("type recovered: "
                + (MethodHandleProxies.wrapperInstanceType(adapter)
                        == IntToText.class));

        MethodHandle recovered =
                MethodHandleProxies.wrapperInstanceTarget(adapter);
        System.out.println("target type: " + recovered.type());
        System.out.println("target call: "
                + (String) recovered.invoke(8L));

        System.out.println("ordinary instance recognized: "
                + MethodHandleProxies.isWrapperInstance(
                        (IntToText) n -> "normal:" + n));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesBasicsDemo.java
java MethodHandleProxiesBasicsDemo
```

Stdout:

```text
interface call: value=7
instanceof: true
recognized: true
type recovered: true
target type: (long)String
target call: value=8
ordinary instance recognized: false
```

**Giải thích từng phần:**

1. `findStatic` tạo handle tới **private static** method `format(long)`. Lookup trong chính class demo có quyền truy cập method này, nên target hợp lệ. `MethodHandleProxies` **không tự đi tìm private method**; nó chỉ nhận handle đã được tạo.
2. Interface yêu cầu `apply(int)`; target nhận `long`. Factory kiểm tra adaptation `int → long` trước khi trả wrapper, nên `adapter.apply(7)` cho `value=7`.
3. Wrapper thực sự `instanceof IntToText` và `isWrapperInstance(adapter)` trả true.
4. `wrapperInstanceType(adapter)` trả lại `Class` chính xác của `IntToText`.
5. `wrapperInstanceTarget(adapter)` trả một handle có hành vi tương đương target, ở demo có `type() == (long)String` và gọi `invoke(8L)` trả `value=8`. **Đừng tổng quát hóa kết quả `target.type()` cụ thể này thành yêu cầu mọi wrapper phải trả đúng object target gốc.**
6. Một lambda Java thông thường implement `IntToText` **không** phải sản phẩm của `asInterfaceInstance`; `isWrapperInstance` trả false. API nhận dạng này không dùng để phát hiện tất cả object implement một interface.

**Cẩn thận với quyền:** trong ví dụ wrapper công khai hóa hành vi của một private method thông qua interface public nested. Đó là capability được trao có chủ đích; nếu method nhạy cảm, không phát adapter ra API không tin cậy.

## 6. Ví dụ Java 17 số 2 — overload, default method và các interface bị từ chối

Tạo file **`MethodHandleProxiesOverloadDemo.java`**:

```java
import java.lang.invoke.*;

public class MethodHandleProxiesOverloadDemo {
    public interface Renderer {
        String render(int x);
        String render(long x);

        default String label() {
            return "DEFAULT";
        }
    }

    public interface TwoNames {
        String first(int x);
        String second(int x);
    }

    interface PackagePrivate {
        String render(long x);
    }

    public sealed interface SealedRenderer permits SealedImpl {
        String render(long x);
    }

    public static final class SealedImpl implements SealedRenderer {
        public String render(long x) {
            return "impl";
        }
    }

    private static String show(long value) {
        return "num=" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesOverloadDemo.class,
                "show",
                MethodType.methodType(String.class, long.class));

        Renderer renderer =
                MethodHandleProxies.asInterfaceInstance(
                        Renderer.class, target);

        System.out.println("render int: " + renderer.render(3));
        System.out.println("render long: " + renderer.render(4L));
        System.out.println("default method: " + renderer.label());
        System.out.println("object method nonnull: "
                + (renderer.toString() != null));

        try {
            MethodHandleProxies.asInterfaceInstance(
                    TwoNames.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("two names: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    PackagePrivate.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("nonpublic: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    SealedRenderer.class, target);
        } catch (IllegalArgumentException expected) {
            System.out.println("sealed: rejected");
        }
        try {
            MethodHandleProxies.asInterfaceInstance(
                    java.util.function.Function.class,
                    MethodHandles.constant(String.class, "fixed"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("incompatible arity: rejected");
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesOverloadDemo.java
java MethodHandleProxiesOverloadDemo
```

Stdout:

```text
render int: num=3
render long: num=4
default method: DEFAULT
object method nonnull: true
two names: rejected
nonpublic: rejected
sealed: rejected
incompatible arity: rejected
```

**Giải thích:**

- `Renderer` có hai **overload cùng tên `render`** và một default `label`. Target `(long)String` adapt được tới cả `render(int)` và `render(long)`, nên wrapper hợp lệ.
- `renderer.label()` chạy default method riêng, không đi qua target `show`. Các method Object được loại khỏi phép đếm tên abstract, nhưng **đừng phụ thuộc** vào chi tiết `toString`/`equals`/`hashCode` của lớp wrapper do runtime sinh.
- `TwoNames` có hai **tên** method trừu tượng, trái hợp đồng của factory.
- `PackagePrivate` không public và `SealedRenderer` là sealed trên Java 17, cả hai bị từ chối dù code caller nhìn thấy các type đó.
- `Function` cần phương thức `apply(Object)Object` (sau erasure), nhưng target constant `()String` không nhận input. Factory không tự thêm đối số, nên ném `WrongMethodTypeException`.

Lưu ý: class demo này **không** đặt `@FunctionalInterface` lên `Renderer` vì hai overload cùng tên không phải một functional method signature duy nhất cho lambda Java; tuy nhiên nó **vẫn** là single-method interface hợp lệ theo định nghĩa đặc biệt của `MethodHandleProxies`.

## 7. Ngoại lệ khi gọi wrapper: checked và unchecked

Một `MethodHandle` có thể ném bất kỳ `Throwable`. Java method signature của interface lại có thể **không khai báo** checked exception đó. `MethodHandleProxies` có quy tắc:

- Exception **unchecked** (chẳng hạn `RuntimeException`, `Error`) được truyền theo hành vi thông thường.
- Checked exception **được khai báo** bởi phương thức interface có thể được ném trực tiếp tới caller.
- Checked exception **không được khai báo** (và các checked throwable không phù hợp) sẽ bị **bọc** trong `java.lang.reflect.UndeclaredThrowableException`.
- Factory không ném ngoại lệ nghiệp vụ chỉ vì target **có thể** throw; lỗi xảy ra khi lời gọi thực sự đi vào nhánh ném của target.

### 7.1. Ví dụ Java 17 số 3 — cùng target, hai hợp đồng exception khác nhau

Tạo file **`MethodHandleProxiesExceptionsDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.*;
import java.lang.reflect.UndeclaredThrowableException;

public class MethodHandleProxiesExceptionsDemo {
    public interface PlainAction {
        String run();
    }

    public interface CheckedAction {
        String run() throws IOException;
    }

    public interface IntegerInput {
        String run(int number);
    }

    private static String fail() throws IOException {
        throw new IOException("disk-offline");
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                MethodHandleProxiesExceptionsDemo.class,
                "fail",
                MethodType.methodType(String.class));

        PlainAction plain =
                MethodHandleProxies.asInterfaceInstance(
                        PlainAction.class, target);
        CheckedAction checked =
                MethodHandleProxies.asInterfaceInstance(
                        CheckedAction.class, target);

        try {
            plain.run();
        } catch (UndeclaredThrowableException e) {
            System.out.println("undeclared wrapper: "
                    + e.getUndeclaredThrowable()
                            .getClass().getSimpleName());
            System.out.println("undeclared message: "
                    + e.getUndeclaredThrowable().getMessage());
        }

        try {
            checked.run();
        } catch (IOException e) {
            System.out.println("declared direct: " + e.getMessage());
        }

        System.out.println("null recognized: "
                + MethodHandleProxies.isWrapperInstance(null));

        try {
            MethodHandleProxies.wrapperInstanceTarget(
                    (PlainAction) () -> "ordinary");
        } catch (IllegalArgumentException e) {
            System.out.println("unwrap ordinary: rejected");
        }

        try {
            MethodHandleProxies.asInterfaceInstance(
                    IntegerInput.class, target);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrong argument count: rejected");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 MethodHandleProxiesExceptionsDemo.java
java MethodHandleProxiesExceptionsDemo
```

Stdout:

```text
undeclared wrapper: IOException
undeclared message: disk-offline
declared direct: disk-offline
null recognized: false
unwrap ordinary: rejected
wrong argument count: rejected
```

**Phân tích:**

1. Hai wrapper có cùng target `()String` nên cùng **ném IOException** khi gọi `run()`.
2. Interface `PlainAction.run()` **không** khai báo checked exception; wrapper bọc nó thành `UndeclaredThrowableException`. Dùng `getUndeclaredThrowable()` (hoặc `getCause()`) để truy xuất nguyên nhân khi debug.
3. Interface `CheckedAction.run() throws IOException` cho phép exception được truyền trực tiếp, nên catch `IOException` hoạt động như contract Java bình thường.
4. `isWrapperInstance(null)` trả false; wrapper do **lambda thường** tạo không được `wrapperInstanceTarget` chấp nhận.
5. `IntegerInput.run(int)` không tương thích với target `()String` vì thiếu tham số. Lỗi `WrongMethodTypeException` xuất hiện ở **lúc tạo adapter**, tách biệt với IOException khi invoke.

Với framework, cần quy định rõ **exception contract** của callback. Đừng để checked exception biến thành `UndeclaredThrowableException` ở tầng ngoài rồi bị log như một lỗi không rõ nguồn.

## 8. Bảng lỗi và thời điểm xảy ra

| Điều kiện | Ngoại lệ thường gặp | Thời điểm | Hướng khắc phục |
| --- | --- | --- | --- |
| `intfc == null` hoặc `target == null` | `NullPointerException` | Gọi factory | Không truyền null; validate trước. |
| `intfc` là class, không phải interface | `IllegalArgumentException` | Factory | Chọn interface public hợp lệ. |
| Interface package-private hoặc `sealed` | `IllegalArgumentException` | Factory | Dùng public, non-sealed interface theo contract. |
| Interface có hai tên abstract method khác nhau | `IllegalArgumentException` | Factory | Viết adapter thủ công hoặc dùng `Proxy` nếu cần nhiều method khác tên. |
| Interface có overload nhưng một descriptor không thích nghi được | `WrongMethodTypeException` | Factory | Chỉnh `target.asType`/combinator cho đúng hoặc tách các case. |
| Interface cần 1 tham số, target có 0 | `WrongMethodTypeException` | Factory | Dùng `dropArguments` nếu được phép bỏ input, hoặc sửa target. |
| Target ném checked exception interface không khai báo | `UndeclaredThrowableException` | Khi gọi method qua wrapper | Khai báo checked exception nếu phù hợp hoặc xử lý nguyên nhân. |
| `wrapperInstanceTarget(x)` với lambda/object thường | `IllegalArgumentException` | Khi unwrap | Kiểm tra `isWrapperInstance(x)` trước. |
| Target nhận reference khác kiểu thực tế | `ClassCastException` hoặc lỗi chuyển kiểu liên quan | Khi gọi | Xác định erasure, cast, conversion, validate dữ liệu. |
| Adapter đã nhận handle tới logic private, bị trao cho code khác | Rủi ro capability | Sau khi expose wrapper | Không công bố adapter khi quyền của target không nên được chia sẻ. |

### 8.1. Chuyển đổi trước hay sau khi tạo?

Javadoc yêu cầu type của target được kiểm tra **trước khi wrapper được tạo**, như thể áp dụng `asType` cho từng declaration cần triển khai. Nghĩa là một mismatch **không thể** adapt sẽ phát hiện ở factory. Nhưng nếu adaptation kiểu tham chiếu có thể được chấp nhận về mặt descriptor và dữ liệu cụ thể mới không hợp lệ, lỗi như `ClassCastException` có thể phát sinh **ở lúc invoke**.

Ví dụ, interface generic thường có descriptor sau erasure như `(Object)Object`. Chuyển Object thành kiểu cụ thể có thể là dynamic cast; đừng suy rằng test với một giá trị Integer thành công đồng nghĩa mọi Object đều được target xử lý.

### 8.2. Object methods, default methods và identity

Object wrapper vẫn có các method như `toString`, `equals`, `hashCode`; các method đó **không được tính** là tên abstract của single-method interface. Nhưng đừng ép chúng trở thành đường gọi nghiệp vụ đến target. Nếu cần so sánh callback hoặc cache, nên dùng khóa/metadata rõ ràng thay vì dựa vào class name hoặc hình dạng runtime của wrapper.

Default method như `Renderer.label()` có thể hoạt động theo implementation mặc định của interface; nó không được chuyển thành một nhánh riêng gọi handle `show`. Nếu muốn nhiều **tên** method với semantics riêng, factory này không phải lời giải tổng quát.

## 9. So sánh với lambda, method reference, LambdaMetafactory và dynamic Proxy

| Cách triển khai | Ưu điểm | Giới hạn / khi tránh |
| --- | --- | --- |
| **Lambda Java** `x -> compute(x)` | Gọn, rõ kiểu compile-time, dễ đọc. | Cần code Java hoặc method reference phù hợp lúc biên dịch; không trực tiếp lấy một MethodHandle động tùy ý làm callback nếu chưa có adapter. |
| **MethodHandleProxies.asInterfaceInstance** | Biến một `MethodHandle` đã có thành object implements public single-method interface; xử lý `asType`; dễ dùng trong runtime động. | Không hỗ trợ non-public/sealed interface, nhiều tên abstract method; có wrapper indirection; cần quản lý checked exceptions. |
| **LambdaMetafactory** | Công cụ liên kết lambda/SAM ở cấp `invokedynamic` với Lookup và call-site semantics; thường phù hợp khi xây runtime/bytecode generator tinh chỉnh. | Bootstrap, invoked type và signature constraints phức tạp hơn; không thay thế trực tiếp một dòng `asInterfaceInstance`. |
| **Proxy.newProxyInstance** | Có thể triển khai **nhiều method khác tên** với `InvocationHandler` xử lý riêng; hỗ trợ nhiều trường hợp động. | Yêu cầu dispatch qua handler/reflection semantics, lập bảng method và xử lý default methods/exceptions có chủ đích; không cùng contract đơn giản với MethodHandleProxies. |
| **Adapter class thủ công** | Tối đa quyền kiểm soát validation, exception policy, logging, ngữ nghĩa từng method. | Nhiều boilerplate; không tự động thích hợp cho method handles được chọn runtime. |

### 9.1. Khi dùng MethodHandleProxies là hợp lý

- Một plugin API public yêu cầu interface callback chỉ có một tên method, trong khi application đã có method handle liên kết từ cấu hình runtime.
- Một dispatch pipeline đang dùng MethodHandle nhưng một library bên ngoài chỉ nhận `Runnable`, `Comparator` hoặc callback interface tương tự.
- Cần thử nghiệm nhanh một contract typed interface trên một method handle đang có, mà không phải sinh bytecode riêng.

### 9.2. Khi nên chọn công cụ khác

- Interface **không public hoặc sealed**: phải thay thiết kế interface/implementation, không thể ép factory chấp nhận bằng reflection.
- Interface có **nhiều method abstract tên khác nhau**: adapter class hoặc dynamic Proxy có thể phù hợp hơn.
- Cần kiểm soát chi tiết semantics của từng overload, logging, retry hoặc policy ngoại lệ: wrapper tự viết có thể dễ bảo trì hơn.
- Một ứng dụng hiệu năng cao, cực kỳ nhạy với hot-path: nên đo và xem xét lambda/handle combinator/LambdaMetafactory phù hợp, **không mặc định** proxy nhanh hoặc chậm hơn trong mọi JVM.
- Không có yêu cầu dynamic binding: lambda hoặc method reference Java thông thường thường đơn giản, rõ ý hơn.

## 10. Tính bảo mật và giới hạn module/class loader

`MethodHandleProxies` **không phải cơ chế nâng quyền**. `MethodHandle` được tạo bằng `Lookup.findStatic`, `findVirtual`, `unreflect`… đã chịu **access check ở thời điểm tạo handle**. Nếu caller có quyền tạo handle đến private method và sau đó phát wrapper ra ngoài, người nhận wrapper có thể kích hoạt method ấy qua interface: capability đã được chuyển giao.

Nên nhớ:

1. Chỉ đưa MethodHandle/adapter ra ngoài nếu consumer thực sự được phép gọi operation được bind.
2. Interface phải public và non-sealed theo điều kiện của factory; Javadoc nói factory **không thực hiện thêm access checks** cho interface ngoài những điều kiện được nêu. Không tự suy ra rằng chỉ cần wrapper là vượt được JPMS để tạo handle tới member bất kỳ.
3. Nếu interface và target sử dụng các class được nạp bởi **class loader khác nhau**, danh tính Class và descriptor có thể không tương thích dù tên kiểu giống nhau. `MethodHandle` và `MethodType` dùng đối tượng `Class` thực, không chỉ chuỗi tên.
4. Với named module, thiết kế package `exports`/`opens`, quan hệ module reads và quyền `Lookup` ở giai đoạn **tạo handle**. Không bật `--add-opens` tràn lan chỉ để né lỗi thiết kế API.
5. Nếu security manager cũ được cài đặt (ngữ cảnh Java 17), Javadoc mô tả `asInterfaceInstance` là caller-sensitive và lưu ngữ cảnh caller cho các kiểm tra security manager khi wrapper gọi target. Đây là chi tiết tương thích legacy; không dùng làm cơ chế bảo vệ chính của ứng dụng mới.

**Đặc biệt:** `wrapperInstanceTarget(wrapper)` có thể cung cấp handle có hành vi tương đương target; nếu wrapper đã là capability nhạy cảm, việc lộ interface object có thể kéo theo khả năng truy cập handle. Đừng nghĩ wrapper là sandbox chỉ vì nó có kiểu interface trừu tượng.

### 10.1. Không thể “thay target” bằng cách gán lại biến Java

Nếu code tạo:

```java
MethodHandle current = first;
MyAction action =
        MethodHandleProxies.asInterfaceInstance(
                MyAction.class, current);
current = second;
```

đây là đoạn **minh họa** với interface public `MyAction`, hai handle `first`/`second` tương thích. Gán lại biến Java `current` **không** làm object `action` tự theo `second`; factory đã nhận tham chiếu handle ở lần tạo adapter.

Nếu mục đích là **relink lời gọi động**, có thể truyền handle mang cơ chế dispatch thay đổi được, ví dụ `MutableCallSite.dynamicInvoker()`, rồi điều khiển target của call site theo memory semantics của nó. Nhưng đây là kỹ thuật **CallSite** riêng, không phải chức năng thay target của `MethodHandleProxies`; phải tuân thủ quy tắc `setTarget`/`syncAll` hoặc dùng loại CallSite phù hợp.

## 11. Performance và khả năng bảo trì

Không có hợp đồng rằng `MethodHandleProxies` luôn tạo implementation nhanh bằng lambda compiler hay có thể inline mọi trường hợp. Nó giải quyết bài toán **interop từ handle sang interface**, không phải một lời hứa về hiệu năng.

Gợi ý thực hành:

- Tạo adapter **một lần** ở bootstrap/initialization khi target ổn định; tái sử dụng interface object thay vì tạo wrapper ở mỗi request.
- Với overload, kiểm tra toàn bộ chữ ký và hành vi conversion **trước khi publish** adapter.
- Tránh bắt mọi `Throwable` trong callback rồi chuyển thành một giá trị thành công giả; log đúng nguyên nhân `UndeclaredThrowableException` khi phát sinh.
- Benchmark trên workload đại diện, có warmup bằng JMH nếu throughput/latency quan trọng. Kiểm tra cả chi phí **tạo proxy** và **invoke qua interface**, vì hai đại lượng khác nhau.
- Dùng public contract rõ ràng để người đọc code hiểu callback gọi cái gì; MethodHandle có thể được chọn động nên cần metadata/debugging phù hợp.

Nếu interface là một public stable API và target chỉ là một hàm tĩnh đơn giản, việc dùng lambda Java bình thường có thể ít phức tạp hơn. Chọn `MethodHandleProxies` khi giá trị thật sự đến từ **target handle được chọn/bổ sung khi runtime**.

## 12. Cách kiểm thử chính xác

Bộ test phù hợp cần bao gồm:

1. **Interface hợp lệ:** public, non-sealed, đúng một tên abstract method; wrapper trả đúng giá trị khi gọi.
2. **Overload cùng tên:** hai descriptor khác nhau vẫn bind cùng target, convert đúng cho từng overload.
3. **Default và Object methods:** không làm interface mất tính hợp lệ; đừng dựa vào implementation detail của object methods.
4. **Giới hạn đầu vào:** class thường, package-private interface, sealed interface, hai tên abstract khác nhau đều bị từ chối.
5. **Lỗi kiểu:** target không đúng số đối số hoặc conversion không hợp lệ -> `WrongMethodTypeException` tại factory.
6. **Wrapper metadata:** `isWrapperInstance(wrapper) == true`; `wrapperInstanceType(wrapper) == requestedType`; `wrapperInstanceTarget(wrapper)` có hành vi tương đương.
7. **Object không phải wrapper:** lambda thường -> `isWrapperInstance == false` và unwrap -> `IllegalArgumentException`.
8. **Checked exception:** interface có khai báo -> ném trực tiếp; không khai báo -> `UndeclaredThrowableException` với cause phù hợp.
9. **Null:** các tham số null ở factory -> `NullPointerException`; `isWrapperInstance(null) == false`.
10. **Bảo mật:** thử không cấp handle private cho consumer không tin cậy; module/class-loader boundaries nếu có trong môi trường triển khai.

### 12.1. Kiểm tra bằng chữ ký thay vì đoán qua tên method

Khi adapter thất bại, in:

```java
System.out.println(target.type());
```

và đối chiếu với descriptor Java sau erasure của từng method interface. Nếu arity không khớp, dùng combinator như `dropArguments` hoặc `insertArguments` chỉ khi semantics thật sự cho phép. Nếu cần đổi giá trị tham số (ví dụ parse String thành int), phải có handle/logic chuyển đổi rõ ràng; `asType` không tự parse dữ liệu ứng dụng.

### 12.2. Test output được hay không cũng không đủ

Một test duy nhất `adapter.apply(7) == "value=7"` không chứng minh hệ thống hỗ trợ đủ lỗi type, checked exception, overload và cấu hình module. Hãy viết test cho các contract đầu vào **bị từ chối**, không chỉ cho happy path.

## 13. Những nhầm lẫn hay gặp

| Nhầm lẫn | Sự thật | Cách khắc phục |
| --- | --- | --- |
| “Phải có `@FunctionalInterface` mới dùng được.” | Factory kiểm tra **một tên method abstract** và public/non-sealed; annotation không phải điều kiện. | Đọc cấu trúc interface, kể cả overload và default methods. |
| “Cứ interface có một method là hợp lệ, dù package-private.” | Interface phải **public**. | Công bố interface public khi đó là contract dự định. |
| “Sealed interface cũng được vì có một abstract method.” | Java 17 contract từ chối sealed. | Dùng implementation được permitted hoặc API khác. |
| “Overload hai descriptor tức là hai method name, phải bị từ chối.” | Cùng **một tên** được phép, nếu target adapt được cả hai. | Kiểm tra từng descriptor và semantics conversion. |
| “Một target `()String` tự phục vụ `apply(int)`.” | Factory không tự thêm đối số. | Dùng `dropArguments` hoặc chỉnh target. |
| “Wrapper gọi target bằng invokeExact.” | Hành vi như `target.invoke`, có adaptation được kiểm tra. | Hiểu `asType` và exception ở factory/invocation. |
| “Lambda thường là wrapperInstance.” | Chỉ instance từ `asInterfaceInstance` được nhận dạng. | Gọi `isWrapperInstance` trước khi unwrap. |
| “wrapperInstanceTarget luôn là cùng object `target` ban đầu.” | Chỉ bảo đảm **tương đương về hành vi**. | Không assert identity; kiểm tra contract. |
| “Checked exception luôn ném nguyên dạng.” | Nếu interface không khai báo, bị bọc `UndeclaredThrowableException`. | Thiết kế throws clause hoặc unwrap root cause. |
| “Gán lại biến `target` thì adapter cũng dùng handle mới.” | Adapter gắn với handle được truyền lúc tạo. | Tạo adapter mới hoặc dùng một handle dispatch động nếu cần. |
| “Wrapper vô hại vì nó chỉ có interface type.” | Handle có thể đã được cấp quyền private nhạy cảm. | Quản lý capability, không phát hành bừa bãi. |
| “Tạo proxy luôn nhanh hơn lambda.” | API không cam kết hiệu năng như vậy. | Benchmark, chọn mức abstraction đơn giản nhất. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `MethodHandleProxies.asInterfaceInstance(IntToText.class, target)` có thể thích nghi target `(long)String` thành `String apply(int)`?

**Đáp:** `asInterfaceInstance` kiểm tra adaptation giống `MethodHandle.asType`; `int → long` là widening primitive conversion hợp lệ, nên descriptor của method interface có thể gọi target.

**Câu 2.** Interface có `render(int)` và `render(long)` có tự động bị từ chối vì hai phương thức không?

**Đáp:** Không. Cả hai có cùng **tên `render`**; factory cho phép overload cùng tên và adapt target với từng descriptor. Một overload không tương thích vẫn có thể khiến factory ném `WrongMethodTypeException`.

**Câu 3.** Interface có `render(int)` và `format(int)` thì sao?

**Đáp:** Không hợp lệ vì có **hai tên** method trừu tượng. `asInterfaceInstance` ném `IllegalArgumentException`.

**Câu 4.** Một `public sealed interface` chỉ có một abstract method được chấp nhận không?

**Đáp:** Không trên Java 17; contract yêu cầu interface public và **not sealed**.

**Câu 5.** Tại sao một lambda Java implement cùng interface không được `wrapperInstanceTarget` chấp nhận?

**Đáp:** Nó không được tạo bằng `MethodHandleProxies.asInterfaceInstance`; `isWrapperInstance` trả false và unwrap ném `IllegalArgumentException`.

**Câu 6.** Nếu target ném `IOException` nhưng interface không khai báo `throws IOException`, caller nhìn thấy gì?

**Đáp:** Một `UndeclaredThrowableException` bọc checked `IOException`; dùng `getUndeclaredThrowable()`/`getCause()` để lấy nguyên nhân.

**Câu 7.** Nếu gán lại biến `MethodHandle target` sau khi tạo adapter, các lời gọi adapter có tự đổi implementation không?

**Đáp:** Không. Adapter sử dụng handle được truyền vào lúc tạo; muốn dispatch động phải có một handle/CallSite có semantics đổi target hoặc tạo lại adapter.

**Câu 8.** Vì sao không nên gửi wrapper được tạo từ MethodHandle private nhạy cảm cho plugin không tin cậy?

**Đáp:** Handle là một capability. Quyền truy cập đã được xác nhận khi tạo handle; wrapper chuyển lời gọi vào capability đó, không chặn lại chỉ vì phương thức có interface type public.

## 15. Tóm tắt

- **`MethodHandleProxies.asInterfaceInstance`** thích nghi một MethodHandle sang **public, non-sealed, single-method interface**.
- **Single-method** ở đây nghĩa là **một tên method trừu tượng**; overload cùng tên/bridge methods được cho phép nếu tất cả descriptor đều adapt được. Method Object và default methods không tính.
- Adaptation thực hiện theo **`asType` / `target.invoke` semantics**; sai arity/không convert được báo bằng `WrongMethodTypeException` ngay ở factory.
- **`isWrapperInstance`, `wrapperInstanceTarget`, `wrapperInstanceType`** chỉ áp dụng cho wrapper tạo bởi chính factory; target khôi phục chỉ cần **tương đương về hành vi**.
- **Checked exception không khai báo** được bọc trong `UndeclaredThrowableException`; chú ý contract callback.
- Wrapper **không phải sandbox hay bộ thay target tự động**. Bảo vệ quyền MethodHandle và chọn lambda, LambdaMetafactory, Proxy hoặc adapter class khác khi factory này không phù hợp.

### Tài liệu tham khảo chính thức (Java SE 17)

- [`MethodHandleProxies`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandleProxies.html): định nghĩa single-method interface, yêu cầu public/non-sealed, overload, conversion, wrapper metadata và checked exceptions.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact`, `asType`, kiểu và capability.
- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `Lookup.findStatic`, combinators như `dropArguments`/`insertArguments`.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn chữ ký Java/JVM.
- [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html) và [`Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): các lựa chọn động khác, với contract và giới hạn khác.
