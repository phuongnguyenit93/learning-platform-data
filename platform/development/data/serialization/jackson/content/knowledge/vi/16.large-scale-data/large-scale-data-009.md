# Dừng sớm, hủy xử lý và đóng tài nguyên đang sử dụng

Khi xử lý JSON lớn bằng Jackson streaming API, ứng dụng không phải lúc nào cũng cần đọc hết tài liệu. Có thể dừng ngay khi tìm thấy bản ghi cần thiết, bỏ qua một nhánh không liên quan, hủy công việc khi người dùng yêu cầu hoặc kết thúc khi nguồn dữ liệu gặp lỗi.

Dừng sớm giúp tiết kiệm CPU và I/O, nhưng phải quản lý đúng vòng đời của parser, generator và stream bên dưới. Một thao tác `break` chỉ thoát vòng lặp; nó không tự giải phóng tài nguyên. Ngược lại, đóng parser quá sớm có thể khiến dữ liệu còn lại chưa được đọc hoặc chưa được xác thực. Khi đang ghi JSON, hủy giữa chừng còn có thể để lại một tài liệu đầu ra chưa hoàn chỉnh.

Bài học này tập trung vào ba việc: dừng việc đọc đúng thời điểm, truyền tín hiệu hủy an toàn và đóng mọi tài nguyên mà tác vụ đang sở hữu.

## 1. Dừng sớm khác với đọc hết tài liệu

Giả sử nguồn JSON là một array có rất nhiều bản ghi:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"},
  {"id": 3, "name": "Chi"}
]
```

Nếu chỉ cần tìm người dùng có `id = 2`, ứng dụng có thể dừng sau phần tử thứ hai. Không cần đọc phần tử thứ ba và những phần tử còn lại.

Có ba hành động thường gặp:

- **Dừng sớm (early exit):** kết thúc vòng lặp hoặc trả kết quả ngay khi đã có điều cần tìm.
- **Bỏ qua nhánh (skip):** không xử lý một object/array cụ thể nhưng vẫn tiếp tục đọc tài liệu bên ngoài.
- **Hủy (cancellation):** một tín hiệu từ bên ngoài yêu cầu tác vụ đang chạy kết thúc.

Ba hành động này không giống nhau. Dừng sớm thường là quyết định của thuật toán; bỏ qua nhánh vẫn tiếp tục parse; hủy thường xuất phát từ người dùng, timeout hoặc một tác vụ khác.

## 2. Dừng sớm khi đã tìm thấy kết quả

Với array lớn, có thể dùng `JsonParser` để đến từng object rồi nhờ Databind ánh xạ riêng object đó thành DTO.

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.util.Optional;

public Optional<User> findUser(
        ObjectMapper mapper,
        InputStream input,
        long wantedId) throws IOException {

    JsonFactory factory = mapper.getFactory();

    try (JsonParser parser = factory.createParser(input)) {
        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected a JSON array");
        }

        while (parser.nextToken() == JsonToken.START_OBJECT) {
            User user = mapper.readValue(parser, User.class);

            if (user.getId() == wantedId) {
                return Optional.of(user);
            }
        }

        if (parser.currentToken() != JsonToken.END_ARRAY) {
            throw new IOException("Unexpected JSON structure");
        }

        return Optional.empty();
    }
}
```

Khi `mapper.readValue(parser, User.class)` đọc một object, parser được tiêu thụ đến hết object đó. Vòng lặp tiếp tục bằng cách gọi `nextToken()` để đến phần tử tiếp theo.

Nếu tìm thấy người dùng, `return` thoát method. Khối try-with-resources vẫn chạy phần đóng parser trước khi method trả về. Parser được đóng và nguồn bên dưới cũng được đóng theo cấu hình auto-close hiện hành.

Lưu ý: khi trả kết quả sớm, các phần tử còn lại của array chưa được parse. Điều này phù hợp nếu mục tiêu chỉ là tìm một bản ghi. Nếu yêu cầu là xác thực toàn bộ file trước khi chấp nhận kết quả, phải đọc đến hết tài liệu hoặc thực hiện một bước xác thực riêng.

## 3. break không tự đóng parser

Một lỗi thường gặp là cho rằng thoát vòng lặp đồng nghĩa với việc tài nguyên đã được giải phóng.

```java
JsonParser parser = factory.createParser(input);

while (parser.nextToken() != null) {
    if (shouldStop(parser)) {
        break;
    }
}

// Parser vẫn cần được đóng.
```

`break` chỉ thoát vòng lặp. Parser vẫn có thể giữ buffer, file descriptor, kết nối hoặc tham chiếu đến nguồn đầu vào.

Nên dùng try-with-resources:

```java
try (JsonParser parser = factory.createParser(input)) {
    while (parser.nextToken() != null) {
        if (shouldStop(parser)) {
            break;
        }
    }
}
```

Dù vòng lặp kết thúc tự nhiên, dùng `break`, `return` hay phát sinh exception, Java vẫn gọi `close()` khi rời khỏi block.

Nếu không dùng try-with-resources, phải đặt việc đóng parser trong `finally`:

```java
JsonParser parser = factory.createParser(input);

try {
    while (parser.nextToken() != null) {
        if (shouldStop(parser)) {
            break;
        }
    }
} finally {
    parser.close();
}
```

Try-with-resources thường dễ đọc hơn và cũng xử lý đúng trường hợp cả phần đọc lẫn phần đóng đều phát sinh exception.

## 4. Bỏ qua một nhánh nhưng tiếp tục đọc

Nếu không cần một trường lồng nhau, không nhất thiết phải hủy toàn bộ tác vụ. Khi parser đang ở `START_OBJECT` hoặc `START_ARRAY`, dùng `skipChildren()` để bỏ qua nội dung con rồi tiếp tục.

Ví dụ bỏ qua trường `debug` nhưng vẫn đọc `payload`:

```java
while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("debug".equals(fieldName)
            && (valueToken == JsonToken.START_OBJECT
                || valueToken == JsonToken.START_ARRAY)) {
        parser.skipChildren();
        continue;
    }

    if ("payload".equals(fieldName)
            && valueToken == JsonToken.START_OBJECT) {
        Payload payload = mapper.readValue(parser, Payload.class);
        process(payload);
    } else if (valueToken == JsonToken.START_OBJECT
            || valueToken == JsonToken.START_ARRAY) {
        parser.skipChildren();
    }
}
```

`skipChildren()` không đóng parser và không hủy nguồn. Nó chỉ đưa parser qua toàn bộ object/array hiện tại đến token kết thúc tương ứng. Sau đó có thể tiếp tục đọc field tiếp theo.

Nếu cần kiểm tra nội dung nhánh bị bỏ qua để xác thực schema hoặc phát hiện dữ liệu sai, không nên skip nó.

## 5. Hủy tác vụ theo kiểu cooperative cancellation

Trong ứng dụng đa luồng, một luồng có thể đang đọc JSON trong khi luồng khác nhận yêu cầu dừng từ người dùng hoặc từ hệ thống điều phối.

Một cách đơn giản là dùng `AtomicBoolean` làm cờ hủy. Luồng đọc kiểm tra cờ ở những điểm an toàn, thường là giữa các token hoặc giữa các bản ghi.

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

public void processUsers(
        ObjectMapper mapper,
        InputStream input,
        AtomicBoolean cancelled) throws IOException {

    try (JsonParser parser = mapper.getFactory().createParser(input)) {
        if (parser.nextToken() != JsonToken.START_ARRAY) {
            throw new IOException("Expected a JSON array");
        }

        while (parser.nextToken() == JsonToken.START_OBJECT) {
            if (cancelled.get()) {
                throw new CancellationException("JSON processing cancelled");
            }

            User user = mapper.readValue(parser, User.class);
            process(user);

            if (cancelled.get()) {
                throw new CancellationException("JSON processing cancelled");
            }
        }
    }
}
```

Luồng điều khiển bên ngoài có thể yêu cầu dừng:

```java
AtomicBoolean cancelled = new AtomicBoolean(false);

// Tác vụ đọc JSON chạy ở worker thread.
Future<?> task = executor.submit(
    () -> processUsers(mapper, input, cancelled)
);

// Khi người dùng bấm Cancel:
cancelled.set(true);
```

Trong ví dụ thực tế, cần truyền và quản lý đúng `InputStream` cùng vòng đời của nó; không chia sẻ một stream cho nhiều tác vụ đọc đồng thời.

Cách này được gọi là cooperative cancellation vì tác vụ tự kiểm tra tín hiệu hủy. Nó chỉ phản ứng tại những điểm mà code có cơ hội kiểm tra cờ.

### 5.1. CancellationException và dọn dẹp tài nguyên

`CancellationException` là unchecked exception. Khi nó thoát khỏi block try-with-resources, parser vẫn được đóng.

Có thể bắt riêng để phân biệt tác vụ bị hủy với lỗi parse:

```java
try {
    processUsers(mapper, input, cancelled);
} catch (CancellationException ex) {
    // Ghi nhận trạng thái CANCELLED, không xem đây là JSON parse failure.
} catch (JsonProcessingException ex) {
    // Xử lý JSON sai cú pháp hoặc lỗi ánh xạ.
} catch (IOException ex) {
    // Xử lý lỗi I/O.
}
```

Nếu method chỉ cần kết thúc bình thường khi bị hủy, có thể trả về một kết quả trạng thái như `CANCELLED`. Quan trọng là không nuốt mọi exception và báo thành công khi dữ liệu chỉ mới được xử lý một phần.

### 5.2. Kiểm tra cờ trước hay sau nextToken()?

Nếu `nextToken()` trả về nhanh từ buffer, kiểm tra cờ trước hoặc sau mỗi token đều hữu ích. Nếu `nextToken()` đang chờ dữ liệu từ mạng hoặc một stream chậm, code không thể kiểm tra cờ cho đến khi lời gọi đó trả về.

Vì vậy, cooperative cancellation không tự giải quyết được thao tác I/O đang block. Cần có timeout hoặc cơ chế hủy ở tầng nguồn dữ liệu.

## 6. Hủy khi parser đang chờ I/O

Jackson parser đồng bộ đọc dữ liệu từ nguồn. Nếu nguồn là socket, HTTP response body hoặc pipe, một lần đọc có thể block chờ byte tiếp theo.

Trong trường hợp đó:

- Cờ `AtomicBoolean` chỉ được nhìn thấy khi luồng đọc quay lại code ứng dụng.
- `Future.cancel(true)` gửi interrupt cho worker, nhưng không bảo đảm mọi InputStream hoặc thư viện I/O đều dừng đọc.
- Đóng nguồn đầu vào có thể làm thao tác đọc đang block kết thúc, nhưng hành vi cụ thể phụ thuộc implementation của stream/client.
- Với socket hoặc HTTP client, nên dùng API hủy request/response của chính client hoặc đóng resource sở hữu kết nối.
- Thiết lập read timeout để tác vụ không chờ vô hạn khi nguồn ngừng gửi dữ liệu.

Ví dụ khái niệm với socket:

```java
try (Socket socket = new Socket(host, port)) {
    socket.setSoTimeout(5_000);

    try (JsonParser parser = factory.createParser(socket.getInputStream())) {
        // Đọc JSON từ socket
    }
}
```

Ở đây `SO_TIMEOUT` giới hạn thời gian chờ cho thao tác đọc socket. Trong code thực tế, cần xác định rõ ai sở hữu socket và ai đóng socket. Nếu socket được chia sẻ hoặc do HTTP client quản lý, không tự ý đóng từ một worker khác mà không theo hợp đồng của client.

Không nên gọi `parser.close()` đồng thời từ nhiều luồng trong khi một luồng khác vẫn đang sử dụng parser. Parser không phải đối tượng để nhiều thread thao tác đồng thời. Hãy gửi tín hiệu hủy cho chủ sở hữu nguồn I/O hoặc dùng cơ chế cancellation được client hỗ trợ, rồi để worker đang đọc đóng parser trong `finally`/try-with-resources.

## 7. Hủy bằng interrupt và Future.cancel()

Executor có thể gửi interrupt cho worker:

```java
Future<?> future = executor.submit(() -> readLargeJson(input));

future.cancel(true);
```

Tham số `true` yêu cầu interrupt nếu task đang chạy. Tuy nhiên, interrupt chỉ là tín hiệu. Jackson streaming parser không bảo đảm tự động dừng ở mọi điểm chỉ vì thread bị interrupt.

Nếu xử lý theo lô, có thể kiểm tra trạng thái interrupt giữa các bản ghi:

```java
while (parser.nextToken() == JsonToken.START_OBJECT) {
    if (Thread.currentThread().isInterrupted()) {
        throw new CancellationException("Worker interrupted");
    }

    User user = mapper.readValue(parser, User.class);
    process(user);
}
```

Dùng `isInterrupted()` để kiểm tra mà không xóa trạng thái interrupt. Nếu code bắt `InterruptedException`, cần khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` trước khi kết thúc hoặc truyền tín hiệu lên tầng gọi.

Không dùng `Thread.stop()` để hủy parsing. Dừng thread đột ngột có thể để lại lock, trạng thái object và tài nguyên ở trạng thái không nhất quán.

## 8. Đóng parser và quyền sở hữu InputStream

Khi gọi `parser.close()`, Jackson giải phóng tài nguyên nội bộ của parser. Việc có đóng nguồn đầu vào bên dưới hay không phụ thuộc cấu hình `AUTO_CLOSE_SOURCE`.

Trong Jackson 2.x, `StreamReadFeature.AUTO_CLOSE_SOURCE` được bật mặc định trong cấu hình thông thường. Vì vậy, đóng parser thường cũng đóng InputStream/Reader mà parser đang dùng.

Nếu ứng dụng cần tiếp tục sử dụng stream sau khi parser kết thúc, có thể tắt auto-close trên factory:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;

JsonFactory factory = JsonFactory.builder()
    .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
    .build();
```

Khi tắt auto-close, parser vẫn cần được đóng để giải phóng buffer và tài nguyên nội bộ; nhưng ứng dụng phải tự đóng InputStream/Reader theo đúng quyền sở hữu.

Một quy tắc dễ áp dụng:

| Ai mở nguồn? | Ai nên chịu trách nhiệm đóng? |
|---|---|
| Method hiện tại tự mở file/stream | Method đó đóng bằng try-with-resources |
| Caller truyền stream và vẫn cần dùng sau khi parse | Caller giữ quyền sở hữu; cấu hình parser không tự đóng nguồn |
| HTTP client tạo response body | Đóng response/body theo API của HTTP client |
| Socket được worker tạo và sở hữu | Worker đóng socket/stream khi kết thúc |
| Stream được chia sẻ theo một abstraction riêng | Tuân theo hợp đồng ownership của abstraction đó |

Không nên dựa vào việc đóng parser để đóng mọi tài nguyên bên ngoài nếu ownership chưa rõ ràng.

## 9. Đóng generator và target OutputStream

Generator cũng có quy tắc tương tự. `JsonGenerator.close()` giải phóng tài nguyên ghi; việc đóng OutputStream/Writer bên dưới phụ thuộc `AUTO_CLOSE_TARGET`.

Trong Jackson 2.x, `StreamWriteFeature.AUTO_CLOSE_TARGET` thường được bật mặc định. Có thể tắt nếu ứng dụng muốn giữ OutputStream mở sau khi generator đóng:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamWriteFeature;

JsonFactory factory = JsonFactory.builder()
    .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
    .build();
```

Dù tắt auto-close target, vẫn phải đóng generator để giải phóng buffer và hoàn tất xử lý nội bộ. Sau đó, chủ sở hữu OutputStream chịu trách nhiệm đóng stream.

Nếu cần cả parser lẫn generator không đóng nguồn/đích, cấu hình cả hai feature trên cùng factory:

```java
JsonFactory factory = JsonFactory.builder()
    .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
    .disable(StreamWriteFeature.AUTO_CLOSE_TARGET)
    .build();
```

Hãy cấu hình factory trước khi tạo parser/generator và không thay đổi ownership policy tùy tiện giữa các tác vụ.

## 10. Đóng generator giữa chừng có thể tạo ra JSON chưa hoàn chỉnh về nghiệp vụ

Một generator có thể đang ghi dở một object hoặc array khi tác vụ bị hủy.

Jackson có feature `AUTO_CLOSE_JSON_CONTENT`, thường được bật mặc định. Khi đóng generator, Jackson cố gắng đóng các object/array còn mở để đầu ra có cấu trúc JSON hoàn chỉnh về cú pháp.

Ví dụ ứng dụng đã ghi:

```json
{
  "users": [
    {"id": 1},
    {"id": 2}
```

Nếu generator được đóng khi array và object vẫn mở, feature auto-close có thể ghi thêm các dấu đóng. Kết quả có thể là JSON parse được, nhưng danh sách chỉ chứa một phần dữ liệu.

Điều này tạo ra rủi ro: consumer có thể hiểu một tài liệu bị hủy giữa chừng là tài liệu hoàn chỉnh. Không nên xem việc generator tự đóng container là bằng chứng rằng tác vụ đã thành công.

Nếu cần hủy và bỏ đầu ra dở dang:

- Ghi vào file tạm hoặc buffer riêng.
- Chỉ publish/rename file khi toàn bộ tài liệu đã ghi thành công.
- Nếu tác vụ bị hủy hoặc lỗi, xóa file tạm.
- Với HTTP response đã gửi byte ra client, không thể thu hồi byte đã gửi; hãy dùng giao thức có framing hoặc trạng thái hoàn tất rõ ràng nếu cần.

Có thể tắt `AUTO_CLOSE_JSON_CONTENT` để generator không tự đóng container, nhưng điều đó không thay thế chiến lược commit/rollback đầu ra. Một tài liệu chưa hoàn tất vẫn phải được coi là thất bại.

## 11. Ghi file theo kiểu atomic để tránh lộ output một phần

Với file JSON lớn, có thể ghi vào file tạm cùng thư mục, đóng generator thành công rồi mới chuyển file tạm thành file đích.

```java
Path target = Path.of("users.json");
Path temp = target.resolveSibling("users.json.tmp");

boolean completed = false;

try {
    try (OutputStream output = Files.newOutputStream(temp);
         JsonGenerator generator = factory.createGenerator(output)) {

        generator.writeStartArray();

        for (User user : users) {
            if (cancelled.get()) {
                throw new CancellationException("Export cancelled");
            }

            mapper.writeValue(generator, user);
        }

        generator.writeEndArray();
    }

    Files.move(
        temp,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.ATOMIC_MOVE
    );

    completed = true;
} finally {
    if (!completed) {
        Files.deleteIfExists(temp);
    }
}
```

Ví dụ này thể hiện ý tưởng commit sau khi ghi hoàn tất:

1. Mọi dữ liệu được ghi vào file tạm.
2. Nếu bị hủy hoặc phát sinh lỗi, file tạm bị xóa.
3. Chỉ khi generator đóng thành công, file tạm mới được chuyển thành file đích.

`ATOMIC_MOVE` phụ thuộc filesystem; nếu không hỗ trợ, thao tác move có thể thất bại. Ứng dụng cần quyết định có fallback sang move thông thường hay báo lỗi. Đặt file tạm cùng filesystem với file đích giúp tăng khả năng atomic move.

Nếu dữ liệu được ghi vào một stream từ xa hoặc HTTP response, không có thao tác rename để rollback. Khi đó nên thiết kế giao thức có marker hoàn tất, checksum, length hoặc commit riêng.

## 12. Dừng sớm khi dùng MappingIterator

Khi đọc một sequence các object cùng kiểu, Jackson Databind cung cấp `MappingIterator`. Iterator này cho phép xử lý từng object và dừng khi đã đủ kết quả.

```java
import com.fasterxml.jackson.databind.MappingIterator;

try (MappingIterator<User> users =
         mapper.readerFor(User.class).readValues(inputStream)) {

    while (users.hasNextValue()) {
        User user = users.nextValue();

        if (matches(user)) {
            processMatch(user);
            break;
        }
    }
}
```

Khi rời khỏi try block, `MappingIterator` được đóng. Nếu iterator sở hữu parser/nguồn được tạo từ InputStream, thao tác close sẽ đóng parser và nguồn theo ownership policy của Jackson.

Nếu iterator được tạo từ một parser do caller truyền vào, cần đọc tài liệu API và xác định rõ ai sở hữu parser; trong trường hợp cần kiểm soát chắc chắn, quản lý parser bằng try-with-resources ở tầng caller.

`MappingIterator` phù hợp với chuỗi các giá trị cùng kiểu. Với JSON array lồng trong một envelope phức tạp, hoặc khi cần bỏ qua và xử lý các field khác, dùng parser trực tiếp sẽ cho quyền kiểm soát rõ hơn.

## 13. Phân biệt dừng sớm, hủy và lỗi

Ứng dụng nên phân biệt ba kết quả:

| Kết quả | Ý nghĩa | Xử lý thường gặp |
|---|---|---|
| COMPLETED | Đã đọc/xử lý hết dữ liệu theo yêu cầu | Commit kết quả |
| STOPPED_EARLY | Đã có đủ kết quả nên chủ động dừng | Đóng parser; ghi rõ chưa đọc hết nếu điều đó quan trọng |
| CANCELLED | Có tín hiệu hủy từ bên ngoài | Đóng tài nguyên; không publish kết quả dở dang |
| FAILED | Parse, mapping hoặc I/O thất bại | Đóng tài nguyên; báo lỗi và giữ nguyên nguyên nhân |

Không nên gộp `STOPPED_EARLY` và `CANCELLED` nếu tầng gọi cần biết tại sao công việc kết thúc. Ví dụ, tìm thấy bản ghi là kết quả hợp lệ; người dùng bấm Cancel có thể là một tác vụ chưa hoàn thành.

Nếu hệ thống cần xác thực toàn bộ JSON, chỉ trạng thái `COMPLETED` sau khi đọc hết và kiểm tra phần kết thúc mới chứng minh toàn bộ tài liệu đã được parse.

## 14. Các lỗi thường gặp

**Dùng break nhưng không đóng parser.** Thoát vòng lặp không giải phóng buffer, stream hoặc kết nối. Dùng try-with-resources.

**Cho rằng Future.cancel(true) luôn dừng được I/O.** Interrupt không bảo đảm mọi stream đều phản ứng. Dùng timeout và API cancellation của HTTP client/socket.

**Đóng parser từ thread khác trong khi parser đang được sử dụng.** Parser không được thiết kế để nhiều thread thao tác đồng thời. Hãy gửi tín hiệu hủy và để worker sở hữu parser dọn dẹp, hoặc hủy nguồn I/O theo API của nó.

**Gọi skipChildren() khi muốn hủy cả tác vụ.** skipChildren chỉ bỏ qua một nhánh và tiếp tục parse.

**Đóng generator rồi xem output là hoàn chỉnh.** Generator có thể tự đóng container nhưng dữ liệu nghiệp vụ vẫn thiếu. Chỉ commit output khi tác vụ hoàn tất.

**Tắt AUTO_CLOSE_SOURCE nhưng quên đóng stream.** Parser không còn đóng nguồn thay ứng dụng; chủ sở hữu phải đóng InputStream/Reader.

**Tắt AUTO_CLOSE_TARGET nhưng quên đóng output.** Generator giải phóng buffer nhưng stream đích vẫn thuộc trách nhiệm của ứng dụng.

**Nuốt CancellationException hoặc IOException.** Tầng gọi có thể hiểu nhầm tác vụ bị hủy hoặc thất bại thành thành công. Hãy biểu diễn trạng thái kết thúc rõ ràng.

**Dùng một parser cho nhiều thread.** Parser là stateful và không thread-safe. Mỗi tác vụ đọc nên sở hữu parser riêng.

## 15. Checklist vận hành cho tác vụ streaming

Trước khi đưa một pipeline đọc/ghi JSON lớn vào production, cần xác định:

- Ai tạo và sở hữu InputStream/Reader?
- Ai tạo và sở hữu OutputStream/Writer?
- Parser và generator có được đóng bằng try-with-resources không?
- Khi dừng sớm, phần dữ liệu chưa đọc có cần được xác thực không?
- Tác vụ có thể bị block trong I/O không, và timeout được đặt ở đâu?
- Cancellation có được kiểm tra giữa các bản ghi/token không?
- HTTP client hoặc socket có API hủy riêng không?
- Nếu bị hủy giữa lúc ghi, output một phần được loại bỏ hay đánh dấu thế nào?
- Tác vụ kết thúc với trạng thái COMPLETED, STOPPED_EARLY, CANCELLED hay FAILED?
- Có giới hạn kích thước, độ sâu JSON và thời gian xử lý phù hợp không?

## 16. Ghi nhớ

- `break` và `return` dừng luồng điều khiển nhưng chỉ try-with-resources hoặc finally mới bảo đảm đóng parser.
- `skipChildren()` bỏ qua một object/array và tiếp tục đọc; nó không hủy toàn bộ tác vụ.
- Dùng cờ cancellation hoặc interrupt để yêu cầu dừng hợp tác; kiểm tra giữa các token hoặc bản ghi.
- Nếu `nextToken()` đang block, cờ hủy không được kiểm tra cho đến khi I/O trả về; cần timeout hoặc API hủy nguồn.
- Không thao tác đồng thời trên cùng parser từ nhiều thread.
- `AUTO_CLOSE_SOURCE` và `AUTO_CLOSE_TARGET` quyết định parser/generator có đóng nguồn/đích bên dưới hay không.
- Đóng generator có thể tự đóng container theo `AUTO_CLOSE_JSON_CONTENT`; JSON có thể hợp lệ về cú pháp nhưng chỉ chứa dữ liệu một phần.
- Ghi output vào file tạm và chỉ commit sau khi hoàn tất; xóa file tạm khi hủy hoặc lỗi.
- Phân biệt dừng sớm hợp lệ, hủy từ bên ngoài và lỗi parse/I/O để tầng gọi không hiểu nhầm trạng thái.

