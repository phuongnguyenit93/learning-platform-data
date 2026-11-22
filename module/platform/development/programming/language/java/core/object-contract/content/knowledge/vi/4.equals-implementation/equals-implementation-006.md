# Dùng `Objects.equals()` cho trường có thể `null` khi cài đặt `equals()`

Trong Java, một trường kiểu tham chiếu như `String`, `Address` hay `Integer` có thể nhận `null`. Khi cài đặt lại `equals(Object)`, việc gọi `field.equals(other.field)` trực tiếp có thể ném `NullPointerException` nếu `field` đang `null`. `java.util.Objects.equals(a, b)` là cách diễn đạt gọn, rõ và **an toàn khi một hoặc cả hai tham chiếu là `null`**.

Bài học tập trung vào cách dùng `Objects.equals()` để xây dựng hợp đồng bằng nhau theo giá trị, phối hợp với `hashCode()` và tránh các lỗi thường gặp.

## 1. Từ phép so sánh không an toàn đến `Objects.equals`

Đoạn sau chỉ minh họa biểu thức đặt bên trong một phương thức `equals`; nó **không phải chương trình Java độc lập**:

```java
// Sai khi displayName có thể null:
return displayName.equals(other.displayName);
```

Nếu `displayName == null`, phép truy cập `.equals(...)` trên tham chiếu `null` sẽ ném ngoại lệ. Điều này xảy ra ngay cả khi `other.displayName` cũng là `null` và hai trường đáng lẽ phải được xem là tương đương.

Có thể kiểm tra hai bên bằng điều kiện tường minh, nhưng thường dùng cách ngắn gọn hơn:

```java
// Biểu thức tương đương về kết quả, với equals được cài đặt đúng hợp đồng:
return displayName == other.displayName
        || (displayName != null && displayName.equals(other.displayName));

// Cách viết khuyến nghị cho trường nullable:
return Objects.equals(displayName, other.displayName);
```

Nhớ `import java.util.Objects;`. `Objects.equals` là phương thức `static`, nên không phải gọi trên đối tượng có thể đang `null`.

## 2. Quy tắc của `Objects.equals(a, b)`

Về hành vi, `Objects.equals(a, b)` tương đương:

```java
a == b || (a != null && a.equals(b))
```

| `a` | `b` | Kết quả | Giải thích |
| --- | --- | --- | --- |
| `null` | `null` | `true` | Cả hai cùng vắng giá trị |
| `null` | Không `null` | `false` | Chỉ một phía vắng giá trị |
| Không `null` | `null` | `false` với lớp tuân thủ hợp đồng `equals` | `a.equals(null)` phải trả về `false` |
| Cùng tham chiếu | Cùng tham chiếu | `true` | `a == b` đúng |
| Hai đối tượng khác tham chiếu, cùng có giá trị | Hai đối tượng khác tham chiếu, cùng có giá trị | Tùy `a.equals(b)` | Ủy quyền cho cách định nghĩa bằng nhau của lớp |

**Phân biệt bản chất:**

- `==` trên hai biến tham chiếu kiểm tra **cùng đối tượng**; `Objects.equals` kiểm tra **bằng nhau theo `equals`** và bổ sung xử lý `null`.
- `Objects.equals` không tự đi qua các trường để so sánh sâu. Nếu kiểu dữ liệu không ghi đè `Object.equals`, hai instance riêng vẫn không bằng nhau.
- `Objects.equals(a, b)` không sửa được một phương thức `a.equals(b)` bị cài đặt sai tính đối xứng hoặc bắc cầu. Nó chỉ làm việc kiểm tra `null` an toàn.

## 3. Ví dụ hoàn chỉnh, chạy được trên Java 17+

Một `ContactProfile` có hai trường nullable (`email`, `displayName`) và một trường nguyên thủy (`priority`). Theo **quy tắc nghiệp vụ của ví dụ**, tất cả ba trường đều tham gia phép so sánh bằng nhau. Đối tượng được giữ bất biến bằng `private final` để an toàn hơn khi dùng làm phần tử `HashSet` hoặc khóa `HashMap`.

Lưu chương trình sau vào **`NullableEqualsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class ContactProfile {
    private final String email;
    private final String displayName;
    private final int priority;

    ContactProfile(String email, String displayName, int priority) {
        this.email = email;
        this.displayName = displayName;
        this.priority = priority;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof ContactProfile that)) {
            return false;
        }

        return priority == that.priority
                && Objects.equals(email, that.email)
                && Objects.equals(displayName, that.displayName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(email, displayName, priority);
    }
}

public class NullableEqualsDemo {
    public static void main(String[] args) {
        ContactProfile a = new ContactProfile("an@example.com", null, 1);
        ContactProfile b = new ContactProfile("an@example.com", null, 1);
        ContactProfile named = new ContactProfile("an@example.com", "An", 1);
        ContactProfile missing1 = new ContactProfile(null, null, 1);
        ContactProfile missing2 = new ContactProfile(null, null, 1);

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(named): " + a.equals(named));
        System.out.println("missing1.equals(missing2): "
                + missing1.equals(missing2));
        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
        System.out.println("Objects.equals(null, \"x\"): "
                + Objects.equals(null, "x"));
        System.out.println("Objects.equals(\"x\", null): "
                + Objects.equals("x", null));

        Set<ContactProfile> profiles = new HashSet<>();
        profiles.add(a);
        profiles.add(b);
        profiles.add(named);
        System.out.println("HashSet size: " + profiles.size());
        System.out.println("Equal objects share hashCode: "
                + (a.hashCode() == b.hashCode()));
    }
}
```

Biên dịch và chạy trong thư mục có tệp trên:

```bash
javac NullableEqualsDemo.java
java NullableEqualsDemo
```

Đầu ra chính xác, không phụ thuộc địa chỉ bộ nhớ hoặc giá trị hash cụ thể:

```text
a.equals(b): true
a.equals(named): false
missing1.equals(missing2): true
a.equals(null): false
Objects.equals(null, null): true
Objects.equals(null, "x"): false
Objects.equals("x", null): false
HashSet size: 2
Equal objects share hashCode: true
```

**Giải thích kết quả:**

1. `a` và `b` là hai instance riêng biệt, nhưng `email`, `displayName` và `priority` đều tương đương. Cụ thể, `Objects.equals(null, null)` cho `true`.
2. `a` và `named` khác nhau tại `displayName`: một phía `null`, phía kia `"An"`. Kết quả là `false`, không có ngoại lệ.
3. `missing1` và `missing2` bằng nhau trong mô hình này vì cả hai trường nullable đều `null` và `priority` bằng nhau. Nếu nghiệp vụ không muốn coi hai hồ sơ thiếu thông tin là bằng nhau, phải thay đổi **quy tắc so sánh của lớp**, thay vì mong `Objects.equals` tự suy luận ý nghĩa `null`.
4. `a.equals(null)` cho `false`, đúng hợp đồng `equals`. Phép kiểm tra `obj instanceof ContactProfile that` an toàn với `null` và không truy cập trường trước khi kiểm tra kiểu.
5. `HashSet` chỉ giữ một trong hai phần tử bằng nhau `a` và `b`, đồng thời giữ `named` vì khác theo `equals`. `HashSet` dựa vào cả `hashCode` và `equals`, nên hai phương thức phải thống nhất.

## 4. Liên hệ với hợp đồng `equals` và `hashCode`

Một phương thức `equals` đúng cần đáp ứng **phản xạ** (`x.equals(x)` là `true`), **đối xứng**, **bắc cầu**, **nhất quán** khi trạng thái không đổi, và `x.equals(null)` là `false`.

Quan hệ bắt buộc với `hashCode` là:

> Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải là `true`.

Chiều ngược lại **không bắt buộc**, vì hai đối tượng khác nhau có thể trùng mã băm. Trong ví dụ, `equals` dùng `email`, `displayName` và `priority`, nên `hashCode` cũng tính theo những trường này bằng `Objects.hash(email, displayName, priority)`.

`Objects.hash` chấp nhận tham chiếu `null`, nhận nhiều đối số qua varargs và trả về một số băm kết hợp. Đừng nhầm với `Objects.hashCode(x)`: phương thức `hashCode(x)` trả về `0` cho `null`, còn khi `x != null` thì trả về `x.hashCode()`; `Objects.hash(x)` dùng thuật toán băm tổng hợp và không nhất thiết bằng `Objects.hashCode(x)` dù chỉ có một đối số.

Sử dụng `Objects.hash` thuận tiện cho value object thông thường; nếu `hashCode` được gọi với tần suất rất cao, varargs và boxing có thể có chi phí, khi đó chỉ nên tối ưu sau khi đo hiệu năng. **Đúng hợp đồng và rõ ràng** là mục tiêu trước tiên.

## 5. Chọn cách so sánh theo loại trường

| Loại dữ liệu | Cách so sánh thích hợp | Lưu ý |
| --- | --- | --- |
| `String`, `Integer`, đối tượng con có thể `null` | `Objects.equals(x, that.x)` | Bên trong vẫn gọi `x.equals` khi `x` có giá trị |
| Kiểu nguyên thủy `int`, `long`, `boolean`, `char` | `==` | Không tồn tại `null`; tránh boxing không cần thiết |
| `float`, `double` | Chọn quy tắc nhất quán, có thể dùng `Float.compare`/`Double.compare` | Chú ý NaN và `-0.0`, đồng bộ với hash |
| Enum | `==` (kể cả khi một bên `null`) hoặc `Objects.equals` | Mỗi hằng enum có danh tính duy nhất |
| Mảng `int[]`, `String[]` | `Arrays.equals` | `Objects.equals` trên mảng thường so sánh tham chiếu, không phải từng phần tử |
| Mảng lồng nhau | `Arrays.deepEquals` | Nếu đưa vào `hashCode`, phối hợp `Arrays.deepHashCode` |

Ví dụ, `Objects.equals(new int[]{1}, new int[]{1})` là `false` vì hai mảng là hai object khác nhau, trong khi `Arrays.equals(new int[]{1}, new int[]{1})` là `true`. Vì thế, `Objects.equals` không phải công cụ so sánh sâu tổng quát.

Với `String`, `Objects.equals("A", "a")` là `false`. Nếu cần không phân biệt hoa thường, phải thiết kế quy tắc chuẩn hóa/so sánh và **`hashCode` tương ứng**; `Objects.equals` không làm thay đổi hành vi `String.equals`.

Đối với lớp Java `record`, compiler tự sinh `equals`/`hashCode` cho các component và xử lý các reference nullable theo ngữ nghĩa thích hợp của record. Tuy nhiên, khi cần viết tay một lớp thông thường, `Objects.equals` vẫn là mẫu cốt lõi cần nắm.

## 6. Các lỗi dễ mắc

- **Dùng `field.equals(other.field)` khi `field` có thể `null`:** phát sinh `NullPointerException`. Với trường tham chiếu cần so sánh theo `equals`, dùng `Objects.equals(field, other.field)`.
- **Dùng `field == other.field` cho `String` hoặc đối tượng giá trị:** đó là so sánh cùng tham chiếu. Nếu muốn bằng nhau theo nội dung, dùng `Objects.equals`.
- **Ghi đè `equals` mà giữ nguyên `Object.hashCode`:** có thể khiến `HashSet`/`HashMap` xử lý sai các đối tượng vốn bằng nhau. Ghi đè cả hai.
- **Đưa vào `hashCode` một trường bị bỏ qua trong `equals`:** có nguy cơ tạo hash khác nhau cho hai đối tượng bằng nhau, vi phạm hợp đồng. Một tập trường băm quá ít phân biệt tuy có thể hợp lệ nhưng gây nhiều va chạm; nên thiết kế các trường nhất quán.
- **Thay đổi trường tham gia `equals`/`hashCode` sau khi đặt đối tượng làm key của `HashMap`:** khóa có thể không tra cứu được nữa. Ưu tiên value object bất biến.
- **Cho rằng mọi hai giá trị `null` đều phải bằng nhau theo nghiệp vụ:** `Objects.equals(null, null)` luôn `true`, nhưng nghiệp vụ có thể cần tiêu chí khác (ví dụ ID không được vắng); kiểm tra hoặc chuẩn hóa dữ liệu từ lúc tạo đối tượng.
- **Quên chiến lược kế thừa:** lớp con thêm trường so sánh có thể làm hỏng tính đối xứng so với lớp cha. Ví dụ dùng `final class` để xác định rõ phạm vi so sánh; với phân cấp mở rộng cần thiết kế riêng.
- **Cho rằng `Objects.equals` sửa được `equals` sai trong một đối tượng lồng nhau:** nó chỉ chuyển việc so sánh cho `a.equals(b)` sau khi xử lý `null`.

## 7. Checklist tự đánh giá

Trước khi hoàn tất `equals` có trường nullable, nên thử các tình huống: (1) hai trường đều `null`; (2) bên trái `null`, bên phải có giá trị; (3) bên trái có giá trị, bên phải `null`; (4) hai đối tượng con khác tham chiếu nhưng bằng nhau theo `equals`; (5) hai đối tượng con khác nhau về giá trị. Tiếp đó xác minh `x.equals(null)` là `false`, `a.equals(b) == b.equals(a)`, và các cặp đối tượng bằng nhau có cùng `hashCode`.

**Ghi nhớ:** khi đã kiểm tra đúng kiểu của `other`, dùng **`Objects.equals(this.field, that.field)`** cho trường tham chiếu nullable, dùng `==` cho phần lớn kiểu nguyên thủy, và cài đặt `hashCode` nhất quán với những trường quyết định `equals`. `Objects.equals` làm phép so sánh an toàn với `null`; quy tắc bằng nhau của toàn đối tượng vẫn do lớp định nghĩa.
