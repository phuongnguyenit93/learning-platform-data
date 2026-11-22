# Phân biệt định dạng nhị phân tự thiết kế với Java serialization

Khi cần lưu dữ liệu thành byte hoặc truyền qua mạng, Java có ít nhất hai hướng tiếp cận rất khác nhau:

1. **Tự thiết kế định dạng nhị phân**: ứng dụng định nghĩa chính xác các byte nào được ghi, thứ tự, kích thước, kiểu dữ liệu, phiên bản và cách giải mã. Có thể dùng `DataOutputStream`/`DataInputStream`, `ByteBuffer` hoặc byte streams.
2. **Java Object Serialization**: dùng `ObjectOutputStream` và `ObjectInputStream` để mã hóa/khôi phục **đồ thị đối tượng Java** theo cơ chế serialization của nền tảng, thường với các lớp triển khai `Serializable`.

Cả hai đều tạo ra dãy byte, nhưng **mục đích và hợp đồng dữ liệu** không giống nhau. Định dạng tự thiết kế là một *giao thức/schema do bạn sở hữu*; Java serialization mang nhiều ngữ nghĩa liên quan đến lớp, đối tượng, tham chiếu và khả năng tương thích của Java.

Bài này tập trung vào lựa chọn, triển khai, tính tương thích và xử lý dữ liệu không tin cậy. Các ví dụ chạy được trên Java 17+.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **serialize object graph** với **encode một schema nhị phân**.
- Giải thích `Serializable`, `serialVersionUID`, `transient`, `ObjectOutputStream.writeObject` và `ObjectInputStream.readObject`.
- Thiết kế một format nhị phân gồm magic, version, số bản ghi, số nguyên và chuỗi UTF-8 có tiền tố độ dài.
- Sử dụng `DataOutputStream`/`DataInputStream` đúng thứ tự đọc–ghi, biết endian và xử lý `EOFException`.
- Phân biệt UTF-8 tiêu chuẩn với **modified UTF-8** của `writeUTF/readUTF`.
- Đặt giới hạn số bản ghi, độ dài chuỗi, kích thước payload và kiểm tra tính hợp lệ **trước khi cấp phát**.
- Lựa chọn cơ chế lưu trữ phù hợp khi cần ổn định format, trao đổi liên ngôn ngữ, quản lý phiên bản hoặc xử lý dữ liệu từ bên ngoài.
- Nhận diện rủi ro của Java deserialization với dữ liệu không tin cậy và vai trò giới hạn của `ObjectInputFilter`.

## 2. So sánh tổng quan

| Tiêu chí | Định dạng nhị phân tự thiết kế | Java serialization |
| --- | --- | --- |
| Đầu vào logic | Giá trị/trường theo schema đã định nghĩa | Đối tượng và đồ thị đối tượng Java |
| Công cụ điển hình | `DataOutputStream`, `DataInputStream`, `ByteBuffer` | `ObjectOutputStream`, `ObjectInputStream` |
| Bố cục byte | Do bạn quy định và kiểm thử | Theo giao thức Java Object Serialization |
| Tên lớp Java trong format | Không bắt buộc | Thường có descriptor/thông tin kiểu lớp trong luồng |
| Tham chiếu dùng chung / chu trình | Phải tự thiết kế ID/reference nếu cần | Cơ chế object handles hỗ trợ chia sẻ tham chiếu và đồ thị vòng |
| Thay đổi schema | Tự định nghĩa version, optional field, migration | Phụ thuộc quy tắc tương thích serialization và thiết kế lớp |
| Khả năng đọc bằng ngôn ngữ khác | Có thể, nếu đặc tả đủ rõ | Không phải format trao đổi liên ngôn ngữ thông dụng |
| Mức độ kiểm soát kích thước | Chủ động nếu format tối giản | Có metadata/overhead; không đoán trước số byte |
| Dữ liệu không tin cậy | Có thể giới hạn và xác thực từng trường; vẫn phải phòng parser bug | **Không nên deserialize nguồn không tin cậy**; nguy cơ qua lớp/callback/gadget |
| Use case gợi ý | Giao thức file/mạng, firmware, cache có schema, lưu lâu dài | Trao đổi hoặc lưu đồ thị đối tượng Java trong môi trường **tin cậy**, có kiểm soát lớp/phiên bản |

**Không đánh đồng** “Java serialization” với mọi hành động chuyển dữ liệu Java thành byte. Một format tự thiết kế, JSON, Protocol Buffers hoặc CBOR cũng đều là các dạng serialization theo nghĩa rộng; trong bài này **Java serialization** được dùng theo nghĩa hẹp của `ObjectOutputStream`/`ObjectInputStream` và cơ chế `Serializable`.

## 3. Format nhị phân tự thiết kế là gì?

Một format nhị phân là **hợp đồng byte** giữa bên ghi và bên đọc. Ví dụ, ta quy định một file chứa danh sách người:

~~~text
Header:
+------------------+------------------+------------------+
| magic: 4 byte    | version: 2 byte  | count: 4 byte    |
+------------------+------------------+------------------+

Mỗi bản ghi:
+------------------+------------------+--------------------------+
| id: int32, 4 B   | nameLength: 4 B  | name: UTF-8, N byte      |
+------------------+------------------+--------------------------+
~~~

Cần xác định **từng chi tiết**, không chỉ viết “ghi một số nguyên và một chuỗi”:

- **Magic**: bốn byte `50 45 50 4C` (ASCII “PEPL”) để nhận diện loại payload.
- **Version**: số nguyên 16-bit **unsigned**, thứ tự byte **big-endian**; phiên bản đầu là `1`.
- **Count**: số nguyên 32-bit có dấu, big-endian, chỉ chấp nhận `0..1000`.
- **ID**: số nguyên 32-bit có dấu, big-endian; ý nghĩa/miền giá trị phải do ứng dụng quy định.
- **Name length**: số nguyên 32-bit có dấu, big-endian, chỉ chấp nhận `0..4096` byte.
- **Name**: đúng `nameLength` byte theo UTF-8 tiêu chuẩn, **không có byte NUL kết thúc**.
- **Thứ tự**: ghi header trước, sau đó từng bản ghi theo thứ tự; không tự thêm separator/padding.
- **Điểm kết thúc**: với một payload đóng gói riêng, sau `count` bản ghi không được có dữ liệu thừa; với luồng chứa nhiều frame liên tiếp phải có framing riêng.

Format tự thiết kế phải định nghĩa rõ **endianness**, trường optional, nullable, giới hạn dữ liệu, cách xử lý version lạ, lỗi thiếu byte và dữ liệu dư. Một cặp encoder/decoder chạy được trên cùng máy **chưa đủ** để thành giao thức đáng tin cậy nếu đặc tả byte còn mơ hồ.

## 4. `DataOutputStream` và `DataInputStream`: công cụ cho format tự định nghĩa

`DataOutputStream` có các phương thức như `writeByte`, `writeShort`, `writeInt`, `writeLong`, `writeBoolean`, `write(byte[])`; `DataInputStream` có các phương thức đọc tương ứng.

Với các số nguyên nhiều byte:

- `writeShort` ghi hai byte; `writeInt` ghi bốn byte; `writeLong` ghi tám byte.
- Các phương thức này dùng **byte có trọng số cao trước** (*big-endian*), không tự thay đổi theo CPU.
- `readUnsignedShort` đọc 2 byte thành `int` trong khoảng `0..65535`; phù hợp version unsigned.
- `readFully(byte[])` cố đọc **đủ** số byte yêu cầu hoặc ném `EOFException` nếu hết nguồn trước khi đủ.
- Một `InputStream.read(byte[])` đơn lẻ **không bảo đảm** lấp đầy mảng, vì vậy khi cần chính xác N byte, `readFully` hoặc vòng lặp tích lũy là quan trọng.
- Các phương thức I/O có thể ném `IOException` do lỗi nguồn/đích; `EOFException` là trường hợp thiếu dữ liệu tại thời điểm cần đủ byte.

Điểm quyết định: `DataOutputStream` **không tự tạo schema**. Nếu bạn ghi `writeInt(id)` rồi `writeInt(nameLength)` và các byte tên, decoder phải đọc **đúng thứ tự**. Đảo vị trí sẽ khiến dữ liệu bị giải nghĩa sai, dù cả hai bên đều dùng lớp Java giống nhau.

### Đừng mặc định `writeUTF()` là UTF-8 tiêu chuẩn

`DataOutputStream.writeUTF(String)` ghi **hai byte độ dài** rồi ghi ký tự bằng **modified UTF-8**, một biến thể của UTF-8. Nó có giới hạn tối đa **65.535 byte trong phần mã hóa**, vượt quá có thể ném `UTFDataFormatException`. `DataInputStream.readUTF()` là cặp đọc phù hợp.

Nếu format cần trao đổi với phần mềm không phải Java hoặc cần định nghĩa chính xác UTF-8 theo chuẩn, cách dễ đặc tả hơn là:

~~~java
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);
~~~

Bên đọc phải kiểm tra độ dài trước khi cấp phát, dùng `readFully`, rồi giải mã UTF-8. Đoạn trên là **mảnh mã** với `text` kiểu `String` và `out` là `DataOutputStream` đã khai báo. `String.length()` đo **UTF-16 code units**, không phải số byte UTF-8; không được ghi `text.length()` làm byte length.

## 5. Ví dụ Java 17+: format nhị phân có header, version và UTF-8

Tạo file **`CustomBinaryDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public class CustomBinaryDemo {
    private static final int MAGIC = 0x5045504C; // "PEPL"
    private static final int VERSION = 1;
    private static final int MAX_RECORDS = 1000;
    private static final int MAX_NAME_BYTES = 4096;

    record Person(int id, String name) {}

    static byte[] encode(List<Person> people) throws IOException {
        if (people.size() > MAX_RECORDS) {
            throw new IOException("Too many records");
        }

        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(sink)) {
            out.writeInt(MAGIC);
            out.writeShort(VERSION);
            out.writeInt(people.size());

            for (Person person : people) {
                byte[] nameBytes =
                        person.name().getBytes(StandardCharsets.UTF_8);

                if (nameBytes.length > MAX_NAME_BYTES) {
                    throw new IOException("Name is too long");
                }

                out.writeInt(person.id());
                out.writeInt(nameBytes.length);
                out.write(nameBytes);
            }
            out.flush();
        }

        return sink.toByteArray();
    }

    static List<Person> decode(byte[] payload) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(payload))) {

            if (in.readInt() != MAGIC) {
                throw new IOException("Bad magic");
            }

            int version = in.readUnsignedShort();
            if (version != VERSION) {
                throw new IOException("Unsupported version: " + version);
            }

            int count = in.readInt();
            if (count < 0 || count > MAX_RECORDS) {
                throw new IOException("Invalid record count");
            }

            List<Person> result = new ArrayList<>(count);

            for (int i = 0; i < count; i++) {
                int id = in.readInt();
                int nameLength = in.readInt();

                if (nameLength < 0 || nameLength > MAX_NAME_BYTES) {
                    throw new IOException("Invalid name length");
                }

                byte[] nameBytes = new byte[nameLength];
                in.readFully(nameBytes);

                String name = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(nameBytes))
                        .toString();

                result.add(new Person(id, name));
            }

            // Chỉ kiểm tra EOF vì payload này được truyền vào như
            // một thông điệp byte[] độc lập, không ghép nhiều frame.
            if (in.read() != -1) {
                throw new IOException("Unexpected trailing bytes");
            }

            return result;
        }
    }

    public static void main(String[] args) throws IOException {
        List<Person> people = List.of(
                new Person(7, "An"),
                new Person(9, "Bình")
        );

        byte[] encoded = encode(people);

        System.out.println("size=" + encoded.length);
        System.out.println(
                "magic=" + HexFormat.of().formatHex(encoded, 0, 4));
        System.out.println("decoded=" + decode(encoded));

        byte[] truncated = Arrays.copyOf(
                encoded, encoded.length - 1);
        try {
            decode(truncated);
            System.out.println("unexpected success");
        } catch (EOFException exception) {
            System.out.println("truncated=EOFException");
        }
    }
}
~~~

Biên dịch (chỉ định encoding của file nguồn để bảo toàn chữ “Bình” trên các môi trường Java 17) và chạy:

~~~bash
javac -encoding UTF-8 CustomBinaryDemo.java
java CustomBinaryDemo
~~~

**Stdout theo nội dung Unicode của chương trình:**

~~~text
size=33
magic=5045504c
decoded=[Person[id=7, name=An], Person[id=9, name=Bình]]
truncated=EOFException
~~~

### Vì sao đúng 33 byte?

- Header: `4 + 2 + 4 = 10` byte.
- Người thứ nhất: `4` byte ID + `4` byte độ dài + `2` byte UTF-8 của `An` = `10` byte.
- Người thứ hai: `4 + 4 + 5 = 13` byte vì `Bình` cần 5 byte UTF-8: `B` (1), `ì` (2), `n` (1), `h` (1).
- Tổng: `10 + 10 + 13 = 33` byte.

`HexFormat` có từ Java 17; nó chỉ định dạng byte để hiển thị, không tham gia vào giao thức. `ByteArrayOutputStream` giữ kết quả trong bộ nhớ nên phù hợp demo nhỏ. Với file lớn, nên ghi streaming và áp dụng giới hạn tổng kích thước/thời gian xử lý.

### Vì sao decoder an toàn hơn cách đọc tùy ý?

1. Kiểm tra magic để nhận diện format.
2. Từ chối version chưa hỗ trợ thay vì đoán cấu trúc.
3. Kiểm tra count **trước** khi cấp phát danh sách hoặc lặp.
4. Kiểm tra độ dài tên **trước** khi cấp phát byte array.
5. `readFully` buộc mỗi tên có đúng số byte; EOF sớm trở thành lỗi.
6. `CharsetDecoder` với `CodingErrorAction.REPORT` báo dữ liệu UTF-8 malformed thay vì âm thầm thay thế ký tự không hợp lệ.
7. Kiểm tra trailing bytes áp dụng cho **một payload độc lập**. Nếu giao thức gửi liên tiếp nhiều bản tin trên một socket, đọc thêm byte để “kiểm tra EOF” sẽ vô tình đụng sang bản tin kế tiếp hoặc chặn chờ; thay vào đó phải giải mã đúng chiều dài frame đã xác định.

Đây vẫn chỉ là một format dạy học: trước khi triển khai thật, cần định nghĩa miền ID, tên rỗng/`null`, giới hạn **toàn bộ** payload, checksum hoặc xác thực khi cần, và hành vi khi có dữ liệu hỏng/trường mới.

## 6. Java Object Serialization hoạt động khác ra sao?

Java Object Serialization được thiết kế để ghi/đọc **đối tượng Java** và mối quan hệ giữa các đối tượng:

~~~java
ObjectOutputStream out = new ObjectOutputStream(outputStream);
out.writeObject(object);

ObjectInputStream in = new ObjectInputStream(inputStream);
Object restored = in.readObject();
~~~

Đây là **mảnh mã** với nguồn/đích byte và biến `object` đã có; cần khai báo ngoại lệ và đóng tài nguyên đúng quyền sở hữu.

Các ý quan trọng:

- Lớp muốn được serialize bằng cơ chế mặc định thường triển khai **`java.io.Serializable`**, một *marker interface* không khai báo phương thức công khai bắt buộc.
- `ObjectOutputStream` ghi thông tin theo **Java serialization stream protocol**, bao gồm metadata lớp và dữ liệu đối tượng; nó không chỉ ghi các trường theo thứ tự do bạn hình dung.
- Một đồ thị có thể chứa nhiều đối tượng, các tham chiếu chia sẻ và chu trình. Cơ chế **handles** giúp bảo toàn quan hệ tham chiếu thích hợp khi ghi/đọc trong cùng stream.
- `ObjectInputStream.readObject()` phục hồi đối tượng và có thể yêu cầu các định nghĩa lớp Java tương ứng; có thể ném `ClassNotFoundException`, `InvalidClassException`, `StreamCorruptedException`, `IOException` và các lỗi khác.
- Không phải bất kỳ object nào cũng serialize được. Nếu một trường cần được serialize giữ giá trị thuộc lớp không serializable, ghi có thể ném **`NotSerializableException`**.
- Trường **`static`** thuộc lớp, không phải trạng thái riêng của object để serialize mặc định. Trường **`transient`** bị loại khỏi serialization mặc định; giá trị sau đọc cần được khôi phục/khởi tạo theo logic ứng dụng nếu quan trọng.
- Có các điểm mở rộng như `writeObject/readObject`, `readResolve/writeReplace` và `Externalizable`. Chúng tăng tính linh hoạt nhưng cũng làm logic serialization phức tạp và tăng rủi ro khi đọc dữ liệu ngoài kiểm soát.

Bạn **không chủ động định nghĩa byte offset cho từng trường** chỉ bằng việc khai báo `implements Serializable`. Một chương trình khác không dùng Java serialization protocol không thể đơn giản đọc các byte này như một chuỗi `int32 + UTF-8`.

## 7. Ví dụ Java 17+: serialize đối tượng và giữ tham chiếu dùng chung

Tạo file **`JavaSerializationDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class JavaSerializationDemo {
    static final class Snapshot implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final int id;
        private final String name;

        Snapshot(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public String toString() {
            return "Snapshot[id=" + id + ", name=" + name + "]";
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Snapshot person = new Snapshot(7, "An");
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(person);
            out.writeObject(person); // Cùng một instance lần thứ hai.
        }

        // Chỉ đọc dữ liệu được CHÍNH chương trình này tạo ra.
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {

            Snapshot first = (Snapshot) in.readObject();
            Snapshot second = (Snapshot) in.readObject();

            System.out.println("first=" + first);
            System.out.println("sameReference=" + (first == second));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JavaSerializationDemo.java
java JavaSerializationDemo
~~~

Stdout:

~~~text
first=Snapshot[id=7, name=An]
sameReference=true
~~~

Vì sao `sameReference=true`?

- `ObjectOutputStream` có cơ chế nhận diện một object đã được ghi trong **cùng stream**, dùng tham chiếu tới object đó thay vì luôn tạo nội dung object độc lập.
- Khi `ObjectInputStream` đọc tham chiếu, nó phục hồi đúng việc hai vị trí cùng trỏ đến một object trong đồ thị đã deserialize.
- Điều này khác với hai bản ghi riêng biệt trong format tự thiết kế: cùng dữ liệu `id/name` **không tự động** có nghĩa cùng một object identity sau decode.

Trong format tự thiết kế, nếu cần chia sẻ reference hoặc xử lý chu trình, thường phải gán ID đối tượng, biểu diễn quan hệ và giải quyết reference qua nhiều bước. Nếu chỉ lưu record độc lập, thường **không cần** ngữ nghĩa này.

**Cảnh báo sử dụng:** demo serialize và deserialize chính payload do chương trình vừa tạo. Không thay nguồn trong ví dụ bằng byte gửi từ Internet, file upload hoặc nội dung không tin cậy rồi gọi `readObject()` trực tiếp.

## 8. `serialVersionUID` giúp gì và không giúp gì?

Với lớp serializable thông thường, `serialVersionUID` là mã phiên bản liên quan đến cơ chế tương thích của lớp:

~~~java
@java.io.Serial
private static final long serialVersionUID = 1L;
~~~

Gán tường minh có thể tránh phụ thuộc vào UID tự tính của lớp; UID tự tính có thể bị ảnh hưởng bởi những thay đổi khai báo không chủ ý. Nhưng **giữ nguyên UID không tự biến mọi thay đổi thành tương thích**.

Ví dụ:

- Thêm/bỏ một số trường trong thay đổi tương thích có thể được cơ chế serialization mặc định xử lý theo quy tắc của Java; trường mới có thể nhận giá trị mặc định.
- Thay đổi bản chất lớp, kiểu trường hoặc quan hệ kế thừa có thể phá vỡ khả năng đọc hoặc ngữ nghĩa, dù UID vẫn được giữ.
- Khi UID của stream và lớp không tương thích, có thể gặp `InvalidClassException`.
- `serialVersionUID` **không phải số version của format byte do bạn tự đặc tả**, không phải checksum, chữ ký hay biện pháp xác thực nguồn.
- Lớp ứng dụng vẫn phải xử lý invariant, dữ liệu cũ và migration khi trường thay đổi.

Với format tự thiết kế, version được ghi là **một trường trong header** và decoder của bạn quyết định chính xác cách đọc mỗi version. Với Java serialization, tương thích còn phụ thuộc vào cấu trúc lớp và cơ chế của Java; không nên dùng nó làm lời hứa định dạng bền vững chỉ nhờ một UID.

## 9. Thiết kế tương thích và nâng cấp schema

### Định dạng tự thiết kế

Bạn kiểm soát chiến lược tiến hóa. Ví dụ:

- **V1**: `id:int32`, `name:utf8`.
- **V2**: thêm `age`, hoặc chuyển sang bản ghi dạng TLV (*type–length–value*) để parser có thể bỏ qua trường không nhận diện.
- Decoder kiểm tra header version, rẽ nhánh đọc đúng schema, điền giá trị mặc định có chủ đích khi đọc dữ liệu cũ.
- Nếu muốn decoder cũ đọc được bản mới, format phải thiết kế **forward compatibility** từ trước, chẳng hạn mỗi frame/field có độ dài và quy tắc bỏ qua phần chưa biết.

Không tự tiện nối thêm trường `age` vào sau mỗi record V1 trong một stream không có kích thước bản ghi rõ ràng: decoder V1 có thể hiểu byte của `age` thành phần đầu bản ghi tiếp theo. Thay đổi số trường mà không đổi version hoặc không có cơ chế skip là cách dễ làm file hỏng.

Một schema thực tế nên quy định: version nào được hỗ trợ, default cho trường thiếu, trường bắt buộc, nullable, danh sách có/không giữ thứ tự, độ dài tối đa, encoding, unknown field policy, và quy trình migrate.

### Java serialization

Bạn giữ được một số ngữ nghĩa object graph, nhưng việc thay đổi cấu trúc lớp ảnh hưởng khả năng đọc dữ liệu cũ. Ngoài `serialVersionUID`, hãy chú ý class/package name, kiểu trường, serializable fields, kế thừa và logic hook.

Nếu cần lưu tài liệu 5–10 năm, chia sẻ giữa nhiều phiên bản dịch vụ hoặc trao đổi với Go/Python/Rust, nên ưu tiên một **giao thức/scheme được phiên bản hóa rõ ràng**, có tài liệu độc lập và bộ test tương thích. Có thể dùng định dạng tự thiết kế khi đủ đơn giản, hoặc cân nhắc một format/schema chuẩn khi yêu cầu liên ngôn ngữ và evolution phức tạp.

## 10. Bảo mật: vì sao không deserialize Java object từ dữ liệu không tin cậy?

**`ObjectInputStream.readObject()` không phải chỉ là đọc các field vô hại.** Java deserialization có thể tải/khôi phục các loại đối tượng và kích hoạt các cơ chế của lớp trong quá trình dựng lại đồ thị (ví dụ callback/hook thích hợp). Khi ứng dụng cho phép dữ liệu ngoài kiểm soát chỉ định các object/class được phục hồi, các class có sẵn trên classpath và chuỗi hành vi liên quan có thể tạo ra rủi ro nghiêm trọng.

Đây là lý do tài liệu Oracle cảnh báo **deserialization of untrusted data is inherently dangerous and should be avoided**. Nguyên tắc chính:

1. **Không dùng Java native deserialization cho payload do bên không tin cậy cung cấp**, kể cả khi đã “kiểm tra vài byte đầu” hoặc dự đoán rằng chỉ có một kiểu object.
2. Nếu hệ thống legacy **bắt buộc** phải deserialize, dùng `ObjectInputFilter`/cơ chế lọc serialization theo Java version và ngữ cảnh; giới hạn class được phép, độ sâu, số reference, độ dài array và lượng byte đọc.
3. Áp dụng giới hạn tổng payload, authentication/integrity, cách ly và kiểm toán classpath/callback; filter chỉ là một lớp phòng vệ, **không thay thế** thiết kế giao thức an toàn.
4. Không xem `serialVersionUID`, `transient` hoặc cast sang một class dự kiến sau `readObject` là biện pháp ngăn payload độc hại. Tác dụng phụ có thể xảy ra **trước** khi cast hoàn tất.
5. Với endpoint nhận dữ liệu từ ngoài, ưu tiên parser của format xác định rõ field và ràng buộc; kiểm soát tất cả input length và dữ liệu nhận được trước khi cấp phát hoặc chạy logic nghiệp vụ.

`ObjectInputFilter` có từ Java 9 và hỗ trợ lọc lớp/array/đồ thị, nhưng cấu hình filter phải phù hợp **toàn bộ** đồ thị và policy bảo mật của ứng dụng. Đừng dùng bộ lọc quá rộng và coi hệ thống đã an toàn tuyệt đối.

### Format nhị phân tự thiết kế có tự động an toàn không?

**Không.** Parser tự viết vẫn có thể sai khi nhận length âm, số đếm quá lớn, phép cộng số nguyên tràn, frame bị cắt, UTF-8 không hợp lệ hoặc payload khiến cấp phát quá nhiều bộ nhớ.

Những kiểm tra tối thiểu với dữ liệu từ bên ngoài:

- Giới hạn tổng frame/payload ngay từ tầng nhận trước khi sao chép cả dữ liệu vào RAM.
- Kiểm tra magic, version và tất cả count/length **trước khi cấp phát** hoặc lặp.
- Dùng `readFully`/vòng tích lũy cho dữ liệu có length cố định, xử lý EOF sớm.
- Kiểm tra length nằm trong số byte còn lại khi decode một payload đóng kín.
- Từ chối UTF-8 malformed nếu contract yêu cầu; xác định policy cho giá trị bất hợp lệ/unknown.
- Quy định checksum để phát hiện hỏng dữ liệu vô ý khi cần; **checksum thường không chứng minh nguồn đáng tin cậy**. Muốn xác thực/chống sửa đổi có chủ đích cần cơ chế mật mã phù hợp.
- Giới hạn CPU, nesting, chu kỳ và bộ nhớ, không chỉ mỗi một trường string.
- Xem parser như ranh giới đầu vào: lỗi phải kết thúc có kiểm soát, không trở thành thao tác nghiệp vụ hoặc ghi đè file ngoài ý muốn.

Ưu điểm của format đơn giản là bạn **có thể giới hạn rõ những kiểu dữ liệu được tạo** (ví dụ int/string/record) mà không yêu cầu JVM dựng lại class tùy ý; độ an toàn vẫn phụ thuộc vào cách triển khai parser.

## 11. Lỗi thường gặp khi đọc/ghi dữ liệu nhị phân

### Lỗi 1: ghi và đọc không cùng thứ tự

~~~java
// Bên ghi:
out.writeInt(12);
out.writeLong(999L);

// Bên đọc SAI:
long x = in.readLong();
int y = in.readInt();
~~~

Hai bên phải thống nhất thứ tự trường. Đây là **mảnh mã** với `out` và `in` phù hợp; nếu đảo như trên, dữ liệu có thể bị giải nghĩa sai mà không có compile error.

### Lỗi 2: nhầm byte length với số ký tự

~~~java
String name = "Bình";
int wrongLength = name.length(); // 4 UTF-16 char, nhưng 5 byte UTF-8
byte[] utf8 = name.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int correctLength = utf8.length;  // 5
~~~

Nếu header ghi 4 mà payload thực là 5 byte, mọi trường kế tiếp có thể lệch vị trí.

### Lỗi 3: chỉ gọi `read(byte[])` một lần

Một lần `read` có thể trả về ít byte hơn yêu cầu. Khi schema ghi name length `N`, phải lặp cho đến khi đủ `N` byte, hoặc dùng `DataInputStream.readFully`. EOF giữa chừng phải là lỗi frame bị cắt, không chuyển byte chưa đọc thành ký tự rỗng.

### Lỗi 4: cấp phát trước khi kiểm tra length

~~~java
int length = in.readInt();
// SAI nếu length đến từ dữ liệu không tin cậy:
byte[] bytes = new byte[length];
~~~

`length` có thể âm hoặc rất lớn. Kiểm tra giới hạn domain, tổng payload và lượng bộ nhớ cho phép trước khi cấp phát.

### Lỗi 5: dùng `writeUTF` như UTF-8 phổ thông

`writeUTF` dùng modified UTF-8 có length 2 byte và giới hạn 65535 byte; đừng ghi nó rồi dùng decoder UTF-8 tiêu chuẩn của giao thức ngoài Java. Nếu chọn modified UTF-8, hãy ghi rõ trong đặc tả và dùng `readUTF` tương ứng.

### Lỗi 6: nghĩ `Serializable` nghĩa là “ổn định vĩnh viễn”

Class thay đổi, cấu trúc đồ thị và quy tắc compatible serialization có thể thay đổi khả năng đọc. `serialVersionUID` không tự xử lý migration hay đảm bảo giữ ngữ nghĩa nghiệp vụ.

### Lỗi 7: tưởng Java serialization giữ nguyên byte khi serialize cùng giá trị

Một stream có thể chứa class descriptors, references và trạng thái phụ thuộc trình tự ghi. Không thiết kế test bằng cách đoán size byte hoặc so sánh thô như một định dạng thủ công đã chuẩn hóa. Để kiểm thử Java serialization, kiểm tra round-trip object và các quan hệ reference/invariant cần giữ.

### Lỗi 8: đưa byte không tin cậy vào `readObject`

Không dùng `ObjectInputStream` như decoder chung của dữ liệu bên ngoài. Dùng parser/schema có ràng buộc và chính sách bảo mật; lọc serialization chỉ dành cho trường hợp legacy bắt buộc và là **một phần** của phòng vệ.

### Lỗi 9: quên phân biệt format và transport

TCP là **dòng byte**, không có ranh giới bản tin mặc định. Một lần `write` bên gửi không nhất thiết tương ứng một lần `read` bên nhận. Cần có độ dài frame/terminator và xử lý partial read, timeout. Hai chương trình cùng dùng `DataInputStream` không tự tạo ra message framing.

### Lỗi 10: tưởng magic/version/chính sách length bảo đảm tính toàn vẹn

Magic giúp nhận diện format, version giúp giải mã tương thích, length giúp biết ranh giới; chúng **không** là bằng chứng dữ liệu không bị sửa. Định dạng cần chống lỗi vô ý có thể dùng checksum; cần xác thực đối tác và nội dung thì chọn giao thức/mã xác thực phù hợp.

## 12. Khi nào chọn cách nào?

**Chọn format nhị phân có schema tự định nghĩa** khi cần:

- Đọc được từ Java lẫn ngôn ngữ khác, hoặc dữ liệu tồn tại độc lập với một class cụ thể.
- Format nhỏ, rõ byte order, dễ kiểm thử bằng vector hex/golden files.
- Định nghĩa chính xác version, field, giới hạn, framing và hành vi backward/forward compatibility.
- Dữ liệu từ file/network bên ngoài cần parser với tập kiểu dữ liệu hữu hạn.
- Thiết bị nhúng, dữ liệu nhị phân tối ưu, hoặc giao thức đã có đặc tả tương ứng.

**Cân nhắc Java serialization** khi:

- Cần giữ đồ thị object và tham chiếu dùng chung giữa các object Java.
- Hai đầu đều là môi trường Java **tin cậy**, kiểm soát classpath, lớp serializable và version.
- Vòng đời dữ liệu ngắn hoặc có chiến lược duy trì tương thích/migration rõ ràng.
- Chấp nhận overhead và coupling với mô hình lớp Java, và đã đánh giá rủi ro deserialize.

Đối với API công khai, dữ liệu lưu dài hạn, giao tiếp liên ngôn ngữ hoặc dữ liệu nhập từ bên ngoài, lựa chọn một schema độc lập với implementation Java thường phù hợp hơn. Nếu schema trở nên phức tạp, không nhất thiết phải tự viết parser: các công cụ/định dạng có đặc tả như Protocol Buffers, Avro, CBOR... có thể giúp quản lý giao thức (mỗi loại có giới hạn và model tương thích riêng).

## 13. Quy trình thiết kế một định dạng nhị phân đáng tin cậy

1. **Định nghĩa use case**: file độc lập, stream nhiều frame, network payload hay cache? Có cần tìm kiếm ngẫu nhiên và nén không?
2. **Viết byte specification**: magic, version, endianness, kiểu số (signed/unsigned), charset, length, nullable, thứ tự trường, byte dư và ranh giới frame.
3. **Chọn version policy**: khi nào tăng version, cách đọc version cũ, cách bỏ unknown field, có cần migration batch?
4. **Đặt giới hạn**: max frame, record, field, name byte length, nesting, tổng cấp phát và thời gian xử lý.
5. **Viết encoder/decoder độc lập theo schema**: không truyền trực tiếp object graph chưa kiểm soát sang bên nhận.
6. **Tạo golden vectors**: với một bản ghi nhỏ, chốt byte hex mong đợi; decoder phải đọc đúng, encoder phải tạo đúng. Test cả tiếng Việt/Unicode, zero length, giá trị biên.
7. **Test sai/hỏng**: magic sai, version lạ, count âm, length quá lớn, thiếu một byte, dữ liệu dư, UTF-8 malformed, overflow.
8. **Kiểm tra interoperability**: nếu có client khác ngôn ngữ, chạy round-trip chéo chứ không chỉ round-trip cùng một implementation.
9. **Xác định failure semantics**: file ghi một phần, checksum, atomic replace, timeout, retry và sự cố mất kết nối.
10. **Bảo trì spec như API công khai**: thay đổi có version, tài liệu, fixture và chính sách hỗ trợ dữ liệu cũ.

## 14. Câu hỏi tự kiểm tra

**1.** Hai dịch vụ cùng dùng Java. Nếu muốn đọc byte bằng Python trong tương lai, nên chọn gì?  
**Đáp án:** Một format có schema và encoding đặc tả độc lập Java (tự thiết kế hoặc chuẩn có sẵn), không giả định native Object Serialization phù hợp với Python.

**2.** `DataOutputStream.writeInt` dùng endianness nào?  
**Đáp án:** Big-endian (byte trọng số cao trước). Nếu format cần little-endian, bạn phải thiết kế/triển khai rõ, chẳng hạn dùng `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` thích hợp.

**3.** Vì sao `writeUTF("Bình")` không đồng nghĩa `write(getBytes(UTF_8))`?  
**Đáp án:** `writeUTF` thêm độ dài 2 byte và dùng modified UTF-8, còn `getBytes(UTF_8)` tạo byte UTF-8 tiêu chuẩn không tự thêm length.

**4.** `ObjectOutputStream` ghi cùng instance hai lần vào cùng stream; object sau khi đọc có giữ quan hệ tham chiếu không?  
**Đáp án:** Thông thường có, nhờ cơ chế handles trong Java serialization; demo `sameReference=true` minh họa trường hợp đó.

**5.** Chỉ định `serialVersionUID = 1L` có đảm bảo đọc được mọi phiên bản lớp không?  
**Đáp án:** Không. Cần tuân thủ quy tắc tương thích của Java serialization và giữ invariant/migration theo thay đổi thực tế.

**6.** Sau khi đọc `nameLength` từ file không tin cậy, bước tiếp theo là gì?  
**Đáp án:** Kiểm tra phạm vi hợp lệ, giới hạn tối đa, số byte frame còn lại và ngân sách bộ nhớ; chỉ sau đó cấp phát và `readFully`.

**7.** Có nên dùng `new ObjectInputStream(socket.getInputStream()).readObject()` trên dữ liệu client không kiểm soát?  
**Đáp án:** Không. Java deserialization từ dữ liệu không tin cậy có rủi ro cao; dùng schema/parser được kiểm soát và các biện pháp xác thực/giới hạn cần thiết.

**8.** Định dạng tự thiết kế có cần version nếu hôm nay chỉ có một loại bản ghi?  
**Đáp án:** Nếu dữ liệu có thể được lưu lâu dài hoặc trao đổi giữa các phiên bản, nên có chính sách version ngay từ đầu để có thể phát hiện và xử lý thay đổi tương lai.

**Ghi nhớ:** `DataInputStream`/`DataOutputStream` là **công cụ để hiện thực format byte do bạn kiểm soát**. `ObjectInputStream`/`ObjectOutputStream` là **cơ chế Java để ghi/đọc đồ thị đối tượng**. Chọn theo hợp đồng dữ liệu, tuổi thọ, tương thích, quyền sở hữu schema và mức độ tin cậy của nguồn; đừng chọn chỉ vì API nào có ít dòng code hơn.

## Tham khảo API Java 17

- [DataOutput — cách mã hóa kiểu nguyên thủy và modified UTF-8](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html)
- [DataInputStream — cách đọc dữ liệu nhị phân](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [ObjectInputStream — Java serialization và cảnh báo dữ liệu không tin cậy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter — lọc lớp và giới hạn đồ thị khi deserialization](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)