# Vai trò của module YAML và YAMLMapper

Jackson thường được dùng để đọc và ghi JSON, nhưng mô hình dữ liệu của Jackson không giới hạn ở JSON text. Jackson được tổ chức thành các phần có trách nhiệm riêng: databind chuyển đổi giữa Java object và cấu trúc dữ liệu, core cung cấp API streaming, annotations mô tả quy tắc mapping, còn các module dataformat kết nối mô hình đó với những định dạng khác.

Module YAML là phần mở rộng giúp Jackson đọc và ghi tài liệu YAML. Lớp YAMLMapper cung cấp API quen thuộc giống ObjectMapper nhưng làm việc với YAML thay vì JSON. Nhờ đó, ứng dụng có thể dùng cùng DTO, annotation, serializer, deserializer và Tree Model để xử lý cả hai định dạng, trong khi parser/generator của YAML chịu trách nhiệm cú pháp YAML.

Điều cần hiểu là YAMLMapper không biến YAML thành một mô hình Java hoàn toàn khác. Nó kết nối cú pháp YAML với data model mà Jackson databind hiểu. Một mapping YAML thường trở thành object, sequence trở thành array, scalar trở thành string/number/boolean/null theo quy tắc phân tích của parser. Từ đó Jackson bind dữ liệu vào POJO, record, Map, List hoặc JsonNode.

Module YAML phù hợp khi hệ thống cần đọc file cấu hình, manifest, tài liệu tích hợp hoặc payload YAML. Nếu cần bảo toàn comment, quote style, anchor, alias và cách trình bày nguyên bản khi chỉnh sửa file, cần đánh giá thêm công cụ xử lý YAML chuyên dụng; databind chủ yếu bảo toàn ý nghĩa dữ liệu theo model chứ không phải mọi chi tiết văn bản nguồn.

## 1. Jackson được chia thành những phần nào?

Để hiểu vai trò YAML module, trước hết cần phân biệt các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| jackson-core | Streaming API, parser, generator và token |
| jackson-annotations | Annotation mô tả cách serialize/deserialize |
| jackson-databind | ObjectMapper, YAMLMapper integration, serializer/deserializer, Tree Model và data binding |
| jackson-dataformat-yaml | Parser/generator YAML và YAMLMapper |
| Các module datatype | Hỗ trợ kiểu Java bổ sung như Java Time, Optional |
| Các module dataformat khác | Kết nối CSV, XML, CBOR, Smile và định dạng khác |

Trong kiến trúc này, YAML module là adapter định dạng. Nó cung cấp cách đọc/ghi YAML cho Jackson, còn phần lớn quy tắc chuyển đổi Java object vẫn đến từ databind.

Ví dụ, một DTO có @JsonProperty, @JsonIgnore, @JsonCreator hoặc custom serializer có thể được dùng với YAMLMapper. Annotation vẫn mô tả property Java; YAML parser/generator quyết định property đó được biểu diễn trong cú pháp YAML.

~~~text
Java DTO / record / Map / JsonNode
                |
                v
          Jackson Databind
                |
                v
         YAMLFactory / YAMLMapper
                |
          +-----+------+
          |            |
          v            v
      YAMLParser   YAMLGenerator
          |            |
          v            v
       YAML text    YAML text
~~~

YAMLMapper là lựa chọn thuận tiện khi ứng dụng chủ yếu cần API databind. YAMLFactory hữu ích khi muốn cấu hình hoặc dùng trực tiếp parser/generator ở mức thấp hơn.

## 2. Module YAML và dependency cần có

Artifact phổ biến của Jackson YAML là jackson-dataformat-yaml, với package chính:

~~~java
com.fasterxml.jackson.dataformat.yaml
~~~

Trong Maven, dependency có dạng:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-yaml</artifactId>
</dependency>
~~~

Trong Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
~~~

Đoạn khai báo không ghi version khi dự án quản lý version qua Jackson BOM hoặc dependency management. Nếu không dùng BOM, cần khai báo version phù hợp theo chính sách build của dự án.

### 2.1. Đồng bộ version Jackson

Jackson gồm nhiều artifact có quan hệ phụ thuộc. YAML module cần tương thích với core và databind được ứng dụng sử dụng. Nên quản lý chúng bằng BOM của release line tương ứng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo module mà không lặp version:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

Không nên nâng riêng YAML module lên một version tùy ý trong khi core/databind vẫn ở release line khác. Hãy xem dependency tree để xác nhận version thực tế được resolve.

YAML module sử dụng thư viện parser YAML ở tầng dưới. Dependency graph cụ thể phụ thuộc phiên bản Jackson YAML module. Vì vậy, khi có security advisory liên quan YAML parser, cần kiểm tra cả dependency bắc cầu của YAML module chứ không chỉ các artifact có tiền tố jackson.

### 2.2. Kiểm tra dependency đã resolve

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.dataformat:jackson-dataformat-yaml
~~~

Gradle:

~~~bash
./gradlew dependencyInsight \
    --dependency jackson-dataformat-yaml \
    --configuration runtimeClasspath
~~~

Nếu ứng dụng đóng gói fat JAR hoặc container, kiểm tra artifact cuối để xác nhận module và parser dependency thực sự có mặt.

## 3. YAMLMapper là gì?

YAMLMapper là lớp mapper chuyên dùng cho YAML, thuộc package com.fasterxml.jackson.dataformat.yaml. Nó cung cấp API databind quen thuộc:

- readValue() để đọc YAML thành Java type.
- writeValueAsString() để ghi Java object thành YAML text.
- readTree() để đọc YAML thành JsonNode.
- treeToValue() để chuyển JsonNode thành Java type.
- valueToTree() để chuyển Java value thành JsonNode.
- readerFor() và writerFor() để tạo reader/writer theo kiểu cụ thể.

Ví dụ khởi tạo:

~~~java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

YAMLMapper yamlMapper = new YAMLMapper();
~~~

Sau đó có thể dùng tương tự ObjectMapper:

~~~java
AppConfig config = yamlMapper.readValue(
    yamlText,
    AppConfig.class
);

String output = yamlMapper.writeValueAsString(config);
~~~

YAMLMapper phù hợp khi phần lớn thao tác là binding giữa YAML và Java. Ứng dụng không cần tự đọc từng dòng hay tách key/value bằng String.

### 3.1. Dùng ObjectMapper với YAMLFactory

Một cách khác là tạo ObjectMapper với YAMLFactory:

~~~java
ObjectMapper yamlObjectMapper =
    new ObjectMapper(new YAMLFactory());
~~~

Cách này cho thấy rõ trách nhiệm: ObjectMapper cung cấp databind, còn YAMLFactory cung cấp parser/generator YAML.

YAMLMapper là API chuyên biệt, thuận tiện và diễn đạt ý định rõ hơn. YAMLFactory hữu ích khi cần tự cấu hình factory hoặc dùng trực tiếp Streaming API.

Không tạo một ObjectMapper JSON rồi kỳ vọng nó tự đọc YAML. Mapper dùng JsonFactory mặc định để đọc JSON; muốn đọc YAML cần factory/mapper dành cho YAML.

## 4. YAML và JSON khác nhau ở cú pháp

YAML biểu diễn các cấu trúc dữ liệu phổ biến bằng cú pháp dễ đọc hơn:

- Mapping tương tự object JSON.
- Sequence tương tự array JSON.
- Scalar tương tự string, number, boolean hoặc null.
- Indentation thể hiện quan hệ lồng nhau.
- Có thể dùng comment, block scalar, anchor và alias.

JSON:

~~~json
{
  "server": {
    "host": "localhost",
    "port": 8080
  },
  "features": [
    "search",
    "export"
  ]
}
~~~

YAML tương đương:

~~~yaml
server:
  host: localhost
  port: 8080
features:
  - search
  - export
~~~

Cả hai có thể ánh xạ thành cùng một Java model:

~~~java
public record ServerConfig(String host, int port) {}

public record AppConfig(
    ServerConfig server,
    List<String> features
) {}
~~~

YAMLMapper xử lý cú pháp YAML rồi dùng databind để tạo AppConfig. Code nghiệp vụ có thể làm việc với Java object mà không cần quan tâm dữ liệu ban đầu đến từ JSON hay YAML.

## 5. Đọc YAML thành POJO

Ví dụ file app-config.yaml:

~~~yaml
application:
  name: order-service
  environment: production

server:
  host: 0.0.0.0
  port: 8080

features:
  - order-search
  - invoice-export
~~~

DTO:

~~~java
public record ServerSettings(String host, int port) {}

public record ApplicationSettings(
    String name,
    String environment
) {}

public record AppConfig(
    ApplicationSettings application,
    ServerSettings server,
    List<String> features
) {}
~~~

Đọc file:

~~~java
YAMLMapper mapper = new YAMLMapper();

AppConfig config = mapper.readValue(
    Path.of("app-config.yaml").toFile(),
    AppConfig.class
);
~~~

Có thể đọc từ String:

~~~java
AppConfig config = mapper.readValue(yamlText, AppConfig.class);
~~~

Hoặc InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    AppConfig config = mapper.readValue(input, AppConfig.class);
}
~~~

Khi dùng InputStream, ứng dụng cần xác định ownership của stream. Ví dụ trên dùng try-with-resources để caller đóng stream sau khi đọc. Nếu parser/mapper được cấu hình đóng nguồn tự động, cần thống nhất ownership để tránh đóng hai lần hoặc đóng một stream mà caller còn cần dùng.

### 5.1. Tên property phải khớp hợp đồng

YAML key application, server, features phải tương ứng với property mà Jackson nhận diện trên DTO. Nếu Java field là applicationName nhưng YAML dùng application-name, có thể dùng @JsonProperty hoặc naming strategy.

~~~java
public record ApplicationSettings(
    @JsonProperty("application-name") String name,
    String environment
) {}
~~~

Nếu dự án dùng cùng DTO cho JSON và YAML, annotation Jackson giúp duy trì một contract mapping thống nhất. Tuy nhiên, tên property trên wire cần được test với cả hai mapper nếu hai định dạng có naming strategy khác nhau.

## 6. Ghi Java object thành YAML

YAMLMapper có thể serialize POJO, record, Map và collection thành YAML.

~~~java
AppConfig config = new AppConfig(
    new ApplicationSettings("order-service", "production"),
    new ServerSettings("0.0.0.0", 8080),
    List.of("order-search", "invoice-export")
);

YAMLMapper mapper = new YAMLMapper();

String yaml = mapper.writeValueAsString(config);
~~~

YAML output có thể có dạng:

~~~yaml
application:
  name: "order-service"
  environment: "production"
server:
  host: "0.0.0.0"
  port: 8080
features:
- "order-search"
- "invoice-export"
~~~

Cách trình bày cụ thể như quote, indentation hoặc document marker có thể phụ thuộc YAMLGenerator configuration và phiên bản module. Hợp đồng nên tập trung vào ý nghĩa dữ liệu trừ khi consumer yêu cầu định dạng văn bản chính xác.

Ghi ra file:

~~~java
try (Writer writer = Files.newBufferedWriter(
        Path.of("app-config.yaml"),
        StandardCharsets.UTF_8)) {

    mapper.writeValue(writer, config);
}
~~~

YAMLMapper ghi qua generator của Jackson. Không cần tự nối chuỗi key/value hoặc tự thêm dấu cách để biểu diễn indentation.

## 7. Dùng cùng annotation Jackson với YAMLMapper

Vì YAMLMapper dùng databind, nhiều annotation Jackson quen thuộc tiếp tục có tác dụng.

Ví dụ:

~~~java
public class UserConfig {

    @JsonProperty("display-name")
    private String displayName;

    @JsonIgnore
    private String internalToken;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String description;

    // Getters and setters
}
~~~

Khi serialize sang YAML:

- displayName được ghi theo tên display-name.
- internalToken bị bỏ qua.
- description null có thể không xuất hiện do NON_NULL.

Một số annotation thường dùng:

| Annotation | Vai trò |
|---|---|
| @JsonProperty | Đặt tên property |
| @JsonIgnore | Bỏ property khỏi mapping |
| @JsonInclude | Quy định điều kiện đưa property vào output |
| @JsonCreator | Chọn constructor/factory để tạo object |
| @JsonValue | Dùng một giá trị làm representation của object |
| @JsonUnwrapped | Làm phẳng property của object con |
| @JsonTypeInfo | Nhận diện subtype trong payload đa hình |
| @JsonIdentityInfo | Biểu diễn identity và reference của object |

Các annotation này mô tả mapping, không phải cú pháp riêng của JSON. Dù vậy, output YAML vẫn có thể khác JSON về scalar style hoặc cách parser suy luận kiểu. Test theo YAML text thực tế nếu consumer phụ thuộc các chi tiết đó.

## 8. Cấu hình module bổ sung như JavaTimeModule

YAMLMapper hỗ trợ đăng ký module databind bổ sung giống ObjectMapper.

Ví dụ DTO có Instant và LocalDate:

~~~java
public record DeploymentInfo(
    String version,
    Instant deployedAt,
    LocalDate releaseDate
) {}
~~~

Cấu hình:

~~~java
YAMLMapper mapper = new YAMLMapper();

mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Serialize:

~~~java
DeploymentInfo info = new DeploymentInfo(
    "2.4.0",
    Instant.parse("2026-11-12T08:30:00Z"),
    LocalDate.of(2026, 11, 12)
);

String yaml = mapper.writeValueAsString(info);
~~~

Với cấu hình ghi date/time dưới dạng string, output có thể tương tự:

~~~yaml
version: "2.4.0"
deployedAt: "2026-11-12T08:30:00Z"
releaseDate: "2026-11-12"
~~~

Cần thêm dependency Java Time module tương thích với Jackson release line. Đừng giả định YAML module tự cung cấp serializer cho mọi kiểu Java ngoài JDK cơ bản.

Nếu ứng dụng đã có ObjectMapper được cấu hình module dùng chung, có thể xây dựng YAMLMapper với cấu hình tương ứng hoặc đăng ký các module cần thiết cho YAML mapper. Không nên sửa mapper dùng chung sau khi đã bắt đầu xử lý request.

## 9. YAML scalar và vấn đề suy luận kiểu

YAML cho phép scalar không cần dấu quote:

~~~yaml
enabled: true
port: 8080
ratio: 0.75
name: order-service
description: null
~~~

Parser có thể suy luận các scalar này thành boolean, number, string hoặc null. Một số giá trị văn bản dễ bị hiểu nhầm:

~~~yaml
enabled: yes
maintenance: no
release: on
code: 00123
date: 2026-11-12
~~~

Quy tắc implicit scalar resolution có thể phụ thuộc YAML specification và phiên bản parser bên dưới. Đặc biệt, các từ như yes/no/on/off, chuỗi có số 0 đầu hoặc chuỗi trông giống ngày có thể được diễn giải khác nhau giữa công cụ YAML.

Nếu giá trị phải là string, hãy quote rõ:

~~~yaml
enabled: "yes"
maintenance: "no"
release: "on"
code: "00123"
date: "2026-11-12"
~~~

Nếu cần boolean hoặc number, dùng scalar có cú pháp không mơ hồ và kiểm thử bằng đúng YAMLMapper đang chạy production.

### 9.1. Identifier không nên bị hiểu thành number

Mã bưu chính, mã tài khoản, mã sản phẩm hoặc version có thể chỉ chứa chữ số nhưng không phải đại lượng để tính toán.

Ví dụ:

~~~yaml
postalCode: "00123"
accountCode: "0000456"
productCode: "000100"
~~~

Nếu bỏ quote, parser có thể hiểu scalar là số theo quy tắc của nó và làm mất số 0 đầu khi bind vào kiểu số. Hãy khai báo Java type là String và quote giá trị YAML.

### 9.2. Date-like scalar

Một scalar như 2026-11-12 có thể được parser nhận diện như date hoặc timestamp tùy YAML version/parser configuration. Nếu contract yêu cầu string, quote nó. Nếu contract muốn LocalDate, kiểm tra JavaTimeModule và behavior của parser cụ thể.

Không dựa vào việc một YAML editor tô màu scalar để kết luận Jackson sẽ bind kiểu gì.

## 10. Null, missing và empty trong YAML

YAML có thể biểu diễn null theo nhiều cách:

~~~yaml
a: null
b: ~
c:
~~~

Các dạng trên thường biểu diễn null theo quy tắc YAML. Property bị bỏ hoàn toàn lại là một trạng thái khác:

~~~yaml
name: An
~~~

Trong ví dụ này không có property description.

Giá trị rỗng cũng khác null:

~~~yaml
description: ""
tags: []
metadata: {}
~~~

| YAML | Ý nghĩa |
|---|---|
| Không có key | Missing property |
| key: null | Explicit null |
| key: ~ | Null shorthand |
| key: | Thường là null scalar |
| key: "" | String rỗng |
| key: [] | Sequence rỗng |
| key: {} | Mapping rỗng |

Ý nghĩa cuối cùng trong Java còn phụ thuộc target type, constructor, default value, @JsonInclude và deserialization configuration.

Với cấu hình cần phân biệt missing và null, không nên chỉ dựa vào một field Java nullable nếu cả hai trường hợp đều được bind thành null. Có thể dùng JsonNode, presence wrapper hoặc custom deserializer để giữ semantics cần thiết.

## 11. Đọc YAML thành JsonNode

YAMLMapper có thể đọc YAML vào Jackson Tree Model:

~~~java
String yaml = """
    server:
      host: localhost
      port: 8080
    features:
      - search
      - export
    """;

JsonNode root = mapper.readTree(yaml);
~~~

Truy cập:

~~~java
String host = root.path("server").path("host").asText();
int port = root.path("server").path("port").asInt();

JsonNode features = root.path("features");
~~~

Nếu cần sửa tree:

~~~java
ObjectNode object = (ObjectNode) root;
object.put("environment", "test");

ArrayNode featureArray = (ArrayNode) object.path("features");
featureArray.add("metrics");
~~~

Tree Model phù hợp khi schema có phần động hoặc cần kiểm tra key trước khi bind DTO.

### 11.1. Tree Model là model dữ liệu, không phải bản sao văn bản YAML

Khi đọc YAML thành JsonNode, ứng dụng làm việc với cấu trúc JSON-like của Jackson. Những chi tiết trình bày như comment, quote style, block scalar style, anchor/alias và indentation không được bảo đảm bảo toàn khi ghi lại.

Ví dụ YAML:

~~~yaml
# Endpoint used by internal health checks
health:
  url: 'https://service.example/health'
~~~

Sau khi parse và ghi lại bằng YAMLMapper, comment hoặc kiểu quote có thể không còn giống nguồn. Nếu mục tiêu là chỉnh sửa file cấu hình của người dùng mà vẫn giữ comment và format, hãy chọn YAML parser/editor có khả năng round-trip syntax tree và giữ trivia/comment.

### 11.2. Dùng valueToTree() với YAMLMapper

valueToTree() tạo JsonNode từ Java value theo serializer của mapper. Node đó là Jackson Tree Model, không phải một đối tượng YAML-specific.

~~~java
ObjectNode tree = mapper.valueToTree(config);
tree.put("generatedBy", "deployment-tool");
~~~

Sau đó có thể ghi tree thành YAML:

~~~java
String yaml = mapper.writeValueAsString(tree);
~~~

Đây là cách tiện khi cần thêm metadata vào payload trước khi phát hành YAML.

## 12. Streaming API qua YAMLFactory

Nếu cần đọc từng token thay vì bind toàn bộ document, có thể lấy factory của YAMLMapper:

~~~java
YAMLMapper mapper = new YAMLMapper();
YAMLFactory factory = mapper.getFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        // Xử lý token theo cấu trúc YAML đã được parser chuẩn hóa.
    }
}
~~~

Dù nguồn là YAML, parser vẫn cung cấp JsonToken của Jackson. Các token như START_OBJECT, FIELD_NAME, VALUE_STRING, VALUE_NUMBER_INT, START_ARRAY và END_ARRAY cho phép tái sử dụng nhiều logic Streaming API.

Điều này không có nghĩa mọi YAML syntax đều có token JSON tương ứng. YAML có tag, anchor, alias, comment và các biểu diễn đặc thù; parser phải chuyển chúng theo khả năng và quy tắc của module. Nếu ứng dụng phụ thuộc vào chi tiết YAML-specific, hãy kiểm tra API riêng của YAML module và version đang dùng.

### 12.1. Khi nào dùng streaming?

Streaming phù hợp khi:

- Tài liệu lớn và không cần giữ toàn bộ object tree.
- Muốn xử lý record theo từng phần.
- Cần kiểm soát thứ tự token.
- Cần dừng sớm khi tìm thấy thông tin.
- Muốn giảm bộ nhớ so với bind toàn bộ tài liệu.

Với file cấu hình nhỏ hoặc vừa, YAMLMapper.readValue() thường dễ hiểu và dễ bảo trì hơn.

## 13. YAML document, nhiều tài liệu và dấu phân cách

YAML cho phép một stream chứa nhiều document, thường được phân cách bằng marker:

~~~yaml
---
name: development
port: 8080
---
name: production
port: 8443
~~~

Một lần gọi readValue() thông thường được thiết kế để bind một root value. Nếu input có nhiều document, không nên giả định một lần readValue() sẽ tự trả về List của tất cả document.

Nếu ứng dụng cần xử lý YAML stream nhiều document, hãy kiểm tra khả năng của phiên bản YAML module đang dùng và chọn API đọc sequence/MappingIterator hoặc parser loop phù hợp. Viết test với hai document, document cuối bị thiếu marker và trailing content để xác nhận behavior thực tế.

Nếu contract chỉ cho phép một document, hãy từ chối hoặc phát hiện nội dung dư theo chính sách rõ ràng. Đừng âm thầm bỏ qua document thứ hai.

## 14. YAMLMapper và YAMLFactory: chọn lớp nào?

| Thành phần | Dùng khi | Ví dụ |
|---|---|---|
| YAMLMapper | Binding POJO, record, Map, List và JsonNode | readValue(), writeValueAsString() |
| YAMLFactory | Tạo parser/generator và cấu hình format layer | createParser(), createGenerator() |
| JsonParser | Đọc token streaming từ YAML | nextToken(), getText() |
| JsonGenerator | Ghi token theo streaming API | writeStartObject(), writeStringField() |
| ObjectReader | Reader bất biến theo target type/configuration | readerFor(AppConfig.class) |
| ObjectWriter | Writer bất biến theo source type/configuration | writerFor(AppConfig.class) |

Ví dụ ObjectReader:

~~~java
ObjectReader reader = mapper.readerFor(AppConfig.class);

AppConfig config = reader.readValue(yamlText);
~~~

Ví dụ ObjectWriter:

~~~java
ObjectWriter writer = mapper.writerFor(AppConfig.class);

String yaml = writer.writeValueAsString(config);
~~~

ObjectReader/ObjectWriter hữu ích khi cùng mapper phục vụ nhiều schema hoặc nhiều cấu hình serialization. Chúng giúp giữ cấu hình theo operation mà không phải thay đổi ObjectMapper dùng chung.

## 15. Kiểm soát unknown property và validation

YAMLMapper dùng cơ chế databind nên các feature như FAIL_ON_UNKNOWN_PROPERTIES vẫn có ý nghĩa.

Ví dụ YAML có field mới:

~~~yaml
server:
  host: localhost
  port: 8080
  experimentalMode: true
~~~

Nếu DTO ServerSettings không có experimentalMode, mapper strict có thể báo lỗi. Có thể cấu hình tolerant:

~~~java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Nhưng không nên tắt globally chỉ để file cấu hình qua được. Với cấu hình điều khiển bảo mật, routing hoặc workflow, unknown property có thể là lỗi chính tả khiến ứng dụng chạy sai. Tùy hợp đồng, strict behavior thường hữu ích để phát hiện typo.

Sau khi binding, vẫn cần validation:

~~~java
public record ServerSettings(
    @NotBlank String host,
    @Min(1) @Max(65535) int port
) {}
~~~

Jackson đảm nhiệm parse và bind. Bean Validation kiểm tra ràng buộc field. Business validation kiểm tra quan hệ giữa các field, môi trường và chính sách vận hành.

## 16. YAML anchors và aliases

YAML hỗ trợ anchor và alias để tái sử dụng một node trong cùng tài liệu:

~~~yaml
defaults: &defaults
  retries: 3
  timeoutSeconds: 10

serviceA:
  <<: *defaults
  endpoint: https://a.example

serviceB:
  <<: *defaults
  endpoint: https://b.example
~~~

Cú pháp merge key và mức hỗ trợ có thể phụ thuộc YAML version và parser implementation. Không nên giả định mọi YAML consumer đều hỗ trợ giống nhau.

Khi YAMLMapper đọc tài liệu có anchor/alias, kết quả mapping phụ thuộc parser và cách module xử lý alias. Nếu ứng dụng dựa vào merge key hoặc alias, hãy tạo fixture kiểm thử với đúng phiên bản Jackson YAML module và parser dependency. Không dùng anchor như một cách thay thế schema hoặc reference model nếu các consumer khác không hỗ trợ.

Nếu cần ghi YAML với anchor và alias có ý nghĩa định dạng, cần xác nhận YAMLGenerator có hỗ trợ đúng yêu cầu. Databind thông thường có thể ghi ra cấu trúc dữ liệu đã mở rộng thay vì tái tạo anchor/alias ban đầu.

## 17. Block scalar và multiline string

YAML có thể biểu diễn chuỗi nhiều dòng bằng literal block scalar hoặc folded block scalar.

~~~yaml
literalText: |
  First line
  Second line
  Third line

foldedText: >
  This is a long
  paragraph that can
  be folded into text.
~~~

Hai cách này có semantics khác nhau về newline và folding. Khi bind vào String, parser tạo giá trị chuỗi theo quy tắc YAML; khi ghi lại, generator có thể chọn style khác.

Nếu nội dung có ý nghĩa chính xác như script, certificate, template hoặc câu lệnh, hãy test giá trị String sau deserialize và tránh chỉ so sánh cách hiển thị trong file.

Không dùng block scalar cho dữ liệu cần giữ nguyên byte sequence nếu contract không định nghĩa encoding/line ending rõ ràng.

## 18. Security khi đọc YAML không tin cậy

YAML là định dạng giàu tính năng hơn JSON. Tài liệu có thể có tag, alias, nesting sâu và scalar dài. Khi đọc input không tin cậy, cần quản lý parser version và giới hạn tài nguyên.

Thực hành tốt:

- Dùng phiên bản Jackson YAML module và parser dependency đã được vá.
- Theo dõi advisory của cả Jackson và YAML parser bắc cầu.
- Không cho phép type metadata tùy ý quyết định class Java được khởi tạo.
- Tránh bật default typing rộng trên dữ liệu bên ngoài.
- Giới hạn kích thước request/file.
- Giới hạn độ sâu nesting và độ dài token nếu version hỗ trợ.
- Kiểm tra behavior của alias/merge key với parser cụ thể.
- Không deserialize trực tiếp vào class tùy ý do payload lựa chọn.
- Dùng DTO allowlist với target type rõ ràng.
- Áp dụng timeout và giới hạn tài nguyên cho import lớn.

Ví dụ cấu hình parser constraints ở các phiên bản hỗ trợ:

~~~java
StreamReadConstraints constraints =
    StreamReadConstraints.builder()
        .maxNestingDepth(100)
        .maxStringLength(1_000_000)
        .maxNumberLength(1_000)
        .build();

YAMLFactory factory = YAMLFactory.builder()
    .streamReadConstraints(constraints)
    .build();

YAMLMapper mapper = new YAMLMapper(factory);
~~~

API builder và constraint support phụ thuộc phiên bản Jackson. Nếu version của dự án không có API trên, hãy dùng cơ chế giới hạn được phiên bản đó hỗ trợ và giới hạn kích thước input ở tầng transport.

Không xem việc parser chấp nhận YAML là bằng chứng tài liệu an toàn. Cần kiểm soát kiểu đích, parser implementation và dữ liệu đầu vào.

## 19. YAMLMapper không phải công cụ giữ nguyên source formatting

Một hiểu nhầm phổ biến là parse file YAML vào POJO, thay một field rồi ghi lại sẽ giữ nguyên toàn bộ file.

Ví dụ nguồn:

~~~yaml
# Public endpoint
endpoint: 'https://api.example/v1'

# Number of retries
retries: 3
~~~

Sau khi đọc thành POJO và serialize lại, comment có thể biến mất, quote style có thể đổi, indentation có thể khác và thứ tự field có thể phụ thuộc cấu trúc model/generator.

Lý do là YAMLMapper làm việc ở mức data model. Nó chuyển cú pháp thành giá trị rồi ghi một representation mới.

Chọn công cụ theo mục tiêu:

| Mục tiêu | Cách phù hợp |
|---|---|
| Đọc YAML thành cấu hình Java | YAMLMapper |
| Ghi YAML từ DTO | YAMLMapper |
| Kiểm tra key động | YAMLMapper + JsonNode |
| Xử lý token tuần tự | YAMLFactory + JsonParser |
| Chuyển đổi YAML sang JSON data model | YAMLMapper đọc tree, mapper JSON ghi tree |
| Sửa file và giữ comment/format/anchor | YAML round-trip editor/parser chuyên dụng |
| Thay một đoạn text đơn giản có format cố định | Text edit có kiểm tra, nếu không làm sai cú pháp |

Nếu file là cấu hình do con người duy trì và comment quan trọng, không nên round-trip qua POJO rồi ghi lại toàn bộ bằng YAMLMapper mà chưa xác nhận khả năng giữ source formatting.

## 20. Chuyển đổi YAML sang JSON và ngược lại

Vì YAMLMapper và ObjectMapper JSON cùng dùng JsonNode model, có thể chuyển một document YAML sang JSON mà không cần tạo DTO trung gian.

~~~java
YAMLMapper yamlMapper = new YAMLMapper();
ObjectMapper jsonMapper = new ObjectMapper();

JsonNode tree = yamlMapper.readTree(yamlText);

String json = jsonMapper
    .writerWithDefaultPrettyPrinter()
    .writeValueAsString(tree);
~~~

Chiều ngược lại:

~~~java
JsonNode tree = jsonMapper.readTree(jsonText);

String yaml = yamlMapper.writeValueAsString(tree);
~~~

Quá trình này chuyển data model. Nó không bảo toàn comment, quote style, anchor, alias hoặc các chi tiết cú pháp YAML ban đầu. Những scalar có cách diễn giải khác nhau giữa YAML và JSON cũng cần được kiểm tra.

Nếu mục tiêu là migration cấu hình, hãy test các giá trị đặc biệt như ngày, chuỗi số 0 đầu, boolean-like string, null và multiline string.

## 21. Đọc và ghi qua Spring hoặc framework

Nhiều framework tự cấu hình Jackson cho JSON nhưng không tự động bật YAML cho mọi endpoint. Việc có dependency jackson-dataformat-yaml không đồng nghĩa mọi HTTP request Content-Type YAML sẽ được chấp nhận.

Nếu ứng dụng cần nhận YAML qua HTTP:

- Cấu hình message converter/codec phù hợp.
- Chỉ cho phép Content-Type mà API công bố.
- Xác nhận mapper YAML dùng đúng modules và security settings.
- Kiểm tra response Content-Type và charset.
- Test request body thực tế qua framework adapter.
- Không giả định ObjectMapper JSON hiện có sẽ tự đọc YAML.

Với Spring MVC, việc thêm converter YAML phụ thuộc phiên bản Spring và cách cấu hình HttpMessageConverter. Hãy đăng ký converter sử dụng YAMLMapper/YAMLFactory theo đúng API của framework đang dùng. Với WebFlux, cần cấu hình codec tương ứng.

Nếu YAML chỉ được dùng để đọc file cấu hình nội bộ, thường không cần mở endpoint HTTP nhận YAML.

## 22. Kiểm thử YAMLMapper

Test nên kiểm tra cả binding và representation thực tế.

### 22.1. Đọc YAML thành POJO

~~~java
@Test
void readsYamlIntoConfig() throws Exception {
    String yaml = """
        server:
          host: localhost
          port: 8080
        features:
          - search
          - export
        """;

    AppConfig config = mapper.readValue(yaml, AppConfig.class);

    assertEquals("localhost", config.server().host());
    assertEquals(8080, config.server().port());
    assertEquals(List.of("search", "export"), config.features());
}
~~~

### 22.2. Ghi POJO thành YAML rồi đọc lại

~~~java
@Test
void writesAndReadsConfig() throws Exception {
    AppConfig source = sampleConfig();

    String yaml = mapper.writeValueAsString(source);

    AppConfig restored = mapper.readValue(yaml, AppConfig.class);

    assertEquals(source, restored);
}
~~~

Round-trip hữu ích nhưng chưa đủ để kiểm tra contract. Cần fixture YAML cố định được review độc lập.

### 22.3. Test scalar có thể bị suy luận sai

~~~java
@Test
void keepsIdentifierAsString() throws Exception {
    String yaml = """
        accountCode: "00123"
        enabledText: "yes"
        """;

    IdentifierConfig config =
        mapper.readValue(yaml, IdentifierConfig.class);

    assertEquals("00123", config.accountCode());
    assertEquals("yes", config.enabledText());
}
~~~

Test này bảo vệ identifier và text không bị hiểu thành số hoặc boolean.

### 22.4. Test null, missing và empty

~~~java
@Test
void distinguishesNullAndEmptyValues() throws Exception {
    JsonNode tree = mapper.readTree("""
        explicitNull: null
        emptyText: ""
        emptyList: []
        emptyMap: {}
        """);

    assertTrue(tree.path("explicitNull").isNull());
    assertEquals("", tree.path("emptyText").asText());
    assertTrue(tree.path("emptyList").isArray());
    assertEquals(0, tree.path("emptyList").size());
    assertTrue(tree.path("emptyMap").isObject());
}
~~~

Bổ sung fixture thiếu key để xác nhận missing khác explicit null theo contract.

### 22.5. Test parser constraints và input sai

Nếu ứng dụng đặt giới hạn nesting, string hoặc number, hãy có test xác nhận payload vượt giới hạn bị từ chối. Bổ sung test malformed YAML, sai indentation, unknown property, sai scalar type và alias/merge key nếu ứng dụng sử dụng.

Không assert thông báo lỗi nội bộ quá cụ thể nếu nó thay đổi theo parser version. Hãy kiểm tra lỗi được ánh xạ thành application error phù hợp.

## 23. Lỗi thường gặp khi dùng YAMLMapper

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| ObjectMapper JSON không đọc được YAML | Đang dùng JsonFactory mặc định | Dùng YAMLMapper hoặc ObjectMapper với YAMLFactory |
| Thiếu YAML module lúc runtime | Chỉ khai báo dependency ở test hoặc module khác | Kiểm tra runtimeClasspath và artifact |
| Jackson module lệch version | Không dùng BOM/constraints | Đồng bộ release line và kiểm tra dependency tree |
| String yes/no bị bind thành boolean | Implicit scalar resolution | Quote string và test parser version |
| Mã 00123 mất số 0 đầu | Identifier bị coi là number | Dùng String và quote YAML scalar |
| Date-like text bị diễn giải khác | Scalar resolution và timezone semantics | Quote hoặc khai báo format/type rõ |
| Comment biến mất sau khi ghi | Databind không bảo toàn source trivia | Dùng round-trip YAML editor |
| Một lần readValue chỉ đọc một document | Nhầm YAML stream nhiều document với một root value | Dùng API sequence phù hợp hoặc giới hạn một document |
| HTTP endpoint không nhận YAML | Framework chưa đăng ký YAML converter/codec | Cấu hình adapter theo framework |
| Alias hoặc merge key khác behavior mong muốn | Parser/version/spec khác nhau | Test fixture với parser thực tế |
| Payload YAML lớn gây tốn tài nguyên | Thiếu giới hạn request/parser | Đặt size, nesting, token và timeout limits |
| Unknown key bị bỏ qua | Mapper tolerant ngoài ý muốn | Chọn strict/tolerant policy theo contract |
| Ghi lại YAML làm đổi quote/indentation | Generator tạo representation mới | Không dùng YAMLMapper khi cần giữ nguyên format |

## 24. Quy trình chọn và sử dụng YAMLMapper

1. Xác định dữ liệu thực sự cần YAML hay JSON đã đủ.
2. Thêm jackson-dataformat-yaml ở runtime.
3. Đồng bộ Jackson core, databind và YAML module bằng BOM hoặc constraints.
4. Chọn YAMLMapper cho databind hoặc YAMLFactory cho Streaming API.
5. Đăng ký module cần thiết như JavaTimeModule.
6. Xác định DTO và property naming theo hợp đồng.
7. Quote rõ identifier và string dễ bị implicit scalar resolution.
8. Quy định missing, null, empty, unknown property và nhiều document.
9. Đọc/ghi bằng readValue(), writeValue(), readTree() hoặc Streaming API phù hợp.
10. Kiểm tra YAML output theo ý nghĩa dữ liệu, không phụ thuộc whitespace nếu không cần.
11. Đặt giới hạn input và dùng subtype allowlist khi deserialize dữ liệu không tin cậy.
12. Nếu cần giữ comment, anchor hoặc style, chọn công cụ round-trip syntax-aware.
13. Test bằng fixture YAML cố định với đúng mapper/parser production.
14. Kiểm tra runtime artifact và security advisory của cả YAML parser dependency.

## 25. Nguyên tắc nên giữ

- YAML module là adapter định dạng cho hệ sinh thái Jackson.
- YAMLMapper cung cấp databind API quen thuộc để đọc/ghi YAML.
- YAMLFactory cung cấp parser/generator ở tầng streaming.
- DTO và nhiều annotation Jackson có thể dùng lại giữa JSON và YAML.
- Cấu trúc YAML mapping, sequence và scalar được ánh xạ vào data model Jackson.
- Dùng đúng mapper/factory; ObjectMapper JSON mặc định không tự trở thành YAMLMapper.
- Đồng bộ version YAML module với core/databind và theo dõi parser dependency bắc cầu.
- Quote identifier và string dễ bị YAML implicit scalar resolution diễn giải khác.
- Phân biệt missing, null, empty string, empty list và empty mapping.
- Không giả định YAMLMapper giữ comment, quote style, anchor, alias hoặc indentation gốc.
- Xác định rõ một document hay nhiều document trong một stream.
- Cấu hình framework converter/codec nếu cần nhận YAML qua HTTP.
- Giới hạn tài nguyên và kiểm soát polymorphic deserialization với input không tin cậy.
- Dùng fixture và test với đúng version parser trong production.
- Chọn YAML round-trip editor nếu yêu cầu là sửa source mà giữ nguyên cách trình bày.

YAML module mở rộng Jackson để ứng dụng đọc và ghi YAML bằng cùng mô hình databind đã dùng cho JSON. YAMLMapper là lựa chọn thuận tiện cho POJO, record, Map, collection và JsonNode; YAMLFactory cho phép làm việc ở mức parser/generator. Khi hiểu rõ scalar resolution, version dependency, giới hạn bảo toàn source formatting và chính sách bảo mật, ứng dụng có thể dùng YAML như một định dạng trao đổi hoặc cấu hình mà vẫn giữ được quy tắc mapping nhất quán.

