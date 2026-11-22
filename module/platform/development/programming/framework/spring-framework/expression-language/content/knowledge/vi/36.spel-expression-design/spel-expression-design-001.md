# Giữ expression ngắn và tập trung vào một quyết định

## 1. Vì sao expression nên ngắn và có một mục tiêu rõ ràng?

SpEL cho phép kết hợp property access, method invocation, toán tử logic, toán tử điều kiện, collection selection/projection và nhiều khả năng khác trong cùng một biểu thức.

Khả năng kết hợp này hữu ích, nhưng một expression quá dài thường khó đọc, khó kiểm thử và khó xác định phần gây lỗi. Khi nhiều quyết định nghiệp vụ hoặc nhiều bước xử lý bị ghép vào một chuỗi, người bảo trì phải hiểu toàn bộ expression trước khi có thể thay đổi một điều kiện nhỏ.

Ví dụ một rule có thể chỉ cần trả lời:

    #order.status == 'PAID' and #order.total >= #minimum

Expression này có một mục tiêu: xác định đơn hàng có đủ điều kiện hay không.

Nếu cần kiểm tra quyền người dùng, tính phí vận chuyển, áp dụng giảm giá, ghi audit và cập nhật trạng thái, đó là các trách nhiệm khác nhau. Không nên ghép tất cả thành một expression duy nhất chỉ vì SpEL có thể gọi method hoặc truy cập bean.

Nguyên tắc thiết kế: một expression nên thể hiện một quyết định hoặc một phép biến đổi có tên gọi rõ ràng. Các bước phức tạp hơn nên được chuẩn bị ở Java hoặc tách thành những thao tác riêng.

## 2. Xác định kết quả cần có trước khi viết expression

Trước khi viết SpEL, hãy diễn đạt mục tiêu bằng một câu ngắn.

Ví dụ:

- Đơn hàng có được miễn phí vận chuyển không?
- Khách hàng có đủ điều kiện nhận ưu đãi không?
- Giá trị cấu hình nào sẽ được sử dụng?
- Tên hiển thị của khách hàng là gì?
- Có phần tử nào trong collection thỏa điều kiện không?

Sau đó xác định kiểu kết quả mong đợi:

| Mục tiêu | Kiểu kết quả phù hợp |
| --- | --- |
| Kiểm tra điều kiện | Boolean |
| Tính một giá trị số | Integer, Long, BigDecimal hoặc kiểu số phù hợp |
| Chọn một giá trị thay thế | String, enum hoặc kiểu miền nghiệp vụ |
| Lấy một property | Kiểu của property |
| Lọc collection | Collection/List phù hợp |
| Tạo cấu trúc dữ liệu | Map hoặc List có kiểu phần tử rõ ràng |

Khi mục tiêu và kiểu kết quả đã rõ, expression thường ngắn hơn vì không phải kiêm nhiệm nhiều bước xử lý.

Ví dụ:

    Expression rule =
        parser.parseExpression(
            "#order.total >= #minimum"
        );

    Boolean eligible =
        rule.getValue(context, Boolean.class);

Việc yêu cầu Boolean giúp hợp đồng của rule rõ ràng. Nếu expression trả về kiểu khác hoặc không thể chuyển đổi, lỗi được phát hiện tại evaluation thay vì âm thầm dùng một giá trị không đúng mục đích.

## 3. Kết hợp các điều kiện cùng phục vụ một quyết định

Một quyết định có thể cần nhiều điều kiện nguyên tử. Điều đó không làm expression trở nên sai thiết kế nếu các điều kiện cùng trả lời một câu hỏi.

Ví dụ:

    #order.status == 'PAID'
        and #order.total >= #minimum
        and #customer.active

Cả ba điều kiện đều tham gia quyết định đơn hàng có đủ điều kiện nhận ưu đãi hay không.

Có thể viết rõ bằng ngoặc:

    (#order.status == 'PAID')
        and (#order.total >= #minimum)
        and (#customer.active == true)

Ngoặc giúp người đọc nhận ra từng điều kiện và giảm việc phải ghi nhớ thứ tự ưu tiên toán tử.

Một expression có nhiều điều kiện không nhất thiết là expression quá phức tạp. Điều quan trọng là tất cả điều kiện có cùng mục đích, dễ hiểu và có chi phí đánh giá hợp lý.

Nếu một điều kiện thực hiện một quyết định độc lập hoặc cần quy trình xử lý riêng, hãy tách nó ra.

## 4. Ví dụ expression ngắn so với expression ôm nhiều trách nhiệm

Giả sử cần xác định một khách hàng có được giảm giá hay không.

Expression tập trung vào quyết định:

    #customer.active
        and #customer.verified
        and #order.total >= #minimumOrderTotal

Expression này chỉ trả lời eligible hay không.

Một thiết kế khó bảo trì có thể cố làm tất cả trong một chuỗi:

    @customerService.verify(#customer.id)
        and @inventoryService.hasStock(#order.items)
        and @pricingService.calculateDiscount(#order) > 0
        and @notificationService.sendPromotion(#customer.email)

Biểu thức thứ hai trộn lẫn xác minh khách hàng, kiểm tra tồn kho, tính giá và gửi thông báo. Nó có thể gọi nhiều service, gây I/O và side effect ngay trong lúc đánh giá điều kiện.

Hãy tách quy trình thành Java code:

    boolean verified =
        customerService.verify(customer.getId());

    boolean hasStock =
        inventoryService.hasStock(order.getItems());

    BigDecimal discount =
        pricingService.calculateDiscount(order);

    boolean eligible =
        verified
            && hasStock
            && discount.compareTo(BigDecimal.ZERO) > 0;

    if (eligible) {
        notificationService.sendPromotion(customer.getEmail());
    }

Nếu vẫn cần SpEL cho rule cấu hình, hãy đưa các facts đã được tính vào context:

    context.setVariable("verified", verified);
    context.setVariable("hasStock", hasStock);
    context.setVariable("discount", discount);

    Boolean eligible = parser.parseExpression(
        "#verified and #hasStock and #discount > 0"
    ).getValue(context, Boolean.class);

Expression lúc này chỉ thực hiện quyết định cuối cùng. Các thao tác có quyền truy cập hệ thống được giữ trong service.

## 5. Chuẩn bị facts trong Java thay vì tạo một object graph quá sâu

Một expression có thể truy cập nhiều tầng:

    #order.customer.profile.membership.level.discountRate

Nếu path dài và nhiều property có thể null, việc đọc expression trở nên khó khăn. Nó cũng phụ thuộc vào cấu trúc nội bộ của nhiều class.

Hãy chuẩn bị một DTO hoặc record chứa các facts cần cho rule:

    public record DiscountFacts(
        boolean customerActive,
        boolean verified,
        String membershipLevel,
        BigDecimal orderTotal,
        BigDecimal discountRate
    ) {}

Tạo facts trong service:

    DiscountFacts facts = new DiscountFacts(
        customer.isActive(),
        customer.isVerified(),
        customer.getMembershipLevel(),
        order.getTotal(),
        discountRate
    );

Đặt facts làm root object:

    StandardEvaluationContext context =
        new StandardEvaluationContext(facts);

Expression:

    customerActive
        and verified
        and membershipLevel == 'GOLD'
        and orderTotal >= 1000

DTO giúp expression chỉ nhìn thấy dữ liệu liên quan đến quyết định. Nó cũng làm thay đổi model nghiệp vụ ít ảnh hưởng hơn đến source rule.

Không nên tạo DTO chỉ để đổi tên các field mà không có lợi ích. Hãy dùng nó khi cần thu hẹp object graph, chuẩn hóa dữ liệu hoặc tạo một hợp đồng ổn định cho expression.

## 6. Tách phép tính phức tạp thành method Java có tên rõ ràng

Nếu một phần logic cần nhiều bước, vòng lặp hoặc xử lý lỗi, hãy đưa phần đó vào method Java.

Ví dụ expression khó đọc:

    (#order.items.?[active == true].![price * quantity]
        .?[#this > 0].size() > 0)
        and #order.customer.profile.region.toUpperCase() == 'VN'

Có thể chuẩn bị dữ liệu trước:

    boolean hasBillableItems =
        orderService.hasBillableItems(order);

    String regionCode =
        regionService.normalize(order.getCustomer());

    context.setVariable(
        "hasBillableItems",
        hasBillableItems
    );
    context.setVariable("regionCode", regionCode);

Expression còn lại:

    #hasBillableItems and #regionCode == 'VN'

Tên biến thể hiện kết quả nghiệp vụ đã được tính. Người đọc không cần phân tích toàn bộ thuật toán bên trong expression.

Nếu một phép tính thực sự là một function nhỏ, ổn định và được phép dùng trong rule, có thể đăng ký function có tên:

    #isWithinRange(#amount, #minimum, #maximum)

Tuy nhiên, không nên dùng function để che giấu một quy trình dài hoặc expose service có quyền rộng. Function nên có chữ ký rõ, phạm vi nhỏ và hành vi dễ dự đoán.

## 7. Dùng ngoặc để làm rõ logic

Expression có thể kết hợp nhiều nhóm toán tử. Khi điều kiện dài, hãy dùng ngoặc để thể hiện nhóm logic thay vì dựa hoàn toàn vào thứ tự ưu tiên.

Ví dụ:

    #order.status == 'PAID'
        and (
            #customer.vip
            or #order.total >= #premiumThreshold
        )

Cách viết này thể hiện rõ: đơn hàng phải được thanh toán, đồng thời khách hàng là VIP hoặc tổng tiền đạt ngưỡng.

So với một expression viết liền:

    #order.status == 'PAID' and #customer.vip or #order.total >= #premiumThreshold

người đọc có thể phải dừng lại để xác định nhóm điều kiện. Dù parser có quy tắc precedence xác định, ngoặc vẫn làm ý định nghiệp vụ rõ hơn.

Với các điều kiện có AND và OR đan xen, hãy ưu tiên ngoặc tường minh.

## 8. Tránh nested ternary và expression nhiều nhánh

Toán tử ternary phù hợp khi cần chọn giữa hai kết quả:

    #score >= 80 ? 'PASS' : 'REVIEW'

Expression này có một điều kiện và hai kết quả dễ hiểu.

Nếu lồng nhiều ternary:

    #score >= 90
        ? 'EXCELLENT'
        : #score >= 80
            ? 'GOOD'
            : #score >= 60
                ? 'PASS'
                : 'FAIL'

expression trở nên khó đọc và khó thêm một mức phân loại mới.

Hãy chuyển bảng phân loại hoặc quy tắc nhiều nhánh sang Java method, enum mapping hoặc cấu trúc cấu hình có schema. SpEL chỉ nên nhận kết quả hoặc áp dụng một điều kiện đơn giản nếu cần.

Tương tự, tránh dùng Elvis, ternary, null-safe navigation và phép nối chuỗi lồng nhau thành một biểu thức dài khó kiểm tra.

## 9. Dùng null-safe navigation có chủ đích

Null-safe navigation giúp expression không lỗi khi receiver có thể null:

    #customer?.profile?.address?.city

Cú pháp ngắn không có nghĩa là đã xác định được dữ liệu thiếu ở tầng nào. Nếu quyết định nghiệp vụ cần phân biệt customer chưa tồn tại với address chưa được khai báo, hãy chuẩn hóa các trạng thái đó trước khi đánh giá.

Ví dụ chuẩn bị facts:

    context.setVariable("customerExists", customer != null);
    context.setVariable("cityConfigured", city != null);

Expression:

    #customerExists and #cityConfigured

Nếu chỉ cần một kết quả mặc định, có thể dùng Elvis:

    #customer?.profile?.address?.city ?: 'UNKNOWN'

Nhưng hãy chắc rằng UNKNOWN có đúng ý nghĩa nghiệp vụ. Elvis có thể chọn giá trị mặc định khi vế trái là null hoặc rỗng theo hành vi của SpEL; nó không thay thế validation.

Không dùng null-safe operator để che giấu dữ liệu bắt buộc đang thiếu. Nếu một property phải luôn tồn tại, hãy phát hiện và báo lỗi ở tầng validation phù hợp.

## 10. Không nhồi collection processing vào một expression

SpEL hỗ trợ selection và projection:

    #orders.?[status == 'PAID']
    #orders.![total]

Có thể kết hợp khi mục tiêu rõ ràng:

    #orders.?[status == 'PAID'].size()

Expression này đếm số đơn hàng đã thanh toán. Tuy nhiên, selection tạo collection kết quả trước khi gọi size().

Nếu chỉ cần kiểm tra có đơn hàng phù hợp, select first có thể thể hiện ý định trực tiếp:

    #orders.^[status == 'PAID'] != null

Nếu cần xử lý nhiều bước trên collection lớn, hãy cân nhắc lọc hoặc tổng hợp bằng Java hoặc ở tầng truy vấn. Không nên biến SpEL thành một pipeline xử lý dữ liệu dài chỉ để tránh viết code Java.

Giữ expression tập trung vào một câu hỏi: lọc, lấy một giá trị, hoặc kiểm tra điều kiện. Các bước độc lập nên có tên và được xử lý riêng.

## 11. Tránh gọi method tốn kém hoặc có side effect

Một expression có thể gọi method trên root object, variable hoặc bean. Method được gọi khi expression được đánh giá.

Ví dụ:

    #customer.isEligible()

Nếu method chỉ kiểm tra một vài field trong bộ nhớ, chi phí có thể nhỏ. Nhưng nếu method truy vấn database, gọi API, ghi log nghiệp vụ hoặc thay đổi trạng thái, expression có thể gây tác động lớn.

Đặc biệt, trong selection:

    #orders.?[#this.customer.isEligible()]

method có thể được gọi lặp lại trên nhiều phần tử.

Hãy tránh I/O và side effect trong predicate hoặc function được expose cho rule. Thực hiện việc lấy dữ liệu, kiểm tra quyền và cập nhật trạng thái trong service có kiểm soát.

Expression nên đánh giá dữ liệu đã chuẩn bị và trả về kết quả có thể dự đoán.

## 12. Đặt tên variable để expression tự giải thích

Tên variable tốt giúp expression ngắn mà vẫn dễ hiểu.

Tên khó hiểu:

    #x and #y > #z

Tên có ngữ nghĩa:

    #customerActive
        and #orderTotal >= #minimumOrderTotal

Khi đọc expression thứ hai, người bảo trì hiểu ngay dữ liệu nào đang được so sánh và mục tiêu có thể là gì.

Nên dùng:

- Danh từ cho facts hoặc dữ liệu.
- Tên boolean thể hiện trạng thái như isVerified, customerActive hoặc hasStock.
- Tên có đơn vị rõ ràng cho giá trị số như totalAmountVnd hoặc retryCount.
- Tên function là động từ hoặc cụm động từ mô tả hành động.

Tránh tên chung chung như data, value, obj hoặc flag nếu có thể dùng tên nghiệp vụ rõ hơn.

Không đăng ký quá nhiều variable không liên quan trong cùng context. Một rule chỉ nên nhận các facts cần thiết cho nhiệm vụ của nó.

## 13. Giữ expression source cố định, truyền dữ liệu qua context

Không ghép giá trị đầu vào vào source:

    String source =
        "#orderTotal >= " + userSuppliedMinimum;

    Expression expression =
        parser.parseExpression(source);

Cách này khiến dữ liệu bên ngoài trở thành một phần của chương trình SpEL và có thể dẫn tới expression injection.

Hãy parse source cố định:

    Expression expression =
        parser.parseExpression(
            "#orderTotal >= #minimumOrderTotal"
        );

Sau đó truyền dữ liệu:

    context.setVariable(
        "orderTotal",
        orderTotal
    );

    context.setVariable(
        "minimumOrderTotal",
        userSuppliedMinimum
    );

Expression giữ nguyên, dữ liệu thay đổi qua variables. Cách này dễ kiểm thử, dễ cache và dễ kiểm soát hơn.

Nếu người dùng cần chọn rule, hãy ánh xạ lựa chọn sang expression đã được ứng dụng định nghĩa trước thay vì parse chuỗi tùy ý.

## 14. Parse một lần và tái sử dụng Expression

Nếu expression source không thay đổi, hãy parse một lần rồi giữ lại Expression để đánh giá nhiều lần.

Ví dụ:

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression rule =
        parser.parseExpression(
            "#orderTotal >= #minimumOrderTotal"
        );

Trong mỗi lần đánh giá, cung cấp context phù hợp:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("orderTotal", currentTotal);
    context.setVariable("minimumOrderTotal", minimum);

    Boolean eligible =
        rule.getValue(context, Boolean.class);

Không parse lại cùng một source trong từng vòng lặp hoặc mỗi lần gọi service nếu có thể giữ Expression để tái sử dụng.

Dữ liệu động nên nằm trong context theo request hoặc lần đánh giá. Không chia sẻ mutable variables giữa các request.

Expression đã parse cũng cần được quản lý theo security policy nhất quán. Không tái sử dụng cùng một instance Expression giữa các context có mức quyền khác nhau.

## 15. Chia expression theo ranh giới có thể kiểm thử

Nếu một quyết định vẫn cần nhiều bước, hãy chia thành các expression nhỏ có tên và mục tiêu riêng.

Ví dụ:

    Expression isOrderPaid =
        parser.parseExpression(
            "#orderStatus == 'PAID'"
        );

    Expression meetsMinimum =
        parser.parseExpression(
            "#orderTotal >= #minimumOrderTotal"
        );

    Expression isEligible =
        parser.parseExpression(
            "#orderPaid and #meetsMinimum"
        );

Ứng dụng có thể đánh giá hai facts đầu tiên, sau đó truyền kết quả vào expression tổng hợp.

Tuy nhiên, không nên tách mọi phép so sánh thành một expression riêng nếu điều đó làm tăng số lượng context và khiến luồng xử lý khó theo dõi. Chỉ chia khi mỗi phần có ý nghĩa độc lập, được tái sử dụng hoặc cần chẩn đoán riêng.

Một cách khác là dùng Java code để tính facts rồi chỉ giữ một expression cuối cùng cho quyết định.

## 16. Kiểm thử expression theo các trường hợp biên

Một expression ngắn vẫn cần được kiểm thử với dữ liệu thực tế và các trường hợp biên.

Với rule:

    #orderPaid and #orderTotal >= #minimumOrderTotal

hãy kiểm tra:

- orderPaid là true và tổng tiền vượt ngưỡng.
- orderPaid là false.
- Tổng tiền đúng bằng ngưỡng.
- Tổng tiền thấp hơn ngưỡng.
- Giá trị số là null nếu kiểu dữ liệu cho phép.
- Variable bị thiếu.
- Variable có kiểu không tương thích.
- Root object hoặc property bắt buộc bị null.

Nên parse expression một lần trong test setup và đánh giá với các context khác nhau.

Kiểm tra kiểu kết quả:

    Boolean result =
        expression.getValue(context, Boolean.class);

Không chỉ kiểm tra một trường hợp true. Những trường hợp false, null, biên số và dữ liệu không hợp lệ giúp phát hiện giả định sai trong rule.

Nếu expression gọi function, hãy test function riêng và test expression tích hợp với function đó.

## 17. Khi nào nên dùng SpEL và khi nào nên dùng Java?

SpEL phù hợp khi cần một rule hoặc phép tính nhỏ, có thể cấu hình và có đầu vào rõ ràng.

| Nhu cầu | Cách nên cân nhắc |
| --- | --- |
| So sánh vài property | SpEL |
| Kết hợp điều kiện boolean | SpEL |
| Chọn một giá trị đơn giản bằng ternary | SpEL |
| Đọc property cấu hình hoặc bean trong injection point | SpEL theo context phù hợp |
| Lặp qua nhiều tầng collection lớn | Java hoặc tầng truy vấn |
| Nhiều nhánh nghiệp vụ phức tạp | Java service |
| Gọi nhiều API hoặc database | Java service |
| Thực hiện transaction hoặc cập nhật nhiều object | Java service |
| Xử lý lỗi và retry nhiều bước | Java service |
| Rule do người dùng cuối tự viết | DSL/rule model giới hạn hoặc thiết kế kiểm soát riêng |

Đừng chọn SpEL chỉ vì có thể viết một thuật toán thành một chuỗi expression. Hãy chọn nó khi biểu thức làm rõ quy tắc và vẫn dễ review.

## 18. Những lỗi thiết kế thường gặp

| Thiết kế | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Một expression chứa nhiều quyết định độc lập | Khó hiểu và khó thay đổi | Tách từng quyết định |
| Path lồng nhau quá sâu | Phụ thuộc nhiều object và dễ lỗi null | Chuẩn bị DTO/facts |
| Nested ternary nhiều tầng | Khó đọc và khó thêm nhánh | Dùng Java method hoặc mapping |
| Selection/projection nhiều tầng | Tốn CPU và bộ nhớ, khó debug | Xử lý collection ở Java hoặc repository |
| Gọi service trong predicate | I/O lặp lại và side effect | Tính kết quả trước, truyền qua variable |
| Dùng tên variable chung chung | Expression khó tự giải thích | Đặt tên theo ngữ nghĩa |
| Nối user input vào source | Nguy cơ expression injection | Dùng variable và source cố định |
| Parse lại trong mỗi lần đánh giá | Lặp chi phí parsing | Parse một lần, tái sử dụng có kiểm soát |
| Chia quá nhiều expression nhỏ | Luồng xử lý phân mảnh | Chỉ tách theo ranh giới có ý nghĩa |
| Dùng expression để thay transaction/service | Thiếu kiểm soát lỗi và trạng thái | Đưa quy trình vào Java service |

## 19. Checklist trước khi đưa expression vào sử dụng

Trước khi lưu hoặc triển khai một expression, hãy tự hỏi:

1. Expression này trả lời đúng một câu hỏi hoặc thực hiện một phép biến đổi rõ ràng không?
2. Kiểu kết quả có xác định và phù hợp với caller không?
3. Mỗi điều kiện có liên quan trực tiếp đến cùng quyết định không?
4. Ngoặc có làm rõ nhóm AND/OR không?
5. Có thể đưa object graph dài thành DTO/facts ngắn hơn không?
6. Có logic nhiều bước nào nên chuyển sang Java method không?
7. Có nested ternary hoặc collection pipeline khó đọc không?
8. Có method nào gọi database, network hoặc thay đổi state không?
9. Variable có tên rõ và chỉ chứa dữ liệu cần thiết không?
10. Source có cố định và dữ liệu được truyền qua context không?
11. Expression có được parse một lần và tái sử dụng theo security policy phù hợp không?
12. Đã kiểm thử true, false, null, giá trị biên và lỗi kiểu chưa?

Nếu expression cần nhiều giải thích bằng comment mới hiểu được, hãy xem lại ranh giới trách nhiệm và dữ liệu đầu vào.

## 20. Những điểm cần nhớ

- Giữ mỗi expression tập trung vào một quyết định hoặc một phép biến đổi rõ ràng.
- Nhiều điều kiện vẫn phù hợp nếu cùng phục vụ một mục tiêu.
- Xác định kiểu kết quả và câu hỏi nghiệp vụ trước khi viết expression.
- Dùng ngoặc để thể hiện nhóm điều kiện và tránh logic khó đọc.
- Chuyển thuật toán nhiều bước và I/O sang Java service.
- Chuẩn bị DTO hoặc facts để tránh property path quá sâu.
- Tránh nested ternary, collection pipeline dài và method có side effect.
- Dùng variable có tên ngữ nghĩa và giữ expression source cố định.
- Truyền dữ liệu qua EvaluationContext thay vì nối chuỗi source từ input.
- Parse một lần và tái sử dụng Expression trong phạm vi security policy nhất quán.
- Tách expression khi mỗi phần có ý nghĩa độc lập hoặc cần kiểm thử riêng.
- Kiểm thử cả true, false, null, boundary và lỗi chuyển đổi.
- Chọn Java hoặc DSL có cấu trúc khi logic vượt quá khả năng diễn đạt rõ ràng của một expression ngắn.

Một expression tốt giúp người đọc hiểu ngay nó đang quyết định điều gì. Khi expression bắt đầu điều phối nhiều service, xử lý nhiều collection hoặc thực hiện nhiều bước nghiệp vụ, hãy chuyển phần đó sang Java và chỉ đưa kết quả cần thiết trở lại SpEL.

## Tài liệu tham khảo

- Spring Framework Reference — Language Reference: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html
- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — Operators: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html
- Spring Framework Reference — Collection Selection and Projection: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html
- Spring Framework Reference — Variables and Functions: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html
