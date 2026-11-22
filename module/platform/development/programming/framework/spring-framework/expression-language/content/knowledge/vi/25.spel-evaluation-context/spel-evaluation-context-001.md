# StandardEvaluationContext và khả năng mở rộng

## 1. StandardEvaluationContext là gì?

Trong SpEL, parser chuyển chuỗi thành Expression, còn EvaluationContext cung cấp môi trường để expression được đánh giá. Context quyết định root object là gì, variable nào tồn tại và expression có thể truy cập property, gọi method, tìm bean, tạo object hoặc chuyển đổi kiểu bằng cơ chế nào.

StandardEvaluationContext là implementation đầy đủ tính năng của EvaluationContext. Nó phù hợp khi ứng dụng cần kiểm soát linh hoạt cách SpEL tương tác với object và các dịch vụ của ứng dụng.

Ví dụ cơ bản:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("minimum", 1000);
    context.setVariable("active", true);

    Expression expression = parser.parseExpression(
        "#active and #minimum >= 500"
    );

    Boolean result =
        expression.getValue(context, Boolean.class);

Expression được parse trước. Khi gọi getValue, SpEL đọc variables từ context, đánh giá các toán tử rồi trả về kết quả.

StandardEvaluationContext không phải parser và cũng không tự tạo expression. Nó là môi trường mà expression sử dụng trong giai đoạn evaluation.

## 2. Root object

Root object là object mặc định mà expression truy cập khi không dùng variable prefix hoặc bean reference.

Có thể truyền root object khi tạo context:

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

Hoặc thiết lập sau:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setRootObject(customer);

Nếu customer có property name và age, expression có thể viết:

    name
    age >= 18

Không cần viết #customer vì customer đang là root object.

Có thể đọc root object bằng API:

    Object root = context.getRootObject().getValue();

Nếu không đặt root object, expression vẫn có thể hoạt động với literal, variable hoặc bean reference đã cấu hình. Tuy nhiên, một property expression không có prefix cần có root object phù hợp để truy cập.

Hãy chọn root object có phạm vi dữ liệu vừa đủ. Nếu đưa một entity lớn hoặc service có nhiều method vào root, expression có thể nhìn thấy nhiều khả năng hơn nhu cầu thực tế.

## 3. Variables và functions

StandardEvaluationContext cho phép đăng ký variable bằng setVariable:

    context.setVariable("customerName", "Lan");
    context.setVariable("orderTotal", 1200);

Trong expression, tham chiếu variable bằng dấu #:

    #customerName
    #orderTotal >= 1000

Có thể cập nhật variable khi context còn được sử dụng:

    context.setVariable("orderTotal", 1500);

Khi expression được đánh giá lại, nó đọc giá trị hiện tại của variable trong context.

Function cũng được đăng ký trong namespace variable/function. StandardEvaluationContext cung cấp registerFunction để đăng ký Method hoặc MethodHandle:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

Gọi function:

    #normalizeCode('  vn  ')

Vì function và variable dùng chung namespace, không nên đặt cùng một tên cho cả hai.

## 4. Những khả năng mặc định của StandardEvaluationContext

StandardEvaluationContext cung cấp các cơ chế mặc định để SpEL làm việc với object Java.

| Thành phần | Trách nhiệm |
| --- | --- |
| PropertyAccessor | Đọc hoặc ghi property và field theo khả năng accessor |
| MethodResolver | Tìm method phù hợp để gọi |
| ConstructorResolver | Tìm constructor phù hợp để tạo object |
| BeanResolver | Tìm bean theo tên |
| TypeLocator | Tìm class theo tên trong type reference hoặc constructor expression |
| TypeConverter | Chuyển đổi giá trị giữa các kiểu |
| TypeComparator | So sánh hai giá trị |
| OperatorOverloader | Mở rộng cách xử lý một số toán tử |

StandardEvaluationContext sử dụng các implementation mặc định dựa trên reflection và cơ chế chuẩn của SpEL cho nhiều thao tác. Một số khả năng vẫn cần cấu hình tường minh: ví dụ, muốn dùng @beanName trong expression độc lập thì phải đăng ký BeanResolver phù hợp.

Có thể thay thế hoặc bổ sung các thành phần này khi hành vi mặc định không đáp ứng mô hình object hoặc quy tắc của ứng dụng.

## 5. PropertyAccessor: tùy chỉnh cách đọc và ghi property

PropertyAccessor chịu trách nhiệm truy cập property trên target object. ReflectivePropertyAccessor là accessor phổ biến để làm việc với JavaBean và field theo cơ chế reflection.

Ứng dụng có thể đăng ký accessor riêng:

    context.addPropertyAccessor(
        new CustomPropertyAccessor()
    );

Một PropertyAccessor tùy chỉnh thường cần xác định:

- Loại target object mà accessor hỗ trợ.
- Property nào có thể đọc.
- Cách lấy giá trị khi đọc.
- Property nào có thể ghi.
- Cách cập nhật giá trị khi ghi.

Các thao tác đọc và ghi được thể hiện qua canRead/read và canWrite/write.

Ví dụ, ứng dụng có một object cấu hình chỉ lưu dữ liệu trong một Map nội bộ. Custom accessor có thể ánh xạ tên property SpEL sang key tương ứng trong Map, thay vì yêu cầu object phải có getter cho từng key.

Hãy giới hạn accessor vào đúng loại target và property được phép. Một accessor quá rộng có thể làm expression truy cập các dữ liệu không nằm trong thiết kế ban đầu.

Nếu cần chỉ đọc, hãy không cho phép ghi hoặc chỉ đăng ký accessor có hành vi đọc. Việc đọc được property không đồng nghĩa property đó phải được phép sửa.

## 6. MethodResolver: kiểm soát lời gọi method

MethodResolver tìm method phù hợp với target object, tên method và các kiểu đối số.

StandardEvaluationContext mặc định có reflective method resolution. Có thể thêm resolver tùy chỉnh:

    context.addMethodResolver(
        new CustomMethodResolver()
    );

MethodResolver tùy chỉnh phù hợp khi ứng dụng muốn expose một API method giới hạn, ánh xạ lời gọi sang một thao tác khác hoặc áp dụng quy tắc chọn method đặc biệt.

Khi thiết kế resolver, cần xác định:

- Target class nào được hỗ trợ.
- Method name nào được phép.
- Số lượng và kiểu đối số.
- Cách chuyển đổi kiểu nếu có.
- MethodExecutor thực hiện lời gọi ra sao.
- Lỗi nào được trả về khi method không hợp lệ.

Không nên cho phép gọi mọi method chỉ vì target là một object Java. Một object có thể chứa method đọc dữ liệu, thay đổi trạng thái, truy cập file hoặc gọi hệ thống ngoài.

Nếu expression không cần method invocation, hãy giới hạn hoặc không cung cấp khả năng đó trong context.

## 7. ConstructorResolver: kiểm soát việc tạo object

ConstructorResolver tìm constructor phù hợp khi expression sử dụng toán tử new.

Ví dụ:

    new com.example.Customer('Lan', 30)

StandardEvaluationContext mặc định có reflective constructor resolution. Có thể thêm resolver tùy chỉnh:

    context.addConstructorResolver(
        new CustomConstructorResolver()
    );

Resolver tùy chỉnh có thể giới hạn class nào được tạo, constructor nào được gọi hoặc cách đối số được ánh xạ.

Điều này hữu ích khi ứng dụng cần một tập class được phép khởi tạo, hoặc cần áp dụng quy tắc tạo object riêng.

Nếu expression không cần tạo object, không cần expose constructor invocation. Với expression đến từ nguồn không tin cậy, khả năng gọi constructor có thể mở rộng đáng kể phạm vi hành động mà expression thực hiện được.

## 8. BeanResolver: kết nối expression với Spring container

BeanResolver cho phép expression tìm bean theo tên bằng cú pháp @beanName.

Ví dụ:

    @pricingService.calculate(#amount)

Khi tự tạo StandardEvaluationContext trong Java, cần đăng ký BeanResolver:

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

Sau đó expression có thể tham chiếu bean được quản lý bởi BeanFactory.

BeanResolver chỉ chịu trách nhiệm tìm bean. Việc đọc property hoặc gọi method trên bean vẫn dùng PropertyAccessor và MethodResolver tương ứng.

Không nên đưa toàn bộ ApplicationContext vào root object hoặc variable chỉ để expression có thể tìm dữ liệu. Hãy cấp bean resolver khi thực sự cần và kiểm soát bean nào expression có thể tham chiếu.

## 9. TypeLocator: kiểm soát cách tìm class

TypeLocator được dùng khi expression cần tham chiếu kiểu Java, ví dụ toán tử T() hoặc constructor expression new.

Ví dụ:

    T(java.math.BigDecimal)
    new java.util.ArrayList()

StandardTypeLocator là implementation chuẩn. Mặc định, package java.lang được nhận diện, nên có thể dùng tên ngắn cho một số class trong package đó.

Có thể đăng ký package import:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator();

    typeLocator.registerImport("com.example");

    context.setTypeLocator(typeLocator);

Sau đó expression có thể tham chiếu class trong package đã import bằng tên ngắn khi không có xung đột.

Có thể cung cấp ClassLoader phù hợp khi ứng dụng chạy trong môi trường có class loader riêng:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator(
            MyApplication.class.getClassLoader()
        );

    context.setTypeLocator(typeLocator);

TypeLocator tìm class; ConstructorResolver mới quyết định constructor nào được gọi khi dùng new. Hai thành phần này có trách nhiệm riêng.

## 10. TypeConverter: chuyển đổi giá trị

TypeConverter chuyển giá trị từ kiểu nguồn sang kiểu đích khi expression hoặc property access yêu cầu.

Ví dụ property age có kiểu int nhưng giá trị được truyền vào là chuỗi:

    context.setVariable("ageText", "30");

    Expression expression =
        parser.parseExpression("#ageText");

    Integer age =
        expression.getValue(context, Integer.class);

SpEL có thể dùng TypeConverter của context để chuyển đổi String thành Integer nếu conversion được hỗ trợ.

Có thể đăng ký TypeConverter tùy chỉnh:

    context.setTypeConverter(customTypeConverter);

Ứng dụng cũng có thể tích hợp ConversionService phù hợp thông qua StandardTypeConverter.

Khi tùy chỉnh converter, cần xác định kiểu nguồn, kiểu đích, quy tắc null, locale, format và hành vi khi dữ liệu không hợp lệ. Không nên chuyển đổi quá rộng khiến expression âm thầm chấp nhận dữ liệu sai định dạng.

## 11. TypeComparator và OperatorOverloader

TypeComparator quyết định cách so sánh hai giá trị trong những trường hợp SpEL cần so sánh các kiểu dữ liệu cụ thể.

Có thể đăng ký comparator tùy chỉnh:

    context.setTypeComparator(customTypeComparator);

Ví dụ, ứng dụng có một kiểu version riêng và cần quy tắc so sánh theo major/minor/patch thay vì so sánh chuỗi thông thường.

OperatorOverloader cho phép mở rộng hành vi của một số toán tử với kiểu dữ liệu tùy chỉnh.

Đăng ký:

    context.setOperatorOverloader(
        customOperatorOverloader
    );

Chỉ nên dùng các extension này khi kiểu dữ liệu hoặc quy tắc nghiệp vụ thực sự cần hành vi khác mặc định. Nếu dùng quá rộng, cùng một expression có thể mang ý nghĩa khác nhau giữa các context và khó debug.

Hãy ghi rõ quy tắc so sánh hoặc overload được hỗ trợ và kiểm thử với các giá trị biên.

## 12. Thứ tự và phạm vi của các extension

Một context có thể chứa nhiều PropertyAccessor hoặc MethodResolver. Việc chọn implementation phù hợp phụ thuộc vào target, tên property/method và khả năng hỗ trợ của từng thành phần.

Khi đăng ký nhiều extension:

- Chỉ thêm accessor/resolver cho loại object cần hỗ trợ.
- Tránh hai extension cùng nhận một target và cùng tuyên bố xử lý một property/method nếu không có lý do rõ ràng.
- Kiểm soát thứ tự trong danh sách accessor hoặc resolver được cấu hình.
- Xác định rõ extension nào xử lý trước và fallback nào được phép.
- Không thay đổi registry tùy tiện giữa các lần đánh giá.

Nếu custom accessor xử lý mọi target quá rộng, nó có thể chiếm các trường hợp vốn nên do accessor mặc định xử lý. Nếu custom resolver trả về executor cho method quá tổng quát, các lời gọi không mong muốn có thể được chấp nhận.

Thiết kế extension hẹp giúp hành vi dễ dự đoán và dễ kiểm thử.

## 13. Ví dụ cấu hình một context có nhiều khả năng

Ví dụ sau minh họa cách cấu hình root object, variable, function và bean resolver:

    ExpressionParser parser =
        new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext(orderFacts);

    context.setVariable("minimum", new BigDecimal("1000"));

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    Expression expression = parser.parseExpression(
        "total >= #minimum and " +
        "#normalizeCode(region) == 'VN'"
    );

    Boolean eligible =
        expression.getValue(context, Boolean.class);

Trong ví dụ:

- orderFacts là root object.
- minimum là variable.
- normalizeCode là function được đăng ký rõ ràng.
- BeanResolver được cấu hình để expression có thể tham chiếu bean nếu cần.

Ví dụ này minh họa khả năng mở rộng. Trong một rule chỉ cần root object, variable và function, không cần đăng ký BeanResolver chỉ vì context có thể hỗ trợ nó.

## 14. StandardEvaluationContext và SimpleEvaluationContext

StandardEvaluationContext hỗ trợ đầy đủ nhiều tính năng SpEL và phù hợp với expression do ứng dụng kiểm soát.

SimpleEvaluationContext được thiết kế cho data binding và property-based expression với tập tính năng giới hạn hơn.

| Tiêu chí | StandardEvaluationContext | SimpleEvaluationContext |
| --- | --- | --- |
| Root object | Có | Có |
| Variables | Có | Có |
| Property access | Có, linh hoạt | Có, theo cấu hình builder |
| Method invocation | Có qua resolver | Chỉ khi cấu hình cho phép |
| Bean references | Có khi đăng ký BeanResolver | Không hỗ trợ |
| Type references T() | Có | Không hỗ trợ |
| Constructor invocation new | Có | Không hỗ trợ |
| Customization | Nhiều resolver và strategy | Tập tính năng giới hạn hơn |

Nếu chỉ cần đọc property từ một DTO, hãy cân nhắc SimpleEvaluationContext read-only:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

Nếu cần bean reference, constructor invocation hoặc type reference, SimpleEvaluationContext không đáp ứng use case đó.

Không nên chọn StandardEvaluationContext chỉ vì nó có nhiều tính năng hơn. Chọn context theo đúng khả năng expression cần sử dụng.

## 15. Vòng đời và tái sử dụng context

StandardEvaluationContext là object có thể thay đổi: root object, variables và các resolver/accessor có thể được cập nhật.

Expression đã parse có thể được giữ lại để đánh giá nhiều lần:

    Expression rule =
        parser.parseExpression("#amount >= #minimum");

Mỗi lần đánh giá, context phải cung cấp dữ liệu phù hợp:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("amount", amount);
    context.setVariable("minimum", minimum);

    Boolean allowed =
        rule.getValue(context, Boolean.class);

Không nên chia sẻ một context mutable giữa nhiều request đồng thời nếu các request cùng cập nhật variables hoặc root object. Dữ liệu của request này có thể ghi đè dữ liệu của request khác.

Một cách tổ chức rõ ràng là giữ expression bất biến khi source không đổi, còn context chứa dữ liệu động được tạo theo request hoặc lần đánh giá.

Nếu muốn tái sử dụng context đã cấu hình sẵn, hãy tách rõ phần cấu hình bất biến khỏi state mutable và bảo đảm cách dùng phù hợp với concurrency.

## 16. Kiểm thử extension

Khi thêm PropertyAccessor, MethodResolver hoặc TypeConverter tùy chỉnh, hãy kiểm thử cả trường hợp thành công và thất bại.

Nên có các nhóm kiểm thử:

1. Target class được hỗ trợ và property/method hợp lệ.
2. Target class không được hỗ trợ.
3. Property hoặc method không tồn tại.
4. Đối số null hoặc sai kiểu.
5. Chuyển đổi kiểu hợp lệ và không hợp lệ.
6. Nhiều resolver cùng có khả năng xử lý một target.
7. Root object hoặc variable bị thiếu.
8. BeanResolver không được cấu hình hoặc bean name không tồn tại.
9. Các thao tác ghi bị từ chối trong context chỉ đọc.
10. Hai request đánh giá đồng thời với dữ liệu context khác nhau.

Hãy kiểm thử expression qua cả parse và getValue. Parse thành công không bảo đảm resolver có thể xử lý target ở runtime.

Khi custom extension thay đổi hành vi, kiểm thử trực tiếp hợp đồng của extension và expression sử dụng nó. Điều này giúp phát hiện lỗi cấu hình trước khi đưa rule vào production.

## 17. Bảo mật và nguyên tắc least privilege

StandardEvaluationContext mạnh vì nó có thể expose nhiều khả năng truy cập. Nếu expression đến từ nguồn không tin cậy, việc cung cấp root object hoặc resolver rộng có thể tạo ra rủi ro.

Các nguyên tắc:

- Không đánh giá expression không tin cậy bằng StandardEvaluationContext có đầy đủ quyền.
- Chỉ cung cấp root object hoặc DTO chứa dữ liệu cần thiết.
- Chỉ đăng ký variables và functions thực sự cần.
- Không đăng ký BeanResolver nếu expression không cần bean.
- Giới hạn PropertyAccessor và MethodResolver.
- Không expose ConstructorResolver hoặc TypeLocator rộng nếu không cần.
- Tránh method có side effect, I/O hoặc quyền quản trị trong context của rule.
- Dùng SimpleEvaluationContext cho trường hợp data binding giới hạn, đồng thời kiểm tra tất cả object và extension vẫn được expose.

SimpleEvaluationContext chỉ giới hạn tập tính năng của ngôn ngữ; nó không tự bảo vệ dữ liệu hoặc method có thể truy cập thông qua object, accessor, resolver, variable hay function được cung cấp.

Hãy xem mỗi extension là một quyền mà expression được cấp. Chỉ cấp quyền cần thiết cho đúng loại rule.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Property không đọc được | Chưa có accessor phù hợp hoặc getter không đúng | Kiểm tra target class và PropertyAccessor |
| Property không ghi được | Accessor không hỗ trợ write hoặc context chỉ đọc | Kiểm tra canWrite/write và cấu hình context |
| Method không tìm thấy | MethodResolver không chọn được method | Kiểm tra tên, đối số và resolver |
| Constructor không tìm thấy | TypeLocator hoặc ConstructorResolver không xử lý được class | Kiểm tra class name, ClassLoader và constructor |
| @beanName thất bại | Chưa đăng ký BeanResolver | Cấu hình BeanFactoryResolver nếu thực sự cần |
| T() không tìm thấy class | TypeLocator hoặc package import chưa phù hợp | Dùng tên đầy đủ hoặc cấu hình TypeLocator |
| Giá trị không chuyển đổi được | TypeConverter không hỗ trợ kiểu nguồn/đích | Kiểm tra conversion và format |
| So sánh cho kết quả không mong muốn | TypeComparator hoặc kiểu dữ liệu khác dự kiến | Kiểm tra kiểu thực tế và quy tắc so sánh |
| Toán tử không hoạt động với custom type | OperatorOverloader chưa được cấu hình | Đăng ký overloader có phạm vi rõ ràng |
| Rule có quyền truy cập ngoài dự kiến | Root object hoặc resolver quá rộng | Thu hẹp context và extension |

Khi debug, hãy xác định expression thất bại ở parse hay evaluation. Sau đó kiểm tra thành phần chịu trách nhiệm cho thao tác đang lỗi thay vì thay đổi toàn bộ context cùng lúc.

## 19. Những điểm cần nhớ

- StandardEvaluationContext là implementation đầy đủ tính năng của EvaluationContext.
- Root object cung cấp đối tượng mặc định cho property expression.
- Variables được tham chiếu bằng #name; functions được gọi bằng #functionName(...).
- PropertyAccessor đọc/ghi property; MethodResolver tìm method; ConstructorResolver tìm constructor.
- BeanResolver tìm bean; TypeLocator tìm class.
- TypeConverter chuyển đổi kiểu; TypeComparator so sánh giá trị; OperatorOverloader mở rộng toán tử.
- Có thể thêm hoặc thay thế extension theo nhu cầu ứng dụng.
- Thứ tự và phạm vi của accessor/resolver cần được kiểm soát khi có nhiều implementation.
- StandardEvaluationContext không tự đăng ký BeanResolver cho một context độc lập.
- SimpleEvaluationContext giới hạn tính năng và phù hợp hơn với data binding cần kiểm soát.
- Giữ Expression để tái sử dụng, nhưng quản lý context mutable theo request hoặc lần đánh giá.
- Không dùng StandardEvaluationContext để đánh giá expression không tin cậy; hãy giới hạn root object và mọi extension theo least privilege.

Khi mở rộng StandardEvaluationContext, hãy bắt đầu từ thao tác expression thực sự cần. Chọn đúng extension, giới hạn target và quyền của nó, rồi kiểm thử hành vi thành công lẫn thất bại. Một context nhỏ, rõ ràng giúp rule dễ bảo trì và dễ kiểm soát hơn.

## Tài liệu tham khảo

- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — EvaluationContext and Type Conversion: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html
- Spring Framework Javadoc — StandardEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html
- Spring Framework Javadoc — EvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html
