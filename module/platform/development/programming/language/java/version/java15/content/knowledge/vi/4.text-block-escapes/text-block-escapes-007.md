# Thời điểm xử lý Unicode escape trong mã nguồn Java: tác động tới text block

## 1. Ý chính: Unicode escape được xử lý rất sớm

Trong Java, **Unicode escape của mã nguồn** như `\u0041`, `\u0020` hay `\u000a` không chờ đến khi chương trình chạy và cũng **không chờ** giai đoạn xử lý escape của một text block. Trình biên dịch nhận diện và chuyển đổi Unicode escape hợp lệ **trước khi xác định token** (từ khóa, dấu phân định, chú thích, chuỗi thông thường và text block).

Với text block (chính thức từ **Java 15**, vẫn sử dụng trong Java 17+), thứ tự cần nhớ là:

~~~text
Ký tự của tệp .java (sau khi giải mã bằng encoding của tệp)
    │
    ▼
1. Dịch Unicode escape đủ điều kiện: \uXXXX → ký tự Unicode
    │
    ▼
2. Nhận diện dấu xuống dòng và các token của Java;
   tại đây mới nhận diện dấu mở/đóng """ của text block
    │
    ▼
3. Xử lý nội dung text block:
   a. Chuẩn hóa CRLF/CR thành LF
   b. Loại thụt lề phụ trợ và khoảng trắng cuối dòng
   c. Diễn giải escape như \n, \t, \r, \s, \\ và nối dòng bằng \
    │
    ▼
Giá trị java.lang.String cuối cùng
~~~

Phân biệt hai loại:

- **Unicode escape của mã nguồn:** bắt đầu bằng dấu gạch chéo ngược đủ điều kiện, theo sau bởi một hoặc nhiều chữ `u` và **bốn chữ số hexadecimal**; ví dụ `\u0041` biểu diễn ký tự `A`. Nó được dịch **trước cả quá trình phân tích cú pháp**.
- **Escape sequence của text block:** chẳng hạn `\n`, `\t`, `\s`, `\\` và dấu `\` nối dòng. Nó được diễn giải **sau khi** trình biên dịch đã chuẩn hóa xuống dòng và loại thụt lề của text block.

Điểm mấu chốt: `\u0020` và `\s` đều có thể tạo dấu cách, nhưng thời điểm tạo ra dấu cách khác nhau, nên **kết quả có thể khác nhau**.

## 2. Ví dụ đơn giản: `\u0041` trở thành chữ A trước khi nhận diện text block

~~~java
String converted = """
        \u0041
        """;
~~~

Dù mã nguồn hiển thị chuỗi sáu ký tự `\u0041`, bộ dịch Unicode của trình biên dịch đã thay nó bằng `A` trước khi nhận diện nội dung text block. Text block sau đó loại phần thụt lề phụ trợ, nên:

~~~java
converted.equals("A\n")  // true
~~~

Dấu xuống dòng sau `A` được giữ vì dấu đóng `"""` nằm trên dòng riêng. Đây là phép biến đổi lúc **biên dịch**, không phải phương thức runtime như `String.replace(...)`.

Thực tế, viết trực tiếp chữ `A` trong text block thường dễ đọc hơn. Unicode escape chủ yếu có giá trị khi cần biểu diễn một ký tự nguồn đặc biệt hoặc phân tích quy tắc từ vựng của Java.

## 3. Vì sao `\u0020` có thể mất dấu cách nhưng `\s` thì giữ lại?

Xét hai text block:

~~~java
String unicodeSpace = """
        A\u0020
        B
        """;

String escapedSpace = """
        A\s
        B
        """;
~~~

### Trường hợp 1: `\u0020`

1. **Dịch Unicode escape sớm:** `\u0020` trở thành một dấu cách thật, đứng ngay sau `A` và trước ký tự kết thúc dòng.
2. **Chuẩn hóa dòng, loại khoảng trắng:** khi text block bỏ khoảng trắng cuối dòng, dấu cách sau `A` **bị loại**.
3. **Diễn giải escape muộn:** không còn `\u0020` hay một escape cần dịch ở vị trí đó.

Kết quả: `unicodeSpace.equals("A\nB\n")` là `true`.

### Trường hợp 2: `\s`

1. **Dịch Unicode escape sớm:** `\s` không phải Unicode escape (`s` không phải chữ `u`), nên còn nguyên hai ký tự `\` và `s`.
2. **Loại khoảng trắng:** `\s` chưa phải dấu cách thực, nên không bị xóa với tư cách khoảng trắng cuối dòng.
3. **Diễn giải escape muộn:** `\s` biến thành **một dấu cách thật** sau `A`.

Kết quả: `escapedSpace.equals("A \nB\n")` là `true`.

| Viết trong dòng nội dung trước dấu xuống dòng | Thời điểm tạo dấu cách | Dấu cách cuối dòng còn không? |
| --- | --- | --- |
| `A\u0020` | Trước bước loại khoảng trắng | **Không** |
| `A\s` | Sau bước loại khoảng trắng | **Có: một dấu cách** |

**Ứng dụng:** khi cố ý giữ dấu cách cuối dòng của text block, dùng `\s` (hoặc escape octal `\040`) thay vì `\u0020`. Đây là quy tắc vẫn áp dụng trong Java hiện đại.

## 4. `\u000a` được chuyển thành xuống dòng trước khi tách token

`\u000a` là Unicode escape của **LF**. Nó không hoạt động giống escape `\n` được diễn giải trong giai đoạn cuối của text block.

~~~java
String unicodeLF = """
        X\u000a
        Y
        """;
~~~

Trước khi text block được nhận diện, `\u000a` đã trở thành ký tự xuống dòng thực sự. Trong mã nguồn còn có một ký tự xuống dòng ngay sau chuỗi `\u000a`, nên ở đây có **hai dấu xuống dòng liên tiếp** giữa `X` và `Y`.

Kết quả:

~~~java
unicodeLF.equals("X\n\nY\n")  // true
~~~

Nếu chỉ muốn một LF trong **giá trị** của chuỗi, thường nên dùng xuống dòng trực tiếp trong text block hoặc escape `\n` khi cần diễn đạt rõ ràng, tránh dùng `\u000a` để thêm ngắt dòng ở cấp mã nguồn.

Unicode escape cho dấu xuống dòng còn ảnh hưởng **ngoài text block**: vì được dịch trước khi phân tích chú thích, một `\u000a` trong dòng `//` có thể kết thúc chú thích sớm hơn dự kiến và khiến phần sau được phân tích như mã Java. Không dùng Unicode escape để che giấu cấu trúc dòng hoặc dấu phân định.

## 5. Unicode escape có thể tạo dấu nháy hoặc dấu gạch chéo ngược

### 5.1. `\u0022` tạo dấu nháy kép trước khi Java nhận diện cú pháp

~~~java
String quote = """
        a\u0022b
        """;
~~~

`\u0022` được dịch thành dấu `"`; kết quả chuỗi là `"a\"b\n"` (tức ba ký tự `a`, `"`, `b` rồi LF). Một dấu nháy kép đơn lẻ được phép nằm trong text block. Tuy nhiên, nếu Unicode escape tạo ra nhiều dấu nháy liên tiếp, **chúng có thể ảnh hưởng đến việc nhận diện dấu đóng `"""`**.

Vì vậy, đừng nghĩ một chuỗi `\u0022` chắc chắn sẽ được giữ nguyên như sáu ký tự dữ liệu bên trong text block. Khi chỉ cần dấu nháy trong nội dung, viết `"` trực tiếp thường rõ ràng hơn.

### 5.2. `\u005c` tạo dấu gạch chéo ngược trước giai đoạn escape của text block

~~~java
String generatedEscape = """
        A\u005cs
        """;
~~~

`\u005c` là ký tự `\`. Sau bước dịch Unicode, phần cuối dòng về mặt từ vựng là `A\s`. Tới giai đoạn xử lý escape của text block, `\s` lại trở thành một dấu cách. Kết quả:

~~~java
generatedEscape.equals("A \n")  // true
~~~

Ví dụ này cho thấy **một Unicode escape dịch sớm có thể tạo ra dấu gạch chéo ngược rồi tham gia xử lý escape muộn hơn**. Trong mã thực tế, viết `A\s` trực tiếp dễ đọc và ít gây ngạc nhiên hơn `A\u005cs`.

## 6. Muốn hiển thị nguyên văn `\u0041` thì làm sao?

Có trường hợp muốn dữ liệu cuối cùng chứa đúng sáu ký tự `\`, `u`, `0`, `0`, `4`, `1`, ví dụ hiển thị mẫu Unicode escape cho người học. Khi đó có thể viết hai dấu gạch chéo ngược trong nội dung Java:

~~~java
String literalUnicodeSequence = """
        \\u0041
        """;
~~~

Java có **quy tắc đủ điều kiện cho dấu gạch chéo ngược** khi dịch Unicode escape. Trong trường hợp này, cặp dấu `\\` trong mã nguồn không biến phần `u0041` thành chữ `A` ở giai đoạn dịch Unicode. Đến giai đoạn escape của text block, `\\` được diễn giải thành **một dấu `\`** thật.

Giá trị kết quả là chuỗi ký tự `\u0041`, **không phải chữ `A`**. Vì ví dụ đặt dấu đóng trên dòng riêng, còn có một `\n` sau sáu ký tự đó:

~~~java
literalUnicodeSequence.equals("\\u0041\n")  // true
~~~

Lưu ý về hiển thị: trong chuỗi Java thông thường `"\\u0041\n"`, `\\` biểu diễn một dấu `\` và `\n` biểu diễn LF. Nó **không** yêu cầu dịch tiếp `u0041` thành `A`. Không nên tùy tiện nhân đôi hoặc bớt dấu `\`: quy tắc nhận diện Unicode escape phụ thuộc chuỗi dấu gạch chéo ngược trong mã nguồn.

## 7. Chương trình hoàn chỉnh: biên dịch và quan sát thứ tự xử lý

Lưu đúng tên tệp **`UnicodeEscapesInTextBlocks.java`**. Chương trình tương thích **Java 17+** và chỉ sử dụng những khả năng text block đã chính thức có từ Java 15.

Hàm `visible` chỉ phục vụ minh họa: thay space thành `·`, dấu xuống dòng thành `<LF>`, tab thành `<TAB>` và CR thành `<CR>` để không nhầm ký tự vô hình.

~~~java
public class UnicodeEscapesInTextBlocks {
    public static void main(String[] args) {
        String converted = """
                \u0041
                """;
        String unicodeSpace = """
                A\u0020
                B
                """;
        String escapedSpace = """
                A\s
                B
                """;
        String quote = """
                a\u0022b
                """;
        String unicodeLF = """
                X\u000a
                Y
                """;
        String generatedEscape = """
                A\u005cs
                """;
        String literalUnicodeSequence = """
                \\u0041
                """;

        System.out.println("converted=" + visible(converted));
        System.out.println("unicodeSpace=" + visible(unicodeSpace));
        System.out.println("escapedSpace=" + visible(escapedSpace));
        System.out.println("quote=" + visible(quote));
        System.out.println("unicodeLF=" + visible(unicodeLF));
        System.out.println("generatedEscape=" + visible(generatedEscape));
        System.out.println("literalUnicodeSequence=" + visible(literalUnicodeSequence));

        System.out.println("checks=" + (
                converted.equals("A\n")
                && unicodeSpace.equals("A\nB\n")
                && escapedSpace.equals("A \nB\n")
                && quote.equals("a\"b\n")
                && unicodeLF.equals("X\n\nY\n")
                && generatedEscape.equals("A \n")
                && literalUnicodeSequence.equals("\\u0041\n")));
    }

    private static String visible(String value) {
        return value.replace(" ", "·")
                .replace("\n", "<LF>")
                .replace("\t", "<TAB>")
                .replace("\r", "<CR>");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeEscapesInTextBlocks.java
java UnicodeEscapesInTextBlocks
~~~

Kết quả chính xác (đã kiểm chứng bằng JDK 24 ở chế độ biên dịch tương thích Java 17):

~~~text
converted=A<LF>
unicodeSpace=A<LF>B<LF>
escapedSpace=A·<LF>B<LF>
quote=a"b<LF>
unicodeLF=X<LF><LF>Y<LF>
generatedEscape=A·<LF>
literalUnicodeSequence=\u0041<LF>
checks=true
~~~

Lệnh `--release 17` yêu cầu trình biên dịch kiểm tra nguồn/API theo Java 17; cú pháp và quy tắc Unicode escape ở bài này vẫn còn được áp dụng trong Java hiện hành.

## 8. Các lỗi phổ biến và cách xử lý

1. **Nhầm Unicode escape với escape của String:** `\u000a` được dịch trước khi phân tích token; `\n` được dịch muộn bên trong text block. Vì thế `\u000a` có thể thay đổi dòng *mã nguồn*, trong khi `\n` chỉ thêm LF vào giá trị chuỗi.
2. **Cho rằng `\u0020` bảo vệ space cuối dòng:** không đúng. Dấu cách tạo bởi `\u0020` có mặt trước khi text block loại khoảng trắng. Hãy dùng `\s` nếu cần giữ space cuối dòng.
3. **Cho rằng bên trong comment hoặc dấu nháy thì `\uXXXX` luôn là chữ bình thường:** sai. Unicode escape được dịch trước khi Java nhận ra comment, dấu nháy hoặc text block. Những escape tạo LF hay dấu nháy có thể đổi cấu trúc mã nguồn.
4. **Không chú ý Unicode escape tạo `\`:** một dấu `\` sinh ra từ `\u005c` có thể kết hợp với ký tự ngay sau để thành escape của text block, như `\s` ở ví dụ.
5. **Không kiểm tra cách viết dấu `\`:** chuỗi dấu gạch chéo ngược liên tiếp có quy tắc riêng quyết định `\u` nào đủ điều kiện để dịch. Nếu muốn lưu mẫu Unicode escape như dữ liệu, thử với kiểm tra `equals` và mã ví dụ đã chạy.
6. **Dùng Unicode escape không hợp lệ:** dạng Java thông dụng là `\u` + đúng bốn chữ số hex (chấp nhận nhiều `u` liên tiếp trước bốn chữ số). `\u{0041}` không phải cú pháp Unicode escape của Java. Với Unicode phức tạp, nên ưu tiên ký tự nguồn được lưu đúng encoding hoặc API làm việc với code point.
7. **Viết chuỗi cần nhiều dòng bằng escape sớm khó bảo trì:** với text block, thường chỉ cần xuống dòng trực tiếp. Dùng `\n`, `\s` hoặc `\\` ở mức text block khi có lý do rõ ràng; đừng lạm dụng `\u000a`, `\u0020` hay `\u005c` để điều khiển bố cục.

**Tự kiểm tra:** Vì sao `\u0020` ở cuối dòng có thể biến mất còn `\s` vẫn tạo ra một dấu cách? Vì Unicode escape **được dịch trước** bước loại khoảng trắng, còn `\s` **được dịch sau** bước đó.

## Tài liệu chính thức

- Java Language Specification, **`3.3 Unicode Escapes**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.3
- Java Language Specification, **`3.10.6 Text Blocks**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- OpenJDK, **JEP 378: Text Blocks** (đã chuẩn hóa trong Java 15): https://openjdk.org/jeps/378