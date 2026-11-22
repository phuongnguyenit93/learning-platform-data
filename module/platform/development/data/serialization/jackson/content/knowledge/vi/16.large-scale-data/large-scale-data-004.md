# Phân biệt một mảng JSON và chuỗi nhiều giá trị gốc

Khi xử lý dữ liệu lớn, một nguồn có thể gửi nhiều bản ghi JSON trong cùng một luồng. Có hai cách tổ chức dễ bị nhầm lẫn:

1. **Một JSON document có root là array:** toàn bộ bản ghi nằm trong một mảng JSON duy nhất.
2. **Một chuỗi gồm nhiều JSON value ở root:** mỗi bản ghi là một JSON text riêng, được đặt liên tiếp trong cùng luồng và phân cách theo quy ước của giao thức.

Ví dụ, đây là một JSON document có root array:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Còn đây là hai JSON object ở root, được phân cách bằng newline:

```text
{"id": 1, "name": "An"}
{"id": 2, "name": "Binh"}
```

Hai dạng có thể chứa cùng bản ghi nhưng khác cấu trúc và cách đóng khung. JSON chuẩn định nghĩa một JSON text là một giá trị ở root; một chuỗi nhiều root value cần quy ước framing riêng. NDJSON/JSON Lines là một quy ước phổ biến: mỗi dòng chứa một JSON text độc lập. Jackson hỗ trợ đọc và ghi cả array lẫn chuỗi nhiều root value bằng các API streaming phù hợp.

## 1. Một JSON document có root là array

Trong cách tổ chức này, file hoặc message là một JSON document duy nhất. Root của document là array, mỗi phần tử đại diện cho một bản ghi.

```json
[
  {"id": 101, "event": "created"},
  {"id": 102, "event": "updated"},
  {"id": 103, "event": "deleted"}
]
```

Các đặc điểm:

- Có đúng một root value là array.
- Mảng bắt đầu bằng `[` và kết thúc bằng `]`.
- Các phần tử được phân cách bằng dấu phẩy.
- Bản ghi có thể là object, scalar, array hoặc `null`, tùy schema.
- Toàn bộ nội dung là một JSON document; nếu thiếu dấu `]` do file bị cắt, document chưa hoàn chỉnh.

Đây là định dạng phù hợp khi hệ thống muốn trao đổi một danh sách như một đơn vị dữ liệu. Client có thể parse toàn bộ thành `List<Event>` nếu kích thước vừa phải, hoặc xử lý từng phần tử bằng streaming nếu dữ liệu lớn.

## 2. Một chuỗi nhiều JSON value ở root

Một luồng có thể chứa nhiều JSON text độc lập nối tiếp nhau, ví dụ:

```text
{"id": 101, "event": "created"}
{"id": 102, "event": "updated"}
{"id": 103, "event": "deleted"}
```

Mỗi dòng ở đây là một object hoàn chỉnh. Newline đóng vai trò dấu phân cách theo quy ước của nguồn dữ liệu; parser cũng xem newline là whitespace giữa các JSON value.

Khác với array:

- Không có `[` ở đầu và `]` ở cuối để bao bọc toàn bộ bản ghi.
- Mỗi JSON text có root riêng.
- Không có dấu phẩy phân cách các root value.
- Luồng cần một quy ước xác định ranh giới record, chẳng hạn whitespace hoặc newline.
- Đây không phải một JSON document duy nhất theo cú pháp JSON chuẩn.

Jackson Core có thể đọc nhiều root value tuần tự từ cùng một parser. Với Databind, `ObjectReader.readValues(...)` trả về `MappingIterator<T>` để xử lý từng value mà không cần tạo một collection chứa tất cả kết quả.

## 3. NDJSON / JSON Lines là gì?

NDJSON (Newline Delimited JSON) và JSON Lines là các quy ước lưu/truyền nhiều JSON text, mỗi record nằm trên một dòng. Một file NDJSON có thể trông như sau:

```text
{"timestamp":"2026-11-12T09:00:00Z","level":"INFO","message":"Started"}
{"timestamp":"2026-11-12T09:00:01Z","level":"WARN","message":"Retrying"}
{"timestamp":"2026-11-12T09:00:02Z","level":"INFO","message":"Completed"}
```

Mỗi dòng là một JSON value độc lập. Thông thường record được ghi ở dạng compact, không pretty print nhiều dòng. Newline thực tế trong một string phải được escape thành `\\n`, không được xuất hiện như một line break thô bên trong JSON text của record.

NDJSON hữu ích cho:

- Log ứng dụng hoặc audit event.
- Export dữ liệu nhiều bản ghi.
- Pipeline xử lý tuần tự và hệ thống ingest log.
- Truyền dữ liệu qua stream mà không cần biết trước tổng số record.
- Khôi phục xử lý theo record khi một dòng lỗi, nếu ứng dụng có chính sách xử lý lỗi phù hợp.

NDJSON là quy ước framing chứ không phải cách viết một JSON array. Nhiều công cụ hỗ trợ NDJSON, nhưng cần thống nhất encoding, newline, cách xử lý dòng trống và cách báo lỗi giữa bên gửi và bên nhận.

## 4. So sánh các hình thức dữ liệu

| Đặc điểm | JSON array | Nhiều root JSON value | NDJSON |
|---|---|---|---|
| Cấu trúc | Một document có root array | Nhiều JSON text liên tiếp | Nhiều JSON text, mỗi text trên một dòng |
| Ký tự bao ngoài | `[` và `]` | Không có wrapper chung | Không có wrapper chung |
| Dấu phân cách record | Dấu phẩy trong array | Quy ước phân cách, thường là whitespace | Newline (`LF` hoặc `CRLF`) |
| Tính chuẩn | Một JSON document hợp lệ | Chuỗi nhiều JSON text, cần giao thức quy định | Quy ước dòng cho nhiều JSON text |
| Pretty print nhiều dòng | Có thể | Có thể nếu parser/giao thức cho phép whitespace | Không phù hợp vì phá ranh giới record theo dòng |
| Xử lý từng record | Có, bằng streaming array | Có, bằng sequence reader/parser | Có, bằng đọc từng dòng hoặc sequence reader |
| Dữ liệu bị cắt | Có thể làm hỏng toàn document | Có thể chỉ hỏng record cuối hoặc phần sau | Thường có thể nhận diện record cuối chưa hoàn chỉnh |

Điểm cần phân biệt: NDJSON cũng là một dạng chuỗi nhiều JSON value ở root, nhưng có quy ước rõ hơn về ranh giới dòng. Không phải mọi chuỗi nhiều root value đều là NDJSON; ví dụ nhiều JSON text được phân cách bằng space hoặc được đóng khung bằng một giao thức khác.

## 5. Đọc JSON array thành `List` khi dữ liệu vừa phải

Nếu dữ liệu không quá lớn và ứng dụng cần truy cập toàn bộ danh sách, có thể đọc array thành `List<T>` bằng `TypeReference`:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

List<Event> events = mapper.readValue(
        jsonArray,
        new TypeReference<List<Event>>() {}
);
```

Jackson tạo một list và deserialize từng phần tử thành `Event`. Cách này đơn giản, nhưng toàn bộ list và các object phần tử được giữ trong bộ nhớ. Với file rất lớn, đây có thể là phần tiêu tốn RAM đáng kể.

Không dùng `List.class` nếu cần giữ kiểu phần tử cụ thể. `List.class` làm mất thông tin generic; các phần tử object có thể trở thành `LinkedHashMap` thay vì `Event`.

## 6. Đọc JSON array theo streaming bằng `MappingIterator`

Với dữ liệu lớn, `ObjectReader.readValues(...)` cho phép xử lý từng phần tử của array. Không cần dựng toàn bộ `List<Event>`:

```java
import com.fasterxml.jackson.databind.MappingIterator;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.InputStream;

public void processArray(InputStream input) throws IOException {
    ObjectMapper mapper = new ObjectMapper();
    ObjectReader reader = mapper.readerFor(Event.class);

    try (MappingIterator<Event> events = reader.readValues(input)) {
        while (events.hasNextValue()) {
            Event event = events.nextValue();
            process(event);
        }
    }
}
```

Khi input bắt đầu bằng một JSON array, `MappingIterator` đọc các phần tử trong array theo thứ tự và chuyển từng phần tử thành `Event`. Iterator không cần giữ toàn bộ danh sách đã đọc. Bộ nhớ chủ yếu dành cho parser, buffer và record hiện tại cùng dữ liệu mà `process()` chủ động lưu lại.

`MappingIterator` là `Closeable`; đóng iterator kết thúc việc đọc và đóng parser/tài nguyên liên quan theo cấu hình. Dùng `try-with-resources` để bảo đảm tài nguyên được giải phóng.

### 6.1. Xử lý record ngay khi đọc

```java
try (MappingIterator<Event> events = mapper.readerFor(Event.class)
        .readValues(input)) {
    while (events.hasNextValue()) {
        Event event = events.nextValue();
        validate(event);
        repository.save(event);
    }
}
```

Đoạn code xử lý từng record ngay khi parser cung cấp. Trong hệ thống thực tế, cần cân nhắc transaction theo batch, idempotency và cách xử lý lỗi. Nếu một record lỗi ở giữa array, việc parse thường không thể tiếp tục một cách an toàn nếu lỗi làm mất đồng bộ cấu trúc; cần xác định rõ có rollback toàn batch hay dừng tại record lỗi.

## 7. Đọc nhiều JSON value ở root bằng `MappingIterator`

Nếu nguồn gửi nhiều object JSON liên tiếp, không có array wrapper, vẫn có thể dùng `ObjectReader.readValues(...)`:

```text
{"id":1,"name":"An"}
{"id":2,"name":"Binh"}
{"id":3,"name":"Chi"}
```

Code đọc:

```java
ObjectReader reader = mapper.readerFor(Event.class);

try (MappingIterator<Event> events = reader.readValues(inputStream)) {
    while (events.hasNextValue()) {
        Event event = events.nextValue();
        process(event);
    }
}
```

`readValues()` đọc chuỗi value tuần tự từ parser. Mỗi object root được ánh xạ thành một `Event`; khi hết luồng, iterator kết thúc.

Đây là điểm khác biệt quan trọng giữa `readValue()` và `readValues()`:

- `readValue(input, Event.class)` đọc một JSON value làm kết quả.
- `readValues(input)` cung cấp một iterator cho chuỗi nhiều value.

Nếu gọi `readValue()` cho luồng có nhiều root object, lời gọi đó chỉ nhằm đọc một value; phần còn lại không được xử lý như một collection tự động. Dùng `MappingIterator` khi giao thức thực sự là sequence.

### 7.1. Nhiều root value không phải một JSON document chuẩn

Đoạn sau:

```text
{"id":1} {"id":2}
```

là hai JSON object root được đặt trong một luồng. Mỗi object riêng lẻ là một JSON text hợp lệ, nhưng toàn bộ chuỗi không phải một JSON document đơn lẻ theo cú pháp JSON chuẩn. Vì vậy, chỉ dùng dạng này khi giao thức hai phía đã thống nhất rằng parser sẽ đọc một sequence.

Không nối nhiều object bằng dấu phẩy mà không có array:

```text
{"id":1},{"id":2}
```

Đây không phải cách phân cách root value thông thường của Jackson. Nếu muốn một document, dùng array; nếu muốn nhiều root value, dùng separator của giao thức như whitespace/newline hoặc một định dạng sequence được quy định.

## 8. Đọc NDJSON từng dòng

Nếu yêu cầu của giao thức là mỗi dòng chứa đúng một JSON text, cách dễ kiểm soát framing nhất là đọc từng dòng bằng `BufferedReader`, rồi deserialize riêng từng dòng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public void processNdjson(InputStream input, ObjectMapper mapper)
        throws IOException {
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        String line;
        long lineNumber = 0;

        while ((line = reader.readLine()) != null) {
            lineNumber++;
            if (line.isBlank()) {
                continue; // Chỉ bỏ dòng trống nếu hợp đồng cho phép.
            }

            try {
                Event event = mapper.readValue(line, Event.class);
                process(event);
            } catch (JsonProcessingException ex) {
                handleInvalidRecord(lineNumber, ex);
            }
        }
    }
}
```

Ưu điểm của cách đọc theo dòng:

- Ranh giới record rõ ràng.
- Có thể báo lỗi theo số dòng.
- Một dòng lỗi có thể được cách ly hoặc ghi nhận mà không nhất thiết bỏ toàn bộ file.
- Không cần đọc toàn bộ file vào bộ nhớ.

Đoạn code giả định mỗi dòng là một JSON text hoàn chỉnh và record không được pretty print thành nhiều dòng. Cũng cần quyết định chính sách với dòng trống; không nên âm thầm bỏ qua nếu dòng trống là dữ liệu lỗi theo hợp đồng.

### 8.1. Vì sao không nên pretty print record NDJSON?

NDJSON dùng newline để phân cách record. Nếu một object được pretty print thành nhiều dòng, ví dụ:

```text
{
  "id": 1,
  "name": "An"
}
```

thì một reader coi mỗi dòng là một record sẽ parse sai. Vì vậy, mỗi JSON text trong NDJSON nên được ghi compact trên một dòng. Khoảng trắng bên trong JSON string vẫn được escape theo cú pháp JSON; newline giữa các record mới là dấu phân cách framing.

## 9. Đọc NDJSON bằng `MappingIterator`

Vì newline là whitespace trong JSON, một parser Jackson có thể đọc các root value tuần tự từ NDJSON compact:

```java
ObjectReader reader = mapper.readerFor(Event.class);

try (MappingIterator<Event> events = reader.readValues(inputStream)) {
    while (events.hasNextValue()) {
        process(events.nextValue());
    }
}
```

Cách này hiệu quả và ngắn gọn khi nguồn bảo đảm sequence gồm các JSON text hợp lệ, phân cách bằng whitespace. Tuy nhiên, parser đang đọc một sequence JSON value tổng quát; nó không kiểm tra quy tắc “một record đúng một dòng”. Nếu cần báo lỗi theo dòng, bỏ qua dòng trống hoặc cô lập record lỗi để tiếp tục, đọc từng dòng sẽ phù hợp hơn.

Nếu mỗi JSON record có thể trải qua nhiều dòng, nguồn đó không còn tuân theo NDJSON framing thông thường. Khi cần nhiều JSON text có định dạng nhiều dòng, hãy chọn giao thức sequence có dấu phân cách record rõ ràng.

## 10. Đọc bằng Jackson Core `JsonParser`

Khi cần kiểm soát token trực tiếp, có thể dùng `JsonParser` thay vì Databind:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

try (JsonParser parser = new JsonFactory().createParser(inputStream)) {
    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        if (token == JsonToken.START_OBJECT) {
            // Bắt đầu một object root hoặc object lồng nhau.
        } else if (token == JsonToken.FIELD_NAME) {
            String fieldName = parser.currentName();
        } else if (token == JsonToken.VALUE_STRING) {
            String value = parser.getText();
        }
    }
}
```

Đoạn code trên chỉ minh họa việc duyệt token. Khi xử lý nhiều root object, cần theo dõi depth để phân biệt object root với object lồng nhau. Nếu cần deserialize từng root thành POJO, `MappingIterator` thường ngắn gọn hơn.

### 10.1. Theo dõi ranh giới root

Với sequence các object root, có thể đếm depth:

```java
int depth = 0;
while (parser.nextToken() != null) {
    JsonToken token = parser.currentToken();

    if (token == JsonToken.START_OBJECT || token == JsonToken.START_ARRAY) {
        depth++;
    } else if (token == JsonToken.END_OBJECT || token == JsonToken.END_ARRAY) {
        depth--;
        if (depth == 0) {
            // Một root container vừa kết thúc.
        }
    }
}
```

Nếu root value có thể là scalar, cần xử lý các token scalar ở depth 0 như một record hoàn chỉnh. Với dữ liệu không đồng nhất, phải xác định schema hoặc discriminator trước khi quyết định cách xử lý từng root value.

## 11. Ghi một JSON array bằng `SequenceWriter`

Khi muốn xuất một JSON document có root array, `ObjectWriter.writeValuesAsArray(...)` cung cấp `SequenceWriter` để ghi từng object vào cùng array:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SequenceWriter;
import com.fasterxml.jackson.databind.ObjectWriter;

ObjectMapper mapper = new ObjectMapper();
ObjectWriter writer = mapper.writerFor(Event.class);

try (SequenceWriter sequence = writer.writeValuesAsArray(outputStream)) {
    for (Event event : events) {
        sequence.write(event);
    }
}
```

`SequenceWriter` quản lý dấu phẩy giữa các phần tử và dấu `[`/`]` bao quanh array. Mỗi lần `write(event)` ghi một phần tử. Đóng sequence hoàn tất array và đóng generator/tài nguyên theo cấu hình writer.

Đây là cách phù hợp khi nguồn cung cấp từng record nhưng output vẫn phải là một JSON array duy nhất. Không cần tự ghi dấu phẩy hoặc chuyển toàn bộ danh sách thành một object trung gian.

### 11.1. Ghi array bằng `JsonGenerator` trực tiếp

Nếu cần kiểm soát từng token, có thể mở array rồi ghi từng object. Khi muốn Databind serialize POJO, lấy factory từ mapper và gắn mapper làm codec:

```java
JsonFactory factory = mapper.getFactory();
try (JsonGenerator generator = factory.createGenerator(outputStream, JsonEncoding.UTF8)) {
    generator.writeStartArray();

    for (Event event : events) {
        mapper.writeValue(generator, event);
    }

    generator.writeEndArray();
}
```

Khi truyền generator do ứng dụng tạo vào `ObjectMapper.writeValue(JsonGenerator, ...)`, mapper ghi value vào generator hiện có. Ứng dụng vẫn chịu trách nhiệm đóng generator và hoàn tất array ngoài cùng.

Nếu chỉ cần serialize từng POJO, `SequenceWriter` thường rõ ràng hơn. Dùng generator trực tiếp khi mỗi record cần kết hợp các token thủ công hoặc có cấu trúc phức tạp.

## 12. Ghi nhiều root value và NDJSON bằng `SequenceWriter`

Khi muốn ghi nhiều JSON text độc lập, `ObjectWriter.writeValues(...)` tạo một sequence writer không có array wrapper:

```java
ObjectWriter writer = mapper.writerFor(Event.class)
        .withRootValueSeparator("\n");

try (SequenceWriter sequence = writer.writeValues(outputStream)) {
    for (Event event : events) {
        sequence.write(event);
    }
}
```

`withRootValueSeparator("\n")` quy định newline giữa các root value. Kết quả có dạng NDJSON compact nếu writer không bật pretty printer:

```text
{"id":1,"name":"An"}
{"id":2,"name":"Binh"}
{"id":3,"name":"Chi"}
```

Khác với `writeValuesAsArray()`, `writeValues()` không ghi `[` hoặc `]`. Nó ghi từng JSON root value và separator được cấu hình giữa chúng.

`SequenceWriter` cần được đóng để hoàn tất việc ghi và giải phóng generator. Nếu output stream thuộc framework/caller và phải tiếp tục được sử dụng, cấu hình `AUTO_CLOSE_TARGET` phù hợp trên factory/generator hoặc dùng stream wrapper không đóng target; quyền sở hữu tài nguyên phải được xác định rõ.

## 13. Ghi array và sequence bằng `JsonGenerator`

Có thể hình dung hai output như sau:

**Một JSON array:**

```java
generator.writeStartArray();
generator.writeObject(event1);
generator.writeObject(event2);
generator.writeEndArray();
```

Kết quả:

```json
[{"id":1},{"id":2}]
```

**Nhiều root value:**

```java
import com.fasterxml.jackson.core.io.SerializedString;

generator.setRootValueSeparator(new SerializedString("\n"));
generator.writeObject(event1);
generator.writeObject(event2);
```

Kết quả:

```text
{"id":1}
{"id":2}
```

Để `writeObject()` serialize POJO, generator cần có `ObjectCodec` phù hợp, thường lấy từ `ObjectMapper.getFactory()` hoặc gắn codec theo cấu hình. Với một `JsonFactory` thuần không có codec, hãy ghi token thủ công hoặc dùng Databind writer.

Không ghi root value sequence khi phía nhận mong đợi một JSON array. Hai định dạng có framing khác nhau và không thể thay thế cho nhau chỉ bằng cách bỏ dấu ngoặc.

## 14. JSON Text Sequences là một định dạng framing khác

Ngoài array và NDJSON, RFC 7464 định nghĩa JSON Text Sequences. Mỗi JSON text được bắt đầu bằng ký tự Record Separator (RS, byte `0x1E`), thường theo sau bởi JSON text và line feed:

```text
<RS>{"id":1,"event":"created"}\n
<RS>{"id":2,"event":"updated"}\n
```

RS giúp nhận diện ranh giới record ngay cả khi JSON text có nhiều dòng. Đây là định dạng khác NDJSON:

- NDJSON dùng newline làm ranh giới record và mỗi JSON text phải nằm trên một dòng.
- JSON Text Sequences dùng RS làm dấu bắt đầu record; JSON text có thể có formatting nhiều dòng.
- Một JSON array dùng dấu ngoặc và dấu phẩy trong một document duy nhất.

Jackson `JsonParser` có thể parse từng JSON text khi ứng dụng đã tách framing RS. `JsonGenerator` không tự động biến một sequence thông thường thành RFC 7464 chỉ bằng việc ghi nhiều root value; ứng dụng cần ghi RS và line feed đúng quy tắc hoặc dùng thư viện/giao thức có hỗ trợ framing đó.

Chọn JSON Text Sequences khi hệ thống cần framing record rõ ràng và khả năng đồng bộ lại sau lỗi/truncated record. Chỉ dùng khi hai phía đã thống nhất giao thức này.

## 15. Khả năng phục hồi khi một record bị lỗi

Một lợi ích của định dạng record độc lập là có thể khoanh vùng lỗi. Tuy nhiên, mức độ phục hồi phụ thuộc framing:

| Định dạng | Khi một record lỗi |
|---|---|
| JSON array | Lỗi cú pháp hoặc cấu trúc có thể làm parser mất khả năng tiếp tục an toàn; thường cần dừng document hoặc xử lý theo chính sách riêng |
| Root value sequence phân cách bằng whitespace | Có thể tiếp tục nếu parser vẫn đồng bộ tại ranh giới root, nhưng lỗi cú pháp có thể khiến không xác định được vị trí tiếp theo |
| NDJSON đọc từng dòng | Có thể cách ly dòng lỗi và tiếp tục dòng sau vì newline xác định ranh giới record |
| JSON Text Sequences | RS cung cấp dấu bắt đầu record để hỗ trợ đồng bộ lại theo quy tắc của giao thức |

Ví dụ xử lý lỗi theo dòng NDJSON:

```java
long lineNumber = 0;
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        lineNumber++;
        if (line.isBlank()) {
            continue;
        }

        try {
            Event event = mapper.readValue(line, Event.class);
            process(event);
        } catch (JsonProcessingException ex) {
            quarantine(lineNumber, line, ex);
        }
    }
}
```

Chỉ tiếp tục sau record lỗi khi hợp đồng cho phép. Nếu record lỗi làm mất tính nhất quán nghiệp vụ, ứng dụng có thể cần dừng toàn bộ import hoặc rollback batch thay vì cách ly riêng dòng đó.

Không ghi toàn bộ dòng lỗi vào log nếu payload có thể chứa thông tin nhạy cảm. Có thể lưu bản ghi vào vùng quarantine được kiểm soát, gắn line number, mã lỗi và correlation id.

## 16. Chọn định dạng theo kích thước và cách tiêu thụ

### 16.1. Chọn JSON array khi

- Consumer mong đợi một JSON document duy nhất.
- Toàn bộ danh sách là một đơn vị nghiệp vụ hoặc một response API.
- Cần tương thích với schema JSON có root array.
- Dữ liệu có thể được đọc toàn bộ hoặc được xử lý bằng streaming array.

### 16.2. Chọn NDJSON khi

- Có nhiều record độc lập được ghi liên tục.
- Muốn append record mới mà không phải sửa dấu `]` cuối file.
- Cần đọc, xử lý hoặc cách ly từng dòng.
- Pipeline ingest và công cụ downstream hỗ trợ newline-delimited records.
- Mỗi record có thể được serialize compact trên một dòng.

### 16.3. Chọn root sequence tổng quát khi

- Giao thức đã quy định rõ nhiều JSON text ở root và separator giữa chúng.
- Consumer dùng parser sequence thay vì parser một document đơn.
- Không cần array wrapper và không nhất thiết yêu cầu line framing.

### 16.4. Chọn JSON Text Sequences khi

- Cần dấu framing riêng cho mỗi record.
- Record có thể nhiều dòng.
- Giao thức cần khả năng đồng bộ lại dựa trên RS.
- Các hệ thống tham gia đã hỗ trợ RFC 7464.

Không nên chọn định dạng chỉ vì nó dễ ghi hơn. Cần cân nhắc consumer, khả năng phục hồi, hợp đồng API, công cụ xử lý và cách xác định ranh giới record.

## 17. Bộ nhớ và hiệu năng khi xử lý dữ liệu lớn

Đọc JSON array thành `List<Event>` có chi phí bộ nhớ tỷ lệ với số lượng record và kích thước object. Streaming bằng `MappingIterator` giúp xử lý từng record khi parser đọc đến, nhưng không tự bảo đảm toàn bộ pipeline dùng ít bộ nhớ.

Ví dụ, nếu `process(event)` thêm mọi event vào một list khác, ứng dụng vẫn giữ toàn bộ dữ liệu. Nếu repository gom tất cả câu lệnh insert vào một batch không giới hạn, bộ nhớ có thể tăng dù parser đang streaming.

Các nguyên tắc thực tế:

- Xử lý và giải phóng record sau khi hoàn tất.
- Dùng batch có kích thước giới hạn khi ghi database.
- Tránh tạo một chuỗi JSON khổng lồ chỉ để ghi ra file.
- Giới hạn kích thước record, độ sâu lồng nhau và tổng số record theo yêu cầu hệ thống.
- Theo dõi backpressure khi nguồn nhanh hơn consumer.
- Xác định rõ transaction/batch boundary và cách resume khi lỗi.

Streaming làm giảm nhu cầu giữ toàn bộ tài liệu trong RAM; nó không loại bỏ chi phí parse, buffer, object hiện tại hoặc dữ liệu mà ứng dụng chủ động tích lũy.

## 18. Cẩn thận với dấu phân cách và pretty printing

Một sequence cần dấu phân cách nhất quán. Với NDJSON, newline là dấu phân cách record. Với sequence tổng quát, có thể dùng whitespace theo giao thức. Với array, dấu phẩy do JSON generator quản lý bên trong array.

Không tự nối dấu phẩy giữa nhiều root value:

```text
{"id":1},{"id":2}
```

Nếu muốn array, dùng `writeStartArray()` và `writeEndArray()` hoặc `writeValuesAsArray()`. Nếu muốn NDJSON, dùng root separator là newline hoặc ghi từng dòng compact. Không dùng pretty printer cho record NDJSON vì line break nội bộ phá framing theo dòng.

Khi dùng `ObjectWriter.withRootValueSeparator("\n")`, separator được đặt giữa các root value. Hãy kiểm tra yêu cầu về newline cuối file: một số consumer yêu cầu mỗi record kết thúc bằng newline, kể cả record cuối; nếu writer chỉ ghi separator giữa các record, ứng dụng có thể cần chủ động thêm line feed cuối theo hợp đồng.

## 19. Ví dụ tổng hợp: đọc sequence và xuất thành một JSON array

Giả sử nguồn gửi NDJSON compact:

```text
{"id":1,"name":"An"}
{"id":2,"name":"Binh"}
{"id":3,"name":"Chi"}
```

Ứng dụng muốn chuyển thành một JSON array duy nhất để lưu file:

```java
import com.fasterxml.jackson.databind.MappingIterator;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.SequenceWriter;

import java.io.InputStream;
import java.io.OutputStream;

public void convertSequenceToArray(InputStream input, OutputStream output)
        throws IOException {
    ObjectMapper mapper = new ObjectMapper();
    ObjectReader reader = mapper.readerFor(Event.class);
    ObjectWriter writer = mapper.writerFor(Event.class);

    try (MappingIterator<Event> events = reader.readValues(input);
         SequenceWriter array = writer.writeValuesAsArray(output)) {
        while (events.hasNextValue()) {
            Event event = events.nextValue();
            array.write(event);
        }
    }
}
```

Ví dụ này dùng parser sequence để đọc từng `Event` và `SequenceWriter` để ghi từng event vào một array. Trong code production, cần xác định quyền sở hữu input/output stream và cấu hình auto-close tương ứng; ví dụ trên giả định các đối tượng reader/writer được phép đóng tài nguyên được truyền vào. Nếu framework quản lý stream, hãy tắt auto-close target hoặc dùng wrapper phù hợp.

Nếu nguồn là NDJSON và cần tiếp tục sau một dòng lỗi, nên đọc từng dòng, deserialize từng record và chỉ ghi các record hợp lệ theo chính sách nghiệp vụ. `MappingIterator` tiện cho sequence hợp lệ, nhưng không cung cấp ranh giới dòng để cách ly lỗi theo line number.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `readValue()` chỉ xử lý một object đầu tiên | API được gọi để đọc một JSON value, trong khi input là sequence | Dùng `readValues()` và `MappingIterator` |
| Parser báo lỗi khi gặp dấu phẩy giữa hai root object | Đang gửi `object,object` mà không có array wrapper | Dùng JSON array hoặc sequence có separator hợp lệ |
| `List<Event>` chứa `LinkedHashMap` | Dùng raw `List.class` | Dùng `TypeReference<List<Event>>` hoặc `JavaType` |
| NDJSON lỗi khi đọc từng dòng | Record đã được pretty print thành nhiều dòng | Ghi mỗi record compact trên một dòng |
| Không biết record nào bị lỗi | Dùng sequence parser nhưng cần chẩn đoán theo line | Đọc NDJSON theo dòng và ghi line number |
| File array bị lỗi ở cuối | Quá trình ghi dừng trước `]` hoặc file bị cắt | Ghi file tạm, hoàn tất rồi thay thế file đích |
| Memory tăng dù dùng `MappingIterator` | Consumer hoặc batch phía sau tích lũy record | Giới hạn batch và xử lý record tuần tự |
| Stream bị đóng sớm | `SequenceWriter`/generator đóng target theo cấu hình | Xác định quyền sở hữu và cấu hình `AUTO_CLOSE_TARGET` |
| Consumer không nhận record cuối | Thiếu newline cuối hoặc chưa flush/close output | Hoàn tất writer và tuân thủ quy ước newline của giao thức |

## 21. Checklist thiết kế giao thức nhiều record

Trước khi chọn array hoặc sequence, hãy trả lời:

1. Consumer mong đợi một JSON document hay nhiều JSON text độc lập?
2. Nếu nhiều record, ranh giới được xác định bằng dấu phẩy trong array, newline, whitespace hay Record Separator?
3. Record có được phép pretty print nhiều dòng không?
4. Dữ liệu có cần đọc tuần tự và xử lý từng record để giới hạn bộ nhớ không?
5. Khi một record lỗi, dừng toàn bộ hay cách ly và tiếp tục?
6. Có cần xác định record cuối bị truncate hoặc thiếu newline không?
7. Ai sở hữu và đóng stream ở hai đầu?
8. Có giới hạn kích thước record, độ sâu và số lượng record không?
9. Hệ thống downstream có hỗ trợ định dạng đã chọn không?

## 22. Kết luận

Một JSON array là một document duy nhất có root array; chuỗi nhiều root value là nhiều JSON text độc lập được đặt trong cùng luồng theo một quy ước phân cách. NDJSON là dạng sequence phổ biến trong đó mỗi JSON text nằm trên một dòng. Với Jackson, dùng `readValue()` và `TypeReference<List<T>>` cho danh sách vừa phải, `MappingIterator`/`ObjectReader.readValues()` để đọc tuần tự, `SequenceWriter.writeValuesAsArray()` để ghi một array và `writeValues()` với root separator newline để ghi sequence/NDJSON. Hãy chọn framing theo hợp đồng của consumer, kiểm soát bộ nhớ và xác định chính sách lỗi ở cấp record.
