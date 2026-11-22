# Thành viên không thể ghi đè và lớp không thể kế thừa trong Java

Trong Java, từ khóa `final` có thể được dùng để **cố định một phần của thiết kế kế thừa**:

- Đặt `final` trên **phương thức** để lớp con không thể ghi đè (*override*) phương thức đó.
- Đặt `final` trên **lớp** để không lớp nào có thể `extends` lớp ấy.
- Đặt `final` trên **biến hoặc field** để không được gán lại giá trị sau khi đã gán hợp lệ.

Ba ý nghĩa này liên quan đến sự ổn định nhưng **không thay thế nhau**. Đặc biệt, `final class` không tự làm mọi dữ liệu bên trong bất biến; `final method` không ngăn phương thức thay đổi trạng thái; `final field` không khiến đối tượng được tham chiếu trở nên bất biến.

Mục tiêu của bài là hiểu chính xác **điều gì bị cấm tại lúc biên dịch**, điều gì vẫn có thể làm, và cách dùng `final` để giữ những quy tắc mà lớp con không được phá vỡ.

## 1. Phương thức `final`: kế thừa được nhưng không override được

Một phương thức instance được đánh dấu `final` vẫn có thể được **gọi và kế thừa** bởi lớp con, nhưng lớp con **không được cung cấp implementation mới với cùng chữ ký override**.

~~~java
class Account {
    private String owner;

    Account(String owner) {
        this.owner = owner;
    }

    public final String getOwner() {
        return owner;
    }
}

class SavingsAccount extends Account {
    SavingsAccount(String owner) {
        super(owner);
    }

    // Không hợp lệ:
    // @Override
    // public String getOwner() {
    //     return "Người khác";
    // }
}
~~~

~~~java
SavingsAccount account = new SavingsAccount("An");
System.out.println(account.getOwner()); // An
~~~

Mặc dù `SavingsAccount` không thể **override** `getOwner()`, nó vẫn được sử dụng phương thức được kế thừa. `final` ngăn thay phần triển khai của phương thức; nó **không** làm biến mất API khỏi lớp con.

Bảng phân biệt:

| Hành động trên phương thức `final` của lớp cha | Có được không? |
| --- | --- |
| Gọi từ đối tượng lớp con | Có, nếu quyền truy cập cho phép |
| Lớp con kế thừa implementation | Có, theo quy tắc kế thừa Java |
| Override cùng chữ ký trong lớp con | Không |
| Lớp con thêm phương thức **overload** khác danh sách tham số | Có |
| Phương thức `final` sửa field hoặc gọi phương thức khác | Có |
| Phương thức `final` gọi một hook overridable | Có, nhưng cần thiết kế cẩn thận |

**Ghi đè (override)** và **nạp chồng (overload)** không giống nhau:

~~~java
class Parent {
    public final void send(String text) {
        System.out.println("Gửi: " + text);
    }
}

class Child extends Parent {
    // Overload: tham số khác, hoàn toàn hợp lệ.
    public void send(String text, int times) {
        for (int i = 0; i < times; i++) {
            send(text); // Gọi phương thức final kế thừa từ Parent.
        }
    }

    // LỖI nếu viết:
    // @Override
    // public void send(String text) { }
}
~~~

`send(String, int)` là phương thức mới với chữ ký khác. Nó không sửa phần triển khai của `send(String)`.

## 2. Lớp `final`: không thể làm superclass

Khi khai báo:

~~~java
final class Receipt {
    private final String code;

    Receipt(String code) {
        this.code = code;
    }

    String getCode() {
        return code;
    }
}
~~~

Bạn vẫn tạo đối tượng được:

~~~java
Receipt receipt = new Receipt("RC-001");
System.out.println(receipt.getCode()); // RC-001
~~~

Nhưng không thể khai báo lớp con:

~~~java
// LỖI BIÊN DỊCH:
// class SpecialReceipt extends Receipt {
// }
~~~

Một lớp `final` có thể tự `extends` lớp cha và `implements` các interface:

~~~java
interface Printable {
    void print();
}

class Document {
    String category() {
        return "Tài liệu";
    }
}

final class Invoice extends Document implements Printable {
    @Override
    public void print() {
        System.out.println(category() + ": hóa đơn");
    }
}
~~~

`Invoice` được **kế thừa** từ `Document`, nhưng **không cho lớp khác kế thừa từ Invoice**. Vì thế nhận định “lớp final không liên quan được đến kế thừa” là sai: nó có thể đứng **ở cuối một nhánh** kế thừa.

Sơ đồ:

~~~mermaid
classDiagram
    class Document {
        +category() String
    }
    class Printable {
        <<interface>>
        +print() void
    }
    class Invoice {
        <<final>>
        +print() void
    }
    Document <|-- Invoice
    Printable <|.. Invoice
~~~

`Invoice` vẫn có thể được sử dụng thông qua biến `Document` hoặc `Printable`. Đánh dấu `final` không loại bỏ đa hình đối với các lớp/interface cha.

## 3. Ví dụ Java chạy được: khóa quy trình chung, mở điểm chuyên biệt hóa

Tình huống: ứng dụng có nhiều kênh thanh toán. Mỗi yêu cầu đều cần kiểm tra số tiền trước khi gọi kênh thanh toán cụ thể, và phải trả thông tin giao dịch theo cấu trúc thống nhất.

Ta thiết kế:

- `PaymentChannel` là hợp đồng cho bên sử dụng.
- `PaymentProcessor` là lớp cha **abstract**, chứa phương thức `process()` **final** để giữ quy trình chung.
- `charge()` là điểm mở rộng `protected abstract`; lớp con thực hiện bước xử lý thanh toán.
- `CardProcessor` là lớp **final**: hoàn thiện xử lý thẻ và không cho subclass thay đổi tiếp.
- `BankTransferProcessor` là một lớp cụ thể khác, cho thấy nhiều implementation có thể cùng dùng quy trình chung.

Lưu toàn bộ vào `FinalInheritanceDemo.java`, chạy với **Java 11+**.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class FinalInheritanceDemo {

    interface PaymentChannel {
        Receipt process(BigDecimal amount);
    }

    static final class Receipt {
        private final String provider;
        private final BigDecimal amount;
        private final String transactionId;

        Receipt(String provider, BigDecimal amount, String transactionId) {
            this.provider = Objects.requireNonNull(provider);
            this.amount = Objects.requireNonNull(amount);
            this.transactionId = Objects.requireNonNull(transactionId);
        }

        String getProvider() {
            return provider;
        }

        BigDecimal getAmount() {
            return amount;
        }

        String getTransactionId() {
            return transactionId;
        }
    }

    static abstract class PaymentProcessor implements PaymentChannel {
        private final String provider;

        protected PaymentProcessor(String provider) {
            String checked = Objects.requireNonNull(provider).trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException("Tên kênh không hợp lệ");
            }
            this.provider = checked;
        }

        // Template Method: lớp con không được bỏ qua quy trình kiểm tra.
        @Override
        public final Receipt process(BigDecimal amount) {
            Objects.requireNonNull(amount, "amount");

            if (amount.signum() <= 0) {
                throw new IllegalArgumentException(
                        "Số tiền phải lớn hơn 0");
            }

            String transactionId = Objects.requireNonNull(
                    charge(amount), "transactionId");
            if (transactionId.isBlank()) {
                throw new IllegalStateException("Thiếu mã giao dịch");
            }

            return new Receipt(provider, amount, transactionId);
        }

        // Mỗi lớp con phải định nghĩa cách xử lý riêng.
        protected abstract String charge(BigDecimal amount);
    }

    // Vừa kế thừa một lớp cha, vừa không cho kế thừa tiếp.
    static final class CardProcessor extends PaymentProcessor {
        CardProcessor() {
            super("CARD");
        }

        @Override
        protected String charge(BigDecimal amount) {
            System.out.println("Xử lý thẻ: " + amount.toPlainString());
            return "CARD-TX-001";
        }

        // Không hợp lệ nếu bỏ comment:
        // @Override
        // public Receipt process(BigDecimal amount) {
        //     return null;
        // }
    }

    static class BankTransferProcessor extends PaymentProcessor {
        BankTransferProcessor() {
            super("BANK");
        }

        @Override
        protected String charge(BigDecimal amount) {
            System.out.println("Chuyển khoản: " + amount.toPlainString());
            return "BANK-TX-002";
        }
    }

    public static void main(String[] args) {
        List<PaymentChannel> channels = List.of(
                new CardProcessor(), new BankTransferProcessor());

        for (PaymentChannel channel : channels) {
            Receipt receipt = channel.process(
                    new BigDecimal("150000"));

            System.out.println(
                    receipt.getProvider() + " -> "
                    + receipt.getTransactionId());
        }

        try {
            channels.get(0).process(BigDecimal.ZERO);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac FinalInheritanceDemo.java
java FinalInheritanceDemo
~~~

Kết quả:

~~~text
Xử lý thẻ: 150000
CARD -> CARD-TX-001
Chuyển khoản: 150000
BANK -> BANK-TX-002
Từ chối: Số tiền phải lớn hơn 0
~~~

Ví dụ chỉ mô phỏng thanh toán bằng chuỗi cố định và console; chưa có kết nối ngân hàng hoặc đảm bảo giao dịch thực tế. Mục tiêu là quan sát quy tắc kế thừa và phần mã được bảo vệ bởi `final`.

### Điều gì được cố định, điều gì được mở rộng?

| Thành phần | Vai trò | Có override ở lớp con? |
| --- | --- | --- |
| `PaymentProcessor.process()` | Kiểm tra số tiền, gọi `charge`, chuẩn hóa Receipt | **Không**, vì `final` |
| `PaymentProcessor.charge()` | Hợp đồng để từng kênh thực thi | **Có**, thậm chí bắt buộc ở lớp con concrete |
| `CardProcessor` | Một loại xử lý thanh toán cụ thể | Không thể có subclass vì class `final` |
| `BankTransferProcessor` | Loại xử lý cụ thể khác | Có thể được kế thừa thêm vì chưa `final` |
| `Receipt` | Dữ liệu giao dịch tạo ra sau xử lý | Không thể kế thừa vì class `final` |

**Chi tiết kỹ thuật quan trọng:** `process()` không override được, nhưng lời gọi `charge(amount)` **bên trong** nó vẫn chọn implementation của instance thực tế. Do đó `final` chỉ khóa phần thân `process`, không đóng toàn bộ khả năng đa hình của lớp.

~~~mermaid
sequenceDiagram
    actor App
    participant P as PaymentProcessor.process() final
    participant C as CardProcessor.charge()
    App->>P: process(150000)
    P->>P: kiểm tra amount > 0
    P->>C: charge(150000)
    C-->>P: "CARD-TX-001"
    P->>P: new Receipt(...)
    P-->>App: Receipt
~~~

Sơ đồ biểu diễn **các vai trò trong một lần gọi trên cùng instance CardProcessor**: `PaymentProcessor.process()` là mã kế thừa đang chạy, còn `CardProcessor.charge()` là mã được dispatch động. Không có một instance `PaymentProcessor` độc lập được tạo thêm.

## 4. Vì sao một phương thức nên là `final`?

Dùng `final` trên phương thức khi phần hành vi đó được xem như **quy tắc cố định của lớp cha**: ví dụ một trình tự kiểm tra trước khi thao tác hoặc một cách biểu diễn định danh không được thay.

Các lợi ích thiết kế có thể có:

1. Ngăn subclass bỏ qua logic quan trọng bằng cách override phương thức.
2. Cho người đọc biết đây là API có implementation ổn định trong cây kế thừa.
3. Giữ một quy trình dùng chung trong khi cho phép chuyên biệt hóa tại các hook riêng.
4. Giảm số cách lớp con có thể làm sai một phần hợp đồng lớp cha.

Tuy nhiên, `final` **không phải biện pháp bảo mật tuyệt đối**. Nếu lớp cha công khai các phương thức thay đổi trạng thái khác, hoặc hook overridable có hành vi nguy hiểm, một subclass vẫn có thể tạo tác động sai. Ví dụ trong chương trình trên, `charge()` có thể trả kết quả hợp lệ về mặt cú pháp nhưng thực tế không thu tiền. Phải thiết kế và kiểm chứng hợp đồng của mọi điểm mở rộng.

Cũng không nên đánh dấu mọi phương thức `final` theo thói quen rồi vô tình làm khó các biến thể hợp lệ. Trước khi khóa một phương thức, hãy xác định **lý do nghiệp vụ hoặc ràng buộc thiết kế** cụ thể.

## 5. Vì sao một lớp nên là `final`?

Dùng `final class` khi thiết kế muốn **đóng khả năng chuyên biệt hóa bằng kế thừa**:

- Kiểu dữ liệu giá trị (value type) có invariant chặt, không muốn subclass mở rộng và thay đổi kỳ vọng.
- Một implementation đã hoàn chỉnh, không cung cấp hợp đồng mở rộng cho subclass.
- Một đối tượng tiện ích hoặc cấu phần chỉ muốn được **sử dụng/ủy quyền** thay vì kế thừa.
- Một kiểu có quy tắc về danh tính, bình đẳng hoặc xử lý nội bộ khó bảo đảm nếu subclass tùy ý thay đổi hành vi.

Ví dụ lớp `Receipt` ở trên không có setter và các field giữ `String`/`BigDecimal` bất biến. Kết hợp với kiểm tra trong constructor, đây là một kiểu dữ liệu **bất biến theo trạng thái quan sát được** trong ví dụ.

Nhưng cần phân biệt nguyên nhân:

~~~java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
~~~

~~~java
Counter counter = new Counter();
counter.increment();
System.out.println(counter.getValue()); // 1
~~~

`Counter` là lớp `final` **nhưng đối tượng vẫn mutable**. `final` ở cấp class chỉ ngăn `extends Counter`, không cấm cập nhật `value`.

Tương tự, một lớp không `final` vẫn có thể thiết kế bất biến nếu bảo vệ tất cả trạng thái đúng cách; bất biến dữ liệu và hạn chế kế thừa là **hai quyết định khác nhau**.

## 6. Ba vị trí của `final` dễ bị lẫn

| Vị trí | Ví dụ | Điều bị cấm | Điều vẫn có thể xảy ra |
| --- | --- | --- | --- |
| Class | `final class Receipt` | Lớp khác `extends Receipt` | Tạo object, gọi method, sửa state nếu class cho phép |
| Method | `public final void process()` | Subclass override cùng chữ ký | Gọi từ subclass, overload với tham số khác |
| Biến/field | `final List<String> items` | Gán lại `items` sau khi đã gán | `items.add(...)` nếu list mutable |

Ví dụ `final` trên biến tham chiếu:

~~~java
import java.util.ArrayList;
import java.util.List;

final List<String> tags = new ArrayList<>();
tags.add("Java");       // Hợp lệ: cập nhật đối tượng List.
// tags = new ArrayList<>(); // Lỗi: không được gán lại biến final.
~~~

Với kiểu nguyên thủy:

~~~java
final int maxAttempts = 3;
// maxAttempts = 5; // Lỗi biên dịch.
~~~

Với tham số phương thức:

~~~java
void render(final String message) {
    // message = "Khác"; // Lỗi: gán lại tham số final.
    System.out.println(message);
}
~~~

Với field không có giá trị tại chỗ khai báo:

~~~java
class User {
    private final String id;

    User(String id) {
        this.id = id; // Gán một lần trong constructor.
    }
}
~~~

Một `blank final field` phải được gán đúng theo quy tắc khởi tạo của Java trên mọi đường khởi tạo hoàn tất bình thường; không được gán lại sau đó. Field `final` tham chiếu tới một đối tượng mutable không khóa trạng thái bên trong đối tượng.

## 7. Thành viên nào không thể override dù không viết `final`?

Không phải thành viên nào của lớp cha cũng là điểm override hợp lệ.

| Thành viên | Có override đúng nghĩa? | Giải thích |
| --- | --- | --- |
| Instance method `public/protected`, không final, không static | Thường có | Nếu có quyền truy cập và chữ ký phù hợp |
| Instance method `final` | Không | Compiler cấm override |
| Method `private` | Không | Không được kế thừa theo cách cho phép override |
| Method `static` | Không | Có thể bị **hide** bởi static method ở subclass, trừ các ràng buộc như final |
| Constructor | Không | Constructor không phải method được kế thừa |
| Field, kể cả `final field` | Không | Field chỉ có thể bị **hide** (che tên), không override động |

### `private` và `static` không phải là override

~~~java
class Parent {
    private void internal() {
        System.out.println("Parent internal");
    }

    static void info() {
        System.out.println("Parent info");
    }
}

class Child extends Parent {
    // Đây là phương thức MỚI, không override private method ở Parent.
    public void internal() {
        System.out.println("Child internal");
    }

    // Đây là static method hiding, không phải instance override.
    static void info() {
        System.out.println("Child info");
    }
}
~~~

~~~java
Parent p = new Child();
p.info();     // Parent info (static ràng buộc theo kiểu khai báo)
// p.internal(); // Không biên dịch: Parent.internal() là private.

Child c = new Child();
c.internal(); // Child internal
~~~

Nên gọi static method qua tên class (`Parent.info()`, `Child.info()`) để tránh nhầm với đa hình động.

Nếu lớp cha khai báo `static final void info()`, lớp con không thể khai báo static method cùng chữ ký để hide. Với `private final void internal()`, subclass vẫn có thể khai báo phương thức mới cùng tên/chữ ký theo quy tắc truy cập, vì đó **không phải override** phương thức private ở cha.

### Không thể kết hợp `abstract` và `final` trên cùng class/method

Hai từ khóa có yêu cầu đối lập:

- `abstract method` yêu cầu subclass cung cấp implementation.
- `final method` ngăn subclass cung cấp implementation bằng override.
- `abstract class` có thể cần/cho phép subclass hoàn thiện.
- `final class` ngăn tạo subclass.

Do đó các khai báo sau **không hợp lệ**:

~~~java
// abstract final class Impossible { }

// abstract class Base {
//     abstract final void execute();
// }
~~~

Trong khi đó, **abstract class vẫn được chứa method final đã triển khai** — chính là thiết kế `PaymentProcessor.process()` ở ví dụ chạy được.

## 8. Nếu cần khóa một số phương thức nhưng vẫn cho phép mở rộng?

Đó là tình huống phổ biến. Có thể dùng một lớp cha **không final** hoặc `abstract class`, rồi đánh dấu đúng các điểm không được override:

~~~java
abstract class ImportJob {
    // Giữ nguyên quy trình.
    public final void run() {
        validate();
        parse();
        save();
    }

    private void validate() {
        System.out.println("Kiểm tra đầu vào chung");
    }

    protected abstract void parse();
    protected abstract void save();
}
~~~

~~~java
class CsvImportJob extends ImportJob {
    @Override
    protected void parse() {
        System.out.println("Đọc CSV");
    }

    @Override
    protected void save() {
        System.out.println("Lưu dữ liệu CSV");
    }
}
~~~

`ImportJob.run()` cố định các bước; subclass chuyên biệt hóa `parse()` và `save()`. Đây là biến thể của mẫu **Template Method**.

Quan trọng: nếu `parse()` hay `save()` ném ngoại lệ hoặc sửa trạng thái không hợp lệ, phương thức `final run()` **không tự hoàn tác** các thay đổi. `final` giải quyết **quyền override**, không thay thế kiểm soát lỗi, giao dịch hay đồng bộ.

## 9. Những lựa chọn thiết kế thay thế `final` trên class

Một lớp `final` áp đặt quy tắc **không có subclass**. Nhưng đôi khi bạn muốn cho phép **một số kiểu con được chọn** mà không mở hoàn toàn.

Từ **Java 17**, Java hỗ trợ `sealed class`:

~~~java
// Ví dụ riêng cho Java 17+, không thuộc bản demo Java 11.
sealed class PaymentMethod permits Cash, Card {
}

final class Cash extends PaymentMethod {
}

final class Card extends PaymentMethod {
}
~~~

Khác nhau:

| Thiết kế | Ai có thể kế thừa? |
| --- | --- |
| `class Base` (không final/sealed) | Các lớp phù hợp quyền truy cập và quy tắc ngôn ngữ |
| `final class Base` | Không ai |
| `sealed class Base permits A, B` | Chỉ các lớp được phép trực tiếp; các subclass phải khai báo `final`, `sealed` hoặc `non-sealed` theo quy tắc |
| `abstract class Base` | Có thể kế thừa; bản thân Base không được `new` trực tiếp |

Đừng chọn `sealed` chỉ để thay một chữ khóa. Nó hữu ích khi thực sự có **tập phân loại hữu hạn và chủ đích**. Mã minh họa chính ở phần 3 chỉ cần Java 11; đoạn `sealed` này cần Java 17 trở lên.

Khi mục tiêu là thay đổi hành vi có thể hoán đổi, **composition + interface** cũng là lựa chọn đáng cân nhắc: thay vì subclass một class `final`, hãy truyền một đối tượng chiến lược vào constructor. `final` không cấm một class **sử dụng** đối tượng khác để thực hiện công việc.

## 10. Các lỗi biên dịch và suy luận sai thường gặp

| Tình huống | Kết luận đúng |
| --- | --- |
| `class B extends FinalA` với `FinalA` là `final class` | Lỗi biên dịch: không thể kế thừa |
| Override `public final void f()` trong subclass | Lỗi biên dịch: không thể override |
| Tạo `new FinalA()` khi constructor truy cập được | Hợp lệ |
| Class `final` implement interface | Hợp lệ |
| Abstract class có một method `final` | Hợp lệ |
| Một method vừa `abstract` vừa `final` | Không hợp lệ |
| Overload một `final method` bằng tham số khác | Hợp lệ |
| `final List<T>` rồi gọi `add()` | Có thể hợp lệ nếu List mutable |
| `private` method lớp cha và method cùng tên ở subclass | Không phải override |
| `static` method cùng tên/chữ ký ở subclass | Hiding nếu hợp lệ, không phải override |
| Dùng `final` để bảo đảm thread-safety | Không đủ; phải xem cả cách truy cập và thay đổi dữ liệu |
| “Final class luôn immutable” | Sai: `Counter` là phản ví dụ |

### Một số trường hợp lỗi có ích để nhận diện

~~~java
final class Locked {
    void work() {}
}

// class CannotExtend extends Locked {} // ERROR

class Base {
    public final void execute() {}
}

class Derived extends Base {
    // @Override
    // public void execute() {} // ERROR

    // Overload vẫn được phép:
    public void execute(int count) {
        for (int i = 0; i < count; i++) {
            execute();
        }
    }
}
~~~

Lý do của lỗi nằm ở **quy tắc kiểu tại thời điểm biên dịch**, không phải vì JVM phát hiện subclass hoạt động sai sau khi đã chạy. Dùng `@Override` khi cố tình override các phương thức được phép là thói quen tốt để compiler kiểm tra giúp.

## 11. Khi nào không nên dùng `final`?

`final` nên diễn đạt một **quyết định thiết kế**. Nếu ứng dụng cần cho đối tượng bên thứ ba mở rộng một API để xử lý đúng nhiều biến thể, việc khóa class/method quá sớm có thể làm API khó dùng hoặc buộc người dùng tạo vòng vo.

Một số dấu hiệu nên xem lại:

- Phần hành vi thực sự cần override, nhưng lớp cha lại khóa bằng `final` mà không cung cấp hook hay abstraction khác.
- Hệ thống mở rộng chức năng thường xuyên và cần thay implementation thông qua interface/strategy, nhưng các phụ thuộc đều gắn vào lớp concrete.
- Bạn dùng inheritance chỉ để tái sử dụng vài dòng tiện ích trong khi quan hệ “is-a” không đúng.
- Bạn cho rằng đánh dấu `final` sẽ tự khắc phục tính đồng thời, bảo mật, bất biến hoặc transaction.

Một quy tắc thực tế: **khóa những phần buộc phải ổn định; mở rộng tại những điểm có hợp đồng rõ ràng**. Với miền nghiệp vụ cần thay đổi linh hoạt, ưu tiên interface/composition hoặc một hook được kiểm soát hơn việc override tùy ý cả quy trình.

## 12. Tự kiểm tra

**Câu 1.** Một method `final` có được lớp con gọi không?

**Đáp án:** Có, nếu quyền truy cập cho phép. Lớp con không được **override** phần triển khai, nhưng có thể **kế thừa và sử dụng**.

**Câu 2.** `final class Printer implements Printable` có hợp lệ không?

**Đáp án:** Có. `final` cấm class khác `extends Printer`, còn `implements Printable` cho biết `Printer` đáp ứng hợp đồng của interface.

**Câu 3.** Trong ví dụ thanh toán, tại sao `process()` là `final` nhưng `CardProcessor.charge()` vẫn được gọi?

**Đáp án:** `process()` là mã chung được kế thừa, không bị override. Nó gọi một hook `charge()` cho phép/đòi hỏi lớp con triển khai; Java dispatch hook này theo kiểu runtime của đối tượng.

**Câu 4.** `final List<String> names = new ArrayList<>(); names.add("An");` có biên dịch không?

**Đáp án:** Có. Không có phép **gán lại** biến `names`; lời gọi `add` làm thay đổi danh sách mutable mà nó tham chiếu.

**Câu 5.** Phương thức `private void save()` trong lớp cha có thể được subclass override không?

**Đáp án:** Không. Subclass có thể khai báo phương thức khác cùng tên/chữ ký ở những trường hợp hợp lệ, nhưng phương thức đó không override phương thức `private` của cha.

**Câu 6.** Một lớp `final` có thể đồng thời là `abstract` không?

**Đáp án:** Không. `final` ngăn kế thừa, trong khi `abstract` chỉ ra một kiểu không được khởi tạo trực tiếp và dành cho lớp con hoàn thiện/sử dụng.

**Câu 7.** Muốn lớp cha giữ trình tự `validate → execute → audit`, đồng thời mỗi subclass được triển khai `execute` khác nhau, nên đặt `final` ở đâu?

**Đáp án:** Đặt `final` trên phương thức điều phối trình tự, và cung cấp `protected abstract` hoặc một hook phù hợp cho `execute`. Kiểm soát ngoại lệ và cập nhật trạng thái riêng, vì `final` không tự tạo tính nguyên tử.

**Câu 8.** Nếu chỉ muốn có đúng ba subclass cụ thể được phép trực tiếp mở rộng một lớp, nên cân nhắc gì ở Java 17+?

**Đáp án:** Cân nhắc `sealed class` với `permits`. Khác với `final class`, `sealed class` cho phép một tập subclass đã chỉ định theo quy tắc của Java.

**Ghi nhớ:** `final method` **khóa khả năng override một phương thức**, `final class` **khóa khả năng có lớp con**, còn `final field/variable` **khóa phép gán lại**. Dùng đúng cấp độ sẽ giúp một hệ phân cấp kế thừa vừa giữ được hành vi quan trọng vừa mở rộng tại những điểm được thiết kế.