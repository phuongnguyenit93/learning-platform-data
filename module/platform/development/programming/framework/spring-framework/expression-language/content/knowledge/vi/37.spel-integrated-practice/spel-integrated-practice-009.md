# Thiết kế allowlist cho expression do người dùng cung cấp

## Mục tiêu

Khi ứng dụng cho phép người dùng viết hoặc chỉnh sửa Spring Expression Language (SpEL), expression trở thành đầu vào có thể thực thi. Người dùng có thể thử đọc property, gọi method, truy cập type, tạo object hoặc sử dụng các khả năng khác mà EvaluationContext cung cấp. Vì vậy, không nên đánh giá trực tiếp một chuỗi SpEL tùy ý bằng context có đầy đủ quyền.

Một **allowlist** xác định rõ những cấu trúc, dữ liệu và thao tác mà expression được phép sử dụng. Thiết kế an toàn bắt đầu từ nguyên tắc deny-by-default: chỉ cho phép những gì đã được xác định và kiểm thử; mọi cú pháp hoặc quyền chưa được duyệt đều bị từ chối.

Sau bài này, bạn có thể:

- Thiết kế allowlist cho expression do người dùng nhập.
- Chọn một tập cú pháp SpEL được phép và từ chối phần còn lại.
- Giới hạn property, method, function và dữ liệu mà expression có thể truy cập.
- Cấu hình EvaluationContext với quyền tối thiểu.
- Xác thực expression trước khi lưu hoặc kích hoạt.
- Giới hạn độ dài, độ phức tạp và tài nguyên đánh giá.
- Cô lập expression theo user, tenant và phiên bản policy.
- Kiểm thử cả cú pháp được phép lẫn các cách truy cập bị cấm.
- Theo dõi và thu hồi expression khi policy thay đổi.

## 1. Xác định mô hình sử dụng trước khi cho phép SpEL

Trước khi thiết kế allowlist, hãy xác định người dùng thực sự cần làm gì. Có nhiều mức độ linh hoạt khác nhau:

1. **Chọn rule có sẵn:** người dùng chọn một điều kiện được định nghĩa trước.
2. **Cấu hình tham số:** người dùng nhập ngưỡng, trạng thái hoặc danh sách giá trị; ứng dụng ghép dữ liệu vào một expression cố định thông qua biến.
3. **Tạo điều kiện có cấu trúc:** người dùng chọn property, toán tử và giá trị từ UI; backend tạo expression từ một model đã kiểm tra.
4. **Nhập SpEL tự do có giới hạn:** người dùng nhập expression, backend parse và chỉ chấp nhận một tập cú pháp được duyệt.

Ba cách đầu thường dễ kiểm soát hơn. Nếu nghiệp vụ chỉ cần cho phép người dùng chọn trường, toán tử và giá trị, không cần mở một ngôn ngữ expression đầy đủ. Hãy ưu tiên cấu hình có cấu trúc hoặc expression template cố định với biến context.

Chỉ dùng SpEL do người dùng cung cấp khi lợi ích của tính linh hoạt đủ lớn để biện minh cho việc duy trì parser policy, accessor, resolver, kiểm thử và quy trình thu hồi.

## 2. Nguyên tắc deny-by-default

Một allowlist phải trả lời cụ thể những gì được phép. Không nên bắt đầu bằng cách cho phép toàn bộ SpEL rồi cố chặn một vài chuỗi nguy hiểm.

Một policy có thể định nghĩa các nhóm sau:

| Nhóm | Chính sách minh họa |
|---|---|
| Literal | Cho phép String, số, Boolean và null nếu nghiệp vụ cần |
| Toán tử | Cho phép toán tử số học, so sánh và logic đã chọn |
| Ngoặc | Cho phép nhóm biểu thức bằng ngoặc |
| Biến | Chỉ cho phép danh sách biến đã khai báo |
| Root object | Chỉ cho phép một DTO có schema rõ |
| Property | Chỉ cho phép property được liệt kê |
| Method | Mặc định từ chối; chỉ mở method thuần đã duyệt |
| Function | Chỉ mở function cụ thể có hợp đồng rõ, nếu thật sự cần |
| Collection operation | Chỉ cho phép selection/projection khi có giới hạn dữ liệu |
| Type reference | Từ chối |
| Constructor | Từ chối |
| Bean reference | Từ chối |
| Assignment | Từ chối |
| Truy cập class/reflection | Từ chối |
| Side effect | Từ chối |

Policy thực tế có thể hẹp hơn. Ví dụ, một bộ lọc đơn giản có thể chỉ cần property read, biến, literal, toán tử so sánh và toán tử logic. Không bật collection operations, method invocation hoặc function nếu không có yêu cầu.

Quy tắc mặc định: một node, property hoặc lời gọi chưa có trong policy được xem là không được phép.

## 3. Giới hạn EvaluationContext

EvaluationContext quyết định expression có thể truy cập dữ liệu và thực hiện thao tác nào. Không dùng StandardEvaluationContext với cấu hình rộng cho expression không đáng tin cậy nếu không có lý do và kiểm soát rất chặt.

**SimpleEvaluationContext** được thiết kế cho các trường hợp data binding có tập chức năng giới hạn. Nó không hỗ trợ Java type reference, constructor invocation hoặc bean reference. Context này cũng yêu cầu ứng dụng lựa chọn rõ cách truy cập property và method.

Ví dụ context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();
~~~

Ví dụ này minh họa chế độ data binding chỉ đọc. Khi cần allowlist property riêng, hãy cấu hình custom PropertyAccessor phù hợp với schema được phép. Khi cần method, cung cấp custom MethodResolver chỉ nhận đúng các method đã duyệt.

Không bật khả năng method invocation tổng quát chỉ để một expression hoạt động. Nếu sử dụng withInstanceMethods(), hãy hiểu rõ phạm vi method mà resolver đó có thể tìm thấy; nó không tự tạo allowlist theo nghiệp vụ.

Với dữ liệu đầu vào không đáng tin, context nên:

- Chỉ cung cấp root DTO đã được chuẩn hóa.
- Chỉ đăng ký các biến cần thiết.
- Chỉ cung cấp PropertyAccessor đã giới hạn property.
- Chỉ cung cấp MethodResolver allowlist nếu method invocation là yêu cầu.
- Dùng TypeConverter có quy tắc rõ ràng.
- Không đăng ký BeanResolver nếu không cần.
- Không cho phép truy cập type hoặc constructor.
- Không đưa application context, service registry hoặc object có quyền rộng vào biến.

SimpleEvaluationContext giúp giảm tập chức năng, nhưng không thay thế toàn bộ policy. Những property và method mà ứng dụng tự cung cấp vẫn phải được kiểm soát.

## 4. Allowlist property bằng model và PropertyAccessor

Không nên đưa entity hoặc service object đầy đủ vào root object. Getter của entity có thể truy cập lazy relationship, chạy truy vấn, trả dữ liệu nhạy cảm hoặc thực hiện logic không dự kiến.

Tạo một DTO chỉ đọc chứa đúng dữ liệu expression cần:

~~~java
public record OrderRuleInput(
    BigDecimal total,
    String region,
    boolean active,
    OrderStatus status
) {}
~~~

Expression có thể đọc các property đã được công bố:

~~~text
#root.total >= #minimumTotal
and #root.active
and #root.region == #requiredRegion
~~~

Một custom PropertyAccessor có thể kiểm tra chính xác target type và tên property được phép. Nếu expression yêu cầu property không có trong allowlist, accessor từ chối truy cập.

Policy property nên ghi rõ:

- Kiểu root được chấp nhận.
- Tên property được phép.
- Kiểu dữ liệu của từng property.
- Property có thể null hay không.
- Property nào được phép dùng trong collection operation.
- Property nào bị cấm vì chứa secret hoặc object có quyền rộng.

Không dựa vào việc người dùng không biết tên property. Tên property cần được kiểm soát ở runtime bằng accessor và model đầu vào đã giới hạn.

## 5. Allowlist method và function

Mặc định nên từ chối method invocation. Một method công khai trên object không mặc nhiên an toàn để gọi từ expression.

Nếu cần method, allowlist phải chỉ rõ:

- Class hoặc interface sở hữu method.
- Tên method.
- Kiểu và số lượng tham số.
- Kiểu trả về.
- Hành vi null.
- Tính thuần và side effect.
- Giới hạn chi phí thực thi.

Ví dụ, có thể cho phép một method thuần kiểm tra trạng thái:

~~~java
public final class RuleFunctions {

    private RuleFunctions() {}

    public static boolean isAllowedRegion(
            String region,
            Set<String> allowedRegions) {
        return region != null
            && allowedRegions.contains(region);
    }
}
~~~

Chỉ công bố method này nếu policy cần nó và các đối số đã được xác thực. Không cho expression gọi method bất kỳ bằng cách bật resolver phản chiếu rộng.

Các method nên bị loại khỏi allowlist gồm:

- Ghi dữ liệu hoặc thay đổi trạng thái.
- Gửi email, message hoặc notification.
- Gọi HTTP, database hoặc hệ thống bên ngoài.
- Đọc/ghi file, environment hoặc system property.
- Khởi chạy process hoặc thread.
- Truy cập reflection, class loader hoặc runtime.
- Truy cập credential, token hoặc secret.
- Thực hiện công việc không có giới hạn rõ ràng.

Function trong SpEL cũng là một khả năng thực thi Java method. Nếu cần function, hãy đăng ký từng function đã duyệt qua cơ chế context phù hợp với phiên bản Spring đang dùng và kiểm thử rằng context không thể gọi method ngoài policy. Không công bố một tập function chung có quyền rộng cho mọi tenant.

## 6. Từ chối type reference, constructor và bean reference

Các cú pháp sau mở rộng đáng kể khả năng của expression:

~~~text
T(java.lang.Runtime)
new java.lang.String('value')
@someBean
~~~

Trong expression do người dùng cung cấp, hãy từ chối các khả năng này theo mặc định:

- **T(...):** tham chiếu class Java, có thể mở đường tới static field và static method.
- **new ...:** tạo object bằng constructor.
- **@beanName:** truy cập Spring bean và có thể dẫn tới service hoặc tài nguyên ứng dụng.

Không cho phép các cú pháp này chỉ vì class hoặc bean hiện tại có vẻ vô hại. Danh sách class/bean có thể thay đổi khi ứng dụng phát triển và vô tình mở thêm quyền.

Nếu một rule cần giá trị từ bean hoặc static constant, hãy lấy giá trị trong Java rồi truyền vào context dưới dạng biến có kiểu rõ. Điều này giúp expression chỉ nhìn thấy dữ liệu cần thiết thay vì có quyền tự tìm object trong container.

## 7. Kiểm tra cú pháp trước khi đánh giá

Quy trình an toàn cần có bước parse và validation trước khi evaluate. Không đánh giá ngay chuỗi do người dùng gửi.

Một pipeline tham khảo:

1. Xác thực caller có quyền tạo hoặc sửa rule.
2. Kiểm tra độ dài và encoding của source.
3. Parse bằng parser configuration đã cố định.
4. Kiểm tra cấu trúc expression theo allowlist.
5. Kiểm tra biến được tham chiếu có trong schema.
6. Kiểm tra property và method theo policy.
7. Kiểm tra kiểu đầu vào và kiểu kết quả dự kiến.
8. Đánh giá test cases bằng context giới hạn.
9. Lưu source, version, policy version và người tạo.
10. Chỉ kích hoạt rule sau khi validation thành công.

Nếu cần duyệt cấu trúc expression, có thể xây một AST validator deny-by-default gắn với phiên bản Spring cụ thể. Validator phải duyệt đệ quy mọi node, bao gồm node lồng trong toán tử, function call, collection operation và subexpression.

Không dùng regex đơn giản để tìm từ khóa như new, T( hoặc @. Các ký tự có thể xuất hiện trong string literal, nested expression hoặc cú pháp khác; regex không thể thay thế việc phân tích cấu trúc. Parser thành công cũng không có nghĩa expression được phép.

AST API và các node implementation có thể thay đổi theo phiên bản Spring. Hãy version hóa validator, kiểm thử khi nâng cấp framework và từ chối node chưa được nhận diện.

## 8. Allowlist biến và kiểu dữ liệu đầu vào

Biến phải được khai báo trước theo một schema. Ví dụ:

| Tên biến | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| minimumTotal | BigDecimal | Có | Ngưỡng tổng tiền |
| requiredStatus | OrderStatus | Có | Trạng thái bắt buộc |
| allowedRegions | Set<String> | Không | Các khu vực được chấp nhận |

Expression chỉ được tham chiếu tên biến trong schema. Nếu có biến không tồn tại, từ chối rule ở bước validation thay vì chờ tới runtime mới phát sinh lỗi.

Trước khi đăng ký biến:

- Xác thực kiểu dữ liệu.
- Kiểm tra null theo policy.
- Kiểm tra miền giá trị.
- Giới hạn kích thước collection và String.
- Chuẩn hóa enum, mã vùng và định dạng.
- Không truyền secret hoặc object có quyền rộng.
- Không lấy tên biến từ client để tạo quyền truy cập động.

Ví dụ đăng ký dữ liệu đã xác thực:

~~~java
context.setVariable("minimumTotal", validatedMinimumTotal);
context.setVariable("requiredStatus", validatedStatus);
context.setVariable("allowedRegions", immutableAllowedRegions);
~~~

Dùng collection bất biến hoặc bản sao chỉ đọc nếu expression không cần thay đổi dữ liệu. Không chia sẻ object mutable giữa các request hoặc tenant.

## 9. Giới hạn collection operation và độ phức tạp

Selection và projection hữu ích nhưng có thể xử lý nhiều phần tử hoặc lồng nhiều tầng:

~~~text
#root.orders.?[#this.total >= #minimumTotal].![#this.id]
~~~

Nếu collection lớn hoặc expression lồng sâu, chi phí có thể tăng đáng kể. Hãy xác định:

- Collection tối đa có thể đưa vào context.
- Độ sâu collection operation được phép.
- Số lượng node trong AST.
- Độ sâu lồng expression.
- Độ dài String và số phần tử có thể xử lý.
- Số lần evaluate đồng thời.
- Những method được gọi trong predicate có chi phí thế nào.

Không cho phép method có thể tải dữ liệu từ database hoặc gọi dịch vụ từ xa trong mỗi vòng lặp. Chuẩn bị dữ liệu cần thiết trước khi evaluate và truyền vào DTO giới hạn.

Cân nhắc từ chối regex matches do người dùng tự viết nếu không có kiểm soát pattern và input. Một regular expression có backtracking xấu có thể tiêu thụ CPU lớn. Nếu nghiệp vụ cần tìm kiếm pattern, hãy giới hạn pattern và input hoặc dùng cơ chế matching có đặc tính thời gian phù hợp.

SpEL không cung cấp một giới hạn thời gian thực thi tổng quát để biến expression tùy ý thành an toàn. Giới hạn độ dài, node, collection và concurrency là các lớp kiểm soát bổ sung; nếu cần deadline cứng cho input không đáng tin, hãy cân nhắc đánh giá trong một tiến trình hoặc sandbox được cô lập có giới hạn tài nguyên.

## 10. Giới hạn parser và compiler

Dùng parser configuration cố định và được quản lý tập trung. Không để người dùng chọn tùy ý parser mode, class loader hoặc các tùy chọn làm thay đổi khả năng expression.

Đối với expression không đáng tin cậy:

- Giữ compiler OFF trừ khi có lý do, benchmark và kiểm thử cụ thể.
- Không xem compiler là biện pháp bảo mật.
- Không cho phép người dùng thay đổi class loader.
- Không bật auto-grow nếu rule không cần tạo hoặc mở rộng cấu trúc dữ liệu.
- Không thay parser configuration theo từng source do client gửi.
- Ghi nhận phiên bản Spring và policy dùng để parse.

Compilation có thể dựa vào kiểu runtime đã quan sát và không hỗ trợ mọi cấu trúc expression. Bật compiler không làm giới hạn property, method hoặc side effect; allowlist vẫn phải được áp dụng độc lập.

## 11. Tách authorization khỏi expression

Allowlist cú pháp không phải cơ chế phân quyền nghiệp vụ. Một expression có thể được giới hạn chỉ đọc nhưng vẫn trả về dữ liệu mà caller không được phép xem nếu root object chứa quá nhiều thông tin.

Các kiểm tra authorization phải được thực hiện ở tầng ứng dụng:

- Caller có quyền tạo, sửa, xem hoặc kích hoạt rule không?
- Rule thuộc tenant hoặc module nào?
- Caller có quyền evaluate rule đó không?
- Root object có thuộc phạm vi tenant hiện tại không?
- Các biến được truyền có được phép dùng trong ngữ cảnh đó không?
- Kết quả có được phép trả về cho caller không?

Không để expression tự quyết định quyền truy cập dữ liệu bằng cách kiểm tra một biến do chính caller kiểm soát. Backend phải xác thực tenant, user và quyền trước khi tạo context.

Dùng DTO theo quyền và phạm vi dữ liệu. Nếu caller chỉ được xem một phần Order, hãy đưa vào context một DTO đã lọc phần dữ liệu đó thay vì entity đầy đủ.

## 12. Xử lý lỗi và thông báo cho người dùng

Validation nên từ chối expression không được phép trước khi kích hoạt. Thông báo cho người dùng cần chỉ ra vị trí và loại lỗi ở mức đủ hữu ích, nhưng không tiết lộ class nội bộ, stack trace, tên bean, cấu trúc hệ thống hoặc dữ liệu nhạy cảm.

Có thể phân loại:

- Cú pháp không hợp lệ.
- Node hoặc toán tử không nằm trong allowlist.
- Biến không được khai báo.
- Property không được phép.
- Method/function không được phép.
- Kiểu đầu vào không hợp lệ.
- Expression vượt giới hạn tài nguyên.
- Evaluation thất bại với dữ liệu hiện tại.

Ở log nội bộ, ghi rule ID, version, policy version, message code, vị trí và cause class. Không log toàn bộ root object, giá trị biến nhạy cảm hoặc source nếu source có thể chứa dữ liệu riêng tư.

Không tự chuyển mọi lỗi thành false hoặc null. Một expression bị từ chối vì policy cần được phân biệt với expression hợp lệ trả về false.

## 13. Version hóa policy và thu hồi quyền

Allowlist sẽ thay đổi theo thời gian. Khi thêm property, method hoặc toán tử, các expression cũ có thể bắt đầu có thêm quyền nếu được đánh giá theo policy mới.

Hãy quản lý version cho:

- Source expression.
- Allowlist policy.
- Root DTO schema.
- Function và method registry.
- Parser configuration.
- Phiên bản Spring Framework.

Mỗi lần evaluate nên biết expression version và policy version nào được áp dụng. Nếu policy bị thu hẹp, hãy rà soát các rule đã lưu và từ chối hoặc yêu cầu chỉnh sửa những rule không còn hợp lệ.

Khi cần thu hồi:

1. Vô hiệu hóa rule hoặc policy version cũ.
2. Invalidate parsed Expression cache liên quan.
3. Ngăn request mới dùng rule đã bị thu hồi.
4. Ghi nhận các lần evaluate bị từ chối.
5. Chạy validation lại với policy mới.
6. Phát hành version rule đã được xác nhận.

Không để cache giữ expression đã được parse hoặc xác thực dưới policy cũ rồi tiếp tục dùng sau khi quyền bị thu hẹp.

## 14. Cache và cách ly tenant

Nếu cache parsed Expression, cache key cần bao gồm source hoặc hash source, rule version, parser configuration và policy version. Khi policy thay đổi, entry cũ phải được invalidated hoặc tách namespace.

Với hệ thống multi-tenant:

- Không dùng cache key chỉ dựa trên tên rule nếu các tenant có source hoặc policy khác nhau.
- Xác thực quyền truy cập rule trước khi lấy entry từ cache.
- Tách namespace theo tenant khi cần.
- Không đưa root object, biến request hoặc EvaluationContext vào cache.
- Không cache kết quả nếu chưa xác định mọi dependency.
- Dùng bounded cache để tránh source mới liên tục làm tăng bộ nhớ.

Expression cache chỉ lưu logic đã parse. Mỗi lần evaluate vẫn phải tạo context với root object, biến và dữ liệu của caller hiện tại.

## 15. Ví dụ pipeline validation

Một service có thể gom các bước kiểm tra vào một nơi:

~~~java
public ValidatedRule validate(
        String source,
        RulePolicy policy) {

    if (source == null || source.length() > policy.maxLength()) {
        throw new InvalidRuleException("Expression length is invalid");
    }

    Expression expression = parser.parseExpression(source);

    astAllowlistValidator.validate(expression, policy);

    variableSchemaValidator.validate(expression, policy.variables());

    return new ValidatedRule(
        expression,
        policy.version()
    );
}
~~~

Đây là cấu trúc minh họa. astAllowlistValidator và variableSchemaValidator là thành phần của ứng dụng cần được triển khai, kiểm thử và gắn với phiên bản Spring cụ thể; SpEL parser không tự cung cấp một policy allowlist hoàn chỉnh.

Khi evaluate:

~~~java
public Object evaluate(
        ValidatedRule rule,
        RuleInput input) {

    authorize(input.caller(), rule);

    SimpleEvaluationContext context =
        contextFactory.createReadOnlyContext(input);

    return rule.expression().getValue(context);
}
~~~

Context factory chỉ đưa vào dữ liệu được phép. Việc authorize được thực hiện trước evaluation và không phụ thuộc vào expression.

## 16. Kiểm thử allowlist

Bộ test cần bao gồm cả expression được phép và expression bị từ chối. Chỉ kiểm tra happy path không chứng minh policy có hiệu lực.

### Positive tests

- Literal và toán tử đã duyệt.
- Property nằm trong allowlist.
- Biến có trong schema.
- Method hoặc function đã được duyệt nếu policy cho phép.
- Selection/projection nếu được phép và dữ liệu trong giới hạn.
- Root DTO đúng kiểu.
- Kết quả có kiểu dự kiến.

### Negative tests

- Property không được phép.
- Biến không khai báo.
- Method không nằm trong registry.
- Gọi method có side effect.
- Type reference bằng T(...).
- Constructor bằng new.
- Bean reference bằng @beanName.
- Assignment hoặc expression thay đổi state.
- Truy cập reflection, class loader, runtime hoặc system properties.
- Collection operation vượt giới hạn.
- Regex hoặc input vượt giới hạn nếu pattern matching bị hạn chế.
- AST node không được nhận diện.
- Source quá dài hoặc lồng quá sâu.
- Caller không có quyền dùng rule hoặc tenant khác.

### Kiểm thử vận hành

- Policy version mới thu hồi được expression cũ.
- Cache không dùng entry đã xác thực bằng policy cũ.
- Hai tenant không dùng nhầm rule hoặc cache entry của nhau.
- Context mới không giữ biến của request trước.
- Lỗi validation không kích hoạt evaluation.
- Log và thông báo không làm lộ dữ liệu nội bộ.
- Nâng cấp Spring không vô tình mở rộng tập node được chấp nhận.

## 17. Quy trình triển khai allowlist

1. **Xác định nhu cầu.** Kiểm tra có thể dùng rule có sẵn, tham số hoặc builder có cấu trúc thay cho SpEL tự do không.
2. **Định nghĩa policy.** Liệt kê literal, toán tử, biến, property, method và collection operation được phép.
3. **Tạo input DTO.** Chỉ đưa dữ liệu cần thiết và đã được lọc theo quyền.
4. **Cấu hình context giới hạn.** Ưu tiên SimpleEvaluationContext và accessor/resolver allowlist.
5. **Parse và validate.** Dùng AST policy deny-by-default gắn với phiên bản Spring cụ thể.
6. **Kiểm tra schema.** Xác nhận root type, biến và result type.
7. **Áp dụng giới hạn tài nguyên.** Giới hạn source, AST, collection, concurrency và input size.
8. **Kiểm tra authorization.** Xác nhận caller, tenant và quyền sử dụng rule.
9. **Kiểm thử.** Chạy positive, negative, boundary, concurrency và tenant isolation tests.
10. **Version hóa và phát hành.** Lưu source, policy version và audit metadata.
11. **Theo dõi và thu hồi.** Đo lỗi, thời gian đánh giá và invalidate khi policy thay đổi.

## 18. Thực hành tốt

- Ưu tiên rule có sẵn, tham số hoặc builder có cấu trúc thay cho SpEL tự do.
- Dùng deny-by-default; chỉ mở cú pháp cần thiết.
- Ưu tiên SimpleEvaluationContext với property access giới hạn.
- Mặc định từ chối method invocation; nếu cần, dùng MethodResolver allowlist.
- Chỉ truyền DTO chỉ đọc và biến đã xác thực.
- Từ chối type reference, constructor, bean reference và assignment.
- Không đưa service, repository, ApplicationContext hoặc entity có quyền rộng vào root/variables.
- Không cho phép method có side effect hoặc I/O.
- Dùng AST validation thay vì regex tìm chuỗi nguy hiểm.
- Gắn AST validator với phiên bản Spring và từ chối node chưa biết.
- Giới hạn source length, AST depth, collection size và concurrency.
- Không giả định SpEL có execution timeout tích hợp.
- Giữ compiler OFF trừ khi đã có benchmark và kiểm thử cụ thể.
- Tách authorization khỏi expression.
- Version hóa source, policy, schema và parser configuration.
- Cache có giới hạn và invalidate khi policy thay đổi.
- Ghi audit metadata nhưng không log secret hoặc dữ liệu nhạy cảm.

## 19. Checklist review

Trước khi cho phép một expression do người dùng cung cấp chạy trong ứng dụng, hãy kiểm tra:

- [ ] Đã xác nhận SpEL tự do thực sự cần thiết.
- [ ] Policy deny-by-default được định nghĩa và version hóa.
- [ ] Tập node, toán tử và cấu trúc được phép có danh sách rõ.
- [ ] Root object là DTO giới hạn, không phải service/entity có quyền rộng.
- [ ] Property access được giới hạn theo allowlist.
- [ ] Method invocation mặc định bị từ chối hoặc dùng resolver allowlist.
- [ ] Function được công bố riêng lẻ và có hợp đồng rõ.
- [ ] Type reference, constructor, bean reference và assignment bị từ chối.
- [ ] Biến có schema, kiểu, null policy và miền giá trị.
- [ ] AST được duyệt đệ quy; node không nhận diện bị từ chối.
- [ ] Không dùng regex thay cho AST validation.
- [ ] Source, collection, AST và concurrency có giới hạn.
- [ ] Không có method I/O hoặc side effect trong expression.
- [ ] Authorization và tenant isolation được thực hiện ở tầng ứng dụng.
- [ ] EvaluationContext không chứa dữ liệu hoặc quyền thừa.
- [ ] Cache key bao gồm source/version và policy/parser configuration.
- [ ] Policy change thu hồi/invalidate expression cũ.
- [ ] Có positive, negative, boundary và isolation tests.
- [ ] Log và lỗi trả về không tiết lộ dữ liệu nội bộ.

## Kết luận

Expression do người dùng cung cấp phải được xem là đầu vào có thể thực thi. Một allowlist an toàn bắt đầu bằng deny-by-default, giới hạn cú pháp, property, method và dữ liệu; dùng EvaluationContext có quyền tối thiểu; parse rồi kiểm tra AST trước khi evaluate; và tách authorization khỏi logic expression. Ưu tiên DTO chỉ đọc, từ chối type reference, constructor, bean reference và side effect, đồng thời giới hạn kích thước và độ phức tạp của input. Version hóa policy, cách ly tenant, quản lý cache và kiểm thử cả trường hợp được phép lẫn bị từ chối để policy tiếp tục có hiệu lực khi ứng dụng và Spring Framework thay đổi.