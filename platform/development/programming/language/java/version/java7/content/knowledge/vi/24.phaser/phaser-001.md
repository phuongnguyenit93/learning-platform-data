# Đồng bộ một nhóm công việc qua nhiều giai đoạn với Phaser trong Java

**Chủ đề:** Java 7 — Phaser  
**Bài học:** Đồng bộ một nhóm công việc qua nhiều giai đoạn  
**Phiên bản:** Java 17+; `java.util.concurrent.Phaser` được giới thiệu trong Java 7 và **vẫn được hỗ trợ trên các bản Java hiện đại**. Các chương trình sử dụng JDK chuẩn, `ExecutorService` và thời hạn chờ khi kiểm thử; không đòi thư viện ngoài.

## 1. Bài toán: nhiều worker cùng đi qua một chuỗi giai đoạn

Giả sử một công việc xử lý dữ liệu có ba bước:

1. **Giai đoạn chuẩn bị:** mỗi worker đọc hoặc tạo phần dữ liệu mình sở hữu.
2. **Giai đoạn xử lý:** mỗi worker dùng kết quả của những worker khác từ bước trước.
3. **Giai đoạn hoàn tất:** mỗi worker xây dựng kết quả cuối, rồi hệ thống công bố kết quả.

Nếu một worker đọc dữ liệu mà worker khác **chưa ghi xong**, kết quả có thể sai. Ta cần một **điểm đồng bộ theo giai đoạn (barrier)** để không cho bất kỳ worker nào bắt đầu phần việc phụ thuộc của giai đoạn sau khi chưa đủ các participants của giai đoạn hiện tại.

```text
Worker A: [stage 0] --arrive--|             [stage 1] --arrive--|  [stage 2]
Worker B: [stage 0] ------arrive--|         [stage 1] ----arrive--| [stage 2]
Worker C: [stage 0] ----arrive--|           [stage 1] ------arrive--| [stage 2]
                               |                         |
                         all arrived                all arrived
                               |                         |
                          phase 0→1                  phase 1→2
                               |                         |
                     release all waiters          release all waiters
```

Điểm quan trọng: **barrier không tự làm công việc thay worker**. Nó chỉ điều phối việc báo **đã tới điểm đồng bộ** và chỉ cho tiến sang pha kế tiếp khi những participants đang đăng ký đã tới.

`Phaser` là một **reusable synchronization barrier** hỗ trợ nhiều lần tiến pha và **số participants có thể thay đổi**. Điều đó khiến nó phù hợp với pipeline nhiều giai đoạn và các nhóm worker có thể tham gia/rút lui.

### 1.1. Phaser khác gì một bộ đếm thông thường?

| Khái niệm | Tác dụng | Khác biệt với Phaser |
| --- | --- | --- |
| `CountDownLatch` | Một sự kiện: đếm về 0 rồi mở khóa người chờ | Một-shot: không tự tái sử dụng thành phase mới |
| `CyclicBarrier` | Một nhóm parties cố định chờ nhau theo nhiều lượt | Phù hợp nhóm cố định; cơ chế reset/broken-barrier khác |
| `Phaser` | Reusable barrier có phase number và registration/deregistration linh hoạt | Có thể tăng/giảm parties, tách **arrive** và **await**, tùy biến `onAdvance` |
| `CountDownLatch.await()` | Đợi sự kiện chung | Không có quan hệ đăng ký nhiều phases và không cần mỗi worker có party |
| `Future.get()` | Đợi kết quả của một tác vụ | Không tự làm các worker đồng bộ tại nhiều điểm qua nhiều vòng |
| `CompletableFuture.allOf` | Đợi tập Futures hoàn tất | Có thể mô tả một đợt tác vụ, nhưng không thay trực tiếp state machine barrier nhiều vòng |
| `Thread.join()` | Đợi thread kết thúc | Không tái sử dụng cùng thread như worker liên tục qua nhiều phase |

**Không phải Phaser là “CyclicBarrier phiên bản mới thay thế”.** Cả hai API đều còn hợp lệ; chọn theo số participants có cố định hay cần thay đổi, nhu cầu quan sát phase, timeout, termination và mức phức tạp.

## 2. Từ vựng: party, arrival, phase, await và termination

Để tránh nhầm lẫn, hãy phân biệt năm khái niệm.

**Party:** một **participant logic** đã được đăng ký. `new Phaser(3)` có ba registered parties. Phaser **không lưu định danh thread nào** là party nào; đó là trách nhiệm của chương trình.

**Arrival:** một party báo rằng **đã xong phần công việc của pha hiện tại** bằng `arrive()`, `arriveAndAwaitAdvance()` hoặc `arriveAndDeregister()`. Mỗi party chỉ được **arrive một lần cho mỗi pha**. Gọi trùng là lỗi sử dụng và có thể không được phát hiện ngay.

**Phase:** thế hệ đồng bộ hiện tại. Phaser mới bắt đầu ở phase `0`. Khi tất cả registered parties của phase đó đến, phaser tiến sang `1`; tiếp theo sang `2`…; về lý thuyết số phase có thể quay vòng sau `Integer.MAX_VALUE`.

**Await:** đợi phase thay đổi, hoặc chờ ngắn hơn nếu phaser đã tiến. `awaitAdvance(phase)` đợi một **giá trị phase cụ thể** không còn là phase hiện tại. Một thread quan sát **không nhất thiết là registered party** nếu chỉ gọi await.

**Termination:** trạng thái kết thúc barrier. Phaser đã terminated không thể tiếp tục một vòng đồng bộ bình thường; các methods đồng bộ trả về **giá trị phase âm**, thường dùng làm tín hiệu dừng. `forceTermination()` giúp giải phóng những waiters trong trường hợp lỗi hoặc shutdown.

### 2.1. Trạng thái nội bộ dễ hình dung

```text
Phaser mới: phase=0, registered=3, arrived=0, unarrived=3

Worker A arrive:
  phase=0, registered=3, arrived=1, unarrived=2

Worker B arrive:
  phase=0, registered=3, arrived=2, unarrived=1

Worker C arrive:
  phase=0, registered=3, arrived=3, unarrived=0
  -> onAdvance(0,3)
  -> phase=1, registered=3, arrived=0, unarrived=3
```

Sơ đồ mô tả **mô hình logic**, không phải chuỗi snapshots nhất thiết được quan sát nguyên tử bởi thread giám sát. Các phương thức `getRegisteredParties()`, `getArrivedParties()` và `getUnarrivedParties()` trả thông tin **có thể thay đổi ngay**; không dùng các con số này thay cho chính operations đồng bộ.

### 2.2. Phaser không ràng buộc party với một Thread object

Đây là điểm dễ bị bỏ sót. `Phaser` quản lý **các bộ đếm**, không giữ danh sách thread identities. Một thread có thể đại diện một party hoặc một coordinator quản lý nhiều party theo giao thức ứng dụng; nhưng nếu bạn không tự theo dõi quyền sở hữu, gọi `arrive` hai lần trong một phase có thể phá barrier.

Do đó, trong chương trình thực:

- Đăng ký số parties **phù hợp số người sẽ báo arrival**.
- Quy định rõ **mỗi worker phải arrive đúng một lần mỗi phase**.
- Worker rút lui phải dùng `arriveAndDeregister` đúng thời điểm.
- Khi có exception, không mù quáng “arrive thêm cho chắc”; dùng failure coordinator và `forceTermination` nếu cả nhóm không thể tiếp tục an toàn.
- Không để một thread không đăng ký tự gọi arrival; observer chỉ nên await/monitor.

## 3. Các API cần biết

| API | Ý nghĩa | Có chờ không? |
| --- | --- | --- |
| `new Phaser()` | Tạo phaser phase 0, ban đầu **0 parties** | Không |
| `new Phaser(n)` | Tạo với `n` registered, unarrived parties | Không |
| `register()` | Thêm một party | Có thể chờ nếu đang tiến pha theo implementation |
| `bulkRegister(n)` | Đăng ký thêm `n` parties | Có thể chờ trong một số trường hợp |
| `arrive()` | Ghi nhận một arrival, trả phase của arrival | **Không chờ các parties khác** |
| `arriveAndAwaitAdvance()` | Arrive rồi đợi phase tiến | **Có thể chờ** |
| `arriveAndDeregister()` | Arrive và bỏ đăng ký party | **Không chờ các parties khác** |
| `awaitAdvance(phase)` | Đợi phase thay đổi khỏi giá trị đã biết | Có thể chờ, **không interruptible** theo nghĩa throwing InterruptedException |
| `awaitAdvanceInterruptibly(phase)` | Đợi phase thay đổi, có thể ném `InterruptedException` | Có |
| `awaitAdvanceInterruptibly(phase,timeout,unit)` | Đợi có thời hạn | Có, báo `TimeoutException` khi timeout |
| `getPhase()` | Quan sát phase hiện tại | Không |
| `getRegisteredParties()` | Snapshot số parties đã đăng ký | Không |
| `getArrivedParties()` | Snapshot số parties đã arrive trong phase hiện tại | Không |
| `getUnarrivedParties()` | Snapshot số parties còn phải arrive trong phase hiện tại | Không |
| `isTerminated()` | Phaser đã kết thúc chưa | Không |
| `forceTermination()` | Yêu cầu terminate và giải phóng waiters | Không |
| `onAdvance(phase,registeredParties)` | Hook khi tất cả arrivals đạt đủ, có thể điều khiển termination | Thực thi trên đường advance |

**Cẩn thận:** `arriveAndAwaitAdvance()` **không nhận timeout**. Nếu cần interrupt/timeout, dùng mẫu `int phase = phaser.arrive(); phaser.awaitAdvanceInterruptibly(phase, timeout, unit);`. Hai thao tác này **không được kèm thêm arrive thứ hai** cho cùng một phase.

## 4. Ví dụ chính: ba worker đi qua ba giai đoạn

Tạo `PhaserMultiStageDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserMultiStageDemo {
  public static void main(String[] args) throws Exception {
    int workers=3, stages=3;
    Phaser barrier=new Phaser(workers);
    int[][] values=new int[stages][workers];
    ExecutorService pool=Executors.newFixedThreadPool(workers);
    try {
      @SuppressWarnings("unchecked")
      Future<Void>[] futures=(Future<Void>[])new Future<?>[workers];
      for(int worker=0;worker<workers;worker++){
        final int id=worker;
        futures[worker]=pool.submit(()->{
          for(int stage=0;stage<stages;stage++){
            values[stage][id]=(stage+1)*(id+1);
            int next=barrier.arriveAndAwaitAdvance();
            if(next<0)throw new IllegalStateException("Unexpected termination");
          }
          barrier.arriveAndDeregister();
          return null;
        });
      }
      for(Future<Void> future:futures)future.get(5,TimeUnit.SECONDS);
      for(int stage=0;stage<stages;stage++){
        int sum=0;for(int number:values[stage])sum+=number;
        System.out.println("stage"+stage+"-sum="+sum);
      }
      System.out.println("terminated="+barrier.isTerminated());
    }finally{
      barrier.forceTermination();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all PhaserMultiStageDemo.java
java PhaserMultiStageDemo
```

**stdout đã kiểm thử:**

```text
stage0-sum=6
stage1-sum=12
stage2-sum=18
terminated=true
```

### 4.1. Đọc chương trình theo từng phase

- Có **3 workers**, do đó `new Phaser(3)` đăng ký ba parties ngay từ đầu.
- Mỗi worker `id` ghi dữ liệu vào phần tử riêng `values[stage][id]`, tránh hai threads ghi cùng vị trí.
- Sau khi ghi xong mỗi stage, worker gọi `arriveAndAwaitAdvance()`, **không được tự ý bắt đầu stage tiếp theo** trước khi đủ ba arrivals.
- Phase bắt đầu là 0. Hoàn thành lượt đầu đưa tới phase 1; hoàn thành lượt thứ hai đưa tới phase 2; lượt cuối đưa tới phase 3.
- Sau ba lượt, mỗi worker `arriveAndDeregister()` tại phase tiếp theo để rút khỏi nhóm.
- Khi party cuối cùng deregister, default `onAdvance` được kích hoạt với số registered parties bằng 0 và **terminates** phaser.
- Main gọi `Future.get(5,SECONDS)` từ thread điều phối, xác nhận toàn bộ tasks đã hoàn tất trước khi đọc mảng.
- `finally` dùng `forceTermination` để tránh giữ waiters nếu exception xảy ra, rồi shutdown executor.

### 4.2. Vì sao không in kết quả trong từng worker?

Thứ tự thực hiện của threads **không được Java cam kết**. Nếu từng worker `System.out.println` khi kết thúc stage, thứ tự dòng có thể thay đổi dù thuật toán đúng. Ví dụ chỉ in từ main **sau khi futures thành công**, vì vậy stdout xác định.

### 4.3. Nếu một worker ném exception giữa chừng?

Giả sử hai worker đã gọi `arriveAndAwaitAdvance()` nhưng worker thứ ba lỗi **trước khi arrive**. Nếu không có recovery, cả hai có thể chờ vô hạn. `finally` của coordinator gọi `forceTermination()` là một lớp bảo vệ, nhưng nếu main đang đợi một Future theo thứ tự và không có timeout, main cũng có thể kẹt.

Trong production cần **failure supervisor**: khi worker bất kỳ lỗi, báo cho coordinator và **forceTerminate** nhóm ngay, hoàn thành/fail các promises và dọn tài nguyên. Dùng deadline cho các chờ ở cấp điều phối và không xem barrier là transaction/rollback.

## 5. Coordinator cũng có thể là một registered party

Khi main thread cần tự quyết định bước chuyển stage hoặc công bố kết quả đúng thời điểm, có thể đăng ký coordinator như một party thứ nhất:

```java
Phaser phaser = new Phaser(1); // Main/coordinator
phaser.bulkRegister(workerCount); // Những workers sẽ tham gia
```

Đây là snippet, `workerCount` cần khai báo và hợp lệ. Các workers + coordinator cùng phải arrive mỗi stage. Nếu main **chỉ muốn quan sát**, đừng đăng ký main rồi quên arrive — điều đó sẽ làm tất cả workers chờ.

### 5.1. Ví dụ runnable: coordinator cùng tham gia hai stages

Tạo `PhaserCoordinatorDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserCoordinatorDemo {
  public static void main(String[] args)throws Exception{
    Phaser barrier=new Phaser(1); // coordinator is one party
    barrier.bulkRegister(2);
    int[][] produced=new int[2][2];
    ExecutorService workers=Executors.newFixedThreadPool(2);
    try{
      Future<?>[] futures=new Future<?>[2];
      for(int w=0;w<2;w++){
        final int id=w;
        futures[w]=workers.submit(()->{
          for(int stage=0;stage<2;stage++){
            produced[stage][id]=10*stage+id+1;
            if(barrier.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
          }
          barrier.arriveAndDeregister();
        });
      }
      for(int stage=0;stage<2;stage++){
        if(barrier.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
      }
      for(Future<?> future:futures)future.get(5,TimeUnit.SECONDS);
      System.out.println("stage0-sum="+(produced[0][0]+produced[0][1]));
      System.out.println("stage1-sum="+(produced[1][0]+produced[1][1]));
      System.out.println("coordinator-only="+(barrier.getRegisteredParties()==1));
      barrier.arriveAndDeregister();
      System.out.println("terminated="+barrier.isTerminated());
    }finally{
      barrier.forceTermination();
      workers.shutdownNow();
      workers.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserCoordinatorDemo.java
java PhaserCoordinatorDemo
```

**stdout đã kiểm thử:**

```text
stage0-sum=3
stage1-sum=23
coordinator-only=true
terminated=true
```

Hai workers ghi các giá trị 1, 2 tại stage 0 và 11, 12 tại stage 1; main tham gia cả hai barriers nhưng không sửa mảng. Sau khi hai worker tasks rút, chỉ còn một party là coordinator. Khi coordinator `arriveAndDeregister`, registered parties về 0 và phaser terminated.

**Điểm thiết kế quan trọng:** coordinator là party **khác** với observer. Nếu bạn đăng ký coordinator chỉ để “theo dõi tiến độ” nhưng không gọi arrival, toàn bộ phase sẽ đứng lại. Nếu chỉ cần đợi chuyển pha mà không làm thành viên, dùng `awaitAdvance` như phần sau.

## 6. Đăng ký/rút bớt parties động giữa các giai đoạn

Khác một barrier có số members cố định, `Phaser` hỗ trợ:

- `register()` thêm **một** party.
- `bulkRegister(n)` thêm **n** parties.
- `arriveAndDeregister()` báo đến barrier rồi **rút khỏi nhóm**.
- `getRegisteredParties()` quan sát số members hiện có.

**Động không đồng nghĩa tùy ý.** Nếu bạn đăng ký người mới sau khi một số workers đã arrive, số unarrived của phase hiện tại có thể thay đổi. Thiết kế nên chỉ rõ **điểm nhận/loại participants** để không vô tình khiến một phase đã gần xong lại phải đợi task chưa được submit.

Một cách dễ hiểu là **coordinator điều phối giữa hai stages**, đăng ký worker mới sau khi worker cũ đã rút và phase trước đã hoàn thành.

### 6.1. Ví dụ runnable: hai workers tham gia luân phiên hai phase

Tạo `PhaserDynamicPartiesDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserDynamicPartiesDemo {
  public static void main(String[] args)throws Exception{
    Phaser phaser=new Phaser(1);
    ExecutorService workers=Executors.newSingleThreadExecutor();
    try{
      phaser.register();
      Future<?> first=workers.submit(()->{
        if(phaser.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
        phaser.arriveAndDeregister();
      });
      phaser.arriveAndAwaitAdvance();
      first.get(5,TimeUnit.SECONDS);
      System.out.println("phase-after-first="+phaser.getPhase());
      System.out.println("parties-after-first="+phaser.getRegisteredParties());
      phaser.register();
      Future<?> second=workers.submit(()->{
        if(phaser.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
        phaser.arriveAndDeregister();
      });
      phaser.arriveAndAwaitAdvance();
      second.get(5,TimeUnit.SECONDS);
      System.out.println("phase-after-second="+phaser.getPhase());
      System.out.println("parties-after-second="+phaser.getRegisteredParties());
      phaser.arriveAndDeregister();
      System.out.println("terminated="+phaser.isTerminated());
    }finally{
      phaser.forceTermination();
      workers.shutdownNow();
      workers.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserDynamicPartiesDemo.java
java PhaserDynamicPartiesDemo
```

**stdout đã kiểm thử:**

```text
phase-after-first=1
parties-after-first=1
phase-after-second=2
parties-after-second=1
terminated=true
```

Quy trình:

1. Phaser bắt đầu với coordinator (1 party).
2. Coordinator `register()` thêm worker thứ nhất → 2 parties.
3. Worker thứ nhất và coordinator cùng arrive → phase 0 tiến thành phase 1.
4. Worker thứ nhất `arriveAndDeregister()` tại phase 1 rồi kết thúc; chỉ còn coordinator.
5. Coordinator **đợi Future thứ nhất hoàn tất** rồi mới đăng ký worker thứ hai → không bị race với việc worker thứ nhất còn là party.
6. Coordinator + worker thứ hai cùng arrive → phase 1 thành phase 2.
7. Worker thứ hai deregister; coordinator vẫn registered, sau đó cũng deregister → termination.

**Vì sao dùng một single-thread executor vẫn ổn?** Hai worker tasks **không phải cùng đợi đồng thời**: task thứ nhất kết thúc rồi task thứ hai mới được submit. Số worker threads đủ cho số parties thật sự đang đợi mỗi lần (coordinator chạy trên main). Trong một pipeline chạy nhiều workers cùng lúc, một pool quá nhỏ có thể gây starvation như phần cảnh báo sau.

### 6.2. Đăng ký trước khi submit hay tự register trong worker?

Cả hai kiểu có thể hợp lệ, tùy ai sở hữu party. Nhưng với một batch mới, thường dễ kiểm soát nhất là:

1. Coordinator biết chính xác số workers, `bulkRegister(n)`.
2. Coordinator submit đủ n tasks lên executor có năng lực chạy chúng.
3. Mỗi task đảm nhiệm một party và gọi arrive đúng hợp đồng.
4. Khi xong toàn bộ các stages mà task cần tham gia, gọi `arriveAndDeregister()`.
5. Nếu submit thất bại sau khi đã đăng ký, coordinator phải **xử lý phần party đã đăng ký nhưng không có worker** — có thể forceTermination/fail whole phase; không bỏ mặc barrier đợi vĩnh viễn.

### 6.3. Thời điểm rút khỏi nhóm

`arriveAndDeregister()` **vừa tính là arrival ở phase hiện tại, vừa giảm số parties cần trong các phase tiếp theo**. Nó **không chờ** các parties còn lại.

Nếu worker muốn rút khỏi nhóm nhưng vẫn **đợi phase vừa rút hoàn tất**, mẫu JavaDoc là:

```java
int oldPhase = phaser.arriveAndDeregister();
int nextPhase = phaser.awaitAdvance(oldPhase);
```

Đây là snippet, `phaser` đã khai báo và worker vẫn còn registration hợp lệ ngay trước `arriveAndDeregister`. Không gọi thêm `arrive()` sau đó ở cùng phase. Nếu không còn parties, phaser có thể terminate và `nextPhase` là số âm.

## 7. Tách arrival và waiting: observer không phải party

`arrive()` **không đợi** phase tiến. Nó trả **phase mà arrival vừa áp dụng**.

`awaitAdvance(phase)` **không tự tính một arrival**. Nó chỉ đợi phase **khác** giá trị được truyền vào — hoặc trả ngay nếu phase đã khác/terminated. Nhờ đó có thể có một **observer chỉ muốn biết tiến độ** mà không làm tăng registered party count.

### 7.1. Ví dụ runnable: hai workers chỉ arrive, main quan sát

Tạo `PhaserObserverDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserObserverDemo {
  public static void main(String[] args)throws Exception{
    Phaser phaser=new Phaser(2);
    ExecutorService workers=Executors.newFixedThreadPool(2);
    try{
      Future<Integer> a=workers.submit(phaser::arrive);
      Future<Integer> b=workers.submit(phaser::arrive);
      int phase=phaser.awaitAdvanceInterruptibly(0,5,TimeUnit.SECONDS);
      System.out.println("arrival-a="+a.get(5,TimeUnit.SECONDS));
      System.out.println("arrival-b="+b.get(5,TimeUnit.SECONDS));
      System.out.println("observed-phase="+phase);
      System.out.println("still-registered="+phaser.getRegisteredParties());
      phaser.forceTermination();
      System.out.println("terminated="+phaser.isTerminated());
    }finally{
      phaser.forceTermination();
      workers.shutdownNow();
      workers.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserObserverDemo.java
java PhaserObserverDemo
```

**stdout đã kiểm thử:**

```text
arrival-a=0
arrival-b=0
observed-phase=1
still-registered=2
terminated=true
```

Vì hai workers gọi `arrive` trong **phase 0**, cả hai nhận phase cũ là 0. Main **không registered**, chỉ đợi `awaitAdvanceInterruptibly(0,5,SECONDS)`; khi cả hai đã arrive, nó thấy phase 1.

**Đặc biệt:** sau khi `arrive()` mà không deregister, parties vẫn registered. Trong ví dụ, không có worker nào tiếp tục phase 1, vì vậy coordinator gọi `forceTermination()` để kết thúc. Nếu chỉ quên dọn mà tiếp tục đợi phase 1, không ai arrive và observer có thể chờ vô hạn.

### 7.2. Vấn đề race giữa getPhase và awaitAdvance

Một observer có thể làm:

```java
int phase = phaser.getPhase();
// ... một worker khác đã hoàn tất phase ở đây ...
int next = phaser.awaitAdvance(phase);
```

Đây là snippet, không phải chương trình độc lập. Nếu phase đã tiến trước khi lời gọi `awaitAdvance`, method **trả ngay** vì phase hiện tại không còn bằng phase truyền vào — đó là hành vi được thiết kế để tránh mất tín hiệu kiểu “check-then-wait” thông thường.

**Nhưng:** nếu một observer bỏ qua nhiều phase quá nhanh, kết quả trả về là trạng thái tại thời điểm quan sát; không nên coi nó là một event log đầy đủ của mọi phase đã chuyển. Nếu cần ghi lại mọi stage event, ứng dụng phải có logging/queue/sequence riêng.

### 7.3. Unregistered observer không được arrive

Observer chỉ có quyền chờ và đọc state. `Phaser` không quản lý danh tính parties, nên API có thể **không phát hiện ngay** một thread không registered lại gọi `arrive`. Hãy giữ quy tắc này tại tầng thiết kế, không dựa vào exception runtime để bảo vệ.

## 8. Timeout: phải có phương án giải phóng cả nhóm

Một nguy cơ lớn trong nhiều giai đoạn là một worker dừng vì lỗi, còn các worker khác mãi mãi chờ. Phaser **không tự đếm một worker bị crash thành arrival**.

Nếu cần timeout:

```java
int phase = phaser.arrive();
try {
    phaser.awaitAdvanceInterruptibly(phase, 5, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    phaser.forceTermination();
    // Fail workflow và dọn các tasks; không coi phase đã thành công.
}
```

Đây là snippet, cần imports và xử lý `InterruptedException`. **Quan trọng:** `arrive()` đã đếm một arrival. Nếu thời gian chờ hết, bạn **không được “sửa” bằng cách gọi arrive một lần nữa** ở cùng phase. `awaitAdvanceInterruptibly` bị timeout/interrupt **không tự cập nhật hoặc terminate phaser**; bạn phải quyết định recovery, thường là fail toàn bộ barrier.

### 8.1. Ví dụ runnable: thiếu một party rồi forceTermination

Tạo `PhaserTimeoutRecoveryDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserTimeoutRecoveryDemo {
  public static void main(String[] args)throws Exception{
    Phaser phaser=new Phaser(2);
    int phase=phaser.arrive();
    boolean timeout=false;
    try{
      phaser.awaitAdvanceInterruptibly(phase,20,TimeUnit.MILLISECONDS);
    }catch(TimeoutException ex){timeout=true;}
    System.out.println("timeout="+timeout);
    System.out.println("phase-before="+phaser.getPhase());
    System.out.println("unarrived-before="+phaser.getUnarrivedParties());
    phaser.forceTermination();
    System.out.println("terminated="+phaser.isTerminated());
    System.out.println("negative-after="+(phaser.awaitAdvance(phase)<0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserTimeoutRecoveryDemo.java
java PhaserTimeoutRecoveryDemo
```

**stdout đã kiểm thử:**

```text
timeout=true
phase-before=0
unarrived-before=1
terminated=true
negative-after=true
```

Ví dụ có **hai registered parties** nhưng chỉ có một arrival. Party còn lại được mô phỏng như participant không bao giờ tới; vì vậy `awaitAdvanceInterruptibly` chắc chắn không thể nhận phase advance trong thời hạn 20 ms.

Sau timeout, `getUnarrivedParties()==1`; Phaser **chưa tự terminate**. Lệnh `forceTermination` báo workflow thất bại, giải phóng các waiters khác (nếu có). `awaitAdvance` sau termination trả giá trị âm.

### 8.2. Interruption không giống timeout

- `awaitAdvanceInterruptibly(phase)` có thể ném `InterruptedException`.
- Overload có timeout có thể ném **cả** `InterruptedException` và `TimeoutException`.
- `awaitAdvance(phase)` và `arriveAndAwaitAdvance()` **không đáp ứng interrupt theo cách ném InterruptedException**; chỉ `shutdownNow()` không đủ để giải quyết một nhóm workers vẫn chờ barrier.
- Sau một exception chờ, trạng thái parties/phase của Phaser **không được tự động chỉnh lại**.
- `InterruptedException` nên được xử lý tại boundary thích hợp, thường restore `Thread.currentThread().interrupt()` nếu không propagate; và kích hoạt failure coordinator khi không thể tiếp tục phase.

**Không đóng mắt chạy tiếp stage sau nếu chờ barrier timeout.** Khi đó các workers khác có thể chưa tạo xong dữ liệu mà stage kế tiếp đang cần.

### 8.3. Vì sao timeout không làm mất registration?

Một party đã arrive trong phase 0 nhưng vẫn là **registered party** cho những phase tiếp theo trừ khi deregister. Timeout chỉ liên quan thread chờ phase advance; nó không phải mệnh lệnh hủy registration. Cách xử lý tốt thường là **terminate workflow** khi một stage không thể hoàn tất trong deadline, thay vì tự điều chỉnh unarrived counts để giả vờ thành công.

## 9. Một worker thất bại: phát tín hiệu cho mọi bên chờ

Trong một pipeline đồng bộ, lỗi của một participant có thể giữ toàn bộ phần còn lại. Vì vậy task có thể dùng:

```java
try {
    doStage();
    phaser.arriveAndAwaitAdvance();
} catch (RuntimeException failure) {
    phaser.forceTermination();
    throw failure;
}
```

Đây là snippet, `doStage` và `phaser` phải có định nghĩa. Mục tiêu là **báo cho cả nhóm** khi một lỗi làm workflow không thể hoàn tất, không chờ đến khi coordinator hết timeout.

### 9.1. Ví dụ runnable: một task ném exception, waiter được đánh thức

Tạo `PhaserFailureRecoveryDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserFailureRecoveryDemo {
  public static void main(String[] args)throws Exception{
    Phaser phaser=new Phaser(2);
    ExecutorService pool=Executors.newFixedThreadPool(2);
    try{
      Future<?> failing=pool.submit((Runnable)()->{
        try{
          throw new IllegalStateException("invalid data");
        }finally{phaser.forceTermination();}
      });
      Future<Boolean> waiting=pool.submit(()->phaser.arriveAndAwaitAdvance()<0);
      boolean errorSeen=false;
      try{failing.get(5,TimeUnit.SECONDS);}
      catch(ExecutionException ex){errorSeen=ex.getCause() instanceof IllegalStateException;}
      System.out.println("error-seen="+errorSeen);
      System.out.println("waiter-released="+waiting.get(5,TimeUnit.SECONDS));
      System.out.println("terminated="+phaser.isTerminated());
    }finally{
      phaser.forceTermination();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserFailureRecoveryDemo.java
java PhaserFailureRecoveryDemo
```

**stdout đã kiểm thử:**

```text
error-seen=true
waiter-released=true
terminated=true
```

Một task lỗi và gọi `forceTermination` trong `finally`; main nhận đúng nguyên nhân `IllegalStateException` qua `ExecutionException.getCause()`. Task còn lại, dù đã chờ trước hay bắt đầu chờ sau termination, nhận **giá trị phase âm** và không kẹt.

**Hành vi quan trọng:** `forceTermination` là một **tín hiệu kết thúc barrier**, không tự cancel mọi Futures, dừng CPU jobs, rollback dữ liệu hay trả result hợp lệ. Bạn phải kết hợp với chính sách hủy/giải phóng của tác vụ và executor.

### 9.2. Đừng deregister bừa trong finally

Một mẫu dễ sai:

```java
try {
    phaser.arriveAndAwaitAdvance();
} finally {
    phaser.arriveAndDeregister();
}
```

Đây là snippet không nên dùng một cách máy móc. Lời gọi `arriveAndAwaitAdvance` có thể đã arrival ở phase này, nhưng do termination/exception logic ở application, một lần `arriveAndDeregister` tiếp theo **có thể áp dụng vào phase khác hoặc trở thành duplicate arrival** nếu state không được điều phối.

Hãy ghi rõ state của party và phase mà nó sở hữu; chỉ deregister đúng **một lần** trong một phase hợp lệ. Khi toàn workflow đã thất bại, `forceTermination` thường an toàn hơn việc bắt mọi thread “arrive thêm” để mở barrier.

## 10. onAdvance: thực hiện hành động khi một phase hoàn tất

Mỗi khi đủ arrivals, Phaser gọi:

```java
protected boolean onAdvance(int phase, int registeredParties);
```

Phương thức này được gọi bởi **party kích hoạt phase advance**. Nó nhận phase vừa hoàn tất (trước khi tăng) và số parties đang đăng ký, có thể làm một phần việc rất ngắn như increment metrics hoặc quyết định dừng sau một số pha nhất định.

**Kết quả trả về:**

- `false`: tiếp tục sang phase kế tiếp.
- `true`: terminate Phaser; các waiters nhận tín hiệu phase âm.

Default `onAdvance` kết thúc khi số registered parties trở thành 0 do deregistration. Override có thể thay đổi policy này (ví dụ dừng sau ba phases dù workers vẫn registered).

### 10.1. Ví dụ runnable: tự dừng sau ba giai đoạn

Tạo `PhaserOnAdvanceDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class PhaserOnAdvanceDemo {
  public static void main(String[] args)throws Exception{
    AtomicInteger calls=new AtomicInteger();
    Phaser phaser=new Phaser(2){
      @Override protected boolean onAdvance(int phase,int registeredParties){
        calls.incrementAndGet();
        return phase>=2 || registeredParties==0;
      }
    };
    ExecutorService pool=Executors.newFixedThreadPool(2);
    int[][] output=new int[3][2];
    try{
      Future<?>[] futures=new Future<?>[2];
      for(int worker=0;worker<2;worker++){
        final int id=worker;
        futures[worker]=pool.submit(()->{
          for(int stage=0;stage<3;stage++){
            output[stage][id]=(stage+1)*(id+1);
            int next=phaser.arriveAndAwaitAdvance();
            if(stage<2&&next<0)throw new IllegalStateException("Early termination");
          }
        });
      }
      for(Future<?> future:futures)future.get(5,TimeUnit.SECONDS);
      int sum=0;for(int[] line:output)for(int number:line)sum+=number;
      System.out.println("on-advance-calls="+calls.get());
      System.out.println("sum="+sum);
      System.out.println("terminated="+phaser.isTerminated());
    }finally{
      phaser.forceTermination();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserOnAdvanceDemo.java
java PhaserOnAdvanceDemo
```

**stdout đã kiểm thử:**

```text
on-advance-calls=3
sum=18
terminated=true
```

Tại phase 0 và 1, `onAdvance` trả false; phase 2 được hoàn tất thì trả true. Có đúng **ba lần gọi hook**. Trên phase cuối, `arriveAndAwaitAdvance` có thể trả **giá trị âm** do terminated; demo chỉ coi phase âm là lỗi **trước stage cuối**.

**Chú ý quan trọng:** khi phaser terminate, `getPhase()` là âm. Không dựa vào phép `getPhase()==3` để chứng minh đã chạy đủ ba phase. Dùng dữ liệu kết quả, số lần hook hoặc state riêng do ứng dụng duy trì.

### 10.2. onAdvance có được chờ I/O hoặc một participant khác không?

Không nên. Hook này chạy **trên đường cho phép các waiters tiến sang phase kế tiếp**. Nếu nó:

- Chờ một worker đang blocked ở chính barrier.
- Gọi `awaitAdvance` cho phase mà chính hook đang chịu trách nhiệm hoàn tất.
- Làm JDBC/HTTP request chậm.
- Giữ lock mà những workers khác cần để giải phóng resource.
- Đưa một task sang pool rồi block đợi task ấy khi pool không có worker rảnh.

...bạn có thể tạo deadlock hoặc tail latency lớn.

**Giữ `onAdvance` ngắn**: cập nhật state/metrics có giới hạn, quyết định terminate, rồi trả về. Nếu có công việc phức tạp cần chạy giữa các stages, mô hình hóa nó như **một party/coordinator riêng** hoặc một bước processing rõ ràng bên ngoài hook. Theo JavaDoc, hiệu ứng gọi các phương thức arrival/registration/waiting trên cùng phaser **ngay trong `onAdvance` là không được xác định**; tránh làm điều đó.

## 11. Pipeline phụ thuộc chéo: chứng minh dữ liệu từ phase trước đã sẵn sàng

Bài toán thiết thực nhất là worker B cần dữ liệu do worker A vừa sản xuất ở phase trước. Khi dùng Phaser đúng, nó tạo **memory consistency effects**: những actions trước arrival của phase sẽ **happen-before** phase advance và actions tiếp theo sau advance.

Điều này khác với việc chỉ có đủ số đếm. Nó giúp các workers có thể quan sát kết quả của phase trước **sau khi barrier được hoàn tất**, miễn là các reads/writes khác được tổ chức đúng.

### 11.1. Ví dụ runnable: mỗi worker đọc dữ liệu của worker bên cạnh

Tạo `PhaserPipelineDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.*;
public class PhaserPipelineDemo {
  public static void main(String[] args)throws Exception{
    Phaser phaser=new Phaser(3);
    int[] produced=new int[3],combined=new int[3];
    ExecutorService pool=Executors.newFixedThreadPool(3);
    try{
      Future<?>[] futures=new Future<?>[3];
      for(int worker=0;worker<3;worker++){
        final int id=worker;
        futures[worker]=pool.submit(()->{
          produced[id]=(id+1)*10;
          if(phaser.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
          combined[id]=produced[id]+produced[(id+1)%produced.length];
          if(phaser.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
          phaser.arriveAndDeregister();
        });
      }
      for(Future<?> future:futures)future.get(5,TimeUnit.SECONDS);
      System.out.println("produced="+Arrays.toString(produced));
      System.out.println("combined="+Arrays.toString(combined));
      System.out.println("terminated="+phaser.isTerminated());
    }finally{
      phaser.forceTermination();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserPipelineDemo.java
java PhaserPipelineDemo
```

**stdout đã kiểm thử:**

```text
produced=[10, 20, 30]
combined=[30, 50, 40]
terminated=true
```

Luồng dữ liệu:

- **Phase 0:** worker 0 ghi 10, worker 1 ghi 20, worker 2 ghi 30 vào ba slots riêng.
- **Barrier 0→1:** chỉ khi cả ba ghi xong, mỗi worker mới đọc `produced` của một worker khác.
- **Phase 1:** worker 0 tính 10+20=30; worker 1 tính 20+30=50; worker 2 tính 30+10=40.
- **Barrier 1→2:** toàn bộ `combined` đã hoàn thành và sẵn sàng để phần tiếp theo dùng.
- **Rút khỏi nhóm:** các workers deregister rồi main đọc output sau khi tất cả futures hoàn tất.

**Tại sao không dùng mỗi `volatile` trên mảng?** Trong Java, `volatile int[]` chỉ bảo đảm visibility cho **reference**, không tự bảo đảm đồng bộ toàn bộ dữ liệu mảng mà không có giao thức. Ở đây, **phaser barrier** cung cấp quan hệ happens-before qua phase; mỗi worker cũng sở hữu một slot riêng.

### 11.2. Barrier không sửa được data race trong cùng một stage

Nếu worker 0 và worker 1 **cùng cập nhật `produced[0]++`** trong phase 0, barrier ở cuối stage **không làm hai lần tăng thành atomic**. Bạn vẫn có lost update vì race xảy ra **trước** barrier.

Hãy phân vùng dữ liệu, dùng immutable partial results, hoặc cơ chế atomic/lock phù hợp cho dữ liệu buộc phải chia sẻ. Phaser chỉ điều phối **ranh giới giữa các giai đoạn**, không tự biến logic trong một giai đoạn thành thread-safe.

## 12. Phaser phân cấp: nhiều nhóm con, một barrier toàn cục

Với số parties rất lớn, một Phaser đơn lẻ có thể có contention trên các bộ đếm. Java hỗ trợ **tiered phasers**: những nhóm con có Phaser riêng, cùng liên kết tới parent phaser.

```text
                    Root Phaser
                   /           \
          Child Phaser A    Child Phaser B
             /      \          /       \
          A1         A2      B1         B2

A1 và A2 arrive ở child A -> child A báo parent
B1 và B2 arrive ở child B -> child B báo parent
Root đủ arrivals -> phase advance cho cả cây
```

Các child phasers **tự đăng ký với parent** khi có members, và **tự deregister parent** khi members về 0. Một child có **hai** local parties nhưng chỉ đại diện **một party** ở parent, giúp giảm contention trên root. Việc phân cấp có overhead và không phải lúc nào cũng nhanh hơn.

### 12.1. Ví dụ runnable: hai nhóm con, bốn workers, hai stages

Tạo `PhaserTieredDemo.java`:

```java
import java.util.concurrent.*;
public class PhaserTieredDemo {
  public static void main(String[] args)throws Exception{
    Phaser parent=new Phaser();
    Phaser left=new Phaser(parent,2),right=new Phaser(parent,2);
    System.out.println("root-parties-initial="+parent.getRegisteredParties());
    ExecutorService pool=Executors.newFixedThreadPool(4);
    try{
      Future<?>[] futures=new Future<?>[4];
      for(int worker=0;worker<4;worker++){
        Phaser child=worker<2?left:right;
        futures[worker]=pool.submit(()->{
          for(int phase=0;phase<2;phase++){
            if(child.arriveAndAwaitAdvance()<0)throw new IllegalStateException("Terminated");
          }
          child.arriveAndDeregister();
        });
      }
      for(Future<?> future:futures)future.get(5,TimeUnit.SECONDS);
      System.out.println("workers-complete="+futures.length);
      System.out.println("root-parties-final="+parent.getRegisteredParties());
      System.out.println("root-terminated="+parent.isTerminated());
    }finally{
      parent.forceTermination();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PhaserTieredDemo.java
java PhaserTieredDemo
```

**stdout đã kiểm thử:**

```text
root-parties-initial=2
workers-complete=4
root-parties-final=0
root-terminated=true
```

**Giải thích:**

- Root tạo với **0 parties**, sau đó child trái có 2 workers và child phải có 2 workers.
- Khi mỗi child có nonzero registered parties, parent được đăng ký **một party đại diện child đó**.
- Root thấy đúng **2 parties**, không phải 4.
- Hai child cùng hoàn thành một stage mới cho phép root phase tiến.
- Mỗi worker đi qua hai stages, rồi deregister ở child.
- Khi mỗi child hết members, nó tự rút khỏi root. Root hết parties và mặc định terminates.

**Không cần gọi `parent.register()` thủ công** cho mỗi worker trong mô hình này; child registration đã được liên kết tới parent. Nếu làm thêm, root sẽ chờ các parties không có ai arrive và có nguy cơ deadlock.

### 12.2. Khi nào tiering đáng dùng?

- Có số lượng lớn participants, đo thấy contention trên một Phaser duy nhất.
- Nhóm workers có cấu trúc tự nhiên theo partitions/tenants/NUMA/work units.
- Hệ thống cần giảm contention trên root và chấp nhận phí điều phối nhiều levels.

**Không áp dụng cho 4 workers chỉ vì ví dụ có tiered Phaser.** Với nhóm nhỏ, một Phaser thường đơn giản và nhanh đủ. Benchmark trước khi thêm cấu trúc phức tạp.

## 13. Termination: default, custom và cưỡng bức

Một Phaser có thể ngừng hoạt động theo ba hướng chính:

**1. Default termination:** khi `onAdvance` mặc định thấy số registered parties về 0 do `arriveAndDeregister` và xảy ra phase advance.

**2. Custom termination:** override `onAdvance(phase, parties)` trả true khi đạt số phases tối đa hoặc điều kiện hoàn tất.

**3. Forceful termination:** `forceTermination()` từ coordinator khi có lỗi, timeout hoặc shutdown.

### 13.1. Đừng bỏ qua giá trị âm

Khi `isTerminated()==true`, các thao tác chờ/registration không còn hoạt động như một reusable barrier bình thường. Nhiều phương thức trả phase **âm** làm tín hiệu termination. Ví dụ:

```java
int next = phaser.arriveAndAwaitAdvance();
if (next < 0) {
    // Workflow đã terminate; không coi stage là thành công.
}
```

Đây là snippet. Riêng nếu **chủ đích terminate sau phase cuối bằng `onAdvance`**, giá trị âm ở lần cuối có thể là **thành công kết thúc**. Hãy phân biệt **termination có chủ đích** với **forceTermination do lỗi** trong state nghiệp vụ; `isTerminated()` một mình không ghi nguyên nhân.

### 13.2. forceTermination không tự “reset” Phaser

`forceTermination` **không reset registrations về 0** và không tạo một Phaser sạch cho batch mới. Các attempts `register` sau termination không còn đưa Phaser trở lại trạng thái hoạt động.

Nếu workflow mới cần chạy các stages từ đầu, tạo **Phaser instance mới** với parties mới, hoặc dùng vòng đời phù hợp ngay từ đầu. Không sửa phase field bằng reflection/Unsafe hay phụ thuộc hành vi triển khai.

### 13.3. Phaser bắt đầu bằng 0 parties có tự terminate không?

`new Phaser()` tạo phase 0 với **0 parties** và chưa tự động có một phase advance. Nó hữu ích khi các workers đăng ký sau. Default termination thường xảy ra khi **deregistration làm số parties về 0** và phaser tiến pha. Vì vậy “không có ai ngay khi tạo” và “vừa rút party cuối” là **hai tình huống vòng đời khác nhau**.

## 14. Cảnh báo deadlock: số parties lớn hơn số worker threads có thể chạy

Một lỗi đặc biệt phổ biến:

```text
Phaser registered parties = 3
ExecutorService fixed thread pool = 2

Submit Task A -> chạy -> arriveAndAwaitAdvance() -> BLOCKED
Submit Task B -> chạy -> arriveAndAwaitAdvance() -> BLOCKED
Submit Task C -> xếp hàng, chưa có thread rảnh

Phase không thể advance: C chưa arrive.
C không thể chạy: A và B đang giữ hai threads.
```

**Đây là thread-pool starvation deadlock do cấu hình và dependency**, không phải lỗi của Phaser. Thêm timeout hoặc `shutdownNow` không tự sửa thiết kế, đặc biệt `arriveAndAwaitAdvance` không ném `InterruptedException`.

### 14.1. Nguyên tắc chọn số worker threads

- Nếu mỗi registered party là một blocking task cần thread để đi tới barrier, phải có **đủ capacity** để tất cả parties đạt barrier.
- Nếu coordinator đã đăng ký là một party, nhớ **coordinator cũng phải arrive**.
- Nếu tasks chia theo batches, không để batch sau chứa party cần đến nhưng batch trước đang block giữ toàn bộ executor.
- Với thread pools dùng chung, một subsystem khác có thể chiếm threads; dùng isolation/bounded submission khi cần.
- Nếu có nhiều I/O waiting, cân nhắc mô hình bất đồng bộ hoặc virtual threads trên phiên bản hỗ trợ, nhưng vẫn phải tránh dependency cycles, quota và resource exhaustion.
- Nếu dùng `ForkJoinPool`, cần hiểu blocking và pool parallelism; JavaDoc lưu ý progress nếu parallelism đáp ứng số parties có thể block đồng thời. Không giả định work stealing tự giải phóng mọi wait.

**Không có công thức “số threads = parties” áp dụng tuyệt đối**: parties là logical participants, main thread có thể là party, tasks có thể arrive không chờ, hoặc cùng thread có thể đại diện nhiều party khi thiết kế đúng. Điều cốt lõi là **mọi arrival bắt buộc đều có đường thực thi khả thi**.

### 14.2. Deadlock do shared lock

Một worker giữ lock L rồi chờ barrier; worker còn lại cần lock L để hoàn tất stage trước khi arrive. Dù pool có 100 threads, đó vẫn là một **wait-for cycle**.

Sửa bằng cách **không giữ lock cần cho các parties khác khi gọi barrier**; critical section nên ngắn, release lock trước khi chờ. Phaser chỉ giải quyết chờ “đủ arrivals”, không giải quyết lock ownership sai.

### 14.3. Deadlock do coordinator quên arrive

Một Phaser(1) có coordinator registered. Nếu coordinator gọi `Future.get()` đợi workers, nhưng workers đang chờ chính party coordinator arrive, hệ thống có vòng chờ:

```text
Coordinator -> Future workers done
Workers -> Phaser phase advance
Phaser -> Coordinator must arrive
Coordinator -> chờ workers done nên không arrive
```

**Sửa:** coordinator phải arrive tại đúng stage **trước khi đợi** các Futures hoàn thành. Hoặc nếu coordinator chỉ quan sát, **đừng đăng ký nó làm party**; dùng `awaitAdvance(phase)`.

## 15. Memory consistency và tính đúng dữ liệu qua các phase

JavaDoc của `Phaser` nêu:

- Actions trước mọi dạng `arrive` **happen-before** phase advance tương ứng và `onAdvance` action (nếu có).
- Những actions đó, qua phase advance, **happen-before** các actions sau phase advance.

Điều đó cho phép thiết kế các chuỗi **produce → barrier → consume** rõ ràng mà không cần tự gắn `volatile` lên mọi phần tử mảng.

**Nhưng phải giữ điều kiện:**

1. Producers **hoàn tất ghi** trước khi arrive.
2. Consumers **chỉ đọc dữ liệu của stage trước** sau successful phase advance.
3. Không có producer khác sửa đồng thời dữ liệu đó trong lúc đang đọc, trừ khi có cơ chế đồng bộ khác.
4. Mỗi worker chỉ arrive đúng một lần; không tạo false barrier advance bằng double-arrival.
5. Nếu terminated do lỗi/timeout, consumer không coi nó là successful phase.
6. Nếu workers có side effects bên ngoài JVM (DB/network), Phaser không thay thế transaction/acknowledgement.

### 15.1. Điều gì xảy ra nếu worker đọc quá sớm?

Nếu worker A đã ghi vào `produced[0]` nhưng chưa arrive, worker B đọc `produced[0]` trước khi barrier mở, bạn có thể có data race hoặc đọc trạng thái chưa đúng theo phase. Chỉ cần đặt `arriveAndAwaitAdvance` ở cuối mỗi stage **và trước phần đọc phụ thuộc** ở stage tiếp theo như demo pipeline.

### 15.2. Tính đúng không phụ thuộc thứ tự kết thúc worker

Phaser không cam kết worker nào được đánh thức đầu tiên. Kết quả phải dựa vào **dữ liệu và thứ tự phase**, không dựa vào thứ tự scheduler. Nếu có downstream ordered output, collect vào mảng theo index rồi publish từ coordinator sau barrier.

## 16. Lập trình với lỗi, cancellation và shutdown

Một workflow production cần **trạng thái riêng** như `RUNNING / CANCELLING / FAILED / COMPLETED`. Phaser chỉ biết registered counts, arrivals và termination; nó **không ghi nguyên nhân lỗi** và không rollback.

### 16.1. Mẫu coordinator an toàn

1. Tạo Phaser và đăng ký parties trước khi bắt đầu stage, theo một ownership policy.
2. Tạo ExecutorService đúng capacity và có giới hạn submissions.
3. Khi worker success, worker arrive đúng một lần cho phase hiện tại.
4. Khi worker fail, ghi nhận nguyên nhân, `forceTermination` và fail job.
5. Coordinator không đợi vô hạn; dùng deadline với Future hoặc các interruptible timed waits.
6. Khi coordinator quan sát phase âm, kiểm tra state/error reason trước khi quyết định kết quả.
7. Dọn resources theo đúng thứ tự: terminate barrier để mở waiters; yêu cầu dừng workers; collect Futures trong deadline; shutdown executor.
8. Không reuse terminated Phaser cho job mới.
9. Không publish output nửa chừng khi stage có worker failure.
10. Không log payload nhạy cảm hoặc tạo queue tasks không giới hạn.

### 16.2. Vì sao shutdownNow trước forceTermination không đủ?

`shutdownNow` thường interrupt những worker threads. Nhưng `arriveAndAwaitAdvance` và `awaitAdvance` **không phải chờ interruptible theo kiểu ném InterruptedException**, nên chỉ interrupt không nhất thiết đánh thức họ.

**Mẫu cleanup tốt hơn:** trước hết `phaser.forceTermination()`, sau đó request executor shutdown/cancel theo policy và wait deadline. Dù vậy, nếu worker đang block trong I/O bên ngoài, termination của Phaser **không tự cancel socket/database operation đó**; cần cleanup của thành phần tương ứng.

### 16.3. Đừng tự deregister sau khi đã arrive cùng phase

Nếu task đã gọi `arrive()` cho phase 0 và đang chờ `awaitAdvance(0)`, gọi `arriveAndDeregister()` ở phase 0 từ một code path khác có thể **đếm thêm arrival** sai. Phải quản lý rõ trạng thái của party, không gọi deregister trong `finally` theo một mẫu “đảm bảo mọi khi” không xét current phase.

Trong batch đã mất khả năng tiến, **forceTermination** là cách rõ ràng hơn để báo “toàn job failed”, thay vì đếm bù arrivals để giải thoát các waiters.

## 17. Giám sát mà không biến metrics thành đồng bộ

Một `Phaser` có các phương thức giám sát:

| Phương thức | Cách đọc đúng |
| --- | --- |
| `getPhase()` | Số phase hiện tại; có thể âm nếu terminated |
| `getRegisteredParties()` | Số parties đăng ký **ở thời điểm quan sát** |
| `getArrivedParties()` | Số parties đã arrive trong phase hiện tại |
| `getUnarrivedParties()` | Số parties chưa arrive trong phase hiện tại |
| `isTerminated()` | Phaser kết thúc hay chưa |
| `toString()` | Snapshot dùng cho debug, không phải serialization contract |

Những giá trị này có thể thay đổi ngay khi workers đến/rút. **Không dùng**:

```java
while (phaser.getUnarrivedParties() > 0) {
    // Busy-spin hoặc dựa vào snapshot để quyết định bắt đầu stage mới.
}
```

Đây là **snippet anti-pattern**. Busy-spin có thể đốt CPU mà không mang memory semantics bạn cần; snapshots không thay thế `awaitAdvance`/barrier operations.

Thay vào đó, dùng `arriveAndAwaitAdvance` hoặc `awaitAdvanceInterruptibly`, và dùng counters chỉ để **quan sát, log có giới hạn hoặc metrics**.

### 17.1. Metrics nên thu thập ở service

- Số active jobs, active parties và số phases hoàn tất.
- Phase duration, stage P95/P99 latency.
- Số worker failures, forced terminations, timeouts và interrupts.
- Số jobs chờ barrier lâu bất thường.
- Thread pool active count, queue length/rejections và task age.
- Deadlines theo job, số retries và số outputs chỉ publish sau success.
- Tỷ lệ dynamic register/deregister.
- Với tiered Phaser, contention/throughput trước và sau khi phân cấp.

**Không in log tại mọi arrival ở tải cao** nếu appender blocking hoặc làm lệch benchmark.

## 18. Phaser có hợp với ForkJoinPool và virtual threads không?

`Phaser` dùng được với nhiều loại threads và executors. Điều cần hiểu là **mô hình blocking wait và số participants**.

### 18.1. ForkJoinPool

Nếu các workers trong `ForkJoinPool` chờ tại Phaser, phải bảo đảm pool đủ khả năng chạy những parties chưa arrive. Tài liệu Java nói progress được bảo đảm khi parallelism cho phép số parties có thể đồng thời blocked. Work stealing/compensation có thể hỗ trợ một số tình huống, nhưng **không được coi là phương án phá deadlock do logical cycle**.

Đối với CPU-bound Fork/Join, tốt nhất là thiết kế subtasks độc lập và sử dụng `fork/join` phù hợp. Phaser hữu ích khi thực sự có **nhiều vòng đồng bộ cùng nhóm**; không cần ép mọi reduction thành barrier đa phase.

### 18.2. Java 21+ virtual threads

Virtual threads giúp biểu diễn nhiều tác vụ chờ theo phong cách tuần tự mà không cần một platform thread cho mỗi task, nhưng không tự sửa:

- Một party không bao giờ arrive.
- Coordinator quên arrival.
- Vòng chờ A đợi B, B đợi A.
- Shared lock giữ qua barrier.
- Quota DB connections/network bandwidth.
- Output đã ghi nửa chừng do task fail.

Ví dụ của bài dùng `Executors.newFixedThreadPool` vì cần chạy trên **Java 17+**, không yêu cầu Java 21. Nếu triển khai Java 21+, có thể cân nhắc virtual threads khi workload nhiều waiting tasks, vẫn phải định nghĩa rõ party lifecycle, deadlines và resource limits.

## 19. Cách lựa chọn một reusable barrier

| Tình huống | Cân nhắc |
| --- | --- |
| Có đúng N workers cố định trong nhiều vòng, barrier đơn giản | `CyclicBarrier` hoặc `Phaser` đều có thể phù hợp |
| Số workers có thể tăng/giảm giữa stages | `Phaser` thuận tiện hơn với register/deregister |
| Một nhóm workers chỉ báo đã xong một lần | `CountDownLatch` thường đơn giản hơn |
| Muốn coordinator quan sát phase mà không tăng party count | `Phaser.awaitAdvance(phase)` |
| Có requirement dừng sau K phases | Override `Phaser.onAdvance` |
| Cần thu result của N independent tasks một lần | `Future`/`CompletableFuture.allOf`/`ExecutorService.invokeAll` có thể đơn giản |
| Có nhiều phases với dữ liệu phụ thuộc chéo | `Phaser` thể hiện rõ phase boundary |
| Có rất nhiều parties và contention đo được | Xem xét **tiered Phaser** |
| Workers chờ I/O dài và pool bị bão hòa | Chọn executor/asynchronous model phù hợp, không chỉ tăng parties |
| Cần rollback dữ liệu khi một worker lỗi | Barrier không giải quyết; cần transaction/output staging |

### 19.1. Đừng nhầm Phaser với “phased task scheduler”

Phaser biết **khi nào một phase hoàn tất**, nhưng nó không tự quyết định mỗi worker phải làm gì, không phân bổ load, không có queue input, không ghi trật tự sự kiện và không lưu kết quả. Những việc đó do ứng dụng hoặc executor đảm nhiệm.

## 20. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `new Phaser(3)` nhưng chỉ hai workers gọi arrival | Hai workers chờ vô hạn | Registered parties phải khớp participants |
| Coordinator đăng ký làm party nhưng chỉ đợi Futures | Workers bị chặn ở barrier | Coordinator phải arrive, hoặc chỉ await như observer |
| Một party gọi `arrive` hai lần cùng phase | Counter bị sai; có thể phát hiện trễ | Track per-party phase/ownership |
| Dùng `arrive()` và nghĩ nó tự block | Worker đi tiếp trước những người khác | Gọi `awaitAdvance(oldPhase)` nếu cần đợi |
| Dùng `awaitAdvance` của observer để tính một arrival | Phase không tiến nếu còn thiếu party | Party gọi arrive, observer chỉ await |
| Quên deregister worker đã rời workflow | Những phase sau vẫn đợi worker vắng mặt | `arriveAndDeregister` đúng thời điểm |
| Deregister hai lần “cho chắc” | Lỗi đếm parties/unarrived | Một exit transition có kiểm soát |
| Register worker mới nhưng submit task thất bại | Có party không ai arrive | Failure supervisor, forceTermination/recover |
| Để pool size 2 phục vụ 3 parties đều chờ | Third task không được schedule | Bảo đảm mọi arrival có đường thực thi |
| Giữ lock khi chờ barrier | Có thể tạo wait-for cycle | Thả lock trước barrier |
| Đợi `awaitAdvance` và không có timeout/policy | Workflow có thể treo lâu | Deadline, error signal, forceTermination |
| Nghĩ timeout tự deregister party | Counts giữ nguyên, phase không tiến | Explicit recovery |
| Dùng `shutdownNow` mà không terminate phaser | Noninterruptible waiters có thể còn chờ | forceTermination trước rồi shutdown |
| Dùng kết quả phase âm như success mọi trường hợp | Che mất lỗi hoặc partial output | Phân biệt expected vs forced termination |
| Override `onAdvance` để gọi I/O blocking | Cản trở phase advance | Hook nhanh, nonblocking |
| Gọi arrival/registration từ trong `onAdvance` | API không quy định hậu quả | Không thao tác Phaser từ hook |
| Nghĩ Phaser tự rollback output | Dữ liệu có thể sửa nửa chừng | Output staging + publish after success |
| Dùng `getUnarrivedParties` để busy-spin | CPU overhead, snapshot racy | Dùng await methods |
| Coi `getPhase` luôn tăng vô hạn | Có thể âm/overflow wrap | Không dùng làm global sequence id vô hạn |
| Đăng ký mỗi leaf của một tree nhưng chỉ vài worker threads | Starvation | Thiết kế parties và execution capacity |
| Tạo tiered tree mọi khi dù chỉ có vài workers | Overhead/code phức tạp | Đo contention rồi mới tier |
| Reuse terminated Phaser cho batch mới | Không hoạt động như barrier mới | Tạo instance mới |
| Tham gia đúng phase nhưng đọc dữ liệu trước barrier | Data race/partial results | Produce → barrier → consume |
| Nghĩ `volatile int[]` bảo vệ mọi element | Reference volatile không làm elements atomic | Partition ownership và phase happens-before |

## 21. Checklist code review

1. Có bao nhiêu **registered parties** ở mỗi phase? Ai sở hữu từng party?
2. Có worker nào có thể mất khả năng arrive (exception, rejected submit, cancel) không?
3. Có một **coordinator** tham gia barrier? Nếu có, coordinator thực sự arrive đúng lúc không?
4. Nếu main chỉ muốn theo dõi, đã dùng observer await thay vì register thêm party chưa?
5. Mỗi party có arrive **đúng một lần trong từng phase** không?
6. Các workers có gọi `arriveAndAwaitAdvance` trước khi phụ thuộc dữ liệu stage trước không?
7. Có xử lý `nextPhase < 0` và phân biệt expected termination với forced failure không?
8. Worker rời nhóm có gọi `arriveAndDeregister` **đúng pha và đúng một lần** không?
9. Có đăng ký đủ parties trước khi bắt đầu stage hoặc định nghĩa rõ dynamic join points không?
10. `bulkRegister(n)` có được dùng với n hợp lệ? Có ai bị bỏ sót không?
11. Executor có đủ capacity để các parties bắt buộc tới barrier không?
12. Có nguy cơ queued tasks chưa chạy vì các threads đang block ở barrier không?
13. Có giữ lock cần bởi worker khác qua một `await`/barrier không?
14. Có tránh gọi blocking I/O hoặc vòng chờ trong `onAdvance` không?
15. Có tránh gọi chính các phương thức arrival/registration trong `onAdvance` không?
16. Nếu cần timeout, có dùng `arrive()` rồi `awaitAdvanceInterruptibly` đúng cách không?
17. Có biết timeout không sửa counts hoặc cancel workers không?
18. Khi một task lỗi, có `forceTermination` và failure propagation rõ không?
19. Có đảm bảo `shutdownNow` không phải cơ chế duy nhất giải phóng noninterruptible waiters không?
20. Có không double-arrive sau exception/timeout không?
21. Có không publish output nếu chưa kết thúc tất cả stages thành công không?
22. Có phân vùng dữ liệu để tránh race trong cùng stage không?
23. Có tin vào happens-before qua phase boundary thay vì chỉ đọc snapshot counts không?
24. Có xử lý `getPhase` âm sau termination và số phase quay vòng về 0 không?
25. Có không dùng terminated phaser cho job mới không?
26. Có theo dõi parties/phase duration/timeouts và thread pool state để phát hiện starvation không?
27. Có sử dụng tiered Phaser chỉ khi contention và quy mô xứng đáng không?
28. Có không đăng ký root party thủ công cho từng worker khi child đã đại diện parent không?
29. Có chính sách graceful shutdown, cancel jobs và resource ownership không?
30. Có kiểm thử các tình huống một worker fail, một worker không tới, dynamic join/leave và expected termination không?

## 22. Bài tập

**Bài 1 — Ba giai đoạn cơ bản.** Chạy `PhaserMultiStageDemo`; vẽ các phase 0→1→2→3 và chỉ ra khi nào mỗi worker được phép bắt đầu stage mới.

**Bài 2 — Thay đổi số workers.** Đổi số workers thành 4 trong `PhaserMultiStageDemo` và điều chỉnh kích thước mảng/pool. Dự đoán các stage sums trước khi chạy; kiểm tra tính đúng không phụ thuộc thứ tự schedule.

**Bài 3 — Coordinator party.** Chạy `PhaserCoordinatorDemo`. Giải thích vì sao main phải arrive hai lần. Nếu main chỉ `Future.get` mà không arrive, vẽ vòng chờ.

**Bài 4 — Observer.** Chạy `PhaserObserverDemo`, bổ sung một observer thứ hai không đăng ký. Vì sao `getRegisteredParties()` vẫn là 2?

**Bài 5 — Arrival tách rời.** Thay `arriveAndAwaitAdvance` bằng `int phase=arrive(); awaitAdvance(phase)`. Kiểm tra chỉ có **một arrival**/party/phase.

**Bài 6 — Dynamic membership.** Chạy `PhaserDynamicPartiesDemo` rồi đăng ký hai workers cùng lúc ở phase thứ hai. Đảm bảo đủ threads và chính sách cleanup.

**Bài 7 — Worker rút sớm.** Một worker chỉ làm stage 0 rồi deregister. Thiết kế sao cho các worker còn lại **không phải chờ worker đã rút** ở stage 1.

**Bài 8 — Timeout.** Chạy `PhaserTimeoutRecoveryDemo`. Vì sao `getUnarrivedParties()==1` ngay sau timeout? Khi nào nên `forceTermination`?

**Bài 9 — Failure.** Chạy `PhaserFailureRecoveryDemo`. Thay exception bằng lỗi validation và ghi trạng thái job FAILED. Phân biệt terminate barrier với cancel worker.

**Bài 10 — onAdvance.** Chạy `PhaserOnAdvanceDemo` rồi đổi điều kiện dừng thành 5 phases. Không dùng `getPhase==5` như kết quả bắt buộc sau termination.

**Bài 11 — Pipeline memory visibility.** Chạy `PhaserPipelineDemo`. Thêm bước stage 2 tính tổng `combined`; hãy chỉ đọc dữ liệu sau khi phase 1 đã hoàn tất.

**Bài 12 — Data race trong một phase.** Cố tình cho hai workers cùng ghi `produced[0]++` trong một test sandbox, nhận diện race, sau đó sửa bằng disjoint ownership/atomic operation.

**Bài 13 — Tiered groups.** Chạy `PhaserTieredDemo` với 3 child groups, mỗi group 2 workers. Xác minh parent parties ban đầu bằng **số groups**, không phải số workers.

**Bài 14 — Shutdown.** Thiết kế coordinator với `try/finally`, `forceTermination`, `shutdownNow` và bounded `awaitTermination`; kiểm thử khi một worker lỗi trước arrival.

**Bài 15 — Executor starvation.** Phân tích mô hình 3 parties nhưng pool 2 threads. Không tạo một integration test treo vô hạn; dùng timeout/failure watchdog và trình bày cách thay đổi năng lực chạy.

**Bài 16 — Per-party ownership.** Tạo một wrapper record chứa ID của worker, phase expected và flag registered. Đảm bảo không double-arrive khi có retry hoặc exception.

**Bài 17 — Metrics.** Thu phase duration và số worker failures. Vì sao `getArrivedParties` chỉ nên dùng giám sát, không làm điều kiện bắt đầu stage tiếp?

**Bài 18 — CyclicBarrier comparison.** Viết cùng bài pipeline với `CyclicBarrier` và `Phaser`. Chỉ ra khi nào fixed party count đơn giản hơn, và khi nào dynamic registration quan trọng.

**Bài 19 — Virtual threads.** Trên Java 21+, thiết kế workers bằng virtual threads; phân tích vì sao logic missing arrival/deadlock vẫn xảy ra nếu coordinator quên arrive.

**Bài 20 — Production workflow.** Thiết kế xử lý dữ liệu ba stages với bounded executor, task failures, timeouts, output staging, graceful shutdown và monitoring; chỉ công bố kết quả sau **toàn bộ stages thành công**.

## 23. Tóm tắt

- `Phaser` là **barrier tái sử dụng**, cho phép một nhóm công việc đồng bộ qua nhiều giai đoạn và **thay đổi số participants**.
- Mỗi **registered party phải arrive đúng một lần mỗi phase**. Phaser không theo dõi thread identity; ứng dụng tự quản lý ownership.
- `arriveAndAwaitAdvance` vừa báo hoàn tất phase hiện tại vừa chờ sang phase mới. `arrive` **không chờ**; `awaitAdvance(phase)` chỉ chờ phase khác, có thể dùng cho observer không đăng ký.
- `register`/`bulkRegister` và `arriveAndDeregister` hỗ trợ nhóm thay đổi giữa các stages, nhưng phải quản lý thời điểm join/leave và submission failures.
- Khi cần timeout/interrupt, dùng `arrive()` rồi `awaitAdvanceInterruptibly` và có **recovery policy**. Timeout không tự sửa counts.
- `onAdvance` là hook lúc phase tiến, có thể quyết định terminate; giữ hook ngắn và tránh gọi phương thức đăng ký/arrival từ bên trong.
- Default termination xảy ra khi không còn registered parties do deregistration; `forceTermination` là tín hiệu kết thúc khi có lỗi/shutdown và **không rollback/cancel công việc**.
- Phaser tạo **happens-before qua phase boundary**: producer hoàn thành rồi arrive; consumer chỉ đọc ở phase tiếp theo. Nó không sửa các races trong cùng phase.
- Executor phải có đủ khả năng cho mọi party tới barrier; thiếu workers, coordinator quên arrive hoặc giữ lock sai đều có thể gây deadlock.
- Tiered Phaser có ích nếu nhóm lớn có contention đo được, nhưng không phải tối ưu bắt buộc.
- Toàn bộ ví dụ sử dụng **API Java 17+ còn hiệu lực**, có thể chạy trên JDK hiện đại mà không cần thư viện bên ngoài.

## Tài liệu chính thức

- [Phaser — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html): registration, arrival, waiting, memory effects, termination, tiered phasers và ví dụ đồng bộ nhiều phase.
- [Phaser — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): contract tương ứng trên Java 17.
- [CyclicBarrier — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): fixed-party reusable barrier và các khác biệt.
- [CountDownLatch — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): một sự kiện đồng bộ đếm về 0.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future, shutdown/shutdownNow, awaitTermination.
- [Future — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): chờ kết quả, interruption và timeout.
- [ForkJoinPool — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing và các tình huống waiting/blocking.
- [Java Language Specification, Chapter 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): memory model và happens-before.
