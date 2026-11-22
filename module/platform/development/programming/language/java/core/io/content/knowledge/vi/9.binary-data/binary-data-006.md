# readUTF, writeUTF và modified UTF-8 trong Java I/O

## 1. Đọc và ghi String trong định dạng dữ liệu nhị phân

Trong Java Core, **DataOutputStream.writeUTF(String)** và **DataInputStream.readUTF()** là cặp API để ghi và đọc chuỗi theo một định dạng nhị phân có quy ước cụ thể. Nó thường đi cùng các thao tác có kiểu như **writeInt/readInt** và **writeBoolean/readBoolean** khi chương trình tự định nghĩa giao thức nhị phân.

Cần phân biệt: **writeUTF không đơn thuần ghi UTF-8 chuẩn**. Nó ghi **hai byte chiều dài** rồi tới nội dung theo **modified UTF-8** (UTF-8 biến đổi theo định dạng Java DataInput/DataOutput). **readUTF** thực hiện quy trình ngược lại.

Ví dụ:

~~~text
writeUTF("Hi") → 00 02 48 69

00 02  : số byte payload = 2 (unsigned short, big-endian)
48 69  : nội dung "Hi" theo modified UTF-8
~~~

Trong khi đó, **"Hi".getBytes(StandardCharsets.UTF_8)** chỉ sinh **48 69**; nó **không** có hai byte tiền tố chiều dài. Vì vậy không thể thay thế cặp writeUTF/readUTF bằng getBytes và new String mà bỏ qua việc thay đổi định dạng trên wire.

Mục tiêu của bài: nắm rõ cấu trúc bản ghi, phân biệt modified UTF-8 và UTF-8 chuẩn, kiểm tra giới hạn byte 65.535, phân loại lỗi đọc/ghi, và triển khai Java 17+ chính xác.

## 2. Cấu trúc nhị phân của writeUTF

Khi gọi **DataOutputStream.writeUTF(text)**, kết quả trên OutputStream có dạng:

~~~text
┌─────────────────────────┬───────────────────────────────────────┐
│ unsigned 16-bit length  │       modified UTF-8 payload         │
│        2 byte           │        chính xác length byte         │
└─────────────────────────┴───────────────────────────────────────┘
          big-endian
~~~

- **Length** là số byte **đã mã hóa** của nội dung, **không tính hai byte prefix**.
- Hai byte length ghi theo **big-endian**: byte cao trước, byte thấp sau.
- Miền length là **0 đến 65.535**, tương đương unsigned short 16-bit.
- Nếu chuỗi rỗng, **writeUTF("")** ghi đúng hai byte **00 00**.
- Nếu chuỗi là **"A"**, kết quả là **00 01 41**.
- Nếu chuỗi là **"é"** (U+00E9), kết quả là **00 02 C3 A9**.
- Nếu chuỗi chỉ gồm ký tự NUL, kết quả là **00 02 C0 80**.

**String.length() không phải độ dài byte**. Java String lưu trữ nội dung theo các đơn vị UTF-16; số byte modified UTF-8 trên wire có thể lớn hơn String.length() nhiều lần. Length prefix chính là số byte payload **sau khi mã hóa**.

**DataInputStream.readUTF()** đọc hai byte chiều dài trước, sau đó lấy đúng số byte payload để giải mã thành một **String**. Nó không đọc một dòng, không dò dấu kết thúc văn bản và không đọc tất cả những byte còn lại của stream.

## 3. Modified UTF-8 khác UTF-8 chuẩn như thế nào?

Modified UTF-8 ở đây mã hóa từng **UTF-16 code unit** tương ứng với Java **char**:

| Giá trị UTF-16 code unit | Độ dài | Dạng byte |
| --- | ---: | --- |
| U+0001 đến U+007F | 1 byte | 0xxxxxxx |
| U+0000 hoặc U+0080 đến U+07FF | 2 byte | 110xxxxx 10xxxxxx |
| U+0800 đến U+FFFF | 3 byte | 1110xxxx 10xxxxxx 10xxxxxx |

Trong đó các chữ x là các bit lấy từ code unit.

### 3.1. NUL: U+0000 thành C0 80

UTF-8 chuẩn mã hóa ký tự U+0000 thành **00**. Với Java DataOutput.writeUTF, ký tự đó được mã hóa thành **C0 80** (hai byte). Đây là chuỗi **overlong** nếu xét theo tiêu chuẩn UTF-8 hiện đại, nên **không được xem nó là UTF-8 chuẩn hợp lệ**.

~~~text
String chứa "A", NUL, "B"

UTF-8 chuẩn payload:         41 00 42
writeUTF payload biến đổi:  41 C0 80 42
Toàn bản ghi writeUTF:   00 04 41 C0 80 42
~~~

Chỉ một ký tự NUL đã khiến hai cách mã hóa khác nhau dù các byte ASCII còn lại giống nhau.

### 3.2. Ký tự Unicode ngoài BMP: UTF-8 4 byte, modified UTF-8 6 byte

Một code point bổ sung như **U+1F600** biểu diễn bằng UTF-8 chuẩn trong **4 byte: F0 9F 98 80**. Java String biểu diễn nó bằng **cặp surrogate UTF-16 D83D DE00**, tức hai Java **char**.

**writeUTF** mã hóa hai code unit ấy riêng biệt, mỗi code unit 3 byte:

~~~text
U+1F600:
UTF-16 surrogate pair:   D83D DE00
Modified UTF-8 payload: ED A0 BD ED B8 80    (6 byte)
UTF-8 chuẩn:            F0 9F 98 80          (4 byte)
writeUTF full record:   00 06 ED A0 BD ED B8 80
~~~

Sau khi **readUTF** giải mã, nó tạo lại hai code unit trong Java String. Không được nhầm **một Unicode code point** với **một Java char**.

### 3.3. Khi nào byte giống nhau?

Các ký tự ASCII khác NUL được mã hóa một byte như UTF-8 chuẩn. Nhiều ký tự BMP, chẳng hạn **é** U+00E9, được mã hóa giống UTF-8 chuẩn (**C3 A9**).

Nhưng **trùng một phần payload không làm hai định dạng tương thích**: **writeUTF** vẫn có tiền tố chiều dài và vẫn khác ở NUL/surrogates. Không được dùng **StandardCharsets.UTF_8** làm decoder tổng quát cho payload writeUTF.

## 4. Ví dụ Java 17+ độc lập: mã hex và round-trip

Lưu file **ModifiedUtfDemo.java** với mã sau:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class ModifiedUtfDemo {
    public static void main(String[] args) throws IOException {
        String first = "A" + '\0' + '\u00E9';
        String supplementary =
                new String(Character.toChars(0x1F600));

        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeUTF(first);
            out.writeUTF(supplementary);
        }

        byte[] wire = memory.toByteArray();
        System.out.println("wire=" + HexFormat.of().formatHex(wire));
        System.out.println("wireLength=" + wire.length);

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            String a = in.readUTF();
            String b = in.readUTF();
            System.out.println("firstEqual=" + first.equals(a));
            System.out.println("supplementaryEqual=" +
                    supplementary.equals(b));
        }

        byte[] standard = first.getBytes(StandardCharsets.UTF_8);
        System.out.println("standardUtf8=" +
                HexFormat.of().formatHex(standard));
        System.out.println("firstLength=" + first.length());
        System.out.println("supplementaryLength=" +
                supplementary.length());
        System.out.println("differentWire=" +
                !Arrays.equals(standard, wire));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 ModifiedUtfDemo.java
java ModifiedUtfDemo
~~~

Stdout:

~~~text
wire=000541c080c3a90006eda0bdedb880
wireLength=15
firstEqual=true
supplementaryEqual=true
standardUtf8=4100c3a9
firstLength=3
supplementaryLength=2
differentWire=true
~~~

Phân tích:

- **00 05**: payload chuỗi đầu có 5 byte.
- **41**: A; **C0 80**: NUL; **C3 A9**: é.
- **00 06**: payload chuỗi sau có 6 byte.
- **ED A0 BD ED B8 80**: cặp surrogate của U+1F600.
- Toàn bộ stream: **2 + 5 + 2 + 6 = 15 byte**.
- Chuỗi đầu có **3 char UTF-16**, nhưng payload modified UTF-8 là **5 byte**.
- Chuỗi thứ hai có **2 char UTF-16** nhưng biểu diễn **một code point Unicode**.
- Mã hóa UTF-8 chuẩn của chuỗi đầu là **41 00 C3 A9**, dài **4 byte**, khác rõ wire format của writeUTF.

**readUTF hai lần** giải mã chính xác hai bản ghi do writeUTF tạo. Kết quả này minh họa tính đối xứng giữa hai API, không có nghĩa payload là UTF-8 chuẩn.

## 5. Phối hợp writeUTF với writeInt/writeBoolean

DataOutputStream ghi các trường đúng thứ tự lời gọi. DataInputStream phải đọc theo **đúng thứ tự và đúng kiểu**. Không có schema tự động trong stream.

Lưu ví dụ **DataRecordDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.HexFormat;

public class DataRecordDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeInt(7);
            out.writeUTF("OK");
            out.writeBoolean(true);
        }

        byte[] raw = memory.toByteArray();
        System.out.println("hex=" + HexFormat.of().formatHex(raw));

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(raw))) {
            int version = in.readInt();
            String name = in.readUTF();
            boolean enabled = in.readBoolean();

            System.out.println("version=" + version);
            System.out.println("name=" + name);
            System.out.println("enabled=" + enabled);
        }
    }
}
~~~

Chạy:

~~~bash
javac DataRecordDemo.java
java DataRecordDemo
~~~

Stdout:

~~~text
hex=0000000700024f4b01
version=7
name=OK
enabled=true
~~~

Wire format theo thứ tự:

~~~text
00 00 00 07     int 7, big-endian, 4 byte
00 02           payload UTF dài 2 byte
4F 4B           hai byte của "OK"
01              boolean true
~~~

Nếu bên đọc gọi **readUTF()** trước **readInt()**, nó có thể hiểu hai byte đầu của int 7 (**00 00**) là một chuỗi rỗng và đọc sai các trường tiếp theo. Vì vậy, hai phía phải thống nhất **schema, version, thứ tự field, kiểu, độ dài và cách xử lý lỗi**.

## 6. Giới hạn độ dài: tối đa 65.535 byte payload

Phương thức **writeUTF** không ghi chuỗi có payload modified UTF-8 dài hơn **65.535 byte**, vì chiều dài được mã hóa trên 16 bit không dấu. Nếu vượt, nó ném **UTFDataFormatException**.

Bảng minh họa:

| Giá trị String | String.length() | Payload modified UTF-8 | Kết quả writeUTF |
| --- | ---: | ---: | --- |
| "A".repeat(65535) | 65.535 | 65.535 byte | Thành công |
| "A".repeat(65536) | 65.536 | 65.536 byte | UTFDataFormatException |
| Một chuỗi 32.767 ký tự NUL | 32.767 | 65.534 byte | Thành công |
| Một chuỗi 32.768 ký tự NUL | 32.768 | 65.536 byte | UTFDataFormatException |
| "é".repeat(32768) | 32.768 | 65.536 byte | UTFDataFormatException |

**Giới hạn này là byte đã mã hóa, không phải số ký tự**. Ngay cả khi String.length() thấp hơn 65.535, payload vẫn có thể vượt giới hạn khi nhiều code unit mã hóa thành 2 hoặc 3 byte.

Lưu file **UtfLengthLimitDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UTFDataFormatException;

public class UtfLengthLimitDemo {
    private static void test(String s) throws IOException {
        ByteArrayOutputStream target = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(target)) {
            out.writeUTF(s);
        } catch (UTFDataFormatException ex) {
            System.out.println("too long");
            return;
        }

        System.out.println("written=" + target.size());
    }

    public static void main(String[] args) throws IOException {
        test("A".repeat(65535));
        test("A".repeat(65536));
        test("\0".repeat(32768));
    }
}
~~~

Lệnh chạy:

~~~bash
javac UtfLengthLimitDemo.java
java UtfLengthLimitDemo
~~~

Stdout:

~~~text
written=65537
too long
too long
~~~

Giá trị **65.537** gồm **65.535 byte payload + 2 byte prefix**. Với String vượt giới hạn, DataOutputStream.writeUTF từ chối thay vì ghi một chuỗi có tiền tố không thể biểu diễn đủ độ dài.

## 7. Lỗi đọc: UTFDataFormatException, EOFException và IOException

**DataInputStream.readUTF()** có thể thất bại do nhiều nguyên nhân khác nhau:

| Tình huống | Ngoại lệ/hiện tượng | Giải thích |
| --- | --- | --- |
| Payload không hợp lệ theo decoder modified UTF-8 | **UTFDataFormatException** | Dạng mã hóa sai, thiếu byte continuation hoặc byte mở đầu không chấp nhận |
| File/socket hết trước khi nhận đủ 2 byte prefix | **EOFException** | Không đọc đủ chiều dài bản ghi |
| Có prefix nhưng byte payload ngắn hơn length đã ghi | **EOFException** | Bản ghi bị cắt |
| Đọc dữ liệu từ luồng nền bị lỗi | **IOException** | Lỗi đọc I/O khác EOF |
| Người đọc dùng nhầm vị trí trong stream | Sai nội dung hoặc ngoại lệ | Prefix có thể bị hiểu nhầm từ byte của trường khác |

**readUTF()** không phải parser có cơ chế tự đồng bộ lại khi dữ liệu lỗi. Nếu byte trên wire bị hỏng hoặc thiếu, các lời đọc tiếp theo có thể bị lệch. Trong ứng dụng thực tế nên dừng xử lý bản ghi lỗi, ghi log có ngữ cảnh phù hợp và quyết định đóng kết nối hoặc phục hồi theo quy tắc giao thức rõ ràng.

Nếu dữ liệu đến từ nguồn không tin cậy, cần bổ sung giới hạn tổng kích thước thông điệp, kiểm tra phiên bản, thứ tự trường và timeout tại tầng mạng. Hai-byte prefix giới hạn riêng mỗi chuỗi nhưng **không tự giới hạn tổng số bản ghi hoặc tổng số byte của toàn stream**.

## 8. Vì sao getBytes(UTF_8) không dùng trực tiếp với readUTF?

Ba luồng xử lý trông giống nhau ở mức người dùng nhưng khác định dạng:

| Cách ghi | Dữ liệu sinh ra | Cách đọc tương ứng |
| --- | --- | --- |
| **DataOutputStream.writeUTF** | Prefix 2 byte + modified UTF-8 | **DataInputStream.readUTF()** |
| **text.getBytes(StandardCharsets.UTF_8)** | Byte UTF-8 chuẩn, không prefix | **new String(bytes, UTF_8)** hoặc decoder chuẩn |
| **OutputStreamWriter(..., UTF_8)** | Byte UTF-8 chuẩn, không prefix tự động | **InputStreamReader(..., UTF_8)** |

Nếu bên gửi ghi **48 69** bằng getBytes UTF-8 nhưng bên nhận gọi **readUTF()**, hai byte đó được diễn giải là **length 0x4869 = 18.537** chứ không phải "Hi"; nếu không đủ các byte payload mà length khai báo, readUTF sẽ ném EOFException.

Nếu bên gửi gọi writeUTF để tạo **00 04 41 C0 80 42** và bên nhận dùng String với UTF-8 chuẩn, đầu đọc không biết phải bỏ qua prefix; hơn nữa **C0 80** không hợp lệ trong UTF-8 chuẩn. Kết quả có thể có ký tự điều khiển hoặc ký tự thay thế thay vì chuỗi gốc.

Vì vậy:

- Dùng **writeUTF/readUTF** chỉ khi cả hai bên thống nhất cùng định dạng đặc thù này.
- Dùng **StandardCharsets.UTF_8** khi giao thức hoặc file yêu cầu UTF-8 chuẩn.
- Không chỉ trao đổi tên charset mà phải mô tả **framing**, prefix, endian, kiểu trường và giới hạn.

Lưu ý các định dạng như JSON, CSV, HTTP hoặc file văn bản UTF-8 thường **không dùng** cặp writeUTF/readUTF.

## 9. Muốn String dài hơn hoặc liên thông nhiều ngôn ngữ?

Một lựa chọn tự thiết kế là **length 4 byte kiểu int big-endian + byte UTF-8 chuẩn**. Đây không phải wire format của readUTF và không nên đọc bằng readUTF.

Ví dụ Java 17+, có giới hạn tối đa 1 MiB cho mỗi bản ghi. Lưu thành **LengthPrefixedUtf8Demo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class LengthPrefixedUtf8Demo {
    private static final int MAX_BYTES = 1024 * 1024;

    static void writeText(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_BYTES) {
            throw new IOException("String exceeds limit");
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String readText(DataInputStream in) throws IOException {
        int count = in.readInt();
        if (count < 0 || count > MAX_BYTES) {
            throw new IOException("Invalid length");
        }
        byte[] bytes = new byte[count];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            writeText(out, "Hello UTF-8");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            System.out.println(readText(in));
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac LengthPrefixedUtf8Demo.java
java LengthPrefixedUtf8Demo
~~~

Stdout:

~~~text
Hello UTF-8
~~~

Ví dụ quy định **int chiều dài tính theo byte UTF-8**, sau đó ghi đúng nội dung UTF-8. **readFully** phải lấy đủ số byte hoặc báo lỗi. Nó dùng String UTF-8 thông thường, không dùng modified UTF-8.

**Bảo mật và tính chặt chẽ:** phải kiểm tra chiều dài trước khi cấp phát, không cho phép độ dài âm, không nhận kích thước tùy ý từ nguồn chưa tin cậy. **new String(bytes, UTF_8)** thường thay thế chuỗi byte không hợp lệ; nếu giao thức phải **từ chối** mọi UTF-8 lỗi, dùng **CharsetDecoder** với **CodingErrorAction.REPORT**.

Với văn bản thông thường không cần length prefix, **BufferedReader/BufferedWriter** và charset rõ ràng thường hợp lý hơn. Với dữ liệu nhị phân dạng record, nên ghi rõ version và định dạng framing cho mọi client.

## 10. Dùng Data Streams cùng buffered streams và quản lý tài nguyên

Với file nhị phân, có thể ghép các lớp:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(1);
    out.writeUTF("Hello");
}
~~~

Đọc theo đúng thứ tự:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int version = in.readInt();
    String message = in.readUTF();
}
~~~

Hai đoạn là **mảnh minh họa**, giả định biến **path** kiểu Path và đã import các lớp **java.io** cùng **java.nio.file** cần dùng. **DataOutputStream/DataInputStream** đảm nhận format nhị phân; **BufferedOutputStream/BufferedInputStream** chỉ thêm vùng đệm để giảm thao tác I/O nhỏ.

Lớp bọc ngoài cùng có thể đóng luồng nền khi kết thúc khối **try-with-resources**. Nếu luồng nền thuộc thành phần khác hoặc là **System.out**, không tự đóng khi phần mềm vẫn còn cần dùng nó.

**flush()** trên output giúp đẩy byte từ buffer Java xuống luồng nền; nó **không đồng nghĩa** với fsync bền vững trên đĩa hay xác nhận rằng đầu nhận đã xử lý thông điệp. Khi cần xác nhận, dùng giao thức hoặc API durability phù hợp.

Không được tự đọc 2 byte prefix rồi gọi **readUTF()** trên phần payload còn lại: **readUTF() luôn đòi thêm một prefix mới tại vị trí hiện tại**, vì vậy sẽ đọc sai.

## 11. Lỗi phổ biến và cách phòng tránh

1. **Nghĩ writeUTF tương đương UTF-8 chuẩn.** Sai: có prefix và modified UTF-8.
2. **Dùng readUTF với getBytes(UTF_8).** Reader diễn giải byte đầu làm length, có thể EOF.
3. **Dùng String.length() làm số byte payload.** Mỗi UTF-16 code unit dùng 1, 2 hoặc 3 byte.
4. **Quên tối đa 65.535 byte encoded.** Chuỗi có ít ký tự hơn vẫn có thể vượt giới hạn.
5. **Quên hai byte length không tính vào payload.** Tổng kích thước bản ghi là **2 + length**.
6. **Giả định modified UTF-8 dùng 4 byte cho code point bổ sung.** Nó mã hóa hai surrogate riêng, thường tổng 6 byte.
7. **Ghi sai NUL.** writeUTF tạo **C0 80**, khác UTF-8 chuẩn **00**.
8. **Dùng length theo little-endian khi bên đọc chờ big-endian.** Hai phía phải tuân thủ đúng định dạng.
9. **Đọc sai thứ tự field.** Khi ghi writeInt rồi writeUTF thì phải đọc readInt rồi readUTF.
10. **Bỏ qua EOFException/UTFDataFormatException.** Bản ghi lỗi không phải chuỗi hợp lệ.
11. **Không giới hạn tổng số bản ghi/tổng byte mạng.** Giới hạn writeUTF chỉ áp dụng cho một payload chuỗi.
12. **Dùng readUTF làm decoder của file UTF-8 thông thường.** Nó không phù hợp với định dạng text thuần.
13. **Hiểu flush là đã đồng bộ xuống đĩa.** Tầng đệm Java và cơ chế durability khác nhau.
14. **Dùng writeUTF cho giao thức liên thông mà không mô tả format.** Client nền tảng khác có thể chỉ hỗ trợ UTF-8 chuẩn.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Kết quả hex của writeUTF("Hi") là gì?  
**Đáp:** **00 02 48 69**, gồm 2-byte length và 2-byte payload.

**Câu 2.** Ký tự NUL được writeUTF mã hóa thế nào?  
**Đáp:** **C0 80**, trong khi UTF-8 chuẩn dùng **00**.

**Câu 3.** Vì sao U+1F600 có thể chiếm 6 byte trong modified UTF-8?  
**Đáp:** Java String dùng hai UTF-16 surrogate, mỗi code unit mã hóa 3 byte.

**Câu 4.** writeUTF với "A".repeat(65535) có thành công không, tổng số byte ghi?  
**Đáp:** Có, tổng **65.537 byte** gồm 2-byte prefix và 65.535-byte payload.

**Câu 5.** Vì sao "é".repeat(32768) không ghi được bằng writeUTF?  
**Đáp:** Payload 65.536 byte vượt giới hạn 65.535 byte.

**Câu 6.** Khi readUTF gặp payload chưa đủ độ dài mà prefix chỉ định, thường báo gì?  
**Đáp:** **EOFException**.

**Câu 7.** Ghi writeInt(7), writeUTF("OK"), writeBoolean(true) thì đọc theo thứ tự nào?  
**Đáp:** **readInt(), readUTF(), readBoolean()**.

**Câu 8.** Một giao thức HTTP yêu cầu UTF-8 chuẩn có nên thay bằng writeUTF không?  
**Đáp:** Không, trừ khi chính giao thức quy định đặc biệt dùng 2-byte length + Java modified UTF-8.

## 13. Tổng kết

**DataOutputStream.writeUTF()** tạo bản ghi gồm **2 byte unsigned big-endian length** và **payload modified UTF-8** dài đúng số byte đó. **DataInputStream.readUTF()** là phương thức đối xứng, đọc prefix và giải mã để khôi phục Java String.

Điểm dễ nhầm nhất: modified UTF-8 **mã hóa NUL thành C0 80**, **mã hóa mỗi UTF-16 code unit** và có thể dùng **6 byte cho một code point bổ sung**, khác UTF-8 chuẩn. Payload tối đa **65.535 byte**. Hãy dùng cặp phương thức này khi cả hai phía thống nhất định dạng Java binary; với text UTF-8 thông thường hoặc String lớn hơn giới hạn, chọn codec/framing khác theo giao thức.

### Tham khảo chính thức

- [Oracle Java SE 17 — DataOutput.writeUTF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html#writeUTF(java.lang.String)): cấu trúc và cách mã hóa.
- [Oracle Java SE 17 — DataInput.readUTF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html#readUTF()): quy tắc đọc và các ngoại lệ.
- [Oracle Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): luồng ghi dữ liệu có kiểu.
- [Oracle Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): luồng đọc dữ liệu có kiểu.
- [Oracle Java SE 17 — UTFDataFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html): lỗi chuỗi modified UTF-8.
