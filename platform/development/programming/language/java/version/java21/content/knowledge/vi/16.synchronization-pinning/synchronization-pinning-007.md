# Giữ synchronized cho vùng tới hạn phù hợp thay vì thay đồng loạt

`synchronized` vẫn là cơ chế đồng bộ hợp lệ và hữu ích trong Java 21. Nó bảo vệ vùng tới hạn bằng monitor của một object, bảo đảm chỉ một thread tại một thời điểm thực thi phần mã được bảo vệ bởi cùng monitor, đồng thời tạo quan hệ hiển thị bộ nhớ giữa thao tác mở khóa và lần khóa tiếp theo trên cùng monitor.

Khi đưa virtual thread vào ứng dụng, cần chú ý đến một giới hạn theo phiên bản: trên JDK 21–23, virtual thread có thể bị pin vào carrier platform thread khi bị block trong lúc đang thực thi vùng `synchronized`. Điều này có thể làm giảm khả năng mở rộng nếu việc block xảy ra thường xuyên và kéo dài. Tuy nhiên, từ JDK 24, JEP 491 đã thay đổi cách runtime xử lý monitor để virtual thread có thể nhường carrier khi block trong `synchronized`; vì vậy cảnh báo pinning do monitor không còn là lý do để thay hàng loạt `synchronized` trong các JDK mới.

Cách tiếp cận phù hợp là giữ `synchronized` cho vùng tới hạn ngắn, bảo vệ đúng trạng thái dùng chung và chỉ cân nhắc `ReentrantLock` khi có yêu cầu đồng bộ cụ thể hoặc khi đo đạc trên runtime mục tiêu cho thấy một vấn đề thực sự.

## 1. synchronized bảo vệ điều gì?

Từ khóa `synchronized` sử dụng monitor gắn với một object. Một thread phải sở hữu monitor trước khi thực thi phần thân của synchronized block hoặc synchronized method. Nếu thread khác đang giữ monitor đó, thread hiện tại phải chờ đến khi monitor được nhả.

Ví dụ:

```java
class Counter {
    private int value;

    public synchronized int incrementAndGet() {
        return ++value;
    }

    public synchronized int currentValue() {
        return value;
    }
}
```

Hai method trên đồng bộ bằng monitor của cùng instance `Counter`. Khi một thread đang chạy `incrementAndGet()`, thread khác không thể đồng thời chạy một method `synchronized` khác trên chính instance đó.

Có thể dùng một object khóa riêng để thể hiện rõ phạm vi đồng bộ:

```java
class Inventory {
    private final Object lock = new Object();
    private int available;

    Inventory(int initialStock) {
        available = initialStock;
    }

    boolean reserve(int quantity) {
        synchronized (lock) {
            if (quantity <= 0 || available < quantity) {
                return false;
            }

            available -= quantity;
            return true;
        }
    }

    int available() {
        synchronized (lock) {
            return available;
        }
    }
}
```

Trong ví dụ, thao tác kiểm tra số lượng và trừ kho nằm trong cùng một vùng tới hạn. Nếu tách hai thao tác này ra khỏi monitor, hai thread có thể cùng đọc một giá trị tồn kho rồi cùng quyết định rằng đủ hàng, dẫn đến đặt vượt số lượng thực tế.

## 2. Các bảo đảm của synchronized vẫn có giá trị

`synchronized` không chỉ ngăn hai thread chạy đồng thời trong cùng vùng tới hạn. Nó còn cung cấp bảo đảm về bộ nhớ theo Java Memory Model.

Khi một thread nhả monitor, các thao tác ghi trước thời điểm nhả có quan hệ *happens-before* với lần thread khác lấy cùng monitor sau đó. Nhờ vậy, thread lấy khóa có thể quan sát các thay đổi được thực hiện trước khi khóa được nhả.

Ngoài ra:

- Monitor có tính reentrant: thread đang giữ monitor có thể vào lại một synchronized block/method sử dụng cùng monitor.
- Monitor được tự động nhả khi rời khỏi synchronized block, kể cả khi thoát do exception.
- Một synchronized instance method khóa monitor của object hiện tại (`this`); synchronized static method khóa monitor của đối tượng `Class` tương ứng.
- Các thread chỉ phối hợp với nhau nếu chúng khóa cùng một monitor.

Những đặc tính này khiến `synchronized` phù hợp với các thao tác cập nhật trạng thái trong bộ nhớ có phạm vi ngắn và có invariant rõ ràng.

Không nên thay `synchronized` bằng một biến `volatile` chỉ để bỏ monitor. `volatile` cung cấp bảo đảm visibility và ordering cho lần đọc/ghi biến, nhưng không biến một chuỗi thao tác như “kiểm tra rồi cập nhật” thành thao tác nguyên tử. Với invariant gồm nhiều field hoặc nhiều bước, vẫn cần khóa hoặc một cấu trúc đồng thời phù hợp.

## 3. Pinning trong Java 21–23

Virtual thread thường có thể unmount khỏi carrier platform thread khi thực hiện thao tác blocking được runtime hỗ trợ. Carrier sau đó có thể chạy virtual thread khác. Cơ chế này cho phép một số lượng lớn virtual thread chia sẻ một nhóm nhỏ platform thread.

Trong JDK 21–23, virtual thread bị pin khi đang thực thi code trong synchronized method hoặc synchronized block. Khi một thao tác blocking xảy ra trong lúc pinning, virtual thread không thể nhường carrier như trường hợp thông thường. Carrier bị giữ lại cho đến khi virtual thread tiếp tục và thoát khỏi tình huống pinning.

Ví dụ cần chú ý khi chạy trên JDK 21–23:

```java
class RemoteConfig {
    private final Object lock = new Object();

    String load() throws Exception {
        synchronized (lock) {
            // Có thể chờ network trong khi đang giữ monitor.
            return callRemoteService();
        }
    }

    private String callRemoteService() throws Exception {
        // Đại diện cho thao tác I/O có thể block.
        Thread.sleep(500);
        return "configuration";
    }
}
```

Nếu nhiều virtual thread thường xuyên đi vào method này và phải chờ trong vùng `synchronized`, carrier platform thread có thể bị giữ lại trong thời gian chờ. Khi hiện tượng xảy ra thường xuyên, số carrier khả dụng cho các virtual thread khác giảm và throughput có thể bị ảnh hưởng.

Cần phân biệt hai việc:

- **Giữ monitor trong một vùng mã ngắn, chỉ thao tác dữ liệu trong bộ nhớ:** thường không tạo ra vấn đề pinning đáng kể vì không có thao tác blocking kéo dài cần unmount.
- **Thực hiện thao tác blocking khi đang ở trong vùng synchronized:** trên JDK 21–23 có thể giữ carrier trong suốt thời gian block và ảnh hưởng khả năng mở rộng.

Do đó, không phải cứ nhìn thấy từ khóa `synchronized` trong ứng dụng Java 21 là phải thay nó. Cần xem vùng tới hạn làm gì, có blocking hay không, tần suất chạy và thời gian giữ monitor.

## 4. Thay đổi từ JDK 24: synchronized không còn gây monitor-related pinning

JEP 491 — *Synchronize Virtual Threads without Pinning* được tích hợp trong JDK 24. Thay đổi này cho phép virtual thread đang block trong synchronized method hoặc synchronized block nhường carrier platform thread để runtime có thể chạy virtual thread khác.

Vì vậy, khác biệt theo phiên bản có thể tóm tắt như sau:

| Hành vi | JDK 21–23 | JDK 24 trở lên |
|---|---|---|
| Virtual thread block trong synchronized method/block | Có thể pin carrier | Có thể unmount và nhường carrier |
| Thay synchronized chỉ để tránh monitor pinning | Có thể cần cân nhắc nếu pinning thường xuyên, kéo dài | Không còn cần vì lý do monitor pinning |
| synchronized bảo vệ mutual exclusion và visibility | Có | Có |
| Tranh chấp monitor và thời gian giữ khóa dài | Vẫn có thể làm các thread khác phải chờ | Vẫn có thể làm các thread khác phải chờ |
| Pinning do native method hoặc foreign function | Có thể xảy ra | Vẫn có thể xảy ra |

JEP 491 loại bỏ gần như toàn bộ trường hợp pinning do monitor, không có nghĩa mọi tình huống pinning đều biến mất. Native method và foreign function vẫn có thể giữ virtual thread gắn với carrier. Ngoài ra, việc nhường carrier không làm cho monitor được nhả: thread khác vẫn phải chờ nếu cần cùng monitor đang được giữ.

Đây là điểm quan trọng khi bảo trì ứng dụng: nếu ứng dụng được triển khai trên JDK 24 trở lên, không nên áp dụng máy móc hướng dẫn cũ “thay synchronized bằng ReentrantLock để tránh pinning”. Hãy xác định phiên bản runtime đang chạy và lý do thực sự cần thay đổi.

## 5. Giữ synchronized cho vùng tới hạn ngắn

Với dữ liệu chia sẻ trong bộ nhớ, synchronized thường là lựa chọn đơn giản và rõ ràng. Vùng tới hạn nên bao gồm các thao tác cần được thực hiện như một đơn vị nhất quán, ví dụ:

- Kiểm tra điều kiện và cập nhật số dư.
- Thêm hoặc xóa phần tử trong một cấu trúc dữ liệu không thread-safe.
- Cập nhật nhiều field cần duy trì cùng một invariant.
- Lấy snapshot nhất quán của trạng thái nội bộ.

Ví dụ:

```java
class Account {
    private final Object lock = new Object();
    private long balance;

    boolean withdraw(long amount) {
        synchronized (lock) {
            if (amount <= 0 || balance < amount) {
                return false;
            }

            balance -= amount;
            return true;
        }
    }

    long balance() {
        synchronized (lock) {
            return balance;
        }
    }
}
```

Cả kiểm tra và trừ tiền đều nằm trong cùng vùng tới hạn. Đây là phần công việc ngắn, xử lý trạng thái trong bộ nhớ và không cần chờ dịch vụ bên ngoài. Việc dùng `synchronized` giúp thể hiện invariant trực tiếp.

Không nên kéo các thao tác không liên quan vào vùng tới hạn. Ví dụ, ghi log đồng bộ ra file, gọi HTTP, truy vấn database hoặc chờ người dùng phản hồi thường không cần nằm bên trong monitor bảo vệ trạng thái nội bộ.

## 6. Tách I/O khỏi vùng synchronized khi có thể

Một cách thiết kế tốt là chỉ khóa để lấy snapshot hoặc cập nhật trạng thái, còn thao tác I/O được thực hiện bên ngoài vùng tới hạn.

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

class ConfigService {
    private final Object lock = new Object();
    private final HttpClient client = HttpClient.newHttpClient();

    private HttpRequest currentRequest;
    private long version;
    private String lastResponse;

    void updateRequest(HttpRequest request) {
        synchronized (lock) {
            currentRequest = request;
            version++;
        }
    }

    String refresh() throws Exception {
        HttpRequest requestSnapshot;
        long versionSnapshot;

        synchronized (lock) {
            requestSnapshot = currentRequest;
            versionSnapshot = version;
        }

        if (requestSnapshot == null) {
            return null;
        }

        HttpResponse<String> response = client.send(
                requestSnapshot,
                HttpResponse.BodyHandlers.ofString()
        );

        synchronized (lock) {
            if (versionSnapshot == version) {
                lastResponse = response.body();
            }
            return lastResponse;
        }
    }
}
```

Phần đọc request và version được bảo vệ bằng monitor. HTTP request chạy ngoài monitor nên không giữ khóa trong lúc chờ network. Khi có response, code lấy khóa lại để cập nhật trạng thái; kiểm tra version giúp tránh ghi đè kết quả của một request cũ nếu cấu hình đã thay đổi trong lúc I/O đang diễn ra.

Mẫu này có thể thay đổi ngữ nghĩa nếu nghiệp vụ thực sự yêu cầu giữ khóa xuyên suốt thao tác I/O. Khi tách vùng tới hạn, cần xác định lại invariant, thứ tự cập nhật và cách xử lý kết quả cũ; không nên chỉ di chuyển code ra ngoài khóa mà không kiểm tra tính đúng đắn đồng thời.

## 7. Khi nào nên cân nhắc ReentrantLock?

`ReentrantLock` thuộc `java.util.concurrent.locks` và cũng cung cấp khóa loại reentrant. Nó có thêm khả năng điều khiển mà synchronized không cung cấp trực tiếp:

- `lockInterruptibly()`: chờ lấy khóa nhưng có thể phản hồi interruption.
- `tryLock()`: thử lấy khóa mà không chờ vô hạn.
- `tryLock(timeout, unit)`: chờ trong thời gian giới hạn.
- Có thể chọn chế độ fairness khi khởi tạo.
- Có thể tạo nhiều `Condition` cho các nhóm điều kiện chờ khác nhau.

Ví dụ:

```java
import java.util.concurrent.locks.ReentrantLock;

class SharedState {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    int updateAndRead() {
        lock.lock();
        try {
            value++;
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

Khối `finally` rất quan trọng: nếu code trong vùng khóa ném exception, khóa vẫn phải được nhả. Với synchronized, việc nhả monitor được thực hiện tự động khi thoát block; với ReentrantLock, lập trình viên phải gọi `unlock()` đúng số lần đã khóa.

Nên chọn ReentrantLock khi ứng dụng thực sự cần timed/interruptible acquisition, fairness, nhiều Condition hoặc một yêu cầu đồng bộ mà intrinsic monitor không đáp ứng thuận tiện. Trong ứng dụng chạy trên JDK 21–23, nó cũng có thể là lựa chọn cho một vùng blocking dài và thường xuyên đã được xác định là gây pinning, nếu không thể thiết kế lại để đưa I/O ra ngoài vùng tới hạn.

Không nên thay tất cả synchronized bằng ReentrantLock chỉ vì API này có nhiều tính năng hơn. Mỗi tính năng bổ sung cũng làm tăng trách nhiệm quản lý khóa và nguy cơ quên unlock hoặc tạo thứ tự khóa không nhất quán.

## 8. Không nhầm pinning với lock contention

Pinning và lock contention là hai vấn đề khác nhau:

- **Pinning:** virtual thread không thể unmount khỏi carrier khi đang ở tình huống pinning; carrier platform thread bị giữ lại.
- **Lock contention:** nhiều thread muốn lấy cùng một khóa, nhưng chỉ một thread được sở hữu monitor/lock tại một thời điểm; các thread còn lại phải chờ.

JDK 24 giải quyết monitor-related pinning cho virtual thread, nhưng không loại bỏ lock contention. Nếu một thread giữ monitor trong vài giây, những thread khác cần monitor đó vẫn phải chờ vài giây. Dù carrier có thể được giải phóng trong JDK mới, thời gian chờ khóa và throughput của phần dữ liệu được bảo vệ vẫn có thể bị ảnh hưởng.

Do đó, các nguyên tắc sau vẫn có giá trị trên mọi phiên bản:

1. Giữ vùng tới hạn ngắn và có mục đích rõ ràng.
2. Không gọi code bên ngoài không kiểm soát khi đang giữ khóa nếu có thể tránh.
3. Tránh khóa nhiều object theo thứ tự không nhất quán.
4. Không giữ khóa trong lúc chờ người dùng, network hoặc một dịch vụ không kiểm soát được độ trễ.
5. Đo contention và latency trước khi thay đổi cơ chế đồng bộ.

## 9. Chẩn đoán pinning theo phiên bản JDK

Trên JDK 21, JDK Flight Recorder (JFR) cung cấp event `jdk.VirtualThreadPinned`. Event này được bật mặc định với ngưỡng thời gian 20 ms trong cấu hình mặc định. Có thể ghi JFR và xem event bằng lệnh:

```bash
jfr print --events jdk.VirtualThreadPinned recording.jfr
```

Trong JDK 21–23, tùy chọn hệ thống `-Djdk.tracePinnedThreads=full` hoặc `-Djdk.tracePinnedThreads=short` có thể in stack trace khi virtual thread block trong trạng thái pinning. Đây là công cụ chẩn đoán theo phiên bản; tùy chọn này không còn được hỗ trợ từ JDK 24.

Trên JDK 24 trở lên, JFR vẫn hữu ích để quan sát các trường hợp pinning còn lại, chẳng hạn khi virtual thread chạy native method hoặc foreign function. Khi đọc kết quả, hãy xem stack trace, thời lượng, tần suất và carrier liên quan; một event riêng lẻ không tự động chứng minh cần thay đổi cơ chế khóa.

Cần kiểm tra runtime thực tế đang chạy ứng dụng. Mã được biên dịch bằng JDK 21 có thể được triển khai trên JDK mới hơn, và hành vi pinning phụ thuộc JDK runtime, không chỉ phụ thuộc source level hoặc bytecode target.

## 10. Quy trình quyết định có nên thay synchronized hay không

| Tình huống | Hướng xử lý |
|---|---|
| Vùng tới hạn ngắn, chỉ đọc/ghi trạng thái trong bộ nhớ | Giữ `synchronized` nếu nó diễn đạt đúng invariant |
| Có I/O hoặc thao tác blocking bên trong synchronized và ứng dụng chạy JDK 21–23 | Ưu tiên tách I/O khỏi khóa; nếu không thể, đo pinning và cân nhắc ReentrantLock cho đúng vùng đó |
| Ứng dụng chạy JDK 24 trở lên và lý do duy nhất để thay là monitor pinning | Giữ synchronized; JEP 491 đã xử lý trường hợp này |
| Cần timed lock, lock có thể interrupt hoặc nhiều Condition | Cân nhắc ReentrantLock |
| Có contention cao dù không còn pinning | Rút ngắn vùng tới hạn, giảm chia sẻ trạng thái hoặc thiết kế lại cấu trúc dữ liệu |
| Pinning đến từ native/foreign function | Điều tra đoạn native/foreign và cách gọi; đổi synchronized không tự giải quyết pinning đó |

Một quy trình thực tế:

1. Xác định JDK runtime của môi trường production.
2. Xác định monitor bảo vệ dữ liệu nào và invariant nào.
3. Kiểm tra vùng tới hạn có I/O, native call hoặc thao tác blocking không.
4. Với JDK 21–23, dùng JFR hoặc công cụ chẩn đoán phù hợp để xác định pinning có thường xuyên và kéo dài không.
5. Nếu có thể, chuyển thao tác blocking ra ngoài monitor và chỉ khóa lúc đọc/ghi trạng thái.
6. Nếu không thể tách, đánh giá ReentrantLock trong đúng vùng cần thiết và giữ `unlock()` trong `finally`.
7. Với JDK 24 trở lên, không refactor chỉ để né monitor pinning; tiếp tục tối ưu contention và các nguyên nhân pinning còn lại.

## 11. Các lỗi thường gặp

| Cách hiểu hoặc cách làm sai | Vì sao không phù hợp | Cách xử lý |
|---|---|---|
| Thay mọi synchronized bằng ReentrantLock | Tăng độ phức tạp quản lý khóa mà không có lợi ích cần thiết | Giữ synchronized cho vùng tới hạn phù hợp |
| Cho rằng synchronized luôn làm virtual thread pin trên mọi JDK | Monitor-related pinning đã được xử lý từ JDK 24 | Xác định runtime và phân biệt JDK 21–23 với JDK 24+ |
| Giữ monitor trong lúc gọi network hoặc database | Làm vùng khóa kéo dài; JDK 21–23 còn có thể pin carrier | Tách I/O khỏi vùng tới hạn nếu invariant cho phép |
| Nghĩ ReentrantLock loại bỏ mọi pinning | Native/foreign call vẫn có thể pin virtual thread | Xem JFR và stack trace để xác định nguồn pinning |
| Thay khóa bằng volatile cho thao tác nhiều bước | volatile không bảo vệ chuỗi kiểm tra-cập nhật như một đơn vị nguyên tử | Dùng monitor, lock hoặc atomic operation thích hợp |
| Quên unlock khi dùng ReentrantLock | Thread khác có thể chờ vô hạn | Luôn đặt unlock trong finally |
| Nghĩ JEP 491 loại bỏ lock contention | Các thread vẫn phải chờ monitor đang được thread khác giữ | Rút ngắn thời gian giữ khóa và giảm tranh chấp |

## 12. Nguyên tắc áp dụng cho Java 21 và runtime hiện nay

Khi phát triển hoặc bảo trì ứng dụng Java 21, hãy giữ `synchronized` ở những nơi nó bảo vệ trạng thái dùng chung bằng vùng tới hạn ngắn, dễ hiểu và đúng với Java Memory Model. Trên runtime Java 21–23, tránh các thao tác blocking kéo dài bên trong synchronized nếu có thể; chỉ chuyển sang ReentrantLock khi có bằng chứng hoặc yêu cầu đồng bộ phù hợp.

Đồng thời, khi ứng dụng được chạy trên JDK 24 trở lên, hãy cập nhật nhận thức về pinning: JEP 491 đã loại bỏ monitor-related pinning, vì vậy việc thay synchronized hàng loạt theo hướng dẫn dành cho Java 21–23 là không cần thiết. Vẫn cần tối ưu vùng tới hạn để giảm contention và vẫn cần điều tra native/foreign pinning nếu JFR cho thấy vấn đề.

Điểm quyết định không phải là chọn một cơ chế khóa mới hơn cho toàn bộ codebase. Hãy chọn cơ chế đáp ứng đúng invariant, khả năng hủy/chờ, yêu cầu công bằng và hành vi runtime của ứng dụng; giữ synchronized khi nó vẫn là lựa chọn đơn giản và chính xác.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Virtual Threads: Scheduling and Pinned Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle Java SE 21 API — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [Oracle JDK 24 — Significant Changes: JEP 491](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html)
