# Ghi nhiều giá trị với ObjectWriter và SequenceWriter

Khi xuất dữ liệu lớn, ứng dụng thường cần ghi nhiều object liên tiếp ra file, HTTP response hoặc một luồng dữ liệu. Việc gom toàn bộ object thành một `List` rồi serialize cả danh sách có thể làm tăng mức sử dụng bộ nhớ. Jackson Databind cung cấp `ObjectWriter` và `SequenceWriter` để cấu hình cách ghi và tuần tự hóa nhiều giá trị theo từng lần gọi.

Hai API có vai trò khác nhau:

- **`ObjectWriter`** là đối tượng ghi đã được cấu hình cho một lần serialize hoặc cho một kiểu dữ liệu. Nó có thể được tái sử dụng và không giữ trạng thái của một lần ghi cụ thể.
- **`SequenceWriter`** là writer có trạng thái, được tạo từ `ObjectWriter`, dùng để ghi nhiều giá trị lần lượt vào cùng một output. Nó quản lý ranh giới giữa các giá trị và có thể ghi chúng thành một JSON array.

Bài học này giải thích cách chọn định dạng đầu ra, cách cấu hình writer, ghi từng phần tử hoặc cả iterator, xử lý JSON Lines, quản lý tài nguyên và tránh tạo một file JSON không hoàn chỉnh.

## 1. Vì sao cần ghi nhiều giá trị theo luồng?

Giả sử hệ thống cần xuất hàng trăm nghìn sản phẩm. Cách đơn giản là lấy toàn bộ dữ liệu thành List rồi serialize:

```java
List<ProductDto> products = repository.findAll();

String json = mapper.writeValueAsString(products);

Files.writeString(path, json, StandardCharsets.UTF_8);
```

Cách này dễ hiểu nhưng thường giữ đồng thời:

1. Toàn bộ danh sách đối tượng Java.
2. Chuỗi JSON hoàn chỉnh trong bộ nhớ.
3. Có thể thêm các buffer hoặc bản sao dữ liệu khi ghi file.

Với dữ liệu lớn, mức sử dụng bộ nhớ có thể tăng đáng kể. Nếu ứng dụng đã có một nguồn dữ liệu dạng Iterator hoặc Stream, có thể serialize từng phần tử khi đọc được nó.

`SequenceWriter` hỗ trợ cách làm đó:

```text
Nguồn dữ liệu
   │
   ▼
Iterator / Stream / cursor
   │
   ├── phần tử 1 ──> serialize ──┐
   ├── phần tử 2 ──> serialize ──┤
   ├── phần tử 3 ──> serialize ──┼──> OutputStream / Writer
   └── ...                       │
                                ▼
                         File hoặc response
```

Writer không cần giữ toàn bộ sequence đã ghi. Tuy nhiên, để tiết kiệm bộ nhớ thực sự, nguồn dữ liệu cũng phải được đọc tuần tự. Nếu ứng dụng vẫn gọi `findAll()` và giữ một List lớn, `SequenceWriter` chỉ giảm phần bộ nhớ dành cho chuỗi JSON đầu ra, không loại bỏ bộ nhớ của danh sách đầu vào.

## 2. ObjectWriter là gì?

`ObjectWriter` thuộc Jackson Databind. Nó đại diện cho một cấu hình serialize cụ thể được tạo từ `ObjectMapper`.

Có thể tạo writer mặc định:

```java
ObjectWriter writer = mapper.writer();
```

Hoặc chỉ định kiểu dữ liệu:

```java
ObjectWriter productWriter = mapper.writerFor(ProductDto.class);
```

Một `ObjectWriter` có thể lưu các lựa chọn như:

- Kiểu Java đích hoặc kiểu gốc mong đợi.
- Pretty printing.
- Root name và root wrapping.
- Root value separator khi ghi nhiều root value.
- Serialization feature.
- Date format, locale, timezone hoặc attributes.
- Schema hoặc cấu hình serializer phù hợp với lần ghi.

`ObjectWriter` là đối tượng cấu hình bất biến theo cách sử dụng thông thường. Các method như `with(...)`, `without(...)`, `withRootName(...)` tạo ra một writer cấu hình mới thay vì thay đổi writer ban đầu. Vì vậy, có thể chuẩn bị nhiều writer cho nhiều định dạng đầu ra mà không cần thay đổi cấu hình toàn cục của mapper.

### 2.1. Ghi một giá trị bằng ObjectWriter

`ObjectWriter` có thể ghi một giá trị vào String, File, OutputStream hoặc Writer:

```java
ObjectWriter writer = mapper.writerFor(ProductDto.class);

String json = writer.writeValueAsString(product);

writer.writeValue(outputStream, product);
```

Ví dụ:

```java
public record ProductDto(
    long id,
    String name,
    BigDecimal price
) {}

ObjectWriter productWriter = mapper.writerFor(ProductDto.class);

ProductDto product = new ProductDto(
    101L,
    "Keyboard",
    new BigDecimal("1250000.00")
);

String json = productWriter.writeValueAsString(product);
```

Kết quả là một JSON object đơn:

```json
{
  "id": 101,
  "name": "Keyboard",
  "price": 1250000.00
}
```

Đây là một lần ghi một giá trị. Nếu cần ghi nhiều object vào cùng một output theo từng lần gọi, hãy tạo `SequenceWriter` từ writer đó.

### 2.2. Cấu hình writer mà không thay đổi ObjectMapper

Có thể bật pretty printing cho một writer:

```java
ObjectWriter prettyWriter = mapper.writerFor(ProductDto.class)
    .withDefaultPrettyPrinter();
```

Hoặc cấu hình feature:

```java
ObjectWriter writer = mapper.writerFor(ProductDto.class)
    .with(SerializationFeature.INDENT_OUTPUT);
```

Có thể tạo writer riêng cho dữ liệu không cần pretty printing:

```java
ObjectWriter compactWriter = mapper.writerFor(ProductDto.class)
    .without(SerializationFeature.INDENT_OUTPUT);
```

Cách này hữu ích khi cùng một ứng dụng cần response dễ đọc cho mục đích debug và file xuất gọn nhẹ cho xử lý máy. Cấu hình writer chỉ áp dụng cho thao tác dùng writer đó.

### 2.3. Writer có kiểu tường minh

`writerFor(ProductDto.class)` giúp Jackson biết kiểu mà writer được thiết kế để serialize. Điều này hữu ích khi dùng generic wrapper, interface, abstract class hoặc polymorphic type.

```java
ObjectWriter eventWriter = mapper.writerFor(EventDto.class);
```

Khi dùng writer có kiểu cụ thể, hãy truyền các giá trị phù hợp với kiểu đã khai báo. Nếu cần ghi nhiều kiểu Java khác nhau trong cùng sequence, dùng writer tổng quát hoặc thiết kế một kiểu envelope/discriminator rõ ràng để định nghĩa hợp đồng dữ liệu.

## 3. SequenceWriter là gì?

`SequenceWriter` là API ghi một chuỗi giá trị Java ra cùng một output. Nó được tạo từ `ObjectWriter` bằng `writeValues(...)` hoặc `writeValuesAsArray(...)`.

Có hai hình thức quan trọng:

| Cách tạo | Hình dạng đầu ra | Ý nghĩa |
| --- | --- | --- |
| `writeValues(output)` | Nhiều JSON root value nối tiếp nhau | Sequence không có array bao ngoài |
| `writeValuesAsArray(output)` | Một JSON array chứa các phần tử | Một JSON document có root là array |

Hai hình thức này khác nhau về hợp đồng dữ liệu. Hãy chọn theo định dạng mà consumer cần đọc.

### 3.1. Ghi nhiều root value không bọc array

Ví dụ:

```java
ObjectWriter writer = mapper.writerFor(ProductDto.class);

try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    sequence.write(new ProductDto(
        101L, "Keyboard", new BigDecimal("1250000.00")
    ));

    sequence.write(new ProductDto(
        102L, "Mouse", new BigDecimal("350000.00")
    ));
}
```

Đầu ra có dạng nhiều JSON value ở cấp root, được ngăn cách bằng root value separator:

```text
{"id":101,"name":"Keyboard","price":1250000.00} {"id":102,"name":"Mouse","price":350000.00}
```

Separator mặc định phụ thuộc cấu hình generator/writer. Với dữ liệu trao đổi giữa các hệ thống, hãy cấu hình separator tường minh thay vì dựa vào mặc định.

Lưu ý: nhiều root value nối tiếp nhau không phải là một JSON document chuẩn duy nhất. Một JSON document thông thường có một giá trị gốc. Sequence này chỉ phù hợp khi giao thức hoặc consumer biết cách đọc nhiều giá trị liên tiếp.

### 3.2. Ghi nhiều giá trị thành một JSON array

Nếu consumer cần một JSON document hợp lệ có root là array, dùng `writeValuesAsArray(...)`:

```java
ObjectWriter writer = mapper.writerFor(ProductDto.class);

try (SequenceWriter sequence = writer.writeValuesAsArray(outputStream)) {
    sequence.write(new ProductDto(
        101L, "Keyboard", new BigDecimal("1250000.00")
    ));

    sequence.write(new ProductDto(
        102L, "Mouse", new BigDecimal("350000.00")
    ));
}
```

Kết quả:

```json
[
  {
    "id": 101,
    "name": "Keyboard",
    "price": 1250000.00
  },
  {
    "id": 102,
    "name": "Mouse",
    "price": 350000.00
  }
]
```

`SequenceWriter` tự ghi dấu ngoặc vuông mở khi bắt đầu và dấu ngoặc vuông đóng khi sequence được đóng. Nó cũng quản lý dấu phẩy giữa các phần tử.

Nếu sequence không có phần tử, chế độ array vẫn tạo một JSON array rỗng:

```json
[]
```

Với đầu ra array, không tự ghi thêm dấu phẩy hoặc dấu ngoặc bằng tay. Để `SequenceWriter` quản lý cấu trúc.

## 4. Ghi dữ liệu từng phần tử bằng write

Method `write(value)` serialize một giá trị rồi ghi nó vào sequence hiện tại:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    for (ProductDto product : products) {
        sequence.write(product);
    }
}
```

Mỗi lần gọi `write` xử lý một phần tử. Ứng dụng có thể đọc từ database cursor, iterator hoặc nguồn dữ liệu khác rồi ghi ngay, không cần gom toàn bộ kết quả vào một List.

Ví dụ dùng Iterator:

```java
Iterator<ProductDto> iterator = productIterator();

try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    while (iterator.hasNext()) {
        ProductDto product = iterator.next();
        sequence.write(product);
    }
}
```

Đây là pattern phù hợp với export dữ liệu lớn. Nguồn dữ liệu chỉ cần cung cấp phần tử tiếp theo khi writer sẵn sàng ghi.

### 4.1. Xử lý và biến đổi từng phần tử trước khi ghi

Có thể chuyển đổi dữ liệu trước khi serialize:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductExportDto.class)
             .writeValuesAsArray(outputStream)) {

    while (source.hasNext()) {
        ProductEntity entity = source.next();

        ProductExportDto dto = new ProductExportDto(
            entity.getId(),
            entity.getName(),
            entity.getPrice()
        );

        sequence.write(dto);
    }
}
```

Cách này giữ ranh giới rõ ràng giữa mô hình lưu trữ và hợp đồng export. Chỉ một DTO của mỗi phần tử cần được tạo tại thời điểm ghi, nếu logic nguồn không tích lũy các DTO đó vào collection.

## 5. Ghi nhiều phần tử bằng writeAll

`SequenceWriter` hỗ trợ `writeAll(...)` để ghi toàn bộ phần tử từ array, `Iterable` hoặc `Iterator`.

Ví dụ với Iterable:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    sequence.writeAll(products);
}
```

Ví dụ với Iterator:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    sequence.writeAll(productIterator);
}
```

Ví dụ với array Java:

```java
ProductDto[] products = loadProducts();

try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    sequence.writeAll(products);
}
```

`writeAll` là cách viết ngắn gọn. Về bản chất, writer vẫn xử lý từng phần tử của nguồn lần lượt. Nó không tự biến một nguồn dữ liệu đã materialize thành một nguồn lazy.

Nếu `products` là một List lớn đã được tạo trước, List vẫn chiếm bộ nhớ. Để giảm memory footprint, hãy truyền một Iterator hoặc Iterable đọc dữ liệu theo từng trang/cursor và tránh giữ mọi phần tử trong bộ nhớ.

## 6. Tạo JSON Lines bằng ObjectWriter và SequenceWriter

Một định dạng thường gặp khi xuất dữ liệu lớn là **JSON Lines (NDJSON)**. Mỗi dòng chứa một JSON value độc lập, thường là một object. Ví dụ:

```text
{"id":101,"name":"Keyboard"}
{"id":102,"name":"Mouse"}
{"id":103,"name":"Monitor"}
```

Đây không phải một JSON array. Mỗi dòng là một JSON document riêng; consumer đọc từng dòng rồi parse như một tài liệu độc lập.

### 6.1. Cấu hình newline làm root value separator

Có thể cấu hình separator là ký tự xuống dòng:

```java
ObjectWriter lineWriter = mapper.writerFor(ProductDto.class)
    .withRootValueSeparator("\n");

try (OutputStream output = Files.newOutputStream(path);
     SequenceWriter sequence = lineWriter.writeValues(output)) {

    for (ProductDto product : productIterator) {
        sequence.write(product);
    }
}
```

Mỗi root value được ngăn cách bằng newline. Khi dùng JSON Lines, nên serialize mỗi record ở dạng compact, không dùng pretty printer tạo nhiều dòng cho một object. Nếu một object trải trên nhiều dòng vật lý, consumer đọc từng dòng sẽ không còn nhận được một JSON document hoàn chỉnh cho mỗi record.

Root value separator chỉ ngăn cách các root value liên tiếp. Nó không tự biến sequence thành JSON array và cũng không tự thêm một newline kết thúc sau phần tử cuối cùng.

### 6.2. JSON Lines và JSON array khác nhau

| Tiêu chí | JSON Lines | JSON array |
| --- | --- | --- |
| Root | Nhiều JSON document nối tiếp, một document mỗi dòng | Một document có root là array |
| Writer | `writeValues()` với separator newline | `writeValuesAsArray()` |
| Đọc | Đọc từng dòng rồi parse từng JSON value, hoặc dùng reader phù hợp | Đọc một JSON array |
| Xử lý tăng dần | Thuận tiện cho consumer đọc từng record | Có thể stream phần tử trong array bằng parser |
| Kết thúc file | Thường có newline giữa các record; newline cuối file là quy ước nên thống nhất | Cần có dấu `]` đóng array |
| Dùng làm JSON document chuẩn đơn | Không | Có |

Nếu API hoặc hệ thống đích yêu cầu JSON array, đừng gửi JSON Lines chỉ vì nó dễ ghi theo luồng. Hình dạng root là một phần của hợp đồng dữ liệu.

### 6.3. JSON Lines không đồng nghĩa với JSON Text Sequences

Có một định dạng khác là JSON Text Sequences (RFC 7464), sử dụng ký tự Record Separator (RS, U+001E) để đánh dấu ranh giới record và thường kết thúc record bằng LF.

Cấu hình `withRootValueSeparator("\n")` tạo sequence phân tách bằng newline, phù hợp với quy ước JSON Lines khi mỗi record compact. Nó không tự thêm ký tự RS, vì vậy không phải cách tạo đầy đủ JSON Text Sequences.

Hãy chọn định dạng theo giao thức của consumer, không dùng các tên JSON Lines, JSON sequence và JSON array như thể chúng tương đương nhau.

## 7. Cấu hình root value separator

`ObjectWriter.withRootValueSeparator(...)` cho phép cấu hình chuỗi phân cách giữa các root value khi dùng `writeValues(...)`.

Ví dụ dùng newline:

```java
ObjectWriter ndjsonWriter = mapper.writerFor(EventDto.class)
    .withRootValueSeparator("\n");
```

Ví dụ dùng một khoảng trắng:

```java
ObjectWriter spacedSequenceWriter = mapper.writerFor(EventDto.class)
    .withRootValueSeparator(" ");
```

Separator cần phù hợp với định dạng và consumer. Đối với JSON Lines, newline giúp mỗi object nằm trên một dòng. Đối với sequence nội bộ, whitespace có thể đủ nếu parser phía đọc biết rằng có nhiều root value nối tiếp.

Không nên đặt separator là dấu phẩy rồi ghi các root value không có array bao ngoài:

```text
{"id":1},{"id":2}
```

Chuỗi này không phải JSON document chuẩn vì thiếu `[` và `]`. Nếu cần dấu phẩy giữa phần tử, hãy dùng `writeValuesAsArray(...)` để generator quản lý array.

### 7.1. Separator không phải ký tự kết thúc record

Root separator được dùng giữa hai root value. Với một sequence chỉ có một phần tử, sẽ không có separator giữa các phần tử. Với sequence có nhiều phần tử, separator xuất hiện ở ranh giới giữa chúng.

Nếu hệ thống nhận yêu cầu newline cuối file, hãy xử lý quy ước đó ở lớp output sau khi sequence đã hoàn tất, đồng thời bảo đảm stream/generator còn được quản lý đúng. Không nên giả định `SequenceWriter.close()` luôn thêm newline cuối cùng.

## 8. Pretty printing khi ghi sequence

Pretty printing hữu ích cho JSON array hoặc file JSON dùng để con người đọc. Có thể tạo writer:

```java
ObjectWriter prettyWriter = mapper.writerFor(ProductDto.class)
    .withDefaultPrettyPrinter();

try (SequenceWriter sequence =
         prettyWriter.writeValuesAsArray(outputStream)) {
    sequence.writeAll(products);
}
```

Trong array mode, pretty printer có thể định dạng dấu ngoặc và phần tử thành nhiều dòng dễ đọc.

Với JSON Lines, không nên bật pretty printing vì một object có thể được tách thành nhiều dòng. JSON Lines yêu cầu mỗi JSON value nằm trên một dòng vật lý. Dùng writer compact cho định dạng này.

Pretty printing làm tăng kích thước đầu ra và có thể tăng lượng byte ghi. Nếu file phục vụ máy đọc hoặc truyền qua mạng, compact JSON thường phù hợp hơn.

## 9. Ghi ra File, OutputStream và Writer

### 9.1. Ghi JSON array ra File

```java
Path path = Path.of("exports", "products.json");

try (OutputStream output = Files.newOutputStream(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE
    );
    SequenceWriter sequence = mapper.writerFor(ProductDto.class)
        .writeValuesAsArray(output)) {

    sequence.writeAll(productIterator);
}
```

Các option trên tạo file nếu chưa có và ghi đè nội dung cũ. Hãy chọn option phù hợp với quy trình export của ứng dụng.

Jackson ghi JSON ra OutputStream bằng UTF-8 theo cấu hình generator thông thường. Nếu dùng Writer, hãy chỉ định charset rõ ràng:

```java
try (BufferedWriter output = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING
    );
    SequenceWriter sequence = mapper.writerFor(ProductDto.class)
        .writeValuesAsArray(output)) {

    sequence.writeAll(productIterator);
}
```

### 9.2. Ghi một giá trị ra OutputStream

Khi chỉ ghi một object:

```java
ObjectWriter writer = mapper.writerFor(ProductDto.class);

try (OutputStream output = Files.newOutputStream(path)) {
    writer.writeValue(output, product);
}
```

Không cần `SequenceWriter` nếu chỉ có một giá trị. Dùng API đơn giản nhất tương ứng với hợp đồng đầu ra.

### 9.3. Dùng JsonGenerator có sẵn

Nếu ứng dụng cần kiểm soát generator, có thể tạo generator trước rồi chuyển cho ObjectWriter:

```java
JsonFactory factory = mapper.getFactory();

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    ObjectWriter writer = mapper.writerFor(ProductDto.class);

    try (SequenceWriter sequence = writer.writeValuesAsArray(generator)) {
        sequence.writeAll(productIterator);
    }
}
```

Khi truyền generator có sẵn, ứng dụng chịu trách nhiệm quản lý vòng đời generator. `SequenceWriter` quản lý sequence và có thể được đóng để hoàn tất array; generator bên ngoài vẫn được đóng ở scope của ứng dụng.

Cách này hữu ích khi cần tùy chỉnh encoding, generator feature hoặc kết hợp ghi dữ liệu JSON với một pipeline streaming khác.

## 10. Quản lý tài nguyên và đóng SequenceWriter

`SequenceWriter` triển khai `Closeable`. Hãy đóng nó sau khi hoàn tất ghi.

Đóng writer quan trọng vì:

- Buffer có thể cần được flush.
- Generator có thể cần ghi token kết thúc.
- Ở chế độ array, dấu `]` được ghi khi sequence hoàn tất.
- Tài nguyên gắn với generator/output target cần được giải phóng theo cấu hình ownership.

Dùng try-with-resources:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    sequence.write(product1);
    sequence.write(product2);
}
```

Không chỉ gọi `flush()` rồi bỏ writer. Flush đẩy dữ liệu đang buffer ra output nhưng không thay thế thao tác close để hoàn tất cấu trúc array.

Khi tạo `SequenceWriter` từ một OutputStream/Writer, writer thường tạo generator riêng để quản lý output. Khi truyền một `JsonGenerator` có sẵn, ứng dụng cần quản lý generator bên ngoài. Hãy xác định rõ ai sở hữu stream/generator và không đóng cùng tài nguyên theo cách gây lỗi ở phần xử lý tiếp theo.

### 10.1. Flush định kỳ

Có thể gọi `sequence.flush()` khi cần đẩy dữ liệu ra output trước khi sequence kết thúc:

```java
try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    int count = 0;

    while (iterator.hasNext()) {
        sequence.write(iterator.next());
        count++;

        if (count % 1000 == 0) {
            sequence.flush();
        }
    }
}
```

Flush định kỳ có thể hữu ích khi consumer cần đọc dữ liệu trong lúc producer vẫn đang chạy hoặc khi output được truyền qua kết nối lâu dài. Tuy nhiên, flush quá thường xuyên có thể giảm hiệu năng do tăng số lần I/O. Hãy chọn chu kỳ theo yêu cầu độ trễ và throughput.

## 11. Ghi sequence từ nguồn dữ liệu lớn

Để tận dụng lợi ích của sequence writing, nguồn dữ liệu nên cung cấp phần tử theo từng bước.

### 11.1. Dùng Stream

Ví dụ với Java Stream:

```java
try (Stream<ProductDto> products = repository.streamAll()) {
    try (SequenceWriter sequence =
             mapper.writerFor(ProductDto.class)
                 .writeValuesAsArray(outputStream)) {

        sequence.writeAll(products.iterator());
    }
}
```

Stream được đóng sau khi ghi xong, giúp giải phóng tài nguyên nguồn như cursor hoặc kết nối được quản lý bởi repository. Thứ tự đóng resource trong try-with-resources là ngược thứ tự khai báo; trong ví dụ lồng nhau, sequence đóng trước rồi stream đóng.

Nếu Stream được tạo từ JPA hoặc database cursor, hãy bảo đảm transaction/session còn mở trong suốt thời gian duyệt. Không lấy Stream từ một transaction đã kết thúc rồi mới serialize.

### 11.2. Dùng phân trang

Nếu repository chỉ hỗ trợ paging, có thể đọc từng trang:

```java
try (SequenceWriter sequence =
         mapper.writerFor(ProductDto.class)
             .writeValuesAsArray(outputStream)) {

    int pageNumber = 0;
    Page<ProductDto> page;

    do {
        page = repository.findPage(
            PageRequest.of(pageNumber, 500)
        );

        sequence.writeAll(page.getContent());
        pageNumber++;
    } while (page.hasNext());
}
```

Cách này giới hạn số bản ghi được giữ cùng lúc theo kích thước trang. Mỗi trang vẫn có thể được giữ trong bộ nhớ, nhưng ứng dụng không cần nạp toàn bộ dữ liệu trước khi bắt đầu ghi.

Kích thước trang cần cân bằng giữa số lần truy vấn, memory footprint và thời gian xử lý. Nếu nguồn dữ liệu thay đổi trong lúc phân trang, cần cân nhắc tính nhất quán của snapshot và cách sắp xếp ổn định.

### 11.3. Xử lý lỗi khi đang ghi

Nếu serialize phần tử thứ N bị lỗi hoặc output stream gặp lỗi I/O, file có thể đã chứa một phần sequence. Với array mode, nếu writer chưa đóng thành công, file có thể thiếu dấu `]` và không phải JSON document hoàn chỉnh.

Với file export cần tính toàn vẹn, có thể ghi vào file tạm:

```java
Path temporary = Path.of("exports", "products.json.tmp");
Path destination = Path.of("exports", "products.json");

try (OutputStream output = Files.newOutputStream(
        temporary,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE
    );
    SequenceWriter sequence = mapper.writerFor(ProductDto.class)
        .writeValuesAsArray(output)) {

    sequence.writeAll(productIterator);
}

Files.move(
    temporary,
    destination,
    StandardCopyOption.REPLACE_EXISTING,
    StandardCopyOption.ATOMIC_MOVE
);
```

Chỉ thay thế file đích sau khi sequence đã ghi và đóng thành công. `ATOMIC_MOVE` phụ thuộc filesystem; nếu không được hỗ trợ, ứng dụng cần xử lý fallback phù hợp. Nếu export thất bại, file tạm có thể được giữ để chẩn đoán hoặc xóa theo chính sách vận hành.

## 12. Ghi nối tiếp vào file có sẵn

Không nên mặc định rằng mở OutputStream với chế độ append rồi gọi `writeValuesAsArray(...)` sẽ tạo được một JSON array hợp lệ. Array cần một dấu `[` ở đầu và một dấu `]` ở cuối. Ghi thêm một array mới vào cuối file sẽ tạo nhiều root document, không phải một array duy nhất.

Với JSON Lines, append có thể phù hợp hơn, nhưng ứng dụng phải quản lý delimiter ở ranh giới giữa batch cũ và batch mới. `withRootValueSeparator("\n")` chỉ tạo separator giữa các giá trị được ghi trong cùng sequence; nó không biết byte cuối file cũ là gì và không tự chèn separator trước phần tử đầu tiên của batch mới.

Trước khi append, cần xác định:

- File hiện có có kết thúc bằng newline không?
- Dòng cuối có phải một JSON value hoàn chỉnh không?
- Batch mới có bắt đầu bằng delimiter cần thiết không?
- Có nhiều writer đồng thời có thể ghi vào cùng file không?
- Có cần khóa file hoặc ghi vào file riêng rồi hợp nhất không?

Nếu không có nhu cầu append được thiết kế rõ, hãy tạo file mới hoặc ghi file tạm rồi thay thế file đích sau khi hoàn tất.

## 13. ObjectWriter và SequenceWriter có thể tái sử dụng như thế nào?

`ObjectWriter` là cấu hình serialize bất biến, nên có thể tạo trước và tái sử dụng cho nhiều lần ghi cùng kiểu dữ liệu:

```java
private final ObjectWriter productWriter =
    mapper.writerFor(ProductDto.class);
```

Mỗi lần export, tạo `SequenceWriter` mới cho output tương ứng:

```java
try (SequenceWriter sequence =
         productWriter.writeValuesAsArray(outputStream)) {
    sequence.writeAll(productIterator);
}
```

Không chia sẻ một `SequenceWriter` đang ghi giữa nhiều request hoặc nhiều thread. Nó giữ trạng thái của một sequence cụ thể, bao gồm generator, trạng thái array và ranh giới các phần tử.

Có thể chia sẻ `ObjectWriter` đã được tạo xong giữa các luồng theo cách dùng thông thường. Cũng như `ObjectMapper`, hãy hoàn tất cấu hình trước khi đưa writer vào sử dụng đồng thời.

## 14. Root wrapping và kiểu dữ liệu polymorphic

`ObjectWriter` có thể được cấu hình root wrapping hoặc serializer cho kiểu polymorphic. Nếu bật `SerializationFeature.WRAP_ROOT_VALUE`, mỗi giá trị được ghi có thể được bọc trong root object theo tên kiểu đã cấu hình.

Ví dụ, một phần tử có thể trở thành:

```json
{
  "product": {
    "id": 101,
    "name": "Keyboard"
  }
}
```

Nếu dùng `writeValuesAsArray`, array sẽ chứa từng root-wrapped value:

```json
[
  {
    "product": {
      "id": 101,
      "name": "Keyboard"
    }
  },
  {
    "product": {
      "id": 102,
      "name": "Mouse"
    }
  }
]
```

Chỉ bật root wrapping khi hợp đồng yêu cầu. Không nhầm wrapper của từng phần tử với array bao ngoài toàn sequence.

Với polymorphic type, mỗi phần tử có thể mang type metadata theo annotation/configuration của kiểu. Consumer cần có cấu hình tương ứng để deserialize. Đặc biệt, không cho dữ liệu không đáng tin cậy tùy ý quyết định class Java cần khởi tạo thông qua default typing thiếu kiểm soát.

## 15. Đọc lại các định dạng đã ghi

Cách đọc phụ thuộc định dạng đầu ra.

### 15.1. Đọc JSON array

Nếu ghi bằng `writeValuesAsArray`, có thể đọc lại toàn bộ array thành List:

```java
List<ProductDto> products = mapper.readValue(
    inputStream,
    new TypeReference<List<ProductDto>>() {}
);
```

Nếu file rất lớn và muốn đọc tuần tự, có thể dùng `JsonParser` hoặc `MappingIterator` để xử lý từng phần tử mà không materialize toàn bộ List.

### 15.2. Đọc JSON Lines

Với JSON Lines, mỗi dòng là một JSON document riêng. Có thể đọc từng dòng rồi deserialize:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
    )) {

    String line;

    while ((line = reader.readLine()) != null) {
        if (line.isBlank()) {
            continue;
        }

        ProductDto product = mapper.readValue(line, ProductDto.class);
        process(product);
    }
}
```

Cách này đơn giản và thể hiện rõ framing theo dòng. Với dòng cực lớn hoặc yêu cầu xử lý đặc biệt, có thể dùng parser/iterator thích hợp. Không đọc toàn bộ file JSON Lines thành một String rồi truyền cho `readValue(..., List.class)`, vì JSON Lines không phải một JSON array.

### 15.3. Đọc nhiều root value không có separator newline

Nếu sequence được ghi bằng separator khác, consumer phải biết chính xác quy ước framing đó. Một `JsonParser` có thể đọc nhiều root value nối tiếp bằng cách lặp `nextToken()`/`readValue` theo kiểu dữ liệu đã biết, nhưng phải xử lý delimiter và end-of-input đúng theo giao thức.

Không nên gửi sequence không bọc array tới consumer chỉ biết gọi một lần `readValue` cho một JSON document. Nếu consumer chỉ hỗ trợ một document, hãy dùng array mode hoặc một định dạng truyền tải có framing được quy định rõ.

## 16. So sánh ObjectWriter, SequenceWriter và writeValue

| API | Mục đích | Số giá trị |
| --- | --- | ---: |
| `ObjectMapper.writeValue(...)` | Ghi một giá trị với cấu hình mapper | Một |
| `ObjectWriter.writeValue(...)` | Ghi một giá trị với cấu hình writer cụ thể | Một |
| `ObjectWriter.writeValues(...)` | Tạo sequence writer không bọc array | Nhiều |
| `ObjectWriter.writeValuesAsArray(...)` | Tạo sequence writer có array bao ngoài | Nhiều |
| `SequenceWriter.write(...)` | Ghi một phần tử vào sequence | Một lần gọi |
| `SequenceWriter.writeAll(...)` | Ghi các phần tử từ array/Iterable/Iterator | Nhiều |

Cách chọn:

- Một object hoặc scalar: dùng `ObjectWriter.writeValue`.
- Nhiều object thành một JSON array: dùng `writeValuesAsArray`.
- Nhiều JSON value độc lập theo giao thức sequence: dùng `writeValues` và separator được quy định.
- JSON Lines: dùng `writeValues` với separator newline và record compact.
- File lớn: kết hợp SequenceWriter với iterator/cursor/stream để không materialize toàn bộ dữ liệu.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| File array thiếu dấu `]` | SequenceWriter chưa đóng hoặc có lỗi trước khi hoàn tất | Dùng try-with-resources và chỉ publish file sau khi close thành công |
| Output có nhiều object nối tiếp nhưng consumer parse lỗi | Dùng `writeValues` trong khi consumer mong một JSON document | Dùng `writeValuesAsArray` hoặc thống nhất định dạng sequence |
| JSON Lines bị tách một object thành nhiều dòng | Writer dùng pretty printer | Dùng compact writer cho NDJSON |
| Hai batch append dính vào nhau | Không thêm delimiter giữa file cũ và batch mới | Kiểm tra byte cuối và quản lý ranh giới batch |
| Bộ nhớ vẫn tăng cao khi export | Nguồn đã nạp toàn bộ List hoặc logic giữ lại mọi phần tử | Dùng iterator/cursor/paging và giải phóng tham chiếu |
| File có nội dung một phần sau exception | Lỗi serialize hoặc I/O giữa sequence | Ghi file tạm, đóng thành công rồi move sang đích |
| Output bị đóng quá sớm | Không rõ ownership của generator/output stream | Quản lý stream và generator theo một scope rõ ràng |
| Mỗi phần tử có wrapper không mong muốn | Bật root wrapping hoặc type metadata | Kiểm tra ObjectWriter và annotation/configuration |
| Các phần tử có hình dạng không đồng nhất | Ghi nhiều kiểu không có schema/discriminator rõ ràng | Dùng writer có kiểu hoặc envelope chung |
| Không thấy dữ liệu khi consumer đọc đồng thời | Buffer chưa được flush | Flush theo chu kỳ khi yêu cầu giao thức cần dữ liệu xuất hiện sớm |

Khi gặp lỗi, xác định trước output dự kiến là một array, JSON Lines hay sequence nhiều root value. Sau đó kiểm tra writer mode, separator, pretty printer và thời điểm close.

## 18. Bài thực hành tổng hợp

Xây dựng chức năng export sản phẩm từ repository:

```java
public record ProductExportDto(
    long id,
    String name,
    BigDecimal price
) {}
```

Thực hiện lần lượt:

1. Tạo `ObjectWriter` bằng `mapper.writerFor(ProductExportDto.class)`.
2. Ghi một sản phẩm bằng `writeValueAsString` và `writeValue`.
3. Tạo `SequenceWriter` bằng `writeValuesAsArray` và ghi ba sản phẩm bằng các lần gọi `write`.
4. Tạo một array khác bằng `writeAll(Iterable)` và `writeAll(Iterator)`.
5. Đọc lại file array thành `List<ProductExportDto>`.
6. Tạo JSON Lines bằng `withRootValueSeparator("\n")` và `writeValues`.
7. Đọc lại JSON Lines theo từng dòng.
8. Bật pretty printer cho array output và so sánh với JSON Lines compact.
9. Dùng Stream hoặc repository paging để ghi nhiều sản phẩm mà không gọi `findAll()` tạo một List lớn.
10. Cố ý tạo một phần tử gây lỗi serialize và quan sát file đầu ra chưa hoàn chỉnh.
11. Chuyển sang file tạm và chỉ move file khi sequence đóng thành công.
12. Thử append batch thứ hai vào JSON Lines; kiểm tra delimiter giữa hai batch.
13. Thử ghi array mode vào file đã có dữ liệu để thấy vì sao không thể append một array mới vào cuối tài liệu cũ.
14. Viết test xác nhận số phần tử, hình dạng root, thứ tự record và giá trị sau khi đọc lại.

Bài thực hành hoàn thành khi có thể chọn đúng writer mode cho hợp đồng đầu ra, ghi dữ liệu theo từng phần tử và xử lý được vòng đời file khi export thành công hoặc thất bại.

## 19. Nguyên tắc ghi nhớ

- `ObjectWriter` là cấu hình serialize có thể tái sử dụng; `SequenceWriter` là writer có trạng thái cho một sequence cụ thể.
- Dùng `writeValue` cho một giá trị; dùng `writeValues` hoặc `writeValuesAsArray` cho nhiều giá trị.
- `writeValuesAsArray` tạo một JSON document có root là array và tự quản lý dấu ngoặc/phân cách phần tử.
- `writeValues` ghi nhiều root value nối tiếp; toàn bộ sequence không phải một JSON document chuẩn đơn.
- `withRootValueSeparator("\n")` phù hợp để phân tách record JSON Lines compact; separator chỉ nằm giữa các root value.
- JSON Lines, JSON array và JSON Text Sequences là các định dạng khác nhau.
- `writeAll(Iterator)` cho phép ghi từ nguồn tuần tự; tránh tạo List lớn nếu mục tiêu là giảm bộ nhớ.
- Đóng `SequenceWriter` để flush và hoàn tất cấu trúc, đặc biệt khi ghi array.
- Không chia sẻ một SequenceWriter đang hoạt động giữa nhiều thread hoặc nhiều output.
- Khi export file quan trọng, ghi file tạm và publish sau khi sequence hoàn tất thành công.
- Quản lý rõ quyền sở hữu của SequenceWriter, JsonGenerator và OutputStream.
- Kiểm tra định dạng thực tế bằng cách đọc lại bằng consumer đúng với giao thức đã chọn.

Khi ghi nhiều giá trị, hãy xác định trước consumer cần một JSON array hay một sequence các JSON document, cấu hình `ObjectWriter` theo hợp đồng đó, rồi dùng `SequenceWriter` để ghi tuần tự và đóng đúng vòng đời output.
