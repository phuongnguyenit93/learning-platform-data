# Tác vụ định kỳ chạy lâu: fixed rate, fixed delay và việc không chạy chồng chính nó

> **Thông điệp quan trọng:** Trong Java, `ScheduledExecutorService.scheduleAtFixedRate` và `scheduleWithFixedDelay` đều tạo **một chuỗi thực thi tuần tự của cùng một tác vụ định kỳ**. Khi tác vụ chạy lâu hơn chu kỳ, lần chạy tiếp theo của **chính periodic task đó không chồng lên lần trước**. Điểm khác nhau là **fixed rate bám lịch bắt đầu danh nghĩa**, còn **fixed delay chỉ bắt đầu đếm delay sau khi lần chạy trước kết thúc**. Không được suy ra rằng các tác vụ định kỳ *khác nhau* trong pool không thể chạy song song.

Bài thuộc **Future & Scheduling** của **Java concurrency nói chung**, dùng Java SE 17+ và chủ yếu các interface `ScheduledExecutorService`, `ScheduledFuture` cùng implementation `ScheduledThreadPoolExecutor`. Không bàn đến Spring hay annotation scheduling của framework.

## 1. Tác vụ định kỳ và câu hỏi cần giải quyết

Với polling, cập nhật cache, kiểm tra health, dọn dẹp dữ liệu hoặc ghi thống kê, ta muốn chạy một `Runnable` nhiều lần theo lịch. Vấn đề xuất hiện khi **một lần chạy mất nhiều thời gian hơn lịch dự kiến**.

Ví dụ, một tác vụ cần chạy “mỗi 100 ms” nhưng một lượt xử lý tốn 250 ms. Chuyện gì xảy ra với lượt kế tiếp?

- Có sinh thêm một thread mới để chạy chồng lên lượt đang xử lý không?
- Có bỏ những “tick” đã trễ không?
- Lượt tiếp theo được tính từ **mốc lịch ban đầu** hay **lúc lượt trước kết thúc**?
- Nếu pool có 4 worker, 4 lượt của cùng task có được chạy cùng lúc không?
- Nếu một lượt ném exception, lịch định kỳ còn tồn tại không?

Trả lời đúng cần phân biệt **một periodic schedule**, **một lần execution**, và **nhiều scheduled tasks độc lập**.

~~~text
ScheduledExecutorService
  ├── periodic task A: A1 -> A2 -> A3 -> ...   (không tự overlap)
  ├── periodic task B: B1 -> B2 -> B3 -> ...   (không tự overlap)
  └── one-shot task C: C1

A1 có thể đồng thời với B1 hoặc C1 nếu đủ worker,
nhưng A1 không đồng thời với A2 thuộc cùng một schedule.
~~~

Đặc tính **không tự overlap** thuộc về các *successive executions của một periodic task được lập lịch bằng API này*. Nó không phải mutex chung bảo vệ mọi lời gọi của cùng một class hay cùng một `Runnable`.

## 2. Hai API phổ biến

~~~java
// Snippet API minh họa, chưa phải chương trình độc lập.
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);

// Mốc bắt đầu lý tưởng: initialDelay, initialDelay+period,
// initialDelay+2*period,... tính từ lịch ban đầu.
ScheduledFuture<?> rateHandle = scheduler.scheduleAtFixedRate(
        task, 0, 100, TimeUnit.MILLISECONDS);

// Đợi delay từ lúc KẾT THÚC execution trước,
// rồi mới đủ điều kiện bắt đầu execution tiếp theo.
ScheduledFuture<?> delayHandle = scheduler.scheduleWithFixedDelay(
        task, 0, 100, TimeUnit.MILLISECONDS);
~~~

Cả hai method nhận một `Runnable`, `initialDelay` và một lượng thời gian `period` hoặc `delay`, trả về một `ScheduledFuture<?>` dùng để quan sát/hủy lịch.

Các ràng buộc đáng nhớ:

- `scheduleAtFixedRate` yêu cầu `period > 0`; `scheduleWithFixedDelay` yêu cầu `delay > 0`, nếu không sẽ ném `IllegalArgumentException`.
- `initialDelay` có thể bằng 0 để chạy ngay khi đủ điều kiện; độ trễ âm ở một số phương thức được xử lý như yêu cầu immediate theo hợp đồng scheduling, nhưng đừng thiết kế lịch nghiệp vụ dựa vào delay âm.
- `TimeUnit` định nghĩa đơn vị; không nhầm mili-giây với giây.
- Các lần thực thi diễn ra trên worker threads do executor quản lý; không dùng `Thread.sleep` trong thread gọi schedule để duy trì lịch.
- `ScheduledFuture.get()` **không trả kết quả bình thường sau mỗi lượt** đối với periodic schedule còn đang lặp. Nó đại diện cho cả chuỗi thực thi định kỳ, không phải một Future riêng cho mỗi tick.

## 3. Fixed rate: mốc bắt đầu dự kiến cách nhau một period

`scheduleAtFixedRate(task, initialDelay, period, unit)` hướng đến lịch:

~~~text
Thời điểm dự kiến của lần k (k từ 0):
    scheduledStart(k) = t0 + initialDelay + k × period
~~~

Ví dụ period 100 ms, thời điểm đủ điều kiện bắt đầu lần lượt là 0, 100, 200, 300 ms (tính tương đối từ t0).

Nếu mỗi lượt chạy **ngắn hơn period**, giữa các lượt có khoảng nghỉ để bám mốc. Nhưng nếu lượt đầu mất **250 ms**, thời điểm danh nghĩa của lượt thứ hai (100 ms) đã qua. Lượt thứ hai có thể **bắt đầu muộn gần như ngay sau khi lượt đầu kết thúc**, tùy worker scheduling; không cần chờ thêm đủ 100 ms tính từ lúc kết thúc.

~~~text
period=100 ms, mỗi lần chạy=250 ms (minh họa lý tưởng)

Mốc fixed-rate:  0    100    200    300    400    500 ...
                 |-----|------|------|------|------|
Chạy A1:         [========= 250 ms =========]
Chạy A2:                                    [==== ...]
                 ^ A2 bắt đầu muộn, không chạy chồng A1
~~~

**Quan trọng:** Đây không có nghĩa scheduler tạo hàng đống `Runnable` riêng cho các mốc bị lỡ rồi chạy chúng đồng thời. Hợp đồng của `ScheduledThreadPoolExecutor` bảo đảm các lần thực thi của **cùng periodic task không overlap**. Khi thời gian đã trễ, những lần chạy tiếp theo có thể bắt đầu liên tiếp với **rất ít hoặc không có thời gian nghỉ** (ngoài chi phí scheduler).

Không có bảo đảm hard real-time về đúng mốc 100 ms: OS, CPU saturation, GC, contention, timer resolution và số worker sẵn có đều có thể khiến lần chạy bắt đầu muộn.

## 4. Fixed delay: tính delay từ khi lượt trước kết thúc

`scheduleWithFixedDelay(task, initialDelay, delay, unit)` có quy tắc:

~~~text
Thời điểm eligible lần đầu: t0 + initialDelay
Lần kế tiếp được phép bắt đầu:
    finish(previous execution) + delay
~~~

Nếu execution mất 250 ms và delay 100 ms, các lần chạy lý tưởng bắt đầu tại 0, 350, 700, 1050 ms.

~~~text
delay=100 ms, mỗi lần chạy=250 ms (minh họa lý tưởng)

Lượt D1:        [========= 250 ms =========]
Nghỉ:                                    [100 ms]
Lượt D2:                                         [========= 250 ms =========]
Nghỉ:                                                                     [100 ms]
Lượt D3:                                                                    ...
~~~

Không phải “fixed delay cố gắng bám 100 ms giữa hai lần bắt đầu”. Nó cam kết **khoảng chờ tối thiểu theo lịch giữa khi kết thúc và lần bắt đầu kế tiếp** (việc được CPU cấp phát có thể khiến khoảng chờ thực tế lớn hơn).

Khi task chậm, tần suất thực tế của fixed delay giảm theo độ dài thực thi. Điều này phù hợp cho:

- Polling cần chờ sau khi request trước kết thúc.
- Cleanup không muốn chạy dồn dập.
- Task có tải I/O cần khoảng cách nghỉ để giảm áp lực downstream.
- Những trường hợp cần tránh hai lần invocation liên tiếp sát nhau khi một invocation đã trễ.

Fixed delay cũng không cho phép cùng periodic task chạy chồng lên chính nó.

## 5. So sánh khi một lượt chạy dài hơn period/delay

| Tiêu chí | `scheduleAtFixedRate` | `scheduleWithFixedDelay` |
| --- | --- | --- |
| Tính lịch từ đâu? | Các mốc bắt đầu danh nghĩa từ `initialDelay` + bội số `period` | Kết thúc lượt trước + `delay` |
| Khi duration ngắn hơn khoảng đặt | Thường có khoảng nghỉ để bám lịch | Nghỉ đúng delay theo cơ chế scheduler |
| Khi duration dài hơn khoảng đặt | Lượt sau có thể bắt đầu muộn, gần như ngay khi lượt trước xong | Vẫn chờ thêm delay sau khi lượt trước xong |
| Có tự overlap cùng periodic task? | **Không** | **Không** |
| Có giữ chính xác mốc thời gian tuyệt đối? | Không, chỉ lập lịch tương đối; có jitter | Không, có jitter |
| Tần suất khi quá tải | Có thể dồn các lượt sát nhau, gây áp lực liên tục | Giảm tự nhiên vì mỗi lượt có khoảng nghỉ |
| Thích hợp khi | Muốn bám cadence định kỳ, ví dụ thu mẫu gần đều | Muốn tránh dồn lần chạy, ví dụ polling và cleanup |
| Nhược điểm cần theo dõi | Trễ tích lũy, chạy liên tiếp không nghỉ | Trôi lịch theo độ dài mỗi execution |

Trong nhiều trường hợp, **fixed rate cũng không “bỏ qua” mỗi mốc trễ theo cách bạn tự kỳ vọng**; nó tiếp tục dựa trên chuỗi mốc danh nghĩa. Nhưng API không hứa một số lượng tick hoàn tất tại thời điểm thực tế cố định. Không dùng `numberOfRuns == elapsed/period` để chứng minh đúng với mọi scheduling/load.

## 6. Ví dụ 1 — mô hình thời gian xác định để hiểu khác biệt

Trước khi viết chương trình có thread và đồng hồ thật, có thể tính toán **mốc thời gian lý tưởng** để phân biệt hai quy tắc. Ví dụ sau không dùng scheduler thực; nó mô phỏng một periodic task **luôn** mất 250 ms và period/delay là 100 ms.

Tạo `PeriodicTimelineModel.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;

public class PeriodicTimelineModel {
    public static void main(String[] args) {
        long durationMs = 250;
        long intervalMs = 100;
        int iterations = 4;

        List<Long> rateStarts = new ArrayList<>();
        long nextNominalRate = 0;
        long previousRateFinish = 0;

        for (int i = 0; i < iterations; i++) {
            long actualStart = Math.max(nextNominalRate, previousRateFinish);
            rateStarts.add(actualStart);
            previousRateFinish = actualStart + durationMs;
            nextNominalRate += intervalMs;
        }

        List<Long> delayStarts = new ArrayList<>();
        long nextDelayStart = 0;

        for (int i = 0; i < iterations; i++) {
            delayStarts.add(nextDelayStart);
            long finish = nextDelayStart + durationMs;
            nextDelayStart = finish + intervalMs;
        }

        System.out.println("fixed rate starts (ms) = " + rateStarts);
        System.out.println("fixed delay starts (ms) = " + delayStarts);
    }
}
~~~

Chạy:

~~~bash
javac PeriodicTimelineModel.java
java PeriodicTimelineModel
~~~

Stdout **chính xác**:

~~~text
fixed rate starts (ms) = [0, 250, 500, 750]
fixed delay starts (ms) = [0, 350, 700, 1050]
~~~

**Giải thích:** Fixed rate có các mốc dự kiến 0, 100, 200, 300 ms nhưng mỗi lượt tốn 250 ms, nên lần tiếp theo đủ điều kiện từ lâu khi lượt hiện tại hoàn tất. Fixed delay cộng 100 ms **sau mỗi lần hoàn thành**. Cả hai mô hình đều chỉ thực hiện **một lượt tại một thời điểm**.

Đây là mô hình lý tưởng **không có scheduler jitter, executor queue, GC, preemption hay hệ thống nhiều worker**. Stdout của mô hình có thể xác định hoàn toàn, còn timestamp tuyệt đối trong ứng dụng thật không có cùng bảo đảm.

## 7. Quy tắc “không chạy chồng chính nó” áp dụng tới đâu?

Java API `ScheduledThreadPoolExecutor` nói rõ: các lần thực thi liên tiếp của một task được lập lịch bằng `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay` **không overlap**; hiệu ứng của một lần thực thi *happen-before* hiệu ứng của lần tiếp theo, ngay cả khi các lần thực thi có thể do **những worker thread khác nhau** thực hiện.

Điều này có một số hệ quả:

1. Nếu invocation `A1` của một periodic schedule vẫn chưa kết thúc, invocation `A2` **không thể bắt đầu chồng** lên `A1` do riêng schedule ấy.
2. Việc scheduler có `corePoolSize=4` hay `corePoolSize=32` **không thay đổi** quy tắc ở mục 1.
3. Invocation kế tiếp có thể được thread khác thực hiện, vì vậy không dựa vào `Thread.currentThread().getName()` luôn giữ nguyên.
4. Các lần chạy được điều phối về mặt memory visibility theo quan hệ *happens-before* giữa successive executions.
5. Hai periodic schedule **khác nhau** có thể đồng thời; không có global exclusion giữa mọi task của scheduler.
6. Nếu một ứng dụng **tự lập lịch cùng một Runnable object hai lần**, nó tạo **hai periodic futures độc lập**; các invocation từ hai lịch có thể overlap nhau. Cùng tham chiếu `Runnable` không đồng nghĩa cùng periodic task schedule.
7. Một periodic task tự submit một task con vào pool khác rồi return; **phần việc asynchronous của task con** có thể còn chạy khi invocation kỳ sau bắt đầu. Scheduler chỉ không overlap phần **execution body của chính scheduled Runnable**, không tự theo dõi downstream tasks.

### Phân biệt “không overlap” và “không cần đồng bộ”

Nếu chỉ một periodic schedule truy cập một state không bị thread nào khác dùng, việc các invocation của nó không overlap giúp tránh reentrancy nội bộ. Nhưng nếu:

- Reader bên ngoài đọc cùng mutable state,
- Có scheduled task khác cũng sửa state,
- Handler đồng thời đến từ API khác,
- Task chuyển việc cho asynchronous child task,

thì **race conditions vẫn có thể xảy ra**. Phải thiết kế thread confinement, locks, atomic variables hoặc immutable snapshots theo phạm vi thực.

## 8. Ví dụ 2 — xác nhận một periodic task không tự overlap khi pool có nhiều worker

Để không dùng `Thread.sleep` rồi suy đoán scheduler, dùng các latch kiểm soát một invocation đang giữ trạng thái. Trong khi invocation thứ nhất vẫn bị chặn, task khác vẫn có thể chạy trên worker khác trong cùng pool.

Tạo `PeriodicNoOverlapDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicNoOverlapDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(4);

        CountDownLatch firstEntered = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch otherTaskRan = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximumActive = new AtomicInteger();
        AtomicInteger runs = new AtomicInteger();

        ScheduledFuture<?> periodic = pool.scheduleAtFixedRate(() -> {
            int nowActive = active.incrementAndGet();
            maximumActive.accumulateAndGet(nowActive, Math::max);
            int invocation = runs.incrementAndGet();

            try {
                if (invocation == 1) {
                    firstEntered.countDown();
                    releaseFirst.await();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        }, 0, 1, TimeUnit.MILLISECONDS);

        try {
            firstEntered.await();

            pool.schedule(otherTaskRan::countDown,
                    0, TimeUnit.MILLISECONDS);
            otherTaskRan.await();

            System.out.println("runs while first blocked = " + runs.get());
            System.out.println("maximum active = " + maximumActive.get());
            System.out.println("other task completed = true");

            System.out.println("cancelled = " + periodic.cancel(true));
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac PeriodicNoOverlapDemo.java
java PeriodicNoOverlapDemo
~~~

Stdout khi không có interruption bên ngoài:

~~~text
runs while first blocked = 1
maximum active = 1
other task completed = true
cancelled = true
~~~

**Tại sao có thể tin kết quả này?**

- `firstEntered.await()` chứng minh lần đầu đã vào Runnable và đang đợi `releaseFirst`.
- Khi lần đầu chưa return, periodic schedule đó không thể chạy invocation thứ hai, dù pool có 4 worker và period chỉ 1 ms.
- Task **khác** được enqueue với delay 0 vẫn chạy được ở một worker rảnh, chứng minh pool không bị khóa độc quyền toàn cục.
- Main cancel periodic Future khi lần đầu còn bị giữ, sau đó `finally` mới mở latch và dừng pool; không có cơ hội tạo một invocation thứ hai thành công.
- `maximumActive == 1` ở thời điểm kiểm tra là dấu hiệu của thử nghiệm; bảo đảm tổng quát về không overlap đến từ hợp đồng API, không đến từ stress test duy nhất.

**Không giữ latch blocking trong một periodic job production** chỉ để thử nghiệm. Với hệ thống thật, hãy dùng timeout và cảnh báo nếu task không tiến triển; tránh khóa tài nguyên quan trọng khi chờ một thread khác cũng cần tài nguyên ấy.

## 9. Fixed rate gặp overload: xử lý mốc trễ và không “catch up song song”

Giả sử period 100 ms nhưng một execution phải chờ network 2 giây. Trong suốt 2 giây đó, rất nhiều mốc danh nghĩa đã trôi qua. Với fixed rate:

- Không tạo 20 bản sao của **chính periodic Future** chạy trên 20 worker để “bù kịp”.
- Lần chạy kế tiếp có thể bắt đầu muộn khi lần trước kết thúc.
- Những lần sau vẫn gắn với chuỗi mốc ban đầu; nếu còn trễ, có thể bắt đầu lại rất sớm.
- Việc chạy dồn dập sau nghẽn có thể khiến **downstream tiếp tục chịu tải**, không có thời gian nghỉ để phục hồi.
- Không có cam kết rằng toàn bộ số lần tương ứng mốc đã qua sẽ hoàn thành trong một khoảng thời gian giới hạn.

Một task fixed-rate đọc dữ liệu có thể cần chính sách **skip stale work** hoặc **coalesce**: thay vì cố xử lý mọi lần cập nhật đã trễ theo logic scheduler, code tự kiểm tra snapshot hiện tại và chỉ thực hiện việc còn hữu ích. Nếu cần một event stream có độ bền và xử lý từng sự kiện, periodic scheduling không phải queue nghiệp vụ durable.

Không dùng fixed rate với kỳ vọng nó tự giới hạn concurrency. Nó giới hạn **overlap của chính schedule ấy**, không giới hạn **tổng công việc** nếu task gọi `submit` để đẩy thêm nhiệm vụ xuống một executor khác.

## 10. Fixed delay khi tác vụ chạy lâu

Với fixed delay, nếu execution mất 2 giây và delay=100 ms, lần kế tiếp chỉ đủ điều kiện sau khi execution hoàn tất và thêm 100 ms. Điều này:

- Tạo một **khoảng nghỉ thật sự giữa hai invocation**, theo cơ chế scheduling.
- Tránh các invocation được phát liên tiếp với độ nghỉ gần 0 khi một lượt chạy trễ.
- Dễ hiểu hơn cho polling “đợi một lúc rồi thử lại sau khi lần trước xong”.
- Làm tần suất bắt đầu biến động cùng thời lượng xử lý, không giữ nhịp bắt đầu cố định.

Fixed delay **không** đặt deadline cho duration. Nếu một invocation kẹt vĩnh viễn, invocation kế tiếp không chạy; scheduler không tự interrupt invocation chỉ vì đã qua delay. Cần I/O timeout, cancellation, watchdog hoặc policy khác nếu muốn kiểm soát thời gian thực thi.

Nếu muốn “thử sau 100 ms kể từ khi đã nhận response”, fixed delay phù hợp. Nếu muốn “cố lấy mẫu vào những mốc gần mỗi phút theo thời gian tường”, phải phân tích fixed rate, clock alignment, độ trễ và missed sampling riêng.

## 11. Ví dụ 3 — kiểm tra khoảng delay sau khi invocation kết thúc

Ví dụ dưới đây chạy **thật** với scheduler và chỉ in một **mệnh đề về thứ tự được đảm bảo**, không in timestamp ngẫu nhiên. Một lượt làm việc mô phỏng mất khoảng 70 ms; delay giữa các lượt là 20 ms. Sau hai lượt, ta kiểm tra khoảng tính từ gần điểm kết thúc lượt 1 đến lúc bắt đầu lượt 2.

Tạo `FixedDelayGapDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class FixedDelayGapDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        AtomicInteger runs = new AtomicInteger();
        AtomicLong firstEnd = new AtomicLong();
        AtomicLong secondStart = new AtomicLong();

        ScheduledFuture<?> future = pool.scheduleWithFixedDelay(() -> {
            int iteration = runs.incrementAndGet();
            long start = System.nanoTime();
            if (iteration == 1) {
                try {
                    // Chỉ mô phỏng công việc chậm, không dùng để
                    // chứng minh vị trí lịch bằng timestamp tuyệt đối.
                    Thread.sleep(70);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                firstEnd.set(System.nanoTime());
            } else if (iteration == 2) {
                secondStart.set(start);
                secondStarted.countDown();
            }
        }, 0, 20, TimeUnit.MILLISECONDS);

        try {
            secondStarted.await();
            long observedGapNs = secondStart.get() - firstEnd.get();
            System.out.println("at least two runs = " + (runs.get() >= 2));
            System.out.println("gap >= 20 ms = "
                    + (observedGapNs >= TimeUnit.MILLISECONDS.toNanos(20)));
        } finally {
            future.cancel(true);
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac FixedDelayGapDemo.java
java FixedDelayGapDemo
~~~

Stdout khi task không bị interrupt ngoài chương trình:

~~~text
at least two runs = true
gap >= 20 ms = true
~~~

Scheduler tính lần đủ điều kiện tiếp theo **sau khi callback lần trước return**; phép `firstEnd.set` nằm ngay trước lúc return nên khoảng đo đến đầu lượt 2 không thể nhỏ hơn delay 20 ms theo semantics và đồng hồ monotonic trên JVM bình thường. Con số elapsed thực tế có thể lớn hơn do scheduler hoặc GC; ví dụ cố tình chỉ in điều kiện đủ/không đủ, không hard-code “90 ms”.

**Giới hạn thử nghiệm:** Một bài benchmark thời gian thực tế cần nhiều mẫu, warmup và môi trường phù hợp. `Thread.sleep(70)` ở đây chỉ tạo duration dài hơn delay để minh họa, không phải kỹ thuật bảo đảm chính xác 70 ms hoặc cách điều phối thread trong production.

## 12. Pool có nhiều worker: hai periodic schedules khác nhau vẫn có thể overlap

Quy tắc không tự overlap **không tạo global mutex** cho scheduler. Một scheduler có từ hai worker trở lên có thể chạy task A và task B đồng thời.

### Ví dụ 4 — hai periodic schedules khác nhau cùng có thể đang chạy

Tạo `DifferentPeriodicTasks.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DifferentPeriodicTasks {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(2);

        CountDownLatch aEntered = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch bFinished = new CountDownLatch(1);
        AtomicBoolean aRunning = new AtomicBoolean();
        AtomicBoolean bObservedA = new AtomicBoolean();

        ScheduledFuture<?> a = pool.scheduleAtFixedRate(() -> {
            aRunning.set(true);
            aEntered.countDown();
            try {
                releaseA.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                aRunning.set(false);
            }
        }, 0, 1, TimeUnit.DAYS);

        ScheduledFuture<?> b = null;
        try {
            aEntered.await();
            b = pool.scheduleWithFixedDelay(() -> {
                bObservedA.set(aRunning.get());
                bFinished.countDown();
            }, 0, 1, TimeUnit.DAYS);

            bFinished.await();
            System.out.println("B ran while A active = "
                    + bObservedA.get());
        } finally {
            a.cancel(true);
            if (b != null) {
                b.cancel(true);
            }
            releaseA.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac DifferentPeriodicTasks.java
java DifferentPeriodicTasks
~~~

Stdout khi bình thường:

~~~text
B ran while A active = true
~~~

Task A đang giữ worker thứ nhất và chờ latch; task B được chạy trên worker thứ hai, đọc cờ A còn active. Hai periodic tasks **độc lập** có thể overlap. Điều không thể xảy ra là lần A thứ hai bắt đầu trong khi lần A thứ nhất chưa kết thúc, vì hai lần đó thuộc cùng lịch `a`.

**Nếu cùng một instance `Runnable` được schedule hai lần**, kết luận cũng tương tự: mỗi lời gọi schedule tạo một periodic job độc lập. Nếu hai job sửa cùng state, cần đồng bộ riêng hoặc không schedule trùng.

## 13. Các lần chạy liên tiếp có quan hệ happens-before

`ScheduledThreadPoolExecutor` có bảo đảm đặc biệt: dù hai lần thực thi kế tiếp của **cùng periodic task** có thể do những thread khác nhau chạy, hiệu ứng của lần trước *happen-before* lần sau. Điều này giúp các thao tác của chính periodic task được quan sát đúng theo thứ tự execution của nó.

~~~text
Periodic schedule A:
    A1 (worker-2) -- completes --> A2 (worker-1)
        |                             ^
        +----------- happens-before --+

Periodic schedule B:
    B1 (worker-3) có thể chạy đồng thời A1;
    không có một HB tổng quát chỉ vì hai task cùng scheduler.
~~~

Không suy ra:

- Field mutable của task tự động an toàn với **reader bên ngoài**.
- Hai periodic tasks khác nhau được serialize với nhau.
- Downstream async tasks được bảo vệ chỉ vì parent task không overlap.
- Side effects mạng/database “commit” theo thứ tự xảy ra trong JVM nếu chúng thuộc hệ thống khác và API chưa đồng bộ trạng thái ấy.
- Hàm `Runnable.run()` luôn được gọi trên cùng worker thread hoặc mang cùng `ThreadLocal` state.

Nếu cần đưa snapshot tới các consumer khác, vẫn cần safe publication/`volatile`, lock, queue, atomic hoặc immutable state theo tình huống. Không sử dụng `ThreadLocal` để lưu state bền vững xuyên các lần invocation nếu lịch có thể chạy trên các worker khác nhau.

## 14. Một lần chạy ném exception: lịch định kỳ bị dừng

Đặc tính quan trọng của `scheduleAtFixedRate` và `scheduleWithFixedDelay`: nếu một execution ném một exception **thoát ra khỏi `Runnable.run()`**, các lần thực thi sau của periodic task đó **bị suppress**. Đây không chỉ là một failed tick; chuỗi periodic execution có thể chấm dứt.

`ScheduledFuture` đại diện cho chuỗi ấy khi đó hoàn tất theo đường lỗi:

- `isDone() == true`, vì chuỗi đã chấm dứt.
- `isCancelled() == false` nếu nó chấm dứt do exception chứ không phải cancellation.
- `future.get()` ném `ExecutionException`, nguyên nhân nằm ở `getCause()`.
- Scheduler có thể vẫn chạy những scheduled tasks khác; **không có nghĩa toàn bộ executor đã shutdown**.

### Ví dụ 5 — lỗi ở lượt thứ hai dừng lịch

Tạo `PeriodicFailureDemo.java` (Java 17+):

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        AtomicInteger count = new AtomicInteger();

        try {
            ScheduledFuture<?> future = pool.scheduleAtFixedRate(() -> {
                int n = count.incrementAndGet();
                if (n == 2) {
                    throw new IllegalStateException("boom");
                }
            }, 0, 1, TimeUnit.MILLISECONDS);

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("runs = " + count.get());
            System.out.println("isDone = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac PeriodicFailureDemo.java
java PeriodicFailureDemo
~~~

Stdout:

~~~text
cause = IllegalStateException
runs = 2
isDone = true
isCancelled = false
~~~

Tại invocation 2, unchecked exception thoát khỏi body, chuỗi chạy định kỳ **không được tiếp tục**. `get()` đang chờ periodic Future sẽ được giải phóng bằng `ExecutionException` (thay vì đợi vô hạn). Đây là một điểm rất dễ bỏ sót nếu chương trình schedule job rồi bỏ qua `ScheduledFuture`.

### Bắt exception hay để lịch dừng?

Phải quyết định theo ngữ nghĩa nghiệp vụ:

- **Fail-fast:** nếu một lỗi làm state không còn hợp lệ, cho exception thoát để dừng schedule, báo lỗi và chờ operator/coordinator.
- **Continue after a recoverable error:** bắt những exception đã hiểu, ghi nhận lỗi, xử lý retry/backoff hợp lệ rồi return bình thường để scheduler cho phép lượt tiếp.
- **Do not swallow everything:** bắt `Throwable` bừa bãi rồi tiếp tục có thể che giấu `Error` nghiêm trọng; log/retry vô hạn không có giới hạn cũng có thể phá hệ thống.
- **Interrupt handling:** nếu `InterruptedException` xuất hiện khi đang xử lý blocking call, cân nhắc restore interrupt flag và thoát đúng policy; đừng coi shutdown như một lỗi cần retry ngay lập tức.

Một wrapper minh họa:

~~~java
// Snippet trong scheduled Runnable; không phải chương trình độc lập.
try {
    pollOnce();
} catch (RecoverableDomainException e) {
    recordFailure(e);
    // Return để lần sau được phép chạy.
}
~~~

Exception do `recordFailure` ném ra vẫn có thể dừng periodic execution. Cần theo dõi cả **lần chạy cuối thành công** và **số lỗi** ở một nơi được kiểm soát, không chỉ kiểm tra executor còn sống hay không.

## 15. ScheduledFuture: trạng thái, get và cancellation

Hai method định kỳ trả về một `ScheduledFuture<?>`. Handle này đại diện cho **toàn bộ chuỗi periodic execution**, không tạo một Future mới cho mỗi lần callback được gọi.

| Thời điểm | `isDone` | `isCancelled` | `get()` |
| --- | --- | --- | --- |
| Đang đợi initial delay | Thường false | false | Chờ |
| Có invocation đang chạy hoặc lịch đang lặp bình thường | false | false | **Tiếp tục chờ** (không trả sau một lần chạy) |
| Một invocation ném exception thoát ra | true | false | `ExecutionException` |
| `cancel` thành công | true | true | `CancellationException` |
| Executor shutdown và periodic schedule bị hủy theo policy | true | true (nếu Future bị cancel) | `CancellationException` |

`getDelay(unit)` phản ánh thời gian còn lại đến khi task đủ điều kiện chạy theo cơ chế scheduler, **không** cho biết duration của callback hoặc một start-time guarantee. Với periodic task đang quá hạn, delay có thể bằng 0 hoặc âm tùy thời điểm/API, nhưng không thể suy ra có nhiều bản sao đang chạy chồng.

### Cancellation không ép callback đang chạy dừng tức thì

- `future.cancel(false)`: yêu cầu ngừng những lần chạy sau, không yêu cầu interrupt invocation hiện tại. Future có thể cancelled trong khi callback đang chạy vẫn tiếp tục làm việc.
- `future.cancel(true)`: yêu cầu ngừng những lần chạy sau và **cố interrupt** callback đang chạy nếu implementation cho phép. Task phải hợp tác với interruption/timeout mới dừng sớm an toàn.
- `isDone()==true` sau cancel không phải bằng chứng mọi side effect đang thực hiện đã kết thúc, không phải transaction rollback.
- `get(timeout)` timeout chỉ giới hạn **lần chờ ở caller**, không tự cancel schedule. Với periodic Future bình thường còn chạy lặp, `get(timeout)` rất dễ timeout vì Future không có kết quả bình thường mỗi chu kỳ.

Nếu muốn biết một lần chạy cụ thể đã xử lý xong, hãy dùng `CountDownLatch`, `CompletableFuture`/acknowledgment theo lần chạy, metrics hoặc state machine riêng. Không lạm dụng `ScheduledFuture.get()` như cơ chế “wait until next tick finishes”.

## 16. Ví dụ 6 — cancel một periodic task trước khi bắt đầu

Tạo `CancelPeriodicDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelPeriodicDemo {
    public static void main(String[] args) throws InterruptedException {
        ScheduledThreadPoolExecutor pool =
                new ScheduledThreadPoolExecutor(1);
        pool.setRemoveOnCancelPolicy(true);

        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> future = pool.scheduleAtFixedRate(
                    runs::incrementAndGet,
                    1, 1, TimeUnit.DAYS);

            System.out.println("cancelled = " + future.cancel(false));
            System.out.println("done = " + future.isDone());
            System.out.println("isCancelled = " + future.isCancelled());
            System.out.println("queued entries = " + pool.getQueue().size());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get = CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }

        System.out.println("runs = " + runs.get());
    }
}
~~~

Chạy:

~~~bash
javac CancelPeriodicDemo.java
java CancelPeriodicDemo
~~~

Stdout:

~~~text
cancelled = true
done = true
isCancelled = true
queued entries = 0
get = CancellationException
runs = 0
~~~

Initial delay là một ngày, nên việc cancel ngay sau schedule diễn ra trước lần chạy đầu. `setRemoveOnCancelPolicy(true)` đảm bảo những delayed task đã cancel không bị giữ lại trong queue lâu không cần thiết theo implementation `ScheduledThreadPoolExecutor`.

**Lưu ý memory retention:** Mặc định `ScheduledThreadPoolExecutor` có thể giữ cancelled delayed tasks trong work queue đến khi tới thời điểm lịch, dù chúng sẽ không được chạy; policy remove-on-cancel giúp giải phóng sớm hơn. Không nhầm nó với method trên `ThreadPoolExecutor` thông thường.

## 17. `ScheduledThreadPoolExecutor` và số worker

`Executors.newScheduledThreadPool(corePoolSize)` tạo scheduler với số core workers được yêu cầu. Khác với `ThreadPoolExecutor` dùng bounded queue tùy ý, implementation `ScheduledThreadPoolExecutor` dùng một delayed work queue **không giới hạn hữu dụng ở mức ứng dụng**; tài liệu lưu ý nó hoạt động như một **fixed-sized pool bằng `corePoolSize`** và việc chỉnh `maximumPoolSize` không có hiệu ứng hữu ích.

Những hệ quả:

- Nhiều delayed tasks hoặc periodic schedules khác nhau có thể cùng đủ điều kiện chạy nhưng phải **đợi worker rảnh**.
- Nếu corePoolSize=1 và task A blocking, task B có thể bị hoãn dù B có deadline sớm.
- Nếu corePoolSize=4, một periodic task A chạy quá lâu vẫn **không tự overlap**; nhưng task B, C, D có thể dùng worker khác.
- Nếu có rất nhiều periodic schedules, việc queue tồn tại không biến số worker thành vô hạn; tổng tải vẫn bị giới hạn bởi CPU, I/O và downstream.
- Các scheduled future/queue entries có thể giữ object graph và tăng memory pressure nếu số lịch đăng ký phát triển không kiểm soát.

**Không tăng `maximumPoolSize` mong sửa backlog** của ScheduledThreadPoolExecutor; hãy đo mức sử dụng core workers, thời gian invocation, số lịch độc lập, chờ queue và downstream saturation. Tăng corePoolSize chỉ thích hợp khi tác vụ độc lập và tài nguyên bên ngoài chịu được concurrency tăng.

### Không giảm core pool tùy tiện về 0

Tài liệu `ScheduledThreadPoolExecutor` khuyến nghị thường không đặt `corePoolSize=0` hoặc bật timeout cho core threads vì có thể dẫn đến scheduler không có thread sẵn sàng xử lý task khi tới hạn. Đây là một tradeoff khác với executor chuyên chạy request bursts.

## 18. Shutdown: policy nào ảnh hưởng task định kỳ?

`ScheduledExecutorService` quản lý task, còn `ScheduledThreadPoolExecutor` có policy đặc biệt cho những lịch còn chờ:

- `setContinueExistingPeriodicTasksAfterShutdownPolicy(boolean)`: quyết định các periodic task đã đăng ký **có được tiếp tục** sau `shutdown()` hay không. Mặc định **false**, nghĩa các periodic tasks hiện hữu không tiếp tục sau shutdown.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(boolean)`: quyết định one-shot delayed tasks đã nhận **có được chạy** sau `shutdown()` hay không. Mặc định **true**.
- `setRemoveOnCancelPolicy(boolean)`: yêu cầu xóa ngay cancelled tasks khỏi queue theo policy của implementation, tránh giữ chúng tới thời hạn lịch.
- `shutdownNow()`: best effort interrupt các task running và trả những task chưa bắt đầu; không bảo đảm body đang chạy hợp tác dừng tức khắc.
- `awaitTermination(timeout, unit)`: đợi executor terminated sau shutdown; bản thân method không hủy/chạy thêm task.

Ví dụ phối hợp shutdown:

~~~java
// Snippet minh họa trong method có thể ném InterruptedException.
periodicFuture.cancel(true);
scheduler.shutdown();

if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
    scheduler.shutdownNow();
    scheduler.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Nếu bạn bật `continueExistingPeriodicTasksAfterShutdownPolicy(true)` mà không chủ động hủy lịch, scheduler có thể tiếp tục chạy periodic tasks và không terminated như kỳ vọng. Vì vậy **đừng cấu hình policy rồi quên quản lý handles**.

Khi cần dừng có trật tự, thường:

1. Ngừng đăng ký periodic tasks mới.
2. Chọn rõ task đang chạy được **đợi hoàn tất** hay bị **yêu cầu interrupt**.
3. Cancel các handles theo policy nghiệp vụ.
4. Gọi `shutdown()` và đợi bằng `awaitTermination` với timeout.
5. Dùng `shutdownNow()` cho nhánh escalation nếu cần, rồi ghi nhận trạng thái còn tồn tại.
6. Giải phóng I/O/database resources **sau khi đã xác nhận** task không còn dùng chúng hoặc có protocol đồng bộ shutdown.

Tín hiệu cancel thành công không tự chứng minh body đã dừng; nếu task đang block trong I/O không interruptible, có thể cần deadline/socket timeout hoặc cách dừng khác.

## 19. Khi periodic task tự submit tác vụ con: khả năng overlap gián tiếp

Một design rất dễ gây nhầm:

~~~java
// Snippet, không phải chương trình độc lập.
scheduler.scheduleAtFixedRate(() -> {
    workerPool.submit(this::longOperation);
}, 0, 100, TimeUnit.MILLISECONDS);
~~~

Scheduled Runnable chỉ thực hiện **submit rồi return** trong thời gian ngắn. Vì vậy scheduler **không overlap phần Runnable submit**, nhưng những task `longOperation` đã submit có thể **chạy song song** hoặc **tồn đọng** ở workerPool.

Hậu quả:

- `longOperation` có thể bị chạy đồng thời dù periodic scheduler tuân thủ no-overlap tuyệt đối.
- Nếu workerPool có queue không giới hạn, backlog tăng khi production rate vượt completion rate.
- Hủy `ScheduledFuture` chỉ dừng **những lần submit trong tương lai**, không tự hủy các task con đã được workerPool nhận.
- `shutdown()` scheduler không tự shutdown workerPool nếu ứng dụng tạo hai executor độc lập.
- Nếu task con thay đổi shared state, cần atomicity, idempotency, lock hoặc serial executor phù hợp.

Để tránh overlap nghiệp vụ, có thể **để toàn bộ xử lý trong scheduled Runnable** và dùng fixed delay; hoặc đặt gate như `Semaphore.tryAcquire()`/`AtomicBoolean.compareAndSet(false,true)` quanh toàn bộ asynchronous operation với release đúng một lần trong mọi nhánh. Nếu gate bị release quá sớm (ngay sau `submit`) thì vẫn overlap.

### Mẫu chống overlap với AtomicBoolean (minh họa)

~~~java
// Snippet cấu trúc trong một class có fields tương ứng.
AtomicBoolean inFlight = new AtomicBoolean();

void tick() {
    if (!inFlight.compareAndSet(false, true)) {
        return; // Bỏ lượt khi công việc trước chưa kết thúc.
    }

    try {
        doWorkSynchronously();
    } finally {
        inFlight.set(false);
    }
}
~~~

Mẫu này chỉ hợp nếu công việc hoàn tất ngay trong `doWorkSynchronously()`. Nếu thay bằng `workerPool.submit(...)` mà `finally` luôn release ngay khi submit trả về, gate trở nên vô nghĩa. Với async work, phải release sau khi **thực sự** hoàn tất hoặc fail/cancel, và bảo đảm không leak gate nếu task chưa bao giờ bắt đầu. Đây là bài toán lifecycle/ownership riêng.

## 20. Task có I/O lâu: thiết kế cancellation và timeout

“Không overlap” không giải quyết một job **bị treo vĩnh viễn**. Nếu một invocation chờ network response vô hạn:

- Fixed rate sẽ không tự tạo invocation mới để thay thế invocation đang kẹt.
- Fixed delay cũng không chạy lượt kế tiếp.
- Scheduler pool có thể mất một worker trong thời gian dài.
- Cancel(true) có thể không ngắt ngay một I/O API không interruptible.
- Các tasks độc lập khác vẫn có thể chạy nếu pool còn worker, nhưng tài nguyên chung có thể bị ảnh hưởng.

Checklist:

- Đặt socket/connect/read timeout hoặc API-specific deadline.
- Hỗ trợ interrupt ở các điểm có thể, đừng nuốt `InterruptedException`.
- Đặt try-with-resources/`finally` để dọn dẹp tài nguyên thuộc task.
- Không giữ một lock chung qua I/O quá lâu.
- Theo dõi **start time, duration, last successful run, error count, cancellation latency**.
- Nếu một invocation đã quá hạn, chọn rõ cancel, skip, retry/backoff hay báo lỗi.
- Đảm bảo operation idempotent nếu có khả năng retry sau timeout hoặc process restart.
- Không mặc định cancel là rollback side effect đã commit.

Với periodic callback nặng, nên tách phần “quyết định có cần làm gì” khỏi phần I/O thật, nhưng phải thiết kế lại điều phối work nếu tách thành asynchronous child tasks.

## 21. Fixed rate có tương đương cron hay một đồng hồ tuyệt đối không?

Không. `scheduleAtFixedRate` trong Java SE lập lịch theo **relative delays/periods**; nó không phải một lịch cron với calendar semantics như “00:00 mỗi ngày theo múi giờ X”. Những chủ đề khác:

- Timezone, DST và giờ địa phương nhảy lùi/tiến.
- Leap seconds, đồng bộ NTP, đổi thời gian hệ thống.
- Một lịch “ngày đầu tháng”, “thứ Hai 9 giờ” hay “sau mỗi ngày lịch”.
- Khởi động lại tiến trình, mất lịch khi JVM dừng, chạy lại những lượt bỏ lỡ.
- Có nhiều JVM/instances cùng chạy một job.

`ScheduledExecutorService` **không cung cấp distributed single-leader lock hoặc durable scheduling**. Nếu có nhiều JVM cùng đăng ký periodic job, mỗi JVM có thể chạy job riêng và gây overlap trên cùng dữ liệu ngoài hệ thống. Muốn một lịch business “chỉ chạy một lần trên toàn cluster”, cần protocol coordinator/lease/lock/durable scheduler ở tầng phù hợp; không được suy từ no-overlap **trong một periodic Future**.

Khi muốn bám lịch giờ tường, hãy tính thời điểm kế tiếp từ `ZonedDateTime`/calendar rule phù hợp, chuyển thành delay tương ứng và xử lý clock/holiday/DST theo yêu cầu; không chỉ đặt `period=24 hours` rồi mặc định đó là “mỗi ngày lúc 09:00” mãi mãi.

## 22. Quan sát và kiểm thử hành vi task chạy lâu

### A. Quan sát thực tế

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Last start / last finish | Biết invocation hiện tại có tiến triển |
| Duration từng lượt, p95/p99 | Nhìn thấy tác vụ nào vượt period/delay |
| Time since last successful finish | Phát hiện job âm thầm dừng vì exception |
| Number of failures | Phân biệt scheduler còn sống với job còn thành công |
| Late start/drift | Đo fixed-rate schedule có trễ so với mốc danh nghĩa |
| Missed business deadlines | Quan trọng hơn số tick trong JVM |
| Pool active threads / queue size | Nhìn thấy contention giữa các scheduled tasks khác nhau |
| Cancellation-to-stop latency | Future cancelled rồi body thực sự dừng sau bao lâu |
| Downstream saturation | Task định kỳ có tạo quá tải DB/API không |

Một periodic Future ở `isDone=false` không chứng minh “job vẫn hoạt động tốt”: nó có thể bị kẹt ở một invocation chưa kết thúc. Cần đo duration/last finish. Ngược lại, `isDone=true` chưa chắc là job thành công; có thể do exception hoặc cancellation.

### B. Dùng latch để test overlap thay vì đoán scheduling

Một test đáng tin nên:

1. Bắt đầu một invocation và giữ nó ở một điểm có thể kiểm soát.
2. Xác nhận invocation đã vào body bằng latch.
3. Dùng một worker khác/điều phối để tạo cơ hội chạy task độc lập.
4. Khi invocation đầu vẫn bị giữ, kiểm tra same-schedule run count không tăng.
5. Nhả latch hoặc cancel trong `finally` để không kẹt test.
6. Đợi executor termination (có timeout) trước khi rời test.
7. Tách xác minh **contract non-overlap** khỏi đo **timing jitter**.

Đừng viết test `Thread.sleep(110)` rồi giả định chắc chắn invocation thứ hai đã chạy hoặc OS phải schedule đúng 110 ms. Lập lịch không cung cấp deadline cứng, stress test chỉ hỗ trợ chứng minh trong điều kiện quan sát chứ không thay tài liệu API.

### C. Khi so sánh fixed rate và fixed delay

Không chỉ đếm số lần chạy trong 1 giây rồi kết luận. Nếu task có thời lượng thay đổi, số invocation phụ thuộc scheduler jitter, GC và resource contention. Hãy đo **thời điểm start/finish** bằng monotonic clock (ví dụ `System.nanoTime()`) và tính:

- Với fixed rate: khoảng cách giữa các start so với period danh nghĩa.
- Với fixed delay: khoảng cách giữa **finish trước** và **start sau** so với delay.
- Với cả hai: liệu có trường hợp cùng periodic Future có hai invocations active không; theo contract là không.
- Lượng công việc mới do mỗi invocation sinh ra, đặc biệt khi có child tasks/worker queues.

## 23. Sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm / sửa thế nào |
| --- | --- |
| “Fixed rate sẽ chạy chồng cùng task khi bị trễ.” | Không, các successive executions trong cùng periodic schedule không overlap. |
| “Pool có 8 worker nên 8 lần của cùng task chạy đồng thời.” | Pool có thể chạy **tám task khác nhau**, không vi phạm no-overlap từng schedule. |
| “Fixed delay là 100 ms giữa hai thời điểm bắt đầu.” | Delay tính từ **finish lần trước** tới lần sau đủ điều kiện. |
| “Fixed rate luôn chờ đúng period sau khi xong.” | Khi đã trễ, lượt sau có thể bắt đầu rất sớm, gần như ngay sau lần trước. |
| “Mỗi period quá hạn tạo một bản sao task chạy song song.” | Không phải hợp đồng của hai periodic scheduling methods. |
| “Hai lời gọi schedule của cùng Runnable là một task.” | Chúng là hai schedules độc lập, có thể overlap nhau. |
| “Lượt trước chạy trên worker-1 thì lượt sau cũng vậy.” | Implementation có thể dùng worker khác; không dựa vào ThreadLocal xuyên lượt. |
| “No-overlap scheduler cũng bảo vệ task con asynchronous.” | Không; task con có lifecycle riêng và có thể chồng/chờ trong pool khác. |
| “Periodic Future.get() trả về sau một lượt chạy.” | Periodic schedule bình thường không có normal result sau mỗi lần. |
| “Job ném exception nhưng scheduler sẽ tiếp tục chạy lượt sau.” | Uncaught exception làm các lần kế tiếp bị suppress. |
| “Future bị cancel là body đã dừng sạch.” | Cancel không bảo đảm worker đã dừng tức thì hay side effect được rollback. |
| “Tăng maximumPoolSize của ScheduledThreadPoolExecutor.” | Với delayed unbounded queue, max pool setting không hữu ích như nhiều người kỳ vọng. |
| “shutdown() luôn dừng mọi lịch one-shot và periodic như nhau.” | Delayed và periodic tasks có policy tiếp tục khác nhau. |
| “Fixed rate 24h là cron 9:00 mỗi ngày.” | Calendar/DST và relative period là các bài toán khác. |
| “Mỗi JVM đều no-overlap nghĩa toàn cluster không overlap.” | Không có distributed coordination trong ScheduledExecutorService. |
| “Không có exception là job đang khỏe.” | Task có thể bị treo; cần theo dõi last successful finish và duration. |

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Tác vụ fixed-rate có period 100 ms, mỗi execution mất 250 ms. Hai invocation của cùng một `ScheduledFuture` có đồng thời chạy không?  
**Đáp án:** Không. Lượt tiếp theo có thể trễ và bắt đầu sát sau lượt trước, nhưng không overlap.

**Câu 2.** Với mô hình lý tưởng trên, fixed rate và fixed delay 100 ms cho các mốc start nào?  
**Đáp án:** Fixed rate có thể bắt đầu tại 0, 250, 500, 750 ms; fixed delay bắt đầu tại 0, 350, 700, 1050 ms nếu mỗi lượt luôn 250 ms.

**Câu 3.** Một periodic task fixed-delay có duration 250 ms và delay 100 ms. Khoảng cách giữa hai lần **bắt đầu** có ít nhất bằng 100 ms không?  
**Đáp án:** Có, nhưng thường khoảng cách là duration trước + delay + scheduling overhead, xấp xỉ 350 ms trong mô hình lý tưởng.

**Câu 4.** `Executors.newScheduledThreadPool(4)` có cho phép task A và B chạy đồng thời không?  
**Đáp án:** Có thể, nếu là **hai schedules khác nhau** và có worker sẵn có. Không làm A overlap với lần A kế tiếp.

**Câu 5.** Hai lần `scheduleAtFixedRate(sameRunnable, ...)` có tạo một periodic schedule duy nhất không?  
**Đáp án:** Không. Hai Future độc lập có thể gọi cùng Runnable đồng thời.

**Câu 6.** Một execution ném `RuntimeException` thoát khỏi Runnable. Lượt kế tiếp có tự chạy tiếp không?  
**Đáp án:** Không. Các executions tiếp theo bị suppress; Future kết thúc exceptional và `get()` ném `ExecutionException`.

**Câu 7.** Một periodic Future chạy được 10 lần và chưa cancel. `get()` có trả bình thường không?  
**Đáp án:** Không. Periodic Future đại diện toàn lịch, thường chưa hoàn tất bình thường.

**Câu 8.** `cancel(true)` được gọi lúc invocation đang chờ network I/O. Có chắc network call dừng ngay không?  
**Đáp án:** Không. Chỉ cố interrupt, cần I/O timeout và cancellation cooperative.

**Câu 9.** Fixed rate có thể tạo áp lực lớn cho downstream khi một execution bị trễ không?  
**Đáp án:** Có, các invocation sau có thể chạy rất sát nhau; fixed delay chờ thêm sau mỗi finish.

**Câu 10.** Nếu Runnable định kỳ chỉ `submit(longTask)` rồi return, có còn bảo đảm `longTask` không overlap không?  
**Đáp án:** Không. Scheduler chỉ không overlap invocation của Runnable, còn child tasks thuộc pool khác có thể đồng thời.

**Câu 11.** `setContinueExistingPeriodicTasksAfterShutdownPolicy(true)` có thể ảnh hưởng gì?  
**Đáp án:** Periodic tasks hiện hữu có thể tiếp tục sau `shutdown`; cần chủ động cancel để scheduler có thể terminated.

**Câu 12.** Fixed rate period 24 giờ có giống “mỗi ngày 09:00 tại timezone X” không?  
**Đáp án:** Không. Một period tương đối không thay calendar rules/DST.

## Tài liệu tham khảo Java SE

- [`ScheduledExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): `scheduleAtFixedRate`/`scheduleWithFixedDelay`, initial delay, period/delay, exception suppression.
- [`ScheduledThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): successive executions không overlap, happens-before, core pool, remove-on-cancel, shutdown policies.
- [`ScheduledFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): handle cho delayed/periodic job.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isDone`, `get`.
- [`Executors` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): factory `newScheduledThreadPool`.
- [`TimeUnit` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): chuyển đổi và biểu diễn thời gian.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối test xác định.

**Ghi nhớ:** `scheduleAtFixedRate` giữ nhịp **mốc bắt đầu dự kiến**, nên khi bị trễ các lượt có thể nối sát nhau; `scheduleWithFixedDelay` luôn đợi thêm **delay sau khi lượt trước kết thúc**. **Cả hai không tự chạy chồng các lần thực thi của cùng periodic task**, nhưng các schedules khác, các child tasks bất đồng bộ hoặc các JVM khác vẫn có thể cạnh tranh tài nguyên.