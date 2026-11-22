# Lớp `final` hoặc phương thức `equals() final` để giới hạn thay đổi hợp đồng

## 1. Vấn đề khi `equals` gặp kế thừa

`Object.equals(Object)` biểu diễn quan hệ bằng nhau logic, không chỉ so sánh địa chỉ bộ nhớ. Hợp đồng yêu cầu **phản xạ** (`a.equals(a)`), **đối xứng** (`a.equals(b) == b.equals(a)`), **bắc cầu** (nếu `a=b`, `b=c` thì `a=c`), **nhất quán** khi dữ liệu so sánh không đổi và `a.equals(null) == false`. Ngoài ra, nếu `a.equals(b)` đúng thì `a.hashCode() == b.hashCode()` bắt buộc đúng. Hai hash bằng nhau **không** bắt buộc hai đối tượng bằng nhau.

Khi lớp cha định nghĩa `equals` bằng một trường như `id` nhưng lớp con tự thêm điều kiện `department`, hai lời gọi `parent.equals(child)` và `child.equals(parent)` có thể khác nhau. Ví dụ lớp cha chấp nhận mọi đối tượng cùng `id`, còn lớp con chỉ chấp nhận chính kiểu lớp con và cùng `department`. Kết quả là **đối xứng bị phá vỡ**; nhiều đối tượng còn có thể làm hỏng bắc cầu.

`HashSet` và `HashMap` phụ thuộc hợp đồng `equals`/`hashCode` để loại trùng, tra cứu và xóa. Nếu hợp đồng bị phá, có thể không tìm thấy khóa tương đương hoặc tập hợp chứa các phần tử “trùng” một cách khó dự đoán. Hai chiến lược ngăn lớp con tùy ý thay đổi quan hệ bằng nhau là **khóa toàn bộ kiểu với `final class`** và **khóa riêng phép bằng nhau bằng `final equals(Object)`**.

## 2. `final class`: không cho kế thừa

Khi khai báo lớp là `final`, Java cấm lớp khác `extends` nó. Không có lớp con để override `equals`, thay đổi `hashCode` hay thêm phần danh tính mà lớp gốc chưa dự liệu. Đây là lựa chọn phù hợp với **value object**, ID, khóa bộ nhớ đệm và kiểu dữ liệu không cần hệ phân cấp con.

Ví dụ trong tệp `AccountId.java`:

```java
import java.util.Objects;

public final class AccountId {
    private final String value;

    public AccountId(String value) {
        this.value = Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof AccountId that
                    && value.equals(that.value));
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
```

Lớp này biên dịch được trên Java 17+ bằng `javac --release 17 AccountId.java`. Hai `AccountId` có cùng `value` sẽ bằng nhau và có cùng hash. Trường `value` là `String` bất biến và được khai báo `final`; constructor từ chối `null`. `final class` cấm `class ChildId extends AccountId` ở thời điểm biên dịch.

Vì bản thân lớp đã không thể bị kế thừa, thường không cần đánh dấu từng `equals` và `hashCode` là `final` để chống override. Nhưng **`final class` không tự làm cho logic đúng**: lập trình viên vẫn có thể viết `equals` bất đối xứng hoặc hash không tương thích, hoặc dùng một trường mutable trong phép so sánh.

Record trong Java 17 cũng là kiểu **ngầm định `final`**. Chẳng hạn `record AccountId(String value) {}` sinh `equals`/`hashCode` từ thành phần `value`. Tuy nhiên, record chứa đối tượng mutable không tự có bất biến sâu; thành phần mảng được so sánh theo tham chiếu chứ không tự so sánh từng phần tử.

## 3. `final equals(Object)`: vẫn cho subclass, giữ chung một định nghĩa

Khi cần lớp con để mở rộng hành vi nhưng mọi lớp phải dùng chung danh tính, lớp cha có thể khóa `equals(Object)`:

```java
import java.util.Objects;

public class Member {
    private final String memberId;

    protected Member(String memberId) {
        this.memberId = Objects.requireNonNull(memberId);
    }

    @Override
    public final boolean equals(Object other) {
        return this == other
                || (other instanceof Member that
                    && memberId.equals(that.memberId));
    }

    @Override
    public final int hashCode() {
        return memberId.hashCode();
    }
}
```

Đây là lớp minh họa độc lập trong `Member.java`. `Member` không `final`, nên subclass được phép thêm trường và phương thức; nhưng **không được override** `equals(Object)` hoặc `hashCode()`. Mọi `Member` có cùng `memberId` đều bằng nhau, kể cả khi chúng thuộc hai lớp con khác nhau. Quy tắc này **chỉ đúng khi miền nghiệp vụ thực sự xem cùng ID là cùng danh tính xuyên mọi subtype**.

### Vì sao cần quan tâm `hashCode()`?

Khóa `equals` nhưng cho phép subclass override `hashCode` chưa đủ an toàn. Lớp con có thể tạo hash theo `memberId` *và* `level`, trong khi `equals` vẫn chỉ nhìn `memberId`. Khi đó hai đối tượng bằng nhau có hash khác nhau. Vì vậy, nếu lớp cha sở hữu một chính sách equality thống nhất, thường nên khai báo **cả `equals(Object) final` và `hashCode() final`**, rồi dùng cùng bộ thuộc tính bất biến để triển khai.

Nếu lớp con viết:

```java
// Cố ý không biên dịch: Member.equals(Object) là final.
class BadMember extends Member {
    BadMember(String id) {
        super(id);
    }

    @Override
    public boolean equals(Object other) {
        return false;
    }
}
```

thì trình biên dịch từ chối override. Lưu ý `equals(BadMember)` chỉ là một **overload**, không phải override `equals(Object)`. Collection trong Java dựa trên chữ ký `equals(Object)`; đừng dùng overload để thử thay đổi khái niệm bằng nhau vì kết quả lời gọi có thể phụ thuộc kiểu tĩnh của tham số.

## 4. Demo Java 17+ chạy được

Tạo `FinalEqualityDemo.java`. Hai ví dụ dùng hai cách khóa khác nhau; output cho thấy chúng hoạt động với `HashSet` như thế nào.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class FinalEqualityDemo {
    static final class AccountKey {
        private final String id;

        AccountKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof AccountKey that
                        && id.equals(that.id));
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    static class Member {
        private final String id;

        protected Member(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public final boolean equals(Object other) {
            return this == other
                    || (other instanceof Member that
                        && id.equals(that.id));
        }

        @Override
        public final int hashCode() {
            return id.hashCode();
        }
    }

    static final class BasicMember extends Member {
        BasicMember(String id) {
            super(id);
        }
    }

    static final class PremiumMember extends Member {
        private final int rewardPoints;

        PremiumMember(String id, int rewardPoints) {
            super(id);
            this.rewardPoints = rewardPoints;
        }
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("A-7");
        AccountKey b = new AccountKey("A-7");
        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        System.out.println("key equals: " + a.equals(b));
        System.out.println("key set size: " + keys.size());

        Member basic = new BasicMember("M-9");
        Member premium = new PremiumMember("M-9", 100);
        Set<Member> members = new HashSet<>();
        members.add(basic);
        members.add(premium);
        System.out.println("member forward: " + basic.equals(premium));
        System.out.println("member reverse: " + premium.equals(basic));
        System.out.println("member hash match: "
                + (basic.hashCode() == premium.hashCode()));
        System.out.println("member set size: " + members.size());
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 FinalEqualityDemo.java
java FinalEqualityDemo
```

Stdout:

```text
key equals: true
key set size: 1
member forward: true
member reverse: true
member hash match: true
member set size: 1
```

Hai khóa `AccountKey` bằng nhau nên `HashSet` lưu một phần tử. `BasicMember` và `PremiumMember` cũng bằng nhau hai chiều vì `Member` áp dụng một chính sách khóa chung. Thuộc tính `rewardPoints` **không tham gia danh tính**, dù là trường của `PremiumMember`; đó là một lựa chọn miền dữ liệu, không phải một thuộc tính mà `final` tự suy ra.

Nếu nghiệp vụ đòi hỏi một `PremiumMember` phải khác `BasicMember` ngay cả khi ID giống nhau, việc khóa `equals` ở cha theo mỗi `id` là **không phù hợp**. Không nên cố sửa hậu quả ở `HashSet`: phải điều chỉnh mô hình danh tính.

## 5. `instanceof` hay `getClass()` bên trong phương thức `final equals`?

Hai lựa chọn kiểm tra kiểu dẫn đến ý nghĩa khác nhau:

| Kiểm tra | Cách hiểu về equality | Lưu ý |
| --- | --- | --- |
| `other instanceof Member` | Một instance lớp cha có thể bằng instance lớp con nếu khóa chung bằng nhau; hai subtype khác nhau cũng có thể bằng nhau | Chỉ dùng nếu ID có cùng ý nghĩa xuyên các subtype |
| `other != null && getClass() == other.getClass()` | Chỉ instance cùng **lớp runtime chính xác** mới bằng nhau | Subtype khác nhau không bằng nhau; trường riêng của subtype vẫn không được thêm vào `equals` đã khóa |

Ví dụ, với `final equals` dựa vào `getClass()`, `Member` sẽ không bằng `PremiumMember`. Nhưng hai `PremiumMember` cùng ID và khác `rewardPoints` vẫn có thể bằng nhau vì phương thức ở cha chỉ thấy `id`. Lớp con không thể override để bổ sung điểm thưởng vào equality.

Một số framework tạo proxy bằng subclass làm lớp runtime khác kiểu miền gốc. Do đó, chọn `getClass()` cần cân nhắc kiến trúc proxy và quy tắc identity thực tế. Với lớp đã `final`, `instanceof` hay `getClass` thường không tạo ra khác biệt do subclass là không thể.

## 6. So sánh hai chiến lược

| Tiêu chí | `final class` | `final equals` trên lớp có thể kế thừa |
| --- | --- | --- |
| Có subclass không? | Không | Có |
| Subclass thay đổi `equals` được không? | Không có subclass | Không thể override |
| Subclass thêm dữ liệu/hành vi? | Không | Có |
| Subclass định nghĩa lại identity riêng? | Không áp dụng | Không, trừ khi thay thiết kế lớp cha |
| `hashCode` có bị override không? | Không có subclass | Cần khai báo `final hashCode()` để cấm override |
| Chặn mọi lỗi hợp đồng? | Không | Không |
| Phù hợp nhất | Value object, key, identifier độc lập | Phân cấp chia sẻ chung một định nghĩa identity |

`final class` hạn chế mọi kế thừa, mạnh hơn nhưng cũng giảm khả năng mở rộng kiểu. `final equals` hẹp hơn: tiếp tục cho phép polymorphism nhưng khóa một chính sách cụ thể. Trong trường hợp thứ hai, cần bảo đảm không có phương thức còn override được làm thay đổi dữ liệu quyết định identity theo thời gian.

## 7. Những lỗi suy luận phổ biến

**Cho rằng final đồng nghĩa bất biến.** Một lớp `final` vẫn có thể chứa `List` hoặc mảng mutable; một trường `final` chỉ cố định tham chiếu, không cố định nội dung. Nếu hash phụ thuộc nội dung có thể sửa, đối tượng làm khóa `HashMap` có thể mất khả năng được tìm lại sau khi thay đổi.

**Khóa equality quá sớm.** Nếu lớp con cần dùng thuộc tính riêng trong tiêu chí danh tính, `final equals` ở cha sẽ ngăn điều đó. Khi ấy nên định nghĩa lại khóa chung sao cho chứa đầy đủ danh tính ngay khi khởi tạo, hoặc tách thành các value type `final` riêng. Có thể dùng composition/interface để chia sẻ hành vi mà không trói equality vào cây kế thừa.

**Chỉ khóa equals, quên hashCode.** Lớp con có thể override hash dẫn đến hai đối tượng bằng nhau nhưng khác mã hash. Ngay cả không có override, mọi thay đổi trong phương thức gốc phải giữ quan hệ bắt buộc giữa hai phương thức.

**Giả định tất cả subclass phải khác nhau.** Một `PremiumMember` và một `BasicMember` có thể là cùng thành viên với một ID; loại thành viên hoặc điểm thưởng là trạng thái, không hẳn danh tính. Ngược lại, nếu hai kiểu đại diện cho hai loại thực thể khác nhau, cùng ID có thể chưa đủ. Quyết định bằng nhau phải dựa vào miền dữ liệu.

**Mọi framework đều chấp nhận final.** Một số thư viện ORM/proxy cần subclass hoặc override phương thức để cung cấp chức năng; `final class`/`final method` có thể ảnh hưởng. Không chọn công thức equality cho entity dựa trên ví dụ value object mà thiếu phân tích identity và cơ chế của framework.

**Dùng `sealed` như thay thế tự động.** `sealed class` chỉ giới hạn **những subclass nào được phép kế thừa**; chúng vẫn có thể override `equals` nếu phương thức không `final`. Sealed giúp kiểm soát phạm vi kế thừa, nhưng không tự bảo đảm tính đối xứng hay bắc cầu.

## 8. Kiểm thử cần có trước khi khóa hợp đồng

Dùng ít nhất ba đối tượng đại diện cho cùng khóa, khác khóa và các subtype; kiểm tra:

1. `a.equals(a)` đúng; `a.equals(null)` sai.
2. `a.equals(b)` và `b.equals(a)` giống nhau, đặc biệt với cặp cha–con.
3. Nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)`.
4. Nếu `a.equals(b)` thì `a.hashCode()==b.hashCode()`. **Không** kiểm tra chiều ngược vì va chạm hash hợp lệ.
5. Khi trạng thái liên quan không đổi, kết quả `equals`/`hashCode` ổn định qua nhiều lời gọi.
6. `HashSet` loại trùng theo đúng identity; `HashMap.get` tìm lại giá trị bằng một đối tượng mới nhưng bằng nhau logic.
7. Dữ liệu identity ổn định sau khi đưa đối tượng vào collection; rà soát các trường mutable và alias tham chiếu.
8. Nếu khóa `equals` ở cha, thử tất cả cặp subtype có cùng/khác ID; xác nhận semantics thật sự mong muốn, đồng thời kiểm tra `hashCode` không còn đường override gây mâu thuẫn.

Với `TreeSet`/`TreeMap`, còn phải kiểm tra `Comparable`/`Comparator` và ý nghĩa của `compare(a,b)==0`; `final equals` không tự ràng buộc comparator.

**Kết luận:** `final class` khóa **cả đường kế thừa**, phù hợp với loại dữ liệu không cần subclass. `final equals(Object)` khóa **một định nghĩa bằng nhau dùng chung cho phân cấp**, nên đi cùng `final hashCode()`. Cả hai chỉ hữu ích khi tiêu chí identity đúng, khóa đủ ổn định và mọi đối tượng liên quan được kiểm tra theo hợp đồng Java.
