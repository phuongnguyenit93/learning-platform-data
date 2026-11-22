# EvaluationContext và dữ liệu mà biểu thức được phép nhìn thấy

Trong Spring Expression Language (SpEL), một biểu thức không tự quyết định được nó có thể đọc dữ liệu nào hoặc gọi được hành động nào. Bộ phân tích cú pháp chỉ chuyển chuỗi biểu thức thành đối tượng Expression; khi chạy, EvaluationContext cung cấp đối tượng gốc, biến, hàm và các cơ chế truy cập thuộc tính, phương thức, kiểu dữ liệu. Vì vậy, hiểu EvaluationContext là hiểu ranh giới dữ liệu mà một biểu thức có thể nhìn thấy.

## 1. Vị trí của EvaluationContext trong quá trình đánh giá

Một lượt đánh giá SpEL thường có ba thành phần:

1. ExpressionParser phân tích chuỗi, ví dụ total > 100.
2. Expression giữ cây biểu thức đã phân tích và cung cấp các phương thức getValue(...) hoặc setValue(...).
3. EvaluationContext cung cấp môi trường chạy để Expression tra cứu dữ liệu và thực hiện các phép truy cập được cho phép.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.name");

EvaluationContext context =
        new StandardEvaluationContext(order);

String customerName = expression.getValue(context, String.class);
~~~

Ở đây order là đối tượng gốc. Khi biểu thức đọc customer.name, SpEL tìm thuộc tính customer trên đối tượng gốc, sau đó đọc name trên đối tượng khách hàng. Khả năng đọc hai thuộc tính này phụ thuộc vào các PropertyAccessor trong context và cấu trúc đối tượng được đưa vào.

Có thể truyền đối tượng gốc ngay trong lúc đánh giá thay vì đặt nó trước trong context:

~~~java
String customerName =
        expression.getValue(context, order, String.class);
~~~

Cách này hữu ích khi muốn tái sử dụng một context đã cấu hình nhưng đánh giá biểu thức trên các đối tượng gốc khác nhau. Hãy chú ý context vẫn có thể chứa biến, resolver và các cấu hình dùng chung giữa những lần đánh giá.

## 2. Đối tượng gốc: root object, #root và #this

Đối tượng gốc là điểm bắt đầu để biểu thức truy cập dữ liệu. Với StandardEvaluationContext, có thể đặt nó bằng constructor hoặc setRootObject(...). Nếu dùng overload getValue(context, rootObject, ...), đối tượng truyền vào sẽ làm root object cho lần đánh giá đó.

SpEL cung cấp hai tham chiếu có ý nghĩa khác nhau:

- #root luôn trỏ đến đối tượng gốc của lượt đánh giá.
- #this trỏ đến đối tượng hiện tại mà biểu thức đang xử lý. Trong các thao tác trên collection như selection (.?[...]) và projection (.![...]), #this thay đổi theo từng phần tử đang được xét, còn #root vẫn giữ nguyên đối tượng gốc.

Ví dụ, giả sử order có thuộc tính lines là danh sách các dòng đơn hàng, mỗi dòng có quantity:

~~~text
#root.lines.?[#this.quantity > 1]
~~~

Biểu thức trên lọc các dòng có số lượng lớn hơn một. Trong điều kiện lọc, #this là từng dòng đơn hàng. Nếu cần đọc dữ liệu từ đối tượng gốc trong cùng biểu thức, có thể dùng #root.

Đối tượng gốc không nhất thiết phải là một entity lớn. Một DTO nhỏ chỉ chứa các trường cần thiết thường là lựa chọn tốt hơn: nó làm rõ dữ liệu được công khai cho biểu thức và giảm khả năng biểu thức đi tới các thành phần nội bộ của ứng dụng.

## 3. Những nguồn dữ liệu và khả năng mà context có thể cung cấp

EvaluationContext không chỉ chứa root object. Tùy implementation và cấu hình, biểu thức có thể tiếp cận các nguồn sau.

### 3.1. Thuộc tính và phần tử của object

PropertyAccessor quyết định cách SpEL đọc hoặc ghi một thuộc tính. Các accessor mặc định của StandardEvaluationContext dùng cơ chế phản chiếu để làm việc với thuộc tính Java thông thường, chẳng hạn getter hoặc field phù hợp.

Ví dụ:

~~~text
customer.name
customer.address.city
order.lines[0].sku
settings['region']
~~~

Các biểu thức trên có thể đọc thuộc tính lồng nhau, phần tử collection, mảng hoặc giá trị trong map khi accessor và kiểu dữ liệu hỗ trợ cách truy cập đó. Với biểu thức có phép gán, việc ghi còn phụ thuộc accessor có hỗ trợ ghi hay không và context có cho phép thao tác đó hay không.

Không nên nhầm tên thuộc tính trong biểu thức với tên cột cơ sở dữ liệu. SpEL đang truy cập object model tại thời điểm chạy; nó không tự truy vấn database hay tự tải quan hệ lazy. Nếu getter của object kích hoạt truy vấn hoặc có tác dụng phụ, biểu thức gọi getter đó có thể gián tiếp gây ra những hành vi tương ứng.

### 3.2. Phương thức

MethodResolver quyết định phương thức nào có thể được gọi trên object. StandardEvaluationContext mặc định sử dụng cơ chế phân giải phương thức dựa trên reflection, nên biểu thức có thể gọi các phương thức phù hợp mà đối tượng và resolver cho phép.

Ví dụ:

~~~text
customer.isActive()
order.calculateTotal()
~~~

Hãy chỉ đưa vào root object những phương thức có ý nghĩa và an toàn khi được gọi trong ngữ cảnh biểu thức. Một getter tưởng như chỉ đọc cũng có thể chứa logic phức tạp; một phương thức nghiệp vụ có thể thay đổi trạng thái, ghi dữ liệu hoặc gọi dịch vụ bên ngoài.

### 3.3. Biến và hàm

Biến được tham chiếu bằng tiền tố #. Có thể đặt biến trên context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "total >= #minimumTotal"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Biến hữu ích khi một giá trị cần tham gia biểu thức nhưng không nên được gắn vào object nghiệp vụ. Nó cũng giúp tách dữ liệu đầu vào khỏi cấu trúc domain object.

Có thể đăng ký hàm để gọi một phương thức static đã chọn:

~~~java
Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);

context.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression(
        "#normalize(customer.name)"
);
String normalizedName = expression.getValue(context, String.class);
~~~

Hàm được đăng ký trở thành một khả năng mà biểu thức có thể gọi. Chỉ đăng ký các hàm có đầu vào, đầu ra và tác dụng phụ đã được kiểm soát. Không đăng ký một lớp tiện ích tổng quát nếu lớp đó mở ra nhiều thao tác không cần thiết.

### 3.4. Bean trong Spring container

Biểu thức có thể tham chiếu bean bằng cú pháp @beanName, nhưng khả năng này cần một BeanResolver phù hợp được cấu hình trong context. Ví dụ, khi context được nối với Spring BeanFactory, có thể dùng BeanFactoryResolver:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Sau khi được cấu hình, biểu thức có thể tham chiếu bean đã phân giải, ví dụ @pricingService. Việc một bean tồn tại trong application context không có nghĩa mọi SpEL context đều tự động nhìn thấy bean đó. Bean reference chỉ hoạt động khi context của lượt đánh giá có resolver tương ứng.

Đưa bean dịch vụ vào phạm vi biểu thức làm tăng đáng kể quyền của biểu thức: nó có thể gọi các phương thức mà bean công khai. Chỉ bật khả năng này khi use case thực sự cần và chỉ cho phép các bean được chọn.

### 3.5. Kiểu Java và khởi tạo đối tượng

Với context đầy đủ như StandardEvaluationContext, SpEL có thể hỗ trợ tham chiếu kiểu bằng T(...) và tạo đối tượng bằng new ...:

~~~text
T(java.lang.Math).max(10, 20)
new java.util.Date()
~~~

Việc phân giải kiểu phụ thuộc TypeLocator; việc tạo đối tượng phụ thuộc ConstructorResolver. Các khả năng này hữu ích trong biểu thức nội bộ được kiểm soát, nhưng thường không cần thiết đối với biểu thức chỉ lọc hoặc hiển thị dữ liệu. Nếu đầu vào biểu thức đến từ người dùng, cho phép truy cập kiểu và constructor có thể mở rộng phạm vi hành động ngoài dự kiến.

### 3.6. Chuyển đổi, so sánh và toán tử

Context còn cung cấp TypeConverter, TypeComparator và OperatorOverloader. Chúng ảnh hưởng đến cách SpEL chuyển kiểu giá trị, so sánh hai đối tượng và xử lý toán tử.

Ví dụ, phép so sánh số hoặc việc gán giá trị từ chuỗi sang thuộc tính có kiểu cụ thể có thể cần chuyển đổi kiểu. Khi ứng dụng dùng ConversionService riêng hoặc kiểu dữ liệu đặc thù, cấu hình converter phù hợp giúp biểu thức có hành vi nhất quán với mô hình dữ liệu của ứng dụng.

Các thành phần này không phải nguồn dữ liệu độc lập như root object hoặc biến; chúng là những quy tắc quyết định cách biểu thức thao tác với dữ liệu đã truy cập được.

## 4. StandardEvaluationContext và SimpleEvaluationContext

Hai implementation thường gặp phục vụ các mức khả năng khác nhau.

### 4.1. StandardEvaluationContext

StandardEvaluationContext cung cấp bộ khả năng SpEL đầy đủ hơn. Nó hỗ trợ cấu hình root object, biến, hàm, property accessor, method resolver, constructor resolver, type locator, type converter, type comparator, operator overloader và bean resolver.

Các accessor và resolver mặc định cho phép truy cập Java theo cơ chế reflection. Đây là lựa chọn phù hợp khi ứng dụng kiểm soát biểu thức và cần các tính năng SpEL nâng cao. Tuy nhiên, không nên xem nó là sandbox cho biểu thức không đáng tin cậy. Root object, biến, hàm và bean resolver có thể làm lộ nhiều dữ liệu hoặc hành động hơn dự định.

### 4.2. SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho tình huống cần một tập con hạn chế của SpEL, đặc biệt là data binding. Builder yêu cầu chọn rõ cách truy cập thuộc tính, ví dụ:

~~~java
EvaluationContext readOnlyContext =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Boolean active = parser.parseExpression("customer.active")
        .getValue(readOnlyContext, order, Boolean.class);
~~~

forReadOnlyDataBinding() phù hợp khi biểu thức chỉ cần đọc dữ liệu. Nếu use case cần ghi thuộc tính, có thể cân nhắc forReadWriteDataBinding(), nhưng chỉ nên bật quyền ghi khi có yêu cầu cụ thể và dữ liệu đầu vào đã được kiểm soát.

SimpleEvaluationContext không hỗ trợ các tính năng như tham chiếu kiểu Java, tạo constructor và bean reference. Việc gọi instance method cũng không được bật mặc định; builder có thể bật rõ ràng bằng withInstanceMethods() khi cần. Việc giới hạn tính năng giúp thu hẹp bề mặt truy cập, nhưng vẫn cần kiểm soát object gốc và accessor được cung cấp.

### 4.3. Chọn implementation theo yêu cầu

| Nhu cầu | Hướng cấu hình |
|---|---|
| Đọc thuộc tính DTO để lọc hoặc hiển thị | SimpleEvaluationContext.forReadOnlyDataBinding() |
| Cần cập nhật thuộc tính qua biểu thức | Chỉ cân nhắc read-write khi có kiểm soát đầu vào |
| Cần gọi instance method được chọn | Chỉ bật method invocation khi thật sự cần; giới hạn object và method |
| Cần biến, hàm, bean hoặc truy cập kiểu/constructor | Dùng context hỗ trợ tính năng tương ứng và cấu hình từng khả năng có chủ đích |
| Đánh giá biểu thức do người dùng cung cấp | Dùng context hạn chế, DTO hẹp và allowlist; tránh cấp quyền tổng quát |

Không có implementation nào tự động biến biểu thức thành an toàn trong mọi trường hợp. Mức an toàn còn phụ thuộc dữ liệu được đưa vào, accessor/resolver được cài đặt và nguồn gốc biểu thức.

## 5. Giới hạn dữ liệu là giới hạn của object graph và resolver

Một biểu thức chỉ có thể đi tới dữ liệu mà context và các đối tượng được cấp cho nó cho phép truy cập. Hãy hình dung đường truy cập bắt đầu từ root object, đi qua property accessor, rồi có thể tiếp tục tới object con, collection, map hoặc phương thức được resolver chấp nhận.

Ví dụ, nếu root object là một DTO chỉ có displayName và status, biểu thức không thể tự nhiên đọc passwordHash từ một entity khác mà DTO không tham chiếu tới. Ngược lại, nếu root object là một service có tham chiếu tới repository, application context và nhiều entity, việc cho biểu thức gọi phương thức trên service có thể mở đường tới một phạm vi dữ liệu rất rộng.

Do đó, câu hỏi quan trọng khi thiết kế context không chỉ là “biểu thức cần đọc trường nào?” mà còn là:

- Root object tham chiếu tới những object nào?
- Những thuộc tính nào có thể đọc hoặc ghi?
- Những phương thức nào có thể được gọi và có tác dụng phụ gì?
- Có biến, hàm hoặc bean nào được đăng ký?
- Có cho phép truy cập kiểu Java hoặc tạo object không?
- Có cần chuyển đổi kiểu hoặc toán tử tùy chỉnh không?

Một context được thiết kế tốt chỉ cung cấp đúng các khả năng mà use case cần.

## 6. Ví dụ cấu hình theo nguyên tắc cấp quyền tối thiểu

Giả sử một màn hình cần lọc đơn hàng theo tổng tiền tối thiểu và trạng thái khách hàng. Mục tiêu là chỉ đọc dữ liệu để hiển thị kết quả.

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression filter = parser.parseExpression(
        "total >= 100 and customer.active"
);

Boolean matches = filter.getValue(
        context,
        order,
        Boolean.class
);
~~~

Ví dụ này minh họa ý tưởng dùng context chỉ đọc và truyền root object riêng cho lần đánh giá. Nếu biểu thức cần biến #minimumTotal, hãy xác nhận implementation/builder đang dùng hỗ trợ biến theo phiên bản Spring của ứng dụng; nếu cần các khả năng của StandardEvaluationContext, hãy cấu hình riêng và giới hạn dữ liệu đưa vào. Không nên chuyển sang context đầy đủ chỉ để tiện truy cập một object lớn.

Khi cần custom property access, có thể cung cấp PropertyAccessor chỉ đọc các thuộc tính được allowlist. Khi cần method call, có thể dùng resolver giới hạn method hoặc chỉ cung cấp DTO có các phương thức thuần, không có side effect. Khi cần bean reference, hãy cấu hình resolver và chỉ công khai các bean được chọn.

## 7. Rủi ro khi đánh giá biểu thức không đáng tin cậy

Biểu thức SpEL có thể làm nhiều hơn đọc một giá trị. Với context rộng, biểu thức có thể gọi method, đọc object lồng nhau, tham chiếu bean, truy cập kiểu hoặc tạo object. Vì vậy, không nên lấy chuỗi biểu thức do người dùng gửi rồi đánh giá trực tiếp bằng StandardEvaluationContext được cấp toàn bộ application context.

Các nguyên tắc thực tế:

1. Ưu tiên SimpleEvaluationContext cho data binding hoặc biểu thức lọc chỉ đọc.
2. Đưa vào root object là DTO tối thiểu, không phải service, repository hoặc application context.
3. Chỉ đăng ký biến và hàm cần thiết; tránh hàm tổng quát có thể thực hiện I/O hoặc thay đổi trạng thái.
4. Chỉ cấu hình BeanResolver, TypeLocator, ConstructorResolver hoặc method invocation khi use case yêu cầu.
5. Giới hạn thuộc tính và phương thức qua accessor/resolver tùy chỉnh nếu dữ liệu đầu vào không đáng tin cậy.
6. Tách biểu thức theo người dùng hoặc request; không để biến và root object của một lượt đánh giá rò sang lượt khác.
7. Kiểm soát thời gian và tần suất đánh giá nếu biểu thức có thể phức tạp hoặc chạy trên dữ liệu lớn.

Không dùng việc parse thành công làm bằng chứng rằng biểu thức an toàn. Parser xác nhận cú pháp có thể phân tích; quyền truy cập và hành vi chỉ xuất hiện khi biểu thức được đánh giá trong một context cụ thể.

## 8. EvaluationContext trong các tích hợp Spring

Khi dùng SpEL trực tiếp, ứng dụng thường tự tạo parser và context. Khi dùng SpEL thông qua các tính năng Spring như @Value, cache, method security hoặc cấu hình khác, framework tích hợp sẽ tạo context theo hợp đồng riêng của tính năng đó.

Vì vậy, các biến có sẵn, root object, bean reference và cú pháp được hỗ trợ có thể khác nhau giữa các tích hợp. Ví dụ, một biểu thức trong method security có thể cung cấp thông tin về method invocation, tham số và authentication; một biểu thức trong cấu hình giá trị có thể có root object và bean resolver khác. Không nên lấy danh sách biến của một tích hợp rồi giả định mọi nơi đều có cùng danh sách.

Khi cần biết biểu thức ở một điểm tích hợp cụ thể nhìn thấy dữ liệu nào, hãy tra tài liệu của chính tính năng đó và kiểm tra implementation/context được sử dụng tại điểm đánh giá. Nếu ứng dụng có customizer hoặc expression handler, hãy xem cấu hình đó vì nó có thể bổ sung hoặc giới hạn các resolver.

## 9. Cách chẩn đoán khi biểu thức không nhìn thấy dữ liệu

Khi biểu thức báo không tìm thấy thuộc tính, biến, bean hoặc method, hãy kiểm tra theo thứ tự:

1. Root object thực tế của lượt đánh giá là gì? Có đang truyền nhầm object hoặc null không?
2. Tên thuộc tính có khớp với getter/field mà accessor hỗ trợ không?
3. Biểu thức có đang ở trong selection/projection khiến #this trỏ tới phần tử hiện tại không?
4. Biến đã được đặt đúng tên chưa? Trong biểu thức phải dùng #tenBien.
5. Hàm đã đăng ký đúng tên và đúng method signature chưa?
6. Bean reference có BeanResolver tương ứng không?
7. SimpleEvaluationContext có đang giới hạn tính năng mà biểu thức cần dùng không?
8. Property accessor, method resolver hoặc type locator tùy chỉnh có loại bỏ khả năng truy cập đó không?
9. Kiểu kết quả yêu cầu trong getValue(..., ResultType.class) có tương thích với giá trị thực tế không?

Phân biệt lỗi cú pháp, lỗi phân giải thuộc tính/phương thức và lỗi chuyển đổi kiểu sẽ giúp xác định đúng lớp cấu hình cần sửa.

## 10. Ghi nhớ

EvaluationContext là hợp đồng giữa biểu thức SpEL và dữ liệu tại thời điểm chạy. Root object xác định điểm bắt đầu; biến và hàm cung cấp đầu vào bổ sung; property accessor và method resolver quyết định cách truy cập object; bean resolver, type locator và constructor resolver mở rộng các khả năng khi được cấu hình; converter, comparator và operator overloader định nghĩa cách thao tác với giá trị.

Khi thiết kế, hãy bắt đầu từ dữ liệu và hành động biểu thức thực sự cần. Cấp một root object hẹp, ưu tiên context chỉ đọc, và bật từng resolver theo nhu cầu cụ thể. Cách tổ chức đó giúp biểu thức dễ hiểu, dễ kiểm soát và tránh vô tình biến một quy tắc dữ liệu đơn giản thành đường truy cập sâu vào ứng dụng.