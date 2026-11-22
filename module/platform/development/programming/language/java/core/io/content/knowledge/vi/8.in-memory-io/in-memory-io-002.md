# ByteArrayOutputStream.toByteArray() tạo bản sao và writeTo() chuyển dữ liệu

Trong Java I/O, **ByteArrayOutputStream** là một **OutputStream ghi vào vùng nhớ**: thay vì gửi ngay các byte đến ổ đĩa hoặc socket, nó tích lũy dữ liệu trong một buffer nội bộ có thể mở rộng. Hai phương thức thường dùng để lấy dữ liệu ra là:

- **byte[] toByteArray()**: trả về **một mảng byte mới** chứa bản sao của toàn bộ dữ liệu đã ghi tính đến thời điểm gọi.
- **void writeTo(OutputStream out)**: **chuyển các byte đang tích lũy sang một OutputStream khác**, không yêu cầu người gọi tạo mảng trung gian bằng toByteArray().

Hiểu sự khác biệt này giúp chọn đúng cách xuất dữ liệu, tránh sửa nhầm buffer, kiểm soát bộ nhớ và làm rõ ai sở hữu luồng đích.

## 1. ByteArrayOutputStream nằm ở đâu trong Java I/O?

**java.io.ByteArrayOutputStream** kế thừa **OutputStream**, nhưng ghi byte vào RAM. Có thể coi đối tượng có trạng thái logic như sau:

~~~text
ByteArrayOutputStream
┌──────────────────────────────────────┐
│ buffer nội bộ: [41][00][FF][42][..] │
│ số byte hợp lệ (count): 4           │
│ phần dung lượng còn trống: không phải dữ liệu
└──────────────────────────────────────┘
                 │
           ┌─────┴────────────┐
           ▼                  ▼
     toByteArray()       writeTo(out)
           │                  │
   mảng byte mới         out.write(...)
   [41 00 FF 42]         trên 4 byte hợp lệ
~~~

Ứng dụng ghi dữ liệu vào đối tượng bằng **write(int)** hoặc **write(byte[], off, len)**. Buffer nội bộ sẽ lớn lên khi cần; **size()** cho biết số byte đang hợp lệ, không phải dung lượng vật lý đã cấp phát. Việc này phù hợp khi muốn xây dựng một payload nhỏ trong bộ nhớ rồi lấy bytes để gửi đi, ví dụ tạo một frame nhị phân hoặc thông điệp trước khi xuất.

Ví dụ khởi tạo:

~~~java
ByteArrayOutputStream data = new ByteArrayOutputStream();
data.write(0x41);
data.write(new byte[] {0x00, (byte) 0xFF, 0x42});
System.out.println(data.size()); // 4
~~~

Đây là **mảnh code minh họa** (cần import **java.io.ByteArrayOutputStream** và đặt trong phương thức có quyền xử lý IOException nếu khai báo qua kiểu OutputStream). Kết quả **size() = 4** dù buffer có thể được cấp phát nhiều hơn 4 byte. Byte **0x00** và **0xFF** đều hợp lệ vì đây là I/O nhị phân, không có bước decode charset.

**ByteArrayOutputStream** không tự mở file, socket hay thiết bị nào. Muốn gửi dữ liệu ra ngoài, ứng dụng chủ động lấy byte bằng **toByteArray()** hoặc dùng **writeTo(out)**.

## 2. toByteArray(): tạo một bản sao độc lập

Hợp đồng của **toByteArray()** là trả về một **byte[] mới** chứa các byte đã ghi, theo đúng thứ tự, với độ dài bằng **size()** tại thời điểm lấy snapshot.

~~~java
byte[] snapshot = buffer.toByteArray();
~~~

Ở đây **buffer** là một ByteArrayOutputStream đã tạo. Mảng **snapshot** là **bản sao**, không phải một view của buffer nội bộ. Bởi vậy:

1. **Sửa phần tử của snapshot không làm thay đổi dữ liệu trong ByteArrayOutputStream.**
2. **Ghi thêm dữ liệu vào ByteArrayOutputStream không tự thay đổi nội dung hoặc độ dài của snapshot cũ.**
3. **reset()** ByteArrayOutputStream không làm rỗng các snapshot đã lấy.
4. **Gọi toByteArray() nhiều lần tạo các mảng mới**, dù dữ liệu có thể giống nhau; người gọi chịu trách nhiệm về chi phí cấp phát và vòng đời của mảng.

Ví dụ:

~~~text
Trước khi gọi:   ByteArrayOutputStream = [41 00 FF]
toByteArray():   snapshot          = [41 00 FF]

snapshot[0] = 5A:
                 snapshot          = [5A 00 FF]
                 ByteArrayOutputStream vẫn [41 00 FF]

Ghi thêm 42 vào stream:
                 ByteArrayOutputStream = [41 00 FF 42]
                 snapshot vẫn          = [5A 00 FF]
~~~

**Tại sao Java cố tình tạo bản sao?** Vì nếu lộ trực tiếp mảng nội bộ, code bên ngoài có thể thay dữ liệu trong luồng mà không qua **write(...)**, vi phạm đóng gói và dễ gây lỗi. Bản sao còn cho phép lưu lại trạng thái byte tại một thời điểm để xử lý sau khi ByteArrayOutputStream được ghi tiếp hoặc reset.

### 2.1. ByteArrayOutputStream và byte[] là hai trạng thái độc lập

Một lưu ý về **tính độc lập**: giá trị **snapshot** không phải “live view” cập nhật tự động. Nếu người dùng cần byte mới sau khi ghi tiếp, phải gọi **toByteArray()** lần khác.

~~~java
byte[] first = buffer.toByteArray();
buffer.write(0x7F);
byte[] second = buffer.toByteArray();
~~~

Đây là đoạn minh họa. **first** giữ nguyên mảng cũ, còn **second** có thêm byte mới. Hai mảng do hai lần gọi được tạo độc lập; chúng không chia sẻ phần tử theo kiểu cùng một mảng.

### 2.2. Chi phí RAM của toByteArray()

Nếu buffer đang chứa **N byte**, gọi **toByteArray()** phải cấp phát thêm một **byte[N]** và sao chép N byte từ vùng đệm. Trong lúc cả buffer nội bộ và snapshot còn được giữ, chương trình có thể phải giữ **cả hai vùng nhớ**; nếu gọi nhiều lần và giữ nhiều snapshot, RAM tăng thêm tương ứng.

Ví dụ lưu 50 MiB trong ByteArrayOutputStream, rồi gọi **toByteArray()**: ngoài bộ nhớ đã giữ trong stream, bản sao thường cần thêm khoảng **50 MiB** (chưa tính overhead mảng, dung lượng dư nội bộ, allocator và các đối tượng khác). Không có nghĩa tổng đúng 100 MiB trong mọi JVM, nhưng cho thấy tại sao cần cẩn thận với dữ liệu lớn.

Chi phí này **đáng chấp nhận khi thực sự cần một byte[] độc lập**, chẳng hạn API nhận byte[], tính hash trên snapshot, gửi qua phương thức chỉ hỗ trợ mảng, hoặc giữ phiên bản không đổi của payload khi tiếp tục xây dựng stream.

## 3. writeTo(OutputStream out): ghi các byte hiện có sang luồng đích

**writeTo(OutputStream out)** chuyển toàn bộ **size() byte đang tích lũy** sang một đối tượng **OutputStream** khác. Theo cách triển khai tiêu chuẩn của ByteArrayOutputStream, nó viết đoạn byte hợp lệ từ buffer nội bộ đến luồng đích; không bắt buộc tạo bản sao byte[] qua **toByteArray()** trước đó.

~~~java
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
buffer.write(new byte[] {1, 2, 3});

OutputStream destination = /* một OutputStream đã mở */;
buffer.writeTo(destination);
~~~

Đây là **mảnh minh họa**, chưa chạy độc lập vì cần tạo một destination thực tế. Phương thức **writeTo** gọi cơ chế ghi của OutputStream đích. OutputStream đích có thể là FileOutputStream, BufferedOutputStream, ByteArrayOutputStream khác, luồng mạng hoặc stream có xử lý bổ sung như nén/mã hóa.

### 3.1. writeTo() không xóa dữ liệu nguồn

**writeTo() không tiêu thụ hoặc reset nội dung của ByteArrayOutputStream.** Sau khi ghi sang destination, **size()** và các byte nguồn vẫn như cũ, nên có thể tiếp tục ghi thêm và gọi **writeTo()** lần khác.

~~~text
Nguồn đã tích lũy:    [41 42 43]  ("ABC")
Đích ban đầu:         [7E]

source.writeTo(dest)

Nguồn sau writeTo:    [41 42 43]  (giữ nguyên)
Đích sau writeTo:     [7E 41 42 43]
~~~

Nếu gọi **source.writeTo(dest)** thêm lần nữa mà không reset nguồn/đích, đích có thể nhận **ABC lần thứ hai**. Đây là cách **ghi thêm**, không phải sao chép kiểu “thay thế toàn bộ nội dung đích”. Chính OutputStream đích và trạng thái của nó quyết định có ghi nối tiếp, ghi đè hay một hình thức xử lý khác.

### 3.2. writeTo() không đồng nghĩa với flush() hoặc close()

**writeTo()** chuyển byte bằng API ghi của đích, **không tự đóng đích** và cũng **không mặc định gọi flush()** trên đích.

Ví dụ nếu **destination** là **BufferedOutputStream**, dữ liệu được chuyển vào buffer của destination nhưng có thể **chưa đến luồng nền** khi writeTo trả về. Nếu cần dữ liệu rời lớp đệm ngay, ứng dụng chủ động gọi **destination.flush()** ở ranh giới thích hợp. Nếu sở hữu destination, đóng bằng **try-with-resources**.

**flush() không đồng nghĩa với dữ liệu đã được ghi bền vững xuống đĩa hoặc đã được bên nhận xử lý.** Đó là các ranh giới xác nhận khác, phụ thuộc loại OutputStream, hệ thống file hoặc giao thức.

### 3.3. Chú ý IOException và tình trạng đích ghi dở

Chữ ký của **writeTo(OutputStream out)** cho phép ném **IOException**, phát sinh từ quá trình ghi xuống đích. Chẳng hạn ổ đĩa đầy, socket ngắt hoặc stream đích lỗi giữa chừng. Khi đó, đích **có thể đã nhận một phần dữ liệu** trước lúc lỗi. Đừng coi writeTo là giao dịch nguyên tử với cơ chế tự rollback.

Nếu **out** bằng null, việc gọi writeTo gây lỗi **NullPointerException** khi cố sử dụng đích. Cần bảo đảm đối tượng đích hợp lệ và xử lý lỗi I/O phù hợp ứng dụng.

## 4. So sánh hai API theo mục đích

| Tiêu chí | **toByteArray()** | **writeTo(OutputStream)** |
| --- | --- | --- |
| Kiểu trả về | **byte[]** | **void** |
| Tác dụng | Tạo snapshot byte độc lập | Đưa byte tích lũy sang OutputStream khác |
| Cần mảng mới kích thước dữ liệu? | **Có** theo hợp đồng | **Không bắt buộc** tạo mảng snapshot ở phía ByteArrayOutputStream |
| Dữ liệu nguồn sau thao tác | Giữ nguyên | Giữ nguyên |
| Đầu ra có phụ thuộc trạng thái đích? | Không có đích | Có: phụ thuộc OutputStream được truyền |
| Có tự flush/close luồng đích? | Không áp dụng | **Không** |
| Lỗi thường cần xét | Cấp phát bộ nhớ, OutOfMemoryError | IOException, ghi dở, ownership đích |
| Nên chọn khi | Cần byte[] để lưu snapshot, API yêu cầu mảng | Muốn chuyển trực tiếp dữ liệu hiện có vào stream đích |

Cả hai đều **không biến byte thành ký tự**. Nếu đang xử lý PNG, ZIP, PDF hoặc payload nhị phân, dữ liệu vẫn là byte. Khi muốn text, nên giải mã bằng charset tường minh ở tầng ứng dụng, tránh dùng **toString()** không chỉ định charset rồi tưởng đây là bản sao byte.

## 5. Ví dụ Java 17+ độc lập: snapshot, writeTo, ghi thêm và reset

Lưu chương trình sau thành **MemoryTransferDemo.java**:

~~~java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class MemoryTransferDemo {
    private static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream source = new ByteArrayOutputStream(2);
        source.write(new byte[] {0x41, 0x00, (byte) 0xFF});

        byte[] snapshot1 = source.toByteArray();
        snapshot1[0] = 0x5A; // Đổi A thành Z trong bản sao.
        System.out.println("snapshot1=" + hex(snapshot1));
        System.out.println("source=" + hex(source.toByteArray()));

        source.write(0x42); // Thêm B vào source.
        byte[] snapshot2 = source.toByteArray();
        System.out.println("snapshot2=" + hex(snapshot2));

        ByteArrayOutputStream target = new ByteArrayOutputStream();
        target.write(0x7E); // Byte có sẵn tại đích.
        source.writeTo(target);
        System.out.println("target=" + hex(target.toByteArray()));

        // Đích đã nhận dữ liệu; việc thêm vào source không cập nhật đích.
        source.write(0x43);
        System.out.println("target after source append=" +
                hex(target.toByteArray()));

        // Reset nguồn không thay đổi snapshot2 đã tạo trước đó.
        source.reset();
        source.write("12".getBytes(StandardCharsets.US_ASCII));
        System.out.println("source after reset=" +
                hex(source.toByteArray()));
        System.out.println("snapshot2 after reset=" + hex(snapshot2));

        // writeTo không tự flush luồng đích có bộ đệm.
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (BufferedOutputStream buffered =
                     new BufferedOutputStream(sink, 8)) {
            source.writeTo(buffered);
            System.out.println("sink before flush=" + sink.size());
            buffered.flush();
            System.out.println("sink after flush=" + sink.size());
        }

        System.out.println("sink data=" + hex(sink.toByteArray()));
        System.out.println("snapshot2 matches original prefix=" +
                Arrays.equals(snapshot2,
                        new byte[] {0x41, 0x00, (byte) 0xFF, 0x42}));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac MemoryTransferDemo.java
java MemoryTransferDemo
~~~

Kết quả chính xác:

~~~text
snapshot1=5a00ff
source=4100ff
snapshot2=4100ff42
target=7e4100ff42
target after source append=7e4100ff42
source after reset=3132
snapshot2 after reset=4100ff42
sink before flush=0
sink after flush=2
sink data=3132
snapshot2 matches original prefix=true
~~~

Giải thích:

1. **snapshot1** ban đầu chứa **41 00 FF**. Sửa phần tử đầu của snapshot thành **5A** không làm nguồn thay đổi: nguồn vẫn **41 00 FF**.
2. Ghi thêm **42** vào nguồn rồi gọi **toByteArray()** tạo **snapshot2 = 41 00 FF 42**.
3. **target** đã có byte **7E**. **source.writeTo(target)** ghi tiếp **41 00 FF 42**, cho kết quả **7E 41 00 FF 42**; nội dung nguồn không bị xóa.
4. Sau đó ghi thêm **43** vào nguồn, target vẫn giữ byte cũ; writeTo không tạo kết nối tự đồng bộ giữa hai stream.
5. **reset()** khiến số byte hợp lệ của nguồn về 0 rồi nhận **31 32** (ASCII “12”). Snapshot2 vẫn giữ **41 00 FF 42**.
6. Với **BufferedOutputStream** dung lượng 8, writeTo của nguồn 2 byte chưa làm sink nhận dữ liệu vì 2 byte đang nằm trong buffer. **flush()** làm sink nhận đủ 2 byte.

Ví dụ sử dụng **ByteArrayOutputStream** làm đích để quan sát trực tiếp byte sau khi ghi. Với file hoặc socket thật, flush và thời điểm dữ liệu được xác nhận còn tùy tầng bên dưới.

## 6. Xuất ByteArrayOutputStream ra file: hai cách thường gặp

Giả sử đã tích lũy payload trong biến **content** kiểu **ByteArrayOutputStream** và có đường dẫn file đích **Path destination**.

### Cách 1: toByteArray() + Files.write

~~~java
byte[] payload = content.toByteArray();
Files.write(destination, payload);
~~~

Đây là **mảnh code**, giả định đã import **java.nio.file.Files**, **java.nio.file.Path** và có các biến nói trên. Phương thức hữu ích khi ứng dụng **cần giữ một mảng độc lập** để tính hash, truyền vào API khác hoặc lưu snapshot. Đổi lại, nó tạo mảng mới có kích thước số byte đang tích lũy.

### Cách 2: writeTo() + Files.newOutputStream

~~~java
try (OutputStream file = Files.newOutputStream(destination)) {
    content.writeTo(file);
}
~~~

Mảnh code này cần import **java.io.OutputStream** và **java.nio.file.Files**, đồng thời sử dụng các biến **content**, **destination**. Khi nghiệp vụ chỉ muốn đưa nội dung ByteArrayOutputStream ra stream khác, **writeTo(file)** trực tiếp thường tránh được bước tạo bản sao **byte[]** như cách 1.

**Lưu ý quan trọng:** **Files.write(path, bytes)** và **Files.newOutputStream(path)** với tùy chọn mặc định đều có thể **tạo file mới hoặc cắt file đích đang tồn tại**. Nếu không muốn ghi đè dữ liệu có sẵn, phải chủ động chọn chính sách mở/tạo file khác, kiểm tra đường dẫn và xử lý lỗi. Việc writeTo không tự quyết định chính sách ghi đè; đó là trách nhiệm của cách tạo OutputStream đích.

Với dữ liệu lớn, vấn đề lớn hơn bản sao toByteArray chính là **ByteArrayOutputStream đã giữ tất cả dữ liệu trong RAM từ đầu**. Nếu có thể đọc trực tiếp từ nguồn và ghi vào đích theo khối, hãy cân nhắc streaming:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    in.transferTo(out);
}
~~~

Đây là **mảnh code minh họa**, cần import **java.io.InputStream**, **java.io.OutputStream**, **java.nio.file.Files** và biến **Path source/destination** hợp lệ. **InputStream.transferTo(OutputStream)** tránh việc phải dồn toàn bộ nội dung vào một ByteArrayOutputStream; đây là lựa chọn khác khi không cần tích lũy dữ liệu trong bộ nhớ.

## 7. reset(), close() và sự khác nhau giữa kích thước nội dung với dung lượng buffer

**reset()** đặt số byte hợp lệ về **0** để tái sử dụng vùng nhớ đã cấp phát:

~~~java
ByteArrayOutputStream content = new ByteArrayOutputStream();
content.write(new byte[] {10, 20, 30});
byte[] saved = content.toByteArray();

content.reset();
System.out.println(content.size()); // 0
System.out.println(saved.length);    // 3
~~~

Mảnh code này cho thấy **saved** vẫn độc lập với content. Gọi reset **không xóa nội dung trong saved**, đồng thời **không bảo đảm xóa sạch các byte cũ khỏi mảng nội bộ**; nó thường chỉ thay đổi biến đếm hợp lệ, giữ dung lượng buffer để tái sử dụng. Do đó, **reset không phải thao tác xóa dữ liệu bí mật an toàn khỏi RAM**.

**close()** của **ByteArrayOutputStream** theo đặc tả **không có tác dụng**: các phương thức vẫn có thể được gọi sau khi đóng đối tượng này. Đây là ngoại lệ hữu ích của stream thuần bộ nhớ, **không áp dụng tùy tiện cho OutputStream file/socket**. Nếu dùng writeTo để gửi đến file/socket, **phải quản lý vòng đời luồng đích riêng**. Với buffer lớn đã sử dụng xong, bỏ tham chiếu để GC có cơ hội thu hồi bộ nhớ; reset đơn thuần có thể tiếp tục giữ mảng nội bộ lớn.

**size()** là số byte đã tích lũy, không phải capacity. Nếu một ByteArrayOutputStream đã từng giữ 10 MiB rồi reset, **size() == 0** nhưng bộ nhớ backing buffer có thể vẫn được giữ ở mức tương ứng. Nếu mong giải phóng RAM sau đợt dữ liệu lớn, không nên giữ mãi đối tượng cũ.

## 8. Có nên dùng toString() thay toByteArray()?

**ByteArrayOutputStream.toString(Charset)** hoặc tạo **new String(byte[], charset)** biến các byte thành **văn bản theo charset**, đó là thao tác khác. Nếu payload là UTF-8 hợp lệ và mục đích là đọc text, giải mã có charset tường minh như **StandardCharsets.UTF_8** là hợp lý.

Nếu byte đại diện PNG, ZIP, PDF, dữ liệu nén hoặc các frame nhị phân, không chuyển qua String để sao chép. Những byte không hợp lệ theo charset có thể bị thay thế và không khôi phục được bản gốc khi mã hóa lại.

Ví dụ:

~~~java
ByteArrayOutputStream content = new ByteArrayOutputStream();
content.write(new byte[] {0x41, (byte) 0xFF});

byte[] exact = content.toByteArray(); // [41 FF], nguyên byte.
String text = content.toString(StandardCharsets.UTF_8);
// "A�" trong xử lý decode UTF-8 thay thế byte FF không hợp lệ.
~~~

Đây là **mảnh code minh họa**, cần import **java.io.ByteArrayOutputStream** và **java.nio.charset.StandardCharsets**. Đối với luồng nhị phân, **byte[]** và OutputStream là mức trừu tượng phù hợp.

Đừng nhầm **toByteArray()** với **toString()**: một phương thức sao chép byte, phương thức còn lại chuyển nội dung thành biểu diễn ký tự, có nguy cơ mất thông tin khi byte không tạo thành văn bản hợp lệ.

## 9. Bảng quyết định theo tình huống

| Tình huống | Chọn API | Lý do |
| --- | --- | --- |
| Cần nhận payload dưới dạng **byte[]** để gọi thư viện | **toByteArray()** | Có snapshot độc lập theo hợp đồng |
| Muốn sửa thử byte đã nhận mà không sửa dữ liệu đang tích lũy | **toByteArray()** | Thay đổi trên mảng bản sao không ảnh hưởng nguồn |
| Đã có ByteArrayOutputStream và muốn ghi ngay vào **file/socket OutputStream** | **writeTo(out)** | Truyền các byte đã tích lũy đến đích mà không cần mảng snapshot |
| Muốn xuất cùng payload đến hai đích khác nhau | Gọi **writeTo(out1)** và **writeTo(out2)** | Nguồn không bị tiêu thụ sau mỗi lần |
| Muốn bắt đầu tích lũy một payload mới với cùng đối tượng | **reset()**, rồi **write(...)** | Reset số byte hợp lệ, tái sử dụng buffer |
| Muốn đích buffered gửi dữ liệu đang giữ | Gọi **flush()** trên đích | writeTo không tự flush |
| Cần xử lý file hàng GB, không cần toàn bộ trong RAM | **InputStream/OutputStream streaming** | Không cần tích lũy toàn bộ dữ liệu rồi mới xuất |
| Cần sao chép file đơn giản | **Files.copy(...)** | API chuyên dụng cho file, có tùy chọn copy phù hợp |

## 10. Các lỗi phổ biến và cách tránh

1. **Cho rằng toByteArray() trả về mảng nội bộ.** Thực tế là **bản sao mới**; chỉnh sửa mảng không ảnh hưởng source.
2. **Cho rằng writeTo() làm rỗng nguồn.** Nó **không reset**, nên lần writeTo sau có thể ghi lại dữ liệu cũ.
3. **Cho rằng writeTo() cũng tạo snapshot trả về.** Nó trả **void** và ghi trực tiếp bằng hợp đồng của OutputStream đích.
4. **Quên flush đích có buffer.** writeTo có thể trả về trong lúc BufferedOutputStream vẫn giữ byte; flush khi cần gửi ngay.
5. **Quên đóng OutputStream đích.** Close ByteArrayOutputStream không thay thế close file/socket.
6. **Giữ nhiều snapshot lớn từ toByteArray().** Mỗi bản sao cần RAM riêng, tăng sức ép GC.
7. **Gọi reset và tưởng mảng đã cấp phát được giải phóng hoặc bị xóa an toàn.** Reset chỉ làm rỗng trạng thái logic của dữ liệu hợp lệ.
8. **Dùng ByteArrayOutputStream cho dữ liệu cực lớn mà không cần gom vào RAM.** Chọn streaming theo khối để giới hạn bộ nhớ.
9. **Chuyển nhị phân thành String rồi encode lại.** Có thể làm biến đổi byte; giữ dạng byte[] hoặc OutputStream.
10. **Coi writeTo() là ghi giao dịch nguyên tử.** Nếu đích lỗi giữa chừng, đích có thể nhận một phần dữ liệu; cần chiến lược retry hoặc file tạm phù hợp.
11. **Không phân biệt ghi nối tiếp và ghi đè đích.** writeTo ghi theo hành vi hiện tại của OutputStream; cách mở file quyết định truncate/append.
12. **Tính độ dài bằng dung lượng đã cấp phát.** Dùng **size()** hoặc độ dài của mảng toByteArray, không giả định kích thước backing buffer bằng số byte hợp lệ.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Ghi byte [1, 2], lấy **a = toByteArray()**, rồi sửa **a[0] = 9**. Gọi **toByteArray()** lần nữa sẽ trả dữ liệu gì?  
**Đáp:** **[1, 2]**, vì mảng **a** độc lập với buffer trong ByteArrayOutputStream.

**Câu 2.** Gọi **source.writeTo(target)** rồi **source.reset()**. Target có mất dữ liệu đã nhận không?  
**Đáp:** Không. reset chỉ làm rỗng số byte hợp lệ ở **source**; target đã nhận một bản ghi byte theo hợp đồng của nó.

**Câu 3.** Nếu gọi **writeTo(target)** hai lần với source không đổi thì sao?  
**Đáp:** Target có thể nhận nội dung nguồn **hai lần liên tiếp**, trừ khi hành vi riêng của target hoặc cách ứng dụng điều khiển khác đi.

**Câu 4.** writeTo trên **BufferedOutputStream** có tự flush sau mỗi lần không?  
**Đáp:** Không; gọi **flush()** khi cần đẩy các byte đang đệm xuống luồng nền.

**Câu 5.** Vì sao dùng **writeTo(file)** đôi khi tiết kiệm RAM hơn **Files.write(path, source.toByteArray())**?  
**Đáp:** writeTo không yêu cầu tạo mảng bản sao bằng toByteArray. Nhưng bản thân source vẫn đã giữ dữ liệu trong RAM; lợi ích chỉ nằm ở việc tránh một bản sao bổ sung.

**Câu 6.** Nếu **reset()** làm **size() == 0**, có nghĩa bộ nhớ đệm đã bị hủy hoặc mọi byte bí mật đã bị xóa chưa?  
**Đáp:** Không. Dung lượng buffer có thể còn được giữ, và reset không phải thao tác xóa byte bảo mật.

**Câu 7.** Nếu file đích có dữ liệu cũ, **Files.newOutputStream(destination)** không option có giữ dữ liệu cũ không?  
**Đáp:** Thông thường **không**: nó sẽ mở file theo tùy chọn mặc định **CREATE** và **TRUNCATE_EXISTING** cho việc ghi. Muốn hành vi khác, phải dùng option phù hợp có kiểm soát.

## 12. Kết luận

**toByteArray()** cung cấp **snapshot byte[] độc lập**; dùng khi cần mảng để lưu, truyền API hoặc xử lý riêng. **writeTo(OutputStream)** gửi **các byte đang tích lũy** đến một stream đích, thuận tiện khi cần xuất dữ liệu mà không tạo một mảng snapshot phụ. Cả hai đều **giữ nguyên nội dung logic của nguồn**, nhưng **writeTo** có thể thất bại do lỗi đích và không tự flush/close đích.

Với dữ liệu lớn, điều cần xem xét trước tiên là **có thật sự cần giữ toàn bộ nội dung trong ByteArrayOutputStream hay không**. Nếu không, chọn luồng đọc/ghi theo khối. Với dữ liệu vừa và nhỏ cần tích lũy trong bộ nhớ, dùng **toByteArray / writeTo / reset / size** đúng hợp đồng sẽ giúp giữ chính xác byte và tránh nhiều lỗi khó tìm.

### Tham khảo

- [Oracle Java SE 17 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): hợp đồng toByteArray, writeTo, reset, size, close.
- [Oracle Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): write, flush và close.
- [Oracle Java SE 17 — BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html): việc đệm byte và flush.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): Files.write, Files.newOutputStream và streaming qua file.
