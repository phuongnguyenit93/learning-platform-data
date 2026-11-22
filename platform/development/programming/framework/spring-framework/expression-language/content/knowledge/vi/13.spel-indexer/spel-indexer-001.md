# Indexer trên mảng và list

## Mục tiêu

Sau bài này, bạn có thể dùng indexer của Spring Expression Language (SpEL) để đọc phần tử trong mảng Java và List; hiểu chỉ số bắt đầu từ 0; dùng biểu thức làm chỉ số; truy cập cấu trúc lồng nhau; và cập nhật phần tử khi đối tượng cho phép ghi. Bạn cũng sẽ biết cách xử lý chỉ số ngoài phạm vi, collection null, phần tử null và khác biệt về khả năng thay đổi giữa mảng với các loại List.

## 1. Indexer là gì?

Indexer là cú pháp truy cập một phần tử theo vị trí bằng cặp dấu ngoặc vuông:

~~~text
target[index]
~~~

Trong SpEL, indexer có thể truy cập phần tử của mảng và List. Ví dụ:

~~~text
#scores[0]
~~~

Biểu thức trên lấy phần tử đầu tiên trong biến #scores. Cú pháp này tương tự cách truy cập mảng trong Java và cách gọi List.get(index), nhưng được viết trực tiếp trong chuỗi biểu thức.

Indexer hữu ích khi một quy tắc cấu hình cần lấy phần tử theo vị trí, đọc một thuộc tính của phần tử hoặc tính toán với dữ liệu đã có trong bộ nhớ. Nó không tự truy vấn cơ sở dữ liệu và cũng không tạo ra một collection mới.

## 2. Chỉ số bắt đầu từ 0

Mảng Java và List đều dùng chỉ số bắt đầu từ 0:

| Chỉ số | Vị trí | Ví dụ với danh sách [10, 20, 30] |
|---:|---|---:|
| 0 | Phần tử thứ nhất | 10 |
| 1 | Phần tử thứ hai | 20 |
| 2 | Phần tử thứ ba | 30 |

Ví dụ với SpEL:

~~~text
#scores[0]
#scores[1]
#scores[2]
~~~

Nếu danh sách có ba phần tử, chỉ số hợp lệ là 0, 1 và 2. Không dùng chỉ số 1 để chỉ phần tử đầu tiên như cách đếm thông thường.

SpEL dùng quy tắc chỉ số của Java. Chỉ số âm không có ý nghĩa “đếm từ cuối” như trong một số ngôn ngữ khác. Ví dụ #scores[-1] không lấy phần tử cuối cùng; nó là một chỉ số không hợp lệ.

Muốn lấy phần tử cuối cùng, hãy dùng kích thước collection để tính chỉ số:

~~~text
#scores[#scores.size() - 1]
~~~

Biểu thức này chỉ hợp lệ khi #scores khác null và có ít nhất một phần tử. Nếu danh sách rỗng, chỉ số tính được là -1 và việc truy cập sẽ thất bại.

## 3. Truy cập mảng bằng indexer

Giả sử Java cung cấp một mảng điểm số:

~~~java
int[] scores = {75, 82, 91};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("scores", scores);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#scores[1]");

Integer secondScore =
    expression.getValue(context, Integer.class);
~~~

Kết quả là 82 vì chỉ số 1 tương ứng với phần tử thứ hai.

Indexer hoạt động với mảng kiểu tham chiếu và mảng kiểu nguyên thủy. Ví dụ, có thể truy cập các phần tử của String[], Integer[], int[] hoặc double[] theo cùng cú pháp.

Với mảng kiểu nguyên thủy như int[], Java không lưu các phần tử dưới dạng đối tượng Integer. Khi SpEL lấy một phần tử để trả về cho ứng dụng, giá trị có thể được đóng gói thành kiểu wrapper tương ứng. Khi yêu cầu kiểu kết quả qua getValue(..., Integer.class), hãy bảo đảm kiểu đích phù hợp với phần tử.

Mảng có độ dài cố định. Có thể thay đổi giá trị một phần tử nếu mảng có thể ghi, nhưng không thể thêm hoặc xóa phần tử để thay đổi độ dài của chính mảng.

## 4. Truy cập List bằng indexer

List cũng dùng cú pháp dấu ngoặc vuông:

~~~text
#names[0]
#names[1]
~~~

Ví dụ Java:

~~~java
List<String> names =
    new ArrayList<>(List.of("An", "Binh", "Chi"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#names[1]");

String secondName =
    expression.getValue(context, String.class);
~~~

Kết quả là "Binh".

Indexer giúp biểu thức ngắn gọn khi cần đọc một phần tử. Nếu đang viết Java trực tiếp, List.get(index) vẫn là API thông thường. Nếu đang viết SpEL, #names[1] là cú pháp truy cập phần tử tương ứng.

List là một interface nên hành vi thực tế phụ thuộc implementation:

- ArrayList hỗ trợ truy cập theo chỉ số nhanh trong điều kiện thông thường.
- LinkedList vẫn có thể được truy cập theo chỉ số nhưng việc đi đến vị trí xa có thể tốn thời gian hơn.
- List không sửa đổi được hoặc danh sách bất biến có thể cho phép đọc nhưng từ chối thao tác ghi.

Khi một biểu thức được đánh giá thường xuyên, hãy cân nhắc cấu trúc collection phù hợp với kiểu truy cập. Truy cập nhiều vị trí ngẫu nhiên thường phù hợp với ArrayList hoặc mảng hơn LinkedList.

## 5. Dùng biểu thức để tính chỉ số

Chỉ số trong dấu ngoặc vuông cũng có thể là một biểu thức SpEL. Nó không nhất thiết phải là một con số viết cố định.

Ví dụ:

~~~text
#items[#selectedIndex]
~~~

Hoặc:

~~~text
#items[#page * #pageSize + #offset]
~~~

Trong trường hợp thứ hai, SpEL tính chỉ số từ số trang, kích thước trang và độ lệch trước khi truy cập phần tử.

Có thể truyền chỉ số từ Java:

~~~java
context.setVariable("items", items);
context.setVariable("selectedIndex", 2);

Expression expression =
    parser.parseExpression("#items[#selectedIndex]");

Object selected = expression.getValue(context);
~~~

Cách này giúp tái sử dụng cùng một biểu thức với các vị trí khác nhau. Ứng dụng chỉ cần cập nhật biến trong context cho lần đánh giá tương ứng.

Tuy nhiên, chỉ số động cần được kiểm tra. Một chỉ số được tính đúng về mặt cú pháp vẫn có thể âm hoặc lớn hơn chỉ số cuối cùng của mảng/List.

## 6. Truy cập thuộc tính của phần tử

Indexer có thể kết hợp với toán tử truy cập thuộc tính. Nếu một phần tử là đối tượng Java, có thể đọc thuộc tính của phần tử ngay sau dấu ngoặc vuông.

Ví dụ:

~~~text
#employees[0].name
~~~

SpEL lấy nhân viên đầu tiên trong danh sách rồi đọc thuộc tính name.

Với một đối tượng đơn hàng có danh sách mặt hàng:

~~~text
#order.items[1].price
~~~

Biểu thức lần lượt lấy order, truy cập items, lấy mặt hàng ở chỉ số 1 và đọc price.

Điều này hữu ích trong cấu hình khi cần lấy một trường từ phần tử cụ thể. Hãy nhớ rằng mọi mắt xích trung gian đều phải tồn tại và có kiểu phù hợp. Nếu order, items hoặc phần tử được lấy ra là null, việc truy cập thuộc tính tiếp theo có thể phát sinh lỗi.

## 7. Truy cập cấu trúc lồng nhau

Mảng có thể chứa mảng khác, và List có thể chứa các List con. Khi đó có thể dùng nhiều indexer liên tiếp.

Ví dụ với mảng hai chiều:

~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6}
};

context.setVariable("matrix", matrix);
~~~

Biểu thức:

~~~text
#matrix[1][2]
~~~

lấy mảng con ở chỉ số 1 rồi lấy phần tử ở chỉ số 2. Kết quả là 6.

Với List lồng nhau:

~~~java
List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C", "D")
);

context.setVariable("groups", groups);
~~~

Biểu thức:

~~~text
#groups[1][0]
~~~

trả về "C".

Mỗi cặp ngoặc vuông truy cập một cấp. Mỗi chỉ số phải hợp lệ đối với đúng mảng hoặc List ở cấp đó. Một chỉ số hợp lệ ở collection ngoài không bảo đảm chỉ số ở collection con cũng hợp lệ.

## 8. Phân biệt mảng và List

Cú pháp indexer của SpEL tương tự nhau, nhưng cấu trúc dữ liệu có các đặc điểm khác nhau:

| Đặc điểm | Mảng Java | List |
|---|---|---|
| Cú pháp SpEL | #array[index] | #list[index] |
| Chỉ số đầu tiên | 0 | 0 |
| Độ dài/kích thước | Cố định sau khi tạo | Phụ thuộc implementation |
| Thay thế phần tử hiện có | Có, nếu mảng có thể ghi | Có nếu List hỗ trợ set |
| Thêm/xóa phần tử | Không thể thay đổi độ dài mảng | Có nếu List hỗ trợ add/remove |
| Kiểu phần tử | Có kiểu thành phần xác định | Có thể khai báo generic; kiểu thực tế vẫn phụ thuộc object lưu bên trong |
| Lỗi chỉ số ngoài phạm vi | Không truy cập được phần tử | Không truy cập được phần tử |

Mảng thường phù hợp khi số lượng phần tử đã biết và ít thay đổi. List phù hợp khi ứng dụng cần các thao tác collection như thêm, xóa hoặc thay thế phần tử tùy implementation.

Indexer chỉ giải quyết việc truy cập theo vị trí. Nó không làm cho mảng có khả năng thay đổi kích thước và cũng không khiến một List bất biến trở thành List có thể sửa đổi.

## 9. Ghi hoặc thay thế phần tử

Trong context cho phép ghi và khi đối tượng đích hỗ trợ cập nhật, indexer có thể được dùng để đặt giá trị cho phần tử.

Ví dụ với List có thể sửa đổi:

~~~java
List<String> names =
    new ArrayList<>(List.of("An", "Binh", "Chi"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();
Expression element = parser.parseExpression("#names[1]");

element.setValue(context, "Minh");
~~~

Sau thao tác này, phần tử ở chỉ số 1 được thay bằng "Minh". Danh sách trở thành ["An", "Minh", "Chi"].

Với mảng, có thể đặt lại giá trị của một phần tử nếu kiểu giá trị tương thích:

~~~java
int[] scores = {75, 82, 91};

context.setVariable("scores", scores);

Expression element = parser.parseExpression("#scores[1]");
element.setValue(context, 90);
~~~

Mảng sau thao tác có các phần tử 75, 90 và 91; độ dài vẫn là 3.

Đây là thao tác ghi vào phần tử đã tồn tại. Gán giá trị ở một index không có nghĩa là chèn phần tử mới vào giữa List hoặc tự tăng độ dài mảng. Muốn thêm hoặc xóa phần tử, hãy dùng API collection trong Java theo đúng yêu cầu nghiệp vụ.

Nếu List bất biến hoặc không hỗ trợ set, thao tác ghi có thể ném ngoại lệ. Với mảng có kiểu thành phần cụ thể, giá trị không tương thích cũng có thể bị từ chối hoặc phát sinh lỗi chuyển đổi.

## 10. Chỉ số ngoài phạm vi và collection null

Indexer cần một mảng/List tồn tại và một chỉ số hợp lệ.

Ví dụ, các truy cập sau không hợp lệ nếu danh sách có ba phần tử:

~~~text
#items[3]
#items[-1]
~~~

Chỉ số hợp lệ là 0, 1 và 2. Truy cập ngoài phạm vi thường làm lần đánh giá SpEL thất bại với lỗi đánh giá chỉ số.

Nếu chính collection là null, SpEL cũng không thể truy cập phần tử:

~~~text
#items[0]
~~~

Trong trường hợp #items là null, cần xử lý trước khi đánh giá indexer.

Nếu collection có thể null hoặc rỗng, có thể dùng điều kiện bảo vệ:

~~~text
#items != null and
#items.size() > 0 and
#items[0] != null
~~~

SpEL dùng đánh giá ngắn mạch cho toán tử and, nên vế sau chỉ cần được đánh giá khi điều kiện trước đã đúng. Khi cần đọc phần tử đầu tiên, hãy kiểm tra cả collection khác null và có ít nhất một phần tử.

Nếu phần tử tại index hợp lệ nhưng bản thân phần tử là null, indexer vẫn có thể trả về null. Lỗi chỉ xuất hiện khi biểu thức tiếp tục gọi phương thức hoặc đọc thuộc tính trên phần tử null mà không có xử lý phù hợp.

## 11. Auto-grow và giới hạn kích thước

SpEL có tùy chọn cấu hình auto-grow cho collection thông qua SpelParserConfiguration. Khi tính năng phù hợp được bật, SpEL có thể mở rộng collection khi một biểu thức truy cập vị trí vượt kích thước hiện tại, trong giới hạn được cấu hình.

Ví dụ cấu hình:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        false,
        true,
        64
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Trong constructor dạng này, các tham số lần lượt điều khiển auto-grow null references, auto-grow collections và giới hạn kích thước mở rộng tối đa.

Auto-grow là hành vi cần được bật có chủ đích. Nó có thể làm thay đổi dữ liệu trong bộ nhớ khi đánh giá biểu thức. Không nên dựa vào nó để thay thế việc kiểm tra chỉ số hoặc xác thực dữ liệu đầu vào.

Đặc biệt, hãy phân biệt việc mở rộng collection với đặc tính độ dài cố định của mảng Java. Nếu ứng dụng cần thay đổi kích thước hoặc cấu trúc của dữ liệu, hãy chọn mô hình collection và API Java phù hợp. Kiểm tra Javadoc của phiên bản Spring đang dùng để xác định chính xác hành vi auto-grow được hỗ trợ cho kiểu dữ liệu cụ thể.

## 12. Ví dụ hoàn chỉnh với cả mảng và List

Ví dụ dưới đây tạo một context chứa mảng điểm số và danh sách tên, sau đó truy cập phần tử bằng indexer:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class IndexerExample {

    public static void main(String[] args) {
        int[] scores = {75, 82, 91};

        List<String> names =
            new ArrayList<>(List.of("An", "Binh", "Chi"));

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("scores", scores);
        context.setVariable("names", names);

        ExpressionParser parser = new SpelExpressionParser();

        Integer secondScore = parser
            .parseExpression("#scores[1]")
            .getValue(context, Integer.class);

        String firstName = parser
            .parseExpression("#names[0]")
            .getValue(context, String.class);

        System.out.println(secondScore); // 82
        System.out.println(firstName);   // An
    }
}
~~~

Ví dụ này cho thấy cùng một cú pháp indexer có thể dùng cho mảng và List. Kiểu trả về được yêu cầu qua getValue giúp Java nhận kết quả với kiểu mong muốn khi có thể chuyển đổi phù hợp.

Trong ứng dụng thực tế, nếu biểu thức cố định và được dùng nhiều lần, có thể phân tích biểu thức một lần rồi tái sử dụng đối tượng Expression. Mỗi lần đánh giá, cung cấp context và dữ liệu phù hợp với vòng đời của ứng dụng.

## 13. Kiểm thử các trường hợp biên

Khi kiểm thử indexer, hãy bao gồm các trường hợp:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Chỉ số 0 | Lấy đúng phần tử đầu tiên |
| Chỉ số cuối hợp lệ | Lấy đúng phần tử cuối |
| Chỉ số bằng kích thước | Xử lý lỗi ngoài phạm vi |
| Chỉ số âm | Không được hiểu là đếm từ cuối |
| Mảng hoặc List null | Không thể truy cập phần tử |
| Collection rỗng | Không có chỉ số hợp lệ |
| Phần tử null | Đọc index có thể trả null; truy cập tiếp thuộc tính cần xử lý |
| List bất biến | Đọc được nhưng ghi có thể thất bại |
| Ghi sai kiểu vào mảng | Kiểm tra chuyển đổi và kiểu thành phần |
| Cấu trúc lồng nhau | Kiểm tra chỉ số ở từng cấp |

Với biểu thức dùng chỉ số động, hãy kiểm thử cả giá trị nhỏ nhất, lớn nhất và các giá trị nằm ngoài phạm vi. Nếu chỉ số đến từ request hoặc cấu hình bên ngoài, nên xác thực ở Java trước khi đưa vào EvaluationContext.

## 14. Ghi nhớ

Indexer của SpEL dùng cú pháp target[index] để truy cập phần tử mảng hoặc List. Chỉ số bắt đầu từ 0; chỉ số âm không có ý nghĩa lấy từ cuối; và mỗi chỉ số phải hợp lệ với cấu trúc đang được truy cập.

Có thể dùng biến hoặc biểu thức để tính chỉ số, kết hợp indexer với truy cập thuộc tính, và lồng nhiều indexer cho mảng hai chiều hoặc List lồng nhau. Trong context và đối tượng cho phép ghi, indexer cũng có thể thay thế một phần tử hiện có.

Mảng có độ dài cố định nhưng phần tử có thể được cập nhật. List có khả năng thay đổi tùy implementation; List bất biến có thể từ chối ghi. Hãy xử lý collection null, collection rỗng, phần tử null và chỉ số ngoài phạm vi; chỉ bật auto-grow khi đã hiểu rõ tác động của cấu hình.

Dùng indexer cho việc truy cập phần tử theo vị trí trong dữ liệu đã có. Nếu cần thêm/xóa phần tử, truy vấn dữ liệu hoặc điều phối logic phức tạp, hãy thực hiện ở lớp Java với API phù hợp.