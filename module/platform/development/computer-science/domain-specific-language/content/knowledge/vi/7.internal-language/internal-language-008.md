# Thiết kế API ổn định

## 1. API ổn định có ý nghĩa gì với ngôn ngữ nội bộ?

Ngôn ngữ nội bộ (internal DSL) là một DSL được xây dựng bằng cú pháp và khả năng của một ngôn ngữ chủ, thường thông qua các hàm, lớp, kiểu dữ liệu và API của thư viện. Ví dụ, một DSL cấu hình quy tắc trong Java có thể dùng method chaining để người phát triển viết các câu lệnh gần với ngôn ngữ nghiệp vụ.

Vì internal DSL dựa trên API của ngôn ngữ chủ, người dùng DSL thực chất đang phụ thuộc vào một tập hợp hợp đồng lập trình: tên và chữ ký phương thức, kiểu tham số, kiểu trả về, quy tắc gọi, hành vi khi chạy và cách báo lỗi. Nếu những hợp đồng này thay đổi tùy tiện, mã DSL của người dùng có thể không biên dịch, biên dịch nhưng chạy khác trước, hoặc phải sửa sau mỗi lần nâng cấp thư viện.

**API ổn định** là API có hợp đồng được xác định rõ, thay đổi theo chính sách tương thích và có lộ trình nâng cấp dự đoán được. Ổn định không có nghĩa API không bao giờ thay đổi. Nó có nghĩa nhóm phát triển biết thay đổi nào được phép, thay đổi nào cần phiên bản mới, và người dùng có thời gian cùng công cụ để chuyển đổi.

Ví dụ, một DSL xử lý đơn hàng có thể được sử dụng trong nhiều module:

~~~java
RuleSet rules = RuleDsl.ruleSet()
        .rule("review-large-order")
            .when(orderTotal().greaterThan(money("10000000", "VND")))
            .then(markForManualReview())
            .end()
        .build();
~~~

Nếu thư viện đổi tên phương thức ruleSet(), thay kiểu trả về hoặc đổi ý nghĩa của greaterThan(), mọi chương trình phụ thuộc có thể bị ảnh hưởng. Vì vậy, thiết kế API cần xem các biểu thức mà người dùng viết là một phần của hợp đồng lâu dài.

## 2. Xác định API surface trước khi triển khai

API surface là toàn bộ phần mà người dùng được phép gọi hoặc phụ thuộc vào. Với internal DSL, nó có thể bao gồm:

- Factory và entry point để bắt đầu một biểu thức DSL.
- Các interface, class, record, enum và kiểu dữ liệu công khai.
- Tên phương thức, tham số, kiểu trả về và generic type.
- Quy tắc kết hợp biểu thức, thứ tự thực thi và cách xử lý giá trị thiếu.
- Exception, error code và kết quả trả về.
- Cơ chế mở rộng như plugin, callback, custom function hoặc provider.
- Cấu hình, annotation và định dạng được dùng để khai báo DSL.

Trước khi viết API, cần xác định ai là người sử dụng. Một DSL chỉ dùng trong một module có thể có bề mặt nhỏ và thay đổi đồng bộ cùng ứng dụng. Một DSL được nhiều nhóm dùng trong nhiều repository cần chính sách tương thích chặt chẽ hơn. Nếu đối tượng sử dụng gồm cả người không chuyên lập trình, API còn cần ưu tiên khả năng đọc, tài liệu và thông báo lỗi.

Một cách hữu ích là viết vài chương trình DSL đại diện cho tình huống thực tế trước khi thiết kế class. Các ví dụ đó giúp phát hiện API thiếu khái niệm, tên gọi không tự nhiên hoặc chuỗi gọi quá dài. API nên làm cho ý định nghiệp vụ dễ nhận biết:

~~~java
RuleDsl.ruleSet()
        .rule("eligible-customer")
            .when(customerIsActive())
            .and(customerHasVerifiedEmail())
            .then(allowCheckout())
            .end()
        .build();
~~~

Từ ví dụ này, có thể nhận ra các khái niệm cần hỗ trợ là rule set, rule, condition, kết hợp điều kiện và action. Thiết kế API từ ngôn ngữ nghiệp vụ giúp tránh việc để cấu trúc nội bộ của parser hoặc compiler quyết định hình dạng DSL.

## 3. Tạo entry point rõ ràng và giới hạn bề mặt công khai

Một internal DSL nên có điểm bắt đầu dễ tìm, tên gọi nhất quán và ít cách làm cùng một việc. Factory hoặc facade giúp gom những điểm bắt đầu vào một nơi:

~~~java
public final class RuleDsl {
    private RuleDsl() {
    }

    public static RuleSetBuilder ruleSet() {
        return new DefaultRuleSetBuilder();
    }

    public static RuleBuilder rule(String name) {
        return new DefaultRuleBuilder(name);
    }
}
~~~

Người dùng bắt đầu từ RuleDsl mà không cần biết lớp triển khai cụ thể. Trong ví dụ, DefaultRuleSetBuilder và DefaultRuleBuilder là chi tiết nội bộ; có thể thay đổi chúng mà không buộc người dùng sửa mã nếu hợp đồng công khai vẫn được giữ nguyên.

Nên ưu tiên công khai interface và kiểu giá trị có ý nghĩa trong miền. Tránh buộc người dùng phụ thuộc trực tiếp vào:

- Lớp parser hoặc AST nội bộ.
- Lớp triển khai có tiền tố Default hoặc Internal.
- Entity của ORM hoặc cấu trúc bảng cơ sở dữ liệu.
- Thư viện bên thứ ba chỉ được dùng để triển khai DSL.
- Trường và phương thức chỉ phục vụ cache, tối ưu hóa hoặc debug.

Khi một kiểu nội bộ lọt vào chữ ký API, việc thay thế công nghệ bên trong có thể trở thành thay đổi phá vỡ tương thích. Nếu cần cho phép người dùng quan sát kết quả, hãy cung cấp kiểu công khai nhỏ, ổn định và chỉ chứa thông tin cần thiết.

## 4. Thiết kế fluent API dễ đọc và có quy tắc

Fluent API cho phép nối nhiều lời gọi để tạo biểu thức có cấu trúc. Đây là cách phổ biến để tạo internal DSL trong Java, Kotlin, C# và nhiều ngôn ngữ hướng đối tượng.

### 4.1. Dùng tên phương thức theo ngôn ngữ miền

Tên phương thức nên diễn đạt hành động hoặc khái niệm nghiệp vụ:

| Tên kỹ thuật khó hiểu | Tên theo miền dễ hiểu hơn |
|---|---|
| setStatus(3) | confirm() |
| executeOp(ADD_LINE, data) | addLine(product, quantity) |
| applyFlag(true) | enableAutomaticRenewal() |
| process(value) | calculateShippingCost(destination) |

Không nên cố biến mọi lời gọi thành câu tiếng Anh tự nhiên nếu điều đó làm API dài hoặc không nhất quán. Mục tiêu là giúp người đọc hiểu ý nghĩa mà không phải mở mã triển khai để đoán.

### 4.2. Dùng kiểu dữ liệu để thể hiện khái niệm

Một API ổn định không nên dùng chuỗi hoặc số nguyên tùy ý cho mọi thứ. Kiểu dữ liệu riêng giúp biểu diễn ý nghĩa, kiểm tra đầu vào và giảm nhầm lẫn:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record CurrencyCode(String value) {
    public CurrencyCode {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency code must contain three uppercase letters");
        }
    }
}

public record Money(BigDecimal amount, CurrencyCode currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");
    }
}
~~~

Khi API nhận Money, người gọi phải cung cấp cả số tiền và đơn vị tiền tệ. Điều này rõ nghĩa hơn việc nhận một double không biết đang biểu diễn VND, USD hay một đại lượng khác.

Với dữ liệu có đơn vị, nên cân nhắc kiểu riêng như Duration, Percentage, Distance, CustomerId hoặc OrderId. Kiểu dữ liệu có tên tốt làm hợp đồng dễ đọc và cho phép bổ sung quy tắc mà không rải kiểm tra khắp ứng dụng.

### 4.3. Dùng kiểu trả về nhất quán

Các phương thức trong chuỗi fluent thường trả về builder hoặc interface mô tả bước tiếp theo. Hãy quyết định rõ phương thức nào:

- Trả về chính builder để tiếp tục cấu hình.
- Trả về builder cấp cha để kết thúc một khối con.
- Trả về đối tượng miền bất biến đã hoàn tất.
- Trả về kết quả thực thi.

Ví dụ:

~~~java
import java.util.function.Consumer;

public interface RuleSetBuilder {
    RuleSetBuilder rule(String name, Consumer<RuleBuilder> definition);

    RuleSet build();
}

public interface RuleBuilder {
    RuleBuilder when(Condition condition);

    RuleBuilder then(Action action);

    RuleBuilder otherwise(Action action);
}
~~~

Trong thiết kế này, build() kết thúc quá trình cấu hình và trả về RuleSet. Những kiểu trả về được công bố phải ổn định vì mã người dùng có thể lưu chúng vào biến, truyền chúng qua module hoặc triển khai interface.

### 4.4. Tránh chuỗi gọi mơ hồ

Một DSL khó sử dụng nếu cùng một tên phương thức có nhiều ý nghĩa tùy vào trạng thái ẩn, hoặc người đọc không biết một lời gọi tác động lên rule hiện tại hay toàn bộ rule set.

Ví dụ, tên add() có thể thêm một rule, condition hay action. Tên cụ thể như addRule, and, then hoặc otherwise giúp ý định rõ hơn. Nếu dùng method overloading, các overload nên có ý nghĩa gần nhau và không gây nhập nhằng khi truyền null, lambda hoặc literal.

## 5. Dùng kiểu để giới hạn trạng thái cấu hình không hợp lệ

Một builder có thể cho phép gọi phương thức theo bất kỳ thứ tự nào, sau đó mới báo lỗi khi build(). Với DSL có quy trình rõ ràng, có thể dùng các interface theo từng trạng thái để chỉ phơi bày thao tác hợp lệ tại mỗi bước.

Ví dụ, một rule cần có điều kiện và hành động trước khi hoàn tất:

~~~java
public interface RuleStart {
    RuleWithCondition when(Condition condition);
}

public interface RuleWithCondition {
    RuleReady then(Action action);
}

public interface RuleReady {
    RuleReady otherwise(Action action);

    RuleSetBuilder end();
}

public interface RuleSetBuilder {
    RuleStart rule(String name);

    RuleSet build();
}
~~~

Người dùng sẽ viết:

~~~java
RuleSet policy = RuleDsl.ruleSet()
        .rule("large-order")
            .when(orderTotal().greaterThan(threshold))
            .then(markForReview())
            .end()
        .build();
~~~

Sau khi gọi rule(), API chỉ cung cấp when(). Sau when(), người dùng mới có thể gọi then(). Cách thiết kế này chuyển một phần lỗi cấu hình từ runtime sang compile time.

Tuy nhiên, không nên tạo quá nhiều interface trạng thái nếu DSL có nhiều nhánh tùy chọn. Hệ thống kiểu phức tạp có thể làm API khó đọc, tăng số kiểu công khai và khiến việc bổ sung bước mới trở thành thay đổi lớn. Hãy dùng typed builder cho các trình tự quan trọng, còn những tùy chọn độc lập có thể được kiểm tra ở build().

## 6. Xác định ngữ nghĩa như một phần của hợp đồng

Giữ nguyên tên và chữ ký phương thức chưa đủ để bảo đảm ổn định. Người dùng còn phụ thuộc vào hành vi. Nếu một phiên bản mới đổi cách tính toán mà không đổi API, chương trình vẫn biên dịch nhưng kết quả có thể sai.

Với mỗi biểu thức DSL, cần xác định:

- Điều kiện được đánh giá theo thứ tự nào?
- Biểu thức có short-circuit hay luôn đánh giá mọi nhánh?
- Giá trị null, thiếu hoặc không xác định được xử lý thế nào?
- So sánh chuỗi có phân biệt chữ hoa, chữ thường và locale không?
- Số thập phân được làm tròn theo quy tắc nào?
- Múi giờ và thời điểm được diễn giải ra sao?
- Hành động có được thực hiện đúng một lần hay có thể chạy lại?
- Thứ tự của các rule hoặc action có ảnh hưởng kết quả không?

Ví dụ, hai điều kiện:

~~~java
isCustomerActive().and(hasCredit())
~~~

có thể được đánh giá theo short-circuit: nếu khách hàng không hoạt động thì điều kiện thứ hai không được gọi. Nếu điều kiện thứ hai có side effect, thay đổi hành vi đánh giá có thể ảnh hưởng chương trình dù biểu thức vẫn biên dịch.

Tương tự, greaterThan() cần định nghĩa rõ cách so sánh. Với tiền tệ, nên yêu cầu cùng loại tiền và dùng số thập phân chính xác thay vì phép tính floating point. Với ngày giờ, cần nêu rõ dùng UTC, múi giờ của tenant hay múi giờ được truyền vào.

Những quy tắc này nên được ghi trong tài liệu API và được kiểm thử bằng các ví dụ có kết quả xác định.

## 7. Giữ API công khai độc lập với chi tiết triển khai

Một internal DSL có thể thay đổi parser, cấu trúc AST, thư viện biểu thức hoặc cách thực thi. API công khai nên tạo một lớp ranh giới để người dùng không phải phụ thuộc vào các thay đổi đó.

Ví dụ, người dùng làm việc với Condition và Action:

~~~java
import java.util.List;
import java.util.Optional;

public interface Condition {
    boolean evaluate(EvaluationContext context);
}

public interface Action {
    void execute(EvaluationContext context);
}

public interface EvaluationContext {
    <T> Optional<T> find(Attribute<T> attribute);
}
~~~

Lớp triển khai có thể chuyển các interface này thành AST, tối ưu biểu thức, tạo bytecode hoặc thực thi trực tiếp. Người dùng chỉ phụ thuộc vào hợp đồng công khai.

Không nên trả AST nội bộ từ một phương thức công khai nếu không có nhu cầu rõ ràng. Nếu cần cung cấp khả năng phân tích hoặc hiển thị cây biểu thức, hãy tạo một mô hình inspection riêng với phiên bản và chính sách tương thích được công bố.

Tương tự, không nên để exception từ thư viện parser hoặc engine bên thứ ba rò rỉ trực tiếp qua API. Hãy chuyển chúng thành lỗi ổn định của DSL, đồng thời giữ nguyên nguyên nhân gốc để phục vụ debug.

## 8. Quản lý thay đổi và tương thích phiên bản

Một API có thể có nhiều dạng tương thích:

| Loại tương thích | Nội dung | Ví dụ thay đổi gây ảnh hưởng |
|---|---|---|
| Source compatibility | Mã nguồn người dùng vẫn biên dịch | Đổi tên phương thức, xóa overload |
| Binary compatibility | Artifact đã biên dịch vẫn liên kết được | Đổi descriptor phương thức hoặc xóa class công khai |
| Behavioral compatibility | Chương trình tiếp tục có cùng ý nghĩa và kết quả | Đổi quy tắc làm tròn hoặc thứ tự đánh giá |
| Configuration compatibility | Tệp DSL hoặc cấu hình cũ vẫn được đọc đúng | Đổi tên trường hoặc thay ý nghĩa giá trị |

Một thay đổi có thể giữ source compatibility nhưng phá behavioral compatibility. Ví dụ, phương thức sortRules() vẫn tồn tại nhưng phiên bản mới sắp xếp theo tên thay vì giữ thứ tự khai báo. Nếu thứ tự ảnh hưởng kết quả, đây là thay đổi phá vỡ hợp đồng.

### 8.1. Phân loại thay đổi

| Loại thay đổi | Ví dụ | Cách xử lý |
|---|---|---|
| Bổ sung tương thích | Thêm factory hoặc overload mới | Có thể phát hành trong phiên bản minor nếu không gây nhập nhằng |
| Sửa lỗi không đổi hợp đồng | Sửa lỗi triển khai để hành vi trở lại đúng như tài liệu | Ghi chú phát hành và kiểm thử hồi quy |
| Thay đổi không tương thích | Xóa phương thức, đổi kiểu trả về hoặc đổi ngữ nghĩa công khai | Cần phiên bản major hoặc cơ chế migration |
| Bổ sung API thử nghiệm | Thêm extension chưa cam kết hỗ trợ lâu dài | Đánh dấu rõ trạng thái và phạm vi sử dụng |

Quy tắc versioning nên được công bố trước. Nếu dự án dùng Semantic Versioning, nhóm cần xác định rõ đâu là public API, đâu là phần thử nghiệm và thế nào được xem là breaking change.

### 8.2. Cẩn thận khi thêm phương thức vào interface Java

Thêm phương thức abstract vào một interface công khai có thể làm các lớp do người dùng tự triển khai không còn biên dịch. Trong một số trường hợp, default method giúp bổ sung hành vi mà không buộc mọi implementation phải cập nhật ngay:

~~~java
import java.util.Optional;

public interface Rule {
    String name();

    default Optional<String> description() {
        return Optional.empty();
    }
}
~~~

Tuy nhiên, default method không tự động giải quyết mọi vấn đề tương thích. Hành vi mặc định phải có ý nghĩa cho mọi implementation cũ; cần cân nhắc xung đột với method cùng tên từ interface khác và không nên thêm default method có side effect bất ngờ.

Nếu người dùng không cần tự triển khai một abstraction, có thể công bố class final hoặc factory tạo implementation thay vì interface mở. Thiết kế kiểu mở rộng cần được quyết định từ nhu cầu thật, vì một interface công khai sẽ tạo ra trách nhiệm tương thích với các implementation bên ngoài.

## 9. Thiết kế extension point có kiểm soát

Internal DSL thường cần mở rộng bằng custom function, operator, validator hoặc action. Extension point tốt cần có hợp đồng rõ ràng:

- Kiểu đầu vào và đầu ra.
- Cách đăng ký và định danh extension.
- Quy tắc xử lý khi trùng tên.
- Phiên bản API mà extension hỗ trợ.
- Cách báo lỗi và giới hạn tài nguyên.
- Quyền truy cập mà extension được cấp.

Ví dụ, một registry có thể đăng ký hàm theo tên:

~~~java
import java.util.List;
import java.util.Optional;

public interface DslFunction {
    String name();

    Object invoke(List<Object> arguments, EvaluationContext context);
}

public interface FunctionRegistry {
    void register(DslFunction function);

    Optional<DslFunction> find(String name);
}
~~~

Trong hệ thống thật, kiểu Object có thể được thay bằng hệ thống kiểu biểu thức rõ ràng hơn để kiểm tra tham số và kết quả trước khi chạy. Ví dụ này chỉ minh họa điểm mở rộng và cách tra cứu.

Không nên để extension ghi đè âm thầm hàm hệ thống hoặc đăng ký hai hàm cùng tên với hành vi không xác định. Hãy quy định namespace, độ ưu tiên và cách phát hiện xung đột. Nếu extension chạy mã bên ngoài, cần xác thực nguồn gốc và giới hạn quyền.

Một extension point cũng cần được quản lý phiên bản. Nếu thay đổi chữ ký invoke(), có thể cần interface mới hoặc adapter để extension cũ tiếp tục hoạt động trong giai đoạn chuyển tiếp.

## 10. Thiết kế lỗi và kết quả trả về ổn định

Lỗi là một phần của API. Người dùng cần biết thao tác thất bại vì dữ liệu sai, quy tắc nghiệp vụ không thỏa mãn, thiếu quyền hay lỗi hạ tầng.

Nên phân loại lỗi bằng kiểu hoặc mã ổn định:

~~~java
import java.util.Objects;

public enum DslErrorCode {
    INVALID_EXPRESSION,
    UNKNOWN_FUNCTION,
    TYPE_MISMATCH,
    RULE_NOT_SATISFIED,
    PERMISSION_DENIED,
    EXECUTION_LIMIT_EXCEEDED
}

public final class DslException extends RuntimeException {
    private final DslErrorCode code;

    public DslException(DslErrorCode code, String message, Throwable cause) {
        super(message, cause);
        this.code = Objects.requireNonNull(code);
    }

    public DslErrorCode code() {
        return code;
    }
}
~~~

Mã lỗi có thể được ứng dụng dùng để quyết định phản hồi, còn thông báo lỗi dành cho con người có thể được cải thiện theo thời gian. Không nên khuyến khích chương trình phụ thuộc vào việc so sánh nguyên văn message, vì nội dung có thể cần sửa, dịch hoặc bổ sung thông tin.

Với lỗi phân tích cú pháp, nên cung cấp vị trí dòng và cột, đoạn nguồn liên quan và gợi ý sửa nếu có thể. Với lỗi runtime, cần có định danh rule hoặc action và execution ID để tra cứu log. Không đưa bí mật hoặc dữ liệu nhạy cảm vào thông báo lỗi.

## 11. Tài liệu hóa hợp đồng API

Tài liệu API cần mô tả cả cách gọi và hành vi. Với mỗi entry point hoặc phương thức quan trọng, nên ghi:

- Mục đích nghiệp vụ.
- Tham số, kiểu dữ liệu, đơn vị và giá trị hợp lệ.
- Kiểu trả về và quyền sở hữu đối tượng được trả về.
- Điều kiện trước khi gọi.
- Hành vi sau khi gọi và side effect có thể xảy ra.
- Cách xử lý null, giá trị thiếu và giá trị mặc định.
- Các exception hoặc error code có thể xuất hiện.
- Tính an toàn khi dùng đồng thời (thread-safety).
- Ví dụ thành công và ví dụ lỗi.
- Phiên bản được giới thiệu, trạng thái ổn định hoặc deprecation.

Đặc biệt, tài liệu nên chỉ rõ phần nào là public API được cam kết hỗ trợ và phần nào là API thử nghiệm. Không nên để người dùng phải suy luận hợp đồng từ mã triển khai hoặc từ một ví dụ đơn lẻ.

Các ví dụ trong tài liệu nên được biên dịch và chạy tự động trong CI. Khi chữ ký API thay đổi, build sẽ phát hiện ví dụ cũ không còn đúng; khi hành vi thay đổi, test có thể phát hiện kết quả khác với hợp đồng đã công bố.

## 12. Kiểm thử tính ổn định của API

Kiểm thử API cần bao phủ nhiều lớp khác nhau:

### 12.1. Compile test

Giữ một tập chương trình DSL mẫu trong project test hoặc một module consumer riêng. Build chúng bằng phiên bản thư viện mới để phát hiện thay đổi chữ ký làm mã người dùng không biên dịch.

### 12.2. Contract test

Kiểm tra những hành vi được công bố: thứ tự đánh giá, giá trị mặc định, cách làm tròn, xử lý null, exception và kết quả của các biểu thức tiêu biểu. Test nên kiểm tra kết quả quan sát được qua API, không khóa chặt vào cấu trúc lớp nội bộ.

### 12.3. Compatibility test

Giữ một số chương trình DSL được tạo bằng phiên bản trước và xác nhận chúng vẫn được phân tích hoặc chuyển đổi theo chính sách tương thích. Với thư viện Java, có thể dùng công cụ kiểm tra binary compatibility để phát hiện việc xóa hoặc đổi chữ ký công khai.

### 12.4. Golden test và snapshot

Với DSL sinh mã hoặc biểu diễn trung gian, có thể lưu đầu ra mong đợi cho những trường hợp quan trọng. Khi đầu ra thay đổi, người phát triển phải xem xét liệu đó là thay đổi định dạng vô hại hay thay đổi ngữ nghĩa.

### 12.5. Test extension và tích hợp

Kiểm tra extension do người dùng đăng ký, xung đột tên, thiếu phụ thuộc, quyền truy cập và giới hạn thực thi. Cũng cần kiểm tra ứng dụng có thể phân biệt lỗi của chương trình DSL với lỗi của runtime hoặc hạ tầng.

Một bộ kiểm thử tốt tập trung vào những gì người dùng quan sát được. Test quá phụ thuộc vào tên lớp private, thứ tự gọi nội bộ hoặc cấu trúc AST sẽ làm việc tái cấu trúc implementation khó khăn mà không tăng đáng kể độ tin cậy của hợp đồng.

## 13. Deprecation và migration

Khi một API cần thay thế, nên có lộ trình chuyển đổi thay vì xóa ngay:

1. Công bố API mới và giải thích lý do.
2. Đánh dấu API cũ là deprecated, kèm hướng dẫn thay thế.
3. Nếu có thể, triển khai API cũ bằng cách gọi API mới để giữ cùng hành vi.
4. Phát cảnh báo build hoặc runtime ở mức phù hợp.
5. Cung cấp ví dụ trước và sau, hoặc migration tool cho thay đổi hàng loạt.
6. Duy trì API cũ trong thời gian đã công bố.
7. Loại bỏ API cũ trong phiên bản major theo chính sách tương thích.

Ví dụ với Java:

~~~java
public interface RuleBuilder {
    RuleBuilder when(Condition condition);

    @Deprecated(since = "2.4", forRemoval = true)
    default RuleBuilder ifCondition(Condition condition) {
        return when(condition);
    }
}
~~~

Trong ví dụ này, ifCondition() được giữ như một adapter chuyển tiếp đến when(). Tài liệu nên nêu phiên bản dự kiến loại bỏ và hướng thay thế. Không nên đánh dấu forRemoval = true nếu chưa có kế hoạch và thời điểm loại bỏ rõ ràng.

Với chương trình DSL được lưu dưới dạng tệp, migration có thể chuyển cú pháp cũ sang cú pháp mới. Công cụ cần hiển thị diff, giữ bản gốc và báo các trường hợp không thể chuyển đổi tự động.

## 14. Những lỗi thiết kế thường gặp

### Công khai quá nhiều lớp triển khai

Người dùng bắt đầu phụ thuộc vào constructor, field hoặc method nội bộ. Khi implementation thay đổi, nhóm phát triển không còn tự do tái cấu trúc. Hãy công bố facade và abstraction vừa đủ.

### Để lộ kiểu của thư viện bên thứ ba

Nếu chữ ký API chứa trực tiếp kiểu parser hoặc engine bên ngoài, việc nâng cấp thư viện đó có thể gây breaking change cho người dùng DSL. Hãy dùng kiểu miền của riêng API tại ranh giới công khai khi điều đó có ích.

### Dùng kiểu quá tổng quát

Nhận Object, Map<String, Object> hoặc chuỗi tùy ý ở mọi nơi khiến API khó kiểm tra và dễ sai. Dùng kiểu miền và generic rõ ràng ở những điểm có quy tắc ổn định.

### Thay đổi ngữ nghĩa mà không đổi phiên bản

Một biểu thức vẫn biên dịch nhưng cho kết quả khác có thể gây lỗi nghiệp vụ khó phát hiện. Hãy xem hành vi là một phần của hợp đồng, có test hồi quy và ghi chú phát hành.

### Quá nhiều overload hoặc tên gọi đồng nghĩa

Nhiều cách gọi gần giống nhau làm người dùng khó biết nên chọn API nào. Hãy duy trì một cách gọi chính, chỉ thêm overload khi nó giúp biểu đạt cùng một hành vi rõ ràng hơn.

### Fluent API có thể rơi vào trạng thái không hợp lệ

Nếu builder cho phép gọi build() khi thiếu điều kiện bắt buộc, lỗi chỉ xuất hiện muộn. Dùng typed builder cho trình tự quan trọng hoặc xác thực tập trung khi build.

### Không kiểm soát extension

Extension có thể tạo xung đột tên, hành vi không xác định hoặc thực thi mã không an toàn. Cần namespace, quy tắc đăng ký, phiên bản và giới hạn quyền.

### Không có chính sách hỗ trợ phiên bản

Nếu không công bố thời gian hỗ trợ và lộ trình deprecation, các nhóm dùng DSL không thể lên kế hoạch nâng cấp. Hãy xác định rõ phiên bản được hỗ trợ và cách xử lý chương trình cũ.

## 15. Quy trình thiết kế một API ổn định

Khi bắt đầu một internal DSL hoặc chuẩn bị công bố API cho nhiều nhóm, có thể thực hiện theo các bước:

1. **Xác định người dùng và phạm vi.** Ai viết DSL, ai triển khai extension, ai vận hành và có bao nhiêu ứng dụng phụ thuộc?
2. **Viết ví dụ sử dụng trước.** Tạo các chương trình đại diện cho tình huống chính và tình huống lỗi.
3. **Liệt kê public API surface.** Xác định entry point, kiểu công khai, chữ ký, lỗi, extension point và cấu hình.
4. **Định nghĩa ngữ nghĩa.** Ghi rõ thứ tự đánh giá, giá trị mặc định, đơn vị, độ chính xác, side effect và thread-safety.
5. **Ẩn implementation.** Đặt facade hoặc interface ở ranh giới; giữ parser, AST và engine ở phía nội bộ nếu không cần công khai.
6. **Chọn chính sách versioning.** Phân biệt thay đổi tương thích và breaking change; xác định cách đánh dấu API thử nghiệm.
7. **Thiết kế migration.** Quy định cách deprecate, thời gian hỗ trợ và hướng dẫn chuyển đổi.
8. **Viết contract test.** Kiểm tra compile, binary compatibility, hành vi và các chương trình mẫu.
9. **Tài liệu hóa.** Cung cấp reference, ví dụ, error catalog và ghi chú phát hành.
10. **Thu thập phản hồi trước khi ổn định.** Thử API với người dùng thực tế, sau đó mới cam kết hỗ trợ lâu dài.

## 16. Kết luận

API là hợp đồng mà người dùng internal DSL phụ thuộc vào. Thiết kế ổn định cần bắt đầu từ ngôn ngữ nghiệp vụ và các ví dụ sử dụng, xác định rõ public API surface, cung cấp entry point và fluent method dễ hiểu, dùng kiểu dữ liệu có ý nghĩa và giữ chi tiết parser hoặc engine ở phía triển khai.

Ổn định còn bao gồm ngữ nghĩa, lỗi, thứ tự đánh giá, giá trị mặc định, extension point và khả năng tương thích giữa các phiên bản. Chính sách versioning, contract test, tài liệu và lộ trình deprecation giúp thay đổi API có thể dự đoán và quản lý được.

Khi thêm hoặc sửa một phương thức DSL, hãy tự hỏi: người dùng hiện tại có phải sửa mã không, chương trình cũ có còn cho cùng kết quả không, và nếu cần chuyển đổi thì họ có tài liệu cùng thời gian để làm việc đó không? Trả lời rõ những câu hỏi này giúp API phục vụ được nhiều nhóm và tồn tại lâu dài cùng ngôn ngữ nội bộ.
