# Java 7 — Fork/Join: Quản lý pool theo quyền sở hữu

## 1. Phạm vi và mục tiêu

`ForkJoinPool` là một `ExecutorService` dùng cơ chế work-stealing, xuất hiện từ Java 7 và **vẫn là API hiện hành trên Java 17+**. Khó khăn trong một hệ thống thật không chỉ là chia tác vụ bằng `fork()/join()`, mà còn là câu hỏi: **Ai sở hữu pool, ai được quyền gửi việc, ai được quyền shutdown, và khi nào mới được giải phóng tài nguyên?**

Bài này tập trung vào **quản lý pool theo quyền sở hữu (resource ownership)**, không lặp lại toàn bộ bài toán work-stealing.

Sau bài học, bạn có thể:

1. Xác định **owned/private pool**, **borrowed/injected pool**, **application-shared pool** và **JVM common pool**.
2. Giao trách nhiệm khởi tạo, submit, dừng nhận việc, theo dõi tác vụ và giải phóng pool cho đúng cấp.
3. Không shutdown pool được truyền từ nơi khác, pool dùng chung hoặc `ForkJoinPool.commonPool()`.
4. Dùng `shutdown()`, `shutdownNow()`, `awaitTermination()`, `isShutdown()`, `isTerminated()` đúng ngữ nghĩa trên Java 17.
5. Phân biệt **kết thúc một task**, **kết thúc một client/service**, **pool quiescent** và **pool terminated**.
6. Xử lý submit-vs-close race, `RejectedExecutionException`, pending tasks, exceptions, interruption và timeout.
7. Biết vì sao một Java 17 `ForkJoinPool` **không** được đặt trực tiếp trong `try-with-resources` như một `AutoCloseable`; cách dùng phù hợp là tạo wrapper riêng hoặc gọi shutdown/await.
8. Hiểu sự khác nhau của `ForkJoinPool.shutdownNow()` với contract chung của một số executors: trong ForkJoinPool, **danh sách trả về luôn rỗng**.
9. Quản lý `CompletableFuture` có explicit executor và không lẫn việc hoàn tất future với lifecycle của pool.
10. Kiểm thử 10 chương trình Java 17 với stdout rõ, tách invariants ổn định khỏi metrics của scheduler.

**Ngữ cảnh trực tiếp:** Chủ đề cha `Fork/Join`, đề bài `Quản lý pool theo quyền sở hữu`. Chỉ dùng kiến thức còn phù hợp hiện nay; phân biệt chính xác API có trong Java 17 và API bổ sung từ Java 19 trở đi.

## 2. “Quyền sở hữu” nghĩa là gì?

Một pool chứa **worker threads, hàng đợi và công việc còn chờ**. Pool là tài nguyên sống lâu hơn một method call thông thường. Quyền sở hữu trả lời ba câu hỏi:

- **Ai tạo?** Thành phần nào quyết định cấu hình `parallelism`, worker factory, lifecycle.
- **Ai dùng?** Những thành phần nào được submit task và giữ handle Future.
- **Ai hủy/đóng?** Thành phần nào có quyền `shutdown()/shutdownNow()`, và khi nào nó phải đợi các việc đã gửi hoàn tất.

Không nhất thiết “người gọi `submit`” là owner. Một HTTP handler có thể submit work vào pool ứng dụng nhưng **không có quyền đóng pool đó** ở cuối request.

### 2.1. Quy tắc ngắn gọn

**Thành phần tạo và chịu trách nhiệm toàn bộ lifecycle của pool mới được quyền shutdown nó.** Thành phần chỉ **mượn** pool thì trả quyền quản lý lại owner, không “dọn dẹp” pool thay owner.

Đây là **nguyên tắc thiết kế ứng dụng**, không phải cơ chế Java tự cấp quyền. `ForkJoinPool` là đối tượng có method shutdown public; Java type system không tự ngăn borrower gọi nhầm. API/service contract phải hạn chế việc đó.

### 2.2. Mô hình ba cấp

```text
APPLICATION ROOT / COMPOSITION ROOT  <-- OWNER
       |
       +-- creates ForkJoinPool
       |       |
       |       +-- Module A -------- submit/use only (BORROWER)
       |       |
       |       +-- Module B -------- submit/use only (BORROWER)
       |
       +-- stop accepting new business requests
       +-- drain/finish outstanding module work
       +-- shutdown owned pool
       +-- awaitTermination
       +-- release application resources
```

Cấp ứng dụng điều phối thời điểm shutdown. Module A kết thúc trước không được shutdown pool vì Module B còn dùng. Owner không nên tắt pool trong khi modules vẫn có thể submit tùy ý.

## 3. Bốn kiểu sử dụng pool

| Loại | Ai tạo? | Ai có quyền shutdown? | Khi nào phù hợp? |
| --- | --- | --- | --- |
| **Owned private pool** | Component/service tạo riêng | Chính component/service owner | Cần isolation, config và lifecycle riêng |
| **Borrowed/injected pool** | Caller/DI container/owner bên ngoài | **Owner bên ngoài**, không phải borrower | Library/module cần chạy tác vụ trong executor có sẵn |
| **Application-shared pool** | Application root tạo một lần | Application root khi toàn hệ thống dừng | Nhiều modules chia sẻ CPU budget |
| **`ForkJoinPool.commonPool()`** | JVM/JDK quản lý | **Không shutdown từ ứng dụng/library** | CPU work ngắn, phù hợp shared pool và defaults |

### 3.1. “Shared” không đồng nghĩa “không ai sở hữu”

Một custom pool có thể được nhiều services sử dụng. Pool đó **vẫn có một owner** là application root. Không phải cứ shared là mọi thành phần đều vô quyền: owner vẫn chịu trách nhiệm cấu hình, số lượng, stop/drain và báo sự cố.

### 3.2. “Borrowed” không nhất thiết gọi được shutdown

Một constructor nhận `Executor` thay vì `ForkJoinPool` có thể làm rõ contract: người dùng chỉ có thể `execute`, không nhìn thấy `shutdown` qua reference kiểu `Executor`. Nếu cần `submit`/Future, có thể dùng interface application tự định nghĩa hoặc `ExecutorService` với **cam kết không shutdown** ở borrower. Java không tự thực thi cam kết đó.

### 3.3. Common pool là loại đặc biệt

`ForkJoinPool.commonPool()` là pool JVM-wide, dùng chung với một số thư viện/cơ chế xử lý song song. Nó **không thuộc quyền đóng** của từng caller. Java 17 Javadoc nói `shutdown()` và `shutdownNow()` không thay đổi trạng thái chạy của common pool. Tuy chúng có thể không làm gì, vẫn **không nên gọi** như một thao tác cleanup trong library.

## 4. Ownership khác task completion

Một task hoàn tất không chứng minh pool nên đóng. Một module đã gửi xong task không chứng minh những modules khác cũng xong.

```text
Task A completed     -> Future A đã có outcome
Task B completed     -> Future B đã có outcome
Module A finished    -> Module A không gửi thêm công việc
Module B finished    -> Module B không gửi thêm công việc
Pool.shutdown()      -> Owner ngừng nhận thêm submissions
Pool terminated      -> Không còn task chạy hoặc chờ
Application stopped  -> Các dependent resources đã giải phóng
```

Đó là những **sự kiện riêng biệt**.

### 4.1. Hai loại tác vụ trong pool

- **Business tasks:** phép tính/job do ứng dụng yêu cầu; có result, deadline và yêu cầu correctness.
- **Infrastructure/lifecycle tasks:** callback/cleanup/monitoring cần chạy để đóng một service.

Owner phải tính cả hai loại. Nếu đóng pool quá sớm trước khi dependent modules kịp submit cleanup task, logic có thể nhận `RejectedExecutionException` và bỏ dở việc cần thiết.

### 4.2. Drain trước khi đóng

Một workflow shutdown thường là:

1. Dừng nhận **business requests mới** ở lớp trên.
2. Bảo đảm producer/services không còn có thể submit vào pool.
3. Đợi hoặc hủy theo chính sách các business tasks cần thiết.
4. Owner gọi `shutdown()`.
5. Owner `awaitTermination` với deadline.
6. Nếu không dừng đúng hạn, xác định escalation/cancellation policy và báo lỗi nếu tasks vẫn không thoát.

**Không đảo ngược thứ tự** bằng cách shutdown pool trước rồi yêu cầu các modules làm cleanup trên pool ấy.

## 5. Java 17: không đặt ForkJoinPool trực tiếp trong try-with-resources

Trong **Java 17**, `ExecutorService` có khai báo:

```java
public interface ExecutorService extends Executor
```

Đây là phần chữ ký **minh họa** từ API, không phải chương trình standalone. `ExecutorService` **chưa** extends `AutoCloseable` ở Java 17. Method `ExecutorService.close()` và quan hệ `AutoCloseable` được bổ sung **từ Java 19**.

Vì vậy, đoạn sau **không biên dịch với `javac --release 17`**:

```java
try (ForkJoinPool pool = new ForkJoinPool(2)) {
    // Khong co AutoCloseable cho ForkJoinPool theo Java 17.
}
```

Đây là ví dụ **sai có chủ đích**; không chạy độc lập. `ForkJoinPool` chỉ được dùng trực tiếp trong try-with-resources khi compile target/API hỗ trợ như Java 19+, và ngay cả khi đó **chỉ đóng pool mà bạn thực sự sở hữu**.

### 5.1. Mẫu Java 17 đúng

```java
ForkJoinPool pool = new ForkJoinPool(2);
try {
    // Submit, get/join task results.
} finally {
    pool.shutdown();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        // Escalate according to owner policy.
    }
}
```

Đây là mảnh minh họa; cần imports và quản lý `InterruptedException`. Chương trình `OwnedLifecycleDemo` dưới đây chạy độc lập và thể hiện đầy đủ lifecycle.

### 5.2. Wrapper AutoCloseable do bạn tự định nghĩa

Bạn **có thể** tự tạo class `OwnedService implements AutoCloseable` trên Java 17 rồi cho method `close()` của class đó gọi shutdown/await. Đây là **API wrapper do ứng dụng viết**, không phải nói Java 17 đã có `ForkJoinPool.close()`. Xem chương trình `AutoCloseableOwnerDemo` ở phần sau.

## 6. Các trạng thái lifecycle của private pool

`ForkJoinPool` kế thừa `ExecutorService` và cung cấp:

- `shutdown()`: bắt đầu orderly shutdown; không nhận submissions mới, các tasks đã nhận có cơ hội hoàn tất.
- `isShutdown()`: shutdown đã được yêu cầu, **không đồng nghĩa mọi task xong**.
- `isTerminating()`: pool đang trong quá trình kết thúc nhưng chưa terminated.
- `isTerminated()`: sau shutdown, các worker/tasks đã kết thúc.
- `awaitTermination(timeout,unit)`: chờ pool termination hoặc timeout/interruption.
- `shutdownNow()`: cố gắng hủy/dừng tasks để kết thúc nhanh hơn; **không hứa mọi computation đều ngừng ngay**.

### 6.1. Trình tự trạng thái thường gặp

```text
RUNNING
  |  accepts tasks
  |
  +-- shutdown() ------------> SHUTDOWN / TERMINATING
  |                               |  no new work
  |                               |  prior work drains
  |                               v
  |                           TERMINATED
  |
  +-- shutdownNow() --------> attempts cancellation/termination
                                  |  best effort, may take time
                                  v
                              TERMINATED (when no tasks left)
```

Đây là **sơ đồ khái niệm**, không phải public state enum của Java. Đọc `isShutdown/isTerminated` thay vì tự dựng state từ tên worker threads.

### 6.2. shutdown là một bước, không phải chờ

`pool.shutdown()` **trả về ngay**, không tự đợi mọi tác vụ. Nếu thành phần gọi shutdown rồi lập tức dùng result chưa hoàn tất hoặc đóng các resources mà tasks còn cần, có thể lỗi.

### 6.3. awaitTermination chỉ hợp lệ sau khi yêu cầu shutdown

`awaitTermination` chờ pool kết thúc sau shutdown; nếu pool chưa shutdown thì nó không tự khởi tạo shutdown. Đừng dùng nó thay `Future.get` để chờ một business result cụ thể trong lúc pool vẫn hoạt động.

### 6.4. isTerminated khác isQuiescent

`isQuiescent()` nói pool hiện không có việc đang chạy/đang được tìm thấy theo trạng thái runtime. Pool **có thể quiescent nhưng vẫn mở để nhận thêm việc**. `isTerminated()` chỉ true sau khi shutdown và toàn bộ tasks/worker lifecycle đã kết thúc.

## 7. Chương trình A — Owner tạo, sử dụng và đóng private pool

Lưu **`OwnedLifecycleDemo.java`**:

```java
import java.util.concurrent.*;

public final class OwnedLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        int answer = 0;
        boolean rejected = false;

        try {
            Future<Integer> f = pool.submit(() -> 40 + 2);
            answer = f.get(5, TimeUnit.SECONDS);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException("not terminated");
        }

        try {
            pool.submit(() -> 7);
        } catch (RejectedExecutionException e) {
            rejected = true;
        }

        System.out.println("result=" + answer);
        System.out.println("shutdown=" + pool.isShutdown());
        System.out.println("terminated=" + pool.isTerminated());
        System.out.println("rejectNew=" + rejected);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OwnedLifecycleDemo.java
java OwnedLifecycleDemo
```

**Stdout đã kiểm chứng:**

```text
result=42
shutdown=true
terminated=true
rejectNew=true
```

Giải thích:

1. Owner tạo `new ForkJoinPool(2)`; không gọi `commonPool()`.
2. Owner submit một task và chờ `Future.get` để biết business result.
3. Trong `finally`, owner thực hiện `shutdown` và `awaitTermination`.
4. Sau termination, submit task mới bị từ chối bằng `RejectedExecutionException`.
5. Không có module khác mượn pool này, nên thời điểm shutdown không ảnh hưởng consumer bên ngoài.

### 7.1. Không nhầm số 2 với số tasks

`new ForkJoinPool(2)` cấu hình target parallelism 2. Nó không có nghĩa có đúng hai `ForkJoinTask` hoặc luôn có hai workers đang hoạt động. Worker threads thường được tạo/lập lịch theo nhu cầu.

### 7.2. Vì sao catch RejectedExecutionException?

Sau shutdown, yêu cầu submit mới **không được chấp nhận**. Đây là lifecycle contract, không phải phép tính 7 sai. Trong production, phải báo người gọi rằng service đang dừng, không nuốt lỗi rồi tuyên bố request hoàn tất.

## 8. Borrowed pool: borrower không shutdown tài nguyên mượn

Ví dụ một library `ReportService` nhận `ForkJoinPool` từ caller. Library có quyền submit công việc nhưng **không có quyền shutdown**. Nếu library tự đóng pool trong `ReportService.close()`, mọi consumer khác có thể nhận `RejectedExecutionException`, kể cả khi application chưa dừng.

### 8.1. Thiết kế ownership contract

```text
Application owns pool
   |
   +-- new Borrower(pool)
   |       |
   |       +-- calculate() -> pool.submit()
   |       +-- close()     -> closes borrower's state only
   |
   +-- still uses pool
   |
   +-- application shutdowns pool
```

Những điều borrower có thể sở hữu riêng:

- Trạng thái nội bộ của service.
- Đăng ký listeners/callbacks do service tạo.
- Futures của riêng service và cơ chế theo dõi completion.
- Bộ nhớ/đầu vào/đầu ra riêng của service.
- Cờ không nhận yêu cầu mới.

Borrower **không sở hữu** chính worker threads hoặc lifecycle của pool được tiêm vào.

## 9. Chương trình B — BorrowedPoolDemo.java

```java
import java.util.concurrent.*;

public final class BorrowedPoolDemo {
    static final class Borrower implements AutoCloseable {
        private final ForkJoinPool pool;
        private boolean closed;

        Borrower(ForkJoinPool pool) {
            this.pool = pool;
        }

        int calculate(int x) throws Exception {
            if (closed)
                throw new IllegalStateException("borrower closed");
            return pool.submit(() -> x * x)
                    .get(5, TimeUnit.SECONDS);
        }

        public void close() {
            closed = true; // Do not shut down the borrowed pool.
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool ownerPool = new ForkJoinPool(2);

        try {
            Borrower borrower = new Borrower(ownerPool);
            int squared = borrower.calculate(6);
            borrower.close();

            int next = ownerPool.submit(() -> 7)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("square=" + squared);
            System.out.println("poolAliveAfterBorrowerClose=" +
                    (!ownerPool.isShutdown()));
            System.out.println("ownerFollowup=" + next);
        } finally {
            ownerPool.shutdown();
            if (!ownerPool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }

        System.out.println("ownerPoolTerminated=" +
                ownerPool.isTerminated());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BorrowedPoolDemo.java
java BorrowedPoolDemo
```

**Stdout đã kiểm chứng:**

```text
square=36
poolAliveAfterBorrowerClose=true
ownerFollowup=7
ownerPoolTerminated=true
```

### 9.1. Phân tích ownership

Borrower dùng pool để tính `6²=36`, rồi tự close **trạng thái borrower**. Pool vẫn nhận `ownerFollowup=7` từ owner. Chỉ owner trong `finally` mới shutdown và await pool.

### 9.2. Chú ý thread safety

Cờ `closed` đơn giản trong demo chỉ chạy tuần tự trên main thread. Nếu `calculate` và `close` có thể chạy đồng thời từ nhiều threads, phải dùng synchronization/`AtomicBoolean` và quyết định cách xử lý in-flight tasks. Không sao chép Boolean field không đồng bộ vào production concurrent service rồi coi đó là cơ chế đóng thread-safe.

### 9.3. Borrower close không nhất thiết chờ tất cả tasks

Một service có thể cần **drain các Futures của riêng nó** trước khi báo “đã đóng”. Việc chờ đó vẫn không phải `pool.shutdown()`. Cụ thể, borrower có thể ngừng nhận requests mới, đợi các Futures đang chạy, rồi hoàn tất close mà pool vẫn phục vụ modules khác.

## 10. Pool dùng chung cho nhiều modules

Nếu Module A và Module B dùng cùng một pool thuộc application root, A **không được đóng pool khi nó khởi động lại** hoặc khi request A hoàn tất.

Lợi ích của một pool chia sẻ có owner:

- Hạn chế số workers/CPU budget so với mỗi module tạo pool riêng tùy tiện.
- Quản lý tài nguyên tại một chỗ.
- Dễ theo dõi và tắt có điều phối.

Rủi ro:

- Module tạo rất nhiều CPU tasks hoặc blocking tasks có thể ảnh hưởng modules khác.
- Một caller làm shutdown nhầm có thể phá service.
- Nếu owner không có protocol stop/drain, race xảy ra giữa producers và shutdown.

**Ownership rõ không đồng nghĩa isolation.** Khi cần isolation theo SLA hoặc security, owner có thể tạo **nhiều pools**, mỗi pool có giới hạn/lifecycle riêng.

## 11. Chương trình C — SharedPoolCoordinatorDemo.java

```java
import java.util.concurrent.*;

public final class SharedPoolCoordinatorDemo {
    static final class Module {
        final ForkJoinPool pool;

        Module(ForkJoinPool p) {
            pool = p;
        }

        Future<Integer> task(int a) {
            return pool.submit(() -> a + 10);
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool applicationPool = new ForkJoinPool(2);

        try {
            Module alpha = new Module(applicationPool);
            Module beta = new Module(applicationPool);

            Future<Integer> a = alpha.task(1);
            Future<Integer> b = beta.task(2);

            System.out.println("sum=" +
                    (a.get(5, TimeUnit.SECONDS) +
                     b.get(5, TimeUnit.SECONDS)));
            System.out.println("sharedInstance=" +
                    (alpha.pool == beta.pool));
            System.out.println("stillOpenBeforeOwnerShutdown=" +
                    (!applicationPool.isShutdown()));
        } finally {
            applicationPool.shutdown();
            if (!applicationPool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }

        System.out.println("ownerTerminated=" +
                applicationPool.isTerminated());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SharedPoolCoordinatorDemo.java
java SharedPoolCoordinatorDemo
```

**Stdout đã kiểm chứng:**

```text
sum=23
sharedInstance=true
stillOpenBeforeOwnerShutdown=true
ownerTerminated=true
```

Hai modules gửi tasks 11 và 12 vào cùng pool. Cả hai lấy kết quả. Owner quan sát pool còn mở, sau đó mới shutdown. **Module.close** không được dùng để đóng pool chung, trừ khi module đó đồng thời được xác định rõ là **owner duy nhất**.

## 12. Quản lý lifecycle theo service/application scope

Một quy tắc rất hữu ích: **phạm vi sống (lifetime) của pool phải đủ dài để bao tất cả jobs và dependents đang dùng nó.**

| Scope | Pool owner thường phù hợp | Rủi ro cần tránh |
| --- | --- | --- |
| Một algorithm call có workload lớn | Call scope thực sự tạo pool riêng, không borrower | Overhead cao nếu call liên tục |
| Một service instance | Service tạo riêng và quản lý shutdown | Service đóng khi requests còn chạy |
| Nhiều services trong app | Application/DI container | Child service shutdown pool mượn |
| JVM common pool | JVM runtime | Library cố shutdown/đổi global state |
| Một job batch có deadline | Job coordinator tạo pool | Job timeout nhưng tasks vẫn chạy |
| Library nhận Executor | Caller/host | Library tự giả định có quyền shutdown |
| Request handler | Thường là borrower từ app | Mỗi request tạo pool không shutdown |

### 12.1. Một pool mới cho từng request là dấu hiệu cần cân nhắc

Tạo `new ForkJoinPool(8)` cho mỗi HTTP request, rồi request kết thúc không shutdown, tạo leak. Kể cả có shutdown, chi phí tạo workers/pools có thể lớn. Hãy dùng owner theo service/application scope khi nhu cầu đa số requests tương tự nhau và có budget rõ.

### 12.2. Scope trong dependency injection

Nếu DI container tạo singleton pool, hãy gắn lifecycle shutdown vào container/application stop hook, **không đặt trong service dùng pool**.

Nếu framework tạo pool theo từng component instance, component ấy phải có shutdown hook riêng. Phụ thuộc framework, method hủy resource có thể khác; tài liệu này tập trung vào contract Java, không giả định một framework cụ thể.

### 12.3. Dependency order

Nếu Service A cần pool trong lúc đóng để flush/finish work, hãy **đóng A trước**, đợi A xong, rồi đóng pool. Dừng executor trước A là thứ tự sai.

## 13. Shutdown protocol: graceful → deadline → escalation

Java 17 `ExecutorService` Javadoc đưa ra mẫu shutdown hai giai đoạn:

1. `shutdown()` — ngừng nhận việc mới.
2. `awaitTermination(...)` — chờ tasks cũ hoàn tất.
3. Nếu timeout — `shutdownNow()` — best effort cancel/stop.
4. `awaitTermination(...)` lần nữa để biết còn task nào chưa dừng.
5. Nếu thread chờ bị interrupt — xử lý interruption/cancellation, **khôi phục interrupt flag**.

### 13.1. Mẫu helper Java 17

```java
static boolean stopOwnedPool(
        ForkJoinPool pool,
        long gracefulMillis,
        long forcedMillis) {
    pool.shutdown();
    try {
        if (pool.awaitTermination(
                gracefulMillis, TimeUnit.MILLISECONDS)) {
            return true;
        }

        pool.shutdownNow();
        return pool.awaitTermination(
                forcedMillis, TimeUnit.MILLISECONDS);
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đây là **helper minh họa**, cần imports `ForkJoinPool` và `TimeUnit`; chỉ gọi trên **pool mà caller thực sự sở hữu**. Trả false không có nghĩa pool đã terminated; owner phải báo/ghi log và xử lý policy tiếp theo.

### 13.2. Vì sao không chờ vô hạn?

Một task có thể chặn I/O hoặc gặp dependency cycle. Nếu owner chờ mãi, shutdown toàn ứng dụng có thể treo. Deadline phải đến từ application requirements. Không coi thời gian demo `5 seconds` là chính sách dùng được cho mọi job.

### 13.3. Nếu timeout, kết quả công việc ra sao?

Shutdown force là **best effort**, không rollback side effects. Nếu jobs đã ghi vào DB/disk hoặc gửi network requests, application phải có consistency/idempotency handling. Owner phải bảo vệ correctness, không chỉ cố làm `isTerminated=true`.

## 14. awaitTermination không hủy nhiệm vụ đang chờ

`awaitTermination(timeout,unit)` trả:

- `true` nếu pool đã terminated trong thời hạn.
- `false` nếu hết hạn mà chưa terminated.
- Ném `InterruptedException` nếu thread gọi bị interrupt.

Phương thức **không tự gọi `shutdown()`, không cancel pending tasks và không đưa kết quả một business Future cụ thể**.

### 14.1. Chương trình D — AwaitTerminationDemo.java

Ví dụ một worker đang chờ latch do main thread quản lý. Owner yêu cầu orderly shutdown, kiểm pool **chưa** terminated khi task chưa được giải phóng; sau khi release, task kết thúc và pool terminated.

```java
import java.util.concurrent.*;

public final class AwaitTerminationDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> f = pool.submit(() -> {
                entered.countDown();
                release.await();
                return 42;
            });

            if (!entered.await(5, TimeUnit.SECONDS))
                throw new IllegalStateException("task not started");

            pool.shutdown();

            boolean finishedEarly =
                    pool.awaitTermination(
                            40, TimeUnit.MILLISECONDS);

            release.countDown();
            int value = f.get(5, TimeUnit.SECONDS);
            boolean finishedLater =
                    pool.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("shutdown=" + pool.isShutdown());
            System.out.println("finishedBeforeRelease=" +
                    finishedEarly);
            System.out.println("value=" + value);
            System.out.println("finishedAfterRelease=" +
                    finishedLater);
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AwaitTerminationDemo.java
java AwaitTerminationDemo
```

**Stdout đã kiểm chứng:**

```text
shutdown=true
finishedBeforeRelease=false
value=42
finishedAfterRelease=true
```

### 14.2. Phân tích

- Pool có target parallelism 1; task đợi latch.
- `entered.await` đảm bảo task đã vào vùng chờ trước khi main gọi shutdown.
- Khi `release` chưa được count down, task chưa thể kết thúc, nên `awaitTermination(40ms)` trả false.
- Sau khi main giải phóng latch, `Future.get` trả 42, `awaitTermination` trả true.
- Cuối chương trình, finally đảm bảo latch không còn giữ worker nếu gặp exception.

Đây là test **chủ động điều khiển dependency**, không dựa vào random delays để hy vọng thấy task còn chạy.

### 14.3. Blocking trong demo không phải lời khuyên CPU tuning

Task chờ latch được dùng để quan sát lifecycle. Work-stealing không tự giải quyết mọi loại blocking; trong workload thật, tránh chặn nhiều workers lâu hoặc dùng `ManagedBlocker`/I/O executor khi phù hợp.

## 15. shutdownNow của ForkJoinPool: danh sách rỗng!

Một điểm khác biệt cần ghi nhớ khi code gọi qua `ExecutorService`:

- `ExecutorService.shutdownNow()` nói chung cố trả một danh sách tasks chưa bắt đầu; implementation khác nhau.
- **`ForkJoinPool.shutdownNow()` theo Java 17 Javadoc luôn trả danh sách rỗng**, vì pool cố cancel cả tasks đang chạy và chưa chạy để hỗ trợ termination khi có task dependencies.
- Empty list **không chứng minh trước đó không có queued tasks**.
- Không lấy empty list làm danh sách work items cần retry.
- Không khẳng định mọi task đã thực sự ngừng chỉ vì `shutdownNow` trả về.
- Những tasks không đáp ứng cancellation hoặc đang làm I/O/blocking có thể kéo dài termination.

### 15.1. Điều phải theo dõi thay vì danh sách trả về

Owner nên giữ **handles/Futures cho jobs quan trọng**, application job IDs và outcome tracking ở tầng business. Nếu cần retry, phải thiết kế dữ liệu work queue/job store riêng; không trông chờ `shutdownNow` cung cấp đủ công việc chưa xử lý.

## 16. Chương trình E — ShutdownNowContractDemo.java

```java
import java.util.concurrent.*;

public final class ShutdownNowContractDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ForkJoinTask<Integer> active = pool.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return 1;
            });

            if (!entered.await(5, TimeUnit.SECONDS))
                throw new IllegalStateException();

            ForkJoinTask<Integer> queued = pool.submit(() -> 2);
            int returned = pool.shutdownNow().size();

            release.countDown();
            boolean ended = pool.awaitTermination(
                    5, TimeUnit.SECONDS);

            System.out.println("returnedListEmpty=" +
                    (returned == 0));
            System.out.println("isShutdown=" + pool.isShutdown());
            System.out.println("isTerminated=" + ended);
            System.out.println("activeDone=" + active.isDone());
            System.out.println("queuedDone=" + queued.isDone());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ShutdownNowContractDemo.java
java ShutdownNowContractDemo
```

**Stdout đã kiểm chứng:**

```text
returnedListEmpty=true
isShutdown=true
isTerminated=true
activeDone=true
queuedDone=true
```

### 16.1. isDone không có nghĩa task thành công

Sau `shutdownNow()`, một `ForkJoinTask` có thể hoàn tất bình thường, **bị cancel** hoặc hoàn tất bất thường. `isDone()==true` là một **trạng thái kết thúc**, không xác nhận task đã tạo kết quả business. Muốn biết, dùng `isCompletedNormally()/isCancelled()/getException()` hoặc `Future.get` thích hợp.

### 16.2. Không bắt buộc returnedListEmpty là “không còn work”

Khi shutdownNow trả empty, vẫn có thể đã có active/queued tasks trước đó. Test này cố ý tạo active task chờ latch và một queued task. `returnedListEmpty=true` là API behavior của ForkJoinPool, không là một phép đếm tasks.

### 16.3. Vì sao cần giải phóng latch ở finally?

Ngay cả khi cancellation không đánh thức một worker đang chờ theo cách mong đợi, main vẫn count down để tránh giữ thread. Chương trình test **không dùng forced shutdown làm cơ chế rollback hoặc proof-of-interrupt**.

## 17. Task thất bại không mặc nhiên làm pool chết

Một `Callable` hoặc `RecursiveTask` có thể ném exception. Outcome của task thất bại phải được truyền về caller; **pool thường vẫn có thể xử lý các submissions tiếp theo**.

- `Future.get()`: có thể ném `ExecutionException` với `getCause()` là lỗi gốc.
- `ForkJoinTask.join()`: thường truyền unchecked exception/Error, không bọc cùng cách với `get`.
- `isDone()` có thể true cả khi task failed.
- Owner phải quyết định service-level fail-fast, retry hoặc tiếp tục; đó là business policy, không phải để pool tự shutdown mỗi khi một task lỗi.

### 17.1. Pool ownership khác retry policy

Owner có thể để pool còn sống sau một task exception, trong khi caller quyết định retry/job failed. Đừng gọi `pool.shutdown()` trong catch của mỗi business task lỗi; nếu pool shared, sẽ phá tasks khác.

## 18. Chương trình F — FailureIsolationDemo.java

```java
import java.util.concurrent.*;

public final class FailureIsolationDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            Future<Integer> failed = pool.submit(() -> {
                throw new IllegalStateException("bad task");
            });

            boolean cause = false;
            try {
                failed.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                cause = e.getCause()
                        instanceof IllegalStateException;
            }

            int good = pool.submit(() -> 40 + 2)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("failurePropagated=" + cause);
            System.out.println("poolStillRunning=" +
                    (!pool.isShutdown()));
            System.out.println("followupResult=" + good);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FailureIsolationDemo.java
java FailureIsolationDemo
```

**Stdout đã kiểm chứng:**

```text
failurePropagated=true
poolStillRunning=true
followupResult=42
```

Task đầu thất bại, nhưng owner chưa shutdown nên vẫn submit task thứ hai. `ExecutionException.getCause()` cho phép phân loại lỗi riêng; pool không tự biến thành failed service trong trường hợp này.

### 18.1. Khi nào owner nên stop pool do một task lỗi?

Khi lỗi chứng tỏ **shared state/cấu hình không còn an toàn**, chẳng hạn một bất biến hệ thống bị phá. Khi đó owner quyết định dừng cả workload. Không dùng quy tắc “task nào ném RuntimeException là đóng toàn pool” cho mọi ứng dụng.

## 19. Common pool: mượn từ JVM, không sở hữu

`ForkJoinPool.commonPool()` được tạo và quản lý bởi runtime. Nó có thể được sử dụng bởi:

- Các `ForkJoinTask` fork ngoài custom pool.
- Một số hoạt động parallel stream trong JDK.
- `CompletableFuture` async methods không truyền Executor (trong điều kiện JDK quy định).
- Code thư viện hoặc ứng dụng khác.

Vì là global/shared resource, module **không được giả định** những tác vụ khác đã kết thúc khi module mình xong.

### 19.1. Vì sao không shutdown common pool?

JDK 17 quy định:

- `commonPool().shutdown()` và `shutdownNow()` **không đổi trạng thái chạy** như private pool.
- `awaitTermination(...)` đối với common pool có hành vi liên hệ tới `awaitQuiescence` nhưng **luôn trả false** vì common pool không terminate cho tới program shutdown.
- `awaitQuiescence(...)` là sự chờ pool tạm thời không còn hoạt động, **không phải shutdown**.
- Tasks async chạy trên common pool có thể không hoàn tất trước khi JVM kết thúc nếu main thoát; ứng dụng phải chờ tasks quan trọng một cách rõ.

Do đó, borrower chỉ chờ **Futures của mình**, không gọi shutdown/awaitTermination với ý định “dọn sạch common pool”.

### 19.2. Parallelism của common pool không cố định

Cấu hình có thể chịu ảnh hưởng `java.util.concurrent.ForkJoinPool.common.parallelism`, khả năng CPU, runtime và container. Không hardcode parallelism hay thread names vào kết quả test.

### 19.3. Common pool không luôn hợp yêu cầu isolation

Nếu tác vụ của ứng dụng làm CPU nặng lâu hoặc chặn I/O, có thể ảnh hưởng library khác đang dùng common pool. Khi cần bounded queue/CPU budget/SLA, owner có thể tạo private executor và truyền tường minh.

## 20. Chương trình G — CommonPoolBorrowingDemo.java

```java
import java.util.concurrent.*;

public final class CommonPoolBorrowingDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();
        boolean singleton =
                (common == ForkJoinPool.commonPool());

        int answer = common.submit(() -> 6 * 7)
                .get(5, TimeUnit.SECONDS);

        System.out.println("sameCommonPool=" + singleton);
        System.out.println("answer=" + answer);
        System.out.println("commonNotShutdown=" +
                (!common.isShutdown()));
        System.out.println("parallelismPositive=" +
                (ForkJoinPool.getCommonPoolParallelism() >= 1));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CommonPoolBorrowingDemo.java
java CommonPoolBorrowingDemo
```

**Stdout đã kiểm chứng:**

```text
sameCommonPool=true
answer=42
commonNotShutdown=true
parallelismPositive=true
```

Ví dụ **không gọi shutdown** vì caller chỉ dùng pool chung. Khi result đã nhận, module xong; các users khác vẫn có thể submit vào common pool. Không sử dụng chính con số common parallelism làm expected output.

## 21. CompletableFuture và quyền sở hữu executor

`CompletableFuture.supplyAsync(...)`, `thenApplyAsync(...)` có overload **truyền `Executor`**:

```java
CompletableFuture<Integer> future =
    CompletableFuture.supplyAsync(() -> 20, executor)
        .thenApplyAsync(x -> x + 22, executor);
```

Đây là mảnh minh họa. Các stage **sử dụng** executor; `CompletableFuture` hoàn tất không có nghĩa executor phải tự dừng.

### 21.1. Default executor

Theo Java 17 `CompletableFuture` docs:

- Async methods **không truyền executor** thường dùng `ForkJoinPool.commonPool()` khi nó hỗ trợ parallelism ít nhất 2.
- Nếu không, có fallback thread mới cho mỗi async task theo chính sách JDK; subclasses có thể override default executor.
- Không được cho rằng mọi async stage trên mọi runtime đều chắc chắn dùng một pool do module sở hữu.

### 21.2. Explicit executor rõ quyền sở hữu hơn

Khi module nhận `Executor` từ application root, truyền nó vào mọi async stage cần kiểm soát. Root vẫn quản lý lifetime. Module phải **đợi những stage quan trọng** trước khi trả trạng thái completed hoặc để root stop pool.

### 21.3. Quên executor ở stage thứ hai là bug isolation

```java
CompletableFuture.supplyAsync(() -> expensive(), ownedPool)
    .thenApplyAsync(x -> transform(x));
```

Đây là mảnh minh họa; `expensive()/transform()` chưa được định nghĩa. Stage đầu truyền `ownedPool`, stage thứ hai **không truyền executor** nên có thể chạy theo default executor khác. Nếu bạn muốn toàn bộ chain dùng một pool cụ thể, chỉ rõ executor ở các async stages tương ứng.

## 22. Chương trình H — ExplicitCompletableFutureDemo.java

```java
import java.util.concurrent.*;

public final class ExplicitCompletableFutureDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool owned = new ForkJoinPool(2);

        try {
            CompletableFuture<Integer> stage =
                CompletableFuture.supplyAsync(() -> 20, owned)
                    .thenApplyAsync(x -> x + 22, owned);

            System.out.println("pipeline=" +
                    stage.get(5, TimeUnit.SECONDS));
            System.out.println("poolStillOpenAfterFuture=" +
                    (!owned.isShutdown()));
        } finally {
            owned.shutdown();
            if (!owned.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }

        System.out.println("ownerTerminated=" +
                owned.isTerminated());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitCompletableFutureDemo.java
java ExplicitCompletableFutureDemo
```

**Stdout đã kiểm chứng:**

```text
pipeline=42
poolStillOpenAfterFuture=true
ownerTerminated=true
```

`poolStillOpenAfterFuture=true` là điểm cốt lõi: pipeline hoàn tất nhưng **executor vẫn mở** cho đến khi owner shutdown. Đây là tách bạch giữa scope của một async computation và scope của pool.

## 23. Wrapper AutoCloseable có quyền sở hữu thật sự

Nếu cần try-with-resources trên Java 17, hãy gói pool **do class tự tạo và sở hữu** trong một wrapper `AutoCloseable`:

- Constructor tạo `new ForkJoinPool(...)`.
- `submit/calculate` chỉ hoạt động khi service còn open.
- `close` chuyển service sang đóng, gọi `shutdown` và `awaitTermination`.
- Nếu không thể kết thúc đúng hạn, cân nhắc `shutdownNow` theo policy.
- Không expose pool thô cho những callers không được phép shutdown.
- Không “auto-close” pool được inject từ bên ngoài.

### 23.1. Thread-safe close vs service state

Một `AtomicBoolean` có thể bảo đảm đoạn shutdown do wrapper chỉ chạy một lần, nhưng **không tự loại bỏ race giữa submit và close**. Một submit vừa qua cờ kiểm tra vẫn có thể bị pool từ chối vì shutdown xảy ra ngay sau đó. Caller phải được phép nhận `RejectedExecutionException`.

### 23.2. Vì sao wrapper tốt hơn đặt try-with-resources trên pool mượn?

Wrapper thể hiện **ownership rõ ràng**: nó tạo resource nên được quyền dọn. Borrower có thể có AutoCloseable wrapper để dọn state riêng, nhưng **không được hiểu close là shutdown pool** nếu không có ownership.

## 24. Chương trình I — AutoCloseableOwnerDemo.java

Lưu **`AutoCloseableOwnerDemo.java`**. Đây là custom wrapper hoạt động với Java 17:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class AutoCloseableOwnerDemo {
    static final class OwnedService implements AutoCloseable {
        private final ForkJoinPool pool = new ForkJoinPool(2);
        private final AtomicBoolean closed = new AtomicBoolean(false);

        Future<Integer> calculate(int x) {
            if (closed.get())
                throw new RejectedExecutionException(
                        "service closed");
            return pool.submit(() -> x * x);
        }

        public void close() throws InterruptedException {
            if (!closed.compareAndSet(false, true)) return;

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                    throw new IllegalStateException(
                            "pool did not terminate");
            }
        }

        boolean terminated() {
            return pool.isTerminated();
        }
    }

    public static void main(String[] args) throws Exception {
        OwnedService owner = new OwnedService();
        int result;

        try (owner) {
            result = owner.calculate(7)
                    .get(5, TimeUnit.SECONDS);
        }

        boolean denied = false;
        try {
            owner.calculate(1);
        } catch (RejectedExecutionException e) {
            denied = true;
        }

        owner.close();

        System.out.println("result=" + result);
        System.out.println("terminated=" + owner.terminated());
        System.out.println("rejectAfterClose=" + denied);
        System.out.println("idempotentClose=true");
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AutoCloseableOwnerDemo.java
java AutoCloseableOwnerDemo
```

**Stdout đã kiểm chứng:**

```text
result=49
terminated=true
rejectAfterClose=true
idempotentClose=true
```

### 24.1. Điểm cốt lõi

`OwnedService` tự tạo pool, vì vậy chính nó được quyền shutdown. `try(owner)` hợp lệ trên Java 17 vì **OwnedService implements AutoCloseable**, không phải vì `ForkJoinPool` đã có `close()`.

### 24.2. Vì sao close được gọi hai lần?

`AtomicBoolean.compareAndSet(false,true)` chỉ cho đoạn dọn tài nguyên chạy một lần. Gọi `close` lần nữa không shutdown lại pool. Tuy nhiên, wrapper **không phải một production lifecycle framework** đầy đủ: concurrent close/submit, interruption, task deadlines và quá hạn dừng cần policy chi tiết hơn.

### 24.3. Interruption khi wrapper đang close

`close()` trong demo khai báo `throws InterruptedException`. Nếu caller bị interrupt, try-with-resources sẽ propagate lỗi tới caller; ứng dụng cấp cao hơn cần quyết định việc force cancel và giữ interrupt flag. Với production owner, có thể dùng mẫu hai giai đoạn đã trình bày và chịu trách nhiệm cleanup/exception reporting rõ.

### 24.4. Không close pool từ chính worker đang chạy của pool

Nếu task trên pool gọi wrapper.close() rồi chờ pool terminate, nó đang chờ **chính thread/task còn đang chạy** kết thúc; có thể tự chờ đến timeout hoặc dẫn đến deadlock logic. Chỉ thực hiện pool shutdown từ lifecycle controller **bên ngoài các tasks mà pool cần đợi**.

## 25. Cancellation thuộc task, shutdown thuộc pool

**Cancellation của một task không giống shutdown toàn pool.**

`ForkJoinTask.cancel(true)` làm task chuyển sang trạng thái hủy theo contract, nhưng không cam kết ngắt tức thì mọi computation đang chạy. Hành vi interrupt trong ForkJoinTask không giống cách người dùng thường tưởng ở một `FutureTask` blocking.

Một caller có thể hủy job **của mình** mà pool vẫn phục vụ jobs khác. Không vì một request timeout mà shutdown executor dùng chung.

### 25.1. Các trạng thái cần phân biệt

| Trạng thái | Tác động lên ai? |
| --- | --- |
| `task.cancel(true)` | Một task handle |
| `future.get(timeout)` hết hạn | Caller chưa nhận result đúng hạn; task có thể tiếp tục |
| `pool.shutdown()` | Toàn pool, từ chối new submissions |
| `pool.shutdownNow()` | Toàn pool, best-effort cancellation/termination |
| `pool.isTerminated()` | Toàn pool đã dừng |
| `Borrower.close()` | Trạng thái borrower; **không tự đóng pool mượn** |
| `commonPool().awaitQuiescence(...)` | Chờ quiescence; **không shutdown common pool** |

### 25.2. Cancellation và side effects

Nếu task đã ghi database, upload một phần file hoặc gửi HTTP request, cancel không làm rollback. Owner phải dùng idempotency, transaction boundary hoặc compensation khi nghiệp vụ cần.

## 26. Chương trình J — CancellationOwnershipDemo.java

```java
import java.util.concurrent.*;

public final class CancellationOwnershipDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            ForkJoinTask<Integer> neverSubmitted =
                    new RecursiveTask<>() {
                protected Integer compute() {
                    return 42;
                }
            };

            boolean success = neverSubmitted.cancel(true);
            boolean cancelled = neverSubmitted.isCancelled();
            boolean threw = false;

            try {
                neverSubmitted.join();
            } catch (CancellationException e) {
                threw = true;
            }

            System.out.println("cancelSucceeded=" + success);
            System.out.println("isCancelled=" + cancelled);
            System.out.println("joinThrowsCancellation=" + threw);
            System.out.println("poolStillOwnedAndOpen=" +
                    (!pool.isShutdown()));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CancellationOwnershipDemo.java
java CancellationOwnershipDemo
```

**Stdout đã kiểm chứng:**

```text
cancelSucceeded=true
isCancelled=true
joinThrowsCancellation=true
poolStillOwnedAndOpen=true
```

### 26.1. Giới hạn bài test

Task `neverSubmitted` chưa hề chạy; cancel đặt trạng thái hủy, `join` ném `CancellationException`. Vì vậy **không thể** dùng demo này để kết luận `cancel(true)` ngắt một CPU task đang chạy. Nó chỉ xác minh **hủy task không làm shutdown pool**.

## 27. Submit song song với shutdown: race hợp lệ

Một ứng dụng nhiều threads có thể có lịch:

```text
Thread A (request)             Thread B (owner)
      |                              |
checks service is open              |
      |                         begins shutdown
calls pool.submit(...)               |
      |                              |
RejectedExecutionException          |
```

Ngay cả khi request kiểm `!pool.isShutdown()` trước submit, trạng thái có thể đổi giữa hai lệnh. Đây là **TOCTOU race**; không thể chỉ dùng một check Boolean trước đó để bảo đảm submit luôn được chấp nhận.

### 27.1. Protocol đóng an toàn

Một thiết kế tốt thường có:

1. Owner chuyển service state sang `STOPPING`, ngừng nhận requests mới.
2. Các producers/schedulers dừng gửi tasks.
3. Owner đợi các submissions đã chấp nhận/in-flight tasks theo policy.
4. Owner shutdown pool.
5. API submit vẫn sẵn sàng báo `RejectedExecutionException` nếu race xảy ra.

Có thể dùng lock, atomic state và ref-count/phaser/structured lifecycle để điều phối, nhưng cần tránh giữ lock trong lúc chờ task cũng cần lock đó.

### 27.2. Borrower không được tự mở lại pool đã shutdown

`ForkJoinPool` không có API reset trạng thái lifecycle để biến một pool terminated thành running. Nếu owner cần restart service, tạo **pool instance mới**, cập nhật dependencies dưới một cơ chế handoff an toàn.

### 27.3. Không nuốt RejectedExecutionException

Một task không được nhận vào pool **không có Future thành công**. Caller phải báo service unavailable, retry khi có owner mới hoặc chuyển workload theo business policy; không ghi log rồi trả response thành công giả.

## 28. Khi một module sở hữu task nhưng không sở hữu pool

Một module có thể chịu trách nhiệm outcome của chính các Futures của nó:

- Gán ID cho jobs, lưu result handles.
- Không tạo thêm jobs sau khi module stop.
- Đợi jobs bắt buộc hoàn tất hoặc cancel theo policy.
- Đóng/giải phóng input/output riêng của module sau khi jobs không còn sử dụng chúng.
- Không gọi `pool.shutdown` trên injected executor.
- Báo owner nếu module chưa drain được trước deadline.

### 28.1. Mô hình tách hai quyền

```text
Borrower controls:
   its own pending jobs/Futures
   its own state and data
   its own acceptance policy
   its own deadlines

Owner controls:
   pool creation/configuration
   pool-wide task admission
   pool shutdown and termination
   shared pool metrics
   replacement pool on restart
```

Điều này đặc biệt quan trọng khi modules có lifecycle khác nhau nhưng cùng một pool.

### 28.2. Không đưa pool trực tiếp vào public API nếu không cần

Nếu module chỉ cần chạy `Runnable`, nhận `Executor`. Nếu cần trả `Future` có thể tiêm một interface ứng dụng riêng (`TaskScheduler` với method `submit`), giới hạn người dùng không gọi shutdown. Đừng expose `ForkJoinPool` nguyên đối tượng ra mọi tầng một cách tùy tiện.

## 29. Blocking workloads và trách nhiệm của owner

Work-stealing giúp workers rảnh lấy tasks khác, nhưng **không làm mọi blocking operation trở nên non-blocking**. Nếu nhiều tasks chờ network/database, pool có thể thiếu workers để xử lý CPU tasks khác.

### 29.1. Chọn pool theo workload

- CPU-bound fork/join decomposition: `ForkJoinPool` thường phù hợp.
- Blocking I/O có concurrency lớn: nên cân nhắc executor được quản lý riêng hoặc async I/O framework.
- Workload pha trộn: owner có thể cần pools riêng để tránh một nhóm jobs ảnh hưởng nhóm khác.
- Một vài blocking operations có thể dùng `ForkJoinPool.ManagedBlocker` để thông báo việc chờ; cơ chế bù workers không được đảm bảo cho mọi tình huống.

### 29.2. Owner phải tính tổng tài nguyên

Nếu mỗi module tạo riêng pool parallelism=16 trên máy 8 cores, các workers có thể cạnh tranh CPU, tăng scheduling/cache overhead. Ownership tập trung cho phép kiểm CPU budget, số tasks đang chờ và khả năng quan sát.

### 29.3. Không dùng pool để che deadlocks

Nếu một task giữ lock rồi chờ `join` vào task cần cùng lock, pool không thể sửa dependency cycle bằng steals. Cần sửa dependency graph. ShutdownNow cũng không phải cơ chế sửa một deadlock logic đáng tin.

## 30. Metrics dành cho owner, không phải sự thật bất biến

`ForkJoinPool` cung cấp nhiều chỉ số phục vụ giám sát:

| Metric | Ý nghĩa |
| --- | --- |
| `getParallelism()` | Target parallelism |
| `getPoolSize()` | Số workers đã được tạo và chưa kết thúc |
| `getActiveThreadCount()` | Ước lượng số workers active |
| `getRunningThreadCount()` | Ước lượng số workers đang chạy, không bị chặn theo định nghĩa |
| `getQueuedTaskCount()` | Ước lượng tasks trong local queues |
| `getQueuedSubmissionCount()` | Ước lượng external submissions chờ |
| `getStealCount()` | Ước lượng số tasks được worker khác thực thi |
| `isShutdown()` | Pool đã được yêu cầu shutdown |
| `isTerminating()` | Đang chuyển trạng thái kết thúc |
| `isTerminated()` | Pool đã kết thúc |

Các số đếm **thay đổi theo thời điểm đo** và là estimates; owner dùng chúng để quan sát, không ép exact counts vào CI hay logic phân quyền. Pool termination phải dựa `isTerminated/awaitTermination`, không dựa `getPoolSize()==0` do một phép đo thoáng qua.

### 30.1. Không đoán số steals

Cùng một workload có thể không steal task nào trên một lần chạy và steal vài tasks lần khác. Không dùng `getStealCount()>0` để tuyên bố pool healthy.

### 30.2. Monitor shutdown stalled

Nếu `isTerminating()` còn true rất lâu sau shutdown, có thể tasks không phản ứng với interrupt, đang chặn I/O hoặc dependency deadlock. Owner cần logs, thread dumps và cơ chế điều phối cleanup; không tăng parallelism vô điều kiện để che vấn đề.

## 31. Parallel streams và hidden use of commonPool

`parallelStream()` hoặc `stream().parallel()` thường dùng cơ chế Fork/Join trong JDK. Library không nên tự shutdown common pool chỉ vì nó đã chạy một parallel stream.

Một số rủi ro:

- Hidden CPU load ảnh hưởng các modules khác chia sẻ commonPool.
- Blocking actions bên trong parallel stream có thể gây starvation.
- Đặt code parallel stream bên trong custom ForkJoinPool không nên được coi là cam kết API portable rằng mọi stage luôn chạy trong pool ấy theo ý muốn ứng dụng.
- Side effects dùng chung và thứ tự xử lý cần được thiết kế thread-safe.

Với nhu cầu **explicit ownership**, dùng `ForkJoinTask`/`RecursiveTask` trong owned pool hoặc API hỗ trợ explicit Executor; không dựa vào tác dụng phụ của thread-local scheduling.

## 32. Khi nào không nên tạo ForkJoinPool mới?

Đừng tạo private pool chỉ vì code đang gọi `CompletableFuture` hoặc muốn “async” cho một tác vụ nhỏ. Hãy cân nhắc:

- Workload CPU có đủ lớn để chia?
- Có cần isolation/SLA?
- Shared pool hiện tại có đủ budget?
- Ai sẽ shutdown pool?
- Bao nhiêu instances service có thể được tạo?
- Nếu request bị cancel, ai xử lý in-flight tasks?
- Cần monitoring, metrics, config và owner readiness?
- Nếu pool không đóng được, ứng dụng có báo failure đúng không?

Ví dụ CPU loop nhỏ có thể chạy tuần tự nhanh hơn. Tạo pool cho từng request có thể gây resource overhead còn lớn hơn tác vụ.

### 32.1. Thời gian sống quá ngắn

Nếu tạo pool, submit một phép tính 2ms rồi shutdown ngay, chi phí tạo/dọn workers có thể không đáng. Có thể dùng pool theo service/application scope hoặc lời gọi tuần tự.

### 32.2. Thời gian sống quá dài

Nếu một private pool vẫn sống sau khi toàn component đã dừng, đó có thể là leak. Owner phải có cleanup hook, test lifecycle và logs.

### 32.3. Dùng chung quá mức

Một pool JVM-wide cho mọi tác vụ CPU/I/O không chắc phù hợp nếu workload khác biệt. Quyền sở hữu tập trung phải đi kèm phân loại workload và capacity planning.

## 33. Xử lý interruption của owner thread

`awaitTermination` ném `InterruptedException` khi caller bị interrupt. Nếu phương thức dọn dẹp muốn trả về mà không ném exception, một pattern phổ biến:

```java
try {
    pool.shutdown();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là mảnh minh họa. Nó **không** đợi lần thứ hai sau forced shutdown; production shutdown policy cần theo dõi termination và báo trạng thái không hoàn tất. Việc khôi phục interrupt flag bảo vệ tín hiệu hủy của caller.

### 33.1. Không nuốt interrupt

`catch (InterruptedException e) { }` làm mất yêu cầu hủy, có thể khiến ứng dụng không kết thúc đúng hạn. Nếu không propagate, ít nhất phải khôi phục interrupt status và thực thi cancellation policy.

### 33.2. Không giải phóng tài nguyên phụ thuộc quá sớm

Nếu tasks còn đang dùng file handle/database session/byte buffer, owner không thể đóng các tài nguyên này một cách tùy tiện ngay khi gọi `shutdownNow()`. Cần cân nhắc tính nhất quán và thứ tự cleanup.

### 33.3. Exception từ cleanup cần được báo

Nếu `awaitTermination` không kết thúc, đừng tự ghi “shutdown successful”. Có thể ghi trạng thái partial shutdown, cảnh báo và giữ diagnostic data. Trường hợp thực tế có thể cần orchestration/hard stop của cả process, tùy nghiệp vụ.

## 34. Failure và cancellation trong một shared pool

Một service có thể thất bại, nhưng pool vẫn phục vụ service khác. Hãy phân biệt:

- **Task failure:** một Future exceptional, xử lý ở job level.
- **Service failure:** service ngừng nhận jobs, báo owner; pool có thể còn.
- **Pool failure/lifecycle stop:** owner chủ động shutdown pool, các producers phải dừng.
- **Application stop:** các modules, network, scheduler và pool dừng theo dependency order.
- **Process failure:** JVM crash; không có bảo đảm shutdown hooks luôn chạy.

### 34.1. Không làm global recovery trong một task

Một task catching exception không nên gọi `ForkJoinPool.commonPool().shutdownNow()` hoặc đóng shared pool. Nó không sở hữu các resources đó.

### 34.2. Yêu cầu idempotency khi retry

Nếu task nửa chừng đã ghi state rồi bị cancel hoặc executor shutdown, retry có thể lặp side effects. Owner/caller phải thiết kế idempotency keys, transaction boundaries hoặc compensation.

### 34.3. Không xem cancel(true) là ngắt tức thì

`ForkJoinTask.cancel` không bảo đảm CPU task đang chạy bị interrupt giống mọi implementation của `FutureTask`. Đừng xây correctness trên việc chắc chắn không còn side effects sau `cancel(true)`.

## 35. CommonPool và application startup/shutdown

Trong một ứng dụng lớn, shared common pool là resource global JVM-level. Bạn có thể dùng nó cho việc phù hợp, nhưng không điều khiển lifecycle tùy ý.

**Khuyến nghị:**

- Với thư viện, nhận `Executor` từ caller nếu cần isolation.
- Nếu dùng commonPool mặc định, nói rõ vào API contract.
- Không gọi `shutdown` hoặc `shutdownNow` từ library.
- Chờ Futures của mình khi chúng quan trọng trước khi ứng dụng exit.
- Quan sát common parallelism từ runtime nếu cần, không hardcode.
- Tránh blocking lâu và code không phản ứng interruption trong common pool.
- Không dùng `awaitTermination` của common pool như một cách đóng nó.

### 35.1. awaitQuiescence không chuyển quyền sở hữu

`commonPool().awaitQuiescence(timeout,unit)` có thể giúp chờ trạng thái rảnh, nhưng không làm pool trở thành owned/private. Các modules khác có thể submit sau đó. Chờ “rảnh” không thay thế chờ **những Futures thuộc về module mình**.

### 35.2. ForkJoinPool.commonPool không nên là single point of truth cho mọi job

Nếu cần audit/business tracking, lưu job IDs và outcomes ở tầng application. Pool metrics/task queues không phải persisted job scheduler đáng tin.

## 36. Bảng kiểm tra Java 17: 10 chương trình đã chạy

| Chương trình | Contract kiểm tra | Kết quả đáng chú ý |
| --- | --- | --- |
| `OwnedLifecycleDemo` | Owner gọi shutdown + await | result42, terminated=true, rejectNew=true |
| `BorrowedPoolDemo` | Borrower.close không shutdown pool | square36, ownerFollowup7 |
| `SharedPoolCoordinatorDemo` | Hai modules dùng pool ứng dụng | sum23, sharedInstance=true |
| `AwaitTerminationDemo` | Task chưa xong làm await false | false trước release, true sau |
| `ShutdownNowContractDemo` | FJP shutdownNow trả empty list | returnedListEmpty=true, task handles done |
| `FailureIsolationDemo` | Task fail không tự giết pool | cause true, followup42 |
| `CommonPoolBorrowingDemo` | Mượn common pool, không shutdown | answer42, commonNotShutdown=true |
| `ExplicitCompletableFutureDemo` | CF stages dùng explicit owner pool | pipeline42, pool sống đến owner close |
| `AutoCloseableOwnerDemo` | Java17 app wrapper sở hữu và close | result49, idempotent close |
| `CancellationOwnershipDemo` | Cancel task khác shutdown pool | cancelled true, pool still open |

Các ví dụ được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK hiện đại, không cần Internet, không sửa tài nguyên hệ thống khác. Với lifecycle, mọi deadline là **giới hạn minh họa cho kiểm thử**, không phải yêu cầu các hệ thống production đều phải chờ 5 giây.

### 36.1. Vì sao không assert exact worker count?

Number of worker threads, steal counts, actual schedules và task execution order có thể thay đổi theo OS, machine/JVM. Bài kiểm tra assertion **ownership và results**, không giả định scheduler tạo đủ workers cụ thể.

## 37. Những anti-pattern cần tránh

1. **Service chỉ nhận pool từ constructor mà gọi shutdown trong close.** Nó không sở hữu pool.
2. **HTTP request tạo pool mới nhưng không shutdown.** Leak.
3. **Một module ngừng hoạt động nên shutdown commonPool.** Sai scope ownership.
4. **Chỉ đợi Future rồi nghĩ pool đã terminated.** Future completion khác pool lifecycle.
5. **Gọi shutdown rồi tiếp tục submit cleanup tasks.** Submit bị từ chối.
6. **Gọi shutdownNow để rollback side effects.** Cancellation không rollback.
7. **Dùng danh sách trả về của ForkJoinPool.shutdownNow làm danh sách pending jobs.** API trả empty list.
8. **Giả định cancel(true) chắc chắn interrupt worker.** Không có bảo đảm tổng quát.
9. **Coi isDone=true là task thành công.** Cancel/failed cũng done.
10. **Coi isShutdown=true nghĩa mọi workers xong.** Cần isTerminated/awaitTermination.
11. **Coi isQuiescent=true nghĩa pool đóng.** Pool có thể vẫn accept tasks.
12. **Gọi awaitTermination trước shutdown để chờ một Future.** Sai mục đích.
13. **Không kiểm kết quả awaitTermination.** Có thể không dừng đúng hạn.
14. **Nuốt InterruptedException.** Mất tín hiệu hủy.
15. **Không điều phối submit-vs-shutdown.** Race và RejectedExecutionException.
16. **Mở private pool per request cho CPU task cực nhỏ.** Overhead.
17. **Mỗi module cấu hình parallelism bằng số cores rồi chạy đồng thời.** Oversubscription.
18. **Cho blocking network/database workloads vào FJP CPU shared.** Starvation.
19. **Giữ lock trong khi join task cần lock.** Deadlock.
20. **Dùng thread names để xác định quyền ownership.** Không hợp lệ.
21. **Quên await business Futures khi app exit.** Có thể mất kết quả.
22. **Đóng file/DB resources trước khi tasks ngừng dùng.** Race dữ liệu.
23. **Đặt ForkJoinPool trực tiếp vào try-with-resources với --release17.** Không có AutoCloseable ở Java17.
24. **Dùng wrapper AutoCloseable rồi close cả injected pool.** Vẫn vi phạm ownership.
25. **Gọi close wrapper từ chính worker pool cần đợi.** Có thể tự chờ/deadlock.
26. **Assume CompletableFuture completed thì executor tự shutdown.** Không.
27. **Quên truyền executor ở một async stage khi muốn isolation.** Stage dùng default.
28. **Coi common pool parallelism là hằng số cố định.** JVM/env configurable.
29. **Dựa vào metrics getStealCount để đếm job đã commit.** Chỉ metric ước lượng.
30. **Kết luận force shutdown thành công dù awaitTermination trả false.** Chưa hoàn tất.

## 38. Bài tập và đáp án gợi ý

**Bài 1.** Một module nhận `ForkJoinPool` từ DI container. Ai shutdown? **Container/application owner**, không phải module.

**Bài 2.** Một service tự tạo private pool trong constructor. Ai shutdown? **Service** khi lifecycle kết thúc.

**Bài 3.** Hai modules A và B dùng một pool. A đã xong, B còn task. A được gọi shutdown không? **Không**.

**Bài 4.** Common pool có ai sở hữu? **JVM runtime**; library không shutdown.

**Bài 5.** `pool.shutdown()` có block cho đến khi tasks xong? **Không**, dùng awaitTermination/Futures.

**Bài 6.** `pool.isShutdown() == true` có chứng minh tasks hoàn tất? **Không**.

**Bài 7.** `pool.isTerminated() == true` có thể xảy ra trước shutdown không? **Không**, cần shutdown trước.

**Bài 8.** `pool.isQuiescent()==true` có thể vẫn nhận task mới? **Có**, nếu pool chưa shutdown.

**Bài 9.** `awaitTermination(10,SECONDS)` trả false nghĩa là gì? **Chưa terminated trước deadline**.

**Bài 10.** `shutdownNow()` của ForkJoinPool trả list rỗng, nghĩa là trước đó không có queued jobs? **Không**.

**Bài 11.** Một task failed với RuntimeException, owner bắt buộc shutdown cả pool? **Không**, tùy business policy.

**Bài 12.** Module đang dùng pool shared nhận `RejectedExecutionException` khi shutdown? **Báo service stopping/cancel theo policy**, không giả success.

**Bài 13.** Vì sao precheck `!isShutdown()` không đảm bảo submit thành công? **Race giữa check và submit**.

**Bài 14.** Sau pool shutdown, muốn tiếp tục dùng cho đợt jobs mới, gọi restart() được không? **Không**, tạo pool instance mới.

**Bài 15.** Request bị timeout, có nên shutdown pool ứng dụng? **Không**, quản lý task handle và job cancellation.

**Bài 16.** Task `cancel(true)` có chắc chắn ngừng ngay mọi side effects? **Không**.

**Bài 17.** ForkJoinTask isDone==true có luôn success? **Không**, có cancelled/exception.

**Bài 18.** CompletableFuture stage xong có tự đóng executor được truyền vào không? **Không**.

**Bài 19.** CompletableFuture chain có stage không truyền executor, có chắc mọi stage đều vào private pool ban đầu? **Không**.

**Bài 20.** Một library chỉ cần execute(Runnable), nên nhận kiểu gì để hạn chế quyền? **Executor** hoặc interface tối thiểu.

**Bài 21.** `try(ForkJoinPool p = new ForkJoinPool(2))` có dùng được với --release17? **Không**.

**Bài 22.** `try(OwnedService owner = ...)` khi OwnedService tự implements AutoCloseable có dùng được ở Java17? **Có**.

**Bài 23.** AutoCloseable wrapper có thể đóng pool được inject từ ngoài không? **Không**, trừ khi ownership được chuyển giao rõ ràng và độc quyền.

**Bài 24.** Khi wrapper.close bị gọi hai lần, muốn bảo đảm cleanup chạy một lần dùng gì? **AtomicBoolean/CAS hoặc đồng bộ lifecycle**.

**Bài 25.** AtomicBoolean đủ loại bỏ race giữa submit và close không? **Không**; phải chấp nhận/có protocol cho RejectedExecutionException.

**Bài 26.** Có nên close pool từ một task đang chạy trên chính pool đó? **Không**, có thể chờ chính nó.

**Bài 27.** Vì sao không lấy `getStealCount` làm số jobs hoàn tất? **Chỉ đo work-stealing, là estimate**.

**Bài 28.** Common pool awaitTermination có thể dùng để đợi nó terminate trước JVM exit? **Không**, common pool không terminate thông thường; method trả false.

**Bài 29.** Dùng commonPool cho blocking I/O trong thư viện có thể ảnh hưởng ai? **Những users khác của common pool**.

**Bài 30.** Vòng đời shutdown hợp lý cho server là gì? **Stop ingress → stop producers → drain tasks → owner shutdown → await → escalate nếu cần**.

**Bài 31.** Nếu worker vẫn đang giữ file handle, có nên force-close file ngay sau shutdownNow không? **Không nếu cần correctness**; phải quản lý outstanding task và resource order.

**Bài 32.** Một component có quyền hủy Future của chính nó nhưng không quyền shutdown pool, có mâu thuẫn không? **Không**, hai scope khác nhau.

**Bài 33.** Vì sao pool per-request không phải mặc định tốt? **Worker startup/GC/resource overhead, khó lifecycle, có nguy cơ leak**.

**Bài 34.** Cần xác nhận business result của task thất bại, nhìn gì? **Future.get cause/isCompletedNormally/getException hoặc outcome app**, không chỉ pool metrics.

**Bài 35.** Java 19 có ExecutorService.close có nghĩa nên tự động đóng commonPool? **Không**, ownership vẫn quyết định quyền dọn.**

## 39. Checklist triển khai

- [ ] Biết pool là owned/private, borrowed/injected, application-shared hay common.
- [ ] Có một owner chịu trách nhiệm lifecycle cho private/shared custom pool.
- [ ] Borrowers không shutdown pool nhận từ bên ngoài.
- [ ] Common pool không bị application/library shutdown.
- [ ] Pool lifetime bao trùm tất cả dependent services và jobs.
- [ ] Có cơ chế dừng nhận requests mới trước khi shutdown.
- [ ] Có protocol dừng producers trước khi pool không nhận submissions.
- [ ] Tracked futures/jobs có outcome rõ và deadline.
- [ ] Coi RejectedExecutionException là lifecycle error hợp lệ.
- [ ] Không sử dụng precheck isShutdown làm bảo đảm submit atomic.
- [ ] Private pool gọi shutdown rồi awaitTermination.
- [ ] Kết quả awaitTermination false được báo/giải quyết đúng.
- [ ] Có bounded escalation/cancellation policy nếu tasks không dừng.
- [ ] Không hiểu shutdownNow trả empty list là không có work.
- [ ] Không dùng shutdownNow làm rollback business side effects.
- [ ] Không close resource mà tasks còn dùng trước khi tasks xong.
- [ ] Không close pool từ trong task của chính pool.
- [ ] Không nhầm isShutdown, isTerminated, isQuiescent.
- [ ] Không coi Future completion là pool terminated.
- [ ] Không coi isDone là result success.
- [ ] Task cancellation không bị hiểu là shutdown pool.
- [ ] Tôn trọng InterruptedException và khôi phục flag khi policy cần.
- [ ] Tác vụ blocking không làm nghẽn shared CPU pool.
- [ ] Không tạo pool per request nếu không thực sự cần.
- [ ] Config parallelism dựa trên tổng CPU budget và workload.
- [ ] CompletableFuture async stages truyền executor rõ khi cần isolation.
- [ ] Metrics dùng để quan sát, không làm business ground truth.
- [ ] Nếu dùng AutoCloseable ở Java17, đó là **owner wrapper tự định nghĩa**.
- [ ] Không viết code dựa vào ExecutorService.close khi target --release17.
- [ ] Có tests cho owner close, borrower close, shared modules và failure.
- [ ] Có tests deterministic về pending task khi shutdown/await.
- [ ] Tài liệu API giữ đúng Java 17+ và phân biệt Java 19 enhancement.

## 40. Tài liệu chuẩn và nguồn đối chiếu

- [Java 17 `ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, common pool, shutdown/shutdownNow, awaitTermination, metrics và trạng thái.
- [Java 17 `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission, shutdown hai giai đoạn, awaitTermination và memory consistency.
- [Java 19 `ExecutorService`](https://docs.oracle.com/en/java/javase/19/docs/api/java.base/java/util/concurrent/ExecutorService.html): `AutoCloseable`/`close()` bổ sung từ Java 19, để **phân biệt phiên bản**, không dùng nhầm với Java17.
- [Java 17 `ForkJoinTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): cancellation, join, task outcome.
- [Java 17 `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancellation.
- [Java 17 `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default executor, explicit executor, async stages.
- [Java 17 `RecursiveTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): fork/join tasks with result.
- [Java 17 `ForkJoinPool.ManagedBlocker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): managed blocking trong worker pool.
- [Java 17 `RejectedExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionException.html): submit bị từ chối sau shutdown hoặc do executor.
- [Java 17 `AtomicBoolean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): đóng wrapper theo hướng idempotent.
- [Java 17 `TimeUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): deadlines/awaitTermination.

**Kết luận:** Với ForkJoinPool, **quyền sở hữu quyết định quyền shutdown**. Pool do component tự tạo thì component chịu trách nhiệm dừng producers, đợi futures, gọi `shutdown/awaitTermination` và xử lý tác vụ không kết thúc. Pool được mượn hoặc được chia sẻ thì borrower **không đóng**; `commonPool()` là tài nguyên JVM dùng chung. Trên Java 17, đừng nhầm `ForkJoinPool` với `AutoCloseable` từ các bản Java mới: nếu cần try-with-resources, hãy tự viết owner wrapper. Phân biệt hủy **một task** với shutdown **toàn pool**, xử lý race/rejection đúng và không dùng `shutdownNow` như rollback hoặc nguồn danh sách jobs chưa chạy.