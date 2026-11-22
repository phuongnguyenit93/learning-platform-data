# Khoanh vùng property path dài bằng expression nhỏ hơn

## 1. Vì sao nên chia nhỏ property path?

Một SpEL expression có thể truy cập nhiều property liên tiếp:

    customer.profile.address.city

Nếu expression này hoạt động sai, chỉ nhìn thông báo lỗi cuối cùng có thể chưa đủ để biết object hoặc property nào gây ra vấn đề.

Đường dẫn có thể thất bại vì nhiều nguyên nhân khác nhau:

- Một object trung gian là null.
- Property không tồn tại hoặc không thể đọc.
- Getter ném exception.
- PropertyAccessor không hỗ trợ kiểu object hiện tại.
- Giá trị trả về có kiểu khác với kiểu mà bước tiếp theo mong đợi.
- Index hoặc Map key không hợp lệ.
- Method trong đường dẫn không tìm thấy hoặc không thực hiện được.
- Dữ liệu lazy-loaded chưa sẵn sàng hoặc việc truy cập kích hoạt thêm thao tác ngoài dự kiến.

Cách debug hiệu quả là chia đường dẫn thành các bước nhỏ, đánh giá từng bước và quan sát giá trị cùng kiểu dữ liệu trung gian.

Thay vì chỉ chạy:

    customer.profile.address.city

hãy kiểm tra lần lượt:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

Bước đầu tiên trả về object Customer, bước tiếp theo trả về Profile, rồi Address, cuối cùng là city. Điểm đầu tiên thất bại hoặc trả về null thường giúp khoanh vùng nguyên nhân.

## 2. Phân biệt lỗi parsing và lỗi evaluation

Trước khi chia nhỏ path, hãy xác định expression lỗi ở giai đoạn nào.

**Parsing** xảy ra khi parser phân tích source:

    Expression expression =
        parser.parseExpression("customer.profile.address.city");

Nếu cú pháp không hợp lệ, parseExpression có thể ném ParseException. Khi đó chưa có Expression hợp lệ để gọi getValue.

**Evaluation** xảy ra khi expression truy cập dữ liệu:

    Object city = expression.getValue(context);

Nếu source hợp lệ nhưng customer hoặc profile là null, hoặc property không đọc được, lỗi xuất hiện khi evaluation và thường được báo bằng EvaluationException hoặc một subtype của nó.

Ví dụ:

    customer.profile.address.city

có thể parse thành công nhưng thất bại khi chạy vì customer.profile trả về null.

Không nên thay đổi cú pháp khi nguyên nhân thực sự là dữ liệu runtime. Hãy kiểm tra parse và evaluation như hai bước riêng.

## 3. Tạo danh sách prefix từ đường dẫn

Với property path đơn giản, hãy viết các prefix tăng dần theo thứ tự truy cập:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

Đánh giá từng prefix với cùng root object và EvaluationContext:

    ExpressionParser parser =
        new SpelExpressionParser();

    String[] prefixes = {
        "customer",
        "customer.profile",
        "customer.profile.address",
        "customer.profile.address.city"
    };

    for (String source : prefixes) {
        try {
            Expression expression =
                parser.parseExpression(source);

            Object value =
                expression.getValue(context, rootObject);

            String typeName = value == null
                ? "<null>"
                : value.getClass().getName();

            log.debug(
                "SpEL prefix [{}] returned type [{}]",
                source,
                typeName
            );
        }
        catch (ParseException ex) {
            log.warn(
                "Cannot parse SpEL prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
            break;
        }
        catch (EvaluationException ex) {
            log.warn(
                "Cannot evaluate SpEL prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
            break;
        }
    }

Khi một prefix thất bại, dừng tại đó và kiểm tra object được truy cập ở bước tương ứng.

Trong ví dụ, mỗi prefix được đánh giá từ cùng root object. Vì vậy, các getter ở những bước trước có thể được gọi lại nhiều lần. Cách này phù hợp để chẩn đoán khi property access có tính đọc ổn định, không tốn kém và không có side effect.

Nếu getter có thể thay đổi state, kích hoạt I/O hoặc lazy loading, hãy ưu tiên cách đánh giá tăng dần ở phần tiếp theo để tránh gọi lặp lại.

## 4. Đánh giá tăng dần trên object trung gian

Với đường dẫn chỉ gồm các property đơn giản, có thể đánh giá từng property trên kết quả của bước trước.

Ví dụ:

    Object current = rootObject;

    String[] properties = {
        "customer",
        "profile",
        "address",
        "city"
    };

    for (String property : properties) {
        if (current == null) {
            log.warn(
                "Stop before property [{}]: previous value is null",
                property
            );
            break;
        }

        try {
            Expression step =
                parser.parseExpression(property);

            current = step.getValue(context, current);

            String typeName = current == null
                ? "<null>"
                : current.getClass().getName();

            log.debug(
                "Property [{}] returned type [{}]",
                property,
                typeName
            );
        }
        catch (ParseException | EvaluationException ex) {
            log.warn(
                "Property step [{}] failed: {}",
                property,
                ex.getMessage()
            );
            break;
        }
    }

Cách này giữ nguyên EvaluationContext nhưng truyền object trung gian làm root object cho bước kế tiếp.

Ưu điểm là mỗi property trong chuỗi được đọc một lần. Khi một bước trả về null, vòng lặp dừng trước khi cố truy cập property tiếp theo.

Phương pháp này phù hợp với property path đơn giản. Nếu đường dẫn có indexer, method invocation, selection, projection hoặc toán tử, hãy chia thành các fragment SpEL hợp lệ thay vì coi mọi thành phần đều là tên property đơn.

## 5. Khi path bắt đầu bằng variable

Nếu expression sử dụng variable, bước đầu tiên cần lấy variable từ context.

Ví dụ expression ban đầu:

    #order.customer.profile.address.city

Có thể kiểm tra theo prefix:

    #order
    #order.customer
    #order.customer.profile
    #order.customer.profile.address
    #order.customer.profile.address.city

Hoặc lấy object từ variable rồi đánh giá tăng dần:

    Object current =
        parser.parseExpression("#order")
            .getValue(context);

    String[] properties = {
        "customer",
        "profile",
        "address",
        "city"
    };

    for (String property : properties) {
        if (current == null) {
            break;
        }

        current = parser
            .parseExpression(property)
            .getValue(context, current);

        log.debug(
            "Step [{}] type [{}]",
            property,
            current == null
                ? "<null>"
                : current.getClass().getName()
        );
    }

Điều quan trọng là variable #order phải được đăng ký trong đúng EvaluationContext đang dùng cho expression gốc.

Nếu thay context bằng một context mới không có variable, custom accessor hoặc converter cần thiết, kết quả debug có thể khác với lỗi ban đầu.

## 6. Giữ nguyên EvaluationContext và root object

Khi chia expression thành các phần nhỏ, hãy giữ các yếu tố runtime giống với lần evaluation ban đầu:

- Cùng root object hoặc đúng object trung gian.
- Cùng variables và functions.
- Cùng PropertyAccessor và MethodResolver.
- Cùng TypeConverter và TypeLocator nếu expression cần chúng.
- Cùng BeanResolver nếu expression tham chiếu bean.
- Cùng cấu hình parser liên quan đến null-safe navigation hoặc auto-grow.

Ví dụ, expression gốc chạy trên StandardEvaluationContext có custom PropertyAccessor. Nếu debug bằng một context mới chỉ có accessor mặc định, một property có thể đọc được ở lần chạy gốc nhưng thất bại trong bước debug.

Không nên thay đổi đồng thời root object, context và expression rồi kết luận đã tìm được nguyên nhân. Thay đổi từng yếu tố sẽ giúp so sánh có ý nghĩa hơn.

## 7. Kiểm tra null ở từng tầng

Với đường dẫn:

    customer.profile.address.city

hãy xác định giá trị nào là null:

    customer
    customer.profile
    customer.profile.address

Nếu customer là null, lỗi xảy ra ngay khi truy cập profile.

Nếu customer tồn tại nhưng profile là null, bước address là nơi thất bại.

Nếu address là null, bước city là nơi thất bại.

Có thể dùng null-safe navigation:

    customer?.profile?.address?.city

Cách viết này cho phép expression trả về null khi một receiver được bảo vệ là null.

Tuy nhiên, kết quả cuối cùng null không cho biết tầng nào null. Khi cần chẩn đoán, hãy kiểm tra từng prefix hoặc từng object trung gian.

Null-safe operator bảo vệ thao tác ngay sau nó. Nếu một bước phía sau vẫn dùng navigation thông thường trên receiver null, expression vẫn có thể thất bại.

## 8. Kiểm tra kiểu dữ liệu sau mỗi bước

Một prefix có thể đánh giá thành công nhưng trả về kiểu khác với giả định của người viết expression.

Ví dụ:

    customer.profile
    customer.profile.address

Có thể profile trả về Map thay vì class Profile, hoặc address trả về một proxy thay vì class Address dự kiến.

Hãy kiểm tra kiểu runtime:

    Object value =
        parser.parseExpression("customer.profile")
            .getValue(context, rootObject);

    if (value != null) {
        log.debug(
            "Runtime type: {}",
            value.getClass().getName()
        );
    }

Kiểu runtime giúp phát hiện:

- Property trả về implementation khác dự kiến.
- Collection chứa kiểu phần tử khác.
- Map được dùng thay cho JavaBean.
- Proxy hoặc wrapper được trả về.
- Getter trả về null hoặc object thay thế.

Khi dùng getValue không chỉ định desired result type, bạn có thể quan sát object thực tế trước khi yêu cầu TypeConverter chuyển nó sang kiểu đích. Điều này tránh nhầm lỗi property access với lỗi chuyển đổi kiểu.

Không nên log toàn bộ object hoặc gọi toString() trên object chưa rõ nguồn gốc. Chỉ log tên kiểu và metadata không nhạy cảm.

## 9. Property của JavaBean và key của Map

Một path dài có thể đi qua cả JavaBean và Map. Cú pháp truy cập cần phù hợp với cấu trúc thực tế.

JavaBean property:

    customer.address.city

Map key:

    #payload['customer']
    #payload['customer']['address']
    #payload['customer']['address']['city']

Nếu key chứa dấu chấm:

    #payload['user.profile']

thì dấu chấm nằm bên trong key string, không phải dấu phân tách property path.

Khi nghi ngờ một bước sai, hãy kiểm tra target có phải Map không và key có tồn tại không. Không mặc định mọi dấu chấm đều là property của JavaBean.

Với Map, indexer thể hiện rõ việc truy cập theo key. Với List hoặc array, indexer truy cập theo vị trí.

## 10. Khoanh vùng indexer trong path

Ví dụ:

    order.items[2].product.category.name

Có thể chia theo các prefix:

    order
    order.items
    order.items[2]
    order.items[2].product
    order.items[2].product.category
    order.items[2].product.category.name

Kiểm tra riêng collection trước khi truy cập index:

    #items.size()
    #items.isEmpty()

Nếu index là 2, List phải có ít nhất ba phần tử. Null-safe indexer chỉ bảo vệ trường hợp receiver null; nó không biến index vượt giới hạn thành null.

Nếu path dùng Map key, kiểm tra key tồn tại và đúng kiểu:

    #payload.containsKey('customer')
    #payload['customer']

Khi indexer lỗi, xác định receiver là null, collection rỗng, index ngoài phạm vi hay key không tồn tại. Đây là những nguyên nhân khác nhau và cần cách xử lý khác nhau.

## 11. Khoanh vùng method invocation

Property path có thể chứa method call:

    order.customer.getProfile().getAddress().getCity()

Nếu lỗi xuất hiện ở một method, hãy tách theo từng lời gọi:

    order.customer
    order.customer.getProfile()
    order.customer.getProfile().getAddress()
    order.customer.getProfile().getAddress().getCity()

Kiểm tra:

- Method có tồn tại trên kiểu runtime không?
- Số lượng và kiểu tham số có phù hợp không?
- Method có trả về null không?
- Method có ném exception không?
- Method có side effect hoặc gọi I/O không?
- MethodResolver nào đang xử lý lời gọi?

Nếu method ném exception, hãy xem cause của EvaluationException thay vì chỉ nhìn position của node method call.

Tránh gọi lại method có side effect trong quá trình debug. Với method tốn kém hoặc không thuần, hãy lưu kết quả một lần ở Java rồi kiểm tra object trả về.

## 12. Đừng tách expression bằng cách split dấu chấm

Không nên dùng:

    String[] parts = source.split("\\.");

Dấu chấm không phải lúc nào cũng là dấu phân tách property.

Ví dụ:

    #settings['user.profile']
    T(java.lang.Math).max(1, 5)
    #customer.calculateTax(10.5)
    #message == 'profile.city'

Trong các biểu thức này, dấu chấm có thể nằm trong Map key, tên package/class, method path hoặc string literal. Decimal number và các cấu trúc lồng nhau cũng làm việc tách chuỗi thủ công dễ sai.

SpEL là một ngôn ngữ có grammar. Cách an toàn là tự xác định các bước có ý nghĩa theo cấu trúc expression, hoặc dùng parser cho từng fragment hợp lệ.

Không dựa vào việc đếm dấu chấm để suy ra AST hoặc property path.

## 13. Template, selection và projection cần được chia theo cấu trúc

Một expression có thể chứa selection hoặc projection:

    orders.?[customer.profile.active == true].![customer.name]

Không nên tách chuỗi này thành các đoạn theo dấu chấm. Cần xác định riêng:

- Source collection orders.
- Predicate bên trong selection.
- Property path được đánh giá trên từng phần tử.
- Projection expression được áp dụng cho các phần tử đã chọn.

Có thể debug source collection trước:

    orders

Sau đó kiểm tra predicate trên một phần tử đại diện:

    customer.profile.active == true

Cuối cùng kiểm tra projection trên một phần tử:

    customer.name

Nếu expression nằm trong template block, hãy giữ nguyên thông tin về delimiter và fragment được parse. Một lỗi trong inner expression có thể báo position tương đối với fragment thay vì toàn bộ template.

## 14. Dùng exception position để chọn prefix cần kiểm tra

Nếu evaluation ném SpelEvaluationException, có thể lấy message code, position và expression source:

    try {
        expression.getValue(context);
    }
    catch (SpelEvaluationException ex) {
        log.warn(
            "Code={}, position={}, source={}",
            ex.getMessageCode(),
            ex.getPosition(),
            ex.getExpressionString()
        );
    }

Position là offset trong expression source, không phải trực tiếp là tên property hoặc số dòng. Nó có thể giúp xác định vùng cần xem xét, nhưng không phải lúc nào cũng đánh dấu toàn bộ token gây lỗi.

Hãy dùng position như manh mối để chọn prefix cần kiểm tra, sau đó xác nhận bằng cách đánh giá các bước nhỏ.

Nếu source hoặc position không có, dùng expression gốc mà ứng dụng giữ lại và kiểm tra từng bước theo cấu trúc đã biết.

## 15. Tránh đánh giá lặp lại getter có side effect

Khi kiểm tra prefix từ đầu mỗi lần, getter ở phần đầu có thể được gọi nhiều lần.

Ví dụ:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

Lần đánh giá cuối có thể gọi lại getCustomer(), getProfile() và getAddress() sau khi các prefix trước đã gọi chúng.

Điều này có thể gây vấn đề nếu getter:

- Kích hoạt lazy loading.
- Gọi database hoặc service ngoài.
- Đọc dữ liệu từ file hoặc network.
- Thay đổi cache hoặc state.
- Ném exception theo điều kiện runtime.

Với path property đơn giản, cách đánh giá tăng dần trên object trung gian giúp tránh lặp lại getter ở các tầng trước.

Với method có side effect, không nên gọi lại chỉ để debug. Hãy dùng fixture, mock, spy hoặc ghi nhận kết quả một lần ở tầng Java phù hợp.

## 16. Kiểm tra lazy loading và proxy

Trong ứng dụng dùng ORM, property access có thể đi qua proxy hoặc lazy relationship.

Ví dụ:

    order.customer.profile.address.city

Việc đọc customer hoặc profile có thể kích hoạt truy vấn database. Nếu persistence context đã đóng, evaluation có thể thất bại dù path và property name đều đúng.

Khi debug, kiểm tra:

- Runtime class có phải proxy không?
- Quan hệ nào đang lazy?
- Có session/entity manager hợp lệ tại thời điểm evaluation không?
- Có truy vấn bổ sung nào được phát sinh cho mỗi property không?
- Path có gây N+1 query khi đánh giá trên collection không?

Nếu expression chỉ cần một số dữ kiện, hãy lấy chúng trong service hoặc repository rồi truyền DTO phù hợp vào EvaluationContext. Không nên dùng một path dài để vô tình tải cả object graph.

## 17. Tạo helper chẩn đoán có kiểm soát

Một helper nhỏ có thể ghi nhận prefix, kiểu kết quả và lỗi mà không log dữ liệu nhạy cảm:

    static void tracePrefix(
            ExpressionParser parser,
            EvaluationContext context,
            Object rootObject,
            String source) {

        try {
            Expression expression =
                parser.parseExpression(source);

            Object value =
                expression.getValue(context, rootObject);

            String type = value == null
                ? "<null>"
                : value.getClass().getName();

            log.debug(
                "Expression prefix [{}] -> [{}]",
                source,
                type
            );
        }
        catch (ParseException ex) {
            log.warn(
                "Parse failed at prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
        }
        catch (EvaluationException ex) {
            log.warn(
                "Evaluation failed at prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
        }
    }

Có thể gọi helper cho các prefix đã xác định thủ công.

Không nên đưa toàn bộ root object, variable map hoặc kết quả object vào log. Expression source cũng có thể chứa literal nhạy cảm nếu được tạo từ cấu hình; hãy redact trước khi ghi.

Trong production, chỉ bật trace chi tiết khi có nhu cầu và giới hạn quyền truy cập log.

## 18. Viết test cho từng bước của property path

Sau khi tìm được bước gây lỗi, hãy tạo test nhỏ với object graph tương ứng.

Ví dụ:

    @Test
    void readsNestedCity() {
        Address address = new Address("Da Nang");
        Profile profile = new Profile(address);
        Customer customer = new Customer(profile);

        StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

        Expression expression =
            new SpelExpressionParser()
                .parseExpression("profile.address.city");

        assertThat(
            expression.getValue(context, String.class)
        ).isEqualTo("Da Nang");
    }

Nên có thêm test cho các trường hợp:

- Root object null.
- Property trung gian null.
- Getter không tồn tại hoặc không đọc được.
- Kiểu trả về khác dự kiến.
- Map key thiếu.
- List rỗng hoặc index vượt giới hạn.
- Custom PropertyAccessor.
- Getter ném exception.
- Lazy proxy hoặc dữ liệu chưa tải nếu ứng dụng dùng ORM.

Test nên dùng object nhỏ, rõ và dữ liệu xác định. Điều này giúp tái hiện lỗi mà không cần khởi động toàn bộ ứng dụng nếu không cần thiết.

## 19. Nếu path được tạo động từ cấu hình hoặc người dùng

Nếu ứng dụng nhận tên property từ người dùng hoặc một hệ thống bên ngoài, đừng nối trực tiếp tên đó vào expression source.

Ví dụ không nên:

    String source = "customer." + suppliedProperty;

    Expression expression =
        parser.parseExpression(source);

Thay vào đó, dùng allow-list:

    Map<String, Expression> allowedPaths = Map.of(
        "name", parser.parseExpression("customer.name"),
        "city", parser.parseExpression("customer.address.city")
    );

    Expression expression =
        allowedPaths.get(suppliedProperty);

Chỉ các path được ứng dụng định nghĩa mới được đánh giá.

Nếu cần nhiều field động, hãy dùng schema hoặc cấu trúc rule có kiểu rõ ràng thay vì cho phép chuỗi tùy ý. Property path có thể truy cập sâu vào object graph, nên cần kiểm soát phạm vi object và accessor.

## 20. Những điểm cần nhớ

- Chia property path dài thành các prefix tăng dần để tìm bước đầu tiên lỗi.
- Phân biệt ParseException ở parseExpression với EvaluationException ở getValue.
- Giữ cùng EvaluationContext, root object và các resolver/accessor khi so sánh.
- Đánh giá tăng dần trên object trung gian phù hợp với path property đơn giản và tránh gọi lại getter trước đó.
- Kiểm tra null và kiểu runtime sau mỗi bước.
- Dùng indexer đúng với List, array và Map; kiểm tra index/key riêng.
- Method invocation cần được kiểm tra như một bước riêng, bao gồm cause và side effect.
- Không dùng split dấu chấm để phân tích expression; dấu chấm có thể nằm trong key, tên class, method hoặc string.
- Selection, projection và template cần được chia theo cấu trúc expression.
- Position trong exception là offset và chỉ là manh mối, không phải source range hoàn chỉnh.
- Cẩn thận với getter kích hoạt lazy loading, I/O hoặc thay đổi state.
- Không log toàn bộ object hoặc dữ liệu nhạy cảm khi trace.
- Nếu path do bên ngoài cung cấp, dùng allow-list hoặc rule model có schema.
- Viết test nhỏ cho từng tầng của object graph và các trường hợp null/type/index.

Khi một property path dài thất bại, hãy thu hẹp phạm vi từng bước: xác nhận root, kiểm tra từng object trung gian, xác định kiểu runtime và chỉ sau đó xem accessor hoặc method liên quan. Cách làm này giúp phân biệt lỗi dữ liệu, lỗi cấu trúc object và lỗi cấu hình SpEL mà không phải đoán từ thông báo cuối cùng.

## Tài liệu tham khảo

- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Evaluation and Exceptions: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — Expression: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/Expression.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html
