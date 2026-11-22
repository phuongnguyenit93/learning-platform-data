# Kiểm tra `null` và kiểu đối tượng trước khi đọc dữ liệu trong `equals()`

## Mục tiêu

Khi ghi đè `equals(Object obj)`, đối số có kiểu khai báo là `Object`: lời gọi có thể truyền vào một đối tượng cùng kiểu, đối tượng thuộc kiểu khác hoặc `null`. Vì thế, trước khi đọc các trường của đối số và so sánh dữ liệu, cần bảo đảm rằng đối số **khác `null` và thuộc kiểu phù hợp**. Sau bài học, bạn sẽ:

- Giải thích vì sao truy cập trường hoặc ép kiểu quá sớm gây `NullPointerException` hoặc `ClassCastException`.
- Viết đúng thứ tự kiểm tra tham chiếu, `null` và kiểu trước khi đọc dữ liệu trong `equals()`.
- Phân biệt hai cách kiểm tra bằng `getClass()` và `instanceof`, biết tác động của kế thừa đối với tính đối xứng.
- Dùng `Objects.equals()` để so sánh các trường tham chiếu có thể `null`, nhưng không nhầm nó với bước kiểm tra kiểu của đối số.
- Kiểm chứng `equals()` trên cùng tham chiếu, hai đối tượng cùng dữ liệu, `null`, kiểu khác và dữ liệu khác.

## 1. Vì sao cần kiểm tra trước khi đọc trường?

Phương thức được ghi đè đúng chữ ký là:

```java
@Override
public boolean equals(Object obj) {
    // Quyết định đối tượng hiện tại có bằng obj hay không.
}
```

`obj` có kiểu khai báo `Object`. Trình biên dịch không thể giả định rằng `obj` luôn thuộc lớp đang cài đặt `equals()`. Chẳng hạn, một đối tượng `Contact` hoàn toàn có thể nhận lời gọi `contact.equals("hello")` hoặc `contact.equals(null)`; việc so sánh phải trả về `false` theo hợp đồng `equals` trong hai tình huống này.

Đoạn dưới đây **sai và chỉ minh họa lỗi**, không phải phương thức để sử dụng:

```java
@Override
public boolean equals(Object obj) {
    Contact other = (Contact) obj;       // Ép kiểu trước khi kiểm tra
    return id == other.id;               // Đọc dữ liệu ngay lập tức
}
```

Có hai rủi ro độc lập:

1. Nếu `obj` là đối tượng không thể ép sang `Contact` (ví dụ `String`), phép ép kiểu ném `ClassCastException`.
2. Nếu `obj == null`, phép ép `(Contact) null` vẫn cho ra `null`; lỗi xuất hiện khi dùng `other.id`, gây `NullPointerException`.

Một cách viết sai khác là gọi `obj.getClass()` ngay lập tức. Nếu `obj` là `null`, lời gọi phương thức trên `null` gây `NullPointerException`.

**Nguyên tắc:** `equals()` không nên ném lỗi chỉ vì đối số là `null` hoặc thuộc kiểu không liên quan. Hãy xác nhận điều kiện hợp lệ trước khi truy cập dữ liệu đặc thù của lớp.

## 2. Thứ tự kiểm tra an toàn với `getClass()`

Mẫu phổ biến, phù hợp khi chính sách bằng nhau đòi hỏi **đúng cùng lớp chạy thực tế**, là:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (obj == null || getClass() != obj.getClass()) {
        return false;
    }

    Contact other = (Contact) obj;  // Ép kiểu an toàn sau khi đã kiểm tra
    return id == other.id
            && java.util.Objects.equals(email, other.email);
}
```

Trình tự giải thích:

1. **`this == obj`:** cùng tham chiếu thì là cùng đối tượng, trả về `true` ngay; đây là phép tối ưu phổ biến và thể hiện tính phản xạ (`x.equals(x)` phải là `true` với đối tượng khác `null`).
2. **`obj == null`:** đối số không tồn tại thì trả về `false`. Bản thân `this` không thể là `null` khi một phương thức instance đang thực thi hợp lệ.
3. **`getClass() != obj.getClass()`:** từ chối đối tượng có lớp chạy thực tế khác, kể cả các lớp khác có trường tên giống nhau.
4. **Ép kiểu `(Contact) obj`:** sau khi vượt qua bước kiểm tra lớp, ta có thể sử dụng kiểu `Contact` để đọc trường.
5. **So sánh dữ liệu:** với `id` kiểu `int`, dùng `==` để so sánh giá trị nguyên thủy; với `email` kiểu `String` có thể `null`, dùng `Objects.equals` để so sánh nội dung an toàn với `null`.

Biểu thức `obj == null || getClass() != obj.getClass()` dựa vào cơ chế **short-circuit** (`||`): khi vế trái là `true`, Java **không đánh giá** vế phải. Nhờ đó, `obj.getClass()` chỉ được gọi khi `obj` chắc chắn không phải `null`.

Dòng ép kiểu chỉ an toàn vì điều kiện phía trước đã bảo đảm đối số có đúng lớp cần thiết. Nếu thay đổi điều kiện kiểm tra kiểu, phải xem lại cả tính hợp lệ của phép ép kiểu.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu vào tệp `EqualityGuardsDemo.java`. Lớp `Contact` được khai báo `final`, có hai trường dữ liệu, ghi đè cả `equals` lẫn `hashCode`.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityGuardsDemo {
    static final class Contact {
        private final int id;
        private final String email;

        Contact(int id, String email) {
            this.id = id;
            this.email = email;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }

            Contact other = (Contact) obj;
            return id == other.id
                    && Objects.equals(email, other.email);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, email);
        }
    }

    public static void main(String[] args) {
        Contact a = new Contact(7, "a@example.com");
        Contact b = new Contact(7, "a@example.com");
        Contact c = new Contact(7, "b@example.com");
        Contact n1 = new Contact(9, null);
        Contact n2 = new Contact(9, null);

        System.out.println("same reference: " + a.equals(a));
        System.out.println("same values: " + a.equals(b));
        System.out.println("null candidate: " + a.equals(null));
        System.out.println("other type: " + a.equals("7"));
        System.out.println("different email: " + a.equals(c));
        System.out.println("both email null: " + n1.equals(n2));

        Set<Contact> contacts = new HashSet<>();
        contacts.add(a);
        contacts.add(b);
        System.out.println("HashSet size: " + contacts.size());
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac EqualityGuardsDemo.java
java EqualityGuardsDemo
```

Kết quả:

```text
same reference: true
same values: true
null candidate: false
other type: false
different email: false
both email null: true
HashSet size: 1
```

Giải thích kết quả:

- `a.equals(a)` trả về `true` ngay từ kiểm tra cùng tham chiếu.
- `a.equals(b)` trả về `true` vì hai đối tượng khác nhau nhưng cùng `id` và `email`. Điều này khác với phép `a == b`, vốn là `false`.
- `a.equals(null)` trả về `false` ở bước kiểm tra `null`.
- `a.equals("7")` trả về `false` ở bước kiểm tra lớp; không cố ép `String` thành `Contact`.
- `a.equals(c)` trả về `false` vì `email` khác nhau.
- `n1.equals(n2)` trả về `true` vì hai đối tượng có `id` bằng nhau và hai giá trị `email` đều là `null`; `Objects.equals(null, null)` trả về `true`.
- `HashSet` chỉ giữ một phần tử từ `a` và `b` vì `equals` xác định chúng bằng nhau và `hashCode` nhất quán.

Ví dụ cố ý dùng `final class Contact`, nên không có lớp con của `Contact` khiến quy tắc kiểm tra kiểu thêm phức tạp.

## 4. Một cách khác: `instanceof` và pattern matching

Với Java 17+, có thể gộp kiểm tra `null`, kiểm tra kiểu và tạo biến đúng kiểu bằng **pattern matching for `instanceof`**:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Contact other)) {
        return false;
    }
    return id == other.id
            && java.util.Objects.equals(email, other.email);
}
```

Đây là **một phương án thay thế** cho phần thân `equals` của lớp `Contact` trong ví dụ trước, không phải chương trình Java độc lập.

Biểu thức `obj instanceof Contact other` chỉ thành công nếu `obj` không phải `null` và đối tượng tương thích với `Contact`. Trong nhánh còn lại sau lệnh `return false`, biến `other` có kiểu `Contact` và được trình biên dịch bảo đảm đã gán phù hợp. Không cần gọi `getClass()`, không cần ép kiểu tường minh và không cần viết thêm `obj != null`.

Với lớp `Contact` khai báo `final` ở ví dụ trên, hai chiến lược đều chấp nhận các đối tượng cùng lớp và từ chối `null` hoặc kiểu khác. Nhưng nếu lớp **có thể được kế thừa**, hai chiến lược không còn cùng chính sách:

- `getClass() == obj.getClass()` yêu cầu **đúng một lớp chạy thực tế**. Đối tượng lớp cha và đối tượng lớp con sẽ bị xem là khác nhau, kể cả khi lớp con kế thừa mọi trường.
- `obj instanceof Base` chấp nhận đối tượng kiểu `Base` **và lớp con** của `Base`. Điều này có thể hữu ích nếu mọi đối tượng trong phân cấp thật sự cùng tuân theo một định nghĩa bằng nhau.
- Nếu lớp con bổ sung trường hoặc viết `equals` với quy tắc khác lớp cha, dùng `instanceof` thiếu cân nhắc có thể phá vỡ **tính đối xứng** hoặc **tính bắc cầu** của `equals`.

Ví dụ về rủi ro thiết kế (mã giả minh họa, không phải Java runnable độc lập): nếu lớp cha `Base.equals(child)` chỉ kiểm tra trường `id`, còn `Child.equals(base)` yêu cầu bên kia cũng là `Child`, có thể xảy ra `base.equals(child) == true` nhưng `child.equals(base) == false`. Đây là vi phạm hợp đồng `equals`.

Vì thế, chọn giữa `getClass` và `instanceof` là lựa chọn **chính sách bằng nhau của cả hệ phân cấp**, không đơn thuần là khác biệt về cú pháp. Với lớp giá trị bất biến `final`, hai cách thường đơn giản và dễ lý giải. Với thực thể có proxy hoặc mô hình kế thừa đặc biệt, hãy xem xét hợp đồng bằng nhau dành riêng cho kiểu và thư viện đang dùng.

### Java trước khi có pattern matching

Mã cổ điển cũng kiểm tra an toàn bằng `instanceof` rồi mới ép kiểu:

```java
if (!(obj instanceof Contact)) {
    return false;
}
Contact other = (Contact) obj;
// Chỉ đọc other.id, other.email sau bước này.
```

Đây là đoạn thân phương thức minh họa. Đối với `null`, phép `instanceof` trả về `false`, nên không cần một lệnh `obj == null` riêng trong nhánh này.

## 5. Tránh nhầm “đối số không `null`” với “trường bên trong không `null`”

Kiểm tra `obj != null` chỉ bảo đảm chính **đối tượng đối số** tồn tại. Sau khi ép kiểu hợp lệ, các trường tham chiếu bên trong vẫn có thể là `null`.

Ví dụ, với đối tượng `Contact` có `email == null`, câu lệnh sau không an toàn:

```java
return email.equals(other.email); // email == null gây NullPointerException
```

Các cách xử lý tùy hợp đồng của trường:

- Nếu `email` có thể `null` và hai giá trị `null` được xem là bằng nhau: `Objects.equals(email, other.email)`.
- Nếu `email` bắt buộc khác `null`: kiểm tra điều kiện ở constructor bằng `Objects.requireNonNull(email)` rồi duy trì invariant ấy; sau đó có thể gọi `email.equals(other.email)`.
- Nếu cần so sánh phần tử mảng: cân nhắc `Arrays.equals` hoặc `Arrays.deepEquals` đúng cấu trúc dữ liệu. `Objects.equals` trên hai mảng vẫn sử dụng `equals()` mặc định của mảng, tức là so sánh danh tính mảng.

`Objects.equals(a, b)` hoạt động tương đương về ý nghĩa với `a == b || (a != null && a.equals(b))`. Phương thức này **không kiểm tra trước** rằng hai đối tượng là kiểu mong muốn cho mã cài đặt `equals` của bạn, cũng không tự chọn tiêu chí bằng nhau cho các trường. Nó chỉ hỗ trợ so sánh hai giá trị có thể `null`.

Chú ý phân biệt hai lời gọi:

```java
Contact contact = null;

// contact.equals(new Contact(1, null)); // Ném NullPointerException
boolean safe = java.util.Objects.equals(
        contact, new Contact(1, null));   // false
```

Đây là đoạn minh họa cần đặt trong phương thức có thể truy cập lớp `Contact`. Khi bên trái `equals` là `null`, bạn không thể gọi phương thức instance. Nhưng vẫn có thể dùng `Objects.equals` để so sánh hai biến tham chiếu có thể `null`.

## 6. Vì sao thứ tự điều kiện quan trọng?

Hãy xét ba cách viết trong thân `equals(Object obj)`, với lớp hiện tại là `Contact`:

| Cách kiểm tra | Khi `obj == null` | Khi `obj` là kiểu khác | Kết luận |
| --- | --- | --- | --- |
| `obj == null || getClass() != obj.getClass()` | Vế phải không chạy; trả về `false` | Trả về `false` khi khác lớp | An toàn |
| `!(obj instanceof Contact)` | `instanceof` cho `false`; trả về `false` | Trả về `false` | An toàn; chính sách nhận lớp con khác `getClass` |
| `getClass() != obj.getClass() || obj == null` | Ném `NullPointerException` trước khi đến kiểm tra `null` | Có thể trả về `false` | Sai thứ tự |
| `Contact other = (Contact) obj;` rồi đọc trường | Có thể ném `NullPointerException` khi đọc trường | Có thể ném `ClassCastException` ngay lúc ép kiểu | Thiếu kiểm tra |

Đôi khi người học thêm điều kiện thừa:

```java
if (obj != null && obj instanceof Contact other) {
    // ...
}
```

Điều kiện này hợp lệ, nhưng `obj != null` là **không cần thiết**, vì `null instanceof Contact` vốn đã là `false`. Khi yêu cầu đơn giản là chống `null` và sai kiểu, một mẫu `instanceof` rõ ràng là đủ. Tuy nhiên, đừng chỉ dùng `obj != null` rồi ép kiểu: kiểm tra tồn tại không chứng minh được đối tượng thuộc đúng lớp.

## 7. Đặt bước kiểm tra vào hợp đồng `equals()`

Một triển khai `equals` đúng cần tuân theo các tính chất chính cho các tham chiếu khác `null`:

1. **Phản xạ:** `x.equals(x)` phải là `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` phải cho cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều `true` thì `x.equals(z)` cũng phải `true`.
4. **Nhất quán:** khi các thông tin tham gia so sánh không đổi, kết quả của các lần gọi lặp lại phải ổn định.
5. **Không bằng `null`:** `x.equals(null)` phải là `false`.

Kiểm tra `this == obj` giúp tối ưu trường hợp phản xạ; kiểm tra `null` và kiểu giúp thực thi yêu cầu thứ năm và xử lý đối số sai kiểu. Nhưng **chúng chưa đủ để bảo đảm toàn bộ hợp đồng**: biểu thức so sánh trường và chính sách với lớp con cũng phải được thiết kế nhất quán.

Khi ghi đè `equals`, thường phải ghi đè `hashCode` để bảo đảm: nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc. Đây là lý do ví dụ hoàn chỉnh ghi đè `hashCode` dựa trên chính `id` và `email` được dùng trong `equals`.

Đối với dữ liệu dùng làm khóa trong `HashMap` hay phần tử của `HashSet`, nên ưu tiên các trường bất biến dùng để tính `equals/hashCode`. Nếu các trường này thay đổi sau khi thêm vào bộ sưu tập dựa trên hash, việc tìm kiếm hoặc xóa phần tử có thể gặp kết quả khó hiểu.

## 8. Kiểm tra kiểu bằng `getClass()` không thay thế cho xác định quy tắc bằng nhau

Hai đối tượng đúng cùng lớp chưa chắc bằng nhau. Ví dụ:

```java
Contact first = new Contact(5, "a@example.com");
Contact second = new Contact(5, "b@example.com");

// first.getClass() == second.getClass() là true,
// nhưng first.equals(second) phải là false theo quy tắc id + email.
```

Đoạn trên là mã minh họa đặt trong phạm vi truy cập `Contact`. Kiểm tra kiểu chỉ cho phép chương trình **tiến đến bước đọc trường một cách an toàn**. Quyết định kết quả cuối cùng nằm ở các trường nào cấu thành tính bằng nhau.

Ngược lại, các đối tượng khác lớp không nhất thiết phải có cùng tên trường hoặc cấu trúc dữ liệu. Đừng cố ép hoặc dùng reflection để đọc trường của một đối tượng khác kiểu chỉ nhằm “so sánh được”; một `equals` thông thường nên biểu đạt đúng hợp đồng của lớp đang cài đặt.

**Về đối tượng ủy quyền (proxy):** Một số framework có thể tạo lớp con động cho đối tượng nghiệp vụ. Khi đó, điều kiện `getClass() != obj.getClass()` có thể từ chối so sánh với proxy, dù về mặt nghiệp vụ người viết mong hai đối tượng tương đương. Vấn đề cần giải quyết ở **thiết kế hợp đồng equals của kiểu/framework cụ thể**, không thể chữa bằng cách xóa mọi bước kiểm tra kiểu.

## 9. Các lỗi thường gặp

**Lỗi 1 — Ép kiểu trước khi kiểm tra.** Dòng `Contact other = (Contact) obj` ở đầu phương thức có thể ném `ClassCastException`. Hãy kiểm tra kiểu rồi mới ép.

**Lỗi 2 — Chạm vào `obj` trước khi kiểm tra `null`.** `obj.getClass()` hoặc `obj.toString()` sẽ ném `NullPointerException` khi đối số vắng mặt. Đặt `obj == null` trước, hoặc dùng `instanceof` để bao quát trường hợp `null`.

**Lỗi 3 — Chỉ kiểm tra `null` mà bỏ qua kiểu.** `obj != null` không bảo đảm `obj` có thể ép sang lớp mong muốn.

**Lỗi 4 — Kiểm tra kiểu xong rồi gọi `equals()` trên trường có thể `null`.** Đối số hợp lệ không có nghĩa tất cả trường đều hợp lệ để gọi phương thức. Dùng `Objects.equals` hoặc kiểm soát invariant ở constructor.

**Lỗi 5 — Thêm phương thức `equals(Contact other)` thay vì ghi đè `equals(Object obj)`.** Đây là **overload**, không phải override; bộ sưu tập Java vẫn dùng `equals(Object)`. Dùng `@Override` và đúng chữ ký để trình biên dịch phát hiện sai sót.

**Lỗi 6 — Tùy tiện thay `getClass()` bằng `instanceof` trong phân cấp lớp.** Hai cách có chính sách kế thừa khác nhau. Xem xét tính đối xứng và bắc cầu trước khi quyết định.

**Lỗi 7 — Ghi đè `equals` mà quên `hashCode`.** Những đối tượng bằng nhau theo `equals` có thể hoạt động sai trong các cấu trúc dựa trên hash nếu `hashCode` không nhất quán.

## 10. Bài tập tự kiểm tra

Giả sử `Contact` là lớp `final` và `equals()` được cài đặt theo ví dụ ở phần 3. Dự đoán kết quả:

```java
Contact a = new Contact(1, "x@example.com");
Contact b = new Contact(1, "x@example.com");
Contact c = new Contact(1, null);
Contact d = new Contact(1, null);
Object other = "x@example.com";

boolean q1 = a.equals(a);
boolean q2 = a.equals(b);
boolean q3 = a.equals(null);
boolean q4 = a.equals(other);
boolean q5 = c.equals(d);
boolean q6 = a == b;
```

Đoạn mã trên được đặt trong một phương thức có thể truy cập `Contact`.

**Đáp án:** `q1 = true` (cùng tham chiếu); `q2 = true` (cùng kiểu và các trường có cùng giá trị); `q3 = false` (đối số `null`); `q4 = false` (khác kiểu); `q5 = true` (`id` bằng nhau và hai `email` đều `null`); `q6 = false` (hai lệnh `new` tạo hai đối tượng khác nhau).

Thử thêm hai thay đổi:

- Bỏ kiểm tra `obj == null` khỏi mẫu dùng `getClass()` và gọi `a.equals(null)`: lỗi sẽ phát sinh khi gọi `obj.getClass()`.
- Thay `Objects.equals(email, other.email)` bằng `email.equals(other.email)` rồi gọi `c.equals(d)`: lỗi sẽ phát sinh vì `c.email == null`.

Hai thay đổi này phân biệt rõ **an toàn của đối số** với **an toàn của trường được so sánh**. Chúng là hai trách nhiệm khác nhau trong một triển khai `equals`.

## Ghi nhớ

Trong `equals(Object obj)`, thứ tự an toàn là: **kiểm tra cùng tham chiếu → loại `null` và kiểu không phù hợp → ép kiểu khi cần → đọc và so sánh các trường**. Với Java 17+, pattern matching cho `instanceof` có thể gộp bước loại `null`, xác minh kiểu và tạo biến đúng kiểu. Chọn `getClass()` hay `instanceof` dựa trên hợp đồng bằng nhau và chính sách kế thừa; sau cùng, bảo đảm so sánh trường an toàn với `null` và `hashCode` phù hợp.