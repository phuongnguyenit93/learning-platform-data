# Không giả định Arena dùng chung tự ngăn tranh chấp dữ liệu

## Mục tiêu

Khi dùng Foreign Function & Memory API (FFM) của Java 22 trở lên, cần phân biệt **cho phép nhiều luồng truy cập cùng vùng nhớ** với **đảm bảo thao tác lên dữ liệu trong vùng nhớ là an toàn khi chạy đồng thời**. `Arena.ofShared()` giải quyết vấn đề phạm vi truy cập luồng và vòng đời bộ nhớ; nó **không tự khóa dữ liệu, không biến phép tăng biến đếm thành nguyên tử, không bảo vệ bất biến của cấu trúc dữ liệu**.

Sau bài này, bạn cần giải thích được vì sao hai luồng dùng cùng `MemorySegment` vẫn có thể cập nhật mất dữ liệu, chọn được cách đồng bộ phù hợp, và bảo đảm `Arena` chỉ đóng sau khi mọi tác vụ còn dùng vùng nhớ đã kết thúc.

## 1. Shared Arena thực sự bảo đảm điều gì?

FFM cung cấp `Arena` để cấp phát và quản lý vòng đời vùng nhớ ngoài heap; vùng nhớ được biểu diễn bởi `MemorySegment`. Mỗi segment gắn với một scope. Khi scope đã hết hiệu lực, các truy cập qua FFM sẽ bị từ chối, giúp tránh truy cập vùng nhớ đã được giải phóng. API còn kiểm tra biên vùng nhớ và ràng buộc luồng tương ứng.

| Arena | Ai có thể truy cập segment? | Có thể đóng tường minh? | Tự ngăn tranh chấp dữ liệu? |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Luồng sở hữu arena | Có, bởi luồng sở hữu | Không phải cơ chế khóa; luồng khác bị từ chối truy cập |
| `Arena.ofShared()` | Nhiều luồng | Có, bởi bất kỳ luồng nào | **Không** |
| `Arena.ofAuto()` | Nhiều luồng | Không; vòng đời do GC quản lý | **Không** |
| `Arena.global()` | Nhiều luồng | Không; scope có vòng đời không giới hạn | **Không** |

Các tính chất như *bounds checking*, *temporal safety* và *thread accessibility* khác với *data-race freedom*:

- **Giới hạn không gian:** đọc/ghi ra ngoài kích thước `MemorySegment` có thể bị từ chối.
- **Giới hạn thời gian:** truy cập khi scope không còn sống bị từ chối.
- **Giới hạn luồng:** segment thuộc confined arena chỉ được luồng sở hữu truy cập; segment thuộc shared arena có thể được nhiều luồng truy cập.
- **Đồng bộ dữ liệu:** các luồng có cùng đọc/ghi một địa chỉ theo thứ tự và quy tắc nhớ đúng hay không là trách nhiệm của chương trình.

Dòng `Arena.ofShared()` **không tương đương** với việc bọc mọi `segment.get(...)` và `segment.set(...)` trong `synchronized`. Việc triển khai arena có khả năng dùng từ nhiều luồng cũng không có nghĩa mọi dữ liệu do arena cấp phát đều là cấu trúc dữ liệu thread-safe.

## 2. Data race trên vùng nhớ được chia sẻ xuất hiện thế nào?

Giả sử một segment chứa số nguyên tại byte offset `0`. Hai luồng đều làm:

1. Đọc giá trị hiện tại bằng `get`.
2. Tính giá trị mới bằng `current + 1`.
3. Ghi lại bằng `set`.

Nếu cả hai đọc `0` trước khi một luồng ghi, cả hai sẽ cùng ghi `1`. Dù có hai lần tăng theo ý định, kết quả vẫn là `1`: **lost update**. Bản thân ba bước đọc–tính–ghi không phải một phép toán nguyên tử.

Lịch thực thi có thể là:

| Thời điểm | Luồng A | Luồng B | Giá trị trong segment |
| --- | --- | --- | --- |
| t0 | — | — | 0 |
| t1 | Đọc được 0 | — | 0 |
| t2 | — | Đọc được 0 | 0 |
| t3 | Ghi 1 | — | 1 |
| t4 | — | Ghi 1 | 1 |

Trong chương trình thực tế, thiếu đồng bộ còn có thể dẫn tới quan sát trạng thái cũ, thứ tự quan sát không như mong muốn hoặc cấu trúc nhiều trường bị đọc ở trạng thái không nhất quán. Không thể dựa vào việc lỗi hiếm xuất hiện, hoặc một lần chạy cho ra kết quả đúng, để kết luận mã an toàn.

### Ví dụ tái hiện lost update một cách xác định

Lưu toàn bộ mã sau thành **SharedArenaRaceDemo.java** (Java 22+):

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.CountDownLatch;

public class SharedArenaRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);
            counter.set(ValueLayout.JAVA_INT, 0L, 0);

            CountDownLatch bothRead = new CountDownLatch(2);
            CountDownLatch allowWrites = new CountDownLatch(1);

            Runnable increment = () -> {
                int current = counter.get(ValueLayout.JAVA_INT, 0L);
                bothRead.countDown();

                try {
                    allowWrites.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                counter.set(ValueLayout.JAVA_INT, 0L, current + 1);
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);
            first.start();
            second.start();

            bothRead.await();       // Chắc chắn cả hai đã đọc giá trị 0.
            allowWrites.countDown();
            first.join();
            second.join();          // Không đóng arena khi worker còn chạy.

            System.out.println(counter.get(ValueLayout.JAVA_INT, 0L));
        }
    }
}
~~~

Biên dịch và chạy:

~~~text
javac SharedArenaRaceDemo.java
java SharedArenaRaceDemo
~~~

Kết quả:

~~~text
1
~~~

Hai `CountDownLatch` cố ý tạo lịch chạy khiến **cả hai luồng đọc trước khi ghi**; chúng không biến phép tăng thành nguyên tử. `join()` giúp đợi các luồng hoàn tất và bảo đảm đọc kết quả sau khi công việc kết thúc. Ví dụ không dựa vào thời gian ngủ hoặc may rủi của bộ lập lịch.

## 3. Bốn cách tổ chức truy cập đúng

### 3.1. Chỉ đọc dữ liệu bất biến sau khi công bố an toàn

Một segment có thể được nhiều luồng đọc cùng lúc khi dữ liệu đã được khởi tạo xong, được **công bố bằng một cơ chế đồng bộ phù hợp** và không còn luồng nào sửa cùng vùng byte trong giai đoạn đọc. Chẳng hạn, khởi tạo dữ liệu trước khi khởi động worker, hoặc giao segment qua hàng đợi thread-safe.

Chỉ gán segment cho một biến dùng chung, hoặc biến tham chiếu `volatile`, không có nghĩa mọi thao tác ghi nội dung sau đó được bảo vệ. Tránh cho một luồng tiếp tục ghi qua alias khác trong khi các luồng còn đang đọc.

### 3.2. Phân vùng độc lập, không ghi đè lên nhau

Nếu mỗi worker chỉ đọc/ghi một khoảng byte **không chồng lấn**, có thể cấp riêng segment hoặc tạo các `asSlice(offset, size)` không giao nhau từ một segment trong shared arena. Việc truy cập các vùng byte độc lập có thể tránh xung đột dữ liệu ở chính các vùng đó.

Tuy nhiên, `asSlice` chỉ tạo **view** trên cùng bộ nhớ, không sao chép dữ liệu. Các slice chồng lấn, trường metadata dùng chung, bộ đếm tổng, hoặc việc tái sử dụng cùng địa chỉ vẫn cần đồng bộ. Cần chờ mọi worker dùng slice hoàn tất trước khi đóng arena.

### 3.3. Dùng cùng một khóa cho cả thao tác phức hợp

Khi nhiều bước phải được thực hiện như một giao dịch logic (đọc rồi ghi, thay đổi nhiều trường, kiểm tra điều kiện rồi cập nhật), dùng `synchronized` hoặc `ReentrantLock`. Ví dụ dưới đây là **đoạn minh họa đặt bên trong một phương thức**, với `segment` là segment chung và `lock` là **cùng một đối tượng khóa** mà mọi luồng liên quan sử dụng:

~~~java
synchronized (lock) {
    int current = segment.get(ValueLayout.JAVA_INT, 0L);
    segment.set(ValueLayout.JAVA_INT, 0L, current + 1);
}
~~~

Phạm vi khóa phải bao trùm **toàn bộ** chuỗi đọc–sửa–ghi, không chỉ bao quanh riêng thao tác `set`. Tất cả đường đọc/ghi cần sự nhất quán phải tuân theo cùng quy ước khóa; chỉ khóa ở writer còn reader đọc trực tiếp có thể vẫn sai. Với dữ liệu nhiều trường cần bất biến chung, khóa thường dễ chứng minh tính đúng đắn hơn nhiều phép nguyên tử rời rạc.

### 3.4. Dùng VarHandle cho phép cập nhật nguyên tử

Với một giá trị scalar thích hợp, `ValueLayout.JAVA_INT.varHandle()` tạo `VarHandle` truy cập segment bằng cặp tọa độ `(MemorySegment, long byteOffset)`. `getAndAdd` thực hiện phép cộng nguyên tử tại địa chỉ chỉ định; `getVolatile` đọc với ngữ nghĩa volatile. Cách này phù hợp với bộ đếm và trạng thái đơn giản, khi layout, căn chỉnh và access mode được nền tảng hỗ trợ.

Chương trình đầy đủ **SharedArenaAtomicDemo.java** (Java 22+):

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

public class SharedArenaAtomicDemo {
    private static final VarHandle INT = ValueLayout.JAVA_INT.varHandle();

    public static void main(String[] args) throws InterruptedException {
        int incrementsPerThread = 100_000;

        try (Arena arena = Arena.ofShared()) {
            MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);

            Runnable increment = () -> {
                for (int i = 0; i < incrementsPerThread; i++) {
                    INT.getAndAdd(counter, 0L, 1);
                }
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);
            first.start();
            second.start();
            first.join();
            second.join();

            System.out.println((int) INT.getVolatile(counter, 0L));
        }
    }
}
~~~

Biên dịch và chạy:

~~~text
javac SharedArenaAtomicDemo.java
java SharedArenaAtomicDemo
~~~

Kết quả:

~~~text
200000
~~~

`Arena.allocate(ValueLayout.JAVA_INT)` cấp đủ bộ nhớ với căn chỉnh phù hợp cho `JAVA_INT` và khởi tạo vùng nhớ về `0`. Mỗi trong hai luồng thực hiện đúng `100_000` lần `getAndAdd(..., 1)`, vì vậy tổng cuối cùng là `200_000`.

**Không suy diễn quá mức:** nguyên tử trên một số nguyên không tự bảo đảm tính nhất quán của một bản ghi gồm nhiều trường. Khi dùng các access mode `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd` hay kiểu layout khác, phải chọn đúng quan hệ bộ nhớ mong muốn và tôn trọng căn chỉnh, byte order, kiểu dữ liệu và những access mode thực sự được hỗ trợ. `JAVA_INT_UNALIGNED` hay địa chỉ lệch căn chỉnh không phải lựa chọn phù hợp để mặc nhiên đòi hỏi thao tác nguyên tử.

## 4. Vòng đời shared Arena là một vấn đề đồng thời riêng

`Arena.ofShared()` cho phép nhiều luồng truy cập segment và cho phép một luồng bất kỳ gọi `close()`. **Điều đó không cho phép đóng arena khi một worker vẫn còn dự định đọc/ghi.** Quản lý vòng đời và đồng bộ nội dung là hai nghĩa vụ khác nhau:

- Tạo arena, cấp phát và chuyển segment cho worker khi scope còn sống.
- Theo dõi worker bằng `join()`, `Future.get()` hoặc cơ chế phối hợp thích hợp.
- Chỉ đóng arena sau khi chắc chắn không còn tác vụ dùng segment. Với lỗi/interrupt, phải thiết kế đường dọn dẹp sao cho worker thực sự dừng hoặc hoàn tất trước khi tài nguyên được giải phóng.
- Không trả về segment từ một scope `try-with-resources` đã đóng rồi kỳ vọng dùng được ở nơi khác.
- Đừng dùng riêng `arena.scope().isAlive()` để chứng minh lần truy cập tiếp theo an toàn: trạng thái có thể thay đổi giữa lúc kiểm tra và lúc dùng (*time-of-check/time-of-use*).

FFM có cơ chế kiểm tra scope và có thể ném ngoại lệ khi truy cập segment hết hiệu lực; một số trường hợp đóng đồng thời với scoped access còn có thể làm `close()` thất bại. Những kiểm tra đó nhằm bảo vệ vòng đời bộ nhớ, **không sửa lỗi lost update hoặc tự hoàn thành giao thức dừng worker**.

Đối với JNI, native downcall hoặc thư viện C cùng truy cập địa chỉ, cần thiết kế **một giao thức đồng bộ mà cả phía Java và native đều tuân thủ**. `synchronized` phía Java chỉ hữu ích với các luồng/đường truy cập thực sự dùng cùng khóa; nó không tự buộc mã native ngoài JVM tuân theo khóa đó.

## 5. Những ngộ nhận và cách sửa

| Ngộ nhận | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| “`ofShared()` đã thread-safe nên `get` rồi `set` an toàn.” | Arena cho phép dùng từ nhiều luồng, nhưng đọc–sửa–ghi vẫn tách rời. | Dùng khóa bao trùm thao tác, hoặc VarHandle atomic phù hợp. |
| “Tách `asSlice()` là mỗi luồng có bản sao riêng.” | Các slice vẫn dùng cùng vùng nhớ nền. | Bảo đảm byte ranges không chồng lấn hoặc sao chép dữ liệu thực sự. |
| “Thêm `volatile` vào biến `MemorySegment` sẽ bảo vệ bytes.” | `volatile` trên tham chiếu không biến mọi cập nhật nội dung thành nguyên tử. | Đồng bộ truy cập vào nội dung theo giao thức rõ ràng. |
| “Khóa riêng ở từng worker là đủ.” | Hai khóa khác nhau không loại trừ lẫn nhau. | Dùng cùng một khóa chia sẻ cho mọi đường truy cập cần bảo vệ. |
| “`isAlive()` trả `true` thì đóng arena cùng lúc vẫn ổn.” | Kiểm tra rồi dùng không phải một thao tác nguyên tử với việc đóng scope. | Điều phối ownership và đợi worker trước khi close. |
| “`asReadOnly()` đóng băng cả vùng nhớ.” | Chỉ view đó không ghi được; alias có quyền ghi vẫn có thể thay đổi dữ liệu. | Ngừng toàn bộ writer hoặc tạo snapshot bất biến an toàn. |
| “Chạy thử nhiều lần không gặp lỗi tức là không có race.” | Lịch chạy và phần cứng có thể che khuất lỗi. | Phân tích các truy cập xung đột và quan hệ happens-before, thêm kiểm thử điều phối. |

## 6. Checklist khi dùng shared Arena trong hệ thống thật

1. **Ai ghi byte nào?** Liệt kê writer, reader, offset, kích thước và các view/alias. Có vùng nào chồng lấn không?
2. **Dữ liệu có thể thay đổi đồng thời không?** Nếu không, khởi tạo và công bố an toàn trước khi đọc. Nếu có, chọn phân vùng độc lập, khóa hoặc atomic theo đúng nhu cầu.
3. **Phép toán nào cần nguyên tử?** Một giá trị hay cả nhóm trường/bất biến? `get` + `set` không thay thế `getAndAdd`.
4. **Thứ tự nhìn thấy dữ liệu được bảo đảm bởi điều gì?** Nêu cụ thể `join`, latch, lock, hàng đợi, volatile/VarHandle access mode hoặc giao thức native; tránh dựa vào `sleep`.
5. **Ai được đóng arena, khi nào?** Xác định owner quản lý vòng đời và điểm worker hoàn tất, kể cả khi xảy ra ngoại lệ/interrupt.
6. **Layout có đúng không?** Kiểm tra byte offset, size, alignment, byte order và khả năng hỗ trợ atomic access mode.
7. **Đã thử lịch chạy bất lợi chưa?** Tái hiện hai worker cùng đọc trước khi ghi, hoặc nhiều worker tăng counter với số lần được xác định rõ.

**Bài tự kiểm tra:** Nếu bỏ `CountDownLatch` trong ví dụ đầu và chạy lại, kết quả có thể tình cờ bằng `2`. Vì sao kết quả đó **không** chứng minh chương trình an toàn? Vì phép đọc–sửa–ghi vẫn thiếu cơ chế bảo đảm nguyên tử; thay đổi lịch chạy có thể lại gây lost update. Nếu thay bằng `getAndAdd` như ví dụ hai, kết quả được bảo vệ bởi thao tác nguyên tử trên chính địa chỉ của counter.

## Tài liệu đối chiếu

- [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): vòng đời, thread confinement, shared arena và close.
- [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): giới hạn không gian/thời gian và thao tác trên segment.
- [Java SE 24 — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html): layout, căn chỉnh và VarHandle.
- [Java SE 24 — VarHandle](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/VarHandle.html): atomic operations và access modes.

**Ghi nhớ:** `Arena.ofShared()` giải quyết **quyền truy cập từ nhiều luồng và vòng đời vùng nhớ**. Trách nhiệm **đồng bộ các truy cập xung đột vào cùng dữ liệu** vẫn thuộc về thiết kế chương trình.