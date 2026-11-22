# Serialization/deserialization an toàn và giới hạn dữ liệu đầu vào

## 1. Vì sao chuyển đổi dữ liệu là một ranh giới bảo mật?

Ứng dụng Java thường trao đổi dữ liệu qua JSON, BSON, Redis value, MessagePack, Protobuf, Avro hoặc binary payload rồi lưu vào cơ sở dữ liệu NoSQL. Hai thao tác tưởng đơn giản là **serialization** (biến object thành chuỗi/byte) và **deserialization** (đọc chuỗi/byte thành object) thực chất nằm ngay ở ranh giới giữa **dữ liệu không đáng tin** và **logic có quyền truy cập dữ liệu**.

Xét API cập nhật hồ sơ:

```text
                 UNTRUSTED                           TRUSTED
Browser / Mobile / Partner                         Server + NoSQL
           |                                             |
           |  JSON HTTP body                             |
           v                                             |
      API gateway                                        |
           |                                             |
           v                                             |
      JSON parser ---------------------------------------+
           |
           v
      Java DTO / validation
           |
           v
      Authorization + business rules
           |
           v
      Driver-safe query / update
           |
           v
      MongoDB / DynamoDB / Cassandra / ...
```

Một payload độc hại có thể gây hại trước khi chạm tới database:

- Quá lớn hoặc lồng quá sâu khiến parser, CPU hoặc heap cạn kiệt.
- Chứa kiểu/metadata khiến bộ deserializer dựng object không mong muốn.
- Dùng một field có vẻ bình thường để vượt qua validation do ép kiểu không rõ ràng.
- Chèn trường `role=ADMIN` vào object được bind trực tiếp vào entity.
- Đưa toán tử MongoDB như `$ne`, `$where` vào query nếu backend ghép raw JSON từ client.
- Thay đường dẫn cập nhật để ghi field của tenant khác.
- Tạo query regex/filter/scan có chi phí lớn.
- Đưa dữ liệu hợp lệ về cú pháp nhưng sai về business, schema, quyền hoặc độ dài.

**Nguyên tắc xuyên suốt:** dữ liệu nhận qua mạng, message broker, cache hoặc file nhập phải tiếp tục được coi là không đáng tin cho đến khi được kiểm tra **cú pháp, kích thước, kiểu, cấu trúc, ngữ nghĩa và quyền sử dụng**. Việc JSON parse thành công chưa nói gì về độ an toàn của thao tác NoSQL phía sau.

### 1.1. Mục tiêu của bài học

Sau bài này, người học có thể:

1. Phân biệt serialization, deserialization, validation, canonicalization và authorization.
2. Nhận diện nguy cơ unsafe polymorphic deserialization, Java native serialization, mass assignment và NoSQL injection.
3. Thiết lập giới hạn bytes, độ sâu, chuỗi, số chữ số, mảng, page size và độ phức tạp truy vấn.
4. Sử dụng typed DTO, Jackson, Bean Validation và API driver theo hướng an toàn.
5. Bảo vệ số tiền, số nguyên lớn, ngày giờ, ObjectId, Unicode, null/missing và schema evolution.
6. Giới hạn tài nguyên khi parse JSON/BSON, nén, Base64 và xử lý event.
7. Thiết kế negative tests, fuzzing, telemetry, response errors và runbook khi có input abuse.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Serialization | Object được mã hóa thành wire/storage format thế nào? | Java `Product` → JSON/BSON |
| Deserialization | Bytes được chuyển thành cấu trúc trong chương trình thế nào? | JSON body → `CreateProductRequest` |
| Syntax validation | Có đúng định dạng hay không? | JSON đóng ngoặc đúng |
| Structural validation | Có đúng field/kiểu/độ dài/số phần tử? | `tags` là mảng tối đa 20 phần tử |
| Semantic validation | Giá trị có hợp lệ với nghiệp vụ? | Giá không âm, ngày kết thúc sau ngày bắt đầu |
| Canonicalization | Có các biểu diễn tương đương cần chuẩn hóa? | Unicode NFC cho identifier theo policy |
| Authorization | Chủ thể có được phép thao tác trên tài nguyên/field đó? | User chỉ sửa profile của chính mình |
| Query parameterization | Dữ liệu có được giữ là data thay vì syntax? | CQL bound values, Mongo `Filters.eq` |
| Resource budgeting | Một request tiêu tốn tối đa bao nhiêu tài nguyên? | Body 64 KiB, page limit 100, query deadline |

**Không tầng nào thay thế tất cả tầng còn lại.** Một `@Size(max=50)` không ngăn deserialization gadget; một parser strict không xác minh user có quyền sửa `role`; một query có bound parameters vẫn có thể scan toàn database nếu cho phép filter không giới hạn.

## 3. Trust boundaries trong kiến trúc Java–NoSQL

Không chỉ HTTP client mới không đáng tin. Những nguồn sau cũng cần kiểm tra theo contract:

- Public REST/GraphQL/WebSocket requests.
- Webhooks từ đối tác, kể cả khi xác minh chữ ký thành công.
- Kafka/RabbitMQ/Redis Streams/CDC events.
- Documents đọc từ collection do nhiều services ghi.
- Redis cache được chia sẻ giữa các tenants hoặc services.
- File import CSV/JSON/NDJSON/ZIP.
- Search query DSL nhận qua API.
- Metadata `Content-Type`, headers, cookies và query parameters.
- Dữ liệu do người dùng đưa vào đã được lưu trước đây rồi được đọc lại (*stored input*).

### 3.1. “Đã ở trong database” chưa có nghĩa đáng tin

Một document có thể được ghi từ phiên bản ứng dụng cũ, migration, công cụ admin hoặc compromised writer. Khi deserializing từ NoSQL vào Java, cần có schema/version handling và kiểm tra các fields ảnh hưởng logic nhạy cảm.

### 3.2. “Có authentication” không đủ

Một người dùng đăng nhập hợp lệ vẫn có thể gửi:

```json
{
  "displayName": "Lan",
  "role": "ADMIN",
  "tenantId": "another-tenant"
}
```

Authentication chỉ trả lời **ai** gửi; không cấp quyền ghi mọi field của server entity.

### 3.3. Chữ ký và checksum không chứng minh nội dung an toàn

Chữ ký có thể giúp xác minh nguồn/integrity của webhook. Nó không giới hạn kích thước, độ sâu, chi phí parse, hoặc tính hợp lệ của business command. Payload từ đối tác hợp lệ vẫn có thể chứa data lỗi.

## 4. Mô hình phòng thủ nhiều lớp

```text
L0  Network / Gateway
    Content-Length, upload cap, rate limit, auth
                     |
L1  Protocol decoding
    Content-Type, UTF-8, decompression budget
                     |
L2  Parser
    JSON syntax, duplicate keys, nesting/string/number caps
                     |
L3  Typed DTO
    Field allowlist, strict types, bounded arrays
                     |
L4  Bean/domain validation
    Ranges, cross-field invariants, normalization
                     |
L5  Authorization
    Tenant ownership, field-level permission
                     |
L6  Query construction
    Bound parameters, safe driver builders
                     |
L7  Database resource controls
    Query timeout, index, pagination, quota
                     |
L8  Monitoring
    4xx patterns, parser failures, CPU/heap/DB load
```

### 4.1. Tại sao chặn từ sớm?

Nếu API chấp nhận body 100 MiB rồi deserializer mới phát hiện field quá dài, memory/network đã bị tiêu tốn. Giới hạn ở gateway/server giúp từ chối sớm; parser limits chặn những body nhỏ nhưng có cấu trúc cực đoan.

### 4.2. Không biến “nhiều lớp” thành “nhiều luật mâu thuẫn”

Giới hạn body, DTO, database schema và client SDK nên được tài liệu hóa đồng bộ. Ví dụ API cho `name` 1.000 ký tự nhưng DB index giới hạn nhỏ hơn sẽ dẫn tới lỗi muộn hoặc ghi không nhất quán.

### 4.3. Từ chối không phải luôn là lỗi 500

Request vượt size có thể trả HTTP 413; cấu trúc/field không hợp lệ thường là 400 hoặc 422 theo contract; quyền sai là 403 hoặc 404 tùy chính sách tránh lộ tài nguyên. Không tiết lộ stack trace/deserializer class name trong response.

## 5. Phân biệt JSON, BSON, POJO, binary format

| Format / biểu diễn | Mạnh ở đâu | Rủi ro cần kiểm tra |
|---|---|---|
| JSON | Tương tác HTTP, dễ đọc, đa ngôn ngữ | Duplicate keys, number precision, depth, kiểu lỏng |
| BSON | MongoDB documents, kiểu dữ liệu phong phú | ObjectId/Decimal128/date/binary, operator injection khi ghép raw |
| POJO/record | Typed domain model trong Java | Mass assignment, coercion, polymorphic binding |
| Jackson tree (`JsonNode`) | Payload linh hoạt | Tự phải enforce schema và giới hạn |
| Java native serialization | Legacy object graph | Deserialization gadgets, object filters, compatibility |
| Protobuf | Strongly typed message schema | Unknown fields, nested/repeated unbounded payloads |
| Avro | Schema evolution trong event streams | Reader/writer schema mismatch, resource limits |
| Redis string/hash | Cache và ephemeral state | Schema mismatch, stale data, untrusted cached payload |
| ZIP/GZIP/Base64 | Transport/storage encoding | Decompression bombs, expansion, CPU/memory pressure |

**Đổi JSON sang BSON hay Protobuf không tự làm một API an toàn.** Các format có trade-off, nhưng validation, authorization và resource budget vẫn cần thiết.

## 6. Deserialization nguy hiểm là gì?

Một hệ unsafe khi bytes do attacker kiểm soát có thể quyết định:

- Object classes được khởi tạo.
- Constructor/setter hoặc lifecycle hooks được gọi.
- Object graph quá lớn/đệ quy.
- Side effects xảy ra khi dựng object.
- Field quyền hạn hoặc internal state được gán ngoài ý muốn.
- Đường dẫn file, classpath, URL hoặc command được dùng trong quá trình deserialize.

### 6.1. Java native serialization

Legacy Java có:

```java
ObjectInputStream in =
        new ObjectInputStream(untrustedInputStream);

Object value = in.readObject();
```

Đây là **anti-pattern** nếu dữ liệu không đáng tin. `readObject()` có thể chạy các cơ chế khôi phục object và gadget chains trong classpath trước khi business code có cơ hội validate `value`.

**Không dùng Java native deserialization cho dữ liệu nhận từ khách hàng, broker công cộng hoặc cache chia sẻ nếu có thể tránh.** Hãy dùng schema format/typed DTO và parser có giới hạn phù hợp.

### 6.2. “Chỉ deserialize class mình biết” chưa đủ nếu filter yếu

Một `instanceof MyType` kiểm tra sau `readObject()` là quá muộn. Bộ lọc classes/depth/refs/bytes phải áp dụng **trong quá trình** đọc; ngay cả vậy, native serialization vẫn là lựa chọn rủi ro hơn structured data formats cho untrusted inputs.

### 6.3. Không nhầm với JSON→POJO bình thường

Jackson tạo một record DTO cụ thể từ JSON có schema hẹp khác với việc cho client quyết định bất kỳ Java class nào sẽ được tạo. Mức nguy hiểm phụ thuộc configuration, classpath và kiểu dữ liệu được cho phép.

## 7. Jackson polymorphic typing và gadget risk

Một số thư viện JSON hỗ trợ polymorphism bằng type metadata:

```json
{
  "@class": "some.package.UnexpectedType",
  "value": "..."
}
```

Nếu ứng dụng cho phép caller chọn class tùy ý bằng default typing hoặc `@JsonTypeInfo` thiếu giới hạn, deserializer có thể khởi tạo kiểu không mong muốn. Mức độ nghiêm trọng phụ thuộc thư viện/version/classes trên classpath.

### 7.1. Quy tắc ưu tiên

- Bind input vào DTO/record cụ thể.
- Không bật global default typing vô điều kiện cho untrusted JSON.
- Không nhận `Class`, `Object`, interface hierarchy không giới hạn nếu client kiểm soát type ID.
- Nếu polymorphism thực sự cần, dùng **allowlist rõ ràng** các subtypes/identifiers.
- Cập nhật Jackson và dependencies theo chính sách bảo mật.
- Giảm classpath gadget surface và test các payload không mong muốn.

### 7.2. Pattern allowlist với discriminator nghiệp vụ

Thay vì cho client gửi tên class Java:

```json
{
  "kind": "CARD",
  "lastFour": "4242"
}
```

Hệ chuyển `kind` qua enum/allowed subtypes:

```java
public enum PaymentMethodKind {
    CARD,
    BANK_TRANSFER
}
```

Tùy kiến trúc có thể dùng sealed interfaces và explicit subtypes, nhưng **không dùng tên class từ client làm factory key tự do**.

### 7.3. Mã dùng nội bộ cũng cần review

Ngay cả khi payload từ DB nội bộ, một field `@type` trong documents legacy có thể bị ghi bởi script/import hoặc actor khác. Đánh giá toàn đường dữ liệu.

## 8. Khi buộc phải đọc Java native serialization

Một số hệ legacy có thể tạm thời cần deserialize object streams. Chính sách an toàn tốt nhất vẫn là **loại bỏ dần định dạng này**. Trong giai đoạn chuyển đổi:

- Chỉ nhận dữ liệu từ nguồn được xác thực/kiểm soát.
- Áp dụng `ObjectInputFilter` với allowlist, giới hạn depth/references/bytes.
- Chặn classes ngoài contract trước khi object được dựng.
- Chạy trong môi trường với quyền hạn tối thiểu.
- Không coi filter là thay thế cho việc giảm rủi ro classpath/gadget.
- Có kế hoạch migrate records sang schema format.

Ví dụ khái niệm Java:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputStream in = new ObjectInputStream(source);

ObjectInputFilter filter = ObjectInputFilter.Config
        .createFilter(
                "maxdepth=12;maxrefs=2000;maxbytes=65536;"
                + "com.example.legacy.SafeRecord;"
                + "java.base/java.lang.String;!*"
        );

in.setObjectInputFilter(filter);
```

**Đây là minh họa policy filter, không phải lời khuyên chấp nhận native deserialization từ Internet.** Những kiểu cần cho object graph thực tế và cú pháp filter phải được kiểm tra với JDK/version; ký tự `!*` từ chối những classes còn lại, nhưng có thể gây lỗi cho records cũ cần thêm allowed types. Chỉ mở allowlist dựa trên contract, không thay bằng wildcard toàn package mà không đánh giá.

## 9. Dùng DTO thay vì bind trực tiếp database entity

Một thiết kế dễ lỗi:

```java
@PostMapping("/users")
public UserDocument create(@RequestBody UserDocument doc) {
    return repository.save(doc);
}
```

Nếu `UserDocument` có `role`, `tenantId`, `isVerified`, `creditLimit` hoặc `createdAt`, caller có thể cố gán chúng ngay trong request.

### 9.1. DTO allowlist

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateUserRequest(
        @NotBlank
        @Size(max = 80)
        String displayName,

        @Size(max = 240)
        String bio
) {}
```

Application tạo entity:

```java
public UserDocument createUser(
        CreateUserRequest request,
        AuthenticatedPrincipal principal
) {
    UserDocument doc = new UserDocument();
    doc.setUserId(newId());
    doc.setTenantId(principal.tenantId());
    doc.setRole("MEMBER");
    doc.setVerified(false);
    doc.setDisplayName(request.displayName());
    doc.setBio(request.bio());
    return userRepository.save(doc);
}
```

### 9.2. Field không có trong DTO không được tự ý ghi

Ngay cả khi JSON gửi `"role":"ADMIN"`, schema binding sẽ từ chối nếu strict-unknown mode bật, hoặc ít nhất không map vào entity khi caller chỉ được bind DTO. Chính sách **từ chối unknown fields** thường giúp phát hiện input nhầm và tấn công sớm hơn silently ignoring.

### 9.3. Không lấy tenant từ body

`tenantId`/`ownerId`/permissions của tài nguyên phải dựa trên principal và authorization policy, không dựa đơn thuần vào field do client gửi.

### 9.4. DTO không thay authorization

Một user hợp lệ có thể được phép sửa displayName của chính mình nhưng không của người khác. Vẫn cần kiểm tra ownership ở service/database mutation.

## 10. Mass assignment / overposting trong NoSQL

**Mass assignment** xảy ra khi application gán hàng loạt fields từ untrusted object vào entity mà không giới hạn danh sách thuộc tính được phép thay đổi.

Payload:

```json
{
  "displayName": "Alice",
  "role": "ADMIN",
  "isVerified": true,
  "balanceMinor": 999999999
}
```

Nếu ứng dụng:

```java
repository.save(objectMapper.convertValue(
        requestBody, UserDocument.class));
```

thì có thể ghi những fields không được phép, tùy mapper/entity/schema.

### 10.1. Dùng field-level mapping tường minh

```java
Update update = new Update()
        .set("displayName", request.displayName())
        .set("bio", request.bio());
```

Không dùng raw map từ client thành `Update` không kiểm soát field names.

### 10.2. Patch requests có cần linh hoạt?

Có thể nhận danh sách field paths được allowlist:

```text
allowed:
  displayName
  bio
  preferences.language

forbidden:
  role
  tenantId
  isVerified
  paymentAccount
```

Mỗi path có validator/authorization riêng; không cho phép tùy ý paths như `a.b.c`, `$set`, hoặc array indexes vào nested internal fields.

### 10.3. Server-generated fields

`id`, `version`, `createdAt`, `updatedAt`, `tenantId`, `ownerId` thường do server/authority cấp. Khi client cần optimistic concurrency, chỉ nhận `expectedVersion` hoặc ETag theo contract thay vì cho sửa trực tiếp `version`.

## 11. Strict JSON parsing: đừng âm thầm chấp nhận cấu trúc mơ hồ

Một payload có duplicate keys:

```json
{
  "role": "MEMBER",
  "role": "ADMIN"
}
```

Một số parser lấy giá trị đầu, số khác lấy cuối hoặc báo lỗi. Nếu API gateway và ứng dụng diễn giải khác, authorization/filter policy có thể bị bypass.

### 11.1. Policy tốt

- Từ chối duplicate field names trong JSON nếu có thể.
- Không cho nhiều JSON values nối nhau mà chỉ đọc value đầu rồi bỏ phần đuôi.
- Từ chối trailing tokens.
- Chọn encoding UTF-8 và xử lý malformed sequences theo contract.
- Từ chối unexpected fields thay vì silently bỏ qua cho API commands nhạy cảm.
- Tránh coercion ngầm từ string thành number/boolean khi contract không cho phép.

### 11.2. Ví dụ trailing data

```text
{"amount":100}{"amount":999}
```

Một parser đọc object đầu rồi bỏ data còn lại có thể khiến các lớp bảo mật và logging nhìn khác nhau. Bật chế độ fail nếu có tokens thừa.

### 11.3. Valid JSON chưa phải valid command

```json
{
  "items": [],
  "limit": 999999999
}
```

Đúng cú pháp nhưng có thể không đúng nghiệp vụ/tài nguyên.

## 12. Jackson: cấu hình parser có giới hạn

Jackson phiên bản có hỗ trợ `StreamReadConstraints` (những phiên bản mới của dòng 2.x) cho phép giới hạn độ sâu và độ dài token trước khi tạo object graph quá lớn.

Ví dụ Spring/Java cấu hình khái niệm:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class SafeJsonMapperFactory {

    public static ObjectMapper create() {
        JsonFactory factory = JsonFactory.builder()
                .streamReadConstraints(
                        StreamReadConstraints.builder()
                                .maxNestingDepth(32)
                                .maxStringLength(16_384)
                                .maxNumberLength(128)
                                .build()
                )
                .build();

        factory.enable(
                JsonParser.Feature.STRICT_DUPLICATE_DETECTION
        );

        ObjectMapper mapper = new ObjectMapper(factory);
        mapper.enable(
                DeserializationFeature.FAIL_ON_TRAILING_TOKENS
        );
        mapper.enable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );

        // Không bật default typing cho dữ liệu không đáng tin.
        return mapper;
    }
}
```

### 12.1. Những giới hạn này thực sự bảo vệ gì?

- `maxNestingDepth(32)`: ngăn object/array lồng quá sâu theo semantics parser.
- `maxStringLength(16_384)`: giới hạn độ dài string token theo đơn vị implementation.
- `maxNumberLength(128)`: giới hạn numeric token.
- Strict duplicate detection: từ chối object field trùng tên.
- Fail on trailing tokens: chặn extra JSON values/tokens sau root.
- Fail on unknown properties: từ chối fields không có trong DTO binding.

### 12.2. Chúng chưa bảo vệ gì?

- Không thay HTTP body byte cap.
- Không tự giới hạn số phần tử của mọi array/map.
- Không bảo đảm aggregate memory/CPU của toàn JSON dưới một mức cụ thể.
- Không kiểm tra domain business hoặc quyền tenant.
- Không giới hạn database query cost khi map dữ liệu thành filter.
- Không thay schema version hoặc validation của từng DTO.

### 12.3. Cấu hình trong Spring Boot

Spring Boot có thể tự quản lý `ObjectMapper`/`JsonFactory`, message converters và nhiều mappers. Cần áp dụng constraints cho **đúng mapper dùng ở HTTP, Kafka và cache**, đồng thời không vô tình tạo mapper riêng không cùng policy. Code trên chỉ định nghĩa factory mẫu; không tự chứng minh HTTP converter của ứng dụng đã dùng nó.

### 12.4. Chính sách theo endpoint

Webhook events, user profile và file import có thể có kích thước hợp lệ khác nhau. Cho phép profile body 16 KiB, batch import vài MiB qua streaming path riêng; không tăng giới hạn toàn site đến 50 MiB chỉ vì một endpoint import.

## 13. HTTP byte limits phải nằm trước deserialization

Giới hạn JSON string length không chặn một body gồm hàng triệu fields ngắn. Body limit tại reverse proxy/gateway/HTTP server là lớp cần thiết.

Ví dụ chính sách:

| Endpoint | Body cap minh họa | Lý do |
|---|---:|---|
| `POST /users` | 16 KiB | DTO nhỏ |
| `PATCH /profiles` | 32 KiB | Một hồ sơ |
| `POST /orders` | 128 KiB | Giới hạn số dòng hàng |
| `POST /events/batch` | 512 KiB | Batch hữu hạn |
| `POST /imports` | 10 MiB upload | Stream/import path có quota riêng |

Những giá trị trên chỉ minh họa. Cần dựa vào payload hợp lệ lớn nhất, overhead encoding, consistency và SLO. Không dùng một con số cố định không xem workload.

### 13.1. `Content-Length` không phải đủ

Client có thể gửi chunked transfer hoặc không khai báo chiều dài như kỳ vọng. Server phải **đếm bytes thực nhận** và dừng khi vượt cap. Không tin header làm bằng chứng.

### 13.2. Bộ nhớ body buffer

Một stack có thể buffer toàn body vào heap trước khi controller được gọi. Cấu hình limit ở điểm nhận/buffering, không chỉ `@Size` sau khi body đã được bind.

### 13.3. Giới hạn concurrency

Ngay cả body 64 KiB, 50.000 requests đồng thời vẫn có thể tiêu thụ tài nguyên lớn. Cần concurrent request budget, timeout, rate limit và backpressure.

### 13.4. Error response

Body quá lớn thường có thể trả `413 Payload Too Large`. Không đợi parse thành công rồi tạo DB request vô ích.

## 14. Mảng, maps và số lượng trường

Độ sâu và độ dài string không giới hạn tổng số array entries:

```json
{
  "tags": ["a", "a", "a", "a", "a"]
}
```

Một mảng vài triệu phần tử vẫn chỉ lồng sâu 1 cấp. Một object với hàng trăm nghìn field names ngắn cũng có thể phá bộ nhớ.

### 14.1. Field-specific caps

```java
import jakarta.validation.constraints.Size;
import java.util.List;

public record ProductTagsRequest(
        @Size(max = 20)
        List<@Size(min = 1, max = 32) String> tags
) {}
```

### 14.2. Validate sau bind chưa phải đủ cho payload cực đoan

DTO validation xảy ra sau parser/collection allocation. Khi cần chặn trước, dùng streaming parser/limit total tokens/elements, HTTP byte cap và concurrency budget.

### 14.3. Nested arrays

Một DTO có `List<List<List<Object>>>` khó kiểm soát. Ưu tiên schema có depth hữu hạn và giới hạn ở từng cấp.

### 14.4. Deduplication

Nếu tags phải duy nhất, kiểm tra uniqueness; một danh sách 20 phần tử giống nhau vẫn có thể làm sai business logic hoặc tạo index entries trùng.

## 15. Số, số tiền và precision

JSON chỉ có cú pháp number, không chuẩn hóa cách mọi ngôn ngữ biểu diễn chính xác số nguyên lớn/decimal.

Ví dụ:

```json
{
  "quantity": 1,
  "priceMinor": 9007199254740993,
  "taxRate": 0.075
}
```

### 15.1. Không dùng floating point cho tiền nghiệp vụ

Java `double` có sai số biểu diễn. Dùng `long` đơn vị tiền nhỏ nhất nếu currency/scale hợp lệ, hoặc `BigDecimal` cùng rounding/scale policy.

### 15.2. Overflow

`priceMinor * quantity` trên `long` có thể overflow nếu không kiểm tra:

```java
long totalMinor = Math.multiplyExact(
        priceMinor,
        quantity
);
```

Cần giới hạn input trước và chuyển arithmetic overflow thành lỗi domain đúng; không để wrap thành số âm hoặc sai.

### 15.3. Giới hạn số chữ số

Một JSON number có hàng triệu chữ số có thể gây CPU/memory pressure khi parse/BigInteger. Dùng parser numeric token length limit và domain min/max.

### 15.4. Cố định scale/rounding

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("12.34");
BigDecimal fixed = price.setScale(
        2,
        RoundingMode.UNNECESSARY
);
```

`UNNECESSARY` ném exception nếu cần làm tròn; phù hợp khi API buộc nhập đúng precision. Nếu domain cho phép rounding, chọn mode và công bố contract.

### 15.5. Decimal128, long, JSON string

MongoDB BSON có `Decimal128`, int32/int64 và các kiểu khác; driver mapping vào `BigDecimal`/`Long` cần rõ. JavaScript clients có precision giới hạn với integers lớn; có thể truyền identifiers/số nguyên rất lớn dưới dạng string theo API schema.

### 15.6. NaN, Infinity, negative zero

JSON chuẩn không cho NaN/Infinity tokens. Không bật non-standard number parsing tùy tiện và không cho những giá trị đó đi vào calculation/index nếu domain không định nghĩa.

## 16. Null, missing, empty và kiểu dữ liệu

Bốn input sau có thể khác nghĩa:

```json
{}
```

```json
{"bio": null}
```

```json
{"bio": ""}
```

```json
{"bio": " "}
```

### 16.1. PUT và PATCH

- `PUT` có thể biểu thị replacement theo API contract.
- `PATCH` cần phân biệt field không gửi (giữ nguyên) và field gửi `null` (xóa/clear) nếu cho phép.
- JSON Merge Patch có semantics riêng với `null`; JSON Patch dùng operations/path riêng.
- Không dùng cùng DTO nullability rồi tự suy hai ý nghĩa trái nhau.

### 16.2. Không để coercion âm thầm

```json
{"enabled":"false"}
```

và:

```json
{"enabled":false}
```

khác kiểu. Nếu bind string thành boolean quá rộng, validation của gateway và app có thể không thống nhất.

### 16.3. MongoDB null/missing query semantics

Bộ lọc `field: null` ở MongoDB có thể match cả documents không có field tùy query form. Nếu business cần *field tồn tại với null*, phải diễn đạt predicate rõ. Không giả định null = absent trong mọi engine.

### 16.4. Server defaults

Defaults nên áp dụng theo contract khi field bị thiếu, không tự ghi đè giá trị null có chủ ý trừ khi đã thiết kế như vậy.

## 17. Unicode, normalization và độ dài chuỗi

Một tên có thể có nhiều Unicode sequences hiển thị gần giống:

```text
é  (precomposed)
e + ◌́ (combining)
```

Một số systems dùng byte length, một số character count/code units, một số grapheme clusters.

### 17.1. Đặt đơn vị giới hạn rõ

`@Size(max=80)` trên Java `String` được tính theo semantics constraint provider đối với CharSequence length (thường là UTF-16 code units), không nhất thiết là 80 grapheme người dùng nhìn thấy. Một emoji có thể chiếm nhiều code units/bytes.

### 17.2. Giới hạn theo bytes khi lưu/truyền

NoSQL document/cache key/index constraints có thể tính theo bytes. Đo UTF-8 encoded length cho các fields nhạy cảm với byte cap, sau khi chọn normalization policy.

### 17.3. Khi nào chuẩn hóa?

Email/usernames/identifiers có thể cần canonicalization để tránh duplicate/confusable identities, nhưng đừng tự lower-case/trim mọi ngôn ngữ hoặc tên hiển thị mà không có rule nghiệp vụ.

### 17.4. Invalid UTF-8

Reject/handle malformed sequences rõ ràng tại decoding boundary. Hai lớp giải mã khác nhau có thể gây input interpretation mismatch.

### 17.5. Visually confusable

Hai strings có thể trông giống nhau nhưng mã Unicode khác; với tên người dùng, domain, payment reference hoặc resource slug, cần rule cho phép ký tự và uniqueness phù hợp.

## 18. Path traversal và field-path injection

NoSQL document updates thường dùng **dot paths**:

```text
preferences.language
shipping.address.city
```

Nếu client tự chọn field path:

```json
{
  "field": "role",
  "value": "ADMIN"
}
```

hoặc:

```json
{
  "field": "tenantId",
  "value": "someone-else"
}
```

và server gọi `Updates.set(field, value)`, nó có thể thay field nội bộ không cho phép.

### 18.1. Allowlist field paths

```java
public enum EditableProfileField {
    DISPLAY_NAME,
    BIO,
    LANGUAGE
}
```

Mapping:

```java
String path = switch (field) {
    case DISPLAY_NAME -> "displayName";
    case BIO -> "bio";
    case LANGUAGE -> "preferences.language";
};
```

### 18.2. Không nhận arbitrary nested paths

Những đường dẫn bắt đầu/kết thúc bằng dots, ký tự `$`, array index không hợp lệ hoặc cú pháp vendor-specific có thể gây rủi ro semantic; quan trọng hơn, path đến field không được ủy quyền vẫn là lỗ hổng ngay cả khi chỉ gồm ký tự chữ cái.

### 18.3. Với map metadata hợp lệ

Nếu nghiệp vụ cần user-defined keys, hãy lưu dưới một namespace riêng và encode/validate key để không bị hiểu thành query/update operator. Đồng thời giới hạn số keys, độ dài và total bytes.

## 19. NoSQL injection: nguyên nhân và lớp phòng vệ

**NoSQL injection** xảy ra khi input từ nguồn không đáng tin được diễn giải như **cú pháp lệnh, filter, operator, key path hoặc query language** thay vì chỉ là một giá trị dữ liệu.

Các nguồn thường gặp:

- Raw MongoDB query JSON được merge với request body.
- Ghép chuỗi CQL/Cypher/SQL-like filters.
- Cho user gửi nguyên Elasticsearch Query DSL mà không giới hạn.
- Dynamic field/collection/index names lấy trực tiếp từ client.
- Regex strings do client chọn với độ phức tạp không giới hạn.
- Redis commands/key patterns được xây từ untrusted fragments.

### 19.1. Data khác code

Cần giữ các phần sau tách biệt:

```text
Trusted query structure
+ Bound user values
+ Trusted, allowlisted field names
+ Server-enforced tenant/ACL predicate
```

### 19.2. Parameterization chưa đủ nếu cho chọn mọi field/operator

Prepared statements/builder APIs ngăn một lớp injection, nhưng request cho `sortBy=anyField`, regex vô hạn hoặc 10.000 filter clauses vẫn có thể tốn tài nguyên/vi phạm quyền. Cần thêm allowlist và query budget.

### 19.3. Không dùng escape thủ công thay parameterization

Một chuỗi tự `replace("'", "''")` không đủ cho mọi engine và operator syntax. Ưu tiên API bind/query builders với semantics cụ thể.

## 20. MongoDB: không gộp raw JSON từ client thành filter

Anti-pattern:

```java
// Không nên: biến JSON request tùy ý thành BSON filter
Document filter = Document.parse(userSuppliedJson);
collection.find(filter).first();
```

Client có thể gửi một object operator thay vì giá trị đơn:

```json
{"password": {"$ne": null}}
```

Nếu endpoint kỳ vọng equality password nhưng chấp nhận raw filter, query semantics đã bị thay đổi. Payload này là **ví dụ nhận diện anti-pattern**, không phải một kỹ thuật hợp lệ để xây authentication.

### 20.1. Dùng typed equality

```java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

Bson filter = Filters.and(
        Filters.eq("tenantId", principal.tenantId()),
        Filters.eq("username", request.username())
);
```

`request.username()` ở đây được dùng như **giá trị** chứ không được parse thành operator. Với authentication, vẫn cần xử lý password hashing, rate limits và phương thức xác thực đúng; không dùng NoSQL filter password từ client.

### 20.2. Tenant predicate phải được gắn server-side

Không chỉ nhận `tenantId` từ JSON rồi tin nó. Cần principal-derived scope và authorization trên kết quả/mutation.

### 20.3. Dùng builder cho update

```java
import com.mongodb.client.model.Updates;

Bson update = Updates.combine(
        Updates.set("displayName", request.displayName()),
        Updates.set("bio", request.bio())
);
```

Không cho request tự gửi `$set`, `$inc`, `$unset` nếu API chỉ cho sửa hồ sơ.

### 20.4. Không mở raw aggregation pipeline cho caller

MongoDB aggregation operators rất mạnh; một user-supplied pipeline có thể truy cập collections khác hoặc tạo chi phí lớn tùy quyền. Cung cấp các truy vấn predefined được parameterized và RBAC.

## 21. MongoDB BSON: ObjectId, dates, decimals và binary

Một document BSON có thể chứa:

```text
ObjectId
Date
Decimal128
Binary
Int32 / Int64 / Double
Array / EmbeddedDocument
```

### 21.1. ObjectId

Một chuỗi `"123"` không phải ObjectId hợp lệ. Nếu route yêu cầu ObjectId, validate định dạng trước khi gọi constructor/driver và trả lỗi 400 thay vì 500.

```java
import org.bson.types.ObjectId;

if (!ObjectId.isValid(rawId)) {
    throw new IllegalArgumentException(
            "Invalid identifier"
    );
}
ObjectId id = new ObjectId(rawId);
```

### 21.2. Decimal128

BSON Decimal128 không đồng nghĩa JSON `double`. Kiểm soát precision/scale khi mapping sang BigDecimal cho số tiền.

### 21.3. Date

BSON Date thường biểu diễn thời điểm (timestamp) với độ phân giải theo driver/format; phân biệt `Instant` với `LocalDate`, múi giờ và parsing ISO-8601. Không lấy timezone của server làm chính sách nghiệp vụ một cách ngầm định.

### 21.4. Binary

Một trường binary encoded Base64 có thể decode ra kích thước lớn. Áp byte cap trước/sau decode; không chỉ `@Size` chuỗi.

### 21.5. Array types

MongoDB document/array size limits có thể từ chối write, nhưng parser Java có thể tiêu tốn nhiều heap trước đó. Chặn ở API boundary.

## 22. Cassandra CQL: prepared statements

Anti-pattern:

```java
String cql = "SELECT * FROM users WHERE username = '"
        + userInput + "'";
session.execute(cql);
```

Nếu `userInput` chứa syntax đặc biệt, server có thể diễn giải thành phần của CQL. Hãy dùng bind variables:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
        "SELECT user_id, display_name "
        + "FROM users_by_username WHERE username = ?"
);

BoundStatement bound = prepared.bind(request.username());
session.execute(bound);
```

### 22.1. Parameter binding có scope

Placeholders dùng cho **values**, không phải tùy tiện mọi identifier hay cấu trúc CQL. Table names, columns, ORDER BY và query shapes nên được chọn từ allowlist/server code.

### 22.2. Chọn partition key hợp lệ

Một query an toàn khỏi injection vẫn có thể bị từ chối hoặc tạo tải scan lớn nếu schema không hỗ trợ. `ALLOW FILTERING` không phải giải pháp cho endpoint tùy ý.

### 22.3. Page size và timeout

Giới hạn page size/token behavior, timeout và result iteration. Một `SELECT` returning millions of rows có thể tốn memory nếu Java gom hết vào list.

### 22.4. Data type validation

CQL `uuid`, `timestamp`, `decimal`, `bigint` cần mapping đúng. Không nhận string bất kỳ rồi cố parse muộn trong DAO với lỗi không kiểm soát.

## 23. Neo4j Cypher và graph query parameters

Một anti-pattern:

```java
String cypher = "MATCH (u:User {name:'"
        + userInput + "'}) RETURN u";
```

Nên dùng parameters:

```java
import org.neo4j.driver.Query;
import org.neo4j.driver.Values;

Query query = new Query(
        "MATCH (u:User {tenantId: $tenantId, name: $name}) "
        + "RETURN u LIMIT 20",
        Values.parameters(
                "tenantId", principal.tenantId(),
                "name", request.name()
        )
);
```

### 23.1. Không để caller tự chọn label/relationship type

Nếu cho phép `MATCH (n:<userProvidedLabel>)` bằng string concatenation, label là cú pháp, không phải bound value như `name`. Sử dụng enum/allowlist để chọn một query predefined.

### 23.2. Tránh graph traversal không giới hạn

Một query có variable-length traversal không bounded trên graph lớn có thể gây CPU/memory exhaustion. Giới hạn hops, fan-out, result size, timeout và authorization.

### 23.3. Row-level/graph-level ACL

Binding `tenantId` trong một query không thay thiết kế quyền trên các relationship paths hoặc dữ liệu cross-tenant được liên kết.

## 24. DynamoDB expressions: tách names và values

DynamoDB cho xây condition/filter/update expression với placeholders:

```text
#s = :expected
```

Ví dụ Java SDK v2 minh họa:

```java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;

UpdateItemRequest update = UpdateItemRequest.builder()
        .tableName("Orders")
        .key(Map.of(
                "orderId",
                AttributeValue.builder().s(orderId).build()
        ))
        .updateExpression("SET #s = :newStatus")
        .conditionExpression("#s = :expected")
        .expressionAttributeNames(Map.of(
                "#s", "status"
        ))
        .expressionAttributeValues(Map.of(
                ":newStatus",
                AttributeValue.builder().s("PAID").build(),
                ":expected",
                AttributeValue.builder()
                        .s("PENDING").build()
        ))
        .build();
```

### 24.1. Vì sao ExpressionAttributeNames?

Dùng aliases cho attribute names và placeholders cho values. Tên bảng/field động vẫn phải allowlist và auth; expression builder không tự kiểm soát business permissions.

### 24.2. `conditionExpression` là invariant guard

Nếu business cần chuyển `PENDING → PAID` chỉ khi đúng trạng thái, atomic condition ở source chống race giữa writers. Input validation không thay atomicity.

### 24.3. Giới hạn `Scan` và filter

API cho phép user gửi filter JSON tùy ý rồi backend gọi `Scan` có thể gây tốn RCU/cost ngay cả khi query structure không bị injection. Hạn chế access paths và request capacity.

### 24.4. SDK không thay schema

`AttributeValue` có các variants string/number/list/map/binary. Adapter phải biết trường nào nhận type nào, không convert mọi JSON node thành arbitrary DynamoDB AttributeValue.

## 25. Elasticsearch/OpenSearch: giới hạn Query DSL

Search API thường cho rich query DSL. Một payload do client tự tạo:

```json
{
  "query": {
    "regexp": {
      "title": ".*"
    }
  },
  "size": 1000000
}
```

Có thể quá tốn kém, tùy index, query và cấu hình. An toàn không chỉ là tránh code injection; còn là **giới hạn search cost**.

### 25.1. Không nhận arbitrary DSL nếu không cần

Frontend có thể gửi:

```json
{
  "text": "database",
  "category": "books",
  "sort": "NEWEST",
  "limit": 20
}
```

Backend ánh xạ sang một query builder predefined, gắn tenant filter và clamp limit.

### 25.2. Các controls

- Allowlist searchable/sortable fields.
- `size` và pagination depth caps.
- Query timeout/deadline và cancellation policy.
- Không cho user tùy chọn scripting, regex/fuzzy/wildcard cost tùy ý.
- Tenant/ACL filter server-side.
- Rate limit và per-user/tenant query budget.
- Kiểm tra total hits/scroll/PIT lifecycle và resource usage.

### 25.3. Search results cần output encoding

Một document từ search index có field do user nhập. Khi render lên HTML/UI, dùng context-aware output escaping để tránh stored XSS, mặc dù dữ liệu đã qua NoSQL.

### 25.4. Document index names

Không để client chọn arbitrary index/alias mà service account có quyền đọc; điều đó có thể vượt data boundary.

## 26. Redis: keys, commands và pattern scope

Redis có giao diện key-value, nhưng cũng tồn tại những rủi ro từ string input:

```text
GET session:<user-id>
HSET user:<id> field value
SCAN MATCH pattern
EVAL script ...
```

### 26.1. Namespace do server chọn

Một key có thể định nghĩa:

```text
app:v1:tenant:<trusted-tenant-id>:user:<validated-user-id>
```

Không nối `tenantId` do client tự gửi để tạo key truy cập dữ liệu người khác.

### 26.2. Key encoding

Nếu identifiers có thể chứa `:` hoặc wildcard chars, nên encode hoặc dùng key formatter cấu trúc rõ, tránh collisions. Với Redis Cluster, hash tags `{...}` có routing semantics; không cho caller thao túng hash tag để gây hotspot/cross-slot behavior.

### 26.3. SCAN vs KEYS

Một endpoint “list all keys matching user pattern” có thể gây tải, leak data hoặc thậm chí block server nếu dùng lệnh không phù hợp. Cần hạn chế permissions, prefix scope và page work budget. `SCAN` cũng có thể tốn chi phí trên keyspace lớn và không tự là authorization filter.

### 26.4. Lua/command selection

Không cho untrusted client gửi tên Redis command hoặc script raw. Dùng operations predefined, ACL và time/resource bounds.

### 26.5. Cache poisoning

Dữ liệu JSON từ Redis có thể bị ghi bởi service khác hoặc bị stale. Deserialize qua typed DTO và schemaVersion; không dùng Redis payload để cấp role/authz mới mà không có authoritative policy.

## 27. Field-name injection, sort và dynamic query

Một endpoint có thể cho:

```text
GET /products?sortBy=price&direction=desc
```

Điểm rủi ro là **field name và direction đều ảnh hưởng cú pháp query**.

### 27.1. Dùng enum

```java
public enum SortField {
    PRICE,
    CREATED_AT,
    NAME
}

public enum SortDirection {
    ASC,
    DESC
}
```

Định nghĩa mapping cố định:

```java
String fieldName = switch (sortField) {
    case PRICE -> "priceMinor";
    case CREATED_AT -> "createdAt";
    case NAME -> "nameNormalized";
};
```

Không nối `sortBy` input thẳng thành CQL/Cypher query hoặc Mongo field path.

### 27.2. Sorting có ảnh hưởng hiệu năng

Ngay cả field hợp lệ vẫn có thể không được index hoặc tạo in-memory sort trên hàng triệu records. Chỉ allowlist những sorts được query plan và capacity budget hỗ trợ.

### 27.3. Filter DSL an toàn

Nếu cần advanced filters, thiết kế AST/grammar hẹp với limits:

```text
max predicates = 8
max nesting depth = 3
allowed operators = EQ, IN, RANGE
max IN values = 20
allowed fields = known indexed fields
```

Sau đó convert AST sang native query builder; không parse raw user query language.

## 28. Regex injection và nguy cơ ReDoS

Nhiều API cung cấp tìm kiếm tên, mã khách hàng hoặc chuỗi mô tả. Nếu backend chấp nhận **regex nguyên văn do user gửi**, có hai rủi ro:

1. Người dùng điều khiển pattern matching ngoài phạm vi tìm kiếm cho phép.
2. Một regex có backtracking phức tạp có thể dùng CPU lớn bất thường (*Regular Expression Denial of Service – ReDoS*).

### 28.1. Phân biệt literal search và regex search

Nếu người dùng nhập:

```text
a.*b
```

và mục tiêu là tìm **chuỗi chứa đúng các ký tự `a.*b`**, backend không nên biến nó thành regex matching mọi chuỗi bắt đầu bằng `a` và kết thúc bằng `b`.

### 28.2. Policy ưu tiên

- Sử dụng exact/prefix search hoặc full-text index có cấu hình phù hợp.
- Không cho phép arbitrary regex từ public API trừ khi có nhu cầu thật.
- Nếu hỗ trợ regex nâng cao, chỉ cho grammar/operators hẹp và giới hạn độ phức tạp, pattern length, scan scope, time/CPU.
- Có query deadline và hạn chế result size.
- Không coi regex pattern cap 100 ký tự là giải pháp ReDoS đầy đủ.

### 28.3. Tạo literal pattern khi thật sự cần

Trong Java:

```java
import java.util.regex.Pattern;

String literal = Pattern.quote(request.searchText());
Pattern pattern = Pattern.compile(literal);
```

Đây là cách escape **cho Java regex engine**. Với MongoDB query regex, PCRE engine có semantics riêng; cần kiểm tra cách driver truyền pattern và khả năng index sử dụng. Một literal regex không thay query cost limit.

### 28.4. Case-insensitive search

Chuyển thành lowercase không đúng với mọi Unicode/collation; nên cân nhắc normalized search field, collation/index hoặc full-text engine tương thích nhu cầu.

## 29. Pagination, limit và chi phí đọc dữ liệu

Một endpoint nhận `limit` có thể bị lạm dụng:

```text
GET /orders?limit=100000000
```

Ngay cả khi query filter an toàn, database/Java mapper có thể đọc quá nhiều dữ liệu.

### 29.1. Bắt buộc giới hạn

```java
public static int boundedPageSize(
        Integer requested
) {
    int defaultSize = 20;
    int maxSize = 100;

    if (requested == null) {
        return defaultSize;
    }
    if (requested < 1 || requested > maxSize) {
        throw new IllegalArgumentException(
                "pageSize must be within [1, 100]"
        );
    }
    return requested;
}
```

### 29.2. Clamp hay reject?

- **Clamp:** client gửi `1_000` nhưng server trả 100; nếu chọn cách này, API contract phải nói rõ effective limit.
- **Reject:** trả 400 khi vượt phạm vi; dễ phát hiện lỗi/tấn công và giữ request semantics minh bạch.
  
Không có một lựa chọn duy nhất cho mọi API; phải nhất quán.

### 29.3. Offset sâu

`offset=1_000_000` có thể làm query tốn scan/sort. Với data lớn, ưu tiên continuation tokens/keyset pagination theo storage model, kèm giới hạn số pages/độ sâu nếu cần.

### 29.4. Continuation token

Đừng để token chứa thông tin quyền/tenant không có integrity protection. Token có thể cần ký, mã hóa hoặc lưu server-side tùy metadata; vẫn phải validate token hết hạn, query fingerprint và scope của principal.

### 29.5. Per-request work budget

Giới hạn **khối lượng quét**, không chỉ số results. Một query trả 10 items nhưng scan 10 triệu documents vẫn có thể gây DoS/cost spike.

## 30. Giới hạn độ phức tạp truy vấn NoSQL

Một API query builder có thể mở cửa tấn công ngay cả khi mọi giá trị được bound an toàn.

Ví dụ người dùng yêu cầu:

```text
OR 1,000 clauses
IN 100,000 values
sort by unindexed field
regex/fuzzy search on every field
graph traversal 50 hops
aggregation with many nested stages
```

### 30.1. Query budget model

Định nghĩa một budget có thể gồm:

```text
maxPredicates = 8
maxBooleanDepth = 3
maxInValues = 20
maxSortFields = 2
maxPageSize = 100
maxTraversalHops = 4
maxAggregationStages = 5
maxExecutionTimeMs = 300
```

Đây là giá trị minh họa, không phải khuyến nghị cứng cho mọi ứng dụng.

### 30.2. Query whitelist

Một ứng dụng nhỏ có thể an toàn hơn khi expose các **query patterns cố định**:

- `GetById`
- `ListByTenantAndCreatedAt`
- `SearchProductsByText`
- `OrdersByCustomerAndStatus`

Thay vì cho caller gửi bất kỳ filter DSL.

### 30.3. Explain và index

Trước khi mở API search mới, kiểm tra plan và truy vấn đại diện trên dataset lớn. Input validation có thể hợp lệ nhưng query sẽ quá tốn chi phí nếu không có index.

### 30.4. Quyền khác với cost

Một request bị giới hạn `limit=100` vẫn có thể đọc nhầm dữ liệu tenant khác nếu query thiếu tenant predicate. Cost controls không phải authorization controls.

## 31. Nén và nguy cơ decompression bomb

Một request có thể khai báo nén GZIP. Một vài kilobytes compressed bytes có thể giải nén thành hàng trăm MiB hoặc hơn.

```text
Compressed 8 KiB
       |
       v
Decompress
       |
       v
Expanded 400 MiB
       |
       v
JSON parse / object allocation
```

### 31.1. Hai giới hạn khác nhau

- `maxCompressedBytes`: lượng bytes nhận từ mạng.
- `maxDecompressedBytes`: lượng bytes sau giải nén.

Một HTTP content-length cap **trước giải nén** chưa giới hạn expanded body.

### 31.2. Streaming decompression có budget

Không dùng một lời gọi đọc toàn input vào byte array vô hạn. Giải nén từng buffer và đếm expanded bytes; dừng khi vượt ngưỡng.

Giả mã:

```text
read compressed stream
create bounded decompressor
while bytes available:
    chunk = decompressor.read(buffer)
    decompressedTotal += chunk.length
    if decompressedTotal > endpointMax:
        reject 413
    feed bounded parser
```

### 31.3. CPU budget

Có thể có compressed input nhỏ nhưng cần nhiều CPU để xử lý. Thêm timeout, concurrency cap và request throttling; byte cap không tự bảo vệ CPU.

### 31.4. Nhiều tầng nén

Nếu payload qua reverse proxy, service mesh và application decoder, phải biết lớp nào giải nén và kiểm soát kích thước. Tránh trường hợp proxy kiểm tra size compressed còn ứng dụng nhận body expanded không giới hạn.

## 32. ZIP import, Base64 và binary payloads

Một endpoint upload ZIP/NDJSON/CSV có rủi ro riêng.

### 32.1. ZIP

Nếu nhận file ZIP:

- Giới hạn compressed size và tổng uncompressed bytes.
- Giới hạn số entries, depth của archive lồng nhau.
- Reject paths nguy hiểm khi giải nén ra filesystem (`../`, absolute path, symlink traversal).
- Kiểm tra file types và extension/content mismatch.
- Không tự extract theo tên file không tin cậy.
- Giới hạn CPU/thời gian và disk quota.

### 32.2. Base64

Chuỗi Base64 có thể phình dữ liệu khoảng 4/3 so với bytes gốc. Giới hạn **cả encoded string và decoded byte length**, không nhận image/video khổng lồ qua trường JSON nhỏ trong design.

### 32.3. NDJSON

Khi import nhiều JSON lines, giới hạn:

- Dung lượng mỗi dòng.
- Số records.
- Tổng expanded bytes.
- Độ sâu/field count từng record.
- Batch size và thời gian xử lý.
- Transaction/partial failure semantics.
- Schema version và dedupe.

### 32.4. CSV/formula injection khác deserialization

Một CSV export có dữ liệu người dùng chứa ký tự spreadsheet formula có thể gây spreadsheet formula injection khi ai đó mở bằng ứng dụng bảng tính. Đó là **output encoding** theo consumer context, không phải NoSQL query injection, nhưng cần được kiểm soát tại export boundary.

## 33. Streaming parse và backpressure

Một JSON array 1 triệu items không nên mặc định được bind vào một `List<Object>` trong heap trước khi bắt đầu xử lý.

```text
HTTP upload
    |
    v
Streaming decoder
    |
    v
Validate record
    |
    v
Bounded queue
    |
    v
NoSQL batch writer
```

### 33.1. Khi nào dùng streaming?

- Bulk import.
- NDJSON event ingestion.
- CDC feed consumption.
- Data migrations.
- Large export/restore.
- Analytics ingestion.

### 33.2. Không vượt memory bằng batching vô hạn

Giới hạn `batchSize`, `queueCapacity`, số outstanding DB writes, bytes buffered và timeout. Batch 1.000 items x 2 MiB có thể tốn gần 2 GiB payload trước overhead.

### 33.3. Backpressure

Nếu ingress 5.000 records/s nhưng sink ghi 2.000 records/s, backlog tăng 3.000/s. Nếu không có capacity/admission control, memory/disk sẽ cạn.

### 33.4. Transaction size

Một import có 100.000 items không nhất thiết nên chạy trong một transaction duy nhất. Chọn batch/partition scope phù hợp và công bố partial-success/retry/idempotency contract.

### 33.5. Hủy request

Client disconnect không chắc DB writes đang in-flight bị rollback. Với import bất đồng bộ, dùng operation ID, trạng thái accepted/committed và cancellation semantics rõ.

## 34. Schema validation ở đâu?

Một cấu trúc quan trọng:

```text
Wire schema
   |
DTO schema
   |
Domain invariant
   |
Database schema/index/constraint
   |
Consumer/read model schema
```

### 34.1. Wire schema

JSON Schema/OpenAPI/Protobuf/Avro có thể mô tả field types, required/optional, arrays, ranges và nested structures.

### 34.2. DTO schema

Java record/Bean Validation kiểm tra giá trị sau binding.

### 34.3. Domain invariant

Ví dụ `startAt < endAt` hoặc `quantity <= available` có thể cần logic domain/atomic source condition, không thể chỉ dùng `@Size`.

### 34.4. Database validation

MongoDB có thể hỗ trợ collection validators theo JSON Schema semantics; các NoSQL khác có kiểu dữ liệu/constraints khác. Database validation là lớp bổ sung, không thay API byte limits/authorization.

### 34.5. Schema evolution

Một event cũ có `status` và event mới có `payment.state`; consumer phải biết version để migrate. Không bật “ignore everything unknown” nếu điều đó làm bỏ trường bảo mật quan trọng.

## 35. Dùng Bean Validation cho Java REST API

Ví dụ DTO rõ ràng:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateOrderRequest(

        @NotBlank
        @Size(max = 64)
        String customerReference,

        @NotNull
        @Size(min = 1, max = 25)
        List<@Valid LineRequest> lines
) {
    public record LineRequest(
            @NotBlank
            @Size(max = 50)
            String sku,

            @Min(1)
            @Max(100)
            int quantity
    ) {}
}
```

Controller:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    public ResponseEntity<OrderResult> create(
            @Valid @RequestBody CreateOrderRequest request
    ) {
        OrderResult result = service.create(request);
        return ResponseEntity.ok(result);
    }
}
```

`OrderService` và `OrderResult` là các kiểu ứng dụng cần triển khai. Ví dụ chỉ minh họa **cách bind và validate**, chưa có authentication/transaction/idempotency.

### 35.1. `@Valid` ở đâu?

Cần `@Valid` tại `@RequestBody` và trên các phần tử nested nếu muốn validation lan xuống. Provider/Spring version và classpath phải có Bean Validation implementation phù hợp.

### 35.2. Giới hạn danh sách

`@Size(max=25)` chặn requests có quá nhiều lines **sau khi bind**, nên vẫn cần HTTP byte cap trước parser.

### 35.3. Giá trị primitive

`int quantity` mặc định 0 nếu không map field trong một số cơ chế; nếu cần phân biệt missing vs 0, dùng `Integer` với `@NotNull`. DTO mẫu có `@Min(1)` nên 0 bị reject, nhưng thiết kế `Integer` có thể rõ hơn cho required data.

### 35.4. Mối quan hệ giữa fields

Dùng custom validation/service logic khi điều kiện phụ thuộc nhiều fields. Không cố nhét toàn domain rule vào regex annotation.

## 36. Cross-field validation và business invariants

Ví dụ đặt lịch:

```json
{
  "startAt": "2026-11-14T10:00:00Z",
  "endAt": "2026-11-14T09:00:00Z"
}
```

Các strings đều đúng ISO-8601 nhưng `endAt` trước `startAt`, không hợp lệ.

### 36.1. Validation nhiều tầng

```text
Syntactic: parse Instant thành công
Structural: start/end không null
Semantic: end > start
Authorization: resource thuộc đúng tenant
Concurrency: slot chưa bị người khác claim
Atomicity: claim tại source bảo vệ bằng condition
```

### 36.2. Invariant cạnh tranh không thể giải bằng DTO validation

Hai clients đều nhập `quantity=1`, cùng thấy inventory=1, vẫn có thể oversell nếu backend chỉ `read → check → write`. Dùng atomic update/CAS/transaction tại source với phạm vi thích hợp.

### 36.3. Idempotency key

API tạo payment/order có thể nhận một idempotency key với length/charset cap và kiểm tra scope theo principal. Không cho client dùng key không giới hạn tạo hàng triệu trạng thái hoặc vượt tenant.

## 37. Tối thiểu hóa quyền ở lớp serializer và DTO đầu ra

Serialization có chiều **đi ra**. Một entity từ DB có thể chứa:

```java
class UserDocument {
    String id;
    String email;
    String passwordHash;
    String resetTokenHash;
    String tenantId;
    String role;
    String displayName;
    String internalNotes;
}
```

Nếu trả `UserDocument` nguyên vẹn qua REST, dữ liệu nhạy cảm có thể bị lộ ngay cả khi input không có vấn đề.

### 37.1. Response DTO

```java
public record PublicUserResponse(
        String id,
        String displayName
) {}
```

### 37.2. Không chỉ dựa vào `@JsonIgnore`

Annotation có thể hữu ích, nhưng một entity được dùng trong nhiều contexts có thể dễ bị thay đổi và leak fields mới. Response DTO allowlist giúp hợp đồng hiển thị rõ hơn.

### 37.3. Role-specific projection

Admin response khác public response. Service phải authorize trước khi chọn DTO; không nhận `"view":"admin"` từ query param rồi tự dùng admin serializer.

### 37.4. Logging và tracing

Không log toàn bộ serialized DTO nếu nó chứa access token, PII, OTP hoặc payment details. Có log fields allowlist/correlation IDs riêng.

## 38. Encrypt, sign, compress không thay validation

Một payload:

```text
Serialize -> Compress -> Encrypt -> Send
```

và:

```text
Receive -> Decrypt -> Decompress -> Parse -> Validate
```

Mỗi bước có rủi ro riêng:

- Encryption giúp confidentiality nếu key/nonce/mode quản lý đúng.
- Authentication/MAC/chữ ký giúp integrity/authenticity theo contract.
- Compression giảm transfer bytes nhưng có thể tạo expansion bomb.
- Schema parser cần size/depth/type caps.
- Authorization cần principal/resource context.

### 38.1. Không deserialize trước khi xác thực khi protocol yêu cầu

Với signed webhook, có thể cần xác minh chữ ký dựa trên raw bytes đúng cách, kiểm tra timestamp/replay window, rồi parse bounded payload. Đừng reserialize JSON rồi verify signature nếu signature protocol ký **raw request body**.

### 38.2. Không tin payload chỉ vì encrypted

Nếu kẻ tấn công có thể điều khiển plaintext trước khi một dịch vụ mã hóa nó, sau decrypt dữ liệu vẫn có thể không hợp lệ.

### 38.3. Tránh compression với dữ liệu nhạy cảm không phù hợp

Trong một số giao thức, compression kết hợp secrets và attacker-controlled content có thể tạo side channel. Xem threat model/giao thức trước khi bật nén tùy ý.

## 39. Cache và message broker cũng cần schema/limits

Một hệ dùng Kafka hoặc Redis Streams có thể đọc messages do nhiều producers khác nhau gửi:

```text
Order Service
     |
     v
Kafka topic
     |
     v
Java Consumer -> deserialize -> update NoSQL
```

### 39.1. Consumer không nên deserialize `Object` tùy ý

Dùng typed envelope:

```java
public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        T payload
) {}
```

Trong implementation thực, `T` cần được bind theo registry/mapping of **allowed event types**, không theo tên class do producer gửi.

### 39.2. Event size

Kafka broker/topic có message size limits; producer/client/deserializer và application cũng cần caps. Không giả định broker max message size tự bảo vệ mọi nested payload sau decompression.

### 39.3. Unknown event versions

Không silently map event version mới sang object cũ nếu làm mất trường bắt buộc. Có compatibility policy, quarantine/DLQ theo tính chất event và alert.

### 39.4. Retry và poison messages

Một invalid payload có thể bị redeliver vô hạn làm kẹt partition. Cần giới hạn retries, phân loại parsing/validation errors, DLQ/quarantine, visibility và recovery.

### 39.5. Idempotency

Một event có thể được giao lại; mutation tại NoSQL cần stable eventId/aggregate version để ngăn side effects trùng. Validation không thay dedupe/transaction.

## 40. CDC deserialization: before/after và schema drift

Change Data Capture mang theo những thay đổi của source DB:

```json
{
  "operation": "UPDATE",
  "key": {"orderId":"O100"},
  "after": {"status":"PAID"},
  "schemaVersion": 3
}
```

### 40.1. Raw CDC chưa chắc có full document

Một update có thể chỉ có delta. Nếu consumer deserialize như full `OrderDocument`, các required fields có thể thiếu, tạo null/default sai.

### 40.2. Deletes

Delete event có thể chỉ có document key và `after=null`. Không để generic mapper crash rồi coi delete như một invalid event cần retry mãi.

### 40.3. Schema migration

Dữ liệu lịch sử dùng schema cũ; consumer cần reader logic tương thích theo phiên bản hoặc migration path rõ ràng.

### 40.4. PII đã bị xóa

Before-image/CDC logs có thể còn chứa thông tin mà người dùng yêu cầu xóa. Cần retention, redaction và deletion propagation; không log raw before-image ra hệ observability.

### 40.5. Quota và backpressure

Một event payload bất thường có thể làm consumer OOM hoặc chặn cả stream. Giới hạn decode size, timeout, schema, DLQ và sink work budget.

## 41. JSON Schema và database validator

Một JSON Schema concept:

```json
{
  "type": "object",
  "required": ["name", "priceMinor"],
  "additionalProperties": false,
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 80
    },
    "priceMinor": {
      "type": "integer",
      "minimum": 0,
      "maximum": 100000000
    }
  }
}
```

Schema này cho phép giới hạn cấu trúc trước khi application dùng dữ liệu; cần chọn validator và dialect phù hợp, kiểm tra type coercion, recursion và tài nguyên khi validation.

### 41.1. MongoDB collection validation

MongoDB có `$jsonSchema` theo cú pháp BSON/schema validation riêng. Không copy JSON Schema ngoài vào MongoDB một cách mù quáng vì format, types và features có thể khác.

### 41.2. Database constraints như defense-in-depth

Dù application validator bỏ sót, database vẫn có thể từ chối document sai. Nhưng nếu endpoint nhận 500 MiB JSON, database validator không ngăn chi phí network/parse trước đó.

### 41.3. Error handling

Nếu database từ chối vì validation, mapping lỗi thành 4xx hoặc 5xx phụ thuộc root cause: input sai contract là 4xx; bug của server mapping có thể là lỗi nội bộ cần alert. Không tiết lộ schema nội bộ nhạy cảm ra response.

### 41.4. Schema drift

Mỗi service dùng schema version khác nhau có thể ghi/đọc không tương thích. Dùng expand-migrate-contract và contract tests.

## 42. Giới hạn thời gian xử lý và tài nguyên

Một input nhỏ có thể khiến DB chạy một query đắt:

```text
Request body: 100 bytes
Query: scan hàng trăm triệu documents
```

Vì vậy cần **resource budget** vượt ngoài parser.

### 42.1. Các mốc deadline

- Network receive timeout.
- JSON parse deadline/budget.
- Handler/request total deadline.
- Connection pool wait timeout.
- Driver/database query timeout.
- Pagination/stream total operation time.
- Broker consumer processing deadline.

### 42.2. Timeout không đồng nghĩa operation chưa commit

Một write timeout có thể đã commit ở NoSQL nhưng response mất. Dùng idempotency key/expected version và kiểm tra authoritative status khi retry.

### 42.3. Concurrency bulkhead

Giới hạn số expensive queries/import jobs đồng thời; tách executor/thread pool hoặc quota cho heavy endpoints để không làm nghẽn toàn API.

### 42.4. Rate limit theo tenant

Một tenant gửi hàng nghìn payload hợp lệ về cú pháp vẫn có thể làm cạn CPU/DB capacity. Rate limit và query budget là lớp bảo vệ availability và fairness.

### 42.5. DB quota

Một số managed NoSQL có request-unit/capacity billing; validate/truncate request sớm giúp bảo vệ chi phí nhưng cần monitor consumed capacity thực tế.

## 43. Cách xử lý lỗi không để lộ dữ liệu nội bộ

Một response nên mô tả input nào không hợp lệ ở mức vừa đủ:

```json
{
  "type": "https://example.invalid/problems/invalid-input",
  "title": "Invalid request body",
  "status": 400,
  "detail": "The request has invalid fields or exceeds limits",
  "requestId": "req-123"
}
```

URL chỉ minh họa.

### 43.1. Không trả stack trace

Tránh lộ class names, internal field names, collections, connection strings, SQL/CQL/aggregation statements và stack traces.

### 43.2. Không echo lại payload độc hại

Một response lỗi chứa nguyên body có thể gây stored/reflected injection ở nơi xem logs hoặc frontend.

### 43.3. Phân loại lỗi

| Trường hợp | Hướng HTTP thường gặp |
|---|---|
| Body vượt cap | 413 |
| JSON malformed | 400 |
| Duplicate key/unknown field | 400/422 theo API |
| Field vượt size/range | 400/422 |
| Không được sửa resource | 403/404 theo policy |
| Too many requests | 429 |
| Query deadline exceeded | 503/504 hoặc API-specific semantics |
| Server mapper bug | 500, log/alert nội bộ |

### 43.4. Error consistency

Nếu gateway reject ở tầng body size nhưng app reject ở DTO layer, response format có thể khác. Có thể chuẩn hóa ở API gateway/controller advice trong phạm vi hỗ trợ.

## 44. Audit và observability cho input abuse

Các chỉ số hữu ích:

- HTTP 400/413/422/429 theo endpoint.
- JSON parse errors, duplicate-key rejects.
- Payload bytes và estimated decoded bytes.
- Max nesting-depth violations.
- DTO constraint violations theo category.
- Unknown field/type coercion attempts.
- Query timeout/throttle và scanned-records cost.
- Regex/aggregation/graph traversal rejects.
- Authentication/authorization failures.
- Tenant quota exhaustion.
- Broker poison messages/DLQ size.
- Deserialization time/CPU/GC/heap allocation.
- Serialization output size và PII leakage alerts.

### 44.1. Không gắn user-provided raw field vào metric labels

Không tạo metric tag `invalidValue="long-attack-string..."`; sẽ gây high-cardinality và leak data. Ghi category và endpoint/operation labels hữu hạn.

### 44.2. Logs có thể là mục tiêu tấn công

Untrusted strings chứa newline/control chars có thể giả log lines nếu ghi thô. Dùng structured logging và escape/sanitize phù hợp; hạn chế payload truncation.

### 44.3. Quan sát trước và sau limit change

Nếu giảm JSON size cap, monitor 413 và client compatibility. Nếu tăng limit, monitor memory, GC, DB load và abuse để biết rủi ro thay đổi.

### 44.4. Không coi mọi validation error là tấn công

Client bug, rollout schema không đồng bộ hoặc integration lỗi cũng tạo 400/422. Investigate theo tenant/version/pattern thay vì block vô điều kiện.

## 45. Case study A: MongoDB login filter nhận raw object

**Bối cảnh:** Endpoint nhận JSON username/password, rồi backend gộp body thành MongoDB filter.

Đường lỗi:

```text
JSON object from client
        |
        v
Document.parse / merge into filter
        |
        v
MongoDB query
```

### 45.1. Nguyên nhân

Một value đáng lẽ là string lại được diễn giải thành object chứa toán tử database. Client kiểm soát query structure.

### 45.2. Cách sửa

1. Định nghĩa DTO `username` và `password` là strings với length caps.
2. Reject JSON object/array nếu field yêu cầu string.
3. Lookup user bằng typed equality `Filters.eq("username", value)`.
4. So password qua password-hashing verifier an toàn, không query plaintext password.
5. Enforce rate limits, lockout/throttling và audit theo security policy.
6. Tránh account enumeration trong response.
7. Test các payload sai kiểu/toán tử.
8. Giữ pool/query timeout và index trên username.

### 45.3. Không chỉ fix bằng regex blacklist

Chặn substring `$ne` trong username không giải quyết việc accept object/operator hoặc một payload syntax khác. Cần tách dữ liệu khỏi cấu trúc truy vấn.

## 46. Case study B: Spring endpoint cho sửa `role`

**Bối cảnh:** API dùng entity trực tiếp:

```java
@PutMapping("/profile")
public UserDocument update(
        @RequestBody UserDocument body
) {
    return repository.save(body);
}
```

Một user có thể gửi `isAdmin`, `tenantId`, `credits`, version metadata hoặc ID của người khác.

### 46.1. Phân tích

- Mass assignment.
- Thiếu identity binding vào principal.
- Thiếu authorization.
- Có thể có lost update nếu save blind.
- Có thể trả entity chứa secrets.

### 46.2. Thiết kế lại

```text
Authenticated principal
       |
Typed UpdateProfileRequest DTO
       |
Validate allowed fields
       |
Read/authorize source resource
       |
Atomic conditional update by tenant+id+version
       |
PublicProfileResponse DTO
```

### 46.3. Không dùng `@JsonIgnore` làm policy quyền duy nhất

Một mapping/serialization path khác có thể bỏ qua annotation hoặc field mới được thêm vào. DTO và explicit update fields rõ hơn.

### 46.4. Test

Payload có `role`, `tenantId`, `balanceMinor` phải reject hoặc không ảnh hưởng nguồn; API không được rò rỉ các fields trong response.

## 47. Case study C: JSON nhỏ nhưng query cực đắt

Một search endpoint nhận:

```json
{
  "query": "*",
  "sort": "unindexedField",
  "limit": 1000000
}
```

Body chỉ vài chục bytes nhưng yêu cầu search toàn index.

### 47.1. Sai lầm

Chỉ đặt body cap và `@NotBlank`, không có query cost model.

### 47.2. Giải pháp

- Text length caps và grammar hẹp.
- Sort field allowlist có index.
- Page size/offset caps.
- Query template/builder thay raw DSL.
- Database timeout, scanned-work budget nếu có.
- Per-tenant rate limit.
- Monitoring request units/CPU/query latency.
- Optional async export cho use case lấy dataset lớn.

### 47.3. Trả kết quả an toàn

Chỉ trả DTO fields cần thiết; sanitize/escape khi render thành HTML.

## 48. Case study D: Consumer nhận poison event

**Bối cảnh:** Kafka consumer đọc `OrderUpdated` event, dùng Jackson default typing không được kiểm soát và ghi vào MongoDB.

Một event không đúng schema gây exception, consumer retry mãi, partition lag tăng.

### 48.1. Nhiều vấn đề cùng lúc

- Polymorphic deserialization không an toàn.
- Thiếu max payload/depth.
- Thiếu version compatibility.
- Thiếu poison message policy.
- Retry vô hạn.
- Không có DLQ visibility.
- Source/sink operation idempotency chưa được kiểm tra.

### 48.2. Pipeline an toàn hơn

```text
Broker record
   |
   v
Size/decompression budget
   |
   v
Fixed event envelope decoder
   |
   v
EventType allowlist + schemaVersion
   |
   v
Typed payload validation
   |
   v
Authorization/source trust checks as needed
   |
   v
Idempotent NoSQL mutation
   |
   v
ACK/checkpoint after success
```

### 48.3. Khi event lỗi schema

Đưa vào quarantine/DLQ sau policy retry hợp lý, giữ metadata an toàn để điều tra. Với sự kiện mang nghĩa vụ tài chính, việc skip cần process phục hồi có trách nhiệm; không tự ack rồi quên.

## 49. Case study E: File import bị decompression bomb

Một Java service chấp nhận ZIP 5 MiB chứa NDJSON products, giải nén toàn bộ vào RAM, sau đó map thành `List<Product>`.

### 49.1. Vấn đề

- ZIP 5 MiB có thể mở thành lượng dữ liệu rất lớn.
- Dòng JSON có thể lồng sâu.
- List lớn tạo heap pressure.
- Một record lỗi làm transaction/import có trạng thái không rõ.
- MongoDB batch writer có thể trở thành bottleneck.
- Dữ liệu fields không giới hạn gây index/cache bùng nổ.

### 49.2. Thiết kế đề xuất

1. Kiểm tra authentication, file type và declared import contract.
2. Stream ZIP entries với total uncompressed bytes cap.
3. Reject unsafe entry names, nested archives không cho phép.
4. Stream NDJSON từng dòng; cap per-line bytes.
5. Parse DTO strict, validate fields/sizes/counts.
6. Batch writer theo batch size/bytes hữu hạn.
7. Enforce tenant authorization và quotas.
8. Ghi import operation status/offset/idempotency.
9. Có reject/quarantine policy cho malformed records.
10. Báo completed items, failed items và reconciliation.

### 49.3. Không biến `200 OK` thành “mọi dữ liệu đã nhập”

Nếu import async, trả `202 Accepted` cùng operation ID và trạng thái. Chỉ báo `PERSISTED` khi source writes đã commit theo contract.

## 50. Case study F: Cache trả dữ liệu khác schema

**Bối cảnh:** Redis giữ JSON của Profile v1; ứng dụng Java mới triển khai DTO v2 với `isVerified` và `role`.

### 50.1. Không tin cache làm authority

Một cached payload cũ/malformed có thể thiếu fields. Không dùng Java default `false` hoặc giá trị trống để quyết định quyền khi schema khác.

### 50.2. Schema version/key namespace

```json
{
  "schemaVersion": 2,
  "sourceVersion": 42,
  "payload": {
    "id": "U42",
    "displayName": "Lan"
  }
}
```

Cache key có thể đổi từ `profile:v1:` sang `profile:v2:` để tránh deserialize legacy payload sai.

### 50.3. Khi parse cache lỗi

- Log sanitized reason.
- Evict/invalidate cache entry nếu phù hợp.
- Fallback source theo policy có budget.
- Không biến parse failure thành “user không tồn tại”.
- Không cấp quyền dựa trên cached data chưa xác minh.

### 50.4. Tenant isolation

Cache key phải chứa tenant scope nếu IDs không globally unique; tránh cache poisoning/cross-tenant response.

## 51. Bộ kiểm thử tiêu cực cho serialization/deserialization

Các tests nên chạy với dữ liệu giả, giới hạn tài nguyên và môi trường được phép.

### Test 1 — JSON malformed

Input bị thiếu dấu ngoặc đóng phải trả 400 và không gọi DB.

### Test 2 — Duplicate keys

JSON có hai `role` fields hoặc hai `amount` fields phải bị từ chối theo strict parsing policy.

### Test 3 — Trailing tokens

Hai JSON objects nối liền nhau không được silently đọc object đầu.

### Test 4 — Deep nesting

Object/array lồng sâu hơn `maxNestingDepth` phải bị từ chối trước khi tạo object graph lớn.

### Test 5 — Oversized string

Một field `name` dài hơn cap phải bị reject, không lưu cắt ngắn âm thầm trừ khi contract quy định.

### Test 6 — Many array elements

`tags` có 1.000 entries trong endpoint max 20 phải reject.

### Test 7 — Many object fields

Object có hàng chục nghìn properties ngắn phải bị chặn bởi body/field/token budget.

### Test 8 — Large numeric token

Số với hàng nghìn chữ số phải bị parser/domain limits từ chối.

### Test 9 — Incorrect scalar type

`"enabled": "true"` bị reject nếu schema chỉ nhận boolean, không silently coerce.

### Test 10 — Null vs missing

PATCH phân biệt absent field với explicit null đúng contract.

### Test 11 — Unknown property

Payload có `role` không trong DTO phải bị reject khi strict policy bật.

### Test 12 — Tenant ownership

Client sửa `tenantId` hoặc resourceId của tenant khác không được phép update dữ liệu.

### Test 13 — Mass assignment

Payload chứa `isAdmin`, `balanceMinor`, `verified` không được tác động entity.

### Test 14 — Mongo operator object

Field yêu cầu string nhưng nhận object `$ne`/`$gt` phải bị reject; backend không diễn giải thành operator.

### Test 15 — CQL quote characters

Username chứa quote/backslash phải được bind như data, không làm thay query syntax.

### Test 16 — Cypher/graph labels

Client không được chọn label/relationship type ngoài allowlist.

### Test 17 — Elasticsearch expensive query

Request size/regex/wildcard/aggregation vượt budget bị reject hoặc bị time-bound.

### Test 18 — Redis key collision

Identifiers có separators phải được encode/validate; hai tenant không đọc chung key.

### Test 19 — Regex pathological

Một pattern hoặc input gây backtracking bất thường phải bị chặn bởi grammar/engine/time budget theo test policy.

### Test 20 — GZIP expansion

Compressed body nhỏ nhưng uncompressed vượt cap phải bị dừng.

### Test 21 — ZIP traversal

Entry name `../outside.json` không được giải nén ngoài thư mục cho phép.

### Test 22 — Oversized Base64

Encoded/decoded binary vượt cap phải reject trước khi ghi DB.

### Test 23 — Invalid UTF-8

Malformed byte sequence phải được xử lý đúng parser policy.

### Test 24 — Unicode normalization

Hai identifiers có biểu diễn Unicode khác nhau phải tuân cùng uniqueness/canonicalization policy.

### Test 25 — Integer overflow

`priceMinor * quantity` vượt `long` phải fail có kiểm soát.

### Test 26 — Decimal precision

`price=1.005` không được làm tròn tùy tiện khi API chỉ cho 2 chữ số thập phân.

### Test 27 — Untrusted polymorphic metadata

Payload chứa class/type ID ngoài allowlist bị reject trước khi tạo object.

### Test 28 — Native serialization input

Không có endpoint nào nhận bytes rồi dùng `ObjectInputStream` trên untrusted data ngoài cơ chế legacy đặc biệt đã được cô lập.

### Test 29 — Cache schema mismatch

Cached `schemaVersion=1` không được áp dụng như v2 nếu chưa migrate/validate.

### Test 30 — CDC delete/null image

Consumer nhận `DELETE` với `after=null` mà không bị coi là malformed update.

### Test 31 — Poison broker message

Malformed event không làm topic/partition retry vô hạn không kiểm soát; có DLQ/alert theo policy.

### Test 32 — Concurrent heavy requests

Nhiều requests hợp lệ nhưng tốn CPU phải chịu quota/backpressure, không khiến heap/GC sụp.

### Test 33 — Unknown write outcome

Request timeout sau DB commit phải được nhận diện bằng idempotency/version, không tạo duplicate business action.

### Test 34 — Output data exposure

Public response không chứa password hash, reset token, internal notes hoặc cross-tenant fields.

### Test 35 — Logging injection

Input chứa newline/control chars không tạo fake logs hoặc làm lộ token trong telemetry.

### Test 36 — Serializer update

Upgrade Jackson/driver/DTO không tự bật coercion/default typing hoặc thay behavior duplicate-key parsing ngoài chủ đích.

## 52. Fuzzing và property-based tests

Negative tests với vài payload cố định là cần thiết, nhưng chưa bao phủ hết mọi cấu trúc JSON/BSON.

### 52.1. Những biến có thể fuzz

- String length và UTF-8 edge cases.
- Numeric boundaries.
- Object depth và array length.
- Null/missing/unknown fields.
- Duplicate keys.
- Field names với dots, `$`, control chars.
- Mixed scalar/array/object types.
- Compression ratio.
- Event schema versions.
- Reordered fields.
- Query predicate counts và page sizes.

### 52.2. Properties cần kiểm tra

```text
Invalid input never causes unauthorized database mutation.
Every accepted input satisfies DTO and domain invariants.
Accepted serialized values round-trip without precision loss
  for fields where round-trip is required.
Parser rejects values over configured resource budgets.
Error responses do not include secrets or stack traces.
```

### 52.3. Round-trip tests

Với một DTO được chấp nhận:

```text
DTO -> JSON -> DTO
```

cần giữ các fields được contract bảo đảm, nhưng không đòi giữ nguyên thứ tự JSON object properties hay whitespace. Với decimal/time, định nghĩa chính xác kiểu dữ liệu và precision.

### 52.4. Thử với nhiều implementation

Một API gateway viết bằng ngôn ngữ khác có thể diễn giải duplicate keys/numeric precision không giống Java. Contract tests qua đường request thật giúp phát hiện sự không nhất quán.

### 52.5. Cần an toàn khi fuzz

Giới hạn CPU/memory/time, dùng dữ liệu giả, không fuzz destructive writes trên production. Thu thập crash/OOM/rejected event với metadata an toàn.

## 53. Một threat model ngắn cho API NoSQL

Ví dụ API cho khách hàng tự xem/sửa sản phẩm của shop.

### 53.1. Assets

- Product data theo tenant.
- User permissions.
- Inventory/price.
- Availability/latency SLO.
- Secrets/PII trong DB/cache/events.

### 53.2. Actors

- Customer chưa đăng nhập.
- Shop owner đăng nhập hợp lệ.
- Partner webhook producer.
- Internal background job.
- Attacker có thể gửi raw HTTP payload.

### 53.3. Trust boundaries

```text
Untrusted client
    -> gateway/auth
    -> bounded parser
    -> validated DTO
    -> server authorization
    -> query builder
    -> database
    -> response DTO
```

### 53.4. Threats

- Input resource exhaustion.
- Unsafe polymorphic deserialization.
- Mass assignment.
- Mongo/Cypher/CQL injection.
- Cross-tenant lookup/update.
- Unbounded expensive search.
- Duplicate/replayed events.
- Output leak.
- Poison cache/CDC payload.

### 53.5. Mitigations

DTO allowlists, strict parser/resource limits, bound query values, trusted query structure, tenant constraints at source, rate limits, idempotency, output projection, telemetry và negative testing.

## 54. Quy trình triển khai theo từng bước

### Bước 1 — Liệt kê input surfaces

Ghi tất cả REST endpoints, webhooks, imports, broker consumers, cache reads, CDC adapters.

### Bước 2 — Định nghĩa wire contract

Schema fields, data types, `required`, nullability, max lengths, arrays/maps counts, numeric ranges, version và format.

### Bước 3 — Đặt resource budget

Body bytes, decompressed bytes, JSON depth, token/field limits, max records, max concurrency, per-tenant rate.

### Bước 4 — Dùng typed DTO

Không bind public JSON vào database entities có fields nội bộ; bật strict parsing trên những endpoints phù hợp.

### Bước 5 — Phân tách authorization

Principal-derived tenant/owner/role được kiểm tra trước source mutation; không tin các fields ID/quyền từ body.

### Bước 6 — Dựng query an toàn

Prepared/bound values, typed builders, allowlist field/collection/index names và constrained query templates.

### Bước 7 — Kiểm tra invariant tại source

Dùng unique constraints/conditional writes/transactions trong phạm vi NoSQL engine để chống race; validation trước read không đủ.

### Bước 8 — Giới hạn work

Page size, timeout, index, query budget, queue/batch limits, backpressure.

### Bước 9 — Kiểm soát dữ liệu đi ra

Response DTO, redaction, HTML/output escaping, retention rules.

### Bước 10 — Đo và diễn tập

Negative tests, fuzzing, malformed broker events, cache schema drift, timeouts, multi-tenant abuse, canary và dashboard.

## 55. Những nhầm lẫn thường gặp

**“JSON parse thành công nghĩa payload an toàn.”** Không; nó mới đúng cú pháp.

**“Có `@Valid` thì body 1 GiB không làm hết heap.”** Không; validation sau parse/binding.

**“Giới hạn HTTP `Content-Length` là đủ cho chunked body.”** Không; phải đếm actual bytes.

**“Giới hạn 32 levels ngăn mọi JSON DoS.”** Không; arrays rộng, nhiều fields và CPU vẫn có thể lớn.

**“String length là giới hạn bytes.”** Không; Unicode UTF-8/UTF-16 có độ dài khác.

**“`@Size` tự bảo vệ cả decompressed ZIP.”** Không; cần expanded bytes cap.

**“Có authentication thì được phép sửa `role`.”** Không; field-level authorization.

**“Dùng entity trực tiếp làm request DTO cho tiện.”** Dễ mass assignment và lộ fields.

**“Jackson `Object` default typing luôn an toàn.”** Không khi allowlist/type validator không phù hợp.

**“`instanceof` sau `ObjectInputStream.readObject()` chặn gadgets.”** Quá muộn.

**“Dữ liệu trong cache không cần validate.”** Không; cache có thể stale/poisoned/legacy.

**“Regex ngắn không bao giờ gây ReDoS.”** Không; grammar/engine behavior quan trọng.

**“Query dùng parameter binding thì không thể DoS.”** Không; full scans/limit lớn vẫn tốn tài nguyên.

**“`LIMIT 20` cho phép scan vô hạn an toàn.”** Không; scanned work vẫn có thể lớn.

**“MongoDB filter JSON do user gửi chỉ là data.”** Không; nó có thể chứa operators.

**“CQL ghép strings ổn nếu escape quote thủ công.”** Ưu tiên prepared statements.

**“DynamoDB expressions không cần validate field names.”** Dynamic names vẫn cần allowlist.

**“Redis key với tenantId trong body đã cách ly tenants.”** Không; tenant phải lấy từ principal/authority.

**“Elasticsearch cho user toàn DSL mới linh hoạt.”** Có rủi ro query cost, dữ liệu và privileges.

**“BSON number và JSON number luôn tương đương.”** Không; type và precision khác.

**“Đọc `double` rồi ghi lại tiền chắc chắn không đổi.”** Không; floating point có thể mất chính xác.

**“Null và missing luôn là một.”** Không; ảnh hưởng PATCH và MongoDB query.

**“Ký webhook rồi khỏi giới hạn kích thước.”** Không; chữ ký không hạn chế tài nguyên.

**“Thêm field mới vào response entity không gây hại.”** Có thể leak secrets.

**“Broker message được retry vô hạn tới khi parse được.”** Poison payload có thể làm pipeline kẹt.

**“CDC delete phải có full after image.”** Không; xử lý theo event type và key.

**“Timeout write chắc chắn là write thất bại.”** Không; kết quả có thể unknown.

**“Mọi lỗi validation đều là tấn công.”** Không; có thể client/schema migration lỗi.

**“Chạy fuzzing trên production để test thật.”** Không; có thể gây outages/destructive writes.

## 56. Bài tập thực hành

### Bài tập 1 — Phân biệt serialization/deserialization

Một `Product` Java được chuyển thành JSON gửi HTTP.

**Câu hỏi:** Đây là serialization hay deserialization?

**Gợi ý:** Serialization.

### Bài tập 2 — JSON không đáng tin

Client gửi một JSON hợp lệ chứa `role=ADMIN`.

**Câu hỏi:** Parser strict đã đủ chưa?

**Gợi ý:** Chưa; DTO field allowlist và authorization.

### Bài tập 3 — Deep JSON

Body 10 KiB nhưng lồng 20.000 arrays.

**Câu hỏi:** Giới hạn nào phù hợp?

**Gợi ý:** Parser nesting-depth và request budget.

### Bài tập 4 — Wide JSON

Body có 50.000 fields ngắn, depth=1.

**Câu hỏi:** Depth limit có đủ không?

**Gợi ý:** Không; byte/token/field-count budgets.

### Bài tập 5 — Duplicate JSON keys

Một request có hai `priceMinor` values.

**Câu hỏi:** Vì sao nên reject?

**Gợi ý:** Tránh gateway/parser/backend diễn giải khác nhau.

### Bài tập 6 — Trailing tokens

Một body chứa hai JSON objects nối nhau.

**Câu hỏi:** Cấu hình nào hữu ích?

**Gợi ý:** `FAIL_ON_TRAILING_TOKENS`.

### Bài tập 7 — Unknown fields

Client gửi `isVerified=true` nhưng DTO chỉ có `displayName`.

**Câu hỏi:** Hướng xử lý?

**Gợi ý:** Reject unknown properties hoặc chắc chắn bỏ qua một cách nhất quán; không map vào entity.

### Bài tập 8 — Polymorphic metadata

Payload chứa `@class` tùy ý.

**Câu hỏi:** Vì sao rủi ro?

**Gợi ý:** Caller có thể ảnh hưởng class được dựng nếu polymorphic handling không an toàn.

### Bài tập 9 — Java native serialization

Ứng dụng nhận base64 binary rồi gọi `ObjectInputStream.readObject()`.

**Câu hỏi:** Có nên làm với Internet input không?

**Gợi ý:** Không; chuyển sang typed schema format, native stream là high risk.

### Bài tập 10 — String length

Một emoji dùng nhiều UTF-8 bytes.

**Câu hỏi:** `@Size(max=10)` có chắc cap 10 bytes không?

**Gợi ý:** Không; xem đơn vị UTF-16/code points/UTF-8.

### Bài tập 11 — Big integer

JavaScript client gửi số nguyên lớn hơn chính xác integer range của `Number`.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Mất precision khi serialize/deserialize; dùng schema/string/BigInteger policy.

### Bài tập 12 — Tiền

`price=12.345` được map sang double rồi làm tròn.

**Câu hỏi:** Nên làm gì?

**Gợi ý:** BigDecimal/minor units, scale/rounding validation.

### Bài tập 13 — Overflow

`priceMinor=Long.MAX_VALUE`, `quantity=2`.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Overflow; domain cap và `Math.multiplyExact`.

### Bài tập 14 — Null vs missing

PATCH thiếu `bio` khác PATCH `bio:null`.

**Câu hỏi:** Vì sao?

**Gợi ý:** Omitted = giữ nguyên, explicit null có thể = xóa theo contract.

### Bài tập 15 — MongoDB raw filter

Backend `Document.parse(requestJson)` làm filter trực tiếp.

**Câu hỏi:** Anti-pattern?

**Gợi ý:** NoSQL operator injection; dùng typed builders.

### Bài tập 16 — CQL string concatenation

User input được nối vào WHERE clause.

**Câu hỏi:** Cách sửa?

**Gợi ý:** `PreparedStatement` và bound values.

### Bài tập 17 — Cypher dynamic label

Client tự chọn raw label.

**Câu hỏi:** Vì sao bind `name` chưa đủ?

**Gợi ý:** Label là query structure; allowlist templates.

### Bài tập 18 — DynamoDB attribute names

API nhận arbitrary update field path.

**Câu hỏi:** Cần gì ngoài expression aliases?

**Gợi ý:** Field allowlist, authorization và atomic conditions.

### Bài tập 19 — Redis tenant key

Client có thể đổi `tenantId` trong JSON body.

**Câu hỏi:** Điều gì nguy hiểm?

**Gợi ý:** Cross-tenant access nếu key dùng body tenant.

### Bài tập 20 — Elasticsearch cost

Search DSL nhận `size=1_000_000`.

**Câu hỏi:** Giải pháp?

**Gợi ý:** Page cap, query templates, timeout và quota.

### Bài tập 21 — Regex

Public API nhận arbitrary complex regex.

**Câu hỏi:** Hai rủi ro?

**Gợi ý:** Query semantics và CPU/ReDoS.

### Bài tập 22 — GZIP bomb

GZIP 5 KiB giải nén 500 MiB.

**Câu hỏi:** Chỉ check compressed body cap có đủ không?

**Gợi ý:** Không; expanded-size và CPU budget.

### Bài tập 23 — ZIP traversal

File entry tên `../../secret.txt`.

**Câu hỏi:** Giải nén tùy ý có an toàn không?

**Gợi ý:** Không; reject paths nguy hiểm và sandbox directory.

### Bài tập 24 — Base64

JSON string 2 MiB encode ra binary lớn.

**Câu hỏi:** Cần caps nào?

**Gợi ý:** Encoded và decoded size.

### Bài tập 25 — Array import

NDJSON import 1 triệu records vào `List` trước khi ghi DB.

**Câu hỏi:** Nên thay bằng gì?

**Gợi ý:** Streaming/batching/backpressure.

### Bài tập 26 — Mass assignment

Spring Controller dùng `@RequestBody UserEntity`.

**Câu hỏi:** Rủi ro với `role`, `balance`?

**Gợi ý:** Overposting và response leakage.

### Bài tập 27 — Concurrency

Hai clients đều vượt DTO validation nhưng cùng reserve một item cuối.

**Câu hỏi:** Nên bảo vệ ở đâu?

**Gợi ý:** Atomic conditional update/transaction tại NoSQL authority.

### Bài tập 28 — Cache schema drift

Redis cache giữ payload v1, Java DTO v2.

**Câu hỏi:** Cách xử lý?

**Gợi ý:** `schemaVersion`, migration/invalidation và safe fallback.

### Bài tập 29 — Poison event

Kafka consumer retry mãi event không parse được.

**Câu hỏi:** Cần bổ sung?

**Gợi ý:** Retry limits, quarantine/DLQ, alert, schema compatibility.

### Bài tập 30 — API error

Parser reject unsafe input; server trả full stack trace.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Lộ thông tin nội bộ; dùng structured safe error.

### Bài tập 31 — Signed webhook

Webhook có chữ ký hợp lệ nhưng body 100 MiB.

**Câu hỏi:** Chữ ký đã đủ để chấp nhận chưa?

**Gợi ý:** Không; size/CPU/semantic/resource limits.

### Bài tập 32 — Output projection

Public API serialize thẳng `UserDocument` có passwordHash.

**Câu hỏi:** Cần gì?

**Gợi ý:** Response DTO allowlist.

### Bài tập 33 — Query without index

Query bind an toàn nhưng scan 50 triệu documents.

**Câu hỏi:** Injection đã được giải quyết hết availability risk chưa?

**Gợi ý:** Không; query-plan/work budget.

### Bài tập 34 — Cache poisoning

Cached JSON có `role=ADMIN`, source đã revoke.

**Câu hỏi:** Có nên dựa cached role để authorize không?

**Gợi ý:** Không; authority/revocation policy.

### Bài tập 35 — Fuzzing

Muốn test parser trước production.

**Câu hỏi:** Những dimensions nào nên fuzz?

**Gợi ý:** Types, depth, lengths, duplicate keys, unicode, numeric boundaries, nested arrays, schema versions.

### Bài tập 36 — Thiết kế API an toàn

Một Java/Spring Boot service dùng MongoDB cho Users, DynamoDB cho Orders, Redis cache và Kafka CDC.

**Yêu cầu:** Thiết kế DTO boundaries, Jackson limits, request/body caps, tenant/field authorization, query builders, idempotency, cache/event schema validation, metrics, failure tests.

**Gợi ý:** Chặn sớm ở gateway/parser, dùng DTO cho input/output, server-derived tenant, atomic source writes, bounded queries, DLQ/replay policy và negative tests.

## 57. Checklist trước khi phát hành

- [ ] Đã xác định tất cả ranh giới untrusted bytes và các serializers/deserializers.
- [ ] Có wire schemas/DTOs rõ field types, nullability và versions.
- [ ] Không dùng native `ObjectInputStream` cho untrusted client data.
- [ ] Không bật unrestricted default typing/polymorphic class selection.
- [ ] Có allowlist subtypes nếu cần polymorphism.
- [ ] Có giới hạn HTTP body bytes từ gateway/server.
- [ ] Đếm actual received bytes, không chỉ tin `Content-Length`.
- [ ] Có decompressed-size và CPU/concurrency budget khi nhận compressed payload.
- [ ] Có parser nesting/string/number constraints.
- [ ] Reject duplicate keys và trailing tokens theo API policy.
- [ ] Có xử lý malformed UTF-8 và Unicode normalization.
- [ ] Giới hạn số elements của arrays/maps và tổng fields/tokens.
- [ ] Không để DTO validation là lớp size limit đầu tiên.
- [ ] Có range/scale/precision policy cho integers, decimals và money.
- [ ] Có null/missing semantics rõ cho PATCH.
- [ ] Có max page size, query predicates, `IN` values, traversal depth.
- [ ] Có query timeouts và database resource budget.
- [ ] Dùng prepared statements/typed filter builders và bound values.
- [ ] Không parse user JSON thành raw MongoDB filter.
- [ ] Field/collection/index/sort/label identifiers được allowlist.
- [ ] Không cho user điều khiển arbitrary regex/script/aggregation DSL.
- [ ] Tenant/owner/role được lấy từ server-side identity và kiểm tra tại source.
- [ ] Không bind request trực tiếp vào database entity chứa fields nội bộ.
- [ ] Atomic business invariants được bảo vệ tại source.
- [ ] Có operation IDs/idempotency và unknown write outcome handling.
- [ ] Có cache key namespace, schemaVersion và safe fallback.
- [ ] Broker/CDC consumers có payload caps, schema version và poison message policy.
- [ ] Có quota/rate limits, backpressure và bulkhead cho expensive endpoints.
- [ ] ZIP/file imports giới hạn expanded bytes, entry count, paths và total records.
- [ ] Responses dùng DTO allowlist; không lộ secrets/PII.
- [ ] Không log full untrusted payload, stack traces hoặc tokens vào user response.
- [ ] Có metrics parser rejects, 413/429, query cost, CPU/GC, poison events.
- [ ] Có negative tests, integration tests và bounded fuzzing.
- [ ] Đã kiểm tra khác biệt parser giữa gateway/client/service nếu liên quan.
- [ ] Có schema migration/compatibility plan và release rollback.
- [ ] Đã lập tài liệu các giới hạn theo endpoint và thông báo cho clients.
- [ ] Tất cả lỗi parsing/validation được xử lý theo policy, không gây OOM/stall.

## 58. Tổng kết

**Serialization** đưa object ra wire/storage format; **deserialization** đưa bytes về object. Cả hai là ranh giới bảo mật quan trọng trong kiến trúc Java với NoSQL, đặc biệt khi API, cache và event stream có thể chứa dữ liệu từ người dùng hoặc nhiều services khác nhau.

Một thiết kế an toàn cần phối hợp các lớp sau:

- **Chặn chi phí sớm:** byte cap, decompression budget, parser depth/string/number limits, array/record counts và concurrency/rate limits.
- **Giữ type và schema rõ:** typed DTO/record, strict parsing, duplicate key rejection, controlled coercion, semantic validation và schema evolution.
- **Không tạo object tùy ý:** tránh native deserialization của untrusted streams và unrestricted polymorphic typing; dùng allowlist khi cần.
- **Không trao quyền query structure cho user:** parameter binding, typed MongoDB filters, prepared CQL, Cypher parameters, DynamoDB expression aliases và query template allowlists.
- **Bảo vệ quyền/invariants tại authority:** tenant/role/field authorization, atomic conditional writes, idempotency và data correctness.
- **Kiểm soát dữ liệu đi ra và dữ liệu nội bộ:** response DTO, output encoding, cache/broker/CDC schema validation, PII retention và logging có giới hạn.
- **Kiểm chứng bằng vận hành thực tế:** negative tests, fuzzing, metrics 4xx/413/429, query cost, heap/GC, poison events và runbook.

**Nguyên tắc cốt lõi:** *Đừng hỏi chỉ “JSON này parse được không?”. Hãy hỏi “kích thước và cấu trúc của dữ liệu này có được giới hạn trước khi cấp phát, nó có được biến thành đúng kiểu và đúng ý nghĩa nghiệp vụ, caller có quyền điều khiển những field/query nào, và một request hợp lệ có thể tiêu tốn tối đa bao nhiêu tài nguyên NoSQL?”.* Chỉ khi có câu trả lời rõ cho cả bốn điểm, serialization/deserialization mới là một phần của hệ thống an toàn thay vì điểm yếu nằm ngay ở đầu vào.


