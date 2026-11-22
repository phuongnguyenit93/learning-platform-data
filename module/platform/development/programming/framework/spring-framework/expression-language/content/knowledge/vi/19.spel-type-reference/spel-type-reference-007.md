# TypeLocator và package import

Trong Spring Expression Language (SpEL), **TypeLocator** là thành phần chịu trách nhiệm phân giải tên kiểu được viết trong type reference **T(...)** thành một lớp Java có thể sử dụng khi đánh giá biểu thức. Nó cho phép biểu thức tham chiếu đến static method, static field hoặc enum constant của một kiểu mà không cần truyền một instance của kiểu đó làm root object.

**StandardTypeLocator** là implementation mặc định thường dùng cùng StandardEvaluationContext. Nó hỗ trợ tìm kiểu theo tên đầy đủ và theo tên ngắn trong những package đã được import. Package import ở đây là cấu hình của TypeLocator dành cho SpEL; nó không phải câu lệnh import trong mã nguồn Java.

## Type reference và vai trò của TypeLocator

Cú pháp type reference:

~~~text
T(fully.qualified.TypeName)
~~~

Ví dụ, gọi static method của Math:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer maximum =
        expression.getValue(context, Integer.class);
~~~

Khi đánh giá **T(java.lang.Math)**, SpEL yêu cầu TypeLocator tìm kiểu có tên java.lang.Math. Sau khi có Class tương ứng, biểu thức có thể gọi static method max.

Nếu tên kiểu không thể được phân giải, lỗi xuất hiện trong giai đoạn evaluation. Chuỗi biểu thức vẫn có thể parse thành công vì việc tìm lớp Java được thực hiện khi SpEL đánh giá type reference.

## StandardTypeLocator

**StandardTypeLocator** là TypeLocator do Spring cung cấp. Nó tìm lớp bằng class loader và hỗ trợ danh sách package import để có thể dùng tên kiểu ngắn.

StandardEvaluationContext mặc định có một StandardTypeLocator. Vì vậy, với những biểu thức thông thường, không cần tự tạo TypeLocator:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).PI");

Double pi =
        expression.getValue(context, Double.class);
~~~

Tên đầy đủ **java.lang.Math** giúp xác định chính xác lớp cần tìm. StandardTypeLocator mặc định cũng import package **java.lang**, vì vậy một số kiểu trong package này có thể được tham chiếu bằng tên ngắn:

~~~java
Expression expression =
        parser.parseExpression("T(Math).max(10, 25)");

Integer maximum =
        expression.getValue(context, Integer.class);
~~~

Trong ví dụ, **T(Math)** được phân giải thành java.lang.Math nhờ package java.lang đã được import mặc định.

Dù tên ngắn tiện lợi, tên đầy đủ thường dễ đọc và ít gây nhầm lẫn hơn khi biểu thức được chia sẻ giữa nhiều module hoặc được lưu trong cấu hình.

## Đăng ký package import

Nếu kiểu nằm ngoài các package đã import, có thể đăng ký package với StandardTypeLocator bằng **registerImport(...)**.

Ví dụ, dùng LocalDate thuộc package java.time:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("java.time");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(LocalDate).of(2026, 12, 31)");

LocalDate deadline =
        expression.getValue(context, LocalDate.class);
~~~

Sau khi đăng ký **java.time**, SpEL có thể phân giải tên ngắn **LocalDate** thành java.time.LocalDate. Biểu thức gọi static method **of(...)** để tạo giá trị ngày.

Nếu không đăng ký package, có thể viết tên đầy đủ:

~~~java
Expression expression =
        parser.parseExpression(
                "T(java.time.LocalDate).of(2026, 12, 31)");
~~~

Hai cách đều tham chiếu cùng một kiểu. Dùng tên đầy đủ không cần thêm package import, miễn là class loader có thể tìm thấy lớp đó.

## Package import chỉ áp dụng cho việc phân giải kiểu trong SpEL

Cần phân biệt package import của TypeLocator với import trong Java:

- **Java import** được compiler dùng để rút gọn tên kiểu trong file nguồn.
- **TypeLocator package import** được SpEL dùng lúc runtime để phân giải tên kiểu trong biểu thức T(...).
- Cấu hình import của TypeLocator không làm thay đổi classpath, không nạp thêm dependency và không tự đăng ký Spring bean.

Ví dụ, dòng Java **import java.time.LocalDate;** trong một file source không tự động khiến mọi SpEL expression có thể dùng **T(LocalDate)**. Muốn dùng tên ngắn trong SpEL, package tương ứng phải nằm trong danh sách import của TypeLocator đang được EvaluationContext sử dụng.

Ngược lại, gọi **registerImport("java.time")** không tạo ra một Java import trong source code. Nó chỉ ảnh hưởng đến cách SpEL phân giải tên kiểu trong các biểu thức được đánh giá bằng context đó.

## Cấu hình TypeLocator trên EvaluationContext

Có thể tạo StandardTypeLocator riêng rồi gắn vào StandardEvaluationContext:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("java.time");
typeLocator.registerImport("java.util");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Từ thời điểm này, các biểu thức được đánh giá bằng context có thể dùng tên ngắn cho những kiểu thuộc java.time và java.util:

~~~java
Expression dateExpression =
        parser.parseExpression("T(LocalDate).now()");

Expression localeExpression =
        parser.parseExpression("T(Locale).US");

LocalDate today =
        dateExpression.getValue(context, LocalDate.class);

Locale locale =
        localeExpression.getValue(context, Locale.class);
~~~

Trong ví dụ:

- **T(LocalDate)** được phân giải trong java.time.
- **T(Locale)** được phân giải trong java.util.
- **now()** và **US** lần lượt là static method và static field/enum constant được truy cập qua kiểu.

Một context có thể dùng một TypeLocator với nhiều package import. Nên đăng ký các package thực sự cần thiết để biểu thức dễ hiểu và giảm khả năng tên ngắn trở nên mơ hồ.

## Sử dụng tên đầy đủ và tránh xung đột tên kiểu

Hai package khác nhau có thể chứa những lớp cùng tên đơn giản. Nếu import cả hai package, một type reference dùng tên ngắn có thể trở nên mơ hồ hoặc được phân giải không như người viết dự định.

Ví dụ, nhiều thư viện có thể cung cấp kiểu **Date**, **Path** hoặc **Config**. Khi có khả năng trùng tên, hãy dùng tên đầy đủ:

~~~java
Expression expression =
        parser.parseExpression(
                "T(java.time.LocalDate).of(2026, 11, 12)");
~~~

Tên đầy đủ cho biết chính xác kiểu mà biểu thức yêu cầu. Đây là lựa chọn tốt trong cấu hình quan trọng, trong biểu thức được lưu lâu dài hoặc khi nhiều module cùng đóng góp package import.

Không nên thêm hàng loạt package chỉ để rút ngắn biểu thức. Danh sách import càng rộng, khả năng xung đột tên và khó hiểu càng tăng.

## Chọn ClassLoader cho StandardTypeLocator

Việc phân giải kiểu cuối cùng phụ thuộc vào **ClassLoader** có thể nạp lớp. StandardTypeLocator có constructor cho phép truyền ClassLoader cụ thể:

~~~java
ClassLoader applicationClassLoader =
        Thread.currentThread().getContextClassLoader();

StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);

typeLocator.registerImport("java.time");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Cách cấu hình này hữu ích trong ứng dụng có nhiều class loader, plugin, container hoặc môi trường triển khai mà class loader mặc định không nhìn thấy mọi lớp cần thiết.

Nếu TypeLocator không tìm thấy một kiểu, hãy kiểm tra:

- Tên kiểu trong T(...) có chính xác không.
- Package import đã đăng ký đúng chưa nếu đang dùng tên ngắn.
- Lớp có thực sự nằm trên runtime classpath không.
- ClassLoader được truyền vào có quyền nạp lớp đó không.
- Lớp có bị tách sang module hoặc class loader riêng không.

Package import chỉ giúp tìm lớp theo tên ngắn; nó không thể làm cho một dependency chưa có trong runtime classpath trở nên khả dụng.

## Dùng TypeLocator tùy chỉnh

Trong trường hợp cần kiểm soát chặt kiểu nào được phép tham chiếu, ứng dụng có thể cung cấp implementation riêng của **TypeLocator** và gắn vào EvaluationContext.

Interface TypeLocator định nghĩa thao tác phân giải tên kiểu thành Class:

~~~java
Class<?> findType(String typeName) throws EvaluationException;
~~~

Một TypeLocator tùy chỉnh có thể chỉ cho phép một tập kiểu cụ thể, sau đó từ chối những tên khác. Ví dụ, ứng dụng có thể chỉ expose một vài lớp tiện ích an toàn cho biểu thức cấu hình.

Mã minh họa:

~~~java
public class AllowListTypeLocator implements TypeLocator {
    private final Map<String, Class<?>> allowedTypes;

    public AllowListTypeLocator(Map<String, Class<?>> allowedTypes) {
        this.allowedTypes = Map.copyOf(allowedTypes);
    }

    @Override
    public Class<?> findType(String typeName) {
        Class<?> type = allowedTypes.get(typeName);

        if (type == null) {
            throw new SpelEvaluationException(
                    SpelMessage.TYPE_NOT_FOUND, typeName);
        }

        return type;
    }
}
~~~

Trong ứng dụng thực tế, cần hoàn thiện imports, kiểu exception và quy ước tên theo phiên bản Spring đang dùng. Ví dụ minh họa ý tưởng: chỉ những tên đã đăng ký trong allowlist mới được phân giải.

Có thể gắn locator này vào context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(allowListTypeLocator);
~~~

Khi dùng TypeLocator tùy chỉnh, cần kiểm soát cả tên đầy đủ lẫn tên ngắn theo đúng chính sách của ứng dụng. Nếu chỉ kiểm tra một dạng tên mà bỏ qua dạng tương đương khác, allowlist có thể không đạt mục tiêu.

## Package import không phải cơ chế bảo mật

Đăng ký một package import không đồng nghĩa giới hạn biểu thức chỉ được phép truy cập các lớp trong package đó. TypeLocator vẫn có thể phân giải tên đầy đủ của một lớp nếu class loader tìm thấy nó, tùy implementation và chính sách đang dùng.

Vì vậy, không nên xem **registerImport(...)** là allowlist hoặc sandbox. Nó chủ yếu là tiện ích để rút gọn tên kiểu.

Nếu biểu thức đến từ người dùng hoặc một nguồn không đáng tin cậy, cần cân nhắc kỹ việc cho phép **T(...)**. Type reference có thể dẫn đến static method hoặc static field của những lớp được phân giải. Một số static method có thể tạo tài nguyên, đọc trạng thái hệ thống hoặc thực hiện tác động phụ khác.

Các hướng kiểm soát phù hợp gồm:

- Chỉ dùng StandardEvaluationContext với biểu thức do ứng dụng kiểm soát.
- Nếu cần đánh giá biểu thức bên ngoài, cân nhắc TypeLocator theo allowlist.
- Chỉ expose những kiểu và method thật sự cần thiết.
- Giới hạn root object, property accessor, method resolver và biến trong context.
- Tránh expose các API có thể truy cập filesystem, mạng, tiến trình hoặc tài nguyên nhạy cảm.
- Xác thực nguồn biểu thức và xử lý lỗi parse/evaluation rõ ràng.

Nếu use case chỉ cần đọc property của DTO, SimpleEvaluationContext có bề mặt tính năng giới hạn hơn và không hỗ trợ type reference. Khi đó, không cần mở StandardEvaluationContext chỉ để thuận tiện cho một cú pháp T(...) không thực sự cần thiết.

## Xử lý lỗi phân giải kiểu

Lỗi có thể xuất hiện ở hai giai đoạn khác nhau:

- **ParseException:** chuỗi SpEL sai cú pháp, ví dụ viết sai cấu trúc T(...).
- **EvaluationException:** biểu thức parse được nhưng TypeLocator không tìm thấy kiểu, method hoặc field không tồn tại, hoặc thao tác không thể thực hiện trong context hiện tại.

Ví dụ:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("T(LocalDate).now()");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    LocalDate today =
            expression.getValue(context, LocalDate.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or evaluate the requested type", ex);
}
~~~

Nếu biểu thức dùng tên ngắn, hãy kiểm tra package import. Nếu dùng tên đầy đủ, kiểm tra classpath và ClassLoader. Nếu lớp đã phân giải được nhưng static method không gọi được, hãy kiểm tra chữ ký method và kiểu của các đối số.

Không nên bắt mọi lỗi rồi trả về một giá trị mặc định mà không ghi nhận nguyên nhân. Một cấu hình type reference sai có thể làm ứng dụng sử dụng nhầm quy tắc hoặc dữ liệu.

## Khi nào nên đăng ký package import?

Package import hữu ích khi một nhóm biểu thức thường xuyên tham chiếu các kiểu trong cùng package, chẳng hạn:

- **java.time** cho LocalDate, LocalDateTime và các kiểu ngày giờ.
- **java.util** cho Locale, UUID và những kiểu tiện ích.
- Package tiện ích nội bộ chứa các lớp có static method thuần, có hợp đồng rõ ràng.

Nếu chỉ có một hoặc hai type reference, dùng tên đầy đủ thường đơn giản hơn việc thay đổi context. Nếu biểu thức cần ổn định qua nhiều module, tên đầy đủ cũng giúp tránh phụ thuộc vào danh sách package import được cấu hình ở nơi khác.

## Kết luận

**TypeLocator** phân giải tên kiểu trong SpEL type reference **T(...)**. **StandardTypeLocator** hỗ trợ tên đầy đủ, package import và ClassLoader; package **java.lang** được import mặc định. Dùng **registerImport(...)** để cho phép tên ngắn từ package khác, hoặc truyền ClassLoader phù hợp khi ứng dụng có môi trường nạp lớp đặc biệt.

Package import chỉ là cơ chế tiện lợi cho phân giải tên, không phải Java import và cũng không phải allowlist bảo mật. Khi biểu thức đến từ nguồn bên ngoài, hãy kiểm soát type resolution bằng TypeLocator phù hợp và chỉ expose các kiểu cần thiết.
