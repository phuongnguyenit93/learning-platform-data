# Quan hệ bộ nhớ do executor, future và collection đồng thời cung cấp

## Dùng hợp đồng API để xác định điểm chuyển giao

Khi một luồng chuẩn bị dữ liệu rồi giao công việc cho luồng khác, câu hỏi không chỉ là “task chạy ở đâu?” mà còn là “các lần ghi nào được phía nhận quan sát đúng?”.

Các API trong `java.util.concurrent` công bố những quan hệ **happens-before** tại các điểm chuyển giao cụ thể. Nhờ đó, chương trình có thể dùng hợp đồng của API mà không cần biết chi tiết khóa hay biến nội bộ của thư viện.

Bài dùng Java 17+ và ba đường truyền: gửi task tới executor, nhận kết quả bằng `Future.get()` và trao đối tượng qua một collection đồng thời.

## Ba bảo đảm cần tách riêng

| Cơ chế | Điểm phía gửi | Điểm phía nhận |
| --- | --- | --- |
| Gửi công việc | Các hành động trong luồng gửi trước khi submit task | Các hành động của task đó |
| Nhận kết quả | Các hành động của phép tính bất đồng bộ | Các hành động sau `Future.get()` tương ứng |
| Collection đồng thời | Các hành động trước khi đặt đối tượng vào collection | Các hành động sau khi luồng khác truy cập hoặc lấy ra đúng đối tượng ấy |

Bảo đảm tổng quát được mô tả trong [thuộc tính nhất quán bộ nhớ của `java.util.concurrent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility). Phạm vi là những hành động và thao tác tương ứng, không phải mọi cập nhật vào mọi dữ liệu trong chương trình.

Một API có thể tạo đường công bố dữ liệu an toàn mà không biến những đối tượng được công bố thành bất biến hoặc làm mọi phép cập nhật tương lai trở nên nguyên tử.

## Ví dụ hoàn chỉnh: gửi, nhận kết quả và chuyển thông điệp

Lưu tệp `ConcurrentMemoryDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ConcurrentMemoryDemo {
    private ConcurrentMemoryDemo() {
    }

    static final class State {
        int input;
        int output;
        boolean completed;
    }

    static final class Message {
        int code;
        String text;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            State state = new State();
            state.input = 21;

            Future<Integer> calculation = executor.submit(() -> {
                state.output = state.input * 2;
                state.completed = true;
                return state.output;
            });

            int returned = calculation.get();
            System.out.println("futureResult: " + returned);
            System.out.println("sharedOutput: " + state.output);
            System.out.println("completed: " + state.completed);

            BlockingQueue<Message> queue = new ArrayBlockingQueue<>(1);
            Future<String> consumer = executor.submit(() -> {
                Message received = queue.take();
                return received.code + ":" + received.text;
            });

            Message message = new Message();
            message.code = 7;
            message.text = "ready";
            queue.put(message);
            System.out.println("queueReceived: " + consumer.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror ConcurrentMemoryDemo.java
java ConcurrentMemoryDemo
```

Khi các công việc và lần chờ hoàn tất bình thường, stdout chính xác:

```text
futureResult: 42
sharedOutput: 42
completed: true
queueReceived: 7:ready
```

Ví dụ dùng các trường thường để thấy rõ hiệu ứng của đường truyền. Không có luồng nào sửa các trường tương ứng ngoài giao thức đang được phân tích.

`finally` gửi yêu cầu dừng executor, đồng thời yêu cầu ngắt công việc còn hoạt động nếu phương thức rời đi bằng ngoại lệ. Ở đường bình thường, hai lần `get()` đã nhận xong kết quả. `shutdownNow()` là yêu cầu dừng/ngắt, không phải một bảo đảm cưỡng chế mọi task bất kỳ phải dừng ngay.

## Cạnh gửi task: các ghi trước submit đi tới task

Trước khi gửi phép tính, `main` tạo `State` và gán `input = 21`. Task đọc `input` để tính kết quả.

Quan hệ đang dùng là:

```text
main: state.input = 21
         │ thứ tự chương trình
main: executor.submit(task)
         └──── happens-before ────> task: đọc state.input
```

Đây là bảo đảm của việc gửi công việc, không phải vì ta đoán worker đã được tạo mới. Pool có thể dùng lại một luồng đã tồn tại từ trước. Xem [hiệu ứng bộ nhớ của `ExecutorService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

`Executor` không bắt buộc mọi triển khai phải chạy bất đồng bộ trong một luồng khác; một triển khai hợp lệ có thể gọi task ngay trong luồng gửi. Vì vậy không đặt giả định “submit xong thì task chưa chạy” vào thiết kế. Xem [`Executor`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html).

Đồng thời, submit không sao chép sâu `state`. Nếu `main` sửa `input` sau submit trong lúc task đọc, cạnh ban đầu không tự sắp thứ tự lần sửa mới đó. Cần một giao thức cập nhật riêng hoặc dữ liệu đầu vào không thay đổi trong thời gian xử lý.

## Cạnh `Future.get`: tác động của task đi trở lại bên gọi

Task ghi `output`, ghi `completed` và trả giá trị. `main` chỉ đọc các trường sau `calculation.get()` đã nhận được kết quả.

Vì vậy không chỉ số nguyên được trả về là `42`; các tác động ghi vào `state.output` và `state.completed` trước khi task hoàn tất cũng có đường happens-before tới các đọc tiếp theo. Xem [hiệu ứng bộ nhớ của `Future`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Chuỗi hai chiều của ví dụ là:

```text
main chuẩn bị đầu vào
        → gửi task
        → task đọc và tính
        → task ghi kết quả
        → nhận qua Future.get()
        → main dùng kết quả và trạng thái
```

Không cần thêm `volatile` chỉ để truyền ba trường này qua đúng hai ranh giới hiện có. Nhưng kết luận đó phụ thuộc việc không có truy cập cạnh tranh khác nằm ngoài giao thức.

Chỉ giữ một đối tượng `Future` trong tay không chứng minh task đã kết thúc. `submit` trả về một phương tiện theo dõi công việc; bên gọi phải dùng các thao tác có hợp đồng phù hợp trước khi dựa vào kết quả cuối.

## Các đường của `get` không có cùng ý nghĩa nghiệp vụ

| Kết quả của thao tác chờ | Cách diễn giải |
| --- | --- |
| `get()` trả về bình thường | Có kết quả của công việc tương ứng |
| `ExecutionException` | Phép tính đã thất bại; cần xem nguyên nhân |
| `InterruptedException` | Luồng đang chờ bị ngắt; không coi như đã nhận kết quả thành công |
| `TimeoutException` với `get(timeout, unit)` | Chưa nhận được kết quả trong giới hạn chờ |
| `CancellationException` | Future đã bị hủy; không diễn giải như một kết quả thành công |

Bảng tập trung vào điều kiện sử dụng kết quả, không gộp mọi ngoại lệ thành “chưa có cạnh bộ nhớ nào”. Điểm thực hành là không tiếp tục dùng các trường như kết quả nghiệp vụ hợp lệ khi đường thành công chưa xảy ra.

`isDone()` có thể là `true` cả khi hoàn tất bình thường, thất bại hoặc bị hủy. Không thay việc xử lý kết quả bằng một phép kiểm tra boolean rồi giả định công việc thành công.

Hủy Future cũng không bảo đảm một task đang chạy, phớt lờ ngắt, đã dừng mọi thay đổi trạng thái. Nếu có hủy hoặc timeout, thiết kế cần quy tắc về vòng đời và quyền cập nhật dữ liệu đang dùng chung.

`shutdown()` chỉ yêu cầu executor ngừng nhận công việc mới và hoàn tất những công việc đã nhận; không dùng riêng lời gọi đó như thao tác chờ kết quả của một task cụ thể.

## Cạnh collection: công bố chính đối tượng được chuyển

Trong phần queue, `main` đã gửi task consumer trước rồi mới tạo và gán các trường của `Message`. Vì các ghi `code` và `text` xảy ra sau submit consumer, chúng không được chứng minh bằng cạnh submit ban đầu.

Thay vào đó, đường truyền là:

```text
main: message.code = 7; message.text = "ready"
                   │
main: queue.put(message)
                   └──── happens-before ────> consumer: queue.take() nhận message
                                                              │
                                                     đọc code và text
```

Các hành động trước khi đặt phần tử vào `BlockingQueue` đứng happens-before những hành động sau khi luồng khác truy cập hoặc lấy đúng phần tử đó. Vì thế consumer đọc `7:ready` mà hai trường không cần `volatile` trong giao thức chuyển giao này. Xem [`BlockingQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

`consumer.get()` sau đó truyền kết quả chuỗi từ task về `main`. Có hai ranh giới nối tiếp: queue từ producer tới consumer, rồi future từ consumer tới bên in kết quả.

`take()` có thể đợi phần tử xuất hiện; việc đợi là đặc điểm tiện ích của API queue này. Bảo đảm bộ nhớ được gắn với thao tác chuyển giao thành công, không phải vì một luồng đã ngủ một khoảng thời gian.

## Collection an toàn luồng không tự bảo vệ mọi cập nhật của phần tử

Sau khi `queue.put(message)` thành công, nếu producer tiếp tục sửa `message.text` đồng thời consumer đọc nó, những ghi mới không tự được bảo vệ bởi lần put đã xảy ra trước đó.

Một chiến lược đơn giản là chuyển quyền sử dụng: producer hoàn tất thông điệp trước khi đặt vào queue rồi không sửa nó nữa. Một chiến lược khác là dùng thông điệp bất biến. Nếu thực sự cần cùng sửa phần tử, phải chọn cơ chế bảo vệ chính phần tử.

Queue không clone thông điệp. Consumer nhận lại một tham chiếu tới đối tượng đã được chuyển, nên thay đổi sau công bố vẫn là thay đổi vào cùng dữ liệu.

Lập luận tương tự áp dụng khi một collection chứa tham chiếu tới cấu trúc có thể thay đổi: an toàn của thao tác trên collection và an toàn của nội dung bên trong là hai câu hỏi khác nhau.

## `ConcurrentMap`: đọc đúng giá trị đã được công bố

`ConcurrentMap` cũng công bố bảo đảm cho các hành động trước khi đặt một đối tượng làm khóa hoặc giá trị, đối với luồng khác truy cập hoặc loại bỏ đối tượng ấy qua map. Xem [`ConcurrentMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

Đoạn sau là các thành viên có thể đặt trong một lớp; cần import `ConcurrentMap` và `ConcurrentHashMap`. Nó minh họa producer và reader, không có stdout cố định vì lần đọc có thể xảy ra trước khi cài đặt:

```java
static final class Config {
    int retries;
}

private final ConcurrentMap<String, Config> configs = new ConcurrentHashMap<>();

void install() {
    Config config = new Config();
    config.retries = 3;
    configs.put("service", config);
}

Integer readRetries() {
    Config config = configs.get("service");
    return config == null ? null : config.retries;
}
```

Nếu `get("service")` nhận đúng giá trị đã cài, việc khởi tạo `retries` trước put có đường công bố phù hợp. Nếu `get` trả `null`, không được coi đó là đã nhận một cấu hình hoặc một tín hiệu hoàn tất.

Với `ConcurrentHashMap`, quan hệ update–retrieval được mô tả theo khóa và kết quả đọc tương ứng; không phải một giao dịch chụp nhất quán toàn bộ map. Các thao tác tổng hợp như `size()` hoặc duyệt nhiều khóa không tự trở thành một hàng rào giai đoạn toàn cục. Xem [`ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Map cũng không tự sắp thứ tự mọi lần sửa `config.retries` sau khi đã put. Nếu muốn cập nhật cấu hình, có thể công bố một đối tượng cấu hình mới theo thiết kế thay vì sửa tự do một đối tượng đang được nhiều luồng dùng.

## Khả năng quan sát khác tính nguyên tử của chuỗi thao tác

Một collection có thể bảo đảm từng thao tác an toàn luồng nhưng không làm cả chuỗi `get` rồi `put` trở thành một phép cập nhật nguyên tử.

Ví dụ, đọc bộ đếm từ map rồi ghi lại giá trị tăng một có thể mất cập nhật khi hai luồng cùng làm. Cần dùng thao tác phối hợp phù hợp của cấu trúc cụ thể, chẳng hạn `merge` trên `ConcurrentHashMap`, hoặc thiết kế giá trị đếm có cơ chế đồng bộ riêng.

Tương tự, `Future.get()` ở cuối không sửa được các phép tăng đếm tranh chấp đã xảy ra trong hai task. Bảo đảm hiển thị kết quả và bảo đảm cách tạo kết quả là hai phần riêng của tính đúng đắn.

Không thêm khóa ngoài chỉ vì chưa biết thư viện dùng gì bên trong; trước hết đọc hợp đồng về tính nguyên tử và bộ nhớ của đúng thao tác đang dùng.

## Rà soát một đường dữ liệu qua API concurrent

1. Xác định luồng gửi ghi dữ liệu nào và ghi trước thao tác chuyển giao nào.
2. Xác định thao tác nhận tương ứng: task nào, Future nào, phần tử queue nào hoặc giá trị map nào.
3. Chỉ ra lần đọc dữ liệu nằm sau thao tác nhận thành công.
4. Kiểm tra có ghi tiếp sau công bố hoặc có nhiều người sửa không; nếu có, bổ sung giao thức riêng.
5. Tách timeout, hủy và thất bại khỏi việc đã nhận kết quả nghiệp vụ thành công.
6. Với nhiều thao tác, kiểm tra tính nguyên tử của toàn chuỗi thay vì chỉ của từng thao tác.

## Thực hành kiểm chứng

1. Đổi `state.input` thành `30` trước submit; `futureResult` và `sharedOutput` phải cùng là `60` khi get thành công.
2. Đổi thông điệp thành `code = 9`, `text = "published"` trước put; consumer phải nhận `9:published`.
3. Vẽ hai cạnh trong phần queue: một cạnh truyền Message tới consumer và một cạnh truyền kết quả consumer tới `main`.
4. Phân tích phiên bản sửa `message.text` sau put trong khi consumer có thể đọc; chỉ ra vì sao lần put cũ không bảo vệ cập nhật mới.
5. Với đoạn map, giải thích sự khác nhau giữa get trả `null` và get nhận một `Config` đã được công bố; không dùng `size() > 0` làm thay thế tổng quát.

Người học cần chỉ ra đúng điểm chuyển giao và đối tượng liên quan của từng bảo đảm, rồi kiểm tra riêng các cập nhật tương lai và những thao tác cần nguyên tử.