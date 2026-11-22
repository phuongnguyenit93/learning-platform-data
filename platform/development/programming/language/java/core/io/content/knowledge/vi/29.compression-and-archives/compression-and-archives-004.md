# `putNextEntry`, `closeEntry` và hoàn tất ZIP archive trong Java

## 1. Bài toán: một ZIP hợp lệ cần nhiều hơn việc ghi byte

Trong Java Core, package `java.util.zip` hỗ trợ tạo và đọc tệp ZIP. Khi đóng gói nhiều file vào một archive, ứng dụng không thể chỉ nối byte của từng file rồi đổi phần mở rộng thành `.zip`. Định dạng ZIP chứa **các entry**, metadata, thông tin kiểm tra tính toàn vẹn và **central directory** cho phép công cụ đọc biết archive gồm những gì.

`ZipOutputStream` là lớp dùng để **ghi tuần tự ZIP archive** vào một `OutputStream`. Ba thao tác trọng tâm:

- **`putNextEntry(ZipEntry entry)`**: bắt đầu ghi một entry mới, đưa stream đến phần dữ liệu của entry đó.
- **`closeEntry()`**: kết thúc entry hiện tại, hoàn thành thông tin cần thiết cho entry và chuẩn bị trạng thái để ghi entry kế tiếp.
- **`finish()`**: hoàn tất **toàn bộ ZIP archive** (kể cả central directory) nhưng **không đóng output stream bên dưới**.
- Ngoài ra, **`close()`** của `ZipOutputStream` hoàn tất archive (nếu chưa hoàn tất) **và đóng cả stream bên dưới**.

**Điểm mấu chốt:** `closeEntry()` đóng **một thành phần** của ZIP; `finish()` và `close()` hoàn thành **cấu trúc toàn archive**. Tệp ZIP có thể có mọi entry đã được `closeEntry()` nhưng vẫn chưa là archive ZIP hoàn chỉnh nếu chưa ghi phần kết thúc/central directory.

Ví dụ sử dụng chuẩn:

```java
try (ZipOutputStream zip =
         new ZipOutputStream(Files.newOutputStream(zipPath))) {

    zip.putNextEntry(new ZipEntry("a.txt"));
    zip.write("A".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();

    zip.putNextEntry(new ZipEntry("b.txt"));
    zip.write("B".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();

} // close() tự hoàn tất archive và đóng stream bên dưới.
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập: cần khai báo `zipPath` và import API. Các ví dụ chạy hoàn chỉnh xuất hiện ở những phần sau.

## 2. `ZipOutputStream`, `ZipEntry` và vòng đời archive

Sơ đồ các trạng thái thao tác thường dùng:

```text
Mở ZipOutputStream
       |
       v
putNextEntry("a.txt")
       |
       v
write(bytes của a.txt)
       |
       v
closeEntry()
       |
       +------------------------------+
       |                              |
       v                              |
putNextEntry("b.txt")                 |
       |                              |
       v                              |
write(bytes của b.txt)                |
       |                              |
       v                              |
closeEntry()                          |
       |                              |
       +--> ... entry tiếp theo ... --+
       |
       v
finish() hoặc close()
       |
       v
Central directory + thông tin kết thúc
       |
       v
ZIP archive hoàn chỉnh
```

**`ZipEntry`** mô tả một thành phần trong archive. Nó mang tên entry (ví dụ `docs/readme.txt`), thời gian sửa đổi, phương pháp nén, kích thước và CRC-32 khi có. **`ZipOutputStream`** quản lý cách dữ liệu entry cùng metadata được ghi vào luồng ZIP.

Một ZIP nhiều file không phải là nhiều `ZipOutputStream` nối liền nhau: nó là **một `ZipOutputStream`**, có **nhiều lần `putNextEntry`/`closeEntry`**, rồi **một lần hoàn tất archive**.

| Phạm vi | Đối tượng/thao tác | Sự kiện kết thúc |
| --- | --- | --- |
| Một file/thư mục trong ZIP | `ZipEntry` | `closeEntry()` |
| Cả tệp ZIP gồm nhiều entry | `ZipOutputStream` | `finish()` hoặc `close()` |
| Đích nhận byte vật lý | `OutputStream` bên dưới | `close()` nếu quyền sở hữu thuộc về ZIP stream; hoặc bên sở hữu tự đóng |

**Thứ tự rất quan trọng**: `write` ngay trước `putNextEntry` không mang nghĩa “ghi một file ZIP”. Muốn ghi dữ liệu entry, phải mở entry trước.

## 3. ZIP bên trong chứa những phần nào?

Ở mức khái niệm, một ZIP archive thường có:

```text
+----------------------------+
| Local file header: a.txt   |
+----------------------------+
| Compressed data: a.txt     |
+----------------------------+
| (optional data descriptor) |
+----------------------------+
| Local file header: b.txt   |
+----------------------------+
| Compressed data: b.txt     |
+----------------------------+
| (optional data descriptor) |
+----------------------------+
| Central directory records  |
| a.txt, b.txt, offsets ...  |
+----------------------------+
| End of central directory   |
+----------------------------+
```

Đây là sơ đồ đơn giản, không đầy đủ tất cả biến thể của chuẩn ZIP (ví dụ ZIP64, extra fields, comments). Nhưng nó cho thấy vì sao **đóng entry cuối không đồng nghĩa archive được kết thúc**.

- **Local file header** đứng gần dữ liệu từng entry.
- **Data descriptor** có thể xuất hiện khi kích thước/CRC chưa biết trước và được ghi sau dữ liệu.
- **Central directory** chứa bảng metadata tổng hợp, offset và số entry.
- **End of central directory** kết thúc cấu trúc ZIP.

`ZipFile` thường dựa vào central directory để truy cập entry ngẫu nhiên. Vì thế nếu bạn chưa `finish()` hoặc `close()` mà cố mở archive qua `ZipFile`, không có cơ sở bảo đảm archive hợp lệ. Trái lại, `ZipInputStream` có thể đọc **một số local entry data** trong luồng chưa hoàn chỉnh, nhưng việc đọc một phần như vậy **không chứng minh toàn archive đúng cấu trúc**.

**Không dùng `flush()` như thay thế cho `finish()`.** `flush` chỉ chuyển các byte đã có qua một số tầng đệm theo hợp đồng stream, không có nghĩa central directory đã được ghi.

## 4. `putNextEntry(ZipEntry)`: bắt đầu entry mới

Cú pháp:

```java
ZipEntry entry = new ZipEntry("docs/readme.txt");
zip.putNextEntry(entry);
zip.write(content);
zip.closeEntry();
```

Đây là đoạn minh họa với `zip` và `content` đã được khai báo ở nơi khác.

Khi gọi `putNextEntry`:

1. `ZipOutputStream` bắt đầu entry có tên xác định.
2. Ghi thông tin cần thiết để xác định entry trong ZIP.
3. Thiết lập stream để những lời gọi `write(...)` tiếp theo thuộc về **entry mới**.
4. Nếu trước đó còn một entry đang hoạt động, `putNextEntry` sẽ **đóng entry trước** trước khi bắt đầu entry mới theo hợp đồng API Java.

Bước 4 giúp code có thể tự chuyển sang entry mới, nhưng **không phải lý do để bỏ `closeEntry()` trong code rõ ràng**. Gọi `closeEntry` tường minh giúp quản lý vòng đời, nơi xử lý lỗi và điểm kiểm tra metadata dễ hiểu hơn.

### Tên entry là đường dẫn logic trong ZIP

`new ZipEntry("docs/readme.txt")` có tên `docs/readme.txt`. Dấu gạch chéo `/` là ký hiệu thư mục thường dùng trong ZIP và **không phụ thuộc dấu phân cách đường dẫn hệ điều hành**.

| Tên entry | Ý nghĩa thông dụng |
| --- | --- |
| `report.txt` | File ở gốc ZIP |
| `docs/readme.txt` | File trong thư mục logic `docs/` |
| `docs/` | Entry biểu diễn thư mục |
| `images/a.png` | File bên trong thư mục logic `images/` |

`ZipEntry` **không tự tạo thư mục thật trên ổ đĩa**; nó chỉ lưu tên và metadata vào archive. Khi giải nén, chương trình đọc ZIP quyết định tạo cấu trúc thư mục tương ứng.

Nếu muốn thể hiện **thư mục rỗng** trong ZIP, cần một entry có tên kết thúc `/`, ví dụ `new ZipEntry("empty/")`, thường không ghi byte dữ liệu. Nếu chỉ chứa entry `docs/readme.txt` mà không chứa `docs/`, nhiều công cụ giải nén vẫn tạo thư mục cha khi cần. Nhưng một **thư mục rỗng** sẽ không được biểu diễn nếu không có entry thư mục riêng.

### Tên trùng và metadata

Trong một `ZipOutputStream`, các tên entry trùng nhau không được chấp nhận; có thể gặp `ZipException: duplicate entry: ...`. Ứng dụng đóng gói cần xác định chiến lược với tên trùng: từ chối, đổi tên hoặc chọn một nguồn duy nhất trước khi ghi. **Không thể “mở lại cùng entry để ghi thêm” sau khi đã kết thúc nó** chỉ bằng cách `putNextEntry` lần nữa cùng tên.

Nếu không đặt thời gian sửa đổi cho `ZipEntry`, implementation có thể dùng thời gian hiện tại. Vì vậy **byte ZIP đầu ra không nhất thiết giống hệt nhau qua các lần chạy** dù nội dung các file giống nhau. Muốn tạo ZIP có byte output tái lập trong build pipeline, phải kiểm soát thứ tự entry, timestamps, tên, metadata, charset, thuật toán/mức nén và môi trường tương thích.

## 5. `write` chỉ ghi dữ liệu thuộc entry hiện tại

Giữa `putNextEntry` và `closeEntry`, `ZipOutputStream.write(...)` ghi nội dung **của entry đang mở**.

```java
zip.putNextEntry(new ZipEntry("hello.txt"));
zip.write("Hello".getBytes(StandardCharsets.UTF_8));
zip.write(" World".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();
```

Hai `write` liên tiếp tạo nội dung giải nén là `Hello World` **trong cùng entry**, không phải hai file mới.

Đối với file lớn, nên truyền byte theo từng khối từ `InputStream`:

```java
try (InputStream input = Files.newInputStream(source)) {
    zip.putNextEntry(new ZipEntry("payload.bin"));

    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        zip.write(buffer, 0, count);
    }

    zip.closeEntry();
}
```

Đây là đoạn minh họa: `zip`, `source` cần khai báo, kèm import và xử lý ngoại lệ. Dùng vòng lặp giúp không cần `Files.readAllBytes` với file lớn. `closeEntry` phải được gọi **sau khi sao chép đủ dữ liệu**; không đóng entry trong mỗi lượt đọc.

### Không dùng Writer tùy tiện trực tiếp trên ZIP stream

`ZipOutputStream` là luồng **byte**, không phải luồng ký tự. Nếu nội dung là text, hãy chỉ định charset:

```java
byte[] utf8 = "Xin chào".getBytes(StandardCharsets.UTF_8);
zip.write(utf8);
```

Không dựa vào charset mặc định của máy. Nếu bọc `OutputStreamWriter` hoặc `BufferedWriter` bên trên `ZipOutputStream`, cần hiểu việc **buffered writer có thể giữ byte chưa flush** và `writer.close()` sẽ đóng cả ZIP stream trước khi ghi các entry tiếp theo. Đối với nhiều entry nhỏ, dùng `getBytes(StandardCharsets.UTF_8)` hoặc một tầng adapter được quản lý lifecycle cẩn thận thường đơn giản hơn.

## 6. `closeEntry()`: kết thúc file, chưa kết thúc archive

Chữ ký:

```java
void closeEntry() throws IOException;
```

`closeEntry()` hoàn tất entry hiện tại và đưa `ZipOutputStream` vào trạng thái có thể bắt đầu entry kế tiếp. Với entry dùng phương pháp nén `DEFLATED`, việc kết thúc entry yêu cầu hoàn tất luồng nén của entry đó và ghi các thông tin cần thiết để giải nén/kiểm tra dữ liệu. Với `STORED`, việc kết thúc có thể kiểm tra kích thước/CRC theo metadata đã khai báo.

**Điều `closeEntry()` không làm:**

- Không tạo ra entry tiếp theo.
- Không tự đóng `OutputStream` bên dưới.
- Không hoàn tất central directory toàn archive.
- Không hủy hoặc mở lại `ZipOutputStream`.
- Không bảo đảm file đích đã được ghi bền vững xuống ổ đĩa.

Có thể gọi nhiều lần `putNextEntry`, `write`, `closeEntry` trên **cùng** stream cho các tên entry khác nhau.

Đặt tên biến giúp tách hai cấp rõ ràng:

```text
putNextEntry("a.txt")  -> mở entry a
write(bytes)           -> ghi data cho a
closeEntry()           -> đóng a

putNextEntry("b.txt")  -> mở entry b
write(bytes)           -> ghi data cho b
closeEntry()           -> đóng b

finish() / close()     -> hoàn tất ZIP chứa a và b
```

Nếu không còn entry đang hoạt động, gọi `closeEntry()` không tạo ra một archive mới. Đừng dùng nó thay vì `finish()`.

## 7. `finish()` so với `close()` và `flush()`

Ba thao tác ở cuối thường bị nhầm:

| Lệnh | Hoàn tất ZIP? | Đóng `ZipOutputStream`? | Đóng stream bên dưới? | Khi dùng |
| --- | --- | --- | --- | --- |
| `closeEntry()` | **Không** | Không | Không | Sau mỗi entry |
| `flush()` | **Không** | Không | Không | Đẩy byte qua luồng theo hợp đồng flush; không hoàn tất archive |
| `finish()` | **Có** | Không đóng stream bên dưới | **Không** | Cần hoàn tất ZIP nhưng vẫn giữ quyền sở hữu sink |
| `close()` | **Có** | **Có** | **Có** | ZIP stream sở hữu sink; thích hợp với try-with-resources |

Cần đọc cột `finish()` chính xác: nó **kết thúc phần dữ liệu ZIP** và không đóng stream được bọc. Đối tượng `ZipOutputStream` không nên được tái sử dụng để bắt đầu thêm entry sau khi đã `finish()`, vì cấu trúc ZIP đã kết thúc. `finish()` **không phải một “checkpoint” để có thể append entry**.

`close()` vừa hoàn tất ZIP vừa đóng chính nó và stream đích. Nếu đang viết ra file qua `Files.newOutputStream(zipPath)`, **`try-with-resources` là lựa chọn mặc định**: code thoát scope bình thường hay có ngoại lệ đều đóng tài nguyên; nếu có lỗi I/O khi hoàn tất/đóng thì vẫn có thể phát sinh `IOException`, và archive lúc đó có thể không hợp lệ.

**Không nên gọi `finish()` bắt buộc trước mọi `close()`.** `close()` có trách nhiệm hoàn tất archive, vì vậy cách làm phổ biến chỉ cần đóng ZIP stream đúng cách. Gọi `finish()` tường minh hữu ích khi bạn cần xác định thời điểm kết thúc archive nhưng **chưa muốn đóng đích**.

### Khi nào dùng `finish()` thực tế?

Nếu một thư viện nhận `OutputStream` do caller sở hữu và trả về một ZIP hoàn chỉnh **mà không được phép đóng stream của caller**, có thể:

1. Tạo `ZipOutputStream` bọc output đã được cung cấp.
2. Ghi toàn bộ entry.
3. Gọi `finish()`.
4. **Không** gọi `close()` trên ZipOutputStream nếu điều đó sẽ đóng output của caller.
5. Để caller quản lý việc flush/close output theo hợp đồng của API.

Cần thiết kế rõ ownership và cleanup nếu có ngoại lệ khi ghi archive. Nếu cần giải phóng cả tài nguyên nén mà vẫn giữ đích mở, cách an toàn còn phụ thuộc cấu trúc lớp/adapter và vòng đời mong muốn; **đừng mặc định `close()` sẽ giữ stream bên dưới mở**.

## 8. Ví dụ Java 17+ độc lập: tạo ZIP nhiều entry và kiểm tra central directory

Ví dụ đầu tiên viết một ZIP vào **file tạm**, gồm một entry thư mục và hai file text. Nó gọi `closeEntry()` rõ ràng sau mỗi entry. Sau khi `try-with-resources` đóng `ZipOutputStream`, dùng `ZipFile` đọc lại từ ZIP đã hoàn tất.

Chương trình kiểm chứng:

- ZIP có đúng ba entry.
- Hai entry text đọc được nội dung mong đợi.
- Entry thư mục được nhận dạng bằng `isDirectory()`.

**Tệp `ZipLifecycleDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path zipPath = Files.createTempFile("zip-lifecycle-", ".zip");

        try {
            try (ZipOutputStream zip = new ZipOutputStream(
                    Files.newOutputStream(zipPath),
                    StandardCharsets.UTF_8)) {

                zip.putNextEntry(new ZipEntry("docs/"));
                zip.closeEntry();

                zip.putNextEntry(new ZipEntry("docs/a.txt"));
                zip.write("Xin chao".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();

                zip.putNextEntry(new ZipEntry("docs/b.txt"));
                zip.write("Java 17".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            } // close(): hoàn tất central directory rồi đóng file.

            try (ZipFile archive = new ZipFile(
                    zipPath.toFile(), StandardCharsets.UTF_8)) {

                System.out.println(
                        "So entry: " + archive.size());

                ZipEntry directory = archive.getEntry("docs/");
                System.out.println(
                        "Entry thu muc: " + directory.isDirectory());

                ZipEntry a = archive.getEntry("docs/a.txt");
                try (var input = archive.getInputStream(a)) {
                    System.out.println("a.txt: "
                            + new String(input.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }

                ZipEntry b = archive.getEntry("docs/b.txt");
                try (var input = archive.getInputStream(b)) {
                    System.out.println("b.txt: "
                            + new String(input.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }
            }
        } finally {
            Files.deleteIfExists(zipPath);
        }
    }
}
```

Chạy với **JDK 17+**:

```bash
javac ZipLifecycleDemo.java
java ZipLifecycleDemo
```

**Stdout khi tạo/đọc ZIP thành công:**

```text
So entry: 3
Entry thu muc: true
a.txt: Xin chao
b.txt: Java 17
```

Giải thích từng bước:

1. `Files.createTempFile` tạo nơi lưu ZIP thử nghiệm.
2. `ZipOutputStream` bọc stream ghi file và dùng `UTF-8` cho **tên entry**.
3. `docs/` có tên kết thúc `/`, không chứa nội dung; `closeEntry` kết thúc entry thư mục.
4. `docs/a.txt`, `docs/b.txt` lần lượt được mở bằng `putNextEntry`, ghi byte UTF-8 rồi đóng bằng `closeEntry`.
5. Thoát `try` gọi `zip.close()` tự động, giúp hoàn tất archive.
6. `ZipFile` đọc một ZIP hợp lệ với central directory; `getEntry` lấy đúng tên và `getInputStream` trả nội dung giải nén.
7. `finally` xóa file tạm sau khi `ZipFile` đã đóng. Hành vi xóa có thể bị ảnh hưởng nếu tiến trình khác can thiệp vào file, nhưng chương trình không phụ thuộc tên file temp ngẫu nhiên.

Vì ví dụ kiểm tra entry theo tên, không in thứ tự mà `ZipFile.entries()` liệt kê, đầu ra không phụ thuộc thời gian tạo file hay kích thước ZIP nén thực tế.

## 9. Ví dụ Java 17+: chứng minh `finish()` không đóng sink

Để thấy khác biệt giữa `finish()` và `close()`, ta tạo một stream bên dưới có cờ `closed`. Sau `finish()`, cờ chưa đổi. Chỉ khi gọi `close()` trên ZIP stream, sink mới bị đóng.

**Tệp `ZipFinishDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import java.io.ByteArrayInputStream;

public class ZipFinishDemo {
    private static class TrackedOutputStream extends FilterOutputStream {
        boolean closed = false;

        TrackedOutputStream(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutputStream destination = new TrackedOutputStream(bytes);
        ZipOutputStream zip = new ZipOutputStream(
                destination, StandardCharsets.UTF_8);

        try {
            zip.putNextEntry(new ZipEntry("one.txt"));
            zip.write("OK".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.finish();
            System.out.println("Sink closed after finish: "
                    + destination.closed);

            try (ZipInputStream input = new ZipInputStream(
                    new ByteArrayInputStream(bytes.toByteArray()),
                    StandardCharsets.UTF_8)) {
                ZipEntry entry = input.getNextEntry();
                System.out.println("First entry: " + entry.getName());
                System.out.println("Body: " + new String(
                        input.readAllBytes(), StandardCharsets.UTF_8));
                input.closeEntry();
            }
        } finally {
            zip.close();
        }

        System.out.println("Sink closed after close: "
                + destination.closed);
    }
}
```

Biên dịch/chạy:

```bash
javac ZipFinishDemo.java
java ZipFinishDemo
```

**Stdout khi thành công:**

```text
Sink closed after finish: false
First entry: one.txt
Body: OK
Sink closed after close: true
```

**Phân tích:**

- `zip.finish()` ghi phần kết thúc ZIP; `TrackedOutputStream.closed` vẫn `false`.
- `ZipInputStream` đọc từ bản sao `byte[]` lúc ZIP đã được hoàn tất.
- `zip.close()` được gọi trong `finally`, đóng ZIP stream và stream bên dưới; cờ `closed` thành `true`.
- `ByteArrayOutputStream.close()` trên JDK chuẩn không khiến dữ liệu đã ghi không còn truy cập được; ở đây ta dùng wrapper theo dõi để quan sát việc phương thức `close` thực sự được gọi xuống sink.

**Đây là ví dụ minh họa ownership, không phải khuyến nghị luôn gọi cả `finish()` và `close()`.** Nếu mục tiêu là giữ stream bên dưới mở cho caller, mã production phải xác định rõ ai sở hữu và ai có quyền đóng stream, thay vì dùng chính mẫu `finally { zip.close(); }` khi caller không cho phép đóng sink.

## 10. `DEFLATED` và `STORED`: metadata khác nhau

Hai phương pháp phổ biến do `ZipEntry` hỗ trợ:

| Phương pháp | Đặc điểm | Metadata phải cung cấp trước? |
| --- | --- | --- |
| `ZipEntry.DEFLATED` | Nén DEFLATE, mặc định của `ZipOutputStream` | Thường có thể để stream tự tính size/CRC khi ghi |
| `ZipEntry.STORED` | Lưu byte nguyên dạng, không nén | **Size, compressed size và CRC-32 phải xác định trước** |

Với `DEFLATED`, nếu chưa đặt size, compressed size hoặc CRC, `ZipOutputStream` có thể tính toán và ghi thông tin thích hợp sau khi xử lý dữ liệu. Bạn vẫn phải gọi `closeEntry()` để kết thúc entry; không thể dựa vào kích thước mảng đầu vào làm kích thước đã nén.

Với **`STORED`**, ZIP không nén byte nên compressed size bằng size. Cần khai báo kích thước và CRC-32 đúng trước khi ghi; nếu thiếu hoặc dữ liệu ghi không khớp, có thể gặp `ZipException`.

Ví dụ phần metadata của một STORED entry:

```java
byte[] payload = new byte[] {10, 20, 30};
CRC32 checksum = new CRC32();
checksum.update(payload);

ZipEntry raw = new ZipEntry("raw.bin");
raw.setMethod(ZipEntry.STORED);
raw.setSize(payload.length);
raw.setCompressedSize(payload.length);
raw.setCrc(checksum.getValue());

zip.putNextEntry(raw);
zip.write(payload);
zip.closeEntry();
```

Đây là đoạn mã minh họa, giả định đã import `java.util.zip` và có biến `zip` đang mở. Hãy tính CRC từ **chính các byte đầu vào thực tế**. `CRC32` là mã kiểm tra phát hiện lỗi tình cờ, **không phải** chữ ký mật mã hoặc công cụ chống sửa đổi có chủ ý.

### Vì sao `STORED` cần CRC trước?

Với một số cách ghi nội dung ZIP không nén, header phải chứa chính xác thông tin size/CRC trước khi ghi dữ liệu. `ZipOutputStream` thực hiện xác thực các giá trị này theo hợp đồng phương pháp STORED.

Nếu không biết kích thước hoặc phải stream dữ liệu nguồn không thể đọc lại, có thể sử dụng `DEFLATED` để ZIP tự tính thông tin trong quá trình ghi (dù dữ liệu có thể không nén nhỏ được), hoặc cân nhắc phương án spool dữ liệu ra vùng tạm trước khi tạo STORED entry.

## 11. Ví dụ Java 17+: tạo STORED entry với size/CRC chính xác

Chương trình sau tạo ZIP trong bộ nhớ, lưu `raw.bin` **không nén** rồi đọc lại, kiểm tra phương pháp và byte dữ liệu.

**Tệp `StoredEntryDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class StoredEntryDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = new byte[] {10, 20, 30, 40};
        CRC32 crc = new CRC32();
        crc.update(payload);

        ZipEntry raw = new ZipEntry("raw.bin");
        raw.setMethod(ZipEntry.STORED);
        raw.setSize(payload.length);
        raw.setCompressedSize(payload.length);
        raw.setCrc(crc.getValue());

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(
                sink, StandardCharsets.UTF_8)) {
            zip.putNextEntry(raw);
            zip.write(payload);
            zip.closeEntry();
        }

        try (ZipInputStream input = new ZipInputStream(
                new ByteArrayInputStream(sink.toByteArray()),
                StandardCharsets.UTF_8)) {
            ZipEntry read = input.getNextEntry();
            byte[] actual = input.readAllBytes();

            System.out.println("Method STORED: "
                    + (read.getMethod() == ZipEntry.STORED));
            System.out.println("Uncompressed size: " + read.getSize());
            System.out.println("Bytes match: "
                    + Arrays.equals(payload, actual));
            input.closeEntry();
        }
    }
}
```

Lệnh:

```bash
javac StoredEntryDemo.java
java StoredEntryDemo
```

**Stdout khi thành công:**

```text
Method STORED: true
Uncompressed size: 4
Bytes match: true
```

Ví dụ minh họa đầy đủ các bước cần cho một STORED entry:

1. Tính CRC32 trên payload trước khi tạo entry.
2. Đặt `method=STORED`, size, compressed size và CRC.
3. Gọi `putNextEntry`, ghi chính xác số byte đã khai báo.
4. `closeEntry` hoàn tất entry và xác minh metadata.
5. Đóng ZIP stream để hoàn tất archive.
6. Giải nén ra byte rồi so sánh nội dung.

Nếu dữ liệu là byte từ nguồn bên ngoài, **không được tính CRC trên bản dữ liệu khác** rồi ghi payload đã thay đổi. Sai CRC hoặc kích thước có thể gây `ZipException` lúc đóng entry.

## 12. Thứ tự gọi API đúng trong các tình huống thực tế

### 12.1. Nhiều file trong một ZIP

```text
ZipOutputStream.open
  putNextEntry(file 1)
    write...
  closeEntry()
  putNextEntry(file 2)
    write...
  closeEntry()
  ...
ZipOutputStream.close()  => archive hoàn chỉnh + sink đóng
```

Trường hợp thông dụng nhất: dùng một `ZipOutputStream` trong `try-with-resources`, đóng entry rõ ràng, để `close()` hoàn tất ZIP.

### 12.2. Caller sở hữu OutputStream

```text
Caller tạo OutputStream
  thư viện tạo ZipOutputStream(output)
    putNextEntry / write / closeEntry ...
    finish()
  trả lại quyền kiểm soát sink cho caller
Caller quyết định flush/close sink
```

Lưu ý phải có quy ước rất rõ về **quyền đóng**. `ZipOutputStream.close()` không phù hợp nếu caller yêu cầu sink vẫn mở. Đôi khi có thể dùng một wrapper non-closing, nhưng cần kiểm soát vòng đời deflater và mọi lỗi I/O; không áp dụng workaround chỉ vì muốn tránh thiết kế ownership rõ ràng.

### 12.3. Dữ liệu chưa ghi hết mà đã closeEntry

```text
putNextEntry("large.bin")
write(chunk 1)
closeEntry()
write(chunk 2)  <-- KHÔNG thuộc large.bin; đây là lỗi quy trình
```

Sau khi `closeEntry()`, nội dung entry đã kết thúc. Chương trình phải đọc/ghi **đầy đủ** payload trước khi đóng entry. Không có API chuẩn để tiếp tục append vào cùng entry sau khi đã đóng nó.

### 12.4. File input gặp IOException khi đang đóng gói

Nếu đọc file nguồn hoặc ghi ZIP phát sinh lỗi trước khi entry hoàn chỉnh, **đừng âm thầm bỏ qua lỗi rồi công bố archive hợp lệ**. Có thể không hoàn tất được entry, hoặc dù ghi xong central directory thì dữ liệu thành phần không đại diện cho nội dung mong muốn.

Quy tắc production nên là:

1. Ghi ZIP vào **tệp tạm**.
2. Dùng `try-with-resources` bảo đảm đóng stream.
3. Nếu quá trình ghi hoàn toàn thành công, **kiểm tra archive nếu cần**.
4. Chỉ khi thành công mới publish/rename tệp tạm sang tên chính thức.
5. Nếu có lỗi, loại bỏ artifact dở dang theo chính sách; không tiếp tục sử dụng như archive thành công.

Khi sử dụng `Files.move` với `ATOMIC_MOVE`, tính khả dụng phụ thuộc provider/filesystem; cần có phương án khi không hỗ trợ. Việc publish atomically không tự thay thế `fsync` hoặc cơ chế độ bền dữ liệu khi cần bảo đảm chống mất điện.

## 13. `closeEntry` có bắt buộc trước `putNextEntry` tiếp theo không?

Theo Java SE 17 API, `putNextEntry` **đóng entry hiện tại nếu nó vẫn còn hoạt động**. Tương tự, `finish()` có trách nhiệm kết thúc ZIP archive và có thể hoàn tất entry đang mở.

Ví dụ về mặt ý tưởng:

```java
zip.putNextEntry(new ZipEntry("a.txt"));
zip.write(new byte[] {65});

// putNextEntry sẽ đóng a.txt trước khi mở b.txt.
zip.putNextEntry(new ZipEntry("b.txt"));
zip.write(new byte[] {66});

zip.finish();
```

Đây là đoạn minh họa sử dụng biến `zip` đã tồn tại. **Không khuyến khích dùng sự tự động này để che giấu trạng thái code.** Lập trình viên nên đóng entry rõ ràng ở điểm dữ liệu hoàn tất, và dùng `try-with-resources` để đảm bảo hoàn tất archive.

Lợi ích của cách tường minh là:
- Có thể đặt logging và số byte đã ghi cạnh entry tương ứng.
- Lỗi CRC/size của entry dễ được quy về entry đang xử lý.
- Phân biệt rõ lỗi đọc nguồn, lỗi ghi ZIP và lỗi finalize.
- Dễ refactor thành hàm `addEntry(zip, source)` có hợp đồng cụ thể.

`closeEntry()` và `close()` không có cùng quyền tác động; nhầm hai tên này sẽ làm hỏng luồng xử lý nhiều file.

## 14. Ghi entry thư mục và đường dẫn tương đối an toàn

Khi tạo archive từ một thư mục nguồn, phải xây tên entry **tương đối so với thư mục gốc**:

```java
Path root = Path.of("/source-folder").toAbsolutePath().normalize();
Path file = root.resolve("images/logo.png");
String entryName = root.relativize(file).toString().replace('\\', '/');
```

Đây là minh họa, không chạy độc lập trên mọi hệ điều hành vì đường dẫn ví dụ cần tồn tại. Quy tắc chuyển `\\` sang `/` hữu ích cho cách biểu diễn tên entry ZIP nhất quán.

Nhưng **chuẩn hóa dấu phân cách chưa đủ để bảo mật**. Không nên nhận tên entry không đáng tin rồi lưu vào ZIP mà bỏ kiểm tra:

- Tránh tên tuyệt đối, traversal `../`, đường dẫn rỗng, các entry gây xung đột.
- Tránh nhúng tên file có thông tin nhạy cảm hoặc đường dẫn máy chủ tuyệt đối.
- Xác định chính sách với symbolic links (bỏ qua, ghi nội dung đích hay biểu diễn link theo một cách đặc biệt).
- Không mặc định ZIP entry tự có quyền/mode metadata tương thích giữa mọi công cụ.

**Khi giải nén ZIP từ người khác** (không phải phần tạo ZIP cốt lõi ở bài này), cần ngăn **Zip Slip**: giải quyết entry name dưới thư mục đích, chuẩn hóa, kiểm tra nó không thoát khỏi thư mục được cho phép, và xử lý symbolic link/TOCTOU theo mô hình đe dọa. Đồng thời giới hạn tổng dung lượng giải nén, số entry, tỉ lệ nén để tránh zip bomb.

Mục tiêu ở phần tạo ZIP là đặt tên entry rõ ràng và tránh tạo archive gây nguy hiểm hoặc khó giải nén.

## 15. Charset, compression level và metadata

### 15.1. Charset cho **tên entry**

`ZipOutputStream(OutputStream out, Charset charset)` cho phép chọn cách mã hóa **tên entry và comment**. Ví dụ:

```java
ZipOutputStream zip = new ZipOutputStream(
        output, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, biến `output` phải là `OutputStream` đang mở.

**Charset trong constructor không tự mã hóa nội dung file.** Nếu bạn muốn lưu văn bản UTF-8, phải mã hóa payload riêng:

```java
zip.write("Tiếng Việt".getBytes(StandardCharsets.UTF_8));
```

Khi giải nén text, phía đọc cũng phải dùng đúng charset của **nội dung**. Đừng đánh đồng charset cho entry names với charset của từng file.

### 15.2. `setLevel(int)` chỉ là mức nén

`zip.setLevel(Deflater.BEST_COMPRESSION)` thay đổi mức nén dùng cho các entry **DEFLATED tiếp theo**. Nó không thay nội dung giải nén, không biến ZIP thành định dạng khác và không thể được dùng để làm archive “hoàn chỉnh” khi chưa `finish/close`.

`ZipEntry.STORED` giữ nguyên dữ liệu, không nén; vì vậy mức nén DEFLATE không có ý nghĩa với entry STORED.

### 15.3. Comment và timestamp

`ZipEntry.setTime(long)` cho phép đặt thời gian sửa đổi. `ZipOutputStream.setComment(String)` đặt comment cho archive. Những metadata này có thể ảnh hưởng byte ZIP và khả năng tái lập khi build.

Trong các pipeline yêu cầu **reproducible builds**, cần sắp xếp thứ tự entry và chuẩn hóa metadata; không tự suy ra ZIP có cùng byte chỉ vì payload logic giống nhau.

## 16. Lưu ý dành cho JAR và GZIP

- **JAR** cũng dựa trên ZIP. `JarOutputStream` kế thừa `ZipOutputStream`, có thể dùng `putNextEntry`/`closeEntry` và `finish/close`. JAR có các quy ước bổ sung như `META-INF/MANIFEST.MF`, chữ ký số và metadata nên không coi một ZIP bất kỳ là JAR triển khai đúng mọi yêu cầu.
- **GZIP** là định dạng khác, thường biểu diễn một luồng nén thay vì archive gồm nhiều entry ZIP. `GZIPOutputStream` có `finish()`/`close()` nhưng **không có `putNextEntry(ZipEntry)`** giống ZIP.

Đừng nhầm:
- `ZipOutputStream`: nhiều tên entry, metadata và central directory.
- `GZIPOutputStream`: luồng dữ liệu nén GZIP, không hỗ trợ danh sách entry theo mô hình ZIP.
- `JarOutputStream`: ZIP có các quy ước JAR bổ sung.

Sự khác biệt này quan trọng khi chọn API phù hợp: đóng gói nhiều file thành một archive dùng ZIP/JAR; nén một luồng dữ liệu thô có thể dùng GZIP hoặc `DeflaterOutputStream` tùy format yêu cầu.

## 17. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả hoặc nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Gọi `write` khi chưa `putNextEntry` | Không có entry hiện tại để chứa dữ liệu | Mở entry trước |
| Gọi `closeEntry` rồi tin ZIP hoàn tất | Chưa có central directory toàn archive | Gọi `finish()` hoặc `close()` |
| Chỉ `flush()` rồi publish ZIP | Stream chưa chắc ghi cấu trúc kết thúc | Hoàn tất ZIP trước khi publish |
| Dùng `close()` rồi muốn thêm entry | Stream đã đóng | Tạo archive mới hoặc thiết kế lại luồng |
| Gọi `finish()` rồi muốn `putNextEntry` | Archive đã hoàn tất | Chỉ finish sau entry cuối |
| Đóng zip bên trong hàm tiện ích khi caller sở hữu sink | Sink bị đóng ngoài ý muốn | Hợp đồng ownership rõ; dùng finish nếu cần giữ sink mở |
| Quên `closeEntry` khi ghi liên tiếp | Có thể vẫn tự đóng khi putNextEntry, nhưng khó kiểm soát vòng đời | Đóng entry rõ ràng sau khi ghi đủ |
| Đặt `STORED` không khai báo size/CRC | `ZipException` | Tính và khai báo trước khi putNextEntry |
| Khai báo sai size hoặc CRC | Lỗi khi đóng/ghi entry | Tính từ byte thực tế, đảm bảo dữ liệu không đổi |
| Dùng lại tên entry | Duplicate entry | Kiểm tra xung đột tên trước khi ghi |
| Coi tên `folder/file.txt` là đường dẫn OS hoàn chỉnh | Không chuẩn, có thể làm lộ đường dẫn host | Dùng đường dẫn tương đối với `/` |
| Tưởng constructor charset mã hóa payload text | File text giải nén sai mã | Tự encode nội dung bằng UTF-8 |
| In kích thước ZIP và tin luôn cố định | Compression và metadata có thể thay đổi | Kiểm tra số entry/nội dung thay vì byte length |
| Ghi ZIP trực tiếp vào artifact chính thức trước khi thành công | Có thể để lại ZIP hỏng sau lỗi | Ghi tệp tạm, xác minh, sau đó publish |
| Dùng ZipInputStream đọc được một entry rồi kết luận ZIP hoàn chỉnh | Local entry có thể đọc trước central directory | Hoàn tất bằng finish/close và kiểm tra bằng ZipFile khi cần |

## 18. Bài tập tự kiểm tra

### Câu 1. Hai entry đã `closeEntry()`, nhưng chưa `finish()`/`close()`

Có bảo đảm `ZipFile` đọc được archive không?

**Không.** `closeEntry()` kết thúc từng entry, trong khi ZIP archive thường cần central directory và phần kết thúc. `ZipFile` dựa trên metadata tổng hợp; cần hoàn tất ZIP đúng cách.

### Câu 2. Đã gọi `zip.finish()` khi sink do caller sở hữu

Sink có tự đóng không, và có nên gọi `putNextEntry` tiếp không?

**Không.** `finish()` không đóng stream bên dưới. Nhưng ZIP đã được hoàn tất, không nên ghi thêm entry; caller quản lý sink theo hợp đồng của mình.

### Câu 3. Dùng `ZipEntry.STORED` với payload đã biết

Những metadata nào phải có?

**Size**, **compressed size** (bằng size) và **CRC-32** chính xác của payload. Nếu thiếu hoặc dữ liệu không khớp có thể gặp `ZipException`. CRC-32 không thay thế xác thực mật mã.

### Câu 4. Lưu `src/docs/readme.txt` thành entry `docs/readme.txt`

Có bắt buộc tạo entry `docs/` trước không?

Không bắt buộc cho **mọi công cụ giải nén** nếu chỉ muốn giải nén file trong thư mục logic; nhiều công cụ tạo thư mục cha theo tên file. Nhưng muốn ZIP biểu diễn **thư mục rỗng** hoặc kiểm soát cấu trúc thư mục tường minh, thêm entry kết thúc `/` là cách thông dụng.

### Câu 5. Dùng `zip.close()` trong try-with-resources có cần `zip.finish()` trước không?

**Không bắt buộc.** `close()` hoàn tất ZIP rồi đóng luồng bên dưới. `finish()` được dùng khi muốn hoàn tất archive nhưng giữ sink mở, hoặc cần đánh dấu điểm kết thúc archive rõ ràng.

### Câu 6. Đã gọi `putNextEntry("x.txt")` rồi ghi nhiều khối byte

Có nên gọi `closeEntry()` sau mỗi khối không?

**Không.** Toàn bộ các khối của `x.txt` thuộc cùng entry đang mở. Gọi `closeEntry()` **một lần sau khi đã ghi đủ**; nếu đóng sớm sẽ kết thúc dữ liệu entry.

### Câu 7. ZipInputStream đọc được `one.txt` từ luồng byte chưa hoàn tất ZIP

Có thể kết luận ZIP hợp lệ hoàn toàn?

**Không.** Đọc được một local entry không chứng minh central directory và end-of-central-directory hợp lệ. Phải `finish` hoặc `close` và kiểm tra tính toàn vẹn của toàn archive theo yêu cầu ứng dụng.

## 19. Checklist đóng gói an toàn

Trước khi bắt đầu:

- Xác định **ai sở hữu `OutputStream`** và ai chịu trách nhiệm gọi `close`.
- Xác định tên entry **tương đối**, không trùng và phù hợp nền tảng giải nén.
- Chọn `DEFLATED` mặc định hoặc `STORED` với metadata đã được tính đúng.
- Xác định charset cho entry name/comment và cách mã hóa payload văn bản.

Khi ghi mỗi entry:

- Gọi `putNextEntry(entry)`.
- Ghi **đầy đủ** nội dung entry trước khi đóng.
- Gọi `closeEntry()`, xử lý `IOException` và `ZipException`.
- Không kết luận có archive hợp lệ nếu quá trình bị lỗi giữa chừng.

Khi hoàn tất:

- Dùng `close()` / `try-with-resources` nếu ZIP stream sở hữu sink.
- Dùng `finish()` nếu phải hoàn tất archive **mà vẫn giữ sink của caller mở**.
- Không publish tệp ZIP dở dang; với file quan trọng, ghi tạm rồi xác minh và publish.
- Khi cần kiểm tra đầy đủ danh sách entry và cấu trúc tổng hợp, mở bằng `ZipFile` sau khi ZIP đã hoàn tất.
- Khi giải nén dữ liệu không tin cậy, có chính sách kiểm tra đường dẫn, độ lớn, số entry và tài nguyên.

## 20. Tổng kết

**Ba thao tác phải nhớ theo đúng phạm vi:**

```text
putNextEntry(entry) -> bắt đầu một entry
write(bytes)        -> ghi nội dung entry ấy
closeEntry()        -> kết thúc entry ấy

lặp lại cho các entry khác

finish()            -> kết thúc TOÀN BỘ ZIP,
                       nhưng giữ OutputStream bên dưới mở

hoặc

close()             -> kết thúc TOÀN BỘ ZIP
                       và đóng cả OutputStream bên dưới
```

`putNextEntry` và `closeEntry` tạo ra ranh giới cho từng file/thư mục bên trong ZIP. `finish` tạo ranh giới kết thúc **archive**, còn `close` đồng thời quản lý vòng đời tài nguyên bên dưới. Không trộn ba lớp trách nhiệm này. Với cách hiểu rõ entry-level và archive-level, bạn có thể viết code đóng gói nhiều file, dọn tài nguyên đúng và tránh tạo ZIP hỏng hoặc để lại dữ liệu dở dang.

**Tài liệu tham khảo chính thức cho Java SE 17:**

- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html) — `putNextEntry`, `closeEntry`, `finish`, `close`.
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html) — tên, method, kích thước, CRC-32.
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html) — đọc ZIP hoàn chỉnh với chỉ mục entry.
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html) — đọc entry tuần tự.
- [JarOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html) — JAR dựa trên ZIP.
