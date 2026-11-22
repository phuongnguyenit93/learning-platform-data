# `@Transient`, `@ReadOnlyProperty` và `@WriteOnlyProperty`

Spring Data Elasticsearch ánh xạ object Java thành document Elasticsearch khi ghi dữ liệu và chuyển document nhận được thành object Java khi đọc dữ liệu. Không phải thuộc tính nào trong entity cũng cần đi qua cả hai chiều. Có thuộc tính chỉ phục vụ hiển thị trong ứng dụng, có thuộc tính do ingest pipeline hoặc một hệ thống khác tạo ra, và cũng có thuộc tính chỉ cần gửi đi trong một lần ghi.

Spring Data cung cấp ba annotation để mô tả những trường hợp này:

- `@Transient`: loại thuộc tính khỏi quá trình persistence mapping.
- `@ReadOnlyProperty`: đọc thuộc tính từ datastore nhưng không ghi thuộc tính đó từ entity xuống datastore.
- `@WriteOnlyProperty`: ghi thuộc tính từ entity xuống datastore nhưng không đọc giá trị của nó từ datastore vào entity.

Ba annotation này thuộc Spring Data Commons (`org.springframework.data.annotation`), được dùng trong mô hình mapping của Spring Data. Chúng điều khiển cách Spring Data chuyển đổi object và document. Chúng không thay thế các thiết lập mapping riêng của Elasticsearch như `@Field`, `index`, `doc_values` hoặc `_source`.

## 1. Hai chiều chuyển đổi giữa entity và Elasticsearch

Khi lưu một entity, Spring Data chuyển object thành dữ liệu để gửi tới Elasticsearch. Khi đọc, Spring Data lấy document trả về và chuyển các trường dữ liệu thành thuộc tính của object.

```text
Ghi dữ liệu

Java entity
    |
    v
Spring Data mapping converter
    |
    v
Elasticsearch document
    |
    v
Index

Đọc dữ liệu

Index
    |
    v
Elasticsearch document / _source
    |
    v
Spring Data mapping converter
    |
    v
Java entity
```

Với một thuộc tính thông thường không có annotation đặc biệt, Spring Data thường ghi giá trị của thuộc tính khi lưu và gán giá trị từ document khi đọc. Ba annotation đang học thay đổi hành vi theo từng chiều.

| Annotation | Ghi từ entity xuống Elasticsearch | Đọc từ Elasticsearch vào entity | Trường hợp sử dụng |
|---|---:|---:|---|
| Không có annotation đặc biệt | Có | Có | Thuộc tính persistence thông thường |
| `@Transient` | Không | Không | Giá trị chỉ tồn tại trong ứng dụng, không thuộc document |
| `@ReadOnlyProperty` | Không | Có | Giá trị được Elasticsearch hoặc hệ thống khác tạo ra |
| `@WriteOnlyProperty` | Có | Không | Giá trị chỉ cần gửi vào datastore hoặc pipeline |

Có thể ghi nhớ ba hành vi như sau:

```text
@Transient          : không ghi, không đọc
@ReadOnlyProperty   : chỉ đọc
@WriteOnlyProperty  : chỉ ghi
```

## 2. `@Transient`: thuộc tính không tham gia persistence mapping

`@Transient` đánh dấu một thuộc tính không phải dữ liệu cần lưu trong datastore. Spring Data bỏ qua thuộc tính này khi chuyển entity thành document và khi chuyển document thành entity.

Annotation thường được dùng cho:

- Giá trị tính toán từ những thuộc tính đã lưu.
- Dữ liệu tạm thời chỉ dùng trong một lần xử lý nghiệp vụ.
- Trạng thái giao diện hoặc giá trị hỗ trợ hiển thị.
- Cache trong bộ nhớ gắn với object nhưng không thuộc dữ liệu Elasticsearch.

Ví dụ một sản phẩm có tên và giá được lưu trong Elasticsearch, còn `displayLabel` chỉ được tạo để hiển thị:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Transient
    private String displayLabel;

    public String getDisplayLabel() {
        return name + " - " + priceInCents + " cents";
    }
}
```

`id`, `name` và `priceInCents` là dữ liệu persistence. `displayLabel` được tạo từ những giá trị đó, vì vậy không cần lưu lặp lại vào Elasticsearch. Khi đọc document, Spring Data cũng không cố gắng lấy một field `displayLabel` để gán vào entity.

### 2.1. `@Transient` không giống `@Field(index = false)`

Hai cấu hình có mục đích khác nhau:

- `@Transient` loại thuộc tính khỏi persistence mapping của Spring Data. Giá trị không được ghi vào document thông qua mapping converter và không được đọc từ document vào thuộc tính.
- `@Field(index = false)` vẫn cho phép thuộc tính tham gia chuyển đổi và lưu giá trị vào document, nhưng yêu cầu Elasticsearch không lập chỉ mục field theo cách thông thường để tìm kiếm term.

Ví dụ, một mô tả dài có thể vẫn cần lưu và trả về trong `_source` nhưng không cần tìm kiếm toàn văn. Khi đó, `index = false` có thể phù hợp. Nếu một giá trị chỉ phục vụ hiển thị và không nên thuộc document, `@Transient` phù hợp hơn.

### 2.2. `@Transient` không phải annotation JSON

`@Transient` của Spring Data chỉ điều khiển persistence mapping. Nó không tự động loại thuộc tính khỏi JSON mà Spring MVC/Jackson trả về. Nếu REST API không được phép trả một thuộc tính, hãy thiết kế DTO hoặc dùng annotation/cấu hình JSON phù hợp, chẳng hạn `@JsonIgnore` khi đó đúng là yêu cầu của API.

Java cũng có từ khóa `transient`, thường liên quan tới Java serialization. Từ khóa của ngôn ngữ và annotation `org.springframework.data.annotation.Transient` thuộc hai cơ chế khác nhau. Khi muốn diễn đạt rõ ý định với Spring Data mapping, có thể dùng annotation của Spring Data.

## 3. `@ReadOnlyProperty`: chỉ đọc từ Elasticsearch

`@ReadOnlyProperty` đánh dấu thuộc tính mà Spring Data được phép đọc từ document nhưng không ghi giá trị thuộc tính đó khi lưu entity.

Đây là lựa chọn hữu ích khi giá trị được tạo hoặc quản lý bên ngoài luồng ghi thông thường của entity, ví dụ:

- Ingest pipeline bổ sung thời điểm tiếp nhận tài liệu.
- Một hệ thống đồng bộ khác bổ sung metadata.
- Một tiến trình xử lý cập nhật trường kết quả sau khi ứng dụng gửi document.
- Elasticsearch trả về một giá trị được tính hoặc được thêm vào `_source` bởi cơ chế khác.

Ví dụ, ứng dụng gửi một đơn hàng và ingest pipeline thêm `indexedAt` vào document:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @ReadOnlyProperty
    @Field(type = FieldType.Date)
    private Instant indexedAt;

    // Constructors, getters and setters
}
```

Khi lưu `Order`, Spring Data không gửi giá trị `indexedAt` từ object xuống Elasticsearch. Khi đọc document có field `indexedAt`, Spring Data vẫn có thể ánh xạ giá trị đó vào thuộc tính `indexedAt`.

Mapping `@Field(type = FieldType.Date)` mô tả kiểu dữ liệu Elasticsearch của field. `@ReadOnlyProperty` mô tả chiều chuyển đổi của Spring Data. Hai annotation có thể cùng xuất hiện vì chúng đảm nhiệm hai vai trò khác nhau.

### 3.1. Ví dụ ingest pipeline bổ sung trường

Một ingest pipeline có thể đặt thời điểm xử lý vào field `indexedAt`:

```http
PUT _ingest/pipeline/add-indexed-time
{
  "processors": [
    {
      "set": {
        "field": "indexedAt",
        "value": "{{{_ingest.timestamp}}}"
      }
    }
  ]
}
```

Có thể cấu hình index sử dụng pipeline mặc định:

```http
PUT orders
{
  "settings": {
    "index.default_pipeline": "add-indexed-time"
  },
  "mappings": {
    "properties": {
      "status": {
        "type": "keyword"
      },
      "indexedAt": {
        "type": "date"
      }
    }
  }
}
```

Khi ứng dụng ghi document vào index này, pipeline có thể bổ sung `indexedAt` trước khi document được lưu. Khi Spring Data đọc document, `@ReadOnlyProperty` cho phép nhận giá trị do pipeline tạo ra.

Ví dụ pipeline và mapping trên được tạo riêng ở Elasticsearch. `@Document` cùng `@Field` không tự động tạo ingest pipeline. Nếu index đã được tạo trước đó, cần bảo đảm mapping và pipeline đã được cấu hình đúng trước khi ứng dụng gửi dữ liệu.

### 3.2. Chú ý khi cập nhật document

`@ReadOnlyProperty` chỉ ngăn Spring Data ghi giá trị thuộc tính từ entity. Nó không khóa field ở mức Elasticsearch và không ngăn một client khác cập nhật field đó.

Ngoài ra, cần hiểu cách ứng dụng ghi document. Một thao tác index thay thế document có thể tạo lại `_source` từ những field mà client gửi. Nếu field `indexedAt` được tạo bởi pipeline, hãy bảo đảm pipeline vẫn chạy để tạo lại field trên mỗi lần ghi cần thiết, hoặc thiết kế luồng update phù hợp. Không giả định field do hệ thống khác tạo sẽ luôn được giữ lại sau mọi lần save.

## 4. `@WriteOnlyProperty`: chỉ ghi xuống Elasticsearch

`@WriteOnlyProperty` đánh dấu thuộc tính được ghi từ entity xuống datastore nhưng không được ánh xạ ngược từ document vào entity khi đọc.

Có thể dùng khi:

- Một giá trị đầu vào chỉ phục vụ ingest pipeline.
- Một lệnh hoặc tham số cần gửi trong lần ghi nhưng không cần có trong object đọc lại.
- Một trường tạm thời được xử lý ở phía Elasticsearch hoặc một hệ thống trung gian.
- Ứng dụng muốn tách mô hình dữ liệu đầu vào khỏi mô hình dữ liệu đọc, trong khi vẫn dùng chung entity ở một số luồng.

Ví dụ, ứng dụng gửi `ingestCommand` để pipeline xử lý, nhưng không cần thuộc tính này khi đọc lại đơn hàng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.WriteOnlyProperty;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @WriteOnlyProperty
    @Field(type = FieldType.Keyword)
    private String ingestCommand;

    // Constructors, getters and setters
}
```

Khi lưu entity có `ingestCommand`, Spring Data ghi giá trị này vào document đầu vào. Khi đọc document thành `Order`, Spring Data không gán giá trị từ field đó vào thuộc tính `ingestCommand`.

### 4.1. `@WriteOnlyProperty` không xóa field khỏi Elasticsearch

Điểm quan trọng là `@WriteOnlyProperty` điều khiển việc chuyển đổi của Spring Data. Nó không tự động xóa field khỏi `_source`, không mã hóa giá trị và không tạo quy tắc phân quyền Elasticsearch.

Nếu field vẫn tồn tại trong `_source`, người dùng có quyền đọc document qua Elasticsearch API hoặc một client khác vẫn có thể nhận được giá trị đó. Annotation chỉ khiến mapping converter của Spring Data không đưa giá trị này vào thuộc tính Java khi đọc.

Nếu dữ liệu đầu vào nhạy cảm và không được phép lưu lâu dài, hãy xử lý yêu cầu đó bằng thiết kế phù hợp, chẳng hạn:

- Không gửi dữ liệu nhạy cảm nếu Elasticsearch không cần nó.
- Dùng ingest pipeline xử lý rồi loại bỏ field đầu vào bằng processor `remove`.
- Cấp quyền truy cập index/document phù hợp và giới hạn các API được phép đọc.
- Dùng DTO riêng để tránh trả dữ liệu nội bộ ra REST API.

Không dùng `@WriteOnlyProperty` như một cơ chế bảo mật hoặc che giấu bí mật.

### 4.2. Ví dụ pipeline loại bỏ trường đầu vào

Một pipeline có thể nhận `ingestCommand`, tạo metadata cần thiết rồi xóa trường lệnh khỏi document trước khi lưu:

```http
PUT _ingest/pipeline/consume-order-command
{
  "processors": [
    {
      "set": {
        "field": "commandProcessed",
        "value": true
      }
    },
    {
      "remove": {
        "field": "ingestCommand",
        "ignore_missing": true
      }
    }
  ]
}
```

Khi index được cấu hình dùng pipeline này, `ingestCommand` có thể được xử lý trong quá trình ingest rồi bị loại bỏ khỏi document cuối cùng. `@WriteOnlyProperty` giúp entity đọc lại không cố gắng ánh xạ field này. Việc xóa thực tế khỏi `_source` là trách nhiệm của pipeline, không phải annotation.

Nếu ứng dụng cần giữ lại giá trị đầu vào để audit, không xóa field một cách tùy tiện. Hãy xác định thời hạn lưu, quyền truy cập và yêu cầu audit trước khi quyết định lưu hoặc loại bỏ dữ liệu.

## 5. So sánh ba annotation trong cùng một entity

Một entity có thể có các thuộc tính với hành vi khác nhau. Ví dụ sau kết hợp cả ba annotation:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.WriteOnlyProperty;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @ReadOnlyProperty
    @Field(type = FieldType.Date)
    private Instant indexedAt;

    @WriteOnlyProperty
    @Field(type = FieldType.Keyword)
    private String ingestCommand;

    @Transient
    private String displayLabel;

    // Constructors, getters and setters
}
```

Ý nghĩa từng thuộc tính:

| Thuộc tính | Annotation | Khi save entity | Khi đọc document |
|---|---|---|---|
| `id` | `@Id` | Dùng làm document ID | Được ánh xạ từ ID |
| `status` | Không có annotation đặc biệt | Được ghi | Được đọc |
| `indexedAt` | `@ReadOnlyProperty` | Không ghi từ entity | Được đọc nếu document có field |
| `ingestCommand` | `@WriteOnlyProperty` | Được ghi | Không được ánh xạ vào entity |
| `displayLabel` | `@Transient` | Bỏ qua | Bỏ qua |

Sự phân chia này giúp entity thể hiện rõ nguồn gốc và vòng đời của từng thuộc tính. Những giá trị do Elasticsearch hoặc pipeline tạo ra không bị ứng dụng vô tình ghi đè bằng giá trị rỗng từ entity; những giá trị chỉ phục vụ lệnh ghi cũng không cần được nạp lại vào object đọc.

## 6. Phân biệt annotation Spring Data với các cấu hình Elasticsearch khác

Các annotation persistence và thuộc tính mapping Elasticsearch thường dễ bị nhầm lẫn vì đều xuất hiện trên cùng một field. Cần phân biệt câu hỏi mà mỗi cấu hình trả lời.

| Cấu hình | Câu hỏi chính | Ảnh hưởng điển hình |
|---|---|---|
| `@Transient` | Thuộc tính có thuộc mô hình persistence của Spring Data không? | Bỏ qua cả ghi và đọc qua mapping converter |
| `@ReadOnlyProperty` | Spring Data có ghi giá trị từ entity không? | Chỉ đọc từ datastore |
| `@WriteOnlyProperty` | Spring Data có nạp giá trị từ datastore vào entity không? | Chỉ ghi xuống datastore |
| `@Field(type = ...)` | Field có kiểu Elasticsearch nào? | Mô tả mapping như `text`, `keyword`, `date`, `long` |
| `@Field(index = false)` | Elasticsearch có lập chỉ mục field để tìm kiếm không? | Điều khiển khả năng index/search của field |
| `@Field(docValues = false)` | Field có tạo doc values không? | Ảnh hưởng các thao tác dựa trên doc values |
| `@JsonIgnore` | Jackson có đưa thuộc tính vào JSON không? | Điều khiển JSON serialization/deserialization |

Ví dụ:

```java
@Field(type = FieldType.Text, index = false)
private String internalDescription;
```

Field `internalDescription` vẫn là thuộc tính persistence. Spring Data có thể ghi và đọc nó; `index = false` điều khiển việc Elasticsearch lập chỉ mục field. Điều này khác với:

```java
@Transient
private String temporaryDescription;
```

`temporaryDescription` bị bỏ qua bởi Spring Data mapping converter.

Tương tự, `@WriteOnlyProperty` không có nghĩa là Elasticsearch không lập chỉ mục field. Nếu field có mapping và được gửi vào index request, Elasticsearch vẫn áp dụng cấu hình mapping tương ứng. `@ReadOnlyProperty` cũng không có nghĩa field bị khóa ghi ở phía cluster.

## 7. Ảnh hưởng tới `_source` và kết quả tìm kiếm

Elasticsearch thường lưu JSON gốc của document trong `_source`. Ngoài `_source`, Elasticsearch còn tạo các cấu trúc phục vụ tìm kiếm, sort hoặc aggregation tùy kiểu field và mapping.

Ba annotation của Spring Data tác động ở tầng chuyển đổi entity/document:

- `@Transient`: Spring Data không đưa thuộc tính vào document được tạo từ entity và không gán field từ document vào thuộc tính.
- `@ReadOnlyProperty`: Spring Data không đưa giá trị thuộc tính vào document khi ghi; nếu document được tạo bởi pipeline hoặc client khác có field tương ứng, Spring Data có thể đọc field đó.
- `@WriteOnlyProperty`: Spring Data đưa giá trị vào document khi ghi nhưng bỏ qua field khi tạo entity từ document.

Các annotation không tự thay đổi cách Elasticsearch lưu `_source` sau khi nhận request. Pipeline, mapping, `_source` configuration và quyền truy cập Elasticsearch mới quyết định dữ liệu nào được lưu, được index và được trả về ở tầng Elasticsearch.

Nếu cần xác định một field có thể tìm kiếm hay không, hãy xem mapping của index. Nếu cần xác định field có tồn tại trong `_source` hay không, hãy kiểm tra document thực tế. Không thể suy ra hai điều đó chỉ từ `@ReadOnlyProperty` hoặc `@WriteOnlyProperty`.

## 8. Ảnh hưởng tới repository và ElasticsearchOperations

Các annotation được áp dụng trong Spring Data mapping layer, vì vậy hành vi xuất hiện khi dùng những API chuyển đổi entity như repository hoặc `ElasticsearchOperations`.

Ví dụ:

```java
Order order = new Order();
order.setId("order-100");
order.setStatus("CREATED");
order.setIngestCommand("RECALCULATE_METADATA");

Order saved = orderRepository.save(order);

Order loaded = orderRepository.findById("order-100")
        .orElseThrow();
```

Ở bước ghi, Spring Data áp dụng quy tắc chuyển đổi của từng thuộc tính. Ở bước đọc, nó áp dụng quy tắc chiều ngược lại. Với document có pipeline, `indexedAt` có thể được đọc vào `loaded`; `ingestCommand` không được nạp vào `loaded`; `displayLabel` vẫn là giá trị transient do ứng dụng tự tính.

Không nên giả định object trả về từ `save` sẽ có cùng trạng thái với một object vừa được đọc lại từ Elasticsearch. Repository có thể trả về entity đầu vào hoặc một biểu diễn đã xử lý tùy API và phiên bản; annotation `@WriteOnlyProperty` điều khiển việc mapping từ datastore, không phải yêu cầu xóa giá trị khỏi object Java mà caller đang giữ.

Nếu dùng Elasticsearch Java Client trực tiếp để đọc hoặc ghi JSON, các annotation Spring Data không tự áp dụng cho request đó. Client cấp thấp không đi qua Spring Data mapping converter. Khi trộn repository, `ElasticsearchOperations` và client trực tiếp, cần hiểu rõ tầng nào đang thực hiện chuyển đổi.

## 9. Lưu ý về constructor, getter/setter và cách truy cập thuộc tính

Spring Data xác định persistent properties dựa trên metadata của entity và cách truy cập được chọn. Trong Java, annotation thường được đặt trên field như các ví dụ trong bài. Nếu dự án sử dụng property access hoặc đặt annotation trên getter, hãy nhất quán với cách Spring Data nhận diện thuộc tính.

Một số điểm cần chú ý:

- Đặt annotation trên đúng field/property mà Spring Data quản lý; tránh có nhiều thuộc tính trùng tên hoặc getter/setter có side effect.
- Nếu dùng Lombok, kiểm tra vị trí annotation được sinh ra và cấu hình `@Getter`, `@Setter` hoặc `@Accessors` để không vô tình đặt annotation vào vị trí khác dự định.
- Constructor dùng để tạo entity khi đọc document phải tương thích với persistent properties. Nếu dùng constructor có tham số, tên/thứ tự và metadata cần phù hợp với quy tắc mapping của Spring Data.
- Với thuộc tính `@Transient`, không yêu cầu Spring Data khôi phục giá trị từ document. Nếu giá trị cần thiết sau khi đọc, hãy tính lại trong ứng dụng hoặc tạo nó qua service/DTO.
- Với `@ReadOnlyProperty`, cần có nguồn khác ghi field vào document. Nếu không có pipeline hoặc writer nào tạo field, thuộc tính sẽ thường là `null`/giá trị mặc định khi đọc.
- Với `@WriteOnlyProperty`, entity được đọc lại không có giá trị thuộc tính đó từ document. Dùng kiểu nullable/wrapper nếu cần phân biệt trạng thái không có giá trị với giá trị mặc định.

## 10. Kiểm tra hành vi bằng dữ liệu thực tế

Khi sử dụng các annotation này, hãy kiểm tra cả hai chiều chuyển đổi thay vì chỉ nhìn vào khai báo Java.

Có thể tạo document mẫu rồi kiểm tra `_source`:

```http
GET orders/_doc/order-100
```

Kiểm tra mapping của index:

```http
GET orders/_mapping
```

Các câu hỏi hữu ích khi kiểm tra:

1. Field `@Transient` có bị bỏ khỏi document do Spring Data tạo không?
2. Field `@ReadOnlyProperty` có được một ingest pipeline hoặc hệ thống khác bổ sung không?
3. Field `@WriteOnlyProperty` có được gửi trong request ghi không?
4. Pipeline có giữ hay loại bỏ field đầu vào trong `_source`?
5. Khi repository đọc lại document, thuộc tính read-only có được gán và thuộc tính write-only có bị bỏ qua không?
6. Mapping Elasticsearch có đúng kiểu dữ liệu và cấu hình index cần thiết không?

Nếu kiểm tra request Elasticsearch trực tiếp, hãy phân biệt document được gửi bởi Spring Data với document được pipeline biến đổi trước khi lưu. Dữ liệu trong `_source` cuối cùng có thể khác JSON ban đầu mà ứng dụng gửi.

Trong integration test, có thể dùng Elasticsearch thật hoặc Testcontainers để kiểm tra mapping converter cùng ingest pipeline. Mock repository chỉ kiểm tra tương tác ở tầng ứng dụng; nó không xác minh hành vi chuyển đổi document của Spring Data hay việc pipeline thực thi trên Elasticsearch.

## 11. Những lỗi sử dụng thường gặp

### Dùng `@Transient` cho field cần được pipeline tạo ra

`@Transient` khiến Spring Data bỏ qua thuộc tính cả khi ghi lẫn khi đọc. Nếu pipeline tạo `indexedAt` và ứng dụng muốn nhận giá trị này khi đọc document, hãy dùng `@ReadOnlyProperty` thay vì `@Transient`.

### Dùng `@ReadOnlyProperty` nhưng không có hệ thống nào ghi field

Annotation chỉ ngăn entity ghi giá trị xuống Elasticsearch. Nó không tự sinh timestamp hoặc metadata. Cần cấu hình ingest pipeline, một writer khác hoặc cơ chế tạo giá trị tương ứng.

### Cho rằng `@WriteOnlyProperty` bảo vệ dữ liệu nhạy cảm

Annotation không đảm bảo field bị xóa khỏi `_source`. Một người dùng có quyền đọc document qua Elasticsearch API vẫn có thể nhìn thấy field nếu nó được lưu. Dùng pipeline remove, phân quyền và thiết kế dữ liệu phù hợp khi cần bảo vệ thông tin.

### Nhầm `@Field(index = false)` với `@Transient`

`index = false` liên quan tới khả năng lập chỉ mục của Elasticsearch. Nó không tự loại field khỏi quá trình đọc/ghi của Spring Data. `@Transient` mới là annotation loại thuộc tính khỏi persistence mapping.

### Mong đợi annotation tác động khi dùng client cấp thấp

Các annotation Spring Data không phải quy tắc mapping của Elasticsearch server. Khi gọi Elasticsearch Java Client trực tiếp, hãy tự tạo request và xử lý response theo cấu trúc dữ liệu mong muốn.

### Quên tác động của thao tác ghi thay thế document

Nếu một field read-only được pipeline tạo ra, thao tác index tiếp theo có thể thay thế `_source`. Hãy bảo đảm pipeline tiếp tục tạo field hoặc dùng cơ chế update thích hợp để không vô tình làm mất metadata.

## 12. Cách lựa chọn annotation

| Nhu cầu | Annotation/cấu hình phù hợp | Lý do |
|---|---|---|
| Giá trị chỉ tính trong ứng dụng, không thuộc document | `@Transient` | Không cần ghi hoặc đọc qua persistence mapping |
| Timestamp do ingest pipeline tạo, ứng dụng cần đọc | `@ReadOnlyProperty` kết hợp `@Field` | Đọc field từ document nhưng không ghi giá trị từ entity |
| Tham số gửi cho pipeline, không cần nạp lại vào entity | `@WriteOnlyProperty` kết hợp `@Field` | Ghi đầu vào nhưng bỏ qua khi đọc entity |
| Chuỗi vẫn lưu trong `_source` nhưng không cần lập chỉ mục | `@Field(index = false)` | Field vẫn thuộc document, chỉ thay đổi hành vi index |
| Thuộc tính không được xuất hiện trong JSON API | DTO hoặc cấu hình Jackson | Điều khiển JSON serialization, độc lập với Spring Data mapping |

## 13. Tổng kết

`@Transient`, `@ReadOnlyProperty` và `@WriteOnlyProperty` cho phép Spring Data mô tả rõ một thuộc tính tham gia vào chiều nào của quá trình persistence. `@Transient` bỏ qua cả đọc và ghi; `@ReadOnlyProperty` chỉ đọc dữ liệu từ Elasticsearch; `@WriteOnlyProperty` chỉ ghi dữ liệu xuống Elasticsearch.

Trong Spring Data Elasticsearch, có thể kết hợp `@ReadOnlyProperty` hoặc `@WriteOnlyProperty` với `@Field` để vừa kiểm soát chiều chuyển đổi ở Spring Data, vừa mô tả kiểu field ở Elasticsearch. Cần phân biệt những annotation này với `index = false`, `_source` và annotation JSON. Đặc biệt, `@WriteOnlyProperty` không phải cơ chế bảo mật và `@ReadOnlyProperty` không khóa field ở phía cluster. Hiểu đúng ranh giới giữa mapping converter, ingest pipeline và Elasticsearch mapping giúp entity phản ánh chính xác nguồn gốc cũng như vòng đời của dữ liệu.
