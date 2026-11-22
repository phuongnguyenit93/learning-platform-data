# Đọc, ghi byte với `Files` và lựa chọn cách xử lý theo kích thước dữ liệu trong Java

## 1. Bài toán: dữ liệu nhỏ và dữ liệu lớn cần hai chiến lược khác nhau

Giả sử ứng dụng phải xử lý ba kiểu tệp:

- Một ảnh đại diện có kích thước nhỏ: cần đọc toàn bộ dữ liệu để gửi lên API hoặc tính hash.
- Một tệp sao lưu vài gigabyte: cần sao chép sang vị trí khác mà không đưa tất cả nội dung vào RAM.
- Một bản ghi nhị phân được cập nhật liên tục: cần ghi thêm byte hoặc tạo bản mới theo quy tắc không ghi đè.

Với Java, lớp tiện ích **`java.nio.file.Files`** cung cấp các phương thức đọc/ghi byte rất gọn và các phương thức mở stream để xử lý từng phần. `Files` thuộc Java NIO.2, có từ **Java 7** và vẫn được dùng trong các phiên bản Java hiện đại.

Có hai nhóm tiếp cận chính:

1. **Đọc/ghi toàn bộ bằng `byte[]`:** `Files.readAllBytes(path)` và `Files.write(path, data, options...)`. Cách này thường tiện cho **dữ liệu nhỏ đã biết giới hạn**.
2. **Đọc/ghi từng khối:** `Files.newInputStream(path)` và `Files.newOutputStream(path, options...)`, kết hợp vòng lặp đọc buffer rồi ghi. Cách này giúp **bộ nhớ phụ thuộc kích thước buffer**, phù hợp khi dữ liệu lớn hoặc chưa rõ kích thước.

Ví dụ hai thao tác khác nhau:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("input.bin");
byte[] data = Files.readAllBytes(source);
```

Và:

```java
try (var input = Files.newInputStream(source)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        processChunk(buffer, count);
    }
}
```

Đây là các **đoạn minh họa đặt trong phương thức có `throws IOException`**. `source` phải được khai báo ở cùng phạm vi; `processChunk` là hàm của ứng dụng cần tự định nghĩa. Các ví dụ hoàn chỉnh có thể biên dịch độc lập nằm ở mục 10.

**Nguyên tắc quyết định:** Không có ngưỡng “mọi tệp dưới X MB đều nên `readAllBytes`” đúng cho mọi JVM. Phải xem **giới hạn bộ nhớ, mức độ đồng thời, loại dữ liệu, nhu cầu xử lý và kích thước tối đa được phép**. Một tệp 10 MB có thể nhỏ với công cụ chạy đơn lẻ nhưng quá lớn nếu hàng nghìn yêu cầu đồng thời cùng giữ mảng byte.

## 2. `Path` và `Files`: giá trị đường dẫn khác thao tác I/O

`Path` mô tả một đường dẫn thuộc hệ thống tệp, còn `Files` chứa các thao tác truy cập hệ thống tệp:

```java
Path file = Path.of("data", "payload.bin"); // Chỉ tạo giá trị Path.
byte[] content = Files.readAllBytes(file);  // Thực hiện I/O thật.
```

`Path.of` có từ **Java 11**. Nếu biên dịch theo Java 7/8, cách tạo đường dẫn tương thích là `Paths.get("data", "payload.bin")`. `Files.readAllBytes`, `Files.write`, `Files.newInputStream` và `Files.newOutputStream` đã có từ Java 7.

Tạo `Path` **không tạo tệp**, không kiểm tra tệp có tồn tại và không tự mở stream. Khi gọi các phương thức `Files`, chương trình có thể gặp `IOException` vì tệp không tồn tại, quyền bị từ chối, ổ đĩa đầy, lỗi mạng hoặc lỗi từ provider.

Các phương thức `Files` thao tác dựa trên dữ liệu **tại thời điểm gọi**. Tệp có thể bị tiến trình khác sửa, xóa hoặc thay thế trong lúc chương trình đang đọc/ghi. Không coi `Files.size(path)` hay `Files.exists(path)` là bảo đảm trạng thái sẽ không đổi về sau.

## 3. Đọc toàn bộ tệp nhỏ: `Files.readAllBytes`

Chữ ký quen thuộc:

```java
byte[] bytes = Files.readAllBytes(path);
```

Đây là biểu thức minh họa trong phương thức có biến `path` kiểu `Path` và khai báo/xử lý `IOException`. Phương thức cố gắng đọc toàn bộ byte của tệp vào **một mảng `byte[]` mới**, rồi trả mảng cho chương trình.

Ví dụ với tệp bốn byte:

```java
Path small = Path.of("small.bin");
byte[] data = Files.readAllBytes(small);

// Nếu nội dung thực là 00 01 02 FF, data.length == 4.
```

**Ưu điểm:**

- Mã ngắn, dễ đọc và dễ kiểm thử.
- Phù hợp khi thuật toán cần toàn bộ dữ liệu cùng lúc, ví dụ parse định dạng nhỏ, tính checksum hoặc xử lý tệp cấu hình nhị phân giới hạn.
- Không cần tự viết vòng lặp và không phải tự đóng một `InputStream` trong mã gọi `readAllBytes`.

**Giới hạn quan trọng:**

- Phải cấp phát một mảng đủ chứa dữ liệu, cộng thêm các vùng nhớ trung gian mà implementation có thể cần.
- Kích thước mảng Java bị giới hạn bởi số phần tử kiểu `int` và giới hạn thực tế của JVM; không thể coi `readAllBytes` là cách đọc an toàn một tệp nhiều gigabyte.
- Khi tệp quá lớn, việc cấp phát có thể gây `OutOfMemoryError`. Chỉ `catch IOException` **không bảo vệ được khỏi hết bộ nhớ**.
- Trong một dịch vụ có nhiều yêu cầu đồng thời, tổng dữ liệu của **mọi mảng còn sống** mới là yếu tố tiêu thụ heap.
- Một tệp nhỏ khi được kiểm tra có thể lớn lên lúc đọc nếu có writer khác; số byte thực tế không được bảo đảm cố định từ trước.

Javadoc của API cũng định hướng `readAllBytes` cho những trường hợp đọc toàn bộ byte là **thuận tiện**, chứ không phải công cụ mặc định cho tệp rất lớn.

### Đọc byte khác đọc văn bản

`byte[]` chứa **byte thô**, không tự có charset. Không tự giải mã ảnh, tệp nén, tài liệu PDF hay payload nhị phân như chuỗi UTF-8 chỉ vì Java có constructor `String`:

```java
byte[] bytes = Files.readAllBytes(path);
String text = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
```

Đây là đoạn minh họa phù hợp **chỉ khi biết nội dung là văn bản UTF-8**. Với dữ liệu nhị phân, decode có thể thay thế các byte không phải UTF-8 hợp lệ và không bảo toàn dữ liệu. Trong Java 11+, nếu cần xử lý **văn bản**, có thể dùng `Files.readString(path, StandardCharsets.UTF_8)` theo đúng hợp đồng charset. Bài này tập trung xử lý **byte**, nên ví dụ dùng tệp `.bin` và so sánh theo byte.

## 4. Ghi toàn bộ byte: `Files.write`

`Files.write(Path, byte[], OpenOption...)` ghi các byte được cung cấp vào đường dẫn. Với dữ liệu nhỏ đã ở sẵn trong RAM:

```java
byte[] header = {0x00, 0x01, 0x02, (byte) 0xff};

Path output = Path.of("output.bin");
Files.write(output, header);
```

Đoạn mã là ví dụ trong phương thức có `throws IOException`. Khi **không truyền `OpenOption`**, `Files.write` có cách mở mặc định tương ứng **`CREATE`, `TRUNCATE_EXISTING` và `WRITE`**:

- Nếu tệp chưa có, tạo tệp mới theo khả năng/quyền của file system.
- Nếu tệp đã có, **cắt nội dung cũ** trước khi ghi.
- Ghi byte của mảng vào tệp.

**Không gọi `Files.write(output, data)` khi cần bảo toàn nội dung cũ.** Nếu hệ thống không cho phép ghi đè, phải quy định rõ tùy chọn mở phù hợp.

### 4.1. Tạo mới, không được ghi đè

```java
Files.write(output, header,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE);
```

`CREATE_NEW` yêu cầu thao tác tạo file mới và **thất bại nếu mục tiêu đã tồn tại**. Nó khác với `CREATE`, vốn cho phép tệp đã tồn tại và mở theo các option khác. Chọn `CREATE_NEW` khi ghi đè tệp cũ là lỗi nghiệp vụ, ví dụ tạo artifact mang tên duy nhất.

### 4.2. Ghi thêm vào cuối tệp

```java
Files.write(output, new byte[] {42},
        java.nio.file.StandardOpenOption.APPEND);
```

Nếu `output` đã có, byte `42` được ghi thêm, thay vì thay thế toàn bộ. Với dạng `APPEND` đơn lẻ này, **không dựa vào việc tệp chưa tồn tại sẽ tự được tạo**. Nếu chính sách cho phép tạo mới khi chưa có:

```java
Files.write(output, new byte[] {42},
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND);
```

Nếu nhiều tiến trình/luồng cùng append, không tự suy ra **tính nguyên tử của cả một record**, thứ tự record hay khả năng an toàn ở mọi provider. Những đảm bảo này phụ thuộc file system, cách mở file và cơ chế đồng bộ của ứng dụng.

### 4.3. Tùy chọn mở quyết định rủi ro mất dữ liệu

| Tùy chọn | Ý nghĩa chính | Khi nên dùng |
| --- | --- | --- |
| `CREATE` | Tạo file nếu chưa tồn tại | Có thể dùng trong ghi mới/append khi chấp nhận file cũ |
| `CREATE_NEW` | Tạo mới và báo lỗi nếu đã tồn tại | Tránh ghi đè file cũ |
| `TRUNCATE_EXISTING` | Cắt file cũ khi mở để ghi | Cố ý thay toàn bộ nội dung |
| `APPEND` | Ghi ở cuối file | Log nhị phân hoặc các record nối tiếp, có hợp đồng rõ |
| `WRITE` | Mở để ghi | Mở output rõ mục đích |
| `READ` | Mở để đọc | Thường dùng với input stream |
| `SYNC` / `DSYNC` | Yêu cầu đồng bộ một số cập nhật xuống thiết bị lưu trữ theo hợp đồng | Khi có yêu cầu durability được thiết kế và kiểm thử cụ thể |

Đừng ghép các `OpenOption` theo thói quen. Một số tổ hợp không hợp lệ hoặc có hành vi phụ thuộc provider. Đặc biệt, **`APPEND` và `TRUNCATE_EXISTING` không diễn đạt một chính sách nhất quán**; thay vì dùng cả hai, hãy chọn rõ ghi thêm hoặc ghi thay thế.

Một lệnh `write` hoàn tất không nhất thiết có nghĩa một bản cập nhật nhiều bước trên nhiều file đã trở thành một **giao dịch nguyên tử**. Nếu ghi tệp cấu hình quan trọng, cần xem xét chiến lược tạo file tạm, đồng bộ dữ liệu, rồi di chuyển/đổi tên theo cơ chế hỗ trợ.

## 5. Đọc dữ liệu lớn: `Files.newInputStream` và buffer

Với dữ liệu lớn, không cần đưa toàn bộ byte vào mảng. Mở một `InputStream`, đọc theo khối cố định rồi xử lý từng khối:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long countBytes(Path source) throws IOException {
    long total = 0;
    byte[] buffer = new byte[8192];

    try (InputStream in = Files.newInputStream(source)) {
        int count;
        while ((count = in.read(buffer)) != -1) {
            total += count;
        }
    }
    return total;
}
```

Đây là **phương thức Java hoàn chỉnh để đặt trong một lớp**. Bộ đếm kiểu `long` giúp biểu diễn tổng số byte vượt giới hạn `int` mà không phải giữ dữ liệu trong RAM.

Điểm cần nhớ:

1. `newInputStream(source)` trả stream đọc tệp; **không đọc hết tệp ngay lúc mở**.
2. `in.read(buffer)` đọc **tối đa `buffer.length` byte** và trả số byte thực sự đọc được.
3. Phải dùng giá trị **`count`** để biết có bao nhiêu byte hợp lệ trong lượt đọc; không được mặc định mảng luôn đầy.
4. `-1` biểu thị đã đến cuối stream.
5. `try-with-resources` tự đóng stream khi thoát khối, kể cả khi có ngoại lệ; nếu đóng lỗi khi đang có lỗi chính, cơ chế suppressed exception có thể giữ thông tin lỗi đóng.
6. Stream và những thao tác đọc có thể ném `IOException`; ứng dụng phải báo lỗi hoặc có chính sách phục hồi thích hợp.

### 5.1. Không được xử lý toàn bộ buffer sau lần đọc ngắn

Đoạn sau **sai** khi dùng cho xử lý byte:

```java
byte[] buffer = new byte[8192];
int count = in.read(buffer);

if (count > 0) {
    process(buffer); // Sai nếu process luôn dùng đủ 8192 byte.
}
```

`in` và `process` là các phần phụ thuộc ứng dụng; đây là ví dụ **cố ý có lỗi**. Nếu chỉ có 120 byte mới, 8072 vị trí còn lại có thể chứa giá trị cũ hoặc chưa được dùng. Cần truyền số lượng byte hợp lệ:

```java
if (count > 0) {
    process(buffer, 0, count);
}
```

Đoạn này chỉ minh họa **hợp đồng xử lý một đoạn trong mảng**. API `process(...)` phải do ứng dụng định nghĩa. Tương tự, khi ghi stream, phải dùng `out.write(buffer, 0, count)`, **không** dùng `out.write(buffer)` nếu lượt đọc chưa đầy.

### 5.2. Kích thước buffer là cấu hình hiệu năng, không phải giới hạn tệp

Một mảng `byte[8192]` chỉ chiếm khoảng 8 KiB dung lượng phần tử. Nếu stream đọc một tệp 2 GiB, nhiều lần đọc/ghi sẽ tái sử dụng **cùng buffer**. Số byte xử lý có thể lớn hơn bộ nhớ buffer rất nhiều.

Các kích thước 4 KiB, 8 KiB, 16 KiB hoặc lớn hơn có thể hợp lý tùy môi trường; **không có một số tối ưu bắt buộc cho mọi hệ thống**. Hiệu năng còn phụ thuộc storage, network, provider, mức đồng thời và bộ đệm nội bộ.

`Files.newInputStream` không phải cam kết tự cung cấp buffering có kích thước phù hợp cho mọi cách đọc. Nếu cần giảm số lần gọi I/O khi chương trình đọc nhiều thao tác nhỏ, có thể sử dụng `BufferedInputStream`. Trong các ví dụ sao chép, việc đọc cả khối lớn và dùng buffered stream là hai kỹ thuật có thể kết hợp.

## 6. Ghi dữ liệu lớn: `Files.newOutputStream` và buffer

Muốn ghi lần lượt các đoạn byte, thay vì tạo một mảng lớn rồi `Files.write` một lần, dùng `OutputStream`:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static void writeBlock(Path target, byte[] block) throws IOException {
    try (OutputStream out = Files.newOutputStream(
            target,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE)) {
        out.write(block);
    }
}
```

Đây là phương thức minh họa đặt trong một lớp; `block` được truyền từ caller. Trong pipeline thực tế, phương thức thường nhận từng khối được sinh ra, tải về hoặc nhận từ input stream, rồi gọi `out.write(buffer, 0, count)` liên tục.

Nếu không truyền option cho `Files.newOutputStream(path)`, chế độ mở mặc định tương ứng **`CREATE`, `TRUNCATE_EXISTING` và `WRITE`**. Đây là cùng rủi ro ghi đè mà `Files.write` có khi không truyền option.

**Ghi không tự đồng nghĩa với flush thành công xuống thiết bị vật lý:** `OutputStream.close()` giúp giải phóng stream và flush những dữ liệu buffered theo hợp đồng của stream, nhưng yêu cầu durability sau mất điện, ghi đồng bộ hoặc cập nhật nhiều tệp là chủ đề thiết kế riêng. Khi gặp lỗi ghi, file đích có thể đã chứa **một phần dữ liệu**.

### 6.1. Tại sao phải đóng output stream?

`try-with-resources` bảo đảm gọi `close()` khi thoát phạm vi, kể cả khi thân `try` có `return` hoặc ném ngoại lệ. Điều này quan trọng vì output stream có thể giữ buffer và tài nguyên hệ điều hành.

```java
try (OutputStream out = Files.newOutputStream(target)) {
    out.write(data);
}
```

Đây là đoạn minh họa trong phương thức có `target` và `data` đã khai báo. Không đóng sớm rồi tiếp tục ghi, không bỏ qua ngoại lệ khi đóng chỉ vì thân đã ghi xong, và không gọi `close()` thủ công không cần thiết bên trong `try`.

### 6.2. Tạo mới hay ghi đè?

- Dữ liệu mới **không được phép đè lên file cũ**: `CREATE_NEW`.
- Dữ liệu được phép **thay thế** nội dung file cũ: chọn chính sách tạo/cắt phù hợp, sau khi xác thực quyền/đường dẫn.
- Dữ liệu được phép **nối vào file**: `APPEND` và có thể `CREATE` nếu cho phép tạo tệp mới.
- Đầu ra là file quan trọng phải cập nhật **nguyên vẹn**: cân nhắc ghi file tạm và thay thế theo quy trình an toàn hơn, thay vì truncate file đích ngay rồi ghi từng đoạn.

Không nên quyết định dựa vào `Files.exists` rồi mở file theo hai bước, vì file có thể thay đổi giữa lần kiểm tra và lần mở (*time-of-check/time-of-use*). `CREATE_NEW` truyền yêu cầu “không được tồn tại” vào chính thao tác mở/tạo, phù hợp hơn với mục tiêu tránh ghi đè.

## 7. Sao chép byte từng khối với bộ nhớ hữu hạn

Một ứng dụng muốn sao chép byte từ `source` sang `destination` có thể dùng:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static long copyInChunks(Path source, Path destination)
        throws IOException {

    byte[] buffer = new byte[8192];
    long copied = 0;

    try (InputStream in =
                 new BufferedInputStream(Files.newInputStream(source));
         OutputStream out =
                 new BufferedOutputStream(Files.newOutputStream(
                         destination,
                         StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE))) {

        int count;
        while ((count = in.read(buffer)) != -1) {
            if (count == 0) continue;
            out.write(buffer, 0, count);
            copied += count;
        }
    }
    return copied;
}
```

Đây là **phương thức tự chứa** để đặt trong một lớp. Phần `try-with-resources` tự đóng cả input lẫn output theo thứ tự ngược lúc rời khối. Việc đóng output buffered là cần thiết để đẩy những byte còn lại ra stream bên dưới.

**Các bất biến chính:**

- `copied` là tổng số byte **thực sự đọc từ input và ghi vào output stream** theo các lời gọi thành công, không được suy ra bằng số lượt `read` nhân kích thước buffer.
- Gọi `out.write(buffer, 0, count)` bảo đảm chỉ ghi phần buffer hợp lệ của lượt đọc.
- Chỉ giữ một buffer dữ liệu có kích thước cố định (ngoài bộ đệm của các stream); không cần nạp toàn bộ nội dung file.
- `CREATE_NEW` tránh cố ý ghi đè file đích đã tồn tại.
- Nếu có lỗi giữa chừng, file đích **có thể tồn tại và chỉ chứa một phần dữ liệu**. Caller phải quyết định giữ để điều tra, xóa tệp tạm, hoặc xử lý lỗi như thế nào.
- Đừng ngầm định mã này phù hợp mọi tình huống copy file đặc biệt như symbolic link, quyền/attributes, hoặc cấu trúc thư mục; nó sao chép **byte của stream được mở**, không phải mọi metadata.

### 7.1. Dùng `InputStream.transferTo` nếu không cần tự thao tác từng khối

Từ **Java 9**, `InputStream.transferTo(OutputStream)` hỗ trợ truyền toàn bộ nội dung còn lại sang một stream đích, trả về số byte truyền:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(
             destination,
             StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    long copied = in.transferTo(out);
    System.out.println("bytes = " + copied);
}
```

Đây là đoạn minh họa trong phương thức có `source`/`destination` kiểu `Path` và xử lý `IOException`. `transferTo` **không tự đóng** hai stream; `try-with-resources` vẫn cần để bảo đảm đóng tài nguyên.

So với vòng lặp buffer tự viết:

- `transferTo` gọn và thích hợp khi chỉ cần chuyển toàn bộ byte còn lại.
- Vòng lặp thủ công thích hợp khi cần kiểm tra từng khối, cập nhật tiến độ, hash, giới hạn byte, giải mã/xử lý từng phần hoặc kiểm soát timeout/cancellation.
- `transferTo` là API có từ Java 9, **không có trong Java 7 nguyên thủy**.
- Không suy ra mọi implementation `transferTo` đều là **zero-copy** ở mức hệ điều hành hoặc có cùng hiệu năng.

### 7.2. Khi chỉ muốn copy file, có `Files.copy`

Nếu không cần tự xử lý buffer, Java có các API chuyên dụng:

```java
Files.copy(source, destination);
```

Mặc định, `Files.copy(Path, Path, ...)` sẽ **thất bại nếu file đích đã tồn tại**, trừ khi cung cấp một tùy chọn phù hợp. Ví dụ cho phép thay đích:

```java
Files.copy(source, destination,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
```

Đây là các câu lệnh minh họa trong phương thức có `Path` và xử lý `IOException`. `Files.copy` là lựa chọn tốt để sao chép file **mà không cần biến đổi byte**. Các thuộc tính tệp, symbolic link, khả năng sao chép giữa provider và bảo đảm của thao tác được điều chỉnh bởi API/options; không mặc định mọi metadata được giữ nguyên tuyệt đối.

**Chọn công cụ theo nhu cầu:** không cần viết lại vòng lặp để sao chép nguyên tệp nếu `Files.copy` đáp ứng hợp đồng. Vòng lặp stream hữu ích khi bạn thật sự phải biến đổi hoặc quan sát nội dung trong lúc đọc/ghi.

## 8. Cách chọn API theo kích thước và cách sử dụng

| Tình huống | Cách tiếp cận | Vì sao |
| --- | --- | --- |
| Tệp nhỏ, có giới hạn rõ, cần toàn bộ byte cùng lúc | `Files.readAllBytes` | Cú pháp đơn giản, dữ liệu ở sẵn trong `byte[]` |
| Đã có mảng byte nhỏ cần ghi một lần | `Files.write` | Gọn, có thể quy định options tạo/ghi đè/append |
| Tệp lớn hoặc không biết trước kích thước | `Files.newInputStream` + buffer | Tránh giữ toàn bộ byte cùng lúc |
| Sinh dữ liệu lớn dần theo thời gian | `Files.newOutputStream` + ghi từng khối | Không phải tích lũy toàn bộ đầu ra trong RAM |
| Chuyển từ một stream sang một stream | Vòng lặp buffer hoặc `InputStream.transferTo` | Dữ liệu chạy theo luồng |
| Sao chép tệp nguyên trạng | `Files.copy` | API chuyên dụng và ngắn gọn |
| Đọc/ghi ở các offset cụ thể của tệp lớn | `FileChannel`/`SeekableByteChannel` khi có yêu cầu | Hỗ trợ vị trí, buffer và mô hình I/O nâng cao |
| Dữ liệu là **văn bản** chứ không phải nhị phân | `Files.readString/writeString` (Java 11+) hoặc Reader/Writer có charset | Tránh lẫn byte với ký tự |
| Cần kiểm soát dung lượng đầu vào không tin cậy | Giới hạn byte khi stream và chính sách từ chối | Không phụ thuộc chỉ vào `Files.size` |

### 8.1. Ngưỡng kích thước là quyết định nghiệp vụ

Ví dụ một ứng dụng đặt **ngưỡng minh họa 64 KiB**:

```java
private static final long MEMORY_LIMIT = 64 * 1024;

static String choose(Path path) throws IOException {
    return Files.size(path) <= MEMORY_LIMIT
            ? "readAllBytes" : "stream";
}
```

Đoạn này là **phương thức minh họa trong lớp**, và ứng dụng cần chọn ngưỡng dựa trên nguồn lực thực tế. Ngưỡng 64 KiB ở đây **không phải khuyến nghị bắt buộc của JDK**.

Bản thân phép `Files.size(path)` chỉ báo một kích thước **được quan sát tại thời điểm gọi**, và có thể không chính xác theo một số loại tệp/file system. Tệp có thể thay đổi sau đó. Nếu đầu vào không tin cậy, cần thêm **giới hạn byte trong quá trình đọc**, không chỉ kiểm tra metadata rồi mặc định `readAllBytes` sẽ luôn cấp phát ít bộ nhớ.

### 8.2. Bộ nhớ tổng cộng quan trọng hơn kích thước của một file

Giả sử 200 yêu cầu chạy đồng thời, mỗi yêu cầu giữ một `byte[]` cỡ 20 MiB. Chỉ riêng vùng byte trong các mảng đã xấp xỉ **4.000 MiB**, chưa tính overhead, cache, thread stacks, object khác hoặc bản sao trong pipeline.

Nếu thay bằng buffer 8 KiB cho mỗi yêu cầu, dữ liệu buffer phần này chỉ khoảng **1.600 KiB**, nhưng tổng tài nguyên còn phụ thuộc việc có stream/file descriptor, việc xếp hàng dữ liệu ở nơi khác và các thao tác sau đọc.

Do đó, ngay cả một tệp được gọi là “nhỏ” vẫn có thể làm quá tải heap khi chương trình giữ quá nhiều bản sao cùng lúc. Thiết kế nên có giới hạn upload/download, số lượng request đồng thời, backpressure và chính sách dừng khi vượt quá giới hạn.

### 8.3. Giới hạn mảng Java

`byte[]` dùng chỉ số kiểu `int` và không thể chứa số lượng phần tử tùy ý. Dù server có heap lớn, **mảng đơn** vẫn có giới hạn phần tử và overhead của JVM. Vì vậy, đối với file kích thước cực lớn, streaming là lựa chọn phù hợp hơn cho copy, checksum, tìm kiếm tuần tự hoặc xử lý block.

Không nên coi việc cấp thêm RAM cho JVM là cách duy nhất để “sửa” một đường đọc file không giới hạn. Lựa chọn thuật toán và cách truyền dữ liệu quyết định đáng kể tính an toàn.

## 9. Kiểm tra byte, tính nguyên vẹn và hiện tượng file thay đổi

### 9.1. Đọc byte phải có kỳ vọng nhị phân

Với các byte `00 01 02 FF`, giá trị `FF` có thể hiện thành `-1` nếu in riêng một `byte` dưới dạng số có dấu trong Java. Điều đó **không phải lỗi dữ liệu**. Để quan sát nội dung nhị phân, có thể in hex bằng `HexFormat` (Java 17+):

```java
byte[] bytes = {0, 1, 2, (byte) 0xff};
String hex = java.util.HexFormat.of().formatHex(bytes);
// hex = "000102ff"
```

Đoạn minh họa trên chạy từ Java 17+. `HexFormat` không có trong Java 7; còn `byte[]` và các API của `Files` đã có từ Java 7.

### 9.2. `Files.mismatch` kiểm tra hai file theo byte

Từ **Java 12**, `Files.mismatch(Path, Path)` trả:

- `-1L` nếu không tìm thấy vị trí khác biệt và hai file có cùng nội dung byte.
- Chỉ số `long` của byte đầu tiên khác nhau khi có khác biệt.
- Nếu một file là tiền tố của file kia, vị trí khác biệt là **độ dài file ngắn hơn**.

```java
long mismatch = Files.mismatch(source, destination);
boolean identical = mismatch == -1L;
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException`. `Files.mismatch` có thể phải đọc dữ liệu và vẫn chịu sự thay đổi đồng thời của file system. Nó giúp **kiểm tra hai file** mà code gọi không phải `readAllBytes` cả hai file để so sánh.

Nếu đã có mảng byte nhỏ trong RAM, `java.util.Arrays.equals(byteA, byteB)` là cách so sánh nội dung hai mảng. Không dùng `byteA == byteB` để so nội dung vì `==` so sánh **tham chiếu mảng**.

### 9.3. Hash/checksum khi cần độ tin cậy qua hệ thống

Một digest như SHA-256 có thể được tính dần bằng `MessageDigest.update(byte[], offset, length)` trong lúc đọc stream, không cần gom toàn bộ dữ liệu vào RAM. Điều này hữu ích khi cần so sánh qua mạng hoặc kiểm chứng dữ liệu tải về với hash mong đợi.

Tuy nhiên, **hash trùng không phải bằng chứng mật mã tuyệt đối rằng hai tệp giống hệt từng byte trong mọi mô hình đe dọa**, và hash không tự xác thực **nguồn** dữ liệu nếu kẻ tấn công có thể thay cả nội dung lẫn hash mong đợi. Khi cần xác minh nguồn tin cậy, sử dụng hash kèm cơ chế ký số/xác thực được thiết kế phù hợp.

### 9.4. Không đoán số byte được ghi khi chỉ nhìn file size trước đó

Một file có thể bị append bởi tiến trình khác trong khi đang copy. `Files.size` là phép quan sát, không phải “chốt” dữ liệu. Đối với yêu cầu cần một **snapshot nhất quán**, cần cơ chế tệp tạm, khóa, snapshot ở tầng storage hoặc quy trình đồng bộ phù hợp hệ thống. Một vòng lặp đọc tới EOF tự nó không bảo đảm mọi byte đều thuộc cùng một thời điểm.

## 10. Ví dụ Java 17+ hoàn chỉnh: lựa chọn theo kích thước và kiểm thử round-trip

Chương trình sau tự tạo tệp nhị phân trong **thư mục tạm**, kiểm tra hai chế độ:

1. Tệp nhỏ bốn byte: `Files.write` và `Files.readAllBytes`, in hex.
2. Tệp lớn 131.072 byte: sinh từng block, chọn streaming vì vượt ngưỡng minh họa 64 KiB, sao chép bằng buffer 8 KiB.
3. Kiểm tra hai file giống nhau theo từng byte, sau đó append một byte để thấy kết quả không còn giống nhau.
4. Xóa file tạm khi kết thúc để không phụ thuộc dữ liệu bên ngoài.

Tạo tệp **`FilesByteStrategyDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public final class FilesByteStrategyDemo {
    private static final long MEMORY_LIMIT = 64 * 1024;
    private static final int BUFFER_SIZE = 8 * 1024;

    private static String choose(Path path) throws IOException {
        return Files.size(path) <= MEMORY_LIMIT ? "readAllBytes" : "stream";
    }

    private static long copyInChunks(Path source, Path destination)
            throws IOException {
        long total = 0;
        byte[] buffer = new byte[BUFFER_SIZE];

        try (InputStream in =
                     new BufferedInputStream(Files.newInputStream(source));
             OutputStream out =
                     new BufferedOutputStream(
                         Files.newOutputStream(destination,
                             StandardOpenOption.CREATE_NEW,
                             StandardOpenOption.WRITE))) {
            int count;
            while ((count = in.read(buffer)) != -1) {
                if (count == 0) continue;
                out.write(buffer, 0, count);
                total += count;
            }
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("files-byte-demo-");
        Path small = folder.resolve("small.bin");
        Path large = folder.resolve("large.bin");
        Path copy = folder.resolve("large-copy.bin");

        try {
            Files.write(small, new byte[] {0, 1, 2, (byte) 0xff},
                StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            byte[] smallContent = Files.readAllBytes(small);
            System.out.println("small hex = "
                + HexFormat.of().formatHex(smallContent));
            System.out.println("small choice = " + choose(small));

            byte[] block = new byte[4 * 1024];
            for (int i = 0; i < block.length; i++) {
                block[i] = (byte) (i % 251);
            }
            try (OutputStream out = Files.newOutputStream(
                    large, StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                for (int i = 0; i < 32; i++) {
                    out.write(block);
                }
            }

            System.out.println("large size = " + Files.size(large));
            System.out.println("large choice = " + choose(large));
            long copied = copyInChunks(large, copy);
            System.out.println("copied bytes = " + copied);
            System.out.println("byte-for-byte equal = "
                + (Files.mismatch(large, copy) == -1L));

            Files.write(copy, new byte[] {42}, StandardOpenOption.APPEND);
            System.out.println("after append size = " + Files.size(copy));
            System.out.println("after append identical = "
                + (Files.mismatch(large, copy) == -1L));
        } finally {
            Files.deleteIfExists(copy);
            Files.deleteIfExists(large);
            Files.deleteIfExists(small);
            Files.deleteIfExists(folder);
        }
        System.out.println("cleanup = ok");
    }
}
```

Biên dịch bằng **JDK 17+** để dùng `HexFormat`, `Path.of`, `Files.mismatch`:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 FilesByteStrategyDemo.java
java FilesByteStrategyDemo
```

**Stdout chính xác trên môi trường kiểm thử thông thường:**

```text
small hex = 000102ff
small choice = readAllBytes
large size = 131072
large choice = stream
copied bytes = 131072
byte-for-byte equal = true
after append size = 131073
after append identical = false
cleanup = ok
```

### 10.1. Giải thích tệp nhỏ

`small.bin` chứa đúng bốn byte: `00 01 02 FF`. `readAllBytes` trả `byte[]` dài 4; `HexFormat` in `000102ff`. `Files.size(small)` nhỏ hơn `64 * 1024` nên hàm minh họa `choose` trả `readAllBytes`. Chương trình dùng lựa chọn đó để trình bày cách chọn chiến lược, không phải một hệ thống tự điều phối mọi lời gọi đọc file.

### 10.2. Giải thích tệp lớn

Mảng `block` có 4.096 byte, được ghi **32 lần**, nên file có `4096 × 32 = 131072` byte, lớn hơn ngưỡng `65536`. Hàm `choose` trả `stream`. `copyInChunks` cấp phát buffer 8.192 byte và sao chép tuần tự. Vì input tệp không đổi trong lúc test, `copied bytes = 131072`.

### 10.3. Kiểm chứng đúng byte

`Files.mismatch(large, copy) == -1L` xác nhận hai file bằng nhau từng byte sau khi copy. Sau đó `Files.write(copy, new byte[] {42}, APPEND)` thêm **một byte** vào cuối file đã tồn tại, khiến độ dài đích thành 131.073 và `Files.mismatch(...)` không còn trả `-1L`.

Ở đây byte `42` là giá trị thập phân của một byte; không có liên quan tới charset. Chương trình không chuyển payload sang `String` nên dữ liệu nhị phân được giữ nguyên.

### 10.4. Phạm vi được đảm bảo của ví dụ

- File và thư mục mẫu được tạo tại **vị trí tạm**; không in đường dẫn thực nên output không phụ thuộc tên thư mục.
- `try-with-resources` đóng stream; `finally` cố xóa các file và thư mục khi hoàn tất.
- Nếu môi trường không cho phép tạo/đọc/ghi/xóa file tạm hoặc có thay đổi từ tác nhân bên ngoài, chương trình có thể ném `IOException`; đó là giới hạn môi trường I/O.
- Hàm `choose` chỉ là **heuristic dựa trên `Files.size`**, không phải một bộ đọc **tự động giới hạn dung lượng**. Phần tiếp theo giải thích cách thực thi giới hạn thực tế khi đọc dữ liệu không tin cậy.

## 11. Đọc có giới hạn dung lượng khi đầu vào không tin cậy

Giả sử dịch vụ chỉ cho phép tối đa `MAX_BYTES` byte trên mỗi yêu cầu. Chỉ kiểm tra `Files.size(path)` trước khi đọc không đủ, vì kích thước có thể thay đổi hoặc metadata có thể không phản ánh đúng số byte sẽ nhận. Cần đếm số byte **thực đọc**, đồng thời từ chối khi vượt giới hạn.

Một bộ khung xử lý stream:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long consumeAtMost(Path path, long maxBytes)
        throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be nonnegative");
    }
    long total = 0;
    byte[] buffer = new byte[8192];

    try (InputStream in = Files.newInputStream(path)) {
        int count;
        while ((count = in.read(buffer)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException("Input exceeds limit");
            }
            total += count;
            // Xử lý chính xác count byte ở vị trí [0, count).
        }
    }
    return total;
}
```

Đây là **phương thức để đặt trong lớp Java**. Việc dùng `count > maxBytes - total` tránh lỗi tràn số khi tính `total + count` nếu `total` được quản lý trong giới hạn. Mã **không gom tất cả dữ liệu vào RAM**; việc xử lý từng khối phải được ứng dụng định nghĩa và không nên tự giữ lại toàn bộ các block nếu mục tiêu là giới hạn bộ nhớ.

Nếu chính sách yêu cầu đọc tối đa một số byte và **dừng ngay khi đạt giới hạn mà không kiểm tra phần tiếp theo**, đó là một hợp đồng khác với “từ chối nếu nguồn có nhiều byte hơn giới hạn”. Mẫu ở trên đọc cho đến EOF hoặc đến khi phát hiện vượt giới hạn, phù hợp với chính sách từ chối nguồn quá lớn.

Nếu cần kiểm tra tính nguyên vẹn hoặc xử lý một upload từ network, ứng dụng cũng phải đặt giới hạn thời gian, tốc độ truyền hoặc quota lưu trữ phù hợp; giới hạn số byte không thay thế những chính sách đó.

### Có nên gọi `readAllBytes` sau khi `Files.size <= maxBytes`?

Có thể khi **nguồn đáng tin cậy và ổn định**, dữ liệu nhỏ và API cần toàn bộ byte. Nhưng không coi kiểm tra size là **bảo đảm cứng** trong hệ thống có writer khác hoặc đầu vào đối kháng. Muốn giới hạn cứng trước khi cấp phát lớn, hãy dùng cơ chế đọc có giới hạn và lựa chọn cấu trúc xử lý phù hợp, thay vì `readAllBytes` trên nguồn không kiểm soát.

## 12. An toàn dữ liệu khi đang ghi file

### 12.1. Lỗi giữa chừng và file chỉ được ghi một phần

Giả sử đầu ra được tạo bằng `Files.newOutputStream` rồi chương trình ném `IOException` sau vài block. Một phần dữ liệu có thể đã nằm trong file đích. `try-with-resources` giúp đóng stream, nhưng **không tự rollback** nội dung file như một giao dịch cơ sở dữ liệu.

Nếu đây là file cấu hình hoặc artifact quan trọng, có thể thiết kế:

1. Tạo file tạm mới trong thư mục/quyền phù hợp.
2. Ghi đầy đủ nội dung vào file tạm, đóng và kiểm chứng khi cần.
3. Thay thế file đích bằng thao tác di chuyển/đổi tên phù hợp; nếu cần nguyên tử, xem xét `StandardCopyOption.ATOMIC_MOVE` và **xử lý tình huống provider không hỗ trợ**.
4. Dọn dẹp file tạm nếu thất bại; xác định rõ chính sách khôi phục.

`Files.move` với `ATOMIC_MOVE` không được bảo đảm luôn hỗ trợ mọi file system hoặc mọi cách thay thế file. Cần test môi trường triển khai và thiết kế xử lý lỗi, không kết luận chỉ cần một dòng `move` là đủ cho mọi yêu cầu durability.

### 12.2. Không ghi đè chỉ vì một đường dẫn trông có vẻ phù hợp

`Path.resolve` hoặc `normalize` xử lý giá trị đường dẫn. Nếu một phần tên file đến từ người dùng, một symbolic link hoặc `..` có thể làm phép mở file chạm đến vị trí ngoài phạm vi dự kiến.

Một phép kiểm tra `candidate.startsWith(root)` sau normalize chỉ giúp kiểm tra **cú pháp tên đường dẫn**, không tự ngăn thay đổi symbolic link hoặc race giữa kiểm tra và ghi. Khi thao tác với file không tin cậy, phải kết hợp policy về root, quyền, link, thao tác mở an toàn và ranh giới sở hữu dữ liệu.

### 12.3. Tránh copy file vào chính nó

Khi xử lý `source` và `destination`, đừng giả định hai chuỗi `Path.toString()` khác nhau chắc chắn là hai file khác nhau: symbolic link/hard link có thể dẫn đến cùng file. Nếu dùng output truncate lên file đầu vào, dữ liệu có thể bị mất ngay lúc mở output.

Với tệp **đã tồn tại** và khi cần xác minh danh tính file, `Files.isSameFile(source, destination)` có thể giúp kiểm tra, nhưng nó có I/O, có thể ném `IOException` và vẫn chịu race condition. Khi copy với mục tiêu tin cậy, chọn API chuyên dụng và chính sách tạo file, file tạm và xác minh phù hợp thay vì tự suy từ chuỗi tên.

## 13. Những ngộ nhận thường gặp

| Nhầm lẫn | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| `Files.readAllBytes` là lựa chọn tốt cho mọi kích thước file | Dễ OOME khi file lớn hoặc nhiều request đồng thời | Dùng khi biết dữ liệu nhỏ và có giới hạn |
| `Files.size` là kích thước bất biến suốt quá trình đọc | File có thể thay đổi hoặc metadata có giới hạn | Xem đó là một quan sát/heuristic, đặt quota khi đọc |
| `read(buffer)` luôn lấp đầy mảng | Lượt đọc có thể ít byte hơn kích thước buffer | Dùng giá trị `count` |
| `out.write(buffer)` luôn đúng sau mọi lượt `read` | Có thể ghi byte dư hoặc dữ liệu cũ trong buffer | Dùng `out.write(buffer,0,count)` |
| Ghi dữ liệu bằng `Files.write` không options là “chỉ tạo mới” | File cũ có thể bị truncate và thay thế | Dùng `CREATE_NEW` nếu phải từ chối file tồn tại |
| `APPEND` đơn lẻ luôn tạo file mới | Có thể lỗi nếu file chưa có | Kết hợp `CREATE` nếu hợp đồng cho phép tạo |
| Stream tự đóng khi biến ra khỏi scope | Không có bảo đảm đóng kịp thời theo vòng đời biến | Dùng `try-with-resources` |
| Coi `close()` là rollback khi write lỗi | File có thể đã được ghi một phần | Thiết kế ghi file tạm và thay thế |
| Đọc byte nhị phân qua `new String` không có rủi ro | Decode theo charset có thể làm thay đổi dữ liệu | Giữ `byte[]`/stream; chỉ decode văn bản đã biết charset |
| Cho rằng `Files.copy` luôn sao chép mọi metadata | Hành vi chịu API/options/provider | Xác định requirements về attributes |
| Cho rằng `InputStream.transferTo` tự đóng stream | API không quản lý ownership như vậy | Dùng `try-with-resources` |
| Cho rằng `transferTo` luôn là zero-copy | Implementation có thể truyền qua buffer | Đo hiệu năng trong môi trường thực |
| Dùng `int` cho tổng byte cực lớn | Có thể tràn số | Dùng `long` cho byte count |
| Xác nhận file tồn tại rồi an tâm ghi | Có race TOCTOU và rủi ro link/path traversal | Dùng options đúng và kiểm soát I/O thực |
| Chỉ so file size để kết luận nội dung giống nhau | Cùng độ dài vẫn có thể khác byte | Dùng `Files.mismatch`, digest hoặc kiểm tra nội dung phù hợp |
| Mỗi file nhỏ nên có một mảng riêng giữ tới hết request | Nhiều mảng đồng thời tốn heap | Tính tổng memory, streaming khi cần |
| Truyền đầu vào không tin cậy thẳng vào `readAllBytes` | Không giới hạn byte thực tế được nhận | Áp dụng giới hạn đọc và quota |
| Coi buffer 8 KiB là “chuẩn tối ưu” | Tốc độ phụ thuộc storage/profiling | Chọn kích thước theo đo đạc và mục tiêu |

## 14. Bài tập có đáp án

### Bài 1 — Chọn API cho hai cỡ tệp

Một tiện ích phải đọc một metadata blob 2 KiB và một log nhị phân 12 GiB. API nào phù hợp?

**Đáp án:** Metadata nhỏ, có giới hạn, có thể dùng `Files.readAllBytes` để xử lý gọn. Log 12 GiB không phù hợp với một mảng `byte[]`; dùng `newInputStream` cùng buffer để xử lý tuần tự, hoặc `Files.copy` nếu chỉ muốn sao chép nguyên file. Giới hạn tài nguyên thực tế vẫn phải được xác định theo ứng dụng.

### Bài 2 — Vì sao vòng lặp dưới đây sai?

```java
byte[] buffer = new byte[4096];
int count = in.read(buffer);
if (count > 0) {
    out.write(buffer);
}
```

**Đáp án:** `count` có thể nhỏ hơn 4096. `out.write(buffer)` ghi toàn bộ 4096 byte, kể cả phần không thuộc lượt đọc hợp lệ. Phải gọi `out.write(buffer,0,count)`, và đọc tiếp trong vòng lặp tới `-1`.

### Bài 3 — Tự chọn ngưỡng không phải chuẩn chung

Một chương trình quyết định file có size nhỏ hơn 64 KiB thì `readAllBytes`. Java có bắt buộc ngưỡng 64 KiB không?

**Đáp án:** Không. Đây chỉ là ngưỡng **minh họa của ứng dụng**. Quyết định thực tế phụ thuộc heap, dữ liệu đồng thời, thuật toán và độ tin cậy của metadata.

### Bài 4 — Ghi vào file đã tồn tại

Nếu gọi `Files.write(path, data)` mà không truyền option trên một tệp đã tồn tại, điều gì có thể xảy ra?

**Đáp án:** Với cách mở mặc định tương ứng `CREATE`, `TRUNCATE_EXISTING`, `WRITE`, nội dung cũ có thể bị xóa và thay bằng các byte mới. Nếu muốn tránh ghi đè, dùng `CREATE_NEW` với chính sách lỗi phù hợp.

### Bài 5 — Append một byte

Tệp `data.bin` có kích thước 100 byte. Gọi `Files.write(data, new byte[]{42}, APPEND)` trên file đó và không có writer khác. Kích thước dự kiến là bao nhiêu?

**Đáp án:** 101 byte. Đây là ghi **một byte** ở cuối file; nếu file không tồn tại mà chỉ truyền `APPEND`, không nên giả định nó được tạo. Thêm `CREATE` khi hợp đồng cho phép.

### Bài 6 — Lựa chọn sao chép

Nếu chỉ cần sao chép một file nguyên trạng, không cần hash, tiến độ hoặc biến đổi từng byte, có bắt buộc viết vòng lặp stream không?

**Đáp án:** Không. `Files.copy(source,destination)` là API chuyên dụng. Nếu muốn thay file đích, xác định rõ `REPLACE_EXISTING` và các yêu cầu metadata; nếu phải thao tác từng khối, dùng stream/`transferTo` theo phiên bản hỗ trợ.

### Bài 7 — So sánh nội dung file

Hai file đều dài 10.000 byte. Có thể kết luận chúng bằng nhau không?

**Đáp án:** Không. Chúng có thể khác nội dung ở bất kỳ byte nào. Trên Java 12+, có thể dùng `Files.mismatch(a,b)` để tìm vị trí khác biệt đầu tiên; kết quả `-1L` khi không có khác biệt theo lần kiểm tra.

### Bài 8 — Đếm byte rất lớn

Một vòng lặp copy chạy với file vài gigabyte. Vì sao `long copied` thích hợp hơn `int copied`?

**Đáp án:** `int` có thể tràn khi tổng vượt phạm vi số nguyên 32-bit; `long` biểu diễn được tổng byte lớn hơn nhiều. Tuy nhiên nó không tự làm mã copy an toàn khỏi các lỗi I/O hoặc giới hạn dung lượng lưu trữ.

### Bài 9 — Kiểm soát file không tin cậy

Một client cung cấp đường dẫn và khẳng định file chỉ 100 KiB; server kiểm tra `Files.size(path)` trước khi `readAllBytes`. Điều gì còn thiếu?

**Đáp án:** Kiểm soát nguồn/đường dẫn và quyền, tính ổn định của tệp giữa các bước, quota thực đọc, giới hạn đồng thời, xử lý file quá lớn và rủi ro symbolic link/path traversal. Nếu dữ liệu không đáng tin, dùng đọc streaming với giới hạn thực tế thay vì tin vào metadata một lần.

### Bài 10 — Hiểu output kiểm thử

Trong `FilesByteStrategyDemo`, vì sao `after append identical = false` sau khi chương trình đã từng in `byte-for-byte equal = true`?

**Đáp án:** Ban đầu `copyInChunks` tạo đích có cùng 131.072 byte; sau đó `Files.write(copy,new byte[]{42},APPEND)` thêm một byte, làm file đích thành 131.073 byte. Hai file không còn có cùng nội dung, nên `Files.mismatch` không trả `-1L`.

## 15. Checklist áp dụng cho chương trình Java hiện đại

- [ ] Xác định dữ liệu **nhị phân hay văn bản**; chỉ decode text khi biết charset.
- [ ] Chọn `readAllBytes` khi toàn bộ dữ liệu nhỏ, có giới hạn và có lý do cần ở trong RAM.
- [ ] Chọn stream/buffer hoặc `Files.copy` cho file lớn, file biến động và thao tác copy tuần tự.
- [ ] Không dùng một `Files.size` đơn lẻ như bảo đảm quota cứng; giới hạn số byte đọc thực tế.
- [ ] Dùng `out.write(buffer,0,count)` theo số byte `read` trả về.
- [ ] Dùng `long` cho tổng số byte đã đọc/ghi.
- [ ] Áp dụng `try-with-resources` cho `InputStream`/`OutputStream` được mở.
- [ ] Chọn `CREATE_NEW`/`APPEND`/`TRUNCATE_EXISTING` theo đúng quy tắc ghi đè dữ liệu.
- [ ] Xử lý `IOException`, file không tồn tại, quyền từ chối, file thay đổi và lỗi ghi giữa chừng.
- [ ] Có chính sách xóa hoặc giữ file đích ghi dở khi thất bại.
- [ ] Nếu cần bảo toàn nội dung file quan trọng, cân nhắc file tạm và thao tác thay thế theo khả năng file system.
- [ ] Với dữ liệu lớn và đồng thời, đo **tổng heap**, buffer, số file descriptor và throughput.
- [ ] Khi kiểm chứng file, so byte hoặc hash phù hợp, không dựa riêng vào kích thước.
- [ ] Đánh dấu rõ API theo phiên bản: `Files.readAllBytes/write/newInputStream/newOutputStream/copy` (Java 7), `InputStream.transferTo` (Java 9), `Files.mismatch` (Java 12), `HexFormat` (Java 17).
- [ ] Có test trên file rỗng, file nhỏ, file lớn hơn ngưỡng, đọc ngắn, đường dẫn không hợp lệ, lỗi quyền, append, không được ghi đè và cleanup.

## 16. Tổng kết

Với `java.nio.file.Files`, **đọc/ghi toàn bộ `byte[]`** là giải pháp đơn giản khi biết rõ kích thước và bộ nhớ cho phép. **Đọc/ghi qua stream theo từng khối** phù hợp hơn khi file lớn, kích thước thay đổi hoặc dữ liệu cần xử lý tuần tự. Các phương thức `Files.copy` và `InputStream.transferTo` giúp giảm mã tự viết trong các trường hợp chuyển byte, nhưng vẫn cần quản lý tài nguyên và hiểu chính sách ghi đè.

Không có một ngưỡng kích thước chuẩn áp dụng cho mọi ứng dụng: `Files.size` là một quan sát về metadata, không phải bảo đảm chống thay đổi hoặc chống hết bộ nhớ. Chọn cách xử lý dựa trên **giới hạn byte, bộ nhớ tổng thể, độ đồng thời, chính sách mở file, yêu cầu nguyên vẹn và rủi ro đầu vào không tin cậy**. Những nguyên tắc này dựa trên NIO.2 từ Java 7 và các tiện ích Java 9/12/17, đều còn phù hợp trong Java hiện đại.