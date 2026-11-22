# SpringEL compiler mode và ParserConfiguration

## Mục tiêu

Sau bài này, bạn có thể giải thích cách Spring Expression Language (SpEL) chuyển từ đánh giá biểu thức thông dịch sang thực thi bằng mã bytecode đã biên dịch; phân biệt ba chế độ `OFF`, `IMMEDIATE` và `MIXED`; cấu hình parser bằng `SpelParserConfiguration`; và quyết định khi nào nên bật biên dịch hoặc các tính năng tự mở rộng dữ liệu.

## 1. Từ parser đến kết quả đánh giá

Khi dùng SpEL, cần phân biệt ba giai đoạn:

1. **Phân tích (parse):** `SpelExpressionParser` đọc chuỗi biểu thức và tạo một đối tượng `Expression`.
2. **Đánh giá thông dịch (interpreted evaluation):** khi gọi `getValue(...)`, SpEL đánh giá cây biểu thức dựa trên đối tượng và ngữ cảnh lúc chạy.
3. **Đánh giá đã biên dịch (compiled evaluation):** nếu bật compiler và biểu thức thuộc nhóm được hỗ trợ, SpEL có thể tạo mã bytecode để những lần đánh giá tiếp theo chạy nhanh hơn.

Parser không có nghĩa là biểu thức đã được biên dịch. Việc gọi `parseExpression(...)` chủ yếu tạo đối tượng biểu thức; kết quả thực tế chỉ xuất hiện khi gọi một phương thức đánh giá như `getValue(...)`.

Ví dụ cơ bản:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#price * #quantity");

EvaluationContext context = new StandardEvaluationContext();
context.setVariable("price", new BigDecimal("12.50"));
context.setVariable("quantity", 4);

BigDecimal amount = expression.getValue(context, BigDecimal.class);
~~~

Đoạn mã này dùng parser mặc định. Nếu không cấu hình compiler, SpEL đánh giá biểu thức theo chế độ thông dịch. Khi cần thay đổi chế độ biên dịch hoặc các hành vi tự mở rộng dữ liệu, ta truyền một `SpelParserConfiguration` vào parser.

## 2. SpEL compiler giải quyết vấn đề gì?

Ở chế độ thông dịch, SpEL phải đi qua cấu trúc biểu thức và thực hiện các bước đánh giá cần thiết ở mỗi lần gọi. Với một biểu thức được đánh giá rất nhiều lần, phần chi phí này có thể đáng kể.

SpEL compiler có thể chuyển một biểu thức được hỗ trợ thành bytecode Java. Bytecode đó được nạp và thực thi trong JVM. Mục đích là giảm chi phí đánh giá lặp lại khi biểu thức và kiểu dữ liệu thực tế đủ ổn định.

Compiler thường có ích khi:

- Cùng một biểu thức được đánh giá lặp đi lặp lại trong đường chạy nóng.
- Kiểu của root object, thuộc tính và kết quả ổn định giữa các lần gọi.
- Biểu thức dùng các cấu trúc mà compiler của phiên bản Spring đang chạy hỗ trợ.
- Chi phí đánh giá biểu thức đủ lớn để tối ưu có ý nghĩa sau khi đo hiệu năng.

Compiler không phải một trình biên dịch đầy đủ cho mọi cú pháp SpEL. Một số biểu thức vẫn cần được đánh giá bằng cơ chế thông dịch. Bật compiler cũng không đảm bảo ứng dụng nhanh hơn trong mọi trường hợp: với biểu thức ít được gọi, chi phí biên dịch và quản lý mã có thể không đem lại lợi ích.

## 3. Ba chế độ biên dịch

SpEL cung cấp enum `SpelCompilerMode` với ba giá trị chính:

| Chế độ | Hành vi | Trường hợp phù hợp |
|---|---|---|
| `OFF` | Tắt biên dịch; biểu thức được đánh giá bằng cơ chế thông dịch | Mặc định an toàn, biểu thức ít chạy hoặc dữ liệu có kiểu thay đổi |
| `IMMEDIATE` | SpEL cố gắng chuyển biểu thức sang dạng biên dịch sớm trong quá trình đánh giá | Biểu thức nóng, kiểu dữ liệu ổn định và đã được kiểm thử |
| `MIXED` | Ban đầu đánh giá thông dịch; sau một số lần chạy, SpEL có thể chuyển sang biên dịch | Ứng dụng cần tự thích nghi giữa khởi động nhanh và tối ưu đường chạy nóng |

### 3.1. OFF

`OFF` là chế độ mặc định khi không yêu cầu compiler. SpEL tiếp tục đánh giá biểu thức bằng cơ chế thông dịch.

Chọn `OFF` khi:

- Biểu thức chỉ được đánh giá thỉnh thoảng.
- Kiểu dữ liệu đầu vào thay đổi nhiều.
- Cần hành vi dễ dự đoán trong giai đoạn phát triển hoặc gỡ lỗi.
- Biểu thức dùng cấu trúc không được compiler hỗ trợ.
- Đo hiệu năng chưa cho thấy biên dịch là nút thắt.

Tắt compiler không làm mất khả năng của ngôn ngữ SpEL. Nó chỉ quyết định cách thực thi biểu thức.

### 3.2. IMMEDIATE

`IMMEDIATE` yêu cầu SpEL thử biên dịch biểu thức sớm trong quá trình đánh giá. Sau khi có đủ thông tin từ lần đánh giá ban đầu, compiler có thể tạo mã thực thi cho biểu thức nếu biểu thức được hỗ trợ.

Chế độ này phù hợp khi ứng dụng kiểm soát biểu thức và biết rằng kiểu dữ liệu sẽ ổn định. Nếu mã đã biên dịch gặp tình huống không tương thích với giả định kiểu lúc biên dịch, lỗi có thể được chuyển tới nơi gọi. Vì vậy, không nên chọn chế độ này cho biểu thức nhận dữ liệu có hình dạng hoặc kiểu thay đổi tùy ý.

Ví dụ, nếu `#order.total` luôn trả về cùng một kiểu số và `#rate` cũng có kiểu ổn định, biểu thức tính tổng có cơ hội phù hợp hơn với compiler so với một biểu thức phụ thuộc vào nhiều loại đối tượng không đồng nhất.

### 3.3. MIXED

`MIXED` bắt đầu bằng đánh giá thông dịch. Sau khi biểu thức được đánh giá đủ số lần, SpEL có thể thử biên dịch để tối ưu những lần chạy tiếp theo.

Nếu việc thực thi ở dạng biên dịch gặp lỗi do giả định kiểu không còn đúng, chế độ `MIXED` có cơ chế quay lại thông dịch. Cơ chế này giúp ứng dụng linh hoạt hơn khi kiểu dữ liệu thực tế có thể thay đổi.

Đây thường là lựa chọn đáng cân nhắc khi:

- Ứng dụng có biểu thức được đánh giá lặp lại.
- Có thể có nhiều kiểu dữ liệu hoặc tình huống runtime hơn dự kiến.
- Muốn SpEL thử tối ưu sau khi đã quan sát cách biểu thức được dùng.
- Chấp nhận cơ chế tự chuyển về thông dịch khi mã đã biên dịch không còn phù hợp.

`MIXED` không thay thế việc kiểm thử. Nếu biểu thức liên tục đổi kiểu hoặc compiler không hỗ trợ cấu trúc đang dùng, lợi ích có thể thấp hoặc không xuất hiện.

## 4. Cấu hình compiler khi tạo parser

Lớp `SpelParserConfiguration` nằm trong package `org.springframework.expression.spel`. Có thể truyền chế độ compiler và class loader vào constructor, rồi dùng cấu hình đó để tạo `SpelExpressionParser`.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        OrderService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("#order.total * #rate");
~~~

Trong ví dụ:

- `SpelCompilerMode.MIXED` chọn chế độ thông dịch trước, sau đó có thể biên dịch khi biểu thức được dùng đủ nhiều.
- `OrderService.class.getClassLoader()` cung cấp class loader mà compiler có thể dùng khi tạo và nạp lớp chứa bytecode đã biên dịch.
- `SpelExpressionParser(configuration)` tạo parser sử dụng chính sách đã khai báo.

Class loader cần nhìn thấy các kiểu mà biểu thức tham chiếu. Trong ứng dụng chạy trong container, plugin hoặc môi trường có nhiều class loader, cần chọn class loader phù hợp với vòng đời và khả năng nhìn thấy các lớp của ứng dụng. Nếu không có yêu cầu đặc biệt, hãy dùng class loader của lớp ứng dụng sở hữu biểu thức.

Constructor không có tham số của `SpelExpressionParser` vẫn có thể được dùng khi chấp nhận thiết lập mặc định. Không cần bật compiler chỉ vì ứng dụng có sử dụng SpEL.

## 5. Cấu hình tự mở rộng null và collection

`SpelParserConfiguration` còn cho phép cấu hình hai hành vi tự mở rộng:

- `autoGrowNullReferences`: cho phép SpEL tự tạo đối tượng khi một đoạn đường dẫn thuộc tính gặp tham chiếu `null`, nếu có thể khởi tạo kiểu tương ứng.
- `autoGrowCollections`: cho phép SpEL tự mở rộng mảng hoặc collection khi biểu thức truy cập một chỉ số nằm ngoài kích thước hiện tại, trong giới hạn cho phép.
- `maximumAutoGrowSize`: giới hạn kích thước tối đa mà cơ chế tự mở rộng collection có thể tạo ra.

Ví dụ cấu hình đầy đủ:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        OrderService.class.getClassLoader(),
        true,   // autoGrowNullReferences
        true,   // autoGrowCollections
        128     // maximumAutoGrowSize
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Ví dụ, giả sử đối tượng `order` có thuộc tính `shippingAddress` đang là `null`. Nếu `autoGrowNullReferences` được bật và SpEL có thể tạo kiểu cần thiết, việc đánh giá đường dẫn:

~~~text
shippingAddress.city
~~~

có thể tạo đối tượng `shippingAddress` trước khi truy cập `city`.

Tương tự, nếu một danh sách có ít phần tử hơn chỉ số mà biểu thức cần truy cập, `autoGrowCollections` có thể làm danh sách lớn lên. Giới hạn `maximumAutoGrowSize` giúp ngăn việc mở rộng vượt quá mức đã cấu hình.

Cần nhớ rằng tự mở rộng có thể làm thay đổi đối tượng trong bộ nhớ. Nó không đơn thuần là thao tác đọc. Nếu biểu thức được dùng trên object đang được chia sẻ, được lưu lại hoặc tham gia giao dịch, việc tạo thêm đối tượng hay phần tử có thể ảnh hưởng đến trạng thái ứng dụng.

Hai tính năng tự mở rộng thường nên để tắt nếu nghiệp vụ không cần chúng. Chỉ bật khi có chủ đích và đặt giới hạn kích thước phù hợp. Kiểu đối tượng được tạo cũng cần có cách khởi tạo mà SpEL có thể sử dụng; không phải mọi kiểu đều có thể tự động tạo trong mọi tình huống.

## 6. Phân biệt ParserConfiguration và EvaluationContext

Hai đối tượng này giải quyết hai vấn đề khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `SpelParserConfiguration` | Cấu hình cách parser xử lý biểu thức, compiler mode, class loader và các tùy chọn tự mở rộng |
| `EvaluationContext` | Cung cấp dữ liệu và quyền mà biểu thức có thể dùng khi đánh giá, như root object, biến, function, bean resolver, property accessor và method resolver |
| `Expression` | Đại diện cho biểu thức đã phân tích và cung cấp các phương thức để lấy hoặc đặt giá trị khi được phép |

Ví dụ kết hợp parser cấu hình compiler với evaluation context:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        OrderService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("#order.total * #rate");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("rate", new BigDecimal("1.08"));

BigDecimal amount =
    expression.getValue(context, BigDecimal.class);
~~~

Ở đây, `ParserConfiguration` quyết định chính sách phân tích và thực thi của parser. `EvaluationContext` cung cấp biến `order` và `rate` cho biểu thức. Thay đổi compiler mode không tự tạo biến, không cấp quyền tra cứu bean và không thay thế việc cấu hình context.

Ngược lại, đổi từ `StandardEvaluationContext` sang một context hạn chế hơn là thay đổi quyền truy cập và khả năng đánh giá, không phải thay đổi compiler mode.

## 7. Giới hạn và điều kiện để biên dịch có hiệu quả

Không phải mọi biểu thức SpEL đều có thể chuyển thành bytecode. Khả năng biên dịch phụ thuộc vào cấu trúc biểu thức và phiên bản Spring đang chạy. Một số biểu thức có thể tiếp tục chạy bằng thông dịch ngay cả khi parser được cấu hình bật compiler.

Các yếu tố cần chú ý:

### 7.1. Kiểu dữ liệu phải đủ ổn định

Compiler tạo mã dựa trên những kiểu mà nó quan sát được trong quá trình đánh giá. Nếu cùng một biểu thức lúc nhận `String`, lúc nhận một kiểu số, hoặc các đối tượng có cấu trúc khác nhau, mã đã biên dịch có thể không còn phù hợp.

Hãy ưu tiên biểu thức có root object và kiểu thuộc tính rõ ràng, ổn định. Tránh giả định rằng một biểu thức có thể tối ưu tốt nếu nó nhận dữ liệu tùy ý từ nhiều nguồn.

### 7.2. Cấu trúc biểu thức phải được hỗ trợ

SpEL compiler chỉ hỗ trợ một tập con các cấu trúc ngôn ngữ. Một biểu thức hợp lệ về cú pháp vẫn có thể không biên dịch được. Khi đó, việc bật compiler không làm cho cú pháp đó trở nên được hỗ trợ.

Nếu một biểu thức không phù hợp, có thể giữ chế độ thông dịch. Không cần viết lại biểu thức chỉ để cố ép compiler sử dụng bytecode.

### 7.3. Biên dịch không thay đổi ý nghĩa nghiệp vụ

Compiler là cơ chế tối ưu cách thực thi. Nó không nên được dùng để thay đổi kết quả mong muốn của biểu thức. Cùng một biểu thức cần cho ra kết quả đúng với dữ liệu hợp lệ ở cả chế độ thông dịch và biên dịch.

### 7.4. Không đánh đồng biên dịch với kiểm tra kiểu tĩnh của Java

SpEL vẫn là ngôn ngữ biểu thức được đánh giá trong runtime. Bật compiler không biến nó thành một lớp mã Java được kiểm tra đầy đủ tại thời điểm biên dịch ứng dụng. Lỗi cú pháp, lỗi truy cập thuộc tính, lỗi chuyển đổi và lỗi dữ liệu vẫn cần được xử lý ở thời điểm thích hợp.

## 8. Cách chọn cấu hình trong ứng dụng

Có thể bắt đầu từ những lựa chọn thực tế sau:

| Tình huống | Cấu hình gợi ý | Lý do |
|---|---|---|
| Biểu thức ít chạy, dùng cho cấu hình thông thường | `OFF` | Giữ cấu hình đơn giản, không phát sinh bước biên dịch không cần thiết |
| Biểu thức nóng, kiểu dữ liệu cố định và được kiểm soát | `IMMEDIATE` | Cho phép tối ưu sớm khi có đủ cơ sở tin cậy |
| Biểu thức chạy nhiều lần nhưng kiểu runtime có thể thay đổi | `MIXED` | Có thể quay lại thông dịch khi mã biên dịch không còn phù hợp |
| Cần tự tạo đối tượng hoặc mở rộng collection khi truy cập | Bật đúng tùy chọn auto-grow cần thiết | Chỉ mở rộng dữ liệu khi nghiệp vụ yêu cầu và có giới hạn |
| Biểu thức lấy từ nguồn không đáng tin cậy | Giữ quyền context ở mức tối thiểu; cân nhắc tắt auto-grow | Hạn chế khả năng gây tác dụng phụ và truy cập đối tượng |

Đừng chọn `IMMEDIATE` hoặc `MIXED` chỉ vì tên chế độ nghe có vẻ nhanh hơn. Hãy đo thời gian đánh giá trong môi trường gần với production, với dữ liệu đại diện và số lần gọi thực tế. So sánh cả thời gian khởi động, chi phí lần chạy đầu, thông lượng sau khi nóng máy và hành vi khi kiểu dữ liệu thay đổi.

Nếu parser được tạo ở một nơi dùng chung, cấu hình của nó sẽ ảnh hưởng đến các biểu thức mà parser đó tạo ra. Khi các nhóm biểu thức có yêu cầu khác nhau về compiler hoặc auto-grow, hãy cân nhắc tạo parser với cấu hình riêng thay vì dùng một chính sách rộng cho tất cả.

## 9. Ví dụ hoàn chỉnh: tạo parser và đánh giá biểu thức

Ví dụ dưới đây chọn `MIXED`, dùng class loader của ứng dụng, không tự mở rộng đối tượng hoặc collection, rồi truyền dữ liệu bằng biến trong context:

~~~java
import java.math.BigDecimal;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class OrderExpressionService {

    public BigDecimal calculate(Order order) {
        SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                OrderExpressionService.class.getClassLoader(),
                false,
                false,
                128
            );

        ExpressionParser parser =
            new SpelExpressionParser(configuration);

        Expression expression =
            parser.parseExpression("#order.total * #taxRate");

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("order", order);
        context.setVariable("taxRate", new BigDecimal("1.08"));

        return expression.getValue(context, BigDecimal.class);
    }
}
~~~

Trong một ứng dụng thực tế, không nhất thiết phải tạo parser và phân tích lại cùng một biểu thức ở mỗi lần gọi như ví dụ minh họa. Nếu biểu thức cố định, có thể khởi tạo parser và `Expression` một lần ở thời điểm cấu hình hoặc khởi tạo service, sau đó tái sử dụng theo cách phù hợp với vòng đời ứng dụng. Context và dữ liệu đánh giá vẫn cần được cung cấp đúng cho mỗi lần thực thi.

## 10. Ghi nhớ

`SpelParserConfiguration` là nơi cấu hình chính sách của parser. Nó cho phép chọn compiler mode, cung cấp class loader và quyết định SpEL có tự tạo tham chiếu `null` hoặc tự mở rộng collection hay không.

`OFF` giữ SpEL ở chế độ thông dịch. `IMMEDIATE` yêu cầu biên dịch sớm khi có thể và phù hợp với kiểu dữ liệu ổn định. `MIXED` bắt đầu bằng thông dịch rồi có thể chuyển sang bytecode, đồng thời có thể quay lại thông dịch nếu mã đã biên dịch gặp vấn đề về kiểu.

Compiler chỉ tối ưu một số biểu thức được hỗ trợ; nó không thay đổi SpEL thành Java và không đảm bảo mọi ứng dụng đều nhanh hơn. `autoGrowNullReferences` và `autoGrowCollections` có thể thay đổi object graph trong bộ nhớ, nên chỉ bật khi cần và giới hạn kích thước phù hợp.

Hãy chọn parser configuration dựa trên tần suất đánh giá, độ ổn định của kiểu dữ liệu, quyền truy cập và hành vi mà nghiệp vụ thực sự cần.