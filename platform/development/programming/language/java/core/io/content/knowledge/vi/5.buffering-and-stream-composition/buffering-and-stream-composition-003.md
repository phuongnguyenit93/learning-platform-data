# Decorator: lớp bọc bổ sung hành vi cho stream trong Java I/O

Một `InputStream` có thể đọc byte từ tệp, nhưng nếu muốn **đọc có bộ đệm**, **đọc kiểu dữ liệu nguyên thủy** hoặc **đếm số byte đã đọc** thì sao? Java I/O giải quyết nhiều nhu cầu như vậy bằng cách **bọc một stream bên trong stream khác**. Lớp bên ngoài giữ cùng giao diện đọc/ghi cơ bản, nhưng bổ sung hành vi trước hoặc sau khi chuyển công việc xuống stream bên trong. Đây là cách áp dụng **Decorator pattern** trong thực tế.

Ví dụ ghép luồng:

~~~text
CHƯƠNG TRÌNH
      |
      v
DataInputStream       <-- bổ sung readInt(), readLong(), readFully()...
      |
      v
BufferedInputStream   <-- thêm bộ đệm cho việc đọc byte
      |
      v
FileInputStream       <-- thực sự đọc byte từ tệp
      |
      v
TỆP NGUỒN
~~~

Ở chiều ghi, cùng tư tưởng hoạt động từ lớp ngoài vào lớp trong: `DataOutputStream` viết giá trị theo biểu diễn nhị phân, `BufferedOutputStream` gom các byte, rồi `FileOutputStream` đưa byte xuống tệp đích.

Sau bài học, bạn cần giải thích được **vai trò từng lớp**, **thứ tự ghép**, **cách lời gọi được chuyển tiếp**, **ai đóng tài nguyên**, và **vì sao bọc stream không tự thay đổi dữ liệu theo kiểu bạn mong muốn nếu chọn sai thứ tự**.

## 1. Decorator pattern trong ngữ cảnh luồng là gì?

Decorator là một mẫu thiết kế cấu trúc: tạo một đối tượng **bọc** một đối tượng có cùng giao diện, sau đó cho đối tượng bọc cung cấp hành vi bổ sung mà không phải sửa trực tiếp lớp nguồn. Trong Java I/O:

- **Component:** kiểu chung, chẳng hạn `InputStream` (đọc byte) hoặc `OutputStream` (ghi byte).
- **Concrete component:** stream nền cung cấp dữ liệu, ví dụ `FileInputStream`, `ByteArrayInputStream`, `FileOutputStream`.
- **Decorator:** stream bọc, như `BufferedInputStream`, `DataInputStream`, `BufferedOutputStream`, `DataOutputStream`.
- **Client:** code chỉ gọi đối tượng ngoài cùng, không cần tự điều phối từng tầng.

Hình dung:

~~~text
Client -> Decorator C -> Decorator B -> Decorator A -> Stream gốc
          [cùng hợp đồng InputStream hoặc OutputStream]
~~~

Decorator **giữ tham chiếu đến một stream khác** và thường ủy quyền các thao tác cần thiết cho nó, có thể thay đổi/đệm/chuyển đổi/đo lường dữ liệu. Về mặt kiến trúc, người dùng muốn thay đổi hành vi bằng **composition (ghép đối tượng)** thay vì sinh nhiều lớp con kết hợp mọi đặc tính.

Ví dụ tạo chuỗi đọc:

~~~java
InputStream input = new DataInputStream(
        new BufferedInputStream(
                new FileInputStream("payload.bin")));
~~~

Các lớp tham gia đều tương thích với kiểu `InputStream`, nên có thể đưa `input` tới các phương thức nhận `InputStream`. Tuy nhiên, phương thức đặc thù `readInt()` chỉ hiện ra nếu biến được khai báo theo kiểu `DataInputStream` hoặc có tham chiếu tới decorator đó:

~~~java
try (DataInputStream input = new DataInputStream(
        new BufferedInputStream(new FileInputStream("payload.bin")))) {
    int version = input.readInt();
}
~~~

Đây là **đoạn minh họa** (không chạy độc lập nếu chưa có `payload.bin` và import). Tệp phải thực sự chứa ít nhất bốn byte theo định dạng mà `readInt` mong đợi; `DataInputStream` không tự nhận biết định dạng file.

## 2. Những lớp decorator byte stream phổ biến

| Lớp | Bọc gì? | Hành vi bổ sung |
|---|---|---|
| `FilterInputStream` | `InputStream` | Lớp cơ sở cho các bộ lọc/luồng bọc input; mặc định phần lớn thao tác chuyển xuống stream bên trong. |
| `BufferedInputStream` | `InputStream` | Giữ một vùng byte đệm để giảm số lần phải đọc nguồn bên dưới; hỗ trợ `mark`/`reset` theo hợp đồng của lớp. |
| `DataInputStream` | `InputStream` | Đọc giá trị nhị phân có kiểu bằng `readInt()`, `readLong()`, `readDouble()`, `readFully()`, v.v. |
| `PushbackInputStream` | `InputStream` | Cho phép đẩy lại một hoặc nhiều byte qua `unread()` để lần đọc sau nhận lại chúng. |
| `FilterOutputStream` | `OutputStream` | Lớp cơ sở cho các bộ lọc/luồng bọc output. |
| `BufferedOutputStream` | `OutputStream` | Gom byte vào bộ đệm trước khi đưa xuống output bên dưới. |
| `DataOutputStream` | `OutputStream` | Ghi giá trị có kiểu như `writeInt()`, `writeLong()`, `writeDouble()` theo định dạng nhị phân của Java. |

Ngoài ra, các lớp nén như `GZIPInputStream` và `GZIPOutputStream` thuộc hệ thống Java I/O/ZIP cung cấp hành vi **giải nén/nén** khi bọc stream. Chúng hữu ích để thấy rằng decorator không chỉ làm bộ đệm: nó có thể thực hiện cả biến đổi dữ liệu.

Nhìn theo quan hệ kế thừa phổ biến:

~~~text
InputStream
  +-- FilterInputStream
        +-- BufferedInputStream
        +-- DataInputStream
        +-- PushbackInputStream

OutputStream
  +-- FilterOutputStream
        +-- BufferedOutputStream
        +-- DataOutputStream
~~~

Không phải **mọi** lớp đọc/ghi đều nhất thiết kế thừa `FilterInputStream`/`FilterOutputStream`. Điều quan trọng của decorator ở đây là **cấu trúc bao một đối tượng và bổ sung hành vi qua hợp đồng chung**, không chỉ tên lớp hoặc hệ kế thừa.

## 3. Cơ chế của lớp bọc: lời gọi chạy qua các tầng

Giả sử nguồn là file chứa byte và chương trình gọi:

~~~java
int value = input.read();
~~~

Nếu `input` là một `BufferedInputStream` bọc `FileInputStream`, lời gọi đi vào lớp buffer trước. Khi buffer còn byte, nó có thể trả ngay byte đã được giữ. Khi cần nạp thêm, nó đọc một khối byte từ `FileInputStream`, rồi trả một byte cho caller. Điều này **giảm số lần gọi xuống tầng I/O nền**, nhưng không nhất thiết làm số byte đầu ra khác đi.

Với `DataInputStream` ở lớp ngoài cùng:

~~~java
int version = dataInput.readInt();
~~~

`readInt()` lấy **bốn byte** từ tầng input bên dưới và ghép thành một giá trị `int` theo định dạng xác định của `DataInput` (big-endian cho số nguyên nhiều byte). `BufferedInputStream` bên trong có thể lấy trước thêm byte vào buffer, nhưng giá trị logic mà `readInt` trả về vẫn đến từ đúng bốn byte của trường dữ liệu này.

**Đừng nhầm số byte đã đọc từ nguồn vật lý với số byte client đã tiêu thụ.** Do nạp trước, `BufferedInputStream` có thể đọc nhiều byte từ file bên dưới dù caller mới yêu cầu một byte hoặc một giá trị. Nếu bạn đặt decorator để thống kê số byte **dưới** buffer, số đếm có thể lớn hơn lượng dữ liệu client đã sử dụng tại thời điểm đo. Nếu đặt thống kê **trên** buffer, số đếm phản ánh các byte đã đi qua lớp thống kê. Thứ tự bọc vì thế ảnh hưởng cả quan sát.

### Thứ tự bọc là một phần của thiết kế

Ví dụ hai cách đặt lớp đếm:

~~~text
A) Client -> CountingInputStream -> BufferedInputStream -> FileInputStream
    đếm byte đã được client lấy qua lớp Counting

B) Client -> BufferedInputStream -> CountingInputStream -> FileInputStream
    đếm byte Buffered đã lấy từ stream nền, kể cả byte đọc trước
~~~

Nếu mỗi tầng chỉ có hành vi chuyển tiếp, sự khác biệt khó thấy; nếu một tầng **buffer, nén, mã hóa, giải mã, kiểm đếm**, thứ tự có thể thay đổi kết quả hoặc số liệu. Thiết kế pipeline từ **định dạng byte thực trên nguồn/đích** rồi đặt tầng xử lý thích hợp.

## 4. Ví dụ Java 17 chạy được: ghép nhiều decorator

Ví dụ này cố tình không cần file bên ngoài. Ta tạo một định dạng nhị phân nhỏ:

~~~text
4 byte: version (số int)
4 byte: số byte của nội dung
N byte: văn bản mã hóa theo UTF-8
~~~

**Luồng ghi**: `DataOutputStream -> BufferedOutputStream -> ByteArrayOutputStream`.  
**Luồng đọc**: `DataInputStream -> BufferedInputStream -> CountingInputStream -> ByteArrayInputStream`.

`CountingInputStream` là decorator tự viết, kế thừa `FilterInputStream` để đếm byte đi qua nó. Tệp mã nguồn **`StreamDecoratorDemo.java`**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class StreamDecoratorDemo {
    static final class CountingInputStream extends FilterInputStream {
        private long count;

        CountingInputStream(InputStream wrapped) {
            super(wrapped);
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value != -1) count++;
            return value;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            int number = super.read(bytes, offset, length);
            if (number > 0) count += number;
            return number;
        }

        long getCount() {
            return count;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] message = "Xin chào".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream storage = new ByteArrayOutputStream();

        try (DataOutputStream output = new DataOutputStream(
                new BufferedOutputStream(storage))) {
            output.writeInt(3);
            output.writeInt(message.length);
            output.write(message);
        }

        byte[] wire = storage.toByteArray();
        CountingInputStream counted = new CountingInputStream(
                new ByteArrayInputStream(wire));
        try (DataInputStream input = new DataInputStream(
                new BufferedInputStream(counted))) {
            int version = input.readInt();
            int length = input.readInt();
            byte[] body = new byte[length];
            input.readFully(body);

            System.out.println("Version: " + version);
            System.out.println("Text: " + new String(body, StandardCharsets.UTF_8));
            System.out.println("Body length: " + length);
        }

        System.out.println("Encoded bytes: " + wire.length);
        System.out.println("Read from source: " + counted.getCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StreamDecoratorDemo.java
java StreamDecoratorDemo
~~~

Kết quả kỳ vọng khi terminal hỗ trợ UTF-8:

~~~text
Version: 3
Text: Xin chào
Body length: 9
Encoded bytes: 17
Read from source: 17
~~~

Nếu console của môi trường cấu hình encoding khác UTF-8, ký tự có dấu có thể hiển thị sai dù phép chuyển đổi byte và giá trị được đọc đúng. Phần còn lại của output vẫn giúp xác minh số byte và quá trình bọc.

**Phân tích từng tầng:**

1. `ByteArrayOutputStream storage` là **đích byte cuối** trong bộ nhớ. `BufferedOutputStream` làm bộ đệm, còn `DataOutputStream` cung cấp `writeInt` để ghi chính xác định dạng của hai số nguyên.
2. `message` có **9 byte UTF-8**: `Xin` có ba byte, dấu cách một byte, `chào` có năm byte vì ký tự `à` cần hai byte. `writeInt(3)` ghi bốn byte; `writeInt(9)` ghi bốn byte; `write(message)` ghi chín byte, nên kết quả là **4 + 4 + 9 = 17 byte**.
3. Đóng `DataOutputStream` ở cuối `try-with-resources` làm các byte còn trong `BufferedOutputStream` được đưa xuống tầng dưới. Sau đó `storage.toByteArray()` lấy byte đã tích lũy; việc đóng `ByteArrayOutputStream` không làm mất nội dung trong bộ nhớ.
4. `ByteArrayInputStream` cung cấp 17 byte để đọc ngược. `CountingInputStream` ghi nhận byte nguồn thực sự cấp; `BufferedInputStream` bọc nó để đệm; `DataInputStream` ở ngoài giải mã hai trường `int`.
5. `readFully(body)` đọc đủ `length` byte hoặc ném `EOFException` nếu không đủ. Nó phù hợp với định dạng có độ dài xác định; không giống một lần `read(body)` có thể trả ít byte hơn yêu cầu.
6. Trong trường hợp cụ thể này, toàn bộ 17 byte đều được tiêu thụ nên số byte đếm là 17. Nếu file có dữ liệu dư, bộ đệm có thể đọc trước nhiều hơn mức `DataInputStream` đã dùng.
7. `try-with-resources` đóng **lớp ngoài cùng**. Các lớp bọc tiêu chuẩn trong chuỗi ví dụ chuyển việc đóng xuống stream bên trong theo hợp đồng của chúng.

Ví dụ minh họa **cơ chế ghép stream và một định dạng nhị phân tự định nghĩa**; nó không phải một định dạng file tiêu chuẩn. Khi nhận dữ liệu từ nguồn không tin cậy, phải kiểm tra `length` (âm, quá lớn, vượt giới hạn cho phép) **trước khi cấp phát `new byte[length]`**. Không bao giờ cấp phát mảng tùy ý chỉ vì một số nguyên trong dữ liệu đầu vào khai báo kích thước như vậy.

### Vì sao decorator tự viết ghi đè hai overload `read`?

Một decorator thống kê cần quyết định **đo byte nào** và bao phủ các cách đọc mà code sử dụng. `read()` trả một byte hoặc `-1` khi hết luồng; `read(byte[], offset, length)` trả số byte đã đọc. Lớp trên tăng bộ đếm chỉ khi có dữ liệu thực sự. Nó kế thừa phần xử lý `read(byte[])` sao cho lời gọi đi qua overload có ba tham số.

Không nên lấy số lần **gọi phương thức** làm số byte đọc. Một lời gọi `read(byte[], off, len)` có thể nhận từ 1 đến `len` byte (hoặc giá trị đặc biệt theo hợp đồng của nó). Mọi decorator tự viết cũng cần xem xét các phương thức khác như `skip()`, `mark()` và `reset()` nếu muốn bộ đếm phản ánh một định nghĩa khác: ví dụ “tổng byte lấy từ nguồn”, “byte đến client” hay “vị trí hiện tại”. Bộ đếm đơn giản ở đây **không đếm `skip` và không đảo số đếm khi `reset`**; vì chương trình không gọi các phương thức ấy nên output ví dụ không bị ảnh hưởng.

## 5. Đóng stream bọc và quyền sở hữu tài nguyên

Với các decorator Java I/O thường gặp, khi đóng **decorator ngoài cùng**, lệnh `close()` được chuyển tới stream nằm bên trong, có thể tiếp tục xuống stream gốc:

~~~text
try (DataOutputStream out =
         new DataOutputStream(
             new BufferedOutputStream(
                 Files.newOutputStream(path)))) {
    // Ghi dữ liệu
}

Ra khỏi try:
DataOutputStream.close()
     -> BufferedOutputStream.close()
           -> OutputStream từ Files.newOutputStream(...).close()
~~~

Do đó, nếu chính phương thức tạo và sở hữu chuỗi decorator, thông thường chỉ cần khai báo **đối tượng ngoài cùng** trong `try-with-resources`. Không nhất thiết liệt kê mọi tầng như những tài nguyên riêng rồi tự đóng lặp lại. Tuy nhiên, phải tra cứu hợp đồng `close` của wrapper cụ thể; một thư viện có thể thiết kế wrapper không đóng stream bên dưới.

**Phân biệt rõ:**

- **Lớp ngoài cùng sở hữu chuỗi:** phương thức tạo stream gốc và decorator, tự chịu trách nhiệm đóng nó; `try-with-resources` ở tầng ngoài cùng là thuận tiện.
- **Lớp bọc mượn stream của caller:** nếu code đặt wrapper vào `try-with-resources`, việc đóng wrapper có thể **đóng luôn stream của caller**. Chỉ làm vậy khi hợp đồng cho phép chuyển quyền sở hữu hoặc caller không dùng stream nữa.
- **Luồng chung (`System.in`/`System.out`) hoặc framework quản lý:** không đóng bừa chỉ vì tiện viết `try-with-resources`. Cần quy định rõ ai kết thúc stream.
- **Stream output có buffer:** dữ liệu có thể chưa đi hết đến đích nếu chưa `flush()` hoặc `close()` đúng lúc. `flush` yêu cầu đẩy dữ liệu có đệm xuống tầng dưới, nhưng không tự bảo đảm dữ liệu đã bền vững trên đĩa hay ứng dụng đầu nhận đã xử lý.

Ví dụ helper nhận output từ caller và chỉ mượn:

~~~java
static void writeRecord(DataOutputStream output, int value)
        throws IOException {
    output.writeInt(value);
    // Không close: caller còn có thể ghi record tiếp.
}
~~~

Đây là **phương thức minh họa** được đặt trong một lớp Java có import `DataOutputStream` và `IOException`. Đối với luồng có dữ liệu đệm, caller chủ động quyết định khi nào flush/close dựa theo vòng đời và giao thức.

## 6. Các lớp bọc phải tương thích với loại dữ liệu

### Byte stream với byte stream

`BufferedInputStream`, `DataInputStream`, `PushbackInputStream` bọc một `InputStream` và vẫn thuộc phía **byte**; `BufferedOutputStream`, `DataOutputStream` bọc `OutputStream` và vẫn thuộc phía **byte**.

### Cầu nối byte và ký tự là adapter

`InputStreamReader` nhận `InputStream` và giải mã byte thành **ký tự**; `OutputStreamWriter` nhận `OutputStream` và mã hóa ký tự thành byte. Về vai trò thiết kế, chúng là **adapter giữa byte stream và character stream**, không phải decorator cùng kiểu `InputStream` ↔ `InputStream`.

~~~java
Reader reader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8));
~~~

Đoạn minh họa cần các import tương ứng. `input` là `InputStream` đã có; `InputStreamReader` chuyển byte thành ký tự UTF-8, và `BufferedReader` đệm ký tự/bổ sung `readLine()`. `BufferedReader` không phải `BufferedInputStream`: một bên đệm **ký tự**, bên kia đệm **byte**. Nếu cần bảo toàn dữ liệu nhị phân tuyệt đối, tránh đi qua decoder/encoder ký tự.

### Dữ liệu có kiểu phải đọc đúng cách đã ghi

`DataOutputStream.writeInt(123)` ghi **4 byte nhị phân**; phía đọc tương ứng là `DataInputStream.readInt()`. Không nên mở file vừa ghi bằng `writeInt` như một tệp UTF-8 rồi chờ thấy các chữ số `"123"`.

Một điểm dễ nhầm: `DataOutputStream.writeUTF(String)` dùng **modified UTF-8** với tiền tố độ dài, **không phải chính xác cùng byte với `string.getBytes(StandardCharsets.UTF_8)` trong mọi trường hợp**. Muốn định dạng một chuỗi **UTF-8 chuẩn** có độ dài rõ ràng, có thể dùng `writeInt(bytes.length)` rồi `write(bytes)` như ví dụ và đọc tương ứng `readInt()` + `readFully()`. Hai phía phải đồng ý về định dạng và thứ tự trường.

## 7. Lớp nén cũng cho thấy vì sao thứ tự ghép quan trọng

Khi lưu dữ liệu nhị phân được mã hóa bởi `DataOutputStream` rồi nén GZIP, một thứ tự hợp lý là:

~~~java
// Minh họa; path là Path đã khai báo.
try (DataOutputStream out = new DataOutputStream(
        new GZIPOutputStream(
                new BufferedOutputStream(
                        Files.newOutputStream(path))))) {
    out.writeInt(123);
}
~~~

Dữ liệu đi theo thứ tự: `DataOutputStream` tạo byte biểu diễn số nguyên → `GZIPOutputStream` **nén** các byte → `BufferedOutputStream` đệm byte đã nén trước khi ghi xuống tệp. Để đọc lại, dựng luồng có trật tự đối ứng:

~~~java
try (DataInputStream in = new DataInputStream(
        new GZIPInputStream(
                new BufferedInputStream(
                        Files.newInputStream(path))))) {
    int value = in.readInt();
}
~~~

Đây là **các đoạn minh họa** cần import `java.io.*`, `java.nio.file.*`, `java.util.zip.GZIPInputStream` và `java.util.zip.GZIPOutputStream`; `path` được cung cấp bởi ứng dụng. Chúng không tạo thành một chương trình `main` riêng.

Nếu đặt tầng giải nén sai phía, chẳng hạn cố `readInt()` trực tiếp từ byte GZIP chưa giải nén, sẽ không thu được số `123` đã ghi. Nếu thay đổi thứ tự các bộ lọc **có biến đổi dữ liệu**, cần thiết kế phía đọc tương ứng. Chỉ gắn thêm wrapper mà không hiểu giao thức là không đủ.

## 8. Decorator và các lựa chọn thay thế

Decorator phù hợp khi cần **tái sử dụng cùng nguồn/đích và thêm một hành vi theo từng tầng**. Tuy nhiên, không phải thao tác I/O nào cũng bắt buộc phải tự dựng chuỗi lớp bọc:

- `Files.readString(path, UTF_8)` hoặc `Files.writeString(path, text, UTF_8)` ngắn gọn khi xử lý một tệp văn bản nhỏ và biết charset.
- `Files.copy(source, destination)` phù hợp nếu chỉ cần sao chép tệp theo đường dẫn và không cần đụng đến dữ liệu ở giữa.
- `InputStream.transferTo(output)` sao chép byte còn lại từ input sang output; có thể sử dụng ngay cả khi input/output đã bọc nhiều tầng.
- `BufferedReader` hữu ích nếu cần đọc từng dòng văn bản; đây là tầng ký tự, nên dùng với charset giải mã phù hợp.
- Đối với bài toán cần nhiều hiệu năng hoặc thao tác ngẫu nhiên phức tạp, `java.nio.channels` có các lựa chọn kênh/buffer chuyên biệt; không nên mặc định decorator giải quyết mọi nhu cầu.

Đánh đổi của ghép nhiều tầng là **thêm cấu hình, thêm trạng thái nội bộ và trách nhiệm đóng tài nguyên**. Dùng đúng những tầng đáp ứng yêu cầu và kiểm tra API có sẵn, thay vì luôn thêm `BufferedInputStream` dù chưa đo lường hoặc API đã có cơ chế đọc theo khối thích hợp.

## 9. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách làm đúng |
|---|---|---|
| “Gắn thêm `BufferedInputStream` là tệp đổi nội dung.” | Buffer chỉ thay chiến lược lấy byte, không đổi bản chất định dạng. | Tách bạch **buffering** và **transformation**. |
| “`DataInputStream` sẽ tự hiểu file text/JSON.” | API này đọc định dạng byte của các phương thức `DataInput`, không đoán cấu trúc. | Phải biết schema binary và thứ tự trường đã ghi. |
| “Không cần quan tâm thứ tự decorator.” | Tầng nén, mã hóa, buffer, đếm có thể làm số liệu/dữ liệu khác. | Thiết kế đường đi từ producer đến consumer và ghép thứ tự đối ứng. |
| “Đóng wrapper ngoài không ảnh hưởng stream gốc.” | Nhiều wrapper gọi `close` xuống lớp dưới, vô tình đóng stream người khác sở hữu. | Thiết kế ownership, dùng `try-with-resources` ở bên sở hữu. |
| “`flush` và `close` là một.” | `flush` đẩy buffer, còn `close` kết thúc tài nguyên; không thể coi đồng nghĩa. | Flush/close theo hợp đồng khi hoàn tất bản ghi/luồng. |
| “Đọc `read(byte[])` một lần luôn đủ.” | Một lần đọc có thể trả ít hơn số byte yêu cầu. | Dùng vòng lặp hoặc `DataInputStream.readFully` khi định dạng đã có độ dài. |
| “`CountingInputStream` trong ví dụ luôn đếm byte mà client đã xử lý.” | Ở dưới buffer, lớp đếm còn thấy byte được đọc trước. | Đặt lớp đo ở tầng tương ứng với đại lượng cần đo. |
| “Đọc text bằng byte stream không cần charset.” | Khi chuyển byte thành ký tự, charset vẫn quyết định nội dung. | Dùng `InputStreamReader` với charset đúng nếu cần text. |
| “`new byte[length]` an toàn với mọi file.” | Độ dài trong input không tin cậy có thể sai/âm/rất lớn. | Ràng buộc độ dài trước khi cấp phát, xử lý EOF và lỗi định dạng. |

## 10. Bài tập tự kiểm tra

**Bài 1.** Chương trình đọc từng dòng UTF-8 từ file. Hãy mô tả các tầng hợp lý.

> **Đáp án:** `FileInputStream` (byte nguồn) → `InputStreamReader(..., UTF_8)` (giải mã byte thành ký tự) → `BufferedReader` (đệm ký tự và cung cấp `readLine()`). Hoặc dùng `Files.newBufferedReader(path, UTF_8)` để tạo trực tiếp reader phù hợp.

**Bài 2.** Vì sao có thể giữ biến ngoài cùng kiểu `InputStream` nhưng không gọi trực tiếp `readInt()`?

> **Đáp án:** `InputStream` là hợp đồng đọc byte chung; `readInt()` là phương thức bổ sung của `DataInputStream`. Muốn gọi trực tiếp phải có tham chiếu kiểu `DataInputStream` (hoặc giao diện hỗ trợ tương ứng), dù đối tượng runtime đang được bọc.

**Bài 3.** Khi code tự mở `FileInputStream` và bọc `BufferedInputStream`, nên đóng ở đâu?

> **Đáp án:** Dùng `try-with-resources` cho đối tượng bọc ngoài cùng do phương thức sở hữu. Theo hợp đồng của các lớp tiêu chuẩn này, đóng wrapper sẽ đóng stream nền. Đừng tự động dùng cách đó nếu stream nền do caller/framework sở hữu.

**Bài 4.** Đặt một bộ đếm phía dưới `BufferedInputStream`. Caller mới gọi `read()` một lần nhưng số đếm nhảy nhiều byte. Đó có chắc là lỗi không?

> **Đáp án:** Không. `BufferedInputStream` có thể nạp sẵn một khối byte. Bộ đếm phía dưới đo byte **đã lấy từ nguồn**, không nhất thiết là số byte caller đã tiêu thụ.

**Bài 5.** Ghi `writeInt(123)` qua `GZIPOutputStream`. Đọc `readInt()` trực tiếp từ tệp GZIP có đúng không?

> **Đáp án:** Không. Phải đặt `GZIPInputStream` ở phía nguồn để **giải nén** byte trước, rồi `DataInputStream` mới giải nghĩa chúng bằng `readInt()`.

## Ghi nhớ

Decorator stream là cách **bổ sung hành vi qua các tầng bọc có cùng giao diện I/O**. Khi ghép, hãy tự hỏi: **nguồn/đích thực là gì; lớp nào thêm buffer, xử lý định dạng hoặc biến đổi byte; thứ tự tầng có đúng với giao thức không; ai sở hữu và đóng chuỗi này?** Trả lời được các câu hỏi đó giúp thiết kế pipeline Java I/O vừa dễ mở rộng vừa không làm sai dữ liệu hoặc vòng đời tài nguyên.

**Tham khảo:** [Java SE 17 — `FilterInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterInputStream.html), [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html), [`DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`DataOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html).