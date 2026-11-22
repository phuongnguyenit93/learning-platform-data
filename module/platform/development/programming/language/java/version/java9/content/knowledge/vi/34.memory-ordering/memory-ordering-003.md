# Ghép cặp đọc acquire với ghi release

## 1. Mục tiêu của cặp acquire/release

Trong chương trình đa luồng, một thread có thể chuẩn bị dữ liệu rồi thông báo cho thread khác rằng dữ liệu đã sẵn sàng. Chỉ ghi một cờ trạng thái là chưa đủ: thread đọc còn phải có cách quan sát cờ theo memory ordering phù hợp để các thao tác ghi dữ liệu trước đó được nhìn thấy.

Java 9 đưa các access mode của `VarHandle` vào nền tảng Java. Hai mode thường được ghép cho giao thức công bố dữ liệu là:

- `setRelease(value)`: ghi một giá trị với release semantics.
- `getAcquire()`: đọc một giá trị với acquire semantics.

Cặp này cho phép một thread công bố dữ liệu bằng release store và thread khác nhận tín hiệu bằng acquire load. Khi acquire read quan sát giá trị được ghi bởi release write tương ứng trên cùng biến, các thao tác trước release được sắp thứ tự trước các thao tác sau acquire.

Đây là một cách thiết lập ordering giữa hai phía mà không yêu cầu mọi truy cập phải tham gia một total order như volatile access.

## 2. Release store: công bố những thao tác đã thực hiện trước đó

Release store đảm bảo các thao tác đọc/ghi xuất hiện trước lần ghi release không bị sắp xếp lại xuống sau lần ghi đó theo memory semantics của Java.

Ví dụ phía producer:

~~~java
payload = 42;
READY.setRelease(1);
~~~

Ý nghĩa:

1. Producer ghi dữ liệu vào `payload`.
2. Producer dùng `setRelease` để công bố trạng thái `READY`.
3. Một consumer có thể dùng acquire read trên cùng biến `READY` để nhận tín hiệu.

Release không làm cho toàn bộ chương trình trở thành đồng bộ và cũng không đợi consumer. Nó chỉ tạo ordering ở phía ghi: các thao tác trước release được giữ trước thao tác công bố.

## 3. Acquire load: nhận tín hiệu trước khi đọc dữ liệu được công bố

Acquire load đảm bảo các thao tác đọc/ghi xuất hiện sau lần đọc acquire không bị sắp xếp lên trước lần đọc đó theo memory semantics của Java.

Ví dụ phía consumer:

~~~java
if ((int) READY.getAcquire() == 1) {
    use(payload);
}
~~~

Khi acquire read quan sát giá trị `1` được producer ghi bằng `setRelease(1)` trên cùng biến `READY`, consumer có ordering cần thiết để đọc dữ liệu producer đã ghi trước release.

Acquire không tự chờ cho đến khi cờ có giá trị mong muốn. `getAcquire()` chỉ đọc một lần và trả giá trị đang quan sát được. Nếu cần chờ, chương trình phải lặp đọc hoặc dùng một cơ chế chờ phù hợp.

~~~java
while ((int) READY.getAcquire() == 0) {
    Thread.onSpinWait();
}
use(payload);
~~~

`Thread.onSpinWait()` là một gợi ý tối ưu cho vòng lặp spin, không phải thao tác đồng bộ. Nó không thay thế acquire read và không tạo quan hệ ordering.

## 4. Điều kiện để cặp acquire/release có hiệu lực

Cần ghép đúng hai phía:

1. Release write và acquire read phải truy cập cùng biến đồng bộ.
2. Acquire read phải quan sát giá trị được công bố bởi release write tương ứng.
3. Dữ liệu cần công bố phải được ghi trước release.
4. Consumer phải đọc dữ liệu sau acquire.

Ví dụ đúng:

~~~java
payload = new Payload("ready");
READY.setRelease(1);

// Thread consumer:
if ((int) READY.getAcquire() == 1) {
    consume(payload);
}
~~~

Trong ví dụ này, `READY` là biến truyền tín hiệu; `payload` là dữ liệu được công bố. Không cần biến `payload` phải là volatile nếu giao thức release/acquire được thiết kế đúng.

Nếu acquire read vẫn đọc giá trị cũ, chẳng hạn `0`, thì consumer chưa nhận được tín hiệu công bố và không được giả định dữ liệu mới đã sẵn sàng. Nếu acquire đọc một giá trị do một thao tác ghi khác tạo ra, không thể tự động coi nó là cặp với release write mà chương trình định dựa vào.

Dùng một biến trạng thái riêng, giá trị trạng thái rõ ràng và giao thức một lần công bố giúp tránh nhầm lẫn giữa các lần publish. Với nhiều producer, nhiều lần tái sử dụng buffer hoặc trạng thái có thể quay về giá trị cũ (ABA), cần thêm sequence number, CAS hoặc giao thức đồng bộ phù hợp.

## 5. Release/acquire không phải mutual exclusion

Cặp release/acquire thiết lập ordering cho việc công bố và nhận dữ liệu. Nó không tự cung cấp:

- Khóa loại trừ lẫn nhau.
- Quyền sở hữu độc quyền trên dữ liệu.
- Một phép tăng/giảm nguyên tử cho biến đếm.
- Bảo đảm mọi cập nhật của nhiều producer được giữ lại.
- Một hàng đợi hoặc cơ chế đánh thức thread.

Nếu nhiều thread cùng cập nhật một biến, cần chọn thao tác nguyên tử phù hợp như `compareAndSet`, `compareAndExchange`, `getAndAdd`, hoặc dùng lock/queue. Release/acquire chỉ giải quyết ordering; nó không biến một chuỗi thao tác đọc-sửa-ghi thành một thao tác nguyên tử.

## 6. So sánh plain, opaque, acquire/release và volatile

Các access mode của VarHandle xác định memory semantics cho từng lần truy cập:

| Mode | Đọc | Ghi | Đặc điểm |
|---|---|---|---|
| Plain | `get` | `set` | Truy cập thông thường, không tạo ordering liên luồng bổ sung |
| Opaque | `getOpaque` | `setOpaque` | Có tính nhất quán và thứ tự coherent trên cùng biến, nhưng không cung cấp ordering acquire/release cho dữ liệu khác |
| Acquire / Release | `getAcquire` | `setRelease` | Ghép cặp đọc/ghi để sắp thứ tự các truy cập xung quanh biến truyền tín hiệu |
| Volatile | `getVolatile` | `setVolatile` | Ngoài acquire/release properties còn có total order giữa các volatile operations |

Acquire/release thường phù hợp khi cần công bố dữ liệu theo một giao thức rõ ràng và không cần total order của volatile. Tuy nhiên, không nên chọn chỉ vì cho rằng nó luôn nhanh hơn; hiệu năng phụ thuộc JVM, kiến trúc CPU và workload.

### Opaque không thay thế acquire/release

Opaque access hữu ích khi cần truy cập có tính nhất quán trên cùng biến nhưng không cần ordering với các biến dữ liệu khác. Nếu consumer đọc một cờ opaque rồi đọc payload, không được suy ra payload đã được công bố theo giao thức acquire/release.

### Volatile mạnh hơn về ordering tổng thể

Volatile read/write tạo một thứ tự tổng thể giữa các volatile operations. Acquire/release chỉ đặt ordering ở hai phía của cặp tương ứng. Nếu chương trình cần một giao thức đơn giản với volatile semantics đầy đủ, dùng `getVolatile`/`setVolatile` hoặc field volatile thông thường có thể dễ hiểu hơn.

### Access mode quyết định semantics thực tế

Memory semantics của access mode ghi đè semantics được khai báo ở field. Ví dụ, một field được khai báo `volatile` nhưng truy cập bằng VarHandle mode `get` hoặc `set` vẫn dùng semantics plain của mode đó. Không được giả định khai báo volatile sẽ tự nâng mọi access mode thành volatile.

Vì vậy, tránh trộn plain, opaque, acquire/release và volatile tùy tiện trên cùng biến. Nếu cần phối hợp nhiều mode, hãy mô tả rõ giao thức và kiểm tra theo Java Memory Model.

## 7. Ví dụ Java chạy được: công bố payload bằng setRelease/getAcquire

Ví dụ dùng một static int làm cờ trạng thái và một static int thường làm payload. Thread ghi đặt payload trước, sau đó công bố cờ bằng `setRelease`. Thread đọc liên tục gọi `getAcquire` cho đến khi nhận được cờ, rồi mới đọc payload.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AcquireReleasePublicationDemo {
    private static int payload;
    private static int ready;

    public static void main(String[] args) throws Exception {
        VarHandle readyHandle = MethodHandles.lookup().findStaticVarHandle(
                AcquireReleasePublicationDemo.class, "ready", int.class);

        Thread writer = new Thread(() -> {
            payload = 42;
            readyHandle.setRelease(1);
        });

        Thread reader = new Thread(() -> {
            long deadline = System.nanoTime() + 5_000_000_000L;
            int observed;
            while ((observed = (int) readyHandle.getAcquire()) == 0) {
                if (System.nanoTime() >= deadline) {
                    throw new IllegalStateException("publication timed out");
                }
                Thread.onSpinWait();
            }
            System.out.println("acquire observed ready = " + observed);
            System.out.println("payload after acquire = " + payload);
        });

        reader.start();
        writer.start();
        writer.join();
        reader.join();
        System.out.println("writer completed release store = 1");
    }
}
~~~

Lưu mã nguồn trong `AcquireReleasePublicationDemo.java`, sau đó biên dịch và chạy với Java 9 trở lên:

~~~bash
javac --release 9 -Xlint:all AcquireReleasePublicationDemo.java
java AcquireReleasePublicationDemo
~~~

Kết quả:

~~~text
acquire observed ready = 1
payload after acquire = 42
writer completed release store = 1
~~~

Có thể biên dịch cùng mã nguồn với Java 17:

~~~bash
javac --release 17 -Xlint:all AcquireReleasePublicationDemo.java
java AcquireReleasePublicationDemo
~~~

Ví dụ dùng một writer và một reader, cờ chỉ chuyển từ `0` sang `1` một lần. Reader chỉ đọc payload sau khi acquire load nhận được `1`. Hai lệnh `join()` ở main chỉ giúp main đợi hai thread kết thúc; chúng không thay thế cặp release/acquire mà reader dùng trước khi đọc payload.

Vòng spin có deadline để ví dụ không chờ vô hạn nếu giao thức bị thay đổi sai. Trong ứng dụng thật, nên cân nhắc `LockSupport.park`, condition, queue hoặc cơ chế chờ phù hợp nếu thời gian chờ có thể dài; spin liên tục có thể tiêu thụ CPU.

## 8. Những lỗi thường gặp

- **Ghi payload sau release:** consumer có thể nhận tín hiệu trước khi payload được chuẩn bị. Hãy ghi dữ liệu trước release store.
- **Đọc payload trước acquire:** ordering nhận dữ liệu chưa được thiết lập tại thời điểm đọc. Hãy acquire trước khi sử dụng payload.
- **Dùng hai biến đồng bộ khác nhau:** release trên cờ A không tự ghép với acquire trên cờ B. Dùng cùng biến cho tín hiệu.
- **Nghĩ getAcquire tự chờ:** nó chỉ thực hiện một lần đọc; cần loop hoặc cơ chế chờ nếu phải đợi trạng thái.
- **Cho rằng bất kỳ giá trị quan sát nào cũng là release write mong muốn:** phải xác định rõ acquire đọc được lần công bố nào, nhất là khi cờ được tái sử dụng.
- **Dùng release/acquire thay CAS:** cặp này không làm một phép đọc-sửa-ghi trở thành nguyên tử.
- **Dùng opaque để công bố payload:** opaque bảo đảm coherence trên biến nhưng không cung cấp ordering acquire/release cho payload.
- **Trộn mode trên cùng biến mà không có lý do:** semantics khác nhau có thể tạo kết quả khó phân tích.
- **Cho rằng field volatile làm mọi VarHandle access thành volatile:** access mode được gọi mới quyết định semantics của thao tác.

## 9. Checklist khi review giao thức

1. Biến nào là tín hiệu công bố dữ liệu?
2. Producer có ghi toàn bộ payload trước `setRelease` không?
3. Consumer có dùng `getAcquire` trên đúng biến tín hiệu không?
4. Consumer có đọc payload sau khi acquire quan sát được giá trị công bố không?
5. Có nhiều writer hoặc nhiều chu kỳ tái sử dụng trạng thái không?
6. Có cần CAS/lock để bảo vệ cập nhật đồng thời không?
7. Acquire/release có đủ hay cần volatile total order?
8. Có đang trộn plain/opaque/acquire/release/volatile trên cùng biến không?
9. Vòng spin có thời hạn hoặc cơ chế chờ phù hợp không?

## 10. Tài liệu tham khảo

- [VarHandle — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/VarHandle.html)
- [VarHandle — Java SE API hiện hành](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java Language Specification — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html)