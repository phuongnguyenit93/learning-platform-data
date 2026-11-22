# Collection literal cố định và biểu thức động

SpEL cho phép tạo collection ngay trong chuỗi biểu thức bằng cú pháp inline. List literal dùng cặp ngoặc nhọn với các phần tử phân tách bằng dấu phẩy; map literal dùng các cặp key-value. Cách viết này hữu ích khi biểu thức cần một tập giá trị nhỏ để so sánh, lọc, truyền vào method hoặc kết hợp với dữ liệu trong object.

Một điểm quan trọng là phân biệt collection chỉ chứa literal cố định với collection có phần tử hoặc key/value được tính động. SpEL có thể cache collection literal khi mọi thành phần đều là giá trị hằng. Nếu có biến, property hoặc lời gọi method, các phần đó phải được đánh giá theo context của từng lần chạy.

## 1. Inline list literal

List literal được viết bằng cặp ngoặc nhọn. Các phần tử được phân tách bằng dấu phẩy:

~~~text
{1, 2, 3}
{'red', 'green', 'blue'}
{true, false, true}
~~~

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("{'red', 'green', 'blue'}");

List<?> colors = expression.getValue(List.class);

System.out.println(colors); // [red, green, blue]
~~~

SpEL phân tích các phần tử trong ngoặc nhọn và tạo một List chứa các giá trị đó. List literal có thể chứa chuỗi, số, Boolean, null hoặc các biểu thức tạo ra object, miễn là các giá trị phù hợp với cú pháp và kiểu mà ứng dụng cần.

Khi cần một danh sách nhỏ dùng trực tiếp trong điều kiện, inline list thường ngắn gọn hơn việc tạo một biến Java chỉ để chứa vài giá trị cố định.

## 2. Inline map literal

Map literal được viết bằng các cặp key-value, trong đó key và value được phân tách bằng dấu hai chấm; các cặp được phân tách bằng dấu phẩy:

~~~text
{'name': 'Lan', 'active': true, 'level': 3}
~~~

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "{'name': 'Lan', 'active': true, 'level': 3}"
);

Map<?, ?> profile = expression.getValue(Map.class);

System.out.println(profile.get("name"));   // Lan
System.out.println(profile.get("active")); // true
~~~

Map literal phù hợp khi biểu thức cần một nhóm thuộc tính nhỏ, có tên rõ ràng. Ví dụ có thể tạo cấu hình tạm thời, truyền một tập tham số vào method hoặc mô tả dữ liệu mẫu ngay trong rule.

Key và value là biểu thức SpEL, nên chúng không bắt buộc phải là string literal. Có thể dùng số, biến hoặc kết quả của phép tính làm key/value nếu kiểu dữ liệu và mục tiêu sử dụng cho phép.

## 3. Collection literal cố định

Một collection literal được xem là cố định khi tất cả thành phần của nó đều là literal hằng. Ví dụ:

~~~text
{1, 2, 3}
{'draft', 'review', 'published'}
{'enabled': true, 'maxRetries': 3}
~~~

Với list hoặc map chỉ gồm các literal cố định, SpEL có thể tạo collection một lần khi phân tích biểu thức và cache giá trị đó để tái sử dụng trong các lần đánh giá tiếp theo. Điều này tránh phải dựng lại cùng một collection cho mỗi lần getValue.

Ví dụ:

~~~java
Expression allowedStates = parser.parseExpression(
        "{'DRAFT', 'REVIEW', 'PUBLISHED'}"
);

List<?> states = allowedStates.getValue(List.class);
~~~

Collection cố định thích hợp cho allowlist nhỏ, nhãn, mã trạng thái hoặc tập hằng được dùng lặp lại. Vì giá trị có thể được cache, hãy xem collection này như dữ liệu cấu hình chỉ đọc. Không nên sửa collection trả về hoặc dựa vào việc một lần đánh giá sẽ tạo ra một instance mới.

Việc cache là chi tiết thực thi nhằm tối ưu biểu thức. Hãy viết biểu thức theo ý nghĩa dữ liệu cố định, không dùng danh tính object hoặc thao tác mutate để suy luận về lifecycle của collection.

## 4. Collection literal có biểu thức động

Nếu một phần tử list hoặc một key/value của map phụ thuộc vào biến, property hoặc method, thành phần đó phải được đánh giá khi biểu thức chạy.

Ví dụ list động:

~~~text
{#primaryColor, #secondaryColor, #fallbackColor}
~~~

Ví dụ map động:

~~~text
{'user': #currentUser.name, 'total': #price * #quantity}
~~~

Có thể đánh giá với context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("primaryColor", "blue");
context.setVariable("secondaryColor", "green");
context.setVariable("fallbackColor", "gray");

Expression expression = parser.parseExpression(
        "{#primaryColor, #secondaryColor, #fallbackColor}"
);

List<?> colors = expression.getValue(context, List.class);
~~~

Giá trị của từng biến được lấy từ context tại thời điểm getValue. Khi context thay đổi, lần đánh giá tiếp theo có thể tạo collection chứa dữ liệu khác.

Khác với collection chỉ gồm literal hằng, collection có thành phần động không thể được coi là một tập giá trị bất biến của biểu thức. SpEL phải đánh giá các thành phần động theo dữ liệu hiện tại.

## 5. So sánh collection cố định và collection động

| Đặc điểm | Collection cố định | Collection động |
|---|---|---|
| Thành phần | Chỉ literal hằng | Có biến, property, phép tính hoặc method |
| Giá trị | Không phụ thuộc context | Phụ thuộc context của lần đánh giá |
| Xử lý | Có thể được tạo và cache khi parse | Các thành phần được đánh giá khi chạy |
| Dùng phù hợp | Tập trạng thái, nhãn, hằng số | Giá trị theo request hoặc object hiện tại |
| Lưu ý | Không dựa vào việc mỗi lần đánh giá có instance mới | Kiểm soát method call và dữ liệu đầu vào |

Ví dụ hai biểu thức:

~~~text
{'OPEN', 'CLOSED'}
{#currentState, #nextState}
~~~

Biểu thức đầu chỉ chứa literal string cố định. Biểu thức thứ hai phụ thuộc vào biến của context, nên kết quả thay đổi theo giá trị biến ở mỗi lượt đánh giá.

Không phải cứ viết collection literal trong ngoặc nhọn thì toàn bộ collection đều cố định. Chỉ cần một thành phần phụ thuộc dữ liệu động, biểu thức phải đánh giá thành phần đó khi chạy.

## 6. Collection lồng nhau

List có thể chứa list khác, map có thể chứa list hoặc map, và các collection có thể được lồng nhiều cấp:

~~~text
{{1, 2}, {3, 4}}
{'colors': {'red', 'blue'}, 'enabled': true}
{'profile': {'name': 'Lan', 'active': true}}
~~~

Ví dụ tạo list lồng nhau:

~~~java
Expression expression = parser.parseExpression(
        "{{1, 2}, {3, 4}}"
);

List<?> matrix = expression.getValue(List.class);
~~~

Có thể kết hợp thành phần cố định và động:

~~~text
{'user': #currentUser.name, 'roles': {'EDITOR', 'REVIEWER'}}
~~~

Ở đây key user có value động lấy từ currentUser, còn roles là list literal cố định. Cấu trúc này cho phép gom dữ liệu cần thiết vào một collection duy nhất.

Với cấu trúc lồng sâu, hãy đặt tên biến hoặc tách phần dữ liệu phức tạp ra Java nếu biểu thức trở nên khó đọc. Một collection literal ngắn giúp mô tả dữ liệu; một cây collection lớn có thể khiến biểu thức khó bảo trì và khó kiểm tra kiểu.

## 7. Collection literal rỗng

SpEL có cú pháp cho collection rỗng:

~~~text
{}
{:}
~~~

Cặp ngoặc nhọn rỗng biểu diễn list rỗng; cú pháp {:} biểu diễn map rỗng.

Ví dụ:

~~~java
List<?> emptyList =
        parser.parseExpression("{}").getValue(List.class);

Map<?, ?> emptyMap =
        parser.parseExpression("{:}").getValue(Map.class);
~~~

Collection rỗng hữu ích khi một biểu thức cần một giá trị collection nhưng hiện chưa có phần tử. Tuy nhiên, hãy kiểm tra kiểu mà code Java mong đợi và tránh giả định một collection rỗng tự mang thông tin kiểu phần tử cụ thể.

Nếu cần một collection có generic type rõ ràng, thường nên tạo nó trong Java hoặc chuyển đổi qua một API có kiểu cụ thể thay vì dựa vào kiểu suy ra từ một literal rỗng.

## 8. Dùng collection literal trong điều kiện

Inline list thường được dùng để kiểm tra một giá trị có thuộc tập cho phép hay không. Với một list được tạo trong biểu thức, có thể gọi method contains():

~~~text
{'DRAFT', 'REVIEW', 'PUBLISHED'}.contains(#order.status)
~~~

Ví dụ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Expression expression = parser.parseExpression(
        "{'DRAFT', 'REVIEW', 'PUBLISHED'}.contains(status)"
);

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

Biểu thức trả về true nếu status của order nằm trong tập trạng thái được liệt kê. Đây là cách gọn để biểu diễn một allowlist nhỏ.

Map literal cũng có thể dùng để tra cứu hoặc kiểm tra key:

~~~text
{'vi': 'Xin chào', 'en': 'Hello'}[#locale]
~~~

Trong ví dụ, giá trị locale xác định key được dùng để lấy lời chào tương ứng. Nếu key không tồn tại, kết quả tra cứu có thể là null; hãy xử lý trường hợp thiếu key theo yêu cầu của ứng dụng.

## 9. Dùng collection literal làm đối số method

Một inline list hoặc map có thể được truyền trực tiếp vào method:

~~~text
filterByStates({'OPEN', 'PENDING'})
configure({'timeout': 30, 'enabled': true})
~~~

Ví dụ Java:

~~~java
public List<Order> filterByStates(List<String> states) {
    // Lọc đơn hàng theo các trạng thái được truyền vào
    return orders.stream()
            .filter(order -> states.contains(order.getStatus()))
            .toList();
}
~~~

SpEL có thể gọi method tương ứng nếu MethodResolver tìm được signature phù hợp và cơ chế chuyển đổi kiểu hỗ trợ các đối số. Hãy kiểm tra kiểu phần tử và kiểu tham số thực tế; một collection literal không tự đảm bảo rằng generic type của Java được suy ra chính xác trong mọi trường hợp.

Khi truyền map literal vào method, hãy xác định rõ kiểu key/value mà method mong đợi. Nếu method yêu cầu Map<String, Integer>, dữ liệu trong literal nên nhất quán với hợp đồng đó.

## 10. Dùng biểu thức động và context theo từng lần đánh giá

Collection động có thể kết hợp nhiều nguồn dữ liệu trong context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("currency", "VND");
context.setVariable("includeTax", true);

Expression expression = parser.parseExpression(
        "{'orderId': #root.id, "
        + "'amount': #root.total, "
        + "'currency': #currency, "
        + "'taxIncluded': #includeTax}"
);

Map<?, ?> summary = expression.getValue(context, Map.class);
~~~

Mỗi lần đánh giá, map summary được xây dựng từ root object và các biến hiện có. Nếu một request khác có order hoặc currency khác, context của request đó tạo ra dữ liệu tương ứng.

Không dùng chung context mutable giữa các request đồng thời nếu biến và root object có thể bị thay đổi. Hãy tạo context cho từng lượt đánh giá hoặc quản lý dữ liệu đầu vào theo cách an toàn với concurrency.

Nếu collection literal có lời gọi method, hãy nhớ method đó có thể được thực thi mỗi lần collection được đánh giá. Tránh đặt method có side effect vào phần tử động nếu collection chỉ nhằm mô tả dữ liệu.

## 11. Phân biệt collection literal với array construction

Inline list và map tạo collection theo cú pháp SpEL. Nếu cần một Java array có kiểu phần tử cụ thể, SpEL có cú pháp tạo array riêng, dùng từ khóa new:

~~~text
new int[3]
new String[2]
new int[]{1, 2, 3}
~~~

Array khác List và Map ở kiểu dữ liệu, kích thước và API truy cập. List thường được truy cập theo indexer và có các method collection; Map được truy cập theo key; array có kiểu component và độ dài cố định sau khi tạo.

Ví dụ:

~~~java
Expression listExpression =
        parser.parseExpression("{1, 2, 3}");

Expression arrayExpression =
        parser.parseExpression("new int[]{1, 2, 3}");

List<?> values = listExpression.getValue(List.class);
int[] numbers = arrayExpression.getValue(int[].class);
~~~

Hãy chọn collection khi cần cấu trúc linh hoạt hoặc key-value. Chọn array khi API Java đích yêu cầu đúng kiểu array hoặc khi kiểu component là một phần của hợp đồng.

## 12. Kiểu dữ liệu của phần tử và chuyển đổi

Inline collection có thể chứa các giá trị khác kiểu:

~~~text
{'Lan', 25, true, null}
~~~

SpEL tạo collection chứa các giá trị với kiểu runtime tương ứng. Không nên giả định mọi phần tử được tự động chuyển về cùng một kiểu chỉ vì chúng nằm trong một list.

Với map, key và value cũng có thể có kiểu khác nhau:

~~~text
{1: 'one', '2': 2, true: 'enabled'}
~~~

Cấu trúc này hợp lệ về mặt biểu đạt nhưng có thể khó sử dụng nếu code Java mong đợi kiểu key/value đồng nhất. Với collection được truyền vào method hoặc gán cho property có generic type cụ thể, hãy chuẩn hóa kiểu dữ liệu và kiểm tra conversion.

Nếu biểu thức cần số decimal chính xác, hãy dùng BigDecimal literal có hậu tố M thay vì để số thực mặc định thành Double:

~~~text
{'price': 19.90M, 'quantity': 3M}
~~~

Kiểu phần tử ảnh hưởng đến phép toán và method được gọi sau đó. Hãy thiết kế collection theo đúng kiểu mà consumer mong đợi.

## 13. Cẩn trọng với collection động và side effect

Một collection literal động có thể chứa lời gọi method, property access hoặc biểu thức có side effect:

~~~text
{#service.nextId(), #service.nextId()}
~~~

Mỗi phần tử có thể kích hoạt một lời gọi method khi collection được đánh giá. Nếu method thay đổi trạng thái, gửi request hoặc ghi dữ liệu, việc đánh giá biểu thức có thể tạo side effect nhiều lần.

Một số nguyên tắc an toàn:

1. Dùng literal cố định cho các tập hằng nhỏ.
2. Dùng biến hoặc property cho dữ liệu động thay đổi theo request.
3. Tránh gọi method có side effect trong collection literal.
4. Không đưa service hoặc repository rộng quyền vào context nếu không cần.
5. Kiểm soát kiểu key/value trước khi truyền collection sang method khác.
6. Không sửa collection literal được dùng như dữ liệu cố định hoặc cache.
7. Dùng DTO hoặc tạo collection trong Java nếu cấu trúc dữ liệu phức tạp.

SpEL là ngôn ngữ biểu thức có thể gọi method và truy cập object. Collection literal không làm giảm quyền của các biểu thức được đặt bên trong nó.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Parser báo lỗi với list literal | Thiếu dấu phẩy hoặc ngoặc nhọn không cân bằng | Kiểm tra từng phần tử và dấu phân cách |
| Map literal không parse được | Thiếu dấu hai chấm giữa key/value | Kiểm tra từng cặp key:value |
| Giá trị không đổi giữa các lần đánh giá | Collection chỉ chứa literal cố định và được cache | Xác định thành phần nào cần động |
| Giá trị động không được cập nhật | Biến hoặc root object trong context không đổi như dự kiến | Kiểm tra context của mỗi lần getValue |
| Không tìm thấy key | Key thiếu hoặc khác kiểu | Kiểm tra key thực tế và kiểu runtime |
| Method không nhận collection | Kiểu đối số hoặc generic contract không tương thích | Kiểm tra signature và converter |
| Thay đổi collection gây ảnh hưởng ngoài dự kiến | Đang mutate một collection literal cố định hoặc object được chia sẻ | Tạo bản sao mutable trong Java nếu cần cập nhật |
| Biểu thức khó bảo trì | Collection lồng sâu hoặc nhiều method call | Tách dữ liệu phức tạp ra DTO/Java |

## 15. Ghi nhớ

Inline list dùng cú pháp {value1, value2}; inline map dùng các cặp {key: value}. Collection chỉ chứa literal hằng có thể được SpEL tạo và cache khi parse. Nếu một phần tử, key hoặc value phụ thuộc biến, property, phép tính hoặc method, phần đó được đánh giá theo context khi chạy.

Có thể lồng list và map, tạo collection rỗng, dùng collection trong điều kiện, tra cứu key hoặc truyền làm đối số method. Nếu cần array Java có kiểu component cụ thể, dùng cú pháp new array thay vì nhầm inline list với array.

Hãy phân biệt dữ liệu cố định với dữ liệu động, giữ kiểu phần tử nhất quán, tránh side effect trong method call và chỉ dùng collection literal cho cấu trúc đủ nhỏ để đọc, kiểm tra và bảo trì ngay trong biểu thức.