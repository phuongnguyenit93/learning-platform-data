# Giới hạn root object, property accessor và resolver

SpEL có thể đọc property, gọi method, tham chiếu kiểu, truy cập bean và gọi function tùy theo khả năng mà EvaluationContext cung cấp. Vì vậy, an toàn của một biểu thức không chỉ phụ thuộc vào chuỗi expression. Nó còn phụ thuộc vào object gốc, property accessor, method resolver, type locator, bean resolver, function đã đăng ký và quyền ghi dữ liệu trong context.

Khi biểu thức được viết và kiểm soát hoàn toàn trong source code, phạm vi sử dụng thường đã được review cùng ứng dụng. Khi expression đến từ database, file cấu hình có thể chỉnh sửa hoặc người dùng, hãy xem nó như một đầu vào có thể thực thi. Thiết kế an toàn bắt đầu bằng nguyên tắc cấp đúng dữ liệu và đúng khả năng tối thiểu mà use case cần.

## 1. EvaluationContext là ranh giới quyền truy cập

EvaluationContext cung cấp dữ liệu và cơ chế để SpEL phân giải biểu thức. Một context có thể chứa root object, variables, property accessors, method resolvers, type locator, bean resolver, function và type converter.

Mỗi thành phần mở thêm một cách mà expression có thể tiếp cận ứng dụng:

| Thành phần | Khả năng được cung cấp |
|---|---|
| Root object | Dữ liệu và method trên object gốc |
| Context variables | Các object hoặc giá trị được đặt tên |
| PropertyAccessor | Đọc hoặc ghi property trên object |
| MethodResolver | Tìm và gọi method |
| TypeLocator | Phân giải kiểu trong T(...) |
| BeanResolver | Tìm bean bằng cú pháp @beanName |
| Registered functions | Gọi Method đã đăng ký bằng tên function |
| TypeConverter | Chuyển đổi kiểu trong quá trình đánh giá hoặc gán |

Không phải expression nào cũng cần tất cả khả năng này. Một rule chỉ đọc hai thuộc tính để quyết định hiển thị có thể không cần method invocation, type reference, bean reference hay quyền ghi.

Hãy cấu hình context theo use case cụ thể. Càng ít object và resolver được cấp, càng dễ giải thích expression có thể làm gì.

## 2. Chọn root object nhỏ và có phạm vi rõ

Root object là điểm bắt đầu của expression. Nếu đưa một entity lớn hoặc service có nhiều method làm root, expression có thể tiếp cận nhiều dữ liệu và hành vi hơn mức cần thiết.

Ví dụ, thay vì đưa toàn bộ User entity vào context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(user);
~~~

hãy cân nhắc tạo một DTO chỉ chứa dữ liệu cần cho rule:

~~~java
public record UserRuleData(
        String region,
        boolean active,
        int accountAgeDays) {
}

UserRuleData ruleData = new UserRuleData(
        user.getRegion(),
        user.isActive(),
        user.getAccountAgeDays()
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Sau đó truyền ruleData làm root object khi đánh giá:

~~~java
Expression expression = parser.parseExpression(
        "active and region == 'APAC' and accountAgeDays >= 30"
);

Boolean allowed = expression.getValue(
        context,
        ruleData,
        Boolean.class
);
~~~

DTO nhỏ giúp giới hạn dữ liệu mà expression nhìn thấy. Nó cũng tách cấu trúc rule khỏi entity persistence và tránh vô tình expose quan hệ lazy, thông tin bí mật hoặc method nghiệp vụ.

Root object nên phản ánh đúng hợp đồng của biểu thức. Nếu rule chỉ cần ba giá trị, không cần đưa toàn bộ graph object vào context.

## 3. Không đưa service hoặc repository làm root object

Service và repository thường có nhiều method, dependency và side effect. Nếu một service được đặt làm root object trong context có khả năng gọi method, expression có thể gọi các thao tác mà cấu hình ban đầu không dự định cho phép.

Ví dụ không nên dùng service rộng quyền làm root:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(paymentService);
~~~

Expression có thể tìm cách gọi method trên object này nếu MethodResolver cho phép.

Nếu cần một giá trị được tính từ service, hãy gọi service trong Java trước, sau đó chỉ đưa kết quả cần thiết vào context:

~~~java
boolean eligible = eligibilityService.isEligible(customer);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

context.setVariable("eligible", eligible);
~~~

Expression chỉ nhận Boolean đã được xác định. Nó không cần truy cập eligibilityService hoặc các dependency bên trong service.

Cách này giữ quyền truy cập hệ thống ở application layer, nơi có thể thực hiện authorization, transaction, logging và xử lý lỗi rõ ràng.

## 4. Dùng SimpleEvaluationContext khi chỉ cần data binding

SimpleEvaluationContext được thiết kế cho các tình huống SpEL có phạm vi tính năng giới hạn. Nó không cung cấp toàn bộ khả năng của StandardEvaluationContext.

Ví dụ context chỉ đọc property theo data binding:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Nếu cần ghi property:

~~~java
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

SimpleEvaluationContext không hỗ trợ type reference, constructor invocation hoặc bean reference như context đầy đủ. Instance method invocation cũng không được bật mặc định; builder có thể bật rõ ràng nếu use case thực sự cần.

Đối với rule chỉ đọc, hãy bắt đầu bằng read-only context. Chỉ chọn read-write khi cần cập nhật property và chỉ bật instance methods khi đã xác định rõ method nào cần dùng.

Không chuyển sang StandardEvaluationContext chỉ vì một biểu thức đơn giản gặp giới hạn. Trước tiên hãy xem có thể chuẩn bị dữ liệu trong Java hoặc cung cấp một context nhỏ hơn hay không.

## 5. Phân biệt StandardEvaluationContext và SimpleEvaluationContext

StandardEvaluationContext cung cấp tập khả năng rộng hơn, bao gồm các cơ chế reflection và resolver có thể cấu hình. Điều này hữu ích cho expression nội bộ cần nhiều tính năng SpEL, nhưng cũng làm phạm vi quyền truy cập rộng hơn nếu dùng với expression không đáng tin cậy.

SimpleEvaluationContext phù hợp với data binding và một tập tính năng được lựa chọn rõ. Nó không tự động trở thành sandbox cho mọi tình huống, nhưng giảm số khả năng có sẵn mặc định.

| Nhu cầu | Hướng cấu hình |
|---|---|
| Chỉ đọc JavaBean property | SimpleEvaluationContext read-only |
| Đọc và ghi property có kiểm soát | SimpleEvaluationContext read-write |
| Cần instance method | Chỉ bật rõ ràng nếu thực sự cần |
| Cần type reference, constructor hoặc bean reference | Đánh giá cẩn thận nhu cầu và phạm vi StandardEvaluationContext |
| Expression do người dùng cung cấp | Không cấp context rộng; dùng DSL hoặc rule có cấu trúc nếu có thể |

Hãy chọn context dựa trên khả năng expression cần dùng, không chỉ dựa trên việc context nào dễ tạo hơn.

## 6. PropertyAccessor quyết định property nào có thể đọc hoặc ghi

PropertyAccessor là cơ chế SpEL dùng để đọc và ghi property trên object. Accessor có thể hỗ trợ một kiểu object cụ thể và quyết định property nào có thể được truy cập.

StandardEvaluationContext có thể được cấu hình với các PropertyAccessor. SimpleEvaluationContext cũng cho phép xây dựng context từ tập accessor được chọn.

Với dữ liệu nhạy cảm, không nên expose mọi property chỉ vì object có getter. Ví dụ một Account có thể có public property balance, status, passwordHash và internalFlags. Rule hiển thị có thể chỉ cần status và region; việc mở tất cả property là không cần thiết.

Một accessor theo allowlist có thể chỉ cho phép những property được xác định trước. Ví dụ hợp đồng mong muốn:

~~~text
UserRuleData.region       read
UserRuleData.active       read
UserRuleData.accountAgeDays read
UserRuleData.internalNotes deny
UserRuleData.credential   deny
~~~

Đây là nguyên tắc thiết kế. Khi triển khai custom PropertyAccessor, cần xác định rõ target type, tên property được phép, cách đọc, cách ghi và exception khi property không được hỗ trợ.

Không nên dùng một accessor tổng quát có thể đọc mọi field hoặc gọi reflection tùy ý trên bất kỳ object nào nếu expression không đáng tin cậy.

## 7. DataBindingPropertyAccessor và phạm vi truy cập

Spring cung cấp DataBindingPropertyAccessor cho các use case data binding. SimpleEvaluationContext có các builder dành cho read-only hoặc read-write data binding để tạo context với property accessor tương ứng.

Data binding accessor giới hạn một số kiểu truy cập kỹ thuật so với reflective property access rộng. Tuy vậy, việc một property có thể đọc được vẫn phụ thuộc object được cấp và hợp đồng property của object đó.

Hãy nhớ rằng accessor không thể biến một root object quá rộng thành một API nghiệp vụ an toàn một cách tự động. Nếu root object có nhiều property công khai, cần cân nhắc dùng DTO hoặc custom accessor để giảm bề mặt truy cập.

Với dữ liệu chỉ đọc, không bật quyền ghi. Với dữ liệu cần cập nhật, xác định trước property nào có thể thay đổi và kiểm tra object sau khi ghi.

## 8. Tạo PropertyAccessor theo allowlist

Nếu rule chỉ được phép đọc một số property, có thể triển khai PropertyAccessor chuyên biệt cho kiểu DTO đó. Accessor cần thực hiện các bước:

1. Khai báo kiểu target mà accessor hỗ trợ.
2. Kiểm tra tên property nằm trong allowlist.
3. Chỉ đọc giá trị từ API được định nghĩa cho property đó.
4. Từ chối property ngoài danh sách.
5. Không cho ghi nếu use case chỉ đọc.
6. Nếu có ghi, kiểm tra riêng danh sách property được phép ghi và kiểu giá trị.

Ví dụ về allowlist ở mức thiết kế:

~~~java
Set<String> readableProperties = Set.of(
        "region",
        "active",
        "accountAgeDays"
);

Set<String> writableProperties = Set.of();
~~~

Tập writable rỗng thể hiện accessor chỉ đọc. Nếu cần ghi, hãy khai báo rõ từng property được phép và kiểm tra quyền ở application layer trước khi gọi setValue.

Khi accessor không hỗ trợ property, hãy để resolver tiếp tục theo chính sách được thiết kế hoặc phát sinh lỗi phù hợp. Không nên âm thầm trả null cho property bị cấm, vì điều đó khiến biểu thức có thể hiểu nhầm rằng dữ liệu thực sự null.

## 9. MethodResolver kiểm soát lời gọi method

MethodResolver chịu trách nhiệm tìm method phù hợp cho một lời gọi trong expression. StandardEvaluationContext mặc định có cơ chế reflection method resolution rộng hơn.

Nếu expression chỉ cần đọc property, không cần cho phép method invocation. Nếu cần gọi method, hãy giới hạn API được expose bằng root object nhỏ hoặc một resolver tùy chỉnh chỉ cho phép method được chọn.

Ví dụ một DTO chỉ cung cấp method thuần:

~~~java
public class ProductRuleData {

    private final int stock;
    private final boolean discontinued;

    public ProductRuleData(int stock, boolean discontinued) {
        this.stock = stock;
        this.discontinued = discontinued;
    }

    public boolean isAvailable() {
        return stock > 0 && !discontinued;
    }
}
~~~

Expression có thể kiểm tra isAvailable nếu context cho phép instance method. Tuy nhiên, không nên đưa một object có method ghi dữ liệu, gửi request hoặc xóa dữ liệu vào context chỉ để dùng một method tiện ích.

Khi không cần method, hãy dùng SimpleEvaluationContext với instance method invocation chưa bật. Nếu cần method, ưu tiên API nhỏ, thuần và có tên mô tả rõ kết quả.

## 10. TypeLocator và type reference T(...)

TypeLocator phân giải tên kiểu được tham chiếu bằng cú pháp T(...). Khi dùng StandardEvaluationContext, StandardTypeLocator mặc định có thể phân giải kiểu theo tên đầy đủ và package import.

Type reference có thể mở đường cho static method hoặc static field:

~~~text
T(java.lang.Math).max(10, 20)
T(java.util.UUID).randomUUID()
~~~

Nếu expression không cần tham chiếu kiểu, hãy tránh cấp khả năng này. SimpleEvaluationContext không cung cấp type reference như StandardEvaluationContext.

Nếu ứng dụng bắt buộc phải hỗ trợ một tập kiểu, hãy cân nhắc TypeLocator giới hạn danh sách class được phép. Không nên cho expression tùy ý phân giải mọi class trên classpath chỉ để hỗ trợ một vài phép tính.

Một type reference an toàn vẫn có thể gọi static method có side effect nếu method đó được phép. Vì vậy, kiểm soát TypeLocator cần đi cùng kiểm soát method resolution và các object khác trong context.

## 11. BeanResolver và quyền truy cập Spring bean

BeanResolver cho phép SpEL tham chiếu bean theo tên bằng cú pháp @beanName. Khi có BeanResolver phù hợp, expression có thể lấy bean và gọi property hoặc method trên bean đó.

Ví dụ:

~~~text
@featureSettings.enabled
@priceCalculator.calculate(#amount)
~~~

Khả năng này có thể làm expression phụ thuộc vào nhiều service trong ApplicationContext. Nếu expression được chỉnh sửa bởi nguồn không tin cậy, bean reference có thể mở quyền truy cập vượt quá mục đích của rule.

Không cấu hình BeanResolver nếu use case không cần bean reference. Nếu cần, hãy chỉ expose một façade nhỏ, không đưa toàn bộ service container hoặc bean có quyền ghi rộng vào phạm vi expression.

Đối với điều kiện cấu hình Spring Boot, tránh tham chiếu bean nghiệp vụ trong @ConditionalOnExpression vì điều kiện được đánh giá sớm trong quá trình xử lý cấu hình và có thể kích hoạt bean khởi tạo trước thời điểm mong muốn.

## 12. Registered functions cũng là một bề mặt quyền truy cập

Function được đăng ký vào EvaluationContext có thể được gọi từ expression bằng tên #functionName(...). Mỗi function mở thêm một hành động mà biểu thức có thể thực hiện.

Chỉ đăng ký function thật sự cần thiết. Ưu tiên method thuần, nhận dữ liệu rõ ràng và trả về kết quả xác định.

Không đăng ký các function như:

~~~text
#deleteAccount(...)
#sendPayment(...)
#executeCommand(...)
~~~

cho một context đánh giá rule không đáng tin cậy.

Nếu cần một phép kiểm tra domain, cung cấp function chỉ đọc có phạm vi hẹp, chẳng hạn #isEligible(#ruleData). Kiểm tra authorization và thực hiện side effect vẫn thuộc service layer.

Function không trở nên an toàn chỉ vì tên của nó không được hiển thị cho người dùng. Bất kỳ function nào có trong context đều là một khả năng mà expression có thể thử gọi.

## 13. Quyền ghi và assignment

SpEL có thể gán giá trị cho property hoặc indexer nếu context và accessor cho phép ghi. Điều này hữu ích cho data binding, nhưng không cần thiết với biểu thức lọc hoặc tính toán.

Nếu expression không cần thay đổi object, hãy dùng context read-only hoặc tắt assignment theo cấu hình builder phù hợp. Không cấp read-write context chỉ vì nó cũng có thể đọc property.

Khi cần ghi, hãy giới hạn root object vào một DTO hoặc command object có các property được phép cập nhật. Không đưa entity có trạng thái nhạy cảm vào context rồi để expression chọn tùy ý property path.

Sau khi cập nhật, ứng dụng vẫn cần validate object, kiểm tra quyền và quyết định có lưu thay đổi hay không. Ghi thành công qua PropertyAccessor không đồng nghĩa thao tác đã được phép theo nghiệp vụ.

## 14. Không đánh giá expression tùy ý do người dùng gửi

Expression do người dùng nhập có thể chứa nhiều cú pháp hơn một điều kiện nghiệp vụ đơn giản. Nếu đánh giá trực tiếp bằng context rộng, người dùng có thể thử đọc property ngoài phạm vi, gọi method hoặc tham chiếu bean/type đã được cấp.

Các lựa chọn an toàn hơn:

- Cung cấp một DSL có cấu trúc, ví dụ field, operator và value đã được allowlist.
- Cho người dùng chọn từ các rule template đã định nghĩa.
- Parse input thành AST hoặc cấu trúc dữ liệu riêng rồi tự đánh giá các phép toán được phép.
- Nếu vẫn dùng SpEL, giới hạn cú pháp, context, root object, accessor và resolver theo một hợp đồng cụ thể.
- Không cho phép expression tùy ý thực hiện assignment hoặc gọi method có side effect.

Một allowlist field đơn thuần ở giao diện không đủ nếu backend vẫn đánh giá chuỗi SpEL tùy ý với context đầy đủ. Kiểm soát phải được thực hiện ở server side trước khi đánh giá.

## 15. Tách dữ liệu và logic nghiệp vụ khỏi expression

Expression nên tập trung vào phép tính hoặc điều kiện nhỏ. Các thao tác như kiểm tra quyền, truy vấn database, gọi API, tính giá theo nhiều quy tắc và cập nhật trạng thái nên nằm trong Java.

Ví dụ, thay vì để expression gọi nhiều service:

~~~text
@accountService.isActive(#userId) and
@riskService.score(#userId) < 50 and
@paymentService.hasNoDebt(#userId)
~~~

hãy tính một DTO kết quả trong service:

~~~java
public record EligibilityRuleData(
        boolean active,
        int riskScore,
        boolean hasNoDebt) {
}
~~~

Service tạo dữ liệu sau khi thực hiện các kiểm tra có quyền phù hợp. SpEL chỉ đánh giá:

~~~text
active and riskScore < 50 and hasNoDebt
~~~

Cách này giúp expression không trực tiếp điều phối service. Dữ liệu đầu vào cũng có thể được kiểm thử độc lập và không làm lộ các dependency bên trong ứng dụng.

## 16. Giới hạn chi phí và độ phức tạp của expression

Expression có thể duyệt collection, gọi method và truy cập object lồng nhau. Một biểu thức ngắn vẫn có thể tạo chi phí lớn nếu nó gọi method truy vấn database cho từng phần tử hoặc duyệt collection rất lớn.

Một số nguyên tắc:

1. Giới hạn kích thước dữ liệu đưa vào context.
2. Tránh method có I/O hoặc lazy loading trong predicate.
3. Tính trước dữ liệu cần thiết trong Java.
4. Giữ collection operation đơn giản và có giới hạn rõ.
5. Không để người dùng cung cấp biểu thức có thể tạo cấu trúc tính toán không giới hạn.
6. Theo dõi thời gian đánh giá và số lần gọi function/method ở các rule quan trọng.

Nếu cần truy vấn tập dữ liệu lớn, hãy lọc ở database hoặc service layer thay vì tải toàn bộ collection vào context rồi để SpEL duyệt.

## 17. Kiểm tra và xử lý lỗi theo ranh giới

Khi expression bị từ chối hoặc đánh giá thất bại, hãy phân biệt lỗi cú pháp, lỗi phân giải và lỗi runtime:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Parse | Cú pháp không hợp lệ | Kiểm tra grammar và template |
| Property access | Property không nằm trong allowlist hoặc không tồn tại | Kiểm tra accessor và root object |
| Method resolution | Method không được phép hoặc không tồn tại | Kiểm tra MethodResolver |
| Type resolution | T(...) tham chiếu kiểu không được phép | Kiểm tra TypeLocator |
| Bean resolution | @beanName không được phân giải | Kiểm tra BeanResolver và chính sách bean |
| Conversion | Kiểu đối số/giá trị không tương thích | Kiểm tra TypeConverter |
| Assignment | Expression cố ghi trong context chỉ đọc | Từ chối thao tác ghi |
| Runtime | Getter hoặc method ném exception | Xem cause và xử lý ở application layer |

Không nên trả về true hoặc null mặc định khi expression lỗi. Với rule quyết định quyền hoặc trạng thái quan trọng, lỗi đánh giá cần được xử lý theo chính sách fail-closed phù hợp với use case.

Log nên ghi mã rule, loại lỗi và nguyên nhân kỹ thuật cần thiết. Tránh ghi toàn bộ expression hoặc dữ liệu nhạy cảm nếu chuỗi đó có thể chứa thông tin người dùng.

## 18. Kiểm thử cấu hình quyền truy cập

Một context an toàn cần được kiểm thử cả khả năng được phép và bị từ chối.

Các trường hợp nên kiểm tra:

- Expression đọc được property trong allowlist.
- Expression không đọc được property nhạy cảm.
- Expression không ghi được property trong context read-only.
- Context read-write chỉ cập nhật property được cho phép.
- Method invocation bị từ chối khi không bật.
- Method không nằm trong allowlist không thể được gọi.
- Type reference bị từ chối nếu context không hỗ trợ hoặc TypeLocator giới hạn.
- Bean reference không được phân giải nếu không cấu hình BeanResolver.
- Function ngoài danh sách không tồn tại trong context.
- Null và dữ liệu sai kiểu được xử lý theo chính sách.
- Expression lỗi không được chuyển thành kết quả cho phép mặc định.

Hãy kiểm thử trên đúng loại EvaluationContext và resolver mà ứng dụng triển khai. Unit test chỉ parse expression mà không đánh giá với context thực tế sẽ không kiểm tra được ranh giới quyền truy cập.

## 19. Ví dụ hoàn chỉnh: context chỉ đọc với dữ liệu tối thiểu

Ví dụ sau tạo một object chỉ chứa dữ liệu mà rule cần:

~~~java
public record OrderRuleData(
        BigDecimal total,
        String region,
        boolean customerActive) {
}
~~~

Chuẩn bị dữ liệu trong Java và đánh giá:

~~~java
OrderRuleData data = new OrderRuleData(
        new BigDecimal("250.00"),
        "APAC",
        true
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "total >= 100 and region == 'APAC' and customerActive"
);

Boolean accepted = expression.getValue(
        context,
        data,
        Boolean.class
);
~~~

Expression chỉ đọc ba thuộc tính. Nó không có service, repository, bean resolver hay type reference cần thiết cho thao tác này.

Nếu sau này rule cần một giá trị khác, hãy mở rộng DTO theo hợp đồng có chủ đích. Đừng đưa toàn bộ entity hoặc ApplicationContext vào chỉ để tránh phải chuẩn bị dữ liệu.

## 20. Ghi nhớ

Giới hạn SpEL bắt đầu từ EvaluationContext. Chọn root object nhỏ, ưu tiên DTO chỉ chứa dữ liệu cần thiết, dùng SimpleEvaluationContext khi phù hợp và chỉ cấp property accessor, method resolver, type locator, bean resolver hoặc function mà use case thực sự cần.

PropertyAccessor quyết định property nào có thể đọc/ghi; MethodResolver quyết định method nào có thể gọi; TypeLocator phân giải T(...); BeanResolver phân giải @beanName; registered functions mở thêm các hành động có thể gọi. Quyền assignment cũng cần được giới hạn nếu expression chỉ đọc.

Không đánh giá expression tùy ý từ người dùng bằng context rộng. Hãy dùng DSL hoặc rule template có cấu trúc khi có thể, tách logic nghiệp vụ và side effect sang Java, kiểm thử cả trường hợp được phép lẫn bị từ chối, và xử lý lỗi theo chính sách rõ ràng. Một context an toàn chỉ expose đúng dữ liệu và hành vi cần thiết cho một mục đích cụ thể.