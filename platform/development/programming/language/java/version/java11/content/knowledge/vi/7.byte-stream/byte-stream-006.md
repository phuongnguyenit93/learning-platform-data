# OutputStream.nullOutputStream và đích bỏ dữ liệu (Java 11+)

**Chủ đề: Byte stream.** `OutputStream` là lớp trừu tượng cho các đích nhận byte trong Java: bộ nhớ, tệp, kết nối mạng hoặc một đích đặc biệt. Từ Java 11, `OutputStream.nullOutputStream()` tạo một **đích nhận và bỏ toàn bộ byte ghi vào**, phù hợp khi API yêu cầu `OutputStream` nhưng chương trình không cần lưu kết quả. Đây là API chính thức của JDK và vẫn tồn tại trong Java hiện đại.

Bài học tập trung vào hợp đồng byte stream, hành vi `write/flush/close`, cách dùng với `InputStream.transferTo`, so sánh với đích lưu trữ, xử lý bộ đệm, tình huống thực tế và kiểm thử. Các chương trình độc lập bên dưới tương thích Java 11 trở lên.

## 1. Khái niệm “đích bỏ dữ liệu”

Ví dụ một phương thức:

```java
void exportData(OutputStream destination) throws IOException
```

Đây là **chữ ký minh họa**. Hàm `exportData` có thể ghi byte mà không biết đích là tệp, bộ nhớ hay một bộ nhận không lưu dữ liệu. Nếu chỉ cần chạy quá trình export mà bỏ sản phẩm, truyền:

```java
try (OutputStream sink = OutputStream.nullOutputStream()) {
    exportData(sink);
}
```

Đoạn minh họa giả định đã có `exportData` và import `java.io.OutputStream`.

Đích này thường được gọi là **null sink** hoặc **discard sink**. Hãy phân biệt:

- `OutputStream.nullOutputStream()` trả về **một đối tượng OutputStream thực**, được phép gọi `write(...)` khi còn mở.
- `OutputStream destination = null;` chỉ là một **tham chiếu null**; gọi `destination.write(...)` sẽ gây `NullPointerException`.
- Null sink **không lưu byte để đọc lại**, không có phương thức như `toByteArray()` và không tạo file hay bản ghi đích.
- Các thao tác ở **phía trước sink** vẫn xảy ra: đọc nguồn, tính toán, mã hóa, tạo buffer, ghi log, tính digest. Bỏ byte ở cuối pipeline không đồng nghĩa bỏ công việc tạo byte.

Mỗi lời gọi `OutputStream.nullOutputStream()` tạo một stream mới. Vì vậy việc đóng một stream không tự đóng stream khác được tạo từ một lời gọi độc lập.

## 2. API, vòng đời và quy tắc chính xác

Chữ ký được thêm vào Java 11:

```java
public static OutputStream nullOutputStream()
```

Không cần thư viện bên ngoài; chỉ cần `java.io.OutputStream`. Stream trả về **ban đầu đang mở**.

| Phương thức | Khi stream đang mở | Sau khi `close()` |
| --- | --- | --- |
| `write(int b)` | Nhận rồi bỏ một byte | Ném `IOException` |
| `write(byte[] b)` | Nhận rồi bỏ các byte trong mảng | Ném `IOException` |
| `write(byte[] b, int off, int len)` | Nhận rồi bỏ đoạn byte được chọn | Ném `IOException` |
| `flush()` | Không làm gì | **Vẫn không làm gì** |
| `close()` | Đóng stream | Gọi tiếp không có tác dụng |

Quy tắc `IOException` ở bảng dành cho **lời gọi write với tham số hợp lệ**. Không dùng bảng để suy đoán thứ tự ưu tiên ngoại lệ khi đồng thời truyền mảng null/vùng chỉ số sai vào một stream đã đóng.

`write(byte[])` nhận một mảng byte; `write(b, off, len)` nhận vùng bắt đầu tại chỉ số `off` với độ dài `len`. Theo hợp đồng `OutputStream`, mảng `null` là tham số sai và các vùng `off/len` vượt mảng là lỗi; việc sink bỏ byte **không biến tham số sai thành dữ liệu hợp lệ**.

**Điểm đặc biệt cần nhớ:** Javadoc của `OutputStream.nullOutputStream()` quy định `flush()` không làm gì ngay cả sau khi stream đóng. Đây là hợp đồng của **null sink**, không phải kết luận cho mọi `OutputStream` hay mọi wrapper.

## 3. Ví dụ cơ bản: các overload write

Tệp **`NullSinkBasics.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;

public class NullSinkBasics {
    public static void main(String[] args) throws IOException {
        byte[] payload = {10, 20, 30, 40};

        try (OutputStream sink = OutputStream.nullOutputStream()) {
            sink.write(65);
            sink.write(payload);
            sink.write(payload, 1, 2);
            sink.flush();
            System.out.println("Writes completed");
        }

        System.out.println("No output bytes retained");
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên:

```bash
javac --release 11 -encoding UTF-8 NullSinkBasics.java
java NullSinkBasics
```

Stdout:

```text
Writes completed
No output bytes retained
```

`write(65)` cung cấp byte giá trị 65; `write(payload)` cung cấp bốn byte; `write(payload, 1, 2)` cung cấp byte 20 và 30. Mọi byte đều bị bỏ khi đến `sink`. Hai dòng stdout xuất hiện vì `System.out` là stream khác đang hướng tới console, **không phải** vì null sink đã giữ hay in payload.

Theo hợp đồng chung của `OutputStream.write(int)`, chỉ tám bit thấp của đối số `int` được dùng làm byte đầu ra. Với null sink, byte đó không được lưu nên không có cách nào đọc lại hay xác minh bằng dữ liệu đầu ra.

## 4. So sánh với các OutputStream lưu dữ liệu

| Loại đích | Dữ liệu có được giữ không? | Tình huống phù hợp |
| --- | --- | --- |
| `OutputStream.nullOutputStream()` | Không | Chạy một đường ghi nhưng bỏ kết quả |
| `ByteArrayOutputStream` | Có, trong bộ nhớ | Cần kiểm tra hoặc lấy byte để xử lý tiếp |
| `FileOutputStream` | Có, tại đích tệp | Cần tạo/cập nhật file theo hợp đồng |

`ByteArrayOutputStream` có thể cấp phát/thay đổi vùng nhớ để lưu payload. Nếu chỉ muốn vứt payload, dùng nó rồi bỏ `toByteArray()` gây sử dụng bộ nhớ không cần thiết.

### Một hàm export, hai đích

Tệp **`SinkComparison.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class SinkComparison {
    static void export(OutputStream out) throws IOException {
        out.write("Java 11".getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        export(memory);

        try (OutputStream discard = OutputStream.nullOutputStream()) {
            export(discard);
        }

        System.out.println("retained: "
                + new String(memory.toByteArray(), StandardCharsets.UTF_8));
        System.out.println("retained byte count: " + memory.size());
        System.out.println("discarded: no stored bytes");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 SinkComparison.java
java SinkComparison
```

```text
retained: Java 11
retained byte count: 7
discarded: no stored bytes
```

`export` không cần biết stream được cấp là loại nào. Với `memory`, bảy byte UTF-8 được lưu và có thể đọc lại; với `discard`, chúng bị bỏ. Câu “discarded” là thông báo mô tả hợp đồng sink, không phải kết quả từ phương thức quan sát nội bộ null sink.

**Kiểm thử nội dung:** Nếu mục tiêu là chứng minh serializer tạo JSON, CSV hoặc binary payload **đúng từng byte**, hãy dùng `ByteArrayOutputStream` và so sánh kết quả. Ghi thành công vào null sink **không chứng minh** byte được tạo đúng.

## 5. Đọc hết nguồn và bỏ byte bằng InputStream.transferTo

`InputStream.transferTo(OutputStream)` có từ Java 9 và vẫn áp dụng với Java 11+. Nó đọc byte từ nguồn cho tới cuối và chuyển các byte đã đọc đến OutputStream. Nếu mọi thao tác thành công, kết quả trả về là **số byte được chuyển**, dù sink không lưu nội dung.

Đoạn minh họa trong phương thức có biến `source` kiểu `InputStream`:

```java
long numberOfBytes = source.transferTo(OutputStream.nullOutputStream());
```

Nên dùng `try-with-resources` nếu phương thức sở hữu nguồn/đích. Không nhầm số byte truyền với số ký tự Unicode.

### Ví dụ chạy độc lập: TransferToDiscard.java

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class TransferToDiscard {
    public static void main(String[] args) throws IOException {
        String text = "A\u00E9B";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

        try (InputStream source = new ByteArrayInputStream(encoded);
             OutputStream sink = OutputStream.nullOutputStream()) {
            long transferred = source.transferTo(sink);

            System.out.println("UTF-16 units: " + text.length());
            System.out.println("UTF-8 bytes: " + encoded.length);
            System.out.println("transferred: " + transferred);
            System.out.println("remaining: " + source.available());
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 TransferToDiscard.java
java TransferToDiscard
```

```text
UTF-16 units: 3
UTF-8 bytes: 4
transferred: 4
remaining: 0
```

Chữ `é` (U+00E9) chiếm 2 byte UTF-8, còn `A` và `B` mỗi ký tự 1 byte: tổng 4 byte. `transferTo` phản ánh số **byte thực sự đã chuyển**, không phải số ký tự. `source.available() == 0` ở đây đúng vì nguồn là `ByteArrayInputStream` đã hết dữ liệu; với InputStream bất kỳ, `available()==0` không nhất thiết chứng minh EOF.

**Điều vẫn xảy ra:** hệ thống vẫn đọc nguồn, cấp phát bộ đệm (tùy cách triển khai), và có thể gặp `IOException` ở nguồn. Null sink chỉ bỏ byte ở **đích**; nó không làm cho quá trình đọc trở nên miễn phí.

Nếu đã có `byte[] data` và chỉ cần biết độ dài, `data.length` đơn giản và trực tiếp hơn việc tạo `ByteArrayInputStream` rồi truyền đến null sink.

## 6. Dùng làm đích cuối cho một pipeline xử lý byte

Trong một pipeline, dữ liệu có thể được xử lý ở **wrapper** trước khi đến null sink. Ví dụ `DigestOutputStream` cập nhật `MessageDigest` từ các byte được ghi, sau đó chuyển tiếp byte đến đích ở dưới.

Tệp **`DigestWithoutStorage.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class DigestWithoutStorage {
    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (OutputStream out = new DigestOutputStream(
                OutputStream.nullOutputStream(), digest)) {
            out.write("Java".getBytes(StandardCharsets.UTF_8));
        }

        byte[] hash = digest.digest();
        System.out.println("SHA-256 bytes: " + hash.length);
        System.out.println("Output stored in null sink: false");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 DigestWithoutStorage.java
java DigestWithoutStorage
```

```text
SHA-256 bytes: 32
Output stored in null sink: false
```

`SHA-256` có digest dài 32 byte, và wrapper tính nó trong lúc byte chạy qua. Null sink không tự tính checksum; vai trò của nó chỉ là bỏ các byte sau wrapper. Nếu dữ liệu đã có ở dạng mảng byte, `digest.update(bytes)` trực tiếp thường đơn giản hơn. Ví dụ stream hữu ích hơn khi code tạo dữ liệu chỉ cho phép cung cấp `OutputStream`.

Nếu đặt `BufferedOutputStream` ở trước null sink, wrapper đó vẫn có thể đệm byte tạm trong bộ nhớ. Vì thế “null sink không lưu dữ liệu” là sự thật **về đích cuối**, không phải bảo đảm rằng toàn bộ pipeline không dùng bộ đệm hoặc không cấp phát bộ nhớ.

## 7. Lifecycle: close và IOException

Null sink đang mở sau khi được tạo. `close()` đóng nó; gọi `close()` lần nữa không có tác dụng. Sau khi đóng, **các lệnh write với tham số hợp lệ ném IOException**. Riêng `flush()` vẫn không làm gì kể cả khi đóng.

Tệp **`NullSinkLifecycle.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;

public class NullSinkLifecycle {
    public static void main(String[] args) throws IOException {
        OutputStream sink = OutputStream.nullOutputStream();

        sink.write(1);
        sink.write(new byte[] {2, 3});
        sink.flush();

        sink.close();
        sink.close();
        sink.flush();

        try {
            sink.write(4);
            System.out.println("unexpected");
        } catch (IOException expected) {
            System.out.println("write(int) after close: IOException");
        }

        try {
            sink.write(new byte[] {5, 6});
            System.out.println("unexpected");
        } catch (IOException expected) {
            System.out.println("write(byte[]) after close: IOException");
        }

        try {
            sink.write(new byte[] {7, 8}, 0, 2);
            System.out.println("unexpected");
        } catch (IOException expected) {
            System.out.println("write(range) after close: IOException");
        }

        System.out.println("repeated close and flush: OK");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NullSinkLifecycle.java
java NullSinkLifecycle
```

```text
write(int) after close: IOException
write(byte[]) after close: IOException
write(range) after close: IOException
repeated close and flush: OK
```

Hãy ưu tiên `try-with-resources` khi tạo stream trong một scope, ngay cả khi null sink không mở tài nguyên tệp. Nếu một wrapper nằm phía trên sink, hành vi đóng của **wrapper** phải được xét theo hợp đồng wrapper; không suy diễn quy tắc `flush()` của null sink cho tất cả stream.

Một hàm được truyền OutputStream từ bên ngoài thường không tự đóng stream trừ khi hợp đồng sở hữu tài nguyên yêu cầu. Ngược lại, nơi tạo stream thường nên chịu trách nhiệm đóng nó.

## 8. Tham số không hợp lệ: byte bị bỏ không có nghĩa lỗi bị bỏ

`write(byte[] b)` và `write(byte[] b, int off, int len)` yêu cầu tham số hợp lệ. Theo hợp đồng chung:

- `b == null` là lỗi `NullPointerException`.
- `off < 0`, `len < 0` hoặc đoạn `off/len` ra ngoài mảng là lỗi `IndexOutOfBoundsException`.
- `len == 0` là một đoạn rỗng hợp lệ nếu `off` nằm trong phạm vi hợp lệ.
- Sau `close()`, một lệnh ghi **hợp lệ về tham số** vào null sink phải ném `IOException`.

Khi nhiều điều kiện lỗi cùng đúng (chẳng hạn stream đã đóng và mảng lại null), **đừng viết logic phụ thuộc loại lỗi được báo trước** mà không có hợp đồng cụ thể. Cách kiểm thử rõ nhất là tách nhóm input sai ra khỏi nhóm trạng thái đóng.

`OutputStream.nullOutputStream()` là một đối tượng thật. Nếu truyền tham chiếu `null` vào API nhận OutputStream, API có thể ném NPE theo hợp đồng của nó; điều đó hoàn toàn khác với việc truyền null sink hợp lệ.

## 9. Khi nào nên dùng, khi nào không?

**Dùng null sink khi:**

1. Một API sản sinh byte bắt buộc cần OutputStream, nhưng bạn chỉ muốn chạy code mà **không giữ sản phẩm**.
2. Bạn muốn tiêu thụ dữ liệu từ InputStream qua `transferTo`, đồng thời không cần lưu byte ở đích.
3. Một wrapper tạo tác dụng có ích, chẳng hạn tính digest/checksum, còn output payload cuối cùng không cần thiết.
4. Bạn muốn tiêm một đích theo môi trường hoặc chế độ chạy vào cùng một hàm xuất dữ liệu.

**Không dùng null sink để:**

- Kiểm tra **đúng/sai của payload** xuất ra: dùng `ByteArrayOutputStream` hoặc sink có khả năng quan sát byte.
- Ghi dữ liệu mà người dùng cần truy xuất sau này: null sink không có file/byte array để khôi phục.
- Đánh giá tốc độ ghi ổ đĩa hoặc mạng: null sink không có chi phí I/O của đích thật.
- Giả định lỗi upstream biến mất: serializer, nguồn đọc, bộ mã hóa, checksum hoặc wrapper vẫn có thể lỗi.
- Khẳng định dữ liệu nhạy cảm không bao giờ xuất hiện trong bộ nhớ/log: bỏ payload ở đích không xóa các bản sao đã được tạo ở trước nó.

Tránh đổi `System.out` toàn cục thành `PrintStream(OutputStream.nullOutputStream())` chỉ để “ẩn log” trong ứng dụng chung: việc này có thể che mất thông tin chẩn đoán của các phần khác. Dùng dependency injection hoặc truyền sink vào đúng hàm cần bỏ dữ liệu.

### Khác biệt với API gần tên

- `InputStream.nullInputStream()`, cũng có từ Java 11, là **nguồn đọc rỗng** (gặp EOF), không phải sink nhận byte.
- `Writer.nullWriter()` là **đích bỏ ký tự** ở tầng `Writer`, trong khi `OutputStream.nullOutputStream()` bỏ **byte**. Khi chuyển chuỗi thành byte, hãy chọn charset tường minh như `StandardCharsets.UTF_8`.
- `ByteArrayOutputStream` lưu byte; `FileOutputStream` ghi tệp. Không có API `read()` trên một OutputStream chỉ ghi.

## 10. Bộ regression test thực thi được

Chúng ta cần kiểm tra cả **đường mở**, **đường đóng**, **tham số sai** và **InputStream.transferTo**. Không nên chỉ kiểm tra rằng “không có file xuất hiện”: điều đó không chứng minh đúng quy tắc đóng hay ném exception.

Ví dụ sau dùng `AssertionError` trực tiếp. Lý do: câu lệnh `assert` của Java có thể không chạy nếu JVM không bật `-ea`.

Tệp **`NullOutputStreamRegression.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class NullOutputStreamRegression {
    private static int checks = 0;

    private static void check(String name, boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    @FunctionalInterface
    interface IoAction {
        void run() throws IOException;
    }

    private static void expectIOException(String name, IoAction action) {
        boolean thrown = false;
        try {
            action.run();
        } catch (IOException expected) {
            thrown = true;
        }
        check(name, thrown);
    }

    public static void main(String[] args) throws IOException {
        OutputStream sink = OutputStream.nullOutputStream();
        byte[] input = {1, 2, 3, 4};

        sink.write(255);
        sink.write(input);
        sink.write(input, 1, 2);
        sink.write(input, input.length, 0);
        sink.flush();
        check("writes while open", true);

        boolean nullRejected = false;
        try {
            sink.write((byte[]) null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check("null array rejected", nullRejected);

        boolean rangeRejected = false;
        try {
            sink.write(input, 3, 2);
        } catch (IndexOutOfBoundsException expected) {
            rangeRejected = true;
        }
        check("invalid range rejected", rangeRejected);

        sink.close();
        sink.close();
        sink.flush();
        check("close and flush", true);

        expectIOException("closed write(int)", () -> sink.write(1));
        expectIOException("closed write(byte[])", () -> sink.write(input));
        expectIOException("closed write(range)", () -> sink.write(input, 0, 2));

        byte[] bytes = "Java".getBytes(StandardCharsets.UTF_8);
        try (ByteArrayInputStream source = new ByteArrayInputStream(bytes);
             OutputStream discard = OutputStream.nullOutputStream()) {
            long amount = source.transferTo(discard);
            check("transferred count", amount == bytes.length);
            check("source consumed", source.available() == 0);
        }

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NullOutputStreamRegression.java
java NullOutputStreamRegression
```

```text
PASS: 9 checks
```

Số kiểm tra: một nhóm write khi mở, một null array, một sai range, một close/flush, ba write sau đóng và hai kiểm tra transfer = **9**. Nếu có lỗi, chương trình ném `AssertionError` kèm tên điều kiện. Trong dự án thực tế, có thể chuyển các trường hợp thành JUnit tests, bổ sung nguồn có lỗi I/O và wrapper cụ thể của ứng dụng.

| Trường hợp | Kỳ vọng |
| --- | --- |
| `write(int)`, `write(byte[])`, `write(range)` khi mở | Chấp nhận byte, không lưu kết quả |
| `write(byte[])` với mảng null khi mở | `NullPointerException` |
| `write(range)` với offset/length sai khi mở | `IndexOutOfBoundsException` |
| `close()` nhiều lần | Không lỗi |
| `flush()` sau `close()` | Không làm gì |
| Các `write` hợp lệ sau đóng | `IOException` |
| `transferTo` từ ByteArrayInputStream | Byte count chính xác, nguồn được đọc hết |

## 11. Câu hỏi củng cố

**1.** `OutputStream.nullOutputStream().write(65)` có in `A` ra console không?

**2.** Sau `sink.close()`, `sink.flush()` và `sink.write(1)` có cùng kết quả không?

**3.** Với nguồn `ByteArrayInputStream` chứa 100 byte, `source.transferTo(OutputStream.nullOutputStream())` có luôn trả 0 chỉ vì đích bỏ dữ liệu không?

**4.** Muốn kiểm thử một serializer có xuất đúng từng byte, ta nên dùng loại sink nào?

**5.** `OutputStream.nullOutputStream()` có giống tham chiếu `null` không?

**6.** Bọc null sink trong `BufferedOutputStream` có bảo đảm cả pipeline không dùng bộ nhớ đệm không?

**Đáp án:** 1. Không, byte bị bỏ và console là một stream khác. 2. Không: `flush()` no-op nhưng `write` sau đóng ném `IOException`. 3. Không: nếu truyền hết nguồn thành công, phương thức trả 100 vì đếm số byte đã chuyển. 4. `ByteArrayOutputStream` hoặc test sink cho phép so sánh byte. 5. Không: null sink là một đối tượng OutputStream hợp lệ. 6. Không: wrapper vẫn có thể cấp phát buffer dù đích cuối bỏ dữ liệu.

## Tài liệu tham khảo chính thức

- [Java 11 — OutputStream.nullOutputStream, write, flush, close](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/OutputStream.html).
- [Java 25 — OutputStream.nullOutputStream (API vẫn tồn tại)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStream.html).
- [Java 11 — InputStream.transferTo và nullInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html).
- [Java 11 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/ByteArrayOutputStream.html).
- [Java 11 — DigestOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/DigestOutputStream.html).
- [Java 11 — Writer.nullWriter](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/Writer.html).
