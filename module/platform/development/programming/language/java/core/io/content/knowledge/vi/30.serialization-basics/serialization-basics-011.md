# Khác biệt với định dạng trao đổi có schema độc lập Java

## 1. Tuần tự hóa một đối tượng Java khác với thiết kế giao thức trao đổi

**Serialization** chuyển trạng thái dữ liệu thành byte/text để lưu trữ hoặc truyền đi; **deserialization** đọc biểu diễn đó trở lại dữ liệu hay đối tượng. Java có sẵn `ObjectOutputStream`, `ObjectInputStream` và interface `Serializable`. Chúng triển khai **Java Object Serialization Stream Protocol**, chủ yếu phục vụ việc khôi phục các đối tượng/đồ thị đối tượng Java.

Trong khi đó, một **định dạng trao đổi có schema độc lập Java** (chẳng hạn JSON + hợp đồng dữ liệu, Protocol Buffers, Avro hoặc binary format được đặc tả đầy đủ) nhằm định nghĩa message có thể được Java, Go, Python hay JavaScript tạo và hiểu mà không cần sử dụng chính class Java của bên gửi.

Cần phân biệt hai mục tiêu:

1. **Object persistence/transport nội bộ Java:** khôi phục state và đồ thị tham chiếu theo quy tắc Java; lớp đọc phải tương thích với serial form của lớp ghi.
2. **Interoperability và data contract:** hai ứng dụng, có thể khác ngôn ngữ và chu kỳ phát hành, trao đổi các trường nghiệp vụ thông qua field identifiers, types, optional/default semantics và wire encoding được thỏa thuận.

**Điểm chính:** việc Java ghi một `byte[]` không khiến định dạng mặc nhiên độc lập Java. Ngược lại, một codec được viết bằng Java vẫn có thể tuân thủ schema độc lập Java nếu định dạng byte được mô tả/kiểm thử ngoài ngôn ngữ ấy.

## 2. Cơ chế Java Object Serialization

Ví dụ một class:

~~~java
import java.io.Serial;
import java.io.Serializable;

final class Profile implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int id;
    private final String name;

    Profile(int id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

Đây là class minh họa, không phải chương trình chạy độc lập. `Serializable` là marker interface; Java Object Serialization lưu dữ liệu theo serial form của class. Mặc định các instance fields đủ điều kiện được tuần tự hóa; `static` fields không phải trạng thái của instance, `transient` fields bị loại khỏi default serial form. Những class/hook đặc biệt có quy tắc riêng.

Để ghi/đọc đối tượng:

~~~java
try (ObjectOutputStream out = new ObjectOutputStream(destination)) {
    out.writeObject(profile);
}

try (ObjectInputStream in = new ObjectInputStream(source)) {
    Profile restored = (Profile) in.readObject();
}
~~~

Đây là **mã minh họa**: `destination` và `source` là hai stream liên quan tới cùng bộ bytes, `profile` đã được khai báo, có imports và xử lý `IOException`/`ClassNotFoundException`. Các `try-with-resources` sẽ đóng stream được bọc: phù hợp khi code sở hữu stream, nhưng cần xem hợp đồng nếu stream được mượn từ caller.

Khi ghi, Java protocol có thể chứa:

- Stream header và các dấu điều khiển protocol.
- Class descriptors chứa định danh/serial form của những lớp liên quan.
- Dữ liệu fields, tham chiếu object và handles duy trì cấu trúc đồ thị/alias.
- Dữ liệu tùy biến từ `writeObject` hoặc các cơ chế substitution, externalization nếu class hỗ trợ.

Khi đọc, `ObjectInputStream` giải quyết class trong Java runtime, kiểm tra tương thích serial form rồi dựng đối tượng. Những hook như `readObject`, `readResolve` có thể chạy logic được định nghĩa bởi class; không thể coi đây chỉ là “đọc JSON thành map”.

Java stream chuẩn có header `AC ED 00 05` ở đầu (hex). Header không giải quyết vấn đề đa ngôn ngữ: một consumer không chạy Java vẫn phải triển khai đầy đủ Java serialization semantics và các class/graph rules để đọc loại dữ liệu này.

### Những dữ liệu không tự được khôi phục hữu ích

Serialization không biến resource trong JVM thành resource sống ở process khác. Ví dụ socket đang kết nối, thread đang chạy, file descriptor hoặc lock native không được “nhân bản” có ý nghĩa chỉ vì một class implement `Serializable`. Các field `transient` cần được tái thiết lập khi cần. Với object graph có tham chiếu tới loại không serializable, có thể gặp `NotSerializableException`.

## 3. serialVersionUID không phải schema version của một API

`serialVersionUID` thuộc về **serializable class Java** và dùng trong kiểm tra compatibility giữa dữ liệu trong stream với class local khi giải mã. Nếu không khai báo, Java có thể tính default UID dựa trên chi tiết class; vì thế việc khai báo tường minh thường hợp lý cho class chủ động dùng Java Serialization.

Tuy nhiên:

- Giữ nguyên UID **không bảo đảm mọi thay đổi class đều tương thích**. Thay đổi loại field, class hierarchy hoặc custom serialization logic có thể phá việc đọc hoặc semantics.
- Đổi package/class name có thể làm class resolution thất bại dù dữ liệu nghiệp vụ nhìn có vẻ giống.
- UID không mô tả field number, kiểu dữ liệu và default theo một schema có thể triển khai độc lập trong Python hay Go.
- Không nên “chữa” mọi `InvalidClassException` bằng việc chỉnh UID cho trùng rồi bỏ qua nguyên nhân.

Ngược lại, **schema version** của một message là một phần của hợp đồng trao đổi mà các ngôn ngữ đều có thể hiểu. Một DTO schema `Profile v2` có thể thêm field `points` mà không đòi hỏi class Java nội bộ giữ nguyên package, superclass hay business methods.

Ngay cả schema version cũng **không tự tạo tương thích**; phải định nghĩa behavior khi dữ liệu mới có field chưa biết, dữ liệu cũ thiếu field, hoặc một trường bị đổi nghĩa.

## 4. Thế nào là schema độc lập Java?

Một schema mô tả **hình dạng dữ liệu và quy tắc diễn giải** mà không cần biết runtime class của producer. Ví dụ:

~~~text
Message: Profile
id      : signed 32-bit integer, required by business
name    : UTF-8 text, non-empty, max 1024 encoded bytes
points  : signed 64-bit integer, default 0 if omitted by agreed schema
Version : 1
Unknown-field handling, null/absence and invalid-input behavior are explicit
~~~

Đây là đặc tả khái niệm, không phải cú pháp của một schema framework cụ thể. Dữ liệu wire cần quy định rõ thêm: encoding, byte order nếu binary, length framing, numeric overflow, nullability, trường chưa biết, version, timestamp/unit và điều kiện xác thực.

Khác với một serialized object Java, **consumer không cần có class `com.example.Profile`**. Consumer Python có thể đọc ID/points/name vào struct hoặc dictionary của nó, miễn cả hai thực thi đúng schema/wire contract.

Không phải mọi định dạng tự nó đều bao gồm schema đầy đủ:

- JSON cung cấp syntax và loại dữ liệu cơ bản nhưng không tự ép schema; thường kết hợp với OpenAPI, JSON Schema và kiểm tra ứng dụng.
- Protobuf định nghĩa message/field numbers trong `.proto`, codec nhiều ngôn ngữ.
- Avro sử dụng writer/reader schemas trong cơ chế schema resolution; binary datum đơn lẻ có thể cần schema truyền riêng, trong khi object container file có định dạng header chứa schema.
- Custom binary format có thể độc lập Java nếu **bản đặc tả** được công bố và được nhiều implementation kiểm chứng. `DataOutputStream` tự nó không phải một schema language.

## 5. Bảng đối chiếu cốt lõi

| Tiêu chí | Java Object Serialization | Schema độc lập Java |
| --- | --- | --- |
| Trọng tâm | Object/graph state Java | Message/DTO contract |
| Gắn class Java của producer | Có, thông qua serial form/class resolution | Không bắt buộc |
| Wire format | Java Object Serialization protocol | JSON/Protobuf/Avro/custom specification |
| Hỗ trợ Go/Python/JS | Không mặc nhiên | Thiết kế để hỗ trợ khi codec/schema phù hợp |
| Version | `serialVersionUID`, quy tắc Java compatibility | Schema/wire version, field number/name, rules |
| Object identity/cycle | Protocol có thể bảo toàn alias/object graph | Thường cần mô hình hóa graph rõ nếu có |
| Lưu trữ lâu dài | Phụ thuộc code/serial form Java | Có thể quản lý schema/migration ổn định hơn |
| Security của input | `readObject` có rủi ro object/gadget hooks | Vẫn cần parse limits/validation, nhưng thường không tái tạo class Java tùy ý |
| Debug | Binary và phụ thuộc Java protocol | JSON dễ đọc; binary schema codecs có tooling |
| Hiệu năng/kích thước | Phụ thuộc object graph/protocol | Phụ thuộc codec và dữ liệu, phải benchmark |
| Schema evolution | Phụ thuộc thay đổi class/serial form | Có quy tắc evolution được quản lý rõ |
| Coupling | Data format dễ dính model Java nội bộ | Có thể tách external DTO khỏi domain model |

Không có định dạng nào tự động “an toàn/nhanh/tương thích tuyệt đối”. Lợi thế của schema độc lập là **hợp đồng dữ liệu có thể review và kiểm thử xuyên ngôn ngữ, phát triển tách khỏi chi tiết class Java**.

## 6. JSON có schema: dễ dùng nhưng phải kiểm soát kiểu

Một bản tin JSON:

~~~json
{
  "schemaVersion": 1,
  "id": 7,
  "name": "Lan",
  "points": 120
}
~~~

Java có thể tạo nó bằng JSON library/codec; không cần dùng `ObjectOutputStream`. Hợp đồng cần quy định:

- `id` có bắt buộc hay không, phạm vi hợp lệ là gì.
- `points` là signed 64-bit integer hay loại khác. JavaScript `Number` không biểu diễn chính xác mọi số nguyên lớn hơn `2^53-1`; schema liên ngôn ngữ cần chiến lược phù hợp cho long/decimal.
- `name` có thể null, rỗng, chứa Unicode normalization nào, giới hạn bytes/chars thế nào.
- Field chưa biết có bị reject/bỏ qua không; thiếu field có default ra sao.
- Timestamp/timezone, money units, định danh và enum values đều cần quy tắc nhất quán.
- Parser phải giới hạn payload size/nesting và validate trước khi map sang domain.

**JSON không đồng nghĩa JSON Schema.** JSON Schema/OpenAPI và contract tests mô tả/kiểm tra những yêu cầu ngoài cú pháp JSON. Decoder đọc JSON hợp lệ nhưng không thỏa business rules vẫn phải từ chối.

## 7. Protocol Buffers: field numbers thay cho Java class identity

Một file `profile.proto` có thể khai báo:

~~~proto
syntax = "proto3";
package example.profile.v1;

message Profile {
  int32 id = 1;
  string name = 2;
  int64 points = 3;
}
~~~

Compiler/runtime Protobuf tạo API cho nhiều ngôn ngữ. Ý nghĩa của field number là thiết yếu: `1` đại diện field `id` trên wire, `2` là `name`, `3` là `points`. Consumer Go/Java/Python có thể diễn giải cùng wire format bằng schema tương thích.

Để tiến hóa schema an toàn:

1. Tránh đổi field number cho field đã triển khai.
2. Khi bỏ field, dùng `reserved` cho số/tên thích hợp để tránh tái sử dụng với ý nghĩa khác.
3. Với field mới, xác định behavior của consumer cũ khi bỏ qua field chưa biết và business logic có chấp nhận không.
4. Thận trọng khi đổi loại field, enum, oneof hoặc field presence.
5. Trong proto3, phân biệt default scalar value với explicit presence; nếu cần, dùng `optional` hay loại phù hợp.
6. Duy trì golden test vectors và backward/forward compatibility tests với các consumer thật.

Protobuf không tự cung cấp authorization, input trust, transaction hay schema registry. Các bài toán đó cần giải pháp tầng ứng dụng.

## 8. Apache Avro: writer schema và reader schema

Một schema Avro đơn giản:

~~~json
{
  "type": "record",
  "name": "Profile",
  "namespace": "example.profile",
  "fields": [
    {"name": "id", "type": "int"},
    {"name": "name", "type": "string"},
    {"name": "points", "type": "long", "default": 0}
  ]
}
~~~

Avro có quy tắc đối chiếu **writer schema** (đã dùng khi ghi) và **reader schema** (được consumer mong đợi), cho phép một số kiểu thay đổi phù hợp mà không buộc các lớp Java giống nhau.

Cần hiểu giới hạn:

- Một Avro **binary datum** đơn lẻ thường không tự chứa toàn bộ writer schema. Khi lưu message trên broker có thể cần schema registry/schema ID hoặc truyền metadata theo protocol.
- Avro object container file có cấu trúc riêng, header/schema metadata; không được suy luận mọi dạng Avro data đều giống file container.
- Thêm field có default, rename/alias, unions và type promotion phải theo quy tắc cụ thể. Thay đổi không tương thích có thể làm schema resolution thất bại.
- Mọi consumer vẫn phải hiểu **ý nghĩa** field; khả năng decode không bảo đảm semantics nghiệp vụ.

JSON, Protobuf và Avro đều là phương án có thể dùng trong hệ thống Java; lựa chọn tùy ecosystem, độ dễ quan sát, kích thước, versioning và performance benchmark.

## 9. Ví dụ Java 17+ hoàn chỉnh: hai cách ghi cùng Profile

Chương trình bên dưới viết cùng dữ liệu theo hai định dạng:

1. **Java Object Serialization**: `ObjectOutputStream` viết object có UID/class descriptor; `ObjectInputStream` đọc lại trong Java. Ví dụ có filter giới hạn class và tài nguyên đọc.
2. **Binary wire format được đặc tả ngoài Java class**: `DataOutputStream`/`DataInputStream` dùng header magic, version, fixed-width integers theo big-endian và length-prefixed UTF-8. Một decoder ở ngôn ngữ khác có thể triển khai từ bảng schema ở phần tiếp theo.

**Định dạng thứ hai là giao thức minh họa do bài tự đặt**, không phải một chuẩn thương mại hay Protobuf. Tính độc lập Java đến từ đặc tả bytes/validation chứ không phải vì dùng `DataOutputStream`.

Tạo tệp **`SchemaExchangeDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class SchemaExchangeDemo {
    private static final byte[] MAGIC = {'P', 'R', 'F', '1'};
    private static final int VERSION = 1;

    static final class Profile implements Serializable {
        @Serial private static final long serialVersionUID = 1L;
        final int id;
        final long points;
        final String name;

        Profile(int id, long points, String name) {
            this.id = id;
            this.points = points;
            this.name = name;
        }
    }

    static byte[] writeJava(Profile p) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(p);
        }
        return bytes.toByteArray();
    }

    static Profile readJava(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=20;maxbytes=4096;" +
                "SchemaExchangeDemo$Profile;java.base/*;!*"));
            return (Profile) in.readObject();
        }
    }

    static byte[] writeWire(Profile p) throws IOException {
        byte[] name = p.name.getBytes(StandardCharsets.UTF_8);
        if (name.length > 1024) throw new IOException("Name too long");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.write(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(p.id);
            out.writeLong(p.points);
            out.writeInt(name.length);
            out.write(name);
        }
        return bytes.toByteArray();
    }

    static Profile readWire(byte[] bytes) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes))) {
            byte[] magic = new byte[4];
            in.readFully(magic);
            if (!Arrays.equals(magic, MAGIC)) throw new IOException("Bad magic");
            int version = in.readInt();
            if (version != VERSION) throw new IOException("Unsupported version");
            int id = in.readInt();
            long points = in.readLong();
            int length = in.readInt();
            if (length < 0 || length > 1024) throw new IOException("Bad length");
            byte[] nameBytes = new byte[length];
            in.readFully(nameBytes);
            if (in.read() != -1) throw new IOException("Trailing bytes");
            return new Profile(id, points,
                    new String(nameBytes, StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws Exception {
        Profile original = new Profile(7, 120, "Lan");
        byte[] javaBytes = writeJava(original);
        byte[] wireBytes = writeWire(original);
        Profile restored = readJava(javaBytes);
        Profile exchanged = readWire(wireBytes);

        System.out.println("Java header: " +
                HexFormat.of().withUpperCase().formatHex(
                        Arrays.copyOf(javaBytes, 4)));
        System.out.println("Java roundtrip: " + restored.id + "|" +
                restored.name + "|" + restored.points);
        System.out.println("Wire magic: " +
                new String(Arrays.copyOf(wireBytes, 4), StandardCharsets.US_ASCII));
        System.out.println("Wire version: 1");
        System.out.println("Wire length: " + wireBytes.length);
        System.out.println("Wire roundtrip: " + exchanged.id + "|" +
                exchanged.name + "|" + exchanged.points);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SchemaExchangeDemo.java
java SchemaExchangeDemo
~~~

**Stdout chính xác**, đã biên dịch/chạy trên JDK:

~~~text
Java header: ACED0005
Java roundtrip: 7|Lan|120
Wire magic: PRF1
Wire version: 1
Wire length: 27
Wire roundtrip: 7|Lan|120
~~~

Giải thích:

- `ACED0005` là header của Java Serialization Stream Protocol, không cho biết schema trao đổi độc lập Java.
- `serialVersionUID=1L` được gắn với serial form của `SchemaExchangeDemo.Profile`; nó không phải version của hệ thống API đa ngôn ngữ.
- `ObjectInputFilter` trong ví dụ cho phép class cụ thể và giới hạn depth/references/bytes. Dù vậy **không được coi đây là bằng chứng ObjectInputStream an toàn cho dữ liệu không tin cậy**. Thực tế nên tránh Java native deserialization qua trust boundary.
- Nhánh wire ghi `PRF1` và version `1`; consumer bất kỳ ngôn ngữ nào có thể hiểu chúng nếu tuân theo byte layout được công bố.
- `writeInt`/`writeLong` ghi số theo **big-endian**; tên được mã hóa UTF-8, độ dài tính bằng **byte**, không tính Java `String.length()`.
- Tổng dung lượng là **4 + 4 + 4 + 8 + 4 + 3 = 27 bytes** với tên `Lan` có 3 byte UTF-8.
- Decoder minh họa kiểm tra magic, version, length tối đa 1024, bytes thiếu và trailing bytes. `readFully` ném lỗi khi stream kết thúc trước số byte yêu cầu.
- Decoder ví dụ dùng `new String(bytes, UTF_8)`. Điều này có thể thay thế malformed UTF-8 bằng ký tự replacement; hệ thống cần reject dữ liệu UTF-8 sai phải dùng `CharsetDecoder` với `CodingErrorAction.REPORT`.
- Ví dụ chưa áp đặt business validation (`id` phải dương, `name` không rỗng, `points` hợp lệ) và không chứng minh interop thực tế với Python/Go. Đó là những bài test cần thêm nếu triển khai.

### Bảng schema bytes của wire format v1

| Vị trí (byte offset) | Dung lượng | Kiểu | Nội dung |
| --- | ---: | --- | --- |
| 0–3 | 4 | ASCII | Magic `PRF1` |
| 4–7 | 4 | signed int32 big-endian | Version = 1 |
| 8–11 | 4 | signed int32 big-endian | `id` |
| 12–19 | 8 | signed int64 big-endian | `points` |
| 20–23 | 4 | signed int32 big-endian | UTF-8 byte length `0..1024` |
| 24 đến hết length | Biến đổi | UTF-8 | Bytes của `name`, không có NUL terminator |

Đây là định dạng **independent of Java implementation** nếu mọi producer/consumer cùng tuân thủ bảng. Nó **không tự có field tagging, unknown-field policy hay schema registry**. Nếu thay đổi layout v1, decoder cũ có thể từ chối trailing bytes; cần nâng version và code migration hoặc đổi sang format có field tags.

**Vì sao không dùng `DataOutputStream.writeUTF`?** Nó dùng **modified UTF-8** và một length prefix theo quy tắc Java, không phải trực tiếp mã hóa UTF-8 chuẩn mà các schema cross-language thường mô tả. Một contract liên ngôn ngữ phải ghi rõ encoding bytes và length prefix như ví dụ.

## 10. Backward compatibility và forward compatibility

Khi format/schema thay đổi, cần trả lời cả hai câu hỏi:

- **Backward compatibility:** reader mới đọc được dữ liệu do writer cũ tạo hay không?
- **Forward compatibility:** reader cũ đọc được dữ liệu do writer mới tạo hay không?

Với schema v1:

~~~text
Profile v1: id, name
Profile v2: id, name, points
~~~

Bảng tư duy:

| Reader / Writer | Rủi ro | Cách giảm |
| --- | --- | --- |
| Reader v2 ← Writer v1 | Không có points | Default/optional theo codec và ý nghĩa nghiệp vụ |
| Reader v1 ← Writer v2 | Có points chưa biết | Cơ chế bỏ qua unknown fields hoặc phiên bản tương thích |
| Reader mới ← Message rất cũ | Nhiều bước migration | Transitive compatibility/migration fixtures |
| Reader cũ ← Kiểu field bị đổi | Decoder hoặc business logic sai | Không đổi field number/meaning tùy tiện, dùng version mới |

**Có thể đọc được bytes không có nghĩa nghiệp vụ đúng.** Nếu field số đang chứa cents nhưng version mới diễn giải thành dollars, cả hai bên vẫn parse thành số nhưng kết quả sai. Cần phân biệt *wire compatibility* với *semantic compatibility*.

Với Protobuf, quy tắc field number/tagged field giúp bỏ qua một số field chưa biết nhưng không cứu được mọi thay đổi. Với Avro, writer-reader schema resolution hỗ trợ những thay đổi tương thích. Với JSON, behavior khi field unknown/default phụ thuộc JSON decoder và hợp đồng. Với custom binary format trong demo, reader v1 còn từ chối trailing bytes, nên đơn giản thêm field vào cuối **không forward compatible**.

Một kế hoạch nâng phiên bản an toàn cần golden messages, upgrade/downgrade tests, và thống kê consumer còn chạy ở các phiên bản cũ trước khi phát hành breaking change.

## 11. Bảo mật: vì sao ObjectInputStream không nên nhận payload tùy ý?

Native Java deserialization không chỉ parse primitive fields. `ObjectInputStream.readObject()` có thể tái tạo các instance, xử lý object graph, gọi các hook có side effects và kích hoạt class/library code. Điều này tạo nguy cơ gadget chain, DoS hoặc hành vi ngoài ý muốn nếu byte stream do attacker kiểm soát.

Các nguyên tắc:

1. **Không dùng Java native serialized objects làm định dạng đầu vào mặc định cho public HTTP/socket/message queues không tin cậy.**
2. Thay bằng DTO/schema và codec giới hạn kiểu dữ liệu, sau đó kiểm tra business validation trước khi sử dụng.
3. Nếu buộc phải hỗ trợ dữ liệu Java Serialization legacy, dùng `ObjectInputFilter`/filter factory theo JDK, allowlist class, giới hạn depth, refs, bytes, array lengths; đánh giá toàn bộ classpath.
4. Filter không phải sandbox và không loại bỏ mọi nguy cơ; cố gắng cô lập/loại bỏ đường giải Java object từ input không tin cậy.
5. JSON/Protobuf/Avro cũng cần giới hạn payload size, nesting, time và bảo vệ parser; codec không tự tạo authentication hay authorization.
6. Đừng deserializing dữ liệu cũ không rõ nguồn chỉ để “thử xem có đọc được không”; môi trường migration phải được bảo vệ.

Một số lỗi Java Serialization:

| Ngoại lệ | Tình huống thường thấy |
| --- | --- |
| `NotSerializableException` | Ghi đối tượng không đủ điều kiện serialization |
| `InvalidClassException` | Serial form không tương thích hoặc lớp bị từ chối |
| `ClassNotFoundException` | Class Java cần giải không có ở reader |
| `StreamCorruptedException` | Stream header/protocol data không hợp lệ |
| `ClassCastException` | Object được khôi phục khác expected type |
| `EOFException`/`OptionalDataException` | Thiếu dữ liệu hoặc đọc sai thứ tự |
| `IOException` | Lỗi đọc/ghi và những trường hợp khác |

Không sửa UID bừa để che `InvalidClassException`, không tắt filter chỉ vì một dữ liệu mẫu không qua được, và không nuốt ngoại lệ rồi xem payload đã được xử lý.

## 12. Lưu trữ lâu dài và tiến hóa mô hình

Một file Java serialized object được lưu năm trước có thể không còn đọc được sau khi đổi package/class, thay field types, sửa hierarchy hoặc thay custom serialization code. Ngay cả khi runtime đọc được, semantic của field có thể đã thay đổi.

Khi cần lưu lâu hoặc có nhiều consumer:

- Tách **external message schema** khỏi internal Java class.
- Gắn schema version/schema ID vào envelope hoặc container phù hợp.
- Quản lý quy tắc thêm/xóa/rename field theo codec thực tế.
- Lưu fixtures từ các version cũ để regression tests.
- Có migration đọc dữ liệu cũ trong môi trường được kiểm soát, chuyển thành DTO mới và validate.
- Có rollback policy nếu producer mới đã ghi dữ liệu mà consumer cũ chưa hiểu.
- Tách integrity/authentication/durability/atomic publish khỏi serialization contract.

Một database schema cũng là một loại contract dữ liệu; chọn schema exchange format không thay cho quản lý migrations ở tầng database.

## 13. DTO boundary thay vì expose domain Java

Không nên tự động dùng entity JPA hoặc object domain phức tạp làm network message. Một service có thể có model nội bộ:

~~~text
Java domain: Account(id, balanceCents, riskFlags, persistenceState)
                       |
                       | mapping + validation
                       v
Public DTO: ProfileV1(id, name, points)
                       |
                       | JSON / Protobuf / Avro encoder
                       v
Wire bytes ---------> Consumer in another language
~~~

Điểm lợi:

- Đổi implementation nội bộ không đương nhiên đổi contract.
- Tránh lộ field private/sensitive do class domain được mở rộng.
- Có nơi kiểm tra giá trị, business invariant và giới hạn kích thước.
- Tách tests cho mapping, codec và cross-language integration.
- Cho phép song song nhiều API schema version trong giai đoạn migration.

Đổi lại, có thêm DTO, mapping và schema governance. Với hệ thống nhiều dịch vụ/ngôn ngữ, chi phí này thường dễ quản lý hơn việc để wire phụ thuộc trực tiếp vào class Java.

## 14. Quy trình migration từ Java Serialization

Một hệ thống đang lưu `.ser`, session, cache hoặc queue bằng Java Object Serialization không thể thay reader sang JSON/Protobuf và mong đọc thẳng byte cũ.

Các bước:

1. Xác định chính xác tất cả nơi đang `writeObject/readObject` và class/serial UID liên quan.
2. Kiểm tra trust boundary, nguồn dữ liệu, hạn lưu trữ và phiên bản deployed.
3. Thiết kế schema/DTO mới chỉ gồm trường nghiệp vụ cần thiết; không mirror mọi Java field.
4. Xác định ID, default, version, unknown-field, encoding, constraints và error behavior.
5. Tạo adapter migration riêng để đọc dữ liệu legacy được tin cậy, qua filter/resource limits; map sang DTO và validate.
6. Đo/kiểm tra compatibility bằng message fixtures, contract tests và ít nhất một consumer non-Java nếu mục tiêu là interop.
7. Deploy hỗ trợ đọc các version cần thiết; tổ chức dual-write/backfill/on-read migration với idempotency và kiểm soát rollback.
8. Theo dõi decode errors, unknown fields, message sizes, schema versions và dữ liệu tồn backlog.
9. Gỡ bỏ native deserialization khi không còn dữ liệu/consumer cần hỗ trợ.

Nếu phải phân biệt định dạng trong thời gian chuyển đổi, nên có **format discriminator** rõ (magic/version/schema ID). Không liên tục thử đọc đầu vào bằng mọi decoder trên dữ liệu không tin cậy chỉ bằng cách bắt exception.

## 15. Những nhầm lẫn phổ biến

| Nhận định sai | Giải thích |
| --- | --- |
| “Serializable thì Python tự đọc được” | Python không mặc nhiên có Java Serialization protocol/class resolution |
| “serialVersionUID là API schema version” | UID thuộc serial form của Java class |
| “Giữ UID sẽ luôn đọc mọi class thay đổi” | Tương thích còn phụ thuộc trường/kiểu/class và semantics |
| “JSON có schema tự động” | JSON là syntax; schema/validation phải quy định |
| “Protobuf đổi số field tùy ý” | Field numbers định danh field trên wire và phải giữ ổn định |
| “Avro binary datum luôn đính kèm schema” | Có thể yêu cầu writer schema/schema ID ngoài |
| “DataOutputStream là chuẩn đa ngôn ngữ” | Phải công bố byte layout, encoding và version |
| “DataOutputStream.writeUTF dùng UTF-8 chuẩn” | Sử dụng modified UTF-8 của Java |
| “Đọc được bytes tức dữ liệu hợp lệ” | Cần kiểm tra business rules và semantic compatibility |
| “Bảo vệ bằng ObjectInputFilter là đủ” | Filter không phải sandbox cho input độc hại |
| “Có schema thì không cần migration” | Breaking change vẫn cần rollout và compatibility plan |
| “Wire compatible luôn semantic compatible” | Cùng bytes có thể mang ý nghĩa nghiệp vụ khác |
| “Binary luôn nhỏ/nhanh hơn JSON” | Phải benchmark với dữ liệu và codec thực tế |

## 16. Checklist khi chọn định dạng

1. Consumer có khác Java hay khác vòng đời triển khai không?
2. Dữ liệu có cần sống nhiều năm và chịu refactor class/package không?
3. Có schema được kiểm soát độc lập với implementation Java không?
4. Có quy tắc kiểu số, encoding, timezone, null/absence và enum chưa?
5. Có giới hạn độ dài, nesting, input trust và quyền truy cập không?
6. Có field identifiers và nguyên tắc không tái sử dụng field đã bỏ không?
7. Có backward/forward compatibility tests và golden fixtures không?
8. Có semantic validation sau khi giải mã không?
9. Có xác định explicit framing/schema ID và cách từ chối unsupported version không?
10. Có tách external DTO với ORM/domain object không?
11. Có quy trình migrate và rollback khi thay schema không?
12. Nếu dùng JSON, đã tính đến 64-bit precision và decimal chưa?
13. Nếu dùng Protobuf, đã hiểu field presence/default và unknown fields chưa?
14. Nếu dùng Avro, đã xác định nơi lấy writer schema chưa?
15. Nếu dùng custom binary, đã có đặc tả endian, length, malformed input và interop tests chưa?

## 17. Câu hỏi tự kiểm tra

1. `ObjectOutputStream` mặc định xuất JSON hoặc Protobuf không? **Không**; nó dùng Java Object Serialization Stream Protocol.
2. `serialVersionUID` làm một chương trình Go tự khôi phục object Java được không? **Không**.
3. Java Serialized object có gắn với serial form/class Java không? **Có**.
4. JSON có ép `points` phải là signed 64-bit integer không? **Không**; schema/validation cần quy định.
5. Protobuf nhận biết trường bằng gì? **Field number**.
6. Avro binary datum lúc nào cũng chứa schema đầy đủ không? **Không**.
7. Format `PRF1` của ví dụ vì sao có thể được Python decode? Vì byte layout, version, big-endian integer và UTF-8 length prefix được **đặc tả rõ**.
8. `DataOutputStream.writeUTF` có phải UTF-8 chuẩn trên wire không? **Không**, là modified UTF-8.
9. Decoder wire v1 có tự hỗ trợ thêm field sau tên không? **Không**, hiện tại nó từ chối trailing bytes.
10. Reader mới đọc dữ liệu writer cũ gọi là gì? **Backward compatibility** theo thuật ngữ thường dùng.
11. Reader cũ đọc dữ liệu writer mới gọi là gì? **Forward compatibility**.
12. Một message decode được nhưng đổi đơn vị cents thành dollars có còn đúng không? **Không**, semantics bị thay đổi.
13. `ObjectInputFilter` có cho phép nhận an toàn mọi byte stream không tin cậy không? **Không**.
14. Muốn migration dữ liệu Java serialized cũ sang Protobuf, chỉ đổi codec là đủ không? **Không**, cần đọc cũ có kiểm soát, map DTO và encode mới.
15. Có cần test consumer đa ngôn ngữ không? **Có**, nếu tương tác đa ngôn ngữ là yêu cầu.
16. Schema độc lập Java có nghĩa không cần chia sẻ bất cứ contract nào không? **Không**; producer và consumer phải chia sẻ đúng schema/wire semantics.

## Tài liệu tham khảo

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html), [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): Java Serialization API.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serial form và `serialVersionUID`.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): kiểm soát deserialization resource/classes.
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html), [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): big-endian primitives và modified UTF-8.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html): protocol và class evolution.
- [Protobuf proto3 language guide](https://protobuf.dev/programming-guides/proto3/): schema, field numbers và wire compatibility.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): binary encoding và schema resolution.
- [JSON Schema](https://json-schema.org/): mô tả schema và validation.
