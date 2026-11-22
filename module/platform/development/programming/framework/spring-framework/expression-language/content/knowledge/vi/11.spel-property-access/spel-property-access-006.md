# Property null giữa đường dẫn truy cập

## Mục tiêu

Sau bài này, bạn có thể nhận biết lỗi khi một thuộc tính ở giữa đường dẫn truy cập có giá trị null; dùng toán tử safe navigation (?.) đúng tại từng bước có thể null; phân biệt việc bỏ qua truy cập với việc cung cấp giá trị mặc định; và kiểm tra các trường hợp null trong biểu thức SpEL trước khi đưa vào ứng dụng.

## 1. Đường dẫn thuộc tính lồng nhau

Trong Spring Expression Language (SpEL), một biểu thức có thể đọc thuộc tính theo chuỗi từ một đối tượng gốc đến các đối tượng con.

Ví dụ, một đơn hàng có khách hàng, khách hàng có địa chỉ và địa chỉ có thành phố:

~~~text
customer.address.city
~~~

SpEL lần lượt thực hiện các thao tác:

1. Đọc thuộc tính customer trên đối tượng gốc.
2. Đọc thuộc tính address trên đối tượng customer.
3. Đọc thuộc tính city trên đối tượng address.
4. Trả về giá trị city.

Cách viết này ngắn gọn khi mọi đối tượng trung gian đều tồn tại. Tuy nhiên, trong dữ liệu thực tế, một khách hàng có thể chưa có địa chỉ hoặc đơn hàng có thể chưa gắn khách hàng. Khi một thuộc tính trung gian trả về null, SpEL không thể tiếp tục đọc thuộc tính kế tiếp trên tham chiếu đó.

Vì vậy, lỗi thường không nằm ở thuộc tính cuối cùng. Nó có thể xuất hiện ở bất kỳ mắt xích nào của đường dẫn.

## 2. Điều gì xảy ra khi thuộc tính ở giữa là null?

Giả sử biểu thức là:

~~~text
customer.address.city
~~~

Có thể gặp các trạng thái dữ liệu sau:

| customer | address | city | Kết quả với đường dẫn thông thường |
|---|---|---|---|
| Có đối tượng | Có đối tượng | Có giá trị | Đọc được city |
| null | Không thể truy cập | Không thể truy cập | Lỗi khi đọc address trên customer null |
| Có đối tượng | null | Không thể truy cập | Lỗi khi đọc city trên address null |
| Có đối tượng | Có đối tượng | null | Đọc được kết quả null |
| Có đối tượng | Có đối tượng | Có giá trị | Đọc được giá trị |

Điểm khác biệt quan trọng là giữa một thuộc tính cuối cùng có giá trị null và một đối tượng trung gian null.

Nếu city là null nhưng address vẫn tồn tại, SpEL có thể trả về null vì đã đọc được thuộc tính cuối cùng. Nếu address là null, việc truy cập city không thể tiếp tục và lần đánh giá có thể thất bại.

Trong Java, điều này tương tự việc gọi một phương thức hoặc đọc một field trên tham chiếu null. SpEL có thể báo lỗi đánh giá thuộc tính, thường kèm thông tin về vị trí biểu thức gây lỗi.

## 3. Dùng toán tử safe navigation

SpEL cung cấp toán tử safe navigation, viết là ?. . Toán tử này kiểm tra đối tượng ở bên trái trước khi thực hiện thao tác truy cập thuộc tính hoặc gọi phương thức kế tiếp.

Ví dụ:

~~~text
customer?.address
~~~

Nếu customer là null, thao tác đọc address được bỏ qua và kết quả của phần biểu thức đó là null. Nếu customer tồn tại, SpEL tiếp tục đọc address như bình thường.

Đối với đường dẫn có nhiều mắt xích có thể null, hãy dùng safe navigation ở từng mắt xích tương ứng:

~~~text
customer?.address?.city
~~~

Kết quả:

- Nếu customer là null, biểu thức trả về null.
- Nếu customer tồn tại nhưng address là null, biểu thức trả về null.
- Nếu cả hai đối tượng tồn tại, biểu thức đọc city.
- Nếu city có giá trị null, kết quả cuối cùng vẫn là null.

Toán tử này giúp biểu thức chịu được dữ liệu thiếu ở những vị trí đã được dự kiến. Nó không tạo ra đối tượng thay thế và cũng không tự chọn một giá trị mặc định.

## 4. Vì sao cần đặt ?. ở từng vị trí có thể null?

Một lỗi phổ biến là chỉ đặt safe navigation ở đầu đường dẫn:

~~~text
customer?.address.city
~~~

Cách viết này chỉ bảo vệ thao tác đọc address trên customer. Nếu customer là null, thao tác address được bỏ qua. Nhưng nếu customer tồn tại và address trả về null, phần truy cập .city phía sau vẫn có thể thất bại.

Nếu address cũng có thể null, hãy bảo vệ cả bước đọc city:

~~~text
customer?.address?.city
~~~

Quy tắc thực hành:

- Dùng ?. trước thuộc tính mà đối tượng nhận có thể null.
- Nếu kết quả của một thuộc tính trung gian cũng có thể null, dùng ?. ở bước truy cập tiếp theo.
- Không cần dùng ?. cho mọi thuộc tính một cách máy móc nếu mô hình dữ liệu bảo đảm đối tượng đó luôn tồn tại.
- Kiểm tra hợp đồng dữ liệu và annotation hoặc quy tắc validation của Java để xác định mắt xích nào thật sự có thể null.

Ví dụ với đường dẫn sâu hơn:

~~~text
order?.customer?.profile?.displayName
~~~

Mỗi dấu ?. bảo vệ một bước truy cập. Nếu một mắt xích trả về null, phần truy cập được bảo vệ kế tiếp sẽ trả về null thay vì cố đọc thuộc tính trên tham chiếu null.

## 5. Safe navigation chỉ xử lý tham chiếu null

Toán tử ?. có phạm vi rõ ràng: nó bỏ qua thao tác kế tiếp khi đối tượng nhận là null. Nó không xử lý mọi loại lỗi có thể xảy ra trong biểu thức.

Ví dụ, các trường hợp sau vẫn cần được xử lý riêng:

- Tên thuộc tính không tồn tại trên kiểu đối tượng.
- Thuộc tính tồn tại nhưng getter ném ngoại lệ.
- Đối tượng không tương thích với thao tác truy cập.
- Giá trị trả về không thể chuyển đổi sang kiểu đích.
- Chỉ số mảng hoặc collection nằm ngoài phạm vi.
- Một phương thức được gọi có lỗi trong phần triển khai.

Ví dụ:

~~~text
customer?.unknownProperty
~~~

Nếu customer tồn tại nhưng kiểu của nó không có thuộc tính unknownProperty, safe navigation không biến thuộc tính không tồn tại thành null. Nó chỉ bảo vệ trường hợp customer là null.

Tương tự, nếu getter address có lỗi bên trong, ?. không bắt và nuốt ngoại lệ đó. Hãy xử lý lỗi ở lớp Java gọi biểu thức và sửa nguyên nhân dữ liệu hoặc mã nguồn tương ứng.

## 6. Kết hợp safe navigation với giá trị mặc định

Safe navigation thường trả về null khi một mắt xích không tồn tại. Nếu ứng dụng cần hiển thị một giá trị thay thế, hãy kết hợp với toán tử Elvis (?:).

Ví dụ:

~~~text
customer?.address?.city ?: 'Chưa cập nhật'
~~~

Cách đọc:

1. Thử lấy city từ customer và address.
2. Nếu đường dẫn an toàn trả về null, dùng chuỗi Chưa cập nhật.
3. Nếu có thành phố, trả về tên thành phố đó.

Có thể dùng giá trị mặc định theo kiểu dữ liệu:

~~~text
customer?.loyaltyPoints ?: 0
~~~

~~~text
customer?.active ?: false
~~~

Elvis là bước chọn giá trị thay thế. Nó không thay thế safe navigation ở những vị trí trung gian có thể null. Ví dụ, chỉ viết customer.address.city ?: 'Unknown' vẫn có thể lỗi trước khi Elvis được đánh giá nếu customer hoặc address là null.

Trong SpEL, Elvis cũng xem chuỗi rỗng là giá trị vắng mặt trong trường hợp phù hợp. Nếu cần phân biệt chuỗi rỗng với null, hãy viết điều kiện rõ ràng theo yêu cầu nghiệp vụ. Các giá trị false và 0 vẫn là giá trị có ý nghĩa; đừng coi chúng là null khi đặt mặc định.

## 7. Dùng điều kiện tường minh khi cần phân biệt null

Đôi khi ứng dụng cần biết thuộc tính có thực sự tồn tại hay không, thay vì chỉ muốn một giá trị hiển thị thay thế.

Có thể so sánh trực tiếp với null:

~~~text
customer?.address?.city != null
~~~

Hoặc dùng toán tử ba ngôi:

~~~text
customer?.address?.city != null
    ? customer.address.city
    : 'Chưa có thành phố'
~~~

Trong ví dụ này, nhánh lấy city chỉ được chọn khi đường dẫn đã kiểm tra có giá trị khác null. Tuy nhiên, nếu có nhiều lần truy cập lặp lại, hãy cân nhắc đưa giá trị đã chuẩn hóa vào biến của context để tránh lặp lại đường dẫn dài.

Nếu chỉ cần giá trị mặc định, Elvis thường ngắn gọn hơn:

~~~text
customer?.address?.city ?: 'Chưa có thành phố'
~~~

Nếu cần phân biệt null, chuỗi rỗng, trạng thái không hợp lệ hoặc nhiều trường hợp nghiệp vụ, hãy dùng điều kiện tường minh hoặc một phương thức Java có tên rõ ràng.

## 8. Dùng trong EvaluationContext và Java

Có thể đánh giá đường dẫn an toàn từ một root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("customer?.address?.city");

String city = expression.getValue(order, String.class);
~~~

Trong ví dụ này, order là root object. Nếu customer hoặc address là null, kết quả city là null.

Nếu muốn truyền đối tượng bằng biến:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order?.customer?.address?.city");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);

String city = expression.getValue(context, String.class);
~~~

Cả hai cách đều sử dụng cùng cú pháp safe navigation. Khác biệt nằm ở nơi cung cấp đối tượng: root object hoặc biến trong EvaluationContext.

Nếu cần cung cấp giá trị mặc định từ biểu thức:

~~~java
Expression expression = parser.parseExpression(
    "#order?.customer?.address?.city ?: 'Chưa cập nhật'"
);

String city = expression.getValue(context, String.class);
~~~

Hãy bảo đảm context chỉ chứa các đối tượng và quyền truy cập mà biểu thức cần. Safe navigation giúp xử lý null trong đường dẫn; nó không thay thế việc thiết kế root object hoặc EvaluationContext phù hợp.

## 9. Thuộc tính null trong collection và chỉ số

Một đường dẫn có thể kết hợp truy cập collection với thuộc tính lồng nhau:

~~~text
orders[0]?.customer?.address?.city
~~~

Nếu phần tử đầu tiên tồn tại nhưng customer hoặc address là null, safe navigation xử lý các mắt xích đó.

Tuy nhiên, biểu thức trên không tự xử lý trường hợp orders là null hoặc danh sách rỗng. Việc truy cập orders[0] diễn ra trước khi ?. trên phần tử có thể được áp dụng. Do đó, cần kiểm tra collection và chỉ số trước:

~~~text
#orders != null and
#orders.size() > 0 and
#orders[0]?.customer?.address?.city == #targetCity
~~~

Điều kiện này kiểm tra collection khác null và có phần tử trước khi đọc phần tử đầu tiên. Khi dùng biểu thức trong môi trường cụ thể, các phương thức như size() phải được phép bởi EvaluationContext.

Với selection, có thể dùng safe navigation cho các thuộc tính của phần tử:

~~~text
#orders.?[customer?.address?.city == #targetCity]
~~~

Ở đây, mỗi phần tử được kiểm tra theo đường dẫn customer, address và city. Nếu customer hoặc address null, biểu thức con trả về null; phép so sánh với targetCity không xem null là một tên thành phố phù hợp.

## 10. Safe navigation với điều kiện Boolean

Một thuộc tính Boolean cũng có thể null, đặc biệt khi dùng kiểu wrapper Boolean thay vì primitive boolean.

Ví dụ:

~~~text
customer?.preferences?.emailEnabled == true
~~~

Biểu thức kiểm tra rõ rằng giá trị phải là true. Nếu customer, preferences hoặc emailEnabled là null, điều kiện không được coi là đã bật.

Có thể dùng Elvis để chọn mặc định false:

~~~text
customer?.preferences?.emailEnabled ?: false
~~~

Cách viết này hữu ích khi null có nghĩa là chưa bật hoặc không cho phép. Nếu null mang ý nghĩa riêng như chưa xác định, cần giữ lại sự khác biệt đó thay vì tự động chuyển thành false.

Không nên giả định mọi thuộc tính Boolean đều có thể unbox an toàn sang boolean. Khi chuyển kết quả null sang kiểu primitive trong Java, ứng dụng có thể gặp NullPointerException. Hãy chọn kiểu trả về nullable hoặc cung cấp mặc định có chủ đích.

## 11. Kiểm thử đường dẫn có thuộc tính null

Khi kiểm thử biểu thức, cần thay đổi từng mắt xích để xác định đúng vị trí có thể null.

Với biểu thức:

~~~text
customer?.address?.city
~~~

Có thể dùng các ca sau:

| Trạng thái dữ liệu | Kết quả mong đợi |
|---|---|
| customer null | null |
| customer tồn tại, address null | null |
| customer và address tồn tại, city null | null |
| customer, address và city đều có giá trị | Tên thành phố |
| customer tồn tại nhưng không có thuộc tính address | Lỗi truy cập thuộc tính |
| getter address ném ngoại lệ | Lỗi đánh giá từ getter |

Ngoài ra, hãy kiểm tra:

- Root object là null.
- Một thuộc tính trung gian trả về null ở các cấp khác nhau.
- Chuỗi rỗng và giá trị mặc định.
- Thuộc tính Boolean có giá trị null, false và true.
- Collection null, collection rỗng và chỉ số ngoài phạm vi.
- Getter hoặc accessor có thể phát sinh ngoại lệ.

Nên kiểm thử cả đường dẫn thông thường và đường dẫn safe navigation để xác nhận ứng dụng đang dựa vào đúng hợp đồng dữ liệu. Khi một thuộc tính bắt buộc phải có, validation ở Java có thể phù hợp hơn việc âm thầm bỏ qua null trong SpEL.

## 12. Khi nào nên dùng safe navigation?

Dùng safe navigation khi null là trạng thái dữ liệu hợp lệ hoặc có thể xuất hiện trong luồng xử lý, chẳng hạn:

- Hồ sơ chưa có địa chỉ.
- Đơn hàng chưa gắn khách hàng.
- Người dùng chưa cấu hình tùy chọn.
- Dữ liệu nhập từ nguồn ngoài có trường tùy chọn.
- Một phần tử collection có quan hệ lồng chưa được thiết lập.

Không nên dùng safe navigation để che giấu vi phạm dữ liệu bắt buộc. Nếu nghiệp vụ yêu cầu customer và address luôn tồn tại, hãy xác thực điều đó ở thời điểm nhận hoặc lưu dữ liệu. Việc biến mọi lỗi thành null có thể khiến ứng dụng bỏ qua dữ liệu sai và tạo ra kết quả khó phát hiện.

Nếu biểu thức bắt đầu có nhiều nhánh mặc định, điều kiện và truy cập lồng sâu, hãy chuyển quy tắc phức tạp vào Java. SpEL nên giữ vai trò đọc dữ liệu và biểu diễn điều kiện ngắn trong cấu hình.

## 13. Ghi nhớ

Một đường dẫn thuộc tính lồng nhau có thể thất bại khi bất kỳ đối tượng trung gian nào là null. Toán tử safe navigation ?. bỏ qua thao tác truy cập kế tiếp nếu đối tượng nhận là null và trả về null cho phần đó.

Với đường dẫn nhiều cấp, hãy đặt ?. ở từng bước có thể nhận một giá trị null, ví dụ customer?.address?.city. Chỉ đặt safe navigation ở đầu đường dẫn không bảo vệ những đối tượng con có thể null ở các bước sau.

Safe navigation không xử lý thuộc tính không tồn tại, lỗi bên trong getter, sai kiểu hoặc chỉ số collection không hợp lệ. Kết hợp nó với Elvis khi cần giá trị mặc định, hoặc dùng điều kiện tường minh khi cần phân biệt null với trạng thái khác.

Hãy xác định rõ thuộc tính nào được phép null, kiểm thử từng mắt xích và giữ validation của dữ liệu bắt buộc ở lớp Java.