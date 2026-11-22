# Dấu chấm phẩy, dấu ngoặc và cấu trúc lồng nhau

SpEL là một ngôn ngữ biểu thức. Một chuỗi SpEL mô tả một giá trị, một phép tính hoặc một điều kiện để Spring phân tích và đánh giá trong một context. Cú pháp của nó có nhiều dấu giống Java, nhưng mỗi dấu có vai trò riêng. Đặc biệt, SpEL không phải một khối lệnh Java thu nhỏ: không thể dùng dấu chấm phẩy để viết liên tiếp nhiều câu lệnh trong cùng một biểu thức.

Khi đọc hoặc viết biểu thức dài, cần phân biệt dấu phân tách đối số, dấu nhóm biểu thức, dấu truy cập phần tử và dấu tạo cấu trúc dữ liệu. Hiểu đúng các vai trò này giúp tránh lỗi parse và làm biểu thức lồng nhau dễ đọc hơn.

## 1. Dấu chấm phẩy không dùng để nối nhiều câu lệnh SpEL

Trong Java, dấu chấm phẩy kết thúc một câu lệnh:

    int quantity = 3;
    int price = 100;

Đây là cú pháp của Java. Khi gọi SpEL parser, ứng dụng truyền vào một chuỗi biểu thức, chẳng hạn:

    Expression expression = parser.parseExpression("quantity * price");

Phần nằm trong chuỗi là SpEL; dấu chấm phẩy kết thúc câu lệnh Java nằm bên ngoài chuỗi. Không nên đưa dấu chấm phẩy vào để nối hai biểu thức độc lập:

    quantity > 0; price > 0

Chuỗi trên không có nghĩa là “kiểm tra quantity rồi kiểm tra price” như hai câu lệnh Java. SpEL không định nghĩa dấu chấm phẩy như một dấu phân tách câu lệnh tổng quát. Nếu cần kết hợp nhiều điều kiện thành một kết quả, hãy dùng toán tử logic:

    quantity > 0 and price > 0

Nếu cần thực hiện hai lần đánh giá độc lập, hãy tạo hai biểu thức và gọi parser/evaluator riêng cho từng biểu thức trong mã Java:

    Expression quantityRule =
            parser.parseExpression("quantity > 0");

    Expression priceRule =
            parser.parseExpression("price > 0");

    Boolean validQuantity =
            quantityRule.getValue(context, order, Boolean.class);

    Boolean validPrice =
            priceRule.getValue(context, order, Boolean.class);

Dấu chấm phẩy vẫn có thể xuất hiện như một ký tự bình thường bên trong chuỗi literal. Ví dụ:

    'A;B;C'

Biểu thức trên trả về chuỗi A;B;C; các dấu chấm phẩy là dữ liệu văn bản, không phải dấu phân tách cú pháp. Quy tắc thực hành là: dấu chấm phẩy thuộc về cú pháp Java ở bên ngoài chuỗi SpEL, hoặc thuộc nội dung chuỗi khi được đặt trong dấu nháy; không dùng nó để ghép nhiều biểu thức SpEL.

## 2. Dấu phẩy phân tách đối số và phần tử

Dấu phẩy là dấu phân tách thường gặp bên trong cấu trúc SpEL. Nó được dùng giữa các đối số khi gọi phương thức, giữa các phần tử của inline list và giữa các cặp trong inline map.

### Đối số của lời gọi phương thức

Một lời gọi phương thức có thể nhận nhiều đối số:

    priceService.calculate(subtotal, discountRate, taxRate)

Mỗi đối số được phân tách bằng dấu phẩy. Bản thân từng đối số vẫn có thể là một biểu thức:

    priceService.calculate(
        order.subtotal,
        order.customer.discountRate,
        order.tax.rate
    )

Trong ví dụ này, order.customer.discountRate và order.tax.rate là các biểu thức truy cập thuộc tính. Dấu phẩy chỉ đánh dấu ranh giới giữa các đối số được truyền vào phương thức.

### Phần tử của danh sách

SpEL dùng cặp dấu ngoặc nhọn {} để tạo inline list. Các phần tử trong danh sách được phân tách bằng dấu phẩy:

    {10, 20, 30, 40}

Một danh sách có thể chứa biểu thức thay vì chỉ chứa literal:

    {order.subtotal, order.shippingFee, order.tax}

Danh sách cũng có thể lồng nhau:

    {{'red', 'green'}, {'blue', 'yellow'}}

Mỗi dấu phẩy phân tách các phần tử ở đúng cấp ngoặc hiện tại. Dấu phẩy bên trong danh sách con không kết thúc phần tử của danh sách ngoài.

### Cặp khóa và giá trị của map

Inline map cũng dùng {}, nhưng mỗi phần tử có dạng key:value:

    {name:'An', tier:'GOLD'}

Dấu hai chấm phân tách khóa với giá trị; dấu phẩy phân tách cặp khóa-giá trị này với cặp tiếp theo. Map có thể chứa map hoặc list khác:

    {
        customer: {name:'An', tier:'GOLD'},
        limits: {maxOrders:10, regions:{'VN', 'SG'}}
    }

Ở đây, customer và limits là hai khóa của map ngoài. Giá trị của customer là một map con; giá trị regions là một list con.

## 3. Dấu ngoặc tròn dùng để gọi hàm và nhóm biểu thức

Dấu ngoặc tròn () có hai vai trò chính: bao quanh danh sách đối số của lời gọi phương thức/hàm và nhóm một phần biểu thức để xác định cách tính.

### Bao quanh đối số

Lời gọi phương thức dùng ngoặc tròn, kể cả khi không có đối số:

    order.calculateTotal()
    order.customer.getDisplayName()
    approvalRule.matches(order)

Nếu có nhiều đối số, đặt chúng trong cùng cặp ngoặc và phân tách bằng dấu phẩy:

    approvalRule.matches(order, currentUser)

Dấu ngoặc của một lời gọi có thể nằm bên trong dấu ngoặc của lời gọi khác. Đây là lời gọi lồng nhau:

    formatter.format(
        order.customer.getDisplayName(),
        order.calculateTotal()
    )

SpEL đánh giá các biểu thức đối số rồi truyền kết quả cho lời gọi bên ngoài. Khi đọc biểu thức, hãy ghép từng dấu ngoặc mở với dấu ngoặc đóng tương ứng để biết lời gọi nào đang nhận đối số nào.

### Nhóm biểu thức để điều khiển thứ tự đánh giá

Ngoặc tròn cũng giúp nhóm điều kiện. Ví dụ:

    (order.total >= 1000000 and order.customer.tier == 'GOLD')
        or order.customer.isVip

Nhóm đầu tiên yêu cầu cả hai điều kiện về tổng tiền và hạng khách hàng cùng đúng. Sau đó kết quả nhóm được kết hợp với điều kiện khách hàng VIP bằng or.

Một ví dụ tính toán:

    (subtotal - discount) * (1 + taxRate)

Hai cặp ngoặc làm rõ rằng cần trừ chiết khấu trước, sau đó mới nhân với hệ số thuế. Nếu bỏ ngoặc, biểu thức có thể được hiểu theo thứ tự ưu tiên toán tử mặc định và cho kết quả khác.

Nên dùng ngoặc khi biểu thức có nhiều toán tử logic hoặc toán học, đặc biệt khi trộn and với or. Dù ngôn ngữ có quy tắc ưu tiên, nhóm rõ ràng giúp người đọc nhìn thấy ý định ngay lập tức.

## 4. Dấu ngoặc vuông dùng để truy cập và lọc phần tử

Dấu ngoặc vuông [] thường biểu thị thao tác truy cập theo chỉ số hoặc theo khóa.

Với list hoặc array, chỉ số bắt đầu từ 0:

    orders[0]
    orders[0].customer.name

Với map, dùng khóa trong ngoặc vuông:

    settings['approvalLimit']
    officers['president'].name

Với chuỗi, có thể truy cập ký tự theo chỉ số:

    customer.code[0]

SpEL còn dùng ngoặc vuông trong collection selection và projection. Selection lọc các phần tử thỏa điều kiện bằng ?[...] sau tên collection:

    orders.?[status == 'PAID']

Projection biến mỗi phần tử thành một giá trị được chọn bằng .![...]:

    orders.![customer.name]

Có thể kết hợp hai thao tác:

    orders.?[status == 'PAID'].![customer.name]

Biểu thức trên lọc các đơn hàng đã thanh toán, rồi lấy tên khách hàng của từng đơn còn lại. Dấu ngoặc vuông sau ? chứa điều kiện lọc; dấu ngoặc vuông sau ! chứa biểu thức tạo giá trị đầu ra.

## 5. Dấu ngoặc nhọn tạo list và map lồng nhau

Dấu ngoặc nhọn {} có thể tạo một danh sách hoặc một map inline. Hình dạng các phần tử giúp xác định cấu trúc mong muốn:

- {1, 2, 3} là list gồm các phần tử.
- {name:'An', tier:'GOLD'} là map gồm các cặp khóa-giá trị.
- {{1, 2}, {3, 4}} là list chứa các list.
- {customer:{name:'An'}, regions:{'VN','SG'}} là map có giá trị là map và list.

Một cấu trúc lồng nhau có thể được truy cập bằng cách kết hợp dấu chấm và ngoặc vuông:

    payload['customer'].name
    payload['regions'][0]

Nếu payload là map có khóa customer chứa một đối tượng hoặc map có thuộc tính name, biểu thức thứ nhất lấy tên khách hàng. Biểu thức thứ hai lấy phần tử đầu tiên trong list regions.

Cần phân biệt ba loại ngoặc:

| Ký hiệu | Vai trò thường gặp | Ví dụ |
|---|---|---|
| () | Gọi phương thức hoặc nhóm biểu thức | max(a, b), (a + b) * c |
| [] | Truy cập phần tử/khóa, selection hoặc projection | items[0], items.?[active] |
| {} | Tạo inline list hoặc inline map | {1, 2}, {name:'An'} |

Dấu ngoặc không thể thay thế tùy ý cho nhau. Ví dụ, items(0) có hình dạng lời gọi phương thức, trong khi items[0] là truy cập phần tử theo chỉ số.

## 6. Cấu trúc lồng nhau: đọc từ trong ra ngoài

Một biểu thức phức tạp thường được ghép từ các biểu thức nhỏ. Cách đọc dễ nhất là tìm cặp ngoặc trong cùng, xác định kết quả của phần đó, rồi lần lượt mở rộng ra bên ngoài.

Xét biểu thức:

    approvalService.isAllowed(
        order.customer.profile,
        order.lines.?[quantity > 0].![product.category]
    )

Có thể phân tích theo các lớp:

1. order.customer.profile truy cập thông tin hồ sơ của khách hàng.
2. order.lines.?[quantity > 0] lọc các dòng đơn hàng có số lượng dương.
3. .![product.category] chuyển mỗi dòng còn lại thành danh mục sản phẩm.
4. approvalService.isAllowed(...) gọi hàm kiểm tra với hồ sơ khách hàng và danh sách danh mục đã tạo.

Phần bên trong lời gọi phương thức có thể chứa property navigation, selection và projection. Mỗi phần có dấu ngoặc và dấu phân tách riêng; không cần làm phẳng tất cả thành một chuỗi khó đọc.

Một ví dụ khác kết hợp map và list:

    {
        customer: {
            name: order.customer.name,
            tier: order.customer.tier
        },
        paidItems: order.lines.?[status == 'PAID'].![product.name],
        summary: {
            subtotal: order.subtotal,
            total: order.total
        }
    }

Biểu thức này tạo một map ngoài với ba khóa customer, paidItems và summary. Giá trị của customer và summary là map con; paidItems là list được tạo bằng selection và projection. Cấu trúc được lồng theo đúng dữ liệu cần biểu diễn.

## 7. Dấu hai chấm và dấu nháy cũng có vai trò riêng

Trong inline map, dấu hai chấm phân tách khóa và giá trị:

    {code:'VN', enabled:true}

Trong toán tử điều kiện ba ngôi, dấu hai chấm phân tách kết quả khi điều kiện sai với kết quả khi điều kiện đúng:

    order.total >= 1000000 ? 'PRIORITY' : 'NORMAL'

Cấu trúc của toán tử là:

    condition ? valueWhenTrue : valueWhenFalse

Vì vậy, cần nhìn ngữ cảnh để phân biệt dấu hai chấm đang nằm trong map hay trong toán tử điều kiện.

Chuỗi ký tự được đặt trong dấu nháy đơn hoặc nháy kép:

    customer.name == 'An'
    message.concat(" approved")

Nếu chuỗi dùng nháy đơn và bản thân nội dung có nháy đơn, SpEL cho phép viết hai dấu nháy đơn liên tiếp:

    'customer''s order'

Dấu phẩy, dấu chấm phẩy, dấu ngoặc hoặc dấu hai chấm nằm bên trong chuỗi literal được xem là dữ liệu văn bản. Chúng không còn mang vai trò phân tách cú pháp ở bên ngoài chuỗi.

## 8. Khoảng trắng và cách định dạng biểu thức dài

SpEL cho phép dùng khoảng trắng, tab và xuống dòng giữa các token. Vì vậy, một biểu thức có thể được xuống dòng để làm rõ từng nhóm:

    (
        order.total >= 1000000
        and order.customer.tier == 'GOLD'
    )
    or order.customer.vip

Khoảng trắng giúp trình bày dễ đọc nhưng không thay đổi ý nghĩa của biểu thức, ngoại trừ khoảng trắng nằm bên trong string literal. Ví dụ 'GOLD MEMBER' là một chuỗi có khoảng trắng thực sự.

Khi biểu thức dài, nên:

- Xuống dòng ở ranh giới đối số hoặc phần tử list/map.
- Thụt lề mỗi cấp cấu trúc lồng nhau.
- Đặt ngoặc rõ ràng quanh các nhóm and/or.
- Dùng tên biến hoặc property có ý nghĩa nghiệp vụ.
- Tách một biểu thức quá dài thành các quy tắc nhỏ trong Java nếu nó khó hiểu hoặc khó kiểm thử.

Không cần thêm dấu chấm phẩy vào cuối biểu thức chỉ vì mã Java xung quanh có dấu chấm phẩy. Chuỗi SpEL chỉ chứa phần biểu thức mà parser cần đọc.

## 9. Những lỗi cú pháp thường gặp

| Cách viết | Vấn đề | Cách viết phù hợp |
|---|---|---|
| a > 0; b > 0 | Dùng dấu chấm phẩy để ghép hai điều kiện | a > 0 and b > 0 |
| calculate(a b) | Thiếu dấu phẩy giữa hai đối số | calculate(a, b) |
| {1; 2; 3} | Dùng dấu chấm phẩy trong inline list | {1, 2, 3} |
| {name 'An'} | Thiếu dấu hai chấm giữa khóa và giá trị map | {name:'An'} |
| orders[0.customer.name | Thiếu dấu ngoặc vuông đóng | orders[0].customer.name |
| (a > 0 and b > 0 | Thiếu dấu ngoặc tròn đóng | (a > 0 and b > 0) |

Khi parser báo lỗi, không nên chỉ nhìn ký tự cuối cùng của thông báo. Hãy kiểm tra từ vị trí lỗi trở về phần cấu trúc gần nhất: dấu ngoặc mở có được đóng chưa, dấu phẩy có nằm giữa hai đối số/phần tử không, và dấu hai chấm có đủ cho cặp khóa-giá trị hoặc nhánh điều kiện không.

## 10. Ví dụ đánh giá bằng Java

Giả sử đối tượng gốc có các thuộc tính total, customer.tier và vip. Có thể parse một biểu thức nhóm điều kiện và đánh giá nó như sau:

    ExpressionParser parser = new SpelExpressionParser();

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    String source =
            "(total >= 1000000 and customer.tier == 'GOLD') or vip";

    Expression expression = parser.parseExpression(source);

    Boolean allowed =
            expression.getValue(context, order, Boolean.class);

parseExpression nhận một chuỗi SpEL. getValue nhận context, đối tượng gốc và kiểu kết quả mong muốn. Các dấu ngoặc trong chuỗi xác định nhóm điều kiện; dấu chấm truy cập thuộc tính lồng nhau. Dấu chấm phẩy kết thúc từng câu lệnh Java bên ngoài chuỗi, không tham gia vào biểu thức được parse.

Trong ứng dụng thực tế, kiểu context phải phù hợp với các thao tác mà biểu thức cần thực hiện. Ví dụ này chỉ đọc thuộc tính nên dùng SimpleEvaluationContext với data binding chỉ đọc. Nếu biểu thức cần tính năng rộng hơn, phải cấu hình context có chủ đích và giới hạn quyền truy cập phù hợp.

## Kết luận

Dấu câu trong SpEL có nhiệm vụ rõ ràng: dấu phẩy phân tách đối số và phần tử; dấu ngoặc tròn gọi phương thức hoặc nhóm biểu thức; dấu ngoặc vuông truy cập, lọc và biến đổi phần tử; dấu ngoặc nhọn tạo list hoặc map; dấu hai chấm phân tách khóa-giá trị hoặc nhánh của toán tử điều kiện. Dấu chấm phẩy không phải dấu phân tách câu lệnh tổng quát của SpEL.

Khi cấu trúc được lồng nhiều cấp, hãy đọc từ trong ra ngoài và giữ thụt lề tương ứng với từng cấp ngoặc. Việc hiểu đúng ranh giới cú pháp giúp parser nhận được biểu thức hợp lệ, đồng thời giúp người bảo trì thấy rõ dữ liệu nào được truy cập, phần nào được nhóm và kết quả nào được truyền sang bước tiếp theo.