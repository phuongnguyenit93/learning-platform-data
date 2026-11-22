# Giới hạn độ dài của `writeUTF` trong Java

`DataOutputStream.writeUTF(String)` là cách ghi một chuỗi vào **luồng dữ liệu nhị phân** của Java sao cho `DataInputStream.readUTF()` có thể đọc lại. Mỗi bản ghi gồm **2 byte tiền tố độ dài** rồi tới nội dung được mã hóa bằng **Modified UTF-8** (UTF-8 biến thể của Java). Vì tiền tố dài 2 byte không dấu, **phần nội dung đã mã hóa chỉ được tối đa 65.535 byte**. Nếu chuỗi vượt giới hạn này, `writeUTF` ném `UTFDataFormatException`.

Điểm dễ nhầm nhất: **65.535 là số byte Modified UTF-8, không phải số ký tự, không phải `String.length()`, và không tính 2 byte tiền tố.** Tùy ký tự, một đơn vị `char` của Java chiếm 1, 2 hoặc 3 byte; một emoji ngoài BMP thường chiếm tới **6 byte** trong Modified UTF-8.

Bài này thuộc mục **Dữ liệu nhị phân** của Java Core I/O. Ta sẽ hiểu định dạng trên dây, tính đúng giới hạn, nhận biết ngoại lệ, kiểm chứng bằng Java 17+, rồi chọn cách ghi dữ liệu khác khi chuỗi dài hơn giới hạn.

## 1. `writeUTF` ghi gì vào OutputStream?

Các API thường dùng:

```java
DataOutputStream out = new DataOutputStream(outputStream);
out.writeUTF(text);

DataInputStream in = new DataInputStream(inputStream);
String restored = in.readUTF();
```

Đây là **mảnh mã minh họa**: `outputStream`/`inputStream` là hai nguồn byte phù hợp, `text` là `String`; cần import `java.io.*` và xử lý `IOException`. Đầu đọc phải đứng đúng vị trí bắt đầu bản ghi và dùng đúng định dạng của `writeUTF`.

Cấu trúc bản ghi:

```text
+------------------------+-------------------------------------+
| 2 byte length          | Payload: Modified UTF-8            |
| unsigned short,        | chính xác N byte                     |
| big-endian, giá trị N  | (N từ 0 đến 65535)                 |
+------------------------+-------------------------------------+

Tổng số byte của một lần writeUTF thành công = 2 + N
N tối đa = 65535
Tổng kích thước bản ghi tối đa = 65537 byte
```

- Hai byte đầu biểu diễn `N` theo thứ tự **byte cao trước, byte thấp sau** (*big-endian*). Đọc ý nghĩa của chúng như một số nguyên không dấu 16 bit trong khoảng `0..65535`.
- `N` là **số byte payload** sau khi mã hóa *toàn bộ chuỗi* bằng Modified UTF-8.
- `DataInputStream.readUTF()` tự đọc tiền tố rồi đúng số byte payload, giải mã về `String`. Bên đọc **không** truyền riêng chiều dài chuỗi.
- Nếu payload cần **65.536 byte trở lên**, `DataOutputStream.writeUTF` ném `UTFDataFormatException` (lớp con của `IOException`) thay vì tạo một bản ghi hợp lệ.
- Chuỗi rỗng vẫn tạo **2 byte** `00 00`, vì payload có chiều dài 0.

Ví dụ: ghi `"ABC"` thì các byte của bản ghi là:

```text
00 03 41 42 43
|---| |------|
  3   "ABC" trong Modified UTF-8
```

Vì vậy `writeUTF("ABC")` khác `out.write("ABC".getBytes(UTF_8))`: lệnh đầu **tự thêm độ dài 2 byte**, lệnh sau chỉ ghi byte do bạn cung cấp.

## 2. Tại sao giới hạn là đúng 65.535 byte?

Phần độ dài được biểu diễn bằng **2 byte**, tức 16 bit, nên có thể chứa tối đa:

\[
2^{16} - 1 = 65535
\]

Trong đặc tả `DataOutput.writeUTF`, Java phải tính **tổng số byte Modified UTF-8 của chuỗi** trước khi quyết định có thể ghi. Nếu tổng vượt 65.535 byte thì gọi `writeUTF` thất bại. Đây là giới hạn **định dạng nhị phân**, không phải hạn chế bộ nhớ của `String` hoặc khả năng của `OutputStream`.

Cần phân biệt:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `s.length()` | Số đơn vị `char` UTF-16 trong chuỗi Java |
| `s.codePointCount(0, s.length())` | Số Unicode code point (không đồng nghĩa số ký tự người dùng nhìn thấy) |
| `s.getBytes(UTF_8).length` | Số byte theo **UTF-8 chuẩn** |
| `modifiedUtf8Length(s)` | Số byte **Modified UTF-8** mà `writeUTF` cần |
| `2 + modifiedUtf8Length(s)` | Kích thước của cả bản ghi `writeUTF` khi hợp lệ |

Nếu chuỗi chỉ gồm các ký tự ASCII từ `U+0001` đến `U+007F` thì mỗi `char` cần 1 byte, nên chuỗi dài 65.535 ký tự vẫn hợp lệ. Nếu toàn ký tự cần 3 byte thì chỉ 21.845 `char` là vừa giới hạn. Với dữ liệu hỗn hợp cần cộng độ dài từng đơn vị `char`.

Không nên xử lý bằng cách “trừ đi 2 byte trước” từ giới hạn 65.535: hai byte tiền tố **nằm ngoài** payload và đã được tính riêng trong kích thước bản ghi.

## 3. Modified UTF-8 không giống UTF-8 chuẩn

`DataOutputStream.writeUTF` dùng **Modified UTF-8 của giao thức `DataInput`/`DataOutput`**, chứ không dùng trực tiếp `StandardCharsets.UTF_8`.

Cách mã hóa dựa trên từng `char` Java (một đơn vị UTF-16):

| Giá trị `char` | Số byte trong Modified UTF-8 | Ghi chú |
| --- | ---: | --- |
| `U+0001` đến `U+007F` | 1 | ASCII khác NUL |
| `U+0000` (NUL) | 2 | Mã hóa thành `C0 80` |
| `U+0080` đến `U+07FF` | 2 | Chẳng hạn `é` = `C3 A9` |
| `U+0800` đến `U+FFFF` | 3 | Mỗi **đơn vị `char`**, kể cả surrogate |
| Unicode code point ngoài BMP, ví dụ `😀` | **6** | Java biểu diễn bằng **hai `char` surrogate**, mỗi `char` thành 3 byte |

Những khác biệt quan trọng:

1. **NUL:** UTF-8 chuẩn mã hóa `\u0000` thành `00` (1 byte), Modified UTF-8 mã hóa thành `C0 80` (2 byte).
2. **Emoji/code point ngoài BMP:** UTF-8 chuẩn dùng một dãy 4 byte; Modified UTF-8 xử lý cặp surrogate UTF-16 thành **hai dãy 3 byte** (tổng 6 byte).
3. **Modified UTF-8 không phải UTF-8 chuẩn để trao đổi văn bản tự do**. Không giả định `new String(payload, UTF_8)` hoặc `InputStreamReader(..., UTF_8)` sẽ đọc đúng payload `writeUTF`, nhất là khi có NUL hoặc ký tự ngoài BMP.
4. Vì cặp surrogate được mã hóa theo từng đơn vị `char`, đếm “số code point” không đủ để tính kích thước Modified UTF-8.

### Một bản ghi cụ thể

Nếu ghi chuỗi gồm **NUL**, `A` và emoji `😀`, Modified UTF-8 tạo payload:

```text
C0 80                NUL: 2 byte
41                   A:   1 byte
ED A0 BD ED B8 80    😀:  6 byte (hai surrogate UTF-16)
--------------------------------
Payload: 9 byte

Cả bản ghi:
00 09 C0 80 41 ED A0 BD ED B8 80
|---| |-------------------------|
  9      payload 9 byte
```

`readUTF()` của Java đọc bản ghi này và phục hồi đúng chuỗi ban đầu. Một bộ giải mã UTF-8 chuẩn có thể coi các byte biểu diễn NUL/surrogate đó là không hợp lệ.

## 4. Ví dụ số liệu ở các ranh giới quan trọng

Giả sử `repeat(n)` lặp chuỗi `n` lần, chỉ tính payload của một lệnh `writeUTF`:

| Nội dung | Byte Modified UTF-8 mỗi phần tử | Số lần lặp | Kích thước payload | Kết quả |
| --- | ---: | ---: | ---: | --- |
| `"A"` | 1 | 65.535 | 65.535 | Thành công |
| `"A"` | 1 | 65.536 | 65.536 | `UTFDataFormatException` |
| `"\u0000"` | 2 | 32.767 | 65.534 | Thành công |
| `"\u0000"` | 2 | 32.768 | 65.536 | `UTFDataFormatException` |
| `"中"` | 3 | 21.845 | 65.535 | Thành công |
| `"中"` | 3 | 21.846 | 65.538 | `UTFDataFormatException` |
| `"😀"` | 6 | 10.922 | 65.532 | Thành công |
| `"😀"` | 6 | 10.923 | 65.538 | `UTFDataFormatException` |

Riêng emoji: `"😀".length() == 2` vì là một cặp surrogate. Lặp 10.922 emoji tạo chuỗi `String` dài **21.844 `char`** nhưng payload Modified UTF-8 có **65.532 byte**. Lặp thêm một emoji chỉ tăng `String.length()` thêm 2, nhưng tăng payload thêm **6 byte** và vượt giới hạn.

Từ đó, **`s.length() <= 65535` là điều kiện cần nhưng chưa đủ** để gọi `writeUTF` thành công. Trong tập ký tự được biểu diễn bằng các đơn vị UTF-16, mỗi `char` cần tối đa 3 byte Modified UTF-8. Nếu `s.length() > 65535` thì chắc chắn quá giới hạn; còn dưới ngưỡng này vẫn cần tính kích thước đã mã hóa.

## 5. Java 17+: chương trình kiểm chứng thành công, thất bại và readUTF

Tạo file `WriteUtfLimitDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UTFDataFormatException;
import java.util.HexFormat;

public class WriteUtfLimitDemo {

    private static void probe(String label, String text)
            throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            try {
                out.writeUTF(text);

                byte[] record = buffer.toByteArray();
                int payloadLength = ((record[0] & 0xff) << 8)
                        | (record[1] & 0xff);

                try (DataInputStream in = new DataInputStream(
                        new ByteArrayInputStream(record))) {
                    String restored = in.readUTF();
                    System.out.println(label + ": payload="
                            + payloadLength + " total=" + record.length
                            + " equal=" + text.equals(restored));
                }
            } catch (UTFDataFormatException e) {
                System.out.println(label
                        + ": UTFDataFormatException written="
                        + buffer.size());
            }
        }
    }

    public static void main(String[] args) throws IOException {
        String nul = String.valueOf((char) 0);
        String cjk = "\u4E2D"; // 中
        String emoji = new String(Character.toChars(0x1F600));

        probe("ASCII max", "A".repeat(65535));
        probe("ASCII over", "A".repeat(65536));

        probe("NUL max", nul.repeat(32767));
        probe("NUL over", nul.repeat(32768));

        probe("CJK max", cjk.repeat(21845));
        probe("CJK over", cjk.repeat(21846));

        probe("Emoji max", emoji.repeat(10922));
        probe("Emoji over", emoji.repeat(10923));

        ByteArrayOutputStream tinyBuffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(tinyBuffer)) {
            out.writeUTF(nul + "A" + emoji);
        }
        String hex = HexFormat.ofDelimiter(" ").withUpperCase()
                .formatHex(tinyBuffer.toByteArray());
        System.out.println("Wire example: " + hex);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac WriteUtfLimitDemo.java
java WriteUtfLimitDemo
```

Stdout đã kiểm chứng trên JDK:

```text
ASCII max: payload=65535 total=65537 equal=true
ASCII over: UTFDataFormatException written=0
NUL max: payload=65534 total=65536 equal=true
NUL over: UTFDataFormatException written=0
CJK max: payload=65535 total=65537 equal=true
CJK over: UTFDataFormatException written=0
Emoji max: payload=65532 total=65534 equal=true
Emoji over: UTFDataFormatException written=0
Wire example: 00 09 C0 80 41 ED A0 BD ED B8 80
```

Giải thích kết quả:

- Trường `payload` là hai byte tiền tố mà chương trình ghép lại thành số không dấu. `total` là kích thước toàn bộ bản ghi trên `ByteArrayOutputStream`.
- Với chuỗi vừa ngưỡng, `readUTF()` phục hồi đúng chuỗi và `equals` là `true`.
- Với chuỗi quá ngưỡng, `UTFDataFormatException` xảy ra do payload vượt 65.535 byte; **trong ví dụ và triển khai JDK này**, `writeUTF` tính trước kích thước, nên `ByteArrayOutputStream` vẫn có 0 byte từ lần ghi thất bại. Đừng mở rộng kết luận này thành bảo đảm rằng mọi lỗi I/O trên mọi stream sẽ rollback dữ liệu đã ghi.
- `tinyBuffer` chứng minh cấu trúc dữ liệu thực tế, bao gồm tiền tố `00 09`, byte NUL dạng `C0 80` và emoji 6 byte.

Chương trình dùng `HexFormat` (Java 17), `String.repeat` (Java 11+) và `Character.toChars`. Nó không phụ thuộc khả năng hiển thị emoji của console: đầu ra là hex và giá trị boolean.

## 6. Tự tính số byte Modified UTF-8 trước khi ghi

Nếu muốn kiểm tra giới hạn trước khi tạo bản ghi, có thể tính dung lượng theo từng đơn vị `char`:

```java
static long modifiedUtf8Length(String s) {
    long length = 0;
    for (int i = 0; i < s.length(); i++) {
        char c = s.charAt(i);
        if (c >= 0x0001 && c <= 0x007f) {
            length += 1;
        } else if (c <= 0x07ff) {
            length += 2;
        } else {
            length += 3;
        }
    }
    return length;
}
```

Đây là **mảnh mã**, đặt trong một lớp Java; `s` phải khác `null`. Dùng `long` để tránh tràn số nếu ứng dụng xử lý các chuỗi cực dài. Thuật toán đi qua mỗi `char` một lần: `O(s.length())` về thời gian và `O(1)` bộ nhớ phụ.

Tại sao ba nhánh này đúng?

1. `c` trong `0x0001..0x007F` cần 1 byte.
2. `c == 0` hoặc `c` trong `0x0080..0x07FF` cần 2 byte.
3. Phần còn lại `0x0800..0xFFFF` cần 3 byte. Hai đơn vị surrogate của một code point ngoài BMP được cộng **hai lần × 3**.

Kiểm tra:

```java
long encodedLength = modifiedUtf8Length(s);
if (encodedLength > 65535) {
    throw new IllegalArgumentException(
            "writeUTF payload exceeds 65535 bytes: " + encodedLength);
}
out.writeUTF(s);
```

Đây là mảnh mã: `s` và `out` được chuẩn bị trước, và cần xử lý `IOException`. Việc tính trước hữu ích để đưa ra thông báo lỗi có ý nghĩa, lựa chọn encoding khác hoặc từ chối giá trị vượt ngưỡng trước khi bắt đầu một bản ghi lớn. Tuy nhiên, **`writeUTF` tự kiểm tra kích thước**; bạn không bắt buộc phải viết bộ đếm này chỉ để tránh ngoại lệ.

**Không dùng** `s.getBytes(StandardCharsets.UTF_8).length` làm kiểm tra tương đương cho `writeUTF`. UTF-8 chuẩn và Modified UTF-8 có số byte khác nhau ở NUL, surrogate và code point ngoài BMP.

### Không nên tự cắt chuỗi khi vượt ngưỡng

`s.substring(0, 65535)` chỉ cắt theo đơn vị `char`, không theo byte Modified UTF-8. Ngay cả khi đoạn mới có chiều dài ngắn hơn 65.535 `char`, nó vẫn có thể cần nhiều hơn 65.535 byte. Nếu cắt ở giữa cặp surrogate thì dữ liệu Unicode có thể bị chia sai. Cắt chuỗi để vừa format còn có thể làm mất dữ liệu quan trọng.

Khi cần lưu toàn bộ nội dung, chọn **định dạng bản ghi khác** thay vì cắt/truncate dữ liệu. Nếu giao thức bắt buộc `writeUTF`, có thể chia thành nhiều bản ghi **chỉ khi cả bên ghi và bên đọc được thiết kế trước để hiểu nhiều phần**, có thứ tự/độ dài/tổng số phần rõ ràng. Không tự chia thành nhiều `writeUTF` rồi kỳ vọng một `readUTF` sẽ ghép lại.

## 7. Cách xử lý UTFDataFormatException

Một ví dụ bắt ngoại lệ:

```java
try {
    out.writeUTF(value);
} catch (UTFDataFormatException e) {
    // value không thể nằm trong một bản ghi writeUTF.
    // Trả thông báo hợp lệ, chọn giao thức thay thế hoặc từ chối dữ liệu.
}
```

Đây là mảnh mã: `out` là `DataOutputStream` và `value` là `String`; cần import `java.io.UTFDataFormatException`.

Điểm cần lưu ý:

- `UTFDataFormatException` không có nghĩa là `String` đã vượt giới hạn bộ nhớ Java. Nó báo rằng dữ liệu không vừa **hợp đồng Modified UTF-8 với tiền tố 2 byte**.
- `IOException` khác có thể phát sinh do nguồn/đích đã đóng, đĩa đầy, mạng ngắt, v.v. Không gom mọi `IOException` thành lỗi độ dài.
- `UTFDataFormatException` cũng có thể xuất hiện **khi đọc** `DataInputStream.readUTF()` nếu phần dữ liệu không phải một chuỗi Modified UTF-8 hợp lệ. Khi đọc mà thiếu byte giữa bản ghi, có thể xảy ra `EOFException`.
- Với luồng nhị phân gồm nhiều trường, nếu một lần ghi gây lỗi giữa quá trình ghi do I/O, trạng thái đích có thể đã bị thay đổi. Không dựa vào cơ chế rollback mặc định của stream.
- Ứng dụng không nên bắt `UTFDataFormatException` rồi gọi lại `writeUTF` trên cùng giá trị không đổi hoặc cắt đại chuỗi để “thử cho qua”.
- Khi có ràng buộc kỹ thuật của định dạng được công khai với người dùng (ví dụ trường mô tả phải nằm trong một bản ghi `writeUTF`), nên xác thực khi nhận dữ liệu để trả thông báo chính xác sớm.

## 8. Phương án cho chuỗi dài hơn: length-prefix 4 byte + UTF-8 chuẩn

Nếu bạn **thiết kế giao thức nhị phân của riêng mình**, có thể thay `writeUTF` bằng định dạng:

```text
[int32 độ dài N, big-endian] [N byte UTF-8 chuẩn]
               4 byte          N byte
```

Ưu điểm: không phụ thuộc giới hạn 65.535 byte của `writeUTF` và dùng **UTF-8 chuẩn**, dễ tương tác hơn với nhiều hệ thống. Nhưng **định dạng này không tương thích `readUTF`**. Bên đọc phải dùng đúng `readInt`, `readFully` và giải mã charset đã thỏa thuận.

Ví dụ Java 17+ độc lập, lưu `LongTextFrameDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class LongTextFrameDemo {
    private static final int MAX_PAYLOAD = 1_000_000;

    static void writeText(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_PAYLOAD) {
            throw new IOException("Payload too large");
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String readText(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid payload length: " + length);
        }
        byte[] bytes = new byte[length];
        in.readFully(bytes);

        // Strict decoding: từ chối byte UTF-8 không hợp lệ.
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new IOException("Invalid UTF-8 payload", e);
        }
    }

    public static void main(String[] args) throws IOException {
        String text = "A".repeat(70_000);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            writeText(out, text);
        }

        byte[] record = buffer.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(record))) {
            String recovered = readText(in);
            System.out.println("Payload bytes: " + (record.length - 4));
            System.out.println("Record bytes: " + record.length);
            System.out.println("Round trip: " + text.equals(recovered));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac LongTextFrameDemo.java
java LongTextFrameDemo
```

Stdout dự kiến:

```text
Payload bytes: 70000
Record bytes: 70004
Round trip: true
```

Chi tiết quan trọng:

1. `getBytes(StandardCharsets.UTF_8)` mã hóa thành **UTF-8 chuẩn**. Byte NUL sẽ là `00` và emoji thường dùng 4 byte — khác Modified UTF-8.
2. `writeInt` tạo tiền tố 4 byte (big-endian) biểu diễn **số byte payload**, không phải `String.length()`.
3. `readInt` đọc kích thước, **kiểm tra không âm và giới hạn tối đa**, rồi `readFully` đọc đúng số byte; nếu thiếu byte, `readFully` ném `EOFException`.
4. Decoder với `REPORT` không chấp nhận chuỗi byte UTF-8 hỏng; ví dụ tránh âm thầm thay ký tự khi dữ liệu bắt buộc hợp lệ.
5. `MAX_PAYLOAD` là **giới hạn ứng dụng tự đặt**, giúp giảm rủi ro cấp phát bộ nhớ quá lớn từ độ dài trong bản tin không đáng tin. Không có nghĩa bộ đệm một triệu byte tự động an toàn trong mọi hệ thống.
6. Ví dụ gom dữ liệu vào byte[] vì kích thước nhỏ, có giới hạn. Nếu nội dung dài hàng trăm MB/GB, nên thiết kế streaming, chia chunk và kiểm soát kích thước thay vì tạo một mảng byte khổng lồ.

Nếu giao thức đã được xác định sẵn bởi một thư viện/protocol bên ngoài, bạn **không thể đơn phương đổi `writeUTF` thành `writeInt + write`** mà vẫn giữ tương thích. Phải cập nhật đồng thời bên đọc, bên ghi và tài liệu wire format.

## 9. `writeUTF` khác gì các phương thức ghi chuỗi khác?

| Cách ghi | Dạng dữ liệu được ghi | Tự có độ dài? | Giới hạn chính |
| --- | --- | --- | --- |
| `DataOutputStream.writeUTF(s)` | Modified UTF-8 | **Có: 2 byte** | Payload tối đa 65.535 byte |
| `DataOutputStream.writeChars(s)` | Mỗi `char` thành 2 byte, high byte trước | **Không** | Không có giới hạn 65.535 byte của `writeUTF`; bên đọc phải biết số ký tự |
| `DataOutputStream.writeBytes(s)` | Chỉ byte thấp của mỗi `char` | **Không** | Có thể mất dữ liệu Unicode |
| `out.write(s.getBytes(UTF_8))` | UTF-8 chuẩn | **Không** | Phải quản lý framing/độ dài |
| `out.writeInt(n); out.write(bytes)` | Do ứng dụng định nghĩa | **Có: 4 byte** | Theo kiểu số, bộ nhớ và giới hạn ứng dụng |
| `OutputStreamWriter(out, UTF_8)` | Ký tự → UTF-8 chuẩn | Không theo bản ghi `writeUTF` | Quản lý ranh giới văn bản/tài nguyên |

`writeBytes(String)` thường **không** phải lựa chọn đúng để ghi Unicode vì chỉ dùng byte thấp của từng `char`. `writeChars(String)` giữ mỗi đơn vị `char` ở hai byte, nhưng không cung cấp tiền tố độ dài; bên đọc cần hợp đồng riêng, ví dụ `readChar()` lặp đúng số lần. Không nên coi các phương thức này là cách “bỏ giới hạn nhưng giữ nguyên kết quả của `writeUTF`”.

Với file trao đổi text (UTF-8), có thể dùng `Files.writeString(path, text, UTF_8)` hoặc `BufferedWriter` thay vì tự thiết kế bản ghi nhị phân. Với giao thức nhị phân cần đọc bằng `DataInputStream`, chọn wire format rõ ràng và có framing.

## 10. Những câu hỏi thực tế về giới hạn

### 10.1. `"A".repeat(65535)` có hợp lệ không?

Có, vì mỗi ký tự `A` là 1 byte Modified UTF-8, payload đúng 65.535 byte, và hai byte tiền tố là `FF FF`. Tổng số byte bản ghi là 65.537.

### 10.2. `"A".repeat(65536)` có được Java tự cắt còn 65.535 byte không?

Không. `writeUTF` **ném `UTFDataFormatException`**. Nó không tự cắt, không tự tạo hai bản ghi và không ghi số dài hơn 65.535 vào trường length 2 byte.

### 10.3. `String.length() == 30000` có chắc ghi được không?

Không. Nếu toàn các `char` mã hóa 3 byte, payload = 90.000 byte, vượt giới hạn. Nếu toàn ASCII khác NUL, payload = 30.000 byte, hợp lệ.

### 10.4. Nếu chuỗi có tiếng Việt thì sao?

Một số chữ Việt trong UTF-16 nằm trong khoảng `U+0080..U+07FF` nên thường cần **2 byte**; một số dấu tổ hợp hoặc ký tự khác có thể cần **2–3 byte** tùy đơn vị `char`. Không suy ra chiều dài byte chỉ từ số chữ hiển thị. Đếm theo từng `char` hoặc để `writeUTF` kiểm tra.

### 10.5. Emoji có phải 4 byte như UTF-8 thông thường không?

Không trong `writeUTF`. Một emoji như `😀` có hai đơn vị surrogate UTF-16 và thường cần **6 byte** Modified UTF-8. Nhưng khi dùng `StandardCharsets.UTF_8` để mã hóa văn bản chuẩn, code point này cần 4 byte.

### 10.6. Tiền tố `FF FF` là một số âm nếu đọc bằng `readShort()`?

Có thể được diễn giải thành `-1` nếu dùng `readShort()`, vì `short` là kiểu có dấu. `DataInputStream.readUTF()` hiểu tiền tố đúng định dạng, tương đương việc đọc một **unsigned short**. Nếu cần kiểm tra length thủ công, dùng `readUnsignedShort()` và không lẫn `readShort()`.

### 10.7. `readUTF` có đọc được byte do `writeInt + UTF-8` tạo ra không?

Không. `readUTF` chờ đúng **2 byte length + Modified UTF-8**, còn định dạng tùy biến ở phần trên là **4 byte length + UTF-8 chuẩn**. Dù một chuỗi ASCII ngắn có thể trông giống nhau ở phần payload, khung bản ghi vẫn khác và decoder có thể đọc lệch.

### 10.8. Có thể dùng `writeUTF` để ghi JSON lớn hoặc văn bản HTML dài không?

Chỉ nếu toàn bộ nội dung mã hóa Modified UTF-8 không vượt 65.535 byte **và** đầu đọc hiểu đúng định dạng. Với JSON/HTTP/text thông thường, thường nên dùng UTF-8 chuẩn và framing theo giao thức thay vì phụ thuộc `writeUTF`.

## 11. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng `s.length() <= 65535` làm điều kiện đủ | Chuỗi nhiều Unicode vẫn vượt ngưỡng | Tính byte Modified UTF-8 |
| Tính `s.getBytes(UTF_8).length` làm kích thước `writeUTF` | Sai với NUL/emoji | Tính theo từng `char` và Modified UTF-8 |
| Trừ 2 từ 65.535 vì tiền tố | Hiểu sai ngưỡng tối đa | 65.535 chỉ là payload; tổng tối đa 65.537 |
| Coi `writeUTF` như `write` UTF-8 thường | Bên đọc sai byte, lỗi charset/framing | Ghép với `readUTF` |
| Dùng `new String(payload, UTF_8)` đọc Modified UTF-8 | NUL và surrogate có thể bị giải mã sai | `DataInputStream.readUTF()` |
| Cho rằng quá giới hạn sẽ bị cắt | Không có bản ghi hợp lệ | Bắt `UTFDataFormatException` và xử lý rõ ràng |
| Gọi `writeUTF` nhiều lần và chỉ gọi `readUTF` một lần | Chỉ đọc được một bản ghi | Thiết kế số lượng/chuỗi các bản ghi |
| Chia `String` tùy tiện ở 65.535 ký tự | Có thể cắt đôi surrogate hoặc vẫn quá dung lượng | Tính bytes và xác định chunk hợp lệ |
| Đổi một đầu sang `writeInt + UTF_8`, đầu kia vẫn `readUTF` | Hỏng giao thức | Nâng cấp đồng bộ wire format |
| Nhận length 4 byte từ nguồn ngoài rồi cấp phát ngay | Có nguy cơ cấp phát bộ nhớ quá lớn | Kiểm tra nonnegative/max trước `new byte[length]` |
| Nhầm `EOFException` khi đọc với `UTFDataFormatException` | Chẩn đoán sai lỗi bản ghi | EOF = thiếu byte; format = Modified UTF-8 không hợp lệ |
| Dùng `writeBytes` để giữ Unicode | Mất phần byte cao của `char` | Dùng UTF-8/encoding thích hợp |
| Giả định mọi lỗi I/O rollback stream | Bản ghi có thể bị ghi dở | Thiết kế transaction/framing/khôi phục ở tầng ứng dụng |

## 12. Bài tập tự kiểm tra

1. **Giới hạn của `writeUTF` là số nào?** 65.535 **byte Modified UTF-8 của payload**, không tính 2 byte tiền tố.
2. **Một chuỗi gồm 65.535 chữ `A` có ghi được không?** Có; payload 65.535 byte, tổng bản ghi 65.537 byte.
3. **Một chuỗi gồm 32.768 ký tự NUL có ghi được không?** Không; cần 65.536 byte Modified UTF-8.
4. **Vì sao `"😀".repeat(10923)` thất bại?** Mỗi emoji dùng 6 byte Modified UTF-8, tổng 65.538 byte.
5. **Tiền tố `FF FF` nghĩa gì?** Payload có chiều dài 65.535 byte không dấu; không phải `-1`.
6. **Phương thức nào đọc tương thích bản ghi `writeUTF`?** `DataInputStream.readUTF()` (hoặc API `DataInput.readUTF` tương thích).
7. **`StandardCharsets.UTF_8` có phải charset của `writeUTF` không?** Không; `writeUTF` dùng Modified UTF-8 theo hợp đồng `DataOutput`.
8. **Nếu chuỗi quá dài nhưng phải giữ đủ dữ liệu thì sao?** Thiết kế định dạng có độ dài lớn hơn (ví dụ tiền tố `int` và UTF-8 chuẩn), hoặc chia bản ghi có framing thỏa thuận hai đầu.
9. **`UTFDataFormatException` chỉ xuất hiện lúc ghi quá dài?** Không; đọc nội dung Modified UTF-8 sai định dạng cũng có thể phát sinh ngoại lệ này.
10. **Có thể dùng `getBytes(UTF_8).length` để kiểm tra giới hạn Modified UTF-8 không?** Không, vì NUL, surrogate và emoji có kích thước khác nhau.

## Tài liệu Java 17 chính thức

- [`DataOutput.writeUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html#writeUTF(java.lang.String)).
- [`DataOutputStream.writeUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html#writeUTF(java.lang.String)).
- [`DataInput.readUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html#readUTF()).
- [`DataInputStream.readUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html#readUTF()).
- [`UTFDataFormatException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html).
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).

**Kết luận thực hành:** Dùng `writeUTF` khi dữ liệu cần khớp giao thức nhị phân Java với `readUTF` và **payload Modified UTF-8 không quá 65.535 byte**. Muốn ghi văn bản dài hơn hoặc trao đổi với hệ thống dùng UTF-8 chuẩn, hãy chọn một định dạng có length-prefix/framing phù hợp và xác thực độ dài khi đọc.
