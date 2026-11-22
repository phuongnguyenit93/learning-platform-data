# Quan hệ giữa ngoại lệ, hợp đồng phương thức và trạng thái chương trình — Java Core Exception

> **Bối cảnh:** Java Core → Exception → Tổng quan. Exception không chỉ là thông báo “có lỗi”. Nó còn là một **cách phương thức kết thúc bất thường**, tác động trực tiếp đến những gì phương thức cam kết với người gọi và trạng thái dữ liệu đã thay đổi trước khi lỗi xuất hiện. Hiểu ba yếu tố này cùng nhau giúp thiết kế API dễ dùng, tránh làm hỏng dữ liệu và viết mã xử lý lỗi có thể kiểm chứng.

## 1. Ba câu hỏi cần trả lời cùng lúc

Khi gọi một phương thức có thể thất bại, hãy xác định:

1. **Hợp đồng phương thức (method contract):** Người gọi phải cung cấp điều kiện gì? Nếu thành công sẽ nhận giá trị/kết quả gì? Những kiểu thất bại nào được báo ra?
2. **Ngoại lệ (exception):** Nếu không hoàn thành bình thường, phương thức ném gì, ở đâu, có truyền ra ngoài không và caller có thể xử lý tại tầng nào?
3. **Trạng thái chương trình (program state):** Tại thời điểm ngoại lệ thoát khỏi phương thức, đối tượng, collection, file, tài nguyên hoặc hệ thống bên ngoài đã đổi đến mức nào?

Ví dụ một phương thức `transfer(from, to, amount)` có thể cam kết:

- Tiền đề: tài khoản hợp lệ, khác nhau, `amount > 0`, đủ số dư, kết quả cộng không tràn.
- Sau khi trả về bình thường: số dư nguồn giảm đúng `amount`, đích tăng đúng `amount`; tổng hai số dư được giữ nguyên.
- Nếu ném một ngoại lệ do dữ liệu không hợp lệ, thiếu số dư hoặc tràn số: cả hai số dư **giữ nguyên**.
- Bất biến: số dư không âm và không vượt phạm vi biểu diễn của kiểu dữ liệu.

Cam kết “khi thất bại, không đổi số dư” là một phần quan trọng của API dù chữ ký Java không thể hiện nó. Chỉ thêm `throws SomeException` **không tự tạo ra** cam kết này.

### 1.1. Bình thường và bất thường là hai đường kết thúc

Một lời gọi phương thức Java có thể:

- **Hoàn tất bình thường:** chạy đến cuối hoặc `return`. Caller nhận giá trị trả về nếu phương thức có kiểu trả về khác `void`.
- **Hoàn tất bất thường do exception:** một `throw` hoặc lời gọi con phát sinh exception chưa được xử lý. Phương thức hiện tại không trả về kết quả thông thường; runtime tìm handler thích hợp. Những câu lệnh bình thường phía sau điểm phát sinh bị bỏ qua.

Một phương thức có thể đã thực hiện một số thay đổi trạng thái **trước khi** exception phát sinh. Vì vậy không thể suy luận “đã throw thì mọi thao tác trước đó bị hoàn tác”. Java không tự động rollback các phép gán, thay đổi collection, ghi file hay gửi yêu cầu mạng.

```text
Caller gọi method()
       │
       ▼
 Kiểm tra điều kiện đầu vào
       │
       ▼
 Thực hiện công việc ──────────────┐
       │                           │
       ▼                           ▼
 return / kết thúc          exception phát sinh
       │                           │
       ▼                           ▼
 caller dùng kết quả       tìm catch phù hợp, stack unwinding
                                   │
                                   ▼
                          trạng thái có thể đã đổi
```

Trên đường exception, `finally` và các thao tác đóng tài nguyên tương ứng có thể được thực thi khi stack tháo dần. Điều này giúp dọn dẹp, nhưng không có nghĩa rằng các thay đổi nghiệp vụ trước đó được hoàn tác.

## 2. Hợp đồng phương thức là gì?

**Method contract** mô tả nghĩa vụ của người gọi và lời bảo đảm của phương thức. Nó thường được biểu đạt qua tên, tham số, kiểu trả về, Javadoc, validation, exception và test. Có bốn phần nên xem xét:

| Thành phần | Câu hỏi | Ví dụ với `withdraw(amount)` |
| --- | --- | --- |
| **Precondition (tiền điều kiện)** | Caller phải bảo đảm hoặc chấp nhận phương thức kiểm tra điều gì? | `amount > 0`; đối tượng tài khoản đang tồn tại. |
| **Postcondition (hậu điều kiện khi thành công)** | Sau khi method trả về bình thường, điều gì chắc chắn đúng? | Số dư giảm đúng số tiền rút và không âm. |
| **Invariant (bất biến)** | Những thuộc tính nào của đối tượng phải giữ đúng ở các thời điểm quan sát hợp lệ? | Số dư không âm; dữ liệu nội bộ thỏa quy tắc của lớp. |
| **Exceptional guarantee (cam kết khi thất bại)** | Khi method ném exception, trạng thái còn sử dụng an toàn không, có giữ nguyên không? | Số dư giữ nguyên với các lỗi đã nêu trong hợp đồng. |

Java compiler kiểm tra kiểu dữ liệu, khả năng truy cập, cú pháp và một số quy tắc checked exception. Compiler **không chứng minh** được toàn bộ precondition, postcondition, invariant hoặc mức độ hoàn tác trạng thái. Người phát triển phải tự thực hiện, ghi tài liệu và kiểm thử.

### 2.1. Phân biệt tiền điều kiện với kiểm tra bên trong

Một API có thể yêu cầu caller không truyền giá trị âm; khi caller vi phạm, phương thức có thể chủ động ném `IllegalArgumentException` để báo sai hợp đồng. Một API khác có thể coi “không đủ số dư” là tình huống nghiệp vụ bình thường cần đưa về kết quả `false` hoặc một loại exception riêng. **Cả hai cách đều có thể hợp lý** nếu hợp đồng nhất quán và người gọi biết phải xử lý.

Tiền điều kiện không nhất thiết là thứ compiler kiểm tra. `int amount` chỉ bảo đảm đây là số nguyên Java, không bảo đảm `amount > 0`. Kiểu `String path` cũng không bảo đảm đường dẫn tồn tại.

### 2.2. Hậu điều kiện chỉ áp dụng khi thành công, trừ khi hợp đồng nói rõ

Giả sử `saveOrder(order)` hứa trả về mã đơn hàng sau khi lưu thành công. Nếu nó ném `IOException`, caller không được tự kết luận đơn hàng chắc chắn chưa được ghi. Ngoại lệ có thể phát sinh **sau** khi một phần hoặc toàn bộ dữ liệu đã được gửi/ghi nhưng trước khi caller nhận xác nhận.

Vì thế, cần viết riêng cam kết trên đường thất bại: “không thay đổi gì”, “có thể đã lưu một phần”, “trạng thái còn hợp lệ nhưng kết quả chưa xác định”, hoặc “phải tải lại từ nguồn dữ liệu”. Không nên dùng cụm “thất bại thì rollback” nếu thực tế không có cơ chế rollback.

### 2.3. Bất biến của đối tượng và trạng thái hợp lệ

Bất biến là thuộc tính luôn phải đúng tại các điểm mà API cho phép quan sát. Ví dụ lớp quản lý số dư không cho số âm, collection chỉ chứa số lượng dương, hoặc một cặp trường `start <= end`. Nếu method cập nhật trường thứ nhất rồi ném trước khi cập nhật trường thứ hai, invariant có thể bị phá vỡ.

Trong mã tuần tự không bị quan sát giữa các bước, trạng thái trung gian có thể tạm thời thay đổi; yêu cầu quan trọng là trạng thái tại **ranh giới công khai** vẫn nhất quán theo hợp đồng. Trong chương trình nhiều luồng, các thay đổi trung gian có thể bị luồng khác nhìn thấy nếu thiếu đồng bộ hóa; cơ chế exception tự nó không tạo tính nguyên tử hay an toàn luồng.

## 3. Exception là tín hiệu thất bại của hợp đồng

Hãy phân biệt ba khái niệm thường lẫn nhau:

- **`throw`**: câu lệnh tạo đường kết thúc bất thường bằng cách ném một đối tượng `Throwable`.
- **`throws`**: một phần khai báo phương thức về các checked exception có thể thoát ra. Có thể khai báo cả unchecked exception để tài liệu hóa, nhưng compiler không bắt buộc.
- **`catch`**: một nơi xử lý exception theo kiểu tương thích; có thể phục hồi, chuyển đổi, bổ sung ngữ cảnh hoặc truyền tiếp.

Ví dụ ý tưởng:

```java
int parsePositive(String text) {
    int result = Integer.parseInt(text); // Có thể ném NumberFormatException.
    if (result <= 0) {
        throw new IllegalArgumentException("Giá trị phải dương");
    }
    return result;
}
```

Đây là **đoạn minh họa phương thức**, không phải chương trình độc lập. Người gọi có hai kiểu thất bại đáng quan tâm: `NumberFormatException` khi chuỗi không phải số nguyên hợp lệ và `IllegalArgumentException` khi parse được nhưng giá trị không dương. Cả hai là unchecked; không cần khai báo `throws`. `NumberFormatException` kế thừa từ `IllegalArgumentException`, nên nếu caller dùng hai khối `catch`, phải đặt khối bắt `NumberFormatException` trước.

### 3.1. Checked và unchecked có liên quan gì tới hợp đồng?

| Phân loại | Cơ chế compiler | Ví dụ | Ý nghĩa đối với thiết kế API |
| --- | --- | --- | --- |
| **Checked exception** | Phải bắt hoặc khai báo khi có thể thoát khỏi phương thức, trừ trường hợp quy tắc ngôn ngữ cho phép khác | `IOException` | Khi ký hợp đồng API, caller bị buộc xét đường lỗi ở mức cú pháp. |
| **Unchecked exception** | Không bắt buộc bắt hoặc khai báo | `IllegalArgumentException`, `IllegalStateException` | Dùng được cho vi phạm hợp đồng, trạng thái không phù hợp hoặc nhiều tình huống khác; vẫn cần tài liệu và test. |
| **`Error`** và lớp con | Không bắt buộc bắt hoặc khai báo | `OutOfMemoryError` | Thường đại diện sự cố nghiêm trọng; ứng dụng thông thường không hứa khôi phục khỏi mọi `Error`. |

Quy tắc kỹ thuật chính xác: checked exceptions là các lớp con của `Throwable` **không** thuộc nhánh `RuntimeException` hoặc `Error`. Trong thực tế API Java thường dùng các lớp con của `Exception` ngoài nhánh `RuntimeException`.

**Không suy luận mức độ nghiêm trọng từ checked/unchecked.** Một lỗi I/O đọc thiếu file có thể là checked và có khả năng xử lý; một lỗi unchecked do dữ liệu không hợp lệ cũng có thể được xử lý tại tầng nhập liệu. Chọn loại exception dựa trên ý nghĩa hợp đồng và cách caller dự kiến sử dụng API.

### 3.2. Lời hứa của `throws` có giới hạn

Chữ ký:

```java
void loadConfig() throws java.io.IOException
```

báo cho caller rằng `IOException` có thể thoát khỏi phương thức. Nó **không** nói rằng:

- ngoại lệ chắc chắn sẽ xảy ra;
- method chỉ có thể ném đúng loại này;
- method chưa thay đổi dữ liệu trước khi ném;
- các thao tác I/O được tự động hoàn tác;
- caller bắt ngoại lệ là đủ để đảm bảo trạng thái hợp lệ;
- JVM sẽ xử lý mọi lỗi có thể xảy ra.

Unchecked exception và `Error` vẫn có thể xảy ra dù không xuất hiện ở `throws`. Hành vi trạng thái khi thất bại phải được chỉ rõ bằng tài liệu, thiết kế và kiểm thử riêng.

### 3.3. Kế thừa và ghi đè hợp đồng

Khi override, phương thức của lớp con **không được mở rộng danh sách checked exception** theo cách không tương thích với khai báo ở lớp cha/interface. Nó có thể khai báo tập checked exception hẹp hơn, không khai báo, hoặc ném unchecked exception. Quy tắc này giúp mã sử dụng một đối tượng qua kiểu cha vẫn biên dịch theo hợp đồng khai báo của kiểu cha.

Tuy nhiên, tính thay thế (substitutability) còn đòi hỏi hợp đồng **về hành vi**: lớp con không nên tùy tiện đặt tiền điều kiện khắt khe hơn hoặc làm suy yếu bảo đảm đã hứa trong interface. Compiler không phát hiện được mọi vi phạm về trạng thái và ý nghĩa nghiệp vụ.

Ví dụ: interface `Account.withdraw(positiveAmount)` hứa khi thất bại sẽ giữ nguyên số dư. Một implementation ném cùng kiểu exception nhưng trừ tiền trước khi ném vẫn vi phạm hợp đồng, dù mã có thể biên dịch bình thường.

## 4. Mức bảo đảm trạng thái khi ngoại lệ xảy ra

Không có một mức độ bảo đảm thống nhất cho mọi method Java. Cần đọc tài liệu hoặc xây dựng rõ cam kết của chính API.

| Mức bảo đảm | Trạng thái sau exception | Ví dụ thực tế |
| --- | --- | --- |
| **Không bảo đảm đủ để tiếp tục (no guarantee)** | Có thể đã làm hỏng bất biến; đối tượng không nên được sử dụng tiếp cho tới khi phục hồi hoặc thay thế. | Phương thức tự viết cập nhật nhiều trường nhưng bỏ dở ở giữa và không có khôi phục. |
| **Basic guarantee** | Đối tượng vẫn đáp ứng bất biến và không rò rỉ tài nguyên do API quản lý, nhưng giá trị có thể đã đổi một phần. | Xử lý được ba phần tử đầu trong danh sách rồi dừng ở phần tử lỗi; danh sách còn hợp lệ. |
| **Strong guarantee** | Với nhóm thất bại đã cam kết, thao tác có hiệu ứng quan sát như chưa từng thực hiện: trạng thái liên quan giữ nguyên. | Parse hết input vào bản sao; chỉ gán snapshot mới sau khi mọi bước kiểm tra thành công. |
| **No-throw guarantee** | Với phạm vi điều kiện đã hứa, method không để exception thoát ra. | Một phép đóng/dọn dẹp được thiết kế phù hợp, có hợp đồng không ném trong các điều kiện định trước. |

Các tên mức bảo đảm này thường gặp khi thảo luận về **exception safety**; Java không tự động áp đặt chúng. “No-throw” không thể được hiểu là lời hứa chống mọi thảm họa môi trường như JVM bị dừng, mất điện hoặc thiếu bộ nhớ cực đoan.

Có ba điều không tương đương:

1. **Object invariant được giữ:** dữ liệu vẫn hợp lệ, dù giá trị khác trước.
2. **Strong exception safety:** với loại thất bại được xét, hiệu ứng quan sát được như chưa thực hiện.
3. **Atomicity/transactionality:** thao tác được nhìn nhận như một đơn vị theo cơ chế đồng thời hoặc giao dịch; thường cần synchronization, database transaction hay giao thức chuyên biệt.

Một phương thức có strong exception safety trong trường hợp chạy tuần tự chưa chắc atomic đối với luồng khác. Và rollback dữ liệu trong RAM không tự rollback file hoặc yêu cầu mạng đã gửi.

## 5. Chương trình Java 17: kiểm tra trước, rồi mới thay đổi trạng thái

Ví dụ sau dùng hai tài khoản có số dư nguyên không âm. Phương thức chuyển tiền kiểm tra tất cả các trường hợp thất bại dự kiến **trước hai phép gán**, để bảo toàn cả hai số dư nếu có lỗi đầu vào, thiếu tiền hoặc tràn số.

Tạo tệp `TransferContractDemo.java`:

```java
import java.util.Objects;

public class TransferContractDemo {
    static final class Account {
        final String id;
        private int balance;

        Account(String id, int initialBalance) {
            this.id = Objects.requireNonNull(id, "id");
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.balance = initialBalance;
        }

        int balance() {
            return balance;
        }
    }

    static void transfer(Account from, Account to, int amount) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");

        if (from == to) {
            throw new IllegalArgumentException("Trùng tài khoản");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        if (from.balance < amount) {
            throw new IllegalStateException("Không đủ số dư");
        }

        // Kiểm tra tràn số trước khi sửa bất kỳ tài khoản nào.
        int newToBalance = Math.addExact(to.balance, amount);
        int newFromBalance = from.balance - amount;

        // Hai bước này không còn kiểm tra/parse có thể thất bại.
        from.balance = newFromBalance;
        to.balance = newToBalance;
    }

    public static void main(String[] args) {
        Account a = new Account("A", 100);
        Account b = new Account("B", 40);

        System.out.println("Ban đầu: A=" + a.balance() + ", B=" + b.balance());
        transfer(a, b, 30);
        System.out.println("Sau chuyển: A=" + a.balance() + ", B=" + b.balance());

        try {
            transfer(a, b, 90);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối: " + e.getMessage());
        }
        System.out.println("Sau thiếu tiền: A=" + a.balance()
                + ", B=" + b.balance());

        try {
            transfer(a, b, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Tham số sai: " + e.getMessage());
        }

        Account full = new Account("FULL", Integer.MAX_VALUE);
        try {
            transfer(a, full, 1);
        } catch (ArithmeticException e) {
            System.out.println("Không chuyển vì: "
                    + e.getClass().getSimpleName());
        }
        System.out.println("Cuối cùng: A=" + a.balance()
                + ", B=" + b.balance()
                + ", FULL=" + full.balance());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 TransferContractDemo.java
java TransferContractDemo
```

Stdout dự kiến, đúng với đoạn mã trên:

```text
Ban đầu: A=100, B=40
Sau chuyển: A=70, B=70
Từ chối: Không đủ số dư
Sau thiếu tiền: A=70, B=70
Tham số sai: Số tiền phải dương
Không chuyển vì: ArithmeticException
Cuối cùng: A=70, B=70, FULL=2147483647
```

### 5.1. Hợp đồng thực tế của `transfer`

**Tiền điều kiện và xử lý vi phạm:**

- Hai tài khoản phải khác `null`; `Objects.requireNonNull` ném `NullPointerException` nếu vi phạm.
- Không cho chuyển từ tài khoản sang chính nó; vi phạm ném `IllegalArgumentException`.
- `amount` phải dương; nếu sai ném `IllegalArgumentException`.
- Tài khoản nguồn phải có đủ tiền; nếu thiếu ném `IllegalStateException` theo lựa chọn API minh họa.
- Số dư đích sau cộng phải nằm trong phạm vi `int`; `Math.addExact` ném `ArithmeticException` nếu tràn.

**Hậu điều kiện khi hoàn thành bình thường:**

- `from.balance` bằng giá trị cũ trừ `amount`.
- `to.balance` bằng giá trị cũ cộng `amount`.
- Cả hai số dư vẫn không âm; tổng số dư của cặp tài khoản giữ nguyên khi tính trong miền số học toán học.

**Cam kết khi thất bại:** với các lỗi kiểm tra ở trên, cả hai số dư giữ nguyên. Bởi chương trình gọi `Math.addExact` trước khi cập nhật, cả trường hợp tràn số cũng không làm mất tiền nguồn.

**Giới hạn ví dụ:** đây là mô hình **tuần tự trong bộ nhớ**. Nó không có khóa và không an toàn cho các lệnh gọi đồng thời trên cùng tài khoản. Nó không phải giao dịch cơ sở dữ liệu hay giao dịch phân tán, không giải quyết crash process ở giữa các thao tác, không tính được tiền tệ thực bằng `int` trong hệ thống sản xuất, và không bảo đảm atomicity đối với quan sát đa luồng. Mục tiêu ở đây là chứng minh một phương pháp thiết kế đường exception, không phải xây ngân hàng thực tế.

### 5.2. Vì sao thứ tự câu lệnh quyết định mức bảo đảm?

Giả sử viết sai:

```java
// Minh họa phản ví dụ bên trong một method; không phải chương trình độc lập.
from.balance -= amount;
to.balance = Math.addExact(to.balance, amount);
```

Nếu `Math.addExact` ném `ArithmeticException` sau khi đã trừ tiền ở nguồn, phương thức thoát ra và **không tự hoàn tác** phép trừ. Khi đó trạng thái một bên đã đổi, một bên chưa đổi.

Sửa bằng cách kiểm tra và tính các giá trị mới trước, rồi mới ghi vào trạng thái như ví dụ đầy đủ. Tổng quát:

```text
Sai:  mutate A → thao tác có thể fail → mutate B
Đúng: validate → chuẩn bị dữ liệu mới → commit thay đổi
```

Công thức “validate rồi commit” hữu ích khi có thể kiểm tra trước mọi lỗi dự kiến và giai đoạn commit ngắn, đáng tin. Nếu ngay trong commit vẫn có thao tác có thể thất bại (ghi file, gọi API, cấp phát bộ nhớ, callback hoặc collection do người khác cài đặt), cần thêm cơ chế transaction, rollback/bù trừ hoặc chấp nhận mức bảo đảm yếu hơn và ghi rõ.

## 6. Trạng thái thay đổi một phần: phân biệt basic với strong guarantee

Một ví dụ rất hay gặp: thêm từng phần tử đã parse vào danh sách hiện có.

```java
// Minh họa bên trong method có biến numbers và inputs.
for (String value : inputs) {
    numbers.add(Integer.parseInt(value));
}
```

Nếu `inputs = ["10", "20", "sai", "30"]`, hai phần tử đầu có thể đã được thêm vào `numbers` trước khi `Integer.parseInt("sai")` ném `NumberFormatException`. Với một `ArrayList` thông thường, danh sách vẫn có thể hợp lệ nhưng đã thay đổi một phần: đó là kết quả phù hợp với **basic guarantee**, không phải strong guarantee. Compiler sẽ không cảnh báo điều này.

Giải pháp khi hợp đồng cần “thay toàn bộ hoặc giữ nguyên” là xây dựng một phiên bản hoàn chỉnh trước khi công bố trạng thái mới.

### 6.1. Chương trình Java 17: snapshot chỉ được thay khi chuẩn bị thành công

Tạo tệp `SnapshotContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SnapshotContractDemo {
    static final class NumberStore {
        private List<Integer> values = List.of();

        void replaceAll(List<String> texts) {
            Objects.requireNonNull(texts, "texts");

            List<Integer> candidate = new ArrayList<>();
            for (String text : texts) {
                int parsed = Integer.parseInt(text);
                if (parsed <= 0) {
                    throw new IllegalArgumentException("Số phải dương");
                }
                candidate.add(parsed);
            }

            // Chuẩn bị snapshot bất biến xong trước khi đổi state.
            List<Integer> ready = List.copyOf(candidate);
            values = ready;
        }

        List<Integer> snapshot() {
            return values;
        }
    }

    public static void main(String[] args) {
        NumberStore store = new NumberStore();

        store.replaceAll(List.of("1", "2"));
        System.out.println("Ban đầu: " + store.snapshot());

        try {
            store.replaceAll(List.of("3", "sai", "4"));
        } catch (NumberFormatException e) {
            System.out.println("Lỗi: " + e.getClass().getSimpleName());
        }
        System.out.println("Sau lỗi parse: " + store.snapshot());

        try {
            store.replaceAll(List.of("5", "0"));
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
        System.out.println("Sau lỗi điều kiện: " + store.snapshot());

        store.replaceAll(List.of("7", "8", "9"));
        System.out.println("Sau cập nhật đúng: " + store.snapshot());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SnapshotContractDemo.java
java SnapshotContractDemo
```

Stdout:

```text
Ban đầu: [1, 2]
Lỗi: NumberFormatException
Sau lỗi parse: [1, 2]
Lỗi: Số phải dương
Sau lỗi điều kiện: [1, 2]
Sau cập nhật đúng: [7, 8, 9]
```

Ở đây, `candidate` là dữ liệu cục bộ. Mọi lần parse, validation và tạo immutable snapshot đều xảy ra trước lệnh `values = ready`. Nếu thất bại trong các bước đó, trường `values` giữ tham chiếu cũ. Khi mọi bước thành công, một phép gán tham chiếu đưa snapshot mới vào sử dụng. `List.copyOf` tạo danh sách không sửa đổi được; caller nhận danh sách từ `snapshot()` không thể dùng `add` hay `remove` để làm thay đổi trạng thái của store.

**Cam kết cần nêu chính xác:** việc giữ nguyên giá trị trường `values` khi phát sinh lỗi ở giai đoạn chuẩn bị là strong guarantee **cho trạng thái nội bộ được mô tả**. Ví dụ chưa đáp ứng điều kiện an toàn luồng: để công bố snapshot giữa các thread, cần cân nhắc `volatile`, synchronization hoặc công cụ concurrency phù hợp. Và việc tạo snapshot tốn bộ nhớ; đây là đánh đổi chấp nhận được hay không tùy tình huống.

### 6.2. Copy-on-write, validate-before-mutate và rollback

Ba cách phổ biến:

| Cách | Khi dùng | Điểm cần cẩn thận |
| --- | --- | --- |
| **Validate-before-mutate** | Có thể kiểm tra toàn bộ tiền điều kiện và thao tác ghi ngắn, ít có khả năng phát sinh lỗi đã dự kiến. | Phải kiểm tra cả tràn số, tham chiếu `null`, thay đổi do caller và điều kiện cạnh tranh. |
| **Copy/prepare then publish** | Thay cả cấu trúc dữ liệu, muốn giữ snapshot cũ nếu parse/validate thất bại. | Tốn bộ nhớ/công; publication giữa các thread cần cơ chế nhìn thấy nhất quán. |
| **Rollback/compensation** | Đã thay đổi nhiều nguồn trạng thái, không thể kiểm tra tất cả trước. | Bản thân rollback có thể thất bại; đặc biệt khó với I/O, mạng và side effect đã phát ra ngoài. |

Không thể “bắt `Exception` rồi rollback tất cả” nếu API/thiết kế không có phương thức khôi phục đủ tin cậy. Cần xác định rõ phạm vi trạng thái thuộc quyền kiểm soát.

## 7. Ngoại lệ lan truyền qua nhiều tầng: ai chịu trách nhiệm điều gì?

Giả sử ứng dụng có luồng:

```text
Giao diện / CLI
    ↓ gọi
OrderService.placeOrder()
    ↓ gọi
InventoryRepository.reserve()
    ↓ gọi
Database / file / API bên ngoài
```

Mỗi tầng có trách nhiệm khác nhau:

- **Tầng hạ tầng:** nêu nguyên nhân kỹ thuật như `IOException`, timeout, lỗi truy cập dữ liệu; nếu API có thể trả kết quả mơ hồ thì phải nêu rõ giới hạn.
- **Tầng nghiệp vụ:** bảo đảm các quy tắc như số lượng dương, không vượt tồn kho; quyết định một lần thao tác có được xem là thành công hay không.
- **Tầng giao tiếp:** chuyển thất bại thành thông báo/kết quả cho người dùng hoặc bên gọi, quyết định khi nào nên nhập lại hay thử lại.

Nếu tầng thấp ném exception, tầng trên cần đọc **cả loại lỗi lẫn trạng thái còn lại**. Ví dụ khi xử lý đơn hàng, lỗi phản hồi từ cổng thanh toán sau khi yêu cầu đã gửi không chứng minh tiền chưa bị trừ. Retry không kiểm soát có thể tạo thao tác lặp; trong hệ thống tích hợp thường cần idempotency key, trạng thái xác nhận hoặc cơ chế đối soát.

Đây là hệ quả trực tiếp của mối quan hệ giữa exception và trạng thái; bản thân `catch` không thể suy ra kết quả của một thao tác bên ngoài chỉ từ việc nó ném lỗi.

### 7.1. Catch tại nơi có thể thực hiện hành động hợp lý

Một nguyên tắc hữu ích: **bắt exception nơi có đủ thông tin để xử lý, chuyển đổi đúng tầng hoặc dọn dẹp**. Không cần bắt mọi exception ngay chỗ phát sinh.

Ví dụ một phương thức tính toán thuần có thể để `IllegalArgumentException` truyền lên caller. Tầng CLI bắt và yêu cầu người dùng nhập lại. Ngược lại, nếu service bắt ngoại lệ rồi im lặng trả `null`, caller có thể nhầm “không có dữ liệu” với “đã thất bại giữa chừng”, dẫn đến trạng thái nghiệp vụ sai.

Phân biệt rõ:

- **Xử lý thực sự:** chọn phương án phục hồi, trả trạng thái lỗi có cấu trúc, sửa input, dừng an toàn, hoặc quyết định retry.
- **Chuyển đổi có ngữ cảnh:** bọc exception thấp thành exception ở tầng cao, giữ nguyên `cause`.
- **Dọn dẹp:** giải phóng resource với try-with-resources; dọn dẹp không nhất thiết là xử lý lỗi nghiệp vụ.
- **Chỉ ghi log:** có thể giúp quan sát, nhưng nếu sau đó nuốt lỗi mà không có hợp đồng phù hợp, trạng thái caller sẽ bị hiểu sai.

### 7.2. Bọc exception nhưng giữ nguyên nguyên nhân

Đoạn sau là **minh họa trong một method**, không phải chương trình độc lập:

```java
try {
    repository.load();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không thể nạp cấu hình", e);
}
```

`e` trở thành **cause** của `IllegalStateException` mới. Khi đọc stack trace, người phát triển có thể tìm được nguyên nhân gốc. Nên dùng constructor nhận cause hoặc `initCause` theo API thích hợp thay vì chỉ lấy `e.getMessage()` rồi bỏ đối tượng gốc.

Đừng dịch tất cả lỗi thành một exception quá chung nếu caller thực sự cần phân biệt “không tồn tại”, “không có quyền”, “dữ liệu sai” và “dịch vụ tạm ngừng”. Đồng thời, không nên lộ thông tin nhạy cảm (đường dẫn riêng, tài khoản, token, câu SQL bí mật) qua thông điệp trả cho người dùng.

## 8. `finally` và try-with-resources bảo đảm dọn dẹp, không hoàn tác nghiệp vụ

Xét:

```java
try {
    balance -= 10;
    doSomethingThatMayThrow();
} finally {
    System.out.println("Dọn dẹp");
}
```

Đây là đoạn mã minh họa nằm trong một phương thức. Nếu `doSomethingThatMayThrow()` ném exception, `finally` thông thường vẫn chạy, **nhưng `balance` đã bị trừ 10**. Một khối `finally` không tự động hoàn tác phép gán, không khởi tạo lại đối tượng và không quyết định một giao dịch nghiệp vụ có thành công hay không.

Đặc biệt tránh `return` hay ném exception mới trong `finally` nếu điều đó che lấp lỗi gốc. `finally` cũng không được bảo đảm chạy khi JVM/process bị chấm dứt đột ngột.

### 8.1. Tài nguyên đóng lỗi: primary và suppressed exception

Try-with-resources là cách ưu tiên để quản lý đối tượng `AutoCloseable`. Có tình huống thao tác chính thất bại **và** `close()` cũng thất bại. Java giữ exception từ thân khối làm exception chính và đưa lỗi phát sinh khi đóng vào danh sách **suppressed**.

Tạo tệp `SuppressedContractDemo.java`:

```java
import java.io.IOException;

public class SuppressedContractDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("lỗi xử lý");
        } catch (IOException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Số lỗi suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed đầu: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SuppressedContractDemo.java
java SuppressedContractDemo
```

Stdout:

```text
Chính: lỗi xử lý
Số lỗi suppressed: 1
Suppressed đầu: lỗi đóng
```

Phương thức `close()` được gọi khi rời khối. Lỗi đóng không thay lỗi chính ở tình huống này mà được gắn vào `getSuppressed()`. Nếu thân khối không ném lỗi nhưng `close()` ném lỗi, exception khi đóng có thể trở thành exception thoát ra ngoài. Với nhiều resource, Java đóng theo thứ tự ngược thứ tự khai báo.

Dọn dẹp tài nguyên và hoàn tác nghiệp vụ là hai trách nhiệm khác nhau: đóng kết nối không tự hủy các thay đổi đã commit; rollback transaction chỉ tồn tại nếu cơ chế transaction tương ứng được sử dụng đúng.

## 9. Quyết định kiểu exception dựa trên hợp đồng và khả năng phục hồi

Khi viết API, hãy trả lời trước: **caller có hành động được gì khi thất bại?** Sau đó mới chọn kiểu kết quả/exception.

| Tình huống | Một thiết kế phù hợp | Điều phải tài liệu hóa |
| --- | --- | --- |
| Tham số sai (số lượng âm, đối tượng `null` không hợp lệ) | `IllegalArgumentException` / `NullPointerException` theo ý nghĩa API | Điều kiện hợp lệ; khi vi phạm, trạng thái có đổi không. |
| Trạng thái hiện tại không cho phép thao tác | `IllegalStateException` hoặc exception nghiệp vụ riêng | Quy tắc trạng thái, kết quả khi thất bại. |
| File không đọc được | `IOException` (checked) | Caller bắt/khai báo; nội dung đích đã bị ảnh hưởng hay chưa. |
| Không tìm thấy dữ liệu là trường hợp thông thường | `Optional<T>`/kết quả có cấu trúc hoặc exception nếu API quy ước như vậy | Ý nghĩa “không tìm thấy” khác gì “truy vấn thất bại”. |
| Dữ liệu người dùng parse không hợp lệ | Bắt `NumberFormatException` ở ranh giới nhập liệu hoặc chuyển sang kết quả validation | Người dùng được nhập lại thế nào; không dùng giá trị giả không có hợp đồng. |
| Yêu cầu gửi qua mạng không nhận phản hồi | Exception kết nối/timeout phù hợp; trạng thái kết quả có thể chưa xác định | Chính sách retry, chống trùng và cách xác nhận kết quả. |

Exception tùy biến chỉ nên có khi caller cần phân loại/phản ứng khác hoặc API muốn truyền ngữ nghĩa có giá trị. Không cần tạo `MyIllegalArgumentException` chỉ để đổi tên của lỗi chuẩn đã diễn đạt đúng.

### 9.1. Khi nào nên trả kết quả thay cho ném exception?

Nếu một tình huống là nhánh kết quả được dự kiến xảy ra thường xuyên (tìm kiếm không thấy phần tử, người dùng thử kiểm tra tính hợp lệ), API có thể dùng `boolean`, `Optional` hoặc loại kết quả rõ trạng thái thay vì dùng exception làm vòng điều khiển thường nhật.

Ngược lại, việc “bọc tất cả vào `boolean`” cũng có thể làm mất nguyên nhân lỗi, khiến caller không biết thao tác đã thay đổi một phần hay chưa. Chọn cách biểu đạt theo bản chất: dữ liệu đầu vào không hợp lệ, thất bại kỹ thuật, hoặc kết quả nghiệp vụ bình thường là những khái niệm cần phân biệt.

### 9.2. Chính sách retry phải phụ thuộc trạng thái, không chỉ kiểu exception

Retry thường hợp lý khi thao tác có tính **idempotent** (lặp lại không tạo thêm hiệu ứng ngoài ý định) hoặc có cơ chế chống xử lý trùng. Nếu caller không biết thao tác đã thành công phía server hay chưa, retry vô điều kiện có thể nhân đôi số lần chuyển tiền/gửi email/đặt đơn.

Một exception chỉ biểu thị việc lời gọi không hoàn thành bình thường từ góc nhìn hiện tại. Trạng thái thực tế của hệ thống ngoài tiến trình có thể phải được xác minh bằng API tra cứu trạng thái hoặc giao thức riêng.

## 10. Ghi tài liệu hợp đồng rõ ràng trong Javadoc

Ví dụ sau minh họa **cách ghi hợp đồng** cho `transfer` ở Mục 5; chữ ký lặp lại chỉ để giới thiệu Javadoc và không tạo thành tệp độc lập:

```java
/**
 * Chuyển amount từ from sang to khi đủ điều kiện.
 *
 * <p>Tiền điều kiện: hai tài khoản khác null, khác nhau,
 * amount dương, nguồn đủ tiền và đích không tràn int.</p>
 *
 * <p>Khi trả về bình thường: số dư from giảm amount,
 * số dư to tăng amount.</p>
 *
 * <p>Nếu một trong các kiểm tra dưới đây thất bại,
 * số dư của cả hai tài khoản được giữ nguyên.</p>
 *
 * <p>Không an toàn khi gọi đồng thời trên cùng tài khoản.</p>
 *
 * @throws NullPointerException nếu from hoặc to là null
 * @throws IllegalArgumentException nếu trùng tài khoản hoặc amount <= 0
 * @throws IllegalStateException nếu nguồn không đủ số dư
 * @throws ArithmeticException nếu số dư đích bị tràn int
 */
static void transfer(Account from, Account to, int amount) {
    // Phần thân phương thức nằm trong ví dụ đầy đủ Mục 5.
}
```

Trong Javadoc thực tế, không dùng thân stub của đoạn trên để thay implementation. Điểm cần học là: `@throws` nói **khi nào và vì sao** lỗi được phát ra, còn phần mô tả văn bản nêu **tác động lên trạng thái**. Một API tốt thường cần cả hai.

Không cần ghi mọi unchecked exception có thể phát sinh từ VM hay thư viện; ưu tiên những trường hợp có thể dự kiến và tác động đến cách caller sử dụng API. Cam kết không được mạnh hơn khả năng implementation thực tế.

## 11. Kiểm thử hợp đồng: luôn xác nhận đường thất bại và trạng thái còn lại

Test chỉ kiểm tra `assertThrows(...)` là chưa đủ nếu contract hứa giữ nguyên dữ liệu. Test nên quan sát cả **exception** và **state**.

Ví dụ JUnit 5 sau là một **đoạn kiểm thử minh họa** dùng `TransferContractDemo` ở Mục 5, cần dự án có dependency JUnit Jupiter tương ứng để biên dịch; không phải chương trình `javac` độc lập:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TransferContractDemoTest {
    @Test
    void insufficientFundsDoesNotChangeBalances() {
        var from = new TransferContractDemo.Account("A", 20);
        var to = new TransferContractDemo.Account("B", 8);

        assertThrows(IllegalStateException.class,
                () -> TransferContractDemo.transfer(from, to, 25));

        assertEquals(20, from.balance());
        assertEquals(8, to.balance());
    }

    @Test
    void overflowDoesNotDebitSource() {
        var from = new TransferContractDemo.Account("A", 10);
        var to = new TransferContractDemo.Account(
                "B", Integer.MAX_VALUE);

        assertThrows(ArithmeticException.class,
                () -> TransferContractDemo.transfer(from, to, 1));

        assertEquals(10, from.balance());
        assertEquals(Integer.MAX_VALUE, to.balance());
    }

    @Test
    void successfulTransferUpdatesBothBalances() {
        var from = new TransferContractDemo.Account("A", 20);
        var to = new TransferContractDemo.Account("B", 8);

        TransferContractDemo.transfer(from, to, 5);

        assertEquals(15, from.balance());
        assertEquals(13, to.balance());
    }
}
```

Vì hai lớp trên không khai báo `package` và `Account` cùng `transfer` có quyền truy cập package-private, file test cũng phải đặt cùng package (trong ví dụ là default package). Trong dự án thực tế nên chọn package, mức truy cập và vị trí test phù hợp.

Một ma trận test tối thiểu:

| Trường hợp | Exception/kết quả mong đợi | Trạng thái cần kiểm |
| --- | --- | --- |
| Input hợp lệ | Method trả về bình thường | Hậu điều kiện đúng, invariant đúng. |
| Tham số sai | Loại exception được tài liệu hóa | Trạng thái giữ nguyên nếu contract hứa strong guarantee. |
| Thiếu dữ liệu/trạng thái không cho phép | Exception hoặc kết quả theo hợp đồng | Không xuất hiện thay đổi không được mô tả. |
| Tràn số / parse lỗi | Exception cụ thể | Không làm hỏng số dư, danh sách hoặc dữ liệu nội bộ. |
| Thất bại sau một số side effect | Exception phù hợp | Xác định rõ tiến độ thực hiện, rollback/bù trừ hoặc trạng thái chưa chắc chắn. |
| Dọn dẹp tài nguyên cũng lỗi | Primary/suppressed exception đúng | Resource được xử lý theo hợp đồng; không mất lỗi gốc. |

**Mẹo test:** lưu bản sao/snapshot trước lời gọi; sau `assertThrows`, so sánh từng trường liên quan, cấu trúc dữ liệu, số lần gọi dependency hoặc hiệu ứng có thể quan sát. Với external side effect, dùng fake/mock hay môi trường tích hợp phù hợp, nhưng đừng biến xác nhận “mock đã được gọi” thành bằng chứng rằng hệ thống thật có transaction.

## 12. Các sai lầm điển hình

### 12.1. “Ném exception tức là không có gì thay đổi”

Sai. Nếu đã gọi `list.add`, ghi file hoặc gửi HTTP trước khi lỗi được ném, tác động trước đó có thể vẫn tồn tại. Cần xác định điểm commit và mức bảo đảm thất bại; không dựa vào trực giác.

### 12.2. “Bắt được exception là khôi phục được trạng thái”

Sai. `catch` cung cấp vị trí xử lý lỗi, không tạo snapshot hay undo log. Nếu muốn rollback, phải có cơ chế khôi phục trạng thái tương ứng. Đặc biệt, side effect ngoài JVM thường không có thao tác “đảo ngược” đơn giản.

### 12.3. “`finally` luôn rollback”

Sai. `finally` dùng để chạy logic dọn dẹp theo quy tắc của Java, không tự lưu giá trị cũ hay hoàn tác. `try-with-resources` giúp đóng tài nguyên; một kết nối được đóng không có nghĩa mọi giao dịch bên ngoài đều đã rollback.

### 12.4. “Có `throws IOException` là caller đã biết toàn bộ hợp đồng”

Sai. Caller chỉ biết một phần đường lỗi ở mức kiểu checked exception. Cần biết tính toàn vẹn dữ liệu, tài nguyên, mức tiến độ đã thực hiện, khả năng thử lại và những unchecked exception được dự kiến.

### 12.5. “Chuyển checked thành unchecked sẽ giải quyết lỗi”

Sai. Việc bọc `IOException` bằng `RuntimeException` chỉ thay cách compiler buộc caller xử lý. Nó không sửa được nguyên nhân, không phục hồi trạng thái và không bảo đảm an toàn hơn. Chỉ chuyển loại exception nếu đúng ranh giới trừu tượng và giữ cause.

### 12.6. “Luôn bắt `Exception` hoặc `Throwable`”

Bắt rất rộng rồi bỏ qua thường che cả lỗi lập trình, khiến trạng thái hỏng âm thầm lan xa. `Error` thường không nên được bắt như sự cố nghiệp vụ thông thường. Ở ranh giới kiểm soát tập trung (ví dụ một worker loop), handler rộng có thể phù hợp, nhưng cần chính sách phục hồi, log, dừng hoặc cách ly công việc rõ ràng.

### 12.7. “Exception safety mạnh đồng nghĩa thread-safe”

Không đúng. Một phép thay tham chiếu sau khi chuẩn bị xong có thể giữ trạng thái cũ trên đường exception trong một thread, nhưng các thread khác vẫn cần quy tắc visibility và đồng bộ thích hợp. Hai phép gán cập nhật hai đối tượng cũng không tự trở thành một giao dịch nguyên tử cho quan sát đồng thời.

### 12.8. “Message exception là hợp đồng duy nhất cần test”

Message có thể thay đổi theo locale, phiên bản hoặc chính sách thông báo. Nếu code cần phân loại lỗi, ưu tiên kiểu exception hay mã lỗi đã tài liệu hóa; so sánh text chính xác chỉ khi message thực sự thuộc contract.

### 12.9. “Chỉ cần xử lý từng bước thành công”

Các bug nghiêm trọng thường xuất hiện ở đường thất bại **sau khi đã có thay đổi**. Hãy tạo test lỗi ở mỗi ranh giới có side effect: trước cập nhật, giữa cập nhật, sau cập nhật nhưng trước xác nhận, trong close, và khi retry.

## 13. Bài tập tự thực hành

**Bài 1 — Chỉ ra hợp đồng bị vi phạm.** Cho method giả định:

```java
// Đoạn minh họa, giả sử data là List<Integer> và input là List<String>.
void replace(List<String> input) {
    data.clear();
    for (String text : input) {
        data.add(Integer.parseInt(text));
    }
}
```

Đề bài của method: “Thay danh sách nếu tất cả chuỗi là số hợp lệ; nếu có lỗi, giữ danh sách cũ.” Hãy giải thích tại sao `data.clear()` phá vỡ hợp đồng trước khi parse hoàn tất. Sửa bằng cách chuẩn bị danh sách mới rồi **thay tham chiếu trường** một lần, nếu thiết kế cho phép, giống Mục 6. Đừng chỉ đổi thành `try/catch` rồi thêm lại phần tử cũ một cách thủ công nếu chưa xét trường hợp rollback cũng thất bại.

**Bài 2 — Tự chọn cách báo lỗi.** Viết `reserve(int quantity)` với invariant tồn kho không âm. Với `quantity <= 0`, chọn `IllegalArgumentException`; với lượng vượt tồn kho, chọn rõ một trong `IllegalStateException`, exception nghiệp vụ hoặc kết quả có cấu trúc. Viết Javadoc giải thích choice, hậu điều kiện và mức bảo đảm khi thất bại; test cả thành công lẫn tồn kho không đủ.

**Bài 3 — Dự đoán exception và state.** Trong ví dụ chuyển tiền, thử thay `Math.addExact` bằng phép cộng `to.balance + amount`. Điều gì có thể xảy ra khi gần `Integer.MAX_VALUE`? Giải thích overflow số nguyên Java khác với ngoại lệ tự động. Sau đó đưa `Math.addExact` trở lại và xác nhận test overflow.

**Bài 4 — Cause và suppressed.** Viết method bọc `IOException` với cause, sau đó chạy `SuppressedContractDemo`. Chỉ ra hai quan hệ khác nhau: `getCause()` diễn tả lỗi dẫn đến exception mới, còn `getSuppressed()` lưu lỗi phụ phát sinh trong khi lỗi chính đang được xử lý/dọn dẹp.

**Bài 5 — Suy luận về retry.** Một lời gọi `placeOrder()` gửi request rồi timeout trước khi nhận response. Liệt kê ít nhất ba khả năng về trạng thái phía server: request chưa tới, đã tới nhưng chưa hoàn tất, đã hoàn tất nhưng response mất. Đề xuất phương thức xác nhận/idempotency trước khi tự động gửi lại.

## 14. Checklist thiết kế API có exception

Trước khi công bố một method quan trọng, lần lượt trả lời:

- [ ] Các precondition có rõ và được kiểm tra trước side effect quan trọng không?
- [ ] Hậu điều kiện sau `return` có thể xác minh bằng test không?
- [ ] Invariant của từng đối tượng liên quan có được bảo toàn khi lỗi xảy ra không?
- [ ] Với từng exception có thể dự kiến, dữ liệu giữ nguyên, thay đổi một phần hay chưa xác định?
- [ ] `throws` và `@throws` phản ánh đúng các checked exception và trường hợp thất bại chính không?
- [ ] API có tạo ngoại lệ phù hợp, không che lỗi lập trình và không dùng kiểu quá rộng không?
- [ ] Nếu chuyển đổi exception, đã giữ `cause` và ngữ cảnh cần thiết chưa?
- [ ] Tài nguyên có được đóng bằng try-with-resources, lỗi suppressed có được giữ khi có giá trị chẩn đoán không?
- [ ] Có giới hạn rõ giữa thao tác trong bộ nhớ và side effect bên ngoài không?
- [ ] Caller có đủ thông tin để quyết định xử lý, rollback, xác nhận trạng thái hoặc retry an toàn không?
- [ ] Nếu nhiều thread có thể gọi cùng lúc, đã có bảo đảm atomicity/visibility ngoài exception safety chưa?
- [ ] Test có kiểm tra cả loại exception **và trạng thái sau thất bại**, chứ không chỉ thông điệp lỗi không?

**Kết luận:** hợp đồng cho biết điều gì phải đúng khi method thành công và khi thất bại; exception là tín hiệu của đường kết thúc bất thường; trạng thái cho biết tác động thật sự đã xảy ra. Muốn thiết kế API đáng tin, cần xác định và kiểm thử cả ba yếu tố ngay từ lúc viết phương thức, đặc biệt ở ranh giới trước và sau mỗi side effect.