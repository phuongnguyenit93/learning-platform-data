# Xử lý trường thiếu, giá trị rỗng và giá trị mặc định

Trong ứng dụng MVC, dữ liệu đi qua nhiều ranh giới: trình duyệt gửi request, Controller binding dữ liệu vào đối tượng đầu vào, dịch vụ ứng dụng thực hiện nghiệp vụ, Model bảo vệ quy tắc và View hiển thị kết quả. Một hợp đồng dữ liệu cần mô tả rõ ý nghĩa của từng trường khi trường đó có mặt, bị bỏ qua, mang giá trị null hoặc chứa chuỗi rỗng.

Những trường hợp này không đồng nghĩa với nhau. Ví dụ, khi cập nhật tên hiển thị, người dùng có thể không gửi trường đó vì không muốn thay đổi; gửi null để xóa tên tùy chọn; gửi chuỗi rỗng để chủ động xóa nội dung; hoặc bỏ qua trường và để máy chủ áp dụng giá trị mặc định. Nếu Controller hoặc Model gộp các trường hợp này thành một giá trị duy nhất, ứng dụng có thể vô tình xóa dữ liệu, ghi đè giá trị người dùng hoặc áp dụng mặc định sai.

Bài học thuộc module **MODEL_VIEW_CONTROLLER**, tập trung vào hợp đồng dữ liệu trong ứng dụng web MVC: cách Controller tiếp nhận dữ liệu, cách Model hiểu ý định cập nhật, cách View biểu diễn trạng thái và cách kiểm thử các trường hợp biên.

## 1. Bốn trạng thái cần phân biệt

Một trường dữ liệu thường có ít nhất bốn trạng thái cần được xem xét:

| Trạng thái | Ý nghĩa thường gặp | Ví dụ JSON |
|---|---|---|
| **Thiếu (absent / omitted)** | Trường không xuất hiện trong payload | `{}` |
| **Null** | Trường có xuất hiện nhưng giá trị được khai báo là không có | `{"nickname": null}` |
| **Rỗng (empty)** | Có giá trị nhưng không chứa phần tử hoặc ký tự | `{"nickname": ""}`, `{"tags": []}` |
| **Mặc định (default)** | Giá trị được hệ thống áp dụng khi hợp đồng quy định không nhận được giá trị khác | Có thể là `"status": "DRAFT"` hoặc được máy chủ tự gán |

Chuỗi chỉ chứa khoảng trắng, ví dụ chuỗi gồm ba dấu cách, là một trường hợp khác với chuỗi rỗng. Trong nhiều nghiệp vụ, chuỗi khoảng trắng được coi là không hợp lệ hoặc cần chuẩn hóa bằng trim. Tuy nhiên, không nên tự động trim mọi trường vì khoảng trắng có thể có ý nghĩa trong một số dữ liệu.

Cần hiểu rằng “giá trị mặc định” không phải một biểu diễn JSON đặc biệt. Nó là quy tắc của hợp đồng hoặc ứng dụng. Giá trị mặc định có thể được áp dụng ở client, Controller, DTO, dịch vụ ứng dụng, Model hoặc database. Nơi áp dụng phải được xác định rõ để tránh các tầng đưa ra mặc định khác nhau.

### 1.1. Trường thiếu không giống null

Xét hai payload:

~~~json
{}
~~~

~~~json
{
  "nickname": null
}
~~~

Payload đầu không nói gì về nickname. Trong một lệnh cập nhật từng phần, điều này thường có nghĩa là giữ nguyên giá trị hiện tại. Payload thứ hai thể hiện rõ trường nickname có mặt và mang giá trị null; hợp đồng có thể định nghĩa đó là yêu cầu xóa giá trị nếu trường cho phép null.

Nếu DTO Java chỉ có một thuộc tính String và deserializer đặt cả trường thiếu lẫn trường null thành null, Controller có thể không phân biệt được hai ý định này. Muốn phân biệt, cần dùng một kiểu biểu diễn hoặc cơ chế binding giữ được thông tin trường có xuất hiện hay không.

### 1.2. Null không giống chuỗi rỗng

~~~json
{
  "nickname": null
}
~~~

~~~json
{
  "nickname": ""
}
~~~

Null thường biểu thị không có giá trị. Chuỗi rỗng là một giá trị chuỗi có độ dài bằng 0. Hợp đồng có thể quy định cả hai đều có nghĩa xóa nickname, nhưng cũng có thể coi null là xóa còn chuỗi rỗng là không hợp lệ. Quyết định phải xuất phát từ ngữ nghĩa nghiệp vụ.

### 1.3. Giá trị mặc định không nhất thiết là null hoặc rỗng

Ví dụ, khi tạo một công việc, nếu người dùng không chọn trạng thái, hệ thống có thể tạo công việc ở trạng thái DRAFT. DRAFT là giá trị mặc định có ý nghĩa nghiệp vụ. Không nên để mỗi tầng tự chọn một giá trị khác nhau, chẳng hạn View mặc định OPEN còn Model mặc định DRAFT.

Giá trị mặc định nên được công bố trong hợp đồng và được áp dụng tại nơi có thẩm quyền. Với quy tắc nghiệp vụ, Model hoặc dịch vụ ứng dụng thường là nơi phù hợp; giá trị mặc định thuần giao diện có thể được khởi tạo trong View.

## 2. Vì sao sự phân biệt này quan trọng trong MVC?

Một request đi qua các tầng và mỗi tầng có thể diễn giải dữ liệu theo cách khác nhau:

~~~mermaid
flowchart TD
    A["View: biểu mẫu hoặc client gửi dữ liệu"] --> B["HTTP request"]
    B --> C["Controller: binding và nhận diện trường"]
    C --> D["Request DTO / Command"]
    D --> E["Application Service"]
    E --> F["Model: áp dụng quy tắc và mặc định nghiệp vụ"]
    F --> G["Persistence"]
    G --> H["Kết quả"]
    H --> I["ViewModel / Response DTO"]
    I --> J["View: hiển thị kết quả"]
~~~

Nếu Controller tự gán chuỗi rỗng thành null mà không có quy tắc, Model sẽ không biết người dùng thực sự muốn xóa hay bỏ qua. Nếu DTO dùng kiểu số nguyên nguyên thủy, trường thiếu có thể bị gán thành 0 và khiến Model hiểu rằng người dùng đã gửi số 0. Nếu database có default nhưng ứng dụng gửi null tường minh, database có thể không áp dụng default như người thiết kế mong muốn.

Phân biệt đúng giúp:

- Giữ nguyên dữ liệu khi client không yêu cầu thay đổi.
- Cho phép xóa một giá trị tùy chọn có chủ đích.
- Không biến dữ liệu rỗng thành một giá trị nghiệp vụ hợp lệ ngoài ý muốn.
- Áp dụng mặc định nhất quán khi tạo mới.
- Trả lỗi validation rõ ràng cho trường bắt buộc.
- Giữ tương thích khi thêm trường mới vào API.
- Tránh ghi đè dữ liệu khi nhiều client dùng các phiên bản hợp đồng khác nhau.

## 3. Trường thiếu trong JSON và hợp đồng API

JSON cho phép một thuộc tính bị bỏ qua hoàn toàn hoặc xuất hiện với giá trị null. Ý nghĩa của hai dạng này do API quy định.

Ví dụ API tạo công việc:

~~~json
{
  "title": "Chuẩn bị báo cáo"
}
~~~

Hợp đồng có thể quy định:

- title là bắt buộc.
- description có thể bị bỏ qua; khi bị bỏ qua, hệ thống lưu null hoặc chuỗi rỗng theo mô hình dữ liệu đã chọn.
- priority nếu bị bỏ qua sẽ mặc định NORMAL.
- dueDate nếu bị bỏ qua sẽ không đặt thời hạn.
- status do hệ thống khởi tạo DRAFT; client không được tự gửi status khi tạo.

Hợp đồng nên mô tả riêng cho từng trường:

| Thuộc tính | Bắt buộc? | Cho phép null? | Cho phép rỗng? | Khi bị bỏ qua |
|---|---|---|---|---|
| title | Có | Không | Không | Trả lỗi |
| description | Không | Có | Có hoặc chuẩn hóa theo quy ước | Không có mô tả |
| priority | Không | Không | Không áp dụng | Mặc định NORMAL |
| dueDate | Không | Có | Không áp dụng | Không đặt thời hạn |
| status | Client không được gửi | Không | Không áp dụng | Server đặt DRAFT |

Bảng này là ví dụ thiết kế, không phải quy tắc chung cho mọi ứng dụng. Một API có thể chọn cách khác, miễn là hành vi được mô tả rõ và nhất quán.

### 3.1. Quy tắc cho request tạo mới

Trong thao tác tạo mới, trường bị bỏ qua thường được xử lý theo một trong các cách:

- Áp dụng giá trị mặc định đã công bố.
- Lưu trạng thái không có giá trị nếu trường là tùy chọn.
- Trả lỗi nếu trường bắt buộc.
- Tự tạo giá trị từ hệ thống, chẳng hạn ID, thời điểm tạo hoặc trạng thái ban đầu.

Không nên nhận các trường do server quản lý như ownerId, createdAt, role hoặc trạng thái phê duyệt từ payload công khai nếu client không có quyền thay đổi chúng. Việc trường bị thiếu hay null không được dùng để quyết định quyền.

### 3.2. Quy tắc cho request cập nhật

Trong cập nhật toàn bộ tài nguyên, chẳng hạn PUT, hợp đồng thường yêu cầu client gửi một biểu diễn đầy đủ của tài nguyên theo quy ước endpoint. Trường bị bỏ qua có thể được xem là thiếu dữ liệu hoặc được xử lý theo schema của API.

Trong cập nhật một phần, chẳng hạn PATCH, trường bị bỏ qua thường có nghĩa là không thay đổi trường đó. Tuy nhiên, ý nghĩa của null và chuỗi rỗng phải được định nghĩa theo định dạng patch được chọn.

Không nên dùng cùng một DTO mơ hồ cho cả tạo mới, thay thế toàn bộ và cập nhật từng phần. Ba thao tác có ngữ nghĩa khác nhau và thường cần hợp đồng đầu vào khác nhau.

## 4. PUT, PATCH và ý nghĩa của null

HTTP định nghĩa PUT và PATCH có mục đích khác nhau. PUT thường thay thế biểu diễn của tài nguyên tại URI; PATCH áp dụng một tập thay đổi lên tài nguyên. Ý nghĩa chính xác vẫn phụ thuộc hợp đồng endpoint và định dạng payload.

### 4.1. PUT: biểu diễn đầy đủ theo hợp đồng

Giả sử endpoint PUT yêu cầu toàn bộ dữ liệu có thể chỉnh sửa:

~~~http
PUT /api/tasks/42
Content-Type: application/json
~~~

~~~json
{
  "title": "Chuẩn bị báo cáo quý",
  "description": "Tổng hợp số liệu",
  "priority": "HIGH"
}
~~~

Nếu description bị bỏ qua, API có thể trả lỗi vì biểu diễn không đầy đủ, hoặc coi đó là không có mô tả theo schema. Không nên để hành vi này ngẫu nhiên phụ thuộc vào cách DTO được khởi tạo.

PUT được định nghĩa là idempotent theo ngữ nghĩa HTTP: gửi cùng một yêu cầu nhiều lần có hiệu quả trạng thái tương đương. Điều đó không bắt buộc response phải giống hệt nhau.

### 4.2. PATCH: chỉ gửi trường cần thay đổi

Ví dụ người dùng chỉ muốn đổi priority:

~~~http
PATCH /api/tasks/42
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "priority": "HIGH"
}
~~~

Theo JSON Merge Patch (RFC 7396), thuộc tính không xuất hiện được giữ nguyên; thuộc tính xuất hiện với null được dùng để loại bỏ thuộc tính tương ứng khỏi biểu diễn mục tiêu. Với trường có thể lưu null, API cần định nghĩa cách biểu diễn xóa và có thể cần một định dạng patch khác nếu muốn phân biệt rõ hơn.

Ví dụ:

~~~json
{
  "description": null
}
~~~

Trong JSON Merge Patch, đây là yêu cầu xóa thuộc tính description khỏi biểu diễn đích. Nếu API dùng một JSON PATCH tùy biến thay vì Merge Patch, ý nghĩa null có thể khác. Không nên mặc định mọi endpoint PATCH đều tuân theo RFC 7396.

### 4.3. JSON Patch dùng thao tác tường minh

JSON Patch (RFC 6902) biểu diễn thay đổi dưới dạng danh sách thao tác. Ví dụ xóa trường description:

~~~json
[
  {
    "op": "remove",
    "path": "/description"
  }
]
~~~

Thay vì suy diễn ý nghĩa từ null, client chỉ rõ thao tác remove. Định dạng này hữu ích khi cần các thao tác add, remove, replace, move, copy hoặc test. Server vẫn phải kiểm tra đường dẫn, quyền thay đổi và tính hợp lệ của kết quả sau patch.

### 4.4. Chọn một ngữ nghĩa và công bố rõ

Không nên trộn các quy ước PATCH mà không nói rõ. Một hợp đồng nên công bố:

- Content-Type được hỗ trợ.
- Trường bị bỏ qua có nghĩa gì.
- Null có được phép không và có nghĩa là gì.
- Chuỗi rỗng được chấp nhận, chuẩn hóa hay từ chối.
- Mảng rỗng có nghĩa xóa toàn bộ phần tử hay là giá trị hợp lệ.
- Trường không được phép sửa sẽ bị bỏ qua hay trả lỗi.
- Cách xử lý khi phiên bản tài nguyên đã thay đổi.

## 5. Binding dữ liệu trong Java và Spring MVC

Khi Spring MVC nhận JSON, Jackson thường chuyển payload thành DTO. Cách khai báo kiểu Java ảnh hưởng đến khả năng phân biệt giá trị thiếu và null.

### 5.1. Kiểu nguyên thủy và kiểu wrapper

Xét DTO:

~~~java
public class UpdateSettingsRequest {
    private boolean notificationsEnabled;
    private Boolean weeklySummaryEnabled;

    public boolean isNotificationsEnabled() {
        return notificationsEnabled;
    }

    public Boolean getWeeklySummaryEnabled() {
        return weeklySummaryEnabled;
    }
}
~~~

Nếu notificationsEnabled bị bỏ qua hoặc null trong JSON, kiểu boolean nguyên thủy không thể giữ trạng thái null; giá trị mặc định của Java là false. Điều này có thể khiến Controller hiểu rằng client chủ động tắt thông báo.

Boolean wrapper có thể giữ null, nhưng chỉ như vậy vẫn chưa phân biệt được trường bị bỏ qua với trường có mặt và null. Nếu hợp đồng PATCH cần phân biệt cả hai, phải dùng kiểu biểu diễn có thêm thông tin về sự hiện diện của trường.

Quy tắc tương tự áp dụng cho số:

| Kiểu Java | Giá trị mặc định khi khởi tạo field | Rủi ro khi binding |
|---|---:|---|
| int | 0 | Trường thiếu có thể bị hiểu là số 0 |
| Integer | null | Có thể phân biệt null với số, nhưng chưa phân biệt absent với null |
| boolean | false | Trường thiếu có thể bị hiểu là false |
| Boolean | null | Có thể giữ null nhưng cần thêm presence để phân biệt absent |

Với trường bắt buộc, không nên dựa vào giá trị mặc định của kiểu nguyên thủy để xác định người dùng đã gửi trường. Hãy dùng wrapper hoặc DTO validation có chủ đích.

### 5.2. DTO riêng cho thao tác tạo và cập nhật

Một DTO tạo mới có thể khai báo rõ trường bắt buộc và mặc định:

~~~java
public record CreateTaskRequest(
    @NotBlank
    @Size(max = 120)
    String title,

    @Size(max = 2000)
    String description,

    Priority priority
) {}
~~~

Application service có thể áp dụng mặc định khi priority bị bỏ qua:

~~~java
public Task create(CreateTaskRequest request) {
    Priority priority = request.priority() == null
        ? Priority.NORMAL
        : request.priority();

    String description = request.description() == null
        ? null
        : request.description().trim();

    return repository.save(
        Task.create(request.title().trim(), description, priority)
    );
}
~~~

Đây là một lựa chọn thiết kế: null hoặc thiếu priority đều được xem là chưa chỉ định và dùng NORMAL. Nếu API cần phân biệt null với absent, DTO phải được mở rộng để giữ presence. Cũng cần quyết định description chuỗi rỗng có được giữ nguyên hay chuẩn hóa thành null.

### 5.3. Dùng wrapper để giữ null chưa đủ cho PATCH

Một DTO như sau vẫn có giới hạn:

~~~java
public record UpdateTaskRequest(
    String title,
    String description,
    Priority priority
) {}
~~~

Nếu JSON bỏ qua description và nếu JSON gửi description null đều được binding thành null, Controller không thể biết nên giữ mô tả cũ hay xóa nó.

Có thể dùng một kiểu wrapper biểu diễn sự hiện diện:

~~~java
public final class PatchField<T> {
    private final boolean present;
    private final T value;

    private PatchField(boolean present, T value) {
        this.present = present;
        this.value = value;
    }

    public static <T> PatchField<T> absent() {
        return new PatchField<>(false, null);
    }

    public static <T> PatchField<T> of(T value) {
        return new PatchField<>(true, value);
    }

    public boolean isPresent() {
        return present;
    }

    public T value() {
        return value;
    }
}
~~~

Trong đó:
- absent() biểu diễn trường không xuất hiện.
- of(null) biểu diễn trường có xuất hiện và mang null.
- of(value) biểu diễn trường có giá trị.

Cần viết deserializer hoặc binder phù hợp để khi trường vắng mặt, DTO nhận PatchField.absent(), còn khi trường xuất hiện, kể cả null, DTO nhận PatchField.of(value). Chỉ tạo lớp wrapper mà không cấu hình binding thì framework không tự biết phải phân biệt presence theo ý muốn.

Một cách khác là nhận payload dạng JsonNode hoặc Map đã được kiểm soát, rồi kiểm tra has("description") và giá trị node. Cách này linh hoạt nhưng cần validate kiểu dữ liệu và đường dẫn rõ ràng.

### 5.4. Không dùng Optional một cách máy móc cho DTO

Optional trong Java hữu ích để biểu diễn kết quả có thể không có ở API nội bộ. Tuy nhiên, dùng Optional làm field của mọi request DTO không tự giải quyết đầy đủ sự khác nhau giữa absent và explicit null. Hành vi deserialize còn phụ thuộc thư viện và cấu hình. Với PATCH, hãy chọn một kiểu presence-aware có hợp đồng rõ ràng thay vì kỳ vọng Optional tự giữ mọi thông tin.

## 6. Trường thiếu và rỗng trong HTML form

HTML form có một số quy tắc gửi dữ liệu riêng:

- Input text thường gửi tên trường với chuỗi rỗng nếu người dùng để trống.
- Checkbox không được chọn thường không xuất hiện trong dữ liệu form gửi đi.
- Radio group không có lựa chọn thường không gửi trường tương ứng.
- Select có thể gửi giá trị option đang chọn; một option value rỗng là chuỗi rỗng, không phải absent.
- Một trường disabled thường không được đưa vào form submission.
- Trường readonly vẫn được gửi, nhưng client có thể sửa request ngoài trình duyệt.

Ví dụ:

~~~html
<form method="post" action="/settings">
    <label for="display-name">Tên hiển thị</label>
    <input id="display-name" name="displayName" value="An">

    <label>
        <input type="checkbox" name="emailAlerts" value="true">
        Nhận thông báo email
    </label>

    <button type="submit">Lưu</button>
</form>
~~~

Nếu checkbox không được chọn, request thường không có tham số emailAlerts. Nếu Controller binding thẳng vào boolean, giá trị có thể trở thành false. Đây thường là hành vi mong muốn cho một form cập nhật toàn bộ cài đặt, nhưng không phù hợp nếu form chỉ cập nhật một vài trường và checkbox vắng mặt phải có nghĩa “không thay đổi”.

### 6.1. Phân biệt form tạo mới và form cập nhật từng phần

Với form tạo mới, trường không có dữ liệu thường được xử lý bằng validation hoặc mặc định. Với form cập nhật toàn bộ cài đặt, checkbox không xuất hiện có thể được hiểu là false vì trình duyệt không gửi checkbox chưa chọn.

Với form cập nhật từng phần, nếu trường không được hiển thị hoặc không thuộc phạm vi thao tác, không nên tự động ghi false. Có thể dùng một form object phản ánh đúng thao tác hoặc gửi một payload JSON có ngữ nghĩa PATCH rõ ràng.

### 6.2. Chuỗi rỗng và khoảng trắng

Input text có thể gửi:
- Chuỗi rỗng: chuỗi không có ký tự.
- Chuỗi chỉ có khoảng trắng.
- Chuỗi có nội dung và khoảng trắng đầu/cuối.

Ứng dụng cần quyết định có trim hay không, và việc trim xảy ra ở đâu. Với tên hiển thị, trim đầu/cuối thường hợp lý. Với mật khẩu hoặc nội dung văn bản có ý nghĩa định dạng, tự động trim có thể làm thay đổi dữ liệu người dùng.

Trong Spring MVC, có thể dùng validation như @NotBlank cho trường không chấp nhận chuỗi rỗng hoặc toàn khoảng trắng. @NotEmpty chỉ yêu cầu giá trị không null và độ dài/kích thước lớn hơn 0; một chuỗi toàn dấu cách vẫn có thể vượt qua @NotEmpty. Hãy chọn constraint theo đúng ngữ nghĩa.

## 7. Giá trị mặc định nên được áp dụng ở đâu?

Giá trị mặc định có thể được áp dụng ở nhiều tầng, nhưng mỗi loại mặc định nên có một nơi sở hữu rõ ràng.

| Loại mặc định | Ví dụ | Nơi thường phù hợp |
|---|---|---|
| Mặc định giao diện | Bộ lọc ban đầu là “Tất cả” | View hoặc client state |
| Mặc định request | page=0, size=20 nếu query parameter vắng mặt | Controller hoặc request binding |
| Mặc định nghiệp vụ | Công việc mới ở trạng thái DRAFT | Application service hoặc Model |
| Mặc định lưu trữ | created_at lấy thời điểm từ database | Database, nếu là quy tắc lưu trữ có chủ đích |
| Mặc định cấu hình | Timeout dịch vụ phụ thuộc | Configuration/application setup |

Không nên áp dụng một mặc định ở nhiều nơi mà không thống nhất. Nếu View hiển thị NORMAL nhưng server mặc định HIGH, người dùng sẽ thấy kết quả khác với lựa chọn của mình.

### 7.1. Mặc định ở Controller

Một tham số truy vấn có thể có giá trị mặc định:

~~~java
@GetMapping("/tasks")
String list(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size,
    org.springframework.ui.Model viewModel
) {
    int safeSize = Math.min(Math.max(size, 1), 100);
    viewModel.addAttribute("tasks", taskService.findPage(page, safeSize));
    return "tasks/list";
}
~~~

Trong Spring MVC, defaultValue được dùng khi request parameter bị thiếu hoặc giá trị rỗng theo quy tắc binding của annotation. Nếu cần phân biệt absent với empty, không nên dựa vào defaultValue; hãy nhận kiểu nullable hoặc kiểm tra request parameter một cách tường minh.

Controller phù hợp với mặc định thuộc giao thức hoặc trải nghiệm truy vấn, như trang đầu tiên và kích thước trang. Quy tắc nghiệp vụ như trạng thái ban đầu của công việc nên được bảo vệ ở phía ứng dụng.

### 7.2. Mặc định trong Model hoặc application service

Giá trị mặc định nghiệp vụ nên được áp dụng ở nơi tạo đối tượng hoặc thực hiện use case, để mọi nguồn gọi đều nhận cùng một hành vi:

~~~java
public static Task create(String title, Priority requestedPriority) {
    Priority priority = requestedPriority == null
        ? Priority.NORMAL
        : requestedPriority;

    return new Task(title, priority, TaskStatus.DRAFT);
}
~~~

Nếu công việc được tạo từ web, API hoặc tác vụ nền, quy tắc mặc định vẫn giống nhau. Controller không cần tự nhớ trạng thái mặc định.

### 7.3. Mặc định ở database

Database có thể khai báo DEFAULT cho cột. Default thường được áp dụng khi câu lệnh INSERT bỏ qua cột hoặc dùng từ khóa DEFAULT. Nếu ứng dụng gửi NULL tường minh, cột có thể nhận NULL thay vì giá trị default, trừ khi schema hoặc trigger có quy tắc khác.

Vì vậy, cần phân biệt:
- Không đưa cột vào INSERT.
- Đưa cột vào INSERT với NULL.
- Đưa cột vào INSERT với một giá trị cụ thể.

Không nên chỉ dựa vào default của database nếu ứng dụng cần hiển thị giá trị đã được áp dụng trước khi đọc lại bản ghi. Cần xác định nguồn có thẩm quyền và đồng bộ mapping giữa entity, database và response.

## 8. Validation cho trường thiếu và giá trị rỗng

Validation cần xác định cả sự hiện diện lẫn giá trị. Các câu hỏi quan trọng:

- Trường có bắt buộc phải xuất hiện không?
- Nếu xuất hiện, có được phép null không?
- Nếu là chuỗi, có chấp nhận chuỗi rỗng hoặc toàn khoảng trắng không?
- Nếu là số, số 0 có hợp lệ không?
- Nếu là danh sách, danh sách rỗng có ý nghĩa gì?
- Nếu trường bị bỏ qua, có mặc định hoặc giữ nguyên giá trị cũ không?

Ví dụ:

~~~java
public record CreateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    String email,

    @Size(max = 500)
    String bio
) {}
~~~

Ở ví dụ này, displayName bắt buộc có nội dung không chỉ gồm khoảng trắng. email có thể null nếu hợp đồng cho phép không cung cấp; nếu có giá trị thì phải đúng định dạng. bio có thể vắng mặt hoặc rỗng theo chính sách của API. Các constraint cần được chọn theo schema và cấu hình deserialization thực tế.

Không nên cho rằng annotation validation tự phân biệt trường bị bỏ qua với trường null. Ví dụ @NotNull có thể từ chối null sau binding, nhưng không cho biết null xuất phát từ trường thiếu hay trường gửi explicit null. Nếu hợp đồng cần phân biệt hai trường hợp, phải kiểm tra presence trước hoặc dùng kiểu dữ liệu giữ được presence.

### 8.1. Validation theo ngữ cảnh tạo và cập nhật

Cùng một trường có thể có quy tắc khác nhau:
- Khi tạo mới, title bắt buộc.
- Khi cập nhật title, nếu trường xuất hiện thì không được rỗng.
- Khi PATCH không gửi title, giữ nguyên.
- Khi PATCH gửi title null, từ chối vì title không thể null.
- Khi PATCH gửi title chuỗi rỗng, từ chối vì title phải có nội dung.

Đây là lý do nên có CreateRequest, ReplaceRequest và PatchRequest riêng khi ngữ nghĩa khác nhau. Dùng một DTO chung rồi thêm nhiều điều kiện theo endpoint thường khó hiểu và dễ bỏ sót.

## 9. Tương thích khi thêm trường mới

Hợp đồng dữ liệu có thể thay đổi theo thời gian. Khi thêm một trường mới vào response, client cũ có thể bỏ qua trường chưa biết. Đây thường là thay đổi tương thích nếu client tuân thủ nguyên tắc bỏ qua thuộc tính không nhận diện.

Khi thêm trường mới vào request:
- Nếu trường tùy chọn và server có mặc định an toàn, client cũ có thể tiếp tục gửi payload cũ.
- Nếu trường mới bắt buộc ngay lập tức, client cũ có thể bị lỗi.
- Nếu server hiểu trường thiếu là null và ghi đè dữ liệu, client cũ có thể vô tình xóa giá trị.
- Nếu default thay đổi theo thời gian, cùng một payload cũ có thể tạo kết quả khác trước.

Khi thay đổi ý nghĩa của null hoặc chuỗi rỗng, đó có thể là thay đổi phá vỡ tương thích dù schema không đổi. Hãy xem ngữ nghĩa dữ liệu là một phần của API contract, không chỉ là tên và kiểu trường.

Một số nguyên tắc:
1. Thêm trường response theo hướng client có thể bỏ qua.
2. Thêm trường request với quy tắc optional/default rõ ràng nếu cần tương thích.
3. Không đổi ngầm ý nghĩa absent/null/empty giữa các phiên bản.
4. Version hóa API hoặc cung cấp giai đoạn chuyển đổi khi thay đổi không tương thích.
5. Kiểm thử payload cũ và payload mới.
6. Ghi rõ default được áp dụng ở server và giá trị thực tế trả về.

## 10. Bảo mật và quyền sở hữu dữ liệu

Trường thiếu, null hoặc mặc định không nên được dùng để bỏ qua kiểm tra bảo mật.

Ví dụ:
- ownerId bị bỏ qua không có nghĩa người dùng được tự do chọn chủ sở hữu.
- role null không có nghĩa bỏ kiểm tra phân quyền.
- status rỗng không có nghĩa server được phép chuyển đối tượng sang trạng thái bất kỳ.
- price bị bỏ qua không có nghĩa lấy giá do client cung cấp từ hidden input.
- trường password rỗng trong form cập nhật hồ sơ thường có nghĩa không đổi mật khẩu, nhưng phải được định nghĩa rõ và xử lý qua luồng bảo mật riêng.

Với các trường nhạy cảm, nên tách request DTO theo quyền được phép sửa. Không binding hàng loạt payload vào entity. Controller và dịch vụ ứng dụng phải xác minh danh tính và quyền trên tài nguyên; Model bảo vệ bất biến nghiệp vụ.

Khi trả dữ liệu, ViewModel hoặc Response DTO chỉ nên chứa trường cần thiết. Không đưa giá trị nội bộ hoặc thông tin nhạy cảm ra response chỉ vì trường đó tồn tại trong entity.

## 11. Ví dụ: cập nhật hồ sơ người dùng

Giả sử hồ sơ có các trường displayName, bio và avatarUrl. Người dùng có thể muốn:
- Không đổi avatar: bỏ qua avatarUrl.
- Xóa avatar: gửi null theo hợp đồng PATCH.
- Đổi avatar: gửi URL mới.
- Để bio trống: gửi chuỗi rỗng nếu hợp đồng coi đó là nội dung rỗng hợp lệ.

Một hợp đồng PATCH có thể quy định:

| Payload | Ý nghĩa |
|---|---|
| `{}` | Không thay đổi trường nào |
| `{"avatarUrl": null}` | Xóa avatar |
| `{"avatarUrl": "https://cdn.example/avatar.png"}` | Thay avatar |
| `{"bio": ""}` | Xóa nội dung bio hoặc lưu chuỗi rỗng theo quy ước |
| `{"displayName": null}` | Từ chối vì tên hiển thị không thể null |

Controller không nên tự cập nhật từng field theo cách mơ hồ. Nó cần chuyển payload thành một command giữ được presence:

~~~java
public record UpdateProfileCommand(
    PatchField<String> displayName,
    PatchField<String> bio,
    PatchField<String> avatarUrl
) {}
~~~

Application service đọc giá trị hiện tại và áp dụng từng trường theo hợp đồng:

~~~java
public void updateProfile(UUID userId, UpdateProfileCommand command) {
    Profile profile = profileRepository.findByUserId(userId)
        .orElseThrow(ProfileNotFoundException::new);

    if (command.displayName().isPresent()) {
        String value = command.displayName().value();

        if (value == null || value.isBlank()) {
            throw new InvalidProfileException(
                "Tên hiển thị không được để trống"
            );
        }

        profile.changeDisplayName(value.trim());
    }

    if (command.bio().isPresent()) {
        String value = command.bio().value();
        profile.changeBio(value == null ? null : value);
    }

    if (command.avatarUrl().isPresent()) {
        String value = command.avatarUrl().value();
        profile.changeAvatarUrl(value);
    }

    profileRepository.save(profile);
}
~~~

Ví dụ giả định PatchField đã được binding đúng như mô tả ở phần trước. Nếu trường avatarUrl có mặt với null, Model có thể xóa avatar; nếu trường không có mặt, Model giữ nguyên avatar. Với bio, ứng dụng chọn lưu chuỗi rỗng như giá trị hợp lệ, còn displayName từ chối null và blank.

Trong thực tế, URL avatar cần được kiểm tra scheme, host hoặc tham chiếu file theo chính sách ứng dụng. Không nên cho phép người dùng cập nhật ownerId, email đã xác minh hoặc quyền truy cập qua cùng command nếu những trường đó có quy trình riêng.

## 12. Kiểm thử hợp đồng trường

Một ma trận kiểm thử giúp tránh bỏ sót khác biệt giữa absent, null, empty và default:

| Trường hợp | Đầu vào | Kết quả cần xác minh |
|---|---|---|
| Thiếu trường bắt buộc | Không có title | Validation thất bại |
| Null trường bắt buộc | title = null | Validation thất bại |
| Chuỗi rỗng | title = chuỗi không có ký tự | Validation thất bại nếu yêu cầu nội dung |
| Chuỗi khoảng trắng | title chỉ có khoảng trắng | Validation thất bại hoặc chuẩn hóa theo hợp đồng |
| Giá trị hợp lệ | title có nội dung | Tạo/cập nhật thành công |
| Thiếu trường tùy chọn | Không có bio | Áp dụng quy tắc mặc định hoặc giữ nguyên |
| Null trường tùy chọn | bio = null | Xóa hoặc lưu null theo hợp đồng |
| Mảng rỗng | tags = [] | Xóa toàn bộ tags hoặc lưu danh sách rỗng theo hợp đồng |
| Trường không được phép sửa | ownerId có mặt | Từ chối hoặc bỏ qua theo chính sách rõ ràng |
| Trường mới bị client cũ bỏ qua | Payload phiên bản cũ | Hành vi tương thích như đã công bố |

Nên kiểm thử ở nhiều tầng:

- **Controller test:** JSON/form binding, trường thiếu, null, chuỗi rỗng và mã lỗi.
- **DTO validation test:** các constraint đúng với kiểu và ngữ nghĩa trường.
- **Application service test:** mặc định và quy tắc cập nhật absent/null.
- **Domain test:** bất biến, ví dụ title không thể rỗng.
- **Persistence integration test:** phân biệt INSERT bỏ qua cột với INSERT gửi NULL; kiểm tra database default.
- **API compatibility test:** payload cũ và payload mới có hành vi đã công bố.

Với PATCH, cần kiểm thử riêng cả trường bị bỏ qua và trường explicit null. Một test chỉ gửi giá trị hợp lệ sẽ không phát hiện lỗi binding khiến hai trạng thái này bị gộp làm một.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng null cho cả absent và explicit null | Không biết giữ nguyên hay xóa dữ liệu | Dùng kiểu presence-aware hoặc định dạng patch rõ |
| Dùng kiểu nguyên thủy cho trường PATCH | Trường thiếu bị biến thành false hoặc 0 | Dùng wrapper và presence khi cần |
| Coi chuỗi rỗng giống chuỗi null ở mọi nơi | Mất ý nghĩa dữ liệu hoặc validation không nhất quán | Quy định riêng cho empty và null |
| Để nhiều tầng tự áp dụng default | View hiển thị một giá trị nhưng server lưu giá trị khác | Chỉ định nơi có thẩm quyền áp dụng default |
| Dùng chung DTO cho POST, PUT và PATCH | Ngữ nghĩa trường bị trộn lẫn | Thiết kế DTO theo use case và phương thức |
| Binding request thẳng vào entity | Client có thể thay đổi trường không được phép | Dùng Request DTO và command |
| Dựa vào database default nhưng gửi NULL tường minh | Default không được áp dụng như mong muốn | Xác định rõ cột được bỏ qua hay nhận NULL |
| Chỉ kiểm thử giá trị hợp lệ | Bỏ sót trường hợp thiếu, null và rỗng | Dùng ma trận kiểm thử hợp đồng |

## 14. Quy trình thiết kế hợp đồng cho từng trường

Khi thêm một trường vào request hoặc response, hãy xác định:

1. Trường có bắt buộc xuất hiện không?
2. Nếu xuất hiện, có cho phép null không?
3. Chuỗi rỗng, khoảng trắng hoặc mảng rỗng có ý nghĩa gì?
4. Nếu trường bị bỏ qua, ứng dụng giữ nguyên, áp dụng default hay trả lỗi?
5. Quy tắc có khác nhau giữa create, replace và partial update không?
6. Giá trị mặc định thuộc giao diện, Controller, application service, Model hay database?
7. Client có được phép thay đổi trường này không?
8. Response cần trả giá trị đã chuẩn hóa hoặc mặc định thực tế nào?
9. Thay đổi này có tương thích với client phiên bản cũ không?
10. Có test riêng cho absent, null, empty, blank và default chưa?

Một hợp đồng tốt không cần làm mọi trường đều phức tạp. Với trường bắt buộc đơn giản, có thể quy định “phải có, không null, không rỗng” và dùng validation tiêu chuẩn. Chỉ khi nghiệp vụ cần phân biệt nhiều ý định cập nhật mới cần kiểu dữ liệu presence-aware hoặc định dạng patch chi tiết.

## 15. Những điểm cần ghi nhớ

Trường thiếu, null, rỗng và giá trị mặc định là các trạng thái khác nhau. Trường thiếu thường biểu thị client không đưa ra chỉ định; null biểu thị không có giá trị; chuỗi rỗng hoặc mảng rỗng là giá trị cụ thể; default là quy tắc mà hợp đồng hoặc ứng dụng áp dụng.

Trong MVC, Controller phải binding dữ liệu mà không làm mất ngữ nghĩa cần thiết. Application service và Model áp dụng quy tắc cập nhật, mặc định nghiệp vụ và bất biến. View hiển thị giá trị thực tế sau khi server xử lý. Với PUT và PATCH, cần công bố rõ ý nghĩa của trường bị bỏ qua và null; không giả định mọi endpoint PATCH dùng cùng một định dạng.

Hãy thiết kế DTO theo mục đích tạo mới, thay thế hoặc cập nhật từng phần; chọn kiểu Java giữ được trạng thái cần phân biệt; áp dụng default ở một nơi có thẩm quyền; và kiểm thử ma trận absent/null/empty/blank/default. Khi hợp đồng dữ liệu rõ ràng, các tầng MVC có thể phối hợp mà không vô tình xóa, ghi đè hoặc tự tạo giá trị sai.
