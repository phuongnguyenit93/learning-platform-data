# 12.3 MutableCallSite, setTarget và khả năng quan sát thay đổi giữa các luồng

## 1. Vấn đề: thay một lời gọi đã liên kết ngay trong lúc chương trình chạy

Trong hệ thống liên kết động, đôi khi cùng một vị trí gọi cần **thay đổi implementation** mà không thay đổi chữ ký. Ví dụ: một runtime chuyển handler phiên bản A sang phiên bản B; một DSL đổi phép xử lý theo cấu hình; hoặc một bộ dispatch phát hiện một kiểu dữ liệu mới và cần relink lời gọi.

Java hỗ trợ việc đó bằng `java.lang.invoke.CallSite`, đối tượng giữ một `MethodHandle` hiện hành gọi là **target**. Với `MutableCallSite`, target có thể đổi qua `setTarget(...)`. Một lời gọi `invokedynamic` đã liên kết tới site hoặc `site.dynamicInvoker()` sẽ dispatch đến target được site dùng tại thời điểm gọi.

Vấn đề khó không nằm ở lệnh thay target, mà ở **Java Memory Model (JMM)**: việc một luồng ghi target mới không tự buộc những luồng khác đang chạy phải nhìn thấy ngay thay đổi ấy. Đây là mục tiêu chính của bài học.

### Sau bài này, bạn sẽ

- Tạo `MutableCallSite` với target ban đầu hoặc một `MethodType` chưa có target hữu dụng.
- Phân biệt `getTarget()`, `setTarget(...)` và `dynamicInvoker()`.
- Thay target hợp lệ, giữ kiểu của call site không đổi, phân tích `WrongMethodTypeException`.
- Giải thích đúng ngữ nghĩa liên luồng của `setTarget`, `getTarget` và `MutableCallSite.syncAll(...)`.
- Phân biệt bảo đảm quan sát từ `MutableCallSite` với `VolatileCallSite` và `ConstantCallSite`.
- Thiết kế relinking có quản lý race, overhead, consistency và kiểm thử concurrency mà không suy luận sai từ một kết quả chạy tình cờ.

## 2. Bản đồ CallSite và các thành phần quan trọng

Một `CallSite` có **kiểu bất biến** `MethodType`. Dù target đổi, mọi target mới phải có **chính xác cùng kiểu** với target cũ. Ba loại call site chính:

| Loại | Target thay đổi được? | Ngữ nghĩa quan sát từ các luồng | Khi phù hợp |
| --- | --- | --- | --- |
| `ConstantCallSite` | Không | Liên kết cố định sau khi tạo; không có thay target. | Đích lời gọi không đổi suốt vòng đời site. |
| `MutableCallSite` | Có | Target hoạt động như **ordinary field** (không phải volatile). Chỉ `setTarget` không bảo đảm luồng khác nhanh chóng thấy đích mới. | Relink ít lần/batch; có thể dùng `syncAll` để công bố target. |
| `VolatileCallSite` | Có | Target hoạt động như **volatile field**; các lần đọc phải tuân theo bảo đảm volatile của JMM. | Target thay đổi thường xuyên hoặc cần quan sát liên luồng với volatile semantics. |

Các thành phần nên tách riêng:

- **`site.type()`:** kiểu bất biến của site, ví dụ `(int)String`.
- **`site.getTarget()`:** nhận một **MethodHandle là target mà caller đang quan sát**. Đây không phải một “live wrapper” tự thay thế giá trị tham chiếu đã nhận trong biến Java.
- **`site.setTarget(newTarget)`:** thay target đang lưu. Kiểu `newTarget.type()` phải bằng `site.type()`.
- **`site.dynamicInvoker()`:** tạo một MethodHandle dùng để đi qua **site**, nhận thay đổi target sau này theo memory semantics của loại call site.
- **`MutableCallSite.syncAll(sites)`:** thao tác đồng bộ hóa cho một **mảng các mutable call site**, để các luồng khác không tiếp tục dùng bản target đã cache quá cũ theo hợp đồng của API.

### 2.1. Khác biệt giữa liên kết động và lời gọi method bình thường

`dynamicInvoker()` tạo một MethodHandle có cùng hành vi liên kết như một lệnh `invokedynamic` đã liên kết đến site. Trong một chương trình Java thuần, ta có thể minh họa relink bằng cách gọi `dynamicInvoker().invokeExact(...)` mà không cần tự sinh bytecode `invokedynamic`.

Điều đó **không có nghĩa** mọi lời gọi Java bình thường đều đi qua call site. Lời gọi `obj.method()` trong code Java không tự dùng `MutableCallSite` của bạn. Framework, compiler hoặc runtime phải **chủ động** liên kết vị trí gọi đến site hoặc dùng dynamic invoker do site cung cấp.

### 2.2. Luồng dữ liệu khái niệm

```text
Caller / invokedynamic
          |
          v
  dynamicInvoker()
          |
          v
  MutableCallSite ─────> target = MethodHandle V1
          |             ^
          |             |
          └─ setTarget(MethodHandle V2)
                        |
                        v
                 target = V2

Luồng ghi: setTarget(V2) -> [syncAll khi cần công bố]
Luồng đọc: có thể còn thấy V1 trước khi bảo đảm đồng bộ được áp dụng
```

Đây là sơ đồ **ngữ nghĩa**, không phải bản mô tả cứng về cách JIT sinh lệnh máy. JVM có thể tối ưu, inline hoặc cache theo những cách tuân thủ JMM.

## 3. Tạo MutableCallSite: target có sẵn hoặc kiểu chưa khởi tạo

Có hai constructor:

```java
// Đoạn minh họa: target là MethodHandle có type (int)String.
MutableCallSite ready = new MutableCallSite(target);

// Chỉ có type, chưa gắn implementation hữu dụng.
MutableCallSite blank = new MutableCallSite(
        MethodType.methodType(String.class, int.class));
```

Đây là trích đoạn trong code đã import `java.lang.invoke.MethodHandle`, `MethodType`, `MutableCallSite` và có một biến `target` tương ứng. Phân biệt rõ:

- `new MutableCallSite(target)` lấy luôn `target.type()` làm kiểu bất biến.
- `new MutableCallSite(type)` đặt kiểu site là `type` và gắn một **target đặc biệt ban đầu sẽ ném `IllegalStateException` nếu bị gọi**. Nó không tự trả `null` hoặc giá trị mặc định.
- `type == null` hoặc `target == null` làm constructor tương ứng ném `NullPointerException`.
- Trước khi đưa một blank site vào đường gọi thực tế, thông thường nên `setTarget(...)` sang một handle hữu dụng đúng kiểu.

Call site không phải mảng có thể đổi type tùy ý: một lần tạo `(int)String`, nó vẫn là `(int)String` cho đến hết vòng đời. Nếu cần đổi chữ ký, phải thiết kế call site hoặc adapter phù hợp; không được dùng `setTarget` để lén đổi số tham số.

## 4. `setTarget`: thay liên kết nhưng không đổi chữ ký

Ví dụ site `(int)String` đang trỏ tới:

```java
static String versionOne(int x) { return "ONE:" + x; }
static String versionTwo(int x) { return "TWO:" + x; }
```

Các đoạn method trên là **minh họa** trong một lớp. Khi hai `MethodHandle` trỏ đến hai method có **cùng** `MethodType.methodType(String.class, int.class)`, chúng có thể thay phiên là target của cùng site.

Tính bất biến của type được kiểm tra **tại `setTarget`**:

- `newTarget == null` -> `NullPointerException`.
- `newTarget.type()` không bằng `site.type()` -> `WrongMethodTypeException`.
- Target cùng type -> được gắn vào site; **không có chuyển đổi kiểu tự động** chỉ vì `invoke` có thể adapt kiểu ở call site.

Ví dụ `MethodHandles.constant(String.class, "hi")` có kiểu `()String`, không cùng `(int)String` nên không thể thay trực tiếp vào site `(int)String`. Muốn nhận thêm tham số int nhưng bỏ qua, cần tạo adapter:

```java
MethodHandle zeroArg = MethodHandles.constant(String.class, "hi");
MethodHandle compatible = MethodHandles.dropArguments(
        zeroArg, 0, int.class);
// compatible.type() == (int)String
site.setTarget(compatible);
```

Đoạn này là trích đoạn, giả định `site` có type `(int)String`. Việc chuẩn hóa type bằng `asType` hoặc combinator khác phải có **chủ đích** và phải phù hợp semantics nghiệp vụ.

## 5. `dynamicInvoker()` khác việc cất `getTarget()` ở một biến

Hai cách dưới đây **không tương đương sau khi site bị relink**:

```java
MethodHandle followsSite = site.dynamicInvoker();
MethodHandle savedTarget = site.getTarget();
```

- `followsSite` là **cầu nối qua call site**. Về mặt API, khi gọi, nó dispatch đến current target mà luồng gọi được phép quan sát.
- `savedTarget` là **chính MethodHandle tại lần `getTarget()` đó**. Nếu code giữ biến `savedTarget` rồi gọi lại sau khi relink, biến này không tự đổi thành target mới.
- Nếu sau này bạn gọi `site.getTarget()` lại, kết quả đọc mới vẫn chịu memory semantics ordinary-field của `MutableCallSite`; còn trên **cùng luồng**, sau `setTarget`, target vừa ghi được dùng theo quy tắc chương trình.

Đây là khác biệt quan trọng giữa **dynamic binding** và **snapshot của tham chiếu handle**. Nếu muốn caller theo dõi việc relink, nó phải dùng `dynamicInvoker` hoặc một `invokedynamic` đã liên kết tới site; đừng giữ mãi một `getTarget()` cũ và mong nó được tự động cập nhật.

### 5.1. Ví dụ Java 17 đầy đủ: relink, lỗi type và blank site

Tạo file **`MutableCallSiteBasicsDemo.java`**:

```java
import java.lang.invoke.*;

public class MutableCallSiteBasicsDemo {
    private static String one(int x) {
        return "ONE:" + x;
    }

    private static String two(int x) {
        return "TWO:" + x;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type =
                MethodType.methodType(String.class, int.class);

        MethodHandle first = lookup.findStatic(
                MutableCallSiteBasicsDemo.class, "one", type);
        MethodHandle second = lookup.findStatic(
                MutableCallSiteBasicsDemo.class, "two", type);

        MutableCallSite site = new MutableCallSite(first);
        MethodHandle dynamic = site.dynamicInvoker();
        MethodHandle snapshot = site.getTarget();

        System.out.println("site type: " + site.type());
        System.out.println("before: "
                + (String) dynamic.invokeExact(3));

        site.setTarget(second);
        System.out.println("after same thread: "
                + (String) dynamic.invokeExact(3));
        System.out.println("saved handle: "
                + (String) snapshot.invokeExact(3));

        try {
            site.setTarget(
                    MethodHandles.constant(String.class, "bad"));
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong target type: rejected");
        }
        System.out.println("still target two: "
                + (String) dynamic.invokeExact(3));

        MutableCallSite blank = new MutableCallSite(type);
        MethodHandle blankInvoker = blank.dynamicInvoker();

        try {
            String ignored = (String) blankInvoker.invokeExact(1);
            System.out.println("unexpected: " + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("blank initial target: uninitialized");
        }

        blank.setTarget(first);
        System.out.println("initialized blank: "
                + (String) blankInvoker.invokeExact(1));
    }
}
```

Lệnh biên dịch và chạy (JDK 17+):

```bash
javac -encoding UTF-8 --release 17 MutableCallSiteBasicsDemo.java
java MutableCallSiteBasicsDemo
```

Stdout chính xác:

```text
site type: (int)String
before: ONE:3
after same thread: TWO:3
saved handle: ONE:3
wrong target type: rejected
still target two: TWO:3
blank initial target: uninitialized
initialized blank: ONE:1
```

**Giải thích:**

1. `type()` của site là `(int)String`; cả hai method có cùng type nên được phép thay thế nhau.
2. Trên **cùng luồng**, sau `setTarget(second)`, dynamic invoker gọi `two` và trả `TWO:3`. Điều này **chưa chứng minh** luồng khác chắc chắn thấy phiên bản hai.
3. Biến `snapshot` giữ target cũ `one`, vì thế trả `ONE:3`; nó không đi qua site nữa.
4. Hằng số `()String` không hợp kiểu `(int)String`, nên `setTarget` ném `WrongMethodTypeException`. Target hợp lệ cuối vẫn là `two`.
5. Blank site với `MethodType` có target đặc biệt ném `IllegalStateException`. Sau khi set đúng `first`, dynamic invoker đã lấy từ trước cũng hoạt động: `ONE:1`.

**Lưu ý:** `invokeExact` có kiểm tra chữ ký tại call site. Ví dụ nhận `String` bằng `(String) dynamic.invokeExact(3)`, không phải `Object` hoặc bỏ luôn kết quả.

## 6. Vấn đề liên luồng: `setTarget` không phải volatile write

Theo Javadoc Java SE 17, trường target trong `MutableCallSite` **cư xử như ordinary non-volatile field**. Vì vậy:

- Luồng A gọi `site.setTarget(newHandle)` **không tự ép** luồng B đang chạy nhận biết ngay target mới.
- Nếu không có synchronization thích hợp liên quan đến site, B có thể tiếp tục dùng giá trị target cũ đã cache, thậm chí **trì hoãn việc quan sát vô thời hạn** theo contract.
- B **cũng có thể thấy** target mới ngay sau `setTarget`, trước khi một lời gọi `syncAll` hoàn tất. Điều đó không biến `setTarget` thành volatile.
- Trong một luồng, đọc lại target sau khi chính luồng đó setTarget tuân theo thứ tự chương trình; ví dụ đơn luồng thường lập tức cho kết quả mới.

### 6.1. Ví dụ timeline khái niệm

```text
Thời điểm       Writer (A)                  Reader (B)
t0              target = V1                gọi V1
t1              setTarget(V2)              có thể vẫn gọi V1
t2              ...                        có thể gọi V1 hoặc V2
t3              syncAll([site]) bắt đầu    có thể còn V1 trong lúc đồng bộ
t4              syncAll hoàn tất           các lượt đọc target tương lai
                                          phải tuân theo hiệu lực syncAll
```

Đây là timeline giải thích **các kết quả được phép**, không phải thứ tự bắt buộc của mọi JDK. JIT có thể tối ưu target theo assumption phù hợp, và `syncAll` giúp JVM thực hiện thao tác cần thiết để các luồng nhận ra sự thay đổi.

**Không kết luận từ một lần chạy** rằng “trên máy này `setTarget` luôn được nhìn thấy ngay”. Chỉ vì reader tình cờ thấy V2 không có nghĩa chương trình đã có hợp đồng liên luồng đúng.

### 6.2. Những thứ không phải chứng minh visibility

- `Thread.sleep(...)` hoặc chờ vài mili-giây: thời gian trôi không tự tạo bảo đảm JMM.
- Dùng `System.out.println(...)` trong vòng lặp để quan sát: in log có synchronization và side effects, làm thay đổi hành vi kiểm thử.
- Đọc nhiều lần và thấy target mới: chỉ cho biết **lần thử đó** có visibility, không phải chứng minh luôn đúng.
- Dùng một `volatile boolean published`, `CountDownLatch`, `join` hay lock để phối hợp rồi thấy V2: các cơ chế này **tự tạo quan hệ synchronization/happens-before**; không thể từ output ấy tách riêng hiệu lực của `syncAll`.

Vì thế ví dụ đa luồng nên được thiết kế để chứng minh cách sử dụng API **có đồng bộ và output kiểm chứng được**, chứ không cố tạo một “race test” tùy máy để chứng minh stale value.

## 7. `MutableCallSite.syncAll(...)`: công bố target mới cho các luồng

Chữ ký:

```java
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

Nó thực hiện synchronization trên **mỗi site trong mảng**, khiến các luồng khác phải loại bỏ target cũ đã cache theo ràng buộc của Java Memory Model. Theo hợp đồng API, các lượt đọc target tương lai phải chấp nhận giá trị được lưu mới nhất tính **tương đối với lần `syncAll` ấy** (hoặc một cập nhật sau đó).

### 7.1. Thứ tự đúng: set target rồi sync

Nếu muốn công bố một bản relink:

```java
site.setTarget(newTarget);
MutableCallSite.syncAll(new MutableCallSite[]{site});
```

Đây là đoạn minh họa, giả định `site` là `MutableCallSite` hợp lệ và `newTarget` có đúng `site.type()`. Cần set trước vì `syncAll` công bố những update **đã có trước nó**; gọi sync rồi mới set không tự bảo đảm target vừa set về sau đã được công bố.

Nếu thay đổi **một nhóm site**, API cho phép gộp:

```java
synchronized (relinkLock) {
    first.setTarget(nextFirst);
    second.setTarget(nextSecond);
    MutableCallSite.syncAll(new MutableCallSite[]{first, second});
}
```

Đây là trích đoạn trong lớp có các biến `relinkLock`, `first`, `second`, `nextFirst`, `nextSecond` tương ứng. Với nhiều writer, Javadoc khuyến nghị dùng **mutual exclusion** phù hợp để tránh `setTarget` và `syncAll` xen kẽ gây race. Có thể dùng một lock ở tuyến **writer**. Reader thông thường không cần lấy lock này chỉ để gọi dynamic invoker.

### 7.2. syncAll bảo đảm và không bảo đảm những gì?

**Bảo đảm/mục đích theo contract:**

- Buộc các luồng sử dụng site tiến tới loại bỏ giá trị target cũ đã cache; hiệu lực có thể được mô hình hóa tương tự volatile write và những volatile read thích hợp.
- Tham chiếu đến cập nhật mới nhất **trước** lần `syncAll` đang được xét, trong một protocol relink có kiểm soát.
- Áp dụng trên **một mảng nhiều site**, thuận tiện cho cập nhật hàng loạt.

**Không bảo đảm:**

- **Không quay ngược** hoặc hủy lời gọi đã bắt đầu chạy trên target cũ.
- Không đòi B phải luôn gọi V1 cho đến lúc sync xong; B có thể thấy V2 **sớm**.
- Không tự biến việc đổi nhiều site thành **một transaction atomic**. Reader có thể bắt gặp một số site đã đổi, một số site còn cũ, nhất là trong khoảng writer đang cập nhật từng site.
- Không sửa các lỗi dữ liệu hoặc cung cấp một giao thức nguyên tử cho **mọi trạng thái ứng dụng khác**. Nếu target mới phụ thuộc nhiều field/config khác, phải thiết kế publication và consistency của chúng.
- Không bảo đảm thao tác **rẻ**: `syncAll` có thể yêu cầu JVM phối hợp/hủy cache JIT giữa các thread và **có thể chặn** đến khi xử lý xong.

### 7.3. Tính chất chi phí và tham số lỗi

Javadoc nhấn mạnh `syncAll` có thể đắt, nên **dùng tiết kiệm và batch khi có thể**, đặc biệt nếu runtime có nhiều call site cần relink trong cùng một đợt.

Nếu mảng truyền vào là `null` hoặc chứa phần tử `null`, API ném `NullPointerException`. Với mảng chứa null, một số site hợp lệ có thể đã được xử lý **trước khi exception phát sinh**; tập site được xử lý là implementation-dependent. Không truyền mảng lỗi và mong một thao tác “all-or-nothing”.

Một implementation có thể lưu target bằng volatile và khiến `syncAll` về thực tế rất nhẹ/no-op nhưng vẫn đúng contract. **Không** dựa vào chi tiết HotSpot hay một phiên bản JDK cụ thể làm lý do bỏ sync trong code có yêu cầu tương thích liên luồng.

## 8. Ví dụ Java 17 đa luồng: công bố rồi quan sát có phối hợp

Đây là chương trình **deterministic demonstration**: worker đọc OLD, chờ; writer thay target thành NEW và gọi `syncAll`; worker tiếp tục đọc NEW. Ta dùng `CountDownLatch` để điều khiển thời điểm, tránh các race ảnh hưởng stdout.

Tạo file **`MutableCallSiteThreadDemo.java`**:

```java
import java.lang.invoke.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class MutableCallSiteThreadDemo {
    public static void main(String[] args) throws Throwable {
        MutableCallSite site = new MutableCallSite(
                MethodHandles.constant(String.class, "OLD"));
        MethodHandle dynamic = site.dynamicInvoker();

        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch continueRead = new CountDownLatch(1);
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                before.set((String) dynamic.invokeExact());
                firstRead.countDown();
                continueRead.await();
                after.set((String) dynamic.invokeExact());
            } catch (Throwable e) {
                failure.set(e);
                firstRead.countDown();
            }
        }, "reader");

        reader.start();
        firstRead.await();

        site.setTarget(MethodHandles.constant(String.class, "NEW"));
        MutableCallSite.syncAll(new MutableCallSite[]{site});

        continueRead.countDown();
        reader.join();

        if (failure.get() != null) {
            throw new AssertionError(failure.get());
        }

        System.out.println("reader before: " + before.get());
        System.out.println("reader after syncAll: " + after.get());
        System.out.println("call site type: " + site.type());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 MutableCallSiteThreadDemo.java
java MutableCallSiteThreadDemo
```

Stdout:

```text
reader before: OLD
reader after syncAll: NEW
call site type: ()String
```

**Phân tích kỹ tính đúng đắn:**

1. Reader được phép thực hiện lượt gọi đầu tiên trước khi writer set target vì writer chờ `firstRead.await()`. Do đó lượt đầu trả OLD.
2. Writer set NEW rồi `syncAll` và mới nhả `continueRead`. Lượt đọc thứ hai xảy ra sau điểm đồng bộ; kết quả là NEW.
3. `dynamicInvoker` được tạo từ trước khi thay target, nhưng vẫn dispatch qua site để nhận phiên bản hiện hành theo memory semantics áp dụng.
4. **Giới hạn của demo:** `CountDownLatch` và `AtomicReference` đều có quy tắc đồng bộ của riêng chúng. Vì vậy chương trình chứng minh một protocol hợp lệ và cho output ổn định, **không thể dùng nó làm bằng chứng thực nghiệm rằng nếu bỏ `syncAll` thì luồng sẽ quan sát OLD**. Sự vắng mặt `syncAll` trong chương trình khác phải được phân tích bằng JMM, không dựa vào số lần test pass.
5. Việc gọi `reader.join()` chỉ làm chương trình chính chờ thread kết thúc và đọc được kết quả; `join` không làm target có visibility trong một vòng lặp **đang chạy trước đó** nếu thiếu protocol thích hợp.

Trong production, việc trì hoãn reader để bảo đảm một lần đọc sau sync có thể không phù hợp với throughput. Bạn cần quyết định **yêu cầu nhất quán**: cập nhật có thể được nhìn thấy sau một đợt relink, hay cần readers quan sát từng thay đổi ngay lập tức.

## 9. So sánh với ConstantCallSite và VolatileCallSite

### 9.1. ConstantCallSite

`ConstantCallSite` được liên kết một lần, giữ target cố định. Không có `syncAll` vì không có cập nhật target được phép. `setTarget(...)` không thể dùng để relink; nếu cần thay logic ở runtime, chọn loại site khác ngay từ thiết kế.

Thích hợp khi bootstrap đã tính xong implementation cuối cùng, việc thay đổi sau đó không cần thiết và JVM có cơ hội tối ưu liên kết ổn định.

### 9.2. VolatileCallSite

`VolatileCallSite` lưu target như **volatile field**:

- `setTarget` có hiệu lực của **volatile write**.
- `getTarget` có hiệu lực của **volatile read**; thread không được giữ mãi một bản target cũ khi thực hiện những lượt đọc sau cập nhật theo quy tắc synchronization order.
- `dynamicInvoker`/lệnh `invokedynamic` liên kết tới site cũng tuân theo semantics quan sát target tương ứng.
- **Không có `VolatileCallSite.syncAll`**; việc cập nhật từng site đã đi kèm bảo đảm volatile.
- Đổi lại có thể **tốn chi phí khi đọc/gọi thường xuyên** so với MutableCallSite, vì coupling giữa threads chặt hơn.

Volatile không có nghĩa mọi lời gọi đang chạy đều bị hủy hoặc rằng mọi kết quả của các reader phải xuất hiện theo một thứ tự hoàn toàn cố định; nó là contract memory visibility/happens-before cho target.

### 9.3. Bảng quyết định

| Câu hỏi | ConstantCallSite | MutableCallSite | VolatileCallSite |
| --- | --- | --- | --- |
| Có relink được? | Không | Có | Có |
| Target field semantics | Không đổi | Ordinary (non-volatile) | Volatile |
| Khi đổi target có cần `syncAll` để có bảo đảm tương đương? | Không áp dụng | Thông thường **có** nếu muốn công bố cho các luồng khác mà không có đồng bộ thay thế | Không |
| Chi phí đọc target | Có thể tối ưu rất tốt | Phù hợp khi update hiếm hoặc batch | Có thể thêm chi phí read synchronization |
| Mô hình ứng dụng | Kết quả bootstrap cố định | Hot relinking theo đợt | Từng lần cập nhật cần visibility với volatile semantics |

**Không phải lời khuyên “luôn dùng Mutable cho hiệu năng”.** Chọn loại call site theo yêu cầu quan sát và tần suất cập nhật; chỉ benchmark sau khi đã bảo đảm tính đúng đắn.

## 10. Ví dụ Java 17: ba loại site với cùng chữ ký

Tạo file **`CallSiteChoiceDemo.java`**:

```java
import java.lang.invoke.*;

public class CallSiteChoiceDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle one = MethodHandles.constant(int.class, 1);
        MethodHandle two = MethodHandles.constant(int.class, 2);

        ConstantCallSite fixed = new ConstantCallSite(one);
        MutableCallSite mutable = new MutableCallSite(one);
        VolatileCallSite volatileSite = new VolatileCallSite(one);

        MethodHandle fixedInvoker = fixed.dynamicInvoker();
        MethodHandle mutableInvoker = mutable.dynamicInvoker();
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();

        System.out.println("before: "
                + (int) fixedInvoker.invokeExact()
                + "," + (int) mutableInvoker.invokeExact()
                + "," + (int) volatileInvoker.invokeExact());

        mutable.setTarget(two);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        volatileSite.setTarget(two);

        System.out.println("after: "
                + (int) fixedInvoker.invokeExact()
                + "," + (int) mutableInvoker.invokeExact()
                + "," + (int) volatileInvoker.invokeExact());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CallSiteChoiceDemo.java
java CallSiteChoiceDemo
```

Stdout:

```text
before: 1,1,1
after: 1,2,2
```

Ví dụ này **chạy trên một luồng** để có output ổn định. Nó minh họa cùng một type `()int` nhưng ba chính sách target khác nhau: constant vẫn 1, mutable sau relink là 2, volatile sau relink là 2. **Không** dùng output đơn luồng để suy ra `VolatileCallSite` và `MutableCallSite` giống nhau về visibility liên luồng.

## 11. Vì sao syncAll không biến nhiều target thành một transaction?

Giả sử ứng dụng có hai site `calculatePrice` và `calculateTax` phải đổi sang cùng bộ policy V2. Writer thực hiện:

```java
synchronized (updateLock) {
    calculatePrice.setTarget(priceV2);
    calculateTax.setTarget(taxV2);
    MutableCallSite.syncAll(new MutableCallSite[]{
            calculatePrice, calculateTax
    });
}
```

Đây là **mã minh họa**, với các biến `updateLock` và hai site/handle đã được tạo, cùng kiểu với target trước đó của từng site.

Bảo đảm `syncAll` áp dụng cho **mỗi site** không có nghĩa reader thấy cả hai site đổi cùng một thời điểm. Trong khoảng writer đang gọi `setTarget` từng site, reader có thể chọn target V2 ở site giá và V1 ở site thuế. Writer lock không tự bảo vệ reader nếu reader không dùng cùng lock.

Nếu nghiệp vụ đòi **atomic snapshot của cả bộ policy**, hãy thiết kế một **điểm công bố duy nhất**: chẳng hạn thay một site điều phối tới một handle trỏ vào object cấu hình **immutable** chứa toàn bộ price/tax V2, hoặc dùng một atomic/volatile reference đến một snapshot policy đã hoàn chỉnh. Không thể suy ra tính nguyên tử nhóm chỉ từ một `syncAll(new MutableCallSite[]{...})`.

Đồng thời, nếu nhiều writer có thể relink cùng site, cần serialize việc `setTarget` và `syncAll`, quản lý version hoặc thứ tự chính sách; nếu writer B chen vào giữa lần set và sync của A, câu hỏi “giá trị mới nhất” có thể không còn tương ứng với version mà A định công bố.

## 12. Hiệu năng và kiến trúc relinking

### 12.1. Vì sao syncAll có thể đắt?

Javadoc cho biết thao tác có thể phải chờ các luồng dùng site loại bỏ phiên bản target cache cũ. Ở một số JVM, điều này liên quan tới tối ưu JIT và deoptimization/handshake hoặc các cơ chế nội bộ khác, nhưng **không nên giả định** chi tiết triển khai cố định.

Một chương trình gọi `syncAll` trong mỗi request khi target liên tục đổi có thể mất lợi ích tối ưu của MutableCallSite. Các lựa chọn:

- **Batch nhiều site** nếu cập nhật cùng đợt; tránh một lời gọi sync riêng cho mỗi site nếu không cần.
- **Relink khi có thay đổi cấu hình**, không phải khi đọc dữ liệu thông thường.
- Nếu update rất thường xuyên và cần volatile visibility, xem xét **`VolatileCallSite`**.
- Nếu phần lớn call site không đổi sau bootstrap, dùng **`ConstantCallSite`** khi phù hợp.
- Nếu cần thay **dữ liệu**, không phải thay **implementation**, cân nhắc một MethodHandle cố định đọc từ cấu hình `volatile`/atomic reference thay vì liên tục thay target.
- Đo bằng benchmark ổn định, bao gồm throughput, tail latency và chi phí của cả **writer relink** lẫn **reader dispatch**, không chỉ số nano-giây của một lần invoke.

### 12.2. Khi target có side effect

Việc đổi target chỉ thay **implementation được chọn cho lời gọi sau**. Nó không hủy công việc đang chạy trên target cũ. Một method V1 đang ghi database vẫn có thể hoàn tất sau khi V2 đã được publish. Nếu logic yêu cầu toàn bộ giao dịch dùng cùng version, hãy:

- Gắn version vào request/context;
- Chốt handler/snapshot lúc bắt đầu giao dịch;
- Định nghĩa giao thức graceful drain hoặc handoff;
- Tránh giả định `syncAll` là “stop-the-world rollback” của các lời gọi V1.

**Ranh giới visibility của target** và **ràng buộc nhất quán nghiệp vụ của toàn request** là hai vấn đề khác nhau.

## 13. Vòng đời liên kết với invokedynamic

Một bootstrap method của `invokedynamic` có thể trả một `CallSite` có `type()` phù hợp với descriptor của vị trí gọi. Nếu bootstrap chọn `MutableCallSite`, những invocation được liên kết qua site có thể dùng target mới sau relink theo semantics vừa học.

Đoạn **minh họa khái niệm**, không phải chương trình độc lập tự sinh bytecode:

```java
// Giả sử caller, name, type là tham số từ bootstrap
// và chooseInitialTarget(...) trả MethodHandle thích hợp.
MethodHandle initial = chooseInitialTarget(caller, name, type);
MutableCallSite site = new MutableCallSite(
        initial.asType(type));
return site; // giá trị trả về của bootstrap method
```

Khi runtime sau đó muốn chuyển implementation, nó cần giữ được tham chiếu tới `site` và gọi `site.setTarget(nextTarget)` với cùng `type`, sau đó công bố bằng `syncAll` nếu cần bảo đảm liên luồng.

Trong ví dụ Java runnable của bài, ta dùng `site.dynamicInvoker()` như một đường tương đương để quan sát relink. Đây là lựa chọn phù hợp để **học API mà không phải tự biên dịch hoặc phát bytecode invokedynamic**. Không nên nhầm việc tạo `MutableCallSite` trong một class Java với việc mọi invocation trong class tự động đi qua site.

## 14. Lỗi thường gặp và cách sửa

| Lỗi/nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng `setTarget` là volatile write | MutableCallSite có target ordinary-field semantics. | Nếu cần publication liên luồng, dùng `syncAll` hoặc cơ chế synchronization đúng, hoặc chọn `VolatileCallSite`. |
| Test thấy reader nhận V2 sau khi sleep rồi kết luận luôn đúng | Thời gian trôi/điều kiện test không tạo contract JMM. | Phân tích happens-before, không dựa vào quan sát ngẫu nhiên. |
| Giữ `MethodHandle cached = site.getTarget()` rồi mong cached theo relink | Biến `cached` giữ một target cũ cụ thể. | Dùng `site.dynamicInvoker()` để dispatch qua site. |
| Truyền handle khác kiểu vào `setTarget` | `site.type()` là bất biến. | Chuẩn hóa bằng `asType`/adapter rồi kiểm tra `type().equals(...)`. |
| Tạo `MutableCallSite(MethodType)` rồi gọi ngay | Target ban đầu được thiết kế để ném `IllegalStateException`. | Gắn target hữu dụng trước khi publish site. |
| Coi `syncAll` là atomic commit của nhiều site | Nó đồng bộ từng site; reader có thể thấy mixture. | Dùng một snapshot/điểm publication duy nhất khi cần consistency nhóm. |
| Cho rằng `syncAll` hủy lời gọi V1 đã chạy | Nó không thể quay ngược execution cũ. | Cấu trúc versioning, draining hoặc transaction boundary. |
| Gọi `syncAll` trước `setTarget` và kỳ vọng target sau được công bố | Sync công bố update tương đối với thời điểm sync. | Set trước, sync sau, và phối hợp writers. |
| Dùng `syncAll` trên mỗi request khi target thay rất nhanh | Có thể gây overhead lớn. | Batch hoặc cân nhắc `VolatileCallSite`. |
| Đọc `VolatileCallSite.getTarget()` như ordinary field | Volatile site có volatile semantics. | Chọn loại site đúng yêu cầu visibility. |
| Biến target thành `()String` cho site `(int)String` | Type khác => `WrongMethodTypeException`. | Thêm tham số giả bằng `dropArguments` nếu semantics phù hợp. |
| Truyền `null` vào `syncAll` hoặc chứa phần tử null | NPE; có thể đã xử lý một số site trước khi lỗi. | Validate mảng site trước khi gọi. |

### 14.1. Lỗi JMM không phải lỗi kiểu

`WrongMethodTypeException` ở `setTarget` báo handle mới **không khớp type**. Nó không liên quan chuyện target V2 có được các luồng khác quan sát hay không.

Ngược lại, một chương trình có **toàn bộ handle đúng chữ ký** vẫn có thể sai concurrency vì thiếu publication. Bài toán đúng cần giải đồng thời hai contract: *MethodType invariant* và *memory visibility*.

## 15. Kiểm thử và tiêu chí chất lượng

### 15.1. Kiểm thử đơn luồng

- Tạo site bằng handle V1 và lưu dynamic invoker.
- Gọi thành công, sau `setTarget(V2)` gọi thành công V2.
- Giữ một snapshot `getTarget()` trước relink và xác minh nó vẫn gọi V1.
- Thử handle sai `MethodType`, bắt `WrongMethodTypeException`.
- Tạo blank site, xác minh target ban đầu ném `IllegalStateException`; sau gắn target thì hoạt động.
- Kiểm tra `site.type()` luôn không đổi.

Đó là những assertion **ổn định**, không cần scheduler hay sleep.

### 15.2. Kiểm thử đa luồng

- Dùng latch/barrier để quy định khi nào worker được phép đọc; **ghi chú rõ** những primitive này đã tạo synchronization bổ sung.
- Sau `setTarget` + `syncAll`, cho phép worker thực hiện lượt đọc kế tiếp, kiểm chứng kết quả phù hợp.
- Dùng thread exception capture và kiểm tra `join`/timeout; không để test pass giả chỉ vì background thread chết.
- Không viết unit test có kỳ vọng “reader phải nhìn thấy OLD nếu không syncAll”: JMM **cho phép reader thấy NEW sớm**.
- Nếu yêu cầu nhất quán giữa nhiều site, viết test riêng cho protocol snapshot/version chứ không kiểm tra `syncAll` như giao dịch.

### 15.3. Kiểm thử năng lực relink của hệ thống thật

Trong production-like benchmark, quan sát cả số lượng `syncAll` trên giây, thời gian writer bị chặn, tỷ lệ relink, tail latency của các luồng gọi và mức phân bổ phiên bản V1/V2 quanh điểm chuyển. Với target có side effect, thêm trace version vào log/metric để biết execution nào bắt đầu bằng implementation nào. **Không kết luận correctness từ benchmark**; correctness phải dựa trên JMM + contract API.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao trên cùng luồng, gọi `dynamicInvoker()` sau `setTarget(V2)` thường trả V2, nhưng ở luồng khác không thể khẳng định điều đó chỉ từ `setTarget`?**

Vì luồng tự ghi tuân theo thứ tự chương trình; còn target của `MutableCallSite` có ordinary-field semantics, nên thiếu đồng bộ thì luồng khác có thể tiếp tục dùng V1 cache cũ.

**2. Vì sao `site.getTarget()` được lưu vào một biến không thay đổi cùng `setTarget`, nhưng `site.dynamicInvoker()` vẫn theo dõi site?**

`getTarget` trả chính MethodHandle được quan sát ở lần đọc đó; biến giữ tham chiếu cũ. Dynamic invoker là một handle dispatch qua site ở mỗi lời gọi theo semantics của call site.

**3. `setTarget` có chấp nhận một MethodHandle có kiểu trả về giống nhau nhưng khác số tham số không?**

Không. `newTarget.type()` phải **bằng hoàn toàn** `site.type()`, nếu không thì `WrongMethodTypeException`. Có thể tạo adapter rõ ràng nếu nghiệp vụ cho phép.

**4. `syncAll` có bảo đảm các lời gọi đã bắt đầu trên V1 dừng và chuyển sang V2 không?**

Không. Nó tác động đến visibility của target trong những lượt đọc sau, không đảo ngược những invocation đã chạy trên handle cũ.

**5. Vì sao `syncAll(new MutableCallSite[]{a,b})` không đủ để thay một bộ chính sách hai site một cách nguyên tử?**

Bởi writer thay từng target và reader có thể quan sát xen kẽ; `syncAll` đồng bộ hóa target của từng site, không tạo một transaction atomic cho toàn bộ bộ policy.

**6. Khi nào nên chọn `VolatileCallSite`?**

Khi target có thể cập nhật thường xuyên và ứng dụng cần volatile-like visibility cho từng lần đổi, thay vì tự phối hợp `MutableCallSite.syncAll` theo đợt. Phải chấp nhận và đo chi phí đọc/ghi tương ứng.

**7. Chạy demo đa luồng có `CountDownLatch` và thấy V2 có chứng minh chỉ `syncAll` tạo visibility không?**

Không. `CountDownLatch` cũng cung cấp synchronization/happens-before. Demo minh họa cách phối hợp đúng và output ổn định; để lý giải bảo đảm của `syncAll` phải dựa trên Javadoc/JMM.

## 17. Ghi nhớ

- **`MutableCallSite` cho phép relink `MethodHandle` target**, nhưng `site.type()` là bất biến.
- **`setTarget` chỉ là ordinary-field write đối với mục tiêu liên luồng**, không tự ép reader ở thread khác thấy target mới ngay.
- **`dynamicInvoker()` dispatch qua site**, khác với việc giữ một snapshot từ `getTarget()`.
- **`syncAll(new MutableCallSite[]{...})` dùng để công bố cập nhật tới các luồng**, có thể tốn chi phí; đặt sau `setTarget` và phối hợp nhiều writer.
- **Reader có thể thấy target mới sớm**, nhưng các lời gọi đã bắt đầu trên target cũ không bị thu hồi; nhóm nhiều site không tự có tính nguyên tử.
- **`VolatileCallSite`** sử dụng volatile semantics cho target và không có `syncAll`; **`ConstantCallSite`** là liên kết cố định.
- **Kiểm thử JMM phải dựa trên contract**, không kết luận từ sleep/log/timing hoặc việc test tình cờ thấy đúng một lần.

### Tài liệu chính thức Java SE 17

- [`MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html) — constructor, `getTarget`, `setTarget`, `dynamicInvoker`, `syncAll`, phần *Non-synchronization of target values* và *Java Memory Model details*.
- [`CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html) — type bất biến, target và dynamic invoker, ba subclass.
- [`VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html) — volatile read/write semantics và khác biệt với MutableCallSite.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) và [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — quy tắc chữ ký của target và lời gọi.
