# Đọc ghi thường và đọc ghi volatile với VarHandle

`VarHandle` được bổ sung trong Java 9 để cung cấp API thống nhất cho việc đọc, ghi và cập nhật biến của object hoặc class. Cùng một biến có thể được truy cập bằng nhiều *memory access mode*. Hai mode cơ bản cần phân biệt là **plain** (`get()` / `set()`) và **volatile** (`getVolatile()` / `setVolatile()`).

Plain access có ngữ nghĩa tương tự truy cập field thông thường không khai báo `volatile`. Volatile access có ngữ nghĩa bộ nhớ của thao tác volatile trong Java Memory Model: nó cung cấp visibility và ordering giữa các thread thông qua quan hệ *happens-before*. Chọn đúng mode quyết định liệu thao tác chỉ cần đọc/ghi giá trị hay còn phải phối hợp trạng thái giữa nhiều thread.

## Mục tiêu

- Tạo `VarHandle` cho field instance hoặc static.
- Phân biệt `get()` / `set()` với `getVolatile()` / `setVolatile()`.
- Hiểu visibility, ordering và quan hệ happens-before.
- Dùng volatile flag để publish dữ liệu an toàn giữa các thread.
- Biết vì sao volatile không làm phép `counter++` trở thành atomic.
- Chọn `compareAndSet()` hoặc `getAndAdd()` khi cần cập nhật nguyên tử.
- Nhận biết các mode acquire/release và lỗi khi trộn memory mode.

## 1. VarHandle và memory access mode

`VarHandle` là một handle có kiểu tới một biến. Biến có thể là field của object, field static hoặc phần tử của array. Sau khi lấy handle, chương trình gọi một access mode để thao tác trên biến đó.

Ví dụ khai báo field và lấy handle cho field static:

~~~java
private static int value;
private static final VarHandle VALUE;

static {
    try {
        VALUE = MethodHandles.lookup().findStaticVarHandle(
            MyClass.class, "value", int.class);
    } catch (ReflectiveOperationException exception) {
        throw new ExceptionInInitializerError(exception);
    }
}
~~~

`findStaticVarHandle()` nhận class khai báo, tên field và kiểu field. Với field instance, dùng `findVarHandle()`; khi truy cập phải truyền thêm object receiver.

`VarHandle` không tạo biến mới. Nó là cách truy cập biến đã tồn tại, với memory mode được chọn ở từng lời gọi. Thường lưu handle trong `static final` để dùng lại.

## 2. Plain read/write: get() và set()

`get()` và `set()` sử dụng plain memory mode:

~~~java
VALUE.set(10);
int current = (int) VALUE.get();
~~~

Plain mode có ngữ nghĩa giống truy cập field thông thường không có volatile ordering. Nó phù hợp khi biến chỉ được dùng trong một thread, khi mọi truy cập đã được bảo vệ bởi cùng một lock/cơ chế đồng bộ khác, hoặc khi ứng dụng không cần bảo đảm visibility/order liên thread từ chính thao tác này.

Plain mode **không tự tạo quan hệ happens-before** giữa hai thread. Nếu một thread ghi plain và thread khác đọc plain mà không có synchronization thích hợp, chương trình có data race. Thread đọc không được bảo đảm thấy giá trị mới hoặc quan sát các lần ghi theo thứ tự mà ứng dụng mong đợi.

Điều này không có nghĩa plain access luôn đọc sai hoặc luôn bị reorder. Nó có nghĩa Java Memory Model không cung cấp bảo đảm đồng bộ liên thread mà volatile hoặc lock cung cấp.

### 2.1. Plain access không phải cơ chế publish

~~~java
// Thread A
data = 42;
ready = true;

// Thread B
if (ready) {
    use(data);
}
~~~

Nếu cả `data` và `ready` đều là field thường, hai đoạn truy cập không có synchronization. Thread B không có bảo đảm rằng khi thấy `ready == true` thì nó cũng thấy `data == 42`. Không dùng cặp plain read/write làm cờ báo sẵn sàng giữa các thread.

## 3. Volatile read/write: getVolatile() và setVolatile()

`getVolatile()` và `setVolatile()` thực hiện truy cập với volatile memory semantics:

~~~java
VALUE.setVolatile(10);
int current = (int) VALUE.getVolatile();
~~~

Volatile access cung cấp hai thuộc tính quan trọng:

- **Visibility:** một volatile write có quan hệ *synchronizes-with* với các volatile read tiếp theo của cùng biến trong synchronization order. Nhờ đó, các thao tác ghi trước volatile write có thể được thread đọc quan sát sau volatile read tương ứng.
- **Ordering:** compiler và runtime phải tuân thủ ràng buộc thứ tự của volatile access theo Java Memory Model; các thao tác không được di chuyển qua volatile access theo cách phá vỡ semantics đã quy định.

Volatile read/write cũng là thao tác nguyên tử đối với chính lần đọc hoặc ghi biến. Tuy nhiên, tính nguyên tử của một lần truy cập không làm cho chuỗi nhiều thao tác trở thành một thao tác nguyên tử.

### 3.1. So sánh plain và volatile

| Tiêu chí | Plain: `get()` / `set()` | Volatile: `getVolatile()` / `setVolatile()` |
| --- | --- | --- |
| Memory semantics | Plain | Volatile |
| Visibility liên thread | Không tự bảo đảm | Có qua quan hệ volatile synchronizes-with |
| Ordering liên thread | Không tạo ordering đồng bộ | Có ordering theo Java Memory Model |
| Happens-before | Không tự tạo | Volatile write/read có thể tạo quan hệ happens-before |
| Trường hợp dùng | Thread-confined hoặc đã có synchronization khác | Cờ trạng thái, publication và dữ liệu cần visibility liên thread |

Không nên chọn mode dựa trên giả định volatile luôn chậm hơn theo một tỷ lệ cố định. Hiệu năng phụ thuộc kiến trúc, runtime, vị trí contention và workload; hãy đo trên ứng dụng thực tế.

### 3.2. Field khai báo volatile và VarHandle

Với Java field khai báo `volatile`, cách đọc/ghi trực tiếp cũng có volatile semantics:

~~~java
private static volatile boolean ready;

// Volatile write
ready = true;

// Volatile read
if (ready) {
    continueWork();
}
~~~

VarHandle cho phép biểu đạt mode ngay tại lời gọi bằng `setVolatile()` và `getVolatile()`. Trong ví dụ hoàn chỉnh, field `ready` được khai báo volatile để ý định dễ đọc; các lời gọi VarHandle vẫn thể hiện rõ mode đang dùng.

## 4. Happens-before và visibility

Java Memory Model định nghĩa quan hệ happens-before để xác định khi nào một thread phải quan sát được tác động của thread khác.

Một volatile write vào biến `ready` synchronizes-with các volatile read tiếp theo của cùng biến trong synchronization order. Do đó, nếu thread A ghi dữ liệu trước volatile write, và thread B đọc được volatile write đó qua volatile read, các thao tác ghi dữ liệu trước đó happens-before các thao tác đọc sau đó.

~~~text
Thread A (writer)                 Thread B (reader)
-----------------                 -----------------
PAYLOAD.set(42)                   while (!READY.getVolatile())
READY.setVolatile(true)     --->  đọc READY thấy true
                                  PAYLOAD.get() thấy 42

  ghi payload
      happens-before
  đọc payload sau volatile read
~~~

Volatile flag có thể publish một nhóm dữ liệu đã được ghi trước đó. Bản thân payload không cần là volatile nếu mọi lần đọc payload diễn ra sau volatile read bảo đảm publication và không có ghi cạnh tranh không được đồng bộ khác.

## 5. Safe publication bằng volatile flag

Ví dụ dưới đây dùng plain access cho `payload` và volatile access cho `ready`. Writer ghi payload trước, rồi đặt cờ `ready`. Reader lặp đến khi đọc được cờ bằng volatile mode, sau đó đọc payload bằng plain mode.

~~~java
private static int payload;
private static volatile boolean ready;

// Writer
PAYLOAD.set(42);
READY.setVolatile(true);

// Reader
while (!(boolean) READY.getVolatile()) {
    Thread.onSpinWait();
}
int observed = (int) PAYLOAD.get();
~~~

Khi reader thấy `ready == true` từ volatile write của writer, ghi `payload = 42` trước đó được publish tới reader. `Thread.onSpinWait()` chỉ là gợi ý tối ưu vòng lặp chờ cho runtime/CPU; nó **không tạo synchronization**. Quan hệ visibility đến từ volatile write/read.

Busy-spin chỉ phù hợp với một số trường hợp đặc thù. Với chờ lâu, cân nhắc `CountDownLatch`, `BlockingQueue`, lock/condition hoặc cơ chế phối hợp thread phù hợp.

## 6. Volatile không làm phép đọc-sửa-ghi thành atomic

Một lỗi phổ biến là cho rằng dùng volatile cho counter thì `counter++` sẽ an toàn giữa nhiều thread. Thực tế, phép tăng là một chuỗi thao tác:

1. Đọc giá trị hiện tại.
2. Cộng thêm một.
3. Ghi giá trị mới.

Hai thread có thể cùng đọc `5`, cùng tính `6`, rồi cùng ghi `6`. Một lần tăng bị mất dù mỗi lần đọc và ghi riêng lẻ đều là volatile.

~~~java
private static volatile int counter;

// Không bảo đảm atomic khi nhiều thread cùng thực hiện
counter++;
~~~

Volatile phù hợp cho trạng thái đơn giản như `ready`, `closed`, `currentConfig` khi một lần đọc/ghi là đủ. Nó không thay thế lock hoặc atomic read-modify-write.

### 6.1. Dùng getAndAdd()

Với VarHandle trỏ tới biến số nguyên, có thể dùng read-modify-write atomic:

~~~java
int previous = (int) COUNTER.getAndAdd(1);
~~~

`getAndAdd(1)` thực hiện phép cộng và trả về giá trị trước cập nhật như một thao tác nguyên tử.

### 6.2. Dùng compareAndSet()

~~~java
boolean updated = (boolean) COUNTER.compareAndSet(expected, replacement);
~~~

`compareAndSet()` chỉ cập nhật nếu giá trị hiện tại bằng `expected`, và phép so sánh/cập nhật diễn ra nguyên tử. Nó là nền tảng cho thuật toán lock-free và các vòng lặp cập nhật có điều kiện.

Không tự viết vòng `get()` rồi `set()` khi cần atomic compare/update; dùng một access mode read-modify-write thích hợp.

## 7. Các memory mode khác

Ngoài plain và volatile, VarHandle còn cung cấp các mode hữu ích trong một số thuật toán đồng thời:

| Mode | Phương thức ví dụ | Ý nghĩa khái quát |
| --- | --- | --- |
| Opaque | `getOpaque()` / `setOpaque()` | Bảo đảm tính nhất quán theo biến ở mức yếu hơn; không cung cấp đầy đủ ordering của volatile |
| Acquire | `getAcquire()` | Các thao tác đọc sau acquire không được reorder vượt qua acquire theo hướng bị cấm |
| Release | `setRelease()` | Các thao tác trước release không được reorder vượt qua release theo hướng bị cấm |
| Volatile | `getVolatile()` / `setVolatile()` | Ordering và visibility theo semantics volatile |

Acquire/release thường được dùng theo cặp: writer thực hiện `setRelease()`, reader dùng `getAcquire()` và đọc thấy giá trị được publish. Đây là công cụ chuyên biệt; nếu chưa có lý do hiệu năng và hiểu rõ Java Memory Model, volatile mode dễ đọc và ít sai sót hơn.

Opaque không phải phiên bản volatile nhẹ hơn có thể thay thế tùy ý. Chỉ dùng opaque/acquire/release khi thuật toán được thiết kế theo đúng memory semantics của chúng.

## 8. Tạo VarHandle và kiểm tra access mode

### 8.1. Field static

~~~java
VarHandle handle = MethodHandles.lookup().findStaticVarHandle(
    Config.class, "version", int.class
);
~~~

### 8.2. Field instance

~~~java
VarHandle handle = MethodHandles.lookup().findVarHandle(
    User.class, "active", boolean.class
);

User user = new User();
handle.set(user, true);
boolean active = (boolean) handle.get(user);
~~~

Với field instance, receiver object là đối số đầu tiên của mỗi access mode. Với field static, không truyền receiver.

### 8.3. Quyền truy cập và kiểu dữ liệu

`MethodHandles.lookup()` áp dụng quy tắc truy cập Java. Lookup phải có quyền truy cập field; nếu không, việc tạo handle có thể thất bại với `IllegalAccessException` hoặc lỗi lookup tương ứng.

Kiểu field phải khớp với kiểu được truyền khi tìm handle. Các lời gọi VarHandle là signature-polymorphic; truyền sai kiểu hoặc sai số lượng đối số có thể gây `WrongMethodTypeException` hoặc `ClassCastException`.

Một số access mode không được hỗ trợ cho mọi kiểu biến hoặc mọi loại handle. Có thể kiểm tra trước bằng `handle.isAccessModeSupported(VarHandle.AccessMode.COMPARE_AND_SET)` khi thuật toán cần mode cụ thể.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ gồm ba phần:

- Dùng plain `set()` / `get()` để đọc ghi một field thường trong cùng thread.
- Dùng volatile `setVolatile()` / `getVolatile()` để đọc ghi field volatile.
- Dùng volatile flag để publish một payload plain từ writer sang reader.

**Tệp:** `VarHandleReadWriteDemo.java`

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleReadWriteDemo {
    private static int plainValue;
    private static volatile int volatileValue;
    private static int payload;
    private static volatile boolean ready;

    private static final VarHandle PLAIN_VALUE;
    private static final VarHandle VOLATILE_VALUE;
    private static final VarHandle PAYLOAD;
    private static final VarHandle READY;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            PLAIN_VALUE = lookup.findStaticVarHandle(
                VarHandleReadWriteDemo.class, "plainValue", int.class);
            VOLATILE_VALUE = lookup.findStaticVarHandle(
                VarHandleReadWriteDemo.class, "volatileValue", int.class);
            PAYLOAD = lookup.findStaticVarHandle(
                VarHandleReadWriteDemo.class, "payload", int.class);
            READY = lookup.findStaticVarHandle(
                VarHandleReadWriteDemo.class, "ready", boolean.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        PLAIN_VALUE.set(7);
        System.out.println("plain read: " + (int) PLAIN_VALUE.get());

        VOLATILE_VALUE.setVolatile(9);
        System.out.println("volatile read: " + (int) VOLATILE_VALUE.getVolatile());

        Thread reader = new Thread(() -> {
            while (!(boolean) READY.getVolatile()) {
                Thread.onSpinWait();
            }
            int observed = (int) PAYLOAD.get();
            System.out.println("published payload: " + observed);
        });

        reader.start();
        PAYLOAD.set(42);
        READY.setVolatile(true);
        reader.join();
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 VarHandleReadWriteDemo.java
java VarHandleReadWriteDemo
~~~

Output:

~~~text
plain read: 7
volatile read: 9
published payload: 42
~~~

Output minh họa giá trị trong lần chạy. Điều cần kiểm chứng của phần publication là reader chỉ đọc payload sau khi volatile read quan sát được `ready == true`; quan hệ happens-before bảo đảm reader thấy payload được writer ghi trước volatile write.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `get()` / `set()` cho cờ chia sẻ giữa thread | Plain access không tạo visibility/happens-before | Dùng volatile mode hoặc cơ chế đồng bộ khác |
| Nghĩ plain access luôn đọc giá trị cũ | Plain mode không bảo đảm visibility, nhưng cũng không khẳng định luôn stale | Diễn đạt theo bảo đảm JMM; không dựa vào kết quả một lần chạy |
| Nghĩ volatile chỉ bảo đảm visibility mà không có ordering | Volatile có cả memory ordering semantics | Hiểu quan hệ synchronizes-with/happens-before |
| Nghĩ volatile làm `counter++` atomic | Increment là read-modify-write gồm nhiều bước | Dùng `getAndAdd()`, `compareAndSet()` hoặc lock |
| Dùng volatile cho nhiều field cần cập nhật nhất quán cùng lúc | Volatile chỉ điều phối từng biến, không tạo transaction nhiều field | Dùng lock hoặc cấu trúc immutable được publish an toàn |
| Nghĩ `Thread.onSpinWait()` tạo visibility | Đây chỉ là hint cho vòng spin | Dùng volatile/lock/latch/queue để đồng bộ |
| Trộn plain và volatile access mà không có thiết kế | Mỗi mode có memory effects khác nhau | Ghi rõ protocol writer/reader và chọn mode nhất quán |
| Nghĩ `setRelease()` tương đương hoàn toàn `setVolatile()` | Release có ordering yếu hơn volatile | Dùng volatile nếu cần semantics volatile; chỉ dùng release khi hiểu yêu cầu |
| Tạo VarHandle với sai field/type hoặc thiếu quyền | Lookup không tìm được field hoặc call site sai kiểu | Kiểm tra class, tên, kiểu và quyền truy cập |

## 11. Quy tắc thực hành

1. Dùng `get()` / `set()` cho plain access khi thread confinement hoặc synchronization khác đã bảo vệ biến.
2. Dùng `getVolatile()` / `setVolatile()` cho trạng thái chia sẻ cần visibility và ordering volatile.
3. Dùng volatile flag để publish dữ liệu đã ghi trước đó; reader phải đọc flag bằng volatile mode trước khi đọc payload.
4. Không suy luận bảo đảm đồng bộ từ việc test trên một máy thấy giá trị mới.
5. Không dùng volatile thay cho atomic read-modify-write; dùng `getAndAdd()`, `compareAndSet()` hoặc lock.
6. Phân biệt `Thread.onSpinWait()` với cơ chế đồng bộ thực sự.
7. Chỉ dùng opaque/acquire/release khi đã hiểu memory semantics và có lý do cụ thể.
8. Tạo handle một lần và lưu trong `static final` khi phù hợp.
9. Kiểm tra access mode được hỗ trợ và quyền truy cập field.
10. Đo hiệu năng trên workload thực tế thay vì mặc định một mode luôn nhanh hơn.

## 12. Tự kiểm tra

- `VarHandle.get()` và `set()` dùng memory mode nào? Plain.
- `getVolatile()` và `setVolatile()` dùng mode nào? Volatile.
- Plain access có tự tạo happens-before giữa hai thread không? Không.
- Volatile write/read có thể tạo quan hệ nào? Synchronizes-with và từ đó là happens-before cho các thao tác trước/sau tương ứng.
- Vì sao volatile flag có thể publish một payload plain? Writer ghi payload trước volatile write; reader quan sát volatile write qua volatile read rồi đọc payload.
- `Thread.onSpinWait()` có phải synchronization không? Không, đó là hint cho vòng lặp chờ.
- Volatile có làm `counter++` atomic không? Không.
- Cần dùng gì cho increment nguyên tử? `VarHandle.getAndAdd()` hoặc cơ chế atomic/lock phù hợp.
- Khi nào dùng `compareAndSet()`? Khi cần so sánh và cập nhật trong một thao tác nguyên tử.
- Khi nào dùng acquire/release? Khi thuật toán cần ordering một chiều và được thiết kế, kiểm thử theo đúng memory semantics.

Điểm cốt lõi: **plain `get/set` chỉ đọc ghi theo ngữ nghĩa thường; volatile `getVolatile/setVolatile` bổ sung visibility và ordering giữa các thread.** Chọn mode theo protocol đồng bộ của ứng dụng, và dùng thao tác read-modify-write nguyên tử khi cần cập nhật kết hợp.