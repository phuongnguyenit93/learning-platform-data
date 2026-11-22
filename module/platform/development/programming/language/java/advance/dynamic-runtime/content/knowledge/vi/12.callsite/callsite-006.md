# 12.6. Sử dụng MutableCallSite.syncAll và phối hợp các luồng cập nhật

> **Ngữ cảnh:** Bài Knowledge của nhóm **12. CallSite** thuộc module **Java Advance – dynamic-runtime**, áp dụng API chuẩn **Java 21**. Một `MutableCallSite` có thể đổi `MethodHandle target` sau khi ứng dụng đã giữ `dynamicInvoker()`. Nhưng `setTarget()` chỉ ghi theo ngữ nghĩa **biến thông thường**, không tự bảo đảm các luồng gọi khác thấy target mới đúng lúc. `MutableCallSite.syncAll(...)` là cơ chế chuyên dụng để buộc các luồng chấp nhận các thay đổi target; muốn cập nhật an toàn khi **nhiều writer**, cần thêm quy trình phối hợp và phải hiểu giới hạn không-atomic của nhiều call site.

## 1. Mục tiêu và điều kiện đầu vào

Sau bài này, bạn cần:

1. Phân biệt `CallSite.type()`, `getTarget()`, `setTarget()`, `dynamicInvoker()`; hiểu type của target cố định trong suốt vòng đời call site.
2. Giải thích được vì sao `MutableCallSite.setTarget(...)` **không phải** một volatile write và tại sao reader đang chạy trên JIT-optimized code có thể tạm dùng target cũ.
3. Nêu đúng ý nghĩa của `MutableCallSite.syncAll(MutableCallSite[] sites)` theo Javadoc Java 21, kể cả in-flight calls, thời điểm reader có thể thấy giá trị mới/cũ, chi phí, null và concurrent writers.
4. Dùng một lệnh `syncAll` sau khi thay đổi **nhiều call sites** để batch việc đồng bộ; tránh gọi mỗi lần thay đổi một site nếu không cần.
5. Giữ `setTarget` và `syncAll` trong **cùng một vùng loại trừ tương hỗ** khi có nhiều writer; không nhầm điều đó với transaction atomic ở phía reader.
6. Thiết kế cách xuất bản **immutable snapshot** nếu một request phải quan sát một bộ routing/configuration nhất quán.
7. Chọn đúng giữa `MutableCallSite`, `VolatileCallSite` và `ConstantCallSite`, xét tần suất update/visibility/overhead.
8. Chạy được năm Java labs với output được xác định và biết giới hạn của thí nghiệm concurrency.

**Kiến thức trước:** `MethodHandle`, `MethodType`, `MethodHandles.constant`, synchronized/lock, Java Memory Model (JMM), `CountDownLatch`, khái niệm happens-before và nguy cơ race. Không cần tự viết bytecode `invokedynamic` để học semantics: `dynamicInvoker()` cho phép thực hành đường gọi động tương đương một linked call site.

## 2. CallSite, target và dynamic invoker

`CallSite` là một điểm liên kết lời gọi động. Mỗi call site gắn với một `MethodType` cố định và một `MethodHandle` target có cùng kiểu ấy. Những subclass thường gặp:

| Loại | Target có đổi được? | Visibility khi đổi target | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `ConstantCallSite` | **Không** | Target cố định | Liên kết không bao giờ đổi sau bootstrap. |
| `MutableCallSite` | **Có** | Ghi/đọc target như **ordinary field**; dùng `syncAll` khi cần buộc các luồng chấp nhận target đã cập nhật | Invalidation/relink ít thường xuyên, theo lô. |
| `VolatileCallSite` | **Có** | `getTarget/setTarget` như **volatile read/write** | Thay đổi thường xuyên hoặc cần visibility gắn với từng update. |

`MutableCallSite` có hai cách khởi tạo:

```java
// Đoạn minh họa; cần import java.lang.invoke.*
MethodHandle initial = MethodHandles.constant(String.class, "old");
MutableCallSite site = new MutableCallSite(initial);      // type = ()String
MutableCallSite blank = new MutableCallSite(initial.type()); // chưa có target hữu ích
```

Cách thứ nhất dùng `initial` làm target. Cách thứ hai tạo một target mặc định ném `IllegalStateException` khi bị gọi cho tới khi được gán bằng `setTarget`.

`site.type()` luôn là `MethodType` ban đầu; `site.setTarget(newTarget)` đòi **newTarget.type() bằng chính xác site.type()**. Không có bước tự chuyển đổi kiểu ngầm: nếu muốn đổi signature, bạn có thể dùng `MethodHandle.asType(...)` một cách có chủ đích để tạo handle tương thích; vẫn phải kiểm tra conversion và return type.

### 2.1. Hai cách dùng target không giống nhau

```java
// Đoạn minh họa sau khi đã tạo site.
MethodHandle live = site.dynamicInvoker();
MethodHandle snapshot = site.getTarget();
```

- `live` là **invoker động**, nên khi được gọi nó liên kết tới target hiện thời của **cùng call site** theo visibility rules của `MutableCallSite`.
- `snapshot` chỉ là **tham chiếu tới một MethodHandle cụ thể** lấy ở thời điểm đọc `getTarget()`. Gọi lại chính `snapshot` về sau không có lý do tự chuyển sang handle vừa cài.
- Tạo **một MutableCallSite mới** và đổi biến Java trỏ tới nó không có tác dụng tự chuyển các invokers đã gắn với **call site cũ**; muốn relink, đổi target của call site mà invoker đang dùng.
- `dynamicInvoker()` là đường thực hành tiện lợi. `invokedynamic` thực sự trong bytecode được link qua bootstrap; các quy tắc target của call site là phần chung, nhưng chương trình bình thường không tự biến mọi Java method call thành `invokedynamic`.

## 3. Vấn đề visibility: vì sao setTarget chưa đủ?

Theo Javadoc Java 21, target variable của `MutableCallSite` hành xử giống **non-volatile field**. Khi updater thread chạy:

```text
Updater thread                  Reader thread
    |                               |
site.setTarget(newHandle)          invoke via dynamicInvoker
    |                               |
    +-- ordinary write             +-- có thể vẫn thấy oldHandle
    |                               |
    +-- không có                   +-- không buộc phải tự phát hiện
        cross-thread barrier            thay đổi đúng lúc
```

Một luồng độc lập không có synchronization thích hợp có thể **tiếp tục dùng bản target đã cache** trong một thời gian không bị giới hạn theo mô hình tương ứng. Đừng dùng quan sát kiểu “máy tôi chạy thấy ngay” làm bằng chứng đây là thao tác thread-safe theo nghĩa visibility.

Phân biệt ba vấn đề:

- **Đúng type**: `setTarget` kiểm tra type của handle; không liên quan chuyện thread khác có thấy update hay không.
- **Visibility**: thread khác nhận ra **target mới**; `syncAll` có hợp đồng bảo đảm riêng cho việc này.
- **Coordination/consistency**: nhiều writer có thể ghi chồng nhau, nhiều site có thể đang ở các version khác nhau; `syncAll` không tự cấp lock hay transaction.

JMM cho phép compiler/JIT tối ưu những lần đọc không có đủ synchronization. `syncAll` được thiết kế để các thực thi buộc những lần đọc target tương lai chấp nhận phiên bản mới, thay vì dựa vào may mắn của cache coherence thông thường.

## 4. Hợp đồng của MutableCallSite.syncAll(...) trong Java 21

Chữ ký chính xác:

```java
public static void MutableCallSite.syncAll(MutableCallSite[] sites);
```

Trong Java, cú pháp khai báo method thực tế là `public static void syncAll(MutableCallSite[] sites)` bên trong class `MutableCallSite`; dòng bên trên chỉ là cách ghi **đường dẫn API đầy đủ**, không phải mã nguồn khai báo hợp lệ khi đặt vào một class khác.

`syncAll` nhận một mảng các **MutableCallSite objects**. Với mỗi site được cung cấp, thao tác đồng bộ buộc các luồng khác bỏ những giá trị target cũ có thể đã cache và chấp nhận giá trị cập nhật trong những lần đọc target tương lai, theo chi tiết JMM của Javadoc.

### 4.1. Trình tự tiêu chuẩn

```java
// Đoạn minh họa, các site đã tạo và newA/newB có type phù hợp.
synchronized (updateLock) {
    siteA.setTarget(newA);
    siteB.setTarget(newB);
    MutableCallSite.syncAll(new MutableCallSite[] {siteA, siteB});
}
```

Hãy **chuẩn bị/validate** các `MethodHandle` trước khi bước vào vùng ghi nếu công việc biên dịch/lookup tốn thời gian; chỉ giữ đoạn commit gọn bên trong lock. Nếu có nhiều writer, **tất cả writer phải tuân cùng chính sách khóa** để ngăn `setTarget` từ writer khác xen giữa `setTarget` và `syncAll` của bạn.

### 4.2. Điều gì được bảo đảm?

- `setTarget` ghi target như ordinary variable. `syncAll` cung cấp **synchronization action** có hiệu ứng tương đương một đợt volatile write ở updater và volatile reads sau đó ở các thread đọc affected sites, theo mô hình được Javadoc mô tả.
- Nó buộc các reader tương lai của từng call-site target chấp nhận **giá trị được lưu mới nhất tương ứng với thao tác đồng bộ**, trừ những update mới hơn xuất hiện sau đó.
- Một số reader có thể thấy target mới **ngay sau `setTarget`, trước `syncAll`**; không cần chờ công bố cuối để “mở” giá trị mới.
- Reader có thể vẫn dùng target cũ **sau `setTarget` nhưng trước khi `syncAll` hoàn tất**. Việc một call đã bắt đầu trên target cũ **không bị đảo ngược**, không bị chạy lại và không được nâng cấp giữa chừng.
- `syncAll` có thể phải chờ cơ chế đồng bộ của các thread liên quan; các chi tiết cache invalidation/safepoint/deoptimization là tùy JVM. Không suy ra nó chỉ là một memory fence cực rẻ.
- `syncAll` áp dụng trên **từng site trong mảng**, nhưng **không phải một thao tác giao dịch nguyên tử cho cả tập site** trước mắt reader.

### 4.3. Những điều không được hứa

| Khẳng định | Đúng/sai | Giải thích |
| --- | --- | --- |
| “`setTarget` tự báo tất cả luồng khác” | **Sai** | Ordinary write không bắt buộc visibility ngay. |
| “Reader không thể thấy target mới trước `syncAll`” | **Sai** | Javadoc cho phép thấy sớm ngay sau `setTarget`. |
| “`syncAll` chờ mọi lời gọi cũ trả về” | **Sai** | Các lời gọi đã bắt đầu trên old target có thể tiếp tục hoàn tất theo old target. |
| “Một lệnh `syncAll` là transaction đổi tất cả site một lúc” | **Sai** | Readers có thể quan sát hỗn hợp version khi đọc nhiều site. |
| “`syncAll` loại bỏ race giữa hai writer” | **Sai** | Phải phối hợp/khóa `setTarget` và `syncAll` khi có nhiều updater. |
| “Mỗi site buộc phải gọi `syncAll` riêng” | **Sai** | API chấp nhận một mảng; batching thường phù hợp. |
| “Đọc `getTarget()` rồi giữ handle cũ sẽ tự đổi” | **Sai** | Đó là MethodHandle snapshot đã lấy; dùng `dynamicInvoker` để đi qua site. |

### 4.4. Null array, null element và xử lý lỗi

`syncAll(null)` ném `NullPointerException`. Nếu mảng `sites` chứa `null`, nó cũng ném `NullPointerException`, nhưng **có thể đã đồng bộ một số phần tử non-null trước khi ném**; phần tử nào đã được xử lý phụ thuộc implementation. Không xem lời gọi thất bại vì null là “all-or-nothing”.

Để tránh trạng thái khó đoán, hãy tạo danh sách site hợp lệ bằng API riêng, bảo đảm mảng khác null và không phần tử null **trước** khi bước vào commit. `syncAll(new MutableCallSite[0])` không có site cần đồng bộ; không thể dùng mảng rỗng để công bố update của những site bạn quên truyền vào.

## 5. Mô hình JMM của syncAll: hiểu vừa đủ và chính xác

Javadoc Java 21 giải thích bằng một **volatile variable khái niệm V** cho từng site `S` được sync. Hình dung:

1. Thread updater đã ghi target mới vào `S` trước khi gọi `syncAll`.
2. Một hành động đồng bộ tương tự **volatile write V** được đưa vào global synchronization order; các hành động đã làm trước đó trong updater được sắp trước write này.
3. Các thread có thể tiếp tục gọi site, nhưng implementation phải buộc chúng cuối cùng ghi nhận mốc đồng bộ đó như một **volatile read khái niệm** trước các lần đọc target tương lai theo JMM constraints.
4. Sau mốc đồng bộ liên quan, chúng không được tiếp tục dùng một giá trị target cũ hơn như thể các update trước `syncAll` chưa xảy ra.

**Không có một biến `V` công khai trong chương trình để người học tự đọc/ghi**; đây là mô hình hình thức mô tả hiệu ứng, không phải lời khuyên tự xây một `volatile boolean` rồi hy vọng nó thay thế chính xác `syncAll` trong mọi đường gọi đã JIT-compile.

Javadoc còn cho phép implementation trì hoãn hoàn tất `syncAll` trong khi reader tiếp tục sử dụng giá trị cũ, miễn tôn trọng JMM; implementation được khuyến khích tránh livelock và cuối cùng buộc các luồng xét đến thay đổi.

### 5.1. Một lỗi tư duy phổ biến: “Đã có lock ở writer nên reader chắc thấy”

Nếu chỉ updater giữ `synchronized(lock)` mà reader gọi `dynamicInvoker()` **không lấy cùng lock**, thì riêng lock phía writer không tự tạo một chương trình đọc-ghi phối hợp đầy đủ giữa hai bên. `syncAll` có hợp đồng riêng đối với visibility target. Nếu yêu cầu toàn bộ thao tác nghiệp vụ của reader có tính nhất quán nhiều bước, cần giao thức synchronization/snapshot ở phía reader, không chỉ writer lock.

## 6. Lab 1 — đổi target, sync một site và giữ snapshot cũ

Tạo file độc lập **`BasicSyncLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.WrongMethodTypeException;

public class BasicSyncLab {
    public static void main(String[] args) throws Throwable {
        MutableCallSite site =
                new MutableCallSite(MethodHandles.constant(String.class, "blue"));
        MethodHandle live = site.dynamicInvoker();
        MethodHandle oldTarget = site.getTarget();

        System.out.println("type=" + site.type());
        System.out.println("before=" + (String) live.invokeExact());

        site.setTarget(MethodHandles.constant(String.class, "green"));
        MutableCallSite.syncAll(new MutableCallSite[] {site});

        System.out.println("after=" + (String) live.invokeExact());
        System.out.println("oldSnapshot=" + (String) oldTarget.invokeExact());

        try {
            site.setTarget(MethodHandles.constant(int.class, 7));
            System.out.println("wrongType=unexpected");
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongType=WrongMethodTypeException");
        }
    }
}
```

Biên dịch/chạy bằng Java 21:

```sh
javac --release 21 -Xlint:all BasicSyncLab.java
java BasicSyncLab
```

**Stdout:**

```text
type=()String
before=blue
after=green
oldSnapshot=blue
wrongType=WrongMethodTypeException
```

### 6.1. Diễn giải

- `MethodHandles.constant(String.class,"blue")` là handle không có tham số, trả `String`, nên `site.type()` là `()String`.
- `live` đi qua `site`; sau update và `syncAll` nó đọc target mới. `oldTarget` được lấy qua `getTarget` trước đó vẫn là handle trực tiếp trả "blue".
- `setTarget` của một `()String` site không chấp nhận `()int`; ném `WrongMethodTypeException`, không tự đổi type của call site.
- Chương trình chạy **một thread**, nên không dùng kết quả "after=green" để kết luận rằng bỏ `syncAll` vẫn an toàn giữa nhiều thread. Ta gọi `syncAll` để minh họa giao thức update cần dùng khi mở rộng sang runtime có concurrency.

## 7. Phối hợp nhiều site: staging, commit và một lần syncAll

Giả sử hệ thống có hai route targets `routeRead` và `routeWrite`. Mỗi route có một `MutableCallSite` để cho phép plugin thay thế implementation. Nếu thay hai target, mẫu có kiểm soát:

```text
[Chuẩn bị newRead, newWrite; kiểm tra MethodType]
                 |
[Writer lock: ngăn writer khác xen vào]
                 |
      readSite.setTarget(newRead)
     writeSite.setTarget(newWrite)
                 |
 MutableCallSite.syncAll([readSite, writeSite])
                 |
[Writer lock released; ghi nhận batch đã publish]
```

**Nên làm:**

- Chuẩn bị target handles ngoài lock, bảo đảm `newRead.type().equals(readSite.type())` và tương tự với site khác.
- Lấy lock **chung của mọi writer**; gọi tất cả `setTarget` sau đó **một lần** `syncAll` cho những sites đã thay đổi.
- Không trộn lệnh cập nhật của writer B vào giữa các lệnh của writer A; nếu phải hỗ trợ rollback khi lỗi, xây rõ state machine ngoài `syncAll`.
- Ghi log version/batch id sau khi công bố, nhưng không coi việc log đã xong là một chứng cứ rằng **mọi lời gọi bắt đầu trước đó** đã chuyển logic.
- Khi cần thay nhiều site nhưng có phụ thuộc logic chéo, đánh giá giải pháp **một site giữ immutable snapshot** ở mục 11.

### 7.1. Tại sao batching có ích?

Theo đặc tả, một lần `syncAll` với nhiều sites có hiệu quả hình thức như nhiều lần sync từng site. Nhưng JVM có thể chịu **chi phí cố định lớn** mỗi lần global coordination và chi phí tăng thêm nhỏ cho mỗi site. Vì vậy nên gom những thay đổi liên quan thay vì buộc tất cả thread đồng bộ sau từng phép `setTarget`.

Không có bảo đảm thời gian chạy cố định của `syncAll`; benchmark cần dựa trên JDK, OS, số lượng reader và workload thực. Không dùng nó như API hàng-ngàn-lần-mỗi-giây nếu chưa đánh giá chi phí; cân nhắc `VolatileCallSite` khi update liên tục.

## 8. Lab 2 — batch hai site và một reader có điều phối

Tạo **`BatchVisibilityLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class BatchVisibilityLab {
    public static void main(String[] args) throws Throwable {
        MutableCallSite left =
                new MutableCallSite(MethodHandles.constant(String.class, "left-1"));
        MutableCallSite right =
                new MutableCallSite(MethodHandles.constant(String.class, "right-1"));
        MethodHandle readLeft = left.dynamicInvoker();
        MethodHandle readRight = right.dynamicInvoker();

        CountDownLatch firstReadDone = new CountDownLatch(1);
        CountDownLatch published = new CountDownLatch(1);
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                String oldLeft = (String) readLeft.invokeExact();
                String oldRight = (String) readRight.invokeExact();
                before.set(oldLeft + "/" + oldRight);
                firstReadDone.countDown();

                published.await();
                String newLeft = (String) readLeft.invokeExact();
                String newRight = (String) readRight.invokeExact();
                after.set(newLeft + "/" + newRight);
            } catch (Throwable e) {
                failure.set(e);
                firstReadDone.countDown();
            }
        }, "reader");
        reader.start();
        firstReadDone.await();

        Object updateLock = new Object();
        synchronized (updateLock) {
            left.setTarget(MethodHandles.constant(String.class, "left-2"));
            right.setTarget(MethodHandles.constant(String.class, "right-2"));
            MutableCallSite.syncAll(new MutableCallSite[] {left, right});
        }
        published.countDown();
        reader.join();
        if (failure.get() != null) throw new AssertionError(failure.get());

        System.out.println("before=" + before.get());
        System.out.println("after=" + after.get());
        System.out.println("updatedTargets=" +
                left.getTarget().type().equals(right.getTarget().type()));
    }
}
```

Lệnh:

```sh
javac --release 21 -Xlint:all BatchVisibilityLab.java
java BatchVisibilityLab
```

**Stdout:**

```text
before=left-1/right-1
after=left-2/right-2
updatedTargets=true
```

### 8.1. Vì sao output có tính xác định?

- Reader đọc cả hai handles trước khi cho phép updater tiếp tục thông qua `firstReadDone`.
- Updater thay hai targets và gọi **một** `syncAll`. Sau khi return, updater mở cổng `published`; reader mới đi tiếp.
- `reader.join()` bảo đảm main đã nhận xong kết quả của reader trước khi in.
- `updatedTargets=true` trong lab chỉ so sánh **MethodType** của hai targets (cùng `()String`); nó **không** chứng minh hai values là một transaction. Các dòng "before/after" mới là quan sát giá trị trong lịch trình có điều phối này.

**Điều không được suy ra:** `CountDownLatch` tự cung cấp synchronization/happens-before. Vì vậy đây **không phải** một thí nghiệm định lượng về độ trễ visibility khi **bỏ `syncAll`**, và không chứng minh rằng riêng `syncAll` làm mọi tổ hợp nhiều site trở thành atomic. Mục tiêu lab là kiểm tra cách dùng API và một chuỗi update có phối hợp cho stdout ổn định.

### 8.2. Thử nghiệm mở rộng (không khuyến nghị dùng làm assertion)

Bạn có thể cho reader chạy vòng lặp liên tục và thay hai sites lần lượt để quan sát có lúc mix `left-2/right-1`. Nhưng nếu không quan sát được tổ hợp đó trong một lần chạy **cũng không chứng minh atomicity**. Scheduler, JIT, CPU và kiến trúc bộ nhớ ảnh hưởng kết quả; không viết test dựa trên sự xuất hiện ngẫu nhiên của race.

## 9. Nhiều writer: đưa setTarget và syncAll vào cùng critical section

`syncAll` không cài lock cho call site. Nếu hai updater cùng tác động một site:

```text
Writer A: setTarget(A)
Writer B: setTarget(B)
Writer A: syncAll([site])
Writer B: syncAll([site])
```

Thì `syncAll` của A có thể đang đồng bộ **giá trị B**, chứ không nhất thiết giá trị A mà A dự định công bố. Nếu A kiểm tra ngay sau sync và ghi log “đã công bố A” thì ghi nhận có thể sai về trạng thái thực.

Mẫu đúng khi **mọi writer tuân cùng lock**:

```java
// Đoạn minh họa: nơi điều khiển update chung.
synchronized (UPDATE_LOCK) {
    int nextVersion = ++version;
    site.setTarget(MethodHandles.constant(String.class, "v-" + nextVersion));
    MutableCallSite.syncAll(new MutableCallSite[] {site});
}
```

Bản thân `synchronized` ở writer đảm bảo **các writer không xen nhau**. Nó không tự tạo atomic snapshot ở reader và không giữ reader đợi trong khi writer cập nhật, trừ khi reader cũng tham gia một protocol thích hợp.

**Nếu nhiều call sites được cập nhật bởi nhiều nhóm:** dùng một lock chung cho những sites có cùng bất biến, hoặc partition locks theo rules không chồng lấn rồi thiết kế thứ tự acquire/deadlock avoidance. Không dùng nhiều lock độc lập cho cùng site nếu có khả năng interleaving.

## 10. Lab 3 — hai writer cùng xuất bản với một lock

Tạo **`CoordinatedWritersLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;
import java.util.concurrent.CountDownLatch;

public class CoordinatedWritersLab {
    private static final Object UPDATE_LOCK = new Object();
    private static final MutableCallSite SITE =
            new MutableCallSite(MethodHandles.constant(String.class, "version-0"));
    private static int version;

    private static void publishNext() {
        synchronized (UPDATE_LOCK) {
            int next = ++version;
            SITE.setTarget(MethodHandles.constant(String.class, "version-" + next));
            MutableCallSite.syncAll(new MutableCallSite[] {SITE});
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle live = SITE.dynamicInvoker();
        CountDownLatch start = new CountDownLatch(1);

        Runnable writer = () -> {
            try {
                start.await();
                publishNext();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        };

        Thread a = new Thread(writer, "writer-A");
        Thread b = new Thread(writer, "writer-B");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("published=" + version);
        System.out.println("result=" + (String) live.invokeExact());
    }
}
```

```sh
javac --release 21 -Xlint:all CoordinatedWritersLab.java
java CoordinatedWritersLab
```

**Stdout:**

```text
published=2
result=version-2
```

### 10.1. Phân tích concurrency

- Hai writer bắt đầu gần nhau sau `start.countDown()`. Thứ tự **writer-A hay writer-B vào lock trước** không xác định và không cần xác định.
- Writer nào vào lock sẽ tăng `version`, cập nhật target và gọi `syncAll` **trước khi thả lock**; writer tiếp theo không thể xen vào giữa bộ lệnh đó.
- Sau `a.join()` và `b.join()`, cả hai updater đã hoàn tất; `version` bằng 2 và final target trả "version-2" độc lập với writer identity.
- Đây là ví dụ tốt để tách **mutual exclusion của writer** khỏi **visibility của target đối với reader**. `join()` và `CountDownLatch` cũng đưa synchronization vào lab, nên không dùng nó để đo khả năng stale target khi bỏ `syncAll`.

**Gợi ý production:** xử lý lỗi từ writer có chủ đích (ví dụ bằng `Future`, `ExecutorService`, completion record). Trong bài lab, code paths có sẵn luôn xây target đúng type nên chương trình không cần nhánh rollback.

## 11. Sync cả một mảng không tạo atomic multi-site transaction

Đây là giới hạn quan trọng nhất khi thiết kế hệ thống dynamic routing.

Giả sử `siteA` và `siteB` phải cùng version trong một transaction:

```text
              Giá trị ban đầu: A=v1, B=v1

Updater (có writer lock)          Reader (không dùng lock)
------------------------          -----------------------
siteA.setTarget(A_v2)             read siteA -> có thể v2
siteB.setTarget(B_v2)             read siteB -> có thể v1
syncAll([siteA,siteB])            // đã quan sát tổ hợp v2/v1
```

Việc writer có lock **không chặn reader** trừ khi reader cũng lấy lock đó hoặc đọc một immutable snapshot hợp lệ. Javadoc cho phép reader thấy target mới trước `syncAll`; nhiều site có thể được đọc tại những thời điểm khác nhau. Ngay sau syncAll, nếu một reader thực hiện **hai lời gọi riêng** và một updater mới xảy ra **giữa hai lời gọi**, reader vẫn có thể thấy **hai version** khác nhau.

`syncAll` có tác dụng đồng bộ **target values**, không biến nhiều calls thành một atomic business transaction. Nếu yêu cầu “một request phải thấy cấu hình A+B cùng version”, cần thêm mô hình nhất quán.

### 11.1. Cách làm: xuất bản một immutable snapshot

Gói những phần liên quan vào một immutable object:

```text
RouteSnapshot(version, routeA, routeB)  // record immutable
                  |
          MethodHandle ()RouteSnapshot
                  |
            MutableCallSite
                  |
             dynamicInvoker()
                  |
           Reader đọc 1 snapshot
                  |
      dùng cả routeA và routeB từ snapshot đó
```

Updater xây một `RouteSnapshot` hoàn chỉnh, rồi thay **một target** trả snapshot đó và `syncAll`. Reader giữ **một kết quả snapshot** cho suốt logical operation. Như vậy bên trong một snapshot không có tổ hợp hai version khác nhau.

Đây là bảo đảm về **cấu trúc dữ liệu/điểm đọc duy nhất**, không phải do `syncAll` biến các fields của object thành giao dịch. Record Java có final fields, nhưng nếu record chứa mutable references cần tiếp tục **copy/defensive immutability**. Không mutate object đã xuất bản sau đó nếu muốn bất biến.

## 12. Lab 4 — publish một snapshot nhất quán

Tạo **`SnapshotPublicationLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MutableCallSite;

public class SnapshotPublicationLab {
    record RouteSnapshot(int generation, String first, String second) {}

    public static void main(String[] args) throws Throwable {
        MutableCallSite site = new MutableCallSite(
                MethodHandles.constant(RouteSnapshot.class,
                        new RouteSnapshot(1, "A1", "B1")));
        MethodHandle readSnapshot = site.dynamicInvoker();

        RouteSnapshot oldValue = (RouteSnapshot) readSnapshot.invokeExact();
        site.setTarget(MethodHandles.constant(RouteSnapshot.class,
                new RouteSnapshot(2, "A2", "B2")));
        MutableCallSite.syncAll(new MutableCallSite[] {site});
        RouteSnapshot newValue = (RouteSnapshot) readSnapshot.invokeExact();

        System.out.println("before=" + oldValue.generation() + ":" +
                oldValue.first() + "/" + oldValue.second());
        System.out.println("after=" + newValue.generation() + ":" +
                newValue.first() + "/" + newValue.second());
        System.out.println("oldStillImmutable=" + oldValue.first());
    }
}
```

```sh
javac --release 21 -Xlint:all SnapshotPublicationLab.java
java SnapshotPublicationLab
```

**Stdout:**

```text
before=1:A1/B1
after=2:A2/B2
oldStillImmutable=A1
```

### 12.1. Hiểu đúng bảo đảm snapshot

- Call site type là `()RouteSnapshot`. Toàn bộ cấu hình được đọc qua **một invocation** rồi giữ bằng biến cục bộ.
- Sau update + sync, lời gọi mới có thể nhận snapshot v2; snapshot v1 đã lấy trước đó vẫn là object bất biến `(1,A1,B1)`.
- Nếu có thêm các thread reader, chúng có thể thấy v1 hoặc v2 tùy thời điểm hợp lệ; **không có một snapshot chứa A2/B1** vì updater không hề tạo object như vậy.
- Nếu reader cần dùng nhiều giá trị trong cùng request, hãy gọi `readSnapshot.invokeExact()` **một lần** và dùng object nhận được, thay vì gọi lại mỗi lần cần routeA/routeB.

**Giới hạn:** nếu writer xuất bản nhiều snapshot liên tiếp, hai request khác nhau vẫn có thể thấy hai version khác nhau — đó là điều bình thường. Nếu cần độ trễ visibility thấp ở mỗi lần update liên tục, `VolatileCallSite` hoặc `AtomicReference<RouteSnapshot>` có thể phù hợp hơn tùy yêu cầu tổng thể.

## 13. Chọn Mutable, Volatile hay Constant CallSite

| Tiêu chí | `ConstantCallSite` | `MutableCallSite` | `VolatileCallSite` |
| --- | --- | --- | --- |
| Có thể `setTarget`? | Không, ném `UnsupportedOperationException` | Có | Có |
| Target semantics | Final/permanent | Ordinary field + `syncAll` để ép nhận cập nhật | Volatile read/write |
| Nhiều reader threads | Dùng target cố định | Cần lập kế hoạch visibility khi relink | Mỗi update có volatile semantics |
| Tần suất update điển hình | Không đổi | Ít, có thể gom batch | Thường xuyên |
| Hỗ trợ đồng bộ hàng loạt | Không cần | `syncAll(MutableCallSite[])` | Không cần/không có `syncAll` riêng |
| Chi phí và tối ưu | Thường có cơ hội tối ưu cao | Đổi ít, chi phí đồng bộ từng đợt có thể lớn | Tight coupling giữa reader/updater có thể gây overhead |
| Có bảo đảm transaction nhiều member? | Không liên quan | **Không** | **Không** |

**`VolatileCallSite`:** Javadoc nói target có tính chất như volatile variable, các luồng reader không được cố chấp dùng target cũ khi có update phù hợp; không phải gọi `syncAll`. Đổi lại có thể tốn chi phí ở đường đọc/gọi động. Với update thường xuyên, Javadoc `MutableCallSite` khuyến nghị cân nhắc volatile call site.

**`ConstantCallSite`:** target đã gắn thì không thể thay. `dynamicInvoker()` trả permanent target, phù hợp với các liên kết không bao giờ thay đổi.

**Lựa chọn thực tế:** nếu một hệ thống plugin cần cập nhật rule vài lần mỗi giờ và có nhiều hot call sites, `MutableCallSite` + batch `syncAll` là một ứng viên hợp lý. Nếu cấu hình thay nhiều lần mỗi giây, đánh giá `VolatileCallSite`. Nếu chỉ cần đọc reference data hoặc immutable config mà không có method-handle composition, `volatile` field/`AtomicReference` có thể đơn giản hơn. Đừng đưa `CallSite` vào code chỉ để thay cho mọi biến có thể cập nhật.

## 14. Lab 5 — Volatile, Constant, blank site và lỗi null

Tạo **`CallSiteChoicesLab.java`**:

```java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.VolatileCallSite;

public class CallSiteChoicesLab {
    public static void main(String[] args) throws Throwable {
        VolatileCallSite volatileSite =
                new VolatileCallSite(MethodHandles.constant(int.class, 1));
        MethodHandle live = volatileSite.dynamicInvoker();
        System.out.println("volatileBefore=" + (int) live.invokeExact());
        volatileSite.setTarget(MethodHandles.constant(int.class, 2));
        System.out.println("volatileAfter=" + (int) live.invokeExact());

        ConstantCallSite constantSite =
                new ConstantCallSite(MethodHandles.constant(String.class, "fixed"));
        System.out.println("constant=" +
                (String) constantSite.dynamicInvoker().invokeExact());
        try {
            constantSite.setTarget(MethodHandles.constant(String.class, "other"));
            System.out.println("constantSet=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("constantSet=UnsupportedOperationException");
        }

        MutableCallSite blank = new MutableCallSite(MethodType.methodType(int.class));
        try {
            int ignored = (int) blank.dynamicInvoker().invokeExact();
            System.out.println("blank=unexpected " + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("blank=IllegalStateException");
        }

        try {
            MutableCallSite.syncAll(null);
            System.out.println("nullArray=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullArray=NullPointerException");
        }
        try {
            MutableCallSite.syncAll(new MutableCallSite[] {blank, null});
            System.out.println("nullElement=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullElement=NullPointerException");
        }
    }
}
```

```sh
javac --release 21 -Xlint:all CallSiteChoicesLab.java
java CallSiteChoicesLab
```

**Stdout:**

```text
volatileBefore=1
volatileAfter=2
constant=fixed
constantSet=UnsupportedOperationException
blank=IllegalStateException
nullArray=NullPointerException
nullElement=NullPointerException
```

### 14.1. Phân biệt exception

- `ConstantCallSite.setTarget` không hỗ trợ việc đổi target dù new handle cùng type.
- `new MutableCallSite(MethodType.methodType(int.class))` tạo site với type `()int` nhưng chưa cài target hữu ích, nên gọi `dynamicInvoker` lúc này ném `IllegalStateException`.
- `syncAll` với array reference `null` hoặc phần tử `null` đều ném `NullPointerException`.
- Với mảng có phần tử null, **không kết luận mọi non-null site chưa được đồng bộ**: Javadoc cho phép một số site đã được xử lý trước khi phát hiện null. Phải validate mảng toàn vẹn trước.
- Lab `VolatileCallSite` chạy trong một thread nên không phải benchmark hay stress test visibility, chỉ xác nhận API và output. Semantics đa luồng phải dựa vào Javadoc, không dựa vào vài dòng output.

## 15. Những lỗi thực tế khi xây runtime relinking

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `setTarget` ném `WrongMethodTypeException` | New target có `MethodType` khác site type | Kiểm tra `newHandle.type().equals(site.type())`; chỉ `asType` nếu conversion hợp lệ/có chủ đích. |
| `setTarget(null)` ném `NullPointerException` | Null target không được hỗ trợ | Dùng handle trả sentinel hoặc thrower đúng signature, không gắn null. |
| `dynamicInvoker` của blank site ném `IllegalStateException` | Dùng `MutableCallSite(MethodType)` trước khi gắn target thực | Cài initial target trước khi công bố site. |
| Reader vẫn thấy old target | Thiếu cross-thread visibility hoặc call đã bắt đầu trên old handle | Gọi `syncAll` theo giao thức; không đòi hủy in-flight calls. |
| Update từ hai writer bị ghi chồng | `setTarget` và `syncAll` không được bảo vệ chung | Áp cùng lock, mô tả quy tắc version, staging và commit. |
| Reader thấy `A2/B1` | Các sites được đọc riêng, batch sync **không atomic** | Một immutable snapshot hoặc protocol reader có lock/version validation. |
| Latency tăng mạnh khi cập nhật | `syncAll` có chi phí phối hợp các thread | Gom sites vào một lần sync, giảm tần suất, benchmark, cân nhắc volatile call site. |
| Giữ direct handle từ `getTarget` mà gọi ra logic cũ | Direct `MethodHandle` không liên kết với site | Gọi qua `dynamicInvoker`, hoặc lấy lại target theo giao thức được đồng bộ. |
| Lệnh `syncAll` kết thúc nhưng service request cũ vẫn chạy | Lời gọi đã bắt đầu trước đó không bị rollback | Thiết kế drain/ref-count/barrier riêng nếu cần chờ in-flight requests. |
| `syncAll` ném `NullPointerException` giữa batch | Array chứa null | Validate mảng trước commit; đừng giả định call failed là hoàn toàn chưa sync. |
| Đổi object `MutableCallSite` mà invoker vẫn chạy site cũ | `dynamicInvoker()` gắn với một site cụ thể | Giữ identity site; cập nhật target của chính site đó. |
| Stress test chạy 100 lần đều thấy bản mới trước sync | Cấu hình scheduler/JIT may mắn | Không dùng “không thấy lỗi” để phủ nhận JMM; kiểm tra spec/concurrency thiết kế. |

### 15.1. Những trường hợp cần thêm cơ chế ngoài syncAll

- **Graceful shutdown hoặc hot reload:** muốn chờ tất cả lời gọi target cũ kết thúc, cần in-flight request accounting, quiescence, stop-the-world protocol, ref-count hoặc lifecycle barrier. `syncAll` không giải quyết yêu cầu này.
- **Giao dịch nhiều route:** cần snapshot/lock/atomic state hand-off; `syncAll` không cung cấp atomicity cho hai lần `dynamicInvoker` riêng biệt.
- **Version monotonicity cho reader:** nếu reader phải bỏ các version cũ và chỉ chấp nhận version tăng, thêm version check theo logical request.
- **Failure recovery:** một update nhiều site có thể thất bại giữa chừng do validation/lookup/error; staging tất cả target trước, quyết định rollback/compensation theo đặc tả ứng dụng. Không mặc định `syncAll` có cơ chế undo.
- **Thao tác blocking:** đừng gọi `syncAll` trong một latency-critical hot path nếu chưa đánh giá, bởi có thể cần phối hợp các reader threads.

## 16. Quy trình production: chuẩn bị, công bố, đo lường

Một quy trình gọn nhưng có kiểm soát:

```text
[1] Nhận yêu cầu thay logic (plugin/config/feature flag)
       |
[2] Dựng & kiểm tra tất cả new MethodHandles bên ngoài writer lock
       |   - correct owner/class loader
       |   - exact MethodType per CallSite
       v
[3] Xác nhận policy, version mới và danh sách MutableCallSites không null
       |
[4] Acquire shared writer lock
       |
[5] setTarget cho sites liên quan
       |
[6] syncAll(một mảng gồm tất cả sites đã thay)
       |
[7] Ghi commit version / release writer lock
       |
[8] Reader dùng dynamicInvoker và contract nhất quán
       |
[9] Monitor: update rate, syncAll latency, version, in-flight traffic
```

### 16.1. Chọn giới hạn của critical section

Không tạo/chạy compiler, không gọi plugin user code, không block trên I/O mạng khi đang giữ writer lock nếu có thể staging trước. Giữ `setTarget` và `syncAll` bên trong cùng lock; điều này có thể làm writer khác đợi lâu nếu `syncAll` có chi phí lớn, vì vậy điều chỉnh cadence/batching.

### 16.2. Thiết kế logging mà không khẳng định quá mức

Nên ghi “update batch X đã hoàn tất `syncAll`” thay vì “tất cả requests đang chạy đều dùng bản X”. Có thể log version của target và số call sites, nhưng không suy được chính xác thời điểm mỗi reader bắt đầu hay kết thúc chỉ từ việc updater trả về.

### 16.3. Tránh lạm dụng JIT assumptions

Các implementation có thể cần invalidation/deoptimization, hoặc có cách dùng volatile targets khiến `syncAll` rất nhẹ. Không viết code phụ thuộc vào details HotSpot cụ thể (ví dụ “luôn flush CPU cache theo cách X”) hay hứa độ trễ xác định. **API-level contract** là nguồn đúng để lý giải visibility.

### 16.4. Khác nhau giữa visibility và publication của dữ liệu khác

`syncAll` bảo đảm ngữ nghĩa visibility được đặc tả cho **call-site target**. Nếu target mới trỏ đến mutable state khác, vẫn phải bảo đảm **safe publication, immutable construction hoặc synchronization phù hợp** cho state đó. Khuyến nghị: target mới được xây hoàn chỉnh trước `setTarget`; dữ liệu chia sẻ qua immutable objects, final fields hoặc cơ chế JMM rõ ràng. Đừng dùng `syncAll` như lời giải tổng quát cho mọi data race trong ứng dụng.

## 17. Bài tập tự kiểm tra

**Bài 1 – Phân biệt handle đang sống và snapshot.** Trong Lab 1, giải thích vì sao `live.invokeExact()` trả "green" nhưng `oldTarget.invokeExact()` vẫn trả "blue". Nếu tạo một `MutableCallSite` mới với "red" và đổi biến `site`, liệu `live` có chuyển sang "red" không? Vì sao?

**Bài 2 – Type mismatch.** Tạo site `(int)String`, rồi thử `setTarget` bằng handle `()String`. Dự đoán exception; sửa bằng cách dựng handle đúng type hoặc dùng `dropArguments`/`asType` có chủ đích. Phân biệt lỗi Java compile time và lỗi runtime khi set target.

**Bài 3 – Batch update.** Thêm `siteC` vào Lab 2, gắn `()String` target "third-1" rồi đổi thành "third-2" cùng hai sites khác. Dùng một mảng ba sites cho `syncAll`. Giải thích lợi ích batching và vì sao vẫn chưa có multi-site transaction.

**Bài 4 – Hai writer.** Bỏ `synchronized (UPDATE_LOCK)` trong Lab 3. Vì sao bạn không còn chứng minh được `published=2` và target cuối phản ánh đúng thứ tự version commit? Không cần trông chờ race xuất hiện trong mỗi lần chạy; phân tích interleaving cụ thể.

**Bài 5 – Reader không có latch.** Mở rộng Lab 2 để reader chạy nhiều vòng trong khi writer cập nhật. Nêu các giá trị có thể quan sát trước khi `syncAll` hoàn tất, bao gồm old/new mix. Không xây assertion yêu cầu một tổ hợp race nhất định phải xuất hiện.

**Bài 6 – Snapshot atomic theo request.** Trong Lab 4, đọc `RouteSnapshot` chỉ một lần rồi xử lý cả `first` và `second`. Cho updater chạy nhiều version; chứng minh một record cụ thể luôn chứa cặp giá trị cùng generation, dù các requests độc lập có thể thấy version khác nhau.

**Bài 7 – Volatile vs Mutable.** Đổi `MutableCallSite` ở Lab 1 sang `VolatileCallSite` và bỏ `syncAll`; giải thích volatile semantics. Thực nghiệm tần suất update/throughput chỉ có ý nghĩa nếu bạn benchmark warmup, tránh side effects, đủ luồng và có tiêu chí đo.

**Bài 8 – Null trong batch.** Đưa `null` vào mảng chứa nhiều sites. Vì sao `NullPointerException` không cho phép khẳng định không site nào đã được sync? Thiết kế bước prevalidation.

**Bài 9 – Hot reload.** Một plugin muốn bảo đảm không còn request nào đang chạy target cũ trước khi unload JAR. `syncAll` có đủ không? Đề xuất cơ chế quiescence/in-flight accounting riêng, phân biệt update visibility với hoàn tất các request đã bắt đầu.

**Bài 10 – Review thiết kế.** Cho hệ thống có 1000 sites cập nhật mỗi ngày 1 lần. Mô tả chiến lược batch và lock. Nếu 10 sites cần update mỗi mili-giây, đánh giá `VolatileCallSite` hoặc một `AtomicReference` làm state indirection; phân tích tradeoff ở mức API trước khi microbenchmark.

### 17.1. Checklist học xong

- [ ] Phân biệt rõ `setTarget` là ordinary write, `syncAll` là synchronization của các affected sites.
- [ ] Nêu được reader có thể thấy target mới trước sync và gọi cũ vẫn hoàn tất sau sync.
- [ ] Không tuyên bố `syncAll` làm nhiều sites atomic hoặc chờ mọi request cũ trả về.
- [ ] Bảo vệ `setTarget + syncAll` bằng shared lock khi có nhiều writers.
- [ ] Biết dùng `dynamicInvoker` và hiểu direct handle snapshot từ `getTarget`.
- [ ] Kiểm tra chính xác `MethodType`, null sites và exception.
- [ ] Có chiến lược batching, immutable snapshot và lựa chọn Mutable/Volatile/Constant thích hợp.
- [ ] Chạy và giải thích được output năm lab, đồng thời nêu hạn chế của các kiểm thử concurrency.

## 18. Tài liệu chuẩn Java 21

- [Java SE 21 – MutableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html): contract của `setTarget`, `getTarget`, `dynamicInvoker`, `syncAll`, Java Memory Model details, null và batching.
- [Java SE 21 – VolatileCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target volatile semantics và lý do không có `syncAll`.
- [Java SE 21 – ConstantCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/ConstantCallSite.html): target cố định và `setTarget` unsupported.
- [Java SE 21 – CallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html): `type()` và hợp đồng CallSite.
- [Java SE 21 – MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `type` và các adapter.
- [Java SE 21 – MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `constant`, `dropArguments`, `exactInvoker`.
- [Java Language Specification 21 – `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4): synchronization actions, happens-before và visibility.

**Ghi nhớ:** `MutableCallSite.setTarget` đổi **mục tiêu**, `MutableCallSite.syncAll` đồng bộ **việc các luồng chấp nhận mục tiêu** theo contract JMM; shared writer lock phối hợp **những người cập nhật**, còn immutable snapshot hoặc reader protocol phối hợp **tính nhất quán của nhiều giá trị**. Không chức năng nào trong ba chức năng ấy tự thay thế hoàn toàn cho hai chức năng còn lại.
