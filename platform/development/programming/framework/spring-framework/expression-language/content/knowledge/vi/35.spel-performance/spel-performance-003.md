# Chi phí EvaluationContext và object graph trong SpEL

Hiệu năng của Spring Expression Language (SpEL) phụ thuộc vào nhiều bước: parse expression, chuẩn bị EvaluationContext, phân giải property và method, rồi thực thi các thao tác trên object graph. Khi expression được đánh giá nhiều lần, chi phí tạo context lặp lại hoặc parse lại cùng một chuỗi có thể trở nên đáng kể. Khi object graph lớn hoặc expression duyệt collection, phần truy cập dữ liệu và tạo kết quả trung gian thường chiếm phần lớn công việc.

Tối ưu đúng cách cần tách các chi phí này ra. Hãy parse expression một lần khi có thể, chỉ cung cấp những khả năng context cần thiết, quản lý context theo đúng phạm vi request và viết expression chỉ truy cập phần object graph thực sự cần dùng. Với collection lớn hoặc logic lồng nhau phức tạp, hãy cân nhắc chuyển phần xử lý đó sang Java.

## 1. Những thành phần tạo nên chi phí evaluation

Một lần đánh giá SpEL có thể bao gồm các công việc sau:

1. **Parse expression:** chuyển chuỗi expression thành đối tượng Expression và cấu trúc nội bộ.
2. **Chuẩn bị EvaluationContext:** cung cấp root object, variables, functions, property accessors, method resolvers, type converter, bean resolver và các chiến lược liên quan.
3. **Resolve property hoặc method:** tìm cách đọc property hoặc gọi method trên object hiện tại.
4. **Duyệt object graph:** lần theo các property lồng nhau, phần tử collection hoặc key của Map.
5. **Thực hiện phép toán và chuyển đổi:** so sánh, tính toán, gọi converter hoặc operator.
6. **Tạo kết quả:** tạo String, collection hoặc object trung gian nếu expression yêu cầu.

Không phải expression nào cũng thực hiện tất cả các bước. Ví dụ, một phép so sánh trên variable đơn giản có ít thao tác hơn một expression gọi bean method, truy cập nhiều property lồng nhau rồi lọc collection.

Khi tối ưu, hãy xác định bước nào đang chiếm thời gian thực tế thay vì chỉ nhìn vào độ dài chuỗi expression.

## 2. Chi phí tạo và cấu hình EvaluationContext

EvaluationContext cung cấp môi trường mà expression sử dụng khi đánh giá. Nó không chỉ chứa root object mà còn có thể chứa variables, functions, property accessors, method resolvers, bean resolver, type locator, type converter và operator overloader.

### 2.1. StandardEvaluationContext

StandardEvaluationContext cung cấp nhiều khả năng của SpEL và các chiến lược mặc định dựa trên reflection. Nó phù hợp khi expression cần truy cập property, gọi method, dùng bean reference, type reference hoặc các tính năng mở rộng khác.

Ví dụ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", minimumTotal);
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Nếu mỗi lần evaluate đều tạo context mới rồi đăng ký lại cùng một tập accessor, resolver hoặc function, ứng dụng sẽ lặp lại công việc cấu hình.

Khi cấu hình ổn định, hãy tách phần khởi tạo context thành một factory/helper để giảm code lặp và bảo đảm các context được tạo nhất quán. Việc có nên tái sử dụng cùng một instance context hay tạo context mới cho từng lần xử lý phụ thuộc vào dữ liệu mutable và phạm vi đồng thời của ứng dụng.

### 2.2. SimpleEvaluationContext

SimpleEvaluationContext chỉ cung cấp một tập con tính năng SpEL. Có thể chọn read-only data binding, read-write data binding hoặc cấu hình property accessor và instance method được phép.

Ví dụ:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Nếu expression chỉ cần đọc property, SimpleEvaluationContext có thể giúp giới hạn khả năng truy cập và giảm phần cấu hình không cần thiết. Tuy nhiên, không nên mặc định rằng nó luôn nhanh hơn trong mọi workload. Hãy chọn context theo tính năng cần dùng và đo hiệu năng với dữ liệu thực tế.

SimpleEvaluationContext không hỗ trợ bean reference, type reference và constructor invocation. Nếu expression cần những tính năng đó, phải chọn context phù hợp hơn.

### 2.3. Không đăng ký khả năng không sử dụng

Mỗi resolver hoặc accessor được cấu hình có thể ảnh hưởng đến quá trình phân giải. Chỉ đăng ký những gì expression cần:

- Không thêm BeanResolver nếu expression không tham chiếu bean.
- Không bật instance method invocation nếu expression chỉ đọc property.
- Không thêm custom PropertyAccessor nếu accessor mặc định đã đáp ứng.
- Không đăng ký converter hoặc function chỉ để phòng trường hợp chưa có nhu cầu.

Giới hạn cấu hình làm cho context dễ hiểu và giảm những đường xử lý không cần thiết.

## 3. Tái sử dụng Expression đã parse

Trong một luồng xử lý lặp lại, không nên parse cùng một chuỗi expression ở mỗi vòng lặp.

Ví dụ nên tránh:

~~~java
for (Order order : orders) {
    Expression expression =
            parser.parseExpression("total * #taxRate");

    BigDecimal total = expression.getValue(
            context,
            order,
            BigDecimal.class
    );
}
~~~

Có thể parse một lần rồi tái sử dụng:

~~~java
Expression expression =
        parser.parseExpression("total * #taxRate");

for (Order order : orders) {
    BigDecimal total = expression.getValue(
            context,
            order,
            BigDecimal.class
    );
}
~~~

Expression giữ cấu trúc đã parse. Mỗi lần getValue() vẫn đánh giá với context và root object được truyền vào, nhưng ứng dụng không phải lặp lại bước parse chuỗi.

Nếu expression được dùng ở nhiều nơi, có thể đặt việc parse vào một registry hoặc cache theo tên quy tắc.

### 3.1. Cache expression theo nội dung và cấu hình parse

Một cache expression nên tính đến các yếu tố ảnh hưởng đến kết quả parse:

- Nội dung expression.
- Parser hoặc parser configuration liên quan.
- ParserContext nếu expression là template hoặc dùng delimiter riêng.
- Những tùy chọn parse khác của ứng dụng.

Không nên dùng một cache không giới hạn cho chuỗi expression do người dùng gửi. Nếu đầu vào có thể tăng liên tục, cache cần giới hạn kích thước hoặc thời gian sống để tránh giữ quá nhiều Expression trong bộ nhớ.

Với expression từ nguồn không tin cậy, ngoài giới hạn cache còn cần giới hạn cú pháp và quyền của EvaluationContext. Cache không phải biện pháp bảo mật.

### 3.2. Không cache kết quả nếu dữ liệu đầu vào thay đổi

Tái sử dụng Expression khác với cache kết quả evaluate.

Ví dụ expression:

~~~text
#order.total * #taxRate
~~~

Kết quả phụ thuộc vào order và taxRate của lần đánh giá. Nếu cache kết quả mà key không bao gồm mọi dữ liệu ảnh hưởng, ứng dụng có thể trả về giá trị cũ.

Chỉ cache kết quả khi đã xác định rõ tính bất biến của dữ liệu, khóa cache bao phủ toàn bộ đầu vào liên quan và thời hạn hiệu lực phù hợp.

## 4. Tạo EvaluationContext mới hay tái sử dụng?

Có hai nhóm dữ liệu trong context:

- **Cấu hình tương đối ổn định:** property accessor, method resolver, bean resolver, type converter và function.
- **Dữ liệu theo lần xử lý:** root object, variables như currentUser, order hoặc request.

Có thể giảm công việc lặp lại bằng cách gom cấu hình vào một factory. Tuy nhiên, context thường có trạng thái mutable: root object và variables có thể được thay đổi bằng các setter.

### 4.1. Tạo context theo request hoặc đơn vị công việc

Một pattern dễ kiểm soát là parse Expression một lần, sau đó tạo EvaluationContext riêng cho mỗi request hoặc mỗi đơn vị công việc:

~~~java
Expression expression =
        parser.parseExpression("total >= #minimumTotal");

StandardEvaluationContext createContext(
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return context;
}
~~~

Cách này giữ dữ liệu của các lần xử lý tách biệt. Nó đặc biệt hữu ích khi nhiều request chạy đồng thời và mỗi request có root object hoặc variables khác nhau.

### 4.2. Khi nào có thể tái sử dụng context?

Có thể cân nhắc tái sử dụng một context khi:

- Các chiến lược truy cập không thay đổi.
- Dữ liệu trong context không bị chia sẻ giữa các lần xử lý độc lập.
- Root object và variables được cập nhật có kiểm soát.
- Không có hai luồng đồng thời ghi/đọc các giá trị mutable khác nhau trong cùng context.

Không nên dùng chung một StandardEvaluationContext mutable cho nhiều request đồng thời nếu mỗi request cần root object hoặc variables riêng. Một request có thể ghi đè variable trong lúc request khác đang evaluate và dẫn tới kết quả sai.

Nếu cần chia sẻ cấu hình, hãy tạo context riêng từ một factory cho từng đơn vị xử lý thay vì chia sẻ một instance đang thay đổi.

## 5. Chi phí truy cập property và method

Expression:

~~~text
#order.customer.address.city
~~~

có nhiều bước truy cập liên tiếp:

1. Đọc order.
2. Đọc customer.
3. Đọc address.
4. Đọc city.

Mỗi bước cần cơ chế property access phù hợp. Với StandardEvaluationContext, các accessor mặc định thường dùng reflection để truy cập property. Method invocation cũng cần resolver tìm method và xác định cách truyền đối số.

Một expression càng có nhiều bước truy cập hoặc lời gọi method thì càng có nhiều công việc cần thực hiện. Tuy nhiên, độ sâu không phải yếu tố duy nhất: getter có thể chứa logic tốn thời gian hơn nhiều so với việc resolve property.

### 5.1. Tránh getter thực hiện công việc nặng

Getter có thể truy vấn database, gọi API, tính toán lớn hoặc kích hoạt lazy loading. SpEL gọi getter như một phần của property access; nó không biết getter đó có chi phí cao.

Ví dụ:

~~~text
#order.customer.accountManager.department.name
~~~

Nếu một getter trong chuỗi kích hoạt truy vấn dữ liệu, một expression ngắn vẫn có thể gây ra nhiều I/O.

Hãy ưu tiên đưa vào context các DTO hoặc object đã được chuẩn bị sẵn với những giá trị expression cần dùng. Không nên đặt truy vấn database hoặc lời gọi mạng trong getter chỉ để expression có thể đọc property.

### 5.2. Tránh gọi lại cùng một phép tính đắt tiền

Nếu nhiều phần expression cùng gọi một method có chi phí cao, method đó có thể được thực hiện nhiều lần.

Ví dụ:

~~~text
#order.calculateShippingCost() + #order.calculateShippingCost()
~~~

Nếu method không có cache nội bộ, expression gọi nó hai lần. Có thể tính trước trong Java rồi đăng ký kết quả:

~~~java
context.setVariable(
        "shippingCost",
        order.calculateShippingCost()
);
~~~

Expression:

~~~text
#shippingCost * 2
~~~

Chỉ đưa kết quả đã tính trước vào context khi ngữ nghĩa cho phép dùng chung một giá trị trong lần xử lý đó.

## 6. Object graph lớn không đồng nghĩa SpEL tự duyệt toàn bộ graph

SpEL chỉ thực hiện những đường truy cập và thao tác được expression yêu cầu. Việc root object có hàng trăm property hoặc nhiều quan hệ không có nghĩa mỗi lần evaluate sẽ tự động đọc tất cả.

Ví dụ:

~~~text
#order.customer.name
~~~

chỉ yêu cầu đi theo đường customer rồi name. Các nhánh khác của object graph không được duyệt chỉ vì chúng tồn tại.

Chi phí tăng khi expression:

- Đi qua nhiều property lồng nhau.
- Truy cập các collection lớn.
- Gọi getter có side effect hoặc tải dữ liệu.
- Dùng nhiều selection/projection lồng nhau.
- Tạo nhiều collection hoặc object trung gian.

Vì vậy, hãy đánh giá graph theo đường truy cập thực tế, số phần tử được duyệt và hành vi của getter, thay vì chỉ nhìn vào tổng số property của root object.

## 7. Selection và projection trên collection

Selection và projection có thể hữu ích nhưng chi phí phụ thuộc số phần tử và độ phức tạp của expression áp dụng cho từng phần tử.

Ví dụ selection:

~~~text
#orders.?[total >= #minimumTotal]
~~~

SpEL phải kiểm tra điều kiện trên các phần tử của collection. Với N phần tử và điều kiện có chi phí gần như cố định, công việc tăng theo N.

Projection:

~~~text
#orders.![total * #taxRate]
~~~

thực hiện phép biến đổi cho từng phần tử và tạo kết quả collection.

### 7.1. Collection trung gian và nhiều lượt duyệt

Expression kết hợp selection và projection:

~~~text
#orders.?[total >= #minimumTotal].![total * #taxRate]
~~~

cần lọc các phần tử rồi tạo kết quả projection. Việc dùng nhiều operator collection có thể tạo collection trung gian và thêm chi phí cấp phát bộ nhớ.

Với collection lớn, hãy đo cả thời gian và lượng cấp phát. Nếu logic gồm nhiều bước, nhiều điều kiện hoặc cần tối ưu luồng dữ liệu, Java Stream hoặc vòng lặp Java có thể dễ kiểm soát hơn.

### 7.2. Tránh selection lồng nhau không cần thiết

Ví dụ một collection lồng trong mỗi phần tử khác:

~~~text
#departments.?[
    employees.?[active].size() > 0
]
~~~

Nếu có D phòng ban và mỗi phòng ban có trung bình E nhân viên, expression có thể phải kiểm tra một lượng phần tử tỷ lệ với D nhân E.

Khi dữ liệu lớn, hãy cân nhắc tính trước trạng thái cần kiểm tra trong Java hoặc tạo DTO chứa thông tin tổng hợp. Không nên dùng expression lồng nhau để thay thế một truy vấn hoặc phép tổng hợp dữ liệu có thể được thực hiện hiệu quả hơn ở tầng phù hợp.

## 8. Lazy loading và nguy cơ N+1 query

Trong ứng dụng dùng ORM, getter của một association có thể kích hoạt lazy loading. Một expression như:

~~~text
#orders.![customer.address.city]
~~~

có thể truy cập customer và address cho từng order. Nếu các association chưa được tải, mỗi lần truy cập có thể phát sinh truy vấn bổ sung.

Đây là nguy cơ N+1 query quen thuộc:

- Một truy vấn lấy danh sách order.
- Sau đó nhiều truy vấn phát sinh khi expression đọc association của từng order.

SpEL không tự gom các truy vấn đó. Nó chỉ gọi property accessor hoặc getter trên object được cung cấp.

Cách xử lý:

1. Tải trước dữ liệu cần dùng bằng fetch join, entity graph hoặc projection phù hợp với ORM đang sử dụng.
2. Chuyển dữ liệu cần hiển thị sang DTO trước khi evaluate.
3. Tránh gọi property association không cần thiết trong selection/projection.
4. Theo dõi số lượng SQL query trong integration test hoặc profiler.
5. Đưa phép tổng hợp lớn về database khi đó là nơi phù hợp để xử lý.

Không nên tối ưu riêng thời gian SpEL nếu chi phí chính đến từ database hoặc lazy loading.

## 9. Chọn root object và variables phù hợp

Root object và variables quyết định những gì expression có thể truy cập.

Một root object quá lớn hoặc chứa nhiều association có thể làm expression dễ vô tình truy cập vào các nhánh không cần thiết. Một DTO nhỏ có đúng các property cần dùng thường giúp expression dễ hiểu và dự đoán hơn.

Ví dụ thay vì đưa một entity graph phức tạp:

~~~java
context.setRootObject(orderEntity);
~~~

có thể tạo dữ liệu đầu vào chuyên biệt:

~~~java
context.setRootObject(new OrderSummary(
        order.getId(),
        order.getCustomer().getDisplayName(),
        order.getTotal()
));
~~~

Expression:

~~~text
id + ' - ' + customerName + ' - ' + total
~~~

DTO giúp giới hạn object graph mà expression nhìn thấy và tránh các getter không cần thiết. Chi phí tạo DTO cũng cần được tính trong benchmark, nhưng đổi lại luồng truy cập rõ ràng hơn.

Variables phù hợp để truyền những giá trị phụ thuộc lần xử lý như threshold, locale hoặc feature flag. Không nên đưa toàn bộ application context hoặc một service locator vào variable chỉ để expression có thể truy cập tùy ý.

## 10. Tối ưu bằng PropertyAccessor hoặc resolver tùy chỉnh

Nếu profiling cho thấy chi phí property access là điểm nghẽn, có thể xem xét PropertyAccessor chuyên biệt cho kiểu dữ liệu thường dùng.

Một accessor tùy chỉnh có thể cung cấp cách đọc property rõ ràng hơn cho một cấu trúc domain đặc biệt. Tuy nhiên, việc tự viết accessor cũng tạo thêm code cần bảo trì và có thể làm thay đổi ngữ nghĩa truy cập.

Chỉ nên tùy chỉnh khi:

- Profiling xác định property resolution là chi phí đáng kể.
- Cấu trúc dữ liệu có quy tắc truy cập ổn định.
- Accessor mặc định không phù hợp hoặc không đủ hiệu quả.
- Có test xác nhận đúng kiểu, null behavior và lỗi truy cập.

Tương tự, custom MethodResolver, BeanResolver hoặc TypeConverter có thể thêm bước xử lý. Không nên thêm resolver chỉ với hy vọng tăng tốc nếu chưa đo được lợi ích.

## 11. Compiled expression và chi phí context

SpEL compiler có thể cải thiện tốc độ thực thi của một số expression được đánh giá thường xuyên. Tuy nhiên, compiler không loại bỏ chi phí tạo EvaluationContext, chuẩn bị variables, gọi service hoặc tải dữ liệu từ object graph.

Một số dạng expression hiện không hỗ trợ compilation, chẳng hạn selection/projection, bean reference, assignment và một số trường hợp cần custom resolver hoặc ConversionService. Những expression này vẫn có thể chạy ở interpreted mode.

Nếu cân nhắc compiler:

- Xác nhận expression thuộc nhóm được hỗ trợ trong phiên bản Spring đang dùng.
- Kiểm tra kiểu root object và property có ổn định qua các lần evaluate.
- Đo cả thời gian parse, khởi tạo context và evaluate.
- Tránh side effect trong expression có thể được fallback/retry ở MIXED mode.
- Không bật compiler chỉ vì expression dài hoặc được đánh giá thường xuyên.

Compiled mode có thể giảm một phần chi phí interpreter, nhưng không sửa được một object graph có getter quá đắt hoặc một expression gây N+1 query.

## 12. Đo hiệu năng đúng cách

Không nên quyết định tối ưu chỉ từ cảm nhận hoặc một lần chạy đơn lẻ. Hãy đo các thành phần với workload gần môi trường thực tế.

Một benchmark có thể tách:

1. Thời gian parse expression.
2. Thời gian tạo và cấu hình EvaluationContext.
3. Thời gian evaluate với root object nhỏ.
4. Thời gian evaluate với object graph sâu.
5. Thời gian selection/projection trên collection có kích thước khác nhau.
6. Số lần gọi getter/method và số lượng truy vấn database nếu có ORM.
7. Lượng cấp phát collection hoặc object trung gian.

JMH phù hợp để benchmark Java ở mức microbenchmark. Với ứng dụng có database, proxy hoặc lazy loading, cần integration test và profiler để đo cả I/O cùng số lượng query.

Trong benchmark, hãy:

- Warm up JVM trước khi lấy số liệu.
- Dùng cùng dữ liệu đầu vào khi so sánh các cách viết.
- Đo nhiều lần và xem phân bố kết quả, không chỉ một giá trị.
- Tách chi phí parse khỏi evaluate nếu mục tiêu là đo vòng lặp nóng.
- So sánh interpreted và compiled chỉ với expression compiler hỗ trợ.
- Giữ cấu hình context tương đương giữa các phương án.
- Kiểm tra kết quả trả về để tránh benchmark một phép tính không có ý nghĩa.

## 13. Checklist tối ưu thực tế

Khi một expression chạy chậm, có thể xem xét theo thứ tự:

1. Parse expression một lần và tái sử dụng Expression.
2. Không tạo context mới bên trong vòng lặp nếu có thể chuẩn bị một lần cho đơn vị xử lý.
3. Tạo context riêng cho mỗi request hoặc công việc khi variables/root object khác nhau.
4. Chỉ đăng ký resolver, accessor và function cần thiết.
5. Giảm số bước property access lặp lại.
6. Tính trước method/getter đắt tiền và đưa kết quả vào variable khi phù hợp.
7. Dùng DTO hoặc projection nhỏ thay vì truyền entity graph quá rộng.
8. Giảm selection/projection lồng nhau trên collection lớn.
9. Kiểm tra lazy loading và N+1 query.
10. Chỉ viết custom accessor hoặc resolver sau khi profiling xác định điểm nghẽn.
11. Cân nhắc compiled mode khi expression được hỗ trợ và kiểu dữ liệu ổn định.
12. Đo lại sau mỗi thay đổi để xác nhận lợi ích và phát hiện chi phí chuyển sang nơi khác.

## 14. Ví dụ: parse một lần, context theo lần xử lý

Ví dụ sau tách expression đã parse khỏi dữ liệu của từng order:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("total >= #minimumTotal");

boolean isEligible(
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class)
    );
}
~~~

Trong ví dụ, Expression được parse một lần và có thể dùng lại. Mỗi lần gọi isEligible() tạo context với root object và threshold tương ứng.

Nếu profiling cho thấy việc tạo context là chi phí đáng kể, hãy benchmark một phương án khác có cấu hình ổn định và trạng thái mutable được kiểm soát. Đừng chuyển sang chia sẻ context toàn cục nếu điều đó khiến các request ghi đè root object hoặc variables của nhau.

## 15. Ghi nhớ nhanh

- Chi phí SpEL gồm parse, tạo EvaluationContext, resolve property/method, duyệt object graph và tạo kết quả.
- Parse Expression một lần rồi tái sử dụng trong hot path.
- Tạo context theo request hoặc đơn vị công việc khi root object và variables khác nhau.
- Không chia sẻ một EvaluationContext mutable giữa các request đồng thời có dữ liệu riêng.
- Chỉ đăng ký resolver, accessor, function và converter mà expression cần.
- SimpleEvaluationContext có tập tính năng nhỏ hơn; chọn theo yêu cầu truy cập và đo thực tế.
- SpEL chỉ duyệt các đường truy cập expression yêu cầu, không tự động quét toàn bộ object graph.
- Property chain sâu, getter đắt tiền và method có side effect có thể làm evaluation chậm.
- Selection/projection duyệt collection và có thể tạo collection trung gian; chi phí tăng theo dữ liệu được xử lý.
- Getter truy cập ORM association có thể kích hoạt lazy loading và N+1 query.
- DTO hoặc projection nhỏ giúp giới hạn object graph và làm dữ liệu đầu vào dễ dự đoán.
- Compiler không loại bỏ chi phí context, getter, service hoặc database.
- Dùng profiler/JMH và integration test để xác định đúng điểm nghẽn trước khi tối ưu.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework — EvaluationContext and Expression Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
