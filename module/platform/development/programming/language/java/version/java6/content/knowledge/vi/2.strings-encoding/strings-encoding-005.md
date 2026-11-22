# Biên giới giữa byte, ký tự và dữ liệu văn bản

Một tệp hoặc gói tin mang các byte. Ứng dụng muốn đọc văn bản thì phải diễn giải các byte đó theo một quy tắc mã hóa. Khi đã có `String`, ta lại làm việc với đơn vị mã và điểm mã, không phải trực tiếp với số byte trên đường truyền.

Nhận ra ranh giới này giúp tránh chữ tiếng Việt bị sai, cắt hỏng emoji và mất dữ liệu khi chuyển nội dung nhị phân thành chuỗi.

## 1. Ba tầng cần phân biệt

```text
byte[] ở tệp/đường truyền
        |
        | giải mã theo charset
        v
String: chuỗi đơn vị mã UTF-16
        |
        | diễn giải điểm mã và văn bản
        v
nội dung mà chương trình/người dùng sử dụng
```

Chiều ngược lại là mã hóa: `String` được chuyển thành byte theo charset đã chọn.

| Tầng | Đơn vị thường gặp | Câu hỏi phù hợp |
| --- | --- | --- |
| Dữ liệu nhị phân | Byte | Đã nhận đủ bao nhiêu byte? |
| Chuỗi Java | Đơn vị mã UTF-16, điểm mã Unicode | Chỉ số String đang trỏ tới đâu? |
| Văn bản hiển thị | Cụm ký tự mà người dùng cảm nhận | Người dùng nhìn thấy bao nhiêu ký tự? |

Một byte có 8 bit. Kiểu `byte` của Java có dấu, nhưng khi xem dữ liệu mã hóa thường biểu diễn theo hex để nhìn rõ từng mẫu 8 bit. Giá trị âm khi in một phần tử `byte[]` không có nghĩa dữ liệu mã hóa bị lỗi.

`char` của Java là một đơn vị mã UTF-16, không luôn tương ứng trọn một ký tự Unicode. Một điểm mã ngoài vùng BMP, chẳng hạn emoji trong ví dụ, cần một cặp surrogate gồm hai `char`.

Xem [biểu diễn String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html) và [khái niệm Charset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html).

## 2. Đừng gắn một số “độ dài” cho mọi tầng

Xét chuỗi gồm ba điểm mã:

```text
A
ế  (U+1EBF)
😀 (U+1F600)
```

Với cách biểu diễn đúng các điểm mã đó:

| Phép đo | Kết quả |
| --- | --- |
| Số đơn vị mã UTF-16 của String | `4` |
| Số điểm mã Unicode | `3` |
| Số byte khi mã hóa UTF-8 | `8` |

Phân tích UTF-8:

```text
A    -> 41
ế    -> e1 ba bf
😀   -> f0 9f 98 80
```

Vì thế:

```java
text.length()
```

không phải số byte mà `text.getBytes(StandardCharsets.UTF_8)` tạo ra.

Ngay cả số điểm mã cũng không luôn bằng số ký tự người dùng cảm nhận. Một chữ có dấu có thể được biểu diễn bằng một điểm mã dựng sẵn hoặc một chữ nền đi cùng dấu kết hợp. Đây là tầng xử lý văn bản cao hơn; không nên dùng `length()` để áp đặt mọi giới hạn giao diện mà chưa xác định đơn vị.

Các mô tả UTF-16 ở đây là hợp đồng nhìn từ API, không phải một khẳng định rằng mọi JDK phải lưu mọi String bằng cùng bố trí mảng nội bộ.

## 3. Charset nằm ở ranh giới chuyển đổi

Hai thao tác có hướng khác nhau:

```java
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(encoded, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa khi đã có `text`; chương trình đầy đủ ở phần sau.

- `getBytes` mã hóa chuỗi thành byte.
- Constructor `String(byte[], Charset)` giải mã byte thành chuỗi.
- Tên charset phải phù hợp với hợp đồng của nơi ghi/gửi dữ liệu.

Một `byte[]` không tự mang nhãn “đây là UTF-8”. Hợp đồng có thể nằm trong định dạng tệp, giao thức hoặc cấu hình. Không mặc định suy ra charset chỉ từ đuôi tệp hay từ việc một lần giải mã có ném ngoại lệ hay không.

Sau khi đã thành `String`, nội dung không có một thuộc tính “charset gốc” mà bạn lấy ra để khôi phục mọi bước đã xảy ra. Charset sẽ lại cần được chọn khi ghi chuỗi ra một biểu diễn byte mới.

## 4. Ví dụ hoàn chỉnh: đo và kiểm tra từng ranh giới

Tạo tệp `TextBoundaryDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public class TextBoundaryDemo {
    public static void main(String[] args) throws Exception {
        String text = "A\u1EBF\uD83D\uDE00";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf16.units=" + text.length());
        System.out.println("code.points=" + text.codePointCount(0, text.length()));
        System.out.println("utf8.bytes=" + utf8.length);
        System.out.println("utf8.hex=" + HexFormat.ofDelimiter(" ").formatHex(utf8));
        String decoded = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("decoded.points=" + points(decoded));
        System.out.println("roundtrip=" + text.equals(decoded));

        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("wrong.length=" + wrong.length());
        System.out.println("wrong.points=" + points(wrong));

        byte[] malformed = {(byte) 0xC3, 0x28};
        System.out.println("replacement.points="
                + points(new String(malformed, StandardCharsets.UTF_8)));
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
        } catch (CharacterCodingException e) {
            System.out.println("strict=" + e.getClass().getSimpleName());
        }

        StringBuilder result = new StringBuilder();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8), StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                result.append(buffer, 0, count);
            }
        }
        System.out.println("reader.roundtrip=" + text.contentEquals(result));
    }

    private static String points(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }
}
```

Mã dùng các escape Unicode để nguồn ví dụ không phụ thuộc việc nhập trực tiếp emoji. Phần in điểm mã và hex cũng dùng ký tự ASCII, nên dễ đối chiếu ngay cả khi terminal chưa hiển thị đúng tiếng Việt.

Các API phụ trợ của ví dụ như `HexFormat` thuộc JDK hiện đại; bài này thực hành khái niệm trên JDK 17+ chứ không gán toàn bộ mã thành cú pháp/API Java 6.

### Biên dịch và chạy

Lưu tệp UTF-8 không BOM. Mở terminal tại thư mục chứa mã, có `javac` và `java` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out TextBoundaryDemo.java
java -cp out TextBoundaryDemo
```

Stdout đã kiểm chứng trên Microsoft OpenJDK 21.0.9:

```text
utf16.units=4
code.points=3
utf8.bytes=8
utf8.hex=41 e1 ba bf f0 9f 98 80
decoded.points=U+0041 U+1EBF U+1F600
roundtrip=true
wrong.length=8
wrong.points=U+0041 U+00E1 U+00BA U+00BF U+00F0 U+009F U+0098 U+0080
replacement.points=U+FFFD U+0028
strict=MalformedInputException
reader.roundtrip=true
```

## 5. Đọc ba kiểu kết quả giải mã

### 5.1. Đúng charset, đúng byte

`roundtrip=true` cho thấy chuỗi mẫu được mã hóa UTF-8 rồi giải mã đúng UTF-8 trở lại bằng nội dung ban đầu.

Đây là bằng chứng với đầu vào hợp lệ của ví dụ, không phải định luật rằng mọi phép chuyển String → byte → String đều không mất thông tin. Charset đích có thể không biểu diễn được nội dung, hoặc String có thể chứa đơn vị surrogate không hợp lệ.

### 5.2. Sai charset nhưng vẫn tạo được String

`wrong.length=8` và danh sách `wrong.points` chứng minh cùng tám byte đã bị diễn giải thành nội dung khác khi chọn ISO-8859-1.

Lượt này không ném lỗi. Việc giải mã thành công về mặt kỹ thuật không chứng minh ta chọn đúng charset. Một bảng ánh xạ có thể nhận các byte đó hợp lệ nhưng tạo ra văn bản không đúng ý người gửi.

Nếu văn bản hiển thị sai, hãy kiểm tra tại ranh giới đầu tiên byte thành chuỗi. Đừng tùy ý đổi qua nhiều charset liên tiếp mà chưa xác định bước nào sai và byte gốc còn được giữ hay không.

### 5.3. Byte không hợp lệ với charset đã chọn

Dãy `c3 28` không phải một chuỗi UTF-8 hợp lệ: byte đầu yêu cầu phần tiếp nối nhưng byte sau không đáp ứng.

Constructor `String(byte[], Charset)` thay đầu vào lỗi bằng ký tự thay thế. Trong stdout:

```text
U+FFFD U+0028
```

U+FFFD là REPLACEMENT CHARACTER, còn U+0028 là dấu mở ngoặc.

Khi cần phát hiện dữ liệu lỗi, dùng `CharsetDecoder` với hành động `REPORT`. Ví dụ nhận `MalformedInputException`, thay vì âm thầm đưa ký tự thay thế vào dữ liệu. Xem [CharsetDecoder và chính sách xử lý lỗi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html).

Hai loại vấn đề cần phân biệt: byte không hợp lệ theo charset, và byte hợp lệ nhưng charset được chọn sai với hợp đồng. Chế độ nghiêm ngặt phát hiện loại thứ nhất; không tự chứng minh được ý nghĩa văn bản của loại thứ hai.

## 6. Biên giới đọc luồng không phải biên giới ký tự

Một ký tự UTF-8 có thể gồm nhiều byte. Mỗi lần đọc từ tệp hoặc mạng có thể kết thúc giữa dãy byte của cùng một điểm mã.

Cách dễ gây lỗi:

```text
đọc khối byte thứ nhất -> new String(khối 1, UTF_8)
đọc khối byte thứ hai  -> new String(khối 2, UTF_8)
nối hai chuỗi
```

Nếu điểm cắt nằm giữa dãy UTF-8, mỗi lần giải mã độc lập có thể coi phần còn thiếu là lỗi. Nối chuỗi sau đó không tự khôi phục byte đã bị thay thế.

`InputStreamReader` trong chương trình là cầu nối có bộ giải mã giữa luồng byte và luồng ký tự. Nó duy trì quá trình giải mã qua các lượt đọc. Xem [InputStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html).

Bộ đệm `char[2]` của ví dụ không cam kết mỗi lượt đọc ứng với một từ, dòng, điểm mã hay cụm ký tự hoàn chỉnh. Vòng lặp ghép đúng số đơn vị đã nhận để giữ nguyên chuỗi. Nếu cần xử lý từng điểm mã hoặc từng dòng, phải chọn bước xử lý tương ứng sau ranh giới giải mã.

Khi tự dùng `CharsetDecoder` cho nhiều `ByteBuffer`, cần giữ byte chưa xử lý và thực hiện đúng vòng đời decode/end-of-input/flush. Không biến mỗi buffer thành một tài liệu riêng nếu chúng chỉ là các phần của cùng luồng.

## 7. Văn bản còn có cấu trúc ở trên lớp mã hóa

Sau khi giải mã đúng, ta mới có thể diễn giải văn bản theo định dạng:

```text
byte HTTP/tệp
    -> giải mã
    -> String/ký tự
    -> phân tích JSON, CSV hoặc định dạng khác
    -> dữ liệu nghiệp vụ
```

Charset trả lời “các byte biểu diễn ký tự nào?”. Bộ phân tích định dạng trả lời “các ký tự này tạo thành trường và giá trị gì?”. Một tài liệu có thể là UTF-8 hợp lệ nhưng JSON sai cú pháp; một tài liệu JSON hợp lệ cũng có thể chứa giá trị nghiệp vụ không hợp lệ.

Tương tự, escape trong JSON và mã hóa UTF-8 là hai tầng khác nhau. Đừng sửa lỗi giải mã bằng cách tùy ý thay dấu gạch chéo hoặc escape của định dạng.

## 8. Dữ liệu nhị phân không tự trở thành văn bản

Ảnh, ZIP, dữ liệu nén và giá trị băm có thể là các dãy byte tùy ý. Gọi `new String(bytes, UTF_8)` lên chúng không tạo ra một cách lưu trữ khôi phục được bảo đảm.

Khi cần chuyển dữ liệu nhị phân qua một kênh văn bản, dùng một biểu diễn được thiết kế cho việc đó, chẳng hạn hex hoặc Base64, rồi giải ngược theo đúng quy ước. Base64 là cách biểu diễn dữ liệu, không phải mã hóa bảo mật.

Hex trong chương trình giúp ta nhìn chính xác byte UTF-8; nó không thay đổi charset của nội dung gốc.

## 9. Áp dụng tại ranh giới nhập/xuất

| Tình huống | Quy tắc cần chốt |
| --- | --- |
| Đọc tệp văn bản | Charset của tệp và chính sách khi byte lỗi |
| Gửi văn bản thành byte | Charset ghi và khả năng biểu diễn nội dung |
| Giới hạn kích thước gói tin | Đếm byte sau khi mã hóa, không dùng String.length |
| Cắt chuỗi theo chỉ số | Biết chỉ số là đơn vị UTF-16; tránh cắt giữa surrogate |
| Xử lý khối dữ liệu mạng | Giữ trạng thái giải mã qua ranh giới khối |
| Lưu byte nhị phân trong trường văn bản | Dùng biểu diễn nhị phân–văn bản phù hợp |

Với API có overload không truyền charset, hãy đọc hợp đồng nó chọn mặc định nào. Ở ranh giới dữ liệu có quy ước rõ, truyền charset tường minh giúp người đọc thấy ngay hợp đồng và dễ tái lập kết quả.

Charset của tệp nguồn, charset của dữ liệu ứng dụng và cách terminal hiển thị stdout là ba cấu hình có thể khác nhau. Một lỗi hiển thị chưa đủ kết luận String trong bộ nhớ đã sai; in điểm mã/hex như ví dụ giúp khoanh vùng.

## 10. Tự kiểm tra

1. Vì sao chuỗi mẫu có `length()=4` nhưng UTF-8 lại có `8` byte?
2. Vì sao giải mã ISO-8859-1 không ném lỗi nhưng vẫn sai nội dung?
3. U+FFFD trong ví dụ đến từ đâu, và vì sao cần giữ byte gốc khi điều tra?
4. Vì sao không nên giải mã độc lập mỗi khối byte đọc từ mạng?
5. Một giới hạn “100 ký tự” cần làm rõ điều gì trước khi triển khai?

Tại mỗi bước, hãy gọi đúng đơn vị và đúng phép chuyển: **byte được giải mã thành ký tự; ký tự được phân tích thành dữ liệu văn bản; văn bản được mã hóa thành byte khi xuất ra ngoài**.
