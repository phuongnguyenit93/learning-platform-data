# Bài toán giới hạn các kiểu con trong một miền dữ liệu

## 1. Vấn đề: miền dữ liệu chỉ có một số trường hợp hợp lệ

Giả sử hệ thống thanh toán cần biểu diễn **kết quả xử lý một giao dịch**. Theo nghiệp vụ hiện tại, một lần xử lý chỉ có thể tạo ra một trong ba kết quả:

1. **Chấp nhận (Approved):** giao dịch hoàn tất, có mã giao dịch và số tiền.
2. **Từ chối (Declined):** không thực hiện được, có lý do cụ thể.
3. **Chờ xác minh (PendingVerification):** khách hàng cần hoàn tất bước xác minh, có mã yêu cầu để theo dõi.

Ba kết quả có **dữ liệu đi kèm khác nhau**, nhưng đều có thể được truyền qua cùng một kiểu trừu tượng `PaymentResult`. Đây là mô hình thường gặp trong những miền dữ liệu có số trường hợp được định nghĩa chặt chẽ: kết quả đăng nhập, trạng thái phê duyệt, loại lệnh trong bộ xử lý, kết quả phân tích cú pháp, phản hồi từ nghiệp vụ đặt hàng.

Điều quan trọng là quy tắc sau:

> Mọi đối tượng được chấp nhận làm `PaymentResult` phải thuộc một trong các trường hợp do miền nghiệp vụ cho phép.

Nếu chỉ viết một `interface` thông thường, Java cho phép những lớp khác triển khai interface đó, kể cả khi người thiết kế không chủ động liệt kê chúng. Quy tắc "chỉ có ba trường hợp" khi ấy tồn tại trong tài liệu và thỏa thuận giữa các lập trình viên, nhưng **không được trình biên dịch bảo vệ**.

Java 17 có thể diễn đạt quy tắc này bằng **sealed class** hoặc **sealed interface**. Tính năng sealed được chuẩn hóa trong Java 17 (JEP 409). Bài học này đi từ nhu cầu giới hạn kiểu con trong miền dữ liệu, đến cách dùng sealed cho đúng và nhận biết các giới hạn của nó.

## 2. Mô hình mở: vì sao interface thông thường chưa đủ?

Xét khai báo:

```java
public interface PaymentResult {
}
```

Ba kiểu đã thống nhất:

```java
public record Approved(String transactionId) implements PaymentResult {
}

public record Declined(String reason) implements PaymentResult {
}

public record PendingVerification(String requestId) implements PaymentResult {
}
```

Về mặt cú pháp, người khác vẫn có thể viết thêm:

```java
public record UnknownResult(String payload) implements PaymentResult {
}
```

Các đoạn mã trên minh họa các khai báo ở **những file riêng** (hoặc có thể đặt trong các kiểu lồng nhau phù hợp). Nếu `PaymentResult` là interface công khai, `UnknownResult` hoàn toàn có thể triển khai nó dù không nằm trong ba trường hợp nghiệp vụ đã định. Khi một phần khác của hệ thống nhận `PaymentResult`, phần đó có thể gặp kiểu lạ và phải đoán nên xử lý thế nào.

Ví dụ:

```java
static String describe(PaymentResult result) {
    if (result instanceof Approved approved) {
        return "Thành công: " + approved.transactionId();
    }
    if (result instanceof Declined declined) {
        return "Từ chối: " + declined.reason();
    }
    if (result instanceof PendingVerification pending) {
        return "Cần xác minh: " + pending.requestId();
    }
    return "Kết quả không xác định";
}
```

Nhánh cuối buộc ứng dụng đối mặt với khả năng có thêm kiểu triển khai. Trong một miền thực sự chỉ cho phép ba trường hợp, đây là một khoảng trống giữa **quy tắc nghiệp vụ** và **hợp đồng kiểu dữ liệu**.

Một cách sửa tạm như kiểm tra tên class bằng chuỗi, bắt đầu từ `Object`, hoặc để tất cả trường trong một đối tượng có thể `null` thường khiến mã khó duy trì hơn. Ta cần khai báo trực tiếp tập kiểu hợp lệ.

## 3. Sealed interface: biến quy tắc nghiệp vụ thành ràng buộc của Java

Trong Java 17, cú pháp:

```java
public sealed interface PaymentResult
        permits Approved, Declined, PendingVerification {
}
```

có nghĩa là `PaymentResult` **chỉ cho phép ba kiểu được nêu trong `permits` kế thừa/triển khai trực tiếp**.

Các kiểu được phép:

```java
public record Approved(String transactionId) implements PaymentResult {
}

public record Declined(String reason) implements PaymentResult {
}

public record PendingVerification(String requestId) implements PaymentResult {
}
```

Với các khai báo đặt đúng quan hệ package/module của Java, đây là một mô hình hợp lệ. `record` vốn là kiểu `final`, vì thế đáp ứng yêu cầu của một kiểu triển khai trực tiếp sealed interface.

Nếu ai đó cố triển khai một trường hợp khác:

```java
// Ví dụ cố tình KHÔNG hợp lệ:
public record UnknownResult(String payload) implements PaymentResult {
}
```

trình biên dịch sẽ từ chối vì `UnknownResult` **không được liệt kê trong `permits`**. Lỗi xuất hiện ngay khi biên dịch, trước khi hệ thống phải xử lý một đối tượng không mong đợi ở runtime.

Sơ đồ mô hình:

```text
PaymentResult  («sealed interface»)
│
├── Approved               («record», final)
│   └── transactionId
│
├── Declined               («record», final)
│   └── reason
│
└── PendingVerification    («record», final)
    └── requestId
```

Quy tắc miền dữ liệu được nhìn thấy trực tiếp qua sơ đồ: một `PaymentResult` có thể thuộc ba nhánh được cho phép. Việc chọn record trong ví dụ là quyết định phù hợp với các **kết quả dữ liệu bất biến ở cấp tham chiếu thành phần**, còn quyền giới hạn các nhánh đến từ `sealed`.

### 3.1. `sealed` thực sự bảo đảm điều gì?

Khi khai báo đúng, sealed giúp:

- **Kiểm soát kế thừa trực tiếp:** chỉ các kiểu nằm trong danh sách được cấp phép mới có thể `extends`/`implements` sealed type.
- **Diễn đạt tập trường hợp được biết trước:** tên các nhánh là một phần của hợp đồng kiểu dữ liệu.
- **Ngăn triển khai tự phát ở compile time:** thay vì phát hiện khi một giao dịch đã chạy đến nhánh xử lý không xác định.
- **Hỗ trợ người đọc mã:** lập trình viên biết chỗ cần tìm để hiểu phạm vi của miền.
- **Tạo nền tảng cho công cụ và tính năng ngôn ngữ sau này:** các phiên bản Java mới hơn có thể dùng pattern matching trong switch để khai thác thông tin tập con đã đóng. Cần phân biệt khả năng đó với Java 17.

Sealed **không tự động** kiểm tra mọi quy tắc nghiệp vụ. Nó không chứng minh rằng `transactionId` hợp lệ, `reason` không trống, giao dịch đã ghi xuống database, hay một chuỗi trạng thái chuyển đổi là đúng. Những quy tắc ấy vẫn cần validation, service logic, giao dịch dữ liệu và kiểm thử.

### 3.2. Sealed giới hạn **kiểu con trực tiếp**

Đây là điểm quan trọng nhất khi đọc cú pháp. `permits A, B` không đồng nghĩa toàn bộ cây kế thừa chỉ có đúng hai kiểu cụ thể ở mọi cấp. Từng kiểu `A`, `B` được phép có thể quyết định có mở tiếp nhánh của nó hay không, bằng `final`, `sealed` hoặc `non-sealed`.

Vì vậy, để mô hình giữ tập kết quả hữu hạn, hãy cân nhắc **đóng các nhánh lá** bằng `final` hoặc dùng record. Đừng thêm `non-sealed` chỉ để tránh một lỗi biên dịch.

## 4. Ví dụ hoàn chỉnh chạy trên Java 17

Để minh họa bằng một file có thể sao chép và chạy trực tiếp, ta đặt các kiểu dưới dạng thành viên lồng bên trong một class công khai. Ví dụ có ba nhánh kết quả, validation cơ bản và mã xử lý phân loại kết quả.

Tạo file **PaymentResultDemo.java**:

```java
import java.util.Objects;

public class PaymentResultDemo {

    public sealed interface PaymentResult
            permits Approved, Declined, PendingVerification {
    }

    public record Approved(String transactionId, long amountInCents)
            implements PaymentResult {

        public Approved {
            Objects.requireNonNull(transactionId, "transactionId");
            if (transactionId.isBlank()) {
                throw new IllegalArgumentException("Mã giao dịch không được trống");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
        }
    }

    public record Declined(String reason) implements PaymentResult {

        public Declined {
            Objects.requireNonNull(reason, "reason");
            if (reason.isBlank()) {
                throw new IllegalArgumentException("Lý do không được trống");
            }
        }
    }

    public record PendingVerification(String requestId)
            implements PaymentResult {

        public PendingVerification {
            Objects.requireNonNull(requestId, "requestId");
            if (requestId.isBlank()) {
                throw new IllegalArgumentException("Mã yêu cầu không được trống");
            }
        }
    }

    static PaymentResult pay(long amountInCents, boolean needsVerification) {
        if (amountInCents <= 0) {
            return new Declined("Số tiền không hợp lệ");
        }
        if (needsVerification) {
            return new PendingVerification("VERIFY-001");
        }
        return new Approved("TX-001", amountInCents);
    }

    static String explain(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "Đã thu " + approved.amountInCents()
                    + " xu, mã " + approved.transactionId();
        }
        if (result instanceof Declined declined) {
            return "Bị từ chối: " + declined.reason();
        }
        if (result instanceof PendingVerification pending) {
            return "Chờ xác minh: " + pending.requestId();
        }
        throw new IllegalStateException(
                "Chưa có cách xử lý kiểu kết quả: " + result
        );
    }

    public static void main(String[] args) {
        System.out.println(explain(pay(125_000, false)));
        System.out.println(explain(pay(125_000, true)));
        System.out.println(explain(pay(-100, false)));
    }
}
```

Chạy bằng JDK 17:

```shell
java -version
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

Kết quả minh họa:

```text
Đã thu 125000 xu, mã TX-001
Chờ xác minh: VERIFY-001
Bị từ chối: Số tiền không hợp lệ
```

Một số quyết định thiết kế trong ví dụ:

- `PaymentResult` là **sealed interface** vì các nhánh chia sẻ khái niệm kết quả xử lý nhưng không cần chia sẻ trạng thái đối tượng hoặc một lớp cha cài đặt.
- `Approved`, `Declined`, `PendingVerification` là **record**, vì từng kết quả mang một bộ dữ liệu đơn giản. Record tự sinh constructor, accessor, `equals`, `hashCode` và `toString` theo hợp đồng record.
- Mỗi record có **compact constructor** kiểm tra dữ liệu thuộc phạm vi riêng. Sealed không thay validation ở tầng này.
- Phương thức `pay` có kiểu trả về chung `PaymentResult`, giúp caller không phải phụ thuộc vào chi tiết lựa chọn nhánh.
- Phương thức `explain` dùng **pattern matching for `instanceof`**, tính năng đã ổn định từ Java 16 và dùng bình thường trong Java 17, không cần bật preview.
- Mã `TX-001` và `VERIFY-001` chỉ là giá trị mô phỏng. Hệ thống thực tế phải cấp mã theo quy trình nghiệp vụ và kiểm soát tính duy nhất.

**Điểm cần nhận thức:** Dù cây kiểu hiện chỉ có ba nhánh, Java 17 **không tự xác nhận rằng chuỗi `if`/`instanceof` đã xử lý hết mọi nhánh**. Nếu sau này cho phép thêm nhánh mới, cần tìm và cập nhật các nơi phân nhánh tương ứng. Việc ném `IllegalStateException` ở cuối là lựa chọn phòng vệ tại runtime, không thay thế cơ chế kiểm tra đầy đủ ở compile time.

## 5. Vì sao không giải quyết bài toán chỉ bằng enum?

`enum` có vị trí rất phù hợp nếu miền chỉ cần **một tập hằng trạng thái**:

```java
enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING_VERIFICATION
}
```

Nhưng nhiều nghiệp vụ cần trả về dữ liệu khác nhau theo từng trường hợp:

| Trường hợp | Dữ liệu riêng cần mang |
|---|---|
| `Approved` | Mã giao dịch, số tiền đã chấp nhận |
| `Declined` | Lý do từ chối |
| `PendingVerification` | Mã yêu cầu xác minh |

Nếu chỉ dùng enum, ta có thể phải tạo một lớp bao gồm toàn bộ trường có thể có:

```java
// Ví dụ chưa tối ưu về mô hình:
record PaymentResponse(
        PaymentStatus status,
        String transactionId,
        Long amountInCents,
        String reason,
        String verificationRequestId
) {}
```

Với thiết kế này, một đối tượng có thể mang `status = APPROVED` nhưng `transactionId = null`, hoặc mang đồng thời `reason` và `transactionId` dù chỉ một trong hai có ý nghĩa. Ta phải tự kiểm soát các tổ hợp không hợp lệ.

Sealed type kết hợp các record cho phép **mỗi trường hợp có cấu trúc riêng**; ví dụ `Approved` không có field `reason` vì trường này không thuộc bản chất của nhánh thành công.

Tuy nhiên, không phải cứ có trạng thái là cần sealed:

| Nhu cầu | Lựa chọn thường hợp lý |
|---|---|
| Chỉ có một tập mã trạng thái cố định, ít hoặc không có dữ liệu riêng | `enum` |
| Các trường hợp hữu hạn mang payload/đặc tính khác nhau, cần đa hình | `sealed interface`/`sealed class` và các nhánh cụ thể |
| Cho phép bên ngoài tạo thêm implementation hợp lệ, chẳng hạn hệ plugin | `interface` thông thường |
| Muốn một lớp thực thi chung và kiểm soát cây kế thừa | `sealed class`, nếu phù hợp với thiết kế kế thừa |

Enum cũng có thể chứa field, method và hành vi riêng theo từng hằng. Vì vậy đây là **lựa chọn mô hình miền**, không phải quy tắc rằng sealed luôn mạnh hơn enum.

## 6. Những quy tắc ngôn ngữ cần hiểu về sealed trong Java 17

### 6.1. `sealed`, `permits` và quan hệ kế thừa

Một sealed class hoặc interface chỉ định những kiểu được phép kế thừa/triển khai trực tiếp:

```java
sealed interface DocumentResult permits Saved, SaveFailed {
}

record Saved(long documentId) implements DocumentResult {
}

record SaveFailed(String reason) implements DocumentResult {
}
```

Các record trên là những kiểu ở cùng một đơn vị nguồn minh họa. Trong dự án nhiều file, cần đặt chúng tại package/module hợp lệ.

**Danh sách `permits` mô tả quan hệ con trực tiếp**, không phải danh sách các đối tượng được quyền khởi tạo. Ngoài việc nằm trong danh sách `permits`, kiểu được phép phải thực sự khai báo `extends` hoặc `implements` kiểu sealed.

Nếu các kiểu con nằm trong cùng *compilation unit* với sealed type, Java có thể suy ra danh sách permitted subclasses để bạn bỏ phần `permits`. Tuy nhiên, viết `permits` tường minh thường có lợi trong bài học và mô hình nghiệp vụ vì người đọc nhìn thấy ngay tập trường hợp.

### 6.2. Các kiểu con trực tiếp phải nêu rõ cách tiếp tục mở rộng

Một lớp hoặc interface trực tiếp kế thừa sealed type phải có trạng thái kế thừa phù hợp:

- **`final`:** dừng nhánh kế thừa tại đây. Record là `final` một cách ngầm định.
- **`sealed`:** tiếp tục hạn chế các kiểu con trực tiếp của nhánh này.
- **`non-sealed`:** mở lại việc kế thừa/triển khai ở phía dưới nhánh này.

Ví dụ:

```java
sealed interface Command permits ExitCommand, DataCommand {
}

final class ExitCommand implements Command {
}

non-sealed interface DataCommand extends Command {
}

final class ImportCommand implements DataCommand {
}
```

`Command` vẫn chỉ có **hai nhánh trực tiếp** là `ExitCommand` và `DataCommand`. Nhưng vì `DataCommand` được khai báo `non-sealed`, các kiểu khác có thể triển khai nó và qua đó cũng là `Command` **gián tiếp**.

Sơ đồ:

```text
Command (sealed)
├── ExitCommand (final)         <- nhánh kết thúc
└── DataCommand (non-sealed)   <- nhánh mở
    ├── ImportCommand (final)
    └── ...có thể thêm kiểu con
```

Nếu nghiệp vụ yêu cầu số trường hợp ở toàn bộ cây là hữu hạn, cần thiết kế các nhánh để giữ ràng buộc đó. `non-sealed` là công cụ có chủ đích cho điểm mở rộng, không phải mặc định nên dùng.

### 6.3. Ràng buộc package/module

Java 17 giới hạn vị trí các kiểu con được phép:

- Nếu sealed type nằm trong **named module**, các direct permitted subclasses phải thuộc **cùng named module**; chúng không nhất thiết phải cùng package.
- Nếu sealed type nằm trong **unnamed module** (ví dụ ứng dụng classpath thông thường), các direct permitted subclasses phải thuộc **cùng package**.

Điều này ảnh hưởng đến cách tổ chức mã khi tách lớp ra nhiều file. Bạn không thể dùng `permits` để cho phép tùy ý một class của thư viện nằm trong module khác kế thừa sealed type.

Ví dụ cấu trúc cùng package, phù hợp ứng dụng classpath:

```text
src/main/java/com/example/payment/
├── PaymentResult.java
├── Approved.java
├── Declined.java
└── PendingVerification.java
```

Trong từng file khai báo cùng dòng `package com.example.payment;`. `PaymentResult.java` chứa danh sách `permits` ba lớp còn lại. Khi dùng build tool với Java 17, compiler sẽ kiểm tra quan hệ cho phép này.

### 6.4. Sealed class và sealed interface chọn thế nào?

**Sealed interface** mô tả một hợp đồng chung. Nó rất tự nhiên khi các nhánh có những dữ liệu hoặc hành vi độc lập, nhất là khi mỗi nhánh là record.

**Sealed class** thích hợp khi các kiểu con cần chia sẻ constructor, field hoặc hành vi chung mà lớp cha sở hữu:

```java
abstract sealed class Operation
        permits TransferOperation, RefundOperation {

    private final String operationId;

    protected Operation(String operationId) {
        this.operationId = java.util.Objects.requireNonNull(operationId);
    }

    public String operationId() {
        return operationId;
    }
}

final class TransferOperation extends Operation {
    TransferOperation(String id) {
        super(id);
    }
}

final class RefundOperation extends Operation {
    RefundOperation(String id) {
        super(id);
    }
}
```

`sealed` không đồng nghĩa `abstract`. Hai từ khóa có vai trò khác nhau: `abstract` ngăn khởi tạo trực tiếp một lớp trừu tượng và cho phép hành vi chưa hoàn chỉnh; `sealed` giới hạn những kiểu được kế thừa trực tiếp. Khi lớp gốc của miền không nên có đối tượng độc lập, kết hợp `abstract sealed class` là một lựa chọn thường gặp.

### 6.5. Sealed không phá quy tắc đóng gói thông thường

Khả năng khai báo `permits` **không tự thay đổi** phạm vi truy cập `public`, package-private hoặc `private`. Một kiểu con được cho phép vẫn phải thỏa điều kiện truy cập và có thể cần truy cập constructor của lớp cha qua phạm vi `protected` hoặc package-private.

Sealed class cũng không có nghĩa dữ liệu trong mọi kiểu con đều immutable. Một class `final` vẫn có thể chứa field có thể thay đổi. Nếu bài toán yêu cầu bất biến dữ liệu, cần thiết kế bổ sung bằng `final` field, record, defensive copy hoặc các phương pháp thích hợp khác.

## 7. Phân nhánh kết quả trên Java 17: làm đúng phiên bản

Khi nhận một biến `PaymentResult`, phần sử dụng thường cần biết đang gặp trường hợp nào. Java 17 hỗ trợ **pattern matching for `instanceof`** ở dạng ổn định:

```java
static String toMessage(PaymentResultDemo.PaymentResult result) {
    if (result instanceof PaymentResultDemo.Approved a) {
        return "OK: " + a.transactionId();
    }
    if (result instanceof PaymentResultDemo.Declined d) {
        return "ERROR: " + d.reason();
    }
    if (result instanceof PaymentResultDemo.PendingVerification p) {
        return "ACTION_REQUIRED: " + p.requestId();
    }
    throw new IllegalStateException("Unhandled payment result");
}
```

Khai báo kiểu trong điều kiện `instanceof` đồng thời tạo biến đã ép kiểu nếu điều kiện thành công. Đây là cách giảm ép kiểu thủ công:

```java
if (result instanceof PaymentResultDemo.Approved) {
    PaymentResultDemo.Approved a =
            (PaymentResultDemo.Approved) result;
    // ...
}
```

Đoạn thứ hai vẫn hợp lệ, nhưng dài hơn và dễ lặp lại kiểu.

**Giới hạn phiên bản quan trọng:** Trong Java 17, **pattern matching for switch mới ở trạng thái preview**, chưa phải phần cú pháp ổn định. Không lấy ví dụ `switch (result) { case Approved a -> ... }` làm lời giải chuẩn cho Java 17 nếu không giải thích rõ preview và các cờ đặc biệt. Pattern matching for switch được chuẩn hóa trong Java 21. Tương tự, record patterns cũng thuộc phiên bản sau Java 17.

Điều này có một hệ quả thực tiễn: Java 17 chưa có cách thông thường bằng `switch` pattern để compiler dùng tính sealed kiểm tra đầy đủ tất cả nhánh như trong những phiên bản mới. Khi thêm một permitted subtype mới trong Java 17, cần rà soát các chuỗi `if`/`instanceof`, visitor hoặc bộ định tuyến liên quan bằng tìm kiếm mã và kiểm thử.

Đừng hứa rằng sealed tự động làm mọi nhánh xử lý của ứng dụng **exhaustive** trên Java 17; điều compiler thực sự kiểm soát ở đây là **quyền kế thừa trực tiếp**.

## 8. Khi nào giới hạn kiểu con mang lại giá trị?

### 8.1. Kết quả nghiệp vụ với payload khác nhau

Mẫu:

```text
LoginResult
├── LoggedIn(sessionToken)
├── InvalidCredentials(reason)
└── MfaRequired(challengeId)
```

Các trường hợp được xác định trong hợp đồng đăng nhập. Mỗi nhánh chứa dữ liệu phù hợp, còn caller chỉ nhận `LoginResult`. Đây là ứng viên tốt nếu đội phát triển kiểm soát đầy đủ các trường hợp và vòng đời thay đổi API.

### 8.2. Các trường hợp của một biểu thức hoặc cú pháp

```text
Expression
├── NumberLiteral(value)
├── Add(left, right)
└── Multiply(left, right)
```

Với bộ phân tích hoặc diễn dịch một ngôn ngữ con có tập nút đã biết, sealed giúp mô tả kiểu nút có thể xuất hiện. Kiểu `Add` có thể chứa hai `Expression` và tạo thành cấu trúc cây. Nếu sau này bổ sung toán tử chia, phải chủ động cập nhật danh sách và những bộ xử lý liên quan.

### 8.3. Lệnh hoặc sự kiện nội bộ có phạm vi xác định

```text
OrderDecision
├── Accepted(orderId)
├── Rejected(reason)
└── ManualReview(caseId)
```

Đây là mô hình phù hợp khi ứng dụng **sở hữu tập quyết định**. Ngược lại, một event bus công khai cho các plugin bên ngoài định nghĩa sự kiện mới có thể cần interface mở và cơ chế đăng ký xử lý động.

### 8.4. Phân biệt trường hợp hợp lệ và tổ hợp dữ liệu bất hợp lệ

Một record tổng quát nhiều trường nullable có thể cho phép tổ hợp sai:

```text
status=DECLINED, transactionId="TX-001", reason=null
```

Mỗi nhánh riêng biệt giúp **thu hẹp những trạng thái có thể biểu diễn**, bởi `Declined` chỉ mang dữ liệu dành cho từ chối và có thể tự kiểm tra `reason`. Đây là lợi ích khi thiết kế mô hình dữ liệu: giảm công việc suy đoán tổ hợp trường trong code xử lý.

Sealed cộng record **không bảo đảm mọi đối tượng đều hợp lệ** nếu constructor vẫn nhận dữ liệu sai hoặc trường chứa đối tượng mutable; các bất biến còn lại cần được thực thi rõ ràng.

## 9. Khi nào không nên khóa hierarchy bằng sealed?

Sealed là một quyết định về **quyền mở rộng API**. Nếu miền được chủ đích thiết kế để những phần độc lập bổ sung implementation, việc khóa hierarchy có thể gây trở ngại.

Ví dụ, một giao diện:

```java
public interface NotificationChannel {
    void send(String message);
}
```

có thể cho phép plugin cung cấp thêm `EmailChannel`, `SmsChannel`, `WebhookChannel` hoặc kênh mới. Nếu thư viện không biết trước mọi kiểu triển khai, một `sealed interface` liệt kê cố định sẽ giới hạn trường hợp sử dụng chính đáng.

Các tình huống nên cân nhắc kỹ:

- **API extension point:** thư viện phát hành cho bên thứ ba tự triển khai interface.
- **Service Provider Interface (SPI):** hỗ trợ implementation xuất hiện từ module/plugin khác.
- **Miền nghiệp vụ thực sự mở:** loại kết quả mới xuất hiện liên tục do tích hợp hệ thống khác.
- **Chỉ có mã trạng thái đơn giản:** `enum` dễ hiểu hơn.
- **Các đối tượng có vòng đời và trạng thái thay đổi phức tạp:** cần chọn class/entity theo yêu cầu của miền và framework, không nhất thiết chuyển sang record.
- **Ràng buộc package/module không phù hợp kiến trúc hiện có:** cần cân nhắc việc tập trung định nghĩa và mở rộng cây, thay vì cố ép các kiểu từ module khác trở thành direct permitted subclasses.

Không nên dùng sealed chỉ để “viết theo Java 17”. Hãy xác định trước **ai sở hữu danh sách trường hợp hợp lệ**, **có cần bên ngoài mở rộng không**, và **khi nào cần thêm một nhánh mới**.

## 10. Thêm một trường hợp mới: điều gì sẽ thay đổi?

Giả sử hệ thống thanh toán bổ sung trạng thái `RefundRequired` khi một giao dịch cần hoàn tiền. Đây là **thay đổi hợp đồng miền**, không phải việc chỉ thêm một class.

Trước khi sửa:

```java
sealed interface PaymentResult
        permits Approved, Declined, PendingVerification {
}
```

Sau khi thống nhất nghiệp vụ, thêm kiểu:

```java
sealed interface PaymentResult
        permits Approved, Declined, PendingVerification, RefundRequired {
}

record RefundRequired(String transactionId, String reason)
        implements PaymentResult {
}
```

Hai đoạn là **minh họa khai báo trước/sau**, không đặt chung vào một file vì sẽ trùng định nghĩa `PaymentResult`.

Vì `RefundRequired` đã được liệt kê, compiler cho phép nó làm subtype trực tiếp. Nhưng những nơi chỉ xử lý ba trường hợp ban đầu vẫn có thể rơi vào nhánh lỗi runtime, trả thông báo mặc định không đúng hoặc bỏ qua nghiệp vụ. Công việc nâng cấp đúng phải bao gồm:

1. Xác định trường hợp mới có thực sự cùng một miền hay cần mô hình riêng.
2. Thêm nhánh mới trong `permits` và khai báo dữ liệu/bất biến riêng.
3. Xác định những luồng xử lý phải phản ứng với trường hợp này: service, controller, mapping sang HTTP/API response, logging, lưu trữ, telemetry.
4. Kiểm tra serializer/deserializer và các thư viện mapping đang sử dụng có hỗ trợ cách biểu diễn dữ liệu mới.
5. Bổ sung kiểm thử cho nhánh mới và các nhánh cũ, đặc biệt xử lý chưa được cập nhật.

Trong Java 17, việc dùng sealed **giúp bảo vệ ranh giới mở rộng của hierarchy**, còn việc phân phối logic xử lý trường hợp mới vẫn là trách nhiệm của thiết kế và kiểm thử.

## 11. Áp dụng vào một codebase Java 8/11 đang được nâng cấp

Khi chuyển hệ thống sang Java 17, không cần đổi mọi interface thành sealed. Hãy bắt đầu từ những nơi có dấu hiệu **miền đóng**:

- Có tài liệu nghiệp vụ liệt kê hữu hạn các loại kết quả.
- Các implementation được sở hữu bởi cùng một module/package phù hợp.
- Caller phải phân biệt một vài trường hợp cụ thể; không có hợp đồng plugin công khai.
- Việc tạo subtype mới thiếu kiểm soát có thể làm sai logic xử lý.

Quy trình triển khai được khuyến nghị:

**Bước 1 — Xác định hợp đồng miền.** Liệt kê tên, ý nghĩa, dữ liệu bắt buộc và điều kiện tạo của mỗi nhánh. Phân biệt *kết quả nghiệp vụ* với *trạng thái workflow* có thể biến đổi theo thời gian.

**Bước 2 — Kiểm kê các subtype hiện có.** Trước khi đổi interface sang sealed, tìm mọi `implements`/`extends`, kể cả trong test và các module phụ thuộc. Nếu có subtype thuộc module ngoài hoặc plugin, hãy xem lại quyết định khóa hierarchy.

**Bước 3 — Quyết định mức đóng.** Dùng sealed interface hoặc sealed class; ưu tiên `final`/record ở các nhánh lá. Chỉ sử dụng `non-sealed` khi thực sự muốn một nhánh tiếp tục mở.

**Bước 4 — Xem lại cách xử lý.** Đánh giá các `if`/`instanceof`, bộ phân phối hành vi, mapper và điểm chuyển dữ liệu ra API. Hệ thống còn phải xử lý trạng thái bất hợp lệ hoặc dữ liệu đầu vào đến từ bên ngoài một cách rõ ràng.

**Bước 5 — Kiểm tra tương thích.** Nâng cấu hình biên dịch và chạy lên Java 17, xác nhận dependency/framework. Với thư viện công khai, thay đổi interface mở thành sealed là thay đổi hợp đồng, có thể khiến mã client trước đây tự triển khai interface không còn biên dịch được.

**Bước 6 — Kiểm thử hành vi.** Test tạo từng nhánh hợp lệ, validation khi đầu vào sai, response mapping và trường hợp thêm subtype mới. Compiler cung cấp một phần bảo vệ nhưng không thay được kiểm thử nghiệp vụ.

### Cấu hình phiên bản biên dịch

Ví dụ từ terminal có JDK 17:

```shell
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

`sealed` là tính năng ngôn ngữ được chuẩn hóa ở Java 17. Nếu dự án buộc phải **chạy trên Java 11**, không thể chỉ viết sealed type rồi dùng `--release 11`; phải thay đổi yêu cầu runtime hoặc giữ mô hình tương thích Java 11. Một binary được biên dịch cho Java 17 không chạy trực tiếp trên JVM Java 11.

## 12. Các hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng trong Java 17 |
|---|---|
| “`sealed` nghĩa là class không có kiểu con.” | Đó là ý nghĩa gần với `final`. `sealed` cho phép **một số subtype trực tiếp được liệt kê**. |
| “`permits` liệt kê tất cả kiểu con ở mọi cấp.” | Nó liệt kê subtype **trực tiếp**; nhánh `non-sealed` có thể mở tiếp. |
| “Có sealed thì mọi nhánh `if` đều được compiler kiểm tra đủ.” | Java 17 không tự kiểm tra exhaustiveness của chuỗi `if`/`instanceof`. |
| “Sealed khiến dữ liệu bất biến.” | Sealed kiểm soát kế thừa, không tự kiểm soát việc thay đổi field. |
| “Record bắt buộc đi với sealed.” | Record có thể dùng độc lập; sealed class/interface cũng có thể dùng với class thường. |
| “`non-sealed` dùng để khai báo kiểu bất kỳ.” | Từ khóa này có ý nghĩa khi khai báo kiểu trực tiếp kế thừa sealed type, để mở lại khả năng kế thừa của nhánh. |
| “Có thể cấp phép trực tiếp cho subtype từ module bất kỳ.” | Direct permitted subtype phải nằm trong cùng named module, hoặc cùng package nếu trong unnamed module. |
| “Sealed giúp bỏ mọi validation và xử lý lỗi.” | Nó chỉ bảo vệ ranh giới subtype; dữ liệu từng nhánh vẫn cần hợp đồng hợp lệ. |
| “Muốn xử lý sealed phải dùng switch pattern trên Java 17.” | Java 17 hỗ trợ `instanceof` pattern ổn định. Switch pattern trên Java 17 còn là preview. |
| “Đổi interface thư viện sang sealed không ảnh hưởng người dùng.” | Đây có thể là breaking change đối với mã client trước đây tự tạo implementation. |

## 13. Bài tập thực hành

### Bài tập 1 — Miền phê duyệt hồ sơ

Thiết kế kết quả phê duyệt với ba trường hợp:

- `Accepted`: có `applicationId` và `approvedAt`.
- `Rejected`: có `reason`.
- `NeedMoreDocuments`: có danh sách tên giấy tờ cần bổ sung.

Yêu cầu:

1. Dùng `sealed interface ApplicationDecision` và ba `record` tương ứng.
2. Viết validation để tránh mã hồ sơ trống, lý do trống và danh sách giấy tờ không hợp lệ.
3. Sử dụng `List.copyOf` khi lưu danh sách tài liệu cần bổ sung để tránh caller thay đổi danh sách sau khi tạo record.
4. Viết hàm `toMessage(ApplicationDecision decision)` dùng pattern matching for `instanceof`, chạy trên JDK 17 mà không cần preview.
5. Thử viết một record thứ tư không có tên trong `permits`; quan sát lỗi compiler rồi giải thích tại sao.

**Câu hỏi tư duy:** Nếu đội sản phẩm cho phép đối tác tự định nghĩa một kiểu kết quả phê duyệt riêng, hợp đồng sealed hiện tại có phù hợp không? Phân tích lại quyền sở hữu của miền trước khi chọn cách sửa.

### Bài tập 2 — Kiểm soát mở rộng từng nhánh

Thiết kế:

```text
Message (sealed)
├── InternalMessage (final)
└── ExternalMessage (non-sealed)
    └── PartnerMessage
```

Hãy viết các class/interface cần thiết và giải thích:

- Vì sao `PartnerMessage` không cần xuất hiện trong `permits` của `Message`?
- Nếu đổi `ExternalMessage` thành `sealed`, cần thay đổi gì?
- Nếu yêu cầu "chỉ có đúng hai loại thông điệp trong toàn bộ hệ thống", nên thiết kế lại như thế nào?

### Bài tập 3 — Chọn enum, sealed hay interface thường

Đối với mỗi bài toán, xác định lựa chọn ban đầu và lý do:

| Bài toán | Điểm cần cân nhắc |
|---|---|
| Thứ trong tuần | Tập hằng cố định, gần như không có payload theo từng trường hợp |
| Kết quả xử lý yêu cầu vay vốn | Các kết quả có payload riêng và hệ thống sở hữu tập trường hợp |
| Plugin xuất file | Bên thứ ba có cần tự thêm định dạng không? |
| Các nút cú pháp trong một trình biên dịch nhỏ | Loại nút được thiết kế bởi ai và có dự kiến mở rộng không? |

Trọng tâm của bài tập là làm rõ **quy tắc miền dữ liệu** trước khi chọn từ khóa Java.

## 14. Ghi nhớ về cách dùng sealed đúng mục đích

Một sealed hierarchy phù hợp khi tập kiểu con là **một phần của hợp đồng nghiệp vụ được kiểm soát**. Nó giúp đưa giới hạn từ lời hứa trong tài liệu thành quy tắc được Java 17 kiểm tra lúc biên dịch.

Trước khi thêm `sealed`, hãy luôn tự trả lời:

1. Miền có thật sự chỉ cho phép một tập trường hợp được xác định trước không?
2. Ai sở hữu quyền bổ sung subtype mới? Có khách hàng thư viện hoặc plugin cần tự mở rộng không?
3. Các nhánh lá nên là `final`/record, hay có lý do rõ ràng để tiếp tục `sealed` hoặc `non-sealed`?
4. Mỗi trường hợp có dữ liệu và bất biến riêng gì?
5. Những nơi phân nhánh theo kiểu cần được cập nhật và kiểm thử ra sao khi miền thay đổi?

Giới hạn kiểu con là một **quyết định thiết kế miền**, còn `sealed` là công cụ của Java 17 giúp thực thi phần ràng buộc kế thừa của quyết định đó.

## 15. Tài liệu tham khảo

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): đặc tả mục đích và cơ chế sealed class/interface được chuẩn hóa trong JDK 17.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): quy tắc chính thức về khai báo class, interface, kế thừa, `permits` và `non-sealed`.
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): tham chiếu API tương thích với Java 17.
- [dev.java — Learn Java](https://dev.java/learn/): học về mô hình đối tượng, record, kế thừa và các tính năng ngôn ngữ Java.
