# Thiết kế bản ghi có vị trí và kích thước xác định trong Java: truy cập ngẫu nhiên

## 1. Mục tiêu và bài toán

Khi ứng dụng cần **đọc hoặc cập nhật trực tiếp bản ghi thứ N** trong một tệp dữ liệu, đọc toàn bộ tệp từ đầu đến N thường không cần thiết. Một thiết kế *fixed-size record* đặt mỗi bản ghi vào một vùng byte có kích thước không đổi; biết chỉ số bản ghi là tính được ngay vị trí byte của nó.

Ví dụ, một tệp lưu tài khoản gồm phần đầu tệp (*header*) 16 byte và nhiều bản ghi 64 byte. Để đọc bản ghi có chỉ số 2 (đánh số từ 0), ứng dụng truy cập trực tiếp byte:

~~~text
offset(index) = HEADER_SIZE + index * RECORD_SIZE
offset(2)     = 16 + 2 * 64 = 144
record 2      = các byte [144, 207] (64 byte)
~~~

Đây là **offset tính bằng byte** trong tệp; nó không phải chỉ số ký tự, số dòng văn bản hoặc khóa nghiệp vụ (`id`). Với bố trí cố định, chi phí định vị theo chỉ số có thể là O(1); hiệu suất I/O thực tế còn phụ thuộc hệ điều hành, thiết bị lưu trữ, cache và mức phân mảnh.

Sau bài học, bạn có thể thiết kế một *schema nhị phân ổn định*, tính vị trí không tràn số, đọc/ghi đúng số byte bằng `FileChannel`, xử lý dữ liệu chuỗi có độ dài thay đổi nhưng vùng lưu trữ cố định, đánh dấu xóa và nhận diện giới hạn về tính nhất quán/durability.

## 2. Quy ước trước khi ghi dữ liệu

Một định dạng bản ghi nhị phân cần một **hợp đồng** để bên ghi và bên đọc hiểu đúng cùng các byte. Hợp đồng này phải quy định rõ:

1. Kích thước header và kích thước một record theo **byte**, không theo số ký tự.
2. Kiểu và vị trí của từng trường; signed/unsigned, thứ tự byte (*endianness*), kiểu số tiền và giá trị biểu thị trạng thái.
3. Bảng mã chuỗi; cách lưu độ dài chuỗi và đệm đến kích thước cố định.
4. Cách tính offset, đánh số chỉ số, cách xác định bản ghi đã xóa hoặc chưa bao giờ ghi.
5. Version/schema khi mở lại tệp, chiến lược cập nhật, phát hiện lỗi và xử lý crash.

Không thể chỉ lưu bằng `DataOutputStream.writeUTF`, sau đó suy ra rằng mỗi bản ghi có độ dài cố định: độ dài chuỗi phụ thuộc nội dung và `writeUTF` dùng định dạng modified UTF-8 có tiền tố độ dài riêng. Cũng không thể dùng `String.length()` để ước lượng số byte UTF-8: một chữ tiếng Việt có thể chiếm nhiều byte dù chỉ là một ký tự hiển thị.

### Schema mẫu: 16 byte header + các record 64 byte

Phần đầu tệp:

| Offset tuyệt đối | Số byte | Trường | Quy ước |
| --- | ---: | --- | --- |
| 0–3 | 4 | `magic` | 0x46524543 tương ứng `FREC` |
| 4–7 | 4 | `version` | Số nguyên 32 bit, giá trị 1 |
| 8–11 | 4 | `recordSize` | Số nguyên 32 bit, giá trị 64 |
| 12–15 | 4 | `reserved` | 0 ở version 1 |

Mỗi bản ghi tính **tương đối** từ offset bắt đầu record:

| Offset trong record | Số byte | Trường | Quy ước |
| --- | ---: | --- | --- |
| 0 | 1 | `status` | 1 = đang dùng; 2 = xóa logic |
| 1–8 | 8 | `id` | `long` có dấu, khóa nghiệp vụ |
| 9–16 | 8 | `balanceCents` | `long`: đơn vị tiền nhỏ nhất, không dùng `double` |
| 17–18 | 2 | `nameLength` | Độ dài byte UTF-8, 0–40 |
| 19–58 | 40 | `nameArea` | Byte UTF-8 + vùng đệm bằng 0 |
| 59–63 | 5 | `reserved` | 0 ở version 1 |
| **Tổng** | **64** | | |

Toàn bộ `int`/`long`/`short` được mã hóa theo `ByteOrder.BIG_ENDIAN`: byte có ý nghĩa cao nhất đứng trước. Bên đọc phải dùng cùng byte order; nếu đổi sang little-endian mà không đổi schema, dữ liệu số sẽ bị hiểu sai.

Trạng thái `status` cho phép phân biệt bản ghi đang hoạt động và bản ghi bị xóa logic. Giá trị 0 không được dùng cho record hợp lệ; nó thường xuất hiện trong vùng chưa được khởi tạo hoặc vùng trống của tệp thưa (*sparse file*). Không được tự hiểu một vùng toàn số 0 là bản ghi hợp lệ.

Một tệp chứa ba record liên tục có độ dài chính xác `16 + 3 * 64 = 208` byte. Record chỉ số 1 bắt đầu tại byte 80, kết thúc ở byte 143; record chỉ số 2 bắt đầu tại byte 144.

## 3. Tính offset đúng và bảo vệ ranh giới

Công thức cơ bản:

~~~java
long offset = Math.addExact(
        (long) headerSize,
        Math.multiplyExact(index, (long) recordSize));
~~~

Đây là **mảnh mã minh họa**: `headerSize`, `index` và `recordSize` cần được khai báo phù hợp. Các phép `Math.multiplyExact` và `Math.addExact` ném `ArithmeticException` nếu tràn `long`, tránh lỗi nhân số nguyên `int` rồi mới ép lên `long`. Cần từ chối `index < 0` và chỉ cho phép ghi ở slot hợp lệ theo chính sách của ứng dụng.

Để đọc **trọn vẹn** record, kiểm tra:

~~~text
offset >= HEADER_SIZE
offset + RECORD_SIZE <= fileSize
(fileSize - HEADER_SIZE) % RECORD_SIZE == 0
~~~

Đây là các ràng buộc đối với tệp liên tục, không có trailer hoặc vùng metadata chen giữa. Phải tính `offset + RECORD_SIZE` bằng phép kiểm tra tràn (ví dụ `Math.addExact`) và kiểm tra bản ghi trong phạm vi đã cấp phát. Nếu file bị cắt còn một phần record, không được im lặng giải mã phần còn lại từ những byte chưa đọc.

**Phân biệt chỉ số lưu trữ và ID nghiệp vụ.** Record có `id=102` không nhất thiết ở vị trí 102. Ví dụ lưu ở index 1. Nếu ID không liên tục, cần bảng ánh xạ `id → slotIndex` (hoặc B-tree/hash index được lưu riêng), không lấy ID làm offset một cách máy móc vì sẽ tạo lỗ hổng lớn trong tệp.

## 4. Ví dụ Java 17+ hoàn chỉnh: đọc, cập nhật, xóa logic theo vị trí

Ví dụ dùng `java.nio.channels.FileChannel` và `ByteBuffer` để đặt record vào một vùng byte xác định. Nó tạo **tệp tạm riêng**, ghi ba bản ghi, đóng/mở lại tệp, đọc trực tiếp record 1, cập nhật record 1 ngay tại vị trí cũ, đánh dấu xóa record 2 và dọn tệp tạm khi hoàn tất.

Lưu vào file `FixedRecordDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordDemo {
    private static final int HEADER_SIZE = 16;
    private static final int RECORD_SIZE = 64;
    private static final int NAME_BYTES = 40;
    private static final int MAGIC = 0x46524543; // "FREC"
    private static final int VERSION = 1;
    private static final byte ACTIVE = 1;
    private static final byte DELETED = 2;

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("fixed-record-", ".bin");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                writeHeader(channel);
                writeRecord(channel, 0, 101, 125_000, "Lan");
                writeRecord(channel, 1, 102, 230_500, "Minh");
                writeRecord(channel, 2, 103, 75_000, "An");
                channel.force(true);
            }

            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                validateHeader(channel);
                System.out.println("Offset record 1: " + offsetOf(1));
                System.out.println("Record 1: " + readRecord(channel, 1));
                writeRecord(channel, 1, 102, 240_000, "Minh");
                System.out.println("Updated record 1: " + readRecord(channel, 1));
                markDeleted(channel, 2);
                System.out.println("Record 2: " + readRecord(channel, 2));
                System.out.println("Count slots: " +
                        (channel.size() - HEADER_SIZE) / RECORD_SIZE);
                channel.force(true);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static long offsetOf(long index) {
        if (index < 0) throw new IllegalArgumentException("index must be >= 0");
        return Math.addExact((long) HEADER_SIZE,
                Math.multiplyExact(index, (long) RECORD_SIZE));
    }

    private static void writeHeader(FileChannel ch) throws IOException {
        ByteBuffer b = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN);
        b.putInt(MAGIC).putInt(VERSION).putInt(RECORD_SIZE).putInt(0);
        b.flip();
        writeFully(ch, b, 0);
    }

    private static void validateHeader(FileChannel ch) throws IOException {
        if (ch.size() < HEADER_SIZE) throw new EOFException("Missing header");
        ByteBuffer b = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN);
        readFully(ch, b, 0);
        b.flip();
        if (b.getInt() != MAGIC || b.getInt() != VERSION
                || b.getInt() != RECORD_SIZE || b.getInt() != 0) {
            throw new IOException("Unsupported header");
        }
        if ((ch.size() - HEADER_SIZE) % RECORD_SIZE != 0) {
            throw new IOException("Truncated record region");
        }
    }

    private static void writeRecord(FileChannel ch, long index,
                                    long id, long cents, String name) throws IOException {
        byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
        if (utf8.length > NAME_BYTES) {
            throw new IllegalArgumentException("name exceeds 40 UTF-8 bytes");
        }
        ByteBuffer b = ByteBuffer.allocate(RECORD_SIZE).order(ByteOrder.BIG_ENDIAN);
        b.put(ACTIVE).putLong(id).putLong(cents)
                .putShort((short) utf8.length).put(utf8);
        // allocate() initialized all remaining bytes to 0; write the full slot.
        b.position(RECORD_SIZE);
        b.flip();
        writeFully(ch, b, offsetOf(index));
    }

    private static String readRecord(FileChannel ch, long index) throws IOException {
        long at = offsetOf(index);
        if (ch.size() < Math.addExact(at, (long) RECORD_SIZE)) {
            throw new EOFException("Record out of range");
        }
        ByteBuffer b = ByteBuffer.allocate(RECORD_SIZE).order(ByteOrder.BIG_ENDIAN);
        readFully(ch, b, at);
        b.flip();
        byte state = b.get();
        if (state == DELETED) return "<deleted>";
        if (state != ACTIVE) throw new IOException("Invalid record state");
        long id = b.getLong();
        long cents = b.getLong();
        int length = Short.toUnsignedInt(b.getShort());
        if (length > NAME_BYTES) throw new IOException("Invalid name length");
        byte[] nameArea = new byte[NAME_BYTES];
        b.get(nameArea);
        String name = new String(nameArea, 0, length, StandardCharsets.UTF_8);
        return "id=" + id + ", cents=" + cents + ", name=" + name;
    }

    private static void markDeleted(FileChannel ch, long index) throws IOException {
        long at = offsetOf(index);
        if (ch.size() < Math.addExact(at, (long) RECORD_SIZE)) {
            throw new EOFException("Record out of range");
        }
        writeFully(ch, ByteBuffer.wrap(new byte[] { DELETED }), at);
    }

    private static void writeFully(FileChannel ch, ByteBuffer b, long at) throws IOException {
        while (b.hasRemaining()) {
            int count = ch.write(b, at);
            if (count <= 0) throw new IOException("Write made no progress");
            at += count;
        }
    }

    private static void readFully(FileChannel ch, ByteBuffer b, long at) throws IOException {
        while (b.hasRemaining()) {
            int count = ch.read(b, at);
            if (count < 0) throw new EOFException("Unexpected end of file");
            if (count == 0) throw new IOException("Read made no progress");
            at += count;
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FixedRecordDemo.java
java FixedRecordDemo
~~~

Stdout chính xác (đã biên dịch và chạy với JDK 21, tương thích Java 17):

~~~text
Offset record 1: 80
Record 1: id=102, cents=230500, name=Minh
Updated record 1: id=102, cents=240000, name=Minh
Record 2: <deleted>
Count slots: 3
~~~

**Diễn giải những điểm quan trọng trong code:**

- `writeHeader` ghi magic, version, kích thước record và reserved trước khi ghi phần thân. `validateHeader` chặn định dạng không tương thích, tệp thiếu header và phần thân không chia hết cho 64.
- `FileChannel.write(buffer, position)` và `FileChannel.read(buffer, position)` thao tác ở **vị trí tuyệt đối**; chúng không dùng/không thay đổi vị trí hiện tại của channel. Điều này giúp truy cập trực tiếp nhưng không làm các thao tác đồng thời tự động trở nên an toàn.
- Một lần `read`/`write` **không được bảo đảm xử lý đủ** mọi byte yêu cầu. Hai hàm `readFully`/`writeFully` cập nhật vị trí tuyệt đối sau từng lần đọc/ghi; `EOFException` nghĩa là không đủ byte. Trong ví dụ dùng channel dạng blocking trên tệp thông thường; trả 0 được báo thành lỗi tiến độ.
- `ByteBuffer.allocate(RECORD_SIZE)` khởi tạo mảng byte bằng 0. Sau khi ghi các trường có độ dài thực tế, `position(RECORD_SIZE)` rồi `flip()` khiến lần ghi chứa đủ 64 byte, bao gồm byte đệm. Nếu gọi `flip()` ngay sau `put(utf8)`, bộ đệm chỉ chứa phần đã ghi và file sẽ **không** nhận đủ một record 64 byte.
- `writeRecord` luôn viết đúng slot 64 byte: cập nhật thông tin ngắn hơn không để lộ byte tên cũ ở vùng padding. Ví dụ ghi ba slot liên tục từ 0 đến 2; helper tối giản chưa kiểm tra chính sách cho phép index bị bỏ trống, vì thế mã sản phẩm nên giới hạn index hợp lệ trước khi gọi.
- `readRecord` giải mã `status`, `long`, độ dài byte UTF-8 và `nameArea` theo đúng schema. Hàm từ chối trạng thái không hợp lệ và `nameLength > 40`; bản ghi xóa logic trả chuỗi `<deleted>` trong ví dụ.
- `markDeleted` chỉ đổi byte trạng thái tại đầu slot. Kích thước file và chỉ số record khác không thay đổi. `Count slots` đếm **slot vật lý**, bao gồm cả slot đã xóa; nó không phải số bản ghi đang hoạt động.
- Hai khối `try-with-resources` đóng channel đúng thời điểm; `Files.deleteIfExists` xóa tệp tạm sau khi các channel đã đóng. `force(true)` yêu cầu đẩy các cập nhật file/metadata ra thiết bị lưu trữ theo hợp đồng của API, nhưng không biến nhiều lần ghi thành một giao dịch nguyên tử.

## 5. Vì sao độ dài byte của chuỗi phải được lưu riêng?

Trong một schema cố định, vùng tên có thể dài 40 byte nhưng tên thật chỉ dùng 3, 10 hoặc 38 byte. Khi đọc, không thể phân biệt chính xác dữ liệu và padding bằng cách bỏ những byte 0 ở cuối nếu giá trị hợp lệ có thể chứa ký tự NUL. Vì thế ví dụ lưu riêng `nameLength` ở hai byte và đọc đúng phần đó.

Ví dụ:

~~~text
name = "Lan"
UTF-8 = 4C 61 6E                      (3 byte)
nameLength = 3                        (2 byte trong schema)
nameArea = 4C 61 6E 00 00 ... 00     (tổng 40 byte)
~~~

Nếu tên là `"Hà"` thì `name.length()` bằng 2 đơn vị ký tự UTF-16, nhưng chuỗi UTF-8 chiếm 3 byte (`H`: 1, `à`: 2). Giới hạn của schema là **40 byte mã hóa**, không phải 40 ký tự Unicode; không được cắt tùy ý sau byte thứ 40 vì có thể làm hỏng một chuỗi UTF-8 nhiều byte.

Trong hệ thống thực tế, khi bộ mã hóa gặp surrogate Unicode không hợp lệ hoặc bộ giải mã gặp dãy UTF-8 lỗi, hãy sử dụng `CharsetEncoder`/`CharsetDecoder` cấu hình `CodingErrorAction.REPORT` để từ chối dữ liệu thay vì để dấu thay thế lặng lẽ xuất hiện. `new String(bytes, UTF_8)` trong ví dụ minh họa giải mã dữ liệu đã được ứng dụng tự ghi; riêng nó không phải bộ xác thực UTF-8 nghiêm ngặt cho tệp tùy ý từ nguồn không tin cậy.

Giá trị `nameLength` có kiểu Java `short` khi viết. Ví dụ giải mã bằng `Short.toUnsignedInt` để xem đúng 0–65535; tiếp tục kiểm tra giới hạn 40 của schema thay vì tin vào dữ liệu trên đĩa.

## 6. Cập nhật, chèn, xóa và tái sử dụng slot

**Cập nhật tại chỗ** chỉ phù hợp khi mọi phiên bản bản ghi đều chiếm đúng `RECORD_SIZE`. Trong ví dụ, đổi `balanceCents` của index 1 không khiến index 2 đổi vị trí. Tên có thể dài/ngắn hơn miễn vẫn mã hóa vào vùng 40 byte; code ghi lại toàn bộ slot và zero padding.

**Chèn liên tục (append)**: slot tiếp theo thường có index `(fileSize - HEADER_SIZE) / RECORD_SIZE`, sau khi đã xác minh kích thước file hợp lệ. Khi nhiều thread/process cùng append, phải phối hợp cấp phát index để không chọn trùng slot.

**Xóa logic (tombstone)**: đặt status thành `DELETED`, giữ nguyên vị trí vật lý của record khác. Muốn tái sử dụng slot đã xóa, quản lý danh sách slot trống hoặc một cấu trúc chỉ mục với cơ chế đồng bộ. Chỉ đặt `status=DELETED` chưa khiến tệp nhỏ đi hay đảm bảo dữ liệu nhạy cảm cũ bị xóa khỏi thiết bị.

**Xóa vật lý bằng dồn record** sẽ làm thay đổi offset của các record phía sau, phá vỡ ánh xạ index → vị trí. Nếu yêu cầu offset ổn định, dùng tombstone hoặc tổ chức lại dữ liệu (*compaction*) có quản lý chỉ mục/tham chiếu và thay đổi version/generation phù hợp.

**Bản ghi mới có ID nghiệp vụ**: nếu cần tra cứu theo ID bất kỳ, xây chỉ mục từ ID tới index; kiểm tra trùng ID khi ghi. Không suy luận “ID 101 → slot 101” nếu đó không phải quy ước đã được chứng minh bởi schema.

## 7. Lựa chọn API và tính đúng đắn của truy cập ngẫu nhiên

| API | Đặc tính | Khi nào chọn |
| --- | --- | --- |
| `RandomAccessFile` | `seek(long)` thay đổi con trỏ file; có `readFully`, `readInt`, `writeLong` | Ví dụ đơn luồng, làm việc trực tiếp qua file pointer |
| `FileChannel` + `ByteBuffer` | `read/write(buffer, long position)` xử lý offset tuyệt đối, có `force` và `lock` | Định dạng nhị phân, đọc/ghi block, kiểm soát byte order |
| `SeekableByteChannel` | Có `position(long)`, đọc/ghi ở vị trí channel hiện tại | Cần abstraction chung cho những channel có thể seek |
| `MappedByteBuffer` qua `FileChannel.map` | Ánh xạ vùng tệp vào bộ nhớ | Bài toán thích hợp memory mapping, cần xử lý phạm vi map, đồng bộ và tài nguyên cẩn thận |

`RandomAccessFile.seek(offset)` đặt file pointer, nên code chia sẻ một instance và liên tục seek/read/write mà thiếu đồng bộ rất dễ đọc nhầm chỗ. Phương thức positional I/O của `FileChannel` tránh phụ thuộc vào file pointer chung, nhưng vẫn phải kiểm soát cạnh tranh khi hai writer sửa cùng byte/record, cũng như lúc file bị truncate hay close đồng thời.

**ByteBuffer có con trỏ riêng** `position`, `limit` và `remaining`. Không chia sẻ một `ByteBuffer` mutable giữa các luồng mà không có đồng bộ thích hợp. Cần xác định rõ byte order bằng `order(ByteOrder.BIG_ENDIAN)` cho từng buffer được dùng để ghi/đọc trường nhiều byte.

## 8. Những giới hạn cần thiết trong ứng dụng thực tế

### Ghi đúng record không đồng nghĩa với ghi nguyên tử

Một lần cập nhật 64 byte có thể tương ứng nhiều lần ghi/khối lưu trữ. Mất điện hoặc crash giữa chừng có thể khiến record chứa dữ liệu pha trộn giữa phiên bản cũ và mới, thậm chí header/tệp bị cắt. `FileChannel.force(true)` hỗ trợ yêu cầu đồng bộ dữ liệu nhưng **không bảo đảm transaction atomicity** cho một lần cập nhật gồm nhiều byte hay nhiều record.

Nếu cần khôi phục sau crash và tính nhất quán mạnh hơn, cân nhắc các kỹ thuật như: bản ghi có `checksum` và số thế hệ (*generation*); copy-on-write sang slot mới rồi cập nhật con trỏ/manifest an toàn; nhật ký ghi trước (*write-ahead log*); hoặc dùng database có transaction thay vì tự xây storage engine.

### Đồng bộ giữa thread/process

- Quy định ai được ghi cùng slot; dùng khóa ở tầng ứng dụng hoặc cơ chế đồng bộ phù hợp.
- `FileChannel.lock()`/`tryLock()` có thể phối hợp khóa tệp/vùng tệp, nhưng đặc tính khóa phụ thuộc nền tảng và provider. Không tự coi khóa hệ điều hành là giải pháp cho mọi trường hợp hoặc là bằng chứng đã có transaction.
- Khi đọc đồng thời writer, một record có thể bị nhìn thấy ở trạng thái trung gian. Nếu cần snapshot nhất quán, phải có giao thức đọc/ghi (ví dụ lock, version/counter và retry, hoặc copy-on-write).
- Đừng cho hai luồng vừa tính cùng `fileSize` rồi cùng append mà không cấp phát index nguyên tử.

### Kiểm tra định dạng từ tệp không tin cậy

Trước khi parse, xác minh ít nhất `magic`, `version`, `recordSize`, tổng độ dài file, index hợp lệ, status, độ dài UTF-8 và giá trị nghiệp vụ. Ví dụ chỉ kiểm tra một số trường quan trọng để tập trung vào thiết kế fixed record; ứng dụng thực tế nên xác thực `id`, `balanceCents`, bytes reserved và tính toàn vẹn.

Với nhu cầu bền vững lâu dài, đừng “đoán” schema từ kích thước file nếu header cho biết một version chưa được hỗ trợ. Hãy từ chối mở hoặc chạy quy trình migration có kiểm thử. Thay đổi kích thước record từ 64 sang 80 byte mà không thay version/migration làm toàn bộ offset cũ không còn chính xác.

### Dung lượng và phân mảnh

- Fixed-size record đơn giản cho truy cập theo slot, đổi lại có **internal fragmentation**: `nameArea` 40 byte vẫn được dành ra khi tên chỉ có 3 byte.
- Dùng record quá nhỏ sẽ hạn chế trường dữ liệu; record quá lớn gây lãng phí cho cập nhật nhỏ và cache.
- Với trường có thể dài bất kỳ (mô tả, ảnh, JSON), cân nhắc record có độ dài biến thiên cộng offset index, hoặc fixed-size metadata record trỏ đến vùng dữ liệu riêng; khi ấy cần cơ chế quản lý free space và tính nhất quán khác.
- Nếu tạo slot ở index rất lớn, một số file system có thể tạo *sparse file* với lỗ hổng đọc ra byte 0. File size lúc đó không chứng minh mọi slot trước index lớn đều từng được ghi.

## 9. Kiểm tra thiết kế trước khi triển khai

Một thiết kế có vị trí và kích thước xác định nên trả lời được các câu hỏi sau:

1. **Offset có xác định tuyệt đối?** Tên header size, record size, index base, kiểu số nguyên và phép kiểm tra tràn.
2. **Mỗi trường có ranh giới byte rõ ràng?** Tổng số byte từng trường chính xác bằng record size; byte order và signedness được tài liệu hóa.
3. **Chuỗi có quy định charset và giới hạn byte?** Encode trước rồi kiểm tra số byte, có length prefix hoặc quy tắc padding không mơ hồ.
4. **Đọc/ghi có xử lý partial I/O và EOF?** Không giả định một lời gọi channel xử lý hết buffer.
5. **Đọc lại sau khi đóng/mở tệp có đúng?** Có magic, version, kiểm tra file length và trạng thái record.
6. **Cập nhật/xóa có giữ offset các record còn lại?** Có tombstone, quy tắc tái sử dụng slot và ánh xạ ID → index.
7. **Crash/concurrency có được xem xét?** Nếu cần atomicity và durability mạnh, phải có giao thức vượt ngoài positional write cơ bản.

Các lỗi hay gặp là tính offset theo ký tự, quên header trong phép tính, dùng `int` cho phép nhân lớn, không `flip()` đúng cách, đặt `ByteBuffer.limit` chưa đủ record, không kiểm tra partial read/write, đọc chuỗi theo số ký tự thay vì UTF-8 bytes và nhầm chỉ số slot với ID nghiệp vụ.

## 10. Câu hỏi tự kiểm tra

1. Header 24 byte, mỗi record 96 byte, index bắt đầu từ 0. Record index 5 ở offset nào? **504** (=24 + 5 × 96); phạm vi byte là [504, 599].
2. Vì sao thay tên `"Lan"` bằng `"Nguyễn"` không được làm các record sau dịch chỗ? Vì cả hai tên nằm trong vùng `nameArea` cố định; phải tính độ dài UTF-8 và ghi padding đầy đủ.
3. Có thể dùng `fileSize / RECORD_SIZE` để đếm slot khi có header 16 byte không? **Không**; cần `(fileSize - HEADER_SIZE) / RECORD_SIZE` sau kiểm tra file size hợp lệ.
4. Xóa logic một slot có giảm tổng số slot không? **Không**; tombstone giữ nguyên slot vật lý, chỉ thay trạng thái.
5. `FileChannel.write(buffer, position)` có ghi đủ 64 byte chỉ với một lần gọi không? **Không được bảo đảm**; phải lặp cho đến khi buffer hết dữ liệu.
6. Đã gọi `force(true)` có đảm bảo mọi cập nhật 64 byte là nguyên tử khi mất điện không? **Không**; cần cơ chế kiểm tra/khôi phục và transaction nếu bài toán yêu cầu.

## Tài liệu API tham khảo

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): positional read/write, `force`, `lock` và memory mapping.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip` và đọc/ghi dữ liệu nhị phân.
- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): `seek`, `readFully` và quản lý con trỏ file.
- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `multiplyExact`, `addExact` giúp phát hiện overflow trong tính offset.
