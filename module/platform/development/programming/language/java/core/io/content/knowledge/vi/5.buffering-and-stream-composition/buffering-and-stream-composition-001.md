# Mục đích của BufferedInputStream và BufferedOutputStream trong Java I/O

Khi làm việc với file, socket hoặc nguồn dữ liệu khác, thao tác đọc/ghi **mỗi lần một byte** thường khiến chương trình gọi xuống nguồn hoặc đích quá nhiều lần. **BufferedInputStream** và **BufferedOutputStream** là hai lớp bọc luồng byte thuộc gói **java.io**, sử dụng một vùng nhớ đệm để **gom nhiều thao tác nhỏ thành những lần đọc/ghi theo khối**. Mục tiêu chính là giảm overhead của lời gọi đến luồng bên dưới; cả hai vẫn xử lý **byte**, không tự chuyển đổi charset hay thay đổi nội dung nhị phân.

## 1. BufferedInputStream và BufferedOutputStream giải quyết vấn đề gì?

Giả sử muốn đọc 100.000 byte của một file, xử lý từng byte rồi ghi ra file khác. Nếu gọi **FileInputStream.read()** và **FileOutputStream.write(int)** riêng lẻ cho mỗi byte, chương trình có thể phải thực hiện rất nhiều thao tác xuống các luồng nền, tùy cách các lớp đó được triển khai. Chi phí kiểm tra trạng thái, chuyển qua các tầng Java/native và giao tiếp thiết bị hoặc hệ điều hành có thể lớn hơn công việc xử lý một byte.

Một **buffer** là mảng byte trong bộ nhớ JVM. Thay vì xuống nguồn 100.000 lần để đáp ứng 100.000 lần **read()**, một **BufferedInputStream** có thể lấy một khối lớn và phục vụ nhiều lần đọc nhỏ từ khối trong RAM. Chiều ghi tương tự: **BufferedOutputStream** tích lũy các byte được ghi rồi gửi từng khối xuống luồng bên dưới.

| Lớp | Bao bọc loại luồng | Mục đích chính | Cách hoạt động |
| --- | --- | --- | --- |
| **BufferedInputStream** | **InputStream** | Giảm số lần đọc nhỏ từ nguồn | Nạp byte theo khối vào buffer, trả dần cho các lần đọc tiếp theo |
| **BufferedOutputStream** | **OutputStream** | Giảm số lần ghi nhỏ xuống đích | Giữ byte trong buffer rồi đẩy xuống luồng nền khi đầy hoặc khi flush/close |
| **BufferedReader** | **Reader** | Đệm dữ liệu ký tự, hỗ trợ đọc dòng | Làm việc với **char**, không thay thế luồng byte cho dữ liệu nhị phân |
| **BufferedWriter** | **Writer** | Đệm các lần ghi ký tự | Làm việc với văn bản, không dùng để sao chép byte tùy ý |

**Buffering không làm cho CPU, ổ đĩa hay mạng tự nhanh hơn**. Nó giúp giảm số lời gọi nhỏ và overhead, khi cấu hình và kiểu truy cập phù hợp. Với những API đã truyền dữ liệu theo khối lớn, việc bọc thêm buffer có thể mang lại ít lợi ích.

## 2. Cơ chế của BufferedInputStream

### 2.1. Vùng đệm đọc hoạt động như thế nào?

Ví dụ ta bọc một InputStream bằng buffer có dung lượng 4 byte:

~~~text
Nguồn dữ liệu: A B C D E F G H I J
                │
                │ nạp một khối khi cần
                ▼
       [ A | B | C | D ]    buffer bên trong
         ▲
         └── read() trả 'A'; lần gọi kế tiếp đọc 'B' từ RAM

Khi hết A..D, buffer được nạp khối E..H, rồi I..J.
~~~

Đây là **mô hình khái niệm** của những lần **read()** nhỏ: buffer giúp tái sử dụng dữ liệu đã đọc. Thực tế Java còn có tối ưu hóa: khi người gọi yêu cầu **một khối rất lớn** bằng **read(byte[], off, len)**, BufferedInputStream có thể đọc trực tiếp vào mảng đích, bỏ qua việc sao chép không cần thiết qua buffer, tùy trạng thái mark và triển khai JDK.

Khi tạo luồng:

~~~java
InputStream buffered = new BufferedInputStream(originalStream);
~~~

hoặc chỉ định kích thước buffer:

~~~java
InputStream buffered = new BufferedInputStream(originalStream, 16 * 1024);
~~~

**originalStream** là một **InputStream đã được tạo trước**, ví dụ từ **Files.newInputStream(path)**. Hai đoạn trên là *mảnh code minh họa*, không phải chương trình chạy độc lập. Constructor nhận **size** dương; kích thước bằng 0 hoặc âm sẽ gây **IllegalArgumentException**. Nếu không truyền size, JDK dùng dung lượng mặc định do triển khai quyết định; đừng dựa vào con số mặc định để làm giao thức.

Khi các byte đang nằm trong buffer, lần **read()** kế tiếp thường lấy dữ liệu trực tiếp từ RAM. Khi buffer hết và luồng nguồn còn mở, lần đọc tiếp theo phải nạp thêm dữ liệu nên **vẫn có thể chặn**, hoặc ném **IOException**. Buffering **không bỏ được timeout, EOF hay lỗi đọc từ nguồn**.

### 2.2. Đọc từng byte và đọc theo khối

Với **BufferedInputStream.read()**, mỗi lời gọi trả một số nguyên từ **0 đến 255** hoặc **-1** khi EOF. Byte **0x00** là dữ liệu bình thường; đừng coi nó là EOF. Với **read(byte[])**, số byte thực nhận có thể nhỏ hơn dung lượng mảng, kể cả khi chưa EOF. Số byte hợp lệ luôn là **count** được trả về.

Ví dụ:

~~~java
byte[] chunk = new byte[8192];
int count;
while ((count = buffered.read(chunk)) != -1) {
    // Chỉ xử lý chunk[0] đến chunk[count - 1].
}
~~~

Mảnh này giả định đã có **buffered** kiểu **InputStream**. Trường hợp đọc khối lớn, bản thân **read(byte[])** đã giảm số lần gọi so với đọc từng byte; vì thế **lợi ích của lớp BufferedInputStream bổ sung có thể nhỏ hoặc không đáng kể**. Cần đo bằng workload thật thay vì luôn bọc nhiều tầng buffer.

### 2.3. mark() và reset(): tiện ích đáng chú ý

**BufferedInputStream** hỗ trợ **mark() / reset()** ngay cả khi nguồn nền không tự hỗ trợ đánh dấu. Điều này hữu ích khi parser cần xem trước vài byte để xác định định dạng, sau đó quay về vị trí đã đánh dấu.

- Gọi **mark(readlimit)** để đánh dấu vị trí hiện tại và khai báo số byte có thể đọc trước khi mark không còn hợp lệ.
- Gọi **reset()** để trở về vị trí đánh dấu nếu mark vẫn hợp lệ.
- **markSupported()** trả về **true** với BufferedInputStream.
- Nếu đọc quá giới hạn làm mark mất hiệu lực, **reset()** có thể ném **IOException**.
- Giữ mark với readlimit lớn có thể làm buffer phải mở rộng, dẫn đến tăng dùng RAM; đây không phải cơ chế tua ngược cả file tùy ý.

Đây là một lợi ích chức năng ngoài chuyện giảm số lần đọc, nhưng vẫn cần quản lý readlimit và tuổi thọ của luồng.

## 3. Cơ chế của BufferedOutputStream

### 3.1. Gom các lần ghi nhỏ thành lần ghi lớn

Ví dụ đặt buffer 4 byte, rồi gọi **write(int)** từng byte:

~~~text
write('A')  → [ A |   |   |   ]
write('B')  → [ A | B |   |   ]
write('C')  → [ A | B | C |   ]
write('D')  → [ A | B | C | D ]
write('E')  → đẩy A B C D xuống OutputStream nền,
              giữ E trong buffer cho lần tiếp theo.
~~~

Sơ đồ thể hiện nguyên tắc gom byte; thời điểm chi tiết có thể thay đổi theo cách ghi và triển khai. Với mảng lớn có độ dài **>= kích thước buffer**, BufferedOutputStream có thể đẩy phần đang đệm rồi ghi mảng đó **thẳng xuống luồng nền**, tránh một lần sao chép thừa.

Tạo wrapper:

~~~java
OutputStream buffered = new BufferedOutputStream(originalStream, 16 * 1024);
~~~

**originalStream** là OutputStream đã tạo, chẳng hạn **Files.newOutputStream(path)**. Đối với thao tác ghi, điều thiết yếu là **write(...) thành công trên wrapper không nhất thiết có nghĩa byte đã được gửi xuống đích ngay lúc đó**. Một phần hoặc toàn bộ dữ liệu vẫn có thể nằm trong buffer.

### 3.2. Khi nào dữ liệu trong buffer được đẩy ra?

Trong quá trình sử dụng bình thường, buffered output gửi byte xuống luồng bên dưới khi:

1. Buffer đã đầy và chương trình muốn ghi thêm byte.
2. Chương trình chủ động gọi **flush()**.
3. Chương trình gọi **close()** hoặc kết thúc khối **try-with-resources**: dữ liệu đang đệm được flush trong quá trình đóng (trừ khi xảy ra lỗi I/O).

Dùng **flush()** ở ranh giới dữ liệu cần được chuyển ngay, chẳng hạn sau một bản tin ứng dụng hoặc sau khi xuất một phản hồi cần truyền đi khi kết nối còn mở:

~~~java
buffered.write(message);
buffered.flush();
~~~

Đây là mảnh code minh họa, giả định **buffered** kiểu OutputStream và **message** là byte[]. **flush()** yêu cầu đẩy byte từ các bộ đệm của tầng này (và theo hợp đồng của các luồng lồng nhau, việc flush có thể tiếp tục đến tầng bên dưới). Nó **không bảo đảm byte đã được ghi bền vững xuống ổ đĩa vật lý**, không thay cho đồng bộ dữ liệu kiểu **FileChannel.force(...) / FileDescriptor.sync()**, và **không bảo đảm đầu bên kia mạng đã nhận/xử lý bản tin**.

**Không flush sau mỗi byte** nếu mục tiêu là tăng tốc ghi. Làm vậy làm mất phần lớn tác dụng gom các thao tác nhỏ. Nếu thao tác ngắn và có sở hữu wrapper, thường có thể để **close()** trong try-with-resources hoàn tất flush thay vì gọi flush thủ công vô ích ngay trước close.

## 4. Ví dụ Java 17+ có thể chạy: quan sát buffer, flush, mark/reset và bảo toàn byte

Lưu mã sau thành **BufferedStreamsDemo.java**. Ví dụ chỉ dùng bộ nhớ để kết quả lặp lại ổn định, không cần tạo file hay phụ thuộc tốc độ đĩa.

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class BufferedStreamsDemo {
    public static void main(String[] args) throws IOException {
        // 1. Buffer đọc và chức năng mark/reset.
        byte[] letters = "ABCDE".getBytes(StandardCharsets.US_ASCII);
        try (BufferedInputStream in = new BufferedInputStream(
                new ByteArrayInputStream(letters), 3)) {
            System.out.println("first=" + (char) in.read());
            in.mark(3);
            byte[] next = in.readNBytes(2);
            System.out.println("next=" +
                    new String(next, StandardCharsets.US_ASCII));
            in.reset();
            System.out.println("after reset=" + (char) in.read());
        }

        // 2. Buffer ghi giữ byte tạm thời trước flush.
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (BufferedOutputStream out =
                     new BufferedOutputStream(sink, 8)) {
            out.write(new byte[] {65, 66, 67}); // A B C
            System.out.println("before flush=" + sink.size());
            out.flush();
            System.out.println("after flush=" + sink.size());
            out.write('D'); // Byte D còn trong buffer cho đến close.
        }
        System.out.println("after close=" + sink.size());
        System.out.println("text=" +
                new String(sink.toByteArray(), StandardCharsets.US_ASCII));

        // 3. Sao chép dữ liệu nhị phân có byte 00 và FF.
        byte[] binary = {0x00, (byte) 0xFF, 0x0A, 0x41};
        ByteArrayOutputStream copyTarget = new ByteArrayOutputStream();
        try (InputStream in = new BufferedInputStream(
                     new ByteArrayInputStream(binary), 2);
             OutputStream out =
                     new BufferedOutputStream(copyTarget, 2)) {
            byte[] chunk = new byte[3];
            int count;
            while ((count = in.read(chunk)) != -1) {
                out.write(chunk, 0, count);
            }
        }
        byte[] copied = copyTarget.toByteArray();
        System.out.println("binary equal=" +
                Arrays.equals(binary, copied));
        System.out.println("binary hex=" +
                HexFormat.of().formatHex(copied));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac BufferedStreamsDemo.java
java BufferedStreamsDemo
~~~

Kết quả:

~~~text
first=A
next=BC
after reset=B
before flush=0
after flush=3
after close=4
text=ABCD
binary equal=true
binary hex=00ff0a41
~~~

Diễn giải:

- **mark(3)** đặt dấu trước B; đọc BC rồi **reset()** quay lại B, nên dòng **after reset=B**.
- Với output buffer dung lượng 8, ba byte **ABC** chưa đủ để kích hoạt ghi xuống **sink**, vì thế **before flush=0**.
- **flush()** làm sink có 3 byte; thêm D rồi kết thúc try-with-resources sẽ **close()**, dẫn đến flush và sink có 4 byte.
- Đối với byte nhị phân **00 FF 0A 41**, đầu ra khớp chính xác (**Arrays.equals** là true). Buffered streams **không tự giải mã UTF-8 hoặc đổi dữ liệu nhị phân**.

Những con số về kích thước sink trong ví dụ dựa vào việc ghi một mảng 3 byte với buffer dung lượng 8 và được kiểm soát rõ ràng. Trong hệ thống file/mạng thật, thời điểm thiết bị hoặc phía nhận thực sự xử lý dữ liệu còn phụ thuộc những tầng bên dưới.

## 5. Ví dụ thực tế: copy file bằng buffered streams

Muốn sao chép file tùy ý mà không biến byte thành ký tự, có thể kết hợp buffer ở cả hai chiều và vòng lặp đọc/ghi theo khối. Lưu chương trình thành **BufferedFileCopy.java**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedFileCopy {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("input.bin");
        Path target = Path.of("output.bin");

        try (InputStream in = new BufferedInputStream(
                     Files.newInputStream(source), 16 * 1024);
             OutputStream out = new BufferedOutputStream(
                     Files.newOutputStream(target), 16 * 1024)) {
            byte[] chunk = new byte[8192];
            int count;
            while ((count = in.read(chunk)) != -1) {
                out.write(chunk, 0, count);
            }
        }

        System.out.println("identical=" +
                (Files.mismatch(source, target) == -1L));
    }
}
~~~

Lệnh biên dịch/chạy sau khi tạo file **input.bin** trong thư mục hiện tại:

~~~bash
javac BufferedFileCopy.java
java BufferedFileCopy
~~~

Nếu không có lỗi, file nguồn không thay đổi trong lúc sao chép và không có tác nhân khác đồng thời sửa đích, output là:

~~~text
identical=true
~~~

Lưu ý:

- **Files.newInputStream** mở nguồn và **Files.newOutputStream** mở đích. Theo mặc định với Files.newOutputStream(path) không có option, file đích sẽ được tạo nếu chưa có hoặc **bị cắt về rỗng nếu đã tồn tại**; phải chủ động chọn chính sách xử lý file đích để tránh mất dữ liệu.
- **out.write(chunk, 0, count)** là bắt buộc: chỉ **count** byte là vừa nhận, nhất là ở lần đọc cuối. Viết cả buffer có thể khiến byte cũ bị chèn vào file đích.
- Try-with-resources **đóng wrapper**, kéo theo đóng luồng nền. Khi OutputStream được đóng, dữ liệu đang đệm được flush; nếu quá trình này ném IOException, bản sao có thể dở dang.
- **Files.mismatch** (Java 12+) so sánh từng byte; **-1** nghĩa là không tìm thấy byte khác nhau trong hai file được đối chiếu. Chỉ so kích thước file không đủ chứng minh dữ liệu giống nhau.
- Nếu cần đơn giản hơn và không có yêu cầu xử lý từng khối, **Files.copy(source, target)** thường là cách sao chép file trực tiếp. Dùng buffered wrappers khi chương trình **thực sự cần làm việc với luồng**.

### Đọc/ghi từng khối có sẵn buffer còn cần BufferedInputStream/OutputStream?

Không phải lúc nào cũng cần. Với vòng lặp đọc mảng **8192 byte** và ghi mảng theo khối, code đã giảm số lời gọi so với **read() / write(int)** đơn lẻ. Các lớp nền còn có thể tự tối ưu, ví dụ tầng hệ điều hành có page cache hoặc thư viện có bộ đệm riêng. Bọc thêm **BufferedInputStream/BufferedOutputStream** đôi khi tăng thêm sao chép bộ nhớ mà không tăng đáng kể throughput; đôi khi lại có ích nếu các lớp giao tiếp với nguồn đọc chậm hoặc chương trình xen kẽ nhiều thao tác nhỏ. **Đo thực tế** với kích thước khối, loại thiết bị và kiểu truy cập của ứng dụng.

## 6. Ghép luồng (stream composition): thêm chức năng bằng cách bọc lớp

Cả hai lớp đều thuộc mô hình **decorator**: một luồng bọc luồng khác, giữ nguyên giao diện InputStream/OutputStream nhưng thêm buffering. Ta có thể xếp nhiều lớp để kết hợp chức năng.

Ví dụ đọc các kiểu nguyên thủy từ file theo giao thức của **DataInputStream**:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int version = in.readInt();
    // ...
}
~~~

Ví dụ ghi dữ liệu có kiểu bằng **DataOutputStream**:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeUTF("Java");
}
~~~

Hai đoạn trên là **mảnh mã minh họa**, giả định đã import **java.io.*** và **java.nio.file.***, cũng như khai báo **path** kiểu **Path**. **DataInputStream/DataOutputStream** đọc/ghi cấu trúc giá trị nguyên thủy, trong khi lớp Buffered làm nhiệm vụ gom byte; mỗi lớp giữ trách nhiệm riêng.

Một số quy tắc ghép luồng:

1. **Gọi nghiệp vụ ở wrapper ngoài cùng.** Đối với DataOutputStream ở ví dụ, gọi **writeInt** trên DataOutputStream thay vì bỏ qua nó để ghi trực tiếp vào OutputStream nền.
2. **Đóng wrapper ngoài cùng nếu bạn sở hữu toàn bộ chuỗi.** Đóng các decorator thường chuyển tiếp đến luồng nền; đừng tiếp tục sử dụng luồng đã bị đóng.
3. **Tránh đóng các luồng chia sẻ không thuộc sở hữu.** Chẳng hạn wrapper quanh **System.out** thường không nên bị đóng tùy tiện vì nó sẽ đóng standard output của ứng dụng; chỉ flush ở thời điểm phù hợp.
4. **Không xếp buffer lặp lại chỉ vì nghĩ càng nhiều càng nhanh.** BufferedInputStream bọc BufferedInputStream hoặc BufferedOutputStream bọc BufferedOutputStream thường tăng độ phức tạp và có thể tăng copy mà không rõ lợi ích.
5. **Chú ý thứ tự khi có nén/mã hóa.** Đặt buffer ở phía dữ liệu thô hay dữ liệu sau xử lý có thể thay đổi nơi gom khối. Các lớp như GZIPInputStream/GZIPOutputStream thường có cơ chế xử lý block và buffering của riêng chúng; hãy hiểu chuỗi wrapper và benchmark thay vì giả định một thứ tự tối ưu chung.

## 7. Chọn kích thước buffer

Constructor dạng **(stream, size)** cho phép tự chọn kích thước mảng byte nội bộ. Ví dụ **8 KiB (8192 byte)** hoặc **16 KiB (16384 byte)** thường là các giá trị thử nghiệm hợp lý, không phải con số tối ưu cho mọi trường hợp.

**Quá nhỏ:** buffer phải nạp/xả nhiều lần, dẫn đến nhiều lời gọi nền hơn. **Quá lớn:** mỗi luồng giữ nhiều RAM, có thể lãng phí khi đồng thời mở hàng nghìn kết nối hoặc file; lợi ích giảm dần. Ví dụ 10.000 stream, mỗi stream có một buffer 64 KiB, phần dung lượng buffer theo phép nhân lý thuyết lên tới khoảng **625 MiB** chỉ cho một chiều (64 × 10.000 KiB = 640.000 KiB ≈ 625 MiB), chưa kể overhead và các buffer khác.

Nếu dùng 2 chiều input/output cho cùng kết nối, có thể có **hai buffer riêng**. Tài nguyên RAM cần xem theo tổng số wrapper đồng thời sống. Khi benchmark, đo throughput và latency trong workload thật: số lượng lời gọi nhỏ, kích thước mỗi lần, tốc độ đĩa/mạng, nhu cầu flush, độ dài luồng và số kết nối đồng thời.

Các lựa chọn không nên dựa vào **InputStream.available()** để suy ra tổng độ lớn file/stream; nó chỉ ước tính byte đọc ngay không chặn, không phải kích thước cuối cùng hay cơ sở duy nhất để cấp phát.

## 8. Mối quan hệ giữa flush, close, timeout và độ bền dữ liệu

| Hành động | BufferedInputStream | BufferedOutputStream |
| --- | --- | --- |
| **read()** | Trả dữ liệu đang đệm hoặc nạp thêm từ nguồn | Không áp dụng |
| **write()** | Không áp dụng | Ghi vào buffer hoặc đẩy byte đến đích khi thích hợp |
| **flush()** | Không cung cấp (InputStream không có flush) | Đẩy dữ liệu đang đệm xuống OutputStream bên dưới |
| **close()** | Đóng wrapper và luồng nền, giải phóng bộ đệm | Flush dữ liệu còn đệm rồi đóng wrapper/luồng nền; lỗi I/O vẫn có thể xảy ra |
| **mark/reset** | Có hỗ trợ với giới hạn readlimit | Không áp dụng |

**flush() không đồng nghĩa với “đã lưu an toàn trên đĩa”**. Với output file, hệ điều hành có thể còn cache; với socket, việc byte đi khỏi buffer Java cũng chưa có nghĩa phía bên kia xử lý. Muốn yêu cầu độ bền đĩa, cần API đồng bộ phù hợp và hiểu hợp đồng hệ thống file; muốn xác nhận dữ liệu mạng, cần giao thức báo nhận ở tầng ứng dụng khi cần.

**Buffer không thay thế timeout**. Đọc mạng có thể vẫn chặn khi chờ byte mới. Chương trình cần thiết lập timeout tại lớp socket/network thích hợp và xử lý ngắt kết nối. Bản thân BufferedInputStream không tự đặt giới hạn thời gian cho read(), và BufferedOutputStream không làm đích bị chậm trở thành đích không chặn.

**Một write không có nghĩa toàn bộ dữ liệu được giao thành công** nếu sau đó close/flush ném lỗi. Khi dữ liệu quan trọng, kiểm tra lỗi I/O, tính toàn vẹn và trạng thái file/luồng đích.

## 9. Lỗi thường gặp

1. **Nhầm buffered streams với character streams.** BufferedInputStream/OutputStream giữ byte, trong khi BufferedReader/Writer làm việc với ký tự. Dữ liệu nhị phân nên dùng luồng byte.
2. **Quên flush khi kết nối còn mở nhưng cần gửi dữ liệu ngay.** Byte có thể vẫn nằm trong BufferedOutputStream; gọi **flush()** tại ranh giới bản tin cần phát.
3. **Flush sau từng byte.** Làm mất hiệu quả gom nhiều thao tác nhỏ. Gom theo bản tin/khối và flush khi cần.
4. **Quên đóng wrapper khi sở hữu tài nguyên.** Byte cuối có thể chưa được flush và descriptor không được giải phóng. Sử dụng **try-with-resources**.
5. **Nghĩ close() của wrapper chỉ đóng wrapper.** Thông thường nó đóng luôn luồng bên trong; tránh đóng những stream chia sẻ còn cần dùng.
6. **Ghi quá số byte đọc được.** Trong vòng lặp buffer, phải dùng **out.write(buffer, 0, count)**, không ghi cả mảng khi **count < buffer.length**.
7. **Đo hiệu năng chỉ bằng một lần chạy.** Tốc độ còn do page cache, JIT, I/O thực, dữ liệu, hệ điều hành và concurrency; benchmark đúng workload.
8. **Cho rằng buffer size càng lớn càng tốt.** RAM tăng theo số luồng, có khi không giảm được lời gọi nền thêm đáng kể.
9. **Tin rằng flush đồng nghĩa fsync hoặc ACK mạng.** Chúng khác nhau; phải chọn cơ chế xác nhận/durability đúng yêu cầu.
10. **Lạm dụng mark/reset khi cần tua ngược dài.** Mark có readlimit và có thể hết hiệu lực, không thay thế khả năng đọc lại file từ đầu.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** BufferedInputStream có phải biến dữ liệu từ byte thành văn bản không?  
**Đáp:** Không. Nó giữ byte trong mảng đệm, không giải mã ký tự.

**Câu 2.** Nếu ghi "ABC" vào BufferedOutputStream có dung lượng 8, byte đã nhất thiết tới OutputStream nền chưa?  
**Đáp:** Chưa. Nó có thể nằm trong buffer; **flush()** hoặc **close()** sẽ yêu cầu đẩy byte đi.

**Câu 3.** Tại sao ghi từng byte vào FileOutputStream có thể chậm hơn khi bọc bằng BufferedOutputStream?  
**Đáp:** Vì wrapper gom các lần gọi nhỏ thành lần ghi lớn xuống luồng nền, giảm chi phí gọi I/O.

**Câu 4.** Nếu vòng lặp đã đọc **byte[8192]** rồi ghi theo khối, thêm buffer luôn nhanh hơn đúng không?  
**Đáp:** Không. Lợi ích tùy triển khai nguồn/đích, kích thước truy cập, chi phí sao chép bộ nhớ và workload thật.

**Câu 5.** Gọi flush trên buffered output có bảo đảm ổ đĩa đã ghi bền vững hoặc đối tác mạng đã nhận không?  
**Đáp:** Không. Flush đẩy dữ liệu trong tầng buffering Java xuống luồng bên dưới, khác với đồng bộ đĩa hoặc xác nhận ở tầng giao thức.

**Câu 6.** BufferedInputStream có chức năng nào khác ngoài buffering?  
**Đáp:** Nó hỗ trợ **mark/reset**, cho phép quay lại vị trí đã đánh dấu trong giới hạn hợp lệ, kể cả khi InputStream nền không có hỗ trợ riêng.

## 11. Ghi nhớ và chọn API

**BufferedInputStream** giúp gom các lần đọc nhỏ thành ít lần đọc lớn hơn từ nguồn; **BufferedOutputStream** gom các lần ghi nhỏ và cần xả buffer đúng thời điểm qua **flush() / close()**. Cả hai là wrapper byte-stream, có thể ghép với stream nền khác theo decorator, không tự đổi charset và không tự giải quyết timeout hay độ bền dữ liệu.

Nếu đang **sao chép file đơn giản**, cân nhắc **Files.copy(...)**. Nếu xử lý byte theo luồng, cần làm việc từng byte hoặc có nhiều thao tác I/O nhỏ, hai lớp buffered là công cụ phù hợp. Chọn kích thước buffer dựa trên tần suất đọc/ghi, lượng RAM và phép đo thực tế.

### Tài liệu tham khảo

- [Oracle Java SE 17 — BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html): nguyên tắc buffering, constructor, mark/reset, read.
- [Oracle Java SE 17 — BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html): buffering, flush và close.
- [Oracle Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): đọc byte, read(byte[]), EOF.
- [Oracle Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): write(byte[], off, len), flush, close.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): newInputStream, newOutputStream, copy và mismatch.
