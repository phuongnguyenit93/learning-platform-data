# Lựa chọn kích thước bộ luồng theo đặc tính tải

## 1. Chọn số luồng là chọn mức cạnh tranh tài nguyên

Kích thước bộ luồng không phải một con số có thể suy ra chỉ từ tên ứng dụng. Nó quyết định bao nhiêu công việc có thể chiếm luồng đồng thời, từ đó ảnh hưởng CPU, bộ nhớ, kết nối và lượng yêu cầu dồn vào các dịch vụ phía sau.

Mục tiêu cần xác định trước: đạt thông lượng mong muốn, giữ độ trễ trong giới hạn và không làm cạn tài nguyên khi tải tăng. Nhiều luồng hơn có thể giúp che thời gian chờ I/O, nhưng cũng có thể tăng chuyển ngữ cảnh, tranh chấp khóa hoặc làm một cơ sở dữ liệu đang chậm càng quá tải.

Bài tập trung `ThreadPoolExecutor` với luồng nền tảng (platform thread), cơ chế vẫn áp dụng trong Java hiện nay. Các con số minh họa là giả định học tập, không phải cấu hình được khuyến nghị chung cho mọi máy.

## 2. Hiểu công việc đang chiếm luồng để làm gì

Một tác vụ có thể chia thành các phần:

```text
thời gian chờ trong queue
    → thời gian được chạy trên CPU
    → thời gian chờ I/O/khóa/tài nguyên
    → thêm CPU và chờ nếu có
    → hoàn thành
```

Ba đại lượng cần phân biệt:

- **Thời gian CPU:** thời gian thực sự dùng bộ xử lý để tính toán.
- **Thời gian chiếm luồng:** từ lúc bắt đầu thực thi đến khi tác vụ xong, gồm cả lúc luồng chờ.
- **Độ trễ đầu-cuối:** còn bao gồm thời gian xếp hàng và các bước trước/sau executor.

| Đặc tính tải | Điểm giới hạn thường cần xem trước | Vì sao thêm luồng có thể không giúp |
|---|---|---|
| Chủ yếu tính toán CPU | Năng lực CPU hiệu dụng | Không tạo thêm lõi; tăng cạnh tranh và chi phí lập lịch |
| Chờ I/O nhiều, công việc độc lập | Khả năng phục vụ của hệ thống I/O và số kết nối | Dồn quá nhiều yêu cầu vào cùng điểm nghẽn |
| Chờ khóa nhiều | Vùng mã được khóa và mức tranh chấp | Nhiều luồng chỉ xếp hàng trước cùng khóa |
| Pha trộn CPU và I/O | Cả năng lực tính toán lẫn tài nguyên phụ thuộc | Một kích thước chung khó phù hợp mọi pha |
| Tác vụ có phụ thuộc lồng nhau | Số luồng còn có thể chạy phần phụ thuộc | Luồng chờ tác vụ con có thể giữ hết nhóm |

Đừng phân loại bằng số dòng mã. Một dòng gọi HTTP có thể giữ luồng lâu hơn hàng nghìn phép tính; một tác vụ “I/O” có thể có thêm pha giải mã hoặc nén rất tốn CPU.

## 3. Với tải CPU: bắt đầu từ năng lực CPU khả dụng, rồi đo

Đối với các công việc độc lập chủ yếu tính toán, mức song song quanh số bộ xử lý JVM có thể sử dụng là một điểm xuất phát để thử nghiệm. Nếu phải chừa năng lực cho luồng xử lý yêu cầu, GC, runtime hoặc các công việc khác, cần ngân sách CPU riêng cho nhóm này.

`Runtime.getRuntime().availableProcessors()` trả số bộ xử lý JVM được cung cấp, có thể thay đổi theo môi trường. Đây là dữ liệu cấu hình ban đầu, không phải bộ tối ưu tự biết giới hạn độ trễ, phần CPU thuộc ứng dụng hay mọi điều kiện triển khai. [Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()).

Ví dụ giả định JVM có 8 bộ xử lý khả dụng, và nhóm chỉ được đặt mục tiêu sử dụng khoảng 6 lõi hiệu dụng để dành tài nguyên cho phần còn lại. Có thể thử các kích thước quanh mức đó với tải đại diện, rồi so sánh thông lượng, p95/p99, CPU và thời gian xếp hàng.

Không kết luận “8 CPU thì đúng 8 luồng trong mọi trường hợp”. Một tác vụ có thể gọi thư viện tự tạo công việc song song; nhiều nhóm cùng hoạt động cũng chia sẻ CPU. Tính tổng cạnh tranh ở cấp tiến trình, không tối ưu từng executor như thể nó là chương trình duy nhất.

## 4. Với tải chờ nhiều: dùng tỉ lệ chạy/chờ làm giả thuyết

Một mô hình ước lượng đơn giản giúp đặt câu hỏi trước khi đo:

```text
C = thời gian CPU trung bình mỗi tác vụ
W = thời gian chờ trong lúc tác vụ chiếm luồng
P = số bộ xử lý được dùng làm cơ sở
U = phần năng lực CPU mục tiêu dành cho nhóm, trong khoảng 0 đến 1

N ≈ P × U × (1 + W/C)
```

Có thể hiểu bằng cách lấy tỉ lệ thời gian một luồng thực sự dùng CPU là `C / (C + W)`. Muốn cung cấp khoảng `P × U` luồng đang tính toán hiệu dụng, số luồng chiếm chỗ ước lượng là `P × U` chia cho tỉ lệ đó. Đây là phép suy luận theo mô hình đơn giản, không phải bảo đảm của ThreadPoolExecutor.

Ví dụ giả định `P = 8`, `U = 0,75`, `C = 10 ms`, `W = 30 ms`:

```text
N ≈ 8 × 0,75 × (1 + 30/10) = 24 luồng
```

**24 là một ứng viên từ mô hình, chưa phải quyết định triển khai.** Phải kiểm tra các giả định:

- C và W được đo trên công việc đại diện, không lấy thời gian nằm trong queue của chính executor làm W để rồi tăng luồng theo một vòng tự khuếch đại.
- Công việc tương đối độc lập; thời gian chờ không chủ yếu do cùng một khóa đang tranh chấp.
- Hệ thống I/O còn đủ khả năng phục vụ mức đồng thời được đề xuất.
- Bộ nhớ, kết nối và các nhóm khác còn đủ ngân sách.
- Tỉ lệ trung bình không che một đuôi độ trễ hoặc đỉnh tải lớn.

Nếu tăng đồng thời làm dịch vụ phía sau chậm thêm, W không còn là hằng số như giả định. Không tiếp tục thay W lớn hơn vào công thức rồi tăng N vô hạn. [ThreadPoolExecutor: quan hệ hàng đợi, kích thước nhóm và tác vụ bị chặn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 5. Giới hạn tài nguyên phía sau có thể nhỏ hơn ứng viên số luồng

Giả sử mô hình gợi ý 24 luồng nhưng dịch vụ cơ sở dữ liệu chỉ cho nhóm công việc này dùng tối đa 12 kết nối đồng thời. Nếu mỗi tác vụ cần giữ một kết nối trong gần như toàn bộ thời gian nó chiếm luồng, cho 24 tác vụ cùng chạy có thể khiến một nửa chỉ đứng chờ kết nối.

Không có đủ tài nguyên phía sau thì thêm luồng không làm có thêm tài nguyên đó. Phải quyết định giới hạn tại đúng ranh giới:

- Giới hạn số luồng của nhóm nếu gần như mọi tác vụ đều chiếm cùng một loại tài nguyên trong cả quá trình.
- Tách pha xử lý hoặc nhóm công việc khi các phần cần tài nguyên khác nhau.
- Dùng cơ chế cấp phép hữu hạn như Semaphore khi chỉ một đoạn trong tác vụ được phép truy cập tài nguyên giới hạn.

Semaphore là công cụ giới hạn số bên truy cập một tài nguyên; nó không tự giới hạn tổng số công việc đã được tạo hoặc đang giữ bộ nhớ. Nếu cho phép sinh vô hạn tác vụ chỉ để chúng chờ giấy phép, vấn đề tích tải vẫn còn. [Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html).

Trong hệ thống nhiều bản sao, ngân sách phía sau phải tính tổng. Mười tiến trình mỗi tiến trình cho phép 12 truy cập đồng thời có thể tạo tới 120 truy cập, chưa tính các ứng dụng khác. Một kích thước an toàn trên máy thử riêng không tự là an toàn khi mở rộng số bản sao.

## 6. Số luồng phải được chọn cùng hàng đợi và chính sách quá tải

Với ThreadPoolExecutor, sau khi đạt mức lõi, executor thường thử xếp hàng trước; chỉ khi queue không nhận được mới thử tăng tới mức tối đa.

```text
dưới core → thử thêm luồng
đạt core → thử queue
queue không nhận → thử tăng đến max
không nhận được nữa → chính sách từ chối
```

Do đó, `core = 4`, `max = 24` với queue không giới hạn thực tế không có nghĩa tải tăng sẽ làm nhóm nhanh chóng dùng 24 luồng. Công việc có thể tiếp tục tích trong queue quanh bốn luồng thực thi.

Với queue hữu hạn, dung lượng quyết định bao nhiêu việc phải chờ trước khi nhóm xét tăng. Queue rất lớn có thể làm tăng độ trễ trước khi chạm mức tối đa; queue rất nhỏ có thể làm tăng số luồng hoặc từ chối sớm hơn. SynchronousQueue không có bộ đệm, nên sẽ tạo áp lực chuyển giao/tăng luồng theo cơ chế khác.

Cần chọn một chính sách khi đã đầy:

- Báo không nhận được việc để nơi gọi trả trạng thái quá tải hoặc thử lại có giới hạn.
- Đưa phản hồi giảm tốc phù hợp về phía tạo việc.
- Chỉ bỏ việc khi hợp đồng thật sự cho phép, đồng thời bảo đảm Future/bên chờ không bị bỏ quên.

Không dùng hàng đợi vô hạn hoặc nhóm luồng gần như vô hạn để né quyết định quá tải. Năng lực phục vụ vẫn hữu hạn; chỉ vị trí tích áp lực thay đổi.

## 7. Ước lượng lượng việc đang chiếm tài nguyên

Một cách kiểm tra chéo: với một dòng việc ổn định, nếu trung bình có 100 tác vụ mỗi giây và mỗi tác vụ chiếm một luồng khoảng 80 mili giây, lượng công việc đang chiếm luồng trung bình có thể quanh:

```text
100 tác vụ/giây × 0,08 giây/tác vụ = 8 tác vụ đang chiếm luồng
```

Đây là một ước lượng theo tốc độ và thời gian chiếm tài nguyên, không đồng nghĩa chọn đúng 8 luồng là đủ giữ p99 khi có đợt tăng tải. Phải xét phân bố thời gian, biến động tốc độ đến và khoảng dự phòng.

Tương tự, cho thêm chỗ queue không tăng tốc độ xử lý bền vững. Nếu công việc đến nhanh hơn khả năng hoàn thành trong thời gian dài, queue sẽ tích. Nếu cần giữ hạn chót đầu-cuối, phải tính cả khoảng nằm trong queue, không chỉ thời gian task.run.

Một tác vụ đã hết giá trị lúc bắt đầu chạy vẫn có thể tốn CPU/kết nối. Chính sách thời hạn và hủy phải gắn với trạng thái công việc thực; một get timeout của người gọi không tự dừng phần đang xử lý.

## 8. Chương trình kiểm chứng giới hạn đồng thời có chủ đích

Ví dụ dưới đây không tự tìm “kích thước nhanh nhất”. Nó kiểm chứng một cấu hình có chủ đích: chỉ hai tác vụ được chiếm luồng cùng lúc, còn hai tác vụ chờ trong queue. Latch mô phỏng một pha chiếm luồng mà chưa thể hoàn tất; đó không phải phép đo hiệu năng I/O thực.

Lưu thành `PoolConcurrencyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(4),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch firstWaveStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= 4; i++) {
                final int value = i;
                futures.add(pool.submit(() -> {
                    int now = active.incrementAndGet();
                    peak.accumulateAndGet(now, Math::max);
                    firstWaveStarted.countDown();
                    try {
                        release.await();
                        return value;
                    } finally {
                        active.decrementAndGet();
                    }
                }));
            }

            if (!firstWaveStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Two tasks did not start");
            }
            System.out.println("active before release: " + active.get());
            System.out.println("queued before release: " + pool.getQueue().size());
            release.countDown();

            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get(10, TimeUnit.SECONDS);
            }
            System.out.println("sum: " + sum);
            System.out.println("peak active: " + peak.get());
            System.out.println("active after results: " + active.get());
        } finally {
            release.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    for (Runnable task : pool.shutdownNow()) {
                        if (task instanceof Future<?> future) {
                            future.cancel(false);
                        }
                    }
                    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Executor did not terminate");
                    }
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 PoolConcurrencyDemo.java
java PoolConcurrencyDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
active before release: 2
queued before release: 2
sum: 10
peak active: 2
active after results: 0
```

Hai luồng không tăng thêm vì core và max đều bằng 2. Hai công việc đầu giữ luồng ở latch; hai công việc còn lại vẫn trong queue khi main đọc. Mở latch cho chúng hoàn thành, lấy bốn kết quả và quan sát mức hoạt động cực đại.

Kết quả chứng minh giới hạn đồng thời của cấu hình nhỏ trong thí nghiệm. Nó không chứng minh hai luồng là tối ưu cho CPU hoặc mạng của máy đang chạy. Một chương trình sleep/latch không mô phỏng đầy đủ băng thông, bộ nhớ đệm CPU, khóa hoặc năng lực cơ sở dữ liệu.

## 9. Đo gì trước khi đổi kích thước?

| Nhóm đo | Câu hỏi nó giúp trả lời |
|---|---|
| Thông lượng hoàn thành | Có thực sự xử lý được nhiều công việc hơn không? |
| Độ trễ p50/p95/p99 | Ai đang phải chờ lâu, đuôi độ trễ có xấu đi không? |
| Thời gian chờ queue | Nhóm thiếu khả năng phục vụ hay queue quá lớn? |
| Thời gian thực thi và CPU mỗi tác vụ | Đang tính toán hay đang chờ? |
| CPU, bộ nhớ, GC, số luồng | Tăng song song có làm cạn tài nguyên tiến trình không? |
| Kết nối, lỗi/thời hạn phía sau | Executor có đang dồn quá mức vào phụ thuộc không? |
| Từ chối, hủy, timeout, thử lại | Hệ thống phản hồi quá tải ra sao, có tự tăng tải qua retry không? |

Thời lượng task.run là thời gian trôi trên đồng hồ, không tự là CPU time. Nếu dùng beforeExecute/afterExecute để đo thời lượng, phải phân biệt nó với thời gian xếp hàng và lấy lỗi Future đúng cách. Chỉ biết “tác vụ mất 500 ms” chưa đủ tính tỉ lệ W/C.

Các chỉ số executor như số active là ảnh chụp/ước lượng trong lúc hệ thống biến động. Để đánh giá mức ổn định và đỉnh tải, cần quan sát theo khoảng thời gian và cùng bối cảnh tải, thay vì một lần đọc rồi tăng số luồng theo phản xạ.

## 10. Quy trình thử nghiệm có thể lặp lại

1. Xác định mục tiêu: tốc độ công việc cần phục vụ, độ trễ và mức tài nguyên được phép dùng.
2. Chọn tải đại diện, gồm kích thước dữ liệu, tỉ lệ công việc và hành vi dịch vụ phụ thuộc.
3. Xác định giới hạn CPU, bộ nhớ và tài nguyên phía sau; đưa ra một khoảng kích thước ứng viên.
4. Đặt queue và chính sách từ chối hữu hạn/phù hợp để thí nghiệm không che quá tải bằng tích việc vô hạn.
5. Thử từng cấu hình dưới cùng điều kiện, có giai đoạn khởi động ổn định và khoảng đo đủ ý nghĩa.
6. So sánh cả thông lượng, đuôi độ trễ, lỗi và tài nguyên; giữ cấu hình đáp ứng mục tiêu với dự phòng cần thiết.
7. Thử tải tăng theo đợt, phụ thuộc chậm và dừng dịch vụ để biết cấu hình phản ứng khi không còn điều kiện lý tưởng.

Không chỉ thử “gửi N tác vụ rồi đợi xong” và lấy thời gian ngắn nhất làm kết luận vận hành. Cách phát tải cũng quan trọng: nếu bộ phát phải chờ hệ thống trả lời rồi mới gửi tiếp, nó có thể tự giảm tốc và không phơi bày đúng độ trễ khi yêu cầu mới vẫn tiếp tục đến.

Đừng in log trong vòng nóng rồi coi kết quả đó là hiệu năng tính toán thuần. Giữ chi phí quan sát ổn định giữa các cấu hình và dùng công cụ phù hợp với câu hỏi đang đo. Mã ví dụ trong bài kiểm chứng cơ chế, không thay quy trình đo tải của ứng dụng thật.

## 11. Tải hỗn hợp, phụ thuộc và vòng đời

Nếu một nhóm vừa chạy công việc CPU dài vừa chạy các công việc I/O cần phản hồi nhanh, công việc loại này có thể làm loại kia phải chờ. Tách nhóm theo loại tài nguyên hoặc mục tiêu phục vụ có thể giúp kiểm soát, nhưng phải tính tổng ngân sách luồng và số kết nối; tạo thêm nhiều nhóm không tạo thêm CPU.

Cần đặc biệt tránh tác vụ trong một nhóm nhỏ gửi tác vụ con vào chính nhóm rồi chờ Future của nó. Nếu tất cả luồng đều đang chờ như vậy, phần con không còn luồng để chạy. Tăng một vài luồng có thể chỉ dời điểm mắc kẹt; nên sửa mô hình phụ thuộc hoặc cách phối hợp kết quả.

`keepAliveTime` ảnh hưởng thu hồi luồng rảnh, không giới hạn thời gian một công việc đang chạy. Tăng/giảm thông số đó không trực tiếp khắc phục CPU quá tải hay dịch vụ phía sau chậm. Chủ sở hữu vẫn phải quản lý shutdown, thời hạn chờ và hủy hợp tác.

Java mới có thêm mô hình virtual thread cho công việc chờ I/O. Khi dùng mô hình đó, không nên máy móc áp công thức số platform worker cho số virtual thread; giới hạn kết nối, tốc độ dịch vụ và công việc đang giữ bộ nhớ vẫn phải được quản lý. Bài không yêu cầu thay mô hình chạy hiện có chỉ để chọn được kích thước ThreadPoolExecutor.

## 12. Tự kiểm tra và thực hành

| Ngộ nhận | Điều cần kiểm tra |
|---|---|
| Số luồng càng lớn thì càng nhanh | Điểm nghẽn và tổng tài nguyên thực tế |
| Tải I/O thì không cần giới hạn luồng | Giới hạn kết nối/dịch vụ/bộ nhớ và lượng công việc đang giữ |
| availableProcessors là cấu hình tối ưu sẵn có | Nó chỉ cho dữ liệu CPU khả dụng làm cơ sở thử nghiệm |
| Max lớn là executor chắc dùng hết max | Loại queue và thứ tự tiếp nhận |
| Công thức cho ra N thì triển khai ngay | Giả định, ngân sách phụ thuộc và đo tải |
| Queue lớn giải quyết tốc độ đến cao kéo dài | Queue chỉ tích việc; phải xử lý giới hạn khả năng phục vụ |
| Get timeout thì công việc đã thôi chiếm luồng | Timeout của bên chờ không tự hủy công việc |

Tự kiểm tra:

1. Vì sao nhóm CPU có thể chậm hơn khi tăng gấp nhiều lần số luồng so với CPU? **Tăng cạnh tranh/lập lịch nhưng không tạo thêm năng lực tính toán.**
2. Tỉ lệ W/C lớn có đủ để chọn nhiều luồng không? **Chưa.** Cần xét W do đâu và tài nguyên phía sau có chịu được không.
3. Vì sao kết quả `peak active: 2` không chứng minh hai luồng là nhanh nhất? **Nó chỉ xác nhận giới hạn cấu hình dưới tải mô phỏng, không so sánh hiệu năng đại diện.**
4. Vì sao phải tính ngân sách trên nhiều bản sao? **Mọi bản sao cùng cạnh tranh các phụ thuộc dùng chung.**

Thực hành: đổi cả core/max trong ví dụ thành 1 và sửa latch đợi đợt đầu thành 1; dự đoán số tác vụ đang chờ trước khi mở latch. Sau đó thử core/max bằng 4 với latch 4 để kiểm chứng mức đồng thời mới. Tách rõ thí nghiệm cơ chế đó với bài đo hiệu năng: muốn chọn cấu hình cho một ứng dụng thật, thay latch bằng công việc đại diện có giới hạn và thu đủ các chỉ số trước khi kết luận.
