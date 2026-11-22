# Property không tồn tại và lỗi đánh giá

## Mục tiêu

Khi SpEL truy cập một property, biểu thức phải tìm được cách đọc property đó trên object hiện tại. Nếu tên property sai, model không cung cấp property, hoặc EvaluationContext không có PropertyAccessor phù hợp, quá trình đánh giá có thể thất bại tại runtime.

Điểm cần phân biệt là **property không tồn tại**, **property tồn tại nhưng không thể đọc**, và **object trung gian là null**. Ba trường hợp này có nguyên nhân và cách sửa khác nhau. Toán tử safe navigation chỉ xử lý receiver null; nó không làm cho một property không tồn tại trở thành hợp lệ.

Sau bài này, bạn có thể:

- Nhận biết lỗi khi SpEL không phân giải được property.
- Phân biệt lỗi cú pháp, lỗi property access và lỗi do dữ liệu null.
- Kiểm tra JavaBean getter, field, kiểu root object và PropertyAccessor.
- Hiểu ảnh hưởng của StandardEvaluationContext và SimpleEvaluationContext.
- Dùng safe navigation đúng chỗ và không che giấu lỗi model.
- Viết kiểm thử để phát hiện lỗi property trước khi triển khai.

## 1. Khi nào property được xem là không tồn tại?

Giả sử root object là một Customer:

~~~java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

Biểu thức sau có thể đọc property name:

~~~text
name
~~~

Trong khi đó, biểu thức sau yêu cầu một property khác:

~~~text
email
~~~

Nếu Customer không cung cấp property email và không có PropertyAccessor nào trong EvaluationContext có thể đọc nó, SpEL không thể hoàn thành việc đánh giá. Thông thường, lời gọi getValue sẽ ném SpelEvaluationException.

Property không tồn tại có thể đến từ nhiều nguyên nhân:

- Viết sai tên property, chẳng hạn emailAddress thay vì email.
- Đổi tên field hoặc getter trong Java nhưng quên cập nhật chuỗi SpEL.
- Dùng nhầm root object; biểu thức kỳ vọng Customer nhưng thực tế nhận Account.
- Getter không có, không phù hợp với quy tắc JavaBean hoặc không thể truy cập theo accessor đang dùng.
- PropertyAccessor tùy chỉnh không được đăng ký hoặc không nhận diện property đó.
- EvaluationContext được cấu hình giới hạn hơn môi trường mà biểu thức ban đầu được viết.

Vì SpEL thường nhận tên property dưới dạng chuỗi, compiler Java không thể bảo đảm mọi tham chiếu trong biểu thức đều được cập nhật khi model thay đổi. Một refactor đổi tên getter có thể biên dịch thành công nhưng làm một biểu thức lưu trong cấu hình thất bại khi chạy.

## 2. Parse thành công không có nghĩa là property hợp lệ

SpEL thường có hai giai đoạn:

1. **Parse:** parser kiểm tra cú pháp biểu thức và tạo đối tượng Expression.
2. **Evaluate:** Expression được đánh giá với root object và EvaluationContext cụ thể.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("email");
~~~

Dòng parse có thể thành công vì email là một tên property hợp lệ về mặt cú pháp. Parser không nhất thiết biết root object thực tế sẽ là Customer, Account hay một loại object khác. Việc phân giải property thường diễn ra khi biểu thức được đánh giá:

~~~java
String value = expression.getValue(context, customer, String.class);
~~~

Nếu customer không có property email mà context cũng không có accessor nào cung cấp property đó, lỗi xuất hiện ở bước getValue.

Vì vậy, chỉ kiểm tra parse không đủ để xác nhận biểu thức có thể chạy. Với biểu thức phụ thuộc vào model, cần kiểm thử đánh giá trên root object đại diện và đúng loại EvaluationContext mà ứng dụng sử dụng.

## 3. Property tồn tại nhưng không thể đọc

Một property có thể tồn tại trong class nhưng vẫn không đọc được qua SpEL. SpEL không truy cập mọi field hoặc method theo một quy tắc duy nhất; việc truy cập phụ thuộc PropertyAccessor được cấu hình trong context.

Với JavaBean, property thường được biểu diễn bằng getter:

~~~java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }
}
~~~

Biểu thức đọc property:

~~~text
name
~~~

Một số điều cần kiểm tra:

- Tên property có đúng với quy tắc JavaBean hay không.
- Getter có đúng chữ ký và kiểu trả về dự kiến hay không.
- Getter hoặc field có visibility phù hợp với accessor hay không.
- Class có được proxy hoặc bọc bởi một object khác khiến kiểu root thực tế khác dự kiến hay không.
- Context có PropertyAccessor tương ứng hay không.

Với property Boolean, JavaBean có thể dùng getter dạng isActive(). Không nên tự suy đoán tên property từ tên field nếu class có getter tùy chỉnh. Hãy kiểm tra model thực tế và quy tắc accessor đang chạy.

### Field và getter không giống nhau

Một field private tên email không tự động bảo đảm mọi EvaluationContext có thể đọc nó. ReflectivePropertyAccessor trong cấu hình chuẩn có thể hỗ trợ các JavaBean property và field theo quy tắc truy cập của nó, nhưng SimpleEvaluationContext có thể dùng DataBindingPropertyAccessor với giới hạn data binding. Một PropertyAccessor tùy chỉnh còn có thể áp dụng quy tắc khác.

Nếu muốn biểu thức đọc một property, hãy thiết kế public getter rõ ràng hoặc cung cấp accessor chuyên biệt. Đừng dựa vào việc một field nội bộ tình cờ đọc được trong một context cụ thể.

## 4. Phân biệt property không tồn tại với object null

Hai tình huống sau khác nhau:

~~~text
customer.email
customer?.email
~~~

- Nếu customer là null, biểu thức đầu có thể thất bại khi cố truy cập email trên null.
- Nếu customer không null nhưng không có property email, cả hai biểu thức đều không thể đọc được property đó.

Toán tử safe navigation **?.** bảo vệ một thao tác truy cập khi object ở bên trái là null. Nó không bỏ qua lỗi phân giải property trên một object đang tồn tại.

Ví dụ, nếu Customer có property name nhưng address có thể null:

~~~text
address?.city
~~~

Khi address null, kết quả của bước truy cập là null. Khi address tồn tại, SpEL vẫn phải tìm được property city trên object đó.

Nếu property city không tồn tại, safe navigation không sửa được lỗi. Cần sửa tên property, model hoặc accessor.

### Safe navigation trên đường dẫn nhiều cấp

Với đường dẫn có nhiều object trung gian có thể null, hãy đặt safe navigation tại từng bước cần bảo vệ:

~~~text
order?.customer?.address?.city
~~~

Mỗi toán tử bảo vệ receiver ngay trước nó. Không giả định một dấu ?. ở đầu đường dẫn sẽ tự động làm mọi bước tiếp theo an toàn trước null. Hãy xác định rõ object nào có thể null và kiểm thử từng tình huống.

### Elvis không xử lý property bị thiếu

Toán tử Elvis có thể cung cấp giá trị mặc định khi vế trái đánh giá thành null:

~~~text
customer.name ?: 'Khách hàng'
~~~

Nếu name tồn tại nhưng có giá trị null, biểu thức có thể dùng giá trị mặc định. Tuy nhiên, nếu property name không thể được phân giải, SpEL vẫn phát sinh lỗi trước khi Elvis có thể chọn giá trị thay thế.

Tương tự:

~~~text
customer?.nickname ?: 'Khách hàng'
~~~

Cú pháp này có thể xử lý customer null hoặc nickname null nếu property nickname tồn tại và đọc được. Nó không biến một property không tồn tại thành property hợp lệ.

## 5. Kiểm tra từng đoạn của property path

Một đường dẫn lồng nhau có thể gồm nhiều bước:

~~~text
order.customer.address.city
~~~

Nếu đánh giá thất bại, chưa chắc city là nguyên nhân. Lỗi có thể xuất hiện ở customer, address hoặc city. Cách chẩn đoán hiệu quả là kiểm tra từng đoạn theo thứ tự:

~~~text
customer
customer.address
customer.address.city
~~~

Với root object là order, mỗi biểu thức trên giúp xác định bước đầu tiên không thể đọc được.

Hãy kiểm tra:

1. Root object có đúng loại mà biểu thức kỳ vọng không?
2. Property đầu tiên có đọc được không?
3. Giá trị trả về có đúng kiểu object dự kiến không?
4. Object trung gian có null không?
5. Property tiếp theo có tồn tại và được accessor hỗ trợ không?

Không nên sửa biểu thức bằng cách thêm safe navigation ở mọi nơi mà chưa xác định nguyên nhân. Nếu một property bị viết sai tên, safe navigation không giúp khôi phục ý định ban đầu.

## 6. Ảnh hưởng của EvaluationContext

EvaluationContext quyết định cách SpEL phân giải property và method. Hai context khác nhau có thể đánh giá cùng một biểu thức với kết quả khác nhau.

### StandardEvaluationContext

StandardEvaluationContext linh hoạt và thường sử dụng ReflectivePropertyAccessor để đọc property qua cơ chế phản chiếu. Nó có thể được mở rộng bằng PropertyAccessor tùy chỉnh và các resolver khác.

Khi biểu thức hoạt động trong context này nhưng thất bại ở môi trường khác, hãy so sánh danh sách accessor và cấu hình thực tế. Đừng mặc định rằng mọi context đều có cùng khả năng truy cập.

### SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho các tình huống data binding với tập khả năng hạn chế hơn. Ví dụ context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Context này phù hợp khi ứng dụng chỉ cần đọc dữ liệu qua các accessor được hỗ trợ. Một property chỉ đọc được trong context phản chiếu rộng hơn có thể không truy cập được trong context data binding giới hạn, tùy model và accessor.

Nếu ứng dụng có PropertyAccessor riêng, hãy đăng ký nó trong factory tạo context và dùng cùng factory đó trong production lẫn test. Điều này tránh việc test xác nhận một cấu hình khác với cấu hình thực tế.

### PropertyAccessor tùy chỉnh

Ứng dụng có thể dùng PropertyAccessor để cung cấp property từ một nguồn hoặc cấu trúc riêng. Ví dụ, accessor có thể đọc thuộc tính từ một đối tượng cấu hình động hoặc một wrapper.

Khi dùng accessor tùy chỉnh, kiểm tra hai khả năng:

- Accessor có nhận diện đúng target object và tên property trong bước canRead hay không.
- Phương thức read có thực sự trả về giá trị đúng và kiểu dữ liệu dự kiến hay không.

Nếu canRead trả về false, SpEL có thể thử accessor khác. Nếu không có accessor nào đọc được property, việc đánh giá sẽ thất bại. Nếu accessor nhận diện property nhưng chính thao tác read ném lỗi, cần xem xét logic của accessor và dữ liệu đầu vào.

## 7. Đọc lỗi SpEL và xử lý ngoại lệ

Lỗi khi đánh giá SpEL thường được biểu diễn bằng SpelEvaluationException, một loại EvaluationException của Spring Expression. Thông báo lỗi thường cung cấp thông tin về thao tác không thực hiện được, tên property hoặc vị trí biểu thức liên quan.

Ví dụ xử lý lỗi tại ranh giới của ứng dụng:

~~~java
try {
    String email = expression.getValue(context, customer, String.class);
    return email;
} catch (SpelEvaluationException ex) {
    // Ghi nhận lỗi đánh giá với ID biểu thức và ngữ cảnh an toàn.
    throw new InvalidRuleException("Không thể đánh giá property trong rule", ex);
}
~~~

Cách xử lý nên phù hợp với vai trò của biểu thức:

- Với biểu thức cố định trong mã nguồn, lỗi có thể chỉ ra bug hoặc thay đổi model chưa được cập nhật.
- Với biểu thức trong cấu hình, lỗi có thể là cấu hình không hợp lệ và nên được phát hiện khi nạp.
- Với biểu thức do quản trị viên tạo, cần trả lỗi xác thực dễ hiểu trước khi kích hoạt.
- Với biểu thức được đánh giá trong request, hãy chuyển lỗi thành phản hồi nghiệp vụ phù hợp và ghi log đủ để truy vết.

Không nên bắt mọi RuntimeException rồi trả null. Cách làm đó có thể biến lỗi model thành kết quả có vẻ hợp lệ và khiến hệ thống đưa ra quyết định sai.

Cũng không nên hiển thị stack trace hoặc dữ liệu nhạy cảm của root object cho người dùng cuối. Hãy ghi ID biểu thức, phiên bản, loại lỗi và correlation ID; chỉ ghi dữ liệu đầu vào khi đã xác định rằng dữ liệu đó an toàn để log.

## 8. Kiểm thử lỗi property

Một bộ kiểm thử tốt nên xác minh cả trường hợp property đọc được và trường hợp không đọc được.

Ví dụ model:

~~~java
public class Customer {
    private String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Kiểm thử property tồn tại:

~~~java
@Test
void readsExistingProperty() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("name");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertEquals("Lan", expression.getValue(context, customer, String.class));
}
~~~

Kiểm thử property không tồn tại:

~~~java
@Test
void failsWhenPropertyDoesNotExist() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("email");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertThrows(
        SpelEvaluationException.class,
        () -> expression.getValue(context, customer)
    );
}
~~~

Kiểm thử null trung gian và safe navigation:

~~~java
@Test
void handlesNullIntermediateObject() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("address?.city");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Customer customer = new Customer("Lan");

    assertNull(expression.getValue(context, customer));
}
~~~

Ví dụ cuối giả định Customer có property address và giá trị address đang null. Nếu property address không tồn tại, safe navigation không thể giúp biểu thức đọc được property đó. Hãy bảo đảm model trong test phản ánh đúng tình huống cần kiểm tra.

Nên có các trường hợp sau trong bộ kiểm thử của biểu thức:

| Trường hợp | Điều cần xác minh |
|---|---|
| Property hợp lệ và có giá trị | Trả về đúng giá trị và kiểu |
| Property hợp lệ nhưng null | Null được xử lý theo hợp đồng |
| Property không tồn tại | Lỗi được phát hiện rõ ràng |
| Getter không đọc được | Accessor/context phản ánh đúng giới hạn |
| Root object null | Biểu thức có hành vi được quy định |
| Object trung gian null | Safe navigation được đặt đúng bước |
| Property path nhiều cấp | Xác định chính xác đoạn gây lỗi |
| Context thay đổi | Biểu thức vẫn hoạt động hoặc thất bại có chủ đích |
| Model đổi tên property | Test hồi quy phát hiện tham chiếu cũ |

## 9. Quy trình chẩn đoán trong ứng dụng

Khi một biểu thức bắt đầu thất bại trong môi trường chạy thực tế, hãy xử lý theo trình tự:

1. **Lấy đúng biểu thức và phiên bản.** Đảm bảo đang điều tra đúng chuỗi được nạp ở instance gặp lỗi.
2. **Xác định root object thực tế.** Kiểm tra class của object được truyền vào getValue và tránh log toàn bộ dữ liệu nhạy cảm.
3. **Tách parse khỏi evaluate.** Xác định lỗi xảy ra khi tạo Expression hay khi gọi getValue.
4. **Kiểm tra property path từng bước.** Bắt đầu từ root rồi mở rộng từng đoạn cho tới khi xác định property đầu tiên không đọc được.
5. **Kiểm tra model và accessor.** Đối chiếu getter, field, visibility, custom PropertyAccessor và loại EvaluationContext.
6. **Kiểm tra null riêng biệt.** Xác định object nào null; chỉ dùng safe navigation khi null là tình huống được chấp nhận.
7. **Tạo regression test.** Đưa root object, context và dữ liệu gây lỗi vào test để lỗi không quay lại.
8. **Triển khai thay đổi có kiểm soát.** Nếu biểu thức nằm trong cấu hình, xác thực phiên bản mới trước khi kích hoạt và giữ khả năng rollback.

Nếu lỗi chỉ xuất hiện ở một số instance, so sánh model thực tế, phiên bản ứng dụng, cấu hình context và phiên bản biểu thức giữa các instance. Có thể một node đang chạy model hoặc cấu hình cũ.

## 10. Phòng ngừa lỗi khi model thay đổi

Property path trong SpEL là một hợp đồng runtime với model Java. Khi đổi tên hoặc cấu trúc property, cần tìm mọi nơi lưu chuỗi biểu thức:

- Annotation và cấu hình XML.
- File properties, YAML hoặc JSON.
- Database hoặc bảng quản lý rule.
- Hệ thống quản trị biểu thức.
- Test fixture và dữ liệu mẫu.
- Các biểu thức được tạo động trong Java.

Nếu biểu thức được quản lý tập trung, nên lưu kèm root type, mục đích, phiên bản và danh sách property được sử dụng. Có thể xác thực tất cả biểu thức với root object mẫu khi ứng dụng khởi động hoặc khi cấu hình được cập nhật.

Đối với thay đổi model lớn, hãy chạy kiểm thử hồi quy trên toàn bộ tập biểu thức liên quan. Một test chỉ parse chuỗi không phát hiện được property path sai; cần đánh giá biểu thức với object đại diện.

## 11. Checklist review

Trước khi chấp nhận biểu thức truy cập property, hãy kiểm tra:

- [ ] Root object có đúng loại theo hợp đồng biểu thức.
- [ ] Property name khớp với model và getter thực tế.
- [ ] Property được đọc bởi PropertyAccessor đang dùng.
- [ ] EvaluationContext trong test giống cấu hình production.
- [ ] Các object trung gian có thể null được xử lý riêng.
- [ ] Safe navigation chỉ dùng cho trường hợp receiver null được chấp nhận.
- [ ] Elvis không được dùng với kỳ vọng che giấu property không tồn tại.
- [ ] Có test cho property hợp lệ, property thiếu và object null.
- [ ] Lỗi parse và lỗi evaluate được phân biệt.
- [ ] Log có ID biểu thức và thông tin truy vết cần thiết mà không lộ dữ liệu nhạy cảm.
- [ ] Thay đổi model có kiểm tra các chuỗi SpEL được lưu ngoài mã nguồn.

## Kết luận

Lỗi property trong SpEL thường xuất hiện khi tên property không đúng, model thay đổi, root object không như dự kiến hoặc EvaluationContext không có accessor phù hợp. Parse thành công chỉ xác nhận cú pháp, còn việc property có thể đọc hay không thường được xác định khi đánh giá với object thực tế. Hãy phân biệt property thiếu với receiver null, kiểm tra từng đoạn của đường dẫn, dùng safe navigation đúng chỗ và kiểm thử bằng cùng context với production. Nhờ đó, lỗi runtime có thể được phát hiện sớm và chẩn đoán bằng nguyên nhân cụ thể.
