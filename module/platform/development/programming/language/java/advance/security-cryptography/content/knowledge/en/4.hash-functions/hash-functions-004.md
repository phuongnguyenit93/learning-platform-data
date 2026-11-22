# 4.4 Băm file lớn bằng luồng hoặc ByteBuffer

## 1. Mục tiêu và bản chất của bài toán

Hàm băm mật mã (cryptographic hash) như **SHA-256** biến một dãy byte dài bất kỳ thành một giá trị dài cố định: SHA-256 tạo ra **32 byte = 256 bit = 64 ký tự hex**. Khi băm file, đầu vào là **toàn bộ các byte của nội dung file, theo đúng thứ tự**, từ byte đầu đến byte cuối. Đường dẫn, tên file, thời gian sửa và kích thước file không tự động được đưa vào digest.

Với file vài GB hoặc lớn hơn bộ nhớ JVM, cách sau dễ gây tốn RAM, tràn giới hạn mảng hoặc `OutOfMemoryError`:

```java
// Minh họa cách KHÔNG nên dùng khi file có thể rất lớn.
byte[] allBytes = Files.readAllBytes(path);
byte[] result = MessageDigest.getInstance("SHA-256").digest(allBytes);
```

Thay vào đó, chỉ giữ một vùng đệm cố định (ví dụ **64 KiB**), lặp cho đến EOF và gọi `MessageDigest.update(...)` cho **chính xác số byte thực sự đọc được**:

```text
File (N byte)
  | read tối đa 64 KiB mỗi lượt
  v
[buffer] -> digest.update(chunk 1) -> digest.update(chunk 2) -> ...
                                                  |
                                                  v
                                           digest.digest()
                                                  |
                                                  v
                                  SHA-256: 32 byte kết quả
```

Trong ký hiệu toán học, nếu nội dung file được chia thành `c1, c2, ..., ck` thì kết quả đúng là `SHA256(c1 || c2 || ... || ck)`; dấu `||` là phép nối byte. Hash theo luồng phải bằng hash đọc toàn bộ file **khi hai bên xử lý cùng một chuỗi byte**. Các ranh giới chunk không làm thay đổi digest.

- **Thời gian:** xấp xỉ O(N) thao tác băm và đọc I/O khi file có N byte.
- **Bộ nhớ ứng dụng:** xấp xỉ O(B), với B là kích thước buffer cố định; không tăng theo dung lượng file. Provider có thể dùng thêm trạng thái/bộ nhớ nội bộ.
- **Kết quả:** `MessageDigest.digest()` hoàn tất và reset đối tượng. Với file mới, khởi tạo `MessageDigest` mới hoặc chắc chắn reset; không vô tình ghép dữ liệu của hai file.
- **Điều kiện quan trọng:** đọc cùng một file trong hai thời điểm **không đồng nghĩa** đọc cùng ảnh chụp dữ liệu nếu file đang bị sửa.

Bài này tập trung vào ba cách với Java 17+: `InputStream` + `byte[]`, `FileChannel` + `ByteBuffer`, và biến thể `DigestInputStream`. Sau đó xét file vượt 2 GiB, so sánh digest, hiệu năng, tính nhất quán và các lỗi thường gặp.

## 2. Chọn API nào?

| Cách | API chính | Điểm mạnh | Điểm cần chú ý |
| --- | --- | --- | --- |
| Đọc tuần tự bằng luồng | `Files.newInputStream(path)`, `InputStream.read(byte[])`, `MessageDigest.update(byte[], off, len)` | Đơn giản; áp dụng cả cho luồng dữ liệu từ file, network hoặc nội dung tải xuống | Chỉ hash `count` byte vừa đọc; dùng try-with-resources; không dùng `available()` để xác định EOF |
| Đọc qua NIO | `FileChannel.open(path)`, `channel.read(buffer)`, `MessageDigest.update(ByteBuffer)` | Quản lý file position, dễ phối hợp với NIO và direct buffer | Phải dùng `flip()` trước `update`, `clear()` trước lượt đọc mới; `update(ByteBuffer)` thay đổi `position` |
| Luồng tự cập nhật hash | `DigestInputStream` | Hữu ích khi đã có pipeline đọc InputStream | Không tự update digest lần nữa; phải đọc đến hết nếu cần hash toàn file |
| Memory-mapped (tùy nhu cầu) | `FileChannel.map(READ_ONLY, offset, length)` | Có thể hữu ích khi đọc theo cửa sổ lớn | `MappedByteBuffer` một vùng map Java 17 có `size <= Integer.MAX_VALUE`; mapping không phải snapshot và vòng đời khác buffer thông thường |

**Không có phương pháp nào mặc định nhanh nhất cho mọi hệ thống.** Hệ điều hành, cache trang, ổ lưu trữ, provider SHA-256, kích thước buffer và số luồng đọc ảnh hưởng kết quả. Chọn `InputStream` cho độ rõ ràng trước; cân nhắc `FileChannel` khi ứng dụng đang dùng NIO hoặc đã benchmark cho workload thực.

## 3. Vòng đời đúng của `MessageDigest` trong một lần băm file

```text
MessageDigest.getInstance("SHA-256")
              |
              v
       digest.update(...)   <--- lần 1
              |
       digest.update(...)   <--- lần 2
              |
               ...
              |
       digest.update(...)   <--- lần cuối, có thể ngắn hơn buffer
              |
              v
         digest.digest()
              |
              v
      32 byte SHA-256; digest reset
```

`update(byte[], offset, len)` tiêu thụ một phần mảng; **không cần** đợi đủ 64 KiB mới cập nhật. `update(ByteBuffer)` chỉ tiêu thụ các byte trong khoảng `position` đến `limit`. Sau `digest()`, không cần gọi `reset()` nếu định dùng lại đối tượng, nhưng việc tạo instance riêng cho mỗi phép băm giúp tránh nhầm trạng thái khi xử lý đồng thời.

Đặc biệt, **không** tính `digest()` sau mỗi chunk rồi nối các digest. Biểu thức `SHA256(c1) || SHA256(c2)` không bằng `SHA256(c1 || c2)` và không phải giá trị SHA-256 của file. Chỉ gọi `digest()` **một lần sau khi đã đọc hết file**.

## 4. Ví dụ hoàn chỉnh: hai cách băm cùng file

Chương trình dưới đây thực hiện hai phép đọc độc lập để so sánh `InputStream` với `FileChannel + ByteBuffer`. Nếu chạy **không đối số**, chương trình tạo một file tạm chứa đúng ba byte ASCII của chuỗi `"abc"`, rồi xóa file tạm. Trường hợp này cho đầu ra xác định để tự kiểm tra. Nếu truyền đường dẫn, chương trình băm file thật; có thể truyền thêm digest SHA-256 đáng tin cậy để xác minh.

Lưu mã nguồn thành **`FileSha256Demo.java`** (Java 17+):

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class FileSha256Demo {
    private static final int CHUNK_SIZE = 64 * 1024;
    private static final String SHA256_ABC =
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    private FileSha256Demo() {}

    public static byte[] hashStream(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] chunk = new byte[CHUNK_SIZE];

        try (InputStream in = Files.newInputStream(path)) {
            int count;
            while ((count = in.read(chunk)) != -1) {
                if (count > 0) {
                    digest.update(chunk, 0, count);
                }
            }
        }
        return digest.digest();
    }

    public static byte[] hashChannel(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        ByteBuffer buffer = ByteBuffer.allocateDirect(CHUNK_SIZE);

        try (FileChannel channel =
                     FileChannel.open(path, StandardOpenOption.READ)) {
            while (true) {
                int count = channel.read(buffer);
                if (count == -1) {
                    break;
                }
                buffer.flip();
                digest.update(buffer);
                buffer.clear();
            }
        }
        return digest.digest();
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: java FileSha256Demo [file [trusted-sha256-hex]]");
        }

        boolean temporary = args.length == 0;
        Path path = temporary
                ? Files.createTempFile("hash-demo-", ".bin")
                : Path.of(args[0]);

        try {
            if (temporary) {
                Files.write(path, "abc".getBytes(StandardCharsets.US_ASCII));
            }

            byte[] fromStream = hashStream(path);
            byte[] fromChannel = hashChannel(path);
            System.out.println("stream=" +
                    HexFormat.of().formatHex(fromStream));
            System.out.println("channel=" +
                    HexFormat.of().formatHex(fromChannel));
            System.out.println("same=" +
                    MessageDigest.isEqual(fromStream, fromChannel));

            String trustedHex = temporary
                    ? SHA256_ABC
                    : (args.length == 2 ? args[1] : null);
            if (trustedHex != null) {
                byte[] expected = HexFormat.of().parseHex(trustedHex);
                if (expected.length != 32) {
                    throw new IllegalArgumentException(
                            "Expected a 64-character SHA-256 hex digest");
                }
                System.out.println("expectedMatch=" +
                        MessageDigest.isEqual(expected, fromStream));
            }
        } finally {
            if (temporary) {
                Files.deleteIfExists(path);
            }
        }
    }
}
```

Biên dịch và chạy với đầu vào mẫu:

```bash
javac -encoding UTF-8 FileSha256Demo.java
java FileSha256Demo
```

Kết quả:

```text
stream=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
channel=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
same=true
expectedMatch=true
```

Chuỗi băm này là test vector SHA-256 chuẩn của chính xác ba byte `abc`, **không phải** hash của chuỗi có ký tự xuống dòng sau `abc`.

Chạy với file thực (hãy thay đường dẫn):

```bash
java FileSha256Demo "/data/large-archive.zip"
```

Nếu đã nhận được SHA-256 hex qua một nguồn **đáng tin cậy** (ví dụ manifest đã được ký và xác minh), hãy truyền đối số thứ hai:

```bash
java FileSha256Demo "/data/large-archive.zip" "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

Chuỗi hex trong lệnh này chỉ minh họa định dạng đối số, **không phải checksum đúng của file ví dụ**. Khi có đối số thứ hai, `expectedMatch=true` chỉ xảy ra nếu digest của file thực khớp chính xác 32 byte mong đợi. Một file đã bị sửa mà vẫn so với checksum mới lấy từ cùng nguồn không đáng tin thì kết quả so khớp vẫn **không xác lập tính xác thực**.

### 4.1 Giải thích cách dùng InputStream

```java
byte[] chunk = new byte[64 * 1024];
try (InputStream in = Files.newInputStream(path)) {
    int count;
    while ((count = in.read(chunk)) != -1) {
        if (count > 0) {
            digest.update(chunk, 0, count);
        }
    }
}
byte[] sha256 = digest.digest();
```

Đoạn trên là **một phần trích từ chương trình đầy đủ**, giả sử `path` và `digest` đã được tạo.

- `read(chunk)` trả về **số byte thực đọc**, có thể nhỏ hơn dung lượng mảng (ví dụ chunk cuối chỉ có 7 byte). Giá trị `-1` là EOF. Do đó phải gọi `update(chunk, 0, count)`, **không** gọi `update(chunk)` ở mọi lượt, vì những byte cũ còn nằm ở đuôi buffer sẽ bị hash lại.
- Với buffer có độ dài dương, luồng file thông thường đọc đến khi có dữ liệu hoặc EOF. Phép kiểm tra `count > 0` giúp không cập nhật gì khi có trường hợp đọc 0 byte.
- `Files.newInputStream` trả luồng byte; `try-with-resources` tự đóng file kể cả khi `read` hoặc `update` ném lỗi. Không dựa vào `available()` để dừng: phương thức đó ước lượng số byte đọc được ngay mà không chặn, **không** phải kích thước file hay thông báo EOF.
- Một lần đọc không bảo đảm đầy buffer; phải lặp đến `-1`. Không đổi byte thành `String` trước khi hash, vì giải mã và mã hóa lại có thể làm đổi dữ liệu.
- Với bulk read 64 KiB, không nhất thiết thêm `BufferedInputStream`; hãy benchmark nếu pipeline gồm nhiều phép đọc rất nhỏ.

### 4.2 Giải thích FileChannel và vòng đời ByteBuffer

`FileChannel.open(path, StandardOpenOption.READ)` tạo channel đọc tuần tự; `FileChannel.read(buffer)` ghi byte vào buffer bắt đầu từ `position` hiện tại và tăng `position` theo số byte thực đọc. Chu trình cho mỗi lượt:

```text
Mới allocate / sau clear:
    position=0               limit=capacity (65536)
Sau channel.read(...), ví dụ đọc 100 byte:
    position=100             limit=65536
Sau buffer.flip():
    position=0               limit=100
Sau digest.update(buffer):
    position=100             limit=100
Sau buffer.clear():
    position=0               limit=65536
```

`buffer.flip()` chuyển buffer từ chế độ ghi sang đọc: đặt `limit` thành vị trí ghi hiện tại, rồi đưa `position` về 0. `digest.update(buffer)` tiêu thụ **đúng** các byte từ `position` đến `limit` và đưa `position` tới `limit`; nó không tự gọi `flip` và không sửa `limit`. `buffer.clear()` đưa các chỉ số về trạng thái sẵn sàng ghi lại, **không xóa nội dung cũ khỏi bộ nhớ**.

`FileChannel.read` trả `-1` ở EOF, có thể trả ít byte hoặc 0 byte theo hợp đồng API. Code vẫn gọi `flip/update/clear` an toàn nếu `count == 0`; lúc đó phạm vi dữ liệu rỗng. Với `FileChannel` đọc file ở chế độ blocking và buffer còn chỗ, việc đọc thông thường sẽ chờ có dữ liệu hoặc EOF, nên không cần triển khai vòng chờ chủ động. Đối với **kênh không blocking khác** (ví dụ socket), phải xử lý trường hợp trả 0 để tránh vòng lặp quay CPU.

`ByteBuffer.allocateDirect(64 * 1024)` cấp direct buffer, có thể giảm một số bước sao chép trong thao tác I/O, nhưng có chi phí cấp phát và sử dụng vùng nhớ ngoài heap. `ByteBuffer.allocate(...)` cấp heap buffer cũng tương thích `MessageDigest.update(ByteBuffer)`. Direct không bảo đảm luôn nhanh hơn và không nên cấp phát direct buffer lớn cho từng request mà không xét ngân sách bộ nhớ.

### 4.3 Tại sao có thể xử lý file lớn hơn 2 GiB?

`InputStream.read` và `FileChannel.read(ByteBuffer)` chỉ cần biết **số byte của một chunk** (kiểu `int`). Vòng lặp có thể chạy hàng chục nghìn lần cho file nhiều GB; kích thước file thực tế được quản lý bằng metadata hoặc `long` khi cần. Không yêu cầu mảng `byte[]` có kích thước bằng file, cũng không đưa tổng chiều dài file vào một `ByteBuffer` duy nhất.

Một buffer 64 KiB có thể tái sử dụng để đọc file 5 GiB, 50 GiB, ... miễn là file hệ thống/provider hỗ trợ và chương trình có đủ thời gian, dung lượng I/O. Trần kích thước là trần của hệ thống file/API/độ dài nguồn dữ liệu, chứ **không** phải 64 KiB. Nếu cần hiển thị tiến độ, dùng bộ đếm `long processed += count` mỗi lần đọc, không tăng theo `buffer.capacity()`.

## 5. Kiểm thử cả chunk rỗng, đúng biên và dư 1 byte

Một lỗi phổ biến chỉ xuất hiện khi file dài `65536 + 1` byte: lượt đọc cuối có 1 byte nhưng tác giả lại hash toàn bộ mảng 65536 byte. Một lỗi khác là quên `flip` khiến ByteBuffer truyền cả vùng chưa được đọc. Kiểm tra nhiều độ dài sát biên buffer giúp bắt những lỗi này.

Lưu thành **`HashBoundaryCheck.java`** trong cùng thư mục với `FileSha256Demo.java`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;

public final class HashBoundaryCheck {
    public static void main(String[] args) throws Exception {
        int[] lengths = {0, 1, 65535, 65536, 65537, 131079, 1048577};
        Path file = Files.createTempFile("hash-boundaries-", ".bin");

        try {
            for (int length : lengths) {
                byte[] data = new byte[length];
                for (int i = 0; i < length; i++) {
                    data[i] = (byte) (31 * i + 7);
                }
                Files.write(file, data);

                byte[] expected = MessageDigest.getInstance("SHA-256")
                        .digest(data);
                byte[] stream = FileSha256Demo.hashStream(file);
                byte[] channel = FileSha256Demo.hashChannel(file);
                if (!MessageDigest.isEqual(expected, stream)
                        || !MessageDigest.isEqual(expected, channel)) {
                    throw new AssertionError(
                            "Mismatch for file length " + length);
                }
            }
            System.out.println("cases=" + lengths.length);
            System.out.println("allMatch=true");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

`HashBoundaryCheck` là chương trình **chạy đầy đủ** nhưng **phụ thuộc** hai phương thức `FileSha256Demo.hashStream` và `FileSha256Demo.hashChannel` của lớp ví dụ trước. Chương trình tự tạo file tạm với dữ liệu nhị phân có thể tái lập, thử 7 kích thước, và xóa file khi xong. Bộ dữ liệu thử chỉ ~1 MiB ở trường hợp lớn nhất nên việc giữ mảng toàn bộ trong **kiểm thử** là hợp lý; đây không phải mẫu xử lý file lớn ngoài sản phẩm.

```bash
javac -encoding UTF-8 FileSha256Demo.java HashBoundaryCheck.java
java HashBoundaryCheck
```

```text
cases=7
allMatch=true
```

Những độ dài được kiểm tra gồm **0, 1, 65535, 65536, 65537, 131079 và 1048577** byte. SHA-256 trên byte[] nhỏ được dùng làm đáp án độc lập cho hai đường đọc chunk; ngoại lệ `AssertionError` cho biết có cách đọc khác với dữ liệu gốc.

Kiểm thử nên mở rộng bằng file thực có byte 0, byte giá trị âm khi nhìn dưới dạng `byte` Java, nội dung đa ngôn ngữ ở các encoding khác nhau và file lớn hơn 2 GiB khi môi trường tích hợp hỗ trợ. Với file nhỏ, chuỗi rỗng có SHA-256 chuẩn là `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; đây là test vector tốt để chắc chắn vòng lặp xử lý EOF ngay từ đầu.

## 6. Biến thể: DigestInputStream tự cập nhật hash khi đọc

Nếu ứng dụng đã sử dụng `InputStream` để copy, parse hoặc đọc dữ liệu từ nguồn khác, có thể bọc luồng bằng `java.security.DigestInputStream` để cập nhật digest **tự động khi các byte được đọc qua wrapper**:

```java
// Hàm minh họa độc lập về mặt chữ ký; đặt trong lớp Java với import:
// java.io.IOException, java.nio.file.Files, java.nio.file.Path,
// java.security.DigestInputStream, java.security.MessageDigest,
// java.security.NoSuchAlgorithmException.
static byte[] hashWithDigestInputStream(Path path)
        throws IOException, NoSuchAlgorithmException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (DigestInputStream input =
                 new DigestInputStream(Files.newInputStream(path), digest)) {
        byte[] chunk = new byte[64 * 1024];
        while (input.read(chunk) != -1) {
            // DigestInputStream da goi digest.update(...) trong read().
        }
    }
    return digest.digest();
}
```

Giải thích: `DigestInputStream.read(...)` sẽ gọi `digest.update(...)` khi chế độ cập nhật đang bật (mặc định bật). **Không** gọi thêm `digest.update(chunk)` trong vòng lặp: như vậy mỗi byte bị hash hai lần. Cần đọc luồng **đến EOF** để băm đủ nội dung; đóng trước khi đọc hết chỉ tạo hash của phần đã tiêu thụ. Phương thức `on(false)` có thể tắt cập nhật nếu giao thức yêu cầu bỏ qua một đoạn (ví dụ header), nhưng khi ấy giá trị digest **không còn là SHA-256 của toàn file**.

Cách này phù hợp khi vừa đọc dữ liệu để xử lý vừa cần hash đúng phần dữ liệu mà pipeline tiêu thụ. Nếu cần hash toàn bộ file bất kể xử lý nghiệp vụ đọc bao nhiêu byte, hãy tách việc tiêu thụ đầy đủ khỏi logic dừng sớm.

## 7. Có nên memory-map file lớn?

Một số hệ thống dùng `FileChannel.map(READ_ONLY, offset, size)` để tạo `MappedByteBuffer` và đưa thẳng vào `MessageDigest.update(ByteBuffer)`. Điều đó vẫn hoạt động với cùng nguyên tắc `position/limit`, nhưng ở Java 17, overload tạo `MappedByteBuffer` có giới hạn **mỗi lần map không vượt `Integer.MAX_VALUE` byte**. Vì vậy không thể map cả file 5 GiB bằng một lời gọi.

Nếu thật sự cần mapping, phải map **theo cửa sổ có độ dài giới hạn**, với `offset` kiểu `long`; hash từng cửa sổ theo đúng thứ tự, cuối cùng gọi `digest()` một lần. Minh họa thuật toán (đoạn khung, **không** phải chương trình độc lập):

```java
// channel: FileChannel da mo READ, digest: MessageDigest SHA-256
final long WINDOW = 1L << 30; // 1 GiB, nho hon Integer.MAX_VALUE
long size = channel.size();
for (long pos = 0; pos < size; ) {
    long length = Math.min(WINDOW, size - pos);
    ByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, pos, length);
    digest.update(mapped);
    pos += length;
}
byte[] result = digest.digest();
```

Chú ý: vùng map có vòng đời độc lập với việc đóng channel; dữ liệu/file bị thay đổi hoặc rút ngắn sau khi map có thể gây hành vi phụ thuộc hệ điều hành, kể cả lỗi truy cập vùng map. Mapping có thể làm tăng áp lực địa chỉ bộ nhớ và khó quản lý giải phóng kịp thời. Với nhiệm vụ **chỉ băm tuần tự**, đọc `InputStream` hoặc `FileChannel.read` thường là lựa chọn dễ kiểm soát và portable hơn. Muốn kết luận mapping nhanh hơn phải đo bằng benchmark cùng môi trường và file thật.

## 8. Kiểm tra checksum: khớp hash khác với xác thực nguồn

Một SHA-256 không có khóa cho phép kiểm tra **hai chuỗi byte có cùng digest hay không** (với xác suất va chạm cực thấp đối với SHA-256 khi dùng đúng). Nhưng hash không chứng minh người gửi là ai; ai sửa được cả file lẫn giá trị hash kèm theo đều có thể cung cấp cặp mới tự nhất quán.

Luồng xác minh an toàn hơn:

1. Lấy SHA-256 mong đợi từ **nguồn đáng tin**: ví dụ metadata từ kênh đã được xác thực, hoặc manifest có **chữ ký số đã xác minh** bằng khóa tin cậy.
2. Giải mã hex thành đúng **32 byte**; đầu vào SHA-256 thông thường phải có 64 ký tự hex, không bao gồm dấu cách hoặc tiền tố `0x` nếu parser không xử lý.
3. Băm đúng byte của file với `MessageDigest`, không giải mã thành text.
4. So sánh byte bằng `MessageDigest.isEqual(expected, actual)`, sau khi kiểm tra độ dài. Hàm này tránh so sánh rồi dừng ở byte đầu tiên khác; tuy nhiên cần thiết kế thêm bảo vệ về nguồn dữ liệu và ranh giới bảo mật.
5. Nếu không khớp, **từ chối sử dụng file**; không lấy giá trị digest mới sinh để "sửa" expected nếu chưa có một nguồn tin cậy xác nhận thay đổi.

Trong chương trình chính, `same=true` chỉ nói hai phương pháp đọc đã cho cùng digest, **không** nói file đáng tin. Khi nhận expected từ manifest tin cậy, `expectedMatch=true` mới cho phép áp dụng quy tắc của quy trình xác minh. SHA-256 không mã hóa file và không che giấu nội dung. Dùng HMAC hoặc chữ ký số nếu cần bảo đảm tính xác thực; băm file đơn thuần không thay thế chữ ký.

Độ dài đầu ra là **số byte digest**, không liên quan đến kích thước file; 64 ký tự hex vì mỗi byte được biểu diễn thành hai chữ số hex. Java 17 cung cấp `HexFormat.of().formatHex(...)` và `HexFormat.of().parseHex(...)`; không cần tự chuyển các byte âm kiểu Java bằng cách nối chuỗi tùy ý.

## 9. File thay đổi khi đang hash: tính nhất quán và TOCTOU

Với file rất lớn, phép băm có thể kéo dài. Trong thời gian đó, một tiến trình khác có thể ghi, truncate, thay thế hoặc đổi nội dung tại đường dẫn. Một lần đọc tuần tự **không được JCA/FileChannel bảo đảm là bản chụp nguyên tử** của file.

- Lượt hash `InputStream` và lượt hash `FileChannel` trong chương trình chính diễn ra **nối tiếp**, nên nếu file bị sửa giữa hai lượt, `same=false` có thể phản ánh **hai phiên bản khác nhau** thay vì lỗi thuật toán.
- File bị kéo dài trong lúc đọc có thể khiến dữ liệu được đọc theo một biên EOF khác; file bị rút ngắn gây thất bại hoặc dữ liệu thiếu. Hash khi file đang bị sửa có thể không tương ứng với một trạng thái ổn định nào.
- Kiểm tra `Files.size(path)` hoặc thời gian sửa **trước và sau** chỉ giúp phát hiện một số thay đổi, **không bảo đảm** file không bị sửa rồi khôi phục. `FileChannel.lock(...)` cũng không phải khóa cưỡng chế di động tuyệt đối giữa mọi tiến trình/hệ điều hành.
- Nếu cần bằng chứng tin cậy, hash **bản snapshot bất biến**, file tạm được tạo xong rồi đóng, bản copy kiểm soát quyền ghi, hoặc đối tượng lưu trữ phiên bản cố định. Khi tải xuống, có thể hash ngay trong quá trình ghi ra file tạm, kiểm tra expected digest sau khi hoàn tất, rồi chỉ công bố/đổi tên file theo quy trình an toàn.
- Với đường dẫn do người dùng cung cấp, cần đánh giá symlink, directory traversal, quyền truy cập và việc đường dẫn bị thay thế giữa lúc kiểm tra và mở file. Quyết định truy cập file phải dựa trên chính sách ứng dụng, không chỉ dựa vào hash.

Hash chỉ phản ánh byte đã được engine tiêu thụ trong lần thực thi đó. Nếu ứng dụng muốn bảo đảm tính toàn vẹn của dữ liệu sẽ **được dùng sau này**, phải đảm bảo dữ liệu đã hash chính là dữ liệu được lưu, chuyển đi hoặc xử lý, không lấy lại file khác từ cùng đường dẫn mà không kiểm soát phiên bản.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `Files.readAllBytes` trên file rất lớn | O(N) RAM; có thể `OutOfMemoryError` hoặc đụng giới hạn mảng | Đọc chunk cố định bằng stream/channel |
| `digest.update(chunk)` dù `read` chỉ trả 1 byte | Hash cả dữ liệu thừa từ lần trước trong mảng | `digest.update(chunk, 0, count)` |
| `while (in.available() > 0)` | Có thể dừng sớm, bỏ dữ liệu | Đọc đến `read(...) == -1` |
| Gọi `digest()` sau mỗi chunk | Cho chuỗi digest của từng chunk, không phải hash file | Chỉ final sau khi đọc xong |
| Quên `buffer.flip()` | Hash sai vùng nhớ, kể cả byte chưa thuộc file | `read → flip → update → clear` |
| Quên `buffer.clear()` | Buffer hết chỗ, lượt đọc kế tiếp có thể trả 0 liên tục | Clear chỉ số sau khi update; không giữ stale position |
| Gọi `flip()` hai lần hoặc `rewind()` sai | Giới hạn/số byte hợp lệ sai, mất hoặc hash lặp dữ liệu | Theo đúng state `position/limit` của từng lượt |
| Dùng `String`/`Reader` để băm "file văn bản" | Encoding và newline có thể thay đổi byte gốc | Băm byte từ `InputStream` hoặc `ByteBuffer` |
| Đọc cùng `MessageDigest` từ nhiều thread | Trộn trạng thái nhiều file; digest sai | Tạo digest riêng cho mỗi tác vụ/luồng |
| Thấy `same=true` rồi kết luận an toàn | Hai lượt có thể cùng đọc file đã bị tấn công | So với digest tin cậy; xác minh chữ ký/HMAC khi cần |
| Dựa vào `size`/`lastModifiedTime` như snapshot | Bỏ sót thay đổi trong lúc đọc | Dùng ảnh chụp bất biến hoặc workflow có kiểm soát |
| Nuốt `IOException` rồi vẫn trả digest | Hash của nội dung chưa đọc đủ bị coi là hoàn tất | Để exception làm thất bại toàn tác vụ; xóa/từ chối kết quả |

**Lưu ý về lỗi:** `NoSuchAlgorithmException` xảy ra nếu provider không hỗ trợ thuật toán; Java SE phải hỗ trợ `SHA-256` theo danh sách chuẩn. `IOException` có thể do file không tồn tại, quyền bị từ chối, thiết bị hỏng hoặc đọc giữa chừng thất bại. Nếu hash file lỗi, không được trả một digest "tạm" như kết quả hợp lệ. `try-with-resources` đóng tài nguyên I/O kể cả khi có exception; không tự nuốt hoặc thay thế exception bằng chuỗi hash rỗng.

## 11. Hiệu năng và bộ nhớ: đo thay vì đoán

**Bắt đầu với buffer vừa phải** như 32–256 KiB, ví dụ 64 KiB, rồi đo trên loại file và thiết bị thực tế. Buffer quá nhỏ tăng số lời gọi I/O; buffer quá lớn tăng footprint (nhất là khi hàng trăm request đồng thời), có thể gây áp lực heap hoặc direct memory mà lợi ích I/O không tăng tương ứng.

**Direct vs heap ByteBuffer:** direct buffer có thể có lợi trong một số đường truyền I/O native, nhưng cấp phát direct buffer thường đắt hơn heap buffer, và provider băm có thể phải sao chép dữ liệu vào implementation nội bộ. Đừng giả định `allocateDirect` cho throughput cao hơn; đo cả CPU, GC, direct memory, latency và số tác vụ đồng thời.

**So sánh công bằng:** thử nhiều kích thước file, nhiều thiết bị và trạng thái cache. Đọc hai lần liên tiếp thường khiến lượt thứ hai được hưởng OS page cache; cần đảo thứ tự, warm-up và nhiều lần đo. Chỉ dùng `System.nanoTime` thô để chẩn đoán gần đúng; nếu muốn benchmark nghiêm túc thì dùng công cụ như JMH và đo cả I/O thực tế.

**Không cần song song hóa digest bằng cách ghép hash chunk.** SHA-256 của một file có cấu trúc state nối tiếp; tính hash riêng cho mỗi chunk rồi nối không cho ra SHA-256 của toàn file. Các thiết kế hash tree/Merkle tree là **giao thức khác** với đầu ra khác, chỉ dùng nếu định dạng bên tiêu thụ có quy định.

**Một tác vụ, một instance:** `MessageDigest` có state; không chia cùng instance cho nhiều file đang xử lý song song. Nếu tối ưu tái sử dụng object theo thread, phải đảm bảo `reset()` trước thông điệp mới và không chia sẻ đồng thời; tạo mới đơn giản hơn khi chi phí chấp nhận được.

## 12. Tự kiểm tra kiến thức

1. Một file 8 GiB có cần tạo mảng byte dài 8 GiB để lấy SHA-256 không? **Không**; chunk 64 KiB và `update` liên tục là đủ.
2. `InputStream.read(chunk)` trả 19 khi buffer có 65536 phần tử thì nên hash bao nhiêu byte? **19 byte**: `digest.update(chunk, 0, 19)`.
3. ByteBuffer đang có `position=19, limit=65536` sau `channel.read`; cần làm gì trước khi `digest.update`? **`flip()`**, để phạm vi đọc đúng 19 byte; sau update phải `clear()`.
4. Tại sao không gọi `digest()` sau mỗi chunk? Vì `digest()` kết thúc **một hash** và reset state; kết quả chunk riêng **khác** hash của phép nối byte.
5. File rỗng có digest không? **Có**: SHA-256 của luồng 0 byte là `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
6. Hai cách đọc cho cùng digest có chứng minh file do nhà phát hành công bố không? **Không**; phải đối chiếu với digest nguồn tin cậy hoặc xác minh chữ ký số.
7. Vì sao `lastModifiedTime` không chứng minh file ổn định khi hash? Có thể thay đổi rồi phục hồi timestamp, hoặc sửa trong lúc đọc. Cần bản snapshot hay quy trình phiên bản bất biến.
8. Có thể băm file 10 GiB bằng một `MappedByteBuffer` từ `FileChannel.map` Java 17 không? **Không** với một vùng map kiểu `MappedByteBuffer` duy nhất; cần chia cửa sổ map hoặc dùng vòng lặp `read`.

## Tài liệu API chính thức

- [MessageDigest (Java SE 21): update(ByteBuffer), digest(), reset(), isEqual()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Files.newInputStream(Path)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#newInputStream(java.nio.file.Path,java.nio.file.OpenOption...))
- [InputStream.read(byte[])](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [FileChannel.read(ByteBuffer) và map()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ByteBuffer: flip(), clear(), position(), limit()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
- [DigestInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DigestInputStream.html)
- [HexFormat (Java 17+)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html)
