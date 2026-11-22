# Stream header và lỗi khi nối tùy tiện nhiều object stream trong Java Serialization

## 1. Vì sao ObjectOutputStream không phải cách “cứ mở thêm là ghi nối”?

Java cung cấp `java.io.ObjectOutputStream` để tuần tự hóa (serialize) đồ thị đối tượng thành một **luồng byte theo giao thức Java Object Serialization**, và `java.io.ObjectInputStream` để đọc lại luồng theo cùng giao thức.

Một luồng đối tượng không chỉ là các byte biểu diễn từng object đặt cạnh nhau. Nó còn mang **stream header**, mô tả class, thông tin định dạng, handles dùng để tham chiếu lại object đã thấy, dấu reset và dữ liệu điều khiển khác.

~~~text
Đúng: MỘT object stream liên tục

OutputStream vật lý
  |
  +-- ObjectOutputStream được tạo một lần
        |
        +-- [stream header]
        +-- [object A / class descriptors / handles]
        +-- [object B / references / metadata]
        +-- [object C ...]
                 |
                 v
       Một ObjectInputStream tương ứng
          readObject() → A
          readObject() → B
          readObject() → C
~~~

Nếu đóng một `ObjectOutputStream` rồi tạo `ObjectOutputStream` khác để **append** vào cuối cùng file, constructor mới sẽ lại ghi **header mới**. Nhưng `ObjectInputStream` đang đọc một object stream liên tục sẽ không tự hiểu header thứ hai là điểm bắt đầu của một stream độc lập.

~~~text
Sai: nối trực tiếp hai object stream có header riêng

[HEADER 1][OBJECT A][HEADER 2][OBJECT B]
          |
          +-- Một ObjectInputStream đọc A thành công
                                  |
                                  +-- đọc tiếp gặp HEADER 2
                                      ở chỗ mong token object
                                      → StreamCorruptedException
~~~

**Ý chính:** phải phân biệt **nhiều object được ghi vào một object stream** với **nhiều object stream độc lập được nối byte tùy tiện**. Hai cấu trúc không có cùng giao thức đọc.

## 2. Stream header được ghi vào lúc nào?

Khi khởi tạo:

~~~java
ObjectOutputStream out = new ObjectOutputStream(rawOutput);
~~~

`ObjectOutputStream` ghi **serialization stream header** vào `rawOutput` trong quá trình khởi tạo. Trong định dạng Java Serialization chuẩn, bốn byte đầu của một stream thông thường là:

~~~text
AC ED 00 05
│     │
│     └── STREAM_VERSION = 0x0005
└──────── STREAM_MAGIC   = 0xACED
~~~

Các hằng số tương ứng nằm trong `java.io.ObjectStreamConstants`. Đây là magic và version của **giao thức Java Serialization**, không phải mã hóa văn bản và cũng không phải header ZIP/GZIP.

Phía đọc:

~~~java
ObjectInputStream in = new ObjectInputStream(rawInput);
~~~

Constructor `ObjectInputStream` đọc/xác minh stream header. Vì vậy:

- Nếu input không bắt đầu bằng header hợp lệ, constructor có thể ném `StreamCorruptedException`.
- Nếu input stream tương tác (ví dụ pipe/network) chưa có đủ byte header, constructor phía đọc **có thể chặn chờ**. Thông thường hãy tạo/phát header ở phía ghi và `flush()` đúng lúc trước khi phía nhận đợi header.
- Nếu đã tạo `ObjectInputStream` và đọc object A thành công, các lời gọi `readObject()` tiếp theo mong **object content token** của **cùng luồng**, không mong một header thứ hai.
- Một lần `ObjectOutputStream.flush()` đẩy byte đang đệm xuống stream bên dưới theo hợp đồng I/O, **không** tạo header mới và **không** đánh dấu một phiên serialization mới.

### Header không phải dấu phân cách từng object

Một object stream thường có **một stream header ở đầu**, không phải một header trước mỗi object:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(destination)) {
    out.writeObject("first");
    out.writeObject("second");
    out.writeObject("third");
}
~~~

Đây là mảnh code minh họa; `destination` là `OutputStream` đã tạo. Cả ba lần `writeObject` dùng **cùng** object stream, vì vậy phía nhận có thể dùng một `ObjectInputStream` gọi `readObject()` ba lần tương ứng.

Ngược lại, tạo ba `ObjectOutputStream` độc lập trên một `OutputStream` vật lý sẽ tạo nhiều đoạn serialization có header riêng. **ObjectInputStream không tự reset parser tại điểm nối đó.**

## 3. Điều gì xảy ra khi append bằng ObjectOutputStream mới?

Mẫu sai phổ biến khi muốn bổ sung object vào file:

~~~java
// Phiên đầu tiên:
try (ObjectOutputStream out = new ObjectOutputStream(
        new FileOutputStream(file))) {
    out.writeObject("alpha");
}

// Phiên tiếp theo: append byte vật lý vào cuối file.
try (ObjectOutputStream out = new ObjectOutputStream(
        new FileOutputStream(file, true))) {
    out.writeObject("beta");
}
~~~

Đây là **mảnh code minh họa lỗi**, với biến `file` kiểu `File` đã có. Hai lần dùng `FileOutputStream` khác nhau và lần thứ hai có `append=true`. Nhưng **`append=true` chỉ nói với hệ thống tệp rằng byte mới được ghi ở cuối file**; nó không nói với `ObjectOutputStream` rằng đang tiếp nối trạng thái serialization của phiên trước.

Nội dung vật lý về mặt ý tưởng:

~~~text
Lần 1:
[AC ED 00 05][serialized "alpha"]

Lần 2:
[AC ED 00 05][serialized "alpha"]
[AC ED 00 05][serialized "beta"]
               ^
     header thứ hai ở giữa file
~~~

Một `ObjectInputStream` mở từ đầu file có thể đọc `"alpha"`. Khi `readObject()` lần nữa, nó gặp byte magic `0xAC` ở vị trí mong đợi một serialization token hợp lệ bên trong stream, và thường ném `StreamCorruptedException` (ví dụ thông báo có thể chứa `invalid type code: AC`).

**Không nên phụ thuộc vào nguyên văn exception message** vì chi tiết thông báo có thể khác giữa JDK/triển khai. Điểm đáng tin là cấu trúc byte đã vi phạm hợp đồng của **một stream liên tục**.

### Trường hợp lỗi xuất hiện ngay trong constructor

Nếu bạn mở một `ObjectInputStream` mới nhưng bắt đầu đọc **giữa file**, tại byte của một object thay vì header, constructor có thể ném `StreamCorruptedException` ngay khi kiểm tra header. Điều này khác với tình huống đọc object đầu thành công rồi mới lỗi ở header thứ hai.

Cả hai bắt nguồn từ cùng sai lầm: **không xác định đúng ranh giới một serialization stream**.

## 4. Mô hình đúng 1: giữ một ObjectOutputStream cho toàn bộ luồng logic

Nếu chương trình chủ động ghi nhiều object trong cùng một phiên, cách đơn giản nhất là tạo writer một lần:

~~~java
try (ObjectOutputStream out =
        new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject("alpha");
    out.writeObject("beta");
    out.writeObject("gamma");
}
~~~

Phía đọc:

~~~java
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(path))) {
    String a = (String) in.readObject();
    String b = (String) in.readObject();
    String c = (String) in.readObject();
}
~~~

Hai đoạn là **mã minh họa**, cần `Path path`, các import tương ứng và xử lý `IOException`/`ClassNotFoundException`.

Ưu điểm:

- Một header thống nhất ở đầu.
- Parser của `ObjectInputStream` đọc đúng stream đang được tiếp nối.
- Handles và thông tin class trong object stream được quản lý nhất quán.
- Dễ dùng khi tạo một snapshot gồm nhiều object biết trước, hoặc khi một process duy trì writer lâu dài.

Hạn chế:

- Nếu JVM thoát và ứng dụng khởi động lại, tạo một `ObjectOutputStream` mới không thể tự khôi phục toàn bộ **trạng thái handle table** của writer trước đó bằng cách chỉ truyền `append=true`.
- Reader phải biết **khi nào dừng**: thường là số object được lưu trong header ứng dụng, một marker cuối có thiết kế rõ ràng, hoặc EOF **chỉ khi giao thức cho phép**.
- Object streams không tự cho phép đọc ngẫu nhiên object thứ 100 bằng một offset tùy ý. Trạng thái handles/descriptors có thể phụ thuộc các object trước.

Nếu mục tiêu là lưu các bản ghi độc lập, appending xuyên nhiều lần khởi động và khôi phục khi dữ liệu cuối bị ghi dở, một định dạng có **record framing rõ ràng** thường dễ vận hành hơn.

## 5. Mô hình đúng 2: nhiều stream độc lập nhưng có framing

Nếu mỗi object/batch phải được serialize độc lập, bạn **có thể** tạo một `ObjectOutputStream` mới cho mỗi batch, **nhưng phải ghi kèm độ dài hoặc cấu trúc phân cách rõ ràng** để phía đọc biết chính xác mỗi segment bắt đầu/kết thúc ở đâu.

Ví dụ định dạng tự thiết kế:

~~~text
[int32 length L1][L1 bytes của ObjectOutputStream #1]
[int32 length L2][L2 bytes của ObjectOutputStream #2]
[int32 length L3][L3 bytes của ObjectOutputStream #3]
~~~

Mỗi segment là **một object stream hợp lệ độc lập**: có header riêng và nội dung riêng. Reader:

1. Đọc độ dài segment.
2. Kiểm tra giới hạn kích thước trước khi cấp phát.
3. Đọc **đúng số byte** của segment đó vào bộ đệm giới hạn.
4. Tạo **một ObjectInputStream riêng** trên segment.
5. Gọi `readObject()` theo số object/schema của segment.
6. Đóng segment reader rồi chuyển segment tiếp theo.

Đó là cách **nối các segment đã được định khung**, chứ không phải nối mù byte rồi đặt một `ObjectInputStream` lên toàn bộ file.

Với dữ liệu không tin cậy, chỉ độ dài segment không đủ để an toàn. Ngoài giới hạn độ dài **compressed/serialized bytes**, phải giới hạn loại class được phép deserialize, độ sâu object graph, số lượng tham chiếu và bộ nhớ theo chính sách ứng dụng.

### Không thể chỉ tạo ObjectInputStream thứ hai trên cùng FileInputStream rồi hy vọng

Nếu `ObjectInputStream` đầu tiên được tạo trên cùng một underlying `InputStream`, implementation có thể đệm hoặc đọc trước một số byte. Vì thế, **không có hợp đồng tổng quát rằng vị trí underlying stream sau một lần `readObject()` là ranh giới an toàn để tạo `ObjectInputStream` kế tiếp**.

Framing theo độ dài với `ByteArrayInputStream`/bounded input là cách làm rõ ràng: mỗi `ObjectInputStream` chỉ nhìn thấy byte của segment thuộc về nó. Khi cần stream lớn không copy toàn bộ vào RAM, dùng bounded input stream và giới hạn dữ liệu cẩn thận.

## 6. Ví dụ Java 17+ chạy độc lập: sai, đúng và framed

Chương trình sau minh họa ba trường hợp với cùng hai chuỗi `"alpha"` và `"beta"`:

- **Đúng — single stream:** một `ObjectOutputStream` ghi hai object; một `ObjectInputStream` đọc hai object.
- **Sai — concatenated streams:** serialize từng object thành một stream riêng rồi nối raw bytes; một `ObjectInputStream` đọc được object đầu nhưng lỗi tại header thứ hai.
- **Đúng — framed independent streams:** mỗi object được serialize thành stream riêng, được đặt sau trường độ dài; mỗi segment có một `ObjectInputStream` riêng.

Chương trình dùng bộ nhớ thay vì file để không phụ thuộc đường dẫn. Lỗi được in theo **tên loại ngoại lệ**, không in thông báo phụ thuộc implementation.

Lưu file `ObjectStreamHeaderDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.StreamCorruptedException;

public class ObjectStreamHeaderDemo {

    private static byte[] serializeOne(String value)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }
        return bytes.toByteArray();
    }

    private static void singleStream()
            throws IOException, ClassNotFoundException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject("alpha");
            out.writeObject("beta");
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            System.out.println("single first=" + in.readObject());
            System.out.println("single second=" + in.readObject());
        }
    }

    private static void badConcatenation()
            throws IOException, ClassNotFoundException {
        byte[] first = serializeOne("alpha");
        byte[] second = serializeOne("beta");

        ByteArrayOutputStream joined = new ByteArrayOutputStream();
        joined.writeBytes(first);
        joined.writeBytes(second);

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(joined.toByteArray()))) {
            System.out.println("concat first=" + in.readObject());

            try {
                in.readObject();
                System.out.println("concat unexpectedly accepted");
            } catch (StreamCorruptedException expected) {
                System.out.println("concat second error="
                        + expected.getClass().getSimpleName());
            }
        }
    }

    private static void framedSegments()
            throws IOException, ClassNotFoundException {
        byte[] first = serializeOne("alpha");
        byte[] second = serializeOne("beta");

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(first.length);
            out.write(first);
            out.writeInt(second.length);
            out.write(second);
        }

        try (DataInputStream source = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            for (int index = 1; index <= 2; index++) {
                int length = source.readInt();

                // Chính sách giới hạn ví dụ: 1 tới 1024 byte/segment.
                if (length <= 0 || length > 1024) {
                    throw new IOException("Invalid segment length");
                }

                byte[] segment = new byte[length];
                source.readFully(segment);

                try (ObjectInputStream in = new ObjectInputStream(
                        new ByteArrayInputStream(segment))) {
                    System.out.println("framed " + index
                            + "=" + in.readObject());
                }
            }
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        byte[] header = serializeOne("x");

        System.out.printf("header=%02X %02X %02X %02X%n",
                header[0] & 0xFF,
                header[1] & 0xFF,
                header[2] & 0xFF,
                header[3] & 0xFF);

        singleStream();
        badConcatenation();
        framedSegments();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectStreamHeaderDemo.java
java ObjectStreamHeaderDemo
~~~

Stdout trên JDK 17+ với định dạng Java Serialization chuẩn:

~~~text
header=AC ED 00 05
single first=alpha
single second=beta
concat first=alpha
concat second error=StreamCorruptedException
framed 1=alpha
framed 2=beta
~~~

Giải thích từng phần:

1. `serializeOne("x")` tạo stream mới, do đó bốn byte đầu là `AC ED 00 05`. Chương trình in hex không phụ thuộc dữ liệu string.
2. `singleStream()` giữ một writer trong cả hai lệnh `writeObject`, cho phép một reader gọi `readObject` hai lần.
3. `badConcatenation()` nối hai byte array, mỗi array đã có header riêng. Reader đầu tiên đọc `alpha`, nhưng lần đọc kế tiếp gặp header thứ hai ở giữa stream và ném `StreamCorruptedException`.
4. `framedSegments()` ghi mỗi segment kèm `int` chiều dài, giới hạn dung lượng và đọc đúng `length` byte vào một mảng độc lập. Mỗi `ObjectInputStream` đọc header ở đầu segment tương ứng, vì vậy cả `alpha` và `beta` đều được giải mã.
5. `DataInputStream.readFully(...)` đòi hỏi đủ byte của segment; nếu nguồn bị cắt cụt thì ném `EOFException`, không âm thầm xem một segment thiếu byte là hợp lệ.
6. Mã không mở file, không yêu cầu quyền truy cập filesystem. Một triển khai lưu trữ thật cần tự thiết kế ghi append atomically theo record, checksum/commit marker nếu yêu cầu, và chính sách phục hồi record cuối đang ghi dở.

**Không lấy demo này làm hướng dẫn deserialize dữ liệu tùy ý từ bên ngoài.** Dữ liệu `ObjectInputStream` từ nguồn không đáng tin có thể nguy hiểm; phần an toàn được giải thích ở mục riêng bên dưới.

## 7. Một vấn đề khác: object handles và tham chiếu lặp

Header không phải trạng thái duy nhất của object stream. `ObjectOutputStream` còn có **handle table** để biết object nào đã được ghi và có thể ghi tham chiếu tới cùng object thay vì serialize lại toàn bộ.

Ví dụ:

~~~java
out.writeObject(someObject);
out.writeObject(someObject);
~~~

Nếu là **cùng object instance**, lần thứ hai có thể ghi một **back-reference**. Khi đọc lại, hai lời gọi `readObject()` có thể trả về **chính cùng object instance** trong JVM nhận, không phải hai bản sao độc lập.

Điều này quan trọng khi nội dung object được sửa giữa hai lần ghi:

~~~text
Object trong RAM: status = "old"
writeObject(object)

Object trong RAM: status = "new"
writeObject(object)  // có thể chỉ ghi tham chiếu tới object đã serialize

Reader có thể tiếp tục thấy status = "old" ở cả hai lần đọc!
~~~

Đây là hành vi theo cơ chế giữ identity, không phải bug của charset hay flush.

### Dùng reset() khi cần loại bỏ lịch sử reference

`ObjectOutputStream.reset()` là thao tác đặc biệt: nó phát một token reset vào **cùng object stream**, đồng thời xóa trạng thái tham chiếu đối tượng đã giữ ở writer để object về sau được serialize như mới.

~~~java
out.writeObject(object);
object.setState("new");
out.reset();
out.writeObject(object);
~~~

Đây là mảnh code minh họa với một kiểu object giả định có method `setState`. Lệnh `reset()` **không ghi lại stream header `AC ED 00 05`**. Nó tạo một điểm reset hợp lệ **bên trong** giao thức serialization, và `ObjectInputStream` tương ứng hiểu token này để reset trạng thái handle khi đọc tiếp.

Hạn chế: không được `reset()` trong khi đang thực hiện một lời gọi serialize object lồng nhau (có thể bị từ chối theo hợp đồng). `reset()` còn làm giảm lợi ích chia sẻ class descriptor/reference, có thể tăng kích thước output; không nên reset sau mọi object nếu không cần.

### Phân biệt reset, flush và mở stream mới

| Hành động | Header mới? | Handle table | Công dụng |
| --- | --- | --- | --- |
| `out.flush()` | Không | Giữ nguyên | Đẩy byte đang đệm |
| `out.reset()` | Không, ghi token reset trong luồng hiện tại | Xóa trạng thái tham chiếu | Ghi lại những object đã từng được serialize |
| `out.writeUnshared(obj)` | Không | Có ngữ nghĩa riêng về root unshared | Hạn chế chia sẻ root object theo hợp đồng |
| `new ObjectOutputStream(raw)` | Có | Khởi tạo trạng thái mới | Bắt đầu **stream độc lập** |
| `new ObjectInputStream(raw)` | Đòi đọc header mới tại vị trí bắt đầu | Khởi tạo bảng tham chiếu mới | Đọc **stream độc lập** |

**Không dùng `reset()` như “cách tự động cứu mọi file append hỏng”** nếu file đã có header lặp. Reset là một phần của writer đã tồn tại và đang phát token đúng ngữ cảnh; nó không tự loại bỏ những header thừa đã ghi.

## 8. Ví dụ thứ hai: reset để không tái sử dụng trạng thái cũ

Ví dụ này tách riêng khỏi chương trình trước, minh họa object reference và snapshot sau `reset()`. Lưu file `ObjectStreamResetDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectStreamResetDemo {
    private static final class Box implements Serializable {
        private static final long serialVersionUID = 1L;

        String value;

        Box(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Box box = new Box("old");

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(box);

            box.value = "new";
            out.writeObject(box); // Thường chỉ phát tham chiếu.

            out.reset();          // Không ghi header mới.
            out.writeObject(box); // Ghi snapshot mới.
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Box first = (Box) in.readObject();
            Box second = (Box) in.readObject();
            Box third = (Box) in.readObject();

            System.out.println("first=" + first.value);
            System.out.println("second=" + second.value);
            System.out.println("third=" + third.value);
            System.out.println("same before reset="
                    + (first == second));
            System.out.println("same across reset="
                    + (first == third));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectStreamResetDemo.java
java ObjectStreamResetDemo
~~~

Stdout:

~~~text
first=old
second=old
third=new
same before reset=true
same across reset=false
~~~

Kết quả cho thấy **hai lần viết cùng instance** trước reset không đương nhiên tạo hai snapshot. Sau `reset()`, cùng đối tượng nguồn được serialize như một đối tượng mới trên stream, và reader tạo instance mới ở lần thứ ba.

`serialVersionUID` trong ví dụ giúp định nghĩa phiên bản class serialization cho `Box`. Nó **không** sửa vấn đề lặp header và không bảo đảm mọi thay đổi class tương thích khi đọc dữ liệu cũ.

## 9. Vì sao sửa file append bằng cách bỏ header mới vẫn nguy hiểm?

Một số ví dụ trên mạng tạo subclass của `ObjectOutputStream` rồi override `writeStreamHeader()` để không ghi header sau lần đầu. Cách này có thể khiến file trông như có **một header ở đầu**.

Tuy nhiên, **chỉ bỏ header không đủ để tái lập tính nhất quán của stream**. Một writer mới có bảng handles riêng bắt đầu từ đầu, trong khi reader của stream hiện hữu đã tích lũy handles của các object trước. Khi writer mới ghi back-reference, class descriptor và các object phụ thuộc nhau, các handle có thể không còn khớp với trạng thái mà reader mong đợi.

Có những biến thể override phát **reset token** để tái đồng bộ handle table, nhưng đó là một thiết kế protocol tùy biến, phụ thuộc ràng buộc vòng đời và tính tương thích cụ thể. Không nên quảng bá "override writeStreamHeader rồi append" như một **công thức mặc định an toàn cho mọi object graph, mọi phiên ghi và mọi ứng dụng**.

Để lưu lịch sử nhiều phiên độc lập, ưu tiên một trong các mô hình rõ ràng:

- **Một stream liên tục được giữ mở và quản lý bởi một owner** nếu vòng đời ghi chỉ ở trong cùng phiên.
- **Nhiều segment có length-prefix**, mỗi segment có header và `ObjectInputStream` riêng.
- **Một file riêng cho mỗi snapshot/batch**, kèm manifest/index nếu cần.
- **Một định dạng record rõ ràng** không phụ thuộc handle table của Java Serialization (ví dụ protocol có schema và framing riêng) khi dữ liệu phải được append lâu dài qua nhiều phiên bản ứng dụng.

### Append trên filesystem không phải transaction

Ngay cả khi framing đã đúng, ghi append trong lúc process crash có thể để lại record cuối chỉ có một phần header độ dài hoặc một phần payload. Reader cần phát hiện segment thiếu, từ chối hoặc bỏ qua phần chưa hoàn chỉnh theo chính sách phục hồi; không giả định mọi `write(...)` và `close()` cùng tạo thành một commit atomically.

## 10. Quản lý thứ tự khởi tạo khi truyền object qua pipe/socket

Đối với hai đầu kết nối dùng object streams hai chiều, có một tình huống dễ deadlock:

~~~text
Peer A: tạo ObjectInputStream → đợi header từ B
Peer B: tạo ObjectInputStream → đợi header từ A

Cả hai cùng chờ, chưa ai tạo hoặc flush ObjectOutputStream.
~~~

Lý do là constructor `ObjectInputStream` có thể **chặn cho tới khi nhận và kiểm tra header**.

Trong protocol đối xứng, một lựa chọn thông thường là:

1. Tạo `ObjectOutputStream` ở hai bên.
2. `flush()` writer để header được đẩy tới transport.
3. Tạo `ObjectInputStream` ở hai bên.
4. Sau đó thực hiện thứ tự gửi/nhận có giao thức rõ ràng và chính sách timeout.

Tùy stream/transport, có thể cần flush byte khi ứng dụng gửi một object mới để peer nhận được kịp thời. **Không gọi `new ObjectOutputStream` cho mỗi message gửi**: sẽ lại có header mới và làm hỏng mô hình một stream liên tục.

Giao thức mạng cần đặt giới hạn kích thước, timeout, cách đóng và xử lý mất kết nối. Không sử dụng ObjectInputStream với byte nhận từ client tùy ý mà thiếu deserialization filter/boundaries.

## 11. Ngoại lệ có thể xuất hiện và cách đọc nguyên nhân

| Ngoại lệ | Khi nào có thể gặp | Ý nghĩa thực tế |
| --- | --- | --- |
| `StreamCorruptedException` | Header sai, token serialization không hợp lệ, header thứ hai giữa luồng | Định dạng byte không đúng chỗ hoặc stream đã hỏng |
| `EOFException` | Hết byte khi đang mong dữ liệu/hay segment | Luồng bị cắt cụt hoặc chương trình đã đọc vượt cấu trúc được thiết kế |
| `ClassNotFoundException` | Reader không tìm thấy class cần deserialize | Phải giải quyết tương thích class/module và classpath |
| `InvalidClassException` | Class không tương thích theo serialization rules/serialVersionUID hoặc bị filter từ chối | Thay đổi schema, version hoặc chính sách an toàn |
| `NotSerializableException` | Writer gặp object không implements `Serializable` và không có cách serialize hợp lệ | Kiểm tra object graph và chiến lược serialization |
| `OptionalDataException` | Reader dùng readObject/read primitive không khớp thứ tự/protocol data trong trường hợp thích hợp | Sai thứ tự đọc hoặc định dạng object/primitive |
| `IOException` | Lỗi stream nền, file, socket hoặc protocol I/O | Phân biệt với lỗi class/schema |

Đừng xử lý mọi `StreamCorruptedException` bằng cách bắt rồi bỏ qua một byte `0xAC` để "tiếp tục". Serialization là định dạng có cấu trúc và tham chiếu nội bộ; bỏ byte tùy tiện làm parser càng mất đồng bộ.

Nếu đã có file bị append sai:

1. Giữ bản gốc để phục hồi; không ghi đè trực tiếp.
2. Xác định chính xác các **segment** hợp lệ nếu có ranh giới từ nguồn tin cậy (như manifest/length-prefix hoặc snapshot riêng).
3. Dùng reader **trên từng segment độc lập** để trích dữ liệu.
4. Tạo file/định dạng mới có framing rõ, sau đó đối chiếu số object và nội dung.
5. Nếu không thể xác định boundary đáng tin, đừng giả định có thể phục hồi toàn bộ object graph chỉ bằng tìm chuỗi byte magic.

## 12. Bảo mật: không deserialize dữ liệu không tin cậy tùy tiện

Java Object Serialization có thể khởi tạo đồ thị class và thực thi hook deserialization của class, như `readObject`/`readResolve`, trong quá trình khôi phục object. Vì thế **không** dùng `ObjectInputStream` để đọc byte từ nguồn không tin cậy mà không có chính sách ràng buộc chặt.

Các biện pháp thiết kế:

- Chỉ chấp nhận dữ liệu từ nguồn được xác thực và kiểm soát.
- Cấu hình `ObjectInputFilter` hoặc cơ chế filter ở phạm vi ứng dụng để giới hạn class/type, số lượng reference, độ sâu đồ thị, số byte và kích thước mảng theo các giới hạn phù hợp.
- Giới hạn kích thước segment/file, timeout và memory budget **trước khi deserialize**.
- Không coi `serialVersionUID`, stream header hay checksum là xác thực chống tấn công.
- Nếu định dạng phải công khai lâu dài hoặc cần tương thích đa ngôn ngữ, cân nhắc JSON/CBOR/Protocol Buffers/Avro (với parser và schema có giới hạn) thay vì Java native serialization.

### Ví dụ thiết lập ObjectInputFilter

Đoạn minh họa có một `ObjectInputStream in` đã tạo và chỉ mong dữ liệu `String`:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=4;maxrefs=32;maxbytes=8192;!*");
in.setObjectInputFilter(filter);
~~~

Đây là mảnh code minh họa, không phải chương trình hoàn chỉnh. Mẫu `!*` từ chối những class chưa được phép theo cú pháp filter pattern; tuy nhiên **String được biểu diễn theo token đặc biệt và không phải lúc nào cũng qua cùng nhánh kiểm tra class**. Vì vậy, không dùng đúng filter trên để kết luận mọi định dạng String đều được kiểm soát hoàn toàn chỉ bằng `!*`. Với object graph thực tế, thiết kế allowlist có chủ đích và kiểm tra đúng những class/framework cần deserialize; xác minh filter bằng test trên payload hợp lệ và không hợp lệ.

**Quan trọng:** filter giới hạn rủi ro, không biến dữ liệu serialization tùy ý thành an toàn. Luôn kết hợp giới hạn đầu vào, nguồn tin cậy và kiểu dữ liệu hợp đồng rõ ràng.

## 13. Checklist thiết kế lưu trữ object bền vững

Khi chuẩn bị lưu nhiều object qua nhiều phiên:

1. **Xác định một stream hay nhiều segment:** một OOS duy trì từ đầu tới cuối hay mỗi segment có framing riêng.
2. **Định nghĩa schema của segment:** số object, loại dữ liệu mong đợi, version, field bắt buộc.
3. **Giới hạn kích thước:** cả payload serialized, graph depth và số đối tượng.
4. **Quản lý ownership:** chỉ một writer theo thiết kế; tránh hai thread tự tạo OOS trên cùng file/transport.
5. **Khả năng đọc sau crash:** kiểm tra độ dài segment, checksum/commit marker nếu cần; bỏ phần cuối bị cắt cụt theo quy tắc.
6. **Tương thích phiên bản class:** chủ động quản lý serialVersionUID hoặc định dạng có schema độc lập.
7. **Đóng/flush đúng lúc:** tránh đóng stream nền mà thành phần khác còn đang dùng; không lấy flush làm dấu kết thúc message nếu chưa có framing.
8. **Khả năng khôi phục:** lưu manifest hoặc index ranh giới nếu ứng dụng cần truy cập ngẫu nhiên.
9. **An toàn deserialization:** filter, allowlist và nguồn tin cậy.
10. **Kiểm thử append và restart:** tạo hai batch tại hai phiên khác nhau rồi kiểm tra đọc lại toàn bộ, không chỉ đọc object đầu.

## 14. Các lỗi thường gặp

**Lỗi 1 — Mở ObjectOutputStream mới với FileOutputStream(append=true).** Một header mới được ghi vào giữa file; một ObjectInputStream liên tục có thể ném `StreamCorruptedException` ở lần đọc tiếp.

**Lỗi 2 — Tưởng flush() tạo điểm bắt đầu stream mới.** `flush()` chỉ đẩy byte, không ghi header/reset handle table và không thay thế record framing.

**Lỗi 3 — Mở ObjectInputStream mới ở một offset bất kỳ.** Constructor đòi stream header hợp lệ tại offset đầu; byte object content không phải header.

**Lỗi 4 — Chỉ bỏ header khi append.** Writer mới có handle table riêng; reader cũ có thể vẫn giữ handle table trước đó, gây tham chiếu sai.

**Lỗi 5 — Nhầm cùng một object instance với hai snapshot độc lập.** `writeObject(obj)` lặp có thể chỉ ghi reference. Dùng `reset()` hoặc mô hình dữ liệu snapshot thích hợp khi thực sự cần serialize trạng thái mới.

**Lỗi 6 — Dùng EOF như giao thức không có trường hợp lỗi.** EOF cũng có thể báo dữ liệu bị cắt cụt. Với record archive/log cần length-prefix, checksum hoặc commit semantics nếu phải phát hiện ghi dở.

**Lỗi 7 — Tưởng serialize object đồng nghĩa phù hợp lâu dài hoặc đa ngôn ngữ.** Dữ liệu Java native serialization phụ thuộc định dạng/class, không phải schema cross-language ổn định mặc định.

**Lỗi 8 — Tạo ObjectInputStream ở cả hai đầu socket trước khi tạo/flush ObjectOutputStream.** Cả hai bên có thể chặn chờ header từ bên kia.

**Lỗi 9 — Bỏ qua readObject filter.** Deserialization từ nguồn không tin cậy có nguy cơ an toàn lớn; giới hạn class và cấu trúc graph.

**Lỗi 10 — Thấy StreamCorruptedException thì tự bỏ byte magic để đọc tiếp.** Không có bảo đảm rằng tìm được ranh giới hợp lệ nếu thiếu framing; cách này có thể làm hỏng dữ liệu hơn.

## 15. Tự kiểm tra

1. Một `ObjectOutputStream` mới ghi gì vào raw stream khi tạo? **Serialization stream header**, thường bắt đầu bằng `AC ED 00 05`.
2. Viết `writeObject(a)` rồi `writeObject(b)` trên **cùng OOS** có cần một header thứ hai không? **Không**.
3. `FileOutputStream(file, true)` có bảo đảm OOS mới tiếp nối handle table cũ không? **Không**; append chỉ là thêm byte vật lý.
4. Vì sao một OIS đọc object thứ nhất rồi lỗi với header thứ hai? Vì parser đang mong **object content token**, không mong khởi đầu stream mới ở giữa.
5. Nếu cần nhiều object stream độc lập trong một file, hãy tổ chức thế nào? **Ghi framing rõ (ví dụ length-prefix), rồi tạo OIS riêng cho từng segment được giới hạn**.
6. Có thể giải quyết lỗi append chỉ bằng `flush()` không? **Không**.
7. `ObjectOutputStream.reset()` có ghi header mới không? **Không**; nó phát token reset và làm mới trạng thái tham chiếu của cùng object stream.
8. Viết cùng object hai lần khi object bị sửa ở giữa có chắc tạo hai snapshot không? **Không**; lần hai có thể là reference tới snapshot cũ.
9. Vì sao OIS constructor trên pipe có thể chặn? Vì cần **đọc stream header** trước khi hoạt động; phía ghi cần tạo/flush header tương ứng.
10. Có nên deserialize bytes từ network không tin cậy với OIS mặc định không? **Không**; cần nguồn tin cậy, filter, giới hạn và cân nhắc một định dạng an toàn hơn.
11. `serialVersionUID` có sửa được header thừa không? **Không**; nó phục vụ nhận dạng/tương thích class trong serialization.
12. Nếu một segment length-prefix mới ghi được một phần rồi JVM crash, reader nên làm gì? **Phát hiện segment thiếu và áp dụng quy tắc phục hồi/bỏ đoạn cuối**, không ghép tùy ý với record tiếp theo.

**Ghi nhớ:** `ObjectOutputStream` là **một serialization stream có header và trạng thái handles**, không đơn thuần là một hàm “biến object thành vài byte”. Mở writer mới để append vào cùng file sẽ tạo **header giữa stream**, khiến reader liên tục dễ gặp `StreamCorruptedException`. Hãy **giữ một OOS cho một luồng logic**, hoặc **đóng khung các stream độc lập với độ dài rõ ràng** và đọc mỗi segment bằng OIS riêng. Phân biệt `flush()`, `reset()` và stream mới; đồng thời quản lý class compatibility, bản ghi ghi dở và an toàn deserialization.
