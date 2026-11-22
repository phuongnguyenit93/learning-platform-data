# Phaser cho số lượng participant linh hoạt trong Java Concurrency

> **Bối cảnh:** `java.util.concurrent.Phaser` là synchronizer của Java SE cho các công việc trải qua **nhiều giai đoạn (phases)**, trong đó **số lượng thread/task tham gia có thể thay đổi** bằng `register()`, `bulkRegister()` và `arriveAndDeregister()`. Bài thuộc **Synchronizers**, chỉ bàn Java concurrency nói chung; nội dung đặc thù về Spring được đặt ở chương khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu khái niệm **phase**, **registered party**, **arrived/unarrived parties** và **phase advance**.
- Giải thích lý do một barrier có số lượng participant cố định không phải lúc nào cũng phù hợp khi tasks ra/vào ở runtime.
- Chọn đúng `register()`, `bulkRegister(n)`, `arrive()`, `arriveAndAwaitAdvance()`, `arriveAndDeregister()`, `awaitAdvance(phase)` và `awaitAdvanceInterruptibly(...)`.
- Phân biệt **đánh dấu đã tới barrier** với **chờ barrier mở**, và phân biệt **deregister** với chỉ rời method hoặc kết thúc thread.
- Thiết kế protocol đăng ký trước khi cho task bắt đầu, deregister chính xác một lần, có coordinator và tránh phase bị treo.
- Giải thích **đăng ký participant trong lúc phase đang diễn ra** có thể ảnh hưởng phase hiện tại, không mặc nhiên là “đăng ký cho vòng kế tiếp”.
- Sử dụng `onAdvance` để kiểm soát chính sách kết thúc, đồng thời nhận biết mặc định Phaser kết thúc khi số registered parties về 0.
- Hiểu cách exception, interruption, timeout và `forceTermination()` ảnh hưởng liveness.
- Viết và chạy chương trình Java 17 có **hai participants ban đầu, một participant tham gia sau phase 0, rồi những participants lần lượt deregister**.
- Phân tích giới hạn của Phaser: không tự quản lý thread, không tự rollback side effects, không thay thế event queue hoặc transaction.

**Tư tưởng chính:** Phaser không “đếm thread đang sống”; nó quản lý **những bên đã đăng ký (parties)** cùng **lượt arrival của họ trong từng phase**. Phase chỉ tiến khi tất cả parties còn đăng ký cần tới phase ấy đã arrive hoặc deregister theo protocol.

## 2. Vấn đề: số lượng participants có thể thay đổi

Giả sử một chương trình xử lý dữ liệu qua ba giai đoạn:

1. Các workers đọc và parse input.
2. Một số workers đi tiếp để transform dữ liệu; một số rút vì hết việc.
3. Một worker mới được thêm để validate hoặc aggregate, rồi tất cả cùng chờ giai đoạn kết thúc.

Nếu có đúng 3 workers từ đầu đến cuối, một barrier với party count cố định có thể đủ. Nhưng ở pipeline động:

- Có worker chỉ tham gia những phase đầu.
- Có worker được khởi tạo sau phase đầu.
- Có phase cần nhiều workers hơn phase trước.
- Có worker hoàn tất công việc riêng và **phải rút** để không ngăn những phase còn lại.

`Phaser` hỗ trợ **dynamic registration và deregistration**. Đây là khác biệt quan trọng so với `CyclicBarrier`, nơi số parties được cung cấp từ constructor và không được tăng/giảm trực tiếp bằng một cặp `register/deregister`.

### Hình dung một pha

```text
PHASE = 3, registered = 4, unarrived = 4

Worker A: làm bước của phase 3 ---> arrive ----\
Worker B: làm bước của phase 3 ---> arrive -----+--> advance sang phase 4
Worker C: làm bước của phase 3 ---> arrive -----|
Coordinator: chuẩn bị barrier ------> arrive ----/

Nếu Worker C không còn tham gia phase sau:
Worker C: arriveAndDeregister() thay vì arrive()
=> tính arrival cho phase hiện tại VÀ giảm registered parties cho các phase sau
```

Bản chất của mô hình không phải “bốn callbacks cần chạy” mà là **bốn parties đã đăng ký có trách nhiệm arrive**. Một party đã registered nhưng quên báo arrive có thể khiến phase chờ vô hạn, bất kể CPU rảnh hay số task khác đã xử lý xong.

## 3. Đọc các khái niệm cơ bản

| Thuật ngữ | Ý nghĩa | API quan sát |
|---|---|---|
| **Phase** | Chỉ số giai đoạn hiện tại; thông thường bắt đầu từ 0 | `getPhase()` |
| **Registered parties** | Số registrations hiện tham gia vào Phaser | `getRegisteredParties()` |
| **Unarrived parties** | Số registrations chưa báo arrival ở phase hiện tại | `getUnarrivedParties()` |
| **Arrived parties** | Số registrations đã báo arrival ở phase hiện tại | `getArrivedParties()` |
| **Arrival** | Tín hiệu một party đã hoàn thành phần việc của phase | `arrive()` |
| **Advance** | Chuyển sang phase kế tiếp sau khi đủ arrivals | `arriveAndAwaitAdvance()`, arrival cuối |
| **Deregistration** | Arrival của phase hiện tại và rút một registration cho về sau | `arriveAndDeregister()` |
| **Termination** | Phaser không còn vận hành như barrier bình thường | `isTerminated()`, `forceTermination()`, `onAdvance` |

Một registration **không được tự động gắn với một `Thread` cụ thể**. Phaser không ghi nhận một Java thread ID và bắt buộc chính thread đó phải arrive. Đó là trách nhiệm của giao thức ứng dụng. Bạn có thể đăng ký trong coordinator và yêu cầu worker báo arrival, nhưng phải chắc chắn mỗi registration có đúng một arrival/deregistration cho từng phase cần thiết.

### Constructor

```java
Phaser phaser = new Phaser();    // Không có party đăng ký ban đầu.
Phaser withMain = new Phaser(1); // Main/coordinator là một party.
Phaser fixedInitially = new Phaser(3);
```

Đây là đoạn code trong một method với `import java.util.concurrent.Phaser;`. Có thể bắt đầu từ 0 và đăng ký sau, nhưng nhiều workflow dễ kiểm soát hơn nếu coordinator **giữ một registration** để phase không tự advance khi còn đang thêm participants.

**Lưu ý:** mặc định `Phaser.onAdvance` trả true khi `registeredParties == 0`, dẫn đến termination khi phase advance và không còn parties. Một Phaser chưa có party đăng ký ngay khi vừa tạo không đồng nghĩa mọi method của nó sẽ tự mang trạng thái terminated theo mọi lộ trình; không suy đoán từ `getRegisteredParties()==0` mà bỏ qua lifecycle contract. Để thấy termination chính xác, dùng `isTerminated()`.

## 4. Cấu trúc phase advance

Một phase được mở khi các registrations đang áp dụng cho phase đó **đều báo arrive hoặc deregister**. Một party báo tới barrier là một arrival.

Ví dụ coordinator + hai workers, tất cả đã registered:

```text
Phase 0: registered = 3
  A.arrive()       -> unarrived 3 -> 2
  B.arrive()       -> unarrived 2 -> 1
  Main.arrive()    -> unarrived 1 -> 0
                     advance: phase 0 -> phase 1
Phase 1: các bên còn registered có obligation arrival mới
```

Khi phase tiến, unarrived count được thiết lập lại theo số registered parties của phase mới, ngoại trừ termination policy có thể khiến Phaser ngừng.

**Không lấy `getArrivedParties()` rồi cộng số thủ công để điều phối**. Các getters trả **snapshot có thể thay đổi ngay lập tức**; caller khác có thể arrive, deregister hoặc register bất kỳ lúc nào theo giao thức của chương trình.

## 5. Các API quan trọng và hành vi

### `register()`

```java
int phaseAtRegistration = phaser.register();
```

Đăng ký thêm một party. Giá trị trả về là phase mà registration áp dụng theo contract; nếu phaser đã terminated, phương thức có thể trả chỉ số phase âm phù hợp với trạng thái termination. **Đăng ký không tạo thread hoặc khởi chạy task**.

Quan trọng: khi Phaser còn active, registration có thể tham gia **phase hiện tại**. Nếu register trong lúc những parties cũ đang chờ phase advance, participant mới có nghĩa vụ arrive để phase hoàn tất.

### `bulkRegister(int parties)`

```java
phaser.bulkRegister(3);
```

Tăng số registrations một lần, hữu ích khi biết cần N workers tham gia cùng phase. `parties` không âm; nếu `parties == 0`, method không thêm registration. Đăng ký quá giới hạn nội bộ có thể gây `IllegalStateException`.

Nếu cần đăng ký cả một batch workers **trước khi submit tasks**, `bulkRegister` thể hiện rõ invariant. Tránh mở cho workers thực thi khi chưa đăng ký đầy đủ nghĩa vụ của họ.

### `arrive()`

```java
int arrivedAtPhase = phaser.arrive();
```

Đánh dấu một registration đã tới barrier của phase hiện tại **nhưng không chờ** phase tiến. Phương thức trả về phase khi arrival được ghi nhận (không nhất thiết là phase sau đó).

Một thread có thể dùng `arrive` rồi làm việc khác, nhưng nếu cần chờ, nên dùng `awaitAdvance(arrivedAtPhase)`. **Không gọi `arrive` hai lần cho cùng registration trong cùng một phase**; có thể gây `IllegalStateException` hoặc làm lệch protocol.

### `arriveAndAwaitAdvance()`

```java
int nextPhase = phaser.arriveAndAwaitAdvance();
```

Vừa arrive, vừa chờ toàn bộ parties cần thiết của phase hoàn thành. Khi hoạt động bình thường, return phase sau advance (ví dụ 1 nếu rời phase 0). Đây là phương thức **không đáp ứng interruption theo cách ném InterruptedException**; nếu cần timeout hoặc interruptibility, xem `awaitAdvanceInterruptibly` kết hợp `arrive`.

### `arriveAndDeregister()`

```java
int oldPhase = phaser.arriveAndDeregister();
```

Báo hoàn tất phase hiện tại **và rút registration**. Đây là điều worker nên làm ở phase cuối cùng nó tham gia. Nó **không chờ** các parties còn lại, và giá trị trả về liên quan phase lúc deregister, không phải giấy chứng nhận mọi task khác đã hoàn tất.

Nếu vừa cần rút vừa cần đợi phase mở, có thể thực hiện `int p = phaser.arriveAndDeregister(); phaser.awaitAdvance(p);` trong protocol phù hợp; sau deregister thread trở thành **observer**, không còn party cần arrive.

### `awaitAdvance(int phase)`

```java
int advanced = phaser.awaitAdvance(phase);
```

Chờ đến khi current phase khác giá trị `phase` được truyền. API này **không tự arrive** và **không yêu cầu thread gọi phải là party**. Vì vậy hữu ích cho observer hoặc sau khi đã `arrive`.

Lưu ý: nếu truyền một phase đã cũ, method có thể return ngay; nếu truyền phase hiện tại nhưng không có bên nào báo arrive, có thể chờ mãi. Không nhầm nó với `arriveAndAwaitAdvance`.

### `awaitAdvanceInterruptibly(int phase, ...)`

Có hai overload:

```java
phaser.awaitAdvanceInterruptibly(phase);
phaser.awaitAdvanceInterruptibly(phase, 500, TimeUnit.MILLISECONDS);
```

Đây là code minh họa bên trong method, cần import `TimeUnit` và khai báo/xử lý `InterruptedException`; bản có timeout còn có thể ném `TimeoutException`.

**Điểm tinh tế:** gọi `awaitAdvanceInterruptibly` **không tự arrive hoặc deregister**. Thông thường party làm `int p = phaser.arrive();` trước, sau đó chờ interruptibly. Nếu thời hạn chờ hết hoặc thread bị interrupt, party đã arrived ở phase ấy vẫn registered cho phase tiếp theo. Phải có shutdown/cancellation protocol riêng để tránh mất registration hoặc workers bỏ đi trong khi phase mới cần họ.

### `forceTermination()`

Dùng để đưa Phaser vào trạng thái terminated, giải phóng những threads đang đợi advance theo contract. Nó **không hủy/interrupt tác vụ đang tính toán**, không tự rollback hay gọi `ExecutorService.shutdownNow()`.

Sau termination, các method về phase có thể trả phase âm để báo trạng thái; application phải kiểm tra và thoát, thay vì tiếp tục loop như thể phase vẫn tăng bình thường.

## 6. Điều làm Phaser linh hoạt: parties vào và ra giữa các phase

Giả sử hai workers A/B cùng coordinator tham gia phase 0. Sau phase 0:

- A và B còn một bước cuối ở phase 1 rồi sẽ rút.
- Coordinator đăng ký thêm C trước khi đóng phase 1.
- C chỉ làm phần việc của phase 1 và rút.
- Coordinator đến barrier phase 1, đợi đủ A/B/C.
- Sau phase 1, chỉ còn coordinator registered.
- Coordinator rút, dẫn tới termination mặc định.

```text
Phase 0:
  Main registered + A + B       = 3 parties
  A, B, Main all arrive         -> phase 1

Phase 1:
  Main + A + B, register C      = 4 parties
  A, B, C arriveAndDeregister  -> chỉ còn Main
  Main arriveAndAwaitAdvance   -> phase 2

After phase 1:
  Main only                     = 1 registered
  Main arriveAndDeregister      -> no parties; terminated
```

Đây là mô hình cho chương trình Java 17 dưới đây. **Số registrations đang được báo giữa các bước là trạng thái logic tại mốc được mô tả**, không khẳng định mọi getter lấy đồng thời đều có thể chụp một snapshot nguyên tử của toàn bộ hệ thống.

### “Đăng ký giữa phase” có nghĩa gì?

Nếu coordinator gọi `phaser.register()` khi phase 1 **đã mở và chưa advance**, C phải có một arrival cho phase 1. Nó không tự được “dời sang phase 2” chỉ vì C là người mới.

Với ứng dụng cần participant tham gia **chỉ từ phase kế tiếp**, tốt nhất dùng một coordination protocol: coordinator giữ registration, chờ phase hiện tại advance xong, sau đó register newcomers **trước khi coordinator cho phase kế tiếp hoàn tất**. Phải tránh race với những workers có thể đã chạy đến arrival của phase mới.

## 7. Chương trình Java 17 chạy được

Chương trình minh họa **dynamic registration/deregistration** với ba worker tasks và main coordinator. Những worker đầu tham gia phase 0, rồi phase 1; worker mới chỉ tham gia phase 1. `AtomicInteger` đếm công việc trong từng phase; `Future.get()` bảo đảm main đã đợi các tasks xong trước khi in counters.

Tạo file **`DynamicPhaserDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DynamicPhaserDemo {
    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1); // Main owns one registration.
        ExecutorService pool = Executors.newFixedThreadPool(3);
        AtomicInteger phase0Work = new AtomicInteger();
        AtomicInteger phase1Work = new AtomicInteger();
        List<Future<?>> tasks = new ArrayList<>();

        try {
            phaser.bulkRegister(2);
            for (int i = 0; i < 2; i++) {
                tasks.add(pool.submit(() -> {
                    phase0Work.incrementAndGet();
                    phaser.arriveAndAwaitAdvance(); // End of phase 0
                    phase1Work.incrementAndGet();
                    phaser.arriveAndDeregister(); // Exit during phase 1
                }));
            }
            int afterFirstBarrier = phaser.arriveAndAwaitAdvance();
            System.out.println("afterPhase0=" + afterFirstBarrier);

            phaser.register(); // Join before main closes phase 1.
            tasks.add(pool.submit(() -> {
                phase1Work.incrementAndGet();
                phaser.arriveAndDeregister(); // Only participates in phase 1
            }));

            int afterSecondBarrier = phaser.arriveAndAwaitAdvance();
            for (Future<?> task : tasks) task.get();
            System.out.println("afterPhase1=" + afterSecondBarrier);
            System.out.println("phase0Workers=" + phase0Work.get());
            System.out.println("phase1Workers=" + phase1Work.get());
            System.out.println("remainingParties=" + phaser.getRegisteredParties());

            phaser.arriveAndDeregister(); // Main exits, zero registrations.
            System.out.println("terminated=" + phaser.isTerminated());
        } finally {
            phaser.forceTermination();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not stop");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 DynamicPhaserDemo.java
java DynamicPhaserDemo
```

**Stdout đã được biên dịch/chạy xác minh bằng Java 17:**

```text
afterPhase0=1
afterPhase1=2
phase0Workers=2
phase1Workers=3
remainingParties=1
terminated=true
```

### Giải thích từng đoạn

**`new Phaser(1)`:** main giữ một registration. Khi hai workers còn chưa đến barrier, main có thể gọi `arriveAndAwaitAdvance` để chờ. Khi workers đã tới phase 0, phase mới mở.

**`bulkRegister(2)` trước khi submit:** hai nghĩa vụ arrival được đăng ký **trước** khi bất kỳ worker task nào có thể chạy. Đây là cách tránh lỗi worker chạy đến arrival khi chưa được tính, hoặc coordinator advance trong lúc đang còn submit workers.

**`arriveAndAwaitAdvance()` trong hai workers:** mỗi worker hoàn thành công việc phase 0 rồi chờ toàn bộ participants (A, B, main) cùng tới barrier. Sau khi phase 0 advance, A/B làm phase 1.

**`phaser.register()` sau barrier đầu:** main đăng ký thêm C khi phase 1 đã bắt đầu nhưng main vẫn giữ một nghĩa vụ arrival, nên phase 1 chưa thể advance trước khi C được đăng ký.

**`arriveAndDeregister()` ở A/B/C:** họ hoàn thành phase 1 rồi rút khỏi các phase sau. Đó là lý do sau phase 1 chỉ còn main.

**`Future.get()`:** main chờ tất cả worker task hoàn thành. Nhờ đó counters ở output không phụ thuộc worker scheduling dù các tác vụ chạy đồng thời.

**`main.arriveAndDeregister()`:** sau khi mọi workers đã rút, main rút cuối cùng. Với default `onAdvance`, khi registered parties về 0, Phaser terminated; `isTerminated()` true.

**`finally`:** `forceTermination()` và `shutdownNow()` là cleanup cho demo ngay cả khi main gặp lỗi. Đây là chiến lược fail-fast cho bài ngắn; production nên chọn graceful shutdown, timeout và cancellation rõ, không coi forceTermination là cách “tự dọn mọi task”.

## 8. Tại sao chương trình trên có kết quả xác định?

Không có dòng print nào phụ thuộc vào thứ tự worker A hoặc B được scheduler chạy trước:

- `afterPhase0=1` đến từ ranh giới phase 0 của main, đảm bảo các obligations ban đầu đã arrived.
- Hai workers A/B mỗi worker increment `phase0Work` một lần trước arrival; `phase0Workers=2` sau khi đã await phase và Future completion.
- Trong phase 1, A/B mỗi người increment một lần, C cũng increment một lần. `phase1Workers=3` sau khi cả ba Future hoàn tất.
- A/B/C đều deregister, nên `remainingParties=1` chỉ còn main.
- Main rút party cuối khiến `terminated=true` theo termination policy mặc định.
- `AtomicInteger` giúp increments an toàn nếu dùng cùng một biến từ nhiều threads.
- `Future.get()` bảo đảm exception từ worker không bị nuốt và cung cấp memory visibility cho main đối với công việc đã hoàn thành.

Nếu thay `AtomicInteger` bằng `int counter++` từ nhiều workers, nguy cơ lost update có thể xuất hiện bất kể Phaser barriers có đúng, vì nhiều workers vẫn có thể tăng counter **cùng lúc trong một phase**.

## 9. Vì sao không dùng Thread.sleep để chờ phase?

Một cách sai:

```java
// Không dùng sleep làm protocol đồng bộ.
Thread.sleep(200);
System.out.println(phaser.getPhase());
```

Đây là snippet minh họa trong method `throws InterruptedException`. Ngủ 200 ms không đảm bảo workers đã hoàn tất, không làm nghĩa vụ arrival biến mất, và không cung cấp ranh giới happens-before thích hợp.

Thay vào đó:

- Party có công việc và cần đợi: `arriveAndAwaitAdvance()`.
- Party đã arrive rồi cần chờ với timeout: `awaitAdvanceInterruptibly(phase, timeout, unit)`.
- Observer không phải party chỉ cần biết phase thay đổi: `awaitAdvance(phase)` hoặc bản interruptible.
- Caller cần biết **task đã hoàn tất thật sự** (không chỉ đến barrier): `Future.get()`/`join()` với policy timeout.

Thời gian chỉ nên dùng cho timeout/deadline và mô phỏng workload trong test, không làm synchronization contract.

## 10. Khác biệt giữa arrive(), awaitAdvance() và arriveAndAwaitAdvance()

Ba lời gọi có quan hệ nhưng không tương đương:

```java
int phase = phaser.arrive();
doIndependentWork();
phaser.awaitAdvance(phase);
```

Đây là đoạn code minh họa trong method. Nó tương đương về ý tưởng “arrive rồi chờ”, nhưng có khoảng thời gian chạy công việc khác giữa hai lời gọi. Thread đã **đánh dấu arrived**, không có quyền arrive lần nữa trong cùng phase chỉ vì đã làm thêm việc.

Ngược lại:

```java
int nextPhase = phaser.arriveAndAwaitAdvance();
```

Vừa arrive vừa chờ barrier ở đúng một operation. Nếu không có công việc nào cần làm trong khoảng chờ, thường dễ hiểu hơn.

**Nguy cơ:** nếu thread gọi `awaitAdvance(currentPhase)` nhưng chưa arrive cho registration của mình và không có ai khác có thể thực hiện arrival thay nó, phase không thể advance. Đây là deadlock logic: nó đang đợi **chính arrival mà nó còn nợ**.

## 11. Đăng ký trước khi khởi chạy task: tránh “arrival without registration”

Nếu khởi chạy task trước:

```java
// Sai về thứ tự responsibility registration:
pool.submit(() -> {
    doWork();
    phaser.arriveAndDeregister();
});
phaser.register(); // Có thể xảy ra quá muộn.
```

Đây là snippet minh họa nguy hiểm, các biến/method được định nghĩa bên ngoài.

Một worker có thể chạy đến `arriveAndDeregister()` **trước khi main đăng ký nó**. Tùy state hiện tại, lời arrive có thể làm sai obligation của party khác hoặc ném lỗi; ý định “task này có một registration riêng” không được bảo vệ.

Cách đúng:

```java
phaser.register();
Future<?> task = pool.submit(() -> {
    try {
        doWork();
    } finally {
        phaser.arriveAndDeregister();
    }
});
```

Đây là đoạn code minh họa trong method với `pool` là `ExecutorService`, import `Future`; khi task chạy, registration đã tồn tại. **Nhưng đoạn này cần được bổ sung error policy:** nếu `submit` bị reject hoặc task **chưa từng bắt đầu** do pool shutdown, registration đã được thêm nhưng không có worker deregister; coordinator cần rollback registration theo protocol an toàn. Nếu task ném lỗi, finally deregister để tránh giữ barrier, nhưng không được coi task nghiệp vụ thành công chỉ vì barrier được mở.

### Đăng ký trong task hay coordinator?

Có thể đăng ký từ worker, nhưng nếu coordinator muốn chờ “tất cả N tasks mới submit” thì đăng ký khi worker bắt đầu có race: coordinator có thể tới barrier trước khi worker đăng ký. Một coordinator giữ một party và **bulkRegister(N) trước submit** giúp rõ ràng hơn.

Mọi đường như rejection, cancellation trước khi task chạy và pool failure đều phải có kế hoạch rút các registrations **chưa được worker nhận trách nhiệm**.

## 12. Đăng ký muộn và race khi phase đang tiến

Một lỗi khác:

```java
// Main không giữ phase mở, workers có thể advance sớm.
Phaser phaser = new Phaser(2);
startTwoWorkers(phaser);
// Sau một khoảng thời gian:
phaser.register();  // Không có nghĩa chắc chắn join phase mong muốn.
```

Đây là snippet minh họa, `startTwoWorkers` được định nghĩa bên ngoài. Nếu hai workers đã arrive và phase advance, registration mới có thể gắn với phase **khác** so với điều bạn kỳ vọng.

Một thiết kế tốt:

- Tạo **registration của coordinator** để chặn phase advance cho đến khi setup hoàn tất.
- Định nghĩa rõ “join current phase” hay “join next phase”.
- Đặt phase boundary và registration trong một **protocol có owner**; tránh nhiều components tự register tùy lúc.
- Trước khi báo “phase finished”, cần kiểm tra **không còn pending registration/submission nào** theo logic của caller, không chỉ nhìn current unarrived snapshot.

Không có một API “registerForExactlyPhaseNAtFutureTime” với cùng semantics như một task scheduler. Nếu cần join theo kế hoạch phức tạp, dùng coordinator quản lý khi nào registration xảy ra.

## 13. arriveAndDeregister(): rời giai đoạn mà không chặn các vòng sau

Một party chỉ cần tham gia hai phase nhưng coordinator sẽ còn chạy ba phase. Sau lần cuối, nó nên:

```java
// Phase cuối worker còn tham gia:
doLastStage();
phaser.arriveAndDeregister();
```

Đây là snippet minh họa trong method.

Nếu nó chỉ gọi `arriveAndAwaitAdvance()` ở phase cuối rồi return khỏi task **mà không deregister**, phaser vẫn coi registration tồn tại ở phase tiếp theo. Coordinator có thể bị treo vì đợi một party đã không còn code để arrive.

**Cần phân biệt:**

- `arrive()`: vẫn registered, còn obligation ở phase sau.
- `arriveAndAwaitAdvance()`: vẫn registered, đã arrive và đợi phase mới.
- `arriveAndDeregister()`: rút party cho các phase sau, không chờ phase hiện tại.
- `forceTermination()`: toàn bộ Phaser kết thúc, không phải “rút một party”.

### Nếu worker lỗi trước barrier

Một pattern:

```java
try {
    processStage();
} catch (RuntimeException e) {
    recordFailure(e);
    throw e;
} finally {
    phaser.arriveAndDeregister();
}
```

Đây là snippet minh họa, `recordFailure`, `processStage`, `phaser` ở ngữ cảnh ngoài.

Nó tránh một registration bị bỏ rơi khi task **đã bắt đầu** và vẫn có khả năng hoàn thành finally. Tuy nhiên, đây là lựa chọn policy: việc deregister có thể cho phép những parties khác **advance mặc dù stage không thành công**. Nếu stages phụ thuộc output của worker lỗi, cần chia sẻ failure state và fail-fast/termination protocol, không chỉ deregister và giả vờ thành công.

**Không gọi `arriveAndDeregister()` hai lần trên cùng logical registration.** Trách nhiệm deregister phải thuộc một đường rõ ràng, chẳng hạn owner task sau khi đã chạy, hoặc coordinator trong đường reject *trước khi worker bắt đầu*.

## 14. Interruption: Phaser không tự loại party bị interrupt

`arriveAndAwaitAdvance()` và `awaitAdvance()` là các phương thức **chờ không thể ngắt bằng checked InterruptedException theo contract**. Nếu application cần chờ đáp ứng interrupt, dùng:

```java
int phase = phaser.arrive();
try {
    phaser.awaitAdvanceInterruptibly(
            phase, 1, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    handleInterruptedWait(e);
} catch (TimeoutException e) {
    handlePhaseTimeout(e);
}
```

Đây là snippet minh họa trong method; cần imports `TimeUnit`, `TimeoutException` và các handler method do application định nghĩa.

Điểm dễ sai: sau `arrive()`, party **vẫn registered**; timeout/interrupt của lời **chờ** không tự hủy arrival hoặc rút registration. Nếu worker bỏ task vĩnh viễn, coordinator phải quyết định:

- Terminate Phaser vì phase không còn an toàn.
- Dùng một giao thức deregistration phù hợp khi phase đổi, tránh arrive hai lần cùng phase.
- Chuyển trách nhiệm arrival ở phase sau cho một worker khác trong giao thức có kiểm soát.
- Ghi nhận failure và đảm bảo các parties còn lại không chờ vô hạn.

**Không tự gọi `arriveAndDeregister()` ngay sau `arrive()` trong cùng phase chỉ vì timed await thất bại.** Điều này sẽ là **một arrival thứ hai** cho cùng registration/phase, có thể làm lệch đếm hoặc ném `IllegalStateException`. Cần controller/termination protocol thay vì “sửa” bằng cách arrive thêm.

### Timeout khác termination

`awaitAdvanceInterruptibly(phase, timeout, unit)` ném `TimeoutException` chỉ nói thread chưa thấy phase advance trong thời hạn. Nó **không tự forceTermination**, và những parties khác có thể đang tiến triển hợp lệ hoặc thực sự đã kẹt.

`forceTermination()` là một hành động riêng, có tác động đến toàn bộ Phaser, không phải một timeout cục bộ vô hại. Chỉ owner/coordinator nên quyết định nếu contract cho phép.

## 15. Phase termination và onAdvance()

Theo mặc định, khi phase advance với **registered parties bằng 0**, Phaser trở thành terminated. Muốn xác định chính sách khác, có thể subclass và override `protected boolean onAdvance(int phase, int registeredParties)`.

Ví dụ chỉ cho chạy tối đa ba phase:

```java
import java.util.concurrent.Phaser;

public final class ThreeRoundsPhaser extends Phaser {
    public ThreeRoundsPhaser(int parties) {
        super(parties);
    }

    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 2 || registeredParties == 0;
    }
}
```

Đây là một **class Java độc lập, có thể biên dịch** trong file `ThreeRoundsPhaser.java`; nó không có `main`. `onAdvance` nhận phase vừa hoàn tất và số registered parties hiện tại. Với chuỗi phase bắt đầu 0, callback khi vừa kết thúc phase 2 trả true (hoặc trả true sớm hơn nếu không còn parties), nên Phaser sẽ terminate theo policy.

### Những chú ý về onAdvance

- Callback có thể được gọi bởi thread thực hiện **arrival cuối khiến phase tiến**; không được mặc định main thread là callback owner.
- Callback nên **nhanh và không block**. Nếu nó làm I/O dài hoặc đợi một party cần phase advance để tiến triển, hệ thống có thể kẹt.
- Return `true` là yêu cầu terminate, không phải “advance tiếp”.
- Return `false` cho phép phase mới bắt đầu, nếu đủ điều kiện.
- Đừng mutate registry của Phaser theo cách tạo self-dependency trong callback.
- Nếu override và luôn return false, cần **một chính sách terminate khác**, nhất là khi registered count về 0; không mặc định mỗi subclass vẫn dùng hành vi termination mặc định.

### Termination và giá trị phase âm

Sau termination, một số method như `getPhase()` có thể trả phase âm để báo trạng thái. Application loop cần kiểm tra `phaser.isTerminated()` hoặc phase âm sau wait để không tiếp tục làm việc không còn ý nghĩa.

Không so sánh phase tăng vô hạn với integer tràn mà không có chính sách lifecycle. Theo API, phase number có semantics riêng khi terminated và wraparound trong thời gian rất dài; ứng dụng thông thường nên dùng số giai đoạn hữu hạn hoặc kiểm soát vòng đời rõ.

## 16. Coordinator và worker: ai là owner của party?

Bản thân Phaser không gắn registration với thread ID. Vì thế nếu bạn có 1.000 jobs nhưng chỉ tạo phaser với 3 parties, có thể đang mô hình hóa **ba worker loops** chứ không phải 1.000 jobs. Điều này hợp lệ nếu mỗi worker có trách nhiệm arrive mỗi phase; nhưng nếu business muốn chờ **tất cả 1.000 jobs**, số party/registration phải phản ánh đúng obligations.

Có ba pattern thường gặp:

**Mỗi worker là một party:** phù hợp khi một worker cố định hoặc tạm thời tham gia mọi phase, deregister khi không còn việc.

**Mỗi job là một party:** coordinator register trước khi submit từng job, job hoàn thành stage gọi arrive/deregister. Cần làm rõ một job có kéo dài nhiều phases hay chỉ thuộc một phase.

**Một coordinator là party “giữ cửa”:** main có registration để không cho phase advance trước khi đăng ký xong những participants của một batch. Coordinator không cần làm work nặng, nhưng phải arrive chính xác khi quá trình đăng ký và chuẩn bị kết thúc.

Không dùng `getRegisteredParties()` như số thread sống; không dùng `Thread.activeCount()` làm party count; không xem `ExecutorService.getPoolSize()` là số nghĩa vụ arrival.

## 17. Registration và lỗi submit/rejection

Một pipeline thực tế có thể:

1. `phaser.register()` cho một task.
2. Gọi `executor.submit(task)`.
3. Task bắt đầu, chạy, đến barrier, deregister.

Nhưng nếu bước 2 ném `RejectedExecutionException` vì pool đã shutdown hoặc bão hòa, không có worker nào sẽ thực hiện bước 3. Registration bị bỏ lại, khiến phase có thể chờ mãi.

Cần xử lý:

```java
phaser.register();
try {
    executor.execute(() -> {
        try {
            doWork();
        } finally {
            phaser.arriveAndDeregister();
        }
    });
} catch (RejectedExecutionException e) {
    phaser.arriveAndDeregister();
    throw e;
}
```

Đây là đoạn **minh họa** trong method với `executor` là executor có rejection bằng exception, `doWork` được định nghĩa, import `RejectedExecutionException`. Nó phù hợp khi executor dùng policy **ném exception rõ ràng**, ví dụ `AbortPolicy`.

**Không áp dụng mù quáng cho mọi handler:** `CallerRunsPolicy` có thể chạy task ngay trên caller; `DiscardPolicy` có thể âm thầm bỏ task mà **không ném exception**, khiến registration vẫn còn. Ownership của executor và rejection semantics phải được xác định, nếu không không thể bảo đảm registration được dọn.

Ngoài ra, nếu task được enqueue thành công nhưng **bị hủy hoặc trả ra bởi shutdownNow() trước khi bắt đầu**, worker finally chưa chạy. Caller/coordinator cần biết task có được thực thi hay không, và quản lý registration tương ứng.

## 18. Một lỗi deadlock điển hình: số party không khớp worker thực tế

Giả sử dùng `Phaser(3)` với coordinator và dự kiến hai worker, nhưng executor chỉ có **một thread**:

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
Phaser phaser = new Phaser(3); // main + 2 worker obligations

pool.submit(() -> phaser.arriveAndAwaitAdvance());
pool.submit(() -> phaser.arriveAndAwaitAdvance());
phaser.arriveAndAwaitAdvance(); // Có thể treo vô hạn.
```

Đây là đoạn **minh họa sai**, không dùng nguyên đoạn để thực hành chạy. Worker đầu tiên có thể block ở barrier; worker thứ hai **vẫn nằm trong work queue**, chưa có worker để chạy; main cũng chờ worker thứ hai. Đây là **thread starvation deadlock**.

Cách xử lý:

- Bảo đảm số worker có thể **cùng đạt barrier** phù hợp với số concurrently blocking parties cần thiết.
- Không dùng một executor nhỏ để chạy nhiều tasks mà các tasks phải đồng thời cùng arrive thì mới tiến triển.
- Có thể thiết kế nonblocking completion/async orchestration, hoặc để registrations đại diện worker loops thực tế chứ không đại diện toàn bộ queued jobs.
- Dùng timeout hoặc `forceTermination` cho đường lỗi, nhưng không xem timeout là lời giải cho kiến trúc không thể tiến triển.

Một `Phaser` linh hoạt không tự tạo thêm thread hay cấp thêm capacity cho executor.

## 19. So sánh với CountDownLatch và CyclicBarrier

| Tiêu chí | `CountDownLatch` | `CyclicBarrier` | `Phaser` |
|---|---|---|---|
| Mục tiêu | Chờ count giảm về 0, thường **one-shot** | Nhiều lần rendezvous với số parties cố định | Nhiều phases với số parties **thay đổi được** |
| Register participant động | Không có API register | Không có register/deregister động | `register`, `bulkRegister` |
| Rút một party đang tham gia | Không theo nghĩa participant riêng | Không có deregister động trực tiếp | `arriveAndDeregister` |
| Tái sử dụng | Không reset sau khi về 0 | Có thể reuse theo generations | Advance qua phases |
| Wait interruptible | `await` interruptible | `await` interruptible/broken-barrier semantics | `awaitAdvanceInterruptibly`; `arriveAndAwaitAdvance` không ném interrupt |
| Khi party thất bại | Caller phải quyết định countDown có xảy ra không | Có cơ chế broken barrier theo contract | Không tự broken vì party lỗi; cần deregister/forceTermination policy |
| Hoạt động khi parties = 0 | Latch count=0 → await trả ngay | Barrier parties phải hợp lệ theo constructor | Có thể khởi tạo zero parties; termination là lifecycle riêng |

### Khi nào chọn Phaser?

- Có **nhiều giai đoạn** cần barrier và **số participants tăng/giảm**.
- Muốn một coordinator quản lý batch workers mới và cho phép workers rời pipeline.
- Cần chính sách termination tại phase boundary qua `onAdvance`.
- Có thể quản lý đăng ký/arrival theo protocol rõ, và có tests cho failure/cancellation.

### Khi nào không cần Phaser?

- Chỉ chờ N tasks xong một lần: `CountDownLatch` hoặc `CompletableFuture.allOf` đơn giản hơn.
- Luôn có đúng N workers qua mọi vòng: `CyclicBarrier` có thể dễ hiểu hơn.
- Cần producer–consumer truyền message: dùng `BlockingQueue`, không dùng Phaser làm data transport.
- Cần locking để bảo vệ shared state trong critical section: `synchronized`, `Lock`, atomics hoặc ownership.
- Cần transaction nhiều resources hoặc durable job orchestration qua process crash: Phaser không cung cấp.

## 20. Phaser phân cấp (hierarchical Phaser)

Java `Phaser` hỗ trợ constructor nhận parent:

```java
Phaser parent = new Phaser(1);       // Coordinator.
Phaser childGroup = new Phaser(parent, 0);
childGroup.bulkRegister(3);
```

Đây là đoạn minh họa bên trong method. `childGroup` có parent `parent` và quản lý ba local parties. Trong một cấu trúc nhiều tầng, child Phaser có thể đại diện **một node party** với parent khi nó có registered parties, giảm áp lực contention ở root khi số participants rất lớn.

### Cần hiểu kỹ trước khi dùng

- Parent/child registration và deregistration có những quy tắc tự động khi child chuyển từ 0→nonzero hoặc ngược lại; không đơn giản cộng ba local parties vào parent như ba registrations độc lập.
- Child Phaser được liên kết với root phase; advanced phase và termination được phối hợp theo cấu trúc hierarchy.
- Quan sát `parent.getRegisteredParties()` không phải số **tổng leaf participants toàn hệ**.
- Khi số participant rất lớn hoặc contention tại một Phaser cao, phân cấp có thể cải thiện hiệu năng, nhưng tạo thêm độ phức tạp debug/lifecycle.
- Với đa số bài tập nhỏ, một Phaser đơn giản là đủ. Chỉ dùng hierarchy khi đã có nhu cầu và benchmark phù hợp.

Theo tài liệu Java, giới hạn số registrations trực tiếp trên một Phaser là **65.535 parties**; nếu cần nhiều hơn, cân nhắc hierarchy hoặc thiết kế synchronization khác. Không nhầm giới hạn này với số thread Java được phép tồn tại.

## 21. Memory consistency và happens-before

Phaser không chỉ đếm: nó còn cung cấp các ranh giới synchronization.

JavaDoc mô tả: **hành động trong thread trước một thao tác arrival** *happen-before* các hành động liên quan đến phase advance; những hành động sau khi phase advance được quan sát sẽ nằm **sau** phase boundary phù hợp về memory ordering.

Ví dụ hai workers xây dữ liệu trước barrier rồi main đọc:

```java
// Worker A:
resultsA[0] = 10;
phaser.arriveAndAwaitAdvance();

// Worker B:
resultsB[0] = 20;
phaser.arriveAndAwaitAdvance();

// Main, nếu cũng đăng ký và tham gia đúng phase:
phaser.arriveAndAwaitAdvance();
int sum = resultsA[0] + resultsB[0];
```

Đây là **pseudocode với các đoạn nằm ở nhiều threads**, không phải code độc lập. Bảo đảm chỉ áp dụng nếu cả ba cùng thuộc **một phase đúng** và không tiếp tục mutate dữ liệu không có synchronization.

### Không ngụ ý mọi state bên ngoài Phaser an toàn

Nếu A/B cùng thực hiện `sharedCounter++` trong phase trước, họ vẫn có thể race với nhau trước barrier. Phase advance giúp quan sát completion/visibility, **không biến phép tăng không nguyên tử thành atomic**.

Dùng `AtomicInteger`, mỗi worker ghi vào partition riêng, hoặc dùng lock/immutable state theo invariant. Trong runnable demo, `AtomicInteger` bảo vệ counters; Phaser điều phối phase; `Future.get()` bổ sung ranh giới hoàn tất task.

### Khi nào phase advance là đủ, khi nào cần Future?

- Nếu cần dữ liệu worker đã xây trước arrival và main đã qua đúng phase boundary, Phaser cung cấp synchronization cần thiết.
- Nếu cần biết worker đã **thoát method và chạy cleanup sau arrival/deregister** hay chưa, barrier không nhất thiết đủ; chờ `Future.get()`/`join()`.
- Nếu worker dùng `arriveAndDeregister()` rồi tiếp tục side effect sau đó, main qua phase boundary **không tự đợi** side effect ấy.
- Nếu có worker không nằm trong Phaser nhưng sửa shared data, barrier không bao phủ worker đó.

Đây là lý do demo gọi `task.get()` trước khi in số liệu và cleanup.

## 22. Quan sát metrics và debug phase bị treo

API quan sát:

```java
int phase = phaser.getPhase();
int registered = phaser.getRegisteredParties();
int arrived = phaser.getArrivedParties();
int unarrived = phaser.getUnarrivedParties();
boolean terminated = phaser.isTerminated();
```

Đây là code trong method với biến `phaser`.

Các giá trị này giúp:

- Biết đang ở phase nào.
- Có bao nhiêu registrations đang được giữ.
- Còn bao nhiêu obligations chưa arrive.
- Phân biệt Phaser active hay terminated.

**Cẩn thận:** getters có thể được đọc ở các thời điểm khác nhau. Không khẳng định `registered == arrived + unarrived` trong một snapshot ghép từ ba lần gọi concurrent nếu phase/registrations đang thay đổi giữa các reads.

### Điều tra khi treo

1. Xem phase, registered, unarrived, terminated.
2. Xem tasks có được submit thành công không; có rejection/cancel trước khi bắt đầu không.
3. Xem worker nào đã tới barrier và worker nào còn chạy/block trong tác vụ trước barrier.
4. Xem một worker có kết thúc mà quên `arriveAndDeregister` không.
5. Kiểm tra thread pool capacity: có task đang block ở barrier giữ toàn bộ workers, trong khi một party khác còn nằm trong executor queue không.
6. Kiểm tra có ai gọi `awaitAdvance` mà không arrive cho registration còn nợ không.
7. Kiểm tra registration bị thực hiện quá muộn hoặc double arrival.
8. Nếu cancellation policy cho phép, dùng `forceTermination` để giải phóng waiters rồi xử lý root cause.

### Thread dump

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thật. Thread dump có thể hiển thị trạng thái waiting/parking trong `Phaser`/`ForkJoinPool.managedBlock` hoặc các primitive liên quan. Một thread `WAITING (parking)` không mặc nhiên là deadlock: đợi barrier hợp lệ cũng có trạng thái chờ.

Nếu muốn chứng minh lỗi, kết hợp stack traces với **danh sách registrations/participants ở tầng nghiệp vụ**; bản thân Phaser không có API liệt kê party identity theo task id.

## 23. Những lỗi phổ biến

1. **Tạo Phaser với party count theo số task dự kiến nhưng không chạy đủ worker threads.** Có thể thread-starvation deadlock.
2. **Quên register một worker trước khi nó arrive.** Arrival có thể làm lệch nghĩa vụ của party khác hoặc ném exception.
3. **Register quá muộn khi phase hiện tại đã advance.** Worker mới có thể tham gia phase khác dự kiến.
4. **Đăng ký mới trong phase đang đợi nhưng không có ai arrive cho registration mới.** Phase bị treo.
5. **Quên deregister worker đã hết việc.** Phase tiếp theo vẫn đòi arrival của worker đó.
6. **Deregister hai lần cho cùng logical registration.** Lệch state hoặc `IllegalStateException`.
7. **Nhầm `arrive()` với `arriveAndAwaitAdvance()`.** Arrive không chờ, nên thread có thể chạy tiếp trước những parties khác.
8. **Gọi `awaitAdvance(current)` nhưng chưa arrive registration của mình.** Thread chờ điều kiện mà chính nó ngăn.
9. **Gọi `awaitAdvanceInterruptibly` rồi tưởng mình đã arrive.** Nó chỉ chờ; phải arrive riêng nếu là party.
10. **Timeout sau arrive rồi gọi arriveAndDeregister ngay trong cùng phase.** Có nguy cơ double arrival; cần failure/termination policy rõ.
11. **Cho rằng interrupt tự làm Phaser giảm registered parties.** Không, phải quản lý deregister/termination.
12. **Cho rằng forceTermination giết các worker và rollback mọi side effects.** Không; nó chỉ chấm dứt barrier coordination.
13. **Xem `getRegisteredParties` là số threads còn sống.** Registration là nghĩa vụ logic, không gắn thread identity.
14. **Đặt `onAdvance` làm I/O dài/lock đợi task khác.** Có thể block phase advance và gây deadlock.
15. **Override `onAdvance` luôn false mà không có shutdown policy.** Phaser có thể không auto terminate khi zero parties theo mong muốn.
16. **Dùng getters để quyết định register/arrive dựa trên snapshot không đồng bộ.** State có thể đổi ngay.
17. **Bỏ qua submission rejection sau khi register.** Không worker nào sẽ arrive và các parties khác treo.
18. **Bỏ qua task cancel trước khi bắt đầu.** Worker finally không chạy, registration bị bỏ lại.
19. **Xử lý lỗi worker bằng deregister rồi coi phase là thành công.** Barrier mở không xác nhận business stage đã thành công.
20. **Dùng Phaser để bảo vệ `counter++` giữa workers.** Barrier không làm phép update trong cùng phase trở nên nguyên tử.
21. **Dùng one-shot CountDownLatch semantics cho Phaser mà không quản lý phases sau.** Party còn registered phải arrive tiếp ở phase mới.
22. **Cho rằng mọi phase advances diễn ra trên main thread.** Arrival cuối có thể từ worker khác.
23. **Cho rằng phaser terminated nghĩa mọi Futures đã hoàn tất.** Worker có thể làm cleanup sau deregister; cần await completion riêng.
24. **Nhầm party hierarchy với số tổng leaf registrations.** Parent có thể chỉ thấy child Phaser như một node party.
25. **Dùng Thread.sleep để làm producer/worker “kịp đăng ký”.** Timing không thể thay protocol register-before-execute.
26. **Cho rằng awaitAdvance luôn chờ.** Nếu phase truyền vào đã khác current, nó có thể trả ngay.
27. **Cho rằng awaitAdvanceInterruptibly timeout là cancellation của toàn Phaser.** Không; timeout là của thread đợi.
28. **Không đặt deadline/alert cho phase chờ lâu.** Một party lỗi có thể làm tất cả chờ vô hạn.
29. **Sử dụng Phaser như data queue.** Phaser chỉ là barrier/phase coordination, không lưu và chuyển message.
30. **Dùng Phaser làm distributed synchronizer.** Nó quản lý synchronization nội bộ JVM, không xử lý nodes crash, network partition hoặc durability.

## 24. Bài tập thực hành

### Bài tập A — năm workers, hai người rút sau phase 0

Khởi tạo `Phaser(1)` cho coordinator, `bulkRegister(5)` trước khi submit 5 tasks. Trong phase 0, cả năm làm việc; hai tasks `arriveAndDeregister()`, ba tasks `arriveAndAwaitAdvance()` rồi làm phase 1. Coordinator qua barrier 0 rồi barrier 1. Kiểm tra số parties còn lại và đảm bảo main không tự advance trước khi đăng ký xong.

### Bài tập B — late join tại phase boundary

Bắt đầu với A/B + coordinator; sau phase 0, đăng ký C/D rồi submit. Cho A/B/C/D làm phase 1, tất cả deregister và main rút sau khi đợi phase 1. Dùng `Future.get()` để khẳng định task completion. Tránh in số thứ tự worker vì scheduler không bảo đảm.

### Bài tập C — timeout có kiểm soát

Một worker cố tình không tới barrier. Coordinator đã arrive bằng `arrive()`, rồi gọi `awaitAdvanceInterruptibly(phase, timeout, unit)`. Khi timeout, coordinator ghi cause và gọi `forceTermination()` theo policy fail-fast, hủy workers và shutdown pool. Giải thích vì sao không nên gọi `arriveAndDeregister()` lần nữa cho registration đã arrived trong cùng phase.

### Bài tập D — executor thiếu worker

Tạo một test có hai tasks chờ barrier nhưng pool chỉ một worker. Dùng test harness timeout để chứng minh không thể tiến triển, tránh chạy một ví dụ cố tình treo vô hạn. Sau đó tăng worker capacity hoặc sửa kiến trúc để hai parties có thể đồng thời tiến tới barrier.

### Bài tập E — custom onAdvance

Tạo subclass `ThreeRoundsPhaser` để terminate sau ba phase. Dùng hai parties thực hiện đúng ba vòng. Phân tích return value từ `arriveAndAwaitAdvance` ở lần cuối có thể báo termination bằng phase âm, và vì sao code cần kiểm tra `isTerminated()`.

### Bài tập F — hierarchy

Tạo root với coordinator, hai child phasers mỗi child có 3 local parties. So sánh registered count của root và tổng local parties, giải thích vì sao root không lưu trực tiếp sáu registrations. Viết test tất cả local parties qua một phase rồi shutdown sạch.

## 25. Câu hỏi ôn tập và đáp án

**Câu 1.** Vì sao Phaser phù hợp khi số participants thay đổi?  
**Đáp án:** Nó hỗ trợ `register`/`bulkRegister` để thêm parties và `arriveAndDeregister` để rút parties khi chạy qua nhiều phases.

**Câu 2.** `new Phaser(1)` có tạo một worker thread không?  
**Đáp án:** Không. Nó đăng ký một logical party ban đầu; caller phải tự chạy code và báo arrival cho party đó.

**Câu 3.** `arrive()` có đợi các parties còn lại không?  
**Đáp án:** Không. Nó đánh dấu arrived và trả về phase đang thực thi.

**Câu 4.** `arriveAndAwaitAdvance()` khác gì `arrive()`?  
**Đáp án:** Nó vừa báo arrival vừa chờ phase advance.

**Câu 5.** Một worker ngừng tham gia, tại sao phải gọi `arriveAndDeregister`?  
**Đáp án:** Nếu chỉ arrive rồi không quay lại, registration vẫn tồn tại ở phase sau, có thể làm barrier chờ mãi.

**Câu 6.** `awaitAdvance(phase)` có cần caller là một party không?  
**Đáp án:** Không. Non-party observer có thể chờ; method không tự arrive.

**Câu 7.** `awaitAdvanceInterruptibly` timeout có tự deregister party không?  
**Đáp án:** Không. Nó chỉ kết thúc việc chờ của caller; registration và arrival state cần protocol riêng.

**Câu 8.** Có được gọi `arriveAndDeregister` ngay sau `arrive()` trên cùng party và phase để “dọn” không?  
**Đáp án:** Không. Đây là double arrival theo cùng registration/phase; có thể làm sai nghĩa vụ. Cần owner-managed failure protocol/termination.

**Câu 9.** Nếu worker mới register khi phase 2 đang mở, có chắc nó chỉ phải arrive từ phase 3 không?  
**Đáp án:** Không. Registration đang active thường áp dụng cho current phase; cần coordinator quản lý phase boundary.

**Câu 10.** Vì sao executor một worker + hai tasks đang chờ barrier có thể deadlock?  
**Đáp án:** Task thứ nhất giữ worker rồi chờ task thứ hai arrive; task hai vẫn queue và không có worker để chạy.

**Câu 11.** `getRegisteredParties()` có cho biết số thread Java đang sống không?  
**Đáp án:** Không. Nó đếm logical registrations, không thread identities.

**Câu 12.** Khi registered parties về 0 trong default Phaser và phase advance, điều gì xảy ra?  
**Đáp án:** `onAdvance` mặc định trả true, khiến Phaser terminate.

**Câu 13.** `onAdvance` return true có nghĩa advance tiếp không?  
**Đáp án:** Không; true báo termination.

**Câu 14.** `forceTermination()` có dừng ngay mọi business task đang tính toán không?  
**Đáp án:** Không. Nó chấm dứt synchronization và giải phóng waiters, không kill threads hay rollback side effects.

**Câu 15.** Nếu cả hai workers cùng `counter++` trước barrier, main qua barrier có được tổng chính xác không?  
**Đáp án:** Không chắc. Barrier không sửa lost update xảy ra giữa workers trong phase; cần atomic/lock/partitioned writes.

**Câu 16.** Chương trình demo có phase0Workers=2 và phase1Workers=3, vì sao?  
**Đáp án:** A/B tham gia cả hai phases; C được register sau phase 0 và chỉ tham gia phase 1.

**Câu 17.** `arriveAndDeregister` có nghĩa “đã chạy xong toàn bộ finally/cleanup của worker” không?  
**Đáp án:** Không. Worker có thể tiếp tục code sau arrival; caller cần chờ Future/join nếu cần task hoàn tất.

**Câu 18.** Nếu pool rejected task sau khi register, phải làm gì?  
**Đáp án:** Xử lý rejection và rút registration theo policy nếu task chưa bắt đầu, hoặc terminate/cancel có kiểm soát. Không để party mồ côi chặn phase.

**Câu 19.** `getArrivedParties` và `getUnarrivedParties` có cung cấp một snapshot nguyên tử chung khi đọc lần lượt không?  
**Đáp án:** Không. Phases/registrations có thể đổi giữa các lần đọc.

**Câu 20.** Khi nào chọn CountDownLatch thay Phaser?  
**Đáp án:** Khi chỉ chờ một tập hoạt động hoàn tất **một lần** và không cần dynamic multi-phase participation.

## 26. Checklist thiết kế thực tế

Trước khi dùng Phaser trong dự án, kiểm tra:

- **Scope:** Phaser thuộc một job/pipeline nào, ai là owner lifecycle?
- **Party identity:** mỗi registration tương ứng worker, task hay coordinator?
- **Registration timing:** số parties đã được thêm **trước khi tasks có thể arrive**?
- **Phase protocol:** task nào cần arrive ở từng phase, task nào cần deregister?
- **Join semantics:** newcomer tham gia current hay next phase, ai giữ phase mở?
- **Failure handling:** task lỗi trước barrier có làm những parties khác chờ vô hạn không?
- **Submission/cancel:** rejection và cancellation trước task start có đường cleanup registration?
- **Interrupt:** cần interruptible/timed wait hay uninterruptible barrier?
- **Timeout:** nếu một phase treo, coordinator có deadline và forceTermination policy?
- **Termination:** default last-party deregistration hay custom `onAdvance`?
- **Executor capacity:** có đủ workers để những parties blocking cùng tới barrier?
- **State safety:** dữ liệu dùng qua phases có publication, atomicity và ownership đúng?
- **Completion:** cần chờ barrier, chờ Future, hay cả hai?
- **Observability:** phase, registered/unarrived, last progress, task failures và deadline?
- **Scalability:** participant count lớn có cần hierarchical Phaser hoặc mô hình khác?
- **Testing:** test một/zero/many parties, register/deregister động, phase timeout, worker failure và shutdown?
- **Version:** triển khai với đúng JDK hỗ trợ API cần dùng (ví dụ Java 17).

Một thiết kế Phaser tốt bắt đầu từ **bảng trách nhiệm arrival của mỗi party theo từng phase**, không bắt đầu từ số thread dự đoán.

## 27. Tài liệu tham khảo chính thức

- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): constructors, register/bulkRegister, arrive/await/deregister, termination, onAdvance, hierarchy và memory consistency.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): cyclic barrier có số parties cố định.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ one-shot count-down.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future, shutdown và lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion và memory-consistency effects.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic counters dùng trong ví dụ.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, happens-before và thread communication.

**Tổng kết:** `Phaser` là barrier nhiều vòng dành cho **tập participants linh hoạt**. Sức mạnh đến từ `register/bulkRegister` và `arriveAndDeregister`, nhưng chính sự linh hoạt đó làm tăng yêu cầu quản lý ownership, phase timing và failure paths. Đăng ký đúng trước khi worker có thể arrive, cho mỗi party một obligation rõ ở mỗi phase, deregister khi rời, và dùng `Future.get` khi cần biết task thực sự hoàn tất. Nếu một participant mất tích, Phaser không thể tự đoán cách sửa: cần coordinator, timeout/interrupt policy và recovery/termination nhất quán.