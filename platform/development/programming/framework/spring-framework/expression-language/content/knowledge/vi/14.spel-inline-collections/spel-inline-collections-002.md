# Tạo list inline và danh sách lồng nhau

## Mục tiêu

Sau bài này, bạn có thể tạo một List ngay trong biểu thức Spring Expression Language (SpEL) bằng cú pháp inline list; sử dụng danh sách rỗng, danh sách một phần tử và danh sách có nhiều phần tử; lồng các list để biểu diễn dữ liệu nhiều chiều; và kết hợp giá trị cố định với biến hoặc biểu thức động. Bạn cũng sẽ biết cách đọc phần tử, dùng list trong điều kiện, phân biệt inline list với selection/projection và xử lý dữ liệu null hoặc sai cấu trúc.

## 1. Inline list là gì?

Inline list là cú pháp tạo một danh sách ngay trong biểu thức SpEL bằng cặp dấu ngoặc nhọn. Các phần tử được phân tách bằng dấu phẩy:

~~~text
{'An', 'Binh', 'Chi'}
~~~

Biểu thức trên tạo ra một List gồm ba chuỗi theo đúng thứ tự đã khai báo. Có thể gán kết quả cho biến Java kiểu List:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("{'An', 'Binh', 'Chi'}");

List<?> names = expression.getValue(List.class);
~~~

Inline list hữu ích khi một biểu thức cần tập hợp một số giá trị để trả về, truyền cho một phương thức, kiểm tra thành viên hoặc dùng làm dữ liệu trung gian. Danh sách được tạo trong bộ nhớ trong quá trình đánh giá biểu thức; cú pháp này không truy vấn cơ sở dữ liệu và không tự tải dữ liệu từ bên ngoài.

Cặp ngoặc nhọn trong inline list là cú pháp của SpEL. Khi viết chuỗi biểu thức trong Java, chuỗi ngoài thường dùng dấu ngoặc kép, còn literal chuỗi bên trong SpEL có thể dùng dấu nháy đơn.

## 2. Danh sách rỗng, một phần tử và nhiều phần tử

SpEL hỗ trợ các dạng inline list thông dụng:

~~~text
{}
{'SPRING'}
{'JAVA', 'SPRING', 'KOTLIN'}
~~~

- `{}` tạo một danh sách rỗng.
- `{'SPRING'}` tạo danh sách có một phần tử.
- Danh sách nhiều phần tử giữ nguyên thứ tự được viết trong biểu thức.

Một phần tử không cần là chuỗi. Inline list có thể chứa số, boolean, null hoặc các giá trị được đánh giá từ biểu thức:

~~~text
{10, 20, 30}
{true, false}
{'A', null, 'C'}
~~~

Danh sách có thể chứa nhiều kiểu dữ liệu nếu biểu thức yêu cầu. Tuy nhiên, nếu danh sách đại diện cho một tập dữ liệu nghiệp vụ, nên giữ kiểu phần tử nhất quán để mã Java sử dụng kết quả dễ dự đoán hơn.

Một phần tử null vẫn là một phần tử trong danh sách. Nó khác với trường hợp danh sách không có phần tử ở vị trí đó. Khi đọc hoặc gọi phương thức trên phần tử null, ứng dụng cần xử lý null theo cách phù hợp.

## 3. Phần tử có thể là biểu thức

Các phần tử của inline list có thể là literal cố định hoặc biểu thức được SpEL đánh giá. Ví dụ:

~~~text
{#primaryColor, #secondaryColor, #fallbackColor}
~~~

Mỗi biến được lấy từ EvaluationContext. Có thể trộn giá trị cố định với giá trị động:

~~~text
{'DEFAULT', #userPreference, #systemFallback}
~~~

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("{'DEFAULT', #preferred, #fallback}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("preferred", "DARK");
context.setVariable("fallback", "LIGHT");

List<?> themes = expression.getValue(context, List.class);
~~~

Kết quả là danh sách gồm ba giá trị theo thứ tự: DEFAULT, DARK và LIGHT.

Nếu biến chưa được đăng ký, tên thuộc tính không tồn tại hoặc một biểu thức con không thể đánh giá, toàn bộ lần đánh giá inline list có thể thất bại. Vì vậy, hãy cung cấp đầy đủ biến và root object mà các phần tử cần dùng.

## 4. Dùng thuộc tính của root object trong inline list

Inline list có thể lấy dữ liệu từ root object, giống các biểu thức SpEL khác:

~~~text
{customer.id, customer.name, customer.email}
~~~

Nếu biểu thức được đánh giá với một Customer làm root object, SpEL đọc ba thuộc tính và tạo danh sách kết quả.

Có thể dùng safe navigation nếu một thuộc tính trung gian có thể null:

~~~text
{order.id, order.customer?.name, order.customer?.email}
~~~

Khi customer là null, hai phần tử tương ứng nhận giá trị null thay vì cố đọc tiếp thuộc tính trên tham chiếu null. Safe navigation chỉ bảo vệ các bước được viết với toán tử `?.`; nếu một đường dẫn có nhiều cấp nullable, cần đặt toán tử tại từng bước phù hợp.

Ví dụ này vẫn giữ phần tử null trong danh sách. Nếu yêu cầu là bỏ hẳn phần tử thiếu khỏi kết quả, cần dùng một phép lọc hoặc xây dựng danh sách ở Java theo quy tắc nghiệp vụ.

## 5. Tạo danh sách lồng nhau

Một inline list có thể chứa các inline list khác. Đây là cách biểu diễn danh sách nhiều chiều hoặc nhóm dữ liệu:

~~~text
{{'A', 'B'}, {'C', 'D'}}
~~~

Biểu thức trên tạo một danh sách ngoài có hai phần tử; mỗi phần tử là một danh sách con:

- Danh sách con thứ nhất gồm A và B.
- Danh sách con thứ hai gồm C và D.

Có thể dùng cấu trúc này để biểu diễn bảng nhỏ, nhóm lựa chọn hoặc dữ liệu theo hàng:

~~~text
{{'Tên', 'Vai trò'}, {'An', 'Admin'}, {'Binh', 'Editor'}}
~~~

Mỗi danh sách con có thể đại diện cho một hàng. Danh sách ngoài giữ thứ tự các hàng; danh sách con giữ thứ tự các cột.

SpEL không tự áp đặt số phần tử của các danh sách con phải bằng nhau. Nếu một danh sách con có ít phần tử hơn, cấu trúc vẫn có thể được tạo, nhưng mã sử dụng kết quả phải xử lý sự khác biệt đó.

## 6. Truy cập phần tử trong danh sách lồng nhau

Kết quả inline list có thể được truy cập bằng indexer như các List khác. Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("{{'A', 'B'}, {'C', 'D'}}");

List<?> matrix = expression.getValue(List.class);
~~~

Sau khi có danh sách, có thể truy cập theo chỉ số bằng SpEL nếu đưa danh sách vào context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("matrix", matrix);

Expression cell =
    parser.parseExpression("#matrix[1][0]");

String value = cell.getValue(context, String.class);
~~~

Kết quả là C: chỉ số 1 chọn danh sách con thứ hai, sau đó chỉ số 0 chọn phần tử đầu tiên của danh sách con đó.

Chỉ số bắt đầu từ 0 ở mọi cấp. Mỗi lần truy cập cần bảo đảm danh sách hiện tại khác null và chỉ số nằm trong phạm vi của chính danh sách đó.

## 7. Danh sách lồng có độ sâu nhiều cấp

Có thể lồng nhiều hơn hai cấp nếu cấu trúc dữ liệu cần thiết:

~~~text
{
    {
        {'A1', 'A2'},
        {'B1', 'B2'}
    },
    {
        {'C1', 'C2'},
        {'D1', 'D2'}
    }
}
~~~

Đây là danh sách ngoài chứa các nhóm; mỗi nhóm chứa các hàng; mỗi hàng chứa các giá trị. Cấu trúc tương tự một mảng ba chiều, nhưng các phần tử ở đây là các List lồng nhau.

Không nên lồng sâu chỉ để làm biểu thức ngắn. Khi cấu trúc có nhiều tầng, hãy đặt tên cho các phần dữ liệu trong Java hoặc dùng một lớp mô hình có thuộc tính rõ ràng. Danh sách lồng phù hợp với dữ liệu nhỏ, có cấu trúc đơn giản và được dùng trực tiếp trong biểu thức.

## 8. Kết hợp inline list với điều kiện và phương thức

Inline list có thể được dùng cùng các toán tử và phương thức của List. Ví dụ, kiểm tra trạng thái có nằm trong nhóm được chấp nhận:

~~~text
{'PAID', 'SHIPPED', 'DELIVERED'}.contains(#order.status)
~~~

Nếu status là một trong ba chuỗi được liệt kê, biểu thức trả về true.

Có thể dùng biến list đã được truyền vào context:

~~~text
#allowedStatuses.contains(#order.status)
~~~

Java:

~~~java
context.setVariable(
    "allowedStatuses",
    List.of("PAID", "SHIPPED", "DELIVERED")
);

Expression expression =
    parser.parseExpression("#allowedStatuses.contains(#order.status)");

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

Inline list cũng có thể là một phần của biểu thức điều kiện lớn hơn:

~~~text
#order != null and
{'PAID', 'SHIPPED'}.contains(#order.status)
~~~

Hãy nhớ rằng lời gọi `contains(...)` là một lời gọi phương thức trên List. Nó cần được EvaluationContext cho phép theo cơ chế method resolution đang dùng. Nếu context hạn chế không cho gọi phương thức, hãy chọn cách diễn đạt hoặc cấu hình phù hợp với chính sách của ứng dụng.

## 9. Inline list khác selection và projection

Ba cú pháp này có mục đích khác nhau:

| Cú pháp | Vai trò | Ví dụ |
|---|---|---|
| Inline list `{...}` | Tạo một danh sách mới từ các phần tử được khai báo | `{'A', 'B'}` |
| Selection `.?[...]` | Lọc các phần tử của collection đang có | `#orders.?[total > 100]` |
| Projection `.![...]` | Tạo collection kết quả bằng cách đánh giá biểu thức cho từng phần tử | `#orders.![id]` |

Inline list khai báo những phần tử sẽ có trong danh sách. Selection và projection thao tác trên một collection đầu vào.

Ví dụ, có thể tạo một danh sách mã trạng thái cố định:

~~~text
{'PAID', 'SHIPPED'}
~~~

Còn nếu cần lấy mã của các đơn hàng đã thanh toán từ dữ liệu đang có:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Không nên nhầm dấu ngoặc nhọn của inline list với dấu ngoặc vuông của selection hoặc projection. Chúng giải quyết các nhiệm vụ khác nhau và có thể được kết hợp trong một biểu thức nếu cần.

## 10. Inline list cố định và biểu thức động

SpEL có thể tối ưu danh sách chỉ chứa các literal cố định. Danh sách chỉ gồm giá trị cố định có thể được tạo ngay trong giai đoạn phân tích biểu thức và tái sử dụng khi đánh giá.

Ví dụ:

~~~text
{'DEV', 'TEST', 'PROD'}
~~~

Ngược lại, nếu danh sách chứa biến hoặc biểu thức cần tính tại runtime:

~~~text
{#environment, #tenant, #defaultEnvironment}
~~~

các phần tử phải được đánh giá khi biểu thức chạy để tạo ra kết quả tương ứng với context hiện tại.

Điều này có nghĩa cùng một đối tượng Expression có thể được phân tích một lần nhưng cho kết quả khác nhau khi các biến trong EvaluationContext thay đổi:

~~~java
Expression expression =
    parser.parseExpression("{#first, #second}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("first", "A");
context.setVariable("second", "B");

List<?> firstResult = expression.getValue(context, List.class);

context.setVariable("first", "X");
context.setVariable("second", "Y");

List<?> secondResult = expression.getValue(context, List.class);
~~~

Lần đánh giá đầu tạo danh sách A, B; lần sau sử dụng các giá trị mới X, Y. Không nên dựa vào identity hoặc khả năng sửa đổi của đối tượng List được trả về như một phần hợp đồng của inline list. Nếu ứng dụng cần một collection có vòng đời hoặc chính sách mutation cụ thể, hãy tạo và quản lý nó trong Java.

## 11. Kiểu dữ liệu và chuyển đổi phần tử

Inline list có thể chứa các phần tử khác kiểu. Ví dụ:

~~~text
{'SPRING', 6, true, null}
~~~

Kết quả là một List chứa chuỗi, số, boolean và null. Khi nhận kết quả ở Java, kiểu tổng quát phù hợp thường là List<?> hoặc List<Object>.

Nếu cần danh sách có kiểu phần tử cụ thể, hãy bảo đảm từng biểu thức con trả về kiểu tương thích:

~~~text
{#primaryId, #secondaryId, #fallbackId}
~~~

Nếu ba biến đại diện cho ID, nên cung cấp chúng cùng kiểu hoặc kiểu có thể chuyển đổi nhất quán.

Việc yêu cầu kiểu kết quả là List.class chỉ xác nhận đối tượng kết quả có thể được chuyển đổi thành List. Nó không kiểm tra rằng tất cả phần tử bên trong đều có cùng kiểu. Nếu cần bảo đảm kiểu phần tử, hãy kiểm tra hoặc chuyển đổi trong Java sau khi đánh giá.

## 12. Lỗi thường gặp khi tạo list inline

Một số lỗi thường xuất hiện khi viết inline list:

- Thiếu dấu ngoặc nhọn đóng.
- Thiếu dấu phẩy giữa hai phần tử.
- Dùng dấu nháy không cân bằng trong literal chuỗi.
- Tham chiếu biến chưa được đăng ký trong EvaluationContext.
- Truy cập thuộc tính trên đối tượng null.
- Lồng list nhưng giả định mọi danh sách con đều có cùng kích thước.
- Dùng index vượt phạm vi khi đọc danh sách lồng.
- Gọi phương thức trên phần tử null hoặc trên kiểu không hỗ trợ phương thức đó.

Ví dụ cú pháp đúng:

~~~text
{'A', 'B', 'C'}
{{'A', 'B'}, {'C', 'D'}}
{#first, #second, 'DEFAULT'}
~~~

Khi parser báo lỗi cú pháp, hãy kiểm tra từng cặp ngoặc và dấu phẩy. Khi parse thành công nhưng getValue thất bại, hãy kiểm tra biến, root object, kiểu phần tử và các thao tác truy cập được thực hiện lúc runtime.

## 13. Kiểm thử danh sách lồng nhau

Khi kiểm thử inline list, hãy bao gồm các trường hợp sau:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Danh sách rỗng `{}` | Kết quả có 0 phần tử |
| Danh sách một phần tử | Phần tử ở chỉ số 0 |
| Danh sách nhiều phần tử | Thứ tự được giữ nguyên |
| Danh sách có phần tử null | null được giữ như một phần tử |
| Danh sách có biến động | Giá trị theo context ở từng lần đánh giá |
| Danh sách lồng nhau | Truy cập đúng cấp và đúng chỉ số |
| Danh sách con rỗng | Không có chỉ số hợp lệ bên trong |
| Danh sách con khác kích thước | Mã sử dụng xử lý cấu trúc không đều |
| Biến chưa đăng ký | Xử lý lỗi đánh giá |
| Literal sai cú pháp | Parser phát hiện lỗi khi phân tích |

Với danh sách nhiều cấp, nên kiểm thử từng đường dẫn truy cập thay vì chỉ kiểm tra toàn bộ kết quả. Điều này giúp xác định chính xác cấp nào có thể rỗng, null hoặc không có chỉ số được yêu cầu.

## 14. Khi nào nên tạo inline list và khi nào nên tạo list trong Java?

Dùng inline list khi:

- Danh sách ngắn và các phần tử được xác định ngay trong biểu thức.
- Cần nhóm một số literal hoặc biến để kiểm tra điều kiện.
- Cần tạo dữ liệu nhỏ, đơn giản trong cấu hình.
- Danh sách lồng có cấu trúc nông và dễ đọc.

Tạo list trong Java khi:

- Danh sách được xây dựng từ nhiều bước nghiệp vụ.
- Cần thêm, xóa, sắp xếp hoặc biến đổi nhiều phần tử.
- Cần kiểm soát kiểu generic, implementation hoặc khả năng sửa đổi.
- Dữ liệu lớn hoặc được tải từ cơ sở dữ liệu, API hay file.
- Cần tái sử dụng collection với vòng đời rõ ràng.

Một biểu thức SpEL nên tập trung vào việc tạo hoặc kiểm tra một tập giá trị nhỏ. Khi logic tạo danh sách trở nên phức tạp, hãy chuyển việc xây dựng collection sang Java rồi truyền kết quả vào EvaluationContext.

## 15. Ghi nhớ

Inline list của SpEL dùng cú pháp `{item1, item2, ...}` để tạo một List ngay trong biểu thức. Danh sách có thể rỗng, có một hoặc nhiều phần tử; phần tử có thể là literal, null, biến hoặc biểu thức được đánh giá lúc runtime.

Có thể lồng inline list để tạo cấu trúc nhiều chiều, sau đó dùng indexer để truy cập từng cấp. Các phần tử giữ thứ tự khai báo; danh sách con không nhất thiết phải có cùng kích thước. Cần kiểm tra null và chỉ số khi đọc dữ liệu lồng nhau.

Danh sách chỉ chứa literal cố định có thể được tạo tại thời điểm parse để tối ưu. Danh sách có biểu thức động cần đánh giá các phần tử theo context hiện tại. Inline list khác selection và projection: nó tạo danh sách từ các phần tử được khai báo, còn hai toán tử kia lọc hoặc biến đổi collection đã có.

Hãy dùng inline list cho nhóm giá trị nhỏ và rõ ràng. Với cấu trúc lớn, thay đổi nhiều hoặc cần quản lý vòng đời, hãy xây dựng List trong Java và truyền vào SpEL.