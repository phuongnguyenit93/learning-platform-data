# Files.readAllBytes và giới hạn bộ nhớ trong Java

`Files.readAllBytes(Path)` là API tiện lợi của `java.nio.file.Files` để **đọc toàn bộ byte của một tệp vào một mảng `byte[]` duy nhất**. Khi tệp nhỏ và thật sự cần tất cả dữ liệu trong bộ nhớ, đây là cách viết ngắn gọn. Khi tệp lớn, đến từ nguồn không tin cậy hoặc có kích thước không dự đoán được, thao tác này có thể tiêu thụ quá nhiều RAM, gây `OutOfMemoryError`, tăng áp lực garbage collection hoặc làm ứng dụng mất ổn định.

**Quy tắc cốt lõi:** nếu nhu cầu là **xử lý tuần tự**, hãy **đọc theo từng khối (streaming)** thay vì tải toàn bộ. Nếu nghiệp vụ bắt buộc cần một `byte[]`, phải thiết kế **giới hạn kích thước và ngân sách bộ nhớ** rõ ràng.

## 1. `Files.readAllBytes(Path)` đọc dữ liệu ra sao?

API:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "photo.png");
byte[] bytes = Files.readAllBytes(path); // Có thể ném IOException.
```

Đây là đoạn mã minh họa cần đặt trong class/phương thức. Phương thức làm các việc có ý nghĩa sau:

1. Mở tệp qua filesystem provider của `Path`.
2. Đọc dữ liệu từ tệp, cố gắng lấy tất cả byte tới EOF.
3. Trả về một **mảng `byte[]`** chứa nội dung đọc được theo thứ tự.
4. Đóng tài nguyên nội bộ của thao tác khi hoàn tất hoặc khi thất bại.

`Files.readAllBytes` đọc **byte thô**, không tự giải mã UTF-8, không phân biệt ảnh, PDF, GZIP hay văn bản và không tự hiểu “mỗi byte là một ký tự”. Với văn bản, cần biết charset gốc rồi mới giải mã:

```java
import java.nio.charset.StandardCharsets;

byte[] data = Files.readAllBytes(path);
String text = new String(data, StandardCharsets.UTF_8);
```

Đoạn này minh họa khi `path` thực sự trỏ tới tệp văn bản UTF-8. Với ảnh, archive hoặc file nhị phân, **giữ dữ liệu là byte**, không ép thành `String`.

### Điều gì KHÔNG xảy ra?

- `Files.readAllBytes` **không trả về một dòng dữ liệu đang được stream**; nó chỉ trả kết quả sau khi đã gom nội dung vào mảng.
- Nó **không có tham số limit** để yêu cầu “chỉ đọc tối đa 10 MB”.
- Nó **không tự động nén hoặc làm nhỏ** nội dung.
- Nó **không tạo snapshot nguyên tử** của một tệp đang bị tiến trình khác sửa; dữ liệu đọc được có thể chịu ảnh hưởng của thay đổi đồng thời.
- Nó **không phù hợp mặc định cho mọi kích thước tệp** chỉ vì có tên ngắn gọn.

Nếu tệp không tồn tại, không đọc được hoặc phát sinh lỗi I/O, thao tác có thể ném `IOException` (ví dụ `NoSuchFileException`). Khi yêu cầu cấp phát bộ nhớ không thể đáp ứng, có thể xuất hiện `OutOfMemoryError` — đây là một `Error` nghiêm trọng, **không** nên xem là đường xử lý thông thường để “thử đọc rồi bắt lỗi nếu quá lớn”.

## 2. Vì sao toàn bộ file trong một `byte[]` dễ tốn RAM?

`byte[]` là một **đối tượng mảng liên tục về mặt logic của Java**, kích thước được biểu diễn bằng `int`. Vì vậy:

- `byte[]` không thể có số phần tử vượt quá giới hạn độ dài mảng Java (xấp xỉ `Integer.MAX_VALUE` về mặt lý thuyết, giới hạn thực tế còn phụ thuộc JVM).
- Một tệp lớn khoảng **2 GiB hoặc hơn** không thể được biểu diễn trọn vẹn trong một `byte[]` đơn thông thường. API không phải công cụ phù hợp cho file ở quy mô đó.
- **File nhỏ hơn 2 GiB vẫn có thể thất bại** nếu heap không đủ, bị phân mảnh, hoặc JVM không thể cấp phát một mảng đủ lớn.
- Mảng cần bộ nhớ cho **byte nội dung và overhead đối tượng**; nếu ứng dụng tạo thêm `String`, bản sao, mảng trung gian hoặc dữ liệu giải nén, tổng bộ nhớ có thể cao hơn đáng kể so với kích thước file.

Ví dụ một file 500 MiB được đọc bằng `Files.readAllBytes` cần một mảng khoảng **500 MiB cho nội dung**, chưa kể overhead, heap đã dùng, bước cấp phát hoặc các bản sao sau đó. Một JVM có giới hạn heap `-Xmx256m` không thể dựa vào `readAllBytes` để giữ tệp 500 MiB trong một mảng.

Lưu ý `-Xmx` giới hạn heap Java, không phải tổng bộ nhớ tiến trình; ứng dụng còn có native memory, thread stacks và các bộ đệm của thư viện. Một file 500 MiB cũng không hàm ý duy nhất “tốn đúng 500 MiB RAM” ở cấp tiến trình.

### Một số phép ước lượng hữu ích

| Dữ liệu | Kích thước byte gần đúng | Hệ quả khi `readAllBytes` |
| --- | --- | --- |
| File cấu hình 4 KiB | 4.096 byte | Thường rất phù hợp nếu thực sự cần toàn bộ |
| File 10 MiB | 10 × 1.048.576 byte | Cần giữ mảng khoảng 10 MiB và thêm overhead |
| File 500 MiB | 500 × 1.048.576 byte | Có thể chiếm tỷ lệ lớn của heap |
| File 3 GiB | Vượt giới hạn mảng `byte[]` đơn thông thường | Không dùng `readAllBytes` |
| File nén 10 MiB | 10 MiB *ở dạng nén* | Nếu giải nén trong RAM, nội dung có thể lớn hơn rất nhiều |

MiB là `1.048.576` byte, còn MB theo hệ thập phân là `1.000.000` byte. Với bài toán giới hạn bộ nhớ, cần thống nhất đơn vị để tránh sai lệch.

## 3. So sánh đọc toàn bộ với xử lý theo từng khối

```text
Cách 1: Files.readAllBytes(path)

File: [-------------------------------- dữ liệu ---------------------------]
                           |
                           v
                  byte[] chứa toàn bộ file
                           |
                   xử lý sau khi đọc xong

Bộ nhớ nội dung: O(kích thước file)


Cách 2: Files.newInputStream(path)

File: [-------------------------------- dữ liệu ---------------------------]
           |             |             |            |
           v             v             v            v
      buffer 8 KiB -> xử lý -> tái sử dụng buffer -> ...
      
Bộ nhớ đọc: O(kích thước buffer)
         (nếu logic xử lý không tích lũy toàn bộ dữ liệu)
```

Ở cách thứ hai, nếu ứng dụng chỉ tính tổng số byte, checksum, ghi sang tệp khác hoặc xử lý record tuần tự, **không cần giữ tất cả byte trong RAM**. Bộ đệm cố định 8 KiB có thể tái sử dụng qua hàng nghìn lần `read`.

Tuy nhiên, nếu sau khi đọc theo từng khối mà lại `append` mọi thứ vào `ByteArrayOutputStream` hoặc lưu toàn bộ vào một `List<byte[]>`, **tổng bộ nhớ vẫn tăng theo kích thước file**. “Dùng InputStream” không tự động đồng nghĩa bộ nhớ luôn nhỏ: quan trọng là ứng dụng làm gì với từng khối.

## 4. Chương trình Java 17+ hoàn chỉnh: so sánh hai cách

Ví dụ tạo tệp tạm nhỏ bằng UTF-8, sau đó đọc toàn bộ bằng `Files.readAllBytes` và đọc theo từng khối `4 byte` bằng `InputStream`. Chúng ta dùng `CRC32` để minh họa việc tính checksum bằng phương pháp streaming mà không cần tích lũy tất cả byte trong mảng. Sau cùng, chương trình giải mã byte UTF-8 đúng charset.

Lưu file **`ReadAllBytesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.CRC32;

public class ReadAllBytesDemo {

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-readall-", ".txt");

        try {
            String original = "Xin chào\n";
            Files.writeString(file, original, StandardCharsets.UTF_8);

            byte[] all = Files.readAllBytes(file);

            CRC32 wholeFileChecksum = new CRC32();
            wholeFileChecksum.update(all);

            CRC32 streamedChecksum = new CRC32();
            long streamedBytes = 0;

            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[4];
                int bytesRead;

                while ((bytesRead = input.read(buffer)) != -1) {
                    streamedChecksum.update(buffer, 0, bytesRead);
                    streamedBytes += bytesRead;
                }
            }

            System.out.println("File bytes: " + Files.size(file));
            System.out.println("readAllBytes length: " + all.length);
            System.out.println("Streamed bytes: " + streamedBytes);
            System.out.println("CRC32 matches: " +
                    (wholeFileChecksum.getValue()
                            == streamedChecksum.getValue()));
            System.out.println("UTF-8 text matches: " +
                    original.equals(
                            new String(all, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReadAllBytesDemo.java
java ReadAllBytesDemo
```

**Stdout chính xác trong điều kiện I/O bình thường:**

```text
File bytes: 10
readAllBytes length: 10
Streamed bytes: 10
CRC32 matches: true
UTF-8 text matches: true
```

Giải thích:

1. `"Xin chào\n"` gồm **10 byte UTF-8**: `Xin` (3), dấu cách (1), `ch` (2), `à` (2), `o` (1), LF (1).
2. `Files.readAllBytes` trả mảng đủ 10 byte; khi đưa vào `CRC32.update(all)`, toàn bộ mảng được xử lý một lần.
3. Vòng lặp streaming dùng **cùng bộ đệm 4 byte** ở mọi lần đọc; giá trị `bytesRead` mới là số byte hợp lệ trong bộ đệm.
4. `streamedChecksum.update(buffer, 0, bytesRead)` xử lý đúng phần vừa đọc, không tính lại các byte cũ ở cuối buffer.
5. `CRC32` của hai luồng bằng nhau chứng minh chúng có cùng checksum trong ví dụ; checksum **không phải** bằng chứng duy nhất tuyệt đối về tính đồng nhất trong mọi ngữ cảnh bảo mật.
6. `new String(all, StandardCharsets.UTF_8)` chỉ được dùng vì chúng ta biết tệp chứa **văn bản UTF-8**. File ảnh hay tệp GZIP không nên giải mã tùy tiện như vậy.

Chương trình xóa tệp tạm trong `finally`, và `try-with-resources` đóng `InputStream`. Nó không tạo dữ liệu lớn hoặc cố gây `OutOfMemoryError` để thử máy.

## 5. Streaming đúng cách với `Files.newInputStream`

Phần cốt lõi của ví dụ có thể tách thành một phương thức xử lý dữ liệu theo từng khối:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long countBytes(Path path) throws IOException {
    long total = 0;

    try (InputStream input = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int n;

        while ((n = input.read(buffer)) != -1) {
            total += n;
            // Tại đây có thể xử lý CHỈ các byte buffer[0..n-1].
        }
    }

    return total;
}
```

Đây là **phương thức minh họa** cần đặt trong một class. Nó sử dụng bộ đệm cố định 8 KiB; `total` là `long` để tránh giới hạn `int` của độ dài một mảng. `InputStream.read(buffer)` có thể trả **ít hơn `buffer.length`** dù chưa EOF — không được coi “đọc ngắn” là hết file.

Nếu muốn xử lý bằng một consumer hoặc ghi ra đích, thực hiện ngay trong vòng lặp:

```java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {

    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        output.write(buffer, 0, n);
    }
}
```

Đây là đoạn minh họa cần biến `source`/`target` dạng `Path` và các import `InputStream`, `OutputStream`, `Files`. **Chỉ ghi `n` byte đã đọc**, không ghi toàn bộ `buffer`. Nếu source và target thực tế là cùng file hoặc cùng đối tượng tệp qua alias/link, cách mở output có thể cắt ngắn dữ liệu nguồn — cần đảm bảo hai đầu khác nhau khi sao chép.

Java còn có `Files.copy(source, target, options...)` để sao chép trực tiếp qua API tệp khi phù hợp, và `InputStream.transferTo(output)` từ Java 9 để chuyển dữ liệu sang `OutputStream`. Những cách này giúp tránh việc tự tạo mảng chứa **toàn bộ file**, miễn là đích cũng xử lý theo luồng chứ không gom toàn bộ vào bộ nhớ.

## 6. Có nên dùng `Files.size(path)` để bảo vệ trước khi đọc?

Có thể dùng `Files.size(path)` để **sàng lọc sơ bộ**:

```java
long maxBytes = 10L * 1024 * 1024; // 10 MiB
long size = Files.size(path);

if (size > maxBytes) {
    throw new IOException("File vượt giới hạn");
}

byte[] data = Files.readAllBytes(path);
```

Đoạn này là mã minh họa cần đặt trong phương thức có `throws IOException` và khai báo `path`/`Files` thích hợp. Nó giúp từ chối một tệp đã được biết là quá lớn **tại thời điểm kiểm tra**. Nhưng nó **chưa tạo giới hạn cứng** cho lượng dữ liệu được cấp phát:

- Tệp có thể **tăng kích thước giữa `Files.size` và `Files.readAllBytes`**.
- Một số loại file/provider hoặc metadata đặc thù không cung cấp kích thước hữu ích để dự đoán chính xác lượng byte đọc được.
- Dù `size <= maxBytes`, heap vẫn có thể không đủ cho mảng hoặc các đối tượng bổ sung.
- Kiểm tra `exists()`, `isRegularFile()`, `size()` riêng biệt rồi mới đọc cũng chịu rủi ro trạng thái thay đổi (*time-of-check to time-of-use*, TOCTOU).

Do đó, nếu dữ liệu **không tin cậy** hoặc bị giới hạn theo quota, giới hạn nên được **thực thi trong quá trình đọc**, không chỉ dựa trên metadata trước khi mở.

## 7. Khi bắt buộc cần `byte[]`: đọc có giới hạn trong lúc stream

Nếu API phía sau thực sự yêu cầu toàn bộ `byte[]`, có thể dùng `InputStream` và `ByteArrayOutputStream` cùng một ngưỡng byte tối đa. Mỗi lần đọc kiểm tra giới hạn **trước khi thêm vào mảng tích lũy**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static byte[] readAtMost(Path path, int maxBytes)
        throws IOException {

    if (maxBytes < 0) {
        throw new IllegalArgumentException(
                "maxBytes must be non-negative");
    }

    try (InputStream input = Files.newInputStream(path);
         ByteArrayOutputStream output =
                 new ByteArrayOutputStream()) {

        byte[] buffer = new byte[8192];
        int count;
        int total = 0;

        while ((count = input.read(buffer)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException("File exceeds byte limit");
            }

            output.write(buffer, 0, count);
            total += count;
        }

        return output.toByteArray();
    }
}
```

Đây là **phương thức minh họa** cần đặt trong một class. Giá trị `total` không vượt `maxBytes` vì điều kiện kiểm tra chạy **trước `output.write`**. Khi file vượt giới hạn, phương thức ném `IOException` và ngừng tích lũy dữ liệu. Nếu tệp bị sửa đồng thời, đoạn kiểm tra này vẫn áp dụng giới hạn trên **số byte thực sự được đọc và giữ lại**.

**Giới hạn quan trọng:** đây vẫn là cách **gom byte vào RAM**. `ByteArrayOutputStream` có vùng đệm nội bộ, có thể mở rộng dung lượng cấp phát vượt số byte đang chứa; `toByteArray()` còn tạo một mảng kết quả mới. Vì vậy **đỉnh bộ nhớ thực tế có thể cao hơn đáng kể `maxBytes`**, và `OutOfMemoryError` vẫn có thể xảy ra nếu giới hạn đặt quá lớn hoặc heap còn ít.

Một lựa chọn giới hạn vài MiB thường hợp lý cho upload cấu hình/small payload; nhưng phải chọn ngưỡng theo tình huống, heap, số request xử lý đồng thời và các cấu trúc phát sinh tiếp theo. Không lấy `Integer.MAX_VALUE` làm giới hạn mặc định chỉ vì `byte[]` dùng `int`.

Nếu cần **giới hạn thực sự sát ngân sách bộ nhớ**, không trả `byte[]` mà nên **xử lý streaming** với buffer cố định, hoặc dùng cơ chế lưu tạm vào file theo quota. Giới hạn byte chỉ là một phần của bảo vệ tài nguyên; còn cần hạn chế thời gian, số request và các thao tác giải nén/phân tích dữ liệu.

## 8. Tình huống thực tế: chọn `readAllBytes` hay API khác?

| Nhu cầu | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| Đọc một icon nhỏ vài KiB để kiểm tra nội dung | `Files.readAllBytes` | Gọn, đủ nhỏ để giữ trong RAM |
| Tải toàn bộ cấu hình binary nhỏ, có hạn mức rõ | `readAtMost` hoặc `Files.readAllBytes` sau đánh giá giới hạn | Có thể cần `byte[]` thực sự |
| Tính checksum cho file vài GB | `Files.newInputStream` + cập nhật digest từng khối | Không cần gom file vào một mảng |
| Sao chép file lớn | `Files.copy` hoặc input/output stream | Xử lý byte theo luồng |
| Đọc file log lớn để lọc dòng | `Files.newBufferedReader` hoặc `Files.lines` | Duyệt theo dòng |
| Tạo `String` từ toàn bộ file văn bản nhỏ | `Files.readString(path, charset)` | Rõ về charset, nhưng vẫn tải toàn bộ văn bản |
| Đọc hết các dòng vào `List<String>` | `Files.readAllLines` | Tiện cho file nhỏ; **không** dành cho file lớn |
| Phục vụ HTTP download kích thước lớn | Streaming từ file sang response stream | Tránh lưu file trong RAM trên mỗi request |
| Xử lý dữ liệu GZIP/ZIP | Giải nén streaming và áp hạn mức **sau giải nén** | Chỉ kiểm kích thước file nén không bảo vệ khỏi expansion |
| Phân tích file ảnh/video rất lớn | Decoder hoặc API chuyên dụng hỗ trợ streaming/tiling | `byte[]` toàn bộ không tối ưu; decoder còn tiêu thụ bộ nhớ riêng |

### Đọc văn bản lớn theo dòng

`Files.lines(path, StandardCharsets.UTF_8)` trả về một `Stream<String>` xử lý dòng khi cần, phù hợp với những tác vụ không cần chứa toàn bộ văn bản:

```java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {

    long warnings = lines
            .filter(line -> line.contains("WARN"))
            .count();

    System.out.println(warnings);
}
```

Đây là đoạn minh họa cần `import java.util.stream.Stream`, `Files`, `StandardCharsets` và biến `path`. **Bắt buộc đóng** stream bằng `try-with-resources` để giải phóng file đang mở. Lưu ý không thu tất cả dòng vào `toList()` nếu mục tiêu là tiết kiệm bộ nhớ; làm như vậy vẫn có chi phí tỷ lệ với nội dung.

Với văn bản UTF-8, `Files.readString` / `Files.readAllLines` cũng có chi phí bộ nhớ tỷ lệ với kích thước nội dung; chúng không phải giải pháp tự động cho file lớn chỉ vì không trả `byte[]`.

## 9. File bị thay đổi trong lúc đọc

Giả sử một tiến trình đang ghi bổ sung log, còn tiến trình khác gọi `Files.readAllBytes`. Kích thước và nội dung tệp có thể thay đổi trong lúc thao tác đang diễn ra.

Không nên suy luận rằng:

- Kích thước nhận được từ `Files.size` chắc chắn bằng `bytes.length` sau `readAllBytes`.
- Nội dung trong mảng luôn là snapshot nhất quán của một thời điểm nếu có writer khác ghi đồng thời.
- Việc đọc thành công có nghĩa dữ liệu đã được xác thực hoặc đáng tin cậy.

Nếu ứng dụng cần snapshot nhất quán, phải thiết kế cơ chế đồng bộ, copy/rename theo giao thức, khóa phù hợp hoặc định dạng có version/checksum; lựa chọn phụ thuộc filesystem và cách ứng dụng ghi file. `readAllBytes` không tự giải quyết cạnh tranh truy cập.

Với dữ liệu do người dùng cung cấp, ngoài giới hạn bộ nhớ còn cần kiểm tra định dạng và kích thước đầu vào theo nghiệp vụ. Một ảnh nén nhỏ có thể mở rộng thành bitmap rất lớn; một file ZIP nhỏ có thể chứa dữ liệu giải nén lớn bất thường. Đây là vấn đề **bộ nhớ sau xử lý**, không được giải quyết chỉ bằng cách giới hạn số byte file gốc.

## 10. Ngoại lệ và quản lý tài nguyên

Chữ ký quan trọng:

```java
byte[] Files.readAllBytes(Path path) throws IOException
```

Đây là **cách mô tả chữ ký**, không phải một lời gọi có thể biên dịch độc lập. Với `Files.readAllBytes`, không cần tự mở/đóng `InputStream` bên ngoài, vì phương thức thực hiện đọc và quản lý tài nguyên nội bộ.

Tuy nhiên, khi chuyển sang `Files.newInputStream` thì phải tự đóng stream:

```java
try (InputStream input = Files.newInputStream(path)) {
    // Dùng input.read(buffer) trong vòng lặp.
}
```

Cần phân biệt:

- **`IOException`:** tệp không tồn tại, quyền không đủ, lỗi đọc hoặc lỗi provider; xử lý theo nghiệp vụ, có thể báo người dùng hoặc retry hợp lý.
- **`OutOfMemoryError`:** JVM không thể cấp phát bộ nhớ cần thiết; đây không phải lỗi “file không tồn tại” và không nên dựa vào cơ chế catch để kiểm soát input quá lớn.
- **`SecurityException`:** có thể xảy ra trong môi trường có chính sách bảo mật/kiểm tra quyền tương ứng.
- **`InvalidPathException`:** có thể phát sinh lúc tạo `Path` từ chuỗi đường dẫn không hợp lệ, không phải vì `readAllBytes` trả byte sai.

Không nuốt mọi ngoại lệ rồi trả mảng rỗng: như vậy chương trình khó phân biệt file rỗng thực sự với thao tác đọc thất bại. Nếu giao diện yêu cầu giới hạn upload, hãy dùng ngoại lệ/cờ lỗi có thông điệp riêng cho “quá giới hạn”.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm/sai? | Hướng xử lý |
| --- | --- | --- |
| `Files.readAllBytes` với mọi file không cần xem kích thước | File lớn có thể vượt giới hạn mảng hoặc heap | Streaming hoặc áp quota có kiểm soát |
| `Files.size(path)` nhỏ nên chắc chắn đọc an toàn | File có thể tăng, heap có thể thiếu | Thực thi giới hạn trong lúc đọc và ngân sách heap |
| `new String(Files.readAllBytes(path))` cho dữ liệu bất kỳ | Chuyển nhị phân thành text không có nghĩa, charset mặc định không rõ | Giữ `byte[]` hoặc dùng charset tường minh khi biết là văn bản |
| Dùng `Files.readAllLines` để “tối ưu RAM” | Nó gom toàn bộ dòng vào `List` | `Files.lines` hoặc `BufferedReader` và xử lý tuần tự |
| Dùng `newInputStream` rồi dồn hết vào `ByteArrayOutputStream` không giới hạn | Vẫn tăng RAM theo dung lượng file | Cấp giới hạn hoặc xử lý streaming |
| Trong loop, xử lý toàn bộ `buffer` sau `read` | Cuối buffer có thể chứa byte từ lượt trước | Chỉ xử lý `buffer[0..n-1]` |
| Một lần `read(buffer)` không đủ buffer nghĩa là EOF | Luồng có thể trả ít byte hơn yêu cầu | Lặp cho tới khi nhận `-1` |
| Cho rằng `byte[]` dài bằng số ký tự | UTF-8 có ký tự nhiều byte | Phân biệt kích thước byte và ký tự |
| Cố bắt `OutOfMemoryError` để “báo file lớn” | Heap có thể đã cạn, ứng dụng không ổn định | Ngăn trước bằng thiết kế stream/limit |
| Quên đóng `InputStream` hoặc `Files.lines` | Có thể rò rỉ tài nguyên/file descriptor | `try-with-resources` |
| Chỉ kiểm kích thước file ZIP/GZIP trước xử lý | Dữ liệu sau giải nén có thể phình lớn | Giới hạn số byte sau giải nén |
| Kích thước file vừa giới hạn, tạo thêm nhiều bản sao | Đỉnh bộ nhớ và concurrency vẫn có thể gây OOM | Đo memory, tránh copy thừa, đặt quota hợp lý |

## 12. Câu hỏi tự kiểm tra

1. **`Files.readAllBytes(path)` trả gì?** Một **`byte[]` chứa toàn bộ byte đã đọc**, không phải `String` và không phải `InputStream`.
2. **Vì sao không nên gọi `readAllBytes` cho file vài GiB?** Vì giới hạn mảng `byte[]`, heap và chi phí cấp phát; streaming phù hợp hơn.
3. **`Files.size(path) <= limit` đã là giới hạn cứng chưa?** Chưa; file có thể thay đổi trước/trong khi đọc và heap có thể thiếu.
4. **Muốn tính CRC32 của file 10 GB có phải đọc toàn bộ không?** Không; dùng `InputStream`, cập nhật checksum từng buffer.
5. **`buffer.length == 8192`, `read(buffer)` trả 700: cần xử lý bao nhiêu byte?** Chỉ **700 byte**.
6. **Thay `readAllBytes` bằng `Files.readAllLines` có tiết kiệm RAM cho file log lớn không?** Không hẳn; nó vẫn gom mọi dòng vào RAM. Nên duyệt `BufferedReader` hoặc `Files.lines`.
7. **Dùng `ByteArrayOutputStream` để nhận mọi byte từ InputStream không giới hạn có phải streaming ít RAM không?** Không; nó vẫn tích lũy nội dung.
8. **Đã giới hạn file GZIP nén ở 10 MiB thì dữ liệu giải nén chắc chắn nhỏ hơn 10 MiB?** Không; phải có hạn mức cho **output đã giải nén**.
9. **`readAllBytes` đọc ảnh có phải giải mã ảnh không?** Không; nó chỉ trả byte thô của file.
10. **Khi nào `readAllBytes` là lựa chọn hợp lý?** Khi tệp **nhỏ, có giới hạn đáng tin**, và nghiệp vụ thực sự cần giữ toàn bộ byte để xử lý.

**Kết luận:** `Files.readAllBytes` là công cụ **đọc trọn một file nhỏ vào một mảng**, không phải API streaming. Khi file lớn, không dự đoán được hoặc đến từ bên ngoài, ưu tiên `Files.newInputStream`, xử lý theo buffer cố định và giới hạn tài nguyên. Khi thật sự cần `byte[]`, áp giới hạn **trong quá trình đọc** và nhớ rằng các bản sao/mảng trung gian vẫn có chi phí bộ nhớ.