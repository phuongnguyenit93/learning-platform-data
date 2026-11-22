# Mô hình singleton, perthis, pertarget và percflow trong vòng đời aspect (AspectJ)

## 1. Vì sao vòng đời aspect là một quyết định kiến trúc?

Trong Aspect-Oriented Programming (AOP), **pointcut** lựa chọn các *join point* mà advice có thể can thiệp, còn **advice** định nghĩa hành vi cắt ngang như metrics, tracing, audit, logging hoặc chính sách thực thi. Một câu hỏi quan trọng nữa là: **instance aspect nào thực hiện advice và sở hữu các trường dữ liệu bên trong aspect?**

AspectJ hỗ trợ các mô hình khởi tạo/liên kết (*instantiation models*):

- **Singleton (`issingleton()` mặc định):** một instance aspect dùng chung trong phạm vi một bản aspect được nạp.
- **`perthis(P)`:** một instance aspect cho mỗi đối tượng `this` đi qua join point khớp `P`.
- **`pertarget(P)`:** một instance aspect cho mỗi đối tượng `target` đi qua join point khớp `P`.
- **`percflow(P)`:** một instance aspect cho mỗi lần đi vào luồng điều khiển động bắt đầu ở join point khớp `P`.

Nếu aspect giữ một trường `count`, với singleton đó có thể là bộ đếm toàn bộ các join point phù hợp, với `perthis` là bộ đếm theo đối tượng đang gọi, với `pertarget` là bộ đếm theo đối tượng nhận lời gọi, còn với `percflow` là trạng thái cho từng lần thực hiện một flow. **Cùng một advice và cùng một field nhưng mô hình instantiation khác nhau sẽ cho cách chia sẻ trạng thái khác nhau.**

Đây là bài học AOP nói chung, dùng cú pháp code-style của AspectJ để minh họa cụ thể. Cú pháp `aspect` và `per...` trong tệp `.aj` cần công cụ biên dịch/weaving AspectJ; chúng không phải cú pháp của Java thuần.

### Những khái niệm phải tách rời

1. **Join point:** một điểm có thể can thiệp trong quá trình thực thi, ví dụ gọi hoặc thực thi phương thức.
2. **Pointcut P trong per-clause:** nơi dùng để tạo/liên kết instance aspect.
3. **Pointcut Q của advice:** nơi advice muốn chạy sau khi có instance tương ứng.
4. **Aspect instance:** object giữ field và thực thi advice; không phải object nghiệp vụ.
5. **Vòng đời:** trạng thái được chia sẻ đến khi nào, khi nào tạo mới và nơi nào có thể truy cập instance.

Việc chọn `perthis` không tự động biến mọi advice thành per-thread. Chọn `percflow` cũng không biến một yêu cầu bất đồng bộ nhiều thread thành một flow liên tục. Để sử dụng đúng, trước tiên phải hiểu `this`, `target` và loại join point.

## 2. `call`, `execution`, `this` và `target`

Xét đoạn Java sau, chỉ mang tính minh họa:

~~~java
class Client {
    void invoke(Worker receiver) {
        receiver.work();
    }
}

class Worker {
    void work() {}
}
~~~

Tại join point `call(void Worker.work())` nằm trong `Client.invoke`:

- `this`: đối tượng `Client` đang thực hiện lời gọi.
- `target`: đối tượng `Worker` nhận lời gọi.

Tại join point `execution(void Worker.work())`:

- `this`: đối tượng `Worker` đang chạy thân `work()`.
- `target`: cũng là đối tượng `Worker` ấy trong trường hợp instance method thông thường.

Vì vậy cùng một chương trình có thể dùng `perthis(call(...))` để tách state theo caller và `pertarget(call(...))` để tách state theo receiver. Nhưng tại nhiều `execution` join point, hai đối tượng trùng nhau, nên hai mô hình có thể cho kết quả phân vùng tương tự.

Điểm gọi từ ngữ cảnh static có thể không có đối tượng `this` phù hợp; pointcut `this(Client)` chỉ match khi ngữ cảnh thật có `Client`. Không dùng tên method, tên kiểu tham số hoặc package để **suy ra quyền bảo mật**. Các cấu trúc này chỉ giúp chọn join point hoặc xác định đối tượng theo hợp đồng.

### Khái niệm cflow

`cflow(P)` bao gồm các join point trong luồng điều khiển động bắt đầu từ P, kể cả điểm P. `cflowbelow(P)` chọn phần dưới P nhưng không bao gồm chính P.

~~~text
Batch.run()       <- bắt đầu P
  step()
  helper()
    step()
Batch.run() về    <- kết thúc flow P
~~~

Đó là phạm vi một chuỗi thực thi đồng bộ còn hoạt động, **không phải** một object tồn tại vĩnh viễn hoặc một request logic tự động lan sang executor/RPC.

## 3. Bảng tổng quan bốn mô hình

| Mô hình | Cú pháp code-style | Khóa liên kết | Tạo instance khi nào? | State đại diện cho |
| --- | --- | --- | --- | --- |
| Singleton | `aspect A { ... }` hoặc `aspect A issingleton() { ... }` | Một bản aspect đã nạp | Khi aspect được khởi tạo trong classloader | Toàn bản aspect |
| Per-this | `aspect A perthis(P) { ... }` | Đối tượng `this` ở join point P | Lần đầu gặp P cho đối tượng chưa liên kết | Một đối tượng đang thực thi/gọi |
| Per-target | `aspect A pertarget(P) { ... }` | Đối tượng `target` ở join point P | Lần đầu gặp P cho target chưa liên kết | Một đối tượng nhận thao tác |
| Per-control-flow | `aspect A percflow(P) { ... }` | Một lần đi vào P | Mỗi lần bắt đầu flow P | Một luồng điều khiển động |

Từ khóa **singleton** ở đây không có nghĩa là chỉ có một instance xuyên nhiều JVM, process hoặc classloader. Mỗi bản aspect được nạp bởi classloader khác nhau có thể có instance singleton riêng.

`perthis` và `pertarget` là các mô hình **per-object**, không phải một aspect cho mỗi lần gọi. Cùng một object được sử dụng nhiều lần sẽ thường dùng lại aspect instance đã liên kết. `percflow` lại có thể có nhiều instance hoạt động lồng nhau trên cùng một thread.

## 4. Singleton: một instance dùng chung

Một aspect không có per-clause là singleton mặc định. Code-style minh họa:

~~~java
// Đoạn AspectJ .aj, không chạy độc lập
aspect Calls {
    private long total;

    before(): call(void Worker.work()) {
        total++;
    }

    public long total() {
        return total;
    }
}
~~~

AspectJ cung cấp accessor `Calls.aspectOf()` để lấy instance. Field `total` được dùng chung cho các join point mà aspect nhận được.

**Phù hợp cho:** cấu hình bất biến, collector metrics dùng chung, utility advice stateless, bảng chính sách không gắn riêng với request.

**Không phù hợp nếu không có đồng bộ hóa:** biến `currentUser`, `requestId`, `transactionState` hoặc một field mutable lưu giá trị của lần gọi hiện tại. Nhiều thread có thể ghi đè nhau, gây đo sai hoặc rò context.

`total++` trong ví dụ không phải phép cộng nguyên tử: đối với cập nhật song song có thể dùng `AtomicLong`/`LongAdder` hoặc cấu trúc synchronized phù hợp. Singleton **không tự thread-safe**; muốn xem tổng toàn hệ thống nhiều instance còn cần tầng tổng hợp bên ngoài.

## 5. `perthis(P)`: một aspect theo đối tượng phía `this`

Ví dụ:

~~~java
// Đoạn AspectJ .aj, không chạy độc lập
aspect ByCaller perthis(
    call(void Worker.work()) && this(Client)
) {
    private int count;

    before(): call(void Worker.work()) && this(Client) {
        count++;
    }

    public int count() {
        return count;
    }
}
~~~

Với hai đối tượng Client `a` và `b`, khi `a` gọi `Worker.work()` lần đầu, AspectJ liên kết một instance `ByCaller` với a. Nếu a tiếp tục gọi cùng hoặc khác Worker, instance đó vẫn được sử dụng. Khi b gọi, một instance khác được liên kết với b.

Ví dụ:

~~~text
a -> Worker X
a -> Worker Y
b -> Worker X

ByCaller của a: 2
ByCaller của b: 1
~~~

Lấy instance đã liên kết bằng `ByCaller.aspectOf(a)` và kiểm tra tồn tại bằng `ByCaller.hasAspect(a)` trong code-style AspectJ. Nếu a chưa đi qua P, chưa chắc có aspect instance; `aspectOf(a)` có thể ném `NoAspectBoundException`.

**Ứng dụng:** thống kê theo caller object, state của một đối tượng chủ động thực hiện thao tác, instrumentation cho các đối tượng caller có vòng đời thực sự phù hợp.

**Cạm bẫy:** nếu a là đối tượng singleton phục vụ mọi khách hàng, `perthis` vẫn chỉ tạo state của một a, **không** phải state riêng cho từng tài khoản. Một đối tượng được chia sẻ giữa nhiều thread cũng làm instance `ByCaller` của nó được chia sẻ và có thể cần synchronization.

## 6. `pertarget(P)`: một aspect theo đối tượng đích

Ví dụ:

~~~java
// Đoạn AspectJ .aj, không chạy độc lập
aspect ByReceiver pertarget(
    call(void Worker.work()) && target(Worker)
) {
    private int count;

    before(): call(void Worker.work()) && target(Worker) {
        count++;
    }

    public int count() {
        return count;
    }
}
~~~

Hai client a và b cùng gọi Worker X, thì instance `ByReceiver` gắn với X ghi cả hai lượt gọi. Nếu b gọi Worker Y, Y có instance aspect khác.

~~~text
a -> X
a -> X
b -> X
b -> Y

ByReceiver của X: 3
ByReceiver của Y: 1
~~~

Truy cập bằng `ByReceiver.aspectOf(X)` sau lần match, hoặc kiểm tra `ByReceiver.hasAspect(X)`.

**Ứng dụng:** theo dõi/chính sách theo đối tượng tài nguyên đích, bộ đếm mỗi repository object hoặc receiver độc lập.

**Cạm bẫy:** per-target là **theo object Java**, không nhất thiết theo tài nguyên logic ở bên ngoài. Hai Worker object có thể cùng tham chiếu một connection pool hoặc một tài khoản remote; việc tạo quota riêng cho từng Worker sẽ không giới hạn tổng tải tới pool/tài khoản đó. Ngược lại, nhiều thread dùng chung một Worker làm state aspect của Worker bị chia sẻ, không tự có mutual exclusion.

### Khi perthis và pertarget giống nhau

Với `execution(void Worker.work())` của instance method, `this` và `target` thường cùng là Worker. Nếu cả hai per-clause chọn execution ấy, cả hai có thể liên kết theo chính Worker. Để chứng minh **sự khác biệt**, ví dụ chạy đầy đủ ở phần sau dùng `call` trong `Client.invoke`, nơi caller và receiver khác nhau.

## 7. `percflow(P)`: một aspect cho mỗi lần vào dynamic control flow

Ví dụ:

~~~java
// Đoạn AspectJ .aj, không chạy độc lập
aspect PerRun percflow(
    execution(void Batch.run(boolean))
) {
    private int steps;

    before(): execution(void Batch.step()) {
        steps++;
    }

    public int steps() {
        return steps;
    }
}
~~~

Mỗi lần vào `Batch.run(boolean)` tạo một **instance PerRun mới**, độc lập với lần vào khác. Khi `Batch.step()` chạy trong flow ấy, advice cập nhật state của instance hiện hành. Tại một vị trí nằm trong flow có thể gọi `PerRun.aspectOf().steps()`.

Khi flow kết thúc, `PerRun.aspectOf()` không còn có instance hiện hành cho flow đó. Gọi ngoài phạm vi có thể ném `NoAspectBoundException`; dùng `PerRun.hasAspect()` khi cần kiểm tra.

### Gọi lồng và đệ quy

~~~text
run(true)         <- tạo F1
  step()          <- F1 đếm 1
  run(false)      <- tạo F2 lồng F1
    step()        <- F2 đếm 1
    step()        <- F2 đếm 2
  return          <- F2 hết hiệu lực; F1 hiện hành
  step()          <- F1 đếm 2
return            <- F1 hết hiệu lực
~~~

Cả F1 và F2 có thể tồn tại trên cùng thread trong cùng khoảng thời gian, nhưng là **hai instance theo hai lần vào P**. Đây là điểm phân biệt với “một aspect cho mỗi thread”.

AspectJ còn có `percflowbelow(P)`: mô hình flow bắt đầu phía dưới điểm P, tương ứng trường hợp muốn loại trừ chính join point entry. Phải phân biệt per-clause dùng để tạo instance với pointcut advice dùng để chọn vị trí chạy.

### Đồng bộ và bất đồng bộ

`percflow` dựa vào **control flow động của quá trình thực thi**. Khi method trả `CompletionStage` hoặc publisher rồi công việc chạy trong thread khác, flow đồng bộ hiện tại có thể đã kết thúc. Aspect instance theo `percflow` không tự lan qua executor, asynchronous callback, message queue hoặc tiến trình khác.

Nếu mục tiêu là trạng thái theo **logical request end-to-end**, hãy thiết kế propagation context độc lập, cleanup và cancellation rõ ràng. Đừng dùng percflow như bằng chứng quyền truy cập hay như một distributed transaction context.

## 8. Ví dụ hoàn chỉnh chạy với AspectJ code-style

Chương trình có hai client, hai worker và hai lời gọi Batch lồng nhau. Kết quả sẽ cho thấy rõ state của từng mô hình. Ví dụ gồm **hai tệp**: Java thường và AspectJ `.aj`, dùng Java 17 cùng công cụ `ajc` tương thích.

### 8.1 Tệp `AspectLifecycleDemo.java`

~~~java
public class AspectLifecycleDemo {
    public static void main(String[] args) {
        Worker shared = new Worker();
        Worker other = new Worker();
        Client a = new Client();
        Client b = new Client();

        a.invoke(shared);
        a.invoke(shared);
        b.invoke(shared);
        b.invoke(other);

        System.out.println("singleton="
            + SingletonMeter.aspectOf().count());
        System.out.println("perthis.a="
            + PerCallerMeter.aspectOf(a).count());
        System.out.println("perthis.b="
            + PerCallerMeter.aspectOf(b).count());
        System.out.println("pertarget.shared="
            + PerTargetMeter.aspectOf(shared).count());
        System.out.println("pertarget.other="
            + PerTargetMeter.aspectOf(other).count());

        new Batch().run(true);
    }
}

class Client {
    void invoke(Worker receiver) {
        receiver.work();
    }
}

class Worker {
    void work() {}
}

class Batch {
    void run(boolean nested) {
        step();
        if (nested) {
            run(false);
        }
        step();

        System.out.println((nested ? "outer=" : "inner=")
            + PerFlowMeter.aspectOf().steps());
    }

    void step() {}
}
~~~

### 8.2 Tệp `LifecycleAspects.aj`

~~~java
aspect SingletonMeter {
    private int calls;

    before(): call(void Worker.work()) && this(Client) {
        calls++;
    }

    public int count() {
        return calls;
    }
}

aspect PerCallerMeter perthis(
    call(void Worker.work()) && this(Client)
) {
    private int calls;

    before(): call(void Worker.work()) && this(Client) {
        calls++;
    }

    public int count() {
        return calls;
    }
}

aspect PerTargetMeter pertarget(
    call(void Worker.work()) && target(Worker)
) {
    private int calls;

    before(): call(void Worker.work()) && target(Worker) {
        calls++;
    }

    public int count() {
        return calls;
    }
}

aspect PerFlowMeter percflow(
    execution(void Batch.run(boolean))
) {
    private int steps;

    before(): execution(void Batch.step()) {
        steps++;
    }

    public int steps() {
        return steps;
    }
}
~~~

### 8.3 Cách build và chạy

Cần JDK 17 và bản AspectJ compiler hỗ trợ Java 17. Hai tệp nằm trong cùng thư mục; môi trường cung cấp lệnh `ajc` và file `aspectjrt.jar`. Ví dụ với shell Unix-like:

~~~bash
mkdir -p out
ajc -17 -d out AspectLifecycleDemo.java LifecycleAspects.aj
java -cp "out:aspectjrt.jar" AspectLifecycleDemo
~~~

Nếu `ajc` chưa nhận runtime từ cấu hình classpath, bổ sung `-classpath aspectjrt.jar` cho lệnh biên dịch; file `aspectjrt.jar` phải nằm tại đường dẫn tương ứng. Windows sử dụng dấu `;` làm dấu phân tách classpath, ví dụ `out;aspectjrt.jar`, và cách tạo thư mục phụ thuộc shell.

Không thay lệnh `ajc` bằng `javac`: Java compiler không hiểu cú pháp `aspect`, và riêng tệp Java cần được build cùng các aspect để nhận các accessor `aspectOf` do AspectJ tạo ra.

**Stdout dự kiến trong lần chạy bình thường:**

~~~text
singleton=4
perthis.a=2
perthis.b=2
pertarget.shared=3
pertarget.other=1
inner=2
outer=2
~~~

**Giải thích:**

1. `a` gọi shared hai lần; `b` gọi shared một lần và other một lần, tổng cộng bốn lời gọi tới `Worker.work()` trong `Client.invoke`. Singleton nhận cả bốn.
2. `perthis` gắn với hai object a và b, mỗi instance đếm hai lượt.
3. `pertarget` gắn với Worker shared và other, lần lượt ba và một lượt.
4. `Batch.run(true)` tạo flow ngoài, gọi `step()` hai lần trong flow của nó. Nó còn gọi lồng `run(false)`; flow trong tạo instance khác và cũng gọi `step()` hai lần. Do print trong flow trong chạy trước khi trở về flow ngoài, các dòng cuối là `inner=2` và `outer=2`.
5. Advice chỉ tăng counter, không in, nên stdout không phụ thuộc thứ tự tương đối giữa các advice tại cùng Worker call join point.

Ví dụ được thiết kế tuần tự một thread và không có exception/callback bất đồng bộ, vì vậy giá trị đếm có thể suy ra một cách xác định. Trong chương trình thật, nhiều thread hoặc pointcut rộng có thể thay đổi số instance, thứ tự, khả năng tranh chấp và lượng trạng thái tồn tại.

## 9. Truy cập instance: `aspectOf` và `hasAspect`

AspectJ code-style cung cấp các accessor sau:

| Mô hình | Lấy instance | Kiểm tra đã có instance |
| --- | --- | --- |
| Singleton | `A.aspectOf()` | `A.hasAspect()` |
| Per-this | `A.aspectOf(caller)` | `A.hasAspect(caller)` |
| Per-target | `A.aspectOf(receiver)` | `A.hasAspect(receiver)` |
| Per-cflow | `A.aspectOf()` trong flow | `A.hasAspect()` trong flow |

**Điểm cần nhớ:** per-object aspect có thể chưa tồn tại nếu đối tượng chưa bao giờ đi qua `P`. Per-cflow aspect có thể không tồn tại ngoài flow P hiện hành. `aspectOf` không tự động tạo một association hợp lệ cho bất kỳ đối tượng/ngữ cảnh tùy ý nào; dùng sai ngữ cảnh có thể nhận `org.aspectj.lang.NoAspectBoundException`.

Aspect trong code-style được quản lý bởi cơ chế AspectJ, không được khởi tạo bằng `new` để cố “gắn” vào target. Với annotation-style aspect biên dịch bằng Java compiler thường, các accessor tạo ở thời điểm compile và tiện ích truy cập có khác biệt; ví dụ ở đây dùng nhất quán code-style `.aj`.

## 10. Per-clause P khác advice pointcut Q

Ví dụ cấu trúc:

~~~java
// Cú pháp AspectJ minh họa, không chạy độc lập
aspect Example pertarget(P) {
    before(): Q {
        // advice tại Q trong ngữ cảnh instance đã liên kết
    }
}
~~~

`P` trong `pertarget(P)` quyết định **đối tượng nào được liên kết với aspect và khi nào association được tạo**. `Q` của `before()` quyết định những join point mà advice muốn chạy. Không thể mặc định advice chạy ở mọi Q nếu chưa có aspect instance thích hợp; cũng không thể coi `perthis(P)` tự động biến Q thành P.

Ví dụ một aspect tạo instance khi method `initialize()` chạy và advice quan sát `process()`. Nếu đối tượng chưa qua `initialize()` mà đã `process()`, advice có thể không chạy do chưa có instance gắn với nó. Điều này có thể là thiết kế mong muốn hoặc lỗi coverage nguy hiểm. Phải test đường gọi đúng.

Trong ví dụ hoàn chỉnh, P và Q được chọn giống nhau để người học quan sát quy tắc dễ hơn. Trong hệ thống lớn, cần mô tả cả P lẫn Q, phạm vi exclude và cách phát hiện thiếu match khi refactor.

## 11. Thời gian sống, bộ nhớ và thread safety

### 11.1 Trạng thái được chia sẻ đến đâu?

- **Singleton:** field có phạm vi bản aspect/classloader. Mọi join point áp dụng có thể chia sẻ state.
- **Perthis/pertarget:** field gắn với object được liên kết. Trạng thái còn có ý nghĩa khi object/association còn tồn tại; vòng đời thu gom phụ thuộc cơ chế runtime và tham chiếu thực tế, không nên tự hứa một thời điểm GC cụ thể.
- **Percflow:** field có ý nghĩa trong một lần flow động đang hoạt động; nested flow có instance riêng, khi ra khỏi flow thì không còn instance hiện hành.

Một aspect per-object không nhất thiết có memory overhead thấp: nếu chương trình tạo hàng triệu object khác nhau và mỗi object chạm P, có thể tạo hàng triệu instance aspect tương ứng. Một percflow trên method đệ quy có thể tạo nhiều instance lồng nhau, cần chú ý allocation và giới hạn độ sâu.

### 11.2 Per-object không tự an toàn đa luồng

Giả sử hai thread cùng gọi Worker shared. `PerTargetMeter.aspectOf(shared)` thuộc một instance chung; `calls++` có nguy cơ mất cập nhật. Tương tự, một Client object dùng chung trên nhiều thread làm perthis instance của nó trở thành shared mutable state.

Với trường hợp counter cần cập nhật nhiều thread, cân nhắc:

~~~java
// Java minh họa, không phải một aspect chạy độc lập
private final java.util.concurrent.atomic.LongAdder calls =
    new java.util.concurrent.atomic.LongAdder();

void onCall() {
    calls.increment();
}

long total() {
    return calls.sum();
}
~~~

`LongAdder.sum()` có thể chỉ là snapshot gần đúng khi có cập nhật đồng thời, nhưng phù hợp cho metrics throughput cao. Với nghiệp vụ cần accounting chính xác theo giao dịch, dùng nguồn dữ liệu/đồng bộ hóa phù hợp hơn.

### 11.3 Singleton và phân tán

Ngay cả singleton aspect cũng không phải global singleton giữa nhiều JVM/process. Nếu cần rate limit toàn cụm, bộ đếm tập trung, hay tổng hợp metrics, bạn cần thêm cơ chế phối hợp hoặc aggregation ngoài process. Chọn per-clause không tự tạo distributed consistency.

## 12. Recursion, async, lỗi và cancellation

**Recursion:** Nếu P là execution của một method đệ quy, mỗi lần đi vào P tạo một flow mới theo `percflow`. Điều này đúng khi mỗi mức cần state riêng, nhưng nếu bạn muốn một logical operation bao cả đệ quy, hãy đánh dấu entrypoint ngoài cùng hoặc truyền context khác. Ví dụ `Batch.run` minh họa nested flow chứ không giả định có một state duy nhất trên cả stack.

**Async:** `CompletableFuture`/`CompletionStage` có thể hoàn tất sau khi method đã trả về, đôi khi trên thread khác. Percflow gắn với control flow đồng bộ không tự kéo dài đến completion. Với publisher nhiều subscriber, một lần tạo publisher và các subscription là những đơn vị khác nhau. Muốn theo dõi lifecycle cần hook vào completion/subscription/terminal và truyền context rõ ràng.

**Exception:** Nếu flow kết thúc do exception, per-flow association hiện hành phải được gỡ đúng quy tắc runtime. Khi viết advice có state, luôn dùng cơ chế cleanup thích hợp; không tự nuốt exception gốc chỉ để cập nhật metric.

**Cancellation:** Hủy future không luôn có nghĩa công việc nền đã dừng. Đừng đưa kết luận quản lý tài nguyên hoặc quyền hạn dựa riêng trên việc `percflow` của method gọi đã kết thúc.

**Bảo mật:** Model gắn instance theo `this`/`target` không chứng minh principal hiện tại hoặc ownership của tài nguyên. Kiểm tra quyền phải dựa vào danh tính đã xác thực, action, resource và context thực tế, không suy quyền từ kiểu hay object đang được instrument.

## 13. Các trường hợp thường chọn sai mô hình

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng singleton field `requestId` | Trộn context giữa các thread | Dùng context scope phù hợp cho từng request |
| Dùng perthis cho user khi Client là singleton | Gộp nhiều user vào một instance | Chọn khóa quyền/user theo context đã xác thực |
| Dùng pertarget làm quota toàn service khi mỗi lần tạo Worker mới | Quota bị chia nhỏ, mất giới hạn toàn service | Dùng một admission controller với phạm vi đúng |
| Dùng percflow cho callback trên executor | Không tìm thấy instance flow hiện hành | Truyền context bất đồng bộ tường minh |
| Dùng perthis trên execution và kỳ vọng phân vùng theo caller khác target | State có thể gắn với target | Chọn call join point và kiểm tra `this/target` |
| Gọi `aspectOf` trước lần match | `NoAspectBoundException` | Dùng `hasAspect` hoặc thiết kế thứ tự rõ |
| Đưa P quá rộng | Tạo instance ngoài phạm vi và tốn bộ nhớ | Rà soát pointcut P và tập match |
| Q match nhưng P chưa khởi tạo association | Advice không có instance phù hợp | Test P và Q riêng |
| `calls++` trong pertarget được nhiều thread dùng | Mất cập nhật | Atomic/adder/synchronization |
| Giả định singleton xuyên nhiều classloader | Sai mô hình state hệ thống | Ghi rõ phạm vi classloader/JVM |

## 14. Checklist kiểm thử và thiết kế

### Singleton

- [ ] Một bản aspect có một instance singleton cho toàn bộ join point trong scope.
- [ ] Các field chia sẻ có đồng bộ hóa phù hợp.
- [ ] Không giữ request/user context ở field toàn cục.

### Perthis

- [ ] Hai caller object khác nhau có hai aspect instance.
- [ ] Một caller gọi nhiều target vẫn dùng instance theo caller.
- [ ] Chọn đúng call/execution join point để `this` có nghĩa dự kiến.
- [ ] Trường hợp chưa qua P được xử lý đúng khi gọi `aspectOf/hasAspect`.

### Pertarget

- [ ] Hai target khác nhau có state riêng.
- [ ] Nhiều caller cùng một target dùng chung state theo target.
- [ ] Tài nguyên ngoài process không bị nhầm với identity object Java.
- [ ] Nhiều thread cùng target không gây race ngoài ý muốn.

### Percflow

- [ ] Mỗi lần vào P tạo state riêng.
- [ ] Nested/recursive flow có instance lồng đúng cách.
- [ ] Trả về hoặc exception kết thúc scope theo lifecycle.
- [ ] `aspectOf()` ngoài flow không bị sử dụng như instance toàn cục.
- [ ] Async callback không mặc định có context percflow.

### Toàn bộ

- [ ] Dùng `ajc` để compile/weave code-style AspectJ, runtime được cung cấp khi chạy.
- [ ] Có integration test qua join point thật, không chỉ unit test class Java.
- [ ] Pointcut P và Q được tài liệu hóa riêng.
- [ ] Đã đo chi phí allocation, contention và số instance ở workload thực.
- [ ] Mọi thay đổi tên method/package/chữ ký được kiểm tra lại độ bao phủ.

## 15. Tài liệu tham khảo chính thức

- [AspectJ Programming Guide – Aspect Instantiation](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): mô hình singleton, per-object và per-control-flow.
- [AspectJ Quick Reference](https://eclipse.dev/aspectj/doc/latest/progguide/quickreference.html): cú pháp per-clause, API `aspectOf` và các pointcut liên quan.

## 16. Kết luận

Bốn mô hình **singleton, `perthis`, `pertarget` và `percflow`** là bốn cách lựa chọn **phạm vi sở hữu trạng thái của aspect**: bản aspect được nạp, đối tượng `this`, đối tượng `target` hoặc một lần đi vào dynamic control flow. Muốn lựa chọn đúng phải hiểu join point là call hay execution, per-clause P có tạo association hay chưa, advice pointcut Q chọn gì, trạng thái có được nhiều thread chia sẻ không, và luồng thực thi có vượt qua ranh giới async không. Ví dụ AspectJ được weave thực sự và bộ test về scope/nested flow là cách xác nhận tốt hơn suy đoán từ tên mô hình.