# Thứ tự happens-before trong Java Memory Model

## 1. Vấn đề: chạy trước theo thời gian chưa đủ để chia sẻ dữ liệu

Hai luồng cùng truy cập một biến có thể không quan sát dữ liệu theo trực giác “luồng kia vừa ghi xong nên tôi phải đọc thấy”.

Ví dụ minh họa chưa đúng giao thức:

```java
class Message {
    int data;
    boolean ready;

    void publish() {
        data = 42;
        ready = true;
    }

    int consume() {
        while (!ready) {
            // Chờ bằng một biến thường là không đủ.
        }
        return data;
    }
}
```

Nếu publish và consume chạy trên hai luồng mà không có cơ chế đồng bộ khác, mã không có bảo đảm về việc nhìn thấy ready/data theo mong muốn. Không nên dựa vào sleep, tốc độ CPU hoặc số lần thử chưa thất bại để coi nó đúng.

Java Memory Model (JMM) dùng quan hệ **happens-before**, thường viết hb, để mô tả những thứ tự quan sát được ngôn ngữ bảo đảm giữa các hành động.

Đây là quy tắc hiện hành của Java. Bài sử dụng cú pháp và API chạy được trên Java 17+.

## 2. Happens-before bảo đảm điều gì?

Nếu hành động ghi W happens-before một lần đọc R của cùng biến, và không có lần ghi khác phù hợp chen vào làm thay đổi kết quả, R phải quan sát giá trị theo các ràng buộc của JMM; nó không được tùy tiện bỏ qua W để đọc giá trị cũ hơn.

Điểm thực dụng thường dùng là **công bố dữ liệu**:

```text
luồng ghi:    ghi dữ liệu ──→ hành động công bố
                                      │
                              cạnh đồng bộ hóa
                                      │
luồng đọc:                    hành động nhận ──→ đọc dữ liệu
```

Kết hợp thứ tự trong từng luồng với cạnh đồng bộ hóa tạo đường happens-before từ ghi dữ liệu tới đọc dữ liệu.

Không nên hiểu hb là một phép đo thời gian:

- Nó là một quan hệ thứ tự bộ phận, không xếp mọi cặp hành động trong chương trình thành một hàng duy nhất.
- Hai hành động không có đường hb vẫn có thể thực tế xảy ra một cái trước một cái.
- Có đường hb không có nghĩa hai hành động phải sát nhau về thời gian.
- Trình biên dịch/JVM có thể tối ưu cách thực thi miễn không tạo hành vi quan sát trái các ràng buộc của mô hình.

Giải thích chỉ bằng “xóa cache CPU” là quá hẹp. JMM là hợp đồng của ngôn ngữ, bao gồm cả tối ưu của trình biên dịch/JVM và những giá trị một lần đọc được phép thấy.

## 3. Các cạnh happens-before thường dùng

| Quy tắc | Đường bảo đảm |
| --- | --- |
| Thứ tự trong một luồng | Hành động trước trong thứ tự chương trình hb hành động sau |
| Monitor | Unlock một monitor hb lần lock sau đó trên cùng monitor |
| Volatile | Ghi một biến volatile hb lần đọc sau đó của cùng biến volatile theo thứ tự đồng bộ hóa |
| Thread.start | Hành động gọi start hb các hành động trong luồng được bắt đầu |
| Kết thúc luồng và join | Các hành động trong luồng hb luồng khác tiếp tục sau khi join xác nhận luồng đó đã kết thúc |
| Khởi tạo mặc định | Ghi giá trị mặc định cho biến có các bảo đảm khởi tạo do JMM quy định |
| Bắc cầu | Nếu A hb B và B hb C thì A hb C |

Quy tắc quan trọng là **cùng đối tượng đồng bộ** hoặc **cùng biến volatile**. Unlock khóa A không tự tạo bảo đảm với lock khóa B; ghi flagA không tự nối với một lần đọc flagB chỉ vì cả hai đều volatile.

Start cũng là một chiều: những hành động trước khi start được công bố cho luồng mới. Mọi sửa đổi tùy ý của luồng cha sau start không tự được bảo vệ bởi lần start đã xảy ra.

Join có ý nghĩa khi nó xác nhận luồng đã kết thúc. Một lời gọi join có thời hạn trả về do hết thời gian trong khi luồng còn chạy không tạo cam kết rằng công việc của luồng đã hoàn tất.

## 4. Bắc cầu là chìa khóa để công bố biến thường

Sửa ví dụ đầu:

```java
class PublishedMessage {
    int data;
    volatile boolean ready;

    void publish() {
        data = 42;
        ready = true;
    }

    int consume() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return data;
    }
}
```

Giả sử có một lần publish, một bên consume và không có lần ghi data khác:

1. Ghi data = 42 đứng trước ghi ready = true trong luồng sản xuất.
2. Ghi volatile ready = true đồng bộ với việc luồng đọc quan sát ready theo quy tắc volatile.
3. Lần đọc ready thành công đứng trước đọc data trong luồng tiêu thụ.
4. Bắc cầu tạo đường hb từ ghi data tới đọc data.

Vì vậy data không bắt buộc cũng là volatile trong giao thức một lần công bố này. Sự bảo đảm đến từ toàn bộ đường hb, không phải chỉ từ bản thân biến data.

Ngược lại, không đặt ready = true trước khi hoàn tất dữ liệu cần công bố. Những lần ghi data sau cạnh công bố không tự được đưa vào bảo đảm trên.

Thread.onSpinWait chỉ là gợi ý cho vòng chờ chủ động, không phải cơ chế công bố bộ nhớ. Nó không thay thế volatile. Trong ứng dụng thực, latch, hàng đợi chờ hoặc cơ chế đồng bộ cấp cao thường diễn đạt việc chờ rõ hơn và tránh chiếm CPU của vòng quay.

## 5. Monitor: phải cùng một khóa và cùng giao thức

Ví dụ minh họa:

```java
class LockedMessage {
    private final Object lock = new Object();
    private int data;

    void write() {
        synchronized (lock) {
            data = 42;
        }
    }

    int read() {
        synchronized (lock) {
            return data;
        }
    }
}
```

Nếu write đã unlock trước khi read lock cùng monitor, đường hb nối ghi data tới đọc data.

Tuy nhiên, hai khối synchronized không bảo đảm write phải diễn ra trước read. Nếu read lấy khóa trước khi write chạy, kết quả 0 vẫn có thể đúng theo giao thức này. Khóa bảo vệ truy cập và công bố qua thứ tự khóa; nó không tự tạo điều kiện “đợi tới khi đã có dữ liệu”.

Nếu cần đợi một trạng thái, phải bổ sung điều kiện chờ hoặc cơ chế phối hợp phù hợp. Cũng không để một phương thức ngoài giao thức đọc/ghi data trực tiếp mà không dùng cùng khóa.

## 6. Chương trình đầy đủ: start, join, volatile và latch

Lưu thành `HappensBeforeDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class HappensBeforeDemo {
    static final class State {
        int input;
        int result;
    }

    static final class Publication {
        int data;
        volatile boolean ready;
    }

    public static void main(String[] args) throws InterruptedException {
        State state = new State();
        state.input = 7;

        Thread worker = new Thread(() -> {
            state.result = state.input * 6;
        });

        worker.start();
        worker.join();

        System.out.println("start and join=" + state.result);

        Publication publication = new Publication();
        int[] observed = new int[1];

        Thread reader = new Thread(() -> {
            while (!publication.ready) {
                Thread.onSpinWait();
            }
            observed[0] = publication.data;
        });

        Thread writer = new Thread(() -> {
            publication.data = 42;
            publication.ready = true;
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();

        System.out.println("volatile publication=" + observed[0]);

        State latched = new State();
        CountDownLatch available = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            try {
                available.await();
                latched.result = latched.input;
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                failure.set(exception);
            }
        });

        Thread producer = new Thread(() -> {
            latched.input = 99;
            available.countDown();
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();

        if (failure.get() != null) {
            throw new AssertionError("Consumer interrupted", failure.get());
        }

        System.out.println("latch publication=" + latched.result);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 HappensBeforeDemo.java
java HappensBeforeDemo
```

Kết quả:

```text
start and join=42
volatile publication=42
latch publication=99
```

Giải thích:

- input = 7 trước worker.start được công bố cho worker; kết quả worker ghi được main đọc sau join.
- data = 42 được công bố cho reader qua volatile ready. Main đọc observed sau reader.join.
- input = 99 được công bố qua countDown tới phần tiếp tục sau await thành công. Main đọc result sau consumer.join.

Không dùng stdout của một chương trình thiếu đồng bộ để chứng minh mô hình. Chương trình này có các đường hb được phân tích; chạy chỉ giúp kiểm tra ví dụ đã viết đúng và có output phù hợp.

## 7. Đồng bộ cấp cao cũng có hiệu ứng bộ nhớ được quy định

Các API trong java.util.concurrent công bố các quan hệ bộ nhớ cụ thể, ví dụ:

- CountDownLatch: các hành động trước countDown hb các hành động sau await thành công khi điều kiện latch được đáp ứng.
- Executor: các hành động trước khi gửi tác vụ hb việc thực thi tác vụ theo hợp đồng.
- Future: công việc của phép tính hb việc quan sát kết quả sau Future.get thành công theo hợp đồng.
- Các concurrent collection/hàng đợi có quy tắc công bố phần tử giữa bên đưa vào và bên nhận.

Không nên rút gọn thành “gọi bất kỳ API concurrent nào là mọi dữ liệu sẽ đồng bộ”. Phải tìm đúng thao tác gửi/nhận, đúng đối tượng phối hợp và chiều bảo đảm.

Ví dụ, gọi size trên một collection khác không phải một hàng rào bộ nhớ tổng quát cho một biến nghiệp vụ không liên quan.

## 8. Happens-before không tự làm thao tác nhiều bước thành nguyên tử

Ví dụ:

```java
volatile int count;

// Ở nhiều luồng:
// count++;
```

count++ gồm đọc, tính và ghi. Volatile bảo đảm các quy tắc nhìn thấy/thứ tự cho các lần truy cập, nhưng không gộp toàn bộ chuỗi thành một thao tác tăng nguyên tử. Hai luồng vẫn có thể đọc cùng giá trị rồi ghi cùng kết quả, làm mất một lần tăng.

Nếu cần tăng nguyên tử, cân nhắc AtomicInteger.incrementAndGet hoặc bảo vệ chuỗi cập nhật bằng cùng khóa.

Tương tự, một collection có thao tác an toàn luồng không tự làm chuỗi “kiểm tra rồi hành động” nguyên tử. Happens-before, loại trừ tương hỗ và tính nguyên tử liên quan nhau nhưng không phải một khái niệm duy nhất.

## 9. Data race và những giới hạn của việc suy luận

Hai truy cập xung đột vào cùng một biến, trong đó có ít nhất một lần ghi, tạo data race nếu không được sắp thứ tự bằng hb theo quy tắc JMM.

Thiếu đường hb không có nghĩa chắc chắn mỗi lần chạy đều đọc giá trị cũ. Nó có nghĩa chương trình thiếu bảo đảm cần thiết để dựa vào kết quả mong muốn.

Một chương trình được đồng bộ hóa đúng có bảo đảm nhất quán tuần tự theo JMM: có thể lý giải hành vi như một phép xen kẽ phù hợp thứ tự từng luồng. Dù vậy, vẫn có thể sai về logic nghiệp vụ, ví dụ hai thao tác được thực hiện an toàn riêng lẻ nhưng thiếu một ranh giới nguyên tử chung.

Các quy tắc đặc biệt của final field có vai trò riêng trong an toàn khởi tạo. Không suy ra rằng mọi trường thường của đối tượng bất biến theo ý định lập trình viên đều tự có cùng bảo đảm, hoặc rằng tham chiếu final khiến đối tượng được tham chiếu không thể thay đổi.

## 10. Những “cách chờ” không tự tạo đường hb cần thiết

- Thread.sleep không phải phép công bố biến thường giữa hai luồng.
- Thread.yield không thay thế khóa hoặc volatile.
- Thread.onSpinWait không tự sửa vòng lặp đọc biến thường.
- “Tác vụ chắc đã chạy xong vì đã lâu” không thay thế join, get, await hoặc một giao thức đúng.
- In log có thể làm thay đổi lịch thực thi và thêm đồng bộ bên trong công cụ log, nhưng không nên dùng nó làm giao thức công bố dữ liệu nghiệp vụ.

Vì vậy, đừng sửa một lỗi nhìn thấy dữ liệu bằng cách thêm sleep cho đến khi thử thấy đúng. Hãy vẽ đường ghi → công bố → nhận → đọc và xác định cạnh nào còn thiếu.

## 11. Cách phân tích một đoạn mã chia sẻ trạng thái

1. Liệt kê các biến được nhiều luồng truy cập.
2. Với mỗi lần đọc quan trọng, xác định lần ghi nào cần được quan sát.
3. Tìm thứ tự trong từng luồng và các cạnh đồng bộ thực sự.
4. Dùng bắc cầu để nối đường hb.
5. Kiểm tra có các lần ghi khác hoặc các lần dùng lại giao thức làm giả định một lần công bố không còn đúng.
6. Kiểm tra riêng tính nguyên tử, điều kiện chờ và quy tắc kết thúc.

Bài tập: trong PublishedMessage, chuyển `ready = true` lên trước `data = 42`. Chỉ ra vì sao không còn đường hb từ lần ghi data mới tới lần đọc data sau khi thấy ready. Không cần tìm một lần chạy sai cụ thể để nhận ra bảo đảm đã mất.

## Tài liệu đối chiếu

- [JLS §17.4.5 — Happens-before và data race](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).
- [java.util.concurrent — Hiệu ứng nhất quán bộ nhớ](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).
- [CountDownLatch — Công bố dữ liệu qua countDown và await](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
