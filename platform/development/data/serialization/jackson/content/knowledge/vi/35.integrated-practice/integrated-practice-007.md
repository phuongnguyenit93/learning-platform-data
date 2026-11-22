# Ghi JSON theo luồng và xử lý lỗi khi đầu ra chưa hoàn tất

Khi serialize một object nhỏ, gọi `ObjectMapper.writeValueAsString()` rồi trả về chuỗi thường rất tiện. Nhưng với batch lớn, export file hoặc response có nhiều record, tạo toàn bộ JSON trong một String hay byte array có thể làm tăng mạnh bộ nhớ và độ trễ. Ghi trực tiếp qua `OutputStream` hoặc `JsonGenerator` giúp dữ liệu đi ra theo từng phần, giảm nhu cầu giữ toàn bộ output trong heap.

Streaming output cũng tạo ra một vấn đề vận hành: nếu serializer, nguồn dữ liệu hoặc output stream thất bại giữa chừng, đích có thể đã nhận một phần JSON. Một phần JSON không nhất thiết là một tài liệu hợp lệ; ngay cả khi generator tự đóng dấu ngoặc lúc close, nội dung có thể vẫn thiếu record. Vì vậy, ứng dụng cần xác định rõ **khi nào tài liệu được xem là hoàn tất**, **ai sở hữu stream**, và **cách công bố output chỉ sau khi ghi thành công**.

Bài này trình bày cách ghi một JSON document hoặc một mảng lớn theo luồng bằng Jackson, quản lý `JsonGenerator` và `SequenceWriter`, phân biệt JSON array với chuỗi nhiều root value, xử lý lỗi khi output chưa hoàn tất, ghi file theo kiểu atomic publish, và chọn giao thức phù hợp cho HTTP hoặc NDJSON.

## 1. Streaming output giải quyết vấn đề gì?

Cách đơn giản:

~~~java
String json = mapper.writeValueAsString(orders);
Files.writeString(path, json, StandardCharsets.UTF_8);
~~~

Cách này thường tạo ít nhất một bản biểu diễn JSON đầy đủ trong bộ nhớ. Nếu dữ liệu lớn, heap có thể đồng thời giữ:

- Object graph nguồn.
- String JSON.
- Byte buffer khi encode.
- Buffer của thư viện hoặc HTTP client.
- Các bản sao tạm thời do framework tạo ra.

Ghi trực tiếp vào stream:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, orders);
}
~~~

Jackson có thể serialize trực tiếp vào output stream, tránh tạo một String chứa toàn bộ JSON. Tuy nhiên, ví dụ này vẫn giả định `orders` đã tồn tại đầy đủ trong bộ nhớ. Streaming output không tự động làm object graph nguồn trở thành streaming.

Nếu nguồn dữ liệu cũng được đọc từng phần, có thể kết hợp iterator/cursor với writer để không cần gom cả batch vào một List.

### 1.1. Ba loại bộ nhớ cần phân biệt

| Thành phần | Streaming output có giảm được không? |
|---|---|
| String/byte array chứa toàn bộ JSON | Có, nếu ghi trực tiếp ra stream |
| Object graph nguồn đã được load toàn bộ | Không, cần nguồn dữ liệu dạng iterator/cursor |
| Buffer của generator và output stream | Vẫn tồn tại, nhưng thường có kích thước hữu hạn |

Streaming chủ yếu giảm bộ nhớ dành cho output trung gian. Nếu ứng dụng gọi repository `.findAll()` rồi truyền List cho Jackson, dữ liệu nguồn vẫn có thể chiếm phần lớn heap.

### 1.2. Khi nào nên dùng streaming?

Phù hợp với:

- Export hàng trăm nghìn hoặc hàng triệu record.
- Ghi batch JSON ra file.
- Phát response lớn cho client.
- Xử lý dữ liệu tuần tự từ database cursor hoặc message source.
- Tạo NDJSON để consumer xử lý từng record độc lập.
- Pipeline mà không cần giữ toàn bộ output trong RAM.

Với payload nhỏ, `writeValueAsString()` thường dễ đọc và đủ hiệu quả. Chỉ chuyển sang streaming khi kích thước, memory pressure hoặc latency cho thấy lợi ích thực tế.

## 2. Luồng ghi JSON trong Jackson

Jackson có thể ghi qua `JsonGenerator`, một abstraction phát token JSON xuống target. Databind dùng serializer để chuyển object Java thành các token đó.

~~~text
Java object / record iterator
          |
          v
   ObjectWriter / Serializer
          |
          v
      JsonGenerator
          |
          v
  OutputStream / Writer / File
          |
          v
       Destination
~~~

Các thành phần có trách nhiệm khác nhau:

- `ObjectMapper`: cấu hình, tìm serializer và điều phối databinding.
- `ObjectWriter`: cấu hình bất biến cho một lần ghi hoặc một kiểu root.
- `SequenceWriter`: ghi nhiều root value theo một sequence, hoặc bọc chúng trong một JSON array.
- `JsonGenerator`: ghi token mức thấp như start object, field name, string, number, start/end array.
- `OutputStream`/`Writer`: nơi nhận bytes hoặc characters.

### 2.1. Ghi một object trực tiếp ra OutputStream

~~~java
ObjectWriter writer = mapper.writerFor(Order.class);

try (OutputStream output = Files.newOutputStream(path)) {
    writer.writeValue(output, order);
}
~~~

Cách này tránh tạo String JSON trung gian. `writeValue(OutputStream, value)` quản lý generator được tạo bên trong; cần đọc tài liệu phiên bản Jackson đang dùng về việc đóng target stream. Mặc định, generator có thể đóng target khi đóng generator.

Nếu stream do caller quản lý và phải tiếp tục sử dụng sau khi Jackson ghi xong, cấu hình quyền sở hữu rõ ràng hoặc tạo generator từ stream bên ngoài rồi tắt `AUTO_CLOSE_TARGET` trên generator đó.

### 2.2. Ghi bytes thay vì String

~~~java
byte[] json = mapper.writeValueAsBytes(order);
~~~

Đây vẫn là cách materialize toàn bộ output vào một byte array. Nó hữu ích khi cần ký payload, gửi qua API yêu cầu byte array hoặc tính hash, nhưng không phải streaming cho tài liệu lớn.

## 3. Ghi một JSON array lớn bằng SequenceWriter

Khi cần tạo một JSON document có root là array, `ObjectWriter.writeValuesAsArray(...)` cung cấp `SequenceWriter` để ghi từng phần tử. Writer tự quản lý dấu ngoặc array và việc ghi từng root value.

~~~java
ObjectWriter orderWriter = mapper.writerFor(Order.class);

try (SequenceWriter sequence =
        orderWriter.writeValuesAsArray(outputStream)) {
    for (Order order : orderSource) {
        sequence.write(order);
    }
}
~~~

Hình dạng output:

~~~json
[
  {"id":"O-1","amount":10},
  {"id":"O-2","amount":20},
  {"id":"O-3","amount":30}
]
~~~

Mỗi lần gọi `sequence.write(order)`, Jackson serialize một phần tử. Ứng dụng không cần tạo List chứa toàn bộ JSON output.

### 3.1. Vì sao cần writeValuesAsArray?

`writeValues(...)` và `writeValuesAsArray(...)` có contract khác nhau:

| API | Hình thức root output | Mục đích |
|---|---|---|
| `writeValues(...)` | Nhiều root value nối tiếp, phân cách bằng root value separator | Protocol chấp nhận nhiều JSON value liên tiếp |
| `writeValuesAsArray(...)` | Một JSON array chứa các phần tử | Một JSON document chuẩn có root array |

Ví dụ sequence không bọc array có thể trông như:

~~~text
{"id":"O-1"} {"id":"O-2"} {"id":"O-3"}
~~~

Đây không phải một JSON document đơn lẻ theo contract thông thường. Một JSON parser chỉ mong đợi một root value có thể từ chối dữ liệu này. Nếu consumer yêu cầu một JSON document, dùng `writeValuesAsArray` hoặc ghi array bằng generator.

### 3.2. Ghi từ iterator hoặc cursor

Nếu nguồn dữ liệu hỗ trợ iterator:

~~~java
try (SequenceWriter sequence =
        mapper.writerFor(Order.class)
                .writeValuesAsArray(outputStream)) {

    while (orderIterator.hasNext()) {
        sequence.write(orderIterator.next());
    }
}
~~~

Nếu iterator mở database cursor hoặc resource khác, resource đó cũng cần được đóng đúng vòng đời. SequenceWriter chỉ quản lý phần output; nó không tự đóng iterator nguồn trừ khi code ứng dụng làm việc đó.

### 3.3. SequenceWriter phải được đóng thành công

Khi đóng SequenceWriter, Jackson hoàn tất array và đóng generator theo vòng đời của writer. Vì vậy, `close()` là một phần của quá trình serialize, không chỉ là cleanup.

Một lỗi có thể xảy ra khi:

- Ghi một phần tử.
- Ghi dấu đóng array.
- Flush buffer.
- Đóng generator.
- Đóng output stream.

Không được đánh dấu file hoặc response là hoàn tất trước khi sequence writer đóng thành công.

## 4. Ghi token trực tiếp bằng JsonGenerator

Khi cần kiểm soát cấu trúc JSON ở mức token, có thể dùng `JsonGenerator`:

~~~java
try (JsonGenerator generator =
        mapper.getFactory().createGenerator(outputStream)) {

    generator.writeStartObject();
    generator.writeStringField("type", "export");
    generator.writeNumberField("count", 2);

    generator.writeArrayFieldStart("items");

    generator.writeStartObject();
    generator.writeStringField("id", "O-1");
    generator.writeNumberField("amount", 10);
    generator.writeEndObject();

    generator.writeStartObject();
    generator.writeStringField("id", "O-2");
    generator.writeNumberField("amount", 20);
    generator.writeEndObject();

    generator.writeEndArray();
    generator.writeEndObject();
}
~~~

Generator giúp kiểm soát chính xác thứ tự token và tránh phải dựng một DTO lớn chỉ để tạo một cấu trúc export đơn giản.

### 4.1. Các cặp start/end phải cân bằng

Các lệnh thường gặp:

| Mở | Đóng |
|---|---|
| `writeStartObject()` | `writeEndObject()` |
| `writeStartArray()` | `writeEndArray()` |
| `writeObjectFieldStart(name)` | `writeEndObject()` |
| `writeArrayFieldStart(name)` | `writeEndArray()` |

Generator kiểm tra cấu trúc token và có thể ném exception nếu ứng dụng ghi field/value sai vị trí. Với nested structure, nên tổ chức code thành các method nhỏ có trách nhiệm đóng cấu trúc mà chúng mở.

### 4.2. Không tự nối JSON bằng chuỗi

Không dùng:

~~~java
output.write(("{\"id\":\"" + id + "\"}").getBytes(UTF_8));
~~~

Cách nối chuỗi dễ làm hỏng escape khi dữ liệu chứa quote, backslash, newline hoặc control character. Nó cũng có nguy cơ tạo JSON injection nếu value không được escape đúng.

Dùng `JsonGenerator` cho token mức thấp hoặc Databind serializer cho object. Cả hai đều hiểu quy tắc escaping JSON.

### 4.3. Kết hợp generator và databinding đúng cách

Nếu cần ghi nhiều object trong một array, ưu tiên SequenceWriter vì nó quản lý sequence và generator lifecycle. Không gọi một API ghi root value đóng generator lặp đi lặp lại trên cùng generator mà chưa kiểm tra contract của API đó.

Một pattern an toàn là để SequenceWriter điều phối từng root object; dùng JsonGenerator trực tiếp khi ứng dụng tự ghi token và chịu trách nhiệm cấu trúc.

## 5. JSON chỉ hoàn chỉnh khi nào?

Một JSON document có thể được xem là hoàn tất khi:

1. Tất cả record dự kiến đã được ghi.
2. Các object/array đã được đóng đúng cấu trúc.
3. Generator/SequenceWriter hoàn tất mà không ném lỗi.
4. Buffer được flush theo contract.
5. Đóng tài nguyên đầu ra thành công nếu close là bước commit dữ liệu.
6. Tầng lưu trữ hoặc transport xác nhận thao tác ghi thành công.

Ví dụ, một array cần có dấu đóng:

~~~json
[
  {"id":"O-1"},
  {"id":"O-2"}
]
~~~

Nếu output dừng ở:

~~~json
[
  {"id":"O-1"},
  {"id":"O-2"}
~~~

thì document bị truncate và parser thông thường sẽ báo lỗi cú pháp.

### 5.1. Có bytes không đồng nghĩa có document hoàn chỉnh

Một file có kích thước lớn hơn 0 không chứng minh nó hợp lệ. Một response đã gửi nhiều kilobytes cũng chưa chứng minh root array đã đóng.

Hãy có trạng thái xử lý riêng:

- `WRITING`: output đang được tạo.
- `COMPLETED`: toàn bộ dữ liệu và bước finalize đã thành công.
- `FAILED`: lỗi xảy ra trước khi công bố.
- `ABORTED`: ứng dụng chủ động dừng trước khi hoàn tất.

Không suy ra trạng thái từ việc file tồn tại hoặc stream đã nhận một số bytes.

## 6. Điều gì xảy ra khi lỗi giữa chừng?

Giả sử ứng dụng đang ghi array gồm 100.000 record. Đến record thứ 40.000, getter ném exception hoặc output stream hết dung lượng.

Một số bytes đã được ghi. Phần còn lại không được tạo. Tùy vị trí lỗi và cấu hình generator, output có thể:

- Kết thúc giữa một token.
- Kết thúc giữa object.
- Kết thúc giữa array.
- Có một số record hoàn chỉnh nhưng thiếu các record sau.
- Nhận thêm dấu đóng khi generator được close tự động.
- Gặp lỗi tiếp theo khi flush hoặc close.

Dù output sau close có vẻ parse được, nó vẫn có thể thiếu record và vi phạm contract nghiệp vụ.

### 6.1. Phân biệt lỗi serialize với lỗi ghi

| Lỗi | Ví dụ | Tầng phát sinh |
|---|---|---|
| Mapping/serialization | Getter ném lỗi, custom serializer thất bại | Jackson Databind |
| Generation | Token được ghi sai cấu trúc | JsonGenerator |
| I/O | Disk full, socket reset, stream đóng | OutputStream/Writer |
| Source iteration | Database cursor hoặc iterator thất bại | Nguồn dữ liệu |
| Finalization | Flush/close thất bại | Generator/target |

Cần giữ nguyên nguyên nhân để log và xử lý. Không biến mọi lỗi thành “JSON không hợp lệ” vì có thể lỗi thực tế là disk full hoặc client đã ngắt kết nối.

### 6.2. Không tiếp tục ghi error JSON vào document đã hỏng

Một cách xử lý sai là catch exception rồi ghi thêm:

~~~json
{"error":"export failed"}
~~~

vào cuối array đang dở. Kết quả có thể là JSON không hợp lệ hoặc một document có hình dạng sai contract. Nếu output đã có một phần dữ liệu, không thể tùy tiện thay nó bằng một error document khác.

Lỗi cần được báo ở tầng protocol hoặc trạng thái job phù hợp.

## 7. AUTO_CLOSE_JSON_CONTENT không phải cơ chế phục hồi

Jackson có feature `JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT`. Khi generator được đóng trong lúc còn object/array mở, feature này có thể khiến generator cố ghi các dấu đóng còn thiếu.

Điều đó hữu ích để đóng cấu trúc trong một số tình huống bình thường, nhưng không phải cơ chế rollback hoặc phục hồi document.

Ví dụ, nếu một array dự kiến có 10.000 record nhưng lỗi xảy ra sau record thứ 2.000, việc tự ghi `]` có thể tạo một JSON array cú pháp hợp lệ chỉ gồm 2.000 record. Consumer có thể parse thành công nhưng nhận một batch thiếu dữ liệu.

Do đó:

- Ghi nhận lỗi trước khi finalize.
- Không công bố output nếu bất kỳ record nào thất bại.
- Không coi việc generator close thành công là bằng chứng rằng tất cả record nguồn đã được xử lý.
- Dùng số record dự kiến/thực tế hoặc completion metadata nếu contract cần xác nhận completeness.

### 7.1. writeEndArray phải là bước có chủ đích

Với code dùng generator thủ công, gọi `writeEndArray()` sau khi vòng lặp hoàn tất. Nếu vòng lặp thất bại, không chạy đường publish.

Với SequenceWriter bọc array, việc đóng sequence hoàn tất array. Chỉ đánh dấu thành công sau khi close trả về mà không có exception.

## 8. Flush, close và quyền sở hữu stream

Ba thao tác có ý nghĩa khác nhau:

- `flush()`: đẩy dữ liệu từ buffer xuống target theo khả năng của stream.
- `close()`: hoàn tất và giải phóng tài nguyên; generator có thể đóng target tùy feature.
- `force()/sync`: yêu cầu tầng file system ghi dữ liệu xuống thiết bị lưu trữ theo API tương ứng; flush không tương đương durable commit.

### 8.1. AUTO_CLOSE_TARGET

Mặc định, JsonGenerator có thể đóng target stream khi generator được đóng. Feature `JsonGenerator.Feature.AUTO_CLOSE_TARGET` kiểm soát hành vi này.

Nếu caller sở hữu stream và cần giữ nó mở:

~~~java
try (JsonGenerator generator =
        mapper.getFactory().createGenerator(outputStream)) {

    generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);

    generator.writeStartObject();
    generator.writeStringField("status", "complete");
    generator.writeEndObject();
    generator.flush();
}

// outputStream vẫn thuộc caller và được caller đóng.
~~~

Generator vẫn được đóng, nhưng target không bị generator đóng. Caller phải tự flush/close output stream theo vòng đời của nó.

### 8.2. Ai tạo tài nguyên thì cần rõ ai đóng

Một số quy tắc dễ áp dụng:

- Nếu method nhận OutputStream do caller truyền vào, tài liệu API phải nói rõ method có đóng stream hay không.
- Nếu method tự mở file hoặc socket, method đó thường chịu trách nhiệm đóng.
- Nếu tạo JsonGenerator từ stream bên ngoài, cấu hình AUTO_CLOSE_TARGET theo ownership.
- Nếu dùng SequenceWriter, kiểm tra việc close sequence có đóng generator/target hay không.
- Không đóng cùng tài nguyên từ nhiều nơi theo các lifecycle không rõ ràng.

Đóng hai lần một số stream phổ biến là an toàn, nhưng không nên dựa vào đó cho mọi custom stream.

### 8.3. Flush mỗi record hay theo batch?

Flush sau từng record có thể giảm độ trễ quan sát được nhưng tăng số lần system call và làm giảm throughput. Không flush sau mỗi field. Chọn policy theo protocol:

- File export: thường để buffer hoạt động và finalize ở cuối.
- HTTP streaming: flush theo batch hoặc khi cần đẩy progress.
- NDJSON: có thể flush sau mỗi record nếu consumer cần nhận record sớm.
- Message broker: dùng producer batching/ack semantics của broker thay vì coi flush của JsonGenerator là commit message.

Flush không bảo đảm dữ liệu đã bền vững trên disk hoặc client đã nhận và xử lý bytes.

## 9. Ghi file theo kiểu atomic publish

Nếu ứng dụng ghi trực tiếp vào file đích và gặp lỗi giữa chừng, file cũ có thể bị truncate hoặc bị thay bằng một file mới chỉ chứa một phần dữ liệu.

Với file export, một pattern hữu ích là:

1. Tạo file tạm trong cùng thư mục với file đích.
2. Ghi toàn bộ JSON vào file tạm.
3. Đóng SequenceWriter/generator và stream thành công.
4. Chỉ sau đó mới move file tạm thành file đích.
5. Nếu bất kỳ bước nào thất bại, xóa file tạm và giữ file đích cũ.

~~~text
target.json (previous complete file)
        |
        | keep available while writing
        |
        +-----------------------------+
                                      |
                                  write to
                                      |
                                      v
                              target.json.tmp
                                      |
                            all writes + close OK?
                                /           \
                              yes            no
                               |              |
                         atomic move       delete temp
                               |
                               v
                      target.json (new complete file)
~~~

### 9.1. Ví dụ ghi array vào file tạm

~~~java
public static <T> void writeJsonArrayAtomically(
        ObjectWriter writer,
        Iterable<T> values,
        Path destination
) throws IOException {
    Path target = destination.toAbsolutePath();
    Path parent = target.getParent();

    Files.createDirectories(parent);

    Path temporary = Files.createTempFile(
            parent,
            "json-export-",
            ".tmp"
    );

    boolean published = false;

    try {
        try (SequenceWriter sequence =
                writer.writeValuesAsArray(temporary.toFile())) {
            for (T value : values) {
                sequence.write(value);
            }
        }

        // Chỉ publish sau khi SequenceWriter đã close thành công.
        Files.move(
                temporary,
                target,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
        );

        published = true;
    } finally {
        if (!published) {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

File tạm nằm cùng thư mục với target để tăng khả năng cả hai cùng filesystem. SequenceWriter đóng thành công trước khi move. Nếu serialization, source iteration hoặc close thất bại, code không thực hiện bước publish.

### 9.2. Atomic move phụ thuộc filesystem

`ATOMIC_MOVE` chỉ được hỗ trợ nếu filesystem/provider cung cấp thao tác đó. Hành vi thay thế target đang tồn tại cũng cần được kiểm tra trên nền tảng triển khai.

Nếu atomic move không được hỗ trợ, đừng âm thầm giả định một move/copy thường có cùng guarantee. Có thể:

- Dừng publish và báo lỗi rõ ràng.
- Dùng tên file versioned bất biến rồi cập nhật một manifest/pointer bằng thao tác atomic đã được hỗ trợ.
- Dùng storage API có transaction hoặc multipart-complete semantics.
- Chọn một filesystem/provider có atomic rename phù hợp.

Ví dụ trên cần được kiểm tra trên filesystem thực tế của production, đặc biệt khi target đã tồn tại. Atomic visibility và durability sau mất điện là hai guarantee khác nhau.

### 9.3. Dọn file tạm khi tiến trình bị kill

Khối `finally` chỉ chạy khi JVM còn cơ hội thực thi. Nếu process bị kill hoặc máy mất điện, file tạm có thể còn lại.

Có thể đặt tên file tạm theo prefix, ghi metadata thời điểm tạo và có job cleanup file cũ. Job cleanup phải chỉ xóa file tạm thuộc ứng dụng và đủ tuổi; không xóa file export đang được một process khác ghi.

### 9.4. Flush và durability của file

Đóng stream thường flush buffer của Java xuống OS, nhưng chưa chắc dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ. Nếu yêu cầu durability mạnh, có thể dùng FileChannel.force(true) hoặc cơ chế tương ứng trước khi publish, đồng thời xem xét sync thư mục sau rename theo khả năng nền tảng.

Đừng thêm force/sync cho mọi export nếu không có yêu cầu durability; thao tác này có chi phí và behavior phụ thuộc filesystem.

## 10. Không thể rollback bytes đã gửi qua HTTP

File tạm có thể được giữ riêng cho tới khi hoàn tất, nhưng HTTP response streaming có một giới hạn khác: sau khi response đã commit và bytes đã được gửi, server không thể rút lại những bytes đó.

Nếu đang stream một JSON array:

~~~json
[
  {"id":"O-1"},
  {"id":"O-2"},
~~~

và database cursor lỗi, server không thể đổi status code thành 500 rồi thay body bằng JSON error một cách đáng tin cậy. Header/status có thể đã gửi; body đã có prefix JSON.

### 10.1. Ba chiến lược cho HTTP

| Chiến lược | Cách hoạt động | Trade-off |
|---|---|---|
| Buffer trước khi trả | Serialize hoàn chỉnh vào memory hoặc temp file, rồi mới gửi | Có thể đảm bảo không gửi JSON dở dang; tăng latency và storage/memory |
| Stream một JSON document | Ghi trực tiếp array/object ra response | Ít buffer; lỗi giữa chừng làm response không hoàn chỉnh |
| Dùng protocol record-based | Mỗi record độc lập, ví dụ NDJSON | Consumer có thể giữ các record hoàn chỉnh trước lỗi |

Chọn theo contract API và kích thước payload. Nếu client cần một JSON document all-or-nothing, buffer hoặc spool hoàn chỉnh trước khi commit response là cách rõ ràng hơn.

### 10.2. Không append error object vào JSON array đang dở

Không làm:

~~~text
[
  {"id":"O-1"},
  {"id":"O-2"},
  {"error":"database failed"}
]
~~~

trừ khi schema của API định nghĩa rõ mỗi phần tử là một union giữa success và error. Nếu contract chỉ định array các Order, error object sẽ làm thay đổi schema và khiến consumer lỗi.

Nếu cần truyền trạng thái lỗi trong streaming protocol, định nghĩa protocol riêng có record type hoặc error event rõ ràng.

### 10.3. Response đã commit thì log và kết thúc stream

Khi lỗi xảy ra sau commit:

- Dừng ghi thêm dữ liệu nghiệp vụ.
- Đóng tài nguyên và ghi nhận lỗi.
- Đánh dấu trace/span là failed.
- Ghi correlation ID để client hỗ trợ điều tra.
- Không giả vờ response đã hoàn tất.
- Không ghi thêm một JSON root value tùy tiện.

Client cần xử lý EOF hoặc parse failure như một response chưa hoàn chỉnh. Nếu API yêu cầu client biết trạng thái cuối cùng trong cùng stream, hãy thiết kế framing và completion record ngay từ đầu.

## 11. NDJSON cho stream gồm nhiều record độc lập

NDJSON (newline-delimited JSON) biểu diễn mỗi record bằng một JSON value trên một dòng:

~~~text
{"id":"O-1","amount":10}
{"id":"O-2","amount":20}
{"id":"O-3","amount":30}
~~~

Đây không phải một JSON array. Mỗi dòng là một JSON document riêng, được phân cách bằng newline. Consumer có thể parse và xử lý từng dòng khi nhận được.

### 11.1. Ghi NDJSON từng record

~~~java
ObjectWriter writer = mapper.writerFor(OrderEvent.class);

try (OutputStream output = Files.newOutputStream(path)) {
    for (OrderEvent event : eventSource) {
        byte[] record = writer.writeValueAsBytes(event);

        output.write(record);
        output.write('\n');
    }

    output.flush();
}
~~~

Mỗi record được serialize hoàn chỉnh vào byte array trước khi ghi. Bộ nhớ trung gian được giới hạn theo kích thước một record, không phải toàn bộ batch. Newline được ghi sau khi record serialize thành công.

Nếu output stream thất bại giữa khi ghi byte array, dòng cuối có thể bị thiếu newline và không hoàn chỉnh. Consumer nên chỉ xử lý các dòng đã kết thúc bằng delimiter theo contract.

### 11.2. Newline trong string JSON

JSON serializer escape newline bên trong string thành chuỗi ký tự escape, ví dụ `\\n`. Vì vậy newline vật lý có thể dùng làm record delimiter trong NDJSON mà không bị nhầm với newline thuộc string value, miễn là mỗi record được ghi dưới dạng một JSON value hợp lệ trên một dòng.

Không dùng pretty printer cho từng record NDJSON vì pretty-printed JSON có thể chứa newline vật lý bên trong một record và phá framing theo dòng.

### 11.3. Xử lý lỗi sau một số record

Giả sử đã ghi ba dòng hoàn chỉnh rồi record thứ tư lỗi:

~~~text
{"id":"O-1"}
{"id":"O-2"}
{"id":"O-3"}
{"id":"O-4"
~~~

Consumer có thể xử lý ba dòng đầu và bỏ dòng cuối chưa có delimiter. Điều này khác với một JSON array bị truncate, nơi toàn bộ document thường không parse được.

NDJSON không tự bảo đảm mọi record đã được xử lý bền vững. Consumer vẫn cần idempotency, checkpoint hoặc acknowledgment nếu xử lý có side effect.

### 11.4. Completion marker nếu cần biết stream đã kết thúc bình thường

Một protocol có thể thêm record cuối cùng:

~~~json
{"recordType":"data","id":"O-1"}
{"recordType":"data","id":"O-2"}
{"recordType":"complete","count":2}
~~~

Consumer chỉ xem batch là hoàn tất khi nhận được record `complete` và kiểm tra count/metadata theo contract. Nếu stream bị ngắt trước marker, batch được xem là incomplete dù các record trước đó parse được.

Completion marker phải được định nghĩa trong schema; không thêm tùy tiện vào một feed chỉ chứa data records.

## 12. SequenceWriter cho nhiều root value

Jackson `SequenceWriter` có thể ghi nhiều root values. Cần phân biệt rõ hai chế độ:

~~~java
ObjectWriter writer = mapper.writerFor(OrderEvent.class);

try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    sequence.write(firstEvent);
    sequence.write(secondEvent);
}
~~~

Đây là sequence root values; separator được điều khiển bởi root value separator của writer. Mặc định, các root value có thể được phân cách bằng khoảng trắng. Một số parser/protocol cho phép nhiều root value, nhưng một JSON document thông thường không cho phép nhiều root độc lập.

Nếu cần NDJSON, có thể cấu hình separator newline:

~~~java
ObjectWriter ndjsonWriter = mapper.writerFor(OrderEvent.class)
        .withRootValueSeparator("\n");

try (SequenceWriter sequence = ndjsonWriter.writeValues(outputStream)) {
    sequence.write(firstEvent);
    sequence.write(secondEvent);
}
~~~

Cần xác định rõ newline cuối cùng và flush policy trong contract. Nếu consumer yêu cầu newline sau mỗi record kể cả record cuối, cách ghi từng byte array rồi thêm newline tường minh ở phần trước làm behavior đó rõ ràng hơn.

Nếu cần một JSON array duy nhất, luôn chọn `writeValuesAsArray`.

## 13. Backpressure và tốc độ của output stream

Streaming không có nghĩa writer luôn ghi nhanh. Nếu consumer đọc chậm, network socket hoặc pipe có thể block khi buffer đầy. Đây là backpressure tự nhiên của stream đồng bộ.

Một pipeline:

~~~text
Database cursor
      |
      v
Jackson serializer
      |
      v
Buffered output
      |
      v
Network / file consumer
~~~

Khi output chậm, thread serialize có thể phải chờ. Điều này giữ tài nguyên như database cursor, connection và request thread lâu hơn.

Các biện pháp:

- Đặt timeout cho nguồn dữ liệu và network.
- Giới hạn số export đồng thời.
- Dùng pagination/cursor có lifecycle phù hợp.
- Không prefetch vô hạn record vào queue.
- Dùng bounded queue nếu producer và writer chạy ở thread khác.
- Theo dõi thời gian serialize, thời gian blocked write và số bytes.
- Hủy query/cursor khi client disconnect nếu framework hỗ trợ.

### 13.1. Không tạo queue không giới hạn

Nếu đọc database nhanh hơn network, một queue không giới hạn có thể giữ hàng triệu object trong heap. Khi cần tách producer và writer, dùng bounded queue và xác định behavior khi đầy: block producer, pause source hoặc cancel job.

### 13.2. Client disconnect là một lỗi output

Trong HTTP, client có thể đóng socket giữa chừng. Server thường nhận IOException từ response stream hoặc framework-specific exception. Không retry ghi tiếp trên cùng response.

Ghi nhận đây là client disconnect/cancel nếu có thể phân biệt, không nhất thiết là bug serializer. Dừng nguồn dữ liệu và đóng cursor để tránh tiếp tục đọc database vô ích.

## 14. Buffering và kích thước chunk

Jackson generator có buffer nội bộ; output stream có thể được bọc thêm bởi BufferedOutputStream. Không cần flush sau mỗi token.

Ví dụ:

~~~java
try (OutputStream file = Files.newOutputStream(path);
     BufferedOutputStream buffered = new BufferedOutputStream(file, 64 * 1024);
     SequenceWriter sequence =
             mapper.writerFor(Order.class).writeValuesAsArray(buffered)) {

    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

SequenceWriter đóng generator và có thể đóng buffered stream theo cấu hình. Vì try-with-resources đóng theo thứ tự ngược, buffered stream cũng được đóng sau khi sequence writer kết thúc. Double-close trên các stream chuẩn thường không gây vấn đề, nhưng nếu ownership cần chính xác, dùng generator ngoài với `AUTO_CLOSE_TARGET=false`.

Buffer lớn hơn có thể giảm số lần write system call nhưng tăng memory trên mỗi export đồng thời. Chọn theo concurrency và throughput đo được, không chọn kích thước tùy tiện.

## 15. Serialization exception và I/O exception

Khi ghi, các lỗi thường đi qua `IOException` hoặc subtype Jackson.

Một số ví dụ:

- `JsonMappingException`: lỗi khi serialize một property hoặc object graph.
- `JsonGenerationException`: lỗi cấu trúc hoặc thao tác generator.
- `IOException`: output stream không ghi được.
- Runtime exception: getter, iterator hoặc business code ném lỗi không được Jackson chuyển đổi theo cách mong đợi.

### 15.1. Giữ nguyên exception và nguyên nhân

Không nên catch tất cả rồi chỉ ném:

~~~java
throw new RuntimeException("JSON export failed");
~~~

Điều này làm mất loại lỗi và cause hữu ích. Có thể wrap ở application boundary nhưng giữ cause:

~~~java
try {
    writeExport();
} catch (IOException ex) {
    throw new ExportException("Không thể hoàn tất JSON export", ex);
}
~~~

Tầng gọi có thể phân biệt lỗi mapping, lỗi source và lỗi destination qua cause chain hoặc exception category nội bộ.

### 15.2. Không retry cùng output stream sau lỗi

Sau IOException, trạng thái stream có thể không xác định: một phần buffer đã được ghi, socket có thể đóng hoặc file có thể chứa prefix. Không tiếp tục ghi từ vị trí logic cũ trừ khi protocol và destination hỗ trợ resume có offset/checkpoint rõ.

Với file, tạo file tạm mới và chạy lại từ đầu hoặc resume theo cơ chế versioned chunk đã thiết kế. Với HTTP, response đã commit không thể restart trên cùng connection.

## 16. Kiểm thử output bị lỗi giữa chừng

Một test hữu ích dùng OutputStream giả lập chỉ cho phép ghi một số byte rồi ném IOException. Điều này kiểm tra code không coi một phần output là thành công.

~~~java
final class FailingOutputStream extends OutputStream {
    private final int byteLimit;
    private final ByteArrayOutputStream captured = new ByteArrayOutputStream();

    FailingOutputStream(int byteLimit) {
        this.byteLimit = byteLimit;
    }

    @Override
    public void write(int value) throws IOException {
        if (captured.size() >= byteLimit) {
            throw new IOException("Simulated output failure");
        }
        captured.write(value);
    }

    @Override
    public void write(byte[] bytes, int offset, int length)
            throws IOException {
        int remaining = byteLimit - captured.size();
        int accepted = Math.min(remaining, length);

        if (accepted > 0) {
            captured.write(bytes, offset, accepted);
        }

        if (accepted < length) {
            throw new IOException("Simulated output failure");
        }
    }

    byte[] capturedBytes() {
        return captured.toByteArray();
    }
}
~~~

Test:

~~~java
@Test
void shouldPropagateFailureWhenOutputStreamStopsAcceptingBytes() {
    FailingOutputStream output = new FailingOutputStream(24);

    assertThrows(IOException.class, () -> {
        try (SequenceWriter sequence =
                mapper.writerFor(Order.class)
                        .writeValuesAsArray(output)) {
            sequence.write(order("O-1"));
            sequence.write(order("O-2"));
        }
    });

    assertEquals(24, output.capturedBytes().length);
}
~~~

Test xác nhận exception được truyền ra khi target ngừng nhận bytes. Nó không khẳng định output partial có thể được dùng; output đó phải bị loại bỏ hoặc được đánh dấu incomplete.

### 16.1. Kiểm thử lỗi từ serializer hoặc nguồn dữ liệu

Ngoài lỗi I/O, cần có test cho:

- Custom serializer ném exception.
- Getter ném exception.
- Iterator ném exception giữa vòng lặp.
- Database cursor bị lỗi.
- Generator close/flush thất bại nếu có thể giả lập.
- Client disconnect trong integration test HTTP.

Điểm cần xác nhận là job không publish file/manifest thành công và không ghi completion marker khi bất kỳ bước nào thất bại.

## 17. Kiểm thử atomic file output

Test file nên có một target cũ đã hoàn chỉnh. Sau khi giả lập lỗi trong lúc tạo file tạm, xác nhận target cũ không bị thay bằng partial JSON.

Ý tưởng:

~~~java
@Test
void shouldKeepPreviousFileWhenNewExportFails() throws Exception {
    Path target = tempDir.resolve("orders.json");
    Files.writeString(
            target,
            "[{\"id\":\"previous\"}]",
            StandardCharsets.UTF_8
    );

    assertThrows(
            IOException.class,
            () -> exportUsingFailingSource(target)
    );

    String existing = Files.readString(target, StandardCharsets.UTF_8);
    assertEquals("[{\"id\":\"previous\"}]", existing);
}
~~~

`exportUsingFailingSource` là helper test dùng iterator ném lỗi sau một số record và thực hiện cùng quy trình temp-file/publish như production. Test nên kiểm tra thêm không còn temp file thuộc job sau cleanup.

### 17.1. Test move failure

Cần kiểm tra behavior khi atomic move không hỗ trợ hoặc target không thể thay thế:

- File tạm được dọn hoặc được đánh dấu để cleanup.
- Target cũ vẫn còn nguyên nếu publish chưa thành công.
- Job báo failure.
- Không tạo completion marker giả.
- Không fallback âm thầm sang thao tác không đáp ứng yêu cầu atomicity.

Test trên filesystem tạm của build agent có thể không đại diện cho NFS, container volume hoặc object storage production. Bổ sung integration test trên loại storage được triển khai nếu atomicity là yêu cầu quan trọng.

## 18. Kiểm thử JSON hoàn chỉnh sau khi ghi

Với file đã ghi thành công, đọc lại bằng parser độc lập hoặc ObjectMapper để xác nhận root structure và record count:

~~~java
@Test
void shouldWriteCompleteArrayThatCanBeReadBack() throws Exception {
    Path file = tempDir.resolve("orders.json");

    try (SequenceWriter sequence =
            mapper.writerFor(Order.class)
                    .writeValuesAsArray(file.toFile())) {
        sequence.write(order("O-1"));
        sequence.write(order("O-2"));
    }

    JsonNode root = mapper.readTree(file.toFile());

    assertTrue(root.isArray());
    assertEquals(2, root.size());
    assertEquals("O-1", root.get(0).path("id").asText());
    assertEquals("O-2", root.get(1).path("id").asText());
}
~~~

Readback này kiểm tra cú pháp và một số giá trị. Nếu contract có count hoặc checksum, kiểm tra chúng riêng. Một JSON array hợp lệ vẫn có thể thiếu record nếu source iterator kết thúc sớm mà không báo lỗi.

### 18.1. So sánh expected count

Nếu biết số record dự kiến, đếm số đã ghi:

~~~java
long expectedCount = source.count();
long writtenCount = 0;

try (SequenceWriter sequence =
        mapper.writerFor(Order.class)
                .writeValuesAsArray(outputStream)) {
    for (Order order : source) {
        sequence.write(order);
        writtenCount++;
    }
}

if (writtenCount != expectedCount) {
    throw new IOException("Export record count does not match expectation");
}
~~~

Trong code thực tế, không gọi `count()` trên stream/cursor nếu việc đó tiêu thụ hoặc chạy lại query không mong muốn. Lấy expected count từ query metadata hoặc batch manifest đã được xác định trước.

## 19. Ghi manifest hoặc completion metadata

Với export lớn, có thể tạo manifest bên cạnh file dữ liệu:

~~~json
{
  "file": "orders-2026-11-12.json",
  "contractVersion": "v2",
  "recordCount": 250000,
  "status": "complete",
  "checksum": "..."
}
~~~

Quy trình:

1. Ghi file dữ liệu tạm.
2. Hoàn tất và đóng writer.
3. Tính record count/checksum.
4. Publish file dữ liệu.
5. Ghi manifest tạm.
6. Publish manifest cuối cùng như tín hiệu completion.

Consumer chỉ xử lý file có manifest trạng thái complete. Nếu dữ liệu đã publish nhưng manifest chưa được công bố, consumer bỏ qua và job có thể retry/reconcile theo policy.

Manifest không tự tạo transaction hai file. Nếu cần consistency giữa data và manifest, dùng versioned filenames cùng một pointer/commit record được publish atomic, hoặc storage/database hỗ trợ transaction phù hợp.

## 20. Ghi vào object storage hoặc message broker

Không phải destination nào cũng hỗ trợ rename atomic như filesystem.

### 20.1. Object storage

Với object storage, thường có thể:

- Upload vào key staging/versioned.
- Dùng multipart upload.
- Chỉ complete multipart sau khi tất cả part thành công.
- Kiểm tra checksum/size.
- Publish manifest hoặc cập nhật pointer sau completion.
- Abort multipart upload khi lỗi.

Hành vi atomicity, consistency và overwrite phụ thuộc nhà cung cấp. Không áp dụng giả định POSIX rename cho object storage.

### 20.2. Message broker

Nếu ghi JSON vào broker, mỗi message thường là một đơn vị commit riêng. Không coi flush của JsonGenerator là broker acknowledgment. Serialize một message hoàn chỉnh trước khi gửi; sau đó chờ producer acknowledgment theo semantics của broker.

Với batch nhiều record, quyết định rõ atomicity:

- Mỗi record độc lập: một số record có thể đã publish trước khi lỗi.
- Batch atomic: cần transaction hoặc staging/commit mechanism của broker.
- At-least-once: consumer phải idempotent vì retry có thể gửi lại record.

### 20.3. Database BLOB/CLOB

Nếu JSON được lưu trong database, ghi vào transaction và commit sau khi serialize thành công. Nếu dùng streaming API của JDBC, kiểm tra driver có hỗ trợ stream đúng như mong muốn và transaction rollback có giữ được row cũ hay không.

## 21. Compression và streaming

Có thể bọc output stream bằng GZIPOutputStream:

~~~java
try (OutputStream file = Files.newOutputStream(path);
     GZIPOutputStream gzip = new GZIPOutputStream(file);
     SequenceWriter sequence =
             mapper.writerFor(Order.class).writeValuesAsArray(gzip)) {

    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

Khi đóng SequenceWriter, generator có thể đóng gzip stream; GZIPOutputStream cần close để ghi trailer/checksum. Nếu gzip stream chưa close thành công, file nén có thể không hoàn chỉnh ngay cả khi phần JSON bên trong đã ghi gần hết.

Với atomic file output, ghi compressed data vào file tạm, đóng mọi layer thành công rồi mới publish. Đừng move file trước khi GZIPOutputStream hoàn tất trailer.

### 21.1. Compression làm thay đổi cách giới hạn tài nguyên

Kích thước file nén nhỏ không có nghĩa JSON giải nén nhỏ. Consumer cần giới hạn kích thước sau giải nén. Producer cũng cần theo dõi CPU compression và output throughput.

## 22. Pretty printing và streaming

Pretty printer thêm whitespace và line breaks để dễ đọc. Nó không làm thay đổi semantics JSON, nhưng có thể tăng output size và làm NDJSON framing sai nếu dùng pretty printing trên từng record.

Với JSON array lớn, pretty printing có thể hữu ích cho file debug nhưng thường không cần thiết cho machine-to-machine exchange. Với NDJSON, mỗi record phải là một JSON value trên một dòng; không bật pretty printer.

Có thể chọn writer riêng:

~~~java
ObjectWriter compactWriter = mapper.writerFor(Order.class);
ObjectWriter prettyWriter = mapper.writerFor(Order.class)
        .withDefaultPrettyPrinter();
~~~

Không thay đổi cấu hình global của mapper theo request đồng thời. Dùng ObjectWriter bất biến để tách policy output.

## 23. Hủy tác vụ và cancellation

Một export lớn có thể bị hủy bởi:

- Người dùng cancel.
- HTTP client disconnect.
- Deadline của job.
- Shutdown ứng dụng.
- Database cursor timeout.
- Destination không còn khả dụng.

Khi hủy:

1. Ngừng lấy record mới.
2. Dừng writer và không publish file tạm.
3. Đóng cursor/transaction.
4. Đóng generator/stream.
5. Xóa temp file hoặc đánh dấu cleanup.
6. Ghi outcome `ABORTED` hoặc `FAILED` theo policy.
7. Không ghi completion marker.

Không bắt InterruptedException rồi tiếp tục serialize như không có gì. Khôi phục interrupt flag khi cần và để cancellation truyền qua các layer.

## 24. Metrics cho streaming output

Có thể theo dõi các metric:

- `json_export_started_total`
- `json_export_completed_total`
- `json_export_failed_total`
- `json_export_aborted_total`
- `json_export_records_written`
- `json_export_bytes_written`
- `json_export_duration_seconds`
- `json_export_output_write_duration_seconds`

Labels nên là export type, contract version, destination class đã chuẩn hóa và outcome. Không dùng filename, user ID, document ID hoặc exception message làm metric label.

Một export hoàn tất khi close/finalization và publish đều thành công. Nếu ghi temp thành công nhưng move thất bại, outcome cuối vẫn là failed.

### 24.1. Phân biệt serialization time với output wait time

Nếu cần tìm bottleneck, đo riêng:

- Thời gian Jackson chuyển object thành token.
- Thời gian write bị block ở destination.
- Tổng thời gian export.
- Bytes và records.
- Thời gian chờ source iterator/database.

Một Timer duy nhất quanh toàn bộ export chỉ cho biết end-to-end duration, không chỉ ra phần nào chậm.

## 25. Các lỗi thường gặp

**Tạo String JSON lớn rồi mới ghi file.** Tăng heap và tạo bản sao output. Dùng OutputStream hoặc SequenceWriter khi dữ liệu lớn.

**Dùng writeValues() nhưng consumer cần một JSON array.** Sequence root values không tương đương một document array. Dùng writeValuesAsArray().

**Gọi close rồi coi mọi output là đầy đủ.** Generator có thể tự đóng dấu ngoặc dù source chưa cung cấp đủ record. Chỉ publish khi toàn bộ vòng lặp và finalize thành công.

**Ghi trực tiếp vào file đích.** Lỗi giữa chừng có thể phá file cũ. Ghi temp rồi publish sau khi close thành công.

**Fallback từ atomic move sang move thường mà không đánh giá.** Guarantee có thể thay đổi. Xác định policy khi filesystem không hỗ trợ atomic move.

**Không phân biệt flush và durable storage.** Flush không phải fsync hoặc commit transaction.

**Đóng stream không rõ ownership.** Generator có thể đóng target. Đặt rõ AUTO_CLOSE_TARGET và resource lifecycle.

**Append error JSON vào response đã bắt đầu.** Body có thể thành JSON sai contract. Thiết kế protocol lỗi riêng hoặc buffer trước khi commit.

**Dùng NDJSON nhưng pretty-print từng record.** Newline nội bộ phá framing. Dùng compact writer.

**Không kiểm tra record count.** JSON parse được nhưng có thể thiếu dữ liệu. So sánh count/checksum hoặc completion manifest.

**Bỏ qua lỗi close.** Flush/close có thể là nơi lỗi được phát hiện. Đưa finalize vào điều kiện thành công.

**Không dừng source khi output lỗi.** Database cursor tiếp tục đọc dù destination đã chết. Hủy source và giải phóng resource.

## 26. Quy trình triển khai

Khi xây dựng một JSON export lớn:

1. Xác định consumer cần một JSON document, một array, hay record stream như NDJSON.
2. Chọn ObjectWriter, SequenceWriter hoặc JsonGenerator theo cấu trúc output.
3. Lấy dữ liệu nguồn theo iterator/cursor có giới hạn thay vì gom toàn bộ batch nếu phù hợp.
4. Xác định quyền sở hữu OutputStream và cấu hình AUTO_CLOSE_TARGET.
5. Ghi từng record và quản lý backpressure.
6. Xem write, flush và close đều là các bước có thể thất bại.
7. Với file, ghi vào temp trong cùng filesystem và chỉ publish sau khi close thành công.
8. Với HTTP, quyết định có buffer/spool trước commit hay chấp nhận stream có thể incomplete.
9. Với NDJSON, định nghĩa newline framing và completion semantics.
10. Giữ record count/checksum nếu cần chứng minh completeness.
11. Viết test giả lập serializer, source và output stream failure.
12. Kiểm tra file cuối bằng parser và contract assertions.
13. Đo memory, throughput, output wait và cancellation trên workload thực tế.
14. Theo dõi completion/failure metrics và cleanup các file tạm còn sót.

## 27. Kết luận

Ghi JSON theo luồng giúp tránh materialize toàn bộ output trong một String hoặc byte array. Với một root array lớn, `SequenceWriter.writeValuesAsArray()` ghi từng phần tử và quản lý cấu trúc array; `JsonGenerator` phù hợp khi cần kiểm soát token trực tiếp. Cần phân biệt array document với nhiều root value nối tiếp, vì hai hình thức có contract khác nhau.

Lỗi giữa chừng có thể để lại một prefix JSON. Việc generator tự đóng object/array khi close không chứng minh tài liệu đầy đủ; một JSON parse được vẫn có thể thiếu record. Chỉ xem output là hoàn tất khi nguồn đã được xử lý hết, writer finalize thành công và destination xác nhận ghi thành công. Với file, dùng temp file và publish sau cùng; với HTTP, nhớ rằng bytes đã commit không thể rollback; với NDJSON, định nghĩa framing và completion marker để consumer phân biệt record hoàn chỉnh với stream bị ngắt.

Quản lý ownership của stream, flush/close, backpressure, cancellation và cleanup là một phần của thiết kế serialization. Kiểm thử bằng output stream cố ý thất bại, source iterator lỗi và file target cũ giúp bảo đảm ứng dụng không công bố output dở dang như một export thành công.

## Tài liệu tham khảo

- [Jackson Databind — ObjectWriter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectWriter.html)
- [Jackson Databind — SequenceWriter API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/SequenceWriter.html)
- [Jackson Core — JsonGenerator API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonGenerator.html)
- [Jackson Core — JsonGenerator.Feature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonGenerator.Feature.html)
- [Java OutputStream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [Java Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java StandardCopyOption API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [NDJSON specification](https://github.com/ndjson/ndjson-spec)

