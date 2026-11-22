# Quan hệ bộ nhớ khi bắt đầu và chờ kết thúc luồng

## `start` và `join` không chỉ điều khiển vòng đời

Một công việc thường nhận dữ liệu từ luồng tạo nó, tính toán trong luồng riêng, rồi trả kết quả cho luồng chờ. Để đọc và ghi đúng, cần biết Java bảo đảm quan hệ bộ nhớ ở hai điểm chuyển giao này như thế nào.

`Thread.start()` khởi động một luồng thực thi riêng. `Thread.join()` chờ luồng được chỉ định kết thúc. Bên cạnh ý nghĩa vòng đời, chúng tham gia các cạnh **happens-before**, giúp truyền tác động bộ nhớ theo một thứ tự được Java Memory Model quy định.

Bài dùng Java 17+ với các luồng tạo qua constructor `Thread`, không dùng `sleep` hoặc log để đoán thời điểm hoàn thành.

## Hai cạnh có hướng khác nhau

| Điểm chuyển giao | Hướng bảo đảm |
| --- | --- |
| Bắt đầu luồng | Các hành động trong luồng gọi, trước `start()`, được sắp trước các hành động của luồng được khởi động |
| Phát hiện luồng đã kết thúc | Các hành động của luồng đã kết thúc được sắp trước các hành động sau khi bên chờ phát hiện kết thúc, điển hình qua `join()` thành công |

Đây là quan hệ có hướng, không phải một cơ chế chia sẻ mọi cập nhật theo cả hai chiều trong suốt thời gian hai luồng cùng chạy. Xem [happens-before trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

Mô hình một lần tính toán:

```text
Luồng main                               Luồng worker
ghi dữ liệu đầu vào
       │
gọi worker.start() ── happens-before ──> đọc đầu vào
                                               │
                                          ghi kết quả
                                               │
                                          kết thúc
       <──────── phát hiện kết thúc qua join ───┘
đọc kết quả sau join
```

## Ví dụ hoàn chỉnh: trường thường vẫn có thể truyền đúng

Lưu tệp `StartJoinMemoryDemo.java`:

```java
public final class StartJoinMemoryDemo {
    private StartJoinMemoryDemo() {
    }

    static final class State {
        int input;
        int result;
        boolean completed;
    }

    public static void main(String[] args) throws InterruptedException {
        State state = new State();
        state.input = 21;

        Thread worker = new Thread(() -> {
            state.result = state.input * 2;
            state.completed = true;
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("completed: " + state.completed);
        System.out.println("result: " + state.result);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror StartJoinMemoryDemo.java
java StartJoinMemoryDemo
```

Khi `join()` hoàn tất bình thường, stdout chính xác:

```text
completed: true
result: 42
```

Các trường trong `State` không phải `volatile`. Ví dụ vẫn đúng vì dữ liệu được chuyển qua hai ranh giới có happens-before, và không có truy cập cạnh tranh nằm ngoài những ranh giới ấy.

## Chứng minh đường truyền đầu vào

`main` gán `state.input = 21` trước khi gọi `worker.start()`. Luồng worker sau đó đọc trường này để tính kết quả.

Thứ tự trong `main` kết hợp cạnh bắt đầu luồng tạo chuỗi:

```text
main ghi input = 21
        happens-before
worker bắt đầu và đọc input
```

`main` không tiếp tục sửa `input` sau khi khởi động worker. Vì vậy không có một lần sửa cạnh tranh khác làm phức tạp điều kiện đọc trong ví dụ.

Chỉ tạo đối tượng bằng `new Thread(...)` chưa chạy công việc. Cạnh bắt đầu luồng liên quan tới việc gọi `start` để bắt đầu luồng đó, không phải việc đã có một đối tượng `Thread` trong bộ nhớ. Xem [`Thread.start()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#start()).

## Chứng minh đường truyền kết quả

Worker ghi `result`, rồi đặt `completed = true`, rồi kết thúc `run` của nó. `main` gọi `worker.join()` không thời hạn và chỉ in các trường sau khi lời gọi trở về bình thường.

Phát hiện kết thúc thiết lập đường để `main` quan sát các tác động của worker. Do không có luồng nào khác sửa `result` hoặc `completed`, kết quả trong chương trình là `42` và `true`.

Điều này không phụ thuộc vào việc worker kết thúc trước hay sau khi `main` bắt đầu gọi `join`. Nếu worker đã kết thúc, bên gọi vẫn có thể chờ/phát hiện trạng thái kết thúc và tiếp tục với bảo đảm tương ứng. Xem [`Thread.join()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#join()).

Không nên giải thích bằng việc “đợi đủ lâu cho CPU xả cache”. Bằng chứng nằm ở quan hệ trong mô hình bộ nhớ, không ở một khoảng thời gian chờ được đoán.

## Cạnh `start` không bao phủ các ghi sau nó

Giả sử sửa trình tự thành:

```java
// Chỉ minh họa một giao thức sai nếu worker đọc input đồng thời.
worker.start();
state.input = 21;
worker.join();
```

Ở đây lần gán `input` đứng sau `start`; quy tắc bắt đầu luồng không tự đặt lần gán đó trước lần đọc của worker. Nếu không có cơ chế phối hợp khác, có truy cập xung đột chưa được sắp thứ tự.

`join` ở cuối cho phép `main` quan sát tác động của worker sau khi nó kết thúc. Nó không quay ngược lại để làm lần đọc đầu vào trước đó của worker trở nên đúng.

Không gán cho phiên bản sai một stdout cố định. Chương trình có thể có vẻ đúng ở một số lần chạy nhưng thiếu bảo đảm cần thiết; kiểm thử nhiều lần không thay thế được đường happens-before bị thiếu.

Nếu cần gửi cập nhật trong lúc worker đang hoạt động, dùng một giao thức phù hợp như cùng monitor, `volatile` theo thiết kế, queue hoặc cơ chế đồng bộ khác. `start` chỉ là một ranh giới ban đầu, không phải kênh cập nhật liên tục.

## `join` có timeout không chứng minh luồng đã kết thúc

`join(long millis)` có thể trả về vì đã hết thời gian chờ trong khi worker vẫn còn chạy. Không đọc `result` theo giả định “đã join thì xong” nếu chưa xác định điều kiện trở về.

Đoạn dưới là một mẫu xử lý trong phương thức có sẵn `worker` và `state`; nó không có stdout cố định vì worker có thể hoàn thành hoặc còn chạy:

```java
worker.join(100);
if (worker.isAlive()) {
    System.out.println("not finished");
    return;
}
System.out.println(state.result);
```

Mẫu giả định `worker` đã được khởi động trước đó. Nếu `isAlive()` cho `false` và ta biết đó là luồng đã bắt đầu, việc phát hiện nó đã kết thúc là thông tin cần để dùng kết quả cuối.

Không dùng riêng `!isAlive()` để kết luận một đối tượng `Thread` bất kỳ “đã hoàn thành”: một luồng chưa từng được bắt đầu cũng không alive. Chờ trên một luồng chưa khởi động không thay thế việc chạy công việc. Xem [`join(long)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#join(long)) và [`isAlive()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#isAlive()).

## `InterruptedException` không phải tín hiệu worker đã xong

Luồng gọi `join` có thể bị ngắt khi đang chờ. Khi lời gọi ném `InterruptedException`, không được coi như nó đã chờ worker kết thúc.

Một lựa chọn là truyền ngoại lệ lên như `main` của ví dụ. Một lựa chọn khác trong một phương thức xử lý là khôi phục trạng thái ngắt và dừng đường đọc kết quả:

```java
try {
    worker.join();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
System.out.println(state.result);
```

Khối mã minh họa này chỉ kết luận có thể đọc kết quả sau đường chờ bình thường. Việc luồng gọi dừng chờ không tự hủy hoặc làm worker kết thúc; quản lý hủy công việc cần chính sách riêng.

Cũng tránh nuốt `InterruptedException` rồi tiếp tục đọc trường như thể worker đã xong.

## Hợp thành hai ranh giới bằng tính bắc cầu

Một luồng điều phối có thể chờ giai đoạn thứ nhất xong rồi mới bắt đầu giai đoạn thứ hai. Khi đó dữ liệu có một đường truyền rõ ràng qua luồng điều phối.

Lưu ví dụ riêng trong `JoinChainDemo.java`:

```java
public final class JoinChainDemo {
    private JoinChainDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        int[] result = {0};
        Thread first = new Thread(() -> result[0] = 21, "first");
        first.start();
        first.join();

        Thread second = new Thread(() -> result[0] *= 2, "second");
        second.start();
        second.join();

        System.out.println("chainedResult: " + result[0]);
    }
}
```

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror JoinChainDemo.java
java JoinChainDemo
```

Stdout chính xác khi các lần chờ hoàn tất bình thường:

```text
chainedResult: 42
```

Lần ghi `21` của `first` được truyền tới `main` sau `first.join()`. Sau đó `main` bắt đầu `second`, nên lần đọc để nhân đôi của `second` đứng sau giai đoạn trước theo happens-before. Cuối cùng `second.join()` cho `main` quan sát kết quả.

Nếu chỉ gọi `first.start()` rồi `second.start()` liên tiếp mà bỏ sự phối hợp giữa hai giai đoạn, thứ tự hai lời gọi bắt đầu trong `main` không tự buộc toàn bộ hành động của `first` xảy ra trước các hành động của `second`.

Ví dụ chuỗi dùng các luồng chạy theo giai đoạn, không minh họa tăng tốc bằng chạy đồng thời. Mục tiêu là chỉ ra đường truyền bộ nhớ có thể hợp thành bằng tính bắc cầu.

## `join` không tự sửa một phép cập nhật tranh chấp

Nếu hai luồng cùng làm `counter++` trên trường thường mà không có giao thức bảo vệ, việc `main` chờ cả hai kết thúc không khiến các phép tăng trước đó trở thành nguyên tử.

`join` giúp `main` quan sát trạng thái sau khi hai luồng dừng. Nó không ngăn hai phép đọc–sửa–ghi chồng lên nhau trong thời gian chúng cùng chạy. Khi cần tăng đếm đồng thời, phải chọn cách cập nhật phù hợp ngay tại nơi cập nhật.

Tương tự, chờ một worker không tự chờ mọi luồng mà worker từng tạo. Phải xác định luồng hoặc công việc nào thật sự đã hoàn tất và đường truyền dữ liệu tương ứng.

## Kết thúc luồng khác hoàn thành nghiệp vụ thành công

Một luồng có thể kết thúc vì `run` xong bình thường hoặc do lỗi không được xử lý. `join` chờ kết thúc; nó không tự truyền ngoại lệ của worker sang bên gọi như một kết quả nghiệp vụ.

Trong ví dụ đầu, `completed` chỉ được gán sau phép tính. Với công việc có thể thất bại, cần mô hình rõ ràng cho kết quả và lỗi. Không xem việc `join` trở về là bằng chứng rằng mọi bước nghiệp vụ trong worker đã chạy thành công.

Với API công việc cấp cao, các hợp đồng như gửi task tới `ExecutorService` và lấy kết quả bằng `Future.get()` cung cấp những ranh giới riêng về kết quả/bộ nhớ. Đừng thay chúng bằng việc cố `join` một luồng pool không tương ứng với vòng đời task. Xem [các bảo đảm bộ nhớ trong `java.util.concurrent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

## Những thao tác dễ bị hiểu nhầm

| Thao tác hoặc quan sát | Không được kết luận thêm điều gì? |
| --- | --- |
| Gọi trực tiếp `worker.run()` | Không phải yêu cầu bắt đầu một luồng mới bằng `start` |
| `Thread.sleep(...)` trong `main` | Không tự xác nhận worker đã kết thúc hoặc cung cấp cạnh join |
| Đọc log thấy worker in trước | Không tự chứng minh mọi lần đọc trường khác đã được đồng bộ đúng |
| Thêm `join` sau một data race | Không làm các thao tác tranh chấp đã diễn ra trở nên nguyên tử |
| Gọi `start` từ constructor còn đang gán trường | Không làm những gán sau `start` tự xảy ra trước worker |

Không gọi `start` nhiều lần trên cùng một đối tượng `Thread` để mong dùng lại ranh giới này cho nhiều tác vụ; một luồng đã bắt đầu không được khởi động lại.

## Cách rà soát đường truyền đầu vào và đầu ra

1. Xác định mọi trường đầu vào worker sẽ đọc và lần ghi nào phải hoàn tất trước `start`.
2. Kiểm tra có cập nhật tiếp nào trong lúc worker đang hoạt động không; nếu có, xác định giao thức riêng cho chúng.
3. Xác định bên nhận chỉ đọc kết quả sau sự kiện kết thúc đã được phát hiện thật sự.
4. Phân loại rõ các đường `join` hoàn tất, timeout và interruption.
5. Kiểm tra lỗi nghiệp vụ và thao tác cập nhật nguyên tử bằng thiết kế riêng, không giao hết trách nhiệm cho `join`.

## Thực hành kiểm chứng

1. Đổi `input` thành `35` trước `start`; kết quả phải là `70` sau `join` bình thường.
2. Bỏ `worker.join()` trong bản thử riêng và giải thích vì sao không còn bảo đảm cho các dòng đọc kết quả ngay sau `start`; không yêu cầu bản sai luôn in cùng một giá trị.
3. Trong ví dụ chuỗi, đổi giá trị giai đoạn đầu hoặc hệ số giai đoạn hai và kiểm tra kết quả theo đường `join` rồi `start`.
4. Phân tích trường hợp một `join(100)` trả về nhưng `worker.isAlive()` còn `true`; không được dùng nó như kết quả cuối.
5. Vẽ hai cạnh riêng trong ví dụ đầu: cạnh truyền input tới worker và cạnh truyền result trở lại `main`.

Người học cần xác định đúng hướng của mỗi ranh giới, chỉ ra dữ liệu nào nằm trước/sau nó và tránh dùng thời gian chờ để thay thế phát hiện hoàn tất.