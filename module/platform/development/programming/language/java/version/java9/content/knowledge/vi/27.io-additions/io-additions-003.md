# Chuyển dữ liệu sang OutputStream bằng InputStream.transferTo

## Mục tiêu

Sau bài học này, bạn có thể:

- Dùng \`InputStream.transferTo(OutputStream)\` để chuyển toàn bộ byte từ nguồn sang đích.
- Hiểu thời điểm method kết thúc, giá trị \`long\` trả về và vị trí của stream nguồn sau khi chuyển thành công.
- Quản lý vòng đời của input và output stream đúng cách.
- Nhận biết tình huống có thể block hoặc không bao giờ đạt EOF.
- Xử lý lỗi I/O và hiểu rằng đích có thể đã nhận một phần dữ liệu.
- Phân biệt chuyển byte trực tiếp với đọc toàn bộ vào bộ nhớ hoặc xử lý văn bản theo encoding.

## 1. transferTo là gì?

Java 9 bổ sung method \`transferTo(OutputStream out)\` vào \`java.io.InputStream\`. Method đọc byte từ input stream hiện tại và ghi chúng sang output stream được truyền vào, theo đúng thứ tự đọc:

~~~java
long transferred = input.transferTo(output);
~~~

Hợp đồng chính:

- Chuyển dữ liệu cho đến khi input stream báo hết dữ liệu (EOF).
- Trả về tổng số byte đã ghi sang output dưới kiểu \`long\`.
- Khi method trả về bình thường, input stream đã ở cuối luồng.
- Method không đóng input stream hoặc output stream.
- Nếu có lỗi I/O, một phần dữ liệu có thể đã được đọc hoặc ghi trước khi exception xuất hiện.

\`transferTo\` là thao tác chuyển byte. Nó không giải mã ký tự, không đổi charset, không thêm newline và không diễn giải nội dung file. Điều này phù hợp với file nhị phân, ảnh, archive, dữ liệu nén hoặc payload cần giữ nguyên từng byte.

Ví dụ tối giản:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {

    long bytes = in.transferTo(out);
    System.out.println("Transferred: " + bytes);
}
~~~

Hai stream được mở bởi đoạn code trên và được đóng khi thoát khỏi khối \`try\`. Việc đóng là trách nhiệm của code sở hữu resource; \`transferTo\` không tự thực hiện điều đó.

## 2. EOF quyết định thời điểm hoàn tất

\`transferTo\` không nhận tham số giới hạn số byte. Method tiếp tục đọc và ghi cho đến khi \`read\` trên input stream trả về \`-1\`, biểu thị EOF.

Điều này tạo ra một khác biệt quan trọng giữa nguồn hữu hạn và nguồn chưa kết thúc:

- Với file thông thường, EOF xuất hiện khi đọc hết file nên thao tác có thể hoàn tất.
- Với \`ByteArrayInputStream\`, EOF xuất hiện khi đã đọc hết mảng byte.
- Với socket hoặc pipe, EOF thường chỉ xuất hiện khi phía gửi đóng đầu ghi hoặc giao thức kết thúc luồng.
- Với nguồn liên tục hoặc vô hạn, EOF có thể không bao giờ xuất hiện; \`transferTo\` có thể tiếp tục block hoặc chạy mãi.

Nếu chỉ muốn chuyển một số byte nhất định, \`transferTo\` không phải API có giới hạn trực tiếp. Hãy dùng vòng lặp \`read\`/ \`write\` với bộ đếm hoặc một wrapper giới hạn số byte. Không gọi \`transferTo\` trên nguồn chưa có điều kiện kết thúc nếu ứng dụng đang chờ method trả về.

## 3. Giá trị trả về là số byte kiểu long

Chữ ký:

~~~java
public long transferTo(OutputStream out) throws IOException
~~~

Giá trị trả về là tổng số byte được ghi. Kiểu \`long\` cho phép đếm lượng dữ liệu lớn hơn giới hạn của \`int\`.

Không nhầm số byte với:

- Số ký tự trong văn bản.
- Số dòng.
- Số lần gọi \`read\` hoặc \`write\`.
- Kích thước buffer nội bộ của implementation.

Nếu input stream kết thúc ngay từ đầu, method trả về \`0\`. Nếu nguồn có 1.024 byte và toàn bộ được ghi thành công, kết quả trả về là \`1024\`.

Đối với dữ liệu văn bản UTF-8, số byte có thể khác số ký tự. Ví dụ, một ký tự Unicode có thể được mã hóa thành nhiều byte. \`transferTo\` chỉ đếm byte mà nó chuyển, không đếm ký tự sau giải mã.

## 4. Quản lý vòng đời của hai stream

\`transferTo\` không đóng stream nào. Sau khi chuyển thành công, cả input và output vẫn thuộc quyền quản lý của code đã tạo hoặc nhận chúng.

Dùng try-with-resources khi method hiện tại sở hữu cả hai resource:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {

    long count = in.transferTo(out);
    out.flush();
    System.out.println(count);
}
~~~

Một số lưu ý:

- \`flush()\` đẩy dữ liệu đang được buffer ở output stream xuống tầng bên dưới. Gọi rõ ràng nếu cần quan sát dữ liệu ở đích trước khi đóng stream.
- Khi thoát khỏi try-with-resources, \`close()\` được gọi cho cả hai resource.
- Nếu stream do caller truyền vào và caller vẫn cần dùng tiếp, không tự đóng nó chỉ vì đã gọi \`transferTo\`.
- Không giả định method tự flush output. Hãy flush hoặc close theo yêu cầu của ứng dụng.
- Nếu output là \`BufferedOutputStream\`, dữ liệu có thể còn trong buffer cho đến khi flush hoặc close.

Không đóng stream quá sớm. Ví dụ, nếu output stream là socket hoặc response body, đóng nó có thể kết thúc kết nối hoặc response mà caller còn cần sử dụng.

## 5. Ví dụ hoàn chỉnh: chuyển byte và kiểm tra trạng thái

Tạo file **TransferToDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Arrays;

public class TransferToDemo {

    private static final class TrackingInputStream
            extends ByteArrayInputStream {
        private boolean closed;

        TrackingInputStream(byte[] data) {
            super(data);
        }

        @Override
        public void close() {
            closed = true;
        }

        boolean isClosed() {
            return closed;
        }
    }

    private static final class TrackingOutputStream
            extends ByteArrayOutputStream {
        private boolean closed;
        private boolean flushed;

        @Override
        public void close() {
            closed = true;
        }

        @Override
        public void flush() throws IOException {
            flushed = true;
            super.flush();
        }

        boolean isClosed() {
            return closed;
        }

        boolean isFlushed() {
            return flushed;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] sourceBytes = {0, 1, 2, 127, (byte) 128, (byte) 255};

        TrackingInputStream input =
                new TrackingInputStream(sourceBytes);
        TrackingOutputStream output =
                new TrackingOutputStream();

        long count = input.transferTo(output);
        byte[] copiedBytes = output.toByteArray();

        System.out.println("transferred = " + count);
        System.out.println("bytes equal = "
                + Arrays.equals(sourceBytes, copiedBytes));
        System.out.println("copied = " + Arrays.toString(copiedBytes));
        System.out.println("input at EOF = " + (input.read() == -1));
        System.out.println("input closed = " + input.isClosed());
        System.out.println("output closed = " + output.isClosed());
        System.out.println("output flushed = " + output.isFlushed());

        long emptyCount =
                new ByteArrayInputStream(new byte[0])
                        .transferTo(new ByteArrayOutputStream());
        System.out.println("empty transferred = " + emptyCount);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out TransferToDemo.java
java -cp out TransferToDemo
~~~

Output chính xác:

~~~text
transferred = 6
bytes equal = true
copied = [0, 1, 2, 127, -128, -1]
input at EOF = true
input closed = false
output closed = false
output flushed = false
empty transferred = 0
~~~

Ví dụ dùng byte có giá trị 0 và các giá trị lớn hơn 127 để xác nhận dữ liệu được giữ nguyên ở mức byte. Khi chuyển xong, input ở EOF nhưng cả hai stream vẫn chưa bị đóng. Với implementation mặc định được dùng trong ví dụ này, output cũng chưa được flush; code cần flush hoặc close khi muốn đẩy dữ liệu buffered xuống đích.

## 6. Sao chép file bằng transferTo

Khi đã có hai stream, \`transferTo\` giúp nối luồng đọc và ghi mà không cần tự tạo vòng lặp buffer:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class FileTransfer {
    public static void main(String[] args) throws Exception {
        Path source = Paths.get("input.bin");
        Path target = Paths.get("output.bin");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(target)) {

            long bytes = in.transferTo(out);
            out.flush();
            System.out.println("Copied bytes: " + bytes);
        }
    }
}
~~~

Lệnh \`Files.newOutputStream(target)\` mặc định tạo file nếu chưa có và truncate file đích hiện có khi mở thành công. Vì vậy, hãy chắc chắn đường dẫn đích đúng và không trùng file nguồn. Nếu cần thay thế file an toàn hơn, có thể ghi ra file tạm rồi thực hiện move phù hợp sau khi chuyển thành công.

Ví dụ trên sở hữu cả hai stream nên đóng chúng bằng try-with-resources. Nếu chuyển thất bại giữa chừng, file đích có thể chứa một phần dữ liệu; ứng dụng cần quyết định có xóa file tạm hoặc xử lý lại hay không.

## 7. Xử lý lỗi I/O và dữ liệu được chuyển một phần

Method khai báo \`throws IOException\`. Lỗi có thể xảy ra khi đọc nguồn hoặc ghi đích:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {

    long count = in.transferTo(out);
    System.out.println("Transferred " + count + " bytes");
} catch (IOException ex) {
    System.err.println("Transfer failed: " + ex.getMessage());
    throw ex;
}
~~~

Không được giả định rằng exception đồng nghĩa với chưa có dữ liệu nào được ghi. Trước thời điểm lỗi:

- Input stream có thể đã đọc qua một số byte.
- Output stream có thể đã ghi một phần hoặc nhiều phần dữ liệu.
- File đích hoặc kết nối đích có thể ở trạng thái chưa hoàn chỉnh.
- Method không trả về số byte cuối cùng nếu bị thoát bằng exception.

Nếu cần khả năng retry đáng tin cậy, hãy thiết kế giao thức riêng: ghi vào file tạm, xác minh kích thước hoặc checksum, sau đó mới công bố file hoàn chỉnh. Với network stream, cần biết giao thức có hỗ trợ resume và cách xác định offset hay không.

Đóng resource trong \`finally\` hoặc try-with-resources để giải phóng file descriptor, socket và các tài nguyên liên quan sau cả thành công lẫn thất bại.

## 8. transferTo, readAllBytes và vòng lặp read/write

| Cách làm | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| \`input.transferTo(output)\` | Muốn chuyển toàn bộ nguồn đến EOF | Không tự đóng stream; có thể block đến EOF |
| \`input.readAllBytes()\` rồi \`output.write(...)\` | Dữ liệu nhỏ, cần toàn bộ byte trong bộ nhớ | Tốn bộ nhớ theo kích thước dữ liệu |
| Vòng lặp \`read(buffer)\` / \`write(buffer)\` | Cần giới hạn byte, báo tiến độ, hủy hoặc xử lý từng chunk | Phải tự xử lý EOF, buffer và lỗi |

Ví dụ vòng lặp khi chỉ muốn chuyển tối đa một số byte:

~~~java
static long transferAtMost(
        InputStream in, OutputStream out, long limit)
        throws IOException {

    if (limit < 0) {
        throw new IllegalArgumentException("limit must be non-negative");
    }

    byte[] buffer = new byte[8192];
    long total = 0;

    while (total < limit) {
        int requested = (int) Math.min(buffer.length, limit - total);
        int read = in.read(buffer, 0, requested);

        if (read == -1) {
            break;
        }

        out.write(buffer, 0, read);
        total += read;
    }

    return total;
}
~~~

Đoạn code này dừng khi đạt giới hạn hoặc nguồn EOF. Nó không đóng hoặc flush stream; caller vẫn quản lý resource. Với stream tùy biến, cần tuân theo hợp đồng của \`read\` và xử lý các ngoại lệ I/O như bình thường.

## 9. Những giới hạn cần nhớ

- \`transferTo\` đọc đến EOF, không nhận tham số số byte tối đa.
- Nó có thể block nếu nguồn chờ dữ liệu hoặc không phát EOF.
- Nó không phải API xử lý ký tự; không thực hiện charset conversion.
- Nó không bảo đảm một chiến lược zero-copy hay một kích thước buffer cụ thể.
- Nó không tự đóng input hoặc output stream.
- Không giả định output đã được flush khi method trả về.
- Nếu lỗi xảy ra, dữ liệu có thể đã được chuyển một phần.
- Với nguồn rất lớn, nó tránh việc caller phải giữ toàn bộ dữ liệu trong một mảng bằng cách chuyển theo luồng; tuy nhiên implementation cụ thể vẫn có thể dùng buffer nội bộ.

## 10. Lỗi thường gặp

### Quên đóng stream

\`transferTo\` không đóng resource. Dùng try-with-resources nếu method sở hữu stream.

### Nghĩ rằng method chỉ chuyển một buffer

Method tiếp tục cho đến EOF. Nếu muốn chuyển một phần, dùng vòng lặp có giới hạn hoặc wrapper phù hợp.

### Gọi trên nguồn không bao giờ kết thúc

Nếu nguồn không phát EOF, lời gọi có thể không trả về. Cần timeout, giao thức kết thúc hoặc giới hạn byte ở tầng ứng dụng.

### Cho rằng dữ liệu đích đã được flush

Method không nên được dùng thay cho \`flush()\`. Với output được buffer, hãy flush hoặc close theo thời điểm cần thiết.

### Dùng readAllBytes cho file lớn

\`readAllBytes\` tạo một mảng chứa toàn bộ nội dung. Với dữ liệu lớn, chuyển trực tiếp qua stream thường phù hợp hơn.

### Coi transfer thất bại là đích vẫn nguyên vẹn

Exception có thể xuất hiện sau khi một phần dữ liệu đã được ghi. Dùng file tạm hoặc cơ chế resume nếu cần tính toàn vẹn.

### Dùng API byte cho văn bản cần đổi encoding

\`transferTo\` sao chép byte nguyên trạng. Nếu cần đọc ký tự, chuẩn hóa newline hoặc đổi charset, dùng Reader/Writer và chỉ định charset rõ ràng.

## 11. Checklist

- [ ] Đã xác định nguồn có EOF và thời điểm EOF xuất hiện.
- [ ] Đã hiểu \`transferTo\` chuyển đến EOF và trả về số byte kiểu \`long\`.
- [ ] Đã xác định code nào sở hữu input và output stream.
- [ ] Đã đóng resource bằng try-with-resources khi phù hợp.
- [ ] Đã flush output nếu cần đọc hoặc quan sát dữ liệu trước khi đóng.
- [ ] Đã tính đến trường hợp nguồn block hoặc không kết thúc.
- [ ] Đã tính đến dữ liệu đích có thể chỉ được ghi một phần khi có IOException.
- [ ] Đã chọn \`transferTo\`, \`readAllBytes\` hoặc vòng lặp buffer theo yêu cầu.
- [ ] Đã giữ nguyên byte khi xử lý dữ liệu nhị phân.
- [ ] Đã dùng Reader/Writer nếu cần xử lý ký tự và encoding.

