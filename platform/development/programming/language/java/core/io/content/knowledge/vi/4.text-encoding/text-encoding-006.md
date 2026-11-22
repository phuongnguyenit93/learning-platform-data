# BOM và sự khác biệt giữa UTF-16, UTF-16BE, UTF-16LE trong Java

## Mục tiêu bài học

Khi đọc hoặc ghi văn bản bằng **luồng byte**, tên charset không chỉ quyết định cách ánh xạ ký tự Unicode thành byte: với UTF-16, nó còn quyết định **thứ tự byte (byte order)** và cách xử lý **BOM (Byte Order Mark)**. Sau bài học, bạn sẽ:

- Giải thích được vì sao cùng một văn bản lại có dãy byte khác nhau khi dùng UTF-16BE và UTF-16LE.
- Nhận biết BOM `FE FF`, `FF FE` và phân biệt BOM với dữ liệu ký tự thông thường.
- Hiểu chính xác cách Java `StandardCharsets.UTF_16`, `UTF_16BE` và `UTF_16LE` mã hóa/giải mã dữ liệu.
- Viết chương trình Java 17+ có thể kiểm chứng byte thực tế, xử lý tệp có hoặc không có BOM và tránh đọc sai nội dung.

## 1. Nền tảng: UTF-16 mã hóa *đơn vị mã* thành byte

Unicode xác định **code point** (điểm mã), chẳng hạn `U+0041` cho chữ `A` và `U+1F600` cho emoji 😀. UTF-16 biểu diễn code point thành một hoặc hai **code unit 16 bit**:

- Với ký tự thuộc Basic Multilingual Plane (BMP), trừ vùng surrogate, UTF-16 thường dùng một code unit 16 bit. Ví dụ `A` là `0x0041`.
- Với code point ngoài BMP, UTF-16 dùng **một cặp surrogate** gồm hai code unit. Ví dụ `U+1F600` được biểu diễn bằng `D83D DE00`.
- **16 bit = 2 byte**, nhưng thứ tự của hai byte trong mỗi code unit có thể khác nhau. Do đó UTF-16 không đồng nghĩa “mọi ký tự luôn chiếm hai byte”.

Khi cần chuyển code unit `0x0041` thành byte:

| Kiểu lưu | Thứ tự byte | Dãy hex |
| --- | --- | --- |
| Big-endian (BE) | Byte cao trước | `00 41` |
| Little-endian (LE) | Byte thấp trước | `41 00` |

Với chuỗi `A😀`, các code unit lần lượt là `0041 D83D DE00`:

- **UTF-16BE:** `00 41 D8 3D DE 00`.
- **UTF-16LE:** `41 00 3D D8 00 DE`.

Hai dãy khác nhau về thứ tự byte trong **từng code unit**, nhưng đều có thể biểu diễn cùng một chuỗi khi bộ giải mã biết rõ byte order.

## 2. BOM là gì, nằm ở đâu?

**BOM (Byte Order Mark)** là dấu hiệu ở **đầu dữ liệu byte** giúp bên đọc nhận biết thứ tự byte của UTF-16 khi định dạng không quy định sẵn BE hay LE. BOM liên hệ với code point `U+FEFF`, được mã hóa khác nhau tùy byte order:

| Hai byte đầu | Ý nghĩa trong UTF-16 |
| --- | --- |
| `FE FF` | BOM của UTF-16 big-endian |
| `FF FE` | BOM của UTF-16 little-endian |

Vì vậy, tệp chứa chữ `A` có thể trông như sau:

```text
UTF-16 BE có BOM: FE FF | 00 41
UTF-16 LE có BOM: FF FE | 41 00
UTF-16 BE không BOM:  00 41
UTF-16 LE không BOM:  41 00
```

Dấu `|` chỉ để phân biệt **BOM** và **payload**; nó không phải byte trong tệp.

Có vài điểm rất quan trọng:

1. **Không phải mọi dữ liệu UTF-16 đều bắt buộc có BOM.** Một giao thức hoặc định dạng có thể công bố rõ UTF-16BE/UTF-16LE, khi đó byte order đã biết và không cần BOM.
2. **BOM không chứa độ dài dữ liệu.** Nó chỉ hỗ trợ nhận biết cách giải mã ở đầu dòng byte.
3. **BOM không phải ký tự hiển thị thông thường.** Khi bộ giải mã UTF-16 nhận diện BOM là chữ ký byte order, chữ ký đó thường không trở thành ký tự trong kết quả giải mã.
4. **BOM có thể được hiểu là ký tự `U+FEFF` nếu dùng bộ giải mã theo byte order cố định.** Đó là lý do một chuỗi có thể bắt đầu bằng ký tự vô hình sau khi đọc không đúng chế độ.
5. **Không nhầm với UTF-8 BOM `EF BB BF`.** UTF-8 không có hai kiểu byte order; BOM UTF-8 là vấn đề khác, không phải cách chọn BE/LE.

## 3. Ba charset UTF-16 trong Java khác nhau thế nào?

Java cung cấp sẵn ba hằng trong `java.nio.charset.StandardCharsets`:

| Charset Java | Khi **mã hóa** (String → byte[]) | Khi **giải mã** (byte[] → String) |
| --- | --- | --- |
| `StandardCharsets.UTF_16` | Tạo BOM `FE FF` rồi mã hóa nội dung theo **big-endian**. | Nếu có BOM `FE FF` / `FF FE` ở đầu thì nhận diện BE/LE tương ứng và tiêu thụ BOM; nếu **không có BOM**, mặc định giải mã theo **big-endian**. |
| `StandardCharsets.UTF_16BE` | Mã hóa big-endian; **không tự thêm BOM**. | Giải mã theo big-endian cố định; **không tự bỏ BOM** như chữ ký byte order. |
| `StandardCharsets.UTF_16LE` | Mã hóa little-endian; **không tự thêm BOM**. | Giải mã theo little-endian cố định; **không tự bỏ BOM** như chữ ký byte order. |

Đây là **hành vi của các charset Java này**, không phải lời cam kết rằng mọi trình đọc văn bản của mọi ngôn ngữ đều chọn BE khi thiếu BOM. Khi trao đổi dữ liệu giữa các hệ thống, phải làm theo tài liệu của định dạng hoặc giao thức.

### Ví dụ trực giác

Nếu nhận `41 00` mà **không có BOM**:

- Giải mã bằng `UTF_16LE`: kết quả là `A` (`U+0041`).
- Giải mã bằng `UTF_16`: Java mặc định BE, nên hai byte thành code unit `0x4100` (`U+4100`), **không phải** `A`.

Không có cách chung để đoán chắc ý nghĩa chỉ từ hai byte `41 00`; quyết định encoding phải đến từ BOM hợp lệ, metadata đáng tin cậy hoặc quy định giao thức.

## 4. Java 17+ — quan sát byte được mã hóa

Tạo tệp **`Utf16BytesDemo.java`** (mã nguồn độc lập):

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf16BytesDemo {
    private static void show(String name, Charset charset, String text) {
        byte[] bytes = text.getBytes(charset);
        System.out.println(name + " = " + HexFormat.of().formatHex(bytes));
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600));

        show("UTF-16", StandardCharsets.UTF_16, text);
        show("UTF-16BE", StandardCharsets.UTF_16BE, text);
        show("UTF-16LE", StandardCharsets.UTF_16LE, text);

        System.out.println("UTF-16 code units = " + text.length());
        System.out.println("Unicode code points = "
                + text.codePointCount(0, text.length()));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 Utf16BytesDemo.java
java Utf16BytesDemo
```

Đầu ra chính xác:

```text
UTF-16 = feff0041d83dde00
UTF-16BE = 0041d83dde00
UTF-16LE = 41003dd800de
UTF-16 code units = 3
Unicode code points = 2
```

Giải thích các con số:

- `feff` ở đầu dòng UTF-16 là BOM big-endian, do bộ mã hóa `UTF_16` tự tạo.
- Phần nội dung big-endian `0041d83dde00` giống dòng UTF-16BE. Dòng UTF-16LE đảo thứ tự byte của từng code unit thành `41003dd800de`.
- Chuỗi `A😀` có **hai Unicode code point** nhưng **ba code unit UTF-16**: `A` dùng một code unit, 😀 dùng hai code unit (surrogate pair).
- Do có BOM, dòng UTF-16 chứa **8 byte**; hai dòng BE/LE không BOM đều chứa **6 byte**. Không nên suy ra độ dài byte chỉ bằng `String.length() * 2`.

`HexFormat` có từ Java 17; ví dụ dùng nó để kết quả hex có thể so sánh chính xác giữa các máy.

## 5. Java 17+ — Java đọc BOM như thế nào?

Tạo tệp **`Utf16DecodeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf16DecodeDemo {
    public static void main(String[] args) {
        HexFormat hex = HexFormat.of();
        byte[] beWithBom = hex.parseHex("feff0041");
        byte[] leWithBom = hex.parseHex("fffe4100");
        byte[] leWithoutBom = hex.parseHex("4100");

        System.out.println("BE BOM with UTF-16 = "
                + new String(beWithBom, StandardCharsets.UTF_16));
        System.out.println("LE BOM with UTF-16 = "
                + new String(leWithBom, StandardCharsets.UTF_16));

        String wrong = new String(leWithoutBom, StandardCharsets.UTF_16);
        System.out.println("LE without BOM using UTF-16 = U+"
                + String.format("%04X", wrong.codePointAt(0)));

        System.out.println("LE without BOM using UTF-16LE = "
                + new String(leWithoutBom, StandardCharsets.UTF_16LE));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Utf16DecodeDemo.java
java Utf16DecodeDemo
```

Đầu ra chính xác:

```text
BE BOM with UTF-16 = A
LE BOM with UTF-16 = A
LE without BOM using UTF-16 = U+4100
LE without BOM using UTF-16LE = A
```

Hai trường hợp có BOM đều cho ra `A` vì `UTF_16` **đọc chữ ký đầu dữ liệu** và chọn đúng BE hoặc LE. Khi không có BOM, `UTF_16` của Java không thể biết rằng `4100` được tạo theo LE, vì vậy nó áp dụng BE mặc định. Đổi sang `UTF_16LE` giải mã đúng.

**Cẩn thận với decoder cố định byte order:** dùng `UTF_16LE` để đọc `FF FE 41 00` có thể đưa `U+FEFF` vào đầu chuỗi vì charset này không có cơ chế tự loại BOM như `UTF_16`. Đừng tự động loại bỏ ký tự đầu chuỗi của mọi file; chỉ xử lý BOM ở vị trí đầu và khi giao thức/charset mong đợi điều đó.

## 6. Ghi và đọc tệp UTF-16LE có BOM theo yêu cầu định dạng

Giả sử một hệ thống ngoài Java bắt buộc file được mã hóa **UTF-16LE và có BOM `FF FE`**. Nếu chỉ dùng:

```java
Files.writeString(path, text, StandardCharsets.UTF_16LE);
```

thì Java ghi nội dung theo LE nhưng **không tự thêm BOM**. Ngược lại, `StandardCharsets.UTF_16` tự phát BOM `FE FF` và dùng BE, **không thay thế được** yêu cầu cụ thể “UTF-16LE có BOM”.

Bạn có thể tự thêm hai byte đầu theo hợp đồng định dạng. Chương trình sau tạo file, đọc lại byte và giải mã:

Tạo tệp **`Utf16LeFileDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class Utf16LeFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample-utf16le.txt");
        String text = "A";

        byte[] payload = text.getBytes(StandardCharsets.UTF_16LE);
        byte[] bytes = new byte[payload.length + 2];
        bytes[0] = (byte) 0xFF;
        bytes[1] = (byte) 0xFE;
        System.arraycopy(payload, 0, bytes, 2, payload.length);

        Files.write(path, bytes);

        byte[] saved = Files.readAllBytes(path);
        System.out.println("file bytes = " + HexFormat.of().formatHex(saved));
        System.out.println("decoded = " + Files.readString(path, StandardCharsets.UTF_16));

        String explicitLe = Files.readString(path, StandardCharsets.UTF_16LE);
        System.out.println("fixed LE sees U+FEFF = "
                + (explicitLe.codePointAt(0) == 0xFEFF));
    }
}
```

Chạy ở thư mục mà ứng dụng có quyền tạo/ghi tệp:

```bash
javac -encoding UTF-8 Utf16LeFileDemo.java
java Utf16LeFileDemo
```

Đầu ra chính xác:

```text
file bytes = fffe4100
decoded = A
fixed LE sees U+FEFF = true
```

Đã có BOM LE, nên `Files.readString(path, StandardCharsets.UTF_16)` nhận diện đúng byte order và trả về chuỗi `A`. Với `UTF_16LE` cố định, cặp byte đầu được diễn giải thành code point `U+FEFF` trong chuỗi, nên phép kiểm tra trên trả về `true`.

Ví dụ ghi một file vật lý `sample-utf16le.txt`. Nếu chạy lại trong cùng thư mục, `Files.write` ghi nội dung mới vào tệp đó theo mặc định. Đây là hành vi của chương trình minh họa; file không được tạo chỉ bằng cách đọc bài học này.

## 7. Chọn charset khi dùng `Reader` và `Writer`

`InputStream` / `OutputStream` làm việc với byte; `Reader` / `Writer` làm việc với ký tự. Mã hóa xảy ra tại ranh giới chuyển đổi:

```java
// Đoạn minh họa, giả định inputStream và outputStream đã được tạo.
Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_16);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_16LE);
```

Hai dòng trên không phải chương trình độc lập. Trong thực tế, chọn charset theo **dữ liệu thật** và quản lý đóng stream theo quyền sở hữu tài nguyên:

- **Dữ liệu có BOM UTF-16 và cần tự nhận diện BE/LE:** đọc bằng `UTF_16`.
- **Dữ liệu rõ ràng UTF-16BE không BOM:** đọc/ghi bằng `UTF_16BE`.
- **Dữ liệu rõ ràng UTF-16LE không BOM:** đọc/ghi bằng `UTF_16LE`.
- **Định dạng yêu cầu UTF-16LE có BOM:** ghi byte `FF FE` rồi nội dung `UTF_16LE`; khi đọc, dùng `UTF_16` để nhận diện BOM hoặc xử lý bỏ BOM trước khi giải mã cố định LE theo hợp đồng.
- **Định dạng chỉ nói “UTF-16” và chấp nhận byte order tự mô tả bằng BOM:** `UTF_16` của Java là lựa chọn phù hợp với quy tắc encoding của Java.

`Files.readString`, `Files.writeString`, `InputStreamReader` và `OutputStreamWriter` đều có cách cung cấp charset; nên **nêu rõ charset** thay vì dựa vào charset mặc định của máy khi trao đổi dữ liệu giữa các hệ thống.

## 8. Lỗi phổ biến và cách chẩn đoán

### Lỗi 1: Đọc UTF-16LE không BOM bằng `UTF_16` rồi bị sai ký tự

Nguyên nhân: Java `UTF_16` mặc định **BE** khi không nhận ra BOM. Với dữ liệu đã biết LE, chỉ định `StandardCharsets.UTF_16LE`.

### Lỗi 2: Tự thêm BOM rồi lại mã hóa bằng `UTF_16`

`String.getBytes(StandardCharsets.UTF_16)` vốn tự thêm `FE FF`. Nếu còn tự ghi thêm BOM phía trước, bạn có thể tạo byte thừa hoặc đặt thêm dấu `U+FEFF` ở phần văn bản sau dấu BOM đầu. Hãy dùng một chiến lược rõ ràng: **`UTF_16` tự sinh BOM và BE**, hoặc **UTF_16BE/UTF_16LE cố định với BOM được ghi thủ công nếu cần**.

### Lỗi 3: Luôn xóa ký tự đầu của mọi chuỗi nếu nhìn thấy U+FEFF

Không được xóa tùy tiện dữ liệu người dùng. `U+FEFF` có thể là kết quả giải mã chữ ký BOM bằng charset cố định, nhưng cũng là code point có thật trong dữ liệu. Chỉ coi byte đầu là BOM theo quy tắc của định dạng đang đọc; không sửa nội dung chỉ dựa trên cảm giác “ký tự này vô hình”.

### Lỗi 4: Giả định UTF-16 luôn có hai byte mỗi ký tự

Emoji và nhiều code point ngoài BMP cần **hai code unit**, tức **bốn byte** trước khi tính BOM. Ngay cả `String.length()` cũng đếm code unit UTF-16, không đếm code point hay byte.

### Lỗi 5: Giải mã sai nhưng không phát hiện vì có ký tự thay thế

Dữ liệu UTF-16 có số byte lẻ, surrogate không hợp lệ hoặc byte order sai có thể gây lỗi giải mã. Các API tiện lợi kiểu `new String(bytes, charset)` có thể thay chuỗi byte không hợp lệ bằng ký tự thay thế. Nếu cần **phát hiện dữ liệu hỏng thay vì âm thầm thay thế**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và xử lý `CharacterCodingException`. Tuy nhiên, một chuỗi sai endian vẫn có thể tạo ra các code point hợp lệ; decoder nghiêm ngặt cũng **không thể tự đoán đúng charset** trong trường hợp đó.

### Lỗi 6: Dựa hoàn toàn vào BOM khi giao thức đã khai báo rõ charset

Không phải file nào cũng có BOM. Nếu metadata nói “UTF-16LE”, cần tuân theo quy định của định dạng về việc BOM có được phép xuất hiện hay không. Với dữ liệu ngoài hệ thống, nên kiểm tra metadata/đặc tả trước, rồi dùng decoder tương ứng và kiểm thử byte thực tế.

## 9. Bảng quyết định nhanh

| Tình huống | Lựa chọn hợp lý |
| --- | --- |
| Có `FE FF` ở đầu, muốn giải mã UTF-16 tự chọn endian | `StandardCharsets.UTF_16` |
| Có `FF FE` ở đầu, muốn giải mã UTF-16 tự chọn endian | `StandardCharsets.UTF_16` |
| Không BOM, phía gửi xác nhận big-endian | `StandardCharsets.UTF_16BE` |
| Không BOM, phía gửi xác nhận little-endian | `StandardCharsets.UTF_16LE` |
| Cần Java tự ghi UTF-16 kèm BOM theo mặc định | `StandardCharsets.UTF_16` (BOM BE) |
| Bắt buộc ghi UTF-16LE kèm BOM `FF FE` | Tự ghi hai byte `FF FE` + payload `UTF_16LE` |
| Cần đối chiếu dữ liệu giữa hệ thống | Ghi nhận dãy byte hex, BOM, charset đã khai báo và code point sau giải mã |

## 10. Tự kiểm tra

**Câu 1.** Byte `00 41` là chữ `A` trong UTF-16BE hay UTF-16LE?

**Đáp án:** UTF-16BE. Cùng chữ `A` trong LE là `41 00`.

**Câu 2.** Tệp bắt đầu `FF FE 41 00`, dùng `StandardCharsets.UTF_16` để đọc thì được gì?

**Đáp án:** `A`. `FF FE` là BOM LE, vì vậy hai byte dữ liệu `41 00` được diễn giải theo LE.

**Câu 3.** `text.getBytes(StandardCharsets.UTF_16LE)` có tự ghi BOM `FF FE` không?

**Đáp án:** Không. Charset `UTF_16LE` xác định thứ tự byte cố định nhưng không tự thêm BOM.

**Câu 4.** Tại sao `new String(new byte[]{0x41, 0x00}, StandardCharsets.UTF_16)` không cho ra `A`?

**Đáp án:** Không có BOM, `UTF_16` của Java mặc định BE nên hai byte là code unit `0x4100`.

**Câu 5.** Chuỗi `A😀` có bao nhiêu code point, bao nhiêu code unit UTF-16 và bao nhiêu byte khi mã hóa bằng `StandardCharsets.UTF_16` của Java?

**Đáp án:** Hai code point; ba code unit; sáu byte nội dung + hai byte BOM BE = **tám byte**.

## Ghi nhớ

- **`UTF_16`:** Java tự ghi BOM `FE FF` khi encode; khi decode dùng BOM để chọn BE/LE, **không có BOM thì mặc định BE**.
- **`UTF_16BE` và `UTF_16LE`:** byte order cố định, **không tự ghi/tiêu thụ BOM theo cơ chế tự nhận diện**.
- **BOM chỉ có ý nghĩa khi giải mã theo đúng hợp đồng của nguồn dữ liệu.** Xem byte gốc, biết charset/định dạng từ đâu và kiểm thử bằng chuỗi có cả ký tự BMP lẫn supplementary để tránh lỗi ẩn.
