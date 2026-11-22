# Các biến thể acquire, release của thao tác cập nhật

`VarHandle` trong Java 9 cung cấp các thao tác đọc-sửa-ghi nguyên tử (*atomic read-modify-write*) cùng nhiều memory access mode. Với các thao tác cập nhật, ngoài biến thể mặc định có volatile semantics, API còn có các biến thể **acquire** và **release** như `getAndAddAcquire()`, `getAndAddRelease()`, `getAndSetAcquire()`, `getAndSetRelease()`, `compareAndExchangeAcquire()` và `compareAndExchangeRelease()`.

Điểm cần tách bạch là **tính nguyên tử của thao tác cập nhật** và **thứ tự bộ nhớ mà thao tác tạo ra**. Hậu tố `Acquire` hoặc `Release` thay đổi ordering semantics; nó không biến một thao tác cập nhật nguyên tử thành thao tác không nguyên tử. Ngược lại, nó cũng không cung cấp đầy đủ cả hai chiều ordering như biến thể volatile mặc định.

## Mục tiêu

- Hiểu acquire và release trong Java Memory Model.
- Phân biệt acquire/release với volatile semantics.
- Dùng các biến thể acquire/release của thao tác read-modify-write.
- Hiểu `getAndAddAcquire/Release()` và `getAndSetAcquire/Release()`.
- Dùng `compareAndExchangeAcquire/Release()` để cập nhật có điều kiện.
- Nhận biết `weakCompareAndSetAcquire/Release()` và khả năng thất bại giả.
- Chọn đúng mode theo hướng truyền dữ liệu giữa các thread.

## 1. Tách atomicity khỏi memory ordering

Thao tác read-modify-write thực hiện đọc giá trị hiện tại, tính giá trị mới và ghi lại như một thao tác nguyên tử đối với các thread cạnh tranh. Ví dụ:

~~~java
int previous = (int) COUNTER.getAndAdd(1);
~~~

Giá trị cũ được trả về, còn biến được tăng thêm một. Hai thread cùng gọi thao tác này không làm mất lần tăng theo kiểu lost update như khi viết `counter++` thông thường.

Memory ordering là một câu hỏi khác: các lần đọc/ghi khác trước hoặc sau thao tác cập nhật có thể được quan sát theo thứ tự nào giữa các thread? VarHandle cho phép chọn mức ordering cần thiết.

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Atomicity | Các thread có thể chen vào giữa phần đọc và phần ghi của thao tác cập nhật không? |
| Acquire/release/volatile ordering | Các truy cập bộ nhớ khác trước hoặc sau thao tác được sắp thứ tự thế nào? |

Vì vậy, `getAndAddAcquire()` vẫn là một phép cộng nguyên tử; `getAndAddRelease()` cũng vậy. Sự khác nhau nằm ở ràng buộc thứ tự bộ nhớ.

## 2. Acquire và release có ý nghĩa gì?

### 2.1. Acquire

Acquire là ordering ở phía sau thao tác. Các truy cập bộ nhớ sau acquire không được di chuyển lên trước acquire theo cách vi phạm memory semantics.

Acquire thường được dùng ở phía đọc/tiêu thụ: thread quan sát trạng thái được publish bởi thread khác, sau đó đọc dữ liệu mà thread kia đã chuẩn bị trước đó.

Ví dụ, reader đọc cờ bằng `getAcquire()`; khi nó quan sát giá trị được publisher ghi bằng release, các lần đọc payload tiếp theo có thể nhìn thấy dữ liệu đã được publish.

### 2.2. Release

Release là ordering ở phía trước thao tác. Các truy cập bộ nhớ trước release không được di chuyển xuống sau release theo cách vi phạm memory semantics.

Release thường được dùng ở phía ghi/công bố: thread chuẩn bị dữ liệu, rồi thực hiện release operation để thông báo trạng thái mới. Reader dùng acquire operation tương ứng để quan sát trạng thái đó.

### 2.3. So sánh với volatile

| Mode | Ràng buộc chính | Hướng sử dụng thường gặp |
| --- | --- | --- |
| Plain | Không tạo ordering liên thread | Thread-confined hoặc đã có synchronization khác |
| Acquire | Bảo vệ các truy cập sau thao tác | Bên đọc/tiêu thụ dữ liệu đã publish |
| Release | Bảo vệ các truy cập trước thao tác | Bên ghi/công bố dữ liệu |
| Volatile | Có cả ordering acquire và release | Khi cần semantics volatile đầy đủ |

Biến thể không có hậu tố như `getAndAdd()` hoặc `compareAndExchange()` dùng volatile memory semantics. Biến thể `Acquire` chỉ có ordering acquire; biến thể `Release` chỉ có ordering release. Không xem hai biến thể này là từ đồng nghĩa hoặc thay thế tùy ý cho volatile.

## 3. Các biến thể acquire/release của thao tác cập nhật

VarHandle cung cấp các nhóm thao tác sau với những biến thể memory mode tương ứng:

| Nhóm thao tác | Volatile mặc định | Acquire | Release |
| --- | --- | --- | --- |
| Đổi giá trị | `getAndSet()` | `getAndSetAcquire()` | `getAndSetRelease()` |
| Cộng giá trị | `getAndAdd()` | `getAndAddAcquire()` | `getAndAddRelease()` |
| AND bit | `getAndBitwiseAnd()` | `getAndBitwiseAndAcquire()` | `getAndBitwiseAndRelease()` |
| OR bit | `getAndBitwiseOr()` | `getAndBitwiseOrAcquire()` | `getAndBitwiseOrRelease()` |
| XOR bit | `getAndBitwiseXor()` | `getAndBitwiseXorAcquire()` | `getAndBitwiseXorRelease()` |
| Compare-and-exchange | `compareAndExchange()` | `compareAndExchangeAcquire()` | `compareAndExchangeRelease()` |

`weakCompareAndSet()` cũng có các biến thể `weakCompareAndSetAcquire()` và `weakCompareAndSetRelease()`; ngoài ra Java 9 còn có `weakCompareAndSetPlain()`.

Không phải mọi thao tác đều áp dụng cho mọi kiểu biến. Ví dụ, phép cộng chỉ phù hợp với các kiểu số được VarHandle hỗ trợ; các thao tác bitwise chỉ phù hợp với kiểu số nguyên tương ứng. Dùng `isAccessModeSupported()` nếu cần kiểm tra một mode trên handle cụ thể.

## 4. getAndAddAcquire() và getAndAddRelease()

`getAndAddAcquire(delta)` cộng `delta` vào biến và trả về giá trị trước cập nhật. Toàn bộ read-modify-write là nguyên tử và có acquire semantics.

~~~java
int previous = (int) COUNTER.getAndAddAcquire(2);
~~~

Acquire ordering hữu ích khi kết quả của thao tác cập nhật được dùng để nhận biết một trạng thái đã được publish và các truy cập tiếp theo cần được giữ sau thao tác acquire.

`getAndAddRelease(delta)` thực hiện cùng phép cập nhật nguyên tử nhưng có release semantics:

~~~java
int previous = (int) COUNTER.getAndAddRelease(3);
~~~

Release ordering hữu ích khi các lần ghi trước thao tác cập nhật cần được công bố trước khi trạng thái/counter được cập nhật.

### 4.1. Giá trị trả về

Cả hai biến thể đều trả về giá trị cũ trước khi cộng:

~~~java
int oldValue = (int) COUNTER.getAndAddRelease(5);
int newValue = oldValue + 5;
~~~

Giá trị trả về là giá trị trước cập nhật, không phải giá trị mới. Nếu cần đọc lại giá trị sau cập nhật, có thể thực hiện một lần đọc riêng với memory mode phù hợp.

### 4.2. Atomicity không có nghĩa là ordering hai chiều

`getAndAddAcquire()` không tự cung cấp release ordering cho các truy cập trước thao tác. `getAndAddRelease()` không tự cung cấp acquire ordering cho các truy cập sau thao tác. Nếu thuật toán cần cả hai chiều, dùng biến thể volatile mặc định hoặc thiết kế protocol rõ ràng với các thao tác acquire/release riêng.

## 5. getAndSetAcquire() và getAndSetRelease()

`getAndSet()` thay giá trị hiện tại bằng giá trị mới một cách nguyên tử và trả về giá trị cũ. Hai biến thể ordering:

~~~java
int oldAcquire = (int) STATE.getAndSetAcquire(READY);
int oldRelease = (int) STATE.getAndSetRelease(DONE);
~~~

- `getAndSetAcquire()` có acquire semantics; phù hợp khi cần lấy giá trị cũ và bảo đảm các truy cập tiếp theo không đi trước thao tác.
- `getAndSetRelease()` có release semantics; phù hợp khi cần công bố các thao tác ghi trước đó cùng với việc cập nhật trạng thái.

Ví dụ publication: writer chuẩn bị payload rồi dùng `getAndSetRelease(true)` trên cờ. Reader dùng `getAcquire()` để chờ cờ và sau đó đọc payload. Thao tác cập nhật cờ là atomic; release/acquire cung cấp ordering cần thiết cho payload.

## 6. compareAndExchangeAcquire() và compareAndExchangeRelease()

`compareAndExchange(expected, newValue)` là thao tác so sánh-và-trao-đổi nguyên tử. Nó đọc giá trị hiện tại; nếu giá trị bằng `expected`, nó ghi `newValue`. Phương thức trả về **witness value** — giá trị đã quan sát trước khi quyết định có cập nhật hay không.

~~~java
int witness = (int) STATE.compareAndExchangeRelease(0, 1);
if (witness == 0) {
    // Giá trị cũ là 0 và thao tác đã cập nhật thành 1.
} else {
    // Giá trị không phải 0; không có trao đổi.
}
~~~

`compareAndExchangeAcquire()` dùng acquire semantics. `compareAndExchangeRelease()` dùng release semantics. Cả hai vẫn thực hiện thao tác compare-and-exchange nguyên tử; hậu tố xác định ordering.

### 6.1. So sánh với compareAndSet()

| API | Kết quả trả về | Memory semantics |
| --- | --- | --- |
| `compareAndSet(expected, update)` | `boolean` thành công/thất bại | Volatile |
| `compareAndExchange(expected, update)` | Giá trị witness | Volatile |
| `compareAndExchangeAcquire(expected, update)` | Giá trị witness | Acquire |
| `compareAndExchangeRelease(expected, update)` | Giá trị witness | Release |

Java 9 không cung cấp các phương thức strong `compareAndSetAcquire()` và `compareAndSetRelease()`. Khi cần strong compare-and-exchange với ordering một chiều, dùng các biến thể `compareAndExchangeAcquire/Release()` và kiểm tra witness.

## 7. weakCompareAndSetAcquire() và weakCompareAndSetRelease()

`weakCompareAndSet()` trả về boolean nhưng có thể thất bại giả (*spurious failure*): nó có thể trả `false` ngay cả khi giá trị hiện tại bằng expected. Đây là điểm khác với strong `compareAndSet()`.

Java 9 có các biến thể:

- `weakCompareAndSetPlain(expected, update)`: không cung cấp ordering volatile/acquire/release.
- `weakCompareAndSet(expected, update)`: volatile semantics.
- `weakCompareAndSetAcquire(expected, update)`: acquire semantics.
- `weakCompareAndSetRelease(expected, update)`: release semantics.

Vì có thể thất bại giả, thường dùng weak CAS trong vòng lặp:

~~~java
int observed = (int) VALUE.getAcquire();
while (!VALUE.weakCompareAndSetRelease(observed, observed + 1)) {
    observed = (int) VALUE.getAcquire();
}
~~~

Trong ví dụ này, mỗi lần thất bại đều đọc lại giá trị rồi thử cập nhật. `getAcquire()` giữ ordering cho phần đọc; `weakCompareAndSetRelease()` công bố cập nhật theo release semantics. Nếu không cần tối ưu chuyên biệt, strong operation như `compareAndExchange()` thường dễ đọc và dễ reasoning hơn.

## 8. Chọn acquire, release hay volatile?

Hãy bắt đầu từ dữ liệu cần truyền và hướng của quan hệ ordering:

### Dùng acquire khi

- Thread hiện tại cần đọc trạng thái được công bố bởi thread khác.
- Sau khi quan sát trạng thái, thread sẽ đọc thêm dữ liệu liên quan.
- Thuật toán chỉ cần ràng buộc acquire ở phía tiêu thụ.

### Dùng release khi

- Thread hiện tại đã chuẩn bị dữ liệu và muốn công bố trạng thái mới.
- Các thao tác ghi trước đó phải được giữ trước lần cập nhật.
- Thuật toán chỉ cần ràng buộc release ở phía công bố.

### Dùng volatile khi

- Cần cả ordering phía trước và phía sau thao tác.
- Độ rõ ràng và correctness quan trọng hơn việc giảm memory ordering.
- Chưa có bằng chứng hiệu năng cho thấy acquire/release một chiều cần thiết.

Không chọn acquire/release chỉ vì tên nghe nhẹ hơn. Một mode yếu hơn nhưng đặt sai phía có thể làm hỏng protocol visibility. Cần xác định rõ writer nào publish, reader nào observe và thao tác nào ghép cặp.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ sau minh họa hai điều:

1. `getAndAddAcquire()` và `getAndAddRelease()` đều cập nhật counter nguyên tử và trả về giá trị trước cập nhật.
2. Writer ghi payload rồi dùng `getAndSetRelease(true)` để công bố trạng thái; reader dùng `getAcquire()` để quan sát trạng thái trước khi đọc payload.

**Tệp:** `VarHandleAcquireReleaseDemo.java`

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleAcquireReleaseDemo {
    private static int counter;
    private static int payload;
    private static boolean published;

    private static final VarHandle COUNTER;
    private static final VarHandle PAYLOAD;
    private static final VarHandle PUBLISHED;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            COUNTER = lookup.findStaticVarHandle(
                VarHandleAcquireReleaseDemo.class, "counter", int.class);
            PAYLOAD = lookup.findStaticVarHandle(
                VarHandleAcquireReleaseDemo.class, "payload", int.class);
            PUBLISHED = lookup.findStaticVarHandle(
                VarHandleAcquireReleaseDemo.class, "published", boolean.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        int beforeAcquire = (int) COUNTER.getAndAddAcquire(2);
        System.out.println("getAndAddAcquire previous: " + beforeAcquire);
        System.out.println("counter after acquire: " + (int) COUNTER.get());

        int beforeRelease = (int) COUNTER.getAndAddRelease(3);
        System.out.println("getAndAddRelease previous: " + beforeRelease);
        System.out.println("counter after release: " + (int) COUNTER.get());

        Thread reader = new Thread(() -> {
            while (!(boolean) PUBLISHED.getAcquire()) {
                Thread.onSpinWait();
            }
            int observed = (int) PAYLOAD.get();
            System.out.println("published payload: " + observed);
        });

        reader.start();
        PAYLOAD.set(42);
        PUBLISHED.getAndSetRelease(true);
        reader.join();
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 VarHandleAcquireReleaseDemo.java
java VarHandleAcquireReleaseDemo
~~~

Output:

~~~text
getAndAddAcquire previous: 0
counter after acquire: 2
getAndAddRelease previous: 2
counter after release: 5
published payload: 42
~~~

Trong phần counter, giá trị cũ lần lượt là `0` và `2`, còn giá trị sau cập nhật lần lượt là `2` và `5`. Phần publication sử dụng một writer và một reader: reader chỉ đọc `payload` sau khi acquire read quan sát cờ được release update.

`Thread.onSpinWait()` là hint cho vòng lặp chờ, không tự tạo synchronization. Quan hệ ordering trong ví dụ đến từ `getAndSetRelease()` và `getAcquire()` trên cùng cờ `published`.

## 10. Lưu ý về kiểu biến và access mode

`VarHandle` là signature-polymorphic API. Kiểu đối số và kiểu trả về phải phù hợp với biến mà handle đại diện.

- Field static: tạo handle bằng `findStaticVarHandle()`; không truyền receiver khi gọi access mode.
- Field instance: tạo handle bằng `findVarHandle()`; truyền object receiver làm đối số đầu tiên.
- `getAndAdd` cần kiểu biến số được hỗ trợ.
- Các thao tác bitwise chỉ áp dụng cho kiểu số nguyên phù hợp.
- `compareAndExchange` và compare-and-set yêu cầu expected/update tương thích với kiểu biến.
- Lookup phải có quyền truy cập field; nếu không, việc tạo handle thất bại.

Kiểm tra hỗ trợ của một mode:

~~~java
boolean supported = handle.isAccessModeSupported(
    VarHandle.AccessMode.GET_AND_ADD_RELEASE
);
~~~

Nếu mode không được hỗ trợ cho handle cụ thể, lời gọi access mode tương ứng có thể ném `UnsupportedOperationException`. Không giả định một thao tác hợp lệ cho mọi loại field.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ acquire/release làm mất atomicity | Nhầm ordering với atomicity | Các read-modify-write variant vẫn atomic; hậu tố chỉ đổi memory ordering |
| Dùng acquire ở phía writer để publish | Acquire chủ yếu bảo vệ truy cập sau thao tác | Dùng release ở phía công bố |
| Dùng release ở phía reader để nhận dữ liệu | Release bảo vệ truy cập trước thao tác | Dùng acquire ở phía tiêu thụ |
| Nghĩ acquire và release tương đương volatile | Mỗi mode chỉ cung cấp một hướng ordering | Dùng volatile khi cần cả hai chiều |
| Nghĩ `getAndAddAcquire()` cung cấp release semantics | Acquire variant không có release ordering | Chọn `getAndAddRelease()` hoặc volatile khi cần publish thao tác trước đó |
| Nghĩ `getAndAddRelease()` cung cấp acquire semantics | Release variant không có acquire ordering | Chọn acquire hoặc volatile nếu các truy cập sau cần ordering |
| Nghĩ `compareAndExchangeAcquire()` trả boolean | API trả witness value | So sánh witness với expected để biết trao đổi có xảy ra |
| Dùng weak CAS một lần rồi coi `false` là chắc chắn mismatch | Weak CAS có thể thất bại giả | Retry trong vòng lặp và đọc lại giá trị |
| Dùng read rồi set thay cho RMW | Hai thao tác riêng lẻ có thể bị thread khác chen vào | Dùng `getAndAdd`, compare-and-exchange hoặc CAS phù hợp |
| Dùng access mode không hỗ trợ cho kiểu biến | Không phải mọi mode áp dụng cho mọi handle | Kiểm tra kiểu field và `isAccessModeSupported()` |

## 12. Quy tắc thực hành

1. Xác định rõ thao tác cập nhật cần atomicity và ordering nào.
2. Dùng biến thể acquire ở phía tiêu thụ khi cần bảo vệ các truy cập sau thao tác.
3. Dùng biến thể release ở phía công bố khi cần bảo vệ các truy cập trước thao tác.
4. Dùng biến thể volatile mặc định khi cần cả acquire và release semantics.
5. Nhớ `getAndAddAcquire/Release()` vẫn là read-modify-write nguyên tử và trả về giá trị cũ.
6. Dùng `compareAndExchangeAcquire/Release()` khi cần compare-and-exchange strong với ordering một chiều.
7. Dùng weak CAS trong vòng lặp và xử lý khả năng thất bại giả.
8. Không thay thế atomic update bằng chuỗi `get()` rồi `set()` khi có cạnh tranh.
9. Không suy luận ordering chỉ từ kết quả một lần chạy; hãy reasoning theo Java Memory Model.
10. Kiểm tra access mode được hỗ trợ và đo hiệu năng trên workload thực tế.

## 13. Tự kiểm tra

- Acquire ordering bảo vệ truy cập ở phía nào? Các truy cập sau acquire không được di chuyển lên trước.
- Release ordering bảo vệ truy cập ở phía nào? Các truy cập trước release không được di chuyển xuống sau.
- `getAndAddAcquire()` có atomic không? Có, đây vẫn là thao tác read-modify-write nguyên tử.
- `getAndAddRelease()` trả về giá trị nào? Giá trị trước khi cộng.
- Khi nào dùng volatile variant? Khi cần cả acquire và release ordering.
- `compareAndExchangeRelease()` trả về gì? Witness value đã quan sát trước khi quyết định cập nhật.
- Java 9 có `compareAndSetAcquire()` không? Không; strong compare-and-exchange có các biến thể acquire/release.
- Weak compare-and-set có thể thất bại dù expected vẫn khớp không? Có, do spurious failure.
- Vì sao weak CAS thường nằm trong vòng lặp? Để thử lại khi có cạnh tranh hoặc thất bại giả.
- `Thread.onSpinWait()` có tạo happens-before không? Không; nó chỉ là hint cho vòng lặp chờ.

Điểm cốt lõi: **Acquire và release thay đổi ordering của thao tác cập nhật, còn atomicity của read-modify-write vẫn được giữ.** Dùng acquire ở phía nhận, release ở phía công bố và volatile khi cần cả hai chiều ordering.