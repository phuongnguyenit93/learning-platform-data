# Ownership và tránh chia sẻ state không cần thiết trong Java Concurrency

## 1. Vấn đề: chia sẻ dữ liệu quá nhiều làm chương trình khó đúng

Khi nhiều thread cùng làm việc, trực giác ban đầu thường là đặt các biến vào một object dùng chung rồi thêm `synchronized`, `Lock` hoặc atomic để bảo vệ. Điều đó có thể cần thiết, nhưng một thiết kế tốt thường bắt đầu từ câu hỏi sớm hơn: **dữ liệu này thực sự cần được nhiều tác vụ cùng sở hữu và cùng thay đổi hay không?**

Trong thiết kế đồng thời (concurrency design), **ownership** là quy ước về **ai được quyền đọc, ai được quyền thay đổi một trạng thái, và khi nào quyền đó được chuyển giao**. Đây là quy ước thiết kế ở cấp object/task/API; Java không có một hệ thống kiểu tuyến tính bắt buộc chỉ một chủ sở hữu như một số ngôn ngữ khác. Vì thế lập trình viên phải thể hiện quy ước bằng cấu trúc dữ liệu, giao diện, vòng đời task và cơ chế trao đổi.

Bài học thuộc Java concurrency nói chung, dùng Java 17+ và `java.util.concurrent`. Không dùng thành phần Spring.

Mục tiêu thực hành:

- Nhận diện **shared mutable state** và những đường tham chiếu vô tình làm nó bị chia sẻ.
- Thiết kế dữ liệu sở hữu riêng cho một task, hoặc snapshot bất biến được nhiều task cùng đọc.
- Chuyển thông tin giữa các task bằng message/queue/Future thay vì cùng sửa một object.
- Phân biệt **ownership**, **immutability**, **thread confinement**, **safe publication**, **synchronization** và **data race**.
- Thiết lập ranh giới vòng đời, bảo đảm dữ liệu và lỗi được thu về trước khi task kết thúc.
- Biết khi nào state thật sự cần dùng chung, và tối thiểu hóa phạm vi chia sẻ thay vì cố loại bỏ mọi cơ chế đồng bộ.

## 2. Từ shared mutable state đến quyền sở hữu

Một object trở thành **shared** khi ít nhất hai thread có thể truy cập cùng object đó. Nếu object hoặc các object nó tham chiếu có thể thay đổi, ta có **shared mutable state**. Ví dụ:

```java
// Ví dụ minh họa về thiết kế dễ gây lỗi; không phải chương trình độc lập.
class SharedCart {
    final java.util.List<String> items = new java.util.ArrayList<>();
}
SharedCart cart = new SharedCart();

// Nếu hai task gọi cart.items.add(...) đồng thời:
// ArrayList không bảo đảm an toàn cho cập nhật đồng thời.
```

Hai vấn đề tách biệt thường xuất hiện:

1. **Tính nguyên tử / race condition:** thao tác nhiều bước bị xen kẽ, gây mất cập nhật, trạng thái trung gian không hợp lệ hoặc hỏng cấu trúc dữ liệu.
2. **Visibility và ordering:** thread khác không nhất thiết quan sát đúng thời điểm/trật tự ghi nếu không có quan hệ *happens-before* thích hợp theo Java Memory Model.

Thêm `volatile` vào tham chiếu `cart` không làm `ArrayList` bên trong thành thread-safe. Thêm `AtomicInteger` cho một trường không tự bảo vệ bất biến liên quan đến nhiều trường. Và đặt `synchronized` lên một phương thức không giúp gì nếu các caller vẫn truy cập dữ liệu qua những đường tham chiếu không được bảo vệ.

### Ownership mô tả điều gì?

Xét một chương trình nhận danh sách yêu cầu rồi tính kết quả:

- **Đầu vào:** ai tạo? Ai được sửa trước và sau khi nộp task?
- **Trong task:** trạng thái tạm có được giữ trong biến local và không lộ cho thread khác?
- **Kết quả:** task trả object mới, hay sửa trực tiếp bảng kết quả của caller?
- **Chuyển giao:** sau khi nộp message, producer có tiếp tục sửa cùng object không?
- **Vòng đời:** caller có chờ kết quả hoặc đóng executor trước khi kết thúc không?

Một contract tốt khiến câu trả lời rõ ràng. Ví dụ: “Caller tạo `Task` bất biến; mỗi worker chỉ dùng biến local; worker trả `Result`; caller duy nhất tổng hợp `Result` sau `Future.get()`.” Khi đó ít trạng thái dùng chung cần đồng bộ.

**Owner không nhất thiết là một thread cố định.** Task có thể chạy trên bất kỳ thread nào do executor chọn, nhưng vẫn có quyền sở hữu riêng đối với dữ liệu của task. Ngược lại, object bất biến có thể được nhiều thread cùng đọc mà không cần chỉ định một thread sở hữu độc quyền khi đọc.

## 3. Ba chiến lược thiết kế thường dùng

| Chiến lược | Quyền truy cập | Khi phù hợp | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Task-local / thread-confined state** | Một task giữ và sửa dữ liệu riêng | Tính toán trung gian, parser, buffer tạm, accumulator độc lập | Không công bố tham chiếu mutable cho task khác |
| **Immutable shared data** | Nhiều task đọc; không ai sửa object sau khi tạo | Configuration, request snapshot, dữ liệu tra cứu | Bất biến phải bao phủ các thành phần mutable bên trong |
| **Message passing / ownership transfer** | Producer giao thông tin cho consumer; consumer là bên cập nhật state của nó | Worker queue, actor-like component, pipeline | Cần quy tắc đóng, giới hạn queue, xử lý lỗi và không mutate sau khi chuyển |

Ba cách có thể kết hợp: một producer gửi **message bất biến** vào queue, mỗi consumer dùng **local state** của mình; kết quả trả về bằng `Future` hoặc một queue phản hồi. Đây là cách giảm bớt số object bị nhiều thread cùng sửa.

Không nên hiểu “ownership” theo nghĩa chỉ thread duy nhất mới được tham chiếu một object. Với object bất biến, chia sẻ tham chiếu có thể an toàn; với object mutable, cần làm rõ **quyền sửa** và **cơ chế công bố**.

## 4. Ví dụ trước–sau: bỏ bộ đếm tổng dùng chung

Cách dễ gặp là các worker cùng ghi vào một biến tổng:

```java
// Minh họa mẫu dễ xảy ra data race, không phải chương trình độc lập.
int[] total = {0};
Runnable work = () -> {
    // Giả sử nhiều thread cùng chạy work.
    total[0]++; // đọc -> cộng -> ghi; không atomic
};
```

`total[0]++` gồm các bước đọc, tính và ghi; với nhiều worker, cập nhật có thể bị mất. Ngoài ra, mã này không có cơ chế chờ hoàn thành hoặc công bố kết quả đầy đủ. Có thể thay bằng `AtomicInteger` khi đúng là một bộ đếm chung, nhưng đôi khi dữ liệu không cần cộng từ nhiều thread.

**Thiết kế theo ownership:** phân vùng dữ liệu, mỗi task xử lý phần của mình, rồi trả một `Result`; chỉ caller tổng hợp sau khi task hoàn tất.

Lưu mã sau vào tệp **`OwnedTasksDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OwnedTasksDemo {
    record Task(String id, int units) {}
    record Result(String id, int cents) {}

    static Result calculate(Task task) {
        // subtotal chỉ thuộc về một lần thực thi task.
        int subtotal = task.units() * 100;
        return new Result(task.id(), subtotal);
    }

    public static void main(String[] args) throws Exception {
        List<Task> tasks = List.of(
                new Task("A", 2),
                new Task("B", 3)
        );

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Future<Result>> pending = new ArrayList<>();
            for (Task task : tasks) {
                pending.add(executor.submit(() -> calculate(task)));
            }

            // Caller duy nhất đọc và trình bày kết quả.
            for (Future<Result> future : pending) {
                Result result = future.get();
                System.out.println(result.id() + "=" + result.cents());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac OwnedTasksDemo.java
java OwnedTasksDemo
```

Stdout:

```text
A=200
B=300
```

**Vì sao chương trình không cần lock cho tổng tiền?**

1. `Task` chỉ chứa `String` và `int`, những thành phần không bị sửa trong chương trình; `List.of(...)` tạo danh sách không cho sửa cấu trúc danh sách.
2. Mỗi lần gọi `calculate` tạo biến local `subtotal` riêng. Không có hai worker cùng ghi `subtotal`.
3. `Result` là record mới của từng task; worker không ghi vào danh sách kết quả chung mà trả về qua `Future`.
4. Caller duy nhất tạo/thêm vào `pending`; lúc đó các worker chỉ giữ `Task` và trả `Result`, không sửa `pending`.
5. `Future.get()` chờ task hoàn tất và cung cấp quan hệ *happens-before* theo contract executor. Mọi ghi của task trước khi hoàn tất được caller quan sát đúng khi lấy kết quả.
6. Dù hai task có thể hoàn thành theo thứ tự khác nhau, thứ tự in là **A rồi B** vì `pending` giữ thứ tự nộp và caller đọc từng `Future` theo thứ tự ấy.

Nếu chương trình cần cộng tất cả kết quả, caller có thể làm sau các `get()` bằng một biến local, không cần các worker cộng chung. Trong tác vụ thực tế, `finally` nên quản lý cả thời hạn dừng và các task lỗi/chưa hoàn thành theo yêu cầu ứng dụng; `shutdown()` ở đây chỉ phát tín hiệu không nhận task mới, còn `get()` trong vòng lặp đã chờ hai task của ví dụ.

### Khi nào vẫn nên dùng atomic hoặc lock?

Nếu nhiều thread thực sự cần cập nhật cùng bộ đếm toàn hệ thống, `AtomicLong` có thể phù hợp. Nếu cần duy trì bất biến “trừ tồn kho và ghi lịch sử phải nhất quán”, có thể phải dùng lock hoặc đồng bộ ở cấp dữ liệu/tài nguyên. Ownership giúp **giảm lượng state chia sẻ**; nó không tuyên bố các cơ chế đồng bộ là vô dụng.

## 5. Immutability: nhiều người đọc, không ai sửa

### Bất biến nông và bất biến sâu

`final` chỉ ngăn gán lại **tham chiếu của trường**, không khóa object mà tham chiếu đó trỏ tới.

```java
// Minh họa không an toàn nếu object bị chia sẻ và bị sửa đồng thời.
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("one"); // vẫn được: final không đóng băng ArrayList
```

Một record cũng **không tự động có tính bất biến sâu**:

```java
record Job(String id, java.util.List<String> tags) {}
```

Record có field cuối cùng, nhưng nếu caller đưa vào `ArrayList` rồi tiếp tục `add`, dữ liệu trong `Job` đổi theo; và `job.tags()` có thể để lộ danh sách mutable cho người dùng sửa.

Khắc phục bằng **defensive copy tại biên tạo object**:

```java
import java.util.List;

// Mảnh mã minh họa: đặt trong Job.java hoặc chương trình phù hợp.
record Job(String id, List<String> tags) {
    Job {
        tags = List.copyOf(tags);
    }
}
```

Trong compact constructor, giá trị tham số `tags` được thay bằng danh sách sao chép trước khi được gán vào trường record. `List.copyOf` tạo danh sách không cho sửa bằng API của nó. Tương tự, `Map.copyOf` và `Set.copyOf` có thể tạo snapshot không cho sửa tương ứng. Các phương thức copy này từ chối phần tử hoặc key/value `null` theo quy tắc API.

Tuy nhiên, **`List.copyOf` chỉ là bản sao nông**: nếu phần tử là `MutableAddress`, mỗi phần tử đó vẫn có thể bị sửa qua tham chiếu khác. Muốn bất biến sâu phải dùng phần tử bất biến hoặc sao chép các object mutable bên trong theo contract riêng.

### `Collections.unmodifiableList` khác snapshot

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);      // [A, B]
System.out.println(snapshot);  // [A]
```

Đây là mảnh mã minh họa bên trong một method, **không phải chương trình độc lập**. View `unmodifiableList` không cho sửa qua `view` nhưng vẫn phản ánh thay đổi từ `source`. `List.copyOf` cung cấp snapshot cấu trúc của danh sách ở thời điểm copy, với điều kiện phần tử được coi là an toàn để chia sẻ. Đừng công bố một “read-only view” lên collection vẫn được thread khác sửa rồi tưởng rằng nó đã immutable hoặc thread-safe.

### Bất biến cần được công bố an toàn

Object immutable có thiết kế đúng vẫn cần được đưa tới thread khác theo kênh công bố phù hợp, ví dụ:

- Truyền tham số khi nộp task cho executor.
- Đặt message vào `BlockingQueue`.
- Trao đổi thông qua `Future`, concurrent collection hoặc cơ chế đồng bộ có contract rõ.
- Xây dựng đầy đủ object trước khi đưa vào field `final` được công bố theo quy tắc Java Memory Model, tránh để lộ `this` khi constructor còn chạy.

Với các object bất biến được xây dựng đúng, các quy tắc `final` có bảo đảm bổ sung; tuy nhiên không nên dùng điều đó thay cho thiết kế đường truyền dữ liệu và vòng đời rõ ràng. Không xuất bản sớm object đang xây dựng hoặc để method khác đọc một cấu trúc mutable khi chưa có hàng rào bộ nhớ.

## 6. Chuyển quyền sở hữu qua message và BlockingQueue

Giả sử producer nhận yêu cầu và consumer duy nhất cập nhật tổng cục bộ. Một thiết kế tốt là producer chỉ tạo **message** rồi giao vào mailbox. Consumer đọc từng message, cập nhật **biến total chỉ mình nó nắm giữ**.

Lưu trong tệp **`MailboxDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class MailboxDemo {
    record Message(int amount, boolean stop) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> mailbox = new ArrayBlockingQueue<>(2);

        Thread consumer = new Thread(() -> {
            int total = 0; // Chỉ thread consumer thay đổi.
            try {
                while (true) {
                    Message message = mailbox.take();
                    if (message.stop()) {
                        break;
                    }
                    total += message.amount();
                }
                System.out.println("total=" + total);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        mailbox.put(new Message(4, false));
        mailbox.put(new Message(5, false));
        mailbox.put(new Message(0, true)); // Tín hiệu kết thúc sau dữ liệu
        consumer.join();
        System.out.println("finished");
    }
}
```

Chạy với JDK 17+:

```bash
javac MailboxDemo.java
java MailboxDemo
```

Stdout:

```text
total=9
finished
```

**Đường đi của ownership:**

1. Producer tạo `Message` chứa dữ liệu bất biến và gửi qua `mailbox.put`.
2. Consumer nhận qua `mailbox.take`. Queue đảm bảo an toàn khi trao đổi giữa các thread và có memory consistency effects theo contract `java.util.concurrent`: những hành động trước khi đặt object vào queue *happen-before* những hành động sau khi thread khác lấy object đó ra.
3. Consumer duy nhất sửa biến `total`. Producer không có tham chiếu đến biến local này, nên không thể vô tình tạo data race trên `total`.
4. Capacity `2` biểu thị mailbox **có giới hạn**; nếu đầy, `put` đợi cho đến khi còn chỗ. Đây là một dạng backpressure, cần quản lý trong ứng dụng thật.
5. Message `stop` được gửi cuối cùng; với ví dụ một producer, queue FIFO và một consumer, tất cả message trước nó được xử lý trước khi consumer thoát.
6. `join()` khiến main đợi consumer trước khi in `finished`; hai dòng stdout có thứ tự xác định.

`BlockingQueue` làm **việc truyền tham chiếu** an toàn, chứ **không tự biến object mutable thành immutable**. Nếu gửi `ArrayList` vào queue rồi producer tiếp tục thêm/xóa phần tử trong khi consumer đọc, data race vẫn có thể xảy ra. Vì thế chọn message bất biến, sao chép phòng vệ, hoặc quy ước chuyển quyền **producer không còn được truy cập để sửa sau khi gửi**.

Với nhiều producer, nhiều consumer hoặc hệ thống chạy lâu dài, giao thức đóng bằng một “poison message” cần thiết kế riêng: một stop message có thể chỉ làm một consumer dừng; producer có thể còn gửi sau stop; shutdown sai thứ tự làm mất dữ liệu hoặc chờ vô hạn. Cần ownership cho **vòng đời mailbox**: ai đóng, ai đợi, ai chịu trách nhiệm xử lý và báo lỗi.

## 7. Ownership transfer không giống chỉ truyền reference

Xét ví dụ sau:

```java
// Mảnh mã minh họa lỗi thiết kế.
List<String> payload = new ArrayList<>();
payload.add("first");
queue.put(payload);       // Consumer có thể lấy ngay.
payload.add("second");    // Producer tiếp tục sửa cùng ArrayList.
```

Nếu `queue` là `BlockingQueue<List<String>>`, lệnh `put`/`take` chỉ điều phối đưa/nhận phần tử và visibility cho các hành động trước khi đưa vào. Nó không cấm sửa sau khi giao. Việc `payload.add("second")` vẫn cùng lúc với consumer đọc là chia sẻ mutable state.

Ba phương án hợp lệ tùy yêu cầu:

1. **Copy-and-share:** producer gọi `queue.put(List.copyOf(payload))`, consumer nhận snapshot bất biến về cấu trúc; an toàn khi phần tử là immutable.
2. **Exclusive handoff:** producer đưa một object mutable rồi cam kết không còn sửa hoặc đọc nó theo cách có race; consumer được chuyển quyền sửa. Contract phải được giữ ở mọi caller.
3. **Shared mutable state có đồng bộ:** khi cả hai thật sự cần sửa cùng object, sử dụng cấu trúc thread-safe hoặc lock thích hợp bảo vệ toàn bộ bất biến.

Trong Java, độc quyền là **quy ước**, không phải trình biên dịch xác minh. Cần review các đường alias: biến khác, collection khác, callback, closure hay static field vẫn có thể giữ cùng tham chiếu. Nếu không kiểm soát được mọi alias, snapshot immutable thường dễ kiểm chứng hơn.

## 8. Thread confinement và task confinement

**Thread confinement**: trạng thái chỉ được một thread truy cập. Có thể dùng biến local trong `Runnable.run()`, hoặc một instance worker sở hữu một cấu trúc dữ liệu và xử lý các message tuần tự.

**Task confinement**: trạng thái gắn với một phép xử lý logic, dù executor có thể chọn thread khác nhau cho những task khác nhau. Đây thường là cách mô tả hữu ích hơn cho nhiều chương trình Java hiện đại.

```java
// Mảnh mã minh họa.
Callable<Integer> task = () -> {
    int localSum = 0;
    for (int value : inputSnapshot) {
        localSum += value;
    }
    return localSum;
};
```

Khi `inputSnapshot` không thay đổi và `localSum` không thoát khỏi task, nhiều invocation có thể chạy đồng thời mà không chia sẻ `localSum`. Chỉ có việc nộp task và thu kết quả cần quản lý.

Lưu ý biến local **chứa tham chiếu** không đồng nghĩa object được trỏ tới là riêng tư. Ví dụ `List<String> local = sharedList;` vẫn trỏ vào danh sách chia sẻ. Một lambda có thể capture một tham chiếu mutable từ vùng ngoài; `effectively final` chỉ khiến biến không thể gán lại, không ngăn sửa object.

`ThreadLocal<T>` là công cụ lưu giá trị riêng cho **mỗi thread**, nhưng nó không thay thế ownership ở cấp tác vụ:

- Trong pool thread tái sử dụng, nếu quên `remove()`, giá trị của task cũ có thể còn ảnh hưởng task sau, đồng thời giữ tài nguyên lâu hơn cần thiết.
- Với virtual thread tạo theo mỗi tác vụ, dùng nhiều `ThreadLocal` hoặc giá trị lớn cũng tiêu tốn bộ nhớ; không nên biến mọi tham số thành context ẩn.
- Task có thể chuyển giữa các thread qua các stage async khác nhau; không mặc định một `ThreadLocal` sẽ theo mọi lời gọi sau khi rời thread ban đầu.
- Truyền tham số tường minh, immutable request context hoặc message thường khiến ownership rõ hơn; `ThreadLocal` có chỗ dùng khi contract của thư viện yêu cầu.

## 9. Ownership và Java Memory Model: không bỏ qua happens-before

Tách trạng thái giúp giảm race, nhưng những lần trao đổi giữa thread vẫn cần có cơ chế đúng.

| Sự kiện | Bảo đảm có ích |
| --- | --- |
| Tạo dữ liệu rồi gọi `thread.start()` | Hành động trước `start` *happen-before* hành động trong thread mới |
| Một thread đã kết thúc, thread khác `join()` thành công | Hành động của thread kết thúc *happen-before* thread chờ đi tiếp sau `join` |
| Nộp `Runnable` hoặc `Callable` cho `ExecutorService` | Hành động trước submit *happen-before* thực thi task |
| Task hoàn tất và caller lấy kết quả bằng `Future.get()` | Hành động trong task *happen-before* hành động sau khi lấy kết quả |
| `BlockingQueue.put` rồi consumer `take` đúng phần tử | Hành động trước đưa phần tử *happen-before* hành động sau khi lấy nó |
| Ghi và đọc cùng một biến `volatile`, hoặc lock/unlock tương ứng | Có ordering/visibility theo quy tắc JMM tương ứng; không tự đảm bảo mọi thao tác phức hợp là atomic |

`happens-before` nói về trật tự và visibility, **không chứng minh một object không còn bị sửa**. Nếu đưa object mutable vào queue và sau đó producer tiếp tục sửa, bảo đảm put/take không loại bỏ tương tác sai sau mốc handoff.

Mọi trạng thái dùng chung phải có một câu trả lời rõ: chỉ đọc immutable? Có một owner ghi? Có protocol handoff? Hay có một cơ chế đồng bộ bảo vệ truy cập? Không thể thay câu trả lời bằng `Thread.sleep(100)`, `yield()`, hoặc đoán rằng thread này sẽ chạy trước thread kia.

## 10. Bất biến nghiệp vụ và cách chia ranh giới

Nhiều race không nằm ở một lệnh `++` mà ở **bất biến nhiều trường**.

Ví dụ một kho hàng có `available` và `reserved`, yêu cầu tổng số phải không vượt quá `capacity`. Hai thread cùng đọc “còn chỗ” rồi cùng đặt chỗ có thể phá invariant ngay cả khi mỗi trường là một atomic riêng. Nếu thật sự có một kho chung phải cập nhật tức thì, bạn cần một cơ chế đồng bộ **ở mức toàn bộ thao tác kiểm tra và cập nhật**, hoặc dồn tất cả lệnh đặt chỗ tới một owner duy nhất.

Mô hình **single writer**:

```text
Nhiều producer
   |     |
   v     v
  immutable commands
         |
         v
  bounded mailbox
         |
         v
  một owner xử lý tuần tự
         |
         +--> state mutable chỉ owner sửa
         |
         +--> immutable result / Future / response queue
```

Ưu điểm: invariant được kiểm tra trong cùng một nơi, giảm lock giữa nhiều caller. Đổi lại, owner có thể thành nút thắt cổ chai; cần quản lý capacity, fairness, timeout, lỗi và shutdown. Nếu throughput cần tăng, cân nhắc chia state thành các **partition độc lập** (ví dụ mỗi key thuộc một owner) với ranh giới rõ ràng. Phân vùng sai hoặc task nhiều key có thể lại đòi hỏi phối hợp/transaction giữa các owner.

Không nên gọi mọi “có một thread xử lý” là không có concurrency: nhiều producer vẫn có thể chạy song song và mailbox cần đồng bộ. Lợi ích nằm ở chỗ **state mutable cốt lõi có một chủ thể ghi**, khiến invariant dễ chứng minh hơn.

## 11. Quản lý lỗi, timeout và vòng đời cùng ownership

Chỉ thiết kế dữ liệu chưa đủ; một task có thể thất bại, bị hủy hoặc kéo dài quá thời hạn.

- **Ai sở hữu Future?** Caller nộp task nên giữ `Future` hoặc truyền quyền quản lý cho thành phần khác có trách nhiệm chờ, hủy và báo lỗi.
- **Ai dừng executor?** Thành phần tạo executor nên có hợp đồng shutdown/close rõ; không để mỗi tác vụ tùy tiện gọi shutdown lên executor chung.
- **Ai đóng queue?** Chọn một coordinator hoặc protocol chốt số producer, bảo đảm mọi message hợp lệ đã xử lý hoặc được báo thất bại.
- **Ai đóng tài nguyên?** Socket/stream/DB connection không thể chuyển giao chỉ bằng một câu nói. Cần mô tả ai đóng, thứ tự đóng, xử lý exception và đường cancel.
- **Nếu timeout?** `Future.get(timeout, unit)` báo timeout chờ; nó không tự đảm bảo task đã dừng. Chủ thể quản lý có thể gọi `cancel(true)` và cần task hợp tác xử lý interrupt.
- **Nếu task ném exception?** `Future.get()` có thể ném `ExecutionException`. Không đánh dấu thành công vì producer đã enqueue hoặc `submit()` trả về.
- **Nếu queue đầy?** `put()` chặn tới khi có chỗ; `offer(timeout)` cho phép chính sách từ chối/giới hạn thay vì block vô hạn.

Trong Java 17, `ExecutorService` được quản lý bằng `shutdown()` và `awaitTermination(...)` khi cần chờ đầy đủ, cùng chính sách cancel/`shutdownNow()` tùy lỗi. Không đặt cơ chế dừng bằng cách cho tất cả worker tự chờ nhau, dễ gây deadlock. Ở JDK mới có thêm tiện ích quản lý lifecycle, nhưng nguyên tắc ownership vẫn là xác định rõ **scope** nào tạo task và scope nào thu kết quả.

**Quyền sở hữu object không bằng quyền sở hữu kết quả.** Có thể task đã hoàn thành và không còn sửa object, nhưng caller vẫn chưa gọi `Future.get()` để nhận exception. Ngược lại, có thể caller không có quyền sửa input nữa nhưng vẫn có nghĩa vụ nhận kết quả.

## 12. Checklist thiết kế trước khi thêm lock

Hãy tự trả lời theo thứ tự:

1. **Liệt kê state:** object nào có thể thay đổi? Field nào trỏ tới collection, array, buffer hoặc object mutable bên trong?
2. **Xác định owner của từng phần:** caller, một task, một worker/partition hay thành phần giữ state chung?
3. **Tìm alias:** có nơi nào khác đang giữ tham chiếu tới cùng object để sửa? Lambda capture, static field, cache, listener, callback và getter có lộ dữ liệu không?
4. **Tách input và output:** có thể đưa snapshot immutable cho task và trả immutable result không? Có thể cộng gộp ở caller thay vì cộng chung?
5. **Xác định điểm handoff:** qua queue/Future/start/join hay publication khác? Producer có ngừng mutate sau điểm đó không?
6. **Giữ invariant:** nếu nhiều field phải nhất quán, đã có một owner ghi hoặc một critical section bao trọn chưa?
7. **Ràng buộc tài nguyên:** queue có giới hạn? Có quá nhiều task concurrent? Timeout, backpressure, cancel và shutdown do ai phụ trách?
8. **Kiểm chứng:** có thể dùng test nhiều lần để phát hiện race, nhưng test pass không chứng minh không còn race. Hãy suy luận dựa trên ownership, contracts của API và Java Memory Model.

### Những anti-pattern phổ biến

| Anti-pattern | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Đưa `ArrayList` chung cho mọi task rồi để mỗi task `add` | Race, cập nhật mất hoặc cấu trúc hỏng | Mỗi task trả kết quả; owner duy nhất ghép danh sách sau `get` |
| Gắn `final` vào field `Map` và coi Map bất biến | Vẫn có thể sửa phần tử/entry | Defensive copy và phần tử immutable; contract rõ |
| Dùng `Collections.unmodifiableList` trên danh sách đang mutate | View vẫn phản ánh thay đổi ngoài | Dùng snapshot `List.copyOf` nếu phần tử an toàn |
| Truyền object mutable qua queue rồi tiếp tục sửa | Race sau thời điểm giao | Copy trước khi gửi hoặc handoff độc quyền |
| Mỗi worker cập nhật nhiều atomic để giữ một invariant chung | Invariant có thể sai giữa các bước | Single writer hoặc đồng bộ bao trọn thao tác |
| Dùng `ThreadLocal` cho mọi dữ liệu tác vụ | Context ẩn, giữ tài nguyên, khó chuyển qua async stage | Tham số rõ ràng và task-local state |
| Có `volatile` trên tham chiếu rồi đọc/sửa fields bên trong tùy ý | Không biến object graph thành thread-safe | Chia ownership hoặc đồng bộ đúng state |
| Tạo task rồi bỏ `Future`, không bao giờ kiểm tra kết quả | Lỗi bị bỏ quên, vòng đời mơ hồ | Caller/scope sở hữu Future và thu lỗi |
| Cố giới hạn số task bằng cách tạo thread pool thật nhỏ cho mọi việc chờ I/O | Nghẽn throughput, latency cao | Giới hạn tài nguyên đích và dùng executor phù hợp workload |
| Chuyển state vào singleton/static chỉ để nhiều task tiện truy cập | Tăng vùng chia sẻ và trách nhiệm đồng bộ | Đưa dữ liệu làm tham số và trả kết quả |
| Thêm lock cục bộ trong một class nhưng expose danh sách mutable qua getter | Caller vẫn sửa ngoài lock | Cung cấp API thao tác, snapshot hoặc encapsulation |

## 13. Bài tập vận dụng và câu hỏi tự kiểm tra

**Bài tập 1 – Tổng kết kết quả:** Có 100 task đọc 100 file và đếm số dòng. Thiết kế nào ít shared mutable state hơn: (A) task tăng một `int` chung, (B) mỗi task trả `long` qua `Future` rồi caller cộng? **B** là lựa chọn dễ kiểm chứng. Task vẫn có thể đọc dữ liệu đầu vào chung bất biến, nhưng accumulator không bị nhiều worker sửa.

**Bài tập 2 – Alias qua record:** `record Request(List<String> names) {}` có tự bảo vệ danh sách khỏi bị sửa không? **Không.** Field là final nhưng danh sách có thể mutable. Dùng defensive copy ở constructor; nếu phần tử cũng mutable thì cần copy sâu hoặc phần tử bất biến.

**Bài tập 3 – Sau queue.put:** Producer đưa `ArrayList` vào `BlockingQueue` rồi sửa list; consumer đồng thời duyệt. Có bảo đảm không race vì queue thread-safe không? **Không.** Queue bảo vệ việc giao phần tử và visibility tại thời điểm handoff, không bảo vệ những chỉnh sửa sau đó.

**Bài tập 4 – Invariant nhiều trường:** Hai `AtomicInteger` cho `available` và `reserved` có đủ giữ invariant liên quan đến cả hai không? **Không nhất thiết**; cập nhật riêng lẻ vẫn có thể xen kẽ. Cần ownership một writer, transaction/lock phù hợp hoặc thiết kế invariant khác.

**Bài tập 5 – ThreadLocal:** Task A và B chạy nối tiếp trên cùng platform thread từ pool. Nếu A đặt context vào `ThreadLocal` rồi không `remove()`, B có thể đọc context cũ không? **Có**, tùy đường code. Vì vậy cần cleanup trong `finally` hoặc tránh context ẩn.

**Bài tập 6 – Future:** `submit` trả về `Future` có nghĩa task đã thành công? **Không.** Task có thể chưa chạy, đang chạy hoặc hoàn tất lỗi. Caller phải quản lý và nhận kết quả/exception đúng contract.

**Bài tập 7 – Chỉ một chủ thể sửa:** Nếu một consumer duy nhất cập nhật `total` là biến local, có cần `AtomicInteger` cho biến ấy không? **Không** trong mô hình của ví dụ. Queue và `join` bảo đảm trao đổi và điểm hoàn tất; không có thread khác sửa `total`.

## 14. Nguyên tắc thực hành cần nhớ

Thiết kế concurrency bằng cách **định nghĩa ownership trước khi thêm synchronization**:

- Dữ liệu chỉ phục vụ một phép xử lý thì giữ **task-local**; kết quả được trả về khi task xong.
- Dữ liệu cần chia sẻ để đọc thì dùng **immutable snapshot** và kiểm soát toàn bộ object graph.
- Dữ liệu phải được sửa theo thời gian thì cố gắng chọn **một owner ghi**; các caller khác gửi lệnh hoặc thông điệp qua kênh thread-safe.
- State không thể tránh chia sẻ mutable cần có **đồng bộ đúng mức invariant**, không chỉ bảo vệ vài dòng rời rạc.
- Mọi handoff phải có contract rõ về **khi nào mất quyền sửa**, visibility, giới hạn dung lượng, xử lý lỗi và vòng đời.

Cách tư duy này khiến code dễ kiểm thử và bảo trì hơn: thay vì phải chứng minh mỗi phép đọc/ghi trên hàng loạt object chia sẻ đều đúng, ta giảm số nơi có quyền ghi, giảm alias và chỉ cần chứng minh các **ranh giới giao tiếp** là an toàn.
