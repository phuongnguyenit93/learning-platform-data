# Đánh đổi giữa linh hoạt, chẩn đoán lỗi và hiệu năng khi cấu hình parser

**SpelExpressionParser** có thể hoạt động với cấu hình mặc định hoặc nhận một **SpelParserConfiguration** để điều chỉnh cách SpEL xử lý biểu thức. Cấu hình parser ảnh hưởng đến những việc như tự mở rộng collection, tự khởi tạo property null và biên dịch biểu thức. Mỗi lựa chọn đem lại sự tiện lợi hoặc hiệu năng trong một số tình huống, nhưng cũng có thể làm thay đổi hành vi, tác động đến dữ liệu hoặc khiến lỗi khó chẩn đoán hơn.

Khi cấu hình parser, cần bắt đầu từ đặc điểm của biểu thức và dữ liệu thực tế: biểu thức do ai cung cấp, được đánh giá bao nhiêu lần, có được phép thay đổi object hay không, và điều gì cần xảy ra khi cú pháp hoặc dữ liệu không hợp lệ.

## Parser mặc định và parser có cấu hình

Trong trường hợp thông thường, có thể tạo parser mà không truyền cấu hình:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("price * quantity");
~~~

Parser mặc định phù hợp với biểu thức SpEL thông dụng. Khi cần điều chỉnh hành vi, tạo **SpelParserConfiguration** rồi truyền vào **SpelExpressionParser**:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(false, false);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Hai tham số boolean trong constructor này lần lượt điều khiển việc tự khởi tạo null reference và tự mở rộng collection. Trong ví dụ, cả hai khả năng đều tắt. Cách này thích hợp khi muốn biểu thức chỉ làm việc với cấu trúc dữ liệu đã tồn tại và tránh thay đổi object ngoài dự kiến.

Cấu hình parser và evaluation context đảm nhiệm hai phần khác nhau. Parser configuration điều chỉnh một số hành vi của parser và quá trình đánh giá biểu thức; **EvaluationContext** cung cấp root object, biến, property accessor, method resolver và các khả năng truy cập khác. Chọn parser configuration không thay thế việc giới hạn những gì biểu thức có thể nhìn thấy trong context.

## Tự khởi tạo property null và tự mở rộng collection

Một tính năng tiện lợi của SpEL là có thể tự tạo object trung gian khi truy cập property null và tự mở rộng collection khi biểu thức truy cập đến một chỉ mục chưa tồn tại. Hai hành vi này được điều khiển bởi:

- **autoGrowNullReferences:** cho phép tự khởi tạo một property trung gian đang null khi biểu thức cần đi sâu vào property đó.
- **autoGrowCollections:** cho phép mở rộng collection khi biểu thức truy cập một chỉ mục nằm ngoài kích thước hiện tại, trong giới hạn cấu hình.

Ví dụ, giả sử một object có cấu trúc lồng nhau và **address** đang null. Nếu bật auto-grow null references, một biểu thức truy cập sâu như **address.city** có thể khiến SpEL tạo object trung gian khi kiểu property cho phép khởi tạo.

Tương tự, khi collection có ít phần tử hơn chỉ mục được truy cập, auto-grow collections có thể mở rộng collection để đáp ứng truy cập đó. Điều này hữu ích trong một số tình huống binding dữ liệu biểu mẫu, nhưng có thể gây bất ngờ nếu mục đích của biểu thức chỉ là đọc dữ liệu.

Có thể bật hai tính năng này bằng constructor tương ứng:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Với cấu hình này, việc đánh giá biểu thức có thể làm thay đổi object hoặc collection. Nếu chỉ cần kiểm tra hoặc hiển thị dữ liệu, nên cân nhắc tắt auto-grow để giữ hành vi đọc rõ ràng và tránh tạo thêm trạng thái ngoài ý muốn.

### Giới hạn kích thước khi auto-grow

Tự mở rộng collection cần có giới hạn. Nếu biểu thức yêu cầu một chỉ mục rất lớn, việc mở rộng không kiểm soát có thể tiêu tốn bộ nhớ và thời gian. SpEL cung cấp cấu hình giới hạn kích thước auto-grow trong các constructor **SpelParserConfiguration** có tham số **maximumAutoGrowSize**.

Khi chọn giới hạn, hãy căn cứ vào kích thước collection hợp lý trong nghiệp vụ. Giới hạn này là một hàng rào bảo vệ cho thao tác auto-grow; nó không thay thế việc kiểm tra dữ liệu đầu vào hoặc giới hạn tài nguyên ở các phần khác của ứng dụng.

## Biên dịch biểu thức và hiệu năng

Mặc định, SpEL đánh giá biểu thức theo cơ chế thông dịch. Với biểu thức được đánh giá rất nhiều lần, có thể cân nhắc **SpelCompiler** để biên dịch biểu thức thành bytecode và giảm chi phí đánh giá lặp lại trong các trường hợp phù hợp.

Chế độ biên dịch được điều khiển qua **SpelCompilerMode**:

| Chế độ | Hành vi | Đánh đổi |
|---|---|---|
| **OFF** | Không biên dịch biểu thức; đánh giá bằng interpreter | Hành vi ổn định, không có chi phí biên dịch; có thể chậm hơn với biểu thức nóng |
| **IMMEDIATE** | Thử biên dịch biểu thức ngay trong lần đánh giá đầu tiên | Có thể cải thiện hiệu năng sớm; lỗi hoặc biểu thức không biên dịch được có thể lộ ra ngay khi chạy |
| **MIXED** | Bắt đầu bằng interpreter, sau một số lần đánh giá thì thử biên dịch | Giảm chi phí biên dịch cho biểu thức ít dùng; có cơ chế quay lại thông dịch nếu biểu thức đã biên dịch gặp vấn đề khi chạy |

Ví dụ cấu hình chế độ biên dịch:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                getClass().getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Trong ví dụ, parser được cấu hình ở chế độ MIXED và sử dụng class loader của ứng dụng. Chế độ này cho phép SpEL quan sát biểu thức qua các lần đánh giá trước khi thử biên dịch.

Không phải biểu thức nào cũng biên dịch được. Khả năng biên dịch phụ thuộc vào cấu trúc biểu thức, kiểu dữ liệu quan sát được và những tính năng SpEL mà compiler hỗ trợ. Biểu thức có kiểu thay đổi giữa các lần đánh giá hoặc dựa nhiều vào hành vi động có thể không phù hợp với compiler. Với những trường hợp đó, interpreter vẫn là cơ chế cần thiết.

Không nên bật compiler chỉ vì một biểu thức có vẻ phức tạp. Biên dịch có chi phí ban đầu và có thể làm tăng độ phức tạp khi chẩn đoán. Chỉ nên cân nhắc sau khi đã đo hiệu năng của workload thực tế và xác nhận biểu thức được dùng lặp lại đủ nhiều để bù chi phí.

## Tái sử dụng Expression trước khi tối ưu bằng compiler

Một cải thiện quan trọng thường đơn giản hơn việc bật compiler là **parse biểu thức một lần rồi tái sử dụng Expression**. Phân tích cú pháp tạo ra cấu trúc biểu thức; nếu ứng dụng parse lại cùng một chuỗi trong mỗi lần gọi, nó lặp lại công việc không cần thiết.

Không nên tổ chức theo cách này trong đường chạy nóng:

~~~java
public BigDecimal calculate(Product product) {
    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("price * quantity");

    return expression.getValue(product, BigDecimal.class);
}
~~~

Thay vào đó, giữ parser và Expression ở nơi phù hợp với vòng đời ứng dụng:

~~~java
private final ExpressionParser parser =
        new SpelExpressionParser();

private final Expression totalExpression =
        parser.parseExpression("price * quantity");

public BigDecimal calculate(Product product) {
    return totalExpression.getValue(product, BigDecimal.class);
}
~~~

Expression được parse khi khởi tạo thành phần chứa nó và được đánh giá trên từng product. Cách này tránh parse lặp lại, giúp phát hiện lỗi cú pháp sớm hơn và làm cho chi phí parse tách khỏi chi phí evaluate.

Nếu biểu thức đến từ cấu hình có thể thay đổi, có thể cache Expression theo chuỗi biểu thức. Cache cần có giới hạn kích thước và chính sách thay thế phù hợp để tránh tăng bộ nhớ không giới hạn khi có nhiều chuỗi khác nhau. Với biểu thức cố định trong mã nguồn, một field hoặc thành phần khởi tạo một lần thường đã đủ.

## Chẩn đoán lỗi ở giai đoạn parse

Parser có thể phát hiện lỗi cú pháp trước khi biểu thức được đánh giá. Ví dụ, thiếu dấu ngoặc hoặc đặt toán tử sai vị trí có thể làm **parseExpression(...)** phát sinh **ParseException**.

~~~java
Expression expression;

try {
    expression = parser.parseExpression("price > ");
} catch (ParseException ex) {
    // Ghi nhận chuỗi không hợp lệ và thông tin vị trí lỗi
    throw new IllegalArgumentException("Invalid expression syntax", ex);
}
~~~

Thông tin trong ParseException giúp xác định chuỗi biểu thức và vị trí cú pháp có vấn đề. Khi biểu thức được lấy từ cấu hình, nên kiểm tra cú pháp tại thời điểm nạp cấu hình hoặc khởi tạo ứng dụng nếu có thể. Như vậy, lỗi cấu hình được phát hiện gần nguồn phát sinh thay vì chỉ xuất hiện khi một yêu cầu cụ thể chạy đến biểu thức đó.

Đối với hệ thống cho phép người dùng nhập biểu thức, cần trả thông báo dễ hiểu nhưng tránh đưa quá nhiều chi tiết nội bộ hoặc stack trace ra giao diện. Có thể lưu chi tiết lỗi ở log phía máy chủ cùng mã định danh yêu cầu để phục vụ điều tra.

## Chẩn đoán lỗi ở giai đoạn evaluation

Parse thành công không đảm bảo biểu thức luôn đánh giá được. Một biểu thức có thể đúng cú pháp nhưng tham chiếu đến property không tồn tại, nhận giá trị null ở vị trí không hỗ trợ null, gọi phương thức không có trong context hoặc thực hiện phép toán trên kiểu không tương thích.

Những lỗi này xuất hiện khi gọi **getValue(...)** hoặc **setValue(...)** và thường thuộc nhóm **EvaluationException**:

~~~java
try {
    BigDecimal total =
            totalExpression.getValue(product, BigDecimal.class);
} catch (EvaluationException ex) {
    // Biểu thức hợp lệ nhưng không thể đánh giá với dữ liệu hiện tại
    throw new IllegalStateException("Expression evaluation failed", ex);
}
~~~

Khi ghi log, nên ghi nhận tên hoặc mã biểu thức đã được quản lý, loại lỗi, root object type và ngữ cảnh nghiệp vụ cần thiết. Tránh ghi toàn bộ object có thể chứa thông tin nhạy cảm. Nếu biểu thức được định danh trong cấu hình, mã định danh đó thường hữu ích hơn việc chỉ ghi một thông báo lỗi chung.

Nên phân biệt lỗi parse và lỗi evaluation trong xử lý ngoại lệ. ParseException chỉ ra vấn đề ở chuỗi cú pháp; EvaluationException chỉ ra vấn đề khi thực hiện biểu thức trên dữ liệu hoặc context cụ thể. Việc phân loại này giúp đội vận hành xác định nên sửa cấu hình, dữ liệu hay môi trường đánh giá.

## Giới hạn độ dài biểu thức và bề mặt cấu hình

Nếu ứng dụng nhận biểu thức từ nguồn bên ngoài, cần giới hạn kích thước chuỗi và phạm vi tính năng. Các phiên bản Spring có hỗ trợ cấu hình giới hạn độ dài biểu thức thông qua **SpelParserConfiguration**; hãy chọn giới hạn phù hợp với phiên bản Spring đang dùng và độ phức tạp tối đa của use case.

Một biểu thức quá dài hoặc có cấu trúc phức tạp có thể làm tăng chi phí parse, khó đọc và khó chẩn đoán. Giới hạn độ dài không thay thế giới hạn thời gian thực thi hay kiểm soát quyền truy cập của evaluation context, nhưng là một hàng rào đầu vào hữu ích.

Cũng cần xem xét ai có thể thay đổi biểu thức. Nếu chỉ đội phát triển quản lý biểu thức trong mã nguồn, có thể ưu tiên khả năng biểu đạt và lỗi được phát hiện trong quá trình khởi động hoặc kiểm thử. Nếu biểu thức được chỉnh sửa qua giao diện quản trị hoặc gửi từ người dùng, nên dùng context giới hạn, xác thực trước khi lưu và theo dõi lỗi đánh giá.

## Chọn cấu hình theo mục tiêu

Có thể chọn cấu hình theo những tình huống phổ biến sau:

| Tình huống | Hướng cấu hình |
|---|---|
| Biểu thức cố định, đánh giá không thường xuyên | Dùng parser mặc định; ưu tiên đơn giản |
| Chỉ đọc property của DTO | Tắt auto-grow; dùng root object phù hợp |
| Binding dữ liệu cần tạo property trung gian hoặc mở rộng list | Bật auto-grow có chủ đích và đặt giới hạn |
| Cùng biểu thức được đánh giá trên nhiều object | Parse một lần, tái sử dụng Expression |
| Biểu thức nóng, chạy nhiều lần và kiểu dữ liệu ổn định | Đo hiệu năng trước; cân nhắc compiler mode |
| Biểu thức do người dùng cung cấp | Giới hạn độ dài, root object, context và khả năng truy cập; xử lý riêng lỗi parse/evaluation |

Không có một cấu hình tối ưu cho mọi ứng dụng. Cấu hình tốt là cấu hình chỉ bật những hành vi mà use case cần, có giới hạn rõ ràng và có cách quan sát lỗi phù hợp.

## Kết luận

Cấu hình parser là một quyết định cân bằng giữa tính linh hoạt, khả năng chẩn đoán và hiệu năng. Auto-grow giúp binding thuận tiện nhưng có thể thay đổi object; compiler có thể tăng tốc biểu thức nóng nhưng không hỗ trợ mọi cấu trúc và cần được đo lường; parse một lần và tái sử dụng Expression thường là bước tối ưu dễ áp dụng. Tách lỗi parse khỏi lỗi evaluation, giới hạn đầu vào và chọn context phù hợp giúp ứng dụng giữ được hành vi có thể dự đoán khi dùng SpEL.
