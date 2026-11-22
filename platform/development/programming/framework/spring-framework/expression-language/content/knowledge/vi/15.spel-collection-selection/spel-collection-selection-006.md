# Phân biệt selection thường với first hoặc last selection

## Mục tiêu

Sau bài này, bạn có thể phân biệt ba cách chọn phần tử trong Spring Expression Language (SpEL): selection thường để lấy tất cả phần tử phù hợp, first selection để lấy phần tử phù hợp đầu tiên và last selection để lấy phần tử phù hợp cuối cùng. Bạn sẽ biết cú pháp của từng toán tử, cách dùng #this trong điều kiện, cách kết hợp selection với projection và cách xử lý collection không có kết quả.

## 1. Selection trong SpEL là gì?

Selection là thao tác lọc một collection theo một điều kiện. SpEL đánh giá điều kiện trên từng phần tử và chọn những phần tử thỏa mãn.

Cú pháp selection thường:

~~~text
collection.?[selectionExpression]
~~~

Ví dụ, lấy tất cả đơn hàng đã thanh toán:

~~~text
#orders.?[status == 'PAID']
~~~

Biểu thức kiểm tra thuộc tính status của từng đơn hàng. Những đơn hàng có status bằng PAID được đưa vào kết quả.

Selection thường phù hợp khi ứng dụng cần toàn bộ phần tử thỏa điều kiện, chẳng hạn:

- Lấy tất cả đơn hàng có trạng thái đã thanh toán.
- Tìm mọi nhân viên thuộc một phòng ban.
- Lọc các sản phẩm có giá thấp hơn một ngưỡng.
- Lấy các bản ghi thỏa một quy tắc nghiệp vụ.

Kết quả là một collection mới chứa tập con các phần tử phù hợp. Với nguồn là mảng hoặc Iterable, kết quả là một collection các phần tử đã chọn. Với nguồn là Map, SpEL đánh giá điều kiện trên từng Map.Entry và trả về một Map chứa các entry phù hợp.

## 2. Selection thường: lấy tất cả kết quả

Toán tử .?[] không dừng ở phần tử phù hợp đầu tiên. Nó tiếp tục xét toàn bộ nguồn và thu thập mọi phần tử thỏa điều kiện.

Ví dụ với một danh sách số:

~~~text
{2, 5, 8, 11, 14}.?[#this > 7]
~~~

Kết quả chứa 8, 11 và 14.

Ví dụ với danh sách đơn hàng:

~~~text
#orders.?[total >= 1000]
~~~

Kết quả chứa tất cả đơn hàng có total lớn hơn hoặc bằng 1000.

Nếu không có phần tử nào phù hợp, selection thường trả về collection rỗng. Điều này khác với first hoặc last selection, vốn chỉ tìm một phần tử duy nhất.

Hãy chọn selection thường khi các phần tử phù hợp đều có ý nghĩa với bước xử lý tiếp theo. Nếu chỉ cần một kết quả đại diện, có thể dùng first hoặc last selection để tránh tạo ra một collection mà ứng dụng không cần.

## 3. First selection: lấy phần tử phù hợp đầu tiên

First selection dùng toán tử .^[]:

~~~text
collection.^[selectionExpression]
~~~

Ví dụ:

~~~text
{2, 5, 8, 11, 14}.^[#this > 7]
~~~

Kết quả là 8, vì đây là phần tử đầu tiên theo thứ tự duyệt thỏa điều kiện #this > 7.

Với danh sách đơn hàng:

~~~text
#orders.^[status == 'PAID']
~~~

Biểu thức trả về đơn hàng đã thanh toán đầu tiên được tìm thấy trong thứ tự duyệt của danh sách.

First selection hữu ích khi:

- Chỉ cần bản ghi phù hợp đầu tiên.
- Danh sách đã được sắp xếp theo thứ tự ưu tiên.
- Cần chọn ứng viên đầu tiên theo thứ tự nguồn.
- Không cần giữ lại các kết quả phù hợp còn lại.

First selection không tự sắp xếp collection. Nếu muốn phần tử có giá trị nhỏ nhất, mới nhất hoặc ưu tiên cao nhất, hãy bảo đảm nguồn đã có thứ tự phù hợp trước khi đánh giá, hoặc sắp xếp dữ liệu trong Java.

Nếu không có phần tử nào thỏa điều kiện, kết quả first selection là null. Vì vậy, khi truy cập tiếp thuộc tính của kết quả, hãy xử lý trường hợp không tìm thấy.

## 4. Last selection: lấy phần tử phù hợp cuối cùng

Last selection dùng toán tử .$[]:

~~~text
collection.$[selectionExpression]
~~~

Ví dụ:

~~~text
{2, 5, 8, 11, 14}. $[#this > 7]
~~~

Khi viết biểu thức thực tế, không đặt khoảng trắng giữa dấu chấm và toán tử; cú pháp đúng là:

~~~text
{2, 5, 8, 11, 14}.$[#this > 7]
~~~

Kết quả là 14, vì đây là phần tử cuối cùng theo thứ tự duyệt thỏa điều kiện.

Với danh sách đơn hàng:

~~~text
#orders.$[status == 'PAID']
~~~

Biểu thức trả về đơn hàng đã thanh toán cuối cùng trong thứ tự duyệt của danh sách.

Last selection hữu ích khi:

- Cần phần tử phù hợp cuối cùng trong một danh sách có thứ tự.
- Cần lấy bản ghi cuối trong một nhóm dữ liệu đã sắp xếp.
- Muốn tìm phần tử cuối cùng thỏa điều kiện mà không cần lấy toàn bộ collection kết quả.

Last selection cũng không sắp xếp nguồn. "Cuối cùng" có nghĩa là cuối cùng theo thứ tự duyệt hiện tại, không mặc định là mới nhất hoặc lớn nhất.

Nếu không có phần tử phù hợp, kết quả last selection là null.

## 5. So sánh ba toán tử

Ba toán tử có cùng một phần điều kiện nhưng khác nhau ở số lượng kết quả được trả về:

| Loại | Cú pháp | Kết quả |
|---|---|---|
| Selection thường | .?[condition] | Tất cả phần tử phù hợp trong một collection |
| First selection | .^[condition] | Một phần tử phù hợp đầu tiên, hoặc null |
| Last selection | .$[condition] | Một phần tử phù hợp cuối cùng, hoặc null |

Ví dụ cùng một nguồn:

~~~text
#numbers.?[#this > 5]
#numbers.^[#this > 5]
#numbers.$[#this > 5]
~~~

Giả sử #numbers là [2, 7, 9, 3, 12]:

- Selection thường trả về [7, 9, 12].
- First selection trả về 7.
- Last selection trả về 12.

Selection thường trả về collection rỗng khi không có kết quả. First và last selection trả về null khi không tìm thấy phần tử phù hợp. Sự khác biệt này ảnh hưởng đến cách dùng kết quả trong biểu thức tiếp theo và cách khai báo kiểu nhận ở Java.

## 6. #this trong điều kiện selection

Trong selection, #this đại diện cho phần tử hiện tại đang được kiểm tra.

Ví dụ:

~~~text
#numbers.?[#this >= 10]
~~~

Khi duyệt từng số, #this lần lượt nhận giá trị của phần tử hiện tại. Điều kiện được đánh giá riêng cho từng phần tử.

Với đối tượng:

~~~text
#employees.^[salary > #minimumSalary]
~~~

Bên trong điều kiện, salary là thuộc tính của nhân viên hiện tại. Có thể viết tường minh:

~~~text
#employees.^[#this.salary > #minimumSalary]
~~~

Biến #minimumSalary được lấy từ EvaluationContext, còn #this thay đổi theo từng nhân viên đang được xét.

Nếu biểu thức selection lồng nhau, #this tương ứng với phần tử của collection ở cấp trong cùng đang được đánh giá. Hãy xác định đúng collection hiện tại để tránh nhầm thuộc tính của đối tượng ngoài với thuộc tính của phần tử bên trong.

## 7. Selection trên Map

SpEL hỗ trợ selection trên Map. Điều kiện được đánh giá trên từng đối tượng Map.Entry; hai thuộc tính key và value có thể được truy cập trong biểu thức.

Ví dụ, lọc các entry có value nhỏ hơn 27:

~~~text
#scoresByName.?[value < 27]
~~~

Kết quả là một Map mới chứa các entry thỏa điều kiện.

Có thể lọc theo key:

~~~text
#settings.?[key.startsWith('feature.')]
~~~

Ví dụ này giả định key là String và method startsWith được phép trong EvaluationContext.

Selection thường trên Map trả về tất cả entry phù hợp. Khi chỉ cần một phần tử theo vị trí duyệt, first hoặc last selection có thể dùng để lấy kết quả phù hợp đầu tiên hoặc cuối cùng. Với Map, điều kiện vẫn được đánh giá trên Map.Entry; hãy xử lý kiểu kết quả tương ứng nếu ứng dụng cần thao tác trực tiếp với entry.

Thứ tự duyệt Map phụ thuộc implementation. LinkedHashMap giữ thứ tự chèn; TreeMap duyệt theo thứ tự sắp xếp của key; HashMap không bảo đảm một thứ tự ổn định. Do đó, không nên dùng first hoặc last selection trên một Map không có thứ tự xác định nếu nghiệp vụ yêu cầu kết quả phải ổn định.

## 8. Selection trên mảng và Iterable

Selection có thể áp dụng cho mảng và các đối tượng triển khai Iterable, bao gồm List và Set.

Ví dụ với mảng:

~~~java
int[] values = {3, 8, 12, 17};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("values", values);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#values.?[#this >= 10]");

Object selected = expression.getValue(context);
~~~

Điều kiện được kiểm tra trên từng phần tử của mảng. Có thể thay .?[] bằng .^[] nếu chỉ cần phần tử đầu tiên đạt điều kiện, hoặc .$[] nếu cần phần tử cuối cùng đạt điều kiện.

Với List, thứ tự phần tử thường là thứ tự được lưu trong danh sách. Với Set, thứ tự phụ thuộc implementation. Một LinkedHashSet giữ thứ tự chèn, trong khi HashSet không bảo đảm thứ tự duyệt ổn định.

Vì first và last selection phụ thuộc thứ tự duyệt, hãy kiểm tra loại collection đầu vào trước khi dùng hai toán tử này trong quy tắc nghiệp vụ.

## 9. Kết hợp selection với projection

Selection và projection có vai trò khác nhau:

- Selection .?[...] lọc phần tử và giữ lại chính các phần tử phù hợp.
- Projection .![...] biến đổi mỗi phần tử thành một giá trị mới và tạo collection kết quả.

Có thể kết hợp chúng:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Biểu thức lọc tất cả đơn hàng đã thanh toán, sau đó lấy id của từng đơn hàng phù hợp.

First selection có thể kết hợp với truy cập thuộc tính của phần tử được tìm thấy:

~~~text
#orders.^[status == 'PAID']?.id
~~~

Biểu thức lấy đơn hàng đã thanh toán đầu tiên rồi đọc id. Safe navigation ở bước sau giúp kết quả là null nếu không có đơn hàng phù hợp.

Tương tự, last selection:

~~~text
#orders.$[status == 'PAID']?.id
~~~

Nếu cần danh sách ID của mọi đơn hàng phù hợp, hãy dùng selection thường kết hợp projection. Nếu chỉ cần ID của đơn hàng phù hợp đầu tiên hoặc cuối cùng, dùng first hoặc last selection rồi truy cập thuộc tính.

## 10. Lồng selection trong selection

Một điều kiện selection có thể chứa một selection khác. Ví dụ, tìm tất cả khách hàng có ít nhất một đơn hàng đã thanh toán:

~~~text
#customers.?[
    orders.?[status == 'PAID'].size() > 0
]
~~~

Selection bên trong lọc danh sách orders của khách hàng hiện tại. Nếu có ít nhất một đơn hàng đã thanh toán, khách hàng đó được giữ lại trong kết quả ngoài.

Có thể dùng first selection để tìm khách hàng đầu tiên có đơn hàng ưu tiên:

~~~text
#customers.^[
    orders.^[priority == true] != null
]
~~~

Trong selection ngoài, #this là khách hàng hiện tại. Trong selection trong, #this là đơn hàng đang được kiểm tra. Kết quả first selection bên trong là null nếu khách hàng không có đơn hàng ưu tiên phù hợp.

Biểu thức lồng có thể khó đọc khi có nhiều cấp. Hãy dùng xuống dòng và dấu ngoặc rõ ràng; nếu quy tắc cần nhiều bước hoặc nhiều lời gọi service, chuyển phần xử lý phức tạp vào Java.

## 11. Xử lý collection null và không có kết quả

Có hai tình huống khác nhau:

1. Collection nguồn không tồn tại hoặc là null.
2. Collection có tồn tại nhưng không có phần tử nào thỏa điều kiện.

Với selection thường, không có kết quả phù hợp sẽ tạo collection rỗng. Với first hoặc last selection, không có kết quả phù hợp sẽ trả về null.

Nếu collection nguồn có thể null, hãy bảo vệ trước khi selection:

~~~text
#orders != null ? #orders.^[status == 'PAID'] : null
~~~

Hoặc dùng safe collection selection khi phiên bản Spring đang dùng hỗ trợ cú pháp đó:

~~~text
#orders?.?[status == 'PAID']
~~~

Safe selection trả về null khi collection nguồn là null; nó không biến null thành collection rỗng. Nếu ứng dụng cần luôn nhận một collection, hãy chuẩn hóa dữ liệu đầu vào trong Java hoặc dùng một biểu thức mặc định có chủ đích.

Với first hoặc last selection, hãy xử lý null trước khi truy cập thuộc tính:

~~~text
#orders.^[status == 'PAID']?.id
~~~

Không nên giả định rằng không có kết quả sẽ trả về một đối tượng rỗng. Kết quả null cần được xử lý rõ ràng.

## 12. Hiệu năng và lựa chọn đúng toán tử

Selection thường cần duyệt toàn bộ nguồn để tìm tất cả phần tử phù hợp. First selection có thể dừng sau khi tìm được phần tử phù hợp đầu tiên. Last selection cần xác định phần tử phù hợp cuối cùng theo thứ tự duyệt, vì vậy thường phải duyệt đến hết nguồn.

Do đó:

- Dùng .?[] khi cần tất cả kết quả.
- Dùng .^[] khi chỉ cần kết quả đầu tiên theo thứ tự duyệt.
- Dùng .$[] khi chỉ cần kết quả cuối cùng theo thứ tự duyệt.
- Nếu cần phần tử lớn nhất, nhỏ nhất hoặc theo một tiêu chí sắp xếp khác, hãy sắp xếp hoặc tính toán trong Java thay vì nhầm lẫn với first/last selection.

Không nên chọn toán tử chỉ dựa trên hiệu năng. Hãy chọn theo ý nghĩa nghiệp vụ và kiểu kết quả cần nhận. Với collection rất lớn hoặc truy vấn dữ liệu ngoài bộ nhớ, nên lọc ở tầng dữ liệu thích hợp thay vì tải toàn bộ dữ liệu rồi dùng SpEL để lọc.

## 13. Ví dụ Java hoàn chỉnh

Ví dụ dưới đây đánh giá cả ba dạng selection trên cùng một danh sách đơn hàng:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SelectionExample {

    public static void main(String[] args) {
        List<Order> orders = loadOrders();

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("orders", orders);

        ExpressionParser parser = new SpelExpressionParser();

        Expression allPaid =
            parser.parseExpression("#orders.?[status == 'PAID']");

        Expression firstPaid =
            parser.parseExpression("#orders.^[status == 'PAID']");

        Expression lastPaid =
            parser.parseExpression("#orders.$[status == 'PAID']");

        Object all = allPaid.getValue(context);
        Order first = firstPaid.getValue(context, Order.class);
        Order last = lastPaid.getValue(context, Order.class);
    }

    private static List<Order> loadOrders() {
        // Lấy dữ liệu từ nguồn của ứng dụng.
        return List.of();
    }
}
~~~

Trong ví dụ, all nhận collection chứa tất cả đơn hàng đã thanh toán; first và last nhận một Order phù hợp đầu tiên hoặc cuối cùng. Nếu danh sách không có đơn hàng đã thanh toán, first và last là null.

Trong ứng dụng thực tế, lớp Order cần có thuộc tính status mà SpEL có thể đọc. Nếu dùng context hạn chế, method/property access phải được cấu hình phù hợp với biểu thức.

## 14. Kiểm thử các trường hợp biên

Với cùng một collection, hãy kiểm thử:

| Dữ liệu nguồn | Điều kiện | Selection thường | First selection | Last selection |
|---|---|---|---|---|
| [2, 7, 9, 3, 12] | #this > 5 | [7, 9, 12] | 7 | 12 |
| [1, 2, 3] | #this > 5 | [] | null | null |
| [5, 5, 5] | #this == 5 | [5, 5, 5] | 5 | 5 |
| [] | #this > 0 | [] | null | null |

Ngoài các trường hợp trên, hãy kiểm tra:

- Collection nguồn là null.
- Phần tử collection là null.
- Điều kiện truy cập thuộc tính lồng có thể gặp null.
- Collection có thứ tự ổn định và collection không bảo đảm thứ tự.
- Map có key hoặc value null.
- Phần tử đầu tiên hoặc cuối cùng không phù hợp nhưng phần tử ở giữa phù hợp.
- Không có phần tử phù hợp.
- Kết quả first/last được truy cập tiếp bằng thuộc tính hoặc phương thức.

Kiểm thử giúp xác nhận ứng dụng hiểu đúng khác biệt giữa collection rỗng và giá trị null, cũng như thứ tự duyệt của nguồn.

## 15. Ghi nhớ

Selection thường dùng .?[condition] để lấy tất cả phần tử phù hợp và trả về một collection. First selection dùng .^[condition] để lấy phần tử phù hợp đầu tiên. Last selection dùng .$[condition] để lấy phần tử phù hợp cuối cùng.

First và last được xác định theo thứ tự duyệt hiện tại của nguồn; các toán tử này không tự sắp xếp collection. Với List và array, thứ tự thường rõ ràng. Với Set hoặc Map, cần xem implementation có bảo đảm thứ tự hay không.

Trong điều kiện selection, #this là phần tử đang được xét. Selection thường trên Map đánh giá từng Map.Entry và giữ lại các entry phù hợp. Có thể kết hợp selection với projection để lấy thuộc tính của tất cả kết quả, hoặc dùng first/last selection khi chỉ cần một đối tượng.

Hãy phân biệt collection rỗng với null: selection thường không có kết quả trả về collection rỗng, còn first/last selection không có kết quả trả về null. Chọn toán tử theo số lượng kết quả mà nghiệp vụ cần và xử lý rõ trường hợp nguồn null hoặc không có phần tử phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)