# JSON encoding

## 1. Vì sao JSON encoding là một yêu cầu bảo mật?

Một API trả về JSON thường phải đưa dữ liệu do người dùng kiểm soát vào phản hồi: tên hiển thị, nội dung bình luận, tên sản phẩm, thông báo lỗi hoặc giá trị tìm kiếm. Những giá trị đó có thể chứa dấu nháy kép, dấu gạch chéo ngược, ký tự xuống dòng và cả chuỗi trông giống cú pháp JSON hoặc HTML.

Yêu cầu bảo mật không phải là cấm mọi ký tự đặc biệt. Yêu cầu đúng là dữ liệu phải tiếp tục được hiểu là **dữ liệu**, không được trở thành một phần cấu trúc tài liệu hoặc mã thực thi ngoài ý muốn.

Trong module yêu cầu bảo mật, JSON encoding cần được đặc tả bằng ba câu hỏi:

1. Dữ liệu được đưa vào ngữ cảnh nào: một phản hồi HTTP JSON độc lập hay JSON nằm trong một tài liệu HTML?
2. Thành phần nào chịu trách nhiệm biến đối tượng thành JSON và bảo toàn kiểu dữ liệu?
3. Có bằng chứng nào cho thấy các giá trị khó xử lý vẫn giữ nguyên ý nghĩa sau khi bên nhận phân tích cú pháp?

Một yêu cầu như “escape dữ liệu để chống injection” quá mơ hồ. Đặc tả tốt phải nêu được điểm xuất dữ liệu, cách tạo JSON, kiểu nội dung phản hồi, hành vi khi lỗi và các trường hợp nghiệm thu.

## 2. Phân biệt tài liệu JSON, chuỗi JSON và chuỗi trong chương trình

Xét đối tượng nghiệp vụ có hai thuộc tính:

```text
displayName = An "Blue"
department  = Security
```

Một tài liệu JSON biểu diễn đối tượng đó có thể là:

```json
{
  "displayName": "An \"Blue\"",
  "department": "Security"
}
```

Dấu `\"` thuộc cú pháp JSON. Sau khi parser đọc tài liệu, giá trị của `displayName` vẫn là `An "Blue"`, không phải một chuỗi chứa thêm dấu gạch chéo ngược trước mỗi dấu nháy.

Ba lớp biểu diễn thường bị nhầm lẫn:

| Lớp | Vai trò | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| Đối tượng hoặc giá trị nghiệp vụ | Chứa dữ liệu và kiểu mà ứng dụng muốn truyền | Trường này là chuỗi, số, boolean, danh sách hay đối tượng? |
| Văn bản JSON | Biểu diễn dữ liệu theo cú pháp JSON | Parser có đọc đúng cấu trúc và giá trị mong muốn không? |
| Literal trong Java, JavaScript hoặc ngôn ngữ khác | Cách viết dữ liệu ngay trong mã nguồn | Những dấu escape nào chỉ phục vụ cú pháp của ngôn ngữ đang viết? |

Ví dụ, một đoạn JSON xuất hiện trong Java có thể cần nhiều dấu `\` hơn khi hiển thị dưới dạng mã nguồn. Không được đếm số dấu gạch chéo ngược trên màn hình rồi kết luận phản hồi HTTP đã bị encode hai lần. Phải xác định đang quan sát literal trong source code, chuỗi trong debugger, nội dung log hay byte thực sự được gửi qua mạng.

### Encoding ký tự và escaping không phải một việc

Trong bài này, JSON encoding bao gồm việc tuần tự hóa giá trị thành JSON và xuất thành byte đúng hợp đồng. Cần tách hai thao tác:

- **Escaping trong JSON:** biểu diễn dấu nháy, dấu gạch chéo ngược và ký tự điều khiển bên trong một JSON string.
- **Encoding ký tự:** chuyển văn bản thành byte, thông thường là UTF-8 khi trao đổi JSON giữa các hệ thống.

Một serializer tạo đúng JSON nhưng sau đó ứng dụng chuyển chuỗi thành byte bằng bảng mã không phù hợp vẫn có thể làm sai tên tiếng Việt. Ngược lại, UTF-8 không giúp đoạn JSON được nối bằng chuỗi thủ công trở nên an toàn.

## 3. Đe dọa chính: dữ liệu làm thay đổi cấu trúc JSON

Đoạn Java sau xây dựng phản hồi bằng cách nối chuỗi:

```java
String body = "{\"displayName\":\"" + displayName + "\"}";
```

Nếu `displayName` chỉ là `Lan`, kết quả trông có vẻ đúng. Nhưng nếu giá trị đầu vào là:

```text
An","role":"admin
```

thì tài liệu được tạo thành:

```json
{"displayName":"An","role":"admin"}
```

Dữ liệu ban đầu đã trở thành hai thuộc tính. Vấn đề ở đây là sự mất toàn vẹn cấu trúc: người viết chương trình muốn tạo một trường, nhưng kết quả lại có thêm trường khác.

Việc xuất hiện `role` trong phản hồi chưa tự động làm tài khoản có quyền quản trị. Tác động phụ thuộc thành phần tiêu thụ phản hồi và cách nó sử dụng trường đó. Phân quyền vẫn phải được thực thi ở phía có thẩm quyền. Tuy nhiên, không được dùng điều này để bỏ qua lỗi tạo JSON: dữ liệu đã vượt khỏi ranh giới mà nó được phép chiếm giữ.

Khi serializer nhận một đối tượng chỉ có thuộc tính `displayName`, kết quả phù hợp là:

```json
{"displayName":"An\",\"role\":\"admin"}
```

Sau khi parse, đối tượng vẫn chỉ có một thuộc tính. Toàn bộ chuỗi `An","role":"admin` nằm trong giá trị của thuộc tính ấy.

Từ đe dọa này có thể rút ra một yêu cầu kiểm chứng được:

> Mọi giá trị không đáng tin cậy trong phản hồi JSON phải được đưa vào mô hình dữ liệu rồi tuần tự hóa bằng serializer được phê duyệt; chúng không được dùng để ghép trực tiếp cú pháp tài liệu JSON.

Phạm vi của yêu cầu bao gồm cả tên thuộc tính động, chuỗi trong mảng, nội dung thông báo lỗi và giá trị nằm sâu trong đối tượng lồng nhau.

## 4. Các quy tắc escaping cần hiểu

JSON string được bao bởi dấu nháy kép. Một số ký tự phải được biểu diễn bằng escape để không phá vỡ ranh giới chuỗi hoặc tạo ký tự điều khiển không hợp lệ trong văn bản JSON.

| Giá trị bên trong chuỗi | Một cách biểu diễn trong JSON string | Ý nghĩa sau parse |
| --- | --- | --- |
| Dấu nháy kép `"` | `\"` | Một dấu nháy kép |
| Dấu gạch chéo ngược `\` | `\\` | Một dấu gạch chéo ngược |
| Xuống dòng LF | `\n` | Ký tự xuống dòng |
| Carriage return CR | `\r` | Ký tự CR |
| Tab | `\t` | Ký tự tab |
| Backspace | `\b` | Ký tự backspace |
| Form feed | `\f` | Ký tự form feed |
| Ký tự điều khiển khác thuộc U+0000–U+001F | Chẳng hạn `\u0000` | Ký tự tương ứng nếu hợp đồng dữ liệu cho phép |

Không nên tự cài đặt các quy tắc này bằng một chuỗi lệnh `replace`. Việc chỉ thay `"` mà quên `\`, xử lý sai thứ tự hoặc bỏ sót ký tự điều khiển rất dễ tạo ra lỗi.

Một số điểm cần phân biệt:

- Dấu `/` có thể xuất hiện trực tiếp hoặc được biểu diễn bằng `\/`; không phải serializer nào cũng chọn cùng một cách.
- Dấu nháy đơn không phải ký tự đóng JSON string. Chỉ escape dấu nháy đơn không giải quyết được JSON injection.
- Ký tự tiếng Việt và nhiều ký tự Unicode có thể được giữ nguyên trong UTF-8 hoặc dùng escape Unicode phù hợp. Không cần biến mọi ký tự thành `\uXXXX` để JSON an toàn.
- Hai văn bản JSON khác nhau về khoảng trắng hoặc cách escape có thể biểu diễn cùng một dữ liệu. Bài kiểm tra thông thường nên so sánh giá trị sau parse, không buộc một cách trình bày nếu giao thức không yêu cầu byte cố định.

Escaping bảo đảm cú pháp, không quyết định dữ liệu có hợp lệ về nghiệp vụ hay không. Ví dụ, một tên người dùng chứa ký tự NUL có thể được serializer biểu diễn đúng nhưng vẫn bị quy tắc dữ liệu từ chối. Hai điều kiện này cần được đặc tả riêng.

## 5. Thiết kế ranh giới tuần tự hóa

Luồng xử lý mong muốn của một API thông thường là:

```text
Dữ liệu nhận vào
    → kiểm tra kiểu, kích thước và quy tắc nghiệp vụ
    → tạo DTO hoặc cấu trúc dữ liệu đầu ra được phép
    → serializer JSON
    → byte UTF-8 và header HTTP phù hợp
    → parser JSON của bên nhận
    → sử dụng giá trị theo đúng ngữ cảnh tiếp theo
```

Mỗi bước có một trách nhiệm cụ thể:

1. Kiểm tra đầu vào giúp xác định giá trị được chấp nhận. Nó không thay thế escaping khi xuất dữ liệu.
2. DTO đầu ra xác định những thuộc tính được phép công khai. Serializer không tự biết trường nào là bí mật.
3. Serializer giữ dữ liệu bên trong cấu trúc JSON. Nó không cấp quyền truy cập và không tự tạo HTML an toàn.
4. Lớp HTTP công bố kiểu biểu diễn và chuyển văn bản thành byte nhất quán.
5. Bên nhận parse JSON rồi tiếp tục áp dụng quy tắc của nơi sử dụng cuối cùng.

Tại mỗi ranh giới, cần xác định thành phần sở hữu việc chuyển đổi. Nếu controller trả đối tượng cho framework thì framework có thể là nơi tuần tự hóa. Nếu một client SDK nhận `String` đã là tài liệu JSON, SDK phải có hợp đồng khác với phương thức nhận một đối tượng cần serialize.

Tên biến như `data`, `body` hoặc `result` thường không thể hiện được sự khác nhau này. Những tên như `profileDto`, `jsonDocument` và `jsonBytes` giúp giảm nhầm lẫn giữa các lớp biểu diễn.

## 6. Ví dụ Java: tạo cấu trúc trước, serialize sau

Ví dụ dưới đây dùng Jackson để minh họa cơ chế. Phiên bản thư viện và cấu hình thực tế phải theo chính sách dependency của dự án; điểm chính là không nối dữ liệu vào cú pháp JSON.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

public final class ProfileJsonWriter {
    private final ObjectMapper mapper;

    public ProfileJsonWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String writeProfile(String displayName, boolean active)
            throws JsonProcessingException {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("displayName", displayName);
        payload.put("active", active);

        return mapper.writeValueAsString(payload);
    }
}
```

Ở đây:

- `displayName` luôn được đưa vào vị trí giá trị chuỗi, hoặc `null` nếu hợp đồng cho phép và đầu vào là `null`.
- `active` là boolean, không phải chuỗi `"true"` hoặc `"false"`.
- Tên các thuộc tính do ứng dụng xác định.
- Serializer chịu trách nhiệm biểu diễn các ký tự đặc biệt.

Với giá trị đầu vào có dấu nháy và ký tự xuống dòng, parser bên nhận phải khôi phục đúng giá trị đó. Không được xóa những ký tự hợp lệ chỉ để tránh phải xử lý cú pháp JSON.

### Trả đối tượng hay trả JSON string?

Trong một framework tự serialize đối tượng trả về, cách thông thường là trả DTO hoặc cấu trúc dữ liệu. Không nên gọi serializer trước rồi vô tình để framework serialize tiếp chuỗi kết quả.

Hai hợp đồng sau khác nhau:

```text
writeObject(profileDto)
    Đầu vào là đối tượng; lớp HTTP sẽ serialize.

writeJsonDocument(jsonDocument)
    Đầu vào đã là văn bản JSON; lớp HTTP gửi nguyên văn theo hợp đồng đó.
```

Đây là tên minh họa trách nhiệm, không phải tên API bắt buộc của một framework. Khi triển khai, cần kiểm tra bộ chuyển đổi phản hồi thực tế thay vì suy luận chỉ từ kiểu trả về là `String`.

### Không chèn “raw JSON” từ người dùng

Các thư viện có thể cung cấp chức năng ghi giá trị JSON thô, custom serializer hoặc annotation để bỏ qua escaping. Những tính năng đó làm thay đổi giả định an toàn của luồng trên.

Một trường do người dùng gửi như sau không được tự động coi là cấu trúc tin cậy:

```text
{"approved":true,"limit":999999}
```

Nếu hợp đồng xác định đó là ghi chú văn bản, nó phải được serialize như một chuỗi. Nếu hợp đồng thực sự cho phép một đối tượng JSON, ứng dụng cần parse, kiểm tra kiểu và schema, giới hạn các thuộc tính được phép rồi serialize lại cấu trúc đã chấp nhận. Không dùng chức năng ghi raw chỉ để tránh những dấu `\` xuất hiện trong kết quả.

## 7. Double encoding: JSON đúng cú pháp nhưng sai hợp đồng

Giả sử API được đặc tả trả về đối tượng:

```json
{"displayName":"Lan"}
```

Ứng dụng serialize đối tượng thành chuỗi, rồi serialize chuỗi đó một lần nữa. Phản hồi có thể trở thành:

```json
"{\"displayName\":\"Lan\"}"
```

Phản hồi thứ hai vẫn là JSON hợp lệ. Tuy nhiên, phần tử gốc là một chuỗi, không phải đối tượng.

Một tiêu chí nghiệm thu chỉ kiểm tra “parser không báo lỗi” sẽ bỏ sót vấn đề. Cần kiểm tra cả kiểu phần tử gốc và cấu trúc mong đợi. Với API hồ sơ, một lần parse phải thu được đối tượng có trường `displayName`; client không cần parse thêm một lần nữa để lấy đối tượng đó.

Không sửa lỗi bằng cách tùy tiện gọi `replace` để bỏ dấu `\`, hoặc bằng cách bắt client parse lặp cho đến khi “ra đúng dữ liệu”. Những cách đó có thể làm hỏng các dấu gạch chéo ngược vốn là dữ liệu thật.

JSON nằm trong một trường chuỗi có thể là chủ ý của một giao thức đặc biệt, chẳng hạn trường lưu biểu thức dưới dạng văn bản. Khi đó schema phải nói rõ và việc parse lớp thứ hai phải có mục đích cụ thể. Không áp dụng trường hợp này như quy ước ngầm cho toàn bộ API.

## 8. JSON trong HTTP response

Đối với một endpoint JSON độc lập, hợp đồng tối thiểu nên bao gồm:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff

{"displayName":"Lan","active":true}
```

Các byte của body được xuất bằng UTF-8 và không thêm BOM. Thông tin về UTF-8 phải phản ánh cách ứng dụng thực sự tạo byte, không chỉ là một giả định dựa trên cấu hình máy phát triển.

`Content-Type` giúp bên nhận hiểu body là JSON. `nosniff` là biện pháp bổ sung để hạn chế việc trình duyệt suy đoán kiểu nội dung trong những ngữ cảnh áp dụng; nó không thay thế serializer, CSP hoặc cách sử dụng dữ liệu an toàn ở client.

Các nhánh lỗi cũng thuộc phạm vi yêu cầu. Nếu một endpoint thành công trả JSON nhưng khi lỗi lại nối đầu vào vào một trang HTML, đường lỗi đã đi sang một ngữ cảnh khác. Cần đặc tả media type, schema lỗi và cách mã hóa cho chính nhánh đó.

Một hệ thống có thể dùng media type JSON chuyên biệt cho lỗi, chẳng hạn `application/problem+json`. Khi sử dụng, phải tuân theo hợp đồng lỗi đã chọn thay vì giả định mọi phản hồi đều có cùng cấu trúc với nhánh thành công.

### Không dùng JSONP như cách đọc JSON thông thường

JSONP tạo một lời gọi JavaScript bao quanh dữ liệu; đó không còn là một tài liệu JSON thuần. Một endpoint trả JSON không nên tự thêm callback theo tham số yêu cầu. Nếu một hệ thống cũ thực sự cần cơ chế này, nó phải có thiết kế riêng cho ngữ cảnh JavaScript và quyền truy cập dữ liệu.

CORS, xác thực, phân quyền, chính sách cache và bảo vệ CSRF của những thao tác thay đổi trạng thái vẫn là các yêu cầu độc lập. Tạo JSON đúng không chứng minh rằng một tài nguyên đã được bảo vệ khỏi đọc hoặc gọi trái phép.

## 9. JSON hợp lệ chưa đủ an toàn khi đặt trong HTML

Xét giá trị:

```text
</script><p>Thông báo không thuộc trang gốc</p>
```

Giá trị này có thể nằm trong một JSON string hợp lệ. Khi được tải như phản hồi `application/json` rồi parse bằng JSON parser, nó vẫn là dữ liệu.

Nhưng nếu tài liệu JSON được chèn trực tiếp vào phần tử `<script>` của một trang HTML, trình phân tích HTML có thể nhận ra chuỗi đóng `</script>` trước khi một JSON parser có cơ hội xử lý nội dung. Điều này cũng cần được xem xét với khối dữ liệu có `type="application/json"`: thuộc tính type không làm bộ phân tích HTML bỏ qua ranh giới kết thúc phần tử.

Do đó, yêu cầu “đã dùng JSON serializer nên có thể chèn vào mọi vị trí” là sai. JSON serializer giải quyết cú pháp JSON; nơi chứa JSON có thể có bộ phân tích cú pháp khác hoạt động trước.

| Nơi đưa dữ liệu vào | Cơ chế cần áp dụng |
| --- | --- |
| Body HTTP JSON độc lập | Serialize JSON và xuất byte theo hợp đồng HTTP |
| Khối dữ liệu JSON trong phần tử `script` của HTML | Serialize JSON, sau đó dùng cơ chế xuất an toàn cho khối dữ liệu HTML này |
| Thuộc tính HTML chứa văn bản JSON | Serialize JSON, rồi mã hóa thuộc tính HTML và bao thuộc tính bằng dấu nháy đúng cách |
| Một đoạn mã JavaScript thực thi | Thiết kế riêng theo ngữ cảnh JavaScript; tránh tự nội suy dữ liệu vào source code |
| Văn bản hiển thị sau khi parse JSON | Gán vào điểm nhận văn bản như `textContent` |

Đặc biệt, dấu `\"` không bảo vệ ranh giới thuộc tính HTML. HTML không coi dấu gạch chéo ngược là ký tự escape dấu nháy theo cách JSON thực hiện.

### Một cách xử lý khối dữ liệu HTML được kiểm soát

Với trường hợp cụ thể là JSON được đặt trong nội dung một phần tử `script` dành cho dữ liệu, cơ chế xuất có thể thay ký tự `<` thực trong tài liệu đã serialize thành escape JSON `\u003c`. Khi parse, giá trị dữ liệu được khôi phục, nhưng trong nguồn HTML không còn ký tự `<` đó để bắt đầu chuỗi đóng phần tử từ dữ liệu.

Ví dụ minh họa một hàm dành riêng cho ngữ cảnh này:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class HtmlJsonDataWriter {
    private final ObjectMapper mapper;

    public HtmlJsonDataWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String writeScriptData(Object value)
            throws JsonProcessingException {
        String jsonDocument = mapper.writeValueAsString(value);

        return jsonDocument
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026");
    }
}
```

Ở ví dụ này, escaping `<` giải quyết khả năng tạo chuỗi đóng phần tử từ dữ liệu. Việc biểu diễn thêm `>` và `&` theo cách nhất quán là lựa chọn của hàm xuất. Hàm nhận đối tượng, serialize trước, rồi chuyển đổi các ký tự thực trong văn bản JSON; nó không phải một bộ thay thế serializer.

Hàm trên chỉ minh họa ngữ cảnh khối dữ liệu đã nêu. Không lấy kết quả ấy rồi mặc định chèn an toàn vào thuộc tính HTML, URL, event handler hoặc một chuỗi JavaScript. Trong một template engine, nên sử dụng helper có hợp đồng rõ ràng cho JSON trong HTML và kiểm tra tương tác với cơ chế auto-escape của engine.

HTML entity encoding cũng không thể được áp dụng máy móc vào nội dung script data. Trong ngữ cảnh đó, biến `"` thành `&quot;` có thể làm JSON không còn được parse như dự định. Điều cần kiểm tra là toàn bộ chuỗi parser thực sự của trang, không phải việc kết quả “có vẻ đã escape”.

## 10. Sau khi parse JSON, dữ liệu vẫn chưa trở thành đáng tin cậy

Client đọc JSON an toàn nhưng sau đó đưa giá trị vào `innerHTML` thì lại tạo một điểm diễn giải HTML mới.

Ví dụ với API trả về `displayName` dạng chuỗi:

```javascript
async function showProfile(targetElement) {
  const response = await fetch("/api/profile", {
    headers: { Accept: "application/json" }
  });

  if (!response.ok) {
    throw new Error("Không tải được hồ sơ");
  }

  const profile = await response.json();

  if (typeof profile.displayName !== "string") {
    throw new Error("Phản hồi không đúng hợp đồng");
  }

  targetElement.textContent = profile.displayName;
}
```

`response.json()` phân tích dữ liệu JSON. `textContent` đưa giá trị vào ngữ cảnh văn bản. Hai thao tác này có trách nhiệm khác nhau và đều cần đúng.

Không dùng `eval` để đọc JSON. Nếu ứng dụng thực sự cho phép một trường chứa HTML có định dạng, trường đó cần hợp đồng riêng về nội dung được phép và cơ chế xử lý HTML; không suy rộng từ trường văn bản thông thường.

Tương tự, một chuỗi lấy từ JSON rồi dùng làm URL vẫn cần chính sách URL. Một đối tượng parse từ JSON không được tự động gộp vào cấu hình tin cậy hoặc dùng như một quyết định phân quyền chỉ vì quá trình parse thành công.

## 11. Bảo toàn kiểu và giá trị là một phần của yêu cầu

An toàn không chỉ là tránh lỗi cú pháp. Một tài liệu JSON có thể parse thành công nhưng mang dữ liệu sai nghĩa.

### 11.1. Boolean, null, trường thiếu và chuỗi rỗng

Các giá trị sau không tương đương:

```json
{"active":false}
```

```json
{"active":"false"}
```

Trong nhiều ngôn ngữ, một chuỗi không rỗng có thể được xem là truthy nếu code tiêu thụ không kiểm tra kiểu. Vì vậy, API phải công bố `active` là boolean và không tự đổi nó thành chuỗi.

Tương tự, cần phân biệt:

- Thuộc tính không xuất hiện: giá trị không được cung cấp, không thuộc biểu diễn này hoặc không được phép công khai, tùy hợp đồng.
- Thuộc tính có giá trị `null`: biểu diễn một trạng thái null đã được định nghĩa.
- Thuộc tính có giá trị `""`: một chuỗi tồn tại nhưng rỗng.

Không để cấu hình bỏ trường null hoặc serializer tùy biến âm thầm thay đổi ý nghĩa của API mà không có quyết định schema.

### 11.2. Số lớn và độ chính xác

JSON có cú pháp số, nhưng khả năng biểu diễn chính xác phụ thuộc parser và kiểu số của bên nhận. Một mã định danh số nguyên lớn có thể mất chính xác khi đi vào kiểu `Number` thông thường của JavaScript.

Ví dụ, nếu hợp đồng đã chọn mã định danh là chuỗi, hãy giữ nó là chuỗi:

```json
{
  "transactionId": "9007199254740993",
  "amount": "1234567890.12",
  "currency": "VND"
}
```

Đây là ví dụ về một hợp đồng chọn chuỗi để bảo toàn mã định danh và giá trị thập phân. Không phải mọi API đều phải biểu diễn tiền bằng chuỗi; lựa chọn phải phù hợp với schema, đơn vị và kiểu số của các bên tham gia. Quan trọng là không để một phép chuyển đổi ngầm làm thay đổi số tiền hoặc tham chiếu giao dịch.

Các giá trị như `NaN` và vô cực không phải JSON number hợp lệ. Ứng dụng phải có chính sách rõ: từ chối dữ liệu không hợp lệ hoặc chuyển sang một biểu diễn khác đã được schema quy định. Không dựa vào hành vi mặc định khác nhau giữa các thư viện.

### 11.3. Tên thuộc tính và thuộc tính trùng

Đầu ra nên có tên thuộc tính duy nhất trong mỗi object. Nếu một tài liệu có hai khóa giống nhau, các parser hoặc lớp ánh xạ có thể diễn giải khác nhau, làm phát sinh bất nhất giữa kiểm tra và sử dụng.

Khi dữ liệu nghiệp vụ là tập các cặp tên–giá trị do người dùng đặt, cần cân nhắc mô hình rõ ràng, chẳng hạn một danh sách các mục, thay vì trộn tên do người dùng kiểm soát với các trường quản trị của đối tượng.

Serializer hỗ trợ tạo đúng cú pháp cho tên thuộc tính động; nó không quyết định một tên thuộc tính có được phép chi phối hành vi của ứng dụng hay không.

## 12. Unicode và UTF-8

Các ví dụ chỉ gồm ký tự ASCII thường bỏ sót lỗi thực tế. Bộ trường hợp nghiệm thu nên có tên tiếng Việt, ký tự ngoài BMP như emoji, dấu kết hợp và ký tự điều khiển mà hợp đồng cho phép.

Những yêu cầu cần xác định gồm:

1. Đường truyền JSON sử dụng UTF-8 nhất quán từ writer đến response body.
2. Giá trị được khôi phục sau parse bằng giá trị đã được chấp nhận trước khi serialize.
3. Việc chuẩn hóa Unicode, nếu có, xảy ra ở một bước có chủ đích và được mô tả; lớp xuất JSON không tự thay đổi chuỗi vì lý do thẩm mỹ.
4. Dữ liệu có đơn vị UTF-16 surrogate lẻ hoặc chuỗi Unicode không phù hợp hợp đồng được xử lý theo chính sách rõ ràng, thay vì trông chờ mọi bên nhận xử lý giống nhau.

Một Java `String` có thể chứa dữ liệu UTF-16 không tạo thành chuỗi Unicode hoàn chỉnh. Việc serializer vẫn xuất được một escape không bảo đảm mọi consumer sẽ chấp nhận và khôi phục giá trị theo cùng cách. Với dữ liệu cần khả năng tương tác cao, hợp đồng nên yêu cầu chuỗi Unicode hợp lệ và xác định hành vi khi đầu vào vi phạm.

Không tự thay ký tự lạ bằng `?` mà vẫn báo thành công nếu điều đó làm sai tên, mã giao dịch hoặc giá trị được dùng để đối chiếu. Nếu chính sách cho phép thay thế ký tự trong một trường hiển thị, hành vi ấy phải được xác định và kiểm tra riêng.

## 13. Hành vi khi serialization thất bại

Serialization có thể lỗi do đối tượng không hỗ trợ, custom serializer gặp lỗi, dữ liệu vượt giới hạn hoặc một trường không thỏa hợp đồng. Cần đặc tả hành vi thay vì chỉ ghi “bắt exception”.

Với endpoint phản hồi một tài liệu JSON thông thường, thiết kế nên bảo đảm:

- Không báo thành công với body rỗng hoặc tài liệu bị cắt giữa chừng.
- Không trả stack trace, đường dẫn máy chủ, secret hoặc toàn bộ đối tượng nội bộ để giải thích lỗi serialization.
- Sử dụng mã HTTP và schema lỗi đã công bố khi response chưa được commit.
- Ghi nhận lỗi theo cơ chế quan sát của hệ thống với dữ liệu được phép ghi.
- Xác định riêng trường hợp response đã bắt đầu được gửi và không thể thay thế bằng một tài liệu lỗi hoàn chỉnh.

Đối với phản hồi vừa phải về kích thước, việc tạo body hoàn chỉnh trước khi commit response giúp xử lý lỗi dễ hơn. Với dữ liệu streaming, cần một giao thức và chính sách lỗi phù hợp; không giả định có thể sửa lại status code hoặc ghép thêm một object lỗi vào cuối JSON đã gửi dở.

Các định dạng như NDJSON có ranh giới bản ghi khác với một JSON array thông thường. Nếu dùng, phải đặc tả định dạng và media type tương ứng; không gọi chung mọi chuỗi nhiều object nối tiếp là một tài liệu JSON hợp lệ.

Giới hạn kích thước, số phần tử và độ sâu cần xuất phát từ rủi ro cùng khả năng của các bên nhận. Không có một con số mặc định phù hợp cho mọi hệ thống. Các giới hạn ấy hỗ trợ khả năng chịu tải và tính tương tác, còn serializer vẫn chịu trách nhiệm tạo đúng cú pháp trong phạm vi đã chấp nhận.

## 14. Mẫu đặc tả yêu cầu bảo mật

Ví dụ dưới đây áp dụng cho API hồ sơ trả đối tượng JSON và một trang có khối dữ liệu JSON được nhúng. Dự án có thể điều chỉnh định danh, nhưng mỗi yêu cầu phải có điểm kiểm tra cụ thể.

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| JSON-01 | Mọi phản hồi JSON chứa giá trị không đáng tin cậy được tạo từ DTO hoặc cấu trúc dữ liệu bằng serializer được phê duyệt | Kiểm tra đường tạo body và trường hợp đầu vào có dấu nháy, gạch chéo ngược, ký tự điều khiển |
| JSON-02 | Dữ liệu không được nối trực tiếp vào cú pháp object, array, tên thuộc tính hoặc giá trị JSON | Đường tạo phản hồi không dùng phép ghép chuỗi để dựng cú pháp từ đầu vào; cấu trúc sau parse không thay đổi theo dữ liệu thử |
| JSON-03 | Phản hồi độc lập có media type đúng hợp đồng và byte UTF-8 không BOM | Đối chiếu header cùng byte body thực tế ở nhánh thành công và nhánh lỗi |
| JSON-04 | Một lần parse phản hồi hồ sơ phải thu được object đúng schema | Kiểm tra kiểu phần tử gốc, thuộc tính và kiểu của từng trường; không cần parse chuỗi lồng thêm lần nữa |
| JSON-05 | Bộ giá trị đã chấp nhận được bảo toàn qua serialize–parse | So sánh giá trị chuỗi, boolean, null và số theo hợp đồng, gồm tiếng Việt và ký tự ngoài BMP |
| JSON-06 | Đầu ra không có tên thuộc tính trùng trong một object và không chứa trường nội bộ ngoài schema | Đối chiếu cấu trúc phản hồi với schema đầu ra và danh sách trường được phép công khai |
| JSON-07 | Chức năng ghi raw JSON không nhận trực tiếp nội dung không đáng tin cậy | Kiểm tra custom serializer và điểm ghi raw; đầu vào dạng văn bản vẫn được truyền như chuỗi |
| JSON-08 | JSON được nhúng vào HTML phải đi qua cơ chế xuất đúng vị trí nhúng | Chuỗi chứa `</script>` không kết thúc khối dữ liệu từ bên trong; parse vẫn khôi phục nguyên giá trị |
| JSON-09 | Client dùng JSON parser và đưa trường văn bản vào điểm nhận văn bản | Kiểm tra quá trình nhận dữ liệu; nội dung giống HTML không tạo phần tử mới khi hiển thị như văn bản |
| JSON-10 | Serialization thất bại có hành vi lỗi xác định và không lộ dữ liệu nội bộ | Gây lỗi có kiểm soát, xác nhận mã phản hồi, schema lỗi và dữ liệu quan sát được |

Ví dụ tiêu chí chấp nhận theo tình huống:

```text
Given:
  API hồ sơ định nghĩa displayName là string và active là boolean.
  Giá trị displayName đã được chấp nhận là: An","role":"admin

When:
  API tạo phản hồi thành công.

Then:
  Body là một tài liệu JSON theo media type đã công bố.
  Một lần parse trả về object đúng schema.
  displayName bằng nguyên giá trị đầu vào đã được chấp nhận.
  Không có thuộc tính role phát sinh từ chuỗi displayName.
  active giữ kiểu boolean.
```

Tiêu chí này liên kết rõ một đe dọa với hành vi cần bảo vệ. Nó không phụ thuộc serializer chọn giữ nguyên Unicode hay xuất escape Unicode, miễn là hợp đồng về dữ liệu và ngữ cảnh vẫn được đáp ứng.

## 15. Bộ trường hợp kiểm chứng nên thiết kế

Các trường hợp dưới đây là đầu vào cho việc nghiệm thu yêu cầu, không phải một bộ lọc chặn chuỗi cố định. Hệ thống không cần cấm các giá trị này trong mọi trường; nó cần bảo toàn cấu trúc và áp dụng quy tắc nghiệp vụ tương ứng.

| Nhóm | Giá trị hoặc tình huống | Điều cần quan sát |
| --- | --- | --- |
| Dấu phân cách | Chuỗi có `"`, `\`, `{`, `}`, `[`, `]`, `,`, `:` | Các ký tự vẫn thuộc giá trị chuỗi; không thêm trường hoặc phần tử |
| Chèn thuộc tính | `An","role":"admin` | Đối tượng sau parse không có trường mới do chuỗi tạo ra |
| Ký tự điều khiển | LF, CR, tab và NUL nếu trường cho phép | JSON hợp lệ và giá trị sau parse đúng hợp đồng |
| Unicode | `Nguyễn Ánh`, emoji và chuỗi có dấu kết hợp | Không mất ký tự, không biến thành mojibake hoặc tự chuẩn hóa |
| Ranh giới HTML | Chuỗi có `</script>` và nội dung giống thẻ | Kiểm tra riêng API JSON và vị trí nhúng HTML; không coi chúng là một ngữ cảnh |
| Kiểu dữ liệu | `false`, `"false"`, `null`, `""`, trường bị thiếu | Schema phân biệt đúng kiểu và ý nghĩa |
| Số và định danh | Mã giao dịch lớn, số thập phân cần bảo toàn | Không mất độ chính xác hoặc đổi kiểu ngoài hợp đồng |
| Double encoding | Object bị serialize thành chuỗi rồi serialize tiếp | Một lần parse thu được đúng kiểu gốc của schema |
| Cấu trúc lồng nhau | Chuỗi nguy cơ nằm trong mảng hoặc object sâu | Serializer bảo vệ mọi mức, không chỉ trường ở ngoài cùng |
| Đường lỗi | Thông báo lỗi chứa đầu vào hoặc serialization thất bại | Không ghép cú pháp thủ công, không lộ thông tin nội bộ |
| Giới hạn | Giá trị sát giới hạn và vượt giới hạn đã công bố | Hành vi ổn định, không trả thành công với body hỏng |

Nên quan sát phản hồi ở mức HTTP thực tế và cả giá trị sau parse. Chỉ nhìn một đoạn log có thể dẫn tới kết luận sai vì log viewer thường hiển thị escape thêm một lớp. Ngược lại, một giao diện hiển thị dữ liệu trông đúng cũng chưa chứng minh body có kiểu hoặc cấu trúc chính xác.

Với trường hợp nhúng HTML, cần kiểm tra trang đã render trong ngữ cảnh trình duyệt: ranh giới khối dữ liệu, DOM tạo ra và giá trị parse được. Kiểm tra cú pháp JSON riêng lẻ không đủ để kết luận ranh giới HTML an toàn.

## 16. Những cách xử lý dễ tạo cảm giác an toàn giả

### Chỉ xóa dấu nháy kép

Xóa dấu nháy làm thay đổi dữ liệu hợp lệ và vẫn không mô tả đầy đủ các quy tắc JSON. Serializer tồn tại để xử lý cú pháp một cách nhất quán; validation quyết định ký tự nào hợp lệ về nghiệp vụ.

### HTML encode mọi giá trị trước khi serialize

Với một API JSON độc lập, giá trị `A&B` không cần biến thành `A&amp;B` để trở thành JSON an toàn. Làm vậy có thể khiến client nhận sai nội dung. Khi JSON được đặt trong HTML, phải xử lý đúng vị trí xuất cuối cùng thay vì lưu sẵn HTML entities vào dữ liệu nghiệp vụ.

### URL encode hoặc Base64 để thay JSON escaping

Hai cơ chế này có mục đích riêng. Dùng chúng tùy tiện làm thay đổi hợp đồng dữ liệu, còn lớp JSON chứa kết quả vẫn cần được serialize đúng. Base64 không phải mã hóa bảo mật, cũng không giải quyết việc nội dung được decode rồi đưa vào điểm diễn giải nguy hiểm.

### Bỏ dấu gạch chéo ngược trước khi trả về

Dấu `\` có thể là thành phần cần thiết của cú pháp JSON hoặc dữ liệu thật. Xóa chúng sau serialization có thể biến một phản hồi đúng thành phản hồi hỏng hoặc mở lại ranh giới chuỗi.

### Cho rằng JSON serializer tự loại bỏ secret

Một serializer có thể serialize hoàn toàn chính xác một trường chứa token, mật khẩu hoặc thông tin nội bộ. Yêu cầu giảm thiểu dữ liệu đầu ra và phân quyền truy cập phải được thể hiện ở mô hình phản hồi cùng logic có thẩm quyền.

### Cho rằng dữ liệu đã parse thì có thể dùng ở mọi nơi

Sau parse, giá trị vẫn có thể đi vào HTML, URL, lệnh hệ điều hành, truy vấn hoặc cấu hình. Mỗi nơi dùng có quy tắc riêng. JSON encoding chỉ bảo vệ ranh giới JSON trong chuỗi xử lý đó.

## 17. Áp dụng vào thiết kế hệ thống

Khi phân tích một endpoint, hãy bắt đầu bằng trường dữ liệu và nơi nó sẽ được sử dụng. Ví dụ, `displayName` được nhập từ trang hồ sơ, lưu trong cơ sở dữ liệu, trả qua API JSON rồi hiển thị trên trang quản trị. Yêu cầu cần theo được giá trị qua cả đường đi:

- Trường được kiểm tra theo quy tắc tên hiển thị khi chấp nhận dữ liệu.
- DTO phản hồi chỉ chứa những thông tin được phép công khai.
- Serializer giữ nguyên tên trong một JSON string.
- Lớp HTTP xuất UTF-8 theo media type đã công bố.
- Client parse phản hồi một lần và hiển thị tên như văn bản.
- Nếu có trang render phía máy chủ nhúng cùng dữ liệu vào HTML, đường nhúng có cơ chế xuất riêng cho ngữ cảnh đó.

Từ đường đi cụ thể này, nhóm có thể xác định nơi thực thi, người chịu trách nhiệm và bằng chứng nghiệm thu cho từng yêu cầu. Kết quả cần đạt là dữ liệu hợp lệ giữ nguyên ý nghĩa, cấu trúc JSON do ứng dụng kiểm soát và mọi bước chuyển sang ngữ cảnh khác đều được thiết kế rõ ràng.
