# 12.5. Phân biệt `getTarget` với `dynamicInvoker` khi target của `CallSite` có thể thay đổi

Trong `java.lang.invoke`, một `CallSite` lưu một `MethodHandle` gọi là **target**. Nếu call site là `MutableCallSite` hoặc `VolatileCallSite`, chương trình có thể dùng `setTarget(...)` để thay target khi đang chạy. Hai phương thức tưởng giống nhau lại phục vụ **hai nhu cầu khác nhau**:

- **`site.getTarget()`:** đọc và trả về **đối tượng MethodHandle hiện được quan sát**. Nếu giữ kết quả trong một biến, bạn giữ *tham chiếu tới handle ở thời điểm đọc*, không tạo một liên kết tự cập nhật.
- **`site.dynamicInvoker()`:** trả về một **MethodHandle dùng để dispatch qua chính CallSite**. Khi gọi handle này, nó ủy quyền đến target mà call site đang quan sát ở lần dispatch đó; nếu call site được relink và cập nhật được nhìn thấy, cùng một dynamic invoker có thể thực thi target mới.

**Điểm khác biệt quyết định:** `getTarget()` hữu ích để lấy snapshot của *liên kết target*; `dynamicInvoker()` hữu ích để giữ đường gọi **theo liên kết thay đổi được**. Không được nhầm một **MethodHandle đã được cache từ `getTarget()`** với một dynamic invoker đã được cache. Ngoài ra, “theo liên kết mới” không có nghĩa tất cả các luồng tự động thấy update ngay: quy tắc memory visibility phụ thuộc loại `CallSite` và cơ chế đồng bộ.

Bài này trình bày sự khác biệt trên Java 17+, giải thích `ConstantCallSite`, `MutableCallSite` và `VolatileCallSite`, liên hệ `invokedynamic`, xử lý type invariants, `syncAll`, cache/combinator, lỗi phổ biến và một chương trình hoàn chỉnh có output kiểm chứng.

## 1. Bản chất của `CallSite` và target

`CallSite` là holder cho một target `MethodHandle`. Khi một instruction `invokedynamic` của JVM được liên kết tới call site, việc dispatch sẽ dựa trên target thuộc liên kết ấy. Tuy nhiên, bạn cũng có thể tạo call site và gọi `dynamicInvoker()` **mà không phải tự viết một instruction `invokedynamic` trong bytecode** (*free-floating call site*).

Giả sử:

```java
MethodHandle a = MethodHandles.constant(String.class, "A");
MutableCallSite site = new MutableCallSite(a);
```

Target `a` có type `()String`: không nhận tham số và trả về `String`. Ở đây:

- `site` là một **CallSite**, không phải một giá trị `String`.
- `site.getTarget()` trả về một **MethodHandle**, chính là target `a` khi chưa có cập nhật.
- `site.dynamicInvoker()` cũng trả về một **MethodHandle**, nhưng là **đường gọi thông qua site**.
- Chỉ khi `(String) handle.invokeExact()` mới thực thi target và lấy chuỗi `"A"`.

Sơ đồ:

```text
T0: site.target = handle A
T1: site.setTarget(handle B)
T2: site.setTarget(handle C)

snapshot = site.getTarget() tại T0 ------> handle A (giữ mãi tham chiếu A)
live     = site.dynamicInvoker() tại T0 --> đọc liên kết từ site khi invoke
                                            tại T0: A
                                            tại T1: B nếu update đã được quan sát
                                            tại T2: C nếu update đã được quan sát
```

Đây là sự khác nhau giữa **giữ một implementation** và **giữ một điểm dispatch**. `setTarget(B)` thay **tham chiếu target trong CallSite**, không mutate đối tượng `MethodHandle A`, không viết lại biến local `snapshot`, cũng không tự cập nhật mọi pipeline từng dùng A.

### 1.1. `CallSite.type()` luôn cố định

Mọi call site có một `MethodType` vĩnh viễn, biểu diễn bằng `site.type()`. `setTarget(newTarget)` chỉ hợp lệ nếu `newTarget.type().equals(site.type())`; yêu cầu bao gồm **đúng số lượng tham số, đúng kiểu từng tham số, đúng kiểu trả về**. Ngay cả khi hai type *có thể* được chuyển đổi bằng adapter, `setTarget` không tự gọi `asType`.

```java
MethodHandle a = MethodHandles.constant(String.class, "A"); // ()String
MethodHandle b = MethodHandles.constant(String.class, "B"); // ()String
MethodHandle i = MethodHandles.constant(int.class, 42);    // ()int

MutableCallSite site = new MutableCallSite(a);
site.setTarget(b); // Hợp lệ: ()String bằng ()String
// site.setTarget(i); // WrongMethodTypeException: ()int khác ()String
```

`setTarget(i)` được comment để minh họa điều kiện lỗi. Chương trình độc lập dưới đây thực hiện lời gọi sai này trong một khối `try/catch` và in ngoại lệ. Một call site **có thể thay target mãi mãi nhưng không thể thay MethodType**. `site.dynamicInvoker().type()` cũng bằng `site.type()`.

## 2. Bảng so sánh API: snapshot handle hay liên kết động?

| Tiêu chí | `getTarget()` | `dynamicInvoker()` |
| --- | --- | --- |
| Trả về | `MethodHandle` được lưu làm target tại thời điểm đọc | `MethodHandle` dùng để gọi gián tiếp qua `CallSite` |
| Nếu lưu vào biến | Biến giữ đúng handle đã đọc | Biến giữ đường gọi gắn với site |
| Sau `setTarget(B)` | Handle **đã lấy trước đó** vẫn là A; gọi `getTarget()` lần **mới** có thể đọc B | Cùng invoker có thể gọi B khi update đã được quan sát |
| Kiểu của kết quả | `site.type()` | `site.type()` |
| Chi phí/hành vi | Gọi target đã chụp; không phải đọc lại site ở mỗi invoke | Mỗi lần dispatch phải có ngữ nghĩa lấy target qua site |
| Các luồng khác | Mỗi lần gọi `getTarget()` theo semantics subclass, có thể gặp giá trị cũ ở MutableCallSite | Tương tự: dynamic route theo semantics subclass, không tự biến Mutable thành volatile |
| `ConstantCallSite` | Luôn target cố định | Trả luôn target cố định |
| Tình huống dùng | Chẩn đoán, ghim implementation/phiên bản, audit | Relinking, đổi chiến lược, bộ định tuyến thay đổi được |

**“Snapshot” chỉ là snapshot của tham chiếu MethodHandle đang nằm trong site**, không phải bản sao bất biến của toàn bộ hành vi. Nếu MethodHandle A tự đọc biến mutable hay gọi `dynamicInvoker()` của một CallSite khác, kết quả của A vẫn có thể thay đổi. Không nên phát biểu “`getTarget()` làm mọi trạng thái bên trong target bất biến”.

### 2.1. Cache `getTarget()` giữ target cũ

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle snapshot = site.getTarget();
site.setTarget(MethodHandles.constant(String.class, "B"));

String oldResult = (String) snapshot.invokeExact();  // "A"
String newResult = (String) site.getTarget().invokeExact(); // "B" cùng luồng
```

`snapshot` không phải pointer có thể tự chuyển đích sang B. Đối với `MutableCallSite`, lần `site.getTarget()` mới có thể thấy B; khi cả `setTarget` và `getTarget` xảy ra trong cùng luồng như ví dụ, nó thấy B. Nhưng nếu một luồng **khác** đọc site, việc thấy target mới phụ thuộc synchronization.

### 2.2. Cache `dynamicInvoker()` giữ lối dispatch động

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle live = site.dynamicInvoker();
String before = (String) live.invokeExact(); // "A"

site.setTarget(MethodHandles.constant(String.class, "B"));
String after = (String) live.invokeExact(); // "B" trong luồng cập nhật
```

Không phải gọi lại `dynamicInvoker()` sau mỗi `setTarget`. Đây là khác biệt thực tế trong các hệ thống cập nhật target lúc runtime.

Javadoc mô tả dynamic invoker tương đương một chuỗi kết hợp `getTarget` của site với `MethodHandles.exactInvoker(site.type())`, qua `MethodHandles.foldArguments(...)`. Vì vậy, về **hành vi** nó đọc target theo trạng thái site ở lần dispatch, rồi thực thi target đó. Đó là cách biểu diễn của đặc tả, không buộc JVM phải thực hiện chính xác từng bước như một interpreter; JVM có thể tối ưu miễn giữ đúng contract.

**Không dựa vào object identity** của các kết quả `dynamicInvoker()` từ nhiều lần gọi ở các subclass khác nhau để xác nhận tính “động”. Điều quan trọng là **hành vi**, không phải có một object wrapper duy nhất hay nhiều object.

## 3. Tác động của ba subclass `CallSite`

### 3.1. `ConstantCallSite`: target vĩnh viễn

`ConstantCallSite` từ đầu đã **không cho phép relink**. `setTarget(...)` luôn ném `UnsupportedOperationException`. `getTarget()` trả target vĩnh viễn, còn `dynamicInvoker()` có thể và thực tế **trả chính target đó**, bởi không có trạng thái động nào cần đọc lại.

```java
MethodHandle target =
        MethodHandles.constant(String.class, "fixed");
ConstantCallSite site = new ConstantCallSite(target);

MethodHandle captured = site.getTarget();
MethodHandle dynamic = site.dynamicInvoker();

System.out.println(captured == dynamic); // true với ConstantCallSite
// site.setTarget(target); // UnsupportedOperationException
```

`captured == dynamic` là đúng theo contract của `ConstantCallSite`, nhưng **không được suy ra** rằng các lời gọi `getTarget()` và `dynamicInvoker()` nói chung luôn trả cùng object trên `MutableCallSite`/`VolatileCallSite`.

Nếu không bao giờ muốn thay implementation, `ConstantCallSite` là lựa chọn rõ nghĩa và tránh chi phí/quy tắc visibility của target mutable.

### 3.2. `MutableCallSite`: target như field thông thường

`MutableCallSite.setTarget(...)` được phép cập nhật, và `getTarget()` có semantics của **ordinary non-volatile field read**. Một luồng đọc khác **có thể không thấy update mới của luồng ghi**, và có thể giữ/cached target cũ trong thời gian không xác định nếu thiếu đồng bộ hóa. Dynamic invoker của mutable call site cũng chịu cùng loại semantics liên kết.

```java
MutableCallSite site = new MutableCallSite(
        MethodHandles.constant(String.class, "A"));
MethodHandle live = site.dynamicInvoker();

site.setTarget(MethodHandles.constant(String.class, "B"));
MutableCallSite.syncAll(new MutableCallSite[] {site});
```

`syncAll` là thao tác chuyên dụng để công bố cập nhật của **các MutableCallSite được nêu trong mảng** và ép các luồng đọc loại bỏ những target cũ đã cache. Điểm thiết yếu:

- Thực hiện `setTarget` cho đúng site **trước** `syncAll`.
- Các reader có thể đã thấy target mới ngay sau `setTarget`, **hoặc** vẫn thấy target cũ cho đến quá trình đồng bộ hóa.
- `syncAll` không quay lại chỉnh sửa những invocation đã **bắt đầu** trên target cũ.
- Nếu cập nhật nhiều site cùng lúc, `syncAll(new MutableCallSite[]{a,b})` **không** biến hai lần cập nhật thành transaction nguyên tử cho reader.
- Javadoc khuyến cáo phối hợp `setTarget` và `syncAll` dưới dạng **mutual exclusion** thích hợp giữa những writer, tránh các đợt cập nhật cạnh tranh.
- `syncAll` có thể đắt; có thể gom nhiều site trong một lần sync khi thuật toán cho phép.

Không phát biểu “`dynamicInvoker` luôn luôn gọi target mới nhất toàn cục” đối với MutableCallSite. Câu đúng hơn: nó **đi qua target mà call site quan sát tại lần gọi**, và visibility của `MutableCallSite` có thể trì hoãn việc quan sát update ở luồng khác.

### 3.3. `VolatileCallSite`: target có volatile semantics

`VolatileCallSite` cũng cho thay target, nhưng `setTarget` được định nghĩa như **volatile write**, còn `getTarget` là **volatile read**. Dynamic invoker theo đường liên kết này nên có khả năng nhìn thấy cập nhật theo semantics volatile mà không cần `MutableCallSite.syncAll`.

```java
VolatileCallSite site = new VolatileCallSite(
        MethodHandles.constant(String.class, "A"));

MethodHandle frozen = site.getTarget();
MethodHandle live = site.dynamicInvoker();
site.setTarget(MethodHandles.constant(String.class, "B"));

String a = (String) frozen.invokeExact(); // "A"
String b = (String) live.invokeExact();   // "B" với đọc sau ghi
```

Ở các luồng khác, đặc tả VolatileCallSite bảo đảm khả năng quan sát update tương ứng với **volatile read/write** của Java Memory Model. Điều đó không đồng nghĩa một invocation **đang chạy dở** trên A sẽ đột ngột bị chuyển sang B. Tính đúng đắn của ứng dụng vẫn phải xử lý các lời gọi đã vào implementation cũ.

### 3.4. Quy tắc chọn subclass

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Không đổi target trong lifetime | `ConstantCallSite` |
| Đổi target ít lần, có cơ chế publish theo đợt và chấp nhận chi phí `syncAll` | `MutableCallSite` |
| Đổi target cần được các reader ở luồng khác nhìn thấy theo semantics volatile | `VolatileCallSite` |
| Cần thay nhiều handler một cách nguyên tử ở cấp hệ thống | Một snapshot/routing policy có đồng bộ riêng; chỉ gọi `syncAll` không đủ |

Không có loại nào đảm bảo tự động ngắt một lời gọi target cũ đã bắt đầu. Cần thêm quiescence/epoch/versioning hoặc khóa nếu bài toán yêu cầu không còn request nào xử lý với implementation cũ sau một mốc cụ thể.

## 4. Bẫy khi xây chuỗi `MethodHandle`

Một method-handle pipeline có thể tạo từ target trực tiếp hoặc từ dynamic invoker:

```java
MethodHandle frozen = site.getTarget();
MethodHandle live = site.dynamicInvoker();

MethodHandle frozenFilter =
        MethodHandles.filterReturnValue(frozen, appendMark);
MethodHandle liveFilter =
        MethodHandles.filterReturnValue(live, appendMark);
```

Ở đây giả sử `site.type() == ()String` và `appendMark.type() == (String)String`; `appendMark` nối dấu `!`, các biến đã được khai báo ở ngữ cảnh thích hợp. Sau khi site từ A sang B:

- `frozenFilter`: vẫn gọi A rồi thêm dấu → `"A!"`.
- `liveFilter`: gọi qua site, nên khi B đã được quan sát thì trả `"B!"`.

`MethodHandles.filterReturnValue(...)` **không tự biết** rằng `frozen` từng xuất phát từ `CallSite.getTarget()`. Nó nối đúng object handle đã truyền vào. Nếu cần pipeline tự thích ứng với relink, **đưa dynamic invoker vào pipeline ngay từ đầu** hoặc phải chủ động xây lại pipeline khi target thay đổi.

## 5. Ví dụ Java 17+ hoàn chỉnh, biên dịch và chạy được

Ví dụ sử dụng target kiểu `()String` để làm rõ output. Những lần thay target ở `MutableCallSite` được thực hiện trong **cùng thread** và gọi `syncAll` để minh họa phương thức công bố chính thức; chương trình không dùng concurrency timing để suy ra visibility.

File **`CallSiteTargetDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;

public class CallSiteTargetDemo {
    static String call(MethodHandle handle) throws Throwable {
        return (String) handle.invokeExact();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle a = MethodHandles.constant(String.class, "A");
        MethodHandle b = MethodHandles.constant(String.class, "B");
        MethodHandle c = MethodHandles.constant(String.class, "C");

        MutableCallSite mutable = new MutableCallSite(a);
        MethodHandle snapshot = mutable.getTarget();
        MethodHandle live = mutable.dynamicInvoker();

        System.out.println("mutable.type=" + mutable.type());
        System.out.println("before.snapshot=" + call(snapshot));
        System.out.println("before.live=" + call(live));

        MethodHandle concat = MethodHandles.lookup().findVirtual(
                String.class, "concat", MethodType.methodType(
                        String.class, String.class));
        MethodHandle appendMark =
                MethodHandles.insertArguments(concat, 1, "!");
        MethodHandle frozenFilter =
                MethodHandles.filterReturnValue(snapshot, appendMark);
        MethodHandle liveFilter =
                MethodHandles.filterReturnValue(live, appendMark);

        mutable.setTarget(b);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("after.snapshot=" + call(snapshot));
        System.out.println("after.fresh=" + call(mutable.getTarget()));
        System.out.println("after.live=" + call(live));
        System.out.println("after.frozenFilter=" + call(frozenFilter));
        System.out.println("after.liveFilter=" + call(liveFilter));

        mutable.setTarget(c);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("later.snapshot=" + call(snapshot));
        System.out.println("later.live=" + call(live));
        System.out.println("later.liveFilter=" + call(liveFilter));

        VolatileCallSite volatileSite = new VolatileCallSite(a);
        MethodHandle volatileSnapshot = volatileSite.getTarget();
        MethodHandle volatileLive = volatileSite.dynamicInvoker();
        System.out.println("volatile.before=" + call(volatileLive));
        volatileSite.setTarget(b);
        System.out.println("volatile.snapshot=" + call(volatileSnapshot));
        System.out.println("volatile.live=" + call(volatileLive));

        CallSite constant = new ConstantCallSite(a);
        System.out.println("constant.snapshot="
                + call(constant.getTarget()));
        System.out.println("constant.dynamic="
                + call(constant.dynamicInvoker()));
        System.out.println("constant.same="
                + (constant.getTarget() == constant.dynamicInvoker()));
        try {
            constant.setTarget(b);
        } catch (UnsupportedOperationException e) {
            System.out.println("constant.write="
                    + e.getClass().getSimpleName());
        }

        try {
            mutable.setTarget(MethodHandles.constant(int.class, 1));
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongType="
                    + e.getClass().getSimpleName());
        }
        try {
            mutable.setTarget(null);
        } catch (NullPointerException e) {
            System.out.println("nullTarget="
                    + e.getClass().getSimpleName());
        }

        MutableCallSite blank = new MutableCallSite(
                MethodType.methodType(String.class));
        MethodHandle blankLive = blank.dynamicInvoker();
        System.out.println("blank.type=" + blank.type());
        try {
            call(blankLive);
        } catch (IllegalStateException e) {
            System.out.println("blank.before="
                    + e.getClass().getSimpleName());
        }
        blank.setTarget(MethodHandles.constant(String.class, "D"));
        System.out.println("blank.after=" + call(blankLive));
    }
}
```

Chạy ở thư mục chứa file bằng JDK 17:

```bash
javac --release 17 CallSiteTargetDemo.java
java CallSiteTargetDemo
```

`stdout` **chính xác**:

```text
mutable.type=()String
before.snapshot=A
before.live=A
after.snapshot=A
after.fresh=B
after.live=B
after.frozenFilter=A!
after.liveFilter=B!
later.snapshot=A
later.live=C
later.liveFilter=C!
volatile.before=A
volatile.snapshot=A
volatile.live=B
constant.snapshot=A
constant.dynamic=A
constant.same=true
constant.write=UnsupportedOperationException
wrongType=WrongMethodTypeException
nullTarget=NullPointerException
blank.type=()String
blank.before=IllegalStateException
blank.after=D
```

### 5.1. Giải thích output

1. **`mutable.type=()String`:** `CallSite` có type cố định, không đổi khi chuyển target A → B → C.
2. **`before.snapshot=A` / `before.live=A`:** trước relink, cả hai đi đến A.
3. **`after.snapshot=A` / `after.fresh=B`:** snapshot cũ giữ A; gọi `getTarget()` lần **mới** trong cùng thread nhận B.
4. **`after.live=B`:** cùng biến `live` đã tạo trước khi relink vẫn gọi B, không cần tạo lại `dynamicInvoker()`.
5. **`after.frozenFilter=A!` / `after.liveFilter=B!`:** pipeline dùng snapshot khác pipeline dùng dynamic invoker. Sau khi đổi tiếp tới C, `later.snapshot=A` và `later.liveFilter=C!` tiếp tục xác nhận khác biệt.
6. **`volatile.snapshot=A` / `volatile.live=B`:** cùng quy tắc snapshot vs dynamic route ở `VolatileCallSite`; bổ sung semantics volatile giữa các thread.
7. **`constant.same=true`:** với `ConstantCallSite`, `getTarget` và `dynamicInvoker` cùng trả permanent target. `setTarget` bị từ chối.
8. **`wrongType`:** `MutableCallSite` không nhận handle `()int` khi `type()==()String`.
9. **`nullTarget`:** `setTarget(null)` bị chặn; CallSite cần một target không null.
10. **`blank.before` / `blank.after`:** constructor nhận `MethodType` cài một target ban đầu có đúng type nhưng **ném IllegalStateException khi gọi**. Sau `setTarget(D)`, **cùng** `blankLive` chạy được và trả D.

**Giới hạn của minh họa:** code chạy tuần tự, nên không phải stress test đảm bảo visibility giữa nhiều luồng. Mọi tuyên bố về `syncAll` và volatile semantics nên dựa trên API specification, không phải một lần in đúng output.

## 6. Đừng nhầm `getTarget()` một lần với đọc lại mỗi lần

Ba cách viết khác nhau (pseudocode; thay `...` bằng danh sách đối số và kiểu thật):

```java
// A: Đọc target một lần rồi giữ lâu.
MethodHandle cached = site.getTarget();
for (...) {
    cached.invokeExact(...);
}

// B: Đọc lại target của site ở mỗi lần gọi.
for (...) {
    site.getTarget().invokeExact(...);
}

// C: Lấy dynamic invoker một lần; dispatch qua site mỗi khi gọi.
MethodHandle live = site.dynamicInvoker();
for (...) {
    live.invokeExact(...);
}
```

- **A** không thấy relink qua chính site đó; nếu handle A chứa logic mutable bên trong thì kết quả vẫn có thể thay đổi vì **state khác**, không phải vì site được relink.
- **B** có thể thấy relink mới trong các lần đọc `getTarget`, nhưng với `MutableCallSite` và nhiều luồng, một lần đọc **không được bảo đảm** sẽ thấy target mới nhất nếu thiếu synchronization.
- **C** giữ đường gọi động và code ứng dụng không phải tự đọc target trong vòng lặp. Nhưng với `MutableCallSite`, visibility của từng lần dispatch vẫn theo ordinary-field semantics.

Cách B và C không nhất thiết tương đương về chi phí hoặc tối ưu; quy tắc ý nghĩa là cả hai đọc target theo CallSite tại lần gọi, khác cách A đã giữ một MethodHandle cụ thể.

Với `ConstantCallSite`, A và C khác nhau về ý định code nhưng không có sự khác biệt observable về relinking, vì không thể thay target.

## 7. Tính bất biến của MethodType và adapter

`setTarget` không tự thích ứng kiểu; kiểu đích phải bằng `site.type()`. Ví dụ:

```java
MethodHandle oldTarget =
        MethodHandles.constant(String.class, "A"); // ()String
MutableCallSite site = new MutableCallSite(oldTarget);

MethodHandle wrong =
        MethodHandles.constant(Object.class, "B"); // ()Object

// site.setTarget(wrong); // WrongMethodTypeException

MethodHandle adapted = wrong.asType(site.type()); // ()String
site.setTarget(adapted);                         // Hợp lệ
```

Đoạn trên là minh họa, có thể đặt trong phương thức xử lý ngoại lệ theo dự án. `asType` chỉ hoạt động khi conversion có thể thực hiện; nó **không** cấp quyền đổi số lượng tham số, tạo ra conversion tùy ý hoặc bỏ qua việc target trả giá trị không tương thích.

Ví dụ target mới cần nhận `int`:

```java
MethodType signature =
        MethodType.methodType(String.class, int.class); // (int)String
MutableCallSite site = new MutableCallSite(signature);

// Muốn thay bằng một constant ()String, phải bổ sung tham số int bị bỏ qua:
MethodHandle constant =
        MethodHandles.constant(String.class, "ok");
MethodHandle acceptsInt =
        MethodHandles.dropArguments(constant, 0, int.class);

site.setTarget(acceptsInt); // (int)String, hợp lệ
```

`site.dynamicInvoker()` cũng có kiểu `(int)String`. Khi gọi `invokeExact`, caller phải truyền `int` và yêu cầu return `String` tại call site; nếu sai descriptor, `WrongMethodTypeException` đến từ **lời gọi MethodHandle**, không nhất thiết từ `setTarget`. Có hai nguồn lỗi type khác nhau phải chẩn đoán đúng.

## 8. Các luồng khác và `syncAll`: đừng suy từ test đơn luồng

Hãy hình dung:

```text
Updater                              Reader
-------                              -------------------------
site.setTarget(B)                    savedLive.invokeExact()
MutableCallSite.syncAll([site])      savedLive.invokeExact()
                                     savedLive.invokeExact()
```

Đây là sơ đồ logic, không phải mã Java chạy được. Trước khi `syncAll` có tác dụng, reader **có thể thấy B sớm** hoặc vẫn thấy A. Khi synchronization hoàn tất, các reader tương lai phải chấp nhận trạng thái target mới theo contract của `syncAll`, nhưng các invocation đã bắt đầu với A không bị đảo ngược. Nếu writer khác relink thêm C ngay lúc đó thì cần xét riêng race.

**Phân biệt hai nhu cầu:**

- **Muốn các luồng nhìn thấy target mới sau mỗi cập nhật:** `VolatileCallSite` là lựa chọn trực tiếp về volatile semantics.
- **Muốn cập nhật ít lần, theo đợt:** `MutableCallSite` + `syncAll`, với kỷ luật writer và chi phí đồng bộ hóa phù hợp, có thể tốt hơn cho mô hình relink không thường xuyên.

Ngay cả `VolatileCallSite` cũng không cho promise kiểu “sau đúng 5 ms mọi tác vụ cũ đã hoàn thành”. Memory visibility và scheduling/lifetime của request là hai vấn đề khác nhau.

Nếu cần cập nhật **nhiều CallSite cùng lúc như một giao dịch**, `MutableCallSite.syncAll(new MutableCallSite[]{a,b})` không cung cấp atomic snapshot của toàn bộ nhóm cho reader. Một giải pháp có thể là công bố **một** target trỏ đến immutable routing snapshot gồm toàn bộ các chiến lược, hoặc dùng lock/epoch/version quản lý nhóm.

## 9. Mối liên hệ với `invokedynamic` và bootstrap

Một điểm gọi `invokedynamic` trong bytecode cần bootstrap method để xác định liên kết. Bootstrap method có thể trả về `CallSite`; các lời gọi tới điểm động sau đó dispatch tới target theo call site đã liên kết.

`site.dynamicInvoker()` cung cấp một `MethodHandle` có hành vi như lời gọi `invokedynamic` **đã liên kết tới site ấy**, kể cả khi đối tượng site được tạo trong Java source chỉ để dùng độc lập.

Không nhầm:

- **`CallSite`:** nơi chứa trạng thái liên kết.
- **`getTarget()`:** đọc MethodHandle đang làm target.
- **`dynamicInvoker()`:** tạo/lấy MethodHandle gọi qua liên kết.
- **`MethodHandle.invokeExact()`:** thực thi một MethodHandle với descriptor tại vị trí gọi; không phải một thao tác để lấy liên kết.

```java
MethodHandle live = site.dynamicInvoker();
String answer = (String) live.invokeExact(); // khi site.type() là ()String
```

`(String)` cast gần `invokeExact` xác định return type của call site là `String`; với kiểu khác phải chọn đối số và cast đúng `MethodType`. Sửa `setTarget` không thể cứu một caller có descriptor `invokeExact` sai.

## 10. Call site khởi tạo bằng `MethodType` nhưng chưa có target hữu ích

Không phải lúc nào constructor cũng nhận một MethodHandle đã sẵn sàng:

```java
MutableCallSite site = new MutableCallSite(
        MethodType.methodType(String.class));
MethodHandle live = site.dynamicInvoker();
```

Call site này có kiểu `()String` và **target không null**. Target mặc định là một **throwing MethodHandle** có type phù hợp; nếu gọi ngay, nó ném `IllegalStateException`. Điều này khác với `site.setTarget(null)` vốn ném `NullPointerException`.

```java
// Đoạn minh họa trong phương thức throws Throwable.
try {
    String value = (String) live.invokeExact();
} catch (IllegalStateException e) {
    // Chưa cài target thực thi hữu ích.
}

site.setTarget(MethodHandles.constant(String.class, "ready"));
String value = (String) live.invokeExact(); // "ready"
```

`live` không cần tạo lại. Với call site được liên kết bởi một bootstrap method, thông thường cần cài target hợp lệ trước khi expose nơi gọi để tránh trạng thái tạm thời này.

## 11. Bảng lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Cache handle rồi target đổi nhưng kết quả vẫn cũ | Đã cache `site.getTarget()` | Nếu cần theo relink, cache `site.dynamicInvoker()` |
| Gọi `getTarget()` nhiều lần ở thread khác vẫn thấy cũ | `MutableCallSite` có semantics của ordinary field | Dùng `syncAll`/đồng bộ phù hợp hoặc `VolatileCallSite` |
| `live.invokeExact()` ném `WrongMethodTypeException` | Descriptor tại caller khác `live.type()` | Kiểm tra loại tham số và **return type**, cast `invokeExact` đúng |
| `setTarget` ném `WrongMethodTypeException` | `newTarget.type()` khác `site.type()` | Adapt bằng `asType`/combinator hợp lệ trước khi set |
| `setTarget(null)` ném `NullPointerException` | Target không thể là null | Dùng throwing target rõ nghĩa nếu chưa sẵn sàng |
| `ConstantCallSite.setTarget(...)` ném `UnsupportedOperationException` | Target của constant là vĩnh viễn | Dùng Mutable/Volatile nếu cần relink |
| Call site mới bằng `MethodType` ném `IllegalStateException` khi invoke | Target mặc định là throwing handle | Cài target hợp lệ trước khi gọi |
| Pipeline `filterReturnValue` vẫn thực thi A | Pipeline xây từ snapshot `getTarget()` | Xây pipeline từ dynamic invoker hoặc xây lại khi update |
| Sau `syncAll` vẫn thấy request đang xử lý A | Request đã lấy hoặc đã bắt đầu target A | Dùng quiescence/epoch/lock nếu cần chặn request cũ |
| Thay nhiều site rồi `syncAll` nhưng thấy trạng thái pha trộn | `syncAll` không phải multi-site transaction | Thiết kế snapshot/version cấp nhóm |

**Debug nhanh**, trong ngữ cảnh đã có `site` và `newTarget`:

```java
System.out.println("site.type: " + site.type());
System.out.println("current.type: " + site.getTarget().type());
System.out.println("new.type: " + newTarget.type());
System.out.println("invoker.type: " + site.dynamicInvoker().type());
```

Đoạn này giúp tìm **type mismatch**. Không suy rằng những lời gọi `println` tự giải quyết visibility trên mọi đường đi đa luồng khác.

## 12. Khi nào cố ý dùng snapshot, khi nào giữ dynamic invoker?

**Ghim một phiên bản cho toàn bộ request.** Nếu request phải dùng đúng implementation đã được chọn lúc bắt đầu, việc lấy `MethodHandle requestTarget = site.getTarget()` một lần có thể là yêu cầu nghiệp vụ chính đáng. Sau đó request sẽ chạy cùng handle. Nhưng nếu handle ấy tự đọc state mutable thì “cùng handle” chưa đồng nghĩa “cùng toàn bộ dữ liệu”.

**Đổi chiến lược cho các request về sau.** Khi ứng dụng muốn hot-swap thuật toán hoặc cập nhật dispatch table động, cache `dynamicInvoker()` là cách tự nhiên. Producer thay target và công bố cập nhật phù hợp với `MutableCallSite`/`VolatileCallSite`; caller không phải tự lắp lại mọi pipeline.

**Bảo đảm nhất quán phiên bản trên nhiều target.** Nếu các target A/B/C tạo nên một configuration set, hãy cân nhắc công bố một immutable snapshot bằng một target duy nhất thay vì cập nhật nhiều site rời rạc mà không có version transaction.

Các vấn đề *tính đúng đắn* cần đặt trước dự đoán *tốc độ*: một pipeline snapshot có thể chạy nhanh trong vài benchmark, nhưng nếu yêu cầu phải theo update thì nó sai về chức năng; một dynamic pipeline dù cập nhật đúng vẫn cần synchronization thích hợp.

## 13. Bài tập kiểm tra hiểu biết

Giả sử các lời gọi sau xảy ra theo thứ tự **trong cùng thread**:

```java
MethodHandle a = MethodHandles.constant(String.class, "A");
MethodHandle b = MethodHandles.constant(String.class, "B");

MutableCallSite site = new MutableCallSite(a);
MethodHandle x = site.getTarget();
MethodHandle y = site.dynamicInvoker();

site.setTarget(b);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

**A.** `(String) x.invokeExact()` trả gì? `(String) y.invokeExact()` trả gì?

**B.** Nếu sau `setTarget(b)` gọi `MethodHandle z = site.getTarget()`, `z` có giống `x` về kết quả không? `y` có cần khởi tạo lại không?

**C.** Nếu xây `filterReturnValue(x, appendMark)` và `filterReturnValue(y, appendMark)`, sau khi relink tiếp tới C hai pipeline sẽ khác thế nào?

**D.** Luồng 1 gọi `setTarget(B)`, luồng 2 gọi `y.invokeExact()` liên tục nhưng không có synchronization. Được phép khẳng định luồng 2 sẽ sớm thấy B không?

**E.** `VolatileCallSite` giúp giải quyết điều gì trong D? Nó có dừng các invocation A đã chạy không?

**F.** Có thể thay handle `()String` bằng `()int` qua `site.setTarget(...)` không? Nếu muốn thay `()Object` bằng `()String`, cần làm gì trước?

**G.** Với `ConstantCallSite`, `getTarget()` và `dynamicInvoker()` có thể trả cùng object không? `setTarget` có được phép không?

**H.** `new MutableCallSite(MethodType.methodType(String.class))` có target null không? Nếu gọi trước khi `setTarget`, lỗi nào xuất hiện?

**Đáp án:**

- **A:** `x` trả `"A"` vì chụp handle cũ; `y` trả `"B"` vì đi qua CallSite và update đã được quan sát.
- **B:** `z` trỏ target B, còn `x` giữ A; `y` vẫn dùng được, không cần tạo lại.
- **C:** Pipeline từ `x` tiếp tục gọi A; pipeline từ `y` theo target C mới khi liên kết được quan sát.
- **D:** Không. `MutableCallSite` đọc target như field thông thường, nên luồng khác có thể giữ target cũ nếu không đồng bộ hóa.
- **E:** Volatile target có semantics như volatile variable, cung cấp visibility mạnh hơn; không hồi tố đổi lời gọi A đã bắt đầu.
- **F:** Không, `()int` khác `()String` và `setTarget` ném `WrongMethodTypeException`. Với `()Object`, dùng `asType(site.type())` nếu conversion hợp lệ rồi mới set.
- **G:** Có; `ConstantCallSite` thực sự trả permanent target cho cả hai. `setTarget` ném `UnsupportedOperationException`.
- **H:** Không; target mặc định là throwing MethodHandle có type đúng, nên invocation ban đầu ném `IllegalStateException`.

## 14. Nguồn tra cứu chính thức

- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): target, `getTarget`, `dynamicInvoker`, `MethodType` bất biến.
- [Java SE 17 — `MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): memory semantics ordinary-field, `syncAll`, giá trị target cache ở nhiều luồng.
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target với volatile semantics và dynamic invoker.
- [Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): target permanent và không hỗ trợ `setTarget`.
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `asType` và quy tắc chữ ký.
- [Java Language Specification SE 17 — `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): memory visibility và happens-before.

**Ghi nhớ:** `getTarget()` đọc ra một MethodHandle hiện tại; khi cache kết quả, bạn **giữ target đó**. `dynamicInvoker()` là một MethodHandle gọi **qua CallSite**, có thể giữ lâu và vẫn theo relink. Với nhiều luồng, phải đồng bộ đúng: `MutableCallSite` có thể cần `syncAll`, còn `VolatileCallSite` cung cấp volatile semantics. Target đổi được nhưng **`CallSite.type()` không đổi**.
