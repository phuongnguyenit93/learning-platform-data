# BlockingQueue trong mô hình bên sản xuất và bên tiêu thụ

## 1. Tách nơi tạo dữ liệu khỏi nơi xử lý dữ liệu

Trong mô hình bên sản xuất/bên tiêu thụ (producer-consumer), một phần chương trình tạo ra đơn vị công việc, còn phần khác nhận và xử lý chúng. Hai phía không cần chạy cùng tốc độ hoặc biết chi tiết triển khai của nhau.

Ví dụ: một bên đọc dòng dữ liệu và tạo yêu cầu phân tích; một hoặc nhiều bên khác lấy từng yêu cầu để phân tích. Giữa hai phía cần một nơi bàn giao dữ liệu có kiểm soát:

```text
Producer 1 ─┐                          ┌─ Consumer 1
            ├─→ BlockingQueue<Work> ───┤
Producer 2 ─┘                          └─ Consumer 2
```

`BlockingQueue<E>` là giao diện hàng đợi an toàn luồng, có các thao tác chờ khi chưa lấy được phần tử hoặc chưa có chỗ để thêm phần tử. Nó giúp tránh tự quản lý một danh sách chung, khóa và vòng chờ cho từng trường hợp.

API này vẫn áp dụng trong Java hiện nay. Ví dụ đầy đủ trong bài dùng Java 17 trở lên.

## 2. Hai tình huống chờ của mô hình

### Consumer đến trước dữ liệu

Nếu queue đang rỗng, `take()` chờ đến khi có phần tử. Consumer không cần lặp liên tục kiểm tra size rồi ngủ một khoảng đoán trước.

### Producer nhanh hơn khả năng xử lý

Nếu queue có dung lượng hữu hạn và đã đầy, `put(element)` chờ đến khi có chỗ. Áp lực từ phía xử lý được truyền ngược về phía tạo dữ liệu: producer chưa thể tiếp tục đưa thêm vô hạn công việc vào bộ nhớ.

```text
queue rỗng → take chờ dữ liệu
queue đầy  → put chờ chỗ trống
```

Chờ ở đây thuộc luồng đang gọi thao tác, không phải queue tự tạo luồng xử lý. Ứng dụng vẫn phải tạo các tác vụ/luồng producer và consumer phù hợp. [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 3. Chọn thao tác theo chính sách chờ

| Mục đích | Không chờ, báo bằng giá trị | Chờ đến khi làm được | Chờ tối đa một khoảng |
|---|---|---|---|
| Thêm phần tử | `offer(e)` → false nếu chưa thêm được | `put(e)` | `offer(e, timeout, unit)` → false nếu hết hạn |
| Lấy và xóa phần tử đầu | `poll()` → null nếu chưa có | `take()` | `poll(timeout, unit)` → null nếu hết hạn |

Ngoài ra `add(e)` hoặc `remove()` dùng ngoại lệ cho một số trường hợp không thể thực hiện ngay; không nhầm chúng với các thao tác chờ.

Việc chọn phương thức là một quyết định ứng dụng:

- Dùng put nếu producer được phép chờ để không mất công việc, đồng thời có đường ngắt/dừng khi hệ thống không tiến triển.
- Dùng offer có thời hạn nếu muốn chờ có giới hạn rồi xử lý quá tải rõ ràng.
- Dùng poll có thời hạn nếu consumer cần định kỳ xem xét điều kiện quản lý khác; null không tự chứng minh sẽ không còn producer đưa việc sau đó.

BlockingQueue không nhận phần tử null. Giá trị null của poll được dành để báo không lấy được phần tử, nên tín hiệu kết thúc phải dùng một giá trị/đối tượng có nghĩa rõ khác.

`put` trả về chỉ cho biết phần tử đã được đưa vào queue; không chứng minh consumer đã xử lý xong. Tương tự, `take` trả phần tử không có nghĩa nghiệp vụ của phần tử đó đã thành công.

## 4. Queue hữu hạn tạo bộ đệm và điều tiết tốc độ

Ví dụ:

```java
BlockingQueue<Work> queue = new ArrayBlockingQueue<>(100);
```

Đoạn minh họa cần kiểu Work và các import phù hợp. Có tối đa 100 phần tử nằm trong vùng đệm, không tính công việc consumer đã lấy ra để xử lý hoặc dữ liệu producer đang chuẩn bị bên ngoài queue.

Queue không tự tăng tốc consumer. Nó giúp hấp thụ một đợt tạo việc nhanh ngắn hạn; nếu tốc độ tạo cao hơn tốc độ xử lý trong thời gian dài thì:

- Queue hữu hạn sẽ gây chờ/từ chối theo thao tác được chọn.
- Queue không giới hạn thực tế có thể tiếp tục giữ nhiều công việc và kéo dài độ trễ cho tới khi tài nguyên cạn.

Chọn dung lượng theo bộ nhớ, thời gian chờ chấp nhận được và hành vi quá tải. Một phần tử có thể giữ cả một khối dữ liệu lớn; giới hạn số phần tử không tự tương đương một giới hạn byte chặt chẽ.

ArrayBlockingQueue có dung lượng cố định, thứ tự FIFO và tùy chọn công bằng cho các luồng đang chờ. Công bằng có thể ảnh hưởng thông lượng; nó không có nghĩa thứ tự hoàn thành nghiệp vụ của nhiều consumer được giữ nguyên. [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

## 5. Bàn giao dữ liệu và tính an toàn luồng

BlockingQueue bảo đảm các hành động trước khi một luồng đưa phần tử vào queue xảy ra-trước các hành động sau khi luồng khác truy cập/lấy phần tử đó theo hợp đồng. Điều này tạo ranh giới công bố dữ liệu từ producer sang consumer.

```text
Producer chuẩn bị Work
    → put(Work)
    → consumer take cùng Work
    → consumer đọc dữ liệu đã được bàn giao
```

Nên ưu tiên một đơn vị công việc bất biến, hoặc chuyển quyền sở hữu rõ ràng sau khi đưa vào queue. Nếu producer tiếp tục sửa một đối tượng mutable trong khi consumer xử lý, queue không tự bảo vệ những lần sửa mới đó.

Tính an toàn của các thao tác queue cũng không biến mọi chuỗi kiểm tra-thực hiện thành nguyên tử. Ví dụ `if (!queue.isEmpty()) queue.take()` vẫn có thể chờ vì một consumer khác lấy phần tử giữa hai câu lệnh. Dùng take hoặc poll theo chính sách mong muốn, thay vì kiểm tra size trước để đoán kết quả.

Queue không sao chép sâu phần tử và không tự xử lý trạng thái của các đối tượng khác mà consumer cùng chia sẻ. Một bộ đếm tổng chung vẫn cần đồng bộ/kiểu nguyên tử, hoặc có thể cho mỗi consumer trả một phần kết quả rồi tổng hợp sau.

## 6. Chương trình đầy đủ với hai producer và hai consumer

Ví dụ có queue ba chỗ và bốn tác vụ chạy trên nhóm bốn luồng. Hai producer tạo các giá trị 1–3 và 4–6. Hai consumer lấy việc, tính tổng riêng, rồi trả phần kết quả của mình.

BlockingQueue không có thao tác close chung. Chương trình dùng một loại phần tử mang cờ kết thúc. Main chỉ gửi hai tín hiệu kết thúc **sau khi cả hai producer hoàn tất đưa dữ liệu**, tương ứng một tín hiệu cho mỗi consumer.

Lưu thành `ProducerConsumerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ProducerConsumerDemo {
    record Item(int value, boolean stop) { }
    record Result(int count, int sum) { }
    private static final Item STOP = new Item(0, true);

    private static Callable<Integer> producer(
            BlockingQueue<Item> queue, int first, int last) {
        return () -> {
            int produced = 0;
            for (int value = first; value <= last; value++) {
                queue.put(new Item(value, false));
                produced++;
            }
            return produced;
        };
    }

    private static Callable<Result> consumer(BlockingQueue<Item> queue) {
        return () -> {
            int count = 0;
            int sum = 0;
            while (true) {
                Item item = queue.take();
                if (item.stop()) {
                    return new Result(count, sum);
                }
                count++;
                sum += item.value();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Item> queue = new ArrayBlockingQueue<>(3);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<?>> all = new ArrayList<>();

        try {
            Future<Result> firstConsumer = pool.submit(consumer(queue));
            all.add(firstConsumer);
            Future<Result> secondConsumer = pool.submit(consumer(queue));
            all.add(secondConsumer);
            Future<Integer> firstProducer = pool.submit(producer(queue, 1, 3));
            all.add(firstProducer);
            Future<Integer> secondProducer = pool.submit(producer(queue, 4, 6));
            all.add(secondProducer);

            int produced = firstProducer.get(10, TimeUnit.SECONDS)
                    + secondProducer.get(10, TimeUnit.SECONDS);
            queue.put(STOP);
            queue.put(STOP);

            Result first = firstConsumer.get(10, TimeUnit.SECONDS);
            Result second = secondConsumer.get(10, TimeUnit.SECONDS);
            System.out.println("produced: " + produced);
            System.out.println("consumed: " + (first.count() + second.count()));
            System.out.println("sum: " + (first.sum() + second.sum()));
            System.out.println("queue empty: " + queue.isEmpty());
        } finally {
            for (Future<?> future : all) {
                future.cancel(true);
            }
            pool.shutdownNow();
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ProducerConsumerDemo.java
java ProducerConsumerDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
produced: 6
consumed: 6
sum: 21
queue empty: true
```

### Đọc bằng chứng

Không giả định consumer thứ nhất nhận đúng ba phần tử hoặc nhận toàn bộ dữ liệu của producer thứ nhất. Phân phối giữa hai consumer phụ thuộc lịch chạy. Tổng count và sum là các tính chất cần giữ.

Hai producer có thể xen kẽ thứ tự đưa dữ liệu, nhưng đều hoàn tất trước khi main đưa STOP. Với queue FIFO đang dùng, các tín hiệu STOP đứng sau dữ liệu đã đưa vào. Mỗi consumer gặp một STOP thì trả về, nên cần đủ hai tín hiệu để cả hai dừng.

Các kết quả riêng không cần một biến tổng được hai consumer cùng tăng. Main tổng hợp sau khi lấy Future của từng bên. Phần finally hủy các tác vụ còn sống và yêu cầu dừng nhóm nếu có đường lỗi; các put/take phản hồi ngắt theo hợp đồng thay vì bỏ qua tín hiệu dừng.

Mã minh họa đường thành công với producer/consumer nhỏ và không có lỗi nghiệp vụ. Với một hệ thống có thể mất consumer trong lúc main gửi STOP, không được mặc định `put(STOP)` luôn hoàn tất: cần giám sát công việc còn sống hoặc dùng cơ chế dừng có giới hạn phù hợp.

## 7. Dừng consumer: queue không tự biết “hết dữ liệu vĩnh viễn”

Queue rỗng là một trạng thái tạm thời. Producer có thể thêm dữ liệu ngay sau đó. Consumer không nên thoát chỉ vì một lần isEmpty trả true nếu hợp đồng chưa xác nhận bên sản xuất đã xong.

Một số chiến lược kết thúc:

| Chiến lược | Khi phù hợp | Điều cần thiết kế |
|---|---|---|
| Phần tử kết thúc như STOP | Biết số consumer và có thể hoàn tất sản xuất | Đúng số tín hiệu, thứ tự sau mọi dữ liệu, không nhầm với dữ liệu thật |
| Ngắt tác vụ consumer | Chủ sở hữu muốn hủy/chấm dứt | Cách xử lý phần đang làm và dữ liệu còn trong queue |
| Poll có thời hạn cùng trạng thái vòng đời | Cần xem xét dừng định kỳ | Trạng thái producer đã xong phải được công bố đúng; không coi timeout đơn lẻ là hết dữ liệu |
| Một giao thức điều phối khác | Dòng việc hoặc lỗi phức tạp hơn | Quyền dừng, xác nhận công việc và đường phục hồi |

STOP không nên là null. Cũng tránh lấy một giá trị dữ liệu hợp lệ như `0` để ngầm coi là kết thúc nếu ứng dụng thật có thể cần xử lý giá trị đó. Ví dụ dùng cờ riêng để phân biệt.

Với nhiều producer, gửi STOP sau khi chỉ một producer xong có thể làm consumer thoát trước khi producer khác tạo hết việc. Với nhiều consumer, một STOP không tự phát tới tất cả các bên; một phần tử được lấy ra bởi một consumer theo thao tác queue.

## 8. Tránh giữ hết luồng ở một phía rồi chờ phía kia

BlockingQueue giúp chờ hiệu quả, nhưng không tự cấp tài nguyên chạy cho bên còn lại. Một lỗi cấu hình thường gặp:

```text
Nhóm chỉ có hai luồng
    → gửi hai consumer chờ take trên queue rỗng
    → gửi producer vào cùng nhóm
    → producer ở queue tác vụ của executor, chưa được chạy
    → hai consumer vẫn chờ dữ liệu
```

Tương tự, có thể giữ hết luồng bằng các producer đang put vào queue đầy trong khi consumer chưa có cơ hội chạy.

Cần phân bổ tài nguyên sao cho những phía phụ thuộc nhau có thể tiến triển: dùng các nhóm riêng phù hợp, tạo đúng số luồng cho mô hình nhỏ, hoặc chọn cấu trúc điều phối khác. Ví dụ sử dụng bốn luồng cho bốn vai trò; nó không khuyến nghị tăng luồng vô hạn cho mọi bài toán.

Cũng không giữ một khóa ngoài trong khi gọi put/take nếu phía đối ứng cần khóa đó để tạo chỗ/dữ liệu. Chờ bên kia mà giữ tài nguyên bên kia cần có thể làm hệ thống tự mắc kẹt dù queue tự nó an toàn luồng.

## 9. Đã take không đồng nghĩa xử lý thành công đúng một lần

Một phần tử được một consumer lấy khỏi queue sẽ không còn nằm trong queue đó. Nếu consumer lỗi ngay sau take, BlockingQueue không tự đưa phần tử trở lại hoặc chuyển nó sang consumer khác.

Vì vậy cần phân biệt:

```text
đã tạo → đã đưa vào queue → đã lấy ra → đang xử lý → thành công/thất bại
```

An toàn thao tác queue không tự là bảo đảm nghiệp vụ “mỗi công việc thành công đúng một lần”. Nếu consumer đã tạo tác dụng phụ rồi thất bại, thử lại có thể gây lặp. Nếu chỉ mất phần tử và không lưu nhận dạng, có thể mất việc.

Với yêu cầu cần phục hồi sau lỗi/khởi động lại, phải thiết kế trạng thái, xác nhận, khả năng xử lý lặp hoặc một hệ thống lưu việc bền vững phù hợp. BlockingQueue trong bộ nhớ không tự giữ dữ liệu qua việc tiến trình kết thúc và không thay một giao thức giao việc bền vững.

Nếu producer thất bại hoặc consumer thất bại, chủ sở hữu cần thu nhận Future/lỗi và quyết định dừng hay tiếp tục. Không chỉ khởi động các vòng while vô hạn rồi bỏ mọi tay cầm vì “queue đã thread-safe”.

## 10. Chọn triển khai queue theo ý định

| Triển khai | Đặc điểm hữu ích | Câu hỏi phải trả lời |
|---|---|---|
| ArrayBlockingQueue | Vùng đệm mảng có dung lượng cố định, FIFO | Cần bao nhiêu chỗ để cân bằng bộ nhớ và độ trễ? |
| LinkedBlockingQueue có capacity | FIFO theo nút liên kết, giới hạn số phần tử | Đã đặt capacity rõ hay vô tình để mặc định rất lớn? |
| SynchronousQueue | Chuyển giao trực tiếp, không có vùng đệm | Bên giao có cần đợi bên nhận sẵn sàng không? |

LinkedBlockingQueue không truyền capacity có giới hạn mặc định là Integer.MAX_VALUE; không nên coi đó là một giới hạn bộ nhớ phù hợp sẵn cho ứng dụng. [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

SynchronousQueue không lưu một phần tử chờ, nên các thao tác quan sát như size bằng 0 không nói hệ thống không có luồng đang chờ giao/nhận hoặc không có công việc đang xử lý. [SynchronousQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

Không phải mọi triển khai BlockingQueue đều có cùng thứ tự FIFO: các queue ưu tiên hoặc trễ có hợp đồng khác. Nếu dùng STOP và dựa vào thứ tự dữ liệu trước tín hiệu kết thúc, phải bảo đảm thứ tự của triển khai đang chọn phù hợp.

## 11. Quan sát và xử lý áp lực đúng ranh giới

Các tín hiệu hữu ích gồm lượng việc producer tạo, lượng queue nhận, thời gian chờ put/take, số việc đang xử lý, số hoàn thành và số thất bại. Queue dài không tự là lỗi nếu nó hấp thụ một đợt ngắn theo dự kiến; queue tăng liên tục có thể cho thấy tốc độ tạo vượt khả năng xử lý.

Các số size/remainingCapacity có thể thay đổi ngay sau khi đọc. Đừng dùng `if (remainingCapacity() > 0) put(...)` để hứa producer chắc chắn không chờ. Dùng offer/timed offer khi muốn một quyết định tiếp nhận có kết quả rõ ràng.

Nếu chọn bỏ hoặc thử lại khi offer không nhận, phải ghi nhận chính sách đó. Không gọi là đã sản xuất thành công chỉ vì đã tạo được đối tượng Work trước khi queue nhận nó. Đưa thêm việc vào một danh sách đệm ngoài queue khi queue đầy cũng có thể vô hiệu hóa giới hạn bộ nhớ mà người thiết kế tưởng đã có.

## 12. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| BlockingQueue tự tạo consumer | Ứng dụng phải tổ chức các luồng/tác vụ |
| Put trả về nghĩa công việc đã xử lý | Chỉ xác nhận việc đưa phần tử thành công |
| Queue rỗng nghĩa hết dữ liệu vĩnh viễn | Cần biết producer đã xong theo giao thức |
| Một STOP làm mọi consumer dừng | Mỗi consumer cần đường nhận tín hiệu phù hợp |
| Thread-safe queue làm mọi đối tượng trong đó thread-safe | Quyền sở hữu và các lần sửa phần tử vẫn phải thiết kế |
| Take là xác nhận xử lý thành công | Consumer có thể lỗi sau khi lấy |
| Dung lượng queue giới hạn mọi bộ nhớ đang dùng | Còn việc đang xử lý và dữ liệu ngoài queue |

Tự kiểm tra:

1. Vì sao consumer không cần lặp kiểm tra isEmpty trước take? **Take đã có cơ chế chờ và lấy theo thao tác an toàn luồng.**
2. Vì sao main chờ cả hai producer trước khi đưa STOP? **Để không kết thúc consumer khi phía khác còn đưa dữ liệu thật.**
3. Vì sao không in số phần tử cố định cho từng consumer? **Phân phối công việc phụ thuộc lịch chạy; chỉ tổng trong thí nghiệm là cố định.**
4. Queue có ba chỗ có nghĩa tối đa ba công việc tồn tại không? **Không.** Consumer có thể đã lấy việc ra, producer cũng có dữ liệu đang chuẩn bị.

Thực hành: đổi dung lượng queue từ 3 thành 1 và kiểm tra tổng kết quả vẫn giữ nguyên. Sau đó tăng consumer lên ba, cấp tài nguyên chạy và số STOP tương ứng, thu kết quả cả ba. Cuối cùng, mô tả riêng chính sách khi một consumer ném lỗi sau take: công việc đó được ghi nhận, thử lại hoặc dừng dòng xử lý như thế nào để không ngầm coi mất phần tử là thành công?
