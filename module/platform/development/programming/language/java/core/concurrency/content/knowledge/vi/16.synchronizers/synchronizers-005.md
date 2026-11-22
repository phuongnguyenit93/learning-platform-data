# Exchanger<T> trao đổi dữ liệu giữa hai luồng trong Java

`Exchanger<T>` là một **điểm gặp gỡ đồng bộ (rendezvous)** trong `java.util.concurrent`: một thread mang một đối tượng tới `exchange()`, thread khác cũng tới điểm đó với một đối tượng của nó; khi **ghép thành công một cặp**, mỗi bên nhận **đối tượng của bên kia** và tiếp tục. Nếu chỉ một bên tới, bên đó **đợi** cho tới khi có partner, bị interrupt hoặc hết hạn timeout nếu dùng overload có thời hạn.

Ví dụ:

```text
Thread A                         Thread B
--------                         --------
có "APPLE"                       có "BANANA"
    |                                |
    +--> exchanger.exchange("APPLE") |
                                     +--> exchanger.exchange("BANANA")
                   GẶP NHAU
                  /         \
A nhận "BANANA" <-           -> B nhận "APPLE"
    |                                |
  tiếp tục                         tiếp tục
```

Đây **không phải queue tích lũy nhiều item**, không phải broadcast một item cho mọi consumer, cũng không phải "gửi trước rồi quên". Hai phía phải tham gia vào **cùng một lần trao đổi thành công** để cả hai nhận được object đối tác. Công cụ rất phù hợp khi **hai giai đoạn của pipeline cần bàn giao cho nhau hai buffer**: producer chuyển buffer đầy và nhận lại buffer trống của consumer, giúp tái sử dụng vùng nhớ thay vì cấp phát liên tục.

Bài Knowledge này thuộc **Synchronizers** trong **Java concurrency nói chung**. Ví dụ dùng Java SE 17+, không dựa vào Spring Framework.

## 1. Bản chất của `Exchanger<T>`

`Exchanger<V>` là một class đồng bộ hoá chứ không phải `Collection`, `Queue` hoặc `Future`.

- **Hai chiều:** hai thread trao đổi, mỗi bên đưa vào một giá trị và nhận giá trị từ bên kia.
- **Ghép cặp:** nếu nhiều thread cùng gọi trên một `Exchanger`, runtime có thể ghép chúng thành những **cặp**; không có danh tính partner cố định theo class.
- **Đồng bộ tại điểm trao đổi:** với một cặp thành công, mỗi bên chỉ đi tiếp sau khi phần trao đổi đã được phối hợp với phía kia.
- **Có blocking:** nếu không có partner, `exchange()` không timeout có thể chờ mãi; bản có timeout cho phép giới hạn thời gian.
- **Có interruption:** các overload khai báo `InterruptedException`; đoạn code gọi phải propagate hoặc xử lý hủy.
- **Không lưu lịch sử:** không có API `peek()`, `size()`, `take()` hay `drain()`. Sau một lần trao đổi, object đã thuộc luồng xử lý tiếp theo của phía nhận theo giao thức ứng dụng.
- **Không tự tạo thread:** ứng dụng vẫn phải dùng `Thread`, `ExecutorService` hoặc cơ chế thực thi phù hợp.

Tên generic `T` hay `V` chỉ là tên type parameter. `Exchanger<String>` trao đổi references tới `String`; `Exchanger<List<Integer>>` trao đổi references tới list. Nó không clone hoặc serialize object.

## 2. Chữ ký API và cách import

Dùng:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
```

Các member chính trong Java SE 17:

```java
public Exchanger();

public V exchange(V x) throws InterruptedException;

public V exchange(V x, long timeout, TimeUnit unit)
        throws InterruptedException, TimeoutException;
```

Đây là **chữ ký minh họa**, không phải mã chạy độc lập; `V` là type parameter của class.

| Phương thức | Hành vi |
| --- | --- |
| `new Exchanger<T>()` | Tạo một điểm trao đổi; chưa có thread nào chờ |
| `exchange(myObject)` | Chờ một thread khác tới để swap; không đặt giới hạn thời gian |
| `exchange(myObject, timeout, unit)` | Chờ tối đa khoảng timeout cho một partner; có thể ném `TimeoutException` |
| Giá trị trả về | Object mà **thread đối tác** đã cung cấp ở lần exchange thành công |

`Exchanger` không cung cấp `send` và `receive` tách rời. **Cả hai thread gọi cùng một method** để vừa gửi vừa nhận. Vì vậy cách tư duy phù hợp là "đổi" chứ không phải "đẩy item vào hàng đợi".

## 3. Trình tự của một lần trao đổi thành công

Giả sử A và B cùng chia sẻ đúng một instance `Exchanger<Message>`:

1. A tạo `messageA` và gọi `exchange(messageA)`.
2. Nếu chưa có partner, A chờ tại điểm trao đổi.
3. B tạo `messageB`, gọi `exchange(messageB)` trên **chính instance đó**.
4. Một cặp A/B được ghép; tham chiếu được swap theo hợp đồng.
5. A nhận object B đã đưa, B nhận object A đã đưa.
6. Hai thread tiếp tục độc lập, có thể ở những thời điểm khác nhau do scheduler.

Không có cam kết A chạy tiếp trước B hay ngược lại. Cũng không có cam kết hai bên thức dậy **đúng cùng một nanosecond**. Kết quả swap là điều được bảo đảm; thứ tự log và thời gian wake-up không phải phần của contract.

Sơ đồ trạng thái khái niệm:

```text
A arrives --------\
                   >--- successful pairing ---> both return peer item
B arrives --------/

A arrives --- waits --- timeout -------> TimeoutException
A arrives --- waits --- interrupt -----> InterruptedException
A arrives --- waits --- forever? ------> possible without partner or cancellation
```

Các đường timeout/interrupt không phải một giao dịch chuyển item thành công. Application phải quyết định xử lý value vẫn giữ ở bên gọi thế nào và có retry hay kết thúc.

## 4. Ví dụ Java 17+: hai thread trao đổi String

Lưu thành `BasicExchangerDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class BasicExchangerDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<String> aGot = new AtomicReference<>();
        AtomicReference<String> bGot = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                start.await();
                aGot.set(exchanger.exchange(
                        "APPLE", 5, TimeUnit.SECONDS));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "A");

        Thread b = new Thread(() -> {
            try {
                start.await();
                bGot.set(exchanger.exchange(
                        "BANANA", 5, TimeUnit.SECONDS));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "B");

        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();

        System.out.println("A received: " + aGot.get());
        System.out.println("B received: " + bGot.get());
    }
}
```

Chạy trên JDK 17+:

```bash
javac BasicExchangerDemo.java
java BasicExchangerDemo
```

**Stdout trên đường chạy thành công (hai thread gặp nhau trong thời hạn):**

```text
A received: BANANA
B received: APPLE
```

Tại sao không in từ trong worker? Nếu để A/B cùng `System.out.println`, thứ tự hai dòng phụ thuộc lịch thread. Code ghi kết quả vào `AtomicReference`, dùng `Thread.join()` chờ cả hai xong, rồi main in theo thứ tự cố định.

`CountDownLatch` cho hai thread khởi hành gần nhau, nhưng không bảo đảm *thời điểm đến exchange chính xác*. Timeout 5 giây là giới hạn tránh treo lâu nếu hệ thống bị lỗi; trên môi trường bị tạm dừng quá thời hạn, demo có thể đi vào nhánh timeout thay vì stdout thành công.

**Lưu ý kiểm thử:** bản demo dùng exception handler đơn giản để làm nổi bật happy path; code production nên thu thập lỗi từ cả hai thread bằng `Future`, completion result hoặc handler có quản lý thay vì chỉ ném unchecked exception trên worker.

## 5. Điều gì xảy ra khi không có partner?

Với:

```java
String peer = exchanger.exchange("HELLO");
```

nếu chỉ một thread duy nhất từng gọi `exchange` trên instance đó, thread có thể **đợi vô hạn**. Điều này thường gặp khi:

- Thread đối tác chưa được start.
- Thread đối tác đã kết thúc vì exception.
- Hai phía dùng **hai instance `Exchanger` khác nhau**.
- Một phía gọi lần thứ hai, phía kia chỉ gọi một lần rồi thoát.
- Một phía đang kẹt ở lock/I/O trước khi chạm `exchange`.
- Caller cho rằng `exchange` chỉ là `offer` vào queue và không cần receiver.

Đừng dùng `Thread.sleep` để đoán "đối tác chắc đã sẵn". Nếu việc chờ vô hạn là không chấp nhận được, dùng overload có timeout và thiết kế giao thức xử lý failure/interrupt rõ.

## 6. Overload có timeout

Chữ ký:

```java
T peer = exchanger.exchange(
        myValue, timeout, TimeUnit.MILLISECONDS);
```

Đây là snippet minh họa với biến kiểu `T`/`myValue` đã được định nghĩa trong method.

Các kết quả có thể xảy ra:

- Một đối tác được ghép trong thời hạn: trả object của partner.
- Chờ vượt thời hạn mà chưa ghép: ném `TimeoutException`.
- Thread nhận interrupt lúc bắt đầu hoặc đang chờ: ném `InterruptedException`; interrupt status được **xóa** khi ngoại lệ được ném theo hợp đồng.
- Nếu `timeout <= 0`, lời gọi **không chờ** để partner mới tới. Nó vẫn có thể ghép nếu có thread khác đã chờ sẵn; vì vậy **không** tự động kết luận mọi lần gọi zero-timeout đều ném TimeoutException.

Timeout của A không phải lệnh đóng `Exchanger`, không có tác dụng tự động interrupt B và không truyền failure cho những thread khác. Mỗi phía cần có chính sách nhất quán về việc dừng/khởi động lại vòng trao đổi.

## 7. Ví dụ Java 17+: một thread đơn độc bị timeout

Lưu thành `ExchangerTimeoutDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExchangerTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        boolean timedOut = false;

        try {
            exchanger.exchange("ALONE", 30, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            timedOut = true;
        }

        System.out.println("Timed out: " + timedOut);
    }
}
```

```bash
javac ExchangerTimeoutDemo.java
java ExchangerTimeoutDemo
```

Stdout chính xác nếu main không bị interrupt từ bên ngoài:

```text
Timed out: true
```

Chương trình không có thread partner nào, nên `exchange` không thể ghép thành công. Sau thời gian chờ, method ném `TimeoutException`; biến nhận true và ứng dụng vẫn tiếp tục.

**Timeout không có nghĩa object "ALONE" đã được gửi tới một queue và bị mất.** Nó chưa được swap thành công. Nếu ứng dụng muốn retry trao đổi cùng payload, phải xác định liệu partner tương lai sẽ dùng cùng phiên làm việc và có nguy cơ ghép nhầm lượt hay không.

## 8. `InterruptedException` và phục hồi interrupt flag

`Exchanger.exchange` là một lời gọi có thể bị interrupt. Nếu thread bị ngắt khi đang chờ, hoặc có interrupt status lúc vào method theo hợp đồng, nó ném `InterruptedException` và **xóa interrupt status**.

Nếu method cho phép `throws InterruptedException`, thường nên **truyền ngoại lệ** để tầng gọi thực hiện cancellation policy:

```java
static String swap(
        Exchanger<String> exchanger, String value)
        throws InterruptedException {
    return exchanger.exchange(value);
}
```

Đây là method minh họa.

Ở ranh giới không thể thêm checked exception như `Runnable.run()`, mẫu thông dụng:

```java
try {
    String received = exchanger.exchange(message);
    handle(received);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là snippet minh họa với `message` và `handle` thuộc ứng dụng. **Restore rồi dừng công việc phù hợp**, không chỉ đặt lại flag rồi lặp `exchange` vô hạn.

Đừng catch rỗng:

```java
catch (InterruptedException ignored) {
    // Sai: xóa tín hiệu hủy và tiếp tục bình thường.
}
```

Cách đó có thể khiến worker không dừng khi executor shutdown/cancel, nhất là khi phía đối tác đã biến mất.

## 9. Ví dụ Java 17+: interrupt khi đang tìm partner

Lưu thành `ExchangerInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExchangerInterruptDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean clearedInCatch = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try {
                entered.countDown();
                exchanger.exchange("NEVER_MATCHED");
            } catch (InterruptedException e) {
                caught.set(true);
                clearedInCatch.set(
                        !Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "waiting-worker");

        worker.start();
        entered.await();

        // Không có partner, worker chỉ thoát qua interruption.
        worker.interrupt();
        worker.join();

        System.out.println("InterruptedException: " + caught.get());
        System.out.println("Flag cleared in catch: "
                + clearedInCatch.get());
        System.out.println("Flag restored: " + restored.get());
    }
}
```

```bash
javac ExchangerInterruptDemo.java
java ExchangerInterruptDemo
```

Stdout chính xác:

```text
InterruptedException: true
Flag cleared in catch: true
Flag restored: true
```

Tại sao kết quả đáng tin:

1. Worker gửi `entered` ngay trước lời gọi `exchange`.
2. Nếu main interrupt khi worker đã chờ, `exchange` ném exception. Nếu interrupt tới **trước** khi worker thực sự vào exchange, method vẫn phát hiện interrupt flag ở điểm vào và ném.
3. Không có thread thứ hai nên không xảy ra ghép cặp bất ngờ.
4. Catch quan sát flag đã được xóa theo API, rồi gọi `Thread.currentThread().interrupt()`.
5. Main `join` chờ worker kết thúc trước khi đọc các `AtomicBoolean`.
6. Không dựa vào `worker.isInterrupted()` sau khi worker đã kết thúc để chứng minh restoration; code đo **ngay trong worker**.

Tính hợp tác hủy ở đây thuộc về **worker đang chờ**. Gọi `worker.interrupt()` không có nghĩa mọi thread đang dùng cùng exchanger đều bị interrupt.

## 10. Hai vòng trao đổi liên tiếp

Một `Exchanger` có thể được tái sử dụng nhiều lần:

```text
Round 1:
A gửi A1; B gửi B1; A nhận B1; B nhận A1

Round 2:
A gửi A2; B gửi B2; A nhận B2; B nhận A2
```

Nếu **đúng hai thread** tham gia, cả hai cùng gọi theo thứ tự lượt nhất quán, mỗi lời gọi có thể ghép với lời gọi tương ứng còn chờ của phía kia. Không cần tạo `new Exchanger` cho từng vòng.

Nhưng nếu một phía bỏ một lượt, retry không phối hợp hoặc xuất hiện thread thứ ba, **một cuộc gặp sau có thể không còn mang ý nghĩa nghiệp vụ cùng round**. Exchanger không tự mang "sequence number" hay kiểm tra rằng hai payload thuộc cùng phiên.

Giải pháp cho giao thức nhiều vòng:

- Đưa `roundId` hoặc correlation ID vào payload.
- Quy định mỗi phía trao đổi chính xác một lần mỗi round.
- Khi timeout/interrupt, xác định rõ **hủy cả phiên** hay retry có đồng bộ.
- Không gửi lại âm thầm nếu một phía có thể đã đi sang round kế.
- Nếu cần match theo request ID bất kỳ, Exchanger đơn không phải cấu trúc phù hợp; dùng map/future/queue theo correlation key.

## 11. Ví dụ Java 17+: hai lượt trao đổi có kết quả cố định

Lưu thành `ExchangerRoundsDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExchangerRoundsDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        AtomicReference<String> aResults = new AtomicReference<>();
        AtomicReference<String> bResults = new AtomicReference<>();

        Thread a = new Thread(() -> {
            try {
                String first = exchanger.exchange(
                        "A1", 5, TimeUnit.SECONDS);
                String second = exchanger.exchange(
                        "A2", 5, TimeUnit.SECONDS);
                aResults.set(first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        Thread b = new Thread(() -> {
            try {
                String first = exchanger.exchange(
                        "B1", 5, TimeUnit.SECONDS);
                String second = exchanger.exchange(
                        "B2", 5, TimeUnit.SECONDS);
                bResults.set(first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("A got: " + aResults.get());
        System.out.println("B got: " + bResults.get());
    }
}
```

```bash
javac ExchangerRoundsDemo.java
java ExchangerRoundsDemo
```

Stdout khi hai thread phối hợp thành công trong timeout:

```text
A got: B1,B2
B got: A1,A2
```

Chỉ hai thread dùng chung instance, mỗi bên phải hoàn tất round 1 trước khi có thể gọi round 2. Không có thread thứ ba làm nhiễu pairing, nên các kết quả được xác định theo round. Nếu môi trường bị scheduler đình trệ quá 5 giây hoặc một worker thất bại, đường lỗi phải được xử lý bởi ứng dụng thực.

## 12. Bàn giao reference, không copy nội dung

Khi:

```java
List<Integer> received = exchanger.exchange(myBuffer);
```

thao tác trao đổi **tham chiếu** tới object. Nó không deep-copy list, không copy byte array, không biến object thành immutable. Nếu A đã gửi một `ArrayList` cho B nhưng A vẫn giữ reference cũ và tiếp tục `add` trong lúc B đọc, **vẫn có data race**.

Hãy dùng quy tắc **ownership transfer**:

1. A sở hữu buffer A trước exchange và được phép ghi vào nó.
2. A gọi `exchange(bufferA)`, không sửa buffer A sau khi đã đưa cho exchanger nếu phía kia có thể truy cập.
3. Khi exchange thành công, A sở hữu **buffer nhận từ B**; B sở hữu buffer A.
4. B chỉ đọc/ghi buffer được nhận theo giao thức đã thống nhất.
5. Những reference cũ không được dùng lại để sửa object đã bàn giao.

Nếu cần giữ ownership cùng lúc cho nhiều thread, phải dùng immutable data, snapshot copy hoặc synchronization riêng. `Exchanger` không phải "bộ khóa" cho mọi thao tác trên object được swap.

## 13. Java Memory Model: happens-before qua lần swap

Javadoc Java SE 17 ghi rõ hiệu ứng memory consistency:

> Với một cặp thread trao đổi thành công, **các hành động trước `exchange()` ở mỗi bên happens-before các hành động sau khi trở về từ `exchange()` tương ứng ở bên kia**.

Điều này rất quan trọng khi trao đổi **mutable buffer**:

```text
Thread A                               Thread B
--------                               --------
buffer.values[0] = 42
buffer.ready = true
    |
    |  Exchanger.exchange(buffer)
    +-------------------------------> receives buffer
                                        |
                                        v
                                  read buffer.ready
                                  read buffer.values[0]
```

Nếu A hoàn tất ghi **trước** exchange thành công và B đọc buffer sau exchange, JMM cung cấp quan hệ visibility cần thiết trên đường trao đổi đó. Không phải đặt mọi field trong buffer thành `volatile` chỉ để công bố những ghi *trước bàn giao* theo giao thức.

Tuy vậy:

- **Happens-before không tự khóa object sau trao đổi.** Nếu A tiếp tục sửa buffer sau khi đã đưa nó cho B, vẫn có rủi ro cạnh tranh.
- Quan hệ này áp dụng cho **cặp exchange thành công**; một lần timeout không thể dùng làm bằng chứng rằng peer đã nhận dữ liệu.
- Dữ liệu được ghi **sau** khi A đã thực hiện exchange không tự trở thành "đã có trước khi B đọc".
- Nếu buffer chứa reference tới những object mà thread thứ ba tiếp tục sửa, phải xem xét synchronization của những object đó riêng.
- Không suy ra một "global happens-before" giữa mọi thread từng dùng cùng exchanger ở các round khác nhau.

## 14. Ví dụ Java 17+: công bố payload mutable bằng exchange

Lưu thành `ExchangerVisibilityDemo.java`:

```java
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExchangerVisibilityDemo {
    static final class Payload {
        int number;  // không cần volatile cho publication ở ví dụ này
        String text;
    }

    public static void main(String[] args) throws InterruptedException {
        Exchanger<Payload> exchanger = new Exchanger<>();
        AtomicInteger observed = new AtomicInteger(-1);

        Thread producer = new Thread(() -> {
            Payload payload = new Payload();
            payload.number = 42;
            payload.text = "ready";

            try {
                exchanger.exchange(payload, 5, TimeUnit.SECONDS);
                // Không chạm lại payload sau khi đã bàn giao.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                Payload received = exchanger.exchange(
                        new Payload(), 5, TimeUnit.SECONDS);

                if ("ready".equals(received.text)) {
                    observed.set(received.number);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        });

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Observed: " + observed.get());
    }
}
```

```bash
javac ExchangerVisibilityDemo.java
java ExchangerVisibilityDemo
```

Stdout nếu exchange thành công:

```text
Observed: 42
```

Đọc `number` và `text` không tạo data race trong cấu hình demo: producer ghi trước bàn giao, consumer đọc sau khi nhận; producer không sửa lại object. `AtomicInteger` ở đây dùng làm kênh ghi kết quả cho main. Main đợi `join` để chắc hai thread đã rời công việc.

Nếu thêm `producerPayload.number++` **sau exchange** trong producer trong lúc consumer vẫn đọc, lập luận không còn đúng: object đã được chia sẻ để biến đổi mà không có ownership/synchronization phù hợp.

## 15. Use case kinh điển: producer đổi buffer đầy lấy buffer trống

Một pipeline có hai giai đoạn:

- **Producer:** lấp đầy buffer từ dữ liệu đầu vào.
- **Consumer:** xử lý buffer đầy, làm trống rồi trao đổi trở lại.

`Exchanger<Buffer>` giúp hai bên bàn giao theo cặp:

```text
Producer                              Consumer
--------                              --------
buffer P = empty                      buffer C = empty
fill P
  |                                      |
  +---------- exchange(P) ---------------+ exchange(C)
  |                                      |
gets C = empty                          gets P = full
fill C                                  process P; clear P
  |                                      |
  +---------- exchange(C) ---------------+ exchange(P)
  |                                      |
gets P = empty                          gets C = full
...
```

Lợi ích:

1. Mỗi phía có **một buffer riêng đang sở hữu** giữa hai lần swap.
2. Không cần cấp phát buffer mới cho mỗi batch nếu tái sử dụng phù hợp.
3. Producer bị **backpressure** tự nhiên khi chờ consumer sẵn sàng đổi buffer.
4. Consumer không đọc một buffer đang bị producer sửa, **nếu ownership protocol được giữ đúng**.
5. Không cần một shared mutable `ArrayList` với hai thread liên tục thêm/xóa trên cùng object.

Nhược điểm: hai giai đoạn bị **ghép nhịp với nhau**. Nếu consumer rất chậm hoặc thất bại, producer có thể đợi lâu. Nó không phải queue cho phép producer đẩy 100 batches rồi đi tiếp.

## 16. Ví dụ Java 17+: producer–consumer đổi hai `ArrayList`

Lưu thành `ExchangerBufferDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExchangerBufferDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<List<Integer>> exchanger = new Exchanger<>();
        AtomicReference<List<Integer>> result = new AtomicReference<>();

        Thread producer = new Thread(() -> {
            List<Integer> myBuffer = new ArrayList<>();
            try {
                for (int n = 1; n <= 3; n++) {
                    myBuffer.add(n);

                    // Gửi buffer đã chứa một item, lấy buffer trống từ consumer.
                    myBuffer = exchanger.exchange(
                            myBuffer, 5, TimeUnit.SECONDS);

                    // Đây là buffer vừa được phía kia giao; nó đang trống
                    // theo giao thức của ví dụ.
                    myBuffer.clear();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            List<Integer> myBuffer = new ArrayList<>();
            List<Integer> collected = new ArrayList<>();

            try {
                for (int round = 0; round < 3; round++) {
                    // Gửi buffer trống, nhận buffer đầy.
                    myBuffer = exchanger.exchange(
                            myBuffer, 5, TimeUnit.SECONDS);

                    collected.addAll(myBuffer);
                    myBuffer.clear();
                }
                result.set(List.copyOf(collected));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (java.util.concurrent.TimeoutException e) {
                throw new IllegalStateException(e);
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Consumed: " + result.get());
    }
}
```

```bash
javac ExchangerBufferDemo.java
java ExchangerBufferDemo
```

Stdout nếu cả ba round thành công:

```text
Consumed: [1, 2, 3]
```

**Chứng minh dữ liệu và ownership:**

1. Hai phía khởi tạo hai `ArrayList` khác nhau.
2. Producer thêm đúng một số vào **buffer mà nó đang sở hữu**, rồi đổi cho consumer.
3. Consumer nhận buffer chứa số đó, copy vào `collected`, rồi `clear()` trước lần trao đổi kế tiếp.
4. Producer nhận buffer phía consumer đã đưa và chuẩn bị điền số tiếp theo.
5. Mỗi vòng dùng đúng một swap ở cả hai phía, nên order các số trong `collected` là 1, 2, 3, dù scheduler thay đổi.
6. `List.copyOf` tạo bản kết quả không cho sửa cấu trúc sau khi consumer hoàn tất.
7. Main dùng `join` để đợi cả hai worker và đọc kết quả.

**Điều kiện sử dụng thực tế:** ở nhánh timeout/interrupt, phải đặt policy xem buffer nào còn sở hữu ở bên nào, worker còn cần cleanup gì và có nên dừng cả pipeline. Ví dụ tập trung vào đường chạy bình thường và ghi nhận lỗi đơn giản. Đừng dùng vòng `while(true)` không deadline với Exchanger nếu peer có thể chết.

## 17. Backpressure có, nhưng không phải queue có capacity

Nếu producer có thể tạo 100 buffer trong 1 giây còn consumer chỉ xử lý 1 buffer/giây, dùng `Exchanger` khiến producer thường phải chờ consumer tại mỗi round. Cơ chế này hạn chế số buffer "đang bay" theo **giao thức hai buffer**.

Nhưng nó không tương đương `ArrayBlockingQueue<>(2)`:

- `BlockingQueue` có **storage slots** cho các item theo API `put`/`take`.
- `Exchanger` là **rendezvous**: mỗi thread đều phải cung cấp item và nhận item.
- Queue hỗ trợ một chiều producer gửi item, consumer nhận; Exchanger hỗ trợ đổi hai chiều trong cùng synchronization point.
- Queue có thể có nhiều producers/consumers và policy dung lượng cụ thể; Exchanger ghép cặp chờ, không quản lý một danh sách item đã gửi.
- Nếu muốn producer gửi mà không cần consumer có item riêng để đổi, queue thường dễ mô hình hóa hơn.
- Nếu cần gửi kèm trả lại buffer dùng lại, Exchanger có thể giảm chuyện copy/allocation và làm rõ ownership.

Chọn công cụ dựa trên **giao thức truyền dữ liệu**, không chỉ vì cả hai đều có blocking.

## 18. `Exchanger` so với `SynchronousQueue`

Javadoc mô tả Exchanger giống một biến thể **hai chiều** của `SynchronousQueue`.

| Tiêu chí | `Exchanger<T>` | `SynchronousQueue<T>` |
| --- | --- | --- |
| Phương thức chính | `exchange(item)` | `put(item)` / `take()` |
| Hướng dữ liệu | Cả hai thread gửi và nhận trong một lần | Một thread put, một thread take |
| Cặp đồng bộ | Hai callers của exchange được ghép | Producer và consumer rendezvous |
| Có lưu backlog không? | Không | Không, queue dung lượng 0 |
| Trả object của đối tác? | Có | Producer `put` không nhận payload ngược từ consumer |
| Có timeout/interrupt? | Có | Có ở các overload thích hợp |
| Có nên dùng cho request–response đa client? | Chỉ khi pairing/round protocol được kiểm soát | Thường cần thêm correlation/future/queue phù hợp |

Cả hai là công cụ synchronization, không tự tạo durability hay bảo đảm processing của remote service.

Nếu chỉ muốn **handoff một chiều**, `SynchronousQueue` thường làm contract dễ đọc hơn. Nếu muốn **swap buffer hai chiều**, `Exchanger` là lựa chọn trực tiếp.

## 19. `Exchanger` so với `CyclicBarrier`, `CountDownLatch`, `Phaser`

Các synchronizers khác nhau về mục đích:

- **`CountDownLatch`:** một hoặc nhiều thread chờ tới khi số đếm về 0. Không swap dữ liệu; không reset được.
- **`CyclicBarrier`:** N bên chờ nhau ở một mốc; có thể có barrier action. Không mặc định trao đổi payload hai chiều.
- **`Phaser`:** quản lý nhiều phase và đăng ký/rút bớt parties. Phù hợp khi số bên tham gia có thể thay đổi.
- **`Exchanger`:** **ghép hai thread** và trao đổi object ngay tại điểm gặp; không đếm đủ N participants cho một collective barrier.
- **`Semaphore`:** giới hạn số permit, không trực tiếp trao đổi hai object.

Nếu muốn **ba thread cùng gặp nhau rồi tiếp tục**, `CyclicBarrier(3)` hoặc `Phaser` thường đúng hơn Exchanger. Exchanger có thể ghép hai trong ba thread và để thread thứ ba chờ, dẫn đến treo nếu không có thread thứ tư.

## 20. Nhiều hơn hai thread dùng cùng một `Exchanger`

Mặc dù bài học thường có đúng hai thread, một `Exchanger` có thể được nhiều thread gọi. Runtime ghép **từng cặp** cho một lần swap thành công.

Ví dụ có bốn thread A, B, C, D cùng tới:

```text
Possible pairing 1: (A,B), (C,D)
Possible pairing 2: (A,C), (B,D)
Possible pairing 3: (A,D), (B,C)
```

Đây là **các khả năng logic**, không phải phân bố xác suất hay thứ tự được Javadoc cam kết.

Với ba thread đến và không có ai khác, một thread có thể chờ partner mãi nếu không timeout/interrupt. Khi muốn truyền tới **đúng B**, Exchanger dùng chung bởi A, B, C, D **không phải hệ thống định tuyến có địa chỉ**. Chọn instance riêng cho từng cặp cố định hoặc dùng một giao thức có correlation key.

Không nên xem Exchanger như một "broadcast channel" mà mọi bên đều nhận được payload của nhau: mỗi exchange ghép **hai** callers, không multicast.

## 21. Ví dụ Java 17+: bốn thread ghép thành hai cặp

Lưu thành `ExchangerMultiplePairsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Exchanger;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExchangerMultiplePairsDemo {
    public static void main(String[] args) throws InterruptedException {
        Exchanger<String> exchanger = new Exchanger<>();
        CountDownLatch begin = new CountDownLatch(1);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger differentPeer = new AtomicInteger();

        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final String mine = "T" + i;

            workers[i] = new Thread(() -> {
                try {
                    begin.await();
                    String peer = exchanger.exchange(
                            mine, 5, TimeUnit.SECONDS);

                    succeeded.incrementAndGet();
                    if (!mine.equals(peer)) {
                        differentPeer.incrementAndGet();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } catch (java.util.concurrent.TimeoutException e) {
                    throw new IllegalStateException(e);
                }
            }, mine);
            workers[i].start();
        }

        begin.countDown();
        for (Thread thread : workers) {
            thread.join();
        }

        System.out.println("Successful threads: " + succeeded.get());
        System.out.println("Got other thread's item: "
                + differentPeer.get());
    }
}
```

```bash
javac ExchangerMultiplePairsDemo.java
java ExchangerMultiplePairsDemo
```

**Stdout trong trường hợp cả bốn thread ghép thành công trong deadline:**

```text
Successful threads: 4
Got other thread's item: 4
```

Không in ra danh tính partner cụ thể, vì pairing (T0/T1, T0/T2 hay T0/T3) **không xác định**. Kết quả logic ổn định: mỗi thread thành công nhận một item từ thread khác, không phải item chính nó gửi. Dữ liệu `mine` của từng worker là unique string; không có thread nào cố tình gửi item trùng nhau.

Nếu hệ thống bị đình trệ quá 5 giây, thread có thể timeout nên số lượng successful nhỏ hơn; bài không hứa hard scheduling deadline. Trong production, cần thu thập lỗi từ workers và phối hợp shutdown/cancellation để không bỏ sót task thất bại.

## 22. Pairing không phải FIFO, công bằng hay định tuyến

Không nên viết code dựa trên các giả định:

- Thread gọi `exchange` sớm nhất chắc ghép với thread gọi tiếp theo theo FIFO tuyệt đối.
- Thread A chắc chỉ ghép với B dù còn C, D cùng dùng exchanger.
- Sau khi một bên timeout, retry của nó luôn ghép đúng "lượt" với peer cũ.
- Một thread sẽ chắc được partner trong thời hạn cố định chỉ vì nhiều thread khác tồn tại.
- Pairing order tương ứng task ID, request ID hoặc timestamp.

`Exchanger` không cung cấp một fairness parameter như một số lock/queue. Lịch pairing và thời gian chờ có thể chịu scheduler, contention và các chi tiết runtime. Nếu cần **công bằng hoặc partner identity**, thiết kế tầng application hoặc chọn công cụ phù hợp.

Với hai threads cố định, việc mỗi thread gọi **một lần/round** dễ suy luận hơn nhiều so với một exchanger toàn cục nhận request của hàng trăm threads không có sequence protocol.

## 23. Timeout, cancel và hiện tượng lệch phiên

Tình huống:

```text
A: muốn đổi dữ liệu round 7
B: còn đang xử lý round 6

A.exchange(round7, 100ms) -> timeout
A quyết định retry round7

B sau đó mới tới exchange(round6)
A retry có thể gặp B round6, dù A tưởng B đã tới round7
```

Exchanger chỉ biết **có hai callers đang chờ**. Nó không kiểm tra các payload có cùng round ID. Do đó, **timeout của một round là vấn đề protocol**, không chỉ là một exception để log.

Một cách xử lý khi pair cố định:

1. Thỏa thuận rằng timeout/interrupt nghĩa là **hủy toàn bộ phiên**, không tự retry một phía.
2. Nếu cần retry, có handshake/sequence ID và cơ chế phục hồi trạng thái ở **cả hai bên**.
3. Không áp dụng side effect dựa trên payload vừa nhận nếu `roundId` không khớp.
4. Không dùng một exchanger chung cho các phiên độc lập nếu có nguy cơ ghép chéo.
5. Quy định timeout từng round và timeout tổng thể để worker không chờ vô hạn sau failure.
6. Dùng resource close/cancellation token phù hợp nếu worker đang block ở nơi khác trước exchange.

Đừng tưởng `exchange(x, timeout)` có "rollback protocol" giữa nhiều lần trao đổi. Nó chỉ quyết định kết quả **của một lời gọi**.

## 24. Khi một phía ném exception trước exchange

Giả sử producer gặp exception ở `fillBuffer()` và rời thread, còn consumer vẫn gọi:

```java
Buffer next = exchanger.exchange(emptyBuffer);
```

Đây là snippet minh họa với `Buffer`/`emptyBuffer` giả định. Consumer có thể **đợi mãi** vì không còn producer.

Giải pháp:

- Dùng timed `exchange` và kiểm tra timeout.
- Khi một phía thất bại, gửi **cancellation signal riêng** (token/interrupt) đến phía còn lại.
- Định nghĩa states `RUNNING`, `STOPPING`, `STOPPED` và cleanup ownership.
- Không dựa vào `finally` của worker lỗi để tự "mở exchanger": Exchanger **không có `countDown` hay `close`**.
- Nếu chỉ có hai worker, caller điều phối có thể dùng `Future` để quan sát thất bại của một bên rồi `cancel(true)` bên còn lại theo hợp đồng executor thích hợp.
- Nếu một buffer đã được chuyển quyền sở hữu, tránh hai bên cùng cleanup/mutate buffer đó khi failure xảy ra.

Mẫu callback lỗi cần chú ý: nếu một thread timeout và rời đi, thread khác có thể vẫn ở lượt exchange tương ứng và phải được wake bằng interrupt hoặc timeout riêng.

## 25. `Exchanger` có thể truyền null hay không?

Tham số generic `T` là một reference type. `Exchanger` không biến `null` thành một token có định danh nghiệp vụ; một lời gọi có thể cần truyền **không có object** theo protocol của hai bên.

Trong code muốn dễ đọc, nên ưu tiên một **message type tường minh**:

```java
record Envelope(long round, String status, String payload) {}

Exchanger<Envelope> exchanger = new Exchanger<>();
```

Đây là snippet minh họa Java 17, không có `main`. Nếu muốn biểu thị "không có payload", dùng `status` hoặc một sealed hierarchy/enum phù hợp. Tránh dùng null như tín hiệu **END** mà không document, vì receiver sẽ khó phân biệt kết thúc bình thường, thiếu dữ liệu hay lỗi logic.

Một object được swap có thể chứa null field theo hợp đồng của object đó; thread safety vẫn phụ thuộc ownership và publication. **Không dựa vào null để điều phối vòng đời**, nhất là khi có retry hoặc nhiều round.

## 26. Generics và type safety

`Exchanger<T>` xác định compile-time type của object trao đổi:

```java
Exchanger<String> strings = new Exchanger<>();
Exchanger<byte[]> byteBuffers = new Exchanger<>();
Exchanger<java.util.List<Integer>> batches = new Exchanger<>();
```

Những declaration này hợp lệ trong method hoặc field scope thích hợp. Java compiler ngăn lời gọi:

```java
strings.exchange(123); // Không biên dịch: Integer không phải String.
```

Đây là **anti-example cố ý không biên dịch**; method còn khai báo `InterruptedException`.

**Generics không deep-copy object:** `byte[]` hoặc `ArrayList` vẫn mutable. Generic type giúp giảm lỗi trộn loại payload, nhưng không thay ownership contract hay cơ chế matching theo round ID.

Nếu cần trao đổi hai **loại** dữ liệu khác nhau trong cùng cặp, đóng gói trong một common supertype/record/interface hoặc dùng wrapper:

```java
record SwapMessage(String sender, int round, byte[] payload) {}
```

Thiết kế loại message theo business contract để tránh ép cast không an toàn. Với record chứa `byte[]`, record là shallow immutable: array bên trong vẫn mutable; phải copy hoặc chuyển ownership an toàn.

## 27. Với executor, ai là người quản lý vòng đời?

`Exchanger` không tạo hay đóng thread. Nếu chạy hai `Runnable` qua `ExecutorService`, cần:

- Pool có đủ khả năng **cho cả hai phía tới exchange**. Một pool fixed single-thread chạy hai task, task thứ nhất chờ exchange và chiếm worker, task thứ hai không được chạy: có thể bị treo.
- **Quan sát lỗi của cả hai tasks**, ví dụ dùng `Future.get` hoặc result channel; ném exception trong worker không tự bảo đảm caller biết.
- Có deadline hoặc cancellation policy cho exchange.
- Nếu hủy một phía bằng `Future.cancel(true)`, phía kia vẫn cần được đánh thức/timeout nếu không có partner mới.
- `shutdownNow` thường yêu cầu interrupt các worker; không bảo đảm arbitrary blocking I/O hoặc user code dừng tức thì.
- Không chia sẻ một exchanger chung giữa nhiều application sessions mà không quản lý pairing rõ.

Ví dụ anti-pattern:

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> exchanger.exchange("A"));
pool.submit(() -> exchanger.exchange("B"));
```

Đây là snippet minh họa, cố ý bỏ phần handle checked exception. Hai task cần cùng chạy tới rendezvous, nhưng single worker bị task đầu chặn nên task thứ hai nằm trong queue. Dùng ít nhất hai worker phù hợp, hoặc thiết kế không yêu cầu hai tasks chiếm worker cùng lúc. Đừng coi việc tăng pool size là cách sửa mọi vấn đề: nếu một task không bao giờ đến exchange, thêm workers vẫn không tạo partner.

## 28. Tránh giữ khóa khi chờ `exchange()`

Một lỗi nguy hiểm:

```java
synchronized (lock) {
    exchanger.exchange(myBuffer);
}
```

Đây là snippet minh họa; thiếu xử lý `InterruptedException`.

Nếu partner phải **lấy cùng monitor `lock`** để chuẩn bị payload rồi mới exchange, sẽ có vòng phụ thuộc:

```text
Thread A: giữ lock -> chờ partner tại exchange
Thread B: chờ lock  -> không thể đến exchange
```

Đó là deadlock do tổ chức lock ordering, không phải lỗi riêng của Exchanger. Tương tự với `ReentrantLock`, semaphore permit hoặc transaction lock đang giữ qua blocking exchange.

**Quy tắc:** chuẩn bị payload và bảo vệ state cần thiết ở một vùng lock ngắn, **nhả lock trước khi chờ partner**, rồi áp dụng kết quả theo giao thức thích hợp. Nếu cần update atomic với kết quả swap, phải thiết kế protocol không tạo vòng chờ hoặc dùng một primitive khác.

## 29. Exchanger và virtual threads

Trong các phiên bản Java có virtual threads (từ Java 21 ở trạng thái ổn định), `Exchanger` vẫn là API phối hợp thread theo hợp đồng Java SE. Tuy nhiên, **Exchanger không tự giải quyết deadlock logic**: nếu chỉ một bên tới, nó vẫn cần partner, timeout hoặc interrupt.

Bài học này dùng **Java 17+** với platform threads để runnable examples hoạt động trên JDK 17. Không phụ thuộc virtual thread APIs hoặc những điều kiện implementation cụ thể của scheduler virtual threads.

Nếu dùng virtual threads ở Java mới hơn, vẫn phải xem xét ownership mutable buffer, exception propagation, multiple rounds và match identity. Đừng nghĩ virtual threads rẻ hơn nghĩa một task có thể đợi partner vô hạn mà không ảnh hưởng lifecycle của ứng dụng.

## 30. Các sai lầm thường gặp

**1. "`exchange` là gửi item vào queue."** Sai. Nó là rendezvous hai chiều; cần partner để thành công.

**2. "Một thread có thể gọi exchange một mình rồi nhận lại chính item."** Không có partner thì block/timeout/interrupt; không tự complete bằng item chính mình.

**3. "Exchanger luôn ghép hai thread có tên A và B."** Không. Khi nhiều callers dùng cùng instance, partner pairing không được cố định bởi tên thread.

**4. "`exchange` tạo thread còn thiếu."** Sai. Người dùng phải khởi tạo/submit những tasks thực sự tham gia.

**5. "Bản có timeout luôn ném khi timeout bằng 0."** Không tuyệt đối. Nếu partner đã chờ sẵn, có thể ghép ngay; không chờ partner mới khi hết budget.

**6. "Timeout tự interrupt phía đối tác."** Sai. Timeout thuộc lời gọi hiện tại; peer cần protocol hủy riêng.

**7. "Interrupt status vẫn bật trong catch InterruptedException."** Theo contract của `exchange`, status đã được clear khi ném; nếu không thể propagate và muốn bảo toàn tín hiệu hủy, restore.

**8. "Exchanger copy ArrayList/buffer."** Sai. Nó swap references; object vẫn mutable.

**9. "Swap xong producer vẫn tự do sửa buffer đã gửi."** Sai với ownership handoff; có thể tạo data race.

**10. "happens-before nghĩa không cần đồng bộ bất kỳ mutation nào về sau."** Sai. Nó bảo đảm ordering/visibility cho hành động trước exchange thành công và hành động sau tương ứng, không khóa những thao tác tương lai.

**11. "Có ba threads gọi exchange thì cả ba đều xong."** Không có collective barrier cho ba; một thread có thể còn chờ.

**12. "Exchanger có FIFO và fairness mặc định."** Không có guarantee fairness/partner ordering như vậy trong public API.

**13. "Hai round dùng chung exchanger luôn đúng dù một bên retry hoặc bỏ lượt."** Không. Cần sequence/cancellation protocol để không ghép lệch round.

**14. "Nếu producer crash, consumer sẽ tự nhận tín hiệu end."** Không. Exchanger không có built-in close/EOF; dùng timeout/interrupt và lifecycle signals.

**15. "Pool một worker có thể chạy hai blocking exchange tasks."** Dễ deadlock/starvation nếu task đầu chờ task thứ hai chưa được chạy.

**16. "Dùng `synchronized` bao quanh `exchange` luôn an toàn."** Không nếu peer cần monitor đó để tới exchange.

**17. "Exchanger thay thế toàn bộ queue, barrier, phaser."** Không. Mỗi loại có mục tiêu synchronization riêng.

**18. "Một exchange thành công nghĩa consumer đã xử lý xong payload."** Không. Nó chỉ xác nhận việc trao đổi references theo pair, không xác nhận nghiệp vụ phía nhận đã commit.

**19. "Có thể retry mọi exchange vô hạn khi TimeoutException."** Nguy cơ retry lệch phiên hoặc giữ resources vô hạn; thiết kế deadline chung và correlation ID.

**20. "Generic type T làm object được trao đổi immutable."** Không. Mutable payload vẫn cần ownership và synchronization.

## 31. Checklist triển khai `Exchanger<T>`

Trước khi đưa vào production:

1. **Có thật sự là hai chiều không?** Nếu chỉ gửi một chiều, cân nhắc `BlockingQueue`/`SynchronousQueue`.
2. **Một lần exchange có chính xác hai participants mong muốn không?** Nếu nhiều threads cùng dùng, xác định pairing policy.
3. **Có giữ cùng instance exchanger không?** Hai instances khác nhau không ghép với nhau.
4. **Đối tác có chắc sẽ tới exchange theo mọi đường execution không?** Kể cả exception/early return.
5. **Có timeout hoặc cancellation plan không?** Tránh chờ vô hạn khi peer chết.
6. **Có xử lý `InterruptedException` đúng không?** Propagate nếu có thể, nếu không restore rồi dừng.
7. **Timeout có hủy cả phiên hay retry không?** Không retry một phía theo cảm tính.
8. **Có sequence ID/correlation ID cho nhiều round không?** Chặn ghép lệch lượt.
9. **Có quy tắc ownership mutable payload không?** Đừng dùng lại reference đã gửi cho partner.
10. **Object nhận có đúng lifecycle không?** Buffer đã được clear, có thể sử dụng lại và không bị bên kia sửa?
11. **Có kiểm tra missing partner?** Test một thread bị cancel trước khi tới rendezvous.
12. **Có shared lock được giữ khi exchange không?** Tránh dependency deadlock.
13. **Executor có đủ worker để hai phía tiến tới exchange không?** Single-thread fixed pool thường không đủ.
14. **Có test nhiều callers và pairing ngẫu nhiên không?** Không hardcode rằng T0 luôn ghép T1.
15. **Có log success/failure/timeouts và thời gian chờ không?** Quan sát latency, nhưng không lẫn scheduling delay với bug.
16. **Có test JMM visibility bằng pattern đúng không?** Ghi trước swap, đọc sau swap; tránh concurrent mutation sau bàn giao.
17. **Ai chịu trách nhiệm shutdown?** Exchanger không có close; stop threads/tasks theo owner.
18. **Có cần exactly-once processing hoặc durability không?** Exchanger không cung cấp transaction log/ack business.
19. **Có hạn chế memory/resource không?** Không giữ buffer rất lớn vô hạn trong vòng exchange.
20. **Có fallback khi peer chậm không?** Chọn deadline, token, queue khác hoặc kết thúc pipeline có kiểm soát.

## 32. Câu hỏi tự kiểm tra

**Câu 1:** `Exchanger<String>` có phải queue chứa String không?

**Không.** Nó là điểm rendezvous: một caller đưa String vào và chờ peer đưa String khác để swap.

**Câu 2:** A gửi "X", B gửi "Y". A và B nhận gì khi thành công?

A nhận "Y", B nhận "X". Không có bảo đảm thứ tự hai thread tiếp tục sau khi swap.

**Câu 3:** Nếu chỉ A gọi `exchange("X")` và B không bao giờ tới?

A có thể chờ vô hạn nếu không bị interrupt; nếu dùng timed overload có thể nhận `TimeoutException`.

**Câu 4:** `exchange(x, timeout)` ném `TimeoutException` có gửi cancellation đến B?

Không. Timeout chỉ báo A không ghép được trong thời hạn; B phải có tín hiệu hoặc timeout riêng.

**Câu 5:** `exchange` với một mutable buffer có tạo deep copy không?

Không. Hai bên swap references. Quy tắc ownership phải ngăn sửa đồng thời sau bàn giao.

**Câu 6:** Ghi `payload.number=42` trước swap và partner đọc sau swap thành công có visibility phù hợp không?

Có, theo memory consistency effect được Javadoc quy định cho cặp exchange thành công, miễn không có mutation cạnh tranh không đồng bộ phá contract.

**Câu 7:** Có ba thread A/B/C dùng một exchanger; tất cả chắc chắn qua exchange không?

Không. Hai thread có thể ghép một cặp, thread còn lại chờ partner thứ tư hoặc timeout/interrupt.

**Câu 8:** Exchanger có tự xác định partner theo ID không?

Không. Khi nhiều callers dùng chung, cần instance theo cặp hoặc protocol định tuyến/correlation bên ngoài.

**Câu 9:** Producer gửi buffer đầy rồi ngay lập tức `clear()` buffer vừa gửi có an toàn không?

Không. Consumer có thể đang đọc cùng object. Producer chỉ được clear **buffer mới nhận** mà nó sở hữu.

**Câu 10:** Hai exchange tasks submit vào `Executors.newSingleThreadExecutor()` có thể bị gì?

Task thứ nhất block chờ partner, task thứ hai nằm trong queue và không thể bắt đầu; có thể dẫn đến không tiến triển.

**Câu 11:** `InterruptedException` từ `exchange` có phải signal phải luôn bỏ qua cho task chạy tiếp không?

Không. Thường nên propagate, hoặc restore flag rồi dừng theo cancellation contract nếu ở ranh giới `Runnable`.

**Câu 12:** Khi nào `Exchanger` hợp hơn `SynchronousQueue`?

Khi **hai phía đều có một object để trao đổi**, đặc biệt khi hoán đổi buffer đầy/trống. Với truyền một chiều, `SynchronousQueue` thường rõ hơn.

**Câu 13:** Có thể tạo một global exchanger rồi dùng cho tất cả client request–response không?

Chỉ khi pairing không quan trọng hoặc có protocol riêng bảo vệ nó. Nếu yêu cầu response đúng request, Exchanger chung không tự cung cấp routing theo ID.

**Câu 14:** `CountDownLatch` và Exchanger khác gì?

Latch đợi một đếm/sự kiện, không swap payload. Exchanger ghép hai callers để trao đổi object.

**Câu 15:** Có nên nắm `ReentrantLock` trong lúc chờ exchange nếu partner cần lock đó để chuẩn bị item?

Không. Dễ tạo vòng phụ thuộc dẫn tới deadlock.

**Câu 16:** Một cặp trao đổi thành công có chứng minh phía nhận đã làm xong nghiệp vụ trên payload không?

Không. Nó xác nhận swap, không xác nhận downstream processing success hay commit. Muốn ack cần giao thức bổ sung.

## 33. Tổng kết

- **`Exchanger<T>` trao đổi object theo từng cặp thread**, không lưu hàng đợi, không broadcast và không tự tạo thread.
- **`exchange(x)`** chờ một partner, swap và trả object của partner; **`exchange(x, timeout, unit)`** thêm giới hạn thời gian và `TimeoutException`.
- **`InterruptedException`** là đường hủy hợp tác; phương thức exchange clear status khi ném, nên không được catch rỗng nếu cần giữ yêu cầu dừng.
- **Happens-before** giữa hành động trước exchange thành công và hành động sau exchange ở thread đối tác giúp **công bố payload đã chuẩn bị xong**, nhưng không tự bảo vệ mutation sau bàn giao.
- Use case đặc trưng là **đổi buffer đầy/trống**, giảm allocation và làm rõ ownership trong producer–consumer hai giai đoạn.
- Với nhiều threads, Exchanger chỉ **ghép từng cặp**, không bảo đảm partner identity, fairness, FIFO hoặc collective synchronization cho N threads.
- **Timeout, exception hoặc missed round** có thể làm lệch protocol; cần sequence ID, deadline, cancellation và cleanup rõ khi dùng nhiều lượt.
- **`SynchronousQueue` thích hợp hơn cho handoff một chiều; `CountDownLatch`/`CyclicBarrier`/`Phaser` phù hợp các mẫu chờ khác.**
- Không chờ exchange trong lúc giữ monitor/lock mà partner cần; không chạy hai blocking tasks trên executor chỉ có một worker.
- Một lần swap thành công không phải transaction, acknowledgment xử lý nghiệp vụ hay bảo đảm durable delivery.

**Tự kiểm tra thiết kế:** *"Ai là partner, hai bên gửi object gì, mỗi bên đang sở hữu buffer nào, và khi một phía không bao giờ tới điểm exchange thì bên kia có thể thoát/cleanup thế nào?"* Nếu trả lời được bốn câu hỏi ấy, `Exchanger<T>` có thể là công cụ rất rõ ràng cho giao thức trao đổi dữ liệu hai chiều trong Java concurrency.

**Tham khảo chính thức:** [Java SE 17 — Exchanger Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Exchanger.html).