# Kiểm tra phiên bản cú pháp và cấu hình parser YAML

Jackson xử lý YAML thông qua module riêng `jackson-dataformat-yaml`, dựa trên parser của SnakeYAML để đọc cú pháp YAML rồi đưa dữ liệu vào mô hình token của Jackson. Vì vậy, hành vi thực tế phụ thuộc ít nhất vào phiên bản Jackson, phiên bản SnakeYAML được resolve và các tùy chọn parser/loader được cấu hình.

Một file YAML có thể được parse thành công ở môi trường này nhưng cho kết quả khác ở môi trường khác nếu dependency tree, quy tắc phân giải scalar hoặc giới hạn alias khác nhau. Muốn dữ liệu ổn định, cần khóa phiên bản tương thích, công bố dialect được hỗ trợ, cấu hình duplicate key và resource limits, rồi kiểm thử bằng chính factory/mapper mà ứng dụng sử dụng.

## 1. Jackson đọc YAML qua những thành phần nào?

Trong Jackson Databind, YAML thường đi qua các thành phần:

- `jackson-dataformat-yaml`: tích hợp YAML với Jackson Core/Databind.
- `YAMLFactory`: tạo parser và generator cho YAML.
- `YAMLParser`: đọc event từ SnakeYAML và chuyển thành token mà Jackson hiểu.
- SnakeYAML: thực hiện việc phân tích cú pháp YAML ở tầng thấp.
- `ObjectMapper` hoặc `YAMLMapper`: ánh xạ token thành Java object và ngược lại.

Luồng đọc:

~~~text
YAML file / String / InputStream
              |
              v
        YAMLFactory
              |
              v
          YAMLParser
              |
              v
          SnakeYAML
              |
              v
     Jackson token stream
              |
              v
        ObjectMapper
              |
              v
          Java object
~~~

Jackson không tự định nghĩa toàn bộ grammar YAML. SnakeYAML xử lý cú pháp, còn Jackson Databind chịu trách nhiệm ánh xạ dữ liệu đã parse sang kiểu Java.

Điều này có nghĩa cấu hình `ObjectMapper` không thay thế cấu hình loader của SnakeYAML. Muốn kiểm soát duplicate key, alias hoặc giới hạn code point, cần cấu hình `LoaderOptions` khi tạo YAML factory.

## 2. Đồng bộ phiên bản Jackson và SnakeYAML

Các module Jackson nên được dùng cùng một release line/version. Ví dụ, `jackson-databind`, `jackson-core` và `jackson-dataformat-yaml` cần tương thích với nhau.

SnakeYAML thường được khai báo như dependency bắc cầu của `jackson-dataformat-yaml`. Phiên bản được resolve phụ thuộc vào POM của Jackson YAML module và dependency management của dự án.

Không nên nâng riêng SnakeYAML lên một major version mới chỉ bằng cách override dependency mà chưa kiểm tra Jackson YAML module đang dùng. SnakeYAML 2.x có thay đổi API và yêu cầu runtime so với một số dòng 1.x; module Jackson cũ có thể không tương thích với phiên bản bị ép mới.

### 2.1. Maven: dùng Jackson BOM

Ví dụ khai báo BOM để các module Jackson cùng phiên bản:

~~~xml
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

    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

Thay `2.x.y` bằng một release Jackson 2.x đã được dự án chọn và kiểm thử. Nếu ứng dụng dùng Jackson 3.x, cần dùng đúng BOM và tọa độ artifact của release line đó; không trộn module 2.x và 3.x.

### 2.2. Gradle: dùng platform

~~~groovy
dependencies {
    implementation platform("com.fasterxml.jackson:jackson-bom:2.x.y")
    implementation "com.fasterxml.jackson.core:jackson-databind"
    implementation "com.fasterxml.jackson.dataformat:jackson-dataformat-yaml"
}
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.x.y"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
~~~

Nếu source code tự import `org.yaml.snakeyaml.LoaderOptions`, SnakeYAML phải có mặt trên compile classpath. Dependency bắc cầu thường cung cấp nó, nhưng hãy xác định phiên bản thực tế bằng dependency insight và cân nhắc khai báo trực tiếp theo chính sách dependency management của dự án.

### 2.3. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.dataformat:jackson-dataformat-yaml,org.yaml:snakeyaml
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency snakeyaml --configuration runtimeClasspath
~~~

Cần xác nhận:

- Chỉ có một phiên bản SnakeYAML được chọn trong runtime classpath.
- Phiên bản Jackson YAML module phù hợp với Jackson Core/Databind.
- Không có dependency khác ép SnakeYAML xuống phiên bản cũ hoặc lên phiên bản không tương thích.
- CI và production resolve cùng dependency lock/BOM như môi trường phát triển.

Không chỉ nhìn version khai báo trong build file; dependency mediation có thể chọn phiên bản khác với điều developer dự định.

## 3. YAML 1.1 và YAML 1.2 có khác biệt về scalar

YAML có nhiều quy tắc implicit typing. Một scalar không đặt trong dấu nháy có thể được parser diễn giải thành boolean, null hoặc number dựa trên cú pháp và schema/resolver.

SnakeYAML classic được Jackson YAML module sử dụng có quy tắc tương thích YAML 1.1 ở nhiều trường hợp. Không nên giả định rằng chỉ vì tài liệu ghi `%YAML 1.2` thì mọi scalar sẽ tự động được phân giải theo YAML 1.2.

Một khác biệt thường gặp:

~~~yaml
enabled: on
approved: yes
disabled: off
answer: true
~~~

Theo quy tắc YAML 1.1, các từ như `on`, `off`, `yes`, `no` có thể được nhận diện như boolean. Trong YAML 1.2 core schema, boolean được giới hạn vào `true` và `false`; các từ `on`, `off`, `yes`, `no` thường là string.

Nếu ứng dụng mong muốn giá trị là string, hãy đặt trong dấu nháy:

~~~yaml
enabled: "on"
approvalWord: "yes"
mode: "off"
~~~

Nếu muốn boolean, dùng cú pháp rõ ràng:

~~~yaml
enabled: true
disabled: false
~~~

### 3.1. Điều khiển các từ boolean kiểu YAML 1.1

Một số phiên bản Jackson YAML cung cấp `YAMLParser.Feature.PARSE_BOOLEAN_LIKE_WORDS_AS_STRINGS`. Khi bật, các từ `yes`, `no`, `on`, `off` được đọc như String thay vì boolean, trong khi `true` và `false` vẫn là boolean:

~~~java
YAMLFactory factory = YAMLFactory.builder()
    .enable(YAMLParser.Feature.PARSE_BOOLEAN_LIKE_WORDS_AS_STRINGS)
    .build();
~~~

Feature này hữu ích khi cần tương thích với file cấu hình có các giá trị như `on` hoặc `yes` mang ý nghĩa chuỗi. Nó không biến parser thành một implementation YAML 1.2 đầy đủ và cũng không thay thế việc đặt nháy trong tài liệu mới. Chỉ dùng nếu phiên bản `jackson-dataformat-yaml` đang khóa có feature này; hãy kiểm tra Javadoc và test bằng mapper production.

### 3.2. Các scalar dễ gây nhầm lẫn

| YAML không đặt nháy | Có thể được phân giải thành | Cách viết rõ ý |
|---|---|---|
| `true`, `false` | Boolean | `true`, `false` |
| `yes`, `no`, `on`, `off` | Boolean theo resolver YAML 1.1 | Đặt nháy nếu muốn String |
| `null`, `~` | Null | Đặt nháy nếu muốn String |
| `0123` | Có thể bị hiểu theo quy tắc số YAML 1.1 | Đặt nháy nếu là mã định danh |
| `0xFF` | Integer dạng hexadecimal | Đặt nháy nếu là chuỗi |
| `1.25e3` | Number | Đặt nháy nếu là mã hoặc text |
| `2026-11-12` | Có thể được resolver nhận diện là dạng timestamp/date | Đặt nháy nếu là text thuần |

Với dữ liệu cấu hình, các giá trị như version string, account code, postal code, ID có số 0 ở đầu và tên trạng thái nên được đặt trong dấu nháy nếu không muốn parser diễn giải thành kiểu khác.

### 3.3. Không dựa vào YAML directive để thay resolver

YAML có thể chứa directive như:

~~~yaml
%YAML 1.2
---
enabled: on
~~~

Nhưng không nên coi directive là một cách portable để buộc mọi thư viện, phiên bản SnakeYAML và cấu hình Jackson dùng cùng một scalar schema. Hãy kiểm tra hành vi của parser thực tế. Nếu contract yêu cầu YAML 1.2 strict, cần chọn parser/engine hỗ trợ đúng schema đó và kiểm thử riêng; Jackson YAML module dùng SnakeYAML classic không nên được mặc định xem là một triển khai YAML 1.2 đầy đủ.

## 4. Tạo YAMLFactory và ObjectMapper

Cấu hình cơ bản:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

YAMLFactory factory = YAMLFactory.builder().build();
ObjectMapper mapper = new ObjectMapper(factory);
~~~

Có thể dùng `YAMLMapper` nếu muốn API mapper chuyên cho YAML:

~~~java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

YAMLMapper mapper = new YAMLMapper();
~~~

Cấu hình factory trước khi tạo parser/mapper. Factory giữ chính sách parser cho các parser được tạo từ nó; không nên thay đổi chính sách trong lúc nhiều request đang sử dụng cùng factory.

Nếu ứng dụng có nhiều loại input khác nhau, có thể tạo factory riêng cho từng contract thay vì dùng một cấu hình global không phân biệt nguồn dữ liệu.

## 5. Cấu hình LoaderOptions cho SnakeYAML

`LoaderOptions` điều khiển các quy tắc và giới hạn của SnakeYAML loader. Jackson YAML factory có thể nhận options này khi được xây dựng.

Ví dụ:

~~~java
import org.yaml.snakeyaml.LoaderOptions;

import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

LoaderOptions loaderOptions = new LoaderOptions();

loaderOptions.setAllowDuplicateKeys(false);
loaderOptions.setMaxAliasesForCollections(20);
loaderOptions.setCodePointLimit(2_000_000);

YAMLFactory factory = YAMLFactory.builder()
    .loaderOptions(loaderOptions)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Ba thiết lập trên giải quyết ba nhóm vấn đề:

- `setAllowDuplicateKeys(false)`: từ chối mapping có key lặp.
- `setMaxAliasesForCollections(20)`: giới hạn số alias tham chiếu đến collection.
- `setCodePointLimit(2_000_000)`: giới hạn số code point được xử lý cho một tài liệu theo quy tắc của SnakeYAML.

Các giá trị số chỉ là ví dụ. Chọn limit theo kích thước và cấu trúc YAML hợp lệ của ứng dụng.

Tên API và khả năng cấu hình phụ thuộc phiên bản SnakeYAML được Jackson YAML module sử dụng. Nếu một method không có trong compile classpath, hãy kiểm tra dependency tree và tài liệu của đúng phiên bản thay vì ép một SnakeYAML version không tương thích vào runtime.

## 6. Từ chối duplicate keys

YAML mapping được kỳ vọng có key duy nhất. Tuy nhiên, nếu parser cho phép key trùng, một document như sau có thể gây ra kết quả không rõ ràng:

~~~yaml
user:
  role: viewer
  role: admin
~~~

Một consumer có thể giữ giá trị đầu, consumer khác giữ giá trị cuối hoặc parser có thể báo lỗi tùy cấu hình. Sự khác nhau này đặc biệt nguy hiểm với cấu hình bảo mật: một lớp kiểm tra có thể thấy `viewer`, trong khi lớp xử lý sau cùng dùng `admin`.

Đặt:

~~~java
loaderOptions.setAllowDuplicateKeys(false);
~~~

để yêu cầu parser từ chối duplicate mapping keys.

Ví dụ:

~~~java
String yaml = """
    user:
      role: viewer
      role: admin
    """;

mapper.readValue(yaml, UserConfig.class);
~~~

Với duplicate key, quá trình parse nên thất bại thay vì âm thầm chọn một giá trị. Hãy kiểm thử behavior trên phiên bản SnakeYAML thực tế vì exception type/message có thể thay đổi theo phiên bản.

Không nhầm setting này với `StreamReadFeature.STRICT_DUPLICATE_DETECTION` của Jackson Core. Strict duplicate detection là cơ chế ở tầng token parser cho các format Jackson hỗ trợ; với YAML, quy tắc duplicate mapping key của SnakeYAML được kiểm soát qua LoaderOptions.

## 7. Giới hạn anchors và aliases

YAML hỗ trợ anchor và alias để tái sử dụng một node:

~~~yaml
defaults: &defaults
  timeout: 30
  retries: 3

serviceA:
  <<: *defaults
  endpoint: https://a.example

serviceB:
  <<: *defaults
  endpoint: https://b.example
~~~

Anchor `&defaults` đặt tên cho node; alias `*defaults` tham chiếu lại node đó. YAML merge key `<<` cũng thường được dùng để kế thừa mapping.

Alias hữu ích cho cấu hình lớn, nhưng một tài liệu có nhiều alias hoặc cấu trúc tham chiếu phức tạp có thể làm parser phải xử lý nhiều node và tiêu tốn tài nguyên. Các cấu trúc alias lồng nhau còn có thể tạo ra dữ liệu mở rộng đáng kể sau khi được xử lý.

Dùng:

~~~java
loaderOptions.setMaxAliasesForCollections(20);
~~~

để giới hạn số alias collection được chấp nhận theo quy tắc của SnakeYAML. Giá trị quá thấp có thể từ chối cấu hình hợp lệ; giá trị quá cao làm giảm hiệu quả bảo vệ. Hãy đặt theo nhu cầu thật và có test cho cấu hình lớn nhất được hỗ trợ.

Không bật alias vô hạn chỉ để một file cấu hình phức tạp parse thành công. Nếu một ứng dụng không cần anchor/alias, có thể đặt giới hạn thấp và chuẩn hóa config để giảm khả năng lạm dụng.

## 8. Giới hạn kích thước tài liệu

`setCodePointLimit` giới hạn số code point mà SnakeYAML xử lý cho tài liệu. Đây là một hàng rào bảo vệ cho input lớn, nhưng không thay thế giới hạn request ở tầng HTTP hoặc file upload.

~~~java
loaderOptions.setCodePointLimit(2_000_000);
~~~

Cần có thêm các giới hạn ở tầng ứng dụng:

- Kích thước file hoặc HTTP body tính theo byte.
- Thời gian đọc và timeout.
- Số lượng document trong một stream.
- Số entry trong mapping và số phần tử trong sequence.
- Độ sâu cấu trúc lồng nhau.
- Số lượng alias và độ phức tạp của graph.
- Kích thước string/number nếu phiên bản parser hỗ trợ giới hạn tương ứng.

Code point không giống byte. Một ký tự Unicode có thể chiếm nhiều byte trong UTF-8 nhưng là một code point. Vì vậy, giới hạn code point của SnakeYAML và giới hạn byte của HTTP server bảo vệ hai lớp khác nhau.

## 9. Cấu hình YAMLParser.Feature

Ngoài `LoaderOptions`, Jackson YAML module có các feature riêng của parser. Một feature thường gặp là:

~~~java
YAMLFactory factory = YAMLFactory.builder()
    .enable(YAMLParser.Feature.EMPTY_STRING_AS_NULL)
    .build();
~~~

`EMPTY_STRING_AS_NULL` điều khiển việc diễn giải empty YAML string/scalar như null trong parser. Hành vi này ảnh hưởng đến cách dữ liệu đi vào Databind, nên chỉ bật khi hợp đồng cấu hình muốn empty value có semantics null.

Cần phân biệt các trường hợp:

~~~yaml
missingValue:
explicitNull: null
emptyString: ""
quotedText: "null"
~~~

- `explicitNull` rõ ràng là null.
- `emptyString` là chuỗi rỗng được đặt nháy.
- `quotedText` là chuỗi gồm bốn ký tự "null".
- `missingValue` là empty/plain scalar; cách parser biểu diễn có thể phụ thuộc feature và phiên bản.

Không bật `EMPTY_STRING_AS_NULL` toàn cục nếu ứng dụng cần phân biệt chuỗi rỗng với null. Hãy kiểm tra output token và object thực tế bằng test với đúng phiên bản module.

Các feature parser khác có thể được thêm ở những release Jackson YAML khác nhau. Trước khi sử dụng, hãy xem Javadoc của đúng version `jackson-dataformat-yaml`; không sao chép một feature từ ví dụ trên mạng rồi giả định mọi release đều có.

## 10. Phân biệt parser feature và generator feature

YAMLFactory tạo cả parser để đọc và generator để ghi. Feature của hai phía có ý nghĩa khác nhau.

| Nhóm | Ví dụ | Ảnh hưởng |
|---|---|---|
| LoaderOptions | `setAllowDuplicateKeys(false)` | Cú pháp và giới hạn khi đọc |
| YAMLParser.Feature | `EMPTY_STRING_AS_NULL` | Cách parser chuyển event/scalar thành token |
| YAMLGenerator.Feature | `WRITE_DOC_START_MARKER` | Cách generator phát ra YAML |
| Jackson Databind feature | `FAIL_ON_UNKNOWN_PROPERTIES` | Cách ánh xạ token thành Java object |

Ví dụ generator có thể ghi marker document:

~~~java
YAMLFactory factory = YAMLFactory.builder()
    .enable(YAMLGenerator.Feature.WRITE_DOC_START_MARKER)
    .build();
~~~

Feature này ảnh hưởng output YAML như marker `---`; nó không thay đổi cú pháp parser chấp nhận khi đọc.

Tương tự, `MINIMIZE_QUOTES` hoặc các tùy chọn quote trong generator chỉ ảnh hưởng cách ghi scalar. Không dùng generator feature để cố sửa vấn đề implicit typing khi đọc input.

## 11. YAML document marker và multi-document stream

YAML có thể chứa một hoặc nhiều document trong cùng stream. Marker thường gặp:

- `---`: bắt đầu document.
- `...`: kết thúc document một cách tường minh.

Ví dụ:

~~~yaml
---
name: service-a
port: 8080
---
name: service-b
port: 8081
~~~

Nếu contract chỉ cho phép một document, hãy từ chối input có thêm root document hoặc trailing content theo cấu hình parser/mapper phù hợp. Có thể kiểm tra trailing token bằng `DeserializationFeature.FAIL_ON_TRAILING_TOKENS` nếu phiên bản Jackson YAML hỗ trợ đúng behavior cần dùng.

Nếu contract cho phép nhiều document, phải đọc và xử lý từng document theo một vòng đời rõ ràng. Không giả định `readValue(...)` một lần sẽ tự trả về một List chứa mọi YAML document.

Ví dụ khái niệm:

~~~java
try (JsonParser parser = factory.createParser(input)) {
    while (parser.nextToken() != null) {
        ConfigDocument document =
            mapper.readValue(parser, ConfigDocument.class);

        process(document);
    }
}
~~~

Cách xử lý nhiều root document phụ thuộc behavior của YAMLParser và Jackson version. Hãy kiểm thử với marker, document rỗng và document cuối bị cắt. Nếu ứng dụng không cần multi-document, contract một document đơn giản và dễ kiểm soát hơn.

## 12. YAML tags và schema ứng dụng

YAML có cú pháp tag tường minh, ví dụ:

~~~yaml
createdAt: !!str 2026-11-12
amount: !!float 12.50
~~~

Tag cung cấp thông tin kiểu cho node theo quy tắc YAML. Jackson YAML module chuyển dữ liệu từ SnakeYAML sang mô hình token của Jackson; không nên giả định mọi custom tag đều được chuyển thành Java type theo cách ứng dụng mong muốn.

Nếu file cấu hình có custom tag:

- Xác định parser version có hỗ trợ tag đó không.
- Xác định Jackson YAML module giữ, bỏ qua hay từ chối tag.
- Không cho tag bên ngoài quyết định class Java tùy ý.
- Kiểm thử tag trên parser production.
- Ưu tiên schema YAML đơn giản, portable giữa các công cụ.

Nếu cần mapping custom tag sang kiểu nghiệp vụ, dùng một bước chuyển đổi/validation có allowlist. Không dựa vào tag tự do để kích hoạt reflection hoặc khởi tạo class không được phép.

## 13. Dùng YAML parser với ObjectMapper và DTO

Sau khi cấu hình factory, Databind hoạt động tương tự JSON:

~~~java
public class ServiceConfig {
    private String name;
    private int port;
    private boolean enabled;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

YAML:

~~~yaml
name: payments
port: 8080
enabled: true
~~~

Đọc:

~~~java
ServiceConfig config = mapper.readValue(yamlText, ServiceConfig.class);
~~~

Các quy tắc Databind như naming strategy, unknown property handling, custom deserializer và validation vẫn áp dụng. Cần tách bạch lỗi cú pháp YAML với lỗi ánh xạ sang DTO:

- Lỗi cú pháp phát sinh ở YAML parser/SnakeYAML.
- Lỗi kiểu/property phát sinh ở Jackson Databind.
- Lỗi nghiệp vụ cần được kiểm tra sau khi object đã tạo.

## 14. Xác thực cấu hình sau khi parse

Parse thành công chỉ có nghĩa tài liệu hợp lệ theo cú pháp parser và có thể ánh xạ theo kiểu đích. Nó không có nghĩa cấu hình hợp lệ cho ứng dụng.

Ví dụ:

~~~yaml
name: payments
port: -1
enabled: true
~~~

YAML này có thể parse và bind thành object, nhưng port âm không hợp lệ.

Có thể dùng Bean Validation hoặc kiểm tra ở tầng cấu hình:

~~~java
if (config.getPort() < 1 || config.getPort() > 65535) {
    throw new IllegalArgumentException("port is outside valid range");
}
~~~

Với cấu hình bảo mật, cần kiểm tra thêm:

- URL/host có nằm trong allowlist không.
- Timeout có nằm trong range không.
- Path file có nằm trong thư mục cho phép không.
- Credential có được lấy từ secret manager thay vì ghi trực tiếp vào YAML không.
- Property không biết có bị từ chối hay được giữ theo contract.
- Giá trị mặc định có được áp dụng rõ ràng không.

Không dùng parse success làm validation duy nhất.

## 15. Cấu hình parser hoàn chỉnh cho một ứng dụng

Ví dụ dưới đây tạo factory với duplicate-key detection và giới hạn alias/document size:

~~~java
import org.yaml.snakeyaml.LoaderOptions;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

public final class YamlMappers {
    private YamlMappers() {
    }

    public static ObjectMapper createConfigMapper() {
        LoaderOptions options = new LoaderOptions();
        options.setAllowDuplicateKeys(false);
        options.setMaxAliasesForCollections(20);
        options.setCodePointLimit(2_000_000);

        YAMLFactory factory = YAMLFactory.builder()
            .loaderOptions(options)
            .build();

        return new ObjectMapper(factory);
    }
}
~~~

Đây là một chính sách khởi đầu. Trước khi dùng production, xác định rõ:

- Jackson release và SnakeYAML version được resolve.
- YAML dialect/scalar resolution mà file cấu hình phải tuân theo.
- Có cho phép aliases, merge keys và multi-document không.
- Duplicate key có bị từ chối không.
- Giới hạn code point/alias có phù hợp dữ liệu thật không.
- Unknown properties trong DTO bị fail hay được bỏ qua.
- Parser error có được log mà không in toàn bộ file cấu hình không.

Không chia sẻ một mapper được cấu hình khác nhau tùy request. Hãy tạo mapper/factory theo contract ổn định và tái sử dụng sau khi cấu hình hoàn chỉnh.

## 16. Kiểm thử behavior của parser theo version

Nên có test nhỏ khóa các behavior quan trọng thay vì chỉ kiểm tra một file YAML lớn có parse được.

### 16.1. Kiểm tra scalar resolution

~~~java
@Test
void documentsBooleanLikeScalarBehavior() throws Exception {
    JsonNode node = mapper.readTree("""
        enabled: on
        label: "on"
        explicitBoolean: true
        """);

    // Assertion phải phản ánh dialect/resolver đã chọn
    // của SnakeYAML version mà ứng dụng khóa.
}
~~~

Nếu parser phát ra kiểu boolean cho `on`, test cần thể hiện rõ đó là behavior mà contract đang chấp nhận hay cần tránh bằng cách yêu cầu producer đặt nháy.

### 16.2. Kiểm tra duplicate key

~~~java
@Test
void rejectsDuplicateMappingKeys() {
    String yaml = """
        user:
          role: viewer
          role: admin
        """;

    assertThrows(
        Exception.class,
        () -> mapper.readValue(yaml, UserConfig.class)
    );
}
~~~

Trong test production, thay `Exception.class` bằng exception cụ thể mà phiên bản SnakeYAML/Jackson đang dùng phát ra nếu cần kiểm tra loại lỗi.

### 16.3. Kiểm tra alias limit

Tạo YAML có số alias vượt giới hạn cấu hình và xác nhận parser từ chối. Đồng thời có test cho số alias hợp lệ để tránh cấu hình quá chặt làm hỏng file thật.

### 16.4. Kiểm tra multi-document và trailing content

Nếu chỉ cho phép một document, xác nhận parser/mapper từ chối document thứ hai. Nếu cho phép nhiều document, xác nhận từng document được đọc độc lập và document cuối bị cắt được đánh dấu lỗi.

### 16.5. Chạy test trên dependency tree production

Test phải dùng cùng BOM, dependency lock và YAMLFactory builder như ứng dụng. Một test chạy với SnakeYAML version khác không chứng minh behavior ở production.

## 17. Nâng cấp Jackson hoặc SnakeYAML

Khi nâng version, kiểm tra theo từng lớp:

1. Release notes của Jackson YAML module.
2. Dependency tree để biết SnakeYAML version mới.
3. API của `LoaderOptions` và YAMLFactory builder.
4. Thay đổi resolver/implicit scalar typing.
5. Duplicate key và alias behavior.
6. Multi-document, tag, anchor và merge key behavior.
7. Exception type/message và vị trí lỗi.
8. Giới hạn resource và hiệu năng trên file đại diện.

Không chỉ chạy test deserialize happy path. Cấu hình YAML có thể là dữ liệu production tồn tại lâu năm; một thay đổi resolver có thể đổi kiểu của scalar mà không làm parser ném lỗi.

Nếu cần nâng SnakeYAML để nhận bản vá bảo mật, hãy nâng theo một tổ hợp Jackson YAML module tương thích. Không giữ một phiên bản parser cũ chỉ vì file cấu hình hiện tại parse được; cũng không ép major version mới mà không kiểm tra compatibility.

## 18. Các lỗi thường gặp

**Chỉ khai báo jackson-dataformat-yaml mà không kiểm tra dependency tree.** Một dependency khác có thể ép SnakeYAML về phiên bản không mong muốn.

**Cho rằng YAML 1.2 directive bảo đảm YAML 1.2 core schema.** Resolver thực tế của SnakeYAML classic có thể dùng quy tắc YAML 1.1 cho scalar.

**Để mã định danh không đặt nháy.** Các giá trị như `on`, `yes`, `00123`, `0xFF` hoặc chuỗi giống ngày có thể bị diễn giải thành kiểu khác.

**Cho phép duplicate key.** Consumer có thể hiểu giá trị khác nhau hoặc một field cấu hình bảo mật bị ghi đè.

**Không giới hạn alias.** YAML anchor/alias có thể làm tăng độ phức tạp và tài nguyên xử lý.

**Chỉ giới hạn code point mà quên body size và timeout.** Giới hạn parser không thay thế giới hạn transport.

**Dùng parser feature để điều khiển generator.** `EMPTY_STRING_AS_NULL` là behavior đọc; `WRITE_DOC_START_MARKER` là behavior ghi.

**Cho rằng ObjectMapper tự xác thực cấu hình nghiệp vụ.** Parse và bind thành công vẫn có thể tạo port âm, URL không được phép hoặc timeout quá lớn.

**Nâng riêng SnakeYAML major version.** Jackson YAML module có thể phụ thuộc API cụ thể; nâng theo tổ hợp tương thích và test lại.

**Log toàn bộ YAML khi parse lỗi.** File cấu hình có thể chứa password, token hoặc endpoint nội bộ. Log request ID, source name đã chuẩn hóa và vị trí lỗi; không in raw document.

## 19. Ghi nhớ

- Jackson YAML module dùng `YAMLFactory`/`YAMLParser` và dựa vào SnakeYAML để đọc cú pháp.
- Giữ `jackson-core`, `jackson-databind` và `jackson-dataformat-yaml` trên cùng release line; kiểm tra SnakeYAML version thực tế trong dependency tree.
- SnakeYAML classic có các quy tắc scalar tương thích YAML 1.1 ở nhiều trường hợp; không giả định YAML 1.2 semantics chỉ từ directive.
- Đặt nháy cho identifier/text dễ bị implicit typing như `on`, `yes`, `00123`, `0xFF` hoặc chuỗi giống ngày.
- Dùng `LoaderOptions` để từ chối duplicate keys và giới hạn aliases/code points.
- `YAMLParser.Feature` điều khiển cách đọc; `YAMLGenerator.Feature` điều khiển cách ghi; Databind feature điều khiển ánh xạ object.
- Quyết định rõ có hỗ trợ anchors, aliases, merge keys và multi-document stream hay không.
- Giới hạn parser cần đi cùng giới hạn byte body, timeout và giới hạn ở tầng ứng dụng.
- Parse thành công không thay thế validation nghiệp vụ hoặc kiểm tra property không biết.
- Khi nâng Jackson/SnakeYAML, kiểm thử scalar resolution, duplicate key, aliases, document boundaries và error handling bằng dependency tree production.

