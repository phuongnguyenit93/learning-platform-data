# Dạng mặc định của `Object.toString()`: tên lớp, dấu `@` và mã băm thập lục phân

Khi in một object trong Java, ta có thể thấy chuỗi dạng `com.example.Book@5e2de80c`. Chuỗi này thường xuất hiện vì lớp **kế thừa triển khai mặc định của `Object.toString()`**. Nó **không phải nội dung các trường**, **không phải địa chỉ bộ nhớ được Java cam kết**, và **không phải định danh duy nhất** của object.

Bài học giải thích chính xác công thức tạo chuỗi, ý nghĩa từng phần, quan hệ với `hashCode()`, những trường hợp không còn dùng định dạng mặc định, cách thử bằng Java 17 và những lỗi cần tránh.

## 1. Hợp đồng mặc định và công thức

Trong `java.lang.Object`, triển khai `toString()` mặc định có thể biểu diễn tương đương bằng:

~~~java
public String toString() {
    return getClass().getName() + "@"
            + Integer.toHexString(hashCode());
}
~~~

Đây là **mã minh họa công thức của phương thức trong `Object`**, không phải đoạn cần chép vào mọi lớp. Ba thành phần được nối trực tiếp và **không có dấu cách**:

| Thành phần | Nguồn | Ý nghĩa |
|---|---|---|
| `getClass().getName()` | Runtime class của object | Tên lớp theo quy tắc binary name của Java |
| `"@"` | Ký tự cố định | Dấu phân tách giữa tên lớp và mã băm |
| `Integer.toHexString(hashCode())` | Giá trị `int` từ `hashCode()` | Chuyển mã băm thành chuỗi hệ **16**, dùng chữ `a`–`f` viết thường |

Với một lớp `Book` trong package `com.example` không ghi đè `toString()`, kết quả có **dạng**:

~~~text
com.example.Book@5e2de80c
~~~

Phần `5e2de80c` chỉ là **mã ví dụ minh họa**, không phải giá trị có thể tiên đoán cho một object bất kỳ. Cùng mã nguồn chạy vào lúc khác có thể in phần đuôi khác. Không dùng chuỗi đó làm dữ liệu kết quả bắt buộc của bài kiểm thử.

Khi một object không ghi đè `toString()`, JVM gọi phương thức kế thừa từ `Object`. Nếu lớp **ghi đè `toString()`**, Java sẽ dùng triển khai của lớp đó; định dạng `ClassName@hex` không còn được bảo đảm.

## 2. Tên lớp là tên runtime, không phải tên biến

Phần đứng trước `@` lấy từ `getClass().getName()`. Nó phụ thuộc vào **kiểu của object thực tế**, không phụ thuộc kiểu khai báo của biến:

~~~java
Object value = new StringBuilder("abc");
System.out.println(value.getClass().getName());
// java.lang.StringBuilder
~~~

Đây là snippet đặt trong `main`. Kiểu tĩnh của `value` là `Object`, nhưng lớp runtime là `StringBuilder`.

Phần tên có thể khác kỳ vọng:

- Lớp top-level thuộc package `com.example`: `com.example.Book`, không chỉ `Book`.
- Lớp thành viên `Demo.Item`: binary name thường là `Demo$Item`, **không** là `Demo.Item`.
- Lớp cục bộ hoặc anonymous có dạng tên do trình biên dịch tạo; không nên hardcode quy ước số trong tên vào kiểm thử.
- Với mảng nguyên thủy `int[]`, `getClass().getName()` trả `[I`; với mảng `String[]` trả `[Ljava.lang.String;`. Vì vậy `toString()` mặc định của array có tiền tố như `[I@`, thay vì chữ `int[]@`.

**`Class.getName()`, `getSimpleName()` và `getCanonicalName()` không phải lúc nào cho cùng kết quả.** `Object.toString()` dùng `getName()`. Nếu muốn tên lớp ngắn để hiển thị, đó là lựa chọn khác cần được viết rõ trong `toString()` tùy chỉnh.

## 3. Mã băm sau dấu @ thực sự là gì?

Phần sau `@` là kết quả của biểu thức:

~~~java
Integer.toHexString(hashCode())
~~~

- `hashCode()` trả một số nguyên Java kiểu `int` có dấu (32-bit).
- `Integer.toHexString(...)` biểu diễn các bit của số theo cơ số 16, **không thêm tiền tố `0x`**.
- Chữ cái trong phần hex được viết thường. Ví dụ mã băm thập phân `42` thành `2a`, `255` thành `ff`, `0` thành `0`, còn `-1` thành `ffffffff`.
- Giá trị này **không được cam kết là địa chỉ bộ nhớ**, số thứ tự object, UUID hay mã duy nhất trên toàn chương trình.
- Hai object khác nhau có thể **trùng hash**. Không được suy từ đuôi hex giống nhau rằng hai tham chiếu chỉ cùng một instance.

Với lớp **không ghi đè `hashCode()`**, phương thức mặc định của `Object` thường cấp một giá trị thích hợp cho identity hashing. Java không quy định phải tính nó từ địa chỉ vật lý. `System.identityHashCode(obj)` trả mã băm theo cơ chế identity của `Object` ngay cả khi lớp đã ghi đè `hashCode()`.

Một điểm đặc biệt quan trọng: **`Object.toString()` gọi `hashCode()` bằng dispatch động**. Nếu lớp ghi đè `hashCode()` nhưng không ghi đè `toString()`, phần hex phản ánh **hashCode đã ghi đè**, không bắt buộc là `System.identityHashCode()`. Đây là lý do không nên mô tả mặc định thành `ClassName@identityHash` trong mọi trường hợp.

## 4. Java 17 chạy được: kiểm chứng công thức và đầu ra xác định

Ví dụ sau có ba lớp lồng:

- `Plain`: giữ nguyên `Object.hashCode()` và `Object.toString()`, nên phần hex không thể dự đoán trước; chương trình kiểm tra công thức bằng boolean.
- `FixedHash`: **chỉ để minh họa**, ghi đè `hashCode()` trả `42`, kế thừa `toString()`; vì vậy phần hex xác định là `2a`.
- `NegativeHash`: trả `-1` để kiểm tra cách đổi thành `ffffffff`.

Lưu file **`ObjectToStringDemo.java`**, không khai báo package:

~~~java
public class ObjectToStringDemo {
    static final class Plain {}

    static final class FixedHash {
        @Override
        public int hashCode() {
            return 42;
        }
    }

    static final class NegativeHash {
        @Override
        public int hashCode() {
            return -1;
        }
    }

    public static void main(String[] args) {
        Plain plain = new Plain();
        String raw = plain.toString();

        System.out.println("plain class: "
                + plain.getClass().getName());
        System.out.println("plain prefix: "
                + raw.startsWith(plain.getClass().getName() + "@"));
        System.out.println("plain formula: "
                + raw.equals(plain.getClass().getName() + "@"
                        + Integer.toHexString(plain.hashCode())));
        System.out.println("plain identity hash: "
                + (plain.hashCode()
                        == System.identityHashCode(plain)));

        FixedHash fixed = new FixedHash();
        System.out.println("fixed: " + fixed);
        System.out.println("fixed hex: "
                + Integer.toHexString(fixed.hashCode()));

        NegativeHash negative = new NegativeHash();
        System.out.println("negative: " + negative);
        System.out.println("negative hex: "
                + Integer.toHexString(negative.hashCode()));

        int[] numbers = {1, 2, 3};
        System.out.println("array class: "
                + numbers.getClass().getName());
        System.out.println("array prefix: "
                + numbers.toString().startsWith("[I@"));
        System.out.println("array content: "
                + java.util.Arrays.toString(numbers));

        String text = "hello";
        System.out.println("String toString: " + text.toString());
    }
}
~~~

Lệnh biên dịch và chạy trên JDK 17+:

~~~bash
javac ObjectToStringDemo.java
java ObjectToStringDemo
~~~

**Đầu ra có thể dự đoán** (không in chuỗi hash ngẫu nhiên của `Plain`):

~~~text
plain class: ObjectToStringDemo$Plain
plain prefix: true
plain formula: true
plain identity hash: true
fixed: ObjectToStringDemo$FixedHash@2a
fixed hex: 2a
negative: ObjectToStringDemo$NegativeHash@ffffffff
negative hex: ffffffff
array class: [I
array prefix: true
array content: [1, 2, 3]
String toString: hello
~~~

Giải thích:

1. `Plain` là lớp thành viên tĩnh trong `ObjectToStringDemo`, vì vậy `getName()` trả binary name `ObjectToStringDemo$Plain`. Kiểm tra tiền tố và công thức trả `true` mà không cần giả định một hash cụ thể.
2. `Plain` không ghi đè hash, nên `hashCode()` phù hợp với `System.identityHashCode()` của chính instance đó.
3. `FixedHash` kế thừa `Object.toString()` nhưng ghi đè `hashCode()`. Kết quả **chính xác** là `ObjectToStringDemo$FixedHash@2a`.
4. `NegativeHash` chứng minh `Integer.toHexString(-1)` cho `ffffffff`; phép đổi hệ 16 không đặt dấu trừ phía trước.
5. `int[]` là object có tên runtime `[I` và giữ `toString()` mặc định. Muốn hiển thị phần tử `[1, 2, 3]`, dùng `Arrays.toString()`.
6. `String` đã ghi đè `toString()` nên trả chính nội dung `hello`, không phải `java.lang.String@...`.

**Lưu ý thiết kế:** các lớp cố tình trả hash cố định trong ví dụ chỉ dùng để trình diễn dispatch và phép chuyển hex. Trong phần mềm thực, mã băm phải phù hợp với `equals()` và có phân phối hợp lý theo dữ liệu để giảm va chạm trong collection băm.

## 5. Điều gì xảy ra khi lớp ghi đè equals, hashCode hoặc toString?

Xét từng trường hợp độc lập:

| Lớp định nghĩa | Hình thức `toString()` nếu không ghi đè nó | Cần chú ý |
|---|---|---|
| Không ghi đè cả ba | `RuntimeClassName@hex(Object.hashCode())` | Phần hex không ổn định giữa các phiên chạy |
| Chỉ ghi đè `hashCode()` | `RuntimeClassName@hex(overriddenHashCode())` | Vẫn là **Object.toString** nhưng đuôi không mặc định identity hash |
| Chỉ ghi đè `equals()` | Vẫn dùng Object.toString và hash mặc định | **Có nguy cơ vi phạm hợp đồng** nếu hai instance được equals coi bằng nhau nhưng hash khác |
| Ghi đè cả `equals()` và `hashCode()` | Vẫn có dạng `RuntimeClassName@hex(hashCode())` | Hai object bằng nhau có cùng hash, có thể có chuỗi toString giống nhau |
| Ghi đè `toString()` | Phụ thuộc code ghi đè | Có thể là JSON-like, text tùy chỉnh, danh sách thuộc tính... |

Ghi đè `toString()` **không có nghĩa** tự thay đổi `equals()` hay `hashCode()`. Ngược lại, ghi đè `equals()`/`hashCode()` không tự sinh cách biểu diễn văn bản dễ đọc. Đây là những hợp đồng khác nhau.

### Ví dụ tùy chỉnh để in các trường

~~~java
final class Book {
    private final String isbn;
    private final String title;

    Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book{isbn='" + isbn + "', title='" + title + "'}";
    }
}
~~~

Đây là khai báo lớp có thể biên dịch; muốn chạy cần thêm `main`. In `new Book("978-1", "Java")` sẽ cho:

~~~text
Book{isbn='978-1', title='Java'}
~~~

Không còn tên đầy đủ của lớp, `@` hay hex vì lớp đã tự quyết định chuỗi trả về. Nếu `Book` dùng làm **value object** trong `HashSet`/`HashMap`, vẫn phải định nghĩa equality/hash tương ứng khi cần; `toString()` không thay thế hai hợp đồng đó.

## 6. Các lớp chuẩn không nhất thiết in theo mẫu Object

Mọi lớp đều thừa hưởng `toString()`, nhưng nhiều lớp chuẩn **ghi đè**:

- `String.toString()` trả nội dung chuỗi. `StringBuilder.toString()` cũng tạo chuỗi biểu diễn các ký tự nó chứa.
- `Integer`, `BigDecimal` và các lớp số thường in giá trị theo quy tắc văn bản của chính kiểu.
- `List`, `Set`, `Map` trong các triển khai phổ biến in nội dung phần tử/mapping; thứ tự duyệt của `HashSet`/`HashMap` không được bảo đảm.
- `record` được Java sinh `toString()` phản ánh các component; nó không giữ nguyên mẫu `ClassName@hex`. Hợp đồng `record` có cách thể hiện riêng.
- **Array** lại là một trường hợp quen thuộc giữ cách in kiểu Object: `new int[]{1,2}.toString()` không in `[1, 2]`. Dùng `Arrays.toString` hoặc `Arrays.deepToString` cho mảng lồng tương ứng.

Vì vậy **không nên suy** từ một object hiển thị dạng `@hex` rằng tất cả object khác đều vậy. Cần kiểm tra có ghi đè `toString()` không; có thể xem Javadoc và cách lớp triển khai ghi đè.

## 7. Đâu là giới hạn và ý nghĩa của giá trị hex?

### Không phải địa chỉ bộ nhớ

Theo đặc tả Java, `hashCode()` là giá trị `int`; không có yêu cầu rằng số đó chứa địa chỉ bộ nhớ hoặc giữ nguyên địa chỉ vật lý. GC có thể di chuyển object, nhưng người dùng Java không cần suy luận địa chỉ vật lý từ `Object.toString()`.

### Không phải khóa duy nhất

Hash có không gian hữu hạn (32 bit). Collision có thể xảy ra, kể cả với hai object khác nhau. Nếu cần biết hai biến có cùng instance, dùng **`==` cho tham chiếu**; nếu cần hai giá trị có bằng nhau theo nghiệp vụ, dùng `equals()`; không lấy đuôi `@hex` làm bằng chứng.

### Không phải định dạng lưu trữ ổn định

Không lưu `Object.toString()` mặc định để sử dụng làm ID database, khóa API, liên kết ổn định, token xác thực hoặc dữ liệu cần parse qua nhiều lần chạy. Hợp đồng `Object.toString()` mô tả dạng chuỗi nhưng không cam kết hash cố định cho cùng ý nghĩa nghiệp vụ trong các tiến trình khác nhau.

### Không suy diễn rằng mọi hash đều là identity hash

Nếu `hashCode()` bị override, `Object.toString()` sẽ gọi hash mới. Ngay cả hai object bằng nhau theo `equals()` và có cùng hash cũng có thể in cùng phần đuôi, nhưng không vì vậy mà chúng là cùng instance. `System.identityHashCode()` là API riêng để lấy identity hash (vẫn **không** cam kết duy nhất).

## 8. Phân biệt toString, equals và hashCode

| Câu hỏi | Dùng | Điều không nên làm |
|---|---|---|
| Muốn trình bày đối tượng cho log/debug? | `toString()` phù hợp với nội dung muốn đọc | Không coi text là identity duy nhất |
| Hai tham chiếu có cùng object? | `a == b` | Không so chuỗi `a.toString().equals(b.toString())` |
| Hai đối tượng có giá trị bằng nhau? | `a.equals(b)` hoặc `Objects.equals(a,b)` | Không dựa vào kết quả `toString` |
| Cần tổ chức khóa trong `HashMap`/`HashSet`? | `equals()` và `hashCode()` đúng hợp đồng | Không dùng đuôi hex của `toString` thay cho khóa |
| Cần in nội dung mảng? | `Arrays.toString()`/`deepToString()` | Không dùng `array.toString()` để in từng phần tử |

Ví dụ: hai object có cùng `toString()` **chưa chắc equals**. Một `toString()` tự viết có thể chỉ in `name` và bỏ `id`, trong khi equality xét ID. Ngược lại, hai object có thể bằng nhau theo `equals()` nhưng có chuỗi `toString()` khác nếu code tự tùy chỉnh không phản ánh cùng các trường. Vì vậy không nên parse hoặc so text của `toString()` để suy ra quan hệ equality.

## 9. Các lỗi thường gặp

1. **Xem `@5e2de80c` là địa chỉ ô nhớ:** Java không bảo đảm điều đó. Đây là hex của hash code.
2. **Nghĩ ký tự sau @ luôn đến từ Object.hashCode:** khi lớp ghi đè `hashCode()`, Object.toString sẽ gọi phiên bản ghi đè.
3. **Cố định mã hex khi viết test:** giá trị hash mặc định không được cam kết giữa các lần chạy; hãy thử bằng công thức hoặc chỉ kiểm tra cấu trúc.
4. **Nhầm `getSimpleName()` với `getName()`:** lớp lồng/thuộc package có tên binary khác tên hiển thị ngắn.
5. **In mảng mong thấy phần tử:** `int[].toString()` cho dạng `[I@hex`; dùng `Arrays.toString`.
6. **Dùng `toString()` làm equality:** các phương thức có mục đích khác nhau; toString có thể thay đổi khi cải thiện log.
7. **Chỉ ghi đè equals mà quên hashCode:** có thể khiến hash collection hành xử không đúng; toString không giải quyết được lỗi này.
8. **Mặc định mọi lớp chuẩn đều in theo dạng @hex:** `String`, wrapper, collection và record có quy tắc khác.

## 10. Tự kiểm tra

**Câu 1.** Với một object không override `toString()`, công thức tạo chuỗi là gì?  
**Đáp án:** `getClass().getName() + "@" + Integer.toHexString(hashCode())`.

**Câu 2.** Lớp `FixedHash` chỉ override `hashCode()` trả `255` nhưng không override `toString()`. Phần sau `@` là gì?  
**Đáp án:** `ff`, vì `Integer.toHexString(255)` trả `"ff"`.

**Câu 3.** `Object.toString()` mặc định có bảo đảm mã hex là duy nhất và bằng địa chỉ vật lý không?  
**Đáp án:** Không. Hash có thể va chạm và API không cam kết đó là địa chỉ bộ nhớ.

**Câu 4.** Tại sao tên lớp lồng có thể chứa dấu `$`?  
**Đáp án:** Vì `getClass().getName()` trả binary name, không nhất thiết tên nguồn/đơn giản.

**Câu 5.** Nếu một lớp override `toString()` để in `Book{title='Java'}`, phần `@hex` còn bắt buộc xuất hiện không?  
**Đáp án:** Không. Chuỗi trả về do implementation `toString()` mới quyết định.

**Câu 6.** `new int[]{1,2}.toString()` có trả `[1, 2]` không?  
**Đáp án:** Không; mảng dùng dạng của Object. Muốn in nội dung cần `Arrays.toString(...)`.

**Ghi nhớ:** Dạng mặc định **`TênLớpRuntime@hex(hashCode())`** phản ánh tên lớp và mã băm được chuyển sang hệ 16; nó hữu ích khi nhìn log/debug, nhưng không phải định danh duy nhất hay cách so sánh giá trị. Luôn phân biệt định dạng kế thừa từ `Object` với `toString()` đã được lớp cụ thể ghi đè.
