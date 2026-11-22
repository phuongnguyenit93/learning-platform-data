# Đọc nhiều giá trị với ObjectReader và MappingIterator

Khi một nguồn JSON chứa rất nhiều bản ghi, đọc toàn bộ dữ liệu thành `List<T>` có thể làm bộ nhớ tăng theo số lượng phần tử. Jackson cung cấp `ObjectReader` và `MappingIterator<T>` để đọc từng giá trị một. Cách này đặc biệt hữu ích khi file có một JSON array lớn hoặc chứa nhiều JSON value nối tiếp nhau.

`ObjectReader` giữ kiểu đích và cấu hình deserialize đã chọn. `MappingIterator` điều khiển việc đọc tuần tự: mỗi lần lấy phần tử tiếp theo, Jackson deserialize một giá trị thành object Java. Ứng dụng có thể xử lý xong phần tử hiện tại rồi chuyển sang phần tử kế tiếp, nhờ đó không cần giữ toàn bộ collection trong bộ nhớ.

Điểm quan trọng là `MappingIterator` chỉ giúp đọc tăng dần; nó không tự bảo đảm bộ nhớ thấp nếu ứng dụng vẫn gom tất cả object vào một list hoặc giữ mọi phần tử trong cache. Lợi ích xuất hiện khi mỗi giá trị được xử lý và giải phóng tham chiếu trước khi đọc tiếp.

## 1. Vì sao cần ObjectReader và MappingIterator?

Giả sử file `users.json` chứa một array có hàng triệu user:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"},
  {"id": 3, "name": "Chi"}
]
```

Nếu đọc toàn bộ array thành list:

```java
List<User> users = mapper.readValue(
    input,
    new TypeReference<List<User>>() {}
);

for (User user : users) {
    process(user);
}
```

Jackson phải tạo toàn bộ `List<User>` và các object `User` trước khi code xử lý vòng lặp. Bộ nhớ cần thiết tăng theo tổng số bản ghi và kích thước object.

Với `MappingIterator`, có thể đọc từng user:

```java
ObjectReader reader = mapper.readerFor(User.class);

try (MappingIterator<User> users = reader.readValues(input)) {
    while (users.hasNextValue()) {
        User user = users.nextValue();
        process(user);
    }
}
```

Iterator lấy từng object từ nguồn. Nếu `process(user)` hoàn tất và ứng dụng không giữ lại tham chiếu đến user, object đó có thể được garbage collector thu hồi khi không còn được sử dụng.

## 2. Vai trò của ObjectReader

`ObjectReader` là đối tượng đọc có cấu hình bất biến được tạo từ `ObjectMapper`. Nó có thể giữ:

- Kiểu Java đích, chẳng hạn `User.class` hoặc một `JavaType` generic.
- Các `DeserializationFeature` riêng cho luồng đọc.
- Injectable values, view hoặc schema khi ứng dụng cần.
- Các tùy chọn đọc khác được kế thừa từ mapper.

Ví dụ tạo reader cho `User`:

```java
ObjectReader userReader = mapper.readerFor(User.class);
```

Sau đó có thể tái sử dụng reader cho nhiều nguồn dữ liệu cùng kiểu:

```java
try (MappingIterator<User> first = userReader.readValues(firstInput)) {
    while (first.hasNextValue()) {
        process(first.nextValue());
    }
}

try (MappingIterator<User> second = userReader.readValues(secondInput)) {
    while (second.hasNextValue()) {
        process(second.nextValue());
    }
}
```

Reader bất biến, vì vậy các phương thức cấu hình như `with()` hoặc `without()` trả về reader mới thay vì sửa reader hiện có. Có thể tạo reader một lần ở giai đoạn khởi tạo service rồi dùng lại:

```java
public class UserImportService {
    private final ObjectReader userReader;

    public UserImportService(ObjectMapper mapper) {
        this.userReader = mapper.readerFor(User.class);
    }

    public void importFrom(InputStream input) throws IOException {
        try (MappingIterator<User> users = userReader.readValues(input)) {
            while (users.hasNextValue()) {
                process(users.nextValue());
            }
        }
    }

    private void process(User user) {
        // Lưu hoặc xử lý một user
    }
}
```

Không cần tạo `ObjectMapper` mới cho mỗi file. Dùng mapper đã được cấu hình trong ứng dụng để giữ module, naming strategy và serializer/deserializer chung.

## 3. Đọc một JSON array lớn bằng MappingIterator

Trường hợp phổ biến nhất là một array ở root, trong đó mỗi phần tử là một object cùng kiểu.

### 3.1. Đọc từ InputStream

```java
ObjectReader userReader = mapper.readerFor(User.class);

try (InputStream input = Files.newInputStream(Path.of("users.json"));
     MappingIterator<User> users = userReader.readValues(input)) {

    while (users.hasNextValue()) {
        User user = users.nextValue();
        process(user);
    }
}
```

`readValues(input)` tạo parser từ nguồn byte và trả về iterator. Với overload nhận stream do reader tạo, iterator quản lý parser mà nó đã tạo; đóng iterator là bước quan trọng để giải phóng parser và nguồn liên quan. Ví dụ vẫn đặt cả stream trong `try-with-resources` để vòng đời nguồn được thể hiện rõ ràng.

Jackson đọc từng object trong array. Mỗi lần gọi `nextValue()`, iterator chuyển phần tử hiện tại thành `User`.

### 3.2. Đọc từ Reader

Nếu dữ liệu đã có dưới dạng ký tự hoặc ứng dụng cần chỉ định charset trước khi parse, có thể dùng `Reader`:

```java
ObjectReader userReader = mapper.readerFor(User.class);

try (Reader source = Files.newBufferedReader(
        Path.of("users.json"), StandardCharsets.UTF_8);
     MappingIterator<User> users = userReader.readValues(source)) {

    while (users.hasNextValue()) {
        process(users.nextValue());
    }
}
```

Ở đây `Files.newBufferedReader()` giải mã byte thành ký tự bằng UTF-8. `ObjectReader` nhận `Reader` và đọc JSON từ các ký tự đó.

### 3.3. Đọc từ file hoặc chuỗi

`ObjectReader` cũng có các overload đọc từ những nguồn khác được Jackson hỗ trợ, chẳng hạn file hoặc chuỗi JSON. Ví dụ với file:

```java
try (MappingIterator<User> users = userReader.readValues(
        Path.of("users.json").toFile())) {
    while (users.hasNextValue()) {
        process(users.nextValue());
    }
}
```

Với dữ liệu đã nằm trong `String`:

```java
String json = "[{\"id\":1,\"name\":\"An\"},{\"id\":2,\"name\":\"Binh\"}]";

try (MappingIterator<User> users = userReader.readValues(json)) {
    while (users.hasNextValue()) {
        process(users.nextValue());
    }
}
```

Lưu ý: dùng `String` chỉ thuận tiện khi dữ liệu đã ở trong bộ nhớ. Nếu mục tiêu là xử lý file lớn, hãy dùng `InputStream` hoặc `Reader` thay vì nạp toàn bộ nội dung vào chuỗi trước.

## 4. MappingIterator đọc được những dạng JSON nào?

`readValues()` được thiết kế để đọc một chuỗi các giá trị cùng kiểu. Nguồn có thể biểu diễn chuỗi đó bằng một JSON array hoặc bằng các root-level JSON value nối tiếp nhau.

### 4.1. Một array chứa nhiều object

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Với `readerFor(User.class).readValues(...)`, mỗi phần tử của array được ánh xạ thành một `User`.

### 4.2. Nhiều root-level value nối tiếp

Jackson cũng có thể đọc nhiều JSON value ở root trong cùng một nguồn:

```json
{"id": 1, "name": "An"}
{"id": 2, "name": "Binh"}
{"id": 3, "name": "Chi"}
```

Đây là một chuỗi các JSON document, mỗi document là một object. Với reader cho `User`, iterator trả về từng user.

JSON chuẩn thường được trao đổi dưới dạng một root value. Việc nối nhiều root value trong một nguồn là khả năng xử lý sequence của Jackson, nhưng không phải mọi hệ thống JSON đều chấp nhận định dạng đó. Nếu dùng định dạng này giữa các hệ thống, cần thống nhất framing và cách phát hiện ranh giới bản ghi.

### 4.3. JSON Lines (NDJSON)

Một định dạng thường gặp cho log hoặc import là JSON Lines: mỗi dòng chứa một JSON value hoàn chỉnh:

```text
{"id":1,"name":"An"}
{"id":2,"name":"Binh"}
{"id":3,"name":"Chi"}
```

`MappingIterator` có thể đọc chuỗi root-level value như trên vì xuống dòng là whitespace giữa các JSON value. Tuy nhiên, iterator không áp đặt ranh giới theo dòng và cũng không cung cấp cơ chế cô lập lỗi theo từng dòng.

Nếu hợp đồng yêu cầu xử lý từng dòng độc lập, chẳng hạn ghi nhận số dòng lỗi rồi tiếp tục với dòng sau, dùng `BufferedReader.readLine()` và deserialize từng dòng:

```java
ObjectReader userReader = mapper.readerFor(User.class);

try (BufferedReader lines = Files.newBufferedReader(
        Path.of("users.ndjson"), StandardCharsets.UTF_8)) {

    String line;
    long lineNumber = 0;

    while ((line = lines.readLine()) != null) {
        lineNumber++;
        if (line.isBlank()) {
            continue;
        }

        try {
            User user = userReader.readValue(line);
            process(user);
        } catch (JsonProcessingException e) {
            recordInvalidLine(lineNumber, line, e);
        }
    }
}
```

Cách đọc từng dòng tạo một chuỗi nhỏ cho mỗi bản ghi nhưng cho phép báo lỗi và tiếp tục ở ranh giới dòng. Nếu cần parse một JSON sequence liên tục và dừng khi có lỗi cú pháp, `MappingIterator` phù hợp hơn.

## 5. Phân biệt đọc sequence với đọc một collection duy nhất

Đây là điểm quan trọng khi chọn kiểu đích.

Nếu JSON root là một array chứa nhiều `User`, hãy dùng reader cho `User` với `readValues()`:

```java
MappingIterator<User> users = mapper
    .readerFor(User.class)
    .readValues(input);
```

Mỗi phần tử array là một giá trị `User` độc lập.

Nếu muốn đọc toàn bộ JSON array thành một object `List<User>`, dùng `readValue()` với kiểu collection:

```java
List<User> users = mapper.readValue(
    input,
    new TypeReference<List<User>>() {}
);
```

Không dùng `readerFor(new TypeReference<List<User>>() {}).readValues(input)` để thay thế ví dụ đầu tiên. Trong trường hợp `readValues()` nhận root array, iterator xem các phần tử trong array là các giá trị sequence. Kiểu đích `List<User>` khi đó có nghĩa mỗi phần tử của sequence phải là một list, không phải cả array root là một list duy nhất.

| Mục tiêu | API và kiểu đích |
|---|---|
| Đọc từng phần tử `User` trong root array | `readerFor(User.class).readValues(input)` |
| Đọc một root array thành `List<User>` | `readValue(input, new TypeReference<List<User>>() {})` |
| Đọc nhiều root object nối tiếp | `readerFor(User.class).readValues(input)` |
| Đọc từng dòng NDJSON và cô lập lỗi theo dòng | `readLine()` rồi `readerFor(User.class).readValue(line)` |

## 6. Đọc generic type với ObjectReader

`ObjectReader` có thể được tạo từ `JavaType` hoặc `TypeReference` khi mỗi giá trị trong sequence là một kiểu generic.

### 6.1. Đọc từng phần tử có kiểu generic

Giả sử mỗi root value là một response:

```json
{"status":"ok","data":{"id":1,"name":"An"}}
{"status":"ok","data":{"id":2,"name":"Binh"}}
```

Có thể tạo reader cho `ApiResponse<User>`:

```java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, User.class);

ObjectReader responseReader = mapper.readerFor(responseType);

try (MappingIterator<ApiResponse<User>> responses = responseReader.readValues(input)) {
    while (responses.hasNextValue()) {
        ApiResponse<User> response = responses.nextValue();
        process(response.getData());
    }
}
```

### 6.2. Dùng TypeReference

Có thể khai báo kiểu generic trực tiếp:

```java
ObjectReader groupReader = mapper.readerFor(
    new TypeReference<Map<String, List<User>>>() {}
);

try (MappingIterator<Map<String, List<User>>> groups = groupReader.readValues(input)) {
    while (groups.hasNextValue()) {
        Map<String, List<User>> group = groups.nextValue();
        processGroup(group);
    }
}
```

Ở đây mỗi giá trị trong sequence là một map có value là list user. Nếu JSON root là một array của những map như vậy, iterator trả về từng map.

### 6.3. Khi nào cần JavaType?

Nếu kiểu phần tử được quyết định lúc chạy, hãy xây dựng `JavaType` bằng `TypeFactory`, sau đó tạo reader:

```java
JavaType itemType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, payloadClass);

ObjectReader reader = mapper.readerFor(itemType);
```

Reader giữ kiểu đã phân giải và có thể được tái sử dụng cho các nguồn cùng cấu trúc. Hãy dùng `TypeFactory` của mapper đang thực hiện deserialize để giữ cùng ngữ cảnh cấu hình.

## 7. Cách dùng MappingIterator

`MappingIterator<T>` triển khai `Iterator<T>` và `Closeable`. Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `hasNextValue()` | Kiểm tra còn JSON value nào có thể đọc; có thể ném `IOException`. |
| `nextValue()` | Deserialize và trả về value tiếp theo. |
| `hasNext()` | Phiên bản theo giao diện `Iterator`; không thể khai báo thêm checked exception. |
| `next()` | Lấy phần tử theo giao diện `Iterator`. |
| `readAll()` | Đọc hết các value còn lại và trả về `List<T>`. |
| `readAll(Collection<T>)` | Đọc hết và thêm vào collection được truyền vào. |
| `close()` | Đóng iterator và parser nếu iterator sở hữu parser. |
| `getParser()` | Truy cập parser liên quan khi cần thông tin vị trí hoặc trạng thái. |

Trong code xử lý I/O, `hasNextValue()` và `nextValue()` thường rõ ràng hơn vì chúng cho phép `IOException` được truyền ra ngoài:

```java
while (iterator.hasNextValue()) {
    User user = iterator.nextValue();
    process(user);
}
```

Nếu dùng `hasNext()`/`next()`, lỗi I/O có thể được bọc trong `RuntimeException` theo hợp đồng của `Iterator`. Với import lớn, cách dùng API có checked exception thường giúp ranh giới xử lý lỗi rõ hơn.

## 8. Quản lý bộ nhớ khi đọc dữ liệu lớn

`MappingIterator` không tạo sẵn một `List` chứa mọi object. Nó đọc một value, trả object cho caller rồi tiếp tục khi caller yêu cầu. Mức sử dụng bộ nhớ thường phụ thuộc vào:

- Kích thước của một object hiện tại.
- Buffer nội bộ của parser và stream.
- Bộ nhớ mà logic xử lý từng record sử dụng.
- Những object mà ứng dụng giữ lại sau khi xử lý.

Nếu mỗi record được xử lý độc lập, bộ nhớ có thể gần như ổn định theo kích thước record lớn nhất và các buffer, thay vì tăng tuyến tính theo số lượng record.

### 8.1. Xử lý xong rồi bỏ tham chiếu

```java
try (MappingIterator<User> users = userReader.readValues(input)) {
    while (users.hasNextValue()) {
        User current = users.nextValue();
        repository.save(toEntity(current));
        // Không thêm current vào một collection giữ lâu dài
    }
}
```

Sau khi vòng lặp chuyển sang record kế tiếp, biến `current` có thể được gán lại và object cũ trở thành eligible for garbage collection nếu không còn tham chiếu nào khác.

### 8.2. Tránh readAll() với file lớn

Đoạn sau đọc toàn bộ sequence vào một list:

```java
List<User> allUsers = userReader.readValues(input).readAll();
```

`readAll()` tiện khi số lượng record nhỏ và ứng dụng thật sự cần toàn bộ kết quả trong bộ nhớ. Với file lớn, nó loại bỏ phần lớn lợi ích streaming vì mọi object vẫn được giữ trong list.

Nếu cần xử lý theo lô, hãy tự gom một batch có giới hạn:

```java
List<User> batch = new ArrayList<>(500);

try (MappingIterator<User> users = userReader.readValues(input)) {
    while (users.hasNextValue()) {
        batch.add(users.nextValue());

        if (batch.size() == 500) {
            repository.saveBatch(batch);
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        repository.saveBatch(batch);
    }
}
```

Batch giới hạn số object đang được giữ. Cần lưu ý `saveBatch()` không được giữ tham chiếu tới list sau khi trả về nếu code tiếp tục gọi `clear()`.

### 8.3. Xử lý backpressure

Nếu mỗi record được chuyển tới một hệ thống downstream chậm, không nên đọc và xếp hàng vô hạn. Xử lý tuần tự hoặc dùng queue có giới hạn giúp tốc độ đọc không vượt quá khả năng tiêu thụ quá xa.

`MappingIterator` là API đồng bộ, caller kiểm soát thời điểm gọi `nextValue()`. Đây là lợi thế tự nhiên để tạo backpressure: chỉ yêu cầu record tiếp theo sau khi xử lý record hiện tại hoặc sau khi có chỗ trong batch/queue.

## 9. Quản lý parser và tài nguyên

`MappingIterator` có thể quản lý parser do chính `ObjectReader` tạo ra từ `InputStream`, `Reader`, `File` hoặc nguồn khác. Hãy đóng iterator bằng `try-with-resources`:

```java
try (MappingIterator<User> users = userReader.readValues(input)) {
    while (users.hasNextValue()) {
        process(users.nextValue());
    }
}
```

Khi truyền một `JsonParser` đã được tạo bên ngoài:

```java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
     MappingIterator<User> users = userReader.readValues(parser)) {
    while (users.hasNextValue()) {
        process(users.nextValue());
    }
}
```

Parser do caller tạo vẫn thuộc trách nhiệm quản lý của caller. Đóng iterator và parser trong `try-with-resources` làm rõ vòng đời và bảo đảm parser được đóng ngay cả khi xử lý lỗi. `MappingIterator` phân biệt parser được quản lý nội bộ với parser do caller truyền vào; không nên giả định đóng iterator luôn đồng nghĩa đóng mọi parser bên ngoài.

Nếu nguồn stream thuộc framework hoặc một thành phần khác, hãy hiểu cấu hình `AUTO_CLOSE_SOURCE` của factory và quyền sở hữu stream. Không đóng nguồn trước khi iterator đọc xong.

## 10. Xử lý lỗi khi đọc sequence

Lỗi có thể xảy ra ở nhiều giai đoạn:

- JSON sai cú pháp hoặc bị cắt giữa chừng.
- Một field có kiểu không tương thích với DTO.
- Creator hoặc custom deserializer ném exception.
- Lỗi I/O từ file, network hoặc nguồn dữ liệu.
- Logic xử lý record ném exception sau khi deserialize thành công.

Ví dụ:

```java
try (MappingIterator<User> users = userReader.readValues(input)) {
    long index = 0;

    while (users.hasNextValue()) {
        index++;
        User user = users.nextValue();
        process(user);
    }
} catch (JsonProcessingException e) {
    throw new ImportException("Invalid JSON in user import", e);
} catch (IOException e) {
    throw new ImportException("Could not read user import source", e);
}
```

Đoạn này dừng import khi gặp lỗi. Đây là chính sách phù hợp khi file phải được xem như một đơn vị toàn vẹn.

### 10.1. Lỗi ở record nào?

Có thể dùng bộ đếm record để bổ sung ngữ cảnh:

```java
long index = 0;
try (MappingIterator<User> users = userReader.readValues(input)) {
    while (users.hasNextValue()) {
        index++;
        User user = users.nextValue();
        process(user);
    }
} catch (IOException e) {
    throw new ImportException("Failed near record " + (index + 1), e);
}
```

Số thứ tự này cho biết record đang được yêu cầu đọc khi lỗi xảy ra. Với một JSON array lớn, vị trí byte/character của parser có thể hỗ trợ điều tra sâu hơn; có thể truy cập parser qua `getParser()` và lấy location phù hợp khi cần.

### 10.2. Có nên bỏ qua record lỗi và tiếp tục?

Không phải lỗi deserialize nào cũng có thể phục hồi an toàn. Nếu JSON bị sai cú pháp giữa một array, parser có thể không biết ranh giới value tiếp theo. Cố gắng skip tùy tiện có thể làm dữ liệu sau đó bị đọc sai.

Nếu yêu cầu nghiệp vụ là xử lý độc lập từng record và tiếp tục khi một record lỗi, hãy chọn định dạng có ranh giới rõ như JSON Lines. Đọc từng dòng riêng giúp bắt lỗi ở một dòng rồi chuyển sang dòng kế tiếp mà không phải đoán vị trí parser trong một tài liệu JSON lớn.

## 11. Kết hợp MappingIterator với xử lý nghiệp vụ

Một service import thường cần validate, chuyển đổi và lưu từng record. Nên tách việc đọc JSON khỏi logic xử lý:

```java
public void importUsers(InputStream input) throws IOException {
    try (MappingIterator<User> iterator = userReader.readValues(input)) {
        while (iterator.hasNextValue()) {
            User user = iterator.nextValue();
            validate(user);
            repository.save(toEntity(user));
        }
    }
}
```

Nếu lưu theo batch, hãy giới hạn kích thước batch. Nếu downstream có thể thất bại giữa chừng, xác định rõ tính chất transaction:

- Toàn file là một transaction: lỗi ở record nào cũng rollback toàn bộ nếu database và quy mô cho phép.
- Mỗi batch là một transaction: các batch trước có thể đã commit khi batch sau lỗi.
- Mỗi record là một transaction: dễ cô lập lỗi nhưng có thể tốn overhead lớn.

Jackson chỉ chịu trách nhiệm parse và deserialize. Transaction, retry, idempotency và báo cáo số record thành công/thất bại thuộc logic ứng dụng.

## 12. Khi nào nên dùng MappingIterator thay vì các API khác?

| API | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| `ObjectMapper.readValue(..., List<T>)` | Đọc cả collection vào bộ nhớ | Dữ liệu nhỏ, cần toàn bộ list |
| `ObjectReader.readValues(...)` | Đọc tuần tự nhiều giá trị thành `T` | Array lớn hoặc JSON value sequence |
| `JsonParser` thủ công | Đọc token và tự quyết định cách tạo object | Cần kiểm soát cấu trúc rất chi tiết hoặc bỏ qua nhiều nhánh |
| Đọc từng dòng NDJSON | Mỗi dòng deserialize độc lập | Cần cô lập lỗi và tiếp tục theo record |

Chọn API có mức trừu tượng phù hợp:

- Nếu chỉ cần `List<T>` nhỏ, `readValue()` dễ đọc hơn.
- Nếu cần xử lý nhiều record cùng kiểu, `MappingIterator<T>` giảm nhu cầu giữ toàn bộ list.
- Nếu cần đọc các phần cấu trúc rất khác nhau hoặc bỏ qua phần lớn dữ liệu, `JsonParser` trực tiếp có thể phù hợp hơn.
- Nếu cần ranh giới lỗi từng record, JSON Lines và đọc theo dòng thường dễ phục hồi hơn.

## 13. Những lỗi thường gặp

**Dùng `readerFor(List<User>)` để đọc từng user trong root array.** Kiểu đích phải là kiểu của từng phần tử sequence, tức `User.class`. Nếu muốn một `List<User>` duy nhất, dùng `readValue()`.

**Gọi `readAll()` cho file lớn.** Phương thức này tạo list chứa toàn bộ kết quả, khiến bộ nhớ tăng theo số record. Hãy xử lý tuần tự hoặc theo batch giới hạn.

**Quên đóng MappingIterator.** Iterator quản lý parser và có thể quản lý nguồn được reader mở. Dùng `try-with-resources`.

**Giữ tất cả object đã đọc trong cache hoặc list phụ.** Dù dùng iterator, ứng dụng vẫn có thể tiêu thụ bộ nhớ lớn nếu giữ mọi tham chiếu. Xử lý và giải phóng từng record.

**Cho rằng MappingIterator tự phục hồi sau mọi lỗi.** Lỗi cú pháp có thể làm parser mất khả năng xác định ranh giới value tiếp theo. Muốn cô lập lỗi, dùng định dạng record độc lập như NDJSON.

**Nhầm JSON array với nhiều root-level document.** Cả hai có thể được đọc theo sequence, nhưng framing và hợp đồng giữa hệ thống khác nhau. Hãy thống nhất định dạng đầu vào.

**Tạo ObjectMapper mới trong vòng lặp.** Việc này lãng phí và có thể làm mất cấu hình. Tạo `ObjectReader` một lần rồi tái sử dụng.

**Dùng parser ngoài mà không quản lý parser.** Khi truyền `JsonParser` cho `readValues(parser)`, caller vẫn cần hiểu và quản lý vòng đời parser.

## 14. Quy trình triển khai đọc dữ liệu lớn

1. Xác định nguồn chứa một root array, nhiều root value hay JSON Lines.
2. Chọn kiểu Java của từng record, ví dụ `User.class` hoặc một `JavaType` generic.
3. Tạo `ObjectReader` từ mapper đã cấu hình.
4. Mở nguồn bằng `InputStream` hoặc `Reader` để không nạp toàn bộ file vào chuỗi.
5. Gọi `readValues()` và dùng `MappingIterator` trong `try-with-resources`.
6. Lặp bằng `hasNextValue()` và `nextValue()`.
7. Xử lý record ngay hoặc gom batch có giới hạn; tránh `readAll()` nếu dữ liệu lớn.
8. Xác định chính sách lỗi: dừng toàn file hay cô lập lỗi theo record bằng định dạng có framing rõ.
9. Quản lý transaction, retry và idempotency ở tầng nghiệp vụ.
10. Đo bộ nhớ và throughput với kích thước dữ liệu gần môi trường thật.

## Kết luận

`ObjectReader` giữ kiểu đích và cấu hình deserialize; `MappingIterator<T>` đọc nhiều giá trị JSON tuần tự và trả về từng object. Với một root array lớn, dùng `readerFor(T.class).readValues(source)` để xử lý từng phần tử mà không tạo một list chứa toàn bộ dữ liệu. Hãy tái sử dụng reader, đóng iterator đúng cách, xử lý record ngay hoặc theo batch giới hạn và tránh `readAll()` khi nguồn lớn. Nếu cần cô lập lỗi theo từng bản ghi, định dạng JSON Lines với ranh giới dòng rõ ràng thường dễ quản lý hơn một tài liệu JSON lớn.
