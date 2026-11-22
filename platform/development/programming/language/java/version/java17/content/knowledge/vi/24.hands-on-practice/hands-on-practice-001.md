# Mô hình giao dịch với sealed interface và các record trong Java 17

Khi xây dựng một hệ thống ledger hoặc xử lý thanh toán, ứng dụng thường có nhiều loại giao dịch: nạp tiền, rút tiền, chuyển tiền, hoàn tiền hoặc điều chỉnh số dư. Các loại giao dịch có dữ liệu riêng nhưng cùng tham gia vào một quy trình xử lý chung. Nếu mô hình chúng bằng một class lớn chứa nhiều field có thể null, code dễ xuất hiện những trạng thái không hợp lệ, chẳng hạn một giao dịch rút tiền lại có tài khoản nhận hoặc một giao dịch chuyển tiền thiếu tài khoản nguồn.

Java 17 cung cấp hai tính năng phù hợp để mô hình hóa miền dữ liệu này:

- **Record** biểu diễn một nhóm dữ liệu có cấu trúc, thường bất biến, với constructor, accessor, equals, hashCode và toString được tạo tự động.
- **Sealed interface/class** giới hạn những kiểu nào được phép triển khai hoặc kế thừa một kiểu cha.

Kết hợp hai tính năng, ta có thể định nghĩa một tập giao dịch đóng, mỗi loại giao dịch là một record riêng. Trình biên dịch biết những kiểu trực tiếp nào được phép thuộc về abstraction đó, còn record giúp dữ liệu giao dịch có cấu trúc và dễ kiểm tra bất biến.

Bài học này xây dựng một mô hình ledger đơn giản với giao dịch nạp, rút và chuyển tiền; giải thích cách thiết kế record, validate dữ liệu, xử lý từng loại giao dịch, bảo đảm tính idempotent ở mức mô hình và nhận biết giới hạn khi đưa ví dụ vào hệ thống thực tế.

## 1. Vì sao dùng sealed interface và record?

Giả sử ứng dụng có một kiểu chung là Transaction. Mọi giao dịch đều có mã định danh và thời điểm phát sinh, nhưng mỗi loại có dữ liệu khác nhau:

| Loại giao dịch | Dữ liệu đặc thù |
| --- | --- |
| Deposit | Tài khoản nhận tiền và số tiền |
| Withdrawal | Tài khoản bị trừ tiền và số tiền |
| Transfer | Tài khoản nguồn, tài khoản đích và số tiền |

Có thể dùng một class duy nhất với các field như sourceAccount, destinationAccount, amount và type. Tuy nhiên, cách đó cho phép nhiều tổ hợp field không hợp lệ:

- Deposit không cần sourceAccount.
- Withdrawal không cần destinationAccount.
- Transfer cần cả sourceAccount và destinationAccount.
- Một field type có thể không khớp với các field đang được gán.

Một mô hình tốt hơn là biểu diễn mỗi trường hợp bằng một kiểu riêng:

~~~text
                 Transaction
                (sealed interface)
                 /     |      \
                /      |       \
           Deposit Withdrawal Transfer
            record    record    record
~~~

**Sealed interface** đóng tập kiểu giao dịch được phép. **Records** biểu diễn dữ liệu của từng trường hợp bằng các thành phần tường minh.

## 2. Record trong Java 17

Record là một dạng class được thiết kế để mang dữ liệu. Ví dụ:

~~~java
public record CustomerId(String value) {
}
~~~

Khai báo trên tương đương một class có:

- field riêng tư và final cho thành phần value;
- constructor nhận value;
- accessor tên value();
- equals() và hashCode() dựa trên thành phần;
- toString() biểu diễn tên record và giá trị thành phần.

Sử dụng:

~~~java
CustomerId id = new CustomerId("C-100");
System.out.println(id.value());
System.out.println(id);
~~~

Accessor của record dùng đúng tên component, ví dụ value(), chứ không mặc định tạo getValue() như một số JavaBean.

Records là kiểu final ngầm định. Chúng không thể được extends bởi class khác, nhưng có thể implements interface. Một record cũng không thể khai báo thêm instance field tùy ý; dữ liệu instance phải được biểu diễn qua record components.

### 2.1. Record không đồng nghĩa với dữ liệu đã hợp lệ

Constructor mặc định của record chỉ gán các component. Nếu miền nghiệp vụ yêu cầu giá trị không null, không rỗng hoặc phải nằm trong một khoảng, hãy kiểm tra trong constructor.

Ví dụ:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID must not be blank");
        }
        value = value.trim();
    }
}
~~~

Đây là **compact canonical constructor**. Nó có thể kiểm tra hoặc chuẩn hóa các tham số. Sau khi constructor kết thúc bình thường, Java tự gán các tham số đã được chuẩn hóa vào component tương ứng.

### 2.2. Record có tính bất biến nông

Các component của record được lưu trong field final. Tuy nhiên, nếu component trỏ tới object mutable, nội dung object đó vẫn có thể thay đổi:

~~~java
public record Report(List<String> warnings) {
}
~~~

Dù field warnings là final, caller vẫn có thể sửa list được truyền vào nếu nó mutable. Khi cần snapshot bất biến, hãy tạo defensive copy:

~~~java
public record Report(List<String> warnings) {
    public Report {
        warnings = List.copyOf(warnings);
    }
}
~~~

Trong mô hình giao dịch, nên ưu tiên component có tính bất biến như String, UUID, Instant, BigDecimal, Currency và record khác đã được thiết kế bất biến. Với collection, luôn cân nhắc defensive copy.

## 3. Sealed interface trong Java 17

Sealed interface giới hạn các kiểu trực tiếp được phép triển khai nó:

~~~java
public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer {
}
~~~

Danh sách permits xác định các subtype được chấp nhận. Các kiểu được liệt kê phải trực tiếp implement interface này.

Mỗi subtype trực tiếp của sealed class/interface phải khai báo một trong ba trạng thái:

- **final:** không cho phép kế thừa tiếp;
- **sealed:** tiếp tục giới hạn các subtype của chính nó;
- **non-sealed:** mở lại khả năng kế thừa cho nhánh đó.

Record là final ngầm định, nên record có thể trực tiếp implement sealed interface mà không cần ghi thêm từ khóa final.

### 3.1. Quy tắc package và module

Các permitted direct subtype phải tuân theo quy tắc vị trí:

- Nếu kiểu cha nằm trong named module, các subtype được phép phải nằm trong cùng module.
- Nếu kiểu cha nằm trong unnamed module, các subtype được phép phải nằm trong cùng package.

Ví dụ trong bài này, các kiểu Transaction, Deposit, Withdrawal và Transfer được đặt trong cùng package của một module ứng dụng. Điều đó giúp danh sách permits rõ ràng và hợp lệ.

### 3.2. Khi nào dùng non-sealed?

Nếu một nhánh cần mở rộng bởi code khác, có thể đánh dấu subtype là non-sealed:

~~~java
public sealed interface Transaction
        permits StandardTransaction, ExtensionTransaction {
}

public sealed interface StandardTransaction
        extends Transaction
        permits Deposit, Withdrawal {
}

public non-sealed interface ExtensionTransaction
        extends Transaction {
}
~~~

Nhánh ExtensionTransaction cho phép các kiểu khác triển khai tiếp. Tuy nhiên, khi mở nhánh như vậy, người xử lý Transaction phải cân nhắc các subtype mới có thể xuất hiện.

Nếu miền nghiệp vụ có một tập loại giao dịch được kiểm soát, nên giữ hierarchy đóng bằng record final và các subtype sealed phù hợp. Dùng non-sealed khi khả năng mở rộng thực sự là một phần của hợp đồng API.

## 4. Thiết kế miền tiền tệ bằng record

Không nên dùng double để biểu diễn tiền trong giao dịch tài chính vì số thực nhị phân có thể không biểu diễn chính xác một số thập phân như 0.1. Dùng BigDecimal và một mã tiền tệ rõ ràng.

Trong ví dụ này, record Money dùng BigDecimal cùng java.util.Currency:

~~~java
package com.acme.ledger;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException(
                    "Currency has no standard fraction digits");
        }

        amount = amount.setScale(
                fractionDigits, RoundingMode.UNNECESSARY);
    }

    public static Money of(String amount, String currencyCode) {
        String code = Objects.requireNonNull(currencyCode)
                .trim()
                .toUpperCase(Locale.ROOT);
        return new Money(
                new BigDecimal(amount),
                Currency.getInstance(code));
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public boolean isPositive() {
        return amount.signum() > 0;
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot combine different currencies");
        }
    }

    @Override
    public String toString() {
        return amount.toPlainString() + " " + currency.getCurrencyCode();
    }
}
~~~

Một số quyết định trong record:

- amount và currency không được null.
- Currency xác định số chữ số thập phân tiêu chuẩn.
- setScale với RoundingMode.UNNECESSARY cho phép chuẩn hóa số 1.2 thành 1.20 nhưng từ chối làm tròn mất phần lẻ.
- add và subtract yêu cầu cùng currency.
- Money cho phép số âm để biểu diễn kết quả trung gian; các record giao dịch sẽ bắt buộc amount dương và Ledger sẽ bảo đảm số dư không âm.

Ví dụ:

~~~java
Money a = Money.of("10.5", "USD");
Money b = Money.of("2.25", "USD");
System.out.println(a.add(b)); // 12.75 USD
~~~

Currency và số chữ số thập phân trong ví dụ phù hợp với các tiền tệ ISO được JDK hỗ trợ. Nếu hệ thống cần tài sản số, token, đơn vị nội bộ hoặc quy tắc tiền tệ đặc thù, hãy xây dựng currency catalog và quy tắc scale riêng; java.util.Currency không phải mô hình cho mọi loại tài sản.

## 5. Định nghĩa Transaction và các record giao dịch

Tạo sealed interface:

**Transaction.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.UUID;

public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer {

    UUID id();

    Instant occurredAt();
}
~~~

Interface khai báo các thuộc tính chung:

- id: định danh duy nhất của giao dịch;
- occurredAt: thời điểm nghiệp vụ ghi nhận giao dịch.

Các loại giao dịch riêng sẽ cung cấp component tương ứng.

### 5.1. Deposit

**Deposit.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Deposit(
        UUID id,
        String accountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Deposit {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Account ID must not be blank");
        }
        accountId = accountId.trim();

        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Deposit amount must be positive");
        }
    }
}
~~~

Deposit chỉ chứa tài khoản nhận tiền và số tiền. Không có field tài khoản nguồn.

### 5.2. Withdrawal

**Withdrawal.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Withdrawal(
        UUID id,
        String accountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Withdrawal {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Account ID must not be blank");
        }
        accountId = accountId.trim();

        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Withdrawal amount must be positive");
        }
    }
}
~~~

Withdrawal chứa tài khoản bị trừ tiền và amount dương. Quy tắc tài khoản có đủ số dư sẽ được kiểm tra ở bước áp dụng giao dịch vào ledger.

### 5.3. Transfer

**Transfer.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Transfer(
        UUID id,
        String fromAccountId,
        String toAccountId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Transfer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (fromAccountId == null || fromAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Source account ID must not be blank");
        }
        if (toAccountId == null || toAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Destination account ID must not be blank");
        }

        fromAccountId = fromAccountId.trim();
        toAccountId = toAccountId.trim();

        if (fromAccountId.equals(toAccountId)) {
            throw new IllegalArgumentException(
                    "Source and destination must be different");
        }
        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }
    }
}
~~~

Transfer kiểm tra hai tài khoản khác nhau và amount dương. Việc kiểm tra hai tài khoản có tồn tại và cùng loại tiền được thực hiện khi áp dụng giao dịch.

### 5.4. Vì sao record phù hợp với transaction?

Một transaction đã được tạo không nên bị thay đổi tùy tiện. Record giúp:

- component là final;
- accessor có tên ngắn, rõ;
- equals/hashCode dựa trên dữ liệu;
- toString thuận tiện khi debug (nhưng không nên ghi dữ liệu nhạy cảm vào log);
- constructor tập trung validate dữ liệu đầu vào.

Record không tự bảo đảm toàn bộ object graph bất biến. Trong ví dụ, component là UUID, String, Instant và Money đã được thiết kế bất biến; vì vậy transaction có snapshot dữ liệu ổn định.

## 6. Xử lý các loại giao dịch bằng instanceof pattern matching

Khi đã có Transaction, một hàm xử lý có thể nhận kiểu cha rồi phân nhánh theo subtype:

~~~java
static void describe(Transaction transaction) {
    if (transaction instanceof Deposit deposit) {
        System.out.println(
                "Nạp " + deposit.amount()
                        + " vào " + deposit.accountId());
    } else if (transaction instanceof Withdrawal withdrawal) {
        System.out.println(
                "Rút " + withdrawal.amount()
                        + " từ " + withdrawal.accountId());
    } else if (transaction instanceof Transfer transfer) {
        System.out.println(
                "Chuyển " + transfer.amount()
                        + " từ " + transfer.fromAccountId()
                        + " tới " + transfer.toAccountId());
    } else {
        throw new IllegalStateException(
                "Unsupported transaction type: "
                        + transaction.getClass().getName());
    }
}
~~~

Pattern matching for instanceof đã là tính năng ổn định trong Java 16, nên dùng được bình thường trong Java 17 mà không cần bật preview.

Sealed interface giúp giới hạn subtype hợp lệ, nhưng chuỗi if/else trên không được compiler bảo đảm exhaustive như một switch pattern đã hoàn thiện. Nhánh cuối vẫn hữu ích để phát hiện trường hợp mô hình thay đổi hoặc code xử lý chưa được cập nhật.

**Lưu ý phiên bản:** pattern matching for switch trong Java 17 vẫn là preview feature. Ví dụ này dùng instanceof pattern matching ổn định, không cần --enable-preview. Khi phát triển trên Java 17, không nên coi pattern switch là cú pháp đã finalized.

## 7. Mô hình số dư bằng Ledger record

Ta cần một trạng thái ledger chứa số dư từng tài khoản và danh sách ID giao dịch đã áp dụng. Dùng record để biểu diễn snapshot bất biến:

**Ledger.java**

~~~java
package com.acme.ledger;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public record Ledger(
        Map<String, Money> balances,
        Set<UUID> appliedTransactionIds
) {
    public Ledger {
        balances = Map.copyOf(balances);
        appliedTransactionIds = Set.copyOf(appliedTransactionIds);

        balances.forEach((accountId, balance) -> {
            if (accountId.isBlank()) {
                throw new IllegalArgumentException(
                        "Account ID must not be blank");
            }
            if (balance.isNegative()) {
                throw new IllegalArgumentException(
                        "Account balance must not be negative");
            }
        });
    }

    public Ledger apply(Transaction transaction) {
        Objects.requireNonNull(transaction, "transaction");

        if (appliedTransactionIds.contains(transaction.id())) {
            return this;
        }

        Map<String, Money> nextBalances =
                new HashMap<>(balances);

        if (transaction instanceof Deposit deposit) {
            Money current = requireBalance(
                    nextBalances, deposit.accountId());
            nextBalances.put(
                    deposit.accountId(),
                    current.add(deposit.amount()));

        } else if (transaction instanceof Withdrawal withdrawal) {
            Money current = requireBalance(
                    nextBalances, withdrawal.accountId());
            Money updated = current.subtract(withdrawal.amount());

            if (updated.isNegative()) {
                throw new IllegalArgumentException(
                        "Insufficient funds");
            }

            nextBalances.put(withdrawal.accountId(), updated);

        } else if (transaction instanceof Transfer transfer) {
            Money source = requireBalance(
                    nextBalances, transfer.fromAccountId());
            Money destination = requireBalance(
                    nextBalances, transfer.toAccountId());

            Money updatedSource =
                    source.subtract(transfer.amount());
            Money updatedDestination =
                    destination.add(transfer.amount());

            if (updatedSource.isNegative()) {
                throw new IllegalArgumentException(
                        "Insufficient funds");
            }

            nextBalances.put(
                    transfer.fromAccountId(), updatedSource);
            nextBalances.put(
                    transfer.toAccountId(), updatedDestination);

        } else {
            throw new IllegalStateException(
                    "Unsupported transaction type: "
                            + transaction.getClass().getName());
        }

        Set<UUID> nextIds =
                new HashSet<>(appliedTransactionIds);
        nextIds.add(transaction.id());

        return new Ledger(nextBalances, nextIds);
    }

    private static Money requireBalance(
            Map<String, Money> balances,
            String accountId) {
        Money balance = balances.get(accountId);
        if (balance == null) {
            throw new IllegalArgumentException(
                    "Unknown account: " + accountId);
        }
        return balance;
    }
}
~~~

### 7.1. Snapshot bất biến và defensive copy

Constructor của Ledger gọi:

- Map.copyOf(balances);
- Set.copyOf(appliedTransactionIds).

Điều này ngăn caller sửa map hoặc set sau khi tạo Ledger. Nếu chỉ khai báo component là final nhưng giữ nguyên HashMap/HashSet mutable do caller truyền vào, record vẫn có thể bị thay đổi gián tiếp.

### 7.2. Mỗi lần apply trả về Ledger mới

Phương thức apply:

1. Kiểm tra transaction đã được áp dụng chưa.
2. Sao chép số dư hiện tại sang map mới.
3. Tính toán các số dư mới.
4. Kiểm tra quy tắc nghiệp vụ như tài khoản tồn tại và đủ số dư.
5. Thêm transaction ID vào tập ID đã xử lý.
6. Trả về một Ledger mới.

Nếu phép tính thất bại, Ledger ban đầu vẫn không bị thay đổi. Với Transfer, cả số dư nguồn và đích được tính trước khi cập nhật map mới, nên không có trạng thái trung gian bị trả ra ngoài.

### 7.3. Kiểm tra tiền tệ

Money.add() và Money.subtract() từ chối phép toán giữa hai currency khác nhau. Do đó:

- Deposit chỉ cộng được nếu số dư và amount cùng currency.
- Withdrawal chỉ trừ được nếu số dư và amount cùng currency.
- Transfer yêu cầu amount tương thích với cả số dư nguồn và đích.

Nếu hai tài khoản có currency khác nhau, Transfer trong mô hình này bị từ chối. Chuyển đổi ngoại tệ cần một mô hình riêng có tỷ giá, thời điểm áp dụng, nguồn tỷ giá, phí và quy tắc làm tròn.

## 8. Chạy thử mô hình ledger

Ví dụ chương trình:

**LedgerDemo.java**

~~~java
package com.acme.ledger;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class LedgerDemo {
    public static void main(String[] args) {
        Ledger ledger = new Ledger(
                Map.of(
                        "A-100", Money.of("100.00", "USD"),
                        "B-200", Money.of("25.00", "USD")
                ),
                Set.of()
        );

        Transfer transfer = new Transfer(
                UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"),
                "A-100",
                "B-200",
                Money.of("10.00", "USD"),
                Instant.parse("2026-01-15T10:00:00Z")
        );

        ledger = ledger.apply(transfer);

        System.out.println(ledger.balances());
        // A-100 = 90.00 USD
        // B-200 = 35.00 USD

        Ledger afterDuplicate = ledger.apply(transfer);
        System.out.println(afterDuplicate.balances());
        // Không trừ/cộng thêm lần thứ hai.
    }
}
~~~

Biên dịch các file trong package:

~~~bash
javac -d out src/com/acme/ledger/*.java
java -cp out com.acme.ledger.LedgerDemo
~~~

Ví dụ trên minh họa việc mô hình hóa và tính toán trạng thái trong bộ nhớ. Nó chưa phải hệ thống ngân hàng hoặc cơ chế ghi sổ bền vững.

## 9. Idempotency và định danh giao dịch

Trong hệ thống phân tán, một request có thể được gửi lại do timeout, retry hoặc client không nhận được phản hồi. Nếu cùng một giao dịch được áp dụng hai lần, số dư có thể bị cập nhật lặp.

Ledger trong ví dụ lưu appliedTransactionIds. Khi gặp ID đã tồn tại, apply trả về snapshot hiện tại:

~~~java
if (appliedTransactionIds.contains(transaction.id())) {
    return this;
}
~~~

Đây là minh họa của idempotency theo transaction ID. Để áp dụng trong hệ thống thực tế:

- ID phải do nguồn tin cậy tạo hoặc được xác thực theo hợp đồng request.
- ID cần có phạm vi duy nhất rõ ràng, chẳng hạn theo tenant hoặc tài khoản nếu phù hợp.
- Việc kiểm tra ID trùng và ghi bút toán phải diễn ra nguyên tử trong cùng transaction lưu trữ.
- Cần xác định cách xử lý khi cùng ID được gửi lại với payload khác.
- Bảng idempotency cần retention phù hợp và chỉ mục duy nhất ở database.

Một Set trong bộ nhớ không đủ cho nhiều instance, restart hoặc xử lý đồng thời. Nó chỉ minh họa ý tưởng ở cấp mô hình.

## 10. Phân biệt command, transaction và event

Trong thiết kế miền nghiệp vụ, từ “transaction” có thể được dùng cho nhiều khái niệm. Nên đặt tên rõ:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Command | Yêu cầu hệ thống thực hiện một hành động. | TransferFunds(from, to, amount) |
| Transaction/domain operation | Quy trình nghiệp vụ kiểm tra và thực hiện hành động. | Kiểm tra số dư, hạn mức, trạng thái tài khoản. |
| Event/ledger entry | Sự kiện hoặc bút toán đã được chấp nhận và ghi nhận. | FundsTransferred, DepositPosted |
| Database transaction | Ranh giới commit/rollback của storage. | BEGIN, UPDATE balances, INSERT ledger, COMMIT. |

Các record Deposit, Withdrawal và Transfer trong ví dụ đóng vai trò dữ liệu giao dịch đã được tạo để áp dụng vào ledger. Trong một hệ thống production, có thể tách command chưa được chấp nhận khỏi event/bút toán đã được commit.

Ví dụ:

~~~java
public sealed interface TransferCommand
        permits CreateTransfer {
}

public record CreateTransfer(
        String fromAccountId,
        String toAccountId,
        Money amount,
        UUID requestId
) implements TransferCommand {
}
~~~

Sau khi xử lý command thành công, ứng dụng mới tạo một event hoặc ledger entry có ID và thời điểm ghi nhận. Cách tách này giúp phân biệt “người dùng yêu cầu chuyển tiền” với “chuyển tiền đã được hệ thống chấp nhận và ghi sổ”.

## 11. Mở rộng mô hình với giao dịch hoàn tiền

Nếu miền nghiệp vụ cần Reversal, có thể thêm record mới vào permits:

~~~java
public sealed interface Transaction
        permits Deposit, Withdrawal, Transfer, Reversal {
    UUID id();
    Instant occurredAt();
}
~~~

Record Reversal có thể tham chiếu giao dịch gốc:

~~~java
public record Reversal(
        UUID id,
        UUID originalTransactionId,
        Money amount,
        Instant occurredAt
) implements Transaction {

    public Reversal {
        if (id == null || originalTransactionId == null
                || amount == null || occurredAt == null) {
            throw new IllegalArgumentException(
                    "Reversal fields must not be null");
        }
        if (id.equals(originalTransactionId)) {
            throw new IllegalArgumentException(
                    "A transaction cannot reverse itself");
        }
        if (!amount.isPositive()) {
            throw new IllegalArgumentException(
                    "Reversal amount must be positive");
        }
    }
}
~~~

Sau khi thêm subtype, mọi logic xử lý Transaction cần được cập nhật để định nghĩa quy tắc reversal. Ví dụ trên mới xác thực dữ liệu cơ bản; nó chưa chứng minh giao dịch gốc tồn tại, chưa bị reversal trước đó, còn trong thời hạn hoàn tiền hay có cùng currency.

Sealed hierarchy làm cho việc mở rộng kiểu trở thành thay đổi có chủ đích: phải cập nhật permits và xử lý nghiệp vụ tương ứng.

## 12. Khi nào dùng sealed interface thay cho enum?

Enum phù hợp khi mỗi trường hợp chỉ cần một giá trị trong tập hằng số:

~~~java
public enum TransactionType {
    DEPOSIT,
    WITHDRAWAL,
    TRANSFER
}
~~~

Enum đơn giản để lưu loại giao dịch, nhưng không tự ràng buộc dữ liệu đặc thù của từng loại. Ta vẫn cần một class chung với nhiều field hoặc nhiều cấu trúc dữ liệu khác.

Sealed interface kết hợp record phù hợp khi từng trường hợp có cấu trúc dữ liệu riêng:

~~~java
Transaction transaction =
        new Transfer(
                UUID.randomUUID(),
                "A-100",
                "B-200",
                Money.of("10.00", "USD"),
                Instant.now());
~~~

Có thể dùng cả hai nếu cần enum để biểu diễn mã loại trong một giao thức bên ngoài, nhưng tránh duy trì hai nguồn sự thật không đồng bộ giữa enum type và subtype thực tế.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Danh sách trạng thái/loại đơn giản, không có payload khác nhau | enum |
| Mỗi trường hợp có dữ liệu riêng | sealed interface + records |
| API cho phép bên thứ ba thêm implementation | interface thông thường hoặc nhánh non-sealed có chủ đích |
| Dữ liệu truyền qua JSON/message broker | sealed model cộng serializer/schema được cấu hình rõ ràng |

## 13. Pattern matching và xử lý exhaustive trong Java 17

Sealed interface cho compiler biết tập subtype trực tiếp. Tuy nhiên, trong Java 17, pattern matching for switch vẫn là preview feature. Nếu muốn code không phụ thuộc preview, dùng instanceof pattern matching:

~~~java
if (transaction instanceof Deposit deposit) {
    processDeposit(deposit);
} else if (transaction instanceof Withdrawal withdrawal) {
    processWithdrawal(withdrawal);
} else if (transaction instanceof Transfer transfer) {
    processTransfer(transfer);
} else {
    throw new IllegalStateException("Unknown transaction");
}
~~~

Không cần thêm --enable-preview cho cú pháp này trong Java 17.

Nếu dự án chủ động chấp nhận preview feature của Java 17, pattern switch có thể được thử nghiệm với cờ preview tương ứng của compiler và runtime. Nhưng preview syntax có thể thay đổi giữa các phiên bản; không nên đưa vào API ổn định nếu yêu cầu chỉ nhắm Java 17 không-preview.

## 14. Kiểm tra bất biến ở đúng lớp

Một mô hình tốt chia validation theo trách nhiệm:

| Lớp | Ví dụ bất biến |
| --- | --- |
| Money | amount/currency không null, scale hợp lệ, phép cộng trừ cùng currency |
| Deposit/Withdrawal | ID và thời điểm hợp lệ, account ID không rỗng, amount dương |
| Transfer | account nguồn/đích khác nhau, cả hai ID hợp lệ, amount dương |
| Ledger | snapshot không có số dư âm, map/set được defensive copy |
| Use case/domain service | account tồn tại, đủ số dư, hạn mức và trạng thái tài khoản |
| Persistence/database | ghi bút toán và cập nhật số dư nguyên tử, ID duy nhất, transaction isolation |

Không nên nhồi tất cả validation vào constructor của record. Record có thể kiểm tra bất biến nội tại của dữ liệu mà nó đại diện; các quy tắc cần truy cập repository, đồng hồ hệ thống hoặc nhiều aggregate thường thuộc application/domain service.

Ví dụ account tồn tại là quy tắc cần nhìn vào ledger hoặc repository, nên không thể xác minh chỉ từ constructor Transfer.

## 15. Những giới hạn quan trọng của mô hình mẫu

Ledger trong bài là một mô hình học tập trong bộ nhớ. Trước khi dùng cho tiền thật hoặc hệ thống nhiều người dùng, cần bổ sung những cơ chế khác:

### 15.1. Atomicity và concurrency

Hai thread có thể cùng đọc một snapshot Ledger rồi tạo hai snapshot mới. Nếu ứng dụng ghi đè tham chiếu mà không có cơ chế đồng bộ, một cập nhật có thể bị mất.

Record bất biến giúp snapshot dễ chia sẻ, nhưng không tự cung cấp transaction isolation. Ở production, dùng database transaction, optimistic locking/version, row locking hoặc cơ chế đồng bộ phù hợp.

### 15.2. Durability

Ledger trong bộ nhớ mất dữ liệu khi tiến trình dừng. Hệ thống thật cần lưu bút toán bền vững, backup, recovery và kiểm soát thứ tự ghi.

### 15.3. Double-entry accounting

Ví dụ cập nhật trực tiếp map số dư để dễ hiểu. Hệ thống kế toán thường dùng ledger entries có debit/credit và quy tắc cân bằng tổng ghi nợ/ghi có. Số dư có thể được tính từ bút toán hoặc duy trì như projection có thể đối soát.

### 15.4. Currency conversion và fee

Transfer mẫu chỉ hỗ trợ hai tài khoản cùng currency và không có phí. Chuyển đổi ngoại tệ cần tỷ giá, nguồn tỷ giá, thời điểm chốt, rounding policy và cách ghi nhận chênh lệch.

### 15.5. Authorization và audit

Sealed interface và record không xác minh người gọi có quyền chuyển tiền. Hệ thống cần authentication, authorization, hạn mức, fraud checks, audit trail và quy trình xử lý tranh chấp.

### 15.6. Serialization và schema evolution

Record và sealed hierarchy không tự tạo schema tương thích cho JSON hoặc message broker. Nếu serialize ra ngoài process, phải định nghĩa discriminator, version, mapping subtype và chính sách khi gặp subtype chưa biết.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thêm được subtype vào sealed interface | Subtype chưa nằm trong permits hoặc vi phạm quy tắc package/module. | Cập nhật permits và đặt subtype trong cùng module (hoặc package của unnamed module). |
| Compiler báo subtype không final/sealed/non-sealed | Direct subtype chưa khai báo trạng thái kế thừa bắt buộc. | Dùng final, sealed hoặc non-sealed; record vốn final ngầm định. |
| Record cho phép dữ liệu null/rỗng | Chỉ dùng constructor mặc định mà không validate. | Dùng compact canonical constructor và kiểm tra bất biến. |
| Record chứa collection vẫn bị thay đổi | Field final chỉ cố định tham chiếu, không làm collection bất biến. | Dùng List.copyOf, Set.copyOf hoặc Map.copyOf. |
| equals của Money không như mong đợi | BigDecimal có scale khác nhau hoặc currency khác nhau. | Chuẩn hóa scale trong constructor và giữ currency trong component. |
| Cộng tiền khác currency | Không kiểm tra currency trước phép toán. | Đặt kiểm tra trong Money.add/subtract. |
| Transfer cập nhật một phía rồi thất bại phía còn lại | Sửa trạng thái trực tiếp trước khi tính hết các điều kiện. | Tính cả hai số dư trên bản sao rồi mới tạo snapshot mới. |
| Một transaction bị áp dụng hai lần | Không có idempotency key hoặc kiểm tra ID không nguyên tử. | Dùng transaction ID duy nhất và unique constraint trong persistence. |
| Hai thread làm mất cập nhật | Immutable snapshot không tự giải quyết concurrent commit. | Dùng database transaction, optimistic locking hoặc synchronization. |
| Thêm record mới nhưng code xử lý quên nhánh | if/else không tự được compiler kiểm tra exhaustive. | Cập nhật mọi consumer và có nhánh fallback rõ ràng; dùng test cho từng subtype. |
| Pattern switch không biên dịch trên Java 17 mặc định | Pattern matching for switch ở Java 17 là preview. | Dùng instanceof pattern matching ổn định hoặc bật preview có chủ đích cho thử nghiệm. |
| Ghi log record làm lộ dữ liệu | toString tự sinh hiển thị component. | Không đưa secret/PII vào component; log dữ liệu đã được chọn lọc. |

## 17. Bài tập tự luyện

### Bài 1 — Thêm loại giao dịch Fee

Tạo record Fee gồm id, accountId, amount và occurredAt. Thêm Fee vào permits của Transaction. Định nghĩa quy tắc amount dương và cách Ledger áp dụng khoản phí.

### Bài 2 — Tạo record Money

Viết record Money dùng BigDecimal và Currency. Constructor phải chuẩn hóa scale theo currency mà không làm tròn mất dữ liệu. Viết add/subtract từ chối currency không khớp.

### Bài 3 — Bảo vệ Transfer

Thêm kiểm tra source và destination khác nhau. Khi apply, tính số dư mới của cả hai tài khoản trước khi tạo Ledger mới. Giải thích vì sao điều này giúp tránh trả về trạng thái chỉ cập nhật một phía.

### Bài 4 — Idempotency

Tạo hai transaction có cùng ID và áp dụng lần lượt. Xác định kết quả mong đợi. Sau đó giải thích vì sao Set trong bộ nhớ chưa đủ để bảo đảm idempotency khi có nhiều instance hoặc database.

### Bài 5 — Command và event

Tách yêu cầu TransferFunds khỏi event FundsTransferred. Xác định trường nào thuộc request, trường nào chỉ có sau khi giao dịch được chấp nhận.

### Bài 6 — Thêm subtype mới

Thêm Reversal vào sealed hierarchy. Liệt kê các nơi cần cập nhật: permits, constructor validation, logic Ledger, serialization mapping và kiểm thử.

### Bài 7 — Xử lý pattern

Viết hàm mô tả Transaction bằng instanceof pattern matching. Giải thích vì sao đoạn code chạy ổn định trên Java 17 mà không cần preview.

## 18. Ghi nhớ khi mô hình giao dịch với sealed interface và record

- Record biểu diễn dữ liệu theo component, tạo accessor, equals, hashCode và toString tự động.
- Dùng compact constructor để kiểm tra và chuẩn hóa component trước khi tạo record.
- Record có field final nhưng chỉ bất biến nông; dùng defensive copy cho collection hoặc component mutable.
- Sealed interface giới hạn các subtype trực tiếp bằng permits.
- Subtype trực tiếp phải final, sealed hoặc non-sealed; record vốn final ngầm định.
- Permitted subtype phải ở cùng named module với kiểu cha, hoặc cùng package nếu kiểu cha thuộc unnamed module.
- Mỗi loại giao dịch nên có record riêng để tránh các field null và tổ hợp dữ liệu không hợp lệ.
- Dùng BigDecimal cho số tiền, gắn currency và kiểm tra scale/rounding rõ ràng.
- Kiểm tra bất biến nội tại trong record; kiểm tra account existence, funds và authorization ở tầng nghiệp vụ phù hợp.
- Instanceof pattern matching là cú pháp ổn định trong Java 17; pattern matching for switch ở Java 17 vẫn là preview.
- Immutable snapshot giúp trạng thái dễ suy luận, nhưng không tự bảo đảm atomicity, concurrency control hoặc durability.
- Idempotency cần transaction ID ổn định và bảo đảm nguyên tử trong persistence khi chạy production.
- Mô hình mẫu không thay thế double-entry ledger, database transaction, authorization, audit hoặc quy tắc thanh toán thực tế.

### Tài liệu tham khảo

- [Java SE 17 Language Specification — Records](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — cú pháp và ngữ nghĩa record.
- [Java SE 17 Language Specification — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6) — khai báo sealed class và permitted subclasses.
- [Java SE 17 Language Specification — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4) — quy tắc sealed interface.
- [Java SE 17 Language Specification — Pattern Matching for instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — pattern variable trong instanceof.
- [JEP 395: Records](https://openjdk.org/jeps/395) — records trở thành tính năng chính thức.
- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — sealed classes/interfaces trở thành tính năng chính thức trong Java 17.
- [JEP 406: Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406) — trạng thái preview của pattern switch trong Java 17.
