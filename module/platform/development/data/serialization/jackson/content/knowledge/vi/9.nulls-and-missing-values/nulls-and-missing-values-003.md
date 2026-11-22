# Thiết kế giá trị mặc định tại constructor hoặc thuộc tính

Khi Jackson deserialize JSON thành object Java, không phải trường nào trong JSON cũng xuất hiện. Có request chỉ gửi một vài thuộc tính, còn các thuộc tính khác cần giữ giá trị mặc định để ứng dụng hoạt động đúng.

Ví dụ, một API tìm kiếm có thể mặc định dùng trang đầu tiên, mỗi trang 20 kết quả và sắp xếp theo thời gian tạo. Client chỉ gửi `keyword` thì ứng dụng vẫn cần có `page`, `pageSize` và `sort` hợp lệ.

Trong Java, các giá trị mặc định có thể được thiết lập tại **field initializer** hoặc **constructor**. Khi Jackson tạo object theo cách dùng constructor không tham số rồi gán các property có trong JSON, giá trị khởi tạo sẽ được giữ lại nếu property tương ứng bị thiếu. Tuy nhiên, một property xuất hiện với giá trị JSON `null` lại là tình huống khác: mặc định Jackson có thể gán `null` vào thuộc tính tham chiếu và ghi đè giá trị ban đầu.

Vì vậy, khi thiết kế giá trị mặc định, cần phân biệt rõ ba trạng thái: property bị thiếu, property có giá trị `null` và property có giá trị cụ thể.

## 1. Giá trị mặc định trong Java

Java cho phép khởi tạo giá trị ngay tại khai báo field:

```java
public class SearchOptions {
    private int page = 0;
    private int pageSize = 20;
    private String sort = "createdAt";
}
```

Field initializer được thực hiện khi object được tạo. Nếu muốn thực hiện logic khởi tạo nhiều bước hoặc giá trị mặc định phụ thuộc nhau, bạn có thể đặt logic đó trong constructor:

```java
public class SearchOptions {
    private int page;
    private int pageSize;
    private String sort;

    public SearchOptions() {
        this.page = 0;
        this.pageSize = 20;
        this.sort = "createdAt";
    }
}
```

Với constructor không tham số, hai cách trên đều tạo ra object có giá trị ban đầu. Field initializer thường ngắn gọn cho giá trị đơn giản; constructor phù hợp khi cần diễn đạt quy tắc khởi tạo hoặc bảo đảm một số bất biến của object.

## 2. Jackson xử lý property bị thiếu như thế nào?

Với JavaBean có constructor không tham số, luồng deserialize khái quát là:

1. Jackson tạo instance bằng constructor.
2. Jackson đọc các property có trong JSON.
3. Với mỗi property được nhận diện, Jackson chuyển giá trị sang kiểu Java và gán qua field, setter hoặc cơ chế truy cập phù hợp.
4. Property không xuất hiện trong JSON thường không được gán lại.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

public class SearchOptions {
    private int page = 0;
    private int pageSize = 20;
    private String sort = "createdAt";
    private List<String> tags = new ArrayList<>();

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }

    public int getPageSize() {
        return pageSize;
    }

    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }

    public String getSort() {
        return sort;
    }

    public void setSort(String sort) {
        this.sort = sort;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Khi đọc JSON:

```json
{
  "page": 2
}
```

Jackson tạo `SearchOptions`, sau đó gán `page = 2`. Các property `pageSize`, `sort` và `tags` không xuất hiện nên không bị gán lại. Kết quả vẫn có:

```text
page     = 2
pageSize = 20
sort     = "createdAt"
tags     = []
```

Đây là cách đơn giản và thường phù hợp nhất để thiết kế default cho DTO có thể được tạo bằng constructor không tham số.

## 3. Property bị thiếu khác với property có JSON null

Hãy so sánh hai JSON sau:

```json
{}
```

và:

```json
{
  "sort": null
}
```

JSON thứ nhất không chứa property `sort`. Nếu Jackson tạo bean từ constructor không tham số và không có bước nào khác gán property đó, giá trị initializer `"createdAt"` vẫn được giữ.

JSON thứ hai có property `sort` với giá trị `null`. Đây là một giá trị đầu vào rõ ràng. Với thuộc tính tham chiếu như `String`, chính sách mặc định thường gán `null` vào property, khiến giá trị mặc định `"createdAt"` bị ghi đè.

Có thể nhìn thấy sự khác biệt qua bảng:

| JSON đầu vào | Hành vi thông thường với bean có field initializer `sort = "createdAt"` | Kết quả |
| --- | --- | --- |
| Không có `sort` | Không có thao tác gán cho property | `"createdAt"` |
| `"sort": null` | Gán null cho thuộc tính tham chiếu | `null` |
| `"sort": "name"` | Gán giá trị được gửi | `"name"` |

Đây là khác biệt quan trọng khi thiết kế API. Client có thể hiểu “không gửi trường” là dùng mặc định, nhưng “gửi null” là chủ động xóa giá trị. Nếu ứng dụng muốn cả hai tình huống đều giữ default, cần cấu hình xử lý null rõ ràng.

## 4. Dùng @JsonSetter(nulls = Nulls.SKIP) để giữ default khi nhận null

Jackson cung cấp `Nulls.SKIP` để bỏ qua việc gán khi giá trị đầu vào là JSON `null`. Khi setter không được gọi, giá trị đã có từ field initializer hoặc constructor được giữ nguyên.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

import java.util.ArrayList;
import java.util.List;

public class SearchOptions {
    private int pageSize = 20;
    private String sort = "createdAt";
    private List<String> tags = new ArrayList<>();

    public int getPageSize() {
        return pageSize;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }

    public String getSort() {
        return sort;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setSort(String sort) {
        this.sort = sort;
    }

    public List<String> getTags() {
        return tags;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Khi deserialize `{"sort": null}`, Jackson bỏ qua thao tác gán `sort`; giá trị `"createdAt"` đã được khởi tạo vẫn còn nguyên. Khi deserialize `{"sort": "name"}`, setter được gọi với giá trị `"name"` và property nhận giá trị mới.

`Nulls.SKIP` có thể áp dụng cho từng property. Vì thế, bạn có thể giữ default cho `sort` nhưng vẫn cho phép một property khác nhận null theo hợp đồng.

### 4.1. Các chính sách null thường gặp

`@JsonSetter` có tùy chọn `nulls` với các giá trị trong `Nulls`:

| Chính sách | Ý nghĩa khi property có JSON null |
| --- | --- |
| `Nulls.SET` | Gán null theo hành vi thông thường cho kiểu đích. |
| `Nulls.SKIP` | Bỏ qua việc gán; giá trị hiện tại của object được giữ lại. |
| `Nulls.FAIL` | Báo lỗi khi gặp null. |
| `Nulls.AS_EMPTY` | Yêu cầu deserializer cung cấp giá trị rỗng phù hợp cho kiểu đích. |
| `Nulls.DEFAULT` | Dùng chính sách null mặc định đã cấu hình. |

Ví dụ, với collection, `AS_EMPTY` có thể biến JSON null thành collection rỗng theo empty value mà deserializer hỗ trợ:

```java
@JsonSetter(nulls = Nulls.AS_EMPTY)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Hãy phân biệt `nulls` với `contentNulls`. `nulls` áp dụng cho chính property, ví dụ toàn bộ `tags` là null. `contentNulls` áp dụng cho phần tử null bên trong collection hoặc map, ví dụ `tags` có dạng `["java", null]`.

## 5. Giá trị mặc định cho kiểu primitive

Các kiểu primitive như `int`, `long` và `boolean` không thể chứa null. Khi JSON gửi null cho primitive, Jackson có hành vi riêng; mặc định, nếu không bật `FAIL_ON_NULL_FOR_PRIMITIVES`, null có thể được chuyển thành giá trị primitive mặc định như `0` hoặc `false`.

Điều đó có thể làm mất giá trị initializer. Ví dụ:

```java
public class PagingRequest {
    private int pageSize = 20;

    public int getPageSize() {
        return pageSize;
    }

    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }
}
```

Với `{}`, `pageSize` giữ giá trị `20`. Nhưng với `{"pageSize": null}`, nếu null được chuyển thành primitive default và setter được gọi, giá trị có thể thành `0`.

Nếu muốn giữ default khi null, có thể áp dụng `@JsonSetter(nulls = Nulls.SKIP)` cho property. Nếu muốn từ chối null để client phải gửi giá trị hợp lệ hoặc bỏ hẳn property, có thể bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`.

Một lựa chọn khác là dùng wrapper `Integer` hoặc `Boolean` khi ứng dụng cần phân biệt rõ “không có giá trị” với `0` hoặc `false`. Sau khi deserialize, tầng validation hoặc nghiệp vụ sẽ quyết định cách diễn giải null.

## 6. Giá trị mặc định tại constructor

Field initializer phù hợp với giá trị đơn giản. Constructor phù hợp khi giá trị mặc định cần logic hoặc cần thiết lập nhiều field cùng nhau:

```java
public class ReportOptions {
    private String format;
    private boolean includeHeader;

    public ReportOptions() {
        this.format = "CSV";
        this.includeHeader = true;
    }

    public String getFormat() {
        return format;
    }

    public void setFormat(String format) {
        this.format = format;
    }

    public boolean isIncludeHeader() {
        return includeHeader;
    }

    public void setIncludeHeader(boolean includeHeader) {
        this.includeHeader = includeHeader;
    }
}
```

Với JSON `{}`, object giữ `format = "CSV"` và `includeHeader = true`, vì các setter tương ứng không được gọi. Nếu JSON gửi `{"format": "JSON"}`, giá trị được cung cấp sẽ thay thế default.

Hãy tránh đặt logic khởi tạo phụ thuộc vào database, network hoặc trạng thái môi trường trong constructor của DTO chỉ để phục vụ deserialize. Constructor nên khởi tạo trạng thái nội tại đơn giản; nghiệp vụ cần dữ liệu bên ngoài nên được thực hiện ở service hoặc factory riêng.

## 7. Constructor-based deserialization và record

Với immutable object hoặc Java record, Jackson thường tạo object thông qua constructor thay vì tạo bean rỗng rồi gọi setter. Khi đó, default trong constructor không tham gia theo cùng cách với JavaBean có constructor không tham số.

Ví dụ record có thể tự chuẩn hóa null trong compact constructor:

```java
public record ReportOptions(String format, boolean includeHeader) {
    public ReportOptions {
        if (format == null) {
            format = "CSV";
        }
    }
}
```

Constructor trên đặt `format` thành `"CSV"` nếu tham số nhận được là null. Điều này có thể áp dụng cho cả trường hợp property bị thiếu và trường hợp JSON gửi explicit null nếu cả hai cùng được chuyển thành tham số null.

Điểm cần lưu ý là compact constructor này không phân biệt được hai ý nghĩa:

- Client không gửi `format`, nên ứng dụng muốn dùng default.
- Client gửi `"format": null`, có thể muốn xóa giá trị hoặc báo lỗi.

Nếu cần phân biệt hai trường hợp trong mô hình immutable, cần thiết kế thêm cơ chế thể hiện sự hiện diện của property, chẳng hạn builder có trạng thái đã được gán, custom deserializer hoặc xử lý JSON tree trước khi tạo object. Không nên giả định rằng constructor luôn biết một tham số null đến từ property bị thiếu hay explicit null.

Với creator constructor, có thể dùng `@JsonProperty(required = true)` cho tham số bắt buộc. Thuộc tính `required` chủ yếu có ý nghĩa đối với creator property; nó không phải cơ chế đặt default. Ngoài ra, các feature như `FAIL_ON_MISSING_CREATOR_PROPERTIES` và `FAIL_ON_NULL_CREATOR_PROPERTIES` có thể thay đổi cách mapper xử lý tham số creator bị thiếu hoặc null.

## 8. @JsonProperty(defaultValue) có tự áp dụng default không?

`@JsonProperty` có thuộc tính `defaultValue`, nhưng cần hiểu đúng mục đích của nó:

```java
@JsonProperty(value = "format", defaultValue = "CSV")
private String format;
```

Trong Jackson Databind lõi, `defaultValue` chủ yếu là metadata để các công cụ hoặc tích hợp khác sử dụng, ví dụ mô tả schema hoặc tài liệu. Không nên dựa vào annotation này để kỳ vọng `ObjectMapper` tự gán `"CSV"` khi JSON thiếu property.

Muốn default thực sự có hiệu lực, hãy khởi tạo field/constructor, dùng builder có default rõ ràng, hoặc viết custom deserializer nếu quy tắc phức tạp. Nếu explicit null cần được xử lý riêng, kết hợp với chính sách null phù hợp như `Nulls.SKIP`, `Nulls.FAIL` hoặc logic tạo object tương ứng.

## 9. Bảng quyết định thiết kế default

| Yêu cầu | Cách triển khai thường phù hợp |
| --- | --- |
| Property không có trong JSON thì dùng giá trị mặc định | Field initializer hoặc constructor không tham số |
| Property có JSON null cũng giữ giá trị đã khởi tạo | `@JsonSetter(nulls = Nulls.SKIP)` |
| Property có JSON null thì dùng giá trị rỗng | `@JsonSetter(nulls = Nulls.AS_EMPTY)` nếu kiểu có empty value phù hợp |
| Property có JSON null phải bị từ chối | `@JsonSetter(nulls = Nulls.FAIL)` hoặc feature phù hợp cho primitive/creator |
| Mọi property phải được gửi trong constructor-based DTO | Creator property `required = true` hoặc `FAIL_ON_MISSING_CREATOR_PROPERTIES` |
| Default phụ thuộc nhiều tham số hoặc logic nghiệp vụ | Factory/service hoặc builder có quy tắc rõ ràng |
| Cần phân biệt missing với explicit null trong immutable DTO | Custom deserializer, builder theo dõi presence hoặc xử lý tree trước khi tạo object |

## 10. Ghi nhớ

Giá trị mặc định trong DTO là một phần của hợp đồng dữ liệu, không chỉ là tiện ích của Java. Khi dùng Jackson với bean có constructor không tham số, field initializer hoặc constructor thường cung cấp default cho property bị thiếu. Property có mặt với JSON null lại có thể ghi đè default; hãy chọn rõ chính sách null thay vì giả định missing và null giống nhau.

- Field initializer phù hợp với default đơn giản.
- Constructor phù hợp với logic khởi tạo nội tại và bất biến của object.
- `Nulls.SKIP` giữ giá trị hiện có khi JSON gửi null.
- Primitive không chứa null; cần chú ý hành vi chuyển null thành `0`/`false` hoặc bật chế độ từ chối.
- Creator constructor/record cần xử lý default theo tham số; null không tự cho biết property đã bị thiếu hay được gửi explicit null.
- `@JsonProperty(defaultValue = ...)` không tự động áp dụng default trong Jackson Databind lõi.

Khi thiết kế một request DTO, hãy xác định riêng hành vi cho property bị thiếu, property null và property có giá trị. Quy định rõ ba trường hợp này giúp API dễ dự đoán, tránh vô tình xóa default và giảm lỗi do client gửi payload không đầy đủ.
