# 12.7 `SwitchPoint`, `guardWithTest` và việc vô hiệu hóa một chiều

Trong `java.lang.invoke`, `SwitchPoint` đại diện cho **một giả định còn hiệu lực hoặc đã bị hủy vĩnh viễn**. Khi giả định còn đúng, một `MethodHandle` được bảo vệ sẽ gọi nhánh `target` (thường là fast path). Sau khi chương trình chủ động hủy giả định, cùng handle đó chuyển sang gọi nhánh `fallback`. Đây là công cụ quan trọng khi xây inline cache, dynamic language runtime, hệ thống liên kết lời gọi hoặc tối ưu phụ thuộc một phiên bản cấu hình.

Hai API có tên gần giống nhau nhưng khác ý nghĩa:

- `point.guardWithTest(target, fallback)` trên **`SwitchPoint`**: chọn nhánh dựa vào **trạng thái valid/invalidated của point**. Trước khi invalidation dùng target, sau đó dùng fallback. Việc vô hiệu hóa **chỉ có chiều valid → invalidated**.
- `MethodHandles.guardWithTest(test, target, fallback)`: gọi một **`test` MethodHandle trả `boolean`** để chọn nhánh theo predicate. Test có thể phụ thuộc vào input tại từng lần gọi và có thể trả true hoặc false luân phiên.

Chúng không nên bị đánh đồng. Một `SwitchPoint` **không** kiểm tra tham số người dùng, **không** tự phát hiện dữ liệu thay đổi và **không** tự reset khi fallback xong việc. Muốn bắt đầu một chu kỳ tối ưu mới sau invalidation, phải tạo `SwitchPoint` mới và guarded handle mới, rồi công bố cấu hình mới theo một protocol phù hợp.

Bài học thuộc nhóm **CallSite** vì các guarded handles có thể là target của `ConstantCallSite` hoặc `MutableCallSite`. Tuy nhiên, `SwitchPoint` **không phải CallSite**: invalidation đổi nhánh của guard nhưng không nhất thiết thay đổi target object được giữ trong CallSite.

Sau bài này bạn có thể giải thích vòng đời một chiều, phân biệt hai biến thể `guardWithTest`, xây fast/fallback tương thích `MethodType`, xử lý `invalidateAll`, ghép guard với CallSite, tránh hiểu lầm concurrency và debug exception. Các ví dụ là Java 17+ độc lập, với lệnh `javac`/`java` và stdout đã được kiểm tra bằng chạy thật.

## 1. Mục đích: tối ưu dựa trên một giả định có tuổi thọ

Giả sử một thư viện runtime đã tra được một phương thức và lưu một kết quả liên kết. Nếu cấu hình hay schema của ứng dụng không đổi, đường gọi nhanh này hợp lệ. Khi có sự kiện thay đổi cấu hình, đường gọi nhanh phải bị bỏ, còn các lời gọi tiếp theo phải đi qua resolver/fallback đúng đắn.

```text
       Giả định về schema/config còn đúng?
                    |
                 SwitchPoint
                    |
          +---------+----------+
          |                    |
       valid               invalidated
          |                    |
          v                    v
    optimized target       safe fallback
    (có thể dùng cache)    (resolve/đọc bản mới)
```

Một phép kiểm tra Java thông thường cũng có thể biểu diễn ý tưởng này:

```java
// Đoạn minh họa, không phải chương trình độc lập:
if (assumptionIsValid) {
    return fastPath(input);
}
return fallbackPath(input);
```

Tuy nhiên, khi application đã tổ chức việc gọi qua **MethodHandle chains**, `SwitchPoint` cho phép mô tả guard như một `MethodHandle` mới, giúp runtime có thể tối ưu hóa trong thời gian giả định ổn định. `SwitchPoint` không cache **giá trị kết quả** của method và không xử lý nghiệp vụ thay cho hai nhánh; bạn chủ động cung cấp cả target và fallback.

Ví dụ ứng dụng hợp lý: một generation của cache trường dữ liệu, một chiến lược method dispatch được liên kết dựa vào class hierarchy hiện tại, hoặc một rule routing có thể bị thay đổi nhưng chỉ cần **hủy hiệu lực thế hệ cũ**. Một predicate thay đổi liên tục theo từng request lại không phải mục đích thích hợp của SwitchPoint.

## 2. Vòng đời của `SwitchPoint`: một chiều

Một `SwitchPoint` mới có trạng thái **valid**:

```java
SwitchPoint point = new SwitchPoint();
System.out.println(point.hasBeenInvalidated()); // false
```

Để vô hiệu hóa:

```java
SwitchPoint.invalidateAll(new SwitchPoint[] {point});
System.out.println(point.hasBeenInvalidated()); // true
```

Hai đoạn là mã minh họa trong một class/method có import `java.lang.invoke.SwitchPoint`. `invalidateAll` là **static method**, nhận một mảng các `SwitchPoint` cần invalidation. Việc gọi nó khi một point đã invalidated không tái kích hoạt point ấy.

```text
 new SwitchPoint()
       |
       v
    VALID  ---- invalidateAll(...) ----> INVALIDATED
                                           |
                                 invalidateAll(...) thêm lần nữa
                                           |
                                           v
                                       INVALIDATED
```

**Không có `reset()`, `validate()` hay `enable()` trên `SwitchPoint`.** Đây là quy tắc thiết kế quan trọng: point mang ý nghĩa một **giả định của một thế hệ**, và thế hệ đó sau khi bị hủy không thể được phục hồi trong cùng object.

Các hệ quả:

1. Guard tạo từ point valid trước invalidation sẽ dùng target.
2. Sau invalidation, những lần gọi guard tiếp theo theo semantics API sẽ chọn fallback.
3. **Mọi guard** được tạo từ cùng point chịu cùng trạng thái invalidated, dù target/fallback của các guard khác nhau.
4. Invalidation không phá hủy object `MethodHandle` và không đổi `guard.type()`; nó thay **nhánh thực thi**.
5. Muốn fast path quay trở lại cho dữ liệu mới, tạo **point mới + guard mới**; giữ guard cũ vẫn dẫn đến fallback.
6. Những switch points khác không bị vô hiệu hóa chỉ vì một point nào đó đã bị invalidated. Bạn cần quản lý danh sách điểm phụ thuộc.

Đừng coi SwitchPoint là một boolean mutable có thể gán `true` rồi `false` nhiều lần. Nó được thiết kế để **JIT/runtime có thể tin rằng invalidated là trạng thái cuối cùng của object**.

## 3. Cách tạo guarded MethodHandle và yêu cầu chữ ký

Các bước:

```java
// Minh họa: target và fallback là MethodHandle đã được tạo.
SwitchPoint point = new SwitchPoint();
MethodHandle guarded = point.guardWithTest(target, fallback);
```

`point.guardWithTest` yêu cầu hai nhánh có **cùng `MethodType`**, bao gồm số lượng, thứ tự, kiểu tham số **và kiểu kết quả**:

```text
target.type()   = (String)String
fallback.type() = (String)String
guarded.type()  = (String)String
```

Nếu target trả `String` nhưng fallback trả `Object`, hai kiểu `(String)String` và `(String)Object` **không tương đương** dù `String` kế thừa từ `Object`. Phép dựng guard sẽ ném `IllegalArgumentException`, thay vì tự chuyển đổi return type. Tương tự, `(int)int` khác `(long)int`, và `(int)void` khác `(int)int`.

Khi thật sự muốn tạo một adapter, hãy làm rõ conversion:

```java
// Đoạn minh họa: rawFallback.type() == (String)Object.
// Việc cast Object -> String chỉ phù hợp nếu dữ liệu trả về thực sự là String.
MethodHandle convertedFallback = rawFallback.asType(
        MethodType.methodType(String.class, String.class));
MethodHandle guarded =
        point.guardWithTest(target, convertedFallback);
```

`asType` không đảm bảo mọi conversion thành công: conversion không hỗ trợ có thể gây `WrongMethodTypeException`; một reference conversion được tạo nhưng gặp object sai kiểu có thể dẫn tới `ClassCastException` lúc chạy.

### 3.1. `invokeExact` yêu cầu chữ ký tại caller khớp

Một guarded handle kiểu `(String)String` phải được gọi với **static argument type `String`** và kiểu kết quả **`String`** ở call site:

```java
// guarded.type() == (String)String
String name = "Ada";
String answer = (String) guarded.invokeExact(name);
```

Ngược lại:

```java
// Mã minh họa gọi sai, sẽ ném WrongMethodTypeException:
Object value = "Ada";
String answer = (String) guarded.invokeExact(value);
```

Giá trị runtime của `value` là `String`, nhưng kiểu **tĩnh** của argument là `Object`; descriptor của caller không khớp `(String)String`. Đây là lỗi của `MethodHandle.invokeExact`, không phải lỗi invalidation.

Cần phân biệt **hai tầng type check**: khi tạo guard, target và fallback phải có type giống nhau; khi gọi bằng `invokeExact`, descriptor của caller phải khớp type của guard.

## 4. Ví dụ độc lập 1 — `SwitchPoint` chuyển fast → fallback

Tạo file **`SwitchPointDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class SwitchPointDemo {
    private static String fast(String value) {
        return "cache:" + value;
    }

    private static String slow(String value) {
        return "fresh:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle fast = lookup.findStatic(SwitchPointDemo.class, "fast", type);
        MethodHandle slow = lookup.findStatic(SwitchPointDemo.class, "slow", type);

        SwitchPoint point = new SwitchPoint();
        MethodHandle guard = point.guardWithTest(fast, slow);

        System.out.println("type: " + guard.type());
        System.out.println("invalid before: " + point.hasBeenInvalidated());
        System.out.println("before: " + (String) guard.invokeExact("Ada"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});

        System.out.println("invalid after: " + point.hasBeenInvalidated());
        System.out.println("after: " + (String) guard.invokeExact("Ada"));
        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        System.out.println("after repeat: " + (String) guard.invokeExact("Lin"));

        SwitchPoint replacement = new SwitchPoint();
        MethodHandle newGuard = replacement.guardWithTest(fast, slow);
        System.out.println("replacement invalid: " + replacement.hasBeenInvalidated());
        System.out.println("replacement: " + (String) newGuard.invokeExact("Lin"));
        System.out.println("old still: " + (String) guard.invokeExact("Lin"));
    }
}
```

Biên dịch và chạy JDK 17+:

```bash
javac --release 17 SwitchPointDemo.java
java SwitchPointDemo
```

Stdout đã được kiểm tra:

```text
type: (String)String
invalid before: false
before: cache:Ada
invalid after: true
after: fresh:Ada
after repeat: fresh:Lin
replacement invalid: false
replacement: cache:Lin
old still: fresh:Lin
```

Diễn giải:

- `findStatic` trả MethodHandles cho `fast` và `slow`, đều có `(String)String`.
- Point mới còn valid nên `guard.invokeExact("Ada")` đi qua `fast`, in `cache:Ada`.
- `invalidateAll` chuyển point sang invalidated. Guard vẫn hợp lệ, nhưng giờ gọi `slow`, in `fresh:Ada`.
- Invalidate lần nữa không thay đổi trạng thái. Với input mới `Lin`, guard vẫn dùng slow.
- `replacement` là đối tượng **mới** nên valid. `newGuard` có thể chọn fast path; guard **cũ** không quay lại fast.

Bản thân `fast` và `slow` trong ví dụ chỉ trả string để dễ quan sát. Trong runtime thật, fallback thường phải **resolve lại dữ liệu**, đọc nguồn nhất quán hoặc xử lý đường an toàn khác. SwitchPoint không tự cấp logic “fresh”.

## 5. Hai biến thể `guardWithTest` khác nhau

Đây là cặp API trọng tâm cần nhớ:

```java
MethodHandle conditionally = MethodHandles.guardWithTest(
        booleanTestHandle, target, fallback);

MethodHandle generationGuard = point.guardWithTest(
        target, fallback);
```

Đoạn này là mã minh họa, với các biến đã được khai báo trong scope. Cả hai đều tạo `MethodHandle` có `type()` bằng `target.type()` và `fallback.type()`, nhưng **nguồn quyết định chọn nhánh** khác nhau.

| Tiêu chí | `MethodHandles.guardWithTest(test,target,fallback)` | `SwitchPoint.guardWithTest(target,fallback)` |
| --- | --- | --- |
| Điều kiện | Kết quả `boolean` của `test` handle | Trạng thái valid/invalidated của point |
| Khi nào chọn nhánh | Kiểm tra predicate theo mỗi lời gọi | Chọn theo trạng thái point |
| Có phụ thuộc arguments? | Có thể; test nhận các arguments phù hợp | Không do API; point không nhận argument để test |
| Có thể true → false → true? | Có nếu predicate trả kết quả như vậy | Không: invalidated không thể thành valid |
| API hủy hiệu lực | Không có invalidation riêng của combinator | `SwitchPoint.invalidateAll(...)` |
| Mục tiêu điển hình | Điều kiện nghiệp vụ, loại input, selector | Hủy giả định về cache/optimization generation |
| Type constraint | Target/fallback cùng type; test trả boolean và tham số là prefix phù hợp | Target/fallback cùng type |

### 5.1. `MethodHandles.guardWithTest` yêu cầu test trả boolean

Với target/fallback kiểu `(String,int)String`, có thể dùng test `(String)boolean` chỉ kiểm tra đối số đầu tiên. Test nhận **prefix của arguments**; nếu test trả true thì target chạy với **toàn bộ arguments**, false thì fallback cũng nhận toàn bộ arguments.

Ví dụ các chữ ký hợp lệ:

```text
test:     (String)boolean
target:   (String,int)String
fallback: (String,int)String
guard:    (String,int)String
```

Test `(String)int` **không hợp lệ** vì Java không tự coi 0 là false và 1 là true. Test có kiểu parameter không khớp prefix cũng sai. Những lỗi này thường được phát hiện ngay khi tạo guard bằng `IllegalArgumentException`.

### 5.2. SwitchPoint không kiểm tra từng request

Giả sử cần chọn ưu đãi tùy tên user. Nếu dùng SwitchPoint valid thì **mọi** tên user đi qua target, kể cả user không đủ điều kiện. Sau invalidation **mọi** tên user đi qua fallback. Trong trường hợp đó, cần **boolean predicate handle** hoặc `if/else`, không phải một invalidation switch.

Có thể lồng các guards trong một runtime phức tạp: SwitchPoint quyết định cache generation còn hợp lệ không, và predicate quyết định xử lý input cụ thể. Tuy nhiên, thứ tự kiểm tra, type signature và security requirements phải được thiết kế rõ; không dùng SwitchPoint để bỏ qua kiểm tra quyền bắt buộc.

## 6. Ví dụ độc lập 2 — predicate và switch point

Tạo file **`GuardComparisonDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class GuardComparisonDemo {
    private static boolean isVip(String user) {
        return user.equals("vip");
    }

    private static String preferred(String user) {
        return "VIP:" + user;
    }

    private static String standard(String user) {
        return "STANDARD:" + user;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringToString = MethodType.methodType(String.class, String.class);
        MethodHandle condition = lookup.findStatic(
                GuardComparisonDemo.class, "isVip",
                MethodType.methodType(boolean.class, String.class));
        MethodHandle preferred = lookup.findStatic(
                GuardComparisonDemo.class, "preferred", stringToString);
        MethodHandle standard = lookup.findStatic(
                GuardComparisonDemo.class, "standard", stringToString);

        MethodHandle conditional =
                MethodHandles.guardWithTest(condition, preferred, standard);
        System.out.println("conditional vip: "
                + (String) conditional.invokeExact("vip"));
        System.out.println("conditional guest: "
                + (String) conditional.invokeExact("guest"));

        SwitchPoint point = new SwitchPoint();
        MethodHandle epochGuard = point.guardWithTest(preferred, standard);
        System.out.println("switchpoint guest before: "
                + (String) epochGuard.invokeExact("guest"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        System.out.println("switchpoint vip after: "
                + (String) epochGuard.invokeExact("vip"));
    }
}
```

Chạy:

```bash
javac --release 17 GuardComparisonDemo.java
java GuardComparisonDemo
```

Stdout kiểm chứng:

```text
conditional vip: VIP:vip
conditional guest: STANDARD:guest
switchpoint guest before: VIP:guest
switchpoint vip after: STANDARD:vip
```

**Tại sao output cố ý khác nhau?**

`conditional` gọi `isVip(user)`: user `"vip"` được chọn target, user `"guest"` chọn fallback. Nó rẽ nhánh theo **dữ liệu của lời gọi**.

`epochGuard` **không** gọi `isVip`. Khi point valid, ngay cả `"guest"` cũng đi nhánh `preferred`; sau khi invalidated, ngay cả `"vip"` cũng đi nhánh `standard`. Nó chọn nhánh theo **trạng thái thế hệ**, không theo dữ liệu user.

Bởi vậy, **không** được thay combinator predicate bằng SwitchPoint nếu target chứa một hành động đòi điều kiện quyền hay điều kiện nghiệp vụ riêng của từng user.

## 7. Quan hệ với `CallSite`: mục đích khác nhau

`CallSite` trong `java.lang.invoke` giữ một **target `MethodHandle`** có type ổn định. Những trường hợp thường gặp:

- `ConstantCallSite`: target reference được cố định sau khởi tạo.
- `MutableCallSite`: `setTarget` cho phép đổi target sang handle khác **cùng `MethodType`**; có quy tắc publication/synchronization, chẳng hạn `syncAll`.
- `VolatileCallSite`: target có thể được thay với volatile semantics về khả năng quan sát giữa threads.

`SwitchPoint` **không** là subclass của CallSite. Nó tạo một **guarded handle**. Handle này có thể đặt vào `CallSite` như một target:

```java
// Đoạn minh họa đã có point, fast và fallback.
MethodHandle guard = point.guardWithTest(fast, fallback);
CallSite site = new ConstantCallSite(guard);
MethodHandle invoker = site.dynamicInvoker();
```

Sau invalidation, **`site.getTarget()` vẫn là object `guard`** nếu site là ConstantCallSite. Nhưng hành vi guard có thể đổi vì point đã invalidated. Điều này không trái với tính “Constant”: đó là tính bất biến **của MethodHandle target được lưu**, không phải bảo đảm kết quả tính toán bên trong target không bao giờ đổi.

`MutableCallSite` có bài toán khác: có thể đổi hẳn target nhiều lần (fast → fallback → fast), nếu luôn giữ cùng type và publication đúng. SwitchPoint cũ thì **không thể** tái hợp lệ.

## 8. Ví dụ độc lập 3 — `ConstantCallSite` và `MutableCallSite`

Tạo file **`CallSiteSwitchPointDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.SwitchPoint;

public class CallSiteSwitchPointDemo {
    private static int fast(int number) {
        return number + 100;
    }

    private static int fallback(int number) {
        return number + 1;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(int.class, int.class);
        MethodHandle fast = lookup.findStatic(
                CallSiteSwitchPointDemo.class, "fast", type);
        MethodHandle fallback = lookup.findStatic(
                CallSiteSwitchPointDemo.class, "fallback", type);

        SwitchPoint point = new SwitchPoint();
        MethodHandle guard = point.guardWithTest(fast, fallback);
        CallSite site = new ConstantCallSite(guard);
        MethodHandle invoker = site.dynamicInvoker();

        int before = (int) invoker.invokeExact(5);
        System.out.println("constant before: " + before);

        SwitchPoint.invalidateAll(new SwitchPoint[] {point});
        int after = (int) invoker.invokeExact(5);
        System.out.println("constant after: " + after);
        System.out.println("constant target same: "
                + (site.getTarget() == guard));

        MutableCallSite mutable = new MutableCallSite(fast);
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("mutable fast: " + (int) dynamic.invokeExact(5));
        mutable.setTarget(fallback);
        MutableCallSite.syncAll(new MutableCallSite[] {mutable});
        System.out.println("mutable fallback: " + (int) dynamic.invokeExact(5));
        mutable.setTarget(fast);
        MutableCallSite.syncAll(new MutableCallSite[] {mutable});
        System.out.println("mutable fast again: "
                + (int) dynamic.invokeExact(5));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CallSiteSwitchPointDemo.java
java CallSiteSwitchPointDemo
```

Stdout đã kiểm chứng:

```text
constant before: 105
constant after: 6
constant target same: true
mutable fast: 105
mutable fallback: 6
mutable fast again: 105
```

`ConstantCallSite` giữ cùng một guard object. Trước invalidation, `invoker.invokeExact(5)` trả `105`; sau invalidation, vẫn qua **chính invoker và guard ấy** nhưng nhánh fallback trả `6`. Phép kiểm tra `site.getTarget() == guard` là `true`.

`MutableCallSite` ở nửa sau chương trình đổi target từ `fast` sang `fallback` rồi quay về `fast` — điều mà một SwitchPoint **đã invalidated** không làm được. Tất cả target đều kiểu `(int)int`; `syncAll` được dùng để minh họa API publication.

**Lưu ý:** gọi `CallSite.dynamicInvoker()` bằng Java source là một bài kiểm tra CallSite API. Nó **không tự tạo opcode `invokedynamic` tùy biến**. Khi một instruction `invokedynamic` thật được liên kết tới CallSite có target guarded handle, sự chuyển nhánh nội bộ cũng có thể được quan sát theo semantics này.

## 9. Nhiều guarded handles cùng phụ thuộc một SwitchPoint

Nếu nhiều đường nhanh dựa vào cùng giả định “schema V1 hợp lệ”, có thể dùng một SwitchPoint để tạo nhiều guards. Khi hủy giả định, gọi `invalidateAll` với chính point ấy để tất cả guards liên quan chuyển sang fallback.

```text
SwitchPoint A
   |
   +-- guard A1: target1 / fallback1
   |
   +-- guard A2: target2 / fallback2

SwitchPoint B
   |
   +-- guard B1: target3 / fallback3

invalidateAll([A]):
  guard A1 -> fallback1
  guard A2 -> fallback2
  guard B1 -> còn target3 nếu B valid
```

Các guarded handles **khác nhau** dùng cùng point **không cần có cùng MethodType với nhau**: quy tắc cùng type chỉ áp dụng **bên trong mỗi cặp target/fallback khi tạo một guard**. Point chỉ mang state valid/invalidated chung.

### 9.1. Vô hiệu hóa theo nhóm

```java
SwitchPoint.invalidateAll(new SwitchPoint[] {point1, point2});
```

Mảng xác định **những point muốn invalid**; không phải lệnh hủy mọi SwitchPoint trên JVM. Nếu hai assumptions liên quan mật thiết, bạn có thể quản lý chúng trong cùng operation. Nếu độc lập, hủy một point không nên kéo theo point còn lại.

Không coi việc invalidating một mảng nhiều point là **transaction nguyên tử cập nhật tất cả dữ liệu nghiệp vụ**. Các snapshots, maps, registry và lifecycle của code vẫn đòi protocol đồng bộ riêng.

## 10. Ví dụ độc lập 4 — hai points, ba guards

Tạo file **`InvalidationGroupDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;

public class InvalidationGroupDemo {
    private static String active(String value) {
        return "active:" + value;
    }

    private static String retired(String value) {
        return "retired:" + value;
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle active = lookup.findStatic(
                InvalidationGroupDemo.class, "active", type);
        MethodHandle retired = lookup.findStatic(
                InvalidationGroupDemo.class, "retired", type);

        SwitchPoint first = new SwitchPoint();
        SwitchPoint second = new SwitchPoint();
        MethodHandle a = first.guardWithTest(active, retired);
        MethodHandle b = first.guardWithTest(active, retired);
        MethodHandle c = second.guardWithTest(active, retired);

        System.out.println("a before: " + (String) a.invokeExact("A"));
        System.out.println("b before: " + (String) b.invokeExact("B"));
        System.out.println("c before: " + (String) c.invokeExact("C"));

        SwitchPoint.invalidateAll(new SwitchPoint[] {first, second});

        System.out.println("a after: " + (String) a.invokeExact("A"));
        System.out.println("b after: " + (String) b.invokeExact("B"));
        System.out.println("c after: " + (String) c.invokeExact("C"));
        System.out.println("states: "
                + first.hasBeenInvalidated() + ","
                + second.hasBeenInvalidated());
    }
}
```

Chạy:

```bash
javac --release 17 InvalidationGroupDemo.java
java InvalidationGroupDemo
```

Stdout đã được kiểm tra:

```text
a before: active:A
b before: active:B
c before: active:C
a after: retired:A
b after: retired:B
c after: retired:C
states: true,true
```

`a` và `b` cùng dùng `first`, còn `c` dùng `second`. Invalidate cả hai points làm cả ba guards chuyển sang fallback. Nếu chỉ truyền `first`, guard `c` vẫn chọn target khi `second` còn valid.

Đây là cách quan sát rõ **invalidation ảnh hưởng các guards phụ thuộc một point**, không phải xóa MethodHandles và cũng không tự làm mất hiệu lực những points độc lập.

## 11. Lỗi khi dựng guard và khi gọi guard

`SwitchPoint.guardWithTest` và `MethodHandles.guardWithTest` kiểm tra hợp đồng kiểu ở bước tạo combinator; `MethodHandle.invokeExact` kiểm tra kiểu ở bước gọi.

| Vị trí lỗi | Dấu hiệu | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| `point.guardWithTest(target,fallback)` | `IllegalArgumentException` | `target.type()` khác `fallback.type()` |
| `MethodHandles.guardWithTest(test,target,fallback)` | `IllegalArgumentException` | Test không trả boolean, tham số test không phù hợp hoặc hai branch types khác |
| `guard.invokeExact(...)` | `WrongMethodTypeException` | Descriptor caller không bằng `guard.type()`: argument static types hoặc return cast sai |
| `lookup.findStatic(...)` | `NoSuchMethodException` | Tên, class, static kind hoặc MethodType lookup sai |
| `lookup.findStatic(...)` | `IllegalAccessException` | Lookup thiếu quyền truy cập vào target |
| Body của target/fallback | Ngoại lệ nghiệp vụ | Target đã được gọi và tự ném lỗi; không mặc định do guard type hay invalidation |

Nếu dùng `asType` để đổi chữ ký một nhánh, cần hiểu adaptation có thể ném `WrongMethodTypeException` ngay khi tạo adapter hoặc gây runtime cast error sau đó. Không “chữa” mismatch bằng một cast mơ hồ mà không biết object thực tế.

### 11.1. Ví dụ độc lập 5 — ba loại mismatch

Tạo file **`GuardTypeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.SwitchPoint;
import java.lang.invoke.WrongMethodTypeException;

public class GuardTypeDemo {
    private static String text(String input) {
        return "text:" + input;
    }
    private static Object object(String input) {
        return "object:" + input;
    }
    private static boolean valid(String input) {
        return input.length() > 0;
    }
    private static int wrongTest(String input) {
        return input.length();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType stringType = MethodType.methodType(String.class, String.class);
        MethodHandle good = lookup.findStatic(GuardTypeDemo.class, "text", stringType);
        MethodHandle wrongReturn = lookup.findStatic(GuardTypeDemo.class, "object",
                MethodType.methodType(Object.class, String.class));
        MethodHandle goodTest = lookup.findStatic(GuardTypeDemo.class, "valid",
                MethodType.methodType(boolean.class, String.class));
        MethodHandle wrongTest = lookup.findStatic(GuardTypeDemo.class, "wrongTest",
                MethodType.methodType(int.class, String.class));
        SwitchPoint point = new SwitchPoint();

        try {
            point.guardWithTest(good, wrongReturn);
        } catch (IllegalArgumentException e) {
            System.out.println("switchpoint mismatch: IllegalArgumentException");
        }
        try {
            MethodHandles.guardWithTest(wrongTest, good, good);
        } catch (IllegalArgumentException e) {
            System.out.println("predicate mismatch: IllegalArgumentException");
        }
        MethodHandle guarded = MethodHandles.guardWithTest(goodTest, good, good);
        try {
            Object broad = "ok";
            String no = (String) guarded.invokeExact(broad);
            System.out.println(no);
        } catch (WrongMethodTypeException e) {
            System.out.println("call mismatch: WrongMethodTypeException");
        }
        System.out.println("correct: " + (String) guarded.invokeExact("ok"));
    }
}
```

Chạy:

```bash
javac --release 17 GuardTypeDemo.java
java GuardTypeDemo
```

Stdout đã kiểm tra:

```text
switchpoint mismatch: IllegalArgumentException
predicate mismatch: IllegalArgumentException
call mismatch: WrongMethodTypeException
correct: text:ok
```

Ở lỗi đầu, `good` là `(String)String` còn `wrongReturn` là `(String)Object`; hai branches không cùng type. Ở lỗi hai, test trả `int` thay vì `boolean`. Ở lỗi ba, guard đã hợp lệ nhưng caller truyền biến có static type `Object`; cần `String`. Cuối cùng `(String) guarded.invokeExact("ok")` đúng descriptor và chạy được.

Khi debug, in `test.type()`, `target.type()`, `fallback.type()` và `guard.type()` thay vì chỉ nhìn source methods cùng tên.

## 12. Concurrency: invalidate không hủy công việc đang chạy

`SwitchPoint.invalidateAll` chuyển trạng thái guard theo semantics của API. Nhưng **không có nghĩa mọi lời gọi đã bắt đầu trước invalidation phải dừng**, hoặc một transaction nghiệp vụ đã thực thi nửa chừng được rollback.

Ví dụ về một interleaving có thể xảy ra:

```text
Thread A                              Thread B
------------------------------------------------------------
bắt đầu gọi guarded handle
đã đi vào fast target
                                      cấu hình thay đổi
                                      invalidateAll(point)
fast target hoàn tất
                                      lời gọi tiếp theo chọn fallback
```

Chương trình muốn **thu hồi quyền ngay cả đối với in-flight operations**, đợi toàn bộ requests cũ hoàn tất trước khi thay cấu hình, hoặc yêu cầu transactional consistency phải có một **synchronization protocol riêng**. `SwitchPoint` không đóng vai trò cancellation token cho target đã thực thi.

### 12.1. Công bố snapshot/configuration phải thread-safe

Ví dụ fast path đọc `Map` hoặc object snapshot thế hệ cũ. Dù invalidation chuyển guard sang fallback, các dữ liệu liên quan vẫn cần đúng quy tắc Java Memory Model:

- Writer xây snapshot mới trước khi công bố.
- Reader nhận snapshot mới thông qua `volatile`, lock, immutable object được công bố an toàn hoặc một cơ chế happens-before phù hợp.
- Fallback không dùng ngầm cache cũ nếu cache đã mất hiệu lực.
- Các references đã được caller cũ giữ chỉ được thu hồi/đóng theo lifecycle an toàn.
- Nếu điều kiện cần “không lời gọi nào được chạy fast sau một điểm thời gian giao dịch”, phải bổ sung protocol để điều phối các lời gọi đang chạy.

`hasBeenInvalidated()` hữu ích cho quan sát, **không** tự tạo atomicity cho chuỗi thao tác:

```java
// Mã minh họa check-then-act có race:
if (!point.hasBeenInvalidated()) {
    useOldSnapshot();
}
```

Point có thể bị invalidated giữa câu `if` và `useOldSnapshot()`. Không dựa vào check này như một rào chắn hoàn chỉnh đối với giao dịch nhiều bước.

### 12.2. Không invalidate theo từng request

SwitchPoint được xây cho **giả định tương đối ổn định** rồi bị hủy khi có sự kiện thực sự. Việc tạo/invalidating vô số points trên hot path có thể làm tăng chi phí và độ phức tạp mà không đem lại lợi ích. Nếu một điều kiện thay đổi liên tục theo từng đầu vào, dùng predicate guard hoặc Java `if`.

Bên cạnh chi phí tạo object và method handle chain, invalidation có thể ảnh hưởng tối ưu hóa JIT/runtime tùy triển khai. Không có bảo đảm `SwitchPoint` luôn nhanh hơn một branch trực tiếp hoặc `MutableCallSite`. Hãy kiểm chứng semantics trước rồi benchmark với workload thật.

## 13. Thiết kế theo generation: muốn nhanh lại phải có point mới

Một cách thiết kế là mỗi **generation** có một snapshot, một `SwitchPoint` và một guarded handle riêng:

```text
Generation 1:
   snapshotV1
   pointV1 (valid)
   guardV1 = pointV1.guardWithTest(cachedV1, resolver)

Configuration update:
   invalidate(pointV1)
   guardV1 từ nay dùng resolver/fallback

Generation 2:
   xây snapshotV2 và cachedV2
   pointV2 = new SwitchPoint()
   guardV2 = pointV2.guardWithTest(cachedV2, resolver)
   publish generation 2 an toàn

Caller còn giữ guardV1: fallback.
Caller nhận guardV2: fast path khi pointV2 valid.
```

Sơ đồ là kiến trúc logic, **không phải implementation concurrency đầy đủ**. Thứ tự invalidate, xây và publish phải phù hợp tính nhất quán của hệ thống. Nếu người dùng cần strong consistency hoặc zero downtime, cần thêm version checks, double buffering, locks hoặc quản lý in-flight operations.

Một fallback tốt nên:

1. Đưa ra kết quả đúng khi cache hoàn toàn hết hạn.
2. Không vô tình gọi lại **chính guard cũ đã invalid** theo vòng lặp vô hạn.
3. Giữ đúng `MethodType` của fast target.
4. Có đường xử lý lỗi resolver rõ ràng (nêu cause, retry có giới hạn nếu thích hợp).
5. Nếu thiết kế tự relink, phải có trách nhiệm cập nhật registry/callsite và publication an toàn.
6. Không xuất bản generation mới trước khi các target/adapter/snapshot đã sẵn sàng.

### 13.1. So sánh với việc relink `MutableCallSite`

Có hai mô hình hợp lệ nhưng không giống nhau:

- **SwitchPoint theo generation:** invalidated V1, tạo `pointV2` và `guardV2`, công bố handle/generation mới. Guard V1 tiếp tục fallback.
- **MutableCallSite:** `setTarget(newTarget)` đổi trực tiếp target của cùng CallSite object; có thể tiếp tục đổi sang các target khác miễn cùng `MethodType` và xử lý sync phù hợp.

Có thể kết hợp cả hai, nhưng không bắt buộc. SwitchPoint dễ diễn đạt “hủy giả định này vĩnh viễn”, MutableCallSite dễ diễn đạt “đây là implementation đang được liên kết”. Nên chọn theo lifecycle thật, không theo tên API.

### 13.2. Một point có thể dùng cho nhiều type khác nhau

Giả sử một schema rule ảnh hưởng hai operations:

```text
lookupUser:  (long)User
lookupOrder: (long)Order
```

Bạn có thể xây `guardUser = point.guardWithTest(userFast,userFallback)` và `guardOrder = point.guardWithTest(orderFast,orderFallback)`. Không cần `guardUser.type()` bằng `guardOrder.type()`. Chỉ cần **mỗi** cặp fast/fallback có cùng type. Invalidate point đó ảnh hưởng cả hai.

Đây là lợi thế khi quản lý một giả định chung, nhưng cũng là rủi ro nếu gom nhiều assumptions độc lập vào một point làm invalidation quá rộng.

## 14. Lỗi và hiểu lầm thường gặp

**1. “SwitchPoint có thể reset sau invalidate.”** Sai. Vòng đời một chiều; new generation cần new point.

**2. “SwitchPoint tự phát hiện Map/config thay đổi.”** Sai. Application phải chủ động gọi `invalidateAll` khi assumption bị phá.

**3. “SwitchPoint guard đọc boolean predicate mỗi lần.”** Sai. Nó dùng trạng thái point; `MethodHandles.guardWithTest` mới nhận predicate handle.

**4. “Dùng SwitchPoint để phân biệt user VIP và guest.”** Sai nếu chỉ dựa vào trạng thái point: mọi argument trong cùng epoch chọn cùng branch. Điều kiện theo user phải được kiểm tra riêng.

**5. “Target/fallback cùng số argument là đủ.”** Sai. Từng argument type và return type phải trùng. `(String)Object` không giống `(String)String`.

**6. “`invokeExact` sẽ tự cast `Object` thành `String`.”** Sai. Call-site descriptor phải chính xác; cast argument trước nếu object thực sự đúng kiểu, hoặc dùng API adaptation theo chính sách.

**7. “Invalidate point sửa luôn target của CallSite.”** Sai. Guard có thể đổi hành vi bên trong `ConstantCallSite` trong khi `getTarget()` không đổi.

**8. “`MutableCallSite` cũng chỉ đổi một chiều.”** Sai. Nó có thể `setTarget` nhiều lần tới các handles có cùng `MethodType`, khác hẳn vòng đời SwitchPoint.

**9. “Sau invalidate, mọi thread ngừng dùng fast ngay cả khi đã chạy vào target.”** Không được bảo đảm theo mô hình transaction. Phải xử lý in-flight work riêng.

**10. “`hasBeenInvalidated` bảo đảm code tiếp theo nhất quán.”** Không. Check-then-act vẫn có race; không thay một synchronization protocol.

**11. “Một `SwitchPoint` tương đương toàn bộ cache invalidation framework.”** Không. Point chỉ là điều kiện cho method-handle guards; cache contents, registry và resource lifecycle là trách nhiệm của code bạn.

**12. “Guard lúc nào cũng có hiệu năng tốt hơn `if`.”** Không có cam kết tuyệt đối. Performance phụ thuộc JIT, tần suất invalidation, shape của handles và workload.

**13. “Nếu invalidate lại, sẽ có một nhánh trung gian.”** Sai. Invalidation lần hai không đảo ngược hay tạo thêm state mới.

**14. “Bất kỳ MethodHandles nào dùng cùng point phải có cùng signature.”** Sai. Chỉ target/fallback **trong cùng một guard** cần cùng type; các guards có thể khác type.

**15. “Fallback chạy nghĩa là dữ liệu mới đã tự xuất hiện.”** Sai. Fallback cần tự resolve/read một state đúng đắn theo application contract.

## 15. Bảng chẩn đoán nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Guard luôn vào fast | Đã invalidate đúng **instance point** mà guard đang giữ chưa? | Kiểm tra reference point và `hasBeenInvalidated()`; tránh tạo nhầm một point khác |
| Guard luôn vào fallback | Point đã invalid trước khi dùng? | Tạo generation mới; không tái sử dụng invalidated point |
| Invalidate rồi kết quả vẫn cũ | Có lời gọi in-flight? Fallback có dùng cache cũ? Caller giữ guard khác? | Kiểm tra dependency/lifecycle và synchronization |
| `point.guardWithTest` ném `IllegalArgumentException` | So sánh `target.type()`, `fallback.type()` | Sửa exact `MethodType` hoặc adapter tường minh |
| `MethodHandles.guardWithTest` ném `IllegalArgumentException` | `test.type()` có return boolean và parameters prefix đúng? | Sửa test type và branch type |
| `invokeExact` ném `WrongMethodTypeException` | Static argument types và return cast của caller | Làm call-site descriptor khớp `guard.type()` |
| Lookup ném `IllegalAccessException` | Scope của `MethodHandles.Lookup` và Java modules | Sửa access contract, không đổ cho SwitchPoint |
| `MutableCallSite.setTarget` thất bại | Type target mới so với `site.type()` | Chuẩn hóa target trước khi gán |
| Một thread không quan sát đúng target mới của MutableCallSite | Protocol publication, `syncAll` | Dùng đúng Mutable/VolatileCallSite semantics |
| Memory giữ nhiều snapshots cũ | Registry/callers còn giữ generations/guards cũ | Quản lý lifecycle và reference retention an toàn |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `SwitchPoint point = new SwitchPoint();` có `hasBeenInvalidated()` là gì?

**Đáp án:** `false`. Point mới valid; guard tạo từ nó chọn target cho đến khi bị invalid.

**Câu 2.** Invalidate cùng point hai lần có bật lại fast path không?

**Đáp án:** Không. Point invalidated vĩnh viễn; muốn fast path mới phải tạo point/guard mới.

**Câu 3.** Hai guarded handles cùng gắn với một point bị invalid. Chúng có cùng chuyển fallback không?

**Đáp án:** Có. Tất cả guards phụ thuộc point đó sẽ chọn fallback sau invalidation theo semantics API.

**Câu 4.** Một predicate `isAdmin(String)` tùy user cần guard nào?

**Đáp án:** Dùng `MethodHandles.guardWithTest(test,target,fallback)` hoặc `if` thông thường. SwitchPoint không tự kiểm tra username và không thay thế kiểm tra quyền.

**Câu 5.** Vì sao target `(String)String`, fallback `(String)Object` không thể đưa trực tiếp vào `point.guardWithTest`?

**Đáp án:** `MethodType` khác return type; cần hai nhánh có type chính xác bằng nhau hoặc adapter hợp lệ.

**Câu 6.** `guard.type()` là `(String)String` nhưng caller truyền `Object s = "A"` cho `invokeExact`. Điều gì xảy ra?

**Đáp án:** `WrongMethodTypeException` vì static caller argument type là `Object`, không phải `String`.

**Câu 7.** Invalidate guard được giữ trong `ConstantCallSite` có cần đổi `CallSite.getTarget()`?

**Đáp án:** Không. Target reference vẫn là cùng guarded handle, nhưng logic trong handle chọn fallback.

**Câu 8.** `MutableCallSite` có thể đổi target từ fast sang slow rồi fast không?

**Đáp án:** Có nếu cùng type và publication đúng; khác với invalidation một chiều của SwitchPoint.

**Câu 9.** Thread đã bắt đầu fast path trước invalidation có bị tự động cancel không?

**Đáp án:** Không. SwitchPoint không thay thế cancellation hoặc transaction barrier; phải thêm protocol concurrency nếu cần.

**Câu 10.** Guard mới dựng từ một point **đã invalidated** có trở lại fast path không?

**Đáp án:** Không. Vẫn dùng trạng thái point đó; cần new SwitchPoint.

**Câu 11.** `test` của `MethodHandles.guardWithTest` có được trả `int` để biểu diễn true/false không?

**Đáp án:** Không. Phải trả `boolean`.

**Câu 12.** Khi nào dùng hai SwitchPoints thay vì một?

**Đáp án:** Khi hai assumptions độc lập và invalidation của một không nên ảnh hưởng các guards của assumption kia.

**Câu 13.** Điểm nào làm `SwitchPoint` có lợi cho cache generation?

**Đáp án:** Nhiều guarded handles có thể dùng một point cho một assumption, invalidation hủy thế hệ cũ một chiều, giúp xây generation mới tách bạch.

**Câu 14.** `SwitchPoint` có tự bảo đảm memory visibility của mọi Map/snapshot mà fast và fallback dùng không?

**Đáp án:** Không. Dữ liệu ngoài guard vẫn cần safe publication, synchronization và ownership đúng.

**Câu 15.** Hai guards dùng cùng point nhưng khác MethodTypes có được không?

**Đáp án:** Được. Quy tắc bằng type chỉ yêu cầu target/fallback của **mỗi guard** giống nhau; các guards khác nhau có thể có signatures khác nhau.

## 17. Thực hành mở rộng

### Bài tập A — Làm mới một cache version

Thiết kế target `cachedPrice(String sku)` và fallback `resolvePrice(String sku)` cùng kiểu `(String)long`. Cho `SwitchPoint` của snapshot V1 bắt đầu valid, gọi guard để quan sát fast. Khi giá cập nhật, invalidate V1; gọi guard cũ để quan sát resolver. Sau đó xây snapshot V2, tạo point V2 và guard V2 để fast path mới hoạt động.

**Kỳ vọng:** point V1 không thể được kích hoạt trở lại; tạo point V2 mới là cách hợp lệ. Nếu có nhiều threads, phải công bố snapshot/guard V2 an toàn.

### Bài tập B — Tách hai assumptions

Tạo `pointForSchema` và `pointForPlugin` riêng, mỗi point bảo vệ hai guards có type giống nhau trong từng cặp. Invalidate chỉ schema: guards của plugin vẫn fast. Invalidate plugin: cả hai nhóm giờ vào fallback, nhưng vì **hai sự kiện riêng**.

**Kỳ vọng:** phạm vi invalidation theo reference của point, không theo tên method hay global registry.

### Bài tập C — So sánh với predicate theo argument

Tạo `isVip(String)` trả boolean và dùng `MethodHandles.guardWithTest` để chọn `preferred`/ `standard`. Dùng nhiều username để minh họa branch thay đổi theo input, không cần invalidate một object nào.

**Kỳ vọng:** một boolean test có thể true/false ở các lần gọi khác nhau. SwitchPoint không phải công cụ thay thế.

## 18. Tài liệu chuẩn

- Java SE 17, **`SwitchPoint`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html — trạng thái valid/invalidated, `guardWithTest`, `invalidateAll`, `hasBeenInvalidated`.
- Java SE 17, **`MethodHandles.guardWithTest`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — boolean test combinator, type constraints, lookup.
- Java SE 17, **`MethodHandle`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — `invokeExact`, `asType`, method-handle types.
- Java SE 17, **`MethodType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html — parameter list và return type.
- Java SE 17, **`CallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html — `getTarget`, `dynamicInvoker`, method type.
- Java SE 17, **`ConstantCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html — target bất biến.
- Java SE 17, **`MutableCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html — `setTarget`, `syncAll`, propagation.
- Java SE 17, **`VolatileCallSite`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html — volatile semantics của target.
- Java Language Specification 17, **§17.4 Java Memory Model**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4 — concurrency, happens-before, synchronization.

**Kết luận:** `SwitchPoint` là **chốt hủy hiệu lực một chiều**, `MethodHandles.guardWithTest` là **rẽ nhánh theo boolean predicate**, còn `CallSite` là **nơi giữ target cho lời gọi động**. Chúng có thể kết hợp, nhưng phải giữ đúng `MethodType`, scope của giả định, ranh giới concurrency và cách tạo generation mới sau invalidation.