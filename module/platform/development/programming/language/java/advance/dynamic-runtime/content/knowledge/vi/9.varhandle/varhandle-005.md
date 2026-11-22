# 9.5. Đọc, ghi plain, opaque, acquire, release và volatile với `VarHandle`

Java cho phép nhiều luồng đọc và ghi cùng một biến, nhưng **đọc được đúng giá trị trong một luồng** chưa chứng minh luồng khác sẽ quan sát đúng dữ liệu hoặc đúng thứ tự các thao tác. Với `java.lang.invoke.VarHandle` (Java 9+), lập trình viên có thể lựa chọn **memory semantics cho từng lần truy cập**: `plain`, `opaque`, `acquire`, `release` và `volatile`.

Các mode này quyết định mức bảo đảm về **atomicity**, **coherence** và **thứ tự truy cập bộ nhớ giữa các luồng**. Chúng không phải năm kiểu dữ liệu và cũng không phải các phép biến đổi giá trị. Bài này tập trung vào Java 17+, giải thích điều gì được phép đọc/ghi, cơ chế publish/consume, ví dụ chạy được và lỗi thường gặp.

## 1. `VarHandle` là gì?

Một `VarHandle` là một tham chiếu **có kiểu** tới một biến hoặc một họ biến: field instance, field static, phần tử array hoặc một số loại bộ nhớ khác do API cung cấp. Bản thân đối tượng `VarHandle` là immutable; nội dung biến mà nó trỏ tới vẫn có thể mutable nếu API và khai báo cho phép.

Mỗi handle có:

- **Variable type** (`varType()`): kiểu giá trị được đọc/ghi, ví dụ `int.class` hoặc `String.class`.
- **Coordinate types** (`coordinateTypes()`): kiểu các tọa độ cần để xác định vị trí biến. Field instance cần receiver; static field không cần receiver; phần tử mảng cần tham chiếu mảng và chỉ số.
- **Access mode type** (`accessModeType(mode)`): chữ ký cần cho một mode cụ thể, chẳng hạn `(Cell)int` khi đọc instance `int`, `(Cell,int)void` khi ghi.
- **Supported modes** (`isAccessModeSupported(...)`): không phải mọi mode đều áp dụng cho mọi handle, đặc biệt field `final` có thể đọc nhưng không thể ghi qua `VarHandle`.

Để lấy handle cho một field instance:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Counter {
    int value;
}

// Đoạn minh họa đặt ở nơi có quyền lookup field Counter.value.
VarHandle VALUE = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);

Counter c = new Counter();
VALUE.set(c, 10);               // plain write
int x = (int) VALUE.get(c);      // plain read
```

Với field `Counter.value` kiểu `int`, các mode đọc có chữ ký logic `(Counter)int`, các mode ghi có chữ ký logic `(Counter,int)void`. Ở lời gọi `get`, cast trực tiếp `(int)` là cần thiết để mô tả đúng kiểu kết quả của *signature-polymorphic call*. Những phương thức mode có dạng khai báo biểu kiến `Object...`, nhưng compiler/JVM sử dụng chữ ký đặc biệt; **không** truyền một `Object[]` thay cho các tọa độ và giá trị theo thói quen reflection.

Các mode ở đây **điều khiển một lần truy cập**. Ví dụ, `VALUE.getVolatile(c)` mang semantics volatile dù field `value` không được khai báo `volatile`; `VALUE.get(c)` lại là plain read kể cả nếu khai báo field gốc có `volatile`. Trộn truy cập với mode không nhất quán rất dễ làm hỏng lập luận về visibility.

## 2. Bảng đối chiếu các mode đọc/ghi

| Mode | Phương thức đọc | Phương thức ghi | Bảo đảm nổi bật | Thường dùng |
| --- | --- | --- | --- | --- |
| **Plain** | `get` | `set` | Tương đương truy cập field thường, không thêm bảo đảm thứ tự quan sát giữa các luồng | Dữ liệu nội bộ có đồng bộ hóa khác hoặc chỉ dùng trong một luồng |
| **Opaque** | `getOpaque` | `setOpaque` | Atomic cho giá trị, có **coherence/ordering trên cùng biến**; không công bố thứ tự các truy cập tới biến khác | Theo dõi trạng thái đơn giản cần mạnh hơn plain nhưng không publish payload |
| **Acquire** | `getAcquire` | *Không có `setAcquire`* | Sau acquire read, các load/store phía sau không bị đưa lên trước; phối hợp với release write phù hợp | Consumer nhận cờ đã publish, sau đó đọc payload |
| **Release** | *Không có `getRelease`* | `setRelease` | Các load/store phía trước không bị đưa xuống sau write này; phối hợp với acquire read phù hợp | Producer ghi payload trước, công bố cờ sau |
| **Volatile** | `getVolatile` | `setVolatile` | Semantics như field `volatile`, có thứ tự toàn phần giữa các volatile access | Cờ chia sẻ, trạng thái cần ordering/visibility mạnh hơn |

**Thứ tự về sức mạnh bảo đảm** thường được dùng để ghi nhớ là **plain → opaque → acquire/release → volatile**, nhưng `acquire` là phía **đọc** còn `release` là phía **ghi**: chúng không phải hai lựa chọn thay thế đối xứng ở cả hai chiều. Đây là thứ tự tổng quát về ràng buộc memory ordering, **không** phải kết luận về tốc độ của từng CPU/JVM.

Theo Javadoc `VarHandle` Java 17:

- Plain `get/set` chỉ được bảo đảm **bitwise atomic** đối với reference và primitive có kích thước không quá 32 bit; `long`/`double` có thể thiếu bảo đảm không rách giá trị (*tearing*) trên nền tảng 32-bit.
- Opaque read/write là bitwise atomic cả với `long`/`double` và được sắp thứ tự nhất quán (*coherently ordered*) cho những truy cập vào **cùng biến**.
- Acquire và release kế thừa bảo đảm của opaque rồi thêm ràng buộc theo **một hướng**.
- Volatile kế thừa bảo đảm acquire/release, đồng thời các volatile access được xếp theo một **thứ tự toàn phần phù hợp**.

Không suy ra rằng một thao tác volatile sẽ “chạy nhanh nhất/chậm nhất” một cách cố định; chi phí còn tùy CPU, JIT, contention và kiến trúc.

## 3. Plain: `get` / `set`

`get` đọc và `set` ghi với semantics giống biến **không `volatile` và không `final`**. Với một field mutable được dùng trong cùng một luồng:

```java
VALUE.set(c, 1);
int n = (int) VALUE.get(c); // 1 trong luồng này
```

Đây là lựa chọn tự nhiên khi dữ liệu **thread-confined**, immutable sau publication an toàn, hoặc việc đồng bộ hóa do một lock/cơ chế khác đảm nhận. Nếu các luồng truy cập cạnh tranh mà không có quan hệ ordering thích hợp, **đừng coi plain read là cách chắc chắn quan sát lần ghi mới nhất**.

Ví dụ sai về ý tưởng giao tiếp luồng:

```java
// Producer:
payload = 42;
READY.set(box, 1);           // plain write

// Consumer:
while ((int) READY.get(box) == 0) {
    // Không có giao thức visibility thích hợp.
}
use(payload);
```

Đây là **pseudocode minh họa**, không phải chương trình hoàn chỉnh: biến `READY`, `box`, `payload`, `use` được giả định tồn tại. Không có bảo đảm consumer sẽ thoát vòng lặp trong điều kiện race này; hơn nữa ngay cả khi nhìn thấy `ready == 1`, việc thấy đúng `payload` cũng chưa được thiết lập. Dùng `Thread.sleep`, tăng thời gian chờ hoặc thêm `println` **không sửa contract của bộ nhớ**.

### 3.1. Atomicity của một access khác với atomicity của cả phép cập nhật

Ngay cả khi từng lần đọc/ghi `int` nguyên tử, đoạn này **không** là tăng nguyên tử:

```java
int old = (int) VALUE.getVolatile(c);
VALUE.setVolatile(c, old + 1); // hai thao tác, thread khác có thể xen vào
```

Dùng `getAndAdd`, `compareAndSet` hoặc cơ chế khóa nếu cần một phép read-modify-write nguyên tử. `volatile` cải thiện ordering/visibility nhưng **không biến hai lời gọi rời rạc thành một transaction**.

## 4. Opaque: `getOpaque` / `setOpaque`

Opaque mạnh hơn plain về atomicity và **coherence của cùng một biến**: những truy cập opaque tới cùng một vị trí được nhìn theo thứ tự nhất quán theo quy tắc của API. Nó không thiết lập ràng buộc ordering với các lần truy cập các biến khác như một cặp release/acquire.

```java
VALUE.setOpaque(c, 2);
int n = (int) VALUE.getOpaque(c); // 2 trong luồng này
```

Opaque có thể phù hợp với một số thuật toán low-level chỉ yêu cầu theo dõi/truyền **giá trị của chính một biến**, được thiết kế và chứng minh tính đúng đắn cẩn thận. Ví dụ một trạng thái thống kê đơn giản mà độ trễ quan sát và phối hợp các field khác không quan trọng, nhưng việc chọn opaque vẫn phải xem toàn bộ giao thức truy cập.

**Không dùng opaque như tín hiệu publish dữ liệu khác nếu chưa có đồng bộ hóa phù hợp.** Ví dụ:

```java
// Producer:
box.payload = 42;
READY.setOpaque(box, 1);

// Consumer:
if ((int) READY.getOpaque(box) == 1) {
    int value = box.payload; // Không được bảo đảm thấy 42 từ riêng cặp opaque.
}
```

Đây cũng là **pseudocode**; các thao tác opaque trên `ready` không bảo đảm các lần truy cập thường trên `payload` được sắp thứ tự quan sát như mong muốn. Thay vì đoán bằng số lần test chạy thành công, hãy xác định có quan hệ ordering hợp lệ hay không.

Opaque **không** có nghĩa mọi luồng thấy giá trị ngay lập tức hoặc tất cả các biến được sắp theo một thứ tự toàn cục. Opaque cung cấp coherence đối với biến đang thao tác, khác với tính chất publish/consume có thứ tự cho *dữ liệu phụ thuộc*.

## 5. Acquire và release: công bố dữ liệu theo cặp

Đây là cặp thường gặp khi producer muốn **chuẩn bị dữ liệu trước**, sau đó **công bố một cờ**; consumer **nhìn thấy cờ công bố**, rồi mới **đọc dữ liệu**.

- `setRelease`: các load/store thực hiện **trước** release write không bị đẩy qua phía sau nó.
- `getAcquire`: các load/store thực hiện **sau** acquire read không bị đẩy qua phía trước nó.
- Khi acquire read thực sự quan sát giá trị được công bố bởi release write **trên biến đồng bộ tương ứng**, các truy cập phía trước của producer và phía sau của consumer được sắp đúng quan hệ cần thiết.

Mô hình tối giản:

```java
// Cả hai thread cùng sử dụng box/READY.
// Producer:
box.payload = 42;              // ghi dữ liệu trước
READY.setRelease(box, 1);       // công bố cờ sau

// Consumer:
while ((int) READY.getAcquire(box) == 0) {
    Thread.onSpinWait();
}
int result = box.payload;        // đọc sau khi quan sát cờ 1
```

Đây là **hai luồng trong giao thức một lần công bố**, chưa phải chương trình độc lập; phần ví dụ hoàn chỉnh bên dưới tạo các thread và handle thật. Sau khi consumer nhìn thấy cờ `1` qua `getAcquire`, nó có thể đọc payload `42` đã được producer ghi trước `setRelease` trong trường hợp này.

**Điều kiện thiết yếu của mô hình:**

1. Producer phải ghi `payload` **trước** khi gọi `setRelease`.
2. Consumer chỉ đọc `payload` **sau** khi `getAcquire` thấy giá trị cờ đã publish.
3. Cả hai phải dùng cùng vị trí đồng bộ `ready`, chứ không phải các biến hoàn toàn khác.
4. Sau publication, producer không tự do ghi đè payload trong lúc consumer đang đọc; nếu muốn cập nhật liên tục, cần giao thức ownership/versioning hoặc đồng bộ hóa bổ sung.
5. Trong chương trình có tranh chấp hoặc chu kỳ publish/reuse phức tạp, cần xét các lần ghi cờ được đọc, thời gian sống dữ liệu và sự tương tác với các access mode khác.

**Điều cần tránh:** Chỉ dùng `setRelease` ở producer nhưng consumer đọc cờ bằng `get` plain, hoặc producer dùng `set` plain nhưng consumer đọc `getAcquire`, không phải cặp publication được trình bày ở đây. Cũng không có API `setAcquire` hay `getRelease` để sử dụng đảo vai trò.

### 5.1. Vì sao acquire/release là ràng buộc một hướng?

Có thể hình dung (chỉ là sơ đồ ý nghĩa, không phải rào chắn CPU chính xác):

```text
Producer                             Consumer
---------                            ---------
write payload = 42                   acquire-read ready == 1
write other prepared state           read payload
release-write ready = 1              read other prepared state

prior reads/writes không dời         subsequent reads/writes không dời
xuống sau release                    lên trước acquire
```

Acquire **không** đảm bảo mọi thao tác trước nó đều phải hoàn tất theo cùng cách volatile; release **không** đảm bảo mọi thao tác sau nó bị giữ lại. Chúng giới hạn những hướng reordering cần cho việc publish/consume, có thể cho compiler/hardware tối ưu nhiều hơn so với volatile trong một số trường hợp.

`Thread.onSpinWait()` chỉ là hint cho runtime khi spinning, **không phải** memory fence hay giải pháp visibility. Vòng lặp spin không giới hạn có thể tiêu tốn CPU và không phải thiết kế timeout/cancellation thích hợp trong ứng dụng thực tế.

## 6. Volatile: `getVolatile` / `setVolatile`

`getVolatile` và `setVolatile` truy cập vị trí với semantics tương đương **đọc/ghi một field được khai báo `volatile`**, bất kể khai báo field gốc. Ngoài các bảo đảm acquire/release, những volatile access được đặt trong một thứ tự toàn phần phù hợp với Java Memory Model.

```java
VALUE.setVolatile(c, 4);
int n = (int) VALUE.getVolatile(c); // 4 trong luồng hiện tại
```

Ứng dụng thông thường:

- Cờ dừng `stopRequested` được producer cập nhật và worker đọc giữa các vòng lặp.
- Trạng thái được nhiều thread quan sát cần semantics giống field `volatile`.
- Truyền tín hiệu một chiều kèm dữ liệu đã chuẩn bị trước đó, khi luật ứng dụng yêu cầu tính nhất quán mạnh hơn acquire/release đơn giản.
- Các thuật toán lock-free có contract memory ordering được xác định rõ.

Với Java thông thường, trường hợp chỉ cần một field `volatile` đơn giản có thể viết trực tiếp:

```java
class WorkerState {
    volatile boolean stopRequested;
}
```

Không cần VarHandle chỉ để đọc/ghi field này; VarHandle có ích khi muốn chọn **access mode tại từng lần gọi**, hoặc xây thư viện concurrency/generic runtime.

**Không nhầm volatile với:**

- **Atomic increment:** `getVolatile` rồi `setVolatile` vẫn không tạo phép `++` nguyên tử.
- **Mutual exclusion:** không ngăn hai luồng thực thi một critical section cùng lúc.
- **Snapshot nhiều field:** hai lần đọc volatile tách rời không tự biến cả object thành một snapshot có tính giao dịch.
- **Bảo đảm một thời gian cụ thể:** volatile không bảo đảm worker được scheduler chạy ngay, hoặc có giới hạn mili giây để đọc trạng thái mới.
- **An toàn khi trộn modes:** nếu producer dùng volatile nhưng consumer dùng plain đối với cờ, không thể suy từ volatile ở một bên rằng toàn bộ giao thức được đồng bộ đầy đủ.

**Quan hệ với field khai báo `volatile`:** Javadoc `VarHandle` nêu rằng access mode của lời gọi **ghi đè memory ordering của declaration site**. Nghĩa là `handle.get(s)` là plain access dù field `volatile`, và `handle.getVolatile(s)` là volatile access dù field không khai báo `volatile`. Trộn cách truy cập với code thông thường phải đặc biệt cẩn thận; hãy dùng một chính sách nhất quán xuyên suốt thuật toán.

## 7. Ví dụ Java 17+ hoàn chỉnh, chạy được

Ví dụ này tạo `VarHandle` cho các field instance, một handle cho phần tử mảng, minh họa **năm nhóm mode** với kết quả dễ kiểm tra, xác nhận write mode không hỗ trợ cho field `final` và mô phỏng công bố payload bằng cặp release/acquire.

Lưu toàn bộ chương trình thành **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static final class Cell {
        int value;
        int payload;
        int ready;
        final int fixed = 9;
    }

    private static final VarHandle VALUE;
    private static final VarHandle READY;
    private static final VarHandle FIXED;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            VALUE = lookup.findVarHandle(Cell.class, "value", int.class);
            READY = lookup.findVarHandle(Cell.class, "ready", int.class);
            FIXED = lookup.findVarHandle(Cell.class, "fixed", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Cell cell = new Cell();
        System.out.println("variable=" + VALUE.varType().getSimpleName());
        System.out.println("coordinates=" + VALUE.coordinateTypes().size());

        VALUE.set(cell, 1);
        System.out.println("plain=" + (int) VALUE.get(cell));

        VALUE.setOpaque(cell, 2);
        System.out.println("opaque=" + (int) VALUE.getOpaque(cell));

        VALUE.setRelease(cell, 3);
        System.out.println("acquire=" + (int) VALUE.getAcquire(cell));

        VALUE.setVolatile(cell, 4);
        System.out.println("volatile=" + (int) VALUE.getVolatile(cell));

        VarHandle elements = MethodHandles.arrayElementVarHandle(int[].class);
        int[] data = {5, 6};
        elements.setVolatile(data, 1, 8);
        System.out.println("array=" + (int) elements.getVolatile(data, 1));

        System.out.println("final.get="
                + FIXED.isAccessModeSupported(VarHandle.AccessMode.GET));
        System.out.println("final.set="
                + FIXED.isAccessModeSupported(VarHandle.AccessMode.SET));

        try {
            FIXED.set(cell, 10);
        } catch (UnsupportedOperationException e) {
            System.out.println("final.write=" + e.getClass().getSimpleName());
        }

        Cell shared = new Cell();
        Thread consumer = new Thread(() -> {
            while ((int) READY.getAcquire(shared) == 0) {
                Thread.onSpinWait();
            }
            System.out.println("published=" + shared.payload);
        });

        consumer.start();
        shared.payload = 42;
        READY.setRelease(shared, 1);
        consumer.join();
        System.out.println("done");
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac --release 17 VarHandleModesDemo.java
java VarHandleModesDemo
```

`stdout` của chương trình:

```text
variable=int
coordinates=1
plain=1
opaque=2
acquire=3
volatile=4
array=8
final.get=true
final.set=false
final.write=UnsupportedOperationException
published=42
done
```

**Giải thích lần lượt:**

1. `VALUE.varType()` là `int`; `VALUE.coordinateTypes()` có một tọa độ là instance `Cell`. Đây là field instance, không phải static field.
2. `plain=1`, `opaque=2`, `acquire=3`, `volatile=4` kiểm chứng rằng cùng một biến có thể được truy cập qua các mode khác nhau. Những dòng chạy tuần tự **không đo** và **không chứng minh** khác biệt ordering giữa nhiều luồng; ordering là thuộc tính hợp đồng và giao thức, không phải khác biệt của con số in ra.
3. `array=8` cho thấy array VarHandle có tọa độ **mảng + chỉ số**; có thể dùng volatile access cho một phần tử mảng theo kiểu phần tử `int`.
4. `FIXED` trỏ tới `final int fixed`: read mode được hỗ trợ, write mode `SET` không. Gọi `FIXED.set(...)` ném `UnsupportedOperationException`; `VarHandle` không phải đường vòng để sửa final field.
5. Consumer đợi cờ `ready` bằng `getAcquire`; producer ghi `payload` rồi `setRelease`. Khi consumer đọc được giá trị cờ publish, nó in `published=42`. `join()` giúp main chờ consumer in xong trước `done`; `join` **không được dùng để tạo visibility của payload trước khi consumer đọc** — vai trò đó thuộc cặp release/acquire.

Ở máy thực tế, vòng spin có thể chờ theo scheduling, nên không nên biến ví dụ thành cam kết deadline hoặc latency. Hệ thống production nên cân nhắc điều kiện dừng, backoff, `LockSupport`, blocking queue hoặc primitive đồng bộ cấp cao hơn phù hợp use case. Ví dụ tập trung vào semantics memory ordering chứ không phải công cụ chờ tối ưu.

## 8. Field instance, static và phần tử array dùng tọa độ khác nhau

Chữ ký mode phụ thuộc **tọa độ của handle**, không chỉ biến có kiểu `int` hay `String`.

| Loại biến | Tạo handle | Tọa độ đọc | Tọa độ ghi |
| --- | --- | --- | --- |
| Instance field `int value` của `Cell` | `lookup.findVarHandle(Cell.class, "value", int.class)` | `(cell)` | `(cell, newValue)` |
| Static field `static int total` của `Totals` | `lookup.findStaticVarHandle(Totals.class, "total", int.class)` | *Không có receiver* | `(newValue)` |
| Array element `int[] arr` | `MethodHandles.arrayElementVarHandle(int[].class)` | `(arr, index)` | `(arr, index, newValue)` |

Ví dụ độc lập về cú pháp (các class/biến giả định đã khai báo trong project):

```java
VarHandle FIELD = MethodHandles.lookup()
        .findVarHandle(Cell.class, "value", int.class);
int instanceValue = (int) FIELD.getVolatile(cell);
FIELD.setRelease(cell, 10);

VarHandle STATIC = MethodHandles.lookup()
        .findStaticVarHandle(Totals.class, "total", int.class);
int total = (int) STATIC.getVolatile();
STATIC.setVolatile(11);

VarHandle ARRAY = MethodHandles.arrayElementVarHandle(int[].class);
int element = (int) ARRAY.getOpaque(arr, 0);
ARRAY.setOpaque(arr, 0, 12);
```

`FIELD`, `STATIC`, `ARRAY` là biến minh họa; phần trên **không** phải chương trình tự chạy do `Cell`, `Totals`, `cell` và `arr` chưa được cung cấp trong đoạn này. Chương trình đầy đủ ở mục 7 minh họa cách import, khởi tạo handle và dùng array thật.

Nếu truyền receiver sai kiểu, thiếu tọa độ, chỉ số mảng vượt giới hạn, hoặc kiểu kết quả không phù hợp với access mode, lời gọi có thể gây các lỗi như `WrongMethodTypeException`, `ClassCastException`, `NullPointerException` hoặc `ArrayIndexOutOfBoundsException` tùy trường hợp. Đây là lỗi **kiểu/tọa độ/dữ liệu**, không tự động là vấn đề memory ordering.

## 9. `isAccessModeSupported` và sự khác nhau với nguyên tử cập nhật

`VarHandle` hỗ trợ nhiều operation ngoài đọc/ghi, như `compareAndSet`, `getAndSet`, `getAndAdd` và biến thể acquire/release. Tuy nhiên, **không thể suy ra** một handle hỗ trợ mọi mode, và không thể coi `getVolatile` + `setVolatile` là phép nguyên tử hợp nhất.

Kiểm tra trước khi dùng:

```java
boolean writable = VALUE.isAccessModeSupported(
        VarHandle.AccessMode.SET_VOLATILE);
boolean canAdd = VALUE.isAccessModeSupported(
        VarHandle.AccessMode.GET_AND_ADD);
```

`VALUE` ở đây là handle `int` mutable. Với field `final`, các mode ghi và cập nhật sẽ không được hỗ trợ; API ném `UnsupportedOperationException` khi gọi mode không hỗ trợ. Một số mode cập nhật số/bitwise cũng phụ thuộc kiểu biến, ví dụ `getAndAdd` không có nghĩa áp dụng cho mọi kiểu reference.

Khi muốn `count++` tuyến tính hóa giữa nhiều thread, có thể dùng:

```java
VALUE.getAndAdd(cell, 1); // atomic update cho int nếu mode được hỗ trợ
```

Nếu muốn biết giá trị trước khi tăng:

```java
int oldValue = (int) VALUE.getAndAdd(cell, 1);
```

Đây là API **đọc-sửa-ghi nguyên tử**; khác với `VALUE.setVolatile(cell, (int) VALUE.getVolatile(cell) + 1)`, vì hai thread vẫn có thể cùng đọc cùng giá trị cũ và làm mất một lượt tăng.

## 10. Những lỗi thường gặp khi chọn mode

| Triệu chứng hoặc cách nghĩ sai | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| “Plain read luôn thấy write mới nhất sau vài vòng loop” | Không có giao thức đồng bộ giữa các thread | Dùng lock/volatile/cặp release-acquire hoặc primitive đồng bộ thích hợp |
| “Opaque flag đủ công bố dữ liệu của các field khác” | Opaque chỉ đảm bảo coherence cho **cùng biến**; không tạo ordering cross-variable như publication | Dùng `setRelease` trên flag và `getAcquire` bên consumer, với đúng thứ tự payload |
| “Dùng `setRelease` là đủ, consumer đọc plain cũng được” | Chưa có cặp acquire quan sát publication | Consumer dùng `getAcquire` trên đúng flag |
| “Dùng `getAcquire` rồi ghi payload sau `setRelease` vẫn ổn” | Ordering một hướng; publish trước dữ liệu là sai giao thức | Producer ghi payload **trước** release write |
| “`volatile` biến mọi `++` thành nguyên tử” | Read rồi write là hai operation | Dùng `getAndAdd`, CAS, lock |
| “Dùng `get` lên field khai báo volatile vẫn là volatile” | Access mode của VarHandle quyết định semantics của **lần truy cập** | Dùng `getVolatile`/`setVolatile` nhất quán theo giao thức |
| “`setOpaque` có thể sửa field final” | Final field là read-only qua VarHandle | Kiểm tra `isAccessModeSupported`, tái thiết kế state |
| “`setRelease` có thể ghép với `getRelease`” | Không tồn tại `getRelease` | Ghép `setRelease` với `getAcquire` |
| “`getAcquire`/`setRelease` luôn nhanh hơn volatile” | Performance phụ thuộc JIT, kiến trúc và contention | Benchmark toàn giao thức; ưu tiên tính đúng đắn |
| “Chạy nhiều lần chưa thấy bug thì plain/opaque an toàn” | Concurrency bug không bắt buộc tái hiện mọi lần | Lập luận theo memory model, test stress là bổ trợ |
| “VarHandle là hàm nhận `Object...` nên cứ bỏ cast int” | Mode methods là signature-polymorphic | Đặt đúng type/cast và tọa độ theo handle type |

**Cẩn thận với mode trộn lẫn:** Dùng plain read xen lẫn opaque/volatile write trên cùng biến không tự động kế thừa tính chất mạnh nhất của các lời gọi khác. Khi kiểm tra logic concurrency, phải khảo sát **tất cả** đường đọc và ghi tới vị trí chia sẻ đó, kể cả truy cập field thông thường và qua VarHandle.

## 11. Lựa chọn mode theo nhu cầu

Hãy bắt đầu từ **invariant cần bảo đảm**, sau đó mới chọn mode:

1. **Chỉ dùng trong một thread hoặc đã được lock bảo vệ:** plain `get/set` thường là đủ. Đừng tự thêm volatile nếu đồng bộ đã rõ ràng, nhưng cũng đừng bỏ lock vì thấy plain đọc đúng.
2. **Cần coherence một biến, không công bố trạng thái biến khác:** có thể nghiên cứu opaque, nếu thuật toán đã được chứng minh đúng và bạn hiểu giới hạn về ordering.
3. **Producer chuẩn bị dữ liệu rồi thông báo consumer:** thường dùng `setRelease` trên flag và `getAcquire` trên cùng flag; đảm bảo producer viết payload trước và consumer đọc payload sau khi thấy cờ.
4. **Cần semantics tương đương volatile field:** dùng `getVolatile/setVolatile`, hoặc khai báo `volatile` trực tiếp khi không cần thay đổi mode theo lời gọi.
5. **Cần thay đổi biến dưới cạnh tranh theo dạng cộng/CAS:** dùng `getAndAdd`, `compareAndSet`, `getAndSet`, lock hoặc primitive concurrency cấp cao. Memory ordering và atomic update là **hai yêu cầu khác nhau**.

Không chọn mode chỉ theo bảng “càng yếu càng nhanh”: mỗi lựa chọn phải giữ nguyên contract visibility/ordering, quyền truy cập, atomicity và liveness mà hệ thống cần.

## 12. Bài tập tự kiểm tra

**A.** Hai thread chia sẻ `ready` và `payload`. Producer viết `payload=7` rồi `readyHandle.setOpaque(state,1)`, consumer đọc `getOpaque(state)==1` và truy cập `payload`. Có được bảo đảm thấy `7` nhờ hai opaque access không?

**B.** Thay `setOpaque` bằng `setRelease` và `getOpaque` bằng `getAcquire` trên **cùng flag**, producer không ghi lại payload sau publication. Vì sao đây là publication pattern đúng hơn?

**C.** Một `VarHandle` trỏ đến `final long id`. Phương thức `getVolatile` có thể đọc nếu lookup hợp lệ không? `setVolatile` có được hỗ trợ không?

**D.** `int x = (int) HANDLE.get(box);` với `HANDLE` trỏ tới instance field `int`. Vì sao phải truyền `box`? Nếu đó là static field `int` thì cần thay đổi lời gọi thế nào?

**E.** Hai luồng cùng muốn tăng `count`, mỗi luồng dùng `getVolatile` rồi `setVolatile`. Có thể mất lượt tăng không? API nào phù hợp?

**F.** Trên JVM 32-bit, plain `get/set` của `long` có bảo đảm bitwise atomic tuyệt đối không? Opaque có bảo đảm đó không?

**G.** Field khai báo `volatile int flag`, nhưng đoạn code sử dụng `handle.get(instance)` thay vì `getVolatile`. Có thể mặc định kết luận đó là volatile read không?

**Đáp án:**

- **A:** Không; opaque chỉ mang coherence đối với biến flag, không đảm bảo ordering để publish payload khác.
- **B:** `setRelease` giữ các thao tác chuẩn bị trước publication, `getAcquire` giữ thao tác đọc payload sau khi nhận publication; cặp matched access vào đúng flag thiết lập ordering cần thiết cho ví dụ.
- **C:** Có thể đọc nếu đủ quyền. `setVolatile` là write mode không hỗ trợ trên final field; gọi sẽ ném `UnsupportedOperationException`.
- **D:** Instance VarHandle cần receiver `box` để xác định vị trí field; static VarHandle không cần receiver, dùng `(int) STATIC_HANDLE.get()`.
- **E:** Có thể mất lượt vì read/write tách rời. Dùng `getAndAdd`, CAS hoặc lock.
- **F:** Không; plain có thể thiếu bảo đảm bitwise atomic `long`/`double` trên 32-bit. Opaque bảo đảm bitwise atomic.
- **G:** Không. Access mode `get` là plain theo quy tắc VarHandle, dù declaration có `volatile`.

## 13. Tài liệu tham khảo

- [Oracle Java SE 17 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): mô tả các mode `get/set`, `getOpaque/setOpaque`, `getAcquire/setRelease`, `getVolatile/setVolatile`, atomicity, coherence và memory ordering.
- [JEP 193 — Variable Handles](https://openjdk.org/jeps/193): động cơ thiết kế VarHandle và các loại access mode.
- [Java Language Specification SE 17 — `17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): data race, ordering và happens-before trong Java.
- [Oracle Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle` và quyền lookup.

**Ghi nhớ:** `plain` không tạo visibility cross-thread; `opaque` thêm atomicity/coherence của chính biến; `release` ghi tín hiệu sau dữ liệu đã chuẩn bị, `acquire` đọc tín hiệu trước khi dùng dữ liệu; `volatile` có semantics ordering mạnh hơn và thứ tự toàn phần giữa volatile access. Đây là **các mode của từng lần truy cập**, không thay thế việc thiết kế đúng giao thức đồng bộ giữa các luồng.
