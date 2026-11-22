# Triển khai equals và hashCode nhất quán giữa các kiểu con trong Java

Khi một class có subtype, equality phải có một định nghĩa thống nhất cho cả hierarchy. Lỗi thường gặp là lớp cha chấp nhận một object lớp con vì các trường chung giống nhau, trong khi lớp con so sánh thêm trường riêng và từ chối object lớp cha. Khi đó equals mất tính đối xứng; nếu hashCode cũng dựa trên các tập trường khác nhau, hợp đồng hash có thể bị phá vỡ.

## 1. Hợp đồng cần giữ

| Tính chất | Câu hỏi kiểm tra |
| --- | --- |
| Phản xạ | x.equals(x) có true không? |
| Đối xứng | x.equals(y) và y.equals(x) có cùng kết quả không? |
| Bắc cầu | nếu x bằng y và y bằng z thì x có bằng z không? |
| Nhất quán | khi dữ liệu liên quan không đổi, kết quả có ổn định không? |
| Null | x.equals(null) có false không? |
| Hash | nếu x.equals(y) là true, hai hash code có bằng nhau không? |

Hai object không bằng nhau vẫn có thể trùng hash code. Điều bắt buộc chỉ là equal implies same hash. Compiler không thể chứng minh các tính chất này chỉ từ việc code biên dịch.

Mỗi hierarchy cần quyết định trước: object khác lớp cụ thể có thể bằng nhau không, subtype có được thêm trường vào equality không, và ai được quyền thay đổi chính sách khi thêm subtype. Đừng bắt đầu bằng cách chọn instanceof hoặc getClass() một cách máy móc; hãy bắt đầu bằng ý nghĩa identity/value trong miền nghiệp vụ.

## 2. Lỗi kinh điển: lớp cha dùng instanceof, lớp con thêm điều kiện

~~~java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Point point
                && x == point.x && y == point.y;
    }

    @Override
    public int hashCode() {
        return 31 * x + y;
    }
}

final class ColorPoint extends Point {
    final String color;

    ColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof ColorPoint point
                && super.equals(point)
                && color.equals(point.color);
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + color.hashCode();
    }
}

public class BrokenEqualityDemo {
    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point colored = new ColorPoint(1, 2, "blue");
        System.out.println(plain.equals(colored));
        System.out.println(colored.equals(plain));
    }
}
~~~

Kết quả:

~~~text
true
false
~~~

Point chấp nhận ColorPoint vì tọa độ trùng; ColorPoint từ chối Point vì thiếu màu. Hai chiều cho kết quả khác nhau. Point còn có thể xem hai object là equal trong khi ColorPoint tạo hash code dựa trên màu, dẫn đến vi phạm quy tắc equal implies same hash. Việc cả hai method đều có @Override không bảo đảm hợp đồng đúng.

## 3. Chọn ranh giới equality cho cả hierarchy

**Mô hình A: chỉ bằng nhau khi cùng lớp runtime.** Phù hợp khi mỗi subtype mang dữ liệu hoặc ý nghĩa khác nhau. Dùng getClass() để từ chối subtype khác, rồi so sánh trường chung và trường riêng. Nếu muốn khóa chính sách cho cả cây, lớp cha có thể định nghĩa final equals/hashCode và gọi hook protected để subtype so sánh chi tiết.

**Mô hình B: equality theo identity chung xuyên subtype.** Phù hợp khi các subtype là những cách nhìn khác nhau của cùng thực thể và có ID toàn cục, bất biến. Lớp cha có thể dùng instanceof với ID chung, đồng thời khai báo final equals/hashCode để subtype không thêm điều kiện riêng. Chỉ chọn mô hình này nếu hai subtype cùng ID thực sự phải đại diện cùng identity nghiệp vụ.

## 4. Ví dụ cho hai mô hình

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualitySubtypesDemo {
    static abstract class Notice {
        private final String code;

        Notice(String code) {
            this.code = Objects.requireNonNull(code);
        }

        protected abstract boolean sameDetails(Notice other);
        protected abstract int detailsHash();

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            Notice other = (Notice) obj;
            return code.equals(other.code) && sameDetails(other);
        }

        @Override
        public final int hashCode() {
            return Objects.hash(getClass(), code, detailsHash());
        }
    }

    static final class EmailNotice extends Notice {
        private final String email;

        EmailNotice(String code, String email) {
            super(code);
            this.email = Objects.requireNonNull(email);
        }

        @Override
        protected boolean sameDetails(Notice other) {
            return email.equals(((EmailNotice) other).email);
        }

        @Override
        protected int detailsHash() {
            return email.hashCode();
        }
    }

    static final class SmsNotice extends Notice {
        private final String phone;

        SmsNotice(String code, String phone) {
            super(code);
            this.phone = Objects.requireNonNull(phone);
        }

        @Override
        protected boolean sameDetails(Notice other) {
            return phone.equals(((SmsNotice) other).phone);
        }

        @Override
        protected int detailsHash() {
            return phone.hashCode();
        }
    }

    static abstract class GlobalEntity {
        private final String id;

        GlobalEntity(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public final boolean equals(Object obj) {
            return this == obj
                    || (obj instanceof GlobalEntity other && id.equals(other.id));
        }

        @Override
        public final int hashCode() {
            return id.hashCode();
        }
    }

    static final class UserEntity extends GlobalEntity {
        UserEntity(String id) { super(id); }
    }

    static final class AdminEntity extends GlobalEntity {
        AdminEntity(String id) { super(id); }
    }

    public static void main(String[] args) {
        Notice a = new EmailNotice("N1", "a@example.org");
        Notice b = new EmailNotice("N1", "a@example.org");
        Notice c = new EmailNotice("N1", "b@example.org");
        Notice d = new SmsNotice("N1", "12345");

        Set<Notice> notices = new HashSet<>();
        notices.add(a);
        notices.add(b);
        notices.add(c);
        notices.add(d);

        HashMap<Notice, String> messages = new HashMap<>();
        messages.put(a, "sent");

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
        System.out.println(a.equals(d));
        System.out.println(notices.size());
        System.out.println(messages.get(b));

        GlobalEntity user = new UserEntity("G1");
        GlobalEntity admin = new AdminEntity("G1");
        System.out.println(user.equals(admin));
        System.out.println(user.hashCode() == admin.hashCode());
    }
}
~~~

Kết quả:

~~~text
true
true
false
false
3
sent
true
true
~~~

Notice dùng mô hình A: chỉ cùng loại và cùng dữ liệu mới bằng nhau. GlobalEntity dùng mô hình B: UserEntity và AdminEntity cùng ID được coi là cùng identity. Hai lựa chọn này đều có thể đúng nếu phù hợp nghiệp vụ; không được trộn chúng trong một hierarchy. Trong mô hình A, phép cast ở sameDetails an toàn vì equals đã xác nhận đúng cùng lớp runtime trước khi gọi hook.

## 5. instanceof, getClass và canEqual trả lời câu hỏi khác nhau

- other instanceof Parent chấp nhận Parent và subtype.
- getClass() == other.getClass() yêu cầu hai object có đúng cùng lớp runtime.
- final equals/hashCode ở base ngăn subtype thay đổi riêng chính sách equality.
- canEqual là một mẫu để hai phía xác nhận có thể so sánh với nhau; chỉ có canEqual không tự chứng minh tính bắc cầu hoặc hashCode đúng.

Kiểm tra lớp cụ thể thường phù hợp khi subtype mang trường equality riêng. Tuy nhiên, nó có thể không phù hợp với ORM proxy hoặc entity có lớp runtime do framework tạo. ID được cấp sau khi persist cũng làm equality khó hơn vì giá trị hash có thể đổi trong vòng đời object. Với entity, hãy tuân theo semantics và lifecycle của framework cụ thể.

Record là final và tự định nghĩa equals/hashCode theo components, phù hợp với nhiều value object. Nếu component là mảng, equality được sinh không tự động trở thành deep equality vì array thường so sánh theo tham chiếu. Sealed hierarchy giới hạn subtype được phép nhưng không tự chọn chính sách equality thay cho bạn.

## 6. Các kiểu dữ liệu và trạng thái dễ tạo lỗi

- **Trường mutable:** nếu một trường dùng cho equals/hashCode thay đổi sau khi object được đưa vào HashSet hoặc dùng làm key của HashMap, thao tác tìm kiếm có thể thất bại. Ưu tiên khóa bất biến.
- **Mảng:** Objects.equals(arrayA, arrayB) không so sánh phần tử của mảng; dùng Arrays.equals hoặc Arrays.deepEquals tùy cấu trúc, và cặp hash tương ứng.
- **BigDecimal:** equals phân biệt scale; 2.0 và 2.00 có thể không bằng nhau dù compareTo trả về 0. Chọn rõ semantics trước khi thiết kế hash.
- **Số thực:** NaN và +0.0/-0.0 cần quy tắc so sánh tương thích với hash; dùng cách xử lý nhất quán như Double.compare và Double.hashCode khi phù hợp.
- **Subclass có field mới:** nếu base equality coi mọi subtype có cùng ID là equal, subtype không được tự thêm trường vào equality mà vẫn giữ quy tắc chung đó.

Một interface có thể được dùng làm kiểu tham chiếu khi gọi equals; implementation vẫn được dispatch theo lớp runtime. Chỉ cùng implement một interface hoặc cùng trả về id() không có nghĩa hai implementation phải bằng nhau. equals(Customer) cũng không thay thế equals(Object); dùng @Override để phát hiện lỗi chữ ký.

## 7. Kiểm thử cả hierarchy

Dùng ma trận gồm: cùng object, object cùng dữ liệu cùng subtype, khác dữ liệu cùng subtype, khác subtype cùng key, khác subtype khác key và null. Với từng cặp và bộ ba thích hợp, kiểm tra phản xạ, đối xứng, bắc cầu, nhất quán và quy tắc equal implies same hash. Sau đó kiểm tra HashSet không thêm bản sao equal và HashMap.get tìm được value khi dùng key khác nhưng equal với key ban đầu.

Đừng chỉ kiểm tra parent.equals(child); luôn thử cả child.equals(parent). Với nhiều tầng kế thừa, kiểm tra mọi cặp subtype liên quan. Nếu dùng assert trong Java, nhớ rằng assertion mặc định tắt nếu không chạy với -ea; test framework có thể giúp thực thi các kiểm tra ổn định hơn.

Trước khi code, hãy trả lời: object có semantics identity hay value; subtype khác nhau có được bằng nhau không; trường nào tham gia equality; ai được quyền thay đổi chính sách; và framework có proxy hoặc ID được cấp trễ không. Chính sách rõ ràng quan trọng hơn việc chọn riêng instanceof hoặc getClass().
