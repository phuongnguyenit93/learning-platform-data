# Đọc `requestParameters` và chuyển kiểu dữ liệu đầu vào

## Mục tiêu bài học

Khi một flow được mở bằng URL hoặc nhận một request từ trình duyệt, ứng dụng thường cần đọc các giá trị như `productId`, `page`, `sort`, `keyword` hoặc danh sách bộ lọc. Trong Spring Web Flow, biến EL đặc biệt **`requestParameters`** cung cấp cách truy cập các tham số của request hiện tại ngay trong flow definition.

Các tham số HTTP thường đến dưới dạng chuỗi. Vì vậy, đọc được giá trị chưa có nghĩa là đã có đúng kiểu Java. Một ID cần trở thành `Long`, số trang cần thành `Integer`, cờ bật/tắt cần thành `Boolean`, còn một kiểu riêng của ứng dụng cần converter phù hợp.

Bài học này tập trung vào cách đọc request parameter, cách chuyển kiểu có kiểm soát và cách đưa dữ liệu đã được kiểm tra vào đúng scope. Sau bài, bạn có thể:

1. Truy cập `requestParameters` trong Spring EL và dùng nó trong `<set>`, `<evaluate>` hoặc transition action.
2. Phân biệt request parameter với `flowScope`, `requestScope` và flow input.
3. Đọc một giá trị đơn, giá trị có thể vắng mặt và tham số bắt buộc.
4. Chuyển chuỗi thành `Integer`, `Long`, `Boolean`, mảng và kiểu ứng dụng.
5. Hiểu khác biệt giữa tham số không có, chuỗi rỗng và giá trị sai định dạng.
6. Xử lý request có nhiều giá trị cùng tên.
7. Kết hợp `requestParameters` với `ConversionService`, converter, formatter và service parser.
8. Giới hạn dữ liệu được chấp nhận, xác thực quyền và tránh gán hàng loạt thuộc tính từ request.

## 1. `requestParameters` là gì?

`requestParameters` là một **implicit EL variable** do Spring Web Flow cung cấp. Nó cho phép flow đọc các tham số của request client hiện tại.

Ví dụ, trình duyệt mở:

```text
/catalog?category=books&page=2
```

Flow có thể đọc:

```xml
<set name="requestScope.category"
     value="requestParameters.category" />

<set name="requestScope.page"
     value="requestParameters.page"
     type="int" />
```

Trong ví dụ:

- `requestParameters.category` lấy chuỗi `books`.
- `requestParameters.page` lấy chuỗi `2`.
- `type="integer"` yêu cầu Web Flow chuyển giá trị thành kiểu số nguyên trước khi gán.
- Kết quả được lưu vào `requestScope`, tức phạm vi của request flow hiện tại.

Tài liệu Spring Web Flow dùng chính mẫu sau để chuyển một tham số thành `long`:

```xml
<set name="requestScope.hotelId"
     value="requestParameters.id"
     type="long" />
```

Đây là cách ngắn gọn khi muốn đọc một tham số và yêu cầu kiểu đích ngay trong flow definition.

### Request parameter thường đến từ đâu?

Trong môi trường Servlet, request parameter thường bao gồm:

- Tham số trên query string của URL.
- Trường form được submit theo kiểu nội dung mà Servlet container phân tích thành request parameters, chẳng hạn `application/x-www-form-urlencoded`.

Ví dụ:

```text
GET /catalog?keyword=spring&page=3

POST /booking
Content-Type: application/x-www-form-urlencoded

hotelId=42&guestCount=2
```

Ở request đầu, flow có thể đọc `keyword` và `page`. Ở request thứ hai, flow có thể đọc `hotelId` và `guestCount` nếu chúng được gửi trong request hiện tại.

`requestParameters` chỉ phản ánh request đang được xử lý. Nó không tự lưu dữ liệu để dùng ở các request sau của cùng flow.

## 2. Phân biệt request parameter với các scope

Một nhầm lẫn thường gặp là đọc được tham số rồi nghĩ rằng Web Flow sẽ tự giữ nó trong toàn bộ hành trình. Thực tế, `requestParameters` là **nguồn dữ liệu đầu vào của request**, còn scope là **nơi ứng dụng lưu dữ liệu**.

| Thành phần | Vai trò | Vòng đời |
| --- | --- | --- |
| `requestParameters` | Đọc tham số client gửi trong request hiện tại | Theo request đang xử lý |
| `requestScope` | Lưu biến tạm trong request của flow | Khi flow được gọi/xử lý request đó |
| `flowScope` | Lưu dữ liệu cần tồn tại qua nhiều state/request của flow | Từ lúc flow bắt đầu đến khi flow kết thúc |
| `viewScope` | Lưu dữ liệu của một `view-state` | Từ lúc vào state đến khi rời state |
| `conversationScope` | Chia sẻ dữ liệu giữa root flow và subflow | Theo vòng đời top-level flow |

Ví dụ:

```xml
<on-start>
    <set name="flowScope.productId"
         value="requestParameters.productId"
         type="long" />
</on-start>
```

`requestParameters.productId` là dữ liệu đọc từ request khởi tạo flow. `flowScope.productId` là bản sao được giữ lại để những state tiếp theo sử dụng.

Nếu chỉ cần dùng giá trị trong một action của request hiện tại, có thể lưu vào `requestScope`. Nếu cần giữ qua nhiều màn hình, hãy copy sang `flowScope` hoặc một model có vòng đời phù hợp.

### `requestParameters` không phải flow input

Flow input là một phần của contract khi một flow được gọi. Ví dụ:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="hotelId" type="long" required="true" />

    <on-start>
        <evaluate expression="bookingService.createBooking(hotelId)"
                  result="flowScope.booking" />
    </on-start>
</flow>
```

`hotelId` ở đây là input attribute mà caller cung cấp theo cơ chế input mapping của Web Flow. `requestParameters.hotelId` là tham số HTTP được đọc từ request. Hai cơ chế có thể cùng chứa một giá trị nhưng có nguồn và contract khác nhau.

Đừng giả định khai báo `<input name="hotelId"/>` tự động có nghĩa là mọi query parameter `hotelId` đều được map theo cùng cách trong mọi kiểu tích hợp. Nếu cần nhận HTTP parameter, hãy kiểm tra cách `FlowHandler` hoặc tầng gọi flow tạo input map; nếu cần đọc trực tiếp request, dùng `requestParameters`.

## 3. Truy cập tham số bằng Spring EL

Spring Web Flow cung cấp `requestParameters` như một biến EL đặc biệt. Trong thuộc tính nhận **standard expression**, viết biểu thức trực tiếp:

```xml
<set name="flowScope.sortBy"
     value="requestParameters.sortBy" />
```

Không bọc biểu thức bằng `#{...}` trong thuộc tính `value` của `<set>`:

```xml
<!-- Standard expression: đúng -->
<set name="flowScope.sortBy"
     value="requestParameters.sortBy" />
```

Template expression có quy tắc khác: nó dùng `#{...}` khi trộn biểu thức với văn bản tĩnh, chẳng hạn một view ID được tạo động. Đừng áp dụng cú pháp template vào standard expression của `<set>` hoặc `<evaluate>`.

### Đọc bằng cú pháp thuộc tính

```xml
<set name="requestScope.keyword"
     value="requestParameters.keyword" />
```

Cách này ngắn và dễ đọc. Giá trị nhận được là chuỗi tham số.

### Gọi accessor của `ParameterMap`

`requestParameters` được cung cấp dưới dạng `ParameterMap`. Ngoài truy cập theo tên, có thể gọi các accessor:

```xml
<set name="flowScope.page"
     value="requestParameters.getInteger('page', 0)" />

<set name="flowScope.hotelId"
     value="requestParameters.getRequiredLong('hotelId')" />
```

Accessor hữu ích khi muốn chuyển kiểu hoặc đặt giá trị mặc định ngay lúc đọc.

## 4. `ParameterMap`: cấu trúc và các accessor quan trọng

`org.springframework.webflow.core.collection.ParameterMap` là abstraction truy cập request parameter. Parameter map có key dạng chuỗi và value dạng chuỗi; nó cung cấp thêm các phương thức typed để chuyển đổi giá trị.

Các phương thức phổ biến:

| Phương thức | Kết quả | Khi dùng |
| --- | --- | --- |
| `get(name)` | `String`, hoặc `null` nếu không có | Đọc raw value |
| `get(name, defaultValue)` | `String` hoặc default nếu không có | Giá trị chuỗi tùy chọn |
| `contains(name)` | `boolean` | Phân biệt tham số vắng mặt với tham số có mặt |
| `getArray(name)` | `String[]`, hoặc `null` nếu không có | Đọc tham số lặp |
| `get(name, targetType)` | Kiểu đích `T`, hoặc `null` nếu không có | Chuyển kiểu tổng quát |
| `get(name, targetType, defaultValue)` | Kiểu `T` hoặc default nếu không có | Chuyển kiểu có giá trị mặc định |
| `getInteger(name)` | `Integer` | Đọc số nguyên tùy chọn |
| `getLong(name)` | `Long` | Đọc ID số dài tùy chọn |
| `getBoolean(name)` | `Boolean` | Đọc cờ tùy chọn |
| `getNumber(name, targetType)` | Kiểu số đích | Đọc kiểu số cụ thể |
| `getRequired(name)` | `String` | Yêu cầu tham số phải có |
| `getRequired(name, targetType)` | Kiểu `T` | Yêu cầu tham số phải có và chuyển kiểu |
| `getRequiredArray(name)` | `String[]` | Yêu cầu mảng tham số phải có |
| `getRequiredInteger(name)` | `Integer` | Yêu cầu số nguyên hợp lệ |
| `getRequiredLong(name)` | `Long` | Yêu cầu ID `long` hợp lệ |
| `getRequiredBoolean(name)` | `Boolean` | Yêu cầu boolean hợp lệ |
| `getMultipartFile(name)` | `MultipartFile` | Đọc file upload theo cơ chế multipart |

Parameter map là **immutable**: nó đại diện cho các giá trị nhận từ request và không phải nơi để chỉnh sửa request parameter.

### Ví dụ Java

```java
import org.springframework.webflow.core.collection.ParameterMap;

public SearchCriteria parse(ParameterMap parameters) {
    String keyword = parameters.get("keyword", "");
    Integer page = parameters.getInteger("page", 0);
    Integer pageSize = parameters.getInteger("size", 20);
    Boolean includeArchived =
            parameters.getBoolean("archived", Boolean.FALSE);

    // Chuẩn hóa và kiểm tra giới hạn trước khi trả kết quả.
    return new SearchCriteria(
            keyword,
            page,
            pageSize,
            includeArchived);
}
```

`SearchCriteria` là DTO do ứng dụng định nghĩa. Ví dụ giả định các accessor typed có thể chuyển các kiểu cơ bản theo conversion service được sử dụng. Phần giới hạn page và quyền truy cập sẽ được trình bày ở các phần sau.

Vì `SearchCriteria` được lưu trong `flowScope`, với repository mặc định DTO này cần hỗ trợ serialization. Chỉ đưa vào nó các giá trị nhỏ, ổn định như chuỗi, số và danh sách mã; không giữ connection, `EntityManager`, request object hoặc resource đang mở.

## 5. Chuyển kiểu ngay trong flow bằng thuộc tính `type`

Action `<set>` hỗ trợ thuộc tính `type` để yêu cầu chuyển giá trị biểu thức sang kiểu đích trước khi gán.

```xml
<set name="requestScope.productId"
     value="requestParameters.productId"
     type="long" />

<set name="requestScope.page"
     value="requestParameters.page"
     type="integer" />

<set name="requestScope.includeArchived"
     value="requestParameters.archived"
     type="boolean" />
```

Các tên kiểu thông dụng như `long`, `int` và `boolean` giúp flow definition thể hiện rõ dữ liệu đích.

### Dùng kiểu wrapper khi tham số có thể vắng mặt

Nếu giá trị có thể không được gửi, kiểu tham chiếu như `Long` hoặc `Integer` thường phù hợp hơn primitive `long` hoặc `int`, vì giá trị có thể là `null`. Khi cần hành vi rõ ràng, dùng accessor typed trả về wrapper hoặc accessor có default thay vì ép một giá trị có thể vắng mặt sang primitive.

### Dùng accessor typed để có default rõ ràng

```xml
<set name="flowScope.page"
     value="requestParameters.getInteger('page', 0)" />

<set name="flowScope.pageSize"
     value="requestParameters.getInteger('size', 20)" />

<set name="flowScope.includeArchived"
     value="requestParameters.getBoolean('archived', false)" />
```

Như vậy:

- Không gửi `page` thì dùng `0`.
- Không gửi `size` thì dùng `20`.
- Không gửi `archived` thì dùng `false`.
- Nếu tham số có mặt nhưng không chuyển được sang kiểu đích, conversion vẫn có thể thất bại; default chỉ xử lý trường hợp không có tham số.

## 6. Phân biệt tham số thiếu, rỗng và sai định dạng

Ba tình huống này không giống nhau:

| Request | `contains("page")` | `get("page")` | Ý nghĩa |
| --- | --- | --- | --- |
| Không gửi `page` | `false` | `null` | Tham số không tồn tại |
| Gửi `page=` | `true` | `""` | Có tham số nhưng chuỗi rỗng |
| Gửi `page=abc` | `true` | `"abc"` | Có chuỗi nhưng không phải số nguyên |
| Gửi `page=3` | `true` | `"3"` | Có chuỗi có thể chuyển thành số nguyên |

### 6.1. Dùng `contains` khi cần phân biệt vắng mặt

```java
if (!parameters.contains("page")) {
    // Chưa cung cấp page: áp dụng mặc định.
} else {
    // Có page: cần xử lý cả trường hợp rỗng hoặc sai định dạng.
}
```

`contains` chỉ kiểm tra sự hiện diện. Nó không kiểm tra chuỗi có nội dung hợp lệ hay không.

### 6.2. `getRequired` kiểm tra sự hiện diện, không thay validation nghiệp vụ

```java
String hotelId = parameters.getRequired("hotelId");
```

Phương thức required ném `IllegalArgumentException` nếu tham số không được tìm thấy. Nếu cần chuyển kiểu:

```java
Long hotelId = parameters.getRequiredLong("hotelId");
```

Accessor typed required có thể ném:

- `IllegalArgumentException` nếu tham số không có.
- `ConversionExecutionException` nếu giá trị không chuyển được.

`getRequired` không thay thế kiểm tra chuỗi rỗng, độ dài, miền giá trị hoặc quy tắc nghiệp vụ. Nếu bắt buộc một chuỗi không trắng, vẫn cần kiểm tra `isBlank()` hoặc dùng validator.

### 6.3. Không biến input sai thành default âm thầm

Ví dụ:

```text
?page=abc
```

Nếu ứng dụng biến mọi lỗi parse thành `page=0`, người dùng sẽ thấy trang đầu và khó biết request đã sai. Với các trường quan trọng, nên báo lỗi đầu vào rõ ràng hoặc trả response phù hợp.

Default có ý nghĩa khi **tham số không được gửi**. Nó không nên che lỗi khi người dùng gửi một giá trị sai định dạng.

## 7. Đọc tham số nhiều giá trị

HTML có thể gửi nhiều giá trị cùng tên, chẳng hạn checkbox hoặc bộ lọc nhiều lựa chọn:

```html
<input type="checkbox" name="tag" value="spring">
<input type="checkbox" name="tag" value="java">
<input type="checkbox" name="tag" value="web">
```

Request có thể chứa:

```text
tag=spring&tag=java&tag=web
```

Không nên dùng accessor chuỗi đơn rồi giả định nó giữ toàn bộ các giá trị. Dùng `getArray(...)`:

```java
String[] tags = parameters.getArray("tag");

if (tags == null) {
    tags = new String[0];
}
```

Nếu cần chuyển từng phần tử:

```java
Long[] selectedIds =
        parameters.getArray("selectedId", Long.class);
```

Với tham số bắt buộc:

```java
String[] requiredTags =
        parameters.getRequiredArray("tag");
```

`getArray(name)` trả về `null` nếu không có tham số. Nếu chỉ có một giá trị, nó vẫn trả về mảng một phần tử.

### Kiểm tra số lượng và phần tử

```java
String[] rawIds = parameters.getArray("selectedId");

if (rawIds == null || rawIds.length == 0) {
    return List.of();
}

if (rawIds.length > 50) {
    throw new InvalidSearchRequestException(
            "Chỉ được chọn tối đa 50 mục");
}

List<Long> ids = Arrays.stream(rawIds)
        .map(Long::valueOf)
        .toList();
```

Đoạn Java trên minh họa kiểm tra giới hạn trước khi xử lý. Trong code thực tế, nên dùng conversion service hoặc parser có kiểm soát để lỗi phần tử không hợp lệ được ánh xạ thành lỗi request dễ hiểu.

### Khi một tham số vốn chỉ được phép có một giá trị

Nếu nghiệp vụ yêu cầu `accountId` chỉ xuất hiện đúng một lần, hãy kiểm tra số phần tử:

```java
String[] values = parameters.getArray("accountId");

if (values == null || values.length != 1) {
    throw new InvalidSearchRequestException(
            "accountId phải xuất hiện đúng một lần");
}
```

Điều này giúp phát hiện request có tham số trùng tên thay vì để ứng dụng vô tình chọn một giá trị theo hành vi của container hoặc tầng chuyển đổi.

## 8. Ví dụ hoàn chỉnh: khởi tạo bộ lọc catalog từ URL

Giả sử flow catalog hỗ trợ URL:

```text
/catalog?keyword=spring&page=2&size=20&tag=java&tag=web
```

Flow cần:

- Đọc `keyword` dạng chuỗi.
- Chuyển `page` thành số nguyên.
- Chuyển `size` thành số nguyên và giới hạn tối đa.
- Đọc nhiều giá trị `tag`.
- Lưu tiêu chí trong flow scope để dùng qua các state.
- Dùng service truy vấn và kiểm tra quyền.

### 8.1. XML flow

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="catalogRequestParser.parse(requestParameters)"
                  result="flowScope.searchCriteria" />
    </on-start>

    <view-state id="showCatalog" view="catalog/results">
        <on-render>
            <evaluate expression="catalogQueryService.search(searchCriteria)"
                      result="viewScope.searchResult" />
        </on-render>

        <transition on="nextPage">
            <evaluate expression="searchCriteria.nextPage()" />
            <render fragments="resultList,pagination" />
        </transition>

        <transition on="previousPage">
            <evaluate expression="searchCriteria.previousPage()" />
            <render fragments="resultList,pagination" />
        </transition>

        <transition on="clearFilters" to="clearSearch" bind="false" />
    </view-state>

    <action-state id="clearSearch">
        <evaluate expression="catalogRequestParser.emptyCriteria()"
                  result="flowScope.searchCriteria" />
        <transition to="showCatalog" />
    </action-state>
</flow>
```

Ví dụ dùng `catalogRequestParser` để gom logic đọc và kiểm tra tham số. `searchCriteria` nằm trong `flowScope`, vì nó cần sống qua các request phân trang. `searchResult` chỉ phục vụ view hiện tại nên nằm trong `viewScope`.

### 8.2. Parser nhận `ParameterMap`

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.stereotype.Component;
import org.springframework.webflow.core.collection.ParameterMap;

@Component("catalogRequestParser")
public class CatalogRequestParser {

    public SearchCriteria parse(ParameterMap parameters) {
        String keyword = parameters.get("keyword", "").trim();
        Integer page = parameters.getInteger("page", 0);
        Integer requestedSize = parameters.getInteger("size", 20);
        String[] rawTags = parameters.getArray("tag");

        if (page < 0) {
            throw new InvalidSearchRequestException(
                    "page không được âm");
        }

        int safeSize = Math.min(Math.max(requestedSize, 1), 50);

        List<String> tags = rawTags == null
                ? List.of()
                : Arrays.stream(rawTags)
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .limit(20)
                        .toList();

        return new SearchCriteria(
                keyword,
                page,
                safeSize,
                tags);
    }

    public SearchCriteria emptyCriteria() {
        return new SearchCriteria("", 0, 20, List.of());
    }
}
```

`SearchCriteria` và `InvalidSearchRequestException` là kiểu do ứng dụng định nghĩa. Ví dụ giả định `getInteger` trả default nếu thiếu, còn giá trị có mặt nhưng sai định dạng sẽ làm conversion thất bại. Nếu ứng dụng muốn hiển thị lỗi form thay vì exception, hãy bắt lỗi conversion tại parser/action adapter và chuyển thành lỗi đầu vào có thông báo phù hợp.

Vì `SearchCriteria` được lưu trong `flowScope`, với repository mặc định DTO này cần hỗ trợ serialization. Chỉ lưu dữ liệu tiêu chí cần thiết; không giữ connection, `EntityManager`, request object hoặc resource đang mở.

### 8.3. Vì sao không đọc mọi tham số rồi gán vào model?

Parser chỉ lấy bốn tham số mà chức năng catalog cần. Những tham số như `role`, `ownerId`, `price`, `tenantId` hoặc `isAdmin` không được tự động sao chép vào DTO. Điều này giảm nguy cơ mass assignment và làm contract đầu vào rõ ràng.

## 9. Chuyển kiểu sang kiểu dữ liệu riêng của ứng dụng

`ParameterMap` hỗ trợ các kiểu thông dụng như `String`, các lớp số, `Boolean` và có accessor tổng quát:

```java
CustomerCode code =
        parameters.get("customerCode", CustomerCode.class);
```

Để chuyển kiểu riêng, conversion service mà parameter map sử dụng phải có converter tương ứng. Ví dụ Spring Core converter:

```java
import org.springframework.core.convert.converter.Converter;

public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        return new CustomerCode(source.trim());
    }
}
```

Đăng ký converter trong conversion service được Web Flow sử dụng. Khi gọi `parameters.get("customerCode", CustomerCode.class)`, `ParameterMap` có thể yêu cầu conversion service chuyển chuỗi sang kiểu đích.

### Không phải mọi kiểu đều nên chuyển trực tiếp trong EL

Một `UUID` có format cố định có thể phù hợp với converter. Một ngày theo locale người dùng có thể cần `Formatter`. Một mã sản phẩm cần tra database để xác nhận tồn tại thì nên qua service nghiệp vụ, không nên nhét truy vấn vào converter.

Phân loại:

| Dữ liệu | Cách xử lý |
| --- | --- |
| `Integer`, `Long`, `Boolean` | Accessor typed của `ParameterMap` hoặc `type` trong `<set>` |
| `UUID` | Converter chuẩn hoặc converter đã đăng ký |
| Enum | Converter/ConversionService theo quy tắc ứng dụng |
| `LocalDate` với ISO | Formatter/conversion service hỗ trợ `java.time` |
| Ngày theo locale tùy người dùng | Formatter hoặc parser nhận locale rõ ràng |
| ID cần kiểm tra tồn tại và quyền | Service truy vấn/authorization |
| Giá tiền có currency | Parser/formatter có locale và currency rõ ràng; service kiểm tra nghiệp vụ |

### Lưu ý về `@DateTimeFormat`

`@DateTimeFormat` gắn với metadata của một field/property khi Web Flow bind model. Khi gọi trực tiếp:

```java
parameters.get("date", LocalDate.class)
```

không có một field cụ thể để Spring đọc annotation. Do đó, đừng giả định annotation trên một DTO bất kỳ tự động quyết định format cho accessor `ParameterMap`. Với tham số đầu vào có format riêng, hãy dùng formatter/converter được đăng ký phù hợp hoặc parser bean có quy tắc rõ ràng.

## 10. `requestParameters` và binding tự động của `view-state`

`requestParameters` cho phép flow đọc trực tiếp tham số. Nhưng nếu người dùng gửi form gắn với một model, Web Flow thường có thể bind tự động thông qua `view-state model`.

Ví dụ:

```xml
<view-state id="editBooking"
            view="booking/edit"
            model="booking">
    <binder>
        <binding property="guestCount" required="true" />
        <binding property="arrivalDate" required="true" />
    </binder>
    <transition on="review" to="reviewBooking" />
</view-state>
```

Ở đây, Web Flow tự bind field được khai báo vào `booking`. Không cần viết thêm:

```xml
<set name="booking.guestCount"
     value="requestParameters.guestCount"
     type="integer" />
```

cho cùng một field nếu binding model đã làm việc đó. Việc đọc thủ công có thể tạo hai đường xử lý khác nhau, khiến conversion hoặc validation bị lặp.

### Khi nào nên đọc trực tiếp `requestParameters`?

- Khởi tạo bộ lọc từ query string khi bắt đầu flow.
- Đọc một tham số điều hướng không thuộc form model.
- Lấy một event-specific value cần dùng trong action.
- Xử lý tham số nhiều giá trị.
- Map dữ liệu đầu vào qua một parser chuyên biệt trước khi đưa vào flow scope.

### Khi nào nên dùng model binding?

- Form có nhiều field thuộc một DTO.
- Cần binding whitelist qua `<binder>`.
- Cần validation theo `view-state`.
- Cần thông báo lỗi gắn với từng field.
- Cần giữ model qua các bước và cho phép người dùng sửa.

## 11. Phạm vi của request parameter và dữ liệu qua nhiều request

Một flow thường được tiếp tục bằng nhiều HTTP request. Khi người dùng nhấn Next, Back hoặc phân trang, mỗi lần gửi lại là một request mới. Không nên giả định query parameter ở URL khởi tạo sẽ tự xuất hiện trong mọi request tiếp theo.

Ví dụ:

```text
Request 1:
  /catalog?keyword=spring&page=2

Request 2:
  POST /catalog
  _eventId=nextPage
  _flowExecutionKey=...
```

Request thứ hai có thể không gửi lại `keyword` hoặc `page` như query string ban đầu. Nếu cần tiếp tục sử dụng chúng, hãy copy vào `flowScope` khi bắt đầu hoặc bind vào model của view.

```xml
<on-start>
    <set name="flowScope.keyword"
         value="requestParameters.get('keyword', '')" />
    <set name="flowScope.page"
         value="requestParameters.getInteger('page', 0)" />
</on-start>
```

`on-start` chỉ chạy khi flow bắt đầu, nên đây là nơi phù hợp để nhận giá trị khởi tạo. Các request sau dùng dữ liệu đã lưu trong flow scope.

Nếu cần cập nhật filter khi người dùng submit form, hãy bind model hoặc đọc parameter trong transition tương ứng; đừng chạy lại logic khởi tạo ban đầu ở mọi request.

## 12. Bảo mật khi đọc dữ liệu do client gửi

`requestParameters` là dữ liệu **không đáng tin cậy**. Người dùng có thể sửa URL, gửi request bằng công cụ khác hoặc thêm tham số không xuất hiện trên giao diện.

### 12.1. Chỉ đọc các tham số được phép

Không nên copy toàn bộ map sang model:

```java
// Không nên: biến mọi tham số client thành thuộc tính model.
bookingForm.setProperties(requestParameters.asMap());
```

Thay vào đó, lấy đúng những field cần:

```java
Long hotelId = parameters.getRequiredLong("hotelId");
Integer guestCount = parameters.getRequiredInteger("guestCount");
```

Và dùng service kiểm tra hotel có tồn tại, người dùng có quyền đặt, số khách có nằm trong giới hạn và còn phòng hay không.

### 12.2. Không tin ID chỉ vì đã chuyển thành `Long`

`hotelId=42` chuyển thành `Long` thành công chỉ chứng minh chuỗi có thể parse thành số. Nó không chứng minh:

- Hotel 42 tồn tại.
- Người dùng có quyền xem hoặc đặt hotel đó.
- Hotel thuộc tenant của người dùng.
- Hotel đang mở đặt phòng.
- Giá và sức chứa do client gửi là chính xác.

Kiểu dữ liệu hợp lệ không đồng nghĩa dữ liệu nghiệp vụ hợp lệ.

### 12.3. Không nhận vai trò hoặc quyền từ request

Không dùng các tham số như:

```text
?isAdmin=true
?role=ADMIN
?ownerId=another-user
?approved=true
```

làm nguồn quyền đáng tin cậy. Lấy người dùng từ security context (`currentUser`/`Principal`) và kiểm tra quyền ở service.

### 12.4. Giới hạn độ dài, số lượng và miền giá trị

- Giới hạn keyword và chuỗi đầu vào.
- Giới hạn `pageSize` tối đa.
- Không nhận mảng ID không giới hạn.
- Kiểm tra số âm, overflow và giá trị ngoài phạm vi.
- Xác thực enum/zone/locale theo allow-list khi cần.
- Chống truy vấn quá tốn kém bằng pagination và giới hạn filter.

### 12.5. Request parameter không thay thế CSRF protection

Việc một event hoặc tham số có mặt trong `requestParameters` không chứng minh request hợp lệ. Với thao tác thay đổi dữ liệu, ứng dụng vẫn cần cấu hình bảo vệ CSRF và xác thực người dùng theo kiến trúc Spring Security/Web Flow.

### 12.6. Cẩn thận với URL redirect

Nếu flow nhận `returnUrl`, đừng redirect trực tiếp tới giá trị tùy ý. Hãy kiểm tra host/path theo allow-list hoặc chỉ nhận một mã đích đã định nghĩa trong ứng dụng để tránh open redirect.

## 13. Lỗi chuyển đổi và cách xử lý

Typed accessor có thể thất bại khi chuỗi không chuyển được:

```text
?page=two
```

Nếu gọi:

```java
Integer page = parameters.getInteger("page");
```

thì `ConversionExecutionException` có thể được ném ra. Với `getRequiredInteger`, còn có `IllegalArgumentException` khi tham số không tồn tại.

### Phân biệt lỗi đầu vào

| Tình huống | Ví dụ | Xử lý phù hợp |
| --- | --- | --- |
| Thiếu tham số tùy chọn | Không có `page` | Dùng default |
| Thiếu tham số bắt buộc | Không có `hotelId` | Trả lỗi request hoặc state thông báo |
| Chuỗi rỗng | `page=` | Xử lý như input rỗng theo contract |
| Sai kiểu | `page=abc` | Báo lỗi chuyển đổi |
| Ngoài miền giá trị | `page=-100` | Validation/rule kiểm tra miền |
| ID hợp lệ nhưng không tồn tại | `hotelId=999999` | Service trả not-found |
| ID tồn tại nhưng không có quyền | `hotelId=42` | Service/security từ chối |

### Tạo parser để gom lỗi đầu vào

Nếu có nhiều tham số hoặc format phức tạp, hãy tạo bean chuyên biệt:

```java
@Component("bookingRequestParser")
public class BookingRequestParser {

    public BookingRequest parse(ParameterMap parameters) {
        try {
            Long hotelId =
                    parameters.getRequiredLong("hotelId");
            Integer guestCount =
                    parameters.getRequiredInteger("guestCount");

            if (guestCount < 1 || guestCount > 8) {
                throw new InvalidBookingRequestException(
                        "Số khách phải từ 1 đến 8");
            }

            return new BookingRequest(hotelId, guestCount);
        } catch (ConversionExecutionException ex) {
            throw new InvalidBookingRequestException(
                    "Tham số có định dạng không hợp lệ", ex);
        } catch (IllegalArgumentException ex) {
            throw new InvalidBookingRequestException(
                    "Thiếu tham số bắt buộc", ex);
        }
    }
}
```

`BookingRequest` và `InvalidBookingRequestException` là kiểu ứng dụng tự định nghĩa. Trong code thực tế, cần phân biệt exception do `guestCount` ngoài miền với exception do thiếu tham số để đưa thông báo phù hợp.

Trong ví dụ, `InvalidBookingRequestException` nên kế thừa `RuntimeException` thay vì `IllegalArgumentException`, để lỗi do rule `guestCount` không bị nhầm với lỗi thiếu tham số trong khối `catch`.

Gọi parser trong flow:

```xml
<on-start>
    <evaluate expression="bookingRequestParser.parse(requestParameters)"
              result="flowScope.bookingRequest" />
</on-start>
```

Nếu parser ném exception nghiệp vụ, hãy cấu hình exception handling phù hợp hoặc xử lý tại action adapter để điều hướng tới state báo lỗi. Đừng để người dùng cuối nhận stack trace.

## 14. Chuyển đổi kiểu tùy chỉnh và `ConversionService`

`ParameterMap` có thể chuyển chuỗi sang target type thông qua conversion service. Với kiểu ứng dụng, đăng ký Spring Core converter hoặc formatter trong conversion service mà Web Flow sử dụng.

Ví dụ value object:

```java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Mã khách hàng không được để trống");
        }
    }
}
```

Converter:

```java
import org.springframework.core.convert.converter.Converter;

public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null || source.isBlank()) {
            return null;
        }
        return new CustomerCode(source.trim());
    }
}
```

Sau khi converter được đăng ký trong service được Web Flow dùng:

```java
CustomerCode code =
        parameters.get("customerCode", CustomerCode.class);
```

Nếu converter không được đăng ký đúng service, việc gọi typed accessor có thể thất bại. Kiểm tra `flow-builder-services` và conversion service của ứng dụng khi MVC chuyển được nhưng Web Flow không chuyển được.

### Dùng formatter cho chuỗi phụ thuộc locale

Với `LocalDate`, `BigDecimal` hoặc dữ liệu hiển thị theo locale, `Formatter<T>` phù hợp hơn converter một chiều. Tuy nhiên, `ParameterMap.get(name, targetType)` không nhận tham số `Locale` trực tiếp. Nếu format thay đổi theo locale, parser bean có thể nhận thêm locale hiện tại từ `flowRequestContext`/`externalContext` và gọi formatter rõ ràng, hoặc dùng model binding với annotation/formatter đã cấu hình.

Không tự đoán format từ chuỗi. Ví dụ `03/04/2026` có thể là ngày 3 tháng 4 hoặc ngày 4 tháng 3 tùy quy ước. Hãy định nghĩa contract input rõ ràng.

## 15. Ví dụ truy cập tham số trong transition

Ngoài lúc khởi tạo flow, `requestParameters` có thể được đọc trong action của transition. Ví dụ một màn hình danh sách có link mở chi tiết:

```xml
<view-state id="showCatalog" view="catalog/results">
    <transition on="openProduct" to="showProduct">
        <set name="flowScope.selectedProductId"
             value="requestParameters.productId"
             type="long" />
    </transition>
</view-state>

<view-state id="showProduct" view="catalog/product">
    <on-render>
        <evaluate expression="productQueryService.findVisibleProduct(selectedProductId)"
                  result="viewScope.product" />
    </on-render>
    <transition on="back" to="showCatalog" />
</view-state>
```

Ví dụ giả định request gửi `productId` cùng event `openProduct`. Nếu dùng named HTML button hoặc link để phát event, cách tạo event parameter phụ thuộc view technology và cách tích hợp Web Flow. Hãy kiểm tra request thực tế trong integration test.

`findVisibleProduct(...)` phải kiểm tra quyền truy cập ở service. Việc `productId` đã chuyển thành `long` không chứng minh người dùng được phép xem sản phẩm.

### Dùng giá trị event khi dữ liệu nằm trong `currentEvent`

Nếu dữ liệu được gắn vào event attributes bởi một action hoặc custom event handler, nguồn phù hợp có thể là `currentEvent.attributes`, không phải `requestParameters`.

Ví dụ:

```xml
<evaluate expression="booking.guests.add(currentEvent.attributes.guest)" />
```

`requestParameters` đọc tham số client của request. `currentEvent.attributes` đọc dữ liệu được gắn vào event hiện tại. Hãy chọn đúng nguồn thay vì giả định mọi giá trị liên quan tới nút bấm đều nằm ở cùng một map.

## 16. Kiểm thử đọc request và chuyển kiểu

Nên kiểm thử cả API `ParameterMap`, biểu thức flow và hành vi HTTP thực tế.

| Kịch bản | Request | Kết quả mong đợi |
| --- | --- | --- |
| Tham số chuỗi | `?keyword=spring` | `requestParameters.keyword` là `spring` |
| Tham số số hợp lệ | `?page=2` | Chuyển thành `Integer(2)` |
| Tham số boolean | `?archived=true` | Chuyển thành `Boolean` theo conversion service |
| Tham số thiếu tùy chọn | Không có `page` | Accessor default trả giá trị mặc định |
| Tham số thiếu bắt buộc | Không có `hotelId` | Required accessor báo thiếu |
| Chuỗi rỗng | `?page=` | Phân biệt có mặt nhưng rỗng |
| Sai định dạng số | `?page=abc` | Conversion error |
| Số âm | `?page=-1` | Parser/validator từ chối theo rule |
| Nhiều giá trị | `?tag=java&tag=web` | `getArray("tag")` trả đủ hai phần tử |
| Không có mảng | Không có `tag` | `getArray("tag")` trả `null` |
| Mảng typed | `?id=10&id=20` | Chuyển từng phần tử theo target type |
| Tham số trùng scalar | `?accountId=1&accountId=2` | Parser phát hiện nếu nghiệp vụ chỉ cho một giá trị |
| Kiểu tùy chỉnh | `?customerCode=AB-123` | Converter được đăng ký và được Web Flow dùng |
| Query khởi tạo flow | `?keyword=spring` | Dữ liệu được copy vào flow scope |
| Request tiếp theo không gửi lại query | POST event phân trang | Flow vẫn dùng tiêu chí đã lưu trong flow scope |
| ID không có quyền | `?productId=42` | Service từ chối truy cập dù parse thành công |
| Giá trị quá lớn | `?size=999999` | Parser giới hạn hoặc từ chối |
| URL encoding | `?keyword=spring%20flow` | Nhận giá trị đã được decode đúng |

### 16.1. Unit test parser

```java
@Test
void appliesDefaultsWhenOptionalParametersAreMissing() {
    ParameterMap parameters =
            new LocalParameterMap(Map.of("keyword", "spring"));

    SearchCriteria criteria = parser.parse(parameters);

    assertEquals("spring", criteria.keyword());
    assertEquals(0, criteria.page());
    assertEquals(20, criteria.pageSize());
}
```

Test trên là ví dụ với `SearchCriteria` dạng record. Trong dự án thật, tạo fixture `ParameterMap` và parser theo constructor thực tế; bổ sung test cho chuỗi rỗng, giá trị sai kiểu và nhiều giá trị.

### 16.2. Test typed accessors

```java
@Test
void convertsIntegerParameter() {
    ParameterMap parameters =
            new LocalParameterMap(Map.of("page", "3"));

    assertEquals(Integer.valueOf(3),
            parameters.getInteger("page"));
}
```

Kiểm thử thêm:

- `getRequiredLong` khi thiếu tham số.
- `getInteger` khi chuỗi không phải số.
- `getArray` với một và nhiều phần tử.
- `getArray(name, Long.class)` khi có phần tử sai.

### 16.3. Test flow integration

Với test support của Spring Web Flow:

1. Khởi chạy flow qua request có query parameter.
2. Xác nhận `on-start` đọc đúng `requestParameters`.
3. Xác nhận giá trị đã chuyển kiểu và được lưu vào `flowScope`.
4. Gửi request tiếp theo không có query parameter ban đầu.
5. Xác nhận flow vẫn sử dụng dữ liệu đã lưu.
6. Gửi input sai kiểu và xác nhận exception/error path phù hợp.
7. Kiểm tra event và request parameters không bị nhầm lẫn.

Unit test parser không thay thế integration test. Cần xác nhận EL parser, flow execution và servlet integration thực sự cung cấp parameter map như dự kiến.

## 17. Các lỗi thường gặp

### 17.1. Đọc được chuỗi nhưng model cần số

**Triệu chứng:** model nhận `String` hoặc expression báo sai kiểu.

**Nguyên nhân:** đọc `requestParameters.id` nhưng không chỉ định kiểu đích.

**Khắc phục:** dùng `type="long"`, `getLong(...)`, `getRequiredLong(...)` hoặc parser có kiểu trả về rõ ràng.

### 17.2. Dữ liệu biến mất ở request tiếp theo

**Nguyên nhân:** giá trị chỉ được đọc từ request hiện tại hoặc lưu trong `requestScope`.

**Khắc phục:** copy giá trị cần giữ sang `flowScope` hoặc model phù hợp.

### 17.3. Tham số thiếu bị coi là chuỗi rỗng

**Nguyên nhân:** không phân biệt `contains`, `get` và giá trị `""`.

**Khắc phục:** kiểm tra sự hiện diện và nội dung riêng; áp dụng default chỉ khi đúng contract.

### 17.4. `getRequired` nhưng vẫn nhận chuỗi rỗng

**Nguyên nhân:** required accessor kiểm tra tham số có tồn tại, không thay kiểm tra non-blank.

**Khắc phục:** sau khi lấy chuỗi, kiểm tra `isBlank()` hoặc dùng validator.

### 17.5. Một tham số có nhiều giá trị nhưng chỉ đọc một

**Nguyên nhân:** dùng accessor đơn thay vì `getArray`.

**Khắc phục:** dùng `getArray`/`getRequiredArray`, kiểm tra số lượng và chuyển từng phần tử.

### 17.6. Conversion error bị che bởi default

**Nguyên nhân:** code bắt mọi lỗi rồi đặt về `0` hoặc giá trị mặc định.

**Khắc phục:** chỉ default khi tham số vắng mặt; báo lỗi khi tham số có mặt nhưng sai kiểu.

### 17.7. Custom converter chạy trong MVC nhưng không chạy trong Web Flow

**Nguyên nhân:** hai thành phần dùng conversion service khác nhau.

**Khắc phục:** cấu hình `flow-builder-services` để Web Flow dùng service chứa converter cần thiết.

### 17.8. `requestParameters` được dùng để cấp quyền

**Nguyên nhân:** tin `role`, `ownerId`, `tenantId` hoặc `approved` do client gửi.

**Khắc phục:** lấy principal từ security context và kiểm tra quyền tại service.

### 17.9. Gán toàn bộ request map vào entity

**Nguyên nhân:** dùng mass assignment, không có allow-list.

**Khắc phục:** chỉ đọc các tham số được phép hoặc dùng `<binder>` whitelist cho model binding.

### 17.10. Nhầm flow input với query parameter

**Nguyên nhân:** nghĩ `<input name="id"/>` luôn tương đương `requestParameters.id`.

**Khắc phục:** xác định dữ liệu được truyền qua flow input mapping hay HTTP request; viết mapping rõ ràng nếu cần chuyển từ tầng gọi flow.

## 18. Bài tập thực hành

Bạn được giao xây dựng flow xem báo cáo:

```text
openReport → showReport → exportReport → completed
```

Request khởi tạo có thể gồm:

```text
?reportId=42&year=2026&month=5&format=csv&department=engineering
```

Yêu cầu:

1. Đọc `reportId` thành `Long`.
2. Đọc `year` và `month` thành `Integer`.
3. Đọc `format` thành enum `ExportFormat`.
4. Đọc `department` thành chuỗi và xác thực theo danh sách phòng ban người dùng được xem.
5. Copy các giá trị cần giữ vào `flowScope`.
6. Dùng service kiểm tra report tồn tại và người dùng có quyền truy cập.
7. Giới hạn năm, tháng và loại export.
8. Không tin `department` hoặc `reportId` chỉ vì conversion thành công.
9. Khi export, không để request parameter trực tiếp quyết định đường dẫn file tùy ý.

**Nhiệm vụ:**

- Viết XML dùng `requestParameters` trong `<on-start>`.
- Viết parser nhận `ParameterMap`.
- Đăng ký converter cho `ExportFormat` nếu cần.
- Viết test cho thiếu `reportId`, `month=13`, `format=unknown`, department không được phép và request có `reportId` lặp.
- Giải thích dữ liệu nào cần ở `requestScope` và dữ liệu nào phải chuyển vào `flowScope`.

## 19. Ghi nhớ

- `requestParameters` là implicit EL variable để đọc tham số client của request hiện tại.
- Giá trị thô thường là chuỗi; dùng `<set type="...">` hoặc accessor typed để chuyển kiểu.
- `ParameterMap` cung cấp `get`, `contains`, `getArray`, `getInteger`, `getLong`, `getBoolean`, `getRequired...` và accessor tổng quát theo target type.
- `get` trả `null` nếu không có; `contains` phân biệt tham số vắng mặt; chuỗi rỗng là một trường hợp riêng.
- `getRequired...` có thể báo lỗi khi thiếu tham số; typed accessor có thể báo `ConversionExecutionException` khi chuyển kiểu thất bại.
- Dùng `getArray` cho tham số nhiều giá trị và kiểm tra số lượng khi field chỉ được phép có một giá trị.
- `requestParameters` là nguồn dữ liệu; `requestScope`/`flowScope` là nơi lưu dữ liệu. Copy sang `flowScope` nếu cần dùng qua nhiều request.
- Flow input là contract riêng giữa caller và flow; không đồng nhất nó với HTTP request parameter.
- Model binding qua `view-state` phù hợp với form DTO và binder allow-list; không cần đọc thủ công lại cùng field.
- Mọi request parameter đều do client kiểm soát. Chuyển kiểu thành công không chứng minh giá trị tồn tại, hợp lệ hay được phép truy cập.

### Tài liệu tham khảo

- [Spring Web Flow 3.0.2 Reference Guide — The `requestParameters` Variable](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#requestParameters-variable): biến EL đặc biệt dùng để truy cập request parameter.
- [Spring Web Flow 3.0.2 Reference Guide — Special EL Variables](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#special-el-variables): các biến scope và quy tắc sử dụng biến trong flow.
- [Spring Web Flow 3.0.1 API — `ParameterMap`](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/core/collection/ParameterMap.html): accessor chuỗi, typed, required và mảng.
- [Spring Web Flow 3.0.1 API — `LocalParameterMap`](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/core/collection/LocalParameterMap.html): parameter map immutable và chuyển kiểu qua conversion service.
- [Spring Web Flow 3.0.2 Reference Guide — Input/Output Mapping](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#input-output-mapping): phân biệt flow input/output với request parameter.
- [Spring Web Flow 3.0.2 Reference Guide — Specifying Bindings Explicitly](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/#specifying-bindings-explicitly): giới hạn field được bind vào model.
