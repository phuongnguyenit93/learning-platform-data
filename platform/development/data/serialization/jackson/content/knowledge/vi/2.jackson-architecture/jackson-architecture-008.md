# Phân biệt tính năng lõi và phần mở rộng theo định dạng

Jackson thường được giới thiệu như thư viện xử lý JSON cho Java. Tuy nhiên, hệ sinh thái Jackson còn có các module cho những định dạng dữ liệu khác như YAML, XML, CSV hoặc các định dạng nhị phân. Để hiểu cách mở rộng này, cần phân biệt **năng lực xử lý dữ liệu lõi** với **module hỗ trợ một định dạng cụ thể**.

Phần lõi cung cấp cơ chế đọc, ghi và ánh xạ dữ liệu. Module theo định dạng cung cấp cách đọc hoặc ghi biểu diễn cụ thể, chẳng hạn YAML hay XML, để cơ chế ánh xạ có thể làm việc với định dạng đó. Nhờ cách tổ chức này, ứng dụng có thể tái sử dụng mô hình Java và nhiều quy tắc ánh xạ mà không phải tự viết lại toàn bộ logic cho từng định dạng.

## 1. Vì sao Jackson có phần lõi và phần mở rộng?

Một ứng dụng Java có thể cần trao đổi dữ liệu trong nhiều tình huống:

- REST API trao đổi JSON với trình duyệt hoặc ứng dụng di động.
- Công cụ vận hành đọc cấu hình YAML.
- Hệ thống tích hợp cũ trao đổi XML.
- Quy trình nhập/xuất dữ liệu dạng bảng dùng CSV.
- Hai dịch vụ cần một biểu diễn nhị phân gọn hơn văn bản.

Các định dạng này có cú pháp và quy tắc biểu diễn khác nhau. JSON tổ chức dữ liệu bằng object và array; XML có element, attribute và namespace; CSV biểu diễn dữ liệu dạng hàng và cột; YAML có cú pháp cấu trúc thân thiện với cấu hình; Smile và CBOR là các định dạng nhị phân.

Nếu mỗi định dạng buộc ứng dụng phải tự viết một cơ chế chuyển đổi object riêng, code sẽ lặp lại nhiều phần như xác định property, chuyển kiểu dữ liệu, tạo object và xử lý lỗi. Jackson tách phần ánh xạ dùng chung khỏi phần xử lý cú pháp riêng của từng định dạng để giảm sự lặp lại đó.

## 2. Phần lõi của Jackson đảm nhiệm việc gì?

Trong cách tổ chức Jackson 2.x thường gặp, ba artifact nền tảng có vai trò như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `jackson-core` | Cung cấp nền tảng streaming để đọc và ghi JSON qua parser, generator và token. |
| `jackson-annotations` | Cung cấp metadata như `@JsonProperty`, `@JsonIgnore`, `@JsonCreator` để mô tả quy tắc liên hệ giữa kiểu Java và dữ liệu. |
| `jackson-databind` | Ánh xạ dữ liệu với kiểu Java qua `ObjectMapper`, tree model `JsonNode`, serializer và deserializer. |

JSON là định dạng được hỗ trợ trực tiếp bởi core mặc định. Với ứng dụng thông thường, bạn có thể dùng `ObjectMapper` để chuyển object Java sang JSON và ngược lại mà không cần tự điều khiển token.

Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;

record Product(String code, BigDecimal price) {}

public class JsonExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        Product product = new Product("P-100", new BigDecimal("49.90"));

        String json = mapper.writeValueAsString(product);
        Product restored = mapper.readValue(json, Product.class);

        System.out.println(json);
        System.out.println(restored.price());
    }
}
```

`ObjectMapper` là API cấp cao. Nó sử dụng cơ chế đọc/ghi JSON của core và cơ chế ánh xạ của databind. Nếu cần kiểm soát thấp hơn, ứng dụng có thể sử dụng trực tiếp `JsonParser` và `JsonGenerator` từ `jackson-core`.

## 3. Phần mở rộng theo định dạng là gì?

Phần mở rộng theo định dạng thường được cung cấp qua các module có tên `jackson-dataformat-*`. Những module này bổ sung parser/generator hoặc factory phù hợp với cú pháp của định dạng tương ứng. Databind có thể sử dụng các thành phần đó để ánh xạ dữ liệu với kiểu Java.

Một số module thường gặp:

| Định dạng | Artifact trong Jackson 2.x | API thường gặp | Đặc điểm dữ liệu |
| --- | --- | --- | --- |
| YAML | `jackson-dataformat-yaml` | `YAMLMapper`, `YAMLFactory` | Cấu trúc dữ liệu dễ đọc, thường dùng cho cấu hình. |
| XML | `jackson-dataformat-xml` | `XmlMapper`, `XmlFactory` | Có element, attribute, namespace và các quy tắc XML riêng. |
| CSV | `jackson-dataformat-csv` | `CsvMapper`, `CsvSchema` | Dữ liệu dạng bảng, thường cần schema để mô tả cột và header. |
| Smile | `jackson-dataformat-smile` | `SmileFactory` | Biểu diễn nhị phân theo mô hình dữ liệu tương tự JSON. |
| CBOR | `jackson-dataformat-cbor` | `CBORFactory` | Định dạng nhị phân có cấu trúc, phù hợp với một số hệ thống trao đổi dữ liệu. |

Tên class cụ thể và khả năng của từng module phụ thuộc phiên bản. Các ví dụ trong bài dùng cách API phổ biến của dòng Jackson 2.x; khi triển khai, hãy theo phiên bản được dependency management của dự án quản lý.

Phần mở rộng không làm cho mọi định dạng trở nên giống hệt JSON. Nó cung cấp cầu nối để Jackson xử lý cú pháp của định dạng đó. Những đặc trưng riêng của XML, CSV hoặc định dạng nhị phân vẫn cần được hiểu và cấu hình phù hợp.

## 4. Ví dụ: dùng cùng mô hình Java với YAML

Giả sử ứng dụng có record:

```java
import java.math.BigDecimal;

public record Product(String code, BigDecimal price) {}
```

Với module YAML, ứng dụng có thể dùng `YAMLMapper` để ghi và đọc dữ liệu:

```java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

import java.math.BigDecimal;

public class YamlExample {
    public static void main(String[] args) throws Exception {
        YAMLMapper mapper = new YAMLMapper();

        Product product = new Product("P-100", new BigDecimal("49.90"));

        String yaml = mapper.writeValueAsString(product);
        Product restored = mapper.readValue(yaml, Product.class);

        System.out.println(yaml);
        System.out.println(restored.code());
    }
}
```

Ý tưởng ánh xạ vẫn quen thuộc: object Java được chuyển thành biểu diễn dữ liệu và có thể được đọc lại thành `Product`. Điểm khác biệt nằm ở mapper/factory xử lý định dạng YAML. Ứng dụng cần thêm module `jackson-dataformat-yaml` vào dependency để sử dụng `YAMLMapper`.

Nếu dùng Gradle và dự án đã quản lý phiên bản Jackson bằng BOM hoặc dependency management, khai báo có thể ở dạng:

```groovy
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
```

Nếu dự án không quản lý phiên bản tập trung, cần khai báo phiên bản tương thích với các artifact Jackson còn lại. Không nên tùy tiện ghép các phiên bản khác dòng vì có thể dẫn đến lỗi tương thích ở runtime hoặc khi biên dịch.

## 5. Các định dạng khác có đặc điểm riêng

### 5.1. XML: có cấu trúc riêng ngoài object và array

`jackson-dataformat-xml` cung cấp `XmlMapper` để ánh xạ XML với kiểu Java. Cách gọi ở mức khái quát tương tự:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper mapper = new XmlMapper();

String xml = mapper.writeValueAsString(product);
Product restored = mapper.readValue(xml, Product.class);
```

Tuy nhiên, XML có nhiều khái niệm không tương đương trực tiếp với JSON, như attribute, namespace, element lặp và mixed content. Vì vậy, khi làm việc với XML, có thể cần annotation hoặc cấu hình riêng để quyết định property Java được biểu diễn thành element hay attribute, tên element là gì và cách xử lý danh sách phần tử.

Không nên giả định rằng cùng một DTO sẽ tự động tạo ra cấu trúc XML đúng với hợp đồng của một hệ thống bên ngoài. Cần kiểm tra XML thực tế và đối chiếu với schema hoặc tài liệu tích hợp của bên nhận.

### 5.2. CSV: dữ liệu dạng hàng và cột

CSV phù hợp với dữ liệu bảng, chẳng hạn danh sách sản phẩm có các cột `code` và `price`. `CsvMapper` kết hợp với `CsvSchema` để mô tả cấu trúc bảng:

```java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

CsvMapper mapper = new CsvMapper();
CsvSchema schema = mapper.schemaFor(Product.class).withHeader();

String csv = mapper.writer(schema).writeValueAsString(product);
Product restored = mapper.readerFor(Product.class)
        .with(schema)
        .readValue(csv);
```

Schema giúp xác định cột và cách xử lý header. CSV không có cấu trúc lồng nhau phong phú như JSON hoặc XML. Nếu mô hình Java chứa object con, danh sách hoặc dữ liệu phức tạp, bạn phải quyết định cách làm phẳng chúng thành cột hoặc chọn định dạng khác phù hợp hơn.

### 5.3. Smile và CBOR: dữ liệu nhị phân

Smile và CBOR biểu diễn dữ liệu dưới dạng nhị phân thay vì văn bản JSON dễ đọc. Với một format factory tương ứng, ứng dụng có thể sử dụng databind để ánh xạ object:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.smile.SmileFactory;

ObjectMapper mapper = new ObjectMapper(new SmileFactory());

byte[] payload = mapper.writeValueAsBytes(product);
Product restored = mapper.readValue(payload, Product.class);
```

Các định dạng nhị phân có thể hữu ích khi hai đầu giao tiếp đều hỗ trợ cùng định dạng và cần đặc tính phù hợp về kích thước hoặc hiệu quả xử lý. Đổi lại, payload không thuận tiện để đọc trực tiếp bằng mắt hoặc chỉnh sửa bằng trình soạn thảo văn bản thông thường.

Việc chọn Smile hay CBOR cần dựa trên khả năng tương thích của hệ thống nhận, yêu cầu vận hành, công cụ quan sát và kết quả đo đạc thực tế. Không nên mặc định định dạng nhị phân luôn nhanh hơn hoặc nhỏ hơn trong mọi tình huống.

## 6. Phân biệt dataformat module với datatype module

Một điểm dễ nhầm là không phải mọi module mở rộng của Jackson đều bổ sung định dạng dữ liệu mới.

**Dataformat module** bổ sung cách đọc/ghi một định dạng bên ngoài, ví dụ YAML, XML, CSV, Smile hoặc CBOR. Nó thay đổi hoặc bổ sung cách dữ liệu được biểu diễn trên đường truyền hay trong tệp.

**Datatype module** bổ sung khả năng xử lý một số kiểu Java trong quá trình ánh xạ. Ví dụ:

| Module | Hỗ trợ thêm | Có tạo định dạng trao đổi mới không? |
| --- | --- | --- |
| `jackson-datatype-jsr310` | Các kiểu ngày giờ trong Java Time như `LocalDate`, `Instant`, `LocalDateTime`. | Không. Nó bổ sung cách ánh xạ kiểu Java. |
| `jackson-datatype-jdk8` | Một số kiểu trong Java 8 như `Optional`. | Không. Nó bổ sung hỗ trợ kiểu Java. |
| `jackson-dataformat-yaml` | Đọc và ghi YAML. | Có. Nó bổ sung một định dạng dữ liệu. |
| `jackson-dataformat-xml` | Đọc và ghi XML. | Có. Nó bổ sung một định dạng dữ liệu. |

Ví dụ, `JavaTimeModule` giúp databind xử lý `LocalDate` hoặc `Instant`. Sau khi đăng ký module phù hợp, kiểu ngày giờ đó vẫn có thể được biểu diễn trong JSON; ứng dụng không vì thế chuyển sang một định dạng mới.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
```

Tùy cấu hình và môi trường framework, một số module có thể được tự động phát hiện hoặc đăng ký. Khi cần kết quả ổn định, hãy kiểm tra cấu hình `ObjectMapper` thực tế thay vì giả định module trên classpath chắc chắn đã được áp dụng.

## 7. Chọn định dạng theo hợp đồng dữ liệu

Không nên chọn định dạng chỉ vì Jackson có module hỗ trợ. Định dạng phải phù hợp với hệ thống nhận, mục đích sử dụng và hợp đồng dữ liệu.

| Tiêu chí | JSON | YAML | XML | CSV | Smile / CBOR |
| --- | --- | --- | --- | --- | --- |
| Dễ đọc bằng mắt | Tốt | Tốt | Có thể dài và nhiều thẻ | Tốt với bảng đơn giản | Thấp vì là nhị phân |
| Cấu trúc lồng nhau | Tốt | Tốt | Tốt, theo mô hình XML | Hạn chế | Tốt |
| Phù hợp dữ liệu dạng bảng | Có thể dùng array/object | Có thể dùng list/map | Có thể nhưng thường dài | Rất phù hợp | Có thể |
| Hỗ trợ rộng trong web API | Rất phổ biến | Ít phổ biến hơn | Phụ thuộc hệ thống tích hợp | Thường dùng cho import/export | Cần hai phía hỗ trợ |
| Nhu cầu schema/quy tắc riêng | Theo hợp đồng JSON | Theo quy tắc YAML | Thường cần chú ý namespace/schema | Cần xác định cột và kiểu | Theo hợp đồng của hệ thống |

JSON thường là lựa chọn mặc định hợp lý cho REST API mới vì mức độ hỗ trợ rộng. YAML phù hợp với nhiều tệp cấu hình. XML thường xuất hiện trong tích hợp hệ thống đã có hợp đồng XML hoặc cần các đặc trưng XML. CSV phù hợp cho nhập/xuất bảng tính. Smile/CBOR chỉ nên chọn khi cả hai phía có khả năng hỗ trợ và lợi ích được xác nhận.

## 8. Lưu ý khi tích hợp với Spring Boot

Trong ứng dụng Spring Boot Web, `ObjectMapper` thường được framework cấu hình và sử dụng thông qua HTTP message converter để đọc request hoặc ghi response JSON. Nếu muốn endpoint hỗ trợ XML, YAML hay một media type khác, việc thêm dependency định dạng có thể là một phần cần thiết, nhưng chưa chắc đã đủ.

Bạn còn phải xem xét:

- HTTP message converter tương ứng có được đăng ký hay không.
- `Content-Type` và `Accept` của request/response có phù hợp không.
- Cấu trúc thực tế có khớp hợp đồng mà client mong đợi không.
- `ObjectMapper` hoặc mapper chuyên biệt có dùng đúng module và cấu hình không.
- Kiểu Java, ngày giờ, enum, null và collection có được biểu diễn nhất quán không.

Một ứng dụng dùng `ObjectMapper` cho JSON không tự động biến mọi endpoint thành endpoint hỗ trợ mọi định dạng Jackson có thể đọc. Khả năng hỗ trợ ở tầng HTTP còn phụ thuộc converter và content negotiation của framework.

## 9. Cách ghi nhớ kiến trúc

- **Lõi xử lý:** cung cấp parser/generator và cơ chế ánh xạ dữ liệu ở mức Java.
- **Phần mở rộng theo định dạng:** bổ sung cách đọc/ghi YAML, XML, CSV hoặc định dạng khác.
- **Phần mở rộng theo kiểu Java:** bổ sung hỗ trợ cho kiểu như `LocalDate`, `Instant` hoặc `Optional` mà không tạo định dạng trao đổi mới.
- **Annotation:** khai báo metadata; cơ chế ánh xạ đọc metadata đó và áp dụng quy tắc.
- **Mapper:** là điểm vào cấp cao giúp ứng dụng làm việc với object Java thay vì tự xử lý token.

Khi cần một định dạng mới, hãy tìm dataformat module phù hợp và kiểm tra mapper/factory mà module cung cấp. Khi định dạng đã đúng nhưng một kiểu Java chưa được ánh xạ như mong muốn, hãy xem xét datatype module hoặc serializer/deserializer. Khi chỉ cần đổi tên hoặc điều khiển một property, annotation hay cấu hình databind thường là nơi phù hợp hơn.
