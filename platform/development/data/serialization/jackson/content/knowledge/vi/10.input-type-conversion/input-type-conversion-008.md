# Lựa chọn từ chối, chấp nhận hoặc chuẩn hóa đầu vào tường minh

Khi Jackson deserialize JSON, giá trị đầu vào đôi khi không có đúng kiểu mà thuộc tính Java mong đợi. Một API có thể gửi số dưới dạng chuỗi, gửi số thập phân cho thuộc tính nguyên, hoặc gửi chuỗi rỗng thay cho một giá trị tùy chọn. Jackson có thể chuyển đổi một số dạng dữ liệu như vậy, nhưng nếu dựa hoàn toàn vào hành vi mặc định thì hợp đồng đầu vào dễ trở nên khó đoán và có thể thay đổi theo kiểu đích hoặc cấu hình.

Jackson cung cấp cơ chế **coercion configuration** để quyết định rõ cách xử lý từng hình dạng đầu vào:

- **Fail:** từ chối dữ liệu không đúng dạng.
- **TryConvert:** cho phép deserializer thử chuyển đổi sang kiểu đích.
- **AsNull:** xem đầu vào như giá trị null.
- **AsEmpty:** chuyển đầu vào thành giá trị rỗng theo định nghĩa của kiểu đích.

Các chính sách này được cấu hình theo kiểu logic hoặc theo lớp Java cụ thể thông qua `CoercionConfig` và `ObjectMapper`. Nhờ đó, ứng dụng có thể chấp nhận một dạng đầu vào có chủ đích, từ chối dạng không an toàn và chuẩn hóa các biểu diễn rỗng theo quy tắc nghiệp vụ.

## 1. Vì sao cần chính sách coercion tường minh?

Giả sử DTO có thuộc tính số lượng:

```java
public class OrderRequest {
    private int quantity;

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

JSON đúng kiểu có dạng:

```json
{
  "quantity": 12
}
```

Nhưng một client có thể gửi:

```json
{
  "quantity": "12"
}
```

Đây là một chuỗi JSON, không phải JSON number. Jackson có thể hỗ trợ chuyển chuỗi số thành kiểu số trong một số cấu hình. Một client khác lại có thể gửi:

```json
{
  "quantity": 12.7
}
```

Đây là JSON number có phần thập phân. Chuyển nó thành `int` có thể làm mất phần dữ liệu. Nếu gửi `"twelve"`, việc chuyển đổi không hợp lệ.

Không phải mọi chuyển đổi đều có cùng ý nghĩa:

| Đầu vào | Kiểu Java đích | Vấn đề cần quyết định |
|---|---|---|
| `"12"` | `int` | Có chấp nhận chuỗi biểu diễn số không? |
| `12.7` | `int` | Có cho phép mất phần thập phân không? |
| `"twelve"` | `int` | Phải từ chối vì không thể chuyển thành số? |
| `""` | `Integer` | Có xem chuỗi rỗng như null hay giá trị rỗng không? |
| `[]` | `User` | Có chấp nhận array rỗng như null/empty không? |
| `1` | `List<Integer>` | Có chấp nhận scalar như một array một phần tử không? |

Một chính sách tường minh làm cho API dễ dự đoán hơn. Ví dụ, hệ thống có thể chấp nhận chuỗi số từ một đối tác cũ, nhưng từ chối số thập phân cho thuộc tính nguyên để tránh âm thầm làm sai dữ liệu.

## 2. CoercionConfig và các thành phần liên quan

Jackson Databind cung cấp các kiểu cấu hình sau:

- `CoercionInputShape`: mô tả hình dạng JSON đầu vào, chẳng hạn `String`, `Integer`, `Float`, `Boolean`, `Array`, `Object`, `EmptyString`, `EmptyArray` hoặc `EmptyObject`.
- `CoercionAction`: mô tả hành động cần áp dụng với hình dạng đầu vào đó.
- `CoercionConfig`: chứa chính sách coercion.
- `MutableCoercionConfig`: phiên bản cấu hình có thể thay đổi, được trả về bởi API cấu hình của mapper.
- `LogicalType`: nhóm kiểu logic như `Integer`, `Float`, `Boolean`, `Textual`, `DateTime`, `POJO`, `Collection` hoặc `Map`.

Thông thường, ta cấu hình thông qua `ObjectMapper`:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Ví dụ trên yêu cầu Jackson từ chối hình dạng đầu vào `String` khi đích thuộc nhóm kiểu logic `Integer`. Các kiểu số nguyên như `int`, `long`, `Integer` và `Long` thuộc nhóm logic này.

Có thể lấy cấu hình theo một lớp Java cụ thể:

```java
mapper.coercionConfigFor(Integer.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert);
```

Hoặc đặt quy tắc mặc định rộng hơn cho các kiểu chưa có cấu hình cụ thể:

```java
mapper.coercionConfigDefaults()
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
```

Hãy ưu tiên chính sách ở phạm vi hẹp khi chỉ một kiểu dữ liệu có yêu cầu riêng. Cấu hình mặc định toàn mapper có thể tác động đến nhiều DTO và module khác nhau.

### 2.1. Các hình dạng đầu vào

Một số `CoercionInputShape` thường gặp:

| Hình dạng | Ví dụ JSON |
|---|---|
| `String` | `"12"`, `"true"`, `"hello"` |
| `Integer` | `12` |
| `Float` | `12.5` |
| `Boolean` | `true`, `false` |
| `Array` | `[1, 2]` |
| `Object` | `{ "id": 1 }` |
| `EmptyString` | `""` |
| `EmptyArray` | `[]` |
| `EmptyObject` | `{}` |
| `Binary` | Giá trị binary được parser cung cấp trong ngữ cảnh phù hợp |

Jackson phân biệt một số hình dạng rỗng với hình dạng tổng quát. Ví dụ, `EmptyString` khác `String`; `EmptyArray` khác `Array`. Vì vậy, nếu muốn xử lý riêng chuỗi rỗng, cần cấu hình đúng shape đó.

### 2.2. Các hành động CoercionAction

| Hành động | Ý nghĩa |
|---|---|
| `Fail` | Báo lỗi khi gặp hình dạng đầu vào đã cấu hình. |
| `TryConvert` | Cho phép deserializer thực hiện chuyển đổi mà nó hỗ trợ. |
| `AsNull` | Xử lý đầu vào như giá trị null. |
| `AsEmpty` | Dùng giá trị rỗng do deserializer của kiểu đích cung cấp. |

`TryConvert` không có nghĩa là Jackson có thể biến mọi chuỗi thành mọi kiểu. Ví dụ, chuỗi `"12x"` vẫn không thể trở thành số nguyên hợp lệ. Hành động này cho phép conversion phù hợp với deserializer; dữ liệu không hợp lệ vẫn có thể gây lỗi.

`AsEmpty` cũng không có một giá trị cố định cho mọi kiểu. Giá trị rỗng phụ thuộc kiểu đích và deserializer. Với collection, nó có thể là collection rỗng; với kiểu khác, cách định nghĩa empty value có thể khác. Hãy xác định rõ kết quả cần có thay vì giả định `AsEmpty` luôn tương đương `null` hoặc `0`.

## 3. Từ chối đầu vào không đúng dạng bằng Fail

Khi dữ liệu đầu vào phải tuân thủ kiểu JSON rõ ràng, `Fail` là lựa chọn phù hợp. Ví dụ, API yêu cầu `quantity` là JSON number nguyên, không chấp nhận chuỗi số hoặc số thập phân.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
```

Với DTO:

```java
public class OrderRequest {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Đầu vào hợp lệ:

```json
{
  "quantity": 12
}
```

Đầu vào bị từ chối:

```json
{
  "quantity": "12"
}
```

Và:

```json
{
  "quantity": 12.7
}
```

Đây là cách phù hợp khi kiểu dữ liệu là một phần quan trọng của hợp đồng API. Client phải gửi đúng JSON number và không thể dựa vào việc Jackson tự chuyển chuỗi hoặc làm tròn/cắt phần thập phân.

### 3.1. Từ chối chuỗi rỗng riêng biệt

Chuỗi rỗng có shape riêng. Nếu muốn từ chối cả chuỗi rỗng cho nhóm số nguyên:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
```

Nếu cần xem chuỗi chỉ chứa khoảng trắng như empty string, cấu hình thêm:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setAcceptBlankAsEmpty(false);
```

`setAcceptBlankAsEmpty(false)` yêu cầu Jackson không xem chuỗi trắng là dạng empty được chấp nhận theo cấu hình đó. Cách xử lý chính xác còn phụ thuộc shape và phiên bản Jackson; khi hợp đồng nghiêm ngặt, hãy kiểm tra cả `""` và `"   "` bằng mapper thực tế.

### 3.2. Từ chối cấu trúc thay cho scalar

Nếu một thuộc tính số không được phép nhận array hoặc object, có thể cấu hình shape tương ứng:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.Array, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Object, CoercionAction.Fail);
```

Quy tắc này làm rõ rằng thuộc tính số chỉ nhận các dạng scalar được cho phép. Với một API public, việc từ chối cấu trúc sai dạng thường dễ phát hiện lỗi client hơn là âm thầm chuyển đổi.

## 4. Chấp nhận chuyển đổi bằng TryConvert

Không phải API nào cũng kiểm soát được toàn bộ client. Một số hệ thống cũ có thể gửi số dưới dạng chuỗi. Khi muốn chấp nhận dạng đầu vào đó, hãy cho phép chuyển đổi có chủ đích.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert);
```

Với JSON:

```json
{
  "quantity": "12"
}
```

Jackson có thể chuyển chuỗi số thành kiểu nguyên tương ứng. Nhưng chuỗi không biểu diễn được số hợp lệ vẫn gây lỗi:

```json
{
  "quantity": "twelve"
}
```

`TryConvert` cho phép thử chuyển đổi theo logic của deserializer, không biến input không hợp lệ thành một giá trị bất kỳ.

### 4.1. Chỉ cho phép dạng cần thiết

Một chính sách thường gặp là chấp nhận string chứa số nguyên nhưng từ chối float:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
```

Kết quả mong muốn:

| JSON đầu vào | Kết quả |
|---|---|
| `12` | Chấp nhận như số nguyên |
| `"12"` | Thử chuyển đổi thành số nguyên |
| `12.5` | Từ chối |
| `"twelve"` | Từ chối vì không chuyển đổi được |

Chính sách này giữ tính tương thích với client gửi string số, đồng thời ngăn việc cắt phần thập phân.

### 4.2. Cấu hình theo LogicalType hoặc lớp cụ thể

`LogicalType` phù hợp khi nhiều kiểu Java cùng chia sẻ một chính sách. Ví dụ, quy tắc với nhóm số nguyên có thể áp dụng cho nhiều thuộc tính `int`, `long`, `Integer` và `Long`.

Nếu một lớp cụ thể cần ngoại lệ, có thể cấu hình theo lớp:

```java
mapper.coercionConfigFor(Quantity.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert);
```

Ví dụ này minh họa cấu hình nhắm vào kiểu Java `Quantity`. Hãy dùng đúng kiểu đích mà Jackson đang deserialize. Nếu `Quantity` là value object có custom deserializer, việc conversion còn phụ thuộc deserializer đó có hỗ trợ coercion tương ứng hay không.

### 4.3. Cẩn trọng với cấu hình rộng

Không nên bật conversion rộng cho mọi kiểu chỉ để sửa một trường hợp cụ thể. Ví dụ, nếu một endpoint chỉ cần nhận `quantity` dưới dạng chuỗi số từ client cũ, hãy giới hạn chính sách ở logical type hoặc class phù hợp. Một thay đổi ở defaults có thể ảnh hưởng nhiều DTO, enum, ngày giờ hoặc kiểu scalar khác.

## 5. Chuẩn hóa đầu vào thành null bằng AsNull

Trong một số API, chuỗi rỗng có nghĩa là “không cung cấp giá trị”. Có thể yêu cầu Jackson xem `EmptyString` như null cho nhóm kiểu đích phù hợp.

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

DTO nên dùng wrapper nếu cần lưu trạng thái null:

```java
public class SearchRequest {
    private Integer pageSize;

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
```

Với JSON:

```json
{
  "pageSize": ""
}
```

Jackson xử lý chuỗi rỗng như null theo chính sách đã cấu hình. Ứng dụng có thể kiểm tra null rồi áp dụng default nghiệp vụ ở tầng service hoặc validation.

### 5.1. Phân biệt AsNull với Nulls.SKIP

`AsNull` là hành động coercion: nó biến một hình dạng đầu vào như chuỗi rỗng thành giá trị null trong quá trình deserialize.

`Nulls.SKIP` là chính sách xử lý null khi gán vào property. Ví dụ:

```java
public class SearchRequest {
    private Integer pageSize = 20;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }

    public Integer getPageSize() {
        return pageSize;
    }
}
```

Nếu mapper đã chuyển `""` thành null và setter dùng `Nulls.SKIP`, thao tác gán null có thể bị bỏ qua, giữ giá trị hiện có `20`. Nếu không có chính sách skip, null có thể được gán vào field wrapper.

Hai cơ chế giải quyết hai bước khác nhau:

1. Coercion quyết định cách diễn giải hình dạng đầu vào.
2. Null handling quyết định cách xử lý giá trị null sau khi đã được nhận diện.

Không nên coi `AsNull` và `Nulls.SKIP` là hai cách viết thay thế nhau.

### 5.2. Null với kiểu primitive

Kiểu primitive như `int` và `boolean` không thể giữ null. Nếu coercion trả về null cho primitive, Jackson có thể dùng giá trị mặc định theo cấu hình hoặc báo lỗi nếu bật `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`.

Ví dụ:

```java
mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Nếu nghiệp vụ cần phân biệt “không có giá trị” với `0` hoặc `false`, hãy dùng wrapper `Integer` hoặc `Boolean` ở DTO đầu vào. Sau đó validate và chuyển sang kiểu primitive/domain cần thiết ở tầng xử lý nghiệp vụ.

## 6. Chuẩn hóa đầu vào thành giá trị rỗng bằng AsEmpty

`AsEmpty` yêu cầu Jackson dùng empty value mà deserializer của kiểu đích cung cấp. Hành vi cụ thể phụ thuộc kiểu.

Ví dụ với collection, có thể xem array rỗng là một collection rỗng:

```java
mapper.coercionConfigFor(LogicalType.Collection)
    .setCoercion(CoercionInputShape.EmptyArray, CoercionAction.AsEmpty);
```

Tuy nhiên, collection deserializer thường đã có quy tắc riêng cho array rỗng. Cần kiểm tra nhu cầu thực tế trước khi thêm cấu hình này. Ví dụ rõ hơn là xử lý một hình dạng empty cho kiểu có empty value phù hợp:

```java
mapper.coercionConfigFor(LogicalType.POJO)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsEmpty);
```

Với POJO, empty value được xác định bởi deserializer và có thể không giống nhau giữa các kiểu. Không nên giả định mọi POJO đều có thể được tạo từ empty string; nếu không có empty value phù hợp, conversion có thể không đáp ứng mong muốn.

### 6.1. AsEmpty không đồng nghĩa với tạo object mặc định theo nghiệp vụ

`AsEmpty` không phải một cơ chế tổng quát để chạy constructor mặc định rồi điền các giá trị nghiệp vụ tùy ý. Nó yêu cầu deserializer cung cấp empty value. Với kiểu tùy chỉnh, empty value có thể cần được định nghĩa trong custom deserializer.

Nếu ứng dụng cần một default cụ thể như `pageSize = 20`, `status = "NEW"` hoặc một object có invariant, nên thực hiện ở constructor, setter, creator hoặc tầng mapping/service. Không nên dựa vào `AsEmpty` để thay thế logic khởi tạo domain.

## 7. Cấu hình chuỗi rỗng và chuỗi chỉ có khoảng trắng

Jackson phân biệt chuỗi thông thường, chuỗi rỗng và chuỗi chỉ chứa whitespace theo cấu hình chấp nhận blank string. Có thể cấu hình:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setAcceptBlankAsEmpty(true)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

Khi bật `setAcceptBlankAsEmpty(true)`, chuỗi chỉ chứa khoảng trắng có thể được xem như empty string cho quy tắc coercion liên quan. Kết hợp `AsNull`, ứng dụng có thể chuẩn hóa cả `""` và chuỗi trắng thành null cho nhóm số nguyên.

Nếu muốn phân biệt:

- `""` được chuyển thành null.
- `"   "` bị từ chối.
- `"12"` được chuyển thành số nguyên.

có thể cấu hình `EmptyString` thành `AsNull`, `String` thành `TryConvert` và đặt `setAcceptBlankAsEmpty(false)`. Hãy xác nhận behavior bằng phiên bản Jackson của ứng dụng, vì cách phân loại blank string là chi tiết cần kiểm tra cùng coercion config.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();
MutableCoercionConfig integerCoercion = mapper.coercionConfigFor(LogicalType.Integer);

integerCoercion
    .setAcceptBlankAsEmpty(false)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);
```

Đối với các input có yêu cầu chặt chẽ, hãy kiểm tra riêng `""`, `" "`, `"12"` và `"twelve"` thay vì suy luận tất cả chuỗi đều đi qua cùng một nhánh.

## 8. Phân biệt coercion với các DeserializationFeature khác

Jackson có những feature lịch sử để điều khiển một số kiểu chuyển đổi cụ thể. Chúng vẫn có thể hữu ích, nhưng không nên nhầm với cơ chế coercion theo input shape.

| Feature | Trường hợp liên quan |
|---|---|
| `ACCEPT_FLOAT_AS_INT` | Cho phép hoặc từ chối chuyển JSON float sang kiểu số nguyên. |
| `ACCEPT_SINGLE_VALUE_AS_ARRAY` | Cho phép đọc một scalar như collection có một phần tử. |
| `UNWRAP_SINGLE_VALUE_ARRAYS` | Cho phép đọc array một phần tử vào kiểu scalar. |
| `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` | Điều khiển một số trường hợp empty string thành null cho kiểu object. |
| `ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT` | Điều khiển một số trường hợp empty array thành null cho kiểu object. |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Từ chối gán JSON null cho kiểu primitive. |

Ví dụ, nếu API muốn nhận scalar `7` như list `[7]`, đây là tính năng cấu trúc collection:

```java
mapper.enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
```

Nếu muốn một array một phần tử được đọc thành scalar, đó là chiều ngược lại:

```java
mapper.enable(DeserializationFeature.UNWRAP_SINGLE_VALUE_ARRAYS);
```

Hai feature này điều khiển việc bọc/mở cấu trúc array. Chúng không giống với việc chuyển string thành number hoặc empty string thành null. Với ứng dụng dùng Jackson phiên bản có `CoercionConfig`, ưu tiên cấu hình coercion cụ thể cho các shape cần kiểm soát, đồng thời kiểm tra các feature cũ có đang tác động lên cùng tình huống hay không.

### 8.1. ALLOW_COERCION_OF_SCALARS

`MapperFeature.ALLOW_COERCION_OF_SCALARS` là một công tắc rộng liên quan đến coercion giữa các scalar type. Tắt feature này có thể hạn chế một số chuyển đổi scalar, nhưng không diễn đạt chi tiết bằng cách chọn từng input shape và hành động.

```java
mapper.disable(MapperFeature.ALLOW_COERCION_OF_SCALARS);
```

Khi cần chính sách cụ thể như “cho phép chuỗi số nhưng từ chối float cho Integer”, `CoercionConfig` dễ diễn đạt ý định hơn. Nếu ứng dụng đang dùng feature rộng này, hãy kiểm tra tương tác với các rule cụ thể trong phiên bản Jackson hiện tại.

## 9. Cấu hình theo phạm vi: defaults, LogicalType và lớp Java

Jackson cho phép đặt coercion policy ở nhiều phạm vi.

### 9.1. Defaults cho mapper

`coercionConfigDefaults()` trả về cấu hình mặc định được dùng làm fallback:

```java
mapper.coercionConfigDefaults()
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
```

Chính sách này có thể ảnh hưởng nhiều kiểu đích. Chỉ nên đặt ở cấp defaults nếu đó thực sự là quy tắc chung của ứng dụng.

### 9.2. LogicalType cho nhóm kiểu

`coercionConfigFor(LogicalType)` đặt quy tắc cho một nhóm kiểu logic:

```java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Cách này hữu ích khi mọi số nguyên trong ứng dụng cần cùng chính sách. Các nhóm như `Float`, `Boolean`, `Textual`, `DateTime`, `POJO`, `Collection` và `Map` giúp giới hạn ảnh hưởng theo loại dữ liệu.

### 9.3. Lớp Java cụ thể

`coercionConfigFor(Class<?>)` dùng khi một kiểu Java cần ngoại lệ riêng:

```java
mapper.coercionConfigFor(ExternalId.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert);
```

Điều này hữu ích khi hai kiểu cùng thuộc một logical type nhưng có hợp đồng đầu vào khác nhau. Hãy cấu hình đúng lớp đích mà Jackson đang xử lý; nếu kiểu có custom deserializer, cần bảo đảm deserializer hỗ trợ chính sách mong muốn.

### 9.4. Cấu hình reader riêng cho một luồng xử lý

Coercion config thuộc cấu hình mapper, vì vậy nếu cần các chính sách khác nhau cho từng luồng độc lập, hãy cân nhắc mapper riêng được cấu hình trước và tái sử dụng. `ObjectReader` có thể thay đổi nhiều `DeserializationFeature`, nhưng không phải mọi API cấu hình coercion đều có biến thể trực tiếp trên reader.

Không nên sửa coercion config của một mapper singleton theo từng request. Nếu hai endpoint có hợp đồng đầu vào khác nhau, có thể dùng hai mapper được cấu hình từ đầu, hoặc tách việc chuẩn hóa/validation ở tầng request mapper để tránh thay đổi trạng thái cấu hình dùng chung.

## 10. Ví dụ tổng hợp: chính sách cho request nhập đơn hàng

Giả sử API nhận request với quy tắc:

- `quantity` phải là số nguyên JSON; không nhận chuỗi số hay số thập phân.
- `pageSize` có thể nhận chuỗi số từ client cũ.
- Chuỗi rỗng của `pageSize` được chuẩn hóa thành null.
- Chuỗi không phải số vẫn bị từ chối.

DTO:

```java
public class OrderImportRequest {
    private Integer quantity;
    private Integer pageSize;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
```

Để biểu diễn chính sách khác nhau theo từng property, có thể tách DTO thành kiểu con/kiểu wrapper riêng hoặc dùng custom deserializer/property-level deserialization configuration. `CoercionConfig` tập trung vào logical type hoặc class, không trực tiếp gắn rule riêng vào tên field thông thường.

Nếu hai field thuộc hai kiểu wrapper khác nhau, ví dụ `StrictQuantity` và `LegacyPageSize`, có thể đặt policy theo class:

```java
mapper.coercionConfigFor(StrictQuantity.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);

mapper.coercionConfigFor(LegacyPageSize.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull)
    .setAcceptBlankAsEmpty(false);
```

Trong thực tế, các wrapper này cần có deserializer hoặc creator phù hợp để nhận giá trị tương ứng. Nếu không muốn tạo kiểu riêng, hãy dùng custom deserializer hoặc tách request DTO theo hợp đồng endpoint.

Điểm quan trọng là không nên giả định `CoercionConfig` có thể chọn property bằng tên field. Rule nhắm đến kiểu logic hoặc lớp Java đích. Nếu hai field cùng kiểu nhưng cần chính sách khác nhau, hãy chọn cơ chế ở cấp property như custom deserializer hoặc thiết kế DTO riêng.

## 11. Kiểm tra chính sách coercion bằng ví dụ nhỏ

Khi cấu hình coercion, hãy thử từng hình dạng đầu vào và xác nhận cả kết quả lẫn lỗi. Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.AsNull);

Integer first = mapper.readValue("\"12\"", Integer.class);
Integer second = mapper.readValue("\"\"", Integer.class);
System.out.println(first);  // 12
System.out.println(second); // null
```

Các trường hợp nên thử:

| Input | Điều cần xác nhận |
|---|---|
| `12` | Số nguyên hợp lệ được giữ nguyên. |
| `"12"` | Chuỗi số được chuyển đổi nếu rule là `TryConvert`. |
| `12.5` | Bị từ chối nếu float-to-integer đặt `Fail`. |
| `"12.5"` | Không được giả định tương đương JSON float; kiểm tra conversion từ string. |
| `""` | Được xử lý theo rule `EmptyString`. |
| `"   "` | Xác nhận `setAcceptBlankAsEmpty` có hiệu lực như mong muốn. |
| `"abc"` | Bị từ chối vì không thể chuyển thành integer. |
| `null` | Xác nhận null handling và kiểu đích. |
| `[]` | Xác nhận policy cho array nếu endpoint có thể nhận cấu trúc sai dạng. |

Khi kiểm tra lỗi, bắt `JsonProcessingException` hoặc exception phù hợp ở tầng gọi để quan sát thông tin path/property. Không nên biến mọi lỗi coercion thành null nếu điều đó làm mất khả năng phát hiện dữ liệu sai.

## 12. Nguyên tắc thiết kế chính sách đầu vào

- Chọn `Fail` cho các trường mà kiểu JSON là một phần nghiêm ngặt của hợp đồng.
- Chọn `TryConvert` khi cần tương thích với nguồn dữ liệu cũ và conversion có ý nghĩa rõ ràng.
- Chọn `AsNull` khi một dạng input cụ thể được định nghĩa là không cung cấp giá trị.
- Chọn `AsEmpty` khi empty value của kiểu đích có ý nghĩa và đã được xác định.
- Phân biệt `String` với `EmptyString`, và kiểm tra riêng chuỗi whitespace.
- Dùng `LogicalType` cho chính sách nhóm, class-level cho ngoại lệ kiểu cụ thể, defaults cho fallback chung.
- Không giả định coercion policy được chọn theo tên property; nếu hai property cùng kiểu cần quy tắc khác nhau, dùng custom deserializer hoặc DTO riêng.
- Phân biệt coercion với `@JsonSetter(nulls = ...)` và các feature xử lý array/scalar.
- Cấu hình mapper trước khi chia sẻ và tái sử dụng; không thay đổi coercion config theo request trên mapper singleton.
- Kiểm tra cả dữ liệu hợp lệ, dữ liệu sai kiểu, empty, null và giá trị biên bằng mapper thực tế của ứng dụng.

## Kết luận

Coercion configuration giúp định nghĩa rõ Jackson phải từ chối, chuyển đổi hay chuẩn hóa một hình dạng JSON đầu vào. `CoercionInputShape` mô tả dữ liệu nhận được, còn `CoercionAction` chọn hành vi `Fail`, `TryConvert`, `AsNull` hoặc `AsEmpty`. Dùng `LogicalType` cho quy tắc chung của một nhóm kiểu, cấu hình theo lớp khi cần ngoại lệ và defaults cho fallback. Khi thiết kế hợp đồng API, hãy chấp nhận conversion có chủ đích, từ chối dữ liệu có nguy cơ mất thông tin và chỉ chuyển input thành null/empty khi ý nghĩa nghiệp vụ đã rõ ràng.
