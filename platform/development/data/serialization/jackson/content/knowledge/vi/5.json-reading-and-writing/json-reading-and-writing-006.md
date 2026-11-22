# Phân biệt tài liệu JSON rỗng, giá trị `null` và dữ liệu đầu vào không có

## 1. Vì sao cần phân biệt ba trạng thái?

Khi một ứng dụng nhận dữ liệu JSON, có những trường hợp thoạt nhìn đều giống như “không có dữ liệu”: request không gửi body, body có độ dài bằng không, body chỉ chứa khoảng trắng, hoặc body chứa giá trị JSON `null`. Tuy nhiên, đây là những trạng thái khác nhau ở các tầng khác nhau của chương trình.

Trong Jackson, sự khác biệt này đặc biệt quan trọng khi dùng `ObjectMapper.readTree(...)` để đọc JSON thành `JsonNode`. Nếu gộp mọi trường hợp thành một giá trị `null` của Java, chương trình có thể bỏ qua một request bị thiếu, hiểu nhầm một tài liệu JSON rỗng là giá trị JSON `null`, hoặc đánh mất ý nghĩa của một thuộc tính được gửi rõ ràng với giá trị `null`.

Ba khái niệm cần tách bạch:

1. **Dữ liệu đầu vào không có (missing input):** tầng ứng dụng không nhận được dữ liệu để phân tích, chẳng hạn request không có body hoặc biến đầu vào chưa được cung cấp. Đây là trạng thái của giao tiếp hoặc chương trình, không phải một giá trị trong cú pháp JSON.
2. **Tài liệu JSON rỗng (empty JSON document):** có một chuỗi đầu vào nhưng chuỗi đó không chứa token JSON nào. Chuỗi có thể có độ dài bằng không hoặc chỉ gồm khoảng trắng hợp lệ của JSON.
3. **Giá trị JSON `null`:** tài liệu có nội dung là token `null`. Đây là một giá trị JSON hợp lệ và Jackson biểu diễn nó bằng `NullNode`.

Ngoài ba trạng thái trên, còn có những trường hợp dễ nhầm như object rỗng `{}`, array rỗng `[]`, chuỗi rỗng `""`, thuộc tính không xuất hiện trong object và tài liệu JSON sai cú pháp. Chúng cần được nhận diện riêng.

## 2. Nhìn từ cú pháp JSON

Một JSON text phải chứa một giá trị JSON. Giá trị đó có thể là object, array, string, number, boolean hoặc `null`. Khoảng trắng có thể xuất hiện trước hoặc sau giá trị, nhưng khoảng trắng không tự tạo thành một giá trị.

| Nội dung đầu vào | Có phải JSON text chứa một giá trị? | Giá trị gốc |
|---|---|---|
| Chuỗi độ dài 0: `` | Không | Không có root value |
| Chỉ có dấu cách hoặc xuống dòng | Không | Không có root value |
| `null` | Có | Giá trị null |
| `{}` | Có | Object rỗng |
| `[]` | Có | Array rỗng |
| `""` | Có | String rỗng |
| `0` | Có | Number bằng 0 |
| `false` | Có | Boolean false |
| `{` | Không | Tài liệu không hợp lệ, thiếu phần còn lại |

Điểm cần nhớ là **rỗng về mặt văn bản không đồng nghĩa với một giá trị JSON rỗng**. Object rỗng và array rỗng vẫn là những giá trị hoàn chỉnh. Ngược lại, tài liệu không có token nào thì chưa cung cấp một giá trị để Jackson tạo node gốc.

JSON cũng cho phép giá trị scalar ở cấp gốc. Vì vậy, `null`, `"hello"`, `42` và `true` đều có thể là toàn bộ nội dung của một tài liệu JSON; không bắt buộc root phải là object.

## 3. Jackson biểu diễn các trạng thái như thế nào?

Với Tree Model, `ObjectMapper.readTree(...)` trả về node gốc của tài liệu. Hành vi quan trọng cần ghi nhớ trong Jackson Databind là:

- Nếu parser không tìm thấy nội dung JSON nào, chẳng hạn đầu vào rỗng hoặc chỉ có khoảng trắng, `readTree(...)` trả về `null` của Java vì không có node gốc.
- Nếu nội dung là token JSON `null`, `readTree(...)` trả về một đối tượng `NullNode`.
- Nếu nội dung là `{}`, Jackson trả về `ObjectNode` không có thuộc tính.
- Nếu nội dung là `[]`, Jackson trả về `ArrayNode` không có phần tử.
- Nếu nội dung là `""`, Jackson trả về `TextNode` chứa chuỗi có độ dài bằng không.
- Nếu nội dung không đúng cú pháp JSON, Jackson ném ngoại lệ thuộc nhóm `JsonProcessingException` thay vì coi dữ liệu sai cú pháp là tài liệu rỗng.

Bảng sau tổng hợp loại kết quả thường thấy:

| Đầu vào | Kết quả từ `readTree` | Cách nhận biết |
|---|---|---|
| `""` theo nghĩa chuỗi Java không có ký tự | `null` Java | `root == null` |
| `"  \n\t"` | `null` Java | `root == null` |
| `"null"` | `NullNode` | `root.isNull()` |
| `"{}"` | `ObjectNode` | `root.isObject()` và `root.size() == 0` |
| `"[]"` | `ArrayNode` | `root.isArray()` và `root.size() == 0` |
| `"\"\""` | `TextNode` | `root.isTextual()` và `root.asText().isEmpty()` |
| `"{"` | Ngoại lệ phân tích | Bắt `JsonProcessingException` |

Trong bảng, chuỗi Java được viết theo dạng escape để phân biệt rõ chuỗi Java với nội dung JSON mà nó chứa. Ví dụ, chuỗi Java `"null"` chứa bốn ký tự `n`, `u`, `l`, `l`, tức là một tài liệu có giá trị JSON null. Chuỗi Java `""` không chứa ký tự nào, tức là không có tài liệu JSON.

### `null` của Java và `NullNode` không giống nhau

Đây là khác biệt quan trọng nhất khi đọc JSON thành cây:

```java
JsonNode absentRoot = mapper.readTree("");
JsonNode nullRoot = mapper.readTree("null");

System.out.println(absentRoot == null); // true
System.out.println(nullRoot == null);   // false
System.out.println(nullRoot.isNull());  // true
```

`absentRoot` không tham chiếu đến một node nào. `nullRoot` là một đối tượng node có kiểu cụ thể, biểu diễn giá trị JSON null. Vì vậy, điều kiện `root == null` và `root.isNull()` trả lời hai câu hỏi khác nhau.

Không nên gọi `root.isNull()` trước khi kiểm tra `root != null`, bởi nếu tài liệu không có root node thì biến `root` là tham chiếu Java null và lời gọi phương thức sẽ gây `NullPointerException`.

## 4. Dữ liệu đầu vào không có nằm ở tầng nào?

Jackson phân tích nội dung được cung cấp cho parser. Việc một nguồn dữ liệu có cung cấp nội dung hay không thường phải được xác định trước đó, tại tầng gọi hàm, tầng đọc file hoặc tầng giao tiếp HTTP.

Ví dụ, một API có thể phân biệt:

- Request không gửi body: tầng HTTP hoặc framework biểu diễn body là không có.
- Request gửi body có độ dài 0: có body nhưng không có byte nội dung.
- Request gửi body chứa `null`: có nội dung JSON và giá trị gốc là null.
- Request gửi body chứa `{}`: có nội dung JSON và giá trị gốc là object rỗng.

Không nên tự động quy định rằng mọi framework đều ánh xạ các tình huống này thành cùng một kiểu Java. Tùy API, một body không có có thể được biểu diễn bằng `null`, `Optional.empty()`, một trạng thái riêng hoặc một đối tượng request không có entity. Hãy xem hợp đồng của tầng nhận dữ liệu để xác định trạng thái thực tế.

Khi viết hàm nhận chuỗi, một tham chiếu `String` bằng `null` cũng là dữ liệu đầu vào không được cung cấp ở tầng Java. Nó khác với chuỗi chứa bốn ký tự `null`. Nên kiểm tra tham chiếu trước khi gọi Jackson và quyết định rõ ứng dụng sẽ xử lý trạng thái này ra sao.

Ví dụ, nếu một endpoint yêu cầu body bắt buộc, request không có body có thể phải bị từ chối ở tầng API. Nếu body là tùy chọn, ứng dụng có thể bỏ qua bước phân tích và giữ trạng thái “không được cung cấp”. Jackson không tự quyết định quy tắc nghiệp vụ đó.

## 5. Viết hàm phân loại đầu vào rõ ràng

Một cách an toàn là biểu diễn kết quả phân tích bằng một trạng thái riêng, thay vì chỉ trả về `JsonNode` và buộc nơi gọi suy đoán ý nghĩa của `null`.

Ví dụ sau dùng Java 17. Hàm `classifyInput` phân biệt đầu vào không được cung cấp, tài liệu rỗng, JSON null và một giá trị JSON thông thường:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

enum InputKind {
    MISSING_INPUT,
    EMPTY_DOCUMENT,
    JSON_NULL,
    JSON_VALUE
}

record ParseOutcome(InputKind kind, JsonNode root) {
}

public class JsonInputClassifier {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static ParseOutcome classifyInput(String input)
            throws JsonProcessingException {

        // null ở đây là tham chiếu Java, nghĩa là bên gọi không cung cấp chuỗi.
        if (input == null) {
            return new ParseOutcome(InputKind.MISSING_INPUT, null);
        }

        // Không có token JSON nào nếu chuỗi rỗng hoặc chỉ có JSON whitespace.
        if (containsOnlyJsonWhitespace(input)) {
            return new ParseOutcome(InputKind.EMPTY_DOCUMENT, null);
        }

        JsonNode root = MAPPER.readTree(input);

        // Giữ kiểm tra này để thể hiện rõ hợp đồng của readTree khi không có root.
        if (root == null) {
            return new ParseOutcome(InputKind.EMPTY_DOCUMENT, null);
        }

        if (root.isNull()) {
            return new ParseOutcome(InputKind.JSON_NULL, root);
        }

        return new ParseOutcome(InputKind.JSON_VALUE, root);
    }

    private static boolean containsOnlyJsonWhitespace(String input) {
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            if (c != ' ' && c != '\t' && c != '\n' && c != '\r') {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        String[] samples = {
                null,
                "",
                "  \n\t",
                "null",
                "{}",
                "[]",
                "\"\"",
                "false"
        };

        for (String sample : samples) {
            ParseOutcome outcome = classifyInput(sample);
            System.out.printf(
                    "input=%s -> kind=%s, root=%s%n",
                    sample,
                    outcome.kind(),
                    outcome.root()
            );
        }
    }
}
```

Hàm `containsOnlyJsonWhitespace` kiểm tra đúng bốn ký tự khoảng trắng mà cú pháp JSON cho phép: dấu cách, tab, xuống dòng và carriage return. Cách kiểm tra này giúp ví dụ bám sát cú pháp JSON. Nếu dùng `String.isBlank()`, Java còn nhận diện một số ký tự Unicode là khoảng trắng; một số ký tự đó không phải whitespace hợp lệ trong JSON và nên được để parser báo lỗi.

Trong `ParseOutcome`, trường `root` có thể là Java null ở hai trạng thái `MISSING_INPUT` và `EMPTY_DOCUMENT`. Trường `kind` giữ thông tin để phân biệt hai nguyên nhân. Với `JSON_NULL`, `root` là `NullNode`; với `JSON_VALUE`, `root` là node tương ứng với giá trị JSON đã đọc.

Nếu chuỗi không rỗng nhưng sai cú pháp, `MAPPER.readTree(input)` ném `JsonProcessingException`. Hàm không bắt rồi đổi ngoại lệ thành `EMPTY_DOCUMENT`, vì làm như vậy sẽ che giấu dữ liệu hỏng. Nơi gọi có thể bắt ngoại lệ để ghi log, trả lỗi đầu vào không hợp lệ hoặc áp dụng chính sách phù hợp với ứng dụng.

## 6. Phân biệt thuộc tính bị thiếu với thuộc tính có giá trị `null`

Sau khi đã có một `ObjectNode`, một vấn đề tương tự xuất hiện ở cấp thuộc tính. Ví dụ:

```json
{
  "name": "Lan",
  "middleName": null
}
```

Trong object trên, thuộc tính `middleName` tồn tại và có giá trị JSON null. Thuộc tính `phone` không xuất hiện. Hai trạng thái này khác nhau dù khi đọc bằng cách không kiểm tra kỹ, chương trình có thể vô tình xử lý chúng giống nhau.

Jackson cung cấp một số API để phân biệt:

| API | Thuộc tính không tồn tại | Thuộc tính tồn tại với JSON `null` | Thuộc tính có giá trị |
|---|---|---|---|
| `get("field")` | Trả về Java `null` | Trả về `NullNode` | Trả về node tương ứng |
| `path("field")` | Trả về `MissingNode` | Trả về `NullNode` | Trả về node tương ứng |
| `has("field")` | `false` | `true` | `true` |
| `hasNonNull("field")` | `false` | `false` | `true` |

Ví dụ:

```java
JsonNode user = MAPPER.readTree("""
        {
          "name": "Lan",
          "middleName": null
        }
        """);

JsonNode missingByGet = user.get("phone");
JsonNode missingByPath = user.path("phone");
JsonNode explicitNull = user.get("middleName");

System.out.println(missingByGet == null);          // true
System.out.println(missingByPath.isMissingNode()); // true
System.out.println(explicitNull.isNull());         // true
System.out.println(user.has("middleName"));       // true
System.out.println(user.hasNonNull("middleName"));// false
```

`MissingNode` là node đặc biệt do API cây dùng làm dấu hiệu cho đường dẫn không tồn tại. Nó không phải token `null` trong JSON. `NullNode` mới là node biểu diễn giá trị JSON null.

Sự khác biệt này có ý nghĩa khi cập nhật dữ liệu. Trong một API cập nhật hồ sơ, chẳng hạn:

- Không gửi `middleName`: có thể hiểu là không yêu cầu thay đổi trường này.
- Gửi `"middleName": null`: có thể hiểu là yêu cầu xóa giá trị hiện tại.
- Gửi `"middleName": "An"`: yêu cầu cập nhật thành một giá trị cụ thể.

Đây chỉ là một quy ước nghiệp vụ thường gặp; ứng dụng phải định nghĩa rõ hợp đồng của mình. Jackson giúp nhận diện trạng thái dữ liệu, còn quyết định cập nhật hay xóa thuộc về logic nghiệp vụ.

## 7. Đọc dữ liệu an toàn khi root có thể là bất kỳ kiểu JSON nào

Không phải mọi tài liệu JSON đều bắt đầu bằng object. Nếu chương trình cần object gốc, hãy kiểm tra loại node trước khi truy cập thuộc tính:

```java
JsonNode root = MAPPER.readTree(input);

if (root == null) {
    throw new IllegalArgumentException("JSON document is empty");
}

if (root.isNull()) {
    throw new IllegalArgumentException("Root JSON value must not be null");
}

if (!root.isObject()) {
    throw new IllegalArgumentException("Root JSON value must be an object");
}

JsonNode nameNode = root.path("name");
if (nameNode.isMissingNode()) {
    System.out.println("name was not provided");
} else if (nameNode.isNull()) {
    System.out.println("name was explicitly set to null");
} else if (nameNode.isTextual()) {
    System.out.println("name = " + nameNode.asText());
} else {
    throw new IllegalArgumentException("name must be a string or null");
}
```

Đoạn mã trên thể hiện ba lớp kiểm tra khác nhau:

1. Kiểm tra có node gốc hay không.
2. Kiểm tra kiểu của giá trị gốc có phù hợp với hợp đồng đầu vào hay không.
3. Kiểm tra thuộc tính cụ thể có bị thiếu, được gửi rõ ràng với null hay có kiểu dữ liệu hợp lệ hay không.

Không nên gọi `asText()` ngay trên một node chưa kiểm tra nếu chương trình cần phân biệt sai kiểu với giá trị hợp lệ. Các phương thức `as...` có thể chuyển đổi hoặc trả về giá trị mặc định; điều đó tiện cho một số trường hợp nhưng không thay thế kiểm tra dữ liệu đầu vào.

## 8. Ghi JSON: giá trị null, object rỗng và trường bị lược bỏ

Sự khác biệt giữa null và không có dữ liệu cũng quan trọng ở chiều ghi. Jackson có thể ghi một số trường hợp như sau:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

ObjectMapper mapper = new ObjectMapper();

String nullJson = mapper.writeValueAsString((Object) null);
String emptyObjectJson = mapper.writeValueAsString(mapper.createObjectNode());
String emptyArrayJson = mapper.writeValueAsString(mapper.createArrayNode());

System.out.println(nullJson);        // null
System.out.println(emptyObjectJson); // {}
System.out.println(emptyArrayJson);  // []
```

Ở đây, `nullJson` là một chuỗi có bốn ký tự `null`, tức là một tài liệu JSON hợp lệ chứa giá trị null. Nó không phải chuỗi Java null và cũng không phải body có độ dài bằng không.

Để tạo object có một thuộc tính null và một thuộc tính không tồn tại:

```java
ObjectNode response = mapper.createObjectNode();
response.put("name", "Lan");
response.putNull("middleName");
response.remove("phone");

String json = mapper.writeValueAsString(response);
System.out.println(json);
```

Kết quả có dạng:

```json
{"name":"Lan","middleName":null}
```

`putNull("middleName")` tạo một thuộc tính hiện diện với giá trị JSON null. `remove("phone")` bảo đảm thuộc tính `phone` không xuất hiện trong object. Không có thuộc tính `phone` trong kết quả vì object không chứa node tương ứng.

Nếu ứng dụng không có dữ liệu đầu vào, điều đó không tự động có nghĩa là cần gọi `writeValueAsString(null)`. Lời gọi này chủ động tạo ra văn bản JSON `null`. Việc có gửi body hay không là quyết định của tầng giao tiếp. Chẳng hạn, một endpoint có thể trả response không có entity, trong khi endpoint khác trả JSON `null`; hai hợp đồng đó không tương đương.

## 9. Chính sách xử lý ở ranh giới API

Một ứng dụng nên quy định rõ cách xử lý từng trạng thái trước khi gọi nghiệp vụ. Ví dụ, một endpoint cập nhật thông tin có thể chọn chính sách như sau:

| Trạng thái nhận được | Ví dụ | Một chính sách có thể áp dụng |
|---|---|---|
| Không có body | Framework không cung cấp nội dung | Trả lỗi yêu cầu thiếu body nếu body bắt buộc; bỏ qua nếu body tùy chọn |
| Body rỗng hoặc chỉ có whitespace | Không có byte/token JSON | Trả lỗi tài liệu JSON rỗng hoặc áp dụng quy tắc body rỗng đã công bố |
| Body là `null` | `null` | Chấp nhận hoặc từ chối theo schema/hợp đồng endpoint |
| Body là `{}` | Object không có trường | Có thể xem là request hợp lệ nhưng không có trường cập nhật, hoặc từ chối vì thiếu trường bắt buộc |
| Body chứa thuộc tính với null | `{"middleName":null}` | Có thể hiểu là yêu cầu xóa giá trị nếu hợp đồng quy định như vậy |
| Body sai cú pháp | `{"name":` | Trả lỗi JSON không hợp lệ; không coi như body rỗng |

Điều quan trọng là không dùng một nhánh xử lý duy nhất cho tất cả trường hợp `null` hoặc “empty”. Một thiết kế API rõ ràng nên nói được:

- Body có bắt buộc không?
- Root JSON phải là object hay được phép là scalar/array/null?
- Trường bị lược bỏ có khác trường được gửi với null không?
- Object rỗng có được chấp nhận không?
- JSON sai cú pháp được trả về lỗi nào?

Các quy tắc này nên được thực thi tại ranh giới đầu vào trước khi dữ liệu được truyền sâu vào logic nghiệp vụ. Nhờ vậy, các lớp bên trong không phải suy đoán liệu một `null` Java là do người dùng gửi JSON null, do thiếu body hay do một thuộc tính không tồn tại.

## 10. Các tình huống cần chú ý khi dùng Jackson

### Không dùng `root == null` để kết luận JSON chứa null

`root == null` sau `readTree` biểu thị không có node gốc, thường là tài liệu không có nội dung. JSON literal `null` được biểu diễn bởi `NullNode`, nên cần `root.isNull()` sau khi đã kiểm tra root không phải Java null.

### Không dùng `isEmpty()` để thay thế kiểm tra trạng thái đầu vào

Kiểm tra kích thước object hoặc array chỉ có ý nghĩa khi đã có node. `{}` và `[]` là hai node hợp lệ có kích thước bằng 0. Chúng không tương đương tài liệu không có root node.

### Không biến lỗi cú pháp thành dữ liệu rỗng

Một chuỗi như `{` hoặc `{"name":` có nội dung nhưng không phải JSON hoàn chỉnh. Hãy giữ ngoại lệ phân tích để tầng gọi nhận biết dữ liệu hỏng, thay vì bắt mọi lỗi rồi trả về trạng thái empty.

### Không truyền tham chiếu Java null như thể đó là JSON text

Nếu biến chuỗi body bằng Java null, hãy xử lý đó là trạng thái không có đầu vào theo hợp đồng của ứng dụng. Chỉ gọi Jackson khi đã có chuỗi nội dung cần phân tích.

### Không đánh đồng trường thiếu với trường null

Khi xử lý JSON object, dùng `get`, `path`, `has` hoặc `hasNonNull` phù hợp với câu hỏi cần trả lời. Nếu nghiệp vụ cần phân biệt “không cập nhật” với “xóa giá trị”, thông tin này phải được giữ lại trong bước chuyển đổi.

## 11. Kết luận

Trong Jackson, tài liệu JSON không có nội dung và tài liệu chứa giá trị JSON `null` được biểu diễn khác nhau: `readTree` trả về Java null khi không có node gốc, còn token `null` tạo ra `NullNode`. Dữ liệu đầu vào không được cung cấp còn thuộc tầng gọi hàm hoặc giao tiếp, nên cần được nhận diện trước khi phân tích. Ở cấp object, `MissingNode` biểu diễn đường dẫn không tồn tại, trong khi `NullNode` biểu diễn thuộc tính có mặt với giá trị null. Khi ghi, `null`, `{}`, `[]`, trường null và trường bị lược bỏ cũng tạo ra các kết quả JSON khác nhau. Giữ riêng những trạng thái này giúp chương trình xử lý request, cập nhật dữ liệu và thiết kế hợp đồng API chính xác hơn.
