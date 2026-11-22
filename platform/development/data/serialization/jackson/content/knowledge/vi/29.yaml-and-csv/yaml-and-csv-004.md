# Giới hạn tài nguyên khi đọc dữ liệu YAML không tin cậy

YAML thường được chọn cho file cấu hình, manifest, dữ liệu import và trao đổi giữa các hệ thống vì dễ đọc hơn JSON. Tuy nhiên, một file YAML do người dùng hoặc hệ thống bên ngoài cung cấp vẫn là đầu vào không tin cậy. Một tài liệu có thể đúng cú pháp nhưng chứa chuỗi cực dài, cấu trúc lồng quá sâu, số lượng phần tử rất lớn, nhiều anchor/alias hoặc nhiều document nối tiếp nhau. Nếu ứng dụng đọc toàn bộ dữ liệu vào bộ nhớ mà không có giới hạn, một payload nhỏ hoặc vừa phải cũng có thể tiêu tốn CPU, heap và thời gian xử lý bất thường.

Jackson XML module không liên quan tới YAML; để đọc YAML bằng Jackson cần `jackson-dataformat-yaml` và `YAMLMapper`/`YAMLFactory` (hoặc `ObjectMapper` được tạo từ `YAMLFactory`). Module này dùng parser dựa trên SnakeYAML để chuyển YAML thành token mà Jackson Databind có thể ánh xạ sang Java type. Vì vậy, cần hiểu cả giới hạn ở parser YAML/SnakeYAML, giới hạn token của Jackson Core và giới hạn ở tầng ứng dụng.

Bài học tập trung vào kiểm soát tài nguyên khi đọc YAML không tin cậy. Các ví dụ dùng Jackson 2.x và SnakeYAML 2.x; API builder và các giới hạn có thể khác theo version. Hãy đồng bộ version Jackson bằng BOM và kiểm tra version SnakeYAML thực tế trong dependency tree trước khi áp dụng cấu hình.

## 1. Những nguồn tiêu tốn tài nguyên trong YAML

YAML có một số tính năng làm việc đọc dữ liệu phức tạp hơn một JSON document đơn giản:

- **Scalar lớn:** một string, block scalar hoặc number có thể rất dài.
- **Nesting sâu:** mapping và sequence có thể lồng nhiều cấp.
- **Collection lớn:** một sequence có thể chứa hàng triệu item; một mapping có thể có rất nhiều key.
- **Anchor và alias:** một node có thể được đặt anchor rồi được tham chiếu lại nhiều lần.
- **Recursive reference:** alias có thể tạo cấu trúc tham chiếu vòng trong một số dạng YAML.
- **Nhiều document:** một stream có thể chứa nhiều YAML document, phân tách bằng `---`.
- **Kiểu dữ liệu và tag:** YAML có scalar resolution và tag metadata; ứng dụng có thể áp dụng custom binding hoặc polymorphic typing sau khi parser tạo token.

Ví dụ một YAML document có cú pháp hợp lệ nhưng chứa sequence lớn:

```yaml
items:
  - id: 1
    name: first
  - id: 2
    name: second
  # Có thể tiếp tục với rất nhiều item.
```

Hoặc nesting sâu:

```yaml
root:
  child:
    child:
      child:
        child:
          value: deep
```

Hoặc anchor/alias:

```yaml
defaults: &defaults
  timeout: 10
  retries: 3

serviceA:
  <<: *defaults

serviceB:
  <<: *defaults
```

Anchor/alias là tính năng hợp lệ của YAML và hữu ích để tránh lặp cấu hình. Tuy nhiên, nếu không giới hạn số alias và kích thước dữ liệu, parser có thể phải xử lý một đồ thị node phức tạp hơn nhiều so với hình thức văn bản ban đầu.

## 2. Phân chia các lớp giới hạn

Không có một tùy chọn Jackson duy nhất giới hạn toàn bộ chi phí đọc YAML. Cần kết hợp nhiều lớp:

| Lớp | Giới hạn cần đặt | Ví dụ cơ chế |
|---|---|---|
| HTTP/API ingress | Tổng số byte body, timeout, tốc độ gửi | Gateway, HTTP server, framework request limit |
| YAML parser | Tổng code point, alias collection, nesting depth, duplicate key | SnakeYAML `LoaderOptions` |
| Jackson Core | Độ sâu token, độ dài string/number | `StreamReadConstraints` nếu module/version hỗ trợ |
| Jackson Databind | Kiểu đích, subtype, trailing token, unknown property | DTO cụ thể và `DeserializationFeature` |
| Application | Số record, số key, batch size, thời gian xử lý | Streaming, counter, backpressure và validation |
| Hạ tầng chạy | Heap, CPU, concurrency, quota | Container limits, thread pool, rate limit |

Các lớp bổ trợ nhau. Ví dụ, `@Size(max = 500)` có thể kiểm tra list sau khi Jackson tạo list; nó không ngăn parser tạo một list gồm hàng triệu phần tử trước khi validation chạy. Muốn giới hạn trước khi materialize, phải giới hạn body hoặc đọc streaming và dừng khi vượt số record.

## 3. Cấu hình `LoaderOptions` của SnakeYAML

Jackson YAML sử dụng SnakeYAML để phân tích cú pháp YAML. `LoaderOptions` cung cấp các giới hạn quan trọng cho parser.

```java
import org.yaml.snakeyaml.LoaderOptions;

LoaderOptions loaderOptions = new LoaderOptions();
loaderOptions.setCodePointLimit(1_000_000);
loaderOptions.setMaxAliasesForCollections(20);
loaderOptions.setNestingDepthLimit(60);
loaderOptions.setAllowDuplicateKeys(false);
loaderOptions.setAllowRecursiveKeys(false);
```

Ý nghĩa các tùy chọn:

- `setCodePointLimit(...)`: giới hạn số Unicode code point được parser xử lý trong stream. Đây không phải giới hạn byte của HTTP body.
- `setMaxAliasesForCollections(...)`: giới hạn số alias tham chiếu tới collection được parser chấp nhận. Giá trị nhỏ hơn giúp giảm bề mặt tấn công qua anchor/alias; chọn theo file hợp lệ của ứng dụng.
- `setNestingDepthLimit(...)`: giới hạn độ sâu nesting của YAML trong các version SnakeYAML có API này.
- `setAllowDuplicateKeys(false)`: từ chối mapping có key trùng lặp.
- `setAllowRecursiveKeys(false)`: không cho phép recursive key trong YAML mapping.

Các setter như `setNestingDepthLimit` phụ thuộc version SnakeYAML. Nếu dự án dùng version cũ chưa có API tương ứng, hãy nâng version được Jackson YAML hỗ trợ hoặc áp dụng giới hạn thay thế ở parser/application layer; không bỏ qua lỗi compile bằng cách xóa toàn bộ giới hạn.

### 3.1. Vì sao code point limit không thay thế body byte limit?

`codePointLimit` đếm nội dung văn bản theo Unicode code point ở parser layer. HTTP body được truyền bằng byte và có thể dùng UTF-8 hoặc encoding khác. Một triệu code point không đồng nghĩa một triệu byte; ký tự Unicode có thể chiếm nhiều byte trong UTF-8.

Hơn nữa, nếu server đã buffer body thành `byte[]` hoặc `String` trước khi Jackson đọc, parser limit không ngăn được chi phí buffer ban đầu. Vì vậy, luôn đặt giới hạn byte ở ingress/server, sau đó mới dùng `codePointLimit` để bảo vệ parser.

### 3.2. Chọn alias limit theo nhu cầu thực tế

Alias là tính năng bình thường của YAML. Không nhất thiết phải cấm hoàn toàn nếu file cấu hình hợp lệ đang dùng anchor/alias. Tuy nhiên, hãy đặt một ngưỡng thấp đủ dùng.

Ví dụ file cấu hình nội bộ chỉ có vài anchor có thể dùng ngưỡng nhỏ. Một file import do đối tác gửi có thể không cần alias; khi đó, có thể đặt ngưỡng rất thấp hoặc bằng 0 theo semantics của SnakeYAML version đang dùng. Hãy xác nhận hành vi của giá trị 0 trong version cụ thể bằng test, vì không nên suy đoán rằng 0 luôn có nghĩa “không alias” trong mọi API.

## 4. Gắn `LoaderOptions` vào `YAMLFactory`

Jackson YAML cho phép cung cấp `LoaderOptions` khi xây dựng `YAMLFactory`:

```java
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.yaml.snakeyaml.LoaderOptions;

LoaderOptions loaderOptions = new LoaderOptions();
loaderOptions.setCodePointLimit(1_000_000);
loaderOptions.setMaxAliasesForCollections(20);
loaderOptions.setNestingDepthLimit(60);
loaderOptions.setAllowDuplicateKeys(false);

YAMLFactory yamlFactory = YAMLFactory.builder()
        .loaderOptions(loaderOptions)
        .build();

ObjectMapper yamlMapper = new ObjectMapper(yamlFactory);
```

Từ đây, `yamlMapper` đọc YAML thông qua factory đã cấu hình:

```java
ImportManifest manifest = yamlMapper.readValue(yamlText, ImportManifest.class);
```

Điểm quan trọng là `LoaderOptions` phải được gắn vào đúng `YAMLFactory` mà mapper thực sự sử dụng. Tạo một `LoaderOptions` riêng nhưng không truyền nó vào factory sẽ không thay đổi parser.

### 4.1. Dùng `YAMLMapper.builder()` nếu version cung cấp

Một số version Jackson YAML có builder riêng cho `YAMLMapper`. Có thể cấu hình tương đương qua factory hoặc mapper builder theo API version. Nếu không chắc builder của version dự án có hỗ trợ `loaderOptions`, cách rõ ràng là tạo `YAMLFactory` với options rồi truyền vào `ObjectMapper` như ví dụ trên.

### 4.2. Hoàn tất cấu hình trước khi chia sẻ mapper

`ObjectMapper` được thiết kế để tái sử dụng sau khi cấu hình hoàn tất. Hãy tạo factory, gắn `LoaderOptions`, cấu hình module và feature ở giai đoạn startup. Không thay đổi parser options theo từng request trên một mapper đang được chia sẻ.

Nếu hai integration có giới hạn khác nhau, hãy tạo mapper/factory riêng cho từng ranh giới hoặc dùng reader riêng cho những feature Databind có thể cấu hình theo lần đọc. Không dùng cùng một mapper rồi thay factory/options liên tục.

## 5. Kết hợp `StreamReadConstraints` của Jackson Core

SnakeYAML `LoaderOptions` kiểm soát những đặc tính YAML-specific. Jackson Core có `StreamReadConstraints` để giới hạn độ sâu token và độ dài string/number ở parser layer trong các version hỗ trợ.

```java
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

StreamReadConstraints readConstraints = StreamReadConstraints.builder()
        .maxNestingDepth(60)
        .maxStringLength(200_000)
        .maxNumberLength(1_000)
        .build();

YAMLFactory yamlFactory = YAMLFactory.builder()
        .loaderOptions(loaderOptions)
        .streamReadConstraints(readConstraints)
        .build();
```

Các giới hạn có ý nghĩa:

- `maxNestingDepth`: giới hạn nesting ở Jackson token parser.
- `maxStringLength`: giới hạn chiều dài string token.
- `maxNumberLength`: giới hạn chiều dài number token.

Nên dùng cả giới hạn SnakeYAML và Jackson khi version/module hỗ trợ. Hai lớp nằm ở hai tầng khác nhau; một số đặc tính YAML có thể bị giới hạn bởi SnakeYAML trước khi trở thành token Jackson. Hãy kiểm thử trên đúng `YAMLFactory` và version đang dùng để xác nhận giới hạn được thực thi như mong đợi.

Không nhầm `maxStringLength` với tổng kích thước tài liệu. Một YAML document có thể chứa hàng nghìn string, mỗi string đều nhỏ hơn giới hạn, nhưng tổng số byte vẫn rất lớn.

## 6. Giới hạn body bytes ở ingress

Parser chỉ bắt đầu bảo vệ dữ liệu sau khi ứng dụng chuyển stream cho Jackson. Để ngăn payload quá lớn chiếm bộ nhớ trước khi parse, hãy giới hạn ở:

- Reverse proxy hoặc API gateway.
- HTTP server và framework nhận request.
- Multipart/file upload handler nếu YAML đến từ file.
- Consumer nhận message nếu YAML được gửi qua broker.
- Bounded stream khi ứng dụng đọc file hoặc stream trực tiếp.

Không chỉ dựa vào `Content-Length`: request có thể được truyền theo chunked encoding hoặc qua một lớp trung gian không cung cấp length đáng tin. Server phải thực thi giới hạn số byte thực sự được nhận/đọc.

Ví dụ chính sách ở ingress có thể là:

| Loại dữ liệu | Ví dụ giới hạn cần quyết định |
|---|---|
| API config nhỏ | Vài trăm KB hoặc ngưỡng theo schema |
| File import | Giới hạn MB rõ ràng theo nghiệp vụ |
| Event message | Giới hạn kích thước từng message ở producer/broker/consumer |
| Batch lớn | Chia thành nhiều batch hoặc dùng streaming protocol |

Các con số phải xuất phát từ payload hợp lệ lớn nhất, số lượng request đồng thời và ngân sách bộ nhớ của ứng dụng. Không có một ngưỡng byte chung phù hợp cho mọi hệ thống.

## 7. Anchor và alias: giới hạn trước khi xử lý graph

YAML cho phép đặt anchor bằng `&name` và tham chiếu bằng `*name`:

```yaml
defaults: &defaults
  timeout: 10
  retries: 3

workerA:
  config: *defaults

workerB:
  config: *defaults
```

Đây là cách hợp lệ để tái sử dụng node. Nhưng payload không tin cậy có thể khai thác alias để làm parser xử lý nhiều tham chiếu và cấu trúc lặp phức tạp.

SnakeYAML cung cấp `maxAliasesForCollections` trong `LoaderOptions` để giới hạn alias tham chiếu collection. Cấu hình:

```java
LoaderOptions options = new LoaderOptions();
options.setMaxAliasesForCollections(10);
```

Ngưỡng này nên được chọn theo nhu cầu thực tế. Nếu file YAML hợp lệ không dùng alias, cân nhắc cấm alias theo semantics được tài liệu hóa của version SnakeYAML đang dùng. Nếu file cấu hình nội bộ cần anchor, cho phép số lượng nhỏ và kiểm tra test.

### 7.1. Alias không phải là giới hạn tổng node

Alias limit chỉ kiểm soát một khía cạnh của YAML. Nó không giới hạn tổng số mapping entry, tổng số scalar hoặc tổng số item trong sequence. Một file không dùng alias vẫn có thể chứa collection rất lớn.

Do đó, cần kết hợp body byte limit, code point limit, nesting depth và giới hạn record ở application layer.

### 7.2. Recursive alias và graph vòng

YAML có thể mô tả tham chiếu vòng thông qua anchor/alias trong những cấu trúc được parser cho phép. Không nên giả định mọi object graph vòng đều phù hợp với DTO hoặc domain model.

Nếu ứng dụng không cần recursive structure, từ chối cấu trúc không phù hợp hoặc chuyển sang schema không cho phép vòng. Nếu cần hỗ trợ, hãy xác định rõ giới hạn node, depth và cách Jackson binding biểu diễn tham chiếu; không để graph tùy ý đi sâu vào logic nghiệp vụ.

## 8. Giới hạn nesting depth

Nesting sâu có thể làm tăng chi phí parser, binder và validator. Một YAML payload có thể lồng mapping/sequence rất nhiều tầng dù tổng byte không quá lớn.

Đặt giới hạn trong SnakeYAML:

```java
options.setNestingDepthLimit(50);
```

Và, khi parser version hỗ trợ, đặt giới hạn Jackson Core:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
        .maxNestingDepth(50)
        .build();
```

Hai giới hạn không nên bị xem là cùng một phép đo nội bộ. SnakeYAML kiểm soát nesting trong quá trình phân tích YAML; Jackson Core kiểm soát nesting token trong quá trình đọc. Cấu trúc YAML như anchor/alias, document boundary và cách parser phát token có thể khiến hai phép đo không hoàn toàn tương đương.

Chọn ngưỡng đủ cho schema hợp lệ và kiểm thử một payload vừa dưới ngưỡng lẫn một payload vượt ngưỡng. Nếu một cấu trúc nghiệp vụ chỉ cần 4-5 tầng, không có lý do cho phép hàng nghìn tầng.

## 9. Giới hạn string và number

Scalar YAML có thể là plain scalar, quoted scalar hoặc block scalar. Một trường text có thể chứa nhiều dòng:

```yaml
description: |
  Đây là nội dung nhiều dòng.
  Có thể tiếp tục rất dài.
```

`maxStringLength` của Jackson và `codePointLimit` của SnakeYAML giúp hạn chế một số trường hợp scalar lớn. `maxNumberLength` giúp ngăn số có hàng trăm nghìn chữ số làm parser/binder tốn tài nguyên.

Ví dụ:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
        .maxStringLength(100_000)
        .maxNumberLength(500)
        .build();
```

Ngoài giới hạn parser, DTO nên có constraint theo nghiệp vụ:

```java
public record ImportRow(
        @NotBlank @Size(max = 80) String code,
        @Size(max = 2_000) String description,
        @PositiveOrZero Long amount) {
}
```

Giới hạn parser bảo vệ quá trình đọc tổng quát; Bean Validation bảo đảm field có kích thước hợp lệ cho use case. Hai lớp có mục tiêu khác nhau.

## 10. Từ chối duplicate mapping key

YAML mapping có thể chứa key trùng:

```yaml
role: user
role: admin
```

Nếu parser cho phép duplicate key, giá trị được giữ lại có thể phụ thuộc implementation hoặc cấu hình. Một gateway, validator và service có thể hiểu khác nhau nếu mỗi thành phần xử lý duplicate key khác nhau.

Đặt:

```java
options.setAllowDuplicateKeys(false);
```

Khi đó, parser từ chối mapping có key trùng theo hành vi SnakeYAML version đang dùng. Đây là lựa chọn phù hợp cho nhiều cấu hình và payload nghiệp vụ vì mỗi key có một ý nghĩa duy nhất.

Không dựa vào thứ tự “giá trị đầu” hoặc “giá trị cuối” để quyết định dữ liệu. Nếu một schema thật sự cần biểu diễn nhiều giá trị cùng tên, hãy dùng sequence:

```yaml
roles:
  - user
  - admin
```

## 11. YAML có nhiều document: giới hạn số document

YAML stream có thể chứa nhiều document, phân tách bằng `---`:

```yaml
---
name: first
---
name: second
```

Một endpoint có thể chỉ chấp nhận đúng một document; một file import có thể chủ đích chứa nhiều record document. Cần định nghĩa contract rõ ràng.

Nếu chỉ nhận một document, dùng reader/feature kiểm tra trailing content phù hợp với Jackson YAML version và kiểm thử với nhiều document. `FAIL_ON_TRAILING_TOKENS` có thể giúp phát hiện token thừa sau value được đọc trong các trường hợp parser biểu diễn chúng như trailing token; hãy xác nhận hành vi với YAML multi-document của version cụ thể.

Nếu chấp nhận nhiều document, hãy đọc tuần tự và đặt giới hạn số document:

```java
ObjectReader documentReader = mapper.readerFor(ImportDocument.class);

int documentCount = 0;
try (MappingIterator<ImportDocument> documents =
             documentReader.readValues(inputStream)) {
    while (documents.hasNextValue()) {
        if (++documentCount > MAX_DOCUMENTS) {
            throw new PayloadLimitException("Too many YAML documents");
        }

        ImportDocument document = documents.nextValue();
        process(document);
    }
}
```

Khả năng `readValues()` phân tách YAML document theo mong muốn phụ thuộc parser/module version; cần integration test với separator `---`, document rỗng và end marker `...`. Nếu protocol cần framing nghiêm ngặt, có thể dùng YAML parser/StAX-like event boundary rõ ràng thay vì dựa vào giả định về sequence.

## 12. Giới hạn tổng số phần tử trong sequence

Một YAML sequence có thể rất lớn:

```yaml
items:
  - code: A
  - code: B
  - code: C
```

`@Size(max = 500)` trên `List<Item>` chỉ được kiểm tra sau khi Jackson đã tạo list. Với file lớn, nên đọc streaming từng item hoặc chia batch.

Ví dụ YAML top-level sequence:

```yaml
- code: A
  quantity: 1
- code: B
  quantity: 2
```

Có thể đọc từng item qua `JsonParser`:

```java
try (JsonParser parser = yamlFactory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new InvalidYamlShapeException("Expected a top-level sequence");
    }

    int count = 0;
    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (++count > MAX_ITEMS) {
            throw new PayloadLimitException("Too many YAML items");
        }

        ImportItem item = mapper.readValue(parser, ImportItem.class);
        validate(item);
        process(item);
    }
}
```

Khi parser đang ở token bắt đầu item, `readValue(parser, ImportItem.class)` đọc item hiện tại. Vòng lặp tiếp tục với token tiếp theo. Ví dụ minh họa top-level sequence; nếu YAML có root mapping với property `items`, cần xử lý field name và START_ARRAY tương ứng.

Streaming giúp không cần giữ toàn bộ list trong heap. Tuy nhiên, `process()` cũng phải có backpressure hoặc batch limit. Nếu mỗi item được đưa vào một list tích lũy không giới hạn, ứng dụng vẫn có thể hết bộ nhớ.

## 13. Giới hạn số key trong mapping

Một mapping có thể có rất nhiều key dù mỗi key/value nhỏ. `LoaderOptions` code point limit giới hạn tổng văn bản, nhưng không thay thế giới hạn số entry theo nghiệp vụ.

Với DTO cố định, Jackson chỉ bind property được mô tả; strict unknown-property policy có thể từ chối key không biết. Nhưng nếu model dùng `Map<String, Object>` hoặc `Map<String, JsonNode>`, mọi key có thể được giữ lại.

Với extension map, sau binding cần kiểm tra:

```java
if (metadata.size() > MAX_METADATA_KEYS) {
    throw new PayloadLimitException("Too many metadata entries");
}
```

Nếu map có thể rất lớn, kiểm tra sau binding vẫn quá muộn. Hãy streaming mapping entries hoặc dùng custom deserializer có counter dừng ngay khi vượt giới hạn. Đừng chấp nhận map động không giới hạn chỉ vì parser có code point limit.

## 14. Dùng DTO cụ thể và tránh kiểu đích quá rộng

Đọc YAML vào `Object`, `Map<String, Object>` hoặc một model có nhiều property không cần thiết làm giảm khả năng kiểm soát schema và lượng object được tạo.

Ưu tiên DTO thể hiện hợp đồng:

```java
public record ServiceConfig(
        @NotBlank @Size(max = 60) String name,
        @Min(1) @Max(30) int timeoutSeconds,
        @Size(max = 20) List<@NotBlank String> endpoints) {
}
```

Deserialize:

```java
ServiceConfig config = mapper.readValue(yamlInput, ServiceConfig.class);
```

DTO cụ thể giúp Jackson biết kiểu đích và giúp ứng dụng kiểm soát property được nhận. Sau binding, chạy Bean Validation và kiểm tra business rule.

Nếu cần YAML linh hoạt, dùng `JsonNode` hoặc `Map<String, JsonNode>` trong một vùng extension được giới hạn. Tránh cho payload quyết định class Java cần khởi tạo.

## 15. Kiểm soát polymorphic typing khi đọc YAML

YAML có tag syntax như `!custom` hoặc các tag theo URI. Jackson YAML chuyển dữ liệu parser thành token Databind; không nên nhầm tag YAML với một cơ chế an toàn để chọn Java class.

Nếu model dùng polymorphic deserialization, hãy dùng logical type ID với subtype allowlist:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = HttpSource.class, name = "http"),
        @JsonSubTypes.Type(value = FileSource.class, name = "file")
})
public interface SourceConfig {
}
```

YAML:

```yaml
kind: http
url: https://example.test/data
```

Không bật default typing rộng hoặc cho phép class name tùy ý từ YAML không tin cậy. Giữ `FAIL_ON_INVALID_SUBTYPE` để type ID không được hỗ trợ bị từ chối.

Nếu ứng dụng dùng SnakeYAML trực tiếp để tạo object thay vì chỉ dùng Jackson YAML parser, hãy chọn constructor an toàn như `SafeConstructor` cho dữ liệu không tin cậy và không dùng constructor cho phép arbitrary Java class tags. Cách dùng SnakeYAML trực tiếp khác với Jackson Databind; hãy đánh giá đúng đường code đang chạy.

## 16. Phân biệt YAML parser với SnakeYAML object construction

`jackson-dataformat-yaml` dùng SnakeYAML ở tầng parser để đọc cấu trúc YAML, sau đó Jackson Databind ánh xạ token sang target Java type. Đây không giống việc gọi trực tiếp `new Yaml().load(...)` để SnakeYAML tự tạo object theo constructor của nó.

Nếu codebase có cả hai cách đọc, cần đánh giá riêng:

**Jackson YAML:**

```java
YAMLFactory factory = YAMLFactory.builder()
        .loaderOptions(options)
        .build();
ObjectMapper mapper = new ObjectMapper(factory);
Config config = mapper.readValue(input, Config.class);
```

**SnakeYAML trực tiếp:**

```java
LoaderOptions options = new LoaderOptions();
options.setCodePointLimit(1_000_000);
options.setMaxAliasesForCollections(20);

Yaml yaml = new Yaml(new SafeConstructor(options));
Object data = yaml.load(input);
```

Với SnakeYAML trực tiếp, `SafeConstructor` giới hạn các loại object được xây dựng theo tập an toàn của thư viện. Sau khi nhận `Object`/map/list, ứng dụng vẫn cần kiểm tra kiểu và schema. Không thay `SafeConstructor` bằng constructor tổng quát cho dữ liệu bên ngoài chỉ để tạo class tùy ý.

Không trộn hai API trong cùng ví dụ hoặc giả định cấu hình `LoaderOptions` của một `Yaml` instance tự động ảnh hưởng tới `YAMLFactory` khác. Mỗi parser instance cần nhận đúng options.

## 17. Kiểm soát duplicate key và merge key

YAML có thể dùng merge key `<<` để kế thừa mapping từ anchor:

```yaml
defaults: &defaults
  timeout: 10
  retries: 3

service:
  <<: *defaults
  timeout: 20
```

Merge key có thể tạo ra kết quả mapping cuối cùng khác với việc chỉ đọc từng dòng văn bản. Khi dùng merge key, cần hiểu parser version xử lý precedence và duplicate key như thế nào.

`setAllowDuplicateKeys(false)` giúp từ chối duplicate mapping key theo parser. Tuy nhiên, semantics merge key có thể có quy tắc riêng trong SnakeYAML; hãy kiểm thử trường hợp key được kế thừa rồi ghi đè.

Nếu ứng dụng không cần merge key hoặc anchor, cân nhắc từ chối các cấu trúc đó theo policy của parser hoặc schema. Một YAML subset đơn giản thường dễ validate và vận hành an toàn hơn một dialect đầy đủ không cần thiết.

## 18. Kiểm soát YAML scalar resolution

YAML có thể diễn giải plain scalar theo quy tắc resolver của parser. Các chuỗi như `true`, `false`, một số dạng số, ngày hoặc giá trị kiểu YAML 1.1 có thể được nhận diện khác với kỳ vọng nếu không được quote.

Ví dụ:

```yaml
enabled: yes
code: 0012
date: 2026-11-12
```

Tùy YAML version/resolver và SnakeYAML version, các giá trị plain scalar có thể được token hóa thành boolean, number hoặc kiểu scalar khác thay vì string thuần. Nếu một field là mã định danh, hãy quote để thể hiện rõ là string:

```yaml
enabled: true
code: "0012"
date: "2026-11-12"
```

Không dựa vào resolver mặc định để bảo vệ kiểu dữ liệu. DTO, coercion policy và test phải xác nhận token được ánh xạ đúng. Đặc biệt, mã có leading zero thường nên là string, không phải integer.

## 19. Giới hạn thời gian và concurrency

Giới hạn parser không ngăn được mọi kiểu tiêu tốn CPU. Một số payload có nhiều node nhỏ, nhiều mapping hoặc custom validation đắt đỏ vẫn có thể xử lý lâu.

Kết hợp:

- HTTP/read timeout và request deadline.
- Rate limit theo client/tenant.
- Giới hạn số YAML parse đồng thời.
- Thread pool có queue bounded.
- Giới hạn record/batch size.
- Giới hạn số query hoặc external call sau khi parse.
- Circuit breaker và quota ở downstream nếu cần.

Không chạy parse file không giới hạn trên thread request quan trọng nếu dữ liệu có thể lớn. Với import job, dùng worker pool có concurrency và queue size rõ ràng; từ chối hoặc đưa file vượt giới hạn vào quarantine.

## 20. Tránh materialize toàn bộ file nếu không cần

Đối với file nhỏ, `readValue()` vào DTO có thể đơn giản và phù hợp. Đối với file lớn, hãy đọc stream theo record/document và xử lý từng phần.

So sánh:

```java
List<ImportRow> rows = mapper.readValue(
        input,
        new TypeReference<List<ImportRow>>() {}
);
processAll(rows);
```

Với cách này, toàn bộ list và object graph được giữ trong heap.

Streaming:

```java
try (JsonParser parser = yamlFactory.createParser(input)) {
    // Đọc token và deserialize từng item, sau đó xử lý/ghi theo batch.
}
```

Streaming giảm lượng dữ liệu cần giữ cùng lúc, nhưng cần thiết kế xử lý lỗi theo record, transaction/batch và backpressure. Nếu ứng dụng giữ tất cả kết quả hoặc tất cả lỗi trong một list không giới hạn, heap vẫn có thể tăng không kiểm soát.

## 21. Giới hạn số lỗi validation được tích lũy

Một file import lớn có thể chứa rất nhiều record không hợp lệ. Nếu ứng dụng lưu mọi `ConstraintViolation` và mọi raw value vào một collection, báo cáo lỗi cũng có thể trở thành nguồn tiêu tốn bộ nhớ.

Đặt giới hạn:

- Số lỗi tối đa lưu trong response hoặc report.
- Số record tối đa xử lý trong một batch.
- Kích thước message lỗi.
- Số ký tự input được giữ lại để chẩn đoán.

Ví dụ, ứng dụng có thể đếm tổng lỗi nhưng chỉ lưu 100 lỗi đầu tiên:

```java
long totalErrors = 0;
List<ImportError> firstErrors = new ArrayList<>();

for (ImportRow row : rows) {
    List<ImportError> errors = validateRow(row);
    if (!errors.isEmpty()) {
        totalErrors += errors.size();
        if (firstErrors.size() < 100) {
            firstErrors.addAll(errors.stream()
                    .limit(100 - firstErrors.size())
                    .toList());
        }
    }
}
```

Trong streaming pipeline, cập nhật counter và report theo batch thay vì giữ toàn bộ record/error. Không ghi nguyên nội dung secret vào error report.

## 22. Không để validation sau binding trở thành giới hạn duy nhất

Bean Validation rất hữu ích cho constraint trên DTO:

```java
public record ImportConfig(
        @NotBlank @Size(max = 80) String name,
        @Size(max = 100) List<@Valid EndpointConfig> endpoints) {
}
```

Nhưng các constraint này chạy sau khi Jackson tạo object. Vì vậy:

- `@Size(max = 100)` không ngăn parser đọc sequence có một triệu item trước khi validate.
- `@Size(max = 80)` không thay parser string limit nếu scalar có thể rất lớn.
- `@Max` không giới hạn số chữ số trước khi number được parse nếu parser chưa có `maxNumberLength`.
- Nested validation không thay nesting depth limit.

Hãy đặt giới hạn càng sớm càng tốt ở tầng nhận byte và parser; dùng Bean Validation để kiểm tra quy tắc dữ liệu sau binding.

## 23. Cấu hình mapper YAML strict cho dữ liệu bên ngoài

Một cấu hình minh họa kết hợp các lớp parser và Databind:

```java
LoaderOptions loaderOptions = new LoaderOptions();
loaderOptions.setCodePointLimit(1_000_000);
loaderOptions.setMaxAliasesForCollections(20);
loaderOptions.setNestingDepthLimit(50);
loaderOptions.setAllowDuplicateKeys(false);
loaderOptions.setAllowRecursiveKeys(false);

StreamReadConstraints readConstraints = StreamReadConstraints.builder()
        .maxNestingDepth(50)
        .maxStringLength(100_000)
        .maxNumberLength(500)
        .build();

YAMLFactory factory = YAMLFactory.builder()
        .loaderOptions(loaderOptions)
        .streamReadConstraints(readConstraints)
        .build();

ObjectMapper yamlMapper = new ObjectMapper(factory)
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Đây là điểm khởi đầu, không phải một cấu hình mặc định phù hợp cho mọi file. Các giá trị `1_000_000`, `20`, `50`, `100_000` và `500` chỉ là ví dụ; điều chỉnh theo schema, file hợp lệ lớn nhất và ngân sách tài nguyên.

`FAIL_ON_TRAILING_TOKENS` phù hợp khi contract yêu cầu một root value. Với YAML multi-document, cần kiểm tra cách parser biểu diễn document boundary và dùng reader sequence phù hợp. Không bật một document policy rồi lại dùng nó cho giao thức nhiều document mà không test.

## 24. Quản lý version Jackson và SnakeYAML

Jackson YAML phụ thuộc SnakeYAML. Khi cập nhật version, kiểm tra:

- Version `jackson-dataformat-yaml` có tương thích với `jackson-core`, `jackson-databind` và `jackson-annotations` không.
- Version SnakeYAML thực tế có phải version được module yêu cầu không.
- `LoaderOptions` API có đủ các setter đang dùng không.
- Hành vi alias, duplicate key, merge key và multi-document có thay đổi không.
- `StreamReadConstraints` có được thực thi bởi YAML parser của version đó không.
- Các test malformed/large YAML có tiếp tục bị từ chối ở đúng giới hạn không.

Dùng Jackson BOM hoặc dependency management của framework để tránh lệch module. Kiểm tra dependency tree để phát hiện SnakeYAML version bắc cầu bị override ngoài dự kiến.

Không coi việc nâng dependency là đủ nếu mapper đang bật cấu hình nguy hiểm hoặc không giới hạn payload. Dependency patch và cấu hình runtime là hai lớp bảo vệ bổ trợ nhau.

## 25. Xử lý lỗi khi vượt giới hạn

Khi payload vượt giới hạn, parser có thể ném exception từ SnakeYAML hoặc Jackson. Không nên trả nguyên stack trace hay nội dung exception nội bộ ra client.

Có thể phân loại lỗi theo nhóm:

| Nhóm lỗi | Ví dụ | Xử lý ở API/import |
|---|---|---|
| Syntax | YAML indentation sai, dấu quote chưa đóng | Báo malformed YAML |
| Parser limit | Code point, nesting hoặc alias vượt ngưỡng | Báo payload vượt giới hạn |
| Mapping | Scalar không thể bind vào kiểu Java | Báo field/type không hợp lệ |
| Schema/validation | Thiếu field, list quá dài, format sai | Báo lỗi validation có field path |
| Business | Mã tham chiếu không tồn tại, trạng thái không cho phép | Báo lỗi nghiệp vụ cụ thể |
| Infrastructure | Timeout, stream bị ngắt, storage lỗi | Log correlation ID và xử lý retry theo policy |

Không tiết lộ ngưỡng bảo mật chi tiết nếu điều đó không cần thiết cho client. Có thể trả mã `PAYLOAD_LIMIT_EXCEEDED` cùng thông điệp chung và correlation ID.

## 26. Kiểm thử các giới hạn parser

Kiểm thử không chỉ payload hợp lệ. Cần tạo input vừa trong giới hạn và input vượt giới hạn cho từng cấu hình quan trọng.

### 26.1. Test code point limit

```java
@Test
void rejectsYamlBeyondCodePointLimit() {
    String yaml = "description: '" + "x".repeat(20_000) + "'";

    assertThrows(Exception.class,
            () -> mapper.readValue(yaml, ImportConfig.class));
}
```

Mapper test cần cấu hình `setCodePointLimit()` thấp hơn chiều dài input được tạo. Trong test thật, bắt exception parser cụ thể của version đang dùng nếu muốn xác nhận đúng nguyên nhân thay vì chỉ bắt `Exception`.

### 26.2. Test nesting depth

Tạo YAML lồng sâu hơn ngưỡng `setNestingDepthLimit()` và xác nhận parser từ chối trước khi service xử lý. Nên có một payload ở ngay dưới ngưỡng để tránh cấu hình quá thấp làm hỏng dữ liệu hợp lệ.

### 26.3. Test alias limit

Tạo document dùng anchor/alias collection vượt `maxAliasesForCollections` và xác nhận parser từ chối. Đồng thời test một file hợp lệ dùng số alias trong giới hạn.

### 26.4. Test duplicate keys

```java
@Test
void rejectsDuplicateMappingKeys() {
    String yaml = """
            role: user
            role: admin
            """;

    assertThrows(Exception.class,
            () -> mapper.readValue(yaml, Map.class));
}
```

Mapper cần `allowDuplicateKeys(false)`. Bắt exception cụ thể theo SnakeYAML/Jackson version nếu cần kiểm tra chính xác loại lỗi.

### 26.5. Test số item tối đa

Với streaming reader, test sequence có đúng `MAX_ITEMS` phải được xử lý; sequence có `MAX_ITEMS + 1` phải dừng và không gọi `process()` cho phần vượt giới hạn. Có thể dùng spy/fake để xác nhận số record đã xử lý.

## 27. Kiểm thử streaming và backpressure

Test streaming cần xác nhận:

- Parser không materialize toàn bộ list vào một collection lớn.
- Mỗi item được deserialize và xử lý theo thứ tự contract.
- Counter dừng ngay khi vượt giới hạn.
- Exception ở một item được xử lý theo policy: dừng file, bỏ record hoặc đưa vào error report có giới hạn.
- Batch size và queue size không vượt ngưỡng.
- Input stream/parser được đóng đúng ownership.

Với file import, có thể dùng một consumer nhận từng record và ghi theo batch. Nếu xử lý bất đồng bộ, queue phải bounded; nếu queue không giới hạn, producer streaming vẫn có thể đẩy dữ liệu nhanh hơn consumer và làm heap tăng liên tục.

## 28. Không log toàn bộ YAML khi parser thất bại

YAML config có thể chứa password, token, private key, endpoint nội bộ hoặc dữ liệu cá nhân. Khi parser báo lỗi ở một vị trí, tránh log toàn bộ document.

Ưu tiên ghi:

- Correlation ID/import ID.
- Nguồn file hoặc tenant đã được phép log.
- Kích thước byte và số document/record đã đọc.
- Loại exception và line/column nếu không làm lộ secret.
- Mã lỗi và giới hạn đã bị vượt.

Nếu cần giữ file để điều tra, lưu vào quarantine có quyền truy cập hạn chế, retention rõ ràng và mã hóa phù hợp. Không đưa raw YAML vào log line vì nó có thể chứa secret, ký tự điều khiển hoặc nội dung rất lớn.

## 29. Các lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Hướng xử lý |
|---|---|---|
| Chỉ giới hạn `Content-Length` | Chunked body hoặc lớp buffer có thể không được giới hạn đúng | Enforce byte count thực tế ở server/stream |
| Chỉ dùng `@Size` | Collection đã được tạo trước khi validation | Streaming và counter trước khi materialize |
| Không giới hạn alias | Parser phải xử lý graph tham chiếu phức tạp | `maxAliasesForCollections` phù hợp |
| Không giới hạn nesting | Payload lồng sâu làm tăng CPU/stack pressure | SnakeYAML nesting limit và Jackson constraints |
| Chỉ đặt `maxStringLength` | Tổng document hoặc số phần tử vẫn có thể rất lớn | Code point/body byte/record limits |
| Cho phép duplicate key | Các thành phần có thể hiểu payload khác nhau | `allowDuplicateKeys(false)` |
| Deserialize toàn bộ file lớn thành List | Heap tăng theo tổng record | Streaming và batch processing |
| Chỉ dùng mapper mặc định | Parser options không phản ánh policy của ứng dụng | Cấu hình `YAMLFactory` tường minh |
| Trộn SnakeYAML trực tiếp với Jackson YAML | Options ở parser này không áp dụng parser kia | Cấu hình đúng từng instance |
| Bật polymorphic typing rộng | YAML có thể ảnh hưởng class runtime được tạo | DTO cụ thể và subtype allowlist |
| Lưu mọi lỗi import | Error collection có thể lớn không giới hạn | Giới hạn số lỗi lưu và kích thước message |
| Log raw YAML | Lộ secret và tạo log injection/volume lớn | Redact, sanitize và log metadata |

## 30. Quy trình đọc YAML không tin cậy

Một pipeline có thể được tổ chức như sau:

```text
YAML từ client / file / message
             |
             v
Ingress
- xác thực nguồn
- giới hạn body bytes
- timeout / rate limit
             |
             v
SnakeYAML LoaderOptions
- code point limit
- alias limit
- nesting depth
- duplicate key policy
             |
             v
Jackson Core constraints
- token nesting
- string/number length
             |
             v
Jackson Databind
- DTO cụ thể
- subtype allowlist
- unknown/trailing token policy
             |
             v
Application
- giới hạn item/key/document
- Bean Validation
- business rules
- batch/backpressure
             |
             v
Lưu trữ / xử lý downstream
- log metadata đã redact
- error report có giới hạn
```

Mỗi bước cần một giới hạn đo được và một cách xử lý lỗi. Nếu payload vượt body limit, dừng trước khi parse. Nếu vượt parser limit, không tiếp tục binding. Nếu vượt record limit, dừng stream. Nếu DTO hợp lệ nhưng vi phạm nghiệp vụ, trả lỗi domain tương ứng.

## 31. Checklist cấu hình

- [ ] Giới hạn byte body ở gateway/HTTP server/file upload.
- [ ] Không dựa riêng vào `Content-Length`.
- [ ] Đặt SnakeYAML `codePointLimit` theo payload hợp lệ lớn nhất.
- [ ] Đặt `maxAliasesForCollections` theo nhu cầu anchor/alias.
- [ ] Đặt `nestingDepthLimit` ở version SnakeYAML hỗ trợ.
- [ ] Từ chối duplicate mapping key nếu contract không cần duplicate.
- [ ] Tắt recursive key nếu không có use case rõ ràng.
- [ ] Đặt Jackson `StreamReadConstraints` cho depth/string/number khi YAML parser version hỗ trợ.
- [ ] Quy định một document hay nhiều document; giới hạn document count.
- [ ] Giới hạn số item/key và dùng streaming cho file lớn.
- [ ] Dùng DTO cụ thể, không nhận class name tùy ý.
- [ ] Giữ polymorphic subtype allowlist và fail khi type ID lạ.
- [ ] Không dùng custom deserializer để gọi database/network hoặc thực hiện side effect.
- [ ] Chạy Bean Validation và business validation sau binding.
- [ ] Giới hạn số lỗi được tích lũy trong import report.
- [ ] Giới hạn timeout, concurrency, queue và batch size.
- [ ] Không log raw YAML hoặc secret.
- [ ] Kiểm thử payload vượt từng ngưỡng trên version thư viện thực tế.

## 32. Ghi nhớ

Đọc YAML không tin cậy cần giới hạn tài nguyên ở nhiều tầng. SnakeYAML `LoaderOptions` kiểm soát code point, alias, nesting và duplicate key; Jackson Core `StreamReadConstraints` có thể giới hạn token depth, string và number; ingress phải giới hạn byte; application phải giới hạn số document, key, item, batch và lỗi được tích lũy.

Không dựa vào Bean Validation để ngăn parser tạo collection quá lớn, không deserialize file lớn thành một list nếu có thể streaming, và không cho payload quyết định class Java tùy ý. Hãy cấu hình `YAMLFactory` với options tường minh, dùng DTO và subtype allowlist, kiểm thử các payload vượt giới hạn và log metadata đã được làm sạch. Khi mỗi lớp có ngưỡng rõ ràng, ứng dụng có thể đọc YAML linh hoạt mà vẫn kiểm soát được bộ nhớ, CPU và thời gian xử lý.
