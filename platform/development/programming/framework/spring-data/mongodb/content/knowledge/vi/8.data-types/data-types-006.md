# UUID representation, dữ liệu nhị phân và tương thích driver

## 1. Vì sao cùng một UUID vẫn có thể không truy vấn được?

Giả sử dịch vụ Java ghi mã giao dịch `00112233-4455-6677-8899-aabbccddeeff` vào MongoDB. Một dịch vụ Python cũng có đúng chuỗi UUID đó nhưng truy vấn không thấy document, trong khi trường tìm kiếm và collection đều đúng. Một khả năng quan trọng là hai dịch vụ **mã hóa UUID thành BSON Binary theo những quy ước khác nhau**.

UUID có giá trị logic 128 bit. MongoDB có thể lưu giá trị này dưới dạng BSON Binary 16 byte, nhưng một trường nhị phân còn có **binary subtype**; riêng một số quy ước UUID cũ còn khác nhau về **thứ tự byte**. Vì thế, hai giá trị có cùng dạng chuỗi UUID chưa chắc tạo ra cùng BSON.

Bài thuộc chương **Kiểu dữ liệu** của module **SPRING_DATA_MONGODB**. Trong Spring Data MongoDB, việc kết nối, ánh xạ document, thao tác bằng `MongoTemplate` hoặc repository, truy vấn, index, kiểm thử và chẩn đoán hiệu năng đều chịu ảnh hưởng của kiểu BSON thực tế. Hiểu UUID representation giúp tránh lỗi khi tích hợp các phiên bản driver, dịch vụ nhiều ngôn ngữ và dữ liệu tồn tại từ trước.

Sau bài này, bạn có thể:

1. Phân biệt UUID ở dạng chuỗi, UUID trong Java và BSON Binary có subtype.
2. Giải thích ý nghĩa của subtype `0x03` (UUID legacy) và `0x04` (UUID standard).
3. Nhận biết sự khác biệt giữa `STANDARD`, `JAVA_LEGACY`, `C_SHARP_LEGACY` và `PYTHON_LEGACY`.
4. Cấu hình rõ representation ở MongoDB Java driver và kiểm tra đường đi qua Spring Data MongoDB.
5. Thiết kế cách lưu `byte[]`, mã băm và payload nhị phân, kiểm tra interoperability, lên kế hoạch migration an toàn.

## 2. Tách ba lớp: UUID logic, byte và BSON Binary

### 2.1. UUID là một giá trị 128 bit

UUID thường được hiển thị thành chuỗi 36 ký tự, gồm 32 chữ số hexadecimal và 4 dấu gạch:

```text
00112233-4455-6677-8899-aabbccddeeff
```

Trong Java:

```java
import java.util.UUID;

UUID eventId = UUID.fromString(
    "00112233-4455-6677-8899-aabbccddeeff"
);

System.out.println(eventId.toString());
// 00112233-4455-6677-8899-aabbccddeeff
```

Java `UUID` lưu giá trị qua hai phần 64 bit. Cách giá trị được hiển thị thành chuỗi khác với việc một driver lựa chọn thứ tự 16 byte để ghi BSON. **UUID version** (ví dụ v4 hay v7) nói về cách UUID được tạo và diễn giải; **UUID representation** ở đây nói về cách driver ghi 16 byte và subtype BSON. Hai khái niệm không thay thế nhau.

### 2.2. BSON Binary có thêm subtype

Trong BSON, một giá trị Binary gồm dữ liệu nhị phân và một mã subtype. Các subtype đáng quan tâm:

| Subtype | Tên thường gặp | Mục đích |
| --- | --- | --- |
| `0x00` | Generic binary | Dữ liệu byte tùy ý như ảnh nhỏ, chữ ký, mã băm |
| `0x03` | UUID legacy | Cách lưu UUID của một số driver/quy ước cũ |
| `0x04` | UUID standard | UUID 16 byte theo thứ tự chuẩn |

Một UUID BSON Binary tiêu chuẩn cần **đúng subtype `0x04` và đúng 16 byte**. BSON String `"00112233-..."` có kiểu dữ liệu khác, dù nội dung chữ mô tả cùng UUID.

MongoDB so khớp giá trị nhị phân theo dữ liệu BSON. Khi truy vấn bằng một giá trị có subtype hoặc thứ tự byte khác với giá trị đã lưu, không thể mặc định MongoDB sẽ tự suy diễn chúng là cùng UUID.

### 2.3. So sánh ba cách lưu

```javascript
// Cách A: chuỗi. BSON String, không phải BSON Binary.
{ eventId: "00112233-4455-6677-8899-aabbccddeeff" }

// Cách B: UUID chuẩn. Trong mongosh, UUID(...) tạo UUID Binary subtype 4.
{ eventId: UUID("00112233-4455-6677-8899-aabbccddeeff") }

// Cách C: Binary legacy. Cần đúng byte và subtype 3 từ hệ thống cũ.
{ eventId: BinData(3, "<base64-cua-16-byte-legacy>") }
```

Chuỗi nằm trong dấu ngoặc nhọn của ví dụ C chỉ là **ký hiệu placeholder**, không phải Base64 hợp lệ để chạy. Muốn truy vấn legacy phải lấy byte thực tế và biết cách driver cũ mã hóa chúng. Không thể đổi mỗi con số `3` thành `4` rồi kết luận UUID đã được chuyển sang chuẩn.

## 3. STANDARD và các legacy representation

### 3.1. Cùng UUID logic, các byte có thể khác nhau

Để so sánh, lấy giá trị:

```text
00112233-4455-6677-8899-aabbccddeeff
```

Theo cách mã hóa UUID tiêu chuẩn, 16 byte (hexadecimal) là:

```text
00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
```

Các representation thường gặp trong MongoDB driver:

| Representation | BSON subtype | Thứ tự byte đối với UUID mẫu |
| --- | --- | --- |
| `STANDARD` | `0x04` | `00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff` |
| `PYTHON_LEGACY` | `0x03` | Giữ thứ tự byte chuẩn, nhưng subtype là legacy |
| `JAVA_LEGACY` | `0x03` | `77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88` |
| `C_SHARP_LEGACY` | `0x03` | `33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff` |

Với Java legacy, từng nửa 8 byte được đảo thứ tự; với C# legacy, những nhóm byte đầu theo quy ước cũ được đảo. Python legacy dùng thứ tự byte chuẩn nhưng mang subtype `0x03`. Ví dụ này cho thấy **subtype 3 không đủ để xác định thứ tự byte**: cần biết representation mà hệ thống đã sử dụng khi ghi.

### 3.2. Vì sao có nhiều kiểu legacy?

Các driver cũ từng chọn cách ánh xạ UUID riêng khi BSON chưa có quy ước UUID thống nhất trên các hệ sinh thái. Điều này gây tình huống:

- Java legacy và C# legacy cùng lưu subtype `0x03` nhưng byte có thể khác.
- Python legacy và standard có thể cùng 16 byte, nhưng khác subtype nên vẫn là hai BSON value khác nhau.
- Cùng driver Java, thay cấu hình representation giữa hai phiên bản dịch vụ có thể làm các bản ghi mới không khớp truy vấn với dữ liệu cũ.

**Quy ước nên dùng cho dữ liệu mới khi cần interoperable là `STANDARD`.** Không tự đổi cấu hình cho hệ thống đã có dữ liệu legacy mà chưa kiểm kê cách lưu và đường đi đọc/ghi cũ.

### 3.3. UNSPECIFIED nghĩa là gì?

MongoDB Java driver các thế hệ mới cung cấp `UuidRepresentation.UNSPECIFIED` nhằm tránh âm thầm chọn một cách mã hóa UUID có thể khác dữ liệu đang có. Khi đường đi mã hóa/giải mã cần xử lý Java `UUID`, thiếu representation rõ ràng có thể dẫn tới lỗi codec hoặc kết quả không được chuyển thành UUID như ứng dụng mong đợi.

Không nên suy ra «không cấu hình» luôn có nghĩa `STANDARD`: mặc định phụ thuộc driver, Spring Data, Spring Boot, custom codec và phiên bản thực tế. Hãy xác định **client nào đang sử dụng** và kiểm tra representation của nó, nhất là sau nâng cấp.

## 4. Dữ liệu nhị phân thông thường khác UUID

UUID chỉ là một ứng dụng cụ thể của BSON Binary. Nhiều dữ liệu khác cũng được lưu bằng mảng byte:

| Dữ liệu | Kiểu Java phổ biến | BSON phù hợp | Lưu ý |
| --- | --- | --- | --- |
| Mã giao dịch UUID | `java.util.UUID` | Binary subtype 4 nếu chuẩn hóa STANDARD | Giữ thống nhất representation xuyên driver |
| SHA-256 digest | `byte[32]` | Generic Binary `0x00` | 32 byte là digest, không phải UUID |
| Chữ ký số | `byte[]` | Generic Binary `0x00` | Không sửa byte hay dùng conversion UUID |
| Dữ liệu file nhỏ | `byte[]` | Generic Binary `0x00` | Cân nhắc kích thước document và cách truyền |
| Định danh bên ngoài dạng chuỗi | `String` | BSON String nếu contract quy định vậy | Không tự ép sang UUID |

MongoDB có giới hạn **16 MiB cho một document BSON**. Với file lớn hoặc tập tin cần stream, có thể sử dụng GridFS hoặc hệ thống lưu trữ đối tượng phù hợp, giữ metadata và khóa tham chiếu trong document. Không nên nhúng file lớn không giới hạn vào document nghiệp vụ.

### 4.1. Base64 là cách biểu diễn trong văn bản

Base64 giúp mang byte qua JSON hoặc giao diện text. Tuy nhiên, lưu Base64 dưới BSON String không giống lưu BSON Binary:

```java
import java.util.Base64;

byte[] digest = new byte[] { 0x01, 0x02, 0x03, 0x04 };
String encoded = Base64.getEncoder().encodeToString(digest);
byte[] decoded = Base64.getDecoder().decode(encoded);
```

Base64 làm tăng kích thước dữ liệu ký tự so với 4 byte gốc. BSON Binary giữ payload dưới dạng byte; Extended JSON có thể dùng Base64 **chỉ để thể hiện** giá trị BSON khi trao đổi hoặc kiểm tra. Bản thân chuỗi Base64 không mang sẵn thông tin về subtype nếu không có metadata đi kèm.

### 4.2. Không suy đoán UUID từ mọi Binary 16 byte

Một mã băm bị cắt còn 16 byte, khóa ngẫu nhiên 16 byte và một UUID đều dài 16 byte, nhưng có **ý nghĩa và contract khác nhau**. Cấu trúc dữ liệu phải quy định rõ field là UUID hay opaque bytes. Chỉ decode thành UUID khi schema và representation xác nhận điều đó.

## 5. Java driver: mã hóa và giải mã UUID tường minh

### 5.1. Sử dụng BsonBinary để tự kiểm tra representation

Ví dụ độc lập với network, minh họa API của MongoDB Java driver:

```java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

UUID id = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");

BsonBinary standard = new BsonBinary(id, UuidRepresentation.STANDARD);
BsonBinary javaLegacy = new BsonBinary(id, UuidRepresentation.JAVA_LEGACY);

System.out.println(standard.getType());   // 4  (subtype 0x04)
System.out.println(javaLegacy.getType()); // 3  (subtype 0x03)

UUID standardRead = standard.asUuid(UuidRepresentation.STANDARD);
UUID legacyRead = javaLegacy.asUuid(UuidRepresentation.JAVA_LEGACY);

System.out.println(standardRead.equals(id)); // true
System.out.println(legacyRead.equals(id));   // true
```

Hai phép đọc trên đều ra cùng UUID logic vì **bộ giải mã được cung cấp đúng representation ban đầu**. Điều này không có nghĩa hai giá trị BSON có thể thay thế cho nhau trong truy vấn MongoDB.

Bạn cũng có thể nhìn thấy byte thật qua `standard.getData()` và `javaLegacy.getData()`. Khi chẩn đoán, nên ghi rõ cả subtype và chuỗi hexadecimal của byte, vì việc in riêng `UUID.toString()` có thể che giấu sai khác trong lưu trữ.

### 5.2. Kiểm tra subtype và bytes qua Java

```java
import java.util.HexFormat;
import org.bson.BsonBinary;

static String describeBinary(BsonBinary binary) {
    return "subtype=" + (binary.getType() & 0xff)
        + ", hex=" + HexFormat.of().formatHex(binary.getData());
}
```

Đặt phương thức này vào class tiện ích trong dự án Java 17+ rồi gọi với `standard` và `javaLegacy` ở mục trên. Với dữ liệu thật, hạn chế in nội dung nhị phân nhạy cảm vào log; chỉ lấy mẫu an toàn khi debug.

### 5.3. Cấu hình MongoClientSettings

Khi ứng dụng tự khởi tạo MongoDB Java driver, nên quyết định UUID representation tường minh:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString("mongodb://localhost:27017"))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Dùng client cho các thao tác đọc/ghi hoặc kiểm thử tích hợp.
}
```

Ví dụ localhost là cấu hình minh họa. Trong production, lấy URI, thông tin xác thực, TLS, timeout và pool settings từ cấu hình bảo mật của ứng dụng. Đừng mở một `MongoClient` mới cho mỗi request; client nên được tái sử dụng và đóng khi ứng dụng kết thúc.

Trong hệ thống đang dùng subtype 3, hãy xác định dữ liệu được ghi bởi representation nào trước khi chuyển cấu hình sang STANDARD. Đổi cấu hình client không tự chuyển document đã lưu.

## 6. Spring Data MongoDB: UUID field và cách dùng đúng

### 6.1. Ví dụ document chứa UUID và bytes

Giả sử một dịch vụ lưu metadata của tài liệu đính kèm. Field `correlationId` là UUID, còn `sha256` là mã băm 32 byte và `content` là payload nhị phân nhỏ:

```java
import java.util.UUID;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("attachments")
public record Attachment(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    @Field("correlation_id") UUID correlationId,
    String contentType,
    byte[] sha256,
    byte[] content
) {}
```

Theo ý định thiết kế:

| Property Java | Field BSON | Kiểu mong muốn |
| --- | --- | --- |
| `id` | `_id` | String, do `@MongoId(FieldType.STRING)` |
| `tenantId` | `tenantId` | String |
| `correlationId` | `correlation_id` | Binary UUID subtype 4 |
| `contentType` | `contentType` | String |
| `sha256` | `sha256` | Generic Binary |
| `content` | `content` | Generic Binary |

**Điều kiện:** Mapping `UUID` thành subtype 4 phụ thuộc đường đi converter/codec và cấu hình representation phù hợp. `@Field("correlation_id")` chỉ thay tên trường, **không đặt UUID representation**. Cần kiểm tra BSON thực tế bằng integration test, vì custom conversions hoặc codec registry khác có thể thay đổi hành vi.

### 6.2. Đọc/ghi qua MongoTemplate và repository

```java
import java.util.UUID;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class AttachmentQueries {
    private final MongoTemplate template;

    public AttachmentQueries(MongoTemplate template) {
        this.template = template;
    }

    public List<Attachment> findByCorrelation(
        String tenantId, UUID correlationId
    ) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("correlationId").is(correlationId)
        );
        return template.find(query, Attachment.class);
    }
}
```

Spring Data có thể dịch `correlationId` thành `correlation_id` dựa trên metadata `Attachment.class`. Với kiểu UUID, phải kiểm tra rằng giá trị query được mã hóa thành **cùng subtype và thứ tự byte** với dữ liệu đã lưu. Một query đúng tên trường nhưng sai BSON value vẫn trả danh sách rỗng.

Ví dụ repository:

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AttachmentRepository
    extends MongoRepository<Attachment, String> {

    Optional<Attachment> findByTenantIdAndCorrelationId(
        String tenantId,
        UUID correlationId
    );
}
```

Đừng truyền `UUID.toString()` thay cho tham số `UUID` nếu contract của repository yêu cầu `UUID`; điều đó vừa khác kiểu Java vừa có thể khiến cách chuyển query không đúng ý định. Query trực tiếp qua driver với BSON String cũng không tự tương đương với UUID Binary.

### 6.3. Spring Boot cấu hình UUID representation

Nếu ứng dụng Spring Boot có tích hợp cấu hình MongoDB client và hỗ trợ `MongoClientSettingsBuilderCustomizer`, có thể cấu hình rõ:

```java
import org.bson.UuidRepresentation;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MongoUuidConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer standardUuidRepresentation() {
        return builder ->
            builder.uuidRepresentation(UuidRepresentation.STANDARD);
    }
}
```

Ví dụ trên minh họa phong cách cấu hình Spring Boot 3.x. Tên package và cơ chế auto-configuration cần kiểm tra theo phiên bản Boot đang dùng; nếu ứng dụng tự tạo `MongoClient` hoặc custom `MongoConverter`, hãy xác nhận customizer có thực sự áp dụng cho client được `MongoTemplate` sử dụng.

Với ứng dụng **reactive**, cần xác minh cả reactive MongoDB client và `ReactiveMongoTemplate` đang dùng cấu hình/codec đúng. Việc reactive hay blocking không thay đổi byte representation; vấn đề nằm ở cách mã hóa/giải mã giá trị BSON trên đường thực thi.

### 6.4. Có nên tự viết converter UUID?

Không nên vội thêm custom converter toàn cục `UUID → String` chỉ để làm cho lỗi codec biến mất. Điều đó thay đổi schema BSON sang String và có thể phá vỡ truy vấn/index hoặc dữ liệu do các dịch vụ khác ghi.

Khi cần tùy biến representation vì dữ liệu lịch sử, hãy xác định rõ:

- Kiểu BSON được giữ lại hoặc muốn chuyển tới.
- Converter hoặc codec nào thực sự được Spring Data sử dụng.
- Truy vấn equality, insert, read và update có cùng quy tắc không.
- Kế hoạch migration và tính tương thích với ứng dụng khác.

Nếu tất cả hệ thống thống nhất lưu UUID dưới dạng String có chuẩn, đó cũng là một lựa chọn schema hợp lệ. Quan trọng là **quy ước lưu trữ được chọn có chủ đích**, nhất quán và được kiểm thử.

## 7. Mongosh và Extended JSON: quan sát dữ liệu đã lưu

### 7.1. Tạo và truy vấn UUID chuẩn

Trong mongosh, ví dụ:

```javascript
const uuidText = "00112233-4455-6677-8899-aabbccddeeff";

db.uuid_events.insertOne({
  source: "example",
  eventId: UUID(uuidText)
});

// Khớp với eventId subtype 4 và đúng byte.
db.uuid_events.findOne({ eventId: UUID(uuidText) });

// Không khớp với field đang chứa UUID Binary.
db.uuid_events.findOne({ eventId: uuidText });
```

MongoDB không tự đổi BSON String sang UUID Binary khi so khớp. Cũng không có quy tắc mặc định «thấy chuỗi dài 36 ký tự thì diễn giải thành UUID».

### 7.2. Mở rộng BSON Binary sang Extended JSON

Một giá trị Binary có thể được biểu diễn bằng Extended JSON canonical dạng:

```json
{
  "eventId": {
    "$binary": {
      "base64": "ABEiM0RVZneImaq7zN3u/w==",
      "subType": "04"
    }
  }
}
```

Base64 trên tương ứng với 16 byte tiêu chuẩn của UUID mẫu. Với legacy binary, subtype có thể là `"03"` và Base64 cần phản ánh **byte thực tế** theo representation cũ. Một số công cụ có thể hiển thị UUID dưới dạng thuận tiện hơn thay vì cấu trúc `$binary`, nên hãy dùng công cụ hiển thị đầy đủ kiểu khi cần điều tra.

Trong mongosh:

```javascript
const sample = db.uuid_events.findOne({ source: "example" });
printjson(sample);
print(EJSON.stringify(sample));
```

Nếu cách hiển thị rút gọn không cho thấy subtype, hãy xuất dữ liệu BSON theo định dạng Extended JSON thích hợp hoặc kiểm tra bằng API `BsonBinary.getType()`/`getData()` của driver. Đừng quyết định migration chỉ dựa vào `UUID.toString()`.

### 7.3. $type không nhận diện đầy đủ representation

```javascript
db.uuid_events.aggregate([
  { $project: { eventIdType: { $type: "$eventId" } } },
  { $limit: 20 }
]);
```

`$type` xác định field là `binData`, nhưng **không phân biệt đủ** STANDARD với các kiểu legacy, vì chúng đều thuộc BSON Binary. Cần quan sát thêm subtype và 16 byte; với subtype 3 còn cần biết driver cũ dùng representation nào.

## 8. Tương thích giữa Java, Python, C# và phiên bản driver

### 8.1. Contract liên dịch vụ

Trong hệ thống có nhiều ngôn ngữ hoặc ứng dụng cũ, tài liệu giao tiếp cần nêu rõ:

| Nội dung contract | Ví dụ lựa chọn |
| --- | --- |
| Tên field MongoDB | `correlation_id` |
| Kiểu logic | UUID 128 bit |
| Kiểu BSON | Binary subtype `0x04` |
| Representation | STANDARD, thứ tự byte chuẩn |
| Dạng API/JSON | Chuỗi UUID canonical, lowercase và có dấu gạch |
| Quy tắc query | Chuyển String API thành UUID, sau đó encode standard |
| Quy tắc dữ liệu cũ | Migration hoặc lớp đọc tương thích có kiểm soát |

Driver Java, PyMongo và .NET/C# đều có lựa chọn biểu diễn UUID, nhưng API cấu hình và mặc định có thể thay đổi theo phiên bản. Khi tích hợp, hãy cấu hình **cả bên ghi và bên đọc** theo cùng contract. Không đủ nếu Java đã đổi sang STANDARD nhưng một batch Python vẫn ghi PYTHON_LEGACY.

### 8.2. Vì sao truy vấn không khớp dù cùng UUID?

Xét ba dữ liệu vật lý:

```text
Java service A:   subtype 03 + Java legacy bytes
Python service B: subtype 03 + Python legacy bytes
Service mới C:    subtype 04 + standard bytes
```

Các ứng dụng có thể cùng hiển thị chuỗi UUID ban đầu, nhưng equality query trên MongoDB chỉ thấy giá trị BSON. Một index trên `correlation_id` không sửa được bất đồng representation; nó chỉ lập index cho các giá trị BSON đã được lưu.

Nếu unique index tồn tại trên field này, **cùng một UUID logic vẫn có thể xuất hiện dưới nhiều biểu diễn vật lý khác nhau**. Unique constraint trên giá trị BSON không phải cơ chế chuẩn hóa UUID xuyên subtype/byte order.

### 8.3. Nâng cấp driver có thể làm lộ lỗi cũ

Khi nâng cấp Java driver/Spring Data MongoDB:

1. Kiểm kê cấu hình representation cũ và nơi tạo `MongoClient`.
2. Lấy mẫu document thật, quan sát subtype/bytes và xác định writer ban đầu.
3. Xây dựng test đọc/ghi trên chính dữ liệu cũ, không chỉ dữ liệu sinh bằng driver mới.
4. Chọn chiến lược giữ legacy tạm thời hay migration sang STANDARD.
5. Kiểm tra các đường insert, `save`, query criteria, aggregation, event consumer và batch.

Khi một lỗi codec xuất hiện sau nâng cấp, không nên sửa bằng việc ép tất cả UUID thành String ở cấp API hoặc viết lại dữ liệu hàng loạt ngay. Trước hết phải biết **kiểu BSON nào đã được lưu** và liệu đường ghi mới có đang dùng quy tắc khác hay không.

## 9. Chiến lược migration từ UUID legacy sang STANDARD

### 9.1. Kiểm kê trước khi viết dữ liệu

Giả sử collection `orders` chứa field `trackingUuid` là legacy, còn ứng dụng mới muốn lưu standard. Trước khi migration, xác nhận:

- Field nằm ở collection nào, có trong `_id` không, có được dùng trong reference không.
- Subtype `0x03`/`0x04`/String phân bố thế nào; document nào đến từ mỗi hệ thống.
- Với subtype 3, các record được ghi bằng JAVA_LEGACY, C_SHARP_LEGACY hay PYTHON_LEGACY.
- Có bản ghi đồng nhất subtype nhưng **trộn thứ tự byte** hay không.
- Index/unique constraint, transaction, consumer và cách rollback nào bị ảnh hưởng.

Chỉ nhìn subtype 3 rồi chọn một bộ decode chung có thể làm thay đổi UUID logic của những bản ghi do driver khác ghi.

### 9.2. Nguyên tắc chuyển đổi giữ nguyên giá trị logic

Quá trình chuyển đúng là:

```text
BSON Binary subtype 3 + bytes cũ
       |
       | Giải mã bằng đúng legacy representation ban đầu
       v
UUID logic trong ứng dụng
       |
       | Mã hóa bằng STANDARD
       v
BSON Binary subtype 4 + bytes chuẩn
```

Ví dụ Java minh họa chuyển đổi **một giá trị đã biết** là Java legacy:

```java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

static BsonBinary convertJavaLegacyToStandard(BsonBinary oldValue) {
    if ((oldValue.getType() & 0xff) != 0x03) {
        throw new IllegalArgumentException("Expected UUID legacy subtype 3");
    }
    UUID logicalId = oldValue.asUuid(UuidRepresentation.JAVA_LEGACY);
    return new BsonBinary(logicalId, UuidRepresentation.STANDARD);
}
```

Ví dụ chỉ đúng nếu nguồn dữ liệu đã được xác nhận là JAVA_LEGACY. Không tự động dùng mã này cho tất cả document subtype 3. Trong migration thực tế còn phải xử lý trường thiếu, `null`, dữ liệu không đủ 16 byte, giới hạn batch, kiểm tra kết quả và cơ chế rollback.

### 9.3. _id cần kế hoạch đặc biệt

MongoDB không cho cập nhật `_id` của document hiện có như một field thường. Nếu UUID nằm trong `_id` và cần đổi subtype/byte, bạn không thể chỉ gọi:

```javascript
// Không phải cách migration hợp lệ: _id là khóa bất biến.
db.orders.updateOne(
  { /* điều kiện */ },
  { $set: { _id: UUID("00112233-4455-6677-8899-aabbccddeeff") } }
);
```

Phải thiết kế chiến lược sao chép/tạo document dưới khóa mới, cập nhật reference, xử lý unique index và cutover ứng dụng. Tùy độ quan trọng của hệ thống, việc chuyển có thể cần cửa sổ bảo trì, cơ chế đồng bộ tạm thời hoặc tiến trình kiểm tra đối soát. Luôn thử trên bản sao dữ liệu trước khi triển khai thật.

### 9.4. Gợi ý quy trình triển khai có kiểm soát

| Giai đoạn | Việc cần chứng minh |
| --- | --- |
| 1. Khảo sát | Đã biết subtype/bytes và nguồn writer của từng nhóm dữ liệu |
| 2. Định chuẩn | Contract mới dùng subtype 4 STANDARD; các client được cấu hình phù hợp |
| 3. Thử nghiệm | Đọc legacy đúng UUID, encode standard và query được bằng client mới |
| 4. Chuyển dữ liệu | Idempotent, xử lý xung đột, có checkpoint và đối soát số record |
| 5. Cutover | Không còn writer legacy phát sinh dữ liệu cũ sau thời điểm chuyển |
| 6. Theo dõi | Query trả đủ kết quả, index/unique constraint hoạt động như dự kiến |
| 7. Kết thúc | Loại bỏ nhánh đọc legacy khi dữ liệu và consumer đã hoàn toàn đồng bộ |

Một migration thành công phải chứng minh cả **đúng dữ liệu logic** và **tương thích truy vấn**, không chỉ việc tất cả bản ghi mới có subtype 4.

## 10. Index và thiết kế truy vấn với UUID Binary

Giả sử `attachments` được tìm theo tenant và correlation ID:

```javascript
db.attachments.createIndex(
  { tenantId: 1, correlation_id: 1 },
  { name: "ix_attachments_tenant_correlation" }
);

db.attachments.find({
  tenantId: "tenant-a",
  correlation_id: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
```

Compound index này có thể hỗ trợ truy vấn equality theo hai field. Nhưng hiệu quả chỉ có ý nghĩa khi giá trị truy vấn dùng đúng BSON subtype và byte order. Index không tự giải mã UUID legacy để đối chiếu với UUID standard.

Nếu `correlation_id` phải unique theo tenant, có thể cân nhắc unique compound index; trước khi tạo, cần quyết định quy tắc của cả dữ liệu lịch sử. Không nên dựa vào unique index đơn thuần để khẳng định một UUID logic không bị trùng dưới những representation khác nhau.

Việc dùng UUID ngẫu nhiên làm `_id` hoặc khóa index cũng có tác động đến mẫu ghi và locality. Đánh giá hiệu năng trên workload thực tế, đặc biệt nếu hệ thống ghi nhiều và dùng UUID tạo ngẫu nhiên; đừng quy một vấn đề phân mảnh hay hiệu năng thành lỗi «UUID Binary sai».

Để kiểm tra index:

```javascript
db.attachments.find({
  tenantId: "tenant-a",
  correlation_id: UUID("00112233-4455-6677-8899-aabbccddeeff")
}).explain("executionStats");
```

Quan sát `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined` và `nReturned`. Khi query sai representation, `nReturned = 0` không chứng minh index kém; cần xác minh **BSON value của filter** trước.

## 11. Thiết kế kiểm thử tương thích

### 11.1. Unit test cho byte representation

Kiểm thử thuần Java, không cần kết nối MongoDB:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.HexFormat;
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;
import org.junit.jupiter.api.Test;

class UuidRepresentationTest {

    @Test
    void standardUuidHasExpectedSubtypeAndBytes() {
        UUID uuid = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff"
        );
        BsonBinary binary = new BsonBinary(uuid, UuidRepresentation.STANDARD);

        assertEquals(4, binary.getType() & 0xff);
        assertArrayEquals(
            HexFormat.of().parseHex("00112233445566778899aabbccddeeff"),
            binary.getData()
        );
        assertEquals(uuid, binary.asUuid(UuidRepresentation.STANDARD));
    }
}
```

Với legacy, thêm test có expected byte cụ thể tương ứng từng representation. Test chỉ assert `UUID.fromString(...).equals(result)` chưa đủ để chứng minh byte BSON trên hai driver giống nhau.

### 11.2. Integration test trên MongoDB thật

Khi có môi trường test phù hợp (MongoDB local/test container), kiểm tra ít nhất các tình huống:

1. Java ghi UUID STANDARD, mongosh đọc thấy Binary subtype 4 với 16 byte chuẩn.
2. Mongosh ghi `UUID("...")`, Spring Data đọc về đúng `UUID`.
3. `MongoTemplate` và repository query được bằng UUID; query bằng chuỗi thuần **không** được ngầm coi là tương đương.
4. `byte[]` chứa digest hoặc payload được round trip đúng byte, không bị chuyển nhầm thành UUID.
5. Dữ liệu legacy mẫu do driver cũ ghi được giải mã đúng; phép ghi mới dùng quy ước đã lựa chọn.
6. Sau restart ứng dụng, cấu hình client/codec vẫn đúng; nâng phiên bản driver không đổi kết quả đọc test fixture.

Với tích hợp nhiều ngôn ngữ, nên tạo **fixture chung** gồm UUID canonical, subtype, 16 byte hex và expected BSON query. Mỗi client đọc/ghi cùng fixture để tìm khác biệt. Dự án không cần chạy toàn bộ bài test trong bước viết tài liệu này; đây là tiêu chí kiểm chứng khi triển khai.

### 11.3. Bảng tình huống cần dự đoán

| Dữ liệu đã lưu | Filter gửi tới MongoDB | Có khớp? |
| --- | --- | --- |
| UUID standard subtype 4 | UUID standard subtype 4 cùng 16 byte | Có |
| UUID standard subtype 4 | BSON String chứa UUID canonical | Không |
| UUID standard subtype 4 | UUID Python legacy subtype 3, cùng byte | Không |
| UUID Java legacy subtype 3 | UUID C# legacy subtype 3, cùng UUID logic | Thường không do byte order khác |
| UUID Java legacy subtype 3 | Java legacy cùng 16 byte và subtype | Có |

Trong bảng, «khớp» được hiểu là equality theo BSON, giả định cùng collection, field path và các điều kiện lọc khác đều đúng.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Giả thuyết | Cách xác minh |
| --- | --- | --- |
| Java báo lỗi codec khi lưu UUID | Client/codec không có representation phù hợp | Xem `MongoClientSettings`, Spring Boot customizer, custom converter |
| Java đọc UUID cũ không ra giá trị dự kiến | Sai legacy representation | Xem subtype + byte, thử giải mã bằng đúng nguồn writer |
| Mongosh truy vấn bằng chuỗi UUID không thấy record | Field lưu Binary, filter là BSON String | Dùng `UUID("...")` khi dữ liệu là subtype 4 |
| Hai dịch vụ cùng UUID string nhưng query khác kết quả | Một dịch vụ dùng legacy, dịch vụ còn lại standard | So sánh subtype và byte thực tế |
| Unique index cho phép hai record cùng UUID logic | BSON representation khác nhau | Chuẩn hóa trước khi dựa vào ràng buộc unique |
| `$type` đều trả `binData` nhưng dữ liệu không khớp | `$type` không cho biết subtype/order | Dùng Extended JSON/BsonBinary kiểm tra sâu |
| `byte[]` bị thay bằng chuỗi Base64 | Conversion/DTO làm thay đổi schema | So BSON type và test round trip byte |
| Migration xong mà reference vẫn không truy vấn được | Khóa và reference có subtype/kiểu khác nhau | Đối soát tất cả collection tham chiếu |
| Query chậm khi dùng UUID | Thiếu index hoặc query không phù hợp | Kiểm tra query correctness rồi dùng `explain` |

Một phương pháp chẩn đoán hiệu quả là ghi ra chuỗi kiểm tra sau:

```text
UUID logic mong muốn
    ↓
Kiểu Java / codec / UuidRepresentation đang hoạt động
    ↓
BSON type + subtype + bytes được ghi
    ↓
BSON type + subtype + bytes của filter
    ↓
Equality query / kết quả / explain
```

Kiểm tra lần lượt giúp phân biệt lỗi **mapping**, lỗi **tương thích driver**, lỗi **dữ liệu lịch sử** và lỗi **index/performance**.

## 13. Bài thực hành có lời giải

### Bài 1 — Phân biệt subtype và kiểu

**Đề bài.** Một document lưu `eventId` bằng UUID subtype 4. Vì sao query sau không tìm thấy?

```javascript
db.uuid_events.find({
  eventId: "00112233-4455-6677-8899-aabbccddeeff"
});
```

**Lời giải.** Filter gửi BSON String, còn field lưu BSON Binary subtype 4. Để truy vấn đúng giá trị tiêu chuẩn:

```javascript
db.uuid_events.find({
  eventId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
```

### Bài 2 — Vì sao Python legacy và standard không bằng nhau?

**Đề bài.** Hai driver có cùng 16 byte RFC của UUID, nhưng một driver dùng `PYTHON_LEGACY` còn driver kia dùng `STANDARD`. Equality query có bảo đảm khớp không?

**Lời giải.** Không. Python legacy dùng subtype 3, standard dùng subtype 4. Cùng byte payload chưa đủ; subtype BSON cũng khác. Muốn tương thích, chuyển dữ liệu về representation chung hoặc truy vấn bằng representation thực tế đã lưu trong giai đoạn chuyển tiếp.

### Bài 3 — Kiểm tra Java legacy bằng bytes

**Đề bài.** Với UUID `00112233-4455-6677-8899-aabbccddeeff`, hãy viết test chứng minh BSON Java legacy khác standard.

**Lời giải:**

```java
UUID id = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");
BsonBinary std = new BsonBinary(id, UuidRepresentation.STANDARD);
BsonBinary old = new BsonBinary(id, UuidRepresentation.JAVA_LEGACY);

System.out.println(std.getType() & 0xff); // 4
System.out.println(old.getType() & 0xff); // 3

System.out.println(HexFormat.of().formatHex(std.getData()));
// 00112233445566778899aabbccddeeff

System.out.println(HexFormat.of().formatHex(old.getData()));
// 7766554433221100ffeeddccbbaa9988
```

Các biến và kiểu như `UUID`, `BsonBinary`, `UuidRepresentation` và `HexFormat` được import tương tự các ví dụ trước.

### Bài 4 — Chọn kiểu lưu hai trường khác nhau

**Đề bài.** Một event có `eventId` UUID và `payloadDigest` SHA-256. Có nên lưu cả hai thành BSON Binary subtype 4?

**Lời giải.** Không. `eventId` dùng subtype 4 nếu contract quy định UUID STANDARD; `payloadDigest` là byte array 32 byte, nên lưu bằng Generic Binary subtype 0 hoặc biểu diễn digest đã thống nhất. Subtype 4 không phải nhãn chung cho mọi dữ liệu nhị phân.

### Bài 5 — Lập kế hoạch đổi representation

**Đề bài.** Service cũ Java ghi `trackingUuid` bằng JAVA_LEGACY, service mới dùng STANDARD. Có được chỉ sửa cấu hình MongoClient và triển khai không?

**Lời giải.** Không thể kết luận an toàn. Cần kiểm kê BSON cũ, xác nhận subtype 3 và Java legacy byte order; dựng test giải mã đúng; thiết kế migration từ UUID logic sang subtype 4; thống nhất writer/reader; kiểm tra index, unique và tham chiếu. Với field `_id`, việc chuyển khó hơn vì khóa không được sửa tại chỗ.

## 14. Checklist bàn giao và ghi nhớ

Trước khi thống nhất một schema UUID giữa các dịch vụ, xác nhận:

| Mục kiểm tra | Tiêu chí hoàn thành |
| --- | --- |
| Representation mới | Đã chọn `STANDARD` hoặc có lý do lưu String rõ ràng |
| Kiểu lưu trong BSON | Biết String/Binary, subtype, thứ tự 16 byte |
| MongoDB Java driver | Cấu hình client/codec đã kiểm tra |
| Spring Data MongoDB | Đã test `MongoTemplate`, repository và mapping thực tế |
| Dịch vụ khác ngôn ngữ | Cùng fixture UUID cho đọc, ghi và query |
| Dữ liệu legacy | Đã xác định nguồn writer và từng representation |
| Field nhị phân khác | Không nhầm digest, chữ ký, file với UUID |
| Chuyển đổi dữ liệu | Migration/rollback và reference đã được đánh giá |
| Query/index | BSON filter khớp dữ liệu; đã đo bằng `explain` khi cần |
| Kiểm thử | Có round trip, subtype/byte assertions và integration test |

**Các quy tắc cần nhớ:**

1. UUID logic không đồng nghĩa với cách lưu: BSON String, Binary subtype 3 và Binary subtype 4 là những biểu diễn khác nhau.
2. `STANDARD` dùng subtype `0x04` và byte chuẩn; các legacy dùng subtype `0x03` nhưng có thể khác nhau về thứ tự byte.
3. Muốn đọc legacy đúng phải biết representation ban đầu; subtype 3 tự nó chưa cho biết JAVA_LEGACY, C_SHARP_LEGACY hay PYTHON_LEGACY.
4. Cấu hình UUID ở driver/Spring Data không tự sửa dữ liệu cũ. Query phải tạo đúng BSON value giống field đã lưu.
5. Dữ liệu `byte[]` thông thường có mục đích riêng, không tự được coi là UUID chỉ vì có 16 byte.
6. Với dữ liệu mới liên dịch vụ, ưu tiên contract STANDARD, kiểm tra byte/subtype bằng test và đánh giá migration trước khi thay đổi hệ thống đã vận hành.
