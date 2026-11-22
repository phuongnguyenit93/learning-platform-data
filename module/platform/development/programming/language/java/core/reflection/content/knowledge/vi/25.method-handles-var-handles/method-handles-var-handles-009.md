# VarHandle trong Java: Plain, Volatile, Acquire–Release và Atomic Access Modes

`VarHandle` (từ Java 9) cho phép thao tác lên **một biến cụ thể** như field của đối tượng, static field hoặc phần tử mảng, đồng thời chỉ định **quy tắc đọc/ghi bộ nhớ**. Các quy tắc này gọi là *access modes*: `get`/`set` (plain), `getVolatile`/`setVolatile`, `getAcquire`/`setRelease` và những thao tác cập nhật nguyên tử như `compareAndSet`, `getAndAdd`.

Điều quan trọng cần phân biệt ngay:

- **Memory ordering/visibility**: một luồng có được phép quan sát thao tác của luồng khác theo thứ tự nào? Thao tác khác trên các field có được xuất bản an toàn không?
- **Atomicity**: một phép cập nhật có diễn ra như một bước không thể chen vào hay không? Chẳng hạn hai luồng tăng cùng bộ đếm có thể mất lần tăng không?
- **Access mode** chỉ định một phần hoặc cả hai thuộc tính trên, tùy phép toán. `volatile` không tự biến biểu thức `x++` thành nguyên tử; `getAndAdd` mới là một phép *read-modify-write* nguyên tử.

Bài này tập trung vào cách chọn mode và lý do lựa chọn đó đúng theo Java Memory Model (JMM), không coi `VarHandle` là công cụ thay thế vô điều kiện cho `synchronized`, `Lock` hay `AtomicInteger`.

## 1. VarHandle trỏ tới biến nào?

Một `VarHandle` là một tham chiếu có kiểu động mạnh (*dynamically strongly typed*) tới vị trí lưu trữ. Nó không lưu giá trị của biến. Khi gọi access mode, chương trình cung cấp **tọa độ** để chỉ ra biến cần thao tác.

Ví dụ minh họa:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Holder {
    int count;
}

class Example {
    static void demo() throws ReflectiveOperationException {
        VarHandle countHandle = MethodHandles.lookup()
                .findVarHandle(Holder.class, "count", int.class);
        Holder holder = new Holder();

        countHandle.set(holder, 10);              // Tọa độ: holder
        int n = (int) countHandle.get(holder);      // n = 10
    }
}
```

- `findVarHandle` tra cứu một **instance field**, nên lời gọi cần đối tượng `holder` làm tọa độ; `findStaticVarHandle` áp dụng cho static field và không yêu cầu instance.
- `MethodHandles.arrayElementVarHandle(int[].class)` tạo handle cho phần tử mảng, với tọa độ là `(mảng, chỉ số)`.
- `VarHandle` không bỏ qua quyền truy cập. `MethodHandles.lookup()` và các cơ chế lookup khác phải có quyền phù hợp khi tạo handle.
- `get`/`set`, `getAcquire`/`setRelease` và các phép atomic có chữ ký thực tế theo kiểu biến và tọa độ, dù tài liệu API biểu diễn bằng `Object...`. Sai kiểu/tọa độ có thể gây `WrongMethodTypeException` hoặc lỗi ép kiểu.
- Handle trỏ đến field `final` không hỗ trợ các mode ghi hoặc atomic update; gọi mode không hỗ trợ ném `UnsupportedOperationException`.

## 2. So sánh các nhóm access mode

| Nhóm | Đọc | Ghi/cập nhật | Bảo đảm cần nhớ | Khi phù hợp |
| --- | --- | --- | --- | --- |
| **Plain (thường)** | `get` | `set` | Không tạo ràng buộc thứ tự liên luồng bổ sung như `volatile` | Dữ liệu chỉ dùng trong một luồng hoặc đã đồng bộ bằng cơ chế khác |
| **Opaque** (mức trung gian) | `getOpaque` | `setOpaque` | Atomic đối với giá trị biến và có tính nhất quán theo thứ tự truy cập cùng biến; **không** xuất bản các field khác bằng release/acquire | Trường hợp rất đặc thù chỉ cần quan sát biến riêng lẻ |
| **Acquire–Release** | `getAcquire` | `setRelease` | Có thứ tự một chiều cho các truy cập trước/sau khi một giá trị được chuyển giao phù hợp | Publish/consume dữ liệu qua cờ trạng thái |
| **Volatile** | `getVolatile` | `setVolatile` | Hiệu ứng đọc/ghi như field `volatile`; các thao tác volatile có thứ tự tổng thể tương ứng trong mô hình bộ nhớ | Cờ chia sẻ, trạng thái cần ngữ nghĩa volatile |
| **Atomic update** | Đọc và sửa trong cùng phép toán | `compareAndSet`, `compareAndExchange`, `getAndSet`, `getAndAdd`… | Cập nhật không bị xen vào ở giữa; mỗi API có memory ordering riêng | Bộ đếm, state machine, cập nhật có cạnh tranh |

Đừng hiểu bảng như một trục duy nhất mà ở đó “atomic mạnh hơn volatile”. **Atomicity và ordering là hai chiều khác nhau**: `compareAndSet` có hiệu ứng volatile, nhưng `compareAndExchangeAcquire` hoặc `getAndAddRelease` chủ động dùng ordering yếu hơn ở một phía.

### 2.1. Plain: `get` và `set`

`get(receiver)`/`set(receiver, value)` có ngữ nghĩa như đọc/ghi một field thông thường không `volatile`.

```java
// Giả sử COUNT là VarHandle tới field int count của đối tượng counter.
COUNT.set(counter, 10);
int x = (int) COUNT.get(counter);
```

Nếu `counter` chỉ được một luồng dùng, hoặc mọi truy cập của các luồng đều nằm trong cùng một giao thức đồng bộ đúng, plain thường đủ. Nếu hai luồng trao đổi dữ liệu không đồng bộ bằng plain read/write, JMM **không bảo đảm** luồng đọc thấy cập nhật mới hoặc quan sát những field khác theo thứ tự mong muốn.

Về tính atomic của thao tác đơn lẻ: tham chiếu đối tượng và primitive tối đa 32 bit có bảo đảm đọc/ghi nguyên vẹn; với `long`/`double` plain trên một số nền tảng 32 bit có ngoại lệ. Dù một `get` đơn lẻ là atomic, phép ghép `get` rồi `set` **không** trở thành atomic read-modify-write.

**Lưu ý khó bỏ qua:** mode điều khiển ngữ nghĩa truy cập **ngay cả khi field khai báo `volatile`**. Dùng `get` qua VarHandle tới một volatile field không đồng nghĩa với `getVolatile`. Pha trộn những mode khác nhau trên cùng biến mà không có thiết kế rõ ràng dễ tạo lỗi bộ nhớ rất khó tái hiện.

### 2.2. Opaque chỉ là điểm tham chiếu

`getOpaque`/`setOpaque` có bảo đảm mạnh hơn plain cho riêng biến được truy cập nhưng không thiết lập giao thức publish/consume cho dữ liệu liên quan. Đừng thay `setRelease` bằng `setOpaque` khi cần xuất bản payload ở một field khác. Bài này chỉ nhắc opaque để đặt acquire/release và volatile vào đúng bối cảnh.

## 3. Volatile: quan sát trạng thái và thứ tự liên luồng

`setVolatile` và `getVolatile` có hiệu ứng bộ nhớ tương ứng ghi/đọc field khai báo `volatile`:

```java
// FLAG là VarHandle của field boolean ready.
FLAG.setVolatile(message, true);
boolean ready = (boolean) FLAG.getVolatile(message);
```

Tương tự cặp ghi/đọc volatile trên cùng biến, ghi volatile đứng trước một lần đọc volatile phù hợp trong *synchronization order* tạo quan hệ đồng bộ để những ghi xảy ra trước được quan sát đúng theo happens-before. Nó rất hữu ích cho cờ `shutdown`, `ready` hoặc một giá trị trạng thái được thay mới nguyên khối.

Nhưng:

- `volatile` **không** làm cho `value++` hoặc `getVolatile` rồi `setVolatile` trở thành một phép atomic. Hai luồng có thể cùng đọc 4 rồi cùng ghi 5, làm mất một lần tăng.
- Volatile không bảo đảm một luồng luôn “thấy ngay lập tức” giá trị khác tại một thời điểm giới hạn cụ thể, cũng không giải quyết race logic kiểu kiểm tra rồi hành động.
- Dùng volatile cho **mọi** field không tạo thành một transaction có nhiều field nhất quán; muốn duy trì bất biến giữa nhiều biến có thể vẫn phải dùng khóa hoặc cách gói trạng thái phù hợp.

Ví dụ tăng sai với tranh chấp:

```java
int current = (int) COUNT.getVolatile(counter);
COUNT.setVolatile(counter, current + 1); // Hai thao tác riêng; có thể mất cập nhật.
```

Phép thay thế đúng, nếu handle hỗ trợ kiểu `int`, là `COUNT.getAndAdd(counter, 1)`.

## 4. Acquire–Release: xuất bản và tiếp nhận dữ liệu

`setRelease` có hiệu ứng **release**: các phép đọc/ghi trước nó trong cùng luồng không được đẩy xuống sau nó theo các ràng buộc bộ nhớ được bảo đảm. `getAcquire` có hiệu ứng **acquire**: những phép đọc/ghi sau nó không được kéo lên trước nó. Khi một luồng acquire quan sát giá trị được xuất bản qua release **trên cùng biến đồng bộ**, các ghi payload trước release có thể được tiếp nhận an toàn sau acquire theo giao thức giao tiếp đó.

Sơ đồ một thông điệp chỉ xuất bản một lần:

```text
Producer                         Consumer
---------                        ---------------------------
message.payload = 42             while (!READY.getAcquire(message))
READY.setRelease(message, true)       chờ cờ true
                                 int x = message.payload
                                 // x = 42 theo giao thức
```

Vì sao phải có cả hai phía?

1. Producer ghi `payload` trước rồi release cờ `ready`.
2. Consumer kiểm tra cờ bằng acquire. Khi đọc được giá trị do release xuất bản, nó có được thứ tự bộ nhớ cần thiết để đọc `payload`.
3. `payload` có thể là field bình thường (**plain**) nếu nó được ghi trước release và không bị sửa đồng thời bên ngoài giao thức. Đây là trường hợp *safe publication*, không phải quyền đọc mọi field không đồng bộ.

Một số giới hạn:

- `getAcquire` **không** có tác dụng “lấy bản mới nhất” của biến tùy ý; nó chỉ tạo những ordering effect tương ứng. Lần đọc cờ có thể thấy `false` và phải thử lại.
- `setRelease` không làm dữ liệu tự động sẵn sàng ở mọi luồng nếu không có phía đọc phù hợp; cũng không bắt buộc phía đọc được lập lịch trong thời gian hữu hạn.
- Khi flag được dùng lại cho nhiều vòng đời thông điệp, cần thêm giao thức để tránh ghi đè payload khi consumer đang đọc. Ví dụ đơn giản ở đây chỉ publish **một lần**.
- Một lệnh đọc release hay ghi acquire không phải cặp cần dùng: trong mô hình này, **ghi release** phối hợp với **đọc acquire**.
- Spin loop chỉ nhằm trình diễn memory ordering; production thường dùng `BlockingQueue`, `CountDownLatch`, `Lock`/`Condition`, hoặc cấu trúc đồng bộ có sẵn để tránh đốt CPU và dễ quản lý hủy/chờ.

### Acquire–release khác volatile như thế nào?

Một cặp release/acquire chủ yếu ràng buộc thứ tự quanh việc **trao thông tin theo một chiều** (publish → consume); volatile bổ sung những bảo đảm mạnh hơn, bao gồm thứ tự tổng thể giữa các truy cập volatile. Vì vậy, nếu chỉ cần producer công bố một payload rồi consumer nhận, acquire/release có thể là lựa chọn phù hợp. Không nên tự suy ra chúng tương đương volatile trong thuật toán có nhiều biến và nhiều kiểu thao tác xen kẽ.

## 5. Atomic access modes: đọc–sửa–ghi thành một phép

`VarHandle` có các phương thức atomic update. Các phương thức phổ biến:

| Phương thức | Giá trị trả về | Ý nghĩa |
| --- | --- | --- |
| `compareAndSet(receiver, expected, update)` | `boolean` | Chỉ ghi nếu giá trị hiện tại bằng `expected` theo phép so sánh của biến; có hiệu ứng volatile |
| `compareAndExchange(receiver, expected, update)` | Giá trị đã quan sát (*witness*) | Trả giá trị thực tế tại thời điểm CAS; ghi khi witness bằng expected |
| `getAndSet(receiver, update)` | Giá trị cũ | Đổi giá trị nguyên tử và trả bản cũ |
| `getAndAdd(receiver, delta)` | Giá trị cũ | Cộng nguyên tử vào kiểu số được hỗ trợ, như `int`/`long` |
| `getAndBitwiseOr` / `getAndBitwiseAnd` / `getAndBitwiseXor` | Giá trị cũ | Cập nhật bit nguyên tử cho kiểu hỗ trợ |
| `weakCompareAndSetPlain` và các biến thể `weakCompareAndSet...` | `boolean` | CAS yếu, **có thể thất bại giả** dù giá trị so sánh khớp; yêu cầu kiểm tra/retry phù hợp |

**Đọc đúng kết quả CAS:**

```java
boolean updated = COUNT.compareAndSet(counter, 4, 5); // true nếu đang là 4
int observed = (int) COUNT.compareAndExchange(counter, 5, 6);
// observed = 5 nếu CAS thành công; nếu đang là giá trị khác thì không ghi và trả giá trị đó
```

Với biến kiểu tham chiếu, phép so sánh expected của CAS dùng **đồng nhất tham chiếu (`==`)**, không gọi `equals()`. Ví dụ, hai đối tượng khác nhau dù `equals` trả true vẫn không khớp trong CAS.

### Vì sao CAS thường cần vòng lặp?

Khi nhiều luồng cùng cập nhật một trạng thái phụ thuộc giá trị cũ, một luồng có thể đọc giá trị cũ rồi bị luồng khác thay đổi trước khi CAS. `compareAndSet` thất bại là tín hiệu thử lại với trạng thái mới:

```java
static void addTen(VarHandle handle, Counter counter) {
    for (;;) {
        int before = (int) handle.getVolatile(counter);
        int after = before + 10;
        if (handle.compareAndSet(counter, before, after)) {
            return;
        }
    }
}
```

Đây là **đoạn minh họa**, giả định đã có lớp `Counter` với field `int value` và một `VarHandle` trỏ đúng field đó. Với phép cộng đơn giản, `getAndAdd(counter, 10)` ngắn gọn và thường phù hợp hơn. Với phép tính phức tạp, cần cân nhắc side effect, contention và việc biểu thức tính lại sau thất bại CAS.

**ABA:** CAS chỉ biết giá trị hiện tại có bằng expected hay không. Nếu một biến lần lượt đổi A → B → A, CAS so với A vẫn có thể thành công dù đã có thay đổi trung gian. Thuật toán cần phát hiện chuyện đó phải lưu thêm version/stamp hoặc áp dụng cơ chế thích hợp khác.

### Memory ordering của các phép atomic

- `compareAndSet`, `compareAndExchange`, `getAndSet` và `getAndAdd` (bản không hậu tố) có hiệu ứng đọc/ghi volatile theo đặc tả riêng.
- Các biến thể `...Acquire` thường chỉ áp dụng ordering acquire ở phía đọc; `...Release` thường chỉ áp dụng ordering release ở phía ghi. Không giả định mọi biến thể mang đầy đủ hiệu ứng volatile.
- `weakCompareAndSetPlain` dùng ngữ nghĩa plain và có thể thất bại giả; những biến thể khác có hiệu ứng tương ứng trong tên.
- Atomicity không đồng nghĩa thuật toán không bao giờ bị tranh chấp, tự bảo đảm fairness, hay luôn kết thúc sau số bước cố định.

Nếu không rõ mode thấp hơn có đủ cho bất biến và quan hệ happens-before của thuật toán hay không, ưu tiên API atomic tiêu chuẩn hoặc phép có ngữ nghĩa volatile dễ lý giải hơn, rồi tối ưu theo bằng chứng.

## 6. Chương trình Java 17+: so sánh mode và chạy đa luồng

Tạo file **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static class Cell {
        int value;
    }

    static class Message {
        int payload;
        boolean ready;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException, InterruptedException {
        VarHandle value = MethodHandles.lookup()
                .findVarHandle(Cell.class, "value", int.class);
        VarHandle ready = MethodHandles.lookup()
                .findVarHandle(Message.class, "ready", boolean.class);

        Cell cell = new Cell();

        // 1. Plain: thao tác đơn luồng, chưa có chia sẻ.
        value.set(cell, 3);
        System.out.println("plain=" + (int) value.get(cell));

        // 2. Volatile: đọc/ghi riêng lẻ với hiệu ứng volatile.
        value.setVolatile(cell, 4);
        System.out.println("volatile=" + (int) value.getVolatile(cell));

        // 3. Atomic compare-and-set và read-modify-write.
        boolean updated = value.compareAndSet(cell, 4, 5);
        System.out.println("CAS=" + updated
                + ", value=" + (int) value.getVolatile(cell));

        int old = (int) value.getAndAdd(cell, 2);
        System.out.println("getAndAdd old=" + old
                + ", value=" + (int) value.getVolatile(cell));

        int witness = (int) value.compareAndExchange(cell, 7, 9);
        System.out.println("exchange witness=" + witness
                + ", value=" + (int) value.getVolatile(cell));

        // 4. Nhiều luồng tăng cùng biến bằng phép atomic.
        value.setVolatile(cell, 0);
        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    value.getAndAdd(cell, 1);
                }
            });
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("atomic counter="
                + (int) value.getVolatile(cell));

        // 5. Producer/consumer: publish một payload bằng release/acquire.
        Message message = new Message();
        Thread reader = new Thread(() -> {
            while (!(boolean) ready.getAcquire(message)) {
                Thread.onSpinWait(); // Chỉ dùng spin để minh họa.
            }
            System.out.println("published payload=" + message.payload);
        });
        reader.start();

        message.payload = 42;
        ready.setRelease(message, true);
        reader.join();
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac VarHandleModesDemo.java
java VarHandleModesDemo
```

Kết quả:

```text
plain=3
volatile=4
CAS=true, value=5
getAndAdd old=5, value=7
exchange witness=7, value=9
atomic counter=40000
published payload=42
```

**Vì sao kết quả đúng?**

1. Plain và volatile ở đầu ví dụ chạy tuần tự trong `main`, nên lần đọc thấy giá trị vừa ghi. Không dùng những thao tác plain đó để suy ra quy tắc chia sẻ giữa các luồng.
2. CAS thấy `4` rồi đổi thành `5`. `getAndAdd` thêm `2`, trả lại giá trị cũ `5`; `compareAndExchange` thấy `7` rồi đổi thành `9`.
3. Bốn worker, mỗi worker tăng `10_000` lần bằng `getAndAdd` trên cùng field. Các phép tăng không bị mất cập nhật, nên tổng là `40_000` sau khi `join` cả bốn luồng.
4. Producer ghi `message.payload = 42` trước `ready.setRelease(message, true)`. Reader chỉ đọc payload sau khi `getAcquire` đã thấy cờ `true`. Đây là một giao thức publish/consume một lần; cờ ban đầu mặc định `false`.
5. `Thread.join()` khiến luồng main đợi kết thúc worker và reader, nhờ đó kết quả in không bị bỏ sót. Vòng chờ trong reader không nhằm làm mẫu cho production.

Đoạn code dùng `Thread.onSpinWait()` từ Java 9, `VarHandle` từ Java 9 và không cần thư viện bên ngoài.

## 7. Lựa chọn mode theo bài toán

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Dữ liệu cục bộ trong một luồng | `get`/`set` (hoặc truy cập field trực tiếp) | Không cần synchronization bổ sung |
| Flag dừng hoặc trạng thái chia sẻ đơn giản | `getVolatile`/`setVolatile`, hoặc field `volatile` | Dễ diễn giải hiệu ứng volatile |
| Producer xuất bản payload một lần | `setRelease` + `getAcquire` trên flag | Tạo ordering cần thiết khi consumer thấy flag được publish |
| Nhiều luồng cộng chung một bộ đếm | `getAndAdd` hoặc `AtomicInteger` | Mỗi lần cộng nguyên tử, không mất cập nhật |
| Cập nhật nếu trạng thái chưa đổi | `compareAndSet`, hoặc `compareAndExchange` nếu cần witness | Kiểm tra và ghi trong một phép atomic |
| Phải đồng bộ bất biến của nhiều field hoặc một critical section | `synchronized`/`Lock` hoặc thiết kế trạng thái bất biến | Atomic một field không đủ bảo vệ cả nhóm |

`VarHandle` hữu ích trong mã thư viện hiệu năng thấp tầng và xây dựng primitive đồng bộ. Ứng dụng thông thường nên ưu tiên `AtomicInteger`, `AtomicReference`, `BlockingQueue`, `Lock`, `synchronized` hoặc các cấu trúc `java.util.concurrent` khi chúng đáp ứng trực tiếp nhu cầu. Chúng dễ review hơn và giảm rủi ro sử dụng sai ngữ nghĩa bộ nhớ.

## 8. Lỗi phổ biến và cách kiểm tra

**Lỗi 1 — Tưởng `volatile` làm `++` nguyên tử.** Truy cập volatile riêng lẻ chỉ bảo đảm ngữ nghĩa cho lần đọc/ghi đó. Để tăng an toàn khi tranh chấp, dùng `getAndAdd` hoặc cập nhật CAS hợp lệ.

**Lỗi 2 — Dùng plain để báo hiệu giữa các luồng.** Nếu consumer chỉ gọi `get` để xem flag mà không có một cơ chế đồng bộ khác, chương trình thiếu bảo đảm visibility/order mong muốn. Dùng acquire/release hoặc volatile theo đúng giao thức.

**Lỗi 3 — Viết payload sau release.** Nếu producer gọi `setRelease(ready, true)` trước rồi mới gán payload, consumer có thể quan sát cờ mà chưa có giá trị payload mới. Luôn thiết lập dữ liệu cần xuất bản **trước** release.

**Lỗi 4 — Acquire từ biến A nhưng release ở biến B.** Không tự động có quan hệ đồng bộ mong muốn. Cần một giao thức kết nối trên đúng vị trí và đúng sự kiện publish/consume.

**Lỗi 5 — Trộn mode trên cùng biến theo cảm tính.** `get` qua `VarHandle` không tự kế thừa volatile từ khai báo field. Hãy chọn một giao thức nhất quán và xem lại đặc tả khi phối hợp modes.

**Lỗi 6 — Cho rằng CAS thành công nghĩa là trạng thái chưa từng đổi.** Hiện tượng ABA cho thấy trạng thái có thể thay đổi trung gian rồi quay về giá trị dự kiến.

**Lỗi 7 — Gọi mode không được hỗ trợ.** Handle cho `final` không cho phép ghi; không phải mọi thao tác số/bit đều hợp lệ với mọi kiểu. Kiểm tra `isAccessModeSupported(VarHandle.AccessMode.XXX)` khi dùng handle trừu tượng.

**Lỗi 8 — Sai kiểu kết quả do các lời gọi signature-polymorphic.** Với field `int`, viết `(int) handle.get(obj)`; với field `boolean`, viết `(boolean) handle.getAcquire(obj)`. Sai kiểu/tọa độ có thể khiến chương trình lỗi lúc chạy.

### Tự kiểm tra

1. Vì sao hai luồng cùng dùng `getVolatile` + `setVolatile` để tăng counter vẫn có thể mất cập nhật?
2. Khi consumer thấy `ready == true` bằng `getAcquire`, những ghi nào của producer được publish qua `setRelease`?
3. `compareAndSet` và `compareAndExchange` khác nhau về giá trị trả về như thế nào?
4. Nếu một thuật toán cần bảo vệ đồng thời `balance` và `version`, cập nhật atomic một field riêng lẻ đã đủ chưa?
5. Vì sao có thể dùng field `payload` bình thường trong ví dụ producer/consumer, nhưng không được ghi lại payload tùy ý sau khi đã publish?
6. Nếu không cần tối ưu thấp tầng, vì sao `AtomicInteger` thường dễ dùng hơn tự quản lý `VarHandle`?

### Tài liệu tra cứu

- [Java SE 17 — `VarHandle` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): danh sách các access mode, tính atomic và memory ordering.
- [Java SE 17 — `MethodHandles` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): tạo handle và yêu cầu quyền lookup.
- [Java Language Specification `17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): `happens-before`, `synchronization order` và các quy tắc bộ nhớ liên quan.
