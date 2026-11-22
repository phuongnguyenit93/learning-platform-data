# `Objects.equals()` xử lý `null` và ủy quyền tới `equals()`

## Mục tiêu bài học

`java.util.Objects.equals(Object a, Object b)` là một tiện ích nhỏ nhưng rất thường gặp khi viết Java. Phương thức này giúp so sánh hai tham chiếu **mà không phải tự kiểm tra xem tham chiếu nhận lời gọi `equals()` có phải `null` hay không**. Khi hai đối tượng đều tồn tại và không cùng tham chiếu, kết quả được quyết định bởi phương thức `equals()` của **đối số thứ nhất**.

Học xong bài này, bạn có thể:

- Dự đoán kết quả `Objects.equals(a, b)` khi một hoặc cả hai đối số là `null`.
- Giải thích việc kiểm tra `a == b` trước và cơ chế ngắn mạch trước khi gọi `a.equals(b)`.
- Phân biệt so sánh danh tính bằng `==` với so sánh logic bằng `equals()`.
- Hiểu chính xác rằng `Objects.equals()` ủy quyền cho `a.equals(b)`, không tự so sánh từng trường, không gọi `b.equals(a)` để kiểm tra hai chiều.
- Sử dụng tiện ích này khi viết `equals(Object)` cho lớp có trường tham chiếu nullable.
- Chọn phép so sánh phù hợp với `String`, record, wrapper, mảng và những đối tượng có hợp đồng `equals()` chuyên biệt.

## 1. Ý nghĩa và chữ ký phương thức

`Objects` là lớp tiện ích trong package `java.util`. Hai đối số của `Objects.equals` được khai báo là `Object`:

```java
public static boolean equals(Object a, Object b)
```

Phương thức trả về `true` nếu hai đối số được xem là bằng nhau và `false` trong trường hợp còn lại theo logic sau:

```java
return (a == b) || (a != null && a.equals(b));
```

Đây là **biểu thức tương đương với cách cài đặt trong thư viện Java**, dùng để giải thích cơ chế; không phải yêu cầu bạn tự định nghĩa lại phương thức `Objects.equals()`.

Biểu thức có ba phần:

1. **`a == b`**: nếu cùng tham chiếu, bao gồm hai đối số đều `null`, trả về `true` ngay.
2. **`a != null`**: nếu đối số đầu tiên là `null` và chưa qua nhánh đầu, không được gọi phương thức trên `a`; kết quả là `false`.
3. **`a.equals(b)`**: khi `a` khác `null` và hai tham chiếu khác nhau, gọi phương thức `equals` do kiểu chạy thực tế của `a` cung cấp. Nó có thể là `Object.equals()` mặc định hoặc phương thức ghi đè của lớp như `String`, `Integer`, record, hoặc lớp do bạn thiết kế.

Hai toán tử `||` và `&&` **đánh giá ngắn mạch** từ trái sang phải: khi `a == b` đã là `true` thì không đánh giá vế phải của `||`; khi `a != null` là `false` thì không đánh giá `a.equals(b)`. Nhờ vậy, `Objects.equals(null, x)` không ném `NullPointerException` do gọi một phương thức trên đối số thứ nhất `null`.

Lưu ý phạm vi bảo đảm: tiện ích này **tránh việc dereference đối số `a` khi nó là `null`**. Nó không ngăn một triển khai `equals()` tùy chỉnh ném ngoại lệ bên trong, và cũng không sửa các lỗi vi phạm hợp đồng `equals()` của lớp.

## 2. Bốn trường hợp `null` căn bản

Với các lớp có `equals()` tuân thủ hợp đồng thông thường (đối tượng khác `null` phải không bằng `null`), bảng kết quả là:

| Đối số `a` | Đối số `b` | `Objects.equals(a, b)` | Vì sao? |
| --- | --- | --- | --- |
| `null` | `null` | `true` | `a == b` là `true`. |
| `null` | `"Java"` | `false` | `a == b` sai; `a != null` sai; không gọi `equals()`. |
| `"Java"` | `null` | `false` | Gọi `"Java".equals(null)` và nhận `false`. |
| `"Java"` | `"Java"` | `true` | Cùng tham chiếu hoặc cùng nội dung theo `String.equals()`. |

Ví dụ:

```java
import java.util.Objects;

// Các lệnh nằm trong một phương thức:
System.out.println(Objects.equals(null, null));     // true
System.out.println(Objects.equals(null, "Java"));   // false
System.out.println(Objects.equals("Java", null));   // false
System.out.println(Objects.equals("Java", "Java")); // true
```

Đoạn này minh họa các lệnh trong phương thức; chương trình độc lập có ở phần 4.

Một sắc thái kỹ thuật quan trọng: việc `Objects.equals(a, b)` với `a` khác `null` cuối cùng gọi `a.equals(b)` có nghĩa là **một lớp tự ghi đè `equals(null)` trả về `true` đã vi phạm hợp đồng `equals`**, và tiện ích không tự sửa sai. Trong code đúng hợp đồng, một bên `null`, một bên không `null` sẽ không bằng nhau. Vì vậy, đừng lấy tiện ích này làm cơ chế kiểm tra hay “chữa” mọi cài đặt `equals` lỗi.

### `Objects.equals(a, b)` không nhất thiết gọi `equals()`

Nếu `a` và `b` cùng tham chiếu:

```java
Object one = new Object();
Object alias = one;

System.out.println(Objects.equals(one, alias)); // true
```

Kết quả đến ngay từ `a == b`. Không cần gọi `one.equals(alias)`, dù phương thức ấy ở lớp `Object` cũng trả về `true` cho cùng tham chiếu. Điều này vừa là tối ưu vừa giải thích vì sao một phép kiểm tra dùng `Objects.equals(x, x)` không thể một mình chứng minh rằng phương thức `x.equals(x)` được ghi đè đúng.

## 3. Vì sao phải hiểu rõ việc “ủy quyền”?

`Objects.equals(a, b)` **không tự biết** hai đối tượng nên được coi là bằng nhau theo ID, tên, số tiền, các trường hay danh tính. Nó giao quyết định cho `a.equals(b)` (sau các kiểm tra nhanh).

So sánh ba ví dụ:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);                  // false
System.out.println(Objects.equals(a, b));    // true

Object x = new Object();
Object y = new Object();
System.out.println(Objects.equals(x, y));    // false
```

- `a == b` so sánh tham chiếu. Hai lệnh `new String(...)` tạo hai đối tượng riêng.
- `Objects.equals(a, b)` cuối cùng gọi `String.equals(b)`, so sánh nội dung chuỗi; hai chuỗi cùng `"Java"` nên kết quả `true`.
- `Object` mặc định không so trường theo nội dung mà dùng tính đồng nhất đối tượng. Hai đối tượng mới `x`, `y` khác nhau nên `Objects.equals(x, y)` vẫn là `false`.

Ví dụ này cho thấy “an toàn với `null`” **không đồng nghĩa** với “mọi đối tượng sẽ được so theo giá trị”. Khi cần so dữ liệu theo một định nghĩa riêng, kiểu dữ liệu phải cài đặt `equals()` phù hợp.

### Vế nào quyết định?

Hãy chú ý hướng gọi:

```text
Objects.equals(a, b)

  nếu a == b
      → true
  ngược lại nếu a == null
      → false
  ngược lại
      → a.equals(b)
```

Không có bước tự động gọi `b.equals(a)`, kiểm tra kết quả hai chiều, hay chuẩn hóa hai đối tượng thành cùng kiểu.

Nếu một lớp viết `equals()` sai khiến `a.equals(b)` và `b.equals(a)` khác nhau, `Objects.equals` có thể cho kết quả khác nhau khi đảo thứ tự đối số. **Lỗi nằm ở việc vi phạm tính đối xứng của hợp đồng `equals`**, không phải phương thức `Objects.equals`.

Đối với `String` và những kiểu chuẩn có hợp đồng đúng, người dùng thường không nhận thấy khác biệt hướng gọi vì tính đối xứng đã được bảo đảm.

## 4. Chương trình Java 17+ có thể biên dịch và chạy

Để quan sát chính xác khi nào `equals()` được gọi, ví dụ sử dụng lớp `Observed` với bộ đếm số lần đi vào phương thức `equals()`. Bộ đếm **không tham gia** định nghĩa bằng nhau hay mã băm.

Lưu tệp `ObjectsEqualsDemo.java`:

```java
import java.util.Objects;

public class ObjectsEqualsDemo {
    static final class Book {
        private final int id;
        private final String title;

        Book(int id, String title) {
            this.id = id;
            this.title = title;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Book other)) {
                return false;
            }
            return id == other.id
                    && Objects.equals(title, other.title);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, title);
        }
    }

    static final class Observed {
        private final int value;
        private int equalsCalls;

        Observed(int value) {
            this.value = value;
        }

        @Override
        public boolean equals(Object obj) {
            equalsCalls++;
            return obj instanceof Observed other
                    && value == other.value;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(value);
        }

        int equalsCalls() {
            return equalsCalls;
        }
    }

    public static void main(String[] args) {
        System.out.println("both null: "
                + Objects.equals(null, null));
        System.out.println("left null: "
                + Objects.equals(null, "Java"));
        System.out.println("right null: "
                + Objects.equals("Java", null));

        String first = new String("Java");
        String second = new String("Java");
        System.out.println("string identity: " + (first == second));
        System.out.println("string equality: "
                + Objects.equals(first, second));

        Book book1 = new Book(7, "Effective Java");
        Book book2 = new Book(7, "Effective Java");
        Book book3 = new Book(7, null);
        Book book4 = new Book(7, null);
        System.out.println("book identity: " + (book1 == book2));
        System.out.println("book equality: "
                + Objects.equals(book1, book2));
        System.out.println("nullable field: "
                + Objects.equals(book3, book4));
        System.out.println("different book: "
                + Objects.equals(book1, book3));

        Observed left = new Observed(4);
        Observed right = new Observed(4);
        System.out.println("delegated: "
                + Objects.equals(left, right));
        System.out.println("left calls: " + left.equalsCalls());
        System.out.println("right calls: " + right.equalsCalls());

        System.out.println("same reference shortcut: "
                + Objects.equals(left, left));
        System.out.println("left calls after shortcut: "
                + left.equalsCalls());
        System.out.println("null shortcut: "
                + Objects.equals(null, right));
        System.out.println("right calls after null: "
                + right.equalsCalls());

        System.out.println("reverse delegation: "
                + Objects.equals(right, left));
        System.out.println("right calls after reverse: "
                + right.equalsCalls());
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac ObjectsEqualsDemo.java
java ObjectsEqualsDemo
```

Đầu ra:

```text
both null: true
left null: false
right null: false
string identity: false
string equality: true
book identity: false
book equality: true
nullable field: true
different book: false
delegated: true
left calls: 1
right calls: 0
same reference shortcut: true
left calls after shortcut: 1
null shortcut: false
right calls after null: 0
reverse delegation: true
right calls after reverse: 1
```

**Giải thích quan trọng:**

- Ba dòng đầu thể hiện cách xử lý `null`. Chúng không ném `NullPointerException` do gọi phương thức trên đối số đầu.
- Hai `String` có nội dung như nhau nhưng tham chiếu khác nhau; `Objects.equals` ủy quyền cho `String.equals` nên bằng nhau.
- Hai `Book` khác instance có thể bằng nhau vì `Book.equals` so sánh `id` và `title`; với hai `title` đều `null`, `Objects.equals(title, other.title)` trả về `true`.
- Ở `Objects.equals(left, right)`, hai tham chiếu khác nhau và `left` tồn tại, nên `left.equals(right)` chạy đúng một lần. Bộ đếm của `right` vẫn là 0.
- Ở `Objects.equals(left, left)`, hai tham chiếu trùng nhau nên dùng nhánh nhanh `a == b`; không tăng bộ đếm.
- Ở `Objects.equals(null, right)`, đối số đầu là `null` nên không gọi `right.equals(...)`. Bộ đếm của `right` vẫn là 0.
- Đảo thứ tự thành `Objects.equals(right, left)` thì chính `right.equals(left)` được gọi; bộ đếm của `right` trở thành 1.

Bộ đếm nằm trong đối tượng chỉ phục vụ quan sát, không quyết định giá trị `equals` hay `hashCode`. Trong mô hình sản xuất, `equals` thường được thiết kế không có tác dụng phụ để giữ hành vi dễ đoán.

## 5. Áp dụng khi viết `equals(Object)` cho lớp có trường nullable

Một tình huống thường gặp là lớp có các trường tham chiếu có thể mang giá trị `null`. Ví dụ `Book` trong chương trình trên có `title` nullable:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Book other)) {
        return false;
    }
    return id == other.id
            && Objects.equals(title, other.title);
}
```

Đây là **phần thân một phương thức bên trong lớp `Book`**, không phải chương trình Java độc lập.

Các trách nhiệm khác nhau:

1. `this == obj` xử lý trường hợp cùng đối tượng và tối ưu lối thoát sớm.
2. `instanceof Book other` kiểm tra rằng đối số không phải `null` và có kiểu phù hợp; trong Java 17, pattern matching tạo biến `other` đúng kiểu.
3. `id == other.id` so sánh hai giá trị nguyên thủy `int`.
4. `Objects.equals(title, other.title)` so sánh hai tham chiếu `String`, bao gồm trường hợp cả hai cùng `null`.

Không nhầm `Objects.equals(title, other.title)` với một phép kiểm tra kiểu của toàn bộ đối số `obj`. Nếu chưa xác minh `obj` thuộc kiểu thích hợp, bạn vẫn không thể truy cập `other.title` một cách an toàn. Hãy kiểm tra đối số trước rồi mới đọc các trường.

### Vì sao không dùng `title.equals(other.title)` trực tiếp?

Giả sử `title == null`. Khi đó:

```java
// Có thể ném NullPointerException:
boolean same = title.equals(other.title);
```

Một cách khác vẫn đúng là kiểm tra null thủ công:

```java
boolean same =
        title == null ? other.title == null
                      : title.equals(other.title);
```

Cả hai đoạn trên là minh họa bên trong lớp có trường `title` và biến `other`. Đối với hầu hết trường hợp so sánh nullable, `Objects.equals(title, other.title)` ngắn gọn hơn và thể hiện đúng ý định.

### Nhớ ghi đè `hashCode()` nhất quán

Nếu `equals()` được ghi đè theo `id` và `title`, hai đối tượng bằng nhau phải có cùng hash. Ví dụ:

```java
@Override
public int hashCode() {
    return Objects.hash(id, title);
}
```

`Objects.hash(...)` là tiện ích tính mã băm kết hợp nhiều giá trị; nó **khác** `Objects.equals(...)` và không tự quyết định lớp nào được xem là bằng nhau. Sự tương thích giữa `equals` và `hashCode` vẫn là trách nhiệm của người cài đặt.

Nếu các trường tham gia equality có thể thay đổi sau khi một đối tượng đã được đưa vào `HashSet` hay dùng làm khóa `HashMap`, kết quả tra cứu có thể không còn đúng như mong đợi; nên xem xét thiết kế đối tượng bất biến hoặc vòng đời khóa phù hợp.

## 6. So sánh `Objects.equals`, `==` và gọi trực tiếp `equals`

| Cách viết | Có an toàn khi đối số bên trái `null`? | Kiểm tra điều gì? | Khi nào nên dùng? |
| --- | --- | --- | --- |
| `a == b` | Có | Danh tính của tham chiếu, hoặc giá trị nếu kiểu nguyên thủy | Kiểm tra cùng instance, kiểm tra `null`, enum |
| `a.equals(b)` | Không | Phụ thuộc định nghĩa `equals` của đối tượng `a` | Khi đã biết `a` khác `null` |
| `Objects.equals(a, b)` | Có, đối với phép dereference `a` | Cùng tham chiếu hoặc ủy quyền tới `a.equals(b)` | So sánh logic các tham chiếu có thể `null` |
| `"OK".equals(a)` | Có đối với literal `"OK"` | So sánh nội dung theo `String.equals()` | So sánh chuỗi với hằng số đã biết |

Những tình huống chỉ cần kiểm tra `null` nên dùng `a == null` hoặc `a != null`. Không cần viết `Objects.equals(a, null)`, vì biểu thức trực tiếp rõ ràng hơn và không phụ thuộc vào một `equals(null)` được cài đặt sai hợp đồng.

Với kiểu nguyên thủy, nên dùng `==` để so sánh giá trị tương ứng. `Objects.equals` nhận `Object` nên giá trị nguyên thủy phải được boxing thành wrapper; việc này không đem lại lợi ích trong so sánh các giá trị nguyên thủy đơn giản.

### Wrapper: bình đẳng theo giá trị vẫn phụ thuộc kiểu

`Objects.equals(Integer.valueOf(5), Integer.valueOf(5))` là `true` vì `Integer.equals` so sánh giá trị int. Tuy nhiên, `Objects.equals(Integer.valueOf(5), Long.valueOf(5))` là `false` vì `Integer.equals` không coi một đối tượng `Long` là bằng `Integer` dù giá trị số trông giống nhau.

Không có cơ chế tự chuyển đổi hai đối tượng bất kỳ sang một “kiểu số chung” chỉ vì bạn gọi `Objects.equals`. Nếu nghiệp vụ cần so số ở nhiều kiểu, phải xác định quy tắc chuyển đổi và độ chính xác rồi triển khai tường minh.

### `BigDecimal`: cùng số toán học chưa chắc `equals`

```java
import java.math.BigDecimal;
import java.util.Objects;

// Trong một phương thức:
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(Objects.equals(a, b)); // false
System.out.println(a.compareTo(b) == 0);  // true
```

`BigDecimal.equals` xét cả giá trị chưa được scale và scale; `compareTo` dùng thứ tự giá trị số. `Objects.equals` không biến `equals` thành `compareTo == 0`. Điều này nhắc lại rằng tiện ích chỉ ủy quyền vào hợp đồng của kiểu cụ thể.

## 7. Cạm bẫy với mảng: an toàn `null` không phải so sánh sâu

Mảng Java không ghi đè `Object.equals()` để so phần tử. Vì vậy hai mảng `int[]` được tạo riêng vẫn cho `Objects.equals(a, b) == false` ngay cả khi cùng nội dung. Với mảng một chiều, `Arrays.equals` thường biểu đạt mục tiêu rõ nhất; với mảng lồng, chọn `Arrays.deepEquals` hoặc `Objects.deepEquals` theo ngữ nghĩa cần thiết.

```java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(Objects.equals(a, b));     // false
System.out.println(Objects.deepEquals(a, b)); // true
```

Đây là các câu lệnh minh họa trong một phương thức, cần import `java.util.Objects`. `Objects.deepEquals` xử lý nội dung mảng và `null` nhưng **không tự so sâu mọi lớp hoặc List chứa mảng**. Bài **Objects.deepEquals() khác Objects.equals() ở đối số mảng** đi sâu vào mảng nhiều chiều, record/List bọc mảng và cặp hàm hash tương thích.

## 8. `Objects.equals` không sửa được một `equals` viết sai

Giả sử một lớp cài đặt `equals()` lệch hợp đồng, chẳng hạn coi người dùng có ID giống nhau là bằng nhau theo chiều này nhưng không theo chiều kia. `Objects.equals` không gọi cả hai chiều để “hòa giải”. Nó chỉ gọi `a.equals(b)` khi cần.

Một số lỗi thường gặp ở phương thức `equals` của lớp:

- **Không đối xứng:** `a.equals(b) == true` nhưng `b.equals(a) == false`.
- **Không bắc cầu:** `a.equals(b)` và `b.equals(c)` đều `true` nhưng `a.equals(c)` lại `false`.
- **Không ổn định:** cùng dữ liệu nhưng kết quả thay đổi qua nhiều lần gọi do trạng thái ngoài hoặc tác dụng phụ.
- **Ném ngoại lệ cho đối số sai kiểu:** ép kiểu trước khi kiểm tra bằng `instanceof` hoặc `getClass()`.
- **Trả `true` cho `null`:** vi phạm hợp đồng `equals`.
- **Ghi đè `equals` nhưng không cập nhật `hashCode`:** gây lỗi trong cấu trúc băm khi hai đối tượng bằng nhau lại có mã băm không tương thích.

`Objects.equals` chỉ cung cấp nhánh xử lý an toàn với `null` ở bên ngoài và gọi phương thức của đối tượng thích hợp. Muốn hành vi bằng nhau đúng về logic, phải cài đặt và kiểm thử `equals(Object)` của lớp đúng hợp đồng.

### Chi tiết cần nhớ về shortcut cùng tham chiếu

Biểu thức `Objects.equals(a, a)` trả về `true` mà không cần gọi `a.equals(a)`. Vì vậy, nếu bạn đang **kiểm thử chính triển khai `equals` của lớp**, hãy gọi trực tiếp `a.equals(a)` để kiểm tra tính phản xạ, và sử dụng hai instance tương đương khác nhau để kiểm tra cách so sánh theo dữ liệu.

Không sử dụng shortcut `Objects.equals(a, a)` để “chứng minh” rằng lớp đã ghi đè `equals` đúng.

## 9. So sánh nhanh với các tiện ích `Objects` khác

Lớp `java.util.Objects` có nhiều phương thức tên gần nhau nhưng chức năng khác nhau:

- **`Objects.equals(a, b)`:** so hai tham chiếu an toàn với `null` ở cấp gọi.
- **`Objects.deepEquals(a, b)`:** so sâu khi hai đối số là mảng; với đối tượng thường, dựa vào `equals` như thích hợp.
- **`Objects.isNull(a)`:** tương đương ý nghĩa với kiểm tra `a == null`, thường dùng làm method reference như `Objects::isNull`.
- **`Objects.nonNull(a)`:** tương đương ý nghĩa với `a != null`, có thể dùng làm predicate.
- **`Objects.requireNonNull(a)`:** trả lại tham chiếu nếu khác `null`, nếu `null` thì **ném `NullPointerException`**; hữu ích để bảo vệ tiền điều kiện, không phải so sánh bằng nhau.
- **`Objects.hashCode(a)`:** trả 0 nếu `a` là `null`, nếu không gọi `a.hashCode()`.
- **`Objects.hash(values...)`:** tổng hợp hash từ nhiều giá trị bằng cơ chế varargs; dùng khi cài đặt `hashCode` cho lớp có nhiều trường.

Đặc biệt, `Objects.requireNonNull(a)` có mục đích **từ chối `null`**, trái với `Objects.equals` là **chấp nhận `null` làm đối số để so sánh**. Dùng đúng công cụ cho đúng hợp đồng dữ liệu.

## 10. Cách dùng trong mã ứng dụng

### So sánh hai trường nullable

```java
String oldEmail = null;
String newEmail = "a@example.com";

boolean changed = !Objects.equals(oldEmail, newEmail); // true
```

Đây là đoạn minh họa trong phương thức với `import java.util.Objects;`. Khi chỉ cần biết hai giá trị nullable có khác nhau hay không, cách viết này rõ ràng và không yêu cầu chuỗi bên trái tồn tại.

### So sánh giá trị khi tìm kiếm hoặc cập nhật

```java
static boolean sameLabel(String current, String expected) {
    return Objects.equals(current, expected);
}
```

Đây là khai báo một phương thức trong lớp đã import `Objects`. Nó tuân theo chính sách **hai `null` được xem là bằng nhau**. Nếu nghiệp vụ không muốn xem “cả hai thiếu dữ liệu” là bằng nhau, hãy viết chính sách riêng thay vì mặc định xem `Objects.equals` là giải pháp cho mọi tình huống.

### Với record

```java
record Point(int x, int y) {}

Point p1 = new Point(1, 2);
Point p2 = new Point(1, 2);

// Trong một phương thức:
boolean equal = Objects.equals(p1, p2); // true
```

`Objects.equals` dùng cách so sánh `equals` mà record cung cấp; với các component như `int`, kết quả là bình đẳng theo thành phần. Nhưng record có component là mảng không tự so nội dung mảng sâu chỉ vì được bọc trong `Objects.equals`.

## 11. Các lỗi thường gặp và cách sửa

1. **Viết `a.equals(b)` khi `a` có thể `null`.** Khi `a == null`, lời gọi gây `NullPointerException`. Dùng `Objects.equals(a, b)` nếu muốn hai tham chiếu nullable được so sánh theo `equals`.
2. **Dùng `==` để so nội dung chuỗi.** `==` kiểm tra hai tham chiếu có trỏ đến cùng object. Dùng `Objects.equals(a, b)` hoặc `String.equals` với receiver khác `null`.
3. **Cho rằng `Objects.equals` so mọi trường của mọi object.** Nó chỉ ủy quyền tới `equals` của toán hạng đầu. Nếu lớp giữ `Object.equals` mặc định, phép so có thể vẫn theo danh tính.
4. **Giả định `Objects.equals(a, b)` sẽ gọi cả `a.equals(b)` và `b.equals(a)`.** Không có bước này. Lớp phải tự bảo đảm tính đối xứng.
5. **Coi `Objects.equals(a, a)` là bài test đầy đủ cho `a.equals(a)`.** Shortcut `a == b` khiến hàm `equals` của đối tượng không được gọi.
6. **Dùng `Objects.equals` để so mảng theo phần tử.** Với mảng thông thường, kết quả vẫn dựa trên danh tính mảng. Dùng `Arrays.equals` hoặc API sâu phù hợp.
7. **Bỏ qua chính sách hai `null` bằng nhau.** `Objects.equals(null, null) == true` là hành vi chủ đích; nếu nghiệp vụ yêu cầu khác, phải có điều kiện riêng.
8. **Cho rằng null-safe đồng nghĩa exception-safe.** Một `equals` tùy chỉnh có thể ném ngoại lệ vì lỗi nội bộ, dữ liệu hỏng hoặc giả định sai. `Objects.equals` không nuốt hoặc tự sửa ngoại lệ đó.
9. **Nhầm `Objects.equals` với `Objects.requireNonNull`.** Một phương thức so sánh có chấp nhận `null`, phương thức kia từ chối `null` bằng ngoại lệ.

## 12. Bài tập tự kiểm tra

Dự đoán kết quả của các biểu thức sau. Giả sử chúng nằm trong một phương thức đã import `java.util.Objects` và `java.util.Arrays`:

```java
String s1 = null;
String s2 = null;
String s3 = "Hello";
String s4 = new String("Hello");

boolean q1 = Objects.equals(s1, s2);
boolean q2 = Objects.equals(s1, s3);
boolean q3 = Objects.equals(s3, s4);
boolean q4 = s3 == s4;

int[] a1 = {1, 2};
int[] a2 = {1, 2};
boolean q5 = Objects.equals(a1, a2);
boolean q6 = Arrays.equals(a1, a2);

Object same = new Object();
boolean q7 = Objects.equals(same, same);
```

**Đáp án:**

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `q1` | `true` | Cả hai cùng `null` nên `a == b` đúng. |
| `q2` | `false` | Đối số đầu là `null`, đối số sau không `null`. |
| `q3` | `true` | `String.equals` so nội dung `"Hello"`. |
| `q4` | `false` | Chuỗi `s4` được tạo thành instance riêng bởi `new`. |
| `q5` | `false` | Mảng không tự so theo phần tử trong `Objects.equals`. |
| `q6` | `true` | `Arrays.equals` so phần tử của hai mảng `int[]`. |
| `q7` | `true` | Nhánh `a == b` nhận diện cùng object. |

**Thực hành mở rộng:** sửa lớp `Book` ở phần 4 để thêm trường `String author` có thể `null`. Cập nhật `equals` bằng `Objects.equals(author, other.author)` và cập nhật `hashCode` bằng `Objects.hash(id, title, author)`. Thử hai sách có cả `title` và `author` đều `null`; sau đó thay đổi một giá trị và kiểm tra kết quả. Mục tiêu là duy trì đúng quan hệ giữa bằng nhau và mã băm mà không dereference trường `null`.

## Ghi nhớ

`Objects.equals(a, b)` tương đương với logic **`a == b || (a != null && a.equals(b))`**. Nó trả `true` khi cả hai `null`, trả `false` khi đối số đầu `null` và đối số sau khác `null`, và ủy quyền cho `equals()` của **đối số đầu tiên** khi cần. Đây là tiện ích so sánh null-safe ở cấp gọi, không phải cơ chế tự so sâu hay bộ sửa lỗi hợp đồng `equals`. Khi làm việc với mảng, số có quy tắc so riêng hoặc các đối tượng nghiệp vụ tùy chỉnh, luôn lựa chọn đúng định nghĩa bằng nhau của kiểu.