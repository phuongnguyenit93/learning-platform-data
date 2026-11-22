# Chuỗi gọi super và truyền dữ liệu bắt buộc khi khởi tạo đối tượng Java

Khi tạo một đối tượng lớp con, Java phải chạy chuỗi constructor của các lớp cha. Mỗi tầng chịu trách nhiệm khởi tạo dữ liệu mà tầng đó sở hữu. Điều này đặc biệt hữu ích với abstract class: không thể tạo trực tiếp abstract class, nhưng constructor của nó vẫn chạy khi một lớp con cụ thể được tạo.

Bài này tập trung vào **super(...)**, **this(...)** và việc buộc lớp con truyền đủ dữ liệu cần thiết cho superclass. Chi tiết về thứ tự field initializer thuộc bài “Thứ tự khởi tạo thuộc tính, khối khởi tạo và constructor”; nguy cơ gọi phương thức override trong constructor được phân tích riêng ở bài chuyên biệt.

## 1. Theo dõi chuỗi constructor

~~~text
Object
  ↑
Entity (abstract class)
  ↑
Account
  ↑
PremiumAccount
~~~

Khi tạo `new PremiumAccount(...)`, mỗi constructor chỉ gọi superclass trực tiếp của mình. PremiumAccount gọi Account, Account gọi Entity, và chuỗi tiếp tục tới Object. Đây là nhiều lời gọi trên **một đối tượng**, không phải nhiều đối tượng cha lồng nhau.

Interface không có constructor và không thêm một tầng vào chuỗi này, dù lớp có thể implements nhiều interface.

## 2. Dữ liệu bắt buộc không được tự suy ra

Trong Java 17, nếu superclass chỉ khai báo `Base(String code)` thì không tồn tại constructor mặc định `Base()` được compiler tự sinh. Constructor subclass cuối chuỗi `this(...)` phải gọi một overload superclass hợp lệ và có thể truy cập bằng `super(code)`; compiler không tự điền dữ liệu còn thiếu.

Một chữ ký `Child(String code)` buộc caller cung cấp đối số ở mức cú pháp, còn constructor `Base` mới là nơi kiểm tra giá trị như null hoặc chuỗi rỗng. Khi chuẩn hóa đối số cho `super(...)`, có thể sử dụng tham số, hằng hoặc helper static; không dựa vào trường instance của đối tượng đang khởi tạo. Ví dụ đầy đủ ở phần tiếp theo cho thấy cách superclass sở hữu việc xác thực và subclass chỉ cung cấp dữ liệu.

## 3. Buộc lớp con truyền dữ liệu cho abstract class

Abstract class thường sở hữu các thuộc tính chung như mã định danh hoặc chủ sở hữu. Constructor có tham số buộc subclass chuyển dữ liệu ngay khi tạo đối tượng; superclass tự kiểm tra và thiết lập bất biến của nó.

Lưu ví dụ chạy được vào **Main.java**:

~~~java
import java.util.Objects;

public class Main {
    interface Auditable {
        String auditLabel();
    }

    static abstract class AccountRecord {
        private final String id;
        private final String owner;

        protected AccountRecord(String id, String owner) {
            this.id = requireNonBlank(id, "id");
            this.owner = requireNonBlank(owner, "owner");
            System.out.println("AccountRecord constructed");
        }

        private static String requireNonBlank(String value, String field) {
            Objects.requireNonNull(value, field + " must not be null");
            if (value.isBlank()) {
                throw new IllegalArgumentException(field + " must not be blank");
            }
            return value;
        }

        public final String id() {
            return id;
        }

        public final String owner() {
            return owner;
        }

        public abstract String summary();
    }

    static final class PremiumAccount extends AccountRecord
            implements Auditable {
        private final String tier;

        PremiumAccount(String id, String owner, String tier) {
            super(id, owner);
            this.tier = Objects.requireNonNull(tier, "tier");
            System.out.println("PremiumAccount constructed");
        }

        @Override
        public String summary() {
            return id() + " | " + owner() + " | " + tier;
        }

        @Override
        public String auditLabel() {
            return id() + "/" + tier;
        }
    }

    public static void main(String[] args) {
        PremiumAccount account =
                new PremiumAccount("P-100", "Linh", "GOLD");
        System.out.println(account.summary());
        System.out.println("Audit: " + account.auditLabel());

        try {
            new PremiumAccount("", "Linh", "GOLD");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac Main.java
java Main
~~~

Stdout:

~~~text
AccountRecord constructed
PremiumAccount constructed
P-100 | Linh | GOLD
Audit: P-100/GOLD
id must not be blank
~~~

Điều cần quan sát:

1. AccountRecord là abstract nhưng constructor của nó vẫn chạy qua `super(id, owner)`.
2. AccountRecord sở hữu và xác thực id, owner rồi lưu vào các trường private final. PremiumAccount không thể gán trực tiếp các trường ấy.
3. Auditable chỉ là hợp đồng hành vi; interface này không có constructor và không tham gia chuỗi super.
4. Chỉ khi constructor cha trả về, constructor PremiumAccount mới tiếp tục gán tier.
5. Nếu id rỗng, constructor cha ném exception và constructor PremiumAccount không đi đến dòng in thứ hai. Chữ ký constructor buộc cung cấp tham số; logic xác thực mới buộc giá trị thực sự hợp lệ.

Constructor nên hạn chế tác dụng phụ bên ngoài. Nếu subclass còn dữ liệu riêng có thể không hợp lệ, việc khởi tạo tổng thể vẫn có thể thất bại sau khi superclass đã chạy; vì vậy đừng gửi thông điệp, đăng ký callback hoặc công bố this trong lúc xây dựng.

## 4. Dùng this(...) để tránh lặp kiểm tra

`this(args)` gọi constructor khác trong cùng lớp. Một constructor chính có thể gom việc xác thực và gán trường, trong khi overload ngắn cung cấp giá trị mặc định:

~~~java
public class TicketDemo {
    static class Base {
        Base(String owner) {
            System.out.println("Base(" + owner + ")");
        }
    }

    static class Ticket extends Base {
        private final int quantity;

        Ticket(int quantity) {
            this("guest", quantity);
            System.out.println("Ticket shortcut");
        }

        Ticket(String owner, int quantity) {
            super(owner);
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            this.quantity = quantity;
            System.out.println("Ticket(" + owner + ", " + this.quantity + ")");
        }
    }

    public static void main(String[] args) {
        new Ticket(2);
    }
}
~~~

Stdout:

~~~text
Base(guest)
Ticket(guest, 2)
Ticket shortcut
~~~

Chuỗi là Ticket(int) → Ticket(String, int) → Base(String), rồi quay ngược về phần còn lại của Ticket(int). Đây vẫn là một đối tượng Ticket; initializer của lớp không chạy hai lần. Trong Java 17, lời gọi this(...) hoặc super(...) phải đứng đầu constructor và một constructor không thể đặt cả hai lời gọi trực tiếp ở đó.

## 5. Phân chia trách nhiệm qua nhiều tầng

~~~java
abstract class BaseEntity {
    private final String id;

    protected BaseEntity(String id) {
        this.id = java.util.Objects.requireNonNull(id, "id");
    }

    public final String id() {
        return id;
    }
}

abstract class OwnedEntity extends BaseEntity {
    private final String owner;

    protected OwnedEntity(String id, String owner) {
        super(id);
        this.owner = java.util.Objects.requireNonNull(owner, "owner");
    }

    public final String owner() {
        return owner;
    }
}

final class Document extends OwnedEntity {
    private final String title;

    Document(String id, String owner, String title) {
        super(id, owner);
        this.title = java.util.Objects.requireNonNull(title, "title");
    }

    public String description() {
        return id() + ": " + title + " (" + owner() + ")";
    }
}
~~~

Đây là các khai báo hợp lệ, không có main. Khi tạo Document, BaseEntity sở hữu id, OwnedEntity sở hữu owner, còn Document sở hữu title. Mỗi constructor kiểm tra dữ liệu do chính tầng đó quản lý. Nếu hệ thống cần quá nhiều lớp chỉ để chuyền vài trường, hãy cân nhắc composition thay vì thêm tầng kế thừa.

## 6. Các ranh giới của lời gọi constructor

Trong Java 17, các đối số của `super(...)` không được dựa vào trạng thái instance của đối tượng chưa khởi tạo. Có thể dùng tham số constructor hoặc helper static để chuẩn hóa/xác thực:

~~~java
class Parent {
    Parent(String id) {}
}

class Child extends Parent {
    Child(String input) {
        super(java.util.Objects.requireNonNull(input, "input").trim());
    }
}
~~~

Đoạn này hợp lệ. Nếu input là null, Objects.requireNonNull ném exception trước khi constructor cha được gọi. Không nên giấu logic phức tạp trong biểu thức đối số; chỉ dùng cách này khi giúp constructor rõ ràng hơn.

Nếu superclass constructor khai báo checked exception, subclass gọi `super(...)` phải khai báo ngoại lệ phù hợp trong `throws`; Java 17 không cho bao lời gọi `super(...)` bằng `try/catch` trong constructor con. Caller có thể bắt exception khi gọi `new Child(...)`. Cũng cần kiểm tra mức truy cập của constructor cha: `private` hoặc package-private có thể không gọi được từ vị trí subclass.

## 7. Lỗi thường gặp và tự kiểm tra

| Tình huống | Cách hiểu hoặc sửa |
| --- | --- |
| Compiler báo implicit super constructor không tồn tại | Viết `super(args)` đúng chữ ký hoặc khai báo constructor cha phù hợp. |
| Lớp con quên truyền id/owner bắt buộc | Đưa dữ liệu vào tham số constructor và gọi super(...) rõ ràng. |
| Các overload lặp logic xác thực | Chọn một constructor chính, cho overload khác gọi this(...). |
| Trường private của cha bị gán từ lớp con | Để superclass tự gán trường qua constructor của nó. |
| Constructor cha gọi hook của lớp con | Tránh logic đa hình khi subclass chưa sẵn sàng; xem bài về overridable method trong constructor. |
| Chỉ kiểm tra constructor nhưng không kiểm tra API cập nhật | Bảo vệ invariant cả sau khi tạo đối tượng. |

**Câu 1.** Abstract class chỉ có Parent(String id). Child() {} có hợp lệ không?  
**Đáp án:** Không, vì Java 17 ngầm chèn super() nhưng Parent() không tồn tại.

**Câu 2.** Một lớp implements ba interface có chạy ba chuỗi constructor không?  
**Đáp án:** Không. Interface không có constructor; chuỗi extends có một superclass trực tiếp ở mỗi tầng.

**Câu 3.** Nên xác thực id ở đâu nếu id thuộc trách nhiệm của abstract superclass?  
**Đáp án:** Trong constructor superclass nhận id, rồi lưu vào trường được đóng gói; subclass bắt buộc gọi super(id).