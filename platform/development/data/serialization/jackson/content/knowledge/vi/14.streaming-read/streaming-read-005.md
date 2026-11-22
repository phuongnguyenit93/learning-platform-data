# Quản lý trạng thái khi đọc đối tượng và mảng lồng nhau

Khi JSON chỉ có một object phẳng, việc đọc bằng Jackson Streaming API khá đơn giản: parser lần lượt trả về tên trường và giá trị tương ứng. Nhưng payload thực tế thường có object bên trong object, array chứa object hoặc array lồng nhiều tầng. Khi đó, parser vẫn phát token theo thứ tự, còn chương trình phải theo dõi mình đang ở trong container nào, đang đọc property nào và khi nào một object hoặc array đã kết thúc.

Đây là bài toán **quản lý trạng thái khi đọc JSON lồng nhau**. Trong Jackson Core, `JsonParser` cung cấp luồng token và parsing context. Ứng dụng có thể dùng đệ quy để đi theo cấu trúc JSON, hoặc dùng stack để quản lý trạng thái tường minh khi cần xử lý tuần tự một cấu trúc sâu hoặc lớn.

## 1. JSON lồng nhau được đọc thành một chuỗi token

Giả sử đầu vào là một đơn hàng:

```json
{
  "orderId": "ORD-1001",
  "customer": {
    "name": "An",
    "active": true
  },
  "items": [
    { "sku": "BK-01", "quantity": 2 },
    { "sku": "PN-02", "quantity": 5 }
  ]
}
```

JSON có cấu trúc cây, nhưng `JsonParser` đọc theo luồng. Parser không trả về toàn bộ cây cùng lúc; mỗi lần gọi `nextToken()` sẽ chuyển đến token kế tiếp.

Chuỗi token khái quát có dạng:

```text
START_OBJECT
  FIELD_NAME "orderId"
  VALUE_STRING "ORD-1001"
  FIELD_NAME "customer"
  START_OBJECT
    FIELD_NAME "name"
    VALUE_STRING "An"
    FIELD_NAME "active"
    VALUE_TRUE
  END_OBJECT
  FIELD_NAME "items"
  START_ARRAY
    START_OBJECT
      FIELD_NAME "sku"
      VALUE_STRING "BK-01"
      FIELD_NAME "quantity"
      VALUE_NUMBER_INT 2
    END_OBJECT
    START_OBJECT
      FIELD_NAME "sku"
      VALUE_STRING "PN-02"
      FIELD_NAME "quantity"
      VALUE_NUMBER_INT 5
    END_OBJECT
  END_ARRAY
END_OBJECT
```

Các token mở và đóng (`START_OBJECT`, `END_OBJECT`, `START_ARRAY`, `END_ARRAY`) cho biết ranh giới của container. `FIELD_NAME` cho biết tên property của object hiện tại. Token giá trị cho biết kiểu dữ liệu thực tế.

Khi đi vào `customer`, parser gặp `START_OBJECT`; khi đọc xong customer, parser gặp `END_OBJECT` và quay lại object cha. Tương tự, khi đi vào `items`, parser gặp `START_ARRAY`; mỗi `START_OBJECT` bên trong array mở một phần tử object mới. Việc nhận biết đúng các ranh giới này là nền tảng để không nhầm field của object con với field của object cha.

## 2. Vòng đời cơ bản của JsonParser

Một parser thường được sử dụng theo mẫu:

```java
try (JsonParser parser = factory.createParser(input)) {
    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        // Xử lý token hiện tại.
    }
}
```

`nextToken()` vừa di chuyển parser vừa trả về token mới. Khi hết input, phương thức trả về `null`. `currentToken()` cho biết token hiện tại mà parser đang đứng.

Các token quan trọng khi đọc object và array:

| Token | Ý nghĩa |
| --- | --- |
| `START_OBJECT` | Bắt đầu một JSON object `{` |
| `END_OBJECT` | Kết thúc object `}` |
| `START_ARRAY` | Bắt đầu một JSON array `[` |
| `END_ARRAY` | Kết thúc array `]` |
| `FIELD_NAME` | Tên một property trong object |
| `VALUE_STRING` | Giá trị string |
| `VALUE_NUMBER_INT` | Giá trị số nguyên |
| `VALUE_NUMBER_FLOAT` | Giá trị số thập phân hoặc số mũ |
| `VALUE_TRUE`, `VALUE_FALSE` | Giá trị boolean |
| `VALUE_NULL` | JSON null |
| `VALUE_EMBEDDED_OBJECT` | Giá trị nhúng, tùy format/parser |

Trong một object, trình tự thường là `FIELD_NAME` rồi đến token biểu diễn value. Value có thể là scalar, `START_OBJECT` hoặc `START_ARRAY`. Trong array, không có `FIELD_NAME`; mỗi phần tử bắt đầu bằng token giá trị hoặc token mở container.

## 3. Quy tắc trạng thái khi đọc object

Khi parser đang ở trong object, chương trình cần theo dõi property hiện tại. Quy trình cơ bản:

1. Đọc token tiếp theo.
2. Nếu token là `END_OBJECT`, object hiện tại đã kết thúc.
3. Nếu token là `FIELD_NAME`, lấy tên trường bằng `getCurrentName()`.
4. Gọi `nextToken()` lần nữa để đến value của trường.
5. Nếu value là scalar, xử lý ngay.
6. Nếu value là `START_OBJECT` hoặc `START_ARRAY`, chuyển sang xử lý container con.

Ví dụ đọc một object phẳng:

```java
while (parser.nextToken() != JsonToken.END_OBJECT) {
    String fieldName = parser.getCurrentName();
    JsonToken valueToken = parser.nextToken();

    if ("orderId".equals(fieldName) && valueToken == JsonToken.VALUE_STRING) {
        String orderId = parser.getText();
        System.out.println(orderId);
    } else {
        parser.skipChildren();
    }
}
```

Đoạn code này giả định parser hiện đang đứng tại `START_OBJECT` và object có cấu trúc hợp lệ. `skipChildren()` bỏ qua toàn bộ nội dung nếu value hiện tại là object hoặc array. Nó giúp giữ parser ở đúng ranh giới để vòng lặp tiếp tục với property kế tiếp.

Không nên gọi `nextToken()` tùy tiện nhiều lần mà không xác định token hiện tại, vì một lần gọi dư có thể bỏ qua value hoặc token đóng container cần xử lý.

## 4. Quy tắc trạng thái khi đọc array

Trong array, parser không trả về tên trường. Mỗi lần `nextToken()` chuyển đến phần tử kế tiếp. Phần tử có thể là scalar, object hoặc một array khác.

Ví dụ đọc một array số:

```java
if (parser.nextToken() == JsonToken.START_ARRAY) {
    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() == JsonToken.VALUE_NUMBER_INT) {
            int value = parser.getIntValue();
            System.out.println(value);
        } else {
            parser.skipChildren();
        }
    }
}
```

Với array chứa object, khi gặp `START_OBJECT`, cần chuyển sang logic đọc object con. Khi object con kết thúc, parser đã đứng tại `END_OBJECT`; vòng lặp array tiếp tục gọi `nextToken()` để đọc phần tử kế tiếp.

Ví dụ, với `items` trong payload đơn hàng, trình tự bên trong array là:

```text
START_ARRAY
  START_OBJECT ... END_OBJECT
  START_OBJECT ... END_OBJECT
END_ARRAY
```

Array chỉ kết thúc khi gặp `END_ARRAY` ở đúng mức lồng hiện tại. Nếu chỉ kiểm tra `END_OBJECT` hoặc không phân biệt độ sâu, chương trình có thể dừng sai vị trí.

## 5. Cách dễ quản lý nhất: dùng hàm đệ quy theo container

Với JSON lồng nhau, cách tổ chức code rõ ràng là tách hàm đọc object, array và value. Mỗi hàm có một hợp đồng trạng thái:

- `readObject()` được gọi khi parser đang đứng tại `START_OBJECT`; hàm đọc đến và tiêu thụ `END_OBJECT` tương ứng.
- `readArray()` được gọi khi parser đang đứng tại `START_ARRAY`; hàm đọc đến và tiêu thụ `END_ARRAY` tương ứng.
- `readValue()` được gọi khi parser đang đứng tại token bắt đầu của một value; nếu value là container, nó gọi hàm phù hợp.

Ví dụ sau duyệt toàn bộ cấu trúc và in đường dẫn của từng giá trị scalar:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.IOException;

public class NestedJsonReader {
    public static void readValue(JsonParser parser, String path) throws IOException {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.START_OBJECT) {
            readObject(parser, path);
        } else if (token == JsonToken.START_ARRAY) {
            readArray(parser, path);
        } else {
            printScalar(parser, path, token);
        }
    }

    private static void readObject(JsonParser parser, String path) throws IOException {
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            if (parser.currentToken() == null) {
                throw new IOException("JSON kết thúc khi object chưa đóng");
            }

            if (parser.currentToken() != JsonToken.FIELD_NAME) {
                throw new IOException("Token mong đợi trong object phải là FIELD_NAME");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            if (valueToken == null) {
                throw new IOException("Thiếu value cho field " + fieldName);
            }

            String childPath = path.isEmpty()
                    ? fieldName
                    : path + "." + fieldName;

            readValue(parser, childPath);
        }
    }

    private static void readArray(JsonParser parser, String path) throws IOException {
        int index = 0;

        while (parser.nextToken() != JsonToken.END_ARRAY) {
            if (parser.currentToken() == null) {
                throw new IOException("JSON kết thúc khi array chưa đóng");
            }

            String childPath = path + "[" + index + "]";
            readValue(parser, childPath);
            index++;
        }
    }

    private static void printScalar(JsonParser parser,
                                    String path,
                                    JsonToken token) throws IOException {
        if (token == JsonToken.VALUE_STRING) {
            System.out.println(path + " = " + parser.getText());
        } else if (token == JsonToken.VALUE_NUMBER_INT
                || token == JsonToken.VALUE_NUMBER_FLOAT) {
            System.out.println(path + " = " + parser.getNumberValue());
        } else if (token == JsonToken.VALUE_TRUE || token == JsonToken.VALUE_FALSE) {
            System.out.println(path + " = " + parser.getBooleanValue());
        } else if (token == JsonToken.VALUE_NULL) {
            System.out.println(path + " = null");
        } else {
            throw new IOException("Token value không được hỗ trợ: " + token);
        }
    }
}
```

Điểm quan trọng là `readValue()` không gọi `nextToken()` trước khi xử lý value. Caller đã di chuyển parser đến token đầu tiên của value. Nếu value là object hoặc array, hàm con chịu trách nhiệm tiêu thụ toàn bộ container, bao gồm token đóng. Khi hàm con trả về, parser đứng ở `END_OBJECT` hoặc `END_ARRAY` của container vừa đọc; caller tiếp tục bằng lần gọi `nextToken()` tiếp theo.

Với JSON đơn hàng, kết quả đường dẫn có dạng:

```text
orderId = ORD-1001
customer.name = An
customer.active = true
items[0].sku = BK-01
items[0].quantity = 2
items[1].sku = PN-02
items[1].quantity = 5
```

Đệ quy phản ánh trực tiếp cấu trúc cây và thường dễ hiểu cho payload có độ sâu vừa phải. Với dữ liệu không tin cậy hoặc có thể lồng rất sâu, cần giới hạn độ sâu để tránh stack overflow.

## 6. Quản lý trạng thái bằng stack tường minh

Đệ quy dùng call stack của Java để nhớ container cha trong khi xử lý container con. Nếu muốn tự kiểm soát trạng thái, có thể dùng `Deque` làm stack các frame.

Mỗi frame đại diện cho một container đang mở và có thể giữ:

- Loại container: object hay array.
- Đường dẫn đến container.
- Tên field đang chờ value đối với object.
- Index phần tử tiếp theo đối với array.

Ví dụ cấu trúc frame:

```java
enum ContainerKind {
    OBJECT,
    ARRAY
}

class Frame {
    final ContainerKind kind;
    final String path;
    String pendingField;
    int nextIndex;

    Frame(ContainerKind kind, String path) {
        this.kind = kind;
        this.path = path;
    }
}
```

Khi parser gặp `START_OBJECT` hoặc `START_ARRAY`, chương trình tạo frame tương ứng và push vào stack. Khi gặp `END_OBJECT` hoặc `END_ARRAY`, chương trình pop frame trên cùng. Nhờ đó, frame trên đỉnh luôn đại diện cho container hiện tại.

Sơ đồ trạng thái:

```text
Đọc token
   │
   ├── START_OBJECT ──> push frame OBJECT
   │
   ├── START_ARRAY  ──> push frame ARRAY
   │
   ├── FIELD_NAME   ──> lưu pendingField ở frame OBJECT
   │
   ├── VALUE_*      ──> xác định path từ frame trên cùng, xử lý value
   │
   ├── END_OBJECT   ──> kiểm tra frame OBJECT rồi pop
   │
   └── END_ARRAY    ──> kiểm tra frame ARRAY rồi pop
```

Một triển khai stack cần cẩn thận với việc xác định đường dẫn của container con. Khi object cha có `pendingField = "customer"` và token kế tiếp là `START_OBJECT`, đường dẫn frame con là `customer`. Khi array cha mở một phần tử object, đường dẫn frame con là `items[0]`, sau đó tăng index của frame array cha.

Ví dụ xử lý trạng thái ở mức khái quát:

```java
Deque<Frame> stack = new ArrayDeque<>();

while (parser.nextToken() != null) {
    JsonToken token = parser.currentToken();

    if (token == JsonToken.FIELD_NAME) {
        Frame current = stack.peek();
        if (current == null || current.kind != ContainerKind.OBJECT) {
            throw new IOException("FIELD_NAME không nằm trong object");
        }
        current.pendingField = parser.currentName();
        continue;
    }

    if (token == JsonToken.START_OBJECT || token == JsonToken.START_ARRAY) {
        String childPath = nextValuePath(stack);
        ContainerKind kind = token == JsonToken.START_OBJECT
                ? ContainerKind.OBJECT
                : ContainerKind.ARRAY;
        stack.push(new Frame(kind, childPath));
        continue;
    }

    if (token == JsonToken.END_OBJECT || token == JsonToken.END_ARRAY) {
        // Kiểm tra loại frame tương ứng rồi pop.
        closeCurrentFrame(stack, token);
        continue;
    }

    // Token scalar: lấy đường dẫn từ frame trên cùng rồi xử lý.
    String valuePath = nextValuePath(stack);
    processScalar(parser, valuePath, token);
}
```

`nextValuePath`, `closeCurrentFrame` và `processScalar` là các hàm hỗ trợ cần được triển khai theo quy ước frame của ứng dụng; đoạn trên minh họa cách phân chia trách nhiệm. Điểm mấu chốt của stack là mỗi token được diễn giải trong ngữ cảnh container đang mở, không chỉ dựa vào tên field toàn cục.

## 7. Dùng JsonStreamContext để quan sát ngữ cảnh parser

Jackson duy trì parsing context nội bộ và cho phép truy cập qua `parser.getParsingContext()`. Context hiện tại mô tả vị trí parser trong cấu trúc JSON, ví dụ đang ở object hay array, tên field hiện tại, index array và context cha.

Ví dụ quan sát context:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonStreamContext;
import com.fasterxml.jackson.core.JsonToken;

while (parser.nextToken() != null) {
    JsonToken token = parser.currentToken();
    JsonStreamContext context = parser.getParsingContext();

    System.out.printf(
            "token=%s, inObject=%s, inArray=%s, name=%s, index=%d%n",
            token,
            context.inObject(),
            context.inArray(),
            context.getCurrentName(),
            context.getCurrentIndex()
    );
}
```

`JsonStreamContext` hữu ích để debug hoặc xây dựng logic phụ thuộc vị trí hiện tại. Tuy nhiên, không nên nhầm parser context với trạng thái nghiệp vụ của ứng dụng. Context cho biết parser đang ở đâu trong cấu trúc JSON; ứng dụng vẫn cần tự quyết định field nào cần lưu, array nào cần xử lý và dữ liệu nào cần kiểm tra.

Khi token là `FIELD_NAME`, parser đang ở trong object và `getCurrentName()` trả tên field. Khi token là value hoặc container con, context có thể vẫn cho biết tên field mà value đó thuộc về. Với array, `getCurrentIndex()` cung cấp index hiện tại theo context. Cách dùng chính xác nên được xác nhận bằng token flow của cấu trúc mà ứng dụng xử lý.

## 8. skipChildren(): bỏ qua container con mà không mất đồng bộ

Không phải lúc nào ứng dụng cũng cần đọc toàn bộ object hoặc array con. Nếu parser đang đứng tại `START_OBJECT` hoặc `START_ARRAY`, `skipChildren()` sẽ bỏ qua toàn bộ nội dung lồng nhau và đặt parser ở token kết thúc container tương ứng.

Ví dụ chỉ cần đọc `orderId`, bỏ qua các field khác:

```java
if (parser.nextToken() == JsonToken.START_OBJECT) {
    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("orderId".equals(fieldName) && valueToken == JsonToken.VALUE_STRING) {
            String orderId = parser.getText();
            System.out.println(orderId);
        } else {
            parser.skipChildren();
        }
    }
}
```

Nếu field không quan tâm chứa một object hoặc array nhiều tầng, `skipChildren()` giúp parser đi qua toàn bộ nhánh đó. Nếu value là scalar, phương thức không làm mất token tiếp theo. Đây là cách hữu ích để bỏ qua metadata lớn hoặc phần payload mà consumer không cần.

Không gọi `skipChildren()` trước khi xử lý value cần giữ lại. Sau khi skip một container, parser đã ở token đóng container đó; vòng lặp nên tiếp tục gọi `nextToken()` theo đúng cấu trúc cha.

## 9. Phân biệt parser state với application state

Một lỗi thiết kế phổ biến là dùng một biến `currentField` toàn cục cho mọi cấp object. Ví dụ, object cha và object con đều có trường tên `id`. Nếu biến này bị ghi đè khi đi vào object con, ứng dụng có thể không biết tên field đó thuộc cấp nào.

Với JSON:

```json
{
  "id": "ORDER-1",
  "customer": {
    "id": "CUSTOMER-9"
  }
}
```

Hai trường `id` có cùng tên nhưng thuộc hai object khác nhau. Chỉ giữ `currentField = "id"` không đủ để phân biệt chúng. Cần có đường dẫn như `id` và `customer.id`, hoặc lưu frame riêng cho từng object.

Hãy phân biệt:

- **Parser state:** token hiện tại, vị trí trong luồng, parsing context và ranh giới container.
- **Application state:** dữ liệu đã đọc, đối tượng nghiệp vụ đang xây dựng, đường dẫn field, index và quy tắc xử lý.

Parser quản lý luồng token. Ứng dụng quản lý ý nghĩa của token trong nghiệp vụ. Việc trộn hai loại trạng thái vào một vài biến đơn giản thường dẫn đến lỗi khi có object/array lồng nhau.

## 10. Xây dựng object Java từ luồng lồng nhau

Nếu mục tiêu là tạo DTO hoàn chỉnh, thường không cần tự viết parser state machine. `ObjectMapper`/`ObjectReader` đã có cơ chế databinding để xử lý object và array lồng nhau.

Ví dụ DTO:

```java
public record Customer(String name, boolean active) {}

public record OrderItem(String sku, int quantity) {}

public record Order(
        String orderId,
        Customer customer,
        List<OrderItem> items
) {}
```

Đọc JSON:

```java
Order order = mapper.readValue(json, Order.class);
```

Jackson tự xử lý trạng thái object/array và ánh xạ các tầng lồng nhau vào property tương ứng. Streaming API phù hợp hơn khi payload rất lớn, cấu trúc động, hoặc ứng dụng chỉ cần xử lý một phần dữ liệu mà không muốn tạo toàn bộ object graph.

## 11. Xử lý array rất lớn theo từng phần tử

Một trường hợp quan trọng là JSON có array chứa hàng trăm nghìn hoặc hàng triệu object. Nếu đọc toàn bộ thành `List<Order>`, toàn bộ object graph phải nằm trong bộ nhớ. Với streaming, có thể đọc từng object rồi xử lý ngay.

Ví dụ JSON cấp gốc là một array:

```json
[
  { "id": "ORD-1", "amount": 10.50 },
  { "id": "ORD-2", "amount": 20.00 },
  { "id": "ORD-3", "amount": 30.00 }
]
```

Có thể dùng `ObjectReader.readValue(parser)` để bind từng phần tử khi parser đang đứng tại `START_OBJECT`:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectReader;

ObjectReader orderReader = mapper.readerFor(Order.class);

try (JsonParser parser = mapper.getFactory().createParser(input)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Root phải là array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw new IOException("Mỗi phần tử phải là object");
        }

        Order order = orderReader.readValue(parser);
        processOrder(order);
    }
}
```

`readValue(parser)` đọc một value bắt đầu tại token hiện tại. Nếu value là object, databind tiêu thụ object đó đến hết; khi trả về, parser sẵn sàng để vòng lặp đọc phần tử kế tiếp. Cách này kết hợp streaming ở cấp array với databinding cho từng phần tử, giúp không phải giữ toàn bộ danh sách trong bộ nhớ.

## 12. Lỗi thường gặp khi quản lý trạng thái

### 12.1. Quên rằng FIELD_NAME chưa phải value

Sau `FIELD_NAME`, parser vẫn chưa đứng ở value. Cần gọi `nextToken()` để đến value trước khi dùng `getText()`, `getIntValue()` hoặc gọi hàm đọc container con.

### 12.2. Gọi nextToken() hai lần và bỏ qua dữ liệu

Nếu vừa gọi `nextToken()` để lấy value rồi lại gọi thêm lần nữa trước khi xử lý, token value có thể bị bỏ qua. Hãy xác định rõ hàm nào chịu trách nhiệm di chuyển parser.

### 12.3. Dừng ở END_OBJECT sai cấp

Trong JSON lồng nhau có nhiều `END_OBJECT`. Hàm đọc object con phải tiêu thụ đúng token đóng của object con; vòng lặp cha chỉ dừng khi gặp token đóng ở cấp của nó. Đệ quy hoặc stack giúp phân biệt các cấp.

### 12.4. Quên tăng index của array

Khi tạo đường dẫn như `items[0]`, `items[1]`, index phải tăng sau mỗi phần tử, kể cả phần tử là object, array hay scalar. Nếu tăng sai thời điểm, đường dẫn có thể trùng hoặc lệch.

### 12.5. Không xử lý VALUE_NULL

JSON null là một token value. Không phải mọi field đều có thể chuyển sang string hoặc number. Hãy xử lý `VALUE_NULL` riêng nếu null có ý nghĩa nghiệp vụ.

### 12.6. Bỏ qua token container nhưng không đồng bộ lại vòng lặp

Khi dùng `skipChildren()` hoặc hàm đệ quy, hãy nhớ parser đã được di chuyển đến token đóng container. Caller phải tiếp tục từ vị trí đó, không tự giả định parser vẫn đứng ở `START_OBJECT` hoặc `START_ARRAY`.

## 13. Giới hạn độ sâu và input không tin cậy

JSON có thể được gửi từ client hoặc hệ thống bên ngoài. Một payload lồng quá sâu có thể làm hàm đệ quy sử dụng nhiều call stack, hoặc làm parser tốn tài nguyên. Với Jackson phiên bản hỗ trợ `StreamReadConstraints`, có thể đặt giới hạn độ sâu nesting và các giới hạn đọc phù hợp:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;

JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNestingDepth(100)
                        .build()
        )
        .build();
```

Giá trị giới hạn cần dựa trên hợp đồng dữ liệu và phiên bản Jackson đang dùng. Ngoài nesting depth, hệ thống nên giới hạn kích thước request, độ dài string/number và số phần tử nếu payload có thể gây tiêu tốn tài nguyên. Đừng tăng giới hạn chỉ để chấp nhận payload bất thường mà chưa hiểu lý do.

## 14. Chọn đệ quy, stack hay databinding?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| JSON lồng nhau có độ sâu vừa phải, cần xử lý mọi node | Hàm đệ quy theo object/array |
| Cần tự kiểm soát đường dẫn và trạng thái từng cấp | Stack frame với `Deque` |
| Chỉ cần bỏ qua một nhánh object/array | `skipChildren()` |
| Cần tạo DTO hoàn chỉnh theo schema rõ ràng | `ObjectMapper`/`ObjectReader` |
| Array rất lớn, xử lý từng phần tử | Streaming parser kết hợp databinding từng phần tử |
| Cần quan sát vị trí parser để debug | `getParsingContext()` / `JsonStreamContext` |

Không có một cách duy nhất phù hợp cho mọi payload. Đệ quy dễ đọc, stack tường minh linh hoạt, databinding giảm code thủ công và streaming từng phần tử giúp kiểm soát bộ nhớ.

## 15. Ghi nhớ

- `JsonParser` đọc JSON theo chuỗi token; `nextToken()` di chuyển đến token kế tiếp.
- Trong object, `FIELD_NAME` đứng trước token value; value có thể là scalar, object hoặc array.
- `START_OBJECT`/`END_OBJECT` và `START_ARRAY`/`END_ARRAY` đánh dấu ranh giới container ở từng cấp.
- Khi đọc lồng nhau, cần giữ trạng thái riêng cho mỗi cấp; không dùng một biến tên field toàn cục để đại diện mọi object.
- Đệ quy phù hợp khi cấu trúc cây cần được duyệt tự nhiên; stack phù hợp khi muốn quản lý frame tường minh.
- `JsonStreamContext` cho biết vị trí hiện tại của parser; `skipChildren()` bỏ qua một container con và giữ parser đồng bộ.
- Có thể kết hợp streaming với `ObjectReader` để đọc từng phần tử của array lớn thành DTO mà không giữ cả danh sách.
- Với JSON không tin cậy, giới hạn độ sâu nesting và kích thước payload để tránh tiêu tốn tài nguyên.

Khi viết code streaming cho JSON lồng nhau, hãy xác định rõ mỗi hàm bắt đầu ở token nào, hàm tiêu thụ đến token nào và ai chịu trách nhiệm gọi `nextToken()` tiếp theo. Quy ước trạng thái rõ ràng giúp tránh bỏ sót value, dừng sai cấp và gán nhầm field giữa object cha với object con.
