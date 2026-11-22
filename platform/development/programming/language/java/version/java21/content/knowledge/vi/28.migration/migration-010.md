# Giữ tương thích hợp đồng dữ liệu, serialization và giao tiếp hệ thống

Khi nâng ứng dụng lên Java 21, việc source code biên dịch và JVM khởi động thành công chưa đủ để kết luận migration an toàn. Ứng dụng còn phải đọc được dữ liệu đã lưu từ phiên bản cũ, trao đổi đúng định dạng với service khác và duy trì hợp đồng mà consumer đang sử dụng. Các rủi ro thường nằm ở `serialVersionUID`, thay đổi class model, default charset UTF-8 từ JDK 18, thư viện serialization dùng reflection vào JDK internals và cách các hệ thống xử lý field mới hoặc giá trị chưa biết.

Nguyên tắc quan trọng là tách hợp đồng dữ liệu bên ngoài khỏi cấu trúc class Java nội bộ. Với giao tiếp giữa service hoặc lưu trữ lâu dài, ưu tiên format có schema và quy tắc versioning rõ ràng như JSON có schema, Protocol Buffers hoặc Avro. Chỉ dùng Java Object Serialization trong phạm vi đã kiểm soát và có kế hoạch tương thích cùng chính sách lọc deserialization.

## 1. Xác định lớp tương thích cần bảo vệ

Một lần nâng JDK có thể ảnh hưởng đến nhiều hợp đồng khác nhau. Không nên gom tất cả thành một kiểm tra “ứng dụng chạy được”.

| Lớp tương thích | Câu hỏi cần trả lời | Ví dụ kiểm tra |
|---|---|---|
| Binary/API compatibility | Class và method mà code đã biên dịch phụ thuộc còn truy cập được không? | Chạy application và thư viện trên JDK 21; kiểm tra lỗi linkage |
| Serialized-data compatibility | Phiên bản mới có đọc được file/blob đã ghi bởi phiên bản cũ không? | Đọc fixture serialization tạo từ bản phát hành trước |
| Wire-contract compatibility | Producer và consumer khác phiên bản có hiểu cùng message không? | Test old producer → new consumer và new producer → old consumer |
| Text/encoding compatibility | Byte được giải mã thành đúng ký tự trên mọi môi trường không? | Kiểm tra UTF-8, file cấu hình, CSV, log và message text |
| Semantic compatibility | Giá trị null, thiếu field, enum mới, timestamp và số thập phân có còn cùng ý nghĩa không? | Contract test và kiểm thử dữ liệu biên |
| Security compatibility | Serializer, parser và deserializer còn hoạt động với chính sách module và filter mới không? | Test filter, quyền truy cập reflection và payload không hợp lệ |

Binary compatibility của class Java không đồng nghĩa với tương thích của dữ liệu đã serialize. Một class có thể biên dịch bình thường nhưng không đọc được blob cũ; ngược lại, một JSON payload vẫn hợp lệ nhưng consumer mới có thể diễn giải sai khi default hoặc timezone thay đổi.

## 2. Giữ hợp đồng dữ liệu độc lập với class Java

Class Java là chi tiết triển khai. Tên class, package, field và cấu trúc object có thể thay đổi trong quá trình refactor; hợp đồng trao đổi với service khác cần ổn định hơn.

Ví dụ một event JSON có schema version rõ ràng:

```json
{
  "schemaVersion": 2,
  "eventType": "order.created",
  "eventId": "evt-7f31",
  "occurredAt": "2026-11-16T09:30:00Z",
  "orderId": "ORD-1042",
  "currency": "VND",
  "total": "125000.00"
}
```

Các trường trong message là tên và kiểu dữ liệu của hợp đồng. Chúng không cần trùng với tên class hoặc field Java. Ứng dụng có thể ánh xạ message sang DTO, record hoặc domain model riêng.

Một hợp đồng tốt cần xác định rõ:

- Tên field, kiểu dữ liệu, đơn vị và ý nghĩa nghiệp vụ.
- Field bắt buộc, field tùy chọn và giá trị mặc định khi field bị thiếu.
- Sự khác nhau giữa field không xuất hiện, field có giá trị `null` và field có giá trị rỗng.
- Cách consumer xử lý field chưa biết và enum value mới.
- Định dạng timestamp, timezone, số thập phân và encoding.
- Quy tắc versioning, thời gian hỗ trợ phiên bản cũ và cách loại bỏ field.

Không dùng tên Java class làm discriminator cho message nếu không có một protocol được thiết kế riêng cho điều đó. Không để thay đổi package hoặc đổi tên class nội bộ vô tình trở thành thay đổi wire contract.

## 3. Thay đổi schema theo hướng tương thích

Với JSON, Avro, Protocol Buffers hoặc format có schema, thay đổi additive thường dễ triển khai hơn thay đổi phá vỡ hợp đồng. Tuy nhiên, một field mới chỉ thực sự tương thích khi cả producer và consumer có quy tắc xử lý rõ ràng.

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm field tùy chọn | Consumer cũ có thể từ chối field lạ | Cấu hình consumer theo schema để bỏ qua field chưa biết hoặc nâng consumer trước |
| Thêm field bắt buộc | Consumer cũ không gửi field; producer cũ không cung cấp field | Có default tương thích hoặc triển khai theo nhiều giai đoạn |
| Đổi tên field | Consumer cũ và mới chờ tên khác nhau | Giai đoạn chuyển tiếp đọc cả tên cũ và mới; chỉ ngừng ghi tên cũ sau khi consumer đã nâng cấp |
| Xóa field | Consumer cũ vẫn cần field đó | Ngừng sử dụng trước, đo usage, rồi mới loại bỏ sau thời gian tương thích |
| Đổi kiểu field | Có thể mất dữ liệu hoặc parse thất bại | Thêm field mới với tên/version mới, chuyển đổi có kiểm soát |
| Thêm enum value | Consumer cũ có thể lỗi khi gặp giá trị chưa biết | Thiết kế nhánh unknown/other hoặc giữ mã chuỗi mở rộng |
| Thay đổi ý nghĩa field nhưng giữ nguyên tên | Payload vẫn parse nhưng nghiệp vụ bị sai | Tạo field/version mới và ghi rõ semantics |

Một quy trình rolling deployment thường an toàn hơn khi nâng consumer trước: consumer mới có thể đọc cả payload cũ và payload mới; sau đó mới nâng producer để gửi field mới. Chỉ xóa field cũ khi không còn consumer nào phụ thuộc vào nó.

### Phân biệt missing, null và empty

Ba trạng thái sau không nhất thiết tương đương:

```json
{}
```

```json
{ "note": null }
```

```json
{ "note": "" }
```

Chúng có thể lần lượt mang nghĩa “producer chưa gửi thông tin”, “producer biết giá trị không tồn tại” và “giá trị tồn tại nhưng rỗng”. Hợp đồng phải xác định ý nghĩa và consumer không nên tự gộp ba trạng thái nếu nghiệp vụ phân biệt chúng.

### Enum cần có chiến lược cho giá trị mới

Nếu consumer ánh xạ trực tiếp mọi giá trị chuỗi sang Java `enum`, một enum value mới có thể làm quá trình deserialize thất bại. Với giao thức cần khả năng mở rộng, có thể giữ giá trị gốc dưới dạng chuỗi trong DTO và ánh xạ các giá trị đã biết sang enum nội bộ; giá trị chưa biết được chuyển tới nhánh xử lý rõ ràng.

Không mặc định giá trị unknown là một trạng thái nghiệp vụ an toàn. Ví dụ, consumer thanh toán không nên diễn giải một trạng thái mới thành `SUCCESS` hoặc tự động tiếp tục giao dịch. Nhánh unknown phải có quyết định nghiệp vụ: từ chối, cách ly, ghi nhận hoặc chuyển xử lý thủ công.

## 4. Java Object Serialization và serialVersionUID

`Serializable` cho phép Java ghi object graph thành serialization stream và khôi phục nó sau này. Runtime sử dụng `serialVersionUID` (SUID) để kiểm tra class ghi và class đọc có tương thích serialization hay không.

Với class thông thường triển khai `Serializable`, nên khai báo SUID tường minh:

```java
import java.io.Serial;
import java.io.Serializable;

final class CustomerSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String customerId;
    private String displayName;
}
```

Nếu không khai báo, JVM tính SUID mặc định dựa trên nhiều chi tiết của class như tên, interface, field, method và constructor. Thay đổi cấu trúc class hoặc khác biệt giữa compiler có thể làm giá trị tính được thay đổi và gây `InvalidClassException` khi đọc stream cũ.

SUID tường minh chỉ giữ ổn định mã nhận diện phiên bản serialization; nó không làm cho mọi thay đổi class trở nên tương thích. Nếu đổi kiểu field, thay đổi hierarchy hoặc thay đổi format dữ liệu tùy chỉnh, stream vẫn có thể không đọc được dù SUID giống nhau.

### Những thay đổi field thường gặp

| Thay đổi class | Khi class mới đọc stream cũ | Khi class cũ đọc stream mới |
|---|---|---|
| Thêm field instance | Field mới nhận giá trị mặc định của kiểu nếu stream không có dữ liệu | Class cũ bỏ qua field bổ sung trong stream |
| Bỏ field instance | Dữ liệu field cũ không còn được gán vào class mới | Field mà class cũ mong đợi có thể nhận giá trị mặc định vì stream mới không ghi nó |
| Đổi kiểu field primitive | Có thể không tương thích với kiểu được ghi trong stream | Có thể không tương thích theo chiều ngược lại |
| Đổi `static`/`transient` làm thay đổi tập field serialize | Có thể mất dữ liệu hoặc nhận default | Có thể mất dữ liệu hoặc nhận default |
| Thay đổi vị trí class trong hierarchy | Có thể làm cấu trúc dữ liệu stream không khớp | Có thể làm cấu trúc dữ liệu stream không khớp |

Tính tương thích có hướng. Khi lưu blob lâu dài hoặc triển khai rolling upgrade, phải kiểm tra cả old writer → new reader và new writer → old reader nếu hệ thống cần hỗ trợ cả hai chiều. Đừng kết luận “thêm field là luôn an toàn” mà không kiểm tra default value và invariant của object.

Nếu field mới cần giá trị khác default `null`, `0` hoặc `false`, có thể cần logic khôi phục tương thích trong `readObject` cho class thường. Logic đó phải được kiểm thử với stream của từng phiên bản được hỗ trợ.

## 5. Lưu ý khi dùng record làm kiểu dữ liệu Serializable

Record có semantics serialization riêng. Record có thể triển khai `Serializable`, nhưng quá trình khôi phục object gọi canonical constructor sau khi các component được đọc. Vì vậy, validation trong constructor vẫn có thể được thực thi khi deserialization.

```java
import java.io.Serializable;

record PaymentSnapshot(String paymentId, long amountMinorUnits)
        implements Serializable {

    PaymentSnapshot {
        if (paymentId == null || paymentId.isBlank()) {
            throw new IllegalArgumentException("paymentId is required");
        }
        if (amountMinorUnits < 0) {
            throw new IllegalArgumentException("amountMinorUnits must be non-negative");
        }
    }
}
```

Các điểm cần lưu ý khi record là dữ liệu serialization:

- SUID mặc định của record là `0L`; quy tắc yêu cầu SUID phải khớp giữa hai phía được miễn cho record theo serialization specification.
- Component được khôi phục qua canonical constructor.
- Component mới không có trong stream cũ nhận giá trị mặc định của kiểu trước khi truyền vào canonical constructor.
- Các method tùy chỉnh `writeObject`, `readObject`, `readObjectNoData`, `writeExternal` và `readExternal` của record bị bỏ qua trong serialization process.
- `writeReplace` và `readResolve` vẫn có thể được sử dụng theo quy tắc serialization của record.

Nếu canonical constructor từ chối dữ liệu khi khôi phục, quá trình deserialization thất bại bằng `InvalidObjectException`. Vì vậy, invariant mới được thêm vào record có thể khiến payload cũ không còn hợp lệ; cần kiểm thử các fixture lịch sử trước khi triển khai.

Chuyển một DTO class cũ thành record có thể ảnh hưởng đến cách khôi phục object, invariant và dữ liệu component. Nếu record được dùng trong file hoặc message lưu lâu dài, hãy kiểm tra bằng fixture được ghi từ phiên bản cũ; không chỉ kiểm tra round-trip trong cùng một build.

## 6. Bảo vệ Java deserialization bằng ObjectInputFilter

Deserialization dữ liệu không đáng tin cậy vốn nguy hiểm. Object graph có thể chứa class không mong đợi, cấu trúc lồng sâu, số lượng reference lớn hoặc array rất lớn. Không dùng `ObjectInputStream.readObject()` trực tiếp với dữ liệu từ client, message broker hoặc file không kiểm soát.

Java 21 có `ObjectInputFilter` để giới hạn class được khôi phục và các đặc tính của object graph. Có thể đặt filter cho từng stream:

```java
import java.io.ObjectInputFilter;
import java.io.InvalidObjectException;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.InputStream;
import java.util.Set;

static PaymentSnapshot readSnapshot(InputStream source)
        throws IOException, ClassNotFoundException {
    Set<Class<?>> allowed = Set.of(
            PaymentSnapshot.class,
            String.class
    );

    ObjectInputFilter filter = info -> {
        if (info.depth() > 20
                || info.references() > 10_000
                || info.streamBytes() > 1_000_000
                || info.arrayLength() > 100_000) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        return allowed.contains(type)
                ? ObjectInputFilter.Status.ALLOWED
                : ObjectInputFilter.Status.REJECTED;
    };

    try (ObjectInputStream input = new ObjectInputStream(source)) {
        input.setObjectInputFilter(filter);
        Object value = input.readObject();
        if (value instanceof PaymentSnapshot snapshot) {
            return snapshot;
        }
        throw new InvalidObjectException("Unexpected root object type");
    }
}
```

Danh sách class trong ví dụ chỉ là allowlist minh họa cho một object graph nhỏ; ứng dụng thực tế phải liệt kê đúng mọi kiểu cần thiết, gồm cả kiểu component, superclass và array nếu payload có sử dụng. Không mở rộng allowlist thành toàn bộ classpath chỉ để làm cho một payload bất kỳ đọc được.

Filter giới hạn class và cấu trúc object graph; nó không thay thế kiểm tra dữ liệu nghiệp vụ sau khi khôi phục. Sau `readObject()`, vẫn cần xác minh range, độ dài chuỗi, trạng thái, quyền sở hữu và invariant của dữ liệu.

### Filter toàn JVM và filter theo ngữ cảnh

Với ứng dụng có nhiều thành phần deserialization, có thể cấu hình filter toàn JVM qua `jdk.serialFilter` hoặc `ObjectInputFilter.Config.setSerialFilter(...)`. JDK 17 trở lên còn có filter factory theo ngữ cảnh theo JEP 415; ứng dụng có thể chọn hoặc kết hợp filter cho từng `ObjectInputStream` dựa trên call path, module, class loader hoặc context đã xác định.

Chọn policy theo use case cụ thể. Một filter quá rộng làm giảm tác dụng bảo vệ; một filter quá hẹp có thể làm hỏng payload hợp lệ sau khi nâng thư viện. Hãy kiểm thử filter với fixture hợp lệ, payload sai định dạng và object graph vượt giới hạn.

## 7. Ưu tiên schema-based format cho giao tiếp giữa hệ thống

Java Object Serialization gắn dữ liệu với class descriptor và quy tắc của Java. Nó không phải một wire contract độc lập ngôn ngữ. Khi producer và consumer được viết bằng ngôn ngữ khác nhau, hoặc khi cần lưu dữ liệu qua nhiều thế hệ ứng dụng, format có schema thường dễ quản lý hơn.

| Nhu cầu | Hướng tiếp cận |
|---|---|
| HTTP API giữa service | JSON với OpenAPI/JSON Schema hoặc hợp đồng API tương đương |
| Event/message có schema tiến hóa | Avro hoặc Protocol Buffers với quy tắc tương thích được kiểm tra |
| File dữ liệu trao đổi giữa nhiều ngôn ngữ | Format công khai có schema, version và encoding được xác định |
| Lưu object nội bộ ngắn hạn trong cùng ứng dụng | Java serialization chỉ khi có lý do rõ ràng, filter và kiểm thử versioning |
| Cache có thể xóa và tái tạo | Cân nhắc format cache có version/key namespace rõ ràng; không dựa vào blob Java serialization lâu dài nếu không cần |

Không có một format nào tự bảo đảm tương thích. JSON cũng có thể phá vỡ consumer nếu đổi field, đổi kiểu hoặc đổi semantics. Schema registry cũng không thay thế contract test. Điểm quan trọng là hợp đồng phải độc lập với class Java và có quy tắc kiểm tra compatibility trong CI.

## 8. Kiểm tra UTF-8 khi nâng từ JDK 17 trở xuống

Từ JDK 18, UTF-8 là default charset của Java SE APIs trên mọi hệ điều hành. Ở JDK 17 trở xuống, default charset phụ thuộc hệ điều hành và locale; ví dụ Windows có thể dùng code page như `windows-1252` hoặc `windows-31j`.

Nếu ứng dụng dùng constructor không chỉ định charset, cùng một file có thể được đọc thành ký tự khác sau khi nâng JDK. Những API cần rà soát gồm `FileReader`, `FileWriter`, `InputStreamReader`, `OutputStreamWriter`, `Scanner` và `Formatter` khi dùng constructor dựa vào default charset.

Với file hoặc protocol có encoding xác định, chỉ định charset ngay tại boundary:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static String readUtf8(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}

static void writeUtf8(Path path, String content) throws IOException {
    Files.writeString(path, content, StandardCharsets.UTF_8);
}
```

Với byte stream:

```java
Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(payload, StandardCharsets.UTF_8);
```

Không dựa vào `Charset.defaultCharset()` để định nghĩa wire format. Default charset là lựa chọn runtime; encoding của protocol phải là một phần của hợp đồng.

### Console không dùng default charset như file API

`System.out` và `System.err` sử dụng charset của console, không nhất thiết là `Charset.defaultCharset()`. Khi kiểm tra lỗi encoding, hãy phân biệt byte của file/protocol với cách terminal hiển thị output. Một terminal hiển thị sai không tự chứng minh dữ liệu đã được ghi sai.

### Lưu ý đặc biệt với Properties

JEP 400 không thay đổi quy tắc encoding riêng của `Properties`:

- `Properties.load(InputStream)` và `store(OutputStream, ...)` sử dụng ISO-8859-1 cùng Unicode escape theo hợp đồng API.
- `Properties.load(Reader)` và `store(Writer, ...)` làm việc với character stream; charset do Reader/Writer quyết định.
- `loadFromXML` và `storeToXML` hỗ trợ UTF-8 và UTF-16 theo API.

Nếu file `.properties` của ứng dụng được định nghĩa là UTF-8, hãy tạo Reader/Writer tường minh:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties properties = new Properties();

try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}

try (Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    properties.store(writer, "Application settings");
}
```

Không đổi từ `load(InputStream)` sang `load(Reader)` hoặc ngược lại mà không xác định encoding thật của file hiện có. Cần giữ khả năng đọc dữ liệu cấu hình cũ hoặc chuyển đổi file một lần có kiểm tra.

## 9. Giữ timestamp, locale và số liệu ổn định trên wire

Một số lỗi migration không đến từ serializer mà từ việc ứng dụng dùng format dành cho hiển thị làm dữ liệu giao tiếp.

### Timestamp và timezone

Không gửi `LocalDateTime` nếu consumer cần biết một thời điểm tuyệt đối mà không có timezone. Dùng một instant có offset rõ ràng, thường chuẩn hóa UTC:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

Instant occurredAt = Instant.now();
String wireValue = DateTimeFormatter.ISO_INSTANT.format(occurredAt);
```

Ví dụ wire value: `2026-11-16T09:30:00Z`. Nếu nghiệp vụ cần giờ địa phương, truyền thêm region/offset theo hợp đồng; không dựa vào timezone mặc định của server.

### Locale và định dạng số

Không serialize kết quả của `NumberFormat` hoặc `DateTimeFormatter` theo locale máy chủ như một giá trị máy cần parse lại. Dấu thập phân, dấu phân nhóm, tên tháng và currency display có thể phụ thuộc locale data của JDK. Dùng kiểu dữ liệu và format machine-readable được định nghĩa rõ, ví dụ decimal theo schema hoặc chuỗi ISO-8601 cho timestamp.

Với tiền tệ, xác định currency code và scale/rounding rule. Nếu dùng JSON number, kiểm tra consumer có giữ độ chính xác thập phân hay không; một số runtime chuyển số thành binary floating point. Có thể dùng decimal string theo schema hoặc một kiểu decimal được hỗ trợ rõ ràng ở cả hai phía.

## 10. Thư viện serializer và strong encapsulation

JDK 17 trở lên strongly encapsulate nhiều API nội bộ. Thư viện serializer, ORM hoặc mapper cũ có thể dùng reflection để truy cập private field hoặc method của `java.*` và gặp `InaccessibleObjectException` khi chạy trên Java 21.

Khi nâng ứng dụng:

1. Cập nhật serializer, ORM, framework HTTP, JDBC driver và message client lên phiên bản hỗ trợ JDK 21.
2. Kiểm tra stack trace để xác định thư viện đang mở reflective access vào package nào.
3. Ưu tiên API công khai, constructor, accessor hoặc cơ chế extension được thư viện hỗ trợ.
4. Nếu cần `--add-opens` như giải pháp chuyển tiếp, chỉ mở đúng module/package cho đúng module đích và ghi rõ dependency cần được loại bỏ.
5. Không dựa vào `--illegal-access`; tùy chọn này không còn khôi phục quyền truy cập reflection cũ trên JDK 17 trở lên.

Ví dụ cú pháp cho một package cụ thể; chỉ nên cân nhắc sau khi đã xác định chính xác thư viện và package cần truy cập:

```bash
java \
  --add-opens java.base/java.util=ALL-UNNAMED \
  -jar application.jar
```

Đây là ví dụ cú pháp, không phải option mặc định nên thêm cho mọi ứng dụng. `ALL-UNNAMED` mở package cho tất cả code trên classpath nên phạm vi khá rộng; nếu thư viện nằm trong named module, hãy chỉ định module đích phù hợp. Giải pháp lâu dài là cập nhật thư viện để không cần truy cập JDK internals.

Chạy `jdeps -jdkinternals` trên artifact của ứng dụng và thư viện nội bộ để phát hiện tham chiếu đến JDK internal APIs. Công cụ phân tích tĩnh không phát hiện đầy đủ truy cập được tạo bằng reflection, vì vậy vẫn cần chạy integration test và kiểm tra log khi thực thi.

## 11. Kiểm thử tương thích trước và sau khi nâng JDK

Một bộ kiểm thử migration nên giữ lại payload thật từ phiên bản đang chạy, không chỉ tạo fixture mới bằng class mới.

| Kiểm thử | Mục tiêu |
|---|---|
| Old writer → new reader | Bản Java 21 đọc được file/blob đã ghi bởi bản cũ |
| New writer → old reader | Consumer cũ đọc được payload mới trong giai đoạn rolling deployment nếu yêu cầu hỗ trợ chiều này |
| Old producer → new consumer | Consumer mới vẫn xử lý event cũ |
| New producer → old consumer | Producer mới không phá consumer cũ trong thời gian chuyển tiếp |
| Missing optional field | Default và invariant được áp dụng đúng |
| Unknown field/enum value | Consumer có chiến lược bỏ qua, giữ lại hoặc từ chối đúng nghiệp vụ |
| Null, empty và malformed data | Validation không nhầm trạng thái hoặc gây lỗi không kiểm soát |
| UTF-8 non-ASCII | Tiếng Việt, ký tự supplementary và dữ liệu nhiều ngôn ngữ được giữ nguyên |
| Deserialization filter | Payload hợp lệ được đọc; class và object graph không được phép bị từ chối |
| Library reflection | Serializer/mapper chạy được trên JDK 21 mà không phụ thuộc quyền mở rộng không cần thiết |

### Dùng golden fixtures từ phiên bản cũ

Lưu payload mẫu đã được tạo bởi từng phiên bản phát hành còn được hỗ trợ. Trong test mới, đọc những file đó bằng code hiện tại và so sánh dữ liệu nghiệp vụ sau khi khôi phục. Không tạo lại toàn bộ fixture bằng class mới trong cùng test run, vì cách đó chỉ chứng minh round-trip trong một phiên bản.

Với wire contract, có thể giữ JSON/Avro/Protobuf mẫu trong repository test hoặc dùng contract test giữa producer và consumer. Mỗi thay đổi schema cần kiểm tra tương thích trước khi deploy.

## 12. Quy trình rollout khi producer và consumer nâng cấp khác thời điểm

Một hệ thống phân tán thường không thể nâng tất cả service cùng lúc. Quy trình expand-and-contract giúp giảm rủi ro:

1. **Expand consumer:** triển khai consumer mới có thể đọc payload cũ và payload mới, nhưng producer vẫn chưa gửi field mới.
2. **Expand schema:** thêm field tùy chọn hoặc version mới theo schema registry/API contract; chưa xóa field cũ.
3. **Expand producer:** triển khai producer gửi field mới sau khi mọi consumer cần thiết đã hỗ trợ.
4. **Observe:** theo dõi parse error, unknown value, retry, dead-letter và metric theo schema version.
5. **Contract:** chỉ bỏ field cũ sau khi xác nhận không còn consumer hoặc dữ liệu lưu trữ cần nó.

Đối với database, áp dụng nguyên tắc tương tự: thêm cột nullable hoặc có default tương thích trước; triển khai code đọc/ghi cả hai nếu cần; backfill dữ liệu; sau đó mới bỏ cột cũ khi tất cả phiên bản ứng dụng đã ngừng sử dụng.

Không dùng một lần deploy Java 21 để đồng thời đổi schema, đổi serializer, đổi timezone và đổi cấu trúc database nếu không cần thiết. Tách thay đổi giúp xác định nguyên nhân khi contract test hoặc production behavior thất bại.

## 13. Checklist migration dữ liệu và tích hợp

1. Liệt kê mọi nơi ứng dụng đọc/ghi dữ liệu: file, database blob, cache, HTTP, message broker và RPC.
2. Xác định format, schema version, charset, timezone và owner của từng contract.
3. Lưu fixture từ phiên bản cũ; kiểm thử old writer → new reader và chiều ngược lại khi cần.
4. Với Java serialization, kiểm tra `serialVersionUID`, field type, class hierarchy, custom serialization và record semantics.
5. Không deserialize dữ liệu không đáng tin cậy; cấu hình `ObjectInputFilter` theo use case và giới hạn object graph.
6. Ưu tiên format schema-based cho giao tiếp liên service hoặc lưu trữ dài hạn.
7. Xác định quy tắc field optional/required, missing/null/empty, enum unknown và schema evolution.
8. Chỉ định UTF-8 hoặc charset của protocol tại mọi boundary; kiểm tra riêng `Properties.load(InputStream)`.
9. Chuẩn hóa timestamp, timezone, locale, currency và decimal precision trong wire format.
10. Nâng serializer, ORM, JDBC driver và client library hỗ trợ Java 21; kiểm tra strong encapsulation.
11. Chạy `jdeps -jdkinternals` và integration test; nhớ rằng reflection động có thể không xuất hiện trong kết quả `jdeps`.
12. Triển khai consumer trước producer khi cần rolling compatibility; chỉ xóa field cũ sau khi hết dependency.
13. Theo dõi lỗi parse, `InvalidClassException`, `InaccessibleObjectException`, encoding mismatch và dead-letter sau rollout.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html)
- [Oracle Java SE 21 Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Java Object Serialization Specification — Versioning of Serializable Objects](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/version.html)
- [Java Object Serialization Specification — Serialization of Records](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/serial-arch.html)
- [Java SE 21 API — Serializable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html)
- [Java SE 21 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
- [Java SE 21 API — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
