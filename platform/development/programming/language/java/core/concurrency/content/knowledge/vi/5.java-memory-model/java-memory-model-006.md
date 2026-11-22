# Thread.start(), Thread.join() và quan hệ đồng bộ trong Java Memory Model

Khi lập trình đa luồng, việc một luồng **thực hiện một phép ghi trước về thời gian** không tự động có nghĩa luồng khác chắc chắn nhìn thấy phép ghi đó. Java Memory Model (JMM) quy định những quan hệ bộ nhớ cho phép ta lập luận về **thứ tự** và **tính hiển thị** giữa các luồng. Hai thao tác căn bản của `Thread` — `start()` và `join()` — đồng thời là những điểm đồng bộ quan trọng trong JMM.

Bài học tập trung vào hai bảo đảm:

1. **Trước `start()` → bên trong luồng được khởi động:** mọi hành động của luồng A trước khi gọi `threadB.start()` có quan hệ *happens-before* với mọi hành động trong luồng B được khởi động.
2. **Bên trong luồng đã kết thúc → sau khi `join()` thành công:** mọi hành động của luồng B có quan hệ *happens-before* với các hành động của luồng A sau khi A phát hiện B đã kết thúc thành công qua `threadB.join()`.

Đây là quan hệ **có hướng**, không phải lời hứa về thứ tự lên lịch CPU. Hiểu đúng hai quy tắc giúp truyền dữ liệu đầu vào sang worker và lấy kết quả sau khi worker hoàn tất, ngay cả khi các biến dữ liệu ví dụ không dùng `volatile` hay `synchronized`.

## 1. Happens-before có nghĩa gì?

Theo JMM, nếu hành động A *happens-before* hành động B, các hiệu ứng bộ nhớ của A được ràng buộc để B quan sát đúng theo quy tắc mô hình bộ nhớ; một phép đọc tại B vẫn phải xét **các phép ghi khác** có thể xen vào, chứ không mặc nhiên nhận đúng giá trị của “phép ghi A” trong mọi trường hợp.

Những điểm then chốt:

- Trong **cùng một thread**, các hành động trước trong thứ tự chương trình (*program order*) happens-before các hành động sau, dù trình biên dịch/JIT/CPU được phép tối ưu trong giới hạn giữ đúng ngữ nghĩa.
- Quan hệ happens-before có tính **bắc cầu**: nếu A → B và B → C thì A → C.
- Một quan hệ *synchronizes-with* (ví dụ `start()` hoặc phát hiện thread kết thúc) tạo ra cạnh happens-before giữa các thread.
- Happens-before **không đồng nghĩa** hai thread chạy lần lượt hoàn toàn. Những phần hành động không được ràng buộc vẫn có thể xen kẽ.
- *Không có* happens-before phù hợp khi hai thread truy cập cùng trạng thái thay đổi có thể tạo **data race** và kết quả không có bảo đảm hiển thị mong đợi.

Vì vậy, `start()` và `join()` nên được hiểu vừa là API vòng đời, vừa là **mốc đồng bộ bộ nhớ**.

## 2. Thread.start(): công bố dữ liệu trước khi khởi động

Quy tắc cốt lõi: **lời gọi `t.start()` trên một thread `t` synchronizes-with các hành động trong thread `t`**. Kết hợp thứ tự chương trình, mọi thao tác được thực hiện trước lời gọi `start()` trong thread khởi tạo happens-before các thao tác trong thread mới.

Sơ đồ:

```text
Thread main                           Thread worker
-----------                           -------------
data.input = 21
data.label = "ready"
      |
      | program order
      v
worker.start()
      |  synchronizes-with
      +--------------------------------> đọc data.input, data.label
                                        tính kết quả
```

Điều này rất hữu ích để **chuyển đầu vào đã chuẩn bị sẵn** cho luồng mới: đối tượng được khởi tạo/điền dữ liệu trước `start()` có thể được worker đọc theo quan hệ happens-before đó. Tuy nhiên, nếu luồng main tiếp tục **ghi cùng biến sau khi `start()`** trong khi worker đang đọc, hai hành động sau `start()` có thể không được đồng bộ với nhau. `start()` không biến mọi chia sẻ dữ liệu tương lai thành an toàn.

Ví dụ đơn giản:

```java
// Trích đoạn minh họa, giả định Data data và Thread worker phù hợp.
data.input = 21;         // Có happens-before với hành động trong worker.
worker.start();
data.input = 99;         // KHÔNG được start() tự bảo vệ đối với worker.
```

Nếu cả main và worker cùng truy cập không đồng bộ đến `data.input` sau `start()`, cần cơ chế phối hợp riêng. Không được suy từ việc đã gọi `start()` rằng worker sẽ nhất định đọc 21 hay 99.

**Điểm dễ nhầm:** `start()` không đợi worker chạy xong, thậm chí không bảo đảm worker đã thực hiện câu lệnh đầu tiên khi `start()` trả về. Nó chỉ khởi động luồng mới và thiết lập cạnh đồng bộ đúng hướng từ các hành động trước `start()`.

## 3. Thread.join(): phát hiện kết thúc và lấy kết quả đúng cách

`thread.join()` khiến **luồng đang gọi** chờ thread đích hoàn tất; nếu bị interrupt trong lúc chờ, phương thức có thể ném `InterruptedException`. Khi phát hiện thread đích đã thực sự kết thúc qua `join()`, các hành động đã thực hiện trong thread đích happens-before các hành động tiếp theo trên luồng gọi.

Sơ đồ:

```text
Thread worker                          Thread main
-------------                          -----------
đọc dữ liệu đầu vào
result.answer = 42
thoát run()
      |
      | thread termination detected by join
      +--------------------------------> worker.join() hoàn tất
                                         |
                                         | program order
                                         v
                                       đọc result.answer
```

Không bắt buộc khai báo `result.answer` là `volatile` **chỉ để chuyển kết quả một chiều** nếu không có truy cập xung đột và main chỉ đọc sau khi `join()` hoàn tất thành công. `join()` tạo điểm chờ vòng đời và bảo đảm hiển thị bộ nhớ cần thiết.

Cần phân biệt:

- `join()` **không** bắt đầu thread. Một `Thread` chưa `start()` không có tác vụ để chờ; gọi `join()` trên nó không khiến `run()` được gọi.
- `join()` **không** tự yêu cầu worker ngừng chạy. Nếu worker bị treo mãi, `join()` không thời hạn có thể chờ mãi.
- `join()` **không** tự lan truyền ngoại lệ xảy ra trong worker sang thread gọi. Phải thiết kế cơ chế thu lỗi/kết quả riêng.
- Chỉ việc **phát hiện thread đã kết thúc** mới tạo quan hệ thích hợp; một lần `join(timeout)` trả về khi worker vẫn sống không phải bằng chứng worker đã hoàn thành.
- Quan hệ bộ nhớ này áp dụng cho *thread cụ thể* được đợi. Nếu worker lại tạo thread con hoặc gửi nhiệm vụ sang executor rồi tự kết thúc, `join()` của worker **không tự động chờ** các tác vụ độc lập còn đang chạy ở nơi khác.

JMM cũng cho phép một thread khác phát hiện termination qua `isAlive()` trả về `false` đối với thread đã thực sự kết thúc; nhưng với mục tiêu chờ hoàn thành, `join()` truyền đạt chủ đích rõ ràng hơn và không buộc phải thăm dò trạng thái liên tục.

## 4. Ví dụ 1 — Truyền input trước start, đọc output sau join

Ví dụ đầy đủ này cố ý dùng trường `int` bình thường, không thêm `volatile` hay `synchronized`, để thấy sự kết hợp của hai cạnh happens-before.

Tạo file **`StartJoinVisibility.java`**:

```java
public class StartJoinVisibility {
    static final class Data {
        int input;
        int output;
    }

    public static void main(String[] args) throws InterruptedException {
        Data data = new Data();
        data.input = 21;

        Thread worker = new Thread(() -> {
            data.output = data.input * 2;
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Input: " + data.input);
        System.out.println("Output: " + data.output);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac StartJoinVisibility.java
java StartJoinVisibility
```

Kết quả:

```text
Input: 21
Output: 42
```

Diễn giải theo JMM:

1. Main ghi `data.input = 21` **trước** `worker.start()`; phép ghi này happens-before phép đọc `data.input` trong worker.
2. Worker đọc 21, tính 42 rồi ghi `data.output = 42` và kết thúc `run()`.
3. Main chờ `worker.join()` hoàn tất; hành động ghi output của worker happens-before phép đọc output ở main sau `join()`.
4. Không thread nào viết chồng lên hai trường theo cách cạnh tranh trong cửa sổ đó, nên output được bảo đảm như trên.

Có thể biểu diễn chuỗi bắc cầu:

```text
main: input = 21
       |
       | program order + start()
       v
worker: đọc input 21 -> output = 42 -> kết thúc
       |
       | termination detected via join()
       v
main: đọc output 42
```

**Ý nghĩa thực tế:** phân công cho thread khác tính kết quả rồi `join()` là một cách chuyển giao trạng thái hợp lệ. Điều này không có nghĩa mọi lần chia sẻ trường bình thường giữa các thread đều an toàn: ví dụ được thiết kế sao cho input được ghi trước start và output chỉ được main đọc sau join.

## 5. Không có quan hệ ngược từ worker về main nếu chỉ gọi start()

Xét đoạn mã (trích đoạn minh họa; `data` đã khai báo):

```java
Thread worker = new Thread(() -> data.output = 42);
worker.start();
System.out.println(data.output); // Không có kết quả cố định.
```

Phép ghi `data.output` của worker **không tự happens-before** phép đọc ở main chỉ nhờ `start()`. Main có thể đọc giá trị cũ hoặc mới, và việc chạy thử nhiều lần cho một kết quả giống nhau vẫn không chứng minh mã đúng. Nếu `data.output` là một trường `int` không đồng bộ, phép ghi/đọc đối nghịch này có thể cấu thành data race.

Cách sửa rõ ràng khi cần kết quả **sau khi hoàn thành**:

```java
worker.start();
worker.join();
System.out.println(data.output);
```

Đoạn sửa là trích đoạn minh họa cần nằm trong phương thức cho phép xử lý `InterruptedException`. Nếu phải nhận **kết quả trong khi worker vẫn đang chạy**, `join()` không đáp ứng vì nó đợi kết thúc; cần `volatile`, `Atomic*`, khóa, `BlockingQueue`, `CountDownLatch`, `Future` hoặc cấu trúc đồng bộ khác phù hợp với giao thức trao đổi dữ liệu.

**Cũng không được suy ra** gọi `first.start(); second.start();` thì toàn bộ công việc của first happens-before công việc của second. Main có thứ tự gọi start cho hai thread, nhưng không có cạnh trực tiếp giữa hành động chạy trong first và second chỉ từ hai lần gọi đó.

## 6. Ví dụ 2 — Bắc cầu khi chuyển dữ liệu giữa hai worker

Nếu main thật sự chờ thread thứ nhất kết thúc rồi mới khởi động thread thứ hai, các cạnh happens-before liên kết thành một chuỗi.

Tạo file **`ThreadHandoff.java`**:

```java
public class ThreadHandoff {
    static final class Box {
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        Box box = new Box();

        Thread producer = new Thread(() -> {
            box.value = 7;
        }, "producer");

        producer.start();
        producer.join();

        Thread consumer = new Thread(() -> {
            System.out.println("Received: " + box.value);
        }, "consumer");

        consumer.start();
        consumer.join();
        System.out.println("Done");
    }
}
```

```bash
javac ThreadHandoff.java
java ThreadHandoff
```

Kết quả:

```text
Received: 7
Done
```

Chuỗi quan hệ:

```text
producer: box.value = 7
             |
             | producer kết thúc -> main join() phát hiện
             v
main: producer.join() xong -> consumer.start()
                                   |
                                   | start() synchronizes-with consumer
                                   v
consumer: đọc box.value == 7
```

Vì happens-before có tính bắc cầu, phép ghi của producer xảy ra trước phép đọc của consumer theo JMM. Không cần một `volatile` riêng cho `box.value` trong đúng giao thức **hoàn tất producer → main join → khởi động consumer** này.

Nếu bỏ `producer.join()`, main có thể khởi động consumer trước khi producer ghi dữ liệu; consumer không được bảo đảm đọc 7. Trong ứng dụng thật, việc xếp hai thread thành từng pha như trên có thể giảm concurrency. Nếu cần chạy đồng thời và chuyển dữ liệu theo sự kiện, dùng cơ chế phối hợp như queue, latch hoặc future.

## 7. join(timeout): kết thúc chờ không có nghĩa worker đã kết thúc

`join(long millis)` chờ **tối đa một khoảng thời gian** cho worker kết thúc; nó có thể trả về trong khi worker vẫn đang chạy. Vì vậy phải **kiểm tra điều kiện hoàn thành** sau lời gọi nếu cần quyết định có thể đọc trạng thái cuối một cách an toàn hay chưa.

Ví dụ sau cố tình giữ worker ở trạng thái chờ bằng latch, nhờ đó nhánh “timeout nhưng thread vẫn sống” dễ quan sát và không phụ thuộc lịch chạy nhanh/chậm.

Tạo file **`TimedJoinDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class TimedJoinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiting-worker");

        worker.start();
        worker.join(20);

        System.out.println("Alive after timed join: " + worker.isAlive());

        release.countDown();
        worker.join();

        System.out.println("Alive after full join: " + worker.isAlive());
    }
}
```

```bash
javac TimedJoinDemo.java
java TimedJoinDemo
```

Kết quả trong lần chạy bình thường:

```text
Alive after timed join: true
Alive after full join: false
```

Worker không thể thoát khỏi `release.await()` trước khi main gọi `release.countDown()`, vì vậy sau `join(20)` nó vẫn sống. Khi release được phát, worker kết thúc, `join()` không thời hạn trả về và main xác nhận thread đã xong. Latch bản thân nó cũng có quy tắc đồng bộ bộ nhớ riêng; ở ví dụ này nó chủ yếu giúp điều khiển thời điểm worker kết thúc.

**Quan trọng:** lời gọi `join(timeout)` trả về đơn thuần chưa đủ để suy ra bảo đảm *worker kết thúc → main*. Khi `worker.isAlive()` cho thấy nó thực sự đã kết thúc thì đây mới là trường hợp phát hiện termination. Với một giá trị timeout, thread có thể hoàn tất trước thời hạn hoặc vẫn chạy sau thời hạn; mã không được mặc định theo một phía.

Đừng dùng `join(0)` để đặt timeout bằng không: với overload `join(long)`, **0 nghĩa là chờ vô thời hạn**. Nếu muốn thời hạn thực tế hoặc khả năng hủy, cần thiết kế riêng đường xử lý timeout/interruption.

## 8. join() bị interrupt và xử lý vòng đời đúng cách

Chỉ thread **đang gọi `join()`** bị chặn trong thao tác chờ. Nếu thread chờ nhận interrupt, `join()` ném `InterruptedException` và việc chờ đã bị ngắt; không được tự động kết luận worker đích đã hoàn thành. Worker đích có thể vẫn đang chạy.

Trong phương thức có trách nhiệm xử lý và không ném tiếp `InterruptedException`, thường khôi phục cờ interrupt để tầng gọi nhận biết:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Quyết định hủy công việc/chuyển trách nhiệm dọn dẹp.
}
```

Đây là trích đoạn minh họa, giả định biến `worker` đã khai báo. **Interrupt luồng đang chờ** khác **interrupt worker đích**. `worker.interrupt()` gửi tín hiệu hợp tác đến worker; nó không ép worker kết thúc ngay, không tự chuyển worker sang TERMINATED, và không thay thế `join()`.

Nếu worker có thể chờ vô hạn, phương án thực tế là có **giao thức yêu cầu dừng**, xử lý interrupt đúng chỗ và thời hạn chờ hợp lý. `Thread.stop()` không phải giải pháp: phương thức này đã lỗi thời và không an toàn.

## 9. join() không mang kết quả và ngoại lệ về cho bạn

`Thread.join()` trả về `void`, chỉ phục vụ chờ/vòng đời. Nó **không trả về giá trị từ Runnable**, cũng không tự ném lại ngoại lệ chưa được xử lý trong worker. Có thể dùng một nơi lưu kết quả/lỗi chia sẻ và chỉ đọc sau `join()`, hoặc chọn API có khả năng mang kết quả như `Future`.

Tạo file **`JoinAndFailure.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

public class JoinAndFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            throw new IllegalStateException("bad input");
        }, "failing-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            failure.set(error);
        });

        worker.start();
        worker.join();

        Throwable error = failure.get();
        System.out.println("Worker terminated: " + !worker.isAlive());
        System.out.println("Failure: "
                + (error == null ? "none" : error.getMessage()));
    }
}
```

```bash
javac JoinAndFailure.java
java JoinAndFailure
```

Kết quả:

```text
Worker terminated: true
Failure: bad input
```

`UncaughtExceptionHandler` nhận lỗi khi luồng sắp kết thúc vì ngoại lệ không được bắt. Sau `join()`, main quan sát được thông tin do handler đã ghi và quyết định xử lý lỗi. `AtomicReference` ở đây làm nơi chứa kết quả có giao diện truy cập rõ ràng; trong một giao thức chỉ đọc sau `join()` thành công, việc chờ kết thúc đã cung cấp quan hệ bộ nhớ cho dữ liệu do worker ghi trước khi chấm dứt.

Cần nhớ rằng **worker kết thúc không đồng nghĩa worker thành công**. Nếu muốn API trả kết quả/ngoại lệ theo giao thức rõ hơn, `ExecutorService.submit(...)` và `Future.get()` cung cấp cách tiếp cận khác, đồng thời có thêm trách nhiệm đóng executor.

## 10. Thread.start()/join() khác volatile, synchronized và các công cụ khác

| Công cụ | Quan hệ/bảo đảm chính | Dùng khi nào? |
|---|---|---|
| `Thread.start()` | Hành động trước start của luồng khởi tạo happens-before hành động trong thread mới. | Công bố dữ liệu đã chuẩn bị trước khi worker bắt đầu. |
| `Thread.join()` | Hành động của thread đã kết thúc happens-before hành động sau khi luồng khác phát hiện kết thúc. | Đợi worker và đọc trạng thái cuối/kết quả. |
| `volatile` | Một phép ghi volatile synchronizes-with các phép đọc sau đó của cùng biến theo thứ tự đồng bộ hóa. | Cờ/tín hiệu hoặc giá trị đơn giản được trao đổi **trong khi các thread còn chạy**. |
| `synchronized` | Mở khóa monitor synchronizes-with lần khóa tiếp theo trên cùng monitor, cùng bảo vệ vùng găng. | Check-then-act hoặc bất biến liên quan nhiều bước/trường. |
| `AtomicInteger` và họ `Atomic*` | Các phép đọc/ghi/cập nhật với bảo đảm nguyên tử và hiệu ứng bộ nhớ theo API. | Bộ đếm, CAS và trạng thái nguyên tử đơn. |
| `CountDownLatch` | Hành động trước `countDown()` happens-before hành động sau `await()` thành công ở thread khác. | Điều phối giữa các thread chưa kết thúc. |
| `Future.get()` | Có hợp đồng chờ kết quả, và hành động của task happens-before hành động sau `get()` tương ứng. | Nhận kết quả hoặc lỗi từ task bất đồng bộ. |

Ví dụ `start()` và `join()` không cần dùng `volatile` cho dữ liệu chuyển giao một chiều đúng cách; nhưng **không thể bỏ mọi đồng bộ hóa** nếu hai thread cùng đọc/ghi trạng thái trong lúc chạy. Một phép `volatile` đọc/ghi cũng không tự làm nguyên tử đoạn mã check-then-act nhiều bước.

### Dễ nhầm giữa “đã xảy ra theo thời gian” và “happens-before”

JMM tạo quan hệ hình thức. Việc nhật ký cho thấy A in ra trước B chưa chắc làm các thao tác dữ liệu khác giữa hai thread có happens-before tương ứng; log dùng đồng bộ hóa nội bộ còn có thể ảnh hưởng lịch chạy. Cần chứng minh bằng các cạnh cụ thể như start, join, lock/unlock, volatile hoặc primitive đồng bộ.

### Dễ nhầm giữa thứ tự start và thứ tự hoàn thành

`a.start(); b.start();` không bảo đảm A hoàn thành trước B. Cũng không bảo đảm A in một dòng trước B chỉ vì A được start trước. Muốn B chỉ thực thi công việc sau khi A xong, hãy chờ `a.join()` trước khi bắt đầu B hoặc dùng một giao thức đồng bộ giữa hai worker.

### Dễ nhầm giữa dữ liệu trong bộ nhớ và tác dụng phụ bên ngoài

Happens-before bảo đảm các quan hệ bộ nhớ trong Java, **không** cam kết file đã được flush/bền trên đĩa, yêu cầu mạng đã được hệ thống khác xử lý hoặc giao dịch ngoài tiến trình đã commit. Muốn có những bảo đảm đó phải dùng API và giao thức riêng của tài nguyên bên ngoài.

## 11. Những câu hỏi để kiểm tra tính đúng đắn

Khi quyết định có thể trao đổi dữ liệu bằng `start()`/`join()` hay không, hãy lần lượt kiểm tra:

1. **Ai ghi input và ghi khi nào?** Nếu main ghi xong trước khi `start()`, worker có thể dựa vào cạnh start.
2. **Input có bị thread khác sửa sau khi start không?** Nếu có, cạnh start không bảo vệ những thao tác cạnh tranh về sau.
3. **Ai ghi output và main đọc khi nào?** Nếu chỉ đọc sau khi `join()` hoàn tất do worker kết thúc, có cạnh termination.
4. **Có phải đang dùng `join(timeout)`?** Nếu worker còn sống sau timeout, chưa thể coi dữ liệu cuối đã ổn định; cần kiểm tra termination hoặc dùng primitive phù hợp.
5. **Worker có tạo thêm thread/task khác không?** `join()` chỉ đợi worker được chỉ định, không tự đợi toàn bộ tác vụ được nó giao đi.
6. **Nếu worker thất bại hoặc không bao giờ kết thúc thì sao?** Có đường báo lỗi và hủy hợp tác, timeout, cleanup phù hợp chưa?
7. **Bất biến có nhiều bước hay nhiều trường không?** Nếu có, start/join có thể phù hợp cho các *pha* tách biệt; còn truy cập đồng thời trong pha cần khóa/atomic/primitive tương ứng.

Lưu ý các quy tắc happens-before này áp dụng cho quan hệ thread Java; với **virtual threads** được giới thiệu chính thức trong Java 21, bản chất quy tắc start/join vẫn có ý nghĩa. Ví dụ bài học sử dụng API Java 17 phổ biến để có thể biên dịch và chạy trực tiếp.

## 12. Tự kiểm tra

1. **`start()` bảo đảm hướng dữ liệu nào?** Các hành động đã xảy ra trước start trên luồng khởi tạo happens-before hành động của thread được start. Không có bảo đảm ngược lại từ worker về main chỉ bằng start.
2. **Vì sao `data.output` không cần `volatile` ở Ví dụ 1?** Vì main chỉ đọc sau `join()` hoàn tất, tạo quan hệ happens-before từ phép ghi của worker tới phép đọc của main; các truy cập không bị tranh chấp ngoài giao thức.
3. **`a.start(); b.start();` có làm hành động của a happens-before b không?** Không, trừ khi có thêm một cạnh đồng bộ nối hai thread.
4. **`join(20)` trả về có chắc worker đã kết thúc không?** Không; phải xác minh worker thực sự đã kết thúc hoặc dùng cách chờ hoàn thành khác.
5. **`join()` có tự truyền ngoại lệ worker sang main không?** Không; cần nơi lưu lỗi, uncaught exception handler, Future hoặc giao thức kết quả riêng.
6. **Nếu main bị interrupt lúc chờ join thì điều gì xảy ra?** Lời gọi có thể ném `InterruptedException`; không được tự coi worker đã hoàn thành.
7. **Vì sao hai thread đồng thời ghi/đọc một biến sau `start()` vẫn có thể race?** Vì cạnh start chỉ bao trùm hành động trước start đến thread mới; không tự sắp thứ tự các truy cập xung đột về sau.
8. **Nếu producer hoàn thành, main join producer rồi start consumer, điều gì bảo đảm consumer nhìn thấy kết quả?** Cạnh termination → join, thứ tự chương trình trên main và cạnh start → consumer ghép thành quan hệ happens-before bắc cầu.

**Ghi nhớ:** `Thread.start()` là cạnh **công bố dữ liệu vào worker**; `Thread.join()` khi thực sự quan sát kết thúc là cạnh **nhận kết quả từ worker**. Ghép đúng hai cạnh với *program order* và tính bắc cầu tạo một giao thức chuyển giao dữ liệu đơn giản, rõ ràng theo Java Memory Model. Với các truy cập đồng thời trong lúc worker còn chạy, vẫn cần cơ chế đồng bộ hóa thích hợp.
