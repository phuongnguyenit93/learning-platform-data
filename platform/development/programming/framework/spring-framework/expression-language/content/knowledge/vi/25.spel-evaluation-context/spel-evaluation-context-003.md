# Root object, variables và bean resolver trong EvaluationContext của SpEL

EvaluationContext là nơi cung cấp dữ liệu và các cơ chế mà Spring Expression Language (SpEL) cần khi đánh giá một expression. Trong đó, **root object** là đối tượng mặc định để tra cứu property; **variables** là các giá trị được đăng ký và tham chiếu bằng tiền tố `#`; **BeanResolver** giúp expression lấy bean theo tên bằng cú pháp `@beanName`.

Ba nguồn dữ liệu này có mục đích khác nhau. Phân biệt chúng rõ ràng giúp expression dễ đọc, dễ kiểm thử và giới hạn đúng những object hoặc service mà biểu thức được phép sử dụng.

## 1. EvaluationContext cung cấp gì?

Khi parse một chuỗi SpEL, parser tạo ra một Expression. Khi đánh giá Expression, SpEL nhận EvaluationContext để biết cách truy cập object và xử lý các thao tác trong biểu thức.

EvaluationContext có thể cung cấp:

- Root object và active context object.
- Variables và functions.
- PropertyAccessor để đọc hoặc ghi property.
- MethodResolver để tìm method cần gọi.
- BeanResolver để resolve bean theo tên.
- TypeLocator để tìm class trong type reference.
- TypeConverter để chuyển đổi kiểu.
- OperatorOverloader để tùy chỉnh một số phép toán.

Không phải mọi expression đều cần tất cả thành phần này. Một biểu thức chỉ đọc property đơn giản có thể chỉ cần root object; biểu thức dùng biến cần variables; biểu thức có `@beanName` cần BeanResolver.

## 2. Thiết lập root object

Root object là điểm bắt đầu khi SpEL tra cứu property hoặc gọi method mà không có target được chỉ rõ. Với StandardEvaluationContext, có thể truyền root object ngay khi tạo context:

    Order order = loadOrder();

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    String status = parser.parseExpression("status")
            .getValue(context, String.class);

Trong ví dụ này, `status` được tra cứu trên object `order`. Không cần viết `#order.status` vì order đang là root object.

Có thể thay root object sau khi tạo context:

    context.setRootObject(anotherOrder);

Các lần đánh giá tiếp theo trên context đó sẽ sử dụng root object mới. Nếu context được tái sử dụng, hãy chú ý trạng thái root hiện tại để tránh một expression vô tình chạy trên object của lần xử lý trước.

Cũng có thể truyền root object trực tiếp khi gọi `getValue` bằng overload phù hợp. Dù dùng cách nào, hãy xác định rõ object nào là root trong từng lần đánh giá.

## 3. Phân biệt #root và #this

SpEL cung cấp hai biến đặc biệt:

- `#root` luôn tham chiếu root object ban đầu của lần đánh giá.
- `#this` tham chiếu active context object tại vị trí expression đang được đánh giá.

Ở cấp ngoài, `#this` thường trùng với root object. Khi expression đi vào collection selection hoặc projection, active context object chuyển sang phần tử đang được xử lý, còn `#root` vẫn giữ nguyên.

Ví dụ:

    #root.items.?[
        price >= #root.minimumPrice
    ]

Trong predicate:

- `#this` là item hiện tại.
- `price` được tra cứu trên item hiện tại.
- `#root.minimumPrice` được đọc từ root object ban đầu.

Có thể viết rõ:

    #root.items.?[
        #this.price >= #root.minimumPrice
    ]

Dùng `#root` khi cần quay lại object gốc từ bên trong collection expression; dùng `#this` khi muốn chỉ rõ object hiện tại.

## 4. Đăng ký và truy cập variables

Variables là các giá trị được ứng dụng đưa vào EvaluationContext. Với StandardEvaluationContext, dùng `setVariable(name, value)` để đăng ký:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("discountRate", new BigDecimal("0.10"));
    context.setVariable("region", "VN");

Trong expression, tham chiếu biến bằng tiền tố `#`:

    #discountRate
    #region
    total * (1 - #discountRate)

Ví dụ kết hợp root property với variable:

    total * (1 - #discountRate)

Ở đây `total` được đọc từ root object, còn `#discountRate` được lấy từ variable trong context.

Có thể đăng ký một object làm variable:

    context.setVariable("customer", customer);

    #customer.name
    #customer.getDisplayName()

Variable có thể là String, số, Boolean, collection hoặc object domain. Chọn kiểu dữ liệu phù hợp và validate dữ liệu đầu vào trong Java trước khi đưa vào context.

## 5. Property, variable và bean reference khác nhau

Ba cú pháp dưới đây không thể thay thế tùy ý cho nhau:

| Cú pháp | Nguồn dữ liệu | Cách cung cấp |
|---|---|---|
| `status` | Property trên root hoặc active context object | Đặt root object và cấu hình PropertyAccessor |
| `#order` | Variable tên order | `context.setVariable("order", order)` |
| `@orderService` | Bean tên orderService trong Spring container | Cấu hình BeanResolver |

Ví dụ:

    status == 'PAID'
    #order.status == 'PAID'
    @orderPolicy.isAllowed(#order)

Dòng đầu đọc property `status` trên root object. Dòng thứ hai đọc biến `order`, rồi truy cập property của object đó. Dòng thứ ba resolve bean `orderPolicy` và gọi method trên bean.

Nếu expression báo không tìm thấy property hoặc variable, hãy kiểm tra đúng nguồn tham chiếu: root object, variable hay bean. Đừng thêm tiền tố `#` hoặc `@` chỉ để thử ngẫu nhiên; mỗi tiền tố có một cơ chế resolve riêng.

## 6. Cấu hình BeanResolver để dùng @beanName

Một StandardEvaluationContext được tạo độc lập không tự biết Spring ApplicationContext. Muốn dùng cú pháp `@beanName`, cần đăng ký BeanResolver.

Spring cung cấp `BeanFactoryResolver` để kết nối EvaluationContext với BeanFactory:

    ConfigurableApplicationContext applicationContext =
            ...;

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setBeanResolver(
            new BeanFactoryResolver(
                    applicationContext.getBeanFactory()
            )
    );

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal total = parser.parseExpression(
            "@pricingService.calculateTotal(#root)"
    ).getValue(context, BigDecimal.class);

Khi đánh giá, BeanFactoryResolver tìm bean `pricingService` theo tên. Expression có thể đọc property hoặc gọi method trên bean sau khi resolve thành công.

Nếu không có BeanResolver, một context tự tạo sẽ không thể resolve `@pricingService`. Việc tạo SpelExpressionParser không tự động liên kết parser với BeanFactory.

## 7. Kết hợp root object, variables và bean resolver

Một expression có thể sử dụng cả ba nguồn trong cùng một lần đánh giá:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "discountRate",
            new BigDecimal("0.05")
    );

    context.setVariable("customer", customer);

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal discount = parser.parseExpression(
            "@pricingService.calculateDiscount(" +
            "#root.total, #customer.level, #discountRate)"
    ).getValue(context, BigDecimal.class);

Trong ví dụ:

- `#root` là order được truyền khi tạo context.
- `#customer` và `#discountRate` là variables được đăng ký.
- `@pricingService` là bean được resolve từ BeanFactory.

Đối số được đánh giá trong context hiện tại trước khi method được gọi. Kiểu đối số và chữ ký method phải tương thích; TypeConverter của context có thể hỗ trợ chuyển đổi khi cần.

## 8. Bean reference khác với variable chứa service

Có thể đưa một service vào context dưới dạng variable:

    context.setVariable("pricingService", pricingService);

    #pricingService.calculateTotal(#root)

Cách này khác với bean reference:

    @pricingService.calculateTotal(#root)

Dạng `#pricingService` lấy object từ variables. Dạng `@pricingService` yêu cầu BeanResolver tìm bean theo tên trong container.

Dùng variable khi ứng dụng muốn cung cấp object cụ thể cho một lần đánh giá hoặc context riêng. Dùng bean reference khi muốn expression sử dụng component do Spring quản lý. Không đăng ký cùng một object theo nhiều cách nếu điều đó khiến người đọc khó biết expression đang dùng nguồn nào.

## 9. StandardEvaluationContext và SimpleEvaluationContext

StandardEvaluationContext cung cấp tập tính năng SpEL đầy đủ hơn, bao gồm khả năng làm việc với property, method, type, constructor và bean resolver khi được cấu hình. Đây là lựa chọn linh hoạt cho expression nội bộ đáng tin cậy.

SimpleEvaluationContext giới hạn tập tính năng để phù hợp hơn với data binding và các use case cần quyền hạn hẹp. Nó không hỗ trợ type reference, constructor invocation hoặc bean reference. Instance method invocation cũng không được bật mặc định; có thể cấu hình rõ qua builder bằng `withInstanceMethods()` khi use case cần.

Ví dụ context chỉ đọc:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

Context này phù hợp khi expression chỉ cần đọc dữ liệu qua data binding. Nếu expression cần `@beanName`, phải dùng một loại EvaluationContext hỗ trợ BeanResolver và cấu hình quyền truy cập có chủ đích.

Không nên chuyển sang StandardEvaluationContext chỉ để làm cho expression chạy được nếu biểu thức đến từ người dùng hoặc nguồn không hoàn toàn tin cậy. Hãy chọn context theo đúng capability cần cung cấp.

## 10. Cô lập context theo từng lần xử lý

Expression đã parse có thể được tái sử dụng, nhưng dữ liệu trong EvaluationContext có thể thay đổi. Root object, variables và resolver là một phần cấu hình hoặc trạng thái của context.

Trong ứng dụng xử lý nhiều request, nên tạo context phù hợp cho từng request hoặc từng use case:

    EvaluationContext createContext(
            Order order,
            Customer customer,
            BeanFactory beanFactory) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable("customer", customer);
        context.setBeanResolver(
                new BeanFactoryResolver(beanFactory)
        );

        return context;
    }

Đây là cấu trúc minh họa. Service tạo context cần xác thực rằng caller được phép truy cập order và customer tương ứng trước khi đưa chúng vào context.

Tránh thay root object hoặc variables trên một context dùng chung giữa các request đồng thời. Điều đó có thể khiến một lần đánh giá nhìn thấy dữ liệu của request khác. Giữ cấu hình context và dữ liệu theo đúng vòng đời của use case.

## 11. Giới hạn bean và dữ liệu được expose

BeanResolver có thể mở quyền truy cập tới các bean trong container. Nếu expression không hoàn toàn tin cậy, không nên mặc định expose toàn bộ BeanFactory mà không giới hạn.

Một số nguyên tắc:

- Chỉ cung cấp bean thật sự cần cho expression.
- Ưu tiên facade có API hẹp thay vì service lớn có nhiều method công khai.
- Không expose ApplicationContext hoặc BeanFactory như một object để expression tự khám phá dependency.
- Không đưa repository, payment service hoặc service quản trị vào context nếu use case không cần.
- Kiểm tra quyền truy cập dữ liệu trước khi đặt object vào root hoặc variables.
- Giới hạn method invocation, property access và assignment theo mục đích sử dụng.

Nếu chỉ cần một vài bean, có thể dùng BeanResolver tùy chỉnh để allowlist tên được resolve. Dù vậy, allowlist bean không thay thế việc giới hạn method và property trên object đã được expose.

## 12. Debug lỗi resolve root, variable và bean

Khi expression không resolve được một tham chiếu, hãy xác định đúng cơ chế đang được dùng:

1. Với property không có tiền tố, kiểm tra root object hoặc active context object và PropertyAccessor.
2. Với `#name`, kiểm tra variable đã được đăng ký bằng đúng tên chưa.
3. Với `@name`, kiểm tra BeanResolver đã được cấu hình và BeanFactory có bean hoặc alias tương ứng.
4. Với property lồng nhau, kiểm tra object trung gian có null không.
5. Với method trên bean hoặc variable, kiểm tra tên method, khả năng truy cập và kiểu đối số.

Có thể kiểm tra variable trong Java:

    Object customerValue = context.lookupVariable("customer");

    System.out.println(
            customerValue == null
                    ? "null"
                    : customerValue.getClass().getName()
    );

Với root object, kiểm tra object đã truyền vào context hoặc giá trị trả về từ `getRootObject()`. Với bean, kiểm tra BeanFactory và resolver ở tầng cấu hình thay vì đổi expression liên tục.

Không nên bắt mọi lỗi resolve rồi trả null như thể dữ liệu không tồn tại. Lỗi có thể đến từ context thiếu cấu hình, sai bean name hoặc lỗi khởi tạo bean; hãy giữ thông tin lỗi đủ để chẩn đoán.

## 13. Ghi nhớ

EvaluationContext cung cấp root object, variables và các resolver mà SpEL cần trong lúc đánh giá. Dùng tên property trực tiếp để truy cập root hoặc active context object; dùng `#variable` cho dữ liệu đăng ký bằng `setVariable`; dùng `@beanName` khi BeanResolver đã kết nối context với Spring container. `#root` giữ root object ban đầu, còn `#this` là active context object và có thể đổi trong collection expression. StandardEvaluationContext hỗ trợ nhiều tính năng hơn; SimpleEvaluationContext giới hạn capability cho data binding. Hãy tạo context theo use case, chỉ expose object và bean cần thiết, và xác thực quyền trước khi cung cấp dữ liệu cho expression.
