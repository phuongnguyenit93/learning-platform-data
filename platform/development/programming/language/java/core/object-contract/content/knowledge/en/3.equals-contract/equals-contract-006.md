# So sánh với null phải trả về false — hợp đồng equals(Object)

## 1. Quy tắc và phạm vi áp dụng

Trong Java, lớp java.lang.Object quy định rằng: **với mọi tham chiếu x khác null, biểu thức x.equals(null) phải trả về false**. Đây là một điều khoản chính thức trong hợp đồng của phương thức equals(Object), bên cạnh tính phản xạ, đối xứng, bắc cầu và nhất quán.

Ý nghĩa: null biểu thị sự vắng mặt của tham chiếu đến đối tượng; nó không phải một đối tượng có thể bằng với một đối tượng đang tồn tại. Dù lớp định nghĩa bình đẳng theo mã định danh, dữ liệu nghiệp vụ hay toàn bộ trạng thái, không được coi null là bằng một đối tượng khác null.

Cần phân biệt ba trường hợp:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| x.equals(null), với x khác null và triển khai đúng | false | Điều khoản “non-nullity” của equals |
| x.equals(y), với x và y đều khác null | Phụ thuộc quy tắc bình đẳng của lớp | Kiểm tra dữ liệu hoặc danh tính theo hợp đồng |
| missing.equals(x), với missing == null | Ném NullPointerException | Không thể gọi phương thức thể hiện trên tham chiếu null |

Quy tắc chỉ nói về **đối số null khi đối tượng nhận lời gọi khác null**. Nó không có nghĩa là mọi phép so sánh có null đều phải trả về false: hai tham chiếu cùng null có thể được một hàm tiện ích xác định là “cùng vắng mặt”.

## 2. Triển khai equals(Object) đúng và an toàn

Trong Java 17+, phép kiểm tra kiểu bằng instanceof có một thuộc tính rất hữu ích: **null instanceof MộtKiểu luôn là false**. Vì vậy, kiểm tra kiểu trước khi đọc thuộc tính đối tượng vừa đáp ứng điều khoản null, vừa xử lý đối số không cùng kiểu.

~~~java
import java.util.Objects;

public class EqualsNullDemo {
    static final class Account {
        private final String number;

        Account(String number) {
            this.number = Objects.requireNonNull(number, "number");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Account account)) {
                return false; // Bao gồm other == null
            }
            return number.equals(account.number);
        }

        @Override
        public int hashCode() {
            return number.hashCode();
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A1");
        Account same = new Account("A1");
        Account different = new Account("B2");
        Account missing = null;
        String status = null;

        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("a.equals(same): " + a.equals(same));
        System.out.println("a.equals(different): " + a.equals(different));
        System.out.println("Objects.equals(a, null): " + Objects.equals(a, null));
        System.out.println("Objects.equals(null, null): " + Objects.equals(null, null));
        System.out.println("constant.equals(status): " + "READY".equals(status));
        System.out.println("missing == null: " + (missing == null));
    }
}
~~~

Lưu với tên **EqualsNullDemo.java**, rồi thực thi trên JDK 17 trở lên:

~~~bash
javac EqualsNullDemo.java
java EqualsNullDemo
~~~

Kết quả chuẩn:

~~~text
a.equals(null): false
a.equals(same): true
a.equals(different): false
Objects.equals(a, null): false
Objects.equals(null, null): true
constant.equals(status): false
missing == null: true
~~~

Diễn giải theo đúng thứ tự xử lý của equals:

1. Khi other trỏ tới chính a, biểu thức this == other trả về true; điều này bảo đảm tính phản xạ.
2. Khi other là null, this == other là false; instanceof cũng trả về false, nên phương thức dừng an toàn.
3. Khi other là Account khác, việc so sánh number quyết định hai đối tượng có bằng nhau hay không.
4. Việc ghi đè hashCode là bắt buộc về mặt hợp đồng khi ghi đè equals: các đối tượng bằng nhau phải có cùng giá trị hashCode. Trong ví dụ, cùng number luôn dẫn tới cùng hashCode.

Vì Account là final nên không có lớp con gây bất đồng về quy tắc bình đẳng. Trong thiết kế cho phép kế thừa, cần chủ động xem xét chính sách so sánh kiểu và tính đối xứng: lựa chọn instanceof hay getClass() có thể ảnh hưởng tới tính tương thích của các lớp cha/con, nhưng **không thay đổi** quy tắc đối số null phải cho kết quả false.

Một cách triển khai khác cũng hợp lệ là kiểm tra null tường minh trước:

~~~java
@Override
public boolean equals(Object other) {
    if (other == null) {
        return false;
    }
    if (this == other) {
        return true;
    }
    if (!(other instanceof Account account)) {
        return false;
    }
    return number.equals(account.number);
}
~~~

Đây là **đoạn thay thế riêng phương thức equals trong lớp Account bên trên**, không phải chương trình Java độc lập. Nhánh other == null giúp người đọc dễ nhận thấy hợp đồng; trong trường hợp này nó không cần thiết về mặt kỹ thuật vì instanceof đã xử lý null. Nếu thuộc tính dùng làm khóa bình đẳng cho phép null, có thể dùng Objects.equals(number, account.number) thay cho number.equals(account.number) để so sánh thuộc tính an toàn.

## 3. equals(Object) khác với Objects.equals(a, b)

**Objects.equals(a, b)** là phương thức tiện ích tĩnh giúp so sánh hai tham chiếu có thể null. Về mặt hành vi, nó tương đương với:

~~~java
return a == b || (a != null && a.equals(b));
~~~

Đây là **biểu thức minh họa phần thân logic của phương thức tiện ích**, không phải phương thức tự chạy. Trường hợp hai đối số đều null, a == b trả về true. Trường hợp chỉ một đối số null, kết quả là false. Nếu a khác null và hai tham chiếu không trùng nhau, tiện ích gọi a.equals(b).

Vì thế:

- **new Account("A1").equals(null)** → false: đối tượng không bằng null.
- **Objects.equals(new Account("A1"), null)** → false: chỉ một tham chiếu null.
- **Objects.equals(null, null)** → true: cùng tham chiếu null, không gọi equals trên null.
- **"READY".equals(status)** khi status == null → false: mẫu so sánh an toàn khi chuỗi hằng ở bên trái.

Không có mâu thuẫn giữa việc Objects.equals(null, null) là true và hợp đồng của Object.equals(Object): điều khoản của hợp đồng chỉ xét lời gọi phương thức trên một đối tượng **khác null**.

Khi chỉ muốn kiểm tra tham chiếu có vắng mặt hay không, viết **value == null** hoặc **value != null** cho rõ ý. Khi cần so sánh bình đẳng giữa hai tham chiếu có thể null, dùng Objects.equals(left, right); khi chắc chắn đối tượng nhận khác null, có thể dùng receiver.equals(value).

## 4. Những lỗi thường gặp

### 4.1. Trả về true cho đối số null

~~~java
@Override
public boolean equals(Object other) {
    if (other == null) {
        return true; // Sai hợp đồng equals
    }
    // ... so sánh phần còn lại
}
~~~

Đây là **mã minh họa lỗi**, không phải ví dụ chạy độc lập. Dù lớp có coi các trường dữ liệu vắng mặt là tương đương, một đối tượng tồn tại vẫn không được bằng chính tham chiếu null. Hãy trả về false và chỉ so sánh dữ liệu sau khi đã kiểm tra kiểu.

### 4.2. Ép kiểu hoặc truy cập trường trước khi kiểm tra null

~~~java
@Override
public boolean equals(Object other) {
    Account account = (Account) other;
    return number.equals(account.number);
}
~~~

Đây cũng là **mã minh họa lỗi** bên trong Account. Khi other == null, phép ép kiểu vẫn cho null nhưng việc truy cập account.number sẽ gây NullPointerException. Khi other là đối tượng khác kiểu, phép ép kiểu có thể gây ClassCastException. Cả hai trường hợp đều cần được loại trừ bằng kiểm tra kiểu trước khi truy cập thuộc tính.

### 4.3. Chỉ nạp chồng equals(Account) thay vì ghi đè equals(Object)

~~~java
public boolean equals(Account other) {
    return number.equals(other.number);
}
~~~

Đoạn mã trên khai báo **một overload**, không ghi đè Object.equals(Object). Lời gọi a.equals(null) có thể được trình biên dịch chọn overload nhận Account (vì tham số cụ thể hơn Object), rồi gây NullPointerException; trong khi lời gọi qua tham chiếu kiểu Object lại đi theo phương thức khác. Hãy dùng đúng chữ ký **public boolean equals(Object other)** kèm **@Override** để trình biên dịch kiểm tra.

### 4.4. Nhầm lẫn với lời gọi trên null

~~~java
Account missing = null;
Account a = new Account("A1");
// missing.equals(a); // Ném NullPointerException nếu bỏ dấu chú thích
boolean safe = Objects.equals(missing, a); // false
~~~

Đây là **đoạn minh họa đặt trong ngữ cảnh có lớp Account**, không phải chương trình độc lập. Việc viết đúng equals trong Account không thể làm cho missing.equals(a) trở nên an toàn: Java phải tìm đối tượng nhận phương thức trước khi thực thi thân equals.

Ngoài ra, không nên viết **return Objects.equals(this, other)** bên trong chính equals(Object): khi this và other đều khác null, không cùng tham chiếu, phương thức tiện ích sẽ gọi lại this.equals(other), dẫn tới đệ quy vô hạn cho cặp không bằng nhau và cuối cùng là StackOverflowError.

## 5. Kiểm tra hợp đồng khi tự viết equals

Một phép kiểm tra tối thiểu, chạy trên mọi đối tượng khác null của lớp, là:

~~~java
Account a = new Account("A1");
if (a.equals(null)) {
    throw new AssertionError("equals(null) phải trả về false");
}
~~~

Đoạn kiểm tra này cần đặt trong phương thức main hoặc một phương thức kiểm thử có quyền truy cập Account. Với JUnit 5, ý tưởng tương đương là **assertFalse(a.equals(null))**.

Nên kiểm tra cùng lúc các thuộc tính khác của equals: a.equals(a) là true; hai Account có number giống nhau phải bằng nhau ở cả hai chiều và có hashCode bằng nhau; number khác nhau cho false; đầu vào không cùng kiểu cho false; lặp lại so sánh khi trạng thái không thay đổi phải cho kết quả ổn định. Đặc biệt, nếu dùng các đối tượng làm khóa HashMap hoặc phần tử HashSet, thuộc tính tham gia equals/hashCode nên ổn định trong suốt thời gian ở trong cấu trúc dữ liệu.

**Ghi nhớ:** Với mọi x khác null, **x.equals(null) == false**. Đặt kiểm tra null/kiểu ở đầu phương thức equals(Object), hoặc dùng instanceof một cách an toàn; chỉ dùng Objects.equals khi bạn cần so sánh hai giá trị mà mỗi bên có thể null.