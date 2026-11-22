# Không khôi phục trực tiếp dữ liệu đối tượng không tin cậy trong Java

## 1. Bản chất vấn đề: byte lạ không phải đối tượng an toàn

Java Object Serialization cho phép ghi một đồ thị đối tượng bằng `ObjectOutputStream.writeObject(...)` và đọc lại bằng `ObjectInputStream.readObject()`. Nhưng **đọc lại object stream không đơn thuần là giải mã dữ liệu**: JVM phải xác định class từ mô tả trong stream, dựng object graph, khôi phục trường, duy trì reference handles và có thể gọi các cơ chế đặc biệt của class.

Một antipattern rất nguy hiểm là:

```java
// KHÔNG LÀM với bytes đến từ nguồn không tin cậy.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
    if (value instanceof ExpectedMessage) {
        process((ExpectedMessage) value);
    }
}
```

Đây là **mã minh họa không an toàn**, không phải chương trình độc lập; `networkInput`, `ExpectedMessage` và `process` giả định có sẵn. Kiểm tra `instanceof` diễn ra **sau khi `readObject()` đã làm công việc giải tuần tự hóa**, nên không phải biện pháp chặn các class không mong muốn được xử lý trong quá trình đọc.

**Nguyên tắc chính của bài:** *Không khôi phục trực tiếp Java objects từ dữ liệu không tin cậy.* Ưu tiên một định dạng dữ liệu có cấu trúc/schema rõ ràng và bộ đọc giới hạn kích thước, kiểu và tài nguyên; chuyển thành DTO hoặc domain object **sau khi** kiểm tra input. Nếu bắt buộc tương thích với serialized data tin cậy của hệ thống cũ, áp dụng bộ lọc class/độ sâu/size, xác thực nguồn, giới hạn tài nguyên và validation theo ngữ cảnh — nhưng đừng gọi đó là “an toàn tuyệt đối”.

### 1.1. “Không tin cậy” bao gồm những nguồn nào?

Không chỉ là request HTTP đến từ Internet:

- Byte lấy từ socket, message queue hoặc dịch vụ mà bên gửi có thể bị chiếm quyền.
- File upload, file tải từ URL, email attachment, nội dung do người dùng chọn.
- Cache/object blob lưu trong bucket, database, queue hoặc filesystem mà bên ghi không hoàn toàn nằm trong trust boundary của tiến trình đọc.
- Dữ liệu cũ do phiên bản chương trình khác ghi ra nhưng chưa có tính toàn vẹn, chữ ký, kiểm soát nguồn hoặc kế hoạch compatibility rõ ràng.
- Nội dung ở môi trường multi-tenant, nơi một tenant có thể tác động file/cache của tenant khác.
- Bất cứ byte stream nào mà đối phương có thể thay thế, cắt ngắn, sửa một phần hoặc phát lại.

Một file mang đuôi `.ser` hay bắt đầu bằng `AC ED 00 05` mới chỉ cho biết nó **trông giống Java serialization stream**. Nó không chứng minh bên ghi đáng tin, object graph hợp lệ hay class sẽ được nạp an toàn.

## 2. Vì sao `readObject()` có bề mặt tấn công lớn?

Khi `readObject()` xử lý một stream, nó có thể:

1. Đọc tên class và các **class descriptors** có trong stream.
2. Yêu cầu JVM tìm/khôi phục các class tương ứng trên classpath/module path.
3. Tạo các đối tượng và cấu trúc tham chiếu theo cơ chế Java serialization.
4. Khôi phục non-transient fields, kể cả các object lồng nhau trong đồ thị.
5. Chạy logic đặc biệt liên quan serialization, chẳng hạn private `readObject`, `readResolve` hoặc các callback validation theo cơ chế tương ứng.
6. Cấp phát mảng, object graph và những cấu trúc có thể lớn hơn nhiều so với kỳ vọng của người gọi.
7. Gặp lỗi loại dữ liệu, thiếu class, vượt giới hạn hoặc stream không hợp lệ **trong khi** quá trình khôi phục đang diễn ra.

Một **gadget chain** là chuỗi hành vi của những class đã có sẵn trong ứng dụng/thư viện có thể bị dữ liệu được deserialize kích hoạt theo cách ngoài dự định của developer. Rủi ro không đòi hỏi class tấn công phải được compile mới tại runtime; những class nằm sẵn trong classpath cũng có thể mang các side effects nguy hiểm khi được xử lý qua serialization.

Bài này **không trình bày payload hoặc hướng khai thác gadget chain**. Điều cần nắm là: kiểm tra kiểu đối tượng sau `readObject` không chặn được mọi hành vi có thể xảy ra *trước khi method trả về*.

### 2.1. Ba nhóm hậu quả phải phòng vệ

| Nhóm | Rủi ro ví dụ | Hướng phòng vệ |
|---|---|---|
| Thực thi logic không mong muốn | Hook/class graph có side effects hoặc hành vi không được dự tính | Tránh native deserialization; giới hạn class đã cho phép; thu hẹp classpath |
| Cạn kiệt tài nguyên | Đồ thị sâu, quá nhiều references, mảng lớn, payload kéo dài | Giới hạn bytes ở tầng transport; depth/references/array; quota CPU/thời gian/bộ nhớ |
| Phá invariant nghiệp vụ | Trường null/sai phạm vi, đối tượng ở trạng thái không thể tạo qua constructor, references không mong đợi | Parse theo schema; validate từng trường; constructor/factory kiểm tra invariant; không tin các field sau deserialize |

Định dạng có schema như JSON/CBOR/Protocol Buffers giúp **không tự động tạo graph Java tùy ý theo class name của stream** nếu triển khai đúng, nhưng **không tự miễn nhiễm** với payload sâu, input quá lớn, lỗi cấu hình kiểu đa hình hoặc thư viện parser có lỗ hổng. Chuyển định dạng là một phần của giải pháp, không phải lý do bỏ validation.

## 3. Phân biệt deserialize, parse và validate

Một tuyến dữ liệu bảo vệ tốt nên tách các bước:

```text
[Input không tin cậy]
        │
        ▼
Giới hạn kích thước/timeout/định dạng ở tầng nhận
        │
        ▼
Parse với schema/format cố định; không tạo class tùy ý
        │
        ▼
Kiểm tra phiên bản, kiểu trường, length, range, UTF-8, invariant
        │
        ▼
DTO dữ liệu thuần đã kiểm tra
        │
        ▼
Constructor/factory của domain object (quyền tối thiểu)
        │
        ▼
Tác vụ nghiệp vụ
```

**Parse** chỉ biến bytes thành representation có kiểu được xác định trước. **Validation** đảm bảo representation đó hợp lệ theo mục tiêu nghiệp vụ. **Deserialization Java object stream** có thêm khả năng dựng object graph và kích hoạt custom object logic; đó là lý do nó không phải parser nhập liệu tổng quát dành cho những nguồn đối kháng.

Một contract an toàn hơn có thể là:

```java
record IncomingMessage(String text, int sequence) {}

static IncomingMessage validate(String text, int sequence) {
    if (text == null || text.isBlank() || text.length() > 100) {
        throw new IllegalArgumentException("Invalid text");
    }
    if (sequence < 0) {
        throw new IllegalArgumentException("Negative sequence");
    }
    return new IncomingMessage(text, sequence);
}
```

Đây là **snippet minh họa** đặt trong class Java 17+; không tự đọc bytes và không có `main`. Ngay cả khi parser đã xác định `String` và `int`, vẫn phải kiểm tra phạm vi, trường bắt buộc và invariant.

## 4. Giải pháp ưu tiên: định dạng dữ liệu nhỏ, giới hạn rõ, không `readObject`

Nếu giao thức do ứng dụng kiểm soát, thường nên chuyển một record dữ liệu cố định thay vì Java object graph. Ví dụ frame:

```text
Offset   Kích thước   Nội dung
0        4 byte       magic = 0x4D534731 ("MSG1")
4        1 byte       protocolVersion = 1
5        4 byte       sequence (signed int, big-endian)
9        2 byte       textByteLength (unsigned short, big-endian)
11       N byte       text UTF-8, N <= 256
```

Lợi ích:

- Type cố định: chỉ có `sequence` và `text`, không có class name do input tự chọn.
- Bytes tối đa của chuỗi và frame đều có giới hạn.
- Decoder UTF-8 có thể cấu hình từ chối bytes sai cấu trúc.
- Protocol version do ứng dụng quản lý, độc lập với `serialVersionUID`/Object Serialization Stream Protocol.
- Có thể viết validator kiểm tra dữ liệu trước khi tạo domain object.

**Giới hạn quan trọng:** nếu đầu vào đến từ network stream, cần **cắt/giới hạn bytes ngay từ lúc nhận**, trước khi tạo mảng lớn. Việc chỉ kiểm tra `byte[].length` sau khi đã vô tình đọc toàn bộ một file 20 GB vào RAM là quá muộn đối với rủi ro cạn kiệt bộ nhớ.

## 5. Ví dụ Java 17+ chạy được: parse một frame rõ cấu trúc

Ví dụ không dùng `ObjectInputStream`. Nó ghi và đọc một frame có length bound, magic, version và UTF-8 strict. Input sai length bị từ chối **trước khi cấp phát mảng payload**.

**Tệp:** `SafeFrameDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class SafeFrameDemo {

    public record Message(String text, int sequence) {}

    public static byte[] encode(Message message) throws IOException {
        byte[] body = message.text()
                .getBytes(StandardCharsets.UTF_8);

        if (body.length > 256) {
            throw new IOException("text too long");
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(0x4D534731);   // "MSG1"
            out.writeByte(1);           // protocol version
            out.writeInt(message.sequence());
            out.writeShort(body.length);
            out.write(body);
        }
        return bytes.toByteArray();
    }

    public static Message decode(byte[] frame) throws Exception {
        // Giới hạn tổng bytes trước khi parse.
        if (frame.length < 11 || frame.length > 512) {
            throw new IOException("invalid frame size");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(frame))) {

            if (in.readInt() != 0x4D534731) {
                throw new IOException("invalid magic");
            }
            if (in.readUnsignedByte() != 1) {
                throw new IOException("unknown version");
            }

            int sequence = in.readInt();
            int length = in.readUnsignedShort();

            if (length > 256) {
                throw new IOException("invalid length");
            }

            byte[] body = new byte[length];
            in.readFully(body); // Thất bại nếu frame thiếu byte.

            // available() chỉ được dùng để tìm trailing bytes ở đây
            // vì nguồn là ByteArrayInputStream đã có đủ frame.
            if (in.available() != 0) {
                throw new IOException("trailing bytes");
            }

            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(body))
                    .toString();

            if (text.isBlank() || text.length() > 100
                    || sequence < 0) {
                throw new IOException("invalid message fields");
            }

            return new Message(text, sequence);
        }
    }

    public static void main(String[] args) throws Exception {
        Message message = decode(
                encode(new Message("HELLO", 7)));

        System.out.println("message: " + message.text()
                + ", seq=" + message.sequence());

        byte[] invalid = encode(new Message("A", 7));

        // Hai byte độ dài ở offset 9..10 trở thành 0x03E7 = 999.
        invalid[9] = 3;
        invalid[10] = (byte) 0xE7;

        try {
            decode(invalid);
        } catch (IOException ex) {
            System.out.println("invalid length: rejected");
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac SafeFrameDemo.java
java SafeFrameDemo
```

**Stdout mong đợi:**

```text
message: HELLO, seq=7
invalid length: rejected
```

### 5.1. Vì sao thiết kế này hạn chế rủi ro?

1. Parser biết trước frame chỉ gồm magic, version, sequence, độ dài và UTF-8 bytes; không có chỗ cho input yêu cầu JVM tạo class Java bất kỳ.
2. `readUnsignedShort` làm rõ length là unsigned 16-bit, nhưng **vẫn kiểm tra ≤256** trước khi tạo `byte[]`, không tin vào length trong dữ liệu.
3. `readFully` từ chối frame thiếu dữ liệu thay vì dùng partial text âm thầm.
4. `ByteArrayInputStream` có frame đã nhận đủ, nên kiểm tra `available()!=0` ở **trường hợp cụ thể này** để phát hiện trailing bytes. Không áp dụng `available()` như thước đo chính xác tổng độ dài network stream.
5. `CharsetDecoder` với `CodingErrorAction.REPORT` từ chối UTF-8 không hợp lệ, thay vì đổi nó thành ký tự `�` mà không báo.
6. Sau khi decode, các quy tắc nghiệp vụ tối thiểu (`text` không rỗng, giới hạn số ký tự, `sequence` không âm) được kiểm tra **trước khi** tạo record.
7. Dữ liệu lỗi chỉ gây `IOException`/lỗi decode hợp lệ, không điều khiển class loading tùy ý qua Object Serialization.

**Phạm vi ví dụ:** input của method là một `byte[]` đã có; với socket thực cần tầng framing và **giới hạn tổng byte nhận vào**, timeout và xử lý kết nối trước khi gọi `decode`. Ví dụ không có authentication, replay protection hay integrity checksum; các yêu cầu đó phải được xây riêng theo threat model.

### 5.2. Giới hạn UTF-8 bytes khác giới hạn độ dài String

`body.length` là số **byte** sau encode UTF-8. `text.length()` là số UTF-16 code units; hai số có thể khác nhau, nhất là với tiếng Việt và emoji. Một chuẩn protocol nên nêu rõ giới hạn theo byte hay code point và kiểm tra đúng đơn vị.

Nếu text phải mang giá trị nhạy cảm hoặc phải được ký số, cần xác định canonicalization/normalization và cách encode, thay vì trông chờ parser tự chuẩn hóa Unicode.

### 5.3. Nếu chọn JSON thì vẫn phải ràng buộc schema

Một hướng khác là gửi JSON như:

```json
{"version":1,"sequence":7,"text":"HELLO"}
```

Parser JSON nên chỉ đọc vào cấu trúc dữ liệu đã biết, giới hạn depth/bytes/string length/number ranges, **không bật tính năng polymorphic class resolution mặc định** cho dữ liệu người dùng. Sau parse, dùng constructor/factory validate DTO. Nếu library cung cấp cơ chế gắn class name trong payload để tự tạo subclass, việc bật bừa các tính năng ấy có thể tái tạo rủi ro “type do input tự quyết định” dưới định dạng khác.

## 6. Khi nào việc dùng ObjectInputStream vẫn được cân nhắc?

Ví dụ ứng dụng phải đọc các file legacy do **chính hệ thống đã kiểm soát** ghi bằng `ObjectOutputStream` và cần tương thích trong giai đoạn chuyển đổi. Trước khi quyết định tiếp tục, trả lời:

- Đường đi từ nơi ghi tới nơi đọc có bảo vệ **tính toàn vẹn và xác thực nguồn** không?
- Có bất kỳ actor ít tin cậy nào có thể thay file/blob trên filesystem, database, queue hoặc backup không?
- Những class nào thực sự cần được dựng khi đọc một record?
- Từng class có hooks `readObject`/`readResolve`/`readExternal` hoặc side effects nào không?
- Có đặt upper bound về bytes, graph depth, số references, kích thước arrays và thời gian xử lý không?
- Có cần đọc cả graph tùy ý, hay chỉ cần 2–5 field có thể chuyển sang DTO?
- Nếu filter từ chối một file hợp lệ cũ, có quy trình báo lỗi/migration rõ không?

Ngay cả với dữ liệu nội bộ, việc lộ file hoặc thay đổi quyền ghi có thể biến “trusted local file” thành một attack surface. Trust là thuộc tính của **toàn bộ tuyến dữ liệu**, không phải của tên file.

## 7. `ObjectInputFilter`: giới hạn class và tài nguyên, không biến dữ liệu lạ thành an toàn

Trong JDK 17/21, `ObjectInputFilter` hỗ trợ kiểm soát quá trình khôi phục Java objects. Nó có thể đánh giá:

- Class được yêu cầu dựng khi filter được gọi.
- Độ sâu đồ thị (depth).
- Số references đã xử lý.
- Độ dài mảng.
- Số bytes đã tiêu thụ theo thông tin của filter.

Ba trạng thái trả về:

| `ObjectInputFilter.Status` | Ý nghĩa |
|---|---|
| `ALLOWED` | Điều kiện được filter này cho phép; không thay thế validation |
| `REJECTED` | Từ chối; active `readObject`/`readUnshared` thường kết thúc bằng `InvalidClassException` |
| `UNDECIDED` | Filter này không quyết định; **không đồng nghĩa REJECTED** |

Một rủi ro lớn là viết filter cho class nguy hiểm trả `UNDECIDED` rồi tưởng đã deny. Nếu có yêu cầu allowlist, phải có **chính sách reject rõ ràng** cho class ngoài danh sách. Cùng lúc cần tính tới lớp/tham chiếu/array/strings mà stream thực sự chứa.

### 7.1. `setObjectInputFilter` phải đặt trước khi đọc object

```java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
```

Đây là snippet minh họa; `source` là `InputStream`, `filter` đã tạo, có import và xử lý `IOException`/`ClassNotFoundException`. Bộ lọc phải được thiết lập **trước lần đọc object**, không phải sau `readObject`. Trong Java 17/21, `setObjectInputFilter` chỉ có thể gọi theo quy tắc một lần trước khi đọc object, và tác dụng filter cuối cùng còn chịu cơ chế **filter factory** của JVM.

**Lưu ý rất quan trọng:** bộ lọc không được gọi cho mọi giá trị primitive và không phải biện pháp kiểm tra **nội dung** của String/field. Tài liệu `ObjectInputStream` nêu rõ các String được xử lý như primitive và không kích hoạt bộ lọc class tương ứng theo cách regular object. Vì vậy dù chỉ allow class DTO, vẫn phải kiểm tra chiều dài và nội dung các trường văn bản **sau khi khôi phục** và **trước khi dùng**.

### 7.2. Filter theo pattern

`ObjectInputFilter.Config.createFilter(...)` hỗ trợ chính sách dạng chuỗi:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=5;maxrefs=32;maxarray=256;maxbytes=8192;"
          + "com.example.legacy.dto.*;!*");
```

Đây là ví dụ cấu hình policy, **không phải một chương trình độc lập**. `com.example.legacy.dto.*` chỉ là namespace minh họa; triển khai thật phải kiểm kê chính xác các class cần cho serialized graph, các arrays và các type thuộc thư viện/framework. Mẫu `!*` là deny class chưa khớp allowlist. Đừng chọn rộng `java.base/*` hoặc `java.*` chỉ vì “đó là Java standard library” nếu không cần thiết; một allowlist có nghĩa chỉ cho phép kiểu thật sự cần thiết.

Một policy quá chặt có thể từ chối cả dữ liệu hợp lệ; một policy quá rộng có thể để lại gadget surface. Cần kiểm thử với các serialized fixtures thực, không chỉ tin rằng filter string nhìn “có vẻ an toàn”.

### 7.3. Filter dựa trên class cụ thể

Có thể viết `ObjectInputFilter` theo class và các giới hạn thay vì pattern tổng quát:

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 5
            || info.references() > 20
            || info.streamBytes() > 4096
            || info.arrayLength() > 128) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();

    // Những callback liên quan reference/metrics có type null.
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == TrustedRecord.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Đây là snippet với một `TrustedRecord` serializable do hệ thống tin cậy quản lý. Nếu toàn bộ graph gồm những class khác, phải thiết kế allowlist phù hợp; đừng copy nguyên mẫu mà kỳ vọng đọc được mọi `List`, `Map`, array và nested DTO. Các metrics do filter cung cấp cũng không thay thế giới hạn kích thước input ở tầng receive.

## 8. Ví dụ Java 17+ chạy được: đọc dữ liệu legacy tin cậy với filter

Ví dụ này **không nhận dữ liệu do đối phương kiểm soát**. Nó tự ghi hai payload trong bộ nhớ: một `Allowed` hợp lệ và một `Unexpected` không thuộc danh sách. Reader giới hạn bytes trước khi khởi tạo `ObjectInputStream`, cài filter **trước `readObject()`**, cho phép chính xác class `Allowed`, kiểm tra graph metrics và validate field sau khi đọc.

**Tệp:** `FilteredLegacyDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilteredLegacyDemo {

    static final class Allowed implements Serializable {
        private static final long serialVersionUID = 1L;
        final String name;

        Allowed(String name) {
            this.name = name;
        }
    }

    static final class Unexpected implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    static byte[] serialize(Object obj) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(obj);
        }

        return bytes.toByteArray();
    }

    static Allowed readTrusted(byte[] wire)
            throws IOException, ClassNotFoundException {

        // Đây là guard của demo; production phải limit cả tầng đọc.
        if (wire.length > 4096) {
            throw new IOException("frame too large");
        }

        ObjectInputFilter filter = info -> {
            if (info.depth() > 5
                    || info.references() > 20
                    || info.streamBytes() > 4096
                    || info.arrayLength() > 128) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            return type == Allowed.class
                    ? ObjectInputFilter.Status.ALLOWED
                    : ObjectInputFilter.Status.REJECTED;
        };

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(wire))) {

            in.setObjectInputFilter(filter);
            Object obj = in.readObject();

            if (obj.getClass() != Allowed.class) {
                throw new InvalidObjectException("unexpected type");
            }

            Allowed value = (Allowed) obj;

            if (value.name == null || value.name.length() > 40) {
                throw new InvalidObjectException("invalid name");
            }

            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        Allowed record = readTrusted(
                serialize(new Allowed("trusted")));

        System.out.println("name: " + record.name);

        try {
            readTrusted(serialize(new Unexpected()));
        } catch (InvalidClassException ex) {
            System.out.println("unexpected class: rejected");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FilteredLegacyDemo.java
java FilteredLegacyDemo
```

**Stdout:**

```text
name: trusted
unexpected class: rejected
```

### 8.1. Những điều ví dụ thật sự kiểm tra

- `Allowed` và `Unexpected` là **hai class test do chính ví dụ định nghĩa**; không có payload khai thác hay input ngoài.
- `readTrusted` kiểm tra tổng chiều dài của byte array **trước khi** dựng ObjectInputStream.
- Filter có giới hạn tài nguyên và **từ chối class bất kỳ khác Allowed**.
- `in.setObjectInputFilter(filter)` xảy ra **trước** `in.readObject()`.
- Sau đọc, code kiểm tra class **chính xác** và trường `name` có giới hạn.
- Trường `String name` vẫn cần validation vì filter không tự kiểm tra từng giá trị chuỗi.
- Đối tượng `Unexpected` bị filter từ chối, dẫn tới `InvalidClassException` được bắt có chủ đích.

### 8.2. Điều ví dụ không chứng minh

**Không** được dùng ví dụ này làm bằng chứng rằng mọi Java object stream từ Internet an toàn nếu gắn cùng filter. Filter có phạm vi giới hạn; class được cho phép vẫn phải được audit hooks/side effects, các graph phức tạp có thể cần chính sách khác, và input source/authentication/timeouts đều nằm ngoài ví dụ.

Một thay đổi class `Allowed` trong tương lai có thể thêm field mới hoặc custom `readObject`. Việc nó vẫn trùng allowlist class name **không phải** bằng chứng code đó an toàn trước dữ liệu được đối phương thiết kế. Cần code review và kiểm thử đầy đủ cho các class nằm trong allowlist.

### 8.3. Vì sao kết quả của self-test có tính xác định?

Cả hai payload được sinh bởi `ObjectOutputStream` trong cùng process nên class descriptors tương ứng với class local; không phụ thuộc file hay mạng. Kết quả chỉ thể hiện policy class cho hai object nhỏ. Nếu JVM đã cấu hình một filter factory toàn hệ thống mang policy chặt hơn, có thể có thêm hành vi từ chối theo policy đó; đây là điều cần test ở môi trường triển khai.

## 9. Filter không phải là “khử độc” mọi stream

Có vài giới hạn phải hiểu chính xác:

| Khẳng định sai | Sự thật |
|---|---|
| “Filter kiểm tra tất cả field values.” | Filter biết class/graph metrics tại các điểm callback; không phải validator schema/nội dung |
| “Chỉ cần `instanceof` sau `readObject`.” | Quá trình khôi phục đã xảy ra trước đó |
| “Class có trong allowlist thì luôn an toàn.” | Chính class đó hoặc những hoạt động liên quan vẫn có thể có side effects và bug |
| “Cứ trả `UNDECIDED` là từ chối.” | UNDECIDED có nghĩa chưa quyết định; phải cấu hình reject policy |
| “Giới hạn `maxbytes` bảo đảm request không tiêu thụ RAM ngoài filter.” | Filter hoạt động trong lúc deserialize; cần giới hạn bytes sớm và quota hệ thống |
| “Một filter global đủ cho mọi use case.” | Mỗi endpoint/context có set class/graph khác nhau, cần policy chuyên biệt |
| “String luôn đi qua filter để kiểm tra length.” | String/primitive có cách xử lý khác; cần validation payload riêng |
| “JSON/CBOR không bao giờ gây DoS.” | Parser khác cũng cần giới hạn tài nguyên và kiểm tra schema |

### 9.1. Global filter và context-specific filter factory

Java hỗ trợ JVM-wide serialization filter bằng system/security property như `jdk.serialFilter`, hoặc API cấu hình. Với Java 17+, cơ chế filter factory cho phép xây dựng chính sách theo context sử dụng từng `ObjectInputStream`.

Ví dụ cấu hình process **minh họa**:

```bash
java -Djdk.serialFilter="maxdepth=10;maxrefs=100;maxarray=1000;maxbytes=65536;com.example.dto.*;!*" MyApp
```

`MyApp` và `com.example.dto.*` chỉ là placeholder ngữ cảnh triển khai, **không phải lệnh để chạy ngay**. Một filter toàn JVM có thể ảnh hưởng tới các library sử dụng serialization nội bộ; trước khi đặt policy phải kiểm kê các use case và test thực tế. Không bật `java.base/*` toàn cục chỉ để tránh lỗi class allowlist nếu điều đó mở phạm vi không cần.

### 9.2. Thứ tự chọn filter có ý nghĩa

`ObjectInputStream` có thể nhận filter ban đầu từ **filter factory** lúc constructor chạy; gọi `setObjectInputFilter` có thể kích hoạt factory một lần nữa để chọn/kết hợp filter. Nếu ứng dụng thay filter factory tùy ý hoặc tạo policy yếu hơn, có nguy cơ làm mất bảo vệ mà một thư viện khác kỳ vọng.

Vì vậy:

- Xác định vị trí quản lý filter factory ở cấp ứng dụng.
- Không để các module tự ý thay global filter factory trong quá trình runtime.
- Với mỗi luồng dữ liệu, dùng filter thích hợp với **context** và audit chính sách effective.
- Test cả trường hợp có filter global và filter per-stream.
- Ghi log việc một stream bị từ chối mà không ghi toàn bộ dữ liệu nhạy cảm.

### 9.3. Filter có thể có lỗ hổng thiết kế trong chính policy

Ví dụ chỉ kiểm tra class root:

```java
Object root = in.readObject();
if (root.getClass() != Allowed.class) {
    throw new SecurityException("wrong root");
}
```

Đây là snippet **không an toàn nếu đứng riêng**, vì nested graph có thể đã được xử lý trước khi kiểm tra root. Một filter thích hợp cần giới hạn **các class có thể xuất hiện trong toàn graph** và giới hạn tài nguyên, không chỉ type top-level. Và ngay sau đó, vẫn phải validate invariant của root lẫn nested data.

## 10. Xác thực nguồn và tính toàn vẹn: cần nhưng không đủ

Một hệ thống có thể bảo vệ data bằng mTLS, HMAC, chữ ký số hoặc storage ACL. Những cơ chế này giúp xác nhận bytes đến từ nguồn hợp lệ hoặc không bị sửa mà không được phát hiện. Nhưng:

- Nguồn được xác thực cũng có thể bị chiếm quyền hoặc có bug ghi ra dữ liệu không hợp lệ.
- Một blob hợp lệ có thể chứa quá nhiều object/bytes vượt quota của người đọc.
- Một file cũ có chữ ký vẫn có thể không tương thích class hiện tại.
- Integrity không tự làm custom `readObject` của class an toàn.
- Chính sách xác thực phải xét replay, key rotation, thời hạn và định danh phiên bản nếu nghiệp vụ yêu cầu.

Vì vậy authentication/integrity chỉ là **một lớp**. Không thay thế input validation, allowlist, resource bounds và thiết kế dữ liệu nhỏ.

## 11. Serialization hooks và constructor bypass

Một Serializable class khi được khôi phục không chạy constructor của **chính serializable class** như khi gọi `new` thông thường. Việc khôi phục field có thể diễn ra trước validation nghiệp vụ. Những cơ chế như:

- private `readObject(ObjectInputStream)`;
- `readResolve()`;
- `readObjectNoData()`;
- `ObjectInputValidation` callbacks;
- `Externalizable.readExternal(...)`;

có thể tham gia logic dựng object theo contract tương ứng.

### 11.1. Invariant cần được kiểm tra khi khôi phục

Ví dụ class chỉ cho phép số lượng không âm:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.Serializable;

public final class Quantity implements Serializable {
    private static final long serialVersionUID = 1L;
    private int amount;

    public Quantity(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
        this.amount = amount;
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (amount < 0) {
            throw new InvalidObjectException("negative amount");
        }
    }
}
```

Đây là **class biên dịch độc lập** `Quantity.java`, không có `main`. Hook validation này có ý nghĩa đối với các dữ liệu **đã cho phép** deserialize, nhưng **không** khiến việc giải tuần tự hóa stream không tin cậy trở nên an toàn. Nó cũng không thay thế kiểm soát side effects của cả object graph.

### 11.2. Immutability không tự được bảo vệ qua serialization

`final` fields, private constructors và factory methods là công cụ thiết kế đối tượng, nhưng Java serialization có các quy tắc phục hồi đặc thù; không nên suy luận rằng chỉ vì không có public setter thì mọi object được deserialize đều thỏa invariant. Với class nhạy cảm, hãy giảm hoặc loại bỏ khả năng deserialize trực tiếp và chỉ tạo object qua factory nhận DTO đã kiểm tra.

## 12. Cách xử lý input từ network

**Không** tạo `ObjectInputStream` trực tiếp trên một socket chỉ vì bên gửi nói “đây là object hợp lệ”:

```java
// PHẢN VÍ DỤ: không dùng với socket nhận dữ liệu không tin cậy.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
Object request = in.readObject();
```

Ngoài bề mặt attack, constructor của ObjectInputStream có thể **chờ stream header**, và `readObject` có thể tiếp tục chờ dữ liệu chưa đủ. Một remote peer có thể gửi quá chậm, không bao giờ kết thúc frame hoặc vượt quota.

Thay bằng giao thức có:

1. Timeout đọc, giới hạn kết nối và tổng bytes tối đa.
2. Frame header (magic/version/length) được parse an toàn trước.
3. Kiểm tra length hợp lệ **trước cấp phát**.
4. Cố định type/schema; không resolve class theo tên từ input.
5. Giải mã charset có chính sách lỗi rõ, xác minh required fields và ranges.
6. Authentication/authorization khi cần, và giới hạn số message mỗi người gửi.
7. Cơ chế backpressure, telemetry lỗi, đóng connection khi protocol vi phạm.

### 12.1. Giới hạn InputStream trước khi readAllBytes

`InputStream.readAllBytes()` tiện dùng, nhưng nếu nguồn chưa tin cậy và chưa có giới hạn, nó có thể cấp phát tăng dần cho tới khi hết bộ nhớ. `ByteArrayOutputStream` cũng vậy nếu cứ copy cho đến EOF.

Trong giao thức có length-prefix, chỉ cấp phát tối đa kích thước hợp lệ. Nếu chưa tin byte length prefix, kiểm tra nó trước. Khi đọc stream chưa framing, dùng một wrapper counted/limited với hard cap và fail-closed; tránh đợi cho tới khi RAM đã cạn rồi mới kiểm tra.

### 12.2. Compression và nested content

Ngay cả khi file nén truyền tới chỉ 10 KB, khi giải nén nó có thể mở rộng thành hàng trăm MB/GB. Cần giới hạn **kích thước sau giải nén**, recursion/nesting, số entry và thời gian xử lý. Đừng đặt giới hạn chỉ lên byte compressed rồi kết luận deserializer/parser không thể gặp input khổng lồ.

## 13. Xử lý lỗi: fail closed thay vì “thử cách khác”

Các exception liên quan Java deserialization:

| Ngoại lệ | Có thể biểu thị |
|---|---|
| `StreamCorruptedException` | Header hoặc control data không hợp lệ |
| `InvalidClassException` | Class không tương thích, hoặc bị filter từ chối |
| `NotSerializableException` | Graph ghi có object không serializable |
| `ClassNotFoundException` | Class trong stream không có ở môi trường đọc |
| `OptionalDataException` | Đọc sai loại object/primitive hoặc dữ liệu đặc biệt |
| `EOFException` | Stream chưa đủ bytes/đến cuối trong lúc đọc |
| `InvalidObjectException` | Invariant/hook validation chủ động từ chối |
| `IOException` | Lỗi I/O hoặc lỗi đọc dữ liệu |
| `ClassCastException` | Root object đọc được khác kiểu ứng dụng mong đợi |

Các lỗi này không nên bị biến thành “payload trống hợp lệ”. Với `ObjectInputStream.readObject()`, tài liệu nói các exception để stream ở trạng thái **không xác định**; thường phải đóng stream và từ chối message thay vì cố skip vài byte rồi tiếp tục như chưa có gì xảy ra.

**Không fallback tự động** theo mẫu “deserialize không được thì tắt filter và thử lại”. Nếu filter từ chối payload, đó là một tín hiệu an ninh/chính sách. Cần log đủ thông tin phi nhạy cảm và điều tra theo quy trình, không hạ cấp validation chỉ để “cho chương trình chạy”.

## 14. Migrations: chuyển khỏi Java Serialization an toàn

Một hệ thống cũ có thể đã lưu nhiều file `.ser`. Chuyển định dạng không chỉ là tìm `readObject` rồi thay `parseJson`; cần có lộ trình:

### 14.1. Kiểm kê điểm đọc và phân loại nguồn

Tìm các điểm nhận serialized objects:

- `ObjectInputStream.readObject` và `readUnshared`.
- Thư viện/framework có deserialization ngầm bên trong, cache, RPC hoặc messaging.
- File lưu state, session, job data, serialized blobs trong database.
- Backups và dữ liệu chưa có chính sách xóa.
- Các consumer chạy phiên bản khác nhau trong cùng hệ thống.

Đối với từng điểm, ghi lại source, quyền ghi, class graph mong đợi, dung lượng, thời gian sống và mức tin cậy. Đừng dựa vào extension hay tên bảng database.

### 14.2. Thiết kế format thay thế

Chọn JSON/CBOR/Protocol Buffers/format byte định nghĩa rõ khi phù hợp; thống nhất:

- Version trong message/schema.
- Danh sách trường và type cố định.
- Kích thước tối đa của message và từng trường.
- Quy tắc optional/default/unknown fields.
- Charset, timezone, date/time, numeric range và chuẩn Unicode.
- Integrity/authentication theo threat model.
- Quy tắc tương thích backward/forward và kế hoạch loại version cũ.

### 14.3. Conversion tool ở môi trường kiểm soát

Nếu vẫn phải mở các file legacy:

1. Chỉ chạy trên bản copy từ nguồn có xác thực và kiểm tra tính toàn vẹn, không trực tiếp trên upload chưa tin cậy.
2. Dùng JDK và classpath đã kiểm kê, áp class/graph/resource filters chặt.
3. Chạy công cụ với quyền OS tối thiểu, hạn chế network, filesystem, CPU/memory/time và logging phù hợp; isolation giảm tác hại nhưng không đảm bảo an toàn tuyệt đối.
4. Validate dữ liệu sau deserialize rồi viết sang định dạng mới.
5. Test sample hợp lệ/corrupt và hỗ trợ rollback khi conversion sai.
6. Sau cutover, loại các đường vào `ObjectInputStream` không còn cần thiết, thay vì để endpoint legacy mở mãi.

Nếu không thể chứng minh input legacy đáng tin và không thể áp controls thích hợp, **từ chối chuyển tự động** tốt hơn là đưa nó vào tiến trình production quan trọng.

## 15. Các lỗi thiết kế phổ biến

1. **Đọc object stream không tin cậy chỉ vì class implements `Serializable`.** Đây không phải chứng nhận an toàn.
2. **Kiểm tra `instanceof` sau `readObject` rồi xem như đã chặn khai thác.** Quá trình deserialize đã thực thi trước đó.
3. **Dựa vào đuôi file `.ser` hay magic header `AC ED 00 05`.** Chúng là dấu hiệu format, không phải authenticity.
4. **Chỉ lọc root class.** Nested graph có thể chứa các class khác đã được xử lý.
5. **Filter trả `UNDECIDED` cho class ngoài danh sách mà nghĩ là deny.** Phải có reject policy.
6. **Cho phép cả package/Java modules không cần thiết.** Làm bề mặt class lớn hơn yêu cầu thật.
7. **Không giới hạn mảng, depth, references hoặc bytes.** Dễ gặp resource exhaustion.
8. **Chỉ giới hạn bytes sau khi `readAllBytes`.** Cấp phát không giới hạn đã xảy ra trước kiểm tra.
9. **Cho rằng filter xác thực nội dung String.** Vẫn phải validate độ dài/giá trị field.
10. **Cho rằng class allowlisted luôn không có side effects.** Audit hook và sự thay đổi class.
11. **Chỉ xác thực nguồn mà không hạn chế format/tài nguyên.** Nguồn bị compromise vẫn có thể gửi input lỗi.
12. **Đổi sang JSON nhưng bật generic polymorphic deserialization cho class do input chọn.** Vẫn cần schema/type whitelist.
13. **Không kiểm tra UTF-8 malformed.** Dữ liệu có thể bị thay thế ký tự âm thầm.
14. **Tin input length-prefix là đúng rồi cấp phát array ngay.** Length do attacker điều khiển phải bị ràng buộc.
15. **Không kiểm tra trailing bytes hoặc dữ liệu thiếu.** Frame không hợp lệ có thể bị chấp nhận một phần.
16. **Để parser/chuyển đổi đọc vô hạn trên socket chậm.** Cần timeout và quotas.
17. **Ngầm chuyển đổi phiên bản class mà không kiểm tra invariant.** Dữ liệu cũ không tự phù hợp model mới.
18. **Bắt lỗi filter rồi tự động tắt filter/retry.** Hạ cấp chính sách bảo vệ.
19. **Dùng `readObject` như công cụ probe file unknown.** Không deserialize để “xem thử file chứa gì”.
20. **Ghi log toàn bộ serialized bytes hoặc secret khi lỗi.** Có thể lộ dữ liệu; ghi thông tin lỗi đã giảm nhạy cảm.
21. **Cho rằng một sandbox/process luôn đủ bảo vệ.** Cần quyền tối thiểu, patch, quan sát runtime và defense-in-depth.
22. **Không kiểm tra policy filter của thư viện sử dụng `ObjectInputStream` ngầm.** Điểm vào có thể nằm ngoài source code endpoint.
23. **Dùng cùng một filter quá rộng cho mọi use case.** Context khác nhau cần class/limits khác nhau.
24. **Không test với file thiếu/truncated, graph sâu và field không hợp lệ.** Chỉ happy path không đánh giá được robustness.
25. **Tưởng parse thành Java record là đủ.** Record có field types nhưng validation nghiệp vụ vẫn cần kiểm tra.
26. **Xem mọi `IOException` khi đọc là recoverable và tiếp tục trên stream hỏng.** ObjectInputStream có thể ở trạng thái không xác định.
27. **Nhầm integrity check với confidentiality.** Dữ liệu xác thực vẫn có thể bị đọc nếu không mã hóa/kiểm soát quyền truy cập.
28. **Tin dữ liệu được lưu “nội bộ” là bất biến.** Kiểm tra ai có quyền ghi từ ứng dụng, backup, file share và queue.
29. **Không giới hạn output khi decode/decompress.** Input nhỏ có thể nở lớn.
30. **Không có kế hoạch xóa endpoint legacy.** Hệ thống vẫn giữ điểm deserialize nguy hiểm sau khi đã chuyển định dạng phần lớn.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `(Expected) in.readObject()` nguy hiểm khi bytes không tin cậy?  
**Trả lời:** Trước khi cast, JVM đã có thể dựng graph, chạy logic deserialize và cấp phát tài nguyên theo stream.

**Câu 2.** Kiểm tra file header `AC ED 00 05` có chứng minh stream an toàn không?  
**Không.** Đây là magic/version của protocol, không xác minh nguồn hoặc class graph.

**Câu 3.** Nên ưu tiên cách gì cho request API do người dùng tạo?  
**Trả lời:** Giao thức dữ liệu có schema/type cố định, parser giới hạn bytes/độ sâu và validation từng trường.

**Câu 4.** `ObjectInputFilter` có thể giới hạn những gì?  
**Trả lời:** Class, array length, graph depth, reference count và số bytes đã tiêu thụ theo contract.

**Câu 5.** Filter trả `UNDECIDED` có nghĩa là class đã bị chặn chưa?  
**Chưa.** Đây là trạng thái chưa quyết định; muốn deny rõ phải trả `REJECTED` theo policy.

**Câu 6.** `setObjectInputFilter` đặt sau `readObject` có đúng không?  
**Không.** Bộ lọc phải được thiết lập trước khi đọc object, theo quy tắc gọi của API.

**Câu 7.** Chỉ allowlist một DTO class thì có cần validate `String name` không?  
**Có.** Filter không kiểm tra mọi giá trị primitive/String; vẫn phải kiểm tra nội dung, giới hạn và invariant.

**Câu 8.** `Future`/async transport có tự hạn chế độ dài object stream không?  
**Không.** Transport API và input framing phải có quota riêng trước khi deserialize.

**Câu 9.** Nếu `InvalidClassException` báo filter từ chối, có nên đọc tiếp cùng stream không?  
**Không nên.** Hãy coi stream hỏng/không tin cậy, đóng và báo lỗi; không hạ cấp filter tự động.

**Câu 10.** Mã ví dụ `SafeFrameDemo` dùng `available()` có áp dụng để đo tổng byte network stream không?  
**Không.** Ở đây nguồn là `ByteArrayInputStream` đã nắm toàn bộ frame; network stream cần length-prefix và bounded read.

**Câu 11.** Dùng chữ ký số có đủ thay filter/schema không?  
**Không.** Chữ ký giúp xác minh tính toàn vẹn và nguồn theo threat model; vẫn cần giới hạn graph/bytes và validation.

**Câu 12.** Khi buộc convert serialized files legacy, nên chạy ở đâu?  
**Trả lời:** Môi trường kiểm soát, dữ liệu đã xác thực, classpath hạn chế, filter chặt và quyền/tài nguyên giới hạn; viết sang định dạng mới rồi bỏ điểm đọc cũ.

**Câu 13.** `InputStream.readAllBytes()` có an toàn cho file upload không giới hạn không?  
**Không.** Nó có thể cấp phát theo toàn bộ input; cần hard cap từ tầng nhận.

**Câu 14.** Filter class chặt có bảo đảm tránh mọi side effects của class allowed không?  
**Không.** Code của chính allowed class/hook vẫn cần audit; filter không phải validator hành vi.

**Câu 15.** Mục đích đúng của Java Object Serialization khi vẫn phải dùng là gì?  
**Trả lời:** Compatibility với dữ liệu/object graph Java do hệ thống kiểm soát, kèm boundaries và controls, **không** phải format nhập liệu mặc định từ đối tượng không tin cậy.

## 17. Kết luận và tài liệu chính thức

**Ghi nhớ:** “Không deserialize để kiểm tra xem object có đúng kiểu hay không; chỉ deserialize khi đã có cơ sở tin cậy, chính sách class/graph và ranh giới tài nguyên phù hợp — và khi có lựa chọn, dùng định dạng dữ liệu với parser có schema.”

Trình tự ra quyết định:

```text
Nguồn có thể bị đối phương kiểm soát?
    ├── Có hoặc chưa chứng minh được nguồn tin cậy
    │       └── KHÔNG dùng ObjectInputStream.readObject trực tiếp
    │               └── Bounded framing → schema parser → validation → DTO
    └── Dữ liệu legacy tin cậy, cần compatibility
            └── Kiểm kê classes + xác minh nguồn
                    └── Quota/input bounds + ObjectInputFilter
                            └── Validate output và audit allowed hooks
                                    └── Migration sang format dữ liệu ổn định
```

Nguồn chính thức (Java SE 21, áp dụng các APIs được trình bày cho Java 17+):

- `ObjectInputStream` — cảnh báo nguy hiểm của untrusted deserialization, hợp đồng `readObject` và `setObjectInputFilter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `ObjectInputFilter` — class/resource filtering, policy composition và filter factory: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectInputFilter.Config` — pattern filters và JVM-wide filter: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- `Serializable` — default serialization và class hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `DataInputStream` — bounded primitive/data reading theo định dạng do ứng dụng thiết kế: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html
- `CharsetDecoder` — chính sách lỗi UTF-8: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- Oracle Secure Coding Guidelines for Java SE, phần Serialization/Deserialization: https://www.oracle.com/java/technologies/javase/seccodeguide.html
