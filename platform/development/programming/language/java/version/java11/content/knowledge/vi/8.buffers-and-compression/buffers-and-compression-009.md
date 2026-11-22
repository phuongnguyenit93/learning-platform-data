# Kết thúc nén, giải nén và giải phóng tài nguyên (Java 11+)

## 1. Vì sao “xong dữ liệu” không đồng nghĩa với “đã giải phóng tài nguyên”?

Trong Java NIO và xử lý dữ liệu nhị phân, một chương trình thường phải **nén** một vùng byte, chuyển dữ liệu nén sang nơi khác, rồi **giải nén** để khôi phục dữ liệu gốc. Hai lớp `java.util.zip.Deflater` và `java.util.zip.Inflater` cung cấp cơ chế nén/giải nén theo định dạng **zlib**; chúng làm việc với `byte[]` hoặc `ByteBuffer`.

Khi dùng trực tiếp các lớp này, cần phân biệt ba việc:

1. **Thông báo không còn dữ liệu đầu vào để nén**: `Deflater.finish()`.
2. **Kiểm tra quá trình nén/giải nén thực sự hoàn thành**: `Deflater.finished()` hoặc `Inflater.finished()`.
3. **Giải phóng tài nguyên của bộ nén/bộ giải nén**: `end()` (tương thích Java 11); trên JDK mới còn có `close()` khi lớp hỗ trợ.

Đây là ba thời điểm **khác nhau**. Gọi `finish()` không có nghĩa mọi byte nén cuối cùng đã được tạo. Gọi `finished()` chỉ kiểm tra trạng thái, **không** giải phóng tài nguyên. Gọi `end()` quá sớm có thể hủy phần dữ liệu chưa xử lý.

Nội dung dưới đây sử dụng kiến thức **vẫn áp dụng hiện nay**, đồng thời chú thích chính xác khác biệt API giữa Java 11 và các JDK mới.

## 2. Bảng vòng đời quan trọng

| Lớp | Phương thức | Vai trò | Không nên hiểu nhầm |
| --- | --- | --- | --- |
| `Deflater` | `setInput(...)` | Cung cấp byte chưa nén | Chưa đồng nghĩa kết thúc toàn bộ đầu vào |
| `Deflater` | `finish()` | Thông báo đã cung cấp **hết** đầu vào; yêu cầu kết thúc luồng nén | **Không** tự trả về mọi byte nén còn lại |
| `Deflater` | `deflate(...)` | Tạo byte nén vào buffer đầu ra, có thể cần gọi nhiều lần | Một lần gọi không nhất thiết đủ |
| `Deflater` | `finished()` | `true` khi đã tạo xong **toàn bộ đầu ra nén** | Không giải phóng tài nguyên |
| `Deflater` | `end()` | Đóng bộ nén, giải phóng tài nguyên và bỏ dữ liệu chưa xử lý | Không thay cho bước nén hết dữ liệu |
| `Inflater` | `setInput(...)` | Cung cấp byte nén | Có thể chỉ cung cấp một phần luồng |
| `Inflater` | `inflate(...)` | Khôi phục các byte gốc vào vùng đầu ra | Có thể trả `0` dù luồng chưa kết thúc |
| `Inflater` | `finished()` | `true` khi đã đạt cuối **luồng dữ liệu nén** hợp lệ | Không giải phóng tài nguyên |
| `Inflater` | `needsInput()` | Cần thêm byte nén để tiếp tục | **Không** đồng nghĩa đã giải nén xong |
| `Inflater` | `needsDictionary()` | Luồng nén yêu cầu từ điển giải nén | Không tự cung cấp từ điển |
| `Inflater` | `end()` | Đóng bộ giải nén và giải phóng tài nguyên | Không chứng minh dữ liệu đã giải nén đầy đủ |

**`Inflater` không có phương thức `finish()` tương ứng với `Deflater.finish()`.** Phía giải nén biết đã hoàn tất nhờ phát hiện điểm kết thúc hợp lệ của luồng nén và `Inflater.finished()` trả `true`.

Ví dụ mô hình vòng đời:

```text
NÉN
setInput → (cung cấp đủ đầu vào) → finish()
         → deflate(...) nhiều lần → finished() == true
         → lấy dữ liệu nén cuối cùng → end() trong finally

GIẢI NÉN
setInput → inflate(...) nhiều lần → finished() == true
          → kiểm tra dữ liệu dư/chính sách dữ liệu → end() trong finally
                  ├─ needsInput() và chưa kết thúc: cần thêm input / lỗi cắt cụt
                  ├─ needsDictionary(): cần dictionary phù hợp
                  └─ DataFormatException: dữ liệu nén sai định dạng
```

## 3. Dùng Deflater đúng cách: finish, deflate, finished, end

### 3.1. `finish()` chỉ đánh dấu hết đầu vào

Khi đã chuyển **toàn bộ byte gốc** vào `Deflater` bằng `setInput`, gọi:

```java
deflater.finish();
```

Lệnh này thông báo rằng **không còn đầu vào mới**. Nó cho phép bộ nén tạo phần kết thúc và các byte còn tồn đọng cần thiết cho luồng zlib hoàn chỉnh. Để thu đủ đầu ra, cần tiếp tục gọi `deflate(...)` cho đến khi `finished() == true`:

```java
byte[] chunk = new byte[1024];
while (!deflater.finished()) {
    int count = deflater.deflate(chunk);
    // Ghi đúng count byte [0, count) vào nơi nhận.
}
```

Đây là **mảnh code diễn giải**, không phải chương trình độc lập. Mã hoàn chỉnh tại mục 5 xử lý cả trường hợp không có tiến triển và đảm bảo `end()`.

**Không gọi `finish()` trước khi còn input phải cung cấp.** Nếu đang nén dữ liệu theo nhiều khối, hãy cung cấp các khối vào thời điểm phù hợp và chỉ gọi `finish()` khi **khối cuối** đã được đưa cho bộ nén. Sau đó tiếp tục lấy hết đầu ra.

### 3.2. `finished()` mới nói đã xuất xong byte nén

`Deflater.finished()` trả `true` khi đã đạt cuối luồng đầu ra nén. Khi `false`, có thể vẫn còn byte nén hoặc byte kết thúc cần tạo. Lấy kết quả quá sớm sẽ dẫn tới luồng thiếu dữ liệu, khiến phía giải nén báo lỗi hoặc không đạt `Inflater.finished()`.

Vì đầu ra có thể lớn hơn buffer tạm, không giả định một lần `deflate(chunk)` đủ. Khi dùng buffer cố định, mỗi lần phải lưu đúng số byte thực tế do phương thức trả về.

### 3.3. `end()` dùng để giải phóng tài nguyên, kể cả khi lỗi

`Deflater` duy trì trạng thái bộ nén và tài nguyên của thư viện zlib bên dưới. Trên **Java 11**, cách quản lý đúng là:

```java
Deflater deflater = new Deflater();
try {
    // setInput, finish, deflate đến khi finished...
} finally {
    deflater.end();
}
```

`finally` vẫn chạy nếu trong `try` có ngoại lệ. **Đừng chờ bộ thu gom rác để giải phóng tài nguyên zlib**; giải phóng rõ ràng khi không còn dùng bộ nén. Sau khi `end()`, đối tượng không còn được dùng cho thao tác nén tiếp theo.

`reset()` có thể đặt lại trạng thái để nén một luồng mới khi bộ nén **chưa đóng**, nhưng nó **không thay thế `end()`** và không phải cách giải phóng tài nguyên cuối cùng.

## 4. Dùng Inflater đúng cách: finished, needsInput, needsDictionary, end

### 4.1. Giải nén đến hết luồng, không chỉ đến khi buffer đầy

`Inflater.inflate(...)` tạo ra một số byte gốc ở mỗi lần gọi. Thông thường phải gọi lặp:

```java
while (!inflater.finished()) {
    int count = inflater.inflate(outputChunk);
    // Xử lý count byte đầu ra đã giải nén.
}
```

Đây là **mã minh họa**, cần bổ sung xử lý trạng thái `count == 0` như ở mục 5. Khi `inflate(...)` trả `0`, **không được tự kết luận** đã giải nén xong. Cần xét:

- `inflater.finished()`: đã thấy cuối luồng nén hợp lệ; dừng.
- `inflater.needsInput()`: chưa đủ byte nén, cần đưa thêm input nếu nguồn vẫn còn dữ liệu.
- `inflater.needsDictionary()`: yêu cầu từ điển giải nén phù hợp; nếu ứng dụng không hỗ trợ, báo lỗi.
- Không thuộc các trường hợp trên mà không tạo byte mới: không nên lặp vô hạn; xử lý điều kiện không tiến triển theo thiết kế ứng dụng.

Nếu đang giải nén từ **một mảng byte được coi là toàn bộ luồng nén**, `needsInput() == true` nhưng `finished() == false` nghĩa là luồng **chưa có điểm kết thúc đầy đủ**: cần báo lỗi dữ liệu thiếu/cắt cụt. Với nguồn streaming, `needsInput()` trước hết có nghĩa là **cần nạp tiếp**; chỉ kết luận cắt cụt khi nguồn đã EOF mà vẫn chưa đạt `finished()`.

### 4.2. Phát hiện dữ liệu lỗi và dữ liệu dư

`inflate(...)` có thể ném `DataFormatException` nếu dữ liệu zlib sai định dạng. Xử lý hoặc chuyển sang `IOException` cho lớp API ngoài như ví dụ hoàn chỉnh.

`Inflater.getRemaining()` cho biết có bao nhiêu byte đầu vào **đã đưa vào inflater** nhưng chưa được tiêu thụ. Khi xác định định dạng chỉ được phép có **đúng một luồng zlib**, có thể kiểm tra `getRemaining() == 0` sau `finished()`.

**Lưu ý:** Một ứng dụng thực có thể cố tình nối metadata hoặc nhiều khung dữ liệu sau một luồng nén; trong trường hợp đó, cần xử lý phần dữ liệu dư theo **giao thức cụ thể**, không mặc định mọi byte dư đều sai. Với nguồn streaming đã chia nhiều khối, `getRemaining()` chỉ nói về phần input đang nằm trong inflater, không tự bao quát các khối chưa nạp.

### 4.3. `end()` phải chạy dù giải nén thất bại

`Inflater` cũng giữ trạng thái/tài nguyên zlib. Với Java 11:

```java
Inflater inflater = new Inflater();
try {
    // setInput, inflate và kiểm tra finished, lỗi dữ liệu...
} finally {
    inflater.end();
}
```

`end()` làm sạch tài nguyên nhưng **không chứng minh đã giải nén thành công**. Vì vậy, kiểm tra `finished()` và xác minh kết quả phải nằm **trước khi** đóng tài nguyên; việc giải phóng cuối cùng vẫn thực hiện trong `finally` bất kể thành công hay thất bại.

## 5. Ví dụ đầy đủ: nén, giải nén, kiểm tra kết thúc và dọn dẹp

Ví dụ sau chạy độc lập trên **Java 11+**, không phụ thuộc thư viện ngoài. Nó chủ động sử dụng `try/finally` với `end()` để tương thích Java 11, giới hạn lượng dữ liệu giải nén, phát hiện luồng cắt cụt, dữ liệu hỏng và phần byte thừa.

Tạo tệp **`CompressionLifecycleDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public class CompressionLifecycleDemo {
    private static byte[] compress(byte[] data) throws IOException {
        Deflater deflater = new Deflater();
        try {
            deflater.setInput(data);
            deflater.finish();

            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[32];
            while (!deflater.finished()) {
                int n = deflater.deflate(chunk);
                if (n > 0) {
                    out.write(chunk, 0, n);
                } else if (!deflater.finished()) {
                    throw new IOException("Nen khong tien trien");
                }
            }
            return out.toByteArray();
        } finally {
            deflater.end();
        }
    }

    private static byte[] decompress(byte[] compressed, int maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be nonnegative");
        }

        Inflater inflater = new Inflater();
        try {
            inflater.setInput(compressed);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[16];

            while (!inflater.finished()) {
                final int n;
                try {
                    n = inflater.inflate(chunk);
                } catch (DataFormatException ex) {
                    throw new IOException("Du lieu nen khong hop le", ex);
                }

                if (n > 0) {
                    if (n > maxBytes - out.size()) {
                        throw new IOException("Vuot gioi han dau ra");
                    }
                    out.write(chunk, 0, n);
                } else if (inflater.finished()) {
                    break;
                } else if (inflater.needsDictionary()) {
                    throw new IOException("Can tu dien giai nen");
                } else if (inflater.needsInput()) {
                    throw new EOFException("Luong zlib chua ket thuc");
                } else {
                    throw new IOException("Giai nen khong tien trien");
                }
            }

            if (inflater.getRemaining() != 0) {
                throw new IOException("Du lieu du sau luong zlib");
            }
            return out.toByteArray();
        } finally {
            inflater.end();
        }
    }

    public static void main(String[] args) throws IOException {
        String text = "Xin ch\u00E0o Java 11! ".repeat(5);
        byte[] original = text.getBytes(StandardCharsets.UTF_8);
        byte[] compressed = compress(original);
        byte[] restored = decompress(compressed, 1024);

        System.out.println("round-trip = " + Arrays.equals(original, restored));
        System.out.println("utf8 = "
                + new String(restored, StandardCharsets.UTF_8)
                        .startsWith("Xin ch\u00E0o"));
        System.out.println("empty = "
                + Arrays.equals(new byte[0], decompress(compress(new byte[0]), 0)));

        try {
            decompress(Arrays.copyOf(compressed, compressed.length - 2), 1024);
            System.out.println("truncated = undetected");
        } catch (EOFException ex) {
            System.out.println("truncated = rejected");
        }

        byte[] corrupted = compressed.clone();
        corrupted[corrupted.length - 1] ^= 1;
        try {
            decompress(corrupted, 1024);
            System.out.println("corrupt = undetected");
        } catch (IOException ex) {
            System.out.println("corrupt = rejected");
        }

        try {
            decompress(compressed, 10);
            System.out.println("limit = missed");
        } catch (IOException ex) {
            System.out.println("limit = rejected");
        }

        byte[] withTrailing = Arrays.copyOf(compressed, compressed.length + 1);
        try {
            decompress(withTrailing, 1024);
            System.out.println("trailing = undetected");
        } catch (IOException ex) {
            System.out.println("trailing = rejected");
        }

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (DeflaterOutputStream zipped = new DeflaterOutputStream(sink)) {
            zipped.write(original);
        }
        try (InflaterInputStream unzipped =
                     new InflaterInputStream(
                             new ByteArrayInputStream(sink.toByteArray()))) {
            System.out.println("stream round-trip = "
                    + Arrays.equals(original, unzipped.readAllBytes()));
        }
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên; `--release 11` giúp kiểm chứng cú pháp/API ở mức Java 11 kể cả khi dùng JDK mới:

```bash
javac --release 11 CompressionLifecycleDemo.java
java CompressionLifecycleDemo
```

**Đầu ra đã kiểm thử thực tế:**

```text
round-trip = true
utf8 = true
empty = true
truncated = rejected
corrupt = rejected
limit = rejected
trailing = rejected
stream round-trip = true
```

Giải thích:

- **`round-trip = true`:** byte sau giải nén đúng bằng byte trước nén.
- **`utf8 = true`:** văn bản có ký tự tiếng Việt được khôi phục đúng qua UTF-8.
- **`empty = true`:** luồng có dữ liệu gốc rỗng cũng được nén và kết thúc hợp lệ; không nhầm với thiếu luồng nén.
- **`truncated = rejected`:** cố tình xóa hai byte cuối luồng nén; đầu giải nén đã hết input mà chưa nhận đủ dấu kết thúc hợp lệ nên bị từ chối.
- **`corrupt = rejected`:** cố tình đổi byte kiểm tra cuối luồng nén; kết quả dữ liệu lỗi được báo qua `IOException` (bao hàm `DataFormatException`).
- **`limit = rejected`:** chương trình chặn đầu ra giải nén vượt `maxBytes`, tránh phân bổ dữ liệu không giới hạn.
- **`trailing = rejected`:** chương trình chỉ chấp nhận **một luồng zlib** và không cho phép byte thừa sau đó.
- **`stream round-trip = true`:** ví dụ dùng `DeflaterOutputStream` và `InflaterInputStream` cũng khôi phục đúng dữ liệu, với `try`-with-resources.

Hai hàm `compress` và `decompress` đều đặt `end()` trong `finally`, nên trạng thái/tài nguyên native của bộ nén/giải nén được giải phóng ngay cả khi có lỗi.

**Giới hạn thiết kế mẫu:** `decompress` nhận toàn bộ mảng nén đầu vào, nên `needsInput()` trong vòng lặp nghĩa là mảng đã cung cấp không đủ để kết thúc luồng. Đối với file lớn/luồng mạng, phải nạp thêm input khi cần và kiểm soát tổng byte giải nén theo từng chunk thay vì đọc hết vào bộ nhớ. Đoạn kiểm tra `getRemaining()` ở đây là **chính sách ứng dụng chỉ chấp nhận đúng một luồng zlib**, không phải yêu cầu của mọi định dạng nén.

## 6. Phân biệt finish, finished, flush, close và end

Tên phương thức giống nhau ở vài lớp nhưng **vai trò khác nhau**:

| Phương thức | Lớp | Ý nghĩa |
| --- | --- | --- |
| `finish()` | `Deflater` | Báo hết input chưa nén; còn phải gọi `deflate` đến khi hoàn tất |
| `finished()` | `Deflater` | Kiểm tra đã tạo hết output nén chưa |
| `finished()` | `Inflater` | Kiểm tra đã giải nén tới cuối luồng nén hợp lệ chưa |
| `finish()` | `DeflaterOutputStream` | Ghi hết các byte nén còn lại, **không đóng** stream dưới |
| `flush()` | `DeflaterOutputStream` | Flush dữ liệu đệm theo chính sách; **không đồng nghĩa hoàn thành luồng nén** |
| `close()` | `DeflaterOutputStream` | Hoàn tất phần output nén còn lại và đóng stream dưới |
| `close()` | `InflaterInputStream` | Đóng stream giải nén và stream dưới, giải phóng tài nguyên tương ứng |
| `end()` | `Deflater` / `Inflater` | Giải phóng tài nguyên zlib của đối tượng dùng trực tiếp |

**Không thay `finish()` bằng `flush()`** khi mục tiêu là tạo **một luồng nén hoàn chỉnh**. `flush()` thường chỉ đẩy dữ liệu đang đệm theo cơ chế flush, không phải lời khẳng định đã hết nguồn dữ liệu. Ngược lại, `DeflaterOutputStream.finish()` dùng khi cần hoàn tất một luồng nén nhưng **vẫn muốn giữ stream bên dưới mở** để tiếp tục áp dụng bộ lọc hoặc ghi dữ liệu khác theo giao thức.

Khi dùng stream, `try`-with-resources là cách tự động gọi `close()` ngay cả khi có lỗi:

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();

try (DeflaterOutputStream zipped = new DeflaterOutputStream(sink)) {
    zipped.write("Hello Java".getBytes(StandardCharsets.UTF_8));
}

byte[] compressedBytes = sink.toByteArray();
```

Đoạn này là **mảnh mã bên trong phương thức có khai báo/nhập khẩu phù hợp**. `close()` của `DeflaterOutputStream` sẽ kết thúc việc ghi byte nén còn lại. `ByteArrayOutputStream` không cần đóng để lấy `toByteArray()`; nó chỉ lưu byte trong bộ nhớ.

### Quyền sở hữu compressor/decompressor khi dùng stream

Đừng giả định mọi stream đều chịu trách nhiệm giải phóng **đối tượng `Deflater`/`Inflater` do bạn truyền từ ngoài vào**:

- Nếu khởi tạo `new DeflaterOutputStream(output)` hoặc `new InflaterInputStream(input)` **không cung cấp** compressor/decompressor, stream tạo đối tượng nội bộ và tự quản lý khi đóng.
- Nếu bạn **tự tạo** `Deflater`/`Inflater` rồi truyền vào constructor stream, hãy xác định rõ **caller sở hữu đối tượng đó** và phải đóng/`end()` sau khi đóng stream.
- Đóng wrapper stream thường cũng **đóng stream bên dưới**. Không dùng `close()` nếu ứng dụng cần giữ stream bên dưới mở, trừ khi thiết kế có cơ chế tách vòng đời rõ ràng; `finish()` trên `DeflaterOutputStream` không đóng stream dưới.

Mẫu Java 11 khi chủ động sở hữu compressor được truyền cho wrapper:

```java
Deflater custom = new Deflater(Deflater.BEST_SPEED);
try {
    try (DeflaterOutputStream zipped =
                 new DeflaterOutputStream(sink, custom)) {
        zipped.write(original);
    } // Đóng stream; hoàn tất luồng nén.
} finally {
    custom.end(); // Giải phóng bộ nén do caller tạo.
}
```

Đây là **mảnh mã minh họa** với `sink`/`original` đã khai báo, chạy trong phương thức xử lý `IOException`. Trình tự đóng stream trước rồi `end()` bảo đảm bộ nén còn sẵn sàng trong lúc wrapper ghi ra phần cuối.

## 7. Khác biệt phiên bản: Java 11 so với JDK 25 trở lên

**Đây là một điểm dễ tạo ra mã sai phiên bản** nếu đọc Javadoc của JDK mới mà quên yêu cầu tương thích Java 11.

- Trong **Java 11**, `Deflater` và `Inflater` **chưa triển khai `AutoCloseable` trực tiếp**. Vì vậy `try (Deflater d = new Deflater()) { ... }` **không thể biên dịch với `javac --release 11`**. Dùng `try/finally` và gọi `end()` như ví dụ hoàn chỉnh.
- Từ **JDK 25**, `Deflater` và `Inflater` triển khai `AutoCloseable`; `close()` gọi `end()`. Trên mã chỉ nhắm JDK 25+, có thể dùng `try`-with-resources trực tiếp.
- **Các lớp stream** như `DeflaterOutputStream` và `InflaterInputStream` đã hỗ trợ `AutoCloseable` từ trước Java 11; `try`-with-resources cho các stream này **dùng được ngay trên Java 11**.

Mã minh họa **chỉ dành cho JDK 25+**, **không phải Java 11**:

```java
// Chỉ biên dịch khi nhắm API JDK 25+:
try (Deflater compressor = new Deflater()) {
    compressor.setInput(data);
    compressor.finish();
    // Tiếp tục deflate(...) đến khi compressor.finished().
} // close() tương đương end().
```

Những lời gọi `finish()`, `finished()` và `end()` vẫn có ý nghĩa thực tế hiện nay; sự bổ sung `AutoCloseable` không làm `finish` và `end` trở thành một thao tác duy nhất. Muốn **một mã nguồn tương thích từ Java 11 đến các bản mới**, mẫu `try/finally + end()` vẫn là lựa chọn phù hợp.

## 8. Dùng ByteBuffer cho đầu vào và đầu ra

Trong Java 11, các overload `setInput(ByteBuffer)`, `deflate(ByteBuffer)` và `inflate(ByteBuffer)` cho phép nén/giải nén mà không cần chuyển mọi byte qua mảng trung gian. Các phương thức xử lý **phần remaining** và điều chỉnh `position` của `ByteBuffer` khi tiêu thụ/ghi byte.

Ví dụ độc lập **`ByteBufferZlibExample.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

public class ByteBufferZlibExample {
    public static void main(String[] args) throws Exception {
        ByteBuffer data = ByteBuffer.wrap("AAA".getBytes(StandardCharsets.UTF_8));
        ByteBuffer compressed = ByteBuffer.allocate(64);

        Deflater compressor = new Deflater();
        try {
            compressor.setInput(data);
            compressor.finish();
            while (!compressor.finished()) {
                int n = compressor.deflate(compressed);
                if (n == 0 && !compressor.finished()) {
                    throw new IllegalStateException("Output buffer is too small");
                }
            }
        } finally {
            compressor.end();
        }
        compressed.flip();

        ByteBuffer restored = ByteBuffer.allocate(64);
        Inflater decompressor = new Inflater();
        try {
            decompressor.setInput(compressed);
            while (!decompressor.finished()) {
                int n = decompressor.inflate(restored);
                if (n == 0 && !decompressor.finished()) {
                    if (decompressor.needsDictionary()) {
                        throw new IllegalStateException("Dictionary required");
                    }
                    if (decompressor.needsInput()) {
                        throw new IllegalStateException("Truncated compressed data");
                    }
                    throw new IllegalStateException("Cannot make progress");
                }
            }
        } finally {
            decompressor.end();
        }
        restored.flip();
        System.out.println("result = " + StandardCharsets.UTF_8.decode(restored));
        System.out.println("source remaining = " + data.remaining());
        System.out.println("compressed remaining = " + compressed.remaining());
    }
}
```

Lệnh:

```bash
javac --release 11 ByteBufferZlibExample.java
java ByteBufferZlibExample
```

**Kết quả đã kiểm chứng:**

```text
result = AAA
source remaining = 0
compressed remaining = 0
```

Điểm cần nhớ:

- `deflate(compressed)` đẩy byte nén vào `ByteBuffer` đầu ra và làm tăng `position`; cần `compressed.flip()` trước khi biến nó thành **input** cho `Inflater`.
- `inflate(restored)` ghi byte giải nén vào `restored` và làm tăng `position`; cần `restored.flip()` trước khi giải mã UTF-8.
- Với ví dụ ngắn `AAA`, buffer 64 byte đủ sức chứa. Trong dữ liệu thực tế, không cố định một buffer nhỏ rồi giả định luôn đủ: phải xả/đọc từng chunk và xử lý khi output đầy.
- ByteBuffer có thể là heap hoặc direct; điều quan trọng là **`position`, `limit` và `remaining`** đúng tại thời điểm gọi.

## 9. Các lỗi phổ biến và xử lý

| Vấn đề | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Gọi `Deflater.end()` ngay sau `finish()` | Vẫn có byte nén/trailer chưa xuất | Gọi `deflate` đến `finished() == true` **trước khi** giải phóng |
| Gọi `Inflater.end()` sau một lần `inflate` | Có thể chưa nhận đủ dữ liệu gốc hoặc chưa gặp điểm kết thúc | Lặp đến `finished()`, xử lý `needsInput` / `needsDictionary` |
| `inflate()` trả `0` rồi vòng lặp chạy mãi | Không kiểm tra trạng thái không tiến triển | Kiểm tra `finished`, `needsInput`, `needsDictionary` và fail khi bế tắc |
| Có `needsInput()` nên kết luận “giải nén xong” | `needsInput` chỉ nói thiếu byte **đầu vào hiện tại** | Chỉ coi hoàn tất khi `finished()`; nếu nguồn EOF mà chưa kết thúc thì báo luồng cắt cụt |
| Gọi `flush()` thay `finish()` | Flush không bảo đảm chốt luồng nén | Dùng `finish()` hoặc `close()` của stream theo yêu cầu |
| Chỉ dùng `try/finally` cho output, quên `end()` | Đối tượng nén/giải nén do caller sở hữu có thể còn tài nguyên native | Đóng đối tượng sở hữu trong `finally` (Java 11) |
| Ghi byte nén thiếu/chưa gọi hết `deflate` | Đầu giải nén không thấy kết thúc hợp lệ | Chỉ xuất dữ liệu sau khi `Deflater.finished()` |
| Dùng `try (Deflater d = ...)` với `--release 11` | `Deflater` chỉ có `AutoCloseable` từ JDK 25 | Java 11 dùng `try/finally + end()` |
| Giải nén dữ liệu không tin cậy vào `readAllBytes()` | Có thể giải nén phình to và tốn bộ nhớ | Áp dụng giới hạn tổng số byte, bộ nhớ và tài nguyên trước khi nhận toàn bộ |
| Nhầm zlib, raw DEFLATE và GZIP | Header/trailer và định dạng không trùng nhau | Dùng cặp encode/decode có định dạng khớp; GZIP dùng `GZIPOutputStream`/`GZIPInputStream` |
| Cho rằng `reset()` dọn tài nguyên | `reset` chỉ tái sử dụng đối tượng | Kết thúc vòng đời bằng `end()` hoặc `close()` khi API hỗ trợ |

**Định dạng nén phải khớp nhau.** `new Deflater()` và `new Inflater()` dùng định dạng zlib tương ứng. Chế độ `nowrap=true` làm thay đổi kỳ vọng về header/trailer; không sử dụng một phía zlib và phía kia raw DEFLATE. Với GZIP hoặc tệp ZIP, dùng các stream/format tương ứng thay vì đưa trực tiếp toàn bộ container vào `Inflater` mặc định.

**An toàn dữ liệu giải nén:** dữ liệu nén nhỏ có thể mở rộng thành đầu ra rất lớn. Khi đầu vào không đáng tin cậy, ứng dụng cần đặt giới hạn kích thước giải nén, số lượng bản ghi/khối, thời gian và tài nguyên phù hợp. Mã ví dụ dùng `maxBytes` để minh họa giới hạn đầu ra, không phải một bộ kiểm tra an ninh đầy đủ.

## 10. Câu hỏi tự kiểm tra

**1.** Sau `deflater.finish()`, có thể gọi `deflater.end()` ngay không?  
**Đáp án:** Không nếu cần đầu ra nén hoàn chỉnh; phải tiếp tục `deflate` cho đến khi `finished()`. `end` chỉ dọn tài nguyên.

**2.** `inflater.inflate(...)` trả `0` và `needsInput() == true`. Có chắc đã giải nén xong không?  
**Đáp án:** Không. Nếu đang đọc theo luồng, cần nạp thêm byte; nếu đã EOF mà `finished()` vẫn false thì dữ liệu bị cắt cụt/chưa hoàn chỉnh.

**3.** `Inflater` có `finish()` giống `Deflater` không?  
**Đáp án:** Không. Phía giải nén dùng `finished()` để biết đã đọc tới điểm kết thúc luồng nén.

**4.** Trên Java 11, có thể đưa `Deflater` trực tiếp vào `try`-with-resources không?  
**Đáp án:** Không. `Deflater` chỉ triển khai `AutoCloseable` từ JDK 25. Java 11 dùng `try/finally` và `end()`; riêng `DeflaterOutputStream` có thể dùng `try`-with-resources.

**5.** Nếu caller tạo `Deflater` rồi truyền cho `DeflaterOutputStream`, ai chịu trách nhiệm đóng `Deflater`?  
**Đáp án:** Caller; cần `end()` sau khi wrapper stream đã đóng/hoàn tất, không giả định wrapper sở hữu compressor bên ngoài.

**6.** Tại sao cần `compressed.flip()` sau khi ghi byte nén vào `ByteBuffer`?  
**Đáp án:** Vì `position` đang ở cuối byte mới ghi; `flip()` đặt lại buffer để phần byte đó trở thành **remaining input** cho `Inflater`.

## 11. Ghi nhớ

Vòng đời đúng cần **hoàn tất dữ liệu trước**, **giải phóng tài nguyên sau**:

- **Nén:** cung cấp đầy đủ input → `Deflater.finish()` → tiếp tục `deflate` đến `finished() == true` → lấy đủ output → `end()` trong `finally`.
- **Giải nén:** cung cấp byte nén → gọi `inflate` và xử lý trạng thái → xác nhận `Inflater.finished() == true` → kiểm tra dữ liệu dư/chính sách định dạng → `end()` trong `finally`.
- **Stream:** dùng `try`-with-resources với `DeflaterOutputStream` và `InflaterInputStream`; `close()` đóng stream, còn `DeflaterOutputStream.finish()` hoàn tất dữ liệu nén mà **không đóng** stream bên dưới.
- **Phiên bản:** Java 11 cần `end()` thủ công cho `Deflater`/`Inflater`; từ JDK 25, hai đối tượng này hỗ trợ `AutoCloseable` trực tiếp. Cả hai cách đều có thể đúng nếu khớp phiên bản đích.

Không nhầm **hết input**, **đã tạo hết output**, **giải nén đến kết thúc hợp lệ** và **đã dọn tài nguyên** là một sự kiện duy nhất.

### Tài liệu chính thức

- [Java 11 — Deflater: finish, finished, deflate, end](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Deflater.html)
- [Java 11 — Inflater: inflate, finished, needsInput, needsDictionary, end](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Inflater.html)
- [Java 11 — DeflaterOutputStream: finish và close](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/DeflaterOutputStream.html)
- [Java 11 — InflaterInputStream: close và đọc giải nén](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/InflaterInputStream.html)
- [Java 25 — Deflater và AutoCloseable/close (Since 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/Deflater.html)
- [Java 25 — Inflater và AutoCloseable/close (Since 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/Inflater.html)
