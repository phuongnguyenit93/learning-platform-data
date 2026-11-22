# Không giữ khóa khi chờ nhập/xuất hoặc chờ tác vụ phụ thuộc

## 1. Vấn đề trong bean có trạng thái

Một bean Spring có phạm vi mặc định là `singleton`: trong cùng một `ApplicationContext` thường chỉ có một đối tượng bean được chia sẻ cho nhiều luồng xử lý yêu cầu. **Singleton không có nghĩa là an toàn luồng.** Nếu bean có trường dữ liệu thay đổi được (`mutable state`), nhiều luồng có thể cùng đọc hoặc ghi trường đó.

Để bảo vệ dữ liệu chung, ta có thể dùng `synchronized`, `ReentrantLock`, các kiểu atomic hoặc cấu trúc dữ liệu concurrent. Tuy nhiên, bảo vệ đúng một biến chưa đủ: **thời gian giữ khóa cũng quyết định khả năng đáp ứng của ứng dụng.**

Giả sử một bean vừa quản lý trạng thái, vừa gọi HTTP, đọc tệp, truy vấn cơ sở dữ liệu hoặc đợi tác vụ khác hoàn tất:

```text
Luồng A: lấy khóa ---- gọi HTTP / đợi Future ............. cập nhật ---- nhả khóa
Luồng B:               đợi khóa .......................... cập nhật nhanh
Luồng C:               đợi khóa .......................... đọc trạng thái

Thời gian giữ khóa của A ≈ thời gian chờ bên ngoài + thời gian cập nhật.
```

Khi A giữ khóa trong thời gian chờ, B và C có thể bị chặn dù phần thao tác với trạng thái chỉ tốn rất ít thời gian. Thời gian chờ mạng, I/O hay lịch chạy của một task khác thường dài và khó dự đoán hơn nhiều so với thao tác cập nhật bộ nhớ.

**Nguyên tắc thiết kế:** Chỉ giữ khóa trong đoạn thực sự cần bảo vệ trạng thái hoặc bất biến chung (`critical section`). Thực hiện thao tác có thể chặn ở bên ngoài vùng khóa; sau đó lấy lại khóa trong thời gian ngắn để kiểm tra và công bố kết quả.

Bài học tập trung vào **khóa trong tiến trình Java** khi bean có trạng thái. Khóa hàng dữ liệu của cơ sở dữ liệu, transaction và khóa phân tán là các cơ chế khác; chúng có quan hệ với hiệu năng nhưng không được thay thế lẫn nhau.

## 2. Vì sao chờ khi đang giữ khóa là nguy hiểm?

### 2.1. Nghẽn khóa và tăng độ trễ

Với `synchronized (guard)`, chỉ một luồng được sở hữu monitor của `guard` tại một thời điểm. Với `ReentrantLock`, chỉ luồng sở hữu khóa mới có thể giữ vùng cần bảo vệ. Luồng khác cần cùng khóa phải chờ.

Một truy vấn HTTP mất 800 ms trong vùng `synchronized` đồng nghĩa những thao tác chỉ cần 1 ms với **cùng khóa** có thể phải đợi phần lớn 800 ms đó. Đây là hiện tượng tranh chấp khóa (`lock contention`), có thể tạo hàng đợi kéo dài và làm thời gian đáp ứng tăng mạnh khi số request lớn.

Không có một con số timeout chung nào đảm bảo an toàn: ngay cả I/O thường nhanh vẫn có thể chậm bất thường khi bị nghẽn mạng, hết connection, tải tăng hoặc dịch vụ bên ngoài lỗi.

### 2.2. Lan truyền lỗi và thiếu công bằng

Một thao tác chậm có thể trì hoãn các tác vụ không liên quan nếu tất cả dùng một khóa toàn cục. Những luồng đứng chờ khóa cũng sử dụng tài nguyên (ví dụ worker thread của server). `synchronized` không cam kết phục vụ các luồng đang chờ theo thứ tự đến.

Khi hệ thống bận, có thể hình thành chuỗi phụ thuộc: nhiều request đợi monitor, worker bị chiếm, tác vụ khác không được chạy đúng lúc, còn request ban đầu tiếp tục đợi. Vì vậy giữ khóa khi chờ cũng có thể khuếch đại một sự cố nhỏ thành nghẽn toàn ứng dụng.

### 2.3. Bế tắc khi chờ một tác vụ cần chính khóa đó

Trường hợp nguy hiểm hơn là A **giữ khóa** rồi gọi `Future.get()` hoặc `CompletableFuture.join()` để chờ B, trong khi B phải lấy **cùng khóa** mới có thể hoàn tất.

```text
Luồng A:
  đã sở hữu monitor M
  |
  +--> chờ kết quả Future của B
                ^
                |
Luồng B: cần monitor M để hoàn tất
                |
                +---- M vẫn do A giữ

A chờ B; B chờ A nhả M => chờ vòng (deadlock).
```

Rủi ro không chỉ có với `Future`. Một callback, tác vụ nền hoặc đoạn logic trong bean khác cũng có thể cần quay về cập nhật trạng thái đang được khóa. Chỉ cần xuất hiện chu trình chờ tài nguyên là có khả năng bế tắc.

Bế tắc khác với nghẽn khóa thông thường: nghẽn có thể giải tỏa khi chủ khóa kết thúc; bế tắc do vòng phụ thuộc không thể tự tiến triển nếu không có timeout, ngắt, hủy hay tác động bên ngoài.

## 3. Những thao tác không nên thực hiện khi sở hữu khóa

| Thao tác | Ví dụ | Tác hại nếu giữ khóa |
|---|---|---|
| Gọi HTTP hoặc RPC đồng bộ | `HttpClient.send(...)`, gọi API từ xa | Độ trễ mạng và lỗi phía ngoài kéo dài critical section |
| Thao tác I/O có thể chặn | Đọc/ghi tệp, socket, database call | Chờ thiết bị, kết nối, pool hoặc dịch vụ |
| Chờ tác vụ phụ thuộc | `Future.get()`, `CompletableFuture.join()` | Tác vụ được chờ có thể cần khóa đang giữ |
| Chờ thread hay tín hiệu | `Thread.join()`, `CountDownLatch.await()` | Luồng báo tín hiệu có thể cần chính trạng thái đang khóa |
| Đợi hàng đợi hoặc tài nguyên | `BlockingQueue.take()/put()` | Thời gian chờ khó kiểm soát |
| Ngủ trong vùng khóa | `Thread.sleep(...)` | Ngủ không nhả monitor hay `ReentrantLock` đang giữ |
| Gọi mã tùy biến/callback | Listener, plugin, hook chưa rõ nội bộ | Có thể tái nhập, chặn, gọi mạng hoặc tạo phụ thuộc bất ngờ |

Đây là các dấu hiệu cần xem lại **ranh giới giữ khóa**, không có nghĩa tất cả API trên luôn chặn. Ví dụ `Future.get()` có thể trả về ngay nếu tác vụ đã xong; nhưng thiết kế an toàn không nên phụ thuộc vào trường hợp thuận lợi đó.

**Phân biệt quan trọng:** `Object.wait()` khi được gọi đúng cách bên trong `synchronized` sẽ **tạm nhả monitor của đối tượng được wait** trong lúc chờ rồi lấy lại monitor trước khi trả về. `Condition.await()` cũng nhả khóa `ReentrantLock` tương ứng trong thời gian đợi. Chúng là cơ chế phối hợp trạng thái có giao thức kiểm tra điều kiện cụ thể; đừng đánh đồng với `Thread.sleep()`, `Future.get()` hoặc HTTP I/O, vốn **không tự giải phóng khóa bạn đang giữ**. Nếu vẫn sở hữu những khóa *khác*, các khóa đó không tự được nhả.

## 4. Ví dụ sai: giữ monitor trong lúc gọi HTTP

Ví dụ bean Spring sau dùng một monitor để bảo vệ số ký tự đã nhận được từ các yêu cầu. Vì gọi HTTP nằm trong `synchronized`, một lần kết nối chậm sẽ giữ khóa lâu hơn cần thiết.

**Mã minh họa dùng Spring và Java 17**, chưa phải chương trình chạy độc lập; cần Spring trong classpath và URI đến máy chủ có thật:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.springframework.stereotype.Service;

@Service
public class SlowLockedBean {
    private final Object guard = new Object();
    private final HttpClient httpClient = HttpClient.newHttpClient();
    private long totalCharacters;

    public long fetchAndRecord(URI uri)
            throws IOException, InterruptedException {
        synchronized (guard) {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString());

            totalCharacters += response.body().length();
            return totalCharacters;
        }
    }
}
```

`totalCharacters += ...` là thao tác cần được bảo vệ vì nhiều request cùng sửa biến. Tuy nhiên, `httpClient.send(...)` không cần monitor để tải dữ liệu: đưa nó vào vùng khóa chỉ khiến những request khác phải chờ trong thời gian mạng.

Đoạn `synchronized (guard)` trong ví dụ cũng có nghĩa mọi lời gọi cùng dùng **một khóa của cùng bean**. Nếu bean còn phương thức khác cùng dùng `guard`, phương thức ấy cũng bị ảnh hưởng. Lệnh `httpClient.send` có thể ném `IOException` hoặc `InterruptedException`; Java vẫn tự nhả monitor khi rời khỏi khối `synchronized` do ngoại lệ, nhưng các request khác đã phải đợi cho tới thời điểm đó.

## 5. Cách sửa: I/O ở ngoài, cập nhật trạng thái trong vùng khóa ngắn

Với trường hợp chỉ cộng dồn số ký tự, có thể tải HTTP trước rồi dùng monitor trong vài thao tác cập nhật:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.springframework.stereotype.Service;

@Service
public class ShortLockedBean {
    private final Object guard = new Object();
    private final HttpClient httpClient = HttpClient.newHttpClient();
    private long totalCharacters;

    public long fetchAndRecord(URI uri)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        // Có thể mất thời gian lâu, nhưng không sở hữu guard.
        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
        long delta = response.body().length();

        // Chỉ khóa phần cần cập nhật cùng một biến.
        synchronized (guard) {
            totalCharacters += delta;
            return totalCharacters;
        }
    }
}
```

Vì sao phiên bản này tốt hơn?

1. Nhiều request có thể thực hiện I/O độc lập mà không phải chờ cùng một monitor.
2. Các thay đổi của `totalCharacters` vẫn tuần tự theo khóa, nên không bị mất cập nhật do phép cộng chồng lấn.
3. Nếu HTTP lỗi, biến tổng không bị thay đổi. Monitor không bị giữ trong giai đoạn chờ bên ngoài.
4. Phần trả về là giá trị tổng **ngay khi request đó cập nhật xong**; thứ tự hoàn tất mạng và thứ tự tăng tổng có thể khác thứ tự request đến.

Ví dụ này đúng vì kết quả I/O **không phụ thuộc một phiên bản trạng thái đã đọc trước đó**. Không thể áp dụng máy móc kiểu “đưa mọi thứ ra khỏi khóa” nếu việc đọc trạng thái, gọi bên ngoài và ghi kết quả cần giữ bất biến xuyên suốt. Trường hợp đó cần cơ chế kiểm tra phiên bản ở phần sau.

Một mẫu thiết kế thường gặp là:

```text
Giai đoạn A — dưới khóa:
    Đọc snapshot cần thiết, cấp ID, kiểm tra điều kiện tại thời điểm đọc
          |
          v
Nhả khóa — chờ bên ngoài:
    HTTP / database / file / Future / tính toán tốn thời gian
          |
          v
Giai đoạn B — lấy khóa lại:
    Kiểm tra trạng thái còn hợp lệ, hợp nhất hoặc từ chối kết quả,
    cập nhật bất biến chung
          |
          v
Nhả khóa — trả lời/gửi thông báo
```

Trong một số bài toán, bước A không cần khóa nếu trạng thái chỉ đọc và được công bố an toàn; trong bài toán khác, bước B có thể dùng `AtomicLong` hoặc cấu trúc concurrent thay monitor. Điều cốt lõi là chỉ giữ cơ chế bảo vệ tại đoạn cần nó.

## 6. Thí nghiệm Java 17: thao tác nhanh vẫn chạy khi tác vụ chậm đang chờ

Ví dụ chạy được dưới đây dùng `CountDownLatch` thay cho mạng thật. Latch cho phép giữ tác vụ chậm ở một điểm chờ **bên ngoài monitor** và chứng minh tác vụ cập nhật nhanh vẫn có thể lấy khóa. Khác với kiểm thử dựa vào `Thread.sleep`, thứ tự kiểm tra được điều phối bằng tín hiệu nên kết quả không phụ thuộc vào tốc độ máy.

**Tệp `LockBoundaryDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LockBoundaryDemo {
    static final class StateBean {
        private final Object guard = new Object();
        private final List<String> history = new ArrayList<>();

        void slowOperation(CountDownLatch started,
                           CountDownLatch allowFinish)
                throws InterruptedException {

            // Đại diện cho thời điểm bắt đầu chờ I/O bên ngoài.
            started.countDown();
            allowFinish.await();  // Không sở hữu guard ở đây.

            synchronized (guard) {
                history.add("slow");
            }
        }

        void quickUpdate() {
            synchronized (guard) {
                history.add("quick");
            }
        }

        List<String> snapshot() {
            synchronized (guard) {
                return List.copyOf(history);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        StateBean bean = new StateBean();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> slow = executor.submit(() -> {
                try {
                    bean.slowOperation(started, allowFinish);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Tác vụ chậm bị ngắt", interrupted);
                }
            });

            started.await();

            Future<?> quick = executor.submit(bean::quickUpdate);
            quick.get();
            System.out.println(bean.snapshot());

            allowFinish.countDown();
            slow.get();
            System.out.println(bean.snapshot());
        } finally {
            allowFinish.countDown();
            executor.shutdown();
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac LockBoundaryDemo.java
java LockBoundaryDemo
```

Kết quả chuẩn:

```text
[quick]
[quick, slow]
```

Giải thích:

- `started.await()` bảo đảm main biết tác vụ chậm đã đến thời điểm báo hiệu chờ. `allowFinish` vẫn chưa được mở nên tác vụ chậm **chưa thể** thêm `slow` vào danh sách.
- `quick.get()` chỉ hoàn tất sau khi tác vụ nhanh đã lấy `guard`, thêm `quick` rồi nhả khóa.
- Main in snapshot đầu tiên khi tác vụ chậm chưa được mở chốt, nên chỉ có `[quick]`.
- Khi `allowFinish.countDown()`, tác vụ chậm tiếp tục, lấy monitor trong thời gian ngắn rồi thêm `slow`. `slow.get()` bảo đảm cập nhật đó xong trước khi in dòng cuối.
- `List.copyOf(history)` được tạo **bên trong vùng khóa** để nhận một bản sao ổn định. Người gọi không cầm tham chiếu đến `ArrayList` nội bộ và không phải giữ khóa khi dùng bản sao.

Điều quan trọng không phải hai thread nhất thiết chạy song song mọi lúc, mà là **tác vụ đang chờ không chiếm monitor** nên tác vụ khác có thể cập nhật trạng thái được bảo vệ.

## 7. Chờ Future trong vùng synchronized có thể tự tạo deadlock

Đây là một **phản ví dụ chỉ để phân tích, không chạy trực tiếp**, vì lời gọi `get()` có thể chờ mãi:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

final class CircularWaitBean {
    private final Object guard = new Object();
    private String state = "ready";

    String dangerous(ExecutorService executor)
            throws InterruptedException, ExecutionException {
        synchronized (guard) {
            Future<String> dependent = executor.submit(() -> {
                synchronized (guard) {
                    return state;
                }
            });
            return dependent.get(); // Chờ B trong lúc giữ guard.
        }
    }
}
```

Giả sử `executor` có worker đang sẵn sàng: A đang chạy `dangerous` và giữ `guard`; B được gửi vào pool, nhưng B muốn đọc `state` nên phải lấy `guard`. A lại gọi `dependent.get()` để chờ B. Vì A không rời khỏi `synchronized` trước khi B hoàn tất, hai luồng tạo một vòng chờ.

Cách sửa là tách **chờ kết quả** khỏi **sở hữu khóa**:

```java
// Mã minh họa phương thức trong CircularWaitBean:
String safer(ExecutorService executor)
        throws InterruptedException, ExecutionException {
    Future<String> dependent = executor.submit(() -> {
        synchronized (guard) {
            return state;
        }
    });

    // Không giữ guard khi đợi kết quả.
    return dependent.get();
}
```

Mẫu sửa này loại bỏ vòng chờ **trên guard** của ví dụ. Tuy nhiên, `get()` vẫn có thể chờ dài hoặc vô hạn nếu chính tác vụ B bị treo. Với yêu cầu thời hạn rõ ràng, dùng `get(timeout, TimeUnit.SECONDS)` và xử lý `TimeoutException`, đồng thời cân nhắc `cancel(true)` khi thật sự cần hủy. Hết hạn `get(timeout, ...)` **không tự hủy** tác vụ; `cancel(true)` cũng chỉ yêu cầu ngắt theo cơ chế hợp tác.

Một biến thể khác là **executor starvation deadlock**: tác vụ A đang chạy trong pool chỉ có một worker, gửi B vào **chính pool đó** rồi gọi `B.get()`. B chưa thể chạy vì A đang chiếm worker duy nhất; sự cố này có thể xảy ra **ngay cả khi không có monitor**. Vì vậy cần kiểm tra cả phụ thuộc khóa và phụ thuộc tài nguyên worker.

## 8. Đừng đánh mất tính đúng đắn khi tách I/O khỏi khóa

Rút ngắn critical section giúp giảm nghẽn, nhưng có thể tạo lỗi **ghi đè kết quả cũ** nếu trạng thái đã thay đổi trong khoảng không giữ khóa.

Xem quy trình:

```text
A: [khóa] đọc cấu hình phiên bản 7 [nhả]
A:       gọi dịch vụ chậm dựa vào phiên bản 7 ...
B: [khóa] cập nhật cấu hình lên phiên bản 8 [nhả]
A:                                        [khóa] ghi kết quả từ phiên bản 7?
```

Nếu A ghi thẳng kết quả cũ, dữ liệu mới của B có thể bị ghi đè hoặc một bất biến nghiệp vụ bị phá vỡ. Ta cần **snapshot + kiểm tra phiên bản + chỉ commit nếu vẫn hợp lệ**. Đây là kiểu kiểm soát đồng thời lạc quan (`optimistic concurrency control`) trong bộ nhớ.

**Tệp `VersionGuardDemo.java` — ví dụ Java 17 độc lập**

```java
public class VersionGuardDemo {
    static final class StateBean {
        private final Object guard = new Object();
        private String value = "ban đầu";
        private long version = 0;

        record Snapshot(long version, String value) {}

        Snapshot readSnapshot() {
            synchronized (guard) {
                return new Snapshot(version, value);
            }
        }

        void updateFromAnotherRequest(String newValue) {
            synchronized (guard) {
                value = newValue;
                version++;
            }
        }

        boolean publishIfUnchanged(Snapshot snapshot, String result) {
            synchronized (guard) {
                if (version != snapshot.version()) {
                    return false;
                }

                value = result;
                version++;
                return true;
            }
        }
    }

    public static void main(String[] args) {
        StateBean bean = new StateBean();

        StateBean.Snapshot before = bean.readSnapshot();
        String resultOfSlowCall = "kết quả từ dữ liệu cũ";

        // Mô phỏng một request khác cập nhật khi lời gọi ngoài đang chạy.
        bean.updateFromAnotherRequest("dữ liệu mới");

        boolean accepted = bean.publishIfUnchanged(
                before, resultOfSlowCall);

        System.out.println("Đã chấp nhận kết quả cũ: " + accepted);
        System.out.println("Trạng thái cuối: "
                + bean.readSnapshot().value());
    }
}
```

```bash
javac VersionGuardDemo.java
java VersionGuardDemo
```

Kết quả:

```text
Đã chấp nhận kết quả cũ: false
Trạng thái cuối: dữ liệu mới
```

Ví dụ mô phỏng sự thay đổi theo thứ tự cố định để quan sát kết quả; trong ứng dụng thật, hai request có thể chạy trên các luồng khác nhau. `readSnapshot()` chụp cả `version` và `value` dưới cùng monitor. Sau khi làm việc bên ngoài, `publishIfUnchanged(...)` kiểm tra phiên bản và ghi trong **một vùng khóa duy nhất**. Nếu phiên bản đã đổi, kết quả cũ bị từ chối.

Tùy nghiệp vụ, khi kiểm tra phiên bản thất bại có thể:

- Đọc snapshot mới rồi **thử lại bên ngoài khóa**, nhưng cần giới hạn số lần thử và đảm bảo thao tác có thể chạy lại.
- Hợp nhất kết quả nếu phép hợp nhất là hợp lệ, ví dụ cộng thêm một lượng độc lập thay vì thay thế toàn bộ giá trị.
- Trả về trạng thái xung đột để caller hoặc người dùng quyết định.
- Thiết kế lại dữ liệu để hai request không phải cập nhật chung một trường.

**Không thể tạo giao dịch nguyên tử xuyên hệ thống chỉ bằng `synchronized`.** Nếu gọi bên ngoài đã gửi email, chuyển tiền hoặc ghi dữ liệu ở một hệ thống khác, việc không chấp nhận kết quả vào bean **không tự hoàn tác** tác động bên ngoài. Khi có side effect, cần phân biệt giai đoạn tính toán, giai đoạn gọi hệ thống ngoài và giai đoạn ghi local; có thể cần idempotency key, transaction, outbox hoặc quy trình bù trừ theo nghiệp vụ. Đây là một bài toán khác với mục tiêu giảm thời gian giữ monitor.

## 9. Dùng ReentrantLock mà không kéo dài vùng khóa

`ReentrantLock` có hành vi sở hữu tương tự ở điểm cốt lõi: **một luồng giữ khóa chặn luồng khác cần cùng khóa**. Khác với `synchronized`, mã sử dụng `ReentrantLock` phải giải phóng thủ công bằng `unlock()`, thường đặt trong `finally`.

**Mã minh họa bên trong một lớp**, giả định có các trường `lock` và `count`:

```java
private final ReentrantLock lock = new ReentrantLock();
private long count;

long recordAfterSlowOperation(long amount)
        throws InterruptedException {
    // Mô phỏng việc chờ bên ngoài. Không giữ lock.
    Thread.sleep(20);

    lock.lock();
    try {
        count += amount;
        return count;
    } finally {
        lock.unlock();
    }
}
```

Để đưa vào một lớp đầy đủ cần import `java.util.concurrent.locks.ReentrantLock`. Đây là đoạn phương thức minh họa; không có `main` và thời gian ngủ chỉ thay thế thao tác chậm trong ví dụ.

Đừng viết kiểu sau:

```java
lock.lock();
try {
    Thread.sleep(20); // Sai vị trí: ngủ khi vẫn giữ lock.
    count++;
} finally {
    lock.unlock();
}
```

Cơ chế `try/finally` giải phóng khóa khi thành công hoặc khi có ngoại lệ, nhưng **không làm cho việc giữ khóa trong lúc chờ trở nên tốt hơn**.

Khi cần đọc nhiều trường phải nhất quán với nhau, hãy đọc các trường đó trong một đoạn khóa ngắn rồi tạo một snapshot bất biến. Khi cần ghi nhiều trường cùng lúc, hãy cập nhật tất cả chúng trong cùng một đoạn khóa để giữ bất biến. Không nên chia nhỏ critical section đến mức phá vỡ tính nguyên tử của trạng thái.

## 10. Bean Spring: chọn đúng nơi đặt trạng thái và cơ chế đồng bộ

### 10.1. Ưu tiên bean không giữ trạng thái theo request

Ví dụ bean sau chỉ dùng biến cục bộ:

```java
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculateTotal(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

Các lần gọi có tham số và biến cục bộ riêng, không tranh chấp một biến `total` trong bean. Đoạn này là ví dụ thành phần Spring, cần dependency Spring và không có `main`; `Math.multiplyExact` giúp báo `ArithmeticException` khi kết quả `long` tràn số.

Một singleton stateless thường dễ mở rộng hơn singleton chứa dữ liệu tạm của từng request. Nếu cần trạng thái chung, hãy xác định rõ **owner**, phạm vi chia sẻ, bất biến cần bảo vệ và giới hạn tải.

### 10.2. Khi phải có trạng thái chung

| Nhu cầu | Cách tiếp cận có thể phù hợp | Lưu ý |
|---|---|---|
| Đếm độc lập | `AtomicLong` | Giảm nhu cầu dùng monitor chung; nhiều trường liên quan vẫn cần phối hợp |
| Tra cứu/ghi từng khóa | `ConcurrentHashMap` | Các thao tác liên hợp cần API nguyên tử thích hợp, chẳng hạn `compute`; không suy ra mọi chuỗi thao tác đều nguyên tử |
| Nhiều trường có bất biến chung | `synchronized` hoặc `ReentrantLock` ngắn | Duy trì một quy tắc khóa nhất quán, ghi/đọc nhất quán |
| Đọc ảnh chụp ổn định | Snapshot bất biến được tạo dưới khóa | Không trả trực tiếp collection mutable nội bộ |
| Gọi API, database hoặc tệp | I/O ngoài khóa; commit dữ liệu trong khóa | Xử lý timeout, lỗi, idempotency và xung đột phiên bản |
| Xử lý bất đồng bộ trên pool | `ExecutorService` hoặc `TaskExecutor` phù hợp | Không chặn worker chờ vòng; cấu hình năng lực và hàng đợi |

**Đối tượng khóa nên là chi tiết nội bộ** (`private final Object guard = new Object()`) để code ngoài bean không thể tùy tiện khóa cùng monitor. Việc dùng `synchronized` trên toàn phương thức instance sẽ dùng monitor của `this`; điều này dễ tạo vùng khóa lớn và tác động tới những lời gọi khác trên cùng instance. Một khóa riêng giúp biểu đạt phạm vi đồng bộ rõ hơn, nhưng vẫn phải giữ critical section ngắn.

### 10.3. @Async và tác vụ phụ thuộc

`@Async` có thể chuyển việc thực thi sang bộ thực thi do Spring cấu hình khi lời gọi đi qua cơ chế proxy thích hợp. Điều này **không** làm biến instance tự động an toàn luồng. Nếu bean singleton gửi một task nền rồi đứng dưới `synchronized` để gọi `Future.get()`, task có thể bị kẹt vì cần cập nhật chính bean đó.

Ngược lại, với `CompletableFuture`, một số continuation không có hậu tố `Async` (như `thenApply`, `thenAccept`) có thể chạy ngay trên luồng hoàn tất giai đoạn trước hoặc luồng đăng ký continuation nếu giai đoạn đã xong. Không nên cho rằng callback luôn chạy ở một worker độc lập hoặc luôn an toàn khi gọi từ trong vùng khóa. Hãy xác định ranh giới tác vụ, cập nhật kết quả bằng đoạn đồng bộ nhỏ và chỉ chờ khi đã rời vùng khóa.

`@Transactional` xử lý ranh giới transaction của các tài nguyên hỗ trợ, **không** biến các trường Java trong bean thành an toàn luồng. Hơn nữa, nếu một transaction đang giữ khóa dữ liệu ở cơ sở dữ liệu, gọi dịch vụ mạng chậm bên trong transaction cũng có thể làm kéo dài thời gian giữ các khóa cơ sở dữ liệu đó. Đây là hai loại khóa khác nhau nhưng cùng dẫn tới nghẽn khi giữ tài nguyên lâu.

## 11. Timeout, interrupt và cleanup

Chuyển I/O ra ngoài monitor giúp các thao tác khác không bị khóa oan, nhưng **không có nghĩa chính tác vụ I/O sẽ hoàn tất**. Với tác vụ có thể chặn, cần chính sách thời hạn và hủy rõ ràng:

1. **Đặt timeout ở nơi phát sinh độ trễ.** Ví dụ HTTP client/request timeout, database query timeout hoặc `Future.get(timeout, unit)`. Đặt timeout vẫn cần cách xử lý khi hết hạn.
2. **Đảm bảo vùng finally nhả ReentrantLock.** Với `synchronized`, monitor được nhả tự động khi thoát khối; `ReentrantLock` bắt buộc `unlock()`.
3. **Bảo toàn tín hiệu ngắt khi bắt mà không ném tiếp.** `InterruptedException` là tín hiệu để phối hợp dừng tác vụ; không nên nuốt ngoại lệ rồi tiếp tục chờ vô hạn.
4. **Không coi cancel là lệnh dừng cưỡng bức.** `Future.cancel(true)` có thể yêu cầu ngắt task, nhưng task cần hợp tác để dừng. Nếu một tác vụ bỏ qua ngắt hoặc một thao tác không hỗ trợ ngắt, nó có thể tiếp tục.
5. **Không đóng pool do bên khác sở hữu.** Trong Spring, pool dùng chung do container quản lý thường được đóng theo vòng đời application context; code nghiệp vụ không tự `shutdown()` sau mỗi request.

Ví dụ một mẫu chờ `Future` **bên ngoài mọi khóa của bean**, nằm trong phương thức có quyền ném `InterruptedException` và `ExecutionException`:

```java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true);
    throw new IllegalStateException("Tác vụ vượt thời hạn", timeout);
}
```

Ở đây `future` là `Future<T>`, phương thức trả về `T`, và đã import các kiểu tương ứng từ `java.util.concurrent`. Đây là mảnh mã minh họa, không phải một chương trình độc lập. Nếu luồng gọi bị ngắt, hãy để `InterruptedException` lan lên tầng có trách nhiệm xử lý; chỉ khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` khi quyết định bắt rồi không ném tiếp.

**Cảnh báo:** Nếu mã này vẫn nằm **bên trong** `synchronized`, tối đa 2 giây chờ của `get` vẫn là tối đa 2 giây mà những luồng khác có thể phải đợi khóa. Timeout là chính sách cho thao tác chờ; **không phải** biện pháp thay thế việc thiết kế ranh giới khóa.

## 12. Phân biệt khóa, trạng thái luồng và khả năng quan sát

Khi sự cố xảy ra trong môi trường chạy, thread dump và số liệu về pool giúp chỉ ra một luồng đang chờ gì và có giữ khóa nào không.

- Luồng có trạng thái `BLOCKED` thường đang chờ lấy một monitor `synchronized`; nhìn thêm vị trí lock owner thay vì chỉ đếm trạng thái.
- Luồng có trạng thái `WAITING` hoặc `TIMED_WAITING` có thể đang gọi `Future.get()`, `join()`, `sleep()` hay `await()`. Trạng thái WAITING **không chứng minh** luồng đã nhả tất cả monitor; cần xem stack và các monitor nó đang sở hữu.
- Với `ReentrantLock`, chi tiết chờ khóa có thể xuất hiện qua các cơ chế park/AQS; thread state đơn lẻ chưa đủ để kết luận.
- Quan sát thời gian chờ, tỷ lệ timeout, độ sâu queue, số worker bận và p95/p99 request latency. Việc tăng số worker đôi khi chỉ che khuất một khóa chung bị giữ quá lâu.

Một dấu hiệu thiết kế cần kiểm tra là bean có cùng một `synchronized` method vừa gọi HTTP, vừa ghi cache, vừa xử lý callback. Câu hỏi cần đặt ra là: **“Đoạn mã nào thực sự cần khóa để duy trì bất biến?”** Từ đó đưa các bước không cần khóa ra ngoài, kiểm tra lại điều kiện thay đổi trạng thái và xác minh bằng thử nghiệm đồng thời.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả có thể gặp | Cách sửa |
|---|---|---|
| Đánh dấu cả method `synchronized` dù phần lớn method là I/O | Mọi request dùng cùng bean phải nối hàng dài | Khóa riêng quanh đọc/ghi trạng thái; I/O ra ngoài |
| Gọi `Future.get()` / `join()` trong monitor | Có thể deadlock với task cần cùng monitor | Gửi việc và chờ ngoài monitor; kiểm tra phụ thuộc worker |
| Dùng `Thread.sleep()` trong critical section để “chờ an toàn” | Không nhả khóa, tăng độ trễ | Thiết kế cơ chế chờ ngoài khóa; nếu cần điều kiện phối hợp, dùng API phù hợp |
| Đưa I/O ra ngoài khóa rồi ghi kết quả cũ không kiểm tra | Lost update hoặc ghi đè trạng thái mới | Snapshot + version check / hợp nhất / retry |
| Chỉ đồng bộ hàm ghi, đọc trực tiếp các trường mutable | Có thể thấy dữ liệu không nhất quán hoặc cũ | Dùng cùng quy tắc đồng bộ khi đọc; snapshot bất biến |
| Trả `ArrayList`/`HashMap` mutable nội bộ cho caller | Caller sửa dữ liệu mà không đi qua khóa | Trả bản sao hoặc chế độ truy cập an toàn |
| Nghĩ `@Async` làm bean singleton thread-safe | Race condition vẫn tồn tại | Xác định rõ ownership và cơ chế đồng bộ |
| Nghĩ `@Transactional` bảo vệ trường của bean | Đồng bộ dữ liệu Java không được bảo đảm | Phân biệt transaction DB với monitor JVM |
| Quên `unlock()` khi có exception | Luồng khác có thể chờ không thời hạn | `lock.lock(); try { ... } finally { lock.unlock(); }` |
| Dựa vào timeout để giữ khóa khi chờ | Contention kéo dài hết timeout | Tách chờ ra ngoài critical section |
| Dùng quá nhiều khóa hoặc nhiều thứ tự lấy khóa | Nguy cơ khóa chéo vòng phụ thuộc | Quy tắc thứ tự khóa thống nhất; giảm phạm vi khóa |

## 14. Bài tập thực hành

### Bài 1 — Xác định ranh giới giữ khóa

Cho một singleton bean có các bước: đọc `version`, gọi HTTP theo `version`, parse JSON, cập nhật `cachedData` và `version`. Hãy chỉ rõ bước nào cần khóa; nếu HTTP đang chạy mà request khác đổi `version`, phải làm gì với kết quả cũ?

**Gợi ý:** Chụp snapshot dưới khóa; HTTP và parse ở ngoài; lấy lại khóa kiểm tra snapshot còn đúng trước khi commit. Nếu không đúng, quyết định retry hoặc trả xung đột. Đừng giả định kết quả cũ luôn dùng được.

### Bài 2 — Đọc và chạy ví dụ LockBoundaryDemo

Chạy chương trình rồi giải thích tại sao `quick` luôn được in trước `slow`. Liệu chương trình còn bảo đảm tiến triển nếu chuyển `allowFinish.await()` vào trong `synchronized (guard)` và vẫn gọi `quick.get()` trước khi mở chốt?

**Gợi ý:** Khi slow nắm monitor và chờ chốt, quick không thể lấy guard để hoàn tất; main lại chờ quick trước khi mở chốt. Đó là vòng chờ. Chỉ phân tích biến thể sai, không chạy không có timeout.

### Bài 3 — Phân biệt hai kiểu bế tắc

So sánh trường hợp A giữ monitor M rồi chờ B cần M, với trường hợp A chạy trong pool một worker, gửi B vào cùng pool rồi chờ B. Vì sao loại thứ hai không cần monitor vẫn bế tắc?

**Gợi ý:** Tìm tài nguyên mà B phải đợi: monitor ở trường hợp một, worker trống ở trường hợp hai.

### Bài 4 — Chứng minh không ghi đè dữ liệu mới

Chạy `VersionGuardDemo`. Nếu thay `publishIfUnchanged` bằng lệnh `value = result` không kiểm tra version, kết quả sẽ khác thế nào? Khi nào có thể hợp nhất thay vì từ chối?

**Gợi ý:** Trạng thái cuối có thể bị ghi đè bằng kết quả cũ. Phép cộng dồn độc lập có thể hợp nhất, nhưng thay một cấu hình dựa trên phiên bản cũ thường cần kiểm tra xung đột.

### Bài 5 — Rà soát bean thực tế

Với một bean đang có `synchronized` hoặc `ReentrantLock`, hãy liệt kê thao tác bên trong vùng khóa và phân loại thành: đọc/ghi shared mutable state, I/O hoặc chờ, tính toán không cần trạng thái, gọi code bên ngoài. Chỉ giữ phần cần bảo toàn bất biến; kiểm tra bằng test đồng thời và quan sát thread dump nếu xuất hiện nghẽn.

## 15. Điều cần nhớ

- **Không giữ monitor hoặc ReentrantLock trong lúc đợi I/O, Future hoặc tác vụ phụ thuộc**, trừ khi có lý do đồng bộ cụ thể và đã chứng minh không tạo chờ vòng hay contention không chấp nhận được.
- **Đọc snapshot ngắn → nhả khóa → thực hiện thao tác chậm → khóa ngắn để kiểm tra và cập nhật** là mẫu nền tảng. Khi có thay đổi đồng thời, cần version check, hợp nhất hoặc retry phù hợp.
- **`synchronized` bảo vệ dữ liệu trong một tiến trình, không điều khiển mạng, transaction DB hay hệ thống ngoài.** Không dùng nó thay cho idempotency hoặc giao dịch xuyên dịch vụ.
- **`Future.get()` và `Thread.sleep()` không tự nhả khóa đang sở hữu.** `Object.wait()` và `Condition.await()` có cơ chế nhả khóa tương ứng riêng khi được dùng đúng, không làm mọi thao tác chờ trở nên an toàn.
- **Bean singleton và `@Async` không tự tạo thread safety.** Giảm shared mutable state, dùng primitive đồng bộ phù hợp, giới hạn tài nguyên và quản lý vòng đời tác vụ rõ ràng.
