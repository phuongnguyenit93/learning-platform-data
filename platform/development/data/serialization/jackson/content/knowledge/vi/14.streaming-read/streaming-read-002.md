# Khởi tạo parser từ nguồn byte và nguồn ký tự

Jackson Core cung cấp `JsonParser` để đọc JSON theo từng token. Trước khi parser có thể đọc token đầu tiên, ứng dụng cần cung cấp dữ liệu đầu vào. Dữ liệu đó có thể đến từ file, network stream, mảng byte, `Reader` hoặc một chuỗi Java.

Điểm cần phân biệt là **nguồn byte** và **nguồn ký tự**:

- Nguồn byte (`InputStream`, `byte[]`, `File`, `URL`) chứa các byte được mã hóa. Jackson cần xác định hoặc nhận biết encoding để giải mã JSON.
- Nguồn ký tự (`Reader`, `char[]`, `String`) đã được giải mã thành ký tự Java. Việc chọn charset đã xảy ra trước khi parser nhận dữ liệu.

Chọn đúng overload của `JsonFactory.createParser()` giúp ứng dụng xử lý dữ liệu lớn theo luồng, giữ đúng encoding và quản lý vòng đời tài nguyên rõ ràng.

## 1. JsonFactory và JsonParser

`JsonFactory` là factory thuộc Jackson Core, chịu trách nhiệm tạo parser để đọc JSON và generator để ghi JSON. `JsonParser` đọc nguồn dữ liệu theo thứ tự và cung cấp các token như `START_OBJECT`, `FIELD_NAME`, `VALUE_STRING`, `VALUE_NUMBER_INT` và `END_OBJECT`.

Ví dụ khởi tạo parser từ chuỗi JSON:

```java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser("{\"id\":25,\"name\":\"An\"}")) {
    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        System.out.println(token);
    }
}
```

Với ứng dụng đã dùng `ObjectMapper`, có thể lấy factory từ mapper:

```java
ObjectMapper mapper = new ObjectMapper();
JsonFactory factory = mapper.getFactory();
```

Đây thường là lựa chọn phù hợp khi muốn dùng cùng `JsonFactory` và các thiết lập parser mà mapper đang sử dụng. Hãy cấu hình factory trước khi chia sẻ nó cho các thành phần khác.

### 1.1. Luồng xử lý tổng quát

```text
Nguồn dữ liệu
   |
   +-- byte source: InputStream / byte[] / File
   |       |
   |       +-- Jackson nhận diện hoặc xử lý encoding
   |
   +-- character source: Reader / char[] / String
           |
           +-- ký tự đã được giải mã trước đó
   |
   v
JsonFactory.createParser(...)
   |
   v
JsonParser
   |
   +-- nextToken()
   +-- đọc tên field và giá trị
   +-- skipChildren() khi cần bỏ qua cấu trúc lồng nhau
   |
   v
Đóng parser và giải phóng tài nguyên
```

Parser không cần biết dữ liệu đến từ file hay network. Sau khi được tạo, cách đọc token về cơ bản giống nhau; điểm khác biệt nằm ở overload tạo parser, encoding và quyền sở hữu nguồn dữ liệu.

## 2. Tạo parser từ nguồn byte

Nguồn byte phù hợp khi đọc file, HTTP body, message queue hoặc dữ liệu nhị phân nhận từ hệ thống khác. Các API thường dùng gồm:

| Nguồn | Overload |
|---|---|
| Luồng byte | `createParser(InputStream)` |
| File | `createParser(File)` |
| URL | `createParser(URL)` |
| Mảng byte | `createParser(byte[])` |
| Một vùng trong mảng byte | `createParser(byte[], offset, length)` |

Với nguồn byte, Jackson có thể nhận diện encoding JSON từ byte đầu vào. Jackson Core hỗ trợ nhận diện các encoding Unicode thường dùng như UTF-8, UTF-16 và UTF-32. Đối với trao đổi JSON giữa các hệ thống, UTF-8 là lựa chọn phổ biến và được khuyến nghị trong thực tế.

### 2.1. Tạo parser từ InputStream

Ví dụ đọc JSON từ file thông qua `InputStream`:

```java
Path path = Path.of("data/users.json");
JsonFactory factory = new JsonFactory();

try (InputStream input = Files.newInputStream(path);
     JsonParser parser = factory.createParser(input)) {

    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        if (token == JsonToken.FIELD_NAME) {
            System.out.println("Field: " + parser.currentName());
        } else if (token.isScalarValue()) {
            System.out.println("Value: " + parser.getText());
        }
    }
}
```

`createParser(input)` nhận byte stream trực tiếp. Jackson đọc dữ liệu từ stream và chuyển thành token khi chương trình gọi `nextToken()`. Không cần tự đọc toàn bộ file thành một `String` trước.

Trong ví dụ, cả `InputStream` và `JsonParser` đều nằm trong `try-with-resources`. Parser mặc định có thể tự đóng source khi đóng parser; đóng thêm stream ở scope bên ngoài là an toàn với các stream chuẩn của Java. Quyền sở hữu source và cấu hình auto-close được giải thích ở phần quản lý tài nguyên.

### 2.2. Tạo parser trực tiếp từ File

Nếu dữ liệu nằm trong file, có thể truyền `File`:

```java
File file = Path.of("data/orders.json").toFile();

try (JsonParser parser = factory.createParser(file)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
```

Overload nhận `File` giúp code ngắn gọn vì Jackson tự mở nguồn byte. Khi parser đóng, tài nguyên do factory mở được đóng theo chính sách auto-close mặc định.

Không nhầm overload này với `createParser(String)`. `File` biểu diễn file cần đọc; `String` biểu diễn nội dung JSON nằm trong bộ nhớ.

### 2.3. Tạo parser từ byte array

Nếu dữ liệu đã nằm trong `byte[]`, có thể tạo parser trực tiếp:

```java
byte[] jsonBytes = Files.readAllBytes(Path.of("data/user.json"));

try (JsonParser parser = factory.createParser(jsonBytes)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
```

Jackson nhận diện encoding từ byte array theo nội dung. Overload có `offset` và `length` cho phép chỉ parse một vùng của mảng:

```java
try (JsonParser parser = factory.createParser(
        jsonBytes,
        startOffset,
        jsonLength)) {
    // Đọc JSON trong vùng đã chọn
}
```

Các giá trị `startOffset` và `jsonLength` phải nằm trong giới hạn mảng và xác định chính xác một tài liệu JSON hợp lệ. Cách này hữu ích khi một giao thức đã đóng khung dữ liệu trong buffer lớn.

Lưu ý: `byte[]` đã chứa toàn bộ dữ liệu trong heap. Parser vẫn đọc token tuần tự, nhưng việc nạp toàn bộ file vào mảng không phải streaming từ nguồn ngoài. Với file lớn hoặc HTTP body dài, ưu tiên `InputStream`.

### 2.4. Tạo parser từ URL

Jackson có overload nhận `URL`:

```java
URL url = URI.create("https://example.com/data.json").toURL();

try (JsonParser parser = factory.createParser(url)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
```

Overload này để factory mở nguồn từ URL. Trong ứng dụng production, nếu cần cấu hình timeout, authentication, header, proxy hoặc retry, thường nên tự tạo `URLConnection`/HTTP client, lấy `InputStream` từ response rồi truyền stream vào parser. Cách đó giúp ứng dụng kiểm soát kết nối và vòng đời HTTP rõ ràng.

Không dùng `URL` parser như một thay thế đầy đủ cho HTTP client. Việc tạo parser không tự cung cấp chính sách timeout, xác thực hoặc retry phù hợp cho ứng dụng.

## 3. Encoding của nguồn byte

Byte stream chứa byte, không chứa khái niệm ký tự Java. Trước khi diễn giải văn bản, cần biết byte được mã hóa theo charset nào.

Với nguồn byte, Jackson có cơ chế nhận diện encoding Unicode của JSON dựa trên byte đầu vào. Điều này giúp parser đọc được các tài liệu được mã hóa UTF-8, UTF-16 hoặc UTF-32 trong những dạng được hỗ trợ.

Ví dụ, nếu file được ghi bằng UTF-8:

```java
try (InputStream input = Files.newInputStream(Path.of("data.json"));
     JsonParser parser = factory.createParser(input)) {
    // Jackson xử lý byte input và encoding
}
```

Không cần tự chuyển byte sang `String` chỉ để chỉ định UTF-8. Truyền byte stream trực tiếp cho parser giúp Jackson xử lý việc giải mã và đọc theo luồng.

### 3.1. BOM và encoding detection

Một số tài liệu văn bản bắt đầu bằng BOM (Byte Order Mark), có thể giúp xác định encoding hoặc byte order. Jackson có thể xử lý BOM được hỗ trợ khi đọc byte source. Tuy nhiên, không nên dùng BOM như cách duy nhất để xác định charset cho mọi giao thức hoặc mọi nguồn dữ liệu.

Đối với API JSON, hãy thống nhất UTF-8 ở hai đầu giao tiếp. Nếu hệ thống nguồn có charset khác, cần biết rõ encoding theo hợp đồng hoặc metadata của nguồn.

### 3.2. Tránh tự chuyển byte thành String không rõ charset

Không nên viết:

```java
String json = new String(bytes);
JsonParser parser = factory.createParser(json);
```

Constructor `new String(bytes)` dùng charset mặc định của JVM, có thể khác môi trường chạy. Nếu bắt buộc phải chuyển byte thành chuỗi trước, chỉ định charset rõ ràng:

```java
String json = new String(bytes, StandardCharsets.UTF_8);
try (JsonParser parser = factory.createParser(json)) {
    // Đọc nội dung
}
```

Tuy nhiên, nếu mục tiêu là đọc JSON từ byte source, truyền `byte[]` hoặc `InputStream` trực tiếp thường tốt hơn. Nó tránh một bản sao chuỗi lớn và giữ khả năng xử lý encoding của parser.

## 4. Tạo parser từ nguồn ký tự

Nguồn ký tự đã được giải mã thành các ký tự Java trước khi Jackson nhận dữ liệu. Các overload thường dùng:

| Nguồn | Overload |
|---|---|
| Reader | `createParser(Reader)` |
| String | `createParser(String)` |
| Mảng ký tự | `createParser(char[])` |
| Một vùng trong mảng ký tự | `createParser(char[], offset, length)` |

Với các nguồn này, Jackson không còn lựa chọn charset cho byte gốc. Nếu dữ liệu ban đầu đến từ file hoặc network, ứng dụng chịu trách nhiệm giải mã byte thành ký tự trước khi tạo `Reader`.

### 4.1. Tạo parser từ Reader

Ví dụ đọc file văn bản UTF-8 qua `Reader`:

```java
Path path = Path.of("data/users.json");

try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
     JsonParser parser = factory.createParser(reader)) {

    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        if (token == JsonToken.FIELD_NAME) {
            System.out.println(parser.currentName());
        }
    }
}
```

`Files.newBufferedReader(path, StandardCharsets.UTF_8)` đã giải mã byte của file thành ký tự. `JsonParser` chỉ nhận các ký tự từ `Reader`, vì vậy encoding cần được chọn chính xác ở bước mở reader.

`Reader` hữu ích khi ứng dụng đã có nguồn ký tự, chẳng hạn `StringReader`, reader từ thư viện khác hoặc luồng văn bản đã được giải mã.

### 4.2. Tạo parser từ String

Nếu JSON đã là một chuỗi Java:

```java
String json = """
    {
      "id": 25,
      "name": "An"
    }
    """;

try (JsonParser parser = factory.createParser(json)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
```

`createParser(String)` parse nội dung chuỗi. Nó không mở file có tên bằng chuỗi đó và cũng không diễn giải chuỗi như URL.

Đây là điểm rất dễ nhầm:

```java
factory.createParser("data/users.json");
```

Đoạn trên yêu cầu Jackson parse chính các ký tự `data/users.json` như nội dung JSON; nó không đọc file. Để đọc file, truyền `File`, `Path` thông qua `InputStream`, hoặc `Reader`.

### 4.3. Tạo parser từ char array

Nếu dữ liệu đã có trong `char[]`, có thể truyền trực tiếp:

```java
char[] jsonChars = json.toCharArray();

try (JsonParser parser = factory.createParser(jsonChars)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
```

Có thể chỉ parse một đoạn:

```java
try (JsonParser parser = factory.createParser(
        jsonChars,
        start,
        length)) {
    // Đọc vùng ký tự được chọn
}
```

Offset và length phải hợp lệ, đồng thời vùng được chọn phải chứa một tài liệu JSON hoàn chỉnh. `char[]` có thể hữu ích khi một thành phần upstream đã xử lý văn bản và giữ dữ liệu dưới dạng mảng ký tự.

## 5. Chọn InputStream hay Reader?

Hai cách đều tạo được parser và đọc token, nhưng khác nhau ở nơi xử lý encoding.

| Tiêu chí | InputStream | Reader |
|---|---|---|
| Dữ liệu đầu vào | Byte | Ký tự Java |
| Encoding | Jackson xử lý encoding của byte source | Thành phần tạo Reader đã chọn charset và giải mã |
| Phù hợp | File/network/body/message dạng byte | Nguồn văn bản đã giải mã hoặc cần charset cụ thể ở tầng ứng dụng |
| Streaming | Có, đọc tăng dần từ stream | Có, đọc tăng dần từ reader |
| Rủi ro chính | Encoding hoặc byte source không đúng | Reader được tạo với charset sai hoặc dữ liệu đã bị giải mã sai |

Nếu có byte source và muốn Jackson tự xử lý encoding được hỗ trợ, dùng `InputStream`. Nếu ứng dụng đã có một `Reader` với charset được xác định từ giao thức hoặc cấu hình, dùng `Reader`.

### 5.1. Khi cần charset được chỉ định bởi ứng dụng

Đôi khi giao thức hoặc file legacy quy định charset rõ ràng. Khi đó, tạo `Reader` với charset được chỉ định:

```java
Charset charset = StandardCharsets.UTF_8;

try (InputStream input = Files.newInputStream(path);
     Reader reader = new InputStreamReader(input, charset);
     JsonParser parser = factory.createParser(reader)) {
    // Đọc token
}
```

Ở đây, `InputStreamReader` chịu trách nhiệm chuyển byte thành ký tự theo UTF-8. Parser không thể tự phát hiện lại charset gốc vì nó chỉ nhận ký tự.

Nếu dữ liệu không được phép thay thế byte lỗi bằng ký tự replacement, có thể cấu hình `CharsetDecoder` để báo lỗi:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

try (InputStream input = Files.newInputStream(path);
     Reader reader = new InputStreamReader(input, decoder);
     JsonParser parser = factory.createParser(reader)) {
    // Dữ liệu sai encoding sẽ được báo lỗi khi giải mã
}
```

Cách này phù hợp khi dữ liệu cần được xác thực nghiêm ngặt theo charset đã thỏa thuận.

## 6. Quản lý vòng đời parser và nguồn dữ liệu

`JsonParser` triển khai `Closeable`. Sau khi đọc xong hoặc khi xảy ra lỗi, hãy đóng parser để giải phóng buffer và các tài nguyên nội bộ.

```java
try (JsonParser parser = factory.createParser(input)) {
    // Đọc JSON
}
```

Jackson có feature `StreamReadFeature.AUTO_CLOSE_SOURCE`. Feature này được bật mặc định trong cấu hình thông thường; khi parser đóng, source có thể được đóng cùng. Source có thể là `InputStream` hoặc `Reader` được truyền vào parser.

### 6.1. Khi parser sở hữu source

Nếu ứng dụng tạo stream chỉ để parser sử dụng, để auto-close mặc định là hợp lý:

```java
try (JsonParser parser = factory.createParser(
        Files.newInputStream(Path.of("data.json")))) {
    // Đọc JSON
}
```

Khi parser đóng, stream được factory/parser quản lý sẽ được đóng theo chính sách auto-close. Trong code thực tế, nếu cần bảo đảm stream được đóng cả khi quá trình tạo parser phát sinh lỗi, hãy quản lý stream bằng một `try-with-resources` bên ngoài.

### 6.2. Khi source thuộc quyền quản lý của thành phần khác

Nếu `InputStream` được truyền từ servlet container, framework, message consumer hoặc một thành phần khác và caller phải giữ quyền đóng source, có thể tắt auto-close trên factory:

```java
JsonFactory factory = JsonFactory.builder()
    .disable(StreamReadFeature.AUTO_CLOSE_SOURCE)
    .build();
```

Khi đó, đóng parser vẫn giải phóng tài nguyên nội bộ của parser nhưng không tự đóng source. Thành phần sở hữu stream phải đóng nó đúng vòng đời.

Feature được cấu hình trên factory và ảnh hưởng các parser tạo từ factory đó. Nếu ứng dụng có cả nguồn do parser sở hữu lẫn nguồn do framework sở hữu, cần tổ chức factory hoặc quản lý tài nguyên nhất quán để tránh đóng nhầm stream.

### 6.3. Đóng parser khác với đóng source

Hãy phân biệt:

- Đóng parser: giải phóng tài nguyên nội bộ, buffer và trạng thái parser.
- Đóng source: đóng `InputStream` hoặc `Reader` bên dưới.

`AUTO_CLOSE_SOURCE` quyết định parser có đóng source cùng hay không. Dù source không thuộc quyền sở hữu của parser, ứng dụng vẫn nên đóng parser sau khi hoàn tất.

## 7. Đọc token giống nhau với mọi loại nguồn

Sau khi tạo parser, code đọc token không phụ thuộc parser được tạo từ byte stream hay character reader.

Ví dụ đọc một object và lấy `id` cùng `name`:

```java
static void readUser(JsonParser parser) throws IOException {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new JsonParseException(parser, "Expected a JSON object");
    }

    Long id = null;
    String name = null;

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new JsonParseException(parser, "Unexpected end of JSON object");
        }
        if (token != JsonToken.FIELD_NAME) {
            throw new JsonParseException(parser, "Expected a field name");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();
        if (valueToken == null) {
            throw new JsonParseException(parser, "Missing field value");
        }

        if ("id".equals(fieldName) && valueToken.isNumeric()) {
            id = parser.getLongValue();
        } else if ("name".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            name = parser.getText();
        } else {
            parser.skipChildren();
        }
    }

    System.out.println("id=" + id + ", name=" + name);
}
```

Có thể gọi cùng hàm này với parser từ `InputStream`:

```java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = factory.createParser(input)) {
    readUser(parser);
}
```

Hoặc từ `Reader`:

```java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
     JsonParser parser = factory.createParser(reader)) {
    readUser(parser);
}
```

Điều này cho thấy source creation và token processing là hai trách nhiệm riêng. Có thể thay nguồn dữ liệu mà không phải viết lại logic xử lý token.

## 8. Kết hợp parser với ObjectMapper

`ObjectMapper` có thể đọc trực tiếp từ nhiều loại nguồn, nhưng đôi khi ứng dụng muốn tự tạo parser để kiểm soát luồng token rồi ánh xạ từng phần thành POJO.

Ví dụ, một file chứa array nhiều user:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Có thể đọc từng object từ byte stream:

```java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new JsonParseException(parser, "Expected a JSON array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        User user = mapper.readValue(parser, User.class);
        process(user);
    }
}
```

Parser điều hướng đến từng phần tử; `ObjectMapper.readValue(parser, User.class)` đọc object hiện tại thành `User`. Đây là cách kết hợp streaming với data binding, phù hợp khi file có nhiều phần tử nhưng logic nghiệp vụ vẫn muốn làm việc với DTO có kiểu.

Nếu parser đã được tạo từ `Reader`, phần ánh xạ object vẫn giống nhau. Chỉ thay cách tạo parser:

```java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
     JsonParser parser = mapper.getFactory().createParser(reader)) {
    // Cùng logic đọc array và map từng object
}
```

## 9. Lựa chọn nguồn phù hợp theo tình huống

| Tình huống | Nguồn nên dùng | Lý do |
|---|---|---|
| Đọc file JSON lớn | `InputStream` hoặc `File` | Đọc tăng dần, không cần nạp toàn bộ nội dung vào String |
| Đọc HTTP response body | `InputStream` | Giữ dữ liệu ở dạng byte và xử lý stream trực tiếp |
| Nguồn đã có Reader | `Reader` | Không cần giải mã lại dữ liệu đã thành ký tự |
| Charset được quy định rõ bởi ứng dụng | `InputStreamReader` với charset/decoder cụ thể | Chủ động kiểm soát quá trình byte-to-character |
| JSON nhỏ đã nằm trong String | `String` | API ngắn gọn, không cần tạo stream trung gian |
| Buffer đã có sẵn trong byte[] | `byte[]` | Không cần copy sang String; Jackson có thể xử lý encoding |
| Một vùng trong buffer lớn | `byte[]`/`char[]` với offset và length | Chỉ parse phần dữ liệu đã được đóng khung |
| File nhỏ đã đọc thành ký tự | `Reader` hoặc `String` | Dùng lại nguồn ký tự có sẵn |

Nếu dữ liệu lớn, tránh `Files.readAllBytes()` hoặc `readString()` chỉ để tạo parser. Những API đó nạp toàn bộ nội dung vào bộ nhớ trước khi Jackson bắt đầu parse. Dùng `InputStream` hoặc `Reader` để tận dụng xử lý tăng dần.

## 10. Những lỗi thường gặp

### Truyền đường dẫn file vào overload String

`createParser("users.json")` parse chuỗi `users.json` như nội dung JSON. Muốn mở file, truyền `File`, `InputStream` hoặc `Reader`.

### Dùng charset mặc định của JVM

`new String(bytes)` hoặc `new InputStreamReader(input)` không chỉ định charset có thể phụ thuộc môi trường. Dùng byte parser trực tiếp hoặc chỉ định charset rõ ràng.

### Chuyển toàn bộ InputStream thành String

Việc này tăng mức sử dụng bộ nhớ và tạo thêm bản sao dữ liệu. Với JSON lớn, truyền stream trực tiếp.

### Đóng source quá sớm

Không đóng `InputStream` hoặc `Reader` trước khi parser đọc xong. Nếu parser không sở hữu source, caller vẫn phải giữ source mở trong toàn bộ thời gian parser sử dụng nó.

### Không đóng parser

Không đóng parser có thể giữ buffer hoặc tài nguyên bên dưới. Dùng `try-with-resources` cho parser.

### Tắt auto-close nhưng quên đóng stream

Nếu `AUTO_CLOSE_SOURCE` bị tắt, parser không còn đóng source thay ứng dụng. Caller phải quản lý vòng đời `InputStream` hoặc `Reader`.

### Dùng Reader nhưng cho rằng Jackson sẽ tự phát hiện charset gốc

Reader chỉ cung cấp ký tự. Nếu byte đã được giải mã sai trước đó, parser không thể khôi phục encoding ban đầu. Hãy xác định charset ở nơi tạo Reader.

## 11. Checklist khi khởi tạo parser

1. Xác định dữ liệu đang có dưới dạng byte hay ký tự.
2. Nếu là byte, chọn `InputStream`, `File`, `URL` hoặc `byte[]` phù hợp; ưu tiên stream cho dữ liệu lớn.
3. Nếu là ký tự, chọn `Reader`, `String` hoặc `char[]`.
4. Xác định encoding của nguồn. Với byte source, dùng khả năng nhận diện encoding của Jackson hoặc cung cấp Reader với charset rõ ràng.
5. Không nhầm `createParser(String)` với mở file hoặc URL.
6. Dùng `try-with-resources` để đóng parser.
7. Xác định ai sở hữu `InputStream`/`Reader` và chính sách `AUTO_CLOSE_SOURCE`.
8. Đọc token tuần tự; dùng `skipChildren()` khi bỏ qua object hoặc array lồng nhau.
9. Với dữ liệu lớn, tránh nạp toàn bộ byte hoặc ký tự vào mảng/chuỗi trước khi parse.
10. Khi kết hợp với `ObjectMapper`, dùng factory từ mapper đang cấu hình nếu cần giữ các thiết lập thống nhất.

## Kết luận

`JsonFactory.createParser()` nhận nhiều loại nguồn để Jackson đọc JSON theo token. Nguồn byte như `InputStream`, `File` và `byte[]` giữ dữ liệu ở dạng byte để Jackson xử lý encoding; nguồn ký tự như `Reader`, `String` và `char[]` đã được giải mã trước khi parser nhận dữ liệu. Hãy chọn nguồn phù hợp với dữ liệu hiện có, chỉ định charset rõ ràng khi tạo Reader, dùng stream cho dữ liệu lớn và quản lý `JsonParser` cùng source theo đúng quyền sở hữu. Sau khi parser được tạo, logic đọc token có thể dùng chung cho mọi loại nguồn.
