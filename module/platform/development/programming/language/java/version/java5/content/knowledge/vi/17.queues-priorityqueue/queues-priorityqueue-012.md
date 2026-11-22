# Ứng dụng xử lý công việc theo mức ưu tiên

## 1. Khi thứ tự đến chưa đủ để quyết định thứ tự xử lý

Giả sử một ứng dụng đang có nhiều việc chờ thực hiện:

- Tạo báo cáo định kỳ.
- Cập nhật chỉ mục tìm kiếm.
- Gửi cảnh báo cần xử lý sớm.

Nếu chỉ dùng FIFO, việc đến trước luôn được lấy trước. Điều này hợp lý khi các công việc có tầm quan trọng tương đương, nhưng có thể khiến cảnh báo khẩn phải chờ sau nhiều báo cáo thông thường.

Hàng đợi ưu tiên giải quyết câu hỏi: **trong những công việc đang chờ, nên chọn việc nào tiếp theo?**

`PriorityQueue` phù hợp để biểu diễn tập công việc chờ theo một quy tắc so sánh. Bản thân nó không thực hiện công việc, không tạo luồng, không đặt lịch theo giờ và không ngắt công việc đang chạy. Một vòng xử lý bên ngoài lấy phần tử bằng `poll()`, rồi gọi hành động tương ứng.

Bài xây dựng một ví dụ đầy đủ chạy trong một luồng bằng Java 17+, với các quy tắc còn áp dụng hiện nay.

## 2. Đặt hợp đồng ưu tiên trước khi viết comparator

Ví dụ dùng hợp đồng sau:

| Thuộc tính | Quy tắc |
|---|---|
| `priority` | Số nguyên từ 1 đến 5; số lớn hơn được xử lý trước |
| `arrival` | Số thứ tự tiếp nhận; nhỏ hơn đứng trước khi cùng mức ưu tiên |
| `id` | Nhãn công việc, không được null hoặc trắng |
| `action` | Hành động cần chạy, không được null |
| Khi công việc ném `RuntimeException` | Ghi nhận thất bại rồi tiếp tục việc khác |
| Khi không còn việc chờ | Vòng xử lý hiện tại kết thúc |

Cần viết rõ “số lớn hơn đứng trước” vì `PriorityQueue` chọn phần tử nhỏ nhất **theo comparator** làm đầu. Nếu chỉ dùng thứ tự tăng dần của số ưu tiên, công việc mức 1 sẽ đứng trước mức 5, trái với hợp đồng vừa đặt.

Comparator tương ứng:

```java
Comparator.comparingInt(Job::priority)
        .reversed()
        .thenComparingLong(Job::arrival);
```

Cách đọc:

1. Đảo riêng thứ tự của `priority` để mức 5 đứng trước mức 1.
2. Khi mức ưu tiên bằng nhau, so `arrival` tăng dần.

Vị trí của `reversed()` có ý nghĩa. Nếu đảo toàn bộ comparator sau khi đã thêm tiêu chí phụ, thứ tự đến cũng bị đảo; như vậy công việc cùng ưu tiên có thể thành đến sau xử lý trước.

`PriorityQueue` không tự bảo đảm FIFO cho các phần tử được comparator xem là ngang nhau. Tiêu chí phụ ở đây là quy tắc ứng dụng chủ động thêm, phù hợp với [hợp đồng PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html).

### Không so sánh bằng phép trừ tùy tiện

Tránh viết comparator tổng quát kiểu:

```java
// Cách viết dễ gây tràn số với miền giá trị rộng:
// (left, right) -> right.priority() - left.priority()
```

Dùng `comparingInt`, `Integer.compare` và các phương thức ghép comparator giúp biểu đạt ý định mà không dựa vào phép trừ có thể tràn số. Ví dụ tuy giới hạn 1..5, cách viết comparator vẫn nên rõ ràng và dễ bảo trì.

## 3. Tách ba trách nhiệm

Một bộ xử lý đơn giản có ba phần:

```text
Tiếp nhận
    → kiểm tra dữ liệu
    → gán số thứ tự đến
    → thêm vào tập việc chờ

Chọn việc
    → poll lấy công việc ưu tiên kế tiếp
    → công việc đó rời hàng đợi

Thực hiện
    → gọi hành động
    → ghi nhận thành công hoặc thất bại
    → quay lại chọn việc tiếp theo
```

Phải phân biệt **việc đã được lấy ra** với **việc đã hoàn thành**. `poll()` thành công chỉ nói rằng có một công việc được lấy khỏi hàng đợi. Hành động phía sau vẫn có thể thất bại.

Trong ví dụ, công việc dùng record chứa dữ liệu so sánh không thay đổi sau khi tạo. Điều này giúp giữ quy tắc ưu tiên nhất quán trong thời gian công việc nằm ở hàng đợi.

## 4. Chương trình đầy đủ

Lưu tệp `PriorityWorkDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityWorkDemo {
    record Job(String id, int priority, long arrival, Runnable action) {
    }

    static final class Scheduler {
        private static final Comparator<Job> ORDER =
                Comparator.comparingInt(Job::priority)
                        .reversed()
                        .thenComparingLong(Job::arrival);

        private final Queue<Job> waiting = new PriorityQueue<>(ORDER);
        private long nextArrival;
        private int succeeded;
        private int failed;

        void submit(String id, int priority, Runnable action) {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(action, "action");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            if (priority < 1 || priority > 5) {
                throw new IllegalArgumentException("priority must be in 1..5");
            }
            waiting.offer(new Job(id, priority, nextArrival++, action));
        }

        List<String> waitingOrder() {
            return waiting.stream().sorted(ORDER).map(Job::id).toList();
        }

        boolean runNext() {
            Job job = waiting.poll();
            if (job == null) {
                return false;
            }
            System.out.println("START " + job.id());
            try {
                job.action().run();
                succeeded++;
                System.out.println("DONE " + job.id());
            } catch (RuntimeException ex) {
                failed++;
                System.out.println("FAIL " + job.id()
                        + ": " + ex.getClass().getSimpleName());
            }
            return true;
        }

        void runUntilEmpty() {
            while (runNext()) {
                // Continue with the next waiting job.
            }
        }

        String summary() {
            return "success=" + succeeded + ", failed=" + failed
                    + ", waiting=" + waiting.size();
        }
    }

    public static void main(String[] args) {
        Scheduler batch = new Scheduler();
        batch.submit("report", 1, () -> System.out.println("build report"));
        batch.submit("alert-A", 5, () -> System.out.println("notify A"));
        batch.submit("alert-B", 5, () -> {
            throw new IllegalStateException("demo failure");
        });
        batch.submit("index", 3, () -> System.out.println("update index"));

        System.out.println("waiting=" + batch.waitingOrder());
        batch.runUntilEmpty();
        System.out.println(batch.summary());
        System.out.println("run empty=" + batch.runNext());

        System.out.println("-- arrival during execution --");
        Scheduler live = new Scheduler();
        live.submit("current", 2, () -> {
            System.out.println("current step 1");
            live.submit("new-urgent", 5,
                    () -> System.out.println("handle urgent"));
            System.out.println("current step 2");
        });
        live.submit("waiting-low", 1,
                () -> System.out.println("handle low"));
        live.runUntilEmpty();
        System.out.println(live.summary());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror PriorityWorkDemo.java
java PriorityWorkDemo
```

Stdout:

```text
waiting=[alert-A, alert-B, index, report]
START alert-A
notify A
DONE alert-A
START alert-B
FAIL alert-B: IllegalStateException
START index
update index
DONE index
START report
build report
DONE report
success=3, failed=1, waiting=0
run empty=false
-- arrival during execution --
START current
current step 1
current step 2
DONE current
START new-urgent
handle urgent
DONE new-urgent
START waiting-low
handle low
DONE waiting-low
success=3, failed=0, waiting=0
```

### Các điểm cần đọc trong mã

- `waiting` được khai báo qua interface `Queue<Job>`; đối tượng thực tế là `PriorityQueue` với comparator đã chọn.
- `submit` kiểm tra dữ liệu trước khi thêm. Các đầu vào sai không trở thành công việc chờ.
- `nextArrival` cấp thứ tự tiếp nhận tại một điểm duy nhất trong mô hình một luồng.
- `waitingOrder` tạo một danh sách đã sắp để xem lịch ưu tiên hiện tại, không tiêu thụ hàng đợi.
- `runNext` lấy đúng một việc, thực hiện nó và trả true nếu đã lấy được việc, kể cả khi hành động thất bại.
- `runUntilEmpty` tiếp tục chừng nào còn lấy được việc.
- `summary` tách số việc thành công, thất bại và còn chờ.

Trong `runUntilEmpty`, true không có nghĩa hành động thành công. Nó chỉ nói rằng một công việc đã được xử lý ở lượt đó. Nếu trả false ngay khi một hành động thất bại, vòng xử lý sẽ dừng và bỏ lại các công việc khác; ví dụ chủ động tránh sự nhầm lẫn đó.

## 5. Phân tích lượt xử lý theo ưu tiên và thứ tự đến

Bốn việc ban đầu được tiếp nhận theo thứ tự:

| Thứ tự tiếp nhận | Công việc | Mức ưu tiên |
|---:|---|---:|
| 0 | report | 1 |
| 1 | alert-A | 5 |
| 2 | alert-B | 5 |
| 3 | index | 3 |

Lịch chọn hiện tại là:

```text
alert-A → alert-B → index → report
```

Giải thích:

1. Hai cảnh báo mức 5 đứng trước.
2. `alert-A` được nhận trước `alert-B`, nên tiêu chí `arrival` đặt nó trước.
3. `index` mức 3 đứng trước `report` mức 1.
4. Thứ tự tiếp nhận không bị bỏ qua hoàn toàn; nó được dùng khi tiêu chí ưu tiên chính không phân biệt được hai công việc.

Lệnh `waitingOrder()` dùng `stream().sorted(ORDER)`, vì vòng duyệt trực tiếp hoặc `toString()` của `PriorityQueue` không bảo đảm hiển thị theo thứ tự lấy. Đây là một bản xem đã sắp, không phải ảnh chụp bố cục heap để suy ra lịch.

Sau đó, `runNext()` dùng `poll()` để thực sự lấy việc theo chính sách ưu tiên. Danh sách xem trước và việc chọn đầu có cùng comparator, nên không tạo ra hai cách hiểu thứ tự khác nhau trong thí nghiệm này.

### Công việc thất bại vẫn đã rời hàng đợi

`alert-B` cố ý ném `IllegalStateException`. Bộ xử lý:

- Ghi nhận một thất bại.
- Không tăng bộ đếm thành công.
- Không tự thêm lại công việc.
- Tiếp tục xử lý `index` và `report`.

Kết quả là 3 thành công, 1 thất bại và không còn việc chờ.

Việc bắt `RuntimeException` thể hiện chính sách của thí nghiệm. Nó không bắt mọi `Error` và không phải một cơ chế phục hồi tổng quát cho mọi lỗi hệ thống.

Trong ứng dụng thật, cần ghi thêm thông tin phù hợp như mã công việc, nguyên nhân lỗi và trạng thái xử lý. Dòng stdout trong bài chỉ giúp quan sát luồng thực thi; nó không thay thế một cơ chế lưu trạng thái bền vững.

## 6. Công việc khẩn xuất hiện khi một việc khác đang chạy

Phần thứ hai của chương trình quan sát một giới hạn quan trọng.

Ban đầu có:

- `current` mức 2.
- `waiting-low` mức 1.

Khi `current` chạy, hành động của nó đưa thêm `new-urgent` mức 5 vào cùng bộ xử lý. Tuy nhiên, stdout vẫn có:

```text
current step 1
current step 2
DONE current
START new-urgent
```

Việc mới khẩn hơn nhưng không cắt ngang hành động đang chạy. Đây là mô hình **không ngắt công việc đang thực hiện**: mức ưu tiên được áp dụng khi chọn công việc tiếp theo từ tập đang chờ.

Trong ví dụ:

1. `current` đã được `poll` khỏi hàng đợi trước khi hành động bắt đầu.
2. Việc thêm `new-urgent` không tự gọi lại vòng chọn việc.
3. Hành động `current` chạy đến khi trả về.
4. Lượt `poll` tiếp theo chọn `new-urgent`, vì nó có ưu tiên cao hơn `waiting-low`.

Không cần tạo nhiều luồng để quan sát giới hạn này. Việc thêm công việc ngay trong hành động là đủ chứng minh ranh giới giữa **thứ tự chờ** và **quyền chạy hiện tại**.

Nếu yêu cầu nghiệp vụ cần phản ứng nhanh hơn một hành động rất dài, có thể phải chia hành động thành các đơn vị nhỏ có điểm nhường hoặc thiết kế cơ chế hủy/phối hợp riêng. `PriorityQueue` không tự cung cấp quyền ngắt thực thi.

Mức ưu tiên công việc cũng không phải `Thread` priority. Thay số trong `Job.priority` không thay bộ lập lịch luồng của JVM.

## 7. Những quyết định cần có khi phát triển thành ứng dụng thực tế

### Đổi ưu tiên của việc đang chờ

Không sửa trực tiếp dữ liệu quyết định thứ tự rồi kỳ vọng heap tự sắp lại. Ví dụ giữ `Job` bất biến ở các trường ưu tiên và thứ tự đến để tránh vấn đề đó.

Nếu cần tăng ưu tiên, thiết kế thao tác cập nhật rõ ràng, chẳng hạn tìm và loại bỏ bản đang chờ rồi thêm một bản mới. Cần quyết định:

- Bản cập nhật có giữ số thứ tự đến cũ hay nhận thứ tự mới?
- Việc đã được lấy ra để chạy thì còn được cập nhật không?
- Một mã công việc có được xuất hiện nhiều lần không?

Những câu hỏi này thuộc hợp đồng của bộ xử lý. `PriorityQueue` không tự coi `id` là khóa duy nhất.

### Thử lại sau lỗi

Ví dụ không tự thử lại. Nếu thêm cơ chế thử lại, cần giới hạn số lần và xác định chính sách ưu tiên của lần thử tiếp theo.

Không đưa lại vô hạn một công việc lỗi ở mức ưu tiên cao nhất: nó có thể liên tục được chọn và cản mọi công việc khác. Nếu cần chờ trước khi thử lại, chỉ có `PriorityQueue` chưa đủ để tự đánh thức hoặc bảo đảm thời điểm thực hiện.

Công việc cũng có thể đã tạo một phần tác dụng trước khi ném ngoại lệ. Vì vậy, thử lại phải xét việc thực hiện lặp có gây tác dụng trùng hay không; không suy ra “đã ném lỗi thì chưa làm gì”.

### Hạn chế việc ưu tiên thấp bị chờ mãi

Nếu công việc ưu tiên cao liên tục xuất hiện, việc ưu tiên thấp có thể không bao giờ được chọn. Đó là nguy cơ **bị trì hoãn vô thời hạn (starvation)** trong chính sách ưu tiên tuyệt đối.

Tùy nhu cầu, có thể chọn:

- Tăng mức phục vụ cho việc đã chờ lâu theo một quy trình cập nhật hợp lệ.
- Giới hạn số việc ưu tiên cao được xử lý liên tiếp trước khi phục vụ nhóm khác.
- Chia nhiều hàng đợi và luân phiên phục vụ theo tỷ lệ.

Không nhét một phép đọc thời gian thay đổi liên tục vào comparator rồi coi như heap sẽ tự đánh giá lại mọi phần tử. Nếu quy tắc ưu tiên thay đổi theo thời gian, cần thiết kế cách cập nhật cấu trúc tương ứng.

### Giới hạn lượng việc chờ

`PriorityQueue` tăng sức chứa khi cần; một con số sức chứa ban đầu không đặt giới hạn số việc chờ. Nếu bộ tiếp nhận nhanh hơn bộ xử lý trong thời gian dài, cần chính sách nhận thêm, từ chối hoặc trì hoãn yêu cầu.

Ví dụ không triển khai giới hạn đó. Việc chọn chính sách phải dựa vào yêu cầu ứng dụng; không dùng `new PriorityQueue<>(100)` rồi hiểu rằng việc thứ 101 chắc chắn bị từ chối.

## 8. Khi có nhiều luồng

`Scheduler` trong chương trình là mô hình một luồng. Các thành phần như `nextArrival`, bộ đếm và `waiting` không được đồng bộ hóa cho nhiều bên truy cập đồng thời.

Không thể cho nhiều luồng gọi `submit`/`runNext` rồi kết luận an toàn chỉ vì cấu trúc đang biểu diễn công việc chờ.

Một hàng đợi như [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html) cung cấp các thao tác hàng đợi an toàn luồng và khả năng chờ lấy việc, nhưng không tự giải quyết mọi vấn đề của bộ xử lý:

- Số thứ tự cần được cấp theo chính sách đồng thời rõ ràng.
- Phần tử ngang mức vẫn cần tiêu chí phụ nếu muốn phân định.
- Bộ đếm, trạng thái thất bại và thao tác hủy cần cơ chế phối hợp riêng.
- Có nhiều bên thực hiện thì thứ tự hoàn thành không bắt buộc trùng thứ tự lấy.
- Hàng đợi ưu tiên này vẫn không phải một giới hạn cứng cho lượng việc chờ.

Trong mô hình nhiều luồng, một việc ưu tiên thấp đã bắt đầu vẫn có thể hoàn thành trước một việc ưu tiên cao lấy sau đó. Phải nói rõ đang muốn bảo đảm **thứ tự tiếp nhận**, **thứ tự chọn việc**, **thứ tự bắt đầu** hay **thứ tự hoàn thành**.

Không dùng kết quả thứ tự hoàn thành của một chương trình nhiều luồng làm bằng chứng trực tiếp rằng comparator của hàng đợi sai.

## 9. Kiểm tra hợp đồng bằng các tình huống nhỏ

| Tình huống | Điều cần xác minh |
|---|---|
| Có việc mức 1 và mức 5 cùng chờ | Mức 5 được chọn trước |
| Hai việc cùng mức ưu tiên | Tiêu chí thứ tự đến được giữ |
| Hàng đợi rỗng | `runNext()` trả false, không gọi hành động |
| Một hành động ném RuntimeException | Thất bại được ghi nhận; việc khác tiếp tục |
| Việc mức 5 được thêm trong lúc việc mức 2 đang chạy | Nó được chọn ở lượt sau, không ngắt hành động hiện tại |
| Mức ưu tiên 0 hoặc 6 | Bị từ chối trước khi thêm |
| Id trắng hoặc hành động null | Bị từ chối theo hợp đồng đầu vào |

Chương trình đã thể hiện năm tình huống đầu. Các kiểm tra đầu vào nằm ngay trong `submit`, trước khi thêm vào `waiting`.

Với bài tập mở rộng, hãy tự viết thêm lời gọi cung cấp ưu tiên không hợp lệ, xác nhận có ngoại lệ và không có việc mới trong `waitingOrder()`. Không đổi comparator để “xếp được” dữ liệu vốn bị hợp đồng cấm.

## 10. Thực hành điều chỉnh chính sách

### Bài 1: số nhỏ biểu thị khẩn hơn

Giả sử quy ước mới là mức 1 khẩn nhất. Cần sửa gì?

**Đáp án:** Bỏ `reversed()` ở tiêu chí `priority`, giữ `thenComparingLong(Job::arrival)`. Cập nhật lại mô tả và kết quả mong đợi theo quy ước mới.

### Bài 2: công việc cùng ưu tiên không cần FIFO

Có thể chỉ so sánh `priority` không?

**Đáp án:** Có nếu nghiệp vụ chấp nhận thứ tự hòa không xác định. Khi đó không viết kiểm thử đòi các mã công việc ngang mức xuất hiện theo lịch sử thêm.

### Bài 3: thấy FAIL rồi muốn dừng toàn bộ

Cần sửa hành vi hay chỉ sửa tên phương thức?

**Đáp án:** Đây là thay đổi chính sách xử lý lỗi. Cần quy định rõ việc còn chờ có bị giữ lại, hủy hay lưu để tiếp tục. Không đổi ý nghĩa của boolean `runNext` một cách âm thầm.

### Bài 4: cần xử lý lại công việc thất bại

Có chỉ cần `waiting.offer(job)` trong catch không?

**Đáp án:** Chưa đủ. Cần giới hạn thử lại, xác định thời gian chờ, mức ưu tiên của lần thử, cách đếm trạng thái và khả năng hành động trước đó đã tạo tác dụng một phần.

Khi ứng dụng xử lý theo mức ưu tiên, hãy xác định **quy tắc chọn việc → cách phân định hòa → thời điểm việc rời hàng đợi → hợp đồng lỗi → giới hạn chờ và đồng thời**. `PriorityQueue` là thành phần chọn công việc kế tiếp; bộ xử lý xung quanh mới quyết định cách thực hiện và quản lý kết quả.
