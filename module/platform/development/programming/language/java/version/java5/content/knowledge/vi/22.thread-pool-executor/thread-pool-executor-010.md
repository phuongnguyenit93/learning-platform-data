# Giới hạn tài nguyên và kiểm soát tốc độ nhận việc

## 1. Vì sao có bộ luồng rồi vẫn có thể quá tải?

Giả sử ứng dụng có bốn luồng làm báo cáo nhưng mỗi yêu cầu được nhận đều giữ một vùng dữ liệu lớn. Khi nguồn gửi nhanh hơn nguồn xử lý, hàng nghìn tác vụ có thể chờ dù chỉ bốn tác vụ đang chạy.

Ngược lại, nếu tác vụ hoàn tất cực nhanh, bốn luồng có thể phát ra rất nhiều yêu cầu tới dịch vụ ngoài trong một giây. Giới hạn bốn luồng chưa bảo đảm tuân thủ hạn mức “100 yêu cầu/giây”.

Vì vậy cần tách:

- **Giới hạn đồng thời:** bao nhiêu công việc được thực hiện cùng lúc?
- **Giới hạn phần việc chờ:** giữ tối đa bao nhiêu công việc chưa bắt đầu?
- **Giới hạn tốc độ:** trong thời gian trôi qua, được cấp bao nhiêu lượt tiếp nhận?
- **Giới hạn tài nguyên phụ thuộc:** bao nhiêu kết nối, bao nhiêu byte, thời hạn nào?

ThreadPoolExecutor hỗ trợ một phần của bài toán. Kiểm soát tiếp nhận phải gắn với các tài nguyên mà công việc thực sự sử dụng.

Các ví dụ dùng Java 17+ và các cơ chế vẫn áp dụng trên Java hiện đại.

## 2. Đơn vị của từng giới hạn phải rõ ràng

| Cơ chế | Đơn vị điển hình | Không tự bảo đảm |
| --- | --- | --- |
| Số luồng của bộ thực thi | Luồng làm việc | Số yêu cầu/giây |
| Dung lượng hàng đợi | Phần tử công việc chờ | Tổng số byte đang giữ |
| Semaphore | Số quyền truy cập đồng thời | Tốc độ theo giây |
| Bộ giới hạn tốc độ | Lượt theo thời gian, có thể cho phép đợt ngắn | Số công việc còn chạy lâu |
| Timeout/deadline | Thời gian chờ/xử lý | Tác vụ đã thực sự dừng |
| Ngân sách dữ liệu | Byte hoặc kích thước đầu vào | Độ phức tạp xử lý của mọi tác vụ |

Một hạn mức cần ghi rõ nó áp dụng cho lần thử gửi, công việc đã nhận, lần bắt đầu gọi dịch vụ ngoài hay kết quả hoàn tất. Các con số sẽ khác nhau nếu có từ chối, thử lại hoặc tác vụ tạo nhiều yêu cầu con.

Ví dụ, giới hạn nhận 100 báo cáo/giây không bảo đảm chỉ có 100 truy vấn cơ sở dữ liệu/giây nếu mỗi báo cáo tạo 20 truy vấn.

## 3. Giới hạn luồng và hàng đợi cùng nhau

Một cấu hình hữu hạn có thể là:

```text
core = 2
max = 2
queue capacity = 2
rejection = AbortPolicy
```

Ở cấu hình này, tối đa hai tác vụ được các luồng của bộ thực thi xử lý và tối đa hai phần tử ở hàng đợi. Khi cả hai phần đều đầy, tác vụ mới bị từ chối bằng ngoại lệ.

Giới hạn luồng và hàng đợi giúp biểu đạt ngân sách công việc trong bộ thực thi. Tuy nhiên:

- Các luồng gửi bên ngoài vẫn có thể giữ yêu cầu chưa gửi.
- Mỗi tác vụ có thể tạo công việc con hoặc giữ nhiều tài nguyên.
- Một hàng đợi khác ở tầng phía trước có thể tiếp tục tích tải.
- Chính sách như CallerRunsPolicy có thể cho tác vụ chạy thêm trên luồng gửi.

Do đó phải đọc cả chính sách từ chối và toàn bộ đường đi của yêu cầu, không chỉ constructor. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

### Thí nghiệm ngân sách đồng thời và chờ

Tệp **ResourceBudgetDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ResourceBudgetDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(2),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch running = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Integer>> accepted = new ArrayList<>();

        Callable<Integer> work = () -> {
            running.countDown();
            release.await();
            return 1;
        };

        try {
            accepted.add(pool.submit(work));
            accepted.add(pool.submit(work));
            if (!running.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            accepted.add(pool.submit(work));
            accepted.add(pool.submit(work));

            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("accepted=" + accepted.size());

            try {
                pool.submit(work);
            } catch (RejectedExecutionException ex) {
                System.out.println("fifth=notAccepted");
            }

            release.countDown();
            int results = 0;
            for (Future<Integer> future : accepted) {
                results += future.get();
            }
            System.out.println("completedResults=" + results);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 ResourceBudgetDemo.java
java ResourceBudgetDemo
```

Stdout khi hoàn tất bình thường:

```text
poolSize=2
queued=2
accepted=4
fifth=notAccepted
completedResults=4
```

Chốt giữ hai tác vụ đầu đang chạy nên hai tác vụ tiếp theo chắc chắn còn chờ lúc kiểm tra. Đây là kiểm chứng dung lượng, không phải đo thông lượng.

Nếu mở chốt sớm và tác vụ rất nhanh, cùng cấu hình này có thể xử lý liên tục nhiều công việc mỗi giây. Muốn hạn chế tốc độ cần một cơ chế theo thời gian riêng.

## 4. Tốc độ nhận cao hơn tốc độ xử lý tạo phần việc tồn đọng

Ví dụ giả định hệ thống nhận 300 công việc/giây nhưng chỉ xử lý bền vững 200 công việc/giây. Khi điều kiện đó kéo dài, phần việc chưa xử lý có xu hướng tăng khoảng 100 công việc mỗi giây.

Một hàng đợi lớn có thể hấp thụ đợt tải ngắn, nhưng không tạo thêm khả năng xử lý bền vững. Nó đổi thời điểm từ chối thành thời gian chờ và bộ nhớ bị giữ.

Cần kiểm soát cả tuổi của công việc. Một kết quả chỉ có giá trị trong hai giây có thể đã vô ích sau mười giây ở hàng đợi, dù cuối cùng tác vụ vẫn chạy đúng mã.

Không chọn queue capacity chỉ vì “máy còn RAM”. Phải xét thời gian chờ chấp nhận được, kích thước tác vụ, tốc độ xử lý và mức biến động.

Nếu đầu vào rất lớn, nên giới hạn kích thước hoặc giữ tham chiếu tới dữ liệu đã được lưu phù hợp thay vì giữ nhiều bản sao trong mỗi tác vụ chờ. Cách lưu đó vẫn cần ngân sách và vòng đời rõ ràng.

## 5. Giới hạn tốc độ bằng mô hình thùng token

Mô hình thùng token (token bucket) biểu diễn hai ý:

- Token được bổ sung theo một tốc độ định trước.
- Thùng có dung lượng tối đa, cho phép một đợt nhận nhanh ngắn khi đã tích đủ token.

Ví dụ tốc độ hai token/giây và dung lượng hai:

```text
Ban đầu có 2 token
    -> nhận 2 lượt ngay
    -> lượt tiếp theo bị từ chối nếu chưa có thời gian bổ sung

Sau 0,5 giây
    -> có thêm 1 token
    -> nhận thêm 1 lượt

Sau thời gian nhàn dài
    -> vẫn chỉ giữ tối đa 2 token
```

Đây không phải cam kết “trong mọi cửa sổ một giây đều không quá hai lượt”. Đợt được phép và token bổ sung có thể tạo phân bố khác theo từng cửa sổ thời gian. Phải chọn thuật toán phù hợp với ý nghĩa hạn mức thực tế.

Mô hình token bucket được mô tả cho điều tiết lưu lượng trong [RFC 3290, phần token bucket](https://datatracker.ietf.org/doc/html/rfc3290#appendix-A.2). Ví dụ dưới đây áp dụng ý tưởng cho lượt tiếp nhận công việc trong một JVM, không triển khai giao thức mạng của RFC.

## 6. Ví dụ token bucket có đồng hồ giả để kiểm chứng

Tệp **RateGateDemo.java**:

```java
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class RateGateDemo {
    static final class TokenBucket {
        private final int capacity;
        private final double tokensPerSecond;
        private final LongSupplier nanoClock;
        private double tokens;
        private long lastNanos;

        TokenBucket(int capacity, double tokensPerSecond, LongSupplier nanoClock) {
            if (capacity <= 0
                    || !Double.isFinite(tokensPerSecond)
                    || tokensPerSecond <= 0) {
                throw new IllegalArgumentException("Invalid rate configuration");
            }
            this.capacity = capacity;
            this.tokensPerSecond = tokensPerSecond;
            this.nanoClock = Objects.requireNonNull(nanoClock);
            this.tokens = capacity;
            this.lastNanos = nanoClock.getAsLong();
        }

        synchronized boolean tryAcquire() {
            long now = nanoClock.getAsLong();
            long elapsed = now - lastNanos;

            if (elapsed > 0) {
                double refill = elapsed / 1_000_000_000.0 * tokensPerSecond;
                tokens = Math.min(capacity, tokens + refill);
                lastNanos = now;
            }

            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }

    public static void main(String[] args) {
        AtomicLong clock = new AtomicLong();
        TokenBucket gate = new TokenBucket(2, 2.0, clock::get);

        System.out.println("initial1=" + gate.tryAcquire());
        System.out.println("initial2=" + gate.tryAcquire());
        System.out.println("initial3=" + gate.tryAcquire());

        clock.addAndGet(TimeUnit.MILLISECONDS.toNanos(500));
        System.out.println("afterHalfSecond1=" + gate.tryAcquire());
        System.out.println("afterHalfSecond2=" + gate.tryAcquire());

        clock.addAndGet(TimeUnit.SECONDS.toNanos(10));
        System.out.println("afterIdle1=" + gate.tryAcquire());
        System.out.println("afterIdle2=" + gate.tryAcquire());
        System.out.println("afterIdle3=" + gate.tryAcquire());
    }
}
```

Chạy:

```shell
javac --release 17 RateGateDemo.java
java RateGateDemo
```

Stdout:

```text
initial1=true
initial2=true
initial3=false
afterHalfSecond1=true
afterHalfSecond2=false
afterIdle1=true
afterIdle2=true
afterIdle3=false
```

Đồng hồ giả chỉ tiến khi chương trình chủ động tăng giá trị, nên kiểm chứng không phụ thuộc độ chính xác của sleep. Một token cho phép một lượt, không được hoàn trả khi công việc kết thúc; token mới xuất hiện do thời gian trôi qua.

Khi dùng nguồn thời gian thực để đo khoảng trôi qua trong cùng JVM, có thể truyền `System::nanoTime`. Không dùng giá trị này như thời gian lịch hoặc so sánh giữa các JVM. Đồng hồ của ví dụ phải có hợp đồng đơn điệu; các khoảng đo cũng phải nằm trong phạm vi hiệu lực của phép trừ thời gian. [Tài liệu System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime())

Lớp minh họa dùng synchronized để việc bổ sung/tiêu token là một thao tác được bảo vệ khi dùng chung. Nó dùng số thực để diễn tả mô hình, không có hàng chờ công bằng hay lưu trạng thái bền vững, và không phải bộ giới hạn phân tán. Nếu mỗi instance ứng dụng có một thùng riêng, tổng hạn mức của nhiều instance sẽ khác hạn mức một JVM.

## 7. Ghép cổng tốc độ với bộ thực thi

Một đường tiếp nhận có thể là:

```text
Yêu cầu
    -> kiểm tra đầu vào/kích thước/thời hạn
    -> cổng tốc độ
    -> ThreadPoolExecutor hữu hạn
    -> tác vụ
    -> tài nguyên phụ thuộc
```

Cần hai kết quả từ chối riêng:

- Không có lượt theo thời gian: quá hạn mức tốc độ đã định.
- Có lượt nhưng bộ thực thi không còn khả năng nhận: bão hòa hoặc đã đóng tiếp nhận.

Không có bảo đảm nguyên tử giữa một token bucket riêng và lời gọi submit. Bộ thực thi có thể từ chối sau khi token đã được cấp.

Vì vậy phải định nghĩa token đo điều gì. Nếu token giới hạn **lượt được phép thử tiếp nhận**, mất token dù submit bị từ chối là chính sách nhất quán. Nếu token phải chỉ đếm **công việc thực sự đã nhận**, cần thiết kế giao thức phối hợp/hoàn trả và kiểm chứng cạnh tranh; không tự thêm một release tùy tiện vào token bucket.

Đặt bộ giới hạn tốc độ ở đầu đường tiếp nhận cũng không bảo đảm tốc độ gọi tài nguyên ngoài: công việc tích trong hàng đợi có thể bắt đầu dồn dập sau đó, một tác vụ có thể phát nhiều lời gọi hoặc thử lại. Khi tài nguyên ngoài có hạn mức riêng, cần kiểm soát ở đúng ranh giới lời gọi đó.

## 8. Semaphore giới hạn tài nguyên dùng đồng thời

Ví dụ ứng dụng có 16 luồng nhưng chỉ muốn cho tối đa 8 thao tác nặng dùng một tài nguyên ngoài cùng lúc. Semaphore có thể biểu diễn 8 quyền truy cập:

1. Lấy một permit trước vùng sử dụng tài nguyên.
2. Thực hiện thao tác.
3. Trả permit trong finally sau khi thực sự rời vùng sử dụng.

Nếu chỉ muốn chờ có giới hạn, dùng thao tác lấy permit có timeout hoặc thử lấy ngay rồi phản hồi không có khả năng xử lý. Không trả permit nếu lần lấy chưa thành công. [Tài liệu Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

Điểm khác token bucket:

- Permit đồng thời được trả khi vùng sử dụng kết thúc.
- Token tốc độ được bổ sung theo thời gian.

Semaphore không tự giới hạn số luồng đang **chờ** permit. Nếu hàng nghìn yêu cầu đều được nhận rồi bị giữ chờ quyền truy cập, áp lực chỉ chuyển sang nơi khác. Phải giới hạn cả nơi giữ công việc chờ.

Cũng không trả permit ngay khi Future bị hủy nếu tác vụ vẫn còn sử dụng tài nguyên. Hủy Future và mã tác vụ thực sự dừng là hai mốc khác nhau. Quyền tài nguyên phải gắn với phạm vi sử dụng thực tế hoặc một giao thức giải phóng được kiểm chứng, tránh cấp lại quyền trong lúc công việc cũ vẫn chạy.

## 9. Điều tiết nguồn gửi và phản hồi quá tải

Khi không nhận được công việc, có thể:

- Từ chối sớm với trạng thái bận/hạn mức rõ ràng.
- Cho nguồn gửi chờ có giới hạn nếu luồng đó được phép chờ.
- Giảm tốc độ phát công việc ở nguồn.
- Gộp các cập nhật có thể thay thế nhau theo hợp đồng nghiệp vụ.
- Ghi nhận vào hệ thống công việc bền vững nếu đã có yêu cầu và ngân sách riêng.

CallerRunsPolicy có thể làm nguồn gửi chậm vì chính nó phải chạy tác vụ khi bão hòa. Nhưng nó cũng làm công việc chạy trên luồng gửi, có thể ảnh hưởng độ trễ, khóa và ngữ cảnh của luồng đó. Sau shutdown, chính sách này bỏ tác vụ; không coi nó là bảo đảm tiếp nhận.

Không phản hồi “đã nhận” khi hệ thống đã bỏ tác vụ. Nếu công việc không được nhận, thử lại phải có giới hạn và có thời gian chờ phù hợp; vòng retry tức thì có thể làm quá tải nặng hơn.

Nếu công việc đã tạo tác dụng phụ, thử lại cần định danh và tính an toàn khi chạy lặp. Lỗi thời gian chờ không tự chứng minh thao tác ở hệ thống ngoài chưa xảy ra.

## 10. Ngân sách thời gian phải đi qua các tầng

Một yêu cầu có deadline tổng cần tính:

```text
thời gian kiểm tra/tiếp nhận
+ chờ hàng đợi
+ chờ permit/kết nối
+ thực thi
+ thử lại nếu có
+ tổng hợp kết quả
```

Cấp riêng năm giây ở từng tầng không có nghĩa tổng yêu cầu nằm trong năm giây. Hãy xác định thời gian còn lại từ deadline và ngừng nhận công việc đã không còn khả năng tạo kết quả hữu ích.

Timeout của Future.get chỉ giới hạn bên gọi chờ. Nó không tự hủy công việc; hủy cũng cần tác vụ hợp tác với ngắt hoặc cơ chế dừng phù hợp của tài nguyên chặn.

Đừng giải phóng sớm tài nguyên dùng chung chỉ vì người gọi không còn chờ. Cần quyền sở hữu rõ cho tài nguyên và phần việc còn chạy.

## 11. Đo đạc để tìm đúng giới hạn

| Số đo | Điều nó giúp phân biệt |
| --- | --- |
| Tốc độ yêu cầu đến | Nguồn tải thực tế |
| Số từ chối theo cổng tốc độ | Hết ngân sách lượt theo thời gian |
| Số từ chối của bộ thực thi | Bão hòa hoặc vòng đời đã đóng |
| Số việc chờ và tuổi công việc chờ | Áp lực tồn đọng và khả năng đáp ứng deadline |
| Thời gian chạy và chờ tài nguyên | CPU, I/O hoặc giới hạn phụ thuộc |
| Số thành công/lỗi/hủy | Kết quả thực tế của công việc đã nhận |
| Bộ nhớ và kích thước đầu vào | Chi phí tài nguyên của công việc |

Số luồng hoạt động cao nhưng CPU thấp có thể do chờ I/O hoặc khóa. Tăng luồng chỉ hữu ích nếu tài nguyên phụ thuộc còn khả năng tiếp nhận. Hàng đợi dài không tự có nghĩa phải tăng dung lượng; có thể cần giảm tốc độ nhận hoặc làm tác vụ nhanh hơn.

Số đo riêng lẻ chỉ là các quan sát, không phải một ảnh chụp nguyên tử chung. Dùng xu hướng và thử nghiệm tải phù hợp; không điều khiển tiếp nhận bằng phép kiểm tra queue size rồi hy vọng không có cạnh tranh.

## 12. Tự thiết kế một ngân sách có đơn vị

Một dịch vụ tạo báo cáo có:

- Hai luồng xử lý.
- Hàng đợi tối đa hai tác vụ.
- Cổng nhận trung bình hai lượt/giây với đợt ngắn tối đa hai lượt.
- Tài nguyên ngoài cho phép tối đa một thao tác nặng cùng lúc.

Hãy giải thích:

1. Có thể có bao nhiêu tác vụ trong bộ thực thi ở trạng thái chạy/chờ?
2. Hai lượt/giây có nghĩa chỉ có hai tác vụ còn chạy không?
3. Nếu tác vụ mất mười giây, cổng tốc độ có đủ ngăn tồn đọng không?
4. Khi hàng đợi đầy sau lúc đã cấp token, phản hồi nào là đúng?
5. Nếu Future bị hủy nhưng tác vụ chưa rời tài nguyên ngoài, có được cấp lại permit không?
6. Nếu chạy ba instance ứng dụng, hạn mức có còn là hai lượt/giây cho toàn hệ thống không?

Một cấu hình tốt ghi rõ **đơn vị, phạm vi, điểm áp dụng và cách phản hồi** của mỗi giới hạn. Khi đó, số luồng, hàng đợi và tốc độ nhận việc phối hợp thành ngân sách tài nguyên có thể kiểm chứng.
