# CAS mạnh, CAS yếu và thất bại giả trong Java

## Mục tiêu

Compare-and-set (CAS) là thao tác nguyên tử có điều kiện: chỉ cập nhật một biến khi giá trị hiện tại vẫn bằng giá trị mong đợi. Java cung cấp CAS mạnh và CAS yếu qua các lớp atomic và `VarHandle`.

Khác biệt quan trọng nhất:

- **CAS mạnh (strong CAS)** không thất bại giả. Nếu giá trị tại thời điểm thao tác bằng giá trị mong đợi, thao tác cập nhật thành công.
- **CAS yếu (weak CAS)** có thể trả về `false` ngay cả khi giá trị hiện tại vẫn bằng giá trị mong đợi. Đây gọi là *spurious failure* (thất bại giả).
- Cả hai đều thực hiện phép so sánh và cập nhật nguyên tử khi thành công. Khác biệt về độ mạnh không đồng nghĩa với khác biệt về tính nguyên tử.
- CAS yếu thường được dùng trong vòng lặp thử lại. Không nên diễn giải một lần trả về `false` của weak CAS như bằng chứng chắc chắn rằng giá trị đã thay đổi.

Với Java 9, `VarHandle` cung cấp các access mode CAS và các biến thể memory ordering. Các lớp như `AtomicInteger`, `AtomicLong` và `AtomicReference` cũng có các phương thức weak CAS với tên nêu rõ thứ tự bộ nhớ.

## 1. CAS hoạt động như thế nào?

Một thao tác CAS nhận ba thành phần:

1. Biến cần cập nhật.
2. Giá trị mong đợi (`expected`).
3. Giá trị mới (`newValue`).

Về mặt khái niệm:

~~~text
nếu current == expected:
    current = newValue
    trả về true
ngược lại:
    giữ nguyên current
    trả về false
~~~

Toàn bộ phép so sánh và cập nhật được thực hiện như một thao tác nguyên tử. Hai thread không thể cùng thành công trên cùng một giá trị cũ nếu thao tác của chúng cạnh tranh để thay thế giá trị đó.

Ví dụ với `AtomicInteger`:

~~~java
AtomicInteger counter = new AtomicInteger(10);

boolean changed = counter.compareAndSet(10, 11);
System.out.println(changed);
System.out.println(counter.get());
~~~

Kết quả:

~~~text
true
11
~~~

Nếu một thread khác đã thay đổi giá trị trước khi CAS diễn ra, `compareAndSet(10, 11)` trả về `false` và không ghi đè giá trị mới của thread kia.

CAS không phải là một phép gán thông thường. Nó kết hợp kiểm tra điều kiện và cập nhật tại cùng một điểm nguyên tử, nhờ đó tránh kiểu lỗi đọc giá trị cũ rồi ghi đè thay đổi của thread khác.

## 2. CAS mạnh và CAS yếu khác nhau ở đâu?

| Đặc điểm | Strong CAS | Weak CAS |
|---|---|---|
| Cập nhật nguyên tử khi thành công | Có | Có |
| Chỉ cập nhật nếu giá trị khớp expected | Có | Có |
| Có thể thất bại giả khi giá trị vẫn khớp | Không | Có |
| Kết quả false | Giá trị tại điểm nguyên tử không khớp expected | Không khớp expected hoặc thất bại giả |
| Cách dùng điển hình | Một lần thử cần kết quả thành công/thất bại rõ ràng | Vòng lặp thử lại |
| Bảo đảm nhanh hơn | Không có | Không có |

Với strong CAS, kết quả `false` cho biết điều kiện so sánh không đúng tại thời điểm thao tác. Với weak CAS, `false` có hai khả năng: giá trị không khớp hoặc thao tác thất bại giả.

Weak CAS được thiết kế để một số nền tảng có thể triển khai thao tác này hiệu quả hơn trong vòng lặp. Tuy nhiên, không có bảo đảm rằng weak CAS luôn nhanh hơn strong CAS trên mọi CPU, JVM hoặc workload. Hãy đo hiệu năng bằng benchmark đại diện trước khi lựa chọn vì lý do tốc độ.

## 3. Spurious failure là gì?

Spurious failure là trường hợp weak CAS trả về `false` dù giá trị được đọc tại điểm so sánh vẫn bằng `expected`. Đây là hành vi được phép theo hợp đồng API, thường liên quan đến cách phần cứng hoặc runtime thực hiện thao tác nguyên tử dưới cạnh tranh bộ nhớ.

Ví dụ về tình huống có thể xảy ra:

~~~text
Giá trị hiện tại: 10
expected:         10
newValue:         11

weak CAS:
    không cập nhật
    trả về false

Đọc lại:
    giá trị hiện tại vẫn là 10

Thử lại weak CAS:
    cập nhật 10 thành 11
    trả về true
~~~

Không nên viết mã giả định rằng weak CAS chỉ trả về false khi thread khác đã cập nhật biến. Nếu không thử lại hoặc kiểm tra lại trạng thái, chương trình có thể bỏ qua một cập nhật hợp lệ.

Spurious failure không phải là mất tính nguyên tử. Mỗi lần gọi vẫn có kết quả nguyên tử: hoặc giá trị được cập nhật theo điều kiện, hoặc không được cập nhật. Điều yếu hơn nằm ở bảo đảm thành công khi điều kiện đang đúng.

## 4. Strong CAS với VarHandle

`VarHandle.compareAndSet(...)` là strong CAS. Nó cập nhật biến nếu giá trị hiện tại bằng expected và trả về boolean:

~~~java
boolean changed = VALUE.compareAndSet(
        receiver,
        expected,
        newValue
);
~~~

Nếu trả về `true`, cập nhật đã diễn ra. Nếu trả về `false`, giá trị tại thời điểm thao tác không khớp expected; strong CAS không được phép trả về false chỉ vì thất bại giả.

`VarHandle.compareAndSet` có memory effects kiểu volatile: thao tác đọc giá trị để so sánh và ghi giá trị mới tuân theo thứ tự bộ nhớ volatile. Vì vậy, đây là lựa chọn tổng quát khi cần một cập nhật CAS mạnh cùng ordering volatile.

`VarHandle` có thể tham chiếu field instance, field static hoặc phần tử array. Kiểu tọa độ và kiểu giá trị phải khớp với VarHandle được tạo; nếu không, lời gọi có thể phát sinh lỗi kiểu lúc chạy.

## 5. Weak CAS với VarHandle

Java 9 cung cấp các access mode weak CAS trên `VarHandle`:

| Phương thức | Memory effects khi đọc expected | Memory effects khi ghi newValue |
|---|---|---|
| `weakCompareAndSetPlain` | Plain | Plain |
| `weakCompareAndSetAcquire` | Acquire | Plain |
| `weakCompareAndSetRelease` | Plain | Release |
| `weakCompareAndSet` | Volatile | Volatile |

Tất cả các phương thức trên đều có thể thất bại giả. Suffix mô tả thứ tự bộ nhớ, không biến weak CAS thành strong CAS.

Ý nghĩa từng mode:

- **Plain:** không tạo ordering liên luồng ngoài các bảo đảm plain của biến.
- **Acquire:** thao tác đọc có acquire semantics; các thao tác sau nó không được sắp xếp lại về trước lần đọc này.
- **Release:** thao tác ghi có release semantics; các thao tác trước nó không được sắp xếp lại về sau lần ghi này.
- **Volatile:** có ordering volatile cho cả phần đọc và ghi.

Chọn memory mode theo giao thức công bố và đọc dữ liệu giữa các thread. Không giảm ordering từ volatile xuống plain chỉ vì muốn dùng weak CAS; việc đó có thể làm mất quan hệ happens-before mà chương trình đang cần.

Một lưu ý: access mode của VarHandle quyết định memory effects cho lần truy cập đó, kể cả khi field được khai báo `volatile`. Khi trộn plain, opaque, acquire/release và volatile trên cùng một biến, phải thiết kế cẩn thận theo Java Memory Model.

## 6. Các phương thức CAS trong AtomicInteger và AtomicReference

Các lớp atomic cung cấp API dễ dùng hơn khi làm việc với một giá trị cụ thể:

- `compareAndSet(expected, newValue)`: strong CAS với volatile memory effects.
- `weakCompareAndSetPlain(expected, newValue)`: weak CAS với plain effects.
- `weakCompareAndSetAcquire(expected, newValue)`: weak CAS với acquire read và plain write.
- `weakCompareAndSetRelease(expected, newValue)`: weak CAS với plain read và release write.
- `weakCompareAndSetVolatile(expected, newValue)`: weak CAS với volatile effects.

Các phương thức weak có tên rõ ràng theo memory ordering giúp người đọc nhận biết hợp đồng bộ nhớ ngay tại chỗ gọi. Những overload này có từ Java 9.

Ví dụ với `AtomicInteger`:

~~~java
AtomicInteger value = new AtomicInteger(0);

int expected = value.get();
while (!value.weakCompareAndSetVolatile(expected, expected + 1)) {
    expected = value.get();
}
~~~

Trong ví dụ này, mỗi lần thất bại đều đọc lại giá trị rồi tính expected và giá trị mới cho lần thử tiếp theo. Nếu chỉ cần cập nhật một lần và muốn kết quả false có nghĩa là điều kiện không khớp, dùng `compareAndSet`.

## 7. Dùng weak CAS trong vòng lặp thử lại

Mẫu phổ biến nhất là đọc giá trị hiện tại, tính giá trị mới rồi thử cập nhật. Nếu weak CAS trả về false, đọc lại và tính lại:

~~~java
int increment(AtomicInteger counter) {
    int current;
    int next;

    do {
        current = counter.get();
        next = current + 1;
    } while (!counter.weakCompareAndSetVolatile(current, next));

    return next;
}
~~~

Vòng lặp có ba bước:

1. Đọc giá trị hiện tại.
2. Tính kết quả dựa trên giá trị vừa đọc.
3. Thử weak CAS; nếu thất bại, lặp lại từ bước đọc.

Không giữ nguyên `expected` và `newValue` cũ vô thời hạn. Nếu lần thử thất bại do cạnh tranh, giá trị mới có thể khác; lần thử tiếp theo phải tính lại dựa trên giá trị hiện tại.

Có thể thêm `Thread.onSpinWait()` trong vòng lặp retry khi workload phù hợp:

~~~java
while (!counter.weakCompareAndSetVolatile(current, next)) {
    Thread.onSpinWait();
    current = counter.get();
    next = current + 1;
}
~~~

`Thread.onSpinWait()` là hint cho runtime/CPU trong vòng lặp chờ ngắn, không phải khóa, không bảo đảm thread khác chạy ngay và không thay thế cơ chế đồng bộ. Nếu phải retry quá lâu, cần đánh giá lại thuật toán, contention và khả năng dùng lock hoặc cấu trúc concurrent khác.

## 8. Strong CAS cũng thường được dùng trong retry loop

Strong CAS không thất bại giả, nhưng vẫn có thể trả về false do thread khác thay đổi giá trị giữa lần đọc và lần cập nhật. Vì vậy, strong CAS cũng thường xuất hiện trong vòng lặp:

~~~java
int increment(AtomicInteger counter) {
    int current;
    int next;

    do {
        current = counter.get();
        next = current + 1;
    } while (!counter.compareAndSet(current, next));

    return next;
}
~~~

Khác biệt nằm ở ý nghĩa của mỗi lần thất bại:

- Strong CAS thất bại vì giá trị không khớp tại điểm nguyên tử.
- Weak CAS thất bại vì giá trị không khớp hoặc thao tác thất bại giả.

Nếu cả hai đều nằm trong retry loop đúng cách, chúng có thể thực hiện cùng một cập nhật logic. Việc chọn weak hay strong phụ thuộc hợp đồng cần thiết, memory ordering và hiệu năng thực tế trên nền tảng triển khai.

## 9. compareAndExchange và witness value

Java 9 bổ sung `compareAndExchange` trên VarHandle và các lớp atomic tương ứng. Khác với `compareAndSet` trả về boolean, compare-and-exchange trả về giá trị quan sát được tại điểm nguyên tử (witness value).

~~~java
int witness = (int) VALUE.compareAndExchange(
        receiver,
        expected,
        newValue
);

if (witness == expected) {
    // Cập nhật thành công.
} else {
    // witness là giá trị quan sát được; dùng nó để tính lần thử tiếp.
}
~~~

Đây là strong operation: không có spurious failure. Nếu witness bằng expected, cập nhật đã thành công; nếu khác, witness cung cấp giá trị mà thao tác quan sát được để caller có thể quyết định bước tiếp theo.

Các biến thể `compareAndExchangeAcquire` và `compareAndExchangeRelease` cho phép chọn ordering phù hợp. Chọn chúng theo yêu cầu đồng bộ dữ liệu, không chỉ theo tên gọi hoặc giả định rằng ordering yếu hơn luôn nhanh hơn.

## 10. ABA problem không phải là spurious failure

CAS so sánh giá trị hiện tại với expected. Nếu giá trị thay đổi từ A sang B rồi quay lại A trước khi CAS chạy, phép so sánh có thể thấy A và thành công.

~~~text
Thread 1 đọc A
Thread 2 đổi A -> B
Thread 2 đổi B -> A
Thread 1 CAS(expected=A, new=C) thành công
~~~

Đây là ABA problem. CAS mạnh và CAS yếu đều có thể gặp vấn đề này; nó khác với spurious failure:

- **Spurious failure:** weak CAS trả false dù giá trị vẫn khớp expected.
- **ABA:** giá trị đã thay đổi trong khoảng thời gian giữa hai lần quan sát nhưng quay lại cùng giá trị expected trước CAS.

Nếu thuật toán cần phát hiện lịch sử thay đổi, có thể kết hợp giá trị với version/stamp, ví dụ `AtomicStampedReference`, hoặc dùng một thiết kế dữ liệu có version riêng. Việc thêm stamp cần được quản lý nhất quán và phải xem xét cả khả năng version quay vòng.

## 11. Ví dụ hoàn chỉnh có thể chạy

Tệp `CasStrengthDemo.java`:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class CasStrengthDemo {
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    static final class Counter {
        int value;
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        boolean strongSuccess = VALUE.compareAndSet(counter, 0, 1);
        boolean strongMismatch = VALUE.compareAndSet(counter, 0, 2);

        int expected;
        do {
            expected = (int) VALUE.getVolatile(counter);
        } while (!VALUE.weakCompareAndSet(
                counter, expected, expected + 1));

        int weakValue = (int) VALUE.getVolatile(counter);
        int witness = (int) VALUE.compareAndExchange(counter, 2, 7);
        int finalValue = (int) VALUE.getVolatile(counter);

        System.out.println("strong CAS success: " + strongSuccess);
        System.out.println("strong CAS mismatch: " + strongMismatch);
        System.out.println("weak CAS final value: " + weakValue);
        System.out.println("compareAndExchange witness: " + witness);
        System.out.println("value after exchange: " + finalValue);
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac --release 9 -Xlint:all CasStrengthDemo.java
java CasStrengthDemo
~~~

Kết quả chuẩn:

~~~text
strong CAS success: true
strong CAS mismatch: false
weak CAS final value: 2
compareAndExchange witness: 2
value after exchange: 7
~~~

Ví dụ cho thấy strong CAS cập nhật 0 thành 1; lần strong CAS tiếp theo dùng expected cũ nên thất bại. Weak CAS được đặt trong vòng lặp và cập nhật 1 thành 2. Cuối cùng compareAndExchange quan sát witness 2, cập nhật thành 7 và trả về witness đó.

Ví dụ chạy đơn luồng nên không nhất thiết quan sát được spurious failure. Việc không thấy thất bại giả trong một lần chạy không làm mất khả năng weak CAS thất bại giả theo hợp đồng API.

## 12. Lỗi thường gặp và checklist

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng weak CAS một lần rồi coi false là giá trị đã đổi | false có thể là spurious failure | Đọc lại và retry nếu thuật toán yêu cầu cập nhật |
| Cho rằng strong CAS luôn thành công nếu vừa đọc thấy expected | Thread khác có thể thay đổi giá trị trước thao tác CAS | Kiểm tra boolean và retry theo giá trị mới |
| Retry nhưng giữ expected cũ | Giá trị hiện tại có thể đã thay đổi | Đọc lại và tính lại newValue trong mỗi vòng |
| Nhầm spurious failure với ABA | Một bên là false không do mismatch, một bên là giá trị đổi rồi quay lại | Phân tích lịch sử cập nhật và dùng stamp/version khi cần |
| Chọn weak CAS vì nghĩ luôn nhanh hơn | Hiệu năng phụ thuộc CPU, JVM và contention | Benchmark trên workload thực tế |
| Dùng plain mode khi cần công bố dữ liệu cho thread khác | Plain không tạo ordering liên luồng cần thiết | Chọn acquire/release hoặc volatile theo giao thức |
| Nghĩ suffix Acquire/Release làm weak CAS thành strong | Suffix chỉ mô tả memory effects | Vẫn phải xử lý spurious failure |
| Dùng một lần weak CAS cho quyết định không thể thử lại | Kết quả false không phân biệt mismatch và spurious failure | Dùng strong CAS nếu cần kết quả mismatch rõ ràng |
| Giả định CAS tự giải quyết mọi vấn đề đồng thời | CAS chỉ bảo vệ một cập nhật có điều kiện | Thiết kế thêm invariant, ordering, retry và xử lý ABA |

Trước khi chọn CAS, hãy xác định:

- Có cần một lần thử với kết quả mismatch rõ ràng hay không.
- Nếu dùng weak CAS, có thể retry an toàn hay không.
- Giá trị mới có cần tính lại sau mỗi lần thất bại hay không.
- Memory ordering cần plain, acquire, release hay volatile.
- Thuật toán có nhạy với ABA hay không.
- Contention có thể gây vòng lặp retry dài hay không.
- Có cần benchmark so sánh strong/weak trên nền tảng chạy thực tế hay không.

Strong CAS phù hợp khi một lần thử cần ngữ nghĩa thất bại rõ ràng. Weak CAS phù hợp với vòng lặp đã xử lý cả mismatch lẫn spurious failure. Dù chọn loại nào, phải giữ đúng memory ordering và invariant của thuật toán; độ mạnh CAS không thay thế thiết kế đồng bộ tổng thể.