# Giới hạn đúng đắn khi trộn nhiều chế độ truy cập của VarHandle

## Mục tiêu

Trong nhóm kiến thức **Trật tự bộ nhớ**, một vấn đề quan trọng là cách các thread dùng nhiều access mode trên cùng biến. Java 9 giới thiệu **VarHandle** với các chế độ plain, opaque, acquire, release, volatile và các thao tác nguyên tử đọc-sửa-ghi. Việc một VarHandle hỗ trợ nhiều mode không có nghĩa các mode có thể thay thế cho nhau mà vẫn giữ nguyên bảo đảm đồng bộ.

Mỗi lần gọi access mode mang một hợp đồng riêng về atomicity, visibility và ordering. VarHandle không có một chế độ bộ nhớ cố định cho toàn bộ vòng đời; khi các thread hoặc thành phần khác nhau dùng các mode khác nhau trên cùng biến, chương trình phải bảo đảm các thao tác tạo thành một giao thức nhất quán. Một thao tác mạnh hơn ở một phía không tự nâng cấp những thao tác plain hoặc opaque ở phía còn lại.

Bài này giải thích cách trộn mode an toàn, các cặp release/acquire và volatile, giới hạn của opaque/plain, các biến thể compare-and-set, cùng cách kiểm tra một giao thức đồng thời.

## 1. Access mode gắn với từng thao tác

Một **VarHandle** là tham chiếu tới một biến. Nó không có một chế độ bộ nhớ cố định cho toàn bộ vòng đời. Cùng một handle có thể được gọi bằng các access mode khác nhau nếu mode đó được hỗ trợ.

Ví dụ, một handle có thể được dùng như sau:

```java
int value = (int) HANDLE.get(box);             // plain read
HANDLE.setRelease(box, 1);                     // release write
int state = (int) HANDLE.getAcquire(box);      // acquire read
boolean changed = HANDLE.compareAndSet(box, 1, 2); // volatile CAS
```

Các lời gọi trên cùng một handle nhưng có bảo đảm khác nhau. Khi đọc mã đồng thời, hãy phân tích từng thao tác đọc/ghi và quan hệ giữa chúng, không gán một nhãn chung như “biến này là volatile” cho mọi lời gọi.

Các nhóm mode chính:

| Nhóm | Phương thức tiêu biểu | Bảo đảm |
|---|---|---|
| Plain | **get()**, **set()** | Tương tự truy cập trường thông thường; không tạo quan hệ đồng bộ giữa thread |
| Opaque | **getOpaque()**, **setOpaque()** | Bảo đảm tính nhất quán và thứ tự truy cập đối với chính biến đó; không sắp thứ tự các biến khác |
| Acquire/release | **getAcquire()**, **setRelease()** | Acquire ngăn thao tác sau bị đưa lên trước; release ngăn thao tác trước bị đưa xuống sau |
| Volatile | **getVolatile()**, **setVolatile()** | Ngữ nghĩa visibility và ordering kiểu volatile |
| Atomic read-modify-write | **compareAndSet()**, **getAndAdd()** | Cập nhật nguyên tử với ngữ nghĩa volatile tương ứng |

Một mode có thể không được hỗ trợ với mọi loại biến. Kiểm tra bằng **isAccessModeSupported()** trước khi xây dựng logic phụ thuộc vào mode tùy chọn.

## 2. Phân biệt atomicity, visibility và ordering

Ba khái niệm này giải quyết những vấn đề khác nhau:

- **Atomicity**: một thao tác được quan sát như một đơn vị không bị xen ngang. Ví dụ, compare-and-set kiểm tra giá trị và cập nhật trong một thao tác nguyên tử.
- **Visibility**: một thread có thể nhìn thấy dữ liệu mà thread khác đã ghi.
- **Ordering**: xác định những thao tác nào được bảo đảm xảy ra trước hoặc không được di chuyển qua một điểm đồng bộ.

Một thao tác nguyên tử không tự động làm mọi dữ liệu liên quan trở nên visible. Ví dụ, CAS trên cờ trạng thái chỉ nguyên tử hóa việc đổi cờ; để công bố một payload được ghi trước đó, phía đọc còn cần một thao tác acquire phù hợp.

Tương tự, một lần đọc volatile không biến tất cả lần đọc plain khác thành volatile. Bảo đảm được xác định bởi access mode thực sự được gọi ở mỗi điểm truy cập.

## 3. Cặp release/acquire để công bố dữ liệu

Một mẫu thường dùng là ghi dữ liệu trước, sau đó công bố trạng thái bằng release; thread đọc chờ trạng thái bằng acquire rồi mới đọc dữ liệu.

Ví dụ, một đối tượng chứa payload và cờ sẵn sàng:

```java
final class Message {
    int payload;
    int ready;
}
```

Tạo VarHandle cho cờ:

```java
private static final VarHandle READY;

static {
    try {
        READY = MethodHandles.lookup()
                .findVarHandle(Message.class, "ready", int.class);
    } catch (ReflectiveOperationException exception) {
        throw new ExceptionInInitializerError(exception);
    }
}
```

Thread sản xuất:

```java
message.payload = 42;
READY.setRelease(message, 1);
```

Thread tiêu thụ:

```java
while ((int) READY.getAcquire(message) == 0) {
    Thread.onSpinWait();
}
int value = message.payload;
```

Nếu acquire đọc được giá trị được công bố bởi release tương ứng, các thao tác ghi trước release được công bố cho các thao tác đọc sau acquire. Trong ví dụ, consumer có thể đọc payload bằng truy cập plain sau khi quan sát trạng thái ready qua acquire.

Điều quan trọng là **cả hai phía phải tham gia đúng giao thức**:

- Writer ghi payload trước lệnh release.
- Reader dùng acquire trên cùng biến điều phối.
- Reader chỉ đọc payload sau khi acquire quan sát trạng thái đã công bố.
- Không có writer khác sửa payload ngoài giao thức trong lúc consumer đọc.

Đây là mẫu công bố một lần. Nếu tái sử dụng Message, reset cờ, ghi payload nhiều lần hoặc có nhiều producer/consumer, cần thiết kế giao thức trạng thái riêng để tránh đọc nhầm thế hệ dữ liệu hoặc race condition.

## 4. Những cách trộn mode không tạo được bảo đảm mong muốn

Một số cặp nhìn có vẻ gần giống nhau nhưng không tạo cùng quan hệ đồng bộ:

| Writer | Reader | Kết luận |
|---|---|---|
| **setRelease()** | **getAcquire()** | Cặp phù hợp để công bố dữ liệu khi acquire quan sát giá trị release |
| **setVolatile()** | **getVolatile()** | Cặp volatile với bảo đảm volatile |
| **setRelease()** | **get()** | Reader plain không có acquire để nhận bảo đảm công bố |
| **set()** | **getAcquire()** | Writer plain không tạo release tương ứng |
| **setOpaque()** | **getOpaque()** | Có tính nhất quán trên cùng biến, nhưng không công bố thứ tự của payload ở biến khác |
| **setVolatile()** | **get()** | Plain read không mang ngữ nghĩa volatile read |

Không suy luận rằng một phía dùng mode mạnh thì phía kia tự được bảo vệ. Ví dụ, release write không làm plain read trở thành acquire. Tương tự, acquire read không thể bù cho một writer chỉ dùng plain store.

Nếu nhiều thành phần trong ứng dụng cùng truy cập một biến, hãy ghi rõ mode được dùng ở mỗi nơi và xác định cặp thao tác tạo quan hệ đồng bộ. Tránh để một thành phần dùng volatile, một thành phần khác dùng plain rồi giả định toàn bộ chương trình có cùng bảo đảm.

## 5. Opaque chỉ điều phối trên cùng biến

Opaque mạnh hơn plain về tính nhất quán đối với cùng biến, nhưng yếu hơn acquire/release về ordering với các biến khác.

Ví dụ:

```java
PAYLOAD.set(box, 42);
READY.setOpaque(box, 1);
```

Ở phía đọc:

```java
if ((int) READY.getOpaque(box) == 1) {
    int value = (int) PAYLOAD.get(box);
}
```

Không dùng cặp opaque này làm giao thức công bố payload. Opaque giúp các truy cập tới READY có thứ tự/coherence phù hợp với chính READY, nhưng không tạo ordering cần thiết giữa READY và PAYLOAD.

Nếu cần công bố dữ liệu liên quan, dùng release/acquire hoặc volatile theo yêu cầu của thuật toán. Opaque chỉ phù hợp khi tính nhất quán của một biến là điều cần thiết và không cần đồng bộ các thao tác trên biến khác.

## 6. Volatile và các mode yếu hơn

Volatile cung cấp bảo đảm ordering mạnh hơn acquire/release và opaque. Với VarHandle, có thể dùng **setVolatile()** và **getVolatile()** để tạo cặp truy cập volatile.

Tuy nhiên, không nên nghĩ rằng sau khi một biến từng được ghi volatile thì mọi truy cập về sau đều tự động có ngữ nghĩa volatile. Nếu một điểm truy cập gọi **get()**, đó vẫn là plain access mode; nếu gọi **getOpaque()**, đó vẫn là opaque mode.

Một giao thức có thể chủ ý kết hợp các thao tác mạnh và yếu, nhưng phải chứng minh rằng từng đường đọc/ghi đều có quan hệ cần thiết. Nếu không có lý do rõ ràng để giảm ordering, giữ cùng một cặp mode sẽ dễ đọc và dễ kiểm chứng hơn.

Khi nhiều thành phần cần tương tác qua cùng biến điều phối, cặp volatile thường dễ hiểu hơn. Khi hiệu năng hoặc kiến trúc yêu cầu ordering yếu hơn, dùng acquire/release sau khi đã xác định chính xác quan hệ công bố.

## 7. Atomic read-modify-write cũng có các mức ordering

VarHandle có các thao tác nguyên tử và một số biến thể ordering:

| Thao tác | Ý nghĩa |
|---|---|
| **compareAndSet()** | CAS với ngữ nghĩa volatile |
| **compareAndExchange()** | Trao đổi có điều kiện với ngữ nghĩa volatile |
| **compareAndExchangeAcquire()** | Biến thể có ngữ nghĩa acquire |
| **compareAndExchangeRelease()** | Biến thể có ngữ nghĩa release |
| **weakCompareAndSetPlain()** | Weak CAS với ngữ nghĩa plain |
| **weakCompareAndSetAcquire()** | Weak CAS với ngữ nghĩa acquire |
| **weakCompareAndSetRelease()** | Weak CAS với ngữ nghĩa release |
| **getAndAdd()** | Cộng nguyên tử với ngữ nghĩa volatile |
| **getAndAddAcquire()** | Cộng nguyên tử với ngữ nghĩa acquire |
| **getAndAddRelease()** | Cộng nguyên tử với ngữ nghĩa release |

Tên gọi của các biến thể cho biết memory effect của thao tác. Không thay **compareAndSet()** bằng **weakCompareAndSetPlain()** chỉ vì cả hai đều trả boolean: weak CAS có thể thất bại giả và biến thể plain không cung cấp ordering volatile.

Nếu dùng weak CAS, thường cần vòng lặp thử lại:

```java
int current;
do {
    current = (int) VALUE.getVolatile(box);
} while (!VALUE.weakCompareAndSetAcquire(
        box, current, current + 1));
```

Ví dụ trên chỉ minh họa cơ chế retry. Thuật toán thực tế cần chọn đúng biến thể weak CAS và access mode đọc sao cho toàn bộ giao thức có ordering cần thiết. Nếu không cần weak CAS, **compareAndSet()** thường dễ hiểu hơn.

## 8. Không trộn mode tùy tiện trong một giao thức nhiều bước

Giả sử một thread ghi hai trường rồi bật cờ:

```java
data.first = 10;
data.second = 20;
READY.setRelease(data, 1);
```

Thread khác chỉ đọc hai trường sau khi acquire quan sát cờ:

```java
if ((int) READY.getAcquire(data) == 1) {
    use(data.first, data.second);
}
```

Giao thức này có một điểm công bố rõ ràng. Nếu thay một trong hai thao tác bằng plain hoặc opaque không đúng vị trí, bảo đảm có thể mất.

Đặc biệt chú ý các tình huống:

- Một thread ghi release nhưng nhiều reader lại đọc cờ bằng plain.
- Một reader dùng acquire nhưng writer cập nhật cờ bằng plain.
- Một thread reset cờ bằng mode yếu trong khi reader vẫn dùng giao thức của thế hệ trước.
- Một trường được truy cập bằng nhiều VarHandle hoặc nhiều API khác nhau mà không thống nhất memory semantics.
- Một CAS nguyên tử được dùng để đổi trạng thái nhưng payload được đọc trước khi có acquire cần thiết.

Khi thiết kế, vẽ rõ thứ tự: ghi dữ liệu, công bố trạng thái, quan sát trạng thái, đọc dữ liệu. Đánh dấu access mode tại từng bước và xác định chính xác thao tác nào tạo quan hệ giữa hai thread.

## 9. Ví dụ Java hoàn chỉnh: công bố payload bằng release/acquire

Chương trình dưới đây tạo một producer và một consumer. Producer ghi payload plain rồi công bố cờ bằng **setRelease()**. Consumer chờ bằng **getAcquire()** rồi đọc payload.

Tạo tệp **VarHandleMixedAccessModesDemo.java**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleMixedAccessModesDemo {
    private static final class Message {
        int payload;
        int ready;
        int counter;
    }

    private static final VarHandle READY;
    private static final VarHandle COUNTER;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            READY = lookup.findVarHandle(Message.class, "ready", int.class);
            COUNTER = lookup.findVarHandle(Message.class, "counter", int.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Message message = new Message();

        Thread consumer = new Thread(() -> {
            while ((int) READY.getAcquire(message) == 0) {
                Thread.onSpinWait();
            }
            System.out.println("payload after acquire: " + message.payload);
        });

        Thread producer = new Thread(() -> {
            message.payload = 42;
            READY.setRelease(message, 1);
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();

        int previous = (int) COUNTER.getAndAdd(message, 1);
        System.out.println("counter previous: " + previous);
        System.out.println("counter current: " + COUNTER.getVolatile(message));

        boolean transitioned = READY.compareAndSet(message, 1, 2);
        System.out.println("volatile CAS: " + transitioned);
        System.out.println("ready: " + READY.getVolatile(message));
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 VarHandleMixedAccessModesDemo.java
java VarHandleMixedAccessModesDemo
```

Stdout chính xác:

```text
payload after acquire: 42
counter previous: 0
counter current: 1
volatile CAS: true
ready: 2
```

Trong ví dụ:

1. **payload** được ghi bằng truy cập plain.
2. **ready** được công bố bằng release.
3. Consumer đọc **ready** bằng acquire trước khi đọc payload.
4. **counter** được cập nhật nguyên tử bằng get-and-add và đọc lại bằng volatile.
5. compare-and-set chuyển ready từ 1 sang 2 bằng thao tác nguyên tử có ngữ nghĩa volatile.

Đây là ví dụ minh họa một giao thức công bố một lần. Nó không chứng minh rằng mọi cách trộn mode đều an toàn; kết quả đúng đến từ quan hệ release/acquire cụ thể giữa producer và consumer.

## 10. Quy trình kiểm tra một thiết kế trộn access mode

Trước khi chấp nhận một thiết kế, hãy trả lời các câu hỏi sau:

1. **Biến điều phối là gì?** Xác định biến dùng để công bố trạng thái hoặc dữ liệu.
2. **Ai ghi và ai đọc?** Liệt kê mọi thread, kể cả callback, executor và code thư viện có thể truy cập biến.
3. **Mode nào được gọi tại mỗi điểm?** Phân biệt rõ plain, opaque, acquire, release, volatile và atomic RMW.
4. **Reader quan sát được thao tác công bố nào?** Với release/acquire, xác định acquire có thể đọc giá trị được ghi bởi release tương ứng hay không.
5. **Có đường đọc nào dùng mode yếu hơn không?** Một reader plain không nhận bảo đảm acquire chỉ vì reader khác dùng acquire.
6. **Có reset hoặc tái sử dụng trạng thái không?** Xem xét nhiều chu kỳ, nhiều producer, ABA và việc payload bị ghi đè.
7. **Atomicity có đủ cho toàn bộ trạng thái không?** CAS trên một biến không biến nhiều trường thành giao dịch nguyên tử.
8. **Có thể đơn giản hóa bằng volatile hoặc lock không?** Chỉ tối ưu ordering sau khi đã có bằng chứng về tính đúng đắn và lợi ích thực tế.

Dùng **isAccessModeSupported()** để kiểm tra mode có sẵn cho handle, nhưng nhớ rằng việc được hỗ trợ không chứng minh giao thức đồng thời đúng. Tính đúng đắn đến từ cách các thao tác liên kết với nhau theo Java Memory Model.

## 11. Lỗi thường gặp

1. **Cho rằng cùng VarHandle có cùng memory ordering ở mọi nơi**: ordering thuộc từng access mode được gọi.
2. **Writer dùng release nhưng reader dùng plain**: không có acquire tương ứng để nhận bảo đảm công bố.
3. **Writer dùng plain nhưng reader dùng acquire**: acquire không thể tạo release đã bị thiếu ở phía ghi.
4. **Dùng opaque để công bố payload ở biến khác**: opaque chỉ bảo đảm thứ tự/coherence đối với cùng biến, không tạo ordering liên biến cần thiết.
5. **Cho rằng một volatile access làm mọi access khác thành volatile**: plain và opaque vẫn mang semantics riêng.
6. **Nhầm atomicity với visibility**: CAS nguyên tử không tự công bố dữ liệu phụ nếu không có quan hệ ordering phù hợp.
7. **Dùng weak CAS như CAS thông thường**: weak CAS có thể thất bại giả; cần retry và chọn đúng biến thể ordering.
8. **Trộn mode trong giao thức nhiều chu kỳ mà không xét reset**: trạng thái cũ, payload mới và ABA có thể làm reader diễn giải sai thế hệ dữ liệu.
9. **Hạ ordering chỉ dựa trên benchmark**: tối ưu mode có thể làm sai giao thức. Chứng minh tính đúng trước, sau đó mới đo hiệu năng.
10. **Coi isAccessModeSupported là bằng chứng thread-safe**: phương thức chỉ cho biết mode được hỗ trợ, không xác nhận cách dùng giữa các thread.

## Kết luận

Có thể dùng nhiều access mode trên cùng một VarHandle, nhưng mỗi thao tác vẫn giữ memory semantics riêng. Plain không tạo đồng bộ liên thread; opaque chỉ điều phối truy cập cùng biến; acquire/release hỗ trợ công bố dữ liệu theo cặp; volatile cung cấp ordering mạnh hơn; các thao tác atomic RMW có biến thể ordering riêng.

Khi trộn mode, hãy xác định writer, reader, biến điều phối và đường đi của dữ liệu. Bảo đảm mọi reader đều quan sát trạng thái qua mode phù hợp trước khi dùng payload. Nếu không thể giải thích rõ quan hệ ordering, chọn giao thức volatile hoặc cơ chế đồng bộ cấp cao hơn để giảm rủi ro.
