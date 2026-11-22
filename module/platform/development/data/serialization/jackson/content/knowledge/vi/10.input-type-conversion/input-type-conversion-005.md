# Xử lý chuỗi rỗng và khoảng trắng khi chuyển kiểu

Khi Jackson đọc JSON, giá trị dạng chuỗi đôi khi được chuyển sang kiểu Java khác. Ví dụ, client có thể gửi số lượng dưới dạng chuỗi `"25"`, hoặc gửi trường tìm kiếm với giá trị `""` hay chỉ chứa dấu cách. Những giá trị này không giống nhau và không phải kiểu Java nào cũng xử lý chúng theo cùng một cách.

Trong Jackson, cần phân biệt:

- **Chuỗi rỗng:** `""`, tức chuỗi có độ dài bằng 0.
- **Chuỗi chỉ có khoảng trắng:** `"   "`, có ký tự nhưng không có nội dung ngoài whitespace.
- **Chuỗi có nội dung và khoảng trắng ở hai đầu:** `" 25 "`.
- **JSON null:** `null`, đây là giá trị JSON riêng, không phải chuỗi.
- **Property bị thiếu:** tên trường hoàn toàn không xuất hiện trong object JSON.

Khi chuyển kiểu, các trạng thái này có thể dẫn đến kết quả khác nhau: giữ nguyên chuỗi, chuyển thành null, chuyển thành giá trị rỗng của kiểu đích hoặc báo lỗi. Hiểu các quy tắc coercion của Jackson giúp ứng dụng xác định rõ dữ liệu nào được chấp nhận và tránh âm thầm biến input không hợp lệ thành giá trị mặc định.

## 1. Bốn dạng input cần phân biệt

Hãy xét property `quantity` trong request JSON:

```json
{ "quantity": "25" }
```

Đây là chuỗi có nội dung. Nếu kiểu Java đích là `Integer`, Jackson có thể chuyển chuỗi số thành số nguyên theo các quy tắc coercion hiện hành.

Các input sau mang ý nghĩa khác:

```json
{ "quantity": "" }
```

Chuỗi rỗng không chứa ký tự nào.

```json
{ "quantity": "   " }
```

Chuỗi này có ký tự whitespace nhưng không có nội dung thực tế.

```json
{ "quantity": null }
```

Đây là JSON null, không phải chuỗi rỗng.

Và cuối cùng:

```json
{}
```

Property `quantity` bị thiếu hoàn toàn. Với bean có field initializer hoặc constructor đặt giá trị mặc định, trạng thái này có thể giữ lại giá trị đã khởi tạo.

Không nên gộp các trạng thái trên thành khái niệm chung “không có dữ liệu”. Hợp đồng API có thể quy định chúng khác nhau, ví dụ chuỗi rỗng nghĩa là người dùng xóa nội dung, whitespace được trim thành rỗng, null nghĩa là không xác định, còn thiếu trường nghĩa là không thay đổi giá trị hiện tại.

## 2. Jackson xử lý chuỗi khi đích là String

Với property Java có kiểu `String`, Jackson thông thường giữ nội dung chuỗi nhận được. Nó không tự động trim mọi chuỗi chỉ vì chuỗi có khoảng trắng ở đầu hoặc cuối.

Ví dụ:

```java
public record SearchRequest(String keyword) {}
```

Với các input:

```json
{ "keyword": "  jackson  " }
```

giá trị `keyword` thường vẫn là `"  jackson  "`.

```json
{ "keyword": "   " }
```

giá trị vẫn là chuỗi chứa ba dấu cách, không tự động biến thành `null` hoặc `""`.

```json
{ "keyword": "" }
```

giá trị là chuỗi rỗng.

Nếu muốn loại bỏ khoảng trắng ở đầu/cuối, hãy quy định việc chuẩn hóa rõ ràng. Có thể thực hiện trong setter, custom deserializer hoặc tầng chuyển đổi request. Việc trim là quy tắc nghiệp vụ của ứng dụng; không nên giả định Jackson tự thực hiện cho mọi kiểu chuỗi.

### 2.1. Chuẩn hóa String bằng setter

Với DTO đơn giản, có thể chuẩn hóa ngay khi gán:

```java
public class SearchRequest {
    private String keyword;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword == null ? null : keyword.strip();
    }
}
```

`strip()` có từ Java 11 và loại bỏ whitespace theo định nghĩa Unicode ở hai đầu chuỗi. Nếu dự án dùng Java cũ hơn, có thể dùng `trim()`, nhưng `trim()` có quy tắc hẹp hơn và không xử lý mọi whitespace Unicode.

Sau khi chuẩn hóa:

- `"  jackson  "` trở thành `"jackson"`.
- `"   "` trở thành `""`.
- `""` vẫn là `""`.
- `null` vẫn là `null`.

Nếu muốn chuỗi chỉ có whitespace trở thành null, có thể viết rõ:

```java
public void setKeyword(String keyword) {
    if (keyword == null) {
        this.keyword = null;
        return;
    }

    String normalized = keyword.strip();
    this.keyword = normalized.isEmpty() ? null : normalized;
}
```

Không nên trim mọi trường String một cách tự động nếu có trường hợp khoảng trắng mang ý nghĩa, chẳng hạn nội dung văn bản, mã định danh có quy ước riêng hoặc dữ liệu cần giữ nguyên để ký số.

## 3. Coercion khi đích là kiểu số

Jackson Databind có thể chuyển một số scalar JSON sang kiểu số Java, tùy kiểu đích, phiên bản và cấu hình mapper. Ví dụ, một giá trị JSON string chứa số như `"25"` có thể được chuyển thành `Integer`.

```java
public record QuantityRequest(Integer quantity) {}
```

Input:

```json
{ "quantity": "25" }
```

Khi coercion được cho phép, kết quả có thể là `Integer.valueOf(25)`. Tuy nhiên, `""` và chuỗi chỉ chứa khoảng trắng không phải chuỗi số hợp lệ theo cách chuyển đổi thông thường. Jackson có các quy tắc riêng để quyết định chúng thành null, giá trị rỗng, thử chuyển đổi hay báo lỗi.

Với dữ liệu quan trọng như số lượng, giá tiền hoặc giới hạn phân trang, không nên dựa vào một giả định chung rằng mọi chuỗi rỗng đều tự thành `0` hoặc null. Hãy xác định chính sách theo kiểu đích và kiểm thử với phiên bản Jackson mà dự án đang sử dụng.

## 4. CoercionConfig: cấu hình cách xử lý chuỗi rỗng

Từ Jackson Databind 2.12, API coercion cho phép cấu hình cách chuyển các dạng input nhất định theo logical type hoặc kiểu Java cụ thể.

Các khái niệm chính:

- `CoercionInputShape`: hình dạng đầu vào, ví dụ `EmptyString`, `EmptyArray`, `Integer`, `Float`, `Boolean`.
- `CoercionAction`: hành động Jackson thực hiện khi gặp hình dạng đó.
- `LogicalType`: nhóm kiểu logic như Integer, Float, Textual, Boolean, DateTime hoặc POJO.
- `CoercionConfig`: cấu hình coercion cho nhóm kiểu hoặc kiểu đích.

Các hành động thường gặp:

| CoercionAction | Ý nghĩa |
| --- | --- |
| `TryConvert` | Thử chuyển đổi theo deserializer thông thường. |
| `AsNull` | Chuyển đầu vào thành giá trị null của kiểu đích. |
| `AsEmpty` | Dùng giá trị rỗng mà deserializer của kiểu đích cung cấp. |
| `Fail` | Từ chối chuyển đổi và báo lỗi. |

Ví dụ, muốn chuỗi rỗng thành null khi đọc các kiểu số nguyên:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;

ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

Sau cấu hình này, chuỗi rỗng được xử lý như null đối với nhóm kiểu số nguyên theo coercion config đã đặt. Kết quả cụ thể tiếp theo còn phụ thuộc kiểu Java đích: `Integer` có thể chứa null, còn `int` là primitive và không thể chứa null.

### 4.1. Cấu hình theo kiểu Java cụ thể

Nếu chỉ muốn áp dụng cho một kiểu đích cụ thể, có thể cấu hình theo class:

```java
mapper.coercionConfigFor(Integer.class)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

Phạm vi cấu hình theo kiểu giúp giới hạn ảnh hưởng. Ví dụ, một API có thể chấp nhận chuỗi rỗng thành null cho `Integer` nhưng yêu cầu `BigDecimal` phải nhận giá trị số hợp lệ.

### 4.2. Chuỗi chỉ có whitespace

Chuỗi rỗng `""` và chuỗi chỉ có whitespace `"   "` là hai hình dạng đầu vào khác nhau. Các phiên bản Jackson mới có hỗ trợ cấu hình cách xử lý blank string thông qua `acceptBlankAsEmpty` trong coercion configuration. Ví dụ cấu hình mặc định cho mapper:

```java
mapper.coercionConfigDefaults()
        .setAcceptBlankAsEmpty(true);
```

Thiết lập này yêu cầu Jackson coi chuỗi chỉ chứa whitespace như dạng empty khi áp dụng các quy tắc coercion tương ứng. Hãy kiểm tra API của phiên bản Jackson đang dùng vì khả năng coercion và cách áp dụng có thể khác giữa các phiên bản.

Nếu cần hành vi nghiêm ngặt, có thể đặt `setAcceptBlankAsEmpty(false)` hoặc cấu hình `CoercionAction.Fail` cho `EmptyString` ở logical type/kiểu đích phù hợp. Không nên bật chính sách blank string toàn cục nếu một số trường văn bản cần giữ nguyên khoảng trắng.

## 5. Chọn AsNull, AsEmpty hay Fail?

Ba hành động thường dùng thể hiện ba hợp đồng dữ liệu khác nhau.

### 5.1. AsNull: coi chuỗi rỗng như null

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

Phù hợp khi trường số là tùy chọn và client gửi chuỗi rỗng được hiểu như không cung cấp giá trị. Với wrapper `Integer`, kết quả có thể là null. Với primitive `int`, Jackson phải áp dụng quy tắc xử lý null cho primitive; tùy feature và kiểu đích, có thể nhận giá trị primitive mặc định hoặc bị từ chối.

### 5.2. AsEmpty: dùng giá trị rỗng của kiểu đích

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsEmpty);
```

`AsEmpty` yêu cầu deserializer cung cấp empty value cho kiểu đích. Với kiểu số, giá trị rỗng có thể là dạng zero theo implementation; với kiểu khác, ý nghĩa empty value có thể khác. Không nên hiểu `AsEmpty` là luôn tạo chuỗi `""` hoặc luôn trả null.

### 5.3. Fail: từ chối chuỗi rỗng

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
```

Chính sách này phù hợp khi trường số đã xuất hiện thì bắt buộc phải chứa giá trị số hợp lệ. Input `""` sẽ gây lỗi chuyển đổi thay vì bị âm thầm diễn giải thành null hoặc zero.

## 6. Phân biệt coercion với các feature cũ

Jackson có một số feature phục vụ các trường hợp empty input cụ thể. Chúng không hoàn toàn tương đương với coercion config.

### 6.1. ACCEPT_EMPTY_STRING_AS_NULL_OBJECT

`DeserializationFeature.ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` cho phép empty String được chấp nhận như null khi deserialize một số kiểu object/structured type. Feature này thường được nhắc đến với POJO hoặc kiểu cấu trúc, không phải một quy tắc tổng quát cho mọi scalar như số, boolean và String.

```java
import com.fasterxml.jackson.databind.DeserializationFeature;

mapper.enable(DeserializationFeature.ACCEPT_EMPTY_STRING_AS_NULL_OBJECT);
```

Không nên dùng feature này để kỳ vọng mọi property số nhận `""` theo một cách cụ thể. Với coercion cho scalar, hãy cấu hình `CoercionConfig` theo logical type hoặc class.

### 6.2. ALLOW_COERCION_OF_SCALARS

`MapperFeature.ALLOW_COERCION_OF_SCALARS` liên quan đến việc cho phép một số chuyển đổi scalar ngoài kiểu tự nhiên của JSON. Nếu ứng dụng cần kiểm soát chặt kiểu đầu vào, hãy xem xét tắt coercion không mong muốn và đặt quy tắc rõ ràng cho từng kiểu.

CoercionConfig cung cấp cách biểu đạt cụ thể hơn cho từng input shape và logical type. Khi dùng đồng thời feature cũ và coercion config, cần kiểm tra thứ tự ưu tiên và hành vi theo phiên bản Jackson của dự án.

## 7. Boolean, enum và các kiểu khác

Chuỗi rỗng hoặc whitespace không chỉ ảnh hưởng đến kiểu số. Các kiểu scalar khác cũng có quy tắc riêng:

- **Boolean:** `"true"` hoặc `"false"` có thể được chuyển đổi tùy coercion; `""` không phải giá trị boolean hợp lệ thông thường.
- **Enum:** chuỗi rỗng hoặc blank có thể được xử lý theo coercion và các feature dành cho enum; không nên giả định nó tự chọn một enum mặc định.
- **Date/Time:** chuỗi rỗng không phải ngày giờ hợp lệ. Nếu muốn coi nó là null hoặc empty, hãy cấu hình rõ và kiểm tra module Java Time đang sử dụng.
- **POJO:** `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` hoặc coercion config có thể ảnh hưởng việc chuỗi rỗng được dùng làm giá trị null cho object.
- **Collection/Map:** JSON array/object có cấu trúc khác với chuỗi rỗng. Nếu nhận chuỗi rỗng cho kiểu collection, cần quy định rõ có từ chối hay chuyển thành empty collection hay không.

Đối với các kiểu nghiệp vụ quan trọng, nên ưu tiên hợp đồng đầu vào rõ ràng và validation cụ thể. Việc coercion thành công chỉ cho biết Jackson tạo được giá trị Java, không bảo đảm giá trị đó hợp lệ về nghiệp vụ.

## 8. Chuẩn hóa khoảng trắng bằng custom deserializer

Nếu quy tắc trim chỉ áp dụng cho một số trường String hoặc cần biến blank thành null, custom deserializer là một lựa chọn. Ví dụ sau dùng Java 11 trở lên:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

import java.io.IOException;

public class TrimmedStringDeserializer extends JsonDeserializer<String> {
    @Override
    public String deserialize(JsonParser parser,
                              DeserializationContext context) throws IOException {
        String value = parser.getValueAsString();
        if (value == null) {
            return null;
        }

        String normalized = value.strip();
        return normalized.isEmpty() ? null : normalized;
    }
}
```

Gắn deserializer vào property:

```java
public class SearchRequest {
    @JsonDeserialize(using = TrimmedStringDeserializer.class)
    private String keyword;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
```

Với cấu hình này, chuỗi `"  jackson  "` trở thành `"jackson"`; chuỗi rỗng hoặc chỉ có whitespace trở thành null. Deserializer chỉ áp dụng cho property được gắn annotation, giúp tránh thay đổi mọi trường String trong ứng dụng.

Nếu cần giữ nguyên chuỗi rỗng nhưng chỉ trim whitespace, hãy trả về `normalized` thay vì đổi chuỗi rỗng thành null. Nếu cần áp dụng quy tắc chung cho mọi String, có thể đăng ký custom deserializer qua module, nhưng phải cân nhắc kỹ tác động đến các trường cần giữ nguyên văn bản.

## 9. Ví dụ cấu hình một DTO có quy tắc rõ ràng

Giả sử API nhận một bộ lọc sản phẩm:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

public class ProductFilter {
    @JsonDeserialize(using = TrimmedStringDeserializer.class)
    private String keyword;

    @JsonSetter(nulls = Nulls.SKIP)
    private Integer pageSize = 20;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
```

Các quy tắc được thiết kế riêng:

- `keyword` được trim; chuỗi blank được chuẩn hóa thành null.
- `pageSize` giữ default 20 nếu property bị thiếu.
- `pageSize` cũng giữ default 20 nếu JSON gửi null vì null setter được skip.
- Nếu `pageSize` là chuỗi số, hành vi chuyển kiểu phụ thuộc coercion config của mapper.
- Nếu `pageSize` là chuỗi rỗng, ứng dụng cần cấu hình rõ `AsNull`, `AsEmpty` hoặc `Fail` cho kiểu số nguyên theo hợp đồng mong muốn.

Trong ví dụ thực tế, nên tách class deserializer và DTO thành các file Java riêng. Đoạn code trên minh họa cách các cơ chế có thể kết hợp, không phải một chính sách mặc định phù hợp cho mọi API.

## 10. Bảng lựa chọn hành vi

| Input | Kiểu đích String | Kiểu đích Integer (phụ thuộc coercion) | Ý nghĩa cần xác định |
| --- | --- | --- | --- |
| Property bị thiếu | Không có thao tác gán; default có thể được giữ | Không có thao tác gán; default có thể được giữ | Không cung cấp trường |
| `""` | Chuỗi rỗng | Có thể AsNull, AsEmpty, Fail hoặc TryConvert | Chuỗi rỗng |
| `"   "` | Chuỗi whitespace được giữ nếu không chuẩn hóa | Phụ thuộc blank-string coercion và phiên bản/cấu hình | Chỉ có khoảng trắng |
| `" 25 "` | Giữ nguyên nếu không trim | Có thể chuyển số nếu deserializer chấp nhận chuỗi số có whitespace | Chuỗi có nội dung kèm whitespace |
| `null` | null | null cho wrapper; primitive cần chính sách riêng | JSON null |
| `25` | Có thể chuyển sang chuỗi theo coercion/cấu hình | Số nguyên tự nhiên | JSON number |

Không nên dựa vào một bảng mặc định chung để suy ra mọi phiên bản Jackson. Khi nâng phiên bản, hãy kiểm tra coercion config và viết kiểm thử cho những input quan trọng như `""`, `" "`, `null`, chuỗi số hợp lệ và chuỗi số sai định dạng.

## 11. Ghi nhớ

- `""`, `"   "`, `null` và property bị thiếu là bốn trạng thái khác nhau.
- Jackson không tự trim mọi giá trị String; nếu cần trim, hãy quy định bằng setter, custom deserializer hoặc tầng chuẩn hóa dữ liệu.
- Khi chuyển chuỗi sang số hoặc kiểu scalar khác, hành vi của empty/blank string phụ thuộc logical type, coercion config, phiên bản và kiểu Java đích.
- `CoercionAction.AsNull`, `AsEmpty`, `TryConvert` và `Fail` thể hiện những chính sách khác nhau.
- `CoercionConfig` có thể cấu hình theo logical type hoặc class; blank string có thể cần cấu hình riêng qua `acceptBlankAsEmpty` trên phiên bản hỗ trợ.
- `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` dành cho một số kiểu object/structured type, không thay thế coercion config cho mọi scalar.
- Coercion chỉ chuyển đổi dữ liệu; validation nghiệp vụ vẫn cần kiểm tra giá trị sau khi deserialize.

Khi thiết kế API, hãy ghi rõ ý nghĩa của chuỗi rỗng và whitespace cho từng trường. Chọn chính sách chuyển kiểu phù hợp, giới hạn phạm vi cấu hình và kiểm tra cả empty string lẫn blank string để tránh dữ liệu không hợp lệ bị chuyển thành null hoặc giá trị mặc định ngoài ý muốn.
