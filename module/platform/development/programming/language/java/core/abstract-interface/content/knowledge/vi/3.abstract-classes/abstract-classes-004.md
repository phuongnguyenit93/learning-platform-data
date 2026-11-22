# Thuộc tính và trạng thái dùng chung của các lớp con trong lớp trừu tượng (Java)

## 1. Mục tiêu và ý nghĩa của trạng thái kế thừa

Một lớp trừu tượng (`abstract class`) trong Java có thể định nghĩa các **instance field** mà mọi lớp con đều sử dụng, kèm constructor, quy tắc kiểm tra dữ liệu và phương thức xử lý thống nhất. Ví dụ, `SavingsAccount` và `CheckingAccount` là hai loại tài khoản; cả hai đều có chủ sở hữu và số dư, dù chính sách rút tiền khác nhau.

Sau bài này, bạn cần phân biệt được:

- **Chung về cấu trúc và hành vi:** lớp cha khai báo một lần các trường và phương thức, lớp con thừa hưởng chúng.
- **Riêng theo đối tượng:** mỗi `new SavingsAccount(...)` hay `new CheckingAccount(...)` có bản trạng thái instance của **chính đối tượng đó**. Một tài khoản tăng số dư không làm tăng số dư tài khoản khác.
- **Chung thực sự giữa các đối tượng:** trường `static` thuộc về lớp khai báo, không phải bản riêng của mỗi đối tượng.

`abstract` không cấm lớp cha sở hữu trường, khởi tạo dữ liệu hoặc viết phương thức cụ thể. Nó chỉ cấm tạo trực tiếp instance của lớp abstract và cho phép khai báo phương thức abstract. Một lớp con cụ thể sẽ hoàn thành phần hành vi còn thiếu.

## 2. Khi nào nên đặt thuộc tính ở lớp cha?

Đưa dữ liệu vào lớp cha khi dữ liệu đó tồn tại với **cùng ý nghĩa** trong mọi lớp con thuộc hệ phân cấp, và có thể chia sẻ cùng cách kiểm tra hoặc quản lý. Giữ dữ liệu riêng tại subclass nếu chỉ subclass đó cần.

| Dữ liệu | Nên đặt ở đâu? | Giải thích |
| --- | --- | --- |
| `owner` (chủ tài khoản) | `Account` | Tài khoản nào cũng có chủ sở hữu |
| `balanceCents` (số dư theo cent) | `Account` | Tất cả cùng chịu quy tắc cập nhật số dư |
| `freeWithdrawals` (số lượt rút miễn phí) | `SavingsAccount` | Chỉ tài khoản tiết kiệm dùng |
| Thống kê tổng tài khoản | Thành phần quản lý riêng, khi thích hợp | Không phải trạng thái thuộc một tài khoản đơn lẻ |

Quy tắc đơn giản: **thuộc tính nào lớp con nào cũng phải có**, có cùng hợp đồng và bất biến, mới là ứng viên tốt để đưa lên lớp cha. Nếu thêm một subclass mới mà trường đó không có nghĩa đối với nó, hãy xem lại cấu trúc kế thừa.

## 3. Ví dụ đầy đủ Java 17: lớp cha giữ invariant, lớp con thêm quy tắc riêng

Ví dụ dùng `long` để lưu **cent** thay vì dùng `double` biểu diễn tiền. Cả hai loại tài khoản kế thừa cùng `owner` và `balanceCents`; lớp cha chịu trách nhiệm ngăn số dư âm, lớp con tự quyết định chính sách rút.

Tạo tệp **`Demo.java`**:

```java
public class Demo {
    public static void main(String[] args) {
        SavingsAccount savings = new SavingsAccount("An", 10_000, 2);
        CheckingAccount checking = new CheckingAccount("Bình", 20_000);

        savings.deposit(5_000);
        savings.withdraw(2_000);
        checking.withdraw(2_000);

        Account account = savings; // Cùng đối tượng, tham chiếu kiểu cha.

        System.out.println("Savings: " + savings.balanceCents()
                + " cents; free withdrawals: " + savings.freeWithdrawals());
        System.out.println("Checking: " + checking.balanceCents() + " cents");
        System.out.println("Account reference: " + account.owner()
                + " / " + account.balanceCents() + " cents");
    }
}

abstract class Account {
    private final String owner;
    private long balanceCents;

    protected Account(String owner, long openingCents) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        if (openingCents < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.owner = owner;
        this.balanceCents = openingCents;
    }

    public final String owner() {
        return owner;
    }

    public final long balanceCents() {
        return balanceCents;
    }

    public final void deposit(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, cents);
    }

    // Thao tác cho lớp con sử dụng, luôn kiểm tra invariant.
    protected final void debit(long cents) {
        if (cents <= 0 || cents > balanceCents) {
            throw new IllegalArgumentException("invalid debit");
        }
        balanceCents -= cents;
    }

    public abstract void withdraw(long cents);
}

final class SavingsAccount extends Account {
    private int freeWithdrawals;

    SavingsAccount(String owner, long openingCents, int freeWithdrawals) {
        super(owner, openingCents);
        if (freeWithdrawals < 0) {
            throw new IllegalArgumentException("negative withdrawal quota");
        }
        this.freeWithdrawals = freeWithdrawals;
    }

    @Override
    public void withdraw(long cents) {
        if (freeWithdrawals == 0) {
            throw new IllegalStateException("no free withdrawals left");
        }
        debit(cents); // Chỉ giảm lượt sau khi trừ tiền thành công.
        freeWithdrawals--;
    }

    public int freeWithdrawals() {
        return freeWithdrawals;
    }
}

final class CheckingAccount extends Account {
    CheckingAccount(String owner, long openingCents) {
        super(owner, openingCents);
    }

    @Override
    public void withdraw(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("withdrawal must be positive");
        }
        debit(Math.addExact(cents, 100)); // Thu thêm phí 100 cents.
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac Demo.java
java Demo
```

Kết quả chính xác:

```text
Savings: 13000 cents; free withdrawals: 1
Checking: 17900 cents
Account reference: An / 13000 cents
```

**Cách đọc ví dụ:**

- `SavingsAccount` bắt đầu 10.000 cent, gửi 5.000, rút 2.000 ⇒ 13.000; hạn mức 2 lượt giảm còn 1.
- `CheckingAccount` bắt đầu 20.000, rút 2.000 và thêm phí 100 ⇒ 17.900. Hai đối tượng không sử dụng chung một trường số dư.
- `Account account = savings` không tạo tài khoản mới; nó là **tham chiếu khác đến cùng đối tượng** `savings`. Vì vậy `account.balanceCents()` nhìn thấy 13.000.
- Lớp `Account` quản lý trường `private long balanceCents`. Lớp con không gán trực tiếp vào nó, mà gọi `debit()`; logic kiểm tra luôn thống nhất.
- `owner` là trường `final` của mỗi instance; `freeWithdrawals` là trường riêng của subclass, không ép tài khoản thanh toán sở hữu nó.
- `withdraw()` được khai báo abstract ở cha và triển khai tại từng lớp con. Phương thức này là **phần hành vi thay đổi**, còn thao tác bảo vệ số dư là **phần hành vi dùng chung**.

Đây là ví dụ về thiết kế trạng thái và kế thừa. Hệ thống tiền tệ thực tế cần thêm các giao dịch nguyên tử, lưu trữ và kiểm soát đồng thời; mã trên không được xem là giải pháp giao dịch ngân hàng đầy đủ.

## 4. Vì sao ưu tiên trường `private` trong lớp abstract?

Lớp con thừa hưởng **phần dữ liệu nằm trong đối tượng**, ngay cả khi mã subclass không được truy cập trực tiếp một trường `private` của cha. Có thể cấp quyền **thực hiện hành vi** thông qua method, thay vì để lớp con sửa dữ liệu tùy ý.

| Modifier | Ai đọc/sửa trực tiếp được trường? | Khuyến nghị |
| --- | --- | --- |
| `private` | Mã trong lớp khai báo; subclass dùng API lớp cha | Nên dùng mặc định cho trạng thái mutable và bất biến cần bảo vệ |
| Không ghi modifier (*package-private*) | Mã trong cùng package | Dùng khi thật sự muốn chia sẻ trong package |
| `protected` | Cùng package và subclass theo quy tắc `protected` của Java | Dùng có cân nhắc; trường mutable dễ bị sửa sai |
| `public` | Mọi mã được phép truy cập lớp | Hiếm khi thích hợp với trường instance mutable |

**Không hiểu nhầm `protected` là “chỉ subclass mới truy cập”.** Các lớp trong cùng package cũng có quyền; subclass khác package còn chịu những hạn chế về biểu thức nhận truy cập. Cách đặt `private` field và `protected final` method thường dễ giữ invariant hơn.

Trong ví dụ:

- `private final String owner`: tham chiếu chỉ được gán trong quá trình khởi tạo; `String` là kiểu bất biến.
- `private long balanceCents`: dữ liệu có thể thay đổi, nhưng mọi đường cập nhật đều nằm dưới kiểm soát của `Account`.
- `public final void deposit(...)`: lớp con không được override để bỏ qua kiểm tra; `Math.addExact` bắt lỗi tràn `long` khi cộng.
- `protected final void debit(...)`: lớp con có thể yêu cầu thao tác trừ tiền hợp lệ nhưng không thay thuật toán kiểm tra.
- `public abstract void withdraw(...)`: lớp con cụ thể phải cung cấp triển khai, nếu không thừa hưởng được một triển khai cụ thể phù hợp.

**Lưu ý về `final`:** `final` của trường tham chiếu chỉ cấm gán lại tham chiếu, không đóng băng object được tham chiếu. Ví dụ `final List<String> tags` vẫn cho phép `tags.add("new")` khi danh sách là mutable. Với trường chứa `List`, `Map` hoặc object mutable trong lớp cha, cần cân nhắc `List.copyOf(...)`, defensive copy và phương thức cập nhật có kiểm soát. Tránh trả trực tiếp cấu trúc dữ liệu mutable nội bộ qua getter.

## 5. Constructor và thời điểm khởi tạo trạng thái

Constructor của lớp cha trừu tượng chạy trong quá trình tạo đối tượng lớp con, thường qua `super(...)`, để thiết lập phần trạng thái mà lớp cha sở hữu. Trường instance bắt đầu từ giá trị mặc định; phần khởi tạo và constructor của lớp cha hoàn tất trước khi các initializer và thân constructor của lớp con hoàn tất.

Tránh gọi phương thức instance có thể override từ constructor lớp cha: Java vẫn dispatch đến lớp con khi các trường của lớp con có thể chưa được gán giá trị mong muốn. Khi thiết kế lớp giữ invariant, constructor nên kiểm tra và gán dữ liệu do chính lớp đó quản lý; ví dụ và quy tắc constructor chi tiết được tập trung trong bài về constructor.

## 6. Field hiding: trường **không** được override như method

Nếu subclass khai báo trường trùng tên với trường ở cha, trường mới **che khuất** (*hide*) tên trường cũ; nó không thay thế trường cũ. Hai trường vẫn tồn tại. Khi truy cập trường, Java xét **kiểu khai báo của biểu thức tham chiếu**; khi gọi instance method được override, Java dispatch theo **kiểu thực tế của đối tượng**.

Lưu mã độc lập sau thành **`FieldHidingDemo.java`**:

```java
public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent child = new Child();

        System.out.println(child.label);
        System.out.println(child.getLabel());
    }
}

class Parent {
    String label = "parent";

    String getLabel() {
        return label;
    }
}

class Child extends Parent {
    String label = "child";

    @Override
    String getLabel() {
        return label;
    }
}
```

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

Kết quả:

```text
parent
child
```

`child.label` chọn trường ở `Parent` vì biến `child` có kiểu `Parent`. `child.getLabel()` gọi phương thức override ở `Child` vì đối tượng thực tế là `Child`.

Không nên viết hai trường có cùng ý nghĩa ở lớp cha và lớp con để mong “override trạng thái”. Dù trường cha là `private` và mã con được phép có trường trùng tên riêng, cách làm đó vẫn tạo hai nơi lưu dữ liệu có thể mâu thuẫn. Định nghĩa một trường tại nơi sở hữu hợp lý, rồi mở rộng hành vi bằng method.

## 7. Trường `static` không đại diện cho trạng thái riêng của mỗi đối tượng

Instance field thông thường thuộc từng đối tượng; hai tài khoản được tạo riêng có hai số dư riêng. Ngược lại, field `static` thuộc lớp khai báo và được chia sẻ giữa các instance. Vì vậy, không dùng `static` cho số dư hoặc trạng thái nghiệp vụ riêng của từng đối tượng.

Phương thức `static` cũng không tham gia dynamic dispatch như instance method, còn trạng thái `static` có thể thay đổi cần được xem xét về đồng thời. Các quy tắc chi tiết của `static`, `final` và `private`, bao gồm hiding và đóng gói, được tập trung trong bài về thành viên và modifier.

## 8. Bảo vệ bất biến chung và khả năng mở rộng

**Invariant** là điều kiện luôn phải đúng đối với trạng thái hợp lệ của đối tượng. Trong `Account`, quy tắc `balanceCents >= 0` được bảo vệ bằng constructor, `deposit()` và `debit()`.

Thiết kế đáng ưu tiên:

- Constructor lớp cha chặn dữ liệu không hợp lệ **ngay lúc tạo object**.
- Phương thức cập nhật kiểm tra đầu vào trước khi sửa trạng thái.
- Lớp con gọi hành vi được lớp cha kiểm soát, tránh tự gán vào mutable field của cha.
- Nếu sửa nhiều trường, xác định thứ tự để không tạo trạng thái dở dang khi có exception. Ví dụ `SavingsAccount` chỉ giảm `freeWithdrawals` sau khi `debit()` thành công.
- Nếu yêu cầu mới làm thay đổi invariant cơ bản (chẳng hạn tài khoản được thấu chi), cần thiết kế lại hợp đồng của lớp cha cho nhất quán, không tạo lối tắt sửa dữ liệu ở subclass.

Với đối tượng mutable dùng bởi nhiều thread, `private`, `final` trên method hoặc getter **không tự bảo đảm thread safety**. Hai luồng có thể đọc cùng giá trị cũ và ghi đè nhau. `volatile` giúp các luồng nhìn thấy cập nhật của trường được đánh dấu, nhưng phép tăng/giảm dạng đọc–tính–ghi không tự trở thành nguyên tử. Tùy mô hình sử dụng, cần đồng bộ hóa, khóa hoặc cách cập nhật nguyên tử phù hợp. Đây là mối quan tâm bổ sung khi chia sẻ object; bản chất kế thừa field không tạo cơ chế đồng bộ.

## 9. Kế thừa, interface và composition

- Dùng **abstract class** khi các subclass thật sự có quan hệ *is-a*, chia sẻ cả **trạng thái instance**, invariant và hành vi, trong khi vẫn có những điểm mở rộng cần subclass triển khai.
- Dùng **interface** để mô tả hợp đồng chung, đặc biệt khi các lớp không cùng hệ phân cấp hoặc cần triển khai nhiều hợp đồng. Một interface Java không có instance field để mỗi implementation kế thừa; trường khai báo trong interface ngầm là `public static final`.
- Dùng **composition** khi phần dùng chung là một khả năng/thành phần có thể lắp ghép, không phải quan hệ is-a ổn định. Ví dụ `FeePolicy` có thể là object được `Account` giữ để thay đổi cách tính phí mà không phải tạo một subclass cho mọi tổ hợp chính sách.

Không nên đẩy một thuộc tính lên lớp cha chỉ vì “các lớp đang trùng code”. Hỏi xem thuộc tính đó có mang cùng ý nghĩa, vòng đời, invariant trong tất cả subclass hay không.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Khai báo `static` cho số dư của từng object | Tất cả instance cùng thấy một số dư | Dùng instance field |
| Để `protected` mutable field cho mọi subclass sửa | Lớp con có thể phá invariant | Giữ `private`, mở method kiểm soát |
| Đưa field chỉ một subclass cần lên cha | Những subclass khác gánh trạng thái vô nghĩa | Giữ field riêng ở subclass |
| Che khuất field bằng khai báo trùng tên | Có hai trường độc lập dễ lệch dữ liệu | Một nơi lưu field; dùng method để tùy biến |
| Constructor cha gọi phương thức override | Đọc trạng thái subclass chưa khởi tạo | Không dispatch method mở trong constructor |
| Trả trực tiếp bộ sưu tập mutable qua getter | Mã ngoài sửa trạng thái bỏ qua kiểm tra | Defensive copy, API cập nhật hợp lệ |
| Nghĩ `final` tham chiếu làm object bất biến | Object mutable vẫn bị thay đổi | Bảo vệ object được tham chiếu |
| Chia sẻ object mutable qua nhiều thread không đồng bộ | Lost update, dữ liệu sai | Cơ chế đồng bộ phù hợp với nghiệp vụ |

## 11. Tự kiểm tra và áp dụng

**Bài tập:** Thêm `StudentAccount`, mỗi đối tượng có `schoolId` và một hạn mức giao dịch miễn phí.

1. `schoolId` nên ở đâu? **`StudentAccount`**, vì các tài khoản khác không có mã trường học.
2. `balanceCents` nên ở đâu? **`Account`**, vì đây là dữ liệu và invariant chung.
3. Subclass có nên sửa trực tiếp `balanceCents`? **Không**; gọi hành vi cập nhật được lớp cha bảo vệ.
4. Hai object `StudentAccount` có dùng chung một số dư không? **Không**, trừ khi bạn cố tình thiết kế nguồn trạng thái chia sẻ khác; instance field thông thường thuộc từng object.
5. Nếu `Account a = new StudentAccount(...)` thì `a.owner()` trả trạng thái từ đâu? **Từ chính object `StudentAccount`** mà `a` đang trỏ tới, nơi lưu phần `Account` được kế thừa.
6. Nếu tính phí phụ thuộc nhiều chính sách thay đổi độc lập với loại tài khoản, nên dùng gì? **Cân nhắc composition**, ví dụ một `FeePolicy` gắn với tài khoản.

**Ghi nhớ:** Lớp trừu tượng là nơi định nghĩa **thuộc tính chung và cơ chế bảo vệ trạng thái chung**; mỗi đối tượng lớp con vẫn sở hữu **bản trạng thái instance riêng**. Hãy đặt field theo đúng ý nghĩa nghiệp vụ, ưu tiên đóng gói `private`, khởi tạo qua `super(...)` và cho phép subclass tùy biến **hành vi**, không tùy ý phá invariant.
