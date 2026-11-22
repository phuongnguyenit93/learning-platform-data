# Các điểm liên quan khóa hoặc đồng bộ khi được hỗ trợ trong AOP

Các chương trình đa luồng thường có những đoạn cần **loại trừ tương hỗ** (mutual exclusion), bảo vệ trạng thái dùng chung hoặc điều phối thứ tự thực thi. Khi muốn ghi nhận thời gian chờ khóa, phát hiện vùng đồng bộ chạy quá lâu hoặc kiểm toán các điểm tranh chấp, ta có thể đặt câu hỏi dưới góc nhìn **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**: liệu những thời điểm liên quan đến khóa có thể được xem là **join point** để một aspect can thiệp không?

Câu trả lời là **có thể, nếu mô hình join point và cơ chế triển khai AOP thật sự hỗ trợ**. Không phải mọi hệ thống AOP nhìn thấy việc lấy/trả monitor, và quan sát một lời gọi phương thức đồng bộ cũng không đồng nghĩa quan sát chính xác từng sự kiện lấy/trả khóa. Bài này phân tích các điểm có thể quan sát, ý nghĩa của chúng, cách chọn điểm, truyền ngữ cảnh, ghi số liệu và các giới hạn an toàn.

## 1. Ôn lại: join point phụ thuộc cơ chế triển khai

Trong AOP:

- **Join point (điểm nối)** là một vị trí hoặc sự kiện thực thi mà một cơ chế AOP cho phép liên kết hành vi bổ sung.
- **Pointcut** chọn tập join point thỏa quy tắc.
- **Advice** chạy khi join point tương ứng được chọn, có thể đọc ngữ cảnh và thực hiện hành vi trước, sau hoặc bao quanh theo khả năng của cơ chế.
- **Weaving** là việc kết hợp hành vi khía cạnh với chương trình; có thể diễn ra ở những thời điểm và bằng kỹ thuật khác nhau.

Một mô hình AOP có thể chỉ hỗ trợ chặn lời gọi thông qua đối tượng đại diện (proxy). Một mô hình khác có thể biến đổi mã hoặc bytecode để nhìn thấy những điểm nằm sâu hơn trong phương thức. Vì vậy, hai cơ chế dùng cùng thuật ngữ “aspect” nhưng **tập điểm có thể can thiệp không nhất thiết giống nhau**.

Đối với khóa, đây là sự khác biệt quyết định: **thao tác lấy/trả khóa thường xảy ra bên trong thân phương thức**, nằm ngoài phạm vi quan sát của cơ chế chỉ chặn lời gọi ở biên đối tượng.

## 2. “Khóa” trong Java là những cơ chế nào?

Để không nhầm join point với một hành vi đồng bộ cụ thể, cần phân biệt ít nhất hai nhóm cơ chế Java.

### 2.1 Monitor gắn với `synchronized`

Mỗi đối tượng Java gắn với monitor. Một luồng vào vùng `synchronized (lockObject)` phải lấy monitor của đối tượng; khi rời vùng này, monitor được nhả, kể cả lúc thoát vì ngoại lệ.

~~~java
private final Object gate = new Object();

void update() {
    synchronized (gate) {
        // Vùng được bảo vệ bởi monitor của gate
    }
}
~~~

Đây là **đoạn mã minh họa bên trong một lớp**, chưa phải chương trình độc lập. Với phương thức `synchronized` không static, monitor liên quan tới đối tượng `this`; với phương thức `static synchronized`, monitor liên quan tới đối tượng `Class` của lớp đó.

Về mặt triển khai JVM, khối `synchronized` thường thể hiện qua thao tác `monitorenter` và `monitorexit` trong bytecode, còn phương thức khai báo `synchronized` có thể biểu thị tính đồng bộ thông qua cờ của phương thức. **Không nên mặc định một cơ chế chỉ tìm lệnh `monitorenter` sẽ bao phủ cả phương thức `synchronized`.**

Monitor của Java là **reentrant**: cùng luồng có thể lấy lại monitor mình đang nắm. Mỗi lần lấy phải tương ứng với việc nhả; một lần nhả ở đoạn lồng nhau chưa chắc làm monitor hoàn toàn tự do nếu luồng vẫn còn mức giữ khóa khác.

### 2.2 Khóa tường minh qua API

Java còn có các công cụ khóa tường minh, như `ReentrantLock` trong `java.util.concurrent.locks`:

~~~java
lock.lock();
try {
    // Vùng được bảo vệ
} finally {
    lock.unlock();
}
~~~

Đây cũng là **đoạn minh họa**, giả sử `lock` đã được khởi tạo. Gọi `lock()`, `tryLock()` và `unlock()` là các **lời gọi phương thức API**. Chúng không đồng nhất với các sự kiện monitor nội tại của `synchronized`. Một cơ chế AOP quan sát được lời gọi API nhất định chưa chắc quan sát được lúc một monitor được lấy hoặc nhả; ngược lại cũng vậy.

Đặc biệt, `tryLock()` có thể trả về `false`, nghĩa là **không lấy được khóa**. Với `lockInterruptibly()` hoặc `tryLock(timeout, unit)`, còn có đường bị ngắt hoặc hết thời gian chờ. Phải phân biệt **đã gọi API khóa** với **đã sở hữu khóa**.

## 3. Các điểm khóa/đồng bộ có thể quan tâm

Tùy cơ chế hỗ trợ, mô hình quan sát có thể phân biệt nhiều sự kiện:

| Điểm/sự kiện khái niệm | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| **Bắt đầu yêu cầu lấy khóa** | Luồng chuẩn bị thử giành quyền vào vùng bảo vệ | Có thể đo thời gian chờ từ đây không? |
| **Lấy khóa thành công** | Luồng đã đạt quyền thực thi trong vùng bảo vệ | Có đúng là đã lấy thành công, hay chỉ vừa gọi `lock()`? |
| **Đang ở trong vùng đồng bộ** | Chạy mã khi một khóa đã được giữ | Đo độ dài vùng bảo vệ và phát hiện thao tác chậm |
| **Chuẩn bị nhả khóa** | Luồng sắp rời phạm vi bảo vệ hoặc gọi thao tác nhả | Advice có làm phát sinh việc tốn thời gian trong vùng khóa không? |
| **Đã nhả khóa / thoát vùng** | Một bước nhả đã hoàn tất | Trong trường hợp reentrant, liệu khóa đã hoàn toàn tự do chưa? |
| **Không giành được khóa / bị ngắt** | Một lần cố gắng không thành công | Không ghi nhầm là đã sở hữu và không gọi nhả khóa sai |
| **Chờ tín hiệu đồng bộ** | Luồng tạm ngừng và chờ điều kiện | Có thể phải nhả rồi giành lại khóa; không nhầm với chờ lấy khóa ban đầu |

**Đây là bảng phân tích ngữ nghĩa**, không phải danh mục join point được mọi bộ AOP hỗ trợ. Một số cơ chế có thể bộc lộ sự kiện gần thao tác monitor; một số chỉ quan sát được lời gọi phương thức hoặc mã được chủ động bọc; một số không cung cấp loại điểm cần thiết.

Với monitor, “bắt đầu đợi”, “giành được”, “bắt đầu rời” và “đã nhả” không nhất thiết là bốn join point độc lập trong một API. Không nên tự sáng tạo biểu thức pointcut `lock(...)` hay `unlock(...)` rồi khẳng định đó là cú pháp AOP phổ quát.

## 4. Hai trục cần tách: điểm thực thi và trạng thái đồng bộ

Một **join point** chỉ mô tả vị trí mà cơ chế có thể can thiệp. **Trạng thái khóa** là sự thật về quyền sở hữu hoặc việc chờ tài nguyên tại thời điểm chạy.

Ví dụ, nếu chặn lời gọi `lock.lock()`:

1. Advice **before call** chạy khi lời gọi sắp bắt đầu; lúc này luồng có thể chưa có khóa.
2. Thân lời gọi `lock()` có thể đợi luồng khác nhả khóa.
3. Advice **after returning** chạy sau khi `lock()` trả về bình thường; với `ReentrantLock.lock()`, lời gọi bình thường quay về khi luồng đã giành được khóa.
4. Với `tryLock()`, **after returning không có nghĩa đã giành được khóa**; phải kiểm tra giá trị boolean trả về.
5. Với `unlock()`, cần phân biệt “sắp gọi”, “đã gọi xong” và **số lần giữ khóa còn lại**; hoàn tất một lần `unlock()` trên khóa reentrant chưa chắc mở hoàn toàn cho luồng khác.

Tương tự, nếu chặn điểm thực thi một **phương thức có `synchronized`**, phạm vi mà advice bao quanh so với lúc JVM lấy/trả monitor phụ thuộc vị trí advice được kết hợp. Không thể suy bằng tên loại join point rằng phép đo đã bao gồm thời gian chờ khóa.

### 4.1 Bốn thời điểm quan trọng cho một vùng monitor

~~~text
Luồng yêu cầu đi vào vùng synchronized
               |
          [Có thể phải chờ]
               |
           LẤY MONITOR
               |
       Chạy khối được bảo vệ
               |
        RỜI VÙNG ĐỒNG BỘ
               |
           NHẢ MONITOR
               |
           Tiếp tục chạy
~~~

Cách đọc thời gian:

- **Thời gian chờ khóa (acquisition wait):** từ lúc cố giành tới lúc đã giành được. Có thể gần bằng không khi không tranh chấp.
- **Thời gian giữ khóa (hold time):** từ lúc giành tới lúc nhả. Bao gồm mã chạy trong vùng bảo vệ và các thời gian chờ thực sự xảy ra khi còn giữ khóa.
- **Thời gian thao tác tổng thể:** có thể gồm các bước khác trước/sau vùng khóa; không đồng nhất với một trong hai số đo trên.

Mốc “đã giành được” phải nằm **sau** khi thao tác lấy khóa thành công. Mốc “đã nhả” phải nằm **sau** thao tác nhả tương ứng. Nếu hệ thống AOP chỉ can thiệp vào phương thức bên ngoài, ta có thể đo độ trễ của *phương thức*, nhưng không được gọi số đó là **thời gian chờ monitor chính xác** khi chưa chứng minh được ranh giới đo.

## 5. Ví dụ Java 17: quan sát thủ công các mốc khóa

Ví dụ này sử dụng các **hook được đặt bằng tay** để giải thích ý nghĩa mốc sự kiện, không phải một cơ chế AOP tự động cài advice vào bytecode. Nó cho thấy những nơi mà một công cụ có đủ khả năng can thiệp *có thể* muốn quan sát.

Tạo file `LockPointsDemo.java`:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class LockPointsDemo {
    private final Object monitor = new Object();
    private final ReentrantLock explicitLock = new ReentrantLock();
    private int counter;

    void updateWithMonitor() {
        System.out.println("MONITOR attempt");
        try {
            synchronized (monitor) {
                System.out.println("MONITOR acquired");
                try {
                    counter++;
                    System.out.println("MONITOR body=" + counter);
                } finally {
                    System.out.println("MONITOR leaving-body");
                }
            }
        } finally {
            System.out.println("MONITOR region-finished");
        }
    }

    void updateWithExplicitLock() {
        System.out.println("LOCK attempt");
        explicitLock.lock();
        System.out.println("LOCK acquired");
        try {
            counter++;
            System.out.println("LOCK body=" + counter);
        } finally {
            System.out.println("LOCK before-unlock");
            explicitLock.unlock();
            System.out.println("LOCK after-unlock");
        }
    }

    public static void main(String[] args) {
        LockPointsDemo demo = new LockPointsDemo();
        demo.updateWithMonitor();
        demo.updateWithExplicitLock();
        System.out.println("RESULT " + demo.counter);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac LockPointsDemo.java
java LockPointsDemo
~~~

Stdout chính xác của chương trình đơn luồng này:

~~~text
MONITOR attempt
MONITOR acquired
MONITOR body=1
MONITOR leaving-body
MONITOR region-finished
LOCK attempt
LOCK acquired
LOCK body=2
LOCK before-unlock
LOCK after-unlock
RESULT 2
~~~

**Giải thích các mốc:**

- `MONITOR attempt` chạy **trước** khối `synchronized`; nó không khẳng định đã lấy được khóa.
- `MONITOR acquired` chạy **trong** khối sau khi JVM đã lấy monitor thành công.
- `MONITOR leaving-body` chạy trong `finally` **vẫn ở trong vùng monitor**, trước khi JVM rời khối.
- `MONITOR region-finished` thuộc `finally` bên ngoài khối. Trong ví dụ, `monitor` luôn khác null, nên một khi vùng được vào, việc rời khối (kể cả lỗi trong thân) kéo theo nhả mức khóa tương ứng trước khi chạy `finally` này.
- `LOCK attempt` là mốc trước lời gọi `lock()`; `LOCK acquired` chạy khi lời gọi trả về bình thường.
- `LOCK before-unlock` là mốc khi luồng vẫn đang nắm khóa; `LOCK after-unlock` nằm sau khi `unlock()` hoàn tất bình thường.
- `RESULT 2` thể hiện cả hai thao tác tăng biến đếm, không hề chứng minh công cụ AOP đã can thiệp.

Ví dụ chỉ có **một luồng**, nên không mô phỏng tranh chấp. Nó ưu tiên trình bày thứ tự mốc rõ ràng. Khi thêm nhiều luồng, thứ tự log giữa các luồng sẽ phụ thuộc lịch chạy, số đo thời gian không cố định và log quá nhiều bên trong vùng khóa có thể thay đổi chính hiện tượng cần quan sát.

## 6. Nếu có hỗ trợ join point khóa, aspect sẽ làm gì?

Bảng dưới tách ba trách nhiệm AOP khỏi cơ chế đồng bộ:

| Trách nhiệm AOP | Câu hỏi | Ví dụ áp dụng cho khóa |
| --- | --- | --- |
| **Chọn điểm (pointcut)** | Quan sát vị trí nào? | Những điểm thử lấy hoặc nhả khóa trong các thành phần được theo dõi |
| **Binding ngữ cảnh** | Advice nhận dữ liệu nào? | Loại thao tác, thông tin vị trí mã, định danh quan sát của khóa, luồng liên quan, thời điểm |
| **Advice** | Làm gì tại điểm được chọn? | Bắt đầu/dừng đồng hồ, tăng bộ đếm tranh chấp, ghi cảnh báo nếu vùng khóa kéo dài |
| **Weaving** | Kết hợp xử lý bằng cách nào? | Cơ chế tương thích với join point mong muốn: bọc lời gọi, biến đổi mã hoặc công cụ quan sát thích hợp |

Ví dụ mô tả chính sách *bằng giả mã khái niệm*, không phải pointcut hợp lệ của mọi công cụ:

~~~text
when attemptAcquire(lock):
    startWaitTimer(currentOperation, lock)

when acquired(lock):
    stopWaitTimer(currentOperation, lock)
    startHoldTimer(currentOperation, lock)

when releaseCompleted(lock):
    stopHoldTimer(currentOperation, lock)
~~~

Mô hình trên chỉ đúng nếu hệ thống thực sự cung cấp đủ các sự kiện với thứ tự, tính ghép cặp và ngữ nghĩa đã nêu. Với khóa reentrant, một luồng có thể giành cùng khóa nhiều lần; một cặp thời điểm đơn giản có thể **đếm sai thời gian giữ khóa** khi chưa theo dõi mức lồng nhau. Với phép lấy khóa thất bại, không được phát sinh sự kiện “đã giành được”; với `tryLock` trả `false`, cần kết thúc phép thử mà không mở bộ đếm giữ khóa.

Không nên đưa dữ liệu có độ phân biệt cực lớn như danh tính của mọi đối tượng khóa vào nhãn metrics công khai theo mặc định: số lượng nhãn có thể tăng quá lớn. Một hệ thống nên có chiến lược lấy mẫu, gom nhóm và dọn dẹp trạng thái theo vòng đời phép đo.

## 7. Khi không có join point monitor: có thể quan sát điều gì?

Nếu cơ chế AOP chỉ chặn lời gọi qua giao diện hoặc phương thức, vẫn có thể:

- Đo tổng thời gian một phương thức xử lý, dù bên trong có dùng `synchronized` hay khóa tường minh.
- Theo dõi lời gọi tới một API khóa *nếu* những lời gọi đó đi qua điểm can thiệp của cơ chế.
- Chủ động đưa thao tác khóa vào một wrapper do chương trình sử dụng, đặt hook trước và sau việc lấy/nhả khóa.
- Dùng các công cụ quan sát runtime hoặc phân tích luồng độc lập khi cần chẩn đoán tranh chấp sâu hơn.

Nhưng phải nói chính xác **đang đo cái gì**. Đo thời gian `service.update()` không tự động là đo thời gian chờ khóa; đo `lock()` không tự động bao trùm `synchronized`; đếm số lần gọi `unlock()` không nhất thiết là đếm số lần khóa trở nên tự do.

Đặc biệt, `synchronized` là cấu trúc đồng bộ có ngữ nghĩa của ngôn ngữ/JVM. Một proxy bên ngoài phương thức không thể tự “nhìn vào” từng thao tác monitor trong mọi khối lồng nhau. Muốn quan sát chính các thao tác này cần khả năng ở cấp phù hợp, chẳng hạn instrument mã hoặc bytecode tại đúng vị trí; **khả năng quan sát sự kiện runtime** cũng không đồng nghĩa **khả năng thực thi advice tùy ý tại sự kiện đó**.

Một API AOP có thể định nghĩa tên hằng hoặc cấu trúc mô tả sự kiện khóa nhưng phiên bản công cụ đang dùng vẫn không có quy tắc chọn hoặc weaving tương ứng. Vì thế phải kiểm tra **danh mục join point được hỗ trợ trong phiên bản và chế độ triển khai thực tế**, thay vì suy từ tên API.

## 8. Trường hợp nâng cao cần đặc biệt chú ý

### 8.1 Reentrancy và cân bằng lấy/nhả

Với `synchronized` và `ReentrantLock`, cùng luồng có thể tái nhập khóa đang giữ. Trạng thái “đang giữ” không nhất thiết chuyển về “không giữ” sau *một* lần thoát vùng trong cùng chuỗi lồng nhau.

Một aspect thống kê cần hiểu ngữ nghĩa của bộ đếm sở hữu hoặc theo dõi các cặp acquisition/release lồng nhau. Nếu chỉ đếm mỗi lần “nhả” là một lần mở khóa hoàn toàn, báo cáo thời gian giữ và số lần tranh chấp sẽ bị sai.

### 8.2 `wait`, `notify` và `Condition.await`

`Object.wait()` làm luồng tạm nhả monitor của **đối tượng được wait**, chờ rồi giành lại monitor đó trước khi tiếp tục. `notify()` hoặc `notifyAll()` đánh thức các luồng đang chờ theo quy tắc của monitor nhưng **không lập tức nhả monitor** của luồng đang gọi.

Với `Condition.await()` gắn với một khóa phù hợp, việc chờ thường bao gồm nhả rồi giành lại khóa theo hợp đồng của điều kiện. Vì vậy, đo “thời gian một đoạn phương thức đang chạy” không thể tự coi tất cả thời gian đó là “thời gian đang giữ khóa”. Muốn tính chính xác phải biết những pha chờ nào làm khóa được nhả tạm thời.

### 8.3 Lấy khóa thất bại, timeout, interrupt

Với khóa tường minh:

- `tryLock()` có thể trả `false`; không được gọi `unlock()` khi lần thử đó không sở hữu khóa.
- `tryLock(timeout, unit)` có thể thất bại vì hết thời gian hoặc ném `InterruptedException`.
- `lockInterruptibly()` có thể bị ngắt trong khi chờ; `lock()` có ngữ nghĩa phản ứng với ngắt khác.

Advice phải thể hiện đúng các nhánh kết quả. Bộ thống kê “attempt”, “acquired”, “failed” và “released” là các đại lượng khác nhau, không nên cộng/trừ máy móc mà bỏ qua reentrancy và các trường hợp thoát bất thường.

### 8.4 Tránh tạo tranh chấp mới trong advice

Advice chạy ở điểm khóa có thể tự ghi log đồng bộ, lấy khóa phụ, gửi dữ liệu mạng hoặc cấp phát bộ nhớ. Điều đó làm vùng giữ khóa dài thêm và có thể tạo chu kỳ khóa dẫn tới deadlock. Đặc biệt, không tùy tiện lấy một khóa thứ hai trong advice đang chạy khi khóa thứ nhất còn được giữ: thứ tự khóa khác nhau giữa các luồng có thể gây bế tắc.

Nên ưu tiên thu thập sự kiện ngắn, giới hạn overhead, sử dụng thời gian đo đơn điệu, xử lý kết xuất bất đồng bộ ở nơi thích hợp và tránh phụ thuộc lặp lại vào chính điểm đang instrument. Cần đề phòng **advice tự kích hoạt lại chính nó** nếu thao tác ghi log hoặc thống kê cũng thỏa pointcut.

### 8.5 Can thiệp không được phá ngữ nghĩa đồng bộ

AOP có thể dùng để quan sát hoặc phối hợp chính sách, nhưng không thể coi việc viết một advice là bằng chứng chương trình đã đồng bộ đúng. Mã cần bảo vệ vẫn phải dùng khóa và nguyên tắc thiết kế hợp lệ. Không được tùy ý chuyển `unlock` sang luồng khác với khóa yêu cầu đúng chủ sở hữu, bỏ qua nhánh `finally`, hoán đổi thứ tự lấy khóa hoặc gọi phần nghiệp vụ nhiều lần mà không hiểu hậu quả.

Việc nhả rồi giành lại khóa cũng liên quan đến **quan hệ bộ nhớ** giữa các luồng. Những bảo đảm hiển thị dữ liệu đến từ ngữ nghĩa đồng bộ của ngôn ngữ/thư viện; việc log một join point không tự tạo hoặc thay thế đúng các bảo đảm đó.

## 9. Phân biệt các đại lượng khi phân tích performance

| Đại lượng | Cần mốc nào? | Không nên suy nhầm thành |
| --- | --- | --- |
| Số lần **thử** lấy khóa | Mỗi yêu cầu/attempt | Số lần lấy thành công |
| Số lần **lấy thành công** | Kết quả acquisition hợp lệ | Số luồng khác nhau hoặc số lần khóa trở nên tự do |
| **Thời gian chờ** | Từ attempt đến acquired hoặc kết thúc thất bại | Thời gian chạy toàn bộ vùng bảo vệ |
| **Thời gian giữ** | Từ acquired tới release tương ứng, có xét lồng nhau/chờ điều kiện | Thời gian CPU thực sử dụng |
| **Độ trễ thao tác** | Mốc đầu/cuối nghiệp vụ | Chỉ riêng thời gian contention |
| Số lần **timeout/interrupt** | Nhánh kết quả tương ứng | Một lần nhả khóa |

**Ví dụ suy luận:** một thao tác mất 120 ms, trong đó 80 ms chờ khóa, 35 ms ở trong vùng khóa và 5 ms ở ngoài. Nếu chỉ đặt around advice tại phương thức, ta có thể thấy khoảng 120 ms nhưng không thể tách 80/35/5 ms nếu thiếu các mốc khóa tương ứng. Ngược lại, nếu đo ngay trong `synchronized` thì đã qua giai đoạn chờ lấy monitor; số đo đó không phản ánh 80 ms chờ trước khi vào.

Các số trong tình huống này là **giả định để minh họa cách đọc số liệu**, không phải output của một chương trình đo cụ thể.

## 10. Các lỗi hiểu sai thường gặp

1. **“Có advice cho phương thức thì mặc nhiên có advice cho monitor.”** Sai. Biên lời gọi/phương thức và thao tác monitor là hai loại điểm khác nhau; khả năng hỗ trợ phải được xác minh.
2. **“Thấy `lock()` được gọi nghĩa là đã có khóa.”** Sai trước khi lời gọi hoàn tất; với `tryLock` còn phải xét kết quả `true/false`.
3. **“Thấy `unlock()` là khóa đã hoàn toàn tự do.”** Sai với reentrancy nếu số lần giữ còn dương.
4. **“Sau khi `notify()` thì luồng gọi đã nhả monitor.”** Sai; việc gửi tín hiệu không tự kết thúc vùng giữ monitor.
5. **“`finally` bên trong `synchronized` chạy sau khi nhả monitor.”** Sai: nó nằm trong vùng đồng bộ; chỉ sau khi rời khối mới có thao tác nhả tương ứng của khối đó.
6. **“Mọi đo lường quanh phương thức đều đo được contention.”** Sai khi thiếu mốc trước/sau acquisition hoặc cơ chế không nhìn thấy khóa bên trong.
7. **“Thêm advice đo/log không ảnh hưởng tranh chấp.”** Sai: chính advice thêm thời gian và đôi khi lấy thêm khóa.
8. **“Một kiểu pointcut khóa luôn có trong mọi hệ thống AOP.”** Sai. Các sự kiện và cú pháp phụ thuộc mô hình join point, công cụ và phiên bản.

## 11. Kiểm thử đúng phạm vi và ngữ nghĩa

Khi thiết kế aspect quan sát khóa, hãy xác nhận:

- **Khả năng hỗ trợ:** đúng loại join point có tồn tại và được phép weave trong chế độ đang dùng? Có bao phủ cả khối `synchronized`, phương thức đồng bộ, và khóa tường minh hay không?
- **Đường thành công:** attempt → acquired → release được ghi đúng thứ tự cho từng lần lấy thực.
- **Đường thất bại:** timeout, `false`, interrupt và ngoại lệ không được ghi nhầm là đã lấy.
- **Đường lồng nhau:** cùng luồng lấy lại khóa nhiều lần không làm bộ đo đánh dấu “khóa hoàn toàn tự do” quá sớm.
- **Đường chờ điều kiện:** `wait`/`await` có thể làm thay đổi tình trạng sở hữu tạm thời; phép đo hold time cần xử lý phù hợp.
- **Tính an toàn:** advice không lấy thêm khóa gây deadlock, không thay kết quả/ngoại lệ của nghiệp vụ và không giữ dữ liệu ngữ cảnh lâu hơn cần thiết.
- **Tính đo lường:** overhead thấp và rõ ràng; khi chạy dưới contention thật, metrics phản ánh đúng loại số đo đã công bố.

Một kiểm thử chỉ thấy log “LOCK acquired” xuất hiện là chưa đủ. Cần kiểm chứng điểm đặt log thật sự nằm **sau acquisition**, cùng luồng sở hữu đúng khóa và mọi đường thất bại đều được phản ánh trung thực.

## 12. Bài tập tư duy

Một nhóm muốn cảnh báo khi “mọi vùng `synchronized` giữ monitor trên 50 ms”. Công cụ AOP hiện tại chỉ bọc lời gọi vào các phương thức công khai.

**Câu hỏi 1 — Có đủ thông tin không?** Chưa. Đo thời gian toàn phương thức không chỉ đo riêng các vùng `synchronized`; một phương thức có thể có nhiều vùng đồng bộ, hoặc chờ monitor trước khi vào vùng.

**Câu hỏi 2 — Cần khả năng gì?** Cần quan sát được các mốc giành và nhả monitor (hoặc có hook tin cậy ngay sát ranh giới), kết hợp đúng cặp mốc và tính đến trường hợp lồng nhau hay chờ điều kiện.

**Câu hỏi 3 — Nếu công cụ không hỗ trợ thì sao?** Có thể instrument thủ công vùng quan trọng, dùng wrapper có phạm vi rõ ràng với khóa tường minh hoặc dùng công cụ chẩn đoán runtime phù hợp. Phải đặt lại tên đại lượng nếu chỉ đo được tổng độ trễ phương thức.

**Câu hỏi 4 — Có nên gửi log mạng ngay trước khi nhả monitor không?** Không nên. Nó kéo dài thời gian giữ khóa và có thể tạo tranh chấp phụ. Thu thập số liệu tối thiểu tại điểm đo rồi xử lý chúng ngoài vùng nóng là hướng tiếp cận thường phù hợp hơn.

**Ghi nhớ:** điểm liên quan khóa và đồng bộ chỉ trở thành **join point có thể can thiệp** khi mô hình AOP hỗ trợ rõ ràng. Khi phân tích, phải tách **lúc thử lấy**, **lúc lấy thành công**, **lúc đang giữ**, **lúc nhả**, **lúc thử thất bại** và **lúc chờ điều kiện**. Làm được điều đó giúp aspect đo lường đúng sự kiện, bảo toàn ngữ nghĩa khóa và tránh đưa rủi ro mới vào chương trình đa luồng.

## Tài liệu tham khảo kỹ thuật

- [Java SE 17, JLS §14.19 — `synchronized` statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19)
- [Java SE 17, JLS §17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)
- [Java SE 17 — `ReentrantLock` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
- [AspectJ Programming Guide — Join Points and Pointcuts](https://eclipse.dev/aspectj/doc/latest/progguide/language.html) (tài liệu tham khảo về mô hình join point; cú pháp và khả năng hỗ trợ phải xác minh theo công cụ đang dùng).
