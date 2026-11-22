# AccessException từ accessor hoặc resolver

Trong Spring Expression Language (SpEL), các extension point như **PropertyAccessor**, **MethodResolver**, **ConstructorResolver** và **BeanResolver** chịu trách nhiệm truy cập property, tìm method, tìm constructor hoặc phân giải bean. Một số thao tác của các interface này khai báo có thể ném **AccessException** thuộc package org.springframework.expression.

AccessException biểu thị rằng accessor hoặc resolver gặp vấn đề khi thực hiện trách nhiệm truy cập hay phân giải của nó. SpEL thường chuyển lỗi này thành một **SpelEvaluationException** phù hợp với thao tác đang được đánh giá và giữ nguyên exception gốc làm cause.

Cần phân biệt hai tình huống: extension point không hỗ trợ target hoặc member đang xét, và extension point thực sự gặp lỗi khi truy cập. Với trường hợp không hỗ trợ, accessor/resolver nên trả về false hoặc null theo hợp đồng interface. Chỉ ném AccessException khi có sự cố thực sự. Nếu dùng exception để báo “không phù hợp”, việc phân giải có thể dừng sớm và che mất accessor hoặc resolver khác có khả năng xử lý.

## 1. AccessException là gì?

### 1.1. Vị trí trong Spring Expression

AccessException nằm trong package:

~~~java
org.springframework.expression.AccessException
~~~

Đây là exception được dùng bởi các interface mở rộng cơ chế truy cập của SpEL. Nó cho phép accessor hoặc resolver báo rằng thao tác đọc, ghi, tìm method, tìm constructor hoặc lấy bean gặp lỗi.

AccessException có thể chứa thông báo và nguyên nhân gốc:

~~~java
throw new AccessException(
        "Could not read customer profile",
        cause
);
~~~

Giữ cause giúp người gọi xác định lỗi ban đầu, ví dụ lỗi reflection, lỗi truy cập dữ liệu hoặc lỗi từ một adapter tùy chỉnh.

### 1.2. AccessException không phải lỗi cú pháp

Một expression có thể parse thành công nhưng vẫn thất bại khi evaluate vì accessor hoặc resolver không thể hoàn thành thao tác.

Ví dụ:

~~~java
customer.email
~~~

Parser có thể tạo Expression từ cú pháp trên. Khi evaluate, SpEL cần tìm PropertyAccessor đọc được property email. Nếu accessor phù hợp gặp lỗi truy cập và ném AccessException, evaluation sẽ thất bại.

Vì vậy, cần tách các giai đoạn:

1. Parse source thành Expression.
2. Phân giải target object, property, method, constructor hoặc bean.
3. Thực thi thao tác truy cập.
4. Trả kết quả hoặc phát sinh lỗi đánh giá.

AccessException thuộc các bước phân giải hoặc thực thi truy cập, không phải lỗi parser nhận diện cú pháp.

### 1.3. Phân biệt với EvaluationException

**EvaluationException** là nhóm exception rộng hơn dùng để biểu thị lỗi trong quá trình đánh giá expression. **SpelEvaluationException** là implementation cụ thể của lỗi đánh giá trong SpEL.

AccessException được khai báo tại các extension point và thường được SpEL chuyển thành SpelEvaluationException khi lỗi đi ra khỏi quá trình đánh giá.

Có thể hình dung:

~~~text
Custom PropertyAccessor / MethodResolver
                 |
                 | throws AccessException
                 v
       SpEL evaluation operation
                 |
                 | wraps with evaluation context
                 v
        SpelEvaluationException
                 |
                 | preserves original cause
                 v
             AccessException
~~~

Khi xử lý lỗi, hãy xem cả exception ngoài và cause. Chỉ nhìn message ngoài có thể không đủ để xác định accessor hoặc resolver nào đã gặp vấn đề.

### 1.4. Không nhầm với Spring Security AccessDeniedException

AccessException của package org.springframework.expression là exception thuộc cơ chế truy cập của SpEL. Nó khác với các exception phân quyền trong Spring Security, chẳng hạn **AccessDeniedException**.

Hai loại exception có tên gần giống nhưng thuộc hai API và mục đích khác nhau:

- Expression AccessException: extension point của SpEL không thể hoàn thành thao tác truy cập/phân giải.
- Security AccessDeniedException: một hành động bị từ chối theo chính sách bảo mật.

Không dùng AccessException của SpEL như cơ chế authorization tổng quát. Phân quyền nghiệp vụ nên được kiểm tra tại service hoặc security layer.

## 2. Những interface có thể ném AccessException

### 2.1. PropertyAccessor

PropertyAccessor đọc và ghi property trên target object. Các phương thức canRead, read, canWrite và write có thể khai báo AccessException.

~~~java
public interface PropertyAccessor {

    Class<?>[] getSpecificTargetClasses();

    boolean canRead(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    TypedValue read(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    boolean canWrite(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue
    ) throws AccessException;
}
~~~

Các phương thức có ý nghĩa khác nhau:

- **canRead** cho biết accessor có thể đọc property được yêu cầu hay không.
- **read** thực hiện đọc và trả về TypedValue.
- **canWrite** cho biết accessor có thể ghi property hay không.
- **write** thực hiện cập nhật giá trị.

Nếu target không thuộc loại accessor hỗ trợ hoặc property không nằm trong phạm vi accessor, hãy trả về false ở canRead/canWrite. Nếu accessor đã xác định có thể xử lý nhưng thao tác thực tế thất bại, hãy ném AccessException.

### 2.2. MethodResolver

MethodResolver tìm một method phù hợp với target, tên method và kiểu các argument:

~~~java
public interface MethodResolver {

    MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes
    ) throws AccessException;
}
~~~

Nếu resolver không xử lý target hoặc không tìm thấy method phù hợp, nó nên trả về null. Nếu resolver gặp sự cố thực sự trong quá trình tìm hoặc kiểm tra method, nó có thể ném AccessException.

MethodResolver trả về MethodExecutor khi đã tìm được cách thực thi. MethodExecutor cũng có thể ném AccessException khi lời gọi không thể hoàn thành:

~~~java
public interface MethodExecutor {

    TypedValue execute(
            EvaluationContext context,
            Object target,
            Object... arguments
    ) throws AccessException;
}
~~~

Do đó, lỗi có thể xảy ra ở cả giai đoạn tìm method và giai đoạn thực thi method.

### 2.3. ConstructorResolver và ConstructorExecutor

ConstructorResolver tìm constructor phù hợp cho biểu thức new:

~~~java
public interface ConstructorResolver {

    ConstructorExecutor resolve(
            EvaluationContext context,
            String typeName,
            List<TypeDescriptor> argumentTypes
    ) throws AccessException;
}
~~~

Resolver trả về ConstructorExecutor khi tìm được cách tạo instance. Nếu không hỗ trợ kiểu hoặc không có constructor phù hợp, resolver nên trả về null để báo không có candidate.

Nếu có lỗi truy cập hoặc reflection trong lúc phân giải/thực thi, AccessException có thể được ném ra. ConstructorExecutor chịu trách nhiệm thực hiện việc tạo instance và cũng có thể báo lỗi truy cập.

### 2.4. BeanResolver

BeanResolver phân giải bean theo tên:

~~~java
public interface BeanResolver {

    Object resolve(
            EvaluationContext context,
            String beanName
    ) throws AccessException;
}
~~~

Nếu context hỗ trợ bean reference, biểu thức:

~~~java
@pricingService
~~~

yêu cầu BeanResolver tìm bean pricingService.

Nếu bean không tồn tại hoặc resolver không thể lấy bean, thao tác có thể thất bại. Với resolver tùy chỉnh, hãy phân biệt tên bean không được hỗ trợ theo chính sách với lỗi thực sự từ BeanFactory hoặc cơ chế tra cứu.

### 2.5. Các thành phần khác không dùng cùng hợp đồng

Không phải mọi lỗi trong SpEL đều được biểu diễn bằng AccessException. Ví dụ, TypeConverter có thể phát sinh lỗi chuyển đổi; TypeLocator có thể báo lỗi khi không phân giải được kiểu; parser có thể báo lỗi cú pháp.

Khi điều tra, hãy xác định extension point nào đang chạy thay vì bắt một exception tổng quát rồi giả định mọi vấn đề đều là AccessException.

## 3. Khi nào nên trả về false hoặc null?

### 3.1. PropertyAccessor không hỗ trợ target

Giả sử một accessor chỉ đọc property từ CustomerView. Khi target là Order, accessor không hỗ trợ object đó:

~~~java
@Override
public boolean canRead(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof CustomerView
            && "email".equals(name);
}
~~~

Nếu target là Order hoặc property không phải email, kết quả false là cách báo rằng accessor này không phù hợp. SpEL có thể tiếp tục thử accessor khác.

Không ném AccessException chỉ vì target không phải CustomerView. Đó là trường hợp bình thường trong quá trình nhiều accessor cùng tham gia phân giải.

### 3.2. MethodResolver không tìm thấy method

Một resolver chỉ xử lý method calculateRisk trên CustomerView. Nếu expression yêu cầu formatName, resolver nên trả về null:

~~~java
if (!(targetObject instanceof CustomerView)
        || !"calculateRisk".equals(name)) {
    return null;
}
~~~

Giá trị null có nghĩa resolver này không cung cấp MethodExecutor cho lời gọi đó. SpEL có thể tiếp tục thử resolver khác.

Nếu resolver ném AccessException cho mọi method ngoài calculateRisk, resolver có thể ngăn các resolver tiếp theo xử lý method mà chúng hỗ trợ.

### 3.3. BeanResolver và tên không được cho phép

Với resolver có allowlist, tên bean không nằm trong danh sách không phải là lỗi hệ thống khi tra cứu. Đây là quyết định chính sách.

Resolver có thể từ chối bằng exception phù hợp để expression không được tiếp tục. Tuy nhiên, cần nhận biết đây là từ chối quyền, không phải trường hợp resolver đơn giản không hỗ trợ một kiểu target.

Không để lỗi quyền truy cập bị chuyển thành “không có bean” một cách âm thầm nếu ứng dụng cần ghi nhận hành vi bị từ chối.

### 3.4. Khi nào AccessException là phù hợp?

Ném AccessException khi accessor hoặc resolver đã được chọn để xử lý nhưng không thể hoàn thành trách nhiệm do một vấn đề thực tế, chẳng hạn:

- Backend dữ liệu mà accessor sử dụng không truy cập được.
- Reflection gặp lỗi quyền truy cập.
- Một adapter cần metadata nhưng metadata bị hỏng hoặc không thể đọc.
- BeanFactory hoặc hệ thống tra cứu bean gặp lỗi trong lúc resolve.
- MethodExecutor không thể thực thi thao tác theo hợp đồng.
- ConstructorExecutor không thể gọi constructor do lỗi truy cập.

Không dùng exception để thay cho giá trị false/null mà interface đã định nghĩa cho trường hợp không phù hợp.

## 4. Cách SpEL xử lý AccessException

### 4.1. Trong property resolution

Khi expression truy cập property, SpEL kiểm tra các PropertyAccessor có thể xử lý target. Accessor có thể trả false nếu không đọc được property đó.

Nếu accessor ném AccessException trong lúc kiểm tra hoặc đọc property, SpEL có thể chuyển lỗi thành SpelEvaluationException gắn với vị trí và tên property đang được đánh giá.

Điều này giúp người gọi biết expression thất bại ở thao tác property nào. Exception gốc vẫn quan trọng để tìm nguyên nhân trong accessor.

### 4.2. Trong method resolution

Khi expression gọi method, SpEL lần lượt hỏi các MethodResolver để tìm MethodExecutor phù hợp.

Resolver trả về null khi không xử lý lời gọi. Nếu resolver ném AccessException, SpEL xem đó là vấn đề trong quá trình phân giải và thường chuyển thành SpelEvaluationException cho method đang được gọi.

Vì vậy, một resolver tùy chỉnh không nên ném AccessException chỉ để nói “tôi không xử lý method này”. Hãy trả về null để resolver khác có cơ hội xử lý.

### 4.3. Trong constructor resolution

Constructor expression cũng cần resolver tìm constructor và executor thực thi nó. Nếu resolver không có candidate, trả về null. Nếu quá trình truy cập constructor gặp lỗi, AccessException có thể được chuyển thành lỗi đánh giá.

Ví dụ:

~~~java
new com.example.domain.Customer('C-100')
~~~

Nếu constructor resolver tùy chỉnh gặp lỗi reflection khi kiểm tra constructor Customer, hãy giữ nguyên cause trong AccessException để việc điều tra không mất thông tin.

### 4.4. Trong bean resolution

Khi expression tham chiếu bean, BeanResolver thực hiện tra cứu. AccessException từ resolver thường được chuyển thành SpelEvaluationException mô tả vấn đề phân giải bean.

Ví dụ:

~~~java
@pricingService.calculate(order)
~~~

Nếu resolver không thể lấy pricingService do lỗi thật sự từ BeanFactory, hãy giữ nguyên nguyên nhân. Nếu tên bean không được phép theo allowlist, báo rõ loại lỗi chính sách trong log nội bộ nhưng không để lộ chi tiết không cần thiết cho người dùng cuối.

### 4.5. Lỗi trong executor khác lỗi không tìm thấy candidate

Cần phân biệt:

- Resolver không tìm thấy candidate và trả null: SpEL tiếp tục tìm resolver khác; nếu không có resolver nào phù hợp, expression báo không tìm được method/constructor.
- Resolver ném AccessException: quá trình phân giải gặp lỗi.
- Executor ném AccessException: candidate đã được chọn nhưng thao tác thực thi thất bại.

Ba trường hợp này có ý nghĩa khác nhau và nên được xử lý riêng khi viết extension point tùy chỉnh.

## 5. Ví dụ custom PropertyAccessor

### 5.1. Mô hình dữ liệu

Giả sử ứng dụng có một kiểu view lưu các thuộc tính động:

~~~java
public class CustomerView {

    private final Map<String, Object> attributes;

    public CustomerView(Map<String, Object> attributes) {
        this.attributes = new HashMap<>(attributes);
    }

    public boolean hasAttribute(String name) {
        return attributes.containsKey(name);
    }

    public Object getAttribute(String name) {
        return attributes.get(name);
    }

    public void setAttribute(String name, Object value) {
        attributes.put(name, value);
    }
}
~~~

Ta muốn SpEL đọc các attribute như property:

~~~java
email
region
customerTier
~~~

### 5.2. Triển khai accessor

~~~java
public class CustomerViewAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { CustomerView.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof CustomerView view
                && view.hasAttribute(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {

        if (!(target instanceof CustomerView view)) {
            throw new AccessException(
                    "Unsupported target for CustomerViewAccessor"
            );
        }

        if (!view.hasAttribute(name)) {
            throw new AccessException(
                    "Customer attribute is no longer available: " + name
            );
        }

        return new TypedValue(view.getAttribute(name));
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof CustomerView;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!(target instanceof CustomerView view)) {
            throw new AccessException(
                    "Unsupported target for CustomerViewAccessor"
            );
        }

        view.setAttribute(name, newValue);
    }
}
~~~

Trong ví dụ:

- canRead trả false khi target không phải CustomerView hoặc attribute không tồn tại.
- read ném AccessException nếu trạng thái target thay đổi sau khi canRead đã trả true.
- canWrite chỉ cho phép ghi trên CustomerView.
- write ném AccessException nếu target không đúng loại.

Trong hệ thống thực tế, cần xác định rõ policy cho attribute được phép ghi. Không nên cho phép ghi mọi key nếu expression có thể đến từ người dùng.

### 5.3. Đăng ký accessor

~~~java
CustomerView view = new CustomerView(
        Map.of(
                "email", "user@example.com",
                "region", "APAC"
        )
);

StandardEvaluationContext context =
        new StandardEvaluationContext(view);

context.addPropertyAccessor(new CustomerViewAccessor());

ExpressionParser parser = new SpelExpressionParser();

String email = parser
        .parseExpression("email")
        .getValue(context, String.class);
~~~

Nếu accessor được đăng ký trên context, SpEL có thể dùng nó để đọc property mà accessor hỗ trợ.

Nếu muốn ghi:

~~~java
parser.parseExpression("region")
        .setValue(context, "EU");
~~~

Thao tác chỉ nên được cho phép khi ứng dụng thực sự cần cập nhật attribute và đã kiểm tra quyền ghi.

### 5.4. Lỗi từ backend trong accessor

Nếu accessor đọc dữ liệu từ backend thay vì Map trong bộ nhớ, hãy bọc lỗi có ý nghĩa:

~~~java
try {
    Object value = profileStore.read(customerId, name);
    return new TypedValue(value);
} catch (ProfileStoreException ex) {
    throw new AccessException(
            "Could not read customer profile attribute",
            ex
    );
}
~~~

Không trả null để che giấu backend đang lỗi. Null có thể là giá trị dữ liệu hợp lệ; nó không nên đại diện cho lỗi truy cập.

## 6. Ví dụ custom MethodResolver

### 6.1. Resolver chỉ xử lý một method

Giả sử CustomerView có method thuần canArchive():

~~~java
public class CustomerView {

    public boolean canArchive() {
        // Quy tắc chỉ đọc, xác định
        return true;
    }
}
~~~

Một resolver có thể chỉ xử lý lời gọi canArchive không có argument:

~~~java
public class CustomerMethodResolver implements MethodResolver {

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!(targetObject instanceof CustomerView)) {
            return null;
        }

        if (!"canArchive".equals(name)
                || !argumentTypes.isEmpty()) {
            return null;
        }

        return (ctx, target, arguments) -> {
            if (!(target instanceof CustomerView view)) {
                throw new AccessException(
                        "Unexpected target for canArchive"
                );
            }

            return new TypedValue(view.canArchive());
        };
    }
}
~~~

Resolver trả null nếu target hoặc chữ ký không thuộc phạm vi hỗ trợ. Nó chỉ trả MethodExecutor khi đã xác định lời gọi phù hợp.

### 6.2. Đăng ký resolver

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customerView);

context.addMethodResolver(new CustomerMethodResolver());

Boolean canArchive = parser
        .parseExpression("canArchive()")
        .getValue(context, Boolean.class);
~~~

Khi method được gọi, executor thực hiện hành vi và trả TypedValue.

### 6.3. Xử lý lỗi trong resolver

Nếu resolver phải đọc metadata hoặc tra cứu cấu hình để xác định method, hãy phân biệt:

- Không có method được resolver hỗ trợ: trả null.
- Metadata không tồn tại do target không đúng loại: thường trả null.
- Metadata cần thiết bị hỏng hoặc nguồn dữ liệu không truy cập được: ném AccessException có cause.
- Method đã được chọn nhưng logic thực thi thất bại: executor báo lỗi phù hợp.

Không ném AccessException cho mọi method khác tên. Làm như vậy có thể chặn resolver mặc định hoặc resolver khác.

## 7. Cách giữ cause và tạo thông báo hữu ích

### 7.1. Dùng constructor có cause

Khi bắt exception từ thư viện hoặc backend, luôn giữ cause:

~~~java
try {
    return repository.readProperty(targetId, propertyName);
} catch (RepositoryException ex) {
    throw new AccessException(
            "Failed to read expression property",
            ex
    );
}
~~~

Không chỉ nối ex.getMessage() vào chuỗi rồi bỏ cause. Giữ cause giúp log và debugger truy vết được loại lỗi gốc cùng stack trace.

### 7.2. Thông báo nên có ngữ cảnh

Một thông báo tốt nên giúp xác định thao tác thất bại:

- Đang đọc hay ghi property nào.
- Đang phân giải method nào.
- Đang tạo kiểu nào.
- Đang tìm bean tên gì.
- Target thuộc nhóm dữ liệu nào nếu thông tin đó an toàn để log.

Không đưa dữ liệu nhạy cảm, token, nội dung đầy đủ của request hoặc thông tin cá nhân vào exception message.

### 7.3. Không để exception che mất loại lỗi

Nếu mọi lỗi đều bị bọc bằng một AccessException chung không có cause hoặc ngữ cảnh, người vận hành khó phân biệt lỗi cấu hình, lỗi dữ liệu và lỗi backend.

Hãy dùng message cụ thể ở lớp extension point và giữ cause gốc. Ở tầng API, chuyển lỗi sang thông báo phù hợp mà không tiết lộ cấu trúc nội bộ.

## 8. Xử lý SpelEvaluationException ở tầng ứng dụng

### 8.1. Bắt exception ở ranh giới evaluate

Có thể bắt EvaluationException quanh lời gọi evaluate:

~~~java
try {
    Object result = expression.getValue(context);
    return result;
} catch (SpelEvaluationException ex) {
    // Ghi log theo mã lỗi và cause
    throw new IllegalStateException(
            "Could not evaluate configured expression",
            ex
    );
}
~~~

Nếu API cần trả lỗi validation hoặc lỗi cấu hình, hãy ánh xạ sang exception của tầng ứng dụng. Không để chi tiết reflection hoặc backend bị lộ trực tiếp cho client.

### 8.2. Kiểm tra cause chain

Để xác định lỗi có bắt nguồn từ AccessException hay không:

~~~java
Throwable cause = ex;

while (cause != null) {
    if (cause instanceof AccessException) {
        // Extension point của SpEL đã báo lỗi truy cập
        break;
    }

    cause = cause.getCause();
}
~~~

Cause chain có thể chứa thêm exception trung gian. Không nên giả định AccessException luôn là cause trực tiếp nếu các lớp tích hợp khác đã bọc lỗi.

### 8.3. Phân loại theo giai đoạn

Nên ghi nhận ít nhất các nhóm:

| Nhóm lỗi | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Parse failure | Source không đúng cú pháp | Kiểm tra expression source |
| Property access failure | Accessor không đọc/ghi được property | Kiểm tra target, property và accessor |
| Method resolution failure | Không tìm được executor hoặc resolver gặp lỗi | Kiểm tra tên, argument và resolver |
| Constructor resolution failure | Không tìm được hoặc không gọi được constructor | Kiểm tra type, chữ ký và constructor resolver |
| Bean resolution failure | BeanResolver không lấy được bean | Kiểm tra tên bean, allowlist và BeanFactory |
| Conversion failure | Argument hoặc kết quả không chuyển đổi được | Kiểm tra TypeConverter/ConversionService |
| Business exception | Code bên trong getter/method/constructor thất bại | Điều tra logic nghiệp vụ và cause |

Không chuyển mọi lỗi thành false, null hoặc collection rỗng. Điều đó có thể khiến rule sai được coi như hợp lệ và che giấu lỗi hạ tầng.

## 9. Những lỗi triển khai thường gặp

| Cách triển khai | Hậu quả | Cách sửa |
|---|---|---|
| canRead ném AccessException khi target không hỗ trợ | Accessor tiếp theo có thể không được thử | Trả false |
| canWrite ném AccessException khi property không thuộc accessor | Chặn accessor có thể ghi khác | Trả false |
| MethodResolver ném exception khi tên method không phù hợp | Resolver khác không có cơ hội xử lý | Trả null |
| ConstructorResolver ném exception khi không có candidate | Phân giải constructor bị ngắt sớm | Trả null |
| read/write trả null hoặc bỏ qua lỗi backend | Che giấu lỗi và tạo kết quả không rõ nghĩa | Ném AccessException có cause |
| Mất cause khi bọc exception | Khó tìm nguyên nhân gốc | Dùng constructor AccessException có cause |
| Bắt mọi SpelEvaluationException rồi trả false | Expression lỗi bị hiểu như điều kiện không đạt | Phân loại lỗi và báo đúng tầng |
| Dùng AccessException thay cho authorization | Trộn lỗi extension point với chính sách bảo mật | Kiểm tra quyền ở service/security layer |
| Trả exception message nội bộ cho client | Có thể lộ tên bean, class hoặc dữ liệu nhạy cảm | Ánh xạ sang thông báo an toàn |
| Dùng accessor hỗ trợ mọi target class | Có thể xung đột với accessor khác | Khai báo specific target classes chính xác |

## 10. Kiểm thử accessor và resolver

### 10.1. Kiểm thử trường hợp không hỗ trợ

Với accessor tùy chỉnh, xác nhận target không phù hợp trả false:

~~~java
assertFalse(
        accessor.canRead(context, new OrderView(), "email")
);
~~~

Với resolver, xác nhận method ngoài phạm vi trả null:

~~~java
assertNull(
        resolver.resolve(
                context,
                new OrderView(),
                "unknownMethod",
                List.of()
        )
);
~~~

Các kiểm thử này quan trọng vì chúng bảo đảm extension point cho phép resolver/accessor khác tiếp tục xử lý.

### 10.2. Kiểm thử AccessException từ thao tác thực tế

Tạo trường hợp accessor đã xác định có thể đọc property nhưng backend bị lỗi. Xác nhận:

- AccessException được ném ra.
- Cause gốc được giữ lại.
- SpEL chuyển lỗi thành SpelEvaluationException khi evaluate.
- Ứng dụng không hiểu nhầm lỗi thành property không tồn tại hoặc kết quả null.

Ví dụ kiểm tra loại exception ngoài:

~~~java
assertThrows(
        SpelEvaluationException.class,
        () -> parser.parseExpression("email")
                .getValue(context)
);
~~~

Sau đó kiểm tra cause chain để xác nhận AccessException hoặc exception gốc được giữ lại theo cách implementation đang dùng.

### 10.3. Kiểm thử read và write

PropertyAccessor có thể hỗ trợ đọc nhưng không hỗ trợ ghi. Hãy kiểm thử riêng:

- canRead true và read trả đúng TypedValue.
- canRead false khi property không thuộc accessor.
- canWrite false khi target hoặc property không được hỗ trợ.
- write cập nhật đúng giá trị khi được phép.
- read/write ném AccessException khi thao tác thực tế thất bại.
- Không có accessor tùy chỉnh nào chặn accessor khác chỉ vì target không phù hợp.

### 10.4. Kiểm thử method và constructor executor

Với resolver tùy chỉnh, kiểm thử cả bước resolve và execute:

- Không hỗ trợ target: null.
- Tên hoặc arity không phù hợp: null.
- Candidate hợp lệ: trả executor.
- Executor thực thi thành công: trả TypedValue đúng.
- Executor thất bại: AccessException giữ cause.
- Resolver mặc định vẫn có thể xử lý các method không thuộc phạm vi resolver tùy chỉnh.

## 11. Quy trình điều tra AccessException trong ứng dụng

Khi gặp lỗi AccessException hoặc SpelEvaluationException có cause là AccessException, hãy làm theo trình tự:

1. **Xác định thao tác.** Expression đang đọc property, ghi property, gọi method, tạo object hay tham chiếu bean?
2. **Tìm extension point.** Xác định PropertyAccessor, MethodResolver, ConstructorResolver hoặc BeanResolver được dùng.
3. **Kiểm tra target.** Xác nhận target class và kiểu argument đúng như extension point mong đợi.
4. **Phân biệt không hỗ trợ và lỗi thật.** Trường hợp không hỗ trợ phải trả false/null; lỗi thực tế mới ném AccessException.
5. **Đọc cause chain.** Tìm exception reflection, backend hoặc logic bên trong gây lỗi.
6. **Kiểm tra thứ tự đăng ký.** Accessor/resolver tùy chỉnh có đang chặn extension point khác hay không?
7. **Kiểm tra quyền.** Nếu lỗi là từ chối truy cập nghiệp vụ, xác nhận authorization ở tầng service.
8. **Sửa tại extension point.** Giữ đúng hợp đồng interface và thông báo có ngữ cảnh.
9. **Kiểm thử cả hai nhánh.** Không hỗ trợ phải cho phép resolver khác xử lý; lỗi thật phải được truyền ra rõ ràng.

Quy trình này giúp tránh cách sửa phổ biến là bắt exception rồi trả false hoặc null, vốn có thể làm mất nguyên nhân và che giấu lỗi cấu hình.

## 12. Tổng kết

AccessException là exception thuộc package org.springframework.expression, được các extension point dùng để báo lỗi trong quá trình truy cập hoặc phân giải. SpEL thường chuyển nó thành SpelEvaluationException gắn với thao tác đang đánh giá và giữ cause để điều tra.

- PropertyAccessor dùng AccessException trong các thao tác đọc/ghi và kiểm tra khả năng truy cập.
- MethodResolver và ConstructorResolver dùng nó khi quá trình tìm candidate gặp lỗi; executor cũng có thể báo lỗi lúc thực thi.
- BeanResolver dùng nó khi tra cứu bean không thể hoàn thành.
- Không hỗ trợ target/member nên trả false hoặc null theo hợp đồng; lỗi thực tế mới ném AccessException.
- Giữ cause, phân loại lỗi theo giai đoạn và không chuyển mọi lỗi thành false/null.
- AccessException của SpEL khác với AccessDeniedException của Spring Security.
- Authorization, validation và giới hạn tài nguyên vẫn thuộc trách nhiệm của tầng ứng dụng.

Khi viết accessor hoặc resolver tùy chỉnh, hãy làm cho trường hợp “không phù hợp” và “đã phù hợp nhưng thao tác thất bại” thật rõ ràng. Điều đó giúp SpEL tiếp tục tìm extension point thích hợp khi cần, đồng thời giữ lại thông tin chính xác khi một thao tác truy cập thực sự bị lỗi.