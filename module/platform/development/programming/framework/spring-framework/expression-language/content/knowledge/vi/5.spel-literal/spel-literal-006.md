# Literal inline collection và kiểu phần tử trong SpEL

## 1. Inline collection là gì?

Spring Expression Language (SpEL) cho phép khai báo trực tiếp một collection ngay trong chuỗi biểu thức. Cú pháp này hữu ích khi cần truyền một danh sách cố định, mô tả cấu hình dạng key/value, tạo dữ liệu lồng nhau hoặc cung cấp tập giá trị cho một phép tính.

SpEL có hai dạng inline collection chính:

- **Inline list** dùng cặp dấu ngoặc nhọn với các phần tử phân tách bằng dấu phẩy: `{value1, value2, value3}`.
- **Inline map** dùng cặp dấu ngoặc nhọn với các cặp khóa và giá trị: `{key1:value1, key2:value2}`.

Kết quả của inline list là một đối tượng thuộc kiểu `List`; kết quả của inline map là một đối tượng thuộc kiểu `Map`. Cả hai đều có thể chứa biểu thức con, giá trị literal, collection lồng nhau hoặc giá trị được lấy từ EvaluationContext.

Điểm cần nhớ về kiểu dữ liệu: cú pháp inline collection không khai báo generic type như `List<String>` hay `Map<String, Integer>`. Kiểu của từng phần tử, khóa và giá trị được quyết định bởi kết quả đánh giá của biểu thức tương ứng.

## 2. Khởi tạo parser và EvaluationContext

Có thể đánh giá inline collection bằng API SpEL độc lập. Ví dụ sau dùng `SpelExpressionParser` và `StandardEvaluationContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

List<?> levels = parser.parseExpression("{'LOW', 'MEDIUM', 'HIGH'}")
        .getValue(context, List.class);

Map<?, ?> settings = parser.parseExpression(
        "{enabled:true, retries:3, 'service.name':'catalog'}")
        .getValue(context, Map.class);
```

`getValue(context, List.class)` yêu cầu kết quả có kiểu ngoài cùng là `List`; nó không khai báo kiểu generic cho từng phần tử. Tương tự, `Map.class` không chỉ định kiểu của key hoặc value.

Trong ứng dụng Spring, biểu thức cũng có thể xuất hiện trong cấu hình như `@Value`. Khi đó, `#{...}` là dấu phân định một SpEL expression, còn dấu ngoặc nhọn bên trong biểu thức là cú pháp inline collection:

```java
@Value("#{ {'READ', 'WRITE'} }")
private List<String> permissions;
```

## 3. Inline list

### 3.1. Cú pháp và danh sách rỗng

Một danh sách có phần tử được viết bằng `{...}`:

```java
List<?> numbers = parser.parseExpression("{1, 2, 3, 4}")
        .getValue(context, List.class);

List<?> names = parser.parseExpression("{'An', 'Binh', 'Chi'}")
        .getValue(context, List.class);
```

`{}` là cú pháp của một danh sách rỗng. Đây là trường hợp đặc biệt hữu ích khi biểu thức cần trả về một collection hợp lệ dù hiện tại không có phần tử:

```java
List<?> empty = parser.parseExpression("{}")
        .getValue(context, List.class);
```

Các phần tử được phân tách bằng dấu phẩy. Có thể thêm khoảng trắng hoặc xuống dòng giữa các token để biểu thức dễ đọc hơn; khoảng trắng bên trong string literal vẫn là một phần của chuỗi.

### 3.2. Kiểu của phần tử

Mỗi phần tử của inline list là một SpEL expression được đánh giá độc lập. Kiểu runtime của phần tử là kiểu của giá trị mà expression đó trả về. Vì vậy, một list có thể chứa các kiểu khác nhau:

```java
List<?> values = parser.parseExpression(
        "{'READY', 3, true, null, 3.14}")
        .getValue(context, List.class);
```

Trong ví dụ này, các phần tử lần lượt là `String`, kiểu số nguyên tương ứng với literal `3`, `Boolean`, `null` và kiểu số thực tương ứng với literal `3.14`. SpEL không tự biến tất cả phần tử thành chuỗi hoặc thành cùng một kiểu chỉ vì chúng nằm trong một list.

Các biểu thức con cũng có thể trả về giá trị từ context:

```java
context.setVariable("currentRole", "ADMIN");

List<?> roles = parser.parseExpression(
        "{'USER', #currentRole, 'AUDITOR'}")
        .getValue(context, List.class);
```

Ở đây `#currentRole` được lấy từ biến đã đăng ký trong EvaluationContext. Nếu biểu thức con trả về một đối tượng nghiệp vụ, phần tử trong list sẽ giữ giá trị đối tượng đó.

### 3.3. Danh sách lồng nhau

Một inline list có thể chứa các inline list khác. Ví dụ:

```java
List<?> matrix = parser.parseExpression(
        "{{'a', 'b'}, {'x', 'y'}}")
        .getValue(context, List.class);
```

Kết quả là một list gồm hai phần tử; mỗi phần tử lại là một list. Có thể dùng cấu trúc lồng nhau để mô tả nhóm, ma trận nhỏ hoặc dữ liệu phân cấp.

Ví dụ khác:

```java
List<?> groups = parser.parseExpression(
        "{'backend', {'java', 'spring'}, 'frontend'}")
        .getValue(context, List.class);
```

Một list lồng nhau không tự động được làm phẳng. Phần tử ở vị trí thứ hai của `groups` vẫn là một list con.

## 4. Inline map

### 4.1. Cú pháp và map rỗng

Inline map dùng cú pháp `{key:value}`. Mỗi cặp khóa và giá trị được phân tách với cặp kế tiếp bằng dấu phẩy:

```java
Map<?, ?> inventor = parser.parseExpression(
        "{name:'Nikola', dob:'10-July-1856'}")
        .getValue(context, Map.class);
```

`{:}` là cú pháp của một map rỗng:

```java
Map<?, ?> empty = parser.parseExpression("{:}")
        .getValue(context, Map.class);
```

Hai cú pháp rỗng cần phân biệt rõ:

| Biểu thức | Kết quả |
|---|---|
| `{}` | List rỗng |
| `{:}` | Map rỗng |

Nếu viết một cặp key/value nhưng bỏ dấu hai chấm, parser sẽ hiểu cấu trúc theo cú pháp list hoặc báo lỗi tùy biểu thức; hãy dùng đúng dấu hai chấm cho mỗi entry của map.

### 4.2. Tên khóa và kiểu của key/value

Tên khóa dạng identifier có thể không cần dấu nháy đơn:

```java
Map<?, ?> config = parser.parseExpression(
        "{name:'catalog', enabled:true, retries:3}")
        .getValue(context, Map.class);
```

Nếu khóa chứa dấu chấm hoặc ký tự khiến nó không còn là identifier đơn giản, hãy đặt khóa trong dấu nháy đơn:

```java
Map<?, ?> config = parser.parseExpression(
        "{'service.name':'catalog', 'feature.enabled':true}")
        .getValue(context, Map.class);
```

Trong SpEL, dấu nháy đơn cũng có thể được dùng cho các khóa chuỗi thông thường, kể cả khi không bắt buộc:

```java
Map<?, ?> config = parser.parseExpression(
        "{'name':'catalog', 'region':'ap-southeast-1'}")
        .getValue(context, Map.class);
```

Kiểu của key và value được quyết định bởi giá trị mà các expression tương ứng tạo ra. Với map cấu hình thông thường, khóa thường là `String`; value có thể là chuỗi, số, boolean, null, list, map hoặc đối tượng khác. Cú pháp inline map không ép tất cả value về cùng một kiểu.

Có thể truy cập value bằng key từ Java:

```java
String name = (String) config.get("name");
Boolean enabled = (Boolean) config.get("enabled");
```

Khi cần đọc key có dấu chấm bằng cú pháp index của SpEL, đặt key trong dấu nháy đơn:

```java
context.setVariable("config", config);

String serviceName = parser.parseExpression(
        "#config['service.name']")
        .getValue(context, String.class);
```

### 4.3. Map lồng nhau và collection làm value

Value của một map entry có thể là inline map hoặc inline list. Ví dụ:

```java
Map<?, ?> application = parser.parseExpression(
        "{service:{name:'catalog', port:8080}, " +
        "features:{'search', 'audit'}, " +
        "limits:{maxRequests:100, burst:20}}")
        .getValue(context, Map.class);
```

Cấu trúc này tạo ra một map ngoài cùng với các value lồng nhau:

- `service` trỏ tới một map có `name` và `port`.
- `features` trỏ tới một list các tên tính năng.
- `limits` trỏ tới một map chứa giới hạn.

Có thể kết hợp nhiều cấp list và map để mô tả dữ liệu có cấu trúc. Cần truy cập đúng cấp: `application.get("service")` trả về map con, không phải trực tiếp tên service.

## 5. Inline collection có thể chứa expression động

Phần tử của list và key/value của map không bắt buộc phải là literal cố định. Chúng có thể tham chiếu biến, property, method hoặc biểu thức SpEL khác, tùy EvaluationContext đã cấu hình:

```java
context.setVariable("region", "ap-southeast-1");
context.setVariable("replicas", 3);

Expression expression = parser.parseExpression(
        "{region:#region, replicas:#replicas, enabled:true}");

Map<?, ?> deployment = expression.getValue(context, Map.class);
```

Khi giá trị của biến thay đổi, lần đánh giá tiếp theo có thể tạo ra collection với nội dung khác. Điều này hữu ích khi một phần cấu trúc là cố định nhưng dữ liệu phụ thuộc vào context tại thời điểm chạy.

Cần phân biệt expression được phân tích một lần với giá trị được tính khi gọi `getValue()`. Parser tạo cấu trúc biểu thức; các phần tử động được giải quyết khi biểu thức được đánh giá.

## 6. Constant collection và hành vi khi đánh giá nhiều lần

SpEL tối ưu inline collection khi toàn bộ cấu trúc chỉ gồm các literal cố định:

- Inline list gồm toàn literal cố định có thể được tạo thành constant list và lưu trong expression thay vì dựng list mới ở mỗi lần đánh giá.
- Inline map gồm literal cố định, hoặc cấu trúc lồng nhau chỉ gồm các list/map constant, có thể được tạo thành constant map.
- Nếu có phần tử, key hoặc value phụ thuộc vào biến hay expression động, collection cần được đánh giá theo context ở mỗi lần chạy.

Ví dụ list cố định:

```java
Expression fixedList = parser.parseExpression(
        "{'LOW', 'MEDIUM', 'HIGH'}");

List<?> first = fixedList.getValue(context, List.class);
List<?> second = fixedList.getValue(context, List.class);
```

Ví dụ list động:

```java
context.setVariable("role", "USER");

Expression dynamicList = parser.parseExpression(
        "{'DEFAULT', #role}");

List<?> roles = dynamicList.getValue(context, List.class);
```

Tối ưu constant có nghĩa là SpEL có thể tái sử dụng giá trị collection gắn với expression. Vì vậy, không nên giả định mỗi lần gọi `getValue()` đều trả về một collection mới để ứng dụng tự do sửa đổi. Tránh dùng một inline collection cố định như vùng dữ liệu tạm có thể thay đổi. Nếu cần một list hoặc map mutable độc lập cho mỗi request, hãy tạo bản sao bằng Java, ví dụ `new ArrayList<>(result)` hoặc `new HashMap<>(result)`.

Việc collection được cache cũng không có nghĩa cú pháp inline tự khai báo một kiểu generic hoặc tự đảm bảo mọi phần tử có cùng kiểu. Constant/dynamic là đặc tính đánh giá và tối ưu của expression; kiểu phần tử vẫn phụ thuộc vào từng giá trị.

## 7. Kiểu phần tử, generic type và chuyển đổi dữ liệu

### 7.1. Inline literal không khai báo generic type

Các biểu thức như `{'A', 'B'}` và `{name:'A'}` tạo ra list/map ở runtime. SpEL không có cú pháp khai báo generic type ngay trong literal, ví dụ không viết `List<String>{...}` hoặc `Map<String, Integer>{...}`.

Nếu cần một collection có kiểu rõ ràng trong mã Java, khai báo biến hoặc thuộc tính đích với generic type:

```java
List<String> names = List.of("An", "Binh");
Map<String, Integer> retryLimits = Map.of("catalog", 3);
```

Khi nhận kết quả từ SpEL, có thể kiểm tra hoặc chuyển đổi giá trị theo kiểu đích. Lưu ý `List.class` và `Map.class` chỉ mô tả kiểu collection ngoài cùng; chúng không mang thông tin generic của phần tử.

### 7.2. Chuyển đổi theo generic type của thuộc tính đích

SpEL tích hợp với Spring ConversionService. Cơ chế chuyển đổi hiểu generic metadata của thuộc tính đích, vì vậy khi gán giá trị vào collection có kiểu phần tử cụ thể, Spring có thể chuyển đổi từng phần tử để duy trì kiểu đích.

Ví dụ, một bean có thuộc tính `List<Boolean>`:

```java
public class FeatureFlags {
    public List<Boolean> enabled = new ArrayList<>();
}

// Bean có một phần tử Boolean ban đầu.
FeatureFlags flags = new FeatureFlags();
flags.enabled.add(Boolean.TRUE);

EvaluationContext context = new StandardEvaluationContext();

parser.parseExpression("enabled[0]")
        .setValue(context, flags, "false");

Boolean enabled = flags.enabled.get(0);
// enabled == Boolean.FALSE
```

Giá trị truyền vào là chuỗi `"false"`, nhưng thuộc tính phần tử có kiểu `Boolean`. ConversionService nhận biết generic type của list và chuyển chuỗi thành `Boolean.FALSE`.

Điều này xảy ra tại ranh giới gán giá trị vào thuộc tính có metadata kiểu. Nó không có nghĩa mọi inline list đều tự động trở thành `List<Boolean>` hoặc `List<String>`. Khi đánh giá một inline collection độc lập, hãy xem kiểu runtime của từng phần tử hoặc chủ động chuyển đổi sang kiểu đích trong ứng dụng.

### 7.3. Phân biệt collection literal với array

Inline list và array là hai kiểu kết quả khác nhau:

```java
List<?> list = parser.parseExpression("{1, 2, 3}")
        .getValue(context, List.class);

int[] array = parser.parseExpression("new int[]{1, 2, 3}")
        .getValue(context, int[].class);
```

`{1, 2, 3}` tạo list; `new int[]{1, 2, 3}` tạo mảng nguyên thủy `int[]`. Nếu API Java yêu cầu array, không thể chỉ dựa vào việc inline list có cùng các giá trị để coi hai kiểu là tương đương. Hãy chuyển đổi rõ ràng hoặc dùng cú pháp array construction.

## 8. Kết hợp inline collection với truy cập phần tử

Sau khi đánh giá, có thể dùng API Java để đọc list/map, hoặc lưu kết quả vào biến SpEL để truy cập bằng index:

```java
context.setVariable("priorities",
        parser.parseExpression("{'LOW', 'MEDIUM', 'HIGH'}")
                .getValue(context));

String selected = parser.parseExpression("#priorities[1]")
        .getValue(context, String.class);
// selected = "MEDIUM"
```

Với map, dùng key trong ngoặc vuông:

```java
context.setVariable("limits",
        parser.parseExpression("{max:100, burst:20}")
                .getValue(context));

Integer max = parser.parseExpression("#limits['max']")
        .getValue(context, Integer.class);
```

Index của list bắt đầu từ `0`. Map được truy cập theo key; nếu key là chuỗi, đặt trong dấu nháy đơn bên trong ngoặc vuông. Với map lồng nhau, tiếp tục index theo từng cấp hoặc dùng property/index access phù hợp với cấu trúc.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `{}` nhưng mong đợi map rỗng | `{}` tạo list rỗng. | Dùng `{:}` cho map rỗng. |
| Map không parse được | Entry thiếu dấu `: ` giữa key và value hoặc thiếu dấu phẩy giữa các entry. | Dùng dạng `{key:value, otherKey:otherValue}`. |
| Key có dấu chấm bị phân tích thành tên property | Key không được đặt trong dấu nháy. | Dùng `{'service.name':'catalog'}`. |
| Ép kết quả thành `List<String>` nhưng có phần tử kiểu khác | Literal không khai báo generic và các expression con có thể trả về nhiều kiểu. | Kiểm tra phần tử hoặc chuyển đổi sang kiểu đích rõ ràng. |
| Gán chuỗi vào phần tử Boolean nhưng không chuyển đổi được | Target không có generic metadata phù hợp hoặc ConversionService không có converter cần thiết. | Kiểm tra kiểu thuộc tính, TypeDescriptor và converter đang dùng. |
| Sửa list/map cố định làm ảnh hưởng lần đánh giá sau | Expression có thể cache collection gồm literal cố định. | Tạo bản sao mutable trong Java trước khi sửa. |
| Cần array nhưng nhận được List | Inline list và array construction có kiểu kết quả khác nhau. | Dùng `new int[]{...}` hoặc chuyển list sang array. |
| Truy cập nhầm cấp trong collection lồng nhau | Phần tử ở cấp ngoài có thể là list/map con. | Kiểm tra kiểu và cấu trúc từng cấp trước khi truy cập sâu. |

Khi gặp lỗi, hãy tách biểu thức thành các phần nhỏ: parse list/map riêng, lấy giá trị bằng `getValue()`, kiểm tra kiểu runtime và từng phần tử, sau đó mới ghép expression động hoặc thao tác index. Với lỗi chuyển đổi, kiểm tra kiểu generic của thuộc tính đích và ConversionService thay vì giả định literal đã mang sẵn kiểu mong muốn.

## 10. Ghi nhớ

- `{a, b, c}` tạo inline list; `{key:value}` tạo inline map.
- `{}` là list rỗng; `{:}` là map rỗng.
- List có thể lồng list; map có thể lồng map hoặc chứa list/map làm value.
- Mỗi phần tử, key và value được đánh giá thành giá trị runtime riêng; inline syntax không khai báo generic type.
- Map key dạng identifier có thể không cần quote; key có dấu chấm như `service.name` cần đặt trong dấu nháy.
- Biểu thức động có thể tham chiếu biến, property hoặc method trong EvaluationContext.
- Cấu trúc chỉ gồm literal cố định có thể được cache thành constant collection; đừng giả định mỗi lần đánh giá tạo collection mới.
- ConversionService có thể chuyển đổi phần tử theo generic metadata của thuộc tính đích khi gán dữ liệu.
- Inline list là `List`; array phải được tạo bằng cú pháp `new Type[]{...}` hoặc chuyển đổi riêng.

## Tài liệu tham khảo

- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework Reference — Inline Maps](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html)
- [Spring Framework Reference — Evaluation and Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
