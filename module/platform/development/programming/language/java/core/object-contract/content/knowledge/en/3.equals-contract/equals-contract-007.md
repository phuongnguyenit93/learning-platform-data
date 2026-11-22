# `x.equals(null)` khác gì gọi `equals()` trên tham chiếu `null`?

## 1. Hai vị trí `null` mang ý nghĩa khác nhau

Trong biểu thức `x.equals(y)`, `x` là **tham chiếu nhận lời gọi phương thức** (receiver), còn `y` là **đối số**. Java phải có một đối tượng làm receiver để thực thi phương thức thể hiện (instance method). Vì vậy cần phân biệt:

- **`x` khác `null`, đối số là `null`:** `x.equals(null)` gọi được phương thức `equals(Object)` trên đối tượng `x`. Theo hợp đồng của `Object.equals`, kết quả phải là `false` với mọi `x` khác `null`.
- **`x` là `null`:** `x.equals(null)` hoặc `x.equals(y)` đều ném `NullPointerException` trước khi thân phương thức `equals` của đối tượng nào đó có thể chạy. Lỗi xuất phát từ **receiver `x`**, không phải vì đối số là `null`.

Nhìn nhanh: `x.equals(null)` **không phải cách kiểm tra xem `x` có bằng `null` hay không**. Cách kiểm tra tham chiếu có `null` là `x == null` (hoặc `x != null`).

## 2. Liên hệ với hợp đồng `equals`

`equals` là phương thức thể hiện được khai báo trong `java.lang.Object`, có chữ ký `public boolean equals(Object obj)`. Một yêu cầu của hợp đồng là: với mọi tham chiếu `x` khác `null`, `x.equals(null)` phải trả về `false`.

Điều này là **quy tắc dành cho cách triển khai `equals`**, không có nghĩa JVM tự thay lời gọi thành `false` trong mọi hoàn cảnh. Lớp ghi đè `equals` sai hợp đồng, chẳng hạn truy cập `obj` khi chưa kiểm tra `null`, có thể tự gây `NullPointerException` ngay cả khi receiver `x` không `null`. Khi đó lỗi thuộc về bản cài đặt `equals`; không làm thay đổi yêu cầu của hợp đồng.

Trong khi đó, khi receiver `x == null`, Java không có đối tượng để gọi `equals`. Không có bất kỳ triển khai `equals` nào nhận được cuộc gọi này; kết quả là `NullPointerException`.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu đoạn mã sau vào tệp `EqualsNullDemo.java`:

```java
import java.util.Objects;

public class EqualsNullDemo {
    public static void main(String[] args) {
        String present = "Java";
        String absent = null;

        System.out.println("present.equals(null): " + present.equals(null));
        System.out.println("absent == null: " + (absent == null));
        System.out.println("Objects.equals(absent, null): " + Objects.equals(absent, null));
        System.out.println("Objects.equals(present, absent): " + Objects.equals(present, absent));
        System.out.println("literal.equals(absent): " + "Java".equals(absent));

        try {
            absent.equals(null);
        } catch (NullPointerException ex) {
            System.out.println("absent.equals(null): NullPointerException");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac EqualsNullDemo.java
java EqualsNullDemo
```

Kết quả chuẩn:

```text
present.equals(null): false
absent == null: true
Objects.equals(absent, null): true
Objects.equals(present, absent): false
literal.equals(absent): false
absent.equals(null): NullPointerException
```

Giải thích từng trường hợp:

- `present.equals(null)` chạy vì `present` trỏ tới một `String`; `String.equals` trả `false` với đối số `null`.
- `absent == null` chỉ so sánh tham chiếu, không gọi phương thức, nên trả `true` và không ném lỗi.
- `Objects.equals(absent, null)` trả `true` vì **cả hai đối số đều `null`**; khác với việc gọi phương thức trên `absent`.
- `Objects.equals(present, absent)` trả `false` vì một đối số có giá trị, một đối số `null`.
- `"Java".equals(absent)` trả `false` vì receiver là chuỗi hằng chắc chắn không `null`.
- `absent.equals(null)` ném `NullPointerException` do receiver `absent == null`; chương trình bắt lỗi chỉ để minh họa, không phải cách kiểm tra `null` nên dùng trong ứng dụng.

## 4. So sánh các cách viết thường gặp

Giả sử biến `x` có kiểu `String` và nhận một trong hai giá trị `"Java"` hoặc `null`:

| Biểu thức | `x = "Java"` | `x = null` | Ý nghĩa |
| --- | --- | --- | --- |
| `x == null` | `false` | `true` | Kiểm tra tham chiếu có `null` hay không |
| `x.equals(null)` | `false` | `NullPointerException` | Gọi `equals` trên receiver `x` với đối số `null` |
| `Objects.equals(x, null)` | `false` | `true` | So sánh hai giá trị có xử lý `null` |
| `"Java".equals(x)` | `true` | `false` | Gọi `equals` trên receiver luôn khác `null` |

`Objects.equals(a, b)` (trong `java.util.Objects`) có logic tương đương `a == b || (a != null && a.equals(b))`. Nhờ điều kiện `a != null`, phương thức xử lý an toàn khi một hoặc cả hai đối số `null`. Khi **cả hai khác `null`**, nó vẫn sử dụng `a.equals(b)`, vì vậy vẫn phụ thuộc vào tính đúng đắn của triển khai `equals`.

`x == null` kiểm tra riêng tham chiếu `null`; còn với hai đối tượng khác `null`, `==` so sánh chúng có phải cùng một đối tượng hay không, trong khi `equals` thường so sánh sự bằng nhau theo ý nghĩa của lớp.

## 5. Viết `equals` đúng khi đối số là `null`

Ví dụ dưới đây là **một phần của lớp** để minh họa cách ghi đè, không phải chương trình độc lập:

```java
final class Book {
    private final String isbn;

    Book(String isbn) {
        this.isbn = java.util.Objects.requireNonNull(isbn);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Book book)) return false;
        return isbn.equals(book.isbn);
    }

    @Override
    public int hashCode() {
        return isbn.hashCode();
    }
}
```

Biểu thức `other instanceof Book book` trả về `false` khi `other == null`, nên không cần gọi phương thức trên đối số `null`. Trường hợp đó, `bookInstance.equals(null)` trả `false`. Cài đặt `hashCode()` nhất quán với `equals()` cũng là một phần quan trọng của hợp đồng đối tượng, nhất là khi dùng trong `HashMap` hoặc `HashSet`.

Ngược lại, mã như `other.getClass()` hoặc `other.equals(this)` **trước khi kiểm tra `other == null`** có thể ném `NullPointerException` trong `bookInstance.equals(null)`, vi phạm hợp đồng.

## 6. Cách chọn biểu thức trong thực tế

- Muốn biết một tham chiếu có `null` không: dùng `x == null` hoặc `x != null`.
- Muốn so sánh hai giá trị có thể đều là `null`: dùng `Objects.equals(x, y)`; hai giá trị `null` được coi là bằng nhau trong phép so sánh này.
- Muốn gọi `equals` khi `x` có thể `null`: dùng `x != null && x.equals(y)` nếu muốn kết quả `false` khi `x == null`; lưu ý cách này khác `Objects.equals(x, y)` khi **cả hai cùng `null`**.
- So sánh với một giá trị cố định chắc chắn không `null`: có thể dùng `"Java".equals(x)` để tránh receiver `null`.
- Khi ghi đè `equals`, bảo đảm mọi đối tượng khác `null` đều trả `false` với đối số `null`, đồng thời duy trì các phần còn lại của hợp đồng `equals` và `hashCode`.

Điểm then chốt: **`null` ở vị trí đối số** là trường hợp `equals` phải xử lý khi receiver tồn tại; **`null` ở vị trí receiver** khiến việc gọi phương thức thể hiện thất bại với `NullPointerException`.