# Literal ký tự và literal chuỗi trong Java 17+

Khi viết `'A'` và `"A"`, bạn đang tạo **hai loại giá trị khác nhau**: `'A'` là literal ký tự có kiểu `char`, còn `"A"` là literal chuỗi có kiểu `String`. Nháy đơn, nháy kép, escape và số ký tự bên trong quyết định đoạn mã có hợp lệ hay không.

Bài này giúp bạn khai báo, in, so sánh và xử lý các literal ấy bằng Java 17+, đồng thời tránh nhầm giữa **một đơn vị mã UTF-16** và **một ký tự Unicode đầy đủ**.

## 1. Phân biệt `char` và `String`

| Nội dung | Literal ký tự | Literal chuỗi |
| --- | --- | --- |
| Cú pháp | `'A'` | `"A"` |
| Kiểu Java | `char`, kiểu nguyên thủy (*primitive*) 16 bit | `String`, kiểu tham chiếu bất biến (*immutable*) |
| Số đơn vị mã được biểu diễn | Đúng một đơn vị mã UTF-16 | Có thể là 0, 1 hoặc nhiều đơn vị mã UTF-16 |
| Rỗng | `''` **không hợp lệ** | `""` hợp lệ |
| Dấu xuống dòng | `'\n'` | `"\n"` |
| Ghép nối | Không có phương thức `concat` trên `char` | `"Ja" + "va"` cho `"Java"` |
| Đọc độ dài | Không gọi `.length()` trên `char` | `"Java".length()` trả 4 |

Ví dụ:

~~~java
char grade = 'A';
String gradeText = "A";
String empty = "";
String message = "Xin chao!";
~~~

Dù `grade` và `gradeText` cùng hiển thị chữ A, chúng **không cùng kiểu**. `char` lưu một đơn vị mã (giá trị số nguyên không dấu 16 bit); `String` biểu diễn một dãy các đơn vị mã và cung cấp nhiều phương thức thao tác chuỗi.

Lưu ý: một ký tự Unicode như emoji `🚀` thường cần **hai đơn vị mã UTF-16** (surrogate pair). Do đó `"🚀"` hợp lệ, nhưng không thể chứa trọn emoji ấy trong một literal `char` đơn lẻ.

## 2. Escape và ranh giới `char`/`String`

Trong cả character literal và string literal, dấu gạch chéo ngược bắt đầu một escape. Một escape phù hợp có thể biểu diễn **một đơn vị mã** mà ta không gõ trực tiếp:

| Source Java | Giá trị khi chạy | Kiểu ví dụ |
| --- | --- | --- |
| `'\n'` | Một char LF, mã 10 | `char` |
| `"\n"` | Chuỗi dài 1 đơn vị UTF-16 chứa LF | `String` |
| `'\\'` | Một char dấu backslash | `char` |
| `"\\n"` | Chuỗi gồm backslash và chữ n, độ dài 2 | `String` |
| `'\''` | Một char dấu nháy đơn | `char` |
| `"Say \"hi\""` | Chuỗi chứa hai dấu nháy kép | `String` |

Điều cần kiểm tra là **kiểu và độ dài giá trị sau khi diễn giải literal**, chứ không đếm ký tự gõ trong source. Escape `\t`, `\r`, `\b`, `\f` cũng có công dụng riêng; ví dụ `"\t"` chứa một code unit tab.

Unicode escape như `\u0041` là một cơ chế khác: Java xử lý Unicode escape **trước bước phân tích token** kể cả ở vị trí trông như comment. Do đó không dùng Unicode escape của LF để chèn newline vào string literal thông thường; dùng `"\n"` hoặc `'\n'`. Các ví dụ xử lý backslash, dấu nháy, đường dẫn và nhiều lớp escape sẽ được phân tích kỹ trong bài chuyên về escape sequence.


## 3. Chương trình Java 17+ chạy được

Lưu tệp UTF-8 tên **`CharacterStringDemo.java`**:

~~~java
public class CharacterStringDemo {
    public static void main(String[] args) {
        char first = 'J';
        char newline = '\n';
        char apostrophe = '\'';

        String language = "Java";
        String greeting = "Xin chao, " + language + "!";
        String twoLines = "dong 1\ndong 2";
        String rocket = "🚀";

        String block = """
                Alpha
                Beta
                """;

        System.out.println("char=" + first);
        System.out.println("newlineCode=" + (int) newline);
        System.out.println("apostrophe=" + apostrophe);
        System.out.println("greeting=" + greeting);
        System.out.println("lines=" + twoLines.replace("\n", "|"));
        System.out.println("length=" + language.length());
        System.out.println("rocketUnits=" + rocket.length());
        System.out.println(
                "rocketPoints=" + rocket.codePointCount(0, rocket.length()));
        System.out.println("block=" + block.replace("\n", "|"));
        System.out.println("equals=" + language.equals("Java"));
    }
}
~~~

Mở terminal trong thư mục chứa file (Windows PowerShell hoặc Linux Bash):

~~~bash
java -version
javac -version
javac -encoding UTF-8 CharacterStringDemo.java
java CharacterStringDemo
~~~

**Expected output:**

~~~text
char=J
newlineCode=10
apostrophe='
greeting=Xin chao, Java!
lines=dong 1|dong 2
length=4
rocketUnits=2
rocketPoints=1
block=Alpha|Beta|
equals=true
~~~

Giải thích kết quả đáng chú ý:

1. `(int) newline` chuyển giá trị `char` của LF sang số nguyên `10`.
2. `twoLines` thật sự chứa dấu xuống dòng; `replace("\n", "|")` giúp nhìn thấy ranh giới hai dòng khi in.
3. `rocket.length() == 2` vì emoji U+1F680 chiếm hai đơn vị mã UTF-16. `codePointCount(...) == 1` vì đó là một Unicode code point.
4. Text block `""" ... """` hỗ trợ từ Java 15, nên dùng được trong Java 17. Literal này chứa xuống dòng và loại bỏ phần thụt lề chung; do có xuống dòng ở cuối, phép `replace` cho `Alpha|Beta|`.
5. `equals` so sánh **nội dung chuỗi**, không dựa vào việc hai biến tham chiếu cùng một đối tượng.

Bạn có thể thử `java CharacterStringDemo.java` trên JDK 17+ để chạy trực tiếp tệp nguồn mà không cần gọi `javac` riêng. Kết quả chương trình vẫn như trên.

## 4. Khi cần chuỗi nhiều dòng: text block

Java 17 hỗ trợ text block `"""` (ổn định từ Java 15), vẫn cho ra **`String`**, không phải một kiểu ký tự mới. Dấu mở `"""` phải có dấu xuống dòng theo sau; compiler loại thụt lề chung để trình bày source thuận tiện:

~~~java
String normal = "A\nB";
String multi = """
        A
        B
        """;
~~~

Hai chuỗi trên không hoàn toàn bằng nhau: `multi` có **newline cuối**, còn `normal` thì không. Dấu đóng ngay sau `B` thay vì ở dòng riêng là một cách bỏ newline cuối. Text block có thể chứa dấu nháy kép thông thường và escape, nhưng dấu cách đầu/cuối còn chịu quy tắc xử lý thụt lề và khoảng trắng riêng. Khi cần nội dung chính xác, hãy kiểm tra bằng `length()` hoặc biểu diễn newline hiện rõ; các thao tác `\s`, nối dòng và vị trí dấu đóng được đi sâu trong bài text block.


## 5. Các lỗi thường gặp

| Đoạn mã | Kết quả | Cách sửa |
| --- | --- | --- |
| `char c = 'A';` | Hợp lệ | Một literal `char` |
| `String s = "A";` | Hợp lệ | Một literal `String` |
| `char c = '';` | Lỗi biên dịch | `char` phải chứa một đơn vị mã; nếu cần rỗng, dùng `String s = "";` |
| `char c = 'AB';` | Lỗi biên dịch | Dùng `String s = "AB";` |
| `String s = 'A';` | Lỗi kiểu dữ liệu | Dùng `String s = "A";` |
| `char c = "A";` | Lỗi kiểu dữ liệu | Dùng `char c = 'A';` |
| `String s = "C:\temp";` | Có thể sai ý định: `\t` là tab | Dùng `"C:\\temp"` |
| `String s = "a\nb";` | Hợp lệ: chứa xuống dòng lúc chạy | Nếu muốn thấy `\n` dưới dạng chữ, dùng `"a\\nb"` |
| `String s = "a" + "b";` | Hợp lệ | Cho kết quả nội dung `ab` |

**So sánh chuỗi:** tránh dùng `==` để kiểm tra nội dung hai `String` bất kỳ. `==` so sánh tham chiếu; `equals` so sánh nội dung. Trong ví dụ đang chạy, `language.equals("Java")` cho `true`.

**Bất biến:** `String` không thay đổi nội dung sau khi tạo. Ví dụ gọi `language.concat(" 17")` trả về **chuỗi mới**, không sửa giá trị `language` nếu bạn không gán kết quả.

## 6. Bài tập ngắn

**Bài 1.** Chọn kiểu đúng cho một chữ `K` và một chuỗi `"K"`; giải thích vì sao `'KK'` không hợp lệ.

*Đáp án:* `char c = 'K';` và `String s = "K";`. `'KK'` có hai đơn vị mã, không phải một `char`.

**Bài 2.** Dự đoán `"Hi\nJava".length()` và `"Hi\\nJava".length()`.

*Đáp án:* `7` và `8`. Chuỗi thứ nhất chứa một ký tự LF; chuỗi thứ hai chứa hai ký tự backslash và chữ `n`.

**Bài 3.** Trong `CharacterStringDemo`, thay `language = "Java"` bằng `"Kotlin"`. Giá trị `greeting` và `equals` sẽ thế nào?

*Đáp án:* `Xin chao, Kotlin!` và `false`.

**Bài 4.** Viết literal chứa chính xác dòng văn bản `C:\work\java`.

*Đáp án:* `"C:\\work\\java"`.

**Bài 5.** Vì sao `"🚀".length()` bằng 2 nhưng `codePointCount` bằng 1?

*Đáp án:* Một code point ngoài BMP được mã hóa bằng **hai UTF-16 code unit**. `String.length()` đếm code unit; `codePointCount` đếm code point (không nhất thiết bằng số *grapheme cluster* mà mắt người thấy).

## Ghi nhớ

- **`'A'` → `char`** (một đơn vị mã UTF-16); **`"A"` → `String`** (dãy ký tự, có thể rỗng).
- Dùng `\n`, `\t`, `\`, `\"`, `\'` đúng chỗ; phân biệt **escape của string** và **Unicode escape xử lý trước token**.
- `String` là immutable; so sánh nội dung bằng `equals`; `length()` đếm UTF-16 code unit.
- **Text block** `""" ... """` cũng là một `String`, hữu ích cho nội dung nhiều dòng trên Java 17+.
