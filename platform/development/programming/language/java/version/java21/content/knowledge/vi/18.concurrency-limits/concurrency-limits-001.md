# Tách số lượng task khỏi giới hạn tài nguyên đang sử dụng

## Mục tiêu

Java 21 virtual threads cho phép tạo một thread nhẹ cho mỗi task, kể cả khi có rất nhiều task đang chờ I/O. Khả năng tạo nhiều task không có nghĩa ứng dụng nên cho phép tất cả cùng truy cập database, dịch vụ HTTP hoặc một tài nguyên hữu hạn. Mỗi dependency vẫn có giới hạn kết nối, số request đồng thời và năng lực xử lý riêng.

Vì vậy cần tách hai câu hỏi:

- Ứng dụng có bao nhiêu task đang được tiếp nhận hoặc chờ xử lý?
- Có bao nhiêu task được phép đồng thời sử dụng một tài nguyên cụ thể?

Bài học này trình bày cách giới hạn số thao tác đang ở trong vùng sử dụng tài nguyên bằng `Semaphore`, kết hợp với connection pool, timeout, admission control và backpressure. Các API được dùng là API ổn định trong Java 21; không cần bật preview feature.

## 1. Số lượng task không phải là số lượng tài nguyên đang được dùng

Một request có thể tạo nhiều task độc lập. Với `Executors.newVirtualThreadPerTaskExecutor()`, mỗi task được submit có thể chạy trên một virtual thread riêng. Executor này thuận tiện cho mô hình một task một virtual thread, nhưng không phải một pool có giới hạn số worker.

Ví dụ, một service nhận 1.000 request cùng lúc. Mỗi request gọi một API đối tác. Ứng dụng có thể tạo 1.000 virtual thread, nhưng đối tác chỉ cho phép tối đa 30 request đang xử lý. Nếu tất cả 1.000 task cùng gửi request ra ngoài, ứng dụng có thể nhận lỗi quá tải, timeout hoặc bị đối tác giới hạn lưu lượng.

Hãy phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Task concurrency | Số task đang thực thi hoặc chờ hoàn tất | 1.000 request đang được xử lý |
| Resource concurrency | Số task đang giữ hoặc sử dụng một tài nguyên cụ thể | Tối đa 30 lời gọi API đối tác đang in-flight |
| Admission limit | Số công việc được phép đi vào hệ thống hoặc một vùng xử lý | Tối đa 200 request đang được nhận |
| Rate limit | Số lần gọi được phép trong một khoảng thời gian | Tối đa 100 request mỗi giây |

Các giới hạn này giải quyết những vấn đề khác nhau. Giới hạn resource concurrency không tự giới hạn tổng số task đang chờ; giới hạn rate không nhất thiết giới hạn số request đang đồng thời chạy; và số virtual thread không phải ngân sách kết nối database.

## 2. Vì sao virtual threads vẫn cần giới hạn tài nguyên?

Virtual thread giảm chi phí duy trì thread trong lúc chờ. Khi một virtual thread thực hiện thao tác blocking được JVM hỗ trợ, nó có thể nhường carrier thread để carrier phục vụ virtual thread khác. Điều đó giúp tăng khả năng xử lý đồng thời, nhưng không làm tăng năng lực của dependency.

Ví dụ, nếu database chỉ có 40 connection trong pool, 500 virtual thread không thể đồng thời sử dụng 500 connection từ pool đó. Các task còn lại phải chờ lấy connection. Nếu thời gian chờ không được kiểm soát, số task chờ có thể tăng, giữ bộ nhớ và kéo dài latency của request.

Các tài nguyên thường cần giới hạn riêng:

- Connection đến database hoặc message broker.
- Số request đồng thời gửi đến một API đối tác.
- Số tác vụ truy cập một dịch vụ có quota hoặc năng lực xử lý cố định.
- Số thao tác đọc/ghi vào một hệ thống file hoặc thiết bị có giới hạn.
- Số tác vụ sử dụng một tài nguyên trong tiến trình mà không thể chia sẻ an toàn.

Không nên giải quyết tất cả bằng cách giảm số virtual thread. Hãy xác định tài nguyên nào là nút thắt và đặt giới hạn ngay tại ranh giới sử dụng tài nguyên đó.

## 3. Dùng `Semaphore` để giới hạn số thao tác đồng thời

`Semaphore` quản lý một số lượng permit. Task phải lấy permit trước khi đi vào vùng sử dụng tài nguyên; khi hoàn tất, task trả permit để task khác có thể tiếp tục.

Ví dụ giới hạn tối đa 20 lời gọi đến một dịch vụ:

```java
import java.util.concurrent.Semaphore;

class PartnerService {
    private static final Semaphore CALL_LIMIT = new Semaphore(20);

    static String call(String request) throws InterruptedException {
        CALL_LIMIT.acquire();
        try {
            return invokePartner(request);
        } finally {
            CALL_LIMIT.release();
        }
    }

    private static String invokePartner(String request) {
        // Thay bằng lời gọi dịch vụ thực tế.
        return "Processed: " + request;
    }
}
```

Với 20 permit, tối đa 20 task có thể cùng nằm trong `invokePartner()`. Task thứ 21 trở đi phải chờ `acquire()` cho đến khi có permit được trả lại.

Khối `try/finally` rất quan trọng. Permit phải được trả dù thao tác thành công hay ném exception. Nếu chỉ gọi `release()` ở cuối nhánh thành công, một lỗi có thể làm mất permit vĩnh viễn và giảm dần năng lực xử lý của service.

Chỉ gọi `release()` sau khi đã lấy được permit. Nếu `acquire()` bị interrupt trước khi lấy permit, không được trả một permit mà task chưa sở hữu.

## 4. Dùng `tryAcquire()` để giới hạn thời gian chờ

`acquire()` có thể chờ không thời hạn. Trong request xử lý trực tuyến, thường cần giới hạn cả thời gian chờ permit. `tryAcquire(timeout, unit)` chờ tối đa khoảng thời gian chỉ định và trả `false` nếu không lấy được permit.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class TimedPartnerService {
    private static final Semaphore CALL_LIMIT = new Semaphore(20);

    static String call(String request)
            throws InterruptedException, TimeoutException {
        boolean acquired = CALL_LIMIT.tryAcquire(250, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new TimeoutException("Dịch vụ đang quá tải");
        }

        try {
            return invokePartner(request);
        } finally {
            CALL_LIMIT.release();
        }
    }

    private static String invokePartner(String request) {
        return "Processed: " + request;
    }
}
```

Nếu không lấy được permit trong 250 ms, task rời khỏi luồng gọi dependency và có thể chuyển thành response phù hợp, chẳng hạn HTTP `503 Service Unavailable` hoặc một lỗi quá tải theo hợp đồng API. Không nên để request chờ vô hạn chỉ để được phép bắt đầu một thao tác vốn đã quá tải.

`tryAcquire()` không thay thế timeout của lời gọi mạng hoặc database sau khi permit đã được cấp. Cần cấu hình timeout cho chính thao tác I/O và luôn trả permit trong `finally` khi thao tác kết thúc.

## 5. Giới hạn đúng vùng sử dụng tài nguyên

Permit nên được giữ trong đúng khoảng thời gian tài nguyên thực sự đang được sử dụng. Không nên lấy permit quá sớm rồi thực hiện nhiều bước chuẩn bị không liên quan, vì điều đó làm giảm năng lực phục vụ của dependency.

```java
import java.util.concurrent.Semaphore;

class ResourceBoundaryExample {
    private static final Semaphore DATABASE_WORK = new Semaphore(12);

    static Report createReport(String userId) throws InterruptedException {
        ReportRequest request = validateAndPrepare(userId);

        DATABASE_WORK.acquire();
        try {
            return queryDatabaseAndBuildReport(request);
        } finally {
            DATABASE_WORK.release();
        }
    }

    record ReportRequest(String userId) {
    }

    record Report(String content) {
    }

    private static ReportRequest validateAndPrepare(String userId) {
        return new ReportRequest(userId);
    }

    private static Report queryDatabaseAndBuildReport(ReportRequest request) {
        return new Report("Report for " + request.userId());
    }
}
```

Trong ví dụ, xác thực và chuẩn bị request diễn ra trước khi lấy permit. Permit chỉ được giữ trong đoạn thao tác cần bảo vệ. Nếu việc xử lý sau truy vấn không còn sử dụng database, có thể trả permit ngay sau khi lấy xong dữ liệu thay vì giữ nó trong toàn bộ quá trình tạo response.

Với connection pool, bản thân thao tác lấy connection đã là một cơ chế giới hạn số connection vật lý. Không nên thêm semaphore cùng kích thước một cách máy móc nếu nó không giải quyết thêm một giới hạn thực tế; giới hạn kép có thể làm giảm throughput và gây khó hiểu khi phân tích thời gian chờ.

## 6. Kết hợp virtual threads với giới hạn tài nguyên

Một mô hình phổ biến là tạo một virtual thread cho mỗi request hoặc task, nhưng dùng semaphore để giới hạn số thao tác được phép đi vào dependency:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class VirtualThreadsWithBulkhead {
    private static final Semaphore PARTNER_LIMIT = new Semaphore(25);

    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 1; i <= 100; i++) {
                int requestId = i;
                executor.submit(() -> process(requestId));
            }
        }
    }

    private static void process(int requestId) {
        boolean acquired = false;
        try {
            acquired = PARTNER_LIMIT.tryAcquire(500, TimeUnit.MILLISECONDS);
            if (!acquired) {
                System.out.println("Từ chối request " + requestId + " do quá tải");
                return;
            }

            callPartner(requestId);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            if (acquired) {
                PARTNER_LIMIT.release();
            }
        }
    }

    private static void callPartner(int requestId) throws InterruptedException {
        // Mô phỏng thời gian sử dụng dịch vụ đối tác.
        Thread.sleep(200);
        System.out.println("Hoàn tất request " + requestId);
    }
}
```

Trong ví dụ, có thể có nhiều virtual thread tồn tại, nhưng tối đa 25 task cùng ở trong `callPartner()`. Virtual thread chờ permit không cần giữ một platform thread riêng trong suốt thời gian chờ khi dùng các thao tác đồng bộ được JVM hỗ trợ.

Đây là một dạng *bulkhead*: giới hạn sự cố hoặc quá tải của một dependency trong phạm vi riêng, giúp các phần khác của ứng dụng tiếp tục hoạt động. Có thể tạo semaphore riêng cho từng dịch vụ để một đối tác chậm không chiếm hết năng lực gọi các dependency khác.

Ví dụ chỉ minh họa cơ chế giới hạn tại dependency. Trong server thực tế, không nên submit vô hạn task từ một vòng lặp hoặc nhận vô hạn request; cần thêm admission control và giới hạn số công việc được giữ trong hệ thống.

## 7. Phân biệt giới hạn in-flight với rate limit

Semaphore giới hạn số thao tác đang diễn ra tại cùng một thời điểm. Nó không trực tiếp giới hạn số lần gọi trong một giây.

Ví dụ, nếu một API phản hồi trong 10 ms và semaphore có 10 permit, hệ thống có thể hoàn tất nhiều đợt 10 request trong một giây. Tổng số request mỗi giây có thể cao hơn nhiều so với 10.

| Cơ chế | Giới hạn | Ví dụ |
|---|---|---|
| `Semaphore` | Số thao tác đang in-flight | Tối đa 20 lời gọi đồng thời |
| Rate limiter | Số lần gọi trong một đơn vị thời gian | Tối đa 100 lần gọi mỗi giây |
| Connection pool | Số connection được cấp đồng thời | Tối đa 30 database connection |
| Admission control | Số request/task được nhận vào hệ thống | Tối đa 200 request đang hoạt động hoặc chờ |

Nếu đối tác quy định cả “không quá 20 request đồng thời” và “không quá 100 request mỗi giây”, cần hai cơ chế riêng: semaphore cho concurrency và rate limiter cho tốc độ. Một semaphore không thay thế được quota theo thời gian.

## 8. Giới hạn số task được nhận và backpressure

Semaphore đặt quanh lời gọi dependency chỉ giới hạn số task đang sử dụng dependency. Những task còn lại vẫn có thể tồn tại và chờ permit. Nếu lượng request đầu vào tăng liên tục, số virtual thread đang chờ cũng có thể tăng và tiêu thụ bộ nhớ.

Do đó, hệ thống cần thêm giới hạn ở điểm tiếp nhận công việc:

- Đặt giới hạn số request đang hoạt động ở server hoặc gateway.
- Dùng hàng đợi có dung lượng hữu hạn khi cần xếp hàng task.
- Từ chối sớm hoặc trả trạng thái quá tải khi hệ thống đã đạt giới hạn.
- Dùng timeout cho thời gian chờ queue và permit.
- Điều tiết tốc độ nhận request nếu upstream có thể gửi nhanh hơn khả năng xử lý.

Không nên dùng một hàng đợi không giới hạn để che giấu tình trạng dependency quá tải. Hàng đợi chỉ làm tăng thời gian chờ và bộ nhớ sử dụng; nó không làm tăng năng lực xử lý của hệ thống phía sau.

### Ví dụ giới hạn admission bằng semaphore

Một semaphore ở ranh giới tiếp nhận có thể giới hạn số request đang được ứng dụng giữ cùng lúc. `tryAcquire()` không chờ và cho phép từ chối ngay khi hết chỗ:

```java
import java.util.concurrent.Semaphore;

class RequestAdmission {
    private static final Semaphore REQUEST_SLOTS = new Semaphore(200);

    static boolean tryHandle(Runnable requestWork) {
        if (!REQUEST_SLOTS.tryAcquire()) {
            return false; // Caller có thể trả HTTP 503 hoặc 429 theo hợp đồng.
        }

        try {
            requestWork.run();
            return true;
        } finally {
            REQUEST_SLOTS.release();
        }
    }
}
```

Trong ví dụ, tối đa 200 request được nhận vào vùng xử lý. Permit được giữ đến khi phần xử lý request kết thúc. Với server bất đồng bộ, cần gắn thời điểm trả permit với callback hoàn tất thực sự của request, không trả ngay khi method chỉ mới đăng ký công việc nền.

Giới hạn admission và giới hạn dependency thường có giá trị khác nhau. Ví dụ ứng dụng có thể nhận tối đa 200 request, trong đó chỉ cho phép 25 request cùng gọi một API đối tác.

## 9. Connection pool là giới hạn tài nguyên chuyên biệt

Với database, connection pool thường là nơi kiểm soát số connection đồng thời. Cấu hình maximum pool size cần dựa trên năng lực database và tổng số ứng dụng cùng sử dụng database đó.

Nếu mỗi instance ứng dụng có pool tối đa 30 connection và hệ thống chạy 5 instance, tổng số connection có thể lên đến 150, chưa tính các service khác, tác vụ batch và kết nối quản trị. Cần tính tổng số kết nối trên toàn hệ thống trước khi chọn pool size.

Một semaphore cục bộ quanh truy vấn có thể hữu ích nếu cần giới hạn số truy vấn nặng thấp hơn số connection trong pool, nhưng nó không thay thế connection pool. Connection pool vẫn quản lý việc cấp phát, tái sử dụng và đóng connection; semaphore chỉ kiểm soát số tác vụ đi vào vùng nghiệp vụ được bảo vệ.

Tránh giữ connection trong lúc thực hiện công việc không cần database, chẳng hạn gọi API đối tác hoặc chờ người dùng. Hãy lấy connection ngay trước truy vấn, kết thúc transaction và trả connection sớm nhất có thể.

## 10. Giới hạn cục bộ và giới hạn toàn cụm

`Semaphore` trong ví dụ là đối tượng trong một JVM. Nếu service có nhiều instance, mỗi instance có semaphore riêng. Ví dụ 4 instance, mỗi instance cho phép 25 lời gọi đồng thời, có thể tạo tổng cộng 100 lời gọi đến dependency.

Vì vậy:

- Nếu giới hạn của dependency là giới hạn theo từng client instance, semaphore cục bộ có thể phù hợp.
- Nếu dependency có quota tổng cho toàn bộ service hoặc toàn bộ tenant, cần tính ngân sách permit trên tất cả instance.
- Có thể chia quota tổng thành ngân sách cố định cho từng instance, hoặc dùng cơ chế điều phối/quota tập trung nếu cần bảo đảm giới hạn toàn cụm khi scale động.
- Khi tăng số replica, phải tính lại tổng connection và số request in-flight có thể phát sinh.

Không nên tuyên bố một semaphore cục bộ bảo vệ được quota toàn hệ thống. Phạm vi hiệu lực của giới hạn phải khớp với phạm vi quota mà dependency áp dụng.

## 11. Chọn số permit như thế nào?

Không có một con số phù hợp cho mọi ứng dụng. Giá trị ban đầu nên dựa trên:

1. Giới hạn concurrency hoặc connection do dependency công bố.
2. Tổng số instance và các client khác đang sử dụng cùng dependency.
3. Thời gian phản hồi thực tế và biến động latency.
4. Throughput mục tiêu và mức tải đỉnh.
5. Phần dung lượng dự phòng để xử lý burst, retry hoặc tác vụ vận hành.

Định luật Little thường được dùng để ước tính số công việc trung bình đang in-flight:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số công việc trung bình đang ở trong hệ thống.
- `λ` là throughput trung bình, tính bằng số công việc mỗi giây.
- `W` là thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Ví dụ, nếu dependency xử lý trung bình 40 request mỗi giây và thời gian xử lý trung bình là 0,5 giây, số request in-flight trung bình theo mô hình ổn định là khoảng 20. Đây chỉ là điểm tham khảo; cần đo p95/p99 latency, burst, giới hạn thực tế của dependency và tải từ các client khác trước khi đặt permit.

Hãy theo dõi số permit đang dùng, số task chờ, thời gian chờ permit, số lần từ chối, timeout, lỗi dependency và latency. Thay đổi giới hạn dựa trên dữ liệu tải thực tế, không chỉ dựa vào số core CPU hoặc số virtual thread.

## 12. Fairness và permit theo trọng số

Mặc định, `Semaphore` không bảo đảm thứ tự FIFO giữa các task chờ permit. Nếu cần chính sách công bằng hơn, có thể tạo semaphore với chế độ fair:

```java
import java.util.concurrent.Semaphore;

class FairSemaphoreExample {
    private static final Semaphore FAIR_LIMIT = new Semaphore(10, true);
}
```

Fair semaphore ưu tiên các thread chờ lâu hơn khi cấp permit theo hàng đợi. Điều này có thể giảm nguy cơ một số task liên tục bị vượt qua, nhưng có thể làm giảm throughput trong một số workload. Chỉ bật fairness khi yêu cầu nghiệp vụ cần thứ tự chờ rõ ràng và đã đo tác động.

Một semaphore cũng có thể cấp nhiều permit cho một tác vụ bằng `acquire(n)` và `release(n)`. Cách này hữu ích khi mỗi tác vụ tiêu thụ lượng tài nguyên khác nhau, nhưng cần bảo đảm số permit được trả đúng bằng số đã lấy và luôn trả trong `finally`. Với giới hạn connection thông thường, một thao tác thường chỉ cần một permit.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ virtual-thread-per-task executor tự giới hạn concurrency | Có thể tạo nhiều lời gọi cùng lúc đến dependency | Đặt giới hạn riêng bằng semaphore hoặc pool tài nguyên |
| Lấy permit nhưng quên `release()` khi có exception | Permit bị giữ mãi, năng lực giảm dần | Đặt thao tác trong `try/finally` |
| Gọi `release()` dù chưa lấy được permit | Số permit tăng ngoài dự kiến | Chỉ release khi việc acquire thành công |
| Chờ `acquire()` vô hạn trong request | Request có thể giữ task chờ quá lâu | Dùng `tryAcquire(timeout, unit)` và deadline |
| Giữ permit trong lúc làm việc không liên quan | Giảm throughput của dependency | Thu hẹp vùng được bảo vệ |
| Dùng semaphore thay connection pool | Không quản lý được vòng đời connection | Dùng connection pool cho connection; semaphore chỉ cho giới hạn nghiệp vụ bổ sung |
| Nhầm concurrency limit với rate limit | Vẫn có thể vượt quota request/giây | Kết hợp rate limiter khi dependency có quota theo thời gian |
| Dùng semaphore cục bộ cho quota toàn cụm | Tổng tải từ nhiều instance vượt giới hạn | Phân bổ quota toàn cụm hoặc dùng điều phối tập trung |
| Chỉ giới hạn dependency mà không giới hạn admission | Nhiều task vẫn xếp hàng và tiêu thụ bộ nhớ | Thêm giới hạn request, hàng đợi hữu hạn và backpressure |

## 14. Checklist thiết kế concurrency limit

Trước khi đưa giới hạn vào production, hãy xác nhận:

1. Đã xác định đúng tài nguyên cần bảo vệ và phạm vi quota của nó chưa?
2. Giới hạn đang kiểm soát số task in-flight, số request được nhận hay tốc độ request?
3. Semaphore hoặc connection pool có số permit/connection phù hợp với tổng số instance không?
4. Mọi đường thoát khỏi vùng sử dụng tài nguyên đều trả permit đúng một lần chưa?
5. Có timeout khi chờ permit và timeout cho thao tác I/O không?
6. Có giới hạn số task đang chờ hoặc cơ chế từ chối sớm không?
7. Có metric cho permit đang dùng, thời gian chờ, số lần từ chối và dependency latency không?
8. Khi scale số instance, tổng ngân sách concurrency có còn nằm trong quota không?
9. Giới hạn có được kiểm chứng bằng tải thực tế và có đủ headroom cho burst không?

## Kết luận

Số virtual thread hoặc số task được tạo không nên quyết định trực tiếp số thao tác được phép sử dụng một dependency. Dùng `Semaphore` để giới hạn vùng in-flight, connection pool để quản lý connection, rate limiter để kiểm soát số lần gọi theo thời gian và admission control để giới hạn công việc được nhận. Kết hợp timeout, backpressure và metric để task không chờ vô hạn. Cuối cùng, phải xác định giới hạn áp dụng trong một JVM hay toàn cụm; một semaphore cục bộ không thể tự bảo đảm quota của toàn bộ hệ thống.
