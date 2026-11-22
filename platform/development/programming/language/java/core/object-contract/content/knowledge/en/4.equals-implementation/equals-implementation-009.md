# Cài đặt equals: tránh so sánh thông qua toString() hoặc hashCode()

## 1. Vấn đề cốt lõi

Khi ghi đè **equals(Object)** trong Java, mục tiêu là trả lời: *hai đối tượng có được coi là cùng một giá trị theo quy tắc của lớp này không?* Quy tắc đó cần dựa trên những thuộc tính tạo nên ý nghĩa bình đẳng (equality) của đối tượng.

Hai cách viết tắt dễ gây lỗi là:

~~~java
// Sai về mặt thiết kế: lấy chuỗi hiển thị làm tiêu chí bằng nhau.
return this.toString().equals(other.toString());

// Sai về mặt logic: lấy mã băm trùng nhau làm bằng chứng bằng nhau.
return this.hashCode() == other.hashCode();
~~~

Các đoạn trên **chỉ minh họa biểu thức sai** trong một ngữ cảnh đã có biến other, không phải phương thức hoàn chỉnh. Vấn đề không nằm ở cú pháp Java mà ở việc dùng sai vai trò của phương thức:

| Phương thức | Mục đích | Điều KHÔNG được bảo đảm |
| --- | --- | --- |
| equals(Object) | Xác định hai đối tượng có bằng nhau về mặt logic theo hợp đồng của lớp hay không | Không tự biết tiêu chí nghiệp vụ; người thiết kế phải định nghĩa |
| toString() | Tạo chuỗi biểu diễn cho con người, ghi log hoặc gỡ lỗi | Không bảo đảm duy nhất, đầy đủ, ổn định, hoặc phản ánh chính xác tiêu chí equals |
| hashCode() | Tạo số nguyên băm để hỗ trợ cấu trúc như HashMap, HashSet | Không bảo đảm mỗi đối tượng hoặc mỗi giá trị khác nhau có số băm khác nhau |

**Quy tắc chính:** so sánh các trường mang ý nghĩa giá trị bằng equals/Objects.equals hoặc cách so sánh phù hợp với kiểu dữ liệu; triển khai hashCode tương thích dựa trên chính các trường ấy. Không suy ngược kết quả equals từ văn bản trình bày hoặc số băm.

## 2. Vì sao không dùng toString() để quyết định equals?

### 2.1. Hai đối tượng khác nhau có thể in ra cùng một chuỗi

Giả sử lớp Account có mã tài khoản id và tên hiển thị displayName. Yêu cầu nghiệp vụ là **hai Account bằng nhau khi cùng id**. toString lại được thiết kế chỉ in tên:

~~~java
@Override
public String toString() {
    return "Account{name='" + displayName + "'}";
}
~~~

Account(id = "A-01", displayName = "Lan") và Account(id = "A-02", displayName = "Lan") cùng in ra chuỗi Account{name='Lan'}, nhưng **không bằng nhau** theo id. Nếu equals so sánh hai chuỗi toString, nó trả true sai.

Nguyên nhân: văn bản phục vụ người đọc thường lược bỏ thuộc tính, che dữ liệu nhạy cảm, làm tròn số, rút gọn danh sách hoặc chọn một nhãn chung. Những quyết định trình bày đó không phải tiêu chí bình đẳng.

### 2.2. Hai đối tượng bằng nhau có thể in ra chuỗi khác nhau

Account(id = "A-01", displayName = "Lan") và Account(id = "A-01", displayName = "Linh") có cùng định danh nên equals phải là true theo quy tắc đã chọn, dù hai chuỗi toString khác nhau.

Trường displayName có thể thay đổi theo ý người dùng và **không tham gia equals**. Nếu đem toString ra so sánh, việc sửa tên hiển thị vô tình thay đổi danh tính logic.

Hai chiều đều không đúng:

- Kết quả x.toString().equals(y.toString()) là true **không suy ra** x.equals(y) là true.
- Kết quả x.equals(y) là true **không đòi hỏi** x.toString().equals(y.toString()) phải true.

### 2.3. toString là giao diện biểu diễn, có thể thay đổi

Đổi cách viết log từ Account{name='Lan'} sang Account(Lan), thêm timestamp, đổi định dạng số/ngày, thay đổi ngôn ngữ, hoặc chỉ đổi thứ tự trường trong chuỗi không được làm thay đổi ý nghĩa equals. Nếu equals phụ thuộc toString, một chỉnh sửa mang tính trình bày có thể trở thành lỗi logic trong tập hợp, so sánh dữ liệu hoặc kiểm thử.

Ngoài ra, Object.toString mặc định trả biểu diễn có dạng tên lớp, ký tự @ và biểu diễn hex của hashCode (đối với lớp không ghi đè toString). Chuỗi này **không phải định danh nghiệp vụ hay cam kết duy nhất**, và giá trị hex không nên được diễn giải như địa chỉ bộ nhớ được bảo đảm. Dùng toString mặc định làm phép so sánh thậm chí gián tiếp mắc vấn đề của hashCode.

Với mảng Java, việc gọi toString trực tiếp cũng không phải phép so sánh nội dung; muốn so sánh các phần tử phải dùng Arrays.equals hoặc Arrays.deepEquals theo cấu trúc.

## 3. Vì sao không dùng hashCode() để quyết định equals?

### 3.1. Hợp đồng chỉ có một chiều

Java quy định:

> Nếu hai đối tượng bằng nhau theo equals, chúng **phải** có cùng hashCode.

Viết bằng ký hiệu:

**x.equals(y) == true ⇒ x.hashCode() == y.hashCode().**

**Chiều ngược lại không đúng:** từ hashCode bằng nhau **không thể kết luận** equals là true.

Lý do: hashCode trả về một giá trị int 32 bit, trong khi tập các giá trị đối tượng có thể lớn hơn rất nhiều. **Va chạm băm (hash collision)** xảy ra khi hai giá trị khác nhau có cùng hashCode. Đây là điều bình thường, không phải bằng chứng rằng hai giá trị bằng nhau.

### 3.2. Va chạm có thể quan sát ngay với String

Ví dụ nổi tiếng và có thể lặp lại trong Java:

~~~java
System.out.println("Aa".hashCode()); // 2112
System.out.println("BB".hashCode()); // 2112
System.out.println("Aa".equals("BB")); // false
~~~

Chuỗi "Aa" và "BB" khác nội dung nhưng cùng mã băm 2112. Nếu viết equals kiểu chỉ kiểm tra this.hashCode() == other.hashCode(), hai đối tượng dùng hai chuỗi đó làm định danh có thể bị coi là bằng nhau sai.

Một phép kiểm tra như sau có thể loại nhanh một số trường hợp trong một thiết kế có hashCode đúng và ổn định:

~~~java
if (hashCode() != other.hashCode()) {
    return false;
}
// Hash giống nhau vẫn cần so sánh các trường thực sự.
~~~

Đó chỉ là đoạn minh họa, không phải phương thức equals hoàn chỉnh. Việc tối ưu thường không cần thiết cho equals thông thường; gọi hashCode có thể tốn thêm công và tăng độ phức tạp. Quan trọng nhất là **hash bằng nhau không đủ để trả true**.

### 3.3. HashMap/HashSet vẫn phân biệt khóa bị va chạm

HashMap và HashSet sử dụng giá trị băm để hỗ trợ tìm kiếm, đồng thời phải dùng phép so sánh bằng nhau phù hợp để phân biệt các khóa khi có va chạm. Hai khóa khác nhau cùng hashCode **vẫn có thể tồn tại riêng** trong HashSet hoặc HashMap.

Nếu bạn định nghĩa equals bằng việc “hash bằng nhau”, chính equals sai sẽ khiến bộ sưu tập coi các khóa khác giá trị là một. Sửa thuật toán hashCode để “ít va chạm hơn” không thể biến việc so sánh hash thành một cách triển khai equals đúng tổng quát.

## 4. Triển khai đúng: chọn trường định danh rồi so sánh trực tiếp

Xét quy tắc nghiệp vụ cho Account:

- Trường id khác null và là **định danh logic**.
- Trường displayName chỉ để hiển thị; hai tài khoản cùng id vẫn bằng nhau dù tên hiển thị khác.
- Khi ghi đè equals, lớp cũng ghi đè hashCode bằng đúng thuộc tính id.
- toString dùng displayName để minh họa sự độc lập giữa chuỗi hiển thị và phép so sánh giá trị.
- Các trường để final giúp trạng thái làm khóa băm giữ ổn định sau khởi tạo.

Mẫu cốt lõi:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Account that)) {
        return false;
    }
    return id.equals(that.id);
}

@Override
public int hashCode() {
    return id.hashCode();
}
~~~

Ở đây, Account là lớp final nên phép kiểm tra instanceof không tạo ra vấn đề đối xứng giữa lớp cha và lớp con. Với hệ phân cấp kế thừa có thể ghi đè equals, cần xem xét chính sách kiểu đối tượng, tính đối xứng và bắc cầu cẩn thận; không được tự động sao chép một công thức cho mọi cấu trúc lớp.

Dùng Objects.equals(a, b) khi các trường được phép null, hoặc gọi equals trực tiếp sau khi bảo đảm không null. Với nhiều trường cùng tham gia equality, so sánh **từng trường liên quan** một cách nhất quán và xây dựng hashCode từ các trường đó. Không đưa thêm displayName vào hashCode nếu equals không dùng nó: hai Account cùng id nhưng khác displayName phải có hashCode bằng nhau.

## 5. Chương trình Java 17+ chạy được và kết quả chính xác

Lưu thành tệp **EqualsWithoutShortcutsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsWithoutShortcutsDemo {
    public static void main(String[] args) {
        Account a = new Account("A-01", "Lan");
        Account b = new Account("A-02", "Lan");
        Account c = new Account("A-01", "Linh");

        System.out.println("Same text: " + a.toString().equals(b.toString()));
        System.out.println("Equals, different id: " + a.equals(b));
        System.out.println("Different text: " + !a.toString().equals(c.toString()));
        System.out.println("Equals, same id: " + a.equals(c));

        System.out.println("Aa hash: " + "Aa".hashCode());
        System.out.println("BB hash: " + "BB".hashCode());
        System.out.println("Strings equal: " + "Aa".equals("BB"));

        Account keyA = new Account("Aa", "First");
        Account keyB = new Account("BB", "Second");
        System.out.println("Same hash: " + (keyA.hashCode() == keyB.hashCode()));
        System.out.println("Equals, collision: " + keyA.equals(keyB));

        Set<Account> set = new HashSet<>();
        set.add(keyA);
        set.add(keyB);
        System.out.println("HashSet size: " + set.size());
    }

    static final class Account {
        private final String id;
        private final String displayName;

        Account(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Account that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }

        @Override
        public String toString() {
            return "Account{name='" + displayName + "'}";
        }
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac EqualsWithoutShortcutsDemo.java
java EqualsWithoutShortcutsDemo
~~~

Kết quả:

~~~text
Same text: true
Equals, different id: false
Different text: true
Equals, same id: true
Aa hash: 2112
BB hash: 2112
Strings equal: false
Same hash: true
Equals, collision: false
HashSet size: 2
~~~

Diễn giải theo từng nhóm:

1. **Same text: true** nhưng **Equals, different id: false** chứng minh chuỗi giống nhau không đủ để kết luận hai Account bằng nhau.
2. **Different text: true** nhưng **Equals, same id: true** chứng minh chuỗi hiển thị khác nhau cũng không đủ để kết luận hai Account khác nhau.
3. "Aa" và "BB" cùng có hash 2112, nhưng String.equals là false. Hai Account tương ứng cũng cùng hashCode và không bằng nhau.
4. HashSet chứa đủ **hai** Account có id khác nhau dù xảy ra va chạm hashCode, vì equals được xây dựng đúng từ id.

Đây là chương trình độc lập đầy đủ. Các ví dụ ngắn ở phần trên chỉ là trích đoạn minh họa, nên không nên biên dịch riêng từng mảnh.

## 6. Các lỗi thường gặp và cách tránh

### Lỗi A — so sánh chuỗi biểu diễn thay vì giá trị

~~~java
// Không nên: chuỗi in ra không đại diện đầy đủ cho bình đẳng logic.
return this.toString().equals(that.toString());
~~~

**Cách sửa:** xác định thuộc tính thực sự quyết định equality; so sánh trực tiếp trường đó. Trong ví dụ Account, dùng id.equals(that.id) sau bước xác minh kiểu.

### Lỗi B — coi hashCode giống nhau là bằng nhau

~~~java
// Sai: va chạm băm làm phát sinh false positive.
return this.hashCode() == that.hashCode();
~~~

**Cách sửa:** hashCode chỉ hỗ trợ phân vùng/tìm kiếm theo băm; equals phải kiểm tra giá trị thật. Đặc biệt tránh dùng Objects.hash(...) làm “chữ ký duy nhất” để so sánh hai đối tượng.

### Lỗi C — equals đúng nhưng hashCode không khớp

~~~java
// Ý tưởng sai: equals chỉ dùng id nhưng hashCode lại dùng cả displayName.
@Override
public int hashCode() {
    return Objects.hash(id, displayName);
}
~~~

Nếu hai Account có cùng id nhưng khác displayName, chúng bằng nhau theo equals mà có thể có hashCode khác nhau, vi phạm hợp đồng bắt buộc. **Cách sửa:** chỉ tính hash từ các trường được sử dụng trong equals, ví dụ return id.hashCode();. Đây là mảnh code minh họa sai, không phải một lớp độc lập.

### Lỗi D — nhầm equals với so sánh tham chiếu

Với các đối tượng String hoặc lớp giá trị, toán tử == hỏi xem hai biến có trỏ tới **cùng đối tượng** không. Nó không thay thế so sánh giá trị:

~~~java
Objects.equals(left.id, right.id)
~~~

Trong trường hợp id bảo đảm không null, left.id.equals(right.id) cũng phù hợp. Với kiểu nguyên thủy như int, dùng == để so sánh giá trị; với mảng, dùng Arrays.equals hoặc Arrays.deepEquals tùy cấu trúc. Chọn phép so sánh đúng cho từng kiểu thay vì tuần tự hóa qua toString.

### Lỗi E — thay đổi trường định danh của khóa đang lưu trong HashSet/HashMap

Nếu trường tham gia equals/hashCode bị sửa sau khi đối tượng làm khóa được chèn vào tập băm, thao tác tra cứu có thể thất bại vì vị trí băm ban đầu không được tự cập nhật. Mẫu trên dùng trường id final để tránh vấn đề phổ biến này; cần lưu ý final của một tham chiếu **không** làm đối tượng mutable mà nó trỏ tới trở thành bất biến.

### Lỗi F — nghĩ toString, hashCode và equals cần cho ra cùng “định danh”

Không có hợp đồng nào bắt buộc toString phải chứa mọi trường bằng nhau, trùng với hashCode, hoặc có nội dung giống nhau trên những đối tượng được coi là bằng nhau. Hợp đồng thực sự liên quan **equals và hashCode**: equal ⇒ same hash. toString là trách nhiệm biểu diễn khác biệt.

## 7. Kiểm thử quan trọng cho lớp có equals riêng

Với lựa chọn “bằng nhau khi cùng id”, cần bao phủ cả trường hợp khiến hai shortcut sai:

| Trường hợp | Kỳ vọng equals | Điều được kiểm chứng |
| --- | --- | --- |
| Cùng id, khác displayName | true | toString khác nhau không ảnh hưởng equality |
| Khác id, cùng displayName | false | toString giống nhau không tạo equality giả |
| Khác id nhưng hashCode trùng nhau | false | Va chạm băm không tạo equality giả |
| Cùng id, hashCode tương ứng | Bằng nhau và cùng hashCode | Hợp đồng equals/hashCode |
| Một tham chiếu so với chính nó | true | Tính phản xạ |
| Bất kỳ Account nào so với null | false | Điều kiện null |
| Đổi thứ tự so sánh hai Account | Cùng kết quả | Tính đối xứng |
| Ba Account có cùng id | Kết quả bắc cầu | Tính bắc cầu |

Một kiểm tra nhanh đối với ba Account bất biến:

~~~java
Account x = new Account("A-01", "Lan");
Account y = new Account("A-01", "Linh");
Account z = new Account("A-02", "Lan");

if (!x.equals(y) || x.hashCode() != y.hashCode()) {
    throw new AssertionError("Cùng id phải bằng nhau và có cùng hash");
}
if (x.equals(z)) {
    throw new AssertionError("Khác id không được bằng nhau");
}
~~~

Đoạn này là ví dụ **đặt trong phạm vi có lớp Account đã khai báo**; trong chương trình đầy đủ ở phần 5, Account là lớp lồng bên trong EqualsWithoutShortcutsDemo nên không biên dịch đoạn kiểm thử này thành một tệp đứng riêng. Để kiểm thử thực tế, đặt nó trong cùng lớp bao ngoài/phương thức phù hợp hoặc dùng một framework như JUnit. Các kiểm tra trong bảng trên cần kết hợp để bảo vệ toàn bộ hợp đồng, không chỉ một ca thử.

Với Java record, trình biên dịch có thể tạo equals/hashCode/toString từ các component của record. Điều đó tiện lợi khi **tất cả component** thực sự phù hợp với định nghĩa equality mong muốn; vẫn cần thiết kế thành phần dữ liệu theo nghĩa nghiệp vụ. Dù record sinh sẵn toString, cũng không dùng kết quả chuỗi đó làm cách cài đặt equals riêng.

## 8. Quy trình chọn cài đặt

1. **Xác định bình đẳng logic:** khóa định danh hay toàn bộ giá trị nào làm hai đối tượng được coi là tương đương? Ví dụ Account dùng id.
2. **Kiểm tra kiểu và null:** tự so sánh với chính nó trả true, kiểu không tương thích/null trả false; cẩn thận với kế thừa.
3. **So sánh trực tiếp trường liên quan:** dùng Objects.equals, các phương thức equals của kiểu giá trị, Arrays.equals cho mảng, hoặc phép so sánh phù hợp cho primitive.
4. **Sinh hashCode từ cùng dữ liệu:** bảo đảm nếu equals true thì hashCode bằng nhau, đồng thời chấp nhận collision giữa hai giá trị khác nhau.
5. **Để toString phục vụ hiển thị:** chỉnh log/định dạng không được vô tình đổi kết quả equality.
6. **Đánh giá tính bất biến và kiểm thử:** nhất là trường hợp cùng text nhưng khác giá trị, khác text nhưng cùng giá trị, cùng hash nhưng khác giá trị, đối xứng, bắc cầu và null.

**Ghi nhớ:** toString() tạo biểu diễn; hashCode() cung cấp mã băm có thể va chạm; chỉ **equals() dựa trên các thuộc tính có ý nghĩa** mới quyết định hai đối tượng bằng nhau về mặt logic.