# BOM, console, terminal và nguồn gốc chữ bị lỗi mã hóa trong Java

## Mục tiêu

Khi chương trình Java đọc một tệp tiếng Việt rồi in ra `Tiáº¿ng Viá»‡t`, `CafÃ©`, các ô vuông hoặc ký hiệu `�`, nguyên nhân không nhất thiết nằm ở phông chữ. Dữ liệu ký tự đã đi qua nhiều tầng: **bytes trên đĩa/mạng → charset decoder → `String` Java → charset encoder → stdout/terminal hoặc tệp → bộ giải mã và font nơi hiển thị**. Chỉ cần một tầng dùng sai quy ước, chữ có thể thành *mojibake* (văn bản lỗi mã) hoặc ký tự thay thế.

BOM (*Byte Order Mark*) là dấu byte ở **đầu một số dạng văn bản Unicode**, giúp nhận biết thứ tự byte của UTF-16/UTF-32 và đôi khi được dùng như chữ ký UTF-8. BOM không thay thế việc xác định charset rõ ràng. Console/terminal lại có cơ chế giải mã, code page và font riêng; charset mặc định của JVM không nhất thiết là charset mà nơi nhận stdout dùng.

Sau bài, bạn có thể:

- Phân biệt **byte**, **Unicode code point**, **UTF-8/UTF-16**, **charset**, **BOM**, **stdout** và **font rendering**.
- Nhận diện byte BOM phổ biến: `EF BB BF` (UTF-8), `FE FF` và `FF FE` (UTF-16).
- Phân tích khi nào BOM UTF-8 trở thành ký tự `U+FEFF` trong `String`, và tại sao chỉ nên loại nó ở đúng ranh giới dữ liệu.
- Hiểu đường đi khi `System.out.println` gửi văn bản đến terminal, IDE, pipeline, tệp log hoặc CI.
- Dùng `StandardCharsets.UTF_8` và API đọc/ghi có charset tường minh trong Java 17+.
- Nhận diện giới hạn của `Charset.defaultCharset()` và khác biệt giữa JDK 17 với các JDK mới hơn.
- Phân biệt **decode sai**, **encode sai**, **mất dữ liệu do replacement**, **double encoding**, **bản thân font thiếu glyph**.
- Viết thử nghiệm byte-level, so sánh hex/code point, dùng decoder `REPORT` và xử lý lỗi đúng tầng thay vì “thử thay dấu”.
- Xác định hướng khắc phục hợp lý cho file, JSON/HTTP, CSV, cửa sổ console và pipeline build.

Đây là bài thuộc nhóm **Charset và I/O**. Điểm mấu chốt không phải ghi nhớ một câu lệnh sửa terminal, mà là xác định chính xác **đầu nào tạo byte, charset nào diễn giải byte và nơi nào hiển thị ký tự**.

## 1. Mô hình đúng: ký tự và byte là hai tầng khác nhau

Trong Java, `String` là một chuỗi ký tự Unicode ở mức API. Khi ghi ra file hoặc stream byte, Java phải **encode** chuỗi thành byte theo charset. Khi đọc byte vào `String`, Java phải **decode** byte theo charset.

```text
      Nguồn ký tự Java                    Đích byte
       String "Tiếng Việt"
              |
        encode UTF-8
              |
       54 69 E1 BA BF ...
              |
         file / socket
              |
        decode UTF-8
              |
       String "Tiếng Việt"
              |
          render/font
              v
        Chữ người dùng thấy
```

Đường đi đúng yêu cầu bên ghi và bên đọc thống nhất charset hoặc giao thức có cơ chế nhận diện charset đáng tin.

Ví dụ ký tự `ế` có code point `U+1EBF`. Khi mã hóa UTF-8, nó thành ba byte `E1 BA BF`. Nếu ba byte này bị đọc theo ISO-8859-1, kết quả không còn là `ế`; chúng được hiểu thành ba code point khác. Nếu chuyển tiếp chuỗi đã đọc sai rồi lại encode UTF-8, hệ thống có thể tạo một tệp hợp lệ về mặt UTF-8 **nhưng nội dung đã sai**.

Cần phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Unicode code point** | Số định danh của ký tự/dấu, ví dụ `U+1EBF` |
| **Charset** | Quy tắc ánh xạ giữa chuỗi ký tự và chuỗi byte, ví dụ UTF-8 |
| **Encoding** | Chuyển ký tự thành byte |
| **Decoding** | Chuyển byte thành ký tự |
| **BOM** | Một chuỗi byte ở đầu dữ liệu được dùng làm dấu nhận dạng/byte-order trong một số encoding |
| **Mojibake** | Văn bản sai hình dạng vì byte đã được giải mã/biến đổi theo charset sai |
| **Replacement character** | `U+FFFD`, thường xuất hiện khi decoder thay dữ liệu byte không hợp lệ |
| **Font/glyph issue** | Ký tự Unicode đúng nhưng hệ thống vẽ thiếu glyph hoặc shaping phù hợp |

**Thay font không sửa được một `String` đã bị decode thành các code point sai.** Ngược lại, nếu `String` vẫn đúng nhưng font thiếu chữ, đổi charset của tệp không giải quyết vấn đề hiển thị.

## 2. UTF-8, UTF-16 và Byte Order Mark

### 2.1. UTF-8 không cần thứ tự byte

UTF-8 mã hóa một code point bằng từ một đến bốn byte, có cấu trúc xác định nên **không có lựa chọn big-endian hay little-endian** cho từng đơn vị mã như UTF-16. Vì thế UTF-8 **không cần BOM để xác định byte order**.

Một số tệp UTF-8 được ghi bắt đầu bằng ba byte:

```text
EF BB BF
```

Đây là **UTF-8 BOM** — thực chất là biểu diễn UTF-8 của `U+FEFF`. Nó đôi khi được dùng như chữ ký cho phần mềm cần nhận biết UTF-8. Nhưng BOM UTF-8 không phải điều kiện bắt buộc, và trong nhiều giao thức hoặc công cụ xử lý dữ liệu nó gây phiền phức vì bị coi là một ký tự đầu nội dung.

Ví dụ tệp CSV có BOM UTF-8 có thể khiến chương trình parser không xử lý BOM nhận tên cột đầu tiên là `"\uFEFFid"` chứ không phải `"id"`. Người nhìn bằng editor thường không thấy ký tự này.

**Không viết BOM UTF-8 theo thói quen.** Hãy xem hợp đồng file/đích nhận có yêu cầu BOM hay không. Khi giao tiếp giữa các dịch vụ hoặc lưu JSON/CSV, charset nên được khai báo và thống nhất, không phụ thuộc một dấu byte không bắt buộc.

### 2.2. UTF-16 cần xét endianness

UTF-16 dùng các code unit 16-bit. Khi serialize thành byte, mỗi code unit phải được ghi theo một thứ tự byte:

- **Big-endian (BE)**: byte có trọng số cao trước.
- **Little-endian (LE)**: byte có trọng số thấp trước.

BOM cho UTF-16 thường là:

| Dạng | Byte đầu | Ý nghĩa |
| --- | --- | --- |
| UTF-16BE có BOM | `FE FF` | Byte order big-endian |
| UTF-16LE có BOM | `FF FE` | Byte order little-endian |
| UTF-8 có BOM | `EF BB BF` | Chữ ký UTF-8; không liên quan endianness |

Ví dụ, code point `U+FEFF` khi biểu diễn bằng UTF-16BE cho `FE FF` và bằng UTF-16LE cho `FF FE`. Nếu phần mềm đoán sai thứ tự byte của dữ liệu UTF-16, nó có thể cho code point khác hoặc lỗi giải mã.

`StandardCharsets.UTF_16` xử lý dạng UTF-16 có BOM để xác định byte order; `UTF_16BE` và `UTF_16LE` chọn thứ tự tường minh. Sự khác nhau giữa các charset này ảnh hưởng việc có xử lý BOM làm metadata hay coi `U+FEFF` là ký tự. Không nên coi cả ba là alias luôn có hành vi giống nhau.

### 2.3. UTF-32 và những dấu mở đầu khác

UTF-32 cũng có BE/LE, các BOM hay gặp là `00 00 FE FF` (BE) và `FF FE 00 00` (LE). Tuy nhiên, `java.nio.charset.StandardCharsets` **không khai báo hằng UTF-32** như một charset chuẩn bắt buộc; nếu code phụ thuộc UTF-32, cần kiểm tra charset/provider thực tế trước khi dùng.

Bài chủ yếu tập trung vào UTF-8/UTF-16 vì hai dạng này phổ biến trong hệ thống Java. Không đoán encoding của tệp chỉ bằng vài byte đầu nếu không có BOM: một chuỗi byte có thể hợp lệ theo nhiều encoding. Khi không có metadata, phát hiện charset bằng thống kê chỉ là **suy đoán**, không thể bảo đảm 100%.

## 3. Java xử lý BOM UTF-8 như thế nào?

Đây là điều dễ bất ngờ: khi giải mã `EF BB BF` bằng `StandardCharsets.UTF_8`, một số API Java tổng quát **giữ `U+FEFF` như ký tự đầu chuỗi** thay vì tự bỏ.

Ví dụ:

```java
byte[] bytes = {
    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
    (byte) 'A', (byte) 'B', (byte) 'C'
};

String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.length());
System.out.println((int) text.charAt(0));
```

Đây là đoạn minh họa trong phương thức có import `java.nio.charset.StandardCharsets`. Kết quả:

```text
4
65279
```

`65279` là giá trị thập phân của `U+FEFF`. Mặc dù màn hình có thể trông như chỉ hiện `ABC`, bên trong `text` có bốn code unit; chuỗi này không bằng `"ABC"` theo `equals`.

Tương tự, `Files.readString(path, StandardCharsets.UTF_8)` đọc tệp có BOM UTF-8 và có thể trả chuỗi bắt đầu bằng `U+FEFF`. API không có hợp đồng chung tự xóa mọi BOM của mọi charset; cách xử lý phụ thuộc bộ giải mã, thư viện và định dạng.

### Loại BOM đúng chỗ

Nếu một định dạng **cho phép BOM UTF-8 như chữ ký** và quy định không coi nó là dữ liệu nội dung, có thể loại **một ký tự `U+FEFF` ở đầu** sau khi decode:

```java
static String stripLeadingBom(String s) {
    return s.startsWith("\uFEFF") ? s.substring(1) : s;
}
```

Đây là phương thức đặt trong một lớp Java; không phải chương trình độc lập. Không xóa `U+FEFF` ở mọi vị trí trong văn bản bằng `replace(...)` một cách vô điều kiện: nếu dữ liệu cho phép các ký tự điều khiển/định dạng có ý nghĩa khác, thao tác đó sẽ làm thay đổi nội dung.

**Quan trọng:** chỉ loại BOM nếu *file format/ứng dụng* xác định BOM là metadata. Đối với giao thức cấm BOM, có thể đúng hơn là **từ chối input** và báo lỗi rõ. Đừng làm sạch âm thầm khiến dữ liệu sai schema được chấp nhận.

### Tại sao dấu BOM xuất hiện trong tên header?

Nếu tệp CSV là:

```text
EF BB BF 69 64 2C 6E 61 6D 65 ...
BOM       i  d  ,  n  a  m  e ...
```

và parser không bỏ BOM, tên cột đầu tiên trở thành `"\uFEFFid"`. Khi code truy cập `columns.get("id")`, nó có thể không tìm thấy dù người dùng nhìn file thấy cột `id`.

Cách xử lý tốt: xác định encoding từ schema, đọc đúng charset, xử lý BOM **ở đầu stream hoặc đầu file** theo quy tắc định dạng rồi mới parse CSV; không tự chuyển/đổi tên mọi cột để che mất vấn đề.

## 4. Nguồn gốc chữ bị lỗi mã hóa: mojibake

Một ví dụ đơn giản:

```text
Chuỗi gốc:       Café
UTF-8 bytes:     43 61 66 C3 A9
Đọc nhầm Latin-1: CafÃ©
```

Ở đây `é` được encode UTF-8 thành `C3 A9`, nhưng nếu hai byte đó bị giải mã theo ISO-8859-1/Latin-1, chúng thành `Ã` và `©`. Kết quả là **hai ký tự sai**; về sau dù hiển thị bằng font tốt vẫn có `CafÃ©`, vì `String` bên trong đã không còn là `Café`.

Với tiếng Việt, mô thức tương tự có thể tạo các cụm như `Tiáº¿ng`, `Viá»‡t`. Tùy bảng mã một byte và byte cụ thể, có ký tự điều khiển hoặc dấu câu khác; không phải mọi hệ thống đều tạo **chính xác cùng chuỗi mojibake**. Ví dụ Windows-1252 và ISO-8859-1 khác nhau ở một số byte từ `80` tới `9F`.

### Các kiểu lỗi thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Cần kiểm tra |
| --- | --- | --- |
| `CafÃ©`, `Tiáº¿ng` | Byte UTF-8 bị decode như single-byte charset | Hex file / charset đọc |
| `���` hoặc dấu `�` | Byte sai encoding hoặc decoder thay dữ liệu malformed | Byte gốc, `CodingErrorAction` |
| Dấu `?` thay ký tự Unicode | Encoder không biểu diễn được ký tự rồi thay bằng `?` | Charset lúc ghi, dữ liệu đã mất |
| Ký tự `ï»¿` ở đầu | BOM UTF-8 bị decode sai như Windows-1252 | Ba byte mở đầu `EF BB BF` |
| Ký tự vô hình `U+FEFF` ở đầu | BOM UTF-8 bị giữ sau decode UTF-8 | `codePointAt(0)` |
| Editor đúng, terminal sai | Charset stdout/terminal không khớp hoặc font thiếu glyph | Redirect stdout ra file và xem hex |
| File đọc đúng, JSON/HTTP sai | Header/schema không đúng, có decode/encode thêm ở gateway | Raw network bytes, content type |
| Chỉ một số ký tự thành ô vuông | Có thể là font/glyph thiếu | Kiểm tra code point vẫn đúng không |

Bảng này giúp định hướng điều tra, không chứng minh nguyên nhân chỉ bằng mắt nhìn. Có trường hợp văn bản đã bị encode/decode sai **nhiều lần**, và chuỗi lỗi nhìn phức tạp hơn.

### Lỗi decode khác lỗi encode

**Decode sai:** byte gốc đúng nhưng được diễn giải thành ký tự sai.

```text
UTF-8 bytes của é: C3 A9
        |
decode ISO-8859-1
        v
Ký tự: Ã©
```

**Encode sai hoặc thay thế:** chuỗi Java chứa ký tự đúng, nhưng nó được ghi bằng charset không hỗ trợ ký tự ấy. Encoder có thể thay bằng byte `3F` tương ứng dấu `?`. Khi đó dữ liệu đã mất, không thể suy lại chính xác ký tự ban đầu chỉ từ dấu `?`.

**Hiển thị sai:** byte stream đúng và `String` đúng, nhưng terminal/renderer dùng charset sai hoặc font không có glyph. Trường hợp này thường có thể sửa ở tầng hiển thị **không cần đụng tới dữ liệu gốc**.

## 5. Một code point sai không thể sửa bằng Normalize

`java.text.Normalizer` xử lý Unicode normalization như NFC/NFD. Nó giải quyết quan hệ chuẩn tắc giữa một ký tự ghép sẵn và chuỗi dấu kết hợp, ví dụ chữ tiếng Việt `ế` so với `e + circumflex + acute`.

Nhưng `"CafÃ©"` không phải một dạng NFD của `"Café"`. Chúng chứa những code point **khác nghĩa** do giải mã sai charset. Vì thế:

```java
Normalizer.normalize(broken, Normalizer.Form.NFC)
```

không phải giải pháp tổng quát để khôi phục chữ bị mojibake.

Đôi khi có thể “phục hồi” chuỗi mojibake bằng cách encode lại theo charset sai đã dùng, rồi decode theo charset gốc. Nhưng chỉ thực hiện an toàn khi **biết chắc đường biến đổi trước đó và chưa mất byte**. Nếu hệ thống đã thay dữ liệu bằng `?` hoặc `U+FFFD`, hoặc đã áp dụng nhiều bước chuyển đổi, có thể không thể khôi phục nguyên bản.

**Ưu tiên lấy lại byte nguồn** và đọc đúng charset; đừng sửa một loạt bằng việc thay `Ã` hoặc `áº` thủ công.

## 6. Java 17 và các JDK mới hơn: charset mặc định thay đổi ra sao?

Một số API Java nếu không truyền charset sẽ dùng **default charset**. Trên Java 17 và nhiều JDK cũ, charset mặc định có thể phụ thuộc hệ điều hành, locale và cấu hình môi trường. Vì vậy cùng một chương trình có thể đọc/ghi byte khác nhau ở các máy.

Từ **JDK 18**, JEP 400 chuẩn hóa mặc định của các API Java liên quan về UTF-8 theo chính sách mới, với các trường hợp tương thích được quy định. Nhưng sự thay đổi này **không có nghĩa mọi byte input/output của tất cả chương trình Java đều tự trở thành UTF-8**, càng không chứng minh stdout, terminal, file cũ và API bên ngoài đã thống nhất.

Ví dụ những điểm cần phân biệt:

- `Charset.defaultCharset()` cho biết default charset của runtime theo hợp đồng của nó.
- `System.getProperty("file.encoding")` có thể phản ánh cấu hình mặc định nhưng không nên dùng nó như phương thức điều khiển mọi stream trong toàn ứng dụng; hành vi được hỗ trợ phụ thuộc phiên bản JDK.
- `System.console()` có thể là `null` khi chương trình chạy trong IDE, background service, pipeline hoặc stdout bị redirect.
- `Console.charset()` (có trong Java 17) cho biết charset của console được kết nối **khi có console**.
- `System.out` là `PrintStream` do runtime tạo với cơ chế liên quan môi trường stdout; **đừng mặc định nó có cùng charset với `Charset.defaultCharset()`** ở mọi nơi.
- `System.err` và `System.out` có thể tới những đích khác nhau, mỗi đích có chính sách ghi/hiển thị riêng.

### Một đoạn chẩn đoán môi trường

```java
import java.io.Console;
import java.nio.charset.Charset;

System.out.println("defaultCharset="
        + Charset.defaultCharset().name());

Console console = System.console();
System.out.println("hasConsole=" + (console != null));

if (console != null) {
    System.out.println("consoleCharset="
            + console.charset().name());
}
```

Đây là đoạn minh họa trong phương thức. **Không ghi stdout cố định** vì kết quả phụ thuộc nơi chạy; cần dùng nó để kiểm tra thực tế.

Nếu `console == null`, chương trình không thể suy rằng không có terminal hiển thị hoặc rằng stdout chắc chắn dùng UTF-8. Trong IDE, terminal giả, CI runner hoặc lệnh redirect, khái niệm `Console` của Java có thể không tồn tại dù có nơi thu nhận output.

Không dùng các system property nội bộ, không được Java API bảo đảm như một hợp đồng portable, để lập luận rằng mọi stdout trên mọi JDK đã được sửa.

## 7. Console và terminal: stdout đi qua những lớp nào?

Một chuỗi in bằng:

```java
System.out.println("Tiếng Việt");
```

cần ít nhất những bước sau:

```text
Java source/bytecode
        |
String với code point Unicode
        |
System.out / PrintStream: encode ký tự thành byte
        |
stdout stream
        |
  +-------------------------+
  | terminal / IDE / CI     |
  | giải mã byte thành chữ  |
  | chọn font và render     |
  +-------------------------+
        |
Người dùng nhìn thấy văn bản
```

Ngoài ra nếu stdout bị redirect:

```text
java App > output.txt
```

thì byte đi vào **file**, không trực tiếp vào trình vẽ terminal. Khi mở `output.txt`, editor lại phải chọn encoding thích hợp. Nếu byte đúng nhưng editor tự nhận encoding sai, bạn có thể nhìn thấy mojibake dù chương trình đã ghi đúng byte.

### Terminal, shell và console không phải một thứ

- **Shell** như PowerShell, `cmd.exe` hoặc Bash phân tích lệnh, quoting, pipeline và một số bước chuyển đổi stdin/stdout.
- **Terminal emulator/console host** hiển thị glyph, xử lý input/output và có thể gắn với một code page.
- **JVM** mã hóa ký tự do `System.out` viết thành byte trước khi đưa ra stdout.
- **Font renderer** vẽ glyph từ Unicode code point. Thiếu glyph có thể cho ô vuông dù byte/code point hoàn toàn đúng.

Vì vậy câu “đã chuyển terminal sang UTF-8” chỉ nói **một phần** của đường đi; vẫn cần kiểm tra JVM, shell và những công cụ trong pipeline.

### Windows: code page và PowerShell

Trong các môi trường Windows, lệnh:

```powershell
chcp
```

hiển thị code page hiện tại của console host trong bối cảnh phù hợp; một số môi trường cho phép chọn UTF-8 bằng `chcp 65001`. Tuy nhiên, **code page không đồng nghĩa charset của mọi chương trình con hay mọi thao tác ghi tệp**.

PowerShell còn có những thiết lập/khác biệt theo phiên bản, ví dụ:

- `[Console]::OutputEncoding` liên quan encoding dùng cho console output theo .NET trong một số đường đi.
- `$OutputEncoding` có thể ảnh hưởng cách PowerShell mã hóa text khi gửi qua stdin của native command.
- `Out-File` và toán tử redirect `>` có hành vi encoding khác nhau giữa Windows PowerShell 5.1 và PowerShell phiên bản mới.
- Windows PowerShell 5.1 có một số thao tác ghi file dùng UTF-16LE BOM theo mặc định, còn các đường dẫn khác có thể dùng encoding khác. **Không giả định mọi lệnh ghi file trong PowerShell 5.1 có cùng mặc định.**

Ví dụ, đưa source hoặc lệnh vào stdin của công cụ Java từ một pipeline PowerShell có thể tạo byte BOM/encoding khác điều công cụ mong đợi. Nếu ký tự `U+FEFF` bị coi là một ký tự trong mã nguồn chứ không phải dấu file, một parser có thể báo lỗi `illegal character: '\ufeff'`.

Không có một câu lệnh Windows duy nhất được bảo đảm khắc phục mọi vấn đề. Cần xác định **đường truyền cụ thể**: output của Java, stdin qua PowerShell, file redirect, hoặc văn bản hiển thị.

### Linux, macOS, Docker và CI

Nhiều môi trường hiện đại dùng UTF-8, nhưng không nên xem đó là hợp đồng mọi container/pipeline. Một process có thể nhận byte UTF-8 qua stdout, trong khi trình thu log/terminal giả định encoding khác. CI có thể ghi nhận stdout thành tệp rồi phục vụ qua web UI; đường đi này có thêm tầng decode.

Khi chạy trong Docker, cần xem metadata môi trường và cách log driver/collector đọc byte; thay `LANG` hoặc locale hệ điều hành không tự sửa một file vốn đã bị decode sai trước đó.

## 8. Chọn API Java có charset tường minh

### 8.1. API nên dùng cho tệp văn bản UTF-8

Trong Java 17+, ưu tiên:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("messages.txt");

Files.writeString(path, "Tiếng Việt", StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa trong phương thức có khai báo hoặc xử lý `IOException`. Khi chỉ định `UTF_8`, ý định được thể hiện rõ: không phụ thuộc charset mặc định của JVM và không tự cần một BOM để Java biết encoding.

`Files.writeString(path, text)` và `Files.readString(path)` đã có mặc định **UTF-8 theo hợp đồng API** kể từ khi được bổ sung vào Java 11; truyền tham số charset vẫn nên dùng khi muốn làm rõ giao ước hoặc viết mã nhất quán với những API khác.

Các API thường cần chú ý:

| API | Chính sách cần nhớ |
| --- | --- |
| `Files.readString(path, UTF_8)` | Decode UTF-8 được chỉ định |
| `Files.writeString(path, text, UTF_8)` | Encode UTF-8 được chỉ định; không tự thêm UTF-8 BOM |
| `Files.newBufferedReader(path, UTF_8)` | Reader với charset rõ |
| `Files.newBufferedWriter(path, UTF_8)` | Writer với charset rõ |
| `new InputStreamReader(in, UTF_8)` | Decode stream bytes thành ký tự |
| `new OutputStreamWriter(out, UTF_8)` | Encode ký tự thành stream bytes |
| `new FileReader(file)` trên Java 17 | Dùng default charset nếu không chỉ định |
| `new FileReader(file, charset)` | Dùng charset được truyền |
| `new String(bytes, UTF_8)` | Decode byte với UTF-8 |
| `text.getBytes(UTF_8)` | Encode chuỗi với UTF-8 |

Chú ý không nên nói “mọi API `Files` đều dùng default charset”: `readString`/`writeString` mặc định UTF-8 theo hợp đồng, trong khi các API khác phải xem overload cụ thể.

### 8.2. StandardCharsets thay tên chuỗi

Thay vì viết:

```java
new String(bytes, "UTF-8");
```

có thể dùng:

```java
new String(bytes, StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` là hằng chuẩn được Java bảo đảm hỗ trợ, tránh lỗi gõ sai tên encoding và thể hiện mục đích rõ. Một số charset tương thích cũ có thể truy cập qua `Charset.forName("windows-1252")` nếu thực sự cần và môi trường hỗ trợ, nhưng đừng dùng charset đó thay UTF-8 cho dữ liệu mới chỉ vì terminal có hiện tượng lỗi.

### 8.3. JSON, HTTP, CSV và properties có hợp đồng riêng

Đừng chuyển text từ API hay database thành một charset chỉ vì muốn terminal hiển thị đẹp.

- **JSON trao đổi hiện đại:** xác định UTF-8 theo giao thức, đồng thời dùng thư viện JSON chuẩn; việc có BOM hoặc không phải theo định dạng. RFC 8259 yêu cầu UTF-8 cho JSON giữa các hệ thống không nằm trong cùng một môi trường đóng, và sender không nên thêm BOM.
- **HTTP:** charset có thể do loại media, specification và `Content-Type` quyết định. Đừng tự suy mọi body là text UTF-8 nếu giao thức khác nói khác.
- **CSV:** bản thân tên CSV không bảo đảm charset; hai phía cần thống nhất charset, delimiter, escape và chính sách BOM.
- **Java `Properties`:** `Properties.load(InputStream)` có hợp đồng đọc ISO-8859-1 với Unicode escapes, còn `Properties.load(Reader)` theo charset của `Reader`. Đừng nhầm hai API với đường nạp tài nguyên `ResourceBundle`/`PropertyResourceBundle` trên JDK hiện đại.
- **Database/JDBC:** truyền text bằng API kiểu ký tự, thiết lập client/server encoding và schema đúng; không encode một `String` thành byte tùy tiện rồi lưu vào cột văn bản để tránh lỗi console.

Charset của **dữ liệu lưu trữ** và charset của **log đang hiển thị** phải được kiểm soát độc lập.

## 9. Decoder nghiêm ngặt và ký tự thay thế U+FFFD

Một mảng byte có thể **không hợp lệ theo UTF-8**. Ví dụ byte `C3 28` gồm một byte bắt đầu chuỗi đa byte nhưng byte tiếp theo không phải continuation byte.

Có hai chính sách phổ biến:

1. **Thay lỗi bằng ký tự replacement** để chương trình vẫn tạo được text và tiếp tục hiển thị.
2. **Báo lỗi ngay** vì dữ liệu phải tuân thủ nghiêm ngặt UTF-8.

Trong Java:

```java
byte[] malformed = {(byte) 0xC3, (byte) 0x28};

String permissive = new String(
        malformed, StandardCharsets.UTF_8);

System.out.println(permissive.contains("\uFFFD"));
```

Đây là đoạn minh họa trong một phương thức; kết quả `true` cho thấy decoder sử dụng replacement.

Nếu nhập liệu yêu cầu **không chấp nhận UTF-8 malformed**, dùng `CharsetDecoder`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

try {
    StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(malformed));
} catch (CharacterCodingException ex) {
    // Từ chối payload không phải UTF-8 hợp lệ.
}
```

Đây là đoạn minh họa trong một phương thức có `malformed` đã khai báo. `REPORT` giúp tránh việc một payload sai bị “chấp nhận” bằng cách âm thầm thay byte không hợp lệ.

**Không thể luôn khôi phục ký tự ban đầu từ `U+FFFD`.** Nếu byte gốc không còn và nhiều chuỗi byte khác nhau đều bị thay bằng cùng ký tự, thông tin đã mất. Tương tự, byte `3F` do encoder thay bằng dấu `?` không chứa cách phục hồi chắc chắn code point gốc.

Không tùy tiện xóa mọi `U+FFFD` rồi coi dữ liệu đã sạch; có thể che đi lỗi truyền dữ liệu quan trọng.

## 10. Ví dụ Java 17+ chạy độc lập: bytes, BOM và lỗi decode

Ví dụ tạo một tệp tạm rồi xóa khi xong, tránh sửa dữ liệu trong project. Nó in **hex và code point** thay vì phụ thuộc terminal có hiển thị tiếng Việt đúng hay không.

Tạo tệp `CharsetAndBomDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.Locale;
import java.util.stream.Collectors;

public class CharsetAndBomDemo {
    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) throws Exception {
        String original = "Ti\u1EBFng Vi\u1EC7t";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 hex: "
                + HexFormat.of().formatHex(utf8));

        String correct = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 round-trip: "
                + original.equals(correct));

        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 equals original: "
                + wrong.equals(original));
        System.out.println("Latin-1 code points: "
                + codePoints(wrong));

        byte[] bom = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF
        };
        byte[] withBom = new byte[bom.length + utf8.length];
        System.arraycopy(bom, 0, withBom, 0, bom.length);
        System.arraycopy(utf8, 0, withBom, bom.length, utf8.length);

        Path file = Files.createTempFile("charset-demo-", ".txt");
        try {
            Files.writeString(
                    file, original, StandardCharsets.UTF_8);
            byte[] clean = Files.readAllBytes(file);

            boolean hasBom = clean.length >= 3
                    && (clean[0] & 0xFF) == 0xEF
                    && (clean[1] & 0xFF) == 0xBB
                    && (clean[2] & 0xFF) == 0xBF;

            System.out.println("writeString adds BOM: " + hasBom);

            Files.write(file, withBom);
            String read = Files.readString(
                    file, StandardCharsets.UTF_8);

            System.out.println("UTF-8 BOM first cp: "
                    + String.format(
                        Locale.ROOT, "U+%04X", read.codePointAt(0)));
            System.out.println("strip BOM works: "
                    + read.substring(1).equals(original));
        } finally {
            Files.deleteIfExists(file);
        }

        byte[] malformed = {
                (byte) 0xC3, (byte) 0x28
        };
        String replacement = new String(
                malformed, StandardCharsets.UTF_8);

        System.out.println("replacement occurs: "
                + replacement.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("strict decoder: accepted");
        } catch (CharacterCodingException ex) {
            System.out.println("strict decoder: rejected");
        }

        byte[] utf16 = original.getBytes(StandardCharsets.UTF_16);
        System.out.println("UTF-16 header: "
                + HexFormat.of().formatHex(utf16, 0, 2));
        System.out.println("UTF-16 round-trip: "
                + original.equals(
                    new String(utf16, StandardCharsets.UTF_16)));
    }
}
```

Lệnh biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 CharsetAndBomDemo.java
java CharsetAndBomDemo
```

Stdout đã kiểm chứng, không phụ thuộc font chữ của console:

```text
UTF-8 hex: 5469e1babf6e67205669e1bb8774
UTF-8 round-trip: true
Latin-1 equals original: false
Latin-1 code points: U+0054 U+0069 U+00E1 U+00BA U+00BF U+006E U+0067 U+0020 U+0056 U+0069 U+00E1 U+00BB U+0087 U+0074
writeString adds BOM: false
UTF-8 BOM first cp: U+FEFF
strip BOM works: true
replacement occurs: true
strict decoder: rejected
UTF-16 header: feff
UTF-16 round-trip: true
```

### Giải thích chính xác output

- `UTF-8 hex` là dãy byte của `Tiếng Việt`. Chữ `ế` tương ứng `E1 BA BF`; chữ `ệ` tương ứng `E1 BB 87`.
- `UTF-8 round-trip: true` chứng minh khi encode/decode cùng UTF-8, chuỗi khôi phục chính xác.
- `Latin-1 equals original: false` và dãy code point cho thấy decode nhầm byte thành **những ký tự khác** chứ không phải lỗi font.
- `writeString adds BOM: false` chứng minh thao tác ghi UTF-8 bình thường không tự chèn ba byte `EF BB BF`.
- Khi chương trình **chủ động thêm BOM** và đọc lại bằng UTF-8, ký tự đầu là `U+FEFF`; loại đúng ký tự đầu giúp so sánh được với dữ liệu gốc.
- `replacement occurs: true` minh họa cách decode mặc định cho byte malformed có thể thay bằng `U+FFFD`.
- `strict decoder: rejected` cho thấy `CharsetDecoder` cấu hình `REPORT` phát hiện byte malformed.
- `UTF-16 header: feff` chứng minh `StandardCharsets.UTF_16` có thể ghi BOM của dạng UTF-16BE mặc định ở đầu; decoder UTF-16 tương ứng đọc lại được chuỗi.

Mục đích chính của ví dụ là kiểm tra **byte và code point**. Nếu terminal hiển thị chữ Việt bị lỗi, stdout chứa hex và giá trị `U+...` vẫn giúp bạn phân biệt chính xác dữ liệu đã thay đổi ở đâu.

## 11. Biên dịch Java source và charset của tệp nguồn

Đường đi của **source code** cần tách khỏi charset của stdout và dữ liệu runtime.

```text
.java file bytes
     |
javac decode source theo encoding
     |
Class file với constant String
     |
JVM chạy chương trình
     |
System.out encode khi in
     |
Terminal decode/render
```

Nếu tệp `.java` chứa chữ Việt thật (không phải Unicode escape) nhưng `javac` đọc source theo encoding sai, bytecode có thể chứa ký tự sai **ngay từ lúc biên dịch**. Lúc đó sửa terminal không làm class file tự đúng lại.

Trên JDK 17, lựa chọn rõ là:

```bash
javac -encoding UTF-8 Main.java
```

Hãy bảo đảm tệp source thực sự được lưu UTF-8. Lệnh trên chỉ quy định cách compiler đọc source, không tự chuyển tệp gốc từ Windows-1258, UTF-16 hay charset legacy khác thành UTF-8.

Trong các hệ thống build như Maven/Gradle, nên khai báo source encoding/charset của resource filtering rõ ràng. Không coi tên file `.java` hoặc `.properties` là bằng chứng nội dung bên trong đang ở UTF-8.

### Unicode escape trong ví dụ có ích nhưng không thay kiểm tra pipeline

Viết:

```java
String name = "Ti\u1EBFng Vi\u1EC7t";
```

cho phép source phần literal sử dụng ASCII nhưng runtime tạo đúng chữ Việt. Điều này giảm phụ thuộc terminal/editor trong ví dụ giáo dục, nhưng không nên dùng escape cho mọi văn bản dịch ở ứng dụng thực. Với nội dung i18n, ưu tiên file tài nguyên đúng encoding, pipeline build đáng tin và test round-trip.

## 12. Chẩn đoán theo từng tầng, không sửa bằng đoán mò

Khi gặp chữ lỗi, làm theo thứ tự:

### Bước 1 — xác định dữ liệu bắt đầu ở đâu

Nguồn có thể là:

- Tệp văn bản/CSV/JSON đọc từ đĩa.
- Request HTTP hoặc response từ dịch vụ khác.
- Bản ghi database trả về qua JDBC.
- File properties/resource bundle.
- Literal được biên dịch trong `.class`.
- Text do người dùng nhập qua console/stdin.

Không thể đưa ra lời giải thích “sai UTF-8” chính xác nếu chưa biết **nguồn byte**, bên gửi và định dạng được công bố.

### Bước 2 — giữ byte gốc trước khi sửa

Nếu đọc tệp, xem các byte đầu và vài byte quanh ký tự lỗi. Ví dụ dùng Java:

```java
byte[] raw = Files.readAllBytes(path);
System.out.println(HexFormat.of().formatHex(raw));
```

Đây là đoạn minh họa trong phương thức với `path` kiểu `Path` và import `Files`/`HexFormat`. Khi tệp lớn, chỉ in một vùng byte cần thiết, không xả dữ liệu nhạy cảm vào log.

Nhìn thấy `EF BB BF` tại offset 0 cho biết có dấu mở đầu UTF-8 BOM; nhìn thấy `E1 BA BF` cho biết các byte phù hợp với chữ `ế` theo UTF-8. Nhưng **một số byte khớp không chứng minh toàn bộ file hợp lệ UTF-8**: nếu cần, dùng decoder strict trên toàn payload.

### Bước 3 — decode bằng charset theo hợp đồng

Không chọn charset theo “máy hiện đang là Windows” hoặc “file có chữ tiếng Việt”. Chọn theo metadata/đặc tả: UTF-8, UTF-16 hoặc charset legacy được nhà cung cấp dữ liệu công bố.

Nếu không có metadata, dùng công cụ nhận diện charset như **gợi ý** rồi kiểm tra với nguồn gốc và nội dung dự kiến; không coi charset detection thống kê là chân lý chắc chắn.

### Bước 4 — kiểm tra String trước khi in

So sánh code point, không dựa hoàn toàn vào console:

```java
String value = ...; // Giá trị nhận từ nguồn đã đọc
value.codePoints()
     .forEach(cp -> System.out.printf("U+%04X%n", cp));
```

Đây là đoạn minh họa trong phương thức với `value` đã được khai báo. Vì định dạng `U+XXXX` dùng ASCII, kết quả giúp xác định `String` đang chứa ký tự đúng hay đã chứa mojibake.

Nếu `String` đã sai, hãy sửa bước decode/nguồn. Nếu `String` đúng nhưng terminal hiển thị sai, tập trung vào stdout encoder, terminal decoder và font.

### Bước 5 — tách stdout khỏi terminal

Thử redirect output ra tệp rồi xem hex tệp đó. Lưu ý chính shell/redirect có thể có hành vi encoding riêng, nên nếu cần kiểm chứng tuyệt đối, hãy cho Java ghi một tệp bằng `Files.writeString(..., UTF_8)` và xem raw bytes.

Nếu tệp Java ghi tường minh UTF-8 đúng mà màn hình terminal sai, không nên sửa dữ liệu trong database. Nếu tệp stdout có byte sai, cần xem encoder của `System.out` hoặc lớp chuyển đổi của pipeline.

### Bước 6 — xem chế độ thay thế lỗi

Khi gặp `�` hoặc `?`, xác định nó được tạo ở bước nào. Nếu là decoder hoặc encoder thay thế, cần xem lại byte nguồn sớm nhất. Một bước đã thay dữ liệu có thể làm việc khôi phục chính xác không còn khả thi.

### Bước 7 — bổ sung test regression

Tạo fixture có:

- Tiếng Việt có dấu: `Tiếng Việt`, `đ`, `ắ`, `ệ`.
- Chữ Latin có dấu như `Café`.
- Một ký tự ngoài BMP như emoji để kiểm tra surrogate/UTF-8 4 byte.
- Tệp UTF-8 có và không có BOM.
- Tệp UTF-16BE/LE có BOM theo đặc tả đang hỗ trợ.
- Byte UTF-8 malformed để test `REPORT`.
- Dữ liệu có tên cột CSV đầu tiên bị `U+FEFF`.
- Kịch bản redirect stdout/CI nếu ứng dụng phụ thuộc log.

Kết quả test nên xác minh **byte, code point, tên charset và các exception**, không chỉ là một screenshot trông có vẻ đúng.

## 13. Những hướng khắc phục sai phổ biến

### “Bỏ BOM ở mọi chỗ”

Sai: một file không có BOM thì không cần loại, còn `U+FEFF` nằm giữa nội dung có thể cần được xử lý theo chính sách riêng. BOM của UTF-16 khác UTF-8. Nên chỉ loại hoặc từ chối BOM ở đầu theo đúng format và charset.

### “Chỉ cần đổi font”

Nếu `String` đã thành `CafÃ©`, font không khôi phục `é`. Font chỉ sửa được việc **glyph không hiển thị** khi code point vẫn đúng.

### “Chỉ cần đổi `file.encoding`”

Trên các JDK, `file.encoding` và default charset có cơ chế được xác định theo phiên bản; JVM runtime, console, shell, công cụ build và file I/O có thể không đồng bộ. Dù đổi default charset, những lời gọi đã có `StandardCharsets.UTF_8` vẫn dùng UTF-8 theo tham số; file bị hỏng trước đó cũng không tự sửa.

### “Chỉ cần đổi PowerShell sang UTF-8”

Đổi encoding của một lớp đường đi không chắc sửa lớp khác, đặc biệt là native stdin, stdout, redirect file và editor đọc file. Hãy kiểm tra byte thực tế ở mỗi ranh giới.

### “Đã decode được String thì chắc đúng”

Một `String` có thể chứa mojibake hợp lệ về mặt Unicode. Decoder dùng replacement có thể trả chuỗi dù byte nguồn sai. Thành công của API không chứng minh **ngữ nghĩa text** đã khôi phục đúng.

### “Lỗi dấu nên chạy NFC”

NFC/NFD giúp thống nhất cách biểu diễn **chuẩn tắc** của dấu Unicode, không sửa những code point được tạo do decode UTF-8 thành Latin-1. Khi chỉ có mojibake, normalize sẽ giữ nguyên sai lầm về charset.

### “Đọc UTF-8 thì BOM luôn tự biến mất”

Không đúng cho nhiều API Java thường dùng: `new String(bytes, UTF_8)` và `Files.readString(path, UTF_8)` có thể giữ `U+FEFF` trong text. Hãy kiểm tra contract của thư viện/format rồi xử lý có chủ đích.

### “Một lần thấy ký tự `�` là sửa bằng replaceAll”

`U+FFFD` có thể đại diện cho nhiều tình huống malformed khác nhau. Xóa nó có thể che lỗi mất dữ liệu. Nên dùng decoder strict khi yêu cầu dữ liệu nguyên vẹn và truy ngược byte nguồn.

## 14. Checklist cho dự án Java thực tế

| Câu hỏi | Hướng xử lý |
| --- | --- |
| Dữ liệu lưu/trao đổi theo charset nào? | Ghi vào schema, hợp đồng HTTP/file và test |
| Java đọc/ghi bằng API nào? | Truyền `StandardCharsets.UTF_8` hoặc charset được quy định |
| Có BOM không? | Xác định chính sách ở byte đầu, không xóa mọi ký tự vô hình |
| JVM version nào? | Phân biệt mặc định JDK 17 với JDK 18+ |
| Default charset có được dùng ngầm không? | Tránh khi dữ liệu cần ổn định qua môi trường |
| `System.console()` có tồn tại? | Không suy từ nó về mọi stdout redirect |
| Shell/terminal/CI đọc stdout bằng gì? | Kiểm tra encoder → bytes → decoder → font |
| Có hiện `U+FFFD` hoặc `?`? | Tìm bước replacement trước khi thông tin mất |
| File CSV header có ký tự ẩn? | Kiểm tra `U+FEFF` ở đầu sau khi decode |
| Có nhập liệu từ charset legacy? | Chuyển đổi tại ranh giới biết rõ charset gốc |
| Có dùng byte/string để ký hoặc hash? | Không đổi encoding/normalization mà không theo hợp đồng |
| Có kiểm thử dữ liệu Unicode đa ngôn ngữ? | Kiểm tra byte, code point và round-trip |
| Có log byte gốc chứa bí mật? | Tránh lộ dữ liệu, chỉ log vùng/snapshot đã kiểm soát |

## 15. Bài tập tự kiểm tra

**Bài 1 — byte và ký tự.** Chữ `é` có UTF-8 bytes nào? Vì sao decode `C3 A9` bằng Latin-1 tạo `Ã©`? Phân biệt lỗi này với trường hợp font không vẽ được `é`.

**Bài 2 — BOM.** Nêu byte mở đầu UTF-8 BOM, UTF-16BE BOM và UTF-16LE BOM. Vì sao UTF-8 không cần BOM cho thứ tự byte? Khi nào UTF-8 BOM có thể được xem là dấu nhận dạng hữu ích, và khi nào nên cấm?

**Bài 3 — Java đọc tệp.** Viết code dùng `Files.readString(path, UTF_8)`. Một tệp bắt đầu `EF BB BF`, kết quả `codePointAt(0)` là gì? Đề xuất cách chỉ bỏ một BOM đầu nếu format cho phép.

**Bài 4 — printf và stdout.** Một literal Java đã đúng Unicode nhưng terminal Windows hiển thị sai. Bạn sẽ kiểm tra `String` trước khi in, byte đã đi qua stdout, code page, font và đường redirect theo thứ tự nào?

**Bài 5 — JDK.** So sánh rủi ro default charset trên Java 17 với thay đổi JEP 400 từ Java 18. Vì sao `Charset.defaultCharset() == UTF_8` vẫn chưa chứng minh console hoặc toàn bộ file cũ là UTF-8?

**Bài 6 — malformed UTF-8.** Với hai byte `C3 28`, thử `new String(bytes, UTF_8)` và `UTF_8.newDecoder().onMalformedInput(REPORT)`. Cách nào có thể trả chuỗi chứa `U+FFFD`, cách nào phải báo lỗi?

**Bài 7 — CSV.** Một file `id,name` có BOM UTF-8 ở đầu. Vì sao parser có thể không tìm thấy cột `id`? Nếu sản phẩm hỗ trợ cả file có và không BOM, bạn sẽ đặt bước xử lý ở đâu?

**Bài 8 — build.** Một tệp Java UTF-8 chứa literal tiếng Việt được compiler đọc với charset sai. Sửa mã output của terminal có đủ không? Nêu cách biên dịch với `-encoding UTF-8` và test code point của literal.

**Bài 9 — pipeline nhiều lớp.** Một service nhận UTF-8 nhưng decode sai rồi ghi lại thành UTF-8. Tệp đầu ra có thể hợp lệ UTF-8 nhưng văn bản sai như thế nào? Khi nào sửa bằng cách encode/decode lại còn khả thi?

**Bài 10 — bảo vệ dữ liệu.** Một payload có `U+FFFD` và một payload khác có glyph thiếu trong font. Hai tình huống này có khác nhau về tính toàn vẹn dữ liệu không? Thiết kế test để xác định nguyên nhân.

## 16. Kết luận

Lỗi mã hóa không phải một vấn đề duy nhất của terminal. Để có chữ tiếng Việt đúng, cần kiểm soát **charset ở từng ranh giới byte ↔ ký tự**. `String` trong Java có thể đúng hoặc sai độc lập với font đang vẽ nó. Khi đọc UTF-8 thành Latin-1, các byte đúng tạo ra code point sai; khi ghi bằng charset không biểu diễn được chữ, encoder có thể thay bằng `?`; khi decode malformed bytes, dữ liệu có thể bị thay bằng `U+FFFD` và không còn khôi phục chính xác được.

**BOM** giúp nhận diện byte order ở UTF-16 và đôi khi được dùng như chữ ký UTF-8, nhưng không được tự áp dụng hoặc tự xóa ở mọi định dạng. `Files.readString(..., UTF_8)` vẫn có thể giữ `U+FEFF` ở đầu nội dung nếu byte BOM UTF-8 tồn tại.

Trong Java 17+, ưu tiên API với `StandardCharsets.UTF_8` hoặc charset được schema công bố; ghi rõ source encoding ở build; khi phát hiện lỗi, kiểm tra **raw bytes → decoder → String code points → encoder → stdout/terminal → font**. Với payload nghiêm ngặt, cấu hình `CharsetDecoder` dùng `CodingErrorAction.REPORT` để không âm thầm che dữ liệu malformed.

**Nguyên tắc cốt lõi:** *Đừng chữa chữ lỗi bằng cách đoán encoding hoặc thay font. Tìm đúng tầng đã biến byte thành ký tự sai, rồi sửa giao ước charset tại ranh giới đó.*

### Tài liệu tham khảo

- [`Charset` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html)
- [`StandardCharsets` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [`CharsetDecoder` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [`Files` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Console.charset()` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html#charset())
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)
- [Unicode FAQ: UTF-8, UTF-16, UTF-32 and BOM](https://www.unicode.org/faq/utf_bom.html)
