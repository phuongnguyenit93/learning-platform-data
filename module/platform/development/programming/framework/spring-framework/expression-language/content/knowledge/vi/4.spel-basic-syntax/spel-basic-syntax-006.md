# Biểu thức lồng trong biểu thức lớn

## Mục tiêu

Sau bài này, bạn có thể đọc và xây dựng một biểu thức SpEL gồm nhiều biểu thức con; hiểu cách toán tử kết hợp, cách dùng dấu ngoặc để thể hiện thứ tự tính toán, và cách lồng truy cập thuộc tính, gọi phương thức, biểu thức điều kiện hoặc thao tác collection. Bạn cũng sẽ biết cách đọc ngữ cảnh #this và #root khi biểu thức lồng nhau, cũng như cách giữ biểu thức dễ bảo trì.

## 1. Biểu thức lớn được tạo từ các biểu thức con

Spring Expression Language (SpEL) cho phép kết hợp nhiều biểu thức nhỏ thành một biểu thức lớn hơn. Mỗi phần nhỏ có thể tạo ra một giá trị, kiểm tra một điều kiện, truy cập một thuộc tính hoặc gọi một phương thức. Kết quả của phần này có thể trở thành đầu vào cho phần tiếp theo.

Ví dụ:

~~~text
(#order.subtotal + #order.shippingFee) * (1 + #taxRate)
~~~

Có thể đọc biểu thức từ trong ra ngoài:

1. Lấy subtotal của đơn hàng.
2. Cộng thêm shippingFee.
3. Tính hệ số thuế bằng 1 + #taxRate.
4. Nhân tổng tiền trước thuế với hệ số thuế.

Các phần #order.subtotal + #order.shippingFee và 1 + #taxRate là những biểu thức con. Toàn bộ phép nhân là biểu thức bao ngoài.

Một biểu thức lớn không phải là nhiều chuỗi SpEL được tự động chạy lần lượt. Parser phân tích toàn bộ cú pháp thành một cấu trúc biểu thức; khi ứng dụng gọi getValue(...), SpEL đánh giá cấu trúc đó và truyền kết quả giữa các phần theo quy tắc của ngôn ngữ.

## 2. Dùng dấu ngoặc để nhóm biểu thức

SpEL có thứ tự ưu tiên toán tử. Các phép nhân và chia thường được thực hiện trước cộng và trừ; các phép so sánh được kết hợp với toán tử logic theo quy tắc ưu tiên của ngôn ngữ.

Ví dụ:

~~~text
#subtotal + #shipping * #quantity
~~~

Phép nhân được thực hiện trước phép cộng. Nếu muốn cộng hai khoản trước rồi mới nhân, hãy nhóm bằng dấu ngoặc:

~~~text
(#subtotal + #shipping) * #quantity
~~~

Dấu ngoặc có hai vai trò quan trọng:

- **Điều khiển thứ tự tính toán:** làm rõ phần nào phải được đánh giá trước.
- **Làm rõ ý định:** giúp người đọc nhận ra ranh giới giữa các biểu thức con, ngay cả khi thứ tự ưu tiên mặc định đã cho cùng một kết quả.

Ví dụ về điều kiện:

~~~text
(#customer != null and #customer.active) or #isAdministrator
~~~

Nhóm hai điều kiện đầu thành một đơn vị logic. Biểu thức chỉ cho kết quả true nếu khách hàng tồn tại và đang hoạt động, hoặc người dùng hiện tại là quản trị viên.

Nên dùng dấu ngoặc khi biểu thức có nhiều toán tử logic hoặc nhiều phép tính lồng nhau. Điều này giảm khả năng người đọc hiểu nhầm thứ tự đánh giá và giúp việc thay đổi biểu thức an toàn hơn.

## 3. Lồng truy cập thuộc tính và phần tử

Một biểu thức có thể tiếp tục truy cập sâu vào kết quả của biểu thức trước đó.

~~~text
#order.customer.address.city
~~~

SpEL lần lượt đọc customer, address và city từ đối tượng order.

Có thể kết hợp truy cập thuộc tính với chỉ số của collection hoặc map:

~~~text
#orders[#selectedIndex].items[#itemIndex].price
~~~

Biểu thức này:

1. Lấy đơn hàng ở vị trí #selectedIndex.
2. Lấy mặt hàng ở vị trí #itemIndex trong đơn hàng đó.
3. Đọc giá price của mặt hàng.

Chỉ số cũng là biểu thức. Ví dụ, có thể tính chỉ số bằng một phép toán:

~~~text
#orders[#page * #pageSize + #offset]
~~~

Khi truy cập nhiều tầng, mỗi phần tử trung gian phải có giá trị và kiểu phù hợp với thao tác kế tiếp. Nếu #orders là null, chỉ số vượt giới hạn hoặc một phần tử không có thuộc tính cần đọc, quá trình đánh giá có thể phát sinh lỗi.

Nếu dữ liệu có thể null, hãy cân nhắc toán tử safe navigation:

~~~text
#order?.customer?.address?.city
~~~

Toán tử ?. giúp tránh tiếp tục truy cập khi tham chiếu ở bên trái là null. Có thể kết hợp với toán tử Elvis để cung cấp giá trị mặc định:

~~~text
#order?.customer?.address?.city ?: 'Chưa có địa chỉ'
~~~

Hãy dùng safe navigation tại những vị trí có khả năng null theo mô hình dữ liệu. Nó không thay thế việc kiểm tra các lỗi khác như sai chỉ số, sai kiểu hoặc gọi phương thức không tồn tại.

## 4. Lồng lời gọi phương thức và đối số

Kết quả của một lời gọi phương thức có thể được dùng làm đối tượng nhận cho lời gọi tiếp theo, hoặc được truyền vào một lời gọi khác.

~~~text
#order.getCustomer().getProfile().getDisplayName()
~~~

SpEL thực hiện các lời gọi theo chuỗi. Khả năng gọi phương thức phụ thuộc vào EvaluationContext, method resolver và quyền truy cập của ứng dụng.

Biểu thức cũng có thể lồng biểu thức con trong danh sách đối số:

~~~text
#pricingService.calculate(
    #order,
    #order.subtotal - #order.discount,
    #taxRate
)
~~~

Trong ví dụ này, phép trừ là một biểu thức con được đánh giá để tạo đối số thứ hai của calculate(...).

Một lời gọi lồng sâu hơn có thể trông như sau:

~~~text
#formatter.format(
    #pricingService.calculate(#order, #taxRate)
)
~~~

Kết quả từ pricingService.calculate(...) trở thành đối số của format(...).

Việc gọi được phương thức không có nghĩa là SpEL tự định nghĩa phương thức đó. Các phương thức và logic nghiệp vụ vẫn được triển khai trong Java. Hãy tránh lồng nhiều lời gọi có tác dụng phụ trong một biểu thức; người bảo trì khó nhìn ra thứ tự gọi, lỗi phát sinh và trạng thái bị thay đổi.

## 5. Lồng toán tử điều kiện

Toán tử ba ngôi ? : cho phép chọn một giá trị dựa trên điều kiện. Một nhánh có thể chứa một biểu thức lớn hơn hoặc một toán tử ba ngôi khác.

~~~text
#order == null
    ? 'MISSING'
    : (#order.total >= #threshold ? 'REVIEW' : 'NORMAL')
~~~

Cách đọc:

- Nếu #order là null, trả về MISSING.
- Nếu đơn hàng tồn tại, tiếp tục đánh giá điều kiện lồng bên trong.
- Nếu tổng tiền đạt ngưỡng, trả về REVIEW; nếu không, trả về NORMAL.

Các nhánh của toán tử ba ngôi là biểu thức, vì vậy chúng có thể chứa phép tính, truy cập thuộc tính hoặc lời gọi phương thức.

Có thể kết hợp điều kiện với toán tử logic:

~~~text
#order != null and
    (#order.cancelled or #order.total >= #threshold)
~~~

Khi biểu thức trở nên dài, hãy dùng dấu ngoặc và xuống dòng trong chuỗi biểu thức để thể hiện cấu trúc. Đừng lồng nhiều tầng điều kiện nếu có thể đặt một quy tắc đã được đặt tên trong Java hoặc cung cấp một biến có ý nghĩa từ context.

## 6. Biểu thức lồng trong selection và projection

SpEL có các toán tử làm việc với collection:

- Selection .?[...] lọc các phần tử thỏa điều kiện.
- Projection .![...] tạo collection mới bằng cách đánh giá biểu thức cho từng phần tử.
- .^[...] lấy phần tử đầu tiên thỏa điều kiện.
- .$[...] lấy phần tử cuối cùng thỏa điều kiện.

Phần điều kiện hoặc phần chiếu bên trong dấu ngoặc vuông cũng là biểu thức. Vì vậy, nó có thể chứa phép so sánh, truy cập thuộc tính, toán tử logic hoặc lời gọi phương thức.

Ví dụ, lọc các đơn hàng có tổng tiền đạt ngưỡng rồi lấy mã đơn hàng:

~~~text
#orders.?[total >= #minimum].![id]
~~~

Có thể lồng selection để tìm các đơn hàng có ít nhất một mặt hàng mang mã SKU cần tìm:

~~~text
#orders.?[items.?[sku == #targetSku].size() > 0].![id]
~~~

Cách đọc biểu thức:

1. Duyệt từng đơn hàng trong #orders.
2. Với mỗi đơn hàng, lọc collection items để tìm các mặt hàng có sku bằng #targetSku.
3. Lấy số phần tử tìm được bằng size().
4. Giữ lại đơn hàng nếu số phần tử lớn hơn 0.
5. Chiếu danh sách đơn hàng còn lại thành danh sách id.

### 6.1. Hiểu #this và #root khi lồng collection

Trong selection hoặc projection, #this đại diện cho phần tử hiện tại đang được xử lý. Khi đi vào một selection lồng bên trong, đối tượng hiện tại thay đổi sang phần tử của collection bên trong.

#root đại diện cho root object của lần đánh giá biểu thức và giữ vai trò tham chiếu đến đối tượng gốc đó. Vì vậy, không nên nhầm #this với #root trong biểu thức lồng.

Ví dụ khái niệm:

~~~text
#orders.?[
    items.?[
        sku == #targetSku
    ].size() > 0
]
~~~

Trong selection ngoài, #this là một đơn hàng. Trong selection bên trong, #this là một mặt hàng. Nếu điều kiện bên trong cần dùng dữ liệu của root object, có thể tham chiếu #root hoặc một biến được đặt rõ trong context.

Khi đọc một biểu thức collection lồng, hãy xác định collection nào đang được duyệt tại từng cặp .?[...] hoặc .![...]. Đây là cách tránh lỗi dùng nhầm thuộc tính của đơn hàng trên một mặt hàng, hoặc ngược lại.

## 7. Lồng biểu thức trong một biểu thức mẫu (template)

SpEL còn hỗ trợ biểu thức mẫu khi parser được tạo với TemplateParserContext hoặc một ParserContext tương ứng. Template có thể chứa văn bản thông thường và các đoạn SpEL được đặt giữa dấu phân cách.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Đơn hàng #{#order.id} có tổng tiền #{#order.subtotal + #order.shippingFee}",
    templateContext
);

String message = expression.getValue(context, String.class);
~~~

Trong ví dụ, toàn bộ chuỗi là một template. Hai đoạn nằm trong #{...} là biểu thức SpEL được đánh giá và chèn vào văn bản kết quả. Bên trong đoạn thứ hai lại có biểu thức con thực hiện phép cộng.

Cần phân biệt:

- (#a + #b) * #rate là một biểu thức SpEL có các biểu thức con.
- "Tổng tiền: #{#a + #b}" chỉ được xử lý như template nếu parser nhận ParserContext phù hợp.
- Một chuỗi ký tự thông thường chứa #{...} không tự động được phân tích đệ quy như một biểu thức mới.

Nếu ứng dụng nhận một chuỗi rồi muốn phân tích chuỗi đó thành biểu thức SpEL riêng, mã Java phải chủ động gọi parser lần nữa. Không nên tự động đánh giá các chuỗi không đáng tin cậy chỉ vì chúng chứa cú pháp trông giống SpEL.

## 8. Cách SpEL đánh giá biểu thức lồng

Parser phân tích toàn bộ biểu thức và tạo cấu trúc nội bộ biểu diễn các toán hạng, toán tử, thuộc tính, lời gọi phương thức và các phần tử khác. Khi gọi getValue(...), SpEL đánh giá các phần theo quy tắc ngữ nghĩa và thứ tự phụ thuộc vào cấu trúc biểu thức.

Một số điểm cần nhớ:

- Các biểu thức con tạo ra giá trị cho phép toán hoặc lời gọi bao ngoài.
- Dấu ngoặc xác định nhóm biểu thức và làm rõ thứ tự.
- Nhánh không được chọn của toán tử ba ngôi không cần được đánh giá để tạo kết quả của nhánh còn lại.
- Các phép logic có thể dùng đánh giá ngắn mạch; ví dụ vế phải của and không cần đánh giá nếu vế trái đã là false.
- Collection selection và projection đánh giá biểu thức bên trong cho từng phần tử tương ứng.
- Lỗi trong một biểu thức con có thể làm toàn bộ lần đánh giá thất bại.

Không nên dựa vào tác dụng phụ để suy luận thứ tự thực thi của các phần không có quan hệ thứ tự được bảo đảm. Hãy giữ các biểu thức tập trung vào tính toán và truy cập dữ liệu; đặt quy trình thay đổi trạng thái trong mã Java có cấu trúc rõ ràng.

## 9. Phân tích lỗi trong biểu thức lồng

Một biểu thức càng nhiều tầng thì càng có nhiều vị trí có thể phát sinh lỗi. Có thể chia lỗi thành hai nhóm:

### 9.1. Lỗi phân tích cú pháp

Parser phát hiện lỗi khi chuỗi không tuân theo cú pháp SpEL, ví dụ:

- Thiếu dấu ngoặc đóng.
- Thiếu toán hạng giữa hai toán tử.
- Dùng sai dấu phân cách của selection hoặc projection.
- Viết sai cú pháp toán tử ba ngôi.
- Đặt dấu nháy chuỗi không cân bằng.

Lỗi cú pháp thường được phát hiện khi gọi parseExpression(...), trước khi đánh giá với dữ liệu thực tế.

### 9.2. Lỗi khi đánh giá

Một biểu thức có thể parse thành công nhưng thất bại lúc chạy, chẳng hạn:

- Tham chiếu null ở vị trí không hỗ trợ truy cập an toàn.
- Chỉ số collection nằm ngoài phạm vi.
- Đối tượng không có thuộc tính hoặc phương thức được yêu cầu.
- Phương thức được gọi ném ngoại lệ.
- Không thể chuyển đổi kết quả sang kiểu đích.
- Collection chứa phần tử không có cấu trúc mà biểu thức kỳ vọng.

Khi gỡ lỗi, hãy tách biểu thức lớn thành những phần nhỏ và đánh giá từng phần bằng dữ liệu đại diện. Có thể tạo các Expression riêng cho mục đích chẩn đoán trong mã Java, hoặc tạm đưa kết quả trung gian vào biến của context. Sau khi xác định được phần gây lỗi, ghép lại biểu thức hoàn chỉnh.

Không cần biến một biểu thức nghiệp vụ dài thành nhiều lần parse ở production. Việc tách nhỏ chỉ là kỹ thuật giúp xác định vị trí lỗi; cách triển khai cuối cùng nên phù hợp với vòng đời và yêu cầu của ứng dụng.

## 10. Giữ biểu thức lồng dễ đọc và dễ bảo trì

Một biểu thức lớn có thể ngắn hơn nhiều dòng Java, nhưng càng lồng sâu càng khó hiểu. Hãy áp dụng các nguyên tắc sau:

1. **Đặt tên biến có ý nghĩa:** dùng #minimumTotal hoặc #targetSku thay cho các tên khó đoán.
2. **Nhóm bằng dấu ngoặc:** thể hiện rõ các phép tính và điều kiện liên quan.
3. **Dùng xuống dòng có chủ đích:** mỗi tầng selection, điều kiện hoặc lời gọi lớn nên có ranh giới dễ nhận biết.
4. **Tránh lồng quá nhiều lời gọi có tác dụng phụ:** một biểu thức nên chủ yếu đọc dữ liệu và tạo kết quả.
5. **Tách logic phức tạp sang Java:** nếu cần nhiều bước nghiệp vụ, vòng lặp, xử lý ngoại lệ hoặc điều phối service, hãy viết một phương thức Java có tên rõ ràng.
6. **Kiểm soát context:** chỉ cung cấp root object, biến, bean và method resolver mà biểu thức thực sự cần.
7. **Kiểm thử cả dữ liệu biên:** đặc biệt là null, collection rỗng, chỉ số không hợp lệ và các kiểu dữ liệu có thể thay đổi.

Một biểu thức như:

~~~text
#order != null and
    #order.customer != null and
    #order.customer.active and
    (#order.total >= #minimum or #order.priority)
~~~

có thể dễ hiểu nếu được nhóm rõ ràng. Nếu biểu thức tiếp tục lồng nhiều collection, lời gọi dịch vụ và điều kiện nghiệp vụ, hãy cân nhắc chuyển phần logic vào Java rồi để SpEL chỉ tham chiếu một giá trị hoặc gọi một phương thức nhỏ được kiểm soát.

## 11. Ví dụ tổng hợp

Giả sử ứng dụng có một danh sách đơn hàng. Mục tiêu là lấy mã các đơn hàng có trạng thái đã thanh toán và chứa ít nhất một mặt hàng thuộc SKU được chọn.

~~~text
#orders.?[
    status == 'PAID' and
    items.?[sku == #targetSku].size() > 0
].![id]
~~~

Biểu thức này kết hợp nhiều lớp:

- Selection ngoài duyệt các đơn hàng.
- Điều kiện thứ nhất kiểm tra status.
- Điều kiện thứ hai lồng một selection trên danh sách items.
- size() kiểm tra có ít nhất một mặt hàng phù hợp.
- Projection cuối cùng lấy id của những đơn hàng được giữ lại.

Có thể đánh giá biểu thức bằng Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
    "#orders.?[status == 'PAID' and items.?[sku == #targetSku].size() > 0].![id]"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("targetSku", "SKU-100");

List<?> orderIds = expression.getValue(context, List.class);
~~~

Trong ứng dụng thực tế, kiểu dữ liệu của orders, items và các thuộc tính cần thiết phải phù hợp với biểu thức. Nếu dữ liệu không đảm bảo, hãy xử lý null và kiểm tra collection ở lớp Java trước khi đánh giá.

## 12. Ghi nhớ

Biểu thức SpEL lớn được cấu thành từ các biểu thức con. Các biểu thức con có thể là phép tính, điều kiện, truy cập thuộc tính, truy cập chỉ số, lời gọi phương thức, selection hoặc projection. Kết quả của một phần có thể trở thành toán hạng, đối số hoặc điều kiện của phần khác.

Dấu ngoặc giúp nhóm biểu thức và làm rõ thứ tự tính toán. Khi lồng collection, cần theo dõi #this vì đối tượng hiện tại thay đổi theo collection đang được xử lý; #root vẫn tham chiếu đối tượng gốc của lần đánh giá.

Parser phân tích toàn bộ cú pháp; SpEL không tự động parse đệ quy mọi chuỗi kết quả. Template chỉ hoạt động khi dùng parser context phù hợp. Lỗi có thể xuất hiện khi parse hoặc khi đánh giá với dữ liệu thực tế.

Hãy giữ biểu thức ngắn gọn, có dấu ngoặc và tên biến rõ ràng. Khi cấu trúc lồng bắt đầu che khuất quy tắc nghiệp vụ, chuyển phần logic đó vào Java và để SpEL đảm nhiệm biểu thức cấu hình nhỏ, dễ hiểu.