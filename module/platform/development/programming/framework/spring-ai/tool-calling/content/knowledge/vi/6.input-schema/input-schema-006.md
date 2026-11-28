# Biểu diễn required, optional và nullable

Khi mô hình gọi một công cụ, dữ liệu đầu vào thường được biểu diễn dưới dạng một JSON object theo schema mà ứng dụng cung cấp. Ba khái niệm `required`, `optional` và `nullable` quyết định cách hiểu dữ liệu đó: một trường có bắt buộc xuất hiện hay không, và nếu xuất hiện thì có được phép mang giá trị `null` hay không.

Ba khái niệm này không đồng nghĩa. `required` nói về sự hiện diện của thuộc tính; `nullable` nói về tập giá trị thuộc tính được phép nhận; `optional` có nghĩa thuộc tính có thể vắng mặt. Nếu nhầm lẫn, ứng dụng có thể bỏ qua dữ liệu cần thiết, áp dụng giá trị mặc định sai hoặc hiểu nhầm yêu cầu xóa dữ liệu thành yêu cầu không thay đổi dữ liệu.

Trong Spring AI, `@ToolParam(required = false)` giúp khai báo tham số không bắt buộc trong định nghĩa công cụ. Việc cho phép giá trị JSON `null` là một yêu cầu khác và cần được thể hiện, kiểm tra theo schema thực tế mà integration gửi đến provider. Ứng dụng vẫn phải xử lý trường hợp thiếu giá trị và xác thực dữ liệu ở runtime.

## Phân biệt ba khái niệm

- **Required:** thuộc tính phải có mặt trong JSON object. Giá trị của nó vẫn có thể là `null` nếu schema cho phép.
- **Optional:** thuộc tính có thể không xuất hiện trong JSON object. Nếu thuộc tính xuất hiện, giá trị phải tuân theo schema của thuộc tính đó.
- **Nullable:** thuộc tính được phép nhận JSON `null`. Nullable không nói thuộc tính có thể bị bỏ qua hay không.

Ví dụ, với object có các thuộc tính `query`, `limit` và `cursor`:

| Trạng thái | `query` | `limit` | `cursor` |
| --- | --- | --- | --- |
| Required, non-null | Phải xuất hiện và phải là chuỗi | — | — |
| Optional, non-null | — | Có thể vắng mặt; nếu có phải là số nguyên | — |
| Optional, nullable | — | — | Có thể vắng mặt; nếu có là chuỗi hoặc `null` |

Điểm cần nhớ là một thuộc tính có thể vừa `required` vừa `nullable`. Ví dụ, API cập nhật hồ sơ có thể yêu cầu client luôn gửi trường `middleName`, nhưng cho phép giá trị `null` để biểu thị người dùng không có tên đệm. Ngược lại, một trường `nickname` có thể optional và non-null: nếu không muốn cập nhật biệt danh thì bỏ trường; nếu gửi thì phải là chuỗi.

## Bốn trạng thái thường gặp

Kết hợp sự hiện diện và khả năng nhận `null` tạo ra bốn cách khai báo phổ biến:

| Khai báo | Thuộc tính có thể vắng mặt? | Có thể nhận `null`? | Ví dụ ý nghĩa |
| --- | --- | --- | --- |
| Required, non-null | Không | Không | Mã đơn hàng bắt buộc phải có và phải là chuỗi hợp lệ. |
| Required, nullable | Không | Có | Trường ghi chú phải được gửi; `null` có nghĩa xóa ghi chú. |
| Optional, non-null | Có | Không | Giới hạn số kết quả; bỏ qua để dùng mặc định, nếu gửi phải là số nguyên. |
| Optional, nullable | Có | Có | Bộ lọc ngày kết thúc có thể không gửi hoặc gửi `null` để biểu thị không giới hạn. |

Một JSON object có thể thể hiện các trạng thái này bằng cách kết hợp `properties` và mảng `required` trong JSON Schema. Kiểu dữ liệu cho phép `null` phải được khai báo riêng.

## Biểu diễn bằng JSON Schema

Trong JSON Schema, `required` là một danh sách ở cấp object, chứa tên những thuộc tính bắt buộc. Nó không phải một thuộc tính boolean bên trong từng property. Kiểu dữ liệu của property mô tả giá trị được phép nhận.

Ví dụ:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Từ khóa cần tìm"
    },
    "limit": {
      "type": "integer",
      "description": "Số kết quả tối đa; bỏ qua để dùng mặc định"
    },
    "cursor": {
      "type": ["string", "null"],
      "description": "Con trỏ trang tiếp theo; có thể bỏ qua hoặc gửi null nếu không có"
    }
  },
  "required": ["query"]
}
```

Trong schema này:

- `query` phải xuất hiện vì tên trường nằm trong `required`; kiểu `string` không cho phép `null`.
- `limit` không nằm trong `required`, nên có thể bị bỏ qua. Nếu xuất hiện, giá trị phải là số nguyên; `null` không hợp lệ theo schema này.
- `cursor` cũng có thể bị bỏ qua. Nếu xuất hiện, giá trị có thể là chuỗi hoặc `null` vì kiểu được khai báo là `string` hoặc `null`.

Để biểu diễn một trường required nhưng nullable, thêm tên trường vào `required` và cho phép kiểu `null`:

```json
{
  "type": "object",
  "properties": {
    "middleName": {
      "type": ["string", "null"],
      "description": "Tên đệm; null nếu người dùng không có tên đệm"
    }
  },
  "required": ["middleName"]
}
```

Một số schema hoặc API có thể biểu diễn union type bằng `anyOf` thay vì mảng `type`, ví dụ:

```json
{
  "anyOf": [
    { "type": "string" },
    { "type": "null" }
  ]
}
```

Đây là các cách biểu diễn khái niệm trong JSON Schema. Provider có thể hỗ trợ một tập con hoặc yêu cầu cấu trúc khác trong một chế độ cụ thể. Cần kiểm tra schema cuối cùng được gửi đi và giới hạn của API đang sử dụng.

## Ánh xạ vào tham số `@Tool` trong Spring AI

Với phương thức công cụ được đánh dấu `@Tool`, `@ToolParam` mô tả từng tham số và cho biết tham số có bắt buộc hay không. `required` mặc định là `true`; đặt `required = false` khi mô hình có thể bỏ qua tham số.

Ví dụ một truy vấn có tham số bắt buộc và tham số tùy chọn:

```java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class CatalogTools {

    @Tool(description = "Tìm sản phẩm theo từ khóa và giới hạn số kết quả")
    public String searchProducts(
            @ToolParam(description = "Từ khóa tên hoặc mã sản phẩm cần tìm")
            String query,
            @ToolParam(
                    description = "Số kết quả tối đa từ 1 đến 20; bỏ qua để dùng mặc định 10",
                    required = false)
            Integer limit) {

        int effectiveLimit = limit == null ? 10 : limit;
        if (query == null || query.isBlank()) {
            throw new IllegalArgumentException("query không được để trống");
        }
        if (effectiveLimit < 1 || effectiveLimit > 20) {
            throw new IllegalArgumentException("limit phải nằm trong khoảng 1 đến 20");
        }

        return "Tìm " + query + " với giới hạn " + effectiveLimit;
    }
}
```

Trong ví dụ, `query` là required và `limit` là optional. `Integer` được dùng thay cho `int` vì kiểu wrapper có thể biểu diễn `null` trong Java. Khi tham số tùy chọn bị bỏ qua, mã ứng dụng áp dụng giá trị mặc định 10.

### `required = false` không đồng nghĩa nullable

Đây là điểm dễ nhầm nhất khi khai báo tool. `@ToolParam(required = false)` nói rằng mô hình có thể không gửi thuộc tính. Nó không nên được hiểu là một cam kết độc lập rằng JSON `null` cũng hợp lệ với mọi schema và mọi provider.

Ví dụ, nếu schema cuối cùng khai báo:

```json
{
  "type": "object",
  "properties": {
    "limit": { "type": "integer" }
  },
  "required": []
}
```

thì `{}` hợp lệ, nhưng `{"limit": null}` không hợp lệ vì kiểu của `limit` chỉ là `integer`. Nếu muốn chấp nhận cả hai dạng, schema phải cho phép `null` trong kiểu của property, và callback phải có cách xử lý trường hợp đó.

Không nên giả định rằng một annotation nullable của Java, một kiểu wrapper hoặc `Optional<T>` luôn được chuyển thành JSON Schema nullable giống nhau ở mọi phiên bản Spring AI. Hãy xem schema mà tool callback thực sự công bố và thử dữ liệu đầu vào với đúng provider/integration đang dùng.

## Nullable trong Java và JSON là hai tầng khác nhau

Java có nhiều cách thể hiện khả năng vắng giá trị, nhưng chúng không tự động tương đương với các trạng thái trong JSON Schema:

| Java | Có thể chứa `null` ở runtime? | Ghi chú khi thiết kế tool |
| --- | --- | --- |
| `int`, `boolean` | Không | Không biểu diễn trực tiếp được giá trị null; không phù hợp nếu cần phân biệt thiếu với `0` hoặc `false`. |
| `Integer`, `Boolean` | Có | Có thể nhận `null`, nhưng schema vẫn phải cho phép null nếu muốn mô hình gửi JSON null. |
| `String`, DTO, collection | Có | Có thể là null ở runtime; kiểu Java tham chiếu không tự chứng minh schema cho phép null. |
| `Optional<T>` | Bản thân wrapper không dùng null trong cách dùng thông thường | Cách ánh xạ sang schema và cách bind phụ thuộc framework; không nên dùng thay cho `required = false` nếu chưa xác nhận hỗ trợ. |

`null` trong Java là một giá trị tham chiếu đặc biệt. `null` trong JSON là một literal có mặt trong dữ liệu. Thuộc tính không xuất hiện trong JSON lại là một trạng thái khác. Khi framework bind JSON vào tham số Java, hai trường hợp “không có thuộc tính” và “thuộc tính có giá trị null” có thể cùng trở thành một giá trị Java `null`. Nếu nghiệp vụ cần phân biệt hai trường hợp, một tham số Java đơn lẻ có thể không giữ đủ thông tin.

## Phân biệt bỏ qua, giữ nguyên và xóa giá trị

Sự khác biệt giữa absent và null đặc biệt quan trọng với công cụ cập nhật dữ liệu. Hãy xét công cụ cập nhật hồ sơ có trường `displayName`:

| Đầu vào | Ý nghĩa nghiệp vụ có thể chọn |
| --- | --- |
| Không có `displayName` | Không thay đổi tên hiển thị hiện tại. |
| `"displayName": "Minh Anh"` | Đặt tên hiển thị thành “Minh Anh”. |
| `"displayName": null` | Xóa tên hiển thị, nếu nghiệp vụ cho phép. |
| `"displayName": ""` | Gửi chuỗi rỗng; ứng dụng phải quy định có hợp lệ hay không. |

Nếu callback chuyển cả absent và null thành `null`, ứng dụng không thể tự biết người gọi muốn giữ nguyên hay xóa trường. Có ba cách thiết kế thường dùng:

1. **Không cần phân biệt:** quy ước absent và null cùng có nghĩa là dùng giá trị mặc định hoặc không lọc. Ghi rõ quy ước này trong description và xử lý nhất quán.
2. **Dùng cờ thao tác tường minh:** thêm trường như `clearDisplayName` hoặc `updateDisplayName` để biểu diễn ý định cập nhật/xóa. Kiểm tra các tổ hợp trường để tránh yêu cầu mâu thuẫn.
3. **Giữ trạng thái hiện diện của JSON:** dùng callback tùy chỉnh nhận dữ liệu JSON thô hoặc một cấu trúc giữ cả `containsKey` và value, nếu nghiệp vụ cần phân biệt chính xác absent với explicit null.

Ví dụ dùng cờ thao tác:

```json
{
  "type": "object",
  "properties": {
    "updateDisplayName": {
      "type": "boolean",
      "description": "Có thực hiện cập nhật tên hiển thị hay không"
    },
    "displayName": {
      "type": ["string", "null"],
      "description": "Tên mới; null để xóa tên nếu updateDisplayName là true"
    }
  },
  "required": ["updateDisplayName", "displayName"]
}
```

Trong thiết kế này, cả hai trường luôn xuất hiện. Ứng dụng kiểm tra `updateDisplayName`; nếu là `false`, bỏ qua thay đổi, nếu là `true` thì áp dụng `displayName`, bao gồm trường hợp null để xóa. Đây là một hợp đồng rõ ràng hơn khi thao tác có tác động phụ.

## Giá trị mặc định thuộc về ứng dụng

JSON Schema có thể chứa metadata `default` trong một số trường hợp, nhưng không nên giả định provider sẽ tự điền giá trị đó vào tool call. `@ToolParam(description = "... mặc định 10 ...", required = false)` cũng chỉ giúp mô hình hiểu quy ước; nó không tự gán 10 cho biến Java.

Hãy áp dụng mặc định trong callback hoặc service:

```java
int effectiveLimit = limit == null ? 10 : limit;
```

Nếu tham số có thể vắng mặt, mô tả nên nói rõ hành vi mặc định. Đồng thời, mã ứng dụng phải kiểm tra giới hạn và không để giá trị ngoài phạm vi đi vào truy vấn. Với thao tác cập nhật, không nên dùng giá trị mặc định nếu nó có thể làm thay đổi dữ liệu ngoài ý muốn.

## Chế độ strict và giới hạn của provider

Một số API của nhà cung cấp có chế độ strict cho tool schema hoặc structured output. Chế độ này có thể áp đặt các ràng buộc bổ sung, chẳng hạn yêu cầu mọi thuộc tính phải được liệt kê trong `required` và dùng union với `null` để biểu diễn trường mà ứng dụng xem là tùy chọn. Khi đó, khái niệm optional ở hợp đồng nghiệp vụ có thể được biểu diễn khác với schema JSON thông thường.

Vì vậy, khi bật strict mode:

- Đọc yêu cầu schema của đúng provider và model.
- Xác nhận integration Spring AI đang dùng có chuyển đổi schema theo chế độ đó hay không.
- Không suy luận rằng mọi schema hợp lệ theo JSON Schema đều được provider chấp nhận.
- Kiểm tra tool call thực tế để biết provider gửi trường bị bỏ qua, gửi null hay áp dụng quy tắc riêng nào.

Nếu schema bị từ chối, hãy xem lỗi của provider và schema cuối cùng sau chuyển đổi. Việc sửa annotation mà không kiểm tra payload có thể che khuất nguyên nhân thực sự.

## Kiểm tra và chuẩn hóa đầu vào trong ứng dụng

Sau khi nhận tool call, ứng dụng nên chuẩn hóa dữ liệu trước khi gọi service. Quy trình có thể gồm:

1. Xác định các trường bắt buộc có mặt và có giá trị hợp lệ.
2. Phân biệt absent, null, chuỗi rỗng và collection rỗng theo quy ước nghiệp vụ.
3. Áp dụng giá trị mặc định cho trường optional nếu trường đó bị bỏ qua.
4. Kiểm tra kiểu, miền giá trị, giới hạn số lượng và định dạng.
5. Xác thực quyền trên tài nguyên theo principal và tenant lấy từ ngữ cảnh tin cậy.
6. Chỉ sau khi các bước trên thành công mới gọi service thực hiện thao tác.

Không dùng `required`, nullable hoặc JSON Schema làm cơ chế phân quyền. Schema chỉ mô tả cấu trúc đầu vào; service vẫn phải kiểm tra người dùng có được phép đọc hoặc thay đổi tài nguyên hay không.

## Kiểm thử required, optional và nullable

Hãy kiểm thử theo ma trận trạng thái thay vì chỉ gửi một JSON hợp lệ. Với mỗi trường, xác định các trường hợp cần thử:

| Trường hợp | JSON mẫu | Điều cần xác nhận |
| --- | --- | --- |
| Thiếu trường required | `{}` | Bị từ chối ở bước xác thực/schema phù hợp. |
| Có trường required hợp lệ | `{"query":"keyboard"}` | Được chuyển đổi và xử lý đúng. |
| Thiếu trường optional | `{"query":"keyboard"}` | Ứng dụng áp dụng mặc định đã định nghĩa. |
| Optional có giá trị hợp lệ | `{"query":"keyboard","limit":5}` | Giá trị được chuyển đúng kiểu. |
| Optional gửi null nhưng schema không nullable | `{"query":"keyboard","limit":null}` | Bị từ chối hoặc xử lý theo hành vi integration đã xác nhận; không âm thầm coi là số 0. |
| Optional nullable gửi null | `{"query":"keyboard","cursor":null}` | Callback nhận và xử lý null theo quy ước. |
| Required nullable gửi null | `{"middleName":null}` | Thuộc tính vẫn được coi là có mặt và null được chấp nhận. |
| Chuỗi rỗng | `{"query":""}` | Được kiểm tra theo quy tắc miền, không nhầm với absent hoặc null. |

Các kiểm thử nên bao gồm:

- Kiểm tra schema công bố: tên thuộc tính, danh sách `required`, kiểu dữ liệu và union null.
- Kiểm tra chuyển đổi: absent và explicit null được bind ra sao trong phiên bản Spring AI hiện tại.
- Kiểm tra giá trị mặc định: tham số optional bị bỏ qua có được ứng dụng chuẩn hóa đúng không.
- Kiểm tra lỗi: dữ liệu sai kiểu, sai định dạng, vượt giới hạn hoặc mâu thuẫn giữa các trường.
- Kiểm tra nghiệp vụ: absent có giữ nguyên dữ liệu, null có xóa dữ liệu và chuỗi rỗng có bị từ chối đúng quy ước không.
- Kiểm tra bảo mật: dữ liệu đầu vào hợp lệ về schema nhưng trỏ đến tài nguyên ngoài quyền truy cập vẫn phải bị từ chối.

Nên dùng unit test để kiểm tra chuẩn hóa và quy tắc nghiệp vụ, test callback để kiểm tra chuyển đổi đầu vào, và integration test với provider để xác nhận schema thực tế được chấp nhận. Không phụ thuộc hoàn toàn vào một lần gọi model thật vì mô hình có thể chọn không gọi công cụ nếu prompt không cần thiết.

## Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mô hình không gửi một trường cần thiết | Trường không nằm trong `required` hoặc description chưa rõ | Xác định lại hợp đồng và khai báo required đúng. |
| Provider từ chối JSON null | Property chỉ khai báo kiểu `string`, `integer` hoặc kiểu không bao gồm null | Cập nhật schema theo cú pháp provider hỗ trợ hoặc yêu cầu mô hình bỏ trường. |
| Tham số Java nhận null dù người gọi bỏ qua trường | Binding ánh xạ absent thành null | Áp dụng mặc định trong callback và không suy ra ý định xóa từ giá trị null. |
| Không phân biệt được absent và explicit null | Cả hai được bind vào cùng giá trị Java null | Dùng callback giữ JSON thô hoặc thêm trường/cờ thao tác tường minh. |
| Tham số optional thành 0 hoặc false ngoài ý muốn | Dùng kiểu nguyên thủy không thể biểu diễn null | Dùng wrapper `Integer`, `Boolean` nếu cần nhận biết không có giá trị. |
| Schema hợp lệ nhưng provider vẫn từ chối | Provider có giới hạn schema hoặc strict mode riêng | Kiểm tra schema cuối cùng và tài liệu của endpoint/model. |
| Ứng dụng dùng giá trị mặc định sai | Mô tả default nhưng không triển khai trong code | Chuẩn hóa giá trị trong callback/service và kiểm thử. |

## Nguyên tắc ghi nhớ

- `required` quyết định thuộc tính có phải xuất hiện trong JSON object hay không.
- `optional` nghĩa là thuộc tính có thể vắng mặt; nếu xuất hiện, giá trị vẫn phải đúng schema.
- `nullable` cho phép thuộc tính có giá trị JSON `null`; nó không làm thuộc tính trở thành optional.
- Một trường có thể required và nullable, hoặc optional và non-null.
- `@ToolParam(required = false)` khai báo tham số không bắt buộc; không tự động chứng minh JSON null được chấp nhận.
- Kiểu wrapper trong Java có thể chứa null ở runtime, nhưng schema phải cho phép null một cách độc lập.
- Absent, null, chuỗi rỗng và giá trị mặc định cần có ý nghĩa nghiệp vụ rõ ràng.
- Nếu cần phân biệt absent với explicit null, giữ trạng thái hiện diện của JSON hoặc thiết kế hợp đồng có cờ thao tác.
- Kiểm tra schema cuối cùng, dữ liệu runtime và quyền truy cập trước khi thực thi công cụ.

Thiết kế đúng `required`, `optional` và `nullable` giúp mô hình gửi dữ liệu đúng hợp đồng, đồng thời giúp ứng dụng diễn giải chính xác ý định của yêu cầu. Đây là nền tảng để các công cụ tìm kiếm, lọc và cập nhật dữ liệu hoạt động ổn định trong những tình huống thực tế.
