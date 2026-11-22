# Sealed hierarchy hỗ trợ exhaustive `switch` trong Java

**Chủ đề:** Java Core Pattern Matching → Sealed hierarchy  
**Phiên bản:** Sealed classes/interfaces là tính năng chính thức từ Java 17 (JEP 409); pattern matching cho `switch` và guard `when` chính thức từ Java 21 (JEP 441). Chương trình thực hành dùng **JDK 21+**.

## 1. Bài toán: làm sao compiler biết đã xử lý đủ mọi subtype?

Khi một phương thức nhận một interface bình thường như `Payment`, Java thường không thể biết chắc toàn bộ các class có thể triển khai interface đó ở hiện tại hoặc tương lai. Vì thế, `switch` expression sử dụng type pattern cần một cách bao phủ các giá trị còn lại, chẳng hạn `default`, nếu các case chưa chứng minh được tính đầy đủ (*exhaustiveness*).

Với **sealed hierarchy**, người thiết kế công khai **tập subtype trực tiếp được phép**. Trình biên dịch có thể phân tích cây kiểu được đóng này để xác nhận các nhãn `case` có bao phủ mọi trường hợp non-null hay không.

Ví dụ:

```java
sealed interface Payment permits Card, Transfer, Voucher {}

record Card(String lastFour) implements Payment {}
record Transfer(String reference) implements Payment {}
record Voucher(int points) implements Payment {}
```

Ở đây `Payment` chỉ cho phép ba subtype trực tiếp: `Card`, `Transfer` và `Voucher`. Chúng là `record`, nên mặc nhiên là `final` và không thể bị subclass tiếp.

Một `switch` trên biến có kiểu tĩnh `Payment` có thể viết:

```java
static String category(Payment payment) {
    return switch (payment) {
        case Card card -> "CARD";
        case Transfer transfer -> "TRANSFER";
        case Voucher voucher -> "VOUCHER";
    };
}
```

Đây là **phương thức minh họa** cần đặt cùng các khai báo kiểu bên trên trong một class/phạm vi Java hợp lệ. Compiler chứng minh cả ba nhóm non-null đã được xử lý, do đó `switch` expression **không cần `default`**.

**Kết luận quan trọng:** sealed hierarchy không phải “tự chạy tất cả case”. Nó cung cấp đủ thông tin về hệ thống kiểu để compiler kiểm tra tính bao phủ; developer vẫn phải viết nhãn phù hợp cho từng nhánh.

## 2. `sealed`, `permits` và các subtype được phép

### 2.1. `sealed` đóng danh sách các subtype trực tiếp

Khai báo:

```java
sealed interface Payment permits Card, Transfer, Voucher {}
```

có nghĩa chỉ những class/interface được khai báo là subtype trực tiếp hợp lệ của `Payment` mới được `implements Payment` hoặc `extends Payment`. Với ví dụ này, không thể tự thêm `class CryptoPayment implements Payment {}` ở nơi khác rồi mong compiler cho qua: kiểu đó chưa nằm trong danh sách permitted direct subclasses.

Trong Java, kiểu được phép còn phải thỏa quy định vị trí: trong một module có tên, chúng phải thuộc cùng module với kiểu sealed; nếu không dùng named module, chúng phải cùng package. Không coi `permits` là một danh sách các tên class bất kỳ ở mọi module.

### 2.2. Mỗi subtype trực tiếp phải có chính sách mở rộng

Một class trực tiếp kế thừa sealed class, hoặc class/interface trực tiếp mở rộng sealed interface, cần thể hiện chiến lược tiếp tục của cây kiểu:

- **`final`**: không cho phép subclass tiếp. Một `record` mặc nhiên `final`, nên không phải viết `final record`.
- **`sealed`**: tiếp tục đóng cây ở cấp tiếp theo bằng một tập subtype được phép.
- **`non-sealed`**: mở nhánh đó cho các subtype tiếp theo, dù nhánh cha vẫn sealed.

Ví dụ minh họa:

```java
sealed interface Outcome permits Success, Failure, Later {}

record Success(String message) implements Outcome {}
record Failure(int code) implements Outcome {}

// Nhánh này chủ động mở rộng:
non-sealed interface Later extends Outcome {}

record Queued(String ticket) implements Later {}
record Retried(int seconds) implements Later {}
```

`Outcome` vẫn đóng ở **cấp trực tiếp**: subtype trực tiếp của nó chỉ có `Success`, `Failure`, `Later`. Nhưng `Later` là `non-sealed`, nên về sau có thể có thêm các implementation khác của `Later`. Điều này quan trọng khi thiết kế `switch`: case `Later later` đủ bao phủ cả nhánh mở đó mà không phải liệt kê mọi implementation con.

**Không nhầm sealed với enum.** Enum đóng tập giá trị hằng; sealed hierarchy đóng tập biến thể kiểu trực tiếp và cho mỗi subtype chứa dữ liệu/hành vi riêng.

## 3. Vì sao `switch` trở thành exhaustive mà không cần `default`?

Java 21 sử dụng thông tin về permitted subtypes khi kiểm tra sự bao phủ của một `switch` với selector kiểu sealed.

Giả sử:

```java
static String describe(Outcome outcome) {
    return switch (outcome) {
        case Success success -> "SUCCESS:" + success.message();
        case Failure failure -> "FAILURE:" + failure.code();
        case Later later -> "LATER";
    };
}
```

Nhánh `Success` khớp các đối tượng `Success`. Nhánh `Failure` khớp `Failure`. Nhánh `Later` bao phủ **mọi đối tượng có kiểu runtime triển khai `Later`**, kể cả `Queued`, `Retried` hay subtype mới được thêm sau này. Ba case đó bao phủ ba nhánh trực tiếp được phép của `Outcome`.

Vì compiler xác nhận được toàn bộ các nhóm kiểu, không cần `default` cho phần giá trị non-null của `Outcome`. Điều này không có nghĩa `switch` tự xử lý được `null`; xem mục 6.

### So sánh với interface không sealed

```java
interface OpenEvent {}
record Created(String id) implements OpenEvent {}
record Removed(String id) implements OpenEvent {}
```

Hai record đang thấy **không chứng minh được** rằng mọi giá trị `OpenEvent` trong tương lai đều thuộc `Created` hoặc `Removed`:

```java
// KHÔNG BIÊN DỊCH khi là switch expression:
static String unsafe(OpenEvent event) {
    return switch (event) {
        case Created created -> "CREATE";
        case Removed removed -> "REMOVE";
    };
}
```

Có thể bổ sung `default`, hoặc dùng một type pattern bao quát theo chính sách thiết kế. Với sealed `Outcome`, compiler có thông tin mạnh hơn nhờ `permits`, vì vậy mới chứng minh được exhaustiveness bằng các nhánh cụ thể.

## 4. Khi thiếu một subtype, compiler báo lỗi

Giả sử:

```java
sealed interface Message permits Email, Sms {}
record Email(String subject) implements Message {}
record Sms(String number) implements Message {}
```

Sau đây **không phải chương trình hợp lệ** vì thiếu `Sms`:

```java
static String broken(Message message) {
    return switch (message) {
        case Email email -> "EMAIL";
    };
}
// Lỗi biên dịch: the switch expression does not cover all possible input values.
```

Cách sửa đúng với miền kiểu đóng:

```java
static String repaired(Message message) {
    return switch (message) {
        case Email email -> "EMAIL";
        case Sms sms -> "SMS";
    };
}
```

Hoặc nếu nghiệp vụ thực sự muốn một dự phòng chung, dùng `default`. Tuy nhiên, với một sealed hierarchy mà mỗi subtype **phải** có logic riêng, liệt kê các subtype cụ thể không kèm `default` thường tạo ra lợi ích lớn: lỗi thiếu case được compiler phát hiện khi lập trình viên thay đổi hệ thống kiểu.

## 5. Guard `when` không tự bao phủ toàn bộ một subtype

Một type pattern có guard chỉ khớp khi **cả type pattern và biểu thức guard** thành công.

```java
case Voucher voucher when voucher.points() < 0 -> "INVALID";
```

Nhánh này chỉ xử lý `Voucher` âm, không xử lý `Voucher(0)`, `Voucher(100)`, v.v. Vì thế, khi muốn exhaustive, sau các nhánh đặc biệt có guard phải còn một nhánh đủ bao phủ phần còn lại của subtype:

```java
case Voucher voucher when voucher.points() < 0 -> "INVALID";
case Voucher voucher -> "VALID:" + voucher.points();
```

Tương tự với `Card`:

```java
case Card card when card.lastFour() == null -> "CARD_MISSING";
case Card card -> "CARD:" + card.lastFour();
```

Đặt nhánh đặc biệt trước, nhánh không guard cùng kiểu sau. Nếu đảo:

```java
// KHÔNG BIÊN DỊCH: nhánh có guard bị dominated.
case Card card -> "ANY_CARD";
case Card card when card.lastFour() == null -> "CARD_MISSING";
```

`case Card card` đầu tiên đã nhận mọi `Card` không null. Nhánh sau không thể được chọn.

**Không đánh đồng dominance với exhaustiveness:** dominance hỏi một nhánh có bị nhánh trước che không; exhaustiveness hỏi tất cả nhánh hợp lệ có đủ bao phủ miền dữ liệu cần thiết không. Một `switch` có thể thiếu exhaustiveness mà không có lỗi dominance, hoặc có `default` nhưng vẫn lỗi dominance.

## 6. `null` là trường hợp riêng, dù subtype đã được bao phủ

Cần ghi nhớ chính xác:

- `case Card card`, `case Transfer transfer`, `case Voucher voucher` xử lý các đối tượng **non-null** phù hợp.
- `null` không phải một đối tượng thuộc `Card`, `Transfer`, `Voucher`.
- Compiler có thể coi một `switch` expression exhaustive theo sealed hierarchy dù không viết `case null`.
- Ở runtime, nếu selector là `null` mà không có nhãn xử lý `null` thích hợp, `switch` thường ném `NullPointerException`, kể cả khi có `default` thông thường.

Nếu đầu vào null là tình huống hợp lệ, chọn một chính sách tường minh:

```java
static String safe(Payment payment) {
    return switch (payment) {
        case null -> "NO_PAYMENT";
        case Card c -> "CARD";
        case Transfer t -> "TRANSFER";
        case Voucher v -> "VOUCHER";
    };
}
```

Hoặc chủ động từ chối null:

```java
case null -> throw new IllegalArgumentException("payment is required");
```

Việc từ chối này là chính sách API, không phải điều compiler tự suy ra từ `sealed`.

**Lưu ý component null:** một `record Card(null)` vẫn là một đối tượng `Card` và sẽ khớp `case Card c`. Sealed hierarchy không bảo đảm component của record khác null. Nếu dùng `c.lastFour().length()`, cần bảo vệ component null trước; bài thực hành bên dưới có case riêng cho tình huống này.

## 7. Có nên viết `default` với sealed hierarchy?

Có thể, nhưng nên quyết định theo hợp đồng ứng dụng. Ví dụ:

```java
static String withDefault(Payment payment) {
    return switch (payment) {
        case Card c -> "CARD";
        case Transfer t -> "TRANSFER";
        default -> "OTHER";
    };
}
```

Ở đây `default` giúp expression exhaustive dù chưa ghi cụ thể `Voucher`. Nếu tương lai thêm permitted subtype `GiftCard`, nhánh đó cũng có thể được `default` nhận mà compiler không yêu cầu viết riêng. Điều này **hợp lý** khi ứng dụng thật sự cho phép fallback chung; nhưng có thể **nguy hiểm** khi subtype mới đòi hỏi nghiệp vụ riêng mà không ai chú ý.

So sánh:

| Cách thiết kế | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Liệt kê đủ nhánh subtype, **không có `default`** | Compiler giúp bắt subtype mới chưa xử lý khi biên dịch lại | Phải cập nhật logic khi hierarchy thay đổi |
| Có `default -> "UNKNOWN"` | Có chính sách fallback cho giá trị chưa phân loại | Dễ che nhánh mới bị quên |
| Có `default -> throw ...` | Không silently chấp nhận giá trị ngoài mong đợi | Vẫn không buộc viết logic riêng cho subtype mới ngay khi compile |
| `case Payment p` bao quát | Có biến kiểu `Payment` cho phần còn lại | Có thể làm các case subtype phía sau bị dominated |

Với miền nghiệp vụ đóng và quan trọng (trạng thái giao dịch, kết quả xác thực, loại thông điệp), thường đáng cân nhắc **không có `default`** để có kiểm tra compile-time mạnh hơn.

Tuy nhiên, không nên bỏ `default` chỉ vì thích một phong cách: trên một selector kiểu mở (`Object` hoặc interface không sealed), compiler có thể vẫn yêu cầu phương án bao phủ khác.

## 8. Sealed subtype lồng tầng và nhánh `non-sealed`

Một sealed hierarchy không bắt buộc dừng ở một tầng:

```java
sealed interface Vehicle permits Bicycle, MotorVehicle {}
record Bicycle(int gears) implements Vehicle {}

sealed interface MotorVehicle extends Vehicle permits Car, Bus {}
record Car(int seats) implements MotorVehicle {}
record Bus(int capacity) implements MotorVehicle {}
```

Có thể xử lý `Vehicle` bằng các case cho `Bicycle`, `Car` và `Bus` khi compiler có thể suy ra các nhánh đóng lồng nhau đã được bao phủ. Nếu chỉ viết `case Car c` và `case Bicycle b`, thì `Bus` còn thiếu. Một lựa chọn khác là `case MotorVehicle motor` để bao phủ cả `Car` và `Bus` nếu không cần chia nhỏ.

Với nhánh `non-sealed`, **không cần và thường không thể** liệt kê hết tất cả implementer tiềm năng:

```java
sealed interface Outcome permits Success, Failure, Later {}
non-sealed interface Later extends Outcome {}
```

Muốn `switch (Outcome)` exhaustive mà không cần default, dùng một case đủ bao phủ `Later`:

```java
case Later later -> "LATER";
```

Cách này hợp lệ cả với implementation `Later` được thêm trong tương lai. **Trade-off:** compiler giúp phát hiện subtype trực tiếp mới của `Outcome`, nhưng **không bắt bạn phân biệt từng implementation mới bên dưới nhánh `Later`**. Nếu cần mỗi loại `Later` có xử lý riêng, hãy cân nhắc giữ nhánh đó sealed thay vì `non-sealed`.

## 9. Chương trình Java 21 hoàn chỉnh: sealed switch không có default

Bài thực hành gồm hai cấu trúc:

1. `Payment`: sealed với ba record final, các case có `when` và nhánh không guard cuối cho từng subtype.
2. `Outcome`: sealed với hai record final và một interface `non-sealed` tên `Later`. Nhánh `case Later l` bao phủ các implementation của `Later`.

Chương trình có self-test với kết quả mong đợi, không cần JUnit hay thư viện ngoài.

**Tạo tệp `SealedSwitchExhaustiveDemo.java`:**

```java
public class SealedSwitchExhaustiveDemo {
    sealed interface Payment permits Card, Transfer, Voucher {}
    record Card(String lastFour) implements Payment {}
    record Transfer(String reference) implements Payment {}
    record Voucher(int points) implements Payment {}

    sealed interface Outcome permits Success, Failure, Later {}
    record Success(String message) implements Outcome {}
    record Failure(int code) implements Outcome {}
    non-sealed interface Later extends Outcome {}
    record Queued(String ticket) implements Later {}
    record Retried(int delaySeconds) implements Later {}

    static String paymentLabel(Payment payment) {
        return switch (payment) {
            case null -> "PAYMENT_NULL";
            case Card c when c.lastFour() == null -> "CARD_MISSING";
            case Card c -> "CARD:" + c.lastFour();
            case Transfer t -> "TRANSFER:" + t.reference();
            case Voucher v when v.points() < 0 -> "VOUCHER_INVALID";
            case Voucher v -> "VOUCHER:" + v.points();
        };
    }

    static String outcomeLabel(Outcome outcome) {
        return switch (outcome) {
            case null -> "OUTCOME_NULL";
            case Success s -> "SUCCESS:" + s.message();
            case Failure f -> "FAILURE:" + f.code();
            case Later l -> "LATER:" + l.getClass().getSimpleName();
        };
    }

    static void check(String name, String actual, String expected) {
        if (!actual.equals(expected)) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(name + "=" + actual);
    }

    public static void main(String[] args) {
        check("null-payment", paymentLabel(null), "PAYMENT_NULL");
        check("card-null", paymentLabel(new Card(null)), "CARD_MISSING");
        check("card", paymentLabel(new Card("1234")), "CARD:1234");
        check("transfer", paymentLabel(new Transfer("TR-7")),
                "TRANSFER:TR-7");
        check("voucher-negative", paymentLabel(new Voucher(-1)),
                "VOUCHER_INVALID");
        check("voucher-zero", paymentLabel(new Voucher(0)), "VOUCHER:0");
        check("voucher", paymentLabel(new Voucher(50)), "VOUCHER:50");

        check("null-outcome", outcomeLabel(null), "OUTCOME_NULL");
        check("success", outcomeLabel(new Success("saved")),
                "SUCCESS:saved");
        check("failure", outcomeLabel(new Failure(404)), "FAILURE:404");
        check("queued", outcomeLabel(new Queued("Q-1")), "LATER:Queued");
        check("retried", outcomeLabel(new Retried(10)), "LATER:Retried");

        System.out.println("ALL CASES PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 SealedSwitchExhaustiveDemo.java
java SealedSwitchExhaustiveDemo
```

**Standard output chính xác:**

```text
null-payment=PAYMENT_NULL
card-null=CARD_MISSING
card=CARD:1234
transfer=TRANSFER:TR-7
voucher-negative=VOUCHER_INVALID
voucher-zero=VOUCHER:0
voucher=VOUCHER:50
null-outcome=OUTCOME_NULL
success=SUCCESS:saved
failure=FAILURE:404
queued=LATER:Queued
retried=LATER:Retried
ALL CASES PASSED
```

### Giải thích output

- `paymentLabel(null)`: vào `case null`, không thử giả định `null` là một trong ba subtype.
- `new Card(null)`: nhánh `Card` có guard bắt component `lastFour == null` trước khi xử lý chung.
- `new Card("1234")`: guard null sai, vào nhánh `Card` không guard.
- `new Transfer("TR-7")`: khớp nhánh `Transfer`.
- `new Voucher(-1)`: khớp guard số âm; `0` và `50` đi vào nhánh `Voucher` tổng quát. Do có nhánh tổng quát này, `Voucher` đã được bao phủ đầy đủ cho exhaustiveness.
- `Outcome` có `Success`, `Failure` hoặc `Later`, nên ba nhánh tương ứng exhaustive. `Queued` và `Retried` đều thuộc `Later`, trả `LATER:Queued`, `LATER:Retried`.
- `check` dùng `equals` để đối chiếu expected result. Nếu một kết quả sai, chương trình ném `AssertionError`; `ALL CASES PASSED` chỉ in sau khi tất cả 12 kiểm tra thành công.

Không một `switch` expression nào trong chương trình dùng `default`, vì các kiểu sealed đã được bao phủ bởi type patterns, kết hợp `case null` cho đầu vào null.

## 10. Ma trận kiểm thử cần có khi sealed hierarchy mở rộng

| Input | Pattern kỳ vọng | Lý do cần test |
| --- | --- | --- |
| `null` | `case null` | Exhaustiveness không đồng nghĩa tự động nhận null |
| `new Card(null)` | `Card` có guard | Component của record có thể null |
| `new Card("1234")` | `Card` không guard | Guard false vẫn có nhánh xử lý |
| `new Transfer("TR-7")` | `Transfer` | Subtype trực tiếp thứ hai được bao phủ |
| `new Voucher(-1)` | `Voucher` có guard | Miền âm riêng |
| `new Voucher(0)` | `Voucher` không guard | Biên zero và phần còn lại |
| `new Success("saved")` | `Success` | Subtype trực tiếp |
| `new Failure(404)` | `Failure` | Subtype trực tiếp |
| `new Queued("Q-1")` | `Later` | Nhánh non-sealed được type pattern bao phủ |
| `new Retried(10)` | `Later` | Implementation khác cũng được bao phủ |

**Hai loại kiểm thử có vai trò khác nhau:**

- **Kiểm tra bằng compiler**: cố ý bỏ `case Transfer` hoặc bổ sung permitted subtype mới mà không cập nhật switch, sau đó biên dịch lại. Compiler báo thiếu exhaustiveness.
- **Kiểm tra runtime**: xác nhận khi các case đầy đủ thì đúng giá trị được chọn, guard đúng thứ tự, kết quả có ý nghĩa và null được xử lý đúng.

Thêm `case Transfer` chỉ để compiler hết lỗi chưa chứng minh code xử lý logic chuyển khoản đúng. Vì thế vẫn cần test riêng cho `Transfer`.

## 11. `switch` expression, enhanced statement và thay đổi module

Trong Java 21, **`switch` expression** phải exhaustive. **Enhanced `switch` statement** (chẳng hạn statement dùng case pattern) cũng có yêu cầu exhaustive; không được suy luận rằng statement có thể thiếu case chỉ vì nó không trả giá trị.

```java
static void printPayment(Payment payment) {
    switch (payment) {
        case Card c -> System.out.println("Card");
        case Transfer t -> System.out.println("Transfer");
        case Voucher v -> System.out.println("Voucher");
    }
}
```

Đây là phương thức **minh họa** cần đặt trong class có khai báo `Payment` như bên trên. Nó là một enhanced switch statement có đủ các subtype, không cần default. Dù vậy, nếu truyền `null`, sự thiếu `case null` vẫn có thể dẫn đến `NullPointerException`.

Một lưu ý chuyên sâu về **separate compilation**: tính exhaustive được compiler kiểm tra dựa trên hierarchy mà nó thấy **khi biên dịch**. Nếu dependency thay đổi subtype mà mã client cũ không được biên dịch lại phù hợp, một `switch` từng exhaustive có thể gặp trạng thái bất ngờ tại runtime (ví dụ `MatchException` theo các điều kiện của đặc tả Java 21). Vì vậy khi thay đổi các lớp sealed công khai trong nhiều module, hãy build lại và chạy test các module phụ thuộc; exhaustiveness compile-time **không phải lời đảm bảo mọi bản binary không đồng bộ đều an toàn**.

## 12. Lỗi phổ biến và cách sửa

| Lỗi hoặc hiểu lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Thiếu `case` cho một permitted subtype | `switch` expression/enhanced statement có thể không biên dịch | Liệt kê đủ subtype hoặc fallback có chủ đích |
| Viết chỉ `case Voucher v when v.points() < 0` | Voucher không âm chưa được bao phủ | Thêm `case Voucher v` không guard |
| Đặt `case Card c` trước `case Card c when ...` | Nhánh đặc biệt bị dominated | Đặt guard trước nhánh tổng quát |
| Tin sealed nghĩa là mọi input đều non-null | Bỏ sót selector null và component null | Có chính sách `case null`; bảo vệ component |
| Cứ thêm `default` cho mọi sealed switch | Có thể che subtype mới chưa được xử lý riêng | Cân nhắc exhaustive không default |
| Cho rằng `non-sealed Later` không cần case vì hiện chỉ có hai implementation | Compiler không suy ra đủ mọi implementation của nhánh mở chỉ từ danh sách đang thấy | Dùng `case Later l` bao phủ nhánh |
| Cho rằng `permits` liệt kê tất cả con/cháu sâu vô hạn | Nhầm subtype trực tiếp với subtype gián tiếp | Hiểu từng nhánh `sealed`/`final`/`non-sealed` |
| Quên `final`, `sealed` hoặc `non-sealed` trên class subtype trực tiếp thông thường | Không đáp ứng luật kế thừa sealed | Chỉ rõ chính sách; record mặc nhiên final |
| Viết class mới trực tiếp `implements Payment` ngoài danh sách | Bị compiler từ chối | Cập nhật `permits` và các switch liên quan có chủ đích |
| Dùng Java 17 để biên dịch pattern `switch` Java 21 | Không hỗ trợ cú pháp chính thức như `when` | Dùng JDK 21+ và `javac --release 21` |
| Nhầm dominance với exhaustiveness | Sửa sai thứ tự case nhưng vẫn thiếu nhánh, hoặc thêm default nhưng case vẫn dominated | Phân tích từng quy tắc riêng |
| Nghĩ compiler bảo đảm xử lý nghiệp vụ đúng | Code vẫn có thể trả nhầm thông tin trong một case hợp lệ | Unit test và test biên cho từng subtype |

## 13. Bài tập tự luyện

1. Tạo `sealed interface Event permits Created, Deleted` với hai record `Created(String id)`, `Deleted(String id)`. Viết `switch` expression trả kết quả cho hai subtype mà không có `default`; giải thích vì sao compiler chấp nhận.
2. Bỏ nhánh `case Deleted d` trong bài 1, biên dịch, đọc lỗi về exhaustiveness. Thêm lại nhánh bị thiếu thay vì vội viết default.
3. Thêm `record Updated(String id) implements Event` và bổ sung `Updated` vào `permits`. Quan sát compiler yêu cầu cập nhật `switch` cũ ra sao. Viết test cho subtype mới.
4. Viết `case Created c when c.id() == null` rồi `case Created c` để xử lý component null. Đảo thứ tự hai nhánh, giải thích lỗi dominance.
5. Thử `switch` không có `case null` trên `Event`. Dù switch exhaustive với non-null, giải thích hành vi khi truyền `null`. Thêm nhánh rõ chính sách.
6. Tạo hierarchy nhiều tầng, trong đó `sealed interface Vehicle` có một subtype `sealed interface MotorVehicle`. Viết case cho các nhánh lá. Thử thêm một nhánh lá mới rồi biên dịch lại.
7. Tạo một nhánh `non-sealed interface Extra extends Event` và thêm nó vào `permits`. Dùng `case Extra e` để bao phủ các implementation hiện tại và tương lai; so sánh với việc cố liệt kê từng implementation.
8. Viết hai phiên bản cho một sealed switch: một bản liệt kê đủ case không default, một bản dùng default. Thêm một permitted subtype rồi so sánh khả năng compiler yêu cầu sửa mã.
9. Chuyển `paymentLabel` thành một `switch` expression trả record `Decision(String code, String message)`. Viết assertion so sánh record thay vì chỉ kiểm tra chuỗi; bảo đảm mỗi subtype có hành vi đúng.
10. Chạy `SealedSwitchExhaustiveDemo`, đối chiếu toàn bộ 13 dòng standard output. Thử `Voucher(-1)`, `Voucher(0)` và `Card(null)` để giải thích vì sao guard không thể thay thế nhánh không guard.

**Tiêu chí hoàn thành:** tự thiết kế được một sealed hierarchy có `permits` hợp lệ; hiểu vai trò `final`/`sealed`/`non-sealed`; viết `switch` Java 21 exhaustive không dùng default khi thích hợp; giải thích xử lý `null`, guard và các cảnh báo khi hierarchy mở rộng; có test compile-time lẫn runtime.

**Tài liệu chính thức:**

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS Java SE 21 — Switch Statements (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [JLS Java SE 21 — Switch Expressions (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
