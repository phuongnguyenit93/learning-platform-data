# Kiểu phần tử của inline collection trong Spring Expression Language (SpEL)

SpEL cho phép khai báo collection ngay trong biểu thức bằng cú pháp inline. Một inline list có thể chứa số, chuỗi, Boolean, null hoặc kết quả của những biểu thức khác. Inline map có thể kết hợp các kiểu giá trị khác nhau cho key và value. Vì vậy, khi làm việc với inline collection, cần hiểu kiểu của từng phần tử được hình thành như thế nào và Java nhận kết quả dưới dạng gì.

Bài này tập trung vào kiểu phần tử của inline list và inline map, collection đồng nhất và không đồng nhất, collection lồng nhau, giá trị động từ EvaluationContext, cách nhận kết quả trong Java và cách kiểm tra hoặc chuyển đổi kiểu khi ứng dụng cần một cấu trúc dữ liệu có kiểu rõ ràng.

## 1. Inline collection là gì?

Inline collection là collection được viết trực tiếp trong biểu thức SpEL, không cần tạo trước một biến List hoặc Map trong Java.

Hai dạng thường gặp:

~~~text
{1, 2, 3}
{'red', 'green', 'blue'}
{'name': 'An', 'age': 30}
~~~

- Inline list dùng các phần tử phân tách bằng dấu phẩy và đặt trong cặp dấu ngoặc nhọn.
- Inline map dùng các cặp key:value, mỗi cặp được phân tách bằng dấu phẩy.
- Các phần tử có thể là literal hoặc biểu thức được đánh giá tại thời điểm gọi getValue().

Ví dụ, biểu thức sau tạo một danh sách ba số:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("{1, 2, 3}");

List<?> numbers = expression.getValue(List.class);
~~~

Biểu thức map:

~~~java
Expression expression = parser.parseExpression(
        "{'name': 'An', 'age': 30}"
);

Map<?, ?> person = expression.getValue(Map.class);
~~~

Inline list tạo ra một đối tượng List; inline map tạo ra một đối tượng Map. Chúng không phải cú pháp khai báo generic của Java và cũng không tự động biến thành array.

## 2. Kiểu của từng phần tử trong inline list

Mỗi phần tử trong inline list được đánh giá thành một giá trị riêng. Kiểu runtime của phần tử phụ thuộc vào biểu thức tạo ra giá trị đó.

Ví dụ:

~~~text
{'Spring', 42, true, null, 3.14}
~~~

Danh sách này có thể chứa:

- String từ literal chuỗi 'Spring'.
- Một kiểu số nguyên từ literal 42.
- Boolean từ literal true.
- Giá trị null.
- Một kiểu số thực từ literal 3.14.

SpEL không bắt buộc mọi phần tử trong một inline list phải có cùng kiểu. Một list có thể chứa nhiều kiểu runtime khác nhau. Vì vậy, khi nhận kết quả trong Java, kiểu phù hợp thường là List<?> hoặc List<Object> thay vì giả định mọi phần tử đều là String hay Integer.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "{'Spring', 42, true, null, 3.14}"
);

List<?> values = expression.getValue(List.class);

Object first = values.get(0);
Object second = values.get(1);
Object third = values.get(2);
Object fourth = values.get(3);
Object fifth = values.get(4);
~~~

Có thể kiểm tra từng phần tử:

~~~java
for (Object value : values) {
    if (value == null) {
        System.out.println("null");
    } else {
        System.out.println(value.getClass().getName());
    }
}
~~~

Đoạn mã kiểm tra kiểu runtime của từng phần tử. Phần tử null không có đối tượng để gọi getClass(), vì vậy cần kiểm tra null trước.

## 3. Kiểu phần tử đến từ literal SpEL

Các literal trong inline collection tuân theo quy tắc kiểu của chính SpEL. Một vài nhóm thường gặp:

| Literal | Giá trị hoặc kiểu thường gặp |
|---|---|
| 'text' | String |
| true, false | Boolean |
| null | null |
| 42 | Số nguyên, thường là Integer với giá trị thông thường |
| 42L | Long |
| 3.14 | Số thực, thường là Double |
| 3.14F | Float |
| 3.14M | BigDecimal |

Ví dụ kết hợp các kiểu:

~~~text
{'name', 25, 9000000000L, 3.14F, 19.99M, false}
~~~

Kiểu số cụ thể còn phụ thuộc giá trị và hậu tố literal. Khi ứng dụng yêu cầu một kiểu số nhất định, hãy biểu diễn kiểu đó rõ ràng hoặc thực hiện chuyển đổi ở ranh giới Java.

Không nên suy luận rằng một list chứa toàn số thì mọi phần tử chắc chắn cùng kiểu. Ví dụ, một list có thể chứa Integer, Long, BigDecimal và Double cùng lúc. Nếu cần tính toán, hãy xác định chính sách chuyển đổi và độ chính xác trước khi sử dụng.

## 4. Inline list đồng nhất và không đồng nhất

### 4.1. List đồng nhất

List đồng nhất là list mà các phần tử có cùng kiểu runtime hoặc cùng tuân theo một hợp đồng kiểu mà ứng dụng mong muốn.

Ví dụ:

~~~text
{'Spring', 'Spring Boot', 'Spring MVC'}
{10, 20, 30}
{true, false, true}
~~~

Trong Java, có thể nhận các kết quả đó bằng List<?> rồi kiểm tra hoặc chuyển sang kiểu mong muốn:

~~~java
List<?> rawNames = parser.parseExpression(
        "{'Spring', 'Spring Boot', 'Spring MVC'}"
).getValue(List.class);
~~~

Vì các phần tử đều là chuỗi, ứng dụng có thể chuyển sang List<String> sau khi xác nhận kiểu. Không nên chỉ ép kiểu toàn bộ list mà bỏ qua kiểm tra nếu biểu thức có thể được thay đổi bởi người dùng hoặc cấu hình bên ngoài.

### 4.2. List không đồng nhất

List không đồng nhất chứa nhiều kiểu phần tử khác nhau:

~~~text
{'An', 25, true, null}
~~~

Cấu trúc này hữu ích khi biểu thức cần trả về một nhóm giá trị có ý nghĩa khác nhau. Tuy nhiên, nó khiến mã Java nhận kết quả phải xử lý kiểu từng phần tử.

~~~java
List<?> values = parser.parseExpression(
        "{'An', 25, true, null}"
).getValue(List.class);

String name = (String) values.get(0);
Integer age = (Integer) values.get(1);
Boolean active = (Boolean) values.get(2);
Object optionalValue = values.get(3);
~~~

Các phép ép kiểu ở trên chỉ an toàn nếu nội dung biểu thức giữ đúng thứ tự và kiểu đã dự kiến. Nếu cấu hình có thể thay đổi, hãy kiểm tra bằng instanceof hoặc dùng một hàm chuyển đổi có kiểm soát.

Không nên dùng một inline list không đồng nhất làm hợp đồng dữ liệu phức tạp khi ứng dụng cần nhiều trường có tên và kiểu ổn định. Trong trường hợp đó, một object Java hoặc Map có key rõ nghĩa thường dễ bảo trì hơn.

## 5. Kiểu của phần tử trong inline map

Inline map biểu diễn dữ liệu theo cặp key:value:

~~~text
{'name': 'An', 'age': 25, 'active': true}
~~~

Mỗi key và value là một biểu thức được đánh giá. Vì vậy, key và value có thể có kiểu khác nhau; các value cũng có thể không đồng nhất.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "{'name': 'An', 'age': 25, 'active': true, 'note': null}"
);

Map<?, ?> result = expression.getValue(Map.class);

Object name = result.get("name");
Object age = result.get("age");
Object active = result.get("active");
Object note = result.get("note");
~~~

Trong ví dụ này, các key là chuỗi, còn value lần lượt là String, số nguyên, Boolean và null.

Key của map không nhất thiết phải là chuỗi nếu biểu thức tạo ra một kiểu key khác. Tuy nhiên, với cấu hình hoặc dữ liệu nghiệp vụ, chuỗi thường dễ đọc và thuận tiện khi truy cập bằng get(key).

Nếu hai key có giá trị bằng nhau theo quy tắc equals/hashCode, map chỉ có một mục cho key đó sau khi biểu thức được tạo. Vì vậy, không nên dựa vào các key trùng nhau để lưu nhiều value độc lập.

## 6. Phần tử là biểu thức động

Inline collection không chỉ chứa literal cố định. Phần tử có thể tham chiếu root object, biến trong EvaluationContext hoặc property của một đối tượng.

Ví dụ dùng biến:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

context.setVariable("userName", "An");
context.setVariable("minimumAge", 18);

Expression expression = parser.parseExpression(
        "{#userName, #minimumAge, #minimumAge + 2}"
);

List<?> values = expression.getValue(context, List.class);
~~~

Kết quả chứa giá trị của các biến và kết quả phép tính. Phần tử thứ ba là kết quả của biểu thức #minimumAge + 2, không phải chuỗi biểu thức.

Ví dụ dùng root object:

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }
}

Customer customer = new Customer("Lan", 25);

Expression expression = parser.parseExpression(
        "{name, age, age >= 18}"
);

List<?> values = expression.getValue(customer, List.class);
~~~

Các phần tử lần lượt lấy name, age và kết quả so sánh age >= 18 từ root object customer. Kiểu của từng phần tử là kiểu của giá trị mà biểu thức con trả về.

Nếu biến hoặc property thay đổi giữa các lần đánh giá, giá trị phần tử tương ứng cũng có thể thay đổi theo context hoặc root object được truyền vào lần gọi getValue().

## 7. Inline collection lồng nhau

Một inline list có thể chứa list khác. Điều này tạo ra cấu trúc nhiều cấp:

~~~text
{{1, 2}, {3, 4}, {5, 6}}
~~~

Kết quả là một List có các phần tử cũng là List.

~~~java
Expression expression = parser.parseExpression(
        "{{1, 2}, {3, 4}, {5, 6}}"
);

List<?> matrix = expression.getValue(List.class);

List<?> firstRow = (List<?>) matrix.get(0);
Object firstValue = firstRow.get(0);
~~~

Có thể lồng map trong list hoặc list trong map:

~~~text
{{'id': 1, 'name': 'An'}, {'id': 2, 'name': 'Binh'}}
~~~

~~~text
{'roles': {'reader', 'editor'}, 'enabled': true}
~~~

Với cấu trúc lồng nhau, kiểu cần kiểm tra ở từng cấp. Một List<?> ngoài cùng không nói lên kiểu của các phần tử bên trong. Mỗi phần tử có thể là List, Map hoặc một giá trị đơn.

Không nên ép kiểu sâu toàn bộ cấu trúc nếu không có hợp đồng rõ ràng. Hãy kiểm tra từng cấp hoặc chuyển đổi sang các lớp miền có kiểu cụ thể.

## 8. Inline collection và generic type của Java

SpEL trả về các đối tượng collection Java, nhưng generic type của Java không được lưu như một phần của kiểu runtime thông thường. Ví dụ, List<String> và List<Integer> đều có runtime class là java.util.List.

Khi gọi:

~~~java
List<?> values = expression.getValue(List.class);
~~~

tham số List.class chỉ yêu cầu kết quả là một List. Nó không yêu cầu SpEL đảm bảo từng phần tử là String.

Đoạn sau có thể biên dịch nhưng không chứng minh rằng mọi phần tử thực sự là String:

~~~java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) expression.getValue(List.class);
~~~

Generic type bị xóa ở runtime, vì vậy phép ép kiểu trên không kiểm tra từng phần tử. Lỗi có thể xuất hiện sau đó khi ứng dụng lấy một phần tử và sử dụng nó như String.

Cách an toàn hơn là nhận List<?> rồi kiểm tra:

~~~java
List<?> values = expression.getValue(List.class);
List<String> names = new ArrayList<>();

for (Object value : values) {
    if (!(value instanceof String)) {
        throw new IllegalArgumentException(
                "Expected a String element"
        );
    }

    names.add((String) value);
}
~~~

Sau khi vòng lặp hoàn tất, names chứa các phần tử String đã được xác nhận. Cách này hữu ích khi biểu thức được cấu hình bên ngoài và nội dung có thể thay đổi.

## 9. Chuyển đổi kiểu phần tử

SpEL có cơ chế TypeConverter thông qua EvaluationContext. Cơ chế chuyển đổi được dùng khi biểu thức cần cung cấp một giá trị cho vị trí có kiểu đích, ví dụ gán vào property hoặc truyền vào lời gọi có tham số kiểu cụ thể.

Tuy nhiên, việc lấy một inline list bằng getValue(List.class) không tự tạo ra hợp đồng generic như List<String>. Class List không chứa thông tin kiểu phần tử. Nếu cần một list đồng nhất, ứng dụng nên xác nhận hoặc chuyển đổi từng phần tử theo kiểu đích.

Ví dụ chuyển đổi có kiểm soát ở Java:

~~~java
List<?> rawValues = parser.parseExpression("{'10', '20', '30'}")
        .getValue(List.class);

List<Integer> numbers = new ArrayList<>();

for (Object value : rawValues) {
    if (!(value instanceof String)) {
        throw new IllegalArgumentException("Expected numeric text");
    }

    numbers.add(Integer.valueOf((String) value));
}
~~~

Sau chuyển đổi, numbers có kiểu phần tử Integer. Nếu một phần tử không phải chuỗi số hợp lệ, Integer.valueOf sẽ báo lỗi; ứng dụng cần xử lý lỗi đó theo yêu cầu nghiệp vụ.

Khi chuyển đổi collection sang một property có khai báo generic type, Spring có thể dùng TypeDescriptor để lấy thêm metadata kiểu đích và hỗ trợ chuyển đổi phần tử. Kết quả cụ thể phụ thuộc converter, kiểu nguồn và kiểu đích được cung cấp cho thao tác chuyển đổi.

## 10. Inline collection literal và việc tái sử dụng

SpEL có thể tối ưu inline list chỉ gồm các giá trị cố định. Với list mà tất cả phần tử đều là literal cố định, parser có thể tạo một constant list để tránh phải xây dựng lại danh sách ở mỗi lần đánh giá.

Điều này có hai hệ quả thiết kế:

- Inline collection phù hợp để biểu diễn dữ liệu đầu vào cố định cho một biểu thức.
- Không nên coi collection literal là một vùng lưu trạng thái có thể sửa đổi qua nhiều lần đánh giá.

Nếu ứng dụng cần thêm, xóa hoặc thay đổi phần tử, hãy tạo collection riêng trong Java hoặc truyền collection qua biến trong EvaluationContext. Không nên dựa vào việc inline list có thể sửa đổi hoặc có cùng identity giữa các lần gọi.

Khi phần tử phụ thuộc biến, root object hoặc dữ liệu động, giá trị cần được đánh giá theo context hiện tại. Hãy xem inline collection là kết quả của biểu thức, không phải nơi lưu trạng thái nghiệp vụ.

## 11. Inline list, inline map và Java array

Ba cấu trúc này có vai trò khác nhau:

| Cấu trúc | Dạng kết quả | Truy cập |
|---|---|---|
| Inline list | List | Theo chỉ số, ví dụ get(0) |
| Inline map | Map | Theo key, ví dụ get("name") |
| Java array | Array có kiểu thành phần cụ thể | Theo chỉ số, ví dụ array[0] |

Inline list và inline map thuận tiện khi biểu thức cần tạo collection. Nếu mã Java yêu cầu một array kiểu String[] hoặc int[], hãy thực hiện chuyển đổi rõ ràng ở phía Java hoặc dùng cơ chế tạo array phù hợp của SpEL.

Không nên giả định một inline list có thể được gán trực tiếp cho mọi tham số array. List và array là hai cấu trúc khác nhau dù đều chứa nhiều phần tử.

## 12. Ví dụ thực tế: tạo danh sách điều kiện và cấu hình

Một biểu thức có thể tạo list chứa các điều kiện Boolean từ root object:

~~~java
public class Account {
    private final int age;
    private final boolean active;
    private final boolean verified;

    public Account(int age, boolean active, boolean verified) {
        this.age = age;
        this.active = active;
        this.verified = verified;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isVerified() {
        return verified;
    }
}

Account account = new Account(25, true, false);

Expression expression = parser.parseExpression(
        "{age >= 18, active, verified}"
);

List<?> checks = expression.getValue(account, List.class);
~~~

List kết quả có ba phần tử Boolean. Mỗi phần tử là kết quả của một biểu thức con. Ứng dụng có thể đọc từng điều kiện hoặc kết hợp chúng trong bước xử lý tiếp theo.

Một inline map có thể tạo cấu hình nhỏ:

~~~java
Expression expression = parser.parseExpression(
        "{'minAge': 18, 'roles': {'reader', 'editor'}, 'enabled': true}"
);

Map<?, ?> configuration = expression.getValue(Map.class);

Object minAge = configuration.get("minAge");
Object roles = configuration.get("roles");
Object enabled = configuration.get("enabled");
~~~

Map này chứa một số nguyên, một collection lồng nhau và một Boolean. Vì kiểu value không đồng nhất, Map<?, ?> là kiểu nhận kết quả an toàn trước khi kiểm tra hoặc chuyển đổi từng value.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Giả định mọi phần tử đều cùng kiểu | Inline list cho phép nhiều kiểu runtime. | Dùng List<?> và kiểm tra từng phần tử. |
| Ép List<?> thành List<String> mà không kiểm tra | Generic type không được xác minh ở runtime. | Duyệt phần tử và kiểm tra hoặc chuyển đổi. |
| Gọi getClass() trên phần tử null | null không có đối tượng để gọi phương thức. | Kiểm tra null trước. |
| Nhầm inline list với array | Inline list tạo List, không phải array. | Chuyển đổi rõ ràng nếu API đích yêu cầu array. |
| Cho rằng Map có mọi value cùng kiểu | Các value của map có thể khác kiểu. | Dùng Map<?, ?> và xác định kiểu theo key. |
| Bỏ qua kiểu của collection lồng nhau | Phần tử bên ngoài có thể là List hoặc Map. | Kiểm tra từng cấp trước khi ép kiểu. |
| Dùng inline list cố định làm vùng lưu trạng thái | List literal cố định có thể được SpEL tối ưu thành constant list. | Tạo collection mutable riêng trong Java khi cần sửa đổi. |
| Giả định getValue(List.class) kiểm tra generic type | Class List không mang thông tin List<String> hay List<Integer>. | Kiểm tra hoặc chuyển đổi phần tử ở ranh giới Java. |
| Không xử lý lỗi khi chuyển đổi | Dữ liệu có thể không đúng định dạng hoặc không tương thích. | Xác thực dữ liệu và xử lý lỗi chuyển đổi. |

## 14. Ghi nhớ

- Inline list dùng cú pháp {value1, value2}; inline map dùng các cặp {key: value}.
- Inline list trả về List; inline map trả về Map.
- Mỗi phần tử được đánh giá riêng và giữ kiểu runtime của giá trị tạo ra nó.
- Một inline list hoặc map có thể chứa nhiều kiểu dữ liệu khác nhau.
- Phần tử có thể là literal, biến, property, phép toán hoặc collection lồng nhau.
- List<?> và Map<?, ?> là cách nhận kết quả an toàn khi chưa xác nhận kiểu từng phần tử.
- Generic type của Java không được kiểm tra chỉ bằng getValue(List.class).
- Dùng TypeConverter hoặc chuyển đổi có kiểm soát khi ứng dụng cần kiểu phần tử cụ thể.
- Inline collection phù hợp để biểu diễn dữ liệu trong biểu thức; tạo collection Java riêng khi cần lưu trạng thái hoặc thay đổi phần tử.
