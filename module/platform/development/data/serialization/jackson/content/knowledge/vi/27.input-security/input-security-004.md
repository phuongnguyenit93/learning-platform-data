# Cấu hình StreamReadConstraints và StreamWriteConstraints theo phiên bản

JSON có thể chứa chuỗi rất dài, số có hàng nghìn chữ số hoặc object lồng nhau nhiều tầng. Những payload này đôi khi hợp lệ về cú pháp nhưng vẫn tiêu tốn nhiều bộ nhớ, CPU hoặc stack của ứng dụng. Khi đọc dữ liệu từ client, message broker hay file bên ngoài, chỉ kiểm tra cú pháp JSON là chưa đủ; parser cần có giới hạn cho những cấu trúc có thể làm tài nguyên tăng bất thường.

Jackson Core cung cấp hai nhóm cấu hình liên quan:

- **`StreamReadConstraints`** giới hạn một số đặc điểm của JSON khi parser đọc input.
- **`StreamWriteConstraints`** giới hạn một số đặc điểm của JSON khi generator ghi output.

Hai nhóm có thời điểm xuất hiện khác nhau trong dòng Jackson 2.x. Vì vậy, code cấu hình phải phù hợp với phiên bản `jackson-core` thực tế của ứng dụng. Bài học này trình bày mốc phiên bản, cách gắn constraints vào `JsonFactory`, cách chia sẻ factory với `ObjectMapper`, cách chọn ngưỡng và cách kiểm thử giới hạn đọc/ghi.

## 1. Vì sao cần giới hạn khi đọc và ghi JSON?

Một JSON document nhỏ có thể chứa một cấu trúc rất sâu:

```json
{
  "node": {
    "node": {
      "node": {
        "node": {
          "value": "end"
        }
      }
    }
  }
}
```

Một payload khác có thể chứa một string rất lớn hoặc numeric literal dài bất thường:

```json
{
  "description": "một chuỗi có thể dài hàng triệu ký tự...",
  "largeNumber": 123456789012345678901234567890
}
```

Các trường hợp cần quan tâm:

- Object/array lồng quá sâu có thể làm tăng chi phí parser và nguy cơ stack exhaustion ở những tầng xử lý khác.
- String token quá dài có thể tạo allocation lớn khi materialize thành `String`.
- Tên property rất dài có thể làm tăng bộ nhớ và chi phí xử lý key.
- Numeric literal quá dài có thể tốn CPU khi parse thành số.
- Khi ghi output, một object graph quá sâu có thể làm generator phải duy trì trạng thái lồng nhau lớn.
- Dữ liệu hợp lệ về cú pháp vẫn có thể vượt giới hạn tài nguyên mà ứng dụng chấp nhận.

`StreamReadConstraints` và `StreamWriteConstraints` giúp đặt giới hạn ở tầng Jackson Core, gần nơi token được đọc hoặc cấu trúc được ghi. Chúng bổ sung cho giới hạn request, file, message và timeout ở các tầng khác.

## 2. Phân biệt read constraints và write constraints

Hai nhóm cấu hình có trách nhiệm khác nhau:

| Nhóm | Áp dụng khi | Ví dụ giới hạn |
| --- | --- | --- |
| `StreamReadConstraints` | Đọc JSON từ parser | Độ sâu lồng nhau, độ dài string, độ dài số; một số phiên bản có thêm giới hạn tên property |
| `StreamWriteConstraints` | Ghi JSON bằng generator | Độ sâu cấu trúc được ghi |

Luồng đọc:

```text
Input bytes / Reader
       │
       ▼
JsonFactory
       │
       ▼
JsonParser + StreamReadConstraints
       │
       ▼
JsonToken
       │
       ▼
ObjectMapper / ObjectReader
       │
       ▼
Java object
```

Luồng ghi:

```text
Java object
       │
       ▼
ObjectMapper / ObjectWriter
       │
       ▼
JsonFactory
       │
       ▼
JsonGenerator + StreamWriteConstraints
       │
       ▼
Output bytes / Writer
```

Cấu hình đọc không tự động giới hạn ghi và ngược lại. Nếu ứng dụng vừa nhận vừa phát JSON, hãy xác định rõ cả hai chính sách.

## 3. Mốc phiên bản trong Jackson 2.x và 3.x

Điểm cần nhớ là không phải mọi minor version của Jackson đều có cùng API.

| Dòng phiên bản | Read constraints | Write constraints | Lưu ý |
| --- | --- | --- | --- |
| Jackson 2.14 trở xuống | Chưa có API `StreamReadConstraints` như các bản mới | Chưa có `StreamWriteConstraints` | Không thể biên dịch ví dụ dùng hai class này; cần nâng cấp hoặc bổ sung kiểm soát ở tầng khác |
| Jackson 2.15.x | Có `StreamReadConstraints` | Chưa có `StreamWriteConstraints` | Có thể cấu hình parser đọc bằng `JsonFactory` |
| Jackson 2.16.x trở lên trong dòng 2.x | Có | Có | Có thể cấu hình cả parser và generator |
| Jackson 3.x | Có các API tương ứng trong dòng mới | Có các API tương ứng trong dòng mới | Namespace package và hệ sinh thái artifact thay đổi; dùng tài liệu đúng major version |

Các mốc này nói về Jackson Core. `jackson-databind` phụ thuộc vào `jackson-core`, nên cần xem phiên bản runtime của Core chứ không chỉ nhìn phiên bản được khai báo cho Databind.

Các minor release có thể bổ sung thêm loại giới hạn hoặc thay đổi API builder. Ví dụ, giới hạn tên property không có mặt trong mọi bản cũ. Nếu cần dùng một builder method ngoài các giới hạn cơ bản trong ví dụ, hãy kiểm tra Javadoc của đúng phiên bản đang dùng và để compiler xác nhận API tồn tại.

**Không trộn `jackson-core`, `jackson-databind`, `jackson-annotations` hoặc module datatype từ các phiên bản không tương thích.** Dùng Jackson BOM hoặc dependency management của dự án để giữ các artifact cùng một release train.

## 4. Cấu hình StreamReadConstraints trên Jackson 2.15+

`StreamReadConstraints` được tạo bằng builder rồi gắn vào `JsonFactory`. Ví dụ dưới đây dùng các giới hạn đọc cơ bản có trong Jackson 2.15:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

StreamReadConstraints readConstraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxNumberLength(128)
        .maxStringLength(1_000_000)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(readConstraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Ý nghĩa:

- `maxNestingDepth(100)`: giới hạn độ sâu lồng nhau của object và array.
- `maxNumberLength(128)`: giới hạn độ dài token số.
- `maxStringLength(1_000_000)`: giới hạn độ dài string value được parser đọc.

Các số trong ví dụ chỉ minh họa. Hệ thống thực tế cần chọn giới hạn theo payload hợp lệ lớn nhất, cách dùng dữ liệu và ngân sách tài nguyên.

### 4.1. Gắn constraints trước khi tạo mapper

`ObjectMapper` sử dụng `JsonFactory` được truyền vào constructor. Vì vậy, cấu hình factory trước rồi mới tạo mapper:

```java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(readConstraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Đừng tạo mapper với factory mặc định rồi nghĩ rằng gọi một method trên `ObjectReader` sẽ thay đổi các giới hạn của parser. Constraints thuộc tầng Core factory/parser, không phải một feature thông thường chỉ bật riêng cho một property Java.

Nếu mapper đã được chia sẻ cho nhiều request, hãy hoàn tất cấu hình factory trước khi đưa mapper vào sử dụng đồng thời.

### 4.2. Dùng cùng factory cho parser trực tiếp

Nếu ứng dụng tạo parser trực tiếp thay vì gọi `ObjectMapper.readValue`, factory đã cấu hình vẫn áp dụng:

```java
try (JsonParser parser = factory.createParser(inputStream)) {
    while (parser.nextToken() != null) {
        // Consume tokens
    }
}
```

Tương tự, `ObjectMapper` được tạo từ factory đó sẽ dùng cùng chính sách. Đây là lý do nên đặt constraints ở factory dùng chung cho một giao thức, thay vì cấu hình rời rạc ở từng chỗ gọi.

## 5. Giới hạn tên property khi phiên bản hỗ trợ

Tên property cũng là một chuỗi đầu vào. Một số minor release của Jackson 2.x bổ sung cấu hình giới hạn độ dài tên property, thường được biểu diễn bằng builder method như `maxNameLength(...)`.

Khi API của phiên bản đang dùng có hỗ trợ, có thể cấu hình theo dạng:

```java
StreamReadConstraints readConstraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxNumberLength(128)
        .maxStringLength(1_000_000)
        .maxNameLength(256)
        .build();
```

Không copy dòng `maxNameLength(...)` vào project đang dùng một minor version chưa cung cấp method này. Hãy kiểm tra Javadoc hoặc để IDE/compiler xác nhận method có sẵn.

Giới hạn tên property đặc biệt hữu ích khi parser nhận object có nhiều key do client hoặc đối tác kiểm soát. Nó không giới hạn số lượng property trong object; giới hạn số lượng field cần được kiểm soát ở tầng schema, streaming/application logic hoặc giới hạn payload phù hợp.

## 6. Cấu hình StreamWriteConstraints trong Jackson 2.16+

`StreamWriteConstraints` được bổ sung trong dòng Jackson 2.x từ 2.16. Ví dụ:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamWriteConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

StreamWriteConstraints writeConstraints =
    StreamWriteConstraints.builder()
        .maxNestingDepth(100)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamWriteConstraints(writeConstraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Giới hạn quan trọng của nhóm write constraints là độ sâu lồng nhau khi generator ghi object/array. Nó giúp ngăn output có cấu trúc sâu vượt ngưỡng được phép.

Ví dụ object graph lồng nhau nhiều tầng có thể vượt giới hạn khi serialize:

```java
Map<String, Object> root = new LinkedHashMap<>();
Map<String, Object> child = new LinkedHashMap<>();

root.put("child", child);
child.put("child", Map.of("child", Map.of("value", "end")));

String json = mapper.writeValueAsString(root);
```

Nếu cấu trúc vượt `maxNestingDepth`, generator báo lỗi constraint thay vì tiếp tục ghi sâu hơn.

`StreamWriteConstraints` không phải giới hạn tổng số byte output, số property, độ dài mọi string hoặc kích thước file. Các giới hạn đó cần được thực hiện ở tầng serialization/application hoặc output destination.

## 7. Cấu hình đồng thời read và write

Với Jackson 2.16+ có thể gắn cả hai nhóm vào cùng một `JsonFactory`:

```java
StreamReadConstraints readConstraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxNumberLength(128)
        .maxStringLength(1_000_000)
        .build();

StreamWriteConstraints writeConstraints =
    StreamWriteConstraints.builder()
        .maxNestingDepth(100)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(readConstraints)
    .streamWriteConstraints(writeConstraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Tất cả parser/generator được tạo từ factory này sẽ dùng chính sách tương ứng.

Có thể đăng ký thêm module Databind sau khi tạo mapper:

```java
mapper.registerModule(new JavaTimeModule());
```

Nếu dùng `JsonMapper.builder(...)`, `ObjectMapper` constructor hoặc một factory được framework inject, nguyên tắc vẫn như nhau: cấu hình constraints trên đúng `JsonFactory` mà mapper thực sự sử dụng.

## 8. Theo phiên bản: tránh gọi API không tồn tại

Một lỗi build thường gặp là copy ví dụ từ tài liệu Jackson mới hơn vào project đang dùng Core cũ.

Ví dụ project dùng 2.15.x nhưng code gọi:

```java
StreamWriteConstraints.builder()
    .maxNestingDepth(100)
    .build();
```

sẽ không biên dịch vì dòng 2.15 chưa cung cấp `StreamWriteConstraints`.

Một tình huống khác là project khai báo `jackson-databind` mới nhưng dependency resolution lại đưa `jackson-core` cũ vào runtime. Code có thể compile theo classpath IDE nhưng chạy với class khác phiên bản, gây `NoSuchMethodError`, `NoClassDefFoundError` hoặc hành vi không nhất quán.

Quy trình xử lý:

1. Xác định phiên bản `jackson-core` thực tế.
2. Xác định phiên bản `jackson-databind` và `jackson-annotations`.
3. Kiểm tra dependency tree để tìm dependency kéo phiên bản cũ.
4. Dùng BOM hoặc dependency constraints để đồng bộ.
5. Chỉ gọi builder method có trong minor version đã chọn.
6. Chạy test trên runtime classpath thực tế, không chỉ compile trong IDE.

### 8.1. Maven: dùng Jackson BOM

Ví dụ khai báo BOM cho dòng Jackson 2.x:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Thay `2.x.y` bằng một release Jackson 2.x đã được dự án chọn và kiểm thử. BOM quản lý phiên bản cho các artifact Jackson tương ứng; không khai báo version riêng lẻ không đồng bộ cho Core và Databind.

Kiểm tra dependency tree:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
```

### 8.2. Gradle: dùng platform

Ví dụ:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.x.y"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
```

Nếu project dùng Groovy DSL, cú pháp tương ứng:

```groovy
dependencies {
    implementation platform("com.fasterxml.jackson:jackson-bom:2.x.y")
    implementation "com.fasterxml.jackson.core:jackson-databind"
}
```

Kiểm tra dependency được chọn:

```bash
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
```

Nếu một framework quản lý Jackson BOM, ưu tiên tuân theo version set mà framework hỗ trợ. Không nâng riêng `jackson-core` mà không xác nhận tương thích với Databind và các module liên quan.

## 9. Global default constraints và per-factory constraints

Jackson 2.x có API cho phép thay đổi default constraints dùng khi tạo factory mới. Tên API có thể gồm:

- `StreamReadConstraints.overrideDefaultStreamReadConstraints(...)`
- `StreamWriteConstraints.overrideDefaultStreamWriteConstraints(...)`

Các API này chỉ có ở dòng phiên bản tương ứng với từng nhóm constraints. Cần kiểm tra phiên bản Core trước khi sử dụng.

Ví dụ minh họa cho một runtime có cả hai API:

```java
StreamReadConstraints.overrideDefaultStreamReadConstraints(
    readConstraints
);

StreamWriteConstraints.overrideDefaultStreamWriteConstraints(
    writeConstraints
);
```

Cấu hình global có phạm vi ảnh hưởng rộng. Nó có thể tác động đến các `JsonFactory` được tạo ở nơi khác trong cùng process, kể cả mapper của thư viện hoặc framework. Nó cũng khiến kết quả phụ thuộc thứ tự khởi tạo nếu các factory đã được tạo trước khi đổi default.

Vì vậy, ưu tiên **per-factory configuration**:

- API công khai có factory riêng với giới hạn phù hợp.
- Import file lớn có factory riêng theo định dạng và ngân sách khác.
- Message consumer có factory riêng nếu hợp đồng message khác HTTP.
- Test tạo factory riêng để xác nhận giới hạn mà không ảnh hưởng mapper khác.

Chỉ dùng global default khi toàn bộ process thực sự cần cùng chính sách và cấu hình được thiết lập sớm tại bootstrap.

## 10. Chọn ngưỡng như thế nào?

Không có một con số phù hợp cho mọi ứng dụng. Ngưỡng nên dựa trên dữ liệu hợp lệ và tài nguyên thực tế.

| Constraint | Câu hỏi khi chọn ngưỡng |
| --- | --- |
| `maxNestingDepth` | Schema hợp lệ sâu tối đa bao nhiêu tầng? Có object/array lồng nhau theo cây không? |
| `maxStringLength` | String lớn nhất hợp lệ là bao nhiêu? Có trường mô tả, nội dung hoặc payload encoded không? |
| `maxNumberLength` | Số thập phân hoặc số nguyên lớn nhất cần hỗ trợ dài bao nhiêu ký tự? |
| `maxNameLength` nếu có | Tên property dài nhất trong schema là bao nhiêu? |
| `StreamWriteConstraints.maxNestingDepth` | Object graph sâu tối đa bao nhiêu tầng khi ghi? |

Một số nguyên tắc:

- Bắt đầu từ schema và payload thực tế, không chọn ngưỡng quá nhỏ chỉ để “an toàn”.
- Chừa biên hợp lý cho dữ liệu hợp lệ tăng trưởng.
- Tránh đặt giới hạn cực lớn mà không có lý do.
- Đặt cùng một chính sách ở các service cùng giao thức để giảm lỗi tương thích.
- Tách giới hạn input công khai khỏi giới hạn cho import nội bộ nếu hai luồng có nhu cầu khác nhau.
- Theo dõi constraint exception để biết giới hạn có đang chặn dữ liệu hợp lệ hay không; không ghi nguyên payload nhạy cảm vào log.

Ví dụ một API nhận tên, mô tả và metadata nhỏ có thể dùng giới hạn string thấp hơn một dịch vụ nhập tài liệu. Một endpoint upload tài liệu không nên nới giới hạn JSON string lên hàng trăm megabyte chỉ vì file lớn; file nên được truyền qua cơ chế upload phù hợp.

## 11. Độ sâu lồng nhau không phải số lượng phần tử

`maxNestingDepth` kiểm soát độ sâu của cấu trúc object/array, không phải tổng số node hoặc tổng số property.

Ví dụ A có độ sâu nhỏ nhưng rất nhiều phần tử:

```json
{
  "items": [
    1, 2, 3, 4, 5
  ]
}
```

Ví dụ B có ít phần tử nhưng lồng nhiều tầng:

```json
{
  "a": {
    "b": {
      "c": {
        "d": {
          "value": 1
        }
      }
    }
  }
}
```

Hai payload tạo ra loại áp lực khác nhau. Giới hạn nesting không thay thế giới hạn số phần tử. Nếu API cần giới hạn số item, hãy kiểm tra collection size trong schema/application logic hoặc xử lý streaming và dừng khi vượt ngưỡng.

Tương tự, `maxStringLength` không giới hạn tổng độ dài của tất cả string trong document. Một object có hàng nghìn string nhỏ vẫn có thể tạo tổng bộ nhớ lớn. Cần giới hạn tổng body size, số property, số array element hoặc kích thước message ở tầng thích hợp.

## 12. StreamReadConstraints không thay thế giới hạn HTTP body

`StreamReadConstraints` kiểm soát các đặc điểm của token/cấu trúc mà Jackson Core đọc. Nó không phải một bộ giới hạn tổng byte của HTTP request.

Một ứng dụng web nên có nhiều lớp giới hạn:

```text
HTTP / reverse proxy
  ├── giới hạn request body bytes
  ├── giới hạn thời gian đọc
  └── giới hạn kích thước sau giải nén nếu có
          │
          ▼
Jackson JsonFactory
  ├── maxNestingDepth
  ├── maxStringLength
  ├── maxNumberLength
  └── maxNameLength nếu phiên bản hỗ trợ
          │
          ▼
Application validation
  ├── số phần tử
  ├── số field
  ├── quy tắc domain
  └── authorization
```

Ví dụ:

- Một request có thể chứa hàng triệu property nhỏ nhưng không vượt string length.
- Một JSON string có thể vừa giới hạn token nhưng tổng body vẫn rất lớn do có nhiều field.
- Nếu input được giải nén trước khi parser đọc, cần xem xét kích thước sau giải nén.
- Parser constraints không thay thế timeout mạng, giới hạn concurrent request hoặc ngân sách bộ nhớ.

Hãy cấu hình giới hạn ở từng tầng theo đúng tài nguyên mà tầng đó kiểm soát.

## 13. StreamWriteConstraints không thay thế giới hạn output size

Write constraints chủ yếu bảo vệ generator khỏi cấu trúc lồng quá sâu. Chúng không tự ngăn một collection khổng lồ tạo ra JSON có hàng triệu phần tử.

Nếu output có thể rất lớn:

- Phân trang dữ liệu trước khi serialize.
- Dùng streaming thay vì materialize toàn bộ kết quả thành một object graph lớn.
- Giới hạn số phần tử theo hợp đồng.
- Ghi vào output có giới hạn dung lượng hoặc kiểm soát quota.
- Dùng file tạm rồi publish/rename khi ghi hoàn tất nếu cần output nguyên tử.

Khi generator ném exception giữa quá trình ghi vào `OutputStream`, file hoặc network stream có thể đã chứa một phần JSON. Không giả định output được rollback tự động.

Với file export quan trọng, có thể ghi vào file tạm cùng filesystem, đóng và xác nhận thành công rồi mới đổi tên sang file chính. Nếu serialize thất bại, xóa file tạm theo chính sách của ứng dụng.

## 14. Bắt và xử lý lỗi constraint

Khi giới hạn bị vượt, Jackson báo lỗi liên quan tới stream constraints. Trong Jackson 2.x, có thể gặp `StreamConstraintsException` thuộc package `com.fasterxml.jackson.core.exc`.

Ví dụ:

```java
import com.fasterxml.jackson.core.exc.StreamConstraintsException;

try {
    JsonNode root = mapper.readTree(json);
} catch (StreamConstraintsException ex) {
    // Convert to a controlled input/output error.
}
```

Không nên bắt mọi `JsonProcessingException` rồi báo cùng một thông điệp “JSON sai”. Có thể phân biệt:

- JSON sai cú pháp.
- Kiểu dữ liệu không đúng.
- Vượt giới hạn stream.
- Lỗi I/O khi đọc nguồn.
- Lỗi mapping do constructor hoặc custom deserializer.

Ở HTTP API, có thể ánh xạ input constraint violation thành lỗi request phù hợp, thường là phản hồi 4xx theo quy ước của ứng dụng. Với lỗi khi ghi response, request có thể đã được chấp nhận và output stream có thể đã bắt đầu; xử lý ở tầng server/logging phù hợp thay vì cố ghi một JSON lỗi thứ hai vào stream đã hỏng.

Không đưa stack trace hoặc toàn bộ payload vào response cho client. Log loại constraint, ngưỡng cấu hình, endpoint/message type và correlation id; tránh log nội dung nhạy cảm.

## 15. Kiểm thử read constraints

Nên kiểm tra ít nhất:

- JSON có độ sâu trong giới hạn.
- JSON vượt độ sâu.
- String value trong giới hạn và vượt giới hạn.
- Numeric token trong giới hạn và vượt giới hạn.
- Tên property quá dài nếu phiên bản hỗ trợ `maxNameLength`.
- Factory/mapper thực tế đang dùng constraints mong muốn.

Ví dụ test string:

```java
@Test
void rejectsStringLongerThanReadLimit() {
    StreamReadConstraints constraints =
        StreamReadConstraints.builder()
            .maxStringLength(8)
            .build();

    JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();

    ObjectMapper mapper = new ObjectMapper(factory);

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readTree("""
            {"value": "123456789"}
            """)
    );
}
```

Ví dụ test numeric length:

```java
@Test
void rejectsNumberLongerThanReadLimit() {
    StreamReadConstraints constraints =
        StreamReadConstraints.builder()
            .maxNumberLength(5)
            .build();

    ObjectMapper mapper = new ObjectMapper(
        JsonFactory.builder()
            .streamReadConstraints(constraints)
            .build()
    );

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.readTree("""
            {"value": 123456789}
            """)
    );
}
```

### 15.1. Test độ sâu

Tạo JSON lồng nhau sâu hơn giới hạn rồi xác nhận parser từ chối. Khi kiểm thử ranh giới chính xác, hãy xác nhận cách Jackson phiên bản đang dùng đếm root/container depth; đừng viết test chỉ dựa trên phỏng đoán off-by-one.

Có thể tạo test helper sinh chuỗi JSON lồng nhau bằng số tầng cố định, nhưng nên giữ input test đủ nhỏ và dễ đọc.

## 16. Kiểm thử write constraints

Test output có cấu trúc lồng sâu hơn giới hạn:

```java
@Test
void rejectsObjectGraphDeeperThanWriteLimit() {
    StreamWriteConstraints constraints =
        StreamWriteConstraints.builder()
            .maxNestingDepth(2)
            .build();

    ObjectMapper mapper = new ObjectMapper(
        JsonFactory.builder()
            .streamWriteConstraints(constraints)
            .build()
    );

    Map<String, Object> root = Map.of(
        "a",
        Map.of(
            "b",
            Map.of("c", "value")
        )
    );

    assertThrows(
        StreamConstraintsException.class,
        () -> mapper.writeValueAsString(root)
    );
}
```

Test này chỉ dùng được trong phiên bản Core có `StreamWriteConstraints`.

Cũng nên có test cấu trúc trong giới hạn để tránh cấu hình quá chặt làm hỏng dữ liệu hợp lệ. Không chỉ kiểm tra trường hợp bị từ chối.

### 16.1. Output stream có thể đã ghi một phần

Nếu dùng `StringWriter`, `ByteArrayOutputStream` hoặc file, sau exception có thể đã có một phần output. Hãy kiểm tra hành vi mà ứng dụng cần xử lý, đặc biệt với export file hoặc response streaming.

Đừng yêu cầu code production phải ghi một JSON lỗi khác vào cùng output stream sau khi generator đã thất bại. Dùng file tạm, buffer có giới hạn hoặc response error handling trước khi bắt đầu gửi body nếu cần đảm bảo output hoàn chỉnh.

## 17. Chọn factory theo từng luồng dữ liệu

Một ứng dụng có thể cần nhiều chính sách:

```java
JsonFactory publicApiFactory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(80)
            .maxNumberLength(128)
            .maxStringLength(256_000)
            .build()
    )
    .build();

JsonFactory importFactory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(150)
            .maxNumberLength(256)
            .maxStringLength(2_000_000)
            .build()
    )
    .build();
```

Mẫu này minh họa việc tách chính sách. Giá trị import không mặc nhiên phải lớn hơn; chỉ đặt khác nhau khi có yêu cầu và ngân sách tài nguyên được xác nhận.

Tạo mapper tương ứng:

```java
ObjectMapper publicApiMapper = new ObjectMapper(publicApiFactory);
ObjectMapper importMapper = new ObjectMapper(importFactory);
```

Không dùng mapper import có giới hạn rất rộng để parse HTTP request công khai chỉ vì nó tiện dùng chung. Hãy gắn mỗi mapper/factory với một trust boundary và một hợp đồng dữ liệu rõ ràng.

## 18. Dùng trực tiếp JsonFactory, ObjectMapper và ObjectReader

Các API nằm ở những tầng khác nhau:

| API | Vai trò | Có thay đổi stream constraints không? |
| --- | --- | --- |
| `StreamReadConstraints.builder()` | Tạo chính sách đọc | Có, tạo cấu hình |
| `StreamWriteConstraints.builder()` | Tạo chính sách ghi | Có, tạo cấu hình |
| `JsonFactory.builder()` | Gắn chính sách vào factory | Có |
| `ObjectMapper(JsonFactory)` | Tạo mapper dùng factory đó | Sử dụng chính sách factory |
| `ObjectReader` | Cấu hình cách bind/read một kiểu | Không thay thế constraints của factory |
| `ObjectWriter` | Cấu hình cách serialize/write | Không thay thế constraints của factory |
| `JsonParser` | Đọc token | Dùng read constraints của factory tạo parser |
| `JsonGenerator` | Ghi token | Dùng write constraints của factory tạo generator |

Điều này giúp tránh nhầm rằng có thể nới giới hạn cho riêng một lần gọi bằng `ObjectReader.with(...)` hoặc `ObjectWriter.with(...)` như với một số `DeserializationFeature`/`SerializationFeature`. Stream constraints thuộc factory.

Nếu cần hai chính sách khác nhau cho hai luồng, tạo hai factory/mapper đã cấu hình riêng, thay vì thay đổi global default theo từng request.

## 19. Những giới hạn và lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `StreamReadConstraints` không tìm thấy | `jackson-core` quá cũ | Dùng Core 2.15+ hoặc nâng đồng bộ Jackson |
| `StreamWriteConstraints` không tìm thấy | Đang dùng Core trước 2.16 | Dùng Core 2.16+ hoặc kiểm soát cấu trúc trước khi ghi |
| Builder method không tồn tại | Method thuộc minor version mới hơn | Đối chiếu Javadoc của đúng Core version |
| Cấu hình có nhưng không có tác dụng | Mapper dùng một `JsonFactory` khác | Kiểm tra đúng factory thực tế được truyền vào mapper |
| IDE compile nhưng runtime lỗi class/method | Core và Databind lệch phiên bản | Dùng BOM và kiểm tra dependency tree |
| Chỉ parser trực tiếp bị giới hạn, mapper khác thì không | Các parser được tạo từ factory khác nhau | Dùng factory cấu hình thống nhất theo luồng |
| Input nhiều phần tử nhỏ vẫn quá lớn | Nesting/string/number limit không giới hạn tổng document | Giới hạn body bytes, số phần tử và tổng tài nguyên ở tầng khác |
| JSON output lớn vẫn ghi được | Write constraints không giới hạn tổng output bytes | Phân trang, streaming và kiểm soát dung lượng output |
| File output dở dang sau exception | Generator đã ghi trước khi gặp lỗi | Ghi file tạm rồi publish khi thành công |
| Global config làm thay đổi mapper khác | Thay đổi default ảnh hưởng factory ở phạm vi rộng | Ưu tiên per-factory configuration |
| Nâng Jackson gây thay đổi hành vi | Default hoặc API constraints khác giữa minor versions | Pin BOM, đọc release notes và chạy contract/security tests |

## 20. Quy trình triển khai theo phiên bản

Khi thêm constraints vào dự án:

1. Xác định major/minor version của `jackson-core` ở compile và runtime.
2. Kiểm tra `jackson-databind`, `jackson-annotations` và module liên quan có cùng release train.
3. Nếu Core thấp hơn 2.15, chưa dùng được `StreamReadConstraints`; lên kế hoạch nâng cấp hoặc áp dụng giới hạn ở tầng transport/application trong thời gian chuyển tiếp.
4. Với Core 2.15, cấu hình read constraints trên `JsonFactory`.
5. Với Core 2.16+, cấu hình thêm write constraints nếu cần giới hạn nesting khi serialize.
6. Chỉ dùng builder method bổ sung khi phiên bản cụ thể hỗ trợ.
7. Ưu tiên per-factory configuration; chỉ đổi global default khi có lý do toàn process.
8. Chọn ngưỡng dựa trên schema và payload hợp lệ lớn nhất.
9. Bổ sung giới hạn tổng body, số phần tử, timeout và output size ở các tầng phù hợp.
10. Kiểm thử cả input/output trong giới hạn và vượt giới hạn.
11. Kiểm tra exception mapping và xử lý output một phần.
12. Xác nhận ứng dụng thực sự dùng factory đã cấu hình.

Nếu nâng từ Jackson 2.x lên 3.x, cần đọc hướng dẫn migration cho major version đó. Ví dụ import `com.fasterxml.jackson.*` trong bài này dành cho Jackson 2.x; không giữ nguyên package import một cách máy móc khi chuyển sang major version mới.

## 21. Bài thực hành tổng hợp

Tạo một ứng dụng nhỏ đọc và ghi JSON bằng Jackson.

### Phần A — Cấu hình đọc

1. Xác nhận phiên bản `jackson-core`.
2. Tạo `StreamReadConstraints` với giới hạn nesting, string và number phù hợp.
3. Gắn vào `JsonFactory`.
4. Tạo `ObjectMapper` từ factory.
5. Đọc JSON bình thường và xác nhận thành công.
6. Đọc JSON có string quá dài và xác nhận `StreamConstraintsException`.
7. Đọc numeric literal quá dài và xác nhận bị từ chối.
8. Tạo JSON lồng nhau vượt giới hạn và kiểm tra lỗi.
9. Nếu phiên bản hỗ trợ `maxNameLength`, kiểm thử tên property quá dài.

### Phần B — Cấu hình ghi

1. Dùng Jackson Core 2.16+.
2. Tạo `StreamWriteConstraints` với giới hạn nesting.
3. Gắn vào `JsonFactory`.
4. Serialize object graph trong giới hạn.
5. Serialize object graph vượt giới hạn và xác nhận lỗi.
6. Kiểm tra output destination có thể chứa dữ liệu một phần sau exception.
7. Với file export, thử ghi file tạm và chỉ đổi tên sau khi serialize hoàn tất.

### Phần C — Kiểm tra version và dependency

1. Khai báo Jackson BOM.
2. Kiểm tra dependency tree để bảo đảm Core và Databind đồng bộ.
3. Thử compile code read constraints với phiên bản 2.15+.
4. Thử write constraints với phiên bản 2.16+.
5. Ghi lại builder method nào được phiên bản dự án hỗ trợ.
6. Nếu thử major version mới, cập nhật package import và migration theo tài liệu tương ứng.

### Phần D — Kiểm tra nhiều lớp bảo vệ

1. Đặt giới hạn HTTP body bytes.
2. Đặt timeout đọc request.
3. Giữ read constraints cho nesting, string và number.
4. Giới hạn số phần tử ở application/schema layer.
5. Giới hạn output size hoặc phân trang kết quả.
6. Ghi log loại constraint exception và correlation id, không ghi toàn bộ payload nhạy cảm.

Bài thực hành hoàn thành khi có thể giải thích giới hạn nào được thực thi ở JsonFactory, giới hạn nào thuộc HTTP/application và cách chọn đúng API theo phiên bản Jackson thực tế.

## 22. Nguyên tắc ghi nhớ

- `StreamReadConstraints` bảo vệ quá trình đọc JSON; `StreamWriteConstraints` kiểm soát một số đặc điểm khi ghi JSON.
- Jackson 2.15+ có read constraints; write constraints có từ Jackson 2.16 trong dòng 2.x.
- Kiểm tra phiên bản `jackson-core` thực tế, không chỉ phiên bản Databind khai báo trực tiếp.
- Cấu hình constraints trên `JsonFactory` trước khi tạo `ObjectMapper`.
- Mọi parser/generator tạo từ factory dùng chính sách tương ứng của factory.
- `maxNestingDepth`, `maxStringLength` và `maxNumberLength` giới hạn những đặc điểm khác nhau.
- Một số builder method bổ sung, như giới hạn tên property, phụ thuộc minor version.
- `ObjectReader`/`ObjectWriter` không thay thế constraints của factory.
- Ưu tiên per-factory configuration; global default có phạm vi ảnh hưởng rộng.
- Dùng Jackson BOM để tránh Core, Databind và module lệch phiên bản.
- Nesting limit không giới hạn số phần tử hoặc tổng body bytes.
- Read constraints không thay thế HTTP body limit, timeout, decompression limit hoặc validation.
- Write constraints không giới hạn tổng output size; streaming, paging và quota vẫn cần thiết.
- Khi ghi thất bại, output stream/file có thể đã chứa một phần dữ liệu.
- Kiểm thử cả trường hợp hợp lệ, vượt giới hạn, runtime factory thực tế và hành vi sau exception.

Hãy xác định phiên bản Jackson trước, sau đó đặt read/write constraints trên đúng `JsonFactory` của từng luồng dữ liệu. Kết hợp giới hạn parser/generator với giới hạn HTTP, application và output destination để kiểm soát tài nguyên theo đúng nơi chúng được sử dụng.
