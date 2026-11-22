# Phân biệt gọi `Thread.start()` và `Thread.run()` trong Java

## 1. Cùng một phương thức `run`, nhưng hai cách gọi có ý nghĩa khác nhau

Một `Thread` đại diện cho một luồng thực thi Java. Công việc mà luồng sẽ thực hiện thường nằm trong `Runnable.run()` hoặc phương thức `Thread.run()` được ghi đè. Điều dễ nhầm lẫn là **gọi `run()` trực tiếp không tạo hoặc khởi động luồng mới**.

- **`thread.start()`**: yêu cầu JVM khởi động luồng được biểu diễn bởi đối tượng `thread`. Khi luồng được lên lịch, JVM thực hiện `run()` trên **luồng mới**. Phương thức `start()` thường trả về trước khi công việc hoàn tất; người gọi tiếp tục thực thi độc lập với luồng mới.
- **`thread.run()`**: gọi một phương thức Java thông thường trên **luồng đang gọi**. Nội dung `run()` chạy đồng bộ; người gọi chờ lời gọi phương thức trả về trước khi thực hiện câu lệnh tiếp theo. Không có luồng Java mới nào được tạo chỉ vì gọi `run()`.

Sự khác biệt nằm ở **ngữ cảnh thực thi**, không phải ở bản thân nội dung của `run()`. Cùng một `Runnable` có thể chạy trên luồng `main` khi gọi trực tiếp hoặc trên luồng được tạo khi gọi `start()`.

```text
Luồng main
  |
  +-- thread.run() ------------------------+
  |     công việc chạy ngay trên main     |
  |     main đợi công việc hoàn thành      |
  |<--------------------------------------+
  |
  +-- thread.start() -- yêu cầu tạo luồng mới
  |       |
  |       +---- luồng worker chạy run()
  |       |       (được JVM/OS lên lịch)
  |       +---- kết thúc sau đó
  |
  +-- main tiếp tục (có thể chạy xen kẽ với worker)
```

Với platform thread, `start()` khởi động luồng Java gắn với OS thread. Với virtual thread (Java 21+), `start()` khởi động virtual thread do JVM lên lịch lên carrier platform thread. **Cả hai đều là luồng Java riêng** với luồng gọi; còn gọi `run()` trực tiếp vẫn chạy ở luồng hiện tại.

## 2. Ví dụ đầu tiên: xác định chính xác luồng nào thực thi

Tạo tệp `StartVsRunDemo.java`:

```java
public class StartVsRunDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable job = () -> System.out.println(
                "Job đang chạy trên: " + Thread.currentThread().getName());

        Thread direct = new Thread(job, "worker-direct");
        direct.run();
        System.out.println("Trạng thái direct: " + direct.getState());

        Thread started = new Thread(job, "worker-started");
        started.start();
        started.join();
        System.out.println("Trạng thái started: " + started.getState());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac StartVsRunDemo.java
java StartVsRunDemo
```

Kết quả khi dùng trình khởi chạy Java thông thường (tên luồng chính là `main`):

```text
Job đang chạy trên: main
Trạng thái direct: NEW
Job đang chạy trên: worker-started
Trạng thái started: TERMINATED
```

Đọc kết quả theo từng bước:

1. `direct` được tạo với tên `worker-direct` nhưng chỉ được gọi `direct.run()`. Lúc thực thi, `Thread.currentThread()` trả về **main**, không phải `direct`. Tên đã đặt cho đối tượng `Thread` không đổi tên luồng thực thi.
2. Vì chưa từng gọi `direct.start()`, trạng thái `direct.getState()` vẫn là `NEW` ngay cả sau khi gọi `direct.run()`.
3. `started.start()` thực sự khởi động một luồng mang tên `worker-started` để chạy `job`. `Thread.currentThread()` lúc đó trả về luồng mới.
4. `started.join()` chờ luồng kết thúc, vì vậy dòng kiểm tra trạng thái sau đó in `TERMINATED`. Không có `join()`, luồng có thể còn đang chạy khi `main` kiểm tra.

Hai dòng đầu ra của ví dụ có thứ tự xác định nhờ `run()` đồng bộ, còn hai dòng cuối có thứ tự xác định nhờ `join()`. Trong một chương trình khác, các câu `println` từ `main` và worker chạy song song có thể xuất hiện theo thứ tự khác nhau; **không dựa vào thứ tự in ngẫu nhiên để kết luận về lập lịch**.

## 3. `run()` trực tiếp là lời gọi đồng bộ

`Thread` thực hiện `Runnable`; khi tạo `new Thread(job)`, công việc `job` được đặt làm mục tiêu của thread. Trong trường hợp thông thường, khi thực thi `Thread.run()`, thread gọi `job.run()`. Nếu bạn gọi `thread.run()` từ `main`, chuỗi lời gọi được thực thi trên stack của `main`:

```text
main()
  -> Thread.run()
       -> Runnable.run()
            -> công việc
  <- return
main() tiếp tục
```

Do đó:

- `run()` trực tiếp **không khởi tạo concurrency** từ đối tượng `Thread` đó.
- Nếu `run()` mất hai giây, luồng gọi bị giữ trong lời gọi khoảng hai giây (trừ khi tác vụ tự giao việc cho luồng khác). Đây là thực thi đồng bộ.
- `Thread.currentThread()` vẫn trả về luồng gọi.
- `run()` là phương thức Java có thể gọi nhiều lần, vì việc gọi nó **không tiêu thụ quyền `start()` một lần duy nhất** của đối tượng `Thread`.
- Exception không được xử lý bên trong lời gọi `run()` sẽ lan theo stack của luồng gọi, như lời gọi phương thức bình thường.

Không nên dùng tên biến `thread`, tên thread đặt trong constructor hoặc sự hiện diện của đối tượng `Runnable` để suy ra chương trình thực sự chạy đa luồng. Quan sát `Thread.currentThread()` và cách khởi động mới cho biết ngữ cảnh thực thi.

## 4. `start()` là thao tác khởi động luồng mới

Với một đối tượng `Thread` đang ở trạng thái `NEW`, gọi `start()` đăng ký yêu cầu khởi động để JVM sắp lịch thực thi `run()`. JVM gọi `run()` trên luồng mới; người lập trình **không cần và không nên gọi `run()` thủ công sau `start()` để khởi động task**.

Điều `start()` **không** cam kết:

- Nó không bảo đảm worker đã thực hiện câu lệnh đầu tiên khi `start()` trả về.
- Nó không bảo đảm worker hoặc `main` luôn chạy trước.
- Nó không chờ công việc hoàn tất. Muốn chờ, dùng `join()` hoặc cơ chế như `Future.get()`.
- Nó không tự bảo đảm việc truy cập dữ liệu chung là an toàn trước race condition.
- Nó không bảo đảm công việc chạy trên một lõi CPU khác; mức song song phụ thuộc bộ lập lịch và phần cứng.

`start()` tạo một nhánh tiến triển đồng thời về mặt thực thi. Trên CPU một lõi, hai luồng vẫn có thể chạy xen kẽ; với nhiều lõi, chúng có thể thực sự chạy song song.

### `start()` chỉ được gọi thành công một lần cho mỗi đối tượng `Thread`

Sau khi một thread đã được khởi động, dù đang chạy hay đã kết thúc, **không được khởi động lại chính đối tượng đó**. Gọi `start()` lần nữa ném `IllegalThreadStateException` (một `RuntimeException`). Nếu muốn chạy lại công việc, tạo đối tượng `Thread` mới hoặc gửi task mới vào executor.

Ví dụ `StartOnceDemo.java`:

```java
public class StartOnceDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable job = () -> System.out.println("Thực thi công việc");

        Thread direct = new Thread(job);
        direct.run();
        direct.run();
        System.out.println("direct state: " + direct.getState());

        Thread worker = new Thread(job);
        worker.start();
        worker.join();

        try {
            worker.start();
        } catch (IllegalThreadStateException e) {
            System.out.println("Không thể start lại cùng Thread");
        }
    }
}
```

```bash
javac StartOnceDemo.java
java StartOnceDemo
```

Kết quả:

```text
Thực thi công việc
Thực thi công việc
direct state: NEW
Thực thi công việc
Không thể start lại cùng Thread
```

Hai lần `direct.run()` khiến cùng một `Runnable` chạy hai lần trên `main`, nhưng `direct` vẫn `NEW`. `worker.start()` thực thi công việc trên thread mới đúng một lần; lần `start()` thứ hai ném exception. `join()` giúp các dòng của worker hoàn tất trước đoạn bắt exception, nên thứ tự đầu ra xác định.

Đặc biệt, **“có thể gọi `run()` nhiều lần” không có nghĩa “có thể khởi động cùng `Thread` nhiều lần”**. `run` là phương thức, còn `start` kích hoạt vòng đời của đối tượng luồng.

## 5. Phân biệt `Runnable.run()`, `Thread.run()` và ghi đè `run()`

Có hai cách thường gặp để định nghĩa công việc chạy trong thread.

### 5.1. Truyền `Runnable` vào `Thread`

```java
Runnable job = () -> System.out.println(Thread.currentThread().getName());
Thread worker = new Thread(job, "report-worker");
worker.start();
```

Đây là **đoạn mã minh họa** (chưa phải một lớp có `main`). `Runnable` mô tả công việc; `Thread` cung cấp ngữ cảnh thực thi. Khi `start()` khởi động worker, phương thức `Thread.run()` mặc định thực thi `job.run()` trên worker. Cách này tách trách nhiệm mô tả công việc khỏi quản lý vòng đời luồng.

### 5.2. Kế thừa `Thread` và ghi đè `run()`

```java
class ReportThread extends Thread {
    @Override
    public void run() {
        System.out.println(Thread.currentThread().getName());
    }
}
```

Đây là **định nghĩa lớp minh họa**. `new ReportThread().start()` thực thi phương thức `run()` đã ghi đè trên luồng mới. `new ReportThread().run()` chỉ gọi phương thức đã ghi đè trên luồng hiện tại.

Khi một lớp con ghi đè `run()`, việc có truyền thêm `Runnable` vào constructor hay không **không tự bảo đảm mục tiêu `Runnable` đó sẽ được gọi**: phương thức `run()` của lớp con quyết định có gọi `super.run()` hoặc gọi target hay không. Khi không cần tùy biến cơ chế quản lý thread, thiết kế dựa trên `Runnable`/`Callable` và executor thường đơn giản, dễ tái sử dụng hơn.

### 5.3. `Thread.currentThread()` không phải biến `this`

Trong phương thức `run()` của lớp `ReportThread`:

- `this` chỉ đối tượng `ReportThread` đang chứa phương thức.
- `Thread.currentThread()` chỉ thread **đang thực thi câu lệnh**.

Sau `start()`, thông thường hai tham chiếu đó cùng chỉ worker. Khi `main` gọi `worker.run()` trực tiếp, `this` vẫn là `worker` nhưng `Thread.currentThread()` là `main`. Đây là cách kiểm tra chính xác nhất khi học sự khác biệt giữa hai phương thức.

## 6. Đồng bộ trình tự bằng `join()`, không bằng `run()`

Người mới đôi khi chọn `run()` vì muốn “đợi cho xong”. Cách đó biến công việc thành cuộc gọi tuần tự, bỏ đi khả năng đồng thời. Nếu cần worker chạy riêng nhưng phải chờ kết quả ở một điểm xác định, dùng `start()` kết hợp `join()`:

```java
Thread worker = new Thread(() -> performWork());
worker.start();

// main có thể làm việc độc lập tại đây.
worker.join(); // Chờ worker kết thúc trước khi tiếp tục.
```

Đây là **đoạn mã minh họa**, trong đó `performWork()` là phương thức do ứng dụng định nghĩa. `join()` có thể ném `InterruptedException`; chương trình thực tế cần truyền tiếp exception hoặc xử lý tín hiệu ngắt đúng cách.

Về bản chất, `join()` làm cho main chờ sau khi đã cho phép worker thực thi độc lập một khoảng thời gian. Với `run()`, toàn bộ công việc đã nằm ngay trong lời gọi trên main; không có worker mới để `join()` đợi.

## 7. `start()` tạo quan hệ happens-before; `run()` không tạo cạnh khởi động luồng

Java Memory Model định nghĩa quan hệ **happens-before** để mô tả các bảo đảm về thứ tự và khả năng nhìn thấy thay đổi bộ nhớ giữa các thread:

- Các hành động của luồng gọi **trước lời gọi `thread.start()` thành công** xảy ra trước những hành động được luồng mới thực hiện.
- Mọi hành động của một thread xảy ra trước khi một thread khác **hoàn tất `join()` thành công trên thread đó**.
- Các bảo đảm riêng khác vẫn cần dùng khi truy cập chung: `synchronized`, `volatile`, các kiểu atomic hoặc collection concurrent tùy trường hợp.

Ví dụ `StartVisibilityDemo.java`:

```java
public class StartVisibilityDemo {
    private static int input;
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        input = 21;

        Thread worker = new Thread(() -> result = input * 2);
        worker.start();
        worker.join();

        System.out.println("result=" + result);
    }
}
```

```bash
javac StartVisibilityDemo.java
java StartVisibilityDemo
```

Kết quả:

```text
result=42
```

`input = 21` xảy ra trước `start()`, vì vậy worker được bảo đảm nhìn thấy cập nhật đó theo quan hệ happens-before. Ghi `result` của worker được bảo đảm nhìn thấy sau `join()` hoàn tất. Ví dụ không cần `volatile` bởi vì hai cạnh đồng bộ nêu trên đã thiết lập thứ tự cần thiết.

Nhưng thay `worker.join()` bằng vòng lặp đọc `result` không có đồng bộ có thể khiến mã mắc lỗi về visibility; chỉ `start()` không bảo đảm mọi lần ghi trong tương lai sẽ được quan sát an toàn bởi main. Và gọi `worker.run()` trực tiếp thực hiện các câu lệnh theo thứ tự chương trình trên main, **không tạo một quan hệ khởi động giữa hai thread**, vì chẳng có thread thứ hai nào được khởi động.

## 8. Exception: chạy trên caller hay trên worker?

Khi `run()` được gọi trực tiếp, một exception không được bắt trong `run()` lan về luồng gọi. Khi `run()` được JVM thực thi sau `start()`, một exception không được xử lý xảy ra **trong worker**; `try/catch` quanh `thread.start()` ở main không bắt được exception ném sau đó trong worker.

Tạo tệp `ThreadExceptionDemo.java`:

```java
public class ThreadExceptionDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable failure = () -> {
            throw new IllegalStateException("boom");
        };

        Thread direct = new Thread(failure, "direct");
        try {
            direct.run();
        } catch (IllegalStateException e) {
            System.out.println("main bắt được: " + e.getMessage());
        }

        Thread worker = new Thread(failure, "worker");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("handler: " + thread.getName()
                        + " -> " + error.getMessage()));
        worker.start();
        worker.join();
    }
}
```

```bash
javac ThreadExceptionDemo.java
java ThreadExceptionDemo
```

Kết quả:

```text
main bắt được: boom
handler: worker -> boom
```

Lần thứ nhất, `direct.run()` ném lỗi trên stack của main nên `catch` ở main xử lý được. Lần thứ hai, worker ném exception trên stack của nó; `UncaughtExceptionHandler` được gắn cho worker xử lý thông tin lỗi. `join()` chờ worker chấm dứt nhưng không tự ném lại exception của worker sang main.

Trong ứng dụng cần thu thập kết quả hoặc lỗi của task, `ExecutorService.submit` cùng `Future.get` có thể phù hợp hơn: `get` báo lỗi task thông qua `ExecutionException` và giúp caller chủ động xử lý. Việc báo lỗi của executor là cơ chế quản lý task, không thay đổi ngữ nghĩa của `Thread.start()` và `Thread.run()`.

## 9. Trạng thái của đối tượng `Thread` và những hiểu lầm thường gặp

Các trạng thái quan sát qua `Thread.getState()` gồm `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và `TERMINATED`. Việc quan sát tức thời bị ảnh hưởng bởi lập lịch; không nên viết chương trình phụ thuộc vào kết quả kiểm tra trạng thái giữa hai câu lệnh đang cạnh tranh.

| Thao tác | Thread mới được khởi động? | Ngữ cảnh thực thi `run()` | Tác động lên vòng đời đối tượng `thread` |
| --- | --- | --- | --- |
| `new Thread(job)` | Chưa | Chưa chạy task | `NEW` |
| `thread.run()` khi thread chưa start | Không | Luồng gọi, ví dụ `main` | Vẫn `NEW` |
| `thread.start()` thành công | Có | Luồng đại diện bởi `thread` | Rời `NEW`, về sau `TERMINATED` |
| `thread.join()` sau `start()` | Không tạo thêm | Không tự chạy lại task | Caller đợi thread kết thúc |
| Gọi `start()` lần thứ hai | Không | Không chạy task lần mới | Ném `IllegalThreadStateException` |

**Một điểm tinh tế:** `run()` là phương thức có thể gọi trực tiếp theo cú pháp Java, nhưng đối tượng `Thread` còn có trạng thái nội bộ do JVM quản lý. Không nên lạm dụng `thread.run()` làm API chạy công việc ở nhiều thời điểm. Nếu muốn gọi công việc tuần tự, gọi trực tiếp `job.run()` hoặc tách logic thành phương thức dịch vụ bình thường để ý định rõ ràng.

## 10. Virtual thread cũng có sự khác biệt `start`/`run`

Từ Java 21, virtual thread là một `Thread` do JVM quản lý, tối ưu cho nhiều công việc I/O-bound đang chờ. Nó vẫn tuân theo nguyên tắc căn bản:

- `Thread.ofVirtual().unstarted(job)` tạo virtual thread ở trạng thái chưa khởi động.
- Gọi `virtual.start()` khởi động **virtual thread mới** và cho JVM lập lịch nó lên carrier.
- Gọi `virtual.run()` trực tiếp trên đối tượng chưa start **không khởi động virtual thread**; công việc (nếu được thực thi theo phương thức được gọi) chạy trên caller. Để chạy công việc ảo đúng mục đích, luôn dùng API `start()` hoặc executor tạo virtual thread.
- `Thread.ofVirtual().start(job)` kết hợp tạo và khởi động, tương đương mục đích với tạo thread chưa start rồi gọi `start()`.
- `Executors.newVirtualThreadPerTaskExecutor()` tạo virtual thread mới cho mỗi task được gửi vào executor; đây không phải lời gọi trực tiếp `run()` trên main.

Ví dụ `VirtualStartDemo.java` (JDK 21+):

```java
public class VirtualStartDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread virtual = Thread.ofVirtual().unstarted(() ->
                System.out.println("isVirtual="
                        + Thread.currentThread().isVirtual()));

        virtual.start();
        virtual.join();
        System.out.println("done=" + !virtual.isAlive());
    }
}
```

```bash
javac VirtualStartDemo.java
java VirtualStartDemo
```

Kết quả:

```text
isVirtual=true
done=true
```

`Thread.currentThread().isVirtual()` được thực thi **bên trong** virtual thread sau khi `start()`, vì vậy là `true`. Dòng `done=true` chỉ in sau `join()`. Virtual thread không phải “giả lập” đồng thời: nó có danh tính và vòng đời luồng Java riêng, dù JVM có thể gắn/tháo nó khỏi các carrier thread khi chờ I/O.

## 11. Khi nào dùng `start()`, khi nào dùng `run()`, khi nào dùng executor?

### Muốn một công việc chạy độc lập với luồng gọi

Dùng `thread.start()`. Quản lý rõ vòng đời, ngắt và dọn dẹp tài nguyên; nếu cần kết quả thì kết hợp cơ chế chờ thích hợp. Với vài luồng cố định có vai trò rõ, thao tác trực tiếp với `Thread` có thể đủ đơn giản.

### Muốn chạy đồng bộ một công việc đơn lẻ

Gọi **chính phương thức thực hiện công việc**, chẳng hạn `job.run()` hoặc `service.perform()`. Gọi `thread.run()` trực tiếp về mặt kỹ thuật có thể thực thi cùng công việc nhưng gây hiểu nhầm rằng bạn đang khởi động thread.

### Muốn quản lý nhiều task, kết quả, hàng đợi và hủy

Dùng `ExecutorService`. Một pool cố định dùng lại platform thread cho nhiều task; `newVirtualThreadPerTaskExecutor()` tạo virtual thread mới cho từng task khi phù hợp với I/O-bound. Khác nhau ở chính sách thực thi, nhưng cả hai giúp tách **task** khỏi chi tiết trực tiếp gọi `Thread.start()`. Khi dùng executor, chờ kết quả bằng `Future.get()` hoặc cơ chế phù hợp; đừng gọi `run()` thủ công trên đối tượng `Thread` do executor quản lý.

Số thread nhiều không tự làm hệ thống nhanh hơn. Nếu tác vụ bị giới hạn bởi CPU, số lõi là nút thắt; nếu chờ kết nối mạng hoặc cơ sở dữ liệu, còn có connection pool, giới hạn hệ thống đích, timeout và an toàn dữ liệu. Virtual thread không làm các tài nguyên bên ngoài trở nên vô hạn.

## 12. Lỗi phổ biến và cách sửa

**Lỗi 1 — tưởng đã chạy đa luồng:**

```java
Thread t = new Thread(() -> doWork());
t.run(); // Sai nếu mục tiêu là khởi động luồng mới.
```

Đoạn mã minh họa, với `doWork()` do ứng dụng định nghĩa. Sửa thành `t.start()`, rồi quyết định có cần `t.join()` hay không.

**Lỗi 2 — gọi cả `start()` và `run()` vì muốn “bắt đầu chắc chắn”:**

```java
Thread t = new Thread(() -> doWork());
t.start();
t.run(); // Có thể thực thi thêm công việc trên caller!
```

Đây không phải cách đợi worker. Có nguy cơ logic của `doWork()` chạy hai lần hoặc cạnh tranh dữ liệu với chính worker. Nếu muốn chờ thread đã khởi động, gọi `t.join()`; nếu chỉ muốn gọi lại task một cách tuần tự thì dùng API công việc rõ ràng.

**Lỗi 3 — gọi `start()` lại sau khi worker xong:** một `Thread` không thể restart. Tạo thread mới hoặc dùng executor nhận task mới.

**Lỗi 4 — cho rằng `start()` chờ xong rồi mới trả về:** `start()` chỉ khởi động. Muốn quan sát kết quả sau worker, dùng `join()`/`Future.get()` và thiết lập đồng bộ thích hợp.

**Lỗi 5 — nghĩ `start()` tự bảo vệ biến dùng chung:** quan hệ happens-before tại điểm khởi động và join không thay thế mọi đồng bộ trong lúc hai thread cùng sửa dữ liệu. Với bộ đếm dùng chung, `counter++` vẫn có thể mất cập nhật; cân nhắc `AtomicInteger`, `synchronized` hoặc cấu trúc concurrent.

**Lỗi 6 — bắt exception quanh `start()` để chặn lỗi của task:** exception ném sau đó trong worker không tự quay về stack của caller. Dùng xử lý lỗi bên trong task, `UncaughtExceptionHandler` hoặc cơ chế thu thập lỗi của executor.

## 13. Kiểm tra hiểu bài

1. **Đoạn sau có chạy trên luồng mới không?**
   `Thread t = new Thread(() -> System.out.println(Thread.currentThread().getName())); t.run();`
   
   **Trả lời:** Không. Lời gọi `run()` thực thi trên luồng gọi, thường là `main`. Đối tượng `t` vẫn `NEW` nếu chưa được `start()`.
2. **Sau `t.start()`, có được gọi `t.start()` lần nữa khi t đã `TERMINATED` không?**
   
   **Trả lời:** Không. Một đối tượng `Thread` chỉ được khởi động thành công một lần. Lần sau ném `IllegalThreadStateException`.
3. **Nếu `main` cần làm tác vụ A trong lúc worker làm B rồi mới sử dụng kết quả B, nên dùng `run()` hay `start()`?**
   
   **Trả lời:** `start()` để B tiến triển độc lập; main làm A; sau đó chờ bằng `join()` hoặc lấy kết quả qua `Future`. Dùng `run()` sẽ chạy B đồng bộ trước A nếu đặt lời gọi B trước.
4. **Vì sao `Thread.currentThread() == t` có thể sai bên trong `t.run()`?**
   
   **Trả lời:** Khi `t.run()` được gọi trực tiếp trên main, `this` vẫn là `t` nhưng thread đang chạy là main; chỉ `start()` mới khiến JVM thực thi `run()` trong luồng t.
5. **Có thể thay `t.start()` bằng `t.run()` để tránh race condition không?**
   
   **Trả lời:** Điều đó chỉ làm lời gọi cụ thể trở thành tuần tự và có thể che dấu tranh chấp trong bài thử. Nó đánh mất concurrency, không sửa cơ chế truy cập chung nếu các thread khác vẫn hoạt động.
6. **`t.start()` có bảo đảm main nhìn thấy mọi biến worker sửa ngay lập tức không?**
   
   **Trả lời:** Không. `start()` bảo đảm các hành động trước start của caller được worker nhìn thấy theo happens-before; để main thấy kết quả sau khi worker hoàn tất có thể dùng `join()` hoặc cơ chế đồng bộ khác.

## 14. Ghi nhớ cốt lõi

**`start()` khởi động luồng Java mới; `run()` trực tiếp là lời gọi phương thức bình thường trên luồng hiện tại.** Một đối tượng `Thread` chỉ được `start()` thành công một lần, còn phương thức `run()` có thể được gọi như phương thức thông thường nhưng không mang ý nghĩa khởi động. Khi cần đồng thời, hãy khởi động rồi quản lý kết thúc bằng `join()` hoặc executor; khi cần đồng bộ, gọi trực tiếp logic công việc. Phân biệt hai cách gọi giúp đọc đúng trạng thái `Thread`, thứ tự thực thi, propagation của exception và các bảo đảm bộ nhớ trong chương trình Java.
