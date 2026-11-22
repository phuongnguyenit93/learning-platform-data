# Kết hợp `sealed interface` với `record` trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** Thiết kế với `sealed`  
> **Mục tiêu:** Thiết kế một tập kiểu dữ liệu có số trường hợp được kiểm soát, biểu diễn từng trường hợp bằng `record`, xử lý chúng bằng cú pháp ổn định trong Java 17 và hiểu giới hạn của cách thiết kế này.

## 1. Bài toán: Một giá trị có nhiều dạng, nhưng mỗi dạng mang dữ liệu khác nhau

Giả sử hệ thống thanh toán phải trả về một trong hai kết quả:

- **Đã thanh toán:** có mã đơn hàng, số tiền và mã giao dịch.
- **Bị từ chối:** có mã đơn hàng và lý do từ chối.

Cả hai đều là *kết quả thanh toán*, nhưng dữ liệu đi kèm không giống nhau. Chúng ta muốn lưu trữ và truyền kết quả qua một kiểu chung, đồng thời không cho một lớp ở nơi bất kỳ tự ý thêm loại kết quả mới ngoài thiết kế.

Trong Java 17, có thể giải quyết bằng cách phối hợp hai đặc tính:

| Thành phần | Vai trò | Điều được đảm bảo |
|---|---|---|
| `sealed interface` | Khai báo **tập hợp những kiểu con trực tiếp được phép** | Chỉ các lớp/giao diện được cho phép mới có thể trực tiếp `implements` hoặc `extends` kiểu `sealed` |
| `record` | Biểu diễn **dữ liệu của từng trường hợp** | Tự sinh constructor chính tắc, accessor, `equals`, `hashCode`, `toString`; lớp record mặc nhiên là `final` |

Ví dụ ý tưởng:

```text
                  PaymentResult
              «sealed interface»
                      │
          ┌───────────┴───────────┐
          │                       │
    Paid (record)           Declined (record)
    - orderId               - orderId
    - amount                - reason
    - transactionId
```

Về mặt mô hình dữ liệu, đây là một **kiểu tổng** (*sum type* hoặc *tagged union*): một giá trị thuộc **một trong các biến thể**. Mỗi `record` lại mang một tập trường của riêng nó (kiểu tích, *product type*). Java không có từ khóa `sum type` riêng; `sealed interface` kết hợp `record` là cách biểu diễn rõ ràng và có kiểm soát.

## 2. Hai cấu phần cần nắm chắc trong Java 17

### 2.1. `sealed interface` kiểm soát những triển khai được phép

Khai báo:

```java
sealed interface PaymentResult permits Paid, Declined {
    String orderId();
}
```

Từ khóa `sealed` thông báo rằng `PaymentResult` **không phải** giao diện có thể được bất kỳ lớp nào triển khai trực tiếp. Mệnh đề `permits` liệt kê chính xác các kiểu con trực tiếp được phép: `Paid` và `Declined`.

Một kiểu **không xuất hiện trong danh sách** sẽ không thể tự ý triển khai `PaymentResult`:

```java
// Không hợp lệ nếu Pending không nằm trong `permits`.
record Pending(String orderId) implements PaymentResult { }
```

Trình biên dịch sẽ báo lỗi rằng `Pending` không phải kiểu con được cho phép của giao diện `sealed`.

Các quy tắc quan trọng của Java 17:

1. Một kiểu con trực tiếp của `sealed` phải được liệt kê trong `permits`, trừ trường hợp danh sách có thể được **suy ra** vì các kiểu con trực tiếp nằm trong cùng compilation unit.
2. Kiểu con trực tiếp được phép phải công bố rõ chính sách kế thừa tiếp: `final`, `sealed` hoặc `non-sealed`. `record` thỏa mãn quy tắc này vì **mặc nhiên là `final`**, không cần và không được viết thêm `final` như một yêu cầu bắt buộc.
3. Nếu các kiểu thuộc **named module**, những kiểu con được phép phải nằm **trong cùng module** với kiểu `sealed`. Nếu thuộc **unnamed module** (thường gặp khi biên dịch không có `module-info.java`), chúng phải thuộc **cùng package**. Quy tắc này làm cho danh sách các biến thể thực sự nằm trong một phạm vi kiểm soát được.
4. `permits` chỉ kiểm soát **kiểu con trực tiếp**. Nếu một kiểu con được phép khai báo `non-sealed`, nó có thể mở rộng lại cây kế thừa ở nhánh đó.

**Lưu ý về thuật ngữ:** `sealed` không đồng nghĩa “chỉ tạo được hai đối tượng”, mà nghĩa là “chỉ tồn tại các nhánh kế thừa trực tiếp đã công bố”. Có thể tạo hàng triệu đối tượng `Paid` và `Declined` khác nhau.

### 2.2. `record` mô tả dữ liệu của từng biến thể

Khai báo một record đơn giản:

```java
record Declined(String orderId, String reason) implements PaymentResult { }
```

Java tự tạo các thành phần tương đương về hành vi với:

```java
// Ví dụ sử dụng API mà record sinh ra; đây không phải mã cần tự viết.
Declined declined = new Declined("ORD-100", "Không đủ hạn mức");

String id = declined.orderId();    // Accessor: orderId()
String reason = declined.reason();  // Accessor: reason()
System.out.println(declined);      // toString()
```

Đặc điểm đáng nhớ của `record`:

- Các **thành phần record** (*record components*) như `orderId` và `reason` xác định trạng thái dữ liệu của record.
- Record có các trường dữ liệu thành viên tương ứng ở dạng **`private final`** và accessor công khai mang tên thành phần, ví dụ `orderId()`; không có getter JavaBean `getOrderId()` được tạo tự động.
- Constructor chính tắc (*canonical constructor*) khởi tạo các thành phần. Có thể tự viết để **kiểm tra hợp lệ** hoặc chuẩn hóa dữ liệu.
- `equals`/`hashCode` so sánh theo các thành phần record; `toString` mô tả tên kiểu cùng các thành phần. Điều này phù hợp với các đối tượng dữ liệu có ý nghĩa theo giá trị.
- Record mặc nhiên là **`final`**, kế thừa trực tiếp `java.lang.Record`, không thể tự `extends` một lớp khác; nhưng có thể `implements` một hoặc nhiều giao diện.

Do record vốn `final`, việc kết hợp với `sealed interface` rất tự nhiên: giao diện giới hạn tập biến thể, mỗi record cung cấp một biến thể lá với dữ liệu tương ứng.

### 2.3. Hai tính năng đều dùng ổn định trong Java 17

- `record` là tính năng chính thức từ **Java 16**.
- `sealed class`/`sealed interface` là tính năng chính thức từ **Java 17**.
- **Pattern matching cho `instanceof`** đã là tính năng chính thức từ Java 16 và sử dụng bình thường trong Java 17.

Vì vậy, những ví dụ dưới đây biên dịch trên **JDK 17** bằng lệnh thông thường, không dùng `--enable-preview`.

## 3. Ví dụ hoàn chỉnh: Kết quả thanh toán

Đặt toàn bộ mã sau vào file `PaymentDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class PaymentDemo {

    // Chỉ Paid hoặc Declined được trực tiếp implements PaymentResult.
    sealed interface PaymentResult permits Paid, Declined {
        String orderId();
    }

    // Record tự sinh orderId(), amount(), transactionId(),
    // equals(), hashCode() và toString().
    record Paid(String orderId,
                BigDecimal amount,
                String transactionId) implements PaymentResult {

        // Compact canonical constructor: kiểm tra invariant đầu vào.
        Paid {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(transactionId, "transactionId");

            if (orderId.isBlank() || transactionId.isBlank()) {
                throw new IllegalArgumentException("Mã không được để trống");
            }
            if (amount.signum() <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
        }
    }

    record Declined(String orderId,
                    String reason) implements PaymentResult {

        Declined {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(reason, "reason");

            if (orderId.isBlank() || reason.isBlank()) {
                throw new IllegalArgumentException("Nội dung không được để trống");
            }
        }
    }

    static String describe(PaymentResult result) {
        Objects.requireNonNull(result, "result");

        // Pattern matching cho instanceof là tính năng chính thức trong Java 17.
        if (result instanceof Paid paid) {
            return "Đơn " + paid.orderId()
                    + " đã thanh toán " + paid.amount()
                    + ", giao dịch " + paid.transactionId();
        }

        if (result instanceof Declined declined) {
            return "Đơn " + declined.orderId()
                    + " bị từ chối: " + declined.reason();
        }

        // Java 17 không tự kiểm tra exhaustiveness cho chuỗi if/instanceof.
        throw new IllegalStateException(
                "Biến thể chưa xử lý: " + result.getClass().getName());
    }

    public static void main(String[] args) {
        PaymentResult first = new Paid(
                "ORD-100",
                new BigDecimal("125000"),
                "TXN-88");

        PaymentResult second = new Declined(
                "ORD-101",
                "Không đủ hạn mức");

        System.out.println(describe(first));
        System.out.println(describe(second));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 PaymentDemo.java
java PaymentDemo
```

Kết quả dự kiến:

```text
Đơn ORD-100 đã thanh toán 125000, giao dịch TXN-88
Đơn ORD-101 bị từ chối: Không đủ hạn mức
```

**Điều cần quan sát:**

1. Biến `first` và `second` cùng có kiểu khai báo `PaymentResult`, nhưng giữ các record khác nhau tại runtime.
2. `PaymentResult` có một hợp đồng chung `orderId()`; mỗi record tự động cung cấp phương thức đúng tên nhờ component `orderId`.
3. Kiểu `Paid` chỉ chứa dữ liệu hợp lý cho thanh toán thành công; kiểu `Declined` chỉ chứa dữ liệu của trường hợp bị từ chối. Không cần tạo một lớp chứa nhiều trường tùy chọn như `amount`, `transactionId`, `reason` rồi kiểm tra các tổ hợp `null` khó kiểm soát.
4. Khi vào `if (result instanceof Paid paid)`, Java đã suy ra `paid` là `Paid`. Không cần ép kiểu `(Paid) result` thủ công.
5. Cả hai record được cho phép trực tiếp nhờ `permits`; record thứ ba sẽ bị trình biên dịch từ chối nếu chưa được thêm vào danh sách.

Trong ví dụ một file, các kiểu con `PaymentResult`, `Paid` và `Declined` đều là kiểu lồng trong `PaymentDemo`. Record lồng là kiểu **tĩnh** (*implicitly static*), nên không cần tạo đối tượng `PaymentDemo` để khởi tạo chúng.

## 4. Vì sao cách này tốt hơn một lớp với nhiều trường tùy chọn?

Một cách mô hình hóa ít chặt chẽ là tạo đối tượng như sau:

```java
// Ví dụ về mô hình dễ tạo trạng thái mâu thuẫn.
class PaymentResponse {
    boolean success;
    String orderId;
    BigDecimal amount;        // Chỉ có ý nghĩa khi success = true
    String transactionId;     // Chỉ có ý nghĩa khi success = true
    String failureReason;     // Chỉ có ý nghĩa khi success = false
}
```

Thiết kế đó cho phép một đối tượng có `success = true` nhưng `failureReason` khác `null`, hoặc `success = false` nhưng vẫn có mã giao dịch. Mã sử dụng phải tự kiểm tra nhiều điều kiện kết hợp.

Khi thay bằng `sealed interface PaymentResult` cùng hai record `Paid`/`Declined`, cấu trúc kiểu dữ liệu diễn đạt rõ sự khác biệt:

| Tiêu chí | Một lớp có nhiều trường tùy chọn | `sealed interface` + `record` |
|---|---|---|
| Tập trường hợp hợp lệ | Thường kiểm tra bằng cờ và điều kiện runtime | Được thể hiện bằng các kiểu con được phép |
| Dữ liệu của từng trường hợp | Có nhiều trường không liên quan, thường mang `null` | Mỗi record chỉ công bố các thành phần cần thiết |
| Tạo thêm loại kết quả | Có thể xuất hiện bằng cách thêm giá trị cờ hoặc string | Cần chỉnh sửa khai báo `permits` có kiểm soát |
| Tính bất biến của dữ liệu | Phải tự cài đặt | Record tự có trường thành viên `final`, kèm lưu ý *shallow immutability* |
| `equals`/`hashCode`/`toString` | Thường tự viết hoặc dùng thư viện | Được record sinh tự động |

Đây là lựa chọn hữu ích khi **tập biến thể được biết trước và có ý nghĩa nghiệp vụ rõ ràng**: trạng thái xử lý, sự kiện hệ thống, kết quả tính toán, lệnh, biểu thức cú pháp hoặc thông điệp nội bộ.

## 5. Viết và sử dụng các record của sealed interface trong dự án nhiều file

Với chương trình thực tế, thường đặt mỗi kiểu công khai vào một file riêng, cùng package hoặc cùng named module theo quy tắc Java 17.

```text
src/main/java/com/example/payment/
    PaymentResult.java
    Paid.java
    Declined.java
```

`PaymentResult.java`:

```java
package com.example.payment;

public sealed interface PaymentResult permits Paid, Declined {
    String orderId();
}
```

`Paid.java`:

```java
package com.example.payment;

import java.math.BigDecimal;

public record Paid(String orderId, BigDecimal amount, String transactionId)
        implements PaymentResult { }
```

`Declined.java`:

```java
package com.example.payment;

public record Declined(String orderId, String reason)
        implements PaymentResult { }
```

Về mặt cấu trúc, ba file này tạo ra đúng các quan hệ kiểu như ví dụ một file trước đó. Để dùng vào production, hãy bổ sung kiểm tra dữ liệu đầu vào và các quy ước nullability/serialization của dự án, chẳng hạn như compact constructor đã minh họa.

Ví dụ mã sử dụng từ package khác:

```java
import com.example.payment.Declined;
import com.example.payment.Paid;
import com.example.payment.PaymentResult;
import java.math.BigDecimal;

class Example {
    public static void main(String[] args) {
        PaymentResult response = new Paid(
                "ORD-100", new BigDecimal("100"), "TXN-1");
        System.out.println(response.orderId());

        if (response instanceof Paid paid) {
            System.out.println(paid.transactionId());
        } else if (response instanceof Declined declined) {
            System.out.println(declined.reason());
        }
    }
}
```

Không thể tạo `record` công khai mới trong một package/module không được phép và cho nó trực tiếp `implements PaymentResult` nếu kiểu đó không có trong danh sách `permits`.

### Khi nào có thể bỏ `permits`?

Java 17 cho phép suy ra danh sách kiểu con trực tiếp khi chúng được khai báo **trong cùng compilation unit**. Ví dụ một file `Message.java`:

```java
sealed interface Message { }

record TextMessage(String text) implements Message { }

record NumberMessage(int number) implements Message { }
```

Ở đây trình biên dịch suy ra `TextMessage` và `NumberMessage` là các trường hợp được phép. Tuy nhiên, khi tách thành nhiều file thì nên khai báo `permits` rõ ràng. Với API cho nhóm phát triển hoặc thư viện dùng lâu dài, danh sách tường minh còn giúp người đọc thấy ngay toàn bộ các biến thể.

## 6. Quy tắc `final`, `sealed`, `non-sealed`: Record phù hợp ở nhánh nào?

Một sealed hierarchy có thể chứa cả class, interface và record. Giả sử:

```java
sealed interface Event permits Created, Retried, SystemEvent { }

record Created(String id) implements Event { }

record Retried(String id, int count) implements Event { }

non-sealed class SystemEvent implements Event { }
```

- `Created` và `Retried` là các nhánh cuối vì record mặc nhiên `final`.
- `SystemEvent` được đánh dấu `non-sealed`, cho phép kiểu khác kế thừa lớp này theo quy tắc kế thừa thông thường.
- Điều kiện giới hạn được kiểm soát tại các kiểu con **trực tiếp** của `Event`, chứ không khép kín mọi hậu duệ nếu đã mở một nhánh `non-sealed`.

Trong mô hình các trường hợp dữ liệu đóng kín, **ưu tiên record cho các nhánh lá**, và cân nhắc kỹ trước khi thêm `non-sealed`: một nhánh mở sẽ khiến tập kiểu runtime thực tế không còn chỉ gồm những lớp cụ thể được liệt kê trên `permits`.

Nếu một trường hợp cần cho phép nhiều kiểu con có kiểm soát, có thể khai báo một `sealed interface` trung gian:

```java
sealed interface Command permits UserCommand, Shutdown { }

sealed interface UserCommand extends Command permits CreateUser, DeleteUser { }

record CreateUser(String name) implements UserCommand { }
record DeleteUser(long id) implements UserCommand { }
record Shutdown() implements Command { }
```

Trong hệ này, `UserCommand` đóng vai trò nhánh trung gian vẫn được niêm phong, còn `CreateUser`, `DeleteUser`, `Shutdown` là các record cuối.

**Quy tắc thiết kế:** `record` không được `extends` class bất kỳ ngoài `java.lang.Record`; do đó không thể dùng `record` làm lớp cơ sở trong một cây kế thừa lớp. Để phân nhóm record, hãy dùng **interface**, bao gồm `sealed interface` nếu muốn cố định tập biến thể.

## 7. Xử lý các biến thể bằng Java 17

### 7.1. `instanceof` pattern matching

Java 17 hỗ trợ trực tiếp:

```java
static void printResult(PaymentResult result) {
    if (result instanceof Paid paid) {
        System.out.println("Giao dịch: " + paid.transactionId());
    } else if (result instanceof Declined declined) {
        System.out.println("Lý do: " + declined.reason());
    } else {
        throw new IllegalStateException("Trường hợp chưa xử lý");
    }
}
```

Biến pattern `paid`/`declined` chỉ được sử dụng trong vùng mà Java biết phép kiểm tra `instanceof` thành công. Đây là **type pattern**, không phải record pattern. Với Java 17, phải gọi `paid.transactionId()` để lấy thành phần của record; cú pháp bóc tách nhiều component bằng record pattern thuộc các phiên bản Java mới hơn.

### 7.2. Tránh dùng cú pháp `switch` của Java mới hơn

Ví dụ sau thường xuất hiện trong tài liệu Java hiện đại:

```java
// KHÔNG dùng như cú pháp Java 17 ổn định:
// return switch (result) {
//     case Paid paid -> paid.transactionId();
//     case Declined declined -> declined.reason();
// };
```

**Trong Java 17, pattern matching cho `switch` vẫn là tính năng *preview*** (JEP 406), cần các cờ preview phù hợp và không phải API/cú pháp ổn định để xây dựng bài học Java 17 phổ thông. `switch` theo pattern trở thành tính năng chính thức ở **Java 21** (JEP 441); record patterns cũng được hoàn thiện ở **Java 21** (JEP 440). Đừng sao chép code dành cho Java 21 rồi kỳ vọng `javac --release 17` biên dịch được.

Vì vậy, nếu dự án **đang biên dịch theo Java 17**, sử dụng `if`/`else if` với `instanceof` pattern hoặc đa hình bằng phương thức trên interface.

### 7.3. Đa hình: Đưa hành vi chung vào interface

Khi logic xử lý thuộc về từng biến thể, có thể định nghĩa phương thức chung trên `sealed interface`, để mỗi record cung cấp cách triển khai riêng:

```java
public class DisplayDemo {
    sealed interface Notification permits Info, Warning {
        String displayText();
    }

    record Info(String message) implements Notification {
        @Override
        public String displayText() {
            return "[INFO] " + message;
        }
    }

    record Warning(String message, int severity) implements Notification {
        @Override
        public String displayText() {
            return "[WARNING " + severity + "] " + message;
        }
    }

    static void show(Notification notification) {
        System.out.println(notification.displayText());
    }

    public static void main(String[] args) {
        show(new Info("Đã lưu"));
        show(new Warning("Cần kiểm tra lại", 2));
    }
}
```

Lợi ích: không phải lặp chuỗi `instanceof` ở nhiều nơi. Việc thêm biến thể mới sẽ buộc record mới thực hiện phương thức `displayText()` theo hợp đồng, giúp trình biên dịch phát hiện thiếu phương thức triển khai.

**Nên chọn cách nào?** Nếu xử lý là một phần trách nhiệm tự nhiên của đối tượng (ví dụ `displayText`, `amount`, `isRetryable`), đa hình thường gọn hơn. Nếu xử lý ở lớp bên ngoài (chuyển sang DTO, xuất JSON, mapping cơ sở dữ liệu, vẽ UI), `instanceof` ở một điểm tập trung có thể hợp lý. Tránh rải nhiều chuỗi `instanceof` qua toàn bộ ứng dụng.

### 7.4. Tính đầy đủ của các nhánh xử lý

Điều quan trọng cần nhớ: dù Java 17 biết `PaymentResult` chỉ cho phép `Paid` và `Declined` trực tiếp, **trình biên dịch không xác nhận chuỗi `if`/`else if` đã xử lý đủ các nhánh**. Nếu sau này thêm record `Pending` vào `permits`, code `if` cũ có thể vẫn biên dịch nhưng đi vào nhánh mặc định khi nhận `Pending`.

Các biện pháp thực tế trong Java 17:

- Đặt logic phân nhánh ở một số ít hàm/điểm chuyển đổi rõ ràng.
- Có nhánh mặc định ném ngoại lệ được đặt tên cụ thể hoặc quy tắc fallback có chủ đích.
- Cập nhật các hàm xử lý khi danh sách `permits` thay đổi và bổ sung kiểm thử cho biến thể mới trong **quy trình phát triển ứng dụng**.
- Dùng đa hình cho hành vi có thể đưa vào hợp đồng chung để trình biên dịch buộc các record mới triển khai.

Không nên quảng bá tính kiểm tra *exhaustiveness* của pattern `switch` ở Java 21 như một bảo đảm mặc định cho Java 17.

## 8. Tạo record bất biến đúng nghĩa cho dữ liệu nghiệp vụ

### 8.1. `record` bất biến ở mức tham chiếu, không tự làm bất biến mọi đối tượng bên trong

Record đảm bảo các trường trạng thái tương ứng component là `final`, nhưng **không deep-copy dữ liệu tham chiếu**. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

record Batch(List<String> ids) { }

class Example {
    public static void main(String[] args) {
        List<String> list = new ArrayList<>();
        list.add("ORD-1");

        Batch batch = new Batch(list);
        list.add("ORD-2");

        System.out.println(batch.ids()); // [ORD-1, ORD-2]
    }
}
```

Giá trị tham chiếu `ids` không thể gán lại sau khi record được tạo, nhưng danh sách gốc vẫn có thể đổi. Khi một record mang ý nghĩa snapshot hoặc value object, hãy sao chép bất biến dữ liệu có thể thay đổi:

```java
import java.util.List;
import java.util.Objects;

record Batch(List<String> ids) {
    Batch {
        Objects.requireNonNull(ids, "ids");
        ids = List.copyOf(ids);
    }
}
```

Trong **compact constructor**, phép gán `ids = List.copyOf(ids)` chuẩn hóa tham số constructor; Java sẽ tự gán giá trị đó cho trường record sau khi hoàn thành phần thân constructor. Không tự viết `this.ids = ...` trong compact constructor.

`List.copyOf` tạo danh sách không thể thay đổi cấu trúc và từ chối phần tử `null`, nhưng nếu phần tử là các đối tượng mutable thì vẫn cần chiến lược sao chép sâu/kiểu phần tử bất biến phù hợp. Tương tự, đối với `byte[]`, `Date` kiểu mutable hoặc map/list lồng nhau, cần xem xét sao chép khi nhận vào **và** khi trả ra từ accessor nếu muốn bất biến sâu.

### 8.2. Constructor của từng biến thể là nơi giữ invariant

```java
import java.math.BigDecimal;
import java.util.Objects;

sealed interface PriceResult permits ValidPrice, InvalidPrice { }

record ValidPrice(BigDecimal value) implements PriceResult {
    ValidPrice {
        Objects.requireNonNull(value, "value");
        if (value.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
    }
}

record InvalidPrice(String errorCode) implements PriceResult {
    InvalidPrice {
        Objects.requireNonNull(errorCode, "errorCode");
        if (errorCode.isBlank()) {
            throw new IllegalArgumentException("Mã lỗi không được trống");
        }
    }
}
```

`sealed` bảo vệ **hình dạng tập biến thể**; constructor của `record` bảo vệ **giá trị hợp lệ của từng biến thể**. Đây là hai lớp bảo đảm khác nhau và cần dùng cùng nhau.

Lưu ý thêm: `equals` mặc định của record phụ thuộc vào `equals` của các component tham chiếu. Ví dụ hai `BigDecimal("10.0")` và `BigDecimal("10.00")` không bằng nhau theo `BigDecimal.equals` vì khác scale. Nếu nghiệp vụ muốn coi hai giá trị là tương đương, hãy quy định cách chuẩn hóa component rõ ràng ở ranh giới dữ liệu thay vì mặc định record đã giải quyết tính bằng nhau theo nghiệp vụ.

## 9. Thiết kế generic: Kết quả thành công hoặc lỗi

Không nhất thiết phải gắn `sealed interface` với một nghiệp vụ cố định. Một mô hình dùng lại phổ biến là `Result<T>`:

```java
import java.util.Objects;

public class GenericResultDemo {

    sealed interface Result<T> permits Success, Failure { }

    record Success<T>(T value) implements Result<T> {
        Success {
            Objects.requireNonNull(value, "value");
        }
    }

    record Failure<T>(String code, String message) implements Result<T> {
        Failure {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
        }
    }

    static Result<String> loadUsername(int userId) {
        if (userId == 1) {
            return new Success<>("Minh");
        }
        return new Failure<>("NOT_FOUND", "Không tìm thấy người dùng");
    }

    static void print(Result<String> result) {
        if (result instanceof Success<?> success) {
            System.out.println("Tên: " + success.value());
        } else if (result instanceof Failure<?> failure) {
            System.out.println(failure.code() + ": " + failure.message());
        } else {
            throw new IllegalStateException("Result chưa được xử lý");
        }
    }

    public static void main(String[] args) {
        print(loadUsername(1));
        print(loadUsername(99));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 GenericResultDemo.java
java GenericResultDemo
```

Kết quả:

```text
Tên: Minh
NOT_FOUND: Không tìm thấy người dùng
```

Ở đây `Success<T>` giữ giá trị thành công có kiểu `T`, còn `Failure<T>` mang dữ liệu lỗi nhưng vẫn thực hiện `Result<T>` để trả về từ cùng phương thức. Khi dùng `instanceof Success<?>`, biểu thức `success.value()` có kiểu `Object` do xóa kiểu generic tại runtime; Java 17 không cho phép kiểm tra `instanceof Success<String>` vì tham số generic không được giữ đầy đủ tại runtime. Nếu cần trả về `T` chính xác, có thể thiết kế phương thức phân nhánh hoặc API xử lý generic rõ ràng, tránh cast không kiểm soát.

Trong ứng dụng thực tế, `Result<T>` có thể bổ sung cách chuyển đổi, xử lý lỗi hoặc cấu trúc lỗi chuẩn, nhưng nên cân nhắc phạm vi: không cần bọc mọi phương thức đơn giản vào `Result` nếu exception hoặc kiểu trả về thông thường đã diễn đạt hợp lý.

## 10. Mô hình đệ quy: Cây biểu thức với `sealed interface` và `record`

Một ứng dụng khác là cây biểu thức toán học. Mỗi nút thuộc một trong hai dạng: số nguyên hoặc phép cộng hai biểu thức con.

```java
public class ExpressionDemo {

    sealed interface Expr permits NumberExpr, Add { }

    record NumberExpr(int value) implements Expr { }

    record Add(Expr left, Expr right) implements Expr {
        Add {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }
    }

    static int evaluate(Expr expr) {
        if (expr instanceof NumberExpr number) {
            return number.value();
        }
        if (expr instanceof Add add) {
            return Math.addExact(
                    evaluate(add.left()),
                    evaluate(add.right()));
        }
        throw new IllegalStateException("Kiểu biểu thức chưa xử lý");
    }

    public static void main(String[] args) {
        Expr expression = new Add(
                new NumberExpr(2),
                new Add(new NumberExpr(3), new NumberExpr(4)));

        System.out.println(evaluate(expression)); // 9
    }
}
```

Điểm thú vị là `sealed interface` giới hạn **loại nút** (`NumberExpr`, `Add`), nhưng **không giới hạn số nút** có thể tạo hoặc độ sâu của cây. Vì `record Add` có hai component kiểu `Expr`, mọi biểu thức con tiếp tục tuân theo cùng mô hình.

`Math.addExact` làm phép cộng báo `ArithmeticException` nếu tràn số nguyên; ví dụ chọn cách này để không âm thầm bỏ qua overflow. Với các bài toán khác, có thể dùng `long` hoặc `BigInteger` nếu yêu cầu miền giá trị lớn.

## 11. Khi nào nên và không nên áp dụng?

### Nên dùng khi

- Miền nghiệp vụ có một **số biến thể xác định rõ** và dự kiến thay đổi có kiểm soát: `Accepted`/`Rejected`, `Pending`/`Completed`/`Failed`, nhóm sự kiện hoặc lệnh.
- Mỗi biến thể được diễn đạt chủ yếu bằng **dữ liệu** và có vài invariant kiểm tra qua constructor.
- Muốn API công bố tập kiểu được phép, tránh các implementation tùy ý từ bên ngoài.
- Muốn giảm boilerplate của đối tượng dữ liệu, nhận `equals`/`hashCode`/`toString` thống nhất.

### Cân nhắc cách khác khi

- **Chỉ cần tập hằng số không có dữ liệu riêng theo từng trường hợp:** `enum` thường đơn giản hơn, ví dụ `enum ConnectionState { NEW, OPEN, CLOSED }`.
- **Yêu cầu người dùng thư viện tự bổ sung implementation:** một `interface` thông thường có thể phù hợp hơn vì `sealed` cố ý hạn chế phần mở rộng.
- **Đối tượng có trạng thái thay đổi liên tục**, vòng đời, kế thừa class hoặc identity riêng: class thông thường hoặc aggregate thiết kế theo nghiệp vụ có thể phù hợp hơn `record`.
- **Dữ liệu đến từ JSON/API/database:** sealed/record vẫn có thể sử dụng, nhưng cần xác định cách thư viện serialization phân biệt các biến thể, xử lý trường thiếu, versioning và constructor. Đừng giả định serializer nào cũng tự hiểu `sealed interface`.

`sealed interface` biểu diễn *đóng tập kiểu*, còn `record` là mô hình dữ liệu có danh tính theo giá trị. Hãy dùng cả hai khi hai đặc tính đó khớp với yêu cầu thật của domain.

## 12. Các lỗi dễ gặp khi kết hợp `sealed interface` và `record`

| Lỗi hoặc hiểu nhầm | Tại sao sai | Cách xử lý trong Java 17 |
|---|---|---|
| `record C(...) implements X` khi `C` không có trong `X permits` | Một kiểu không được phép triển khai trực tiếp giao diện sealed | Thêm `C` vào `permits` sau khi có chủ đích mở rộng mô hình |
| Tạo implementation ở package/module không hợp lệ | Java 17 giới hạn vị trí subtype được phép: cùng module được đặt tên hoặc cùng package trong unnamed module | Đặt các kiểu vào cấu trúc module/package hợp lệ |
| `record` cố `extends SomeBaseClass` | Record đã kế thừa `java.lang.Record`, không được kế thừa class tùy ý | Dùng `implements` interface; thiết kế lại cây kiểu |
| Cho rằng mọi thành phần của record đều deep immutable | `final` giữ tham chiếu, không đóng băng List/Map/array được tham chiếu | Sao chép phòng vệ và dùng kiểu thành phần bất biến |
| Dùng `getOrderId()` như accessor record mặc định | Accessor record là `orderId()` | Dùng `orderId()` hoặc chủ động định nghĩa API bổ sung nếu cần |
| Viết `case Paid paid ->` trong `switch` với `--release 17` | Pattern switch chưa ổn định ở Java 17 | Dùng `instanceof` pattern hoặc phương thức đa hình |
| Viết cú pháp record pattern như `instanceof Paid(var id, var amount, var tx)` | Record patterns không thuộc Java 17 ổn định | Dùng `instanceof Paid paid` và gọi các accessor |
| Tin rằng `if/else if` đã được kiểm tra đủ các biến thể | Java 17 không kiểm tra exhaustiveness của chuỗi `if` | Tập trung xử lý, có fallback rõ ràng, cập nhật test khi thêm biến thể |
| Dùng `non-sealed` rồi giả định chỉ có các record trong `permits` xuất hiện ở runtime | Nhánh `non-sealed` có thể được mở rộng bằng subtype khác | Chỉ mở nhánh khi đó là chủ đích; ưu tiên record lá cho mô hình đóng kín |
| Dùng `record` có `BigDecimal`, array hoặc thành phần mutable mà mặc định equality đúng theo nghiệp vụ | `equals` record theo component, không tự chuẩn hóa giá trị và không deep-compare mọi cấu trúc | Chọn component phù hợp và định nghĩa chuẩn hóa/đồng nhất dữ liệu |

## 13. Bài tập thực hành

### Bài 1 — Quản lý trạng thái tác vụ

Thiết kế kiểu `TaskState` với đúng ba biến thể:

1. `Queued(String taskId, long createdAt)`.
2. `Running(String taskId, int percent)`; `percent` phải từ `0` đến `100`.
3. `Completed(String taskId, String outputPath)`.

Yêu cầu: tạo `sealed interface TaskState` khai báo `taskId()`, viết các `record` tương ứng và dùng `instanceof` pattern để tạo thông báo trạng thái. Không dùng pattern matching cho `switch`.

<details>
<summary>Gợi ý đáp án Java 17</summary>

```java
public class TaskStateDemo {
    sealed interface TaskState permits Queued, Running, Completed {
        String taskId();
    }

    record Queued(String taskId, long createdAt) implements TaskState { }

    record Running(String taskId, int percent) implements TaskState {
        Running {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException("percent phải trong [0, 100]");
            }
        }
    }

    record Completed(String taskId, String outputPath) implements TaskState { }

    static String summary(TaskState state) {
        if (state instanceof Queued queued) {
            return queued.taskId() + " đang chờ từ " + queued.createdAt();
        }
        if (state instanceof Running running) {
            return running.taskId() + " đang chạy: " + running.percent() + "%";
        }
        if (state instanceof Completed completed) {
            return completed.taskId() + " xong: " + completed.outputPath();
        }
        throw new IllegalStateException("Trạng thái không được hỗ trợ");
    }

    public static void main(String[] args) {
        System.out.println(summary(new Running("TASK-1", 60)));
    }
}
```

</details>

### Bài 2 — Giải thích việc mở rộng biến thể

Từ ví dụ thanh toán, hệ thống xuất hiện trường hợp thứ ba: `Pending(String orderId, String pendingReason)`.

- Vì sao `record Pending(...) implements PaymentResult` không biên dịch ngay khi khai báo?
- Cần sửa thành phần nào của sealed hierarchy?
- Sau khi mở rộng `permits`, phương thức `describe` có được trình biên dịch Java 17 nhắc bổ sung nhánh xử lý mới không?

**Đáp án định hướng:** Thêm `Pending` vào danh sách `PaymentResult permits Paid, Declined, Pending`, khai báo record trực tiếp `implements PaymentResult` trong phạm vi package/module hợp lệ, rồi bổ sung nhánh `instanceof Pending pending` vào `describe`. Java 17 không tự yêu cầu cập nhật chuỗi `if`; nếu bỏ sót, chương trình có thể đi vào nhánh `IllegalStateException` tại runtime.

### Bài 3 — Bảo vệ trạng thái bất biến

Tạo `record BatchResult(List<PaymentResult> items)`. Hãy giải thích vì sao `items` có thể bị thay đổi từ bên ngoài sau khi record được tạo và sửa bằng `List.copyOf(items)` trong compact canonical constructor. Sau đó thử truyền `null` hoặc phần tử `null` để quan sát cách `List.copyOf` từ chối dữ liệu.

## 14. Tóm lược và tài liệu tra cứu

Trong Java 17, `sealed interface` dùng để **giới hạn các biến thể**, còn `record` mô tả **dữ liệu của từng biến thể** với ít mã lặp. Các record được phép trực tiếp triển khai sealed interface mà không cần khai báo thêm `final`, vì record đã mặc nhiên là lớp cuối. Kiểm tra hợp lệ bằng compact canonical constructor, xử lý bằng `instanceof` pattern hoặc đa hình và chú ý rằng `record` chỉ bất biến nông nếu chứa tham chiếu đến dữ liệu mutable.

Các nguồn chính thức để tra cứu phiên bản Java 17:

- [JEP 409 — Sealed Classes (finalized in JDK 17)](https://openjdk.org/jeps/409): động cơ thiết kế, `sealed`, `permits`, `final`/`sealed`/`non-sealed`.
- [JEP 395 — Records (finalized in JDK 16)](https://openjdk.org/jeps/395): record components, constructor và tính chất của record.
- [JEP 394 — Pattern Matching for `instanceof` (finalized in JDK 16)](https://openjdk.org/jeps/394): cú pháp `instanceof Type variable` dùng trong Java 17.
- [Java Language Specification 17 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10), [§9.1.1.4 Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): quy tắc ngôn ngữ cụ thể ở Java 17.
- [JEP 406 — Pattern Matching for `switch` (Preview in JDK 17)](https://openjdk.org/jeps/406), [JEP 441 — Pattern Matching for `switch` (finalized in JDK 21)](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns (finalized in JDK 21)](https://openjdk.org/jeps/440): nhận biết cú pháp của các phiên bản mới hơn để không dùng nhầm trong dự án Java 17.

**Điều cần ghi nhớ khi thực hành:** cố định các trường hợp bằng `sealed interface`, mô hình hóa mỗi trường hợp thành `record`, giữ dữ liệu hợp lệ ngay khi khởi tạo và xử lý đủ từng biến thể bằng cú pháp mà JDK 17 hỗ trợ ổn định.
