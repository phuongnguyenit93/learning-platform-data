# Lựa chọn dependency cho JSON và cho các định dạng mở rộng

Khi dùng Jackson, việc chọn dependency phụ thuộc vào hai câu hỏi: ứng dụng cần **API nào để đọc/ghi dữ liệu**, và cần **định dạng dữ liệu nào**. JSON đã được hỗ trợ trực tiếp bởi Jackson Core và Jackson Databind; các định dạng như XML, YAML, CSV, CBOR hay Smile cần module tương ứng. Ngoài ra, những kiểu Java như `LocalDateTime` hoặc `Optional` có module hỗ trợ riêng, nhưng đó là mở rộng kiểu dữ liệu chứ không phải định dạng mới.

Chọn đúng dependency giúp classpath gọn, tránh xung đột phiên bản và làm rõ khả năng dữ liệu mà ứng dụng thực sự cần.

## 1. Hiểu các lớp dependency trong hệ sinh thái Jackson

Jackson được chia thành nhiều module. Ba module nền tảng thường gặp nhất trong ứng dụng xử lý JSON là Core, Annotations và Databind.

| Module | Maven artifact (Jackson 2.x) | Trách nhiệm |
|---|---|---|
| Core | `com.fasterxml.jackson.core:jackson-core` | Đọc và ghi JSON theo luồng token; cung cấp parser, generator và factory |
| Annotations | `com.fasterxml.jackson.core:jackson-annotations` | Cung cấp annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonFormat` |
| Databind | `com.fasterxml.jackson.core:jackson-databind` | Ánh xạ JSON với đối tượng Java và mô hình cây `JsonNode` |

Có thể hình dung mối quan hệ thường gặp như sau:

```text
Ứng dụng
   |
   +-- ObjectMapper / JsonNode
   |       |
   |       +-- jackson-databind
   |               |
   |               +-- jackson-core
   |               +-- jackson-annotations
   |
   +-- JsonParser / JsonGenerator (nếu dùng streaming trực tiếp)
           |
           +-- jackson-core
```

`jackson-databind` phụ thuộc vào Core và Annotations. Vì vậy, khi chỉ cần `ObjectMapper`, khai báo `jackson-databind` thường đã đưa các module nền tảng cần thiết vào dependency graph.

### 1.1. Chọn Databind khi cần ánh xạ object với JSON

Đây là lựa chọn phổ biến cho REST API, DTO, file JSON và thông điệp giữa các dịch vụ.

```java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(user);
User restored = mapper.readValue(json, User.class);
```

Dependency chính:

```groovy
implementation("com.fasterxml.jackson.core:jackson-databind")
```

Không cần tìm một artifact riêng có tên `jackson-dataformat-json` cho trường hợp thông thường. JSON là định dạng nền tảng mà Jackson Core hỗ trợ; Databind xây dựng khả năng ánh xạ object trên nền tảng đó.

### 1.2. Chọn Core khi chỉ cần streaming API

Nếu ứng dụng xử lý dữ liệu lớn theo từng token, không cần tạo toàn bộ object graph hoặc cây `JsonNode`, có thể dùng Core trực tiếp.

```java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();
        // Xử lý từng token tại đây
    }
}
```

Dependency:

```groovy
implementation("com.fasterxml.jackson.core:jackson-core")
```

Streaming giúp đọc/ghi tuần tự và kiểm soát bộ nhớ tốt hơn trong một số workload. Đổi lại, ứng dụng phải tự điều khiển việc đi qua token và ánh xạ dữ liệu; không có trải nghiệm data binding đầy đủ như `ObjectMapper`.

### 1.3. Khi nào cần khai báo Annotations?

Nếu ứng dụng sử dụng các annotation Jackson trong mã nguồn, chẳng hạn `@JsonProperty` hoặc `@JsonIgnore`, dependency Annotations là phần API mà mã nguồn đang tham chiếu.

```groovy
implementation("com.fasterxml.jackson.core:jackson-annotations")
```

Khi đã khai báo Databind, Annotations thường có mặt qua dependency bắc cầu. Tuy vậy, trong dự án coi annotation là dependency trực tiếp của mã nguồn, có thể khai báo rõ artifact này và để BOM quản lý phiên bản. Không cần tự thêm cả ba artifact nền tảng một cách máy móc nếu ứng dụng chỉ dùng `ObjectMapper`.

## 2. Dependency cho những kiểu Java thường gặp

Một số kiểu dữ liệu của Java cần module hỗ trợ riêng để Jackson ánh xạ đúng ý nghĩa.

| Nhu cầu | Artifact (Jackson 2.x) | Ghi chú |
|---|---|---|
| `java.time`: `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` | `com.fasterxml.jackson.datatype:jackson-datatype-jsr310` | Cung cấp `JavaTimeModule` |
| Các kiểu JDK 8 như `Optional`, `OptionalInt` | `com.fasterxml.jackson.datatype:jackson-datatype-jdk8` | Cung cấp hỗ trợ cho các kiểu thuộc JDK 8 |
| Tên tham số constructor | `com.fasterxml.jackson.module:jackson-module-parameter-names` | Hữu ích khi data binding qua constructor có tham số và metadata tương ứng |
| Kotlin data class, nullability và constructor Kotlin | `com.fasterxml.jackson.module:jackson-module-kotlin` | Chỉ thêm trong ứng dụng Kotlin |

Ví dụ với Java Time:

```groovy
implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
```

Trong ứng dụng Java thuần, đăng ký module với mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Sau đó Jackson có thể xử lý các kiểu `java.time` theo quy tắc của module. Việc tắt `WRITE_DATES_AS_TIMESTAMPS` trong ví dụ này khiến ngày giờ được ghi theo dạng văn bản thay vì dạng số/mảng theo cấu hình mặc định tương ứng.

**Datatype module không phải dataformat module.** `jackson-datatype-jsr310` mở rộng cách ánh xạ kiểu `LocalDateTime` trong JSON, YAML hoặc định dạng khác có hỗ trợ data binding. Nó không tạo ra một định dạng file mới.

## 3. Dependency cho các định dạng mở rộng

JSON là định dạng mặc định. Khi cần đọc/ghi định dạng khác, thêm dataformat module tương ứng và sử dụng mapper hoặc factory của module đó.

| Định dạng | Artifact (Jackson 2.x) | API thường dùng | Trường hợp phù hợp |
|---|---|---|---|
| XML | `com.fasterxml.jackson.dataformat:jackson-dataformat-xml` | `XmlMapper` | Tích hợp hệ thống dùng XML, tài liệu có element/attribute/namespace |
| YAML | `com.fasterxml.jackson.dataformat:jackson-dataformat-yaml` | `YAMLMapper`, `YAMLFactory` | File cấu hình hoặc dữ liệu dạng cây cần dễ đọc |
| CSV | `com.fasterxml.jackson.dataformat:jackson-dataformat-csv` | `CsvMapper`, `CsvSchema` | Dữ liệu bảng với hàng và cột |
| CBOR | `com.fasterxml.jackson.dataformat:jackson-dataformat-cbor` | `CBORFactory` | Biểu diễn nhị phân gọn theo mô hình dữ liệu CBOR |
| Smile | `com.fasterxml.jackson.dataformat:jackson-dataformat-smile` | `SmileFactory` | Biểu diễn nhị phân theo định dạng Smile của Jackson |

### 3.1. XML

Thêm module XML:

```groovy
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
```

Sử dụng `XmlMapper`:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();

String xml = xmlMapper.writeValueAsString(user);
User restored = xmlMapper.readValue(xml, User.class);
```

XML có khái niệm element, attribute và namespace. Cấu trúc XML không hoàn toàn tương đương object JSON, vì vậy các mô hình XML đặc thù có thể cần annotation hoặc cấu hình riêng. Không nên giả định rằng mọi JSON DTO đều tự động tạo ra XML đúng hợp đồng của hệ thống bên ngoài.

### 3.2. YAML

Thêm module YAML:

```groovy
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
```

Ví dụ:

```java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

YAMLMapper yamlMapper = new YAMLMapper();

String yaml = yamlMapper.writeValueAsString(user);
User restored = yamlMapper.readValue(yaml, User.class);
```

YAML thường được chọn cho file cấu hình hoặc tài liệu cần con người đọc và chỉnh sửa. Module YAML có dependency parser YAML bắc cầu; hãy để BOM quản lý các phiên bản tương thích và chỉ ghi đè parser khi có lý do cụ thể.

### 3.3. CSV

Thêm module CSV:

```groovy
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-csv")
```

CSV là định dạng bảng nên việc ánh xạ cần quan tâm đến schema cột:

```java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

CsvMapper csvMapper = new CsvMapper();

CsvSchema schema = csvMapper.schemaFor(User.class)
    .withHeader();

String csv = csvMapper.writer(schema)
    .writeValueAsString(users);
```

Schema quyết định tên và thứ tự cột, cũng như việc có ghi header hay không. CSV phù hợp với danh sách bản ghi phẳng; cấu trúc lồng nhau hoặc quan hệ phức tạp cần được chuyển thành mô hình bảng phù hợp trước khi ghi.

### 3.4. CBOR và Smile

Hai định dạng này biểu diễn dữ liệu theo dạng nhị phân. Chúng hữu ích khi hệ thống cần định dạng máy đọc và không yêu cầu payload có thể mở bằng trình soạn thảo văn bản thông thường.

CBOR:

```java
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;

ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());

byte[] bytes = cborMapper.writeValueAsBytes(user);
User restored = cborMapper.readValue(bytes, User.class);
```

Smile:

```java
import com.fasterxml.jackson.dataformat.smile.SmileFactory;

ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());

byte[] bytes = smileMapper.writeValueAsBytes(user);
User restored = smileMapper.readValue(bytes, User.class);
```

Dependency tương ứng là `jackson-dataformat-cbor` và `jackson-dataformat-smile`. Cần thống nhất định dạng ở cả phía ghi và phía đọc; không thể gửi byte CBOR hoặc Smile cho bên nhận đang chờ JSON văn bản.

## 4. Khai báo dependency theo từng hệ build

Các ví dụ dưới đây sử dụng tọa độ Maven của Jackson 2.x (`com.fasterxml.jackson.*`). Hãy chọn phiên bản phù hợp với JDK, framework và các thư viện còn lại trong ứng dụng. Không sao chép một số phiên bản ngẫu nhiên vào từng dependency.

### 4.1. Maven: dùng Jackson BOM

BOM (Bill of Materials) quản lý tập phiên bản tương thích của các module Jackson. BOM không tự thêm thư viện vào ứng dụng; nó chỉ cung cấp phiên bản để các dependency được khai báo bên dưới sử dụng.

```xml
<properties>
    <jackson.version>2.x.y</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- JSON object binding -->
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <!-- Java Time types -->
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>

    <!-- YAML, chỉ thêm nếu ứng dụng thực sự dùng YAML -->
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
```

Thay `2.x.y` bằng một phiên bản Jackson 2.x cụ thể đã được dự án lựa chọn. Khi thêm XML, CSV, CBOR hoặc Smile, khai báo artifact tương ứng mà không phải lặp lại version nếu BOM đã quản lý nó.

### 4.2. Gradle Groovy DSL: dùng Jackson BOM

```groovy
def jacksonVersion = providers.gradleProperty("jacksonVersion").get()

dependencies {
    implementation(platform(
        "com.fasterxml.jackson:jackson-bom:${jacksonVersion}"
    ))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")

    // Chỉ thêm module định dạng khi có nhu cầu
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
```

Có thể đặt phiên bản trong `gradle.properties`:

```properties
jacksonVersion=2.x.y
```

Gradle `platform(...)` đưa các quy tắc phiên bản từ BOM vào dependency resolution. Những dependency Jackson cùng nằm trong BOM sẽ được căn chỉnh theo bộ phiên bản đã chọn.

### 4.3. Spring Boot: ưu tiên dependency management của Boot

Khi ứng dụng dùng Spring Boot, starter web thông thường đã đưa hỗ trợ JSON/Jackson vào dependency graph thông qua các starter liên quan. Ví dụ:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Chỉ thêm nếu ứng dụng cần ánh xạ XML
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
}
```

Trong dự án đã dùng Spring Boot dependency management, nên để BOM của phiên bản Boot đang chạy quản lý các module Jackson. Khi thêm một dataformat module, thường chỉ cần khai báo artifact và không tự gắn version riêng.

Nếu dự án dùng Gradle native BOM thay cho plugin quản lý dependency, có thể import BOM `spring-boot-dependencies` theo phiên bản Boot đang dùng. Không nên đồng thời ép nhiều BOM hoặc khai báo version thủ công nếu chưa xác định rõ quy tắc ưu tiên của Gradle/Maven.

Điều quan trọng là không nâng riêng `jackson-databind` trong khi `jackson-core`, `jackson-annotations` và các module mở rộng vẫn do một bộ phiên bản khác quản lý. Một ứng dụng có thể biên dịch nhưng lỗi ở runtime do API không tương thích.

## 5. Phân biệt Jackson 2.x và Jackson 3.x khi chọn tọa độ

Các ví dụ dependency và import trong bài này minh họa dòng Jackson 2.x, vốn dùng tọa độ Maven `com.fasterxml.jackson.*` và package Java quen thuộc như `com.fasterxml.jackson.databind`.

Jackson 3.x là major line riêng, có thay đổi namespace/package và tọa độ artifact sang hệ `tools.jackson.*` ở các module tương ứng. Vì vậy:

- Không ghép dependency Jackson 2.x và Jackson 3.x trong cùng một cấu hình như thể chúng là các module cùng phiên bản.
- Chọn BOM thuộc đúng major line và dùng các artifact/module được phát hành cho major line đó.
- Khi nâng major version, đọc hướng dẫn migration và kiểm tra các API, annotation, module datatype/dataformat mà ứng dụng đang dùng.
- Nếu Spring Boot hoặc framework khác đang quản lý Jackson, xác định major line do framework chọn trước khi thêm module mới.

Tên class và package trong mã nguồn cũng phải khớp với major line. Việc chỉ đổi version số mà giữ nguyên mọi tọa độ và import có thể không đủ khi chuyển từ Jackson 2 sang Jackson 3.

## 6. Chọn dependency theo nhu cầu thực tế

Có thể dùng bảng quyết định sau để bắt đầu:

| Nhu cầu | Dependency nên khai báo |
|---|---|
| Dùng `ObjectMapper` để đọc/ghi JSON | `jackson-databind` |
| Đọc/ghi JSON theo token, không cần data binding | `jackson-core` |
| Mã nguồn trực tiếp dùng annotation Jackson | `jackson-annotations` (thường đã có bắc cầu qua Databind) |
| Xử lý `LocalDate`, `LocalDateTime`, `Instant` | `jackson-datatype-jsr310` |
| Xử lý `Optional` của JDK 8 | `jackson-datatype-jdk8` |
| Đọc/ghi XML | `jackson-dataformat-xml` |
| Đọc/ghi YAML | `jackson-dataformat-yaml` |
| Đọc/ghi CSV | `jackson-dataformat-csv` |
| Đọc/ghi CBOR | `jackson-dataformat-cbor` |
| Đọc/ghi Smile | `jackson-dataformat-smile` |

Một cấu hình tối thiểu cho REST API dùng JSON và kiểu ngày giờ Java có thể chỉ cần Databind cùng Java Time module. Nếu ứng dụng chỉ đọc JSON theo luồng, Core là lựa chọn phù hợp hơn. Chỉ thêm dataformat module khi có đầu vào/đầu ra thuộc định dạng đó.

Không nên thêm toàn bộ module chỉ vì "có thể sẽ cần". Mỗi dependency bổ sung làm tăng dependency graph, bề mặt cập nhật bảo mật và khả năng phát sinh xung đột phiên bản.

## 7. Kiểm tra dependency graph và lỗi thường gặp

Sau khi khai báo, cần xác nhận phiên bản thực tế mà build đã chọn.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson
```

Khi kiểm tra, chú ý các điểm sau:

1. `jackson-core`, `jackson-annotations`, `jackson-databind`, datatype và dataformat module có nằm trên major line tương thích không.
2. Có framework hoặc thư viện khác kéo một phiên bản Jackson khác vào không.
3. Có khai báo version thủ công ghi đè BOM ngoài ý muốn không.
4. Module định dạng có thật sự được dùng bằng mapper/factory tương ứng không.
5. Dependency có đúng scope không: mã nguồn dùng API thường cần `implementation` (Gradle) hoặc scope mặc định phù hợp trong Maven; tránh để thư viện cần lúc chạy chỉ nằm trong test scope.

### Các lỗi cấu hình thường gặp

**Chỉ thêm `jackson-core` nhưng lại import `ObjectMapper`.** `ObjectMapper` thuộc Databind. Hãy thêm `jackson-databind` hoặc dùng Core API đúng với nhu cầu streaming.

**Tự khai báo nhiều version khác nhau.** Ví dụ Databind ở một phiên bản nhưng Core hoặc YAML ở phiên bản khác. Hãy dùng Jackson BOM hoặc dependency management của framework để căn chỉnh.

**Đã dùng Spring Boot starter nhưng thêm lại toàn bộ Jackson không cần thiết.** Kiểm tra dependency graph trước; starter có thể đã cung cấp Databind và các module nền tảng.

**Thêm module YAML nhưng vẫn tạo mapper JSON mặc định.** Dependency chỉ đưa khả năng vào classpath; mã nguồn cần dùng `YAMLMapper` hoặc `YAMLFactory` để đọc/ghi YAML.

**Nhầm datatype với dataformat.** Java Time module hỗ trợ kiểu `LocalDateTime`; YAML module hỗ trợ cú pháp YAML. Hai module giải quyết hai chiều mở rộng khác nhau và có thể cùng được dùng trong một ứng dụng.

**Nâng riêng một module để xử lý CVE hoặc lỗi runtime.** Hãy xem advisory, phiên bản framework và BOM trước khi nâng. Cập nhật một module Jackson đơn lẻ có thể tạo ra tổ hợp phiên bản không được kiểm thử cùng nhau.

## 8. Nguyên tắc lựa chọn

- Bắt đầu từ API cần dùng: streaming hay object binding.
- Chọn định dạng theo hợp đồng dữ liệu: JSON, XML, YAML, CSV hay một định dạng nhị phân.
- Bổ sung datatype module khi mô hình Java có kiểu cần hỗ trợ đặc biệt.
- Quản lý toàn bộ phiên bản Jackson bằng một BOM hoặc BOM của framework.
- Tôn trọng major line mà framework đang sử dụng; không trộn Jackson 2.x và 3.x.
- Kiểm tra dependency graph và thử đọc/ghi một payload đại diện cho từng định dạng trước khi đưa vào luồng nghiệp vụ.

Lựa chọn dependency tốt là lựa chọn phản ánh đúng khả năng ứng dụng cần, có phiên bản nhất quán và tạo ra classpath dễ hiểu, dễ bảo trì.

