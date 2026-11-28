# Đối chiếu `stdout.encoding` và `stderr.encoding` với tài liệu của đúng JDK đang dùng

## 1. Vì sao phải kiểm tra hai thuộc tính riêng?

Trong Java, `System.out` và `System.err` đều là `PrintStream`, nhưng chúng phục vụ hai luồng đầu ra khác nhau:

- `System.out` thường chứa kết quả chính mà chương trình hoặc tiến trình gọi cần nhận.
- `System.err` thường chứa thông báo lỗi, cảnh báo và thông tin chẩn đoán để có thể theo dõi riêng, kể cả khi stdout đã được chuyển hướng.

Hai stream có charset riêng:

- `stdout.encoding` mô tả encoding được dùng khi `System.out` chuyển ký tự thành byte.
- `stderr.encoding` mô tả encoding được dùng khi `System.err` chuyển ký tự thành byte.

Từ JDK 18, theo **JEP 400**, UTF-8 là default charset thông thường của các API Java SE phụ thuộc default charset. Nhưng **`System.out` và `System.err` không dùng `Charset.defaultCharset()`**. Chúng theo các thuộc tính riêng ở trên.

Bài này đối chiếu hợp đồng của **Java SE 24**, đúng feature release của runtime workspace đang dùng: **Azul Zulu OpenJDK 24.0.2**. Mục tiêu là đọc đúng tài liệu của phiên bản, kiểm tra giá trị thực tế và hiểu ảnh hưởng khi redirect stdout/stderr ra file hoặc pipe.

## 2. Xác định đúng JDK trước khi đọc tài liệu

Không nên lấy tài liệu của một phiên bản JDK khác rồi mặc định mọi chi tiết đều giống nhau. Trước hết, kiểm tra phiên bản và nhà cung cấp của runtime thực sự dùng để chạy ứng dụng:

```powershell
java -version
```

Trên workspace dùng để soạn bài này, kết quả là:

```text
openjdk version "24.0.2" 2025-07-15
OpenJDK Runtime Environment Zulu24.32+13-CA
OpenJDK 64-Bit Server VM Zulu24.32+13-CA
```

Đây là bản phân phối Azul Zulu của OpenJDK, triển khai Java SE 24. Khi đối chiếu hợp đồng API, sử dụng tài liệu Java SE 24 tương ứng; khi kiểm tra hành vi thực tế, chạy chính runtime Azul Zulu 24.0.2 trên môi trường triển khai.

### 2.1. Xem các property liên quan đến encoding

Trên Windows PowerShell:

```powershell
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.version|java.vendor|file.encoding|native.encoding|stdout.encoding|stderr.encoding'
```

Trên Linux hoặc macOS:

```bash
java -XshowSettings:properties -version 2>&1 |
    grep -E 'java.version|java.vendor|file.encoding|native.encoding|stdout.encoding|stderr.encoding'
```

Các property quan trọng cần ghi nhận:

| Property | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản runtime đang chạy |
| `java.vendor` | Nhà cung cấp JDK |
| `file.encoding` | Default charset mà JDK chọn |
| `native.encoding` | Encoding môi trường gốc mà JDK phát hiện |
| `stdout.encoding` | Encoding của `System.out` |
| `stderr.encoding` | Encoding của `System.err` |

**Kết quả đo tại workspace hiện tại**:

```text
java.version      = 24.0.2
java.vendor       = Azul Systems, Inc.
file.encoding     = UTF-8
native.encoding   = UTF-8
stdout.encoding   = UTF-8
stderr.encoding   = UTF-8
```

Các giá trị này là kết quả của runtime và môi trường workspace tại thời điểm kiểm tra, không phải giá trị bắt buộc trên mọi máy chạy JDK 24.

## 3. Hợp đồng Java SE 24 quy định gì?

Tài liệu `System` của Java SE 24 mô tả riêng hai trường:

| Trường trong `System` | Kiểu | Encoding theo hợp đồng |
| --- | --- | --- |
| `System.out` | `PrintStream` | Tương ứng với `stdout.encoding` |
| `System.err` | `PrintStream` | Tương ứng với `stderr.encoding` |

Tài liệu Java SE 24 còn quy định:

- `System.out` thường nối với thiết bị hiển thị hoặc một đích đầu ra do môi trường chỉ định.
- `System.err` thường dùng cho thông báo lỗi hoặc thông tin cần được theo dõi riêng, kể cả khi `System.out` đã chuyển hướng.
- Hai thuộc tính `stdout.encoding` và `stderr.encoding` có giá trị mặc định phụ thuộc nền tảng.
- Khi nền tảng không cung cấp console streams, giá trị mặc định của các thuộc tính này lấy theo `native.encoding`.

Điều này có nghĩa một JVM có default charset UTF-8 vẫn có thể có stdout hoặc stderr dùng encoding khác, tùy môi trường. Ngược lại, khi nền tảng không cung cấp console streams, hai giá trị có thể cùng bằng `native.encoding`.

### 3.1. Phân biệt với `file.encoding` và `native.encoding`

| Giá trị | Điều nó mô tả | Có đại diện cho stdout/stderr không? |
| --- | --- | --- |
| `file.encoding` | Default charset của JDK | Không |
| `native.encoding` | Encoding môi trường gốc do JDK phát hiện | Chỉ là cơ sở mặc định trong một số môi trường không có console streams |
| `stdout.encoding` | Encoding của `System.out` | Có |
| `stderr.encoding` | Encoding của `System.err` | Có |
| `Charset.defaultCharset()` | Charset mặc định mà các API phụ thuộc default charset sử dụng | Không trực tiếp |

Không dùng `Charset.defaultCharset()` để suy ra charset của hai print stream. Cũng không lấy `native.encoding` làm kết luận nếu đã có giá trị `stdout.encoding` và `stderr.encoding` cụ thể.

### 3.2. JEP 400 không gộp hai stream về UTF-8

JEP 400 chuẩn hóa default charset của nhiều API Java SE từ JDK 18. Thay đổi đó tác động đến những API như `String.getBytes()` hoặc các constructor reader/writer không truyền charset.

`System.out` và `System.err` là các standard streams đã được JVM khởi tạo riêng. Charset của chúng theo `stdout.encoding` và `stderr.encoding`. Vì vậy, không thể kết luận rằng hai stream dùng UTF-8 chỉ từ kết quả:

```java
System.out.println(Charset.defaultCharset().name());
```

Lệnh trên chỉ in default charset của JVM. Muốn kiểm tra stream thực tế, dùng `PrintStream.charset()`.

## 4. Đối chiếu chi tiết `stdout.encoding` và `stderr.encoding` trong tài liệu Java SE 24

Đọc hai phần trong tài liệu chính thức:

1. `System` — phần *Field Details* và *Standard System Properties*.
2. `Supported Encodings` — phần *Default Charset* và ghi chú về standard output/error streams.

Nội dung của hai property:

| Property | Được mô tả cho | Điểm cần lưu ý trong tài liệu Java SE 24 |
| --- | --- | --- |
| `stdout.encoding` | `System.out` và `System.console()` | Là tên charset dùng cho output. Tài liệu `System` nói rõ runtime có thể được khởi chạy với giá trị `UTF-8`; giá trị khác dẫn đến hành vi không được đặc tả. |
| `stderr.encoding` | `System.err` | Là tên charset dùng cho error output. Giá trị mặc định phụ thuộc nền tảng; tài liệu Supported Encodings hướng dẫn chỉ định encoding qua property này. |

Điểm cần giữ chính xác khi đọc tài liệu: `stdout.encoding` và `stderr.encoding` là **hai property khác nhau**, mô tả hai đích khác nhau. Không giả định chúng luôn bằng nhau. Tài liệu `System` của Java SE 24 nêu rõ giới hạn startup `UTF-8` trong mô tả `stdout.encoding`; khi cấu hình theo vendor hoặc runtime cụ thể, cần đọc đúng phần property tương ứng và không suy diễn rằng mọi tên charset đều được hỗ trợ như nhau.

Nếu ứng dụng cần một output UTF-8 portable, hãy dùng cấu hình UTF-8 được tài liệu runtime hỗ trợ. Nếu ứng dụng cần ghi một file bằng charset khác, tạo stream riêng với charset tường minh thay vì dựa vào việc ép encoding toàn cục của standard streams.

### 4.1. Giá trị mặc định khi môi trường có console

Khi môi trường cung cấp console streams, encoding được thiết lập theo môi trường và người dùng. Với console tương tác, charset ghi của `Console` dựa trên `stdout.encoding`.

`Console.charset()` cho biết charset dùng cho thao tác ghi của console. Phương thức này không phải API để đọc charset của `System.err`. Muốn xem encoding của error stream, kiểm tra `stderr.encoding` hoặc gọi `System.err.charset()` trên JDK 18+.

### 4.2. Giá trị mặc định khi môi trường không cung cấp console streams

Tài liệu Java SE 24 Supported Encodings ghi rõ: khi nền tảng không cung cấp streams cho console, giá trị mặc định của `stdout.encoding` và `stderr.encoding` lấy theo `native.encoding`.

Đây là lý do trong môi trường chạy nền, service hoặc một số cách khởi chạy không gắn với terminal, hai property có thể trùng với encoding môi trường gốc. Tuy nhiên, vẫn cần đọc giá trị thực tế của process; không tự gán encoding chỉ từ tên hệ điều hành.

## 5. Kiểm tra charset thực tế bằng `PrintStream.charset()`

Từ **Java 18**, `PrintStream.charset()` trả về đối tượng `Charset` mà instance `PrintStream` đang dùng. Vì `System.out` và `System.err` đều là `PrintStream`, có thể kiểm tra trực tiếp:

```java
import java.nio.charset.Charset;

System.out.println("stdout property = "
        + System.getProperty("stdout.encoding"));
System.err.println("stderr property = "
        + System.getProperty("stderr.encoding"));

System.out.println("System.out charset = "
        + System.out.charset().name());
System.err.println("System.err charset = "
        + System.err.charset().name());

System.out.println("default charset = "
        + Charset.defaultCharset().name());
```

Khi đối chiếu kết quả, có thể dùng bảng sau:

| So sánh | Điều cần xác nhận |
| --- | --- |
| `System.out.charset()` với `stdout.encoding` | Charset thực tế của output stream có khớp property khởi tạo không |
| `System.err.charset()` với `stderr.encoding` | Charset thực tế của error stream có khớp property khởi tạo không |
| Hai giá trị `stdout.encoding` và `stderr.encoding` | Hai stream có cùng encoding hay không |
| Hai charset stream với `Charset.defaultCharset()` | Standard streams có khác default charset không |
| Hai charset stream với `native.encoding` | Môi trường gốc có trùng encoding stream hay không |

**Kết quả đo tại workspace Azul Zulu 24.0.2**:

```text
System.out.charset() = UTF-8
System.err.charset() = UTF-8
stdout.encoding      = UTF-8
stderr.encoding      = UTF-8
file.encoding        = UTF-8
native.encoding      = UTF-8
```

Trong môi trường này, cả hai stream và default charset cùng dùng UTF-8. Kết quả đó chỉ xác nhận cấu hình của process hiện tại; không chứng minh rằng stdout/stderr trên các máy khác luôn giống nhau.

### 5.1. Vì sao nên kiểm tra cả property lẫn đối tượng stream?

Property mô tả cấu hình mà JVM công bố. `PrintStream.charset()` trả charset của **đối tượng stream hiện tại**.

Ứng dụng có thể gọi `System.setOut(...)` hoặc `System.setErr(...)` để thay thế stream chuẩn bằng một `PrintStream` khác được tạo với charset tường minh. Khi đó:

- `stdout.encoding` hoặc `stderr.encoding` vẫn là property của tiến trình.
- `System.out.charset()` hoặc `System.err.charset()` phản ánh stream đang được gắn tại thời điểm kiểm tra.
- Hai kết quả có thể khác nhau nếu ứng dụng đã thay thế stream.

Do đó, khi điều tra ứng dụng lớn, cần tìm xem có thành phần nào gọi `System.setOut` hoặc `System.setErr` hay không. Không chỉ dựa vào giá trị property để kết luận byte thực tế được ghi.

## 6. Kiểm tra trong môi trường chạy thật

### 6.1. Dùng chương trình probe nhỏ

Có thể tạo một lớp Java độc lập để in thông tin của đúng process:

```java
import java.io.PrintStream;
import java.nio.charset.Charset;

public class StreamEncodingProbe {
    public static void main(String[] args) {
        PrintStream out = System.out;
        PrintStream err = System.err;

        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));

        System.out.println("file.encoding = "
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding = "
                + System.getProperty("native.encoding"));

        System.out.println("stdout.encoding = "
                + System.getProperty("stdout.encoding"));
        System.err.println("stderr.encoding = "
                + System.getProperty("stderr.encoding"));

        System.out.println("defaultCharset = "
                + Charset.defaultCharset().name());
        System.out.println("out.charset = " + out.charset().name());
        System.err.println("err.charset = " + err.charset().name());
    }
}
```

Biên dịch và chạy với source file UTF-8:

```bash
javac -encoding UTF-8 StreamEncodingProbe.java
java StreamEncodingProbe
```

Dùng đúng executable `java` và `javac` của runtime cần kiểm tra. Nếu máy có nhiều JDK, xác minh `java -version` và `javac -version` để tránh biên dịch bằng một JDK nhưng chạy bằng JDK khác.

### 6.2. Đọc riêng stdout và stderr khi redirect

Trên Windows PowerShell:

```powershell
java StreamEncodingProbe 1> stdout.txt 2> stderr.txt
```

Trên Linux/macOS:

```bash
java StreamEncodingProbe 1> stdout.txt 2> stderr.txt
```

Sau khi chạy, đọc hai file theo charset tương ứng. Nếu `stdout.encoding` là UTF-8 nhưng `stderr.encoding` là một charset khác, hai file cần được giải mã độc lập.

Có thể gộp hai luồng:

```bash
java StreamEncodingProbe > combined.log 2>&1
```

Nhưng nếu stdout và stderr dùng charset khác nhau, file gộp có thể chứa các đoạn byte theo hai encoding. Công cụ đọc log chỉ dùng một charset sẽ không thể giải mã đúng toàn bộ nội dung. Nếu cần một log duy nhất, nên cấu hình cả hai stream cùng encoding theo cách được runtime hỗ trợ hoặc dùng một logging pipeline có charset thống nhất.

### 6.3. Chuyển hướng không tự chuyển đổi byte sang UTF-8

Shell redirect thay đổi **đích nhận byte**. Nó không phải một bước decode/encode văn bản để tự động chuẩn hóa file đầu ra sang UTF-8.

Ví dụ:

- `> stdout.txt` đưa byte từ `System.out` vào file.
- `2> stderr.txt` đưa byte từ `System.err` vào file.
- `2>&1` gộp hai luồng vào đích đã chuyển hướng theo thứ tự shell xử lý.

Nếu muốn đọc file redirect bằng UTF-8, phải xác nhận stream đã tạo byte UTF-8. Không kết luận encoding chỉ từ đuôi `.txt` hoặc `.log`.

## 7. `System.out` và `System.err` có thể khác nhau như thế nào?

Giả sử một môi trường có các giá trị:

```text
file.encoding   = UTF-8
native.encoding = windows-1258
stdout.encoding = UTF-8
stderr.encoding = windows-1258
```

Đây là ví dụ giả định để minh họa sự độc lập của các thuộc tính, không phải cấu hình mặc định được bảo đảm bởi JDK. Nếu runtime thực tế cho phép và khởi tạo hai stream như vậy, byte của stdout và stderr phải được giải mã theo hai charset tương ứng.

Trong trường hợp này:

- File nhận stdout được đọc bằng UTF-8.
- File nhận stderr được đọc bằng Windows-1258.
- Nếu gộp hai luồng thành một file, file có thể chứa byte thuộc hai encoding.
- `Charset.defaultCharset()` vẫn là UTF-8; nó không thay đổi encoding của stderr.

Với ứng dụng thực tế, không nên tự đặt một giá trị charset tùy ý cho standard stream nếu tài liệu JDK không bảo đảm hành vi đó. Ví dụ này chỉ giải thích vì sao phải đọc và đối chiếu hai property riêng.

## 8. Những điểm cần kiểm tra trong tài liệu Java SE 24

Khi đọc tài liệu của đúng phiên bản, hãy tập trung vào các phần sau:

| Tài liệu | Phần cần đọc | Thông tin cần lấy |
| --- | --- | --- |
| `System` (Java SE 24 API) | Field Details: `out` | Encoding của `System.out` tương ứng `stdout.encoding` |
| `System` (Java SE 24 API) | Field Details: `err` | Encoding của `System.err` tương ứng `stderr.encoding` |
| `System` (Java SE 24 API) | Standard System Properties | Ý nghĩa và giới hạn cấu hình của từng property |
| `PrintStream` (Java SE 24 API) | `charset()` | Charset của instance stream hiện tại; có từ Java 18 |
| `Console` (Java SE 24 API) | `charset()` và read/write operations | Charset của console và mối liên hệ với stdout |
| `Supported Encodings` (Java SE 24) | Default Charset | Standard streams không dùng default charset; property defaults theo nền tảng |

Khi nâng cấp lên một JDK khác, hãy mở tài liệu của chính feature release đang triển khai. Không sao chép một nhận định về property từ Java SE 24 sang JDK khác nếu tài liệu phiên bản đó đã thay đổi.

### 8.1. Không nhầm `Console.charset()` với `System.err.charset()`

`Console.charset()` cho biết charset của console, mặc định dựa trên `stdout.encoding`. Nó không phải cách kiểm tra charset của `System.err`.

Để so sánh riêng:

```java
System.out.println(System.out.charset().name());
System.err.println(System.err.charset().name());
```

Dòng thứ nhất đọc charset của stdout; dòng thứ hai đọc charset của stderr. Hai kết quả có thể giống hoặc khác nhau.

## 9. Lựa chọn xử lý khi encoding không khớp

Nếu `stdout.encoding` hoặc `stderr.encoding` khác encoding mà hệ thống nhận mong đợi, hãy xác định rõ ai sở hữu output và cần hợp đồng nào.

| Nhu cầu | Cách xử lý |
| --- | --- |
| Output chính phải là UTF-8 | Dùng cấu hình UTF-8 mà JDK hiện hành hỗ trợ cho stdout, sau đó kiểm tra `System.out.charset()` |
| Error output phải được lưu và đọc như UTF-8 | Kiểm tra `stderr.encoding` và `System.err.charset()` trên runtime; xác nhận cấu hình startup theo tài liệu vendor |
| Ghi một file UTF-8 riêng | Dùng `Files.writeString(path, text, StandardCharsets.UTF_8)` hoặc writer/print stream riêng với charset UTF-8 |
| Ghi file theo charset legacy | Tạo writer/print stream riêng với charset được định dạng file yêu cầu |
| Hai stream bị gộp vào một log | Bảo đảm chúng dùng cùng encoding hoặc ghi qua một logging system có encoding thống nhất |
| Ứng dụng thay thế `System.out`/`System.err` | Kiểm tra charset của stream mới qua `PrintStream.charset()` |

Ví dụ tạo một `PrintStream` riêng để ghi file UTF-8, không phụ thuộc charset của standard streams:

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

try (PrintStream log = new PrintStream(
        Path.of("application.log").toFile(),
        StandardCharsets.UTF_8)) {
    log.println("Tiếng Việt: xử lý thành công");
}
```

Đây là stream do ứng dụng tạo và sở hữu; charset của nó được truyền trực tiếp qua constructor. Không cần thay đổi `file.encoding`, `stdout.encoding` hoặc `stderr.encoding` để ghi một file riêng.

### 9.1. Không thay đổi property sau khi stream đã khởi tạo

Không dùng:

```java
System.setProperty("stdout.encoding", "UTF-8");
System.setProperty("stderr.encoding", "UTF-8");
```

với kỳ vọng các standard streams đang tồn tại tự khởi tạo lại encoder. Tài liệu `System` cảnh báo rằng thay đổi standard system property sau initialization có thể không có tác dụng mong muốn vì giá trị có thể đã được cache.

Nếu cần thay stream chuẩn trong ứng dụng, `System.setOut` và `System.setErr` cho phép gán một `PrintStream` mới. Tuy nhiên, đây là thay đổi toàn cục ảnh hưởng đến mọi thành phần trong JVM; chỉ thực hiện khi ứng dụng thực sự sở hữu cấu hình process và đã kiểm soát các thư viện dùng stream đó.

## 10. Kết quả đối chiếu trên runtime workspace

Khi kiểm tra runtime tại workspace, các giá trị quan sát được là:

| Hạng mục | Giá trị |
| --- | --- |
| Runtime | Azul Zulu OpenJDK 24.0.2 |
| Vendor build | Zulu24.32+13-CA |
| OS | Windows |
| `file.encoding` | UTF-8 |
| `native.encoding` | UTF-8 |
| `stdout.encoding` | UTF-8 |
| `stderr.encoding` | UTF-8 |
| `System.out.charset()` | UTF-8 |
| `System.err.charset()` | UTF-8 |

Kết quả này phù hợp với hợp đồng Java SE 24: `System.out` dùng `stdout.encoding` và `System.err` dùng `stderr.encoding`. Trong môi trường workspace hiện tại, hai property cùng là UTF-8 nên không thấy khác biệt về byte encoding giữa hai luồng.

Khi chuyển ứng dụng sang máy khác, container khác hoặc một JDK vendor khác, hãy chạy lại probe và đối chiếu tài liệu tương ứng. Không lấy kết quả của workspace này làm giá trị mặc định cho mọi deployment.

## 11. Bài tập tự kiểm tra

**Bài 1.** JDK 24 có `Charset.defaultCharset()` trả về UTF-8. Có thể kết luận `System.out` và `System.err` đều dùng UTF-8 không?

*Đáp án:* Không. `System.out` dùng `stdout.encoding`; `System.err` dùng `stderr.encoding`. Hai property có default theo nền tảng và có thể khác `file.encoding` hoặc `native.encoding`.

**Bài 2.** `stdout.encoding` và `stderr.encoding` có phải cùng một property không?

*Đáp án:* Không. Chúng là hai property riêng cho hai print stream. Cần kiểm tra từng giá trị và từng đối tượng `PrintStream`.

**Bài 3.** Trên Java SE 24, phương thức nào giúp kiểm tra charset thực tế của `System.err`?

*Đáp án:* `System.err.charset()`, vì `System.err` là `PrintStream` và `PrintStream.charset()` có từ Java 18.

**Bài 4.** Nếu môi trường không cung cấp console streams, default của `stdout.encoding` và `stderr.encoding` được tài liệu Java SE 24 mô tả như thế nào?

*Đáp án:* Các giá trị mặc định lấy theo `native.encoding`. Dù vậy, vẫn nên kiểm tra property thực tế của process.

**Bài 5.** Nếu chạy `java App > all.log 2>&1`, điều gì có thể xảy ra khi stdout và stderr có charset khác nhau?

*Đáp án:* Hai luồng cùng ghi vào một đích nhưng byte được tạo theo hai encoding khác nhau. File gộp có thể không được giải mã đúng bằng một charset duy nhất.

**Bài 6.** Có nên gọi `System.setProperty("stderr.encoding", "UTF-8")` trong `main()` để đổi charset của `System.err` không?

*Đáp án:* Không nên dựa vào cách này. Standard system properties có thể được đọc hoặc cache khi khởi tạo stream. Hãy cấu hình theo tài liệu runtime lúc khởi động hoặc tạo một `PrintStream` riêng với charset tường minh cho đích do ứng dụng quản lý.

## 12. Ghi nhớ

`stdout.encoding` và `stderr.encoding` là hai thuộc tính riêng mô tả encoding của `System.out` và `System.err`. Chúng không phải `file.encoding` và cũng không đồng nghĩa với `Charset.defaultCharset()`. Theo tài liệu Java SE 24, giá trị mặc định phụ thuộc nền tảng; khi nền tảng không cung cấp console streams, chúng lấy theo `native.encoding`.

Trên runtime workspace Azul Zulu 24.0.2, cả hai property và hai lời gọi `PrintStream.charset()` đều trả về UTF-8. Đây là kết quả đo tại một môi trường cụ thể. Khi triển khai ở môi trường khác, hãy kiểm tra lại bằng `-XshowSettings:properties` và `PrintStream.charset()`, sau đó đối chiếu với tài liệu của đúng JDK đang chạy.

Khi cần ghi file hoặc payload có hợp đồng encoding rõ ràng, hãy tạo stream riêng với charset được chỉ định tường minh. Chỉ dựa vào stdout/stderr khi bạn đã xác định đúng encoding của process và của hệ thống nhận dữ liệu.

### Tài liệu tham khảo chính thức — Java SE 24

- [Oracle Java SE 24 — System: System.out, System.err và Standard System Properties](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html).
- [Oracle Java SE 24 — Supported Encodings: Default Charset và standard streams](https://docs.oracle.com/en/java/javase/24/intl/supported-encodings.html).
- [Oracle Java SE 24 — PrintStream: charset()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/PrintStream.html).
- [Oracle Java SE 24 — Console: charset()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/Console.html).
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
