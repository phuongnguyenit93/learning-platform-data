# Kích thước bộ đệm và số lần gọi I/O trong Java

## 1. Mục tiêu học tập

Khi đọc/ghi tệp hoặc trao đổi dữ liệu qua luồng, cách gọi `read()` và `write()` ảnh hưởng đến số lần lớp Java phải yêu cầu lớp bên dưới cung cấp hoặc nhận dữ liệu. **Bộ đệm (buffer)** gom nhiều thao tác nhỏ thành các lần trao đổi theo khối, thường giảm chi phí gọi I/O và cải thiện thông lượng, nhưng không phải cứ tăng kích thước buffer thì chương trình sẽ luôn nhanh hơn.

Sau bài học, bạn có thể:

- Giải thích **buffer là gì**, luồng có đệm khác gì luồng không đệm, và quan hệ giữa kích thước buffer với số lần yêu cầu dữ liệu từ tầng dưới.
- Ước tính số lần đọc/ghi theo khối trong mô hình đơn giản và chỉ ra vì sao số **lần gọi phương thức Java** không đồng nghĩa chính xác với số **system call** hay thao tác đọc/ghi vật lý trên thiết bị.
- Chọn kích thước đệm ban đầu hợp lý cho `BufferedInputStream`, `BufferedOutputStream`, `BufferedReader`, `BufferedWriter`; hiểu khi nào tăng buffer hữu ích hoặc không.
- Nhận diện đánh đổi giữa **throughput, latency, memory, flush, EOF, thời gian chờ và hiệu quả khi có nhiều luồng**.
- Đo hiệu quả bằng ví dụ Java 17+ có đầu ra xác định, rồi biết cách thiết kế phép đo hiệu năng thực tế có kiểm soát.

Phạm vi bài là **bộ đệm và ghép luồng** trong Java Core I/O. Nội dung tập trung vào nguyên tắc ra quyết định và phương pháp kiểm chứng, không đưa ra “kích thước tối ưu” chung cho mọi thiết bị hay workload.

## 2. Buffer là gì và được đặt ở đâu?

**Buffer** là vùng nhớ tạm giữ dữ liệu giữa nơi sinh/nhận dữ liệu và nơi tiêu thụ/ghi dữ liệu. Khi ứng dụng xử lý từng byte hoặc từng ký tự, lớp có đệm có thể gom chúng thành một khối lớn trước khi chuyển xuống luồng bên dưới.

Ví dụ, chương trình đọc từng byte:

```text
Ứng dụng:        read() read() read() ... 1000 lần
                      |
BufferedInputStream (buffer 128 byte):
                 1 lần nạp tối đa 128 byte → phục vụ nhiều lần read()
                      |
InputStream bên dưới:
                 nhiều yêu cầu nhỏ có thể thành ít yêu cầu theo khối hơn
                      |
Hệ điều hành / filesystem / thiết bị
```

Chiều ghi:

```text
Ứng dụng:        write(1 byte) write(1 byte) ...
                      |
BufferedOutputStream (buffer 128 byte):
                 gom các byte vào bộ nhớ
                      |
                 ghi xuống luồng bên dưới theo khối
                      |
Hệ điều hành / filesystem / thiết bị
```

Buffer nằm ở nhiều tầng: lớp `Buffered*` trong Java, bộ đệm của `Reader`/`Writer`/encoder, page cache của hệ điều hành, bộ nhớ của thiết bị và đôi khi buffer mạng. Chúng có vai trò khác nhau. **Thêm một `BufferedInputStream` không bảo đảm thêm một thao tác đọc vật lý cho mỗi lần nạp buffer.**

### 2.1. Các lớp I/O thường gặp

| Lớp / API | Đơn vị | Vai trò |
| --- | --- | --- |
| `InputStream`, `OutputStream` | Byte | Giao diện đọc/ghi byte; việc có đệm phụ thuộc lớp triển khai |
| `BufferedInputStream` | Byte | Dự trữ một mảng byte; các `read()` nhỏ có thể được phục vụ từ mảng |
| `BufferedOutputStream` | Byte | Gom nhiều `write()` nhỏ; ghi khối xuống OutputStream bên dưới |
| `Reader`, `Writer` | `char` UTF-16 | Giao diện đọc/ghi ký tự, có thể liên quan mã hóa ký tự |
| `BufferedReader` | `char` | Gom đọc ký tự; có `readLine()` để đọc theo dòng |
| `BufferedWriter` | `char` | Gom ký tự trước khi ghi xuống writer được bọc |
| `Files.newBufferedReader` / `newBufferedWriter` | Ký tự | Tiện ích mở luồng văn bản có đệm, nên chỉ định charset |
| `FileChannel` và `ByteBuffer` | Byte | API channel/buffer cho nhu cầu theo vị trí hoặc tối ưu cụ thể |

**Lưu ý:** “Không dùng lớp `BufferedInputStream`” không có nghĩa mọi lần gọi `read()` chắc chắn gây system call; một số lớp đầu vào vốn đã có cache/buffer. Ngược lại, thêm nhiều lớp đệm chồng nhau không tự động tạo hiệu năng tốt hơn.

## 3. Kích thước bộ đệm ảnh hưởng số lần gọi I/O thế nào?

Giả sử tổng lượng dữ liệu là **N byte**, mỗi lần lớp dưới cung cấp/nhận thành công đúng **B byte**, không có lỗi hoặc trả về ngắn. Số lần chuyển dữ liệu theo khối tối thiểu theo mô hình này là:

\[
K = \left\lceil \frac{N}{B} \right\rceil
\]

Với N = 1.000 byte:

| Kích thước B | Số khối để chuyển 1.000 byte theo giả định đơn giản |
| ---: | ---: |
| 1 byte | 1.000 |
| 10 byte | 100 |
| 100 byte | 10 |
| 128 byte | 8 (7 khối 128 + 1 khối 104) |
| 256 byte | 4 |
| 1.024 byte | 1 |

Công thức trên là **ước lượng cho số lần truyền payload khi mỗi yêu cầu có thể xử lý tối đa B byte**, không phải cam kết của Java hay filesystem. Thực tế có thể khác vì:

- `read(byte[])` có thể trả về **ít hơn** số byte đã yêu cầu, ngay cả khi chưa EOF; cần xử lý đúng giá trị trả về.
- Vòng lặp đọc đến EOF thường cần **một lần đọc cuối** trả `-1` để xác nhận đã hết dữ liệu.
- `write(byte[], off, len)` của `OutputStream` tuân thủ hợp đồng API khác với `WritableByteChannel.write(ByteBuffer)`; trên channel có thể phải lặp vì ghi từng phần.
- Buffer không đầy có thể được đẩy ra khi gọi `flush()` hoặc `close()`; nhiều lần flush nhỏ có thể làm tăng số lần ghi xuống dưới.
- Người đọc có thể gọi `read(byte[])` với khối lớn hoặc có các lớp tối ưu/đường chuyển dữ liệu riêng, khiến kích thước lớp buffer không còn quyết định trực tiếp từng yêu cầu.
- Mã hóa ký tự, nén dữ liệu, độ lớn block filesystem và cache hệ điều hành làm quan hệ giữa ký tự, byte và thao tác thiết bị thêm phức tạp.

**Điểm quan trọng:** phép đếm ở tầng `Buffered*` thường là số lần gọi **luồng được bọc**. Muốn khẳng định số system calls thật sự phải đo ở tầng hệ điều hành bằng công cụ phù hợp; không thể suy một-một chỉ từ số lời gọi Java.

### 3.1. Mô hình chi phí và lợi ích giảm dần

Một mô hình định tính hữu ích:

\[
T_{\text{total}} \approx T_{\text{data}} + K \times T_{\text{call}} + T_{\text{copy}} + T_{\text{other}}
\]

Trong đó `T_data` là chi phí vận chuyển dữ liệu, `T_call` là chi phí cố định của mỗi lời gọi sang tầng dưới, `T_copy` là chi phí sao chép qua buffer và `T_other` gồm mã hóa, lock, scheduling, caching hoặc độ trễ thiết bị.

Tăng B có thể làm giảm K mạnh khi B ban đầu rất nhỏ. Nhưng khi K đã ít, tăng B thêm có thể mang lại lợi ích nhỏ hoặc khiến phần giữ bộ nhớ/copy phức tạp hơn. Đây chỉ là **mô hình phân tích**, không phải công thức dự đoán thời gian chính xác trên mọi máy.

## 4. Ví dụ Java 17+: đếm số lần gọi tầng dưới khi đọc và ghi

Ví dụ dùng các `InputStream`/`OutputStream` đo đếm trong bộ nhớ, không truy cập tệp thật. Nhờ đó, kết quả **tất định** và chỉ rõ sự khác biệt giữa “ứng dụng gọi phương thức bao nhiêu lần” với “buffer yêu cầu luồng bên dưới bao nhiêu lần”.

Lưu thành **`BufferCallCountDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Arrays;
import java.util.Objects;

public class BufferCallCountDemo {
    static final class CountingInput extends InputStream {
        private final byte[] data;
        private int position;
        int calls;

        CountingInput(byte[] data) {
            this.data = data;
        }

        @Override
        public int read() {
            calls++;
            return position < data.length ? data[position++] & 0xff : -1;
        }

        @Override
        public int read(byte[] destination, int offset, int length) {
            Objects.checkFromIndexSize(offset, length, destination.length);
            if (length == 0) {
                return 0;
            }
            calls++;
            if (position >= data.length) {
                return -1;
            }
            int count = Math.min(length, data.length - position);
            System.arraycopy(data, position, destination, offset, count);
            position += count;
            return count;
        }
    }

    static final class CountingOutput extends OutputStream {
        int calls;
        int bytes;

        @Override
        public void write(int value) {
            calls++;
            bytes++;
        }

        @Override
        public void write(byte[] source, int offset, int length) {
            Objects.checkFromIndexSize(offset, length, source.length);
            calls++;
            bytes += length;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] data = new byte[1000];
        Arrays.fill(data, (byte) 65);

        CountingInput rawInput = new CountingInput(data);
        int rawReadBytes = 0;
        while (rawInput.read() != -1) {
            rawReadBytes++;
        }

        CountingInput bufferedSource = new CountingInput(data);
        int bufferedReadBytes = 0;
        try (InputStream in = new BufferedInputStream(bufferedSource, 128)) {
            while (in.read() != -1) {
                bufferedReadBytes++;
            }
        }

        CountingOutput rawOutput = new CountingOutput();
        for (byte value : data) {
            rawOutput.write(value);
        }

        CountingOutput bufferedTarget = new CountingOutput();
        try (OutputStream out = new BufferedOutputStream(bufferedTarget, 128)) {
            for (byte value : data) {
                out.write(value);
            }
        }

        System.out.println("Read raw: " + rawInput.calls
                + " calls, " + rawReadBytes + " bytes");
        System.out.println("Read buffered: " + bufferedSource.calls
                + " calls, " + bufferedReadBytes + " bytes");
        System.out.println("Write raw: " + rawOutput.calls
                + " calls, " + rawOutput.bytes + " bytes");
        System.out.println("Write buffered: " + bufferedTarget.calls
                + " calls, " + bufferedTarget.bytes + " bytes");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 BufferCallCountDemo.java
java BufferCallCountDemo
```

`stdout`:

```text
Read raw: 1001 calls, 1000 bytes
Read buffered: 9 calls, 1000 bytes
Write raw: 1000 calls, 1000 bytes
Write buffered: 8 calls, 1000 bytes
```

**Giải thích kết quả:**

1. **Đọc không đệm:** `read()` được gọi 1.000 lần để nhận từng byte và **lần thứ 1.001** trả EOF (`-1`).
2. **Đọc với buffer 128:** `BufferedInputStream` phục vụ nhiều lệnh `read()` từ mảng byte. Với nguồn đo đếm trong ví dụ, luồng dưới nhận 8 yêu cầu lấy dữ liệu (7 × 128 + 104 byte) và 1 yêu cầu báo EOF, tổng **9**.
3. **Ghi không đệm:** gọi `write(int)` 1.000 lần trên `CountingOutput`, mỗi lần ghi một byte, nên có **1.000** lời gọi tới đích.
4. **Ghi với buffer 128:** các byte được gom thành 7 lần ghi 128 byte và một lần ghi 104 byte khi đóng luồng, tổng **8** lời gọi xuống `CountingOutput`.

**Các số trên đo lời gọi tới đối tượng `CountingInput`/`CountingOutput`, không phải số system calls thực tế.** Hai lớp đo đếm không mở file descriptor và không ghi ra thiết bị. Giá trị `8`/`9` là kết quả của cách tổ chức luồng trong ví dụ, không phải cam kết rằng mọi reader/writer hoặc filesystem sẽ luôn có những con số đó.

Ở lần ghi cuối, `try-with-resources` đóng `BufferedOutputStream` và đẩy phần byte còn trong bộ đệm xuống đích. Nếu chương trình thoát bất thường trước khi flush/close, phần dữ liệu chưa đẩy xuống có thể không xuất hiện ở luồng bên dưới.

## 5. Ảnh hưởng khác nhau giữa đọc và ghi

### 5.1. Đọc từng byte, đọc thành khối

Một vòng lặp:

```java
int value;
while ((value = in.read()) != -1) {
    // xử lý một byte
}
```

Nếu `in` là `FileInputStream`, rất nhiều lần đọc từng byte có thể gây chi phí lớn; nếu `in` là `BufferedInputStream`, phần lớn `read()` được phục vụ bằng buffer đã nạp. Nhưng chương trình vẫn có chi phí xử lý **mỗi byte một vòng lặp**.

Khi bài toán chỉ cần chuyển dữ liệu, đọc thành khối giúp giảm cả số lời gọi ở tầng ứng dụng:

```java
byte[] block = new byte[16 * 1024];
int count;
while ((count = in.read(block)) != -1) {
    if (count > 0) {
        out.write(block, 0, count);
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; `in` và `out` cần là các luồng mở hợp lệ. Luôn dùng `count` thực tế: lần đọc có thể ngắn hơn chiều dài `block`. Với luồng chuẩn ở chế độ blocking và `block.length > 0`, đọc thành công thường có số byte dương; đoạn trên vẫn xử lý an toàn trường hợp đọc bằng 0. Quản lý đóng hai luồng bằng `try-with-resources` tại nơi sở hữu tài nguyên.

Nếu luồng có sẵn cơ chế chuyển tối ưu, cân nhắc `InputStream.transferTo(OutputStream)` hoặc `Files.copy`. Không giả định viết lại thủ công luôn nhanh hơn API chuẩn.

### 5.2. Ghi nhỏ liên tục, nhu cầu flush và độ trễ

`BufferedOutputStream` gom `write` nhỏ cho đến khi buffer đầy hoặc được `flush()`/`close()`. Điều này thường cải thiện thông lượng khi ghi một lượng dữ liệu lớn.

Tuy nhiên, nếu chương trình cần bên nhận thấy một thông điệp **ngay lập tức**, giữ dữ liệu trong buffer có thể tăng latency. Với giao thức yêu cầu ranh giới thông điệp, flush ở **điểm hoàn thành thông điệp**, không flush sau mỗi byte một cách máy móc.

Ví dụ đối với console, socket hoặc output phân lớp: dữ liệu chưa được flush có thể chưa được chuyển tới tầng kế tiếp; nhưng `flush()` không bảo đảm bên nhận đã xử lý thông điệp hoặc dữ liệu đã bền vững trên đĩa.

### 5.3. Character buffer có kích thước tính bằng `char`

`BufferedReader` và `BufferedWriter` nhận kích thước buffer tính theo **đơn vị `char`**; con số đó không tương đương số byte UTF-8. Với ký tự đa byte, số byte tạo thành còn do charset và cấu trúc Unicode. Ví dụ:

```java
// Đoạn minh họa, không phải chương trình độc lập.
try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8);
     java.io.BufferedReader buffered =
             new java.io.BufferedReader(reader, 16 * 1024)) {
    int first = buffered.read();
}
```

Cách ghép này chỉ minh họa cú pháp; `Files.newBufferedReader` vốn trả một `BufferedReader` nên bọc thêm `BufferedReader` là **thừa** trong đa số ứng dụng. Khi cần cấu hình dung lượng bộ đệm ký tự rõ ràng, có thể tạo `InputStreamReader` từ `InputStream` rồi bọc `BufferedReader(reader, size)`; phải xác định rõ ai sở hữu và đóng các resource. Tương tự, `BufferedWriter(Writer, size)` đếm theo ký tự.

## 6. Chọn kích thước buffer như thế nào?

Không có một con số hiệu quả tối ưu cho mọi workload. Kích thước mặc định do các lớp Java quyết định có thể phù hợp cho rất nhiều ứng dụng; việc tăng lên 64 KiB hoặc 256 KiB cần lý do và số đo thực tế.

### 6.1. Một quy trình chọn lựa thực dụng

1. **Xác định loại dữ liệu:** byte hay ký tự, kích thước bản ghi/tệp, số lượng kết nối, yêu cầu độ trễ và cách sử dụng đầu ra.
2. **Chọn baseline:** trước tiên dùng `Files.copy`/`transferTo` hoặc lớp `Buffered*` với mặc định, đo workload đại diện.
3. **Nếu có nhiều thao tác rất nhỏ:** thử buffer rõ ràng, chẳng hạn 4 KiB, 8 KiB, 16 KiB, 64 KiB, 256 KiB; đó là các **mức để thử nghiệm**, không phải quy tắc bắt buộc.
4. **Đo nhiều chỉ số:** thời gian xử lý, throughput (MiB/s), latency (đặc biệt p95/p99), số lần gọi tầng dưới, CPU, GC, heap, bộ nhớ giữ bởi các luồng, tổng byte đọc/ghi và số lỗi.
5. **Đánh giá trong tải song song:** cùng buffer 256 KiB, 10 luồng có thể dùng 2,5 MiB cho một lớp buffer, còn 10.000 luồng có thể dùng khoảng 2,44 GiB *chỉ riêng mảng buffer*, nếu mỗi luồng thật sự giữ một buffer 256 KiB.
6. **Chọn mức nhỏ nhất đáp ứng mục tiêu:** nếu hiệu năng gần tương đương, buffer nhỏ hơn thường dễ quản lý bộ nhớ và độ trễ.

Ví dụ phép tính bộ nhớ thô:

\[
M_{\text{buffer}} \approx C \times B
\]

trong đó `C` là số luồng/phiên đồng thời có buffer riêng và `B` là số byte mỗi buffer; con số này **chưa tính object header, buffer khác, decoder/encoder, queue và bộ nhớ ứng dụng**. Với `BufferedReader`, dung lượng `char[]` thường cần nhiều hơn một byte cho một `char` nên phải tính theo đơn vị cấp phát thực tế.

### 6.2. Vì sao buffer càng lớn không phải lúc nào cũng tốt?

- **Lợi ích giảm dần:** từ 1 byte lên 8 KiB giảm mạnh số lời gọi, nhưng từ 64 KiB lên 1 MiB có thể ít khác biệt khi tầng dưới đã xử lý hiệu quả.
- **Tăng footprint:** buffer thường là riêng cho từng instance; số kết nối/tệp đồng thời lớn làm tổng bộ nhớ tăng.
- **Tác động latency:** dữ liệu chờ flush có thể làm bên nhận thấy thông điệp chậm; chính sách flush và ranh giới bản ghi quan trọng.
- **Chi phí sao chép:** lớp wrapper mới có thể thêm đường copy; với API truyền theo khối đã tối ưu, chèn thêm buffer chưa chắc giúp ích.
- **Chi phối bởi bottleneck khác:** mã hóa UTF-8, parse JSON/CSV, nén, tốc độ ổ đĩa, network, lock hoặc số thao tác metadata có thể quyết định throughput nhiều hơn buffer.
- **Tính chất môi trường:** ổ cứng/SSD, filesystem cache, máy ảo, mạng và cách lập lịch thread khác nhau có thể thay đổi kết quả.

Không tối ưu từ công thức đơn giản nếu bài toán đã chạm giới hạn băng thông/CPU hoặc latency phục vụ request là mục tiêu chính.

## 7. Ghép luồng: đệm đúng tầng

Trong Java, các lớp bọc luồng kết hợp khả năng: mở tệp byte → giải mã ký tự → đệm dòng; hoặc mở tệp byte → đệm byte → ghi.

### 7.1. Ví dụ ghép đúng chức năng

Với byte nhị phân:

```java
// Đoạn minh họa; inputPath và outputPath phải là Path hợp lệ.
try (java.io.InputStream input =
         new java.io.BufferedInputStream(
             java.nio.file.Files.newInputStream(inputPath), 16 * 1024);
     java.io.OutputStream output =
         new java.io.BufferedOutputStream(
             java.nio.file.Files.newOutputStream(outputPath), 16 * 1024)) {
    input.transferTo(output);
}
```

Các đối tượng `Buffered*` ở bên ngoài sở hữu luồng tệp bên trong; đóng chúng sẽ đóng luồng đã được bọc. Ở ví dụ này, buffer có thể hữu ích tùy cách `transferTo` thực hiện truyền và đặc tính nguồn/đích; nên đo trước khi quyết định cần cả hai.

Với văn bản:

```java
// Đoạn minh họa; source và target phải là Path hợp lệ.
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             source, java.nio.charset.StandardCharsets.UTF_8);
     java.io.BufferedWriter writer =
         java.nio.file.Files.newBufferedWriter(
             target, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

**Chú ý:** `readLine()` bỏ dấu xuống dòng gốc; `newLine()` thêm dấu xuống dòng phụ thuộc nền tảng. Đây là **biến đổi nội dung theo dòng**, không phải phép sao chép bảo toàn byte hoặc bảo toàn chính xác kiểu kết thúc dòng. Nếu yêu cầu giữ nguyên byte, không dùng quy trình trên.

### 7.2. Tránh buffer trùng lặp vô ích

`Files.newBufferedReader` đã trả một `BufferedReader`; `Files.newBufferedWriter` trả `BufferedWriter`. Bọc thêm một `BufferedReader` nữa chỉ vì nghĩ “hai lớp buffer sẽ nhanh gấp đôi” thường không có căn cứ. Tương tự, với API đã nhận/gửi buffer lớn, thêm `BufferedInputStream` có thể không giảm rõ các lời gọi thực tế.

Tuy nhiên, không có nguyên tắc “cấm ghép hai lớp”: một lớp có thể đệm ký tự, lớp khác đệm byte, lớp khác mã hóa hoặc nén; mỗi lớp có mục đích riêng. Quyết định dựa trên chức năng, cách flush và số đo thực tế.

## 8. Đo hiệu năng đúng cách

Ví dụ `BufferCallCountDemo` đo số lần gọi của các đối tượng Java và khẳng định cơ chế gom lời gọi; **nó không benchmark ổ đĩa**. Khi so sánh thật:

- Dùng cùng dữ liệu đầu vào và đầu ra hợp lệ; xác minh tổng byte và nội dung sau mỗi lần chạy.
- Tách thời gian mở/đóng tệp khỏi thời gian truyền nếu muốn đánh giá riêng throughput, đồng thời có phép đo end-to-end để phản ánh ứng dụng.
- Thử nhiều kích thước file: rất nhỏ (chi phí mở file nổi bật), trung bình, lớn hơn filesystem cache nếu môi trường cho phép.
- Chạy nhiều lượt; khởi động JVM, JIT, GC và cache ảnh hưởng lần chạy đầu. Báo phân bố hoặc median thay vì lấy một số lẻ.
- Giám sát throughput/latency, CPU, heap, GC, bộ nhớ đồng thời, thời gian chờ và số bytes thực. Nếu phân tích số system call, dùng công cụ quan sát của hệ điều hành; đừng suy từ `CountingInput`.
- Tránh để trình benchmark “thắng” nhờ tác vụ khác: ghi vào `ByteArrayOutputStream` và ghi ra SSD là hai workload khác hẳn; đọc từ page cache khác đọc thực từ thiết bị.
- Với vi mô Java, có thể dùng framework benchmark như JMH khi phù hợp; đo chức năng I/O end-to-end vẫn phải theo tải thực và cache thực tế.

**Câu hỏi cần trả lời khi đổi kích thước:** “Mục tiêu là giảm chi phí gọi phương thức, giảm system call, tăng MiB/s, hay giảm độ trễ để người dùng thấy kết quả?” Mỗi mục tiêu có phép đo và lựa chọn khác nhau.

## 9. Những lỗi thường gặp

1. **Đồng nhất lời gọi Java và system call:** `BufferedInputStream.read()` có thể chạy hoàn toàn trong Java khi đã có dữ liệu; luồng dưới/hệ điều hành còn có cơ chế cache riêng.
2. **Hiểu nhầm `read(byte[])` luôn lấp đầy buffer:** cần dùng số byte thực trả về; `-1` mới báo EOF.
3. **Bỏ qua lần đọc cuối xác nhận EOF:** số lần yêu cầu đọc của chương trình có thể nhiều hơn số khối payload một đơn vị hoặc hơn nữa.
4. **Flush sau mỗi byte hoặc từng ký tự:** loại bỏ phần lớn lợi ích gom ghi; chỉ flush theo yêu cầu quan sát dữ liệu và ranh giới giao thức.
5. **Không flush/close khi hoàn tất:** dữ liệu còn trong buffer có thể chưa tới sink; dùng `try-with-resources`.
6. **Tăng buffer đồng loạt cho mọi connection:** tổng footprint lớn, tăng áp lực heap/GC và có thể xấu đi khi tải cao.
7. **Lấy kích thước buffer ký tự làm số byte:** UTF-16 `char` và byte UTF-8 có kích thước khác.
8. **Thêm nhiều buffer giống nhau không có mục đích:** tăng phức tạp và copy mà chưa chắc giảm lời gọi hữu ích.
9. **Tin một phép đo trên file nhỏ:** lần chạy đầu, cache, xử lý file metadata hoặc scheduling có thể che hiệu ứng buffer.
10. **Không xử lý lỗi I/O:** ghi dở và reader/writer thất bại có thể làm chương trình công bố dữ liệu sai. Buffer chỉ tối ưu trao đổi dữ liệu, không cung cấp transaction hoặc rollback.
11. **Coi kích thước buffer là giới hạn kích thước input:** buffer 8 KiB vẫn có thể dùng để đọc tệp 100 GiB; ứng dụng cần quota/timeouts độc lập.
12. **Không xét độ trễ:** throughput tăng nhưng thông điệp bị giữ trong buffer quá lâu có thể không phù hợp với ứng dụng tương tác.

## 10. Bài tập tự kiểm tra

1. Với N = 10.000 byte, buffer B = 1.000 byte và giả định mỗi lần truyền đủ B byte, tính số khối payload. Vì sao vòng đọc đến EOF có thể cần thêm một lần gọi `read`?
2. Từ `BufferCallCountDemo`, thử B = 250 byte (giữ input 1.000 byte). Dự đoán số lần ghi xuống `CountingOutput` khi close, và số lần đọc xuống `CountingInput` bao gồm kiểm tra EOF.
3. Thêm `flush()` sau mỗi `out.write(value)`. Giải thích vì sao số lần gọi xuống tầng dưới sẽ tăng rất mạnh.
4. So sánh hai trường hợp: một tệp văn bản UTF-8 1 GiB được chuyển sang tệp khác bằng buffered reader/writer và cùng tệp đó được gom vào `StringWriter`. Đường nào có nguy cơ dùng heap tỷ lệ với kích thước file?
5. Thiết kế thử nghiệm nhiều kích thước buffer 4/16/64/256 KiB cho tệp lớn. Bạn sẽ kiểm tra tính đúng của output và đo thông số nào?
6. Trong ứng dụng có 20.000 kết nối đồng thời, vì sao buffer riêng 256 KiB/kết nối là quyết định tốn bộ nhớ? Tính phần buffer thô bằng phép nhân và cho biết còn thiếu những thành phần gì.
7. Giải thích khi nào nên flush ở ranh giới thông điệp và vì sao flush không chứng minh thiết bị đã lưu bền vững.
8. Phân biệt buffer `byte[]` với buffer `char[]` trong việc đo dung lượng và charset.

**Ghi nhớ:** Buffer làm thay đổi cách **gom các yêu cầu đọc/ghi** tới tầng dưới. Kích thước buffer lớn hơn thường giảm số lần chuyển khối trong mô hình đơn giản, nhưng lợi ích thực chịu ảnh hưởng của EOF, cách đọc/ghi, layering, cache, số lượng phiên đồng thời, chính sách flush và loại thiết bị. Hãy chọn dựa trên **tính đúng, mục tiêu hiệu năng và kết quả đo**, thay vì mặc định “càng lớn càng nhanh”.