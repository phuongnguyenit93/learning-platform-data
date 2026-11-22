# Tính nguyên tử, tính hiển thị và thứ tự thực thi giữa các luồng

Khi nhiều luồng cùng truy cập dữ liệu, một chương trình không thể chỉ dựa vào việc các câu lệnh nhìn có vẻ đơn giản hoặc đã được viết theo đúng thứ tự trong tệp nguồn.

Java Memory Model (JMM) quy định những kết quả quan sát được mà chương trình đa luồng được phép có. Ba câu hỏi nền tảng là:

| Khía cạnh | Câu hỏi |
| --- | --- |
| Tính nguyên tử (atomicity) | Thao tác cần xem như một khối có thể bị luồng khác chen vào giữa không? |
| Tính hiển thị (visibility) | Khi một luồng ghi dữ liệu, luồng khác có cơ sở nào để quan sát dữ liệu đó? |
| Thứ tự (ordering) | Những hành động nào được bảo đảm có quan hệ trước–sau đối với việc quan sát giữa các luồng? |

Một công cụ có thể giải quyết một số khía cạnh mà chưa đủ cho toàn bộ bài toán. Ví dụ, `volatile` cung cấp quy tắc hiển thị và thứ tự phù hợp cho biến, nhưng `volatile int count` không làm `count++` thành một lần cập nhật nguyên tử.

## 1. Từ trạng thái chia sẻ đến xung đột

Biến cục bộ nguyên thủy thuộc một lượt gọi phương thức không tự trở thành dữ liệu chia sẻ chỉ vì chương trình có nhiều luồng. Nhưng các luồng có thể giữ tham chiếu đến cùng một đối tượng và đọc/ghi các trường hoặc phần tử mảng của nó.

Hai truy cập xung đột khi cùng truy cập một biến và ít nhất một truy cập là ghi. Nếu các truy cập xung đột giữa các luồng không được sắp thứ tự bằng quan hệ happens-before phù hợp, chương trình có thể có data race.

Cần phân biệt:

- **Data race:** khái niệm của mô hình bộ nhớ về các truy cập xung đột thiếu happens-before.
- **Race condition:** kết quả nghiệp vụ phụ thuộc vào cách các thao tác xen kẽ không được kiểm soát.

Một chuỗi thao tác trên biến volatile vẫn có thể có race condition dù các lần truy cập biến đã có quy tắc đồng bộ. Bảo đảm cho một lần đọc/ghi không tự mở rộng thành bảo đảm cho cả chuỗi kiểm tra–cập nhật.

## 2. Tính nguyên tử: một câu lệnh không nhất thiết là một thao tác không thể chia nhỏ

Xét:

```java
count++;
```

Ở mức ý nghĩa, cần:

1. Đọc giá trị hiện tại.
2. Tính giá trị cộng 1.
3. Ghi kết quả lại.

Nếu hai luồng cùng đọc 0 trước khi một bên ghi, cả hai có thể ghi 1. Hai lượt tăng nhưng kết quả chỉ tăng một lần: cập nhật bị mất.

Mô phỏng:

```text
Luồng A: đọc 0
Luồng B: đọc 0
Luồng A: ghi 1
Luồng B: ghi 1
Kết quả: 1
```

Dù từng lần đọc hoặc ghi `int` là nguyên tử, cả chuỗi vẫn không nguyên tử. Khai báo `volatile int count` không ngăn lịch xen kẽ này.

### Các thao tác đơn và thao tác ghép

| Trường hợp | Điều cần nhớ |
| --- | --- |
| Đọc/ghi một tham chiếu | Nguyên tử, nhưng không tự bảo vệ trạng thái bên trong đối tượng |
| Đọc/ghi đơn với boolean, byte, short, char, int, float | Nguyên tử theo JMM |
| Đọc/ghi long hoặc double không volatile | Đặc tả cho phép trường hợp không nguyên tử; không lấy hành vi một JVM làm bảo đảm chung |
| Đọc/ghi long hoặc double volatile | Có bảo đảm nguyên tử tương ứng |
| `count++`, `count += n` | Là chuỗi đọc–sửa–ghi, không tự nguyên tử |
| `AtomicInteger.incrementAndGet()` | Một cập nhật tăng nguyên tử theo hợp đồng API |
| Hai lần gọi atomic khác nhau | Không tự thành một giao dịch chung |

Tính nguyên tử của gán tham chiếu không có nghĩa đối tượng được công bố an toàn hoặc mọi trường bên trong được nhìn thấy đúng.

## 3. Tính hiển thị: đã ghi không có nghĩa bên khác tự quan sát đúng

Xét ý tưởng chưa đồng bộ:

```java
// Các trường dùng chung, minh họa bên trong một lớp:
int payload;
boolean ready;

// Luồng ghi:
payload = 42;
ready = true;

// Luồng đọc:
// while (!ready) { }
// use(payload);
```

Đây là sơ đồ các thao tác của hai luồng, không phải chương trình hoàn chỉnh để chạy.

Nếu không có cơ chế đồng bộ phù hợp, luồng đọc không có bảo đảm rằng vòng chờ sẽ quan sát lần ghi `ready`, hoặc rằng việc thấy `ready == true` tạo ra quan hệ công bố đúng cho `payload`.

Không nên giải thích bằng một quy tắc máy móc như “mỗi luồng luôn có bản sao riêng” hoặc “volatile luôn bỏ qua mọi cache”. JMM mô tả bảo đảm ngôn ngữ; JVM và phần cứng có thể thực hiện chúng theo nhiều cách.

Điều cần thiết ở mã ứng dụng là xác định cơ chế giao tiếp giữa các luồng, không phải đoán sau bao nhiêu mili giây một cache sẽ “tự cập nhật”.

## 4. Thứ tự: không lấy thời gian quan sát làm quan hệ đồng bộ

Trong một luồng, chương trình phải có hành vi phù hợp với ngữ nghĩa thực thi của luồng đó. Nhưng giữa các luồng, nhìn hai dòng mã theo thứ tự trong nguồn chưa đủ để suy ra mọi luồng đều quan sát chúng theo một thứ tự tương ứng.

Trình biên dịch, JVM và phần cứng có thể tối ưu hoặc tổ chức thực thi khác, miễn kết quả quan sát được tuân thủ JMM.

Điều này không đồng nghĩa mọi thao tác có thể bị đảo tùy ý. Các quy tắc đồng bộ đặt ra giới hạn quan sát cụ thể.

Cũng không thể chứng minh đúng chỉ bằng phát biểu “luồng ghi chắc chạy xong trước vì tôi cho luồng đọc ngủ lâu hơn”. `Thread.sleep` và `Thread.yield` không tự tạo quan hệ công bố dữ liệu cần thiết.

Nếu cần biết một luồng đã hoàn tất và quan sát các tác động của nó, dùng cơ chế có hợp đồng như `join`; nếu cần chờ một sự kiện, dùng công cụ đồng bộ tương ứng.

## 5. Happens-before nối các bảo đảm lại với nhau

Quan hệ happens-before là công cụ để suy luận việc quan sát các ghi giữa các luồng. Nó không phải lời khẳng định rằng mỗi lệnh máy A luôn chạy xong trước mỗi lệnh máy B theo đồng hồ.

Các cạnh nền tảng:

| Cơ chế | Quan hệ cần dùng |
| --- | --- |
| Thứ tự chương trình trong một luồng | Hành động trước happens-before hành động sau theo quy tắc chương trình |
| Cùng một monitor | Unlock monitor happens-before lần lock tiếp sau trên chính monitor đó |
| Cùng một biến volatile | Ghi volatile happens-before lần đọc volatile tiếp sau theo thứ tự đồng bộ |
| `Thread.start()` | Các hành động trước khi start được công bố tới hành động trong luồng được khởi động theo quy tắc này |
| `Thread.join()` thành công | Hành động của luồng kết thúc happens-before việc bên gọi tiếp tục sau khi nhận biết kết thúc qua join |
| Công cụ trong java.util.concurrent | Có các bảo đảm bộ nhớ riêng, ví dụ countDown trước await thành công tương ứng |

Happens-before có tính bắc cầu: nếu A happens-before B và B happens-before C, thì A happens-before C.

### Mẫu công bố bằng cờ volatile

```java
int payload;
volatile boolean ready;
```

Luồng ghi:

```java
payload = 42;
ready = true;
```

Luồng đọc:

```java
if (ready) {
    System.out.println(payload);
}
```

Trong tình huống công bố một lần này, khi bên đọc quan sát cờ true từ lần ghi công bố, có chuỗi:

```text
ghi payload
  -> ghi ready volatile
  -> đọc ready volatile thấy công bố
  -> đọc payload
```

Các quy tắc chương trình, volatile và tính bắc cầu bảo đảm dữ liệu trước cờ được công bố đúng. `payload` không bắt buộc cũng là volatile trong mẫu này.

Điều kiện quan trọng là không có một bên khác tiếp tục sửa `payload` ngoài giao thức đó. Đảo cờ true/false để tái sử dụng một buffer có thể cần một giao thức nhiều bước; không suy từ ví dụ một lần sang mọi bài toán producer–consumer.

## 6. Chương trình kiểm chứng hoàn chỉnh

Ví dụ dùng Java 17+, gồm ba thí nghiệm:

1. Ép hai lượt đọc–sửa–ghi chia nhỏ cùng đọc một giá trị trước khi ghi, để thấy rõ mất cập nhật dù trường là volatile.
2. Dùng phép tăng của `AtomicInteger`.
3. Công bố dữ liệu qua cờ volatile.

Lưu thành `MemoryModelBasicsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class MemoryModelBasicsDemo {
    static final class SplitCounter {
        volatile int value;
    }

    static final class Message {
        int payload;
        volatile boolean ready;
    }

    static void runTwo(Runnable action) throws InterruptedException {
        Thread first = new Thread(action);
        Thread second = new Thread(action);
        first.start();
        second.start();
        first.join();
        second.join();
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SplitCounter split = new SplitCounter();
        CountDownLatch bothRead = new CountDownLatch(2);

        Runnable splitIncrement = () -> {
            int old = split.value;
            bothRead.countDown();
            await(bothRead);
            split.value = old + 1;
        };
        runTwo(splitIncrement);
        System.out.println("split read-modify-write: " + split.value);

        AtomicInteger atomic = new AtomicInteger();
        runTwo(() -> {
            for (int i = 0; i < 10_000; i++) {
                atomic.incrementAndGet();
            }
        });
        System.out.println("atomic increments: " + atomic.get());

        Message message = new Message();
        int[] observed = new int[1];
        Thread reader = new Thread(() -> {
            while (!message.ready) {
                Thread.onSpinWait();
            }
            observed[0] = message.payload;
        });
        Thread writer = new Thread(() -> {
            message.payload = 42;
            message.ready = true;
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();
        System.out.println("published payload: " + observed[0]);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 MemoryModelBasicsDemo.java
java MemoryModelBasicsDemo
```

Stdout khi các luồng hoàn tất bình thường:

```text
split read-modify-write: 1
atomic increments: 20000
published payload: 42
```

### Vì sao kết quả đầu là 1?

Mỗi luồng đọc `split.value` trước khi giảm latch. Cả hai phải tới điểm đó trước khi được phép ghi. Vì vậy, cả hai đã đọc giá trị ban đầu 0, rồi cùng ghi 1.

Đây là cách chủ động tạo một lịch xen kẽ cho chuỗi chia nhỏ. Không có lời khẳng định rằng chạy `volatileCount++` trong mọi chương trình đều phải cho ra một giá trị sai cụ thể. Không phối hợp lịch như thí nghiệm thì số cập nhật bị mất có thể thay đổi theo lần chạy.

Latch dùng để dàn cảnh hai lần đọc, không biến cả thao tác thành nguyên tử. Kết quả chứng minh hai lần ghi volatile riêng lẻ không tạo một phép tăng nguyên tử chung.

### Vì sao hai kết quả sau có cơ sở?

`incrementAndGet` cung cấp phép tăng nguyên tử, nên 20.000 lần tăng đều được tính khi hai luồng hoàn tất. `join` giúp main chờ và có quan hệ quan sát các tác động của luồng trước khi in kết quả.

Ở thí nghiệm công bố, bên đọc chỉ đọc payload sau khi quan sát cờ volatile. Mảng `observed` được reader ghi, rồi main đọc sau `reader.join()`, nên đường truyền kết quả về main cũng có cơ sở happens-before.

`Thread.onSpinWait()` chỉ là gợi ý hỗ trợ vòng chờ bận; nó không cung cấp đồng bộ thay cho volatile. Vòng quay ngắn trong bài dùng để nhìn rõ cơ chế. Khi cần chờ thực tế, công cụ blocking như latch hoặc queue thường tránh tiêu tốn CPU hơn.

JMM không hứa thời gian hoàn tất hay sự công bằng lập lịch. Bài kiểm chứng kết quả đúng khi các luồng chạy và hoàn tất, không suy ra một hạn thời gian luôn được bảo đảm.

## 7. synchronized giải quyết vùng cập nhật và công bố theo cùng khóa

Ví dụ một bộ đếm:

```java
final class Counter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
```

Hai phương thức dùng cùng monitor của đối tượng `Counter`:

- Chỉ một luồng vào vùng được bảo vệ trên cùng đối tượng tại một thời điểm.
- Cả chuỗi `value++` nằm trong vùng độc quyền, nên không bị một lần increment cùng khóa chen giữa.
- Unlock và lock sau đó trên cùng monitor tạo quan hệ hiển thị.

Các lần đọc/ghi liên quan phải tuân theo cùng giao thức. Bảo vệ một đường ghi nhưng đọc trực tiếp trường qua đường không đồng bộ có thể làm thiết kế sai.

Khóa hai đối tượng khác nhau cũng không tự bảo vệ cùng trạng thái. Điều quan trọng là các bên thực sự dùng chung monitor hoặc cơ chế đồng bộ đã thiết kế.

## 8. Chọn công cụ theo đơn vị cần bảo vệ

| Nhu cầu | Hướng thường phù hợp |
| --- | --- |
| Công bố một cờ hoặc tham chiếu theo giao thức đơn giản | Volatile |
| Tăng/đổi một biến đơn theo thao tác atomic có sẵn | AtomicInteger, AtomicReference... |
| Kiểm tra và cập nhật nhiều trường theo một bất biến chung | Cùng khóa hoặc một thiết kế trạng thái atomic phù hợp |
| Chờ luồng hoàn tất | Join hoặc công cụ quản lý tác vụ tương ứng |
| Chờ một mốc công việc | Latch hoặc công cụ đồng bộ phù hợp |
| Truyền phần tử giữa producer và consumer | Collection đồng thời/BlockingQueue với hợp đồng bộ nhớ rõ ràng |

Hai `AtomicInteger` độc lập không tự bảo đảm một quan hệ như `balanceA + balanceB` luôn được quan sát ở trạng thái nhất quán. Hai biến volatile cũng không tự tạo ảnh chụp chung.

Một biến volatile trỏ đến đối tượng không làm mọi trường có thể thay đổi của đối tượng trở thành volatile. Công bố tham chiếu đúng và bảo vệ các lần sửa tiếp theo là hai trách nhiệm cần phân biệt.

Các trường final có quy tắc khởi tạo riêng giúp xây dựng đối tượng bất biến, nhưng final không làm đối tượng được tham chiếu tự bất biến và không thay thế mọi yêu cầu công bố/truy cập an toàn.

## 9. Những cách kiểm chứng dễ tạo kết luận sai

- Chạy thử nhiều lần mà chưa thấy lỗi rồi coi chương trình có data race là đúng.
- Dùng sleep để “chờ dữ liệu chắc đã sang luồng khác”.
- Thêm println vào vòng lặp rồi coi kết quả mới chứng minh cơ chế ban đầu; việc ghi log có thể đổi lịch và tạo đồng bộ ngoài ý muốn.
- Khẳng định volatile làm mọi thao tác với biến thành nguyên tử.
- Cho rằng một phương thức chỉ có một dòng thì không thể bị xen kẽ.
- Bỏ volatile vì máy hiện tại “luôn đọc đúng”.
- Dùng phép tăng atomic nhưng ghép nhiều bước mà không kiểm tra hợp đồng toàn chuỗi.

Kết quả thử nghiệm giúp tìm lỗi, nhưng bằng chứng đúng phải gắn với các quan hệ đồng bộ và đơn vị cập nhật cần bảo vệ. Chương trình sai có thể chạy đúng trong nhiều lần; chương trình đúng vẫn cần được phân tích về khả năng chờ, tài nguyên và hiệu năng.

## 10. Tự kiểm tra

1. `volatile int count` có làm `count++` nguyên tử không?
2. Ghi một tham chiếu nguyên tử có tự bảo đảm đối tượng bên trong đã được công bố đúng không?
3. Vì sao đọc `payload` sau cờ volatile có thể thấy dữ liệu đã ghi trước cờ?
4. Sleep có thay thế join để quan sát chắc chắn kết quả một luồng không?
5. Hai khóa khác nhau có mặc nhiên bảo vệ chung một biến không?
6. Hai thao tác atomic liên tiếp có luôn là một giao dịch nguyên tử không?

Đáp án:

1. Không.
2. Không.
3. Có chuỗi happens-before qua thứ tự chương trình, volatile và tính bắc cầu, theo giao thức công bố đã nêu.
4. Không.
5. Không.
6. Không; cần bảo vệ đúng đơn vị bất biến của bài toán.

## Tài liệu đối chiếu

Xem [JLS 21 §17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4), [§17.4.5 — Happens-before](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5), [§17.7 — Long và double](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.7), API [java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html) và phần bảo đảm bộ nhớ của [java.util.concurrent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html).
