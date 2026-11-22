# Kiểm thử cả nhánh điều kiện và trường hợp collection rỗng

## Mục tiêu

Sau bài này, bạn có thể thiết kế kiểm thử cho cả hai nhánh của biểu thức điều kiện trong Spring Expression Language (SpEL); xác nhận hành vi của toán tử ternary, Elvis và logic AND/OR; và phân biệt collection rỗng, collection không có phần tử phù hợp với giá trị null. Bạn cũng sẽ biết cách kiểm tra selection, projection, first/last selection, dữ liệu lồng nhau và các trường hợp biên bằng JUnit. Mục tiêu là bảo đảm expression trả về đúng kết quả cho cả dữ liệu bình thường lẫn những trạng thái dễ bị bỏ sót.

## 1. Vì sao phải kiểm thử cả hai nhánh?

Một biểu thức có điều kiện thường có ít nhất hai kết quả có thể xảy ra. Ví dụ:

~~~text
#paid ? 'PAID' : 'PENDING'
~~~

Khi paid là true, biểu thức trả về PAID. Khi paid là false, biểu thức trả về PENDING.

Nếu chỉ kiểm thử trường hợp paid = true, nhánh false có thể chứa lỗi mà bộ test không phát hiện. Lỗi có thể là tên property sai, biến chưa được đăng ký, giá trị mặc định không đúng hoặc một phép gọi method chỉ xuất hiện ở nhánh còn lại.

Với biểu thức nghiệp vụ, cần kiểm tra ít nhất:

- Nhánh điều kiện đúng.
- Nhánh điều kiện sai.
- Trường hợp điều kiện null hoặc thiếu dữ liệu, nếu hợp đồng cho phép.
- Giá trị biên khiến điều kiện đổi từ false sang true hoặc ngược lại.
- Kiểu và giá trị kết quả của từng nhánh.

Một expression parse thành công không có nghĩa cả hai nhánh đều chạy được. Parser kiểm tra cú pháp của toàn biểu thức, nhưng lỗi truy cập property, method hoặc chuyển đổi kiểu ở một nhánh có thể chỉ xuất hiện khi nhánh đó được đánh giá.

## 2. Kiểm thử toán tử ternary

Toán tử điều kiện có cú pháp:

~~~text
condition ? valueWhenTrue : valueWhenFalse
~~~

Ví dụ:

~~~text
#order.total >= #minimum ? 'ELIGIBLE' : 'NOT_ELIGIBLE'
~~~

Để kiểm thử đầy đủ, tạo hai bộ dữ liệu sao cho điều kiện lần lượt đúng và sai:

| total | minimum | Kết quả mong đợi |
|---:|---:|---|
| 150 | 100 | ELIGIBLE |
| 80 | 100 | NOT_ELIGIBLE |
| 100 | 100 | ELIGIBLE |
| 99.99 | 100 | NOT_ELIGIBLE |

Các giá trị đúng bằng ngưỡng rất quan trọng. Nếu nghiệp vụ dùng >= nhưng expression vô tình dùng >, test với 150 và 80 vẫn có thể qua; test ở đúng biên 100 mới phát hiện sai khác.

Mỗi nhánh nên được xác nhận cả nội dung lẫn kiểu kết quả. Nếu một nhánh trả String còn nhánh kia trả một kiểu object khác, hãy kiểm tra điều đó có được thiết kế có chủ ý và có thể chuyển đổi sang kiểu đích mong muốn hay không.

## 3. Ternary chỉ đánh giá nhánh được chọn

Trong biểu thức điều kiện, SpEL đánh giá điều kiện rồi đánh giá nhánh tương ứng. Nhánh không được chọn không cần thực thi.

Ví dụ:

~~~text
#customer != null ? #customer.name : 'Guest'
~~~

Nếu customer là null, kết quả là Guest và phần truy cập name không được thực hiện.

Đây là lý do ternary thường được dùng để bảo vệ một thao tác chỉ hợp lệ khi điều kiện đúng. Tuy nhiên, điều kiện phải thực sự kiểm tra trạng thái cần bảo vệ. Nếu expression dùng một property khác có thể null trước khi quyết định nhánh, lỗi vẫn có thể xảy ra.

Khi kiểm thử, nên có một test xác nhận nhánh được chọn và một test xác nhận nhánh còn lại. Nếu nhánh có method call hoặc function, có thể dùng test double để xác nhận chỉ thao tác dự kiến được gọi. Tránh đưa tác dụng phụ vào expression chỉ để kiểm tra thứ tự; hãy kiểm tra bằng mock hoặc spy ở Java khi cần.

## 4. Kiểm thử toán tử Elvis

Elvis operator dùng cú pháp:

~~~text
value ?: fallback
~~~

Ví dụ:

~~~text
#customer.nickname ?: 'Guest'
~~~

Nếu nickname có giá trị phù hợp, expression trả về nickname. Nếu giá trị bên trái là null, Elvis trả về fallback. Với chuỗi rỗng, cần xác định hành vi mong muốn và kiểm thử theo đúng quy tắc của phiên bản SpEL đang sử dụng; đừng mặc định Elvis đồng nghĩa với kiểm tra chuỗi blank.

Một số trường hợp nên kiểm tra:

| Giá trị bên trái | Điều cần xác nhận |
|---|---|
| "An" | Giữ giá trị hiện có |
| null | Dùng fallback |
| "" | Xác nhận quy tắc với chuỗi rỗng |
| "   " | Xác nhận có cần trim/blank validation riêng |
| 0 | Không nhầm số 0 với null |
| false | Không nhầm false với null |

Elvis hữu ích cho giá trị tùy chọn. Nó không thay thế validation cho dữ liệu bắt buộc. Nếu nickname bắt buộc phải có nội dung, trả về Guest có thể che giấu dữ liệu sai thay vì báo lỗi.

## 5. Kiểm thử logic AND và OR

Các toán tử logic thường dùng:

~~~text
#enabled and #authorized
#isAdmin or #isOwner
not #blocked
~~~

Với AND, kết quả chỉ true khi cả hai điều kiện true. Với OR, kết quả true khi ít nhất một điều kiện true.

Hãy lập bảng tổ hợp thay vì chỉ kiểm tra một trường hợp:

| A | B | A and B | A or B |
|---|---|---|---|
| true | true | true | true |
| true | false | false | true |
| false | true | false | true |
| false | false | false | false |

Kiểm thử cả bốn tổ hợp giúp phát hiện nhầm toán tử, đảo điều kiện hoặc thiếu một vế.

AND và OR trong SpEL có đánh giá ngắn mạch. Với AND, nếu vế trái đã false thì vế phải không cần được đánh giá. Với OR, nếu vế trái đã true thì vế phải không cần được đánh giá. Điều này hữu ích khi vế phải chỉ hợp lệ sau khi vế trái đã xác nhận object khác null:

~~~text
#customer != null and #customer.active
~~~

Tuy nhiên, hãy viết điều kiện theo thứ tự dễ hiểu và không dựa vào short-circuit để che giấu cấu trúc dữ liệu bất thường. Kiểm thử trường hợp vế trái làm dừng đánh giá và trường hợp vế phải thực sự được chạy.

## 6. Kiểm thử collection rỗng và collection không có kết quả

Collection rỗng và collection có phần tử nhưng không có phần tử nào phù hợp là hai dữ liệu đầu vào khác nhau.

Ví dụ selection:

~~~text
#numbers.?[#this > 10]
~~~

Cần kiểm thử ít nhất hai trường hợp:

- Nguồn là collection rỗng: không có phần tử để xét.
- Nguồn có phần tử nhưng tất cả đều không thỏa điều kiện.

Cả hai trường hợp selection thường đều tạo kết quả rỗng, nhưng chúng đại diện cho trạng thái dữ liệu khác nhau. Nếu nghiệp vụ cần phân biệt, hãy kiểm tra collection nguồn trước khi selection hoặc cung cấp metadata riêng về trạng thái nguồn.

Ví dụ:

| Nguồn | Điều kiện | Kết quả selection |
|---|---|---|
| [] | #this > 10 | Collection rỗng |
| [1, 2, 3] | #this > 10 | Collection rỗng |
| [5, 12, 20] | #this > 10 | [12, 20] |

Không nên chỉ kiểm tra kích thước kết quả rồi kết luận nguồn ban đầu rỗng. Kết quả rỗng cũng có thể do điều kiện lọc không khớp phần tử nào.

## 7. Phân biệt collection rỗng với null

Một collection rỗng là object collection hợp lệ nhưng không chứa phần tử. Null nghĩa là không có tham chiếu collection.

Ví dụ:

~~~java
List<Integer> empty = List.of();
List<Integer> missing = null;
~~~

Hai trạng thái này không tương đương:

- Với collection rỗng, có thể gọi size() và nhận 0.
- Với null, gọi size() trực tiếp sẽ thất bại.
- Selection trên collection rỗng trả về kết quả rỗng.
- Truy cập collection null cần được bảo vệ hoặc xử lý theo hợp đồng dữ liệu.

Nếu nghiệp vụ coi null và empty giống nhau, hãy chuẩn hóa dữ liệu ở Java trước khi đưa vào context. Nếu chúng có ý nghĩa khác nhau, hãy giữ riêng hai trạng thái và viết test cho cả hai.

Ví dụ expression có kiểm tra null:

~~~text
#orders == null ? 'MISSING' :
    (#orders.isEmpty() ? 'EMPTY' : 'PRESENT')
~~~

Biểu thức này phân biệt collection chưa được cung cấp, collection rỗng và collection có phần tử. Cần bảo đảm biến orders đã được đăng ký và kiểu của nó hỗ trợ isEmpty().

## 8. Kiểm thử selection thường trên collection rỗng

Selection thường dùng toán tử .?[]:

~~~text
#orders.?[total >= #minimum]
~~~

Với List rỗng, selection trả về một collection rỗng. Với List có phần tử nhưng không phần tử nào đạt điều kiện, kết quả cũng rỗng.

Ví dụ:

~~~text
#orders.?[status == 'PAID']
~~~

Nên kiểm tra:

- Nguồn là List rỗng.
- Nguồn có một phần tử không phù hợp.
- Nguồn có nhiều phần tử nhưng không phần tử nào phù hợp.
- Nguồn có một phần tử phù hợp.
- Nguồn có nhiều phần tử phù hợp.
- Phần tử có thuộc tính null nếu mô hình cho phép.
- Nguồn là null nếu ứng dụng có thể cung cấp trạng thái này.

Khi kết quả rỗng là hợp lệ, test nên xác nhận collection tồn tại và không có phần tử, thay vì chỉ kiểm tra kết quả không null.

## 9. Kiểm thử projection trên collection rỗng

Projection dùng toán tử .![] để biến đổi từng phần tử:

~~~text
#orders.![id]
~~~

Nếu nguồn là List rỗng, projection trả về collection kết quả rỗng. Không có phần tử nào để đánh giá biểu thức id.

Ví dụ:

~~~text
#numbers.![#this * 2]
~~~

Với nguồn [], kết quả là []. Với nguồn [2, 4], kết quả là [4, 8].

Hãy kiểm thử cả nguồn rỗng và nguồn có phần tử. Nếu projection gọi property lồng nhau, cần thêm trường hợp phần tử có object con null:

~~~text
#orders.![customer.name]
~~~

Nếu một order có customer null, việc đọc name có thể thất bại. Nếu customer là tùy chọn, có thể dùng safe navigation:

~~~text
#orders.![customer?.name]
~~~

Test cần xác nhận kết quả của phần tử null theo đúng hợp đồng; không nên giả định projection tự bỏ qua phần tử thiếu dữ liệu.

## 10. Kiểm thử first và last selection

First selection dùng .^[] để lấy phần tử phù hợp đầu tiên; last selection dùng .$[] để lấy phần tử phù hợp cuối cùng.

~~~text
#numbers.^[#this > 10]
#numbers.$[#this > 10]
~~~

Nếu collection không có phần tử phù hợp, cả first và last selection trả về null. Đây là khác biệt quan trọng so với selection thường, vốn trả về collection rỗng.

Ví dụ với [3, 12, 18]:

- Selection thường trả về [12, 18].
- First selection trả về 12.
- Last selection trả về 18.

Với [] hoặc [1, 2, 3], first và last selection không tìm thấy phần tử nên trả về null.

Hãy kiểm tra cả trường hợp không có kết quả, chỉ có một kết quả và có nhiều kết quả. Với first/last, kiểm tra thêm thứ tự nguồn vì "đầu tiên" và "cuối cùng" phụ thuộc thứ tự duyệt hiện tại; các toán tử này không tự sắp xếp collection.

## 11. Bảng so sánh hành vi collection

Bảng sau giúp chọn assertion phù hợp cho từng toán tử:

| Toán tử | Nguồn rỗng | Không có phần tử phù hợp | Có phần tử phù hợp |
|---|---|---|---|
| .?[condition] | Collection rỗng | Collection rỗng | Collection các phần tử phù hợp |
| .![expression] | Collection rỗng | Không áp dụng điều kiện lọc; projection xử lý các phần tử nguồn | Collection giá trị được chiếu |
| .^[condition] | null | null | Một phần tử đầu tiên phù hợp |
| .$[condition] | null | null | Một phần tử cuối cùng phù hợp |

Projection không lọc phần tử theo điều kiện. Nếu nguồn có N phần tử, projection đánh giá biểu thức trên từng phần tử theo thứ tự duyệt và tạo kết quả tương ứng. Nếu cần lọc rồi mới chiếu, hãy kết hợp selection và projection:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Với nguồn rỗng, kết quả cuối cùng là collection rỗng. Với nguồn không rỗng nhưng không có đơn hàng PAID, kết quả cũng rỗng.

## 12. Kiểm thử collection lồng nhau

Collection có thể chứa collection con. Ví dụ mỗi khách hàng có một danh sách đơn hàng:

~~~text
#customers.![orders.?[status == 'PAID'].![id]]
~~~

Kết quả là một collection lồng nhau; mỗi phần tử ngoài tương ứng một khách hàng, còn collection con chứa ID của các đơn hàng đã thanh toán.

Cần kiểm thử các tình huống:

- Không có khách hàng.
- Có khách hàng nhưng danh sách orders rỗng.
- Có khách hàng với orders không có đơn phù hợp.
- Có khách hàng với một hoặc nhiều đơn phù hợp.
- Property orders là null.
- Một phần tử trong collection ngoài là null, nếu nguồn cho phép.
- Dữ liệu con có property cần thiết là null.

Collection con rỗng không có nghĩa collection ngoài rỗng. Ví dụ có hai khách hàng nhưng cả hai không có đơn đã thanh toán thì kết quả có thể là hai collection con rỗng.

Nếu muốn bỏ các khách hàng không có đơn phù hợp, cần selection ở cấp ngoài:

~~~text
#customers.?[
    orders != null and orders.?[status == 'PAID'].size() > 0
].![name]
~~~

Biểu thức cần được kiểm thử với orders null, empty và có kết quả. Nếu logic lồng trở nên khó đọc, hãy tính trước trạng thái trong Java hoặc dùng method nghiệp vụ có tên rõ ràng.

## 13. Kiểm thử Map và collection khác

SpEL hỗ trợ selection trên Map. Điều kiện được đánh giá trên từng Map.Entry và có thể dùng key hoặc value.

Ví dụ:

~~~text
#scores.?[value >= #passingScore]
~~~

Với Map rỗng, kết quả selection là Map rỗng. Với Map có entry nhưng không entry nào đạt ngưỡng, kết quả cũng không có entry.

Cần kiểm tra:

- Map rỗng.
- Map có entry nhưng không phù hợp.
- Map có một hoặc nhiều entry phù hợp.
- Key hoặc value null nếu được phép.
- Implementation Map có thứ tự duyệt khác nhau.

Với Set, thứ tự duyệt phụ thuộc implementation. Với List, thứ tự thường là thứ tự phần tử trong danh sách. Điều này đặc biệt quan trọng khi kiểm thử first/last selection; dùng nguồn có thứ tự xác định nếu test cần kết quả ổn định.

## 14. Kiểm thử null và safe navigation

Collection null cần được kiểm thử riêng với collection rỗng. Nếu nguồn có thể null, hãy quyết định rõ biểu thức cần:

- Trả về null.
- Trả về collection rỗng.
- Trả về một trạng thái hoặc thông báo mặc định.
- Báo lỗi vì dữ liệu bắt buộc bị thiếu.

Ví dụ chuẩn hóa null thành collection rỗng trong biểu thức:

~~~text
#orders == null ? {} : #orders.?[status == 'PAID']
~~~

Cách này dùng inline list rỗng làm fallback. Nếu kết quả phải luôn là cùng kiểu collection cụ thể, việc chuẩn hóa trong Java thường rõ ràng hơn vì có thể tạo đúng kiểu collection mong muốn.

Safe navigation có thể bảo vệ việc truy cập trên một tham chiếu null:

~~~text
#customer?.address?.city
~~~

Với safe collection selection/projection, cú pháp và khả năng hỗ trợ phụ thuộc phiên bản Spring đang dùng. Hãy kiểm tra tài liệu của phiên bản dự án trước khi dùng; nếu muốn tương thích rộng, có thể kiểm tra null tường minh bằng ternary.

Đừng dùng safe navigation để che giấu dữ liệu bắt buộc bị thiếu. Test nên phân biệt trường hợp null được phép với trường hợp null phải bị từ chối.

## 15. Viết test với JUnit 5

Một test đơn giản có thể tạo parser, context và đánh giá expression:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class SpelCollectionTest {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    @Test
    void selectionOnEmptyListReturnsEmptyResult() {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("numbers", List.of());

        Expression expression =
            parser.parseExpression("#numbers.?[#this > 10]");

        List<?> result =
            expression.getValue(context, List.class);

        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    void firstSelectionOnEmptyListReturnsNull() {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("numbers", List.of());

        Expression expression =
            parser.parseExpression("#numbers.^[#this > 10]");

        assertNull(expression.getValue(context));
    }
}
~~~

Ví dụ xác nhận hai kiểu kết quả khác nhau: selection thường trả về collection rỗng, còn first selection trả về null khi không tìm thấy phần tử.

Không nên chỉ dùng assertNotNull cho mọi kết quả collection. Hãy kiểm tra cả kích thước, phần tử và thứ tự nếu thứ tự là một phần của hợp đồng.

## 16. Dùng parameterized test cho cả hai nhánh

JUnit 5 parameterized test giúp chạy cùng một quy tắc với nhiều bộ dữ liệu:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class SpelConditionTest {

    static Stream<org.junit.jupiter.params.provider.Arguments>
    conditionCases() {
        return Stream.of(
            org.junit.jupiter.params.provider.Arguments.of(true, "PAID"),
            org.junit.jupiter.params.provider.Arguments.of(false, "PENDING")
        );
    }

    @ParameterizedTest
    @MethodSource("conditionCases")
    void evaluatesBothConditionalBranches(
            boolean paid, String expected) {

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("paid", paid);

        Expression expression =
            new SpelExpressionParser().parseExpression(
                "#paid ? 'PAID' : 'PENDING'"
            );

        assertEquals(
            expected,
            expression.getValue(context, String.class)
        );
    }
}
~~~

Có thể mở rộng nguồn test để bao gồm các giá trị biên, null hoặc trạng thái đặc biệt. Nếu điều kiện nhận số tiền, dùng BigDecimal trong test để tránh sai số số thực và kiểm tra đúng bằng ngưỡng, thấp hơn ngưỡng và cao hơn ngưỡng.

Parameterized test giúp đảm bảo các trường hợp cùng một quy tắc được chạy nhất quán, đồng thời làm rõ bảng dữ liệu đầu vào và kết quả mong đợi.

## 17. Kiểm tra kiểu kết quả và exception

Ngoài giá trị, hãy kiểm tra kiểu kết quả mà ứng dụng mong đợi:

~~~java
String status = expression.getValue(context, String.class);
~~~

Với selection hoặc projection, kiểu collection ngoài có thể được yêu cầu qua getValue(context, List.class), nhưng kiểu generic của phần tử không được bảo đảm chỉ bởi List.class. Nếu cần List<String>, hãy kiểm tra từng phần tử hoặc chuyển đổi rõ ràng.

Cũng cần xác nhận các trường hợp phải lỗi:

- Biến bắt buộc chưa được đăng ký.
- Collection null trong biểu thức không bảo vệ null.
- Property lồng nhau null.
- Phần tử có kiểu không phù hợp.
- Method hoặc getter ném exception.
- Giá trị không chuyển đổi được sang kiểu đích.

Dùng assertThrows với loại exception phù hợp và không kiểm tra message quá chặt nếu message có thể thay đổi giữa các phiên bản Spring. Nên kiểm tra exception type, cause hoặc mã lỗi ổn định mà ứng dụng kiểm soát.

## 18. Kiểm thử dữ liệu biên và trường hợp đặc biệt

Một bộ test vững chắc nên bao gồm:

| Nhóm | Trường hợp |
|---|---|
| Điều kiện | true, false, đúng bằng ngưỡng, ngay dưới và trên ngưỡng |
| Elvis | null, chuỗi rỗng, chuỗi blank, 0, false |
| Logic | Đủ bốn tổ hợp AND/OR |
| Collection | null, empty, một phần tử, nhiều phần tử |
| Selection | Không match, một match, nhiều match |
| Projection | Empty, giá trị bình thường, phần tử có property null |
| First/last | Empty, no match, một match, nhiều match |
| Nested collection | Outer empty, inner empty, inner null, inner có match |
| Map | Empty, no match, match, key/value null |
| Kiểu dữ liệu | Kiểu đúng, kiểu khác, giá trị không chuyển đổi được |

Không cần tạo mọi tổ hợp có thể nếu chúng không có ý nghĩa nghiệp vụ. Hãy ưu tiên các trường hợp có thể thay đổi kết quả, kiểu trả về hoặc đường đi của expression.

Với mỗi expression, ghi rõ dữ liệu đầu vào và kết quả mong đợi. Điều đó giúp người bảo trì hiểu vì sao một trường hợp rỗng hoặc null được xem là hợp lệ.

## 19. Tách test parse khỏi test evaluate

Nên có kiểm thử parse riêng cho expression cố định:

~~~java
@Test
void expressionCanBeParsed() {
    assertDoesNotThrow(() ->
        new SpelExpressionParser().parseExpression(
            "#orders.?[#this > 10]"
        )
    );
}
~~~

Sau đó có test evaluate với context và dữ liệu thực tế. Test parse phát hiện lỗi cú pháp; test evaluate phát hiện lỗi biến, kiểu, property và dữ liệu.

Với template expression, parse bằng ParserContext tương ứng. Với expression dùng bean hoặc function, context test phải đăng ký resolver hoặc function giống cách ứng dụng chạy.

Một test parse thành công không thể thay thế test cho cả hai nhánh điều kiện hoặc collection rỗng. Các đường đi runtime phải được chạy bằng dữ liệu tương ứng.

## 20. Những lỗi kiểm thử thường gặp

Một số thiếu sót dễ làm test tạo cảm giác an toàn giả:

- Chỉ test nhánh true mà bỏ nhánh false.
- Chỉ test collection có dữ liệu và bỏ trường hợp rỗng.
- Dùng collection rỗng nhưng không test collection có phần tử mà không match.
- Gộp null với empty dù nghiệp vụ phân biệt hai trạng thái.
- Chỉ kiểm tra kết quả không null mà không kiểm tra nội dung.
- Kiểm tra first/last mà không kiểm soát thứ tự nguồn.
- Chỉ test expression parse thành công.
- Không test property lồng nhau null.
- Không xác nhận kiểu kết quả sau projection.
- Dùng dữ liệu không chạm đúng biên điều kiện.
- Không kiểm tra nhánh có function hoặc method call.
- Dùng cùng EvaluationContext mutable giữa test khiến trạng thái rò rỉ.

Mỗi test nên tạo context và dữ liệu riêng, trừ khi mục đích test chính là hành vi cập nhật hoặc tái sử dụng context. Điều này giúp kết quả độc lập và tránh phụ thuộc thứ tự chạy test.

## 21. Quy trình xây dựng bộ test

Có thể thực hiện theo trình tự:

1. Xác định expression source và ParserContext cần dùng.
2. Liệt kê biến, root object và kiểu dữ liệu cần thiết.
3. Viết bảng quyết định cho từng điều kiện.
4. Tạo bộ dữ liệu true/false và các giá trị biên.
5. Liệt kê collection empty, no-match, null và có kết quả.
6. Xác định kiểu kết quả cho selection, projection và first/last.
7. Viết test parse riêng.
8. Viết test evaluate bằng JUnit.
9. Dùng parameterized test cho các bộ dữ liệu lặp.
10. Thêm test exception cho các trạng thái phải bị từ chối.
11. Chạy test trên phiên bản Spring thực tế của dự án.
12. Giữ test hồi quy khi expression hoặc model thay đổi.

Với expression được cấu hình ngoài ứng dụng, hãy chạy test khi nạp hoặc cập nhật cấu hình để phát hiện lỗi cú pháp sớm. Dữ liệu runtime vẫn cần test riêng vì không thể bao phủ mọi trạng thái chỉ bằng parse.

## 22. Ghi nhớ

Hãy kiểm thử mọi nhánh có thể chạy của expression, đặc biệt là cả true và false của ternary, các trường hợp null của Elvis và bốn tổ hợp AND/OR. Ternary chỉ đánh giá nhánh được chọn; AND/OR có short-circuit, vì vậy test cần xác nhận cả trường hợp vế phải được đánh giá và trường hợp được bỏ qua.

Với collection, phân biệt nguồn rỗng, nguồn có dữ liệu nhưng không match và nguồn null. Selection thường không có kết quả trả về collection rỗng; projection trên nguồn rỗng cũng trả về collection rỗng; first/last selection không tìm thấy phần tử trả về null. Collection lồng nhau cần test riêng trạng thái của từng cấp.

Dùng JUnit 5 và parameterized test để bao phủ dữ liệu đúng, sai, biên và rỗng. Kiểm tra cả giá trị, kiểu kết quả, thứ tự khi có ý nghĩa và exception cần thiết. Parse test chỉ xác nhận cú pháp; evaluate test mới xác nhận expression hoạt động với context và dữ liệu thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)