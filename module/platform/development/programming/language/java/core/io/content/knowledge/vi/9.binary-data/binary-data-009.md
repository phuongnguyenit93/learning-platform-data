# Kiểm tra độ dài trước khi cấp phát hoặc đọc dữ liệu nhị phân trong Java

## 1. Vì sao kiểm tra độ dài là bước bắt buộc?

Khi chương trình Java đọc dữ liệu nhị phân từ file, socket, gói tin hoặc luồng được xây dựng từ đầu vào bên ngoài, nó có thể gặp một **trường độ dài** (length prefix) cho biết cần đọc bao nhiêu byte. Nếu ứng dụng tin ngay giá trị này rồi gọi `new byte[length]` hoặc `readNBytes(length)`, một giá trị sai hoặc cố ý quá lớn có thể dẫn tới sử dụng quá nhiều bộ nhớ, lỗi cấp phát, chờ dữ liệu vô hạn, ghi thiếu dữ liệu hoặc làm cạn tài nguyên.

Quy tắc trung tâm là:

> **Xác định giới hạn tin cậy, kiểm tra số lượng trước khi cấp phát và đọc, sau đó xác minh số byte thực nhận.** Với nguồn không biết trước độ dài, sử dụng cách đọc theo khối và hạn mức tích lũy.

Đây là bài học về **dữ liệu nhị phân** trong Java Core I/O. Các kỹ thuật áp dụng cho `InputStream`, `DataInputStream`, `ByteBuffer`, `FileChannel` và định dạng có cấu trúc; không nên nhầm kích thước byte với số ký tự trong văn bản.

Sau bài học, bạn có thể:

- Phân biệt **độ dài công bố** và **số byte thật sự nhận được**, cùng đơn vị đo của trường độ dài.
- Kiểm tra số âm, số 0, giá trị vượt ngưỡng, sai phiên bản định dạng và phép tính độ dài bị tràn.
- Đọc đủ một frame nhị phân bằng `DataInputStream.readFully` với giới hạn cấp phát rõ ràng.
- Xử lý trường hợp EOF đến sớm, nguồn không phát EOF, lỗi I/O và dữ liệu dư.
- Giới hạn dữ liệu khi không có length-prefix bằng vòng lặp streaming với bộ đệm nhỏ.
- Nhận ra khi nào `Files.size`, `available()`, `readAllBytes()` và `readNBytes(int)` không phù hợp làm biện pháp bảo vệ.
- Áp dụng hạn mức theo **byte trên wire**, số phần tử, kích thước đã giải nén và ngân sách bộ nhớ ở những tầng tương ứng.

## 2. Mô hình một frame nhị phân có trường độ dài

Một định dạng đơn giản có thể gồm:

```text
+----------------------+----------------------+
| 4-byte payloadLength | payloadLength bytes  |
+----------------------+----------------------+
         header                 payload
```

Ví dụ giả định 4 byte đầu biểu diễn số nguyên `int` **có dấu, big-endian** theo `DataInputStream.readInt()`. Khi header là `00 00 00 03`, ứng dụng phải nhận đúng ba byte payload tiếp theo.

Nhưng một header nhận từ bên ngoài **không phải sự thật đã được xác minh**. Các tình huống có thể xảy ra:

| Header công bố | Payload thực nhận | Ý nghĩa và cách xử lý |
| --- | --- | --- |
| 3 byte | 3 byte | Hợp lệ về độ dài nếu giá trị không vượt ngưỡng và nội dung đáp ứng định dạng |
| 0 byte | 0 byte | Có thể hợp lệ nếu giao thức cho phép payload rỗng |
| -1 byte | Bất kỳ | Giá trị âm không hợp lệ với độ dài byte |
| 2.147.483.647 byte | Ít byte | Không cấp phát mảng cực lớn; từ chối nếu vượt ngân sách |
| 100 byte | 20 byte rồi EOF | **Truncated frame**: dữ liệu bị thiếu, phải báo lỗi |
| 3 byte | 5 byte còn trong luồng | Một frame tiêu thụ 3 byte; 2 byte dư có thể là frame tiếp theo hoặc dữ liệu không hợp lệ tùy giao thức |
| 3 byte | 3 byte nhưng checksum sai | Đủ độ dài vẫn chưa chứng minh nội dung đúng hoặc toàn vẹn |

**Tách biệt ba việc**: (1) header nằm trong miền giá trị hợp lệ, (2) nguồn thực sự cung cấp đủ byte, (3) dữ liệu đáp ứng các kiểm tra cú pháp/kiểu/độ toàn vẹn. Chỉ vượt qua một bước không thay thế hai bước còn lại.

### 2.1. Đơn vị đo: byte, phần tử hay ký tự?

Các định dạng có thể dùng những kiểu “độ dài” khác nhau:

- **Số byte payload**: ứng dụng có thể dùng trực tiếp làm kích thước bộ đệm byte *sau khi kiểm tra*.
- **Số phần tử**: nếu mỗi bản ghi chiếm `elementSize` byte, tổng byte là `count × elementSize`; phải kiểm tra tràn trước khi cấp phát.
- **Số ký tự**: độ dài theo Unicode code point, UTF-16 `char` hoặc số byte UTF-8 có thể khác nhau; không tự quy đổi 1 ký tự = 1 byte.
- **Tổng chiều dài frame**: có giao thức tính cả header, có giao thức chỉ tính payload. Đọc sai hợp đồng này sẽ lệch ranh giới frame.
- **Độ dài chưa nén hoặc đã nén**: hai giá trị có thể khác rất xa; hạn mức chỉ trên input nén không ngăn được dữ liệu giải nén phình lớn.

Trước khi viết code, hãy ghi rõ hợp đồng: header dài bao nhiêu byte, signed/unsigned, endian, đơn vị, có tính header không, giá trị 0 có hợp lệ không, kích thước tối đa cho phép và phản ứng khi dữ liệu thiếu/dư.

## 3. Kiểm tra trước `new byte[length]`

Mã nguy hiểm:

```java
// Minh họa kiểu code KHÔNG AN TOÀN:
// InputStream/dataInput và giao thức chưa được kiểm soát.
int length = dataInput.readInt();
byte[] payload = new byte[length];
dataInput.readFully(payload);
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; biến `dataInput` giả định là `DataInputStream` hợp lệ. Lỗi nằm ở thứ tự tin tưởng vào `length`:

- `length < 0` có thể gây `NegativeArraySizeException` khi tạo mảng.
- Giá trị cực lớn có thể gây `OutOfMemoryError` hoặc làm cạn heap trước khi đọc được payload.
- Nếu ứng dụng đọc từ mạng và đối tác công bố độ dài lớn nhưng chỉ gửi vài byte, chương trình có thể giữ bộ nhớ lớn trong khi chờ.
- `readFully` báo lỗi khi dữ liệu bị cắt ngắn, nhưng kiểm tra này diễn ra **sau** cấp phát; vì vậy không đủ để bảo vệ tài nguyên.

Mẫu an toàn hơn:

```java
int length = dataInput.readInt();

if (length < 0 || length > MAX_PAYLOAD_BYTES) {
    throw new IOException("Invalid payload length: " + length);
}
byte[] payload = new byte[length];
dataInput.readFully(payload);
```

Đây cũng là **đoạn minh họa**; `MAX_PAYLOAD_BYTES` phải là hằng số/chính sách đã xác định, `dataInput` là nguồn hợp lệ. Với dữ liệu rỗng, quyết định có chấp nhận `length == 0` hay không phụ thuộc định dạng.

**Điểm cốt lõi:** Giới hạn tối đa phải đến từ yêu cầu hệ thống và ngân sách tài nguyên, chứ không dựa vào giá trị “tối đa mà Java cho phép” hoặc con số kẻ gửi tự công bố.

### 3.1. Chọn ngân sách cấp phát

Một giới hạn per-frame cần xét:

1. **Loại dữ liệu:** ảnh thumbnail, metadata 1 KiB và ảnh gốc hàng trăm MiB có nhu cầu khác nhau.
2. **Số request đồng thời:** 1.000 request đều cấp phát 8 MiB đã tương ứng khoảng 8.000 MiB payload tạm, chưa gồm object/GC/buffer khác.
3. **Số bản ghi trong một request:** mỗi frame 1 MiB có thể hợp lệ nhưng 100.000 frame liên tiếp không thể đọc toàn bộ vào RAM.
4. **Kích thước kết quả đã xử lý:** dữ liệu giải nén, chuyển mã, cấu trúc đối tượng hoặc danh sách phần tử có thể lớn hơn byte input.
5. **Độ trễ và tốc độ nguồn:** một request có thể giữ vùng nhớ lâu nếu mạng chậm; cần timeout và quota tổng thời gian.
6. **Đầu ra:** nếu ghi vào `ByteArrayOutputStream` hoặc gom payload vào `List<byte[]>`, bộ nhớ tăng theo tổng dữ liệu, dù từng frame nhỏ.

Đặt giới hạn per-frame, per-request và đồng thời theo **ba tầng khác nhau** khi hệ thống cần bảo vệ toàn cục. Giới hạn `int`/kích thước mảng Java chỉ là ranh giới kỹ thuật, không phải ngân sách vận hành hợp lý.

## 4. Ví dụ Java 17+ hoàn chỉnh: đọc frame có giới hạn và nhận biết EOF sớm

Chương trình dưới đây dùng `DataInputStream` để đọc **4 byte length prefix big-endian** rồi kiểm tra giới hạn `1.024 byte` **trước** khi tạo mảng. `readFully` bảo đảm hoặc đọc đủ payload hoặc ném `EOFException`.

Lưu thành **`SafeFrameDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class SafeFrameDemo {
    private static final int MAX_PAYLOAD_BYTES = 1024;

    static byte[] readFrame(InputStream source) throws IOException {
        // Caller owns source and closes it when finished.
        DataInputStream input = new DataInputStream(source);

        int declaredLength = input.readInt();
        if (declaredLength < 0
                || declaredLength > MAX_PAYLOAD_BYTES) {
            throw new IOException(
                    "Invalid frame length: " + declaredLength);
        }

        byte[] payload = new byte[declaredLength];
        input.readFully(payload);
        return payload;
    }

    static byte[] makeFrame(int announcedLength, byte[] actualPayload)
            throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(buffer)) {
            output.writeInt(announcedLength);
            output.write(actualPayload);
        }
        return buffer.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] valid = makeFrame(3, new byte[] {10, 20, 30});
        try (InputStream input = new ByteArrayInputStream(valid)) {
            System.out.println(
                    "Valid: " + Arrays.toString(readFrame(input)));
        }

        byte[] tooLarge = makeFrame(2048, new byte[0]);
        try (InputStream input = new ByteArrayInputStream(tooLarge)) {
            try {
                readFrame(input);
            } catch (IOException error) {
                System.out.println("Rejected: " + error.getMessage());
            }
        }

        byte[] truncated = makeFrame(3, new byte[] {10});
        try (InputStream input = new ByteArrayInputStream(truncated)) {
            try {
                readFrame(input);
            } catch (EOFException error) {
                System.out.println("Truncated: "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 SafeFrameDemo.java
java SafeFrameDemo
```

**Stdout chính xác:**

```text
Valid: [10, 20, 30]
Rejected: Invalid frame length: 2048
Truncated: EOFException
```

**Giải thích từng trường hợp:**

- **Valid:** header cho biết 3 byte; giới hạn cho phép 3, mảng 3 byte được tạo, `readFully` nhận đúng ba byte và in ra theo thứ tự.
- **Rejected:** header công bố `2048 > 1024`. Chương trình báo lỗi ngay khi đọc header, **chưa cấp phát mảng payload lớn và chưa cố đọc phần payload**.
- **Truncated:** header hợp lệ công bố 3 byte, nguồn chỉ có 1 byte. `readFully` ném `EOFException` thay vì trả một mảng “đủ dài” nhưng chứa phần còn lại là zero.
- **Vòng đời:** các `ByteArrayInputStream` được đóng trong `try-with-resources` của mã gọi. `readFrame` tạo wrapper `DataInputStream` nhưng không đóng nguồn vì caller sở hữu `InputStream`; với luồng dùng chung nhiều frame, wrapper có thể được tạo một lần và quản lý chung ở tầng caller.

### 4.1. Giới hạn ví dụ

Chương trình trên kiểm tra **một frame** theo định dạng đơn giản. Khi xử lý nhiều frame nối tiếp, nó chưa giới hạn tổng số frame và tổng byte trên kết nối. Header hoặc payload còn có thể chứa checksum, magic number, phiên bản, kiểu dữ liệu và ràng buộc nội dung cần được kiểm tra riêng.

`readFrame` không đọc thêm byte để “kiểm tra EOF toàn luồng” vì trong giao thức gồm nhiều frame, byte còn lại có thể chính là header của frame kế. Nếu giao thức quy định **chỉ một frame duy nhất**, tầng gọi cần kiểm tra có trailing data và quyết định xử lý. Với stream mạng mở lâu, đọc thêm để chờ EOF có thể block; không thể kiểm tra trailing data bằng cách chờ vô hạn một cách máy móc.

## 5. Khi chưa biết tổng chiều dài: đọc streaming với hạn mức

Có loại nguồn không cung cấp size đáng tin: stream từ socket, HTTP body chunked, một số định dạng nén hoặc nguồn sinh dữ liệu theo thời gian. Nếu gọi `readAllBytes()`, `ByteArrayOutputStream` không giới hạn hoặc `transferTo` sang đích không giới hạn, chương trình có thể tiêu thụ tài nguyên rất lớn.

Cách xử lý là:

1. Đặt **giới hạn tối đa tổng byte** theo nghiệp vụ, ví dụ `MAX_BYTES`.
2. Sử dụng bộ đệm nhỏ và chỉ yêu cầu đọc tối đa **số byte còn được phép**.
3. Cập nhật bộ đếm sau mỗi lần đọc thành công; không nhầm `read() == -1` với dữ liệu rỗng.
4. Khi đạt đúng hạn mức, xác định nguồn đã kết thúc hay còn byte. Nếu còn byte, báo lỗi vượt hạn mức; không báo thành công với kết quả cắt cụt nếu giao thức yêu cầu toàn bộ.
5. Nếu đang ghi file có giá trị nghiệp vụ, dùng **file tạm**, dọn khi lỗi và chỉ công bố khi toàn bộ quá trình đã thành công.

### 5.1. Ví dụ Java 17+ có giới hạn tích lũy

Lưu thành **`BoundedBinaryCopyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class BoundedBinaryCopyDemo {
    static long copyWithLimit(
            InputStream input, OutputStream output, long maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be nonnegative");
        }

        byte[] buffer = new byte[4096];
        long copied = 0;

        while (true) {
            long remaining = maxBytes - copied;

            if (remaining == 0) {
                // One extra read distinguishes exact size from overflow.
                if (input.read() != -1) {
                    throw new IOException(
                            "Limit exceeded: " + maxBytes);
                }
                return copied;
            }

            int requested = (int) Math.min(
                    (long) buffer.length, remaining);
            int count = input.read(buffer, 0, requested);

            if (count == -1) {
                return copied;
            }
            if (count == 0) {
                throw new IOException("Input made no progress");
            }

            output.write(buffer, 0, count);
            copied += count;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] source = {10, 20, 30, 40, 50};

        try (InputStream input = new ByteArrayInputStream(source);
             ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            System.out.println("Allowed: "
                    + copyWithLimit(input, output, 5));
        }

        try (InputStream input = new ByteArrayInputStream(source);
             ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            try {
                copyWithLimit(input, output, 4);
            } catch (IOException error) {
                System.out.println("Rejected: " + error.getMessage());
            }
            System.out.println("Partial bytes: " + output.size());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BoundedBinaryCopyDemo.java
java BoundedBinaryCopyDemo
```

**Stdout chính xác:**

```text
Allowed: 5
Rejected: Limit exceeded: 4
Partial bytes: 4
```

**Phân tích:**

- Trường hợp giới hạn bằng 5: sao chép đủ 5 byte. Lần đọc thử tiếp theo trả EOF nên kết quả là 5.
- Trường hợp giới hạn bằng 4: chỉ bốn byte đầu được ghi. Lần đọc thử sau đó tìm thấy byte thứ năm và ném `IOException`, không trả kết quả thành công.
- Đích `ByteArrayOutputStream` vẫn giữ **4 byte đã ghi trước lỗi**. Không có rollback tự động. Với dữ liệu thực, không công bố output dở; dùng tệp tạm hoặc cơ chế transaction phù hợp.
- Bước đọc thêm một byte để xác định vượt hạn mức **có thể block** nếu nguồn chưa phát EOF. Với socket hoặc nguồn vô hạn, phải cấu hình deadline, timeout hay cancellation ở tầng nguồn. Một số giao thức có length-prefix đáng tin sau khi đã kiểm tra và không cần chờ EOF toàn kết nối.
- Ví dụ dùng `ByteArrayOutputStream` vì chỉ có 5 byte. Trong hệ thống thực, output phải là sink giới hạn/streaming nếu dữ liệu lớn; buffer 4 KiB **không giới hạn tổng byte** khi output vẫn tích lũy.

**Bài học quan trọng:** Giới hạn **bộ đệm** (`4096`) và giới hạn **toàn bộ input** (`maxBytes`) là hai điều khác nhau. Một vòng lặp có buffer nhỏ vẫn có thể đọc vô hạn nếu không kiểm tra tổng.

## 6. Đọc đủ byte và phát hiện payload bị cắt ngắn

Các API có hợp đồng khác nhau:

| API | Hành vi cần nhớ |
| --- | --- |
| `InputStream.read()` | Trả 0–255 cho byte đọc được; `-1` khi EOF |
| `InputStream.read(byte[])` | Trả số byte thực đọc; có thể ít hơn kích thước mảng |
| `InputStream.read(byte[], off, len)` | Chỉ đọc tối đa `len` byte; có thể trả ít hơn; kiểm tra `count` |
| `DataInputStream.readFully(byte[])` | Đọc đến khi đủ mảng hoặc ném `EOFException` nếu nguồn kết thúc sớm |
| `DataInputStream.readFully(byte[], off, len)` | Đọc đúng phân đoạn yêu cầu hoặc ném `EOFException` |
| `InputStream.readNBytes(int len)` | Trả mảng chứa tối đa `len` byte, **có thể ít hơn** nếu EOF; phải kiểm tra độ dài |
| `InputStream.readAllBytes()` | Đọc đến EOF, có thể cần bộ nhớ lớn; không áp dụng hạn mức riêng |
| `InputStream.transferTo(OutputStream)` | Sao chép đến EOF; số trả về là byte đã truyền, không tự áp quota |
| `Files.size(Path)` | Lấy kích thước file được báo tại một thời điểm; không khóa nội dung trong suốt lần đọc |
| `InputStream.available()` | Ước lượng byte có thể đọc ngay không chờ; **không** báo tổng dung lượng hoặc EOF |

Ví dụ vòng lặp nguy hiểm vì tin rằng một lần đọc trả đủ:

```java
// SAI về mặt giao thức nếu yêu cầu chính xác 100 byte:
byte[] payload = new byte[100];
int count = input.read(payload);
// count có thể là 17, 40 hoặc -1; payload chưa chắc đầy.
```

Với giao thức yêu cầu chính xác 100 byte, sau kiểm tra giới hạn có thể dùng `DataInputStream.readFully(payload)` hoặc vòng lặp cộng dồn `count` cho đến khi đủ; EOF sớm phải được coi là dữ liệu không hoàn chỉnh, không phải phần đuôi bằng 0.

### 6.1. Xử lý header bị cắt ngắn

`DataInputStream.readInt()` đọc 4 byte theo big-endian. Nếu mới nhận được 1–3 byte rồi EOF, nó ném `EOFException` trước khi có `declaredLength` hợp lệ. Đừng gán giá trị mặc định 0 và coi đó là frame rỗng. Phải phân biệt EOF ngay ranh giới giữa các frame (có thể là kết thúc hợp lệ) với EOF **giữa header** hoặc **giữa payload** (sai định dạng).

### 6.2. Còn byte phía sau frame thì sao?

Nếu protocol cho phép nhiều frame liên tiếp, đọc đúng số byte của frame hiện tại rồi giữ byte còn lại để đọc header kế tiếp. Nếu định dạng file chỉ cho một frame, byte trailing là lỗi hoặc phần metadata tùy đặc tả. Không tự gọi `available() == 0` để kết luận “hết frame”: `available` không đủ nghĩa để xác định cấu trúc.

## 7. Kiểm tra số học để ngăn tràn và lỗi đơn vị

Khi trường độ dài là **số phần tử**, bạn cần tính tổng byte. Ví dụ ảnh có `width`, `height`, `channels` và `bytesPerChannel`, mỗi giá trị có thể do input công bố. Không viết:

```java
// NGUY HIỂM: phép nhân int có thể overflow.
int bytes = width * height * channels * bytesPerChannel;
byte[] pixels = new byte[bytes];
```

Đây là đoạn minh họa với biến chưa khai báo. Phép nhân kiểu `int` có thể tràn thành số âm hoặc số nhỏ; sau đó code có thể cấp phát sai hoặc kiểm tra giới hạn sai. Đổi sang `long` từ **trước phép nhân đầu tiên**, kiểm tra miền từng chiều và tổng byte, sau đó mới ép sang `int` khi đã chắc chắn phù hợp.

Mẫu minh họa với `long` và `Math.multiplyExact`:

```java
// Minh họa: width, height, channels là các số lấy từ header.
// Không chạy độc lập nếu chưa khai báo biến và ràng buộc.
if (width <= 0 || height <= 0 || channels <= 0) {
    throw new IOException("Invalid dimensions");
}

long pixels;
long totalBytes;
try {
    pixels = Math.multiplyExact((long) width, (long) height);
    totalBytes = Math.multiplyExact(pixels, (long) channels);
} catch (ArithmeticException overflow) {
    throw new IOException("Dimensions overflow", overflow);
}

long maxImageBytes = 8L * 1024 * 1024;
if (totalBytes > maxImageBytes) {
    throw new IOException("Image too large");
}
byte[] image = new byte[(int) totalBytes];
```

Ví dụ giả định **một byte mỗi channel**; nếu có `bytesPerChannel`, phải nhân thêm bằng phép toán được kiểm soát. Đây là minh họa cho cấu trúc validation, chưa kiểm tra màu/stride/padding/dung lượng metadata hoặc toàn vẹn ảnh.

Tại sao không chỉ kiểm tra `bytes <= Integer.MAX_VALUE`? Vì ngân sách thật có thể nhỏ hơn rất nhiều và việc cấp phát gần giới hạn mảng Java hoàn toàn không phù hợp trong hệ thống nhiều request đồng thời. Tránh việc chuyển `long` hoặc unsigned length sang `int` **trước khi** kiểm tra giới hạn, vì cast có thể thay đổi giá trị.

### 7.1. Length unsigned và endian

Một header gồm 4 byte có thể được định nghĩa là `uint32` thay vì signed `int`. Java `DataInputStream.readInt()` diễn giải nó theo signed two's complement; nếu định dạng thật là unsigned, giá trị lớn hơn `Integer.MAX_VALUE` sẽ xuất hiện dưới dạng số âm.

Nếu giao thức dùng unsigned 32-bit big-endian, có thể diễn giải qua:

```java
// Minh họa sau khi đã có DataInputStream input:
long unsignedLength = Integer.toUnsignedLong(input.readInt());
if (unsignedLength > MAX_ALLOWED_BYTES) {
    throw new IOException("Length too large");
}
```

**Không** lập tức cast `unsignedLength` về `int`. `MAX_ALLOWED_BYTES` phải được định nghĩa và áp dụng trước, thường thấp hơn nhiều so với giới hạn `int`. Với little-endian, cần API/cách đọc phù hợp, chẳng hạn `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` sau khi đã kiểm soát kích thước input. Đọc sai endian có thể khiến độ dài nhỏ biến thành con số rất lớn.

### 7.2. Phép cộng khi tính tổng các phần

Nếu nhiều chunk có độ dài `length`, đừng viết `total += length` rồi mới hỏi “có vượt max không” khi `total` có nguy cơ overflow. Với số không âm và giới hạn xác định, kiểm tra trước:

```java
// Minh họa: total >= 0, length >= 0, maxBytes >= 0.
if (length > maxBytes - total) {
    throw new IOException("Total size exceeded");
}
total += length;
```

Cách này đúng khi đã bảo đảm `0 <= total <= maxBytes` và `length >= 0`. Nếu không giữ được các bất biến đó, phải kiểm tra/áp dụng `Math.addExact` và giới hạn trước khi dùng kết quả. Đừng coi một quota per-chunk đủ để bảo vệ tổng nhiều chunk.

## 8. File metadata, TOCTOU và dữ liệu thay đổi trong lúc đọc

Có thể kiểm tra kích thước trước khi mở file:

```java
// Minh họa; path là Path hợp lệ do caller kiểm soát.
long size = java.nio.file.Files.size(path);
if (size < 0 || size > MAX_ALLOWED_BYTES) {
    throw new IOException("File too large");
}
```

Kiểm tra này hữu ích cho file thông thường có kích thước ổn định, nhưng **không phải cơ chế bảo vệ duy nhất**:

- Giữa lúc gọi `Files.size` và lúc mở/đọc, file có thể bị sửa, thay thế hoặc tăng dung lượng. Đây là vấn đề *time of check to time of use* (TOCTOU).
- Nhiều nguồn không phải file thông thường (socket, pipe, thiết bị, nguồn nén) không có tổng độ dài đáng tin.
- Một số hệ thống file đặc biệt có hành vi kích thước khác với file thường.
- `InputStream.available()` không có nghĩa “tổng số byte còn lại”; dùng nó để cấp phát hoặc xác nhận đã hết dữ liệu là sai.

Nếu đòi hỏi giới hạn chính xác, hãy **enforce trong lúc đọc**, đồng thời có thể dùng metadata để từ chối sớm những trường hợp hiển nhiên quá lớn. Khi cần chống thay đổi file/đường dẫn có chủ đích, còn phải kiểm soát đường dẫn, quyền, symlink, định danh file và vòng đời handle theo thiết kế hệ thống.

## 9. Những dạng dữ liệu cần nhiều hơn một hạn mức

### 9.1. Dữ liệu nén và nguy cơ phình to

Một file ZIP/gzip có thể nhỏ trên ổ đĩa nhưng giải nén thành lượng dữ liệu rất lớn. Kiểm tra kích thước file nén trước khi cấp phát **không đủ**. Khi dùng `GZIPInputStream`, `ZipInputStream` hoặc bộ giải nén khác, hãy đặt hạn mức trên **tổng byte đầu ra giải nén** và tổng số file/entry, xử lý đường dẫn entry nếu tạo file ra ổ đĩa, hạn chế độ sâu/lồng nhau và thời gian xử lý nếu ứng dụng yêu cầu.

### 9.2. Số bản ghi, số chiều và các cấu trúc lồng nhau

Nếu header nói có 10 triệu phần tử, một frame có thể không quá lớn riêng lẻ nhưng tổng đối tượng Java tạo ra có thể lớn hơn nhiều lần phần byte trên wire. Đặt giới hạn số phần tử, số lớp lồng, chiều mảng và tổng bộ nhớ ước tính trước khi dựng cấu trúc. Với ma trận, ảnh hay âm thanh nhiều kênh, kiểm tra phép nhân kích thước an toàn như mục 7.

### 9.3. Chuỗi ký tự được chứa trong frame nhị phân

Nếu frame chứa chuỗi UTF-8, giới hạn **số byte** trước khi cấp phát/giải mã; số ký tự Java có thể khác số byte. Sau đó validate charset, chính sách malformed input, giới hạn số ký tự/code points nếu nghiệp vụ cần. Không dùng `String.length()` như đại diện cho số byte trên mạng.

### 9.4. Dữ liệu đến từ mạng

Length-prefix có thể bị làm giả. Ngoài giới hạn byte, cần read timeout/deadline, cancellation, kiểm soát số kết nối và số request đồng thời. Nếu peer công bố 1.024 byte rồi gửi rất chậm, một `readFully` vẫn có thể chờ lâu ngay cả khi kích thước đã được kiểm tra hợp lệ. Đừng dùng `InputStream.available()` để “tránh bị block”: nó không cho biết bao giờ sẽ có đủ frame.

## 10. Cấp phát trước hay xử lý theo khối?

| Trường hợp | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Frame nhỏ có size đáng tin sau validation | Kiểm tra giới hạn → `new byte[length]` → `readFully` | Dễ parse theo mảng, kiểm soát EOF rõ |
| File rất lớn, cần copy/hash/scan tuần tự | Buffer hữu hạn, vòng lặp theo khối | Không cần giữ toàn bộ byte |
| Nguồn không biết length | Streaming + quota tổng + timeout/cancellation | Tránh đọc vô hạn/tích lũy không kiểm soát |
| Metadata công bố size nhưng file có thể thay đổi | Kiểm tra metadata để từ chối sớm **và** quota trong lúc đọc | Chặn TOCTOU về kích thước |
| Dữ liệu nén | Giới hạn input lẫn output giải nén | Chặn phình to sau giải nén |
| Tập bản ghi có count/length | Validate count, length, tổng tích lũy và phép nhân | Tránh overflow và cạn heap |
| Cần giữ file kết quả cũ nếu input lỗi | Ghi file tạm → verify → công bố/replace theo chính sách | Tránh ghi đè file thật bằng bản dở |

Nếu chỉ muốn tính SHA-256 của file nhiều GB, đọc từng khối để cập nhật digest; không đọc tất cả byte vào một mảng. Nếu muốn parse một frame nhỏ làm object, kiểm tra độ dài trước rồi đọc đúng frame là hợp lý.

## 11. Lỗi phổ biến và cách xử lý

1. **Tin ngay header:** lấy `length` từ nguồn không đáng tin rồi cấp phát mà không có `MAX_LENGTH`.
2. **Chỉ kiểm tra `length > MAX`:** bỏ sót số âm; một số định dạng còn cấm length 0.
3. **Ép `long`/unsigned sang `int` quá sớm:** có thể tràn hoặc thành số âm khiến kiểm tra sai.
4. **Nhân/cộng kích thước bằng `int`:** phép toán tràn trước khi kiểm tra tổng byte.
5. **Giả định `read(byte[])` đọc đầy buffer:** có thể trả ít hơn; phải đọc đến đủ hoặc báo EOF sớm.
6. **Xem EOF sớm là dữ liệu hợp lệ:** mảng đã cấp phát chứa byte 0 ở phần chưa đọc; không được im lặng chấp nhận.
7. **Tin `available()` cho biết kích thước toàn bộ:** API này chỉ ước lượng byte sẵn có không phải chờ.
8. **Dùng `readAllBytes()` trên nguồn không có giới hạn:** có thể hết heap hoặc chờ vô hạn.
9. **Chỉ đặt quota trên từng chunk:** tổng một triệu chunk vẫn vượt ngân sách.
10. **Chỉ đo compressed bytes:** dữ liệu giải nén có thể phình rất lớn.
11. **Nhầm byte với ký tự:** UTF-8 biến một code point thành số byte khác nhau.
12. **Không xử lý số frame nhiều hơn dự kiến:** một frame nhỏ không có nghĩa toàn kết nối nhỏ.
13. **Tin `Files.size` không thay đổi:** không bảo vệ khỏi file tăng/thay đổi trong lúc đọc.
14. **Không giới hạn thời gian với nguồn mạng:** frame hợp lệ về length vẫn có thể không bao giờ nhận đủ byte.
15. **Ghi output trực tiếp rồi công bố khi lỗi:** phần dữ liệu dở có thể trông như file hoàn chỉnh.
16. **Không kiểm tra magic/version/checksum:** độ dài đúng không bảo đảm định dạng và nội dung đúng.

## 12. Checklist kiểm thử và bài tập

### 12.1. Kiểm thử một frame có length prefix

- **Length = 0**: chấp nhận hoặc từ chối theo đặc tả, không coi tự động là lỗi.
- **Length = 1**: đọc đúng một byte.
- **Length = MAX**: chấp nhận nếu có đủ payload và tài nguyên.
- **Length = MAX + 1**: từ chối **trước khi cấp phát**.
- **Length = -1**: từ chối trước khi tạo mảng.
- **Header thiếu 1–3 byte**: `readInt` báo EOF sớm.
- **Payload thiếu một byte**: `readFully` báo `EOFException`.
- **Payload chính xác**: parse/validate nội dung theo định dạng.
- **Trailing byte**: xử lý theo quy tắc một frame hay nhiều frame.
- **Nhiều frame hợp lệ liên tiếp**: kiểm soát quota tổng và số lượng.
- **Nguồn đọc chậm**: timeout/deadline phát huy tác dụng ở tầng nguồn.

### 12.2. Thực hành

1. Đổi `MAX_PAYLOAD_BYTES` trong `SafeFrameDemo` thành `3`, thử độ dài 0, 3, 4 và -1; ghi lại hành vi mong đợi.
2. Sửa đầu vào của ví dụ thành header 4 byte nhưng payload có 3 byte; chứng minh code ném `EOFException`.
3. Viết parser cho định dạng `count (int) + count × 8 byte`, dùng `Math.multiplyExact((long) count, 8L)`, kiểm tra số âm, số phần tử và tổng byte trước khi cấp phát.
4. Trong `BoundedBinaryCopyDemo`, thử max bằng 0, 4, 5, 6. Phân biệt trường hợp input rỗng, vừa đủ và vượt ngưỡng; chỉ rõ output dở sau lỗi.
5. Thiết kế giao thức nhiều frame: mỗi frame ≤ 1 MiB nhưng tổng một request ≤ 16 MiB. Làm sao kiểm tra quota tổng **trước khi cộng độ dài frame**?
6. So sánh dùng `Files.size` trước khi mở và đo bytes trong lúc đọc; mô tả một thay đổi file giữa hai bước khiến metadata không còn đúng.
7. Thiết kế xử lý file nén có output giới hạn 50 MiB; giải thích vì sao kiểm tra kích thước ZIP/gzip ban đầu chưa đủ.
8. Với một giao thức có trường `uint32` little-endian, xác định đúng API để đọc header, chuyển giá trị sang `long`, validate và chỉ sau đó cast sang `int` khi thật sự cần.
9. Giả lập nguồn chậm hoặc ném `IOException`; kiểm tra quá trình dừng an toàn, đóng stream và không công bố file đích chưa đầy đủ.

## 13. Tự đánh giá

Bạn đã nắm bài khi có thể giải thích rõ:

- Tại sao `new byte[dataInput.readInt()]` là rủi ro ngay cả khi phía gửi “thông thường” luôn gửi dữ liệu nhỏ?
- Tại sao `DataInputStream.readFully` quan trọng nhưng **không thay thế** kiểm tra size trước cấp phát?
- `readNBytes(length)` và `readAllBytes()` có thể làm tăng sử dụng bộ nhớ thế nào?
- Tại sao số byte có sẵn của `available()` khác với kích thước nguồn?
- Tại sao cần kiểm tra phép nhân/cộng **trước** khi đưa kết quả vào bộ cấp phát?
- Có gì khác giữa limit 4 KiB cho buffer và limit 4 MiB cho tổng input?
- Khi nào cần giới hạn **byte sau giải nén** và số phần tử, không chỉ byte nén?
- Nếu đọc thất bại ở giữa payload, kết quả đã ghi ra file đích cần được xử lý thế nào?

**Ghi nhớ:** Độ dài lấy từ nguồn ngoài chỉ là **khẳng định chưa được tin cậy**. Hãy xác định đơn vị và trần hợp lệ, kiểm tra phép toán kích thước và số lượng trước cấp phát, sau đó yêu cầu đủ byte hoặc báo lỗi. Với dữ liệu không có length tin cậy, đọc theo khối có **quota tích lũy**, kiểm soát timeout, và xử lý output dở. Cách này bảo vệ cả tính đúng dữ liệu lẫn ngân sách bộ nhớ và tài nguyên I/O.