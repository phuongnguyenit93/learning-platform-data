# Tách tác vụ khỏi cơ chế thực thi bằng Executor

## Khái niệm: mô tả việc cần làm khác với quyết định cách chạy

Một tác vụ trả lời câu hỏi **“cần làm việc gì?”**. Cơ chế thực thi trả lời **“ai chạy, trên luồng nào, khi nào và theo chính sách nào?”**.

Trong Java:

- `Runnable` biểu diễn một thao tác không trả kết quả trực tiếp.
- `Executor` nhận một `Runnable` và thực thi nó theo chính sách của bộ thực thi.

API tối thiểu của Executor là:

```java
void execute(Runnable command);
```

Thay vì để mỗi tác vụ tự tạo luồng, mã gửi việc có thể giao tác vụ cho một đối tượng Executor. Chính sách dùng luồng được đặt ở nơi khác.

Sự tách biệt này vẫn là nền tảng hiện hành của thư viện đồng thời Java. Ví dụ trong bài chạy trên JDK 17 trở lên, không cần thư viện ngoài.

Định nghĩa và mục tiêu thiết kế có tại [Executor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html).

## Trước khi tách: nơi gửi việc bị gắn chặt với luồng

Ví dụ minh họa:

```java
// Mảnh minh họa trong một phương thức:
new Thread(task).start();
```

Cách viết này có thể phù hợp với một tình huống nhỏ, nhưng nơi gửi tác vụ đồng thời đã quyết định:

- Tạo một Thread mới.
- Dùng chính luồng đó cho tác vụ.
- Khởi động ngay theo cơ chế Thread.
- Tự chịu trách nhiệm tổ chức vòng đời các luồng được tạo.

Nếu nhiều phần trong chương trình tự làm như vậy, việc thay đổi cách thực thi sẽ phải chạm vào nhiều nơi.

Sau khi tách:

```java
// Mảnh minh họa trong phương thức có executor và task:
executor.execute(task);
```

Nơi gửi chỉ phụ thuộc hợp đồng Executor. Thành phần lắp ghép ứng dụng có thể cung cấp một cách chạy phù hợp.

Điểm cải thiện không phải chỉ là đổi tên một lệnh gọi. Nó là chuyển quyền lựa chọn chính sách thực thi ra khỏi phần mô tả công việc và khỏi nhiều nơi gửi việc riêng lẻ.

## Ba vai trò trong một thiết kế nhỏ

| Vai trò | Trách nhiệm |
| --- | --- |
| Tác vụ | Chứa thao tác cần thực hiện và dữ liệu đầu vào cần dùng |
| Nơi gửi tác vụ | Xác định khi nào cần yêu cầu công việc |
| Bộ thực thi | Quyết định cách tổ chức việc chạy theo hợp đồng và cấu hình |

Ví dụ, một tác vụ tính báo cáo không cần tự biết hệ thống đang dùng một luồng làm việc, một nhóm luồng hay cách chạy trực tiếp để kiểm tra đơn vị.

Ngược lại, bộ thực thi không nên phải biết chi tiết nghiệp vụ của từng loại báo cáo chỉ để gọi `run()`.

Điều này giúp thay cơ chế thực thi mà giữ nguyên phần thao tác, nhưng không tự làm tác vụ đúng trong mọi hoàn cảnh đồng thời. Tác vụ vẫn phải tuân thủ hợp đồng về dữ liệu, lỗi và tài nguyên.

## Runnable là công việc, không phải một luồng đã chạy

`Runnable` có phương thức:

```java
void run();
```

Tạo một đối tượng Runnable không tự thực thi nó. Lambda như:

```java
Runnable task = () -> System.out.println("work");
```

chỉ tạo một giá trị có thể được gọi để thực hiện thao tác.

Gọi trực tiếp `task.run()` chạy thao tác trên luồng hiện tại. Giao nó cho Executor cho phép bộ thực thi quyết định cách gọi.

Runnable cũng không bắt buộc phải chỉ dùng một lần. Nhưng nếu cùng một đối tượng Runnable bị chạy nhiều lần hoặc đồng thời, trạng thái mà nó dùng phải phù hợp với cách sử dụng đó. Chứa dữ liệu có thể thay đổi bên trong một task không làm dữ liệu ấy tự an toàn luồng.

Hợp đồng của thao tác không có kết quả trực tiếp được mô tả tại [Runnable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runnable.html).

## Executor không đồng nghĩa luôn bất đồng bộ

Đây là điểm cần nắm ngay từ đầu: interface Executor **không bắt buộc mọi tác vụ phải chạy trên một luồng khác**.

Một cách triển khai hợp lệ có thể gọi `run()` ngay trong luồng gửi:

```java
Executor direct = Runnable::run;
```

Với cách này, `execute(task)` chỉ trở về sau khi lời gọi `run()` hoàn tất bình thường hoặc ném lỗi ra theo đường gọi trực tiếp.

Một cách triển khai khác có thể dùng luồng làm việc hoặc nhóm luồng. Khi đó tác vụ có thể bắt đầu trước hoặc sau lúc lời gọi `execute` trở về, tùy cơ chế và lịch chạy.

Vì vậy, chỉ nhìn kiểu biến là `Executor` chưa đủ để kết luận:

- Có tạo luồng mới không?
- Tác vụ có chạy đồng thời với bên gửi không?
- Có nhiều tác vụ chạy song song không?
- Bên gửi có phải chờ công việc hoàn tất không?

Phải biết chính sách và hợp đồng của đối tượng Executor cụ thể mà ứng dụng cung cấp.

## Chương trình đầy đủ: một tác vụ, hai cơ chế thực thi

Ví dụ dùng cùng một đối tượng `PrintTask`:

1. Chạy thông qua Executor trực tiếp.
2. Chạy qua một ExecutorService có một luồng làm việc.

Tác vụ chỉ chứa một nhãn final và in nhãn đó. Nó không tự tạo Thread hoặc tự quyết định vòng đời của bộ thực thi.

Lưu thành `ExecutorSeparationDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorSeparationDemo {
    static final class PrintTask implements Runnable {
        private final String label;

        PrintTask(String label) {
            this.label = label;
        }

        @Override
        public void run() {
            System.out.println(label);
        }
    }

    static void dispatch(Executor executor, Runnable task) {
        executor.execute(task);
    }

    public static void main(String[] args)
            throws InterruptedException {
        Runnable task = new PrintTask("task");

        Executor direct = Runnable::run;
        System.out.println("direct.before");
        dispatch(direct, task);
        System.out.println("direct.after");

        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            System.out.println("worker.before");
            dispatch(worker, task);
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not terminate");
            }
            System.out.println("worker.after");
        } finally {
            if (!worker.isTerminated()) {
                List<Runnable> neverStarted = worker.shutdownNow();
                System.err.println("cleanup.pending=" + neverStarted.size());
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ExecutorSeparationDemo.java
java ExecutorSeparationDemo
```

Trong lượt chạy bình thường khi tác vụ hoàn tất trước hạn chờ:

```text
direct.before
task
direct.after
worker.before
task
worker.after
```

Hạn năm giây là giới hạn chờ của ví dụ. Nếu bộ thực thi không hoàn tất trong khoảng đó, chương trình báo lỗi thay vì in dòng `worker.after` như thể đã xác nhận hoàn tất. Thời hạn này không phải bảo đảm hiệu năng của Executor.

## Đọc thiết kế qua ví dụ

### PrintTask chỉ mô tả thao tác

`PrintTask.run()` chỉ in nhãn. Nó không gọi `new Thread`, không biết về số luồng làm việc và không tự shutdown tài nguyên chung.

Cùng một đối tượng `task` được chạy hai lần trong ví dụ. Điều này phù hợp vì phần trạng thái của task chỉ là nhãn bất biến, và hai lượt được tổ chức nối tiếp.

Nếu đổi nó thành một tác vụ chứa bộ đếm hoặc trạng thái có thể thay đổi, cần xem lại điều kiện chạy nhiều lần hoặc đồng thời. Việc dùng Executor không tự sửa các tranh chấp bên trong tác vụ.

### dispatch chỉ phụ thuộc Executor

```java
static void dispatch(Executor executor, Runnable task) {
    executor.execute(task);
}
```

Phương thức không cần biết đối tượng nhận là Executor trực tiếp hay ExecutorService có luồng riêng.

Đây là điểm nối của thiết kế: cùng hợp đồng gửi việc, khác chính sách thực thi được cung cấp từ bên ngoài.

### Nhánh direct chạy trong đường gọi hiện tại

`Runnable::run` khiến bộ thực thi gọi task trực tiếp. Vì vậy dòng `task` nằm giữa `direct.before` và `direct.after`.

Điều này kiểm chứng rằng interface không tự yêu cầu phải có một bước chuyển luồng.

Nếu task ném một ngoại lệ không được kiểm tra trong cách triển khai trực tiếp này, ngoại lệ có thể đi ngược theo chính ngăn xếp của bên gọi. Đừng viết nơi gửi với giả định rằng gọi qua Executor luôn cách ly lỗi trên luồng khác.

### Nhánh worker xác nhận hoàn tất một cách rõ ràng

`Executors.newSingleThreadExecutor()` tạo một bộ thực thi có một luồng làm việc. Ví dụ đưa tác vụ vào, gọi shutdown để kết thúc giai đoạn nhận việc, rồi đợi nó hoàn tất.

Dòng `worker.after` được in **sau khi** `awaitTermination` báo hoàn tất, không phải sau một lời gọi execute đơn lẻ.

Nếu bỏ thao tác đợi, thứ tự giữa một dòng in ở bên gửi sau execute và dòng in trong task không nên được mặc định. Task có thể chạy trước hoặc sau dòng đó theo lịch thực tế.

## execute không trả kết quả và không đại diện cho việc đã hoàn tất

`Executor.execute` trả `void`. Nó không trả một đối tượng có thể dùng trực tiếp để:

- Lấy kết quả tính toán.
- Chờ một task cụ thể kết thúc.
- Hủy một task cụ thể.
- Đọc lỗi mà task lưu lại.

Một lời gọi execute đã trở về không có nghĩa công việc đã thành công. Với cách chạy trực tiếp, nó có thể đã chạy xong; với cách chạy khác, nó có thể đang đợi hoặc đang chạy.

Nếu ứng dụng cần theo dõi một tác vụ hoặc lấy giá trị trả về, `ExecutorService` và các API như `submit`/`Future` cung cấp hợp đồng phong phú hơn. Đó là một lớp nhu cầu bổ sung, không làm execute tự có giá trị kết quả.

Không dùng một `sleep` tùy ý để thay cho API chờ hoàn tất. Chờ đủ lâu theo cảm giác không tương đương việc đã xác nhận tác vụ kết thúc.

## Executor và ExecutorService có ranh giới khác nhau

| API | Điều nó cung cấp |
| --- | --- |
| `Executor` | Khả năng giao một Runnable để thực thi |
| `ExecutorService` | Thêm quản lý vòng đời, gửi việc có kết quả theo dõi và các thao tác điều phối |
| `ScheduledExecutorService` | Thêm khả năng lên lịch theo hợp đồng của nó |

Một thành phần chỉ cần gửi việc nên nhận giao diện tối thiểu phù hợp. Không nhất thiết cấp cho mọi tác vụ quyền đóng bộ thực thi chung.

Trong ví dụ:

- `dispatch` nhận `Executor`.
- `main` tạo và sở hữu `ExecutorService`.
- `main` chịu trách nhiệm kết thúc nó.

Nếu ứng dụng cung cấp một bộ thực thi dùng chung qua constructor, thành phần nhận thường không nên tự shutdown nó chỉ vì một lời gọi của riêng mình xong. Quyền quản lý vòng đời phải được xác định ở nơi lắp ghép.

Xem các thao tác bổ sung tại [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).

## Vòng đời trong ví dụ không thuộc về tác vụ

`shutdown()` ngừng nhận tác vụ mới theo hợp đồng của service và cho các tác vụ đã nhận tiếp tục hoàn tất. Nó không tự chờ cho mọi tác vụ kết thúc.

`awaitTermination` mới là bước đợi sau yêu cầu shutdown. Kết quả boolean cho biết service đã kết thúc trong thời gian chờ hay chưa.

Khối finally yêu cầu dừng khẩn hơn nếu ví dụ chưa kết thúc. `shutdownNow()` cố gắng dừng các tác vụ đang chạy và trả những tác vụ chưa bắt đầu; nó không cưỡng chế mọi mã đang chạy phải kết thúc ngay lập tức.

Vì task của ví dụ rất ngắn và không giữ tài nguyên ngoài, lượt chạy bình thường không đi vào nhánh in thông tin dọn dẹp. Với tác vụ thật, cần có giao thức hủy và xử lý interruption phù hợp.

Không coi ví dụ nhỏ này là một chính sách shutdown hoàn chỉnh cho mọi hệ thống; mục đích là cho thấy thành phần sở hữu bộ thực thi quản lý vòng đời, còn Runnable giữ phần công việc.

## Gửi việc có thể bị từ chối

Executor có thể không chấp nhận một tác vụ, chẳng hạn khi bộ thực thi đã ngừng nhận việc hoặc chính sách tài nguyên không cho phép nhận thêm.

`RejectedExecutionException` biểu thị tình huống không thể chấp nhận tác vụ để thực thi theo cơ chế nêu trong API. Xem [RejectedExecutionException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionException.html).

Cần phân biệt:

- **Lỗi nhận việc:** task chưa được nhận theo đường mong đợi.
- **Lỗi thực thi:** task đã bắt đầu và phần thân thất bại.
- **Lỗi lấy kết quả:** tùy API theo dõi mà bên gọi đang dùng.

Không bắt một ngoại lệ quanh execute rồi cho rằng đã thu được mọi lỗi phát sinh trên luồng làm việc sau đó.

Chính sách khi bị từ chối phải dựa trên yêu cầu ứng dụng. Không tự lặp lại một công việc có tác động bên ngoài mà chưa xác định nó đã được thực hiện hay chưa và việc lặp có hợp lệ không.

## Quan hệ bộ nhớ khi giao tác vụ

Hợp đồng Executor cung cấp quan hệ happens-before từ các hành động ở luồng gửi trước khi giao Runnable tới lúc tác vụ bắt đầu thực thi, có thể ở luồng khác.

Điều này giúp chuyển dữ liệu được chuẩn bị **trước khi gửi** vào tác vụ.

Nhưng nó không có nghĩa mọi sửa đổi **sau khi gửi** đều tự được đồng bộ hóa với task. Nếu task và bên gửi cùng truy cập một đối tượng có thể thay đổi, vẫn cần mô hình chia sẻ phù hợp.

Ví dụ, một biến cục bộ được lambda bắt giữ có thể là một tham chiếu effectively final, nhưng đối tượng được tham chiếu vẫn có thể thay đổi. Quy tắc capture không tự tạo tính bất biến sâu.

Cũng không suy ra execute có một bảo đảm chuyển kết quả theo chiều ngược lại cho việc đọc tùy ý ở phía gửi. Nếu cần nhận kết quả, hãy sử dụng cơ chế hoàn tất/chuyển giao phù hợp.

## Thay chính sách thực thi mà giữ nguyên tác vụ

Một thành phần có thể nhận Executor qua constructor:

```java
// Mảnh khai báo minh họa:
final class JobDispatcher {
    private final Executor executor;

    JobDispatcher(Executor executor) {
        this.executor = java.util.Objects.requireNonNull(executor);
    }

    void dispatch(Runnable task) {
        executor.execute(task);
    }
}
```

Mảnh này cần import Executor nếu đặt trong tệp riêng.

Nơi lắp ghép có thể cung cấp bộ chạy trực tiếp cho một loại kiểm tra, hoặc bộ chạy có luồng làm việc cho môi trường ứng dụng. JobDispatcher không cần tự tạo nhóm luồng.

Tuy nhiên, thay đổi chính sách có thể thay đổi:

- Task có chạy đồng thời với bên gửi hay không.
- Thứ tự hoàn tất giữa các task.
- Nơi xuất hiện ngoại lệ.
- Khả năng sử dụng dữ liệu gắn với một luồng.
- Nhu cầu bảo vệ trạng thái chia sẻ.

“Tách biệt” giúp cô lập quyết định, không làm các quyết định có thể đổi mà bỏ qua mọi hệ quả về hành vi.

## Kiểm tra với bộ chạy trực tiếp có ích nhưng có giới hạn

Bộ chạy trực tiếp có thể giúp kiểm tra riêng thao tác nghiệp vụ hoặc việc một thành phần có gửi đúng công việc hay không, mà không cần điều phối nhiều luồng.

Nhưng nếu chỉ kiểm tra bằng `Runnable::run`, bạn chưa kiểm chứng:

- Tranh chấp giữa các tác vụ.
- Thứ tự hoàn tất không cố định.
- Chờ/hủy trên luồng khác.
- Vấn đề phát sinh khi dữ liệu bị sửa sau gửi.
- Vòng đời của service và chính sách từ chối.

Nên tách kiểm tra công việc khỏi những kiểm chứng có ý nghĩa cho cơ chế đồng thời thực tế. Không dùng sự thuận tiện của bộ chạy trực tiếp để suy ra tác vụ chắc chắn an toàn trên mọi bộ thực thi.

## Lỗi phổ biến

| Hiểu nhầm | Cách kiểm tra |
| --- | --- |
| Executor luôn tạo luồng mới | Xem đối tượng triển khai và chính sách được cung cấp |
| execute luôn bất đồng bộ | Executor có thể chạy trực tiếp |
| execute trở về là task đã thành công | Xác định API hoàn tất/kết quả được dùng |
| Task phải tự shutdown executor | Xác định ai sở hữu tài nguyên dùng chung |
| Nhiều task tự nhiên có thứ tự hoàn tất như thứ tự gửi | Xem hợp đồng bộ thực thi cụ thể |
| Runnable tự là một thread | Nó biểu diễn thao tác, không phải lịch thực thi |
| Lambda bắt tham chiếu final nghĩa là dữ liệu sâu an toàn | Kiểm tra đối tượng có bị thay đổi sau gửi không |
| Catch quanh execute bắt mọi lỗi ở worker | Phân biệt lỗi gửi và lỗi xảy ra sau đó |
| Dùng direct trong kiểm tra là đã chứng minh đồng thời | Cần kiểm chứng riêng hành vi thật sự có nhiều luồng |

## Thực hành kiểm chứng

1. Chạy chương trình và chỉ ra chỗ nào mô tả tác vụ, chỗ nào chọn chính sách thực thi.
2. Đổi nhãn của PrintTask mà không sửa `dispatch` hay cơ chế luồng; xác nhận công việc và chính sách là hai phần khác nhau.
3. Trong một bản thử riêng, thêm dòng in ngay sau execute ở nhánh worker trước bước đợi; giải thích vì sao không nên cố định thứ tự giữa dòng đó và output của task.
4. Thay bộ thực thi trong một nơi lắp ghép bằng direct, giữ nguyên nơi gửi việc. Xác định tác động tới nơi xử lý lỗi và việc chờ.
5. Tạo một thành phần nhận Executor qua constructor và giữ quyền shutdown ở bên ngoài thành phần đó.
6. Nếu cần trả về một kết quả tính toán, chỉ ra nhu cầu mà interface Executor chưa cung cấp trước khi chuyển sang API phong phú hơn.

Điều cần nắm là **Runnable giữ nội dung công việc, Executor nhận quyền tổ chức cách chạy, còn thành phần sở hữu bộ thực thi chịu trách nhiệm chính sách và vòng đời phù hợp**.
