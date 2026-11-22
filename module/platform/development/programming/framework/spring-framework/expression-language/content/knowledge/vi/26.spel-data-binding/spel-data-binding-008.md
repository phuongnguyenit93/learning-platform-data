# Giới hạn property được phép ghi

## Mục tiêu

Sau bài này, bạn có thể giới hạn những property mà biểu thức Spring Expression Language (SpEL) được phép thay đổi; phân biệt quyền đọc với quyền ghi; chọn DataBindingPropertyAccessor hoặc PropertyAccessor tùy chỉnh; và thiết kế allowlist cho các property được phép cập nhật. Bạn cũng sẽ biết cách phân biệt assignment trong biểu thức với API setValue của Java, xử lý property lồng nhau, và kiểm thử những thao tác ghi bị từ chối.

## 1. Vì sao cần giới hạn property được phép ghi?

SpEL có thể đọc property và, tùy EvaluationContext, thay đổi property của object. Ví dụ:

~~~text
displayName = 'An'
~~~

Nếu biểu thức được đánh giá trên một JavaBean có setter public cho displayName và context cho phép ghi, giá trị của object có thể bị thay đổi.

Quyền ghi rộng có thể tạo ra rủi ro khi biểu thức đến từ cấu hình, người dùng hoặc một nguồn mà ứng dụng không kiểm soát hoàn toàn. Một biểu thức có thể vô tình ghi đè trạng thái quan trọng như role, ownerId, balance, status hoặc các trường dùng trong phân quyền.

Không phải mọi property đều nên có thể ghi chỉ vì JavaBean cung cấp setter. Ứng dụng cần xác định rõ:

- Property nào được phép đọc.
- Property nào được phép ghi.
- Object hoặc kiểu dữ liệu nào được phép truy cập.
- Những thao tác ghi nào phải thực hiện qua service để áp dụng validation và quy tắc nghiệp vụ.

Nguyên tắc quan trọng là cấp đúng quyền tối thiểu mà biểu thức cần. Nếu biểu thức chỉ dùng để lọc hoặc tính toán, context chỉ đọc thường là lựa chọn phù hợp.

## 2. PropertyAccessor quyết định khả năng đọc và ghi

SpEL sử dụng PropertyAccessor để truy cập property của object. Một accessor có thể hỗ trợ đọc, ghi hoặc cả hai.

Các phương thức chính của PropertyAccessor gồm:

- `canRead(...)`: cho biết accessor có thể đọc property được yêu cầu hay không.
- `read(...)`: đọc giá trị property.
- `canWrite(...)`: cho biết accessor có thể ghi property hay không.
- `write(...)`: thực hiện ghi giá trị vào property.

Khi đánh giá một biểu thức đọc property, SpEL tìm accessor phù hợp rồi gọi thao tác đọc. Khi biểu thức yêu cầu ghi, SpEL cần accessor hỗ trợ ghi và property đích phải có thể cập nhật.

Ví dụ:

~~~text
customer.displayName
~~~

là truy cập đọc thông thường.

~~~text
customer.displayName = 'An'
~~~

là thao tác ghi vào displayName. Việc đọc được property không đồng nghĩa accessor cũng cho phép ghi property đó.

Đây là điểm kiểm soát quan trọng: chính sách quyền ghi có thể được thực hiện tại accessor thay vì dựa vào việc người viết biểu thức có nhớ tránh các property nhạy cảm hay không.

## 3. Read-only và read-write data binding

SimpleEvaluationContext cung cấp các factory để cấu hình data binding theo hai chế độ.

Context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Context đọc và ghi:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Hai cấu hình sử dụng DataBindingPropertyAccessor với quyền khác nhau:

| Cấu hình | Đọc property | Ghi property |
|---|---|---|
| forReadOnlyDataBinding() | Có | Không |
| forReadWriteDataBinding() | Có | Có, nếu property hỗ trợ ghi |

DataBindingPropertyAccessor được thiết kế cho data binding và truy cập các public property phù hợp. Nó không mở toàn bộ khả năng truy cập reflection của StandardEvaluationContext. Một số kiểu hoặc property nhạy cảm, chẳng hạn các property liên quan đến Class và ClassLoader, bị giới hạn theo thiết kế của accessor.

Tuy nhiên, chế độ read-write vẫn có thể cho phép ghi nhiều public property của object được cung cấp. Nếu chỉ muốn cho phép một tập property nhỏ, hãy dùng PropertyAccessor tùy chỉnh với allowlist thay vì coi read-write data binding là chính sách phân quyền theo từng trường.

## 4. Gán property bằng biểu thức

Khi context hỗ trợ assignment và accessor cho phép ghi, SpEL có thể gán property bằng toán tử dấu bằng:

~~~text
displayName = 'An'
~~~

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("displayName = 'An'");

Profile profile = new Profile();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.getValue(context, profile);
~~~

Biểu thức được đánh giá với profile làm root object. SpEL tìm property displayName và sử dụng accessor để ghi giá trị.

Nếu context được tạo bằng forReadOnlyDataBinding(), thao tác gán không được chấp nhận. Nếu accessor không cho phép ghi displayName, thao tác cũng bị từ chối dù object có setter public.

Kết quả cụ thể còn phụ thuộc kiểu property và khả năng chuyển đổi giá trị. Nếu property là String và biểu thức tạo String, không cần chuyển đổi phức tạp. Nếu kiểu không tương thích, TypeConverter có thể được yêu cầu trước khi accessor ghi giá trị.

## 5. Gán qua Expression.setValue()

Ngoài toán tử gán trong chuỗi SpEL, Java có thể yêu cầu ghi property thông qua API Expression.setValue():

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("displayName");

Profile profile = new Profile();

EvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

expression.setValue(context, profile, "An");
~~~

Trong ví dụ, biểu thức chỉ xác định property displayName. Mã Java gọi setValue để ghi giá trị vào property đó.

Cả assignment trong biểu thức và setValue đều cần accessor có khả năng ghi. Vì vậy, một allowlist được triển khai đúng trong PropertyAccessor có thể kiểm soát cả hai đường ghi này.

Cần phân biệt quyền ghi của accessor với cờ cho phép assignment trong biểu thức. Builder của SimpleEvaluationContext có thể hỗ trợ withAssignmentDisabled() ở những phiên bản Spring tương ứng để tắt toán tử assignment trong biểu thức. Cờ này giới hạn cú pháp assignment; chính sách canWrite của accessor vẫn là nơi kiểm soát property nào được phép ghi qua cơ chế truy cập property.

Không dùng việc tắt assignment như một thay thế cho allowlist property nếu ứng dụng vẫn gọi setValue từ Java.

## 6. Giới hạn ghi theo allowlist

Nếu ứng dụng chỉ muốn cho phép cập nhật displayName nhưng cấm cập nhật role, balance và ownerId, có thể tạo PropertyAccessor tùy chỉnh.

Ý tưởng của allowlist:

| Property | Đọc | Ghi |
|---|---|---|
| displayName | Cho phép | Cho phép |
| locale | Cho phép | Cho phép nếu nghiệp vụ cần |
| role | Cho phép hoặc hạn chế | Từ chối |
| balance | Cho phép hoặc hạn chế | Từ chối |
| ownerId | Cho phép hoặc hạn chế | Từ chối |
| passwordHash | Từ chối hoặc chỉ cung cấp qua API chuyên biệt | Từ chối |

Allowlist nên mô tả rõ quyền đọc và quyền ghi riêng biệt. Một property có thể cần đọc để hiển thị hoặc kiểm tra điều kiện nhưng không được phép sửa qua SpEL.

Trong accessor tùy chỉnh:

- `canRead(...)` chỉ trả về true cho những property được phép đọc.
- `read(...)` chỉ trả về giá trị của property đã được chấp thuận.
- `canWrite(...)` chỉ trả về true cho property nằm trong danh sách được phép ghi.
- `write(...)` thực hiện cập nhật và từ chối mọi tên property ngoài allowlist.

Không nên chỉ kiểm tra tên property ở giao diện hoặc trong chuỗi expression. Quyết định cuối cùng cần được thực thi tại accessor vì mọi biểu thức đều đi qua cơ chế này khi truy cập property.

## 7. Ví dụ PropertyAccessor tùy chỉnh

Ví dụ dưới đây minh họa accessor cho một Profile. Accessor cho phép đọc displayName và role, nhưng chỉ cho phép ghi displayName.

~~~java
import org.springframework.expression.AccessException;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.PropertyAccessor;
import org.springframework.expression.TypedValue;

public class ProfilePropertyAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Profile.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context, Object target, String name) {
        return target instanceof Profile
            && ("displayName".equals(name) || "role".equals(name));
    }

    @Override
    public TypedValue read(
            EvaluationContext context, Object target, String name)
            throws AccessException {

        Profile profile = (Profile) target;

        if ("displayName".equals(name)) {
            return new TypedValue(profile.getDisplayName());
        }

        if ("role".equals(name)) {
            return new TypedValue(profile.getRole());
        }

        throw new AccessException("Property is not readable: " + name);
    }

    @Override
    public boolean canWrite(
            EvaluationContext context, Object target, String name) {
        return target instanceof Profile
            && "displayName".equals(name);
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!canWrite(context, target, name)) {
            throw new AccessException("Property is not writable: " + name);
        }

        if (!(newValue instanceof String)) {
            throw new AccessException("displayName must be a String");
        }

        Profile profile = (Profile) target;
        profile.setDisplayName((String) newValue);
    }
}
~~~

Đăng ký accessor với SimpleEvaluationContext:

~~~java
EvaluationContext context =
    SimpleEvaluationContext
        .forPropertyAccessors(new ProfilePropertyAccessor())
        .build();
~~~

Ví dụ này minh họa chính sách allowlist. Trong ứng dụng thực tế, accessor cần xử lý đúng các kiểu null được phép, chuyển đổi kiểu nếu cần và các lỗi setter có thể phát sinh.

Nếu có nhiều loại object, có thể viết accessor riêng cho từng kiểu hoặc một accessor có quy tắc rõ ràng theo target type. Không nên tạo một accessor tổng quát cho phép ghi mọi property chỉ vì tên property không nằm trong một danh sách cấm ngắn.

## 8. Denylist và allowlist

Có hai cách phổ biến để xác định property được phép ghi:

**Denylist** liệt kê các property bị cấm. Những property còn lại có thể được ghi.

**Allowlist** liệt kê rõ những property được phép. Mọi property không nằm trong danh sách đều bị từ chối.

| Cách tiếp cận | Hành vi mặc định | Rủi ro |
|---|---|---|
| Denylist | Cho phép trừ các trường bị cấm | Property mới được thêm vào model có thể vô tình được phép ghi |
| Allowlist | Từ chối trừ các trường được duyệt | Cần cập nhật danh sách khi thêm property mới |

Với dữ liệu nhạy cảm hoặc biểu thức đến từ nguồn bên ngoài, allowlist thường dễ kiểm soát hơn. Khi model thêm property mới, quyền ghi không tự động mở rộng.

Hãy xem xét cả alias hoặc đường dẫn lồng nhau. Nếu accessor cho phép ghi một property ở object con, biểu thức có thể tiếp cận nó qua nhiều đường dẫn khác nhau. Chính sách phải được áp dụng trên target object và property name thực tế mà accessor nhận được.

## 9. Property lồng nhau và quyền ghi ở từng cấp

Một đường dẫn property có thể gồm nhiều cấp:

~~~text
customer.address.city
~~~

Khi đọc, SpEL lần lượt lấy customer, address rồi city. Khi gán:

~~~text
customer.address.city = 'Da Nang'
~~~

SpEL phải đọc được các đối tượng trung gian và ghi được property cuối cùng city.

Quyền ghi city không đồng nghĩa mọi property trên customer hoặc address đều được phép ghi. Accessor cần quyết định theo từng target object và tên property mà nó nhận được.

Ví dụ, ứng dụng có thể cho phép cập nhật address.city nhưng cấm thay thế toàn bộ customer hoặc address. Hãy thiết kế allowlist theo kiểu object và property cụ thể, đồng thời kiểm soát những đường dẫn nào được phép xuất hiện trong expression.

Nếu một đối tượng trung gian là null, thao tác đọc đường dẫn có thể thất bại trước khi tới property cuối cùng. Auto-grow có thể thay đổi hành vi trong một số cấu hình parser, nhưng việc tự tạo object trung gian cũng cần được bật và giới hạn có chủ đích. Không nên bật auto-grow chỉ để tránh lỗi dữ liệu mà không xem xét tác động lên object graph.

## 10. Property có setter nhưng vẫn có thể bị từ chối

Một JavaBean có setter public không tự động đồng nghĩa mọi EvaluationContext đều cho phép ghi.

Có thể xảy ra các trường hợp:

- Context chỉ đọc từ chối ghi dù setter public.
- Accessor tùy chỉnh từ chối property không nằm trong allowlist.
- Property không có setter hoặc không thể cập nhật.
- Property có kiểu đích không tương thích với giá trị mới.
- Setter ném exception do validation hoặc trạng thái object.
- Object hoặc property không được accessor hỗ trợ.

Ví dụ, Profile có setter cho role nhưng accessor chỉ cho phép displayName. Khi expression cố ghi role, canWrite trả về false và SpEL không thực hiện cập nhật qua accessor đó.

Đây là hành vi mong muốn khi role là dữ liệu nhạy cảm. Việc object có khả năng kỹ thuật để thay đổi không có nghĩa biểu thức được cấp quyền thay đổi.

## 11. Conversion không thay thế quyền ghi hoặc validation

Khi gán property, SpEL có thể cần TypeConverter để chuyển giá trị nguồn sang kiểu property đích. Tuy nhiên, ba việc này độc lập:

1. **Conversion:** giá trị có chuyển được sang kiểu property không?
2. **Write permission:** accessor có cho phép ghi property đó không?
3. **Validation:** giá trị mới có thỏa điều kiện nghiệp vụ không?

Ví dụ, chuỗi "25" có thể chuyển thành Integer 25. Nhưng nếu property age bị cấm ghi qua SpEL, thao tác vẫn phải bị từ chối. Nếu property age được phép ghi, giá trị 25 vẫn có thể không hợp lệ theo chính sách của ứng dụng.

Không nên dựa vào setter để thực hiện toàn bộ authorization. Setter thường nên bảo vệ tính nhất quán nội tại của object; quyền người dùng và quy tắc nghiệp vụ nên được kiểm tra tại service hoặc lớp ứng dụng thích hợp.

## 12. Phân biệt quyền ghi property với quyền gọi method

PropertyAccessor kiểm soát việc đọc và ghi property. Nó không phải cơ chế duy nhất quyết định những hành động mà expression có thể thực hiện.

Một biểu thức có thể gọi method trên object nếu EvaluationContext cung cấp MethodResolver phù hợp:

~~~text
profile.changeRole('ADMIN')
~~~

Ngay cả khi accessor không cho phép ghi trực tiếp property role, method changeRole có thể thay đổi role nếu method được phép gọi.

Vì vậy, giới hạn property write chưa đủ để bảo đảm object không thể bị thay đổi. Cần xem xét thêm:

- Những method nào được phép gọi.
- Method có tác dụng phụ hay thay đổi trạng thái không.
- BeanResolver có cho phép truy cập service nhạy cảm không.
- Root object có chứa object có quyền rộng không.
- Các function được đăng ký có thể thay đổi dữ liệu hay không.

Nếu mục tiêu là chỉ cho phép expression đọc dữ liệu, hãy dùng context chỉ đọc và giới hạn cả method resolver, function và bean reference theo nhu cầu. Nếu cần cho phép một số thao tác cập nhật, hãy thiết kế API hẹp với tên và tác dụng rõ ràng.

## 13. SimpleEvaluationContext và StandardEvaluationContext

Hai loại context có phạm vi khả năng khác nhau:

| Khả năng | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Chọn PropertyAccessor | Có | Có |
| Data binding chỉ đọc | Có | Có thể cấu hình |
| Data binding đọc ghi | Có | Có thể cấu hình |
| Custom PropertyAccessor | Có | Có |
| Method invocation | Chỉ khi bật cơ chế phù hợp | Có resolver mặc định và khả năng tùy chỉnh |
| Type reference và constructor | Không hỗ trợ đầy đủ | Có thể cấu hình |
| Bean reference | Không hỗ trợ | Có thể cấu hình BeanResolver |

SimpleEvaluationContext phù hợp với các biểu thức cần tập tính năng giới hạn và quyền property được chọn. StandardEvaluationContext linh hoạt hơn nhưng cần kiểm soát chặt các resolver và object được cung cấp.

Nếu mục tiêu chỉ là ghi một số property đã xác định, custom PropertyAccessor trong SimpleEvaluationContext thường là cách diễn đạt chính sách rõ ràng. Không nên chuyển sang StandardEvaluationContext chỉ để bỏ qua một giới hạn quyền mà ứng dụng đã chủ ý thiết lập.

## 14. Tắt assignment trong biểu thức

Một số phiên bản Spring cung cấp cấu hình builder để tắt assignment trong biểu thức:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadWriteDataBinding()
        .withAssignmentDisabled()
        .build();
~~~

Cấu hình này cho phép accessor data binding đọc ghi, nhưng tắt các toán tử assignment trong expression theo khả năng của phiên bản Spring tương ứng.

Điều này hữu ích khi ứng dụng muốn cho phép một số thao tác ghi được khởi tạo từ Java qua API, nhưng không muốn chuỗi expression tự thực hiện assignment.

Hãy phân biệt ba lớp kiểm soát:

- Read-only accessor: không cho ghi property qua accessor.
- Read-write accessor với allowlist: chỉ cho ghi các property được duyệt.
- Assignment disabled: chặn cú pháp assignment trong biểu thức.

Nếu cần allowlist theo từng property, vẫn phải triển khai canWrite và write phù hợp. Tắt assignment không tự tạo danh sách property được phép ghi.

Kiểm tra Javadoc của phiên bản Spring đang dùng để xác nhận builder có hỗ trợ withAssignmentDisabled() trước khi áp dụng.

## 15. Xử lý lỗi khi ghi property bị từ chối

Khi expression cố ghi vào property không được phép, SpEL có thể phát sinh SpelEvaluationException hoặc lỗi đánh giá liên quan đến việc ghi property. Nếu custom accessor ném AccessException, nguyên nhân có thể được đưa vào exception của SpEL.

Ở lớp gọi expression, nên xử lý lỗi có chủ đích:

~~~java
try {
    expression.getValue(context, profile);
}
catch (EvaluationException ex) {
    // Ghi nhận lỗi và chuyển thành phản hồi phù hợp.
}
~~~

Không nên bắt mọi exception rồi bỏ qua. Cần phân biệt:

- Property không được phép ghi.
- Property không tồn tại.
- Không có setter hoặc accessor phù hợp.
- Giá trị không thể chuyển đổi.
- Setter ném exception.
- Object trung gian null.
- Method hoặc resolver gây lỗi trong một biểu thức phức tạp.

Với custom accessor, thông báo lỗi nên nêu property bị từ chối và target type cần thiết, nhưng tránh ghi dữ liệu nhạy cảm của object vào log. Ở API bên ngoài, không nhất thiết phải tiết lộ chi tiết nội bộ của object model.

## 16. Thiết kế object phù hợp cho data binding

Một cách giảm rủi ro là tạo object đầu vào chuyên biệt chỉ chứa những property mà biểu thức cần thay đổi.

Ví dụ, thay vì truyền một User entity đầy đủ có role, passwordHash và trạng thái tài khoản, ứng dụng có thể tạo một DTO:

~~~java
public class ProfileUpdate {

    private String displayName;
    private String locale;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

SpEL chỉ nhận ProfileUpdate làm root object. Những property nhạy cảm không có trong DTO nên không thể bị sửa thông qua đường dẫn property thông thường của object đó.

DTO chuyên biệt không thay thế allowlist hoặc validation, nhưng thu hẹp bề mặt dữ liệu mà expression có thể tác động. Sau khi binding, service Java vẫn cần kiểm tra quyền, định dạng, miền giá trị và quy tắc nghiệp vụ trước khi cập nhật entity thật.

## 17. Kiểm thử chính sách property được phép ghi

Hãy kiểm thử cả property được phép và property bị từ chối:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Đọc displayName | Thành công nếu nằm trong read allowlist |
| Ghi displayName | Thành công nếu nằm trong write allowlist |
| Đọc role | Theo chính sách đọc đã cấu hình |
| Ghi role | Bị từ chối nếu không nằm trong write allowlist |
| Ghi balance | Bị từ chối nếu property nhạy cảm |
| Ghi property không tồn tại | Lỗi truy cập property |
| Ghi giá trị sai kiểu | Lỗi conversion hoặc write |
| Setter ném exception | Lỗi đánh giá được truyền lên |
| Root object null | Xử lý theo hợp đồng dữ liệu |
| Property lồng nhau null | Không ghi được nếu không có object đích |
| Expression assignment bị tắt | Cú pháp assignment bị từ chối |
| Expression.setValue trên property bị cấm | Accessor vẫn từ chối ghi |
| Gọi method thay đổi trạng thái | MethodResolver và quyền gọi phải được kiểm soát |

Nên kiểm thử custom PropertyAccessor trực tiếp và kiểm thử tích hợp qua SpEL. Kiểm thử trực tiếp xác nhận allowlist; kiểm thử tích hợp xác nhận parser, EvaluationContext, TypeConverter và accessor phối hợp đúng.

## 18. Ghi nhớ

PropertyAccessor quyết định một property có thể được đọc hoặc ghi hay không. Quyền đọc không đồng nghĩa quyền ghi. SimpleEvaluationContext cung cấp forReadOnlyDataBinding() và forReadWriteDataBinding() để chọn chế độ data binding; chế độ đọc ghi có thể cho phép nhiều public property, vì vậy cần custom PropertyAccessor nếu chỉ một số property được phép cập nhật.

Allowlist nên tách quyền đọc và quyền ghi. canRead/read kiểm soát property được đọc; canWrite/write kiểm soát property được thay đổi. Một setter public không tự cấp quyền ghi trong mọi context. Với đường dẫn lồng nhau, SpEL cần đọc được các object trung gian và accessor phải cho phép ghi property đích.

Assignment trong chuỗi expression và Expression.setValue() đều cần quyền ghi của accessor. Cờ withAssignmentDisabled() có thể tắt cú pháp assignment trong các phiên bản hỗ trợ, nhưng không thay thế allowlist cho các thao tác ghi do Java gọi. Conversion cũng không cấp quyền ghi và không thay thế validation.

Hãy cấp quyền tối thiểu, dùng DTO chuyên biệt hoặc accessor allowlist, kiểm soát method invocation song song với property write và kiểm thử cả thao tác được phép lẫn bị từ chối. Những thay đổi nghiệp vụ nhạy cảm như role, balance hoặc ownership nên đi qua service Java có authorization và validation rõ ràng.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [DataBindingPropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)