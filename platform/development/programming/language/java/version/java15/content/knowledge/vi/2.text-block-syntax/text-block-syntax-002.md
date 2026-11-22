# Dấu mở và dấu đóng bằng ba dấu nháy kép trong Java text block

Text block là cách viết giá trị `String` bằng cặp dấu phân định ba dấu nháy kép `"""`. Cú pháp này phù hợp khi chuỗi có nhiều dòng, chẳng hạn HTML, JSON hoặc thông báo nhiều dòng. Các quy tắc dưới đây áp dụng cho Java 15 trở lên, bao gồm các bản Java hiện đại.

## 1. Nhận biết dấu mở và dấu đóng

Dạng cơ bản:

```java
String message = """
        Dòng thứ nhất
        Dòng thứ hai
        """;
```

- **Dấu mở**: ba dấu nháy kép liên tiếp `"""`, tiếp theo có thể là khoảng trắng ngang (dấu cách, tab, form feed), rồi **bắt buộc là ký tự kết thúc dòng**. Nội dung chỉ bắt đầu ở dòng kế tiếp.
- **Dấu đóng**: ba dấu nháy kép liên tiếp `"""`, kết thúc phần nội dung của text block. Dấu đóng có thể nằm trên dòng riêng hoặc ngay sau ký tự nội dung cuối cùng.
- **Dấu chấm phẩy** `;` trong ví dụ kết thúc câu lệnh gán của Java, không thuộc dấu đóng.
- Giá trị tạo ra có kiểu `String`; đây không phải cú pháp nội suy biến hoặc một kiểu chuỗi mới.

Chữ `Dòng thứ nhất` và `Dòng thứ hai` ở ví dụ trên trở thành hai dòng trong chuỗi. Khi bỏ phần thụt lề phụ do mã nguồn, giá trị tương đương `"Dòng thứ nhất\nDòng thứ hai\n"`.

## 2. Quy tắc bắt buộc của dấu mở

**Phải xuống dòng sau dấu mở.** Không được đặt ký tự nội dung ngay sau `"""` trên cùng một dòng:

```java
// SAI: không có ký tự xuống dòng sau dấu mở.
String a = """Xin chào""";

// SAI: có chữ ngay sau dấu mở, dù phần còn lại xuống dòng.
String b = """Xin chào
        mọi người
        """;
```

Cách đúng:

```java
String a = """
        Xin chào""";

String b = """
        Xin chào
        mọi người
        """;
```

Với `a`, chuỗi chỉ chứa `Xin chào`. Với `b`, hai dòng văn bản được ngăn bởi `\n`, và chuỗi còn có một `\n` ở cuối. Dấu xuống dòng bắt buộc ngay sau dấu mở **không tự thêm một dòng trống ở đầu chuỗi**: nó chỉ đánh dấu ranh giới bắt đầu nội dung.

Khoảng trắng ngang sau dấu mở, trước ký tự kết thúc dòng, là hợp lệ nhưng không hữu ích trong hầu hết trường hợp. Viết `"""` rồi xuống dòng ngay sẽ rõ ràng hơn.

## 3. Vị trí dấu đóng quyết định dòng mới cuối chuỗi

Hai dạng sau đều hợp lệ và tạo giá trị khác nhau:

```java
// Dấu đóng ở dòng riêng: giữ ký tự xuống dòng sau "Hello".
String withFinalNewline = """
        Hello
        """;

// Dấu đóng ngay sau "Hello": không có ký tự xuống dòng cuối.
String withoutFinalNewline = """
        Hello""";
```

Giá trị chính xác:

| Biến | Biểu diễn giá trị (viết `\n` cho ký tự xuống dòng) | Độ dài |
| --- | --- | ---: |
| `withFinalNewline` | `Hello\n` | 6 |
| `withoutFinalNewline` | `Hello` | 5 |

Quy tắc nhớ: **dấu đóng ở dòng riêng** thường giữ ký tự xuống dòng ở cuối dòng nội dung trước nó; **dấu đóng cùng dòng với ký tự cuối** sẽ không tự tạo dòng mới cuối chuỗi. Điều này rất quan trọng khi so sánh chuỗi, ghi file hoặc tạo nội dung gửi qua mạng.

Một text block có thể rỗng:

```java
String empty = """
        """;
System.out.println(empty.isEmpty()); // true
```

## 4. Chương trình Java chạy được và kết quả chính xác

Lưu nội dung sau thành file `TextBlockDelimiters.java` (mã hóa UTF-8):

```java
public class TextBlockDelimiters {
    private static String show(String value) {
        // Hiển thị ký tự xuống dòng thực bằng hai ký tự \ và n.
        return value.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String withNewline = """
                Xin chào
                """;
        String withoutNewline = """
                Xin chào""";
        String twoLines = """
                Dòng 1
                Dòng 2
                """;
        String empty = """
                """;

        System.out.println("withNewline=" + show(withNewline));
        System.out.println("withoutNewline=" + show(withoutNewline));
        System.out.println("twoLines=" + show(twoLines));
        System.out.println("emptyLength=" + empty.length());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TextBlockDelimiters.java
java TextBlockDelimiters
```

Đầu ra (các chuỗi `\n` được in thành hai ký tự `\${T} và `n` nhờ hàm `show`):

```text
withNewline=Xin chào\n
withoutNewline=Xin chào
twoLines=Dòng 1\nDòng 2\n
emptyLength=0
```

Như vậy, ký tự xuống dòng của dấu mở không đứng ở đầu giá trị; còn việc có `\n` cuối giá trị phụ thuộc cách đặt dấu đóng và nội dung thực tế.

## 5. Dấu đóng liên quan thế nào tới thụt lề?

Trong text block, Java tự loại bỏ **thụt lề phụ** của mã nguồn. Với dấu đóng trên một dòng riêng, khoảng thụt lề trước dấu đóng cũng tham gia xác định phần thụt lề phụ được loại bỏ:

```java
String noLeadingSpaces = """
        <p>Xin chào</p>
        """;

String fourLeadingSpaces = """
            <p>Xin chào</p>
        """;
```

- `noLeadingSpaces` có giá trị `"<p>Xin chào</p>\n"`.
- `fourLeadingSpaces` có **bốn dấu cách ở đầu** rồi đến `<p>Xin chào</p>` và `\n`. Dòng nội dung được thụt vào sâu hơn dòng dấu đóng bốn dấu cách nên bốn dấu cách đó còn lại trong chuỗi.

Khi đặt dấu đóng ngay sau nội dung, không có dòng dấu đóng riêng để xác định lề; Java vẫn loại thụt lề phụ theo các dòng nội dung. Vì thế, **đừng coi mọi khoảng trắng nhìn thấy trong code là một phần của `String`**. Hãy kiểm tra giá trị thực nếu bố cục khoảng trắng quan trọng.

Dù file nguồn dùng LF hay CRLF, ký tự kết thúc dòng bên trong text block được chuẩn hóa thành `\n`. Các khoảng trắng ở cuối dòng nội dung thường bị loại bỏ trong quá trình xử lý; muốn giữ chúng cần dùng escape thích hợp, ví dụ `\s`. Đây là xử lý vẫn áp dụng trong Java hiện đại.

## 6. Có thể dùng dấu nháy kép bên trong nội dung không?

Có. Một hoặc hai dấu nháy kép trong nội dung text block không cần escape:

```java
String json = """
        {"name": "Lan", "active": true}
        """;
```

Nhưng **ba dấu nháy kép liên tiếp không được viết nguyên trạng trong nội dung**, vì chúng có thể bị hiểu là dấu đóng. Khi cần hiển thị chính bộ ba dấu nháy kép, hãy escape một dấu, chẳng hạn dấu đầu:

```java
String explanation = """
        Dấu mở của text block là \"""
        """;
```

Giá trị của `explanation` là dòng chữ `Dấu mở của text block là """` và một ký tự xuống dòng cuối. Dấu `\${T} trước dấu nháy kép là escape của Java; nó không xuất hiện trong chuỗi kết quả. Text block vẫn xử lý escape như chuỗi Java thông thường nên nó **không phải raw string**.

## 7. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai hoặc gây bất ngờ | Cách sửa |
| --- | --- | --- |
| Viết `"""abc"""` trên một dòng | Thiếu ký tự kết thúc dòng bắt buộc của dấu mở | Xuống dòng ngay sau ba dấu nháy mở |
| Viết chữ ngay sau dấu mở rồi mới xuống dòng | Dấu mở chỉ cho phép khoảng trắng ngang trước ký tự kết thúc dòng | Đưa chữ xuống dòng tiếp theo |
| Chỉ dùng một hoặc hai dấu nháy khi muốn kết thúc | Text block yêu cầu bộ ba dấu nháy kép làm dấu đóng | Dùng đúng `"""` |
| Đặt dấu đóng ở dòng riêng nhưng quên `\n` cuối | Dòng nội dung trước dấu đóng có ký tự xuống dòng thực | Đưa dấu đóng lên sau ký tự cuối nếu không muốn newline cuối |
| Giả định thụt lề trong source luôn được giữ nguyên | Java tự loại thụt lề phụ | Xác định lề của nội dung và dấu đóng; kiểm tra kết quả |
| Chèn ba dấu nháy kép liên tiếp vào nội dung mà không escape | Có thể bị nhận là dấu đóng sớm | Escape một trong ba dấu nháy kép |

**Lưu ý về chọn cú pháp:** Nếu chuỗi chỉ có một dòng ngắn, cú pháp thông thường `"Xin chào"` dễ đọc hơn. Text block vẫn có thể chứa một dòng nội dung, nhưng dấu mở của nó vẫn bắt buộc có ký tự kết thúc dòng.

## 8. Tự kiểm tra

Đọc đoạn mã hợp lệ sau:

```java
String first = """
        A
        B
        """;

String second = """
        A
        B""";
```

1. Biểu diễn giá trị chính xác của `first` và `second` bằng cách hiện ký tự xuống dòng là `\n`?
2. Chuỗi nào có ký tự xuống dòng ở cuối?
3. Có được đổi dòng đầu thành `String first = """A` hay không?

**Đáp án:** (1) `first` là `A\nB\n`; `second` là `A\nB`. (2) Chỉ `first`. (3) Không, vì dấu mở bắt buộc theo sau bởi ký tự kết thúc dòng trước khi có nội dung.

**Tài liệu đối chiếu:** [Oracle — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html), [Java Language Specification §3.10.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6).
