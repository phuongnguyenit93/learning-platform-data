# Kết hợp selection và projection trong một biểu thức

## Mục tiêu

Sau bài này, bạn có thể kết hợp selection và projection trong Spring Expression Language (SpEL) để lọc collection rồi chuyển các phần tử phù hợp thành dữ liệu kết quả; hiểu thứ tự thực hiện và kiểu kết quả sau mỗi bước; sử dụng biến `#this` đúng phạm vi; và áp dụng chuỗi thao tác cho List, mảng, Iterable và Map. Bạn cũng sẽ biết cách xử lý collection rỗng, null, phần tử lồng nhau và các tình huống cần chuyển logic sang Java.

## 1. Selection và projection giải quyết hai việc khác nhau

SpEL cung cấp hai nhóm toán tử thường được dùng cùng nhau:

- **Selection** lọc phần tử của một collection theo điều kiện.
- **Projection** đánh giá một biểu thức trên từng phần tử để tạo collection kết quả mới.

Selection thường dùng cú pháp:

~~~text
collection.?[condition]
~~~

Projection dùng cú pháp:

~~~text
collection.![expression]
~~~

Ví dụ, với danh sách đơn hàng, có thể lọc các đơn hàng đã thanh toán:

~~~text
#orders.?[status == 'PAID']
~~~

Kết quả vẫn là các đối tượng đơn hàng thỏa điều kiện. Nếu chỉ cần mã đơn hàng, có thể chiếu mỗi đơn hàng thành thuộc tính id:

~~~text
#orders.![id]
~~~

Kết quả là một danh sách mã, không còn là danh sách đối tượng Order.

Kết hợp hai thao tác giúp biểu thức thực hiện một pipeline ngắn: chọn những phần tử cần thiết trước, sau đó lấy ra đúng dữ liệu mà bước tiếp theo cần.

## 2. Mẫu phổ biến: lọc trước, chiếu sau

Cú pháp kết hợp thường gặp:

~~~text
collection.?[condition].![projectionExpression]
~~~

Ví dụ:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

SpEL thực hiện theo thứ tự:

1. Duyệt các phần tử của `#orders`.
2. Đánh giá `status == 'PAID'` trên từng đơn hàng.
3. Tạo collection chứa những đơn hàng phù hợp.
4. Đánh giá `id` trên từng đơn hàng đã chọn.
5. Trả về collection các mã đơn hàng.

Giả sử dữ liệu ban đầu:

| id | status | total |
|---|---|---:|
| O-101 | PAID | 250 |
| O-102 | NEW | 180 |
| O-103 | PAID | 420 |
| O-104 | CANCELLED | 90 |

Biểu thức trả về danh sách `['O-101', 'O-103']`.

Đây là cách viết phù hợp khi cần loại bỏ những đối tượng không liên quan rồi chỉ lấy một hoặc một vài thuộc tính của phần còn lại. Nó cũng làm rõ mục đích: điều kiện quyết định phần tử nào được giữ, còn projection quyết định thông tin nào được xuất ra.

## 3. Kết quả thay đổi sau mỗi bước

Cần hiểu kiểu và hình dạng dữ liệu sau từng toán tử để viết phần tiếp theo đúng cách.

Với một List hoặc Iterable:

- Selection thường `.?[...]` trả về một List chứa các phần tử phù hợp.
- Projection `.![...]` trả về một List chứa kết quả biểu thức trên từng phần tử.
- Projection có thể tạo List các đối tượng, chuỗi, số, boolean hoặc các collection con.

Ví dụ:

~~~text
#employees.?[active == true]
~~~

trả về các nhân viên đang hoạt động.

~~~text
#employees.?[active == true].![name]
~~~

trả về danh sách tên của những nhân viên đang hoạt động.

~~~text
#employees.?[active == true].![salary]
~~~

trả về danh sách mức lương của nhóm nhân viên đó.

Sau projection, mỗi phần tử kết quả là giá trị của biểu thức projection. Nếu projection lấy `name`, phần tử kết quả là tên; nếu lấy `salary`, phần tử kết quả là mức lương. Không thể tiếp tục truy cập thuộc tính của Employee trên một kết quả chỉ còn là String hoặc số.

## 4. Dùng #this trong selection và projection

Trong selection và projection, `#this` đại diện cho phần tử hiện tại đang được xử lý.

Ví dụ:

~~~text
#numbers.?[#this >= 10]
~~~

Ở mỗi lần duyệt, `#this` là một số trong collection. Điều kiện kiểm tra số hiện tại có lớn hơn hoặc bằng 10 hay không.

Trong projection:

~~~text
#employees.![#this.name]
~~~

`#this` là nhân viên hiện tại; biểu thức lấy thuộc tính name của nhân viên đó.

Nếu thuộc tính nằm trực tiếp trên phần tử, SpEL thường cho phép viết gọn:

~~~text
#employees.?[active].![name]
~~~

Trong selection, `active` được đọc trên phần tử hiện tại. Trong projection, `name` cũng được đọc trên phần tử hiện tại.

Có thể tham chiếu biến của EvaluationContext trong cả hai giai đoạn:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

`#minimumTotal` là biến được ứng dụng cung cấp; `#this` ngầm định là đơn hàng hiện tại trong điều kiện và projection.

`#root` vẫn tham chiếu root object của lần đánh giá. Khi selection hoặc projection lồng nhau, `#this` thay đổi theo phần tử của collection đang xử lý ở cấp hiện tại, còn `#root` không đổi.

## 5. Lọc theo điều kiện rồi lấy nhiều thuộc tính

Projection không chỉ lấy một thuộc tính. Nó có thể tạo ra một biểu thức tổng hợp từ nhiều thuộc tính của phần tử hiện tại.

Ví dụ:

~~~text
#orders.?[status == 'PAID'].![id + ':' + total]
~~~

Mỗi đơn hàng đã thanh toán được chuyển thành một chuỗi chứa mã và tổng tiền.

Có thể chiếu thành một inline list cho mỗi phần tử:

~~~text
#employees.?[active].![{id, name, department}]
~~~

Kết quả là một List mà mỗi phần tử lại là một List con gồm id, name và department của nhân viên tương ứng.

Với dữ liệu cần một cấu trúc kết quả có tên trường rõ ràng, hãy cân nhắc tạo DTO hoặc Map trong Java. Một danh sách các giá trị theo vị trí có thể khó bảo trì nếu số trường tăng hoặc thứ tự các trường thay đổi.

## 6. Kết hợp selection với projection lồng nhau

Collection có thể chứa collection con. Selection và projection có thể được lồng để lọc ở nhiều cấp.

Ví dụ, lấy tên các mặt hàng có SKU đang được yêu cầu trong tất cả đơn hàng:

~~~text
#orders.![items.?[sku == #targetSku].![name]]
~~~

Cách đọc:

1. Projection ngoài duyệt từng đơn hàng.
2. Với mỗi đơn hàng, truy cập danh sách items.
3. Selection bên trong giữ các mặt hàng có sku bằng `#targetSku`.
4. Projection bên trong chuyển mỗi mặt hàng đã chọn thành name.
5. Projection ngoài tạo một kết quả tương ứng với mỗi đơn hàng.

Kết quả là một List các List tên mặt hàng. Mỗi danh sách con tương ứng với một đơn hàng; đơn hàng không có mặt hàng phù hợp sẽ có danh sách con rỗng.

Nếu mục tiêu là lấy tất cả tên mặt hàng phù hợp từ mọi đơn hàng thành một List phẳng, biểu thức lồng này chưa tự làm phẳng kết quả. Hãy dùng Java để flatten, hoặc thiết kế nguồn dữ liệu thành một collection phẳng trước khi đánh giá.

Ví dụ tìm các đơn hàng có ít nhất một mặt hàng mang SKU cụ thể, rồi lấy mã đơn hàng:

~~~text
#orders.?[items.?[sku == #targetSku].size() > 0].![id]
~~~

Selection bên trong kiểm tra danh sách items của đơn hàng hiện tại. Selection bên ngoài chỉ giữ đơn hàng khi số mặt hàng phù hợp lớn hơn 0. Projection cuối cùng lấy id.

## 7. Thứ tự thao tác ảnh hưởng đến kết quả

Selection và projection không thể đổi chỗ một cách tùy ý vì projection có thể làm mất thông tin cần cho điều kiện lọc.

Lọc đối tượng trước rồi lấy tổng tiền:

~~~text
#orders.?[status == 'PAID'].![total]
~~~

Kết quả là tổng tiền của các đơn hàng đã thanh toán.

Chiếu tổng tiền trước rồi lọc các giá trị số:

~~~text
#orders.![total].?[#this >= #minimumTotal]
~~~

Kết quả là các giá trị total đạt ngưỡng, nhưng các đối tượng Order ban đầu đã bị thay bằng số tiền.

Hai biểu thức có thể trả về những danh sách khác kiểu và phục vụ mục đích khác nhau:

| Thứ tự | Kết quả | Thông tin còn giữ |
|---|---|---|
| Selection rồi projection | List giá trị được chiếu từ các đối tượng phù hợp | Chỉ các trường được projection tạo ra |
| Projection rồi selection | List các giá trị chiếu thỏa điều kiện sau projection | Giá trị chiếu, không còn toàn bộ đối tượng gốc |

Nếu điều kiện cần dùng `status` nhưng projection đã chuyển đối tượng thành `total`, bước selection sau đó không còn truy cập được status. Hãy chọn thứ tự sao cho dữ liệu cần cho điều kiện vẫn tồn tại ở bước tương ứng.

## 8. Kết hợp first hoặc last selection với projection

Ngoài selection thường, SpEL có first selection và last selection:

- `.^[...]` lấy phần tử phù hợp đầu tiên theo thứ tự duyệt.
- `.$[...]` lấy phần tử phù hợp cuối cùng theo thứ tự duyệt.

Nếu chỉ cần mã của đơn hàng đã thanh toán đầu tiên:

~~~text
#orders.^[status == 'PAID']?.id
~~~

Nếu cần mã của đơn hàng đã thanh toán cuối cùng:

~~~text
#orders.$[status == 'PAID']?.id
~~~

Trong hai ví dụ này, first hoặc last selection trả về một đối tượng đơn lẻ hoặc null. Safe navigation ở bước lấy id giúp tránh truy cập thuộc tính trên kết quả null khi không tìm thấy đơn hàng.

Nếu cần danh sách ID của tất cả đơn hàng đã thanh toán, dùng selection thường rồi projection:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Không dùng first hoặc last selection khi nghiệp vụ cần tất cả kết quả. Hai toán tử này cũng không sắp xếp collection; đầu tiên và cuối cùng được xác định theo thứ tự duyệt hiện tại.

## 9. Kết hợp với Map

SpEL hỗ trợ selection và projection trên Map. Điều kiện selection được đánh giá trên từng Map.Entry; có thể truy cập thuộc tính `key` và `value`.

Ví dụ, lọc các entry có giá trị lớn hơn một ngưỡng rồi lấy key:

~~~text
#pricesBySku.?[value > #minimumPrice].![key]
~~~

Selection trên Map giữ lại các entry phù hợp trong một Map; projection sau đó tạo List các key của những entry đã chọn.

Có thể chiếu value:

~~~text
#pricesBySku.?[value > #minimumPrice].![value]
~~~

Nếu chỉ cần Map chứa các entry phù hợp, dừng sau selection:

~~~text
#pricesBySku.?[value > #minimumPrice]
~~~

Với Map, thứ tự duyệt phụ thuộc implementation. HashMap không bảo đảm thứ tự ổn định; LinkedHashMap giữ thứ tự chèn; TreeMap duyệt theo thứ tự key. Khi dùng first hoặc last selection trên Map, hãy hiểu rõ thứ tự duyệt của implementation đang dùng.

## 10. Xử lý collection null, rỗng và phần tử null

Cần phân biệt ba trạng thái:

1. Collection nguồn là null.
2. Collection tồn tại nhưng rỗng hoặc không có phần tử phù hợp.
3. Collection có phần tử null.

Với selection thường, nếu nguồn hợp lệ nhưng không có phần tử phù hợp, kết quả là collection rỗng. Projection trên collection rỗng cũng tạo collection kết quả rỗng.

Nếu nguồn là null, thao tác selection hoặc projection thông thường có thể thất bại. Có thể bảo vệ bằng điều kiện hoặc safe navigation phù hợp với phiên bản Spring đang dùng.

Ví dụ dùng điều kiện tường minh:

~~~text
#orders != null ? #orders.?[status == 'PAID'].![id] : {}
~~~

Nếu `#orders` là null, biểu thức trả về inline list rỗng. Nếu collection tồn tại, biểu thức lọc rồi chiếu mã đơn hàng.

Với phần tử null, điều kiện như `status == 'PAID'` có thể không đọc được thuộc tính trên phần tử null. Có thể kiểm tra trước:

~~~text
#orders.?[#this != null and status == 'PAID'].![id]
~~~

Toán tử logic and sử dụng đánh giá ngắn mạch, vì vậy phần truy cập status chỉ cần được đánh giá khi phần tử hiện tại khác null.

Nếu thuộc tính bên trong phần tử cũng có thể null, hãy xử lý đúng mắt xích đó bằng safe navigation hoặc điều kiện rõ ràng. Không dùng projection để che giấu lỗi dữ liệu bắt buộc.

## 11. Kiểu kết quả trong Java

Sau khi kết hợp selection và projection, kiểu phần tử của kết quả phụ thuộc vào biểu thức projection.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#orders.?[status == 'PAID'].![id]"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);

List<?> paidOrderIds =
    expression.getValue(context, List.class);
~~~

Ở đây, kết quả là List các giá trị id. Nếu id là String, ứng dụng có thể chuyển đổi hoặc kiểm tra từng phần tử theo kiểu mong muốn.

Yêu cầu `List.class` xác định kiểu collection bên ngoài; nó không bảo đảm kiểu generic của mọi phần tử. Nếu cần một List<String> hoặc List<Long> đã được xác thực, hãy kiểm tra kiểu phần tử hoặc chuyển đổi trong Java.

Với projection lồng nhau, kết quả có thể là List các List. Với Map selection rồi projection, kết quả projection là List của giá trị được chiếu. Hãy xác định kiểu kết quả dựa trên toán tử cuối cùng và kiểu của biểu thức bên trong.

## 12. Điều kiện truy cập phương thức và EvaluationContext

Selection và projection có thể gọi phương thức trong biểu thức, ví dụ:

~~~text
#orders.?[customer.isPreferred()].![customer.getDisplayName()]
~~~

Khả năng gọi phương thức phụ thuộc vào method resolver và quyền truy cập mà EvaluationContext cung cấp. StandardEvaluationContext thường có cấu hình linh hoạt hơn; SimpleEvaluationContext yêu cầu bật rõ những khả năng cần thiết theo builder tương ứng.

Nếu dùng context bị giới hạn, hãy kiểm tra các property accessor và method resolver đã cấu hình có cho phép thao tác trong điều kiện và projection hay không. Không nên chuyển sang context có quyền rộng hơn chỉ để làm biểu thức chạy nếu chưa xác định nhu cầu truy cập.

Một getter hoặc phương thức được gọi trên từng phần tử cũng có thể tốn chi phí hoặc có tác dụng phụ. Ưu tiên các phép đọc dữ liệu đơn giản, ổn định và tránh gọi service từ mỗi phần tử trong collection.

## 13. Hiệu năng và kích thước collection

Kết hợp selection và projection thường phải duyệt dữ liệu theo các bước:

1. Selection duyệt collection nguồn để đánh giá điều kiện.
2. Các phần tử phù hợp được giữ trong collection kết quả.
3. Projection duyệt collection đã chọn để tạo giá trị kết quả.

Nếu nguồn có N phần tử và có M phần tử phù hợp, thường cần một lượt đánh giá điều kiện trên N phần tử và một lượt projection trên M phần tử. Đây là mô tả trực quan về số lần duyệt; chi phí thực tế còn phụ thuộc kiểu collection, biểu thức con, getter và method được gọi.

Để tránh công việc không cần thiết:

- Lọc trước khi projection nếu điều kiện cần dữ liệu của đối tượng gốc.
- Chỉ projection những trường thực sự cần dùng.
- Tránh gọi truy vấn hoặc service đắt tiền trong điều kiện cho từng phần tử.
- Không tạo nhiều collection trung gian nếu dữ liệu rất lớn.
- Với dữ liệu lưu trong database, cân nhắc lọc và chọn cột ngay ở tầng truy vấn.
- Đo hiệu năng với dữ liệu đại diện trước khi tối ưu.

Nếu collection rất lớn hoặc cần phân trang, SpEL thường phù hợp hơn với quy tắc trên một tập dữ liệu đã được giới hạn. Việc tải toàn bộ dữ liệu vào bộ nhớ rồi lọc bằng SpEL có thể làm tăng thời gian và mức sử dụng bộ nhớ.

## 14. Ví dụ Java hoàn chỉnh

Ví dụ sau lọc đơn hàng đã thanh toán, có tổng tiền đạt ngưỡng, rồi lấy mã và tổng tiền của chúng:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SelectionProjectionExample {

    public List<?> findPaidOrderTotals(
            List<Order> orders,
            BigDecimal minimumTotal) {

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression = parser.parseExpression(
            "#orders.?[status == 'PAID' and total >= #minimumTotal].![{id, total}]"
        );

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("orders", orders);
        context.setVariable("minimumTotal", minimumTotal);

        return expression.getValue(context, List.class);
    }
}
~~~

Mỗi phần tử của kết quả là một List con gồm id và total của một đơn hàng phù hợp. Cách biểu diễn này ngắn gọn cho một kết quả nhỏ. Nếu cần cấu trúc dữ liệu có tên trường, kiểu generic rõ ràng hoặc được dùng rộng trong ứng dụng, hãy tạo DTO trong Java.

## 15. Các lỗi thường gặp

Một số lỗi phổ biến khi kết hợp selection và projection:

- Dùng `.![...]` trước khi lọc rồi cố truy cập thuộc tính gốc không còn trong kết quả.
- Nhầm selection thường với first hoặc last selection.
- Quên rằng `#this` là phần tử hiện tại và thay đổi khi đi vào collection lồng.
- Giả định kết quả projection vẫn là kiểu đối tượng nguồn.
- Không xử lý collection null hoặc phần tử null.
- Dùng phương thức không được EvaluationContext cho phép.
- Giả định Map, Set hoặc collection khác có thứ tự duyệt giống List.
- Dùng biểu thức lồng sâu đến mức khó xác định kiểu dữ liệu ở mỗi bước.
- Gọi thao tác đắt tiền cho từng phần tử.

Khi biểu thức khó đọc, hãy tách dữ liệu trung gian trong Java, đặt tên biến có ý nghĩa hoặc chuyển quy tắc nhiều bước sang một phương thức nghiệp vụ.

## 16. Kiểm thử pipeline selection và projection

Với biểu thức:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Hãy kiểm tra các trường hợp:

| Dữ liệu nguồn | Kết quả mong đợi |
|---|---|
| Nhiều đơn hàng, có một số đơn đã thanh toán | Danh sách ID của các đơn đã thanh toán |
| Không có đơn đã thanh toán | List rỗng |
| Collection rỗng | List rỗng |
| Collection null | Xử lý theo nhánh bảo vệ hoặc safe navigation đã chọn |
| Có phần tử null | Điều kiện cần kiểm tra null trước khi đọc thuộc tính |
| ID của phần tử phù hợp là null | Kết quả có thể chứa null |
| Projection trả về List con | Kiểm tra đúng cấu trúc lồng |
| Map nguồn | Kiểm tra đúng kiểu kết quả Map hoặc List sau từng bước |
| Thứ tự nguồn thay đổi | Thứ tự kết quả có thay đổi tương ứng không |

Cũng nên kiểm tra cùng một collection với selection thường, first selection và last selection nếu nghiệp vụ có yêu cầu các số lượng kết quả khác nhau. Điều này giúp phát hiện việc chọn nhầm toán tử.

## 17. Ghi nhớ

Selection dùng `.?[...]` để lọc phần tử; projection dùng `.![...]` để chuyển từng phần tử thành một giá trị hoặc cấu trúc kết quả mới. Mẫu thường dùng là `collection.?[condition].![expression]`: lọc trước, chiếu sau.

Thứ tự hai thao tác ảnh hưởng đến kiểu và thông tin còn lại. Sau projection, phần tử kết quả là giá trị được chiếu, vì vậy không còn mặc nhiên truy cập được thuộc tính của đối tượng ban đầu. Trong mỗi điều kiện hoặc biểu thức projection, `#this` là phần tử hiện tại; với collection lồng, phạm vi hiện tại thay đổi theo cấp.

Selection trên Map giữ lại các entry phù hợp; projection trên Map tạo List các kết quả được chiếu. Với List, mảng và Iterable, selection/projection tạo các collection kết quả theo quy tắc của SpEL. Hãy xử lý null, collection rỗng, phần tử null và thứ tự duyệt.

Dùng selection kết hợp projection cho pipeline nhỏ, dễ đọc trên dữ liệu đã có trong bộ nhớ. Với collection lớn, truy vấn đắt tiền, nhiều bước nghiệp vụ hoặc kết quả cần kiểu dữ liệu rõ ràng, hãy cân nhắc xử lý ở Java hoặc tầng truy vấn phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)