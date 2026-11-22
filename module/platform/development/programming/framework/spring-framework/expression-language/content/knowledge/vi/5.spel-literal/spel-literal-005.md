# Literal mảng, list và map

Spring Expression Language (SpEL) cung cấp cú pháp tạo các cấu trúc dữ liệu ngay trong biểu thức. Ta có thể tạo inline list, inline map và cấp phát mảng Java mà không cần viết một đoạn Java riêng cho từng giá trị. Các cấu trúc này hữu ích khi truyền argument cho method, xây dựng dữ liệu đầu vào, truy cập phần tử hoặc kết hợp nhiều giá trị trong một biểu thức.

Cần phân biệt ba khái niệm:

- **Mảng Java (array):** có kiểu phần tử xác định và kích thước cố định sau khi tạo.
- **Inline list:** cú pháp SpEL dùng dấu ngoặc nhọn để tạo một đối tượng List.
- **Inline map:** cú pháp SpEL dùng cặp key-value để tạo một đối tượng Map.

Dấu ngoặc nhọn trong SpEL không mặc nhiên có nghĩa là Java array initializer. **{1, 2, 3}** tạo inline list; để tạo mảng Java, dùng cú pháp cấp phát như **new int[3]**.

## 1. Inline list

### 1.1. Cú pháp cơ bản

Inline list được viết bằng dấu ngoặc nhọn, các phần tử phân cách bởi dấu phẩy:

~~~java
{1, 2, 3}
~~~

Có thể phân tích và lấy kết quả trực tiếp:

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<?> numbers = parser
        .parseExpression("{1, 2, 3}")
        .getValue(List.class);
~~~

Kết quả là một List chứa ba giá trị số. Kiểu cụ thể của phần tử phụ thuộc literal được dùng trong biểu thức và quy tắc suy luận kiểu của SpEL.

Inline list có thể chứa các kiểu literal khác nhau:

~~~java
{'Spring', 'SpEL', 'Expression'}
{10, 20.5, 30}
{true, false, null}
~~~

Không nên trộn nhiều kiểu nếu mục đích của list yêu cầu một kiểu phần tử thống nhất. Nếu list được gán vào property có kiểu cụ thể, khả năng chuyển đổi còn phụ thuộc TypeConverter và metadata kiểu đích.

### 1.2. List rỗng

SpEL biểu diễn list rỗng bằng cặp ngoặc nhọn không có phần tử:

~~~java
{}
~~~

Ví dụ:

~~~java
List<?> empty = parser
        .parseExpression("{}")
        .getValue(List.class);
~~~

Khi đọc biểu thức, cần phân biệt **{}** với **{:}**. Cú pháp thứ nhất là inline list rỗng; cú pháp thứ hai là inline map rỗng.

### 1.3. List lồng nhau

Một phần tử của list có thể là một inline list khác:

~~~java
{{1, 2}, {3, 4}, {5, 6}}
~~~

Đây là một list gồm ba list con. Có thể truy cập phần tử theo chỉ số:

~~~java
parser.parseExpression("{{1, 2}, {3, 4}}[1][0]")
        .getValue(Integer.class);
~~~

Kết quả là **3**: chỉ số **1** chọn list con thứ hai, chỉ số **0** chọn phần tử đầu tiên trong list con đó.

Chỉ số của list bắt đầu từ 0. Truy cập chỉ số âm hoặc vượt quá giới hạn có thể phát sinh lỗi khi đánh giá biểu thức.

### 1.4. Kết hợp literal và biểu thức động

Inline list không bắt buộc mọi phần tử phải là literal cố định. Phần tử có thể là property, biến, phép toán hoặc một biểu thức SpEL khác:

~~~java
List<?> values = parser
        .parseExpression("{1, order.total, order.quantity * 2}")
        .getValue(context, List.class);
~~~

Trong ví dụ này, **order.total** và **order.quantity * 2** được đánh giá theo context. Giá trị trong list vì thế phụ thuộc root object hoặc biến đang có tại thời điểm đánh giá.

Có thể lồng list với các biểu thức con:

~~~java
{
    order.id,
    order.customer.name,
    order.items[0].productCode
}
~~~

Khi biểu thức dài, nên xuống dòng và giữ cấu trúc rõ ràng để dễ xác định phần tử nào gây lỗi.

### 1.5. List literal cố định và tối ưu của SpEL

Vì lý do hiệu năng, SpEL có thể tạo một constant list khi tất cả phần tử của inline list đều là literal cố định. Khi biểu thức được đánh giá nhiều lần, parser có thể tái sử dụng giá trị constant thay vì tạo lại list ở mỗi lần.

Điều này có một hệ quả thực tế: không nên giả định mỗi lần gọi **getValue()** sẽ trả về một list mới để ứng dụng tùy ý thay đổi. Hãy xem kết quả inline list như dữ liệu đầu vào của biểu thức và tránh sửa đổi nó. Nếu nghiệp vụ cần collection mutable có vòng đời riêng, hãy tạo collection trong Java hoặc thông qua một factory được kiểm soát.

Khi list chứa property hoặc biểu thức động, giá trị phần tử cần được đánh giá theo context hiện tại; không áp dụng suy luận rằng toàn bộ list luôn là một constant.

## 2. Inline map

### 2.1. Cú pháp key-value

Inline map dùng dấu ngoặc nhọn, mỗi cặp gồm key, dấu hai chấm và value; các cặp phân cách bằng dấu phẩy:

~~~java
{'name': 'An', 'active': true, 'level': 3}
~~~

Có thể lấy kết quả dưới kiểu Map:

~~~java
Map<?, ?> user = parser
        .parseExpression("{'name': 'An', 'active': true, 'level': 3}")
        .getValue(Map.class);
~~~

Trong ví dụ, các key là chuỗi và các value gồm String, Boolean và số. Đây là cách tạo một cấu trúc key-value ngắn gọn để truyền cho method hoặc dùng trong biểu thức tiếp theo.

### 2.2. Map rỗng

Inline map rỗng dùng cú pháp đặc biệt:

~~~java
{:}
~~~

Ví dụ:

~~~java
Map<?, ?> emptyMap = parser
        .parseExpression("{:}")
        .getValue(Map.class);
~~~

Không nhầm cú pháp này với **{}**, vốn biểu diễn list rỗng.

### 2.3. Truy cập phần tử theo key

Có thể lấy value từ map bằng indexer:

~~~java
parser.parseExpression("{'name': 'An', 'age': 25}['name']")
        .getValue(String.class);
~~~

Kết quả là chuỗi **An**.

Nếu map nằm trong root object, truy cập tương tự:

~~~java
settings['timeout']
settings['language']
~~~

Với key là chuỗi, hãy đặt key trong dấu nháy khi viết biểu thức. Cách này giúp phân biệt rõ tên key với property hoặc biến mà SpEL cần phân giải.

### 2.4. Value có thể là biểu thức

Map có thể kết hợp dữ liệu tĩnh với giá trị lấy từ context:

~~~java
{
    'customerId': customer.id,
    'customerName': customer.name,
    'total': order.total,
    'eligible': order.total >= 100
}
~~~

Mỗi value được đánh giá như một biểu thức SpEL. Do đó, map có thể đóng vai trò như một object dữ liệu trung gian để truyền vào method hoặc tạo kết quả cho một quy tắc nghiệp vụ.

Key cũng là thành phần của biểu thức. Trong trường hợp thông thường, nên dùng key literal dễ đọc, đặc biệt là String. Tránh tạo key phức tạp nếu không có nhu cầu rõ ràng vì điều đó làm biểu thức khó đọc và khó chẩn đoán.

### 2.5. Map lồng nhau

Có thể đặt inline map hoặc inline list bên trong value:

~~~java
{
    'customer': {
        'id': 1001,
        'name': 'An'
    },
    'permissions': {'READ', 'WRITE'},
    'preferences': {
        'language': 'vi',
        'notifications': true
    }
}
~~~

Cấu trúc này là một map có value gồm các map và list con. Truy cập các phần tử lồng nhau bằng cách kết hợp indexer:

~~~java
{
    'customer': {'id': 1001, 'name': 'An'},
    'permissions': {'READ', 'WRITE'}
}['customer']['name']
~~~

Kết quả là **An**.

Với cấu trúc nhiều tầng, nên tách biểu thức thành nhiều phần hoặc chuẩn bị dữ liệu trong Java nếu việc truy cập và biến đổi trở nên phức tạp.

### 2.6. Map literal cố định

Tương tự inline list, SpEL có thể tối ưu inline map mà mọi key và value đều là literal cố định bằng cách tạo constant map. Không nên phụ thuộc vào giả định mỗi lần đánh giá sẽ nhận được một map mới để mutate.

Nếu map cần được thay đổi theo request, cần thêm phần tử hoặc giữ trạng thái lâu dài, hãy quản lý map đó trong Java và truyền vào evaluation context. Inline map phù hợp hơn với cấu trúc dữ liệu được tạo ra để phục vụ một lần đánh giá biểu thức.

## 3. Tạo mảng Java

### 3.1. Cú pháp cấp phát mảng

SpEL hỗ trợ array construction bằng từ khóa **new**, tên kiểu phần tử và kích thước mảng:

~~~java
new int[3]
~~~

Biểu thức này tạo một mảng **int** có ba phần tử. Vì đây là mảng primitive, các phần tử ban đầu có giá trị mặc định là **0**.

Có thể tạo mảng tham chiếu:

~~~java
new java.lang.String[2]
~~~

Mảng String có hai phần tử và mỗi phần tử ban đầu là **null**.

Ví dụ lấy kết quả:

~~~java
int[] numbers = parser
        .parseExpression("new int[3]")
        .getValue(int[].class);
~~~

Kết quả là một Java array thực sự, không phải List.

### 3.2. Giá trị mặc định và kích thước

Giá trị mặc định phụ thuộc kiểu phần tử:

| Kiểu phần tử | Giá trị mặc định |
|---|---|
| **int**, **long**, **short**, **byte** | **0** |
| **float**, **double** | **0.0** |
| **boolean** | **false** |
| **char** | Ký tự null |
| Kiểu tham chiếu như String hoặc đối tượng miền | **null** |

Kích thước được xác định khi cấp phát. Mảng Java không tự tăng hoặc giảm số phần tử như collection.

Kích thước không hợp lệ, chẳng hạn số âm, sẽ gây lỗi khi đánh giá. Ứng dụng cũng nên giới hạn kích thước nếu biểu thức đến từ nguồn không tin cậy để tránh cấp phát mảng quá lớn.

### 3.3. Mảng nhiều chiều

SpEL hỗ trợ cấp phát mảng nhiều chiều:

~~~java
new int[2][3]
~~~

Biểu thức tạo mảng hai chiều gồm hai hàng, mỗi hàng có ba phần tử. Sau khi mảng được gán vào property của root object, có thể truy cập một phần tử bằng hai chỉ số:

~~~java
matrix[1][2]
~~~

Chỉ số **1** chọn hàng thứ hai, chỉ số **2** chọn phần tử thứ ba của hàng đó.

Có thể tạo mảng ba chiều bằng ba kích thước:

~~~java
new int[2][3][4]
~~~

Để dễ đọc, nên gán mảng vào property của root object rồi truy cập theo từng chiều. Tất cả chỉ số mảng đều bắt đầu từ 0.

### 3.4. Mảng không giống inline list

Hai biểu thức sau tạo ra hai kiểu kết quả khác nhau:

~~~java
{1, 2, 3}
new int[3]
~~~

- **{1, 2, 3}** là inline list, có kiểu collection.
- **new int[3]** là mảng Java kiểu **int[]**, gồm ba giá trị **0** ban đầu.

Không nên dùng dấu ngoặc nhọn của inline list như thể đó là Java array initializer. Nếu cần mảng đã có dữ liệu cụ thể, có thể chuẩn bị mảng trong Java rồi đặt vào root object hoặc biến của context. Sau đó SpEL truy cập các phần tử như một mảng thông thường.

## 4. Truy cập và cập nhật phần tử

### 4.1. Truy cập theo chỉ số

SpEL dùng indexer để truy cập phần tử của array hoặc list:

~~~java
numbers[0]
items[1]
matrix[0][2]
~~~

Chỉ số bắt đầu từ 0. Khi chỉ số nằm ngoài phạm vi, việc đánh giá có thể thất bại. Nếu index được tính từ property hoặc biến, cần kiểm tra dữ liệu đầu vào để tránh lỗi runtime.

Ví dụ với root object:

~~~java
Expression expression =
        parser.parseExpression("quantities[1]");

Integer secondQuantity =
        expression.getValue(context, Integer.class);
~~~

Kết quả phụ thuộc property **quantities** là array hay list và giá trị tại vị trí thứ hai.

### 4.2. Truy cập map bằng key

Với map, indexer nhận key:

~~~java
settings['timeout']
settings['language']
~~~

Nếu key không tồn tại, kết quả có thể là **null** tùy loại map và accessor. Nếu biểu thức tiếp tục truy cập property của giá trị null, lỗi đánh giá có thể xuất hiện. Nên kiểm tra key hoặc dùng biểu thức điều kiện phù hợp trước khi truy cập sâu.

### 4.3. Cập nhật phần tử bằng setValue

Khi expression trỏ đến vị trí có thể ghi trong root object, có thể dùng **setValue** để cập nhật phần tử:

~~~java
Expression expression =
        parser.parseExpression("quantities[1]");

expression.setValue(context, 25);
~~~

Tương tự, có thể cập nhật phần tử list hoặc value trong map:

~~~java
parser.parseExpression("items[0]").setValue(context, newItem);

parser.parseExpression("settings['timeout']")
        .setValue(context, 30);
~~~

Các ví dụ này giả định root object cung cấp property tương ứng và collection/mảng có thể thay đổi. Việc ghi vẫn phụ thuộc khả năng truy cập của property accessor, kiểu phần tử và TypeConverter đang cấu hình.

Không phải mọi kết quả inline đều thích hợp để cập nhật. Nếu inline list hoặc map được tối ưu thành constant, không nên dựa vào việc nó có thể mutate. Với dữ liệu cần cập nhật, hãy dùng collection hoặc array do ứng dụng quản lý và đặt trong context.

## 5. Kết hợp list, map và array trong một biểu thức

Một biểu thức có thể lồng nhiều cấu trúc để mô tả dữ liệu phức tạp:

~~~java
{
    'code': order.id,
    'lines': {
        {
            'product': order.items[0].productCode,
            'quantity': order.items[0].quantity
        },
        {
            'product': order.items[1].productCode,
            'quantity': order.items[1].quantity
        }
    },
    'tags': {'priority', 'online'},
    'valid': order.total > 0
}
~~~

Đây là map ngoài cùng, trong đó **lines** là list các map con, **tags** là list và **valid** là một biểu thức Boolean. Cấu trúc như vậy có thể hữu ích khi tạo argument cho một method nhận dữ liệu dạng Map.

Tuy nhiên, không nên biến SpEL thành ngôn ngữ xây dựng object quá lớn. Nếu biểu thức chứa nhiều tầng lồng nhau, nhiều điều kiện hoặc lặp lại cùng một phép truy cập, hãy cân nhắc chuyển phần tạo dữ liệu sang Java. SpEL phù hợp với biểu thức ngắn, rõ nghĩa và có phạm vi quyền hạn được kiểm soát.

## 6. Chuyển đổi kiểu giữa list, map và array

Inline list và inline map là collection; array là kiểu dữ liệu Java riêng. Việc chuyển từ một loại sang loại khác phụ thuộc TypeConverter và ConversionService của context hoặc cách ứng dụng lấy kết quả.

Ví dụ, nếu cần một mảng int từ dữ liệu list, không nên giả định mọi cấu hình SpEL đều tự động chuyển đổi được:

~~~java
Object value = parser
        .parseExpression("{1, 2, 3}")
        .getValue(context);
~~~

Có thể yêu cầu kiểu kết quả mong muốn:

~~~java
int[] values = parser
        .parseExpression("{1, 2, 3}")
        .getValue(context, int[].class);
~~~

Việc chuyển đổi chỉ thành công khi TypeConverter hỗ trợ kiểu nguồn và kiểu đích tương ứng. Nếu cần quy tắc chuyển đổi đặc biệt, đăng ký converter phù hợp trên ConversionService và cấu hình StandardTypeConverter cho context.

Với collection generic, metadata kiểu phần tử cũng quan trọng. Ví dụ, **List<String>** và **List<Integer>** có cùng raw type là List nhưng yêu cầu chuyển đổi phần tử khác nhau. Nếu chuyển dữ liệu cho property generic, cần bảo đảm TypeDescriptor và converter có đủ thông tin về kiểu đích.

Đối với map, cần kiểm soát cả kiểu key và kiểu value. Một map có key String không thể mặc nhiên dùng như map có key CustomerId nếu không có quy tắc chuyển đổi tương ứng.

## 7. Ví dụ hoàn chỉnh với root object

Ví dụ sau dùng một bean chứa array, list và map để minh họa cách SpEL đọc các cấu trúc dữ liệu:

~~~java
import java.util.List;
import java.util.Map;

public class ReportData {

    private final int[] scores = {80, 90, 95};
    private final List<String> names =
            List.of("An", "Binh", "Chi");
    private final Map<String, Object> settings =
            Map.of("language", "vi", "enabled", true);

    public int[] getScores() {
        return scores;
    }

    public List<String> getNames() {
        return names;
    }

    public Map<String, Object> getSettings() {
        return settings;
    }
}
~~~

Tạo context và đánh giá các biểu thức:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(new ReportData());

Integer firstScore = parser
        .parseExpression("scores[0]")
        .getValue(context, Integer.class);

String secondName = parser
        .parseExpression("names[1]")
        .getValue(context, String.class);

String language = parser
        .parseExpression("settings['language']")
        .getValue(context, String.class);

Boolean enabled = parser
        .parseExpression("settings['enabled']")
        .getValue(context, Boolean.class);
~~~

Kết quả lần lượt là **80**, **Binh**, **vi** và **true**.

Có thể tạo cấu trúc dữ liệu mới dựa trên root object:

~~~java
Map<?, ?> summary = parser
        .parseExpression(
                "{'firstScore': scores[0], " +
                "'secondName': names[1], " +
                "'language': settings['language']}"
        )
        .getValue(context, Map.class);
~~~

Ở đây map được tạo từ các giá trị runtime của root object. Nếu đánh giá với một root object khác, các value có thể thay đổi theo dữ liệu tương ứng.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dùng **{}** nhưng mong đợi Map | **{}** là inline list rỗng | Dùng **{:}** để tạo map rỗng |
| Dùng **{1,2,3}** nhưng cần array | Cú pháp này tạo List | Dùng array construction hoặc truyền array từ Java |
| Truy cập phần tử ngoài phạm vi | Index âm hoặc lớn hơn giới hạn | Kiểm tra kích thước trước khi đánh giá |
| Không lấy được map value | Key sai hoặc không tồn tại | Kiểm tra chính xác key và kiểu key |
| Chuyển list sang array thất bại | TypeConverter không hỗ trợ chuyển đổi | Cấu hình ConversionService hoặc chuyển đổi trong Java |
| Cập nhật phần tử thất bại | Collection không mutable hoặc property không ghi được | Kiểm tra quyền ghi và vòng đời collection |
| Biểu thức lồng nhau khó parse | Thiếu dấu ngoặc, dấu phẩy hoặc dấu hai chấm | Kiểm tra từng cặp cấu trúc và tách biểu thức để thử |

Khi debug, nên parse từng cấu trúc nhỏ trước. Ví dụ, kiểm tra riêng inline list, sau đó kiểm tra map, rồi mới lồng chúng lại. Cách này giúp xác định lỗi nằm ở cú pháp, kiểu kết quả hay dữ liệu runtime.

## 9. Hiệu năng và an toàn

### 9.1. Không tạo cấu trúc quá lớn trong biểu thức

Inline list/map có thể làm biểu thức ngắn gọn, nhưng tạo collection lớn trực tiếp trong biểu thức sẽ khiến chuỗi khó đọc và khó kiểm soát tài nguyên. Với dữ liệu lớn, hãy chuẩn bị ở Java rồi truyền vào context.

Kích thước array cũng nên được giới hạn. Một biểu thức có thể hợp lệ về cú pháp nhưng yêu cầu cấp phát mảng quá lớn khi đánh giá.

### 9.2. Không mutate collection constant

Với inline list/map gồm các literal cố định, SpEL có thể tạo constant collection để tối ưu. Không nên sửa đổi các collection này hoặc dựa vào giả định rằng mỗi lần đánh giá có một instance mới.

Nếu cần thêm/xóa phần tử, dùng collection mutable do ứng dụng sở hữu. Đừng dùng biểu thức như nơi lưu trữ trạng thái giữa các lần đánh giá.

### 9.3. Kiểm soát biểu thức do người dùng cung cấp

Nếu người dùng có thể nhập SpEL, cần giới hạn kích thước và độ phức tạp biểu thức, các type được phép tham chiếu và những thao tác mà EvaluationContext cung cấp. Không cho phép biểu thức tùy ý cấp phát array lớn hoặc truy cập object nhạy cảm chỉ vì cú pháp parse hợp lệ.

Cần nhớ rằng inline list/map là cấu trúc dữ liệu của biểu thức, không phải ranh giới bảo mật. Quyền truy cập thực tế vẫn phụ thuộc root object, property accessor, method resolver, type locator và các dịch vụ khác trong context.

## 10. Chọn cấu trúc dữ liệu phù hợp

| Nhu cầu | Cấu trúc nên dùng | Cú pháp SpEL |
|---|---|---|
| Danh sách phần tử có thể truy cập theo chỉ số | List | **{1, 2, 3}** |
| Danh sách lồng nhau | List of lists | **{{1, 2}, {3, 4}}** |
| Dữ liệu key-value | Map | **{'name': 'An', 'active': true}** |
| Map rỗng | Map | **{:}** |
| List rỗng | List | **{}** |
| Vùng nhớ có kiểu phần tử và kích thước cố định | Java array | **new int[3]** |
| Mảng nhiều chiều | Java multidimensional array | **new int[2][3]** |
| Collection cần thay đổi lâu dài | Collection do Java quản lý | Truyền qua root object/context |

## 11. Tổng kết

SpEL hỗ trợ ba cấu trúc dữ liệu với mục đích khác nhau:

- **Inline list** dùng **{...}** để tạo List; **{}** là list rỗng.
- **Inline map** dùng cặp **key: value**; **{:}** là map rỗng.
- **Array construction** dùng **new Type[size]** để tạo mảng Java có kiểu phần tử và kích thước xác định.

Hãy dùng list và map để biểu diễn dữ liệu ngắn gọn ngay trong biểu thức; dùng array khi cần kiểu mảng Java; và dùng collection do ứng dụng quản lý khi cần cập nhật hoặc giữ trạng thái. Khi chuyển đổi kiểu giữa các cấu trúc, kiểm tra TypeConverter và ConversionService thay vì giả định SpEL tự chuyển đổi mọi trường hợp.