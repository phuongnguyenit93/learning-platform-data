# Kiểu nguyên thủy, chuỗi, enum và trường có cấu trúc

Input schema là hợp đồng mô tả dữ liệu mà mô hình được phép gửi khi yêu cầu ứng dụng thực thi một tool. Trong Spring AI, schema này thường được suy ra từ chữ ký phương thức được đánh dấu bằng `@Tool` hoặc từ kiểu đầu vào của một `ToolCallback`.

Kiểu Java ảnh hưởng trực tiếp đến hình dạng JSON Schema: chuỗi trở thành `string`, số nguyên trở thành `integer`, số thực trở thành `number`, giá trị đúng/sai trở thành `boolean`, enum trở thành chuỗi có tập giá trị cho phép, còn record hoặc POJO trở thành đối tượng có các thuộc tính con.

Thiết kế schema tốt giúp mô hình tạo đối số rõ ràng và giúp ứng dụng kiểm tra dữ liệu dễ hơn. Tuy nhiên, schema chỉ mô tả hình dạng dữ liệu. Backend vẫn phải xác thực giá trị, kiểm tra quyền và áp dụng quy tắc nghiệp vụ trước khi thực thi.

## 1. Input schema được dùng ở đâu trong tool calling?

Khi ứng dụng cung cấp một tool cho mô hình, nó gửi kèm định nghĩa tool gồm tên, mô tả và input schema. Mô hình đọc định nghĩa đó để quyết định có gọi tool hay không và cần tạo những đối số nào.

Ví dụ, tool `lookupInventory` cần biết SKU và kho:

~~~java
@Component
class InventoryTools {

    private final InventoryService inventoryService;

    InventoryTools(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Tool(
        name = "lookupInventory",
        description = "Tra cứu số lượng tồn kho của một SKU tại một kho."
    )
    public StockView lookupInventory(
            @ToolParam(description = "Mã SKU cần tra cứu") String sku,
            @ToolParam(description = "Kho cần tra cứu") String warehouse) {
        return inventoryService.lookup(sku, warehouse);
    }
}
~~~

Từ chữ ký phương thức, Spring AI có thể tạo schema đầu vào để mô hình biết rằng:

- `sku` là một chuỗi.
- `warehouse` là một chuỗi.
- Cả hai trường đều là đối số của tool.

Khi mô hình muốn tra cứu, nó có thể tạo lời gọi có dạng khái niệm:

~~~json
{
  "sku": "A-100",
  "warehouse": "HANOI"
}
~~~

Ứng dụng nhận tool call, phân giải callback tương ứng, chuyển đối số thành kiểu Java và thực thi phương thức. Tool result sau đó được đưa trở lại cuộc hội thoại để mô hình tiếp tục trả lời.

Cần phân biệt ba việc:

1. **Mô tả schema:** cho mô hình biết dữ liệu cần cung cấp và định dạng mong đợi.
2. **Chuyển đổi dữ liệu:** ánh xạ JSON arguments sang kiểu Java mà phương thức nhận.
3. **Xác thực và thực thi:** ứng dụng kiểm tra dữ liệu, quyền và trạng thái nghiệp vụ rồi mới gọi service.

Schema hỗ trợ bước đầu và một phần bước chuyển đổi. Nó không thay thế xác thực ở bước thứ ba.

## 2. Ánh xạ kiểu Java sang JSON Schema

Các kiểu dữ liệu phổ biến được biểu diễn trong JSON Schema như sau:

| Kiểu Java | Kiểu JSON Schema thường dùng | Ví dụ JSON |
|---|---|---|
| `String`, `char`, `Character` | `string` | `"A-100"` |
| `int`, `Integer`, `long`, `Long` | `integer` | `20` |
| `float`, `Float`, `double`, `Double`, `BigDecimal` | `number` | `12.5` |
| `boolean`, `Boolean` | `boolean` | `true` |
| `enum` | `string` kèm danh sách `enum` | `"HANOI"` |
| `record` hoặc POJO | `object` với các thuộc tính | `{"sku":"A-100"}` |
| `List<T>` hoặc mảng | `array` với schema của phần tử | `["A-100","B-200"]` |

Đây là cách ánh xạ khái niệm. Schema thực tế có thể có thêm mô tả, ràng buộc, trường bắt buộc và cấu trúc phụ thuộc vào phiên bản Spring AI, Jackson và provider.

### 2.1. Kiểu số nguyên

Dùng `int` hoặc `Integer` cho số lượng, số lần, số trang hay các giá trị đếm. Dùng `long` hoặc `Long` khi phạm vi giá trị có thể vượt giới hạn của `int`.

Ví dụ:

~~~java
@Tool(
    name = "findLowStock",
    description = "Tìm sản phẩm có số lượng tồn kho thấp hơn ngưỡng."
)
public List<StockView> findLowStock(
        @ToolParam(description = "Ngưỡng số lượng tồn kho, là số nguyên không âm")
        int threshold) {

    if (threshold < 0) {
        throw new IllegalArgumentException("Ngưỡng phải không âm");
    }

    return inventoryService.findBelow(threshold);
}
~~~

Schema đầu vào có thuộc tính `threshold` kiểu `integer`. Mô hình nên gửi số JSON như `5` thay vì chuỗi `"5"`.

Các lưu ý:

- Số lượng sản phẩm thường là số nguyên, không dùng `double` nếu không có phần thập phân.
- Kiểm tra giá trị âm, giá trị vượt giới hạn và quy tắc nghiệp vụ tại backend.
- Nếu dữ liệu có thể lớn hơn phạm vi kiểu Java, cần chọn kiểu phù hợp và xác thực trước khi chuyển đổi.
- Không dựa vào mô tả schema để bảo đảm mô hình không gửi số ngoài phạm vi.

### 2.2. Kiểu số thực

Dùng `BigDecimal` cho giá tiền hoặc đại lượng cần giữ độ chính xác thập phân. `float` và `double` phù hợp với một số phép đo, thống kê hoặc tính toán khoa học, nhưng biểu diễn nhị phân có thể gây sai số làm tròn.

Ví dụ:

~~~java
@Tool(
    name = "findProductsByPrice",
    description = "Tìm sản phẩm theo khoảng giá."
)
public List<ProductView> findProductsByPrice(
        @ToolParam(description = "Giá thấp nhất, tính theo VND")
        BigDecimal minimumPrice,
        @ToolParam(description = "Giá cao nhất, tính theo VND")
        BigDecimal maximumPrice) {

    if (minimumPrice.signum() < 0
            || maximumPrice.compareTo(minimumPrice) < 0) {
        throw new IllegalArgumentException("Khoảng giá không hợp lệ");
    }

    return productService.findByPriceRange(minimumPrice, maximumPrice);
}
~~~

Schema biểu diễn hai đối số là `number`. Ứng dụng cần thống nhất đơn vị tiền tệ và quy tắc làm tròn. Đừng để mô hình tự đoán đơn vị khi có thể mô tả rõ trong `description` hoặc dùng trường riêng cho currency.

### 2.3. Kiểu boolean

Dùng `boolean` hoặc `Boolean` cho lựa chọn hai trạng thái, ví dụ có bao gồm sản phẩm hết hàng hay không.

~~~java
@Tool(
    name = "searchInventory",
    description = "Tìm tồn kho theo SKU và tùy chọn bao gồm hàng đã hết."
)
public List<StockView> searchInventory(
        @ToolParam(description = "Mã SKU cần tìm") String sku,
        @ToolParam(description = "Có bao gồm sản phẩm hết hàng hay không")
        boolean includeZeroStock) {

    return inventoryService.search(sku, includeZeroStock);
}
~~~

Đối số JSON phải là `true` hoặc `false`, không phải chuỗi `"true"` hoặc `"false"`.

Không dùng boolean khi nghiệp vụ có hơn hai trạng thái. Ví dụ, trạng thái đơn hàng nên là enum như `PENDING`, `CONFIRMED`, `CANCELLED`. Hai boolean như `isApproved` và `isRejected` còn có thể tạo ra trạng thái mâu thuẫn khi cùng đúng.

## 3. Chuỗi và quy tắc nhập liệu

`String` là kiểu phổ biến nhất trong input schema: SKU, mã khách hàng, mã đơn, từ khóa tìm kiếm, tên kho hoặc nội dung ghi chú.

Ví dụ:

~~~java
@Tool(
    name = "findCustomer",
    description = "Tra cứu khách hàng theo mã khách hàng."
)
public CustomerView findCustomer(
        @ToolParam(description = "Mã khách hàng, ví dụ CUS-10025")
        String customerCode) {

    if (customerCode == null || customerCode.isBlank()) {
        throw new IllegalArgumentException("Mã khách hàng không được để trống");
    }

    return customerService.findByCode(customerCode.trim());
}
~~~

Schema có thể chỉ biểu diễn `customerCode` là `string`. Những quy tắc như không rỗng, độ dài tối đa, định dạng mã hoặc tập ký tự hợp lệ cần được mô tả và xác thực.

Một số nguyên tắc khi thiết kế trường chuỗi:

- Đặt tên theo ý nghĩa nghiệp vụ, chẳng hạn `customerCode` thay vì `value`.
- Mô tả định dạng bằng ví dụ cụ thể như `CUS-10025` hoặc `SKU-AB12`.
- Phân biệt mã định danh với tên hiển thị. Mã thường ổn định và phù hợp để tra cứu hơn.
- Giới hạn độ dài và loại bỏ ký tự không hợp lệ ở backend.
- Chuẩn hóa khoảng trắng hoặc chữ hoa/thường theo quy tắc của hệ thống.
- Không dùng một chuỗi tự do để nhận dữ liệu có cấu trúc như nhiều mã, nhiều trạng thái hoặc nhiều thuộc tính.

Nếu tool nhận nội dung văn bản tự do, hãy xem đó là dữ liệu không đáng tin cậy. Không thực thi SQL, shell command, biểu thức hoặc URL chỉ vì chúng xuất hiện trong một chuỗi mà mô hình gửi đến.

## 4. Enum: giới hạn giá trị bằng tập lựa chọn

Enum phù hợp khi một trường chỉ nhận một số giá trị hữu hạn đã được xác định trong mã nguồn. Ví dụ, kho hàng có thể được biểu diễn bằng enum:

~~~java
public enum WarehouseCode {
    HANOI,
    HO_CHI_MINH,
    DA_NANG
}
~~~

Dùng enum trong chữ ký tool:

~~~java
@Tool(
    name = "lookupInventory",
    description = "Tra cứu tồn kho theo SKU và mã kho."
)
public StockView lookupInventory(
        @ToolParam(description = "Mã SKU cần tra cứu") String sku,
        @ToolParam(description = "Mã kho: HANOI, HO_CHI_MINH hoặc DA_NANG")
        WarehouseCode warehouse) {

    return inventoryService.lookup(sku, warehouse);
}
~~~

Schema tương ứng có dạng khái niệm:

~~~json
{
  "type": "string",
  "enum": [
    "HANOI",
    "HO_CHI_MINH",
    "DA_NANG"
  ],
  "description": "Mã kho cần tra cứu"
}
~~~

Nhờ danh sách giá trị cho phép, mô hình có thể chọn một giá trị enum thay vì tự tạo tên kho bất kỳ. Khi chuyển thành Java, giá trị phải khớp với quy tắc chuyển đổi enum mà ứng dụng đang dùng.

### 4.1. Chọn giá trị enum ổn định

Giá trị enum là một phần của hợp đồng giữa ứng dụng và mô hình. Vì vậy:

- Dùng mã ngắn, ổn định, không phụ thuộc ngôn ngữ hiển thị.
- Không đổi tên hằng enum tùy tiện sau khi đã công bố schema.
- Mô tả rõ ý nghĩa của từng lựa chọn trong tool description hoặc mô tả trường.
- Xử lý trường hợp mô hình gửi giá trị ngoài danh sách hoặc sai chữ hoa/thường.
- Nếu giá trị hiển thị cho người dùng khác với mã nội bộ, ánh xạ chúng ở lớp ứng dụng.

Ví dụ, giao diện có thể hiển thị “Hồ Chí Minh”, nhưng mã dùng trong API là `HO_CHI_MINH`. Tránh sử dụng nhãn giao diện có dấu làm giá trị enum nếu hệ thống đã có mã ổn định.

### 4.2. Khi nào không nên dùng enum?

Không dùng enum cho dữ liệu có thể thay đổi thường xuyên hoặc có số lượng lớn, ví dụ danh sách khách hàng, mã sản phẩm, mã kho do người quản trị thêm mới. Những giá trị đó nên được kiểm tra bằng service hoặc repository.

Nếu enum thay đổi theo tenant hoặc theo quyền của người dùng, schema tĩnh có thể không phản ánh đúng lựa chọn hiện tại. Có thể lọc danh sách tool hoặc xây dựng schema theo ngữ cảnh được phép, nhưng backend vẫn phải xác minh quyền khi thực thi.

## 5. Trường có cấu trúc: object và record lồng nhau

Khi một tool cần nhiều thuộc tính có quan hệ với nhau, hãy nhóm chúng thành một kiểu dữ liệu có cấu trúc thay vì tạo một danh sách tham số dài.

Ví dụ, bộ lọc tồn kho có thể gồm khoảng số lượng và lựa chọn bao gồm hàng hết:

~~~java
public record QuantityRange(
    Integer minimum,
    Integer maximum
) {}

public record InventoryFilter(
    QuantityRange quantity,
    Boolean includeZeroStock
) {}
~~~

Sau đó khai báo tool nhận bộ lọc:

~~~java
@Tool(
    name = "searchInventory",
    description = "Tìm sản phẩm theo SKU, kho và bộ lọc tồn kho."
)
public List<StockView> searchInventory(
        @ToolParam(description = "Mã SKU hoặc tiền tố SKU")
        String sku,
        @ToolParam(description = "Mã kho cần tìm")
        WarehouseCode warehouse,
        @ToolParam(
            description = "Điều kiện lọc tồn kho, có thể bỏ qua",
            required = false
        )
        InventoryFilter filter,
        ToolContext toolContext) {

    String tenantId = (String) toolContext.getContext().get("tenantId");
    if (tenantId == null || tenantId.isBlank()) {
        throw new AccessDeniedException("Thiếu tenant đã xác thực");
    }

    validateFilter(filter);
    return inventoryService.search(tenantId, sku, warehouse, filter);
}

void validateFilter(InventoryFilter filter) {
    if (filter == null || filter.quantity() == null) {
        return;
    }

    Integer min = filter.quantity().minimum();
    Integer max = filter.quantity().maximum();

    if (min != null && min < 0) {
        throw new IllegalArgumentException("Số lượng tối thiểu phải không âm");
    }
    if (max != null && max < 0) {
        throw new IllegalArgumentException("Số lượng tối đa phải không âm");
    }
    if (min != null && max != null && min > max) {
        throw new IllegalArgumentException("Khoảng số lượng không hợp lệ");
    }
}
~~~

Trong ví dụ:

- `sku` là chuỗi.
- `warehouse` là enum.
- `filter` là object.
- `filter.quantity` là object con.
- `minimum` và `maximum` là số nguyên.
- `includeZeroStock` là boolean.
- `ToolContext` mang tenant ID do máy chủ cung cấp và không phải trường mà mô hình tự điền.

Một schema khái niệm cho tool này:

~~~json
{
  "type": "object",
  "properties": {
    "sku": {
      "type": "string",
      "description": "Mã SKU hoặc tiền tố SKU"
    },
    "warehouse": {
      "type": "string",
      "enum": ["HANOI", "HO_CHI_MINH", "DA_NANG"]
    },
    "filter": {
      "type": "object",
      "properties": {
        "quantity": {
          "type": "object",
          "properties": {
            "minimum": { "type": "integer" },
            "maximum": { "type": "integer" }
          }
        },
        "includeZeroStock": {
          "type": "boolean"
        }
      }
    }
  },
  "required": ["sku", "warehouse"]
}
~~~

Đây là minh họa hình dạng schema. Danh sách trường bắt buộc, cách biểu diễn kiểu nullable và mô tả của thuộc tính lồng nhau phụ thuộc bộ sinh schema và phiên bản framework. Hãy kiểm tra tool definition thực tế mà ứng dụng gửi đến provider thay vì giả định schema được sinh đúng như ví dụ.

### 5.1. Object phù hợp hơn một chuỗi JSON tự do

Không nên nhận một chuỗi như `"{\"minimum\":5,\"maximum\":20}"` rồi tự parse trong tool nếu có thể khai báo trực tiếp một record `QuantityRange`. Kiểu có cấu trúc giúp:

- Mô hình biết rõ tên và kiểu của từng trường.
- Ứng dụng nhận được đối tượng Java có cấu trúc.
- Có thể xác thực từng trường và mối quan hệ giữa các trường.
- Unit test dễ kiểm tra các trường hợp hợp lệ và không hợp lệ.
- Giảm lỗi do JSON lồng nhau sai cú pháp hoặc sai tên thuộc tính.

Dùng chuỗi JSON tự do chỉ khi tool thực sự cần nhận một tài liệu JSON động, không có cấu trúc cố định và ứng dụng có parser cùng quy tắc kiểm tra riêng.

### 5.2. Danh sách và mảng

Nếu một trường nhận nhiều giá trị cùng kiểu, dùng `List<T>` hoặc mảng. Ví dụ, tool có thể nhận danh sách SKU:

~~~java
@Tool(
    name = "lookupManyInventory",
    description = "Tra cứu tồn kho cho một danh sách mã SKU."
)
public List<StockView> lookupManyInventory(
        @ToolParam(description = "Danh sách mã SKU cần tra cứu")
        List<String> skus) {

    if (skus == null || skus.isEmpty() || skus.size() > 50) {
        throw new IllegalArgumentException("Danh sách SKU phải có từ 1 đến 50 phần tử");
    }

    return inventoryService.lookupMany(skus);
}
~~~

Schema của `skus` có kiểu `array` và phần tử có kiểu `string`. Ứng dụng cần giới hạn số phần tử, kiểm tra từng mã, loại bỏ phần tử trùng nếu nghiệp vụ yêu cầu và kiểm soát kích thước kết quả trả về.

Nếu phần tử là record, schema của mảng sẽ chứa schema object cho từng phần tử. Chỉ dùng cấu trúc lồng sâu khi nghiệp vụ thực sự cần; schema quá phức tạp khiến mô hình khó tạo đối số và khó bảo trì.

## 6. Required, optional và nullable

Ba khái niệm này liên quan nhưng không đồng nghĩa:

- **Required:** thuộc tính phải xuất hiện trong JSON.
- **Optional:** thuộc tính có thể bị bỏ khỏi JSON.
- **Nullable:** thuộc tính xuất hiện nhưng giá trị có thể là `null` nếu schema cho phép.

Ví dụ, hai JSON sau khác nhau:

~~~json
{
  "sku": "A-100",
  "warehouse": "HANOI"
}
~~~

~~~json
{
  "sku": "A-100",
  "warehouse": "HANOI",
  "filter": null
}
~~~

Trong JSON thứ nhất, trường `filter` bị bỏ qua. Trong JSON thứ hai, trường `filter` có mặt và giá trị là `null`. Không nên mặc định rằng `required = false` đồng nghĩa schema chấp nhận `null`.

### 6.1. Dùng @ToolParam để mô tả tham số tùy chọn

Với tham số phương thức, có thể khai báo rõ một tham số không bắt buộc:

~~~java
@Tool(
    name = "searchProducts",
    description = "Tìm sản phẩm theo từ khóa và tùy chọn giới hạn kết quả."
)
public List<ProductView> searchProducts(
        @ToolParam(description = "Từ khóa tìm kiếm")
        String keyword,
        @ToolParam(
            description = "Số kết quả tối đa, mặc định do ứng dụng quyết định",
            required = false
        )
        Integer limit) {

    int safeLimit = limit == null ? 10 : Math.min(Math.max(limit, 1), 50);
    return productService.search(keyword, safeLimit);
}
~~~

Trong ví dụ, `limit` có thể không xuất hiện trong đối số. Ứng dụng chọn giá trị mặc định và giới hạn khoảng hợp lệ. Không phụ thuộc vào mô hình để áp dụng giới hạn tối đa.

Với tham số bắt buộc, giữ `required = true` hoặc dùng giá trị mặc định của annotation theo phiên bản đang dùng. Với tham số tùy chọn, kiểm tra cả trường hợp bị bỏ qua lẫn trường hợp nhận `null` nếu provider/schema cho phép.

### 6.2. Primitive và wrapper

Kiểu nguyên thủy Java như `int` và `boolean` không thể nhận `null`. Kiểu wrapper như `Integer` và `Boolean` có thể biểu diễn giá trị thiếu sau khi chuyển đổi.

Tuy nhiên, việc dùng wrapper không tự động làm trường thành optional. Thuộc tính có bắt buộc hay không còn phụ thuộc schema và cấu hình `@ToolParam`. Vì vậy:

- Dùng primitive khi giá trị bắt buộc và luôn có giá trị hợp lệ.
- Dùng wrapper khi cần biểu diễn trạng thái chưa có dữ liệu.
- Khai báo tính required/optional rõ ràng.
- Kiểm tra giá trị `null` tại backend trước khi dùng.
- Không suy luận rằng schema hỗ trợ nullable chỉ vì Java field dùng wrapper.

## 7. Mô tả trường để mô hình chọn đúng giá trị

Tên và kiểu dữ liệu cho biết hình dạng, nhưng mô tả giúp mô hình hiểu ý nghĩa nghiệp vụ. Mỗi tham số nên có mô tả ngắn, cụ thể.

Ví dụ, hai trường sau đều là chuỗi nhưng ý nghĩa rất khác:

- `customerCode`: mã định danh khách hàng, ví dụ `CUS-10025`.
- `customerName`: tên hiển thị của khách hàng, có thể không duy nhất.

Mô tả tốt nên trả lời:

1. Trường này đại diện cho dữ liệu gì?
2. Định dạng hoặc đơn vị nào được chấp nhận?
3. Có ví dụ giá trị hợp lệ không?
4. Có điều kiện nghiệp vụ nào quan trọng không?

Tránh mô tả chung chung như “giá trị cần tìm”, “thông tin đầu vào” hoặc “tham số”. Mô tả cũng không nên chứa bí mật, dữ liệu cá nhân thật hoặc hướng dẫn nội bộ không cần thiết cho việc chọn tool.

Đối với enum, mô tả các lựa chọn bằng ngôn ngữ dễ hiểu. Đối với số, nêu đơn vị và giới hạn. Đối với object, giải thích mục đích của nhóm thuộc tính và quan hệ giữa chúng.

## 8. Xác thực dữ liệu sau khi nhận tool arguments

Ngay cả khi đối số được parse thành Java object và đúng kiểu schema, dữ liệu vẫn có thể sai hoặc không được phép sử dụng.

Ví dụ, `minimum = 10` và `maximum = 5` đều là số nguyên hợp lệ, nhưng khoảng tìm kiếm không hợp lệ. Mã kho `HANOI` có thể là enum hợp lệ nhưng người dùng hiện tại không có quyền xem kho đó.

Ứng dụng cần kiểm tra theo nhiều lớp:

| Lớp | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| Kiểu và cấu trúc | Có parse được và đúng kiểu không? | `limit` phải là số nguyên |
| Giá trị | Có nằm trong phạm vi cho phép không? | `limit` từ 1 đến 50 |
| Quan hệ trường | Các trường có nhất quán không? | `minimum <= maximum` |
| Tồn tại | Tài nguyên có thực sự tồn tại không? | SKU có trong catalog |
| Phân quyền | Người dùng có quyền thao tác không? | Tenant có quyền xem kho |
| Trạng thái nghiệp vụ | Trạng thái hiện tại có cho phép không? | Đơn chưa bị hủy |

Có thể dùng Bean Validation như `@NotBlank`, `@Min`, `@Max` và validator tùy chỉnh trong lớp nghiệp vụ. Không giả định mọi annotation validation đều tự động chuyển thành ràng buộc JSON Schema; hãy kiểm tra schema được sinh ra. Dù schema có thể biểu diễn một giới hạn, backend vẫn cần thực hiện validation trước khi gọi service hoặc ghi dữ liệu.

Các giá trị tin cậy như tenant ID, user ID và vai trò nên lấy từ security context hoặc `ToolContext` do máy chủ tạo. Không khai báo chúng thành trường đầu vào để mô hình tự cung cấp.

## 9. Kiểm tra schema thực tế và kiểm thử

Schema được sinh tự động có thể thay đổi theo phiên bản Spring AI, Jackson, kiểu dữ liệu và provider. Nên kiểm tra định nghĩa thực tế thay vì chỉ kiểm tra chữ ký Java.

Một bộ kiểm thử hữu ích gồm:

| Trường hợp | Điều cần xác minh |
|---|---|
| String hợp lệ | Chuỗi được parse đúng, giữ đúng mã |
| String rỗng hoặc quá dài | Backend từ chối theo quy tắc |
| Integer hợp lệ | Giá trị được ánh xạ thành kiểu số nguyên |
| Number ngoài phạm vi | Validation từ chối trước khi truy cập dữ liệu |
| Boolean | Chỉ nhận giá trị boolean hợp lệ |
| Enum hợp lệ | Giá trị ánh xạ đúng hằng enum |
| Enum ngoài danh sách | Không gọi service |
| Object lồng nhau | Các thuộc tính con được chuyển đổi chính xác |
| Optional bị bỏ qua | Ứng dụng dùng giá trị mặc định đúng |
| Null | Được xử lý theo hợp đồng nullable đã định |
| Mảng rỗng/quá lớn | Kiểm tra số phần tử và giới hạn request |
| Sai quyền | Callback từ chối trước khi truy cập tài nguyên |

Ví dụ kiểm tra validation của một bộ lọc:

~~~java
@Test
void rejectsInvalidQuantityRange() {
    InventoryFilter filter = new InventoryFilter(
        new QuantityRange(20, 5),
        false
    );

    assertThrows(
        IllegalArgumentException.class,
        () -> inventoryTools.validateFilter(filter)
    );
}
~~~

Ngoài unit test cho validation, nên có integration test dùng model giả lập hoặc tool call có đối số xác định để xác minh:

1. Tool definition được gửi cùng prompt.
2. Input schema có tên trường, kiểu và mô tả như mong đợi.
3. Tool arguments được chuyển thành kiểu Java đúng.
4. `ToolContext` không xuất hiện trong schema đầu vào của mô hình.
5. Callback chỉ gọi service sau khi validation và phân quyền thành công.
6. Tool result được trả về cuộc hội thoại với dữ liệu cần thiết.

Nếu cần log schema để chẩn đoán, chỉ log định nghĩa không chứa dữ liệu nhạy cảm và không log API key hay tool arguments của người dùng trong production.

## 10. Nguyên tắc thiết kế schema dễ dùng và an toàn

- Dùng kiểu nguyên thủy và wrapper đúng với ý nghĩa dữ liệu.
- Dùng `String` cho mã hoặc văn bản; mô tả định dạng rõ ràng.
- Dùng enum cho tập lựa chọn nhỏ, ổn định và có giới hạn.
- Dùng record/POJO cho nhóm thuộc tính có quan hệ; tránh chuỗi JSON tự do khi cấu trúc đã biết.
- Dùng List hoặc mảng khi cần nhiều phần tử cùng kiểu và giới hạn kích thước.
- Đặt tên trường theo ngôn ngữ nghiệp vụ, tránh tên mơ hồ.
- Khai báo required/optional có chủ đích; phân biệt trường bị bỏ qua và `null`.
- Không đưa thông tin xác thực hoặc quyền hạn vào schema.
- Xác thực kiểu, giá trị, quan hệ trường, tồn tại và quyền ở backend.
- Kiểm tra schema thực tế được sinh ra sau khi nâng cấp Spring AI hoặc Jackson.
- Giữ input schema nhỏ và rõ để mô hình có thể tạo arguments chính xác.

## Tài liệu tham khảo

- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): khai báo `@Tool`, `@ToolParam`, input schema, `ToolCallback` và cách thực thi tool.
- [Spring AI — Tool Context](https://docs.spring.io/spring-ai/reference/api/tools.html#_tool_context): truyền dữ liệu ngữ cảnh server-side cho tool mà không yêu cầu mô hình cung cấp.
- [JSON Schema — Types](https://json-schema.org/understanding-json-schema/reference/type): các kiểu string, number, integer, boolean, object và array.
- [JSON Schema — Enumerated values](https://json-schema.org/understanding-json-schema/reference/enum): giới hạn giá trị của một thuộc tính bằng enum.

Schema là hợp đồng đầu vào giữa mô hình và ứng dụng. Hãy thiết kế nó rõ ràng để mô hình dễ tạo yêu cầu, đồng thời giữ việc xác thực và quyết định thực thi ở phía máy chủ.

