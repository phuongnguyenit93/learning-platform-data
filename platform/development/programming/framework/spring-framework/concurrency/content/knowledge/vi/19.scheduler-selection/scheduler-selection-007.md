# Giới hạn fixed-delay chạy trên luồng scheduler của SimpleAsyncTaskScheduler

## 1. Một ngoại lệ ảnh hưởng đến kiến trúc

`SimpleAsyncTaskScheduler` (Spring Framework 6.1+) thường được giới thiệu là
scheduler sử dụng một thread để kích hoạt và những thread riêng để chạy
callback. **Không áp dụng mô hình đó một cách máy móc cho fixed-delay.**
Theo Javadoc của Spring, fixed-delay chạy ngay trên **scheduler thread duy
nhất** để giữ semantics: lần tiếp theo chỉ bắt đầu sau khi callback trước
**hoàn tất** và khoảng delay đã trôi qua.

Ví dụ một scheduled method xử lý I/O trong 8 giây và có
`fixedDelay = 2000`. Trong một chu kỳ thông thường, callback đầu hoàn thành
sau 8 giây, sau đó mới nghỉ thêm 2 giây. Với
`SimpleAsyncTaskScheduler`, callback fixed-delay dài còn có thể chiếm
scheduler thread, **làm các tác vụ fixed-delay khác phải chờ**.

## 2. Đối chiếu ba chế độ kích hoạt

| Chế độ | Mốc thời gian chính | Điều cần hiểu |
| --- | --- | --- |
| Fixed-delay | Khoảng cách từ *kết thúc* callback tới *bắt đầu* lần kế tiếp | Callback có thể giữ scheduler thread của SimpleAsyncTaskScheduler |
| Fixed-rate | Nhắm vào nhịp kích hoạt có chu kỳ | Có thể giao các lần kích hoạt sang thread khác; phải xét khả năng chồng lấn |
| Cron | Các thời điểm theo biểu thức lịch và múi giờ | Việc tính thời điểm không đồng nghĩa công việc hoàn thành đúng thời điểm |

Đổi fixed-delay sang fixed-rate **không phải** thao tác tối ưu hóa vô hại:
ngữ nghĩa vận hành thay đổi. Fixed-delay thường thể hiện ý định “làm xong rồi
nghỉ”; fixed-rate thể hiện “cố bám theo nhịp thời gian”. Nếu nghiệp vụ không
cho phép hai lần cập nhật dữ liệu chồng nhau, cần thêm cơ chế **single-flight**,
lock/lease hoặc kiểm soát ở phía dữ liệu; không chỉ đổi annotation.

## 3. Ví dụ tái hiện head-of-line blocking

```java
import java.util.concurrent.CountDownLatch;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class FixedDelayExperiments {
    private final CountDownLatch release = new CountDownLatch(1);

    // Dùng cùng bean SimpleAsyncTaskScheduler cấu hình ở bài trước.
    @Scheduled(scheduler = "reportScheduler", fixedDelay = 2_000)
    public void slowJob() throws InterruptedException {
        System.out.println("SLOW: " + Thread.currentThread().getName());
        release.await();
    }

    @Scheduled(scheduler = "reportScheduler", fixedDelay = 2_000)
    public void anotherJob() {
        System.out.println("OTHER: " + Thread.currentThread().getName());
    }

    public void releaseExperiment() {
        release.countDown();
    }
}
```

Đây là **bài thí nghiệm có chủ đích**, không đưa vào ứng dụng production:
callback `slowJob` bị giữ cho đến khi có lệnh `releaseExperiment()`.
Dùng test có timeout và `finally` để nhả latch ngay cả khi assertion lỗi.
Quan sát tên thread và số lượt thực thi của hai callback, tránh kết luận từ
một trace duy nhất vì thứ tự ban đầu còn phụ thuộc lịch chạy của hệ điều hành.

## 4. Lựa chọn thiết kế

- Nếu cần giữ ngữ nghĩa fixed-delay cho job có thể chạy lâu, xem xét một
  `ThreadPoolTaskScheduler` với số worker phù hợp và kế hoạch thử tải.
  Cần nhớ mỗi chuỗi periodic vẫn có thứ tự/điều kiện hoàn tất riêng, không
  tự bảo đảm toàn hệ thống không chồng lấn.
- Nếu cần tách kích hoạt khỏi việc xử lý lâu, dùng một callback ngắn chỉ làm
  nhiệm vụ gửi việc sang executor có giới hạn. Khi đó **thời điểm callback
  kết thúc không còn là thời điểm công việc thật kết thúc**; fixed-delay sẽ
  tính theo phần giao việc ngắn, chứ không tính theo business task phía sau.
- Nếu bản chất job cần bảo đảm độ bền, retry qua restart hoặc chỉ một máy
  trong cụm thực thi, một scheduler in-memory không đủ. Cần durable
  queue/job store hoặc coordination riêng.

## 5. Checklist trước khi quyết định

1. Delay cần đo từ lúc callback hoàn tất hay từ lúc nghiệp vụ bên dưới hoàn tất?
2. Hai lượt có được phép chồng lấn không? Nếu không, state nào bảo đảm điều đó?
3. Một callback chặn scheduler thread có gây trễ các lịch khác hay không?
4. Khi task bị hủy, interrupt được xử lý hợp tác hay callback tiếp tục?
5. Metric nào đo *schedule lag*, *execution duration*, *handoff latency*
   và *business completion* riêng biệt?

## 6. Kết luận

Fixed-delay trên `SimpleAsyncTaskScheduler` là trường hợp phải đặc biệt cẩn
thận vì chạy trên scheduler thread duy nhất. Hãy lựa chọn scheduler theo
semantics của công việc, không chỉ dựa vào khả năng tạo virtual threads.

**Tham khảo:** [Spring Scheduling Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
