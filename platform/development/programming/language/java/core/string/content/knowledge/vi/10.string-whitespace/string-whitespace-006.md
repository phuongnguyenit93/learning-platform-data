# Phân biệt null, chuỗi rỗng và dữ liệu chỉ có khoảng trắng trong Java

Trong Java, **null**, **chuỗi rỗng** (`""`) và **chuỗi chỉ chứa khoảng trắng** là ba trạng thái khác nhau. Chúng thường cùng xuất hiện khi nhận dữ liệu từ biểu mẫu, tệp cấu hình, cơ sở dữ liệu hoặc API, nhưng cách kiểm tra và ý nghĩa nghiệp vụ không giống nhau.

- **null**: biến tham chiếu không trỏ đến một đối tượng String.
- **Chuỗi rỗng `""`**: có đối tượng String hợp lệ, nhưng độ dài bằng 0.
- **Chuỗi trắng** (*blank string*): chuỗi rỗng hoặc chuỗi mà mọi code point đều được Java xem là *whitespace*. Ví dụ `"   "`, `"\t\n"` là blank; `" A "` không blank.

Chọn đúng phép kiểm tra giúp tránh **NullPointerException**, tránh chấp nhận dữ liệu chỉ có khoảng trắng và giữ nguyên sự khác biệt giữa “không cung cấp dữ liệu” và “cung cấp một chuỗi rỗng”.

## 1. Ba trạng thái: khác nhau về đối tượng và nội dung

Xem đoạn minh họa sau:

~~~java
String absent = null;
String empty = "";
String spaces = "   ";
String padded = " Java ";
~~~

| Giá trị | Có đối tượng String? | length() | isEmpty() | isBlank() |
|---|---|---:|---|---|
| `null` | Không | Không gọi được | Không gọi được | Không gọi được |
| `""` | Có | 0 | true | true |
| `"   "` | Có | 3 | false | true |
| `"\t\n"` | Có | 2 | false | true |
| `" Java "` | Có | 6 | false | false |
| `"Java"` | Có | 4 | false | false |

Các ô “không gọi được” không có nghĩa là phương thức trả về false: **gọi `absent.length()`, `absent.isEmpty()` hoặc `absent.isBlank()` khi absent là null sẽ ném NullPointerException**.

Hai String có độ dài khác 0 vẫn có thể chỉ chứa whitespace. Vì vậy, **isEmpty() không thay thế được isBlank()** trong việc kiểm tra đầu vào không có văn bản có ý nghĩa.

Một điểm cần nhớ: String là immutable. Việc gọi `strip()` hay `trim()` tạo/trả về giá trị String thích hợp, không biến đổi nội dung String gốc; `null` thì không phải String nên không có phương thức để gọi.

## 2. null: trạng thái không có tham chiếu String

Khai báo `String value = null;` tạo một biến tham chiếu có giá trị null, **không tạo một đối tượng String chứa từ “null”**.

~~~java
String value = null;

System.out.println(value == null);   // true
System.out.println(value != null);   // false
System.out.println("".equals(value)); // false
~~~

Những biểu thức so sánh tham chiếu `== null` và `!= null` là hợp lệ. Một String literal như `""` luôn là receiver không-null, nên `"".equals(value)` an toàn và trả về false nếu value null.

Ngược lại, đoạn sau gây lỗi:

~~~java
String value = null;
System.out.println(value.isEmpty()); // NullPointerException
~~~

Đây là **đoạn minh họa tình huống lỗi**, không phải một chương trình đầy đủ cần chạy chung với các ví dụ khác. Java không thể gọi phương thức instance trên tham chiếu null.

### null có đồng nghĩa dữ liệu sai không?

Không nhất thiết. Trong nhiều API, null thể hiện **vắng mặt/không được cung cấp**; ở nơi khác, null là dữ liệu không hợp lệ. Ý nghĩa do hợp đồng dữ liệu quyết định:

- Trường tùy chọn không gửi lên có thể được biểu diễn bằng null.
- Một trường bắt buộc có thể **từ chối null** bằng validation.
- Khi cập nhật từng phần (*partial update*), “không gửi trường” và “gửi trường có null” thậm chí có thể mang ý nghĩa khác nhau. Một biến String đơn lẻ không đủ biểu diễn cả ba trạng thái “không có trường”, “null” và “chuỗi có giá trị”; cần một cấu trúc/hợp đồng phù hợp nếu nghiệp vụ đòi hỏi.

**Đừng tự động chuyển null thành `""` ở mọi ranh giới hệ thống**, vì làm vậy có thể đánh mất thông tin “người dùng chưa cung cấp” so với “người dùng cố ý để rỗng”.

## 3. Chuỗi rỗng: `""`, length() và isEmpty()

Chuỗi rỗng là một đối tượng String có **0 đơn vị mã UTF-16**:

~~~java
String empty = "";
System.out.println(empty.length());  // 0
System.out.println(empty.isEmpty()); // true
System.out.println(empty.isBlank()); // true
~~~

`isEmpty()` được định nghĩa tương đương kiểm tra `length() == 0`. Nó không duyệt hay bỏ qua khoảng trắng:

~~~java
System.out.println(" ".isEmpty());   // false
System.out.println("\t".isEmpty());  // false
System.out.println("\n".isEmpty());  // false
System.out.println(" x ".isEmpty()); // false
~~~

Với bất kỳ String không-null nào, `s.isEmpty()` chỉ true khi **không có đơn vị mã nào**.

### Khác biệt giữa `""` và `"null"`

~~~java
String absent = null;
String word = "null";

System.out.println(absent == null); // true
System.out.println(word == null);   // false
System.out.println(word.isEmpty()); // false
System.out.println(word.isBlank()); // false
~~~

Chuỗi `"null"` gồm bốn chữ cái n, u, l, l; nó **không** phải giá trị null. Một số cách chuyển đổi như `String.valueOf((Object) null)` tạo chuỗi chữ `"null"`; việc hiển thị chữ này không có nghĩa dữ liệu gốc đã có giá trị văn bản từ người dùng.

## 4. Chuỗi trắng và String.isBlank() từ Java 11

`String.isBlank()` có từ Java 11. Nó trả về true khi **chuỗi rỗng hoặc chỉ bao gồm các code point mà Character.isWhitespace(int) xác định là whitespace**.

~~~java
System.out.println("".isBlank());       // true
System.out.println("   ".isBlank());    // true
System.out.println("\t\n".isBlank());   // true
System.out.println(" A ".isBlank());    // false
System.out.println("0".isBlank());      // false
~~~

`isBlank()` là kiểm tra **nội dung**, không phải thao tác xóa ký tự. Nó không thay đổi String. Một chuỗi có một chữ cái, chữ số hoặc dấu câu không thuộc tập whitespace sẽ trả về false, dù trước và sau có nhiều dấu cách.

### Những khoảng trắng không nhất thiết là dấu cách ASCII

Whitespace trong Java bao gồm nhiều ký tự như tab, xuống dòng và một số dấu cách Unicode. Khác biệt đáng chú ý:

| Ký tự | Mã Unicode | Character.isWhitespace | isBlank() cho chuỗi chỉ chứa ký tự đó |
|---|---|---|---|
| Dấu cách ASCII | U+0020 | true | true |
| Tab | U+0009 | true | true |
| Xuống dòng LF | U+000A | true | true |
| EM SPACE | U+2003 | true | true |
| NO-BREAK SPACE (NBSP) | U+00A0 | false | false |

**NBSP (U+00A0) là ví dụ quan trọng:** người dùng có thể nhìn thấy nó giống một dấu cách thông thường, nhưng `Character.isWhitespace` không coi nó là whitespace. Vì thế, **một String chỉ chứa NBSP không được `isBlank()` coi là blank**.

Điều này không phải lỗi của isBlank(); đó là quy tắc phân loại cụ thể của API. `Character.isSpaceChar` có tập nhận diện không giống `Character.isWhitespace`; đừng đánh đồng hai phương thức.

Nếu nghiệp vụ cần coi cả NBSP, zero-width space hoặc các ký tự định dạng đặc biệt là “không có dữ liệu”, phải **định nghĩa rõ danh sách/khuôn mẫu ký tự được phép bỏ qua**, đồng thời cân nhắc các rủi ro khi chuẩn hóa dữ liệu Unicode. Không có một phép kiểm tra duy nhất mặc nhiên đúng cho mọi ngôn ngữ và mọi biểu mẫu.

## 5. Phân biệt kiểm tra và biến đổi chuỗi

`isEmpty()` kiểm tra đúng độ dài 0; `isBlank()` hỏi chuỗi có rỗng hoặc chỉ gồm `Character.isWhitespace` hay không. Cả hai chỉ trả về `boolean`. Ngược lại, `trim()` và `strip()` trả về một chuỗi đã cắt **hai mép** theo hai quy tắc khác nhau; chúng không sửa đối tượng String gốc.

~~~java
String em = "\u2003";
String nbsp = "\u00A0";
System.out.println(em.isBlank());           // true
System.out.println(em.trim().isEmpty());    // false
System.out.println(em.strip().isEmpty());   // true
System.out.println(nbsp.isBlank());         // false
System.out.println(nbsp.strip().isEmpty()); // false
~~~

`trim()` xét đơn vị mã `char <= U+0020`, còn `strip()` và `isBlank()` theo Java whitespace; NBSP không thuộc tập sau. Trong bài này, điểm quan trọng hơn là **cả bốn đều cần một String không-null để gọi**. Xử lý `null` trước, rồi quyết định giữ nguyên hay chuẩn hóa dựa trên ý nghĩa của từng trường. Không nên tự biến `null` thành `""` chỉ để gọi được các phương thức này.

## 6. So sánh phương thức theo từng trạng thái

Giả sử `s` là String **không-null**:

| Trạng thái s | s.isEmpty() | s.isBlank() | s.strip().isEmpty() |
|---|---|---|---|
| `""` | true | true | true |
| `"   "` | false | true | true |
| `"\t\n"` | false | true | true |
| `" Java "` | false | false | false |
| `"\u2003"` (EM SPACE) | false | true | true |
| `"\u00A0"` (NBSP) | false | false | false |
| `"0"` | false | false | false |

Trong kiểm tra chuỗi trống hoặc chỉ chứa whitespace theo định nghĩa Java, `isBlank()` trực tiếp, ngắn và dễ đọc hơn việc chỉ kiểm tra `strip().isEmpty()`. Không cần tạo chuỗi sau khi strip nếu chỉ cần boolean.

Với **null**, mọi lời gọi instance ở bảng đều gây NullPointerException. Vì vậy, cần tách riêng kiểm tra null hoặc bảo đảm API không bao giờ trả về null.

## 7. Viết điều kiện an toàn khi dữ liệu có thể null

### 7.1. Kiểm tra null bằng `== null`

~~~java
String input = null;

if (input == null) {
    System.out.println("Missing");
}
~~~

`null` là giá trị tham chiếu đặc biệt, không phải String. Đây là trường hợp dùng `==` hợp lý. Ngược lại, khi **so sánh nội dung của hai String**, nên dùng `equals()` theo ngữ nghĩa cần thiết.

### 7.2. Null hoặc rỗng: kiểm tra kết hợp có short-circuit

~~~java
static boolean isNullOrEmpty(String s) {
    return s == null || s.isEmpty();
}
~~~

Đây là **phương thức minh họa**, cần đặt bên trong một lớp Java. Toán tử `||` có đánh giá ngắn mạch: nếu `s == null` true, Java không chạy `s.isEmpty()` nên tránh NullPointerException.

Kết quả dự kiến:

- `isNullOrEmpty(null)` → true.
- `isNullOrEmpty("")` → true.
- `isNullOrEmpty("   ")` → false.

### 7.3. Null hoặc blank: chặn dữ liệu chỉ có whitespace

~~~java
static boolean isNullOrBlank(String s) {
    return s == null || s.isBlank();
}
~~~

Hàm trả true cho null, `""` và `"   "`, nhưng trả false cho `" Java "` hoặc `"\u00A0"` (NBSP).

Nếu cần kiểm tra giá trị **có nội dung theo quy tắc whitespace của Java**, dùng:

~~~java
static boolean hasText(String s) {
    return s != null && !s.isBlank();
}
~~~

Toán tử `&&` cũng đánh giá ngắn mạch. Nếu s null thì vế `!s.isBlank()` không được chạy. Cách này thường phù hợp cho trường nhập tên, tiêu đề hoặc từ khóa tìm kiếm bắt buộc có nội dung.

### 7.4. Khi hai giá trị có thể null

`java.util.Objects.equals(a, b)` trả true khi cả hai cùng null, false khi chỉ một bên null, và so sánh theo `a.equals(b)` khi a không-null:

~~~java
System.out.println(java.util.Objects.equals(null, null)); // true
System.out.println(java.util.Objects.equals(null, ""));   // false
System.out.println(java.util.Objects.equals("", ""));     // true
~~~

Quy tắc này hữu ích khi so sánh hai trạng thái nullable. Nó **không** thay cho kiểm tra blank: `Objects.equals("", "   ")` vẫn false và `Objects.equals(null, "")` cũng false.

## 8. Chương trình Java 17+ đầy đủ

Ví dụ này kiểm tra rõ các giá trị null, rỗng, khoảng trắng ASCII, tab/xuống dòng, EM SPACE, NBSP và chuỗi có chữ. Nhãn được in riêng để không dựa vào cách terminal hiển thị ký tự vô hình.

Lưu thành tệp **BlankStringDemo.java** với mã UTF-8:

~~~java
public class BlankStringDemo {
    private static boolean isNullOrBlank(String s) {
        return s == null || s.isBlank();
    }

    private static boolean hasText(String s) {
        return s != null && !s.isBlank();
    }

    public static void main(String[] args) {
        String[] values = {
                null, "", "   ", " \t\n", " Java ",
                "Java", "\u2003", "\u00A0"
        };
        String[] labels = {
                "null", "empty", "spaces", "tabs",
                "padded", "word", "em-space", "nbsp"
        };

        for (int i = 0; i < values.length; i++) {
            String s = values[i];
            System.out.printf(
                    "%s: null=%s empty=%s blank=%s%n",
                    labels[i], s == null,
                    s != null && s.isEmpty(),
                    s != null && s.isBlank()
            );
        }

        System.out.println("nullOrBlank(null)=" + isNullOrBlank(null));
        System.out.println("nullOrBlank(spaces)=" + isNullOrBlank("   "));
        System.out.println("hasText(Java)=" + hasText("  Java  "));
        System.out.println("hasText(spaces)=" + hasText("   "));

        String emSpace = "\u2003";
        String nbsp = "\u00A0";
        System.out.println("trim-em-empty=" + emSpace.trim().isEmpty());
        System.out.println("strip-em-empty=" + emSpace.strip().isEmpty());
        System.out.println("trim-nbsp-empty=" + nbsp.trim().isEmpty());
        System.out.println("strip-nbsp-empty=" + nbsp.strip().isEmpty());

        String input = "  Java  ";
        String clean = input.strip();
        System.out.println("original=[" + input + "]");
        System.out.println("clean=[" + clean + "]");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 BlankStringDemo.java
java BlankStringDemo
~~~

Đầu ra chính xác:

~~~text
null: null=true empty=false blank=false
empty: null=false empty=true blank=true
spaces: null=false empty=false blank=true
tabs: null=false empty=false blank=true
padded: null=false empty=false blank=false
word: null=false empty=false blank=false
em-space: null=false empty=false blank=true
nbsp: null=false empty=false blank=false
nullOrBlank(null)=true
nullOrBlank(spaces)=true
hasText(Java)=true
hasText(spaces)=false
trim-em-empty=false
strip-em-empty=true
trim-nbsp-empty=false
strip-nbsp-empty=false
original=[  Java  ]
clean=[Java]
~~~

Cần quan sát:

1. Biến null được kiểm tra trước bằng `s == null`, nên không có lời gọi phương thức trên null.
2. Chuỗi rỗng cho cả `empty=true` và `blank=true`.
3. Chuỗi gồm dấu cách/tab/xuống dòng có `empty=false`, `blank=true`.
4. Chuỗi có chữ `" Java "` không được xem là blank dù có khoảng trắng đầu/cuối.
5. EM SPACE là blank và được `strip()` loại bỏ; NBSP không được `isBlank()` hay `strip()` nhận là whitespace.
6. `strip()` trả chuỗi kết quả, không sửa biến `input`.

## 9. Chọn chính sách chuẩn hóa theo nghiệp vụ

Một hệ thống thực tế thường phải quyết định **những trạng thái nào cần phân biệt**:

| Tình huống | Chính sách gợi ý | Giải thích |
|---|---|---|
| Tên hiển thị bắt buộc | Từ chối null hoặc `isBlank()` | Không chấp nhận thiếu dữ liệu, rỗng hoặc chỉ whitespace |
| Từ khóa tìm kiếm tùy chọn | Có thể coi null/blank là “không có bộ lọc” | Thuận tiện cho người dùng; phải ghi rõ hợp đồng API |
| Mã định danh hoặc mật khẩu | Không tự strip/trim nếu không được đặc tả | Khoảng trắng có thể là dữ liệu hợp lệ và có ý nghĩa |
| Văn bản người dùng tự do | Giữ nguyên nếu cần bảo toàn | Việc loại bỏ whitespace có thể làm thay đổi nội dung mong muốn |
| Cập nhật một phần dữ liệu | Phân biệt không gửi trường, null, `""` nếu cần | Ba trạng thái có thể dẫn đến hành vi cập nhật khác nhau |
| So sánh thay đổi giữa hai chuỗi nullable | Dùng `Objects.equals(old, next)` | Giữ khác biệt null và chuỗi rỗng |
| Làm sạch dữ liệu theo quy tắc Java whitespace | `strip()` sau khi bảo đảm không-null | Hỗ trợ nhiều whitespace Unicode hơn `trim()` |

Một quy trình nhập tên hiển thị có thể là: nhận nullable String → kiểm tra null → dùng `strip()` nếu sản phẩm cho phép loại bỏ whitespace đầu/cuối → kiểm tra kết quả `isEmpty()` hoặc `isBlank()` → lưu kết quả. Tuy nhiên, **không dùng một quy trình chuẩn hóa duy nhất cho mọi trường**. Với mật khẩu, đoạn văn định dạng hay dữ liệu có chữ ký số, việc thay đổi khoảng trắng có thể phá vỡ ý nghĩa và tính toàn vẹn của dữ liệu.

### Ví dụ chuẩn hóa có chủ đích

~~~java
static String normalizeOptionalTitle(String title) {
    if (title == null) {
        return null;
    }

    String cleaned = title.strip();
    return cleaned.isEmpty() ? null : cleaned;
}
~~~

Đây là **phương thức minh họa**: null giữ nguyên; chuỗi rỗng hoặc chỉ whitespace theo `strip()` được biến thành null; tên có nội dung được cắt whitespace hai đầu. Hành vi đó chỉ đúng khi **hợp đồng nghiệp vụ cho phép coi các giá trị trắng như dữ liệu vắng mặt**.

Một phương án khác là giữ chuỗi rỗng riêng và chỉ từ chối blank khi cần validation:

~~~java
static void requireNonBlank(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Value must contain text");
    }
}
~~~

Cả hai đoạn trên phải được đặt trong một lớp để biên dịch; chúng minh họa **hai chính sách khác nhau**, không nên áp dụng đồng thời mà không có mục đích rõ.

## 10. Unicode: vì sao dữ liệu nhìn trống đôi khi isBlank() lại false?

Có những ký tự hiển thị ít hoặc không có dấu vết trên màn hình nhưng **không thuộc bộ ký tự whitespace mà Java dùng cho `isBlank()`**. NBSP là trường hợp thường gặp khi sao chép nội dung từ HTML. Một số ký tự định dạng không có độ rộng hiển thị cũng có thể xuất hiện trong dữ liệu.

Điều này dẫn đến ba lưu ý:

1. **Không suy luận dữ liệu là trống từ cách nó hiển thị trên màn hình.** Cần kiểm tra mã Unicode nếu kết quả bất ngờ.
2. **Không tự xóa mọi ký tự vô hình một cách tùy tiện.** Một số ký tự có tác dụng ngôn ngữ hoặc định dạng hợp lệ; xóa chúng có thể làm thay đổi dữ liệu.
3. **Cần xác định chính sách đầu vào:** ứng dụng muốn nhận dạng whitespace theo `Character.isWhitespace`, theo tập Unicode rộng hơn, theo cấu hình giao diện hay theo quy tắc chuyên biệt?

Ví dụ so sánh hai predicate:

~~~java
int nbsp = 0x00A0;
System.out.println(Character.isWhitespace(nbsp)); // false
System.out.println(Character.isSpaceChar(nbsp));   // true
~~~

`Character.isWhitespace` và `Character.isSpaceChar` có hợp đồng khác nhau. Java String.isBlank() dựa vào `isWhitespace`, nên kết quả cho NBSP là false.

Nếu phải xác định trạng thái “chỉ có các ký tự vô hình” theo chính sách riêng, hãy viết hàm kiểm tra **từng code point** và áp dụng bộ predicate do ứng dụng lựa chọn. Tránh ép index UTF-16 thành số thứ tự code point; dùng `codePoints()` hoặc phương thức duyệt code point phù hợp.

## 11. Các lỗi phổ biến

1. **Gọi `isEmpty()` trên null:** `s.isEmpty()` gây NullPointerException nếu s null. Kiểm tra trước bằng `s == null` hoặc bảo đảm hợp đồng đầu vào không-null.
2. **Chỉ dùng `isEmpty()` khi cần từ chối khoảng trắng:** `"   ".isEmpty()` là false; dùng `isBlank()` cho yêu cầu không có ký tự nội dung.
3. **Xem `""` và null là cùng một giá trị:** chuỗi rỗng là String tồn tại; null là không có tham chiếu. Chúng có thể mang ý nghĩa khác nhau trong API, JSON, database và quy tắc cập nhật.
4. **Cho rằng `strip()` luôn xử lý được mọi dấu cách nhìn thấy:** `strip()` dựa trên `Character.isWhitespace` nên không loại NBSP.
5. **Dùng `trim()` với kỳ vọng hỗ trợ tất cả whitespace Unicode:** `trim()` chỉ loại bỏ các đơn vị mã <= U+0020 ở hai đầu, không phải thuật toán phân loại whitespace Unicode.
6. **Tự chuyển null thành chữ `"null"`:** phép chuyển thành văn bản hiển thị không giữ được semantics vắng mặt; kiểm tra thiết kế dữ liệu trước khi chuyển đổi.
7. **Gọi `strip()` rồi quên nhận kết quả:** String bất biến; `input.strip();` không sửa `input`.
8. **Dùng `==` để so sánh nội dung String:** `== null` là cách kiểm tra null hợp lệ, nhưng `s == ""` không phải kiểm tra nội dung rỗng đáng tin cậy. Dùng `isEmpty()` sau null-check hoặc `"".equals(s)`.
9. **Tự cắt whitespace của mã định danh/mật khẩu:** một số hệ thống coi whitespace là thành phần quan trọng; làm sạch dữ liệu phải theo chính sách đã xác định.
10. **Mặc định chuỗi rỗng là đầu vào không hợp lệ trong mọi trường hợp:** nhiều trường cho phép giá trị rỗng có chủ đích, ví dụ mô tả tùy chọn; hãy căn cứ hợp đồng nghiệp vụ.
11. **Tin rằng dùng `isBlank()` là kiểm tra mọi dạng dữ liệu “không nhìn thấy”:** NBSP hoặc ký tự định dạng có thể làm kết quả false. Quy tắc Java whitespace khác với quy tắc hiển thị.
12. **Bỏ qua phiên bản JDK:** `isBlank()` và `strip()` có từ Java 11; mã Java 17+ dùng được. Dự án Java 8 phải tự dùng cách khác nếu cần cùng chính sách.

## 12. Bài tập tự kiểm tra

Cho đoạn:

~~~java
String a = null;
String b = "";
String c = " \t ";
String d = "\u2003";
String e = "\u00A0";
String f = " A ";
~~~

Hãy tự trả lời:

1. Giá trị nào bằng null?
2. Giá trị nào có `isEmpty() == true` nếu chỉ gọi trên đối tượng không-null?
3. Giá trị nào có `isBlank() == true`?
4. Gọi `a.isBlank()` tạo kết quả boolean nào hay gây ngoại lệ?
5. `d.trim().isEmpty()` và `d.strip().isEmpty()` khác nhau thế nào?
6. `e.isBlank()` có phải true vì NBSP trông giống dấu cách không?
7. Nếu ứng dụng coi cả null và blank là thiếu dữ liệu, nên viết điều kiện nào?
8. Vì sao không nên tự strip một mật khẩu trước khi so sánh?

**Đáp án:**

1. Chỉ **a** là null.
2. Chỉ **b** rỗng thực sự.
3. **b, c, d** là blank theo `Character.isWhitespace`.
4. **NullPointerException**, vì a không tham chiếu String.
5. `d.trim().isEmpty()` **false**, còn `d.strip().isEmpty()` **true**.
6. **false**; NBSP không được `Character.isWhitespace` xem là whitespace.
7. `value == null || value.isBlank()`, tận dụng short-circuit.
8. Khoảng trắng có thể là ký tự hợp lệ trong mật khẩu; strip làm thay đổi dữ liệu người dùng đưa vào.

**Ghi nhớ:** **null = không có đối tượng; `""` = String có độ dài 0; blank = String rỗng hoặc chỉ chứa whitespace theo định nghĩa Java.** Dùng `== null` để kiểm tra tham chiếu, `isEmpty()` để kiểm tra độ dài 0, `isBlank()` để kiểm tra nội dung trắng; luôn kiểm tra null trước khi gọi phương thức instance.
