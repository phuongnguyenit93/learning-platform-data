# ConstructorResolver và việc chọn constructor

Trong Spring Expression Language (SpEL), biểu thức có thể tạo một object Java bằng cú pháp **new TypeName(arguments)**. Khi đánh giá biểu thức này, SpEL phải tìm constructor phù hợp với kiểu được yêu cầu và các đối số đã được tính. Thành phần chịu trách nhiệm tìm constructor là **ConstructorResolver**.

Trong **StandardEvaluationContext**, SpEL mặc định sử dụng **ReflectiveConstructorResolver** để tìm constructor có thể gọi bằng reflection. Việc chọn constructor phụ thuộc vào số lượng đối số, kiểu dữ liệu thực tế và khả năng chuyển đổi kiểu của EvaluationContext. Vì vậy, khi một lớp có nhiều constructor overload, kiểu của các đối số có vai trò quan trọng.

## Cú pháp tạo object trong SpEL

Cú pháp tổng quát:

~~~text
new fully.qualified.TypeName(argument1, argument2, ...)
~~~

Tên kiểu được viết sau từ khóa **new**. Các đối số là những biểu thức SpEL có thể được đánh giá thành giá trị truyền vào constructor.

Ví dụ, tạo một BigDecimal từ chuỗi:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("new java.math.BigDecimal('19.95')");

BigDecimal price =
        expression.getValue(context, BigDecimal.class);
~~~

Biểu thức yêu cầu tạo một instance BigDecimal bằng constructor nhận String. Kết quả là một object BigDecimal có giá trị 19.95.

Với kiểu thuộc package **java.lang**, SpEL có thể dùng tên ngắn vì package này được import mặc định trong cơ chế phân giải kiểu:

~~~java
String message =
        parser.parseExpression("new String('Hello')")
                .getValue(context, String.class);
~~~

Với kiểu ở package khác, nên dùng tên đầy đủ để biểu thức xác định rõ lớp cần tạo. Constructor invocation không yêu cầu bọc tên lớp bằng **T(...)**; cú pháp **T(...)** dành cho type reference.

## Vai trò của ConstructorResolver

**ConstructorResolver** là một extension point của SpEL dùng để tìm constructor phù hợp cho một type và danh sách đối số. Resolver nhận thông tin về kiểu cần tạo cùng kiểu của các đối số, sau đó trả về cơ chế thực thi constructor nếu tìm được ứng viên phù hợp.

Trong cấu hình mặc định, **StandardEvaluationContext** có **ReflectiveConstructorResolver**. Resolver này sử dụng reflection để tìm constructor có thể truy cập trên lớp đích và xác định constructor phù hợp với các đối số.

Có thể hình dung luồng xử lý như sau:

1. Parser phân tích chuỗi và tạo một Expression.
2. Khi Expression được đánh giá, SpEL phân giải tên kiểu sau từ khóa new thành Class.
3. Các đối số của constructor được đánh giá trong EvaluationContext.
4. ConstructorResolver tìm constructor phù hợp với số lượng và kiểu đối số.
5. SpEL áp dụng chuyển đổi kiểu nếu context hỗ trợ và cần thiết.
6. Constructor được thực thi và object mới được trả về.

Parser chỉ kiểm tra cấu trúc cú pháp. Việc tìm lớp, chọn constructor và thực thi xảy ra trong giai đoạn evaluation.

## ReflectiveConstructorResolver mặc định

Với StandardEvaluationContext, ứng dụng thường không cần tự đăng ký ConstructorResolver cho trường hợp thông thường:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("new java.util.ArrayList()");

List<?> result =
        expression.getValue(context, List.class);
~~~

SpEL phân giải java.util.ArrayList, tìm constructor không tham số phù hợp rồi tạo instance mới. Object trả về là một ArrayList mutable theo đặc tính của lớp Java đó.

Nếu constructor cần đối số, biểu thức có thể truyền literal hoặc giá trị lấy từ context:

~~~java
context.setVariable("initialCapacity", 20);

Expression expression =
        parser.parseExpression(
                "new java.util.ArrayList(#initialCapacity)");

List<?> result =
        expression.getValue(context, List.class);
~~~

Biến **#initialCapacity** được đánh giá trước và truyền vào constructor tương ứng. Kiểu runtime của biến là Integer, phù hợp với constructor nhận capacity kiểu int sau cơ chế chuyển đổi/unboxing tương ứng.

## Chọn constructor khi có overload

Một lớp Java có thể khai báo nhiều constructor cùng tên lớp nhưng khác số lượng hoặc kiểu tham số:

~~~java
public class Coordinate {
    private final double x;
    private final double y;

    public Coordinate(double x, double y) {
        this.x = x;
        this.y = y;
    }

    public Coordinate(String pair) {
        String[] parts = pair.split(",");
        this.x = Double.parseDouble(parts[0]);
        this.y = Double.parseDouble(parts[1]);
    }

    public double getX() {
        return x;
    }

    public double getY() {
        return y;
    }
}
~~~

Có thể gọi từng overload bằng biểu thức phù hợp:

~~~java
Coordinate point1 =
        parser.parseExpression(
                "new com.example.Coordinate(10.0, 20.0)")
                .getValue(context, Coordinate.class);

Coordinate point2 =
        parser.parseExpression(
                "new com.example.Coordinate('10,20')")
                .getValue(context, Coordinate.class);
~~~

Biểu thức đầu truyền hai đối số số, nên constructor nhận hai tham số double là ứng viên phù hợp. Biểu thức thứ hai truyền một String, nên constructor nhận String được chọn.

Số lượng đối số thường giúp loại bỏ những constructor không phù hợp. Khi nhiều overload có cùng số lượng tham số, SpEL cần xét kiểu đối số và khả năng chuyển đổi để chọn ứng viên tương thích.

## Kiểu đối số và chuyển đổi kiểu

EvaluationContext có **TypeConverter** để hỗ trợ chuyển đổi giá trị khi một đối số chưa có đúng kiểu tham số constructor nhưng có thể chuyển đổi.

Ví dụ, lớp Point có constructor nhận hai số nguyên:

~~~java
public class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
~~~

Có thể truyền literal chuỗi nếu TypeConverter của context hỗ trợ chuyển String thành số nguyên:

~~~java
Expression expression =
        parser.parseExpression(
                "new com.example.Point('10', '20')");

Point point =
        expression.getValue(context, Point.class);
~~~

Trong môi trường Spring thông thường, StandardTypeConverter dựa trên cơ chế chuyển đổi của Spring để hỗ trợ nhiều chuyển đổi phổ biến. Tuy nhiên, không nên mặc định mọi kiểu đều có thể chuyển đổi. Nếu không có converter phù hợp, evaluation sẽ thất bại.

Khi dữ liệu đến từ biến hoặc property, hãy cung cấp kiểu dữ liệu rõ ràng nếu có thể. Việc truyền đúng kiểu thường làm lựa chọn overload dễ dự đoán hơn và giảm phụ thuộc vào chuyển đổi ngầm.

## Overload có thể gây mơ hồ

Nếu một lớp có nhiều constructor nhận các kiểu tham số có thể chuyển đổi từ cùng một giá trị đầu vào, việc lựa chọn có thể không rõ ràng. Trường hợp này dễ gặp khi constructor overload dùng các kiểu gần nhau, kiểu wrapper, kiểu số hoặc giá trị null.

Ví dụ:

~~~java
public class UserKey {
    public UserKey(String value) {
        // ...
    }

    public UserKey(UUID value) {
        // ...
    }
}
~~~

Một biểu thức truyền String rõ ràng:

~~~java
new com.example.UserKey('user-123')
~~~

sẽ hướng tới constructor nhận String. Nhưng nếu biểu thức truyền một giá trị null hoặc một giá trị có thể chuyển đổi theo nhiều cách, việc chọn overload có thể không còn hiển nhiên.

Không nên dựa vào một quy tắc lựa chọn overload ngầm khi kết quả có ý nghĩa nghiệp vụ. Hãy truyền biến có kiểu cụ thể, dùng một constructor có chữ ký không mơ hồ hoặc tạo một static factory method với tên thể hiện rõ mục đích.

Ví dụ, thay vì nhiều overload khó phân biệt, API có thể cung cấp **UserKey.fromText(...)** và **UserKey.fromUuid(...)**. Khi đó, biểu thức hoặc Java code gọi đúng factory method theo ý định.

## Số lượng đối số và varargs

ConstructorResolver cũng phải xét số lượng đối số. Constructor không tham số chỉ phù hợp khi biểu thức không truyền đối số; constructor có tham số phải nhận được số lượng đối số tương ứng, bao gồm các trường hợp varargs mà cơ chế reflection hỗ trợ.

~~~java
public class TagSet {
    private final List<String> tags;

    public TagSet(String... tags) {
        this.tags = List.of(tags);
    }
}
~~~

Nếu dùng constructor varargs, hãy cung cấp các đối số theo cách SpEL và resolver của phiên bản Spring đang dùng có thể ánh xạ đúng. Với biểu thức phức tạp hoặc overload kết hợp varargs, nên kiểm tra bằng test trên đúng phiên bản Spring thay vì dựa vào suy đoán từ cú pháp.

Nếu việc ánh xạ đối số trở nên khó hiểu, một factory method có chữ ký rõ ràng thường là API ổn định hơn cho biểu thức.

## ConstructorResolver tùy chỉnh

Ứng dụng có thể đăng ký **ConstructorResolver** riêng trong StandardEvaluationContext khi cần kiểm soát cách tìm và thực thi constructor.

Một resolver tùy chỉnh có thể hữu ích khi:

- Chỉ cho phép tạo một số kiểu object nhất định.
- Áp dụng quy tắc lựa chọn constructor riêng.
- Tạo object qua factory hoặc cơ chế khởi tạo đặc biệt.
- Giới hạn những constructor mà biểu thức bên ngoài được phép gọi.
- Tích hợp với một mô hình object hoặc container khác.

StandardEvaluationContext cung cấp API để cấu hình danh sách constructor resolver, ví dụ thông qua **setConstructorResolvers(...)** hoặc thêm resolver theo API tương ứng của phiên bản Spring. Khi thay đổi danh sách mặc định, cần quyết định rõ có giữ ReflectiveConstructorResolver hay không.

Một resolver tùy chỉnh nên từ chối type hoặc constructor không được phép một cách rõ ràng. Không nên triển khai resolver chỉ kiểm tra tên kiểu nhưng bỏ qua quyền của constructor hoặc tác động phụ khi khởi tạo.

## Constructor invocation và SimpleEvaluationContext

**SimpleEvaluationContext** được thiết kế cho một tập con khả năng SpEL, chủ yếu dành cho data binding với bề mặt truy cập được giới hạn. Nó không hỗ trợ constructor invocation như StandardEvaluationContext.

Ví dụ, không nên kỳ vọng biểu thức sau chạy trong SimpleEvaluationContext:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("new java.math.BigDecimal('19.95')");
~~~

Nếu use case cần tạo object bằng cú pháp new, hãy dùng context hỗ trợ constructor invocation và cấu hình quyền truy cập phù hợp. Nếu chỉ cần đọc property của DTO, không nên mở rộng context lên StandardEvaluationContext chỉ để có thêm khả năng không cần thiết.

## Lỗi khi chọn hoặc thực thi constructor

Một biểu thức constructor có thể thất bại vì nhiều lý do:

- **Không phân giải được type:** tên lớp sai, dependency không có trong runtime classpath hoặc ClassLoader không nhìn thấy lớp.
- **Không tìm thấy constructor phù hợp:** không có constructor có thể truy cập với số lượng và kiểu đối số được cung cấp.
- **Không chuyển đổi được đối số:** TypeConverter không hỗ trợ chuyển kiểu đầu vào sang kiểu tham số.
- **Overload mơ hồ:** nhiều constructor có thể phù hợp nhưng không thể xác định một lựa chọn rõ ràng.
- **Constructor phát sinh exception:** logic bên trong constructor thất bại khi tạo object.
- **Context không hỗ trợ constructor invocation:** ví dụ dùng SimpleEvaluationContext cho cú pháp new.

Nên phân biệt lỗi parse với lỗi evaluation. Chuỗi **new com.example.Point(1, 2)** có thể hợp lệ về cú pháp, nhưng nếu lớp không tồn tại hoặc không có constructor tương thích, lỗi chỉ xuất hiện khi đánh giá.

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "new com.example.Point(10, 20)");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Point point =
            expression.getValue(context, Point.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or invoke constructor", ex);
}
~~~

Khi ghi log, nên lưu mã biểu thức và loại lỗi cùng thông tin cần thiết về kiểu đích. Tránh ghi toàn bộ đối số nếu chúng có thể chứa dữ liệu nhạy cảm.

## Constructor có thể tạo side effect

Gọi constructor không phải lúc nào cũng là thao tác thuần. Constructor có thể đọc cấu hình, cấp phát tài nguyên, mở kết nối, ghi log hoặc thực hiện logic khác.

Nếu một biểu thức được đánh giá nhiều lần, object mới có thể được tạo nhiều lần và side effect có thể lặp lại. Vì vậy, không nên dùng constructor invocation trong biểu thức mà framework đánh giá thường xuyên nếu việc tạo object có chi phí hoặc tác động phụ đáng kể.

Với object nghiệp vụ hoặc service cần quản lý vòng đời, dependency injection và factory/service method thường phù hợp hơn việc tạo trực tiếp bằng SpEL. Constructor invocation thích hợp nhất cho các giá trị hoặc object nhỏ, có quá trình khởi tạo rõ ràng và ít side effect.

## An toàn khi đánh giá biểu thức từ nguồn bên ngoài

Cho phép constructor invocation trong một evaluation context rộng có thể cho biểu thức khả năng tạo những kiểu Java mà TypeLocator và ConstructorResolver phân giải được. Một biểu thức do người dùng cung cấp có thể cố tạo object không nằm trong ý định ban đầu của ứng dụng.

Nếu cần đánh giá biểu thức từ bên ngoài:

- Giới hạn kiểu được phép phân giải bằng TypeLocator phù hợp.
- Giới hạn constructor bằng ConstructorResolver theo allowlist nếu use case cần tạo object.
- Dùng root object nhỏ và chỉ cung cấp biến cần thiết.
- Tránh expose constructor có thể tạo tài nguyên hoặc thực hiện tác động phụ.
- Giới hạn nguồn, độ dài và quyền chỉnh sửa biểu thức.
- Xử lý riêng lỗi parse, lỗi phân giải constructor và exception khi khởi tạo.

Package import hoặc việc chỉ dùng tên lớp đầy đủ không phải cơ chế bảo mật. Quyền tạo object phụ thuộc vào type resolution, constructor resolver và context mà ứng dụng cung cấp.

## Khi nào nên dùng constructor invocation trong SpEL?

Cú pháp **new ...(...)** phù hợp khi cần tạo một object đơn giản ngay trong biểu thức, chẳng hạn:

- Tạo BigDecimal từ một chuỗi số đã được kiểm soát.
- Tạo một kiểu giá trị nhỏ có constructor rõ ràng.
- Tạo collection hoặc object tiện ích trong một cấu hình giới hạn.
- Tạo một giá trị trung gian tại điểm tích hợp Spring hỗ trợ SpEL.

Nếu object cần quản lý vòng đời, có side effect, cần dependency injection hoặc chứa logic nghiệp vụ phức tạp, hãy tạo nó trong Java hoặc thông qua Spring bean/factory phù hợp. Cách này làm rõ trách nhiệm khởi tạo và giúp kiểm thử dễ hơn.

## Kết luận

**ConstructorResolver** chịu trách nhiệm tìm constructor phù hợp cho biểu thức SpEL có cú pháp **new TypeName(arguments)**. StandardEvaluationContext mặc định sử dụng ReflectiveConstructorResolver; việc chọn overload phụ thuộc số lượng, kiểu đối số và khả năng chuyển đổi của context. Nếu không tìm được constructor tương thích hoặc constructor thất bại, lỗi xuất hiện trong giai đoạn evaluation.

Khi có overload, hãy truyền kiểu đối số rõ ràng và tránh trường hợp mơ hồ như null hoặc chuyển đổi nhiều hướng. Dùng ConstructorResolver tùy chỉnh khi cần giới hạn hoặc thay đổi cách tạo object. Vì constructor có thể tạo side effect, chỉ cho phép biểu thức tạo những object phù hợp và không đánh giá chuỗi không đáng tin cậy trong context có quyền rộng.
