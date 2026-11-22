# EvaluationException và lỗi trong lúc đánh giá

SpEL tách quá trình sử dụng biểu thức thành hai giai đoạn chính: phân tích chuỗi expression để tạo đối tượng Expression, sau đó đánh giá Expression với dữ liệu và EvaluationContext cụ thể. Lỗi có thể xuất hiện ở cả hai giai đoạn. Phân biệt đúng thời điểm lỗi giúp xác định nguyên nhân nằm ở cú pháp, dữ liệu đầu vào, cấu hình context, chuyển đổi kiểu hay method được gọi.

Trong Spring Expression, EvaluationException là nhóm exception dành cho lỗi khi xử lý biểu thức. SpEL có các lớp cụ thể như SpelParseException cho lỗi phân tích và SpelEvaluationException cho nhiều lỗi lúc đánh giá. Khi xử lý lỗi, cần xem cả loại exception, vị trí trong expression, message code và nguyên nhân gốc thay vì chỉ đọc một dòng thông báo.

## 1. Hai giai đoạn: parse và evaluate

Một expression thường được tạo bằng ExpressionParser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("name == 'Lan'");
~~~

Lệnh parseExpression phân tích chuỗi và tạo Expression. Nếu chuỗi sai cú pháp, lỗi xảy ra ngay trong giai đoạn parse.

Sau đó, getValue đánh giá expression:

~~~java
Boolean result = expression.getValue(
        context,
        rootObject,
        Boolean.class
);
~~~

Lỗi trong giai đoạn này có thể do property không tồn tại, object null, method không phân giải được, đối số sai kiểu, converter không hỗ trợ hoặc method được gọi ném exception.

Hai giai đoạn nên được xử lý riêng trong code. Điều này giúp log và báo lỗi chính xác hơn, đặc biệt khi expression được parse một lần rồi đánh giá nhiều lần với dữ liệu khác nhau.

## 2. Các exception chính của Spring Expression

Một số lớp exception thường gặp:

| Exception | Vai trò |
|---|---|
| EvaluationException | Lớp exception tổng quát cho lỗi đánh giá biểu thức |
| ParseException | Lỗi trong quá trình phân tích expression |
| SpelParseException | Lớp SpEL cụ thể cho lỗi parse |
| SpelEvaluationException | Lớp SpEL cụ thể cho lỗi evaluate |

ParseException và SpelParseException thuộc nhánh exception của Spring Expression dành cho parse. SpelEvaluationException thường được dùng khi SpEL không thể hoàn tất thao tác lúc đánh giá.

Không phải mọi lỗi đều có cùng nguyên nhân. Một lỗi parse thường chỉ ra chuỗi không đúng grammar; một lỗi evaluate có thể phụ thuộc vào root object hoặc context chỉ xuất hiện tại runtime.

Khi viết catch block, hãy bắt exception cụ thể nhất mà ứng dụng có thể xử lý. Nếu cần catch cả nhóm, dùng EvaluationException ở ranh giới evaluate sau khi đã tách lỗi parse.

## 3. Bắt lỗi parse riêng với lỗi evaluate

Ví dụ:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "#order.total > 100"
    );
} catch (ParseException ex) {
    // Chuỗi expression không hợp lệ.
    throw ex;
}

try {
    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
} catch (EvaluationException ex) {
    // Expression đã parse nhưng không thể đánh giá.
    throw ex;
}
~~~

Cần bắt ParseException trước nếu dùng chung một try block vì nó thuộc hệ exception của Spring Expression và có thể được xem như một dạng EvaluationException.

Nếu ứng dụng parse expression khi khởi động, lỗi parse có thể ngăn context khởi tạo. Nếu expression được đánh giá theo từng request, lỗi evaluate có thể chỉ xảy ra với một tập dữ liệu hoặc một context cụ thể.

Đừng gộp cả hai thành một thông báo chung như “SpEL failed”. Hãy ghi nhận giai đoạn lỗi để người vận hành biết nên kiểm tra cấu hình expression hay dữ liệu runtime.

## 4. SpelParseException: lỗi cú pháp

SpelParseException xuất hiện khi parser không thể hiểu chuỗi expression. Nguyên nhân thường gặp gồm:

- Thiếu hoặc thừa dấu ngoặc.
- Chuỗi literal không đóng dấu nháy.
- Sai cú pháp toán tử hoặc toán hạng.
- Cấu trúc selection/projection không hợp lệ.
- Cú pháp function, type reference hoặc bean reference bị viết sai.
- Dấu phân cách trong biểu thức lồng nhau không đúng.

Ví dụ lỗi:

~~~java
parser.parseExpression("total >");
parser.parseExpression("'Spring");
parser.parseExpression("#items.?[active == true");
~~~

Parser không thể tạo Expression hợp lệ từ các chuỗi này.

Khi chẩn đoán, hãy kiểm tra vị trí lỗi mà exception cung cấp nếu có. Với expression dài, vị trí ký tự giúp tìm dấu ngoặc hoặc toán tử bị sai nhanh hơn so với việc đọc lại toàn bộ chuỗi.

Nếu expression được tạo bằng cách nối nhiều chuỗi, hãy log hoặc tái tạo chuỗi cuối cùng đã đưa vào parser. Đừng chỉ log từng mảnh vì lỗi có thể xuất hiện tại ranh giới giữa hai mảnh.

## 5. SpelEvaluationException: lỗi lúc evaluate

SpelEvaluationException xuất hiện khi expression đã được parse nhưng một thao tác không thể hoàn thành lúc chạy.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("customer.address.city");

String city = expression.getValue(
        context,
        rootObject,
        String.class
);
~~~

Expression có thể parse thành công, nhưng khi evaluate sẽ lỗi nếu customer không tồn tại trên root object, address là null hoặc property accessor không thể đọc city.

Các nguyên nhân khác gồm:

- Property hoặc method không tồn tại.
- Method không được phép gọi trong context hiện tại.
- Function chưa đăng ký.
- Bean hoặc type không thể phân giải.
- Index hoặc key không hợp lệ.
- Kiểu dữ liệu không tương thích với toán tử.
- Conversion không thực hiện được.
- Getter, setter hoặc method ném exception.

Để tìm nguyên nhân, hãy kiểm tra root object, variables và resolver của đúng EvaluationContext được truyền vào getValue. Cùng một Expression có thể chạy thành công với context này nhưng thất bại với context khác.

## 6. Đọc vị trí và mã lỗi

Các exception của Spring Expression có thể cung cấp thông tin về vị trí trong expression, message code và các giá trị liên quan đến lỗi. Với SpEL, SpelMessage mô tả các loại lỗi cụ thể như không tìm thấy property, không gọi được method hoặc không chuyển đổi được kiểu.

Khi xử lý, nên ghi nhận tối thiểu:

- Loại exception.
- Message code nếu exception cụ thể cung cấp.
- Vị trí lỗi nếu có.
- Tên rule hoặc mã cấu hình đang được đánh giá.
- Nguyên nhân gốc trong cause chain.
- Loại root object và phiên bản rule nếu thông tin này an toàn để log.

Không nên phụ thuộc vào toàn bộ message text để phân loại lỗi vì nội dung thông báo có thể thay đổi theo phiên bản framework hoặc ngôn ngữ. Nếu cần xử lý theo mã lỗi, hãy dùng API exception tương ứng và kiểm tra phiên bản Spring mà ứng dụng đang chạy.

Tránh ghi toàn bộ root object hoặc mọi context variable vào log. Dữ liệu có thể chứa thông tin cá nhân, token, thông tin tài khoản hoặc bí mật cấu hình.

## 7. Lỗi không tìm thấy property

Expression có thể tham chiếu property không tồn tại trên object hiện tại:

~~~text
#customer.dispayName
~~~

Ví dụ trên viết sai tên displayName. Parser vẫn có thể chấp nhận cú pháp, nhưng khi evaluate, PropertyAccessor không tìm được property tương ứng.

Nguyên nhân thường gặp:

- Sai chính tả tên property.
- Root object khác kiểu dự kiến.
- Getter không tuân theo quy ước property mà accessor nhận diện.
- PropertyAccessor tùy chỉnh không hỗ trợ kiểu object.
- Context giới hạn quyền đọc property.
- Expression đang ở trong collection operation nên object hiện tại khác với root object.

Hãy xác nhận object thực tế và property path ở từng cấp. Với expression có #this, kiểm tra xem #this đang trỏ tới root object hay một phần tử collection.

Không nên xử lý mọi lỗi property bằng cách trả về null. Property bị cấm, property sai tên và property có giá trị null là các tình huống khác nhau, cần được phân biệt.

## 8. Lỗi null khi truy cập object lồng nhau

Một property path có thể đi qua nhiều object:

~~~text
#order.customer.address.city
~~~

Nếu customer hoặc address là null, truy cập tiếp có thể thất bại. Đây là lỗi runtime, không phải lỗi cú pháp.

Có thể kiểm tra trước:

~~~text
#order.customer != null and
#order.customer.address != null and
#order.customer.address.city == 'Da Nang'
~~~

AND có short-circuit: khi một điều kiện bên trái là false, các điều kiện phía sau không cần được đánh giá.

SpEL cũng có safe navigation operator ?. trong các ngữ cảnh truy cập phù hợp:

~~~text
#order.customer?.address?.city
~~~

Safe navigation có thể giúp trả null khi object trước toán tử là null. Tuy nhiên, cần hiểu cách toán tử này lan truyền qua toàn bộ expression và kiểu kết quả mong muốn. Nó không thay thế validation nếu property bắt buộc phải tồn tại.

Nếu dữ liệu đầu vào thiếu cấu trúc là lỗi nghiệp vụ, hãy phát hiện và báo lỗi rõ ràng thay vì biến mọi trường hợp thành null.

## 9. Lỗi method resolution và method invocation

Expression có thể gọi method trên root object, biến hoặc property object:

~~~text
#customer.calculateDiscount()
#text.substring(0, 5)
~~~

Lỗi có thể xảy ra khi:

- Object không có method được gọi.
- Số lượng hoặc kiểu đối số không phù hợp.
- MethodResolver không cho phép method đó.
- Method không truy cập được.
- Method được chọn ném exception khi chạy.
- Một đối số null không được method xử lý.

Phân biệt lỗi không tìm thấy method với lỗi bên trong method. Nếu method đã được gọi và ném exception, hãy xem cause gốc để xác định lỗi thuộc logic Java hay thuộc SpEL.

Không nên bắt mọi exception rồi coi method trả về null. Điều đó có thể che giấu lỗi trong service, database hoặc quy tắc domain. Hãy để method có hợp đồng rõ ràng và xử lý exception tại application layer phù hợp.

## 10. Lỗi function chưa đăng ký hoặc sai chữ ký

Function đã đăng ký được gọi bằng cú pháp #functionName(...). Nếu function không tồn tại trong EvaluationContext, SpEL không thể phân giải lời gọi.

~~~text
#normalize(#rawName)
~~~

Các nguyên nhân thường gặp:

- Function chưa được đăng ký trong context đang đánh giá.
- Tên trong registerFunction khác tên trong expression.
- Context được tạo lại nhưng không đăng ký function.
- Function bị ghi đè bởi binding cùng tên trong context.
- Số lượng hoặc kiểu đối số không phù hợp với Method đã đăng ký.
- Conversion sang kiểu tham số thất bại.

Hãy kiểm tra cấu hình function tại đúng context, không chỉ kiểm tra nơi khởi tạo parser. Parser tạo Expression; EvaluationContext cung cấp function và các binding khi evaluate.

Nếu function dùng nhiều overload, hãy xác định rõ Method được đăng ký. Tên function đã đăng ký gắn với Method cụ thể, nên đừng kỳ vọng SpEL tự chọn overload như cách gọi method thông thường trên object.

## 11. Lỗi type reference và bean reference

Type reference dùng cú pháp T(...). Nếu TypeLocator không phân giải được class, expression có thể parse được nhưng thất bại khi evaluate:

~~~text
T(com.example.MissingType)
~~~

Bean reference dùng cú pháp @beanName. Nếu BeanResolver không được cấu hình hoặc bean không tồn tại, việc phân giải có thể thất bại:

~~~text
@pricingService.currentRate()
~~~

Hãy kiểm tra:

- Tên class và package.
- TypeLocator đang được context sử dụng.
- Bean name và ApplicationContext.
- BeanResolver có được cung cấp hay không.
- Context hiện tại có hỗ trợ type/bean reference hay không.

SimpleEvaluationContext giới hạn nhiều tính năng so với StandardEvaluationContext. Một expression dùng T(...) hoặc @beanName có thể không phù hợp với context giới hạn. Không nên mở rộng context chỉ để làm lỗi biến mất nếu use case không thực sự cần khả năng đó.

## 12. Lỗi indexer, collection và Map

Indexer có thể dùng để đọc List, array hoặc Map:

~~~text
#items[0]
#settings['region']
~~~

Lỗi runtime có thể xuất hiện khi:

- Index âm hoặc vượt phạm vi array/List.
- Collection nguồn là null.
- Key không có trong Map và biểu thức tiếp tục truy cập property trên kết quả null.
- Key có kiểu khác với key thực tế.
- Collection không hỗ trợ thao tác ghi.
- Phần tử tại vị trí được chọn là null.

Với Map, key không tồn tại thường cho kết quả null. Nếu cần phân biệt key thiếu với value null, dùng containsKey() trước khi đọc.

Với List hoặc array, kiểm tra kích thước trước khi truy cập index nếu vị trí đến từ dữ liệu động. Với thao tác ghi, xác nhận collection mutable và vị trí đích đã tồn tại.

## 13. Lỗi toán tử và kiểu dữ liệu không tương thích

Một expression có thể dùng toán tử trên các kiểu dữ liệu không phù hợp:

~~~text
#price + #customer
#createdAt > #quantity
~~~

SpEL có cơ chế toán tử và conversion, nhưng không phải mọi cặp kiểu đều có ý nghĩa hoặc có thể chuyển đổi.

Ví dụ, phép cộng giữa hai số có thể hợp lệ; phép cộng giữa một số và object domain tùy thuộc toán tử, converter và kiểu dữ liệu thực tế. So sánh hai object cũng phụ thuộc kiểu và khả năng so sánh.

Hãy kiểm tra runtime type của các biến và property. Nếu cần chuyển đổi, thực hiện conversion rõ ràng hoặc chuẩn hóa dữ liệu trước khi đưa vào context.

Đừng dựa vào việc một expression parse thành công để kết luận phép toán chắc chắn hợp lệ. Parse kiểm tra cú pháp; nhiều vấn đề về kiểu chỉ xuất hiện khi expression được đánh giá với dữ liệu cụ thể.

## 14. Lỗi chuyển đổi kiểu

SpEL có thể dùng TypeConverter của EvaluationContext khi cần chuyển giá trị sang kiểu đích, ví dụ trong typed getValue, gán property hoặc gọi method có tham số khác kiểu.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("#rawAge");

Integer age = expression.getValue(
        context,
        Integer.class
);
~~~

Nếu rawAge là chuỗi "twenty", converter mặc định không thể chuyển thành Integer. Lỗi xảy ra trong giai đoạn evaluate hoặc conversion.

Các nguyên nhân thường gặp:

- Dữ liệu nguồn sai định dạng.
- Không có converter cho cặp kiểu nguồn/đích.
- Converter tùy chỉnh từ chối giá trị.
- Giá trị null được gán vào primitive.
- Kiểu trả về không tương thích với kiểu mà caller yêu cầu.

Khi cần kiểu domain riêng, có thể cấu hình StandardTypeConverter với ConversionService có converter tương ứng. Converter nên chỉ chịu trách nhiệm chuyển kiểu; validation nghiệp vụ vẫn phải thực hiện riêng.

## 15. Lỗi khi ghi property bằng setValue

Expression.setValue cũng đánh giá đường dẫn property và thực hiện ghi, nên có thể phát sinh EvaluationException.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("address.city");

expression.setValue(context, customer, "Da Nang");
~~~

Lỗi có thể xảy ra nếu:

- Property không tồn tại hoặc không có setter.
- Object trung gian address là null.
- Accessor hiện tại chỉ cho đọc.
- Giá trị mới không chuyển đổi được sang kiểu đích.
- Object hoặc collection không hỗ trợ cập nhật.
- Setter ném exception do validation hoặc invariant.

Đọc được property không có nghĩa chắc chắn ghi được property. Với object bất biến, hãy tạo object mới bằng constructor hoặc factory thay vì cố gắng dùng setValue.

Nếu expression chỉ cần đọc, hãy dùng context read-only. Không cấp quyền ghi chỉ để tránh một lỗi accessor.

## 16. Exception từ method được gọi bên trong expression

Khi SpEL gọi method Java, method có thể ném exception như IllegalArgumentException, IllegalStateException hoặc exception nghiệp vụ riêng. Framework có thể bọc lỗi này trong exception đánh giá.

Ví dụ:

~~~java
public static BigDecimal calculateTax(BigDecimal amount) {
    if (amount.signum() < 0) {
        throw new IllegalArgumentException(
                "Amount must be non-negative"
        );
    }
    return amount.multiply(new BigDecimal("0.08"));
}
~~~

Nếu expression gọi function trên với amount âm, lỗi gốc đến từ method. Hãy kiểm tra cause chain để phân biệt method đã chạy và từ chối dữ liệu với lỗi SpEL không phân giải được function.

Method dùng trong expression nên có hợp đồng rõ, kiểm tra input và tránh side effect. Nếu method có thể gọi database hoặc API, cần quyết định rõ cách xử lý lỗi, timeout và transaction ở tầng service.

## 17. Chiến lược xử lý lỗi theo use case

Không có một chính sách mặc định phù hợp cho mọi expression. Cách xử lý phụ thuộc hậu quả nếu expression không đánh giá được.

| Use case | Hướng xử lý thường phù hợp |
|---|---|
| Cấu hình bắt buộc khi khởi động | Fail fast và báo rõ expression/property gây lỗi |
| Rule quyết định quyền truy cập | Fail closed; lỗi không được biến thành cho phép |
| Giá trị hiển thị không bắt buộc | Có thể dùng fallback đã xác định |
| Rule do quản trị viên cấu hình | Báo lỗi validation trước khi publish rule |
| Expression theo request | Ghi nhận lỗi có mã request/rule và trả lỗi phù hợp |
| Tính toán tài chính | Không dùng default âm thầm; chuyển lỗi về tầng nghiệp vụ |

Không nên trả true khi expression lỗi nếu expression quyết định quyền, eligibility hoặc điều kiện quan trọng. Một fallback chỉ an toàn khi nghiệp vụ đã xác định rõ giá trị thay thế và người vận hành biết khi nào fallback được dùng.

Với cấu hình bắt buộc, fail-fast thường giúp phát hiện lỗi ngay lúc khởi động thay vì để ứng dụng chạy trong trạng thái sai.

## 18. Log lỗi có ích mà không lộ dữ liệu

Log nên giúp tái hiện vấn đề nhưng không làm lộ thông tin nhạy cảm.

Thông tin hữu ích:

- Rule ID hoặc tên expression đã được định danh.
- Giai đoạn parse hay evaluate.
- Loại exception và message code nếu có.
- Vị trí lỗi nếu exception cung cấp.
- Loại root object.
- Phiên bản cấu hình hoặc mã deployment.
- Cause gốc đã được lọc thông tin nhạy cảm.

Tránh log password, access token, thông tin thanh toán, toàn bộ entity hoặc mọi context variable. Nếu expression được người dùng cung cấp, chuỗi expression cũng có thể chứa dữ liệu cá nhân; hãy áp dụng chính sách log phù hợp.

Không nên ghi stack trace đầy đủ cho mọi lỗi đầu vào dự kiến ở mức ERROR nếu nó tạo log noise lớn. Tuy nhiên, cũng không nên loại bỏ cause gốc khi cần điều tra lỗi lập trình hoặc lỗi hệ thống.

## 19. Parse một lần, evaluate nhiều lần

Nếu expression cố định hoặc được quản trị viên cấu hình trước, có thể parse một lần rồi tái sử dụng Expression:

~~~java
Expression expression =
        parser.parseExpression("#order.total >= #minimum");

for (Order order : orders) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00")
    );

    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
}
~~~

Cách này tách lỗi parse khỏi lỗi evaluate theo từng order. Nếu expression sai cú pháp, phát hiện ngay khi nạp rule. Nếu một order có dữ liệu bất thường, lỗi evaluate có thể được gắn với đúng record.

Không nên chia sẻ một EvaluationContext mutable giữa nhiều luồng hoặc nhiều request nếu root object và variables thay đổi. Tạo context riêng cho từng lượt đánh giá hoặc quản lý dữ liệu theo cách an toàn với concurrency.

Nếu expression thay đổi, cần parse lại phiên bản mới và quản lý lifecycle/cache của Expression theo mã rule hoặc phiên bản cấu hình.

## 20. Kiểm thử các tình huống lỗi

Ngoài trường hợp thành công, hãy kiểm thử các lỗi có thể xảy ra ở cả hai giai đoạn.

Các nhóm test hữu ích:

1. Expression sai cú pháp phải phát sinh lỗi parse.
2. Property không tồn tại phải được xử lý theo chính sách.
3. Root object hoặc property trung gian null.
4. Method hoặc function chưa đăng ký.
5. Method được gọi nhưng ném exception.
6. Type reference hoặc bean reference không được phân giải.
7. Đối số sai kiểu hoặc converter không hỗ trợ.
8. Index ngoài phạm vi và key Map không tồn tại.
9. setValue trên property chỉ đọc.
10. Expression bị giới hạn bởi SimpleEvaluationContext.
11. Lỗi không được chuyển thành kết quả cho phép mặc định.
12. Log không chứa dữ liệu nhạy cảm.

Test nên dùng đúng loại EvaluationContext, accessor, resolver và converter của ứng dụng. Một test chỉ gọi parseExpression không kiểm tra được lỗi runtime phụ thuộc dữ liệu.

## 21. Ví dụ hoàn chỉnh: tách parse và evaluate, ghi nhận cause

~~~java
public class RuleEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public boolean evaluate(
            String ruleId,
            String expressionText,
            EvaluationContext context) {

        final Expression expression;

        try {
            expression = parser.parseExpression(expressionText);
        } catch (ParseException ex) {
            // Ghi nhận ruleId, loại lỗi parse và vị trí nếu có.
            throw new IllegalArgumentException(
                    "Invalid rule syntax: " + ruleId,
                    ex
            );
        }

        try {
            Boolean result = expression.getValue(
                    context,
                    Boolean.class
            );

            return Boolean.TRUE.equals(result);
        } catch (EvaluationException ex) {
            // Ghi nhận ruleId, exception và cause gốc.
            throw new IllegalStateException(
                    "Could not evaluate rule: " + ruleId,
                    ex
            );
        }
    }
}
~~~

Ví dụ minh họa việc phân tách lỗi và chuẩn hóa exception ở ranh giới ứng dụng. Chính sách trả về false khi kết quả Boolean null cần được quyết định theo use case; với rule phân quyền hoặc rule quan trọng, không được dùng giá trị mặc định này nếu nó có thể mở quyền ngoài ý muốn.

Trong ứng dụng thực tế, có thể tạo exception domain riêng như RuleParseException và RuleEvaluationException để caller phân biệt lỗi cấu hình với lỗi dữ liệu runtime. Không nên làm mất cause gốc khi bọc exception.

## 22. Ghi nhớ

ParseException hoặc SpelParseException báo lỗi khi parser không thể tạo Expression từ chuỗi. EvaluationException và SpelEvaluationException báo lỗi trong lúc đánh giá, chẳng hạn không tìm thấy property, method, function, type hoặc bean; object null; index không hợp lệ; kiểu không tương thích; conversion thất bại hoặc method ném exception.

Hãy tách parse khỏi evaluate, kiểm tra vị trí và message code nếu có, đọc cause chain và xác nhận đúng root object cùng EvaluationContext. Parse một lần cho rule ổn định, nhưng tạo context phù hợp cho từng lượt đánh giá.

Chọn chính sách theo hậu quả của rule: cấu hình bắt buộc nên fail fast, rule phân quyền nên fail closed và fallback chỉ dùng khi nghiệp vụ đã xác định rõ. Log đủ thông tin để điều tra nhưng không ghi dữ liệu nhạy cảm, đồng thời kiểm thử cả lỗi cú pháp lẫn lỗi runtime.