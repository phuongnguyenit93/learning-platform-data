# Lựa chọn bộ mã ký tự khi đọc dữ liệu bằng Scanner

## 1. Chọn đúng cách chuyển byte thành chữ

Tệp và luồng nhập chứa byte. Để đọc được chữ, chương trình cần biết quy tắc giải mã: **bộ mã ký tự (charset)**, chẳng hạn UTF-8. Sau bước đó, Scanner mới chia văn bản thành các phần và đọc bằng `next()`, `nextLine()` hoặc `nextInt()`.

```text
Byte của nguồn → giải mã bằng charset → ký tự → Scanner → giá trị cần dùng
```

Ví dụ, chữ `é` được mã hóa UTF-8 thành hai byte `C3 A9`. Nếu đọc hai byte ấy bằng ISO-8859-1, ta nhận hai ký tự khác. Dữ liệu vẫn có thể đọc hết mà không có ngoại lệ, nhưng ý nghĩa đã sai. Vì vậy, “chương trình chạy được” chưa chứng minh rằng charset đúng.

**Nguyên tắc chọn:** lấy charset từ hợp đồng dữ liệu hoặc cấu hình của bên tạo dữ liệu. Với dữ liệu mới do mình kiểm soát, nên thống nhất UTF-8 ở cả bên ghi và bên đọc. Không suy ra charset từ đuôi `.txt`, tên tệp hoặc việc nội dung là tiếng Việt.

## 2. Đặt charset tại đúng ranh giới

| Nguồn đưa cho Scanner | Đã là ký tự chưa? | Đặt charset ở đâu? |
| --- | --- | --- |
| `Path`, `File`, `InputStream`, `ReadableByteChannel` | Chưa, nguồn chứa byte | Constructor Scanner có tham số charset |
| `Reader` như `InputStreamReader` | Rồi | Khi tạo Reader để giải mã byte |
| `String` | Rồi | Không có bước chọn charset trong Scanner |

Ví dụ sau là các đoạn mã sử dụng độc lập trong ngữ cảnh đã có biến nguồn và các import tương ứng; chúng không phải một chương trình hoàn chỉnh:

```java
Scanner fromFile = new Scanner(path, StandardCharsets.UTF_8);
Scanner fromStream = new Scanner(inputStream, StandardCharsets.UTF_8);
Scanner fromText = new Scanner("Xin chào");
```

Các constructor nhận `Charset` ở trên dùng được với Java 17+. Không cần truyền chuỗi tên mã khi đã có hằng `StandardCharsets.UTF_8`. Các hằng trong StandardCharsets được nền tảng Java bảo đảm hỗ trợ. Xem [StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html).

Khi tạo `Scanner(reader)`, charset đã được Reader quyết định. Scanner không giải mã lại. Nếu Reader đã biến byte thành chữ sai, thay delimiter hoặc gọi `useLocale()` không thể sửa bước giải mã đó. [InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html) là lớp nối luồng byte với luồng ký tự.

## 3. Ví dụ hoàn chỉnh: cùng byte, hai cách giải mã

Lưu thành `ScannerCharsetDemo.java`. Chương trình tự tạo tệp tạm, ghi UTF-8 và đọc bằng charset chỉ định nên không cần chuẩn bị tệp đầu vào.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Scanner;

public class ScannerCharsetDemo {
    private static String readLine(Path file,
                                   java.nio.charset.Charset charset)
            throws java.io.IOException {
        try (Scanner scanner = new Scanner(file, charset)) {
            String line = scanner.nextLine();
            if (scanner.ioException() != null) {
                throw scanner.ioException();
            }
            return line;
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("scanner-charset-", ".txt");
        try {
            String original = "caf\u00E9";
            Files.writeString(file, original + "\n",
                    StandardCharsets.UTF_8);

            String correct = readLine(file, StandardCharsets.UTF_8);
            String wrong = readLine(file, StandardCharsets.ISO_8859_1);

            System.out.println("UTF-8 equals original: "
                    + original.equals(correct));
            System.out.println("ISO-8859-1 equals original: "
                    + original.equals(wrong));
            System.out.print("Wrong code points:");
            wrong.codePoints().forEach(cp ->
                    System.out.printf(" U+%04X", cp));
            System.out.println();
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 ScannerCharsetDemo.java
java ScannerCharsetDemo
```

Stdout chính xác:

```text
UTF-8 equals original: true
ISO-8859-1 equals original: false
Wrong code points: U+0063 U+0061 U+0066 U+00C3 U+00A9
```

Ba ký tự ASCII đầu giữ nguyên; hai byte của `é` bị hiểu thành `U+00C3` và `U+00A9`. Ví dụ in mã Unicode để kết quả không phụ thuộc phông chữ hay charset hiển thị của terminal. ISO-8859-1 ở đây chỉ là đối chứng có chủ đích để thấy lỗi, không phải lựa chọn cho dữ liệu tiếng Việt.

Tệp tạm được xóa sau khi dùng. `try-with-resources` đóng Scanner và nguồn tệp của nó. Các thao tác tạo, ghi và xóa tệp dùng [Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).

## 4. Không giao hợp đồng dữ liệu cho charset mặc định

`new Scanner(path)` và `new Scanner(inputStream)` dùng charset mặc định của JVM. Trong JDK hiện đại, mặc định là UTF-8, trừ cấu hình riêng của triển khai; không được suy ra rằng mọi tệp hoặc mọi nguồn nhập cũng là UTF-8. Tham khảo [Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html#defaultCharset()).

Với tệp có hợp đồng UTF-8, hãy viết trực tiếp:

```java
try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        // Xử lý line theo yêu cầu của ứng dụng.
    }
    if (scanner.ioException() != null) {
        throw scanner.ioException();
    }
}
```

Đây là đoạn mã minh họa trong phương thức có `throws IOException`, đã import Scanner và StandardCharsets, và có biến `Path path`.

Việc ghi rõ charset giữ ý định ngay tại chỗ đọc dữ liệu. Nó cũng tránh phải thay đổi cấu hình toàn JVM để chữa một nguồn nhập riêng lẻ.

Đừng nhầm ba thiết lập:

- `javac -encoding UTF-8`: cách compiler đọc tệp mã nguồn `.java`.
- `new Scanner(source, StandardCharsets.UTF_8)`: cách chương trình giải mã byte đầu vào lúc chạy.
- Charset của đầu ra và terminal: cách kết quả được mã hóa rồi hiển thị.

Đọc đúng nhưng terminal hiện sai dấu là một tình huống khác với đọc sai byte.

## 5. Nhập từ bàn phím và chuyển hướng stdin

Bàn phím trong terminal, cửa sổ chạy của IDE và tệp chuyển hướng vào stdin có thể tạo byte theo các cấu hình khác nhau. **Không mặc định rằng System.in luôn là UTF-8 chỉ vì chương trình chạy trên JDK mới.**

Nếu có console thực, có thể lấy Reader mà console cung cấp:

```java
java.io.Console console = System.console();
if (console != null) {
    Scanner scanner = new Scanner(console.reader());
    if (scanner.hasNextLine()) {
        String line = scanner.nextLine();
        console.writer().println(line);
        console.writer().flush();
    }
}
```

Đây là đoạn minh họa trong một phương thức. Không đóng Scanner ở đây vì ứng dụng còn sở hữu console. `System.console()` có thể trả về `null`, thường gặp khi chạy qua IDE hoặc không có console gắn với JVM; phải quyết định nguồn nhập phù hợp cho ứng dụng trong nhánh đó. [Console](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Console.html) cung cấp giao diện ký tự cho thiết bị console.

Nếu hợp đồng đầu vào khẳng định stdin chứa UTF-8, ví dụ nhận dữ liệu từ một tiến trình ghi UTF-8, thì dùng:

```java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
```

Không đóng đối tượng này giữa chừng nếu phần khác còn cần `System.in`: đóng Scanner sẽ đóng nguồn bên dưới. Tránh tạo nhiều Scanner cùng đọc một stdin vì mỗi đối tượng có thể đọc trước vào bộ đệm.

## 6. Cần phát hiện byte hỏng: giải mã nghiêm ngặt

Chọn đúng tên charset chưa đủ cho luồng cần kiểm tra tính hợp lệ. Dữ liệu có thể bị cắt giữa một chuỗi UTF-8 hoặc chứa byte hỏng. Đừng dựa vào giả định “Scanner chắc chắn sẽ ném lỗi giải mã ra chỗ gọi”.

Khi yêu cầu là từ chối dữ liệu sai, tạo `CharsetDecoder` với `CodingErrorAction.REPORT`, đưa nó vào InputStreamReader, rồi đưa Reader vào Scanner. Có thể kiểm soát riêng lỗi byte không hợp lệ và lỗi không ánh xạ được. Xem [CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

Lưu thành `StrictScannerDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class StrictScannerDemo {
    public static void main(String[] args) throws Exception {
        // C3 phải có byte tiếp nối hợp lệ; 28 không phải byte tiếp nối.
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (var input = new ByteArrayInputStream(invalidUtf8);
             var reader = new InputStreamReader(input, decoder);
             var scanner = new Scanner(reader)) {
            while (scanner.hasNextLine()) {
                scanner.nextLine();
            }

            System.out.println("Decoding failed: "
                    + (scanner.ioException() != null));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 StrictScannerDemo.java
java StrictScannerDemo
```

Stdout chính xác:

```text
Decoding failed: true
```

Điểm dễ bỏ sót: nếu thao tác đọc nguồn bên dưới ném IOException, Scanner xem đó như kết thúc đầu vào và giữ lỗi để lấy qua `ioException()`. Bởi vậy, `hasNextLine() == false` chưa đủ để kết luận đã đọc hết thành công. Xem [hợp đồng Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

Trong ứng dụng nhập dữ liệu, kiểm tra `ioException()` sau vòng lặp và báo thất bại trước khi chấp nhận kết quả. Ví dụ trên chỉ minh họa tín hiệu lỗi; nếu yêu cầu không được nhập một phần dữ liệu thì cần đọc, kiểm tra vào vùng tạm hoặc dùng giao dịch phù hợp trước khi lưu chính thức. Ngoài ra, bộ giải mã nghiêm ngặt chỉ kiểm tra tính hợp lệ theo charset đã chọn; nó không chứng minh đó là charset thật của nguồn.

## 7. Những nhầm lẫn cần tách riêng

| Hiện tượng | Cần kiểm tra | Không nên chữa bằng |
| --- | --- | --- |
| Chữ sai nhưng vẫn đọc hết | Charset của bên ghi và bên đọc | Đổi delimiter hoặc Locale |
| Có ký tự thay thế `�` | Byte gốc, charset và chính sách xử lý lỗi | Xóa ký tự lạ rồi chấp nhận dữ liệu |
| `nextInt()` không nhận giá trị đầu tiên của tệp | Nội dung thực, có thể có BOM đầu tệp | Mặc định kết luận charset sai |
| Chữ trong String đúng nhưng in ra sai | Charset đầu ra và terminal | Giải mã lại String bằng charset khác |
| `nextLine()` trả chuỗi rỗng sau `nextInt()` | Vị trí đọc và phần kết thúc dòng | Đổi UTF-8 sang charset khác |

**BOM UTF-8:** một số tệp bắt đầu bằng byte `EF BB BF`, biểu diễn `U+FEFF`. Đừng giả định Scanner tự bỏ dấu này. Nếu định dạng cho phép BOM ở đầu tệp, xử lý đúng một dấu ở vị trí đầu vào, trước khi phân tích giá trị đầu tiên. Không xóa mọi `U+FEFF` trong toàn văn bản. Với UTF-16, BOM và thứ tự byte là vấn đề riêng; chọn theo đặc tả nguồn, không thử các charset ngẫu nhiên cho đến khi “nhìn có vẻ đúng”.

`useLocale()` phục vụ cách hiểu số theo quy ước vùng, ví dụ dấu thập phân. Nó hoạt động sau giải mã byte nên không sửa được văn bản đã giải mã sai.

## 8. Thực hành tự kiểm tra

1. Thay `original` trong ví dụ đầu bằng `"Ti\u1EBFng Vi\u1EC7t"`. Kết quả so sánh UTF-8 vẫn phải là `true`; dãy mã ở dòng cuối sẽ thay đổi.
2. Thay dữ liệu hỏng ở ví dụ hai bằng `"OK\n".getBytes(StandardCharsets.UTF_8)`. Kết quả `Decoding failed` phải trở thành `false`.
3. Xác định một nguồn dữ liệu thực tế: ai tạo byte, charset được công bố ở đâu, ai sở hữu việc đóng nguồn, và chương trình báo lỗi thế nào nếu dữ liệu không hợp lệ.

Khi xem lại đoạn đọc bằng Scanner, hãy tìm rõ hai quyết định: **charset nào giải mã nguồn byte** và **lỗi giải mã được phát hiện, xử lý ra sao**. Đó là cơ sở để đọc văn bản có dấu ổn định giữa các môi trường.
