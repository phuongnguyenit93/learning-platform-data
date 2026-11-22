# `compareAndSet()`, `compareAndExchange()` và giá trị quan sát được

`VarHandle` cung cấp các access mode nguyên tử để đọc, ghi và cập nhật biến mà không cần viết một lớp atomic riêng cho từng trường. Hai thao tác thường gặp là `compareAndSet(expected, newValue)` và `compareAndExchange(expected, newValue)`. Cả hai đều thực hiện phép so sánh và cập nhật nguyên tử: chỉ ghi giá trị mới khi giá trị hiện tại bằng giá trị kỳ vọng.

Điểm khác biệt quan trọng nằm ở kết quả trả về. `compareAndSet()` trả về `boolean`, cho biết phép cập nhật có thành công hay không. `compareAndExchange()` trả về *witness value* — giá trị mà thao tác nguyên tử quan sát được tại đúng thời điểm so sánh. Giá trị này cho biết vì sao phép đổi không thành công và thường giúp viết vòng lặp cập nhật lock-free rõ ràng hơn.

Các API này có từ Java 9 và vẫn là API hiện hành. Bài viết tập trung vào semantics của hai thao tác, cách đọc witness value, memory ordering, các lỗi thường gặp và cách chọn thao tác phù hợp.

## 1. VarHandle là gì?

`VarHandle` là một tham chiếu có kiểu mạnh đến một biến hoặc một nhóm biến có cùng cấu trúc truy cập. Nó có thể trỏ đến:

- Trường instance của một class.
- Trường `static` của một class.
- Phần tử trong mảng.
- Một số cấu trúc dữ liệu được truy cập thông qua tọa độ (coordinate) phù hợp.

Mỗi `VarHandle` có kiểu biến (`varType`) và danh sách kiểu tọa độ (`coordinateTypes`). Ví dụ, handle tới một trường instance cần đối tượng chứa trường làm tọa độ; handle tới trường static không cần tọa độ đối tượng.

Khác với gọi getter/setter thông thường, `VarHandle` cho phép chọn access mode cho từng thao tác: plain, opaque, acquire, release, volatile hoặc atomic update. Các access mode xác định tính nguyên tử và quy tắc sắp xếp bộ nhớ của thao tác đó.

Ví dụ tạo handle tới trường static kiểu `int`:

```java
VarHandle VALUE = MethodHandles.lookup().findStaticVarHandle(
        Counter.class, "value", int.class
);
```

Việc tìm handle chịu kiểm tra quyền truy cập của `MethodHandles.Lookup`. Nếu trường không thể truy cập theo lookup hiện tại, thao tác tìm handle có thể thất bại bằng `IllegalAccessException`; nếu tên hoặc kiểu trường không đúng, có thể nhận `NoSuchFieldException`.

## 2. Cơ chế compare-and-set

`compareAndSet(expectedValue, newValue)` thực hiện một thao tác nguyên tử:

1. Đọc giá trị hiện tại của biến theo memory semantics của volatile read.
2. So sánh giá trị đó với `expectedValue`.
3. Nếu bằng nhau, ghi `newValue` theo volatile write và trả về `true`.
4. Nếu khác nhau, không thay đổi biến và trả về `false`.

Ví dụ:

```java
boolean updated = VALUE.compareAndSet(10, 20);
```

Nếu giá trị tại thời điểm phép toán là `10`, biến được cập nhật thành `20` và kết quả là `true`. Nếu giá trị là `15`, biến vẫn là `15` và kết quả là `false`.

`compareAndSet()` chỉ trả lời câu hỏi “có cập nhật được không?”. Khi trả về `false`, nó không cung cấp trực tiếp giá trị đã làm phép so sánh thất bại. Nếu sau đó gọi `getVolatile()` để đọc lại, giá trị đọc được có thể đã thay đổi bởi thread khác sau thao tác compare-and-set.

Đây là một thao tác strong compare-and-set: nếu giá trị quan sát tại thời điểm nguyên tử khác `expectedValue`, kết quả là `false`; nó không được phép thất bại giả tạo khi hai giá trị thực sự bằng nhau. Điều này khác với các access mode `weakCompareAndSet...`, vốn có thể thất bại giả tạo và thường được dùng trong vòng lặp retry được thiết kế phù hợp.

## 3. Cơ chế compare-and-exchange

`compareAndExchange(expectedValue, newValue)` cũng so sánh và cập nhật nguyên tử, nhưng trả về giá trị đã quan sát thay vì `boolean`.

- Nếu witness value bằng `expectedValue`, biến được cập nhật thành `newValue`.
- Nếu witness value khác `expectedValue`, biến giữ nguyên giá trị tại thời điểm thao tác.
- Trong cả hai trường hợp, phương thức trả về witness value đã được quan sát nguyên tử.

Ví dụ:

```java
int witness = (int) VALUE.compareAndExchange(10, 20);
```

Nếu `witness == 10`, phép đổi đã thành công và giá trị mới được ghi là `20`. Nếu `witness == 15`, phép đổi không thành công; biến không bị thay đổi bởi thao tác này và `witness` cho biết giá trị thực tế đã khiến phép so sánh thất bại.

Điểm quan trọng là witness không phải một lần đọc riêng sau khi thất bại. Nó chính là giá trị được quan sát trong cùng thao tác nguyên tử. Vì vậy, nó mô tả chính xác trạng thái tại thời điểm compare-and-exchange thực hiện, dù một thread khác có thể cập nhật biến ngay sau đó.

## 4. So sánh trực tiếp hai phương thức

| Tiêu chí | `compareAndSet(expected, update)` | `compareAndExchange(expected, update)` |
| --- | --- | --- |
| Điều kiện cập nhật | Giá trị hiện tại bằng expected | Giá trị hiện tại bằng expected |
| Cập nhật | Ghi update nếu khớp | Ghi update nếu khớp |
| Giá trị trả về | `boolean` | Witness value có kiểu của biến |
| Khi thành công | `true` | Witness bằng expected |
| Khi thất bại | `false` | Witness khác expected |
| Có cung cấp giá trị quan sát được? | Không | Có |
| Memory semantics mặc định | Volatile read + volatile write | Volatile read + volatile write |

Nếu chỉ cần nhánh thành công/thất bại, `compareAndSet()` ngắn gọn và thể hiện đúng ý định. Nếu khi thất bại cần biết giá trị thực tế để tính giá trị cập nhật tiếp theo, `compareAndExchange()` thường tránh được một lần đọc riêng có thể đã lỗi thời.

Không được suy ra rằng witness value luôn là giá trị hiện tại khi phương thức trả về. Nó là giá trị được quan sát tại thời điểm nguyên tử; biến có thể thay đổi ngay sau thời điểm đó.

## 5. Ví dụ Java hoàn chỉnh

Ví dụ sau truy cập một trường static kiểu `int`. Trường không cần khai báo `volatile` để các access mode `compareAndSet`, `compareAndExchange` và `getVolatile` có memory semantics tương ứng với tên access mode. `VarHandle` xác định semantics cho từng lần truy cập.

Tạo tệp `CompareAndExchangeDemo.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class CompareAndExchangeDemo {
    private static int value = 10;
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findStaticVarHandle(
                    CompareAndExchangeDemo.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static int readValue() {
        return (int) VALUE.getVolatile();
    }

    public static void main(String[] args) {
        boolean casSuccess = VALUE.compareAndSet(10, 20);
        System.out.println("CAS success: " + casSuccess);
        System.out.println("Value after CAS: " + readValue());

        boolean casFailure = VALUE.compareAndSet(10, 30);
        System.out.println("CAS failure: " + casFailure);
        System.out.println("Value after failed CAS: " + readValue());

        int exchangeWitness = (int) VALUE.compareAndExchange(20, 40);
        System.out.println("Exchange witness (success): " + exchangeWitness);
        System.out.println("Value after exchange: " + readValue());

        int mismatchWitness = (int) VALUE.compareAndExchange(20, 50);
        System.out.println("Exchange witness (mismatch): " + mismatchWitness);
        System.out.println("Value after mismatch: " + readValue());
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all CompareAndExchangeDemo.java
java CompareAndExchangeDemo
```

Kết quả stdout:

```text
CAS success: true
Value after CAS: 20
CAS failure: false
Value after failed CAS: 20
Exchange witness (success): 20
Value after exchange: 40
Exchange witness (mismatch): 40
Value after mismatch: 40
```

Lần `compareAndSet(10, 20)` đầu tiên thành công. Lần gọi tiếp theo vẫn kỳ vọng `10`, nhưng giá trị đã là `20`, nên kết quả là `false` và biến không đổi. `compareAndExchange(20, 40)` trả witness `20` và cập nhật thành `40`. Lần cuối kỳ vọng `20` nhưng quan sát được `40`, nên trả witness `40` và không ghi `50`.

## 6. Vì sao witness value hữu ích trong vòng lặp cập nhật?

Giả sử muốn tăng một biến nguyên tử lên một đơn vị. Với `compareAndSet()`, khi cập nhật thất bại, chương trình thường phải đọc lại giá trị rồi thử lại:

```java
for (;;) {
    int current = (int) VALUE.getVolatile();
    int next = current + 1;
    if (VALUE.compareAndSet(current, next)) {
        break;
    }
}
```

Nếu một thread khác thay đổi biến sau lần đọc `current`, CAS thất bại. Vòng lặp quay lại đọc lại rồi tính `next`.

Với `compareAndExchange()`, witness value có thể trở thành đầu vào cho lần thử tiếp theo:

```java
int current = (int) VALUE.getVolatile();
for (;;) {
    int next = current + 1;
    int witness = (int) VALUE.compareAndExchange(current, next);
    if (witness == current) {
        break;
    }
    current = witness;
}
```

Nếu witness bằng `current`, phép cập nhật thành công. Nếu khác, witness chính là giá trị mà thao tác vừa quan sát; vòng lặp dùng nó làm giá trị đầu vào cho lần thử tiếp theo mà không cần một lần đọc riêng ngay sau thất bại.

Đây là mẫu retry phổ biến cho thao tác compare-and-exchange. Trong ứng dụng thực tế, cần kiểm tra overflow, điều kiện dừng, contention và khả năng starvation. Vòng lặp có thể thử nhiều lần khi nhiều thread cùng cập nhật; không nên giả định mỗi thread sẽ hoàn tất trong một số lần cố định.

## 7. Giá trị quan sát được và race condition

Giả sử biến đang là `5`. Thread A gọi `compareAndExchange(3, 9)` và nhận witness `5`. Kết quả cho biết tại điểm nguyên tử, biến không bằng `3`, nên thao tác không ghi `9`.

Ngay sau đó, thread B có thể cập nhật biến thành `7`. Khi thread A đọc lại biến, nó có thể nhận `7`, không phải `5`. Điều này không làm witness sai: witness ghi lại trạng thái đúng tại thời điểm thao tác của A.

Với `compareAndSet()`, nếu nhận `false` rồi gọi một getter, giá trị getter trả về có thể đã được một thread khác cập nhật. Vì thế, không được diễn giải getter sau thất bại như giá trị chính xác đã làm CAS thất bại.

Không dùng witness để giả định biến vẫn giữ nguyên sau khi phương thức trả về. Nếu logic tiếp theo cần bảo đảm một trạng thái khác không thay đổi, cần thực hiện thêm thao tác đồng bộ/kiểm tra phù hợp thay vì dựa vào một giá trị đã quan sát trước đó.

## 8. Memory semantics của các access mode

`compareAndSet()` và `compareAndExchange()` mặc định có memory semantics của volatile read và volatile write. Điều này cung cấp atomicity cho thao tác compare-and-update và các quy tắc visibility/ordering tương ứng của volatile access.

`VarHandle` còn có các biến thể memory ordering cho compare-and-exchange:

| Access mode | Phần đọc | Phần ghi |
| --- | --- | --- |
| `compareAndExchange()` | Volatile | Volatile |
| `compareAndExchangeAcquire()` | Acquire | Plain |
| `compareAndExchangeRelease()` | Plain | Release |

Acquire đảm bảo các thao tác đọc/ghi sau access không bị sắp xếp trước access đó. Release đảm bảo các thao tác đọc/ghi trước access không bị sắp xếp sau access đó. Các biến thể acquire/release có thể hữu ích khi thuật toán chỉ cần thứ tự bộ nhớ yếu hơn volatile đầy đủ.

Chỉ dùng biến thể yếu hơn khi đã xác định rõ quan hệ happens-before và yêu cầu visibility của thuật toán. Không thay `compareAndExchange()` bằng acquire/release chỉ để tối ưu theo cảm tính; sai memory ordering có thể làm thread khác quan sát dữ liệu không đúng thứ tự mong muốn.

Access mode của `VarHandle` quyết định semantics của lần truy cập. Không được giả định rằng khai báo trường là `volatile` sẽ làm cho mọi lần truy cập qua VarHandle tự động có cùng semantics; hãy chọn đúng access mode ở từng nơi.

## 9. Primitive, reference và phép so sánh

Với biến primitive, expected value được so sánh theo giá trị của kiểu primitive tương ứng. Với biến reference, điều kiện khớp dùng reference identity (`==`), không gọi `equals()`.

Ví dụ nếu hai object khác nhau nhưng `equals()` trả về `true`, `compareAndSet(expected, update)` vẫn thất bại nếu reference đang lưu không chính là object `expected`. Đây là hành vi cần thiết cho thao tác nguyên tử trên một biến tham chiếu.

Kiểu đối số tại call site phải tương thích chính xác với access mode type của VarHandle. Các phương thức VarHandle là signature-polymorphic; compiler dùng kiểu biểu thức gọi để tạo descriptor. Sai kiểu có thể dẫn đến `WrongMethodTypeException` hoặc `ClassCastException` khi chạy.

Access mode không được hỗ trợ cho loại biến/handle cụ thể có thể ném `UnsupportedOperationException`. Hãy dùng đúng factory method và kiểm tra hợp đồng của loại biến mà handle truy cập.

## 10. ABA problem

Compare-and-set và compare-and-exchange chỉ kiểm tra giá trị hiện tại có bằng expected hay không. Chúng không tự phát hiện lịch sử thay đổi giữa hai lần quan sát.

Ví dụ một thread đọc giá trị `A`; thread khác thay đổi `A` thành `B`, rồi lại đổi về `A`. Thread đầu gọi `compareAndSet(A, C)` và có thể thành công vì giá trị hiện tại lại là `A`. Nó không biết biến đã từng đi qua `B`.

Đây là ABA problem. Nếu việc thay đổi rồi quay lại cùng giá trị vẫn có ý nghĩa đối với thuật toán, hãy kết hợp version/stamp với dữ liệu, dùng một trạng thái có sequence number hoặc một cơ chế đồng bộ phù hợp. Với reference, có thể xem xét cấu trúc có version như `AtomicStampedReference` khi semantics của nó đáp ứng yêu cầu.

Không phải mọi thuật toán đều bị ABA ảnh hưởng. Nếu chỉ quan tâm giá trị hiện tại và việc quay lại `A` là chấp nhận được, CAS có thể vẫn phù hợp. Hãy xác định invariant của dữ liệu trước khi thêm versioning.

## 11. Chọn compareAndSet hay compareAndExchange?

**Chọn `compareAndSet()` khi:**

- Chỉ cần biết cập nhật có thành công hay không.
- Khi thất bại, thuật toán có thể đọc lại và tính toán từ đầu.
- Muốn code đơn giản, dễ đọc với một nhánh boolean.

**Chọn `compareAndExchange()` khi:**

- Cần biết giá trị đã được quan sát trong thao tác nguyên tử.
- Muốn dùng witness làm đầu vào cho lần retry tiếp theo.
- Cần phân biệt chính xác expected mismatch tại thời điểm thao tác mà không thực hiện một lần đọc rời rạc sau thất bại.

**Cả hai đều cần:**

- Xác định đúng kiểu biến và coordinate của VarHandle.
- Chọn memory ordering theo yêu cầu visibility/ordering của thuật toán.
- Xử lý contention, retry, overflow và ABA nếu các vấn đề đó liên quan.
- Không giả định thao tác là lock-free trên mọi nền tảng; API quy định tính nguyên tử và semantics, còn đặc tính hiệu năng phụ thuộc implementation/runtime/hardware.

## 12. Lỗi thường gặp

- **Nghĩ `compareAndSet()` trả về giá trị mới:** phương thức chỉ trả `boolean`; dùng getter nếu cần đọc trạng thái sau đó.
- **Nghĩ `compareAndExchange()` trả về giá trị mới:** nó trả witness value, tức giá trị quan sát trước khi cập nhật (hoặc giá trị mismatch).
- **Đọc lại sau CAS thất bại rồi coi đó là witness:** lần đọc riêng có thể thấy một thay đổi mới hơn; chỉ compare-and-exchange trả witness trong chính thao tác nguyên tử.
- **Coi witness là giá trị hiện tại vĩnh viễn:** thread khác có thể thay đổi biến ngay sau thao tác.
- **Dùng `equals()` cho reference CAS:** phép so sánh reference dùng identity `==`.
- **Nhầm strong và weak CAS:** các access mode `weakCompareAndSet...` có thể thất bại giả tạo; `compareAndSet()` là strong.
- **Bỏ qua memory ordering:** chọn access mode acquire/release/plain không đúng có thể làm hỏng visibility và ordering giữa các thread.
- **Quên ABA:** giá trị có thể thay đổi rồi quay lại expected mà CAS vẫn thành công.
- **Không kiểm tra kiểu call site:** sai descriptor hoặc kiểu tọa độ có thể gây lỗi runtime.

## 13. Checklist triển khai

1. Xác định biến cần cập nhật và tạo VarHandle bằng lookup/factory đúng loại.
2. Kiểm tra access mode có được hỗ trợ và kiểu tại call site khớp chính xác.
3. Dùng `compareAndSet()` nếu chỉ cần boolean; dùng `compareAndExchange()` nếu cần witness.
4. Nếu retry, dùng witness làm trạng thái đầu vào mới khi phù hợp và bảo đảm điều kiện dừng rõ ràng.
5. Chọn volatile/acquire/release theo yêu cầu Java Memory Model; ưu tiên semantics dễ chứng minh.
6. Xem xét ABA, overflow, contention và starvation theo invariant của dữ liệu.
7. Kiểm thử nhiều thread và đo hiệu năng trên runtime/hardware mục tiêu; không suy ra lock-free chỉ từ tên API.

`compareAndSet()` trả lời cập nhật có thành công hay không; `compareAndExchange()` còn cung cấp witness value được quan sát nguyên tử. Chọn phương thức theo thông tin thuật toán cần sau phép so sánh, đồng thời giữ đúng memory ordering và xử lý các race condition có thể xảy ra.

## Tài liệu tham khảo

- [Java 9 API: `VarHandle`](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/VarHandle.html)