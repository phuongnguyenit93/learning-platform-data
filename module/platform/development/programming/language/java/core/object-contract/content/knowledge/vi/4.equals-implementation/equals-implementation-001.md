# Chữ ký `public boolean equals(Object)` và cách kiểm tra bằng `@Override`

Khi tự định nghĩa “hai đối tượng có bằng nhau hay không”, ta phải **ghi đè** phương thức `equals(Object)` được thừa kế từ `java.lang.Object`. Phương thức dành cho việc này có dạng:

~~~java
@Override
public boolean equals(Object obj) {
    // Cài đặt phép so sánh bằng nhau
}
~~~

Điểm cốt lõi của bài: kiểu tham số phải là **`Object`**, không phải tên lớp đang viết. Chú thích `@Override` giúp trình biên dịch phát hiện trường hợp ta tưởng đã ghi đè nhưng thực tế lại khai báo một phương thức khác.

## 1. Hiểu đúng từng thành phần

- **`equals`** là tên phương thức. Mọi lớp Java đều thừa kế `equals(Object)` từ `Object`, trừ khi đã có phiên bản ghi đè.
- **`(Object obj)`** là danh sách tham số: **đúng một tham số** có kiểu `java.lang.Object`. Tên biến (`obj`, `other`, `o`…) có thể đổi mà không ảnh hưởng việc ghi đè. Tham số kiểu `Object` cho phép gọi qua biến tham chiếu bất kỳ kiểu đối tượng nào.
- **`boolean`** là kiểu trả về bắt buộc: `true` khi hai đối tượng được xem là bằng nhau, `false` khi không. Không dùng `Boolean`, `int` hoặc `void`.
- **`public`** là mức truy cập bắt buộc khi ghi đè phương thức `public` của `Object`; không được thu hẹp thành `protected`, không có modifier (package-private) hay `private`.
- Phương thức ghi đè là **phương thức đối tượng**, không phải `static`.
- **`@Override`** thông báo ý định ghi đè cho trình biên dịch. Nếu khai báo không khớp một phương thức có thể được ghi đè, chương trình không biên dịch được.

Phân biệt thuật ngữ: trong Java, *method signature* theo nghĩa ngôn ngữ gồm **tên phương thức và kiểu các tham số**; kiểu trả về và mức truy cập không nằm trong signature theo định nghĩa này. Tuy nhiên, để **ghi đè hợp lệ** `Object.equals(Object)`, khai báo vẫn phải thỏa `public` và `boolean`.

`Object.equals(Object)` mặc định chỉ trả về `true` nếu hai tham chiếu trỏ đến cùng một đối tượng. Ghi đè cho phép định nghĩa **bằng nhau theo giá trị** phù hợp với kiểu dữ liệu, chẳng hạn hai cuốn sách có cùng mã ISBN.

## 2. Tại sao `equals(Book)` không thay thế được `equals(Object)`?

Xét khai báo dưới đây (**đoạn minh họa lỗi; không phải chương trình độc lập**):

~~~java
final class WrongBook {
    private final String isbn;

    WrongBook(String isbn) {
        this.isbn = isbn;
    }

    // Sai nếu mục tiêu là ghi đè Object.equals(Object).
    public boolean equals(WrongBook other) {
        return other != null && isbn.equals(other.isbn);
    }
}
~~~

`equals(WrongBook)` là **overload** (nạp chồng) vì nhận `WrongBook`, khác kiểu tham số `Object`. Nó **không override** `Object.equals(Object)`. Vì thế:

- `wrongA.equals(wrongB)` có thể gọi `equals(WrongBook)` khi biểu thức `wrongB` có kiểu tĩnh `WrongBook`.
- `wrongA.equals((Object) wrongB)` lại gọi `equals(Object)` thừa kế từ `Object`, nên hai thực thể khác nhau thường cho `false` dù có cùng ISBN.
- Những API như `HashSet`, `HashMap` hay `Objects.equals(a, b)` dựa vào phép so sánh đối tượng `equals(Object)`; overload riêng không thay thế hợp đồng đó.

Nếu thêm `@Override` ngay trên `equals(WrongBook)`:

~~~java
@Override
public boolean equals(WrongBook other) {
    return other != null && isbn.equals(other.isbn);
}
~~~

`javac` sẽ **báo lỗi biên dịch** vì phương thức này không ghi đè phương thức nào của lớp cha/giao diện trong ví dụ. Đây chính là lợi ích thiết thực của `@Override`: lỗi lộ ra ngay lúc biên dịch, trước khi chạy ứng dụng.

## 3. Ví dụ Java 17 chạy được

Tạo tệp **`EqualsSignatureDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsSignatureDemo {

    private static final class Book {
        private final String isbn;

        Book(String isbn) {
            this.isbn = Objects.requireNonNull(isbn);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Book other)) {
                return false;
            }
            return isbn.equals(other.isbn);
        }

        @Override
        public int hashCode() {
            return isbn.hashCode();
        }
    }

    // Cố tình khai báo overload sai để quan sát sự khác nhau.
    private static final class WrongBook {
        private final String isbn;

        WrongBook(String isbn) {
            this.isbn = Objects.requireNonNull(isbn);
        }

        public boolean equals(WrongBook other) {
            return other != null && isbn.equals(other.isbn);
        }
    }

    public static void main(String[] args) {
        Book first = new Book("ISBN-1");
        Book sameIsbn = new Book("ISBN-1");
        Book different = new Book("ISBN-2");
        Object asObject = sameIsbn;

        System.out.println(first.equals(sameIsbn));
        System.out.println(first.equals(asObject));
        System.out.println(first.equals(null));
        System.out.println(first.equals("ISBN-1"));
        System.out.println(first.equals(different));

        Set<Book> books = new HashSet<>();
        books.add(first);
        books.add(sameIsbn);
        books.add(different);
        System.out.println(books.size());

        WrongBook wrongA = new WrongBook("ISBN-1");
        WrongBook wrongB = new WrongBook("ISBN-1");
        Object wrongAsObject = wrongB;
        System.out.println(wrongA.equals(wrongB));
        System.out.println(wrongA.equals(wrongAsObject));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac EqualsSignatureDemo.java
java EqualsSignatureDemo
~~~

**Kết quả chuẩn:**

~~~text
true
true
false
false
false
2
true
false
~~~

Giải thích lần lượt:

1. Hai `Book` khác thực thể nhưng cùng ISBN có kết quả `true` vì `Book.equals(Object)` so sánh giá trị `isbn`.
2. Biến `asObject` có kiểu tĩnh `Object` nhưng vẫn gọi **phiên bản override tại thời điểm chạy** của `Book`; kết quả vẫn là `true`.
3. `null` và chuỗi `"ISBN-1"` không phải `Book`, nên cho `false`.
4. Hai `Book` khác ISBN cho `false`.
5. `HashSet` chỉ giữ hai cuốn sách khác nhau theo ISBN vì `equals(Object)` và `hashCode()` nhất quán.
6. Với `WrongBook`, lệnh đầu chọn overload `equals(WrongBook)` và in `true`; lệnh sau nhận đối số kiểu `Object`, chọn `Object.equals(Object)` được thừa kế, nên in `false`.

### Tại sao phương thức đúng kiểm tra theo thứ tự đó?

- `this == obj` xử lý nhanh trường hợp cùng tham chiếu và bảo đảm đối tượng bằng chính nó.
- `obj instanceof Book other` kiểm tra cả kiểu của đối số; `null` không thỏa `instanceof`, nên trả `false` an toàn. Cú pháp pattern matching này được hỗ trợ trên Java 17.
- `isbn.equals(other.isbn)` so sánh dữ liệu quan trọng khi chắc chắn cả hai đều là `Book`. Constructor dùng `Objects.requireNonNull` để bảo đảm `isbn` khác `null`.
- Lớp `Book` là `final` để ví dụ không phải xử lý quy tắc bằng nhau khi có lớp con. Quyết định dùng `instanceof` hay `getClass()` trong phân cấp kế thừa cần xem xét riêng nhằm giữ tính đối xứng của `equals`.

Ta viết thêm `hashCode()` vì hai đối tượng được `equals` coi là bằng nhau phải có cùng hash code. `@Override` cũng hữu ích cho phương thức này; tuy nhiên trọng tâm ở đây vẫn là kiểm tra đúng **chữ ký `equals(Object)`**.

## 4. Những lỗi khai báo `@Override` sẽ bắt được

Các đoạn dưới đây đều là **mảnh mã cố tình sai**, giả sử chúng nằm trong một lớp bình thường thừa kế trực tiếp từ `Object`. Mỗi đoạn được xét độc lập, không ghép vào chương trình chạy:

~~~java
@Override
public boolean equals(Book other) { return true; } // Sai tham số: overload.
~~~

~~~java
@Override
protected boolean equals(Object other) { return true; } // Thu hẹp public.
~~~

~~~java
@Override
public Boolean equals(Object other) { return true; } // Sai kiểu trả về.
~~~

~~~java
@Override
public static boolean equals(Object other) { return true; } // Không thể override bằng static.
~~~

~~~java
@Override
public boolean equals(Object other, int mode) { return true; } // Thừa tham số.
~~~

Với từng trường hợp, `javac` từ chối biên dịch; thông báo cụ thể có thể khác nhau tùy loại lỗi và phiên bản trình biên dịch. Riêng trường hợp `equals(Book)` không có `@Override` thì **vẫn có thể biên dịch**, nhưng không đạt mục tiêu ghi đè. Vì vậy, hãy viết annotation ngay lúc khai báo phương thức.

Cũng cần phân biệt: `@Override` **không tự kiểm tra logic** bên trong thân phương thức. Một phương thức có đúng chữ ký và annotation vẫn có thể viết sai về ngữ nghĩa (ví dụ so sánh giá trị sai hoặc vi phạm tính đối xứng, bắc cầu). Các lỗi đó cần kiểm thử và tuân thủ hợp đồng `equals`.

## 5. Cách tự kiểm tra nhanh trong dự án

Khi cài đặt phép bằng nhau cho một lớp dữ liệu:

1. Gõ đúng `@Override public boolean equals(Object obj)`; tên `obj` tùy chọn.
2. Để IDE hoặc `javac` xác nhận phương thức thực sự override; không bỏ `@Override` chỉ để “làm hết lỗi”.
3. Kiểm tra các trường hợp cùng tham chiếu, cùng giá trị, khác giá trị, `null`, sai kiểu.
4. Đặc biệt, gọi qua **biến kiểu `Object`** để phát hiện kiểu lỗi overload như ví dụ trên.
5. Khi ghi đè `equals`, cũng cài đặt `hashCode` nhất quán, rồi kiểm tra hành vi của các collection dựa trên hash.

**Ghi nhớ:** `public boolean equals(Object obj)` mới ghi đè đúng phương thức của `Object`. `equals(T obj)` (với `T` là lớp của bạn) chỉ là overload. `@Override` biến sự nhầm lẫn này thành lỗi biên dịch rõ ràng và nên luôn có mặt khi chủ đích là ghi đè.