# Giới hạn bộ nhớ khi đầu vào không đáng tin — Byte stream trong Java 11+

> **Bối cảnh:** Dữ liệu đọc từ mạng, upload, tệp do người dùng cung cấp, luồng giải nén hoặc nguồn của hệ thống ngoài có thể lớn hơn dự kiến, không có kích thước biết trước, hoặc kéo dài rất lâu. Với `InputStream`, nguyên tắc an toàn là **chọn ngưỡng tin cậy trước**, **đếm số byte thực sự đọc**, và **dừng khi vượt ngưỡng**. Các API Java 11 trong bài này vẫn được hỗ trợ trên JDK hiện đại.

## 1. Học xong bài này bạn làm được gì?

1. Hiểu vì sao `InputStream.readAllBytes()`, `Files.readAllBytes()`, `ByteArrayOutputStream` và `String` có thể làm tăng bộ nhớ khi dữ liệu chưa được giới hạn.
2. Phân biệt **kích thước công bố** của dữ liệu với **số byte thực sự đọc**; biết vì sao `InputStream.available()` không dùng để đo kích thước toàn bộ đầu vào.
3. Viết helper đọc dữ liệu có giới hạn và trả `byte[]`, phát hiện chính xác trường hợp đầu vào dài **hơn ngưỡng đúng một byte**.
4. Sao chép từ `InputStream` sang `OutputStream` với buffer cố định, đếm `long` và tránh giữ toàn bộ nội dung trong heap.
5. Áp dụng giới hạn ở **đúng tầng xử lý**, nhất là khi giải nén hoặc parse dữ liệu có thể tạo thêm nhiều object.
6. Kiểm thử ngưỡng 0, đúng giới hạn, vượt giới hạn, input rỗng, nguồn trả về từng phần và cleanup sau lỗi.

## 2. Mô hình nguy cơ: đầu vào “không đáng tin” nghĩa là gì?

Đầu vào không đáng tin không nhất thiết do người tấn công chủ ý tạo ra. Nó có thể là một client upload nhầm tệp quá lớn, dịch vụ từ xa trả về dữ liệu không như cam kết, tệp bị hỏng hoặc dữ liệu nén nhỏ nhưng phình to khi giải nén.

Ví dụ chương trình muốn nhận tối đa **1 MiB** nội dung một request, nhưng người dùng gửi luồng có **200 MiB**. Nếu ứng dụng gọi:

~~~java
byte[] body = input.readAllBytes();
~~~

thì API sẽ cố đọc hết phần còn lại của `input` và giữ nội dung trong một mảng. Khi luồng quá lớn, ứng dụng có thể dùng nhiều heap, tăng thời gian GC hoặc gặp `OutOfMemoryError`. `readAllBytes()` phù hợp với trường hợp nhỏ **đã biết là an toàn**, chứ không tự đặt giới hạn bảo vệ ứng dụng.

Một luồng có thể chứa **nhiều byte hơn kích thước của bộ nhớ còn trống**, hoặc không bao giờ kết thúc nếu đầu bên kia vẫn gửi dữ liệu. Đọc luồng mà không có giới hạn là để cho nguồn ngoài quyết định bao nhiêu tài nguyên chương trình tiêu thụ.

**Hạn mức cần được xác định bởi ứng dụng**, theo chức năng và ngân sách tài nguyên; không lấy nguyên giá trị mà client khai báo làm hạn mức bảo mật.

### Các loại giới hạn khác nhau

| Giới hạn | Đo cái gì? | Phải đặt ở đâu? |
| --- | --- | --- |
| **Raw-body limit** | Số byte thực nhận từ nguồn, ví dụ HTTP request body | Khi đọc luồng mạng/nguồn thô |
| **Expanded-data limit** | Byte đã giải nén (`GZIPInputStream`, ZIP entry...) | **Sau** bước giải nén |
| **In-memory payload limit** | Số byte tối đa được giữ làm `byte[]`, cộng thêm chi phí bản sao | Trước khi tích lũy nội dung trong RAM |
| **Output-size limit** | Byte tối đa cho phép ghi vào tệp hoặc hệ thống đích | Trong vòng lặp sao chép |
| **Time limit** | Thời gian chờ dữ liệu, thời gian đọc hoặc thời hạn request | Ở tầng mạng/ứng dụng, độc lập với byte limit |
| **Concurrency limit** | Số request/tác vụ lớn đang chạy cùng lúc | Ở bộ điều phối, server hoặc hàng đợi |

**1 MiB = 1.048.576 byte.** Trong một chương trình thực tế, giá trị hạn mức cần đến từ cấu hình **đáng tin cậy** và phù hợp tài nguyên. Không dùng số MiB minh họa trong bài làm ngưỡng mặc định cho mọi loại dữ liệu.

## 3. Hiểu đúng hợp đồng các API InputStream

`InputStream` là luồng **byte**; một lời gọi `read(byte[])` có thể trả **ít byte hơn** kích thước buffer, kể cả khi luồng còn dữ liệu. Chỉ giá trị **`-1`** mới biểu thị đã tới cuối luồng. Đừng suy ra kết thúc chỉ vì `read` trả ít hơn `buffer.length`.

| API | Hợp đồng Java 11 liên quan | Rủi ro khi nguồn không đáng tin |
| --- | --- | --- |
| `InputStream.readAllBytes()` | Đọc toàn bộ byte còn lại tới EOF vào một `byte[]` | Không có giới hạn do ứng dụng truyền; có thể tốn rất nhiều RAM |
| `Files.readAllBytes(path)` | Đọc toàn bộ tệp vào một mảng | Tệp lớn làm mảng lớn; kiểm tra kích thước bên ngoài không thay thế kiểm tra khi đọc |
| `InputStream.readNBytes(int len)` | Đọc tối đa `len` byte, dừng khi đủ hoặc EOF | Có **giới hạn dữ liệu trả về**, nhưng vẫn cấp phát bộ nhớ tỉ lệ với `len`; tự nó không từ chối phần dư |
| `InputStream.readNBytes(byte[], off, len)` | Đọc vào buffer do bạn cấp, tối đa `len` byte | Cần vòng lặp/logic bổ sung để xử lý toàn bộ request và phát hiện vượt ngưỡng |
| `InputStream.transferTo(out)` | Chuyển **toàn bộ** byte còn lại tới EOF sang `out` | Không có tham số cap; với `ByteArrayOutputStream` vẫn có thể dồn dữ liệu vào RAM; với file có thể dùng nhiều đĩa |
| `InputStream.available()` | **Ước tính** byte có thể đọc mà không chặn, không phải tổng kích thước | Không dùng để quyết định kích thước mảng hay kiểm soát input |
| `ByteArrayOutputStream` | Tích lũy byte trong vùng nhớ có thể phát triển; `toByteArray()` tạo bản sao | Có thể dùng hơn một lần kích thước payload ở thời điểm sao chép |
| `InputStream.read(buf,off,len)` | Đọc tối đa `len` byte mỗi lần; `-1` là EOF | Phù hợp để xây dựng vòng lặp có cap và bộ đệm cố định |

Javadoc Java 11 đã nói `readAllBytes()` không dành cho luồng dữ liệu lớn. `readNBytes(int)` cũng không biến một `len` cực lớn thành mức sử dụng RAM thấp; nó chỉ giới hạn **byte trả về** theo tham số truyền vào.

### Vì sao available() không phải giới hạn đáng tin?

~~~java
int guessedSize = input.available();
byte[] data = new byte[guessedSize];
~~~

Đây là mẫu **không đúng** để đọc hết luồng. `available()` có thể trả 0 ngay cả khi dữ liệu sẽ đến sau đó, vì nó nói về lượng dữ liệu có thể đọc mà không chặn. Một số loại stream có thể trả giá trị gần dung lượng còn lại; nhiều loại khác không làm vậy. Không dựa trên `available()` để quyết định buffer chứa toàn bộ input hoặc chứng minh input nhỏ.

Tương tự, `Content-Length` do HTTP client gửi hoặc `Files.size(path)` chỉ là **thông tin để kiểm tra sớm**. Có thể từ chối ngay nếu kích thước công bố vượt giới hạn, nhưng vẫn phải **đếm byte thật trong lúc đọc** để xử lý nguồn không khai báo chiều dài, thông tin lỗi, dữ liệu thay đổi giữa lúc kiểm tra và lúc đọc, hoặc luồng không tương ứng với thông tin bên ngoài.

## 4. Mẫu thiết kế: đếm byte, chỉ đọc đến giới hạn rồi thử thêm 1 byte

Giả sử `maxBytes = 5`, đầu vào có độ dài:

- 0 byte: hợp lệ.
- 1–4 byte: hợp lệ.
- **Đúng 5 byte:** hợp lệ; cần chứng minh đã tới **EOF**, không phải chỉ vừa đầy buffer.
- **6 byte:** từ chối; chỉ cần phát hiện **byte thứ sáu** để biết đã quá ngưỡng.

Thiết kế đáng tin có ba phần:

1. Có hạn mức `maxBytes` do ứng dụng chọn và bộ đệm cố định (ví dụ 8 KiB).
2. Sau mỗi `read`, tăng biến `total` theo **số byte thực nhận**; bảo đảm `total` không vượt `maxBytes` trước khi chấp nhận/ghi byte.
3. Khi đạt đúng giới hạn, **đọc thử 1 byte** để phân biệt “đúng giới hạn và EOF” với “còn dữ liệu”. Nếu thử đọc trả `-1` thì chấp nhận; nếu trả byte thì báo vượt giới hạn.

Cách này tránh lỗi rất phổ biến:

~~~java
// SAI: vừa đạt cap chưa chứng minh phần còn lại của stream đã hết.
if (total == maxBytes) {
    return result;
}
~~~

Không cần tải toàn bộ phần dư để từ chối: chỉ một byte vượt ngưỡng đã đủ. Việc thử đọc byte cuối **có thể phải chờ** một luồng mạng chưa đóng; vì vậy hệ thống còn cần timeout/deadline độc lập.

### Đếm kiểu long để tránh tràn số

Dùng `long` cho tổng byte đi qua luồng, nhất là khi truyền ra tệp. Đừng viết:

~~~java
// Có thể tràn số nếu total lớn:
if (total + count > maxBytes) {
    throw new IOException("too large");
}
~~~

Thay vào đó, khi đã giữ bất biến `0 <= total <= maxBytes`:

~~~java
long remaining = maxBytes - total;
if (count > remaining) {
    throw new IOException("too large");
}
~~~

So sánh với **phần còn lại** không cần phép cộng có thể tràn, đồng thời có thể kiểm tra trước khi gửi byte sang đích.

## 5. Chương trình Java 11+ hoàn chỉnh: cap cho byte[] và copy giới hạn

Tệp **`LimitByteStreamsDemo.java`** sau có một helper cốt lõi là `copyAtMost`. Helper này chỉ tạo buffer **8.192 byte** và đếm số byte đã chuyển. Một helper khác là `readAtMost` tái sử dụng cùng giới hạn nhưng tích lũy kết quả vào `byte[]` khi payload đủ nhỏ.

Ví dụ dùng dữ liệu tự tạo trong bộ nhớ và một tệp tạm do `Files.createTempFile` tạo, nên không cần mạng hoặc dịch vụ bên ngoài.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LimitByteStreamsDemo {
    static final class LimitExceededException extends IOException {
        LimitExceededException(long cap) {
            super("Input exceeds " + cap + " bytes");
        }
    }

    // Copy tối đa maxBytes; byte kế tiếp (nếu có) gây lỗi.
    // Không đóng in/out: người gọi sở hữu tài nguyên.
    static long copyAtMost(InputStream in, OutputStream out, long maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be >= 0");
        }

        byte[] buffer = new byte[8192];
        long copied = 0;

        while (true) {
            long remaining = maxBytes - copied;

            // Nếu đã đạt cap, chỉ thử đọc 1 byte để kiểm tra EOF.
            int request = (int) Math.min((long) buffer.length,
                    remaining > 0 ? remaining : 1L);
            int n = in.read(buffer, 0, request);

            if (n == -1) {
                return copied; // Tới EOF mà chưa vượt cap.
            }
            if (n == 0) {
                // Một InputStream chuẩn phải tiến triển khi request > 0.
                throw new IOException("InputStream made no progress");
            }
            if (n > remaining) {
                // Không ghi byte vượt giới hạn xuống đích.
                throw new LimitExceededException(maxBytes);
            }

            out.write(buffer, 0, n);
            copied += n;
        }
    }

    // Chỉ dùng khi cap nhỏ, do ứng dụng tin cậy lựa chọn.
    static byte[] readAtMost(InputStream in, int cap) throws IOException {
        if (cap < 0) {
            throw new IllegalArgumentException("cap must be >= 0");
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        copyAtMost(in, out, cap);
        return out.toByteArray();
    }

    static void check(byte[] payload, int cap) throws IOException {
        try (InputStream in = new ByteArrayInputStream(payload)) {
            try {
                byte[] bytes = readAtMost(in, cap);
                System.out.println(
                        "cap=" + cap + ": OK (" + bytes.length + " bytes)"
                );
            } catch (LimitExceededException ex) {
                System.out.println("cap=" + cap + ": REJECTED");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] six = "ABCDEF".getBytes(StandardCharsets.UTF_8);

        check(six, 6);         // Đúng bằng cap.
        check(six, 5);         // Dài hơn cap đúng 1 byte.
        check(new byte[0], 0); // Rỗng, cap bằng 0.

        Path temp = Files.createTempFile("bounded-input-", ".bin");
        try {
            try (InputStream in = new ByteArrayInputStream(six);
                 OutputStream out = Files.newOutputStream(temp,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {
                System.out.println(
                        "copied=" + copyAtMost(in, out, 6)
                );
            }
            System.out.println("onDisk=" + Files.size(temp));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Chạy bằng JDK 11 trở lên:

~~~bash
javac LimitByteStreamsDemo.java
java LimitByteStreamsDemo
~~~

**Stdout chính xác của dữ liệu thử:**

~~~text
cap=6: OK (6 bytes)
cap=5: REJECTED
cap=0: OK (0 bytes)
copied=6
onDisk=6
~~~

### Vì sao ví dụ này đúng?

1. `readAtMost` trả `byte[]` chỉ sau khi `copyAtMost` đọc tới EOF mà không phát hiện byte vượt giới hạn.
2. Khi payload dài **6 byte** và cap = **5**, helper chấp nhận tối đa 5 byte vào `ByteArrayOutputStream`, sau đó thử đọc thêm 1 byte. Vì còn byte thứ sáu, nó ném `LimitExceededException`; chương trình in `REJECTED`.
3. Nếu payload dài **đúng 6 byte**, sau 6 byte đã copy, lần đọc kiểm tra EOF trả `-1`. Helper chấp nhận đầy đủ 6 byte.
4. Cap = 0 với stream rỗng vẫn hợp lệ vì lần đọc thử 1 byte nhận `-1`. Cap = 0 với stream không rỗng sẽ bị từ chối.
5. `copyAtMost` dùng mảng buffer cố định, nên riêng **buffer đọc** không tăng theo kích thước input. Khi `out` là tệp, byte được ghi dần ra tệp. Khi `out` là `ByteArrayOutputStream`, byte vẫn được tích lũy trong heap — đây là quyết định có chủ đích của `readAtMost`.
6. `in.read(...)` có thể trả ít hơn số byte yêu cầu; code luôn dùng đúng `n`, không tự cho rằng một lần đọc là đủ.
7. Các stream được đóng bằng `try-with-resources`. Tệp tạm được xóa trong `finally`; nếu việc xóa gặp lỗi filesystem, `deleteIfExists` có thể ném `IOException`.

**Lưu ý về bộ nhớ:** `readAtMost` vẫn phải cấp phát đủ RAM cho dữ liệu hợp lệ. `ByteArrayOutputStream` có vùng nhớ tích lũy và `toByteArray()` tạo **một mảng sao chép mới**; do đó **đỉnh sử dụng heap có thể lớn hơn cap**. Chỉ dùng biến thể `byte[]` với ngưỡng **nhỏ và được duyệt theo ngân sách memory thực tế**. Việc giới hạn input giúp ngăn tăng vô hạn, nhưng không làm dữ liệu lớn trở nên miễn phí.

## 6. Giữ bộ nhớ thấp khi đầu vào lớn: stream sang tệp, không dồn vào RAM

Nếu nghiệp vụ cần xử lý hoặc lưu nội dung kích thước lớn hơn mức hợp lý để chứa trong heap, dùng `InputStream` và `OutputStream` với một **buffer cố định**:

~~~text
Nguồn không đáng tin --> InputStream --(8 KiB/lần)--> bộ đếm byte
                                                    |
                                           vượt giới hạn?
                                           /           \
                                         có            không
                                         |               |
                                     từ chối       OutputStream
                                                  (tệp/tầng xử lý)
~~~

Trong chương trình ở mục 5, `copyAtMost` đã có dạng này. Khi `out` là `Files.newOutputStream(temp)`, ứng dụng không giữ toàn bộ payload trong `byte[]`. Đổi sang tệp **không** có nghĩa là bỏ giới hạn: kẻ gửi có thể làm đầy đĩa nếu chỉ dùng `InputStream.transferTo(fileOut)` mà không kiểm số byte.

### Tệp tạm và tính toàn vẹn đầu ra

Với một upload thực tế, nên ghi vào **tệp tạm có giới hạn**, chỉ đưa ra tên tệp cuối cùng **sau khi nhận đủ dữ liệu và xác thực thành công**:

~~~java
// Ví dụ minh họa trong method có throws IOException.
// input, targetDir và targetName đã được xác thực ở tầng gọi.
Path temporary = Files.createTempFile(targetDir, "upload-", ".part");
boolean completed = false;
try {
    try (OutputStream out = Files.newOutputStream(
            temporary, StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING)) {
        copyAtMost(input, out, MAX_UPLOAD_BYTES);
    }

    // Chỉ đặt completed=true khi các kiểm tra nội dung đều thành công.
    validateUploadedFile(temporary);
    completed = true;
} finally {
    if (!completed) {
        Files.deleteIfExists(temporary);
    }
}

// Tiếp tục xử lý/di chuyển temporary tới vị trí cuối theo chính sách ứng dụng.
~~~

Đây là **đoạn thiết kế minh họa**, không phải chương trình độc lập: cần định nghĩa `input`, `targetDir`, `MAX_UPLOAD_BYTES`, `validateUploadedFile` và thao tác publish tệp. Nó nhấn mạnh: nếu dữ liệu bị từ chối, tệp tạm chứa phần đã ghi **phải bị xóa**; một exception không tự động hoàn tác những byte đã ghi ra đĩa. Trong code thực tế cần quản lý chính sách tên đích, quyền ghi, cleanup và thao tác move theo yêu cầu nhất quán dữ liệu.

### Buffer cố định là một phần, không phải mọi phần của bộ nhớ

Một vòng lặp có buffer 8 KiB có chi phí RAM thấp cho việc **chuyển byte**, nhưng:

- Nếu output là `ByteArrayOutputStream`, dữ liệu vẫn tích lũy; buffer đọc cố định không đủ để giới hạn heap.
- Nếu sau đó gọi `Files.readAllBytes(temp)`, ứng dụng lại phải nạp cả file vào RAM.
- Nếu parser tạo một danh sách object lớn từ input, bộ nhớ parser có thể tăng mạnh dù input đọc theo chunk.
- Nếu 100 request cùng lúc mỗi request giữ 1 MiB, tổng các payload đã khoảng 100 MiB, chưa kể array-copy, thread stacks và các object khác. Hạn chế **concurrency** song song với cap từng request.

## 7. Dùng readNBytes(int) an toàn cho đầu vào nhỏ

`InputStream.readNBytes(int len)` (có từ Java 11) là cách gọn khi ứng dụng **cho phép tích lũy byte trong bộ nhớ** và đã chọn cap nhỏ.

Nếu muốn từ chối dữ liệu vượt `limit`, có thể đọc **`limit + 1`** byte để tạo dấu hiệu vượt giới hạn:

~~~java
int limit = 1 * 1024 * 1024;  // Ví dụ 1 MiB do ứng dụng đặt.
byte[] payload;

try (InputStream in = openUntrustedStream()) {
    byte[] candidate = in.readNBytes(limit + 1);
    if (candidate.length > limit) {
        throw new IOException("Input too large");
    }
    payload = candidate;
}
~~~

**Đây là đoạn minh họa**, cần triển khai `openUntrustedStream()` và quyết định chính sách lỗi cụ thể.

Điểm cần đọc kỹ:

- `readNBytes(limit)` chỉ bảo đảm trả **không quá limit byte**; nếu đọc được đúng limit byte, chưa chắc input đã kết thúc. Bởi vậy chỉ `readNBytes(limit)` rồi coi như “đã đọc hết dữ liệu hợp lệ” có thể **lặng lẽ cắt phần dư**.
- Đọc `limit + 1` giúp phân biệt trường hợp vượt giới hạn mà không cần đọc toàn bộ phần còn lại. Chọn `limit` đủ nhỏ để phần cấp phát cần thiết vẫn nằm trong ngân sách heap.
- `limit` phải không âm và **nhỏ hơn `Integer.MAX_VALUE`** trước khi cộng 1; nếu giới hạn là số không đáng tin hoặc quá lớn có thể gây tràn số/OutOfMemoryError.
- `readNBytes(int)` có thể sử dụng **bộ nhớ tạm** tỉ lệ với lượng byte được đọc, không hứa chỉ cấp phát một mảng đúng bằng số byte trả về.
- `readNBytes(int)` không tự đóng stream; `try-with-resources` ở caller chịu trách nhiệm đóng.
- Nếu payload có thể lớn hoặc số lượng request đồng thời cao, dùng `copyAtMost` với output ra file/processor thay vì cấp phát `byte[]`.

Đừng viết `readNBytes(Integer.MAX_VALUE)` để “an toàn vì đã truyền limit”: đó vẫn là yêu cầu cho phép dữ liệu khổng lồ chiếm heap.

## 8. HTTP, Content-Length, upload và input chậm

Một web request có thể đến dưới dạng **chunked transfer** hoặc không có độ dài đáng tin cậy. Ngay cả khi có header độ dài:

1. **Kiểm tra sớm:** nếu `Content-Length` hợp lệ và lớn hơn cap, từ chối trước khi đọc body.
2. **Giới hạn thực tế:** khi đọc từng chunk, đếm byte và dừng ngay khi quá cap, bất kể header nói gì.
3. **Không tin phần header để cấp phát mảng**: tránh `new byte[(int) contentLength]` khi giá trị chưa được kiểm tra và ép kiểu có thể tràn hoặc client công bố kích thước sai.
4. **Thiết lập timeout/deadline:** byte cap không ngăn client gửi 1 byte mỗi vài giây mãi mãi. Thời gian đọc, tốc độ tối thiểu hoặc deadline cần được xử lý ở tầng server/mạng.
5. **Giới hạn số kết nối/tác vụ:** cap cho từng request là chưa đủ khi rất nhiều request cùng tiêu thụ RAM/CPU/đĩa.
6. **Sử dụng giới hạn sẵn có của framework/server** cho kích thước request, multipart, số file, số phần và các lớp parser; rồi duy trì giới hạn ở tầng ứng dụng nếu cần. Bởi vì một số framework có thể buffer trước khi code ứng dụng nhìn thấy `InputStream`, giới hạn chỉ đặt sau bước buffer sẽ quá muộn.

Nếu client gửi dữ liệu vượt cap, hành vi đóng luồng/kết nối, trả lỗi và dọn tệp tạm phụ thuộc giao thức/framework. `copyAtMost` chỉ phát hiện ngưỡng, không tự quyết định mã HTTP hay quản lý socket.

## 9. Dữ liệu nén: giới hạn byte đã giải nén

Tệp gzip/zip có thể **nhỏ ở dạng nén nhưng rất lớn sau giải nén**. Chỉ giới hạn kích thước upload thô vẫn chưa đủ bảo vệ heap, đĩa và CPU khi giải nén.

Ví dụ minh họa cách đặt cap ở **sau** bước giải nén (giả sử `raw` là stream của tệp gzip và `output` là output được quản lý):

~~~java
try (GZIPInputStream expanded = new GZIPInputStream(raw)) {
    copyAtMost(expanded, output, MAX_EXPANDED_BYTES);
}
~~~

Cần import `java.util.zip.GZIPInputStream` và có `MAX_EXPANDED_BYTES`, `raw`, `output` trong scope. Trong trường hợp thực tế, **nguồn thô cũng cần giới hạn riêng** trước/trong bước giải nén; một request không đáng tin không được phép gửi dữ liệu nén vô hạn.

Tại sao vị trí cap quan trọng? `GZIPInputStream.read(...)` trả **byte đã giải nén**. Đếm `expanded` sau bộ giải nén mới đo được kích thước mà consumer thực sự phải xử lý. Với ZIP, cần tính kích thước **từng entry và tổng các entry**, số entry, độ sâu đường dẫn, giới hạn CPU/thời gian và đích giải nén. Không tin hoàn toàn vào metadata kích thước khai báo trong tệp nén.

**Giới hạn byte không giải quyết mọi rủi ro của parser.** Ví dụ một JSON chỉ vài MiB vẫn có thể làm parser sinh rất nhiều object hoặc cấu trúc lồng sâu. Nếu dùng định dạng phức tạp, đặt thêm giới hạn độ sâu, số lượng phần tử, kích thước chuỗi và chi phí xử lý ở parser phù hợp.

## 10. Tính toán ngân sách heap khi có nhiều request

Một cap `C` byte cho mỗi request **không đồng nghĩa** peak heap chỉ bằng `C`:

- `ByteArrayOutputStream` có thể giữ buffer nội bộ dung lượng lớn hơn dữ liệu đang sử dụng; `toByteArray()` cấp phát một mảng mới và sao chép dữ liệu.
- Sau khi chuyển sang `String` hoặc parse JSON, một biểu diễn object khác có thể tồn tại đồng thời với `byte[]`.
- Decoder, thư viện, collection, cache và các request khác cùng chiếm bộ nhớ.
- Garbage collector có thể chưa thu hồi ngay các buffer không còn tham chiếu.

Hình dung một phép tính quy hoạch:

~~~text
Peak memory ≈ số request đang xử lý
              × (payload tối đa + bản sao/decoder/parser/buffer)
              + bộ nhớ nền của ứng dụng
~~~

Đây là **mô hình ngân sách** để dự trù, không phải công thức bảo đảm bộ nhớ chính xác cho mọi JVM.

Ví dụ có **50 request đồng thời**, mỗi request cho giữ tối đa **2 MiB** payload: chỉ mảng payload đã có thể chiếm **100 MiB**; nếu còn buffer nội bộ và bản sao của mỗi request thì sử dụng có thể cao hơn đáng kể. Vì vậy một service thường cần đồng thời:

- Cap byte/request;
- Cap số request đang xử lý;
- Phân luồng các tác vụ lớn;
- Cap dữ liệu sau parse/giải nén;
- Metrics về kích thước thực, tỷ lệ từ chối, heap và GC;
- Deadline/read timeout và cơ chế hủy công việc.

Nếu không có ngân sách cụ thể, ưu tiên stream sang đĩa hoặc xử lý theo chunk, tránh giữ toàn bộ dữ liệu không đáng tin trong heap.

## 11. Khi nào ném lỗi, khi nào trả kết quả?

**Dữ liệu dài đúng `maxBytes` là hợp lệ** nếu quy tắc cho phép “không quá N byte”; dữ liệu `maxBytes + 1` bị từ chối. Helper nên làm rõ hợp đồng này ngay trong tên, JavaDoc và test.

Chữ ký gợi ý:

~~~java
static long copyAtMost(InputStream in, OutputStream out, long maxBytes)
        throws IOException
~~~

Nó trả số byte chấp nhận/ghi khi tới EOF trong giới hạn. Khi vượt ngưỡng, ném một ngoại lệ nhận diện được, ví dụ `LimitExceededException extends IOException`. Nhờ đó caller phân biệt lỗi “quá lớn” (có thể trả HTTP 413 ở tầng web) với lỗi đĩa/mạng thực tế. Mã HTTP là quyết định **của framework/tầng ứng dụng**, không thuộc hợp đồng `InputStream`.

**Không nên trả về byte đầu tiên rồi coi input đã hoàn thành** khi vẫn còn dư dữ liệu. Nếu chức năng chỉ cần xử lý *prefix* (ví dụ sniff magic bytes), thiết kế API riêng là “readPrefix” và ghi rõ rằng phần còn lại **chưa được xử lý**, đồng thời giới hạn các bước đọc tiếp theo. Đọc prefix và xác thực toàn bộ payload là hai bài toán khác nhau.

Cũng đừng bắt `OutOfMemoryError` như một cơ chế kiểm soát kích thước. Phòng ngừa bằng cap, streaming, resource budgets và kiểm soát concurrency hiệu quả và đáng tin cậy hơn.

## 12. Tình huống lỗi dễ bỏ sót

| Cách làm | Vì sao sai hoặc thiếu? | Hướng xử lý |
| --- | --- | --- |
| `input.readAllBytes()` trên upload chưa giới hạn | Chấp nhận dữ liệu không giới hạn trong heap | Dùng vòng lặp đếm byte có cap; hoặc preconfigured server limit |
| `Files.readAllBytes(path)` trên tệp do user tạo | File có thể lớn hoặc bị thay đổi giữa kiểm tra và đọc | Đọc qua `Files.newInputStream` và đếm byte thật |
| `input.available()` để tính tổng kích thước | Đó là ước tính dữ liệu không chặn | Đừng dùng làm total length hay giới hạn |
| Tin tuyệt đối vào HTTP `Content-Length` | Header có thể thiếu, sai hoặc không phù hợp nội dung thực nhận | Check sớm và kiểm tra lại khi stream |
| `readNBytes(cap)` rồi giả định EOF | Đọc đúng cap không nói phần sau đã hết | Đọc tối đa cap + 1 hoặc thử 1 byte sau cap |
| `transferTo(new ByteArrayOutputStream())` | Có thể tích lũy toàn bộ input trong heap | Dùng helper có cap và output phù hợp |
| Dùng buffer 8 KiB nhưng output là `ByteArrayOutputStream` không cap | Buffer đọc nhỏ, buffer đích vẫn tăng | Đếm và từ chối trước khi vượt |
| Kiểm `total + count > cap` với số lớn | Tổng có thể tràn | So sánh `count > cap - total` |
| Chỉ giới hạn byte nén | Dữ liệu sau giải nén vẫn có thể quá lớn | Đặt cap sau bộ giải nén và cap thô riêng |
| Chỉ kiểm file/stream trước khi parse | Parser có thể tạo rất nhiều object | Giới hạn thêm cấu trúc/độ sâu/số phần tử |
| Vượt cap thì ném exception nhưng giữ file tạm | Để lại dữ liệu dở, chiếm đĩa | Cleanup file tạm bằng `finally` |
| Không đóng stream khi lỗi | Rò rỉ file descriptor/socket | `try-with-resources` theo sở hữu tài nguyên |
| Có byte cap nhưng không timeout | Nguồn chậm có thể giữ request vô hạn | Timeout/deadline và hủy tác vụ |
| Đặt cap theo giá trị client tự gửi | Client có thể chọn cap tùy ý | Chỉ lấy cap từ cấu hình/chính sách tin cậy |

## 13. Bộ kiểm thử tối thiểu đáng làm

Với `copyAtMost` hoặc `readAtMost`, nên kiểm tra những trường hợp sau:

1. **Input rỗng, cap = 0:** trả rỗng / đếm 0, không lỗi.
2. **Input 1 byte, cap = 0:** ném ngoại lệ vượt giới hạn.
3. **Input ngắn hơn cap:** nhận đầy đủ rồi EOF.
4. **Input đúng cap:** nhận đầy đủ, đọc thử byte tiếp theo phải cho EOF.
5. **Input vượt cap đúng 1 byte:** từ chối.
6. **Input vượt cap nhiều byte:** từ chối mà không cần đọc hết phần dư.
7. **Input dài hơn buffer 8 KiB:** đếm đúng qua nhiều lần `read`.
8. **InputStream trả dữ liệu từng chunk nhỏ:** vẫn xử lý đến EOF; không coi lần đọc thiếu là kết thúc.
9. **Đích ghi tệp:** file bị giới hạn tối đa số byte đã chấp nhận; file tạm bị dọn khi thất bại.
10. **Input nén:** cap được áp dụng trên byte sau giải nén, không chỉ trên kích thước nguồn thô.
11. **Giới hạn cực lớn/âm:** bị từ chối theo chính sách trước khi cấp phát mảng hoặc gây tràn phép tính.
12. **Luồng bị lỗi I/O giữa chừng:** caller nhận lỗi và dọn tài nguyên; không công bố payload chưa hoàn chỉnh là thành công.

Có thể xây một stream thử không cho biết kích thước hoặc chỉ trả tối đa 2–3 byte/lần để kiểm tra độ bền của vòng lặp. Cũng nên có test với luồng có thể chặn để xác thực **deadline**, nhưng tránh những bài test phụ thuộc timing thiếu ổn định.

Để kiểm tra định lượng, dùng giá trị cap đo bằng **byte**; chuỗi có dấu tiếng Việt hoặc emoji có số byte UTF-8 khác số đơn vị UTF-16. Nếu giới hạn là số byte, không dùng `String.length()` làm số đo.

## 14. Checklist áp dụng trong code review

- [ ] Cap cho từng loại đầu vào được chọn bởi ứng dụng, có đơn vị **byte** rõ ràng và phù hợp ngân sách.
- [ ] Input không đáng tin được **đếm byte thật khi đọc**, không chỉ tin header hoặc `available()`.
- [ ] Trường hợp **đúng cap** được chấp nhận; byte thứ **cap + 1** bị từ chối.
- [ ] Phép tính counter không có nguy cơ tràn số; buffer đọc có kích thước cố định.
- [ ] Không giữ toàn bộ payload trong `ByteArrayOutputStream` hoặc `byte[]` nếu payload không đủ nhỏ.
- [ ] Dữ liệu giải nén và parser có giới hạn riêng khi cần.
- [ ] `InputStream`, `OutputStream` và file tạm được quản lý đúng vòng đời; không công bố file dở.
- [ ] Có giới hạn đồng thời và thời gian ở tầng kết nối/ứng dụng; không nhầm byte cap với timeout.
- [ ] Test bao gồm input rỗng, exact limit, limit + 1, các lần đọc ngắn, EOF, lỗi I/O và cleanup.
- [ ] Mã tương thích phiên bản Java mục tiêu; không cần API thử nghiệm hoặc cơ chế Java đã lỗi thời.

## 15. Tự kiểm tra

**Câu 1.** `readNBytes(1024)` trả về mảng 1024 byte. Đầu vào có chắc chắn chỉ dài 1024 byte không?

**Không.** Phương thức chỉ bảo đảm đọc tối đa 1024 byte. Luồng có thể còn byte thứ 1025. Để từ chối payload dài hơn 1024, đọc thử thêm một byte hoặc dùng `readNBytes(1025)` với cap đủ nhỏ.

**Câu 2.** Đã dùng buffer 8 KiB, vậy việc `transferTo` sang `ByteArrayOutputStream` có giới hạn RAM không?

**Không.** Vùng đích `ByteArrayOutputStream` vẫn tích lũy byte. Buffer đọc nhỏ không ngăn tổng buffer đích tăng theo kích thước input.

**Câu 3.** Upload gzip nặng 200 KiB, cap raw-body 1 MiB. Có thể giải nén thẳng vào `ByteArrayOutputStream` mà không giới hạn nữa không?

**Không.** Nội dung mở rộng có thể lớn hơn rất nhiều; đặt cap **sau** `GZIPInputStream`, và cân nhắc xử lý theo chunk ra tệp/processor.

**Câu 4.** Nếu client không gửi EOF sau khi đã gửi đúng cap, logic thử byte thứ cap + 1 có thể chờ không?

**Có.** Giới hạn byte không thay thế timeout hoặc deadline của kết nối. Ứng dụng cần cấu hình cả hai.

**Câu 5.** Khi từ chối input quá lớn sau khi ghi một phần ra tệp, làm gì?

**Đóng stream và dọn tệp tạm**, không dùng dữ liệu một phần như file thành công. Chỉ publish file sau kiểm tra toàn bộ nội dung trong giới hạn.

## Tài liệu API chính thức

- [`InputStream` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html): `read`, `readAllBytes`, `readNBytes`, `available`, `transferTo` và giới hạn theo hợp đồng.
- [`InputStream` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html): đối chiếu API và nguyên tắc này trên JDK hiện đại.
- [`ByteArrayOutputStream` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/ByteArrayOutputStream.html): buffer có thể tăng; `toByteArray` tạo mảng mới.
- [`Files` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): mở luồng tệp, kích thước tệp, tệp tạm và `readAllBytes`.
- [`GZIPInputStream` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPInputStream.html): `read` trả byte **đã giải nén**.
- [`ZipInputStream` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/ZipInputStream.html): xử lý từng entry ZIP và byte giải nén.

**Ghi nhớ:** Hạn mức bảo vệ ứng dụng phải được **thực thi trong vòng lặp đọc**, bằng **số byte thực nhận**. Dùng byte đệm cố định, từ chối khi có byte vượt cap, xử lý EOF và đóng tài nguyên. Khi dữ liệu lớn, stream sang đích có giới hạn; khi dữ liệu nén hoặc có cấu trúc, giới hạn thêm chi phí sau giải nén/parse. Các nguyên tắc này đúng với Java 11 và JDK hiện đại.