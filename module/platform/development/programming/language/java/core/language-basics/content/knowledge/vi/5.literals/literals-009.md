# Literal `null` và những nơi không thể gán `null` — Java 17+

`null` là một **literal** của Java, biểu thị việc một tham chiếu **không trỏ tới đối tượng hay mảng nào**. Đây không phải chuỗi `"null"`, không phải số `0` và cũng không phải giá trị mặc định của mọi kiểu dữ liệu.

Quy tắc chính: **`null` có thể gán cho biến kiểu tham chiếu, nhưng không thể gán trực tiếp cho biến kiểu nguyên thủy (*primitive*).** Việc gán hợp lệ về cú pháp chưa chắc bảo đảm an toàn khi dùng giá trị sau đó.

## 1. `null` gán được cho kiểu nào?

| Kiểu đích | Ví dụ | Hợp lệ trên Java 17? | Vì sao |
| --- | --- | --- | --- |
| Lớp | `String text = null;` | Có | `String` là kiểu tham chiếu |
| Lớp bao (*wrapper*) | `Integer number = null;` | Có | `Integer` là đối tượng, khác `int` |
| Mảng | `int[] numbers = null;` | Có | Bản thân mảng là kiểu tham chiếu |
| Interface | `Runnable task = null;` | Có | Biến giữ tham chiếu đến đối tượng thực thi interface |
| Enum hoặc record | `Status s = null;` khi `Status` là enum | Có | Đều là kiểu tham chiếu |
| Kiểu tổng quát tham chiếu | `java.util.List<String> list = null;` | Có | Biến giữ tham chiếu danh sách |
| Nguyên thủy | `int n = null;` | **Không** | `int` cần giá trị số nguyên |
| Nguyên thủy | `boolean ok = null;` | **Không** | `boolean` cần `true` hoặc `false` |
| Nguyên thủy | `char c = null;` | **Không** | `char` cần giá trị mã ký tự |
| Biến cục bộ dùng `var` | `var x = null;` | **Không** | Compiler không suy luận được kiểu từ initializer `null` đơn lẻ |

Các kiểu nguyên thủy còn lại `byte`, `short`, `long`, `float`, `double` cũng **không nhận `null` trực tiếp**. `void` không phải kiểu biến lưu giá trị; phương thức `void` không được dùng `return null;`.

**Chi tiết ngôn ngữ:** literal `null` là giá trị duy nhất của *null type*. Null type không có tên để bạn khai báo biến trực tiếp. Java cho phép chuyển giá trị này sang kiểu tham chiếu phù hợp, nhưng không sang kiểu nguyên thủy.

## 2. Ví dụ Java 17 chạy được

Tạo file UTF-8 tên **`NullLiteralDemo.java`**:

~~~java
import java.util.Objects;

public class NullLiteralDemo {
    static String displayName(String name) {
        return name == null ? "(khong co ten)" : name;
    }

    static int lengthOrZero(String text) {
        return text == null ? 0 : text.length();
    }

    public static void main(String[] args) {
        String name = null;
        Integer boxedCount = null;
        int[] numbers = null;
        String[] names = {"Mai", null};

        System.out.println("nameIsNull=" + (name == null));
        System.out.println("boxedIsNull=" + (boxedCount == null));
        System.out.println("arrayIsNull=" + (numbers == null));
        System.out.println("elementIsNull=" + (names[1] == null));

        System.out.println("display=" + displayName(name));
        System.out.println("lengthOrZero=" + lengthOrZero(name));
        System.out.println("stringNull=" + "null".equals(name));
        System.out.println("objectsEquals=" + Objects.equals(name, null));

        try {
            System.out.println("length=" + name.length());
        } catch (NullPointerException ex) {
            System.out.println("dereference=NullPointerException");
        }

        try {
            int count = boxedCount; // Tu dong unboxing Integer -> int.
            System.out.println("count=" + count);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
~~~

Mở **Windows PowerShell** hoặc **Linux/Bash** tại thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NullLiteralDemo.java
java NullLiteralDemo
~~~

**Expected output:**

~~~text
nameIsNull=true
boxedIsNull=true
arrayIsNull=true
elementIsNull=true
display=(khong co ten)
lengthOrZero=0
stringNull=false
objectsEquals=true
dereference=NullPointerException
unboxing=NullPointerException
~~~

Giải thích:

- `String`, `Integer`, `int[]` đều là kiểu tham chiếu, nên biến có thể chứa `null`.
- Mảng `names` **không null**, nhưng **phần tử** `names[1]` có thể null vì phần tử có kiểu `String`.
- `name.length()` biên dịch hợp lệ nhưng gọi phương thức trên tham chiếu null sẽ ném `NullPointerException` lúc chạy.
- `int count = boxedCount;` cũng biên dịch hợp lệ: compiler chèn phép *unboxing* từ `Integer` sang `int`. Nhưng vì wrapper đang null, thao tác unboxing ném `NullPointerException`.
- `Objects.equals(name, null)` so sánh an toàn khi một hoặc hai đối số là null; `"null".equals(name)` so sánh chuỗi literal với tham chiếu null nên trả `false`.

Trong ví dụ, `try/catch` được dùng chỉ để **minh họa hai lỗi runtime** mà không làm chương trình ngừng ngay. Trong ứng dụng thực, nên kiểm tra và xử lý dữ liệu đầu vào trước khi truy cập hoặc unboxing.

## 3. Lỗi **biên dịch** khác lỗi **khi chạy**

Các dòng dưới đây **cố ý sai**, chỉ dùng để học, không thêm vào chương trình đang chạy:

~~~java
// int quantity = null;       // Sai: null khong chuyen sang int.
// boolean enabled = null;    // Sai: null khong chuyen sang boolean.
// char letter = null;        // Sai: null khong chuyen sang char.
// var unknown = null;        // Sai: khong suy luan duoc kieu.
// int[] values = {null};     // Sai: phan tu int khong nhan null.
~~~

Ngược lại, các dòng sau **hợp lệ về kiểu**:

~~~java
Integer quantity = null;
Boolean enabled = null;
Character letter = null;
String inferred = null;
Integer[] values = {null};
~~~

Phân biệt hai loại mảng:

~~~java
int[] a = null;           // Hop le: tham chieu mang chua null.
int[] b = new int[2];     // Phan tu primitive co gia tri 0.
String[] c = new String[2]; // Phan tu tham chieu mac dinh null.
~~~

Ở đây `a.length` sẽ ném `NullPointerException` vì **bản thân a là null**. `b[0]` bằng `0`; `c[0]` bằng `null`. Việc dùng cùng từ “giá trị mặc định” không có nghĩa các kiểu đều nhận cùng một giá trị.

## 4. `null` không giống giá trị rỗng hoặc giá trị mặc định

| Giá trị | Ý nghĩa |
| --- | --- |
| `null` | Không có tham chiếu đối tượng/mảng |
| `""` | Một `String` tồn tại, có độ dài 0 |
| `"null"` | Một `String` gồm bốn chữ `n-u-l-l` |
| `0` | Giá trị số nguyên 0 |
| `false` | Giá trị boolean false |
| `new int[0]` | Một đối tượng mảng có độ dài 0, **không null** |

Dùng `text == null` khi cần biết có tham chiếu hay không. Dùng `text.isEmpty()` khi đã biết `text` không null và muốn kiểm tra chuỗi rỗng. Có thể kết hợp:

~~~java
if (text == null || text.isEmpty()) {
    System.out.println("Thieu noi dung");
}
~~~

Toán tử `||` có **short-circuit**: nếu `text == null` là true, Java không gọi `text.isEmpty()` ở vế phải, nhờ đó tránh `NullPointerException`.

Khi so sánh nội dung `String`, dùng `Objects.equals(a, b)` để xử lý cả trường hợp null, hoặc `"OK".equals(value)` khi literal chắc chắn không null. Toán tử `==` giữa hai biến kiểu tham chiếu so sánh **cùng tham chiếu hay không**, không phải nội dung.

## 5. Dùng `null` trong trả về, tham số và generic

~~~java
static String findName(boolean found) {
    return found ? "Mai" : null; // Hop le: tra ve String.
}

static int findCount() {
    return 0; // Khong the return null cho int.
}

static void show(String value) {
    System.out.println(value == null ? "(empty)" : value);
}
~~~

- Có thể gọi `show(null)` vì tham số có kiểu tham chiếu `String`.
- `return null;` hợp lệ khi kiểu trả về là kiểu tham chiếu, ví dụ `String`, nhưng không hợp lệ với `int` hoặc phương thức `void`.
- Với generic, `java.util.List<String> items = null;` hợp lệ; nhưng gọi `items.size()` sẽ ném `NullPointerException`.
- Cũng cần phân biệt **tham chiếu danh sách null** với **danh sách tồn tại có phần tử null**. Ví dụ `new java.util.ArrayList<String>()` là danh sách tồn tại; một số API chấp nhận phần tử null, còn `List.of(null)` sẽ ném `NullPointerException`.

Nếu không muốn trả null để báo “không tìm thấy”, có thể cân nhắc `Optional<String>` với `Optional.empty()` hoặc `Optional.ofNullable(value)`. `Optional` là một lựa chọn API, không tự thay đổi quy tắc của literal `null`.

## 6. Bài tập tự kiểm tra

**Bài 1:** Trong `String s = null;` và `String s = "";`, cách nào có thể gọi `s.length()` ngay?

*Đáp án:* Chuỗi rỗng `""`: kết quả 0. Với `null`, lời gọi ném `NullPointerException`.

**Bài 2:** Vì sao `Integer number = null;` biên dịch, còn `int number = null;` không biên dịch?

*Đáp án:* `Integer` là kiểu tham chiếu; `int` là nguyên thủy. Nếu unbox một `Integer` đang null, lỗi phát sinh **khi chạy**.

**Bài 3:** `String[] names = {null};` có hợp lệ không? Còn `char[] chars = {null};`?

*Đáp án:* Cái đầu hợp lệ vì phần tử là `String`; cái sau không vì phần tử `char` là primitive.

**Bài 4:** Sửa `var data = null;` mà vẫn muốn giữ chỗ cho giá trị `String` sau này.

*Đáp án:* Dùng `String data = null;` để nêu rõ kiểu; `var` không suy luận được kiểu từ `null`.

**Bài 5:** Dự đoán `"null".equals((String) null)` và `Objects.equals(null, null)`.

*Đáp án:* Lần lượt `false` và `true`.

## Checklist ghi nhớ

- [ ] `null` là literal, **không phải** số, false hay chuỗi `"null"`.
- [ ] `null` gán được cho kiểu tham chiếu, **không** gán trực tiếp cho primitive.
- [ ] `var x = null` không suy luận được kiểu trên Java 17.
- [ ] Bản thân mảng có thể null; phần tử của mảng primitive thì không.
- [ ] Gán `null` hợp lệ không có nghĩa truy cập phương thức hoặc unboxing là an toàn.
- [ ] Phân biệt lỗi biên dịch với `NullPointerException` lúc chạy.
- [ ] Có thể dùng kiểm tra `== null`, short-circuit `||` và `Objects.equals` khi phù hợp.

**Kết luận:** `null` biểu thị **không có tham chiếu**. Java cho phép nó ở những vị trí cần kiểu tham chiếu, nhưng từ chối trong nơi yêu cầu giá trị primitive. Khi code đã biên dịch, hãy kiểm tra null trước khi dereference hoặc unbox để tránh lỗi runtime.
