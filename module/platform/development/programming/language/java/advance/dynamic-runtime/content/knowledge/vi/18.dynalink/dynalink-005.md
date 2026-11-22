# 18.5 GuardedInvocation: ghép handle thực thi, guard và điều kiện vô hiệu hóa

`GuardedInvocation` là một cấu trúc trung tâm của **Dynalink** (`jdk.dynalink`): nó gói một **`MethodHandle` thực thi** (invocation) cùng những điều kiện xác định **khi nào handle ấy còn phù hợp** với đối số và trạng thái runtime. Điều kiện có thể bao gồm một **guard handle trả `boolean`**, một hoặc nhiều **`SwitchPoint`** có thể bị vô hiệu hóa từ bên ngoài, và một **lớp ngoại lệ dự kiến** báo rằng linkage hiện tại không còn áp dụng được.

Nói gọn, `GuardedInvocation` diễn đạt một đề xuất:

> "Với loại đối tượng/hoàn cảnh này, hãy gọi implementation này; nếu guard không thỏa, phiên bản bị invalidated hoặc implementation ném loại exception được chỉ định, hãy chuyển sang đường fallback để tìm hoặc dùng một implementation phù hợp hơn."

Những phần cấu tạo đó được đóng gói trong **một immutable tuple** và có thể kết hợp thành **một `MethodHandle` duy nhất** bằng `compose(...)`. Khi chạy qua Dynalink thật, `GuardingDynamicLinker.getGuardedInvocation(...)` thường cung cấp tuple này cho `DynamicLinker`; một `RelinkableCallSite` sử dụng nó để xây đường gọi có fast path và đường **relink-and-invoke** khi điều kiện không còn phù hợp.

**Cần phân biệt ngay:** `GuardedInvocation` **không phải** `CallSite`, không phải riêng một lệnh `invokedynamic` và cũng không tự tìm implementation mới. Nó mô tả **một lựa chọn điều kiện**. Việc fallback chỉ trả giá trị hay có thực sự **relink** phụ thuộc vào `MethodHandle` được cung cấp làm fallback và cách `DynamicLinker`/call-site quản lý nó.

> **Môi trường:** JDK 17 trở lên, module **`jdk.dynalink`**. Các chương trình bên dưới chạy trên classpath với lệnh `javac --release 17 --add-modules jdk.dynalink` và `java --add-modules jdk.dynalink`. Cả bốn ví dụ hoàn chỉnh đã được biên dịch và chạy, stdout được đối chiếu với thực tế. Trong project có `module-info.java`, có thể dùng `requires jdk.dynalink;` trong module descriptor thay vì áp đặt cách chạy classpath của ví dụ.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

- Hiểu vai trò của `jdk.dynalink.linker.GuardedInvocation` trong **liên kết động**, đặc biệt giữa `GuardingDynamicLinker`, `DynamicLinker` và `RelinkableCallSite`.
- Đọc đúng bốn thành phần: `invocation`, `guard`, `SwitchPoint[]` và `Class<? extends Throwable> exception`.
- Nắm ý nghĩa của `getInvocation()`, `getGuard()`, `getSwitchPoints()`, `getException()` và `hasBeenInvalidated()`.
- Dùng `compose(fallback)` hoặc `compose(guardFallback, switchpointFallback, catchFallback)` với các handle có kiểu tương thích.
- Phân biệt **guard false**, **switch point invalidated** và **exception-based fallback**: chúng đều có thể chuyển nhánh nhưng không có cùng cơ chế hay trạng thái.
- Hiểu vì sao `hasBeenInvalidated()` chỉ phản ánh switch points, **không** phản ánh guard false hoặc exception đã bị bắt.
- Dùng `replaceMethods(...)`, `addSwitchPoint(...)`, `asType(...)`, `dropArguments(...)`, `filterArguments(...)` mà không đánh mất ý nghĩa các điều kiện đã gắn.
- Giải thích vì sao fast path cần điều kiện kiểm tra đúng receiver/type/state và khi nào relinking có ích.
- Tự tạo một pipeline Dynalink thật: custom `GuardingDynamicLinker` trả `GuardedInvocation` cho các kiểu receiver khác nhau, `SimpleRelinkableCallSite` chạy và relink khi guard thất bại.
- Chẩn đoán sai `MethodType`, fallback không tương thích, switchpoint đã invalidated hoặc linker không xử lý operation.

## 2. Guarded invocation nằm ở đâu trong Dynalink?

**Dynalink** là thư viện trong module JDK `jdk.dynalink`, xây cơ chế liên kết các operation như đọc property, ghi property, gọi hàm trên đối tượng có loại động. Nó có thể dùng cùng bytecode `invokedynamic` hoặc được gọi trực tiếp từ interpreter theo Java API.

Các vai trò:

| Thành phần | Là gì? | Công việc |
| --- | --- | --- |
| `CallSiteDescriptor` | Metadata của điểm gọi | Chứa `Lookup`, `Operation` và `MethodType` |
| `GuardingDynamicLinker` | Trình phân giải operation do framework/ngôn ngữ cung cấp | Xem `LinkRequest`; nếu hiểu receiver/operation thì trả `GuardedInvocation` |
| `GuardedInvocation` | Tuple điều kiện | Target implementation, guard, switch points, exception policy |
| `DynamicLinker` | Bộ điều phối linkers/fallbacks | Tìm guarded invocation phù hợp, hỗ trợ relinking |
| `RelinkableCallSite` | Call site nhận và ghép guarded invocation | Cài `MethodHandle` target với đường fallback để relink |
| `SimpleRelinkableCallSite` | Triển khai cache đơn hình (monomorphic) | Giữ một guarded invocation đang hoạt động |
| `ChainedCallSite` | Triển khai cache đa hình (polymorphic) | Giữ chuỗi guarded invocations để thử nhiều loại |
| `SwitchPoint` | Tín hiệu invalidation một chiều | Khi bị invalidate, các fast paths dựa vào nó đi sang fallback |

Luồng khái niệm:

```text
Client chạy site với receiver (A)
          |
          v
RelinkableCallSite (chưa có fast path)
          |
      relink fallback
          |
          v
DynamicLinker -> GuardingDynamicLinker
                    |
                    v
             GuardedInvocation
                invocation -> handle thực thi A
                guard      -> nhận đúng receiver A?
                switchpoints -> cấu hình còn mới?
                exception  -> lỗi dự kiến cần relink?
                    |
                    v
       Call site ghép guarded handle + fallback
                    |
                gọi fast path A

Sau đó receiver khác kiểu (B):
      guard A trả false -> fallback -> linker chọn B
                                           |
                                      GuardedInvocation B
                                           |
                                        cập nhật site
```

Một điều kiện quan trọng: `GuardingDynamicLinker.getGuardedInvocation(request, services)` **có thể trả `null`** khi linker không nhận xử lý operation/receiver. `null` ở đây không phải "một guarded invocation có invocation null": constructor `GuardedInvocation` yêu cầu invocation khác null.

### 2.1. "GuardedInvocation" không tự gắn vào JVM `invokedynamic`

Bạn hoàn toàn có thể tự tạo:

```java
GuardedInvocation gi = new GuardedInvocation(target, test);
MethodHandle composed = gi.compose(fallback);
```

Đây là **fragment**, các biến `target`/`test`/`fallback` giả định đã khởi tạo. Nó tạo một **MethodHandle composite** trong bộ nhớ, chưa phát bytecode `invokedynamic` và chưa tạo `CallSite`. Trong Dynalink, phần liên kết/relink khi guard fail được làm bởi bộ điều phối và fallback của call site.

Nếu một JVM `invokedynamic` đã bootstrap thành một `RelinkableCallSite` và framework sau đó thay target khi guard fail, đó là **relink logic Dynalink**. Không nên coi hoạt động này là JVM bắt buộc chạy lại bootstrap method để reset trạng thái linked của cùng opcode.

## 3. Bốn trường thông tin của `GuardedInvocation`

Ở mức khái niệm:

```text
GuardedInvocation
  |
  +-- invocation: MethodHandle         [bắt buộc]
  |
  +-- guard: MethodHandle              [tùy chọn, trả boolean]
  |
  +-- switchPoints: SwitchPoint[]      [tùy chọn, zero hoặc nhiều]
  |
  +-- exception: Class<? extends Throwable>
                                       [tùy chọn]
```

Các getter tương ứng:

```java
// Fragment: gi là một GuardedInvocation hợp lệ.
MethodHandle invoke = gi.getInvocation();
MethodHandle guard = gi.getGuard();             // có thể null
SwitchPoint[] switches = gi.getSwitchPoints(); // có thể null
Class<? extends Throwable> invalidating = gi.getException(); // có thể null
boolean invalidated = gi.hasBeenInvalidated();
```

Bản thân tuple được coi là **immutable**: việc thay method hoặc thêm switch point tạo ra một `GuardedInvocation` khác. Nhưng **`SwitchPoint` được tham chiếu vẫn có trạng thái mutable ngoài tuple**: ai đó có thể gọi `SwitchPoint.invalidateAll(...)` và khiến tuple cũ không còn valid.

### 3.1. Invocation: fast path thực thi

`getInvocation()` trả handle **thực sự làm công việc** khi lựa chọn hiện tại còn hợp lệ. Ví dụ:

```text
(String)String : value -> "fast:" + value
(Object)Object : obj -> ((Box)obj).name
```

MethodHandle thường là kết quả từ `MethodHandles.Lookup.findStatic`, `findVirtual`, `asType` hoặc các combinators. Nó có `MethodType` rất cụ thể: số thứ tự tham số, kiểu tham số, kiểu trả về.

**Không** giả định `gi.getInvocation().invokeExact(...)` tự thực thi guard. Nếu bạn gọi trực tiếp invocation getter, bạn đang **bỏ qua guard, switchpoint và fallback**, có thể dẫn tới cast sai hoặc hành vi không còn phù hợp. Muốn áp dụng đầy đủ điều kiện, phải dùng composite hoặc để Dynalink call site quản lý.

### 3.2. Guard: kiểm tra invocation có áp dụng với đối số hiện tại không

Guard là một `MethodHandle` trả **primitive `boolean`**. Thông thường guard nhận cùng tham số với invocation, hoặc tiền tố tham số cần thiết theo hợp đồng `MethodHandles.guardWithTest`. Ví dụ:

```text
invocation : (Object)Object
guard      : (Object)boolean
fallback   : (Object)Object

guard(receiver) == true:
    invocation(receiver)

guard(receiver) == false:
    fallback(receiver)
```

Nếu guard phân biệt class của receiver:

```java
static boolean isBox(Object receiver) {
    return receiver instanceof Box;
}
```

Đây là **fragment**, cần class `Box` định nghĩa trong mã đầy đủ. Sau khi guard pass, target có thể cast `receiver` sang `Box`. Nếu guard false, nên đi fallback để chọn target khác thay vì ép kiểu rồi ném `ClassCastException`.

**Guard không phải một `Predicate` object chung chung**: Dynalink dùng `MethodHandle` với method type tương thích, không tự lấy lambda `Predicate` để xem là guard. Guard cũng không phải boolean tính **một lần lúc link**. Nó có thể được gọi **mỗi lần thực thi path đã ghép** khi cần quyết định.

### 3.3. Switch points: trạng thái liên kết còn mới không

`SwitchPoint` là primitive trong `java.lang.invoke` để báo **một điều kiện dùng chung đã hết hiệu lực**. Ví dụ cấu hình object model thay đổi, property layout bị sửa, hoặc một tối ưu hóa cũ không còn an toàn.

- `SwitchPoint` mới có `hasBeenInvalidated() == false`.
- `SwitchPoint.invalidateAll(new SwitchPoint[]{sp})` làm nó chuyển sang **invalidated**.
- SwitchPoint **không thể revalidate**. Muốn tối ưu hóa lại, tạo switch point mới và guarded invocation mới.
- Khi một guarded invocation chứa **nhiều switch points**, **chỉ cần một** bị invalidated là `GuardedInvocation.hasBeenInvalidated()` trả `true`.
- Khi composite chứa switch point đã invalidated, nó đi **switchpoint fallback**, bỏ qua fast path được bảo vệ.
- Việc invalidate **không** tự thay target của `CallSite` hoặc tự gọi linker nếu fallback chỉ là một method bình thường; fallback mới quyết định hành vi tiếp theo.

**Đừng nhầm** việc một `SwitchPoint` có trạng thái bị vô hiệu hóa với một `guard` trả false cho một input. Guard có thể true ở lời gọi sau nếu receiver khác; switchpoint đã invalidated thì **mãi invalidated**.

### 3.4. Exception class: tín hiệu điều kiện không còn phù hợp

Tham số exception tùy chọn có type `Class<? extends Throwable>`. Khi invocation ném một exception thuộc type chỉ định, composite có thể chuyển sang **catch fallback**, và trong Dynalink fallback đó thường dẫn tới relinking.

Ví dụ chọn `ClassCastException.class` khi fast path giả định receiver có class nhất định. Đây có thể là chiến lược tối ưu khi cast failure hiếm và chi phí kiểm tra guard ở mọi lần đắt; nhưng chỉ nên làm khi ngoại lệ thực sự biểu thị **assumption mismatch**.

**Quan trọng:**

- `gi.getException()` trả class được cấu hình; **không phải** "exception cuối cùng đã xảy ra".
- `gi.hasBeenInvalidated()` **chỉ xem các switchpoints**, nên guard false hoặc exception được bắt **không làm nó chuyển thành true**.
- Một exception trigger có thể làm **đường gọi hiện tại** fallback/relink. Bản thân tuple không có bộ nhớ "đã catch một lần nên vĩnh viễn invalidated".
- Không nên khai báo `Exception.class`/`Throwable.class` bừa bãi: điều đó có thể nuốt lỗi lập trình/ứng dụng và gây vòng relink vô tận.
- Đừng coi mọi `ClassCastException` là dấu hiệu an toàn để relink: có thể exception đến từ bug nội bộ của implementation chứ không phải receiver type assumption.

## 4. Constructors và getter quan trọng

Các constructor trong Java 17 API:

| Cách tạo | Ý nghĩa |
| --- | --- |
| `new GuardedInvocation(invocation)` | Invocation vô điều kiện: không guard/switch/exception |
| `new GuardedInvocation(invocation, guard)` | Guard-based validity |
| `new GuardedInvocation(invocation, switchPoint)` | Validity phụ thuộc một switch point |
| `new GuardedInvocation(invocation, guard, switchPoint)` | Cần guard và switch point |
| `new GuardedInvocation(invocation, guard, switchPoint, exception)` | Thêm exception-based fallback |
| `new GuardedInvocation(invocation, guard, switchPoints, exception)` | Nhiều switch points và exception policy |

`invocation` không được null. `guard` có thể null, `switchPoint` có thể null, tập `switchPoints` có thể null; exception class cũng có thể null. Guard cần method type tương thích theo quy tắc `MethodHandles.guardWithTest`, đặc biệt kiểu trả về là `boolean`.

Getter cung cấp các phần tử để trình phân giải/call-site có thể kiểm tra, điều chỉnh hoặc ghép chúng:

```java
// Fragment: không có nội dung API nào tự gọi target trong các getter.
gi.getInvocation();
gi.getGuard();
gi.getSwitchPoints();
gi.getException();
gi.hasBeenInvalidated();
```

Nhìn `getGuard()==null` không tự suy luận code xấu: một invocation **unconditional** có thể hoàn toàn hợp lệ khi target luôn xử lý được mọi receiver theo descriptor. Nhưng với một linker chỉ áp dụng cho `Box`, trả một unconditional target **ép kiểu sang Box** cho site nhận `Object` sẽ rất nguy hiểm khi receiver mới đổi sang `String`.

## 5. Ghép điều kiện bằng `compose`

API trọng tâm:

```java
MethodHandle complete = gi.compose(fallback);
```

Đây là fragment. `fallback` là `MethodHandle` chịu trách nhiệm nhận đúng các đối số và có kiểu trả về phù hợp với `invocation`. Cách gọi này dùng **một fallback chung** cho ba tình huống: guard false, switchpoint invalidated, hoặc exception loại được cấu hình.

Nếu cần biết chính xác nguyên nhân, sử dụng overload:

```java
MethodHandle complete = gi.compose(
        guardFallback,
        switchpointFallback,
        catchFallback);
```

**Thứ tự argument quan trọng**: `guardFallback` đầu tiên, `switchpointFallback` thứ hai, `catchFallback` thứ ba. Trong ví dụ 2, ba handle trả các tiền tố `guard:`, `switch:` và `catch:` khác nhau để kiểm chứng.

### 5.1. Dòng điều khiển của composite

```text
     invoked composite MethodHandle
                 |
                 v
        SwitchPoint còn valid?
           |               |
          no              yes
           |               |
           v               v
  switchpointFallback   guard tồn tại?
                           |
                   +-------+-------+
                   |               |
                 false            true/none
                   |               |
                   v               v
             guardFallback     invocation
                                   |
                        exception được cấu hình?
                                   |
                          +--------+--------+
                          |                 |
                   loại khớp           bình thường
                          |                 |
                          v                 v
                     catchFallback       kết quả
```

Sơ đồ mô tả logic thông thường của composite. Implementation có thể áp dụng cấu trúc `MethodHandles.guardWithTest`, `SwitchPoint.guardWithTest` và `catchException`; các chi tiết tối ưu hóa JVM không phải API public.

Nếu switch point invalidated, composite có thể đi thẳng switchpoint fallback trước khi test guard; điều này được xác minh bằng ví dụ 2 khi input `"skip-X"` trước invalidation chọn `guard:`, còn sau invalidation chọn `switch:`.

### 5.2. `compose(fallback)` không nhất thiết relink

Nếu `fallback(String)` chỉ trả `"fallback:"+s`, composite đơn giản gọi nó khi guard false. Nó **không** hỏi lại `GuardingDynamicLinker` để chọn invocation mới.

Trong pipeline Dynalink, fallback thường là **relink-and-invoke handle** do `DynamicLinker` cung cấp. Vì vậy khi guard fail, Dynalink có thể:

1. Xem request và receiver hiện tại.
2. Nhờ các `GuardingDynamicLinker` tạo `GuardedInvocation` khác.
3. Gọi `RelinkableCallSite.relink(...)`/`resetAndRelink(...)` để cập nhật fast path.
4. Thực thi operation trên receiver vừa gây guard miss.

Cùng một `compose` nhưng fallback khác nhau sẽ cho hành vi khác nhau. Bản thân `GuardedInvocation` không quản lý cache monomorphic/polymorphic.

### 5.3. Bảng điều kiện và hành động

| Trạng thái | Composite với một fallback | Composite với ba fallback | `hasBeenInvalidated()` |
| --- | --- | --- | --- |
| Guard pass, switchpoints hợp lệ, invocation không ném exception trigger | Gọi invocation | Gọi invocation | `false` nếu chưa có switchpoint invalidated |
| Guard false | Gọi fallback | Gọi guardFallback | Không thay đổi vì guard false |
| Bất kỳ switchpoint bị invalidate | Gọi fallback | Gọi switchpointFallback | `true` |
| Invocation ném exception type được cấu hình | Gọi fallback | Gọi catchFallback | Không thay đổi *vì exception*; vẫn tùy switchpoints |
| Invocation ném exception không khớp policy | Exception đi ra caller | Exception đi ra caller | Không tự thay đổi |

Trong mã thực tế, fallback có thể tiếp tục ném exception; guard cũng có thể có side effects hoặc lỗi. Không dùng bảng này như lời hứa rằng mọi code path đều luôn trả giá trị.

## 6. Ví dụ 1 — Guard pass/fail và invocation vô điều kiện

Tạo **`GuardComposeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.linker.GuardedInvocation;

public final class GuardComposeDemo {
    static String fast(String value) {
        return "fast:" + value;
    }

    static boolean accepts(String value) {
        return value.startsWith("ok");
    }

    static String fallback(String value) {
        return "fallback:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle target = lookup.findStatic(GuardComposeDemo.class, "fast", type);
        MethodHandle guard = lookup.findStatic(GuardComposeDemo.class, "accepts",
                type.changeReturnType(boolean.class));
        MethodHandle otherwise = lookup.findStatic(GuardComposeDemo.class, "fallback", type);

        GuardedInvocation guarded = new GuardedInvocation(target, guard);
        MethodHandle composite = guarded.compose(otherwise);
        System.out.println("invocation type: " + guarded.getInvocation().type());
        System.out.println("guard type: " + guarded.getGuard().type());
        System.out.println("exception absent: " + (guarded.getException() == null));
        System.out.println("initially invalidated: " + guarded.hasBeenInvalidated());
        System.out.println("composite type: " + composite.type());
        System.out.println("accept: " + (String) composite.invokeExact("ok-A"));
        System.out.println("reject: " + (String) composite.invokeExact("no-B"));

        GuardedInvocation unconditional = new GuardedInvocation(target);
        MethodHandle plain = unconditional.compose(otherwise);
        System.out.println("no guard: " + (unconditional.getGuard() == null));
        System.out.println("unconditional: " + (String) plain.invokeExact("no-C"));
    }
}
```

Chạy:

```bash
javac --release 17 --add-modules jdk.dynalink GuardComposeDemo.java
java --add-modules jdk.dynalink GuardComposeDemo
```

**Stdout đã kiểm chứng:**

```text
invocation type: (String)String
guard type: (String)boolean
exception absent: true
initially invalidated: false
composite type: (String)String
accept: fast:ok-A
reject: fallback:no-B
no guard: true
unconditional: fast:no-C
```

Giải thích:

1. `fast` có type `(String)String`; `accepts` có type `(String)boolean`. Số/kiểu tham số tương ứng và guard trả boolean.
2. `guarded.compose(otherwise)` tạo composite `(String)String`. Với `"ok-A"` guard true, trả `fast:ok-A`.
3. Với `"no-B"` guard false, gọi handle fallback `otherwise` để trả `fallback:no-B`.
4. `getException()==null` vì không cấu hình exception policy; `hasBeenInvalidated()==false` vì không có switchpoint invalidated (thậm chí không có switchpoint).
5. `new GuardedInvocation(target)` tạo invocation vô điều kiện, nên input `"no-C"` vẫn gọi fast target. Từ `no guard: true` không được suy ra target này đúng cho mọi input **trong mọi ứng dụng**; ở ví dụ, `fast` chỉ ghép chuỗi nên không có cast assumption.

### 6.1. Liên hệ trực tiếp với `MethodHandles.guardWithTest`

Một guarded invocation chỉ có invocation+guard về bản chất giống ghép:

```java
// Fragment: target, test, fallback có MethodType tương thích.
MethodHandle composite =
        MethodHandles.guardWithTest(test, target, fallback);
```

`GuardedInvocation` thêm metadata switchpoints/exception và các phương pháp biến đổi chung cho cả target/guard. Dùng wrapper làm cho các dynamic linkers có thể trao đổi một đề xuất linkage hoàn chỉnh thay vì tự định dạng ba/bốn handles độc lập.

## 7. Ví dụ 2 — Guard fallback, switchpoint fallback và catch fallback

Đây là điểm dễ nhầm nhất: **ba loại điều kiện không đồng nghĩa**. Ví dụ sử dụng method thực thi ném `IllegalArgumentException` với input `"boom"`, guard từ chối prefix `"skip"` và một `SwitchPoint` có thể vô hiệu hóa từ bên ngoài.

Tạo **`InvalidateComposeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import jdk.dynalink.linker.GuardedInvocation;

public final class InvalidateComposeDemo {
    static String execute(String value) {
        if (value.equals("boom")) throw new IllegalArgumentException("outdated");
        return "invoke:" + value;
    }

    static boolean guard(String value) {
        return !value.startsWith("skip");
    }

    static String onGuard(String value) {
        return "guard:" + value;
    }

    static String onSwitch(String value) {
        return "switch:" + value;
    }

    static String onCatch(String value) {
        return "catch:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle invocation = lookup.findStatic(
                InvalidateComposeDemo.class, "execute", signature);
        MethodHandle check = lookup.findStatic(
                InvalidateComposeDemo.class, "guard", signature.changeReturnType(boolean.class));
        MethodHandle guardFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onGuard", signature);
        MethodHandle switchFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onSwitch", signature);
        MethodHandle catchFallback = lookup.findStatic(
                InvalidateComposeDemo.class, "onCatch", signature);
        SwitchPoint switchPoint = new SwitchPoint();

        GuardedInvocation guarded = new GuardedInvocation(
                invocation, check, switchPoint, IllegalArgumentException.class);
        MethodHandle composite = guarded.compose(
                guardFallback, switchFallback, catchFallback);
        System.out.println("normal: " + (String) composite.invokeExact("ok"));
        System.out.println("guard false: " + (String) composite.invokeExact("skip-X"));
        System.out.println("expected exception: " + (String) composite.invokeExact("boom"));
        System.out.println("invalid after exception: " + guarded.hasBeenInvalidated());
        System.out.println("exception policy: " + guarded.getException().getSimpleName());

        SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
        System.out.println("invalid after switch: " + guarded.hasBeenInvalidated());
        System.out.println("switched: " + (String) composite.invokeExact("ok"));
        System.out.println("switch before guard: " + (String) composite.invokeExact("skip-X"));
    }
}
```

Lệnh:

```bash
javac --release 17 --add-modules jdk.dynalink InvalidateComposeDemo.java
java --add-modules jdk.dynalink InvalidateComposeDemo
```

**Stdout chính xác:**

```text
normal: invoke:ok
guard false: guard:skip-X
expected exception: catch:boom
invalid after exception: false
exception policy: IllegalArgumentException
invalid after switch: true
switched: switch:ok
switch before guard: switch:skip-X
```

### 7.1. Phân tích ba đường fallback

- **Normal:** `execute("ok")` trả `invoke:ok`.
- **Guard false:** `guard("skip-X")` trả false, nên đi `onGuard`; execution target không cần được gọi.
- **Exception:** `execute("boom")` ném `IllegalArgumentException`; composite bắt **đúng loại được cấu hình** và gọi `onCatch`. Exception thực tế không được truyền làm tham số đầu cho `onCatch` trong ví dụ này; fallback nhận cùng đối số `String` của site.
- **Status:** Sau exception, `guarded.hasBeenInvalidated()` vẫn false. Đây là điểm phân biệt exception-triggered fallback với switchpoint state.
- **External invalidation:** `SwitchPoint.invalidateAll(...)` chuyển switch point sang invalidated; `hasBeenInvalidated()` từ đó trả true.
- **Ưu tiên switchpoint:** Các lời gọi `"ok"` và `"skip-X"` đều chọn `onSwitch` sau invalidation vì wrapper không còn cho chạy guard/fast path.

### 7.2. Có thực sự "vô hiệu hóa" guard vĩnh viễn sau exception không?

Không phải với một `GuardedInvocation` được compose thủ công vào handle tĩnh như demo. Exception policy tạo **catch fallback khi exception khớp**; nó không tự gọi `SwitchPoint.invalidateAll(...)` hoặc ghi cờ invalidated vĩnh viễn trong tuple. Vì vậy nếu không invalidate switchpoint, một lời gọi mới với `"ok"` vẫn có thể chạy `execute("ok")`, và một lời gọi mới với `"boom"` lại ném exception rồi được catch.

Khi fallback là **relink-and-invoke** của Dynalink, một expected exception có thể dẫn tới một quá trình liên kết lại và thay/cập nhật target của call site. Đó là **hành vi của fallback và call site**, không phải trường trạng thái mặc định của tuple.

### 7.3. Nhiều `SwitchPoint`

Có thể tạo constructor nhận mảng:

```java
// Fragment: invocation, guard là các MethodHandle có type tương thích.
GuardedInvocation gi = new GuardedInvocation(
        invocation, guard,
        new SwitchPoint[]{schemaSwitch, configSwitch},
        ClassCastException.class);
```

Một trong hai switchpoints invalidated sẽ khiến `gi.hasBeenInvalidated()` true. Điều kiện này tương đương ý tưởng "fast path chỉ valid khi **cả schema và cấu hình** vẫn valid". Không cần tự kiểm tra thủ công cả hai tại mỗi lần gọi nếu chúng được ghép vào composite.

## 8. Immutable tuple và các phép biến đổi `GuardedInvocation`

Một `GuardedInvocation` không có `setInvocation(...)` để sửa trực tiếp tuple. Thay vào đó, Java 17 API cung cấp:

| Method | Kết quả / mục đích |
| --- | --- |
| `replaceMethods(newInvocation, newGuard)` | Tạo tuple mới với invocation/guard mới; bảo toàn switchpoint(s) và exception policy |
| `addSwitchPoint(sp)` | Tạo tuple mới bổ sung switchpoint (nếu `sp==null` thường trả tuple hiện tại) |
| `asType(MethodType)` | Adapt invocation và guard (nếu có) về chữ ký phù hợp; guard vẫn trả boolean |
| `asType(LinkerServices, MethodType)` | Dùng conversion rules của linker services |
| `asTypeSafeReturn(LinkerServices, MethodType)` | Dùng conversion không làm mất precision/magnitude cho return type |
| `asType(CallSiteDescriptor)` | Adapt theo method type trong descriptor |
| `dropArguments(pos, types...)` | Thêm đối số không dùng vào invocation và guard phù hợp |
| `filterArguments(pos, filters...)` | Áp dụng filters tương ứng cho invocation và guard |

**Cảnh báo:** "Bảo toàn switchpoint" không có nghĩa sao chép ra một `SwitchPoint` mới chưa invalidated. Nếu hai tuples tham chiếu cùng switchpoint, việc invalidate switchpoint đó có thể ảnh hưởng cả hai. Ngược lại, `addSwitchPoint(extra)` không tự thêm extra vào tuple gốc.

### 8.1. `asType` có hai method type cần quan sát

Một GuardedInvocation có:

```text
invocation type: (String)String
guard type:      (String)boolean
```

Sau `gi.asType(MethodType.methodType(Object.class, String.class))`:

```text
invocation type: (String)Object
guard type:      (String)boolean
```

Return type của guard vẫn **boolean**; không biến guard thành `(String)Object` chỉ vì invocation trả `Object`. Nếu guard chỉ kiểm tra một tiền tố của danh sách tham số, adapter cần giữ tương thích với cơ chế guard-composition. Với `LinkerServices`, khả năng chuyển đổi còn phụ thuộc conversion rules mà linker đã đăng ký, không phải Java cast tùy ý.

### 8.2. `dropArguments` không xóa thông tin ngữ cảnh đã có

`dropArguments(0, int.class)` trên một tuple `(String)String` biến invocation thành `(int,String)String`. Tham số `int` đầu tiên được chấp nhận nhưng **bỏ qua**. Guard tương ứng cũng cần nhận đối số ở vị trí hợp lệ để composite có thể hoạt động.

Đừng nhầm `dropArguments` của method-handle combiner với `MethodType.dropParameterTypes` (xóa tham số khỏi type) hoặc `insertArguments` (gắn giá trị cố định, làm giảm số tham số). Dùng khi call site cung cấp thêm một context argument mà implementation nhanh hiện tại không cần.

### 8.3. `filterArguments` tác động đến guard và invocation

Nếu bạn trim input `" ok-B "` trước khi vào target, guard cũng nên nhìn cùng giá trị `"ok-B"`. `GuardedInvocation.filterArguments(0, trimHandle)` thực hiện điều đó cho invocation và guard ở vị trí tương ứng, tránh bug guard kiểm tra chuỗi chưa normalize nhưng target nhận chuỗi đã normalize.

Tất nhiên filter phải có chữ ký đúng; một filter kiểu sai có thể khiến adapter creation thất bại. Hành vi chi tiết nếu guard có ít tham số hơn invocation được mô tả trong Javadoc API.

## 9. Ví dụ 3 — `replaceMethods`, `addSwitchPoint`, `filterArguments`, `dropArguments` và `asType`

Tạo **`GuardTransformDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import jdk.dynalink.linker.GuardedInvocation;

public final class GuardTransformDemo {
    static String first(String s) {
        return "v1:" + s;
    }

    static String second(String s) {
        return "v2:" + s;
    }

    static boolean guard(String s) {
        return s.startsWith("ok");
    }

    static String fallback(String s) {
        return "fallback:" + s;
    }

    static String normalize(String s) {
        return s.trim();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle first = lookup.findStatic(GuardTransformDemo.class, "first", signature);
        MethodHandle second = lookup.findStatic(GuardTransformDemo.class, "second", signature);
        MethodHandle guard = lookup.findStatic(GuardTransformDemo.class, "guard",
                signature.changeReturnType(boolean.class));
        MethodHandle fallback = lookup.findStatic(GuardTransformDemo.class, "fallback", signature);
        MethodHandle filter = lookup.findStatic(GuardTransformDemo.class, "normalize", signature);
        SwitchPoint initialSwitch = new SwitchPoint();
        SwitchPoint extraSwitch = new SwitchPoint();
        GuardedInvocation original = new GuardedInvocation(first, guard, initialSwitch);
        GuardedInvocation changed = original.replaceMethods(second, guard);
        GuardedInvocation expanded = changed.addSwitchPoint(extraSwitch);
        System.out.println("same descriptor: "
                + original.getInvocation().type().equals(changed.getInvocation().type()));
        System.out.println("original target: "
                + (String) original.compose(fallback).invokeExact("ok-A"));
        System.out.println("changed target: "
                + (String) changed.compose(fallback).invokeExact("ok-A"));
        System.out.println("expanded switchpoints: " + expanded.getSwitchPoints().length);

        GuardedInvocation trimmed = expanded.filterArguments(0, filter);
        System.out.println("filter target: "
                + (String) trimmed.compose(fallback).invokeExact(" ok-B "));
        GuardedInvocation withContext = original.dropArguments(0, int.class);
        MethodHandle fallbackWithContext = MethodHandles.dropArguments(
                fallback, 0, int.class);
        System.out.println("dropped type: " + withContext.getInvocation().type());
        System.out.println("ignored context: " + (String) withContext.compose(
                fallbackWithContext).invokeExact(3, "ok-C"));
        MethodType widened = MethodType.methodType(Object.class, String.class);
        GuardedInvocation adapted = original.asType(widened);
        System.out.println("adapted type: " + adapted.getInvocation().type());
        System.out.println("adapted result: " + (Object) adapted.compose(
                fallback.asType(widened)).invokeExact("ok-D"));

        SwitchPoint.invalidateAll(new SwitchPoint[]{extraSwitch});
        System.out.println("original invalid: " + original.hasBeenInvalidated());
        System.out.println("expanded invalid: " + expanded.hasBeenInvalidated());
        System.out.println("expanded fallback: "
                + (String) expanded.compose(fallback).invokeExact("ok-E"));
        System.out.println("original still executes: "
                + (String) original.compose(fallback).invokeExact("ok-E"));
    }
}
```

Chạy:

```bash
javac --release 17 --add-modules jdk.dynalink GuardTransformDemo.java
java --add-modules jdk.dynalink GuardTransformDemo
```

**Stdout đã kiểm chứng:**

```text
same descriptor: true
original target: v1:ok-A
changed target: v2:ok-A
expanded switchpoints: 2
filter target: v2:ok-B
dropped type: (int,String)String
ignored context: v1:ok-C
adapted type: (String)Object
adapted result: v1:ok-D
original invalid: false
expanded invalid: true
expanded fallback: fallback:ok-E
original still executes: v1:ok-E
```

Giải thích:

1. `replaceMethods(second, guard)` tạo tuple `changed`; tuple `original` vẫn chứa `first`.
2. `addSwitchPoint(extraSwitch)` tạo `expanded`, với **hai** switchpoints. Việc invalidate `extraSwitch` chỉ ảnh hưởng những tuples chứa thêm switchpoint ấy; `original` và `changed` không tự nhận thêm extra.
3. `filterArguments(0, normalize)` trim input trên cả guard và invocation. Do đó `" ok-B "` thành `"ok-B"` để guard pass, output từ `second` là `v2:ok-B`.
4. `dropArguments(0, int.class)` thêm ignored context vào invocation/guard. Fallback `(String)String` cũng phải được adapt thành `(int,String)String`; không tự động bỏ đối số dư.
5. `asType((String)Object)` thay đổi kiểu trả về invocation; guard vẫn trả boolean. Fallback được adapt tương ứng trước khi compose.
6. Sau `invalidateAll(extraSwitch)`, `expanded.hasBeenInvalidated()` true và đi fallback. `original` vẫn hợp lệ vì chỉ có `initialSwitch` chưa invalidated.
7. Các output cho thấy **immutable tuple không đồng nghĩa có "deep copy" mọi shared mutable state**: switchpoints đã gắn có thể được invalidated chung từ bên ngoài.

## 10. Dynalink thật: `GuardingDynamicLinker` tạo GuardedInvocation cho receiver động

Ba ví dụ trước chủ động `new GuardedInvocation(...)` và `compose(...)`. Để thấy cách nó hoạt động trong **Dynalink**, thử một operation `GET PROPERTY "label"` trên hai loại receiver `Box` và `String`.

Trong pipeline mẫu:

- `CallSiteDescriptor` lưu `Lookup`, operation và signature `(Object)Object`.
- `DynamicLinkerFactory` được cấu hình một **prioritized custom linker**.
- `SimpleRelinkableCallSite` giữ một fast path, phù hợp mô hình **monomorphic cache**.
- Khi nhận `Box` đầu tiên, linker trả invocation `boxValue` + guard `isBox`.
- Khi nhận `String`, guard `isBox` thất bại; Dynalink dùng fallback để gọi lại custom linker, lấy invocation `stringValue` + guard `isString` và cập nhật site.
- Khi quay lại `Box`, `SimpleRelinkableCallSite` đã thay fast path gần nhất, nên phải relink tiếp.

Điều này minh họa rằng **guard là một điều kiện liên kết**, còn fallback của Dynalink là **đường làm mới linkage trong runtime**, không phải một string-formatted fallback thông thường.

### 10.1. Ví dụ 4 — Custom linker, guard miss và monomorphic relink

Tạo **`DynalinkPipelineDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public final class DynalinkPipelineDemo {
    static final class Box {
        final String name;
        Box(String name) { this.name = name; }
    }

    static Object boxValue(Object object) {
        return "box:" + ((Box) object).name;
    }

    static boolean isBox(Object object) {
        return object instanceof Box;
    }

    static Object stringValue(Object object) {
        return "text:" + object;
    }

    static boolean isString(Object object) {
        return object instanceof String;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(Object.class, Object.class);
        MethodType guardType = type.changeReturnType(boolean.class);
        MethodHandle boxHandle = lookup.findStatic(
                DynalinkPipelineDemo.class, "boxValue", type);
        MethodHandle boxGuard = lookup.findStatic(
                DynalinkPipelineDemo.class, "isBox", guardType);
        MethodHandle stringHandle = lookup.findStatic(
                DynalinkPipelineDemo.class, "stringValue", type);
        MethodHandle stringGuard = lookup.findStatic(
                DynalinkPipelineDemo.class, "isString", guardType);

        int[] linkRequests = {0};
        GuardingDynamicLinker custom = (request, services) -> {
            Object receiver = request.getReceiver();
            if (receiver instanceof Box) {
                linkRequests[0]++;
                return new GuardedInvocation(boxHandle, boxGuard);
            }
            if (receiver instanceof String) {
                linkRequests[0]++;
                return new GuardedInvocation(stringHandle, stringGuard);
            }
            return null;
        };

        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinkers(custom);
        DynamicLinker linker = factory.createLinker();
        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                lookup, StandardOperation.GET.withNamespace(
                        StandardNamespace.PROPERTY).named("label"), type);
        SimpleRelinkableCallSite site =
                linker.link(new SimpleRelinkableCallSite(descriptor));
        MethodHandle invoke = site.dynamicInvoker();
        System.out.println("site type: " + site.type());
        System.out.println("first box: "
                + (Object) invoke.invokeExact((Object) new Box("A")));
        System.out.println("links after box: " + linkRequests[0]);
        System.out.println("second box: "
                + (Object) invoke.invokeExact((Object) new Box("B")));
        System.out.println("links after same type: " + linkRequests[0]);
        System.out.println("first string: "
                + (Object) invoke.invokeExact((Object) "Hello"));
        System.out.println("links after string: " + linkRequests[0]);
        System.out.println("second string: "
                + (Object) invoke.invokeExact((Object) "World"));
        System.out.println("links after same string type: " + linkRequests[0]);
        System.out.println("back to box: "
                + (Object) invoke.invokeExact((Object) new Box("C")));
        System.out.println("links after switch back: " + linkRequests[0]);
    }
}
```

Chạy:

```bash
javac --release 17 --add-modules jdk.dynalink DynalinkPipelineDemo.java
java --add-modules jdk.dynalink DynalinkPipelineDemo
```

**Stdout đã kiểm chứng:**

```text
site type: (Object)Object
first box: box:A
links after box: 1
second box: box:B
links after same type: 1
first string: text:Hello
links after string: 2
second string: text:World
links after same string type: 2
back to box: box:C
links after switch back: 3
```

### 10.2. Vì sao lần thứ hai cùng type không relink?

Lời gọi `Box("B")` đi vào fast path đang có:

```text
guard isBox("Box B") -> true
    |
    v
boxValue(...) -> "box:B"
```

Không cần hỏi lại custom linker, do đó count vẫn bằng 1. Khi có `"Hello"`, guard `isBox` trả false nên fallback của `SimpleRelinkableCallSite`/`DynamicLinker` chọn `String` strategy, count thành 2. Khi nhận `Box("C")`, monomorphic cache đang giữ String path nên guard fail và count thành 3.

Các lần chạy count này là **số lần custom linker đưa ra GuardedInvocation** trong demo một-thread, không phải số lần JVM bootstrap method chạy. Chương trình tạo `SimpleRelinkableCallSite` trực tiếp trong Java source, **không tự phát opcode `invokedynamic`**.

### 10.3. Một giới hạn có chủ ý của custom linker

Custom linker trong demo chỉ được thử trên **một** descriptor dành cho `GET PROPERTY "label"`. Nó chọn target dựa vào **receiver type** và không kiểm tra `request.getCallSiteDescriptor().getOperation()`. Trong sản phẩm thật, một `GuardingDynamicLinker` thường phải xác nhận operation/name/namespace trước khi nhận xử lý. Nếu không, linker có thể vô tình áp dụng logic lấy property `label` cho một operation khác như `CALL` hoặc `SET`.

Nếu nhận receiver ngoài `Box`/`String`, custom linker trả null để các linker khác trong factory thử xử lý. Dynalink có `BeansLinker` fallback tiêu chuẩn; một operation hoàn toàn không được linker nào xử lý có thể đưa đến `NoSuchDynamicMethodException`. Đừng thay `return null` bằng một tuple giả có invocation null.

### 10.4. `SimpleRelinkableCallSite` và `ChainedCallSite`

- `SimpleRelinkableCallSite` lưu một guarded invocation vào target tại một thời điểm, thuận tiện khi receiver thường cùng một loại. Khi chuyển `Box → String → Box`, sẽ thay fast path nhiều lần.
- `ChainedCallSite` có thể giữ **một chuỗi** invocations đã liên kết, thường hỗ trợ polymorphic inline cache. Việc receiver đổi giữa một số kiểu quen thuộc có thể đi qua nhiều guards trong chain thay vì chạy lại linker mọi lần.
- Cả hai là **implementation của `RelinkableCallSite`**. Lựa chọn ảnh hưởng caching/hiệu năng, nhưng `GuardedInvocation` vẫn là đơn vị hợp đồng nhận từ `GuardingDynamicLinker`.
- Khi có SwitchPoint invalidated, một cache có thể loại bỏ/không dùng guarded invocation cũ và gọi linker để tạo tuple mới.

Không khẳng định mỗi `ChainedCallSite` luôn cache vô hạn: chain có giới hạn và chính sách relink/reset của implementation.

## 11. Kiểu của `MethodHandle` là hợp đồng bắt buộc

Bảng signature thường gặp:

| Vai trò | Ví dụ MethodType |
| --- | --- |
| Dynamic call site | `(Object)Object` |
| Target cho receiver `Box` | `(Object)Object` |
| Guard `isBox` | `(Object)boolean` |
| Relink fallback | `(Object)Object` |
| Call site nhận thêm context | `(int,Object)Object` |
| Guard nếu chỉ kiểm tra receiver đầu | Có thể là prefix phù hợp, vẫn phải tuân thủ guardWithTest/adaptation |

Nếu target thực tế có type `(Box)String` nhưng call site nhận `(Object)Object`, có thể adapt bằng `MethodHandle.asType` hoặc `LinkerServices.asType`. Tuy nhiên cast `Object→Box` có thể thất bại; guard phải giữ đúng điều kiện và type thích hợp. Dynalink `LinkerServices` cung cấp cơ chế chuyển kiểu chuyên dụng cho ngôn ngữ runtime, không phải mọi conversion đều là cast JVM thông thường.

### 11.1. Đọc chữ ký trước khi compose

Trước khi debug logic, in:

```java
// Fragment: target, guard và fallback đã tồn tại.
System.out.println(target.type());
System.out.println(guard.type());
System.out.println(fallback.type());
```

Với `invokeExact`, **kiểu static tại call site của Java** (bao gồm kiểu trả về theo cast) cũng phải phù hợp. `WrongMethodTypeException` có thể xuất hiện nếu gọi handle với signature sai; `IllegalArgumentException` có thể xuất hiện khi cố ghép các handles không tương thích. Đừng coi mọi lỗi này là "guard false" hoặc "relink request".

### 11.2. Guard cần kiểm tra đủ giả định, không quá rộng

Nếu invocation cast receiver sang `ArrayList`, guard chỉ test `receiver instanceof List` là **quá rộng** vì có những `List` khác không phải `ArrayList`. Hậu quả: guard pass nhưng target ném `ClassCastException`. Có thể dùng check `receiver instanceof ArrayList` hoặc thiết kế invocation nhận `List` nếu thực sự hỗ trợ mọi subtype phù hợp.

Ngược lại, guard `receiver.getClass() == ExactClass.class` đôi lúc quá chặt nếu logic cũng xử lý an toàn subclasses. Lựa chọn guard gắn với **assumption thật** của target, không chỉ tối ưu microbenchmark.

### 11.3. Guard nên ít side effect

Guard được chạy trong hot path; side effects (đếm global, I/O, mutation) có thể làm hành vi thay đổi khó đoán, đặc biệt khi compiler/JVM tối ưu hóa MethodHandles hoặc các threads đồng thời truy cập. Nên giữ guard nhanh, thuần và dựa trên trạng thái có memory visibility chính xác.

Nếu cache dựa trên **schema/layout/config** thay đổi bất đồng bộ, SwitchPoint thường là tín hiệu phù hợp hơn việc guard tự làm I/O hoặc đọc cấu hình phức tạp mỗi lần.

## 12. Sơ đồ chiến lược invalidation/relink

Giả sử runtime có một "schema version" ảnh hưởng cách đọc property. Khi thay schema, invocation cũ không còn đúng.

```text
Version 1:
   GuardedInvocation v1
       invocation: readPropertyV1
       guard:      receiver instanceof Record
       switch:     schemaV1Switch

   call site -> composed v1 -> readPropertyV1

Schema updated:
   SwitchPoint.invalidateAll([schemaV1Switch])

Next call:
   composed v1 -> switchpointFallback -> DynamicLinker
                                           |
                                      create v2 handles
                                           |
                                      new SwitchPoint v2
                                           |
                                      GuardedInvocation v2
                                           |
                                      call site relink
                                           |
                                      readPropertyV2
```

**Lưu ý:** `SwitchPoint.invalidateAll(...)` **không tự tạo v2**. Đây là trách nhiệm của **fallback + linker**. Nếu code dùng `compose(plainFallback)` và `plainFallback` chỉ trả giá trị mặc định, mọi lần sau invalidation sẽ tiếp tục trả giá trị đó; không có magic re-link.

### 12.1. Invalidate nhiều điểm cùng một sự kiện

Nếu nhiều guarded invocations dựa vào một schema, có thể chia sẻ cùng `SwitchPoint`. Khi schema đổi, invalidating một object đó làm tất cả handles có liên quan đi fallback. Đây là công cụ invalidation hiệu quả nhưng cần quản lý lifetime/ownership:

- Đừng chia sẻ SwitchPoint giữa các giả định độc lập nếu một thay đổi không cần hủy tất cả cache.
- Một switchpoint đã invalidated không thể tái sử dụng cho phiên bản mới; tạo mới.
- Nếu có nhiều thread cập nhật schema và gọi site, cần công bố state/cache nhất quán theo Java Memory Model, không coi invalidate như transaction toàn cục.
- Một invocation có thể đang chạy trên target cũ vào thời điểm invalidate; việc invalidation không bắt buộc hủy đoạn code đang thực thi.

### 12.2. Exception-based relink chỉ nên dành cho lỗi dự kiến

Ví dụ khi nhiều receiver khác nhau làm cast assumptions thỉnh thoảng sai, linker có thể chọn `ClassCastException.class` làm invalidating exception. Tuy nhiên:

- Thứ nhất, exception path thường đắt nếu lỗi xảy ra liên tục; guard rõ ràng có thể tốt hơn.
- Thứ hai, exception cần đúng ý nghĩa: một NPE không mong muốn hoặc bug của target không nên biến thành thử relink vô hạn.
- Thứ ba, `hasBeenInvalidated()` không kiểm tra event exception trước đó; nếu muốn tracking, đặt metrics trong fallback/linker.
- Thứ tư, một exception có thể bị bắt trong target trước khi thoát ra nên catch fallback **không nhìn thấy** nó; chỉ exception thoát qua composite và khớp type mới kích hoạt nhánh này.

## 13. Lỗi và chống ví dụ thường gặp

| Hiện tượng | Vì sao xảy ra | Hướng xử lý |
| --- | --- | --- |
| `ClassNotFoundException` hoặc "package jdk.dynalink not visible" | Module `jdk.dynalink` không được resolve/require | Thêm `--add-modules jdk.dynalink` ở classpath ví dụ hoặc `requires jdk.dynalink;` trong module |
| `NullPointerException` khi tạo GuardedInvocation | Invocation handle null | Luôn cung cấp MethodHandle hợp lệ; linker không xử lý được thì trả `null` cho request |
| `IllegalArgumentException` lúc compose | Guard/fallback/target method types không tương thích | In `MethodHandle.type()`, adapt có chủ ý |
| `WrongMethodTypeException` khi `invokeExact` | Java call site typed sai kiểu tham số/return | Cast kiểu trả về chính xác; xác nhận signature |
| `ClassCastException` sau guard pass | Guard quá rộng hoặc argument filter sai | Guard phải kiểm tra đúng assumption của target |
| Mọi receiver bị linker đưa vào cùng target | Custom linker không kiểm tra operation/receiver | Xác nhận `LinkRequest.getCallSiteDescriptor()` và `getReceiver()` |
| Guard false nhưng không thấy linker chạy | Fallback chỉ là handle trả default value | Cài đường relink-and-invoke do Dynalink cung cấp |
| `hasBeenInvalidated()==false` sau catch fallback | Getter chỉ phản ánh switchpoints | Theo dõi exception events qua metrics/fallback nếu cần |
| Switchpoint invalidated rồi nhưng invocation vẫn được gọi trực tiếp | `getInvocation()` bỏ qua guards | Gọi composite/call site; không bypass validity |
| Invalidate xong mà vẫn dùng cache version cũ | Fallback không làm relink hoặc reference mới chưa công bố | Kiểm tra `RelinkableCallSite.relink` và visibility |
| `SwitchPoint` không khôi phục được | Invalidation một chiều | Tạo SwitchPoint mới + GuardedInvocation mới |
| `addSwitchPoint` được gọi nhưng original vẫn không bị ảnh hưởng | Tuple immutable | Giữ reference tuple trả về |
| `replaceMethods` khiến guard đánh giá sai type | Thay target nhưng không adapt guard | Dùng `asType`/guard tương thích với new invocation |
| `filterArguments` khiến guard và target nhìn khác nhau | Filter hoặc input assumption không đồng nhất | Áp filter phù hợp cho cả hai bằng API tuple |
| `dropArguments` xong, compose fallback sai arity | Fallback chưa nhận tham số context mới | `MethodHandles.dropArguments` trên fallback |
| Relink quá nhiều khi nhận Box/String xen kẽ | SimpleRelinkableCallSite là monomorphic cache | Cân nhắc ChainedCallSite nếu workload đa hình |
| Không relink khi dùng `ChainedCallSite` vài loại quen thuộc | Các guarded invocations còn valid trong chain | Hiểu cache hit, đừng đồng nhất "mỗi call" với link request |
| Dùng `Throwable.class` làm invalidating exception | Bắt cả lỗi lập trình/nghiêm trọng | Chọn exception hẹp thể hiện stale assumption |
| `getSwitchPoints()` trả null | Tuple không có switchpoint | Xử lý null; không gọi `length` vô điều kiện |
| Dùng `GuardedInvocation` cho bảo mật/sandbox | Guard chỉ là điều kiện dispatch | Kiểm soát quyền truy cập ở tầng Java/module/classloader riêng |

### 13.1. Tránh fallback loop

Một linker chỉ biết xử lý `Box` nhưng guard luôn false đối với chính `Box` đó có thể khiến fallback yêu cầu relink **lặp đi lặp lại**. Triệu chứng có thể là CPU cao, stack overflow hoặc throughput giảm. Kiểm tra:

1. Linker có trả invocation phù hợp request thực tế không?
2. Guard vừa tạo có pass với receiver đang dùng không?
3. `MethodType` có khớp descriptor không?
4. Switchpoint có **đã invalidated ngay** lúc trả tuple không?
5. Có ngoại lệ dự kiến bị ném **mỗi lần** bởi invocation không?
6. Fallback có thể thoát khi không linker nào xử lý operation hay không?

Dynalink cung cấp logic quản lý relinking, nhưng nó không thể sửa một guard luôn sai hoặc assumption không bao giờ thành true.

### 13.2. "Guarded" không phải cơ chế authorization

Trong một dynamic runtime, guard `receiver instanceof AdminObject` không cấp quyền admin, không validate session và không thực thi access control theo chính sách nghiệp vụ. Nó chỉ xác định **MethodHandle fast path có áp dụng** hay không.

Nếu method đích thực hiện thao tác bảo mật, hãy kiểm tra authorization bên trong tầng domain/security thích hợp, không chỉ dựa vào guard/`SwitchPoint` để ngăn một caller không tin cậy gọi trực tiếp method.

### 13.3. MethodType của fallback phải đúng *sau* mọi adapter

Nếu GI `original` có target `(String)String` nhưng `dropArguments(0,int.class)` tạo target `(int,String)String`, fallback vẫn `(String)String` sẽ không thỏa hợp đồng compose. Ví dụ 3 chủ động:

```java
MethodHandle fallbackWithContext =
        MethodHandles.dropArguments(fallback, 0, int.class);
```

Đây là fragment. Đừng tùy tiện cast một `MethodHandle` thành kiểu generic vì Java method handle là typed invocation tại runtime; cần combinator đúng.

## 14. Phân biệt ba lớp "vô hiệu hóa"

| Cơ chế | Điều kiện kích hoạt | Tính kéo dài | Hành động ở composite | Khi dùng trong Dynalink |
| --- | --- | --- | --- | --- |
| **Guard failure** | Input hiện tại không thỏa guard | Theo từng invocation; lần sau có thể pass | Guard fallback | Relink cho receiver khác hoặc chọn path khác |
| **SwitchPoint invalidation** | Owner invalidate switchpoint từ bên ngoài | Một chiều, áp dụng cho các lần gọi sau | Switchpoint fallback | Stale schema/cache/config; phải thiết lập path mới |
| **Invalidating exception** | Target ném exception đã khai báo | Theo lần invoke; tuple không tự ghi cờ permanent | Catch fallback | Linker sửa assumption sau expected failure |

Hãy coi cả ba là những **cách trình bày "fast path không còn thích hợp"** nhưng có **tính chất và tác dụng khác nhau**. Không dùng `hasBeenInvalidated()` để đếm tất cả.

### 14.1. Các công cụ Java gần giống nhưng không thay thế hoàn toàn

- `MethodHandles.guardWithTest`: một phép chọn giữa hai handle dựa trên guard; không tự mang metadata nhiều switchpoints và exception policy.
- `SwitchPoint.guardWithTest`: một guard một chiều dựa trên invalidation; không chứa generic receiver-specific guard.
- `MethodHandles.catchException`: bắt một loại exception và gọi handler; không tự biết Dynalink relink semantics.
- `GuardedInvocation.compose`: ghép cả ba loại điều kiện cùng invocation thành composite cho runtime linker.
- `RelinkableCallSite.relink`: nhận guarded invocation từ Dynalink và cài path mới; không phải constructor `GuardedInvocation`.

Tổ hợp nào phù hợp phụ thuộc mô hình động của ngôn ngữ/framework; GuardedInvocation tiện khi muốn biểu diễn **một đề xuất linkage hoàn chỉnh có thể trao đổi** giữa các thành phần.

## 15. Bài tập mở rộng có định hướng

**Bài tập A — Guard theo receiver:** Đổi chương trình `DynalinkPipelineDemo` để nhận thêm `Integer` và trả `"number:"+value`. Gợi ý: thêm handle target, guard `instanceof Integer` và nhánh xử lý trong linker; quan sát linkRequests trên chuỗi Box → String → Integer → Box.

**Bài tập B — Schema version:** Tạo một `SwitchPoint` gắn với `GuardedInvocation` xử lý `Box`. Sau `SwitchPoint.invalidateAll`, bảo đảm có đường fallback relink để tạo một `SwitchPoint` mới, nếu không site sẽ luôn đi fallback cũ. Kiểm tra `hasBeenInvalidated()` trước/sau.

**Bài tập C — Exception policy:** Thử đổi `IllegalArgumentException.class` thành `ClassCastException.class` trong ví dụ 2; dự đoán kết quả của `composite.invokeExact("boom")`. Tại sao ngoại lệ không còn được catch fallback xử lý? Thử một expected exception thật sự biểu thị stale assumption.

**Bài tập D — Polymorphic cache:** Thay `SimpleRelinkableCallSite` bằng `ChainedCallSite` trong demo 4, giữ cùng descriptor và linker. So sánh số lần linking khi luân phiên một số receiver types, sau khi chương trình được làm nóng; đừng quên chính sách giới hạn chain.

**Bài tập E — Kiểu handle:** Thay `(Object)Object` của call site thành `(Object)String`, adapt invocation/guard phù hợp. Quan sát lỗi nếu cứ trả target với type cũ. Giải thích vì sao `asType` đúng nghĩa là một phần hợp đồng linking.

## 16. Câu hỏi tự kiểm tra

1. `GuardedInvocation` là một `CallSite`, một `MethodHandle`, hay một tuple metadata?
2. Thành phần nào của GuardedInvocation bắt buộc khác null?
3. Guard trả kiểu gì và cần tương thích với tham số của invocation như thế nào?
4. `getInvocation()` có tự kiểm tra `getGuard()` không?
5. Phân biệt `compose(fallback)` với `compose(guardFallback, switchpointFallback, catchFallback)`.
6. Khi guard false, `hasBeenInvalidated()` có tự thành true không?
7. Khi invocation ném invalidating exception, `hasBeenInvalidated()` có tự thành true không?
8. Khi một trong hai switchpoints bị invalidated, `hasBeenInvalidated()` trả gì?
9. Một SwitchPoint đã invalidated có reset thành valid được không?
10. Nếu `compose` dùng một fallback chỉ trả default value, Dynalink có bắt buộc relink không?
11. Tại sao `replaceMethods` trả GuardedInvocation mới thay vì sửa tuple gốc?
12. `addSwitchPoint(extra)` có tự làm tuple gốc nhận thêm extra không?
13. Vì sao filterArguments cần thay cả guard và invocation ở các vị trí tương ứng?
14. `dropArguments(0,int.class)` ảnh hưởng tới fallback type như thế nào?
15. Trong `DynalinkPipelineDemo`, vì sao hai lần liên tiếp gọi `Box` chỉ tạo một GuardedInvocation?
16. Vì sao luân phiên `Box → String → Box` trên `SimpleRelinkableCallSite` tạo ba link requests trong demo?
17. `ChainedCallSite` khác `SimpleRelinkableCallSite` ở chiến lược cache nào?
18. Nếu custom linker không hiểu receiver/operation, nên trả gì từ `getGuardedInvocation`?
19. `jdk.dynalink` là một phần của module nào? Với classpath application Java 17, dùng option nào ở lệnh ví dụ?
20. Một `ClassCastException` do bug implementation có luôn hợp lý để trigger relink không?

### Gợi ý trả lời

1. Là **tuple** mô tả một invocation với các điều kiện validity; `compose` mới tạo composite MethodHandle.
2. `invocation`; các điều kiện còn lại optional.
3. Primitive `boolean`, tham số tương thích với invocation theo `guardWithTest`.
4. Không; gọi getter invocation trực tiếp có thể bypass guard/switchpoint.
5. Một fallback dùng chung; overload ba fallback tách guard/switch/exception.
6. Không, chỉ là quyết định theo input.
7. Không; flag này chỉ quan sát switchpoints.
8. `true`, vì chỉ cần một switchpoint invalidated.
9. Không; tạo SwitchPoint mới.
10. Không; chỉ Dynalink relink-and-invoke fallback phù hợp mới gây relink.
11. Tuple immutable, muốn thay methods thì tạo object mới.
12. Không; chỉ tuple trả về có thêm switchpoint.
13. Để guard và target nhìn cùng data transformation, tránh assumption sai.
14. Target mới `(int,String)String`, fallback cũng cần thích ứng với call signature đó.
15. Guard `isBox` còn pass, cache hit.
16. Monomorphic cache thay một guarded invocation hiện hành khi receiver class thay đổi.
17. ChainedCallSite có thể giữ nhiều guarded invocations trong chain.
18. Trả `null` để thử linker khác, không return GuardedInvocation có invocation null.
19. Module `jdk.dynalink`; trong ví dụ chạy classpath dùng `--add-modules jdk.dynalink`.
20. Không; phải chứng minh exception thực sự đánh dấu assumption mismatch, tránh nuốt bug và vòng relink.

## 17. Tài liệu chuẩn

- [Java SE 17 API — `GuardedInvocation`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html): các constructors, getters, `hasBeenInvalidated`, `compose`, `replaceMethods`, `addSwitchPoint` và adapters.
- [Java SE 17 API — `GuardingDynamicLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html): hợp đồng `getGuardedInvocation`, trả `null` và relink requests.
- [Java SE 17 API — module `jdk.dynalink`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html): mục đích, operation model, lifecycle, Dynalink trong bytecode/interpreter.
- [Java SE 17 API — `DynamicLinkerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html) và [`DynamicLinker`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html): tạo/link call sites, prioritized linkers, fallback resolution.
- [Java SE 17 API — `SimpleRelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html) và [`ChainedCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html): monomorphic và polymorphic inline cache.
- [Java SE 17 API — `RelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/RelinkableCallSite.html): `relink`, `resetAndRelink`, `initialize` và relink-and-invoke fallback.
- [Java SE 17 API — `SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): guardWithTest, invalidation và visibility semantics.
- [Java SE 17 API — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `guardWithTest`, `filterArguments`, `dropArguments`, `catchException`.
- [Java SE 17 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `MethodType` và adapter semantics.

**Tổng kết:** `GuardedInvocation` là **invocation + guard + switchpoint invalidation + exception fallback policy**. `compose` biến tuple ấy thành một method handle có fast path/fallback. Guard false và exception chỉ quyết định theo lần gọi; `hasBeenInvalidated()` nhận biết **switchpoint invalidation một chiều**, không phải mọi loại thất bại. Khi được đặt vào Dynalink, `GuardingDynamicLinker` đưa ra guarded invocation và `RelinkableCallSite` biến guard miss/invalidation thành cơ hội **chọn target mới**. Luôn kiểm tra method types, điều kiện guard và fallback thực tế thay vì cho rằng tuple tự động relink.