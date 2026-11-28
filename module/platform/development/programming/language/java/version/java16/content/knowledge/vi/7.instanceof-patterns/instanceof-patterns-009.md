# Dùng pattern variable trong equals tường minh của lớp dữ liệu

## 1. Vì sao pattern matching hữu ích trong equals?

Một lớp dữ liệu thường cần định nghĩa khi nào hai đối tượng được xem là bằng nhau. Trong Java, phương thức dùng cho mục đích này là `equals(Object obj)`, được kế thừa từ `Object`.

Trước Java 16, cách viết phổ biến là kiểm tra kiểu rồi ép kiểu thủ công:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof AccountKey)) {
        return false;
    }

    AccountKey other = (AccountKey) obj;
    return accountId == other.accountId;
}
~~~

Từ Java 16, pattern matching for `instanceof` cho phép gộp phép kiểm tra kiểu với việc khai báo biến nhận đối tượng đã khớp:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof AccountKey other)) {
        return false;
    }

    return accountId == other.accountId;
}
~~~

Biến `other` có kiểu tĩnh `AccountKey` và chỉ được sử dụng trên đường đi mà pattern đã khớp. Không cần viết thêm phép ép kiểu `(AccountKey) obj`. Đây là cú pháp chính thức từ Java 16 theo JEP 394, không phải tính năng preview.

## 2. Mẫu equals(Object) với pattern variable

Một lớp dữ liệu có thể chứa nhiều trường cần tham gia xác định danh tính:

~~~java
import java.util.Objects;

public final class AccountKey {
    private final String tenant;
    private final long accountId;

    public AccountKey(String tenant, long accountId) {
        this.tenant = tenant;
        this.accountId = accountId;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }

        if (!(obj instanceof AccountKey other)) {
            return false;
        }

        return accountId == other.accountId
                && Objects.equals(tenant, other.tenant);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenant, accountId);
    }
}
~~~

Trong phương thức này:

1. `this == obj` xử lý nhanh trường hợp hai tham chiếu cùng trỏ đến một đối tượng.
2. `obj instanceof AccountKey other` kiểm tra đối tượng có phải `AccountKey` hay không và khai báo biến `other`.
3. Nếu pattern không khớp, phương thức trả về `false`.
4. Nếu pattern khớp, phần còn lại so sánh các trường dùng để xác định giá trị của khóa.

`Objects.equals(tenant, other.tenant)` so sánh an toàn khi một hoặc cả hai giá trị chuỗi là `null`. Với `accountId` là kiểu nguyên thủy `long`, có thể so sánh trực tiếp bằng `==`.

## 3. Vì sao `other` dùng được sau câu lệnh guard?

Phạm vi của pattern variable được xác định theo luồng điều khiển (*flow scoping*). Trong `equals`, câu lệnh:

~~~java
if (!(obj instanceof AccountKey other)) {
    return false;
}
~~~

đảm bảo mọi đường đi tiếp tục sau `if` đều đã khớp với `AccountKey`. Nếu `obj` là `null` hoặc có kiểu khác, pattern thất bại, điều kiện phủ định đúng và phương thức kết thúc bằng `return false`.

Vì vậy, ở dòng so sánh tiếp theo, `other` chắc chắn đã được ràng buộc và khác `null`:

~~~java
return accountId == other.accountId
        && Objects.equals(tenant, other.tenant);
~~~

Không cần kiểm tra `other != null` thêm lần nữa. Phép `instanceof` trả về `false` với nguồn `null`, nên pattern không bao giờ cung cấp một `other` có giá trị `null`.

Có thể viết biểu thức ngắn hơn bằng `&&`:

~~~java
return obj instanceof AccountKey other
        && accountId == other.accountId
        && Objects.equals(tenant, other.tenant);
~~~

Vế phải của `&&` chỉ được đánh giá khi pattern khớp. Tuy nhiên, dạng guard clause thường dễ đọc hơn khi `equals` có nhiều trường hoặc cần xử lý thêm điều kiện.

## 4. Luôn ghi đè đúng `equals(Object)`

Chữ ký phương thức phải nhận `Object`, không phải chính lớp dữ liệu:

~~~java
public boolean equals(Object obj) {
    // ...
}
~~~

Nếu viết `equals(AccountKey other)`, đó là một overload (nạp chồng), không ghi đè phương thức `equals(Object)` của `Object`. Khi một API hoặc collection gọi `equals(Object)`, phương thức overload có thể không được sử dụng như mong đợi.

Luôn đặt `@Override`:

~~~java
@Override
public boolean equals(Object obj) {
    // So sánh giá trị
}
~~~

Trình biên dịch sẽ báo lỗi nếu chữ ký không thực sự ghi đè được phương thức cha.

## 5. equals phải tuân thủ hợp đồng và đi cùng hashCode

Khi định nghĩa equality, không chỉ cần so sánh đúng các trường. Phương thức `equals` còn phải tuân thủ hợp đồng của Java:

- **Phản xạ:** một đối tượng phải bằng chính nó.
- **Đối xứng:** nếu `a.equals(b)` là `true`, thì `b.equals(a)` cũng phải là `true`.
- **Bắc cầu:** nếu `a.equals(b)` và `b.equals(c)` đều là `true`, thì `a.equals(c)` cũng phải là `true`.
- **Nhất quán:** kết quả không thay đổi khi các dữ liệu dùng để so sánh không thay đổi.
- **Không null:** với đối tượng khác `null`, `equals(null)` phải trả về `false`.

`hashCode` có hợp đồng liên quan:

- Nếu hai đối tượng bằng nhau theo `equals`, chúng phải có cùng `hashCode`.
- Hai đối tượng không bằng nhau có thể có cùng mã băm; Java không yêu cầu mọi mã băm phải duy nhất.

Vì vậy, phải dùng cùng tập trường để quyết định `equals` và `hashCode`. Với ví dụ `AccountKey`, cả hai đều sử dụng `tenant` và `accountId`.

~~~java
@Override
public int hashCode() {
    return Objects.hash(tenant, accountId);
}
~~~

`Objects.hash` là API chuẩn của Java và phù hợp khi cần kết hợp nhiều trường. Nếu lớp dùng trường mảng, cần chọn các hàm `Arrays.equals` và `Arrays.hashCode` tương ứng thay vì dựa vào so sánh tham chiếu mặc định của mảng.

## 6. Chọn `instanceof` hay kiểm tra đúng class bằng `getClass()`?

Đây là một quyết định thiết kế quan trọng đối với lớp dữ liệu có thể được kế thừa.

### 6.1. Lớp dữ liệu `final`: thường dùng `instanceof` pattern

Trong ví dụ `AccountKey`, lớp được khai báo `final`. Không có lớp con nào có thể mở rộng nó, nên kiểm tra:

~~~java
if (!(obj instanceof AccountKey other)) {
    return false;
}
~~~

là cách viết ngắn gọn và rõ ràng. Mọi đối tượng khớp đều có đúng kiểu `AccountKey`; không có lớp con thêm trạng thái làm thay đổi ý nghĩa equality.

Đối với các lớp giá trị độc lập, bất biến và không cần kế thừa, thiết kế `final` giúp quy tắc bằng nhau dễ duy trì.

### 6.2. Khi cần phân biệt chính xác lớp runtime

Nếu lớp không `final` và equality yêu cầu hai đối tượng phải có cùng lớp runtime, có thể kết hợp pattern với `getClass()`:

~~~java
public class Amount {
    private final long cents;

    public Amount(long cents) {
        this.cents = cents;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Amount other)
                || getClass() != other.getClass()) {
            return false;
        }
        return cents == other.cents;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(cents);
    }
}
~~~

Điều kiện đầu tiên xác nhận `obj` là một `Amount` hoặc subtype của nó. Điều kiện thứ hai yêu cầu lớp runtime của `this` và `other` giống hệt nhau. Nhờ `||` đánh giá ngắn mạch, `other.getClass()` chỉ được gọi sau khi pattern đã khớp.

Kiểm tra `getClass()` có ngữ nghĩa chặt hơn `instanceof`: một `Amount` và một lớp con của `Amount` không được xem là bằng nhau, kể cả khi giá trị `cents` trùng nhau.

### 6.3. Vì sao kế thừa làm equals khó hơn?

Giả sử `Amount` có lớp con bổ sung trường `discount`. Nếu `equals` ở lớp cha chỉ so sánh `cents`, hai đối tượng của lớp con có thể bị xem là bằng nhau dù `discount` khác nhau. Nếu lớp con ghi đè `equals` để so sánh thêm `discount`, phép so sánh giữa đối tượng cha và con có thể vi phạm tính đối xứng.

`getClass()` ngăn equality giữa hai lớp runtime khác nhau, nhưng không tự động so sánh trường mới của lớp con. Nếu lớp con kế thừa nguyên `equals` của lớp cha, hai instance của cùng lớp con vẫn có thể bị so sánh chỉ bằng các trường của lớp cha.

Vì thế, với lớp dữ liệu có trạng thái, lựa chọn dễ duy trì nhất thường là:

- Dùng lớp `final` nếu equality chỉ dựa trên dữ liệu của chính lớp.
- Nếu cho phép kế thừa, thiết kế hợp đồng `equals`/`hashCode` cho toàn bộ hệ phân cấp ngay từ đầu và yêu cầu lớp con tham gia đầy đủ.
- Không thêm lớp con mang trạng thái vào một hệ equality đã được định nghĩa mà không xem xét lại tính đối xứng và bắc cầu.

## 7. Những trường hợp cần chú ý khi so sánh trường

### 7.1. Trường tham chiếu có thể là `null`

Sử dụng `Objects.equals` cho trường tham chiếu:

~~~java
Objects.equals(left.name, right.name)
~~~

Biểu thức trả về `true` nếu cả hai cùng `null`, hoặc nếu hai giá trị không null bằng nhau theo `equals`. Nếu trường bắt buộc không null, có thể kiểm tra ở constructor và dùng trực tiếp `field.equals(other.field)`.

### 7.2. Kiểu nguyên thủy

Các kiểu nguyên thủy có thể so sánh trực tiếp:

~~~java
return active == other.active
        && score == other.score;
~~~

Với `float` và `double`, cần chọn cách so sánh phù hợp với ý nghĩa dữ liệu và hợp đồng mong muốn; không mặc định rằng mọi phép so sánh số thực đều nên dùng `==`.

### 7.3. Collection

Các collection chuẩn như `List` định nghĩa `equals` theo nội dung và thứ tự phần tử. Nếu hai trường `List<String>` được dùng trong equality, có thể so sánh bằng `Objects.equals`:

~~~java
return Objects.equals(tags, other.tags);
~~~

Hãy bảo đảm các phần tử bên trong cũng có equality phù hợp. Nếu collection hoặc phần tử có thể thay đổi, equality và hash code của đối tượng chứa cũng có thể thay đổi theo.

## 8. Không làm thay đổi trường tham gia equality sau khi đưa vào hash collection

Nếu một đối tượng được đưa vào `HashSet` hoặc dùng làm khóa `HashMap`, các trường tham gia `equals` và `hashCode` nên bất biến trong thời gian đối tượng nằm trong collection.

Ví dụ, nếu `tenant` hoặc `accountId` thay đổi sau khi thêm `AccountKey` vào `HashSet`, mã băm mới có thể khác mã băm lúc thêm. Khi đó, việc tìm hoặc xóa đối tượng có thể không hoạt động như mong đợi.

Đây là một lý do thực tế để dùng các trường `final` cho lớp giá trị:

~~~java
private final String tenant;
private final long accountId;
~~~

`final` bảo vệ việc gán lại tham chiếu hoặc giá trị nguyên thủy. Với trường tham chiếu tới một collection có thể thay đổi, chỉ khai báo tham chiếu `final` là chưa đủ; cần sao chép phòng vệ hoặc dùng collection không thể sửa đổi nếu equality phụ thuộc vào nội dung của nó.

## 9. Khi nào nên tự viết equals, khi nào nên dùng record?

Từ Java 16, `record` là tính năng chính thức để khai báo lớp dữ liệu. Record tự sinh `equals`, `hashCode` và `toString` dựa trên các component:

~~~java
public record AccountKey(String tenant, long accountId) {
}
~~~

Nếu equality mặc định theo các component là đúng với yêu cầu, thường không cần tự viết `equals` cho record. Record cũng là kiểu final, nên không có vấn đề lớp con mở rộng trạng thái như lớp dữ liệu thông thường.

Lớp thường vẫn cần `equals` tường minh khi:

- Đã có một API hoặc mô hình lớp không thể chuyển thành record.
- Quy tắc equality có chủ đích khác với phép so sánh component mặc định.
- Cần giữ tương thích với thiết kế lớp hiện tại.

Trong các trường hợp đó, pattern variable giúp phần kiểm tra kiểu trong `equals(Object)` gọn hơn và loại bỏ phép ép kiểu thủ công.

**Ghi nhớ:** Trong `equals(Object obj)`, dùng `obj instanceof DataType other` để kiểm tra kiểu và lấy biến đã khớp trong một bước. Sau guard clause, `other` chỉ khả dụng khi pattern thành công. Hãy so sánh cùng tập trường trong `equals` và `hashCode`, đồng thời quyết định rõ lớp dữ liệu có cho phép kế thừa hay không để giữ hợp đồng equality ổn định.
