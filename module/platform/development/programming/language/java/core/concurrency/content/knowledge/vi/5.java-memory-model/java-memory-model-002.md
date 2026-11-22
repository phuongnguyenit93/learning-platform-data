# Happens-before và vai trò trong tính đúng đắn của Java Concurrency

Khi hai thread truy cập chung dữ liệu, không thể chỉ nhìn thứ tự câu lệnh trong mã nguồn để kết luận thread đọc sẽ thấy kết quả mới nhất. Java Memory Model (JMM) mô tả những cách quan sát bộ nhớ nào được phép khi chương trình chạy đồng thời. **Happens-before (HB)** là quan hệ thứ tự để lập luận rằng một nhóm thao tác ghi đã được công bố và có thể được quan sát đúng bởi các thao tác đọc về sau.

HB giúp trả lời các câu hỏi: Khi worker ghi dữ liệu rồi kết thúc, main đọc được gì? Ghi một cờ `volatile` có đủ để công bố dữ liệu trước đó không? Vì sao `synchronized` vừa tránh chen ngang vừa mang hiệu ứng bộ nhớ? Vì sao `Thread.sleep()` không giải quyết data race? Từ các câu hỏi đó, chúng ta có thể phân biệt **visibility**, **ordering**, **atomicity** và chứng minh chương trình đúng theo hợp đồng Java.

Đây là bài **Java Memory Model trong Java Concurrency nói chung**. Các cơ chế riêng của Spring nằm ngoài phạm vi.

## 1. Vấn đề: thứ tự trong source chưa đủ cho đa luồng

Xét trạng thái chia sẻ:

~~~java
final class Message {
    int data;
    boolean ready;
}
~~~

Writer:

~~~java
message.data = 42;
message.ready = true;
~~~

Reader:

~~~java
while (!message.ready) {
    // Đợi writer.
}
System.out.println(message.data);
~~~

Đây là **các mảnh minh họa lỗi**, chưa phải chương trình độc lập. Nếu `message` được truy cập bởi hai thread mà không đồng bộ, reader không có bảo đảm cần thiết rằng nó sẽ thấy `ready == true`, hoặc rằng khi thấy ready thì cũng nhìn được `data == 42`. Compiler và phần cứng có thể tối ưu một cách hợp lệ theo JMM, và các thao tác đọc/ghi thường không tự thiết lập việc công bố dữ liệu qua thread khác.

Vòng `while` còn là busy waiting: nó có thể chạy liên tục, lãng phí CPU. Thêm `Thread.sleep(10)`, `Thread.yield()` hoặc `Thread.onSpinWait()` có thể thay đổi tốc độ/lịch polling, nhưng **không tạo quan hệ HB** cần thiết.

Ta cần một giao thức đồng bộ thực sự: `volatile`, monitor `synchronized`, `Lock`, `CountDownLatch`, `Future`, `Thread.join()`, queue đồng thời hoặc API có memory-consistency contract rõ ràng.

### 1.1 Ba thuộc tính không đồng nghĩa

| Thuộc tính | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| **Visibility** | Đảm bảo đọc quan sát cập nhật theo các ràng buộc JMM. | Thread đọc cờ hoặc dữ liệu cũ khi chưa được publish. |
| **Ordering** | Đảm bảo thứ tự quan sát cần thiết giữa các hành động. | Reader thấy tín hiệu nhưng chưa có bảo đảm payload đã publish. |
| **Atomicity** | Một thao tác/cụm thao tác quan trọng diễn ra không bị chen giữa theo giao thức. | Hai thread cùng thực hiện `count++` gây mất cập nhật. |

**HB là nền tảng visibility và ordering**. HB không tự biến phép tăng ghép thành atomic và không thay thế việc bảo vệ invariant nghiệp vụ.

## 2. Định nghĩa và cách đọc quan hệ happens-before

Ký hiệu `A →HB B` nghĩa là hành động A *happens-before* hành động B. Đây là **quan hệ thứ tự một phần** theo Java Memory Model, không phải cách đo A xảy ra trước B bao nhiêu mili giây theo đồng hồ. HB được hình thành bởi:

- **Program order:** trong cùng thread, những hành động đứng trước theo thứ tự chương trình tạo các cạnh HB đến những hành động sau.
- **Synchronizes-with:** những quan hệ đồng bộ giữa thread được JMM định nghĩa, ví dụ unlock→lock trên cùng monitor hoặc volatile write→subsequent volatile read.
- **Transitivity (bắc cầu):** nếu A →HB B và B →HB C thì A →HB C.

Hãy hình dung:

~~~text
Writer                              Reader
---------------------------         ----------------------------
ghi payload = 42                    ...
      |
      v
ghi volatile ready = true --------> đọc volatile ready == true
                                          |
                                          v
                                     đọc payload
~~~

Mũi tên ngang là cạnh đồng bộ của volatile khi reader đọc tín hiệu do writer công bố. Hai mũi tên dọc là program order. Theo tính bắc cầu, `ghi payload = 42 →HB đọc payload`. Nếu không có một writer khác thay đổi payload cạnh tranh, reader có cơ sở để thấy 42.

**Không được đồng nhất HB với lịch chạy vật lý.** JVM/CPU vẫn có thể tái sắp xếp instruction miễn giữ những kết quả quan sát hợp lệ theo JMM. Hai hành động có thể xảy ra cách nhau rất lâu mà vẫn thiếu cạnh HB nếu không có một cơ chế đồng bộ tương ứng.

**HB cũng không phải điều kiện đủ duy nhất cho mọi kết quả đọc:** nếu có nhiều lần ghi cùng biến và các quan hệ thứ tự khác, phải xét tất cả phép ghi cạnh tranh và quy tắc đọc giá trị của JMM. Khi kết luận reader thấy một giá trị cụ thể, luôn nói rõ những giả định như “chỉ một writer ghi biến này trước tín hiệu”.

## 3. Những quy tắc HB cơ bản của JMM

| Nguồn quan hệ | Cạnh happens-before quan trọng | Điều kiện |
| --- | --- | --- |
| Thứ tự trong thread | Hành động trước →HB hành động sau trong program order. | Cùng thread; không tự đồng bộ với thread khác. |
| Monitor (`synchronized`) | Unlock một monitor →HB mọi lock tiếp theo trên chính monitor ấy. | Cùng monitor; mọi đường truy cập phải dùng protocol phù hợp. |
| Biến `volatile` | Ghi volatile →HB những lần đọc volatile về sau của **cùng biến** trong synchronization order. | Không có tác dụng atomic cho phép `++` nhiều bước. |
| `Thread.start()` | Lời gọi `start()` →HB mọi hành động trong thread được khởi chạy. | Các phép ghi của caller trước start được công bố theo quy tắc. |
| Kết thúc thread | Mọi hành động trong worker →HB thread khác khi nó phát hiện worker kết thúc, chẳng hạn qua `join()` thành công. | Timed join hết hạn lúc worker còn sống không bảo đảm completion. |
| Interruption | `interrupt()` →HB điểm thread bị interrupt phát hiện tín hiệu đó. | Interruption là yêu cầu hợp tác, không phải ép dừng. |
| Khởi tạo mặc định | Default initialization của object →HB các hành động khác trên object. | Không chứng minh mọi field đã được constructor cấu hình đúng cách khi object publish không an toàn. |
| Tính bắc cầu | A →HB B và B →HB C ⇒ A →HB C. | Nối các cạnh program order và synchronization. |

Quan hệ *synchronizes-with* chỉ những cạnh đồng bộ cơ bản. *Happens-before* còn gồm thứ tự chương trình và chuỗi cạnh bắc cầu; bởi vậy có thể có HB từ một lần ghi thông thường trước volatile đến một lần đọc thông thường sau volatile mà không phải biến nào cũng mang từ khóa `volatile`.

Java còn định nghĩa *synchronization order*, một thứ tự tổng thể cho các synchronization actions phù hợp program order của mỗi thread. Không cần dự đoán toàn bộ thứ tự này khi viết ứng dụng, nhưng cần hiểu rằng không thể ghép tùy tiện một volatile write với bất kỳ volatile read nào để chứng minh điều mình muốn.

## 4. Dùng volatile để publish dữ liệu

Sửa class ban đầu:

~~~java
final class Message {
    int data;
    volatile boolean ready;
}
~~~

Writer thực hiện:

~~~java
message.data = 42;     // Ghi dữ liệu trước.
message.ready = true;  // Phát tín hiệu bằng volatile write.
~~~

Reader:

~~~java
if (message.ready) {   // Volatile read thấy true của writer.
    System.out.println(message.data);
}
~~~

Các mảnh trên giả định `message` đã được khai báo. Khi reader thấy tín hiệu thích hợp, cạnh volatile write→read cùng program order cho phép suy ra lần ghi `data = 42` xảy ra trước lần đọc `data` theo HB. Với một writer duy nhất và không có lần sửa cạnh tranh về `data`, reader có thể thấy giá trị 42.

**Thứ tự hai lệnh rất quan trọng.** Nếu writer đặt `ready = true` rồi mới ghi `data = 42`, reader có thể nhận tín hiệu trước khi dữ liệu được chuẩn bị. Nếu reader đọc `data` trước khi đọc `ready`, phép đọc ấy không nhận được bảo đảm publish từ tín hiệu phía sau.

**Giới hạn của volatile:**

- Một phép đọc/ghi volatile đơn lẻ có visibility và ordering theo JMM; nó không biến nhiều câu lệnh thành một giao dịch.
- `volatile int count; count++` vẫn có thể mất cập nhật vì `++` là read–modify–write.
- Một `volatile Message reference` không khiến mọi field bên trong Message tự được bảo vệ khi object tiếp tục bị sửa không đồng bộ sau khi publish.
- Cờ volatile không phải cơ chế chờ hiệu quả cho thời gian dài. Với giao thức thông báo/hoàn tất, ưu tiên blocking primitive như latch hoặc future.

### 4.1 Ví dụ runnable: công bố và quan sát bằng volatile

Ví dụ bên dưới dùng một volatile flag và vòng spin ngắn **chỉ để quan sát rõ cơ chế**; trong sản phẩm nên dùng blocking primitive. Worker cố ý được đợi bằng `join()` để chương trình đóng đúng vòng đời.

Tạo `VolatileHappensBeforeDemo.java`:

~~~java
public final class VolatileHappensBeforeDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Payload: " + payload);
        }, "reader");

        Thread writer = new Thread(() -> {
            payload = 42;
            ready = true;
        }, "writer");

        reader.start();
        writer.start();
        writer.join();
        reader.join();
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac VolatileHappensBeforeDemo.java
java VolatileHappensBeforeDemo
~~~

Kết quả khi thread được scheduler cấp cơ hội chạy bình thường:

~~~text
Payload: 42
~~~

`Thread.onSpinWait()` chỉ là CPU hint, **không** tạo HB. Chính write/read của biến `ready` là cạnh đồng bộ. Mặc dù có visibility đúng, vòng spin vẫn có thể chiếm CPU và bị starvation nếu scheduler không cho một bên chạy. Trong phần ứng dụng thực tế bên dưới, chúng ta dùng `CountDownLatch.await()` thay kiểu chờ này.

## 5. Synchronized: vừa loại trừ chen ngang vừa publish bộ nhớ

Một monitor lock đem lại hai tác dụng khác nhau:

1. **Mutual exclusion:** chỉ một thread giữ cùng monitor tại một thời điểm. Các phép ghi/đọc trong critical section được bảo vệ khỏi chen ngang bởi thread khác cũng dùng monitor ấy.
2. **Happens-before:** unlock một monitor xảy ra trước lần lock về sau trên **cùng monitor**. Trạng thái đã ghi dưới protocol được công bố theo JMM.

Ví dụ Java 17+ tạo `SynchronizedHappensBeforeDemo.java`:

~~~java
public final class SynchronizedHappensBeforeDemo {
    private static final Object LOCK = new Object();
    private static int total;

    public static void main(String[] args) throws InterruptedException {
        Runnable add = () -> {
            for (int i = 0; i < 1_000; i++) {
                synchronized (LOCK) {
                    total++;
                }
            }
        };

        Thread first = new Thread(add, "first");
        Thread second = new Thread(add, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        synchronized (LOCK) {
            System.out.println("Total: " + total);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SynchronizedHappensBeforeDemo.java
java SynchronizedHappensBeforeDemo
~~~

Stdout:

~~~text
Total: 2000
~~~

Mọi phép `total++` được thực hiện trong cùng monitor `LOCK`, nên không có hai critical section chồng lên nhau. `join()` bảo đảm main đợi cả hai thread kết thúc và công bố những hành động của worker cho main; lần lấy lock cuối cũng tuân thủ monitor protocol.

Nếu chỉ giữ hai lệnh `join()` nhưng bỏ `synchronized` trong worker, kết quả có thể bị mất cập nhật. Join làm kết quả **được nhìn thấy sau khi thread đã chạy xong**, không sửa những race đã xảy ra **trong quá trình chạy**.

Nếu hai thread khóa hai object khác nhau, chúng không cùng một monitor và không có mutual exclusion chung. Đừng kết luận “cả hai nơi đều có synchronized” mà bỏ qua **khóa cụ thể** và **mọi đường truy cập** đến invariant.

## 6. start() và join(): hai chiều công bố theo vòng đời thread

Trong đa số bài toán worker đơn giản, `Thread.start()` và `Thread.join()` đã cung cấp các cạnh HB cần thiết.

Tạo `StartJoinVisibilityDemo.java`:

~~~java
public final class StartJoinVisibilityDemo {
    private static final class Job {
        int input;
        int output;
    }

    public static void main(String[] args) throws InterruptedException {
        Job job = new Job();
        job.input = 21;

        Thread worker = new Thread(() -> {
            job.output = job.input * 2;
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Result: " + job.output);
    }
}
~~~

Chạy:

~~~bash
javac StartJoinVisibilityDemo.java
java StartJoinVisibilityDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Đồ thị lập luận:

~~~text
main: job.input = 21
       |
       v  program order
main: worker.start()
       |
       v  start happens-before worker actions
worker: đọc input, ghi output = 42
       |
       v  termination detected by join
main: worker.join() kết thúc
       |
       v  program order
main: đọc output = 42
~~~

Mặc dù `input` và `output` chỉ là `int` thường, các lần truy cập theo đúng luồng start/join này có một quan hệ HB phù hợp. Không cần đánh dấu mọi trường là volatile nếu **không có thread khác truy cập cạnh tranh trái protocol**.

Lưu ý: `Thread.sleep(100)` của main sau `worker.start()` không thay thế `join()`. Nó chỉ chờ một khoảng thời gian, không bảo đảm worker đã kết thúc và không cung cấp cạnh completion. `join(timeout)` trả về mà worker còn sống cũng chưa bảo đảm toàn bộ kết quả đã publish.

Với API vòng đời, `Thread.isAlive()` trả `false` sau khi thread đã start và kết thúc có thể là một cách phát hiện termination theo JMM, nhưng việc liên tục polling `isAlive()` thường lãng phí CPU. Chọn `join()` để chờ trực tiếp.

## 7. Data race là gì?

Hai access ở các thread khác nhau **xung đột** nếu chúng truy cập cùng một biến và ít nhất một access là write. Khi chúng không được sắp thứ tự bởi HB, chương trình có **data race**.

Ví dụ:

~~~java
int counter; // Trường chia sẻ.

// Thread A:
counter++;

// Thread B:
counter++;
~~~

Đây là mảnh minh họa. Hai lần tăng mỗi lần gồm đọc giá trị cũ, tính giá trị mới, ghi lại; chúng có thể cùng đọc cùng giá trị ban đầu và ghi đè, dẫn đến mất cập nhật.

**JMM có ràng buộc cả chương trình có data race**, nên nói “data race khiến Java được phép làm bất kỳ điều gì” là không chính xác. Nhưng khi thiếu các cạnh HB cần thiết, trực giác “các lệnh source đã chạy theo đúng thứ tự nên chắc chắn đúng” không đủ để chứng minh kết quả.

Một chương trình **correctly synchronized** theo định nghĩa của JMM không có data race trong các execution sequentially consistent của nó. Chương trình như vậy nhận được bảo đảm hành vi có thể giải thích theo *sequential consistency*: các thao tác như thể xen kẽ trong một thứ tự tổng thể tôn trọng thứ tự của từng thread.

Đây là bảo đảm về **hành vi quan sát bộ nhớ**, không có nghĩa các thread thực sự chạy tuần tự, không có tranh chấp CPU hay không có deadlock. Một chương trình hoàn toàn dùng lock đúng vẫn có thể có lỗi logic nghiệp vụ, hoặc chờ vô hạn.

### 7.1 HB không phải atomicity

Giả sử hai thread cùng chạy:

~~~java
if (balance > 0) {
    balance--;
    withdrawals++;
}
~~~

Muốn giữ invariant “số dư không âm, số lượt rút thành công phù hợp”, cần bảo vệ cả thao tác kiểm tra và cập nhật như một critical section. Việc đánh dấu `balance` và `withdrawals` là volatile không biến cụm lệnh thành atomic. Có thể dùng cùng một lock cho tất cả đường đọc/ghi hoặc một atomic state transition được thiết kế cho toàn bộ invariant.

HB chứng minh công bố dữ liệu theo quan hệ thứ tự; atomicity bảo đảm không có thread khác chen ngang một cập nhật cần toàn vẹn. Trong thiết kế concurrent, **phải kiểm tra cả hai**.

## 8. Safe publication của object và final fields

*Safe publication* là chuyển một reference sang thread khác qua cơ chế đồng bộ sao cho trạng thái object đã khởi tạo được nhìn thấy đúng.

Ví dụ rủi ro:

~~~java
final class Settings {
    String host;
    int port;
}

// Thread A, giả định shared là field thường:
Settings value = new Settings();
value.host = "localhost";
value.port = 8080;
shared = value;

// Thread B:
Settings snapshot = shared;
if (snapshot != null) {
    // Không đủ căn cứ để coi host/port đã publish an toàn.
}
~~~

Mảnh trên chưa có khai báo `shared`, là **ví dụ lỗi**, không phải chương trình độc lập. Do writer/reader truy cập reference không đồng bộ, việc reader thấy một reference khác null chưa đủ để kết luận mọi trạng thái khởi tạo đã được quan sát theo protocol an toàn.

Các cách publish phổ biến:

- Ghi reference vào trường `volatile` rồi đọc lại qua cùng trường volatile.
- Sử dụng cùng monitor `synchronized` hoặc `Lock`.
- Truyền object qua `BlockingQueue` hay collection concurrent có hợp đồng memory-consistency tương ứng.
- Lấy object là kết quả từ `Future.get()` sau khi task hoàn thành.
- Công bố qua class initialization hợp lệ của JVM.
- Thiết kế immutable object với final fields và không để `this` escape trong constructor.

### 8.1 Cẩn thận với final

~~~java
final class Endpoint {
    final String host;
    final int port;

    Endpoint(String host, int port) {
        this.host = host;
        this.port = port;
    }
}
~~~

JMM có những bảo đảm khởi tạo đặc biệt cho `final` fields khi constructor hoàn tất đúng và reference không thoát ra ngoài trong lúc xây dựng. Các trường này hữu ích cho immutable object. Nhưng:

- `final` cố định **reference của trường**, không tự làm object mà reference đó trỏ tới trở thành immutable; `final List<String>` vẫn có thể trỏ đến danh sách mutable.
- Những lần sửa trạng thái mutable **sau constructor** vẫn cần đồng bộ.
- Không cho `this` escape bằng cách đăng ký listener hoặc start thread sử dụng object đang xây dựng trước khi constructor hoàn tất.

Ví dụ snapshot publish:

~~~java
final class Config {
    final String host;
    final int port;

    Config(String host, int port) {
        this.host = host;
        this.port = port;
    }
}

final class ConfigHolder {
    private volatile Config current = new Config("localhost", 8080);

    Config readSnapshot() {
        return current;
    }

    void replace(Config next) {
        current = next;
    }
}
~~~

Đây là mảnh minh họa. Writer tạo một `Config` hoàn chỉnh rồi thay reference volatile; reader lấy một instance để dùng trong một thao tác. Nếu gọi `readSnapshot()` nhiều lần, các lần gọi có thể nhận các phiên bản khác nhau. Khi cần snapshot nhất quán xuyên suốt xử lý, hãy lưu reference vào biến local một lần.

## 9. java.util.concurrent cung cấp thêm memory-consistency effects

Ngoài các quan hệ JMM nền tảng, nhiều class concurrent có hợp đồng HB cụ thể:

| API | Quan hệ chính | Giới hạn cần hiểu |
| --- | --- | --- |
| `CountDownLatch` | Hành động trước `countDown()` →HB hành động sau `await()` thành công khi count về 0. | Latch không tự thu thập exception của task; countDown phải đúng mốc completion. |
| `ExecutorService` | Hành động trước submit task →HB hành động trong task; hành động trong task →HB hành động sau khi lấy kết quả qua `Future.get()`. | Submit không đồng nghĩa task đã chạy xong. |
| `Future.get()` | Hành động của task →HB hành động sau khi lấy kết quả qua get. | Cần phân biệt completion, failure, cancellation và timeout. |
| `BlockingQueue` | Hành động trước khi put object →HB hành động sau khi thread khác take/access phần tử theo hợp đồng. | Không tự bảo vệ sửa đổi object sau khi put. |
| `Semaphore` | Hành động trước `release()` →HB hành động sau `acquire()` thành công tương ứng. | Giữ invariant nhiều trường vẫn cần protocol riêng. |
| `Lock` | Các thao tác lock/unlock thành công có memory effects như monitor tương ứng. | Phải lock/unlock đúng cùng cơ chế và nhả trong `finally`. |
| Atomic classes | Các phép đọc/ghi/CAS có memory effects được API mô tả. | Các bước `get()` rồi `set()` không tự gộp thành một atomic transaction. |

Cần đọc hợp đồng **của đúng primitive**. Không suy rằng mỗi lần chạm bất kỳ concurrent collection nào đều công bố mọi cập nhật trên toàn bộ object graph. Các hiệu ứng HB thường áp dụng cho dữ liệu **trước** hành động chuyển giao và việc nhận/truy cập phần tử theo API, không bảo vệ những cập nhật phát sinh sau đó.

### 9.1 Ví dụ Java 17+: không cần volatile khi đã có latch

Tạo tệp `LatchHappensBeforeDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class LatchHappensBeforeDemo {
    private static int result;
    private static final CountDownLatch READY = new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread producer = new Thread(() -> {
            result = 42;
            READY.countDown();
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                READY.await();
                System.out.println("Result: " + result);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac LatchHappensBeforeDemo.java
java LatchHappensBeforeDemo
~~~

Stdout khi không có interruption ngoài:

~~~text
Result: 42
~~~

`result` là một `int` thường. Nhưng `result = 42` xảy ra trước `READY.countDown()`, và reader chỉ đọc result sau `READY.await()` thành công: có cạnh HB do latch. Không cần thêm `volatile` cho result chỉ để publish lần ghi đó.

Lưu ý rằng `CountDownLatch.await()` có thể trả về khi số tín hiệu đạt 0 dù thread producer vẫn chưa hoàn toàn `TERMINATED` ở thời điểm đó; muốn đợi chính vòng đời Thread kết thúc cần `join()`. Ở đây hai lời gọi join còn giúp main kết thúc sau các worker.

## 10. Double-checked locking: thiếu volatile có thể publish sai

Mẫu lazy initialization có hai lượt kiểm tra thường được gọi là *double-checked locking* (DCL). Nếu reference chia sẻ là field thường, nhánh đọc ngoài lock có thể không có HB với nhánh ghi:

~~~java
final class LazyService {
    private static Service instance; // Sai: thiếu volatile.

    static Service getInstance() {
        if (instance == null) {
            synchronized (LazyService.class) {
                if (instance == null) {
                    instance = new Service();
                }
            }
        }
        return instance;
    }
}
~~~

Đây là mảnh lỗi, `Service` chưa được định nghĩa. Chỉ phần kiểm tra bên trong lock được đồng bộ qua monitor. Reader ở nhánh nhanh ngoài lock không có quan hệ publish đầy đủ đối với một lần ghi thường vào `instance`. Sửa field thành:

~~~java
private static volatile Service instance;
~~~

Với volatile reference và protocol đúng, lần khởi tạo, ghi reference và lần đọc reference tương ứng được ordered. Tuy nhiên DCL có nhiều chi tiết dễ sai; với singleton lazy đơn giản, holder idiom có thể dễ đọc hơn:

~~~java
final class Service {
    private Service() {}

    private static final class Holder {
        static final Service INSTANCE = new Service();
    }

    static Service getInstance() {
        return Holder.INSTANCE;
    }
}
~~~

Đây là mảnh minh họa class. Class initialization của JVM có cơ chế đồng bộ tương ứng; khi Holder được khởi tạo lần đầu, singleton được publish theo hợp đồng initialization. Vẫn phải tránh leak `this` trước khi constructor hoàn tất.

## 11. Happens-before không tự bảo đảm liveness

Một chương trình có thể dùng synchronization đúng để đảm bảo state nhất quán nhưng vẫn **không tiến triển**:

- Thread A giữ lock L1 rồi đợi L2; thread B giữ L2 rồi đợi L1: deadlock.
- Một task pool nhỏ chờ kết quả task khác trong chính queue của pool: thread-pool starvation.
- Reader chờ một latch không ai countDown: có thể block mãi.
- Một vòng CAS liên tục retry: có thể có progress toàn hệ thống nhưng một thread riêng lẻ bị starvation.

HB và JMM bàn về **các quan sát bộ nhớ hợp lệ**. Liveness/progress bàn về **điều kiện công việc tiếp tục và kết thúc**. Muốn chương trình thực tế đúng, cần thiết kế cả việc công bố dữ liệu lẫn thời hạn chờ, cancellation, interruption và thứ tự lấy lock.

Đừng dùng việc nhiều thread vẫn chạy CPU làm bằng chứng rằng mọi thao tác sẽ kết thúc. Và không nên dùng `Thread.sleep` để “sửa” race: nó chỉ làm lỗi ít xuất hiện hơn hoặc thay đổi interleaving.

## 12. Các lỗi diễn giải HB thường gặp

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “A chạy trước B theo đồng hồ nên A →HB B.” | HB là quan hệ JMM dựa trên program order/synchronization, không dựa vào khoảng thời gian. |
| “Có `volatile` là mọi thao tác đều atomic.” | Volatile không biến `count++` thành atomic. |
| “`Thread.join()` sửa mất cập nhật giữa worker.” | Join công bố kết quả khi worker đã kết thúc; race trong lúc worker chạy vẫn có thể xảy ra. |
| “Hai khối `synchronized` bất kỳ tạo HB.” | Cần dùng **cùng monitor** trong protocol tương ứng. |
| “Final reference làm toàn bộ object graph immutable.” | Chỉ reference final; object mutable được trỏ tới cần kiểm soát riêng. |
| “Đã có `ready = true` thì mọi phép ghi sau đó cũng được publish.” | HB phát tín hiệu áp dụng cho các hành động đã đứng trước write đồng bộ; các ghi sau cần protocol riêng. |
| “`sleep()`, `yield()`, `onSpinWait()` giúp visibility.” | Chúng không tạo cạnh HB cho dữ liệu chia sẻ. |
| “Log cho ra kết quả đúng chứng minh không có data race.” | Logging và scheduler có thể che giấu race; test hữu hạn không thay chứng minh. |
| “Sequential consistency có nghĩa runtime chạy tuần tự.” | Đây là mô hình kết quả bộ nhớ, không phải yêu cầu scheduler chạy từng thread một. |
| “Dùng AtomicInteger cho một trường bảo vệ mọi invariant.” | Cần phân tích toàn bộ chuyển trạng thái và các field phụ thuộc. |

## 13. Quy trình chứng minh correctness bằng HB graph

Đối với một đoạn code concurrent, thực hiện tuần tự:

1. **Ghi rõ invariant.** Ví dụ “số dư không âm”, “config được đọc theo snapshot nhất quán”, “task chỉ trả kết quả sau khi đã khởi tạo xong”.
2. **Liệt kê tất cả access xung đột.** Thread nào đọc/ghi cùng trường? Có access ngoài lock hay ngoài protocol không?
3. **Đánh dấu program order mỗi thread.** Lần ghi payload nằm trước hay sau tín hiệu? Phép đọc nằm trước hay sau khi nhận tín hiệu?
4. **Tìm cạnh đồng bộ thực sự.** Cùng monitor lock, volatile write/read tương ứng, start/join, latch, future, queue transfer?
5. **Nối cạnh bằng tính bắc cầu.** Có đường A →HB B từ phép ghi cần publish đến phép đọc cần bảo đảm không?
6. **Tính đến writer khác.** Có phép ghi cạnh tranh làm mất kết luận một giá trị cụ thể hoặc tạo data race không?
7. **Kiểm tra atomicity.** Một thao tác gồm nhiều bước có thể bị chen giữa, phá invariant không?
8. **Kiểm tra liveness.** Lock có thể bị giữ mãi, tín hiệu có thể không đến, timeout/interrupt có được xử lý không?
9. **Viết test theo invariant.** Dùng barrier/latch để tái hiện interleaving, test stress có giới hạn; không dùng chỉ `sleep()` làm điều kiện.
10. **Code review lại sau khi sửa.** Thêm một access bỏ qua lock hoặc một writer sau publish có thể phá toàn bộ lập luận cũ.

Ví dụ một giao thức được publish đúng:

~~~text
writer                             reader
------                             ------
payload = 42
   |
   v
volatile ready = true ---------> if (ready)  // volatile read
                                    |
                                    v
                               use(payload)
~~~

Nếu chuyển `use(payload)` lên **trước** `if (ready)` hoặc chuyển `payload = 42` xuống **sau** ghi ready, đường HB bảo đảm dữ liệu không còn giống sơ đồ.

## 14. Test concurrency và giới hạn của việc chạy thử

Không thể dùng “chạy 10.000 lần thấy đúng” để chứng minh một giao thức có HB. Data race phụ thuộc lịch chạy, optimizer, mức tải, runtime và CPU.

- Dùng `CountDownLatch` hoặc `CyclicBarrier` để bắt đầu tác vụ đồng thời và tạo các điều kiện interleaving cụ thể; đừng dùng sleep để phỏng đoán.
- Assert **invariant chính xác**, ví dụ hai thread mỗi thread tăng 1.000 lần phải cho kết quả 2.000, thay vì assert kết quả lớn hơn 0.
- Stress test nhiều lần với nhiều thread để tìm lỗi nhưng phải chấp nhận rằng không quan sát thấy lỗi chưa chứng minh chương trình an toàn.
- Dùng công cụ nghiên cứu concurrency như **OpenJDK jcstress** khi cần khảo sát những kết quả quan sát được của các đoạn mã nhỏ; đọc đúng các outcome được JMM cho phép.
- Review HB graph cùng với protocol atomicity: đây là phần kiểm chứng mà test hữu hạn không thể thay thế.
- Log/println trong đoạn bị race có thể vô tình thêm đồng bộ hoặc làm thay đổi scheduling, che dấu lỗi; tránh dựa vào hiện tượng đó.

Thread dump hỗ trợ xem thread `BLOCKED` hoặc `WAITING` khi chương trình kẹt nhưng không tự chứng minh một field đã publish an toàn. Giữ mục tiêu quan sát đúng: HB cho memory consistency, thread dump cho điều tra runtime/liveness.

## 15. Tự kiểm tra kiến thức

**1.** Writer ghi `data=42` rồi `volatile ready=true`; reader thấy `ready==true` rồi mới đọc data. Vì sao có thể kết luận đọc 42 nếu không có writer khác?  
**Đáp:** Program order của writer, cạnh volatile write→read và program order của reader tạo đường HB từ ghi data đến đọc data.

**2.** Nếu bỏ volatile ở ready nhưng giữ nguyên thứ tự code thì có bảo đảm tương tự không?  
**Đáp:** Không. Thiếu synchronization; thread đọc và ghi có thể bị data race.

**3.** `Thread.sleep(100)` sau khi start worker có thay `join()` được không?  
**Đáp:** Không. Sleep không có cạnh HB với việc worker kết thúc; join nhận biết completion.

**4.** Hai thread cùng chạy `volatile int counter; counter++`, có chắc đủ 2.000 lượt tăng không?  
**Đáp:** Không. Phép tăng ghép không atomic; cần lock hoặc atomic increment.

**5.** Tại sao hai `synchronized` dùng hai object khác nhau chưa bảo vệ được một biến chia sẻ?  
**Đáp:** Mutual exclusion và cạnh unlock→lock chỉ áp dụng cho cùng monitor phù hợp.

**6.** Sau `worker.join()`, main thấy output đã ghi trong worker, nhưng hai worker trước đó cùng cập nhật sai. Join có sửa lỗi không?  
**Đáp:** Không. Join tạo visibility sau termination, không ngăn race và lost update đã xảy ra.

**7.** Một object có `final List<String> items`. Có thể cập nhật list từ nhiều thread mà không có synchronization không?  
**Đáp:** Không. Final chỉ cố định reference; object được trỏ tới còn mutable.

**8.** `CountDownLatch.await()` trả về khi count bằng 0. Reader có nhìn thấy trạng thái producer ghi trước `countDown()` không?  
**Đáp:** Có theo hợp đồng memory-consistency của latch khi await trả về thành công.

**9.** Chương trình không có data race có tự động không deadlock không?  
**Đáp:** Không. Safety/visibility và liveness là hai chiều correctness khác nhau.

**10.** Cần những gì để chứng minh một invariant concurrent?  
**Đáp:** Xác định access, lập HB graph, tìm writer cạnh tranh, kiểm tra atomicity của thao tác ghép và xét liveness. Test chỉ bổ trợ lập luận.

**Ghi nhớ:** *Happens-before* giúp chứng minh việc **công bố và quan sát dữ liệu đúng thứ tự** giữa các thread. Để chương trình đúng toàn diện, còn phải bảo vệ **atomicity và invariant** cũng như giải quyết **liveness**. Hãy dựa vào hợp đồng rõ ràng của `volatile`, `synchronized`, `start()/join()` và `java.util.concurrent` thay vì độ trễ, log hay tình cờ scheduler.