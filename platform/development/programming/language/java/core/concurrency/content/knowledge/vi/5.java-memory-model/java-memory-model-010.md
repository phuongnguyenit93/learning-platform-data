# Reordering của compiler, CPU và bộ nhớ trong Java Memory Model

Trong chương trình một thread, ta thường đọc các lệnh theo thứ tự từ trên xuống. Nhưng khi hai hoặc nhiều thread cùng thao tác trên dữ liệu, **thứ tự lệnh được viết trong mã nguồn không tự trở thành thứ tự mà thread khác được bảo đảm quan sát**. Trình biên dịch, JIT của JVM và phần cứng đều có thể tối ưu cách thực thi; dữ liệu cũng có thể được giữ tạm trong thanh ghi, cache hoặc bộ đệm ghi. Java Memory Model (JMM) quy định những kết quả nào được phép và những quan hệ đồng bộ nào giúp chương trình có kết quả dự đoán được.

Ví dụ, nhìn hai câu lệnh:

```java
data = 42;
ready = true;
```

Đây là đoạn minh họa, giả định `data` và `ready` là hai field được thread khác đọc. Thread viết thấy `data` được gán trước `ready`; **thread đọc không mặc nhiên được bảo đảm** rằng thấy `ready == true` sẽ thấy `data == 42` nếu cả hai field thông thường được truy cập không đồng bộ. Nguyên nhân cốt lõi là chương trình chưa thiết lập quy tắc **happens-before** cần thiết, chứ không thể từ một kết quả bất thường mà xác định chắc chắn chính CPU hoặc compiler đã hoán đổi hai lệnh.

Bài học này bàn về concurrency của **Java nói chung**, tập trung vào reordering trong JMM và cách thiết kế mã Java 17+ đúng. Không phụ thuộc cơ chế concurrency riêng của Spring Framework.

## 1. Reordering nghĩa là gì?

**Reordering** là việc các thao tác được thực thi hoặc được quan sát theo một thứ tự khác với thứ tự cú pháp được viết, trong giới hạn mà ngôn ngữ và kiến trúc cho phép. Phải phân biệt ba góc nhìn:

1. **Thứ tự mã nguồn (program order):** thứ tự hành động xuất hiện trong luồng thực thi của một thread theo mô hình ngôn ngữ.
2. **Cách hiện thực tối ưu:** compiler/JIT có thể sắp xếp lại, loại bỏ, gộp thao tác hoặc lưu giá trị tạm; CPU có thể thực thi và hoàn tất thao tác theo pipeline và cơ chế bộ nhớ của nó.
3. **Thứ tự quan sát giữa các thread:** điều gì thread khác thực sự có quyền nhìn thấy theo JMM, các quan hệ đồng bộ và các thao tác xung đột.

Không có nghĩa JVM tùy ý làm sai chương trình. Các tối ưu phải **tôn trọng Java Memory Model**, bao gồm những kết quả không được phép thay đổi trong ngữ cảnh có đồng bộ đúng.

Khái niệm **as-if-serial** nói rằng tối ưu trong một thread phải giữ hành vi quan sát được của chương trình đơn luồng như thể các phép toán được thực hiện theo ngữ nghĩa tuần tự. Nhưng điều này **không đủ để đảm bảo** các thread khác nhìn thấy mọi ghi bộ nhớ theo đúng thứ tự trực quan của mã nguồn nếu chưa có quan hệ đồng bộ.

Ví dụ:

```java
int a = 10;
int b = 20;
int sum = a + b;
System.out.println(sum);
```

Trong một thread, chương trình phải in `30`; JVM có thể tối ưu tính giá trị mà không phải phát sinh từng bước đọc/ghi như người học hình dung. Điều quan trọng là kết quả hợp lệ được bảo toàn, không phải từng instruction máy phải đi theo thứ tự văn bản.

## 2. Vì sao compiler và JIT có thể thay đổi thứ tự?

Java source được `javac` biên dịch thành bytecode; JVM chạy bytecode thông qua interpreter và/hoặc trình biên dịch JIT tùy môi trường. Các bước tối ưu có thể:

- **Đưa một phép đọc ra khỏi vòng lặp** nếu phép đọc lặp lại được xem là không cần thiết theo những ràng buộc hiện có.
- **Giữ giá trị trong thanh ghi** hoặc loại bỏ các lần đọc/ghi trung gian nếu không ảnh hưởng hành vi phải bảo toàn.
- **Hoán đổi hai thao tác độc lập** trong cùng thread khi không phá các quan hệ thứ tự được ngôn ngữ yêu cầu.
- **Inline và tối ưu qua ranh giới phương thức**, khiến cấu trúc thực thi không giống cách sắp xếp lời gọi ở source.
- **Tối ưu việc truy cập trường hoặc phần tử**, miễn là tuân thủ JMM và các quy tắc về synchronization/exception/quan sát hợp lệ.

Một ví dụ nguy hiểm là vòng lặp chờ flag bình thường:

```java
class UnsafeStopSignal {
    boolean stopped;

    void requestStop() {
        stopped = true;
    }

    void work() {
        while (!stopped) {
            // Làm việc hoặc spin.
        }
    }
}
```

Đây là **anti-pattern minh họa**, không phải chương trình nên chạy thử trực tiếp: nếu một thread gọi `work()` còn thread khác gọi `requestStop()`, chương trình thiếu đồng bộ. Worker **không được bảo đảm** sẽ thấy việc cập nhật; vòng lặp có thể kéo dài vô hạn. Đây có thể liên quan đến việc compiler tối ưu việc đọc, cache/register hoặc visibility, nhưng một lần chạy không đủ để kết luận cơ chế cụ thể nào đã gây ra hành vi.

Khi `stopped` là một `volatile boolean` và tất cả đường truy cập dùng trường volatile đó, mỗi lần kiểm tra phải tôn trọng ngữ nghĩa volatile theo JMM. Tuy nhiên, **`volatile` không tạo lời hứa về lịch cấp CPU, thời gian kết thúc hay khả năng thức dậy của một worker đang block trong I/O**.

## 3. CPU, cache và store buffer: trực giác về khác biệt quan sát

Ở mức phần cứng hiện đại, nhiều CPU core có cache và đường thực thi riêng. Một phép ghi có thể qua **store buffer** trước khi các core khác có thể quan sát theo trật tự phù hợp; một phép đọc có thể nhận dữ liệu từ cache, thanh ghi hoặc hệ thống bộ nhớ. CPU còn có pipeline, speculative execution và cơ chế xử lý thứ tự bộ nhớ của kiến trúc.

Mô hình khái quát:

```text
            Core 1                           Core 2
       +--------------+                 +--------------+
       | registers    |                 | registers    |
       | store buffer |                 | store buffer |
       | cache        |                 | cache        |
       +------+-------+                 +------+-------+
              |                                |
              +---------- memory system -------+
                          |
                     shared data
```

Sơ đồ chỉ giúp hiểu **vì sao các core có thể quan sát việc đọc/ghi khác trực giác**. Nó không mô tả đúng mọi tầng cache hoặc trình tự chuyển dữ liệu của một CPU cụ thể.

Hai điều dễ nhầm:

- **Cache coherence** (duy trì tính nhất quán của giá trị tại một địa chỉ theo quy tắc phần cứng) **không đồng nghĩa** chương trình có thứ tự bộ nhớ toàn cục theo source cho mọi địa chỉ khác nhau.
- Java không bắt lập trình viên suy ra tính đúng đắn từ x86, ARM hay một CPU cụ thể. **JMM** là hợp đồng có hiệu lực giữa chương trình Java và mọi triển khai tuân thủ; compiler/JIT/JVM phải kết hợp các instruction, memory barrier hoặc kỹ thuật khác để bảo đảm hợp đồng đó trên phần cứng đang chạy.

Một chương trình data race có thể "chạy ổn" trên một cấu hình rồi hỏng khi đổi JDK, cấu hình JIT, CPU hoặc tải hệ thống. Điều đó không chứng minh một nền tảng "đã sửa" race; nó cho thấy chương trình đã dựa vào kết quả không được bảo đảm.

## 4. Litmus test: hai ghi, hai đọc và kết quả bất ngờ

Ví dụ kinh điển để suy nghĩ về visibility và reordering là **store-buffering litmus test** với hai biến `x` và `y` ban đầu bằng `0`:

```text
Giá trị đầu: x = 0, y = 0

Thread A                    Thread B
---------                   ---------
x = 1                       y = 1
r1 = y                      r2 = x

Kết quả quan tâm: r1 = 0 và r2 = 0
```

Nếu coi bốn thao tác như được **xen kẽ tuần tự trên một bộ nhớ nhất quán toàn cục**, trong khi vẫn giữ thứ tự chương trình ở từng thread, kết quả cả hai cùng đọc `0` là không thể: một trong hai phép ghi phải đứng trước phép đọc đối diện theo một trật tự đơn nhất.

Nhưng với các thao tác **ordinary (non-volatile) không có synchronization giữa các thread**, JMM cho phép hành vi không tương đương một thứ tự xen kẽ tuần tự đơn giản như vậy. Kết quả `r1 == 0 && r2 == 0` có thể hợp lệ. Không phải cứ chạy ví dụ là sẽ gặp; một nền tảng có thể quan sát chủ yếu những kết quả khác.

Đây là ví dụ phân tích, không phải stdout cố định. Nếu muốn viết phép thử Java độc lập, có thể dùng hai thread như sau:

```java
public class StoreBufferingIllustration {
    static int x, y, r1, r2;

    public static void main(String[] args) throws InterruptedException {
        Thread a = new Thread(() -> {
            x = 1;
            r1 = y;
        });
        Thread b = new Thread(() -> {
            y = 1;
            r2 = x;
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("r1=" + r1 + ", r2=" + r2);
    }
}
```

```bash
javac StoreBufferingIllustration.java
java StoreBufferingIllustration
```

**Stdout không cố định.** Chẳng hạn có thể thấy `r1=0, r2=1`, `r1=1, r2=0`, `r1=1, r2=1` hoặc `r1=0, r2=0`; các lịch chạy khác nhau và các quan sát hợp lệ của JMM ảnh hưởng kết quả. Một lần chạy thấy `1,1` không chứng minh code đã có đồng bộ.

Ở ví dụ trên, main gọi `join()` chỉ để **đọc kết quả sau khi cả hai worker kết thúc**. `join()` thiết lập happens-before từ hành động của worker tới main **sau join**, nhưng không tạo thứ tự đủ mạnh giữa thao tác `x = 1; r1 = y` của A với thao tác `y = 1; r2 = x` của B đang chạy cùng lúc. Vì vậy, `join()` không tự ngăn kết quả `0,0`.

Lưu ý: không thể dùng chính một phép thử này để khẳng định "compiler đã đảo thứ tự" hoặc "store buffer đã trì hoãn ghi" trong một lần chạy cụ thể. JMM mô tả **kết quả hợp lệ**, không cấp quyền suy ngược chắc chắn một nguyên nhân phần cứng từ output.

## 5. Java Memory Model: điều luật thay cho suy đoán CPU

JMM thuộc Java Language Specification, chương 17 (Threads and Locks). Nó quy định quan hệ giữa các hành động của chương trình, synchronization actions, **happens-before**, và những giá trị một phép đọc có thể quan sát.

Một số thuật ngữ quan trọng:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Program order | Thứ tự hành động trong mô hình thực thi từng thread |
| Synchronization action | Hành động đồng bộ có ý nghĩa với JMM, như lock/unlock monitor, volatile read/write, khởi động thread |
| Synchronization order | Trật tự tổng thể được mô hình bộ nhớ quy định cho các synchronization action, nhất quán với program order tương ứng |
| Synchronizes-with | Quan hệ đồng bộ cụ thể giữa các hành động, ví dụ unlock rồi lock cùng monitor hoặc volatile write rồi volatile read phù hợp |
| Happens-before (HB) | Bao gồm program order và synchronizes-with, với tính bắc cầu; dùng để xác định những hiệu ứng bộ nhớ được bảo đảm |
| Data race | Hai truy cập xung đột vào cùng biến, ít nhất một ghi, mà không có quan hệ happens-before giữa chúng |
| Correctly synchronized | Chương trình không có data race trong mọi cách thực thi tuần tự nhất quán tương ứng; được hưởng bảo đảm về sequential consistency của JMM |

**Sequential consistency (SC)** là trực giác rằng các thao tác của tất cả thread được phép xem như một thứ tự xen kẽ duy nhất và vẫn giữ program order trong từng thread. Một kết quả quan trọng của JMM: **chương trình Java được đồng bộ đúng là sequentially consistent** theo định nghĩa của JMM. Điều này **không** có nghĩa JVM phải thực thi vật lý từng instruction đúng thứ tự source; nó nghĩa kết quả của chương trình được đồng bộ đúng có thể được giải thích theo mô hình SC phù hợp.

### Happens-before và tính bắc cầu

Nếu hành động A **happens-before** B, và B happens-before C, thì A happens-before C. Quan hệ này giúp tạo **đường công bố dữ liệu** từ producer tới consumer.

Các cạnh HB thường gặp:

- Hành động trước trong cùng thread HB hành động sau theo program order.
- `Thread.start()` HB những hành động của thread vừa được start.
- Hành động của thread được đợi HB các hành động của thread gọi sau `Thread.join()` thành công.
- Unlock monitor HB lock tiếp theo trên **cùng monitor**.
- Một lần ghi volatile HB những lần đọc volatile tiếp theo cùng biến theo synchronization order.
- Hành động trước khi gửi task qua `ExecutorService` HB hành động trong task; hành động task HB hành động sau khi kết quả được lấy bằng `Future.get()` theo hợp đồng của các tiện ích concurrent.

Chỉ đọc/ghi biến ordinary từ nhiều thread mà không có một trong các đường đồng bộ phù hợp **không tự tạo HB**.

## 6. Ví dụ then chốt: message passing bằng `volatile`

Ta muốn publisher cập nhật payload rồi báo cho reader. Dùng một **volatile flag** là cách cơ bản để công bố dữ liệu nếu giao thức là đơn giản một lần.

Lưu thành `VolatilePublicationDemo.java`:

```java
public class VolatilePublicationDemo {
    private static int data;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Data: " + data);
        });

        reader.start();

        data = 42;
        ready = true;

        reader.join();
    }
}
```

```bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
```

**Stdout chính xác khi chương trình chạy hoàn tất:**

```text
Data: 42
```

Tại sao đúng?

1. Trong thread main, `data = 42` **happens-before** `ready = true` theo program order.
2. `ready = true` là **volatile write**. Khi reader đọc được `ready == true` từ volatile read, quan hệ synchronizes-with phù hợp được thiết lập từ volatile write đến volatile read.
3. Volatile read đó diễn ra trước lần đọc `data` theo program order trong reader.
4. Nhờ **tính bắc cầu HB**, ghi `data = 42` happens-before lần đọc `data`. Trong giao thức này không có ghi cạnh tranh khác tới `data`, nên reader được bảo đảm thấy `42`.

`volatile` trên **`ready`** là đủ cho ví dụ: nó tạo đường publication cho lần ghi ordinary trước đó. Không cần đánh dấu cả `data` volatile **khi chỉ có giao thức một lần và không có ghi cạnh tranh khác**.

Đây là một ví dụ học cơ chế; một vòng `while (!ready)` spin liên tục tiêu thụ CPU và không có timeout. Ứng dụng thật nên dùng blocking coordination phù hợp như `CountDownLatch`, `BlockingQueue` hoặc `Future`. Chỉ thêm `Thread.onSpinWait()` để giảm chi phí spin trên một số nền tảng **không tạo memory barrier, không bổ sung HB** và không thể sửa một flag ordinary đang race.

### Nếu bỏ `volatile` thì sao?

Với `private static boolean ready;`, thread writer gán `data = 42` rồi `ready = true` nhưng reader **không được bảo đảm** sẽ quan sát `ready` thay đổi. Ngay cả nếu thấy `true`, chương trình chưa có quan hệ công bố dữ liệu bảo đảm reader thấy `data == 42` trong ngữ cảnh truy cập dữ liệu thiếu đồng bộ.

Đừng dùng `Thread.sleep(100)` như bản sửa: ngủ một khoảng thời gian không sinh ra quan hệ HB giữa producer và reader.

## 7. `volatile` cấm những reordering nào và không làm được gì?

Trong JMM, volatile read/write là **synchronization actions** có thứ tự; các compiler và CPU phải triển khai để kết quả phù hợp với quy tắc bộ nhớ Java. Với mẫu message passing:

```java
data = 42;        // Ghi ordinary
ready = true;     // Ghi volatile
```

và:

```java
if (ready) {      // Đọc volatile
    use(data);    // Đọc ordinary
}
```

Đoạn này là minh họa: `use` là phương thức giả định. Volatile write đóng vai trò **release**, volatile read tương ứng đóng vai trò **acquire** trong cách giải thích thường dùng. Các hiệu ứng trước publication không được phép biến mất hoặc được quan sát theo cách phá HB cần thiết khi reader đã nhận publication.

Điều đó **không đồng nghĩa** mỗi biến ordinary trên toàn hệ thống bỗng được đồng bộ, hay toàn bộ chương trình bị cấm tối ưu. Các ràng buộc chỉ cần đủ để đáp ứng hành vi JMM.

Ba giới hạn rất quan trọng:

1. **Không biến phép toán tổng hợp thành atomic:** `volatile int count; count++;` vẫn là read-modify-write và có thể lost update.
2. **Không tạo critical section:** nhiều thread có thể đồng thời thực thi code sau khi thấy một flag volatile; không có mutex bảo vệ invariant nhiều field.
3. **Không đảm bảo thời gian hoặc tiến độ:** một volatile read không làm worker đang `sleep()`, đợi queue hoặc kẹt I/O tự thức dậy; cũng không bảo đảm thread được scheduler cấp CPU kịp thời.

Nếu chỉ cần flag dừng hoặc publication một chiều, volatile có thể phù hợp. Nếu cần cập nhật đếm atomic, dùng `AtomicInteger` hoặc lock; nếu cần invariant nhiều biến, thường dùng `synchronized`/`Lock` hoặc thiết kế chuyển quyền sở hữu.

## 8. `volatile` và litmus test: sửa cái gì?

Quay lại ví dụ `x` và `y`. Nếu **cả hai là volatile**:

```java
static volatile int x;
static volatile int y;

// Thread A: x = 1; r1 = y;
// Thread B: y = 1; r2 = x;
```

Các truy cập volatile nằm trong synchronization order tổng thể phù hợp với program order của mỗi thread. Nếu cả hai thread đọc giá trị ban đầu `0`, từ thứ tự:

```text
A: volatile write x=1  trước  volatile read y=0
B: volatile write y=1  trước  volatile read x=0
```

ta sẽ cần một vòng thứ tự mâu thuẫn với synchronization order và thứ tự của các phép ghi/đọc volatile. Vì vậy kết quả **`r1=0, r2=0` bị cấm** trong phiên bản cả `x` và `y` đều volatile, với cùng một lần khởi tạo và không có thread thứ ba sửa chúng.

Điểm quan trọng: nếu chỉ đổi một field thành volatile mà vẫn có những truy cập ordinary xung đột không được đồng bộ, không được suy ra chương trình đã đúng. Cần phân tích **toàn bộ giao thức** và quan hệ HB của từng lần đọc/ghi.

## 9. Monitor `synchronized`: mutual exclusion kết hợp ordering và visibility

Một vùng `synchronized` trên cùng monitor giải quyết hai vấn đề:

- **Mutual exclusion:** chỉ một thread giữ monitor đó để chạy critical section tại một thời điểm.
- **Memory ordering/visibility:** unlock trên monitor happens-before lock tiếp theo trên **chính monitor ấy**.

Ví dụ dùng monitor để trao giá trị:

Lưu thành `MonitorPublicationDemo.java`:

```java
public class MonitorPublicationDemo {
    private static final class Mailbox {
        private int value;
        private boolean ready;

        synchronized void publish(int newValue) {
            value = newValue;
            ready = true;
            notifyAll();
        }

        synchronized int awaitValue() throws InterruptedException {
            while (!ready) {
                wait();
            }
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox box = new Mailbox();

        Thread consumer = new Thread(() -> {
            try {
                System.out.println("Message: " + box.awaitValue());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        box.publish(42);
        consumer.join();
    }
}
```

```bash
javac MonitorPublicationDemo.java
java MonitorPublicationDemo
```

Stdout trên đường chạy bình thường:

```text
Message: 42
```

Vì sao không mất tín hiệu dù publisher có thể chạy trước consumer?

- Cả `publish` và `awaitValue` đồng bộ trên cùng đối tượng `Mailbox`.
- Trường `ready` được kiểm tra khi giữ monitor; nếu đã `true` thì consumer đọc ngay mà không `wait`.
- Nếu consumer `wait()` trước, nó tạm **nhả monitor**, cho publisher vào, cập nhật hai field và `notifyAll()`; consumer chỉ tiếp tục đọc `value` sau khi lấy lại monitor.
- `while (!ready)` đúng hơn `if` vì có thể có spurious wakeup hoặc một thread khác thay đổi điều kiện. `notifyAll()` không cho phép consumer đọc ngoài monitor.
- Các ghi trước unlock của publisher được bảo đảm quan sát phù hợp sau khi consumer lock lại monitor.

Mẫu này kết hợp lock và condition; trong code đa tác vụ thực tế, có thể dùng `BlockingQueue` hoặc `CountDownLatch` thay cho tự triển khai điều kiện nếu hợp đồng phù hợp hơn.

## 10. `Thread.start()` và `Thread.join()` cũng tạo thứ tự bộ nhớ

Không cần mọi field được chia sẻ đều là volatile. Khi vòng đời thread đã tạo quan hệ HB đúng, plain field có thể được đọc an toàn ở những điểm cụ thể.

Lưu thành `JoinVisibilityDemo.java`:

```java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> result = 42);

        worker.start();
        worker.join();

        System.out.println("Result: " + result);
    }
}
```

```bash
javac JoinVisibilityDemo.java
java JoinVisibilityDemo
```

Stdout chính xác:

```text
Result: 42
```

Thao tác `result = 42` trong worker happens-before các hành động của main sau `worker.join()` thành công. Với chỉ một writer như ví dụ và không có truy cập concurrent khác tới `result`, không cần dùng volatile.

Nhưng nếu main tự đọc `result` **trước** `join()` trong lúc worker đang chạy, đó là một kiểu truy cập khác và cần phân tích đồng bộ riêng. Tương tự, `start()` giúp công bố những hành động đã xảy ra trước `start()` tới thread mới; nó không tự đồng bộ mọi ghi phát sinh **sau** `start()` ở thread cha.

**Quan sát trạng thái `Thread.getState()` bằng polling không thể thay thế ý nghĩa đợi hoàn tất của `join()`.** Cần một primitive có hợp đồng completion/HB rõ ràng.

## 11. `Future.get()`, queue và các cạnh happens-before cấp thư viện

Các tiện ích trong `java.util.concurrent` có **memory consistency effects** được mô tả theo API. Một số trường hợp thường dùng:

| Cơ chế | Bảo đảm cần dùng |
| --- | --- |
| `ExecutorService.submit(...)` | Hành động trước khi gửi task happens-before hành động trong task |
| `Future.get()` | Hành động của task happens-before hành động sau khi caller lấy kết quả bằng `get()` |
| `BlockingQueue.put/take` | Hành động trước khi đặt phần tử vào queue happens-before hành động sau khi thread khác lấy phần tử tương ứng ra |
| `CountDownLatch.countDown/await` | Hành động trước `countDown()` happens-before hành động sau khi `await()` tương ứng trở về thành công |
| `synchronized` cùng monitor | Unlock happens-before lock tiếp theo của cùng monitor |
| `volatile` | Write happens-before các read volatile tiếp theo cùng biến theo quy tắc JMM |

Một ví dụ `Future` rõ ràng:

Lưu thành `FutureVisibilityDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> future = executor.submit(() -> result = 42);

            future.get(); // Đợi hoàn tất và thiết lập cạnh HB.
            System.out.println("Result: " + result);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac FutureVisibilityDemo.java
java FutureVisibilityDemo
```

Stdout chính xác:

```text
Result: 42
```

Ở đây task ghi trường ordinary `result`, còn main chỉ đọc sau `get()` thành công. Trạng thái `result` được công bố theo hợp đồng memory consistency của `Future`. Nếu nhiều task tiếp tục ghi đè `result` sau đó thì `get()` của một task chưa đủ bảo vệ một phép đọc trước các writer còn lại.

Điểm chung: những API đồng bộ cao hơn như future hoặc queue thường dễ dùng đúng hơn việc tự tạo hai flag boolean rồi dựa vào việc đọc/ghi không đồng bộ.

## 12. Reordering không đồng nghĩa `count++` trở thành atomic

Giả sử:

```java
private static volatile int count;

static void increment() {
    count++;
}
```

Đây là đoạn code minh họa một anti-pattern, không phải chương trình độc lập. `volatile` làm từng lần đọc và ghi `count` có ngữ nghĩa volatile. Nhưng `count++` vẫn có các bước logic:

```text
Thread A                    Thread B
read count = 5
                            read count = 5
compute 6
                            compute 6
write count = 6
                            write count = 6
```

Kết quả có thể là `6` sau hai lần tăng thay vì `7`. **Ordering/visibility không tự bảo đảm atomicity của read-modify-write**.

Sửa bằng một operation atomic:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class Counter {
    private final AtomicInteger count = new AtomicInteger();

    int incrementAndGet() {
        return count.incrementAndGet();
    }
}
```

Hoặc dùng `synchronized` cho một critical section đúng. Nếu invariant gồm nhiều biến, phải bảo vệ cả giao dịch, không chỉ từng bước đọc/ghi độc lập.

## 13. Safe publication: khởi tạo xong mới công bố

Một object có thể có nhiều field liên quan nhau. Nếu một thread tạo object, khởi tạo các field rồi chuyển **tham chiếu** cho thread khác mà không có safe publication, reader có thể không được bảo đảm thấy trạng thái đã xây dựng đúng như mong đợi theo JMM.

Mẫu nguy hiểm:

```java
class Config {
    int port;
    String host;
}

class UnsafeConfigHolder {
    Config config; // Plain reference, không có giao thức publication.

    void initialize() {
        Config c = new Config();
        c.port = 8080;
        c.host = "localhost";
        config = c; // Thread khác đọc config không đồng bộ.
    }
}
```

Đây là minh họa lỗi, không phải một chương trình runnable hoàn chỉnh. Không nên lập luận rằng "phép gán `config = c` nằm cuối nên mọi thread chắc chắn thấy tất cả field mới". Nếu không có HB, việc công bố tham chiếu qua plain field trong lúc reader truy cập không đồng bộ **không tạo bảo đảm** như vậy.

Một giải pháp đơn giản là **immutable snapshot + volatile reference**, khi các field và đối tượng bên trong có ngữ nghĩa immutable thực sự:

```java
record Config(int port, String host) {}

final class ConfigHolder {
    private volatile Config current = new Config(8080, "localhost");

    void update(int port, String host) {
        current = new Config(port, host);
    }

    Config snapshot() {
        return current;
    }
}
```

`Config` là record giữ `int` và `String` (immutable), nên rất dễ lý luận về trạng thái đã công bố. Mỗi lần `snapshot()` lấy **một tham chiếu** đến một giá trị hoàn chỉnh. Volatile write/read cung cấp publication phù hợp; các reader không quan sát một object bị sửa từng field giữa chừng.

Nếu record chứa `List<Item>` với `Item` mutable thì record **không tự deep-immutable**; cần bản sao, giới hạn quyền sở hữu hoặc bảo vệ các phần tử theo yêu cầu.

## 14. `final` fields và giới hạn của việc khởi tạo

JMM có quy tắc đặc biệt cho **final fields** khi object được xây dựng đúng: các final field được khởi tạo trong constructor có bảo đảm visibility mạnh hơn field ordinary trong những trường hợp liên quan đến constructor freeze. Tuy vậy, có những giới hạn:

- **Không cho `this` thoát khỏi constructor** trước khi khởi tạo hoàn tất. Ví dụ không đăng ký listener trỏ đến `this` hoặc khởi động thread dùng `this` giữa constructor.
- `final List<String> items` chỉ cố định **tham chiếu**, không ngăn `items.add(...)` và không tự biến list thành thread-safe.
- Phải phân biệt **khởi tạo object đúng** và **cập nhật mutable state sau này**; quy tắc final field không bảo vệ các mutation về sau.
- Safe publication vẫn là thiết kế ưu tiên để chuyển object giữa các thread và bảo vệ các quan hệ giữa nhiều dữ liệu có thể đổi.

Các field `final` thích hợp với value object và bất biến, nhưng không phải "mẹo" sửa toàn bộ data race.

## 15. Double-checked locking và vai trò của `volatile`

Ví dụ singleton lazy initialization truyền thống thường viết kiểm tra nhanh rồi kiểm tra lại trong lock:

```java
final class LazyService {
    private static volatile LazyService instance;

    private LazyService() {
    }

    static LazyService getInstance() {
        LazyService local = instance;
        if (local == null) {
            synchronized (LazyService.class) {
                local = instance;
                if (local == null) {
                    local = new LazyService();
                    instance = local;
                }
            }
        }
        return local;
    }
}
```

Đây là một class minh họa đầy đủ, không có phương thức `main` vì mục tiêu là xem giao thức khởi tạo.

**Vì sao volatile quan trọng?**

- Writer phải xây dựng object rồi **công bố tham chiếu** qua volatile field.
- Reader ở đường đi nhanh có thể thấy tham chiếu không null và sử dụng nó **mà không lấy monitor**. Volatile read bảo đảm việc công bố phù hợp với các ghi đã xảy ra trước volatile write.
- Nếu xóa volatile, việc check không null ở đường đi nhanh không có synchronization với writer; trong Java hiện đại không được xem đó là một triển khai double-checked locking đúng.
- Kiểm tra bên trong `synchronized` ngăn nhiều thread đồng thời tạo instance khi còn null.

Với singleton đơn giản, static holder hoặc enum thường dễ hiểu hơn. Nếu constructor để `this` thoát ra quá sớm hoặc object có mutable state cần bảo vệ sau này, volatile singleton reference không tự giải quyết những vấn đề đó.

## 16. CPU memory barrier và JMM: cách hiểu đúng

Ở ngôn ngữ phần cứng, **memory fence/barrier** là các cơ chế giới hạn một số reorderings và quan sát bộ nhớ. JVM có thể sử dụng các instruction fence, ràng buộc JIT, các acquire/release operations hay những instruction có ngữ nghĩa ordering thích hợp để thực thi JMM trên phần cứng cụ thể.

Không có quy tắc đơn giản "mỗi lần `volatile` luôn phát sinh một instruction fence giống nhau trên mọi CPU/JDK". JMM quy định **hiệu ứng bắt buộc**, không quy định máy phải dùng một instruction cố định. Trên những nền tảng khác nhau, compiler và CPU có thể thực thi các ràng buộc khác nhau để đạt cùng hợp đồng Java.

Java còn có các API nâng cao như `VarHandle` với access modes ordinary, opaque, acquire, release và volatile. Chúng phục vụ những giao thức concurrent chuyên sâu; chọn sai mode có thể làm thiếu ordering. Một cặp lời gọi fence đặt tùy tiện **không tự thiết lập giao thức publication đúng** nếu không có các thao tác liên kết và điều kiện đọc/ghi phù hợp.

Khi học reordering, nên thành thạo `volatile`, `synchronized` và primitive concurrent trước. Chỉ dùng `VarHandle`, fences hoặc thuật toán lock-free khi có yêu cầu rõ và kiểm chứng được những điều kiện JMM của thuật toán.

## 17. Đừng dùng `sleep()` hay log để "sửa" vấn đề thứ tự

Những thay đổi sau đôi khi làm lỗi hiếm hơn nhưng không xây được hợp đồng đồng bộ:

- Chèn `Thread.sleep(10)` giữa hai thao tác.
- In `System.out.println(...)` trong vòng lặp rồi thấy lỗi biến mất.
- Thay đổi mức tối ưu JIT và kết luận race đã được sửa.
- Chạy một thread trong debugger rồi nhận kết quả ổn định.
- Chuyển từ máy nhiều lõi sang máy ít lõi và thấy test qua.

Một số thao tác logging hoặc debugger có thể **thay đổi lịch chạy và thêm đồng bộ phụ**, làm race khó tái hiện. Nhưng không được dựa vào hiệu ứng phụ đó để bảo đảm hành vi của dữ liệu chia sẻ. Thiết kế đúng phải chỉ rõ **điểm publication và cạnh HB** trong code nghiệp vụ.

Để phân biệt, thử tự hỏi: "Nếu bỏ tất cả `sleep`, log và breakpoint, chương trình còn có quan hệ synchronizes-with nào giữa writer và reader?" Nếu không, phải xem lại giao thức.

## 18. Khi nào được phép reordering và khi nào bị ràng buộc?

| Tình huống | Có thể giả định thread khác thấy theo source order không? | Lý do |
| --- | --- | --- |
| Hai field ordinary, writer và reader truy cập không đồng bộ | **Không** | Không có HB giữa các truy cập xung đột |
| Writer ghi dữ liệu rồi volatile flag; reader đọc thấy flag rồi lấy dữ liệu | **Có, theo phạm vi publication đã phân tích** | Volatile write/read tạo HB và HB có tính bắc cầu |
| Writer unlock monitor; reader lock cùng monitor trước khi đọc | **Có, với những ghi/đọc được bảo vệ phù hợp** | Unlock/lock cùng monitor có HB |
| Main gọi `start()` sau khi cấu hình dữ liệu; worker đọc dữ liệu khởi tạo | **Có cho các hành động xảy ra trước `start()`** | Thread start tạo HB |
| Main đọc kết quả sau `worker.join()` thành công | **Có cho những hành động trước khi worker kết thúc**, nếu không có writer xung đột khác | Thread termination/join HB |
| Main đọc kết quả sau `Future.get()` thành công | **Có theo memory consistency effects của Future** | Task actions HB caller sau get |
| Chỉ dùng `Thread.sleep(...)` để đợi writer | **Không** | Sleep không phải publish/acquire |
| `volatile count++` từ hai writer | **Không bảo đảm tổng số lần tăng** | Volatile ordering không tạo atomic read-modify-write |

Bảng nói về **bảo đảm của một giao thức cụ thể**, không phải bảo đảm mọi object sẽ bất biến mãi mãi sau khi được công bố. Nếu xuất hiện writer mới, phải xét tiếp các cạnh HB và bất biến tại thời điểm đọc.

## 19. Reordering, visibility và atomicity: ba vấn đề phải tách

| Khía cạnh | Câu hỏi | Công cụ/ví dụ |
| --- | --- | --- |
| Ordering | Các hành động có bị quan sát trái với thứ tự mà giao thức yêu cầu không? | Volatile publication; lock/unlock; HB |
| Visibility | Reader có bảo đảm quan sát một ghi trước đó hay không? | Cạnh HB qua volatile, monitor, start/join, future, queue |
| Atomicity | Một chuỗi thao tác có bị xen kẽ giữa chừng và phá invariant không? | `AtomicInteger.incrementAndGet()`, CAS đúng cách, critical section |
| Progress/liveness | Task có thể tiếp tục và kết thúc không? | Signaling, timeout, interruption, deadlock prevention |

Một chương trình có thể giải quyết ordering/visibility của một flag nhưng vẫn sai vì dùng `count++` từ nhiều writer. Hoặc có phép tăng atomic nhưng worker bị deadlock ở lock khác. **JMM không thay thế thiết kế coordination và lifecycle**, và điều kiện thread-safe phải được xét ở ranh giới nghiệp vụ cụ thể.

## 20. Cách phân tích một đoạn code đa luồng

Khi thấy một tình huống "đọc đúng khi chạy đơn luồng nhưng sai khi chạy nhiều thread", làm theo các bước:

1. **Liệt kê shared variables:** Những field nào có thể bị đọc/ghi từ ít nhất hai thread? Có mutable object hoặc collection nằm sau một tham chiếu được chia sẻ không?
2. **Đánh dấu các truy cập xung đột:** Có những lần đọc/ghi cùng biến với ít nhất một ghi không?
3. **Tìm cạnh HB:** Dùng volatile read/write cùng biến, monitor lock/unlock cùng đối tượng, thread start/join, future/queue/latch hoặc cơ chế khác có hợp đồng memory consistency không?
4. **Xác định invariant:** Chỉ cần publish một snapshot, hay cần atomic read-modify-write hoặc cập nhật đồng thời nhiều field?
5. **Thiết kế publication:** Dùng immutable snapshot + volatile reference, `synchronized`, atomic type, concurrent collection hoặc single-owner/message passing phù hợp.
6. **Đảm bảo progress:** Có nguy cơ spin mãi, block vô hạn, thiếu tín hiệu, deadlock hoặc bị cancel mà không giải phóng không?
7. **Kiểm tra theo hợp đồng**, sau đó mới stress test và đo performance. Test có thể tìm lỗi nhưng kết quả đúng ở vài lần chạy không tự chứng minh thiếu race.

Ví dụ nếu một ứng dụng có `volatile boolean done` nhưng đồng thời nhiều worker tăng một `int processed` ordinary, flag `done` chưa chắc sửa được việc các increment mất dữ liệu **giữa các worker**. Cần giải quyết atomicity hoặc ownership của `processed` trước khi dùng flag để công bố kết quả.

## 21. Câu hỏi tự kiểm tra

**1. Java compiler có được phép tối ưu hoặc hoán đổi hai thao tác mà không giữ nguyên thứ tự instruction máy như source không?**

Có, nếu kết quả và những ràng buộc phải tuân theo JMM được giữ. Không thể suy từ thứ tự source ra thứ tự instruction máy hoặc thứ tự quan sát của thread khác khi chưa có synchronization.

**2. Vì sao `data = 42; ready = true;` có thể không đủ cho thread khác?**

Nếu `data` và `ready` là các field ordinary chia sẻ không đồng bộ, không có HB bảo đảm reader nhìn thấy `ready` và payload đúng. Dùng volatile publication đúng giao thức, monitor hoặc cơ chế khác để thiết lập HB.

**3. Trong litmus test `x=1; r1=y` và `y=1; r2=x`, hai biến ordinary có thể cho cả `r1` và `r2` bằng `0` không?**

Có thể theo JMM. Nhưng chạy một lần chưa chắc quan sát kết quả đó; không được từ output mà khẳng định chính xác CPU hay JIT đã làm gì.

**4. Nếu cả `x` và `y` là volatile trong cùng litmus test, kết quả `0,0` có còn hợp lệ không?**

Không trong mô hình giả định đã nêu, vì các volatile action phải tuân thủ synchronization order nhất quán với program order và không thể tạo vòng thứ tự cần thiết cho hai phép đọc cùng thấy `0`.

**5. Vì sao `volatile count++` vẫn có thể mất lần tăng?**

Vì phép tăng là chuỗi đọc, tính và ghi. `volatile` không hợp nhất chúng thành một thao tác atomic. Dùng `AtomicInteger` hoặc khóa bảo vệ toàn bộ phép tăng.

**6. `Thread.join()` có sửa race giữa hai worker đã cùng đọc/ghi shared state khi chúng đang chạy không?**

Không. `join()` giúp main chờ và nhìn thấy công việc đã hoàn thành; nó không tạo mutual exclusion hoặc thứ tự đủ giữa hai worker đang cập nhật cùng dữ liệu trước đó.

**7. Cache coherence có nghĩa Java tự động nhìn thấy mọi ghi đúng thứ tự source ở tất cả thread không?**

Không. Cache coherence không phải hợp đồng JMM cấp ngôn ngữ cho nhiều địa chỉ và các hành động chưa đồng bộ. Cần phân tích HB theo Java.

**8. Có thể sửa một vòng polling flag ordinary bằng cách thêm `Thread.sleep()` không?**

Không. Sleep chỉ trì hoãn, không tạo cạnh publication giữa writer và reader. Hãy thay flag bằng volatile theo giao thức đúng hoặc dùng một primitive coordination.

**9. Dùng `record` và `final` có loại bỏ mọi rủi ro reordering với shared mutable state không?**

Không. Immutable value giúp giảm vấn đề, nhưng record chứa phần tử mutable vẫn có thể bị sửa. Cần khởi tạo đúng, tránh escape trong constructor, dùng safe publication và bảo vệ mọi mutation về sau.

## 22. Những điều cần nhớ

- **Reordering** là vấn đề về cách thực thi và quan sát hành động dưới các ràng buộc của JMM; source order không phải cam kết quan sát giữa các thread chưa đồng bộ.
- **Compiler/JIT, CPU và hệ thống bộ nhớ** đều có thể ảnh hưởng cách đọc/ghi biểu hiện, nhưng một kết quả bất thường không đủ chứng minh nguyên nhân duy nhất ở một tầng nào.
- **Happens-before** là công cụ chính để lập luận về thứ tự và visibility. Program order cộng synchronizes-with có tính bắc cầu.
- **`volatile`** thích hợp cho một số giao thức publication/flag. Nó **không** khiến phép `count++` thành atomic hay thay thế lock cho invariant nhiều bước.
- **`synchronized`**, thread `start/join`, `Future.get()` và queue/latch có memory consistency effects cụ thể; chọn công cụ theo hành vi cần bảo đảm.
- **Safe publication** và immutable data giúp tránh nhiều vấn đề khó; ngược lại, data race có thể tiềm ẩn ngay cả khi test thường xuyên cho kết quả đúng.
- **`sleep`, log, breakpoint hoặc cảm nhận về CPU cache** không phải giải pháp thay thế thiết kế đồng bộ.

Khi phân tích lỗi Java concurrency, hãy chỉ rõ **writer**, **reader**, các thao tác xung đột, ranh giới **atomicity** và đường **happens-before**. Cách lập luận này bền vững trước các thay đổi của JIT, CPU và hệ thống bộ nhớ hơn nhiều so với việc suy đoán thứ tự thực thi từ mã nguồn.