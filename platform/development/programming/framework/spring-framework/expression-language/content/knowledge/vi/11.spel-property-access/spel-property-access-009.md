# Kiểm soát property được truy cập qua PropertyAccessor trong Spring Expression Language (SpEL)

Trong SpEL, biểu thức có thể đọc hoặc ghi thuộc tính của đối tượng gốc. Cơ chế **PropertyAccessor** quyết định một tên property có thể được truy cập trên một đối tượng hay không, giá trị được lấy bằng cách nào và có được phép ghi hay không.

PropertyAccessor là điểm mở rộng quan trọng khi ứng dụng muốn biểu diễn dữ liệu theo cách riêng, cung cấp các property ảo hoặc giới hạn những trường mà biểu thức được phép nhìn thấy. Ví dụ, một đối tượng Customer có thể không có getter displayName nhưng SpEL vẫn có thể đọc được property displayName thông qua một accessor tùy chỉnh.

Bài này trình bày vai trò của PropertyAccessor, hợp đồng API, cách đăng ký vào EvaluationContext, thứ tự lựa chọn accessor, cách kiểm soát quyền đọc/ghi và các lưu ý bảo mật khi đánh giá biểu thức.

## 1. PropertyAccessor nằm ở đâu trong quy trình SpEL?

Khi SpEL gặp một biểu thức truy cập property như:

~~~text
name
customer.email
address.city
~~~

SpEL cần xác định đối tượng đích, tên property và cách đọc giá trị. Việc này được thực hiện thông qua danh sách PropertyAccessor gắn với EvaluationContext.

Quy trình tổng quát:

1. Parser phân tích chuỗi và tạo đối tượng Expression.
2. Khi đánh giá, SpEL xác định target object và tên property cần truy cập.
3. SpEL lần lượt hỏi các PropertyAccessor trong EvaluationContext xem accessor nào có thể đọc hoặc ghi property đó.
4. Accessor phù hợp thực hiện thao tác đọc hoặc ghi.
5. Giá trị được đưa trở lại quá trình đánh giá biểu thức.

Ví dụ, với biểu thức name và root object là một Customer, SpEL tìm accessor có thể xử lý property name trên đối tượng Customer. Accessor có thể dùng getter, đọc một trường, truy cập Map hoặc tự tính ra một giá trị ảo.

PropertyAccessor không phân tích cú pháp biểu thức. Nó tham gia ở giai đoạn đánh giá, khi SpEL cần truy cập một property cụ thể.

## 2. Giao diện PropertyAccessor

PropertyAccessor thuộc package org.springframework.expression. Giao diện này xác định đối tượng đích mà accessor hỗ trợ và các thao tác đọc/ghi property.

Các phương thức chính:

| Phương thức | Vai trò |
|---|---|
| getSpecificTargetClasses() | Khai báo các kiểu target mà accessor xử lý. Trả về null nếu accessor áp dụng cho mọi kiểu target. |
| canRead(context, target, name) | Kiểm tra accessor có thể đọc property name trên target hay không. |
| read(context, target, name) | Đọc giá trị property và trả về TypedValue. |
| canWrite(context, target, name) | Kiểm tra accessor có thể ghi property hay không. |
| write(context, target, name, newValue) | Ghi giá trị mới vào property. |

Chữ ký khái quát:

~~~java
public interface PropertyAccessor {

    Class<?>[] getSpecificTargetClasses();

    boolean canRead(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) throws AccessException;

    void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException;
}
~~~

Các kiểu liên quan:

- **EvaluationContext** cung cấp môi trường đánh giá hiện tại, bao gồm root object, biến, bộ chuyển đổi và danh sách accessor.
- **TypedValue** đóng gói giá trị đọc được cùng thông tin kiểu tùy chọn.
- **AccessException** biểu thị lỗi trong quá trình kiểm tra, đọc hoặc ghi property.

Nếu accessor không hỗ trợ một property, canRead hoặc canWrite trả về false. Nếu accessor đã nhận xử lý nhưng thao tác thực tế thất bại, nó có thể ném AccessException để báo lỗi cho SpEL.

## 3. getSpecificTargetClasses và phạm vi áp dụng

getSpecificTargetClasses() giúp accessor khai báo các kiểu đối tượng mà nó được thiết kế để xử lý.

Ví dụ, một accessor chỉ dành cho Customer:

~~~java
@Override
public Class<?>[] getSpecificTargetClasses() {
    return new Class<?>[] { Customer.class };
}
~~~

SpEL có thể dùng thông tin này để lựa chọn accessor phù hợp với target object. Nếu accessor xử lý nhiều kiểu, trả về mảng gồm các kiểu đó.

Nếu accessor thực sự có thể xử lý mọi kiểu target, phương thức có thể trả về null. Tuy nhiên, không nên khai báo phạm vi toàn cục nếu accessor chỉ hiểu một vài loại đối tượng. Phạm vi cụ thể giúp tránh việc accessor được hỏi trên những đối tượng không tương thích.

Trong canRead, read, canWrite và write vẫn cần kiểm tra target và tên property trước khi thao tác. Không nên chỉ dựa vào getSpecificTargetClasses() để bỏ qua kiểm tra đầu vào.

## 4. canRead và read: kiểm soát quyền đọc

Hai phương thức canRead và read có trách nhiệm khác nhau:

- canRead trả lời câu hỏi accessor có hỗ trợ đọc property này trên target hiện tại hay không.
- read thực hiện việc lấy giá trị và trả về một TypedValue.

Thông thường, canRead kiểm tra cả kiểu đối tượng và tên property. Ví dụ:

~~~java
@Override
public boolean canRead(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof Customer
            && "displayName".equals(name);
}
~~~

Nếu target là Customer và tên property là displayName, accessor nhận xử lý. Với tên khác hoặc kiểu target khác, nó trả về false để SpEL có thể thử accessor tiếp theo.

Phương thức read lấy giá trị:

~~~java
@Override
public TypedValue read(
        EvaluationContext context,
        Object target,
        String name) throws AccessException {

    if (!canRead(context, target, name)) {
        throw new AccessException("Unsupported property: " + name);
    }

    Customer customer = (Customer) target;
    String displayName =
            customer.getFirstName() + " " + customer.getLastName();

    return new TypedValue(displayName);
}
~~~

TypedValue có thể chứa null nếu property có giá trị null. Khi cần cung cấp thêm thông tin kiểu tường minh, có thể dùng các API TypeDescriptor tương ứng.

Một accessor nên nhất quán giữa canRead và read: nếu canRead trả về true cho một cặp target/property, read phải biết cách xử lý cặp đó hoặc báo lỗi cụ thể.

## 5. canWrite và write: kiểm soát quyền ghi

Đọc và ghi là hai quyền riêng biệt. Một property có thể được phép đọc nhưng không được phép thay đổi.

- canWrite kiểm tra property có thể nhận giá trị mới hay không.
- write thực hiện việc gán giá trị.

Ví dụ, displayName là giá trị được tính từ firstName và lastName nên chỉ cho đọc. Property alias có thể được phép đọc và cập nhật.

~~~java
@Override
public boolean canWrite(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof Customer
            && "alias".equals(name);
}
~~~

Triển khai write:

~~~java
@Override
public void write(
        EvaluationContext context,
        Object target,
        String name,
        Object newValue) throws AccessException {

    if (!canWrite(context, target, name)) {
        throw new AccessException("Property is read-only: " + name);
    }

    if (newValue != null && !(newValue instanceof String)) {
        throw new AccessException("alias must be a String");
    }

    Customer customer = (Customer) target;
    customer.setAlias((String) newValue);
}
~~~

Trong ví dụ, alias chỉ nhận String hoặc null. Nếu ứng dụng cần chuyển đổi kiểu, accessor có thể sử dụng TypeConverter từ EvaluationContext và kiểm tra kiểu đích trước khi ghi.

Không nên cho phép ghi chỉ vì property có thể đọc. Một allowlist đọc và một allowlist ghi có thể khác nhau tùy yêu cầu nghiệp vụ.

## 6. Ví dụ hoàn chỉnh: tạo property ảo và property có thể ghi

Giả sử Customer lưu firstName, lastName và alias. Ứng dụng muốn SpEL truy cập displayName như một property ảo, đồng thời cho phép cập nhật alias.

Lớp miền:

~~~java
public class Customer {

    private final String firstName;
    private final String lastName;
    private String alias;

    public Customer(String firstName, String lastName, String alias) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.alias = alias;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getAliasValue() {
        return alias;
    }

    public void setAlias(String alias) {
        this.alias = alias;
    }
}
~~~

Accessor tùy chỉnh:

~~~java
import org.springframework.expression.AccessException;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.PropertyAccessor;
import org.springframework.expression.TypedValue;

public class CustomerPropertyAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Customer.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof Customer
                && ("displayName".equals(name) || "alias".equals(name));
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {

        if (!canRead(context, target, name)) {
            throw new AccessException("Unsupported property: " + name);
        }

        Customer customer = (Customer) target;

        if ("displayName".equals(name)) {
            return new TypedValue(
                    customer.getFirstName() + " " + customer.getLastName()
            );
        }

        return new TypedValue(customer.getAliasValue());
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof Customer && "alias".equals(name);
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!canWrite(context, target, name)) {
            throw new AccessException("Property is read-only: " + name);
        }

        if (newValue != null && !(newValue instanceof String)) {
            throw new AccessException("alias must be a String");
        }

        ((Customer) target).setAlias((String) newValue);
    }
}
~~~

Đăng ký accessor và đánh giá:

~~~java
import java.util.Collections;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

Customer customer = new Customer("An", "Nguyen", "an01");

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

// Danh sách này chỉ cho phép các property do accessor tùy chỉnh cung cấp.
context.setPropertyAccessors(
        Collections.singletonList(new CustomerPropertyAccessor())
);

ExpressionParser parser = new SpelExpressionParser();

Expression displayName = parser.parseExpression("displayName");
String display = displayName.getValue(context, String.class);

// display = "An Nguyen"

Expression alias = parser.parseExpression("alias");
alias.setValue(context, "premium");

String currentAlias = alias.getValue(context, String.class);

// currentAlias = "premium"
~~~

Trong ví dụ này:

- displayName không cần getter cùng tên trong Customer; accessor tự tính giá trị từ firstName và lastName.
- alias được đọc thông qua getAliasValue và được cập nhật qua setAlias.
- canWrite chỉ cho phép ghi alias.
- displayName là property chỉ đọc.
- setPropertyAccessors thay danh sách accessor của context bằng danh sách được chỉ định. Vì vậy, các property khác không được accessor tùy chỉnh hỗ trợ sẽ không có reflective accessor mặc định để xử lý.

Đoạn mã minh họa cách kiểm soát tập property mà biểu thức nhìn thấy. Nếu ứng dụng muốn giữ khả năng truy cập property Java thông thường, cần cấu hình thêm accessor phù hợp trong danh sách.

## 7. Đăng ký PropertyAccessor vào EvaluationContext

PropertyAccessor không tự động áp dụng cho mọi biểu thức. Nó phải được đăng ký vào EvaluationContext dùng khi đánh giá.

### 7.1. StandardEvaluationContext

StandardEvaluationContext hỗ trợ đăng ký accessor tùy chỉnh:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.addPropertyAccessor(new CustomerPropertyAccessor());
~~~

addPropertyAccessor thêm accessor vào danh sách hiện có. Đây là cách mở rộng khi accessor xử lý một property mới mà các accessor mặc định không biết.

Nếu cần kiểm soát thứ tự hoặc thay thế toàn bộ danh sách, có thể dùng setPropertyAccessors:

~~~java
context.setPropertyAccessors(Arrays.asList(
        new CustomerPropertyAccessor(),
        new ReflectivePropertyAccessor()
));
~~~

Danh sách được cung cấp xác định những accessor nào được dùng và thứ tự thử chúng. Khi custom accessor cần ưu tiên xử lý một property vốn cũng được reflective accessor hỗ trợ, hãy đặt custom accessor trước accessor phản chiếu.

Nếu dùng setPropertyAccessors, hãy nhớ rằng bạn đang thay danh sách hiện tại. Bỏ sót accessor mặc định có thể làm thay đổi những property mà biểu thức cũ truy cập được.

### 7.2. SimpleEvaluationContext

SimpleEvaluationContext phù hợp khi muốn giới hạn tập tính năng của SpEL, chẳng hạn trong data binding hoặc biểu thức do người dùng cấu hình.

Context này cho phép lựa chọn PropertyAccessor cụ thể qua builder, ví dụ:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(
                new CustomerPropertyAccessor()
        ).build();
~~~

SimpleEvaluationContext không cung cấp toàn bộ khả năng của StandardEvaluationContext. Nó được thiết kế để loại bỏ hoặc giới hạn một số khả năng nâng cao như tham chiếu kiểu, tạo đối tượng và tham chiếu bean; khả năng gọi phương thức cũng cần được cấu hình theo nhu cầu.

Nếu chỉ cần đọc dữ liệu, có thể chọn cấu hình read-only. Nếu cần ghi property, hãy chọn chế độ cho phép ghi và chỉ cung cấp accessor có thể kiểm soát thao tác đó.

## 8. Thứ tự lựa chọn accessor và xử lý xung đột

Một EvaluationContext có thể chứa nhiều PropertyAccessor. SpEL cần tìm accessor hỗ trợ target object và property đang được truy cập.

Ví dụ, context có:

1. CustomerPropertyAccessor
2. ReflectivePropertyAccessor

Nếu biểu thức đọc displayName trên Customer, custom accessor có thể nhận xử lý property ảo đó. Nếu custom accessor trả về false từ canRead, SpEL có thể tiếp tục thử accessor sau.

Nếu cả hai accessor đều hỗ trợ cùng một property, thứ tự có ý nghĩa. Accessor được thử trước có thể quyết định cách property được đọc hoặc ghi. Vì vậy:

- Đặt custom accessor trước khi cần ưu tiên cách diễn giải tùy chỉnh.
- Giữ reflective accessor sau nó nếu vẫn muốn cho phép truy cập JavaBean thông thường.
- Bỏ reflective accessor khi muốn chỉ cho phép danh sách property do ứng dụng định nghĩa.
- Tránh để hai accessor cùng tuyên bố hỗ trợ một property nếu chúng có cách đọc/ghi khác nhau mà không có quy tắc ưu tiên rõ ràng.

canRead và canWrite nên chỉ trả về true cho những property mà accessor thực sự kiểm soát. Không nên trả true quá rộng rồi để read hoặc write tự xử lý nhiều trường hợp không liên quan.

## 9. ReflectivePropertyAccessor và accessor tùy chỉnh

Spring cung cấp ReflectivePropertyAccessor để truy cập property Java thông qua reflection. Đây là accessor thường dùng trong StandardEvaluationContext và hỗ trợ các property JavaBean phù hợp thông qua getter, setter hoặc field theo quy tắc của nó.

Accessor phản chiếu hữu ích khi biểu thức cần truy cập các property Java thông thường:

~~~text
name
address.city
account.balance
~~~

Accessor tùy chỉnh phù hợp khi:

- Property không tồn tại trực tiếp trong lớp Java nhưng có thể được tính hoặc lấy từ nguồn khác.
- Tên property trong biểu thức cần ánh xạ sang một cấu trúc dữ liệu riêng.
- Chỉ một tập property được phép xuất hiện trong biểu thức.
- Quyền đọc và quyền ghi khác nhau.
- Ứng dụng cần kiểm soát dữ liệu trả về, chuẩn hóa giá trị hoặc áp dụng quy tắc chuyển đổi riêng.

Có thể kết hợp accessor tùy chỉnh với ReflectivePropertyAccessor. Điều này giúp ứng dụng mở rộng cách truy cập cho một số property trong khi giữ các property JavaBean thông thường.

## 10. Dùng PropertyAccessor để tạo allowlist property

Một mục đích quan trọng của PropertyAccessor là giới hạn những property mà biểu thức có thể truy cập.

Ví dụ, một quy tắc cấu hình chỉ được phép đọc:

~~~text
customerName
accountStatus
creditLimit
~~~

Ứng dụng có thể tạo accessor chỉ hỗ trợ đúng ba tên này. Những property khác trả về false từ canRead và không được truy cập nếu không có accessor khác xử lý chúng.

Để thực sự giới hạn tập property:

1. Chọn target type cụ thể trong getSpecificTargetClasses.
2. Kiểm tra chính xác tên property trong canRead và canWrite.
3. Chỉ triển khai read hoặc write cho các property được cho phép.
4. Cấu hình danh sách accessor sao cho không có accessor rộng hơn vô tình mở lại property bị chặn.
5. Kiểm tra cả quyền gọi phương thức và những tính năng SpEL khác được bật trong context.

Nếu chỉ thêm một allowlist accessor vào StandardEvaluationContext nhưng vẫn giữ ReflectivePropertyAccessor, những property mà accessor allowlist từ chối có thể vẫn được accessor phản chiếu truy cập. Vì vậy, muốn giới hạn thật sự thì phải kiểm soát toàn bộ danh sách accessor được dùng.

## 11. Kiểm soát lỗi và chuyển đổi giá trị

Khi viết accessor tùy chỉnh, cần xử lý các trường hợp:

- Target null hoặc không đúng kiểu.
- Tên property không được hỗ trợ.
- Property không có giá trị.
- Giá trị mới có kiểu không tương thích.
- Lỗi khi truy cập nguồn dữ liệu bên dưới.
- Property chỉ đọc nhưng biểu thức yêu cầu ghi.

AccessException dùng để báo lỗi ở tầng truy cập property. SpEL có thể chuyển lỗi này thành lỗi đánh giá biểu thức. Vì vậy, mã ứng dụng nên xử lý lỗi ở ranh giới đánh giá phù hợp.

Nếu accessor cần chuyển đổi kiểu, có thể dùng TypeConverter từ EvaluationContext. Không nên tự ép kiểu tùy tiện khi dữ liệu có thể đến từ biểu thức hoặc nguồn cấu hình bên ngoài.

Ví dụ, nếu property alias chỉ nhận String, accessor nên xác định rõ hành vi với null và kiểu khác String. Quy tắc chuyển đổi phải phù hợp với hợp đồng dữ liệu của ứng dụng.

## 12. Lưu ý bảo mật khi cho phép truy cập property

PropertyAccessor ảnh hưởng trực tiếp đến dữ liệu mà biểu thức có thể đọc và thay đổi. Nếu biểu thức được nhập bởi người dùng hoặc lấy từ nguồn không đáng tin cậy, việc đăng ký accessor quá rộng có thể làm lộ dữ liệu hoặc cho phép sửa đổi trạng thái ngoài dự kiến.

Một số nguyên tắc:

1. **Giới hạn target type:** chỉ hỗ trợ những lớp cần thiết.
2. **Dùng allowlist tên property:** chỉ cho phép những property mà nghiệp vụ cần.
3. **Tách quyền đọc và ghi:** chỉ cho phép write với các property được phép thay đổi.
4. **Cẩn thận với reflection:** ReflectivePropertyAccessor có thể mở rộng bề mặt truy cập sang property Java thông thường.
5. **Kiểm soát method access:** PropertyAccessor không kiểm soát toàn bộ lời gọi phương thức. Nếu method invocation vẫn được bật, biểu thức có thể tiếp cận hành vi khác ngoài tập property.
6. **Chọn EvaluationContext phù hợp:** cân nhắc SimpleEvaluationContext khi không cần đầy đủ tính năng của StandardEvaluationContext.
7. **Không coi accessor là sandbox hoàn chỉnh:** cần giới hạn cả root object, biến, hàm, method resolver, type locator, bean resolver và các tính năng khác được cung cấp cho biểu thức.

PropertyAccessor là một lớp kiểm soát quan trọng, nhưng chính sách bảo mật phải bao quát toàn bộ khả năng của EvaluationContext.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Property không được tìm thấy | Không có accessor nào hỗ trợ target và tên property. | Kiểm tra canRead, kiểu target và danh sách accessor. |
| Accessor không được gọi | Accessor khác đứng trước đã xử lý property. | Kiểm tra thứ tự danh sách và dùng setPropertyAccessors khi cần. |
| canRead trả về true nhưng read thất bại | Kiểm tra trong canRead không phản ánh đầy đủ điều kiện đọc. | Đồng bộ điều kiện giữa canRead và read. |
| Property đọc được nhưng không ghi được | canWrite trả về false hoặc write không được triển khai. | Kiểm tra quyền ghi riêng biệt. |
| Ghi sai kiểu | Accessor không xác thực hoặc chuyển đổi newValue. | Kiểm tra kiểu hoặc dùng TypeConverter. |
| Property bị chặn nhưng vẫn truy cập được | Một accessor khác, chẳng hạn accessor phản chiếu, vẫn cho phép truy cập. | Kiểm soát toàn bộ danh sách accessor. |
| Dùng accessor cho mọi target | getSpecificTargetClasses trả về null hoặc phạm vi quá rộng. | Khai báo kiểu target cụ thể khi có thể. |
| Nghĩ rằng PropertyAccessor chặn được mọi hành vi | Lời gọi phương thức và tính năng SpEL khác nằm ngoài phạm vi accessor. | Giới hạn EvaluationContext và các resolver liên quan. |

## 14. Ghi nhớ

- PropertyAccessor quyết định cách SpEL đọc hoặc ghi property trên target object.
- canRead và canWrite kiểm tra khả năng; read và write thực hiện thao tác.
- read trả về TypedValue; lỗi truy cập có thể được báo bằng AccessException.
- getSpecificTargetClasses khai báo các kiểu target mà accessor hỗ trợ.
- StandardEvaluationContext cho phép thêm hoặc thay thế danh sách accessor.
- Thứ tự accessor quan trọng khi nhiều accessor hỗ trợ cùng một property.
- ReflectivePropertyAccessor xử lý property Java thông thường; accessor tùy chỉnh mở rộng hoặc giới hạn cách truy cập.
- Muốn dùng allowlist thật sự, phải kiểm soát toàn bộ danh sách accessor, không để accessor rộng hơn mở lại property bị chặn.
- PropertyAccessor chỉ kiểm soát truy cập property; cần giới hạn thêm các tính năng khác của EvaluationContext khi xử lý biểu thức không đáng tin cậy.
