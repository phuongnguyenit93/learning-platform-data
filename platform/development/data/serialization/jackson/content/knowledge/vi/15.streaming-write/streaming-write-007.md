# Quản lý bộ đệm, flush và đóng tài nguyên

Khi ghi JSON bằng Jackson Streaming API, `JsonGenerator` không nhất thiết ghi từng ký tự hoặc byte xuống đích ngay tại thời điểm gọi `writeString()`, `writeNumber()` hay `writeFieldName()`. Generator thường giữ dữ liệu trong bộ đệm nội bộ rồi ghi theo từng đợt. Cách làm này giảm số lần gọi I/O và cải thiện hiệu suất, nhưng cũng có nghĩa dữ liệu vừa ghi có thể vẫn đang nằm trong bộ đệm.

Ba thao tác cần hiểu rõ là:

- **Buffering:** giữ tạm dữ liệu trước khi chuyển xuống `OutputStream` hoặc `Writer`.
- **`flush()`:** đẩy dữ liệu đang chờ trong generator xuống đích; tùy cấu hình, thao tác flush còn được chuyển tiếp đến stream/writer bên dưới.
- **`close()`:** kết thúc generator, xử lý phần JSON còn mở theo cấu hình và đóng hoặc nhường quyền quản lý tài nguyên đầu ra theo chính sách của generator.

Quản lý đúng ba phần này giúp tránh dữ liệu bị giữ trong bộ đệm, tránh đóng nhầm stream do thành phần khác sở hữu và bảo đảm tài nguyên được giải phóng kể cả khi quá trình ghi phát sinh exception.

## 1. JsonGenerator ghi dữ liệu qua các lớp bộ đệm

Một luồng ghi JSON thường có các thành phần:

```text
Ứng dụng
   │ writeStartObject(), writeStringField(), ...
   ▼
JsonGenerator
   │ bộ đệm nội bộ của Jackson
   ▼
OutputStream hoặc Writer
   │ có thể có BufferedOutputStream / BufferedWriter
   ▼
Hệ điều hành, file hoặc kết nối mạng
```

`JsonGenerator` chuyển các lệnh ghi thành cú pháp JSON và có thể giữ byte/ký tự trong buffer nội bộ. Khi buffer đầy, generator tự ghi một phần dữ liệu xuống output target. Khi ứng dụng gọi `flush()`, generator đẩy phần dữ liệu còn chờ xuống target.

Nếu target cũng là một wrapper có bộ đệm, ví dụ `BufferedOutputStream` hoặc `BufferedWriter`, dữ liệu sau khi rời buffer của Jackson vẫn có thể nằm trong buffer của wrapper. Việc flush generator có chuyển tiếp lệnh flush xuống target hay không phụ thuộc feature `FLUSH_PASSED_TO_STREAM`.

Ví dụ tạo generator từ output stream:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

JsonFactory factory = new JsonFactory();

try (OutputStream output = Files.newOutputStream(Path.of("order.json"));
     JsonGenerator generator = factory.createGenerator(output)) {

    generator.writeStartObject();
    generator.writeStringField("id", "ORD-1001");
    generator.writeNumberField("total", 250.00);
    generator.writeEndObject();
}
```

Khi khối `try` kết thúc, try-with-resources gọi `close()` trên generator rồi trên output stream. Generator hoàn tất phần ghi của nó; output stream sau đó được đóng. Cách này phù hợp khi đoạn code tạo và sở hữu cả hai tài nguyên.

## 2. Buffering giúp ích điều gì?

Nếu generator ghi xuống stream sau từng ký tự, số lần gọi I/O có thể rất lớn. Bộ đệm gom nhiều phần dữ liệu lại rồi ghi theo từng khối, nhờ đó giảm overhead.

Ví dụ:

```java
generator.writeStartObject();
generator.writeStringField("name", "An");
generator.writeNumberField("age", 28);
generator.writeBooleanField("active", true);
generator.writeEndObject();
```

Các lệnh trên cập nhật luồng output của generator. Ứng dụng không cần tự tạo chuỗi JSON hoàn chỉnh rồi mới ghi; generator quản lý bộ đệm và việc escape ký tự cho JSON.

Jackson có buffer nội bộ thông qua cơ chế quản lý I/O của factory. Có thể bọc thêm target bằng `BufferedOutputStream` hoặc `BufferedWriter`, nhưng không phải lúc nào cũng cần. Thêm nhiều lớp buffer có thể làm tăng độ phức tạp của vòng đời tài nguyên và khiến ứng dụng phải hiểu rõ flush ở từng lớp.

Hãy bắt đầu với generator và output target phù hợp. Chỉ thêm buffer bên ngoài khi có lý do đo đạc hoặc yêu cầu cụ thể về I/O.

## 3. flush() làm gì?

`JsonGenerator.flush()` yêu cầu generator đẩy dữ liệu đang giữ trong buffer nội bộ xuống output target. `flush()` không kết thúc object/array JSON, không kết thúc generator và không đóng output stream.

Ví dụ:

```java
generator.writeStartObject();
generator.writeStringField("status", "PROCESSING");
generator.flush();

// Generator vẫn có thể tiếp tục ghi.
generator.writeNumberField("progress", 50);
generator.writeEndObject();
generator.flush();
```

Lần flush đầu đẩy dữ liệu đã ghi đến thời điểm đó xuống target, nhưng object JSON vẫn đang mở. Ứng dụng tiếp tục ghi `progress` rồi đóng object. Lần flush sau đẩy phần còn lại xuống target.

Trong một JSON document thông thường, thường chỉ cần để generator tự flush khi buffer đầy và gọi `close()` khi hoàn tất. Gọi `flush()` sau mỗi field thường tạo nhiều thao tác I/O không cần thiết và có thể làm giảm throughput.

### 3.1. Khi nào nên gọi flush()?

Flush có ích khi dữ liệu cần được chuyển xuống target trước khi generator kết thúc, chẳng hạn:

- Ghi một phần kết quả ra kết nối đang mở và bên nhận cần nhận sớm.
- Ghi từng record theo một giao thức streaming có ranh giới record rõ ràng.
- Sau khi ghi xong một phần log hoặc một đoạn output, ứng dụng cần các lớp bên dưới nhận dữ liệu.
- Đang dùng `BufferedOutputStream`/`BufferedWriter` và muốn đẩy cả buffer của wrapper xuống lớp tiếp theo.

Với JSON document thông thường ghi ra file, flush trước khi close thường không cần thiết vì `close()` sẽ hoàn tất việc ghi. Hãy gọi flush tại ranh giới có ý nghĩa với giao thức hoặc ứng dụng, không gọi lặp lại một cách máy móc.

## 4. FLUSH_PASSED_TO_STREAM điều khiển việc chuyển tiếp flush

Jackson cung cấp `JsonGenerator.Feature.FLUSH_PASSED_TO_STREAM`. Feature này quyết định liệu lệnh `JsonGenerator.flush()` có được chuyển tiếp đến `flush()` của output target bên dưới hay không.

- Khi bật, generator flush buffer nội bộ rồi gọi flush trên `OutputStream` hoặc `Writer` được dùng làm target.
- Khi tắt, generator vẫn đẩy buffer nội bộ của nó xuống target, nhưng không yêu cầu target flush buffer riêng của target.

Feature này mặc định được bật trong Jackson Core thông dụng.

Ví dụ tắt việc chuyển tiếp flush:

```java
import com.fasterxml.jackson.core.JsonGenerator;

generator.disable(JsonGenerator.Feature.FLUSH_PASSED_TO_STREAM);
```

Giả sử target là `BufferedOutputStream`. Khi gọi `generator.flush()` với feature bị tắt, byte có thể đã được chuyển khỏi buffer của Jackson sang buffer của `BufferedOutputStream`, nhưng wrapper vẫn chưa đẩy byte xuống stream bên dưới. Nếu cần đẩy cả lớp wrapper, ứng dụng có thể gọi `output.flush()` trực tiếp hoặc giữ feature chuyển tiếp flush được bật.

Thông thường không cần tắt feature này. Chỉ thay đổi khi ứng dụng chủ động quản lý nhiều lớp buffer và hiểu rõ thời điểm dữ liệu phải được đẩy xuống từng lớp.

## 5. close() khác flush() như thế nào?

`close()` kết thúc vòng đời của `JsonGenerator`. Sau khi generator đóng, không được tiếp tục gọi các phương thức ghi trên generator đó.

Những việc liên quan đến close gồm:

1. Hoàn tất nội dung JSON còn mở theo chính sách `AUTO_CLOSE_JSON_CONTENT`.
2. Đẩy dữ liệu còn trong buffer của generator ra target.
3. Đóng target nếu generator chịu trách nhiệm quản lý target theo `AUTO_CLOSE_TARGET` hoặc theo trạng thái resource được factory quản lý.
4. Giải phóng tài nguyên nội bộ của generator.

`flush()` chỉ đẩy dữ liệu đang chờ; generator vẫn mở để tiếp tục ghi. `close()` kết thúc generator và thực hiện các bước hoàn tất cần thiết.

| Thao tác | Đẩy buffer của generator | Kết thúc generator | Đóng target theo cấu hình |
| --- | --- | --- | --- |
| `flush()` | Có | Không | Không |
| `close()` | Có, như một phần của quá trình đóng | Có | Có thể, tùy quyền quản lý target và feature |

Không nên dùng `flush()` thay cho `close()`. Nếu generator không được đóng, tài nguyên nội bộ có thể không được giải phóng và target có thể không được hoàn tất đúng cách.

## 6. AUTO_CLOSE_TARGET và quyền sở hữu stream

`JsonGenerator.Feature.AUTO_CLOSE_TARGET` điều khiển việc generator có tự đóng output target khi generator được đóng hay không. Trong cấu hình thông dụng, feature này mặc định bật.

Khi generator tạo từ một stream mà chính đoạn code đó sở hữu, để mặc định là hợp lý:

```java
try (OutputStream output = Files.newOutputStream(path);
     JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("status", "DONE");
    generator.writeEndObject();
}
```

Khi generator được tạo từ stream do thành phần khác sở hữu, việc generator tự đóng stream có thể gây lỗi. Ví dụ, một thư viện nhận `OutputStream` từ caller để ghi một phần JSON, nhưng caller còn cần tiếp tục dùng stream sau khi generator kết thúc.

Trong trường hợp đó, có thể tắt auto-close target:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    JsonGenerator generator = factory.createGenerator(output);
    generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);

    try (generator) {
        generator.writeStartObject();
        generator.writeStringField("message", "part of a larger stream");
        generator.writeEndObject();
    }

    // Generator đã đóng, nhưng output vẫn do khối bên ngoài quản lý.
    output.write('\n');
}
```

Ví dụ này minh họa quyền sở hữu tài nguyên: khối ngoài tạo và đóng `output`; generator chỉ sử dụng nó và không tự đóng target khi generator được đóng. Khi khối ngoài kết thúc, `output` mới được đóng.

Trong các phiên bản Jackson mới, cấu hình stream feature có thể được biểu diễn qua `StreamWriteFeature.AUTO_CLOSE_TARGET` trong API builder/configuration mới hơn. Hãy dùng API tương ứng với phiên bản dependency của dự án; `JsonGenerator.Feature.AUTO_CLOSE_TARGET` vẫn là cách quen thuộc trong nhiều ví dụ Jackson 2.x.

Lưu ý: nếu factory tự tạo stream từ `File` hoặc một nguồn tài nguyên do factory quản lý, factory có thể xem đó là resource managed và đóng nó khi generator đóng. Muốn caller quản lý vòng đời, hãy truyền một `OutputStream`/`Writer` do caller tạo và cấu hình quyền sở hữu rõ ràng.

## 7. AUTO_CLOSE_JSON_CONTENT: đóng cấu trúc JSON còn mở

`JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT` điều khiển việc generator tự hoàn tất object hoặc array chưa được đóng khi `close()` được gọi. Feature này mặc định bật trong Jackson Core thông dụng.

Ví dụ:

```java
JsonGenerator generator = factory.createGenerator(output);
generator.writeStartObject();
generator.writeStringField("id", "ORD-1001");
// Quên writeEndObject()
generator.close();
```

Với `AUTO_CLOSE_JSON_CONTENT` bật, generator có thể tự ghi token kết thúc object trước khi đóng. Điều này giúp output có cấu trúc JSON hoàn chỉnh trong một số trường hợp, nhưng không nên dựa vào nó để thay thế việc quản lý cặp start/end một cách chính xác.

Đối với array lồng trong object, generator sẽ hoàn tất các cấu trúc đang mở theo thứ tự cần thiết để đóng các container. Tuy nhiên, tự động đóng không thể sửa mọi lỗi logic, chẳng hạn field đang chờ value hoặc ứng dụng đã ghi một chuỗi token không đúng hợp đồng.

Nếu tắt feature:

```java
generator.disable(JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT);
```

generator sẽ không tự thêm token đóng cho các container còn mở khi close. Nếu code quên `writeEndObject()` hoặc `writeEndArray()`, output có thể là JSON không hoàn chỉnh và parser phía nhận sẽ báo lỗi.

Vì vậy, thông thường nên giữ feature mặc định và vẫn viết rõ các lệnh `writeEndObject()`/`writeEndArray()`. Cấu trúc start/end tường minh giúp code dễ đọc, dễ kiểm tra và không phụ thuộc vào việc generator tự sửa phần kết thúc.

## 8. Kết hợp try-with-resources để không rò rỉ tài nguyên

Java try-with-resources tự động gọi `close()` trên tài nguyên khi rời khỏi khối, kể cả khi có exception. `JsonGenerator` triển khai `Closeable`, vì vậy có thể dùng trực tiếp.

```java
try (JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartArray();
    generator.writeString("Java");
    generator.writeString("Jackson");
    generator.writeEndArray();
}
```

Khi generator là tài nguyên duy nhất do đoạn code sở hữu, đây là cách đơn giản. Nếu output target cũng do đoạn code sở hữu và cần kiểm soát rõ thứ tự đóng, khai báo cả hai tài nguyên trong cùng try-with-resources:

```java
try (OutputStream output = Files.newOutputStream(path);
     JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartArray();
    generator.writeNumber(10);
    generator.writeNumber(20);
    generator.writeEndArray();
}
```

Java đóng tài nguyên theo thứ tự ngược với thứ tự khai báo: generator đóng trước, rồi output đóng sau. Điều này phù hợp vì generator cần target còn mở trong lúc hoàn tất việc ghi.

Nếu generator mặc định tự đóng target, việc output được đóng lần nữa bởi try-with-resources thường được các stream chuẩn hỗ trợ an toàn, nhưng quản lý ownership rõ ràng vẫn giúp tránh phụ thuộc vào hành vi của một implementation stream cụ thể.

## 9. BufferedOutputStream và BufferedWriter

Ứng dụng có thể bọc target bằng buffer bên ngoài:

```java
try (OutputStream file = Files.newOutputStream(path);
     BufferedOutputStream buffered = new BufferedOutputStream(file);
     JsonGenerator generator = factory.createGenerator(buffered)) {

    generator.writeStartObject();
    generator.writeStringField("status", "READY");
    generator.writeEndObject();
    generator.flush();
}
```

Ở đây có thể tồn tại ít nhất hai lớp buffer: buffer của generator và buffer của `BufferedOutputStream`. Với `FLUSH_PASSED_TO_STREAM` bật, `generator.flush()` chuyển tiếp flush xuống wrapper, nhờ đó wrapper đẩy dữ liệu của nó xuống file stream.

Nếu feature này tắt, `generator.flush()` chỉ đẩy buffer Jackson vào `BufferedOutputStream`; wrapper có thể vẫn giữ dữ liệu. Khi đó cần gọi `buffered.flush()` nếu ứng dụng thực sự cần đẩy buffer wrapper tại thời điểm đó.

Với `Writer`, nguyên tắc tương tự áp dụng cho `BufferedWriter`. Cần phân biệt encoding và loại target: nếu ghi JSON ra `OutputStream`, factory có thể dùng `JsonEncoding.UTF8`; nếu ghi qua `Writer`, encoding đã được quyết định bởi writer mà caller cung cấp.

Không thêm nhiều lớp buffer chỉ theo thói quen. Hãy đo hiệu năng và chọn một cấu trúc đơn giản, rõ quyền sở hữu.

## 10. Flush không đồng nghĩa với dữ liệu đã bền vững trên đĩa

Flush thường có nghĩa dữ liệu đang nằm trong các buffer của generator/wrapper được chuyển xuống lớp bên dưới. Điều đó không nhất thiết đồng nghĩa dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ.

Ví dụ, `OutputStream.flush()` không phải API đồng bộ hóa vật lý tương đương `FileDescriptor.sync()` hoặc `FileChannel.force(...)`. Nếu ứng dụng cần bảo đảm dữ liệu file được đẩy xuống storage theo yêu cầu durability, phải dùng cơ chế của tầng file/hệ điều hành phù hợp.

Tương tự, flush một response HTTP không bảo đảm client đã nhận và xử lý dữ liệu. Nó chỉ yêu cầu các lớp output đẩy dữ liệu đang buffer về phía kết nối; lỗi mạng hoặc việc client ngắt kết nối vẫn có thể xảy ra.

Vì vậy, hãy dùng đúng thuật ngữ: flush đẩy buffer; close kết thúc tài nguyên; durability và delivery là các vấn đề ở tầng khác.

## 11. Ghi JSON từng phần trên một kết nối đang mở

Trong một luồng phản hồi dài hoặc giao thức truyền record, ứng dụng có thể cần ghi một phần dữ liệu rồi flush để bên nhận bắt đầu xử lý. Ví dụ, nếu hệ thống dùng NDJSON (mỗi dòng là một JSON document độc lập), có thể ghi một object, thêm newline rồi flush tại ranh giới record:

```java
try (JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("event", "started");
    generator.writeEndObject();
    generator.writeRaw('\n');
    generator.flush();

    generator.writeStartObject();
    generator.writeStringField("event", "completed");
    generator.writeEndObject();
    generator.writeRaw('\n');
    generator.flush();
}
```

Đây là ví dụ về giao thức NDJSON do ứng dụng lựa chọn. Một JSON document chuẩn thông thường chỉ có một giá trị gốc; nhiều object nối tiếp cần quy ước framing rõ ràng như newline-delimited JSON hoặc length-prefix. `flush()` không tự tạo ranh giới record và cũng không làm một JSON document chưa hoàn chỉnh trở thành hợp lệ.

Với NDJSON, mỗi record phải được ghi hoàn chỉnh trước newline và flush. Nếu ứng dụng cần một JSON array duy nhất, hãy giữ array mở, ghi từng phần tử theo cú pháp array và đóng array trước khi kết thúc generator.

## 12. Xử lý exception khi ghi

Ghi JSON có thể thất bại do lỗi I/O, stream bị đóng sớm, client ngắt kết nối hoặc lỗi dữ liệu khi serializer chuyển đổi property. Try-with-resources giúp gọi `close()` ngay cả khi thân khối phát sinh exception.

Ví dụ:

```java
try (JsonGenerator generator = factory.createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("id", order.getId());
    generator.writeNumberField("total", order.getTotal().doubleValue());
    generator.writeEndObject();
} catch (IOException e) {
    // Ghi nhận lỗi I/O và xử lý theo ngữ cảnh của ứng dụng.
    throw new UncheckedIOException("Không thể ghi JSON", e);
}
```

Trong code thực tế, không nên chuyển `BigDecimal` sang `double` nếu cần giữ chính xác số thập phân; ví dụ trên chỉ minh họa luồng exception. Có thể dùng `generator.writeNumber(order.getTotal().toPlainString())` hoặc API ghi số phù hợp để giữ giá trị decimal theo hợp đồng.

Nếu `close()` cũng phát sinh lỗi trong lúc một exception khác đang được ném, try-with-resources giữ lỗi đóng như suppressed exception. Điều này giúp không làm mất exception gốc từ thân khối.

## 13. Cấu hình feature ở đâu?

Các feature liên quan đến vòng đời generator thường có thể được đặt trên generator cụ thể hoặc cấu hình ở factory để áp dụng cho generator được tạo từ factory đó.

Ví dụ cấu hình ngay trên generator:

```java
generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);
generator.enable(JsonGenerator.Feature.FLUSH_PASSED_TO_STREAM);
generator.enable(JsonGenerator.Feature.AUTO_CLOSE_JSON_CONTENT);
```

Hoặc cấu hình factory trước khi tạo generator:

```java
JsonFactory factory = JsonFactory.builder()
        .configure(StreamWriteFeature.AUTO_CLOSE_TARGET, false)
        .build();
```

API builder với `StreamWriteFeature` có trong các phiên bản Jackson mới; với phiên bản cũ hơn, có thể dùng `JsonGenerator.Feature` thông qua factory/generator API tương ứng. Hãy kiểm tra dependency version của dự án trước khi chọn cách cấu hình.

Các feature quan trọng:

| Feature | Mặc định thường gặp | Tác dụng |
| --- | --- | --- |
| `AUTO_CLOSE_TARGET` | Bật | Generator tự đóng target khi close nếu generator chịu trách nhiệm quản lý target |
| `AUTO_CLOSE_JSON_CONTENT` | Bật | Generator tự đóng object/array còn mở khi close |
| `FLUSH_PASSED_TO_STREAM` | Bật | Chuyển tiếp `flush()` đến output target bên dưới |

Không nên tắt các feature chỉ để né một lỗi vòng đời. Trước tiên, xác định ai sở hữu target, khi nào bên nhận cần dữ liệu và generator có được phép kết thúc cấu trúc JSON đang mở hay không.

## 14. Quy trình lựa chọn thực tế

Khi triển khai ghi JSON theo luồng, có thể quyết định theo trình tự:

1. **Ai tạo target?** Nếu code tạo `OutputStream`/`Writer`, code đó thường chịu trách nhiệm đóng nó. Nếu target được truyền từ caller, cần xác định generator có được phép đóng hay không.
2. **Có cần dữ liệu xuất hiện trước khi kết thúc không?** Nếu không, để generator buffer và đóng khi hoàn tất. Nếu có, flush tại ranh giới ứng dụng có ý nghĩa.
3. **Có buffer bên ngoài không?** Nếu có, kiểm tra `FLUSH_PASSED_TO_STREAM` và xác định lớp nào cần được flush.
4. **Cấu trúc JSON đã đóng đầy đủ chưa?** Gọi `writeEndObject()` và `writeEndArray()` rõ ràng trước khi close.
5. **Có cần generator tự đóng target không?** Chọn `AUTO_CLOSE_TARGET` theo ownership.
6. **Có cần giới hạn tài nguyên không?** Tránh flush quá thường xuyên, tránh giữ stream mở quá lâu và xử lý exception bằng try-with-resources.

## 15. Ghi nhớ

- `JsonGenerator` dùng buffer nội bộ để gom dữ liệu trước khi ghi xuống `OutputStream` hoặc `Writer`.
- `flush()` đẩy dữ liệu đang chờ xuống target nhưng không kết thúc generator và không đóng target.
- `FLUSH_PASSED_TO_STREAM` quyết định lệnh flush có được chuyển tiếp đến stream/writer bên dưới hay không.
- `close()` kết thúc generator, hoàn tất dữ liệu còn lại và xử lý target theo chính sách quản lý tài nguyên.
- `AUTO_CLOSE_TARGET` quyết định generator có tự đóng output target hay không; hãy đặt theo quyền sở hữu stream.
- `AUTO_CLOSE_JSON_CONTENT` cho phép generator tự hoàn tất container JSON còn mở khi đóng, nhưng code vẫn nên viết rõ token kết thúc.
- Try-with-resources bảo đảm generator và target được đóng đúng thứ tự ngay cả khi có exception.
- Flush không bảo đảm dữ liệu đã bền vững trên đĩa hoặc client đã nhận được dữ liệu.
- Chỉ flush tại ranh giới có ý nghĩa; flush sau từng field có thể làm giảm hiệu năng.

Khi dùng Jackson Streaming API, hãy quản lý riêng ba câu hỏi: dữ liệu đang nằm trong buffer nào, khi nào cần đẩy dữ liệu xuống target và ai chịu trách nhiệm đóng target. Một quy ước ownership rõ ràng cùng try-with-resources sẽ giúp tránh mất dữ liệu chưa flush, đóng nhầm stream và rò rỉ tài nguyên.
