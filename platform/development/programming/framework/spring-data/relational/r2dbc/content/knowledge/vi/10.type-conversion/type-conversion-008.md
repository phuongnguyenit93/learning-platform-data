# Xử lý dữ liệu nhị phân, Blob, Clob và vòng đời tài nguyên

Trong Spring Data Relational R2DBC, dữ liệu nhị phân và văn bản lớn có thể được ánh xạ thành các kiểu Java thông thường như `byte[]` và `String`, hoặc được xử lý dưới dạng các tài nguyên reactive `Blob` và `Clob` của R2DBC SPI. Hai cách tiếp cận có đặc điểm khác nhau về bộ nhớ, cách đọc dữ liệu và vòng đời connection.

Với dữ liệu nhỏ, `byte[]` hoặc `String` thường đơn giản và dễ dùng. Với dữ liệu lớn, việc materialize toàn bộ nội dung vào heap có thể gây áp lực bộ nhớ. `Blob` và `Clob` cho phép đọc/ghi theo luồng, nhưng chúng là các handle gắn với tài nguyên của driver/database. Ứng dụng cần tiêu thụ hoặc discard chúng đúng cách, trong thời gian connection còn hợp lệ, và phải xử lý cleanup khi publisher hoàn tất, phát lỗi hoặc bị hủy.

## 1. Phân biệt dữ liệu nhị phân và dữ liệu ký tự lớn

Database có nhiều kiểu cột để lưu nội dung lớn. Tên và hành vi cụ thể phụ thuộc hệ quản trị:

| Loại nội dung | Kiểu Java thường gặp | Kiểu SQL ví dụ | Đặc điểm |
|---|---|---|---|
| Dữ liệu nhị phân nhỏ hoặc vừa | `byte[]` | `BINARY`, `VARBINARY`, `BYTEA` | Toàn bộ nội dung được giữ trong một mảng byte |
| Dữ liệu nhị phân lớn | R2DBC `Blob` | `BLOB`, `BYTEA` hoặc kiểu LOB riêng của database | Có thể đọc/ghi theo luồng các `ByteBuffer` |
| Văn bản nhỏ hoặc vừa | `String` | `VARCHAR`, `TEXT`, `CLOB` | Toàn bộ nội dung được giữ trong một chuỗi Java |
| Văn bản lớn | R2DBC `Clob` | `CLOB`, `TEXT` hoặc kiểu văn bản lớn riêng | Có thể đọc/ghi theo luồng các `CharSequence` |

Ví dụ, PostgreSQL thường dùng `BYTEA` cho dữ liệu nhị phân và `TEXT` cho văn bản dài; MySQL có các biến thể `BLOB` và `TEXT`; Oracle có các kiểu LOB như `BLOB` và `CLOB`. Cách driver biểu diễn những cột này thành `byte[]`, `String`, `Blob` hoặc `Clob` không hoàn toàn giống nhau. Hãy kiểm tra tài liệu của database và R2DBC driver cụ thể.

Không nên chọn kiểu Java chỉ dựa trên tên SQL. Cần xác định driver có hỗ trợ kiểu đó, kích thước dữ liệu tối đa, cách truyền dữ liệu và yêu cầu streaming của ứng dụng.

## 2. byte[] và String: cách đơn giản cho dữ liệu có giới hạn

Với một ảnh nhỏ, mã băm, tài liệu ngắn hoặc nội dung văn bản có kích thước giới hạn, dùng `byte[]` và `String` có thể là lựa chọn phù hợp.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("document_metadata")
public class DocumentMetadata {

    @Id
    private Long id;

    private String fileName;

    private String contentType;

    private byte[] preview;

    private String description;
}
```

`preview` chứa dữ liệu nhị phân; `description` chứa văn bản. Khi driver hỗ trợ mapping tương ứng, Spring Data Relational có thể đọc/ghi các thuộc tính này như giá trị thông thường.

### 2.1. Ưu điểm và giới hạn

Ưu điểm:

- Mô hình Java đơn giản, dễ truyền giữa các tầng.
- Dễ kiểm thử và dễ serialize khi kích thước nhỏ.
- Không cần tự quản lý publisher của LOB.
- Phù hợp với metadata, thumbnail hoặc payload đã có giới hạn kích thước rõ ràng.

Giới hạn:

- Toàn bộ nội dung phải được materialize trong bộ nhớ.
- `byte[]` cần một vùng nhớ liên tục đủ lớn.
- `String` cũng cần giữ toàn bộ nội dung và có overhead biểu diễn ký tự trong JVM.
- Khi nhiều request cùng tải file lớn, heap có thể tăng mạnh dù database và connection pool vẫn hoạt động bình thường.
- Việc trả về một `Mono<byte[]>` không làm thao tác đọc dữ liệu trở thành streaming chỉ vì API là reactive.

Ví dụ, nếu một endpoint tải file 80 MB và có 30 request đồng thời, chỉ riêng nội dung file có thể cần khoảng 2,4 GB bộ nhớ thô, chưa tính object overhead, buffer, bản sao khi chuyển đổi và các dữ liệu khác. Vì vậy, cần giới hạn kích thước khi dùng `byte[]` hoặc `String`.

### 2.2. Đặt giới hạn kích thước

Nếu nghiệp vụ chỉ cho phép preview tối đa 1 MB, hãy kiểm tra kích thước trước khi lưu và trước khi đọc. Không nên tin một giá trị `Content-Length` do client gửi mà không xác nhận kích thước dữ liệu thực tế.

Với nội dung văn bản, hãy cân nhắc giới hạn theo số byte khi truyền qua mạng và số ký tự sau giải mã. UTF-8 có số byte khác số ký tự, nên hai giới hạn này không đồng nhất.

## 3. Blob và Clob trong R2DBC SPI

R2DBC SPI cung cấp hai abstraction cho nội dung lớn:

- `io.r2dbc.spi.Blob`: biểu diễn nội dung nhị phân lớn.
- `io.r2dbc.spi.Clob`: biểu diễn nội dung ký tự lớn.

Đây là các kiểu reactive. Chúng không đơn thuần là một mảng byte hoặc chuỗi đã được tải hoàn toàn vào heap.

Các API quan trọng:

| Kiểu | Đọc nội dung | Bỏ qua nội dung và giải phóng tài nguyên |
|---|---|---|
| `Blob` | `stream()` trả publisher của `ByteBuffer` | `discard()` trả publisher hoàn tất khi discard xong |
| `Clob` | `stream()` trả publisher của `CharSequence` | `discard()` trả publisher hoàn tất khi discard xong |

Ví dụ chữ ký sử dụng:

```java
import io.r2dbc.spi.Blob;
import io.r2dbc.spi.Clob;

Flux<ByteBuffer> binaryChunks = Flux.from(blob.stream());
Flux<CharSequence> textChunks = Flux.from(clob.stream());
```

`stream()` phát các chunk theo kiểu reactive. Một chunk không nhất thiết tương ứng với một hàng database, một packet mạng hoặc một kích thước cố định. Driver quyết định cách phân đoạn dữ liệu.

### 3.1. Blob dùng cho dữ liệu nhị phân

`Blob` phù hợp với nội dung như ảnh gốc, file PDF, tệp đính kèm, nội dung media hoặc dữ liệu nhị phân lớn khác.

```java
Publisher<ByteBuffer> source = ...;
Blob blob = Blob.from(source);
```

`Blob.from(...)` tạo một Blob từ publisher các `ByteBuffer`. Publisher nguồn được tiêu thụ khi driver thực hiện thao tác ghi. Hãy đảm bảo nguồn có thể được subscribe theo vòng đời của thao tác và không tái sử dụng một nguồn one-shot cho nhiều lần ghi.

### 3.2. Clob dùng cho dữ liệu ký tự

`Clob` phù hợp với nội dung văn bản lớn như nội dung bài viết, tài liệu text hoặc dữ liệu ký tự dài.

```java
Publisher<CharSequence> source = ...;
Clob clob = Clob.from(source);
```

Clob phát các đoạn `CharSequence`. Việc mã hóa ký tự khi truyền đến database do driver xử lý theo hợp đồng của driver và database. Không tự chuyển từng chunk thành byte theo một charset tùy ý nếu chưa xác định cách mã hóa mà cột và driver yêu cầu.

## 4. Đọc Blob và Clob theo luồng

Khi đọc một LOB, ứng dụng có thể nhận `Blob` hoặc `Clob` từ `Row`. Cần tiêu thụ stream trong phạm vi connection còn hoạt động.

Ví dụ lấy một `Blob` từ hàng kết quả ở mức R2DBC SPI:

```java
connection.createStatement("SELECT content FROM document WHERE id = $1")
    .bind(0, documentId)
    .execute();
```

Đoạn trên minh họa việc tạo statement theo cú pháp bind marker của PostgreSQL. Tên marker và cách bind vị trí phụ thuộc driver; không phải cú pháp SQL này dùng được cho mọi hệ quản trị.

Một mẫu streaming hoàn chỉnh hơn giữ connection trong khi chunk được tiêu thụ:

```java
Flux<ByteBuffer> streamDocument(
        ConnectionFactory connectionFactory,
        long documentId) {

    return Flux.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Flux.from(
                connection.createStatement(
                    "SELECT content FROM document WHERE id = $1")
                    .bind(0, documentId)
                    .execute())
            .concatMap(result -> Flux.from(result.map(
                (row, metadata) -> row.get("content", Blob.class))))
            .concatMap(blob -> Flux.from(blob.stream())),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Trong ví dụ:

- `ConnectionFactory.create()` cấp connection theo mô hình reactive.
- `Flux.usingWhen(...)` giữ connection trong suốt thời gian publisher đọc dữ liệu còn hoạt động.
- `Result.map(...)` lấy `Blob` từ cột `content`.
- `blob.stream()` phát các chunk `ByteBuffer`.
- Cleanup đóng/trả connection khi luồng hoàn tất, phát lỗi hoặc bị hủy.

Ví dụ giả định truy vấn trả về một hàng có cột `content` không null. Trong code thực tế cần xử lý trường hợp không có hàng, cột null, nhiều hàng và kiểu LOB mà driver thực sự trả về.

**Không nên lấy `Blob` từ một truy vấn, phát handle đó ra ngoài rồi mới đọc stream sau khi thao tác database đã kết thúc.** LOB có thể phụ thuộc vào connection hoặc tài nguyên driver. Nếu connection đã được trả về pool hoặc đóng, việc đọc tiếp có thể thất bại. Hãy đọc hoặc discard LOB trong phạm vi connection được giữ sống.

### 4.1. Khi chỉ cần bỏ qua LOB

Nếu câu truy vấn trả về một LOB nhưng nghiệp vụ không cần nội dung, hãy discard nó thay vì giữ handle không sử dụng:

```java
Mono<Void> discardDocumentContent(Connection connection, long documentId) {
    return Flux.from(connection.createStatement(
            "SELECT content FROM document WHERE id = $1")
            .bind(0, documentId)
            .execute())
        .concatMap(result -> Flux.from(result.map(
            (row, metadata) -> row.get("content", Blob.class))))
        .concatMap(blob -> Mono.from(blob.discard()))
        .then();
}
```

`discard()` là một thao tác reactive, cần được subscribe/compose để việc giải phóng hoàn tất. Gọi method mà không nối publisher vào pipeline không bảo đảm tài nguyên đã được giải phóng.

### 4.2. Clob cũng cần được tiêu thụ trong connection scope

Mẫu xử lý Clob tương tự Blob, nhưng stream phát `CharSequence`:

```java
Flux<CharSequence> streamDocumentText(
        ConnectionFactory connectionFactory,
        long documentId) {

    return Flux.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Flux.from(
                connection.createStatement(
                    "SELECT body FROM document_text WHERE id = $1")
                    .bind(0, documentId)
                    .execute())
            .concatMap(result -> Flux.from(result.map(
                (row, metadata) -> row.get("body", Clob.class))))
            .concatMap(clob -> Flux.from(clob.stream())),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Nếu ứng dụng cần ghép toàn bộ Clob thành một `String`, hãy chỉ làm vậy khi kích thước có giới hạn. Với nội dung lớn, xử lý từng chunk hoặc ghi sang một sink phù hợp để tránh tạo một chuỗi khổng lồ trong heap.

## 5. Ghi Blob và Clob

R2DBC SPI cho phép tạo Blob/Clob từ publisher để truyền dữ liệu theo luồng vào câu lệnh.

### 5.1. Ghi Blob

```java
Mono<Long> saveBinary(
        DatabaseClient databaseClient,
        String fileName,
        Flux<ByteBuffer> content) {

    return Mono.defer(() -> {
        Blob blob = Blob.from(content);

        return databaseClient.sql("""
                INSERT INTO document(file_name, content)
                VALUES (:fileName, :content)
                """)
            .bind("fileName", fileName)
            .bind("content", blob)
            .fetch()
            .rowsUpdated();
    });
}
```

`Mono.defer` tạo Blob khi subscription bắt đầu, giúp mỗi lần thực thi có một publisher nguồn mới theo cách caller cung cấp. Nếu `content` là publisher one-shot hoặc phụ thuộc stream đã bị tiêu thụ, không thể mặc định subscribe lại sẽ tạo ra cùng nội dung. Cần xác định rõ publisher nguồn có thể được sử dụng bao nhiêu lần.

Việc bind `Blob` chỉ hoạt động khi driver và database hỗ trợ kiểu LOB tương ứng. Với database/driver chỉ hỗ trợ dữ liệu nhị phân dưới dạng `byte[]`, cần dùng kiểu đó hoặc cơ chế riêng của driver.

### 5.2. Ghi Clob

```java
Mono<Long> saveText(
        DatabaseClient databaseClient,
        String title,
        Flux<CharSequence> bodyChunks) {

    return Mono.defer(() -> {
        Clob clob = Clob.from(bodyChunks);

        return databaseClient.sql("""
                INSERT INTO article(title, body)
                VALUES (:title, :body)
                """)
            .bind("title", title)
            .bind("body", clob)
            .fetch()
            .rowsUpdated();
    });
}
```

Trong ví dụ, `bodyChunks` cung cấp nội dung theo từng đoạn. Cần kiểm tra driver có hỗ trợ bind `Clob` hay không và cột `body` có kiểu phù hợp.

### 5.3. Không tự chuyển toàn bộ stream thành byte[] trước khi bind

Nếu nguồn dữ liệu đã là `Flux<ByteBuffer>`, việc gọi `collectList()` hoặc `reduce` thành `byte[]` trước khi ghi sẽ làm mất lợi ích streaming. Chỉ materialize khi kích thước được giới hạn và việc giữ toàn bộ nội dung trong heap là lựa chọn có chủ đích.

## 6. Vòng đời tài nguyên của Blob và Clob

LOB cần được xem là tài nguyên có vòng đời, không phải một object dữ liệu thông thường có thể giữ tùy ý.

Các nguyên tắc chính:

1. **Tiêu thụ hoặc discard.** Sau khi nhận `Blob`/`Clob`, ứng dụng cần đọc stream hoặc gọi `discard()` nếu không cần nội dung.
2. **Giữ connection trong thời gian cần thiết.** Một số driver cần connection còn mở để đọc hoặc ghi LOB. Không phát handle ra ngoài rồi dùng sau khi connection đã được release.
3. **Compose reactive cleanup.** `stream()`, `discard()` và `Connection.close()` đều là publisher; phải nối chúng vào pipeline.
4. **Xử lý cancellation.** Nếu client ngừng tải hoặc subscriber hủy, cleanup phải được chạy để giải phóng LOB và connection.
5. **Không dùng lại handle đã tiêu thụ.** Publisher của LOB có thể chỉ dùng một lần hoặc phụ thuộc trạng thái driver; không giả định có thể subscribe nhiều lần.
6. **Không giữ ByteBuffer quá thời gian cần thiết.** Sao chép dữ liệu nếu cần lưu lại sau tín hiệu hiện tại, vì buffer có thể gắn với cơ chế quản lý bộ nhớ của driver.

### 6.1. Vì sao cần xử lý cả complete, error và cancel?

Reactive pipeline có ba kết thúc quan trọng:

- `onComplete`: stream đọc xong bình thường.
- `onError`: driver hoặc ứng dụng phát lỗi khi đọc/ghi.
- `cancel`: downstream không cần dữ liệu nữa, ví dụ client đóng kết nối HTTP.

Nếu chỉ cleanup khi complete, lỗi hoặc cancellation có thể để lại connection hoặc LOB chưa được giải phóng. Các toán tử `usingWhen` của Reactor hỗ trợ cleanup theo những tín hiệu này.

Ví dụ khung quản lý connection:

```java
Flux<ByteBuffer> content = Flux.usingWhen(
    Mono.from(connectionFactory.create()),
    connection -> readBlobChunks(connection),
    connection -> Mono.from(connection.close()),
    (connection, error) -> Mono.from(connection.close()),
    connection -> Mono.from(connection.close())
);
```

Ba callback cuối lần lượt xử lý complete, error và cancel. Nếu có LOB chưa tiêu thụ hết, ứng dụng cần dùng cơ chế discard/cleanup phù hợp với driver trước khi connection được tái sử dụng. Việc đóng/trả connection thường là lớp bảo vệ cuối cùng, nhưng không nên thay thế hiểu biết về vòng đời LOB của driver.

### 6.2. Connection.close() khi dùng pool

Khi connection được lấy từ R2DBC Pool, gọi `close()` thường trả connection về pool để tái sử dụng, không nhất thiết đóng socket vật lý ngay lập tức. Pool có thể kiểm tra hoặc loại bỏ connection sau đó. Khi tự quản lý connection, hãy dùng `ConnectionFactory`/pool đúng cách và không tự giữ connection qua nhiều request.

Với `DatabaseClient`, Spring quản lý việc acquire và release connection cho thao tác thông thường. Nếu xử lý LOB yêu cầu stream còn sống sau khi câu query đã phát ra kết quả, cần thiết kế thao tác sao cho việc tiêu thụ LOB diễn ra trong phạm vi connection của driver. Khi cần kiểm soát rõ phạm vi đó, API R2DBC SPI trực tiếp với `usingWhen` có thể phù hợp hơn một mapper trả về handle LOB.

## 7. Giới hạn bộ nhớ khi chuyển đổi dữ liệu

Có ba kiểu xử lý phổ biến:

| Cách xử lý | Bộ nhớ phía ứng dụng | Phù hợp |
|---|---|---|
| Đọc thành `byte[]` hoặc `String` | Tăng theo kích thước toàn bộ nội dung | Dữ liệu nhỏ, có giới hạn |
| Đọc `Blob`/`Clob` theo chunk và xử lý ngay | Có thể giữ gần mức chunk/buffer đang xử lý | Nội dung lớn, streaming |
| Đọc stream rồi `collectList()`/ghép thành một object | Cuối cùng vẫn giữ toàn bộ nội dung | Chỉ khi kích thước được giới hạn và cần materialize |

Ví dụ chuyển stream Blob thành `byte[]`:

```java
Mono<byte[]> collectSmallBlob(Flux<ByteBuffer> chunks) {
    return chunks
        .reduce(new ByteArrayOutputStream(), (output, buffer) -> {
            ByteBuffer copy = buffer.slice();
            byte[] bytes = new byte[copy.remaining()];
            copy.get(bytes);
            output.write(bytes, 0, bytes.length);
            return output;
        })
        .map(ByteArrayOutputStream::toByteArray);
}
```

Đoạn code sao chép từng chunk vào `ByteArrayOutputStream`, sau đó tạo một mảng kết quả. Đây vẫn là thao tác materialize toàn bộ dữ liệu; chỉ dùng cho nội dung nhỏ hoặc đã có giới hạn kích thước. `ByteBuffer.slice()` giúp đọc một view của vùng còn lại mà không thay đổi position của buffer gốc.

Với file lớn, hãy xử lý từng chunk rồi ghi đến đích streaming như file system, object storage hoặc HTTP response. Không nên giữ toàn bộ file trong `ByteArrayOutputStream` nếu mục tiêu là tiết kiệm heap.

## 8. Tích hợp với WebFlux và truyền file cho client

Trong ứng dụng WebFlux, có thể trả nội dung theo stream để tránh tạo một mảng byte khổng lồ. Tuy nhiên, cần cân nhắc rằng connection database có thể phải được giữ trong suốt thời gian client tải dữ liệu.

Luồng tổng quát:

```text
HTTP client
    |
    v
WebFlux handler
    |
    v
Reactive service
    |
    v
R2DBC connection được giữ trong usingWhen
    |
    v
Blob.stream() phát ByteBuffer theo chunk
    |
    v
Chuyển chunk sang DataBuffer / response body
    |
    v
HTTP client nhận nội dung
    |
    v
Complete hoặc cancel -> cleanup LOB và connection
```

Spring WebFlux thường dùng `DataBuffer` để ghi response body. Khi chuyển từ `ByteBuffer`, hãy dùng buffer factory phù hợp và tuân thủ quy tắc ownership/release của `DataBuffer` trong phiên bản Spring đang dùng. Không tự release hoặc giữ buffer sau thời gian mà framework/driver cho phép.

Một client tải rất chậm có thể kéo dài thời gian giữ connection. Nếu file lớn và số lượt tải đồng thời cao, điều này có thể làm pool cạn dù mỗi truy vấn SQL rất nhanh. Cần cân nhắc:

- Dùng giới hạn kích thước và giới hạn số lượt tải đồng thời.
- Dùng timeout phù hợp cho việc tải file.
- Dùng object storage/CDN cho file lớn hoặc tải lặp lại nhiều lần.
- Lưu metadata trong database và nội dung file ở hệ lưu trữ chuyên dụng.
- Nếu phải stream từ database, theo dõi thời gian giữ connection và pending acquire.

Không phải lúc nào lưu file trực tiếp trong database cũng là lựa chọn tốt. Database phù hợp khi cần transaction nhất quán giữa metadata và nội dung, quyền truy cập theo dữ liệu, backup chung hoặc yêu cầu nghiệp vụ cụ thể. Object storage thường phù hợp với file rất lớn, tải nhiều lần hoặc cần phân phối qua CDN.

## 9. Chọn giữa byte[], Blob, String và Clob

Hãy chọn theo kích thước, driver và cách ứng dụng tiêu thụ dữ liệu:

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Ảnh thumbnail nhỏ | `byte[]` | Đơn giản và kích thước có giới hạn |
| File đính kèm lớn | `Blob` | Đọc/ghi theo chunk, giảm nhu cầu materialize |
| Mô tả hoặc ghi chú ngắn | `String` | Dễ thao tác và mapping |
| Nội dung văn bản rất dài | `Clob` | Có thể xử lý theo chunk ký tự |
| Chỉ cần metadata file | Các cột thông thường như tên, MIME type, size, checksum | Không cần tải nội dung LOB |
| Tải file nhiều lần với kích thước lớn | Object storage, database lưu metadata | Giảm thời gian giữ connection database |

Không có một ngưỡng kích thước cố định cho mọi ứng dụng. Hãy đo heap, số request đồng thời, tốc độ network, độ trễ database và chi phí chuyển đổi. Một payload 100 KB có thể được materialize an toàn trong một workload, nhưng cùng cách làm có thể gây áp lực nếu hàng nghìn request đồng thời.

## 10. Mapping trong Spring Data Relational và hỗ trợ của driver

Spring Data Relational dùng mapping metadata và converter để chuyển đổi giữa entity với kiểu dữ liệu mà R2DBC driver hỗ trợ. Tuy nhiên, khả năng ánh xạ `byte[]`, `String`, `Blob` hoặc `Clob` phụ thuộc vào phiên bản Spring Data, R2DBC SPI và driver.

Trước khi đặt LOB trực tiếp vào entity, cần xác nhận:

- Driver có hỗ trợ kiểu SQL tương ứng không.
- Driver trả về `byte[]`/`String` hay `Blob`/`Clob`.
- Spring Data converter có chuyển đổi kiểu đó tự động hay không.
- Mapping có tiêu thụ LOB trong connection scope phù hợp không.
- Có cần custom converter hoặc thao tác `DatabaseClient`/R2DBC SPI trực tiếp không.

Nếu cần custom conversion, có thể đăng ký converter thông qua `R2dbcCustomConversions` theo cơ chế cấu hình của Spring Data R2DBC. Converter cần tôn trọng bản chất reactive và vòng đời LOB. Không nên viết converter đồng bộ gọi `block()` để gom toàn bộ LOB thành `byte[]` nếu dữ liệu có thể lớn.

JPA có annotation `@Lob`, nhưng không nên mặc định annotation JPA đó điều khiển mapping R2DBC. Spring Data Relational sử dụng mapping và converter riêng. Hãy dùng các kiểu và annotation được Spring Data Relational/R2DBC hỗ trợ, đồng thời xác nhận hành vi trên driver thật.

Với `DatabaseClient`, mapper do ứng dụng viết có thể chủ động lấy `byte[]`, `String`, `Blob` hoặc `Clob`:

```java
databaseClient.sql("SELECT id, content FROM document WHERE id = :id")
    .bind("id", documentId)
    .map((row, metadata) -> row.get("content", byte[].class))
    .one();
```

Ví dụ chỉ phù hợp khi driver hỗ trợ trả cột `content` thành `byte[]` và nội dung có kích thước đủ nhỏ. Nếu driver trả về LOB handle, hãy đọc stream trong connection scope thay vì giả định `row.get(..., byte[].class)` luôn chuyển đổi được.

## 11. Xử lý dữ liệu nhị phân an toàn

Dữ liệu nhị phân thường là file do client gửi lên. Ngoài mapping và streaming, ứng dụng cần xác định chính xác kích thước, kiểu nội dung và quyền truy cập.

Các nguyên tắc thực tế:

- Không tin tên file hoặc MIME type do client gửi; xác minh theo chính sách của ứng dụng.
- Giới hạn kích thước upload trước khi nội dung chiếm quá nhiều tài nguyên.
- Tính checksum khi stream nếu cần phát hiện nội dung lỗi hoặc hỗ trợ deduplication.
- Không log byte nội dung, token hoặc dữ liệu nhạy cảm.
- Không đưa file upload vào bộ nhớ toàn bộ nếu đã có nguồn `Flux<ByteBuffer>`.
- Xác định encoding rõ ràng khi chuyển dữ liệu ký tự thành byte và ngược lại.
- Với file có cấu trúc, kiểm tra định dạng thực tế thay vì chỉ dựa vào phần mở rộng.
- Cân nhắc mã hóa at-rest, quyền truy cập và chính sách lưu trữ/xóa dữ liệu.

Nếu nội dung được lưu trong database cùng metadata, hãy xác định transaction có cần bao trùm cả hai thao tác hay không. Với object storage, database và object store thường không có một transaction ACID chung; cần thiết kế trạng thái upload, cleanup file mồ côi và retry/idempotency phù hợp.

## 12. Xử lý lỗi và cancellation khi đọc/ghi LOB

LOB streaming có thể lỗi giữa chừng do network reset, database timeout, client ngắt kết nối hoặc lỗi đọc buffer. Lỗi có thể xuất hiện sau khi một số chunk đã được gửi tới downstream.

Ứng dụng cần:

1. Để lỗi được truyền trong reactive pipeline.
2. Đảm bảo cleanup của LOB và connection chạy khi error hoặc cancel.
3. Không trả về một file được coi là hoàn chỉnh nếu stream bị ngắt giữa chừng.
4. Nếu ghi file ra hệ thống ngoài, ghi vào file tạm hoặc object key tạm rồi chỉ công bố khi hoàn tất.
5. Nếu cần retry, xác định có thể bắt đầu lại từ đầu hay cần hỗ trợ resume/range.
6. Với thao tác ghi database, xác định transaction đã commit hay chưa trước khi thực hiện lại để tránh bản ghi hoặc file trùng.

Với dữ liệu lớn, retry toàn bộ stream có thể rất tốn kém. Nếu hệ thống cần tiếp tục tải từ vị trí đã đọc, phải thiết kế protocol resume, offset hoặc multipart upload; R2DBC `Blob`/`Clob` không tự cung cấp một cơ chế resume nghiệp vụ tổng quát.

## 13. Kiểm thử và quan sát

Kiểm thử LOB cần chạy với database và driver thực tế vì cách biểu diễn và streaming phụ thuộc implementation.

Các tình huống nên kiểm tra:

- Lưu và đọc một Blob nhỏ bằng kiểu được driver hỗ trợ.
- Lưu và đọc một Blob lớn theo nhiều chunk.
- Lưu và đọc Clob có ký tự Unicode, dấu tiếng Việt và ký tự nhiều byte.
- Nội dung rỗng và cột nullable.
- Hủy subscription giữa lúc stream đang chạy.
- Mất kết nối hoặc timeout khi đang đọc/ghi.
- Discard LOB mà ứng dụng không cần tiêu thụ.
- Xác nhận connection được trả về pool sau complete, error và cancel.
- Tải nhiều LOB đồng thời và quan sát heap, GC, pool acquire và thời gian giữ connection.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Kích thước nội dung | Phát hiện payload vượt giới hạn |
| Số chunk và kích thước chunk | Hiểu cách driver phân đoạn dữ liệu |
| Thời gian stream | Phân biệt database chậm và downstream chậm |
| Connection hold time | Thời gian connection bị giữ trong khi truyền LOB |
| Pool pending acquire | Phát hiện LOB stream giữ quá nhiều connection |
| Heap/GC | Phát hiện vô tình materialize toàn bộ nội dung |
| Số cancellation và lỗi stream | Đánh giá khả năng cleanup và độ ổn định |

Không chỉ kiểm tra rằng file trả về đúng nội dung. Cần xác nhận ứng dụng không giữ connection hoặc buffer sau khi stream kết thúc.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đọc file lớn thành `byte[]` | Heap tăng theo kích thước file và số request | Dùng `Blob.stream()` hoặc object storage |
| Gom toàn bộ chunk bằng `collectList()` | Mất lợi ích streaming và giữ dữ liệu trong bộ nhớ | Xử lý từng chunk hoặc ghi đến sink |
| Phát `Blob` ra ngoài rồi đọc sau khi connection đã release | LOB có thể không còn truy cập được | Tiêu thụ LOB trong connection scope |
| Không gọi `discard()` khi bỏ qua LOB | Tài nguyên driver/database có thể chưa được giải phóng | Compose `discard()` trong pipeline |
| Gọi `discard()` nhưng không subscribe | Publisher cleanup không được thực thi | Nối publisher vào pipeline hoặc await trong reactive flow |
| Chỉ cleanup khi complete | Error/cancel có thể để lại tài nguyên | Dùng `usingWhen` và cleanup cho cả ba tín hiệu |
| Giữ `ByteBuffer` để dùng sau | Buffer có thể gắn với vòng đời driver | Xử lý ngay hoặc copy dữ liệu cần giữ |
| Giả định mọi driver hỗ trợ Blob/Clob giống nhau | Lỗi mapping hoặc bind runtime | Kiểm tra tài liệu và integration test của driver |
| Dùng JPA `@Lob` để cấu hình R2DBC | Annotation có thể không có tác dụng trong mapping R2DBC | Dùng kiểu và conversion được Spring Data Relational hỗ trợ |
| Stream file chậm qua connection pool nhỏ | Connection bị giữ lâu, request khác chờ acquire | Giới hạn concurrency, thời gian stream hoặc chuyển file sang object storage |
| Retry stream ghi không idempotent | Có thể ghi nội dung trùng hoặc trạng thái dở dang | Dùng transaction, idempotency key và quy trình upload rõ ràng |

## 15. Quy trình lựa chọn và triển khai

Khi thiết kế chức năng lưu hoặc tải dữ liệu lớn, có thể đi theo trình tự:

1. **Xác định loại dữ liệu:** nhị phân hay văn bản, có cần giữ nguyên byte hay cần xử lý ký tự.
2. **Xác định kích thước:** kích thước trung bình, tối đa và số request đồng thời dự kiến.
3. **Kiểm tra database và driver:** kiểu SQL, kiểu Java được hỗ trợ và khả năng Blob/Clob streaming.
4. **Chọn representation:** `byte[]`/`String` cho nội dung nhỏ có giới hạn; `Blob`/`Clob` hoặc object storage cho nội dung lớn.
5. **Thiết kế connection scope:** giữ connection trong thời gian cần đọc/ghi LOB và release trên complete/error/cancel.
6. **Thiết kế giới hạn tải:** upload size, concurrency, timeout, pool capacity và thời gian stream.
7. **Thiết kế lỗi và tính nhất quán:** cleanup, retry, idempotency và xử lý file chưa hoàn tất.
8. **Kiểm thử với driver thật:** xác nhận mapping, streaming, Unicode, cancellation và tài nguyên được giải phóng.
9. **Theo dõi production:** heap, GC, kích thước file, connection hold time, pending acquire và lỗi stream.

## 16. Nguyên tắc cần nhớ

- `byte[]` và `String` đơn giản nhưng materialize toàn bộ nội dung; chỉ dùng khi kích thước được giới hạn.
- `Blob` biểu diễn dữ liệu nhị phân lớn và phát `ByteBuffer` theo reactive stream.
- `Clob` biểu diễn dữ liệu ký tự lớn và phát `CharSequence` theo reactive stream.
- Driver/database quyết định khả năng hỗ trợ và cách ánh xạ kiểu LOB; không giả định mọi driver giống nhau.
- Tiêu thụ hoặc discard LOB trong khi connection còn hoạt động.
- Không phát LOB handle ra ngoài connection scope rồi mới đọc stream.
- Dùng `usingWhen` hoặc cơ chế resource management tương ứng để cleanup khi complete, error và cancel.
- Không gọi `block()` để tiêu thụ LOB trong pipeline reactive.
- Tránh `collectList()` hoặc gom toàn bộ nội dung nếu mục tiêu là streaming.
- Theo dõi thời gian giữ connection vì client tải chậm có thể làm pool cạn.
- Cân nhắc object storage cho file lớn, tải nhiều lần hoặc cần CDN.
- Kiểm thử bằng database và driver thật, bao gồm cancellation và cleanup.

Xử lý LOB trong Spring Data R2DBC không chỉ là chọn `byte[]`, `Blob` hay `Clob`. Điều quan trọng là cân bằng giữa kích thước dữ liệu, cách driver truyền nội dung, bộ nhớ và vòng đời connection. Dữ liệu nhỏ có giới hạn thường phù hợp với kiểu Java thông thường; dữ liệu lớn cần streaming, cleanup reactive và giới hạn tải rõ ràng để ứng dụng không giữ connection hoặc bộ nhớ lâu hơn mức cần thiết.
