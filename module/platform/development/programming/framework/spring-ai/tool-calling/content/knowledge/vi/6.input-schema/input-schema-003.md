# Mô hình hóa đối số bằng record hoặc DTO

Khi một công cụ chỉ cần một vài tham số đơn giản, phương thức `@Tool` có thể nhận trực tiếp `String`, số hoặc enum. Nhưng một thao tác nghiệp vụ thường cần nhiều trường liên quan: từ khóa, danh mục, khoảng giá, trạng thái còn hàng hoặc khoảng thời gian. Nếu đưa tất cả thành tham số rời, chữ ký phương thức nhanh chóng dài và khó mở rộng.

Spring AI có thể dùng một kiểu dữ liệu có cấu trúc như Java `record` hoặc DTO làm đối số của phương thức công cụ. Kiểu dữ liệu đó trở thành hợp đồng đầu vào: mô hình sinh một object JSON theo schema, framework chuyển object thành kiểu Java, rồi phương thức công cụ chuyển yêu cầu đã kiểm tra tới service nghiệp vụ.

Trong module `SPRING_AI_TOOL_CALLING`, cách mô hình hóa này giúp giữ rõ ranh giới giữa đối số mà mô hình được phép đề xuất và dữ liệu nội bộ mà ứng dụng phải tự cung cấp qua `ToolContext`. Ứng dụng vẫn chịu trách nhiệm xác thực, phân quyền, quy tắc nghiệp vụ và thực thi.

Sau bài học, bạn có thể:

- Chọn `record` hoặc DTO làm kiểu đối số cho một phương thức `@Tool`.
- Thiết kế property, kiểu dữ liệu, enum, trường bắt buộc và trường tùy chọn phù hợp với JSON Schema.
- Dùng object lồng nhau khi các trường tạo thành một khái niệm nghiệp vụ rõ ràng.
- Kiểm tra dữ liệu sau khi framework chuyển JSON thành Java object.
- Tách dữ liệu do mô hình sinh khỏi tenant, principal và thông tin tin cậy do ứng dụng truyền vào.

## 1. Vì sao cần một kiểu đầu vào có cấu trúc?

Giả sử người dùng muốn tìm sản phẩm theo nhiều điều kiện. Chữ ký với các tham số rời có thể trông như sau:

```java
@Tool(description = "Tìm sản phẩm theo nhiều điều kiện")
public List<ProductSummary> searchProducts(
        String keyword,
        ProductCategory category,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean inStockOnly) {
    // ...
}
```

Khi số điều kiện tăng, phương thức khó đọc, khó kiểm thử và khó thay đổi. Mô hình cũng phải điền nhiều trường cùng cấp mà không có một kiểu Java đại diện cho toàn bộ yêu cầu tìm kiếm.

Có thể gom chúng vào một record:

```java
public record ProductSearchRequest(
    String keyword,
    ProductCategory category,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Boolean inStockOnly
) {}
```

Phương thức công cụ chỉ nhận một đối tượng:

```java
@Tool(description = "Tìm sản phẩm theo từ khóa và bộ lọc")
public List<ProductSummary> searchProducts(ProductSearchRequest request) {
    return catalogService.search(request);
}
```

Lúc này, đối số của tool call là một JSON object có các property tương ứng với thành phần của record. Một kiểu đầu vào có cấu trúc giúp:

- Gom các trường cùng thuộc một yêu cầu nghiệp vụ.
- Tái sử dụng hợp đồng giữa công cụ, service và kiểm thử khi phù hợp.
- Mô tả rõ kiểu dữ liệu và quan hệ giữa các trường.
- Thêm bộ lọc tùy chọn mà không làm chữ ký phương thức phình to.
- Tạo một điểm tập trung để chuẩn hóa và kiểm tra đầu vào.

Không phải công cụ nào cũng cần DTO. Với thao tác chỉ nhận một mã định danh hoặc một từ khóa, tham số đơn giản vẫn dễ hiểu hơn. Dùng record/DTO khi nhiều trường tạo thành một yêu cầu có ý nghĩa và cần được quản lý như một đơn vị.

## 2. Record là lựa chọn gọn cho hợp đồng đầu vào

Java `record` phù hợp với dữ liệu đầu vào vì nó biểu diễn một nhóm giá trị, cung cấp constructor, accessor và các phương thức `equals`, `hashCode`, `toString`. Các thành phần record được khai báo ngay trên phần đầu kiểu dữ liệu nên người đọc dễ nhận ra cấu trúc.

Ví dụ đầy đủ hơn:

```java
import java.math.BigDecimal;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

public record ProductSearchRequest(
    @JsonPropertyDescription("Từ khóa hoặc tên sản phẩm cần tìm")
    String keyword,

    @JsonPropertyDescription("Nhóm sản phẩm cần lọc; có thể bỏ qua")
    ProductCategory category,

    @JsonPropertyDescription("Giá thấp nhất, không âm; có thể bỏ qua")
    BigDecimal minPrice,

    @JsonPropertyDescription("Giá cao nhất, không âm; có thể bỏ qua")
    BigDecimal maxPrice,

    @JsonPropertyDescription("Chỉ lấy sản phẩm còn hàng; bỏ qua nếu không lọc tồn kho")
    Boolean inStockOnly
) {
    public ProductSearchRequest {
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("keyword không được để trống");
        }

        keyword = keyword.strip();

        if (keyword.length() > 80) {
            throw new IllegalArgumentException("keyword không được dài quá 80 ký tự");
        }

        if (minPrice != null && minPrice.signum() < 0) {
            throw new IllegalArgumentException("minPrice không được âm");
        }

        if (maxPrice != null && maxPrice.signum() < 0) {
            throw new IllegalArgumentException("maxPrice không được âm");
        }

        if (minPrice != null && maxPrice != null
                && minPrice.compareTo(maxPrice) > 0) {
            throw new IllegalArgumentException("minPrice không được lớn hơn maxPrice");
        }
    }
}
```

`@JsonPropertyDescription` là metadata của Jackson để mô tả property. Spring AI xây dựng schema thông qua cơ chế sinh JSON Schema được cấu hình trong ứng dụng; việc một metadata annotation được phản ánh chính xác vào schema còn phụ thuộc generator và phiên bản đang dùng. Vì vậy, hãy kiểm tra schema thực tế mà ứng dụng gửi cho model thay vì chỉ dựa vào việc annotation đã xuất hiện trong mã nguồn.

Record có constructor gọn (compact constructor) để chuẩn hóa hoặc từ chối dữ liệu ngay khi tạo đối tượng. Điều này hữu ích với các bất biến luôn phải đúng, chẳng hạn từ khóa không rỗng hoặc giá trị nhỏ nhất không lớn hơn giá trị lớn nhất. Nếu cần nhiều bước kiểm tra hoặc tra cứu trạng thái nghiệp vụ, hãy giao phần đó cho validator hoặc service thay vì làm constructor phụ thuộc vào cơ sở dữ liệu.

## 3. Khai báo enum và kiểu dữ liệu cho property

Chọn kiểu Java phản ánh đúng ý nghĩa của từng property. Ví dụ, nhóm sản phẩm có tập giá trị hữu hạn nên được biểu diễn bằng enum:

```java
public enum ProductCategory {
    KEYBOARD,
    MOUSE,
    MONITOR,
    ACCESSORY
}
```

Enum giúp giới hạn tập giá trị mà mô hình có thể đề xuất. Tuy vậy, một giá trị enum hợp lệ về mặt cú pháp chưa chắc hợp lệ với thao tác cụ thể. Service vẫn phải kiểm tra quy tắc nghiệp vụ, chẳng hạn danh mục đó có được phép tìm trong tenant hiện tại hay không.

Với tiền tệ, ưu tiên `BigDecimal` thay cho `double` để tránh sai số nhị phân khi so sánh và tính toán. Với ngày giờ, dùng kiểu thời gian có ý nghĩa rõ ràng như `LocalDate` hoặc `OffsetDateTime`, đồng thời mô tả định dạng và múi giờ mà nghiệp vụ yêu cầu. Không dùng `String` cho mọi trường nếu đã có kiểu Java phù hợp.

| Dữ liệu | Kiểu thường phù hợp | Điều cần quy định |
|---|---|---|
| Từ khóa, mã định danh | `String` | Độ dài, định dạng, ký tự cho phép |
| Số lượng, số lần | `Integer` hoặc `Long` | Giới hạn nhỏ nhất/lớn nhất |
| Giá, số tiền | `BigDecimal` | Đơn vị tiền tệ, số chữ số thập phân, miền giá trị |
| Trạng thái hữu hạn | `enum` | Các giá trị được hỗ trợ và ý nghĩa |
| Ngày không có giờ | `LocalDate` | Định dạng ngày và giới hạn thời gian |
| Thời điểm có múi giờ | `OffsetDateTime` hoặc `Instant` | Quy tắc offset/múi giờ |
| Cờ tùy chọn | `Boolean` | Ý nghĩa khi true, false và khi bị bỏ qua |

## 4. Thiết kế trường bắt buộc và trường tùy chọn

Một schema tốt phải phân biệt được dữ liệu bắt buộc với bộ lọc tùy chọn. Trong `ProductSearchRequest`, `keyword` là cần thiết để thực hiện tìm kiếm; `category`, `minPrice`, `maxPrice` và `inStockOnly` có thể được bỏ qua.

JSON Schema minh họa cho hợp đồng đó có thể như sau:

```json
{
  "type": "object",
  "properties": {
    "keyword": {
      "type": "string",
      "description": "Từ khóa hoặc tên sản phẩm cần tìm"
    },
    "category": {
      "type": "string",
      "enum": ["KEYBOARD", "MOUSE", "MONITOR", "ACCESSORY"]
    },
    "minPrice": { "type": "number" },
    "maxPrice": { "type": "number" },
    "inStockOnly": { "type": "boolean" }
  },
  "required": ["keyword"],
  "additionalProperties": false
}
```

Đây là schema minh họa về ý nghĩa hợp đồng, không phải cam kết rằng mọi phiên bản Spring AI hoặc mọi provider sẽ sinh đúng từng khóa như trên. Cấu hình schema generator, annotation được hỗ trợ và chế độ tool calling của provider có thể làm schema thực tế khác đi. Hãy xem JSON Schema thực tế trong log/debug hoặc kiểm thử callback trước khi đưa lên môi trường chạy.

Một số lưu ý quan trọng:

- Trường bắt buộc phải có mặt trong schema và được kiểm tra lại khi thực thi.
- Trường tùy chọn nên có cách biểu diễn rõ khi bị bỏ qua.
- `Boolean` có thể phân biệt `true`, `false` và `null` (không được cung cấp). `boolean` chỉ có `true` hoặc `false`, nên không biểu đạt được trạng thái chưa chọn.
- `null`, thiếu property và giá trị mặc định không phải lúc nào cũng tương đương. Chọn một quy ước rõ ràng cho từng trường.
- Đừng đánh dấu tất cả property là bắt buộc chỉ vì record có constructor chứa tất cả thành phần.

Đối với provider hoặc chế độ schema yêu cầu tất cả trường phải có mặt, có thể cần điều chỉnh hợp đồng để mô hình gửi giá trị tường minh, chẳng hạn dùng enum có giá trị `ANY` thay cho một trường tùy chọn bị thiếu. Chỉ dùng cách này khi `ANY` có nghĩa nghiệp vụ rõ ràng và được kiểm tra ở phía ứng dụng.

## 5. Đưa record vào phương thức `@Tool`

Khai báo một tham số record trong phương thức công cụ. `@ToolParam` mô tả toàn bộ đối tượng đầu vào ở cấp tham số; mô tả từng property có thể được cung cấp bằng metadata mà schema generator hỗ trợ.

```java
import java.util.List;

import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

@Component
public class ProductCatalogTools {

    private final ProductCatalogService catalogService;

    public ProductCatalogTools(ProductCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Tool(
        name = "search_products",
        description = "Tìm sản phẩm theo từ khóa và các bộ lọc tùy chọn. "
            + "Chỉ đọc danh mục và trả về tối đa 5 kết quả."
    )
    public List<ProductSummary> searchProducts(
            @ToolParam(description = "Đối tượng điều kiện tìm kiếm sản phẩm")
            ProductSearchRequest request) {

        return catalogService.search(request, 5);
    }
}
```

Khi model gọi công cụ, phần arguments có dạng object tương tự:

```json
{
  "keyword": "bàn phím cơ không dây",
  "category": "KEYBOARD",
  "minPrice": 500000,
  "maxPrice": 2500000,
  "inStockOnly": true
}
```

Spring AI dùng bộ chuyển đổi đối số để chuyển JSON thành `ProductSearchRequest`, sau đó callback gọi phương thức. Nếu JSON sai cấu trúc hoặc không chuyển được sang kiểu Java, lỗi có thể xảy ra trước khi phần thân phương thức chạy. Vì vậy, cần kiểm thử cả bước chuyển đổi lẫn logic bên trong phương thức.

Không tự parse chuỗi JSON bằng thao tác cắt chuỗi hoặc regex trong phương thức công cụ. Hãy để cơ chế chuyển đổi JSON của framework tạo object theo kiểu đã khai báo; nếu cần kiểm soát mapping, cấu hình converter/mapper phù hợp và kiểm thử hợp đồng đó.

## 6. Khi nào dùng DTO class thay cho record?

Record phù hợp với hợp đồng dữ liệu bất biến và gọn. DTO class có thể phù hợp hơn khi cần tương thích với thư viện yêu cầu constructor rỗng và setter, cần kế thừa, hoặc cần cách xây dựng đối tượng linh hoạt.

Ví dụ DTO JavaBean:

```java
import java.math.BigDecimal;

public class ProductSearchDto {

    private String keyword;
    private ProductCategory category;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Boolean inStockOnly;

    public ProductSearchDto() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public ProductCategory getCategory() {
        return category;
    }

    public void setCategory(ProductCategory category) {
        this.category = category;
    }

    public BigDecimal getMinPrice() {
        return minPrice;
    }

    public void setMinPrice(BigDecimal minPrice) {
        this.minPrice = minPrice;
    }

    public BigDecimal getMaxPrice() {
        return maxPrice;
    }

    public void setMaxPrice(BigDecimal maxPrice) {
        this.maxPrice = maxPrice;
    }

    public Boolean getInStockOnly() {
        return inStockOnly;
    }

    public void setInStockOnly(Boolean inStockOnly) {
        this.inStockOnly = inStockOnly;
    }
}
```

Phương thức `@Tool` có thể nhận `ProductSearchDto` thay cho `ProductSearchRequest`. DTO class cần có các accessor và cơ chế khởi tạo mà JSON mapper đang cấu hình có thể sử dụng. Sau khi deserialize, ứng dụng vẫn phải gọi validator hoặc kiểm tra thủ công trước khi gửi xuống service.

| Tiêu chí | `record` | DTO class |
|---|---|---|
| Khai báo | Ngắn, property nằm trong header | Dài hơn, thường có field và accessor |
| Tính bất biến | Thành phần final, không có setter | Có thể bất biến hoặc mutable tùy thiết kế |
| Constructor | Canonical constructor rõ ràng | Có thể có constructor rỗng và nhiều constructor |
| Chuẩn hóa đầu vào | Compact constructor | Constructor, setter hoặc validator |
| Tương thích thư viện | Cần mapper hỗ trợ record | Thường phù hợp với JavaBean mapper |
| Phù hợp | Hợp đồng yêu cầu bất biến, gọn | Hợp đồng cần setter, kế thừa hoặc tương thích JavaBean |

Hãy dùng kiểu đơn giản nhất đáp ứng được JSON mapper và schema generator của ứng dụng. Đừng chọn DTO class chỉ vì thói quen nếu record đã được hỗ trợ tốt trong stack hiện tại.

## 7. Mô hình hóa object lồng nhau

Khi một nhóm property tạo thành một khái niệm riêng, có thể biểu diễn nó thành record lồng nhau. Ví dụ, khoảng giá có hai đầu mút và luôn cần được kiểm tra cùng nhau:

```java
import java.math.BigDecimal;

public record PriceRange(
    BigDecimal min,
    BigDecimal max
) {
    public PriceRange {
        if (min != null && min.signum() < 0) {
            throw new IllegalArgumentException("min không được âm");
        }
        if (max != null && max.signum() < 0) {
            throw new IllegalArgumentException("max không được âm");
        }
        if (min != null && max != null && min.compareTo(max) > 0) {
            throw new IllegalArgumentException("min không được lớn hơn max");
        }
    }
}

public record ProductSearchRequest(
    String keyword,
    ProductCategory category,
    PriceRange priceRange,
    Boolean inStockOnly
) {}
```

Object JSON tương ứng có thể như sau:

```json
{
  "keyword": "màn hình",
  "category": "MONITOR",
  "priceRange": {
    "min": 2000000,
    "max": 8000000
  },
  "inStockOnly": true
}
```

Object lồng nhau giúp nhóm trường có quy tắc chung, nhưng mỗi tầng làm schema phức tạp hơn. Chỉ tạo nested object khi nó có ý nghĩa nghiệp vụ hoặc được tái sử dụng. Nếu chỉ có hai trường đơn giản và provider/model xử lý object lồng nhau kém ổn định, có thể giữ các trường ở cấp cao nhất.

Không tạo cấu trúc lồng nhau quá sâu, mảng lồng nhiều cấp hoặc map có key tùy ý nếu tác vụ không thực sự cần. Các cấu trúc quá rộng khiến mô hình khó tạo JSON đúng và khiến ứng dụng khó giới hạn dữ liệu.

## 8. Kiểm tra schema được sinh ra

Kiểu Java là nguồn mô tả đầu vào, nhưng hợp đồng cuối cùng mà mô hình nhìn thấy là JSON Schema sau khi Spring AI và provider adapter xử lý. Cần xác minh schema thực tế thay vì giả định nó luôn giống hoàn toàn cấu trúc Java.

Khi kiểm tra schema, chú ý:

1. Tên công cụ và mô tả có chính xác không?
2. Root có phải object như mong đợi không?
3. Tên property có đúng với tên record component hoặc getter không?
4. Kiểu dữ liệu có đúng không: string, number, boolean, array, object hay enum?
5. Trường nào nằm trong `required`? Trường tùy chọn có thực sự được phép bỏ qua không?
6. Mô tả property có được giữ lại không?
7. Nested object và enum có được provider chấp nhận không?
8. Schema có chứa property nội bộ ngoài ý muốn không?

Schema có thể được log ở mức debug hoặc kiểm tra qua đối tượng định nghĩa công cụ trong unit test, tùy API và phiên bản Spring AI. Tránh bật log toàn bộ prompt/arguments ở môi trường production nếu nội dung có dữ liệu nhạy cảm.

Một bài kiểm thử hợp đồng có thể kiểm tra các thuộc tính quan trọng mà không khóa cứng mọi khoảng trắng hay thứ tự JSON:

```java
@Test
void productSearchSchemaExposesOnlyExpectedProperties() {
    ToolCallback callback = ToolCallbacks.from(new ProductCatalogTools(catalogService))[0];

    String schema = callback.getToolDefinition().inputSchema();

    assertThat(schema).contains("keyword");
    assertThat(schema).contains("category");
    assertThat(schema).contains("minPrice");
    assertThat(schema).contains("maxPrice");
    assertThat(schema).contains("inStockOnly");
    assertThat(schema).doesNotContain("tenantId");
}
```

Đây là ví dụ kiểm thử ý tưởng; chữ ký accessor và cách lấy `inputSchema()` cần khớp phiên bản Spring AI đang dùng. Nếu API trả về một kiểu khác, hãy điều chỉnh phần truy cập nhưng giữ nguyên mục tiêu kiểm tra schema được công bố.

## 9. Đối số của mô hình và dữ liệu tin cậy của ứng dụng

Không đưa mọi dữ liệu mà service cần vào record đầu vào. Có hai nhóm dữ liệu với nguồn tin cậy khác nhau:

| Nhóm | Ví dụ | Nguồn tạo |
|---|---|---|
| Đối số nghiệp vụ mô hình được phép đề xuất | Từ khóa, danh mục, khoảng giá, mã đơn hàng | Tool call do mô hình sinh |
| Ngữ cảnh tin cậy | Tenant ID, principal, quyền, correlation ID | Ứng dụng lấy từ phiên hoặc hệ thống xác thực |

Với công cụ tìm kiếm đa tenant, có thể nhận `ProductSearchRequest` từ mô hình và `ToolContext` từ ứng dụng:

```java
@Tool(
    name = "search_products",
    description = "Tìm sản phẩm trong danh mục của tenant hiện tại."
)
public List<ProductSummary> searchProducts(
        @ToolParam(description = "Điều kiện tìm kiếm sản phẩm")
        ProductSearchRequest request,
        ToolContext toolContext) {

    String tenantId = (String) toolContext.getContext().get("tenantId");
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalStateException("Thiếu tenant context");
    }

    return catalogService.search(tenantId, request, 5);
}
```

Ứng dụng lấy `tenantId` từ principal đã xác thực và truyền qua `.toolContext(...)`. Mô hình chỉ tạo `request`. Không thêm `tenantId`, role hoặc userId vào DTO để mô hình tự điền. Dù context đến từ ứng dụng, service vẫn phải kiểm tra quyền truy cập tài nguyên theo người dùng và tenant.

Không đưa access token, mật khẩu hoặc secret vào DTO hay context. Chỉ truyền dữ liệu tối thiểu cần thiết để thực thi thao tác.

## 10. Kiểm tra dữ liệu sau khi deserialize

JSON Schema giúp mô hình tạo đối số theo cấu trúc dự kiến, nhưng dữ liệu nhận được vẫn phải được coi là không đáng tin cậy. Có thể phát sinh các tình huống:

- Property bị thiếu hoặc có giá trị `null`.
- Chuỗi rỗng, quá dài hoặc sai định dạng.
- Số âm, số vượt giới hạn hoặc khoảng giá không hợp lệ.
- Enum hợp lệ về kiểu nhưng không được phép trong ngữ cảnh nghiệp vụ.
- Danh sách quá lớn hoặc object lồng nhau vượt giới hạn.
- Đối số tham chiếu tới dữ liệu mà người dùng không có quyền truy cập.

Có thể kiểm tra bất biến đơn giản trong compact constructor của record. Với DTO class, dùng validator tường minh hoặc Jakarta Bean Validation nếu ứng dụng đã cấu hình. Không giả định rằng chỉ thêm `@Valid`, `@NotNull` hoặc `@Size` vào DTO sẽ tự động làm cho mọi đường gọi tool kích hoạt validation; cần nối validator vào luồng thực thi và kiểm thử điều đó.

Một validator có thể kiểm tra các điều kiện phụ thuộc nhiều trường:

```java
public void validate(ProductSearchRequest request) {
    if (request == null) {
        throw new IllegalArgumentException("Thiếu điều kiện tìm kiếm");
    }

    if (request.minPrice() != null && request.maxPrice() != null
            && request.minPrice().compareTo(request.maxPrice()) > 0) {
        throw new IllegalArgumentException("Khoảng giá không hợp lệ");
    }
}
```

Các điều kiện phụ thuộc vào trạng thái dữ liệu, tenant hoặc quyền người dùng phải được kiểm tra trong service nghiệp vụ, nơi có đủ thông tin tin cậy.

## 11. Thiết kế schema ổn định khi hợp đồng thay đổi

DTO là hợp đồng giữa mô hình và ứng dụng. Khi thay đổi nó, cần nghĩ tới tương thích:

- Thêm một property tùy chọn thường ít ảnh hưởng hơn thêm một property bắt buộc.
- Đổi tên property có thể khiến model cũ hoặc lời gọi đang được lưu không còn khớp.
- Đổi kiểu `String` thành enum hoặc number có thể làm JSON cũ không deserialize được.
- Xóa giá trị enum có thể khiến yêu cầu được sinh từ lịch sử không còn hợp lệ.
- Thay đổi ý nghĩa của property mà không đổi tên vẫn có thể làm hành vi sai.

Khi cần thay đổi lớn, cân nhắc tạo công cụ phiên bản mới với tên hoặc hợp đồng mới trong giai đoạn chuyển tiếp. Giữ mô tả và schema đồng bộ với hành vi thật của service. Không duy trì một trường cũ nếu nó đã mất ý nghĩa nghiệp vụ chỉ để tránh chỉnh sửa.

## 12. Lỗi thường gặp khi dùng record hoặc DTO

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JSON không chuyển được thành record | Mapper hoặc phiên bản thư viện không hỗ trợ cấu trúc đang dùng | Kiểm tra cấu hình Jackson và kiểm thử deserialize bằng đúng mapper của ứng dụng |
| Schema không có property mong đợi | Generator không đọc được metadata hoặc getter/record component | Kiểm tra schema thực tế, cấu hình module/annotation được hỗ trợ |
| Trường tùy chọn luôn bị yêu cầu | Quy tắc required của generator hoặc provider | Xem `required` trong schema và điều chỉnh hợp đồng/schema configuration |
| Mô hình gửi `null` thay vì bỏ property | Provider/model biểu diễn trường tùy chọn theo cách đó | Xác định quy ước null/missing và xử lý tường minh |
| Enum không được chấp nhận | Giá trị sinh ra không nằm trong tập enum hoặc provider giới hạn schema | Mô tả giá trị hợp lệ, kiểm tra schema và từ chối giá trị không hợp lệ |
| Object lồng nhau khó sinh | Schema quá sâu hoặc cấu trúc phức tạp | Làm phẳng những trường không cần nhóm hoặc giảm độ sâu |
| DTO chứa trường nội bộ | Dùng nhầm entity hoặc DTO dùng chung quá rộng | Tạo input DTO chuyên biệt chỉ có property cần cho tool |
| Validation không chạy | DTO chỉ có annotation nhưng chưa nối validator vào callback | Gọi validator rõ ràng trong adapter/service và thêm kiểm thử |

## 13. Kiểm thử hợp đồng đầu vào

Nên kiểm tra ba lớp độc lập.

**Kiểm thử kiểu dữ liệu:** tạo record/DTO từ JSON mẫu, xác nhận property được map đúng, enum được chuyển đúng và giá trị thiếu/null có hành vi dự kiến.

**Kiểm thử validation:** thử từ khóa rỗng, chuỗi quá dài, giá âm, min lớn hơn max, enum không hợp lệ và nested object không hoàn chỉnh. Xác nhận service không được gọi khi đầu vào bị từ chối.

**Kiểm thử schema công cụ:** tạo `ToolCallback` từ phương thức `@Tool`, kiểm tra schema có đúng property, kiểu, mô tả, enum và required list. Xác nhận những trường tin cậy như tenantId không xuất hiện trong schema gửi mô hình.

**Kiểm thử tích hợp:** mô phỏng tool call với JSON hợp lệ và không hợp lệ; xác nhận callback deserialize đúng DTO, truyền context từ ứng dụng và trả kết quả hoặc lỗi phù hợp. Không cần gọi provider thật cho mọi ca kiểm thử; dùng phản hồi mô hình giả để kiểm soát chính xác tình huống.

## 14. Ghi nhớ

- Record hoặc DTO là hợp đồng đầu vào có cấu trúc cho tool call. Mô hình sinh object JSON; Spring AI chuyển object đó thành kiểu Java để phương thức thực thi.
- Dùng record cho hợp đồng gọn và bất biến; dùng DTO class khi cần setter, constructor hoặc tương thích JavaBean.
- Chọn kiểu property có ý nghĩa: enum cho tập giá trị hữu hạn, `BigDecimal` cho tiền, kiểu thời gian cho ngày giờ và wrapper cho trường có thể vắng mặt.
- Phân biệt property bắt buộc, tùy chọn, null và giá trị mặc định. Kiểm tra JSON Schema thực tế mà provider nhận được.
- Object lồng nhau hữu ích khi các trường thuộc cùng một khái niệm; giữ cấu trúc đủ nông để schema dễ sinh và dễ kiểm tra.
- Schema không thay thế validation, phân quyền hoặc quy tắc nghiệp vụ. Đối số từ mô hình luôn là dữ liệu không đáng tin cậy.
- Tenant, principal và quyền phải đến từ ứng dụng qua context tin cậy; không yêu cầu mô hình tự sinh chúng.

Khi thiết kế DTO cho công cụ, hãy bắt đầu từ thao tác nghiệp vụ và chỉ đưa vào những trường cần thiết để yêu cầu thao tác đó. Sau đó xác định kiểu, mô tả, required/optional, quy tắc validation và context tin cậy; cuối cùng kiểm tra schema được sinh ra cùng hành vi deserialize trước khi cho phép callback gọi service.
