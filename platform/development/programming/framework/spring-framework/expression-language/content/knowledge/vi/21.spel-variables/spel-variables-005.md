# Biến trong selection và projection

Trong SpEL, selection và projection cho phép lọc hoặc biến đổi từng phần tử của collection. Khi biểu thức được chạy cho từng phần tử, đôi khi ta cần thêm một giá trị bên ngoài collection để làm điều kiện hoặc tham số tính toán. Ví dụ, lọc các dòng đơn hàng theo số lượng tối thiểu do cấu hình cung cấp, hoặc tính giá sau chiết khấu dựa trên một tỷ lệ được truyền vào.

EvaluationContext cho phép đăng ký các biến có tên. Trong biểu thức, biến được tham chiếu bằng tiền tố #, chẳng hạn #minimumQuantity hoặc #discountRate. Khi dùng các biến này bên trong selection và projection, cần phân biệt chúng với #this và #root: biến do ứng dụng cung cấp giữ nguyên tên và giá trị trong context; #this đại diện cho phần tử hiện tại; #root đại diện cho đối tượng gốc của lần đánh giá.

## 1. Selection và projection hoạt động trên phần tử hiện tại

Selection dùng cú pháp .?[...] để giữ lại các phần tử thỏa điều kiện:

    lines.?[quantity >= 2]

Projection dùng cú pháp .![...] để tính một giá trị cho từng phần tử:

    lines.![product.name]

Trong cả hai thao tác, SpEL lần lượt đánh giá biểu thức bên trong ngoặc vuông trên từng phần tử của collection. Các property không có tiền tố trong phần biểu thức thường được đọc từ phần tử hiện tại.

Có thể viết tường minh đối tượng hiện tại bằng #this:

    lines.?[#this.quantity >= 2]

    lines.![#this.product.name]

Cách viết có #this giúp người đọc thấy rõ property thuộc về phần tử đang được xử lý. Điều này đặc biệt hữu ích khi biểu thức có thêm biến từ context hoặc cần truy cập dữ liệu của root object.

## 2. Biến trong EvaluationContext

Biến là giá trị được ứng dụng đưa vào EvaluationContext với một tên cụ thể. Với StandardEvaluationContext, có thể đăng ký biến bằng setVariable():

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 2);
    context.setVariable("discountRate", new BigDecimal("0.10"));

Trong SpEL, tham chiếu đến hai biến đó bằng tiền tố #:

    #minimumQuantity
    #discountRate

Tên biến trong biểu thức phải khớp với tên đã đăng ký. Tiền tố # phân biệt biến context với property của root object hoặc property của phần tử hiện tại.

Ví dụ:

    lines.?[quantity >= #minimumQuantity]

Trong biểu thức này, quantity là property của LineItem hiện tại; #minimumQuantity là biến được ứng dụng truyền vào context. Mỗi dòng hàng được so sánh với cùng ngưỡng tối thiểu đã đăng ký.

Nếu viết minimumQuantity mà không có #, SpEL sẽ tìm property đó trên đối tượng hiện tại. Nó không tự hiểu đó là biến context.

## 3. Phân biệt #this, #root và biến do ứng dụng đặt

Ba loại tham chiếu này có vai trò khác nhau:

| Cách viết | Ý nghĩa |
|---|---|
| #this | Đối tượng hiện tại đang được biểu thức xử lý |
| #root | Root object của toàn bộ lần đánh giá |
| #minimumQuantity | Biến minimumQuantity do ứng dụng đăng ký trong context |
| quantity | Property quantity trên đối tượng hiện tại trong selection/projection |
| #root.customerTier | Property customerTier trên root object |

Giả sử root object là Order, có collection lines, property customerTier và property exchangeRate. Khi đánh giá:

    lines.?[#this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD']

- #this là LineItem hiện tại.
- #this.quantity là số lượng của dòng hàng đó.
- #minimumQuantity là ngưỡng được đăng ký trong context.
- #root.customerTier là hạng khách hàng của Order ban đầu.

#root không đổi thành phần tử collection khi selection hoặc projection bắt đầu. Ngược lại, #this thay đổi theo phần tử đang được xử lý.

## 4. Ví dụ: dùng biến để lọc collection

Giả sử ứng dụng có lớp Order với danh sách LineItem. Mỗi LineItem có quantity và product. Quy tắc cần giữ lại các dòng có số lượng đạt ngưỡng cấu hình.

Java chuẩn bị root object và biến:

    Order order = orderService.findOrder(orderId);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 3);

Biểu thức selection:

    lines.?[quantity >= #minimumQuantity]

Đánh giá:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "lines.?[quantity >= #minimumQuantity]");

    List<?> qualifyingLines =
            expression.getValue(context, List.class);

Với ngưỡng bằng 3, các dòng có quantity từ 3 trở lên được giữ lại. Những dòng còn lại bị loại khỏi kết quả selection; collection nguồn không bị thay đổi.

Có thể dùng #this để làm rõ hơn:

    lines.?[#this.quantity >= #minimumQuantity]

Hai biểu thức tương đương trong ngữ cảnh này. Biến #minimumQuantity có cùng giá trị trong mọi lần đánh giá phần tử của selection.

## 5. Ví dụ: dùng biến trong projection

Projection cũng có thể dùng biến làm tham số cho phép tính. Giả sử mỗi LineItem có unitPrice kiểu BigDecimal. Ứng dụng truyền vào hệ số điều chỉnh giá:

    context.setVariable(
            "priceFactor",
            new BigDecimal("1.05"));

Biểu thức:

    lines.![#this.unitPrice.multiply(#priceFactor)]

Mỗi dòng hàng được chuyển thành giá đã nhân với hệ số 1.05. Kết quả là một collection các giá trị BigDecimal.

Có thể viết đầy đủ phần Java:

    Expression projection =
            parser.parseExpression(
                    "lines.![#this.unitPrice.multiply(#priceFactor)]");

    List<?> adjustedPrices =
            projection.getValue(context, List.class);

Trong ví dụ này, #this.unitPrice lấy giá của dòng hàng hiện tại; #priceFactor lấy biến dùng chung do ứng dụng cung cấp. Phép biến đổi không cập nhật unitPrice trên LineItem.

Biến đặc biệt hữu ích khi cùng một quy tắc được đánh giá trên nhiều phần tử nhưng tham số tính toán được quyết định ở bên ngoài, chẳng hạn tỷ lệ chiết khấu, ngưỡng điểm, ngày hiệu lực hoặc mã khu vực.

## 6. Kết hợp selection, projection và nhiều biến

Một biểu thức có thể dùng cùng lúc nhiều biến và cả hai thao tác. Ví dụ, chỉ lấy tên sản phẩm của những dòng hàng có số lượng đạt ngưỡng và thuộc đơn hàng của khách GOLD:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![#this.product.name]

Quy trình gồm hai bước:

1. Selection kiểm tra từng LineItem bằng quantity và hạng khách hàng của root object.
2. Projection lấy product.name từ mỗi dòng còn lại.

Một ví dụ khác tính giá sau khi áp dụng tỷ lệ giảm giá, nhưng chỉ cho các dòng có số lượng dương:

    lines.?[#this.quantity > 0]
         .![#this.unitPrice.multiply(#discountFactor)]

Trong đó discountFactor là biến đã đăng ký trong EvaluationContext. Có thể đổi giá trị biến khi tạo context cho một lần đánh giá khác mà không phải viết lại chuỗi biểu thức.

Khi biểu thức có nhiều điều kiện, nên xuống dòng và dùng #this hoặc #root tường minh để người đọc nhận ra nguồn của từng giá trị.

## 7. Biến không thay thế property của phần tử

Một biến context là dữ liệu bên ngoài được đưa vào biểu thức. Nó không tự động trở thành property của từng phần tử collection.

Ví dụ:

    lines.?[quantity >= #minimumQuantity]

Ở đây, quantity thuộc LineItem, còn minimumQuantity thuộc context. Nếu LineItem cũng có property minimumQuantity, cách viết không có # sẽ truy cập property của LineItem hiện tại:

    lines.?[quantity >= minimumQuantity]

Hai biểu thức có thể cho kết quả khác nhau. Hãy dùng # trước tên biến khi muốn đọc giá trị do ứng dụng đăng ký.

Tương tự, nếu root object có property customerTier, có thể viết:

    #root.customerTier

Cách viết customerTier bên trong selection có thể tìm property trên phần tử hiện tại. Nếu LineItem không có property đó, biểu thức có thể lỗi. Dùng #root để nói rõ rằng giá trị cần lấy thuộc Order gốc.

## 8. #this thay đổi trong collection lồng nhau

Khi biểu thức đi vào một selection hoặc projection lồng nhau, #this đại diện cho phần tử đang được xử lý ở phạm vi collection hiện tại. Vì vậy, trong biểu thức lồng nhiều cấp, cần xác định #this đang chỉ đến loại đối tượng nào.

Ví dụ, mỗi Order có collection lines và mỗi LineItem có collection discounts:

    orders.![lines.![#this.amount]]

Ở projection ngoài, #this là Order hiện tại. Khi biểu thức tiếp tục vào projection của lines, #this trở thành LineItem hiện tại. Trong projection trong cùng, #this.amount được đọc trên đối tượng hiện tại của collection đó.

#root vẫn đại diện cho root object ban đầu của lần đánh giá, không tự chuyển thành Order hoặc LineItem chỉ vì biểu thức đi sâu vào collection con.

Khi cần dùng dữ liệu của root trong biểu thức lồng nhau, hãy tham chiếu #root rõ ràng. Nếu cần giữ và sử dụng nhiều cấp đối tượng trung gian trong một phép biến đổi rất phức tạp, nên cân nhắc chia nhỏ xử lý trong Java để tránh biểu thức khó theo dõi.

## 9. Biến có kiểu dữ liệu và giá trị null

Biến được đăng ký trong context là một object Java. Kiểu runtime của giá trị đó ảnh hưởng đến các phép so sánh và tính toán trong SpEL.

Ví dụ:

    context.setVariable("minimumQuantity", 3);
    context.setVariable("activeOnly", true);
    context.setVariable("cutoffDate", LocalDate.of(2026, 1, 1));

Các biểu thức có thể dùng trực tiếp những biến này:

    lines.?[quantity >= #minimumQuantity]
    lines.?[active == #activeOnly]
    records.?[createdAt >= #cutoffDate]

Nếu một biến có thể null, cần xác định cách xử lý trước khi dùng nó trong phép so sánh hoặc phép tính. Ví dụ, nếu minimumQuantity có thể null:

    #minimumQuantity != null
        and quantity >= #minimumQuantity

Toán tử and có short-circuit; khi biến null, vế phải không cần được đánh giá. Tuy nhiên, điều kiện này chỉ hợp lý nếu nghiệp vụ xác định rằng null đồng nghĩa với việc không chọn phần tử. Nếu null cần dùng một ngưỡng mặc định, có thể dùng Elvis:

    quantity >= (#minimumQuantity ?: 1)

Hãy chọn chính sách null rõ ràng. Không nên để một biến thiếu giá trị vô tình tạo ra lỗi chuyển kiểu hoặc kết quả không mong đợi.

## 10. Dùng biến với Map trong selection và projection

Khi selection hoặc projection chạy trên Map, phần tử hiện tại là Map.Entry. Có thể dùng #this.key và #this.value để đọc khóa và giá trị.

Ví dụ chỉ giữ các mục có giá trị lớn hơn ngưỡng:

    #prices.?[#this.value > #minimumPrice]

Ở đây, #minimumPrice là biến context; #this.value là giá trị của entry hiện tại. Selection trên Map giữ lại các entry thỏa điều kiện.

Projection có thể tạo collection các chuỗi từ key và value:

    #prices.![#this.key + ':' + #this.value]

Có thể kết hợp với biến định dạng:

    #prices.![#this.key + ':' + #this.value + #suffix]

Trong ví dụ này, suffix là biến do ứng dụng cung cấp. Projection tạo ra các giá trị đầu ra cho từng entry; nó không tự xây dựng một Map mới giữ nguyên cấu trúc key-value.

## 11. Tái sử dụng Expression và vòng đời EvaluationContext

Nếu chuỗi biểu thức không đổi, ứng dụng có thể parse một lần và tái sử dụng Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "lines.?[quantity >= #minimumQuantity]");

Mỗi lần đánh giá, tạo hoặc chuẩn bị một EvaluationContext với root object và biến tương ứng:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", requestedMinimum);

    List<?> result =
            expression.getValue(context, List.class);

Cách này tách hai phần: Expression đại diện cho quy tắc đã phân tích; EvaluationContext cung cấp dữ liệu của lần đánh giá hiện tại.

Không nên dùng chung một context mutable giữa các request đồng thời nếu mỗi request có root object hoặc biến khác nhau. Một request có thể ghi đè biến của request khác nếu cùng sử dụng context. Hãy tạo context theo lần đánh giá hoặc quản lý việc cập nhật và đồng bộ hóa một cách có chủ đích.

Cũng không cần parse lại biểu thức chỉ vì giá trị biến thay đổi. Chỉ cần đánh giá Expression đã có với context chứa giá trị mới, miễn là cú pháp và ý nghĩa của rule không đổi.

## 12. Ví dụ hoàn chỉnh: lọc và tính giá sau chiết khấu

Giả sử Order có các property lines và customerTier. Mỗi LineItem có quantity, unitPrice và product.name. Ứng dụng muốn lấy tên và giá sau chiết khấu của các dòng có số lượng đạt ngưỡng, chỉ khi khách hàng thuộc hạng GOLD.

Đăng ký dữ liệu:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumQuantity", 2);
    context.setVariable("discountFactor", new BigDecimal("0.90"));

Biểu thức selection:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ]

Biểu thức projection có thể lấy tên sản phẩm:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![#this.product.name]

Nếu cần tạo một chuỗi mô tả có cả tên và giá sau giảm:

    lines.?[
        #this.quantity >= #minimumQuantity
        and #root.customerTier == 'GOLD'
    ].![
        #this.product.name + ': '
        + #this.unitPrice.multiply(#discountFactor)
    ]

Đánh giá biểu thức bằng parser:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "lines.?[#this.quantity >= #minimumQuantity "
            + "and #root.customerTier == 'GOLD']"
            + ".![#this.product.name + ': ' "
            + "+ #this.unitPrice.multiply(#discountFactor)]");

    List<?> descriptions =
            expression.getValue(context, List.class);

Kết quả phụ thuộc vào dữ liệu của order và các biến được đăng ký. Khi thay đổi minimumQuantity hoặc discountFactor, ứng dụng có thể đánh giá lại cùng Expression với context mới.

## 13. Lỗi thường gặp khi dùng biến trong selection và projection

| Cách viết hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| minimumQuantity nhưng muốn đọc biến context | Thiếu tiền tố # | Dùng #minimumQuantity |
| #minimumQuantity không có giá trị | Chưa đăng ký biến hoặc giá trị được đặt là null | Kiểm tra setVariable và chính sách null |
| #this.customerTier nhưng property thuộc Order | #this đang là phần tử collection | Dùng #root.customerTier |
| #root.quantity trong selection | quantity thuộc phần tử hiện tại | Dùng #this.quantity hoặc quantity |
| Biến bị thay đổi giữa các request | Dùng chung context mutable | Tạo context riêng cho lần đánh giá |
| Phép so sánh lỗi kiểu | Biến có kiểu không tương thích | Đăng ký đúng kiểu và xác thực dữ liệu |
| Biểu thức lồng nhau đọc nhầm #this | #this đổi theo collection hiện tại | Phân tích từng phạm vi, dùng #root rõ ràng |

Khi gặp lỗi, hãy xác định tên nào là property của phần tử, tên nào là property của root object và tên nào là biến context. Sau đó kiểm tra kiểu và giá trị của từng biến trước khi đánh giá.

## 14. Giới hạn và bảo mật khi cung cấp biến

Biến trong EvaluationContext là một phần của dữ liệu mà biểu thức được phép sử dụng. Chỉ nên đăng ký những giá trị cần thiết cho rule.

Một số nguyên tắc:

- Truyền kiểu dữ liệu cụ thể thay vì chuỗi chưa được xác thực nếu rule cần tính toán.
- Không đưa thông tin nhạy cảm hoặc object có quyền truy cập rộng vào context khi biểu thức không cần.
- Không để người dùng bên ngoài tự do chọn tên và giá trị biến rồi đánh giá biểu thức tùy ý.
- Xác định rõ biến nào bắt buộc, biến nào có thể null và giá trị mặc định nếu thiếu.
- Dùng context giới hạn quyền khi chỉ cần đọc dữ liệu; cấu hình StandardEvaluationContext có chủ đích nếu rule cần tính năng nâng cao.
- Kiểm thử selection/projection với collection rỗng, phần tử null, biến null và dữ liệu sai kiểu.

Biến chỉ cung cấp dữ liệu cho biểu thức; nó không tự kiểm tra quyền nghiệp vụ. Service vẫn phải xác thực người gọi, kiểm soát dữ liệu được phép truy cập và quyết định hành động sau khi nhận kết quả rule.

## Kết luận

Trong selection và projection, biến context cho phép đưa các tham số bên ngoài vào biểu thức mà không phải gắn chúng vào từng phần tử collection. Ứng dụng đăng ký biến bằng setVariable(), còn SpEL đọc biến bằng tiền tố #. #this đại diện cho phần tử hiện tại; #root luôn đại diện cho root object ban đầu; property không có tiền tố được đọc từ đối tượng hiện tại trong phạm vi selection/projection.

Khi kết hợp các tham chiếu này, hãy phân biệt rõ nguồn của từng giá trị, đặc biệt trong collection lồng nhau. Parse Expression một lần, cung cấp EvaluationContext phù hợp cho mỗi lần đánh giá, xác định chính sách null và chỉ đưa dữ liệu cần thiết vào context. Cách làm đó giúp rule dễ tái sử dụng, dễ cấu hình và dễ kiểm soát trong ứng dụng Spring.