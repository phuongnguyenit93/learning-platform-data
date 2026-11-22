# Quan hệ happens-before của khóa monitor

## `synchronized` vừa bảo vệ truy cập, vừa tạo thứ tự bộ nhớ

Khi hai luồng chia sẻ dữ liệu, chỉ biết một luồng đã ghi giá trị trong mã nguồn chưa đủ để chứng minh luồng khác sẽ đọc giá trị đó đúng lúc. Cần một giao thức phối hợp và một quan hệ thứ tự mà Java Memory Model bảo đảm.

Monitor là cơ chế khóa gắn với mỗi đối tượng Java. `synchronized (monitor)` yêu cầu luồng lấy khóa monitor trước khi thực hiện thân khối. Tại một thời điểm, chỉ một luồng giữ monitor đó; khi rời khối, khóa được mở, kể cả khi khối kết thúc bởi ngoại lệ. Xem [ngữ nghĩa khối `synchronized`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.19).

Trong bài, **happens-before** là quan hệ bảo đảm về thứ tự và khả năng quan sát tác động bộ nhớ. Nó không chỉ mô tả thứ tự các dòng log hoặc việc một luồng có vẻ chạy sớm hơn trên đồng hồ.

## Quy tắc cốt lõi: mở và khóa lại cùng monitor

Thao tác mở khóa một monitor happens-before những thao tác khóa tiếp theo trên **chính monitor đó**. Kết hợp với thứ tự chương trình trong từng luồng và tính bắc cầu, các ghi trước khi mở khóa được truyền qua chuỗi thứ tự tới các đọc sau lần khóa phù hợp. Xem [happens-before trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5).

Một chuỗi minh họa:

```text
Luồng ghi                               Luồng đọc
ghi payload = 42
        │ thứ tự trong luồng
mở khóa monitor M
        └──── happens-before ────────> khóa lại monitor M
                                            │ thứ tự trong luồng
                                      đọc payload
```

Điều quan trọng là hai phía dùng cùng **đối tượng monitor**, không phải chỉ cùng từ khóa `synchronized` hoặc cùng tên biến ở hai nơi khác nhau.

Quan hệ này không buộc luồng ghi luôn lấy khóa trước luồng đọc. Nếu luồng đọc vào trước khi có lần công bố dữ liệu, nó có thể thấy trạng thái chưa sẵn sàng. Giao thức phải nói rõ khi nào được đọc kết quả.

## Ví dụ hoàn chỉnh: công bố một giá trị một lần

Ví dụ có hai trường thường `payload` và `ready`, cùng được bảo vệ bằng một monitor riêng. Luồng đọc chờ tới khi dữ liệu sẵn sàng, thay vì đoán thời điểm bằng `sleep`.

Lưu tệp `MonitorHappensBeforeDemo.java`:

```java
public final class MonitorHappensBeforeDemo {
    private MonitorHappensBeforeDemo() {
    }

    static final class OneShotValue {
        private final Object monitor = new Object();
        private int payload;
        private boolean ready;

        void publish(int value) {
            synchronized (monitor) {
                if (ready) {
                    throw new IllegalStateException("already published");
                }
                payload = value;
                ready = true;
                monitor.notifyAll();
            }
        }

        int awaitValue() throws InterruptedException {
            synchronized (monitor) {
                while (!ready) {
                    monitor.wait();
                }
                return payload;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        OneShotValue shared = new OneShotValue();
        int[] observed = {-1};

        Thread reader = new Thread(() -> {
            try {
                observed[0] = shared.awaitValue();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "reader");

        Thread writer = new Thread(() -> shared.publish(42), "writer");
        reader.start();
        writer.start();
        reader.join();
        writer.join();

        if (observed[0] != 42) {
            throw new AssertionError("reader did not complete normally");
        }
        System.out.println("observed: " + observed[0]);
    }
}
```

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror MonitorHappensBeforeDemo.java
java MonitorHappensBeforeDemo
```

Trong lần chạy bình thường, không có luồng bên ngoài ngắt các luồng của ví dụ, stdout chính xác là:

```text
observed: 42
```

`OneShotValue` chỉ cho công bố một lần. Sau khi `ready` thành `true`, lời gọi công bố khác bị từ chối. Đây là lựa chọn giúp bài chỉ có một lần ghi payload cần phân tích, không phải một hàng đợi hay kênh trao đổi lặp.

Nhánh xử lý `InterruptedException` khôi phục cờ ngắt của luồng đọc. Nếu luồng không hoàn tất đọc bình thường, phép kiểm tra trong `main` báo lỗi thay vì in một kết quả có vẻ hợp lệ.

## Chứng minh đường truyền dữ liệu trong ví dụ

Khi `publish(42)` thành công, luồng ghi thực hiện dưới monitor:

1. Ghi `payload = 42`.
2. Ghi `ready = true`.
3. Gọi `notifyAll()`.
4. Rời khối và mở khóa monitor.

Khi luồng đọc có thể đi qua vòng `while (!ready)`, nó đang giữ cùng monitor và đã quan sát điều kiện sẵn sàng. Lần lấy lại hoặc lấy khóa sau khi bên ghi công bố dữ liệu tạo cạnh đồng bộ cần thiết. Bằng tính bắc cầu, lần ghi payload đứng happens-before lần đọc được dùng làm kết quả.

Các trường `payload` và `ready` không cần thêm `volatile` trong giao thức hiện tại vì mọi truy cập cạnh tranh tới chúng đều tuân theo cùng khóa. Điều này không có nghĩa một trường thường tự an toàn khi bị đọc ở nơi khác ngoài giao thức.

`monitor` là một tham chiếu `private final` để hai phương thức luôn dùng cùng một đối tượng khóa. `final` ở tham chiếu khóa không tự làm hai trường dữ liệu trở thành bất biến hay thay thế việc đồng bộ.

## Hai lịch thực thi đều hợp lệ

### Luồng đọc tới trước

Luồng đọc lấy monitor, thấy `ready == false` và gọi `wait()`. Việc chờ giải phóng monitor, nên luồng ghi có thể vào khối công bố dữ liệu.

Sau khi được đánh thức và giành lại monitor, luồng đọc kiểm tra lại `ready`. Nó chỉ trả payload khi điều kiện đúng.

### Luồng ghi tới trước

Luồng ghi công bố dữ liệu và rời khối trước khi luồng đọc vào. Luồng đọc lấy cùng monitor, thấy `ready == true` và đọc payload ngay.

Không cần lưu một “thông báo chưa dùng” để lần đọc sau nhận được. Điều kiện trạng thái `ready` được bảo vệ bằng monitor mới là điều quyết định có thể tiếp tục hay không.

Bởi vậy, thứ tự hai lời gọi `start()` trong `main` không phải một giả định rằng reader chắc chắn đã vào `wait` trước writer.

## Vai trò của `wait()` và `notifyAll()`

`wait()` phải được gọi khi luồng đang sở hữu monitor của đúng đối tượng. Khi chờ, nó nhả monitor đó; trước khi trả về bình thường, nó phải giành lại monitor.

`notifyAll()` đánh thức các luồng đang chờ trên đối tượng, nhưng **không mở khóa ngay tại dòng gọi**. Luồng được đánh thức phải chờ tới khi có thể lấy lại monitor. Cạnh bộ nhớ đang dùng để giải thích payload là mở khóa rồi khóa lại, không phải cách nghĩ rằng `notifyAll` tự chuyển quyền sở hữu khóa. Xem [`Object.wait()` và thông báo monitor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#wait()).

Vòng `while` là cần thiết: luồng chờ có thể thức dậy giả (spurious wakeup), hoặc sau khi thức, điều kiện của một giao thức tổng quát vẫn chưa phù hợp. Không thay vòng kiểm tra điều kiện bằng một lệnh `if` chỉ vì một lần chạy thử có vẻ đúng.

`wait()` chỉ nhả monitor đang dùng cho lần chờ đó; nó không nhả mọi khóa khác mà luồng có thể đang giữ. Ví dụ sử dụng một monitor để đường phối hợp dễ theo dõi.

## Vì sao `join()` xuất hiện trong `main`?

Mảng `observed` là phương tiện nhận kết quả từ reader. `main` chỉ đọc phần tử của mảng sau `reader.join()` thành công, tức reader đã kết thúc. Quy tắc kết thúc luồng và `join` tạo thứ tự để `main` quan sát kết quả reader đã ghi.

Đây là một đường đồng bộ khác với đường từ writer tới reader. Writer truyền payload cho reader qua monitor của `OneShotValue`; reader truyền kết quả cho `main` qua kết thúc luồng và `join`.

`writer.join()` cũng bảo đảm chương trình đã đợi writer kết thúc trước khi kết luận. Việc `join` dùng để đợi luồng kết thúc không nên bị nhầm là tự sửa mọi truy cập dữ liệu cạnh tranh xảy ra trước đó giữa hai luồng khác. Xem [`Thread.join()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#join()).

## Điều kiện quan trọng nhất là cùng một đối tượng khóa

### Hai monitor khác nhau không tạo cạnh đang cần

Đoạn minh họa dưới đây **không phải chương trình đồng bộ đúng** cho việc công bố `value` giữa hai luồng nếu không có cơ chế khác:

```java
// Các trường thuộc cùng một lớp, chỉ minh họa lỗi giao thức.
private final Object writeMonitor = new Object();
private final Object readMonitor = new Object();
private int value;

void write() {
    synchronized (writeMonitor) {
        value = 42;
    }
}

int read() {
    synchronized (readMonitor) {
        return value;
    }
}
```

Phía đọc và ghi đều có `synchronized`, nhưng khóa hai đối tượng khác nhau. Không có cạnh mở–khóa của cùng monitor nối lần ghi và đọc ở đây. Chạy thử có thể vẫn đọc được `42`; kết quả đó không biến giao thức thành đúng.

Không gán một stdout stale cố định cho ví dụ sai. Vấn đề là thiếu bảo đảm cần thiết và có truy cập xung đột chưa được sắp thứ tự, không phải JVM bắt buộc luôn trả một giá trị cũ cụ thể.

### Cùng tên biến chưa chắc cùng khóa

Nếu mỗi instance có trường `lock = new Object()`, hai instance giữ hai monitor khác nhau dù đều gọi trường là `lock`.

`synchronized` trên phương thức instance dùng monitor của `this`. Phương thức `static synchronized` dùng monitor của đối tượng `Class` của lớp khai báo. Chúng không mặc nhiên khóa chung một monitor. Xem [quy tắc chọn monitor trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.1).

Chỉ đưa `synchronized` vào phía ghi, còn phía đọc truy cập cạnh tranh tự do, cũng không tạo một cặp mở–khóa đáp ứng đường công bố đang xét.

## Những điều happens-before không tự bảo đảm

- Không chọn luồng nào được vào monitor trước và không hứa công bằng khi nhiều luồng chờ.
- Không tự chờ một điều kiện nghiệp vụ; `ready` và vòng chờ là phần giao thức cần thiết trong ví dụ.
- Không gắn vĩnh viễn một biến với một khóa. Người viết chương trình phải giữ quy tắc mọi truy cập liên quan dùng đúng monitor.
- Không tự bảo vệ các lần sửa dữ liệu sau khi đã nhả khóa nếu các lần sửa đó nằm ngoài giao thức.
- Không hoàn tác các trường đã sửa khi khối ném ngoại lệ. Mở khóa tự động giúp tránh giữ khóa mãi, không biến khối thành giao dịch có rollback.

Với một monitor tái nhập, luồng có thể vào khóa nhiều lần. Rời một khối lồng không có nghĩa luồng khác đã có thể giành monitor nếu luồng hiện tại còn giữ nó ở khối bên ngoài.

Ngoài ra, các ghi đứng trước thao tác mở khóa trong thứ tự luồng có thể tham gia chuỗi happens-before; không phải chỉ dữ liệu được viết ở ngay một dòng kề dấu `}`. Tuy nhiên, cách thiết kế dễ kiểm tra vẫn là đặt truy cập trạng thái dùng chung dưới giao thức bảo vệ nhất quán.

## Đừng thay bằng suy luận theo thời gian hoặc cache

`Thread.sleep()` không mở monitor mà luồng đang giữ và không tạo một quy tắc công bố dữ liệu thay cho cạnh monitor. Đợi lâu hơn chỉ thay đổi lịch thực thi có thể quan sát, không cung cấp chứng minh happens-before.

Tương tự, việc log cho thấy “writer chạy trước” không đủ để chứng minh một lần đọc không đồng bộ sẽ có giá trị mong muốn. Mã ghi log còn có thể thêm những tác động đồng bộ riêng, khiến việc suy luận từ thử nghiệm càng khó.

Nên giải thích bằng thao tác ghi, mở khóa, lấy khóa, đọc và quan hệ bắc cầu. Không cần khẳng định JVM luôn “xả toàn bộ cache xuống RAM” khi rời monitor; JMM đặt ra hành vi có thể quan sát, còn cách thực hiện cụ thể phụ thuộc JVM và phần cứng.

Các khóa tường minh như `Lock` cũng có yêu cầu về hiệu ứng đồng bộ bộ nhớ, nhưng `lock.lock()` không đồng nghĩa với lấy intrinsic monitor bằng `synchronized(lock)`. Không trộn hai cơ chế chỉ vì chúng cùng tham chiếu một đối tượng Java. Xem [ngữ nghĩa đồng bộ bộ nhớ của `Lock`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

## Cách rà soát một giao thức monitor

1. Liệt kê trạng thái dùng chung và các lần đọc/ghi của từng luồng.
2. Xác định chính xác đối tượng monitor của mỗi khối hoặc phương thức đồng bộ.
3. Vẽ chuỗi: ghi → mở monitor → lấy cùng monitor → đọc.
4. Nếu reader có thể tới trước, xác định điều kiện và cơ chế chờ phù hợp.
5. Kiểm tra không có nhánh nào bỏ qua khóa hoặc sửa trạng thái sau đó ngoài giao thức.
6. Tách bằng chứng đúng theo JMM khỏi việc một số lần chạy thử không lộ lỗi.

## Thực hành kiểm chứng

1. Đổi payload được công bố thành `99` và cập nhật kiểm tra kỳ vọng trong `main`; kết quả phải là `observed: 99` khi reader hoàn tất bình thường.
2. Đảo thứ tự hai lời gọi `start()` mà giữ nguyên giao thức. Kết quả vẫn là `42`; không có giả định reader phải chờ trước.
3. Chỉ ra cạnh đồng bộ nào nối writer với reader, rồi chỉ ra cạnh khác nối reader với `main`.
4. Phân tích đoạn hai monitor sai bằng sơ đồ; không cần đợi nó “chắc chắn in sai” mới kết luận thiếu bảo đảm.
5. Giải thích vì sao bỏ vòng `while` hoặc bỏ phần chờ làm thay đổi giao thức, dù các khối còn lại vẫn dùng cùng monitor.

Người học cần nêu được cả hai phần: cùng monitor tạo cạnh happens-before để truyền tác động bộ nhớ, còn điều kiện trạng thái và lịch giành khóa quyết định khi nào một lần đọc được phép trả kết quả.