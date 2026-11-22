# Hai đối tượng độc lập có thể biểu diễn cùng giá trị

Trong Java, **danh tính đối tượng (object identity)** và **giá trị mà đối tượng biểu diễn (value)** là hai khái niệm khác nhau. Hai đối tượng được tạo độc lập có thể chứa cùng dữ liệu và có cùng ý nghĩa trong bài toán, nhưng chúng vẫn là hai đối tượng riêng biệt. Vì vậy, câu hỏi “có phải cùng một đối tượng không?” và “có biểu diễn cùng giá trị không?” phải được trả lời bằng hai cách kiểm tra khác nhau.

## 1. Phân biệt danh tính, tham chiếu và giá trị

- **Đối tượng** là thực thể được tạo trong lúc chương trình chạy. Mỗi lần biểu thức `new` tạo thành công một đối tượng mới, đối tượng đó có danh tính riêng.
- **Tham chiếu (reference)** là giá trị mà biến kiểu tham chiếu giữ để trỏ tới đối tượng. Hai biến có thể giữ tham chiếu đến **cùng một đối tượng**; đó là hai tên gọi (alias) cho cùng một thực thể.
- **Trạng thái** là các dữ liệu bên trong đối tượng. Hai đối tượng khác nhau có thể có trạng thái trùng nhau.
- **Bằng nhau về giá trị** phụ thuộc định nghĩa của kiểu dữ liệu: đối với một tọa độ có thể là cùng `x, y`; đối với số tiền có thể là cùng lượng tiền và đơn vị tiền tệ. Trong Java, phương thức `equals(Object)` thường thể hiện định nghĩa đó, **nếu kiểu dữ liệu đã cài đặt phù hợp**.

| Cách kiểm tra | Ý nghĩa đối với tham chiếu đối tượng |
| --- | --- |
| `a == b` | Hai tham chiếu có đang trỏ tới đúng **một đối tượng** không? |
| `a.equals(b)` | Theo cách triển khai `equals` của kiểu `a`, hai đối tượng có được coi là bằng nhau không? |
| `Objects.equals(a, b)` | Kiểm tra bằng nhau an toàn khi một hoặc cả hai tham chiếu có thể là `null`; nếu đều khác `null`, dùng `a.equals(b)`. |

**Giới hạn cần nhớ:** với các kiểu nguyên thủy như `int`, toán tử `==` so sánh giá trị; cách diễn giải về danh tính ở bảng trên áp dụng cho **tham chiếu đến đối tượng**. Đừng nhầm tham chiếu hoặc kết quả `==` với địa chỉ bộ nhớ có thể quan sát hay quản lý trực tiếp.

## 2. Thử nghiệm: cùng giá trị, khác đối tượng

Tệp **`IdentityAndValueDemo.java`**, chạy được trên Java 17+:

~~~java
import java.util.Objects;

public class IdentityAndValueDemo {
    record Point(int x, int y) {}

    static final class Label {
        private final String text;

        Label(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
        System.out.println(first.hashCode() == second.hashCode());

        Label left = new Label("Java");
        Label right = new Label("Java");
        System.out.println(left == right);
        System.out.println(left.equals(right));
        System.out.println(Objects.equals(left.text, right.text));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IdentityAndValueDemo.java
java IdentityAndValueDemo
~~~

Kết quả chuẩn:

~~~text
false
true
true
true
false
false
true
~~~

Giải thích theo thứ tự:

1. `first` và `second` đến từ **hai lần `new Point(...)`** nên `first == second` là `false`, dù cả hai chứa tọa độ `(2, 3)`.
2. `Point` là **record**. Với thành phần `int x, int y`, phương thức `equals` được sinh tự động so sánh giá trị các thành phần; kết quả `true`. Record cũng sinh `hashCode` phù hợp với `equals`, nên hai giá trị bằng nhau phải có mã băm bằng nhau.
3. `alias = first` sao chép **tham chiếu**; không tạo đối tượng thứ ba. Do đó `first == alias` là `true`.
4. `Label` là class bình thường **không override `equals`**. Nó kế thừa `Object.equals`, vốn so sánh danh tính. Vì vậy hai `Label` độc lập vẫn `equals` trả `false`, mặc dù hai trường `text` có nội dung bằng nhau.
5. `Objects.equals(left.text, right.text)` dùng ngữ nghĩa `String.equals`: hai chuỗi có cùng nội dung thì bằng nhau. Điều này **không biến** hai đối tượng `Label` thành một.

Bài học quan trọng: **cùng dữ liệu không tự động làm cho hai instance bằng nhau theo `equals`**. Kết quả tùy hợp đồng của kiểu dữ liệu. Và **`equals` trả `true` không làm hai instance trở thành cùng một đối tượng**.

## 3. Vì sao `Object.equals` mặc định chưa diễn đạt “cùng giá trị”?

Mọi class đều kế thừa `java.lang.Object`. Nếu không override, `Object.equals` thực hiện kiểm tra tương đương với `this == obj`. Vì thế:

- Class có thể có hai instance độc lập và tất cả trường đều giống nhau, nhưng `equals` mặc định vẫn trả `false`.
- `String`, các lớp wrapper như `Integer`, nhiều lớp thư viện như `List`, và record có cách định nghĩa `equals` theo giá trị/nội dung thích hợp cho từng kiểu.
- Một class định nghĩa **đối tượng thực thể (entity)** cũng có thể cố ý giữ ngữ nghĩa danh tính, hoặc định nghĩa bằng nhau theo mã định danh nghiệp vụ. Không tồn tại quy tắc “cứ so tất cả trường là đúng” cho mọi miền dữ liệu.

Chẳng hạn, hai bản ghi `Customer` có tên giống nhau chưa chắc là một khách hàng; ngược lại hai đối tượng `Money(100, "VND")` có thể hợp lý khi xem là cùng giá trị. Phải quyết định rõ trường nào cấu thành **giá trị có ý nghĩa**, rồi mới triển khai `equals`.

## 4. Tạo value object tự định nghĩa: `equals` đi cùng `hashCode`

Khi muốn hai đối tượng độc lập có cùng dữ liệu được xem là bằng nhau, ta có thể tự override `equals` và `hashCode`. Ví dụ một value object chỉ dùng hai thành phần bất biến là `amount` và `currency`.

Tệp **`MoneyDemo.java`**, chạy được trên Java 17+:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MoneyDemo {
    static final class Money {
        private final long amount;
        private final String currency;

        Money(long amount, String currency) {
            this.amount = amount;
            this.currency = Objects.requireNonNull(currency);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Money that)) {
                return false;
            }
            return amount == that.amount && currency.equals(that.currency);
        }

        @Override
        public int hashCode() {
            return Objects.hash(amount, currency);
        }
    }

    public static void main(String[] args) {
        Money first = new Money(100, "VND");
        Money second = new Money(100, "VND");
        Money third = new Money(200, "VND");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(third));
        System.out.println(first.hashCode() == second.hashCode());

        Set<Money> values = new HashSet<>();
        values.add(first);
        values.add(second);
        values.add(third);
        System.out.println(values.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MoneyDemo.java
java MoneyDemo
~~~

Kết quả chuẩn:

~~~text
false
true
false
true
2
~~~

Ở đây, `first` và `second` là hai đối tượng khác nhau nhưng cùng biểu diễn “100 VND”, nên `equals` là `true`. `third` biểu diễn “200 VND” nên không bằng hai đối tượng kia. `HashSet` chỉ giữ **hai giá trị phân biệt** theo hợp đồng `equals` và `hashCode`.

Để đọc cách cài đặt:

- `this == other` trả kết quả sớm khi hai tham chiếu chỉ tới cùng instance.
- `instanceof Money that` xác nhận đối tượng bên phải thuộc kiểu mong đợi và tạo biến `that` (pattern matching của Java 17).
- Phần so sánh `amount` và `currency` là **quyết định về giá trị**: cùng số lượng nhưng khác tiền tệ thì không bằng nhau.
- `hashCode` tính từ **chính các trường dùng trong `equals`**; nếu hai đối tượng bằng nhau thì mã băm bắt buộc bằng nhau.

Ví dụ cố ý dùng class `final` và các trường `private final` để giá trị sau khi tạo không thay đổi. Điều này giúp `equals` ổn định hơn khi đối tượng được đưa vào cấu trúc dữ liệu dựa trên hash. Trong dự án thật còn cần làm rõ chuẩn hóa `currency`, đơn vị của `amount` và quy tắc nghiệp vụ; chúng không được Java tự quyết định thay lập trình viên.

## 5. Hợp đồng của `equals` và `hashCode`

Khi override `equals`, Java yêu cầu tuân thủ các tính chất sau (giả sử trạng thái tham gia so sánh không thay đổi trong khoảng kiểm tra):

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ | `x.equals(x)` là `true` với `x != null`. |
| Đối xứng | `x.equals(y)` và `y.equals(x)` phải cho cùng kết quả. |
| Bắc cầu | Nếu `x.equals(y)` và `y.equals(z)` là `true` thì `x.equals(z)` phải là `true`. |
| Nhất quán | Khi dữ liệu liên quan không đổi, gọi lại `x.equals(y)` phải cho cùng kết quả. |
| So với null | `x.equals(null)` phải là `false` với `x != null`. |

Quy tắc hash then chốt: **`x.equals(y) == true` thì `x.hashCode() == y.hashCode()`**. Chiều ngược lại **không đúng**: hai đối tượng không bằng nhau vẫn có thể trùng mã băm (hash collision). `hashCode` không phải mã nhận diện duy nhất. Tương tự, `System.identityHashCode(obj)` là một mã băm theo danh tính, **không đảm bảo duy nhất** và không phải địa chỉ bộ nhớ.

Nếu chỉ override `equals` mà bỏ qua `hashCode`, `HashSet` có thể giữ hai phần tử lẽ ra coi là trùng; `HashMap` có thể không tìm ra key có giá trị bằng nhau. Nếu viết class biểu diễn giá trị, hãy kiểm tra cả hai phương thức và các cấu trúc dữ liệu tiêu thụ chúng.

## 6. Các trường hợp dễ gây nhầm

### `String`: giá trị là nội dung, không phải cùng tham chiếu

~~~java
String a = new String("java");
String b = new String("java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Hai lệnh `new` cố ý tạo hai đối tượng khác nhau; `String.equals` so sánh chuỗi ký tự. Trong code thường ngày không cần chủ động tạo `new String(...)` như vậy. Hai literal có thể trỏ cùng chuỗi nhờ **string pool**, nên kết quả `==` đôi khi là `true`; đó không phải lý do dùng `==` để kiểm tra nội dung chuỗi.

### Mảng: `equals` mặc định không so sánh từng phần tử

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(a == b);                // false
System.out.println(a.equals(b));           // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Mảng không override `Object.equals` để so sánh nội dung. Với mảng một chiều nguyên thủy, dùng `Arrays.equals` khi muốn so phần tử; với mảng lồng nhau cần xem xét `Arrays.deepEquals`. Record có trường kiểu mảng cũng **không tự động so nội dung mảng** trong `equals` được sinh: trường mảng vẫn có ngữ nghĩa so sánh tham chiếu trừ khi tự thiết kế cách so sánh khác.

### “Cùng giá trị” là quy ước của từng kiểu

`new java.math.BigDecimal("1.0")` và `new java.math.BigDecimal("1.00")` có giá trị số học tương đương theo `compareTo(...) == 0`, nhưng `BigDecimal.equals` trả `false` vì xét cả **scale**. Đừng mặc định rằng “trông giống nhau”, “số học tương đương” và “`equals` bằng nhau” luôn là một.

### Cùng đối tượng có thể đổi trạng thái

Nếu `alias = original` rồi gọi phương thức làm thay đổi trạng thái trên `alias`, `original` cũng quan sát được thay đổi, vì cả hai tham chiếu đến cùng instance. `original == alias` vẫn là `true`. Ngược lại, hai đối tượng đang bằng nhau theo giá trị có thể **không còn bằng nhau** sau khi một đối tượng bị sửa trường tham gia `equals`.

Đặc biệt, tránh sửa những trường ảnh hưởng `equals`/`hashCode` của đối tượng **đang là key trong `HashMap` hoặc phần tử của `HashSet`**. Nếu mã băm đổi sau khi lưu, thao tác tìm/kiểm tra/xóa có thể cho kết quả ngoài mong đợi. Ưu tiên đối tượng giá trị bất biến.

## 7. Cách áp dụng khi lập trình

1. Xác định câu hỏi thực tế: cần biết **cùng instance**, hay **cùng giá trị theo nghiệp vụ**?
2. Khi cần danh tính/tham chiếu (ví dụ xác minh hai biến trỏ tới một đối tượng), dùng `==`.
3. Khi cần bằng nhau về nội dung/giá trị, dùng `equals` đúng theo hợp đồng của kiểu; khi tham chiếu có thể `null`, cân nhắc `Objects.equals(a, b)`.
4. Khi tự tạo value object, xác định các trường tham gia bằng nhau, override **cả `equals` và `hashCode`**, rồi kiểm tra các tình huống bằng nhau, khác nhau, `null` và dùng trong `HashSet`/`HashMap`.
5. Khi phù hợp với mô hình dữ liệu, cân nhắc **record** để nhận sẵn ngữ nghĩa giá trị của các thành phần; vẫn phải hiểu hạn chế với thành phần có thể thay đổi, nhất là mảng.
6. Tránh dùng riêng `hashCode`, `identityHashCode`, địa chỉ suy đoán hoặc kết quả `toString` để kết luận hai đối tượng “là một” hay “bằng nhau”.

**Tự kiểm tra:** Với `Point p = new Point(2, 3);` và `Point q = new Point(2, 3);`, vì sao `p == q` là `false` nhưng `p.equals(q)` là `true`? Nếu viết `Point r = p;`, kết quả `p == r` đổi thế nào? Nếu thay `Point` bằng class không override `equals`, kết quả phép so sánh giá trị sẽ ra sao?

**Ghi nhớ:** *Hai đối tượng có thể khác danh tính nhưng bằng giá trị. Danh tính do tham chiếu và toán tử `==` phản ánh; bằng nhau về giá trị phải dựa trên hợp đồng `equals` của kiểu dữ liệu, cùng với `hashCode` nhất quán khi dùng collection dựa trên hash.*