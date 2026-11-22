# Kiểm thử dữ liệu cắt cụt, dữ liệu hỏng và đầu ra lớn khi nén/giải nén (Java 11+)

## 1. Vì sao phải kiểm thử ba nhóm tình huống này?

Khi làm việc với **buffer và nén** trong Java, một luồng nén có thể đến từ tệp, mạng, upload của người dùng hoặc bộ nhớ. Đầu vào không phải lúc nào cũng đầy đủ, hợp lệ hay có kích thước giải nén nhỏ như người viết chương trình dự đoán.

Ba nhóm lỗi cần kiểm tra riêng:

1. **Dữ liệu cắt cụt (*truncated*)**: các byte cuối bị mất, luồng bị ngắt giữa chừng, thiếu payload hoặc thiếu phần kiểm tra tính toàn vẹn. Một phần dữ liệu đầu ra có thể đã được đọc trước khi lỗi xuất hiện.
2. **Dữ liệu hỏng (*corrupt*)**: header sai định dạng, bit trong payload bị thay đổi, checksum/trailer sai hoặc dữ liệu không tuân thủ định dạng nén.
3. **Đầu ra quá lớn (*oversized decompressed output*)**: dữ liệu nén ban đầu rất nhỏ nhưng giải nén thành nhiều MB/GB. Nếu đọc hết vào bộ nhớ hoặc ghi không kiểm soát, chương trình có thể hết RAM, hết đĩa hoặc bị tấn công *decompression bomb*.

**Mục tiêu kiểm thử** không chỉ là “chương trình có ném exception hay không”, mà còn là:

- Dữ liệu hợp lệ được giải nén chính xác, kể cả nội dung rỗng.
- Đầu vào cắt cụt/hỏng được từ chối ở vị trí phù hợp, không bị coi là thành công.
- Kích thước **sau giải nén** được kiểm soát trong lúc đọc từng khối, trước khi chấp nhận hoặc lưu thêm dữ liệu vượt ngưỡng.
- Tài nguyên I/O được đóng dù kiểm thử thất bại.
- Phần dữ liệu giải nén chưa xác thực hoàn toàn không bị công bố như một kết quả hợp lệ.
- Kiểm thử có thể lặp lại, không phụ thuộc thông báo lỗi riêng của một bản JDK.

Bài học dùng **`GZIPInputStream`/`GZIPOutputStream`** và **`byte[]`** làm ví dụ Java 11+. Đây là API hiện hành của `java.util.zip`, phù hợp để học kiểm thử một luồng GZIP. Với ZIP nhiều entry, cần thêm các kiểm tra riêng được nêu ở phần cuối.

## 2. Hiểu đường đi dữ liệu và vị trí xảy ra lỗi

Dòng chảy đơn giản:

```text
Byte nguồn đã nén (tệp/mạng/byte[])
    |
    v
GZIPInputStream -- đọc/giải nén theo từng khối --> byte[] buffer cố định
    |                                               |
    |                                               v
    |                                    Cộng dồn số byte giải nén
    |                                               |
    |                                  Kiểm tra ngưỡng trước khi ghi
    |                                               |
    v                                               v
Kiểm tra cấu trúc, checksum                 OutputStream đích hợp lệ
và trạng thái kết thúc
```

Các điểm mấu chốt:

- **`GZIPInputStream` giải nén dữ liệu byte**. Nó không tự áp dụng giới hạn tổng số byte đầu ra do ứng dụng lựa chọn; ứng dụng phải đếm.
- Một `buffer` chỉ giới hạn kích thước **một khối đọc**, không giới hạn tổng đầu ra. Buffer `8192` byte có thể được dùng liên tục hàng triệu lần.
- Với GZIP, luồng chứa header, phần dữ liệu nén DEFLATE và phần cuối có thông tin kiểm tra (CRC32 của dữ liệu giải nén và kích thước modulo \(2^{32}\)). Giải nén cần tiến đến cuối luồng để phát hiện các lỗi chỉ lộ ra khi kiểm tra đoạn cuối.
- **CRC32 là kiểm tra lỗi vô tình, không phải xác thực mật mã**. Người có thể chủ động thay đổi nội dung có thể tạo luồng có CRC mới hợp lệ; muốn bảo vệ tính xác thực cần cơ chế như chữ ký số/MAC hoặc giao thức bảo mật phù hợp.
- Đọc một vài byte đầu thành công **không đồng nghĩa** toàn bộ dữ liệu nén hợp lệ.

Trong các lệnh minh họa, ta dùng `try-with-resources` để đóng cả nguồn giải nén và buffer đích. Khi lỗi xuất hiện, Java vẫn thực hiện cơ chế đóng các tài nguyên đã mở.

## 3. Thiết kế ma trận kiểm thử

| Ca kiểm thử | Cách tạo đầu vào | Kỳ vọng cần kiểm tra |
| --- | --- | --- |
| Dữ liệu hợp lệ | Nén một `byte[]` đã biết bằng `GZIPOutputStream` và đóng luồng nén đầy đủ. | Giải nén xong, so sánh toàn bộ byte với bản gốc. |
| Dữ liệu rỗng hợp lệ | Nén `new byte[0]` thành **một GZIP hợp lệ**. | Giải nén ra `byte[0]`, **không** coi đó là lỗi. |
| Chạm đúng giới hạn | `maxOutputBytes == original.length`. | Thành công, không có lỗi vượt ngưỡng. |
| Vượt giới hạn 1 byte | `maxOutputBytes == original.length - 1`. | Bị chặn bởi cơ chế giới hạn kích thước của ứng dụng. |
| Cắt giữa luồng | Giữ một nửa mảng byte của luồng GZIP. | Bị từ chối; không trả về kết quả hợp lệ. |
| Thiếu trailer | Bỏ vài byte cuối của luồng GZIP. | Bị từ chối khi giải nén/kiểm tra kết thúc. |
| Hỏng header | Sửa một byte chữ ký GZIP. | Bị từ chối như đầu vào sai định dạng. |
| Hỏng checksum | Sửa byte của CRC32 trong phần trailer. | Bị từ chối khi đọc đến vùng kiểm tra tính toàn vẹn. |
| Dữ liệu nén nhỏ, đầu ra lớn | Nén một mảng lớn chứa nhiều ký tự lặp. | Phần giải nén vượt ngưỡng bị chặn dù byte nén rất ít. |

**Không nhầm hai tình huống rỗng:**

- `compress(new byte[0])` tạo một luồng GZIP **hợp lệ có cấu trúc**, giải nén ra 0 byte.
- `new byte[0]` đưa thẳng vào `GZIPInputStream` **không phải một luồng GZIP hoàn chỉnh**. Đây là đầu vào thiếu header và có thể bị từ chối ngay khi khởi tạo.

**Phân biệt cơ chế phát hiện:** đầu vào cắt cụt/hỏng thường tạo ra `IOException` (một số trường hợp là `EOFException` hoặc `ZipException`); còn kiểm tra kích thước của bài học sẽ **chủ động ném `IOException` với lý do của ứng dụng**. Không nên viết test đòi hỏi tất cả tình huống đều phát ra cùng một subtype hoặc nguyên văn thông báo của JDK.

## 4. Viết hàm giải nén có giới hạn đầu ra

Hàm dưới đây sẽ được dùng trong chương trình hoàn chỉnh:

```java
private static byte[] decompressLimited(byte[] compressed, long maxOutputBytes)
        throws IOException {
    if (maxOutputBytes < 0) {
        throw new IllegalArgumentException("Negative size limit");
    }
    try (GZIPInputStream input = new GZIPInputStream(
                new ByteArrayInputStream(compressed), 8192);
         ByteArrayOutputStream output = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[8192];
        long total = 0;
        int n;
        while ((n = input.read(buffer)) != -1) {
            if (n > maxOutputBytes - total) {
                throw new IOException("Uncompressed size limit exceeded");
            }
            output.write(buffer, 0, n);
            total += n;
        }
        return output.toByteArray();
    }
}
```

Đây là **phương thức minh họa bên trong lớp**, yêu cầu các import tương ứng. Phần chương trình ở mục 6 có tất cả import, lớp và `main` để chạy độc lập.

Giải thích các quyết định:

1. **Đọc lặp đến `-1`:** đọc toàn bộ phần được cung cấp và đến kết thúc hợp lệ để thư viện có cơ hội kiểm tra trailer/checksum. Không trả về dữ liệu chỉ vì đã đọc được một khối.
2. **Buffer cố định `8192` byte:** việc xử lý chia khối giúp không cần cấp phát buffer bằng toàn bộ kích thước nội dung chưa biết.
3. **`long total`:** giảm nguy cơ tràn bộ đếm khi đo lượng byte tích lũy; trong mẫu có thể giới hạn nhỏ nhưng cách đếm phù hợp để mở rộng.
4. **`n > maxOutputBytes - total`:** so sánh **trước** `output.write(...)`; tránh cộng `total + n` rồi mới kiểm tra, vốn có thể tràn số nếu đặt giới hạn rất lớn. Với `maxOutputBytes >= 0` và `total <= maxOutputBytes`, phép trừ an toàn.
5. **Cho phép đúng ngưỡng:** `n == maxOutputBytes - total` vẫn hợp lệ. Một byte tiếp theo sẽ bị từ chối.
6. **`ByteArrayOutputStream` chỉ dùng cho bài test quy mô kiểm soát:** nếu giải nén tệp rất lớn hoặc dữ liệu không tin cậy trong production, nên stream sang đích có giới hạn thay vì giữ toàn bộ byte trong RAM.
7. **`try-with-resources`:** nguồn nén được đóng ngay cả khi sai định dạng hoặc vượt ngưỡng.

Điều cần nhớ: giới hạn này kiểm soát **tổng byte giải nén được chấp nhận vào đích**, không đảm bảo toàn bộ quá trình dùng đúng `maxOutputBytes` RAM. Input `byte[]`, buffer, trạng thái của bộ giải nén và `ByteArrayOutputStream` đều có bộ nhớ riêng; sản xuất thực tế cần áp dụng thêm giới hạn bộ nhớ/đầu vào.

## 5. Tạo dữ liệu lỗi một cách có kiểm soát

Không nên kiểm thử bằng tệp “bị hỏng ngẫu nhiên” mà không biết hỏng chỗ nào. Hãy tạo một luồng GZIP hợp lệ trước, sau đó **biến đổi đúng một đặc điểm**:

### 5.1. Cắt cụt dữ liệu

```java
byte[] cutMiddle = Arrays.copyOf(valid, valid.length / 2);
byte[] cutTrailer = Arrays.copyOf(valid, valid.length - 4);
```

Các đoạn này là **mảnh mã minh họa** sau khi đã có `valid`; chương trình đầy đủ nằm ở mục 6. Cắt giữa luồng giúp kiểm tra thiếu dữ liệu nén. Cắt phần đuôi kiểm tra lỗi khi không đủ trailer. Hai ca có thể được phát hiện ở **giai đoạn khác nhau**: lúc đọc DEFLATE hoặc lúc kiểm tra phần cuối.

Không chỉ cắt 1 byte ở một vị trí và kết luận mọi trường hợp cắt cụt đều được xử lý đúng. Những mức cắt phù hợp khác gồm: không có header, chỉ có header, cắt giữa payload, thiếu 1–8 byte cuối và luồng đến hết ngay sau một block.

### 5.2. Sửa header và CRC một cách xác định

```java
byte[] wrongHeader = valid.clone();
wrongHeader[0] ^= 1; // Thay đổi byte đầu của chữ ký GZIP.

byte[] wrongCrc = valid.clone();
wrongCrc[valid.length - 8] ^= 1; // Byte đầu CRC32 ở trailer GZIP.
```

Đây là hai cách tạo lỗi độc lập và lặp lại được. Với **luồng GZIP do `GZIPOutputStream` tạo ra và đã đóng đầy đủ**, trailer 8 byte cuối gồm CRC32 (4 byte) và ISIZE (4 byte). Sửa một bit CRC sẽ khiến quá trình kiểm tra tính toàn vẹn bị lỗi khi đọc đủ luồng.

Chú ý: việc sửa một byte bất kỳ ở giữa dữ liệu DEFLATE **không nhất thiết** tạo lỗi tại cùng một vị trí hoặc cùng một exception. Một thay đổi có thể làm giải nén thất bại ngay, hoặc chỉ gây sai checksum về cuối. Trong test, xác định trước vị trí thay đổi và **không cố khớp chính xác lỗi dạng chuỗi** do thư viện trả về.

### 5.3. Tạo đầu ra lớn từ input nén nhỏ

```java
byte[] repeated = new byte[2_000_000];
Arrays.fill(repeated, (byte) 'A');
byte[] compressedLarge = compress(repeated);
```

Các byte lặp nén tốt, nên `compressedLarge` thường nhỏ hơn `repeated` rất nhiều. Nhưng giải nén vẫn tạo **2.000.000 byte**. Nếu giới hạn là **1.000.000 byte**, việc giải nén phải bị chặn.

Đây là dữ liệu test **có giới hạn và không nguy hiểm**. Không tạo khối nén cực lớn hoặc vô hạn để chứng minh một quy tắc đơn giản. Test bảo vệ tài nguyên nên đặt ngưỡng nhỏ, xác định và có thể chạy ổn định trong CI.

## 6. Chương trình Java 11+ hoàn chỉnh: tự kiểm thử các tình huống

Lưu mã dưới đây vào tệp **`GzipRobustnessDemo.java`**. Chỉ sử dụng Java SE, không cần thư viện ngoài. Các hàm `assertRejected` và `assertLimited` ném `AssertionError` nếu kết quả **khác điều kiện mong đợi**, nên lệnh chạy sẽ thất bại khi một trường hợp kiểm thử bị lỗi.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipRobustnessDemo {
    private static final int BUFFER_SIZE = 8192;
    private static final long MAX_OUTPUT_BYTES = 1_000_000;

    private static byte[] compress(byte[] data) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(data);
        }
        return output.toByteArray();
    }

    private static byte[] decompressLimited(byte[] compressed, long maxOutputBytes)
            throws IOException {
        if (maxOutputBytes < 0) {
            throw new IllegalArgumentException("Negative size limit");
        }
        try (GZIPInputStream input = new GZIPInputStream(
                    new ByteArrayInputStream(compressed), BUFFER_SIZE);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[BUFFER_SIZE];
            long total = 0;
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (n > maxOutputBytes - total) {
                    throw new IOException("Uncompressed size limit exceeded");
                }
                output.write(buffer, 0, n);
                total += n;
            }
            return output.toByteArray();
        }
    }

    private static void assertRejected(String name, byte[] bad) {
        try {
            decompressLimited(bad, MAX_OUTPUT_BYTES);
            throw new AssertionError(name + " unexpectedly accepted");
        } catch (IOException expected) {
            System.out.println(name + "=rejected");
        }
    }

    private static void assertLimited(String name, byte[] input, long limit) {
        try {
            decompressLimited(input, limit);
            throw new AssertionError(name + " unexpectedly accepted");
        } catch (IOException expected) {
            if (!"Uncompressed size limit exceeded".equals(expected.getMessage())) {
                throw new AssertionError(name + " failed for wrong reason", expected);
            }
            System.out.println(name + "=limit-rejected");
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] original = "Java 11: gzip corruption and truncation test\n"
                .getBytes(StandardCharsets.UTF_8);
        byte[] valid = compress(original);

        if (!Arrays.equals(original, decompressLimited(valid, original.length))) {
            throw new AssertionError("Valid gzip round-trip failed");
        }
        System.out.println("valid=ok");

        if (decompressLimited(compress(new byte[0]), 0).length != 0) {
            throw new AssertionError("Empty gzip round-trip failed");
        }
        System.out.println("empty=ok");

        assertLimited("oneByteShort", valid, original.length - 1);

        assertRejected("truncatedBody", Arrays.copyOf(valid, valid.length / 2));
        assertRejected("truncatedTrailer", Arrays.copyOf(valid, valid.length - 4));

        byte[] corruptHeader = valid.clone();
        corruptHeader[0] ^= 1;
        assertRejected("corruptHeader", corruptHeader);

        byte[] corruptChecksum = valid.clone();
        corruptChecksum[valid.length - 8] ^= 1;
        assertRejected("corruptChecksum", corruptChecksum);

        byte[] large = new byte[2_000_000];
        Arrays.fill(large, (byte) 'A');
        byte[] compressedLarge = compress(large);
        System.out.println("largeCompressedSmaller=" +
                (compressedLarge.length < large.length));
        assertLimited("largeOutput", compressedLarge, MAX_OUTPUT_BYTES);
    }
}
```

Biên dịch với JDK có compiler còn hỗ trợ mức Java 11, rồi chạy:

```bash
javac -encoding UTF-8 --release 11 GzipRobustnessDemo.java
java GzipRobustnessDemo
```

**Đầu ra đã kiểm chứng khi chạy trên JDK 24 (biên dịch với `--release 11`):**

```text
valid=ok
empty=ok
oneByteShort=limit-rejected
truncatedBody=rejected
truncatedTrailer=rejected
corruptHeader=rejected
corruptChecksum=rejected
largeCompressedSmaller=true
largeOutput=limit-rejected
```

### Đọc kết quả đúng cách

- `valid=ok`: chương trình **so sánh toàn bộ mảng byte** sau khi giải nén, chứ không chỉ so sánh độ dài.
- `empty=ok`: một nguồn GZIP hợp lệ có thể tạo nội dung rỗng mà không bị coi là hỏng.
- `oneByteShort=limit-rejected`: giới hạn được kiểm tra đúng cả ở điều kiện biên; luồng nén hoàn toàn hợp lệ nhưng đầu ra lớn hơn giới hạn do ứng dụng đặt.
- `truncatedBody` và `truncatedTrailer`: hai loại cắt cụt được từ chối; không cần giả định một subtype hoặc message lỗi giống nhau.
- `corruptHeader` và `corruptChecksum`: phát hiện lỗi định dạng và CRC ở các giai đoạn khác nhau.
- `largeCompressedSmaller=true`: dữ liệu nén ít byte hơn dữ liệu gốc, nên chỉ đặt giới hạn **kích thước file nén** là không đủ.
- `largeOutput=limit-rejected`: chương trình chặn khi giải nén vượt 1.000.000 byte, trước khi thêm khối gây vượt giới hạn vào output.

Hai chi tiết giúp test tránh báo PASS giả:

1. `assertRejected` chỉ bắt `IOException`. Nếu giải nén sai sót vẫn **thành công**, hàm ném `AssertionError` và **không tự bắt lại** lỗi test của chính nó.
2. `assertLimited` kiểm tra lỗi giới hạn do **ứng dụng** ném, không chấp nhận một `IOException` bất kỳ từ dữ liệu hỏng thay thế cho điều kiện vượt kích thước.

Trong hệ thống test hiện đại có thể dùng JUnit 5 để diễn đạt các assert tương tự; chương trình trên cố ý dùng Java SE thuần để có thể chạy trực tiếp và kiểm tra đầu ra mà không cần tải dependency.

## 7. Vì sao phải đọc đến cuối luồng để kiểm tra tính toàn vẹn?

Giả sử chương trình chỉ đọc 100 byte đầu, thấy nội dung có vẻ hợp lý rồi trả “thành công”. Nếu lỗi checksum hoặc thiếu trailer nằm ở cuối, chương trình có thể **chưa bao giờ chạy đến chỗ phát hiện lỗi**.

Với trường hợp đầu vào được cho là hợp lệ, quy trình tối thiểu:

1. Mở `GZIPInputStream`.
2. Đọc giải nén theo khối, đồng thời kiểm tra kích thước và xử lý dữ liệu.
3. **Tiếp tục đọc tới EOF (`-1`)** để thư viện có thể kiểm tra nội dung định dạng/trailer.
4. Chỉ **xác nhận kết quả hoàn tất** sau khi không có exception và các điều kiện nghiệp vụ được thỏa.
5. Đóng nguồn/đích đúng hợp đồng.

Nếu phát hiện vượt giới hạn ở bước 2, **dừng ngay là đúng** vì đã phải từ chối đầu vào đó; không cần tiếp tục giải nén toàn bộ dữ liệu quá lớn chỉ để có thêm thông báo lỗi CRC. Nhưng không được xem kết quả đầu ra tạm thời là hợp lệ.

**Kiểm tra GZIP không phải kiểm tra tính xác thực.** CRC32 giúp phát hiện nhiều lỗi truyền/ghi thông thường; nó không chống được người tạo lại luồng đã chỉnh sửa cùng CRC hợp lệ. Với đầu vào có yêu cầu bảo mật và nguồn không tin cậy, cần lớp xác thực riêng và chính sách chấp nhận dữ liệu rõ ràng.

## 8. Thiết kế giới hạn an toàn cho đầu ra lớn

### 8.1. Buffer cố định chưa đủ

Một vòng lặp đọc `8192` byte nhiều lần có thể tạo đầu ra hàng GB. **Bảo vệ đúng phải tính tổng các byte được giải nén**. Hãy xác định mức tối đa trên cơ sở loại tệp và yêu cầu nghiệp vụ:

- File cấu hình nhỏ có thể đặt mức giới hạn nhỏ.
- Tệp log hoặc báo cáo lớn cần cách lưu/xử lý streaming và giới hạn phù hợp hơn.
- Hệ thống nhận nội dung từ người dùng phải có cả giới hạn về byte nén nhận vào, byte giải nén tạo ra và thời gian/tài nguyên xử lý.

Không dùng một ngưỡng chung cho mọi ứng dụng. Ví dụ **1.000.000 byte** trong chương trình chỉ là giới hạn cố định để minh họa test.

### 8.2. Đặt giới hạn trước khi ghi và tránh tràn số

```java
long total = 0;
long maxBytes = 1_000_000;
// n là số byte thực sự được giải nén trong lần đọc này.
if (n > maxBytes - total) {
    throw new IOException("Uncompressed size limit exceeded");
}
total += n;
```

Đây là **mảnh mã minh họa** với biến `n` đến từ `input.read(buffer)`. Đảm bảo `maxBytes >= 0` và invariant `total <= maxBytes` trước phép trừ. Không chỉ dùng `if (total > maxBytes)` sau khi ghi, vì khi đó khối vượt ngưỡng **đã đi vào output**. Dùng `long` cho tổng thay vì `int` để không gây lỗi logic khi số lượng byte lớn.

### 8.3. Tránh đọc tất cả vào RAM với đầu vào không tin cậy

Những cách tiện lợi như `input.readAllBytes()` hoặc `InputStream.transferTo(output)` **không tự thêm ngưỡng giải nén của nghiệp vụ**. Với file chưa biết trước quy mô, hãy điều khiển vòng lặp đọc và kiểm tra tổng số byte trong lúc truyền sang output giới hạn.

Mẫu có `ByteArrayOutputStream` vì dữ liệu test được **giới hạn nhỏ có kiểm soát**. Với production, ưu tiên luồng đầu vào nén trực tiếp từ file/network và luồng ra phù hợp; kiểm soát cả bộ nhớ của các lớp wrapper, tránh nạp toàn bộ byte nén qua `Files.readAllBytes` nếu đầu vào có thể quá lớn.

### 8.4. Đừng công bố output từng phần như file đã hoàn tất

Một luồng GZIP sai CRC có thể đã cung cấp nhiều byte giải nén trước khi phát hiện lỗi ở đoạn cuối. Nếu bạn ghi thẳng vào file đích chính thức, file đó có thể bị **ghi dở** khi exception xảy ra.

Thiết kế an toàn hơn là:

1. Ghi dữ liệu vào **file tạm được quản lý**, có giới hạn kích thước.
2. Đọc/giải nén hết luồng và thực hiện mọi xác minh cần thiết.
3. Chỉ khi tất cả bước thành công, mới công bố/đổi tên file tạm thành file kết quả theo cơ chế phù hợp.
4. Nếu lỗi, xóa file tạm theo chính sách dọn dẹp.

Nếu cần chuyển file theo cách nguyên tử, tính khả dụng của `Files.move(..., ATOMIC_MOVE)` phụ thuộc filesystem/provider. Không được giả định mọi filesystem hỗ trợ atomic move, cũng không bỏ qua yêu cầu đồng bộ hóa và quyền truy cập của hệ thống thực tế.

### 8.5. Giới hạn tài nguyên khác

Giới hạn số byte sau giải nén là **cần thiết nhưng chưa đủ**. Tùy môi trường cần thêm:

- Giới hạn **byte nén** ở đầu vào, tránh upload/tải không giới hạn.
- Giới hạn **thời gian xử lý, CPU, số tác vụ đồng thời** và khả năng hủy tác vụ.
- Giới hạn **tốc độ phình nở** khi hữu ích, nhưng không lấy tỷ lệ nén làm giới hạn duy nhất vì dữ liệu hợp lệ có thể nén rất tốt.
- Chính sách truy cập file, dung lượng đĩa và đầu ra của dịch vụ.
- Quan sát/ghi nhận số byte đọc, số byte giải nén, loại lỗi và việc dọn dẹp mà **không** lộ dữ liệu nhạy cảm hoặc stack trace cho người dùng cuối.

Một số giới hạn (như thời gian/CPU) cần được thực hiện ở tầng hệ thống, job hoặc mạng; `GZIPInputStream` tự nó không triển khai toàn bộ chính sách kiểm soát tài nguyên.

## 9. Kiểm thử ZIP cần thêm các trường hợp nào?

**GZIP** thường là một luồng byte nén. **ZIP** là định dạng archive có thể chứa **nhiều entry**, tên file và metadata. Không thể bê nguyên mọi kỳ vọng GZIP sang `ZipInputStream` hoặc `ZipFile` mà bỏ qua cấu trúc ZIP:

| Loại kiểm tra ZIP | Điều kiện bổ sung |
| --- | --- |
| Entry bị hỏng/cắt cụt | Đọc đủ nội dung mỗi entry; kiểm tra ngoại lệ và tính toàn vẹn theo API. |
| Nhiều entry | Áp dụng giới hạn byte **trên từng entry** và **tổng toàn archive**. |
| Quá nhiều file | Giới hạn **số lượng entry**, độ sâu thư mục và các tài nguyên cần tạo. |
| Tên entry không tin cậy | Ngăn **Zip Slip**: không cho đường dẫn trong archive vượt khỏi thư mục giải nén được phép; xem xét symlink và điều kiện race. |
| Metadata khai báo kích thước | Không chỉ tin `ZipEntry.getSize()` hoặc `getCompressedSize()`: các giá trị có thể chưa biết hoặc không đủ để xác thực ngưỡng thực tế. |
| Archive bị cắt phần chỉ mục cuối | `ZipInputStream` đọc tuần tự các entry, `ZipFile` dùng cấu trúc archive khác; chiến lược kiểm thử cần phản ánh parser thực tế. |

Không mặc định rằng `ZipInputStream` phát hiện mọi dạng mất phần cuối hoặc xác thực toàn bộ central directory giống `ZipFile`. Chọn API phù hợp và tạo fixture hỏng đúng phần cấu trúc muốn kiểm tra. Nếu cần bảo đảm toàn bộ archive, phải định nghĩa yêu cầu đối với **toàn bộ ZIP**, không chỉ thành công khi giải nén một entry đầu.

Đối với giải nén ZIP ra thư mục, kiểm thử đường dẫn đích theo các thành phần `Path`, không đơn thuần dựa trên kiểm tra chuỗi có `".."`; các trường hợp symlink và filesystem khác nhau cần xử lý theo mô hình đe dọa của ứng dụng.

## 10. Tối ưu thiết kế test tự động và tránh false positive

Một bộ kiểm thử tốt nên có:

- **Dữ liệu fixture được tạo trong test** hoặc được kiểm soát phiên bản, không dựa vào tệp trên máy lập trình viên.
- **Test dương** cho dữ liệu hợp lệ, đầu vào rỗng hợp lệ, dữ liệu chứa Unicode được mã hóa thành byte theo charset rõ ràng khi bài toán là văn bản.
- **Test âm** cho cắt cụt ở các vị trí khác nhau, sai header, sai checksum, payload bị thay đổi và lỗi I/O từ nguồn đầu vào.
- **Test biên kích thước** tại `limit - 1`, `limit` và `limit + 1`, bao gồm nguồn có kích thước đầu ra 0.
- **Test phình nở** với một khối byte có kích thước vừa đủ nhưng tỷ lệ nén cao; không tạo payload cực đại khiến CI thiếu RAM.
- **Test tài nguyên**: xác minh stream/file tạm được đóng/dọn sau cả thành công và thất bại.
- **Test hiệu năng giới hạn**: kiểm thử timeout/cancellation ở tầng phù hợp nếu ứng dụng giải nén đầu vào không tin cậy.

Không viết:

```java
try {
    decompressLimited(bad, limit);
} catch (Exception ignored) {
    // Không có assert: test có thể cho PASS giả.
}
```

Đây là **phản ví dụ**, không phải logic kiểm thử nên dùng. Nếu muốn kiểm tra đúng lỗi, dùng kiểu exception đã dự kiến; đối với giới hạn do code tự kiểm soát, nên dùng **loại lỗi/định danh rõ ràng**. Trong ví dụ tự chứa, `assertLimited` kiểm tra message do chính phương thức giải nén định nghĩa; trong code production có thể dùng exception riêng để tránh dựa trên văn bản thông báo.

**Không kiểm tra chính xác chuỗi của lỗi từ JDK** như `"Unexpected end of ZLIB input stream"` hoặc `"Corrupt GZIP trailer"`. Thời điểm lỗi được phát hiện và thông báo có thể thay đổi theo implementation, cách input được phân đoạn và phiên bản JDK. Thứ cần kiểm tra là **bị từ chối**, không sinh output được chấp nhận và không làm rò rỉ tài nguyên.

Đặc biệt, phương thức kiểm thử âm phải **không bắt luôn `AssertionError` mà chính test ném ra**. Điều này giúp test thất bại khi code nhận sai dữ liệu mà vẫn trả thành công.

## 11. Bài tập và đáp án

**Câu 1.** Giải nén bằng buffer `8192` byte có đủ để bảo đảm không bao giờ tạo ra đầu ra quá 1 MB không?

**Đáp án:** Không. Buffer chỉ giới hạn mỗi lần đọc; phải cộng tổng byte qua các lần đọc, kiểm tra **trước khi ghi**.

**Câu 2.** Vì sao một file GZIP có thể trả hàng nghìn byte hợp lệ rồi mới ném `IOException`?

**Đáp án:** Header/payload có thể đọc được một phần; lỗi cắt cụt/checksum/trailer chỉ được phát hiện khi đọc đến vùng dữ liệu liên quan. Không xác nhận thành công trước khi đọc đầy đủ và kiểm tra kết thúc.

**Câu 3.** Một GZIP giải nén thành 0 byte có luôn là dữ liệu hỏng không?

**Đáp án:** Không. GZIP hợp lệ có thể chứa nội dung rỗng. Phải phân biệt nó với input byte rỗng `new byte[0]` không có cấu trúc GZIP.

**Câu 4.** Giới hạn là 10.000 byte, giải nén đúng 10.000 byte có nên bị từ chối không?

**Đáp án:** Không, nếu chính sách cho phép **tối đa** 10.000 byte. Từ chối khi byte thứ 10.001 sẽ được ghi; kiểm thử `limit-1`, `limit`, `limit+1`.

**Câu 5.** Nếu kiểm tra CRC32 của GZIP thành công, có thể kết luận file đã được xác thực chống sửa đổi có chủ ý không?

**Đáp án:** Không. CRC32 phát hiện lỗi dữ liệu thông thường nhưng không phải chữ ký/MAC; cần biện pháp xác thực bảo mật thích hợp khi dữ liệu có thể bị chỉnh sửa bởi kẻ tấn công.

**Câu 6.** Khi giải nén ra file đích đã ghi được một nửa rồi phát hiện CRC sai, nên làm gì?

**Đáp án:** Không công bố file là hoàn thành. Dùng file tạm và chỉ chuyển thành file chính thức sau khi xác minh đầy đủ; dọn file tạm nếu thất bại.

**Câu 7.** Có thể chỉ dựa vào `ZipEntry.getSize()` để quyết định một archive ZIP an toàn về tài nguyên không?

**Đáp án:** Không. Metadata có thể thiếu hoặc không đủ; phải **đếm byte thực sự giải nén**, áp dụng giới hạn mỗi entry, tổng archive và số entry; đồng thời kiểm tra đường dẫn giải nén.

**Câu 8.** Trong test dữ liệu hỏng, vì sao không nên assert exact text của `ZipException`?

**Đáp án:** Lý do từ chối nên được kiểm tra bằng kiểu/nhóm lỗi và hợp đồng của ứng dụng; chuỗi thông báo của Java có thể thay đổi, khiến test dễ hỏng giả khi cập nhật JDK.

## 12. Tóm tắt và tài liệu tham khảo

- Với dữ liệu nén, luôn kiểm thử **dữ liệu hợp lệ**, **rỗng hợp lệ**, **cắt cụt**, **hỏng cấu trúc/checksum** và **đầu ra giải nén lớn**.
- Với GZIP, **đọc đến EOF** là cần thiết để xác định một luồng hoàn thành; thành công khi đọc một vài khối đầu chưa đủ.
- Dùng buffer có kích thước xác định, **đếm byte đã giải nén**, kiểm tra trước khi ghi và giới hạn tổng đầu ra bằng chính sách rõ ràng.
- Đừng dựa vào `readAllBytes()`, tỷ lệ nén hay kích thước file nén như biện pháp bảo vệ duy nhất.
- Lỗi có thể phát sinh khi **mở** hoặc khi **đọc** luồng; test âm nên chấp nhận lỗi I/O dự kiến thay vì phụ thuộc thông báo của JDK.
- Dọn tài nguyên bằng `try-with-resources`; khi ghi file chính thức, cần tránh công bố dữ liệu giải nén dở trước khi xác thực và hoàn tất.
- Với ZIP nhiều entry, bổ sung giới hạn từng entry/tổng, số file, đường dẫn đích và kiểm thử parser thật sự sử dụng.
- **CRC32 không phải xác thực mật mã**. Nếu nguồn có thể bị sửa đổi có chủ đích, phải có kiểm tra tính xác thực độc lập.

Nguồn kỹ thuật vẫn áp dụng trong Java hiện đại:

- [Oracle Java SE 11 — GZIPInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPInputStream.html).
- [Oracle Java SE 11 — GZIPOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPOutputStream.html).
- [Oracle Java SE 11 — ZipInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/ZipInputStream.html).
- [Oracle Java SE 11 — ZipFile](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/ZipFile.html).
- [Oracle Java SE 11 — InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html).
- [RFC 1952 — GZIP file format specification](https://www.rfc-editor.org/rfc/rfc1952).