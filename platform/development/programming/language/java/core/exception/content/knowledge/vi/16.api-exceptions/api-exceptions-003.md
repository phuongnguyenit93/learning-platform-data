# EOFException và xử lý dữ liệu kết thúc sớm trong Java

> **Java Core – Exception** · Nhóm: **Ngoại lệ API** · Trọng tâm: phân biệt kết thúc stream bình thường với dữ liệu bị cắt giữa cấu trúc/bản ghi, đọc chính xác số byte cần thiết và giữ nguyên lỗi khi xử lý tệp hoặc luồng nhị phân. Ví dụ hoàn chỉnh tương thích **Java 17+**.

## 1. Hiểu đúng EOF và EOFException

**EOF** là viết tắt của *end of file*, nói rộng hơn là **đã tới cuối nguồn dữ liệu đầu vào**. Một nguồn có thể là tệp, bộ nhớ, socket hoặc luồng được bọc qua API khác.

`java.io.EOFException` là một **checked exception**, kế thừa `IOException`. Nó thường được các API đọc dữ liệu có cấu trúc phát sinh khi **số byte còn lại không đủ để hoàn tất thao tác đọc được yêu cầu**.

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        └── java.io.EOFException
~~~

Điều dễ nhầm nhất là **“đến cuối stream” không phải lúc nào cũng là exception**.

~~~java
InputStream in = new ByteArrayInputStream(new byte[] {65});
System.out.println(in.read()); // 65
System.out.println(in.read()); // -1: đã tới EOF, không tự ném EOFException.
~~~

Đây là đoạn minh họa cần import `InputStream` và `ByteArrayInputStream`, có thể đặt trong method khai báo/handle `IOException`. Với `InputStream.read()`, **`-1` là giá trị báo EOF**, còn byte thực tế được trả về dưới dạng số nguyên trong khoảng 0–255.

Trái lại:

~~~java
DataInputStream in =
        new DataInputStream(new ByteArrayInputStream(new byte[] {1, 2}));
int value = in.readInt(); // EOFException: readInt cần 4 byte.
~~~

Đây là đoạn minh họa cần import `DataInputStream`, `ByteArrayInputStream` và handle IOException. `readInt()` yêu cầu **đủ bốn byte** để tạo một giá trị `int`. Nguồn chỉ có hai byte nên việc kết thúc sớm là **vi phạm yêu cầu của chính thao tác đọc**.

**Quy tắc nhớ:** Nếu API đang hỏi “có thêm byte nào không?”, EOF có thể được báo bằng `-1` hoặc một sentinel khác. Nếu API đang yêu cầu **một giá trị/bản ghi hoàn chỉnh với kích thước xác định**, hết dữ liệu **giữa chừng** thường phải là lỗi và có thể xuất hiện dưới dạng `EOFException`.

## 2. Phân biệt những API báo cuối dữ liệu theo cách khác nhau

Không được suy rằng tất cả method tên `read` đều có cùng hợp đồng EOF.

| API | Khi tới cuối dữ liệu | Ý nghĩa thực tế |
| --- | --- | --- |
| `InputStream.read()` | Trả `-1` | Không còn byte đơn tiếp theo |
| `InputStream.read(byte[])` | Có thể trả `-1`; khi chưa EOF có thể trả ít byte hơn buffer | Một lần đọc không đảm bảo lấp đầy buffer |
| `Reader.read()` | Trả `-1` | Không còn ký tự tiếp theo |
| `BufferedReader.readLine()` | Trả `null` nếu không còn dòng nào | Một dòng cuối không có ký tự xuống dòng vẫn có thể được trả bình thường |
| `DataInputStream.readInt()` | Ném `EOFException` nếu không đủ 4 byte | Cần đủ một giá trị `int` nhị phân |
| `DataInputStream.readUnsignedByte()` | Ném `EOFException` nếu không còn byte | Cần đúng 1 byte |
| `DataInputStream.readFully(byte[])` | Ném `EOFException` nếu không đọc đủ kích thước mảng | Cần đủ toàn bộ buffer |
| `DataInputStream.readUTF()` | Có thể ném `EOFException` nếu dữ liệu UTF theo định dạng này bị cắt | Cần header độ dài và đủ phần nội dung |
| `Scanner.nextInt()` | Có thể ném `NoSuchElementException` khi không còn token phù hợp | API phân tích token, không dùng EOFException làm quy tắc chung |

**Quan trọng:** `InputStream.read(byte[])` có thể trả một số dương **nhỏ hơn kích thước buffer mà chưa tới EOF**. Một lần đọc “thiếu byte” chưa chứng minh dữ liệu đã kết thúc; API có thể trả phần còn lại trong lần đọc sau.

Một số API khác, như `InputStream.readNBytes(len)`, có hợp đồng trả **mảng ngắn hơn độ dài mong muốn khi tới EOF** chứ không nhất thiết ném EOFException. Hãy đọc đúng **Javadoc của method đang sử dụng**.

## 3. Khi nào EOF là bình thường, khi nào là lỗi?

Tình huống phụ thuộc **giao thức dữ liệu (data format/protocol)** chứ không chỉ loại stream.

### 3.1. EOF bình thường ở ranh giới hợp lệ

Giả sử tệp chứa dãy byte tùy ý và nhiệm vụ là đọc tới cuối:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    int next;
    while ((next = in.read()) != -1) {
        process(next);
    }
}
~~~

Đây là đoạn minh họa cần import `InputStream`, `Files`, `Path`; `path` và `process` phải được định nghĩa, method phải handle/declare IOException. Trong bài toán này, `read() == -1` là điều kiện **kết thúc vòng lặp bình thường**, không phải dữ liệu hỏng.

### 3.2. EOF bất thường giữa một giá trị bắt buộc

Một tệp được định nghĩa luôn chứa **một mã int 4 byte**, nhưng thực tế chỉ còn 2 byte:

~~~java
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {0, 1}))) {
    in.readInt(); // Ném EOFException.
}
~~~

Đây là đoạn minh họa cần import các lớp tương ứng và handle IOException. Vì format **yêu cầu một giá trị đầy đủ**, không thể lấy 2 byte hiện có rồi tự coi là một `int` hợp lệ.

### 3.3. EOF ở đầu bản ghi khác EOF ở giữa bản ghi

Xét giao thức bản ghi:

~~~text
Mỗi record = [4 byte độ dài payload] [payload đúng số byte đã công bố]
Các record nối tiếp nhau; không có record-count ở đầu stream.
~~~

Có ba trường hợp:

- **Không còn byte nào ngay trước header của record tiếp theo:** có thể coi là **clean EOF**, nghĩa là đã hết các bản ghi trọn vẹn.
- **Đã đọc byte đầu của header nhưng còn thiếu byte để đủ 4:** **truncated header**. Đây là dữ liệu lỗi.
- **Header hợp lệ báo payload dài N byte nhưng nguồn hết khi chưa đọc đủ N:** **truncated payload**. Đây là dữ liệu lỗi.

Nếu format có **record count bắt buộc**, ví dụ đã công bố 10 bản ghi mà mới nhận 9, thì EOF ngay ở ranh giới sau bản ghi thứ 9 vẫn là **lỗi so với giao thức ấy**. Clean EOF hay unexpected EOF **không thể quyết định chỉ bằng việc thấy stream đã hết**.

## 4. Hợp đồng DataInputStream và các phương thức thường ném EOFException

`DataInputStream` cung cấp các phương thức đọc **kiểu primitive nhị phân** và dữ liệu theo format cụ thể. Đối với mỗi method, số byte cần đọc phụ thuộc định dạng.

| Method | Yêu cầu dữ liệu | Khi thiếu byte |
| --- | --- | --- |
| `readBoolean()` | 1 byte | `EOFException` |
| `readByte()` / `readUnsignedByte()` | 1 byte | `EOFException` |
| `readShort()` / `readUnsignedShort()` | 2 byte | `EOFException` |
| `readChar()` | 2 byte | `EOFException` |
| `readInt()` / `readFloat()` | 4 byte | `EOFException` |
| `readLong()` / `readDouble()` | 8 byte | `EOFException` |
| `readFully(buffer)` | Đủ số byte mà buffer yêu cầu | `EOFException` |
| `readUTF()` | Header độ dài và dữ liệu theo modified UTF-8 | `EOFException` nếu chưa đủ; `UTFDataFormatException` với mã hóa không hợp lệ theo định dạng |

Lưu ý: đây là các thao tác đọc theo **format DataInput**, không phải việc đọc các chuỗi chữ số dưới dạng text. Tệp chứa ký tự `'1'`, `'2'`, `'3'`, `'4'` không tự động có nghĩa là số nguyên 1234 khi gọi `readInt()`. Method đọc bốn byte theo biểu diễn nhị phân big-endian của DataInput.

### 4.1. readInt đọc đủ bốn byte, không chấp nhận giá trị “nửa int”

~~~java
byte[] twoBytes = {1, 2};
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(twoBytes))) {
    in.readInt();
} catch (EOFException ex) {
    System.out.println("Truncated integer");
}
~~~

Đây là đoạn minh họa cần import `DataInputStream`, `ByteArrayInputStream`, `EOFException` và handle/declare IOException phù hợp. Khi gọi `readInt()`, hai byte đã có **không đủ** để tạo int.

**Không nên dùng** catch EOFException và tự thay bằng 0, vì dữ liệu 2 byte chưa thể hiện ý nghĩa số 0 trong giao thức. Nếu format cho phép giá trị thiếu, phải có quy tắc biểu diễn giá trị thiếu tường minh.

### 4.2. readFully khác read(byte[])

~~~java
byte[] data = new byte[8];
in.readFully(data);
~~~

Đây là đoạn minh họa cần `in` thuộc kiểu DataInputStream và xử lý IOException. `readFully(data)` yêu cầu **đủ 8 byte**, lặp việc đọc khi cần; nếu EOF xảy ra trước đó, method ném EOFException.

Trong khi đó:

~~~java
int n = in.read(data);
~~~

một lần đọc qua InputStream/DataInputStream có thể trả số lượng **ít hơn 8 nhưng lớn hơn 0**, dù vẫn còn dữ liệu về sau. Vì thế, để đọc một payload có độ dài xác định, `readFully` tránh lỗi phổ biến “gọi read một lần rồi mặc định buffer đã đầy”.

**Thận trọng:** Khi `readFully` đã đọc được một phần rồi gặp EOFException, buffer có thể **đã bị ghi một phần**. Không nên tiếp tục dùng nó như một payload hoàn chỉnh sau catch.

## 5. Chương trình Java 17 hoàn chỉnh: phân biệt clean EOF và truncated data

Tạo tệp **`EarlyEOFExceptionDemo.java`**. Chương trình dùng các byte array trong bộ nhớ để tái tạo **bảy tình huống** không phụ thuộc hệ thống tệp hoặc mạng:

1. Nhiều bản ghi nhị phân hoàn chỉnh rồi tới clean EOF.
2. Stream rỗng: clean EOF trước bản ghi đầu.
3. Payload bị cắt ngắn.
4. Header độ dài bị cắt ngắn.
5. Header có length vượt giới hạn format.
6. Khác biệt `readInt`, `read()` và `readFully` khi hết byte.
7. `readUTF` thành công và đọc chuỗi UTF bị cắt.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EarlyEOFExceptionDemo {
    private static final int MAX_PAYLOAD = 1024;

    private static byte[] frame(String value) throws IOException {
        byte[] payload = value.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);
            out.write(payload);
        }
        return buffer.toByteArray();
    }

    private static byte[] concat(byte[] first, byte[] second) {
        byte[] result = Arrays.copyOf(first, first.length + second.length);
        System.arraycopy(second, 0, result, first.length, second.length);
        return result;
    }

    private static String readRecord(DataInputStream in) throws IOException {
        int first = in.read();
        if (first == -1) {
            return null; // Clean EOF: no header byte consumed.
        }
        // Once the first header byte exists, remaining 3 bytes are required.
        int length = ((first & 0xFF) << 24)
                | (in.readUnsignedByte() << 16)
                | (in.readUnsignedByte() << 8)
                | in.readUnsignedByte();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload); // Throws EOFException for truncated payload.
        return new String(payload, StandardCharsets.UTF_8);
    }

    private static void consume(String label, byte[] input) {
        System.out.println("== " + label + " ==");
        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(input))) {
            int count = 0;
            while (true) {
                String record = readRecord(in);
                if (record == null) {
                    System.out.println("clean-eof after " + count + " record(s)");
                    break;
                }
                System.out.println("record[" + count + "]=" + record);
                count++;
            }
        } catch (EOFException ex) {
            System.out.println("truncated=" + ex.getClass().getSimpleName());
        } catch (IOException ex) {
            System.out.println("io-error=" + ex.getMessage());
        }
    }

    private static void primitiveAndRawRead() throws IOException {
        System.out.println("== primitive and raw read ==");
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(new byte[] {1, 2}))) {
            in.readInt();
        } catch (EOFException ex) {
            System.out.println("readInt=" + ex.getClass().getSimpleName());
        }

        try (ByteArrayInputStream in =
                     new ByteArrayInputStream(new byte[] {65})) {
            System.out.println("read-first=" + in.read());
            System.out.println("read-end=" + in.read());
        }

        byte[] target = new byte[4];
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(new byte[] {65, 66}))) {
            in.readFully(target);
        } catch (EOFException ex) {
            System.out.println("readFully=" + ex.getClass().getSimpleName());
            System.out.println("partial-buffer=" + Arrays.toString(target));
        }
    }

    private static void utfSample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("Hello");
        }
        byte[] encoded = bytes.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(encoded))) {
            System.out.println("readUTF-ok=" + in.readUTF());
        }
        byte[] truncated = Arrays.copyOf(encoded, encoded.length - 1);
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            in.readUTF();
        } catch (EOFException ex) {
            System.out.println("readUTF-short=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        consume("complete records", concat(frame("A"), frame("BC")));
        consume("empty stream", new byte[0]);
        byte[] original = frame("HELLO");
        consume("truncated payload",
                Arrays.copyOf(original, original.length - 2));
        consume("truncated header", new byte[] {0, 0});
        consume("invalid length", new byte[] {0, 0, 8, 0});
        primitiveAndRawRead();
        utfSample();
    }
}
~~~

### Cách biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 EarlyEOFExceptionDemo.java
java EarlyEOFExceptionDemo
~~~

**Stdout chính xác đã được kiểm chứng bằng việc biên dịch và thực thi:**

~~~text
== complete records ==
record[0]=A
record[1]=BC
clean-eof after 2 record(s)
== empty stream ==
clean-eof after 0 record(s)
== truncated payload ==
truncated=EOFException
== truncated header ==
truncated=EOFException
== invalid length ==
io-error=invalid frame length: 2048
== primitive and raw read ==
readInt=EOFException
read-first=65
read-end=-1
readFully=EOFException
partial-buffer=[65, 66, 0, 0]
readUTF-ok=Hello
readUTF-short=EOFException
~~~

Chương trình không cần tệp thật, không mở socket và không dựa trên message của EOFException do JVM tạo ra. Do đó stdout minh họa các nhánh lỗi một cách nhất quán. Nếu chạy trên hệ thống có các cờ JVM hoặc phiên bản khác, cú pháp và hợp đồng API vẫn cần đối chiếu Javadoc tương ứng; ví dụ đã được kiểm chứng cụ thể với biên dịch `--release 17`.

## 6. Cách đọc record có length-prefix mà không nuốt dữ liệu bị cắt

Tâm điểm của chương trình là:

~~~java
private static String readRecord(DataInputStream in) throws IOException {
    int first = in.read();
    if (first == -1) {
        return null; // Chưa tiêu thụ byte header nào: clean EOF.
    }

    int length = ((first & 0xFF) << 24)
            | (in.readUnsignedByte() << 16)
            | (in.readUnsignedByte() << 8)
            | in.readUnsignedByte();

    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("invalid frame length: " + length);
    }

    byte[] payload = new byte[length];
    in.readFully(payload);
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

Đây là **phương thức trích từ chương trình đầy đủ**, cần các import và hằng `MAX_PAYLOAD` tương ứng.

### 6.1. Đọc byte đầu riêng để phân biệt clean EOF

Tại thời điểm chuẩn bị đọc một record mới, `in.read()` trả `-1` nghĩa là **chưa có byte nào của header được tiêu thụ**. Với giao thức “nhiều record cho đến hết stream” trong ví dụ, đó là ranh giới hợp lệ để dừng vòng lặp.

Phương thức trả `null` để biểu thị **không có record tiếp theo**. Vì payload được chuyển thành String bằng `new String(...)`, một record có payload độ dài 0 sẽ trả chuỗi rỗng `""`, **khác null** và không bị nhầm thành EOF.

Nếu format cho phép giá trị payload là null theo cách khác, nên sử dụng kiểu kết quả có trạng thái rõ ràng (ví dụ một wrapper có `present`, sealed result hoặc một dạng sentinel không xung đột), thay vì đánh đồng null dữ liệu với null kết thúc.

### 6.2. Sau byte đầu, các byte header còn lại là bắt buộc

Khi `first != -1`, một bản ghi **đã bắt đầu**. Ba byte độ dài còn lại được đọc bằng `readUnsignedByte()`; method này ném EOFException nếu không lấy được byte bắt buộc. Vì vậy input `{0, 0}` cho kết quả:

~~~text
== truncated header ==
truncated=EOFException
~~~

Nếu đơn giản gọi `readInt()` cho cả header rồi bắt EOFException và “ngừng đọc bình thường”, bạn sẽ không phân biệt được **stream rỗng/clean EOF** với **header đã bắt đầu nhưng bị cắt**. Phân biệt ấy là lý do phải đọc byte đầu trước.

Lưu ý về biểu thức ghép độ dài: `read()` trả một giá trị nguyên 0–255, nên code dùng `first & 0xFF` và dịch bit theo định dạng **big-endian** tương ứng với `DataOutputStream.writeInt`. Với bit dấu cao nhất, kết quả `int` có thể âm; bộ kiểm tra giới hạn sẽ từ chối.

### 6.3. Giới hạn độ dài trước khi cấp phát buffer

Header có bốn byte là một số nguyên 32-bit. Nếu tin tưởng mù quáng mọi length từ nguồn không đáng tin, chương trình có thể cố tạo một mảng rất lớn, gây **cạn bộ nhớ** hoặc từ chối dịch vụ.

Ví dụ bảo vệ:

~~~java
if (length < 0 || length > MAX_PAYLOAD) {
    throw new IOException("invalid frame length: " + length);
}
~~~

Giao thức minh họa đặt giới hạn `MAX_PAYLOAD = 1024`. Header `{0,0,8,0}` đại diện độ dài 2048, nên in:

~~~text
io-error=invalid frame length: 2048
~~~

Đây là **length không hợp lệ**, chưa phải EOFException: parser từ chối ngay trước khi đọc payload. Trong hệ thống thực tế, giá trị giới hạn cần dựa vào format, ngân sách bộ nhớ và rủi ro an ninh, không dùng mặc định 1024 cho mọi ứng dụng.

### 6.4. readFully giúp phát hiện payload thiếu byte

Sau khi kiểm tra length, code tạo buffer đúng kích thước và gọi:

~~~java
byte[] payload = new byte[length];
in.readFully(payload);
~~~

Nếu header nói payload phải dài 5 byte nhưng stream chỉ còn 3 byte, `readFully` ném EOFException. Ví dụ đã tạo record `"HELLO"` rồi cắt mất hai byte cuối để kiểm tra đúng điều kiện này.

**Không được** tự dùng 3 byte đã có làm record hợp lệ, vì như vậy vi phạm format. Nếu ứng dụng cần khôi phục dữ liệu phần nào, hãy thiết kế **chế độ recovery riêng**, với logging và giới hạn rõ, thay vì tráo đường lỗi thành thành công.

## 7. ReadFully có thể đã ghi một phần vào buffer trước khi ném lỗi

Trong chương trình:

~~~java
byte[] target = new byte[4];
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {65, 66}))) {
    in.readFully(target);
} catch (EOFException ex) {
    System.out.println("partial-buffer=" + Arrays.toString(target));
}
~~~

Đây là đoạn trích từ phương thức runnable. Buffer được tạo có bốn phần tử ban đầu bằng 0. Hai byte `65` và `66` được copy trước khi gặp EOF. Kết quả trên JVM đã chạy:

~~~text
readFully=EOFException
partial-buffer=[65, 66, 0, 0]
~~~

**Ý nghĩa:** Có exception không đồng nghĩa buffer được **rollback** về trạng thái ban đầu. Nó có thể chứa dữ liệu một phần, kể cả khi `readFully` đã báo thất bại.

Nguyên tắc xử lý:

1. Chỉ công bố hoặc commit dữ liệu khi **toàn bộ record đã được đọc và xác thực**.
2. Nếu đọc lỗi, đánh dấu buffer/record hiện tại là **không hoàn chỉnh**, không tái sử dụng như giá trị đúng.
3. Khi cần retry, phải biết **vị trí stream đã tiêu thụ bao nhiêu byte**; một lần đọc lỗi có thể đã làm con trỏ di chuyển.
4. Không mặc định có thể retry lại cùng phương thức trên cùng stream mà dữ liệu tự quay về đầu record.
5. Nếu cần phục hồi, phải có format cho phép xác định ranh giới record, offset, checksum hoặc thao tác seek/reopen phù hợp.

Một lời gọi `readFully` giúp bảo đảm **hoặc đọc đủ, hoặc báo lỗi**; nó **không bảo đảm tính nguyên tử của side effect lên mảng hoặc trạng thái stream**.

## 8. readUTF và EOFException: không nhầm với UTF-8 thông thường

`DataOutputStream.writeUTF(String)` và `DataInputStream.readUTF()` dùng **modified UTF-8 với một header độ dài unsigned short**, khác với việc đơn giản ghi các byte `String.getBytes(StandardCharsets.UTF_8)`.

Trong chương trình:

~~~java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
try (DataOutputStream out = new DataOutputStream(bytes)) {
    out.writeUTF("Hello");
}
byte[] encoded = bytes.toByteArray();
~~~

Sau đó `readUTF()` trên toàn bộ encoded data trả `"Hello"`. Nếu bỏ đi một byte cuối, `readUTF()` không còn đủ phần nội dung được khai báo và ném `EOFException`:

~~~text
readUTF-ok=Hello
readUTF-short=EOFException
~~~

### Trường hợp đọc UTF hỏng nhưng không phải thiếu byte

Nếu dữ liệu có đủ số byte mà **mã hóa modified UTF-8 không hợp lệ**, API có thể ném `UTFDataFormatException`, cũng là một dạng `IOException`. Đây là lỗi **format encoding**, cần phân biệt với thiếu byte.

Ngoài ra, header độ dài của `writeUTF/readUTF` giới hạn số byte theo format (tối đa 65535 byte encoded), không phải một cơ chế để đọc file UTF-8 kích thước tùy ý.

**Khi xây dựng giao thức riêng**, nếu muốn dùng UTF-8 tiêu chuẩn, có thể thiết kế length-prefix theo byte và dùng `StandardCharsets.UTF_8` như ví dụ `readRecord`. Phía ghi/đọc phải thống nhất đúng format. Không ghi bằng `writeUTF` rồi giả định phía đọc dùng `new String(input, UTF_8)` trên toàn bộ byte stream là tương đương.

## 9. Đọc text: BufferedReader.readLine trả null, không mặc định ném EOFException

Với tệp văn bản phân dòng:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

Đây là mã minh họa cần import `BufferedReader`, `Files`, `Path`, `StandardCharsets`, và khai báo/handle IOException. `processLine` phải có định nghĩa.

Theo hợp đồng `readLine()`:

- Khi có dòng, trả một String (có thể rỗng).
- Nếu stream đã hết và **không còn ký tự nào để tạo dòng mới**, trả `null`.
- Một dòng cuối không có ký tự xuống dòng **vẫn được trả là một dòng**, không bị tự loại bỏ.
- Một lỗi I/O thực sự vẫn có thể ném IOException, không phải lúc nào cũng được biểu diễn bằng null.

Nếu format yêu cầu chính xác 10 dòng mà chỉ nhận 9, `readLine() == null` ở dòng thứ 10 là một **vi phạm format**, dù API báo EOF bằng null thay vì tự ném EOFException. Caller phải quyết định xử lý, ví dụ:

~~~java
String header = reader.readLine();
if (header == null) {
    throw new EOFException("missing required header line");
}
~~~

Đây là đoạn minh họa với biến `reader` phù hợp và import `EOFException`. Ở đây **ứng dụng chủ động ném EOFException** để diễn đạt “thiếu dòng bắt buộc”, không phải `readLine()` tự ném EOFException.

## 10. InputStream.read(byte[]) đọc thiếu không nhất thiết do EOF

Một nhầm lẫn phổ biến:

~~~java
byte[] buffer = new byte[1024];
int n = input.read(buffer);
if (n < buffer.length) {
    // Sai nếu mặc định dữ liệu đã hết / bị hỏng.
}
~~~

Đây là đoạn minh họa cần biến `input` kiểu InputStream và xử lý IOException. Một lần `read(buffer)` có thể trả **ít byte hơn yêu cầu**, nhất là trên luồng mạng hoặc luồng được bọc, trong khi lần đọc tiếp theo vẫn có byte.

Vì vậy:

- `n > 0`: đã đọc được n byte, **chưa kết luận** hết stream chỉ vì n nhỏ hơn buffer.
- `n == -1`: báo EOF theo API của InputStream.
- `n == 0`: với một số overload và trường hợp đặc biệt (như len = 0), có thể không đọc byte nào; xử lý theo Javadoc chính xác.
- Nếu cần đúng N byte, dùng cơ chế **đọc lặp đến đủ N**, như `DataInputStream.readFully`.
- Nếu format cho phép tới EOF thì xử lý sentinel; nếu format yêu cầu N byte, tới EOF trước N là lỗi.

Đừng dựa vào `InputStream.available()` làm “tổng số byte còn lại trong file/stream”. Theo API, đó chỉ là **ước lượng số byte có thể đọc hoặc skip mà không block** trong điều kiện được mô tả; đặc biệt với network stream nó không nói dữ liệu tương lai có tới hay không.

## 11. Đọc từ socket: close, EOF và timeout có nghĩa khác nhau

Trên một stream mạng, việc đọc có thể có những kết quả cần phân biệt:

- **`read() == -1`**: không còn dữ liệu từ đầu vào theo trạng thái stream; trong giao thức TCP, có thể phản ánh bên gửi đã đóng phần gửi dữ liệu một cách bình thường. Nhưng nếu giao thức đang chờ phần còn lại của một message, đó vẫn là **unexpected end** ở tầng protocol.
- **`SocketTimeoutException`**: một thao tác I/O vượt quá thời hạn chờ đã cấu hình. Đây **không đồng nghĩa** bên gửi chắc chắn đóng stream hoặc dữ liệu đã bị cắt vĩnh viễn.
- **`EOFException`**: thường do API cấp cao yêu cầu đọc cấu trúc/giá trị đầy đủ nhưng stream đã hết trước khi đáp ứng yêu cầu.
- **`SocketException`/IOException khác**: lỗi kết nối, reset, vấn đề I/O; không nên tự coi tất cả là EOF.

Ví dụ một peer gửi header độ dài 100 byte, payload mới được 60 byte rồi kết thúc kết nối. Nếu parser dùng `readFully(100 bytes)`, nó báo EOFException vì message **không hoàn chỉnh**. Nếu code chỉ kiểm tra `read() == -1` và coi là kết thúc bình thường, nó có thể vô tình chấp nhận một record bị thiếu.

**Hành động đúng phụ thuộc giao thức**: ghi log packet/frame id, từ chối record, đóng kết nối bị lỗi, cân nhắc retry request **nếu thao tác an toàn/idempotent**, hoặc bắt đầu lại từ checkpoint khi format hỗ trợ. Không retry vô hạn chỉ vì thấy EOF.

## 12. Những trạng thái parser nên phân biệt rõ

Một parser record thường có những trạng thái:

| Trạng thái | Dữ liệu đã nhận | Kết quả phù hợp |
| --- | --- | --- |
| Chưa bắt đầu record; stream báo EOF | Không có byte header mới | Clean EOF nếu format cho phép |
| Header đọc chưa đủ | Một phần header | Lỗi truncated header |
| Header hoàn tất nhưng length âm/vượt giới hạn | Đủ header nhưng giá trị sai | Lỗi format/validation |
| Payload chưa đủ so với length | Một phần payload | Lỗi truncated payload |
| Payload đủ nhưng encoding sai | Đủ byte, decode không hợp lệ | Lỗi format encoding |
| Payload hợp lệ | Đủ header và đủ nội dung | Commit/emit một record |
| Stream hết sau record hoàn chỉnh | Đang ở ranh giới tiếp theo | Clean EOF nếu đủ số record yêu cầu |

Bảng nêu **một mô hình parser ứng dụng**; không khẳng định rằng Java có sẵn đúng những class exception riêng cho mọi hàng. Một số hệ thống tạo custom exception như `TruncatedRecordException`, `InvalidLengthException` và giữ cause là EOFException/IOException gốc để caller có chính sách khác nhau.

### 12.1. Không áp dụng một chính sách lỗi cho mọi hoàn cảnh

Tùy ứng dụng:

- **Tệp cấu hình/bản ghi nghiệp vụ:** dữ liệu thiếu nên fail fast, không trả một object chưa được kiểm chứng.
- **Luồng streaming liên tục:** clean EOF ở ranh giới gói có thể hoàn toàn bình thường.
- **Network request-response:** payload thiếu so với content length có thể là lỗi giao thức cần retry có kiểm soát.
- **Tệp phục hồi/forensic:** có thể lưu phần record hoàn chỉnh cuối cùng, ghi cảnh báo về record bị cắt; không âm thầm xem toàn bộ file là hợp lệ.
- **Tệp append-only khi writer còn hoạt động:** thấy EOF khi đọc chưa chắc writer đã hoàn tất; cần cơ chế phối hợp/tailing và quy tắc commit record, không tự gán kết luận từ API read.

Thiết kế format cần nói rõ **khi nào EOF hợp lệ**. Nếu không có mô tả đó, catch EOFException có nguy cơ che mất hỏng dữ liệu.

## 13. Cách catch EOFException đúng vị trí

Vì `EOFException extends IOException`, cần đặt handler cụ thể **trước handler tổng quát** khi có cả hai:

~~~java
try {
    readExpectedRecord();
} catch (EOFException ex) {
    reportTruncatedData(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
~~~

Đây là mẫu minh họa, các hàm phải được định nghĩa. Nếu đặt `catch (IOException)` trước `catch (EOFException)` trong cùng chuỗi, nhánh EOFException bị bao phủ và **compiler sẽ từ chối** do handler không thể tới được.

Một anti-pattern nguy hiểm:

~~~java
while (true) {
    try {
        processNextRecord();
    } catch (EOFException ex) {
        break; // Sai nếu record bị cắt giữa chừng cũng đi qua đây.
    }
}
~~~

Đây là mã minh họa, không phải chương trình độc lập. Nó chỉ hợp lệ khi **hợp đồng của processNextRecord() bảo đảm EOFException chính là sentinel kết thúc giữa hai record**, không thể có dữ liệu cắt ngang. Với DataInputStream.readInt(), EOFException một mình **không thể** phân biệt hết byte ngay trước giá trị và hết byte giữa giá trị.

Cách tốt hơn khi protocol có length-prefix không kèm record count là:
1. Kiểm tra clean EOF tại **điểm bắt đầu header**, chưa tiêu thụ byte.
2. Sau khi record đã bắt đầu, để EOFException lan như một lỗi truncation.
3. Catch EOFException ở **boundary xử lý file/connection**, đánh dấu input bị lỗi, không vô tình tiếp tục record tiếp theo.

Trong chương trình mẫu, `readRecord` trả `null` cho clean EOF, còn ném EOFException khi header/payload bị cắt. Đây là cách tách tình trạng **bình thường** và **bất thường** bằng contract của chính parser.

## 14. EOFException không phải một cách “chữa” dữ liệu thiếu

Một số lựa chọn sai và hậu quả:

~~~java
try {
    return in.readInt();
} catch (EOFException ex) {
    return 0; // Không có nghĩa hai byte thiếu tương đương số 0.
}
~~~

Đây là anti-pattern trong một phương thức trả int, với biến `in` và phần khai báo IOException cần phù hợp. Nếu format quy định đúng 4 byte nhưng chỉ nhận 2, không đủ bằng chứng rằng giá trị là 0.

Mẫu tương tự với chuỗi:

~~~java
byte[] payload = new byte[size];
try {
    in.readFully(payload);
} catch (EOFException ex) {
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

Đây là anti-pattern minh họa với phương thức trả String và các biến/import tương ứng. Buffer có thể còn phần chưa đọc, mặc định zero; convert thành String lúc ấy biến **truncated/corrupted input** thành kết quả nhìn như hợp lệ.

Cách xử lý tốt hơn:

- Ném tiếp exception với bối cảnh (offset, record index, expected/actual bytes nếu biết).
- Chỉ xuất bản **record đã đọc đủ và qua validation**.
- Nếu ứng dụng cho phép khôi phục một phần, cung cấp kết quả recovery **được đánh dấu rõ là không hoàn chỉnh**.
- Khi cần lưu trạng thái, dùng transaction/checkpoint: dữ liệu phần record chưa hoàn thành không được tự động commit.
- Không dùng `EOFException` để thay cho việc thiếu dữ liệu nghiệp vụ có thể xử lý bình thường nếu API đó đã có một kiểu kết quả phù hợp.

## 15. Thiết kế exception có bối cảnh để dễ debug

`EOFException` có thể không mang message đủ chi tiết. Khi gặp dữ liệu bị cắt, caller thường muốn biết:
- Đang đọc **file/stream** nào, từ **offset** nào?
- Đang ở **bản ghi thứ mấy**, phần **header hay payload**?
- Số byte dự kiến là bao nhiêu?
- Đã đọc được bao nhiêu byte trước khi lỗi, nếu có thể biết?
- Có thể retry hoặc resume an toàn không?

Một cách gắn bối cảnh mà vẫn giữ lỗi gốc:

~~~java
try {
    in.readFully(payload);
} catch (EOFException ex) {
    throw new IOException(
            "Truncated payload in record " + recordIndex
                    + ", expected " + payload.length + " bytes",
            ex);
}
~~~

Đây là mã minh họa; cần có các biến và method xử lý IOException phù hợp. Wrapper mới là `IOException` có **cause = EOFException gốc**. Caller có thể log stack trace nguyên nhân cùng thông điệp cấp ứng dụng.

Nếu caller cần bắt riêng **truncated data** như một nhánh hợp đồng ổn định, có thể tạo subclass `IOException` riêng với các trường dữ liệu có cấu trúc. Không nên dựa vào việc so sánh chuỗi message như `"Unexpected EOF"` vì thông điệp có thể thay đổi.

Một nguyên tắc tương tự áp dụng cho `try-with-resources`: nếu thao tác đọc đã thất bại và `close()` cũng thất bại, exception từ close có thể nằm trong `getSuppressed()`. Ghi log toàn bộ Throwable, không chỉ `ex.getMessage()`, giúp giữ cả cause và lỗi cleanup.

## 16. DataInputStream, readUTF và ObjectInputStream: không trộn format

`DataInputStream` và `DataOutputStream` là cặp phù hợp để đọc/ghi primitive binary theo cùng encoding. `ObjectInputStream` và `ObjectOutputStream` dùng một **object serialization stream format** khác, có marker và metadata riêng.

Một số trường hợp đọc object stream đến cuối có thể nhận EOFException. Nhưng không nên suy:

- Cứ `ObjectInputStream.readObject()` ném EOFException là hết một danh sách object hợp lệ.
- Mọi exception khi đọc object đều là EOFException.
- File serialization bị cắt chỉ cần catch EOFException rồi coi là đọc xong.

Ngoài EOFException, object serialization có thể ném `StreamCorruptedException`, `OptionalDataException`, `ClassNotFoundException` hoặc các loại lỗi khác tùy API và dữ liệu. Nếu format không cung cấp **số object, sentinel kết thúc hoặc khung bao rõ ràng**, chỉ dựa vào EOFException để chấp nhận file có thể che trường hợp truncation.

Đối với dữ liệu lâu dài hoặc gửi qua mạng, serialization native của Java có thêm các mối quan tâm về tương thích phiên bản và an toàn. Hãy chọn format/giao thức rõ ràng, có size limit, kiểm tra schema và ranh giới record phù hợp.

### Không đánh đồng UTF-8 và modified UTF-8

Cặp `writeUTF/readUTF` phù hợp với nhau theo Javadoc của DataOutput/DataInput. Nhưng một format tự thiết kế dùng `writeInt(length) + UTF-8 bytes` phải được đọc theo đúng logic length-prefix + UTF-8; không thể tráo `readUTF()` vào đó vì header và kiểu encoding khác.

## 17. Hiệu năng, bộ nhớ và dữ liệu không tin cậy

Khi đọc length-prefix từ nguồn bên ngoài:

1. **Giới hạn kích thước** trước khi cấp phát mảng; tránh length âm hoặc quá lớn.
2. **Giới hạn số bản ghi** và tổng số byte khi cần, không chỉ một record.
3. **Không giữ mọi record trong bộ nhớ** nếu có thể xử lý từng record hoàn chỉnh.
4. **Không cấp phát dựa trên available()** như thể đó là độ dài thật.
5. **Không coi read() trả ít byte hơn yêu cầu là dữ liệu hỏng** khi API cho phép partial read; chỉ xác nhận truncation sau khi thật sự gặp EOF trước độ dài cần.
6. **Kiểm tra encoding** khi đầu vào cần UTF-8 hợp lệ. `new String(bytes, StandardCharsets.UTF_8)` thông thường có thể thay chuỗi byte lỗi bằng ký tự thay thế; nếu format yêu cầu strict UTF-8, dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`.
7. **Tránh infinite retry** trên stream đã EOF. Đọc lại cùng stream có thể tiếp tục trả -1; muốn retry phải có nguồn mới, seek/reopen hoặc cơ chế resume được thiết kế.
8. **Xử lý cancellation/timeout** riêng với lỗi EOF, đặc biệt trong môi trường network.
9. **Đóng stream đúng vòng đời** bằng try-with-resources và bảo toàn exception cleanup/suppressed.
10. **Test hỏng dữ liệu có chủ đích**, không chỉ happy path.

Một header cho phép đọc dữ liệu khổng lồ mà không giới hạn có thể gây lỗi tài nguyên ngay trước khi parser có cơ hội phát hiện payload bị cắt. Do đó validation length và giới hạn tổng là một phần thiết yếu của parser an toàn.

## 18. Những lỗi hiểu sai thường gặp

1. **“Đến EOF luôn ném EOFException.”** Sai: InputStream.read thường trả -1; Reader.readLine trả null.
2. **“EOFException là unchecked.”** Sai: nó kế thừa IOException nên là checked exception.
3. **“Bắt EOFException rồi break mọi vòng lặp đọc record là an toàn.”** Sai nếu thiếu byte giữa header/payload cũng ném EOFException.
4. **“readInt chỉ đọc tới lúc có dữ liệu, có 2 byte cũng ra một số.”** Sai: cần đủ 4 byte.
5. **“readFully ném lỗi nên buffer chắc chắn chưa bị thay đổi.”** Sai: có thể đã đọc một phần.
6. **“Gọi read(byte[]) một lần phải đầy buffer.”** Sai: API có thể trả ít byte hơn độ dài yêu cầu.
7. **“Một lần partial read chứng minh EOF.”** Sai: có thể có byte trong lần đọc tiếp theo.
8. **“available() cho tổng số byte còn lại của stream.”** Sai: không có cam kết đó trong contract tổng quát.
9. **“Cắt header là clean EOF vì vẫn đọc được một phần.”** Sai: nếu record đã bắt đầu thì header thiếu là lỗi.
10. **“Kết thúc ngay sau record hoàn chỉnh luôn là lỗi.”** Không: phụ thuộc giao thức, có thể là ranh giới clean EOF.
11. **“Record-count khai báo 10 nhưng nhận 9 rồi EOF vẫn được coi là đủ.”** Sai theo format có count bắt buộc.
12. **“Có length N, nhận N-1 byte vẫn có thể emit record bình thường.”** Sai nếu format quy định phải đủ N.
13. **“Header length lớn chỉ cần cấp phát rồi đọc thử.”** Nguy hiểm: phải validate giới hạn trước.
14. **“UTFDataFormatException và EOFException là một.”** Sai: một trường hợp sai encoding, trường hợp kia thiếu byte (tùy method và ngữ cảnh).
15. **“readUTF hiểu mọi dạng UTF-8 file.”** Sai: dùng modified UTF-8 và header đặc thù.
16. **“writeInt(length) và writeUTF có cùng header.”** Sai: writeInt dùng 4 byte; writeUTF có header độ dài 2 byte.
17. **“SocketTimeoutException chắc chắn nghĩa là peer đã đóng.”** Sai: timeout là hạn chờ, không đồng nghĩa EOF.
18. **“Catch IOException trước EOFException vẫn bắt EOF riêng được.”** Sai: nhánh cụ thể phía sau sẽ unreachable.
19. **“Nên mặc định trả 0 khi thiếu byte cho int.”** Sai: đang hợp thức hóa dữ liệu hỏng.
20. **“Close stream làm dữ liệu đang đọc dở trở nên hợp lệ.”** Sai: cleanup không khôi phục format.
21. **“EOFException có message luôn cố định.”** Sai: đừng phụ thuộc thông điệp JVM/API.
22. **“Nếu readObject ném EOFException thì chắc chắn toàn bộ object stream hợp lệ.”** Sai: format và độ hoàn chỉnh phải được xác định bằng framing/metadata phù hợp.
23. **“Nếu đã catch EOFException thì không cần catch IOException.”** Sai: parser còn có thể gặp lỗi I/O, format hoặc length khác.
24. **“EOF do socket và EOF do đọc tệp nhị phân đều cần cùng cách retry.”** Không: policy phụ thuộc nguồn, side effect và giao thức.
25. **“Truncated record có thể tự coi như record rỗng.”** Sai nếu không có biểu diễn đó trong format.

## 19. Bài tập tự kiểm tra

**Câu 1.** `InputStream in` có một byte, gọi `in.read()` hai lần. Kết quả?

*Đáp án:* Lần đầu trả giá trị byte 0–255, lần thứ hai trả -1 khi EOF; riêng tình huống này không tự ném EOFException.

**Câu 2.** `DataInputStream.readInt()` cần mấy byte, khi chỉ còn hai byte thì sao?

*Đáp án:* Cần bốn byte theo format DataInput; khi thiếu ném EOFException.

**Câu 3.** Giao thức có header 4 byte, stream trống trước khi đọc header: có thể là kết thúc bình thường không?

*Đáp án:* Có, nếu protocol cho phép chuỗi nhiều record kết thúc tại ranh giới chưa bắt đầu record nào. Nếu format bắt buộc phải có ít nhất một record hoặc có record-count chưa đáp ứng thì vẫn là lỗi giao thức.

**Câu 4.** Đã đọc 1 byte header, nhưng stream hết. Có nên dừng vòng lặp bình thường?

*Đáp án:* Không; header đã bắt đầu nhưng chưa hoàn thành, nên phải coi là truncated header.

**Câu 5.** Header báo payload 100 byte, thực tế còn 60 byte. `readFully(payload)` làm gì?

*Đáp án:* Cố đọc đủ rồi ném EOFException khi không đủ; buffer có thể đã chứa 60 byte và không được xem là record hoàn chỉnh.

**Câu 6.** `InputStream.read(buffer)` trả 60 với buffer 100 byte. Có kết luận chắc chắn bị cắt không?

*Đáp án:* Chưa. Một lần đọc có thể trả thiếu khi chưa EOF; cần tiếp tục đọc theo contract để xác định có nhận đủ 100 hay không.

**Câu 7.** Có nên dùng `available() == 0` để kết luận file/socket đã EOF?

*Đáp án:* Không. available() không phải dấu hiệu kết thúc tổng quát cho mọi stream.

**Câu 8.** `readUTF()` khác `new String(bytes, UTF_8)` ở điểm nào?

*Đáp án:* readUTF kỳ vọng header độ dài cùng modified UTF-8 theo DataInput. new String giải mã bytes theo UTF-8 tiêu chuẩn và không tự xử lý header đó.

**Câu 9.** Một dòng text cuối không có ký tự xuống dòng, `readLine()` có trả dòng này không?

*Đáp án:* Có. Chỉ khi không còn ký tự nào cho dòng tiếp theo thì readLine trả null.

**Câu 10.** Chương trình có `catch (IOException)` trước `catch (EOFException)` trong cùng try: kết quả?

*Đáp án:* Lỗi compile-time do catch EOFException bị catch IOException trước bao phủ.

**Câu 11.** Header độ dài bị đọc thành 2048 nhưng format giới hạn 1024: EOFException hay lỗi validation?

*Đáp án:* Lỗi validation length. Ví dụ chính ném IOException với message invalid frame length, trước khi cố đọc payload.

**Câu 12.** Vì sao không nên catch EOFException rồi trả payload thiếu byte như đã đọc đủ?

*Đáp án:* Vì record chưa đáp ứng kích thước bắt buộc; buffer có thể chứa dữ liệu một phần, còn thiếu dữ liệu và chưa qua validation.

**Câu 13.** Peer không phản hồi và `read()` bị timeout có đồng nghĩa peer đóng kết nối?

*Đáp án:* Không. Timeout là điều kiện chờ hết thời hạn, khác với EOF được báo bằng -1 hoặc thiếu byte đã xác định.

**Câu 14.** Khi muốn gửi nguyên vẹn một record chứa nhiều byte UTF-8, nên ghi độ dài theo số ký tự hay số byte?

*Đáp án:* Với giao thức đã quy định payload là mảng UTF-8 bytes, length cần tính bằng **số byte encoded**, không phải số ký tự Unicode trong String.

**Câu 15.** Một parser đã nhận đủ header và payload, sau đó gặp EOF trước header record mới. Có cần ném EOFException?

*Đáp án:* Không nhất thiết. Nếu format cho phép nhiều record nối tiếp đến EOF, đây chính là clean EOF. Nếu còn record bắt buộc theo count, nó là lỗi format.

## 20. Checklist triển khai parser chống EOF ngoài dự kiến

Trước khi đưa một parser vào ứng dụng:

1. **Mô tả format byte-level:** header, byte order, length, encoding, checksum, record count, sentinel kết thúc.
2. **Định nghĩa clean EOF tại ranh giới nào:** trước header hay sau sentinel, hay khi đã đủ record-count?
3. **Dùng API đọc đúng số byte cần:** `readFully` hoặc vòng lặp tương đương, không một lần read may rủi.
4. **Kiểm tra length và giới hạn tài nguyên** trước cấp phát.
5. **Phân biệt lỗi header, payload, encoding, checksum và IO** theo nhu cầu xử lý.
6. **Không emit record một phần** nếu format không cho phép.
7. **Chỉ commit tác động nghiệp vụ sau khi validate record hoàn chỉnh.**
8. **Giữ cause/stack trace và context** khi bọc exception.
9. **Cẩn thận trạng thái stream sau lỗi:** có thể đã tiêu thụ một phần, không tự rewind.
10. **Test empty input, complete input, thiếu 1/2/3 byte header, thiếu payload, invalid length, length 0, nhiều records, trailing bytes, encoding sai, và IO error.**
11. **Test cả đường clean EOF lẫn truncated input**, bảo đảm không đi vào cùng nhánh thành công.
12. **Kiểm tra thời gian chờ và hủy** nếu là stream mạng; không gọi retry vô hạn.
13. **Đóng tài nguyên an toàn** bằng try-with-resources và xem suppressed nếu close cũng lỗi.
14. **Không dựa vào message mặc định** của EOFException để phân loại hành vi.

## 21. Tài liệu Java 17 chính thức

- [Java SE 17 API – EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): ngoại lệ biểu thị kết thúc input trước khi đọc đủ dữ liệu cần thiết.
- [Java SE 17 API – IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): lớp cha checked của EOFException và nhiều lỗi I/O khác.
- [Java SE 17 API – InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read()` trả -1 tại EOF, các overload có thể đọc ít byte hơn yêu cầu.
- [Java SE 17 API – DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): primitive reads, `readFully`, `readUTF`.
- [Java SE 17 API – DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html): mô tả định dạng dữ liệu, `readFully` và các trường hợp EOF.
- [Java SE 17 API – DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): `writeInt`, `writeUTF` tương thích với DataInput.
- [Java SE 17 API – BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` trả null tại cuối input.
- [Java SE 17 API – UTFDataFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html): lỗi không đúng định dạng modified UTF-8.
- [Java SE 17 API – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): để phân biệt lỗi chờ tác vụ bất đồng bộ với EOF trong dữ liệu, khi bài toán có concurrency.
- [JLS Java SE 17 chương 11 – Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): cơ sở checked/unchecked exception.

**Kết luận:** `EOFException` là **checked IOException**, thường báo rằng một API đang yêu cầu một giá trị nhị phân hoàn chỉnh nhưng stream kết thúc trước khi đọc đủ byte. Trong khi đó, `InputStream.read() == -1` hoặc `BufferedReader.readLine() == null` có thể chỉ là EOF **bình thường**. Hãy định nghĩa ranh giới bản ghi, nhận biết **đã bắt đầu header/payload hay chưa**, đọc đúng kích thước bắt buộc, kiểm tra length và chỉ chấp nhận record đã hoàn tất. Không catch EOFException rồi mặc nhiên coi mọi dữ liệu kết thúc sớm là hợp lệ.