# Chỉ số âm, chỉ số vượt giới hạn và lỗi đánh giá

Indexer trong Spring Expression Language (SpEL) dùng cú pháp dấu ngoặc vuông để truy cập một vị trí hoặc một giá trị theo khóa, ví dụ **items[0]**, **text[2]** hoặc **settings['theme']**. Khi chỉ số hoặc dữ liệu truy cập không hợp lệ, biểu thức có thể parse thành công nhưng phát sinh lỗi ở giai đoạn evaluation.

Cần phân biệt ba trường hợp: chỉ số âm trên cấu trúc truy cập theo vị trí, chỉ số lớn hơn phạm vi hiện có và key không tồn tại trong Map. Chúng không có cùng ý nghĩa và không nhất thiết tạo ra cùng kết quả.

## Chỉ số âm không phải cách truy cập từ cuối

Với **array**, **List** và **String**, SpEL sử dụng chỉ số bắt đầu từ 0 theo quy tắc của Java. Chỉ số 0 là phần tử hoặc ký tự đầu tiên; chỉ số cuối là độ dài trừ 1.

SpEL không dùng chỉ số âm theo quy ước của Python để truy cập ngược từ cuối. Ví dụ:

~~~java
List<String> names = List.of("An", "Binh", "Chi");

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();

String first = parser.parseExpression("#names[0]")
        .getValue(context, String.class);

// Chỉ số âm không có nghĩa là phần tử cuối
String last = parser.parseExpression("#names[-1]")
        .getValue(context, String.class);
~~~

Biểu thức **#names[0]** trả về An. Biểu thức **#names[-1]** không trả về Chi; nó gây lỗi khi SpEL cố truy cập List bằng chỉ số âm.

Muốn lấy phần tử cuối, hãy tính chỉ số hợp lệ từ kích thước collection hoặc chuẩn bị biến chỉ số trong Java:

~~~java
context.setVariable("lastIndex", names.size() - 1);

String last = parser.parseExpression("#names[#lastIndex]")
        .getValue(context, String.class);
~~~

Cách này làm rõ rằng vị trí cuối phụ thuộc kích thước collection tại thời điểm đánh giá. Nếu collection có thể rỗng, phải kiểm tra trước khi tính hoặc sử dụng chỉ số cuối.

## Chỉ số âm với String

String cũng sử dụng index bắt đầu từ 0. Chỉ số âm không truy cập ký tự từ cuối chuỗi:

~~~java
context.setVariable("code", "SPRING");

String first = parser.parseExpression("#code[0]")
        .getValue(context, String.class);

// Không phải ký tự cuối của chuỗi
String invalid = parser.parseExpression("#code[-1]")
        .getValue(context, String.class);
~~~

Biểu thức đầu trả về **"S"**. Biểu thức thứ hai phát sinh lỗi vì String không có vị trí âm.

Nếu muốn lấy ký tự cuối, có thể dùng **length() - 1** khi EvaluationContext cho phép gọi instance method:

~~~java
String last = parser.parseExpression(
        "#code[#code.length() - 1]")
        .getValue(context, String.class);
~~~

Hoặc tính chỉ số trong Java rồi truyền vào context. Cách thứ hai phù hợp khi dùng context chỉ đọc không bật method invocation.

Lưu ý rằng chỉ số String của Java dựa trên đơn vị UTF-16. Với emoji hoặc ký tự ngoài Basic Multilingual Plane, một ký tự người dùng nhìn thấy có thể chiếm hai đơn vị UTF-16. Vì vậy, lấy vị trí cuối theo **length() - 1** không nhất thiết lấy trọn một Unicode code point trong mọi chuỗi.

## Chỉ số vượt giới hạn của Array và List

Với array hoặc List, chỉ số hợp lệ phải nằm trong phạm vi từ 0 đến kích thước trừ 1. Chỉ số bằng kích thước hoặc lớn hơn kích thước đều nằm ngoài phạm vi.

~~~java
List<String> names = List.of("An", "Binh", "Chi");

context.setVariable("names", names);

String value = parser.parseExpression("#names[3]")
        .getValue(context, String.class);
~~~

List có ba phần tử, nên các chỉ số hợp lệ là 0, 1 và 2. Truy cập index 3 phát sinh lỗi evaluation. Tương tự, truy cập phần tử ngoài phạm vi của array cũng không trả về một giá trị mặc định.

Với dữ liệu đầu vào động, không nên giả định chỉ số luôn hợp lệ. Hãy kiểm tra kích thước trước khi đánh giá hoặc xử lý lỗi evaluation tại ranh giới phù hợp.

~~~java
int index = requestedIndex;

if (index < 0 || index >= names.size()) {
    throw new IllegalArgumentException("Index is outside the list bounds");
}

context.setVariable("index", index);

String value = parser.parseExpression("#names[#index]")
        .getValue(context, String.class);
~~~

Kiểm tra trong Java giúp ứng dụng trả về thông báo nghiệp vụ dễ hiểu thay vì để một lỗi truy cập nội bộ lan ra ngoài.

## Auto-grow collection có thể thay đổi hành vi

SpEL có tùy chọn **autoGrowCollections** trong **SpelParserConfiguration**. Khi được bật, một số collection có thể được tự mở rộng nếu biểu thức truy cập một chỉ số lớn hơn chỉ số cuối hiện có. Điều này hữu ích trong data binding, nhưng có thể gây bất ngờ nếu biểu thức chỉ được dùng để đọc dữ liệu.

Ví dụ cấu hình parser với auto-grow và giới hạn kích thước:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                false,  // không tự khởi tạo null reference
                true,   // cho phép tự mở rộng collection
                128);   // giới hạn kích thước auto-grow

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Khi collection có thể mở rộng và index nằm ngoài kích thước hiện tại nhưng vẫn trong giới hạn cấu hình, SpEL có thể thêm các vị trí cần thiết. Các vị trí mới có thể chứa null cho đến khi được gán giá trị.

Auto-grow không biến chỉ số âm thành chỉ số hợp lệ. Nó cũng không phải cách xử lý chung cho mọi cấu trúc: String là immutable, array có kích thước cố định và Map truy cập theo key thay vì vị trí. Collection không hỗ trợ thay đổi kích thước cũng có thể không mở rộng được.

Nếu biểu thức chỉ cần đọc, nên cân nhắc tắt auto-grow. Nếu cần bật cho binding, hãy đặt giới hạn hợp lý và nhớ rằng việc đọc một index lớn có thể làm thay đổi collection trong bộ nhớ.

## Giới hạn kích thước auto-grow

Việc tự mở rộng đến một chỉ số rất lớn có thể tiêu tốn bộ nhớ và thời gian. Tham số **maximumAutoGrowSize** giới hạn kích thước mà SpEL được phép mở rộng trong cơ chế auto-grow.

Ví dụ, nếu giới hạn là 128, ứng dụng không nên kỳ vọng SpEL tự mở rộng collection đến hàng triệu phần tử chỉ vì biểu thức yêu cầu index lớn. Khi vượt giới hạn, quá trình evaluation có thể phát sinh lỗi.

Giới hạn này giúp kiểm soát một hành vi cụ thể của parser. Nó không thay thế việc xác thực chỉ số đầu vào, giới hạn kích thước dữ liệu tổng thể hoặc kiểm soát tài nguyên của ứng dụng.

Với biểu thức lấy từ người dùng, nên giới hạn index trước khi đưa vào context. Không nên dựa hoàn toàn vào maximumAutoGrowSize để xử lý dữ liệu đầu vào không đáng tin cậy.

## Chỉ số không tồn tại trong Map khác với index ngoài phạm vi

Map được truy cập bằng **key**, không phải vị trí tuần tự. Vì vậy, một key âm có thể hoàn toàn hợp lệ nếu Map chứa key đó:

~~~java
Map<Integer, String> labels = new HashMap<>();
labels.put(-1, "Special");

context.setVariable("labels", labels);

String label = parser.parseExpression("#labels[-1]")
        .getValue(context, String.class);
~~~

Trong ví dụ này, **-1** là key của Map. Nó không có nghĩa là phần tử cuối cùng. Nếu Map chứa key -1, biểu thức có thể trả về giá trị Special.

Nếu key không tồn tại, thao tác tra cứu Map thông thường trả về null. Đây là điểm khác với List hoặc String: chỉ số ngoài phạm vi trên cấu trúc truy cập theo vị trí thường phát sinh lỗi, còn key vắng mặt trong Map có thể đơn giản là không có giá trị.

Khi Map cho phép giá trị null, cần phân biệt key không tồn tại với key tồn tại nhưng có value null nếu nghiệp vụ cần biết chính xác hai trường hợp này. Có thể kiểm tra bằng Java trước khi đưa dữ liệu vào biểu thức.

## String rỗng và collection rỗng

Một String rỗng có độ dài bằng 0, một List rỗng có kích thước bằng 0 và một array rỗng cũng không có phần tử nào. Không có index hợp lệ để đọc từ các cấu trúc này.

~~~java
context.setVariable("text", "");
context.setVariable("items", Collections.emptyList());

String character =
        parser.parseExpression("#text[0]")
                .getValue(context, String.class);

String item =
        parser.parseExpression("#items[0]")
                .getValue(context, String.class);
~~~

Cả hai biểu thức đều không có phần tử tại index 0. Nếu chuỗi hoặc collection có thể rỗng, hãy kiểm tra độ dài hoặc kích thước trước khi truy cập.

Có thể thực hiện kiểm tra trong Java, hoặc chuẩn bị một biến Boolean như **#hasItems** trong context rồi dùng nó trong biểu thức điều kiện. Cách nào phù hợp tùy context có cho phép những method cần thiết hay không.

## Phân biệt null với index ngoài phạm vi

Một đối tượng null và một chỉ số không hợp lệ là hai vấn đề khác nhau:

- **Đối tượng null:** không có object để thực hiện indexing.
- **Index ngoài phạm vi:** object tồn tại nhưng vị trí yêu cầu không tồn tại.
- **Key Map không có:** Map tồn tại nhưng không chứa key được yêu cầu.

Từ **Spring Framework 6.2**, SpEL hỗ trợ null-safe indexing bằng cú pháp **?.[index]**:

~~~java
context.setVariable("text", null);

String first = parser.parseExpression("#text?.[0]")
        .getValue(context, String.class);
~~~

Nếu text là null, biểu thức trả về null thay vì cố truy cập index. Tuy nhiên, null-safe indexing không biến một index ngoài phạm vi thành hợp lệ. Nếu text là chuỗi rỗng, **#text?.[0]** vẫn có thể phát sinh lỗi do vị trí 0 không tồn tại.

Với phiên bản Spring trước 6.2, cú pháp này không được hỗ trợ. Khi cần tương thích các phiên bản cũ, hãy kiểm tra null trong Java trước khi đánh giá.

## Lỗi phát sinh ở giai đoạn evaluation

Chuỗi **#items[10]** có thể parse thành công vì cú pháp indexing là hợp lệ. Lỗi chỉ xuất hiện khi SpEL đánh giá biểu thức trên một collection không có phần tử ở index 10.

Nên phân biệt:

- **ParseException:** chuỗi biểu thức sai cú pháp, ví dụ thiếu dấu ngoặc hoặc viết sai toán tử.
- **EvaluationException:** biểu thức parse được nhưng không thể đánh giá với root object, context hoặc dữ liệu hiện tại. Các lỗi truy cập index thường thuộc nhóm này và có thể được biểu diễn bằng một SpelEvaluationException cụ thể.

Ví dụ tách hai giai đoạn:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#items[#index]");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String item = expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot access indexed value", ex);
}
~~~

Việc tách lỗi giúp xác định vấn đề nằm ở chuỗi cú pháp hay dữ liệu thực tế. Khi log, nên ghi mã biểu thức, loại cấu trúc đang truy cập và index đã được kiểm tra theo chính sách phù hợp; tránh ghi toàn bộ object nếu có dữ liệu nhạy cảm.

## Không nên che giấu lỗi bằng giá trị mặc định tùy tiện

Khi index không hợp lệ, có thể muốn trả về chuỗi rỗng hoặc phần tử mặc định để tránh lỗi. Tuy nhiên, việc thay lỗi bằng giá trị mặc định có thể làm dữ liệu sai trở nên khó nhận biết.

Ví dụ, nếu mã đơn hàng cần có ít nhất sáu ký tự nhưng biểu thức truy cập index 5 trên một chuỗi ngắn, trả về chuỗi rỗng có thể khiến hệ thống phân loại sai mã. Trong trường hợp này, xác thực độ dài và trả lỗi đầu vào rõ ràng sẽ phù hợp hơn.

Chỉ dùng giá trị mặc định khi đó là quy tắc nghiệp vụ có chủ đích, chẳng hạn một key Map không tồn tại được phép dùng nhãn mặc định. Không nên biến mọi IndexOutOfBounds thành null hoặc chuỗi rỗng một cách tổng quát.

## Quy tắc thực hành khi dùng indexer

- Với String, array và List, dùng index không âm bắt đầu từ 0.
- Kiểm tra index nhỏ hơn độ dài hoặc kích thước trước khi đánh giá nếu dữ liệu đến từ bên ngoài.
- Không coi index âm là cách truy cập từ cuối.
- Với Map, xem giá trị trong ngoặc là key; key âm có thể hợp lệ.
- Chỉ bật auto-grow khi thật sự cần data binding và đặt maximumAutoGrowSize phù hợp.
- Phân biệt null object, index ngoài phạm vi và key Map không tồn tại.
- Dùng null-safe indexing từ Spring 6.2 khi cần xử lý đối tượng đích null; vẫn phải kiểm tra index.
- Bắt và phân loại lỗi evaluation ở ranh giới phù hợp, không che giấu dữ liệu đầu vào sai bằng mặc định tùy tiện.

## Kết luận

Indexer của SpEL không dùng chỉ số âm để truy cập từ cuối đối với String, array hoặc List. Chỉ số âm và chỉ số vượt phạm vi thường dẫn đến lỗi evaluation. Map lại tra cứu theo key, nên một key âm có thể hợp lệ và key không tồn tại thường trả về null.

Auto-grow collection có thể mở rộng một số collection khi index vượt kích thước hiện tại, nhưng không làm chỉ số âm hợp lệ và có thể thay đổi trạng thái object. Hãy đặt giới hạn kích thước, xác thực index và phân biệt rõ null với vị trí không tồn tại. Khi dữ liệu đầu vào không đáng tin cậy, xử lý kiểm tra trong Java trước khi đánh giá SpEL thường giúp hành vi dễ dự đoán và dễ chẩn đoán hơn.
