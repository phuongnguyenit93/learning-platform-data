# Tạo map inline với key và value trong SpEL

Spring Expression Language (SpEL) cho phép khai báo một Map ngay trong biểu thức bằng cú pháp map inline. Cách này hữu ích khi cần tạo một cấu trúc key-value nhỏ để truyền cho method, biểu diễn metadata, tạo cấu hình hoặc gom các giá trị được tính từ object hiện tại.

Một map inline có các cặp key và value, ngăn cách bằng dấu phẩy. Key là chuỗi literal đặt trong dấu nháy đơn; value có thể là literal hoặc một biểu thức SpEL. Vì vậy, một map có thể vừa chứa giá trị cố định vừa lấy dữ liệu từ biến, property hay phép tính trong EvaluationContext.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Nhận biết cú pháp map inline và phân biệt nó với list inline.
- Khai báo các cặp key-value trong một biểu thức SpEL.
- Dùng chuỗi literal làm key và dùng biểu thức làm value.
- Truyền biến, đọc property và tính toán giá trị trong map.
- Tạo map lồng nhau và kết hợp map với list inline.
- Đọc một phần tử bằng key sau khi nhận kết quả map.
- Hiểu cách SpEL xử lý map literal cố định và map có value động.
- Biết khi nào nên tạo map trong Java thay vì viết inline trong SpEL.

Bạn nên biết cách dùng SpelExpressionParser, Expression.getValue() và StandardEvaluationContext để truyền biến vào biểu thức.

## 2. Map inline là gì?

Map là cấu trúc dữ liệu lưu các cặp key-value. Trong SpEL, có thể tạo map ngay trong chuỗi biểu thức thay vì phải tạo object Map trước ở Java.

Ví dụ:

~~~text
{'name': 'Spring', 'version': 6}
~~~

Biểu thức trên tạo một map gồm hai cặp:

| Key | Value |
|---|---|
| name | Spring |
| version | 6 |

Key được viết dưới dạng chuỗi literal trong dấu nháy đơn. Value có thể là chuỗi, số, boolean, null hoặc một biểu thức trả về giá trị phù hợp.

Một ví dụ khác:

~~~text
{'enabled': true, 'retryCount': 3, 'description': 'default policy'}
~~~

Map inline thường phù hợp với dữ liệu nhỏ và cấu trúc đã biết trước. Với dữ liệu lớn, thay đổi thường xuyên hoặc cần thao tác phức tạp, nên tạo Map trong Java rồi truyền vào context.

## 3. Cú pháp cơ bản

Cú pháp tổng quát:

~~~text
{'key1': value1, 'key2': value2, 'key3': value3}
~~~

Các thành phần:

- Cặp dấu ngoặc nhọn bao quanh map.
- Key là chuỗi literal, đặt trong dấu nháy đơn.
- Dấu hai chấm phân cách key và value.
- Dấu phẩy phân cách các cặp key-value.
- Value là một biểu thức SpEL hợp lệ.

Ví dụ:

~~~text
{'id': 1001, 'active': true, 'name': 'An'}
~~~

Có thể viết biểu thức nhiều dòng để dễ đọc nếu chuỗi được truyền vào parser vẫn giữ nguyên cú pháp:

~~~text
{
    'id': 1001,
    'active': true,
    'name': 'An'
}
~~~

Tránh key trùng nhau vì khi một key được khai báo nhiều lần, giá trị trước có thể bị thay thế trong quá trình tạo Map. Cấu trúc có key duy nhất dễ hiểu và dễ bảo trì hơn.

## 4. Phân biệt map inline với list inline

SpEL dùng dấu ngoặc nhọn cho cả inline list và inline map. Dấu hiệu phân biệt là dấu hai chấm giữa key và value.

| Cấu trúc | Ví dụ | Ý nghĩa |
|---|---|---|
| List inline | {'red', 'green', 'blue'} | Danh sách các phần tử |
| Map inline | {'color': 'red', 'enabled': true} | Các cặp key-value |

List chứa các giá trị theo vị trí; Map chứa giá trị được tra cứu theo key. Khi cần mô tả thuộc tính có tên như name, status hoặc configuration, map inline thường phù hợp hơn.

Một map có thể chứa list làm value:

~~~text
{
    'name': 'Spring',
    'tags': {'java', 'framework', 'expression'}
}
~~~

Ngược lại, một list cũng có thể chứa các map:

~~~text
{
    {'id': 1, 'name': 'A'},
    {'id': 2, 'name': 'B'}
}
~~~

Cấu trúc thứ hai là list gồm các map; nó hữu ích khi biểu diễn một tập bản ghi nhỏ trong biểu thức.

## 5. Dùng các kiểu value khác nhau

Value trong map inline không bị giới hạn ở chuỗi. Có thể dùng số, boolean, null và các biểu thức trả về object.

~~~text
{
    'name': 'Spring',
    'majorVersion': 6,
    'stable': true,
    'deprecated': false,
    'note': null
}
~~~

Một số ví dụ:

~~~text
{'count': 10 + 5}
~~~

~~~text
{'isAdult': #age >= 18}
~~~

~~~text
{'displayName': #firstName + ' ' + #lastName}
~~~

~~~text
{'upperName': #person.name.toUpperCase()}
~~~

Value được đánh giá theo ngữ cảnh SpEL. Nếu value tham chiếu biến chưa được đăng ký, property không tồn tại hoặc method không thể gọi, quá trình evaluate có thể thất bại.

Key và value có quy tắc khác nhau: key của map inline là chuỗi literal được đặt trong dấu nháy đơn; value mới là nơi thường đặt biểu thức động. Nếu cần key động, hãy xây dựng Map bằng Java rồi truyền map đó vào SpEL.

## 6. Dùng biến trong value

Biến SpEL có tiền tố #. Ứng dụng đăng ký biến trong EvaluationContext trước khi đánh giá map:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "{'name': #name, 'age': #age, 'active': #active}"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
context.setVariable("age", 25);
context.setVariable("active", true);

Map<?, ?> result =
    expression.getValue(context, Map.class);
~~~

Kết quả là một map tương đương:

~~~text
{
    'name': 'An',
    'age': 25,
    'active': true
}
~~~

Có thể thay đổi giá trị biến rồi đánh giá lại cùng expression:

~~~java
context.setVariable("name", "Binh");
context.setVariable("age", 30);

Map<?, ?> anotherResult =
    expression.getValue(context, Map.class);
~~~

Map kết quả lần sau lấy các value mới từ context. Cách này cho phép giữ cấu trúc map ổn định trong khi dữ liệu thay đổi theo từng lần đánh giá.

Không cần ghép chuỗi giá trị vào expression. Truyền dữ liệu bằng biến giúp giữ ranh giới giữa cú pháp và dữ liệu, đồng thời tránh lỗi escape khi giá trị có dấu nháy hoặc ký tự đặc biệt.

## 7. Lấy value từ property của object

Map inline có thể dùng property của root object hoặc object được truyền qua biến:

~~~java
public class Customer {
    private Long id;
    private String name;
    private boolean active;

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Biểu thức:

~~~text
{'customerId': #customer.id, 'customerName': #customer.name, 'active': #customer.active}
~~~

Đăng ký customer:

~~~java
context.setVariable("customer", customer);

Map<?, ?> summary =
    parser.parseExpression(
        "{'customerId': #customer.id, 'customerName': #customer.name, 'active': #customer.active}"
    ).getValue(context, Map.class);
~~~

SpEL đọc property theo các PropertyAccessor trong context. Nếu customer null, hoặc một property path không hợp lệ, việc đánh giá value tương ứng có thể lỗi. Hãy dùng null-safe navigation ở value nếu dữ liệu có thể null:

~~~text
{'customerName': #customer?.name ?: 'Guest'}
~~~

Null-safe navigation và Elvis được đánh giá bên trong value; key vẫn là chuỗi literal.

## 8. Kết hợp phép tính trong value

Một lợi ích của map inline là có thể gom các giá trị đã tính vào cùng một cấu trúc:

~~~text
{
    'subtotal': #price * #quantity,
    'discount': #price * #quantity * #discountRate,
    'total': (#price * #quantity) * (1 - #discountRate)
}
~~~

Map kết quả có thể được dùng làm summary hoặc input cho một bước tiếp theo.

Dùng dấu ngoặc khi công thức có nhiều toán tử để thể hiện thứ tự tính. Với công thức nghiệp vụ dài hoặc cần làm tròn tiền tệ, hãy cân nhắc tính trong Java để quản lý BigDecimal, scale và rounding rõ ràng.

Một ví dụ có điều kiện:

~~~text
{
    'eligible': #customer.active and #order.total >= #minimum,
    'label': #order.total >= #minimum ? 'QUALIFIED' : 'PENDING'
}
~~~

Mỗi value được đánh giá như một biểu thức riêng. Nếu value có lỗi, toàn bộ quá trình tạo map có thể không hoàn tất.

## 9. Map lồng nhau

Value của một key có thể là một map inline khác. Cách này phù hợp khi dữ liệu có cấu trúc phân cấp:

~~~text
{
    'customer': {
        'id': #customerId,
        'name': #customerName
    },
    'order': {
        'number': #orderNumber,
        'total': #orderTotal
    }
}
~~~

Có thể đọc dữ liệu lồng nhau bằng cú pháp index:

~~~text
#result['customer']['name']
~~~

Nếu map được trả về trực tiếp từ expression, Java có thể đọc qua Map API:

~~~java
Map<?, ?> result = expression.getValue(context, Map.class);

Object customerValue = result.get("customer");

if (customerValue instanceof Map<?, ?> customerMap) {
    Object customerName = customerMap.get("name");
}
~~~

Khi map lồng nhau nhiều tầng, nên giữ tên key rõ ràng và tránh cấu trúc quá sâu. Nếu dữ liệu là một hợp đồng API ổn định, DTO có kiểu thường an toàn và dễ bảo trì hơn Map lồng nhau.

## 10. Kết hợp map với list inline

Map có thể chứa list làm value, ví dụ danh sách role hoặc tag:

~~~text
{
    'username': #username,
    'roles': {'ADMIN', 'EDITOR'},
    'permissions': {'read', 'write'}
}
~~~

List cũng có thể chứa các map:

~~~text
{
    {'code': 'VN', 'name': 'Vietnam'},
    {'code': 'SG', 'name': 'Singapore'}
}
~~~

Đây là một cách biểu diễn dataset nhỏ ngay trong biểu thức. Nếu danh sách dài, được cập nhật thường xuyên hoặc cần validation, hãy khởi tạo trong Java và truyền vào context thay vì nhúng toàn bộ dữ liệu vào chuỗi SpEL.

## 11. Truy cập map sau khi tạo

Sau khi nhận kết quả map, có thể lấy value theo key bằng cú pháp index:

~~~text
#settings['theme']
~~~

Nếu map là biến được đăng ký trong context:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "dark");
settings.put("maxItems", 20);

context.setVariable("settings", settings);

Expression expression =
    parser.parseExpression("#settings['theme']");

String theme =
    expression.getValue(context, String.class);
~~~

Kết quả là dark.

Với map inline được tạo trong một expression, có thể lấy map về Java rồi đọc bằng get(key). Cần phân biệt key không tồn tại với key có value null. Cả hai trường hợp có thể khiến thao tác đọc trả về null; nếu cần phân biệt, hãy dùng Map.containsKey(...) ở Java hoặc cung cấp một quy tắc kiểm tra riêng.

## 12. Map literal cố định và value động

SpEL có thể tối ưu map inline chỉ gồm các literal cố định hoặc cấu trúc hằng lồng nhau bằng cách tạo map hằng để tái sử dụng cho expression. Nếu một hoặc nhiều value phụ thuộc vào dữ liệu runtime, chẳng hạn biến hoặc property, map được tạo khi expression được đánh giá để lấy value hiện tại.

Ví dụ map cố định:

~~~text
{'mode': 'SAFE', 'maxRetries': 3}
~~~

Ví dụ map động:

~~~text
{'user': #username, 'createdAt': #timestamp}
~~~

Sự khác biệt này quan trọng khi thiết kế ứng dụng. Đừng dựa vào việc map inline cố định sẽ tạo ra một object mới ở mỗi lần evaluate. Nếu cần một map mutable để thay đổi, hãy tạo bản sao trong Java:

~~~java
Map<?, ?> literal =
    parser.parseExpression("{'mode': 'SAFE', 'maxRetries': 3}")
        .getValue(Map.class);

Map<Object, Object> mutableCopy =
    new LinkedHashMap<>(literal);
~~~

Hãy xem map literal cố định như dữ liệu chỉ đọc. Cách này tránh phụ thuộc vào chi tiết tối ưu nội bộ của parser và ngăn thay đổi ngoài ý muốn ảnh hưởng tới lần sử dụng sau.

## 13. Sử dụng map inline trong Spring

Map inline có thể xuất hiện trong các điểm tích hợp Spring nhận SpEL, ví dụ @Value:

~~~java
@Value("#{ {'mode': 'SAFE', 'maxRetries': 3} }")
private Map<String, Object> defaults;
~~~

Biểu thức tạo map với hai cặp key-value. Spring đánh giá expression trong context của container rồi gán kết quả cho property nếu kiểu kết quả tương thích.

Có thể tạo map có value lấy từ bean hoặc property khác, tùy resolver và context mà Spring cung cấp:

~~~java
@Value("#{ {'serviceName': @serviceInfo.name, 'enabled': @featureFlags.enabled} }")
private Map<String, Object> serviceSettings;
~~~

Chỉ dùng bean reference khi bean resolver trong context có sẵn và bean được quản lý bởi container. Nếu map chỉ là cấu hình tĩnh, có thể cân nhắc dùng configuration properties hoặc cấu hình Java có kiểu thay vì biểu thức phức tạp.

Map inline không tự chuyển thành một DTO tùy ý chỉ vì key trùng với tên field. Nếu cần object có kiểu, hãy dùng constructor, factory hoặc binder phù hợp với mô hình ứng dụng.

## 14. Kiểm soát kiểu và giá trị

Map inline có thể chứa nhiều kiểu value khác nhau. Khi lấy kết quả bằng Map.class, các value thường được xử lý như Object. Vì vậy, code tiêu thụ map cần kiểm tra kiểu trước khi ép kiểu.

~~~java
Map<?, ?> result = expression.getValue(context, Map.class);

Object ageValue = result.get("age");

if (ageValue instanceof Number age) {
    int years = age.intValue();
}
~~~

Không nên giả định tất cả value đều là String. Map có thể chứa Boolean, Number, collection, map lồng nhau, object từ context hoặc null.

Nếu hợp đồng dữ liệu yêu cầu kiểu cố định, hãy xác thực từng key và value hoặc chuyển đổi sang DTO trong Java. Đối với map đầu vào từ bên ngoài, cần kiểm tra key bắt buộc, kiểu value, giới hạn kích thước và giá trị hợp lệ.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Parser báo lỗi cú pháp | Thiếu dấu hai chấm, dấu phẩy hoặc dấu nháy | Kiểm tra từng cặp key-value |
| Dùng list nhưng muốn map | Không có cặp key:value | Thêm key literal và dấu hai chấm |
| Key động không hoạt động | Key inline yêu cầu chuỗi literal | Tạo map trong Java nếu key thay đổi |
| Không tìm thấy biến | Chưa đăng ký biến trong context | Gọi setVariable với đúng tên |
| Value property bị lỗi | Root object null hoặc property path sai | Kiểm tra object và dùng null-safe navigation khi phù hợp |
| Value có kiểu không mong đợi | Map chứa nhiều kiểu Object | Kiểm tra kiểu trước khi ép kiểu |
| Map lồng nhau khó đọc | Cấu trúc quá sâu hoặc key không rõ | Dùng tên key có ý nghĩa hoặc chuyển sang DTO |
| Thay đổi map ảnh hưởng lần dùng sau | Map literal cố định có thể được tái sử dụng | Tạo mutable copy trong Java trước khi sửa |
| Annotation không phân giải bean | Context không có bean resolver hoặc sai tên bean | Kiểm tra điểm tích hợp và ApplicationContext |

## 16. Bài tập thực hành

1. Tạo map inline gồm name, age và active.
2. Tạo map có value lấy từ biến trong StandardEvaluationContext.
3. Tạo map có value là biểu thức số học và điều kiện Boolean.
4. Tạo map lồng nhau gồm customer và order, rồi đọc customer.name.
5. Tạo map chứa list roles và permissions.
6. Dùng map inline cố định, sau đó tạo mutable copy trong Java và thay đổi một key.
7. Thử truyền key động và quan sát vì sao nên xây dựng map trong Java.
8. Viết test cho biến chưa đăng ký, property null, value null, key thiếu và value sai kiểu.

## 17. Checklist trước khi dùng map inline

- [ ] Đã dùng dấu ngoặc nhọn và cặp key:value đúng cú pháp chưa?
- [ ] Key có phải chuỗi literal được đặt trong dấu nháy đơn không?
- [ ] Key có duy nhất và dễ hiểu không?
- [ ] Value có tham chiếu biến hoặc property đã tồn tại trong context không?
- [ ] Đã xử lý null trong value nếu dữ liệu có thể thiếu chưa?
- [ ] Đã phân biệt map inline với list inline chưa?
- [ ] Cấu trúc lồng nhau có đủ nông và rõ ràng không?
- [ ] Đã xác định kiểu của value khi Java tiêu thụ map chưa?
- [ ] Có cần mutable copy trước khi sửa map không?
- [ ] Dữ liệu có đủ nhỏ để đặt inline hay nên tạo Map trong Java?
- [ ] EvaluationContext có chỉ cấp quyền cần thiết cho các value động không?

## 18. Kết luận

Map inline cho phép tạo nhanh cấu trúc key-value ngay trong SpEL. Key là chuỗi literal, còn value có thể là literal, biến, property, phép tính, điều kiện hoặc một cấu trúc map/list lồng nhau. Dùng cú pháp này cho dữ liệu nhỏ và ổn định; truyền dữ liệu động qua EvaluationContext thay vì ghép chuỗi. Hãy kiểm tra kiểu value, phân biệt key thiếu với value null và tạo bản sao trong Java nếu cần map mutable. Khi cấu trúc trở nên lớn hoặc là hợp đồng dữ liệu quan trọng, DTO và Map được xây dựng trong Java thường dễ kiểm soát hơn.