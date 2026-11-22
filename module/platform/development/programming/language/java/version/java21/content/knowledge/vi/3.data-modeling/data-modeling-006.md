# Kết hợp sealed hierarchy với record để mô hình hóa các biến thể dữ liệu

Trong ứng dụng, một khái niệm nghiệp vụ đôi khi có nhiều dạng dữ liệu khác nhau. Ví dụ, kết quả thanh toán có thể là thành công, bị từ chối hoặc đang chờ xử lý. Mỗi dạng mang những thông tin riêng, nhưng tất cả đều là một loại kết quả thanh toán. Nếu mô hình hóa bằng một lớp duy nhất chứa nhiều trường nullable và các cờ trạng thái, dữ liệu dễ rơi vào những tổ hợp không hợp lệ.

Java cung cấp hai tính năng bổ trợ nhau để biểu diễn loại dữ liệu này: **sealed hierarchy** giới hạn tập kiểu con được phép, còn **record** mô tả dữ liệu của từng biến thể. Trong Java 21, Record Patterns và pattern matching for `switch` đã là tính năng chính thức, giúp phân tích các biến thể và xử lý từng trường hợp một cách rõ ràng.

Các mốc phiên bản cần phân biệt:

- Record trở thành tính năng chính thức từ Java 16.
- Sealed classes và sealed interfaces trở thành tính năng chính thức từ Java 17.
- Record Patterns và pattern matching for `switch` được hoàn thiện trong Java 21.

## 1. Vì sao cần mô hình hóa các biến thể dữ liệu?

Giả sử một thao tác thanh toán có ba kết quả:

- Được chấp thuận: có mã giao dịch và số tiền.
- Bị từ chối: có mã lỗi và lý do.
- Đang chờ: có mã tham chiếu để tra cứu tiếp.

Một cách thiết kế kém rõ ràng là tạo một lớp duy nhất với tất cả thuộc tính:

```java
public class PaymentResult {
    String status;
    String transactionId;
    Long amountInCents;
    String errorCode;
    String reason;
    String reference;
}
```

Với cấu trúc này, một đối tượng có thể chứa đồng thời dữ liệu thành công và dữ liệu từ chối, hoặc thiếu những trường cần thiết cho trạng thái của nó. Mã sử dụng phải liên tục kiểm tra `status`, kiểm tra `null` và tự suy luận trường nào có ý nghĩa.

Mô hình theo biến thể giúp mỗi dạng chỉ chứa dữ liệu phù hợp. Sealed hierarchy định nghĩa tập biến thể được chấp nhận; mỗi record thể hiện cấu trúc của một biến thể. Ví dụ, `Approved` có mã giao dịch và số tiền, còn `Rejected` có mã lỗi và thông báo.

## 2. Sealed hierarchy là gì?

Một lớp hoặc interface được khai báo với từ khóa `sealed` có thể kiểm soát những kiểu nào được phép kế thừa hoặc triển khai trực tiếp. Danh sách các kiểu được phép được khai báo bằng mệnh đề `permits`.

Ví dụ:

```java
public sealed interface PaymentResult
        permits Approved, Rejected, Pending {
}
```

`PaymentResult` là interface sealed. Chỉ các kiểu được liệt kê trong `permits` mới được phép triển khai trực tiếp interface này. Những kiểu khác không thể tự ý `implements PaymentResult`.

Sealed hierarchy không có nghĩa là chỉ có đúng một đối tượng hoặc chỉ có một instance. Nó giới hạn **tập kiểu con trực tiếp**, từ đó cho phép người thiết kế kiểm soát các biến thể hợp lệ của mô hình.

### Quy tắc của kiểu con được phép

Mỗi kiểu con trực tiếp được liệt kê trong `permits` phải khai báo rõ cách tiếp tục kiểm soát hệ phân cấp bằng một trong ba lựa chọn:

- `final`: không cho phép kiểu khác kế thừa tiếp.
- `sealed`: tiếp tục giới hạn những kiểu con trực tiếp của chính nó.
- `non-sealed`: mở nhánh đó để các kiểu khác có thể kế thừa hoặc triển khai.

Một record là lớp `final` theo quy tắc của ngôn ngữ, nên có thể làm kiểu con trực tiếp của sealed interface mà không cần ghi thêm `final`. Record không thể là kiểu con của sealed class vì nó đã kế thừa trực tiếp từ `java.lang.Record`.

Các kiểu con được phép phải nằm trong cùng named module với sealed type nếu kiểu đó thuộc named module. Nếu sealed type nằm trong unnamed module, các kiểu con được phép phải ở cùng package. Quy tắc này giúp trình biên dịch và hệ thống module xác định tập kiểu được kiểm soát.

## 3. Dùng record làm từng biến thể của sealed interface

Có thể khai báo các record lồng bên trong sealed interface để gom một mô hình dữ liệu vào cùng một phạm vi:

```java
public sealed interface PaymentResult
        permits PaymentResult.Approved,
                PaymentResult.Rejected,
                PaymentResult.Pending {

    record Approved(String transactionId, long amountInCents)
            implements PaymentResult {
    }

    record Rejected(String errorCode, String reason)
            implements PaymentResult {
    }

    record Pending(String reference)
            implements PaymentResult {
    }
}
```

Mỗi record là một biến thể của `PaymentResult`:

| Biến thể | Dữ liệu riêng | Ý nghĩa |
|---|---|---|
| `Approved` | `transactionId`, `amountInCents` | Thanh toán được chấp thuận |
| `Rejected` | `errorCode`, `reason` | Thanh toán bị từ chối |
| `Pending` | `reference` | Kết quả đang chờ xử lý |

Các record lồng trong interface là kiểu thành viên có tính chất `public static` ngầm định. Chúng vẫn là những kiểu record độc lập, có constructor và accessor riêng. Việc lồng kiểu chỉ giúp tổ chức mã và thể hiện quan hệ giữa kiểu tổng quát với các biến thể.

Có thể tạo kết quả tương ứng như sau:

```java
PaymentResult approved =
        new PaymentResult.Approved("TX-1001", 250_000);

PaymentResult rejected =
        new PaymentResult.Rejected("LIMIT_EXCEEDED", "Amount exceeds limit");

PaymentResult pending =
        new PaymentResult.Pending("REF-9001");
```

Biến có kiểu khai báo `PaymentResult` có thể tham chiếu đến bất kỳ biến thể được phép nào. Mã gọi hàm không cần biết trước một kết quả cụ thể là record nào; phần xử lý sẽ phân nhánh theo kiểu thực tế.

## 4. Bảo vệ điều kiện hợp lệ của từng biến thể

Sealed hierarchy kiểm soát những kiểu được phép tham gia vào mô hình. Nó không tự kiểm tra dữ liệu bên trong từng record. Mỗi biến thể vẫn cần bảo đảm các điều kiện hợp lệ của chính nó.

Có thể dùng compact constructor của record để kiểm tra dữ liệu:

```java
import java.util.Objects;

public sealed interface PaymentResult
        permits PaymentResult.Approved, PaymentResult.Rejected, PaymentResult.Pending {

    record Approved(String transactionId, long amountInCents)
            implements PaymentResult {
        public Approved {
            Objects.requireNonNull(transactionId, "transactionId");
            transactionId = transactionId.strip();

            if (transactionId.isEmpty()) {
                throw new IllegalArgumentException("transactionId must not be empty");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        }
    }

    record Rejected(String errorCode, String reason) implements PaymentResult {
    }

    record Pending(String reference) implements PaymentResult {
    }
}
```

Đoạn mã trên minh họa compact constructor ngay trong record `Approved` được khai báo lồng bên trong sealed interface. Nếu khai báo record ở cấp top-level, kiểu đó phải được nêu đúng tên trong `permits` và tuân thủ quy tắc package/module của sealed type.

Với compact constructor, tham số thành phần được ngầm khai báo. Có thể kiểm tra hoặc chuẩn hóa tham số; Java tự gán các giá trị sau cùng vào trường thành phần khi constructor kết thúc bình thường. Không viết lệnh gán `this.transactionId = transactionId` trong compact constructor.

Record có các trường thành phần `final`, nhưng điều này chỉ bảo vệ việc gán lại trường. Nếu một thành phần tham chiếu đến collection hoặc đối tượng mutable, trạng thái bên trong đối tượng đó vẫn có thể thay đổi. Khi mô hình yêu cầu bảo vệ dữ liệu, cần cân nhắc sao chép đầu vào hoặc sử dụng kiểu thành phần bất biến.

## 5. Xử lý sealed hierarchy bằng pattern matching for switch

Java 21 cho phép sử dụng pattern matching trong `switch` như một tính năng chính thức. Kết hợp với sealed hierarchy, switch expression có thể xử lý từng biến thể mà không cần viết chuỗi `instanceof` và ép kiểu thủ công.

```java
static String describe(PaymentResult result) {
    return switch (result) {
        case PaymentResult.Approved(var transactionId, var amount) ->
                "Approved: " + transactionId + ", amount=" + amount;

        case PaymentResult.Rejected(var errorCode, var reason) ->
                "Rejected: " + errorCode + " - " + reason;

        case PaymentResult.Pending(var reference) ->
                "Pending: " + reference;
    };
}
```

Mỗi nhãn `case` sử dụng một Record Pattern. Khi giá trị khớp với biến thể, Java lấy các thành phần thông qua accessor của record và gán vào các pattern biến. Kiểu của biến được suy ra từ kiểu thành phần tương ứng.

Ví dụ, `PaymentResult.Approved(var transactionId, var amount)` có nghĩa là:

1. Kiểm tra giá trị đang xét có phải một `PaymentResult.Approved` hay không.
2. Nếu khớp, lấy `transactionId` và `amountInCents` thông qua accessor.
3. Gán các giá trị đó cho hai pattern biến `transactionId` và `amount` trong nhánh tương ứng.

Tên biến trong pattern do người viết chọn, không bắt buộc trùng tên thành phần record. Có thể dùng kiểu tường minh thay cho `var` khi muốn thể hiện rõ kiểu dữ liệu.

## 6. Exhaustive switch và lợi ích của sealed hierarchy

Switch expression ở ví dụ trên không có nhánh `default`, nhưng vẫn xử lý đầy đủ mọi biến thể được khai báo trong sealed hierarchy. Trình biên dịch biết `PaymentResult` chỉ có ba kiểu con trực tiếp được phép và cả ba đã được bao phủ.

Đây là tính chất **exhaustiveness** (tính đầy đủ) của switch. Nó giúp phát hiện trường hợp bị bỏ sót ngay trong quá trình biên dịch thay vì để một biến thể mới đi vào nhánh xử lý không dự kiến.

Giả sử sau này mô hình bổ sung biến thể `Cancelled`:

```java
record Cancelled(String reason) implements PaymentResult {
}
```

Và kiểu mới được thêm vào danh sách `permits` của `PaymentResult`, những switch expression đang xử lý toàn bộ `PaymentResult` cần được xem xét cập nhật để bao phủ biến thể này. Khi biên dịch lại với định nghĩa hierarchy mới, trình biên dịch có thể chỉ ra switch không còn exhaustive.

Lợi ích này đặc biệt hữu ích với mô hình nghiệp vụ có tập trạng thái được kiểm soát, chẳng hạn kết quả xác thực, trạng thái xử lý lệnh, kết quả phân tích cú pháp hoặc các loại thông điệp nội bộ.

### Xử lý null

`null` không phải một biến thể record và không tự động được xử lý bởi các pattern liệt kê subtype. Nếu switch có thể nhận `null`, hãy thể hiện rõ nhánh này:

```java
static String describeSafely(PaymentResult result) {
    return switch (result) {
        case null -> "No payment result";
        case PaymentResult.Approved(var id, var amount) ->
                "Approved " + id;
        case PaymentResult.Rejected(var code, var reason) ->
                "Rejected " + code;
        case PaymentResult.Pending(var reference) ->
                "Pending " + reference;
    };
}
```

Nếu selector là `null` mà switch không có `case null`, việc thực thi sẽ ném `NullPointerException`. Việc thêm `case null` là quyết định về hợp đồng đầu vào của hàm, không phải một biến thể bổ sung của sealed hierarchy.

## 7. Dùng guard when để xử lý chi tiết hơn trong một biến thể

Đôi khi một biến thể có thể được chia thành các trường hợp xử lý theo dữ liệu bên trong. Guard `when` cho phép bổ sung điều kiện cho pattern:

```java
static String classify(PaymentResult result) {
    return switch (result) {
        case PaymentResult.Approved(var id, var amount)
                when amount >= 1_000_000 -> "High-value payment: " + id;

        case PaymentResult.Approved(var id, var amount) ->
                "Standard payment: " + id;

        case PaymentResult.Rejected(var code, var reason) ->
                "Rejected: " + code;

        case PaymentResult.Pending(var reference) ->
                "Awaiting: " + reference;
    };
}
```

Trường hợp `Approved` có guard được đặt trước mẫu `Approved` tổng quát. Nếu đặt mẫu tổng quát trước, mẫu có guard phía sau sẽ bị mẫu trước bao phủ và trình biên dịch báo nhãn `case` không thể đạt tới. Với pattern switch, thứ tự nhãn và khả năng bao phủ của từng mẫu cần được xem xét cẩn thận.

Guard nên thể hiện điều kiện nghiệp vụ bổ sung. Nếu điều kiện làm thay đổi bản chất loại dữ liệu, hãy cân nhắc tạo một biến thể riêng thay vì gom quá nhiều trạng thái vào cùng một record.

## 8. Sealed class, sealed interface và record: chọn cấu trúc nào?

Sealed hierarchy có thể được xây dựng bằng sealed class hoặc sealed interface. Record có thể triển khai sealed interface. Record không thể mở rộng sealed class vì mọi record đều kế thừa trực tiếp từ `java.lang.Record`; nếu cần một sealed class làm kiểu cha, các biến thể phải là class tương thích với quy tắc kế thừa. Việc chọn cấu trúc phụ thuộc vào quan hệ giữa các kiểu và nhu cầu chia sẻ hành vi.

| Cấu trúc | Khi phù hợp | Đặc điểm |
|---|---|---|
| `sealed interface` + record | Các biến thể chủ yếu là dữ liệu, không cần chia sẻ trạng thái lớp cơ sở | Mỗi record có thể mang các thành phần riêng và cùng triển khai một hợp đồng |
| `sealed abstract class` + class con | Các biến thể cần dùng chung trạng thái hoặc triển khai hành vi từ lớp cơ sở | Có thể khai báo trường instance, constructor và phương thức dùng chung |
| Interface thông thường | Muốn cho phép module hoặc thư viện khác bổ sung kiểu triển khai | Tập kiểu triển khai mở, không exhaustive chỉ dựa vào danh sách kiểu con |
| `enum` | Tập giá trị cố định, mỗi giá trị không cần cấu trúc dữ liệu riêng phức tạp | Biểu diễn các hằng số có tên, có thể bổ sung hành vi theo từng hằng số |

Sealed interface thường phù hợp cho các kết quả hoặc thông điệp có nhiều dạng dữ liệu khác nhau. Sealed abstract class phù hợp khi các biến thể có chung trạng thái hoặc logic được kế thừa. Enum đơn giản và dễ đọc hơn nếu mỗi lựa chọn chỉ là một giá trị cố định, ví dụ `LOW`, `MEDIUM`, `HIGH`.

## 9. Khi nào một nhánh nên là sealed hoặc non-sealed?

Một sealed hierarchy không bắt buộc mọi nhánh đều kết thúc bằng record hoặc final class. Có thể tiếp tục phân cấp hoặc mở một nhánh khi có lý do thiết kế rõ ràng.

Ví dụ:

```java
public sealed interface Message
        permits Message.SystemMessage, Message.UserMessage, Message.ExtensionMessage {

    record SystemMessage(String text) implements Message {
    }

    record UserMessage(String userId, String text) implements Message {
    }

    non-sealed interface ExtensionMessage extends Message {
    }
}
```

`SystemMessage` và `UserMessage` là các biến thể record đóng. `ExtensionMessage` là nhánh mở; những kiểu khác có thể triển khai interface này. Vì một nhánh `non-sealed` có thể phát sinh thêm kiểu con, switch xử lý toàn bộ hierarchy thường cần có pattern bao phủ nhánh mở, chẳng hạn `case Message.ExtensionMessage message -> ...`.

Không nên dùng `non-sealed` chỉ để né việc cập nhật switch. Nó làm thay đổi hợp đồng của mô hình: một phần hierarchy trở thành điểm mở rộng cho các kiểu mới. Nếu mục tiêu là kiểm soát toàn bộ biến thể, hãy giữ các nhánh đóng bằng `final`, record hoặc sealed subtype.

## 10. Những trường hợp sử dụng phù hợp

Kết hợp sealed hierarchy với record đặc biệt hữu ích khi tập biến thể có giới hạn và mỗi biến thể có cấu trúc dữ liệu riêng.

**Kết quả nghiệp vụ:**

```java
public sealed interface ValidationResult
        permits ValidationResult.Valid, ValidationResult.Invalid {
    record Valid(String normalizedValue) implements ValidationResult {
    }

    record Invalid(String field, String message) implements ValidationResult {
    }
}
```

Mã gọi có thể xử lý kết quả hợp lệ và không hợp lệ bằng switch mà không phải kiểm tra một loạt trường nullable.

**Thông điệp hoặc sự kiện nội bộ:** một hierarchy có thể gồm `UserCreated`, `UserDisabled` và `EmailChanged`, mỗi record chứa đúng dữ liệu cần thiết để xử lý sự kiện tương ứng. Sealed hierarchy phù hợp khi tập sự kiện được quản lý bởi cùng một module hoặc nhóm mã nguồn.

**Cây cú pháp hoặc biểu thức:** một sealed interface `Expression` có thể có các biến thể `Literal`, `Addition` và `Variable`. Record Patterns giúp phân rã node và xử lý cây bằng switch expression. Đây là cách mô hình hóa hữu ích cho parser, bộ đánh giá biểu thức hoặc bộ chuyển đổi cú pháp.

Với các điểm mở rộng do bên thứ ba tự định nghĩa, interface thông thường hoặc một nhánh `non-sealed` có thể phù hợp hơn. Sealed hierarchy nên phản ánh đúng quyền sở hữu và khả năng mở rộng của mô hình trong ứng dụng.

## 11. Các nguyên tắc thiết kế cần nhớ

Khi thiết kế mô hình biến thể bằng sealed hierarchy và record, hãy cân nhắc các nguyên tắc sau:

1. **Mỗi record đại diện cho một trạng thái có ý nghĩa:** tên kiểu và thành phần dữ liệu cần thể hiện rõ biến thể đó.
2. **Không dùng trường nullable để thay thế biến thể:** nếu hai trạng thái có dữ liệu khác nhau, nên cân nhắc hai record riêng.
3. **Giữ hierarchy đóng khi cần kiểm soát đầy đủ:** chỉ thêm `non-sealed` nếu thực sự cần điểm mở rộng.
4. **Xác thực dữ liệu tại constructor:** bảo đảm mỗi record không được tạo ra trong trạng thái vi phạm bất biến nghiệp vụ.
5. **Dùng switch exhaustive:** liệt kê các biến thể đã biết để compiler hỗ trợ phát hiện trường hợp bị bỏ sót.
6. **Xử lý null theo hợp đồng rõ ràng:** null không tự trở thành một subtype hoặc record variant.
7. **Cẩn trọng khi thay đổi hierarchy:** thêm, xóa hoặc đổi tên biến thể có thể ảnh hưởng các switch, API và dữ liệu trao đổi.
8. **Không nhầm `final` với bất biến sâu:** record bảo vệ trường thành phần khỏi gán lại, nhưng không tự làm bất biến các đối tượng mutable được tham chiếu.

## 12. Tổng kết

Sealed hierarchy giới hạn những kiểu có thể kế thừa hoặc triển khai trực tiếp một kiểu cha. Record mô tả dữ liệu của từng biến thể với constructor, accessor và các phương thức giá trị được sinh tự động. Khi kết hợp hai tính năng, mô hình có thể thể hiện rõ tập trạng thái hợp lệ cùng dữ liệu riêng của từng trạng thái.

Java 21 bổ sung khả năng phân tích cấu trúc này bằng Record Patterns và pattern matching for `switch` đã được hoàn thiện. Một switch expression có thể xử lý toàn bộ các biến thể của sealed hierarchy và được trình biên dịch kiểm tra tính đầy đủ. Cách thiết kế này phù hợp với kết quả nghiệp vụ, sự kiện, thông điệp và cây dữ liệu có tập dạng được kiểm soát.

## Tài liệu tham khảo

- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — sealed classes và sealed interfaces, được hoàn thiện trong Java 17.
- [JEP 395: Records](https://openjdk.org/jeps/395) — record classes, được hoàn thiện trong Java 16.
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440) — Record Patterns, được hoàn thiện trong Java 21.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441) — pattern matching for switch, được hoàn thiện trong Java 21.
- [Java Language Specification, Java SE 21 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2) — quy tắc về sealed class và permitted direct subclasses.
- [Java Language Specification, Java SE 21 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10) — quy tắc về record class.
- [Java Language Specification, Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11) — quy tắc switch và pattern matching.
