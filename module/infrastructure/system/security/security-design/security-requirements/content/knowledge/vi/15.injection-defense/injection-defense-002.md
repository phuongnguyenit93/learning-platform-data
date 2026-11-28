# NoSQL injection

## 1. Không dùng SQL không có nghĩa là không có injection

NoSQL injection xuất hiện khi dữ liệu không đáng tin được đưa vào vị trí có thể điều khiển cấu trúc hoặc hành vi của một thao tác truy vấn. Đầu vào đáng lẽ chỉ là giá trị tìm kiếm lại trở thành toán tử, biểu thức, tên trường, đoạn chương trình hoặc một phần cấu trúc thực thi.

Trong thiết kế yêu cầu bảo mật, câu hỏi quan trọng là: **ai được quyền quyết định ý nghĩa của thao tác gửi đến database?** Client có thể được chọn giá trị và một số chức năng tìm kiếm đã công bố; việc đó không mặc nhiên cho phép client gửi ngôn ngữ truy vấn gốc của database.

Bài học sử dụng MongoDB làm ví dụ cụ thể vì cấu trúc filter giúp quan sát rõ ranh giới giữa dữ liệu và chỉ dẫn. Không suy rằng mọi hệ NoSQL có cùng toán tử, driver hoặc cơ chế khai thác. Với một hệ thống khác, cần xác định cú pháp, API và những vị trí mà dữ liệu có thể được diễn giải như chỉ dẫn của chính hệ thống đó.

Một yêu cầu có thể kiểm chứng là:

> Mọi điểm tiếp nhận dữ liệu không đáng tin phải ánh xạ đầu vào sang tập thao tác truy vấn do server định nghĩa. Client không được cung cấp trực tiếp filter, update document, pipeline hoặc biểu thức thực thi. Tên trường, toán tử và phạm vi truy cập phải được server kiểm soát; giá trị phải được kiểm tra theo schema trước khi đưa vào query builder.

Yêu cầu này cần được chứng minh trên cả API, tác vụ bất đồng bộ, bộ lọc đã lưu và công cụ quản trị có cùng quyền truy cập dữ liệu, không chỉ trên một form tìm kiếm.

## 2. Phân biệt giá trị, toán tử và phạm vi quyền

Giả sử một API tìm đơn hàng nhận mã khách hàng và trạng thái:

```json
{
  "customerRef": "cust-example-042",
  "status": "PAID"
}
```

Hợp đồng mong muốn là so sánh hai giá trị đã kiểm tra với các field cố định. Nếu API nhận một object ở chỗ đáng lẽ là string và chuyển nguyên nó thành điều kiện truy vấn, ý nghĩa có thể thay đổi.

Ví dụ kiểm thử tổng hợp sau thay string bằng object:

```json
{
  "customerRef": {"$ne": null},
  "status": "PAID"
}
```

Trong một filter MongoDB không an toàn, cấu trúc `{"customerRef": {"$ne": null}}` là điều kiện truy vấn khác với tìm một mã khách hàng cụ thể. Tài liệu MongoDB mô tả chính rủi ro object thay thế scalar khi chuyển JSON không được kiểm tra sang BSON. Xem [MongoDB — Validate Untrusted Input Before Converting JSON to BSON](https://www.mongodb.com/docs/drivers/client-libraries-best-practices/#validate-untrusted-input-before-converting-json-to-bson).

Điểm dễ nhầm là một chuỗi chứa các ký tự `$`, `{` hoặc `}` không tự trở thành toán tử. Rủi ro phụ thuộc nơi và cách giá trị được đưa vào thao tác. Một string được giữ đúng là string trong điều kiện equality khác với một object được dùng như query document hoặc một string bị parse lại thành filter.

| Thành phần | Ai nên quyết định trong API minh họa? | Ví dụ |
|---|---|---|
| Giá trị tìm kiếm | Client đề nghị, server kiểm tra | Mã khách hàng cần tìm |
| Field database | Server | `customerRef`, `status` |
| Toán tử | Server | Equality cho mã khách hàng |
| Tenant và phạm vi dữ liệu | Server từ ngữ cảnh quyền đã xác minh | Tenant mà chủ thể được phép đọc |
| Sort, projection và giới hạn | Server định nghĩa tập lựa chọn | Sắp theo thời gian, tối đa số kết quả đã quy định |
| Pipeline hoặc mã thực thi | Không thuộc quyền gửi trực tiếp của client thông thường | Không nhận một pipeline MongoDB tùy ý |

Kiểm tra input không thay thế phân quyền. Một filter được dựng an toàn về injection vẫn có thể đọc dữ liệu ngoài quyền nếu thiếu điều kiện tenant hoặc kiểm tra quyền tài nguyên.

## 3. Những đường đi thường làm mất ranh giới

### 3.1. Dùng nguyên request làm query

Mẫu Java sau minh họa một cách thiết kế cần tránh nếu body thuộc quyền điều khiển của người gọi:

```java
// Không dùng mẫu này cho body không đáng tin.
Document filter = Document.parse(requestBody);
collection.find(filter);
```

Vấn đề không nằm ở việc parser đọc JSON thành công hay thất bại. Vấn đề là toàn bộ cấu trúc mà người gọi gửi được trao quyền điều khiển filter. Việc parse thành một đối tượng BSON không đồng nghĩa đối tượng đó đáp ứng schema của endpoint.

Một biến thể khác là server tự tạo filter ngoài cùng nhưng chép các object con từ request vào các vị trí điều kiện. Khi đó, nhìn bề ngoài server vẫn đang “dùng query object”, nhưng client có thể kiểm soát cấu trúc bên trong.

### 3.2. Ghép chuỗi rồi parse hoặc đánh giá lại

Nếu server ghép dữ liệu vào chuỗi JSON của filter, dấu phân cách và cú pháp có thể làm thay đổi cấu trúc sau bước parse. Nếu server còn đánh giá chuỗi thành mã, bề mặt rủi ro có thể mở rộng hơn truy vấn thông thường.

Biện pháp là dựng thao tác bằng API có cấu trúc với các vị trí giá trị đã xác định. Tuy nhiên, vẫn phải kiểm tra kiểu giá trị và những tham số mang ý nghĩa cấu trúc. Không chuyển vấn đề từ nối chuỗi sang một hàm builder nhận mọi object tùy ý.

OWASP nhấn mạnh rằng query object không tự ngăn operator injection khi giá trị không đáng tin vẫn là object. Khuyến nghị này đi cùng việc kiểm tra scalar và không chấp nhận raw query JSON từ client. Xem [OWASP — NoSQL Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Security_Cheat_Sheet.html#prevent-nosql-injection).

### 3.3. Cho client chọn tên field, sort hoặc update path

Một API nhận `field`, `operator`, `value` rồi dùng trực tiếp cả ba làm cấu trúc database đã mở quyền lớn hơn một form tìm kiếm đơn giản. Việc `value` là string không bảo vệ được `field` hoặc `operator`.

Tương tự, API cập nhật profile không nên nhận nguyên update document. Server cần chọn những thuộc tính được sửa và tạo thao tác tương ứng, thay vì để request quyết định field quản trị, đường dẫn lồng hoặc kiểu cập nhật.

Projection cũng là một quyết định về dữ liệu đầu ra. Cho client yêu cầu mọi field có thể làm lộ thuộc tính nhạy cảm dù điều kiện tìm kiếm hoàn toàn đúng.

### 3.4. Parse lại dữ liệu đã lưu

Một bộ lọc được lưu trong database không tự trở thành dữ liệu đáng tin. Nếu người dùng từng kiểm soát nội dung đó, một tác vụ xuất báo cáo đọc lại và diễn giải nó thành query vẫn có thể tạo injection ở thời điểm sau.

Thiết kế cần giữ provenance: ai được tạo, ai được sửa, phiên bản schema nào đã được kiểm tra và bước sử dụng nào có quyền diễn giải. Việc dữ liệu đã đi qua lưu trữ không phải bằng chứng rằng có thể chạy nó như một thao tác database.

## 4. Biến mục tiêu phòng vệ thành hợp đồng đầu vào

Một endpoint tìm đơn hàng có thể định nghĩa hợp đồng như sau:

| Field API | Kiểu và điều kiện | Ánh xạ do server sở hữu |
|---|---|---|
| `customerRef` | String bắt buộc, không trắng, chiều dài có giới hạn | Equality trên field `customerRef` |
| `status` | Một giá trị enum đã công bố | Equality trên field `status` |
| `sort` | `CREATED_ASC` hoặc `CREATED_DESC` | Tập field sort cố định |
| `limit` | Số nguyên trong khoảng đã định nghĩa | Giới hạn số kết quả |
| Field khác | Bị từ chối theo chính sách endpoint | Không được chép thêm vào filter |

Tenant không nằm trong tập field mà client được tự quyết định. Nếu API có chức năng chọn tenant cho người dùng đa tenant, giá trị đề nghị phải được kiểm tra với quyền trước khi tạo scope; không dùng trực tiếp từ body như một sự thật đã được xác thực.

Hợp đồng cũng cần quy định:

- Có chấp nhận `null`, array hoặc object thay scalar không.
- Field thiếu có làm query rộng hơn không, và điều đó có đúng nghiệp vụ không.
- Có cho phép chuyển đổi object hoặc number thành string không.
- Field trùng tên được xử lý tại parser như thế nào.
- Có lớp nào tự giải mã hoặc parse lại giá trị sau khi đã kiểm tra không.
- Các dạng nhập HTTP JSON, query parameter, message và file có cùng ý nghĩa không.

Không để parser âm thầm tạo object từ một query parameter lồng nếu endpoint chỉ nhận string. Cần kiểm tra đầu vào sau bước parse thực tế, vì cùng biểu diễn trên đường truyền có thể trở thành những kiểu khác nhau tùy cấu hình framework.

### Từ chối cấu trúc không có trong hợp đồng

Với hợp đồng ở bảng trên, `customerRef` là object phải bị từ chối trước khi gọi database. Không “làm sạch” bằng cách bỏ key bắt đầu bằng `$` rồi tiếp tục với một object rỗng. Thao tác đó có thể đổi ý nghĩa hoặc làm mất một điều kiện lọc bắt buộc.

Một chuỗi bình thường có ký tự giống toán tử cần được xử lý theo schema của field và ngữ nghĩa tìm kiếm đã công bố. Không nên áp dụng một denylist ký tự chung cho mọi dữ liệu rồi xem đó là biện pháp chính. Denylist vừa có thể bỏ sót cấu trúc nguy hiểm, vừa có thể từ chối dữ liệu hợp lệ.

## 5. Giữ phạm vi truy cập độc lập với điều kiện người dùng

Giả sử `S` là scope do server xác lập và `U` là điều kiện tìm kiếm hợp lệ mà người dùng được chọn. Kết quả phải thỏa:

```text
S AND U
```

Nếu endpoint hỗ trợ nhiều điều kiện thay thế, cần giữ grouping:

```text
Đúng với mục tiêu scope: S AND (U1 OR U2)
Không tương đương:      (S AND U1) OR U2
```

Ở biểu thức thứ hai, một bản ghi thỏa `U2` có thể không cần thỏa `S`. Đây là lỗi thiết kế quyền ngay cả khi mọi toán tử đều được server tạo bằng builder.

Không trộn hai map bằng cách cho dữ liệu client ghi đè `tenantId` hoặc các điều kiện bảo vệ. Cũng không có đường fallback “filter không hợp lệ thì tìm tất cả”. Lỗi dựng filter phải dẫn tới từ chối có kiểm soát, không phải mở rộng phạm vi.

Scope phải tồn tại cho cả truy vấn đếm, xuất file, xem chi tiết, cập nhật và xóa, nếu chúng cùng chịu ràng buộc quyền. Chỉ bảo vệ endpoint trả danh sách nhưng bỏ điều kiện ở endpoint đếm vẫn có thể làm lộ thông tin ngoài phạm vi.

Trong hệ thống thật, tenant có thể chưa đủ để xác định toàn bộ quyền. Có thể cần thêm quyền theo chủ sở hữu, nhóm, phân loại dữ liệu hoặc thao tác cụ thể. Scope trong ví dụ chỉ là một phần mô hình quyền, không phải kết luận rằng thêm `tenantId` là giải quyết mọi access control.

## 6. Query builder hữu ích nhưng không phải bộ quyết định chính sách

MongoDB Java driver cung cấp `Filters` để dựng các điều kiện như `eq` và `and`, trả về đối tượng `Bson`. Điều này giúp code xác định rõ field và thao tác thay vì ghép chuỗi query. Xem [MongoDB Java Driver — Filters Builders](https://www.mongodb.com/docs/drivers/java/sync/current/builders/filters/).

Tài liệu driver cũng nêu builder không tự sanitize dữ liệu truyền vào. Vì vậy, ứng dụng vẫn phải xác định kiểu, field và chức năng được phép trước khi gọi builder. Xem [MongoDB Java Driver — Builders, Input Validation](https://www.mongodb.com/docs/drivers/java/sync/current/builders/#overview).

Không nên chuyển nguyên một `Document` nhận từ request vào vị trí vốn phải là string chỉ vì một overload hoặc generic type của thư viện cho phép biên dịch. Kiểu Java đủ rộng không đồng nghĩa ý nghĩa nghiệp vụ được phép đủ rộng.

Tài liệu MongoDB phân biệt equality tường minh với một số dạng match ngầm định và khuyến nghị dạng `$eq` tường minh cho input do người dùng cung cấp. Đây là lý do cần hiểu ngữ nghĩa filter cụ thể, không chỉ nhìn xem nó có phải JSON hợp lệ không. Xem [MongoDB Manual — `$eq`, Security Implications](https://www.mongodb.com/docs/manual/reference/operator/query/eq/#security-implications).

Trong thiết kế minh họa, server chỉ đưa các giá trị string đã kiểm tra vào các phép equality cố định. Không nhận regex object, query document hoặc tên toán tử ở những vị trí đó.

## 7. Ví dụ Java: tạo query từ một command hẹp

Ví dụ sử dụng Java 17 và API của MongoDB Java Sync Driver. Nó minh họa bước dựng query, không cấu hình kết nối hoặc thực hiện một hệ thống phân quyền hoàn chỉnh.

Lớp tiếp nhận phía trước phải kiểm tra JSON theo schema: không ép object thành string, không nhận field không biết và không biến một query document thành `SearchInput`. `AccessScope` phải do luồng xác thực và phân quyền phía server tạo; không bind record này từ request body.

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.conversions.Bson;

public final class OrderSearchQueries {

    private OrderSearchQueries() {
    }

    public enum OrderStatus {
        OPEN,
        PAID,
        CANCELLED
    }

    public enum SortMode {
        CREATED_ASC,
        CREATED_DESC
    }

    public record AccessScope(String tenantId) {
    }

    public record SearchInput(
        String customerRef,
        OrderStatus status,
        SortMode sort,
        int limit
    ) {
    }

    public record QueryPlan(Bson filter, Bson sort, int limit) {
    }

    public static QueryPlan build(AccessScope scope, SearchInput input) {
        if (scope == null
                || scope.tenantId() == null
                || scope.tenantId().isBlank()) {
            throw new IllegalStateException("ACCESS_SCOPE_REQUIRED");
        }

        if (input == null
                || input.customerRef() == null
                || input.customerRef().isBlank()
                || input.customerRef().length() > 64
                || input.status() == null
                || input.sort() == null
                || input.limit() < 1
                || input.limit() > 100) {
            throw new IllegalArgumentException("INVALID_SEARCH_INPUT");
        }

        Bson filter = Filters.and(
            Filters.eq("tenantId", scope.tenantId()),
            Filters.eq("customerRef", input.customerRef()),
            Filters.eq("status", input.status().name())
        );

        Bson sort = switch (input.sort()) {
            case CREATED_ASC -> Sorts.ascending("createdAt", "orderId");
            case CREATED_DESC -> Sorts.descending("createdAt", "orderId");
        };

        return new QueryPlan(filter, sort, input.limit());
    }
}
```

Giới hạn 64 đơn vị UTF-16 cho mã khách hàng và tối đa 100 kết quả là lựa chọn minh họa của endpoint. Hệ thống thật cần chọn giới hạn theo nghiệp vụ và ngân sách tài nguyên; các con số này không phải chuẩn chung.

Repository có thể áp dụng kết quả bằng các vị trí đã biết của driver:

```java
// plan được tạo bằng OrderSearchQueries.build sau các cổng kiểm soát.
collection.find(plan.filter())
    .sort(plan.sort())
    .limit(plan.limit());
```

Đoạn gọi này chưa thể hiện projection, timeout, phân trang hoặc ánh xạ response. Những yêu cầu đó cần được bổ sung ở repository và API thực tế. Không trả nguyên mọi field của document chỉ vì filter đã được dựng an toàn.

Điểm bảo vệ trong thiết kế là:

- Field và toán tử được chọn trong code, không đến từ string tùy ý của request.
- Giá trị tìm kiếm có kiểu hẹp trước khi được đưa vào builder.
- Tenant là một điều kiện bắt buộc lấy từ scope đã kiểm tra.
- Sort chỉ chọn giữa hai cấu trúc có sẵn.
- Không có bước nối JSON hoặc parse lại `customerRef` thành query.
- Thiếu scope hoặc input không hợp lệ dẫn đến lỗi; không thay bằng filter rỗng.

Một record có tên `AccessScope` không tự làm dữ liệu bên trong đáng tin. Nếu lớp HTTP bind `tenantId` từ body vào record rồi truyền đến đây, yêu cầu về nguồn scope đã bị vi phạm dù code dựng filter không đổi.

Tương tự, kiểm tra trong `build` không thay thế schema ở điểm tiếp nhận. Nó không thể biết client ban đầu gửi object nhưng binder đã biến object đó thành string. Kiểm thử tích hợp cần xác minh cả đường chuyển từ thông điệp sang command.

## 8. Nếu nghiệp vụ cần bộ lọc nâng cao

Không nên biến yêu cầu “người dùng chọn điều kiện tìm kiếm” thành “người dùng gửi toàn bộ query MongoDB”. Có thể thiết kế một ngôn ngữ nghiệp vụ hẹp, chẳng hạn:

```json
{
  "conditions": [
    {
      "field": "createdAt",
      "operation": "AFTER",
      "value": "2026-01-01T00:00:00Z"
    }
  ]
}
```

Đây vẫn là input không đáng tin. Server cần xác định:

- Những field nào được tìm, sort hoặc xuất theo quyền của chủ thể.
- Phép toán nào hợp lệ cho từng field và kiểu giá trị của nó.
- Số điều kiện, độ sâu nhóm, số phần tử mỗi danh sách và chiều dài giá trị.
- Quan hệ AND/OR được phép và cách giữ scope bắt buộc bên ngoài điều kiện người dùng.
- Cách chuyển một node đã hợp lệ sang cấu trúc do server tạo.
- Chính sách khi không có điều kiện, điều kiện mâu thuẫn hoặc điều kiện không được hỗ trợ.

Không ánh xạ `operation` bằng cách gắn thêm ký tự `$` rồi chuyển trực tiếp thành toán tử database. Nên dùng một bảng hoặc nhánh ánh xạ hữu hạn do server sở hữu, với những kiểu dữ liệu được kiểm tra riêng.

Nếu bộ lọc được lưu, lưu phiên bản schema và thông tin owner theo mô hình quyền. Khi đọc lại, cần kiểm tra quyền hiện hành và tính tương thích trước khi thực thi. Một user từng có quyền đọc field không nhất thiết vẫn có quyền đó vào lúc chạy báo cáo sau này.

Quyền tìm kiếm nâng cao cũng là một năng lực có thể gây chi phí hoặc suy ra thông tin. Cho phép người dùng tìm theo một field không tự đồng nghĩa họ được nhận giá trị field đó trong projection, và ngược lại.

## 9. Regex, script và giới hạn tài nguyên

### 9.1. Đừng biến tìm kiếm text thành ngôn ngữ regex ngoài ý muốn

Nếu hợp đồng là tìm một chuỗi literal hoặc một tiền tố, không truyền thẳng chuỗi đó thành regex chỉ để tiện triển khai. Khi đó người dùng có thể điều khiển ngữ nghĩa tìm kiếm khác với chức năng đã công bố.

Nếu tính năng thật sự cần regex hoặc một ngôn ngữ tìm kiếm, cần đặc tả nó như một năng lực riêng: ai được dùng, cú pháp nào được nhận, giới hạn chi phí, thời gian thực thi, số kết quả và hành vi hủy. Giới hạn chiều dài đầu vào không tự chứng minh mọi biểu thức đều có chi phí chấp nhận được.

Một query chỉ trả ít kết quả vẫn có thể tốn tài nguyên để tìm ra chúng. Vì vậy, `limit` là giới hạn đầu ra, không phải bằng chứng duy nhất cho chi phí truy vấn. Cần xem xét index, kế hoạch thực thi và ngân sách theo những mẫu query được phép.

### 9.2. Không tiếp nhận mã thực thi từ người dùng

Không đưa input người dùng vào thân hàm hoặc biểu thức JavaScript phía database. MongoDB khuyến nghị dùng các toán tử thông thường thay cho xây dựng mã từ input, và tắt server-side scripting khi ứng dụng không cần khả năng đó. Khả năng cấu hình phải được đối chiếu với cách triển khai thực tế. Xem [MongoDB — Restrict Server-Side JavaScript Execution](https://www.mongodb.com/docs/drivers/client-libraries-best-practices/#restrict-server-side-javascript-execution).

Tắt scripting không loại bỏ operator injection hoặc lỗi scope. Một truy vấn equality hoặc một toán tử so sánh đã đủ gây lộ dữ liệu nếu server để client thay đổi điều kiện ngoài quyền.

### 9.3. Giới hạn phải bao phủ toàn luồng

Yêu cầu có thể cần giới hạn kích thước body, độ sâu JSON, số điều kiện, số phần tử danh sách, số bản ghi mỗi trang, thời gian xử lý và số truy vấn đồng thời. Các giá trị được chọn cần gắn với mục tiêu khả dụng và tài nguyên của hệ thống.

Không có fallback vô hạn khi timeout hoặc parser lỗi. Một lỗi nguồn phụ thuộc không được dẫn đến bỏ điều kiện, chuyển sang quét toàn bộ hoặc gửi một thao tác thay thế rộng hơn.

## 10. Các lớp phòng vệ bổ sung và giới hạn của chúng

Tài khoản database của ứng dụng cần quyền tương ứng với nghiệp vụ. Một dịch vụ chỉ đọc không nên có quyền quản trị hoặc sửa dữ liệu không liên quan. Điều này giảm phạm vi tác động khi có lỗi, nhưng không sửa được một query đọc ngoài quyền người dùng nếu tài khoản dịch vụ vốn đọc được nhiều dữ liệu.

Schema validation tại collection hỗ trợ bảo vệ cấu trúc document lưu trữ. Tài liệu MongoDB mô tả việc kiểm tra insert và update theo cấu hình; đây không phải một bộ kiểm tra hợp đồng query cho mỗi request. Xem [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).

Do đó, schema của dữ liệu lưu không thay thế schema request. Collection có thể chỉ chứa những document hợp lệ nhưng một filter bị thay đổi vẫn chọn sai tập document.

TLS, giới hạn kết nối mạng, quản lý secret và bảo vệ giao diện quản trị cũng cần theo mô hình đe dọa. Chúng bảo vệ những bề mặt khác, không trao cho input quyền được điều khiển cấu trúc query.

WAF hoặc quy tắc nhận dạng ký tự có thể giúp phát hiện một số mẫu bất thường. Không nên dùng việc một payload bị WAF chặn làm bằng chứng rằng mọi sink trong ứng dụng đều an toàn. Luồng import, consumer hoặc dữ liệu đã lưu có thể không đi qua cùng lớp đó.

## 11. Tập yêu cầu bảo mật có thể nghiệm thu

Các mã dưới đây là thiết kế minh họa, cần gắn với danh mục điểm tiếp nhận và thao tác database của sản phẩm cụ thể.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| NOSQL-01 | Mọi endpoint và consumer có schema field, kiểu và cấu trúc được phép | Hợp đồng đầu vào, cấu hình parser/binder và kiểm tra sai kiểu |
| NOSQL-02 | Không đưa raw filter, update document, pipeline hoặc mã thực thi do client điều khiển vào driver | Truy vết các sink và kiểm tra luồng từ input tới thao tác |
| NOSQL-03 | Tên field, toán tử, sort, projection và collection được server chọn từ tập cho phép theo chức năng | Bảng ánh xạ và kịch bản gửi lựa chọn ngoài tập |
| NOSQL-04 | Giá trị được kiểm tra kiểu trước khi dựng query; không parse lại giá trị thành cấu trúc thực thi | Kiểm tra object thay scalar và chuỗi có hình thức giống query |
| NOSQL-05 | Scope quyền bắt buộc do server xác lập và không bị ghi đè hoặc vượt qua bằng grouping | Kiểm tra đa tenant, OR, field trùng và các đường đếm/xuất dữ liệu |
| NOSQL-06 | Regex hoặc ngôn ngữ biểu thức chỉ tồn tại khi có yêu cầu rõ ràng, quyền và ngân sách riêng | Danh mục tính năng, giới hạn và kiểm tra chi phí theo mẫu được phép |
| NOSQL-07 | Input lỗi hoặc dựng filter thất bại không dẫn đến truy vấn rộng hơn | Kịch bản lỗi và quan sát thao tác thực sự gửi tới database |
| NOSQL-08 | Bộ lọc đã lưu được kiểm tra theo schema, provenance và quyền tại thời điểm sử dụng | Kịch bản lưu rồi chạy lại, thay quyền và thay phiên bản schema |
| NOSQL-09 | Các thao tác được giới hạn đầu vào, đầu ra và tài nguyên theo ngân sách đã định nghĩa | Kết quả kiểm tra giới hạn, timeout và hành vi hủy |
| NOSQL-10 | Phản hồi và log không lộ query thô, credential hoặc dữ liệu ngoài quyền | Kiểm tra các nhánh lỗi, chẩn đoán và báo cáo xuất |
| NOSQL-11 | Quyền database và cấu hình tính năng thực thi chỉ đủ cho nghiệp vụ | Chính sách quyền và kiểm tra khả năng thao tác ngoài phạm vi |

Mỗi yêu cầu cần owner và phạm vi cụ thể. Đội API sở hữu schema; đội ứng dụng sở hữu việc dựng thao tác; đội dữ liệu hoặc nền tảng sở hữu quyền và cấu hình database; đội kiểm thử xác minh hiệu quả xuyên các lớp.

Danh mục sink nên bao gồm cả đọc và ghi. Một nơi không có truy vấn tìm kiếm trực tiếp vẫn có thể tiếp nhận cấu trúc nguy hiểm qua thao tác cập nhật, tác vụ báo cáo hoặc bộ lọc hàng loạt.

## 12. Thiết kế dữ liệu và kịch bản nghiệm thu

Chỉ thực hiện các kịch bản trên môi trường được phép với dữ liệu tổng hợp. Có thể tạo hai tenant A và B, mỗi tenant có các đơn hàng đánh dấu riêng. Trong tenant A, tạo cả bản ghi thỏa và không thỏa điều kiện tìm kiếm để kiểm tra query có bị mở rộng ngay trong cùng tenant hay không.

| Kịch bản | Kết quả mong đợi trong endpoint minh họa |
|---|---|
| Request đúng schema | Trả đúng các bản ghi được phép, đúng điều kiện và giới hạn |
| `customerRef` là object có key toán tử | Bị từ chối tại biên, không chuyển thành điều kiện database |
| `customerRef` là array hoặc `null` | Bị từ chối theo schema, không bỏ điều kiện tìm kiếm |
| `status` là object thay enum | Bị từ chối, không đưa cấu trúc vào query |
| Gửi thêm field `filter`, `pipeline` hoặc `tenantId` | Bị từ chối theo hợp đồng, không chép vào thao tác |
| String chứa văn bản giống query | Được xử lý như literal nếu schema cho phép, hoặc bị từ chối theo quy tắc field; không đổi cấu trúc |
| Gửi sort hoặc field không được công bố | Bị từ chối, không được dùng như tên field database |
| Hai field cùng tên trong một object | Được xử lý theo chính sách parser đã định nghĩa, không có diễn giải khác nhau giữa các lớp |
| Điều kiện OR trong tính năng nâng cao | Mọi kết quả vẫn nằm trong scope bắt buộc |
| Thiếu scope hoặc scope không được cấp quyền | Không thực thi query rộng hoặc dùng tenant mặc định |
| Filter không hợp lệ hoặc nguồn phụ thuộc lỗi | Không fallback sang filter rỗng |
| Bộ lọc do user lưu rồi worker chạy lại | Vẫn áp dụng schema và quyền cần thiết, không tin vì đã lưu |
| Input hoặc danh sách điều kiện vượt giới hạn | Từ chối có kiểm soát, không tạo chi phí không giới hạn |
| Gọi đường đếm, export hoặc cập nhật tương ứng | Không vượt scope chỉ vì dùng endpoint khác |

Kết quả trả lỗi chưa đủ chứng minh query không chạy. Trong môi trường kiểm thử, cần quan sát sink hoặc dùng công cụ kiểm tra tương ứng để xác nhận không có thao tác nguy hiểm được gửi trước khi response lỗi xuất hiện.

Cũng cần một request đối chứng hợp lệ. Một implementation từ chối mọi request sẽ không làm lộ dữ liệu nhưng không đáp ứng chức năng. Bằng chứng tốt phải cho thấy dữ liệu hợp lệ được xử lý đúng và cấu trúc không được phép không thể mở rộng quyền hoặc ý nghĩa query.

Với các lựa chọn filter được phép, có thể kiểm tra cấu trúc BSON sinh ra và tập kết quả thực tế. Chỉ so sánh text hiển thị của query có thể nhầm lẫn giữa các biểu diễn tương đương; điều cần bảo vệ là toán tử, field, grouping, kiểu giá trị và scope.

Nếu cần thu thao tác để kiểm thử, dùng dữ liệu tổng hợp và quyền truy cập phù hợp. Không bật ghi toàn bộ query sản xuất chỉ để chứng minh không có injection, vì giá trị filter có thể là dữ liệu cá nhân hoặc thông tin nhạy cảm.

## 13. Phản hồi lỗi và điều tra sự cố

API có thể trả mã ổn định như `INVALID_SEARCH_INPUT` kèm request ID và đường dẫn field đã được kiểm soát. Không đưa nguyên exception của parser hoặc database ra ngoài; exception có thể chứa query, tên collection, đường dẫn nội bộ hoặc dữ liệu đầu vào.

Log nên đủ để xác định endpoint, loại vi phạm schema, mẫu thao tác do server định nghĩa và scope theo chính sách dữ liệu. Không cần ghi raw body hoặc credential để biết một object đã được gửi vào field scalar.

Các dấu hiệu cần điều tra có thể gồm tỷ lệ lỗi kiểu tăng, yêu cầu field không được công bố hoặc nhiều truy vấn chạm ngân sách tài nguyên. Đây là tín hiệu, không phải bằng chứng tự động rằng mọi request đó là tấn công; quyết định cần gắn với bối cảnh và dữ liệu có thẩm quyền.

Khi phát hiện một đường injection, cần xác định phạm vi thao tác có thể bị thay đổi, dữ liệu bị tiếp cận và quyền của tài khoản database. Sửa điểm dựng query và bổ sung kiểm tra hồi quy; đồng thời rà soát các sink có cùng mẫu ánh xạ input. Không coi việc chặn một toán tử cụ thể là đã xử lý mọi trường hợp của lỗi thiết kế.

## 14. Những ngộ nhận và bài tập áp dụng

| Ngộ nhận | Điều cần kiểm tra lại |
|---|---|
| “NoSQL không dùng SQL nên không có injection” | Dữ liệu có điều khiển cấu trúc hoặc biểu thức của thao tác không |
| “JSON parse thành công là input an toàn” | Đúng cú pháp có thể vẫn là một query ngoài hợp đồng |
| “Dùng object hoặc builder là đủ” | Field, toán tử và các object con có do client điều khiển không |
| “Chỉ cấm ký tự `$` là được” | Schema, kiểu và toàn bộ các vị trí điều khiển có được giới hạn không |
| “Tắt JavaScript là hết rủi ro” | Operator injection và lỗi scope vẫn có thể tồn tại |
| “Database đã có schema” | Schema dữ liệu lưu khác với hợp đồng query của ứng dụng |
| “Có tenant trong query là đủ” | Grouping và đường fallback có cho phép vượt scope không |
| “Chỉ trả 20 bản ghi nên truy vấn luôn nhẹ” | Chi phí tìm và lọc trước khi trả kết quả có được giới hạn không |

Một dịch vụ báo cáo cho phép người dùng lưu bộ lọc dạng JSON. API lúc lưu kiểm tra rằng JSON hợp lệ nhưng không kiểm tra field hay toán tử. Worker xuất báo cáo sau đó parse lại JSON thành filter, thêm tenant bằng cách trộn map và gửi tới database bằng tài khoản có quyền đọc toàn bộ tenant.

Hãy thực hiện các việc sau trên thiết kế:

1. Xác định các ranh giới mà dữ liệu được trao quyền điều khiển thao tác.
2. Đề xuất schema nghiệp vụ cho filter thay vì nhận raw query database.
3. Mô tả cách tạo scope bắt buộc và giữ nó khi có nhóm OR.
4. Viết một yêu cầu cho bộ lọc đã lưu và một yêu cầu cho quyền của worker.
5. Thiết kế dữ liệu kiểm thử gồm hai tenant và các bản ghi đối chứng trong cùng tenant.
6. Nêu bằng chứng cho thấy lỗi không dẫn đến export rộng hơn hoặc ghi query nhạy cảm vào log.

Kết quả cần là hợp đồng về quyền điều khiển query, không chỉ một hàm thay thế ký tự. NoSQL injection được phòng vệ hiệu quả khi server giữ cấu trúc thao tác, giá trị được kiểm tra đúng kiểu và mọi đường thực thi luôn bị ràng buộc bởi phạm vi quyền đã xác minh.
