# Phân biệt SpEL expression do nhà phát triển viết và expression do người dùng nhập

Spring Expression Language (SpEL) là một ngôn ngữ biểu thức có thể đọc property, thực hiện phép toán, gọi method và truy cập các thành phần được cung cấp trong EvaluationContext. Vì vậy, một biểu thức SpEL không đơn thuần là chuỗi văn bản: khi được đánh giá, nó có thể thực thi hành vi trên các đối tượng mà context cho phép truy cập.

Cần phân biệt rõ hai nguồn biểu thức:

- **Expression do nhà phát triển viết** là một phần của mã nguồn hoặc cấu hình được kiểm soát, review và phát hành cùng ứng dụng.
- **Expression do người dùng nhập** đến từ request, giao diện quản trị, file cấu hình do bên ngoài cung cấp hoặc một nguồn không được tin cậy tương đương. Nó phải được xem như chương trình do bên ngoài cung cấp.

Sự khác biệt này quyết định cách chọn EvaluationContext, dữ liệu nào được đưa vào root object, có cho phép gọi method hay tham chiếu bean hay không, và cách xác thực đầu vào. Bài này tập trung vào ranh giới tin cậy và cách thiết kế an toàn khi ứng dụng có nhu cầu dùng SpEL cho cả hai trường hợp.

## 1. Vì sao nguồn gốc expression quan trọng?

Cùng một biểu thức có thể an toàn trong một ngữ cảnh và nguy hiểm trong ngữ cảnh khác. Ví dụ:

~~~text
account.active and account.balance >= 100
~~~

Nếu biểu thức do nhà phát triển viết và được đánh giá trên một DTO nhỏ chỉ chứa dữ liệu cần thiết, hành vi có thể dự đoán được.

Nếu người dùng được tự do gửi expression, họ có thể thay đổi property được đọc, thêm lời gọi method hoặc sử dụng những khả năng khác mà EvaluationContext cung cấp. Khi context có quyền truy cập rộng, biểu thức có thể đọc dữ liệu ngoài mục đích ban đầu hoặc kích hoạt hành vi không mong muốn.

Do đó, trước khi đánh giá SpEL, cần trả lời ba câu hỏi:

1. Ai kiểm soát nội dung expression?
2. Expression được phép truy cập những đối tượng và hành vi nào?
3. Kết quả được dùng cho mục đích gì, đặc biệt có ảnh hưởng đến phân quyền hoặc thay đổi trạng thái hay không?

Không nên đánh giá mức độ an toàn chỉ dựa trên việc chuỗi biểu thức trông đơn giản hoặc chỉ chứa vài phép so sánh.

## 2. Expression do nhà phát triển viết

Expression do nhà phát triển viết thường nằm trong mã nguồn, annotation, XML bean definition hoặc cấu hình được kiểm soát trong quy trình phát hành.

Ví dụ trong mã Java:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int batchSize;
~~~

Ví dụ trong Spring Security:

~~~java
@PreAuthorize("@documentAuthorization.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId);
}
~~~

Trong các ví dụ này, nhà phát triển quyết định expression, kiểu dữ liệu được truy cập và bean hoặc method được gọi. Expression có thể được review như một phần của mã nguồn.

Tuy nhiên, expression do nhà phát triển viết không có nghĩa mọi dữ liệu đưa vào nó đều đáng tin cậy. Giá trị từ HTTP request, tên tài khoản, mã tài liệu hoặc nội dung form vẫn là dữ liệu bên ngoài. Cần truyền chúng như dữ liệu và xác thực theo quy tắc nghiệp vụ.

Một expression được kiểm soát có thể xử lý dữ liệu không đáng tin cậy an toàn hơn nếu dữ liệu được truyền qua biến hoặc root object có cấu trúc rõ ràng, thay vì ghép trực tiếp vào chuỗi expression.

## 3. Expression do người dùng nhập

Expression do người dùng nhập là nội dung mà ứng dụng không kiểm soát trước khi chạy. Ví dụ:

- Người dùng quản trị tự tạo điều kiện lọc dữ liệu.
- Khách hàng nhập quy tắc tính toán trong một màn hình cấu hình.
- Hệ thống nhận expression từ file hoặc dịch vụ bên ngoài.
- Người dùng có thể sửa một trường cấu hình được lưu trong database rồi ứng dụng đánh giá nó bằng SpEL.

Một chuỗi được lưu trong database vẫn là đầu vào không đáng tin cậy nếu người dùng hoặc hệ thống bên ngoài có thể thay đổi nó.

Khi đánh giá expression bên ngoài, người nhập đang cung cấp logic thực thi. Không nên coi chuỗi này như một giá trị dữ liệu bình thường, cũng không nên mặc định rằng việc parse thành công đồng nghĩa với việc biểu thức an toàn.

Nếu nghiệp vụ chỉ cần người dùng chọn một điều kiện, chẳng hạn trạng thái bằng ACTIVE hoặc số dư lớn hơn một ngưỡng, hãy cân nhắc một cấu trúc rule có kiểu rõ ràng thay vì cho phép nhập SpEL tùy ý.

## 4. Rủi ro khi ghép dữ liệu người dùng vào expression

Một lỗi thiết kế phổ biến là ghép trực tiếp đầu vào vào chuỗi SpEL:

~~~java
String spelText =
        "'" + userInput + "' == 'admin'";

Expression expression =
        parser.parseExpression(spelText);

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Đoạn mã này làm dữ liệu người dùng trở thành một phần cú pháp của expression. Nếu đầu vào chứa dấu nháy hoặc toán tử, nó có thể thay đổi cấu trúc biểu thức thay vì chỉ được xem là dữ liệu.

Đây là một dạng expression injection. Việc loại bỏ một vài ký tự bằng replace hoặc regex thường không đủ để bảo đảm an toàn, vì SpEL có nhiều thành phần cú pháp và cách biểu diễn giá trị khác nhau.

Cách phù hợp là giữ expression cố định do nhà phát triển viết và truyền đầu vào qua biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("input", userInput);

Expression expression =
        parser.parseExpression("#input == 'admin'");

Boolean result =
        expression.getValue(context, Boolean.class);
~~~

Trong ví dụ này, userInput là giá trị của biến input. Nội dung đó không được phân tích lại như một đoạn SpEL.

Nguyên tắc quan trọng: **dữ liệu người dùng phải đi vào expression dưới dạng dữ liệu đã được bind, không phải bằng cách nối chuỗi vào mã biểu thức**.

## 5. Parse expression không đồng nghĩa với evaluate expression

SpEL thường có hai giai đoạn:

1. Parser phân tích chuỗi và tạo đối tượng Expression.
2. Ứng dụng gọi getValue() hoặc một thao tác đánh giá khác để thực thi biểu thức trong EvaluationContext.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("age >= 18");

Boolean eligible =
        expression.getValue(context, source, Boolean.class);
~~~

parseExpression() xử lý cú pháp và có thể báo lỗi nếu expression không hợp lệ. getValue() đánh giá biểu thức trên dữ liệu và khả năng truy cập do context cung cấp.

Việc parse thành công không chứng minh expression an toàn. Một expression hợp lệ vẫn có thể gọi method, đọc property nhạy cảm hoặc thực hiện hành vi không phù hợp nếu context cho phép.

Cần kiểm soát cả nội dung expression và môi trường đánh giá. Không nên dùng kết quả parse thành công như một cơ chế xác thực bảo mật.

## 6. EvaluationContext quyết định quyền của expression

EvaluationContext cung cấp môi trường mà SpEL dùng khi đánh giá. Các thành phần quan trọng có thể gồm:

- Root object và các biến.
- PropertyAccessor để đọc hoặc ghi property.
- MethodResolver để tìm method có thể gọi.
- BeanResolver để tham chiếu bean bằng cú pháp @beanName.
- TypeLocator để xử lý type reference T(...).
- TypeConverter để chuyển đổi giá trị.
- Function được đăng ký trong context.

StandardEvaluationContext có nhiều khả năng và thường phù hợp với expression do nhà phát triển kiểm soát. Nếu đưa một StandardEvaluationContext có quyền rộng cho expression do người dùng nhập, người dùng có thể tiếp cận những khả năng mà ứng dụng không định cung cấp.

Ví dụ, các cú pháp sau cho thấy những nhóm chức năng khác nhau:

~~~text
name
#minimumAge
#normalize(name)
@pricingService.defaultCurrency
T(java.lang.Math).max(10, 20)
~~~

Chúng lần lượt minh họa property, biến, function, bean reference và type reference. Không phải ứng dụng nào cũng cần mở tất cả các khả năng này cho một expression.

Hãy cấu hình context theo đúng mục đích. Không dùng một context có đầy đủ quyền chỉ vì nó tiện cho cả biểu thức nội bộ và biểu thức bên ngoài.

## 7. Dùng SimpleEvaluationContext cho trường hợp giới hạn

SimpleEvaluationContext được thiết kế để cung cấp một tập tính năng SpEL giới hạn hơn StandardEvaluationContext. Ứng dụng phải chọn rõ cơ chế property access và khả năng method invocation phù hợp.

Ví dụ read-only data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression =
        parser.parseExpression("active and age >= 18");

Boolean result = expression.getValue(
        context,
        accountView,
        Boolean.class
);
~~~

Cấu hình này phù hợp khi expression cần đọc property từ một đối tượng dữ liệu. Nó không cung cấp đầy đủ các khả năng như type references, constructor invocation và bean references của StandardEvaluationContext. Method invocation cũng không được bật mặc định trong cấu hình read-only data binding này.

SimpleEvaluationContext có thể giảm bề mặt truy cập, nhưng không phải một sandbox tuyệt đối cho mọi loại expression. Getter vẫn có thể thực thi mã Java, object lồng nhau vẫn có thể chứa dữ liệu nhạy cảm, và một collection lớn vẫn có thể làm phép duyệt tốn tài nguyên.

Khi dùng expression do người dùng nhập:

- Chỉ cung cấp root object nhỏ, chứa đúng các property được phép.
- Ưu tiên read-only property access.
- Không thêm bean resolver hoặc type access nếu nghiệp vụ không cần.
- Không bật method invocation một cách tùy tiện.
- Kiểm tra giới hạn của builder và accessor đang dùng trong phiên bản Spring cụ thể.

Nếu cần một tập phép toán hẹp hơn nữa, hãy thiết kế một DSL hoặc rule model riêng thay vì mở rộng SpEL không giới hạn.

## 8. Thiết kế root object theo nguyên tắc least privilege

Root object là điểm bắt đầu để expression truy cập dữ liệu. Đưa toàn bộ entity hoặc service lớn vào context có thể làm lộ nhiều property và hành vi hơn mức cần thiết.

Không nên cung cấp trực tiếp những đối tượng có thể dẫn tới:

- Toàn bộ ApplicationContext hoặc BeanFactory.
- Entity có nhiều quan hệ và trường nội bộ.
- Request/session chứa thông tin nhạy cảm.
- Service có method thay đổi dữ liệu hoặc gọi hệ thống bên ngoài.
- Đối tượng chứa token, credential hoặc thông tin bí mật.

Thay vào đó, tạo một DTO chỉ chứa các trường cần dùng:

~~~java
public class AccountRuleView {
    private final String status;
    private final int age;
    private final BigDecimal balance;

    public AccountRuleView(
            String status,
            int age,
            BigDecimal balance) {
        this.status = status;
        this.age = age;
        this.balance = balance;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}
~~~

Đánh giá expression trên DTO:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "status == 'ACTIVE' and age >= 18 and balance > 0"
);

Boolean allowed = expression.getValue(
        context,
        accountRuleView,
        Boolean.class
);
~~~

DTO này chỉ phơi bày status, age và balance. Expression không cần biết về repository, service, entity graph hoặc các trường khác của tài khoản.

Least privilege áp dụng cho cả root object, collection được trả về và các accessor được đăng ký.

## 9. Tách điều kiện người dùng chọn khỏi expression code

Nếu người dùng chỉ cần tạo một rule đơn giản, có thể cung cấp form hoặc cấu trúc dữ liệu có kiểu:

~~~java
public enum RuleField {
    STATUS,
    AGE,
    BALANCE
}

public enum RuleOperator {
    EQUALS,
    GREATER_THAN,
    LESS_THAN
}

public class UserRule {
    private RuleField field;
    private RuleOperator operator;
    private String value;
}
~~~

Ứng dụng xác thực từng trường và toán tử trong allowlist, sau đó tự thực hiện so sánh trên dữ liệu đã chuẩn hóa.

Ví dụ, chỉ cho phép:

- STATUS với EQUALS.
- AGE với GREATER_THAN hoặc LESS_THAN.
- BALANCE với GREATER_THAN hoặc LESS_THAN.

Cách này giúp người dùng chọn điều kiện mà không được cung cấp cú pháp thực thi tùy ý. Nó cũng giúp kiểm tra kiểu dữ liệu, giới hạn số rule, lưu version và hiển thị lại cấu hình một cách ổn định.

Nếu thật sự cần expression language, có thể xây dựng một DSL nhỏ chỉ hỗ trợ các property và toán tử nghiệp vụ cần thiết. Đừng giả định rằng việc lọc một vài chuỗi bằng regex sẽ biến toàn bộ ngôn ngữ SpEL thành DSL an toàn.

## 10. Xác thực expression do người dùng nhập

Nếu ứng dụng bắt buộc phải nhận SpEL từ bên ngoài, cần xác định rõ grammar và khả năng được phép trước khi đưa vào production.

Một quy trình kiểm soát có thể gồm:

1. Giới hạn độ dài expression và kích thước dữ liệu đầu vào.
2. Chỉ chấp nhận những property nằm trong allowlist nghiệp vụ.
3. Chỉ cho phép các toán tử và cấu trúc cần thiết.
4. Dùng EvaluationContext với quyền truy cập tối thiểu.
5. Không cung cấp bean reference, type reference hoặc constructor invocation nếu không có lý do rõ ràng.
6. Không bật method invocation nếu biểu thức chỉ cần đọc property và tính toán.
7. Xác thực kiểu kết quả theo hợp đồng, ví dụ kết quả rule phải là Boolean.
8. Kiểm thử với đầu vào sai cú pháp, null, dữ liệu biên và collection lớn.
9. Giới hạn số expression được lưu, parse và đánh giá theo từng người dùng hoặc tenant.

Một parser có thể giúp phát hiện lỗi cú pháp, nhưng parse không thay thế kiểm tra chính sách. Nếu cần kiểm tra cấu trúc expression, hãy dùng một grammar hoặc mô hình rule do ứng dụng kiểm soát; tránh phụ thuộc vào các lớp AST nội bộ không được hỗ trợ như API ổn định.

## 11. Nguy cơ từ method invocation và getter

Truy cập property trong Java thường đi qua getter. Getter là mã Java và về lý thuyết có thể làm nhiều việc hơn việc trả về một field.

Ví dụ getter không phù hợp cho biểu thức:

~~~java
public BigDecimal getBalance() {
    auditService.writeAccessLog();
    return accountRepository.calculateCurrentBalance(id);
}
~~~

Nếu expression được đánh giá nhiều lần, getter có thể gây truy vấn hoặc tác dụng phụ lặp lại. Đối với expression do người dùng nhập, việc để người dùng chọn property có getter phức tạp còn làm tăng khó khăn khi dự đoán chi phí thực thi.

Tương tự, method invocation có thể kích hoạt hành vi thay đổi trạng thái hoặc gọi dịch vụ bên ngoài.

Các nguyên tắc:

- Getter trên DTO dành cho rule nên đơn giản và không có tác dụng phụ.
- Không đưa service có thao tác ghi vào root object.
- Chỉ bật method invocation khi thật sự cần và giới hạn method có thể gọi.
- Không coi tiền tố # hoặc việc dùng SimpleEvaluationContext là bảo đảm mọi method đều an toàn.

## 12. Bảo vệ dữ liệu và quyền truy cập

Một expression có thể đọc mọi dữ liệu mà root object và accessor làm lộ. Nếu dữ liệu nguồn chứa email, số điện thoại, token, thông tin tài chính hoặc dữ liệu của tenant khác, expression có thể tạo kết quả chứa những thông tin đó.

Hãy chuẩn bị dữ liệu theo đúng phạm vi người dùng được phép xem trước khi đánh giá expression. Không dựa vào expression để thay thế kiểm tra quyền truy cập dữ liệu.

Ví dụ, trước khi đánh giá rule cho một khách hàng:

1. Xác thực người gọi.
2. Kiểm tra tenant và quyền truy cập đối tượng.
3. Tải đúng bản ghi mà người gọi được phép xem.
4. Tạo DTO chỉ chứa trường cần cho rule.
5. Đánh giá expression trong context giới hạn.
6. Kiểm tra kiểu và ý nghĩa của kết quả.

Expression trả về true không tự chứng minh người gọi có quyền truy cập bản ghi. Quyết định phân quyền vẫn phải nằm trong logic bảo mật được kiểm soát của ứng dụng.

## 13. Tài nguyên, thời gian thực thi và lưu cache

Expression do người dùng nhập có thể gây tốn tài nguyên ngay cả khi không gọi bean hay method nguy hiểm. Ví dụ, expression có thể duyệt collection lớn, thực hiện nhiều phép chiếu/lọc lồng nhau hoặc dùng toán tử regex trên chuỗi dài.

Nên kiểm soát:

- Độ dài expression.
- Kích thước chuỗi và collection được đưa vào context.
- Số lượng rule được phép lưu cho một người dùng.
- Tần suất đánh giá và mức đồng thời.
- Những getter và phép toán được phép sử dụng.
- Số expression khác nhau được giữ trong cache.

Không nên giả định SpEL tự cung cấp một giới hạn thời gian thực thi an toàn cho mọi biểu thức. Nếu một method có thể chạy lâu, việc đặt timeout ở tầng gọi không nhất thiết dừng được mã đang chạy bên trong. Cách tốt hơn là không cho expression không đáng tin cậy gọi các thao tác có thời gian thực thi không kiểm soát.

Nếu cache Expression, dùng cache có giới hạn dung lượng và chính sách loại bỏ phù hợp. Không dùng cache không giới hạn với key là chuỗi do người dùng tùy ý gửi lên, vì số lượng expression khác nhau có thể tăng liên tục.

## 14. Xử lý lỗi và ghi log

Expression bên ngoài có thể sai cú pháp, truy cập property không tồn tại, tạo kết quả không đúng kiểu hoặc phát sinh lỗi khi đánh giá.

Cần phân biệt:

- Parse exception: cú pháp expression không hợp lệ.
- Evaluation exception: lỗi trong lúc đánh giá property, method hoặc phép toán.
- Conversion error: kết quả không chuyển đổi được sang kiểu đích.
- Validation error: expression hợp lệ về cú pháp nhưng vi phạm chính sách của ứng dụng.

Không trả nguyên stack trace hoặc chi tiết nội bộ cho người dùng cuối. Có thể trả thông báo validation ngắn, đồng thời ghi mã lỗi tương quan ở phía server.

Khi ghi log, tránh lưu expression nếu nó có thể chứa dữ liệu cá nhân, bí mật hoặc thông tin do người dùng nhập nhạy cảm. Nếu cần điều tra, ghi định danh rule, người tạo, thời điểm, version và loại lỗi theo chính sách dữ liệu của ứng dụng.

## 15. Ví dụ: expression cố định, dữ liệu thay đổi

Ví dụ này minh họa cách nhà phát triển giữ expression cố định và truyền dữ liệu người dùng qua biến.

~~~java
public class AccountView {
    private final String status;
    private final int age;

    public AccountView(String status, int age) {
        this.status = status;
        this.age = age;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }
}

String requestedStatus = request.getParameter("status");

AccountView source = new AccountView(
        account.getStatus(),
        account.getAge()
);

StandardEvaluationContext context =
        new StandardEvaluationContext(source);

context.setVariable("requestedStatus", requestedStatus);

Expression expression = parser.parseExpression(
        "status == #requestedStatus and age >= 18"
);

Boolean matches = expression.getValue(
        context,
        Boolean.class
);
~~~

Expression là hằng số do nhà phát triển viết. requestedStatus là dữ liệu đến từ request nhưng được bind vào biến, nên nội dung đó không trở thành cú pháp SpEL.

Trong ứng dụng thực tế, vẫn cần xác thực requestedStatus theo tập trạng thái hợp lệ và kiểm tra quyền truy cập account trước khi tạo source object.

## 16. Ví dụ: đánh giá rule bên ngoài bằng context giới hạn

Nếu nghiệp vụ thực sự yêu cầu người dùng nhập rule, hãy cung cấp dữ liệu nhỏ và dùng context chỉ đọc:

~~~java
AccountRuleView source = new AccountRuleView(
        "ACTIVE",
        25,
        new BigDecimal("1500.00")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

String userExpression =
        "status == 'ACTIVE' and age >= 18 and balance > 0";

Expression expression =
        parser.parseExpression(userExpression);

Object result = expression.getValue(context, source);

if (!(result instanceof Boolean)) {
    throw new IllegalArgumentException(
            "Rule expression must return a Boolean"
    );
}

boolean matches = (Boolean) result;
~~~

Ví dụ dùng một expression đơn giản chỉ đọc property và thực hiện so sánh. Trong ứng dụng thật, cần thêm chính sách allowlist property/toán tử, giới hạn kích thước, xác thực quyền và kiểm thử các biểu thức được chấp nhận.

Không mở rộng ví dụ này thành một endpoint nhận mọi SpEL mà không có giới hạn. SimpleEvaluationContext giúp giảm tính năng có sẵn, nhưng chính sách ứng dụng vẫn phải xác định expression nào được chấp nhận.

## 17. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nối input vào chuỗi SpEL | Dữ liệu có thể thay đổi cú pháp expression. | Dùng biến hoặc root object để truyền dữ liệu. |
| Cho rằng parse thành công nghĩa là an toàn | Parse chỉ xác nhận cú pháp có thể được phân tích. | Kiểm soát quyền của context và chính sách expression. |
| Dùng StandardEvaluationContext rộng cho expression bên ngoài | Context có thể cung cấp nhiều khả năng truy cập. | Dùng context giới hạn và root object tối thiểu. |
| Expose toàn bộ entity hoặc service | Expression có thể nhìn thấy nhiều dữ liệu và hành vi không cần thiết. | Dùng DTO/read model với allowlist property. |
| Bật method invocation không giới hạn | Method có thể thay đổi trạng thái hoặc gọi hệ thống bên ngoài. | Tắt method invocation nếu không cần; giới hạn resolver nếu cần dùng. |
| Dựa vào regex để lọc cú pháp SpEL | Grammar có nhiều cách biểu diễn và lồng nhau. | Dùng DSL/rule model có kiểu hoặc kiểm soát grammar rõ ràng. |
| Dùng expression làm quyết định phân quyền duy nhất | Kết quả expression không thay thế kiểm tra quyền trên dữ liệu. | Xác thực người gọi và phạm vi dữ liệu trước khi đánh giá. |
| Không giới hạn collection hoặc expression size | Biểu thức có thể tiêu tốn CPU và bộ nhớ. | Giới hạn độ dài, dữ liệu, tần suất và số rule. |
| Cache mọi expression không giới hạn | Người dùng có thể tạo số lượng key lớn. | Dùng cache bounded hoặc không cache expression bên ngoài. |
| Trả stack trace cho người dùng | Lộ tên lớp, cấu trúc và thông tin nội bộ. | Trả lỗi validation ngắn và ghi log an toàn phía server. |

## 18. Nguyên tắc thực hành

1. Phân loại expression theo nguồn gốc và mức độ tin cậy trước khi đánh giá.
2. Giữ expression do nhà phát triển viết trong mã nguồn hoặc cấu hình được kiểm soát.
3. Không ghép dữ liệu người dùng trực tiếp vào chuỗi SpEL.
4. Truyền input qua biến hoặc DTO có kiểu rõ ràng.
5. Chỉ cung cấp root object và property cần thiết.
6. Dùng SimpleEvaluationContext với read-only data binding khi bài toán chỉ cần đọc property.
7. Không cấp bean reference, type access, constructor invocation hoặc method invocation nếu không cần.
8. Dùng DSL/rule model có allowlist khi người dùng cần tự tạo điều kiện.
9. Xác thực quyền truy cập dữ liệu độc lập với kết quả expression.
10. Giới hạn kích thước, số lượng, tần suất và tài nguyên khi xử lý expression bên ngoài.
11. Xử lý lỗi parse, evaluate, conversion và validation riêng biệt.
12. Không xem parse thành công hoặc read-only context là sandbox bảo đảm an toàn tuyệt đối.

## 19. Ghi nhớ

- Expression do nhà phát triển viết được kiểm soát trong mã nguồn hoặc cấu hình; expression do người dùng nhập phải được xem là chương trình không đáng tin cậy.
- SpEL có thể đọc property và thực thi method tùy khả năng EvaluationContext cung cấp.
- Nối input vào expression có thể gây expression injection.
- Giữ expression cố định và truyền dữ liệu người dùng qua biến hoặc root object.
- StandardEvaluationContext có nhiều khả năng; không dùng context quyền rộng cho expression bên ngoài.
- SimpleEvaluationContext giới hạn tính năng và phù hợp với một số trường hợp read-only data binding, nhưng không phải sandbox tuyệt đối.
- Root object nhỏ và DTO chỉ đọc giúp giới hạn dữ liệu mà expression có thể thấy.
- Parse thành công không chứng minh expression an toàn.
- Dùng DSL/rule model có kiểu khi người dùng chỉ cần chọn điều kiện nghiệp vụ.
- Kiểm soát method, getter, collection size, expression size, cache và tần suất đánh giá.
- Quyết định phân quyền và quyền truy cập dữ liệu phải được kiểm soát độc lập với expression.
