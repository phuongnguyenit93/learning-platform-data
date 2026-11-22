# Backpressure và lựa chọn dung lượng hữu hạn

## 1. Vấn đề: tốc độ đưa việc vào lớn hơn tốc độ xử lý

Một hàng đợi hai đầu giúp tách bên tạo công việc khỏi bên xử lý. Tuy nhiên, tách rời không có nghĩa bên xử lý sẽ nhanh hơn. Nếu mỗi giây có 200 công việc đến nhưng chỉ xử lý xong 100 công việc, phần tồn đọng tăng khoảng 100 công việc mỗi giây trong khoảng đó.

Đệm thêm công việc vào bộ nhớ chỉ trì hoãn thời điểm hệ thống phải quyết định: tiếp tục chờ, từ chối, giảm tốc độ đầu vào hay chuyển công việc sang nơi khác. Nếu bỏ qua quyết định này, độ trễ có thể tăng rất cao trước cả khi bộ nhớ cạn.

**Điều tiết ngược (backpressure)** là cách áp lực từ bên xử lý chậm truyền ngược về bên đưa việc vào, khiến đầu vào giảm tốc hoặc phải xử lý tình trạng chưa được tiếp nhận. Trong một đường xử lý dùng `BlockingDeque`, dung lượng hữu hạn tạo ra ranh giới; cách ứng dụng phản ứng khi chạm ranh giới mới quyết định chính sách điều tiết.

```text
bên tạo -> [deque có giới hạn] -> bên xử lý
   ^              |
   |          khi đã đầy
   +--- chờ / chưa được nhận / giảm tốc
```

Giới hạn hàng đợi là một công cụ quản lý tài nguyên. Nó không tự tạo thêm năng lực xử lý, không bảo đảm mọi công việc được nhận, cũng không tự biến toàn bộ hệ thống thành một giao thức điều tiết theo nhu cầu như Reactive Streams.

## 2. Dung lượng của LinkedBlockingDeque giới hạn điều gì?

`LinkedBlockingDeque` cho phép chỉ định một dung lượng dương cố định. Nếu không truyền dung lượng, giới hạn mặc định là `Integer.MAX_VALUE`; đây không phải một ngân sách bộ nhớ thực tế dành riêng cho ứng dụng. Các nút được tạo khi thêm phần tử. [Tài liệu LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

```java
// Minh họa khai báo, cần import các kiểu từ java.util.concurrent.
BlockingDeque<Job> queue = new LinkedBlockingDeque<>(128);
```

`Job` là kiểu công việc do ứng dụng định nghĩa. Con số 128 có nghĩa tối đa 128 phần tử đang nằm trong deque, tính chung cả hai đầu. Không có 128 chỗ riêng cho đầu và 128 chỗ riêng cho cuối.

Cần phân biệt ba phạm vi:

| Phạm vi | Ví dụ | Dung lượng deque có giới hạn trực tiếp không? |
| --- | --- | --- |
| Công việc đang nằm trong deque | 128 phần tử đang đợi lấy | Có, theo số phần tử |
| Công việc đã được lấy ra và đang xử lý | 8 luồng đang gọi dịch vụ khác | Không |
| Công việc còn giữ ở bên ngoài | Nhiều luồng tạo bị chặn, bộ đệm mạng, hàng đợi executor khác | Không |

Ngay khi bên xử lý lấy một phần tử, deque có thể nhận phần tử khác, mặc dù công việc vừa lấy còn đang chạy. Nếu muốn giới hạn tổng số công việc đã nhận nhưng chưa hoàn tất, cần một cơ chế theo dõi/giới hạn riêng, chẳng hạn giấy phép được giữ từ lúc nhận đến lúc hoàn thành. Không dùng `queue.size()` làm đại diện cho toàn bộ công việc đang tồn tại.

Dung lượng cũng là **số phần tử**, không phải byte. Một công việc chứa mảng 10 MiB và một công việc chỉ chứa mã định danh đều chiếm một chỗ, nhưng tác động lên bộ nhớ rất khác.

## 3. Chọn phản ứng khi đầy trước khi chọn con số

Các phương thức thêm có những hợp đồng khác nhau:

| Cách thêm ở cuối | Nếu đang đầy | Khi nào phù hợp? |
| --- | --- | --- |
| `putLast(job)` | Chờ chỗ trống; có thể bị ngắt | Bên tạo được phép chờ và có cơ chế dừng/hủy |
| `offerLast(job)` | Trả `false` | Cần quyết định ngay công việc có được nhận không |
| `offerLast(job, timeout, unit)` | Chờ có giới hạn, trả `false` nếu chưa thêm được | Chỉ được dành một phần thời gian cho bước tiếp nhận |
| `addLast(job)` | Ném `IllegalStateException` | Đầy được coi là tình huống vi phạm điều kiện mà bên gọi phải xử lý |

Các phương thức ở đầu có tên tương ứng `putFirst`, `offerFirst`, `addFirst` và dùng chung giới hạn. Phiên bản `put` và `offer` có thời hạn khai báo `InterruptedException`. [Các dạng thao tác BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html)

Một deque hữu hạn kết hợp với `putLast` có thể làm bên tạo chậm lại một cách trực tiếp. Với `offerLast`, bên gọi phải phản ứng với `false`; nếu bỏ qua kết quả thì chỉ tạo ra mất công việc âm thầm. Nếu bên gọi chuyển mọi công việc bị từ chối sang một danh sách không giới hạn, áp lực chỉ bị đẩy sang chỗ khác.

Đoạn minh họa tại biên tiếp nhận công việc:

```java
// queue, job và reject là các thành phần do ứng dụng cung cấp.
boolean accepted = queue.offerLast(job, 50, TimeUnit.MILLISECONDS);
if (!accepted) {
    reject(job); // Báo rõ chưa được tiếp nhận; không báo thành công.
}
```

Thời hạn 50 ms ở đây dành cho bước thêm vào deque. Nó không phải thời hạn hoàn thành công việc. Nếu yêu cầu còn có đọc dữ liệu, gọi dịch vụ và chờ kết quả, những bước đó phải cùng nằm trong ngân sách thời gian tổng thể do ứng dụng quản lý.

## 4. Minh chứng chạy được: bên tạo chờ khi đủ chỗ

Chương trình sau có deque dung lượng 2. Luồng chính điền đủ hai chỗ rồi khởi động một bên tạo đang cố thêm công việc thứ ba. Trước khi luồng chính lấy một phần tử, bên tạo không thể xác nhận đã thêm xong.

Lưu thành `BoundedDequeDemo.java`, dùng Java 17+ và không cần thư viện ngoài:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class BoundedDequeDemo {
    public static void main(String[] args) throws Exception {
        BlockingDeque<String> queue = new LinkedBlockingDeque<>(2);
        queue.putLast("job-1");
        queue.putLast("job-2");
        System.out.println("slots=" + queue.remainingCapacity());
        System.out.println("offer=" + queue.offerLast("rejected"));

        CountDownLatch entering = new CountDownLatch(1);
        CompletableFuture<Void> added = new CompletableFuture<>();
        Thread producer = new Thread(() -> {
            entering.countDown();
            try {
                queue.putLast("job-3");
                added.complete(null);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                added.completeExceptionally(e);
            }
        }, "producer");

        producer.start();
        try {
            entering.await();
            try {
                added.get(100, TimeUnit.MILLISECONDS);
                throw new AssertionError("The queue has no free slot");
            } catch (TimeoutException expected) {
                System.out.println("producer-not-finished");
            }

            System.out.println("taken=" + queue.takeFirst());
            added.get(5, TimeUnit.SECONDS);
            System.out.println("producer-finished");
            System.out.println("queue=" + queue);
            System.out.println("size=" + queue.size());
        } finally {
            producer.interrupt();
            producer.join();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 BoundedDequeDemo.java
java BoundedDequeDemo
```

Đầu ra:

```text
slots=0
offer=false
producer-not-finished
taken=job-1
producer-finished
queue=[job-2, job-3]
size=2
```

`offer=false` chứng minh phương án thử thêm không chờ đã không tiếp nhận phần tử `rejected`; phần tử đó không xuất hiện trong deque. Bên tạo tiếp theo dùng `putLast` nên giữ nguyên ý định thêm `job-3` và chờ.

`entering` chỉ báo rằng luồng tạo đã bắt đầu đi đến thao tác thêm, không chứng minh một trạng thái luồng tại đúng thời điểm lấy mẫu. Điều chương trình kiểm tra là chưa có xác nhận thêm xong trong khi hai chỗ vẫn bị chiếm. `CompletableFuture.get` hết thời hạn không hủy thao tác `putLast`; sau khi lấy `job-1`, chính thao tác đó có thể hoàn thành.

Mọi dòng đầu ra đều do luồng chính in. Lần `added.get` thành công diễn ra trước khi xem nội dung deque, và không có luồng nào còn thay đổi deque sau đó, nên danh sách cuối có thứ tự xác định. Khoảng 100 ms chỉ là cửa sổ quan sát, không phải một phép đo chính xác thời gian chờ hay hiệu năng.

## 5. Ước lượng dung lượng từ bộ nhớ, độ trễ và đợt tăng tải

Không có con số 128, 1.000 hay 10.000 đúng cho mọi hệ thống. Hãy bắt đầu từ các ràng buộc có thể đo được và ghi rõ giả định. Các phép tính dưới đây là mô hình lập kế hoạch đơn giản, không phải bảo đảm độ trễ trong môi trường thật.

### 5.1. Ràng buộc bộ nhớ

Gọi `M` là ngân sách bộ nhớ được dành cho phần công việc đang xếp hàng, `S` là chi phí giữ lại ước lượng trên một phần tử:

```text
C_memory <= floor(M / S)
```

`S` cần tính phần dữ liệu mà tham chiếu trong deque làm còn sống, không chỉ kích thước của một tham chiếu. Ngoài dữ liệu công việc còn có nút liên kết và chi phí đối tượng. Khi công việc có kích thước biến động lớn, cần giới hạn kích thước từng công việc hoặc theo dõi tổng byte; giới hạn số phần tử đơn thuần chưa đủ.

Ví dụ, nếu dành 4 MiB và ước lượng mỗi công việc giữ 16 KiB dữ liệu, phép chia cho kết quả 256 công việc **trước khi** tính chi phí cấu trúc và phần dự phòng. Không lấy 256 làm một cấu hình chắc chắn an toàn mà chưa đo thực tế; bộ nhớ của luồng xử lý, dữ liệu đang chạy và phần còn lại của JVM cũng cần ngân sách riêng.

### 5.2. Ràng buộc thời gian chờ

Giả sử toàn bộ bên xử lý duy trì được 100 công việc/giây, các công việc có thời gian xử lý tương đối đều và được lấy theo FIFO. Nếu chấp nhận khoảng 0,2 giây nằm trong hàng đợi, một ước lượng thô là:

```text
số việc đợi ≈ tốc độ xử lý tổng × thời gian chờ cho phép
            ≈ 100 × 0,2
            ≈ 20 công việc
```

Đây chỉ là ước lượng khi dòng xử lý hoạt động ổn định. Nó không bảo đảm p95/p99, không bao gồm thời gian xử lý của chính công việc, và không xử lý đầy đủ tác động của công việc rất chậm, dịch vụ bị treo hay phân bố thời gian phục vụ không đều. Nếu dịch vụ phía sau ngừng phản hồi, ngay cả một hàng đợi rất ngắn cũng có thể chờ lâu.

Dung lượng quá lớn có thể giữ rất nhiều công việc đã không còn cơ hội hoàn thành trong thời hạn của bên gọi. Tăng dung lượng không nhất thiết cải thiện trải nghiệm; đôi khi chỉ biến từ chối sớm thành hết thời gian muộn.

### 5.3. Ràng buộc do đợt tăng tải

Với một khoảng tăng tải tương đối đều, phần tồn đọng tăng thêm được ước lượng:

```text
tồn đọng tăng ≈ max(0, tốc độ đến - tốc độ xử lý) × thời gian tăng tải
```

Nếu có 200 công việc/giây đến trong 5 giây, bên xử lý chỉ đạt 100 công việc/giây, thì tồn đọng tăng khoảng 500 công việc. Kết quả giả định ban đầu chưa có công việc đang đợi và khả năng xử lý vẫn giữ được mức đó.

Ở ví dụ này, nhận hết đợt tăng tải đòi hỏi bộ đệm khoảng 500 phần tử, trong khi mô hình độ trễ vừa rồi chỉ cho khoảng 20; mô hình bộ nhớ cũng chỉ cho tối đa 256 trước dự phòng. Ba yêu cầu đang không đồng thời thỏa mãn. Không thể giải mâu thuẫn chỉ bằng một giá trị dung lượng.

Cần chọn thay đổi có ý nghĩa đối với nghiệp vụ: giảm lượng được tiếp nhận, tăng năng lực xử lý nếu nút thắt cho phép, chấp nhận thời gian chờ dài hơn, gộp các cập nhật tương đương, hoặc chuyển sang nơi lưu bền vững nếu công việc thực sự phải được giữ lại. Nơi lưu bền vững vẫn có giới hạn và chính sách quá tải riêng.

### 5.4. Kiểm tra cả tải kéo dài

Một bộ đệm hữu hạn giúp hấp thụ chênh lệch ngắn hạn. Nếu lượng được nhận trung bình cứ cao hơn khả năng hoàn thành trong thời gian dài, mọi dung lượng hữu hạn cuối cùng đều đầy. Nếu hai mức trung bình sát nhau, các biến động cũng có thể tạo thời gian chờ lớn; cần khoảng dự phòng năng lực thay vì chỉ so sánh hai con số trung bình.

Ước lượng hợp lý để khởi đầu là chọn dung lượng nằm trong cả ngân sách bộ nhớ và ngân sách chờ, rồi thử tải để xem các giả định có đúng không. Nhu cầu hấp thụ tăng tải lớn hơn giới hạn đó phải được xử lý bằng chính sách tiếp nhận, không bị giấu đi bằng tăng hàng đợi.

## 6. Hệ thống phải làm gì khi không tiếp nhận được?

Chính sách phụ thuộc vào giá trị của công việc và hợp đồng với bên gọi:

- **Chờ có giới hạn:** bên tạo được phép chậm lại, nhưng sau một khoảng phải báo chưa tiếp nhận. Phù hợp khi vẫn còn ngân sách thời gian.
- **Từ chối rõ ràng:** trả trạng thái mà bên gọi hiểu được là công việc chưa được nhận. Không xác nhận thành công trước rồi âm thầm bỏ.
- **Gộp hoặc thay thế:** chỉ dùng khi nhiều công việc biểu diễn cùng một trạng thái và nghiệp vụ cho phép bỏ trạng thái trung gian. Không áp dụng tùy tiện cho giao dịch hoặc sự kiện phải xử lý từng lần.
- **Lưu bền vững:** tách yêu cầu giữ việc khỏi bộ nhớ tiến trình, đi kèm quy tắc xác nhận, thử lại và giới hạn dung lượng.

Việc thử lại cần giới hạn số lần, tổng thời gian và tốc độ. Nếu mọi bên gọi thử lại ngay khi deque đầy, tải mới còn được cộng thêm tải thử lại. Một vòng `while (!queue.offerLast(job)) {}` không phải cách giảm tải: nó tiếp tục tiêu tốn tài nguyên trong khi không có chỗ trống.

Phải phân biệt “được đưa vào deque” và “đã xử lý thành công”. Kết quả `true` từ `offerLast` chỉ xác nhận bước đầu. Nếu tiến trình dừng sau khi nhận vào bộ nhớ, `BlockingDeque` tự nó không bảo đảm phục hồi công việc.

## 7. Các bẫy riêng của hàng đợi hai đầu

### Chỗ trống không được đặt trước bằng một lần kiểm tra

Không viết quy tắc tiếp nhận như sau rồi coi đó là nguyên tử:

```java
// Minh họa cách kiểm tra sai khi có nhiều bên tạo.
if (queue.remainingCapacity() > 0) {
    queue.addLast(job);
}
```

Một bên tạo khác có thể dùng hết chỗ sau lần kiểm tra. Cách ra quyết định trực tiếp là gọi `offerLast` và dựa trên kết quả của chính thao tác thêm. `size()` và `remainingCapacity()` có ích để quan sát, không phải giấy giữ chỗ cho lần gọi kế tiếp.

### Đưa lại vào đầu có thể chiếm đường của công việc khác

`putFirst` không có sức chứa riêng cho công việc ưu tiên hoặc thử lại. Nếu deque đã đầy, việc đưa lại vào đầu cũng phải đối mặt với giới hạn đó. Đưa liên tục công việc thử lại lên đầu còn có thể làm công việc cũ ở cuối chờ rất lâu.

Đặc biệt, nếu mọi luồng xử lý đều đang cố `putFirst` công việc thất bại vào một deque đầy, có thể không còn luồng nào thực hiện thao tác lấy để tạo chỗ trống. Chính sách thử lại phải tránh tình huống tất cả bên xử lý tự trở thành bên tạo đang bị chặn.

### Không giả định giới hạn deque là giới hạn executor

Nếu đưa `LinkedBlockingDeque` vào `ThreadPoolExecutor`, việc có một cấu trúc hỗ trợ `put` không khiến `execute` tự chờ bằng `put`. Executor có quy tắc tạo luồng, xếp hàng và từ chối riêng; khi đã đạt giới hạn số luồng và hàng đợi, tác vụ có thể bị từ chối. Cần đọc cả cấu hình executor và chính sách từ chối. [Quy tắc hàng đợi của ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

### Không chặn đường duy nhất có thể làm hệ thống tiến triển

Không để bên tạo giữ khóa mà bên xử lý cần rồi chờ `putLast`. Tương tự, nếu bên tạo và bên xử lý chỉ có chung một luồng thực thi, bên tạo bị chặn có thể khiến bên xử lý không bao giờ được chạy để giải phóng chỗ.

Với luồng sự kiện hoặc luồng tiếp nhận có yêu cầu phản hồi nhanh, chờ vô hạn còn có thể làm nghẽn nhiều yêu cầu khác. Hãy chọn `offer`/thời hạn hoặc một điểm tiếp nhận khác phù hợp với mô hình chạy của ứng dụng.

### Hữu hạn không có nghĩa số luồng bị chặn cũng hữu hạn

Mỗi luồng tạo bị chặn có thể còn giữ công việc và dữ liệu liên quan ở ngoài deque. Cho phép vô số bên tạo cùng chờ có thể làm bộ nhớ tăng dù `size()` không vượt dung lượng. Phải xem xét cả giới hạn đồng thời của đầu vào và các bộ đệm trước deque.

## 8. Đo gì để điều chỉnh cấu hình?

Đừng tăng dung lượng chỉ vì thấy deque đầy một lần. Hãy quan sát theo thời gian:

| Dữ liệu cần đo | Câu hỏi nó giúp trả lời |
| --- | --- |
| Mức chiếm dụng và thời gian liên tục ở gần đầy | Đây là đợt tăng tải ngắn hay quá tải kéo dài? |
| Tốc độ đến, được tiếp nhận, hoàn thành và thử lại | Công việc tích tụ ở đâu, thử lại có khuếch đại tải không? |
| Số lần `offer` trả `false`, số lần hết thời gian | Chính sách từ chối đang tác động đến bao nhiêu công việc? |
| Thời gian chờ của bên tạo và thời gian nằm trong deque | Áp lực đang truyền về đâu, độ trễ có vượt ngân sách không? |
| Công việc đang xử lý và tài nguyên phía sau | Nút thắt có thực sự nằm ở số luồng xử lý không? |
| Bộ nhớ giữ lại, kích thước công việc, thời gian GC | Giới hạn số phần tử có thực sự giữ được ngân sách bộ nhớ? |

Đo thời gian nằm trong deque bằng thời điểm tiếp nhận và thời điểm bắt đầu xử lý. Chọn rõ điểm bắt đầu đo: nếu ghi thời điểm trước một lần `put` có thể bị chặn, phép đo sau đó sẽ bao gồm cả thời gian chờ được thêm, chứ không chỉ thời gian nằm trong deque.

Thử tải nên có ít nhất ba tình huống: tải bình thường, đợt tăng tải ngắn và bên xử lý chậm/ngừng tiến triển. Kiểm tra cả khi dừng hệ thống: bên tạo đang chờ có thoát được không, công việc đã nhận được quản lý ra sao, kết quả báo cho bên gọi có chính xác không.

## 9. Bài tập quyết định

Một hệ thống xử lý đều 50 công việc/giây. Mỗi công việc giữ khoảng 8 KiB dữ liệu. Ngân sách dữ liệu đang xếp hàng là 1 MiB, ngân sách chờ ước lượng là 0,1 giây. Một đợt đầu vào 100 công việc/giây kéo dài 2 giây.

1. Giới hạn theo dữ liệu là bao nhiêu trước khi tính chi phí cấu trúc? `1.024 KiB / 8 KiB = 128` phần tử.
2. Ước lượng theo ngân sách chờ là bao nhiêu? `50 × 0,1 = 5` phần tử, với các giả định ổn định đã nêu.
3. Tồn đọng tăng trong đợt tải là bao nhiêu? `(100 - 50) × 2 = 100` phần tử.
4. Chọn dung lượng 100 có tự đáp ứng cả ba yêu cầu không? Không: nó không phù hợp ngân sách chờ thô 5 phần tử, dù vẫn dưới giới hạn dữ liệu chưa tính dự phòng.
5. Nếu giữ mục tiêu chờ ngắn, ứng dụng phải làm gì? Quyết định tiếp nhận có giới hạn và phản hồi khi không nhận được, hoặc thay đổi năng lực/chính sách nghiệp vụ; không chỉ mở rộng deque.

Điểm cần nhớ khi thiết kế là ghép **một dung lượng có căn cứ** với **một chính sách quá tải rõ ràng**, rồi kiểm chứng cả hai bằng dữ liệu thực tế.
