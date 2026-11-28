# Danh sách, đối tượng lồng nhau và kiểu generic theo khả năng hỗ trợ

Đầu vào của một công cụ không phải lúc nào cũng là vài chuỗi hoặc con số độc lập. Một yêu cầu nghiệp vụ có thể chứa danh sách trạng thái, khoảng thời gian, bộ lọc lồng nhau hoặc một tập thuộc tính có cấu trúc. Trong Java, những dữ liệu đó thường được biểu diễn bằng `List<T>`, `Set<T>`, `Map<K,V>`, mảng, record và DTO.

Khi Spring AI cung cấp công cụ cho mô hình, các kiểu Java này cần được biểu diễn thành schema có cấu trúc để mô hình biết trường nào là mảng, phần tử mảng có kiểu gì, đối tượng lồng nhau có những thuộc tính nào và kiểu generic cụ thể ra sao. Khả năng sinh schema phụ thuộc kiểu khai báo, cơ chế chuyển đổi và phiên bản Spring AI cùng model provider. Vì vậy, hãy thiết kế kiểu dữ liệu rõ ràng và kiểm tra schema thực tế được gửi đi.

Bài này tập trung vào danh sách, đối tượng lồng nhau và kiểu generic; cách chọn cấu trúc Java để schema dễ hiểu; những giới hạn do type erasure và kiểu động; cùng cách xác thực dữ liệu ở thời điểm thực thi.

## Từ kiểu Java đến cấu trúc JSON Schema

Mô hình không nhận trực tiếp một đối tượng Java. Ứng dụng gửi định nghĩa công cụ với schema đầu vào, thường dựa trên JSON Schema. Một số ánh xạ thường gặp:

| Kiểu Java thường dùng | Hình dạng JSON tương ứng | Schema thường cần mô tả |
|---|---|---|
| `String` | Chuỗi | `type: string` |
| `Integer`, `Long`, `BigDecimal` | Số | `type: integer` hoặc `type: number` tùy kiểu và generator |
| `Boolean` | Đúng/sai | `type: boolean` |
| `List<T>`, `Collection<T>`, mảng | Mảng | `type: array` và `items` mô tả kiểu của từng phần tử |
| `Set<T>` | Mảng có ngữ nghĩa tập hợp ở phía Java | `type: array`; ràng buộc duy nhất có thể cần biểu diễn hoặc kiểm tra riêng |
| `Map<String, T>` | Đối tượng có các khóa động | `type: object` và quy tắc cho `additionalProperties` |
| DTO hoặc record | Đối tượng | `type: object`, `properties`, `required` và có thể có `additionalProperties` |
| DTO chứa DTO hoặc collection | Đối tượng lồng nhau, mảng lồng nhau | Schema con được lồng theo cấu trúc thuộc tính hoặc `items` |

Bảng trên mô tả hình dạng dữ liệu ở mức khái niệm. Tên trường, `required`, `nullable`, `additionalProperties`, định dạng và các ràng buộc cụ thể do schema generator cùng cấu hình quyết định. Đừng suy ra rằng mọi annotation validation trên Java đều tự động trở thành ràng buộc trong schema.

Ví dụ, nếu một công cụ nhận danh sách mã trạng thái, mô hình cần hiểu `statuses` là một mảng chuỗi chứ không phải một chuỗi duy nhất chứa dấu phẩy. Nếu mỗi phần tử là một bộ lọc có `name` và `values`, schema phải mô tả phần tử mảng là một object có hai thuộc tính đó.

## Khai báo danh sách và mảng

### Danh sách các giá trị đơn giản

Với danh sách chuỗi, hãy khai báo kiểu phần tử rõ ràng:

```java
@Tool(
    name = "findOrdersByStatus",
    description = "Tìm các đơn hàng theo một hoặc nhiều trạng thái nghiệp vụ. "
            + "Dùng khi người dùng muốn lọc danh sách đơn; không thay đổi trạng thái đơn."
)
public List<OrderSummary> findOrdersByStatus(
        @ToolParam(description = "Danh sách trạng thái cần tìm, ví dụ CONFIRMED hoặc SHIPPED")
        List<OrderStatus> statuses) {

    if (statuses == null || statuses.isEmpty()) {
        throw new IllegalArgumentException("Cần ít nhất một trạng thái");
    }
    return orderQueryService.findByStatuses(statuses);
}
```

`List<OrderStatus>` thể hiện rõ hơn `List<String>` khi tập trạng thái là hữu hạn và có enum tương ứng. Nếu dùng enum, hãy kiểm tra schema được tạo có liệt kê đúng các giá trị mà provider chấp nhận hay không. Tên enum Java và cách serialize có thể ảnh hưởng đến giá trị JSON.

Nếu dùng `List<String>`, mô tả tham số nên nói rõ định dạng và tập giá trị hợp lệ. Ứng dụng vẫn cần kiểm tra từng phần tử; schema kiểu string không tự giới hạn chuỗi vào những giá trị nghiệp vụ hợp lệ.

### Mảng và collection

Mảng Java như `String[]` cũng có hình dạng JSON là array. `List<T>` thường tiện hơn cho xử lý nghiệp vụ vì có API collection phong phú và biểu diễn được kiểu phần tử bằng generic. `Collection<T>` có thể phù hợp nếu phương thức không cần hành vi riêng của List.

`Set<T>` thể hiện ý nghĩa không trùng lặp ở phía Java. Tuy nhiên, không nên mặc định schema sinh ra luôn có `uniqueItems: true`, hoặc mô hình sẽ không tạo phần tử trùng. Hãy loại bỏ hoặc từ chối giá trị trùng trong ứng dụng nếu tính duy nhất quan trọng.

Với mọi collection, cần xác định:

- Collection có bắt buộc phải có ít nhất một phần tử không?
- Có giới hạn số phần tử tối đa không?
- Phần tử có được phép null hoặc trùng lặp không?
- Thứ tự phần tử có mang ý nghĩa không?
- Nếu danh sách rỗng, nghiệp vụ hiểu là “không lọc”, “không có kết quả” hay dữ liệu không hợp lệ?

Các giới hạn số lượng và tính duy nhất cần được kiểm tra ở runtime. Không để một yêu cầu sinh ra danh sách quá lớn làm tăng chi phí truy vấn hoặc bộ nhớ.

## Đối tượng lồng nhau bằng DTO và record

Khi một nhóm trường luôn đi cùng nhau, hãy gom chúng vào DTO hoặc record thay vì tạo một danh sách tham số rời rạc dài. Cấu trúc Java thể hiện quan hệ giữa các trường và giúp schema mô tả object lồng nhau.

Ví dụ một bộ lọc sản phẩm có danh sách danh mục, khoảng giá và các thuộc tính:

```java
public record PriceRange(
        BigDecimal min,
        BigDecimal max) {
}

public record AttributeFilter(
        String name,
        List<String> values) {
}

public record ProductSearchCriteria(
        List<String> categories,
        PriceRange priceRange,
        List<AttributeFilter> attributes) {
}
```

Phương thức công cụ nhận một đối tượng tiêu chí:

```java
@Tool(
    name = "searchProducts",
    description = "Tìm sản phẩm đang kinh doanh theo danh mục, khoảng giá "
            + "và các thuộc tính. Dùng khi người dùng muốn lọc hoặc so sánh sản phẩm."
)
public List<ProductSummary> searchProducts(
        @ToolParam(description = "Bộ tiêu chí tìm kiếm sản phẩm")
        ProductSearchCriteria criteria) {

    validateSearchCriteria(criteria);
    return productService.search(criteria);
}
```

Ở đây, `ProductSearchCriteria` là object; `categories` là array chuỗi; `priceRange` là object con; `attributes` là array các object `AttributeFilter`; mỗi `values` lại là array chuỗi. Một cấu trúc có kiểu cụ thể giúp mô hình hiểu quan hệ dữ liệu tốt hơn một trường JSON tùy ý.

Schema minh họa cho phần object `ProductSearchCriteria` có thể có hình dạng như sau. Đây là ví dụ khái niệm để đọc cấu trúc; schema thực tế do Spring AI sinh ra cần được kiểm tra trong dự án:

```json
{
  "type": "object",
  "properties": {
    "categories": {
      "type": "array",
      "items": { "type": "string" }
    },
    "priceRange": {
      "type": "object",
      "properties": {
        "min": { "type": "number" },
        "max": { "type": "number" }
      }
    },
    "attributes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "values": {
            "type": "array",
            "items": { "type": "string" }
          }
        }
      }
    }
  }
}
```

Schema trên chưa thể hiện hết các ràng buộc bắt buộc, null, giới hạn phần tử hoặc quy tắc nghiệp vụ. Những chi tiết đó phụ thuộc cấu hình sinh schema và validation của ứng dụng.

### Khi nào nên dùng DTO hoặc record?

Ưu tiên DTO hoặc record khi:

- Nhiều trường tạo thành một khái niệm nghiệp vụ có tên, như `DateRange`, `AddressFilter` hoặc `ProductSearchCriteria`.
- Có object lồng nhau cần được tái sử dụng ở nhiều công cụ.
- Muốn giới hạn các thuộc tính hợp lệ bằng một cấu trúc rõ ràng.
- Muốn dễ viết validation, unit test và tài liệu cho hợp đồng đầu vào.

Record phù hợp với dữ liệu đầu vào bất biến và ngắn gọn. Class DTO phù hợp khi cần constructor tùy chỉnh, setter, kế thừa hoặc cách binding đặc biệt. Dù chọn kiểu nào, hãy bảo đảm Jackson hoặc converter đang dùng có thể tạo instance từ JSON arguments trong cấu hình dự án.

Không nên lồng object quá sâu. Cấu trúc nhiều tầng khiến schema dài, mô hình khó tạo đối số và người phát triển khó kiểm tra. Nếu một phần dữ liệu có thể được truy vấn riêng, cân nhắc tách thành công cụ khác hoặc dùng một DTO phẳng hơn.

## Danh sách object và object lồng nhiều tầng

Một mảng có thể chứa object thay vì kiểu nguyên thủy. Ví dụ, yêu cầu tạo báo cáo có thể chứa nhiều điều kiện lọc:

```java
public record OrderFilter(
        String field,
        String operator,
        String value) {
}

public record OrderReportRequest(
        List<OrderFilter> filters,
        List<String> groupBy,
        Integer limit) {
}
```

Trong JSON, `filters` có dạng:

```json
{
  "filters": [
    { "field": "status", "operator": "EQ", "value": "SHIPPED" },
    { "field": "region", "operator": "IN", "value": "NORTH" }
  ],
  "groupBy": ["region", "status"],
  "limit": 100
}
```

Ví dụ này minh họa mảng object và mảng chuỗi. Tuy nhiên, một cấu trúc có `field`, `operator`, `value` tự do dễ trở thành ngôn ngữ truy vấn tổng quát. Nếu dùng kiểu này, ứng dụng phải ánh xạ `field` và `operator` qua allowlist, kiểm tra kiểu giá trị theo từng field và giới hạn số điều kiện. Không chuyển trực tiếp nội dung mô hình tạo thành SQL, biểu thức truy vấn hoặc tên cột.

Nếu tập field và operator hữu hạn, hãy dùng enum hoặc DTO chuyên biệt để schema mô tả lựa chọn rõ hơn. Với một báo cáo cố định, các tham số có tên cụ thể thường an toàn và dễ hiểu hơn một bộ lọc động quá tổng quát.

## Map và các khóa động

`Map<String, T>` phù hợp khi số lượng thuộc tính thay đổi và các giá trị có cùng một kiểu. Ví dụ `Map<String, List<String>>` có thể biểu diễn tập nhãn theo nhóm:

```java
@Tool(
    name = "searchByLabels",
    description = "Tìm tài liệu theo các nhóm nhãn; mỗi khóa là tên nhóm "
            + "và mỗi giá trị là danh sách nhãn cần khớp."
)
public List<DocumentSummary> searchByLabels(
        @ToolParam(description = "Bản đồ tên nhóm tới danh sách nhãn")
        Map<String, List<String>> labelsByGroup) {

    validateLabels(labelsByGroup);
    return documentService.search(labelsByGroup);
}
```

JSON tương ứng có thể như sau:

```json
{
  "labelsByGroup": {
    "department": ["engineering", "platform"],
    "visibility": ["internal"]
  }
}
```

Với map, tên khóa do dữ liệu cung cấp nên schema thường khó liệt kê trước từng property. `additionalProperties` có thể mô tả kiểu giá trị của các khóa động nếu schema generator tạo được ràng buộc đó. Tuy nhiên, map không tự giới hạn tên khóa theo danh mục nghiệp vụ.

Hãy chọn map khi khóa thực sự là dữ liệu động. Nếu các trường có tên cố định như `minPrice`, `maxPrice`, `currency`, dùng DTO rõ ràng sẽ giúp mô hình hiểu hợp đồng tốt hơn và ứng dụng dễ kiểm tra hơn.

Tránh `Map<String, Object>` cho đầu vào công cụ nếu có thể. Kiểu `Object` cho phép giá trị tùy ý, làm schema kém cụ thể và tăng công việc kiểm tra/chuyển đổi khi thực thi. Nếu phải dùng, hãy định nghĩa rõ tập cấu trúc được phép và xác thực đệ quy trước khi xử lý.

## Kiểu generic và Java type erasure

Generic giúp khai báo kiểu phần tử hoặc kiểu giá trị, ví dụ `List<OrderFilter>` và `Map<String, List<String>>`. Thông tin generic trong chữ ký phương thức Java thường có thể được đọc qua metadata reflection, dù Java dùng type erasure cho nhiều thao tác ở runtime. Điều này có nghĩa `List<OrderFilter>` vẫn cung cấp thông tin kiểu tham số trong generic signature, nhưng một biến kiểu thô `List` hoặc type variable chưa được giải quyết không cho biết rõ kiểu phần tử thực tế.

So sánh:

```java
// Kiểu phần tử rõ ràng
List<OrderFilter> filters;

// Kiểu thô: không nêu loại phần tử
List filters;

// Type variable chưa được ràng buộc tại chữ ký cụ thể
<T> List<T> convertFilters(...);
```

Khi sinh schema, kiểu cụ thể giúp xác định `items` là chuỗi, số, enum hay object. Với raw type, wildcard rộng hoặc type variable chưa được giải quyết, schema có thể thiếu thông tin hoặc trở nên tổng quát. Cơ chế phân giải generic của Spring AI/Jackson và phiên bản cụ thể quyết định mức thông tin được giữ lại.

### Generic wrapper

Một DTO generic như `PageRequest<T>` có thể tái sử dụng cho nhiều loại dữ liệu trong mã ứng dụng. Tuy nhiên, schema của một công cụ cần một kiểu cụ thể để mô hình biết cấu trúc của `T`.

```java
public record PageRequest<T>(
        T filter,
        Integer page,
        Integer size) {
}

public record ProductFilter(String category, BigDecimal maxPrice) {
}
```

Nếu chữ ký công cụ khai báo một kiểu tham số cụ thể như `PageRequest<ProductFilter>`, generic signature có thể cung cấp kiểu `ProductFilter` cho quá trình introspection. Nhưng nếu chữ ký chỉ dùng raw `PageRequest`, `PageRequest<?>` hoặc một type variable chưa giải quyết, schema có thể không mô tả được `filter` như mong muốn.

Trong hợp đồng gửi cho mô hình, ưu tiên một kiểu cụ thể hoặc DTO chuyên biệt như `ProductPageRequest` khi schema generic không được giải quyết ổn định. Tính tái sử dụng trong Java không nên làm hợp đồng công cụ trở nên mơ hồ.

### Những kiểu cần cân nhắc kỹ

| Kiểu khai báo | Rủi ro đối với schema hoặc chuyển đổi | Hướng xử lý |
|---|---|---|
| Raw `List` hoặc `Map` | Không có kiểu phần tử/giá trị cụ thể. | Khai báo generic cụ thể như `List<OrderFilter>`. |
| `List<?>` | Mô tả phần tử quá rộng. | Dùng DTO hoặc kiểu phần tử xác định. |
| `List<T>` trong method generic | `T` có thể chưa được giải quyết khi framework introspect method. | Dùng kiểu cụ thể cho tool method hoặc callback. |
| `Map<String, Object>` | Giá trị có thể là nhiều hình dạng JSON khác nhau. | Dùng DTO, sealed model được hỗ trợ hoặc kiểm tra cấu trúc theo allowlist. |
| `Optional<T>` | Cách biểu diễn optional trong schema và converter có thể khác theo phiên bản. | Dùng `required`/nullable theo API được hỗ trợ và xác minh schema thực tế. |
| Kiểu polymorphic với nhiều subtype | Schema có thể không thể hiện đầy đủ subtype mà provider hỗ trợ. | Dùng enum discriminator hoặc DTO riêng, rồi kiểm tra schema với provider. |

Đặc biệt, không nên giả định một kiểu Java hợp lệ là tự động được mọi model provider chấp nhận. Một schema JSON hợp lệ về mặt cú pháp vẫn có thể dùng cấu trúc mà provider giới hạn hoặc diễn giải khác.

## Phân biệt required, optional và nullable trong cấu trúc lồng nhau

Với object và collection, cần phân biệt sự hiện diện của thuộc tính với giá trị bên trong:

- **Required:** thuộc tính phải xuất hiện trong object.
- **Optional:** thuộc tính có thể không xuất hiện.
- **Nullable:** thuộc tính có thể xuất hiện với giá trị `null` nếu schema và converter hỗ trợ cách biểu diễn đó.
- **Empty collection:** thuộc tính xuất hiện với `[]`; đây không phải `null` và cũng không giống thuộc tính bị thiếu.

Ví dụ, bốn trường hợp sau không nhất thiết có cùng ý nghĩa:

```json
{}
```

```json
{ "categories": null }
```

```json
{ "categories": [] }
```

```json
{ "categories": ["books", "office"] }
```

Ứng dụng cần quy định rõ trường hợp nào được chấp nhận. Với danh sách bộ lọc, `[]` có thể có nghĩa không áp dụng bộ lọc; với danh sách trạng thái bắt buộc, `[]` có thể là đầu vào không hợp lệ. Không để mỗi service tự hiểu khác nhau.

Trong DTO lồng nhau, quy tắc này áp dụng ở từng tầng. Một object `priceRange` có thể bị thiếu, có thể null, hoặc xuất hiện với `min` và `max` không đầy đủ. Nếu nghiệp vụ yêu cầu cả hai biên, hãy kiểm tra cặp giá trị và thứ tự của chúng trong ứng dụng.

## Validation phải đi theo cấu trúc dữ liệu

Schema mô tả hình dạng dữ liệu cho mô hình; validation trong ứng dụng bảo vệ hệ thống. Hãy kiểm tra đệ quy các cấu trúc lồng nhau thay vì chỉ xác thực object ngoài cùng.

Ví dụ với `ProductSearchCriteria`, cần kiểm tra:

- `criteria` không null.
- `categories` có số phần tử trong giới hạn, mỗi tên danh mục hợp lệ và không chứa giá trị trùng nếu nghiệp vụ không cho phép.
- `priceRange.min` và `priceRange.max` không âm; nếu cả hai có giá trị thì `min` không lớn hơn `max`.
- `attributes` có số phần tử giới hạn; mỗi phần tử có `name` nằm trong allowlist và `values` có số lượng/kích thước hợp lý.
- Không chấp nhận trường hoặc cấu trúc không được hỗ trợ nếu converter cho phép dữ liệu dư.

Có thể dùng Jakarta Bean Validation (`@Valid`, `@NotNull`, `@Size`, `@DecimalMin` và constraint tùy chỉnh) để tổ chức validation. Tuy nhiên, không giả định annotation validation tự động được chuyển thành JSON Schema hoặc tự chạy trong mọi đường gọi tool. Hãy gọi validator rõ ràng ở ranh giới thực thi hoặc xác minh cơ chế tích hợp của phiên bản đang dùng.

Một ví dụ đơn giản:

```java
public record PriceRange(
        @DecimalMin("0.0") BigDecimal min,
        @DecimalMin("0.0") BigDecimal max) {
}

public record ProductSearchCriteria(
        @Size(max = 20) List<String> categories,
        @Valid PriceRange priceRange,
        @Size(max = 30) List<@Valid AttributeFilter> attributes) {
}
```

Các annotation này chỉ mô tả một phần ràng buộc. Ví dụ `@DecimalMin` không tự bảo đảm `min <= max`; cần class-level constraint hoặc kiểm tra nghiệp vụ riêng. Ngoài ra, xác minh rằng validator thực sự được gọi khi phương thức tool được thực thi.

## Giữ schema đủ nhỏ và dễ hiểu

Một schema lớn với nhiều tầng object, danh sách dài, map động và nhiều nhánh tùy chọn làm tăng độ khó tạo đối số. Hãy giữ hợp đồng tập trung vào một mục tiêu nghiệp vụ.

Một số cách đơn giản hóa:

1. Giới hạn số tầng lồng nhau và số thuộc tính trong mỗi object.
2. Dùng enum cho tập giá trị hữu hạn thay vì chuỗi tự do.
3. Dùng DTO riêng cho từng trường hợp sử dụng thay vì một DTO tổng quát có hàng chục trường tùy chọn.
4. Hạn chế `Map<String, Object>` và các collection không có generic cụ thể.
5. Đặt giới hạn số phần tử, độ dài chuỗi và kích thước payload.
6. Tách thao tác tìm kiếm, xem chi tiết và cập nhật thành các công cụ có mục tiêu riêng khi chúng có quy tắc khác nhau.

Không gửi các trường nội bộ như `tenantId`, `userId`, quyền, token hay thông tin xác thực trong schema để mô hình điền. Những giá trị đó phải đến từ context đáng tin cậy do ứng dụng cung cấp và được kiểm tra khi thực thi.

## Kiểm tra schema thực tế được tạo

Đừng chỉ nhìn vào class Java rồi kết luận schema đúng. Sau khi đăng ký tool, hãy kiểm tra `ToolDefinition` hoặc schema đầu vào được tạo bởi phiên bản Spring AI trong dự án. Cách truy cập/quan sát có thể khác theo API; có thể dùng log debug có kiểm soát, unit test cho định nghĩa tool hoặc kiểm tra request gửi đến model provider trong môi trường thử nghiệm.

Đối với mỗi tham số phức tạp, kiểm tra các điểm sau:

- Mảng có `items` đúng kiểu hay không.
- Mảng object có schema cho từng thuộc tính của phần tử hay không.
- DTO lồng nhau có đủ `properties` và kiểu dữ liệu hay không.
- Generic type có được phân giải thành kiểu cụ thể hay bị biến thành object quá rộng.
- `required`, nullable và giá trị mặc định có đúng với hợp đồng mong muốn không.
- Enum có chứa đúng các giá trị mà ứng dụng chấp nhận không.
- Map có cho phép khóa tùy ý ngoài phạm vi nghiệp vụ không.
- Schema có tuân theo giới hạn của model provider đang dùng không.

Nếu schema sai hoặc quá rộng, hãy sửa kiểu Java, annotation hoặc cấu hình schema generator rồi kiểm tra lại. Đừng chỉ sửa prompt để che một schema không phản ánh đúng hợp đồng thực thi.

## Kiểm thử các cấu trúc phức tạp

Một bộ kiểm thử hữu ích nên bao gồm cả chuyển đổi JSON và quy tắc nghiệp vụ:

| Trường hợp | Dữ liệu ví dụ | Kết quả cần xác minh |
|---|---|---|
| Danh sách hợp lệ | `categories: ["books", "office"]` | Deserialize đúng kiểu phần tử và truy vấn đúng bộ lọc. |
| Danh sách rỗng | `categories: []` | Ứng dụng áp dụng đúng quy tắc cho collection rỗng. |
| Phần tử sai kiểu | `categories: ["books", 10]` | Chuyển đổi hoặc validation từ chối dữ liệu. |
| Object lồng hợp lệ | `priceRange: {"min": 100, "max": 500}` | DTO con được tạo đúng và quy tắc khoảng giá được áp dụng. |
| Object lồng thiếu trường | `priceRange: {"min": 100}` | Ứng dụng xử lý theo quy tắc required của object con. |
| Mảng object | `attributes: [{"name":"color","values":["blue"]}]` | Mỗi phần tử được chuyển thành `AttributeFilter` đúng kiểu. |
| Generic cụ thể | `List<OrderFilter>` | Schema và converter giữ đúng kiểu `OrderFilter`. |
| Generic mơ hồ | Raw `List` hoặc `Map<String,Object>` | Phát hiện schema quá rộng và kiểm tra runtime chặt chẽ. |
| Dữ liệu quá lớn | Hàng nghìn phần tử hoặc chuỗi rất dài | Ứng dụng từ chối hoặc giới hạn trước khi truy vấn. |
| Trường null hoặc bị thiếu | `priceRange: null` hoặc không có thuộc tính | Hai trường hợp được xử lý theo hợp đồng đã định nghĩa. |

Nên có unit test cho validation và mapping, integration test cho tool callback/converter, cùng kiểm thử schema với model provider. Khi nâng cấp Spring AI hoặc đổi provider, chạy lại bộ kiểm tra schema vì cách hỗ trợ kiểu phức tạp có thể thay đổi.

## Bài tập thực hành

Xây dựng công cụ tìm sản phẩm với bộ lọc lồng nhau:

1. Tạo `ProductSearchCriteria` gồm danh sách danh mục, `PriceRange` và danh sách `AttributeFilter`.
2. Dùng `List<String>`, `List<AttributeFilter>` và record lồng nhau để biểu diễn cấu trúc.
3. Thêm một biến thể dùng `Map<String, List<String>>`; so sánh schema và mức kiểm soát với DTO.
4. Thử raw `List`, `List<?>` và một generic wrapper có type variable; quan sát sự khác nhau trong schema được tạo.
5. Xác định ý nghĩa của danh sách rỗng, object null, trường bị thiếu và trường có giá trị null.
6. Thêm validation cho số lượng phần tử, khoảng giá, tên thuộc tính và kích thước chuỗi.
7. Kiểm tra schema thực tế và chạy test cho dữ liệu hợp lệ, sai kiểu, thiếu trường và vượt giới hạn.

Bạn hoàn thành khi có thể giải thích schema của từng mảng và object con, chỉ ra kiểu generic nào được phân giải rõ ràng, và chứng minh ứng dụng từ chối dữ liệu sai trước khi gọi dịch vụ nghiệp vụ.

## Danh sách kiểm tra

- [ ] Mọi collection đều khai báo kiểu phần tử cụ thể.
- [ ] Mọi object lồng nhau đều có DTO hoặc record với thuộc tính có ý nghĩa.
- [ ] Dùng map khi khóa thực sự động; tránh map giá trị `Object` nếu có cấu trúc rõ ràng hơn.
- [ ] Không dùng raw type, wildcard rộng hoặc type variable chưa giải quyết trong hợp đồng tool nếu có thể tránh.
- [ ] Phân biệt rõ required, optional, nullable và collection rỗng.
- [ ] Kiểm tra `items`, `properties`, `required`, enum và `additionalProperties` trong schema thực tế.
- [ ] Validation được áp dụng đệ quy cho object, collection và phần tử lồng nhau.
- [ ] Có giới hạn số phần tử, độ sâu, kích thước chuỗi và payload.
- [ ] Thông tin danh tính, tenant và quyền đến từ nguồn đáng tin cậy, không do mô hình tự điền.
- [ ] Đã kiểm thử schema và hành vi với phiên bản Spring AI cùng model provider mục tiêu.

Danh sách, object lồng nhau và generic giúp mô hình gửi đầu vào gần với cấu trúc nghiệp vụ của ứng dụng. Chất lượng tích hợp phụ thuộc vào việc kiểu Java thể hiện rõ hợp đồng, schema được sinh đúng và ứng dụng xác thực toàn bộ dữ liệu trước khi thực thi.
