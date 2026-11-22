# 9.10 Quan hệ với Java Memory Model, memory fence và rủi ro trộn nhiều chế độ truy cập

`VarHandle` cho phép truy cập một biến (field instance, field static hoặc phần tử mảng) với **nhiều chế độ nhất quán bộ nhớ** ngay tại từng lời gọi: `get`/`set` (plain), `getOpaque`/`setOpaque` (opaque), `getAcquire`/`setRelease` (acquire/release), `getVolatile`/`setVolatile` (volatile), cùng các thao tác cập nhật nguyên tử như `compareAndSet` và `getAndAdd`. Các phương thức `VarHandle.fullFence()`, `acquireFence()`, `releaseFence()`, `loadLoadFence()`, `storeStoreFence()` cung cấp ràng buộc sắp xếp bộ nhớ độc lập với một VarHandle cụ thể.

Sự linh hoạt này có giá: **đọc/ghi cùng một địa chỉ bằng nhiều mode khác nhau không tự động tạo ra cùng bảo đảm**. Một flag viết bằng `setOpaque` rồi đọc bằng `getVolatile` không thể được coi như cặp `setRelease`–`getAcquire` để publish dữ liệu kèm theo. Một lần gọi `fullFence()` cũng **không tự biến** hai biến plain thành một giao thức giao tiếp an toàn.

Bài này làm rõ cách API VarHandle nối với Java Memory Model (JMM), ý nghĩa của các fence, cách thiết kế giao thức publish/consume, nguy cơ *mixed-mode access*, sự khác nhau giữa **atomicity**, **visibility**, **ordering** và **progress**, cùng cách kiểm thử. Các ví dụ biên dịch với Java 17+.

## 1. Bốn câu hỏi phải tách riêng

Khi thiết kế truy cập dữ liệu đồng thời, đừng hỏi chung chung “lệnh này thread-safe không?”. Hãy trả lời bốn câu hỏi sau:

1. **Atomicity (tính nguyên tử)**: một thao tác đọc/ghi hoặc read-modify-write có bị chia nhỏ/torn hay bị thread khác chen vào giữa thao tác không?
2. **Visibility (khả năng quan sát)**: một thread có thể thấy những giá trị nào do thread khác ghi? Điều gì tạo điều kiện cho các write được công bố tới reader?
3. **Ordering (thứ tự quan sát)**: những truy cập khác có được phép xuất hiện như thể bị đảo thứ tự trước/sau thao tác này không?
4. **Progress/liveness**: reader có được bảo đảm cuối cùng sẽ thấy flag mới hay thoát vòng lặp không? Đây là câu hỏi khác với memory ordering và còn phụ thuộc lịch chạy, giao thức và các điều kiện khác.

Ví dụ `counter++` gồm đọc, cộng và ghi. Ngay cả khi mỗi read và write dùng mode `volatile`, **cặp đọc–ghi** không phải một thao tác read-modify-write nguyên tử; hai writer có thể cùng đọc giá trị cũ và ghi đè kết quả của nhau. Muốn tăng bộ đếm đồng thời, hãy dùng `getAndAdd` hoặc vòng lặp CAS phù hợp.

Ngược lại, `getOpaque`/`setOpaque` bảo đảm truy cập một biến có tính nguyên tử bitwise theo tài liệu API nhưng **không có bảo đảm sắp xếp các biến payload khác** như một cặp release/acquire. Không thể suy ra “đã atomic thì an toàn để publish toàn bộ object”.

### 1.1. JMM cho phép compiler/CPU tối ưu, trong giới hạn đã định

Java Memory Model (JLS `17.4) xác định các hành vi quan sát giữa thread. **Program order** là thứ tự hành động của từng thread theo ngữ nghĩa nguồn; **synchronization order** là thứ tự tổng của các synchronization actions; **synchronizes-with** và quan hệ bắc cầu **happens-before** (HB) xác định các ràng buộc liên thread.

Hình dung hai thread:

```java
// Thread A
payload = 42;
ready = true;

// Thread B
if (ready) {
    System.out.println(payload);
}
```

Đây chỉ là mã minh họa: nếu `ready` và `payload` đều truy cập plain mà không có đồng bộ khác, không thể suy ra hễ B thấy `ready == true` thì B buộc phải thấy `payload == 42`. Các hành vi quan sát có thể khác với thứ tự ta đọc mã nguồn, vì chương trình chưa thiết lập ràng buộc liên thread thích hợp.

**Happens-before không đơn giản là “lệnh nguồn A xuất hiện trước B”**. Thứ tự trong một thread tạo cạnh HB nội bộ; để bắc cầu sang thread khác, cần một cơ chế liên thread thích hợp, ví dụ thao tác `volatile` tương ứng, monitor lock/unlock, thread start/join hoặc giao thức truy cập bộ nhớ có hiệu ứng release/acquire được tài liệu VarHandle quy định.

Nếu chương trình đã có cơ chế đồng bộ khác (ví dụ cả hai thread thực thi bên trong cùng monitor), plain access có thể an toàn trong phạm vi monitor đó. Không nên kết luận tất cả plain access đều sai; cái sai là **dùng plain access không có một giao thức đồng bộ đủ mạnh**.

## 2. Bản đồ access mode VarHandle theo memory effect

Một `VarHandle` là một tham chiếu có kiểu đến biến. **Mode nằm ở phương thức gọi**, không bị cố định chỉ vì object VarHandle được tạo như thế nào.

| Cặp/nhóm API | Mức bảo đảm quan trọng | Khi phù hợp |
| --- | --- | --- |
| `get` / `set` | *Plain*: ngữ nghĩa truy cập non-volatile; không tạo ràng buộc ordering liên thread của volatile | Dữ liệu chỉ dùng một thread, hoặc đã được bảo vệ bằng đồng bộ khác |
| `getOpaque` / `setOpaque` | Truy cập bitwise-atomic và coherent cho **cùng một biến**, có tính program-order đối với chính biến đó; **không** publish payload như release/acquire | Một số trạng thái/flag độc lập chỉ cần coherent visibility hạn chế |
| `getAcquire` | Read với hiệu ứng *acquire*: các load/store sau không được quan sát như xảy ra trước read này | Nhận công bố từ matching release |
| `setRelease` | Write với hiệu ứng *release*: các load/store trước không được quan sát như xảy ra sau write này | Công bố payload đã chuẩn bị trước đó |
| `getVolatile` / `setVolatile` | Ngữ nghĩa như đọc/ghi field `volatile`; các volatile operations có thứ tự tổng với nhau, mạnh hơn acquire/release | Flag hoặc trạng thái cần hợp đồng volatile rõ ràng, phối hợp nhiều thao tác volatile |
| `compareAndSet`, `getAndSet`, `getAndAdd` | Read-modify-write nguyên tử với hiệu ứng bộ nhớ như các truy cập volatile tương ứng | CAS, bộ đếm/đổi trạng thái atomic |
| Biến thể `...Acquire` / `...Release` của RMW | Atomic update vẫn nguyên tử; hiệu ứng ordering đọc/ghi có thể **bất đối xứng** và yếu hơn mode mặc định | Thuật toán đã chứng minh chỉ cần phía acquire hoặc release |
| `weakCompareAndSetPlain` | Weak CAS nguyên tử nhưng có thể thất bại giả dù giá trị đang khớp; hiệu ứng memory order plain | Thuật toán có retry và tự kiểm soát ordering |

**Không phải mọi mode đều dùng được với mọi biến.** Ví dụ, một `VarHandle` trỏ đến field `final` không hỗ trợ write/atomic-update; gọi mode không được hỗ trợ dẫn đến `UnsupportedOperationException`. Có thể hỏi `isAccessModeSupported(VarHandle.AccessMode.…)` trước khi dùng.

### 2.1. Plain có giới hạn atomicity khác Opaque

Theo JDK 17, plain `get`/`set` được bảo đảm atomic bitwise đối với reference và primitive tối đa 32 bit; với `long`/`double` trên một số nền tảng 32-bit có thể không được bảo đảm như các mode mạnh hơn. Các read/write mode khác như opaque, acquire/release, volatile có bảo đảm atomic bitwise theo tài liệu VarHandle. Đây là **atomicity của một lần truy cập biến**, không có nghĩa tổ hợp đọc–sửa–ghi đã atomic.

Cụm “coherently ordered” của opaque chỉ liên quan đến **cùng variable**. Nó không cho phép suy ra mọi trường trong một object được reader quan sát như một giao dịch nguyên khối.

### 2.2. Atomicity và ordering là hai trục độc lập

Ví dụ:

- `getAndAdd(counter, 1)` là một atomic RMW, tránh lost update trên counter và dùng memory effect của mode tương ứng.
- `getVolatile(counter)` rồi `setVolatile(counter, old + 1)` là **hai thao tác riêng**. Volatile ordering mạnh không biến cặp này thành một atomic increment.
- `setRelease(flag, true)` có hiệu ứng publish các write trước đó khi consumer đọc với matching acquire, nhưng không bảo đảm một writer khác không đồng thời ghi đè cùng flag/payload; giao thức ownership vẫn phải được thiết kế.
- `getOpaque(flag)` có thể đọc một giá trị coherent của flag, nhưng không đủ để đọc plain payload đã được writer thiết lập trước `setOpaque(flag, true)` như một bản ghi được công bố.

## 3. Release → acquire: mẫu publish/consume đúng

Giả sử chỉ có **một writer**, publish **một lần**, sau đó payload không bị thay đổi. Thread writer:

```java
message.id = 17;
message.text = "confirmed";
PUBLISHED.setRelease(message, true);
```

Thread reader:

```java
while (!(boolean) PUBLISHED.getAcquire(message)) {
    Thread.onSpinWait();
}
int id = message.id;
String text = message.text;
```

Hai đoạn này là minh họa, `PUBLISHED` là VarHandle tới field `boolean published`. Trật tự:

```text
WRITER                          READER
message.id = 17
message.text = "confirmed"
PUBLISHED.setRelease(true)  ──>  PUBLISHED.getAcquire() == true
                                 read message.id
                                 read message.text

publish các write trước release      consume sau matching acquire
```

Theo đặc tả VarHandle, **đọc acquire ghép với write release tương ứng** tạo ordering để những truy cập reader *sau acquire* không quan sát payload như thể được thực hiện trước những write writer *trước release*. Điều kiện **reader thực sự quan sát publication phù hợp** là trọng tâm; không phải bất kỳ `getAcquire` nào cũng lập tức bảo đảm thấy một write tương lai.

### 3.1. Những điều kiện không được bỏ qua

- Writer hoàn thành ghi payload **trước** `setRelease`.
- Reader chỉ đọc payload **sau** khi `getAcquire` xác nhận flag công bố, không đọc trước rồi hy vọng fence sửa sai.
- Trên cùng flag, các bên dùng cặp mode tương thích và cùng cơ chế ownership. Nếu writer vẫn sửa payload song song sau khi publish, bản thân flag không bảo vệ lần sửa mới.
- Nếu có nhiều writer, reader hoặc nhiều vòng publish/reuse, cần state machine, sequence number, ownership, CAS hoặc khóa phù hợp. Một boolean `ready` đơn thuần dễ gặp ABA hoặc đọc dữ liệu của vòng khác.
- `Thread.onSpinWait()` chỉ là gợi ý tối ưu cho spin loop; nó **không phải fence**, không tạo HB và không bảo đảm fairness/liveness. Spin vô hạn cũng hao CPU, nên chương trình thật nên cân nhắc blocking, timeout hoặc các primitive cấp cao hơn.

### 3.2. Chương trình Java 17+ thực thi được: hai thread

Tạo tệp **`VarHandlePublicationDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class VarHandlePublicationDemo {
    static final class Message {
        int id;
        String text;
        boolean published;
    }

    static final VarHandle PUBLISHED;
    static {
        try {
            PUBLISHED = MethodHandles.lookup()
                    .findVarHandle(Message.class, "published", boolean.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Message message = new Message();
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> error = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
            while (!(boolean) PUBLISHED.getAcquire(message)) {
                if (System.nanoTime() >= deadline) {
                    error.set(new IllegalStateException("publication timed out"));
                    return;
                }
                Thread.onSpinWait();
            }
            observed.set(message.id + ":" + message.text);
        }, "reader");
        Thread writer = new Thread(() -> {
            message.id = 17;
            message.text = "confirmed";
            PUBLISHED.setRelease(message, true);
        }, "writer");

        reader.start();
        writer.start();
        writer.join();
        reader.join();
        if (error.get() != null) {
            throw new IllegalStateException("reader did not observe publication", error.get());
        }
        System.out.println("published=" + observed.get());
    }
}
```

Lệnh chạy:

```bash
javac --release 17 VarHandlePublicationDemo.java
java VarHandlePublicationDemo
```

Trong một lần chạy thành công, `stdout` là:

```text
published=17:confirmed
```

**Giải thích rõ các loại đồng bộ:** phép truyền payload từ writer sang reader dựa vào `PUBLISHED.setRelease` / `PUBLISHED.getAcquire`. `Thread.join()` giúp **main** chờ hai thread hoàn thành trước khi in kết quả; nó không phải phép đồng bộ thay thế cặp release/acquire giữa writer và reader. `AtomicReference` dùng để chuyển kết quả và lỗi từ reader sang main mà không tạo race mới cho trạng thái kết quả.

Timeout trong ví dụ là cơ chế phòng trường hợp lỗi/lập lịch bất thường, **không phải** một bảo đảm tiến triển từ VarHandle: nếu thread không được chạy, có thể lỗi timeout thay vì dòng output. Một bài test chạy thành công không chứng minh mọi interleaving đều an toàn; kết luận đúng đắn dựa trên hợp đồng memory model.

## 4. Volatile: mạnh hơn acquire/release ở điểm nào?

`getVolatile` và `setVolatile` mang ngữ nghĩa như field Java khai báo `volatile`. Các thao tác volatile nằm trong một **synchronization order** tổng và phù hợp với program order; thao tác volatile trên một biến cũng có quan hệ đọc/ghi theo JMM. JDK VarHandle mô tả rằng volatile mode có thêm bảo đảm thứ tự tổng giữa các volatile operations, bên cạnh các hiệu ứng của acquire/release.

Với một flag công bố dữ liệu đơn giản, cả hai cặp này thường biểu đạt được giao thức phù hợp:

```java
// Phương án A: release/acquire
READY.setRelease(box, true);
boolean ready = (boolean) READY.getAcquire(box);

// Phương án B: volatile/volatile
READY.setVolatile(box, true);
boolean ready2 = (boolean) READY.getVolatile(box);
```

Đây là hai cặp **minh họa độc lập**, không phải bốn lệnh để chạy liên tiếp thay cho một protocol thực. Ở phương án B, các truy cập khác vẫn phải được đặt đúng vị trí trước publish và sau consume; mode mạnh **không** tự làm các thao tác nghiệp vụ thành một transaction atomic.

**Không diễn đạt volatile là “mọi thread thấy ngay lập tức”**: thời gian scheduling, blocking hay tiến triển không được bảo đảm chỉ vì biến là volatile. Volatile đưa ra quy tắc visibility/ordering có thể dựa vào, không phải một cam kết về thời hạn.

### 4.1. Mode truy cập thắng modifier của field

Một chi tiết rất dễ bỏ sót từ Javadoc JDK 17: **access mode của VarHandle ghi đè memory ordering implied bởi khai báo biến**. Nếu field khai báo `volatile int marker` nhưng gọi `VH.get(instance)`, phép truy cập ấy mang **ngữ nghĩa plain**; gọi `VH.setRelease(instance, x)` mang release semantics; còn đọc/ghi trực tiếp qua Java expression `instance.marker` vẫn mang semantics của field `volatile`.

Không được mặc định:

> “Tôi đã khai báo field là volatile, vậy mọi lời gọi VarHandle tới nó cũng volatile.”

Điều này sai. Điều cần review là **mọi đường truy cập thực tế**, bao gồm truy cập source-level, Reflection, VarHandle và những nơi có thể alias cùng địa chỉ.

## 5. Ví dụ Java 17+ độc lập: cùng VarHandle, nhiều mode và fence

Tạo tệp **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static final class State {
        int payload;
        boolean ready;
        volatile int marker;
        int counter;
    }

    static final VarHandle READY;
    static final VarHandle MARKER;
    static final VarHandle COUNTER;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            READY = lookup.findVarHandle(State.class, "ready", boolean.class);
            MARKER = lookup.findVarHandle(State.class, "marker", int.class);
            COUNTER = lookup.findVarHandle(State.class, "counter", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        State state = new State();
        state.payload = 42;
        READY.setRelease(state, true);
        System.out.println("ready/acquire=" + (boolean) READY.getAcquire(state));
        System.out.println("payload=" + state.payload);

        READY.setOpaque(state, false);
        System.out.println("ready/opaque=" + (boolean) READY.getOpaque(state));

        MARKER.set(state, 7);       // Plain despite 'volatile' declaration.
        System.out.println("marker/plain=" + (int) MARKER.get(state));
        MARKER.setVolatile(state, 8);
        System.out.println("marker/volatile=" + (int) MARKER.getVolatile(state));

        int old = (int) COUNTER.getAndAdd(state, 3);
        System.out.println("counter/old=" + old);
        System.out.println("counter/now=" + (int) COUNTER.getVolatile(state));

        VarHandle.loadLoadFence();
        VarHandle.storeStoreFence();
        VarHandle.acquireFence();
        VarHandle.releaseFence();
        VarHandle.fullFence();
        System.out.println("fences=5");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 VarHandleModesDemo.java
java VarHandleModesDemo
```

`stdout` đúng:

```text
ready/acquire=true
payload=42
ready/opaque=false
marker/plain=7
marker/volatile=8
counter/old=0
counter/now=3
fences=5
```

**Chú ý giới hạn của ví dụ:** tất cả thao tác trong `VarHandleModesDemo` thực hiện trên **một thread**. Vì vậy nó chứng minh cách tra VarHandle, cú pháp mode, signature-polymorphic return cast và thao tác fence có thật trong API; nó **không phải bằng chứng** về visibility giữa thread. Sự khác nhau giữa memory mode chỉ trở nên quan trọng khi có những interleaving và đường truy cập từ các thread khác.

Mỗi VarHandle ở đây trỏ đến field instance, nên mỗi lời gọi nhận receiver `state` trước giá trị mới (nếu là write). Vì return type của `READY` là `boolean` và của `COUNTER` là `int`, biểu thức đọc có cast `(boolean)` / `(int)` tương ứng. Mode có chữ ký tại call site không khớp kiểu VarHandle có thể gây `WrongMethodTypeException`.

## 6. Memory fence là gì, và không phải là gì?

Memory fence chỉ định **ràng buộc thứ tự** giữa những load/store nằm trước và sau fence trong thread hiện tại, theo loại fence. VarHandle cung cấp **năm static methods** sau:

| Fence | Ràng buộc ordering theo Javadoc JDK 17 | Tránh diễn giải sai |
| --- | --- | --- |
| `VarHandle.loadLoadFence()` | Load **trước** không bị reorder với load **sau** | Không ràng buộc đầy đủ store hoặc tạo publication |
| `VarHandle.storeStoreFence()` | Store trước không bị reorder với store sau | Không thay thế acquire của reader |
| `VarHandle.acquireFence()` | Load trước không bị reorder với load **và store** sau | Không nhất thiết ràng buộc mọi store trước fence |
| `VarHandle.releaseFence()` | Load và store trước không bị reorder với store sau | Không tự gắn một reader/flag cụ thể vào fence |
| `VarHandle.fullFence()` | Load và store trước không bị reorder với load và store sau | Không tự tạo khóa, CAS hay giao thức HB toàn cục |

Đây là mô tả về **observable reordering constraints**, không phải hứa hẹn JVM luôn phát ra chính xác một instruction fence phần cứng trong mọi trường hợp. JIT có thể dùng cơ chế cụ thể phù hợp kiến trúc CPU, thậm chí bỏ instruction nếu bảo đảm đã được thỏa theo cách khác.

### 6.1. Hai sự thật cực kỳ quan trọng

**Thứ nhất, một fence không kèm biến đồng bộ.** Ví dụ:

```java
// Không phải giao thức publish an toàn chỉ vì có fence.
payload = 42;
VarHandle.fullFence();
ready = true;                 // plain write

// Thread khác:
if (ready) {                 // plain read
    VarHandle.fullFence();
    use(payload);
}
```

Các đoạn trên chỉ là *anti-pattern minh họa*: không đảm bảo cặp truy cập flag plain thiết lập publication/consumption an toàn. Fence ràng buộc reordering ở mỗi thread nhưng **không tự tạo** sự kiện đồng bộ giữa hai thread, không bảo đảm reader nhìn thấy flag mới đúng lúc, và không tự gắn cạnh happens-before qua biến `ready`.

**Thứ hai, fence không phải thao tác read-modify-write nguyên tử.** `fullFence` trước và sau `counter++` không biến `counter++` thành `getAndAdd`. Vẫn có thể lost update nếu hai thread cùng đọc số cũ rồi cùng ghi số đã tăng.

### 6.2. Nếu đã có mode phù hợp, có cần thêm fence không?

Ở mẫu publish/consume thông thường, `setRelease` và `getAcquire` **đã mang memory effects cần thiết**. Chèn `fullFence` trước/sau cả hai phía theo thói quen có thể làm code khó hiểu và tốn chi phí mà không cải thiện giao thức.

Ví dụ đúng về mặt ý tưởng:

```java
// Writer: chuẩn bị dữ liệu, công bố một lần.
box.payload = 42;
READY.setRelease(box, true);

// Reader: chỉ đọc payload sau khi nhìn thấy ready.
if ((boolean) READY.getAcquire(box)) {
    consume(box.payload);
}
```

Đây là đoạn minh họa với `READY` và `consume` đã được định nghĩa phù hợp; muốn chạy độc lập hãy dùng `VarHandlePublicationDemo` ở trên. Trong giao thức single-writer/single-publication, không cần tự thêm `releaseFence` hoặc `acquireFence` ngoài các thao tác này.

Khi cần fence rời trong thuật toán lock-free phức tạp, **phải chứng minh** nơi nó tạo ràng buộc gì, biến nào được đọc/ghi theo mode nào, và cơ chế nào liên kết các thread. Không suy diễn máy móc từ tên lệnh C/C++ hay kiến trúc x86/ARM: tài liệu VarHandle đã nói rõ hiệu ứng tương thích ở một số khía cạnh nhưng **khác ngữ nghĩa** với memory model của các ngôn ngữ đó.

## 7. Rủi ro trộn nhiều chế độ trên cùng biến

Javadoc `VarHandle` cảnh báo trực tiếp: access mode **override** memory-ordering effect của declaration; khi truy cập cùng biến bằng nhiều mode, JMM có thể cho phép kết quả bất ngờ. Trọng tâm review không phải “mode mạnh nhất từng xuất hiện ở đâu đó”, mà là **đường ghi công bố và đường đọc tiêu thụ có ghép đúng hay không**.

### 7.1. Bốn phối hợp có thể gây hiểu lầm

| Writer của flag | Reader của flag | Có thể giả định publish payload plain trước write của writer? |
| --- | --- | --- |
| `setRelease` | `getAcquire`, đọc đúng publication | **Có**, với điều kiện giao thức publish/consume đúng, payload không bị viết đè cạnh tranh |
| `setVolatile` | `getVolatile`, đọc publication phù hợp | **Có**, theo volatile semantics và JMM |
| `setOpaque` | `getVolatile` | **Không được suy ra**: writer chưa có release effect bảo vệ payload |
| `setRelease` | `getOpaque` | **Không được suy ra**: reader thiếu acquire effect cho các đọc payload tiếp theo |
| `setVolatile` | `get` (plain) | **Không được suy ra**: reader không thực hiện volatile/acquire read |
| `set` (plain) | `getVolatile` | **Không được suy ra**: writer không thực hiện release/volatile write |
| `setOpaque` | `getOpaque` | Coherent cùng flag, **không đủ** để publish payload ở biến khác |

Bảng xét **một giao thức chỉ dựa trên flag VarHandle**, không xét các cơ chế đồng bộ khác có thể đã bảo vệ dữ liệu. Nếu toàn bộ critical section được bảo vệ bằng lock đúng cách, việc đánh giá phải tính cả lock/unlock đó.

Đừng hiểu các ô “Không” là “chắc chắn sẽ chạy sai”; nghĩa chính xác là **không có cơ sở đặc tả để chứng minh an toàn theo giả định này**. Một JDK, CPU hay lịch chạy cụ thể có thể tạo kết quả như mong muốn hàng tỷ lần mà không biến anti-pattern thành đúng.

### 7.2. Anti-pattern: ghi opaque, đọc volatile

```java
// Giả sử Holder có int payload; volatile boolean ready;
// và READY là VarHandle đến Holder.ready.

// Thread writer
holder.payload = 42;
READY.setOpaque(holder, true);

// Thread reader
if ((boolean) READY.getVolatile(holder)) {
    int value = holder.payload; // Không được bảo đảm đã publish đúng.
}
```

Đây là đoạn minh họa không độc lập; **đừng dùng làm mẫu đồng bộ**. Dù reader dùng `getVolatile`, writer dùng `setOpaque` nên không có release write tương ứng theo protocol. Tương tự, việc đổi writer sang `setRelease` nhưng reader quay về `getOpaque` vẫn thiếu mắt xích acquire.

Sửa bằng **một cặp rõ ràng**, ví dụ:

```java
// Writer
holder.payload = 42;
READY.setRelease(holder, true);

// Reader (sau khi quan sát ready)
if ((boolean) READY.getAcquire(holder)) {
    int value = holder.payload;
}
```

Dùng `setVolatile`/`getVolatile` cũng là một giao thức đúng khi các giả định còn lại được đáp ứng. **Không tự “nâng” một đầu mà bỏ qua đầu kia**.

### 7.3. Cạm bẫy field khai báo volatile nhưng bị VarHandle đọc plain

```java
final class Status {
    volatile int code;
}

// Giả sử CODE là VarHandle trỏ tới Status.code:
int a = status.code;           // Java source volatile read.
int b = (int) CODE.get(status); // VarHandle plain read.
int c = (int) CODE.getVolatile(status); // Volatile mode.
```

Đây là đoạn minh họa; `Status`, `status` và `CODE` phải được khai báo/tra cứu trước khi chạy. Dù `a`, `b` và `c` đọc cùng field, **`b` không thừa hưởng volatile semantics** chỉ vì field có modifier `volatile`. Nếu một thư viện/framework dùng plain VarHandle trên field mà ứng dụng đọc/ghi trực tiếp qua `volatile`, phải review lại toàn bộ giao thức. Điều này đặc biệt nguy hiểm trong serializer, agent, mapper hoặc công cụ instrumentation dùng VarHandle thay cho đường truy cập Java thông thường.

### 7.4. Đọc thử bằng getOpaque không biến thành acquire vì có fence về sau

Một cám dỗ là dùng `getOpaque(flag)`, nếu thấy true thì gọi `acquireFence()` rồi đọc payload. Đừng mặc định cách này tương đương `getAcquire(flag)` hoặc tạo cặp đồng bộ chuẩn theo mọi điều kiện JMM. Cần phân tích đầy đủ các điều kiện về reads, writes, fences và quan hệ liên thread; không được lấy mô hình C/C++ rồi tự áp vào Java.

Ở mức ứng dụng, cách sáng sủa và dễ chứng minh hơn là gọi thẳng `getAcquire` tại điểm tiêu thụ, ghép với `setRelease` tại điểm công bố. Fence rời dành cho thuật toán thấp tầng có chứng minh và kiểm thử riêng.

## 8. Atomic update, CAS và sự khác nhau giữa nguyên tử với visibility

### 8.1. Lost update dù dùng volatile load/store

Mã sau **không phải tăng nguyên tử**:

```java
int old = (int) COUNTER.getVolatile(state);
COUNTER.setVolatile(state, old + 1);
```

Nếu hai thread đọc cùng `old==5`, cả hai đều có thể ghi `6`; kết quả đáng lẽ `7` đã bị mất một lượt tăng. Mỗi operation riêng có volatile semantics nhưng **chuỗi hai operation** không atomic.

Thay bằng:

```java
int previous = (int) COUNTER.getAndAdd(state, 1);
```

`getAndAdd` đọc giá trị cũ và cập nhật atomically; với mode mặc định nó có hiệu ứng memory như volatile read/write được JDK mô tả. Một giải pháp khác là vòng lặp `compareAndSet` có khả năng retry khi tranh chấp. Không thay thế CAS bằng tổ hợp get/set không được đồng bộ.

### 8.2. Các biến thể Acquire/Release của RMW

`getAndSetAcquire`, `getAndSetRelease`, `compareAndExchangeAcquire`, `compareAndExchangeRelease`, `getAndAddAcquire` và `getAndAddRelease` vẫn làm thao tác cập nhật **nguyên tử**, nhưng chọn hiệu ứng ordering cho phía đọc hoặc ghi khác với default volatile. Ví dụ, biến thể `…Acquire` ưu tiên hiệu ứng acquire trên **phía đọc**, trong khi phía ghi có thể chỉ như plain; `…Release` có hiệu ứng release **phía ghi** nhưng phía đọc có thể chỉ như plain.

Do đó:

- Đừng nhìn chữ “atomic” rồi suy ra mọi đường đọc/ghi của RMW đều volatile.
- Với một CAS dùng để **publish** dữ liệu, cần bảo đảm nhánh ghi thành công có memory effect release phù hợp; một biến thể chỉ-acquire không thay thế release cho writer.
- Với một RMW để **consume** dữ liệu được publish, cần bảo đảm phần đọc có acquire effect; một biến thể chỉ-release không tự giúp reader.
- Kiểm tra đặc tả của **chính method cụ thể**, vì read và write side có thể không đối xứng.
- `weakCompareAndSetPlain` còn có thể **thất bại giả**, do đó phải retry hoặc xử lý `false`; không dùng nó như phép kiểm tra “đã bị thread khác thay đổi chắc chắn”.

### 8.3. Trộn atomic RMW và plain write trên cùng state

Nếu một thread dùng `COUNTER.getAndAdd(state,1)` còn thread khác dùng `COUNTER.set(state,0)` mà không có protocol, reset plain có thể chen vào và phá giả định về các lần tăng. Tính atomic của `getAndAdd` **không làm cho mọi thao tác của các thread khác trở thành một transaction chung**.

Một thiết kế bộ đếm cạnh tranh phải quy định **tất cả đường cập nhật**: dùng CAS, atomic RMW, khóa hoặc thay nguyên trạng thái với cơ chế nhất quán. Đừng tối ưu một “đường nhanh” bằng `set` vì nó có vẻ chỉ là “reset đơn giản”.

## 9. Mối quan hệ với các cơ chế đồng bộ Java khác

| Cơ chế | Nguyên tắc |
| --- | --- |
| `synchronized`/monitor | Lock/unlock tạo quan hệ `synchronizes-with`; bảo vệ nhiều field trong critical section |
| `volatile` field | Truy cập source-level theo volatile semantics; tạo quy tắc HB tương ứng trên cùng volatile variable |
| `VarHandle.getVolatile/setVolatile` | Diễn đạt volatile access mode cho biến do handle trỏ đến |
| `VarHandle.getAcquire/setRelease` | Ordering có hướng để publish/consume theo cặp tương ứng, thường nhẹ hơn volatile toàn diện |
| `VarHandle.getOpaque/setOpaque` | Coherence/bitwise atomic của một biến mà không cung cấp publication payload như acquire/release |
| `VarHandle.*Fence` | Ràng buộc reordering giữa các truy cập lân cận trong thread; không phải mutex, CAS hay notification |
| `java.util.concurrent.atomic.*` | API sẵn cho các kiểu atomic thông dụng; thường là lựa chọn dễ review hơn tự dựng giao thức |
| `CountDownLatch`, `BlockingQueue`, `CompletableFuture` | Primitive cấp cao đưa ra cơ chế giao tiếp/handoff rõ ràng; nhiều ứng dụng không cần tự quản lý fence |

Không nên “chuyển hết” code dùng `synchronized` sang VarHandle chỉ để hy vọng nhanh hơn. Một critical section bảo vệ bất biến phức tạp trên nhiều biến có thể cần khóa. `VarHandle` lý tưởng khi cần điều khiển truy cập ở một biến hay xây thuật toán không khóa với một **chứng minh invariant, ordering và progress** rõ ràng.

### 9.1. Immutable/final không giải quyết mọi tình huống

Trường `final` được JMM dành những quy tắc khởi tạo riêng, nhưng object chứa các tham chiếu mutable hoặc các field không-final vẫn cần giao thức công bố và truy cập đúng. Chẳng hạn công bố một object rồi tiếp tục sửa `List` mutable bên trong bằng thread writer trong khi reader duyệt không đồng bộ có thể gây race dù reference tới list được lưu ở final field.

Khi dùng message passing, ưu tiên tạo một object immutable hoàn chỉnh rồi publish **tham chiếu** qua volatile/release-acquire; vẫn cần quản lý vòng đời và không chỉnh sửa mutable state sau publish.

## 10. Checklist thiết kế một protocol VarHandle an toàn

Trước khi đưa vào thư viện hoặc production, viết rõ các invariant sau:

1. **Biến chia sẻ nào?** Liệt kê field, array slot và mọi alias. Đừng chỉ liệt kê những nơi đã có VarHandle; còn đường truy cập field trực tiếp, Reflection, JNI, thư viện khác.
2. **Ai sở hữu quyền ghi?** Single writer hay multi-writer? Reader có được ghi lại state không? Trường nào sau publish còn mutable?
3. **Mode trên từng cạnh?** Với mỗi đường đọc/ghi cùng variable, ghi tên chính xác `get`, `setRelease`, `getAcquire`, `setVolatile`, `compareAndSet`… Không thay tất cả bằng chữ “atomic”.
4. **Dữ liệu gì được publish?** Các write payload xảy ra trước publication; reader chỉ consume sau khi thấy publication hợp lệ.
5. **Quan hệ liên thread ở đâu?** Chỉ ra cặp release/acquire hoặc volatile/monitor/concurrent primitive rõ ràng. Fence rời tự nó không trả lời được câu hỏi này.
6. **Atomicity của tổ hợp operation?** Nếu cần read-modify-write, dùng atomic RMW/CAS hoặc mutex. Một dãy volatile accesses không tự thành atomic transaction.
7. **Recycling và ABA?** Nếu flag reset/reuse, cần sequence number hoặc state machine; một lần flag chuyển true không đủ để phân biệt thế hệ dữ liệu.
8. **Progress và CPU?** Spin bao lâu, có backoff/park/block không, timeout xử lý gì? `Thread.onSpinWait` không tạo điều kiện HB.
9. **Khả năng hỗ trợ mode và kiểu?** Field final là read-only, kiểu VarHandle có coordinate types, các mode/atomic update có thể không được hỗ trợ. Xem `isAccessModeSupported`; kiểm tra đúng type và cast tại call site.
10. **Test trên những nền tảng nào?** CI nhiều JDK/OS/CPU, kiểm tra interleaving và tải; dùng công cụ concurrency stress (ví dụ JCStress). Một test “chạy một triệu lần không lỗi” không tự chứng minh đúng JMM.

### 10.1. Review bằng sơ đồ thay vì chỉ đọc code tuần tự

Một bản review có thể viết theo mẫu:

```text
Protocol: one-shot single-writer publication
Shared state: data (plain), ready (boolean accessed via VarHandle)
Writer owner: exactly one
  W1: write data
  W2: READY.setRelease(true)
Reader:
  R1: READY.getAcquire() observes true from W2
  R2: read data
Ordering argument:
  W1 before W2; matching release/acquire links W2 to R1; R2 after R1
Other writes to data: none after W2
Potential hazards: reader races before R1? no; reset/reuse? no
```

Nếu không thể điền được **“other writes”**, **“matching read/write”**, hoặc **“recycle policy”**, thuật toán chưa đủ rõ để coi là an toàn.

## 11. Kiểm thử JMM: không lấy stdout làm bằng chứng tuyệt đối

Ví dụ chạy thành công trong một thread hoặc một lần chạy hai thread không chứng minh mọi cách interleave. Nguy cơ concurrency đôi khi chỉ xuất hiện trên CPU khác hoặc khi JIT tối ưu theo điều kiện khác.

- **Không dùng `Thread.sleep` làm đồng bộ**. Ngủ một khoảng không tạo edge HB giữa các plain writes/reads.
- **Tránh “test vô tình làm đúng”**: thêm `join`, latch hoặc logging với lock vào đúng chỗ có thể tạo thêm synchronization, che race ban đầu. Hãy phân tích đồ thị HB của **code được test** lẫn logic test.
- **Không dựa vào việc x86 thường mạnh hơn ARM** để loại bỏ acquire/release trên đường cần bảo đảm. Code phải đúng theo Java specification, không chỉ đúng trên một kiến trúc.
- **Dùng stress test có cấu trúc**, ví dụ JCStress, ghi rõ các trạng thái outcome được đặc tả cho phép/cấm. Stress test là bằng chứng thực nghiệm bổ trợ, không thay thế lý luận.
- **Với kết quả không ổn định**, mô tả tập outcome hợp lệ thay vì công bố một `stdout` cố định cho data race. Bài này cố tình không đưa ví dụ “chắc chắn đọc ra 0” cho một race, vì như vậy là bịa hành vi không được bảo đảm.
- **Điều kiện progress** phải được xem riêng: một spin loop có thể được lập lịch kém hoặc bị timeout dù ordering logic đúng, nên hãy giới hạn thời gian và có chính sách xử lý.

## 12. Lỗi thường gặp và hướng khắc phục

| Triệu chứng / quan niệm sai | Vấn đề thật | Hướng sửa |
| --- | --- | --- |
| “`volatile` field nên `vh.get` là volatile read” | Access mode ghi đè modifier ordering | Dùng `getVolatile` hoặc đúng acquire protocol, audit mọi đường truy cập |
| Writer `setOpaque`, reader `getVolatile` | Thiếu release effect bên writer | Dùng cặp release/acquire hay volatile/volatile nhất quán |
| Writer `setRelease`, reader `getOpaque` | Reader thiếu acquire cho payload | Đổi reader sang `getAcquire` |
| Sau plain write gọi `fullFence` là đủ publish | Fence không tự xây cạnh đồng bộ liên thread | Tạo giao thức communication có release/acquire, volatile, lock hoặc concurrent primitive |
| Có CAS ở writer nên reader plain luôn thấy payload | Writer atomic không thay thế reader synchronization | Xem read side và mode phù hợp của state/flag |
| `getVolatile` rồi `setVolatile` là atomic increment | Hai operation có thể bị chen vào | Dùng `getAndAdd` hoặc CAS loop |
| `getOpaque` chắc sẽ thấy cập nhật ngay | Không có deadline/liveness guarantee | Thiết kế notification, blocking/backoff/timeout |
| `releaseFence` rồi `set` tương đương mọi trường hợp `setRelease` | Fence và mode không nên thay thế cơ học trong JMM | Dùng mode trực tiếp; nếu dùng fence phải có chứng minh giao thức |
| Chỉ có field `final` nên object luôn bất biến sâu | Object được tham chiếu có thể mutable | Defensive copy, không mutate sau publication, đồng bộ khi cần |
| Dùng plain trên `long`/`double` ở mọi nền tảng là atomic | Plain không bảo đảm bitwise atomic trên một số platform 32-bit | Dùng opaque/acquire/volatile hay atomic phù hợp |
| Test pass nghĩa là không có race | Một vài lịch chạy không bao phủ JMM | Lý luận HB, stress test và review invariants |
| `WrongMethodTypeException` từ `vh.get...` | Truyền sai coordinate type hoặc cast sai kiểu trả | Kiểm tra `varType()`, `coordinateTypes()`, `accessModeType(...)` |

## 13. Bài tập tự kiểm tra

**Bài A.** Hai thread cùng tăng `count` bằng `getVolatile` rồi `setVolatile`. Có đảm bảo mỗi increment được tính không?

**Đáp án:** Không. Hai operation riêng không atomic khi ghép; dùng `getAndAdd` hoặc vòng CAS.

**Bài B.** Field là `volatile boolean done`, nhưng writer gọi `DONE.setOpaque(obj,true)` và reader gọi `DONE.getVolatile(obj)` rồi đọc plain payload. Có thể dựa vào declaration để bảo đảm payload đã publish không?

**Đáp án:** Không. VarHandle writer dùng opaque mode, không có release effect tương ứng. Cần đồng nhất protocol.

**Bài C.** `VarHandle.fullFence()` ở cả hai thread có tự tạo synchronizes-with cho flag plain không?

**Đáp án:** Không. Fence đặt ràng buộc reordering riêng, không tự tạo giao tiếp liên thread. Dùng volatile hoặc release/acquire trên biến được chia sẻ phù hợp.

**Bài D.** Viết mode cho producer chuẩn bị object không thay đổi sau publish, consumer đọc flag và sau đó đọc payload.

**Đáp án:** Producer ghi payload rồi `FLAG.setRelease(holder,true)`; consumer đợi `(boolean)FLAG.getAcquire(holder)` là `true` từ publication phù hợp rồi mới đọc payload. Phải có điều kiện ownership/reuse đúng.

**Bài E.** `getOpaque` và `setOpaque` cho phép kết luận gì về payload ở **biến khác**?

**Đáp án:** Không kết luận payload đã được publish đúng như một cặp release/acquire. Opaque cho bitwise atomic và coherence của **biến đó** nhưng không tạo ordering liên thread cho payload khác.

**Bài F.** `VarHandle.releaseFence()` ràng buộc hướng nào? Có giống `acquireFence()` không?

**Đáp án:** Release fence ngăn **load/store trước** reorder với **store sau**; acquire fence ngăn **load trước** reorder với **load/store sau**. Không giống nhau.

**Bài G.** Vì sao `weakCompareAndSetPlain` có thể trả `false` khi value đang khớp? Có thể dựa vào `false` để kết luận vừa có writer khác không?

**Đáp án:** Vì weak CAS có thể thất bại giả; `false` không đủ chứng minh contention hay giá trị đã thay. Cần retry hoặc logic xử lý `false` thích hợp.

**Bài H.** Một giao thức single-use setRelease/getAcquire đúng nhưng writer tiếp tục sửa `payload` sau khi setRelease mà không đồng bộ. Reader có an toàn không?

**Đáp án:** Không suy ra an toàn. Publication bảo vệ write **trước release**; những ghi mới của writer sau publication có thể cạnh tranh với reader. Cần thêm ownership/handshake/lock hoặc tránh mutation sau publish.

## Nguồn chuẩn để đối chiếu

- [JDK 17 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): bảng access modes, các bảo đảm plain/opaque/acquire/release/volatile, cảnh báo mixed-mode, CAS và năm fence methods.
- [JDK 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `findVarHandle`, `findStaticVarHandle` và factory tạo handle.
- [JLS 17 — `17.4 Memory Model`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): program order, synchronization order, synchronizes-with, happens-before, các hành vi đọc/ghi hợp lệ.
- [JDK 17 — `java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): các lớp atomic phổ biến và ngữ nghĩa đồng bộ có thể dùng thay thuật toán tự chế.
- [JDK 17 — `Thread.onSpinWait`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait()): gợi ý hiệu năng cho spin loop, không phải primitive đồng bộ.

**Kết luận cần nhớ:** dùng mode theo **đúng đường truyền dữ liệu**. `setRelease` kết hợp `getAcquire` có ý nghĩa publish/consume; `setVolatile`/`getVolatile` mang semantics volatile mạnh hơn; opaque chỉ coherent cho biến đang truy cập; fence giới hạn reordering chứ không tự dựng happens-before; atomic RMW bảo vệ một cập nhật nhưng không chữa một giao thức visibility sai. **Trộn mode mà không có lập luận ordering cụ thể là rủi ro đúng đắn, không chỉ rủi ro hiệu năng.**
