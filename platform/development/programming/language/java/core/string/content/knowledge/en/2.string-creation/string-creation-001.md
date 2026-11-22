# Literal chuỗi và cú pháp dấu nháy kép trong Java

## 1. Literal chuỗi là gì?

**String literal** (literal chuỗi) là một đoạn văn bản được viết trực tiếp trong mã nguồn Java và đặt giữa **hai dấu nháy kép** ASCII (`"`). Nó biểu diễn một đối tượng `String` chứa dãy ký tự tương ứng.

```java
String greeting = "Xin chào, Java!";
String empty = "";
String numberAsText = "123";
```

- `"Xin chào, Java!"` và `"123"` đều là biểu thức kiểu `String`, dù nội dung có chữ hay chữ số.
- `""` là **chuỗi rỗng**, có độ dài bằng `0`, không phải `null`.
- Dấu nháy kép **đánh dấu ranh giới** của literal; chúng không trở thành ký tự trong chuỗi.
- `String` là lớp `java.lang.String`; Java tự import `java.lang`, nên không cần câu lệnh `import` riêng.

Đọc `String greeting = "Xin chào, Java!";` theo hai phần: `String greeting` khai báo biến tham chiếu kiểu `String`, còn `"Xin chào, Java!"` là literal dùng để khởi tạo giá trị. Tên biến, kiểu dữ liệu và literal là các thành phần khác nhau.

## 2. Quy tắc cú pháp của dấu nháy kép

Cú pháp cơ bản:

```java
String variableName = "nội dung";
```

1. Literal chuỗi thông thường **mở bằng `"` và đóng bằng `"`** trên cùng một dòng nguồn; trình biên dịch xác định chuỗi kết thúc ở dấu `"` không được escape tiếp theo.
2. Nội dung có thể không có ký tự nào (`""`), có dấu cách (`" "`), ký tự tiếng Việt, ký hiệu, hoặc các **escape sequence** hợp lệ.
3. Muốn đưa một dấu `"` thành **nội dung** của chuỗi, phải viết `\"`. Muốn đưa dấu gạch chéo ngược `\` thành nội dung, phải viết `\\`.
4. Trong literal thông thường, không được chèn trực tiếp một ký tự xuống dòng của mã nguồn ở giữa hai dấu nháy; dùng `\n` để biểu diễn xuống dòng.

Các ví dụ minh họa cú pháp, **không phải chương trình hoàn chỉnh**:

```java
String a = "Java";                 // Hợp lệ
String b = "";                     // Hợp lệ: chuỗi rỗng
String c = " ";                    // Hợp lệ: một dấu cách
String d = "Anh ấy nói: \"Chào\"";  // Hợp lệ: chứa dấu nháy kép
String e = "Dòng 1\nDòng 2";       // Hợp lệ: có ký tự xuống dòng khi chạy
```

Phân biệt dấu nháy:

| Cách viết | Kiểu / ý nghĩa | Ghi chú |
|---|---|---|
| `"A"` | `String` | Một chuỗi dài 1 ký tự |
| `'A'` | `char` | Một giá trị ký tự |
| `""` | `String` | Chuỗi rỗng |
| `"null"` | `String` | Văn bản gồm 4 chữ cái |
| `null` | Literal `null` | Không tham chiếu đến đối tượng nào |

Ví dụ: `String value = 'A';` **không biên dịch** vì `'A'` là `char`, không phải `String`. Muốn gán một chuỗi, viết `String value = "A";`.

## 3. Escape sequence trong literal chuỗi

Dấu `\` mở đầu một **escape sequence**: cách viết đặc biệt trong mã nguồn để đưa ký tự khó gõ trực tiếp hoặc có ý nghĩa cú pháp vào chuỗi.

| Viết trong mã nguồn | Ký tự được tạo ra | Tình huống thường gặp |
|---|---|---|
| `\"` | `"` | Hiển thị dấu nháy kép |
| `\\` | `\` | Đường dẫn Windows, ký tự gạch chéo ngược |
| `\n` | Xuống dòng (line feed) | Văn bản nhiều dòng |
| `\t` | Tab ngang | Phân cách cột |

Các escape còn lại như `\r`, `\b`, `\f`, `\s` và `\'` được trình bày đầy đủ ở bài chuyên về escape ngay sau bài này.

Phân biệt **mã nguồn** và **giá trị thực**:

```java
String newline = "\n";      // Chứa 1 ký tự xuống dòng, không chứa '\' và 'n'
String letters = "\\n";     // Chứa 2 ký tự: '\' và 'n'
String quote = "\"";        // Chứa 1 ký tự: '"'
String windowsPath = "C:\\temp\\log.txt";
```

Đặc biệt, viết đường dẫn như `"C:\temp\log.txt"` là sai ý định: `\t` sẽ thành tab còn `\l` không phải escape hợp lệ nên trình biên dịch báo lỗi. Nếu cần biểu diễn dấu `\` thật, dùng `\\`.

Một escape không được Java nhận biết, chẳng hạn `"\q"`, sẽ gây lỗi biên dịch (*illegal escape character*), không âm thầm giữ nguyên dấu `\`.

### Unicode trong chuỗi

Java có thể dùng ký tự Unicode trực tiếp, chẳng hạn `"Tiếng Việt"`, khi tệp nguồn được đọc đúng encoding. Dạng `\u0041` tạo ký tự `A` ở giai đoạn dịch mã nguồn, **trước khi** phân tích literal. Vì vậy không dùng `\u000A` để viết ký tự xuống dòng trong literal: hãy dùng `\n`. Cơ chế và các bẫy này được phân tích trong bài Unicode escape riêng.

## 4. Ví dụ Java 17+ có thể chạy

Lưu tệp **`StringLiteralDemo.java`** với nội dung:

```java
public class StringLiteralDemo {
    public static void main(String[] args) {
        String greeting = "Xin chào, Java!";
        String empty = "";
        String quoted = "Bạn nói: \"Java\"";
        String path = "C:\\docs\\note.txt";
        String twoLines = "Dòng 1\nDòng 2";
        String tabSeparated = "A\tB";

        System.out.println(greeting);
        System.out.println("empty.length() = " + empty.length());
        System.out.println(quoted);
        System.out.println(path);
        System.out.println(twoLines);
        System.out.println(tabSeparated.replace("\t", "[TAB]"));
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac -encoding UTF-8 StringLiteralDemo.java
java StringLiteralDemo
```

**Stdout** (mỗi dòng đúng thứ tự; ví dụ thay tab bằng `[TAB]` để nhìn thấy vị trí tab):

```text
Xin chào, Java!
empty.length() = 0
Bạn nói: "Java"
C:\docs\note.txt
Dòng 1
Dòng 2
A[TAB]B
```

Giải thích:

- Literal `""` tạo chuỗi rỗng nên `empty.length()` là `0`.
- Trong `quoted`, `\"` tạo dấu nháy kép xuất hiện ở stdout.
- Trong `path`, mỗi `\\` tạo ra **một** dấu `\`.
- Trong `twoLines`, `\n` làm `println` hiển thị hai dòng nội dung.
- `\t` tạo tab thật; `replace` chỉ đổi tab thành nhãn dễ quan sát lúc in kết quả.

## 5. Literal chuỗi, biến và đối tượng String

### Literal có thể dùng ở nhiều vị trí

Literal là **biểu thức** kiểu `String`, không chỉ xuất hiện bên phải phép gán:

```java
System.out.println("Sẵn sàng");
boolean isEmpty = "".isEmpty();
int length = "Java".length(); // 4
String message = "Xin " + "chào";
```

Nối bằng `+` tạo một biểu thức chuỗi. Trong Java, `"Java"` không tự biến thành tên biến, `"123"` không tự biến thành số nguyên và `"Xin ${name}"` **không có cơ chế nội suy biến** theo cú pháp `${...}`. Nếu có biến `name`, một cách đơn giản là `"Xin " + name`.

### Vì sao không nên so sánh chuỗi bằng `==`?

Java **intern** các string literal: cùng nội dung literal thường tham chiếu đến cùng đối tượng trong string pool. Trình biên dịch còn có thể gộp những biểu thức nối chỉ chứa hằng tại thời điểm biên dịch. Nhưng `==` trên hai tham chiếu `String` kiểm tra **cùng đối tượng hay không**, không kiểm tra nội dung.

```java
String first = "Java";
String second = "Java";
String builtAtRuntime = new String("Java");

System.out.println(first == second);         // true
System.out.println(first == builtAtRuntime); // false
System.out.println(first.equals(builtAtRuntime)); // true
```

Đây là đoạn minh họa đặt **bên trong một phương thức**, không phải tệp Java độc lập. Sử dụng `.equals(...)` để so sánh nội dung; đừng dựa vào pool để suy luận `==` sẽ luôn đúng với hai chuỗi có chữ giống nhau.

Một literal vẫn là đối tượng `String` bất biến (*immutable*). Ví dụ `text.toUpperCase()` trả về chuỗi mới (hoặc có thể trả lại chính chuỗi nếu không cần thay đổi), chứ không sửa nội dung bên trong đối tượng `String` ban đầu.

## 6. Những lỗi thường gặp

| Đoạn mã | Vấn đề | Cách sửa |
|---|---|---|
| `String s = 'Java';` | Dấu `'...'` không tạo `String`; nhiều ký tự còn không hợp lệ cho `char` | `String s = "Java";` |
| `String s = "Java;` | Thiếu dấu `"` đóng | `String s = "Java";` |
| `String s = "C:\temp\file";` | `\t`, `\f` bị hiểu thành ký tự điều khiển | `String s = "C:\\temp\\file";` |
| `String s = "A "B" C";` | Dấu `"` bên trong làm kết thúc literal sớm | `String s = "A \"B\" C";` |
| `String s = "\q";` | `\q` không phải escape hợp lệ | Sử dụng `\\q` nếu cần ký tự `\` và `q` |
| `String s = ""; if (s == null) ...` | Chuỗi rỗng không phải `null` | Kiểm tra `s.isEmpty()` nếu mục tiêu là rỗng |
| `a == b` với `String` | So sánh tham chiếu | Dùng `a.equals(b)` khi chắc `a` không `null` |

Các dòng lỗi trong bảng là ví dụ chẩn đoán, **không phải mã nguồn chạy được**.

### Chuỗi chứa nhiều dòng thì sao?

Một literal chuỗi **thông thường** dùng `"..."`
không thể xuống dòng trực tiếp trong mã nguồn:

```java
// KHÔNG hợp lệ nếu xuống dòng thật bên trong "..."
String invalid = "Dòng 1
Dòng 2";
```

Viết `"Dòng 1\nDòng 2"` hoặc ghép `"Dòng 1\n" + "Dòng 2"`. Từ Java 15 còn có **text block** sử dụng `"""` cho văn bản nhiều dòng; đó là cú pháp riêng, phù hợp khi cần trình bày nội dung lớn, và khác với cặp dấu `"` của literal thông thường đang xét.

## 7. Tự kiểm tra

1. `"A"` và `'A'` khác nhau về kiểu như thế nào?
2. `" "` có rỗng không? `""` có bằng `null` không?
3. Viết literal biểu diễn nội dung chính xác `C:\java\src`.
4. Vì sao `String text = "Dòng 1\nDòng 2";` có thể in ra hai dòng, dù mã nguồn chỉ có một dòng?
5. Hai biến `String` cùng nội dung thì nên dùng `==` hay `.equals()` để kiểm tra văn bản?

**Đáp án:** (1) `String` và `char`; (2) `" "` chứa một dấu cách, `""` là chuỗi rỗng khác `null`; (3) `"C:\\java\\src"`; (4) `\n` là ký tự xuống dòng trong giá trị của chuỗi; (5) `.equals()`.

Một literal chuỗi hợp lệ cần có đúng ranh giới dấu nháy kép, các escape phù hợp và ý thức rõ sự khác nhau giữa những ký tự **viết trong mã nguồn** và những ký tự **thực sự tồn tại trong đối tượng `String`**.
