# Giới hạn dung lượng, số entry và tỷ lệ giải nén — bảo vệ Java ZIP extraction

## 1. Vì sao phải đặt giới hạn khi giải nén?

Trong Java Core I/O, các API như `ZipFile`, `ZipInputStream` và `ZipEntry` cho phép đọc tệp ZIP tương đối dễ dàng. Nhưng một tệp ZIP đến từ nguồn không tin cậy có thể rất nhỏ khi lưu trữ và tạo ra lượng dữ liệu cực lớn, rất nhiều tệp con hoặc cấu trúc thư mục phức tạp khi giải nén.

Một số rủi ro thường gặp:

- **ZIP bomb / decompression bomb:** dữ liệu nén chỉ vài kilobyte hoặc megabyte nhưng có thể nở thành hàng gigabyte, gây cạn dung lượng đĩa, CPU, RAM hoặc thời gian xử lý.
- **Quá nhiều entry:** hàng trăm nghìn tệp nhỏ có thể gây cạn inode, handle, metadata và thời gian tạo tệp, dù tổng byte giải nén không lớn.
- **Một entry quá lớn:** một tệp đơn lẻ vượt ngưỡng nghiệp vụ, khiến hệ thống lưu trữ hoặc xử lý phía sau bị quá tải.
- **Tỷ lệ giải nén quá cao:** một entry rất nhỏ sau nén nhưng có lượng byte không nén lớn bất thường.
- **Zip Slip / path traversal:** entry có tên như `../../outside.txt` cố ghi ra ngoài thư mục được phép.
- **File overwrite, tên trùng, symlink và file system quirks:** gây ghi đè tài liệu đang có hoặc làm đường dẫn cuối cùng trỏ đến vị trí không mong muốn.

**Không có một ngưỡng duy nhất giải quyết mọi rủi ro.** Hệ thống nên đặt giới hạn độc lập về kích thước ZIP đầu vào, số entry, kích thước từng entry sau giải nén, tổng kích thước đã giải nén và tỷ lệ nén; sau đó bổ sung giới hạn tài nguyên và kiểm tra đường dẫn.

Mục tiêu bài này: thiết kế chính sách bảo vệ, hiểu công thức tỷ lệ giải nén, xử lý metadata chưa biết/không đáng tin, áp dụng giới hạn **trong lúc stream byte**, và viết ví dụ Java 17+ chạy độc lập.

## 2. Ba giới hạn chính và cách tính

### 2.1. Dung lượng (size)

Có ít nhất ba con số khác nhau:

1. **Dung lượng ZIP đầu vào:** kích thước tệp archive trên đĩa, ví dụ `Files.size(zipPath)`. Chặn archive đầu vào khổng lồ trước khi đọc sâu.
2. **Dung lượng giải nén của một entry:** số byte thực tế `InputStream.read(...)` tạo ra cho riêng entry đó. Chặn một file quá lớn.
3. **Tổng dung lượng giải nén của archive:** cộng các byte thực tế của mọi entry đã đọc. Chặn trường hợp nhiều file nhỏ, mỗi file trong giới hạn nhưng tổng cộng lại quá lớn.

Ví dụ chính sách **minh họa** cho một dịch vụ nhận tệp ZIP cấu hình:

| Thuộc tính | Giới hạn ví dụ | Mục đích |
| --- | ---: | --- |
| Kích thước archive đầu vào | 4 MiB | Giới hạn tải lên và xử lý tệp ZIP |
| Số entry (gồm cả thư mục) | 100 | Hạn chế số tệp/thư mục và chi phí metadata |
| Dung lượng giải nén một entry | 1 MiB | Không cho một file đơn lẻ quá lớn |
| Tổng byte giải nén | 2 MiB | Không cho tổng dữ liệu bùng nổ |
| Tỷ lệ giải nén tối đa một file | 100:1 | Chặn dữ liệu nở bất thường |

Các con số này **không phải tiêu chuẩn an toàn chung của Java**. Trong thực tế, cần thiết lập theo nghiệp vụ, hạ tầng, quota, SLA, loại file hợp lệ và kết quả benchmark. Nếu dịch vụ nhận bản backup nhiều gigabyte, các ngưỡng ví dụ rõ ràng không phù hợp.

**MiB = 1.048.576 byte** (2^20); không nhầm với MB thập phân = 1.000.000 byte.

### 2.2. Giới hạn số entry

Một entry trong ZIP có thể đại diện cho file hoặc thư mục. Ví dụ:

~~~text
project/
project/docs/
project/docs/readme.md
project/config.json
~~~

Archive trên có **4 entry** nếu cả hai thư mục được ghi thành các entry tường minh. Một archive khác có thể chỉ ghi hai file mà không có các entry thư mục riêng; số entry phụ thuộc cách đóng gói.

Nên đếm toàn bộ các entry mình duyệt, **kể cả entry thư mục**, thay vì chỉ đếm những file có payload. Nếu tên trùng xuất hiện, cần xác định chính sách từ chối, không để entry sau âm thầm ghi đè entry trước. Nếu cần giới hạn số **file thực sự** riêng với số entry, có thể theo dõi thêm một bộ đếm; không thay thế bộ đếm tổng entry.

Giới hạn số entry giúp giảm nguy cơ archive chứa hàng chục nghìn file kích thước 0. Giới hạn tổng byte **không** đủ để chặn trường hợp đó.

### 2.3. Tỷ lệ giải nén (decompression ratio)

Với một entry:

\[
\text{ratio} = \frac{\text{số byte sau giải nén}}{\text{số byte dữ liệu đã nén}}
\]

Ví dụ:

- Entry có 500.000 byte sau giải nén, 100.000 byte dữ liệu nén: tỷ lệ **5:1**.
- Entry có 500.000 byte sau giải nén, 1.000 byte dữ liệu nén: tỷ lệ **500:1**.
- Nếu chính sách cho tối đa 100:1, trường hợp thứ hai bị từ chối.

Để tránh phép chia không cần thiết, có thể kiểm tra:

~~~java
// Chỉ hợp lệ khi compressedBytes > 0 và phép nhân không tràn long.
boolean tooHigh = uncompressedBytes > compressedBytes * maxRatio;
~~~

Nếu số byte nén bằng **0** nhưng số byte sau giải nén lại **dương**, ratio không xác định/vô hạn: phải xem là bất thường và từ chối. Nếu cả hai bằng 0, đây có thể là entry rỗng hợp lệ.

**Cảnh báo:** tỷ lệ nén tự nó không nói toàn bộ mức độ nguy hiểm. Một file rất lớn nhưng có tỷ lệ 2:1 vẫn có thể lấp đĩa; ngược lại một file nhỏ hợp lệ có tỷ lệ 200:1 có thể bị chính sách chặn. Do đó phải kết hợp ratio với **giới hạn byte tuyệt đối**, thời gian và tài nguyên.

## 3. Chỉ kiểm tra ZipEntry.getSize() có đủ không?

**Không.** `ZipEntry.getSize()` cho biết kích thước chưa nén được khai báo trong metadata, và `ZipEntry.getCompressedSize()` cho biết kích thước đã nén theo metadata ZIP. Trong một số đường đọc, chúng có thể là `-1`, tức chưa biết.

~~~java
ZipEntry entry = /* một entry đã đọc */;
long declaredSize = entry.getSize();
long declaredCompressedSize = entry.getCompressedSize();
~~~

Đây chỉ là **đoạn minh họa API**, không phải chương trình độc lập. Hai giá trị trên có ích để **từ chối sớm** những entry có thông tin rõ ràng vượt ngưỡng. Nhưng metadata do dữ liệu đầu vào cung cấp, nên không được coi là bằng chứng an toàn cuối cùng khi xử lý archive không tin cậy.

Hãy phân biệt hai lớp bảo vệ:

- **Preflight metadata:** kiểm tra số entry, tên, kích thước khai báo, kích thước nén khai báo, tỷ lệ khai báo. Nếu vi phạm có thể từ chối trước khi tạo file.
- **Streaming enforcement:** khi gọi `read(...)`, cộng **số byte thực tế** và từ chối ngay nếu một entry hoặc tổng archive vượt quota. Đây là lớp bắt buộc để tránh tin tuyệt đối vào khai báo.

Với `ZipFile`, thông tin lấy từ central directory thường có kích thước cụ thể; tuy nhiên mã vẫn phải quyết định cách xử lý trường hợp không có/không hợp lệ. Ví dụ trong bài **từ chối metadata kích thước không xác định** để thực thi ratio một cách bảo thủ. Ứng dụng khác có thể hỗ trợ chế độ stream `ZipInputStream` mà chưa biết kích thước từ đầu, nhưng lúc đó càng phải áp giới hạn byte thực tế; việc tính tỷ lệ nén chính xác cần đo đúng lượng byte nén đã tiêu thụ cho từng entry, không suy đoán từ số byte trả về của luồng giải nén.

**Đừng tự lấy `Files.size(zipPath)` làm mẫu số tỷ lệ cho mỗi entry.** Kích thước archive còn chứa header, tên file, central directory và dữ liệu của các entry khác. Tỷ lệ từng entry dùng kích thước dữ liệu nén của **chính entry** đó.

## 4. Các loại ZIP bomb cần hiểu

### 4.1. Entry lớn bất thường

Một entry ghi nhiều byte giống nhau, chẳng hạn hàng triệu ký tự `A`, có thể nén rất tốt. Trên đĩa, nó nhỏ; sau giải nén, nó gây áp lực lên ổ lưu trữ hoặc bước parse.

**Bảo vệ:** giới hạn kích thước từng entry và tỷ lệ nén, kiểm tra trong mỗi vòng `read`.

### 4.2. Rất nhiều file nhỏ

Archive có 100.000 entry, mỗi entry chỉ vài byte. Tổng byte có thể nhỏ nhưng thao tác mở/tạo/đóng file, metadata, inode, quyền và quét virus tiêu tốn đáng kể.

**Bảo vệ:** giới hạn số entry, độ dài tên, độ sâu thư mục, số tệp được tạo; kết hợp quota và timeout. Giới hạn 100 entry ở ví dụ sau là một lựa chọn minh họa.

### 4.3. ZIP lồng ZIP

Archive ngoài chứa nhiều archive bên trong; ứng dụng sau đó tự động giải nén từng archive con. Nếu chỉ đặt quota **mỗi tầng**, tổng chi phí có thể tăng rất nhanh.

**Bảo vệ:** tốt nhất **không tự động giải nén đệ quy** trừ khi nghiệp vụ yêu cầu. Nếu có, áp ngân sách **toàn cục** cho cả cây (độ sâu, tổng entry, tổng byte, tổng thời gian, tỷ lệ) và từ chối khi vượt giới hạn. Đừng reset quota về mặc định không giới hạn ở mỗi archive con.

### 4.4. Entry có metadata/tên cố tình gây lỗi

Tên lạ, tên quá dài, đường dẫn trùng, đường dẫn cha `..`, đường dẫn tuyệt đối, dấu phân cách của hệ điều hành khác, symlink hoặc file hỏng có thể gây lỗi hoặc tạo tác dụng phụ ngoài phạm vi.

**Bảo vệ:** kiểm tra path, chính sách tên và kiểu entry; giải nén vào thư mục mới, độc lập, không có file sẵn. `ZipFile` chỉ cung cấp phần thông tin ZIP mà API công khai có thể đọc; không mặc định nó là trình xác thực hoàn chỉnh mọi loại metadata, permission hay symbolic link của ZIP.

## 5. Mô hình giải nén nhiều lớp bảo vệ

Một pipeline an toàn hơn:

~~~text
Đầu vào archive
      |
      v
Giới hạn upload + kích thước ZIP + quyền sở hữu
      |
      v
Mở ZIP, duyệt metadata: count, path, size, ratio
      |
      +-- Vi phạm --> REJECT (không công bố output)
      |
      v
Tạo thư mục đích mới trong vùng staging
      |
      v
Lần lượt stream từng entry theo buffer cố định
      |
      +-- Quota byte/ratio/time bị vượt --> ABORT & CLEANUP
      |
      v
Kiểm tra schema, CRC khi thư viện đọc, nội dung, chính sách
      |
      v
Công bố kết quả đã kiểm tra, ghi trạng thái/audit
~~~

**Điểm thiết kế:** việc giải nén **không nên ghi trực tiếp vào thư mục ứng dụng đang hoạt động**. Nếu phát hiện bomb ở giữa chừng, các file đã ghi một phần phải được coi là staging chưa tin cậy. Chỉ công bố sau khi toàn bộ archive vượt qua các kiểm tra liên quan.

### Ngân sách (budget) dùng chung

Giới hạn tổng byte phải **tích lũy qua mọi entry**, không reset về 0 ở mỗi file. Dạng kiểm tra tránh tràn số:

~~~java
if (n > maxEntryBytes - entryBytes
        || n > maxTotalBytes - totalBytes) {
    throw new IOException("Exceeded decompression quota");
}

entryBytes += n;
totalBytes += n;
~~~

Đây là đoạn minh họa với `n` là số byte mới đọc **dương**, các bộ đếm ban đầu không âm và luôn nằm trong giới hạn. So sánh theo dạng `limit - used` giúp tránh phép cộng `used + n` tràn `long`.

Việc đọc bằng bộ đệm `byte[8192]` chỉ giữ khoảng 8 KiB dữ liệu của lượt đọc **không** tự giới hạn file đầu ra. Phải cộng và chặn theo tổng byte thật.

## 6. Ví dụ Java 17+ hoàn chỉnh: ZipFile với giới hạn chặt

Ví dụ tạo một ZIP hợp lệ gồm hai file, giải nén vào thư mục mới rồi kiểm tra nội dung. Sau đó tạo một ZIP có tên entry `../outside.txt` để cho thấy bộ kiểm tra path từ chối trước khi ghi ra ngoài.

Ví dụ dùng policy nhỏ để dễ học:

- Tệp ZIP gốc tối đa 4 MiB.
- Tối đa 100 entry.
- Mỗi file sau giải nén tối đa 1 MiB.
- Tổng dữ liệu sau giải nén tối đa 2 MiB.
- Mỗi file tối đa 100:1; từ chối metadata size không xác định.
- Không nhận entry có `..`, đường dẫn tuyệt đối, dấu `\`, ổ đĩa dạng Windows, tên trống hoặc đường dẫn logic trùng.
- Tạo **thư mục output chưa tồn tại**, dùng `CREATE_NEW` để tránh ghi đè.

Lưu thành **`SafeZipExtractionDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class SafeZipExtractionDemo {
    private static final long MAX_ZIP = 4L * 1024 * 1024;
    private static final long MAX_ENTRY = 1L * 1024 * 1024;
    private static final long MAX_TOTAL = 2L * 1024 * 1024;
    private static final long MAX_RATIO = 100;
    private static final int MAX_COUNT = 100;

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory("zip-limits-");
        try {
            Path goodZip = work.resolve("good.zip");
            try (ZipOutputStream out =
                         new ZipOutputStream(Files.newOutputStream(goodZip))) {
                addEntry(out, "docs/readme.txt", "hello");
                addEntry(out, "metadata.txt", "v1");
            }

            Path goodOutput = work.resolve("unpacked");
            int files = extract(goodZip, goodOutput);
            System.out.println("Files extracted: " + files);
            System.out.println("Readme: " + Files.readString(
                    goodOutput.resolve("docs/readme.txt"),
                    StandardCharsets.UTF_8));

            Path badZip = work.resolve("bad.zip");
            try (ZipOutputStream out =
                         new ZipOutputStream(Files.newOutputStream(badZip))) {
                addEntry(out, "../outside.txt", "forbidden");
            }

            boolean rejected = false;
            try {
                extract(badZip, work.resolve("blocked"));
            } catch (IOException expected) {
                rejected = true;
            }
            System.out.println("Traversal rejected: " + rejected);
        } finally {
            cleanup(work);
        }
    }

    private static void addEntry(
            ZipOutputStream out, String name, String text)
            throws IOException {
        out.putNextEntry(new ZipEntry(name));
        out.write(text.getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
    }

    private static int extract(Path zipPath, Path outputRoot)
            throws IOException {
        if (Files.size(zipPath) > MAX_ZIP) {
            throw new IOException("ZIP input too large");
        }

        try (ZipFile zip = new ZipFile(zipPath.toFile())) {
            List<ZipEntry> entries = new ArrayList<>();
            Set<Path> usedNames = new HashSet<>();
            Enumeration<? extends ZipEntry> it = zip.entries();

            // First pass: do not write before validating all entries.
            while (it.hasMoreElements()) {
                ZipEntry entry = it.nextElement();
                if (entries.size() >= MAX_COUNT) {
                    throw new IOException("Too many ZIP entries");
                }

                Path relative = validateName(entry.getName());
                if (!usedNames.add(relative)) {
                    throw new IOException("Duplicate path: " + relative);
                }

                long size = entry.getSize();
                long compressed = entry.getCompressedSize();
                if (size < 0 || compressed < 0) {
                    throw new IOException("Unknown ZIP entry size");
                }
                if (size > MAX_ENTRY || compressed > MAX_ZIP) {
                    throw new IOException("Entry size exceeded");
                }
                if (exceedsRatio(size, compressed)) {
                    throw new IOException("Ratio exceeded");
                }
                if (entry.isDirectory() && size != 0) {
                    throw new IOException("Directory entry with data");
                }
                entries.add(entry);
            }

            // A fresh, unshared output directory limits overwrite risk.
            Files.createDirectory(outputRoot);
            long total = 0;
            int fileCount = 0;
            byte[] chunk = new byte[8192];

            for (ZipEntry entry : entries) {
                Path relative = validateName(entry.getName());
                Path output = outputRoot.resolve(relative).normalize();
                if (!output.startsWith(outputRoot)) {
                    throw new IOException("Path escaped target directory");
                }

                if (entry.isDirectory()) {
                    Files.createDirectories(output);
                    continue;
                }

                Files.createDirectories(output.getParent());
                long entryBytes = 0;
                long compressed = entry.getCompressedSize();

                try (InputStream in = zip.getInputStream(entry);
                     OutputStream out = Files.newOutputStream(
                             output,
                             StandardOpenOption.CREATE_NEW,
                             StandardOpenOption.WRITE)) {

                    int n;
                    while ((n = in.read(chunk)) != -1) {
                        if (n == 0) {
                            throw new IOException("Input made no progress");
                        }
                        if (n > MAX_ENTRY - entryBytes
                                || n > MAX_TOTAL - total) {
                            throw new IOException("Byte quota exceeded");
                        }

                        entryBytes += n;
                        total += n;
                        if (exceedsRatio(entryBytes, compressed)) {
                            throw new IOException("Ratio exceeded");
                        }
                        out.write(chunk, 0, n);
                    }
                }

                // Count only files written successfully.
                fileCount++;
            }
            return fileCount;
        }
    }

    private static boolean exceedsRatio(
            long uncompressed, long compressed) {
        if (uncompressed == 0) {
            return false;
        }
        if (compressed == 0) {
            return true;
        }
        // MAX_ZIP constrains compressed values before calling here.
        return compressed <= Long.MAX_VALUE / MAX_RATIO
                && uncompressed > compressed * MAX_RATIO;
    }

    private static Path validateName(String name) throws IOException {
        if (name.isBlank()
                || name.indexOf('\\') >= 0
                || name.indexOf('\0') >= 0
                || name.startsWith("/")
                || name.matches("^[A-Za-z]:.*")) {
            throw new IOException("Unsafe name: " + name);
        }

        Path relative;
        try {
            relative = Path.of(name);
        } catch (RuntimeException invalidName) {
            throw new IOException("Invalid ZIP path", invalidName);
        }
        if (relative.isAbsolute()) {
            throw new IOException("Absolute ZIP path");
        }
        for (Path part : relative) {
            if (part.toString().equals("..")) {
                throw new IOException("Parent traversal forbidden");
            }
        }
        relative = relative.normalize();
        if (relative.toString().isEmpty()
                || relative.toString().equals(".")) {
            throw new IOException("Empty path");
        }
        return relative;
    }

    private static void cleanup(Path root) throws IOException {
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(
                    Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 SafeZipExtractionDemo.java
java SafeZipExtractionDemo
~~~

**Stdout kỳ vọng trên file system thông thường:**

~~~text
Files extracted: 2
Readme: hello
Traversal rejected: true
~~~

### Giải thích mã

1. `Files.size(zipPath)` chặn kích thước archive đầu vào trước khi đọc nội dung sâu. Đây **không phải** giới hạn dung lượng đã giải nén; nó là một quota riêng.
2. Vòng `zip.entries()` duyệt entry một lần để xác thực toàn bộ tên, số entry và metadata trước khi ghi. `entries.size() >= MAX_COUNT` chặn entry thứ 101.
3. `usedNames` từ chối tên đã chuẩn hóa bị lặp, không để entry mới cố ý ghi đè entry cũ. Trường hợp tên có cùng ý nghĩa trên file system case-insensitive còn phụ thuộc nền tảng; `CREATE_NEW` là một lớp bảo vệ bổ sung.
4. `validateName` từ chối tên rỗng, NUL, backslash, đường dẫn dạng ổ đĩa, tuyệt đối và bất kỳ thành phần `..`. Nó chặn những hình thức traversal cơ bản và yêu cầu đường dẫn dùng dấu `/` cho ZIP minh họa.
5. `Files.createDirectory(outputRoot)` yêu cầu output chưa tồn tại. Không ghi dữ liệu vào thư mục hệ thống đang sử dụng hoặc đường dẫn có sẵn với các file quan trọng.
6. Với mỗi file, chương trình đọc từng chunk tối đa 8192 byte rồi **kiểm tra quota trước khi ghi chunk đó**. Hai bộ đếm `entryBytes` và `total` phản ánh byte thực tế; không chỉ tin `entry.getSize()`.
7. Hàm `exceedsRatio` xử lý trường hợp mẫu số bằng 0 và tránh tràn `long`. Trong ví dụ, metadata `compressed` đã bị giới hạn ≤ 4 MiB.
8. `ZipFile.getInputStream(entry)` chỉ mở dữ liệu của entry cụ thể; `try-with-resources` đóng luồng kể cả khi phát hiện vượt quota.
9. Sau khi xử lý đủ, chương trình in số file và nội dung đã giải nén. Một archive độc hại có tên `../outside.txt` bị từ chối ở vòng kiểm tra đầu tiên.
10. `cleanup` xóa cây thư mục tạm trong demo. Mã demo không phải một hệ thống lưu trữ lâu dài; production cần quy trình staging, cleanup lỗi, quản lý race/symlink và công bố kết quả an toàn hơn.

**Giới hạn chủ đích:** Ví dụ dạy nguyên tắc đếm dung lượng, entry, ratio và ngăn Zip Slip cơ bản. Nó **không phải ZIP sandbox đầy đủ**. Không có watchdog timeout, sandbox OS, xác thực format nghiệp vụ, xử lý POSIX symlink mode trong ZIP, hạn chế độ sâu/tên, quota đồng thời giữa nhiều request, hay cơ chế xuất bản nguyên tử. Không sử dụng nguyên xi nó để xử lý archive thù địch trên môi trường nhiều người dùng mà không bổ sung các lớp bảo vệ tương ứng.

## 7. Tại sao phải kiểm tra ratio cả trước và sau giải nén?

### Kiểm tra trước (declared ratio)

Nếu ZIP khai báo `uncompressedSize = 10_000_000` và `compressedSize = 1_000`, tỷ lệ 10.000:1 vượt ngưỡng 100:1; có thể từ chối ngay, không cần tạo file hay giải nén payload.

Việc từ chối sớm tiết kiệm tài nguyên nhưng **chưa đủ**: metadata không nhất thiết đáng tin; parser còn có thể đối mặt với dữ liệu hỏng hoặc cấu trúc archive phức tạp.

### Kiểm tra trong vòng đọc (actual output)

Nếu metadata khai báo một entry nhỏ nhưng luồng thực tế tạo ra nhiều byte hơn, bộ đếm thật sẽ vượt `MAX_ENTRY` hoặc `MAX_TOTAL`. Kiểm tra mỗi chunk giới hạn lượng dữ liệu ứng dụng ghi xuống disk.

Đối với ratio, ví dụ sử dụng số byte **thực sự đã giải nén** và số byte nén **khai báo** trong central directory. Đây là **lớp ngăn sớm**, không phải bộ đo chính xác số byte nén vật lý đã đọc tại mỗi khoảnh khắc. Nếu metadata compressed size không đáng tin, giới hạn output tuyệt đối vẫn là biện pháp chắc chắn hơn.

Để đo tỷ lệ nén chính xác trong một pipeline streaming không có metadata tin cậy, phải instrument nguồn byte nén thật theo từng entry, bao gồm lưu ý buffering, data descriptor và ranh giới ZIP; không lấy tổng byte đọc từ một luồng wrapper bất kỳ rồi gọi đó là compressedSize per entry.

### Ratio của toàn archive

Có thể tính:

\[
\text{archive ratio} =
\frac{\text{tổng byte chưa nén}}{\text{kích thước ZIP trên đĩa}}
\]

như một chỉ số bổ sung, nhưng tỷ lệ này khác tỷ lệ **mỗi entry** vì ZIP có header, metadata và thư mục trung tâm. Nó có thể bỏ qua một entry cực đoan khi các entry khác làm mẫu số lớn. Do đó, nếu cần, dùng cả giới hạn tỷ lệ từng entry và tổng archive, không thay thế các giới hạn byte tuyệt đối.

## 8. ZipFile hay ZipInputStream?

| Yếu tố | `ZipFile` | `ZipInputStream` |
| --- | --- | --- |
| Cách truy cập | Mở archive, duyệt entry trong central directory, lấy luồng cho từng entry | Đọc tuần tự các entry từ một `InputStream` |
| Metadata kích thước | Thường có từ central directory trước khi mở payload | Có thể `-1` trước khi đọc xong entry nếu dùng data descriptor |
| Thuận tiện cho preflight toàn bộ entry | **Có**, nhưng metadata vẫn cần kiểm tra và runtime quota | Khó hơn khi phải biết tất cả entry trước khi giải nén |
| Đầu vào không seek được | Không phải lựa chọn trực tiếp | Phù hợp với luồng input, nhưng vẫn cần quota đầu vào |
| Chặn ZIP bomb | Cần giới hạn streaming byte thực tế | Cũng phải giới hạn streaming byte thực tế |
| Quy tắc ghi tệp | Ứng dụng quyết định, phải chống traversal/overwrite | Ứng dụng quyết định, không tự an toàn hơn |

**Không nhầm `getNextEntry()` với việc một entry đã giải nén hoàn tất.** Với `ZipInputStream`, phải đọc tới hết entry hoặc đóng entry trước khi chuyển sang entry tiếp theo theo hợp đồng API. Vì metadata có thể chưa biết, giới hạn byte thực tế càng quan trọng.

Nếu ZIP được upload qua mạng, giới hạn dung lượng upload cũng phải được thực thi **trong khi nhận dữ liệu**, không đợi toàn bộ upload xong rồi mới kiểm tra. Với `ZipFile`, thường nhận upload vào file staging đã giới hạn trước, sau đó mới mở ZIP.

## 9. Phải tính cả tài nguyên ngoài số byte

Các giới hạn size/count/ratio là lõi bài học, nhưng không giải quyết tất cả kiểu từ chối dịch vụ.

### 9.1. CPU và thời gian

Một archive có thể tốn CPU đáng kể để giải nén/kiểm tra, kể cả khi output cuối cùng dưới quota. Không có timeout tích hợp chung cho mọi lệnh `InputStream.read` trong ZIP. Trong hệ thống production, đặt deadline cho request, theo dõi thời gian, và cân nhắc cô lập bằng tiến trình/container có quota CPU, RAM, đĩa.

Kiểm tra thời gian trong vòng đọc có thể giúp dừng giữa các chunk, nhưng nếu **một lời gọi đọc bị kẹt**, bộ đếm thời gian ngoài luồng hoặc cơ chế giám sát ở mức tiến trình sẽ cần thiết. `Thread.interrupt()` không phải bảo đảm dừng mọi hoạt động decompression ngay lập tức.

### 9.2. Số lượng yêu cầu đồng thời

Giới hạn mỗi ZIP 2 MiB output nhưng nhận đồng thời 10.000 archive có thể dẫn đến tổng lượng dữ liệu và I/O lớn. Cần giới hạn **concurrency**, queue, tổng byte staging, số file đang mở và tốc độ nhận request. Các quota nên có cả phạm vi request và tenant/service.

### 9.3. Độ dài tên và độ sâu thư mục

Tên entry rất dài hoặc cấu trúc thư mục sâu có thể gây lỗi đường dẫn, quá tải metadata hoặc tạo cây khó dọn. Hệ thống thực tế nên định nghĩa giới hạn `MAX_NAME_LENGTH`, `MAX_DEPTH` và các ký tự/tên thiết bị bị cấm theo nền tảng.

Các đường dẫn có ký tự đặc biệt cần được chuẩn hóa theo chính sách xuyên nền tảng. Ví dụ, từ chối dấu `\` trong tên ZIP là chính sách đơn giản để tránh việc một hệ điều hành xem nó là dấu phân cách trong khi hệ điều hành khác xem là ký tự.

### 9.4. File permissions, symlink và race condition

ZIP có thể chứa thông tin quyền Unix hoặc metadata biểu diễn symbolic link. API `ZipEntry` chuẩn không cung cấp mọi thuộc tính POSIX kiểu archive cho một hệ thống extraction có yêu cầu bảo mật cao. Không suy ra rằng mọi entry không kết thúc bằng `/` chắc chắn là file thường an toàn.

Ngoài ra, kiểm tra `output.startsWith(outputRoot)` là kiểm tra đường dẫn **về mặt ký tự**, không tự bảo vệ trước khi một tiến trình khác tạo symlink ở thư mục cha ngay sau kiểm tra. Vì vậy:

- Dùng output staging mới, riêng biệt, chỉ có tiến trình/trust domain được phép sửa.
- Không theo các symlink do phía không tin cậy có thể đặt vào staging.
- Tránh giải nén trực tiếp vào đường dẫn đang có file hoặc đang được nhiều actor ghi đồng thời.
- Đối với threat model nghiêm ngặt, sử dụng cơ chế thao tác path dựa trên handle, sandbox và kiểm tra attribute thích hợp.

`CREATE_NEW` chặn ghi đè file đã tồn tại tại tên đích cuối cùng, nhưng **không phải bảo đảm đầy đủ** chống các cuộc đua symlink ở thư mục cha.

## 10. Kiểm tra archive hỏng và CRC

ZIP có CRC-32, và các API giải nén có thể phát hiện một số loại dữ liệu hỏng qua cấu trúc hoặc CRC. Tuy nhiên:

- **CRC-32 không phải chữ ký mật mã hoặc cơ chế xác thực người gửi.**
- Việc giải nén thành công không có nghĩa dữ liệu hợp lệ theo schema nghiệp vụ.
- Không vì CRC đúng mà bỏ qua quota byte/count/ratio.
- Dữ liệu có thể hỏng, có encoding sai, hoặc được cố ý dựng để khai thác bước xử lý tiếp theo.

Nếu cần bảo đảm nội dung đáng tin từ một nhà phát hành, dùng hash/chữ ký số và chuỗi xác minh nguồn phù hợp, không chỉ dựa CRC ZIP.

## 11. Công bố dữ liệu sau khi giải nén và khôi phục lỗi

Một request nên có các trạng thái rõ ràng:

~~~text
RECEIVED
   |
   v
VALIDATING_METADATA
   |
   v
EXTRACTING_IN_STAGING
   |
   +---- error/quota/path failure ---> REJECT + CLEANUP
   |
   v
VALIDATING_CONTENT
   |
   +---- schema/hash failure -------> REJECT + CLEANUP
   |
   v
PUBLISHING
   |
   v
READY
~~~

**Quan trọng:** nếu quota vượt giữa lúc ghi entry thứ ba, hai entry trước có thể đã tồn tại trong staging. Không được coi staging là bản giải nén thành công; phải đánh dấu reject và dọn dẹp. Ví dụ phía trên được thiết kế để xóa toàn bộ cây tạm khi chương trình kết thúc, kể cả đường lỗi.

Trong ứng dụng thật, upload có thể đến từ người dùng không tin cậy. Nên phân biệt rõ namespace staging và namespace đã công bố. Việc di chuyển/đổi tên toàn bộ thư mục có nguyên tử hay không phụ thuộc file system; nếu cần atomic publication, phải kiểm tra tính hỗ trợ và thiết kế giao thức phù hợp, không mặc định mọi `Files.move` là atomic.

Nếu có retry, phải tránh công bố dữ liệu từng phần hoặc ghi đè kết quả của request khác. Có thể dùng request ID/phiên bản riêng, checkpoint/audit và cleanup chạy lại an toàn.

## 12. Sai lầm phổ biến và cách sửa

| Sai lầm | Tại sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Chỉ giới hạn dung lượng tệp `.zip` | ZIP nhỏ có thể giải nén rất lớn | Giới hạn tổng byte sau giải nén và từng entry |
| Chỉ giới hạn tổng dung lượng đã giải nén | Nhiều file rỗng vẫn làm cạn inode/metadata | Giới hạn số entry và tài nguyên tạo file |
| Chỉ giới hạn một entry | Nhiều entry nhỏ cộng dồn vượt quota | Dùng bộ đếm tổng qua mọi entry |
| Tin `ZipEntry.getSize()` là chính xác tuyệt đối | Metadata có thể thiếu/không đáng tin | Kiểm tra metadata **và** byte thực tế |
| Kiểm tra size sau khi ghi hết | Disk đã có thể đầy trước khi kiểm tra | Kiểm tra trong từng vòng đọc trước khi ghi |
| Chỉ kiểm tra compression ratio | Ratio thấp vẫn có thể nở thành dữ liệu rất lớn | Kết hợp ratio với giới hạn tuyệt đối |
| Chia cho compressedSize=0 | Lỗi chia 0 hoặc tính ratio sai | Phân biệt payload rỗng và payload dương |
| Dùng `int` đếm tổng byte | Tràn số khi dữ liệu lớn | Dùng `long` và phép so sánh tránh overflow |
| Không kiểm tra đường dẫn ZIP | `../...` có thể ghi ra ngoài đích | Chuẩn hóa, từ chối traversal và sandbox output |
| Giải nén vào thư mục đang sử dụng | Đè file hoặc công bố dữ liệu chưa được xác thực | Dùng staging mới, `CREATE_NEW`, kiểm tra và publish |
| Chấp nhận đường dẫn trùng không chủ đích | Ghi đè, hành vi khó dự đoán | Kiểm tra duplicate và chính sách file system |
| Tự động giải nén ZIP bên trong ZIP vô hạn | Quota từng tầng không ngăn bùng nổ toàn cây | Giới hạn độ sâu và ngân sách toàn cục |
| Không giới hạn thời gian/concurrency | CPU, I/O hoặc request backlog bị quá tải | Timeout, queue bounded và sandbox khi cần |
| Tin CRC là chữ ký bảo mật | Dữ liệu độc hại vẫn có CRC hợp lệ | Xác minh nguồn/schema/chữ ký theo threat model |
| Trả thành công dù extraction ném exception | Thư mục đích có thể chỉ chứa dữ liệu một phần | Không publish trước khi verify và cleanup đường lỗi |

## 13. Các tình huống tính quota

### Tình huống A: ZIP nhỏ, nội dung khổng lồ

Archive 200 KiB, có một file 50 MiB sau giải nén. Nếu MAX_ENTRY = 1 MiB, phải dừng ngay khi bộ đếm uncompressed byte vượt 1 MiB, kể cả metadata đầu vào khai báo khác.

Tỷ lệ xấp xỉ 250:1 cũng vượt mức 100:1; nhưng chỉ cần **một** trong các quota bị vượt là đủ để từ chối.

### Tình huống B: 200 file rỗng

Tổng dung lượng đã giải nén là 0 byte, nhưng 200 entry vượt MAX_COUNT = 100. Phải từ chối dù ratio và size hoàn toàn nhỏ.

### Tình huống C: 10 file, mỗi file 400 KiB

Không file nào vượt MAX_ENTRY = 1 MiB, nhưng tổng 4.000 KiB lớn hơn MAX_TOTAL = 2 MiB. Chính sách phải chặn khi tổng thực tế vượt ngưỡng.

### Tình huống D: File 500 KiB sau giải nén và 1 KiB nén

Ratio = 500:1. Nếu MAX_RATIO = 100:1, phải từ chối dù byte output có thể vẫn dưới MAX_ENTRY.

### Tình huống E: ZIP lồng nhau

ZIP ngoài giải nén thành ZIP con 1 MiB, sau đó ZIP con tạo 50 MiB. Nếu ứng dụng tự giải nén ZIP con, phải tính quota của **cả chuỗi**; nếu không hỗ trợ nested archives thì nên giữ ZIP con như một file dữ liệu và không mở thêm.

## 14. Checklist triển khai production

Trước khi nhận ZIP từ bên ngoài, xác nhận:

1. **Chính sách số lượng:** giới hạn archive size, entry count, total unpacked bytes, per-entry bytes và tỷ lệ nén; có quota toàn hệ thống/tenant.
2. **Thực thi streaming:** kiểm tra số byte thực tế theo chunk; không dùng `readAllBytes()` hay `ByteArrayOutputStream` không giới hạn cho payload lạ.
3. **Path safety:** chống Zip Slip, absolute path, tên trùng, separator khác hệ điều hành, symlink, giới hạn độ sâu và tên.
4. **Staging:** tạo thư mục mới, không cho người dùng khác sửa trong quá trình giải nén, cấm ghi đè, không public dữ liệu trước khi verify.
5. **Format/schema:** chỉ chấp nhận loại file cần thiết, encoding/structure hợp lệ; không suy diễn từ extension.
6. **Resource isolation:** deadline, giới hạn CPU/RAM/disk/inode/open file descriptor và số request đồng thời.
7. **Error handling:** xử lý `IOException`, file hỏng, CRC lỗi, không tiến triển; cleanup staging và báo trạng thái reject.
8. **Observability:** log request id và lý do từ chối, đếm quota exceeded, thời gian/byte/entry, theo dõi ổ đĩa.
9. **Test âm tính:** archive nhiều file rỗng, file nén cực tốt, metadata không hợp lệ, entry lồng sâu, traversal, duplicate, ZIP lồng ZIP, upload ngắt giữa chừng.
10. **Tài liệu hợp đồng:** công bố giới hạn hợp lệ cho người gửi và thông báo lỗi rõ ràng; không âm thầm cắt bớt dữ liệu giải nén.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** ZIP 5 MiB, sau giải nén 6 MiB. MAX_ZIP = 4 MiB, MAX_TOTAL = 10 MiB. Có được chấp nhận không?

**Đáp án:** Không. ZIP đầu vào đã vượt MAX_ZIP dù tổng output chưa vượt giới hạn.

**Câu 2.** Có 101 entry, mỗi entry 0 byte; MAX_COUNT = 100. Có phải ZIP bomb đáng lo không?

**Đáp án:** Archive vượt chính sách số entry. Không cần dữ liệu lớn mới gây áp lực metadata/inode. Từ chối theo MAX_COUNT.

**Câu 3.** `getSize() == -1` nghĩa là kích thước entry bằng -1 byte?

**Đáp án:** Không. `-1` nghĩa là kích thước chưa biết. Phải có chính sách xử lý; không coi là an toàn. Nếu hỗ trợ stream, phải đếm byte thực tế và có cơ chế đánh giá ratio phù hợp.

**Câu 4.** Ratio 10:1 nhưng entry giải nén 50 GiB, giới hạn mỗi entry 1 GiB. Có cho qua vì ratio thấp?

**Đáp án:** Không. Giới hạn byte tuyệt đối đã bị vượt.

**Câu 5.** Đang giải nén file thứ 20, tổng byte đạt MAX_TOTAL. Lần `read()` tiếp theo trả 8192 byte. Cần làm gì?

**Đáp án:** Từ chối trước khi ghi chunk mới vì `8192 > MAX_TOTAL - totalBytes`. Không để byte vượt quota xuất hiện trên đĩa.

**Câu 6.** Tệp ZIP có entry `../../etc/config` nhưng tổng byte rất nhỏ. Có an toàn không?

**Đáp án:** Không. Đường dẫn cố vượt thư mục output là rủi ro độc lập với kích thước; từ chối path traversal.

**Câu 7.** Giải nén bằng `ZipInputStream`, size chưa biết trước. Có thể chỉ nhìn metadata rồi quyết định không?

**Đáp án:** Không. Phải giám sát byte output thực tế trong lúc đọc và dùng chính sách thay thế cho ratio nếu chưa đo được compressedSize chính xác.

**Câu 8.** CRC ZIP khớp có chứng minh file đến từ nguồn đáng tin không?

**Đáp án:** Không. CRC là cơ chế phát hiện lỗi dữ liệu thông thường, không xác thực nguồn hoặc chống sửa đổi có chủ đích như chữ ký số.

## 16. Ghi nhớ

- **Dung lượng ZIP đầu vào, byte sau giải nén của từng entry và tổng byte sau giải nén là ba quota riêng.**
- **Số entry** chặn archive có quá nhiều file/thư mục, kể cả khi tổng byte gần bằng 0.
- **Tỷ lệ giải nén** giúp phát hiện dữ liệu nở cực mạnh nhưng **không thay thế giới hạn byte tuyệt đối**.
- **Không tin metadata ZIP một cách tuyệt đối**: kiểm tra cả khai báo trước khi đọc và byte thực tế khi giải nén.
- **Không chỉ phòng bomb:** phải từ chối traversal, kiểm soát symlink/overwrite, staging và tài nguyên đồng thời.
- **Tính đúng đắn cần được chứng minh bằng quota được thực thi trước mỗi lần ghi**, xử lý lỗi và chỉ công bố output khi toàn bộ quy trình thành công.
