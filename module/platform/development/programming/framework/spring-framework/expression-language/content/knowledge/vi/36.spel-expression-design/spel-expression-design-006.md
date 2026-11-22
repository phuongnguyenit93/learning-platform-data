# Chuẩn hóa cách viết expression giữa các module

## Mục tiêu

Khi nhiều module cùng sử dụng Spring Expression Language (SpEL), mỗi module có thể tự hình thành cách đặt tên biến, viết điều kiện, xử lý null, cấu hình parser và kiểm thử expression. Nếu không có quy ước chung, cùng một quy tắc có thể được viết theo nhiều kiểu khác nhau, khiến việc review, bảo trì, nâng cấp Spring và chẩn đoán lỗi trở nên khó khăn.

Chuẩn hóa không có nghĩa mọi module phải dùng một expression giống nhau. Mục tiêu là thống nhất những phần có thể dùng chung: cú pháp, cách đặt tên, phạm vi dữ liệu, semantics của kiểu, cấu hình EvaluationContext, xử lý lỗi, bảo mật và quy trình kiểm thử. Mỗi module vẫn có thể có rule riêng, nhưng người đọc biết cách tìm root object, biến, function và hành vi null trong mọi expression.

Sau bài này, bạn có thể:

- Xây dựng quy ước chung cho SpEL trong nhiều module.
- Đặt tên expression, biến và function nhất quán.
- Viết expression rõ phạm vi root object và phần tử hiện tại.
- Thống nhất null handling, numeric semantics và conversion.
- Chuẩn hóa selection, projection, template và type reference.
- Dùng chung parser/context factory mà vẫn cô lập dữ liệu từng request.
- Quản lý function, bean reference và quyền truy cập có kiểm soát.
- Version hóa rule, cache Expression và kiểm thử theo cùng tiêu chuẩn.
- Đưa quy ước vào review, tài liệu và quy trình phát hành.

## 1. Nguyên tắc thiết kế chung

Một quy ước tốt cần giúp người đọc trả lời nhanh các câu hỏi:

1. Expression này phục vụ quy tắc nghiệp vụ nào?
2. Root object có kiểu gì và chứa dữ liệu nào?
3. Biến nào được cung cấp từ EvaluationContext?
4. Expression trả về kiểu gì?
5. Null và dữ liệu không hợp lệ được xử lý ra sao?
6. Function hoặc method nào được phép gọi?
7. Parser và EvaluationContext được cấu hình như thế nào?
8. Rule được version hóa, kiểm thử và thay đổi ở đâu?

Nên áp dụng các nguyên tắc sau:

- **Rõ nghĩa trước khi ngắn:** ưu tiên tên biến và expression dễ hiểu hơn cách viết ngắn nhưng mơ hồ.
- **Có kiểu rõ ràng:** xác định kiểu root, biến, đối số và kết quả.
- **Không có side effect:** expression chủ yếu đọc dữ liệu và tính toán.
- **Cấu hình tập trung:** parser và EvaluationContext được tạo qua cơ chế dùng chung.
- **Dữ liệu theo request được cô lập:** không chia sẻ context mutable giữa các request độc lập.
- **Có kiểm thử:** mỗi rule có test cho kết quả đúng, sai và các giá trị biên.
- **Có version:** source và cấu hình liên quan được quản lý để có thể truy vết.
- **Quyền tối thiểu:** chỉ cung cấp object, property, method và function mà rule cần.

## 2. Quy ước đặt tên và định danh expression

Mỗi expression nên có một định danh ổn định, mô tả module và mục đích nghiệp vụ. Không nên dùng toàn bộ source text làm tên hiển thị cho người vận hành.

Một mẫu định danh có thể là:

~~~text
<module>.<domain>.<rule-purpose>
~~~

Ví dụ:

~~~text
checkout.order.minimum-total
billing.invoice.tax-eligibility
catalog.product.visible-to-customer
shipping.address.serviceable
~~~

Quy ước đặt tên nên thống nhất:

- Dùng chữ thường và dấu chấm để phân cấp.
- Dùng từ thể hiện nghiệp vụ, tránh tên kỹ thuật chung chung như rule1 hoặc expressionA.
- Giữ ID ổn định qua các lần sửa source.
- Tăng version khi semantics hoặc source thay đổi.
- Ghi owner hoặc module chịu trách nhiệm cho rule.
- Không nhúng thông tin request, user hoặc tenant vào ID.
- Tách ID rule khỏi nội dung expression và khỏi cache key nội bộ.

Nếu hệ thống có nhiều tenant với rule riêng, namespace hoặc tenant ownership cần được quản lý ở tầng registry và quyền truy cập. Không dựa vào tên ID do client gửi để xác định quyền.

## 3. Quy ước định dạng expression

Expression nên được viết sao cho điều kiện có thể đọc và review độc lập. Với điều kiện dài, xuống dòng theo nhóm logic thay vì dồn toàn bộ vào một chuỗi khó đọc.

Ví dụ:

~~~text
#root.active
and #root.total.compareTo(#minimumTotal) >= 0
and #root.status == #requiredStatus
~~~

Quy ước định dạng:

- Mỗi điều kiện nghiệp vụ chính nằm trên một dòng khi expression dài.
- Dùng khoảng trắng quanh toán tử để dễ đọc.
- Dùng ngoặc khi thứ tự ưu tiên không hiển nhiên.
- Nhóm các điều kiện liên quan bằng dòng và chú thích trong tài liệu đi kèm.
- Tránh lồng quá nhiều ternary hoặc toán tử logic trong một expression.
- Tránh lặp cùng một điều kiện dài ở nhiều vị trí.
- Không chèn comment vào giữa expression nếu cú pháp hoặc nơi lưu không hỗ trợ comment.
- Không dùng ký tự viết tắt không được giải thích trong tên biến.
- Dùng một kiểu quote thống nhất cho string literal trong SpEL.

Ví dụ có nhóm điều kiện:

~~~text
(
    #root.active
    and #root.status == #requiredStatus
)
and #root.total.compareTo(#minimumTotal) >= 0
~~~

Nếu expression dài tới mức phải đọc nhiều lần mới hiểu, hãy chuyển một phần logic sang function thuần có tên mô tả hoặc chia rule thành các bước có tên trong Java. Không cố giữ toàn bộ logic trong một chuỗi chỉ vì SpEL có thể biểu diễn được.

## 4. Quy ước root object và phạm vi #this

Mỗi module nên xác định một root model có cấu trúc rõ ràng cho nhóm rule của mình. Tài liệu rule cần ghi root type, các property được phép đọc và kiểu kết quả dự kiến.

Dùng **#root** khi muốn tham chiếu rõ dữ liệu gốc:

~~~text
#root.order.total >= #minimumTotal
~~~

Dùng **#this** khi cần chỉ rõ object hiện tại trong collection operation:

~~~text
#root.orders.?[
    #this.active and #this.total >= #minimumTotal
]
~~~

Trong collection selection hoặc projection, #this là phần tử hiện tại của operation đó. Khi lồng collection operation, #this chuyển theo tầng đang xử lý. Vì vậy:

- Dùng #root cho dữ liệu gốc cần giữ tham chiếu xuyên suốt expression.
- Dùng #this cho phần tử đang được selection hoặc projection xử lý.
- Không dựa vào property trần khi expression có nhiều tầng và phạm vi có thể gây nhầm lẫn.
- Ghi rõ kiểu phần tử tại mỗi tầng khi expression lồng nhau.
- Tránh đổi ý nghĩa root object giữa các phiên bản của cùng rule ID.

Ví dụ collection lồng nhau:

~~~text
#root.departments.![ 
    #this.employees.?[
        #this.active and #this.salary >= #minimumSalary
    ].![#this.name]
]
~~~

Kết quả là danh sách tên nhân viên theo từng phòng ban; projection lồng nhau giữ cấu trúc danh sách con. Không giả định kết quả tự động được flatten.

## 5. Quy ước tên và kiểu biến

Biến từ EvaluationContext phải có tên nhất quán giữa nơi đăng ký và nơi sử dụng. Khi gọi setVariable(), truyền tên không có dấu #; trong expression, tham chiếu bằng #name.

Ví dụ:

~~~java
context.setVariable("minimumTotal", minimumTotal);
context.setVariable("requiredStatus", OrderStatus.APPROVED);
context.setVariable("allowedRegions", allowedRegions);
~~~

Expression:

~~~text
#root.total >= #minimumTotal
and #root.status == #requiredStatus
and #allowedRegions.contains(#root.region)
~~~

Quy ước đặt tên:

- Dùng lowerCamelCase.
- Tên thể hiện ý nghĩa nghiệp vụ, không chỉ kiểu dữ liệu.
- Thêm đơn vị hoặc phạm vi khi có thể gây nhầm lẫn: minimumTotal, maximumAge, timeoutSeconds.
- Dùng enum thay cho chuỗi trạng thái nếu model có enum phù hợp.
- Dùng BigDecimal cho giá trị tiền hoặc số thập phân cần độ chính xác.
- Dùng collection có generic type rõ ràng.
- Tránh tên quá chung như value, data, x hoặc limit nếu có nhiều giá trị cùng loại.
- Quản lý tên biến tập trung bằng constant hoặc một parameter object có schema rõ.

Mỗi rule nên khai báo danh sách biến đầu vào, kiểu, trạng thái bắt buộc/tùy chọn và ý nghĩa null. Không để người vận hành phải suy ra các biến cần thiết chỉ bằng cách đọc source expression.

## 6. Quy ước null handling

Các module cần thống nhất null có nghĩa gì trước khi viết expression. Null có thể là dữ liệu không hợp lệ, trạng thái chưa có, hoặc một giá trị tùy chọn. Không nên để từng expression tự ngầm chọn một cách xử lý khác nhau.

Một số quy tắc cần ghi rõ:

- Root object có được phép null không?
- Property trung gian có được phép null không?
- Collection null được xem là rỗng hay là lỗi?
- Phần tử null trong collection có được phép không?
- Biến tùy chọn null có nghĩa bỏ qua điều kiện hay không?
- Getter hoặc function có thể trả null không?

Ví dụ kiểm tra customer có thể null:

~~~text
#root.customer?.active == true
~~~

Nếu null phải bị từ chối, biểu thức có thể thể hiện rõ:

~~~text
#root.customer != null and #root.customer.active
~~~

Với collection có thể null, xác định chính sách trước khi dùng selection. Null-safe collection operations phụ thuộc phiên bản Spring; hãy xác nhận phiên bản framework được module hỗ trợ trước khi dùng cú pháp đó.

Không dùng safe navigation để che giấu lỗi property không tồn tại hoặc model sai. Safe navigation chỉ xử lý target null ở vị trí được áp dụng.

## 7. Quy ước numeric và conversion

Các module phải thống nhất cách xử lý số, đặc biệt khi expression liên quan đến tiền, tỷ lệ, giới hạn và thời gian.

Khuyến nghị:

- Dùng BigDecimal cho tiền và phép tính thập phân cần chính xác.
- Không trộn String, Integer, Double và BigDecimal trong cùng một rule nếu không có quy tắc conversion rõ.
- So sánh BigDecimal theo giá trị số bằng compareTo khi scale không thuộc contract.
- Xác định rounding mode và scale ở tầng nghiệp vụ.
- Dùng kiểu đích rõ khi gọi getValue(context, TargetType.class).
- Dùng ConversionService chung của ứng dụng khi rule cần conversion.
- Đăng ký custom Converter qua cấu hình tập trung.
- Validate dữ liệu trước khi evaluate nếu định dạng có ràng buộc nghiệp vụ.

Ví dụ so sánh số tiền:

~~~text
#root.total.compareTo(#minimumTotal) >= 0
~~~

Không dựa vào conversion ngầm để biến một chuỗi tùy ý thành số tiền. Nếu dữ liệu đầu vào là String, hãy parse và validate tại ranh giới ứng dụng rồi truyền BigDecimal đã chuẩn hóa vào context.

## 8. Quy ước collection operations

Các module nên dùng nhất quán cú pháp selection và projection:

- **.?[predicate]** lọc phần tử.
- **.![projection]** chuyển mỗi phần tử thành kết quả.
- **.^[predicate]** lấy phần tử đầu tiên khớp.
- **.$[predicate]** lấy phần tử cuối cùng khớp.

Ví dụ selection:

~~~text
#root.orders.?[#this.active]
~~~

Ví dụ projection:

~~~text
#root.orders.![#this.id]
~~~

Ví dụ lấy phần tử đầu tiên:

~~~text
#root.orders.^[#this.status == #requiredStatus]
~~~

Quy ước sử dụng:

- Predicate trả về Boolean rõ ràng.
- Không gọi function có side effect trong selection/projection.
- Xác định kiểu phần tử collection.
- Xác định hành vi với collection rỗng và null.
- Không giả định projection lồng nhau tự flatten.
- Không phụ thuộc thứ tự của Set hoặc Map nếu implementation không bảo đảm.
- Với lọc, nhóm, sắp xếp hoặc flatten phức tạp, cân nhắc thực hiện trong Java.

Nếu collection chứa nhiều loại phần tử, hãy chuẩn hóa model hoặc dùng điều kiện kiểm tra kiểu rõ ràng. Đừng để một expression chung dựa trên các property chỉ tồn tại ở một số phần tử mà không có quy tắc bảo vệ.

## 9. Quy ước function và method call

Function được đăng ký trong EvaluationContext thường nên là public static method nhỏ, có chữ ký ổn định và tên mô tả hành vi.

Ví dụ:

~~~java
context.registerFunction(
    "normalizeCode",
    TextFunctions.class.getMethod("normalizeCode", String.class)
);
~~~

Gọi trong expression:

~~~text
#normalizeCode(#root.code)
~~~

Quy ước:

- Tên function dùng lowerCamelCase và mô tả hành vi.
- Đối số và kiểu trả về phải rõ ràng.
- Function nên thuần: cùng input cho cùng output, không thay đổi trạng thái bên ngoài.
- Hành vi null phải được định nghĩa.
- Không dùng function static để giữ dependency hoặc thay thế Spring service.
- Không gọi method có side effect trong expression.
- Chỉ đăng ký function mà module thực sự cần.
- Dùng context factory để đăng ký function nhất quán.

Nếu cần repository, API client, transaction hoặc logic nhiều bước, hãy chuyển sang service Java được Spring quản lý. SpEL nên kết hợp dữ liệu và điều kiện; không nên trở thành nơi điều phối toàn bộ luồng nghiệp vụ.

## 10. Quy ước bean reference và type reference

Bean reference bằng @beanName có thể làm expression phụ thuộc vào container và bean resolver:

~~~text
@taxPolicy.currentRate
~~~

Chỉ dùng khi module có nhu cầu rõ ràng và context hỗ trợ BeanResolver. Nếu mục đích chỉ là inject bean vào một property, ưu tiên cơ chế dependency injection thông thường.

Type reference dùng T(...) để truy cập static member hoặc enum:

~~~text
T(java.math.RoundingMode).HALF_UP
~~~

Quy ước:

- Dùng fully qualified class name cho class ngoài java.lang.
- Không đăng ký import prefix riêng lẻ ở nhiều module mà không có quy ước chung.
- Hạn chế bean reference trong rule nghiệp vụ nếu có thể truyền dữ liệu cần thiết qua biến.
- Không dùng static method có side effect.
- Ghi nhận dependency của rule vào bean hoặc class bên ngoài.
- Chỉ bật type/bean resolution khi EvaluationContext và nguồn expression được kiểm soát.

## 11. Quy ước template expression

Nếu expression trộn văn bản tĩnh với nội dung động, hãy xác định rõ template mode và delimiter.

Mặc định:

~~~text
Hello, #{#customerName}!
~~~

Có thể dùng TemplateParserContext hoặc ParserContext.TEMPLATE_EXPRESSION. Nếu nội dung thường xuyên chứa prefix #{ như văn bản literal, chọn delimiter tùy chỉnh và ghi nhận delimiter trong metadata của rule.

Phân biệt:

- Template delimiter #{...} dùng để đánh dấu expression block.
- String literal bên trong SpEL dùng dấu nháy theo cú pháp SpEL.
- XML/JSON/Java string có quy tắc escaping riêng.
- Property placeholder và SpEL là hai cơ chế khác nhau.

Không giả định backslash là cách escape delimiter của template nếu ParserContext không định nghĩa quy tắc đó. Template do người dùng cung cấp vẫn thực thi SpEL bên trong expression block; delimiter tùy chỉnh không phải cơ chế bảo mật.

## 12. Parser configuration và EvaluationContext factory

Các module nên dùng parser factory hoặc registry chung để cấu hình:

- Compiler mode.
- Compiler class loader.
- ParserContext cho template.
- Auto-grow behavior nếu cần.
- Các giới hạn cấu hình phù hợp với phiên bản Spring.

Tương tự, dùng EvaluationContext factory để cấu hình nhất quán:

- PropertyAccessor.
- MethodResolver.
- ConstructorResolver nếu thực sự cần.
- TypeLocator.
- TypeConverter/ConversionService.
- BeanResolver nếu được phép.
- Function registrations.

Ví dụ cấu trúc tạo context:

~~~java
public StandardEvaluationContext createContext(
        Object rootObject,
        RuleParameters parameters) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

    context.setVariable("minimumTotal", parameters.minimumTotal());
    context.setVariable("requiredStatus", parameters.requiredStatus());
    context.setTypeConverter(
        new StandardTypeConverter(applicationConversionService)
    );

    registerApprovedFunctions(context);
    return context;
}
~~~

Đây là cấu trúc minh họa; tên method, parameter object và API cần điều chỉnh theo Java/Spring version của dự án.

Cấu hình chung nên ổn định, còn root object và biến thuộc request phải được tạo riêng cho lần đánh giá. Không cache context mutable có dữ liệu request trong singleton hoặc cache dùng chung.

## 13. Quy ước compiler và hiệu năng

Compiler của SpEL có thể tăng tốc một số expression, nhưng dựa vào kiểu runtime quan sát được và không hỗ trợ mọi cấu trúc expression.

Quy ước chung nên là:

- Mặc định giữ compiler OFF nếu chưa có benchmark và yêu cầu rõ.
- Chỉ bật compilation cho expression được hỗ trợ và có kiểu runtime ổn định.
- Dùng IMMEDIATE khi muốn lỗi compiled evaluation được trả về caller.
- Dùng MIXED khi fallback về interpreter là chấp nhận được.
- Không đặt side effect trong expression có thể bị MIXED đánh giá lại.
- Cấu hình compiler class loader có thể nhìn thấy các kiểu liên quan.
- Đo parse time và evaluate time riêng.
- Không giả định mọi expression đều được compile chỉ vì compiler mode đã bật.

Nếu một module cần compiler mode khác, ghi rõ lý do, phạm vi rule và test tương ứng. Tránh để các module tự chọn compiler mode mà không có tài liệu vì hành vi lỗi và hiệu năng có thể khác nhau.

## 14. Cache và version hóa rule

Parsed Expression có thể được cache khi source được dùng lặp lại. Cache key cần phân biệt ít nhất:

- Rule ID.
- Rule version hoặc source hash.
- ParserContext/delimiter.
- Parser configuration identity.
- Compiler mode và class loader nếu ảnh hưởng tới expression.

Dùng bounded cache nếu số lượng rule có thể tăng. Có chính sách invalidation khi source, version hoặc cấu hình thay đổi.

Không cache EvaluationContext chứa root object và biến request. Không cache kết quả evaluate nếu chưa xác định đủ mọi dependency như input, user, tenant, thời gian, bean state và configuration.

Khi rule thay đổi:

1. Tạo version mới hoặc invalidate entry cũ.
2. Parse source mới bằng parser configuration hiện hành.
3. Kiểm tra expression và metadata.
4. Chạy bộ test rule.
5. Phát hành version mới theo quy trình.
6. Ghi nhận version đã được dùng trong lần evaluate để truy vết.

## 15. Bảo mật và giới hạn quyền

Expression có thể đọc property, gọi method, tham chiếu type, bean, function hoặc constructor tùy EvaluationContext. Vì vậy, việc cung cấp context là quyết định về quyền.

Các module cần thống nhất:

- Nguồn nào được phép tạo hoặc sửa expression.
- Ai có quyền kích hoạt version rule.
- Object và biến nào được phép đưa vào context.
- PropertyAccessor và MethodResolver nào được đăng ký.
- Có cho phép type reference, constructor hoặc bean reference không.
- Function nào được công bố.
- Expression có được phép gọi method có side effect không.
- Giới hạn source length, số rule và thời gian xử lý nếu phù hợp.

Ưu tiên context có quyền tối thiểu. Dùng SimpleEvaluationContext khi tập thao tác giới hạn đáp ứng nhu cầu; dùng StandardEvaluationContext khi cần tính năng rộng hơn và có kiểm soát.

Không coi việc đổi delimiter, dùng fully qualified name hoặc cache expression là biện pháp bảo mật. Nếu expression không đáng tin cậy, hãy giới hạn cả khả năng parser/context và nguồn dữ liệu.

## 16. Chuẩn kiểm thử chung

Mỗi module nên có cùng nhóm kiểm thử cơ bản:

- Parse thành công với parser configuration thực tế.
- Kết quả đúng cho input hợp lệ.
- Kết quả sai khi điều kiện không thỏa.
- Giá trị đúng bằng ngưỡng và sát ngưỡng.
- Null ở root, property trung gian, biến và phần tử collection.
- Conversion thành công và thất bại.
- Collection rỗng, một phần tử, nhiều phần tử và thứ tự.
- Function/method thiếu, sai kiểu hoặc ném exception.
- Context mới không giữ state của request trước.
- Expression version mới không dùng cache entry cũ.
- Quyền truy cập không vượt quá cấu hình.
- Kết quả SpEL được đối chiếu với logic Java tham chiếu độc lập.

Với rule quan trọng, viết Java reference hoặc expected value độc lập để phát hiện expression diễn đạt sai nghiệp vụ. Không viết Java reference chỉ gọi lại SpEL expression.

Có thể dùng parameterized test để chạy nhiều bộ dữ liệu trên cùng expression. Với miền dữ liệu rộng, dùng differential testing và lưu input/seed khi phát hiện sai khác.

## 17. Quy ước xử lý lỗi và logging

Mỗi module nên xử lý lỗi theo cùng một cấu trúc:

1. Phân biệt parse error và evaluation error.
2. Ghi nhận rule ID và version.
3. Ghi nhận message code và vị trí expression nếu có.
4. Xác định loại thao tác: property, method, constructor hay conversion.
5. Giữ cause chain để chẩn đoán.
6. Chuyển lỗi kỹ thuật thành lỗi nghiệp vụ ở ranh giới phù hợp.
7. Không nuốt exception rồi trả null/false nếu đó không phải contract.

Log nên có correlation ID, rule ID/version, kiểu root và thông tin lỗi cần thiết. Không log password, token, object graph hoặc toàn bộ biến có thể chứa dữ liệu nhạy cảm.

Không phụ thuộc vào toàn bộ message text của exception để điều khiển logic. Message wording có thể thay đổi giữa phiên bản Spring; message code và loại exception thường hữu ích hơn cho phân loại.

## 18. Mẫu metadata cho một expression

Ngoài source, nên lưu metadata tối thiểu để module khác có thể hiểu và vận hành rule.

Ví dụ cấu trúc:

~~~yaml
id: checkout.order.minimum-total
version: 3
module: checkout
description: Order must be active and meet the configured minimum total.
rootType: com.example.checkout.Order
resultType: java.lang.Boolean
variables:
  minimumTotal:
    type: java.math.BigDecimal
    required: true
  requiredStatus:
    type: com.example.checkout.OrderStatus
    required: true
nullPolicy: required-values-must-not-be-null
parser:
  mode: standard-expression
  compiler: off
functions: []
owner: checkout-team
~~~

Đây là metadata minh họa, không phải định dạng bắt buộc của Spring. Dự án có thể dùng database, YAML, JSON hoặc một registry khác, nhưng nên lưu đủ thông tin để validate và trace rule.

Không lưu secret hoặc giá trị request trong metadata. Metadata mô tả contract và cấu hình; dữ liệu thực tế được truyền qua EvaluationContext khi đánh giá.

## 19. Quy trình đưa expression mới vào module

1. **Mô tả rule:** ghi mục đích, owner, root type và result type.
2. **Khai báo input:** liệt kê biến, kiểu, required/optional và null policy.
3. **Viết expression:** theo quy ước tên, format và phạm vi #root/#this.
4. **Xác định capability:** property, method, function, type hoặc bean reference cần thiết.
5. **Dùng factory chung:** tạo parser và EvaluationContext theo cấu hình module.
6. **Kiểm tra bảo mật:** chỉ cung cấp dữ liệu và quyền cần thiết.
7. **Viết test:** happy path, negative path, null, conversion, collection và Java reference.
8. **Version hóa:** lưu source cùng metadata và version.
9. **Phát hành:** invalidate cache phù hợp và ghi nhận version mới.
10. **Theo dõi:** quan sát lỗi, thời gian evaluate và thay đổi rule.

## 20. Checklist review liên module

Trước khi merge hoặc phát hành expression, hãy kiểm tra:

- [ ] Rule có ID, owner và version rõ ràng.
- [ ] Root type và result type được ghi nhận.
- [ ] Biến có tên, kiểu và required/null policy.
- [ ] #root và #this được dùng đúng phạm vi.
- [ ] Expression được format theo quy ước chung.
- [ ] Null handling nhất quán với contract.
- [ ] Numeric type, precision và rounding rõ ràng.
- [ ] ConversionService và custom converter được cấu hình tập trung.
- [ ] Selection/projection có kết quả và ordering được xác định.
- [ ] Function thuần, không có side effect ngoài ý muốn.
- [ ] Bean/type/constructor access chỉ bật khi cần.
- [ ] Parser và EvaluationContext factory được dùng đúng.
- [ ] Context request không bị chia sẻ hoặc cache.
- [ ] Compiler mode có lý do và test phù hợp.
- [ ] Cache key phản ánh source/version/parser configuration.
- [ ] Invalidation khi rule hoặc configuration thay đổi.
- [ ] Có Java reference hoặc expected value độc lập.
- [ ] Có test null, conversion, collection, exception và concurrency phù hợp.
- [ ] Logging không làm lộ dữ liệu nhạy cảm.
- [ ] Metadata và tài liệu vận hành được cập nhật.

## Kết luận

Chuẩn hóa SpEL giữa các module cần một bộ quy ước thống nhất về định danh rule, định dạng expression, tên biến, phạm vi #root/#this, null, conversion, collection, function và quyền truy cập. Parser configuration và EvaluationContext factory nên được quản lý tập trung, trong khi dữ liệu root và biến của từng request phải được cô lập. Cache parsed Expression theo source/version và cấu hình parser; kiểm thử bằng Java reference độc lập; version hóa và invalidate khi rule thay đổi. Khi các module cùng tuân theo một contract rõ ràng, expression dễ review, vận hành và nâng cấp hơn mà vẫn giữ được sự linh hoạt cho từng miền nghiệp vụ.