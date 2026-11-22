# Định nghĩa trạng thái hợp lệ trước và sau khi phương thức thất bại

Một API Java không chỉ cần trả kết quả đúng khi **thành công**. Khi một lời gọi ném exception giữa chừng, đối tượng còn sử dụng được không? Field nào được phép đổi? Tài nguyên có được đóng không? Caller có thể thử lại không? Một thao tác đã ghi dữ liệu ra file, database hoặc dịch vụ bên ngoài có thực sự được hoàn tác không?

Chủ đề **“Định nghĩa trạng thái hợp lệ trước và sau khi phương thức thất bại”** là phần cốt lõi của thiết kế API có khả năng dự đoán. Nó kết hợp **invariant**, **precondition**, **postcondition**, **exceptional postcondition**, **mức bảo đảm an toàn khi có exception**, quản lý tài nguyên và kiểm thử đường lỗi.

Ví dụ lời gọi `wallet.withdraw(200)` từ ví chỉ có 100 đơn vị:

- Caller có vi phạm tiền điều kiện không? Nếu có, method ném loại exception nào?
- Sau khi ném, số dư còn 100 hay bị đổi thành giá trị âm?
- Nếu method đã gửi một yêu cầu thanh toán ra ngoài trước khi lỗi, nó có thể khẳng định giao dịch chưa xảy ra không?
- Nếu cần gọi lại, phải sửa input, sửa state, hay xác minh side effect trước?

**Hợp đồng tốt** nói rõ cả trạng thái **trước lời gọi**, trạng thái **sau thành công**, và trạng thái **sau thất bại**. Cú pháp `throws` hay việc có một khối `catch` **không tự đem lại** những bảo đảm đó.

Các ví dụ tập trung Java 17+, độc lập và có lệnh chạy/stdout khi được đánh dấu là chương trình đầy đủ. Những đoạn minh họa được ghi chú rõ, không phải tất cả đều có thể chạy một mình.

## 1. Ba lớp hợp đồng: trước, sau thành công, sau thất bại

Xét một phương thức thay đổi trạng thái:

```java
account.withdraw(amount);
```

Đây là **lời gọi minh họa**; biến và lớp cần được định nghĩa. Hợp đồng nên tách:

1. **Precondition (tiền điều kiện):** điều caller phải thỏa trước khi gọi. Ví dụ `amount > 0`.
2. **Normal postcondition (hậu điều kiện thành công):** nếu method trả bình thường, điều gì đúng? Ví dụ số dư giảm đúng bằng `amount`.
3. **Exceptional postcondition (hậu điều kiện khi thất bại):** nếu method ném exception, điều gì vẫn được bảo đảm? Ví dụ số dư không đổi với lỗi validation; hoặc object vẫn ở một trạng thái `FAILED` được công bố.

Bên cạnh đó, **invariant** là điều phải giữ ở mọi trạng thái ổn định và quan sát được của đối tượng. Ví dụ `balance >= 0` hay `start <= end`.

Một bản mô tả tối thiểu:

| Khía cạnh | Hợp đồng của `withdraw` |
| --- | --- |
| Trạng thái trước hợp lệ | `balance >= 0` |
| Đối số hợp lệ | `amount > 0` |
| Thành công | `newBalance = oldBalance - amount` |
| Đối số không hợp lệ | Ném `IllegalArgumentException`; `balance` không đổi |
| Không đủ tiền | Ném `IllegalStateException` hoặc domain failure theo thiết kế; `balance` không đổi |
| Tài nguyên/phụ thuộc lỗi | Quy tắc riêng, không được suy là đã rollback giao dịch bên ngoài |

Vấn đề quan trọng là **hậu điều kiện thất bại phải cụ thể**, không thể chỉ viết “có lỗi thì ném exception”.

## 2. Invariant là gì và cần giữ ở thời điểm nào?

**Invariant** là điều kiện về trạng thái của đối tượng cần luôn đúng tại các điểm mà hệ thống công bố trạng thái là hợp lệ.

Ví dụ một khoảng số:

```text
lower <= upper
```

Một đối tượng `Range` có thể dùng hai field `lower` và `upper`. Nếu method cập nhật một field trước rồi sau đó ném exception trước khi cập nhật field còn lại, invariant có thể bị phá.

**Phân biệt trạng thái trung gian và trạng thái quan sát được:**

- Trong một thao tác nội bộ, code có thể tính toán nhiều giá trị tạm.
- Trước khi phương thức trả hoặc ném, trạng thái công bố ra ngoài phải tuân theo bảo đảm đã ghi.
- Trong môi trường nhiều luồng, một trạng thái trung gian **không được lộ** qua các lời gọi đồng thời nếu class hứa thread safety/invariant luôn quan sát nhất quán.
- Nếu object hỗ trợ callback/reentrancy, ngay trong một method, callback có thể quan sát trạng thái chưa hoàn tất nếu bạn gọi callback giữa các bước cập nhật.

Vì vậy invariant không đơn thuần là một biểu thức `if`; nó gắn với **quy tắc xuất bản và quan sát trạng thái**.

## 3. Các mức bảo đảm khi có exception

Trong thiết kế phần mềm thường phân biệt ba mức *exception safety guarantee*:

| Mức | Khi method thất bại | Ví dụ ý nghĩa |
| --- | --- | --- |
| **Basic guarantee** | Các invariant vẫn đúng, tài nguyên được quản lý; trạng thái có thể đã đổi | Đã ghi một số bản ghi thành công trước khi dừng |
| **Strong guarantee** | Thất bại không làm thay đổi trạng thái quan sát được thuộc phạm vi cam kết (*commit-or-no-change*) | Cấu hình cũ giữ nguyên nếu cấu hình mới không hợp lệ |
| **No-throw guarantee** | Thao tác được thiết kế không để exception thoát ra trong những điều kiện mà hợp đồng bao phủ | Một getter thuần, đơn giản, không phụ thuộc I/O |

Đây là thuật ngữ **thiết kế**, không phải ba interface bắt buộc do Java cung cấp. Java **không tự động kiểm chứng** rằng một class đã đạt mức mà bạn công bố.

Cần rất cẩn thận với phạm vi:

- Strong guarantee về **field trong một object** không có nghĩa đã rollback **log, email, file, database, request HTTP**.
- Basic guarantee **không** cho phép object rơi vào trạng thái bất hợp lệ; nó chỉ cho phép một số thay đổi đã xảy ra nhưng **invariant vẫn đúng**.
- No-throw guarantee là một **lời hứa thiết kế về ngữ cảnh hợp lệ**, không có nghĩa không bao giờ có `Error` nghiêm trọng như `OutOfMemoryError` hay trục trặc JVM. Không dùng `catch (Throwable)` để giả vờ bảo đảm no-throw trong mọi trường hợp.

## 4. “Trạng thái không đổi” phải định nghĩa theo phạm vi

Khi công bố “nếu thất bại thì trạng thái không đổi”, hãy xác định **đối tượng và tác động nào** nằm trong lời hứa:

- Chỉ field của một instance?
- Cả collection do instance sở hữu?
- Những object mutable được tham chiếu?
- Dữ liệu đã ghi xuống file?
- Thay đổi trong transaction database?
- Side effect gửi sang hệ thống khác?
- Callback/listener đã nhận thông báo?
- Dữ liệu đã xuất bản cho thread khác?

Một class có thể giữ nguyên `this.state` nhưng đã:

```java
listener.onChanged(newValue);
throw new IllegalStateException("commit chưa hoàn tất");
```

Đây là **mã minh họa**. Dù field nội bộ chưa đổi, **listener đã quan sát một side effect**. Nói method này có strong guarantee toàn hệ thống sẽ không chính xác.

Hợp đồng nên viết cụ thể: “Nếu validation thất bại, cấu hình đang được sử dụng không đổi; không gọi listener”. Hoặc: “Nếu quá trình gửi thất bại, một số byte có thể đã được gửi, người gọi phải đối chiếu trạng thái trước khi retry”.

## 5. Ví dụ sai: sửa trạng thái trước rồi mới kiểm tra

Một triển khai nguy hiểm của cặp giá trị `lower`, `upper`:

```java
void setBounds(int newLower, int newUpper) {
    lower = newLower;
    if (newLower > newUpper) {
        throw new IllegalArgumentException("lower > upper");
    }
    upper = newUpper;
}
```

Đây là **phương thức minh họa** trong một class có hai field. Nếu ban đầu khoảng là `[2, 8]` rồi gọi `setBounds(10, 4)`, method gán `lower = 10` trước khi ném exception, trong khi `upper` vẫn là `8`. Trạng thái thành `[10, 8]`: **bất biến `lower <= upper` bị phá**.

Đây không chỉ là vi phạm strong guarantee mà có thể còn **không đạt basic guarantee**. Sau khi catch, các method khác có thể hoạt động sai vì đối tượng đang bất hợp lệ.

Cách sửa đơn giản: **kiểm tra toàn bộ các điều kiện có thể thất bại trước khi gán**, nếu phép commit cuối không thể thất bại trong phạm vi thông thường.

## 6. Chương trình Java 17: đối chiếu cách cập nhật sai và đúng

Lưu **`BoundsFailureDemo.java`**:

```java
public class BoundsFailureDemo {
    static class UnsafeRange {
        private int lower = 2;
        private int upper = 8;

        void setBounds(int a, int b) {
            lower = a;
            if (a > b) {
                throw new IllegalArgumentException("lower > upper");
            }
            upper = b;
        }

        String view() {
            return "[" + lower + ", " + upper + "]";
        }
    }

    static class SafeRange {
        private int lower = 2;
        private int upper = 8;

        void setBounds(int a, int b) {
            if (a > b) {
                throw new IllegalArgumentException("lower > upper");
            }
            lower = a;
            upper = b;
        }

        String view() {
            return "[" + lower + ", " + upper + "]";
        }
    }

    public static void main(String[] args) {
        UnsafeRange unsafe = new UnsafeRange();
        SafeRange safe = new SafeRange();

        try {
            unsafe.setBounds(10, 4);
        } catch (IllegalArgumentException e) {
            System.out.println("Unsafe bị từ chối");
        }
        try {
            safe.setBounds(10, 4);
        } catch (IllegalArgumentException e) {
            System.out.println("Safe bị từ chối");
        }

        System.out.println("Unsafe sau lỗi: " + unsafe.view());
        System.out.println("Safe sau lỗi: " + safe.view());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 BoundsFailureDemo.java
java BoundsFailureDemo
```

**Stdout chính xác:**

```text
Unsafe bị từ chối
Safe bị từ chối
Unsafe sau lỗi: [10, 8]
Safe sau lỗi: [2, 8]
```

Trong `UnsafeRange`, đối tượng vẫn giữ giá trị mới của `lower` dù thao tác bị từ chối và invariant đã sai. `SafeRange` kiểm tra trước, sau đó mới gán, nên lỗi validation giữ nguyên trạng thái.

**Giới hạn:** `SafeRange` ở đây là ví dụ **đơn luồng không có callback**. Việc gán hai field riêng rẽ không tự bảo đảm thread khác luôn quan sát một snapshot nhất quán. Vấn đề concurrent observation cần thiết kế riêng.

## 7. Tiền điều kiện: lỗi thuộc trách nhiệm caller

Một phương thức nên công bố đối số nào hợp lệ:

```java
/**
 * @param amount số tiền nguyên dương
 * @throws IllegalArgumentException nếu amount không dương
 */
public void deposit(long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException(
                "amount phải lớn hơn 0");
    }
    // ...
}
```

Đây là **mã minh họa**, phần cập nhật cần được triển khai. `IllegalArgumentException` mô tả **tham số caller truyền vi phạm tiền điều kiện**. Nó là unchecked nên Java không buộc khai báo `throws` trong chữ ký, nhưng JavaDoc `@throws` vẫn hữu ích.

Nếu một tham số null không được chấp nhận, có thể dùng `Objects.requireNonNull` theo hợp đồng. Nếu object ở trạng thái chưa mở/đã đóng, `IllegalStateException` thường phản ánh **vòng đời/trạng thái** chính xác hơn `IllegalArgumentException`.

Quan trọng: **kiểm tra tiền điều kiện càng sớm càng tốt, trước side effect**. Khi validation thất bại, API nên có exceptional postcondition dễ hiểu, thường là “không thay đổi trạng thái”.

## 8. Hậu điều kiện thành công phải tương ứng với hậu điều kiện lỗi

Xét ví tiền:

- **Trước:** `balance >= 0`.
- **Input:** `amount > 0`.
- **Thành công:** `newBalance = oldBalance - amount`, vẫn không âm.
- **Không đủ tiền:** không trừ bất kỳ phần nào, ném lỗi hoặc trả thất bại theo hợp đồng.
- **Validation sai:** không thay đổi.
- **Nếu dữ liệu thuộc giao dịch bên ngoài:** cần cam kết riêng về persistence.

Một contract không nên viết mơ hồ “nếu có lỗi thì trạng thái có thể bất kỳ”. Nếu không thể cam kết strong guarantee, hãy nói rõ **mức basic**, những tác động đã có thể xảy ra và thao tác phục hồi tương ứng.

Ngoại lệ là tín hiệu điều khiển về **thất bại của lời gọi**, nhưng không tự miêu tả tình trạng state. Hợp đồng API mới quyết định người dùng có thể tiếp tục như thế nào.

## 9. Ví dụ Java 17: bảo toàn số dư khi rút thất bại

Lưu **`WalletContractDemo.java`**:

```java
public class WalletContractDemo {
    static class Wallet {
        private long balance;

        Wallet(long initial) {
            if (initial < 0) {
                throw new IllegalArgumentException(
                        "initial phải không âm");
            }
            balance = initial;
        }

        long balance() {
            return balance;
        }

        void withdraw(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (amount > balance) {
                throw new IllegalStateException("Không đủ tiền");
            }
            balance -= amount;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        try {
            wallet.withdraw(150);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối: " + e.getMessage());
        }
        System.out.println("Sau từ chối: " + wallet.balance());

        wallet.withdraw(30);
        System.out.println("Sau thành công: " + wallet.balance());

        try {
            wallet.withdraw(-5);
        } catch (IllegalArgumentException e) {
            System.out.println("Input sai: " + e.getMessage());
        }
        System.out.println("Cuối: " + wallet.balance());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 WalletContractDemo.java
java WalletContractDemo
```

**Stdout chính xác:**

```text
Từ chối: Không đủ tiền
Sau từ chối: 100
Sau thành công: 70
Input sai: amount phải dương
Cuối: 70
```

Trong trường hợp này, **validation xảy ra trước phép trừ** và `long` không bị overflow ở phép trừ vì `amount > 0` và `amount <= balance`, với `balance` luôn không âm trong class đơn giản. Nếu sau này thêm các method cộng số dư, vẫn cần kiểm soát overflow để invariant giữ đúng.

Bài học là **lỗi không để lại số dư âm hay trừ một phần**. Nó chưa phải ứng dụng ví điện tử thực với nhiều luồng, lưu trữ hoặc giao dịch ngân hàng.

## 10. Kiểm tra overflow cũng thuộc bảo đảm trạng thái

Một số phép tính Java `int` và `long` có thể **overflow mà không ném exception tự động**, tạo ra trạng thái sai.

Ví dụ nạp vào một số dư gần `Long.MAX_VALUE`:

```java
balance += amount;
```

Phép cộng có thể tràn thành số âm, phá invariant. Một cách mạnh hơn là tính trước bằng `Math.addExact`:

```java
long next = Math.addExact(balance, amount);
if (next < 0) {
    throw new IllegalStateException("Số dư không hợp lệ");
}
balance = next;
```

Đây là **mã minh họa**, giả định đã kiểm tra `amount > 0` và `balance >= 0` trước đó. `Math.addExact` ném `ArithmeticException` nếu phép cộng tràn; vì chưa gán, trạng thái cũ được giữ.

Không nên hiểu rằng **mọi phép tính trung gian đều an toàn chỉ vì không có checked exception**. Validation có thể ném unchecked exception và những phép tính im lặng overflow cũng cần được kiểm soát.

## 11. Ví dụ Java 17: phép cộng tràn nhưng state vẫn nguyên

Lưu **`OverflowGuaranteeDemo.java`**:

```java
public class OverflowGuaranteeDemo {
    static class Counter {
        private long value;

        Counter(long initial) {
            value = initial;
        }

        void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException(
                        "amount phải không âm");
            }
            long next = Math.addExact(value, amount);
            value = next;
        }

        long value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(Long.MAX_VALUE - 1);
        counter.add(1);
        System.out.println("Đạt max: "
                + (counter.value() == Long.MAX_VALUE));

        try {
            counter.add(1);
        } catch (ArithmeticException e) {
            System.out.println("Bắt overflow");
        }

        System.out.println("Giữ max: "
                + (counter.value() == Long.MAX_VALUE));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 OverflowGuaranteeDemo.java
java OverflowGuaranteeDemo
```

**Stdout chính xác:**

```text
Đạt max: true
Bắt overflow
Giữ max: true
```

`Math.addExact` tính và kiểm tra **trước commit**. Nếu phép tính ném `ArithmeticException`, dòng gán `value = next` không chạy, giữ trạng thái cũ.

Nếu dùng `value += amount`, tràn số có thể làm trạng thái vi phạm invariant mà không hề có exception để catch.

## 12. Pattern “validate → prepare → commit”

Để đạt strong guarantee cho dữ liệu nội bộ, một cách thực tế:

1. **Validate:** kiểm tra precondition và state hiện tại.
2. **Prepare:** tạo dữ liệu/giá trị thay thế, tính mọi phép có thể lỗi trong biến local hoặc object tạm.
3. **Commit:** chỉ cập nhật trạng thái công bố khi mọi bước chuẩn bị đã thành công.

Ví dụ:

```java
void replace(List<String> incoming) {
    Objects.requireNonNull(incoming, "incoming");
    List<String> candidate = List.copyOf(incoming);
    this.items = candidate;
}
```

Đây là **method minh họa**, cần import `List`, `Objects` và field `items`. `List.copyOf` có thể ném nếu input null/bao gồm phần tử null, hoặc gặp lỗi phù hợp trong quá trình tạo bản sao. Vì `this.items` chỉ được gán **sau khi candidate hoàn tất**, lỗi trước commit giữ nguyên reference cũ.

**Không giả định List.copyOf luôn snapshot chính xác một collection bị thread khác sửa đồng thời**; cần đầu vào ổn định hoặc đồng bộ phù hợp. Và `List.copyOf` chỉ tạo cấu trúc list không chỉnh sửa được qua API của nó; nếu phần tử bên trong là object mutable, chúng không tự được deep-copy.

## 13. Ví dụ Java 17: cập nhật collection kiểu copy-then-swap

Lưu **`CopyThenSwapDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class CopyThenSwapDemo {
    static class Registry {
        private List<String> names = List.of("old");

        List<String> snapshot() {
            return names;
        }

        void replace(List<String> incoming) {
            Objects.requireNonNull(incoming, "incoming");
            List<String> candidate = List.copyOf(incoming);
            names = candidate;
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        try {
            registry.replace(java.util.Arrays.asList("A", null));
        } catch (NullPointerException e) {
            System.out.println("Bản cập nhật bị từ chối");
        }

        System.out.println("Sau lỗi: " + registry.snapshot());

        registry.replace(List.of("A", "B"));
        System.out.println("Sau thành công: " + registry.snapshot());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CopyThenSwapDemo.java
java CopyThenSwapDemo
```

**Stdout chính xác:**

```text
Bản cập nhật bị từ chối
Sau lỗi: [old]
Sau thành công: [A, B]
```

Ở đường lỗi, `List.copyOf` từ chối phần tử null và **chưa có thay đổi nào được gán cho `names`**. Ở đường thành công, chỉ một phép gán reference xuất bản bản list mới.

Đây là strong guarantee đối với **danh sách tên được lưu bên trong một instance trong ví dụ đơn luồng**; nó không tự đồng bộ khi nhiều thread truy cập field.

## 14. Không lộ trạng thái mutable qua getter

Strong guarantee có thể bị phá bởi **aliasing**, ngay cả khi setter được triển khai rất cẩn thận.

Ví dụ có vấn đề:

```java
class Store {
    private final List<String> values = new ArrayList<>();

    List<String> getValues() {
        return values;
    }
}
```

Đây là **class minh họa** cần import `List`, `ArrayList`. Caller nhận đúng reference tới list nội bộ rồi có thể viết `store.getValues().clear()` mà không đi qua validation.

Nếu invariant là “list luôn chứa ít nhất một item”, getter mutable làm invariant mất bảo vệ.

Các lựa chọn:

- Trả **immutable snapshot** như `List.copyOf(values)` nếu nội dung phù hợp.
- Trả view không chỉnh sửa được như `Collections.unmodifiableList` khi muốn phản ánh thay đổi của list nguồn nhưng không cho caller sửa qua view.
- Dùng object immutable ngay từ đầu và thay thế toàn bộ reference khi commit.
- Kiểm soát sở hữu/ownership của mọi reference mutable được truyền qua API.
- Nếu các phần tử cũng mutable, cân nhắc deep copy hoặc một representation bất biến phù hợp.

Hậu điều kiện thất bại không bền vững nếu caller có đường khác để sửa state không kiểm soát.

## 15. Đối tượng immutable giúp đơn giản hóa exception safety

Với một value object bất biến, method “thay đổi” có thể tạo **object mới**. Nếu xây object mới thất bại, object cũ tự nhiên còn nguyên.

Ví dụ Java 17:

```java
record PortRange(int min, int max) {
    PortRange {
        if (min < 1 || max > 65535 || min > max) {
            throw new IllegalArgumentException("PortRange sai");
        }
    }

    PortRange withMax(int nextMax) {
        return new PortRange(min, nextMax);
    }
}
```

Đây là **record minh họa**, có thể đặt trong một file Java riêng tên `PortRange.java`. Một `PortRange(1000, 2000)` sẽ không đổi khi `withMax(500)` ném `IllegalArgumentException`.

Lợi ích:

- Không có thao tác sửa một phần trạng thái của object gốc.
- Có thể chuẩn bị object mới hoàn chỉnh trước khi xuất bản.
- Dễ dùng với cache, snapshot, so sánh và kiểm thử.
- Giảm rủi ro callback quan sát trạng thái nửa chừng.

Giới hạn: record có các component tham chiếu mutable **không tự trở thành deep immutable**. Nếu chứa `List<MutableItem>`, cần thiết kế snapshot/deep copy phù hợp.

## 16. Ví dụ Java 17: cấu hình bất biến và thất bại khi tạo bản mới

Lưu **`ImmutableConfigDemo.java`**:

```java
public class ImmutableConfigDemo {
    record Config(String host, int port) {
        Config {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("host rỗng");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("port sai");
            }
        }

        Config withPort(int newPort) {
            return new Config(host, newPort);
        }
    }

    public static void main(String[] args) {
        Config current = new Config("localhost", 8080);

        try {
            current = current.withPort(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Tạo cấu hình mới thất bại");
        }

        System.out.println("Cấu hình cũ: " + current);

        current = current.withPort(9090);
        System.out.println("Cấu hình mới: " + current);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ImmutableConfigDemo.java
java ImmutableConfigDemo
```

**Stdout chính xác:**

```text
Tạo cấu hình mới thất bại
Cấu hình cũ: Config[host=localhost, port=8080]
Cấu hình mới: Config[host=localhost, port=9090]
```

Phép gán `current = current.withPort(-1)` không xảy ra vì vế phải ném exception trước khi tạo kết quả. Nếu tạo cấu hình mới thành công, biến `current` mới được trỏ tới object mới. Đây là mẫu **prepare then publish** tự nhiên khi dùng immutable data.

## 17. Khi phép commit cũng có thể thất bại

Không phải mọi thao tác commit là một phép gán field đơn giản. Nếu commit phải:

- ghi qua filesystem,
- gọi database,
- gửi message ra broker,
- cập nhật nhiều object chia sẻ,
- gọi listener có thể ném exception,
- cấp phát thêm bộ nhớ,
- cập nhật cache rồi công bố sự kiện,

thì **commit có thể thất bại giữa chừng**. Khi ấy pattern “validate → prepare → commit” cần được mở rộng.

Một số chiến lược:

1. **Giảm điểm có thể thất bại trong commit:** chuẩn bị dữ liệu và cấp phát trước, commit chỉ bằng cập nhật nguyên tử khi có thể.
2. **Transaction** của hệ thống hỗ trợ, với phạm vi rõ ràng.
3. **Compensation** có chủ đích nếu không thể rollback thực sự (nhưng compensation cũng có thể thất bại).
4. **State machine** công bố trạng thái `IN_PROGRESS`, `FAILED` hoặc `UNKNOWN` để caller không hiểu nhầm.
5. **Idempotency keys** và đối chiếu trạng thái khi side effect phía xa có thể đã xảy ra.

Đừng dùng `catch (Exception e) { oldValue = backup; }` rồi tuyên bố strong guarantee nếu phần còn lại của commit đã có side effect không thể hoàn tác.

## 18. Basic guarantee: trạng thái thay đổi một phần nhưng vẫn hợp lệ

Không phải API nào cũng cần strong guarantee. Một bộ xử lý import cho phép ghi thành công các hàng đầu tiên rồi dừng ở hàng lỗi có thể cung cấp **basic guarantee**:

- Mọi bản ghi đã commit là hợp lệ.
- Dữ liệu chưa được commit không bị coi là đã xử lý.
- Vòng đời tài nguyên được quản lý.
- Sau lỗi, đối tượng vẫn hoạt động theo invariant và có thể báo trạng thái đã xử lý một phần.
- Caller được công bố rõ **partial success**.

Ví dụ conceptual:

```java
for (Record record : records) {
    validate(record);
    storeOne(record); // Mỗi record có commit riêng.
}
```

Đây là **mã minh họa**, với các lớp/phương thức phụ chưa được định nghĩa. Nếu item thứ 5 thất bại, 4 item trước đã được lưu; method có thể ném exception, nhưng hệ thống không nên tuyên bố “không thay đổi gì”.

Basic guarantee không hề là thiết kế tồi nếu nó được **công bố rõ**, giữ invariant và phù hợp nghiệp vụ. Sai lầm là để caller **mặc nhiên kỳ vọng all-or-nothing** trong khi triển khai chỉ đảm bảo partial progress.

## 19. Ví dụ Java 17: partial progress vẫn giữ invariant

Lưu **`PartialImportDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialImportDemo {
    static class Importer {
        private final List<String> accepted = new ArrayList<>();

        void importAll(List<String> input) {
            for (String item : input) {
                if (item.isBlank()) {
                    throw new IllegalArgumentException(
                            "Item không được rỗng");
                }
                accepted.add(item);
            }
        }

        List<String> snapshot() {
            return List.copyOf(accepted);
        }
    }

    public static void main(String[] args) {
        Importer importer = new Importer();

        try {
            importer.importAll(List.of("A", "B", "", "C"));
        } catch (IllegalArgumentException e) {
            System.out.println("Import dừng: " + e.getMessage());
        }

        System.out.println("Đã nhận: " + importer.snapshot());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 PartialImportDemo.java
java PartialImportDemo
```

**Stdout chính xác:**

```text
Import dừng: Item không được rỗng
Đã nhận: [A, B]
```

Các item `"A"` và `"B"` đã được thêm. Khi gặp chuỗi rỗng, exception được ném **trước khi thêm item lỗi**; list nội bộ vẫn chỉ chứa dữ liệu hợp lệ. Caller phải biết `importAll` có thể **commit từng phần tử**, không giả định thất bại làm list quay về trạng thái ban đầu.

Mẫu này không thích hợp với hợp đồng nhập khẩu dữ liệu kiểu all-or-nothing, trừ khi được thay bằng staging và commit một lần hoặc transaction.

## 20. Strong guarantee cho batch: chuẩn bị hết rồi mới công bố

Nếu nghiệp vụ yêu cầu **hoặc nhận toàn bộ batch, hoặc không thay đổi gì**, có thể chuẩn bị một cấu trúc mới trước:

```java
void importAll(List<String> input) {
    List<String> candidate = new ArrayList<>(accepted);
    for (String item : input) {
        if (item.isBlank()) {
            throw new IllegalArgumentException("Item rỗng");
        }
        candidate.add(item);
    }
    accepted = List.copyOf(candidate);
}
```

Đây là **method minh họa**, với `accepted` là field có thể gán lại kiểu `List<String>` và import `List`, `ArrayList`. Nếu validation hoặc copy thất bại trước `accepted = ...`, field cũ không đổi.

Lưu ý:

- `accepted` không được khai báo `final` nếu muốn thay reference.
- Nếu các item mutable, việc sao chép list không tự sao chép sâu các item.
- Nếu gọi callback trong lúc prepare, callback có thể phát sinh side effect bên ngoài.
- Nếu nhiều thread có thể thay đổi `accepted`, cần đồng bộ hoặc cơ chế update nguyên tử.
- Trong hệ thống persistence, copy-then-swap của bộ nhớ **không rollback database hay file**.

Mục tiêu không chỉ là “dùng một list tạm”, mà là **đặt mọi công việc có thể thất bại trước ranh giới commit**.

## 21. Chương trình Java 17: batch thất bại không thêm phần tử nào

Lưu **`AtomicImportDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class AtomicImportDemo {
    static class Importer {
        private List<String> accepted = List.of("old");

        void importAll(List<String> input) {
            List<String> candidate = new ArrayList<>(accepted);
            for (String item : input) {
                if (item == null || item.isBlank()) {
                    throw new IllegalArgumentException(
                            "Item không hợp lệ");
                }
                candidate.add(item);
            }
            accepted = List.copyOf(candidate);
        }

        List<String> snapshot() {
            return accepted;
        }
    }

    public static void main(String[] args) {
        Importer importer = new Importer();

        try {
            importer.importAll(List.of("A", "", "C"));
        } catch (IllegalArgumentException e) {
            System.out.println("Batch thất bại");
        }
        System.out.println("Sau lỗi: " + importer.snapshot());

        importer.importAll(List.of("A", "B"));
        System.out.println("Sau thành công: " + importer.snapshot());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 AtomicImportDemo.java
java AtomicImportDemo
```

**Stdout chính xác:**

```text
Batch thất bại
Sau lỗi: [old]
Sau thành công: [old, A, B]
```

Mọi thay đổi được xây trong `candidate`. Chỉ khi danh sách hoàn tất và `List.copyOf` thành công, field `accepted` được cập nhật. Đây là strong guarantee cho **state nội bộ được quản lý trong ví dụ đơn luồng**.

## 22. Exception safety không đồng nghĩa với thread safety

Một method có strong guarantee khi gọi đơn luồng **không tự động an toàn** khi nhiều thread chạy đồng thời.

Ví dụ hai field:

```java
if (newLower > newUpper) {
    throw new IllegalArgumentException();
}
lower = newLower;
upper = newUpper;
```

Đây là **mã minh họa**. Một thread khác có thể đọc `lower` sau khi gán nhưng trước khi `upper` được gán, quan sát trạng thái trung gian không phù hợp. Nếu trường hợp này vi phạm hợp đồng, cần thêm đồng bộ.

Các lựa chọn thiết kế:

- Bảo vệ cả thao tác đọc và ghi bằng **cùng lock** (`synchronized` hoặc `Lock`).
- Gói trạng thái vào **một immutable snapshot** rồi cập nhật một reference với quy tắc xuất bản phù hợp (ví dụ `volatile`/`AtomicReference`).
- Sử dụng **CAS** nếu thao tác yêu cầu kiểm tra phiên bản hiện tại rồi cập nhật atomically.
- Giới hạn object ở **một thread** và ghi rõ nó không thread-safe.

**Chỉ thêm `volatile` cho từng field riêng lẻ không biến nhiều phép gán thành một transaction.** Exception guarantee và atomicity/visibility là các thuộc tính khác nhau nhưng có liên quan.

## 23. Ví dụ Java 17: công bố snapshot bất biến bằng một reference

Lưu **`SnapshotStateDemo.java`**:

```java
public class SnapshotStateDemo {
    record Bounds(int lower, int upper) {
        Bounds {
            if (lower > upper) {
                throw new IllegalArgumentException("Khoảng sai");
            }
        }
    }

    static class RangeStore {
        private volatile Bounds bounds = new Bounds(1, 5);

        Bounds snapshot() {
            return bounds;
        }

        void replace(int lower, int upper) {
            Bounds candidate = new Bounds(lower, upper);
            bounds = candidate;
        }
    }

    public static void main(String[] args) {
        RangeStore store = new RangeStore();

        try {
            store.replace(9, 2);
        } catch (IllegalArgumentException e) {
            System.out.println("Từ chối khoảng sai");
        }

        System.out.println("Sau lỗi: " + store.snapshot());

        store.replace(3, 7);
        System.out.println("Sau thành công: " + store.snapshot());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SnapshotStateDemo.java
java SnapshotStateDemo
```

**Stdout chính xác:**

```text
Từ chối khoảng sai
Sau lỗi: Bounds[lower=1, upper=5]
Sau thành công: Bounds[lower=3, upper=7]
```

Record `Bounds` kiểm tra invariant khi tạo. Field `volatile Bounds bounds` được cập nhật bằng **một phép gán reference**, nên reader lấy được một snapshot nhất quán của hai thành phần immutable. Nếu việc cập nhật là **read-modify-write dựa trên snapshot cũ** giữa nhiều writer, chỉ `volatile` không ngăn lost update: có thể cần `AtomicReference.compareAndSet` hoặc lock.

Đây là một cách kết hợp strong guarantee khi tạo candidate và quy tắc publish state trong môi trường concurrent.

## 24. Ví dụ: atomic transfer giữa hai số dư trong một object

Khi thay đổi nhiều field phải đi cùng nhau, hãy kiểm tra mọi điều kiện trước. Ví dụ dưới đây dùng **một lock trên instance** để không cho các method của chính class quan sát transfer nửa chừng.

Lưu **`AccountTransferDemo.java`**:

```java
public class AccountTransferDemo {
    static class Ledger {
        private long left = 100;
        private long right = 20;

        synchronized void transfer(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (amount > left) {
                throw new IllegalStateException(
                        "Không đủ số dư bên trái");
            }

            long nextRight = Math.addExact(right, amount);
            long nextLeft = left - amount;

            left = nextLeft;
            right = nextRight;
        }

        synchronized String snapshot() {
            return left + "/" + right;
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();

        try {
            ledger.transfer(150);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối chuyển");
        }
        System.out.println("Sau lỗi: " + ledger.snapshot());

        ledger.transfer(30);
        System.out.println("Sau chuyển: " + ledger.snapshot());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 AccountTransferDemo.java
java AccountTransferDemo
```

**Stdout chính xác:**

```text
Từ chối chuyển
Sau lỗi: 100/20
Sau chuyển: 70/50
```

`Math.addExact` kiểm soát overflow ở số dư nhận trước khi gán. Cả `transfer` và `snapshot` dùng **cùng monitor lock**; caller dùng API đã thiết kế không nhìn thấy giữa hai phép gán. Những side effect chưa được cài trong ví dụ (database, network, listener) không được bao phủ bởi lock này.

**Không coi đây là hệ thống chuyển tiền đa tài khoản/đa tiến trình thực tế.** Transaction database, lock đa đối tượng, crash recovery và idempotency cần thiết kế riêng.

## 25. Ràng buộc state trước và sau lifecycle failure

Có những object không thể trở lại trạng thái cũ sau khi hoạt động thất bại, nhưng vẫn có thể chuyển sang một trạng thái **hợp lệ, rõ nghĩa**.

Ví dụ state machine:

```text
NEW → OPEN → CLOSED
       │
       └── I/O thất bại → FAILED
```

Hợp đồng:

- `read()` chỉ hợp lệ ở `OPEN`.
- Nếu validation sai, object vẫn ở `OPEN` (strong guarantee cho lỗi input).
- Nếu underlying I/O hỏng không thể tiếp tục, object chuyển sang `FAILED`.
- Sau `FAILED`, chỉ những thao tác đã công bố (ví dụ `close`, `state` hoặc `diagnostics`) được phép; `read()` bị từ chối bằng `IllegalStateException`.
- Dù có lỗi, object **không** ở một trạng thái mơ hồ nửa OPEN nửa CLOSED.

Đây là **basic guarantee** cho lỗi I/O: trạng thái có thay đổi sang `FAILED`, nhưng invariant về lifecycle vẫn giữ.

Một số API JDK cho phép thử lại đọc sau timeout; không nên ép mọi loại IOException vào `FAILED` nếu contract và giao thức cho phép tiếp tục. Quyết định phải dựa trên **khả năng duy trì invariant sau lỗi cụ thể**.

## 26. Chương trình Java 17: exceptional postcondition là trạng thái FAILED

Lưu **`FailureStateDemo.java`**:

```java
import java.io.IOException;

public class FailureStateDemo {
    enum State {
        NEW, OPEN, FAILED, CLOSED
    }

    static class ReaderSession {
        private State state = State.NEW;

        void open() {
            if (state != State.NEW) {
                throw new IllegalStateException("Không còn NEW");
            }
            state = State.OPEN;
        }

        String read(boolean fail) throws IOException {
            if (state != State.OPEN) {
                throw new IllegalStateException(
                        "read cần trạng thái OPEN");
            }
            if (fail) {
                state = State.FAILED;
                throw new IOException("Lỗi đọc");
            }
            return "data";
        }

        State state() {
            return state;
        }

        void close() {
            state = State.CLOSED;
        }
    }

    public static void main(String[] args) {
        ReaderSession session = new ReaderSession();
        session.open();
        System.out.println("Trước: " + session.state());

        try {
            session.read(true);
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Sau lỗi: " + session.state());
        session.close();
        System.out.println("Sau close: " + session.state());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 FailureStateDemo.java
java FailureStateDemo
```

**Stdout chính xác:**

```text
Trước: OPEN
Bắt: Lỗi đọc
Sau lỗi: FAILED
Sau close: CLOSED
```

Lỗi đọc khiến object chuyển sang `FAILED` có chủ đích trước khi ném checked `IOException`. Mục tiêu là **công bố hậu điều kiện lỗi rõ ràng**, không phải giữ nguyên mọi thứ trong mọi trường hợp.

Đối với hệ thống thực, trạng thái `FAILED` phải có quy tắc đóng, tái tạo hoặc chẩn đoán phù hợp; không dùng state flag để che resource leak.

## 27. Kiểm tra và thao tác có thể ném exception bất kỳ lúc nào?

Trong Java, một lời gọi thường có nhiều nguồn lỗi:

- **Validation**: `IllegalArgumentException`, `NullPointerException`.
- **Lifecycle**: `IllegalStateException`.
- **Tính toán**: `ArithmeticException` như `Math.addExact`.
- **Collection**: `IndexOutOfBoundsException`, `ConcurrentModificationException` theo API.
- **I/O**: `IOException`, `UncheckedIOException` hoặc lỗi framework.
- **Allocation**: lỗi cấp phát/JVM nghiêm trọng, thường ngoài phạm vi bảo đảm phục hồi ứng dụng.
- **Callback tùy ý**: có thể ném exception mà class gọi callback không kiểm soát.
- **Cancellation/interruption**: đặc biệt ở hoạt động chờ hoặc tác vụ bất đồng bộ.

Việc định nghĩa state hậu lỗi cần xét **những nguồn lỗi nằm trong hợp đồng mà API hứa xử lý**, chứ không chỉ một câu `throw new IllegalArgumentException` do chính bạn viết.

Ví dụ nếu bạn đã cập nhật field thứ nhất rồi gọi một callback có thể ném `RuntimeException` trước khi cập nhật field thứ hai, lỗi callback có thể phá invariant dù nhánh validation đã được kiểm tra từ trước.

## 28. Callback, observer và rủi ro reentrancy

Xem mẫu có vấn đề:

```java
state = "UPDATING";
listener.onChange(newValue);
state = "READY";
```

Đây là **mã minh họa**. Nếu `listener.onChange` ném exception, object bị kẹt ở `"UPDATING"`. Nếu listener còn gọi ngược `getState()` trước khi ném, nó đã thấy trạng thái trung gian.

Các chiến lược:

1. Hoàn tất và công bố state nhất quán **trước** khi phát thông báo; nhưng nếu listener thất bại, phải công bố rằng side effect thông báo có thể thất bại sau commit.
2. Chuẩn bị event và state mới, commit theo thứ tự có hợp đồng rõ.
3. Không gọi callback không tin cậy giữa các bước sửa invariant.
4. Nếu callback chạy bất đồng bộ, cần công bố failure semantics riêng cho event delivery.
5. Nếu notification là bắt buộc cùng với state transition, cần một cơ chế transactional/outbox hoặc cách bù trừ, không chỉ `try/catch`.

**Strong guarantee với trạng thái nội bộ** không kéo theo strong guarantee với toàn bộ observer. Hợp đồng phải nói rõ **commit trước hay sau notification** và kết quả khi notification thất bại.

## 29. Tài nguyên và hậu điều kiện lỗi

State không chỉ là field nghiệp vụ. Một API còn quản lý **file handle, socket, lock, database connection, stream hoặc thread**.

Sau lỗi, cần trả lời:

- Tài nguyên có đang mở không?
- Ai sở hữu việc đóng?
- Đóng có thể ném lỗi không?
- Có giữ lock không, hay đã được giải phóng?
- Đối tượng có thể tái sử dụng hay phải tạo mới?
- Có dữ liệu trong buffer chưa flush?
- Có transaction chưa commit/rollback?
- Caller được phép retry trên cùng resource không?

`try-with-resources` giúp đóng resource khi thoát phạm vi:

```java
try (InputStream input = openInput()) {
    return parse(input);
}
```

Đây là **mã minh họa**, method `openInput`, `parse` cần được định nghĩa và phương thức bao ngoài xử lý checked exceptions. Khi `parse` ném, Java vẫn cố gọi `input.close()`. Nhưng **đóng resource** không tự bảo đảm dữ liệu ghi trước đó được rollback hoặc đối tác không nhận request.

**Không đánh đồng “cleanup thành công” với “transaction rollback thành công”.**

## 30. Ví dụ Java 17: try-with-resources vẫn đóng sau lỗi

Lưu **`CleanupAfterFailureDemo.java`**:

```java
public class CleanupAfterFailureDemo {
    static class Resource implements AutoCloseable {
        private boolean closed;

        void work() {
            System.out.println("Đang xử lý");
            throw new IllegalStateException("Thất bại");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("Đã đóng");
        }

        boolean isClosed() {
            return closed;
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            resource.work();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Closed: " + resource.isClosed());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CleanupAfterFailureDemo.java
java CleanupAfterFailureDemo
```

**Stdout chính xác:**

```text
Đang xử lý
Đã đóng
Bắt: Thất bại
Closed: true
```

`try (resource)` hợp lệ từ Java 9 với một biến resource **final hoặc effectively final**. Dù `work()` thất bại, `close()` được gọi trước khi handler catch thực thi.

Đây là một bảo đảm về **vòng đời resource** trong ví dụ, không phải bảo đảm rằng mọi trạng thái nghiệp vụ bị đổi trong `work()` đã được hoàn tác.

## 31. Nếu cả thao tác chính và cleanup đều thất bại?

`try-with-resources` dùng **suppressed exceptions** để không làm mất lỗi chính khi `close()` cũng ném exception.

Ví dụ:

```java
try (Resource resource = acquire()) {
    perform(resource);  // Ném lỗi chính.
} // close() có thể ném lỗi phụ.
```

Đây là **mã minh họa**, `Resource` và các method phụ cần được khai báo. Nếu thân `try` ném một exception và `close()` cũng ném, lỗi close thường được gắn vào `primary.getSuppressed()` theo cơ chế chuẩn.

Hợp đồng trạng thái cần xét: một resource có thể **đã thực hiện cleanup một phần** rồi `close` thất bại. Lỗi bị suppressed vẫn đáng ghi nhận khi đánh giá tài nguyên có thực sự được giải phóng.

Không chỉ lấy `primary.getMessage()` rồi bỏ cause/suppressed nếu cần chẩn đoán điều kiện khôi phục. Trong logger, ưu tiên ghi object `Throwable` đầy đủ.

## 32. Ví dụ Java 17: ngoại lệ close thành suppressed

Lưu **`SuppressedFailureDemo.java`**:

```java
import java.io.IOException;

public class SuppressedFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close thất bại");
        }
    }

    static void run() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("work thất bại");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedFailureDemo.java
java SuppressedFailureDemo
```

**Stdout chính xác:**

```text
Primary: work thất bại
Suppressed count: 1
Suppressed: close thất bại
```

Nếu code tự viết `finally` rồi ném exception mới, nó có thể **che lỗi ban đầu**; dùng cấu trúc resource phù hợp giúp giữ dữ liệu chẩn đoán tốt hơn.

## 33. Phép ghi file/network có thể chỉ hoàn thành một phần

Một `OutputStream.write` có thể **đã xuất một số byte trước khi IOException được ném**. Khi đó không thể kết luận “method ném IOException nên chưa ghi gì”.

Ví dụ tự chạy mô phỏng **partial I/O** mà không cần filesystem:

Lưu **`PartialWriteDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class PartialWriteDemo {
    static class FailingOutput extends OutputStream {
        private final StringBuilder delivered = new StringBuilder();

        @Override
        public void write(int value) throws IOException {
            if (delivered.length() == 2) {
                throw new IOException("Sink từ chối byte tiếp theo");
            }
            delivered.append((char) (value & 0xff));
        }

        String delivered() {
            return delivered.toString();
        }
    }

    public static void main(String[] args) {
        FailingOutput output = new FailingOutput();

        try {
            output.write("ABC".getBytes(StandardCharsets.US_ASCII));
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Đã ghi: " + output.delivered());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 PartialWriteDemo.java
java PartialWriteDemo
```

**Stdout chính xác:**

```text
Bắt: Sink từ chối byte tiếp theo
Đã ghi: AB
```

`OutputStream` có implementation `write(byte[])` gọi `write(byte[],off,len)` mặc định; lớp `OutputStream` mặc định lần lượt gọi `write(int)` với từng byte. Trong ví dụ, hai byte `A` và `B` đã được chấp nhận, byte `C` gây lỗi. `IOException` không tự làm mất hai byte đã ghi.

**Đây là mô phỏng chủ động**, không chứng minh mọi stream sẽ chia nhỏ việc ghi giống vậy. Bài học tổng quát là phải viết hợp đồng về **partial progress**, không áp strong guarantee cho I/O chỉ bằng suy đoán.

## 34. Database transaction: mạnh trong phạm vi transaction, không tự bao cả thế giới

Một transaction database có thể cung cấp atomicity cho một nhóm thao tác **trên những tài nguyên thuộc phạm vi transaction ấy**. Ví dụ khung JDBC:

```java
connection.setAutoCommit(false);
try {
    debit(connection, from, amount);
    credit(connection, to, amount);
    connection.commit();
} catch (SQLException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        e.addSuppressed(rollbackError);
    }
    throw e;
}
```

Đây là **mã minh họa**, cần connection, các helper và xử lý transaction lifecycle phù hợp. Trong thực tế phải khôi phục `autoCommit`/đóng connection theo quyền sở hữu, và tính đến lỗi network trong hoặc sau commit.

Các điều kiện quan trọng:

- Cùng transaction không tự bao phủ email, file hay HTTP call gửi trong giao dịch.
- `rollback()` cũng có thể thất bại; cần bảo toàn lỗi rollback.
- Một lỗi kết nối trong lúc `commit()` có thể khiến **kết quả commit chưa rõ** đối với client.
- Không được khẳng định “có SQLException thì database chắc chắn không thay đổi”.
- Isolation và concurrency của database cần được cấu hình phù hợp; exception safety ở Java không thay thế transaction semantics.

Hợp đồng có thể cần trạng thái **UNKNOWN** hoặc khả năng đối chiếu transaction ID khi kết quả commit chưa thể xác minh.

## 35. Distributed side effects: “ném lỗi” không có nghĩa “chưa thực hiện”

Trong RPC, HTTP, message broker hoặc hệ thống thanh toán, một request có thể:

1. Được client gửi.
2. Được server nhận và xử lý.
3. Được server commit.
4. Phản hồi bị mất.
5. Client timeout và ném exception.

Trong trường hợp này, lời gọi phía client **thất bại ở mức biết kết quả**, nhưng side effect phía server **có thể đã xảy ra**.

Không thể sửa vấn đề bằng:

```java
catch (IOException e) {
    sendAgain();
}
```

Đây là **phản ví dụ minh họa**, method `sendAgain` chưa được định nghĩa. Lặp lại có thể tạo giao dịch thứ hai.

Các kỹ thuật phù hợp:

- **Idempotency key** để cùng một logical request không bị xử lý lặp sai.
- **Request/transaction ID** để tra cứu trạng thái server.
- **Retry có giới hạn** với backoff và deadline.
- **Outbox** hoặc event-driven consistency nếu hệ thống cần phối hợp ghi dữ liệu và phát sự kiện.
- **Compensation** khi không thể transaction xuyên dịch vụ.
- **Trạng thái kết quả chưa rõ** được công bố rõ cho caller, không trả “thất bại chắc chắn chưa commit”.

Strong guarantee **toàn hệ thống phân tán** đòi hỏi giao thức/thành phần hỗ trợ, không phải là tính năng tự có của checked exception.

## 36. Trạng thái kết quả: SUCCESS, FAILED và UNKNOWN

Với những API có side effect từ xa, một kết quả có thể phải phân biệt:

- **SUCCESS:** server đã xác nhận thao tác thành công.
- **FAILED:** server xác nhận thao tác không thực hiện hoặc từ chối và hợp đồng biết trạng thái.
- **UNKNOWN:** client không xác định chắc thao tác đã commit hay chưa.

Ví dụ kiểu kết quả Java 17:

```java
enum Outcome {
    SUCCESS, FAILED, UNKNOWN
}

record OperationResult(String requestId, Outcome outcome) {
}
```

Đây là **hai loại minh họa**, không có `main`. Một request timeout có thể dẫn đến `UNKNOWN`, còn một validation failure trước khi gửi có thể chắc chắn là `FAILED` mà không có side effect.

Không nên trả `FAILED` với ý nghĩa “chưa thực hiện” khi chỉ biết là **không nhận được phản hồi**. Nếu caller cần retry, việc phân biệt UNKNOWN là rất quan trọng.

## 37. Checked và unchecked exception không quyết định state guarantee

Một method `throws IOException` có thể:

- không thay đổi state nếu thất bại,
- thay đổi một phần state hợp lệ,
- đưa object vào `FAILED`,
- hoặc không thể xác minh side effect bên ngoài.

Tương tự, method ném `IllegalArgumentException` cũng có thể **vô tình làm hỏng state** nếu validation được thực hiện sau khi sửa field.

Do đó:

- **Checked vs unchecked:** quy tắc compiler ép catch-or-declare và ý nghĩa hợp đồng lỗi.
- **Basic/strong/no-throw:** mức cam kết trạng thái khi method kết thúc bất thường.
- **Atomicity:** tính không chia nhỏ được của một nhóm cập nhật trong phạm vi hệ thống xác định.
- **Thread safety:** các bảo đảm khi truy cập đồng thời.
- **Idempotency:** thực hiện lặp cùng logical operation không tạo hiệu ứng không mong muốn.
- **Durability:** hiệu ứng đã commit còn tồn tại qua những sự cố tương ứng.

Những thuộc tính này **không thay thế cho nhau**. Một API đáng tin thường cần nhiều hơn một thuộc tính cùng lúc.

## 38. Không được giả định catch sẽ phục hồi invariant

`try/catch` là cơ chế xử lý luồng điều khiển sau exception:

```java
try {
    updatePartA();
    updatePartB();
} catch (RuntimeException e) {
    log(e);
}
```

Đây là **mã minh họa**. Nếu `updatePartA` đã thay đổi state, rồi `updatePartB` ném exception, handler chỉ ghi log **không khôi phục gì**.

Viết `catch` không đồng nghĩa:

- rollback field,
- rollback database,
- thu hồi message đã gửi,
- đóng tất cả tài nguyên,
- giải phóng mọi lock,
- hoặc giữ nguyên trạng thái đối tượng.

Một handler đúng phải biết **hậu điều kiện thất bại** và quyền sở hữu công việc. Nếu không thể phục hồi, nó nên lan truyền hoặc chuyển lỗi bằng cause theo hợp đồng, thay vì trả thành công giả.

## 39. Cẩn thận với rollback thủ công

Một cách nghĩ thường gặp:

```java
State old = current;
try {
    updateExternalSystem();
    current = next;
} catch (Exception e) {
    current = old;
    throw e;
}
```

Đây là **mã minh họa**, các biến và method cần được định nghĩa. Đặt `current = old` không thể tự xóa side effect của `updateExternalSystem()`. Nếu `current` trỏ tới một object mutable đã bị sửa trong chỗ khác, giữ reference cũ cũng không bảo đảm trạng thái cũ thực sự còn nguyên.

Rollback thủ công có thể thất bại do:

- backup là shallow copy/alias.
- thao tác hoàn tác tự nó ném exception.
- callback đã nhìn thấy dữ liệu trung gian.
- resource/transaction đã commit một phần.
- thread khác đã đọc hoặc sửa state.
- một sự kiện đã được gửi sang hệ thống khác.
- lỗi phát sinh ở vị trí chưa được bạn dự đoán.

Nếu không thể rollback có độ tin cậy tương xứng, **công bố basic guarantee hoặc FAILED/UNKNOWN** thay vì hứa strong guarantee giả.

## 40. Exception safety và method có side effect quan sát được

Một public API có thể tạo side effect ngay cả khi field object không đổi:

- Ghi log có chứa dữ liệu.
- Tăng metric/counter.
- Phát event.
- Gửi email.
- Cấp phát ID mới.
- Tiêu thụ item từ queue.
- Đánh dấu một công việc đã chạy.
- Gọi callback bất đồng bộ.

Điều này có nghĩa “**không đổi state**” cần định nghĩa theo **phạm vi quan sát thực sự cần bảo đảm**. Một số side effect như log/metrics được chấp nhận xảy ra ngay cả khi method thất bại; không phải tất cả cần rollback.

Ví dụ một API có thể cam kết “nếu validation thất bại, dữ liệu nghiệp vụ không thay đổi; hệ thống vẫn ghi một audit event về lần gọi bị từ chối”. Hợp đồng này có thể hoàn toàn hợp lệ, nhưng không nên viết đơn giản “mọi trạng thái đều không đổi”.

## 41. Kết hợp exception cause với tình trạng state

Exception nên cho biết **nguyên nhân**; contract/documentation nên cho biết **tình trạng object**. Một số API muốn biểu diễn trạng thái cùng exception domain:

```java
class SubmissionException extends Exception {
    private final boolean mayHaveCommitted;

    SubmissionException(String message,
                        boolean mayHaveCommitted,
                        Throwable cause) {
        super(message, cause);
        this.mayHaveCommitted = mayHaveCommitted;
    }

    boolean mayHaveCommitted() {
        return mayHaveCommitted;
    }
}
```

Đây là **class minh họa**, không có `main`. Nó thể hiện cách công bố tri thức mà caller cần để quyết định đối chiếu hoặc retry.

Tuy nhiên, boolean `mayHaveCommitted` có thể chưa đủ cho hệ thống thực. Một enum `NOT_SENT/CONFIRMED/UNKNOWN` hoặc một result object chứa request ID, outcome và thông tin hỗ trợ phục hồi có thể biểu đạt rõ hơn.

**Không suy diễn tình trạng commit chỉ từ `IOException`, `TimeoutException` hay `RuntimeException`.** Nguồn thông tin phải là hợp đồng giao thức/trạng thái được xác minh.

## 42. Viết JavaDoc với exceptional postcondition rõ ràng

Ví dụ API:

```java
/**
 * Thay toàn bộ cấu hình đang chạy.
 *
 * @param next dữ liệu cấu hình mới, không null
 * @throws NullPointerException nếu next null
 * @throws IllegalArgumentException nếu next không hợp lệ
 *
 * <p>Nếu validation thất bại, cấu hình hiện tại
 * không bị thay đổi và listener chưa được gọi.</p>
 *
 * <p>Nếu cập nhật nguồn bên ngoài thất bại, trạng thái
 * có thể là FAILED; gọi state() để kiểm tra trước khi retry.</p>
 */
public void replace(Config next) {
    // implementation theo hợp đồng trên
}
```

Đây là **mã minh họa**, với `Config` và implementation được thiết kế riêng. Khi viết JavaDoc thật, cần mô tả cả những điều kiện state và exception cụ thể nếu method có chúng.

Một template hữu ích trong tài liệu:

| Mục | Câu cần trả lời |
| --- | --- |
| Invariant | Những điều nào luôn đúng ở state hợp lệ? |
| Precondition | Caller được truyền gì và gọi lúc nào? |
| Success | Field/resource/side effect nào thay đổi? |
| Failure by validation | State nào không đổi? |
| Failure by I/O | Có thể đã ghi/gửi một phần không? |
| Failure by cancellation | Tài nguyên và interrupt status thế nào? |
| Retry | Có cần sửa input, rebuild object, tra cứu trạng thái hay idempotency key không? |
| Ownership | Ai đóng, rollback, release lock hoặc xử lý object FAILED? |

Mục tiêu là **caller không phải đọc toàn bộ source** mới biết sau exception có thể làm gì.

## 43. Thiết kế test: kiểm tra trạng thái, không chỉ loại exception

Một test chỉ xác nhận:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.update(badInput));
```

là **mã minh họa dùng JUnit**, cần thư viện và biến phù hợp. Nó kiểm tra có exception nhưng **chưa xác minh state hậu lỗi**.

Cần thêm:

- Snapshot state trước khi gọi.
- Chèn một lỗi có chủ đích ở vị trí mong muốn.
- Gọi method và bắt đúng loại exception.
- Snapshot state sau lỗi.
- So sánh các phần thuộc invariant và strong/basic guarantee.
- Nếu có side effect bên ngoài, kiểm tra fake/mock sink đã nhận gì, không suy từ state nội bộ.
- Kiểm tra tài nguyên đóng/lock được giải phóng.
- Kiểm tra cause/suppressed nếu wrapper/cleanup nằm trong hợp đồng.
- Kiểm tra caller có thể gọi method nào sau lỗi.
- Kiểm tra retry và idempotency theo tình huống.

**Test exception safety phải chủ động thử nhiều điểm thất bại**, không chỉ một nhánh validation dễ nhất.

## 44. Chương trình Java 17: assert cả exception và trạng thái không đổi

Lưu **`FailureInvariantAssertionsDemo.java`**:

```java
public class FailureInvariantAssertionsDemo {
    static class Counter {
        private int value = 5;

        void increase(int delta) {
            if (delta <= 0) {
                throw new IllegalArgumentException(
                        "delta phải dương");
            }
            int candidate = Math.addExact(value, delta);
            value = candidate;
        }

        int value() {
            return value;
        }
    }

    static void assertUnchanged(
            Counter counter, int before, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Thiếu exception");
        } catch (RuntimeException expected) {
            if (counter.value() != before) {
                throw new AssertionError("State đã thay đổi");
            }
            System.out.println("PASS unchanged");
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        assertUnchanged(counter, 5,
                () -> counter.increase(-1));

        counter.increase(3);
        System.out.println("Success state: " + counter.value());

        Counter nearMax = new Counter();
        nearMax.increase(Integer.MAX_VALUE - 5);

        assertUnchanged(nearMax, Integer.MAX_VALUE,
                () -> nearMax.increase(1));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 FailureInvariantAssertionsDemo.java
java FailureInvariantAssertionsDemo
```

**Stdout chính xác:**

```text
PASS unchanged
Success state: 8
PASS unchanged
```

Các nhánh được kiểm tra:

- Input âm ném `IllegalArgumentException`, `value` giữ 5.
- Tăng hợp lệ cập nhật từ 5 lên 8.
- Từ một đối tượng có `value = Integer.MAX_VALUE`, tăng tiếp gây `ArithmeticException` từ `Math.addExact`, giá trị vẫn nguyên.

Test dùng `AssertionError` chủ động để không cần cờ `-ea`. Nó chưa bao phủ mọi failure injection nhưng là mẫu kiểm thử **exceptional postcondition**, chứ không chỉ loại exception.

## 45. Failure injection: thử lỗi ở từng giai đoạn

Một hệ thống có nhiều bước:

```text
VALIDATE → PREPARE → WRITE → NOTIFY → COMMIT
```

Cần thử khi từng bước ném lỗi:

| Điểm phát lỗi | Điều cần xác minh |
| --- | --- |
| Validate | Không có thay đổi và không gọi dependency có side effect |
| Prepare | Candidate bị bỏ, state cũ hợp lệ |
| Write | Có partial I/O không? Có resource leak không? |
| Notify | Commit đã diễn ra chưa? Event có thể gửi một phần không? |
| Commit | Outcome có rõ không? Rollback/compensation có đảm bảo không? |
| Close/cleanup | Lỗi chính và suppressed có được bảo toàn không? |

Có thể dùng:

- Fake dependency chủ động ném `IOException` ở lần gọi thứ N.
- Fake sink ghi số lượng mục đã nhận rồi ném.
- In-memory repository quản lý transaction giả với outcome rõ.
- Latch để tạo tình huống concurrency cụ thể.
- Property-based test kiểm tra invariant trên nhiều input.
- Integration test độc lập cho database/filesystem/network thật.

Không phụ thuộc vào việc “đợi mạng tự lỗi” để kiểm thử logic guarantee; lỗi hạ tầng thực tế rất khó tái hiện đúng bước.

## 46. Đường thất bại và mức độ bảo đảm theo loại API

| API/thao tác | Mức có thể hướng tới | Chú ý |
| --- | --- | --- |
| Setter đơn giản đã validate đầy đủ | Strong cho field | Cần lưu ý observer và concurrency |
| Thay thế immutable snapshot | Strong cho snapshot | Snapshot cũ giữ nguyên nếu prepare thất bại |
| Batch import từng item | Basic | Đã commit một phần, phải công bố |
| Batch all-or-nothing trong memory | Strong trong phạm vi bộ nhớ | Prepare tất cả trước khi swap |
| Ghi `OutputStream` | Thường phải chấp nhận partial progress | IOException không rollback byte |
| JDBC transaction | Atomic trong phạm vi transaction hỗ trợ | Lỗi commit/đường mạng có thể khiến outcome chưa rõ |
| RPC có side effect | Cần idempotency/đối chiếu trạng thái | Timeout không chứng minh chưa commit |
| Resource close | Có thể ném IOException | Quản lý cleanup/suppressed |
| Getter bất biến đơn giản | Có thể thiết kế no-throw trong điều kiện hợp lệ | Không hứa miễn nhiễm mọi Error của JVM |

Bảng là gợi ý **thiết kế hợp đồng**, không phải khẳng định rằng mọi implementation của một loại API luôn đạt một mức guarantee cố định.

## 47. Những sai lầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có `catch` thì trạng thái tự rollback.” | Không. Catch chỉ xử lý luồng điều khiển. |
| “Checked exception chắc chắn giữ nguyên state.” | Không. Checked/unchecked độc lập với state guarantee. |
| “Chỉ cần invariant đúng khi thành công.” | Sau thất bại vẫn cần mức guarantee đã công bố. |
| “Basic guarantee nghĩa là không đổi gì.” | Không. State có thể đổi nhưng invariant phải giữ. |
| “Strong guarantee nghĩa là rollback cả email, log, database.” | Chỉ trong phạm vi cam kết; side effect ngoài cần cơ chế riêng. |
| “No-throw nghĩa là có thể bắt `Throwable` để không bao giờ lỗi.” | Không. Đừng che lỗi nghiêm trọng/JVM. |
| “Validation có thể đặt sau khi sửa field vì đã có exception.” | Có thể làm hỏng state trước khi ném. |
| “`List.copyOf` tự deep-copy mọi item mutable.” | Không. Chỉ tạo cấu trúc list snapshot theo hợp đồng. |
| “Getter trả list nội bộ không ảnh hưởng invariant.” | Caller có thể sửa trực tiếp nếu list mutable. |
| “Hai field `volatile` được gán liên tiếp là một transaction.” | Không. Reader có thể thấy trạng thái giữa chừng. |
| “Một immutable record chứa mutable field chắc chắn deep immutable.” | Không. Cần sở hữu/snapshot component. |
| “`finally`/try-with-resources tự hoàn tác dữ liệu ghi.” | Không. Chủ yếu quản lý cleanup tài nguyên. |
| “`IOException` khi write nghĩa là chưa ghi byte nào.” | Không. Ghi một phần có thể đã xảy ra. |
| “Timeout RPC chứng minh server chưa commit.” | Không. Outcome có thể là UNKNOWN. |
| “`rollback()` luôn thành công.” | Không. Rollback có thể ném lỗi riêng. |
| “Đã ném `IllegalStateException` thì object phải hỏng hoàn toàn.” | Không. Có thể là thao tác sai lifecycle, state vẫn hợp lệ. |
| “Chuyển sang FAILED là vi phạm basic guarantee.” | Không nếu FAILED là trạng thái hợp lệ có contract. |
| “Một phép gán reference đủ giải quyết mọi race writer.” | Không. Read-modify-write đồng thời cần lock/CAS. |
| “Catch rồi trả thành công là resilience.” | Chỉ đúng khi thật sự khôi phục theo contract. |
| “Chỉ assert loại exception là đủ test an toàn.” | Cần kiểm tra state và side effect sau failure. |

## 48. Câu hỏi tự kiểm tra

**1. Invariant là gì?**  
Một điều kiện về trạng thái phải giữ tại các điểm đối tượng được công bố là hợp lệ.

**2. Exceptional postcondition là gì?**  
Cam kết về state và side effect khi method kết thúc bằng exception.

**3. Basic guarantee khác strong guarantee ra sao?**  
Basic giữ invariant nhưng cho phép partial state changes; strong giữ nguyên trạng thái quan sát được trong phạm vi cam kết khi thất bại.

**4. Java có tự bảo đảm strong guarantee cho mọi method `throws IOException` không?**  
Không. Cần thiết kế/triển khai/kiểm thử.

**5. Vì sao đặt validation sau phép gán field nguy hiểm?**  
Exception có thể xảy ra sau khi state đã đổi một phần, thậm chí phá invariant.

**6. Pattern validate–prepare–commit giải quyết điều gì?**  
Đẩy những bước có thể lỗi trước một commit nhỏ, giúp giữ state cũ nếu chuẩn bị thất bại.

**7. Vì sao `List.copyOf` hữu ích nhưng không phải deep copy?**  
Nó tạo list không chỉnh sửa được bằng API list, nhưng object phần tử mutable có thể vẫn được chia sẻ.

**8. Record bất biến chứa `List<MutableItem>` có tự deep immutable không?**  
Không. Component tham chiếu mutable cần chính sách riêng.

**9. `Math.addExact` giúp ngoại lệ thế nào?**  
Nó phát hiện overflow trước khi gán, giúp tránh công bố giá trị tràn sai invariant.

**10. Catch một exception có bảo đảm callback trước đó chưa chạy không?**  
Không. Callback có thể đã tạo side effect trước khi ném.

**11. Nếu import 4 item rồi lỗi ở item thứ 5, đó có thể là mức guarantee nào?**  
Basic, nếu bốn item đã commit hợp lệ và invariant còn đúng, đồng thời contract công bố partial progress.

**12. Tại sao ghi `OutputStream` có thể để lại dữ liệu một phần sau IOException?**  
Implementation có thể ghi các byte trước khi gặp lỗi ở byte tiếp theo.

**13. `try-with-resources` cam kết điều gì khi thân try ném?**  
Nó cố đóng resource; nếu close cũng ném, có thể gắn suppressed exception lên lỗi chính. Không tự rollback side effect.

**14. Vì sao `rollback()` của database không thể được giả định luôn thành công?**  
Rollback có thể gặp lỗi I/O/kết nối hoặc tình trạng transaction chưa rõ, nên cần xử lý và log lỗi riêng.

**15. Timeout sau khi gửi lệnh tạo giao dịch có chứng minh giao dịch chưa commit?**  
Không. Có thể phải dùng trạng thái UNKNOWN và request ID để đối chiếu.

**16. `volatile Bounds` snapshot có giải quyết lost update giữa nhiều writer không?**  
Không. Cần CAS/lock cho read-modify-write.

**17. Nếu object chuyển thành `FAILED` sau IOException, có thể vẫn đạt basic guarantee không?**  
Có, nếu FAILED là trạng thái hợp lệ được công bố và tài nguyên được quản lý.

**18. Vì sao không catch `RuntimeException` rồi trả dữ liệu thành công mặc định?**  
Có thể che bug và partial side effect, vi phạm hợp đồng caller.

**19. Test ngoại lệ tốt cần kiểm tra thêm gì ngoài loại exception?**  
State trước–sau, invariant, side effect, resource, cause/suppressed, khả năng retry/sử dụng tiếp.

**20. Nếu getter cho caller reference tới collection mutable nội bộ, hậu điều kiện thất bại có dễ kiểm soát không?**  
Không. Caller có thể làm thay đổi state ngoài mọi validation của API.

**21. Lỗi trong listener sau commit có nghĩa commit trước đó đã tự rollback?**  
Không. Cần hợp đồng riêng cho commit và notification.

**22. Có nên dùng `catch (Throwable)` để tạo bảo đảm no-throw tuyệt đối không?**  
Không. Che cả lỗi nghiêm trọng của JVM thường không thể tạo bảo đảm an toàn thật.

**23. Tại sao cần nêu phạm vi “state không đổi”?**  
Vì field, resource, callback và side effect ngoài tiến trình có phạm vi bảo đảm khác nhau.

**24. Khi lỗi có thể khiến kết quả phía xa chưa rõ, caller cần thông tin gì?**  
Request ID, outcome UNKNOWN hoặc khả năng truy vấn trạng thái và chính sách idempotency/retry.

## 49. Checklist thiết kế API có hậu điều kiện lỗi rõ ràng

1. **Viết invariant:** đối tượng hợp lệ phải thỏa điều kiện gì?
2. **Viết precondition:** đối số, state và quyền sở hữu của caller là gì?
3. **Viết normal postcondition:** thành công làm đổi điều gì?
4. **Viết exceptional postcondition:** nếu thất bại thì gì được giữ, gì có thể đổi?
5. **Chọn mức guarantee phù hợp:** basic, strong hay no-throw trong phạm vi cụ thể.
6. **Không hứa strong guarantee ngoài phạm vi có thể kiểm soát.**
7. **Validate trước mutation** khi có thể.
8. **Prepare dữ liệu vào local/immutable candidate**, commit sau cùng.
9. **Kiểm tra overflow và các phép có thể ném** trước khi gán.
10. **Không lộ mutable internal state** qua getter hoặc input alias.
11. **Xét callback/reentrancy** có thể quan sát trạng thái giữa chừng.
12. **Nếu có nhiều writer, thêm lock/CAS đúng phạm vi** thay vì chỉ `volatile` cho nhiều field.
13. **Nếu cho partial progress, ghi rõ** item nào có thể đã commit.
14. **Nếu có resource, xác định ownership và cleanup**, dùng try-with-resources khi phù hợp.
15. **Quan sát cause và suppressed** khi thao tác và cleanup cùng lỗi.
16. **Xem ghi file/network có thể partial**; đừng suy ra rollback khi IOException.
17. **Với transaction DB, xác định isolation, commit, rollback và trạng thái chưa rõ.**
18. **Với RPC có side effect, dùng idempotency/đối chiếu trạng thái** trước retry.
19. **Trạng thái FAILED/CLOSED/UNKNOWN có được định nghĩa rõ không?**
20. **Không bắt exception rồi trả thành công giả** nếu chưa phục hồi thật.
21. **Test đường lỗi tại mọi giai đoạn**: validation, prepare, write, notification, commit, close.
22. **Assert invariant và snapshot trước–sau**, không chỉ assert exception type.
23. **Kiểm tra tài nguyên và side effect ngoài**, không chỉ field Java.
24. **Viết JavaDoc về retry/reuse policy** sau exception.
25. **Đánh giá tính tương thích API** nếu thay đổi loại exception hoặc hậu điều kiện lỗi.

## 50. Kết luận

**Thiết kế API không kết thúc ở việc “phương thức ném exception nào”.** Một hợp đồng đáng tin phải định nghĩa **trạng thái hợp lệ trước khi gọi, trạng thái sau thành công, và trạng thái sau thất bại**.

Khi thất bại, có ba cách cam kết phổ biến: **basic guarantee** giữ invariant dù có partial progress; **strong guarantee** giữ nguyên trạng thái quan sát được trong phạm vi công bố; **no-throw guarantee** dành cho những thao tác thật sự có thể thiết kế không để exception thoát trong điều kiện hợp lệ. Java không tự kiểm chứng bất kỳ lời hứa nào trong ba mức này.

Để thực hiện, hãy ưu tiên **validate → prepare → commit**, dùng immutable snapshot/copy-then-swap khi thích hợp, kiểm tra overflow trước gán, quản lý tài nguyên bằng hợp đồng rõ và viết test thất bại ở từng bước. Đồng thời nhớ rằng **ghi I/O có thể partial, commit transaction có thể chưa rõ, và timeout từ hệ thống bên ngoài không chứng minh side effect chưa diễn ra**.

Câu hỏi quan trọng nhất để review mỗi API là:

> **“Nếu phương thức dừng bằng exception ngay tại bước này, caller có thể tin điều gì về trạng thái hiện tại và được phép làm gì tiếp?”**

Trả lời được câu hỏi đó bằng invariant, exceptional postcondition và test cụ thể là nền tảng của **API Java an toàn khi có lỗi**.
