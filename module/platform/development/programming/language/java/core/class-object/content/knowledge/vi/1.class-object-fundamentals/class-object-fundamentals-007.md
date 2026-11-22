# Ví dụ xuyên suốt: mô hình hóa tài khoản ngân hàng bằng lớp và đối tượng trong Java

Một tài khoản ngân hàng là ví dụ dễ thấy về mối quan hệ giữa **lớp (class)**, **đối tượng (object)**, **trạng thái (state)** và **hành vi (behavior)**. Thay vì chỉ học cú pháp `class` và `new` riêng lẻ, bài này đi từ yêu cầu thực tế đến một chương trình Java chạy được, sau đó giải thích chính xác mỗi phần trong chương trình tương ứng với khái niệm nào.

**Phạm vi:** đây là mô hình học tập chạy trong một tiến trình, theo thứ tự từng lệnh, với số tiền tính bằng **đồng Việt Nam nguyên (VND)**. Mục tiêu là hiểu cách thiết kế và sử dụng đối tượng. Một hệ thống ngân hàng thực tế còn đòi hỏi xác thực, lưu trữ bền vững, lịch sử giao dịch, kiểm soát đồng thời và giao dịch cơ sở dữ liệu.

## 1. Chuyển yêu cầu thực tế thành mô hình

Giả sử chương trình phải quản lý hai tài khoản, An và Bình, với các yêu cầu:

1. Mỗi tài khoản có số tài khoản, tên chủ tài khoản và số dư.
2. Tạo tài khoản với số dư ban đầu không âm.
3. Có thể **nạp tiền**, **rút tiền**, **chuyển tiền** từ tài khoản này sang tài khoản khác.
4. Số tiền mỗi giao dịch phải dương; không rút hoặc chuyển quá số dư.
5. Chỉ những phương thức của lớp mới được trực tiếp thay đổi số dư; mã bên ngoài chỉ đọc số dư.
6. Thay đổi số dư của An không tự làm thay đổi số dư Bình, trừ khi có thao tác chuyển tiền giữa hai tài khoản.

Ta xác định một **lớp** `BankAccount` làm kiểu chung. Mỗi tài khoản cụ thể là một **đối tượng** của lớp này.

| Thành phần của bài toán | Biểu diễn trong Java | Ý nghĩa |
| --- | --- | --- |
| Kiểu tài khoản | `class BankAccount` | Bản định nghĩa chung của các tài khoản |
| Số tài khoản | Trường `accountNumber` | Dữ liệu nhận diện nghiệp vụ của một tài khoản |
| Tên chủ tài khoản | Trường `ownerName` | Dữ liệu mô tả chủ tài khoản |
| Số dư | Trường `balance` | Trạng thái riêng, thay đổi theo giao dịch |
| Mở tài khoản | Constructor `BankAccount(...)` | Thiết lập trạng thái ban đầu hợp lệ |
| Nạp tiền | `deposit(amount)` | Hành vi làm tăng số dư |
| Rút tiền | `withdraw(amount)` | Hành vi làm giảm số dư có kiểm tra |
| Chuyển tiền | `transferTo(receiver, amount)` | Hành vi ảnh hưởng hai đối tượng |
| Xem thông tin | `summary()`, `balance()` | Đọc trạng thái mà không cho bên ngoài sửa trực tiếp |

Ví dụ hai biểu thức:

~~~java
BankAccount an = new BankAccount("VN001", "An", 1_000_000);
BankAccount binh = new BankAccount("VN002", "Binh", 500_000);
~~~

Cả hai đều có **kiểu** `BankAccount`, nhưng tạo **hai đối tượng khác nhau**. `an` và `binh` là **biến tham chiếu**, còn dữ liệu số dư cụ thể thuộc về các đối tượng mà chúng trỏ tới.

## 2. Quyết định thiết kế trước khi viết code

### Trạng thái và tính bất biến của dữ liệu

Đối với mô hình đơn giản này, số tài khoản và tên chủ tài khoản được thiết lập một lần lúc tạo đối tượng, nên dùng `private final String`. Số dư thay đổi trong suốt đời sống đối tượng, nên dùng `private long balance`. `final` bảo vệ việc gán lại một trường sau khởi tạo; nó không tự động biến toàn bộ đối tượng thành bất biến.

Tất cả trường được khai báo `private` để mã gọi không thể thực hiện kiểu thao tác nguy hiểm như `an.balance = -100`. Những thay đổi hợp lệ phải đi qua phương thức có kiểm tra.

### Quy tắc phải luôn đúng (invariant)

Một đối tượng `BankAccount` hợp lệ trong bài này phải thỏa:

- `accountNumber` và `ownerName` không phải `null`, không rỗng hoặc chỉ có khoảng trắng.
- `balance >= 0`.
- Tiền nạp, rút, chuyển là số nguyên dương.
- Không chuyển tiền tới chính tài khoản đang chuyển.
- Nếu yêu cầu rút/chuyển không hợp lệ, số dư các tài khoản liên quan vẫn giữ nguyên.

Constructor kiểm tra trạng thái ban đầu. Các phương thức thay đổi trạng thái kiểm tra điều kiện trước khi cập nhật.

### Biểu diễn tiền

Vì ví dụ dùng **số đồng VND nguyên**, kiểu `long` đơn giản và tránh sai số nhị phân khi dùng `double` cho phép cộng trừ tiền. `long` vẫn có giới hạn giá trị; ta dùng `Math.addExact` để phát hiện cộng tràn thay vì âm thầm tạo kết quả sai. Với số tiền có đơn vị nhỏ lẻ hoặc nhiều loại tiền tệ, thiết kế phù hợp hơn thường là `BigDecimal` kèm quy tắc làm tròn, thang đo và kiểu tiền tệ rõ ràng.

## 3. Chương trình hoàn chỉnh

Tạo đúng một tệp tên **`BankAccountDemo.java`** trong thư mục làm việc. Tệp có hai lớp cấp cao nhất: `BankAccount` không mang `public`; `BankAccountDemo` là lớp `public` chứa `main`, vì vậy tên tệp phải trùng `BankAccountDemo`.

~~~java
import java.util.Objects;

class BankAccount {
    private final String accountNumber;
    private final String ownerName;
    private long balance;

    BankAccount(String accountNumber, String ownerName, long initialBalance) {
        if (accountNumber == null || accountNumber.isBlank()) {
            throw new IllegalArgumentException("Số tài khoản không hợp lệ");
        }
        if (ownerName == null || ownerName.isBlank()) {
            throw new IllegalArgumentException("Tên chủ tài khoản không hợp lệ");
        }
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư ban đầu không được âm");
        }

        this.accountNumber = accountNumber;
        this.ownerName = ownerName;
        this.balance = initialBalance;
    }

    String accountNumber() {
        return accountNumber;
    }

    long balance() {
        return balance;
    }

    String summary() {
        return accountNumber + " | " + ownerName + " | " + balance + " VND";
    }

    void deposit(long amount) {
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    void withdraw(long amount) {
        requirePositive(amount);
        if (amount > balance) {
            throw new IllegalArgumentException("Số dư không đủ");
        }
        balance -= amount;
    }

    void transferTo(BankAccount receiver, long amount) {
        Objects.requireNonNull(receiver, "receiver");
        requirePositive(amount);

        if (receiver == this) {
            throw new IllegalArgumentException("Không thể chuyển cho chính mình");
        }
        if (amount > balance) {
            throw new IllegalArgumentException("Số dư không đủ");
        }

        // Tính trước để nếu cộng tràn thì hai số dư chưa bị thay đổi.
        long receiverNewBalance = Math.addExact(receiver.balance, amount);

        balance -= amount;
        receiver.balance = receiverNewBalance;
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
    }
}

public class BankAccountDemo {
    public static void main(String[] args) {
        BankAccount an = new BankAccount("VN001", "An", 1_000_000);
        BankAccount binh = new BankAccount("VN002", "Binh", 500_000);

        System.out.println("Ban đầu:");
        System.out.println(an.summary());
        System.out.println(binh.summary());

        an.deposit(200_000);
        an.withdraw(50_000);
        an.transferTo(binh, 300_000);

        System.out.println("Sau giao dịch:");
        System.out.println(an.summary());
        System.out.println(binh.summary());

        BankAccount anotherNameForAn = an;
        System.out.println("an == anotherNameForAn: "
                + (an == anotherNameForAn));
        System.out.println("an == binh: " + (an == binh));

        try {
            an.withdraw(900_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rút thất bại: " + ex.getMessage());
        }

        System.out.println("Số dư An cuối: " + an.balance() + " VND");
    }
}
~~~

Yêu cầu **Java 17 trở lên**. Tại thư mục chứa tệp, chạy:

~~~bash
javac -encoding UTF-8 BankAccountDemo.java
java BankAccountDemo
~~~

Kết quả trên stdout:

~~~text
Ban đầu:
VN001 | An | 1000000 VND
VN002 | Binh | 500000 VND
Sau giao dịch:
VN001 | An | 850000 VND
VN002 | Binh | 800000 VND
an == anotherNameForAn: true
an == binh: false
Rút thất bại: Số dư không đủ
Số dư An cuối: 850000 VND
~~~

`javac` có thể tạo các tệp `BankAccount.class` và `BankAccountDemo.class`. Không cần một tệp `BankAccount.java` riêng để chạy ví dụ này. Nếu tách thành hai tệp khi mở rộng dự án, quy tắc đặt tên lớp `public` và package phải được áp dụng nhất quán.

## 4. Lần theo các đối tượng và biến tham chiếu

Sau hai lệnh `new BankAccount(...)`, ta có thể hình dung:

~~~text
LỚP: BankAccount
  định nghĩa các trường và phương thức chung
                       |
                       v
  Biến an -----------------> Đối tượng A
                             accountNumber = "VN001"
                             ownerName = "An"
                             balance = 1000000

  Biến binh ---------------> Đối tượng B
                             accountNumber = "VN002"
                             ownerName = "Binh"
                             balance = 500000
~~~

Các phương thức `deposit`, `withdraw`, `transferTo` được **định nghĩa ở lớp**; khi gọi phương thức instance, chương trình thực hiện thao tác với đúng đối tượng nhận lời gọi.

`an.deposit(200_000)` tác động đến đối tượng A. `binh` không thay đổi vì hai đối tượng giữ hai trường `balance` riêng. `an.transferTo(binh, 300_000)` là trường hợp một phương thức cố ý cập nhật **hai** đối tượng: đối tượng nguồn nhận qua `this` và đối tượng đích nhận qua tham số `receiver`.

Trong constructor:

~~~java
this.accountNumber = accountNumber;
this.ownerName = ownerName;
this.balance = initialBalance;
~~~

`this.accountNumber` là trường của đối tượng đang được khởi tạo; `accountNumber` không có `this` ở vế phải là tham số. Tương tự với tên chủ tài khoản và số dư ban đầu. `this` không tồn tại trong phương thức `static`, vì phương thức `static` không được gọi với một đối tượng nhận riêng.

Câu lệnh:

~~~java
BankAccount anotherNameForAn = an;
~~~

**Không tạo tài khoản mới.** Nó chỉ sao chép giá trị tham chiếu từ `an` sang một biến khác. Vì vậy `an == anotherNameForAn` cho `true`: hai biến trỏ đến **cùng một đối tượng**. `an == binh` cho `false`: hai biểu thức `new` đã tạo hai instance khác nhau.

Nếu `anotherNameForAn.deposit(10_000)`, `an.balance()` cũng sẽ phản ánh thay đổi đó, vì hai biến quan sát cùng đối tượng. Ngược lại, muốn có đối tượng riêng phải tạo instance khác bằng cách thích hợp.

## 5. Theo dõi trạng thái sau từng giao dịch

Ta có thể kiểm tra toàn bộ phép tính mà không cần đoán kết quả.

| Bước | Lệnh | An (VND) | Bình (VND) | Giải thích |
| --- | --- | ---: | ---: | --- |
| 0 | Tạo hai đối tượng | 1.000.000 | 500.000 | Constructor nhận số dư ban đầu |
| 1 | `an.deposit(200_000)` | 1.200.000 | 500.000 | Chỉ tài khoản An được cộng |
| 2 | `an.withdraw(50_000)` | 1.150.000 | 500.000 | An còn đủ tiền nên được trừ |
| 3 | `an.transferTo(binh, 300_000)` | 850.000 | 800.000 | Trừ An 300.000 và cộng Bình 300.000 |
| 4 | `an.withdraw(900_000)` | 850.000 | 800.000 | Bị từ chối: yêu cầu vượt số dư |

Ở bước 3, **tổng số dư** trước và sau chuyển vẫn là `1_650_000` VND vì giao dịch chỉ chuyển giữa hai tài khoản đang mô phỏng: `1_150_000 + 500_000 = 850_000 + 800_000`. Tại bước 4, exception xảy ra **trước** lệnh trừ số dư, nên tài khoản An vẫn giữ 850.000 VND.

Lưu ý: nạp/rút trong mô hình không mô tả nguồn hoặc đích tiền bên ngoài, nên không thể suy ra một định luật bảo toàn tổng tiền cho tất cả thao tác. Đây là ví dụ về trạng thái đối tượng chứ chưa phải hệ thống sổ cái.

## 6. Giải thích cơ chế của từng phương thức

### Constructor: tạo trạng thái hợp lệ ngay từ đầu

Constructor `BankAccount(String, String, long)` được gọi khi thực hiện `new BankAccount(...)`. Nó xác thực dữ liệu đầu vào rồi khởi tạo ba trường. Nếu yêu cầu không hợp lệ, `IllegalArgumentException` được ném và biểu thức tạo đối tượng không hoàn tất bình thường.

Điểm cần phân biệt: **constructor không có kiểu trả về** (không viết cả `void`), tên trùng tên lớp và chỉ là một phần của quy trình tạo instance. `new` mới là biểu thức tạo đối tượng. Hai lần gọi constructor tương ứng với hai đối tượng riêng.

### `deposit`: thay đổi trạng thái của đối tượng nhận

~~~java
void deposit(long amount) {
    requirePositive(amount);
    balance = Math.addExact(balance, amount);
}
~~~

Đầu tiên kiểm tra `amount > 0`. Tiếp theo, `Math.addExact` cộng chính xác hai số `long` hoặc ném `ArithmeticException` nếu tràn. Vì phép cộng được tính trước phép gán, số dư không thay đổi nếu có lỗi tràn số. `balance` trong phương thức instance tương đương `this.balance` trong ngữ cảnh này.

### `withdraw`: không phá vỡ invariant

~~~java
void withdraw(long amount) {
    requirePositive(amount);
    if (amount > balance) {
        throw new IllegalArgumentException("Số dư không đủ");
    }
    balance -= amount;
}
~~~

Việc kiểm tra số tiền dương và số dư **diễn ra trước** phép trừ. Kết quả là không thể hoàn thành một lệnh rút khiến `balance` âm theo đường gọi phương thức này. Code bên ngoài cũng không được sửa trực tiếp trường `private balance`.

### `transferTo`: tương tác giữa hai object

Chuyển tiền là thao tác có hai đối tượng tham gia:

- `this` là tài khoản **gửi**, chính là đối tượng ở bên trái dấu chấm của `an.transferTo(...)`.
- `receiver` là tài khoản **nhận**, được truyền qua đối số; trong ví dụ là đối tượng mà `binh` tham chiếu.

Các kiểm tra lần lượt loại bỏ đối tượng nhận `null`, số tiền không dương, gửi cho chính mình và số dư không đủ. Biểu thức `receiver == this` so sánh **danh tính object**, không so sánh số tài khoản hay chủ tài khoản.

Sau khi kiểm tra, phương thức tính `receiverNewBalance` trước khi gán để tránh tình huống trừ tài khoản gửi rồi mới phát hiện cộng tài khoản nhận bị tràn `long`. Điều này cải thiện tính nhất quán trong **ví dụ chạy tuần tự**; không tạo ra một giao dịch ngân hàng có bảo đảm ACID. Khi nhiều luồng, nhiều tiến trình hoặc lỗi hệ thống xuất hiện, vẫn cần cơ chế đồng bộ, giao dịch lưu trữ và phục hồi phù hợp.

### `summary` và `balance`: đọc dữ liệu, không cấp quyền sửa

`summary()` tạo chuỗi biểu diễn trạng thái. `balance()` trả về một giá trị `long`; gọi `long amount = an.balance()` chỉ sao chép số nguyên, không mở đường sửa trường nội bộ. Đây là cách đơn giản để tách quyền **đọc trạng thái** và quyền **thay đổi trạng thái**.

## 7. Phân biệt danh tính đối tượng và danh tính nghiệp vụ

Có hai câu hỏi khác nhau:

1. **Hai tham chiếu có trỏ cùng một đối tượng trong JVM không?** Với kiểu tham chiếu, `a == b` trả lời câu hỏi này.
2. **Hai bản ghi mô tả cùng một tài khoản nghiệp vụ không?** Câu hỏi này thường dựa trên `accountNumber` cùng quy tắc định danh của hệ thống, không chỉ dựa vào `==`.

Ví dụ minh họa (các dòng dưới đây là đoạn mã đặt trong một phương thức, không phải chương trình độc lập):

~~~java
BankAccount first = new BankAccount("VN100", "Lan", 100_000);
BankAccount second = new BankAccount("VN100", "Lan", 100_000);

System.out.println(first == second); // false
System.out.println(first.accountNumber().equals(second.accountNumber())); // true
~~~

Hai đối tượng **khác danh tính tham chiếu** vì được tạo qua hai lần `new`, dù cùng số tài khoản. Trong ứng dụng thật, kho lưu trữ thường phải bảo đảm số tài khoản là duy nhất; constructor của ví dụ này không biết những đối tượng khác đã tồn tại nên **không bảo đảm tính duy nhất toàn hệ thống**.

Không nên tùy tiện ghi đè `equals()` chỉ để so sánh mọi trường của tài khoản. Việc chọn tiêu chí đồng nhất nghiệp vụ và quan hệ với `hashCode()` là quyết định thiết kế riêng, đặc biệt khi đối tượng có trạng thái thay đổi.

## 8. Những trường hợp cần kiểm tra

Bài học về object không chỉ nằm ở kết quả thành công. Các trường hợp dưới đây cho biết điều kiện bảo vệ trạng thái có hoạt động như dự kiến không.

| Thao tác | Kết quả mong đợi | Trạng thái sau lỗi |
| --- | --- | --- |
| `new BankAccount("", "An", 0)` | `IllegalArgumentException` | Không tạo xong instance hợp lệ |
| `new BankAccount("VN004", "An", -1)` | `IllegalArgumentException` | Không tạo xong instance hợp lệ |
| `an.deposit(0)` | `IllegalArgumentException` | `an.balance` giữ nguyên |
| `an.withdraw(-10)` | `IllegalArgumentException` | `an.balance` giữ nguyên |
| `an.withdraw(900_000)` khi An có 850.000 | `IllegalArgumentException` | An vẫn còn 850.000 |
| `an.transferTo(an, 1)` | `IllegalArgumentException` | Không thay đổi |
| `an.transferTo(null, 1)` | `NullPointerException` | Không thay đổi |
| `an.deposit(Long.MAX_VALUE)` khi An có số dư dương | `ArithmeticException` | Số dư không đổi vì cộng tràn |

Ở các dòng kiểm tra minh họa, `an` được giả định là tham chiếu tới tài khoản đã tạo với số dư phù hợp. Đây là các **kịch bản kiểm thử**, không phải những lệnh được chạy trong hàm `main` phía trên.

Một kịch bản hữu ích khác: nếu tài khoản nhận có số dư gần `Long.MAX_VALUE`, `transferTo` có thể ném `ArithmeticException` khi tính số dư mới cho người nhận; trong luồng tuần tự đã viết, số dư cả hai đối tượng vẫn giữ nguyên vì chưa đến hai phép gán cuối cùng.

## 9. Các lỗi thường gặp khi mô hình hóa

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `public long balance` | Mọi nơi có thể đặt số dư âm hoặc bỏ qua quy tắc nghiệp vụ | Giữ `private`, đổi trạng thái qua phương thức |
| Dùng `double` để lưu số tiền | Sai số biểu diễn nhị phân có thể làm lệch phép tính tài chính | Dùng đơn vị nhỏ nhất bằng số nguyên hoặc `BigDecimal` theo yêu cầu |
| Viết `BankAccount other = an` rồi nghĩ đã có tài khoản mới | Hai biến chia sẻ đúng cùng một đối tượng và trạng thái | Phân biệt sao chép tham chiếu với tạo đối tượng |
| Đặt `balance` là `static` | Mọi tài khoản cùng nhìn thấy một trường số dư dùng chung | Dùng trường instance cho số dư mỗi tài khoản |
| Cập nhật số dư trước, kiểm tra sau | Yêu cầu sai có thể để lại trạng thái bị thay đổi | Kiểm tra điều kiện, tính toán có thể lỗi trước khi gán |
| Không kiểm tra `amount <= 0` | Nạp số âm thành rút tiền hoặc rút số âm thành nạp tiền | Kiểm tra số tiền dương ở đầu mỗi hành vi |
| Dựa vào `==` để xác định tài khoản theo số tài khoản | Hai instance khác nhau có thể có cùng định danh nghiệp vụ | Phân biệt định danh JVM và khóa nghiệp vụ |
| Cho rằng đối tượng đã được lưu sau khi gọi `new` | Khởi động lại chương trình thì trạng thái trong bộ nhớ biến mất | Tích hợp kho lưu trữ và giao dịch riêng khi cần |
| Cho rằng `transferTo` hiện tại an toàn đa luồng | Giao dịch đồng thời có thể đọc/ghi số dư không nhất quán | Thiết kế đồng bộ, điều phối giao dịch và lưu trữ đúng yêu cầu |

Một điểm thường bị bỏ qua: `private` chỉ giới hạn truy cập theo ngôn ngữ và hỗ trợ đóng gói; nó không thay thế xác thực, phân quyền hoặc bảo vệ dữ liệu của một ứng dụng ngân hàng thực.

## 10. Từ ví dụ đơn giản đến thiết kế lớn hơn

Trong mô hình này, một lớp đủ để hiểu các khái niệm cơ bản. Khi yêu cầu tăng, có thể cân nhắc phân trách nhiệm:

- `BankAccount` giữ dữ liệu và quy tắc cốt lõi của một tài khoản.
- Một dịch vụ giao dịch điều phối chuyển tiền giữa tài khoản, xác thực yêu cầu và dùng cơ chế giao dịch thích hợp.
- Một kho lưu trữ quản lý định danh duy nhất, đọc và ghi trạng thái bền vững.
- Một bản ghi giao dịch riêng có thể lưu thời điểm, số tiền, tài khoản gửi/nhận, mã giao dịch và kết quả để đối soát.

Đây là hướng mở rộng về sau, không phải yêu cầu bắt buộc để hiểu `class` và `object`. Trong bản demo, **đối tượng chỉ sống trong bộ nhớ** và tất cả thao tác tuần tự trong `main`; không nên dùng trực tiếp mô hình này để xử lý tiền thực hoặc kết luận rằng nó đủ an toàn cho hệ thống ngân hàng.

Điểm mạnh của thiết kế hiện tại là có thể quan sát rõ **một lớp tạo ra nhiều đối tượng, mỗi đối tượng có trạng thái riêng, và các đối tượng có thể hợp tác thông qua lời gọi phương thức**.

## 11. Tự luyện tập với cùng mô hình

**Bài 1 — Dự đoán trạng thái.** Tạo tài khoản C với số dư `100_000`, gọi `deposit(20_000)` rồi `withdraw(30_000)`. Số dư cuối là bao nhiêu? Nếu thêm lệnh `withdraw(100_000)`, điều gì xảy ra?

**Bài 2 — Phân biệt đối tượng và biến.** Cho `BankAccount alias = an;`. Sau khi gọi `alias.deposit(5_000)`, giá trị `an.balance()` thay đổi thế nào? Vì sao? Điều gì khác biệt nếu viết `new BankAccount(...)` để tạo một tài khoản khác?

**Bài 3 — Thay đổi yêu cầu.** Cho phép tài khoản có hạn mức rút mỗi lần. Nên đặt điều kiện đó trong mã gọi `main` hay trong phương thức `withdraw` của lớp? Nếu có thêm loại tiền tệ, việc chỉ dùng `long balance` có đủ biểu đạt không?

**Bài 4 — Tìm lỗi.** Một lập trình viên viết `balance -= amount` ở đầu `withdraw` rồi mới kiểm tra `amount > 0` và số dư có âm không. Hãy chỉ ra vì sao cách này có thể làm hỏng trạng thái và viết lại theo thứ tự kiểm tra trước, cập nhật sau.

Đối chiếu nhanh: bài 1 được `90_000` và lệnh rút 100.000 bị từ chối, số dư không đổi; bài 2 làm tăng số dư trên **cùng object** nên cả hai biến đều quan sát giá trị mới; bài 3 cần bảo vệ giới hạn nghiệp vụ ở nơi kiểm soát việc đổi trạng thái và một mô hình tiền tệ rõ đơn vị/loại tiền; bài 4 phải kiểm tra số tiền dương, đủ số dư rồi mới trừ.

Khi nhìn vào bất kỳ thiết kế lớp nào, hãy tự trả lời bốn câu hỏi: **Lớp mô tả điều gì? Mỗi đối tượng giữ trạng thái nào? Ai có quyền đổi trạng thái? Khi các đối tượng tương tác, quy tắc nào luôn phải đúng?** Ví dụ tài khoản ngân hàng chính là cách áp dụng bốn câu hỏi đó trong Java.
