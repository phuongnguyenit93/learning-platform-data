# Thu nhỏ context để phát hiện quyền truy cập dư thừa

## Mục tiêu

Sau bài này, bạn có thể kiểm tra một SpEL EvaluationContext đang cung cấp những khả năng nào; thu hẹp root object, property accessor, method resolver, bean resolver, function và cơ chế tạo kiểu; và dùng các phép thử được phép/bị từ chối để phát hiện quyền truy cập dư thừa. Bạn cũng sẽ biết khi nào nên chọn SimpleEvaluationContext, khi nào cần một context tùy chỉnh, cách giữ các biểu thức hiện có hoạt động sau khi thu hẹp quyền và cách điều tra lỗi mà không mở rộng context chỉ để làm test chạy qua.

## 1. Vì sao cần thu nhỏ EvaluationContext?

EvaluationContext quyết định dữ liệu và các cơ chế mà SpEL có thể sử dụng khi đánh giá expression. Tùy cách cấu hình, expression có thể đọc property, gọi method, tham chiếu bean, dùng function, chuyển đổi kiểu hoặc tạo object.

Một context có quá nhiều khả năng làm tăng phạm vi tác động của expression. Ví dụ, một quy tắc chỉ cần đọc `order.total` nhưng lại được đánh giá với toàn bộ domain entity, service có quyền ghi dữ liệu, BeanResolver truy cập toàn container và method resolver mặc định. Nếu expression hoặc template bị sửa ngoài dự kiến, những khả năng dư thừa đó có thể trở thành đường dẫn tới dữ liệu hoặc hành động không cần thiết.

Thu nhỏ context giúp trả lời các câu hỏi:

- Expression thực sự cần đọc object và property nào?
- Có cần gọi method hay chỉ cần đọc dữ liệu đã chuẩn bị?
- Có cần bean reference hay ứng dụng có thể truyền kết quả qua variable?
- Có cần function nào, và function đó có quyền gì?
- Có cần type reference hoặc constructor invocation không?
- Những thao tác nào phải luôn bị từ chối?
- Khi model hoặc expression thay đổi, test nào sẽ phát hiện quyền mới bị mở rộng?

Nguyên tắc là chỉ cấp các khả năng cần thiết cho nhiệm vụ của expression. Quyền không cần thiết nên bị loại bỏ ngay trong context thay vì dựa vào quy ước người viết expression.

## 2. Kiểm kê quyền trước khi thay đổi context

Trước tiên, lập danh sách các thao tác mà expression hiện tại thực hiện:

| Khả năng | Dấu hiệu trong expression hoặc context |
|---|---|
| Đọc root property | `name`, `order.total`, `#root.id` |
| Đọc variable | `#minimum`, `#customer` |
| Đọc property của variable | `#customer.profile.name` |
| Gọi instance method | `#order.calculateTotal()` |
| Gọi function đã đăng ký | `#normalize(#code)` |
| Tham chiếu bean | `@pricingService.calculate(...)` |
| Tham chiếu kiểu | `T(java.time.LocalDate)` |
| Gọi constructor | `new java.math.BigDecimal(...)` |
| Gán property | `status = 'READY'` |
| Selection/projection | `#orders.?[...]`, `#orders.![...]` |

Đọc expression source và xác định root object, variable, resolver được ứng dụng cung cấp. Ghi rõ khả năng nào là yêu cầu nghiệp vụ, khả năng nào chỉ tồn tại do context dùng cấu hình mặc định.

Không nên thu hẹp context bằng cách xóa ngẫu nhiên một resolver rồi chờ production phát sinh lỗi. Hãy xác định trước expression cần gì, viết test cho hành vi hợp lệ và hành vi cần bị từ chối, sau đó áp dụng cấu hình tối thiểu.

## 3. Thu hẹp root object trước tiên

Root object là điểm bắt đầu để truy cập property không có tiền tố #. Nếu truyền một entity lớn hoặc object có nhiều quan hệ, expression có thể nhìn thấy nhiều dữ liệu hơn mức cần thiết.

Ví dụ, thay vì đưa toàn bộ User entity vào context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(userEntity);
~~~

hãy tạo một object đọc chuyên biệt chỉ chứa dữ liệu cần cho expression:

~~~java
public record UserView(
        String displayName,
        String locale,
        boolean active) {
}
~~~

Sau đó:

~~~java
UserView view = new UserView(
    user.getDisplayName(),
    user.getLocale(),
    user.isActive()
);

EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Object result = expression.getValue(context, view);
~~~

Expression chỉ nhận được những property được công bố trên UserView. Các quan hệ, setter và phương thức quản trị trên entity thật không xuất hiện trong object này.

Đây là một ranh giới dữ liệu hữu ích: nếu expression chỉ cần tên và locale, không có lý do phải truyền password hash, role, token, collection nội bộ hoặc repository vào root object.

## 4. Truyền dữ liệu qua variable thay vì truyền object quá rộng

Không phải mọi dữ liệu cần dùng đều phải nằm trong root object. Có thể truyền các giá trị cụ thể qua variable:

~~~java
context.setVariable("minimumTotal", minimumTotal);
context.setVariable("featureEnabled", featureEnabled);
~~~

Expression:

~~~text
total >= #minimumTotal and #featureEnabled
~~~

Cách này làm rõ các đầu vào mà quy tắc cần. Nếu chỉ cần một con số hoặc boolean, truyền đúng giá trị đó thay vì truyền một service hoặc một cấu hình lớn để expression tự truy cập.

Khi truyền object qua variable, áp dụng cùng nguyên tắc như root object: ưu tiên DTO hoặc view chỉ chứa property cần thiết. Variable không tự giới hạn quyền; nếu giá trị là một service hoặc object có method nhạy cảm, expression vẫn có thể sử dụng những khả năng mà context cho phép.

Hãy đặt tên variable theo vai trò và kiểm tra kiểu của nó trước khi đánh giá. Không nối dữ liệu người dùng trực tiếp vào expression source.

## 5. SimpleEvaluationContext cho biểu thức đọc dữ liệu

SimpleEvaluationContext được thiết kế cho các trường hợp cần một tập tính năng SpEL giới hạn. Ví dụ, khi expression chỉ cần đọc property theo data binding:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Có thể đánh giá expression trên root object:

~~~java
Expression expression =
    new SpelExpressionParser().parseExpression(
        "active and locale != null"
    );

Boolean active =
    expression.getValue(context, userView, Boolean.class);
~~~

SimpleEvaluationContext không cung cấp toàn bộ tính năng của StandardEvaluationContext. Nó không bật type reference, constructor invocation hoặc bean reference như một context đầy đủ. Method invocation cũng không được bật mặc định; builder có thể cấu hình instance method access khi ứng dụng thực sự cần.

Với biểu thức chỉ đọc property, đây thường là điểm khởi đầu phù hợp. Nếu cần một tính năng bổ sung, hãy bật đúng khả năng đó và kiểm thử lại ranh giới quyền sau khi cấu hình.

## 6. Chọn read-only thay vì read-write khi có thể

Nếu expression chỉ phục vụ tính toán, điều kiện hoặc hiển thị, không nên cấp quyền ghi property:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Chế độ read-only cho phép đọc property theo accessor tương ứng nhưng không cho expression thay đổi property thông qua data binding.

Nếu ứng dụng cần cập nhật một số trường, hãy xem xét một command hoặc DTO chuyên biệt, validation và service Java có authorization rõ ràng. Khi vẫn cần assignment trong SpEL, hãy dùng context read-write với PropertyAccessor allowlist chỉ cho phép đúng các property cần ghi.

Không dùng read-write chỉ vì một expression hiện tại có toán tử gán. Trước hết hãy xác định vì sao việc cập nhật cần nằm trong expression và liệu service chuyên biệt có diễn đạt quy tắc rõ ràng hơn hay không.

## 7. Giới hạn PropertyAccessor theo kiểu và property

PropertyAccessor quyết định expression có thể đọc hoặc ghi property trên target object hay không. Với accessor tùy chỉnh, có thể kiểm soát theo cả kiểu target lẫn tên property.

Một allowlist nên xác định riêng:

- Những target type được hỗ trợ.
- Những property được đọc.
- Những property được ghi, nếu có.
- Cách xử lý property không tồn tại hoặc không được phép.
- Kiểu dữ liệu mà accessor chấp nhận.

Ví dụ chính sách cho một view:

| Target type | Property | Đọc | Ghi |
|---|---|---|---|
| UserView | displayName | Cho phép | Không |
| UserView | locale | Cho phép | Không |
| UserView | active | Cho phép | Không |
| UserEntity | passwordHash | Không | Không |
| UserEntity | role | Không hoặc hạn chế | Không |

Không dùng denylist ngắn làm chính sách mặc định cho object lớn. Khi model thêm property mới, denylist có thể vô tình để lộ property mới; allowlist giữ mặc định là từ chối.

Nếu cần đọc một tập property nhỏ, SimpleEvaluationContext với DataBindingPropertyAccessor chỉ đọc có thể đủ. Nếu cần quy tắc chi tiết hơn, dùng PropertyAccessor tùy chỉnh và test từng property được cho phép hoặc từ chối.

## 8. Kiểm soát method invocation

Method invocation có thể biến một expression đọc dữ liệu thành một hành động. Một method như getDisplayName() có thể chỉ trả về giá trị, nhưng method như changeRole(), deleteAccount() hoặc sendPayment() có thể thay đổi trạng thái hoặc tương tác với hệ thống bên ngoài.

SimpleEvaluationContext không bật instance method invocation mặc định. Chỉ gọi builder withInstanceMethods() nếu expression thực sự cần gọi method trên object được cung cấp.

Nếu bật method invocation, hãy thu hẹp object được truyền vào để chỉ có các method an toàn và cần thiết. Một DTO chỉ có getter thường dễ kiểm soát hơn entity hoặc service đầy đủ.

Với StandardEvaluationContext, cần chú ý MethodResolver mặc định có thể cho phép gọi method công khai trên các object truy cập được. Nếu dùng context này cho expression không đáng tin cậy, hãy cấu hình resolver rõ ràng theo allowlist hoặc chọn context giới hạn phù hợp.

Không coi việc property accessor chỉ đọc là đủ để bảo đảm expression không thể thay đổi trạng thái. Method invocation là một con đường riêng cần được kiểm soát.

## 9. Hạn chế BeanResolver và bean reference

Cú pháp `@beanName` yêu cầu BeanResolver. Nếu expression chỉ cần một vài giá trị đã tính, hãy truyền các giá trị đó qua variable thay vì cung cấp cả Spring container.

Ví dụ, thay vì:

~~~text
@pricingService.calculate(#order)
~~~

ứng dụng có thể gọi service ở Java trước, sau đó truyền kết quả đã được xác định:

~~~java
context.setVariable(
    "calculatedTotal",
    pricingService.calculate(order)
);
~~~

Expression chỉ cần:

~~~text
#calculatedTotal >= #minimumTotal
~~~

Cách này giữ service và các dependency của nó bên ngoài phạm vi expression.

Nếu bean reference là yêu cầu thực sự, dùng BeanResolver giới hạn chỉ phân giải các bean đã duyệt. Tránh cung cấp BeanFactory hoặc ApplicationContext rộng cho template do người dùng chỉnh sửa. Chỉ cho phép các bean có method cần thiết, có hợp đồng rõ ràng và không mở quyền vượt quá mục đích.

Không đăng ký bean vào context chỉ để tránh truyền một biến đơn giản. Mỗi bean được phơi bày có thể mở rộng khả năng mà expression có thể gọi.

## 10. Chỉ đăng ký function cần thiết

Function được đăng ký trong EvaluationContext có thể gọi mã Java qua cú pháp `#functionName(...)`.

Nếu expression chỉ cần chuẩn hóa mã, hãy đăng ký đúng function đó:

~~~java
context.registerFunction(
    "normalizeCode",
    TextFunctions.class.getMethod("normalizeCode", String.class)
);
~~~

Không đăng ký cả một bộ function tiện ích lớn nếu expression chỉ cần một hàm. Không đăng ký function có thể thực thi lệnh, đọc bí mật, ghi file, gọi mạng hoặc thay đổi dữ liệu khi mục đích của expression chỉ là tính toán.

Function và variable dùng chung namespace, vì vậy tránh đặt trùng tên. Với context không đáng tin cậy, tạo một danh sách function allowlist nhỏ và test rằng tên ngoài danh sách không thể gọi.

Nếu logic cần dependency hoặc transaction, hãy giữ nó trong service Java. Function thường phù hợp với phép biến đổi nhỏ, xác định và có đầu vào/đầu ra rõ ràng.

## 11. Hạn chế type reference và constructor invocation

StandardEvaluationContext hỗ trợ type reference qua `T(...)` và constructor invocation qua `new`. Những khả năng này có thể mở rộng phạm vi lớp và hành vi mà expression truy cập.

Nếu expression không cần tạo object hoặc tham chiếu class, đừng cung cấp context rộng chỉ để thuận tiện. SimpleEvaluationContext loại bỏ các khả năng này theo thiết kế.

Nếu thật sự cần trong context tùy chỉnh, hãy xem xét TypeLocator và ConstructorResolver theo allowlist. Chỉ cho phép các kiểu và constructor đã được xác định là cần thiết. Không cho phép một package rộng rồi giả định mọi class trong package đều an toàn.

Cần kiểm tra cả đối số constructor và số lần expression được đánh giá. Một constructor có thể cấp phát object lớn, mở tài nguyên hoặc thực hiện tác dụng phụ.

## 12. Kiểm soát TypeConverter và PropertyAccessor tùy chỉnh

TypeConverter có thể chuyển giá trị giữa các kiểu; PropertyAccessor đọc hoặc ghi property; cả hai đều ảnh hưởng đến hành vi expression.

Chỉ cấu hình converter tùy chỉnh khi expression cần chuyển đổi đó. Một converter tổng quát có thể tạo ra nhiều đường chuyển đổi hơn dự kiến hoặc chấp nhận định dạng đầu vào quá rộng.

Với property accessor tùy chỉnh, tránh fallback sang reflective accessor rộng nếu mục tiêu là giới hạn quyền. Hãy kiểm tra danh sách accessor thực tế trong context và xác nhận accessor nào xử lý từng target type.

Nếu một accessor tùy chỉnh không nhận target type, SpEL có thể thử accessor tiếp theo. Vì vậy, một accessor allowlist đứng trước một accessor tổng quát không tự bảo đảm từ chối property ngoài danh sách nếu accessor sau vẫn đọc được chúng. Cần thiết kế danh sách accessor sao cho không còn đường truy cập rộng ngoài ý muốn.

## 13. Tạo một context tối thiểu cho biểu thức chỉ đọc

Ví dụ sau cung cấp root object chuyên biệt và context chỉ đọc:

~~~java
public record OrderView(
        String status,
        BigDecimal total,
        boolean customerActive) {
}

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "customerActive and total >= #minimumTotal"
);

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

OrderView view = new OrderView(
    "PAID",
    new BigDecimal("125.00"),
    true
);

context.setVariable(
    "minimumTotal",
    new BigDecimal("100.00")
);

Boolean eligible =
    expression.getValue(context, view, Boolean.class);
~~~

Ví dụ minh họa các nguyên tắc:

- Root object chỉ có ba property cần thiết.
- Context chỉ cho phép data binding đọc.
- Ngưỡng được truyền bằng variable.
- Expression không cần bean, function, type reference hoặc constructor invocation.

Tạo context riêng cho từng lần xử lý nếu variables hoặc root object thay đổi.

## 14. Dùng context riêng cho từng nhiệm vụ

Không nên dùng một context rộng dùng chung cho mọi expression. Các nhiệm vụ khác nhau có thể cần tập quyền khác nhau:

| Nhiệm vụ | Context phù hợp |
|---|---|
| Hiển thị nhãn từ DTO | Read-only data binding |
| Kiểm tra điều kiện trên object view | Read-only context và variables cần thiết |
| Tính toán với function thuần | Context có đúng function allowlist |
| Cập nhật một DTO chuyên biệt | Read-write accessor với write allowlist |
| Quy tắc cần gọi service | Xử lý service ở Java hoặc bean resolver giới hạn |
| Template do người dùng chỉnh sửa | Context giới hạn, root object hẹp, không có quyền thực thi dư thừa |

Tách context theo nhiệm vụ giúp một expression không vô tình thừa hưởng quyền chỉ cần cho expression khác. Nó cũng làm test dễ đọc hơn vì mỗi context có hợp đồng cụ thể.

Không tái sử dụng context mutable giữa các request khác nhau nếu biến, root object hoặc quyền truy cập có thể thay đổi. Việc chia sẻ context rộng có thể gây rò rỉ dữ liệu và hành vi khó dự đoán.

## 15. Kiểm tra quyền dư thừa bằng negative tests

Một test chỉ chứng minh expression hợp lệ chạy được chưa đủ để xác nhận context đã được thu hẹp. Cần có negative tests cho những hành động phải bị từ chối.

Ví dụ, nếu expression chỉ được đọc displayName:

- Đọc displayName phải thành công.
- Gán displayName phải bị từ chối.
- Gọi method thay đổi role phải bị từ chối hoặc không thể truy cập.
- Tham chiếu bean không được cung cấp phải thất bại.
- Type reference hoặc constructor không được phép phải không thực hiện được.
- Property không nằm trong allowlist phải bị từ chối.

Có thể viết test bằng JUnit:

~~~java
@Test
void readOnlyContextCanReadButCannotWrite() {
    EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Profile profile = new Profile("An");

    Expression read =
        parser.parseExpression("displayName");

    assertEquals(
        "An",
        read.getValue(context, profile, String.class)
    );

    Expression write =
        parser.parseExpression("displayName = 'Binh'");

    assertThrows(
        EvaluationException.class,
        () -> write.getValue(context, profile)
    );
}
~~~

Kiểu exception chính xác có thể phụ thuộc thao tác và phiên bản Spring; hãy kiểm tra exception hierarchy thực tế của dự án. Điều quan trọng là test chứng minh thao tác ghi không xảy ra và object vẫn giữ giá trị ban đầu.

Negative tests nên kiểm tra cả kết quả và trạng thái object sau khi bị từ chối.

## 16. So sánh context rộng và context thu hẹp

Một cách phát hiện quyền dư thừa là lập bảng hành vi cho expression trên context hiện tại và context mục tiêu:

| Thao tác | Context hiện tại | Context thu hẹp mong muốn |
|---|---|---|
| Đọc property cần thiết | Thành công | Thành công |
| Đọc property nhạy cảm | Có thể đang thành công | Bị từ chối hoặc không có trong root view |
| Ghi property | Có thể được phép | Bị từ chối |
| Gọi method không cần thiết | Có thể được phép | Bị từ chối |
| Tham chiếu bean | Có thể phân giải | Không có hoặc allowlist hẹp |
| Gọi function ngoài nhu cầu | Có thể đã đăng ký | Không đăng ký |
| Type reference/constructor | Có thể được hỗ trợ | Không hỗ trợ hoặc allowlist rõ |

Chạy cùng một bộ test trên cả hai cấu hình. Với các thao tác cần thiết, kết quả phải giữ nguyên. Với thao tác dư thừa, context thu hẹp phải từ chối.

Không nên dùng context rộng làm tiêu chuẩn đúng cho mọi hành vi. Mục tiêu là bảo toàn các use case được chấp thuận và loại bỏ khả năng không cần thiết.

## 17. Theo dõi thay đổi quyền khi expression hoặc model thay đổi

Quyền có thể mở rộng ngoài ý muốn khi:

- Root object được đổi từ DTO sang entity đầy đủ.
- Thêm method invocation vào expression.
- Đăng ký thêm bean hoặc function.
- Thay SimpleEvaluationContext bằng StandardEvaluationContext.
- Bổ sung reflective accessor hoặc resolver tổng quát.
- Bật assignment hoặc constructor invocation.
- Thay đổi kiểu của biến hoặc property.

Hãy lưu danh sách capability mà từng expression được phép dùng cùng test tương ứng. Khi sửa expression hoặc context, chạy lại positive và negative tests.

Nếu expression được lưu trong database hoặc cấu hình bên ngoài, nên gắn identifier/version cho template. Khi thay đổi template, kiểm tra nó với context dự kiến trước khi phát hành.

Không nên cấp thêm quyền toàn cục để sửa một expression riêng lẻ. Nếu một expression cần thêm khả năng, hãy đánh giá nhu cầu và tạo context riêng cho nó.

## 18. Gỡ lỗi khi expression bị từ chối

Khi một expression thất bại sau khi thu hẹp context, hãy xác định khả năng nào đang bị thiếu:

1. Root object có đúng kiểu và property cần thiết không?
2. Variable bắt buộc đã được đăng ký chưa?
3. PropertyAccessor có hỗ trợ target type không?
4. Expression có gọi method mà context không bật không?
5. Có bean reference nhưng không có BeanResolver không?
6. Có function nhưng chưa đăng ký không?
7. Có type reference hoặc constructor bị giới hạn không?
8. Giá trị có cần conversion mà converter hiện tại không hỗ trợ không?
9. Đây là lỗi quyền truy cập mong muốn hay cấu hình bị thiếu?

Nếu thao tác bị từ chối là thao tác ngoài nhu cầu, test đang xác nhận đúng chính sách. Nếu đó là hành vi hợp lệ của use case, chỉ bổ sung đúng capability cần thiết rồi cập nhật test.

Không giải quyết lỗi bằng cách chuyển mọi expression sang StandardEvaluationContext hoặc thêm reflective resolver rộng. Cách đó có thể làm test hiện tại chạy qua nhưng tái mở quyền đã chủ động loại bỏ.

## 19. Ghi log và quan sát capability

Trong môi trường phát triển, có thể ghi nhận cấu hình context và identifier của expression để biết một expression được đánh giá với tập quyền nào.

Nên ghi:

- Expression identifier hoặc template version.
- Loại EvaluationContext được sử dụng.
- Root object type hoặc DTO type.
- Các variable name đã được cung cấp, không nhất thiết ghi giá trị.
- Các accessor/resolver/function được cấu hình.
- Loại thao tác bị từ chối và property hoặc method liên quan.
- Exception type và cause chain.

Không ghi toàn bộ object, password, token, dữ liệu cá nhân hoặc giá trị variable nhạy cảm. Log nên giúp xác định capability bị gọi mà không biến thành bản sao của dữ liệu nghiệp vụ.

Ở production, dùng metric hoặc log có giới hạn để theo dõi lỗi từ chối. Một đợt tăng đột biến có thể chỉ ra template cũ chưa được cập nhật, thay đổi model hoặc một nguồn đang cố sử dụng capability ngoài allowlist.

## 20. Checklist thu nhỏ context

Trước khi đưa expression vào sử dụng, hãy xác nhận:

1. Root object chỉ chứa dữ liệu expression cần.
2. Variable được đăng ký rõ ràng và có kiểu dự kiến.
3. Context read-only nếu không cần cập nhật.
4. PropertyAccessor chỉ hỗ trợ target type và property được duyệt.
5. Method invocation bị tắt nếu không cần.
6. BeanResolver không được cung cấp nếu không cần bean reference.
7. Nếu cần bean, resolver chỉ phân giải bean allowlist.
8. Chỉ đăng ký function thực sự cần.
9. Type reference và constructor invocation không được mở nếu không cần.
10. Converter không chấp nhận thêm định dạng ngoài hợp đồng.
11. Không có accessor/resolver tổng quát vô tình mở lại quyền.
12. Có positive tests cho thao tác cần thiết.
13. Có negative tests cho thao tác dư thừa.
14. Test xác nhận object không bị thay đổi khi thao tác bị từ chối.
15. Context không chia sẻ mutable state giữa các request không liên quan.

Checklist này giúp biến "context có vẻ an toàn" thành một hợp đồng quyền có thể kiểm thử.

## 21. Ghi nhớ

EvaluationContext là ranh giới quyết định dữ liệu và khả năng mà SpEL được phép sử dụng. Hãy bắt đầu bằng root object nhỏ hoặc DTO chỉ đọc, truyền giá trị cần thiết qua variables và chọn SimpleEvaluationContext khi biểu thức chỉ cần data binding giới hạn.

PropertyAccessor kiểm soát đọc/ghi property; MethodResolver kiểm soát lời gọi method; BeanResolver kiểm soát bean reference; function registration cho phép gọi các Method đã chọn; TypeLocator và ConstructorResolver ảnh hưởng type reference và constructor invocation. Không để accessor hoặc resolver tổng quát vô tình mở lại quyền sau một allowlist.

Để phát hiện quyền dư thừa, kiểm thử cả hành vi hợp lệ lẫn hành vi phải bị từ chối. So sánh context hiện tại với context thu hẹp, xác nhận kết quả hợp lệ vẫn giữ nguyên và thao tác ngoài nhu cầu không thể thực hiện. Khi expression bị từ chối, bổ sung đúng capability cần thiết thay vì mở rộng toàn bộ context.

Thu nhỏ context không thay thế authorization trong service hoặc validation nghiệp vụ. Những hành động thay đổi dữ liệu, phân quyền hoặc tài nguyên vẫn nên đi qua API Java có hợp đồng và kiểm soát rõ ràng.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)
- [MethodResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)