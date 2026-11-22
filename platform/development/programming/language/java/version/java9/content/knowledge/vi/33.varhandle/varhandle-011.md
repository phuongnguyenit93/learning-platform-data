# Chọn `VarHandle` khi các lớp atomic có sẵn chưa phù hợp

`AtomicInteger`, `AtomicLong` và `AtomicReference` là những lựa chọn dễ dùng khi ứng dụng cần một biến độc lập có thao tác nguyên tử. Tuy nhiên, đôi khi trạng thái đã nằm sẵn trong một field hoặc phần tử mảng, cần nhiều kiểu memory ordering, hoặc cần một thao tác truy cập mức thấp hơn mà các lớp atomic đóng gói sẵn không thể biểu đạt trực tiếp. Trong những trường hợp đó, `VarHandle` là lựa chọn đáng cân nhắc.

`VarHandle` được bổ sung từ Java 9. Nó cung cấp một tham chiếu có kiểu đến field, phần tử mảng hoặc một biến có cấu trúc truy cập phù hợp; từ cùng handle, chương trình có thể chọn plain, opaque, acquire, release, volatile hoặc các access mode cập nhật nguyên tử. Đây là công cụ mức thấp để kiểm soát cách truy cập biến, không phải lý do để thay mọi lớp atomic trong ứng dụng.

## 1. Bắt đầu từ yêu cầu, không bắt đầu từ API

Trước khi chọn công cụ đồng bộ, hãy xác định chính xác trạng thái nào cần bảo vệ và thao tác nào phải nguyên tử.

- Nếu chỉ cần một bộ đếm độc lập, `AtomicInteger` hoặc `AtomicLong` thường đơn giản và dễ đọc.
- Nếu cần thay thế một tham chiếu độc lập, `AtomicReference<T>` thường thể hiện ý định rõ ràng.
- Nếu trạng thái đã nằm trong field của object hoặc trong array và không muốn thay đổi cấu trúc dữ liệu chỉ để bọc nó bằng một atomic holder, `VarHandle` có thể truy cập trực tiếp vị trí đó.
- Nếu cần chọn memory ordering khác nhau cho từng lần đọc/ghi, các access mode của `VarHandle` cung cấp quyền kiểm soát chi tiết.
- Nếu một invariant trải trên nhiều field phải được cập nhật như một giao dịch, một `VarHandle` cho từng field không tự tạo ra phép cập nhật nguyên tử nhiều field; hãy xem xét lock hoặc thay thế một object trạng thái bất biến bằng CAS trên một reference.

Chọn API theo invariant và hợp đồng cần bảo đảm. Đừng chọn `VarHandle` chỉ vì nó có nhiều access mode hơn.

## 2. Các lớp atomic có sẵn phù hợp khi nào?

`java.util.concurrent.atomic` cung cấp những lớp chuyên biệt với API cấp cao hơn:

| API | Khi phù hợp |
| --- | --- |
| `AtomicInteger`, `AtomicLong`, `AtomicBoolean` | Một giá trị primitive độc lập cần cập nhật nguyên tử |
| `AtomicReference<T>` | Một reference độc lập cần thay thế hoặc CAS |
| `AtomicIntegerArray`, `AtomicLongArray`, `AtomicReferenceArray<T>` | Mảng atomic có API rõ ràng cho từng phần tử |
| `AtomicIntegerFieldUpdater<T>`, `AtomicLongFieldUpdater<T>`, `AtomicReferenceFieldUpdater<T,V>` | Cập nhật một field phù hợp trong object hiện có bằng updater chuyên biệt |
| `LongAdder` | Bộ đếm thống kê có nhiều thread cập nhật; `sum()` không phải snapshot nguyên tử tức thời |

Ví dụ với một bộ đếm độc lập:

```java
AtomicInteger requests = new AtomicInteger();
int current = requests.incrementAndGet();
```

Đoạn mã cho thấy rõ ý định: tăng một bộ đếm nguyên tử. Không cần tự tạo `VarHandle`, tự viết vòng lặp CAS hay chọn memory mode. Với trạng thái đơn giản như vậy, lớp atomic chuyên biệt thường là lựa chọn tốt hơn.

Field updater cũng có thể phù hợp nếu field hiện có là `volatile` và chỉ cần những thao tác mà updater cung cấp. Tuy nhiên, updater có hợp đồng truy cập và yêu cầu kiểu riêng; `VarHandle` cho phép tạo handle có kiểu trực tiếp và cung cấp nhiều access mode hơn, bao gồm acquire/release và các dạng compare-and-exchange.

## 3. Khi `VarHandle` giải quyết được điều mà atomic holder không tiện làm

### Truy cập field đã có sẵn

Giả sử một object đã có field `count` và nhiều thành phần cần cập nhật field đó. Bọc field bằng `AtomicInteger` có thể buộc phải đổi kiểu dữ liệu, thay đổi cấu trúc object hoặc sửa nhiều nơi đang sử dụng field. Một `VarHandle` có thể truy cập trực tiếp field hiện có mà không cần thay field thành một atomic holder.

Điều này hữu ích trong thư viện, framework, cấu trúc dữ liệu hoặc code cần giữ layout của object. Tuy vậy, handle vẫn phải được tạo qua lookup hợp lệ và các access mode phải được dùng đúng với kiểu biến.

### Truy cập phần tử mảng

`MethodHandles.arrayElementVarHandle(arrayType)` tạo handle cho phần tử của một loại mảng. Tọa độ truy cập gồm mảng và chỉ số, sau đó là các đối số của access mode. Điều này cho phép dùng CAS hoặc các thao tác nguyên tử trên phần tử mảng mà không phải tạo một atomic object riêng cho từng phần tử.

```java
int[] values = {5};
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
boolean changed = element.compareAndSet(values, 0, 5, 9);
```

Trong ví dụ, tọa độ là `values` và `0`; `5` là giá trị kỳ vọng, `9` là giá trị cập nhật. Nếu phần tử tại vị trí đó vẫn bằng `5` ở thời điểm nguyên tử, nó được đổi thành `9`.

### Chọn memory ordering theo từng thao tác

Atomic classes cung cấp các thao tác tiện dụng với semantics được định nghĩa sẵn. `VarHandle` hữu ích khi thuật toán cần phân biệt rõ plain, opaque, acquire, release và volatile access, hoặc cần phối hợp các thao tác với một giao thức công bố dữ liệu đã được thiết kế và chứng minh.

Đây là lý do kỹ thuật đáng kể để dùng `VarHandle`; chỉ thay đổi access mode vì nghĩ rằng nó nhanh hơn có thể làm sai visibility hoặc ordering giữa các thread.

## 4. Tạo VarHandle cho field

Với field instance, dùng `MethodHandles.Lookup.findVarHandle()`:

```java
VarHandle handle = MethodHandles.lookup().findVarHandle(
        Counter.class, "count", int.class);
```

Với field static, dùng `findStaticVarHandle()`. Với array element, dùng `arrayElementVarHandle()` như ví dụ trước.

Coordinate types phụ thuộc loại handle:

| Loại biến | Coordinate khi gọi access mode |
| --- | --- |
| Field instance | Đối tượng chứa field |
| Field static | Không có coordinate |
| Array element | Mảng và chỉ số phần tử |

Lookup chịu kiểm tra quyền truy cập Java. Nếu field không thể truy cập bằng lookup hiện tại, việc tạo handle có thể ném `IllegalAccessException`; tên hoặc kiểu field không đúng có thể dẫn đến `NoSuchFieldException`. Khi truy cập private member của class khác, `MethodHandles.privateLookupIn()` có thể cần thiết, và quyền truy cập còn chịu quy tắc module: package của module đích phải được mở phù hợp cho module gọi.

Không dùng reflection hoặc lookup để vượt qua chính sách truy cập của ứng dụng. Tạo handle một lần ở vị trí có trách nhiệm và tái sử dụng nó; tránh lặp lại lookup cho mỗi lần cập nhật.

## 5. Access mode là một phần của hợp đồng

Một `VarHandle` cung cấp nhiều access mode. Chúng không chỉ là những tên gọi khác nhau cho cùng một thao tác:

| Nhóm access mode | Ví dụ | Ý nghĩa chính |
| --- | --- | --- |
| Plain | `get`, `set` | Truy cập thông thường, không thêm ordering đồng bộ |
| Opaque | `getOpaque`, `setOpaque` | Bảo đảm nhất quán truy cập ở mức opaque, ordering yếu hơn acquire/release |
| Acquire/release | `getAcquire`, `setRelease` | Phối hợp công bố dữ liệu theo quan hệ acquire/release |
| Volatile | `getVolatile`, `setVolatile` | Có semantics visibility và ordering của volatile |
| Atomic update | `compareAndSet`, `compareAndExchange`, `getAndAdd` | Thực hiện thao tác cập nhật nguyên tử phù hợp với biến |

`compareAndSet()` và `compareAndExchange()` mặc định có volatile read/write semantics. Các biến thể như `compareAndExchangeAcquire()` và `compareAndExchangeRelease()` cho phép chọn ordering yếu hơn khi thuật toán chỉ cần ordering tương ứng.

Chỉ chọn access mode yếu hơn khi đã xác định quan hệ happens-before và yêu cầu visibility của dữ liệu. Nếu không có lý do rõ ràng, dùng semantics dễ hiểu và dễ kiểm chứng trước; đừng tự tối ưu memory ordering theo cảm tính.

Mỗi handle không nhất thiết hỗ trợ mọi access mode. Có thể kiểm tra bằng `isAccessModeSupported(VarHandle.AccessMode.COMPARE_AND_SET)`; gọi một mode không được hỗ trợ sẽ ném `UnsupportedOperationException`. Kiểu biến, alignment và loại handle ảnh hưởng đến những mode khả dụng.

## 6. Ví dụ hoàn chỉnh: atomic holder, field hiện có và array element

Ví dụ dưới đây đặt ba cách tiếp cận cạnh nhau. `AtomicInteger` quản lý một giá trị độc lập. `VarHandle` truy cập trực tiếp field `count` trong object `Counter`. Một handle khác cập nhật nguyên tử phần tử của mảng `int[]`.

Tạo tệp `VarHandleChoiceDemo.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.atomic.AtomicInteger;

public class VarHandleChoiceDemo {
    private static final class Counter {
        private int count;
        private static final VarHandle COUNT;

        static {
            try {
                COUNT = MethodHandles.lookup().findVarHandle(
                        Counter.class, "count", int.class);
            } catch (ReflectiveOperationException ex) {
                throw new ExceptionInInitializerError(ex);
            }
        }

        void increment() {
            int current = (int) COUNT.getVolatile(this);
            while (!COUNT.compareAndSet(this, current, current + 1)) {
                current = (int) COUNT.getVolatile(this);
            }
        }

        int get() {
            return (int) COUNT.getVolatile(this);
        }
    }

    public static void main(String[] args) {
        AtomicInteger standalone = new AtomicInteger(10);
        System.out.println("AtomicInteger update: " + standalone.incrementAndGet());

        Counter counter = new Counter();
        counter.increment();
        counter.increment();
        System.out.println("Existing field via VarHandle: " + counter.get());

        int[] values = {5};
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
        boolean changed = element.compareAndSet(values, 0, 5, 9);
        System.out.println("Array element CAS: " + changed);
        System.out.println("Array value: " + values[0]);
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all VarHandleChoiceDemo.java
java VarHandleChoiceDemo
```

Kết quả stdout:

```text
AtomicInteger update: 11
Existing field via VarHandle: 2
Array element CAS: true
Array value: 9
```

Trong ví dụ, field `count` vẫn là `int` thông thường. `VarHandle` chọn `getVolatile()` và `compareAndSet()` cho từng lần truy cập; không cần khai báo field là `volatile` để access mode của handle có volatile semantics. Cách này cho thấy memory semantics thuộc về access mode được gọi.

Vòng lặp CAS đọc lại giá trị khi có thread khác cập nhật đồng thời. Ví dụ chạy một thread nên không thể hiện contention; trong ứng dụng nhiều thread, cần kiểm thử tính đúng đắn của invariant và đo hiệu năng dưới tải thực tế.

## 7. Vì sao không dùng VarHandle cho mọi thứ?

`VarHandle` có mức kiểm soát thấp hơn và đòi hỏi người viết hiểu rõ memory model. Dùng nó cho một bộ đếm đơn giản có thể làm code dài hơn mà không đem lại lợi ích.

Ưu tiên atomic class chuyên biệt khi:

- Trạng thái là một biến độc lập và API có sẵn đáp ứng đầy đủ.
- Muốn code ngắn, thể hiện ý định rõ và giảm rủi ro sai memory ordering.
- Cần một cấu trúc chuyên dụng như `LongAdder` cho thống kê có contention cao.
- Không có yêu cầu truy cập field/array hiện có hoặc access mode đặc biệt.

Ưu tiên `VarHandle` khi:

- Cần thao tác nguyên tử trực tiếp trên field hoặc array element hiện có.
- Không muốn đổi layout dữ liệu chỉ để thêm một atomic wrapper.
- Cần chọn access mode hoặc memory ordering cụ thể.
- Đang xây dựng thư viện/cấu trúc dữ liệu mức thấp và cần một handle có kiểu cho nhiều loại thao tác.

## 8. Giới hạn quan trọng: nhiều field không thành một giao dịch

Một `VarHandle` chỉ bảo đảm semantics của thao tác trên biến mà handle đại diện. Nếu object có hai field `balance` và `version`, gọi CAS riêng trên từng field không làm cho cặp cập nhật trở thành nguyên tử. Thread khác có thể quan sát trạng thái nằm giữa hai lần cập nhật.

Nếu invariant phụ thuộc nhiều field, có thể dùng:

- `synchronized` hoặc `Lock` để bảo vệ toàn bộ vùng cập nhật.
- Một object trạng thái bất biến chứa tất cả giá trị liên quan, rồi dùng `AtomicReference<State>` hoặc VarHandle trên reference để thay thế toàn bộ state bằng CAS.
- Một cấu trúc dữ liệu chuyên dụng đã có hợp đồng đồng bộ phù hợp.

Không cố ghép nhiều CAS độc lập thành transaction nếu chưa có giao thức đồng bộ đầy đủ. Điều đó thường tạo race condition khó kiểm chứng.

## 9. Reference comparison, ABA và retry

Với biến reference, các thao tác compare-and-set so sánh reference identity, không gọi `equals()`. Hai object có nội dung bằng nhau nhưng là hai instance khác nhau vẫn không được coi là cùng expected reference.

CAS cũng không tự phát hiện ABA: giá trị có thể đổi từ A sang B rồi trở lại A; phép so sánh cuối cùng vẫn thấy A và có thể thành công. Nếu lịch sử thay đổi có ý nghĩa, hãy đưa version/stamp vào trạng thái hoặc chọn cấu trúc đồng bộ có hỗ trợ versioning.

Vòng lặp retry phải có điều kiện dừng và phải tính toán lại từ giá trị quan sát mới nhất. Khi contention cao, một thread có thể phải retry nhiều lần; không được giả định CAS loop luôn hoàn tất trong số bước cố định.

## 10. Kiểu dữ liệu và lỗi runtime thường gặp

VarHandle là API signature-polymorphic. Kiểu đối số và kiểu kết quả tại call site phải khớp với access mode type của handle. Với primitive, thường cần ép kiểu rõ ràng khi lấy kết quả, ví dụ `(int) handle.getVolatile(receiver)`.

Các lỗi thường gặp gồm:

- Tìm sai tên hoặc kiểu field: `NoSuchFieldException`.
- Lookup không có quyền truy cập: `IllegalAccessException`.
- Kiểu đối số hoặc coordinate tại call site không khớp: có thể gây `WrongMethodTypeException` hoặc `ClassCastException`.
- Gọi access mode không được hỗ trợ: `UnsupportedOperationException`.
- Truyền receiver không thuộc class mà handle yêu cầu hoặc index ngoài phạm vi: thao tác thất bại theo hợp đồng kiểu/array tương ứng.

Có thể dùng `varType()`, `coordinateTypes()` và `accessModeType(mode)` để kiểm tra kiểu của handle khi xây dựng framework hoặc code tổng quát. Trong code ứng dụng thông thường, giữ kiểu handle cụ thể và gọi trực tiếp thường dễ đọc hơn.

## 11. Hiệu năng và khả năng lock-free

`VarHandle` được thiết kế để cung cấp truy cập có kiểu và các thao tác nguyên tử hiệu quả, nhưng tên API không phải cam kết rằng mọi access mode đều lock-free trên mọi kiến trúc hoặc runtime. Hiệu năng còn phụ thuộc JVM, CPU, mức contention, cache coherence và cách thuật toán được viết.

Không nên chọn VarHandle chỉ dựa trên giả định rằng nó luôn nhanh hơn `AtomicInteger`. Hãy benchmark bằng workload đại diện, nhiều thread, kích thước dữ liệu và phần cứng mục tiêu. Đo throughput, latency, allocation và mức contention; đồng thời giữ một phiên bản code đơn giản để so sánh.

## 12. Quy trình lựa chọn

1. Xác định invariant và phạm vi trạng thái cần cập nhật nguyên tử.
2. Nếu chỉ có một biến độc lập, thử `AtomicInteger`, `AtomicLong` hoặc `AtomicReference` trước.
3. Nếu cần truy cập field/array hiện có, xem xét `VarHandle` và xác định coordinate types.
4. Tạo handle bằng lookup hợp lệ; kiểm tra quyền truy cập và module boundary.
5. Chọn access mode theo yêu cầu atomicity, visibility và ordering; không dùng mode yếu hơn nếu chưa chứng minh được tính đúng.
6. Nếu invariant có nhiều field, dùng lock hoặc CAS trên một state object thay vì nhiều CAS rời rạc.
7. Xử lý ABA, retry, contention và kiểu call site.
8. Kiểm thử đa luồng và benchmark trước khi quyết định dựa trên hiệu năng.

`VarHandle` phù hợp khi cần kiểm soát truy cập nguyên tử trực tiếp trên field hoặc array hiện có, hoặc cần memory ordering mà atomic holder đơn giản không biểu đạt thuận tiện. Với một giá trị độc lập, lớp atomic chuyên biệt vẫn thường là lựa chọn rõ ràng hơn; với invariant nhiều biến, hãy dùng cơ chế đồng bộ bảo vệ toàn bộ trạng thái.