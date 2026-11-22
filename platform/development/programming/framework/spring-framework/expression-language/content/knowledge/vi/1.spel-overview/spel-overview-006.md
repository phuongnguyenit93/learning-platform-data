# Khả năng đọc, khả năng kiểm tra và rủi ro khi biểu thức thay đổi

## Mục tiêu

Trong Spring Framework Expression Language (SpEL), biểu thức thường được lưu dưới dạng chuỗi và được phân tích, đánh giá trong một ngữ cảnh do ứng dụng cung cấp. Cách làm này giúp cấu hình hoặc chính sách có thể thay đổi mà không phải viết lại luồng Java, nhưng cũng tạo ra một phụ thuộc ít hiển thị hơn so với lời gọi phương thức thông thường.

Sau bài này, bạn có thể:

- Viết biểu thức ngắn, dễ đọc và thể hiện rõ điều kiện nghiệp vụ.
- Xác định dữ liệu gốc, biến, bean và các khả năng mà EvaluationContext cho phép biểu thức sử dụng.
- Kiểm tra cú pháp và hành vi của biểu thức bằng các bài kiểm thử có thể lặp lại.
- Nhận diện những thay đổi trong model, kiểu dữ liệu hoặc ngữ cảnh có thể làm biểu thức hỏng.
- Giới hạn rủi ro khi biểu thức được lưu trong cấu hình hoặc được cập nhật trong lúc ứng dụng đang chạy.

## 1. Vì sao khả năng đọc của SpEL quan trọng?

SpEL là một ngôn ngữ biểu thức. Một chuỗi như **order.total >= 100** có thể được phân tích rồi đánh giá trên một đối tượng Order. Mã Java gọi trực tiếp một phương thức thường để lộ kiểu và tên phương thức qua compiler; biểu thức SpEL lại tham chiếu thuộc tính và phương thức bằng tên ở dạng chuỗi. Vì vậy, một thay đổi trong model có thể không được compiler phát hiện tại thời điểm build.

Hãy xem biểu thức sau:

~~~text
order.customer?.active and order.total >= #minimum
~~~

Người đọc có thể nhận ra ba thành phần: khách hàng, trạng thái hoạt động và tổng đơn hàng so với ngưỡng. Biểu thức vẫn đủ ngắn để kiểm tra bằng mắt. Ngược lại, nếu một biểu thức chứa nhiều tầng điều kiện lồng nhau, truy cập collection, gọi phương thức có tác dụng phụ và tham chiếu nhiều biến, người bảo trì sẽ khó biết phần nào quyết định kết quả.

Một biểu thức tốt nên trả lời được ba câu hỏi:

1. Đối tượng nào đang được đánh giá?
2. Giá trị phụ thuộc nào được đưa vào từ bên ngoài?
3. Kết quả biểu thức có ý nghĩa gì trong nghiệp vụ?

Nếu phải đọc thêm nhiều lớp Java mới trả lời được các câu hỏi này, hãy xem xét tách logic thành một phương thức nghiệp vụ có tên rõ ràng, hoặc chia biểu thức thành những phần nhỏ được đặt tên và kiểm thử riêng.

## 2. Làm rõ dữ liệu và ngữ cảnh đánh giá

SpEL không tự biết ứng dụng muốn đánh giá đối tượng nào. Ứng dụng truyền một root object và một EvaluationContext cho Expression.

- **Root object** là đối tượng mặc định mà biểu thức truy cập. Với root là Order, biểu thức **total** tương đương việc đọc thuộc tính total trên Order.
- **EvaluationContext** cung cấp cách đọc thuộc tính, gọi phương thức, phân giải kiểu, bean, hàm và biến. Những khả năng thực tế phụ thuộc vào loại context và các resolver/accessor được cấu hình.
- **Biến** được tham chiếu bằng dấu #, ví dụ **#minimum** hoặc **#region**.
- **#root** luôn chỉ root object. **#this** chỉ đối tượng hiện tại trong một phần đánh giá; điều này đặc biệt hữu ích trong selection và projection trên collection.
- **Bean reference** dùng cú pháp **@beanName**, nhưng chỉ hoạt động khi context có BeanResolver phù hợp.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("total >= #minimum");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
context.setVariable("minimum", new BigDecimal("100.00"));

Boolean accepted = expression.getValue(context, order, Boolean.class);
~~~

Trong ví dụ này, root object là order, còn ngưỡng minimum là biến được truyền qua context. Việc đưa ngưỡng vào biến giúp biểu thức không phải chứa một con số cố định và cho phép bài kiểm thử thay đổi dữ liệu đầu vào một cách rõ ràng.

Nên ghi lại hợp đồng của mỗi biểu thức ở nơi quản lý nó: loại root object, tên và kiểu các biến, kiểu kết quả mong đợi, cùng những khả năng context được phép sử dụng. Hợp đồng này giúp người thay đổi biểu thức biết cần giữ tương thích với phần nào của ứng dụng.

## 3. Các quy tắc giúp biểu thức dễ đọc

### Giữ một ý nghiệp vụ chính trong mỗi biểu thức

Ưu tiên điều kiện có thể diễn đạt thành một câu. Dùng ngoặc để thể hiện nhóm logic khi có nhiều toán tử:

~~~text
(order.status == 'PAID' or order.status == 'SHIPPED')
and order.total >= #minimum
~~~

Không dựa hoàn toàn vào trí nhớ về độ ưu tiên toán tử khi biểu thức có nhiều AND/OR. Ngoặc làm rõ ý định và giúp việc sửa điều kiện an toàn hơn.

### Đặt tên biến theo ý nghĩa nghiệp vụ

Tên như **#minimumEligibleTotal**, **#allowedRegion** hoặc **#reviewRequired** dễ hiểu hơn tên chung chung như **#x**, **#v1**. Biến nên biểu diễn dữ liệu đầu vào hoặc một khái niệm đã được xác định trong ứng dụng.

### Xử lý null có chủ đích

Toán tử safe navigation **?.** cho phép truy cập thuộc tính hoặc gọi phương thức mà không gây lỗi chỉ vì đối tượng ở bên trái là null:

~~~text
order.customer?.name
~~~

Toán tử Elvis **?:** có thể cung cấp giá trị mặc định khi biểu thức bên trái không có giá trị phù hợp:

~~~text
order.customer?.name ?: 'Khách lẻ'
~~~

Hãy chọn mặc định dựa trên nghiệp vụ. Một giá trị mặc định có thể khiến biểu thức tiếp tục chạy nhưng che giấu dữ liệu bị thiếu. Nếu khách hàng bắt buộc phải tồn tại, kiểm tra null và báo lỗi rõ ràng có thể đúng hơn việc tự thay bằng một tên mặc định.

Safe navigation cũng không thay thế việc xác định hợp đồng dữ liệu. Nếu biểu thức truy cập nhiều thuộc tính nối tiếp, hãy kiểm tra từng điểm có thể null và kiểm thử trường hợp đó.

### Dùng collection operation vừa đủ

SpEL hỗ trợ các thao tác thường gặp trên collection:

- Selection **.?[condition]** lọc phần tử thỏa điều kiện.
- Projection **.![expression]** tạo collection mới từ kết quả của biểu thức trên từng phần tử.
- Truy cập chỉ số như **[0]** lấy một phần tử theo vị trí.

Ví dụ:

~~~text
#root.items.?[active].![code]
~~~

Biểu thức trên lọc các item đang active rồi lấy code của từng item. Nó ngắn gọn, nhưng người đọc vẫn cần biết items có thể null hay rỗng hay không, active có phải thuộc tính Boolean hay không, và code có thể null hay không.

Đặc biệt cẩn thận với truy cập chỉ số. Biểu thức **items[0]** có thể hoạt động với collection không rỗng nhưng lỗi khi collection rỗng. Nếu kết quả phụ thuộc vào phần tử đầu tiên, hãy xác định rõ hành vi cho collection rỗng và có bài kiểm thử tương ứng.

### Tránh gọi phương thức có tác dụng phụ

Biểu thức dùng để quyết định hoặc đọc dữ liệu nên có tính quan sát được và dễ lặp lại. Tránh gọi phương thức ghi database, gửi thông báo, thay đổi trạng thái hoặc sửa collection trong lúc đánh giá. Một biểu thức có thể được đánh giá nhiều lần, tại nhiều vị trí hoặc trong quá trình kiểm tra; tác dụng phụ sẽ làm kết quả khó dự đoán.

Nếu nghiệp vụ cần thay đổi dữ liệu, thực hiện hành động đó trong service Java có tên rõ ràng. Dùng SpEL để chọn hoặc đánh giá điều kiện, không biến nó thành nơi thực thi quy trình.

## 4. Chọn EvaluationContext theo mức quyền cần thiết

Loại context ảnh hưởng trực tiếp đến những gì một biểu thức có thể làm.

**StandardEvaluationContext** cung cấp khả năng mở rộng mạnh: property accessor, method resolver, constructor resolver, type locator, bean resolver và biến. Nó phù hợp khi ứng dụng chủ động cần các khả năng đó và kiểm soát được nguồn biểu thức.

**SimpleEvaluationContext** được thiết kế cho các trường hợp data binding với phạm vi khả năng hạn chế hơn. Có thể xây dựng context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Nếu thực sự cần gọi instance method, ứng dụng có thể cấu hình thêm khả năng đó bằng builder tương ứng. Chỉ bật những gì biểu thức cần và mô tả rõ trong hợp đồng của biểu thức.

Không nên đánh giá chuỗi do người dùng hoặc nguồn bên ngoài tùy ý cung cấp bằng một StandardEvaluationContext có đầy đủ quyền. Một biểu thức không đáng tin có thể cố truy cập phương thức, kiểu hoặc bean mà ứng dụng không định cho phép. Khi cần biểu thức do người dùng cấu hình, hãy giới hạn cú pháp và context, kiểm soát quyền truy cập, giới hạn độ dài/độ phức tạp và kiểm thử các trường hợp bị từ chối.

Việc chọn context cũng là một phần của tính tương thích. Một biểu thức có thể chạy trong StandardEvaluationContext nhưng thất bại khi chuyển sang SimpleEvaluationContext vì method resolver, bean resolver hoặc khả năng khác không còn được bật. Hãy xem thay đổi context như thay đổi hợp đồng, không chỉ là thay đổi cấu hình nội bộ.

## 5. Kiểm thử biểu thức một cách có hệ thống

Một bài kiểm thử SpEL nên xác minh cả cú pháp lẫn kết quả đánh giá. Đừng chỉ kiểm tra rằng parser không ném lỗi: một biểu thức hợp lệ về cú pháp vẫn có thể trả kết quả sai khi dữ liệu thay đổi.

### Kiểm tra cú pháp

Phân tích biểu thức trong kiểm thử hoặc khi nạp cấu hình để phát hiện lỗi cú pháp sớm:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertDoesNotThrow(() ->
    parser.parseExpression("total >= #minimum")
);
~~~

Nếu biểu thức nằm trong cấu hình hoặc kho chính sách, có thể kiểm tra tất cả biểu thức tại thời điểm nạp để lỗi được phát hiện trước khi nhận yêu cầu thực tế. Cần báo tên/ID biểu thức và vị trí cấu hình để người vận hành tìm đúng nguồn.

### Kiểm tra kết quả với root object và context thực tế

~~~java
@Test
void acceptsOrderAtMinimumThreshold() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("total >= #minimum");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
    context.setVariable("minimum", new BigDecimal("100.00"));

    Order order = new Order(new BigDecimal("100.00"));

    Boolean result = expression.getValue(context, order, Boolean.class);

    assertEquals(Boolean.TRUE, result);
}
~~~

Bài kiểm thử dùng cùng loại context, root object và kiểu kết quả mà ứng dụng thực tế sử dụng. Nếu production thêm biến, custom accessor hoặc bean resolver, hãy đưa cấu hình tương ứng vào một factory dùng chung để kiểm thử và ứng dụng không vô tình đánh giá trong hai môi trường khác nhau.

### Tạo bộ trường hợp biên

Với biểu thức kiểm tra điều kiện đơn hàng, tối thiểu nên xem xét:

| Trường hợp | Điều cần xác minh |
|---|---|
| Giá trị đúng bằng ngưỡng | Ranh giới >= có đúng ý định không |
| Giá trị thấp hơn ngưỡng | Biểu thức trả false như mong đợi |
| Root object null | Ứng dụng từ chối hoặc xử lý theo hợp đồng |
| Thuộc tính trung gian null | Safe navigation/default có đúng ý định |
| Collection rỗng | Selection, projection hoặc truy cập chỉ số có hành vi xác định |
| Biến chưa được cung cấp | Lỗi được phát hiện và báo đủ ngữ cảnh |
| Kiểu dữ liệu thay đổi | Conversion hoặc phép so sánh có còn hợp lệ |
| Giá trị ngoài miền dự kiến | Kết quả và lỗi có được xử lý rõ ràng |

Không phải biểu thức nào cũng cần mọi trường hợp trên. Hãy chọn các trường hợp dựa trên root object, biến, phép toán và cấu trúc dữ liệu mà biểu thức thực sự sử dụng.

### Kiểm tra kiểu kết quả

Nếu biểu thức được kỳ vọng trả về Boolean, hãy yêu cầu kiểu Boolean khi gọi **getValue**:

~~~java
Boolean decision = expression.getValue(context, rootObject, Boolean.class);
~~~

Điều này giúp phát hiện biểu thức trả về kiểu không phù hợp tại điểm đánh giá. Đừng chuyển mọi kết quả thành chuỗi rồi tự diễn giải bằng logic khác; kiểu kết quả nên được quy định ngay trong hợp đồng.

### Kiểm tra lỗi đánh giá

Tách lỗi phân tích cú pháp khỏi lỗi khi đánh giá. ParseException thường chỉ ra chuỗi biểu thức không hợp lệ. EvaluationException thường liên quan đến thuộc tính không tồn tại, phương thức không thể gọi, biến hoặc bean không được phân giải, dữ liệu null, hoặc chuyển đổi kiểu thất bại.

Trong log, ưu tiên ghi ID biểu thức, phiên bản, thời điểm, loại lỗi và correlation ID của yêu cầu. Tránh ghi toàn bộ dữ liệu nhạy cảm của root object hoặc biến chỉ để chẩn đoán.

## 6. Rủi ro khi biểu thức thay đổi

Biểu thức là một hợp đồng runtime giữa chuỗi SpEL, model Java và EvaluationContext. Thay đổi ở bất kỳ thành phần nào cũng có thể ảnh hưởng đến kết quả.

### Đổi tên hoặc cấu trúc thuộc tính

Nếu **customer.active** đổi thành **customer.enabled**, compiler Java không nhất thiết phát hiện chuỗi SpEL cũ. Biểu thức có thể chỉ lỗi khi một luồng nghiệp vụ cụ thể được chạy. Khi refactor model, tìm cả các biểu thức được lưu trong annotation, XML, cấu hình, database hoặc hệ thống quản trị chính sách.

### Đổi kiểu dữ liệu hoặc ngữ nghĩa

Một thuộc tính có thể vẫn tồn tại nhưng đổi từ Integer sang String, từ số tiền sang một kiểu tiền tệ, hoặc từ Boolean sang trạng thái nhiều giá trị. Biểu thức vẫn có thể parse nhưng phép so sánh, conversion hoặc ý nghĩa nghiệp vụ đã thay đổi. Cần kiểm tra kiểu và ngữ nghĩa, không chỉ tên thuộc tính.

### Thay đổi nullability và cardinality

Một thuộc tính trước đây luôn có giá trị có thể trở thành nullable. Collection trước đây luôn có phần tử có thể rỗng. Truy cập thuộc tính nối tiếp hoặc **[0]** có thể bắt đầu thất bại. Ngược lại, thêm một giá trị mặc định có thể làm lỗi dữ liệu bị che đi và khiến quyết định nghiệp vụ thay đổi âm thầm.

### Thay đổi EvaluationContext

Tắt một method resolver, thay đổi property accessor, bỏ BeanResolver hoặc chuyển từ StandardEvaluationContext sang SimpleEvaluationContext có thể khiến biểu thức hiện tại không còn chạy. Ngược lại, bật thêm khả năng có thể mở rộng quyền của biểu thức vượt quá dự kiến.

### Thay đổi thứ tự hoặc cách kết hợp điều kiện

Sửa **and** thành **or**, bỏ ngoặc hoặc thay đổi ngưỡng có thể làm tập đối tượng được chấp nhận thay đổi đáng kể. Các trường hợp ở ranh giới và tổ hợp điều kiện cần được kiểm thử như một phần của review.

### Thay đổi phương thức được gọi

Một phương thức có thể đổi tên, tham số, kiểu trả về hoặc tác dụng phụ. Vì tên phương thức trong SpEL là chuỗi, refactor thông thường có thể không tìm được tất cả nơi tham chiếu. Tránh để biểu thức phụ thuộc vào nhiều phương thức nội bộ hoặc phương thức có logic phức tạp.

### Thay đổi nguồn biểu thức

Nếu biểu thức được lưu bên ngoài mã nguồn và có thể chỉnh sửa lúc ứng dụng đang chạy, hai instance có thể đánh giá hai phiên bản khác nhau trong giai đoạn triển khai. Cần xác định cách phân phối, cache, hiệu lực, rollback và nhận diện phiên bản. Một biểu thức mới nên được parse và kiểm tra trước khi trở thành phiên bản đang hoạt động.

## 7. Quy trình thay đổi biểu thức an toàn

Khi sửa một biểu thức đang được sử dụng:

1. **Xác định nguồn và người sở hữu.** Tìm nơi lưu chuỗi, ID biểu thức, nơi nạp, nơi cache và các luồng gọi nó.
2. **Ghi lại hợp đồng hiện tại.** Ghi root type, biến, bean/function được phép dùng, context, kiểu kết quả và ý nghĩa nghiệp vụ.
3. **Tạo ví dụ đầu vào đại diện.** Bao gồm trường hợp thông thường, ranh giới, null, collection rỗng và dữ liệu sai nếu chúng có liên quan.
4. **Sửa biểu thức và kiểm thử độc lập.** Parse biểu thức mới rồi đánh giá trên cùng context và bộ dữ liệu.
5. **So sánh kết quả cũ và mới.** Với chính sách quyết định quyền, giá, hạn mức hoặc trạng thái, xem xét các trường hợp mà kết quả thay đổi và xác nhận chúng là chủ ý.
6. **Triển khai có khả năng quay lại.** Nếu biểu thức được cập nhật ngoài ứng dụng, lưu phiên bản trước, ID phiên bản mới và cách khôi phục. Không thay thế phiên bản đang hoạt động trước khi phiên bản mới được xác thực.
7. **Theo dõi lỗi sau triển khai.** Theo dõi lỗi parse/evaluation theo ID và phiên bản biểu thức, tỷ lệ kết quả bất thường và các luồng nghiệp vụ bị ảnh hưởng.

Với biểu thức cố định trong mã nguồn, nên tập trung vào kiểm thử hồi quy cùng thay đổi model. Với biểu thức chỉnh sửa được lúc chạy, cần thêm kiểm tra trước khi kích hoạt, quản lý phiên bản và cơ chế rollback.

## 8. Quản lý biểu thức trong ứng dụng

Một vài quy tắc tổ chức giúp giảm chi phí bảo trì:

- Đặt biểu thức trong một vị trí có tên hoặc ID ổn định thay vì lặp lại chuỗi ở nhiều lớp.
- Lưu mô tả ngắn về mục đích, root type, biến và kiểu kết quả bên cạnh biểu thức.
- Dùng một factory hoặc cấu hình chung để tạo EvaluationContext giống nhau giữa production và test.
- Parse một lần khi nạp hoặc cập nhật biểu thức rồi tái sử dụng đối tượng Expression khi phù hợp; tránh parse lại cùng chuỗi cho từng bản ghi nếu không cần thiết.
- Nếu bật SpEL compiler để tối ưu hiệu năng, đo đạc trước và kiểm thử với đúng tập biểu thức/model thực tế. Không xem compiler mode là biện pháp sửa một biểu thức quá phức tạp.
- Không để người dùng cuối nhập một chuỗi SpEL tùy ý vào trường tìm kiếm hoặc form thông thường. Nếu sản phẩm cần trình soạn thảo chính sách, cung cấp tập khả năng được giới hạn và xác thực riêng.
- Khi cần chẩn đoán, ghi ID và phiên bản biểu thức, không phụ thuộc vào việc log toàn bộ nội dung dữ liệu đầu vào.

## 9. Checklist review

Trước khi chấp nhận một thay đổi liên quan đến SpEL, hãy kiểm tra:

- [ ] Biểu thức có thể được đọc và giải thích bằng một câu ngắn.
- [ ] Root object, biến và kiểu kết quả được xác định rõ.
- [ ] EvaluationContext chỉ bật những khả năng cần thiết.
- [ ] Các điểm có thể null, collection rỗng và truy cập chỉ số đã được xem xét.
- [ ] Biểu thức được parse trong kiểm thử hoặc bước nạp cấu hình.
- [ ] Kết quả được kiểm thử với dữ liệu thường, dữ liệu biên và dữ liệu không hợp lệ có liên quan.
- [ ] Thay đổi tên/kiểu thuộc tính và phương thức đã được đối chiếu với các chuỗi biểu thức.
- [ ] Nếu biểu thức được cập nhật lúc chạy, phiên bản mới có xác thực và có cách rollback.
- [ ] Log và thông báo lỗi đủ để xác định biểu thức gây lỗi mà không làm lộ dữ liệu nhạy cảm.

## Kết luận

SpEL dễ bảo trì khi biểu thức ngắn, có hợp đồng dữ liệu rõ ràng, được đánh giá trong EvaluationContext có phạm vi phù hợp và có bài kiểm thử mô tả hành vi. Vì biểu thức là chuỗi được kiểm tra ở runtime, mọi thay đổi về model, kiểu dữ liệu, context hoặc nguồn cấu hình đều cần được xem là thay đổi hợp đồng. Tập trung vào khả năng đọc, kiểm thử ranh giới và quản lý phiên bản sẽ giúp các biểu thức tiếp tục phản ánh đúng nghiệp vụ khi ứng dụng phát triển.
