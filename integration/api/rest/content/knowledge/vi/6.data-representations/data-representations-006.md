# Phân biệt trường thiếu, null, giá trị rỗng và mặc định

## 1. Vì sao sự khác biệt này ảnh hưởng đến hợp đồng REST?

Giả sử một khách hàng có biệt danh `An`. Giao diện chỉ muốn đổi tên hiển thị nên gửi:

```http
PATCH /customers/cus-104 HTTP/1.1
Content-Type: application/vnd.example.customer-update+json

{
  "displayName": "Nguyễn Minh An"
}
```

Nếu máy chủ chuyển JSON thành một đối tượng Java có trường `nickname == null`, rồi sao chép tất cả thuộc tính sang entity, biệt danh có thể bị xóa ngoài ý muốn. Client không hề gửi yêu cầu xóa. Thông tin “trường này có xuất hiện trong request hay không” đã mất ở bước ánh xạ.

Chiều ngược lại cũng nguy hiểm: nếu máy chủ bỏ qua mọi giá trị `null`, người dùng có thể không bao giờ xóa được biệt danh khi họ chủ động gửi `"nickname": null` theo hợp đồng API.

Trong module `INTEGRATION_API_REST`, biểu diễn dữ liệu là một phần của thiết kế resource và hành vi HTTP. Một hợp đồng tốt phải giải thích được client đã gửi gì, máy chủ hiểu đó là thao tác nào, trạng thái resource thay đổi ra sao và response thể hiện kết quả thế nào.

Sau bài này, người học có thể:

- Phân biệt sự hiện diện của một trường với giá trị của trường đó.
- Viết quy tắc riêng cho thiếu trường, `null`, rỗng và giá trị mặc định.
- Giữ được ý định cập nhật khi xử lý JSON trong Java.
- Mô tả hợp đồng bằng schema và chọn các tình huống kiểm thử cần thiết.

## 2. Bốn khái niệm cần tách biệt

### 2.1. Trường thiếu: không có cặp tên và giá trị

Hai JSON sau khác nhau về cấu trúc:

```json
{}
```

```json
{
  "nickname": null
}
```

Trong JSON đầu tiên, tên `nickname` không xuất hiện. Đây là trạng thái **thiếu trường**, thường gọi là *missing*, *absent* hoặc *omitted*. Không có một giá trị JSON tên là `missing` để client gửi thay thế.

Thiếu trường có thể mang những ý nghĩa khác nhau tùy thao tác:

- Khi tạo resource: dùng mặc định, để chưa xác định hoặc báo thiếu dữ liệu bắt buộc.
- Khi cập nhật từng phần: giữ nguyên giá trị hiện có nếu hợp đồng quy định như vậy.
- Khi đọc resource: trường không nằm trong projection đã chọn, không được trả cho người gọi hoặc không thuộc biến thể response này.

Vì vậy, client không thể kết luận rằng “không thấy trường” luôn có nghĩa là “resource chưa có dữ liệu”.

### 2.2. `null`: trường có mặt với một giá trị JSON riêng

```json
{
  "nickname": null
}
```

`null` là giá trị JSON hợp lệ. Việc nó có hợp lệ trong một trường cụ thể hay không phụ thuộc schema và quy tắc nghiệp vụ.

Ví dụ, hợp đồng có thể quy định `nickname: null` nghĩa là “không có biệt danh”. Nhưng với `displayName`, `null` có thể bị từ chối vì mọi khách hàng phải có tên hiển thị.

Không dùng cùng một `null` để âm thầm đại diện cho nhiều trạng thái quan trọng như “chưa thu thập”, “người dùng từ chối cung cấp”, “không áp dụng” và “đã bị xóa”. Nếu nghiệp vụ cần phân biệt, hãy mô hình hóa trạng thái đó rõ ràng:

```json
{
  "taxIdentifier": {
    "state": "NOT_APPLICABLE"
  }
}
```

Ở đây `state` giải thích ý nghĩa nghiệp vụ. Không cần suy đoán từ việc một thuộc tính khác bị thiếu hay có giá trị `null`.

### 2.3. Giá trị rỗng: vẫn có kiểu dữ liệu và vẫn có nội dung ngữ nghĩa

Các giá trị sau không thể thay thế tùy tiện cho nhau:

| Biểu diễn | Trạng thái quan sát được | Câu hỏi cần đặt ra |
| --- | --- | --- |
| `""` | Chuỗi dài 0 | Trường có cho phép chuỗi rỗng không? |
| `"   "` | Chuỗi gồm khoảng trắng | Có chuẩn hóa khoảng trắng trước khi kiểm tra không? |
| `[]` | Mảng không có phần tử | Có nghĩa là đã biết danh sách không có phần tử không? |
| `{}` | Đối tượng không có thuộc tính | Có phải đối tượng hợp lệ hoặc bản cập nhật không có thay đổi không? |
| `null` | Giá trị JSON null | Có cho phép và có mang nghĩa xóa không? |
| Thiếu trường | Không có thuộc tính đó | Dùng mặc định, giữ nguyên hay báo lỗi? |

`0` và `false` là các giá trị cụ thể, không phải dữ liệu bị thiếu. Một đơn hàng có `discountAmount: 0` có thể hoàn toàn hợp lệ; `marketingOptIn: false` là một lựa chọn cần được bảo toàn.

Chuỗi `"null"` cũng là một chuỗi có bốn ký tự, khác với JSON `null`. Tương tự, `"false"` khác boolean `false`, và `"[]"` khác mảng `[]`. Hợp đồng cần quyết định có chấp nhận chuyển kiểu hay từ chối ngay tại biên API.

### 2.4. Mặc định: quy tắc chọn giá trị khi một điều kiện xảy ra

Mặc định không phải trạng thái thứ tư được mã hóa trong JSON. Nó là quy tắc xử lý, chẳng hạn:

> Khi tạo khách hàng, nếu không gửi `marketingOptIn`, máy chủ dùng `false`. Nếu gửi `null`, máy chủ từ chối request.

Quy tắc trên có hai nhánh khác nhau:

```text
Không có marketingOptIn  -> false
Có marketingOptIn: null  -> lỗi
```

Một API khác có thể chấp nhận `null` và xử lý theo cách khác. Điều cần thiết là ghi rõ điều kiện áp dụng mặc định; không để cấu hình framework vô tình quyết định hợp đồng.

## 3. Lập bảng hợp đồng trước khi viết DTO

Xét resource khách hàng với bốn trường có thể ghi:

- `displayName`: chuỗi sau chuẩn hóa phải có từ 1 đến 80 ký tự.
- `nickname`: chưa có biệt danh hoặc là chuỗi sau chuẩn hóa có từ 1 đến 40 ký tự.
- `tags`: danh sách chuỗi không rỗng; danh sách có thể không có phần tử.
- `marketingOptIn`: boolean thể hiện lựa chọn nhận thông tin tiếp thị.

API minh họa chọn các quy tắc sau. Đây là **quyết định của API trong bài**, không phải quy tắc tự động áp dụng cho mọi REST API.

### 3.1. Tạo mới bằng `POST /customers`

| Trường | Thiếu trường | `null` | Rỗng | Giá trị hợp lệ |
| --- | --- | --- | --- | --- |
| `displayName` | Báo lỗi | Báo lỗi | `""` hoặc chỉ khoảng trắng: lỗi | Chuẩn hóa rồi lưu |
| `nickname` | Không có biệt danh | Không có biệt danh | `""` hoặc chỉ khoảng trắng: lỗi | Chuẩn hóa rồi lưu |
| `tags` | Dùng `[]` | Báo lỗi | `[]`: hợp lệ | Lưu danh sách |
| `marketingOptIn` | Dùng `false` | Báo lỗi | Không có dạng “boolean rỗng” | Lưu cả `true` và `false` |

Ví dụ request tối thiểu:

```json
{
  "displayName": "Minh An"
}
```

Response thành công có thể trả `201 Created`, `Location: /customers/cus-104` và biểu diễn đã áp dụng mặc định:

```json
{
  "id": "cus-104",
  "displayName": "Minh An",
  "nickname": null,
  "tags": [],
  "marketingOptIn": false
}
```

Client thấy được trạng thái máy chủ thực sự đã lưu. Client không cần đoán xem mặc định trong tài liệu có được áp dụng hay chưa.

### 3.2. Cập nhật từng phần bằng định dạng riêng

Với `PATCH /customers/{id}` và media type `application/vnd.example.customer-update+json`, API minh họa định nghĩa:

| Trường | Thiếu trường | `null` | Rỗng | Giá trị hợp lệ |
| --- | --- | --- | --- | --- |
| `displayName` | Giữ nguyên | Báo lỗi | `""` hoặc chỉ khoảng trắng: lỗi | Thay tên |
| `nickname` | Giữ nguyên | Xóa biệt danh | `""` hoặc chỉ khoảng trắng: lỗi | Thay biệt danh |
| `tags` | Giữ nguyên | Báo lỗi | `[]`: xóa mọi phần tử | Thay toàn bộ danh sách |
| `marketingOptIn` | Giữ nguyên | Báo lỗi | Không áp dụng | Thay lựa chọn, kể cả `false` |

Không áp dụng lại mặc định tạo mới cho trường bị thiếu trong request này. Nếu khách hàng đang có `marketingOptIn: true`, request chỉ đổi tên không được tự đặt lựa chọn đó về `false`.

Với trạng thái ban đầu:

```json
{
  "displayName": "An",
  "nickname": "An ở nhà",
  "tags": ["java", "spring"],
  "marketingOptIn": true
}
```

Request sau có ba thao tác rõ ràng:

```json
{
  "nickname": null,
  "tags": [],
  "marketingOptIn": false
}
```

Kết quả:

```json
{
  "displayName": "An",
  "nickname": null,
  "tags": [],
  "marketingOptIn": false
}
```

Tên hiển thị được giữ nguyên vì thiếu trường. Biệt danh bị xóa vì `null`. Danh sách được làm rỗng vì `[]`. Lựa chọn tiếp thị được đổi thành `false` vì đó là giá trị client đã gửi.

## 4. HTTP method và định dạng cập nhật cùng quyết định ý nghĩa

### 4.1. Không suy ra toàn bộ hợp đồng từ chữ `PATCH`

`PATCH` cho biết đây là yêu cầu sửa đổi resource, nhưng ý nghĩa từng giá trị còn phụ thuộc định dạng request. Ghi `Content-Type: application/json` đơn thuần không tự định nghĩa “thiếu thì giữ nguyên” hay “null thì xóa”. API phải công bố quy tắc hoặc dùng một định dạng patch đã được chuẩn hóa.

Ví dụ trong bài dùng media type riêng để làm rõ rằng `nickname: null` là quy tắc của hợp đồng này. Không được gọi mọi JSON dùng cho cập nhật từng phần là JSON Merge Patch.

### 4.2. JSON Merge Patch

Với `application/merge-patch+json`, thuộc tính bị thiếu không bị sửa; thuộc tính có giá trị `null` được loại khỏi đối tượng đích. Mảng được thay toàn bộ. Không thể dùng `null` theo cách này để lưu một thuộc tính với giá trị null tường minh. Đây là ngữ nghĩa của [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396.html).

```json
{
  "nickname": null,
  "tags": []
}
```

Nếu chọn định dạng này, cần xác định việc loại thuộc tính khỏi tài liệu đích được ánh xạ sang mô hình nghiệp vụ như thế nào.

### 4.3. JSON Patch

`application/json-patch+json` biểu diễn từng thao tác riêng. Ví dụ sau đặt `nickname` thành null, giả sử thuộc tính đã tồn tại:

```json
[
  { "op": "replace", "path": "/nickname", "value": null }
]
```

Thao tác `remove` lại loại thuộc tính:

```json
[
  { "op": "remove", "path": "/nickname" }
]
```

`replace` và `remove` yêu cầu vị trí đích tồn tại. Chọn định dạng này khi cần phân biệt thao tác đặt null và loại thuộc tính; vẫn phải kiểm tra quyền và dữ liệu sau cập nhật. Các thao tác được định nghĩa trong [RFC 6902](https://www.rfc-editor.org/rfc/rfc6902.html).

### 4.4. Cẩn thận với `PUT`

Một hợp đồng dùng `PUT` để thay thế phần trạng thái có thể ghi phải quy định biểu diễn thay thế gồm những trường nào. Ví dụ, API có thể yêu cầu `displayName`, `tags`, `marketingOptIn`, cho phép `nickname` vắng mặt để biểu diễn không có biệt danh, và giữ các trường do máy chủ quản lý như `id` ngoài dữ liệu đầu vào.

Không tái sử dụng bảng “thiếu trường thì giữ nguyên” của PATCH cho PUT chỉ vì cùng dùng một DTO. Cũng không mặc định rằng mọi trường bị thiếu trong PUT đều phải biến thành `null`; các thuộc tính bắt buộc, giá trị suy ra và mặc định phải được xác định trong hợp đồng thay thế.

## 5. Mặc định nên được áp dụng ở thời điểm nào?

Một luồng xử lý dễ kiểm soát là:

```text
Đọc JSON và giữ thông tin trường có mặt
    -> kiểm tra cấu trúc và kiểu
    -> diễn giải thiếu / null / giá trị theo thao tác
    -> chuẩn hóa các giá trị được phép chuẩn hóa
    -> áp dụng mặc định nếu đúng điều kiện
    -> kiểm tra trạng thái ứng viên theo nghiệp vụ
    -> lưu trong giao dịch
    -> tạo response
```

Các bước có thể được tổ chức khác nhau trong ứng dụng cụ thể, nhưng không được làm mất dấu hiệu hiện diện trước khi dùng nó để quyết định hành vi.

### 5.1. Mặc định trong tài liệu không tự chạy trong chương trình

Trong JSON Schema, `default` là thông tin mô tả; validator không tự điền trường bị thiếu chỉ vì schema khai báo giá trị đó. Máy chủ phải thực thi quy tắc mặc định đã công bố. Xem [tài liệu annotations của JSON Schema](https://json-schema.org/understanding-json-schema/reference/annotations).

Ví dụ, schema ghi `default: false` cho `marketingOptIn` chưa chứng minh rằng controller, service hoặc database sẽ dùng `false` khi client bỏ trường này.

### 5.2. Mặc định ở các tầng có thể mâu thuẫn

Giả sử tài liệu API công bố `pageSize` mặc định là `20`, service dùng `50`, còn giao diện tự gửi `10`. Khi request luôn chứa `pageSize=10`, lỗi lệch mặc định có thể bị che khuất rất lâu.

Nên chọn nơi chịu trách nhiệm rõ ràng cho mặc định và kiểm thử request thật sự thiếu trường. Nếu database cũng có default, cần biết ứng dụng có bỏ cột khỏi câu lệnh ghi hay luôn truyền một giá trị. Không suy ra “cột có DEFAULT nên mọi giá trị null sẽ được thay thế”.

### 5.3. Không dùng điều kiện “giống rỗng” để quyết định mặc định

Một lỗi thường gặp ở client JavaScript:

```javascript
const enabled = input.marketingOptIn || true;
```

Khi client gửi `false`, biểu thức trên chọn `true`. Nó đã thay đổi ý định của người dùng.

Nếu hợp đồng yêu cầu chỉ mặc định khi thuộc tính bị thiếu, hãy kiểm tra sự hiện diện:

```javascript
const supplied = Object.prototype.hasOwnProperty.call(
  input, "marketingOptIn"
);

const enabled = supplied ? input.marketingOptIn : false;

if (typeof enabled !== "boolean") {
  throw new Error("marketingOptIn phải là boolean");
}
```

Toán tử `??` giữ được `false` và `0`, nhưng vẫn gộp `null` với `undefined`. Nó chỉ phù hợp nếu hợp đồng cho phép hai trường hợp đó dùng cùng mặc định.

## 6. Giữ thông tin hiện diện khi xử lý bằng Java

### 6.1. Vì sao DTO thông thường có thể không đủ?

Xét lớp dữ liệu đầu vào:

```java
public final class CustomerUpdateRequest {
    public String nickname;
    public Boolean marketingOptIn;
}
```

Với cách bind thông thường của Jackson vào các trường tham chiếu chưa khởi tạo, cả `{}` và `{"nickname": null}` đều có thể tạo ra `nickname == null`. Quan sát mỗi giá trị Java lúc này không đủ để biết client đã bỏ trường hay gửi null.

Đổi `Boolean` thành primitive `boolean` cũng không giải quyết được vấn đề hiện diện. Một trường không được gán có giá trị Java ban đầu là `false`; còn cách xử lý JSON null phụ thuộc cấu hình deserializer.

Tương tự, không nên mặc định rằng `Optional<T>` là mô hình cập nhật ba trạng thái. Cần một thiết kế biểu diễn được riêng biệt:

```text
ABSENT          -> client không gửi trường
PRESENT_NULL    -> client gửi null
PRESENT_VALUE   -> client gửi một giá trị, kể cả [] hoặc false
```

Có thể dùng JSON tree, một kiểu wrapper có dấu hiệu `present`, hoặc deserializer chuyên biệt. Phần dưới dùng JSON tree để nhìn rõ thông tin đầu vào.

### 6.2. Ví dụ hàm xử lý giữ đủ ba trạng thái

Ví dụ dùng Java 17 và Jackson 2.x với package `com.fasterxml.jackson.databind`. Đây là phần diễn giải dữ liệu, không phải controller hoàn chỉnh. Không áp dụng thuật toán này như một trình xử lý JSON Merge Patch tổng quát.

```java
import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class CustomerUpdates {
    private static final Set<String> WRITABLE = Set.of(
        "displayName", "nickname", "tags", "marketingOptIn"
    );

    public record CustomerState(
        String displayName,
        String nickname,
        List<String> tags,
        boolean marketingOptIn
    ) {
        public CustomerState {
            tags = List.copyOf(tags);
        }
    }

    public static CustomerState apply(
        CustomerState current, JsonNode patch
    ) {
        if (patch == null || !patch.isObject()) {
            throw invalid("body", "phải là một JSON object");
        }

        var names = patch.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (!WRITABLE.contains(name)) {
                throw invalid(name, "không phải trường được phép ghi");
            }
        }

        String displayName = current.displayName();
        String nickname = current.nickname();
        List<String> tags = current.tags();
        boolean marketingOptIn = current.marketingOptIn();

        if (patch.has("displayName")) {
            displayName = readNonBlankText(
                patch.get("displayName"), "displayName", 80
            );
        }

        if (patch.has("nickname")) {
            JsonNode value = patch.get("nickname");
            nickname = value.isNull()
                ? null
                : readNonBlankText(value, "nickname", 40);
        }

        if (patch.has("tags")) {
            JsonNode value = patch.get("tags");
            if (!value.isArray()) {
                throw invalid("tags", "phải là mảng, không nhận null");
            }
            List<String> replacement = new ArrayList<>();
            for (int i = 0; i < value.size(); i++) {
                replacement.add(readNonBlankText(
                    value.get(i), "tags[" + i + "]", 30
                ));
            }
            tags = List.copyOf(replacement);
        }

        if (patch.has("marketingOptIn")) {
            JsonNode value = patch.get("marketingOptIn");
            if (!value.isBoolean()) {
                throw invalid("marketingOptIn", "phải là boolean");
            }
            marketingOptIn = value.booleanValue();
        }

        return new CustomerState(
            displayName, nickname, tags, marketingOptIn
        );
    }

    private static String readNonBlankText(
        JsonNode node, String field, int maxCodePoints
    ) {
        if (node == null || !node.isTextual()) {
            throw invalid(field, "phải là chuỗi, không nhận null");
        }
        String value = node.textValue().strip();
        int length = value.codePointCount(0, value.length());
        if (value.isBlank() || length > maxCodePoints) {
            throw invalid(
                field, "phải có từ 1 đến " + maxCodePoints + " ký tự"
            );
        }
        return value;
    }

    private static IllegalArgumentException invalid(
        String field, String message
    ) {
        return new IllegalArgumentException(field + ": " + message);
    }
}
```

Các quyết định quan trọng trong ví dụ:

- `has(...)` kiểm tra sự hiện diện, kể cả khi giá trị JSON là null. Sau khi biết trường có mặt, mã mới kiểm tra kiểu và giá trị.
- Nhánh boolean dùng `isBoolean()` trước `booleanValue()`, tránh vô tình chuyển chuỗi hoặc số thành lựa chọn nghiệp vụ.
- Mảng rỗng tạo danh sách mới rỗng; không bị hiểu thành “không có yêu cầu cập nhật”. Phần tử null hoặc chuỗi trắng bị từ chối.
- Hàm tạo trạng thái ứng viên mới, không sửa `current` trong quá trình kiểm tra. Một lỗi ở trường cuối không làm entity hiện tại bị thay đổi một phần.
- Độ dài chuỗi trong ví dụ tính theo Unicode code point sau `strip()`. Đây không phải số byte hay số ký tự hiển thị theo cụm; dự án cần thống nhất cùng quy tắc giữa API và lưu trữ.

Khi tích hợp với Spring, controller nhận JSON tree và media type đã công bố, service kiểm tra quyền cùng ràng buộc liên trường, rồi mới lưu trạng thái ứng viên trong giao dịch. Không dùng `IllegalArgumentException` như một response HTTP trực tiếp: tầng xử lý lỗi phải chuyển lỗi đầu vào thành mã trạng thái và cấu trúc lỗi nhất quán.

## 7. Schema phải tách “bắt buộc có mặt” và “cho phép null”

Hai chiều này độc lập:

| Bắt buộc có mặt? | Cho phép null? | Ví dụ khi xét riêng `nickname` |
| --- | --- | --- |
| Không | Không | Chấp nhận thiếu trường hoặc chuỗi hợp lệ |
| Có | Không | Phải gửi chuỗi hợp lệ |
| Không | Có | Chấp nhận thiếu trường, null hoặc chuỗi hợp lệ |
| Có | Có | Phải có trường; giá trị có thể là null |

Trong schema, không thể suy ra “cho phép null” từ việc trường không nằm trong danh sách `required`.

Ví dụ sau là đoạn schema cho request tạo mới, theo cú pháp OpenAPI 3.1:

```yaml
type: object
additionalProperties: false
required:
  - displayName
properties:
  displayName:
    type: string
    minLength: 1
    maxLength: 80
  nickname:
    type: [string, "null"]
    minLength: 1
    maxLength: 40
  tags:
    type: array
    default: []
    items:
      type: string
      minLength: 1
      maxLength: 30
  marketingOptIn:
    type: boolean
    default: false
```

`required` điều khiển sự hiện diện; `type` điều khiển giá trị được chấp nhận. Cú pháp kiểu hợp với null trên dùng trong [Schema Object của OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html#schema-object).

Đoạn schema này chưa mô tả hết việc chuẩn hóa khoảng trắng. Chuỗi `"   "` vẫn có độ dài lớn hơn 0. Quy tắc “chuẩn hóa rồi từ chối chuỗi trắng” cần được ghi trong mô tả trường và thực thi trong mã xử lý.

Với request PATCH minh họa, dùng schema riêng: bỏ yêu cầu có mặt của các trường có thể cập nhật và bỏ các default dành cho tạo mới. Nullability của từng trường vẫn theo bảng hợp đồng. Ngoài schema, phải ghi rằng thiếu trường nghĩa là giữ nguyên, `nickname: null` nghĩa là xóa biệt danh và mảng `tags` thay thế toàn bộ danh sách.

Không dùng một schema chung thiếu mô tả để đại diện đồng thời cho POST, PUT, PATCH và response nếu các thao tác có quy tắc khác nhau.

## 8. Response cũng cần quy ước ổn định

Request và response có thể dùng các quy ước khác nhau, nhưng sự khác biệt phải được giải thích.

Trong API minh họa, GET đầy đủ trả `nickname: null` khi khách hàng không có biệt danh. API không tự bỏ trường này khỏi response vì serializer được cấu hình loại null toàn cục. Nếu thay đổi cấu hình serializer làm trường biến mất, client có thể hiểu nhầm response đầy đủ thành response bị giới hạn trường.

Với một collection đã được truy vấn và không có phần tử, biểu diễn `[]` thường dễ sử dụng:

```json
{
  "items": [],
  "total": 0
}
```

`items: null` cần một ý nghĩa riêng nếu API hỗ trợ nó, chẳng hạn kết quả chưa được tính trong một hợp đồng cụ thể. Không luân phiên trả `null` và `[]` chỉ vì hai nhánh code khác nhau tạo ra hai kiểu đối tượng.

Một trường bị ẩn do quyền truy cập cũng không nên bị tự động diễn giải thành “giá trị thực tế là null”. Khi cần cho client phân biệt các trạng thái này, hợp đồng response phải cung cấp thông tin phù hợp mà không tiết lộ dữ liệu bị hạn chế.

Về cache và cơ chế phát hiện thay đổi, ứng dụng cần thống nhất biểu diễn chuẩn. Không xóa null hay sắp xếp lại cấu trúc tùy tiện trong một tầng trung gian nếu các bước kiểm tra điều kiện, chữ ký hoặc cache đang phụ thuộc vào nội dung biểu diễn.

## 9. Query parameter: thiếu, rỗng và chữ “null”

Các URI sau có đầu vào khác nhau:

```text
GET /customers
GET /customers?nickname=
GET /customers?nickname=null
```

- URI đầu không gửi tham số `nickname`.
- URI thứ hai gửi giá trị chuỗi rỗng theo cách diễn giải query parameter thông thường của API.
- URI thứ ba gửi chuỗi `null`; không tự trở thành JSON null vì query string không phải JSON object.

Nếu muốn lọc khách hàng không có biệt danh, có thể công bố một tham số rõ nghĩa như `hasNickname=false`, thay vì để client đoán phải gửi chuỗi rỗng hay chữ `null`.

Với phân trang, một hợp đồng có thể quy định: thiếu `pageSize` thì dùng `20`; `pageSize=` hoặc `pageSize=null` là lỗi; `pageSize=0` là lỗi vì phạm vi cho phép là 1 đến 100. Ở đây `0` bị từ chối do ràng buộc số lượng, không phải vì nó được xem là thiếu dữ liệu.

Cần kiểm tra cả bước bind tham số của framework. Nếu tầng bind đã chuyển chuỗi rỗng thành mặc định, service phía sau có thể không còn biết đầu vào ban đầu thuộc trường hợp nào.

## 10. Lỗi phải phản ánh quy tắc bị vi phạm

API nên trả lỗi có thể phân biệt các nguyên nhân sau:

| Đầu vào | Nguyên nhân có thể báo |
| --- | --- |
| Thiếu `displayName` trong POST | `FIELD_REQUIRED` |
| `displayName: null` | `NULL_NOT_ALLOWED` |
| `displayName: "   "` | `BLANK_NOT_ALLOWED` |
| `marketingOptIn: "false"` | `TYPE_MISMATCH` |
| `tags: null` | `NULL_NOT_ALLOWED` |
| `tags: [null]` | Lỗi ở phần tử `/tags/0` |
| Gửi `id` trong request ghi | `FIELD_NOT_WRITABLE` theo hợp đồng minh họa |

Ví dụ cấu trúc lỗi do API tự định nghĩa:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "path": "/displayName",
      "code": "NULL_NOT_ALLOWED",
      "message": "Tên hiển thị không được là null."
    }
  ]
}
```

Có thể chọn `400 Bad Request` cho lỗi đầu vào hoặc phân biệt JSON sai cú pháp bằng `400`, dữ liệu hợp lệ về cú pháp nhưng vi phạm hợp đồng bằng `422 Unprocessable Content`. Điều cần thiết là công bố chính sách và áp dụng nhất quán. Không để cùng một lỗi null lúc trả `400`, lúc thành lỗi máy chủ `500` vì đi qua hai đường bind khác nhau.

Nếu API chỉ hỗ trợ một media type cập nhật, request dùng media type khác phải đi qua chính sách thương lượng nội dung phù hợp; không âm thầm xử lý cùng một JSON theo ngữ nghĩa patch khác.

## 11. Quyền ghi và tính toàn vẹn khi cập nhật

Phân biệt thiếu và null không thay thế kiểm tra quyền. Một người có quyền sửa biệt danh không nhất thiết có quyền sửa vai trò hoặc trạng thái xác minh.

Tầng cập nhật nên dùng danh sách trường được phép ghi. Trường ngoài hợp đồng, kể cả được gửi dưới dạng null, vẫn phải đi qua quy tắc xử lý đã công bố. Ví dụ `{"role": null}` không được trở thành cách vượt qua kiểm tra quyền chỉ vì một đoạn code bỏ qua các giá trị null.

Với ràng buộc liên trường, cần kiểm tra trạng thái sau khi ghép request với dữ liệu hiện tại. Giả sử bật nhận tin qua email đòi hỏi email đã xác minh. Request thiếu trường email không có nghĩa là bỏ qua điều kiện này; máy chủ phải xét email đang có trên resource.

Đồng thời, “thiếu thì giữ nguyên” chỉ giải quyết ý nghĩa dữ liệu. Nó không tự ngăn hai client ghi đè thay đổi của nhau. Khi có yêu cầu kiểm soát cập nhật đồng thời, cần thêm cơ chế phiên bản hoặc điều kiện cập nhật phù hợp, rồi áp dụng bản cập nhật trên trạng thái đã được kiểm tra.

## 12. Ma trận kiểm thử theo ý định của client

Không chỉ kiểm thử một payload hợp lệ. Chọn trường hợp sao cho mỗi nhánh hợp đồng đều quan sát được bằng request và trạng thái resource sau đó.

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| POST thiếu `displayName` | Bị từ chối; không tạo resource |
| POST thiếu `marketingOptIn` | Resource mới có `false` |
| POST gửi `marketingOptIn: false` | Lưu đúng `false` |
| POST gửi `marketingOptIn: null` | Bị từ chối, không dùng mặc định |
| PATCH chỉ có `displayName` | Biệt danh, tags và lựa chọn tiếp thị không đổi |
| PATCH gửi `nickname: null` | Xóa biệt danh |
| PATCH gửi `nickname: ""` | Bị từ chối theo hợp đồng minh họa |
| PATCH gửi `nickname: "   "` | Bị từ chối sau chuẩn hóa |
| PATCH gửi `tags: []` | Xóa hết phần tử |
| PATCH gửi `tags: null` | Bị từ chối |
| PATCH gửi `tags: [null]` | Bị từ chối với vị trí phần tử |
| PATCH gửi `marketingOptIn: false` khi đang là true | Chuyển thành false |
| PATCH gửi `marketingOptIn: "false"` | Bị từ chối vì sai kiểu |
| PATCH có một trường hợp lệ và một trường lỗi | Không lưu thay đổi một phần |
| PATCH gửi `{}` | Không thay đổi trạng thái theo hợp đồng minh họa |
| PATCH gửi JSON `null` ở gốc | Bị từ chối vì body phải là object |
| GET sau khi xóa biệt danh | Trả `nickname: null` theo quy ước response |

Đặc biệt, kiểm thử thiếu trường phải gửi JSON thật sự không có tên trường. Tạo DTO rồi để serializer tự quyết định có ghi null hay không có thể vô tình biến ca “thiếu” thành ca “null”.

Kiểm thử tại biên HTTP giúp quan sát cả JSON parser, binding, validation, service, lưu trữ và serialization. Khi logic đã được tách thành hàm như `CustomerUpdates.apply`, có thể bổ sung kiểm thử đơn vị cho bảng quy tắc mà không phải dựng cả ứng dụng.

Với cập nhật kiểu gán giá trị, gửi lại cùng payload trong cùng điều kiện thường cho cùng trạng thái cuối. Tuy nhiên không suy ra mọi PATCH đều idempotent: thao tác thêm phần tử, sự kiện phát sinh và quy tắc xử lý lặp cần được thiết kế riêng.

## 13. Các lỗi thiết kế thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| DTO gộp thiếu và null thành một giá trị | Không phân biệt giữ nguyên và xóa | Giữ thông tin hiện diện ở biên API |
| Mặc định lại mọi trường thiếu khi PATCH | Ghi đè dữ liệu không được yêu cầu sửa | Chỉ áp dụng mặc định theo thao tác đã công bố |
| Đổi mọi chuỗi rỗng thành null toàn cục | Mất lựa chọn biểu diễn và che lỗi dữ liệu | Chuẩn hóa theo từng trường |
| Xem `false` hoặc `0` là không có dữ liệu | Đảo lựa chọn hoặc thay số client gửi | Kiểm tra hiện diện và kiểu dữ liệu |
| Cho rằng `required` cũng cấm null | Schema chấp nhận dữ liệu ngoài ý muốn | Thiết kế riêng presence và nullability |
| Chỉ khai báo schema default | Tài liệu và runtime không thống nhất | Thực thi mặc định và kiểm thử request thiếu trường |
| Sao chép request trực tiếp vào entity | Ghi nhầm trường hoặc sửa một phần trước khi lỗi | Dùng danh sách trường ghi và trạng thái ứng viên |
| Cấu hình response loại null mà không xét hợp đồng | Client không biết trường vắng vì lý do gì | Quy định cách serialize cho từng loại response |
| Dùng chung quy tắc cho mọi media type patch | Null bị hiểu thành hai thao tác khác nhau | Gắn ngữ nghĩa với đúng định dạng request |

## 14. Cách áp dụng khi thiết kế một trường mới

Khi thêm một trường vào REST API, hãy viết được câu trả lời cụ thể cho các điểm sau trước khi triển khai:

1. Trường có bắt buộc xuất hiện trong request tạo mới, thay thế và cập nhật từng phần không?
2. Nếu trường có mặt với null, máy chủ lưu null, xóa dữ liệu, dùng mặc định hay trả lỗi?
3. Những dạng rỗng nào hợp lệ: chuỗi rỗng, chuỗi trắng, mảng rỗng hoặc object rỗng?
4. Nếu có mặc định, điều kiện và thời điểm áp dụng là gì? Ai chịu trách nhiệm thực thi?
5. DTO hoặc mô hình đầu vào có giữ được thông tin hiện diện cho tới lúc quyết định thao tác không?
6. Response thể hiện chưa có giá trị như thế nào, và client có phân biệt được với trường bị lược bỏ không?
7. Kiểm thử HTTP nào chứng minh từng quy tắc và bảo đảm không mất dữ liệu ngoài ý muốn?

Một thiết kế rõ ràng giữ nguyên ý định của client từ JSON đầu vào đến trạng thái đã lưu. Thiếu trường, null và rỗng chỉ được gộp khi hợp đồng chủ động quy định rằng chúng có cùng ý nghĩa; giá trị mặc định chỉ được áp dụng khi đúng điều kiện của thao tác.
