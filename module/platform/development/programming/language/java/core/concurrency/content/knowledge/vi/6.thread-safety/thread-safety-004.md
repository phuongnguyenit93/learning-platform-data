# Thread confinement và ownership rõ ràng trong Java Concurrency

> **Phạm vi:** thiết kế thread-safe bằng cách **giới hạn nơi truy cập mutable state** và **quy định một chủ sở hữu rõ ràng** của dữ liệu. Nội dung áp dụng cho Java SE (Java 17+), với các API chuẩn như `ExecutorService`, `Future`, `BlockingQueue` và `ThreadLocal`. Các vấn đề triển khai riêng của Spring được dành cho chương riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **thread confinement**: một đối tượng có thể thay đổi chỉ được sử dụng bởi một thread tại một thời điểm, và vì sao điều đó có thể loại bỏ nhu cầu khóa khi thao tác nội bộ.
- Phân biệt **thread confinement**, **task confinement**, **ownership**, **immutable data**, **shared mutable state** và **safe publication**.
- Nhận ra lúc nào một tham chiếu **escape** ra ngoài vùng kiểm soát, làm mất confinement dù đối tượng được tạo trong biến local.
- Thiết kế việc **bàn giao ownership** qua queue, `Future.get()`, `join()` hoặc giao thức có *happens-before*; tránh vừa chuyển quyền vừa tiếp tục sửa object.
- Dùng `ThreadLocal` đúng với thread pool, biết khi nào phải `remove()` và vì sao thread-local **khác** dữ liệu chỉ sống trong một request/task.
- Chọn giữa **single owner**, dữ liệu bất biến, chia partition và khóa/atomic phù hợp với invariant của bài toán.
- Kiểm tra tính đúng đắn, tránh data race, sai lệch visibility, thứ tự xử lý bất định, aliasing và rò rỉ trạng thái giữa các task.

**Tư tưởng cốt lõi:** thay vì để nhiều thread trực tiếp cập nhật cùng một cấu trúc rồi cố khóa mọi chỗ, có thể thiết kế để **chỉ một thread sở hữu phần mutable state đó**, còn thread khác chuyển công việc hoặc bản dữ liệu độc lập đến chủ sở hữu. Ownership phải được bảo đảm bằng API và luồng dữ liệu thực tế; một lời chú thích “chỉ thread này dùng” không tự tạo an toàn.

## 2. Vì sao hạn chế chia sẻ thường đơn giản hơn chia sẻ có khóa?

Trong chương trình tuần tự, một `ArrayList`, `HashMap` hay `StringBuilder` có thể được thay đổi thoải mái nếu không có truy cập đồng thời. Khi nhiều thread chia sẻ cùng object mutable mà không có giao thức phối hợp, những thao tác như đọc rồi ghi, kiểm tra rồi cập nhật hoặc thay đổi nhiều trường có thể xen kẽ và phá invariant.

Ví dụ giả định cả hai thread cùng làm:

```java
// Minh họa chưa an toàn khi truy cập đồng thời:
List<Integer> numbers = new ArrayList<>();
// Thread A: numbers.add(1);
// Thread B: numbers.add(2);
```

Đoạn này cần import `java.util.ArrayList` và `java.util.List`; các dòng thread là **mô tả**, không phải chương trình độc lập. `ArrayList` không bảo đảm thread safety cho nhiều writer đồng thời. Không nên kỳ vọng kết quả luôn chứa đủ cả hai phần tử hoặc cấu trúc vẫn ở trạng thái nhất quán.

Có hai hướng thiết kế phổ biến:

1. **Chia sẻ có kiểm soát:** nhiều thread truy cập trạng thái chung nhưng dùng cùng lock/atomic/concurrent collection phù hợp với invariant.
2. **Giảm chia sẻ:** mỗi worker xử lý state riêng; khi cần trao đổi, gửi giá trị bất biến, snapshot hoặc command tới một owner có trách nhiệm duy nhất.

Confinement loại bỏ cuộc đua trên đối tượng **chỉ khi điều kiện không có truy cập đồng thời ngoài owner thật sự được giữ**. Nó không tự biến các thao tác I/O hay giao dịch nhiều service thành nguyên tử, không làm scheduler xác định và không thay thế những ràng buộc ordering cần thiết ở ranh giới chuyển dữ liệu.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Thread confinement** | Một object mutable được dùng trong phạm vi một thread, không bị thread khác truy cập khi còn mutable. | Một `StringBuilder` chỉ có worker hiện tại dùng. |
| **Task confinement** | Dữ liệu và logic riêng của một task, không bị task khác truy cập trong khi thực thi. | `ArrayList` local tạo bên trong `Callable.call()`. |
| **Ownership** | Ai có **quyền đọc/ghi**, khi nào quyền đó bắt đầu/kết thúc và API nào là con đường truy cập hợp lệ. | Consumer duy nhất sửa sổ cái; producer chỉ gửi command. |
| **Ownership transfer** | Quyền xử lý một object chuyển từ bên gửi sang bên nhận qua một ranh giới rõ ràng. | Producer đưa message vào `BlockingQueue`, sau đó không sửa mutable message đó nữa. |
| **Immutable object** | Nội dung quan sát được không đổi sau khi xây dựng và công bố đúng. | `String`, `Integer`, record chỉ chứa các thành phần immutable. |
| **Safe publication** | Cách làm một đối tượng và trạng thái khởi tạo của nó được thread khác quan sát theo bảo đảm của Java Memory Model. | Dữ liệu gửi qua `BlockingQueue` hoặc kết quả đọc qua `Future.get()`. |
| **Shared mutable state** | Một object có thể thay đổi và nhiều thread cùng có đường truy cập. | Cùng một `HashMap` được nhiều worker cập nhật. |

**Confinement là một thuộc tính của đường đi tham chiếu và cách sử dụng**, không phải kiểu dữ liệu. Cùng một `ArrayList` có thể an toàn khi hoàn toàn local, nhưng trở thành shared mutable state khi đưa tham chiếu của nó cho worker khác trong lúc owner cũ vẫn sửa.

**Ownership ở đây là quy ước thiết kế** do chương trình thực thi và kiểm chứng. Java không mặc định có hệ thống kiểu sở hữu/borrow checker tự ngăn bạn chia sẻ object mutable tùy ý. Muốn quy ước đủ mạnh, cần private fields, immutable messages, API giới hạn quyền sửa, quy trình handoff và các test/invariant thích hợp.

## 4. Ba mức confinement thường gặp

### 4.1. Biến local và object chỉ sử dụng trong một lời gọi

```java
String buildLine(String name, int score) {
    StringBuilder builder = new StringBuilder();
    builder.append(name).append(':').append(score);
    return builder.toString();
}
```

Đây là **method minh họa** đặt trong một class. `builder` được tạo, dùng, rồi bỏ trong một invocation; method trả ra `String` bất biến. Nếu lời gọi của hai thread không chia sẻ tham chiếu `builder`, mỗi invocation có state riêng và không cần `synchronized` quanh `append`.

**Cẩn thận:** “biến local” không đồng nghĩa “object private”:

```java
// Minh họa nguy cơ thoát tham chiếu (escape).
ArrayList<String> local = new ArrayList<>();
someSharedObject.store(local); // Thread khác có thể nhận đúng object này.
local.add("changed");          // Không còn cơ sở khẳng định nó bị confined.
```

Đoạn trên giả định `someSharedObject` có method `store`, không phải class chạy độc lập. Việc tham chiếu thoát ra ngoài **có thể** dẫn tới chia sẻ; nguy cơ xảy ra nếu đối tượng được dùng đồng thời và không có phối hợp. Để an toàn, hoặc giữ nó hoàn toàn local, hoặc chuyển **snapshot bất biến** hay handoff có hợp đồng rõ ràng.

Một object được tạo trong constructor cũng không tự an toàn: nếu để `this` thoát ra trong khi object chưa khởi tạo xong (đăng ký callback, start thread giữ `this`, đưa vào global registry), thread khác có thể quan sát trạng thái chưa hoàn chỉnh. Hoàn thành khởi tạo rồi mới công bố bằng cơ chế phù hợp.

### 4.2. Một worker sở hữu state suốt giai đoạn thực thi

Một worker xử lý từng phần dữ liệu trong collection local:

```java
// Bên trong Callable<List<String>>.call()
List<String> results = new ArrayList<>();
for (String item : input) {
    results.add(transform(item));
}
return List.copyOf(results);
```

Đây là **đoạn code minh họa**, `input` và `transform` do bài toán cung cấp. Mỗi task tạo `results` riêng, không thread nào đồng thời mutate nó. `List.copyOf` tạo danh sách không cho thay đổi cấu trúc; để dữ liệu **bất biến sâu**, bản thân các phần tử `String` ở ví dụ cũng phải bất biến. Nếu phần tử là những bean mutable, copy danh sách **không** tự đóng băng các bean.

### 4.3. Một chủ sở hữu lâu dài cho phần trạng thái chung

Ví dụ một consumer quản lý số dư trong một biến chỉ tồn tại ở thread của nó. Các producer không sở hữu số dư; họ gửi lệnh `Add(amount)` qua queue. Chỉ consumer có quyền áp dụng lệnh, do đó **mọi cập nhật số dư nối tiếp trong một owner**. Chương trình bên ngoài không lấy reference tới biến mutable để sửa trực tiếp.

Đây là mô hình **single-writer / actor-style ownership** ở mức thiết kế, có thể xây bằng Java SE `BlockingQueue`. Không cần gọi một framework actor để có nguyên tắc này.

Single owner thường giúp đơn giản hóa invariant của chính state mà owner nắm giữ. Tuy nhiên, nếu các state khác nhau cần commit nguyên tử với nhau, ownership mỗi phần riêng **không tự cung cấp transaction xuyên owner**.

## 5. Ownership rõ ràng: ai được làm gì, tại thời điểm nào?

Một bản thiết kế tốt nên có câu trả lời cụ thể cho các câu hỏi:

1. **Ai tạo object?** Ai giữ bản tham chiếu mutable ban đầu?
2. **Ai được sửa?** Một thread, một task, một consumer lâu dài, hay nhiều thread qua cùng lock?
3. **Khi nào quyền chuyển?** Khi đặt vào queue, khi `Future` hoàn thành, khi hoàn tất `join`, hay sau thao tác đồng bộ nào?
4. **Bên gửi còn được làm gì?** Có được tiếp tục sửa message sau `put()` không? Nếu không, cách nào ngăn các đường ghi ngoài ý muốn?
5. **Bên nhận biết dữ liệu đã sẵn sàng bằng gì?** Có quan hệ happens-before để quan sát giá trị đúng không?
6. **Lúc kết thúc ai dọn tài nguyên?** Thread sở hữu có đóng file/socket/context và báo lỗi cho bên gọi không?

### Một quy ước owner nên biểu diễn qua API

Ví dụ API ở mức ý tưởng:

```java
interface LedgerCommands {
    void submitCredit(long amount) throws InterruptedException;
    // Không trả về mutable Map<Long, Account> nội bộ để caller tự sửa.
}
```

Đây là **interface minh họa**. Producer chỉ submit, consumer sở hữu dữ liệu. Nếu cần lấy kết quả, cung cấp một **snapshot**, `Future` hoặc response message với quy tắc memory visibility và lifecycle rõ ràng. Đừng trả về reference đến `HashMap`/`ArrayList` nội bộ rồi trông chờ caller “nhớ không sửa”.

## 6. Ownership transfer khác việc chia sẻ cùng tham chiếu

Khi hai thread lần lượt xử lý một mutable object, có thể dùng **handoff**:

```text
Thread producer                              Thread consumer
------------------------------------------   -----------------------------------
Tạo object, owner = producer
Thiết lập đầy đủ dữ liệu
Đưa message vào BlockingQueue
Không sửa hoặc đọc-mutate object sau handoff
                                             queue.take() nhận message
                                             owner = consumer
                                             Đọc/ghi state theo contract
                                             Tạo snapshot / gửi phản hồi
```

Với `BlockingQueue`, các hành động xảy ra trong thread trước khi đặt phần tử vào queue *happen-before* các hành động trong thread khác sau khi truy cập hoặc lấy phần tử đó khỏi queue, theo hợp đồng memory consistency của `java.util.concurrent`. Điều đó bảo đảm **publication/visibility** qua queue.

Nhưng handoff có **hai điều kiện độc lập**:

- **Visibility/order:** bên nhận phải quan sát được dữ liệu đã chuẩn bị trước khi gửi; queue/Future/lock có thể cung cấp HB.
- **Exclusive ownership:** bên gửi **không tiếp tục mutate** object sau khi bàn giao nếu bên nhận có thể đang dùng nó; queue **không** làm biến mất các tham chiếu còn lưu ở producer.

Sai nếu producer vẫn sửa `message` sau `queue.put(message)` và consumer đọc đồng thời: queue bảo đảm những ghi **trước put**, không biến mọi ghi **sau put** thành an toàn. Nếu cần cho cả hai bên cùng đọc, dùng immutable object/snapshot; nếu cần sửa ở cả hai, phải có giao thức chuyển quyền qua lại hoặc bảo vệ mọi truy cập bằng synchronization thích hợp.

Đây là khác biệt giữa **safe publication** và **ongoing thread safety**: một object được công bố đúng vẫn có thể bị data race khi cùng mutate về sau.

### Làm rõ aliasing

Hai biến khác tên vẫn có thể trỏ **cùng object**:

```java
ArrayList<Integer> first = new ArrayList<>();
List<Integer> second = first;
second.add(1);
System.out.println(first); // [1]
```

Đoạn có thể biên dịch trong một method (cần import `List`, `ArrayList`). Đây là aliasing bình thường, không tự là race. Nhưng nếu thread A dùng `first` và thread B dùng `second` đồng thời, confinement bị phá vì đó là **một object duy nhất**. Muốn tạo hai bản độc lập, dùng copy với semantics phù hợp; shallow copy chưa tách các phần tử mutable.

## 7. Safe publication và Java Memory Model

Confinement không cần đồng bộ cho mọi bước cập nhật **bên trong một owner**. Nhưng khi dữ liệu chuyển owner hoặc được công bố, Java Memory Model vẫn quan trọng.

Một số ranh giới hợp lệ thường dùng:

| Ranh giới | Bảo đảm liên quan | Dùng đúng khi |
|---|---|---|
| `Thread.start()` | Hành động trước `start()` HB hành động trong thread được start. | Chuẩn bị dữ liệu trước khi thread bắt đầu. |
| `Thread.join()` thành công | Hành động của thread đã kết thúc HB thread khác sau khi xác nhận kết thúc qua join. | Owner hoàn thành rồi caller đọc/thu kết quả. |
| `ExecutorService.submit()` → `Future.get()` | Hành động trước submit HB task; hành động task HB các hành động sau `Future.get()` thành công. | Trả kết quả từ worker về caller. |
| `BlockingQueue.put/offer` → `take/poll` nhận phần tử | Hành động trước khi đặt phần tử HB hành động sau khi lấy/truy cập phần tử ở thread khác. | Gửi dữ liệu/command giữa owner. |
| `synchronized` unlock → lock cùng monitor | Release/Acquire tạo `synchronizes-with` và HB theo thứ tự. | Chia sẻ mutable state có khóa. |
| `volatile` write → read phù hợp | Bảo đảm ordering/visibility liên quan biến volatile. | Cờ/công bố đơn giản có giao thức đúng, không có compound atomicity. |

HB bảo đảm visibility/ordering của các hành động liên quan. **HB không đồng nghĩa object tự động immutable, và không buộc các thread hoàn thành theo một lịch duy nhất.**

Với `Future.get()`, caller nên kiểm tra lỗi `ExecutionException`, `InterruptedException`; lời gọi bị hủy/không hoàn tất không thể xem như đã có kết quả sẵn sàng. Trong các API trả kết quả có hiệu lực thông qua hợp đồng cụ thể, đọc lại JavaDoc tương ứng thay vì suy rằng một lần sleep đã đủ cho phép nhận object.

**Trường `final` và immutable objects:** Java có các bảo đảm đặc biệt về final fields khi object được xây dựng đúng và không làm `this` escape trong constructor. Nhưng `final List<T> items` chỉ làm tham chiếu `items` không được gán lại; nếu list còn mutable và bị chia sẻ, phần tử vẫn có thể thay đổi. Hãy phân biệt **immutable reference**, **immutable container**, và **deeply immutable object graph**.

## 8. Ví dụ thực hành Java 17+: task-local data và single owner

Chương trình có hai phần:

- Hai `Callable` mỗi cái xây một `ArrayList<Integer>` **riêng** rồi trả `List.copyOf(local)`. Caller lấy hai kết quả bằng `Future.get()` và tự gộp ở thread main.
- Một thread duy nhất sở hữu biến `balance`. Main gửi lệnh cộng qua `ArrayBlockingQueue`; consumer là **nơi duy nhất** cập nhật `balance`. Giá trị `Integer` gửi qua queue là immutable.

Tạo file **`OwnershipDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OwnershipDemo {
    static final class BuildChunk implements Callable<List<Integer>> {
        private final int first;
        BuildChunk(int first) { this.first = first; }

        @Override
        public List<Integer> call() {
            ArrayList<Integer> local = new ArrayList<>();
            local.add(first);
            local.add(first + 1);
            return List.copyOf(local);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<List<Integer>> one = executor.submit(new BuildChunk(1));
            Future<List<Integer>> two = executor.submit(new BuildChunk(3));

            List<Integer> merged = new ArrayList<>();
            merged.addAll(one.get());
            merged.addAll(two.get());
            System.out.println("merged=" + merged);
            System.out.println("sum=" + merged.stream().mapToInt(Integer::intValue).sum());
        } finally {
            executor.shutdown();
        }

        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(4);
        Thread owner = new Thread(() -> {
            int balance = 0; // Chỉ thread này có quyền thay đổi.
            try {
                while (true) {
                    int command = inbox.take();
                    if (command == Integer.MIN_VALUE) break; // Dừng sau các lệnh.
                    balance += command;
                }
                System.out.println("ownerTotal=" + balance);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "account-owner");

        owner.start();
        inbox.put(5);
        inbox.put(7);
        inbox.put(Integer.MIN_VALUE);
        owner.join();
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 OwnershipDemo.java
java OwnershipDemo
```

**Stdout đã kiểm chứng:**

```text
merged=[1, 2, 3, 4]
sum=10
ownerTotal=12
```

### Vì sao kết quả đúng dù scheduler không cố định?

1. Mỗi `BuildChunk.call()` chỉ tạo và sửa danh sách `local` **trong worker của chính task đó**; các worker không chia sẻ danh sách mutable.
2. `List.copyOf(local)` trả về danh sách không hỗ trợ sửa cấu trúc. Từng phần tử là `Integer` immutable, nên kết quả ở đây không chứa object mutable cần phối hợp bổ sung.
3. Main gọi `one.get()` và `two.get()` theo **thứ tự cố định** rồi mới `addAll` vào `merged` (do main sở hữu). Dù task thứ hai chạy xong trước, thứ tự gộp vẫn là `[1, 2, 3, 4]`. `Future.get()` cho caller ranh giới hoàn tất và memory consistency phù hợp.
4. `balance` là biến local nằm trong lambda của consumer và **không tham chiếu ra ngoài** để thread khác sửa. Các command gửi trong queue được consumer lấy theo thứ tự FIFO của `ArrayBlockingQueue`.
5. Main gửi `5`, `7` rồi sentinel `Integer.MIN_VALUE`. Consumer xử lý hai số đầu, sau đó dừng; kết quả luôn `12` khi chương trình hoàn thành bình thường.
6. `owner.join()` chờ receiver kết thúc trước khi main thoát; chương trình không phụ thuộc vào delay hay `sleep()`.

**Giới hạn chủ đích của ví dụ:** sentinel `Integer.MIN_VALUE` là tín hiệu kết thúc được dành riêng, nên hệ thống thực phải bảo đảm giá trị này **không là dữ liệu hợp lệ**, hoặc nên dùng kiểu thông điệp tách riêng như `record Add(int amount)` và `enum Stop`. Ví dụ chỉ có **một producer** để làm rõ thứ tự FIFO; với nhiều producer, các message từ producer khác nhau có thể xen kẽ, và việc xác định thứ tự nghiệp vụ cần contract rõ. Nếu consumer ném exception, hệ thống thật phải báo lỗi thay vì chỉ im lặng: có thể dùng `Future`, kênh phản hồi hoặc completion signal. `shutdown()` ở đây dừng nhận task mới cho executor; trong ứng dụng dài hạn cần có chiến lược await/close theo lifecycle và xử lý cancellation.

**Điều quan trọng:** không có `synchronized` quanh mỗi lần cộng `balance`, vì không có thread thứ hai cập nhật biến đó. Nhưng `BlockingQueue` vẫn là primitive đồng bộ giữa các thread. “Không cần lock cho state local” **không có nghĩa mọi giao tiếp xuyên thread đều không cần đồng bộ**.

## 9. ThreadLocal: một bản giá trị gắn với mỗi thread

`ThreadLocal<T>` cấp cho **mỗi thread** một value riêng theo cùng một `ThreadLocal` key. Nó hữu ích cho state phụ trợ đòi hỏi gắn với thread, chẳng hạn buffer ngắn hạn không muốn truyền qua nhiều lớp method, nhưng cần hiểu giới hạn.

Ví dụ:

```java
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

static String format(String name, int quantity) {
    StringBuilder builder = BUFFER.get();
    try {
        builder.setLength(0);
        builder.append(name).append(':').append(quantity);
        return builder.toString();
    } finally {
        BUFFER.remove();
    }
}
```

Đây là **các thành viên minh họa của một class**; yêu cầu import mặc định `java.lang` là đủ. `BUFFER.get()` trong mỗi thread trả về bản `StringBuilder` của thread đó. Vì mỗi `StringBuilder` chỉ được dùng bởi thread gắn với nó và không được công bố cho thread khác, thao tác append không cần synchronized.

**Vì sao dùng `remove()`?** Worker của `ExecutorService` có thể được tái sử dụng cho nhiều task khác nhau; giá trị `ThreadLocal` có thể sống cùng worker và gây rò trạng thái, bộ nhớ hoặc dữ liệu của task trước sang task sau. `remove()` ở `finally` giúp xóa binding của thread hiện tại kể cả khi task ném exception. Với use case chỉ một method đơn giản, một biến local `new StringBuilder()` thường rõ ràng hơn và tránh quản lý lifecycle của `ThreadLocal`.

### Những giới hạn quan trọng của ThreadLocal

- **Thread-local không đồng nghĩa request-local/task-local.** Hai request chạy tuần tự trên cùng pooled thread có thể thấy cùng value nếu không reset/remove; một request chuyển sang thread khác lại thấy value khác.
- `ThreadLocal` không copy sâu object được gán vào. Nếu hai thread gọi `set(sharedMutableObject)` với **cùng tham chiếu object**, cả hai vẫn có thể race trên object đó dù ThreadLocal keys độc lập.
- `ThreadLocal` không tạo khóa/transaction cho resource dùng chung (file, DB, socket, static map).
- `InheritableThreadLocal` có semantics kế thừa khác, không biến state thành an toàn khi dữ liệu mutable được chia sẻ; không giả định nó tự truyền đúng qua thread pool.
- Đừng dùng ThreadLocal để giấu tham số nghiệp vụ quan trọng đến mức không thể biết owner, cleanup hoặc đường truyền dữ liệu. Context explicit thường dễ kiểm thử hơn.
- Với **virtual threads (Java 21+)**, ThreadLocal vẫn tồn tại nhưng mỗi virtual thread có lifecycle riêng; tạo số lượng cực lớn thread kèm state nặng có thể tốn bộ nhớ. Không thiết kế logic dựa vào “thread nhất định được tái sử dụng” khi dùng virtual threads.

## 10. Single-writer ownership so với synchronized / atomic

Confinement là một **lựa chọn thiết kế**, không phải luôn là thay thế tối ưu cho các cơ chế khác.

| Tình huống | Cách tiếp cận phù hợp | Điều phải chứng minh |
|---|---|---|
| Mỗi task tính một kết quả độc lập | Local state rồi immutable result/`Future.get()` | Không escape mutable object; kết quả công bố đúng |
| Nhiều producer phát command, một state owner | `BlockingQueue` + single consumer | Đúng ordering, backlog/backpressure, shutdown, error handling |
| Nhiều task truy cập cùng một invariant cần đáp ứng tức thời | `synchronized` / `ReentrantLock` | Mọi read/write liên quan dùng cùng protocol |
| Bộ đếm độc lập cần cập nhật từ nhiều thread | `AtomicInteger` / `LongAdder` (theo ngữ nghĩa cần) | Atomicity và snapshot semantics phù hợp |
| Mỗi key có thể xử lý độc lập | Partition/sharding theo key và owner | Không có cập nhật xuyên partition phá invariant |
| Dữ liệu chia sẻ để đọc, không thay đổi | Immutable snapshot công bố an toàn | Không giữ tham chiếu mutable lồng bên trong |
| Một ít buffer phụ trợ theo thread | Local variable hoặc `ThreadLocal` | Không chia sẻ reference, có cleanup nếu dùng pool |

**Thread confinement không có nghĩa “thread affinity là miễn phí”.** Chuyển tất cả request qua một owner làm giảm cạnh tranh cập nhật nhưng có thể tạo queue bottleneck, tăng latency, tràn hàng đợi hoặc khiến một thread phải gánh quá nhiều việc. Với CPU-bound tasks độc lập, partition thành nhiều owner có thể khai thác nhiều core hơn.

**Dùng một owner cho một invariant** khi tính đúng đắn đơn giản hơn; nếu state phải cập nhật atomically cùng nhiều owner khác, có thể cần giao thức phối hợp phức tạp hơn. Đừng chia nhỏ ownership chỉ vì muốn thêm parallelism khi không giữ được invariant.

## 11. Common pitfalls: “chỉ một thread sửa” vẫn có thể sai

### 11.1. Một phía dùng lock, phía còn lại đọc trực tiếp

```java
// Minh họa sai khi truy cập cùng trạng thái không theo một protocol.
synchronized (guard) {
    sharedValue++;
}
// Ở thread khác: int value = sharedValue; // đọc không có cùng khóa/HB
```

Đây là đoạn code minh họa với `guard` và `sharedValue` đã khai báo. Writer khóa đúng không đủ nếu reader đọc mutable state mà không có quan hệ HB. Confinement chỉ đúng khi reader **không đọc trực tiếp** trong giai đoạn chỉ owner sở hữu; hãy gửi snapshot hoặc dùng cùng synchronization protocol.

### 11.2. Bàn giao xong vẫn sửa object

```java
// Minh họa sai nếu producer tiếp tục mutate sau publication.
List<String> message = new ArrayList<>();
message.add("before");
queue.put(message);
message.add("after"); // consumer có thể đang đọc message.
```

Đây là đoạn minh họa trong method `throws InterruptedException`, với `queue` giả định là `BlockingQueue<List<String>>`. `put` bảo đảm visibility cho những hành động **trước put**; nó không biến việc đồng thời sửa object thành an toàn. Khắc phục bằng immutable `List.copyOf(message)`, ownership handoff dứt khoát hoặc lock bao phủ tất cả read/write.

### 11.3. Trả reference tới state nội bộ

```java
class Owner {
    private final List<String> data = new ArrayList<>();

    List<String> getData() {
        return data; // caller có thể mutate mà owner không biết.
    }
}
```

Đây là class minh họa cần import `java.util.List`, `java.util.ArrayList`. `private` chỉ bảo vệ **field reference** khỏi truy cập trực tiếp, còn method đã trả object mutable ra ngoài. Dùng snapshot `List.copyOf(data)` khi đang ở đúng owner hoặc có khóa phù hợp; nếu element mutable, cũng cần snapshot/copy đến độ sâu mà contract yêu cầu.

### 11.4. Dùng ThreadLocal để giữ “owner” của request trong pool

Nếu một task đặt dữ liệu vào ThreadLocal rồi task tiếp theo có khả năng chạy trên **worker khác**, request context không theo task. Nếu task tiếp theo chạy trên **worker cũ**, giá trị có thể còn sót từ request trước. Do đó ThreadLocal không phải công cụ đảm bảo ownership theo request; dùng tham số explicit, immutable context, hoặc API truyền context có lifecycle rõ ràng.

### 11.5. Chỉ có một writer nhưng nhiều reader không phối hợp

**Single-writer không tự suy ra mọi reader đều thread-safe**. Nếu writer sửa một `HashMap` trong khi reader khác duyệt nó mà không đồng bộ, vẫn có data race; một writer chỉ giúp tránh *writer–writer race*, không tự loại bỏ *writer–reader race*. Cần immutable snapshot, copy-on-write, read/write locking hoặc protocol mà readers không truy cập trạng thái đang mutate.

### 11.6. Giữ tham chiếu mutable trong immutable wrapper

`List.copyOf(list)` làm **danh sách kết quả không thể add/remove**, nhưng nếu phần tử là `Order` mutable, `get(0).setStatus(...)` vẫn có thể thay đổi đối tượng. Java `record` cũng chỉ mặc định làm các component fields `private final`; record chứa `List<MutableItem>` không tự deep immutable. Cần defensive copy, immutable element types và constructor/accessor phù hợp.

### 11.7. Tưởng thứ tự lấy việc là thứ tự xong việc

Queue FIFO cho một consumer xác định thứ tự **nhận** command theo thứ tự enqueue, nhưng hệ thống có nhiều producer có thứ tự enqueue tổng có thể thay đổi; thêm I/O bất đồng bộ có thể làm các side effect hoàn tất khác thứ tự. Nếu nghiệp vụ cần total order, sequence number hoặc một owner điều phối, phải định nghĩa rõ các điểm cấp thứ tự và hoàn thành.

## 12. Vòng đời và lỗi của owner

Thiết kế owner không dừng ở câu “consumer là thread duy nhất sửa state”. Nó còn cần trả lời các tình huống thực:

1. **Khởi động:** owner được tạo trước khi nhận command, hay queue có thể đệm command trong lúc owner khởi động?
2. **Dừng:** caller có gửi tín hiệu kết thúc sau mọi producer không? Có drain queue hay bỏ task? Sentinel có thể xung đột với dữ liệu thật không?
3. **Backpressure:** queue có giới hạn hay không? `put()` block khi đầy, `offer(timeout)` có thể báo thất bại; chính sách đó phải rõ.
4. **Exception:** nếu handler lỗi, owner có cần phản hồi lỗi cho caller và vẫn giữ state nhất quán không? Exception không tự hoàn tác cập nhật đã làm.
5. **Cancellation/interrupt:** một worker đợi `take()` có thể bị interrupt; phải xử lý cleanup và trạng thái kết thúc, không nuốt `InterruptedException`.
6. **Resource ownership:** ai chịu trách nhiệm đóng resource (`AutoCloseable`) và vào thời điểm nào? Đừng để producer đóng resource trong khi consumer còn đang dùng.
7. **Memory:** queue có thể tích lũy rất nhiều message nếu producer nhanh hơn consumer. Dùng bounded queue và quan sát queue length, processing time, latency, rejection/backpressure.

Với `ExecutorService`, gọi `shutdown()` ngừng nhận task mới nhưng không tự chờ mọi task hoàn tất. Dùng `Future.get()` với task quan trọng hoặc `awaitTermination()` khi cần ranh giới đóng sạch; xử lý `InterruptedException`/`ExecutionException`/timeout theo contract. Không dùng `Thread.sleep()` để thay thế việc đồng bộ lifecycle.

## 13. Thiết kế ownership rõ ràng khi có nhiều worker

Có một số mô hình tổ chức thông dụng:

**Map-reduce cục bộ:** mỗi worker tạo accumulator riêng; sau `Future.get`, main merge. Ưu điểm: ít contention. Nếu tổng hợp cần kết quả chính xác trên kiểu số có thể overflow hoặc số thực không kết hợp tuyệt đối, phải định nghĩa thứ tự và chính sách độ chính xác.

**Partition theo key:** `hash(key)` hoặc quy tắc định tuyến đưa tất cả update của cùng key tới owner duy nhất. Các key độc lập có thể chạy song song. Cần ổn định routing khi resize/rebalance và đồng bộ khi chuyển quyền sở hữu partition.

**Event loop / actor-style:** một thread xử lý tuần tự queue command và sở hữu state. Rất phù hợp khi state có nhiều trường liên quan, nhưng phải tránh blocking I/O dài khiến queue bị tắc. Nếu cần async I/O, phải thiết kế callback/reentry và thứ tự áp dụng kết quả.

**Snapshot publishing:** owner tạo một snapshot hoàn chỉnh rồi công bố an toàn cho nhiều reader. Snapshot immutable cho phép reader đọc không khóa trong suốt vòng đời snapshot; thế hệ tiếp theo được tạo ở nơi riêng rồi thay snapshot theo cơ chế publication phù hợp (ví dụ volatile reference đến immutable snapshot). Đây là chiến lược tốt cho đọc nhiều/ghi ít, nhưng có chi phí copy và không tạo transaction với các side effect bên ngoài.

### Sơ đồ lựa chọn nhanh

```text
Có mutable state cần xử lý?
    |
    +-- Không: immutable data / pure function -> chia sẻ đọc an toàn khi công bố đúng
    |
    +-- Có
         |
         +-- Chỉ một task dùng, không escape? -> task-local / thread confinement
         |
         +-- Có nhiều producer, một nơi cập nhật state?
         |       -> single owner + queue/command + backpressure
         |
         +-- Nhiều thread cần cập nhật cùng invariant?
                 -> synchronized / Lock / atomic / dữ liệu phân vùng
                    theo đúng granularity và contract
```

Sơ đồ là hướng dẫn kiến trúc ban đầu; không phải thuật toán cho mọi bài toán. Việc lựa chọn còn phụ thuộc throughput, latency, dữ liệu cần nhất quán, failure recovery và nhu cầu nhiều process.

## 14. Thread confinement và Java 21+ virtual threads

Virtual threads dùng mô hình rất nhiều thread Java nhẹ hơn platform threads, nhưng **quy tắc ownership và data race vẫn áp dụng**:

- Một mutable object chỉ được một virtual thread dùng và không escape vẫn có thể confined.
- `ThreadLocal` gắn với từng virtual thread; khác với tập nhỏ các worker platform thread tái sử dụng. Mỗi value lớn nhân với số lượng virtual thread lớn có thể tốn bộ nhớ.
- Đừng suy rằng “virtual thread có ít overhead” đồng nghĩa có thể chia sẻ `ArrayList/HashMap` mutable giữa chúng mà không khóa.
- Bounded queues, backpressure và state partitioning vẫn cần thiết khi downstream hữu hạn.

Ví dụ thực hành của bài **chạy trên Java 17** với platform threads. Virtual threads là cơ chế được chuẩn hóa từ Java 21; không cần dùng chúng để hiểu thread confinement.

## 15. Kiểm thử và đánh giá kiến trúc confinement

### Kiểm chứng correctness

1. Vẽ **ownership map**: mỗi object mutable, ai tạo, ai được đọc, ai được ghi, nơi bàn giao, nơi kết thúc lifecycle.
2. Kiểm tra **escape paths**: return reference, field static, listener/callback, lambda capture, shared collection, queue, constructor leak.
3. Với mỗi handoff, xác định **happens-before** nào làm dữ liệu đã chuẩn bị hiển thị cho receiver.
4. Kiểm tra bên gửi **có còn được phép truy cập/mutate** sau handoff không; dùng immutable snapshot hoặc không giữ reference nếu cần.
5. Stress test nhiều producers/consumers, nhiều thứ tự completion, cancellation và queue full; assert invariant, số message được xử lý, đúng lỗi/timeout.
6. Test cleanup `ThreadLocal.remove()` với pooled workers chạy nhiều task nối tiếp; chú ý tránh rò dữ liệu xuyên task.
7. Đo throughput, latency p95/p99, queue depth, CPU và memory. Nếu một owner thành bottleneck, cân nhắc partition theo invariant có thể tách an toàn.

### Ví dụ assertion có ý nghĩa

Nếu gửi 100 lệnh tăng `1` qua một consumer và chờ completion, tổng phải bằng 100. Nhưng nếu có khả năng retry lệnh, phải xác định lệnh được áp dụng đúng một lần hay có idempotency key; single-owner chỉ làm quá trình cập nhật tuần tự, **không tự mang lại exactly-once delivery**.

Với mô hình task-local + merge, kiểm tra đầy đủ phần tử, không trùng/bỏ sót, và input không bị worker thay đổi ngoài ý muốn. Tránh test “chạy 1000 lần không crash” làm bằng chứng duy nhất cho thread safety.

## 16. Các lỗi hiểu nhầm thường gặp

1. **“Object được tạo trong biến local thì chắc chắn chỉ một thread dùng.”** Sai nếu tham chiếu escape vào shared field, callback, queue hoặc được truyền cho thread khác khi vẫn đang mutate.
2. **“Đã dùng BlockingQueue thì có thể sửa message sau put.”** Sai; queue đảm bảo publication cho hành động trước handoff, không bảo vệ những ghi ngoài owner sau đó.
3. **“Một writer duy nhất nên reader nào cũng đọc được không khóa.”** Sai; writer–reader data race vẫn tồn tại nếu chia sẻ mutable state thiếu synchronization.
4. **“ThreadLocal = task-local = request-local.”** Sai; thread pool tái sử dụng thread và task có thể đổi worker.
5. **“List.copyOf làm tất cả element bất biến.”** Sai; copy container có thể vẫn chứa reference đến element mutable.
6. **“final field nghĩa là object immutable.”** Sai; `final List` vẫn có thể chứa và trỏ tới cấu trúc mutable.
7. **“Dùng synchronized quanh worker là bắt buộc để thread-safe.”** Không, nếu worker chỉ sửa state riêng và dùng handoff có memory semantics rõ; lock có thể không cần ở phần xử lý local.
8. **“Single owner bảo đảm mọi tác vụ hoàn thành đúng thứ tự gửi.”** Còn phụ thuộc thứ tự enqueue của nhiều producer, xử lý async và contract phản hồi.
9. **“Future trả ra dữ liệu đồng nghĩa worker đã bảo đảm mọi side effect ngoài JVM thành công.”** Không; `Future.get()` cho kết quả/ngoại lệ của task, không phải transaction ở database hay network.
10. **“Không dùng lock nghĩa là không có đồng bộ.”** Các primitive như `BlockingQueue`/`Future` vẫn phối hợp thread và mang memory guarantees.
11. **“Chỉ cần nhanh là tốt.”** Phải ưu tiên invariant, visibility, lifecycle và tính đúng đắn; sau đó mới đo contention/throughput/latency.
12. **“Thread confinement tự động ngăn deadlock.”** Nó giảm nhu cầu dùng lock cho state local, nhưng owner vẫn có thể kẹt đợi phản hồi từ owner khác hoặc blocking queue, tạo vòng phụ thuộc và không tiến triển.

## 17. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Thread A tạo `ArrayList` trong một method, truyền tham chiếu đó cho B rồi tiếp tục `add` trong khi B duyệt list. Có thread confinement không?  
**Đáp án:** Không. Object đã escape và có hai bên truy cập đồng thời. Cần bàn giao ownership dứt khoát, tạo snapshot immutable, hoặc phối hợp mọi read/write.

**Câu 2.** Vì sao `BlockingQueue.put(message)` hữu ích nhưng chưa đủ nếu producer vẫn sửa `message` sau đó?  
**Đáp án:** Queue có HB từ hành động trước put tới hành động receiver sau take, nhưng không tự ngăn data race trên những cập nhật sau khi put. Phải dừng mutate hoặc dùng protocol khác.

**Câu 3.** Hai `Callable` mỗi cái tự xây `ArrayList<Integer>` rồi trả `List.copyOf`; main đợi `Future.get()` trước khi gộp. Có cần khóa từng lần `local.add()` không?  
**Đáp án:** Không, nếu mỗi danh sách thật sự chỉ thuộc worker của nó; `get` tạo ranh giới hoàn tất và visibility. Main gộp trên một list mà main sở hữu.

**Câu 4.** Một pooled thread dùng `ThreadLocal<StringBuilder>` cho task trước, task sau tiếp tục dùng cùng worker. Có thể còn state không mong muốn không?  
**Đáp án:** Có. `ThreadLocal` gắn với thread và có thể tồn tại qua nhiều task. Reset state và `remove()` trong `finally` theo lifecycle.

**Câu 5.** Một object có `private final List<Order> orders`; caller lấy bản `List.copyOf(orders)`. Có bảo đảm caller không thể thay đổi `Order` bên trong không?  
**Đáp án:** Không. `List.copyOf` chỉ bảo vệ cấu trúc list, không deep-freeze phần tử mutable. Cần immutable `Order` hoặc defensive deep snapshot.

**Câu 6.** Tại sao single-writer thường giảm lock contention nhưng không bảo đảm luôn nhanh hơn shared-state có khóa?  
**Đáp án:** Single consumer có thể thành bottleneck, queue có chi phí/hàng đợi và producer cần backpressure. Kết quả phụ thuộc tải và khả năng partition.

**Câu 7.** Handoff bằng `Thread.sleep(100)` giữa producer và consumer có đủ để công bố dữ liệu an toàn không?  
**Đáp án:** Không. Sleep không tạo một quan hệ HB phù hợp cho việc chia sẻ state; dùng queue, lock, volatile protocol, `Future` hoặc primitive có contract đúng.

**Câu 8.** Nếu một thread sở hữu `balance` nhưng nhiều thread có thể đọc trực tiếp qua getter không đồng bộ, còn được xem là confinement an toàn không?  
**Đáp án:** Không, vì dữ liệu mutable được chia sẻ với reader thiếu giao thức. Trả snapshot qua owner hoặc bảo vệ reader bằng memory-consistency protocol.

**Câu 9.** Muốn chia một chủ sở hữu thành bốn để tăng hiệu năng, điều kiện quan trọng nhất là gì?  
**Đáp án:** Partition state theo invariant độc lập và bảo đảm key/message luôn đến đúng owner; các giao dịch xuyên partition cần giao thức riêng.

**Câu 10.** `volatile Snapshot current` trỏ tới snapshot thực sự immutable, owner xây snapshot mới rồi gán `current = snapshot`. Reader chỉ đọc snapshot hiện tại. Có thể tránh lock ở reader không?  
**Đáp án:** Có, nếu snapshot được khởi tạo/công bố đúng, toàn bộ object graph được đọc là immutable, và reader lấy reference `volatile` một lần cho lần xử lý. Gán volatile tạo publication/visibility; không nên để owner mutate snapshot cũ đang được reader sử dụng.

## Tài liệu tham khảo chính thức

- [Java SE 17 — java.util.concurrent package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): bộ primitive concurrency và memory-consistency properties.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission và lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion và kết quả từ task.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): mô hình producer-consumer, blocking và memory consistency.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `withInitial`, `get` và `remove`.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): danh sách không hỗ trợ mutate cấu trúc, lưu ý phần tử mutable.
- [JLS `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, data race, happens-before và monitor.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join` và thread lifecycle.

**Điều cần nhớ:** muốn dựa vào thread confinement để có thread safety, hãy kiểm soát **mọi alias đến mutable object**, quy định **ai được sửa khi nào**, và tạo **ranh giới publication/handoff có happens-before**. Khi ownership rõ ràng, nhiều cập nhật local không cần khóa; sự phối hợp giữa các owner vẫn cần cơ chế tin cậy và xác minh invariants.