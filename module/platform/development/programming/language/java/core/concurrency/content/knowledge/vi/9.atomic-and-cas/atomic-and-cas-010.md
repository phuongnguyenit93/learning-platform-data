# VarHandle: truy cập atomic và access mode trong Java

## 1. VarHandle là gì và giải quyết bài toán nào?

**`java.lang.invoke.VarHandle`** là API JDK (xuất hiện từ Java 9, dùng được trong Java 17+) mô tả cách truy cập **một biến** qua một handle có kiểu: trường instance, trường static hoặc phần tử mảng. Khác với một getter/setter thông thường, `VarHandle` cho phép chọn **access mode** tại mỗi lần truy cập: đọc/ghi plain, opaque, acquire/release, volatile và—khi kiểu biến hỗ trợ—các thao tác atomic như compare-and-set, compare-and-exchange, get-and-set, get-and-add.

Ví dụ, cùng một trường `int` có thể được đọc bằng `getVolatile` hoặc dùng `getAndAdd` để tăng nguyên tử. API đem những primitive cấp thấp của Java Memory Model (JMM) đến mã Java thuần, không cần dùng `sun.misc.Unsafe`.

Điều cần nhớ ngay từ đầu:

- **VarHandle không phải chính biến:** nó là một đối tượng mô tả cách truy cập đến vị trí biến. Dữ liệu thực vẫn nằm trong một instance, một trường static hoặc mảng.
- **Access mode quyết định memory-ordering semantics** của *lần truy cập*, không nên xem mọi `get`/`set` tự có tính chất như `volatile`.
- **Handle không tự khóa nhiều trường cùng lúc.** Atomicity của `getAndAdd` hoặc CAS áp dụng cho **một vị trí biến**; bất biến trải qua nhiều biến cần thiết kế riêng.
- **Quyền truy cập vẫn được kiểm tra** khi tạo handle qua `MethodHandles.Lookup`; VarHandle không phải cách hợp lệ để bỏ qua đóng gói hoặc quyền module.
- **Không mọi mode hợp lệ với mọi kiểu trường.** Có thể kiểm tra bằng `isAccessModeSupported(...)`; mode không hỗ trợ gây `UnsupportedOperationException` khi gọi.

Trong bài này ta dùng Java 17+, API JDK tiêu chuẩn và các ví dụ Java concurrency nói chung.

## 2. VarHandle xác định “biến nào” bằng kiểu và tọa độ

Có ba dạng quen thuộc:

| Loại vị trí | Cách tạo handle | Tọa độ khi gọi | Ví dụ |
| --- | --- | --- | --- |
| Trường **instance** | `lookup.findVarHandle(MyClass.class, "value", int.class)` | Đối tượng receiver | `VALUE.getVolatile(myObject)` |
| Trường **static** | `lookup.findStaticVarHandle(MyClass.class, "total", int.class)` | Không có receiver | `TOTAL.getVolatile()` |
| Phần tử **mảng** | `MethodHandles.arrayElementVarHandle(int[].class)` | Mảng và chỉ số | `ELEMENT.getVolatile(array, index)` |

`VarHandle.varType()` cho biết **kiểu giá trị** của biến; `coordinateTypes()` cho biết các **kiểu tọa độ** để xác định vị trí. Ví dụ handle trường instance `int value` có value type `int` và một coordinate là loại đối tượng chủ; handle phần tử `int[]` có hai coordinate: mảng `int[]` và chỉ số `int`.

### Tạo handle cho trường private

Tạo một handle trong **chính class khai báo trường**, thường dùng:

```java
private static final VarHandle VALUE;

static {
    try {
        VALUE = MethodHandles.lookup()
                .findVarHandle(MyClass.class, "value", int.class);
    } catch (ReflectiveOperationException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

Đây là **snippet** về pattern khởi tạo; `MyClass` và import chưa được khai báo ở đây. Ví dụ hoàn chỉnh ở phần sau.

`findVarHandle` xác nhận tên trường và kiểu trường tương ứng; nếu không tìm thấy hoặc không được phép truy cập thì có thể ném `NoSuchFieldException` hoặc `IllegalAccessException` (đều nằm trong nhóm `ReflectiveOperationException`). `MethodHandles.lookup()` mang quyền truy cập của class gọi nó; với class khác hoặc module khác, không được giả định có quyền xem trường private. `MethodHandles.privateLookupIn(...)` chỉ dùng khi đáp ứng quyền truy cập/module openness tương ứng, không phải lối tắt vượt bảo mật.

**Lưu ý với trường `final`:** một handle có thể đọc trường final khi được phép, nhưng các access mode ghi thường **không được hỗ trợ** cho final field. Không tìm cách sửa final field thông qua một mode không hợp lệ.

## 3. Các access mode và bảo đảm memory-ordering

VarHandle chia access mode theo ý nghĩa truy cập dữ liệu và ordering. Bảng sau là sơ đồ học tập; chi tiết có trong Javadoc của `VarHandle` và Java Memory Model.

| Mode/API điển hình | Cách hiểu thực hành | Lưu ý |
| --- | --- | --- |
| `get`, `set` | **Plain**: tương ứng truy cập thông thường, không thêm bảo đảm đồng bộ liên thread kiểu volatile | Không dùng plain để công bố state mutable không đồng bộ |
| `getOpaque`, `setOpaque` | **Opaque**: bảo đảm về tính nhất quán/coherence ở mức biến được truy cập, nhưng ordering yếu hơn acquire/release | Không tự công bố dữ liệu phụ thuộc ở trường khác |
| `getAcquire` | **Acquire read**: các truy cập tiếp theo trong thread đọc không bị đưa lên trước acquire theo các ràng buộc của mode | Hữu ích khi đọc cờ đã được writer công bố bằng release |
| `setRelease` | **Release write**: các truy cập trước đó của thread ghi không bị đẩy xuống sau release theo ràng buộc của mode | Thường dùng cùng `getAcquire` trên **cùng biến tín hiệu** |
| `getVolatile`, `setVolatile` | **Volatile**: đọc/ghi có các bảo đảm ordering/visibility của `volatile` | Mạnh hơn về ordering, nhưng hai lời gọi riêng không biến thành một transaction |
| `compareAndSet`, `compareAndExchange` | **Atomic conditional update** | Dùng khi phải kiểm tra giá trị hiện tại rồi ghi một cách nguyên tử |
| `getAndSet`, `getAndAdd` | **Atomic read–modify–write** (trên kiểu hỗ trợ) | Trả giá trị trước cập nhật; tránh lost update như `x++` thường |
| Các biến thể `...Acquire`, `...Release`, `...Plain` | Phiên bản với bảo đảm ordering được chọn cho thao tác atomic tương ứng | Chỉ dùng khi hiểu rõ hợp đồng bộ nhớ của mode đó |

Các cấp độ không có nghĩa **plain = luôn nhìn thấy ngay** hoặc **volatile = thao tác nghiệp vụ nhiều bước tự atomic**. JMM xác định các quan hệ giữa những hành động; việc mỗi lần chạy tình cờ quan sát được dữ liệu mới không phải bằng chứng an toàn.

### Plain access

`(int) VALUE.get(receiver)` và `VALUE.set(receiver, 42)` thể hiện phép đọc/ghi thông thường. Nếu một thread ghi và thread khác đọc cùng biến bằng plain mà không có quan hệ happens-before khác, chương trình có thể có **data race**. Không thay `synchronized`, latch hoặc volatile bằng hai lời gọi plain chỉ vì chúng đi qua VarHandle.

### Opaque access

`getOpaque`/`setOpaque` áp dụng các ràng buộc yếu, hướng tới những giao thức cấp thấp cần tính nhất quán của cùng một vị trí nhưng không cần ordering đầy đủ với các vị trí khác. **Không được** suy ra: reader thấy một cờ cập nhật qua opaque thì các trường dữ liệu thông thường viết trước cờ chắc chắn đã được publish theo quan hệ release/acquire.

Nếu người học chưa có nhu cầu giao thức non-blocking cấp thấp, acquire/release hoặc volatile thường rõ nghĩa và dễ kiểm chứng hơn.

### Acquire và release

Pattern công bố một lần, **writer**:

```java
payload = 42;           // Ghi dữ liệu thường trước.
READY.setRelease(this, 1); // Công bố cờ.
```

**Reader**:

```java
while ((int) READY.getAcquire(this) == 0) {
    Thread.onSpinWait();
}
int local = payload; // Đọc dữ liệu sau khi thấy cờ công bố.
```

Hai snippet này giả sử `payload`, `READY` và receiver đã được khai báo; **không phải hai file độc lập**. Khi acquire đọc đúng giá trị đã được writer công bố qua release trên cùng biến tín hiệu, tác dụng ordering của release/acquire cho phép sử dụng dữ liệu đã ghi trước việc công bố theo giao thức đó. Ví dụ độc lập ở phần 7.

Vòng `onSpinWait()` chỉ là minh họa cơ chế; production thường ưu tiên `CountDownLatch`, `BlockingQueue`, `Future` hoặc API chờ khác khi không cần polling. Busy-wait có thể lãng phí CPU, cần timeout/cancellation nếu công việc có thể không hoàn tất.

### Volatile access

`getVolatile`/`setVolatile` có semantics tương tự truy cập vào trường volatile. Một lần ghi volatile happens-before lần đọc volatile tương ứng theo các quy tắc synchronization order, hỗ trợ visibility/ordering giữa các thread.

**Sai lầm quen thuộc:** hai thread cùng thực hiện `(int) VALUE.getVolatile(obj)` rồi `VALUE.setVolatile(obj, old + 1)`. Từng lần get/set có semantics volatile, nhưng **cặp lời gọi không nguyên tử**: cả hai có thể đọc cùng `old` rồi cùng ghi một kết quả. Để tăng đúng, dùng `getAndAdd` hoặc CAS loop.

## 4. Java 17+ hoàn chỉnh: bộ đếm atomic bằng `getAndAdd`

Tạo file `VarHandleCounter.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleCounter {
    private int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup()
                    .findVarHandle(VarHandleCounter.class, "count", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public void increment() {
        COUNT.getAndAdd(this, 1);
    }

    public int get() {
        return (int) COUNT.getVolatile(this);
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandleCounter counter = new VarHandleCounter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Final count: " + counter.get());
    }
}
```

Biên dịch và chạy:

```bash
javac VarHandleCounter.java
java VarHandleCounter
```

Đầu ra khi bốn worker kết thúc bình thường:

```text
Final count: 4000
```

**Điểm cốt lõi:**

1. `COUNT` là handle tới trường instance `int count` của `VarHandleCounter`; mỗi lần gọi cần truyền đúng receiver (`this`).
2. `getAndAdd(this, 1)` là **một thao tác read–modify–write atomic**, khác với lấy `getVolatile` rồi `setVolatile` thành hai bước.
3. `getVolatile(this)` đọc kết quả với semantics volatile. `Thread.join()` cũng tạo quan hệ happens-before từ hành động của worker tới thread main sau khi chờ thành công.
4. Scheduler có thể chạy các worker theo mọi thứ tự, nhưng không làm mất lượt tăng; 4 × 1.000 = 4.000.

VarHandle phù hợp khi cần điều khiển kiểu truy cập của một trường cụ thể. Với **bộ đếm đơn giản**, `AtomicInteger` thường ngắn hơn, dễ đọc hơn và có ít cơ hội sử dụng sai access mode. Dùng VarHandle khi bạn thật sự cần một kiểu layout hoặc giao thức mà các lớp atomic không diễn đạt rõ.

## 5. Compare-and-set: kiểm tra và cập nhật cùng một bước

`compareAndSet(receiver, expected, newValue)` kiểm tra biến hiện tại có bằng expected không và, nếu đúng, ghi giá trị mới **nguyên tử**. Kết quả là `boolean`:

- `true`: phép thay thành công.
- `false`: giá trị hiện tại không khớp expected (hoặc, với **weak** CAS variants, còn có thể thất bại giả—*spurious failure*).

Với kiểu reference, so sánh trong các primitive CAS liên quan đến **tham chiếu** (reference identity) chứ không phải tự gọi logic `equals()` của object. Với primitive, so sánh theo kiểu dữ liệu hỗ trợ.

### CAS loop để giữ bất biến “số lượng không âm”

Tạo file `VarHandleInventory.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.atomic.AtomicInteger;

public class VarHandleInventory {
    private int remaining = 3;
    private static final VarHandle REMAINING;

    static {
        try {
            REMAINING = MethodHandles.lookup()
                    .findVarHandle(VarHandleInventory.class,
                                   "remaining", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public boolean reserveOne() {
        while (true) {
            int old = (int) REMAINING.getVolatile(this);
            if (old <= 0) {
                return false;
            }
            if (REMAINING.compareAndSet(this, old, old - 1)) {
                return true;
            }
            // Giá trị đã thay đổi: phải đọc lại và thử lần nữa.
        }
    }

    public int remaining() {
        return (int) REMAINING.getVolatile(this);
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandleInventory inventory = new VarHandleInventory();
        AtomicInteger accepted = new AtomicInteger();
        Thread[] buyers = new Thread[10];

        for (int i = 0; i < buyers.length; i++) {
            buyers[i] = new Thread(() -> {
                if (inventory.reserveOne()) {
                    accepted.incrementAndGet();
                }
            });
            buyers[i].start();
        }

        for (Thread buyer : buyers) {
            buyer.join();
        }

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Remaining: " + inventory.remaining());
    }
}
```

Chạy:

```bash
javac VarHandleInventory.java
java VarHandleInventory
```

Đầu ra khi tất cả thread hoàn tất:

```text
Accepted: 3
Remaining: 0
```

Các thread tranh nhau nhưng chỉ ba phép chuyển `3 → 2 → 1 → 0` có thể thành công. Khi CAS thất bại vì giá trị bị thay, vòng lặp không dùng snapshot cũ nữa. Phép kiểm tra `old > 0` và việc decrement được liên kết bởi CAS tại **điểm tuyến tính hóa** của lần cập nhật thành công.

**Phạm vi atomicity:** một CAS chỉ bảo vệ `remaining`. Nếu thao tác bán hàng còn phải thêm record vào danh sách, ghi file hoặc cập nhật tài nguyên ngoài JVM, CAS trên một trường **không** biến toàn bộ công việc thành transaction. Cần lựa chọn thêm cơ chế bảo vệ các bất biến liên quan.

## 6. `compareAndExchange`, weak CAS và các atomic access mode

### `compareAndSet` và `compareAndExchange` khác nhau

- `compareAndSet(expected, update)` trả về `boolean` thành công/thất bại.
- `compareAndExchange(expected, update)` trả về **giá trị thực sự quan sát tại thời điểm so sánh** (*witness value*). Nếu witness bằng expected, phép ghi được thực hiện; nếu không, witness là giá trị đã khiến thao tác thất bại.
- Các biến thể `compareAndExchangeAcquire` và `compareAndExchangeRelease` cho phép chọn memory-ordering yếu hơn ở những chiều phù hợp của thao tác; phải đọc đúng hợp đồng API.
- `weakCompareAndSetPlain` cùng các biến thể weak có thể **thất bại giả** ngay khi giá trị hiện tại vẫn khớp expected. Khi dùng chúng trong thuật toán, thường cần retry và tính đến tiến triển trong điều kiện cạnh tranh.

Ví dụ ý tưởng với một VarHandle có value type `int` và tọa độ receiver:

```java
// Snippet: VALUE là VarHandle cho trường int của obj.
boolean swapped = VALUE.compareAndSet(obj, 5, 6);
int witness = (int) VALUE.compareAndExchange(obj, 6, 7);
```

Đây là snippet, không thể dự đoán `swapped`/`witness` nếu chưa biết trạng thái thực của `obj`. Không in một kết quả “đảm bảo” cho mã có trạng thái chưa xác định.

### Atomic read–modify–write

Các access mode như `getAndSet`, `getAndAdd`, `getAndBitwiseOr`/`And`/`Xor` (khi type hỗ trợ) đọc giá trị cũ và cập nhật biến như **một thao tác atomic**.

`getAndAdd` trả về **giá trị trước khi cộng**, không phải kết quả sau cộng. Ví dụ nếu giá trị hiện tại là 10:

```java
// Snippet: VALUE là VarHandle kiểu int của obj.
int old = (int) VALUE.getAndAdd(obj, 5); // old = 10
// Giá trị được lưu là 15.
```

Để biết một mode có dùng được với handle cụ thể hay không, kiểm tra:

```java
boolean allowed =
        VALUE.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD);
```

Các snippet trên chưa bao gồm khai báo `obj`, `VALUE`; ví dụ array ở phần 8 là một chương trình chạy độc lập.

**Chọn mode đúng với thuật toán:** `getAndAdd` cho bộ đếm; CAS loop cho cập nhật có điều kiện; `getAndSet` cho trao đổi một giá trị; các mode acquire/release dùng khi chứng minh được ordering yếu vẫn đủ. Chọn mode yếu “để chạy nhanh hơn” mà không chứng minh happens-before có thể tạo bug rất khó tái hiện.

## 7. Java 17+: publication với `setRelease` và `getAcquire`

Một nhu cầu phổ biến: producer tạo dữ liệu rồi công bố cờ sẵn sàng; consumer chỉ đọc dữ liệu **sau khi quan sát được cờ**. Ta không cần khóa toàn bộ object nếu giao thức một lần này được thiết kế chính xác.

Tạo file `VarHandlePublication.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandlePublication {
    private int payload;
    private int ready;

    private static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup()
                    .findVarHandle(VarHandlePublication.class,
                                   "ready", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandlePublication signal = new VarHandlePublication();

        Thread producer = new Thread(() -> {
            signal.payload = 42;
            READY.setRelease(signal, 1);
        });

        Thread consumer = new Thread(() -> {
            while ((int) READY.getAcquire(signal) == 0) {
                Thread.onSpinWait();
            }
            System.out.println("Received: " + signal.payload);
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
```

Chạy:

```bash
javac VarHandlePublication.java
java VarHandlePublication
```

Khi cả hai thread hoàn tất bình thường, đầu ra:

```text
Received: 42
```

**Phân tích theo memory ordering:**

1. Producer ghi trường thường `payload = 42` **trước** khi phát cờ bằng `setRelease(signal, 1)`.
2. Consumer lặp `getAcquire(signal)` cho tới khi thấy 1. Việc acquire đọc cờ đã được phát bằng release thiết lập ordering cần thiết để truy cập `payload` ở phía sau đọc dữ liệu đã được công bố.
3. `payload` không cần tự được khai báo volatile trong **giao thức một writer, publish một lần, không có ghi tiếp vào payload** này.
4. `Thread.onSpinWait()` chỉ gợi ý cho JVM/CPU về busy-spin; nó **không thay thế** acquire/release hoặc tạo signal.
5. Để tránh vòng chờ vô hạn nếu producer không công bố do lỗi, production phải có chính sách hủy, timeout hoặc dùng một primitive blocking phù hợp.

**Giới hạn:** nếu producer thay payload liên tục trong khi consumer đang đọc, hoặc nhiều producer cùng công bố một cờ duy nhất, giao thức trên **không tự đủ** để cung cấp snapshot đa phiên bản. Khi đó cần version, queue, immutable snapshot hoặc khóa phù hợp với yêu cầu.

## 8. Java 17+: VarHandle cho phần tử mảng

Một handle cho phần tử `int[]` yêu cầu **hai tọa độ**: mảng và chỉ số. Không cần định nghĩa trường trong class riêng. Tạo file `VarHandleArray.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleArray {
    private static final VarHandle ELEMENT =
            MethodHandles.arrayElementVarHandle(int[].class);

    public static void main(String[] args) {
        int[] values = {10, 20};

        int old = (int) ELEMENT.getAndAdd(values, 1, 5);
        boolean replaced = ELEMENT.compareAndSet(values, 0, 10, 15);

        System.out.println("Old second: " + old);
        System.out.println("New second: "
                + (int) ELEMENT.getVolatile(values, 1));
        System.out.println("First replaced: " + replaced);
        System.out.println("New first: "
                + (int) ELEMENT.getVolatile(values, 0));
    }
}
```

Chạy:

```bash
javac VarHandleArray.java
java VarHandleArray
```

Đầu ra:

```text
Old second: 20
New second: 25
First replaced: true
New first: 15
```

Trong ví dụ, `getAndAdd(values, 1, 5)` cộng 5 **nguyên tử** vào phần tử chỉ số 1 và trả giá trị cũ 20. `compareAndSet(values, 0, 10, 15)` thành công vì giá trị tại chỉ số 0 đúng là 10. Một thao tác atomic trên phần tử `values[0]` **không** tạo transaction cho toàn bộ mảng; nếu cần thay nhiều phần tử như một snapshot bất biến thì phải thêm giao thức thích hợp.

VarHandle mảng là lựa chọn tốt khi cần atomic access từng slot của một mảng primitive/reference. Không suy từ nó rằng `ArrayList` hoặc một cấu trúc dữ liệu mutable phức tạp cũng an toàn để thao tác đồng thời.

## 9. Mối quan hệ với JMM: visibility, atomicity và ordering

Phải phân biệt ba câu hỏi độc lập:

1. **Visibility:** thread đọc có quan sát được dữ liệu writer đã công bố không?
2. **Ordering:** các thao tác phụ thuộc trước/sau nhau có được sắp đúng theo giao thức đồng bộ không?
3. **Atomicity:** phép kiểm tra–cập nhật có diễn ra như một bước không thể bị chen ngang trên vị trí đó không?

Ví dụ:

- `VALUE.getVolatile(obj)` giải quyết yêu cầu đọc kiểu volatile, nhưng đọc rồi gọi `setVolatile` ở bước sau **không** là atomic read–modify–write.
- `VALUE.getAndAdd(obj, 1)` là phép cộng nguyên tử trên một vị trí, nhưng không bảo vệ toàn bộ invariant gồm thêm một trường khác.
- `setRelease(flag, 1)` và `getAcquire(flag)` phù hợp để publish dữ liệu đã ghi **trước** tín hiệu cho reader chỉ đọc dữ liệu **sau** khi thấy tín hiệu; không bảo đảm những ghi tiếp theo của writer sẽ là snapshot nhất quán.
- `getOpaque`/`setOpaque` yếu hơn acquire/release về ordering, nên không tự thay cho giao thức publish dữ liệu phụ thuộc.
- `get`/`set` plain trên cùng trường mutable từ các thread khác nhau không có đồng bộ thích hợp có thể tạo data race.

### VarHandle có làm trường thường thành volatile mãi mãi không?

**Không.** Một `VarHandle` cho phép gọi **nhiều mode khác nhau** trên cùng vị trí. Độ mạnh của một mode là thuộc tính của lần truy cập cụ thể. Nếu ở một đường code dùng `setRelease` nhưng đường khác dùng `get` plain khi cần đọc dữ liệu đã publish, không thể chỉ viện dẫn rằng “trường đã được xử lý bằng VarHandle” để khẳng định an toàn.

Thiết kế cần quy định **cặp mode phù hợp** trên mọi đường truy cập, cùng bất biến và quan hệ đồng bộ. Một accessor dùng mode khác có thể phá cách suy luận ban đầu.

### Fences

`VarHandle` còn có các phương thức static như `fullFence()`, `acquireFence()`, `releaseFence()`, `loadLoadFence()` và `storeStoreFence()` để diễn tả một số ràng buộc thứ tự bộ nhớ độc lập với một phép truy cập biến cụ thể. Đây là công cụ cấp thấp cho các thuật toán đồng thời chuyên sâu.

**Không** dùng một fence lẻ như bản sửa thần kỳ cho data race hay lỗi check–then–act. Phải có giao thức tương tác đầy đủ giữa reader/writer, chứng minh tính hợp lệ theo JMM và chọn đúng vị trí đặt fence. Khi chưa có lý do rất cụ thể, dùng các access mode acquire/release/volatile hoặc API concurrent cao hơn thường dễ kiểm chứng hơn.

## 10. Kiểu dữ liệu, signature và lỗi khi gọi VarHandle

Các phương thức `get`, `set`, `compareAndSet`... có hình thức **signature-polymorphic**. Trình biên dịch/JVM kiểm tra kiểu tham số/tọa độ và kiểu trả về theo access mode. Vì vậy:

- Handle trường instance cần receiver đúng kiểu và các tham số thích hợp với `varType()`.
- Handle static **không** cần receiver.
- Handle array cần tọa độ **array** và **index** trước giá trị mới hoặc expected/new.
- Kết quả đọc thường cần cast phù hợp, ví dụ `int n = (int) HANDLE.getVolatile(obj)`.
- Ký hiệu `(int) HANDLE.getVolatile(...)` không nên bỏ đi khi dùng trong biểu thức kiểu Java dễ suy diễn sai.
- Gọi với kiểu/ký hiệu không phù hợp có thể gây lỗi liên quan method type như `WrongMethodTypeException`; receiver sai kiểu có thể gây lỗi runtime tương ứng.
- Mode không hỗ trợ bởi loại biến/handle có thể ném `UnsupportedOperationException`.
- Khi dùng handle field có quyền truy cập restricted, việc tạo handle có thể thất bại vì `IllegalAccessException`; không thể sửa bằng việc lén thay đổi access mode.

### Kiểm tra capability trước khi chọn mode

```java
// Snippet: handle được tạo hợp lệ ở chỗ khác.
boolean atomicAddSupported =
        handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD);
Class<?> valueType = handle.varType();
```

Đoạn này chưa phải chương trình độc lập. Kiểm tra capability đặc biệt hữu ích nếu viết utility tổng quát nhận handle nhiều kiểu khác nhau. Với các demo kiểu `int` bên trên, mode `GET_AND_ADD` được hỗ trợ.

**Một điểm thiết kế:** `VarHandle` không tự động gom các thao tác bất kỳ thành primitive cấp cao. Nếu mode không hỗ trợ, không nên giả lập bằng `get` rồi `set` khi thuật toán đòi nguyên tử tính.

## 11. So sánh VarHandle với `AtomicInteger`, `AtomicReference` và lock

| Cơ chế | Khi nào phù hợp | Giới hạn / chi phí suy luận |
| --- | --- | --- |
| `AtomicInteger`/`AtomicLong` | Bộ đếm, trạng thái primitive đơn có CAS và atomic update | Tạo object wrapper và API gắn với biến atomic cụ thể |
| `AtomicReference` | Thay thế một reference (thường trỏ tới immutable snapshot) bằng CAS | Chỉ atomic với **tham chiếu**, không tự làm object được tham chiếu trở thành bất biến |
| `AtomicIntegerFieldUpdater` | Atomic access tới một field theo ràng buộc của updater | Điều kiện kiểu/field và cơ chế truy cập riêng |
| **`VarHandle`** | Cần access mode cụ thể cho field/static/array slot, xây primitive concurrent hoặc kiểm soát memory semantics | API cấp thấp; phải tự thiết kế đúng cặp mode, casts và giao thức |
| `synchronized`/`ReentrantLock` | Cần critical section hoặc invariant liên quan nhiều trường | Lock contention, nguy cơ deadlock; nhưng thường đơn giản hơn CAS phức tạp |
| Immutable snapshot qua `volatile`/atomic reference | Nhiều reader chỉ đọc, writer thay bản đầy đủ | Writer có thể phải tạo snapshot mới; reader cần tránh sửa nội dung snapshot |

**VarHandle không phải lựa chọn bắt buộc để có code nhanh hơn.** Nếu `AtomicInteger.incrementAndGet()` diễn đạt trọn nghiệp vụ, nó thường là lựa chọn rõ ràng. VarHandle phát huy giá trị trong triển khai thư viện cấu trúc dữ liệu, thuật toán non-blocking, mảng atomic hoặc những trường cần phối hợp mode ordering khác nhau. Đo benchmark thực tế trước khi kết luận hiệu năng.

## 12. Những sai lầm dễ gây lỗi concurrency

1. **“VarHandle = volatile ở mọi truy cập.”** Sai: plain, opaque, acquire/release và volatile có semantics khác nhau.
2. **“`getVolatile` rồi `setVolatile` là một CAS.”** Sai: vẫn là hai thao tác; thread khác chen vào được.
3. **“`getAndAdd` trả về giá trị mới.”** Sai: nó trả giá trị **trước** cập nhật.
4. **“`compareAndSet` có thể được thay bằng hai thao tác get/set.”** Sai: check–then–act khi tách ra không atomic.
5. **“Weak CAS false nghĩa là giá trị chắc chắn không khớp.”** Sai: weak CAS có thể thất bại giả.
6. **“`setOpaque`/`getOpaque` công bố tất cả các trường viết trước.”** Sai: ordering yếu hơn giao thức release/acquire cần cho dữ liệu phụ thuộc.
7. **“Writer dùng setRelease nhưng reader dùng plain get vẫn đủ.”** Không được suy ra có giao thức công bố an toàn.
8. **“CAS trên một field bảo vệ cả object nhiều field.”** Sai: invariant liên trường cần cơ chế khác hoặc biểu diễn thành một trạng thái atomic.
9. **“Một handle tới private field vượt được Java module system.”** Sai: quyền tạo handle bị kiểm tra.
10. **“Mode nào cũng hợp lệ cho mọi kiểu.”** Sai: dùng `isAccessModeSupported` nếu viết utility tổng quát.
11. **“Cứ dùng VarHandle sẽ nhanh hơn synchronized.”** Sai: phụ thuộc contention, đường đọc/ghi, CPU/JVM, độ phức tạp retry và cache effects.
12. **“Một lần test ra kết quả đúng nghĩa là memory ordering đúng.”** Sai: lỗi JMM có thể chỉ xuất hiện ở một lịch/JVM/hardware khác.

## 13. Checklist áp dụng VarHandle vào code thật

1. **Chọn biến:** trường instance/static hay phần tử mảng? Giá trị thuộc kiểu gì? Các tọa độ nhận dạng vị trí là gì?
2. **Xác định quyền truy cập:** handle có được tạo bằng `Lookup` hợp lệ và không phá module encapsulation không?
3. **Nêu invariant:** chỉ cần atomic cho một trường, hay phải bảo vệ nhiều trường cùng lúc?
4. **Chọn access mode nhỏ nhất có thể chứng minh đúng:** plain/opaque chỉ khi có cơ chế khác, acquire/release cho giao thức xuất bản, volatile khi cần semantics mạnh hơn, CAS/getAndAdd cho atomic RMW.
5. **Chứng minh reader/writer hợp tác:** mode phía đọc có tương thích với mode phía ghi? Dữ liệu phụ thuộc được ghi trước publish và chỉ đọc sau acquire không?
6. **Xử lý CAS thất bại:** nếu dùng loop, đọc lại state; có chính sách tiến triển, giới hạn retry/timeout nếu nghiệp vụ cần.
7. **Không có side effect lặp ngoài ý muốn:** CAS loop có thể chạy nhiều lần; không gửi mail hay ghi file trong thân hàm tính toán retry mà không có idempotency.
8. **Kiểm tra kiểu và hỗ trợ mode:** receiver, array index, return cast, `AccessMode` có hợp lệ không?
9. **Kiểm thử concurrency thật:** dùng bất biến, interleaving có kiểm soát, stress test; dùng jcstress cho các litmus test JMM chuyên sâu khi phù hợp.
10. **Cân nhắc API cao hơn:** một `AtomicInteger`/lock/queue/immutable snapshot có thể dễ đọc, dễ review và an toàn hơn.
11. **Đo thay vì đoán:** benchmark với warm-up JVM và workload đại diện; phân biệt hiệu năng với tính đúng đắn.
12. **Ghi lại policy:** mọi lần truy cập cùng state nên tuân thủ quy tắc access mode và memory ordering đã quyết định.

**Kết luận:** VarHandle là công cụ JDK để truy cập một biến với **access mode được chọn rõ ràng**, bao gồm plain, opaque, acquire/release, volatile và nhiều thao tác atomic. Sức mạnh của nó nằm ở việc thể hiện chính xác memory semantics mà một thuật toán concurrent cần; trách nhiệm của người viết là chứng minh giao thức giữa các thread, bảo vệ invariant và không nhầm nhiều phép truy cập riêng lẻ với một thao tác nguyên tử.