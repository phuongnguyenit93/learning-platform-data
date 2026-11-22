# Mối quan hệ giữa `JsonFactory`, `JsonParser` và `JsonGenerator`

Trong Jackson Core, `JsonFactory`, `JsonParser` và `JsonGenerator` là ba thành phần phối hợp để đọc và ghi JSON theo mô hình streaming. Chúng có trách nhiệm khác nhau nhưng tạo thành một chuỗi thống nhất: **factory tạo ra đối tượng làm việc với luồng dữ liệu; parser đọc JSON thành các token; generator ghi các token thành JSON**.

Hiểu rõ ranh giới này giúp chọn đúng API khi xử lý JSON lớn, chuyển đổi dữ liệu từng phần hoặc tích hợp Jackson Databind.

## 1. Vị trí của ba thành phần trong Jackson

Ba kiểu này thuộc Jackson Core, thường được import từ package `com.fasterxml.jackson.core`:

| Thành phần | Trách nhiệm chính | Làm việc trực tiếp với |
|---|---|---|
| `JsonFactory` | Tạo parser và generator; giữ cấu hình chung cho việc đọc/ghi JSON | Nguồn dữ liệu hoặc đích ghi khi tạo đối tượng |
| `JsonParser` | Đọc JSON và lần lượt cung cấp các token mô tả nội dung | `InputStream`, `Reader`, mảng byte, chuỗi JSON hoặc nguồn được hỗ trợ |
| `JsonGenerator` | Nhận lệnh ghi token và tuần tự hóa chúng thành JSON | `OutputStream`, `Writer` hoặc đích ghi được hỗ trợ |

Có thể hình dung mối quan hệ như sau:

```text
                         Jackson Core

                    +------------------+
                    |    JsonFactory   |
                    | cấu hình và tạo  |
                    +--------+---------+
                             |
                +------------+------------+
                |                         |
         createParser(...)         createGenerator(...)
                |                         |
                v                         v
       +----------------+        +------------------+
       |   JsonParser   |        |  JsonGenerator   |
       | JSON -> tokens |        | tokens -> JSON   |
       +-------+--------+        +---------+--------+
               |                           ^
               v                           |
        InputStream / Reader       OutputStream / Writer
```

`JsonFactory` không tự đọc toàn bộ tài liệu rồi trả về một cây JSON. Nó tạo ra đối tượng chuyên trách cho từng luồng. `JsonParser` và `JsonGenerator` cũng không phải hai đầu của một kết nối bắt buộc: ứng dụng có thể chỉ dùng parser để đọc, chỉ dùng generator để ghi, hoặc dùng cả hai khi chuyển đổi dữ liệu.

## 2. `JsonFactory`: điểm khởi tạo parser và generator

`JsonFactory` là đối tượng tạo các luồng đọc và ghi JSON. Thay vì tự khởi tạo parser hay generator bằng constructor, ứng dụng thường yêu cầu factory tạo chúng từ nguồn đầu vào hoặc đích đầu ra.

```java
import com.fasterxml.jackson.core.JsonFactory;

JsonFactory factory = new JsonFactory();
```

Sau khi tạo factory, có thể dùng cùng một instance để tạo nhiều parser và generator:

```java
JsonParser parser = factory.createParser(inputStream);
JsonGenerator generator = factory.createGenerator(outputStream);
```

Các overload khác cho phép đọc từ `Reader`, `String`, `File` hoặc dữ liệu byte, và ghi ra `Writer` hoặc `OutputStream`. Chọn overload phù hợp với loại nguồn/đích mà ứng dụng đang có để tránh tự chuyển đổi dữ liệu không cần thiết.

### 2.1. Factory chịu trách nhiệm gì?

Factory là nơi tập trung các thiết lập ảnh hưởng đến việc tạo parser và generator, ví dụ:

- Các tính năng đọc và ghi JSON được bật hoặc tắt.
- Quy tắc xử lý những giới hạn của luồng như độ sâu cấu trúc hoặc kích thước nội dung, tùy phiên bản Jackson và cấu hình.
- Cấu hình codec được dùng khi tích hợp với tầng ánh xạ đối tượng.
- Việc tạo parser/generator phù hợp với kiểu nguồn hoặc đích dữ liệu.

Factory không giữ vị trí đọc hiện tại của từng tài liệu. Vị trí đọc, token hiện tại và trạng thái cấu trúc thuộc về từng `JsonParser`; trạng thái ghi thuộc về từng `JsonGenerator`. Vì vậy, tạo hai parser từ cùng một factory vẫn tạo ra hai phiên đọc độc lập.

### 2.2. Có thể tái sử dụng factory

Thông thường, một `JsonFactory` được cấu hình khi khởi tạo rồi tái sử dụng để tạo nhiều parser/generator. Factory được thiết kế để có thể dùng chung giữa các luồng xử lý sau khi cấu hình hoàn tất. Trong khi đó, mỗi parser hoặc generator nên gắn với một luồng công việc cụ thể; không dùng chung một parser/generator cho nhiều luồng đồng thời.

Nếu cần các cấu hình đọc/ghi khác nhau, có thể tạo các factory riêng hoặc hoàn tất cấu hình trước khi đưa factory vào sử dụng. Tránh thay đổi cấu hình trong lúc những luồng xử lý khác đang tạo hoặc sử dụng parser/generator từ factory đó.

## 3. `JsonParser`: đọc JSON theo từng token

`JsonParser` là API đọc dạng streaming theo mô hình pull. Ứng dụng chủ động yêu cầu parser tiến đến token kế tiếp bằng `nextToken()`. Parser không bắt buộc phải dựng toàn bộ JSON thành object trong bộ nhớ.

Ví dụ với tài liệu:

```json
{
  "name": "An",
  "active": true,
  "scores": [8, 9]
}
```

Parser lần lượt nhìn thấy các token đại diện cho cấu trúc và giá trị, chẳng hạn:

```text
START_OBJECT
FIELD_NAME       "name"
VALUE_STRING     "An"
FIELD_NAME       "active"
VALUE_TRUE
FIELD_NAME       "scores"
START_ARRAY
VALUE_NUMBER_INT 8
VALUE_NUMBER_INT 9
END_ARRAY
END_OBJECT
```

Tên token được biểu diễn bằng enum `JsonToken`. Parser giữ vị trí hiện tại; sau mỗi lần gọi `nextToken()`, ứng dụng kiểm tra token hiện tại rồi lấy giá trị tương ứng.

### 3.1. Ví dụ đọc tuần tự

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.IOException;
import java.io.InputStream;

public class ReadJsonExample {
    public void read(InputStream input) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonParser parser = factory.createParser(input)) {
            JsonToken token;

            while ((token = parser.nextToken()) != null) {
                if (token == JsonToken.FIELD_NAME) {
                    System.out.println("Field: " + parser.getCurrentName());
                } else if (token == JsonToken.VALUE_STRING) {
                    System.out.println("String: " + parser.getText());
                } else if (token == JsonToken.VALUE_NUMBER_INT) {
                    System.out.println("Integer: " + parser.getIntValue());
                } else if (token == JsonToken.VALUE_TRUE) {
                    System.out.println("Boolean: true");
                } else if (token == JsonToken.VALUE_FALSE) {
                    System.out.println("Boolean: false");
                }
            }
        }
    }
}
```

Điểm cần nhớ:

- `nextToken()` di chuyển parser đến token tiếp theo và trả về `null` khi đã hết nội dung.
- `getCurrentName()` lấy tên field khi token hiện tại là tên field hoặc đang ở ngữ cảnh có field hiện hành.
- `getText()` đọc nội dung dạng văn bản của token hiện tại.
- Các phương thức như `getIntValue()`, `getLongValue()` hoặc `getDecimalValue()` lấy giá trị số theo kiểu mong muốn.
- Chỉ gọi phương thức lấy giá trị phù hợp với token hiện tại. Ví dụ, không gọi `getIntValue()` khi parser đang ở `START_OBJECT`.

### 3.2. Token cấu trúc và token giá trị

Các token thường gặp được chia thành hai nhóm:

| Nhóm | Token tiêu biểu | Ý nghĩa |
|---|---|---|
| Cấu trúc | `START_OBJECT`, `END_OBJECT` | Bắt đầu/kết thúc object |
| Cấu trúc | `START_ARRAY`, `END_ARRAY` | Bắt đầu/kết thúc array |
| Cấu trúc | `FIELD_NAME` | Tên thuộc tính trong object |
| Giá trị | `VALUE_STRING` | Chuỗi |
| Giá trị | `VALUE_NUMBER_INT`, `VALUE_NUMBER_FLOAT` | Số nguyên, số thập phân |
| Giá trị | `VALUE_TRUE`, `VALUE_FALSE`, `VALUE_NULL` | Boolean và null |

Với object hoặc array lồng nhau, parser phát ra token mở, các token con rồi token đóng tương ứng. Nếu ứng dụng không cần xử lý nội dung bên trong một object/array, có thể gọi `skipChildren()` khi parser đang ở token mở để bỏ qua toàn bộ cấu trúc con đó.

### 3.3. Vì sao parser phù hợp với dữ liệu lớn?

Parser đọc tiến dần theo yêu cầu. Ứng dụng có thể xử lý một phần dữ liệu, ghi kết quả hoặc cập nhật trạng thái rồi tiếp tục đọc. Cách này thường tiết kiệm bộ nhớ hơn việc dựng toàn bộ tài liệu thành cây JSON hoặc nhiều object Java.

Đổi lại, ứng dụng phải tự quản lý luồng điều khiển: biết parser đang ở token nào, xử lý cấu trúc lồng nhau ra sao và khi nào cần bỏ qua một nhánh. Streaming đem lại khả năng kiểm soát tốt nhưng đòi hỏi mã xử lý token cẩn thận.

## 4. `JsonGenerator`: ghi JSON từ các lệnh token

`JsonGenerator` là API ghi dạng streaming theo mô hình push. Ứng dụng gọi các phương thức `write...()` theo thứ tự mong muốn; generator chịu trách nhiệm tạo cú pháp JSON tương ứng, bao gồm dấu ngoặc, dấu phẩy, dấu nháy và escape ký tự cần thiết.

### 4.1. Ví dụ tạo JSON

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonEncoding;

import java.io.IOException;
import java.io.OutputStream;

public class WriteJsonExample {
    public void write(OutputStream output) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {
            generator.writeStartObject();
            generator.writeStringField("name", "An");
            generator.writeBooleanField("active", true);

            generator.writeArrayFieldStart("scores");
            generator.writeNumber(8);
            generator.writeNumber(9);
            generator.writeEndArray();

            generator.writeEndObject();
        }
    }
}
```

Kết quả JSON có cấu trúc tương đương:

```json
{
  "name": "An",
  "active": true,
  "scores": [8, 9]
}
```

Định dạng khoảng trắng có thể khác nhau tùy cấu hình pretty printer. Điều quan trọng là generator tạo ra JSON hợp lệ từ chuỗi lệnh ghi.

### 4.2. Generator quản lý cấu trúc ghi

Một số phương thức thường dùng:

| Phương thức | Tác dụng |
|---|---|
| `writeStartObject()` / `writeEndObject()` | Mở/đóng object |
| `writeStartArray()` / `writeEndArray()` | Mở/đóng array |
| `writeFieldName(name)` | Ghi tên field |
| `writeString(value)` | Ghi giá trị chuỗi |
| `writeNumber(value)` | Ghi giá trị số |
| `writeBoolean(value)` | Ghi boolean |
| `writeNull()` | Ghi `null` |
| `writeStringField(name, value)` | Ghi field chuỗi trong một object |
| `writeNumberField(name, value)` | Ghi field số trong một object |
| `writeObjectFieldStart(name)` | Ghi tên field và mở object con |
| `writeArrayFieldStart(name)` | Ghi tên field và mở array con |

Generator theo dõi ngữ cảnh hiện tại để xử lý dấu phân cách và cấu trúc. Ví dụ, sau `writeStartObject()`, một field cần được ghi bằng tên và giá trị; khi ghi xong object con phải đóng đúng cấp bằng `writeEndObject()`. Gọi các lệnh sai thứ tự có thể dẫn đến lỗi sinh JSON hoặc lỗi trạng thái generator.

Generator cũng xử lý việc escape chuỗi. Khi truyền chuỗi có dấu nháy kép, dấu gạch chéo ngược hoặc ký tự điều khiển, ứng dụng nên truyền giá trị nguyên bản cho `writeString()` thay vì tự ghép chuỗi JSON và tự thêm escape.

## 5. Ba thành phần phối hợp như thế nào?

Quan hệ giữa chúng thể hiện rõ qua ba kiểu công việc thường gặp.

### 5.1. Chỉ đọc JSON

```text
InputStream / Reader
        |
        v
JsonFactory.createParser(...)
        |
        v
    JsonParser
        |
        v
  nextToken() -> ứng dụng xử lý từng token
```

Ứng dụng cần một factory để tạo parser. Sau đó parser đọc nguồn đầu vào độc lập với factory. Khi hoàn tất, ứng dụng đóng parser theo quy tắc sở hữu tài nguyên của mình.

### 5.2. Chỉ ghi JSON

```text
ứng dụng quyết định dữ liệu và thứ tự ghi
        |
        v
JsonFactory.createGenerator(...)
        |
        v
   JsonGenerator
        |
        v
OutputStream / Writer
```

Ứng dụng tạo generator từ factory rồi phát các lệnh ghi. Generator chuyển những lệnh đó thành JSON và gửi đến đích đầu ra.

### 5.3. Đọc, biến đổi rồi ghi lại

Đây là trường hợp dùng cả parser và generator. Parser đọc token từ nguồn; ứng dụng có thể kiểm tra, lọc hoặc biến đổi dữ liệu; generator ghi kết quả sang đích khác.

```text
JSON đầu vào
     |
     v
JsonParser -- tokens --> Ứng dụng / logic biến đổi
                                  |
                                  v
                         JsonGenerator
                                  |
                                  v
                            JSON đầu ra
```

Hai đối tượng được tạo độc lập từ factory. Parser không tự gửi token sang generator; chính ứng dụng quyết định token nào được xử lý và cách ghi kết quả.

## 6. Ví dụ: sao chép một tài liệu JSON bằng streaming

Jackson cung cấp phương thức hỗ trợ sao chép token hiện tại. `copyCurrentEvent(parser)` sao chép một event hiện tại; `copyCurrentStructure(parser)` sao chép cả cấu trúc bắt đầu tại token hiện tại, bao gồm các token con của object hoặc array.

Ví dụ sau đọc token đầu tiên của tài liệu rồi sao chép toàn bộ cấu trúc JSON đó sang generator:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonEncoding;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class CopyJsonExample {
    public void copy(InputStream input, OutputStream output) throws IOException {
        JsonFactory factory = new JsonFactory();

        try (JsonParser parser = factory.createParser(input);
             JsonGenerator generator =
                 factory.createGenerator(output, JsonEncoding.UTF8)) {

            if (parser.nextToken() != null) {
                generator.copyCurrentStructure(parser);
            }
        }
    }
}
```

Ví dụ này minh họa việc phối hợp parser và generator mà không cần chuyển toàn bộ tài liệu thành `Map`, `List` hoặc một cây `JsonNode`. Generator sẽ tuần tự hóa lại nội dung, vì vậy khoảng trắng và cách trình bày văn bản có thể khác nguồn ban đầu trong khi cấu trúc và giá trị JSON được giữ lại.

Với một luồng xử lý nhiều phần hoặc cần biến đổi từng field, ứng dụng có thể tự duyệt token và gọi các lệnh ghi tương ứng. Khi sao chép một event đơn lẻ, cần nhớ rằng event mở object/array không tự bao gồm các token con; hãy dùng `copyCurrentStructure()` khi muốn sao chép toàn bộ nhánh cấu trúc.

## 7. Vòng đời và quản lý tài nguyên

Parser và generator thường giữ tài nguyên liên quan đến nguồn/đích dữ liệu. Vì vậy, nên đóng chúng một cách xác định, thường bằng `try-with-resources` như các ví dụ trên.

- Đóng parser kết thúc phiên đọc và, theo cấu hình auto-close, có thể đóng nguồn đầu vào.
- Đóng generator hoàn tất việc ghi, flush dữ liệu còn đệm và, theo cấu hình auto-close, có thể đóng đích đầu ra.
- Nếu ứng dụng cần tiếp tục sử dụng `InputStream`, `Reader`, `OutputStream` hoặc `Writer` sau khi đóng parser/generator, cần kiểm tra và cấu hình các tính năng auto-close phù hợp, đồng thời tự quản lý vòng đời của stream.
- Không giữ parser/generator lâu hơn thời gian cần thiết; một đối tượng nên gắn với một thao tác đọc hoặc ghi cụ thể.

`JsonFactory` thường sống lâu hơn parser/generator và được tái sử dụng. Việc đóng parser không đồng nghĩa phải tạo lại factory.

## 8. `JsonFactory` và `ObjectMapper` liên quan ra sao?

`JsonFactory`, `JsonParser` và `JsonGenerator` thuộc tầng streaming của Jackson Core. `ObjectMapper` thuộc Jackson Databind và cung cấp ánh xạ giữa JSON với object Java.

`ObjectMapper` sử dụng hạ tầng streaming bên dưới. Khi gọi `readValue(...)`, Databind đọc token từ parser để tạo object; khi gọi `writeValue(...)`, Databind ghi object thông qua generator. Có thể cung cấp một `JsonFactory` cho `ObjectMapper` để dùng cấu hình Core tương ứng:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = new JsonFactory();
ObjectMapper mapper = new ObjectMapper(factory);
```

Như vậy, hai tầng giải quyết hai loại công việc khác nhau:

| Jackson Core | Jackson Databind |
|---|---|
| Đọc/ghi token JSON | Ánh xạ JSON với object Java |
| Kiểm soát trực tiếp thứ tự và cấu trúc streaming | Làm việc với POJO, collection, kiểu dữ liệu và cấu hình mapper |
| Phù hợp khi cần xử lý từng phần hoặc tối ưu luồng dữ liệu | Phù hợp khi muốn chuyển đổi dữ liệu thành object một cách thuận tiện |

Không nên nhầm `JsonParser` với `ObjectMapper`: parser cung cấp token, còn mapper dùng token để thực hiện ánh xạ cấp cao hơn.

## 9. Khi nào nên dùng từng thành phần?

| Nhu cầu | Thành phần/cách dùng phù hợp |
|---|---|
| Đọc JSON theo thứ tự, xử lý từng field hoặc record | `JsonFactory` tạo `JsonParser` |
| Ghi JSON theo cấu trúc do ứng dụng quyết định | `JsonFactory` tạo `JsonGenerator` |
| Đọc rồi lọc/chuyển đổi và ghi lại mà không dựng cả cây dữ liệu | Dùng `JsonParser` và `JsonGenerator` cùng nhau |
| Chuyển JSON thành DTO/POJO hoặc ngược lại | Dùng `ObjectMapper`; tầng này dựa trên Core |
| Cần truy cập linh hoạt vào một cấu trúc JSON trong bộ nhớ | Cân nhắc Jackson Tree Model (`JsonNode`) |

Streaming đặc biệt hữu ích khi dữ liệu lớn, cần giới hạn bộ nhớ hoặc chỉ quan tâm đến một phần tài liệu. Với dữ liệu nhỏ và cấu trúc ổn định, `ObjectMapper` thường giúp mã ứng dụng ngắn và dễ bảo trì hơn.

## 10. Những nhầm lẫn thường gặp

**Nhầm `JsonFactory` là parser.** Factory chỉ tạo parser/generator và cung cấp cấu hình khi khởi tạo. Việc đọc token diễn ra trên instance `JsonParser`.

**Nhầm parser tự tạo object Java.** Parser Core cung cấp token và giá trị ở vị trí hiện tại. Việc ánh xạ thành POJO là trách nhiệm của Databind hoặc logic do ứng dụng tự viết.

**Nhầm generator nhận một object bất kỳ rồi tự biến nó thành JSON.** Generator Core cung cấp các lệnh ghi token. Để ghi POJO trực tiếp, thường dùng `ObjectMapper` hoặc một `ObjectCodec` phù hợp.

**Nhầm parser và generator tự liên kết với nhau.** Chúng là hai đối tượng độc lập. Khi chuyển dữ liệu, ứng dụng hoặc phương thức sao chép token của Jackson thực hiện việc đưa event từ parser sang generator.

**Dùng chung một parser cho nhiều tác vụ đồng thời.** Vị trí đọc là trạng thái có thể thay đổi. Mỗi tác vụ nên có parser riêng; quy tắc tương tự áp dụng cho generator.

**Quên đóng parser/generator.** Điều này có thể khiến tài nguyên hoặc dữ liệu còn trong bộ đệm không được giải phóng/hoàn tất đúng lúc. Dùng `try-with-resources` giúp vòng đời rõ ràng hơn.

## 11. Kết luận về mối quan hệ

Ba thành phần tạo thành nền tảng streaming của Jackson Core:

1. `JsonFactory` là nơi tạo và cấu hình các đối tượng đọc/ghi.
2. `JsonParser` đọc JSON và cung cấp lần lượt các `JsonToken` cho ứng dụng.
3. `JsonGenerator` nhận các lệnh ghi token và tạo JSON ở đích đầu ra.

Factory có thể được tái sử dụng; parser và generator đại diện cho từng phiên đọc/ghi. Khi hiểu rõ ba vai trò này, có thể ghép chúng thành pipeline xử lý JSON hiệu quả hoặc dùng chúng làm nền cho tầng ánh xạ object của Jackson Databind.
