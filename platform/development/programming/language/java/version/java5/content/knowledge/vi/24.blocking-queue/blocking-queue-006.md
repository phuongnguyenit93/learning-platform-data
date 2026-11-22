# `LinkedBlockingQueue` và lựa chọn giới hạn dung lượng

## 1. Mô hình: một hàng công việc đang chờ, không phải bộ nhớ vô tận

`LinkedBlockingQueue<E>` là hàng đợi an toàn khi nhiều luồng cùng truy cập, dùng các nút liên kết để giữ phần tử. Bên tạo đưa công việc vào cuối hàng; bên xử lý lấy ở đầu hàng theo thứ tự vào trước, ra trước (FIFO). Khi cần, thao tác thêm có thể đợi chỗ trống và thao tác lấy có thể đợi dữ liệu.

Hàng đợi giúp tách tốc độ tạo và tốc độ xử lý trong một khoảng thời gian. Ví dụ một đợt yêu cầu đến nhanh có thể được giữ lại rồi xử lý dần. Nhưng nếu công việc liên tục đến nhanh hơn khả năng xử lý, hàng đợi chỉ tích lũy phần chênh lệch; nó không tạo thêm năng lực xử lý.

Vì vậy, câu hỏi quan trọng không chỉ là “dùng lớp hàng đợi nào?” mà còn là “cho phép bao nhiêu công việc chờ, chờ bao lâu và làm gì khi không nhận thêm được?”. Với `LinkedBlockingQueue`, giới hạn đó là một quyết định rõ ràng khi khởi tạo.

Các constructor và hành vi dưới đây vẫn được mô tả trong [Java SE `LinkedBlockingQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html), không cần API đã lỗi thời.

## 2. Ba cách khởi tạo và một bẫy mặc định

```java
BlockingQueue<String> defaultQueue = new LinkedBlockingQueue<>();
BlockingQueue<String> boundedQueue = new LinkedBlockingQueue<>(100);
BlockingQueue<String> seededQueue = new LinkedBlockingQueue<>(List.of("A", "B"));
```

Đây là đoạn minh họa; cần import `java.util.List`, `java.util.concurrent.BlockingQueue` và `java.util.concurrent.LinkedBlockingQueue` khi đặt trong chương trình.

| Cách tạo | Dung lượng tối đa | Số phần tử lúc tạo | Điều cần nhớ |
| --- | --- | --- | --- |
| `new LinkedBlockingQueue<>()` | `Integer.MAX_VALUE` | 0 | Gần như không có giới hạn thực dụng đối với bộ nhớ ứng dụng |
| `new LinkedBlockingQueue<>(100)` | 100 | 0 | Giới hạn 100 phần tử, không phải 100 byte |
| `new LinkedBlockingQueue<>(collection)` | `Integer.MAX_VALUE` | Số phần tử của collection | Không lấy kích thước collection làm dung lượng tối đa |

Constructor nhận số nguyên yêu cầu dung lượng lớn hơn 0. Dung lượng được cố định khi tạo; lớp này không có phương thức để tăng hoặc giảm dung lượng của chính đối tượng hàng đợi đó.

Constructor từ collection giữ thứ tự duyệt của collection, không tự sắp xếp theo ưu tiên. Collection hoặc phần tử `null` là đầu vào không hợp lệ. Khi dùng hàng đợi, không thêm `null`.

Nếu muốn có dữ liệu ban đầu **và** một giới hạn nhỏ, hãy tạo hàng đợi với giới hạn trước rồi đưa các phần tử vào theo chính sách đã chọn. Cần kiểm tra số phần tử ban đầu có phù hợp dung lượng; không giả định `addAll` sẽ tự biến thành một giao dịch toàn bộ hoặc không có gì.

### “Không giới hạn” là cách gọi thực dụng

Constructor mặc định vẫn có trần số phần tử là `Integer.MAX_VALUE`, không phải vô hạn toán học. Tuy nhiên, bộ nhớ có thể cạn rất lâu trước khi đạt trần này. Từ góc nhìn kiểm soát quá tải, không nên coi con số đó là một cơ chế bảo vệ bộ nhớ hữu ích cho ứng dụng thông thường.

Hàng đợi không cấp phát sẵn hơn hai tỷ nút lúc khởi tạo. Nút được tạo dần khi thêm phần tử. Điều đó làm việc khởi tạo nhẹ hơn so với việc dự trữ toàn bộ vùng chứa, nhưng không loại bỏ chi phí tăng bộ nhớ khi tồn đọng lớn.

## 3. Dung lượng đếm phần tử, còn bộ nhớ phụ thuộc dữ liệu được giữ

Mỗi phần tử trong hàng đợi có một nút liên kết và tham chiếu đến đối tượng dữ liệu. Vì hàng đợi giữ tham chiếu, dữ liệu còn nằm trong hàng thường vẫn có thể được truy cập và chưa thể được thu gom như dữ liệu đã không còn ai sử dụng.

Một ước lượng để bắt đầu lập ngân sách là:

```text
bộ nhớ gắn với tồn đọng
≈ số phần tử đang chờ × bộ nhớ trung bình giữ lại bởi một phần tử
  + chi phí nút liên kết và cấu trúc hàng đợi
```

Đây là mô hình ước lượng, không phải công thức đo heap chính xác. Các phần tử có thể chia sẻ cùng đối tượng con nên phép nhân có thể đếm trùng; ngược lại, một phần tử nhỏ có thể giữ tham chiếu đến một cấu trúc dữ liệu rất lớn. Chi phí đối tượng còn phụ thuộc JVM và cấu hình.

Ví dụ, 600 công việc, mỗi công việc giữ khoảng 8 KiB dữ liệu riêng, đã tương ứng khoảng 4,7 MiB dữ liệu trước khi cộng chi phí nút và các đối tượng bao quanh. Với công việc có kích thước biến động mạnh, giới hạn số phần tử chưa đủ để kiểm soát tốt số byte giữ lại. Có thể cần giới hạn kích thước đầu vào hoặc ngân sách bộ nhớ riêng ở lớp ứng dụng.

Giới hạn hàng đợi cũng chỉ bao phủ công việc **đang chờ trong hàng**. Các công việc đã được lấy ra và đang xử lý, dữ liệu bên tạo đã tạo sẵn, cùng các bộ đệm khác đều nằm ngoài số đếm đó.

## 4. Khi đạt giới hạn, phương thức thêm quyết định phản ứng

Giả sử có `new LinkedBlockingQueue<>(2)` và hai chỗ đều đã dùng:

| Thao tác | Phản ứng khi chưa có chỗ |
| --- | --- |
| `offer(job)` | Trả `false`, công việc chưa được nhận |
| `add(job)` | Ném `IllegalStateException` |
| `put(job)` | Chờ để thêm; hỗ trợ ngắt luồng qua `InterruptedException` |
| `offer(job, timeout, unit)` | Chờ trong khoảng cho phép; trả `false` nếu hết thời gian mà chưa thêm được; hỗ trợ ngắt luồng |

Giới hạn dung lượng không tự chọn cách xử lý quá tải thay cho chương trình. Dùng `offer` mà bỏ qua `false` có thể làm mất công việc khỏi luồng xử lý. Dùng `put` có thể truyền áp lực ngược (backpressure) đến bên tạo, nhưng đòi hỏi bên xử lý vẫn có cơ hội chạy và giải phóng chỗ.

Nếu constructor mặc định để dung lượng rất lớn, `put` thường không bị chặn bởi giới hạn hàng trong điều kiện bình thường. Viết `put` không tự biến một hàng đợi mặc định thành hàng đợi được giới hạn theo ngân sách ứng dụng.

Phần tử được nhận thành công mới chỉ vào bộ đệm bộ nhớ. Điều đó chưa bảo đảm nó đã được xử lý, được lưu bền vững hoặc tồn tại sau khi tiến trình dừng.

## 5. Ví dụ chạy được: thấy rõ giới hạn và thứ tự FIFO

Lưu thành `LinkedQueueCapacityDemo.java`. Chương trình dùng Java 17 trở lên, chạy một luồng để kết quả quan sát không phụ thuộc thứ tự lập lịch giữa nhiều luồng.

```java
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class LinkedQueueCapacityDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> defaultQueue = new LinkedBlockingQueue<>();
        System.out.println("default remaining: "
                + defaultQueue.remainingCapacity());

        BlockingQueue<String> seededQueue =
                new LinkedBlockingQueue<>(List.of("X", "Y"));
        System.out.println("seeded size: " + seededQueue.size());
        System.out.println("seeded remaining: "
                + seededQueue.remainingCapacity());

        BlockingQueue<String> queue = new LinkedBlockingQueue<>(2);
        System.out.println("offer A: " + queue.offer("A"));
        System.out.println("offer B: " + queue.offer("B"));
        System.out.println("remaining: " + queue.remainingCapacity());
        System.out.println("offer C: " + queue.offer("C"));
        System.out.println("timed offer C: "
                + queue.offer("C", 20, TimeUnit.MILLISECONDS));
        System.out.println("contents: " + queue);

        System.out.println("take: " + queue.take());
        queue.put("C");
        System.out.println("after put C: " + queue);
        System.out.println("take: " + queue.take());
        System.out.println("take: " + queue.take());
        System.out.println("poll empty: " + queue.poll());
        System.out.println("remaining: " + queue.remainingCapacity());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LinkedQueueCapacityDemo.java
java LinkedQueueCapacityDemo
```

Stdout:

```text
default remaining: 2147483647
seeded size: 2
seeded remaining: 2147483645
offer A: true
offer B: true
remaining: 0
offer C: false
timed offer C: false
contents: [A, B]
take: A
after put C: [B, C]
take: B
take: C
poll empty: null
remaining: 2
```

Những điểm được kiểm chứng:

- Hàng đợi khởi tạo từ hai phần tử không bị giới hạn ở hai phần tử: dung lượng còn lại là `Integer.MAX_VALUE - 2`.
- Hàng đợi dung lượng 2 từ chối nhận `C` khi còn giữ `A` và `B`; không có cơ chế tự loại phần tử cũ.
- Trong lần `offer` có thời hạn, không có bên lấy dữ liệu nên kết quả là `false`; ví dụ không khẳng định thời gian thực tế chính xác bằng 20 ms.
- Sau khi lấy `A`, có chỗ để `put C` trở về bình thường. Các lần lấy tiếp theo trả `B` rồi `C`, đúng FIFO.
- `poll()` khi trống trả `null`, trong khi nếu đổi thành `take()` thì luồng có thể chờ dữ liệu mới. Ví dụ chủ động dùng `poll()` ở cuối để không chờ vô hạn.

## 6. Chọn dung lượng từ bộ nhớ, độ trễ và tải dồn

Không có một con số tối ưu áp dụng cho mọi hệ thống. Có thể bắt đầu bằng ba ràng buộc, rồi kiểm tra bằng đo đạc thực tế.

### Bước 1: tính lượng tồn đọng khi có tải dồn

Giả sử bên tạo đưa vào 800 công việc/giây trong 2 giây, còn bên xử lý hoàn thành ổn định 500 công việc/giây. Nếu hàng ban đầu trống, mức tồn đọng tăng xấp xỉ:

```text
(800 - 500) × 2 = 600 công việc
```

Đây là mô hình đơn giản, giả định tốc độ đều và không có yếu tố nghẽn khác. Nó giúp ước lượng cần khoảng bao nhiêu chỗ để hấp thụ toàn bộ đợt dồn, không phải bằng chứng rằng chọn 600 luôn đủ trong thực tế.

Nếu sau đó tốc độ đến giảm xuống 400 công việc/giây, khả năng làm giảm tồn đọng chỉ còn khoảng `500 - 400 = 100` công việc/giây. Làm hết 600 công việc tồn có thể cần thêm khoảng 6 giây, dù bên xử lý vẫn đang làm 500 công việc mỗi giây.

### Bước 2: đối chiếu thời gian chờ có thể chấp nhận

Với tốc độ xử lý tổng hợp 500 công việc/giây, phần tử ở cuối một hàng có khoảng 600 phần tử phía trước có thể phải đợi cỡ `600 / 500 = 1,2` giây trước khi được phục vụ. Ước lượng này bỏ qua chi tiết các công việc đang chạy, độ dài từng công việc và lập lịch; không dùng nó làm bảo đảm thời gian tối đa.

Nếu mục tiêu chỉ cho phép khoảng 200 ms chờ trong hàng, lượng đệm theo cùng mô hình chỉ cỡ `500 × 0,2 = 100` công việc. Yêu cầu “giữ toàn bộ đợt tồn 600” và “mọi công việc chỉ chờ cỡ 200 ms” không đồng thời được đáp ứng bằng cách chọn một dung lượng trong mô hình này. Cần giảm tốc độ tiếp nhận, tăng khả năng xử lý hoặc thay đổi yêu cầu.

### Bước 3: đối chiếu bộ nhớ và cách phản hồi quá tải

Kiểm tra lượng bộ nhớ giữ lại ở mức dung lượng dự kiến, thêm phần dành cho dữ liệu đang xử lý và các thành phần khác. Sau đó quyết định khi đầy sẽ chờ, từ chối hay xử lý theo cơ chế khác. Một hàng nhỏ có thể làm lộ quá tải sớm; một hàng lớn có thể làm bên gọi tưởng hệ thống vẫn tiếp nhận tốt trong khi thời gian chờ đã không còn phù hợp.

Giới hạn hữu hạn giúp kiểm soát phần tồn đọng, nhưng không chữa được tình huống tốc độ đến trung bình luôn lớn hơn tốc độ xử lý. Khi đó, sớm muộn hàng cũng đầy hoặc bên tạo phải chậm lại.

## 7. Điều gì cần đo khi chạy thật?

Theo dõi một nhóm số liệu cùng nhau:

- Số phần tử đang chờ và dung lượng cấu hình.
- Số lần không tiếp nhận được hoặc hết thời gian chờ tiếp nhận.
- Thời gian bên tạo bị giữ ở bước đưa công việc vào hàng.
- Tuổi của công việc trước khi bắt đầu xử lý và thời gian xử lý.
- Tốc độ tiếp nhận, tốc độ hoàn thành, heap và hoạt động thu gom rác.

Một giá trị `size()` đơn lẻ không giải thích được toàn bộ hệ thống. Hàng thường trống có thể là đang dư năng lực hoặc đang bị nghẽn ở bước tạo trước đó. Hàng gần đầy trong thời gian dài có thể báo rằng chỉ tăng dung lượng sẽ kéo dài thời gian chờ.

`remainingCapacity()` là quan sát tại một thời điểm, không đặt chỗ trước cho luồng gọi. Đừng kiểm tra nó lớn hơn 0 rồi giả định `add` chắc chắn thành công: một luồng khác có thể thêm phần tử vào giữa hai bước. Hãy dựa vào kết quả của thao tác thêm phù hợp.

FIFO cũng chỉ nói về thứ tự phần tử được lấy từ hàng. Nếu nhiều luồng xử lý đồng thời, công việc lấy ra trước vẫn có thể hoàn thành sau công việc khác.

## 8. Liên hệ với `ThreadPoolExecutor`: dung lượng ảnh hưởng cả cách mở rộng nhóm luồng

Khi dùng `LinkedBlockingQueue` làm hàng chờ cho `ThreadPoolExecutor`, lựa chọn dung lượng có thêm tác động: sau khi đã đủ số luồng lõi (`corePoolSize`), executor ưu tiên đưa công việc vào hàng trước khi tạo thêm luồng vượt mức lõi. Nếu hàng mặc định luôn còn khả năng tiếp nhận trong phạm vi vận hành, tăng `maximumPoolSize` không làm nhóm tự mở rộng chỉ vì các luồng lõi đang bận.

Với hàng hữu hạn, khi không thể xếp thêm, executor mới có thể tạo thêm luồng tới mức tối đa; khi cả khả năng tạo luồng và tiếp nhận đều hết, chính sách từ chối xử lý được áp dụng. Cơ chế này được mô tả trong [Java SE `ThreadPoolExecutor`, phần Queuing](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Không suy ra rằng truyền một `BlockingQueue` vào executor làm `execute()` tự gọi `put()` để đợi chỗ. Chọn dung lượng cho executor phải đi cùng số luồng và chính sách từ chối. Tác vụ bị từ chối do quá tải cũng cần được phân biệt với việc executor đã ngừng nhận tác vụ. Phần này giải thích tác động của dung lượng; cấu hình toàn bộ vòng đời executor là một chủ đề riêng.

## 9. Nút liên kết không bảo đảm luôn nhanh hơn hàng đợi mảng

`LinkedBlockingQueue` tạo nút theo dữ liệu được thêm, nên chi phí cấp phát và thu gom rác có thể đáng kể. `ArrayBlockingQueue` dùng vùng chứa mảng với dung lượng cố định, là một lựa chọn khác khi muốn vùng chứa được xác định rõ ngay từ đầu.

Không chọn chỉ từ nhận xét “danh sách liên kết nhanh hơn mảng”. Kết quả phụ thuộc số bên tạo, số bên xử lý, mức tranh chấp, kích thước dữ liệu, dung lượng hàng và cấu hình JVM. Với yêu cầu hiệu năng, đo trên tải đại diện sau khi đã xác định đúng chính sách dung lượng. Cấu trúc bên trong không thay thế yêu cầu về thời gian chờ và bộ nhớ.

## 10. Các lỗi cần tránh và tự kiểm tra

| Lỗi | Hệ quả hoặc cách sửa |
| --- | --- |
| Dùng constructor mặc định rồi cho rằng đã giới hạn theo bộ nhớ | Đặt dung lượng theo ngân sách và kiểm tra kích thước dữ liệu |
| Nghĩ constructor từ collection dùng kích thước collection làm trần | Tạo rõ dung lượng nếu cần trần nhỏ |
| Tăng dung lượng để xử lý quá tải kéo dài | Tồn đọng và độ trễ tăng; cần thay đổi tiếp nhận hoặc năng lực xử lý |
| Bỏ qua `offer` trả `false` | Công việc chưa được nhận nhưng bên gọi có thể hiểu nhầm là thành công |
| Gọi `put` khi không còn luồng nào có thể lấy dữ liệu | Có thể chờ không có tiến triển; kiểm tra cách phân bổ luồng |
| Bắt `InterruptedException` rồi lờ đi yêu cầu dừng | Truyền ngoại lệ ra lớp quyết định hoặc khôi phục cờ ngắt và thoát theo chính sách |
| Coi hàng đợi bộ nhớ như nơi lưu trữ bền vững | Công việc có thể mất khi tiến trình dừng; cần cơ chế khác nếu yêu cầu phải lưu bền |

Tự trả lời trước khi chọn `new LinkedBlockingQueue<>(capacity)`:

1. Một phần tử giữ lại bao nhiêu dữ liệu, và kích thước có thể tăng đột biến không?
2. Ở tải đại diện, phần tử chờ bao lâu trước khi được xử lý?
3. Đợt tải dồn cần hấp thụ dài bao lâu, sau đó có đủ tốc độ để làm hết phần tồn không?
4. Khi hàng đầy, bên tạo được phép chờ đến mức nào và công việc chưa nhận sẽ được xử lý ra sao?
5. Giới hạn này đã bao phủ những nguồn giữ dữ liệu nào, và còn dữ liệu đang xử lý ngoài hàng hay không?

Một dung lượng có ý nghĩa phải gắn với các câu trả lời đó và được kiểm tra lại bằng số liệu vận hành, thay vì giữ constructor mặc định theo thói quen.
