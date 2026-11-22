# Đăng ký PropertyAccessor, MethodResolver và ConstructorResolver

**EvaluationContext** quyết định SpEL có thể nhìn thấy và thao tác với dữ liệu nào khi đánh giá một biểu thức. Với **StandardEvaluationContext**, ứng dụng có thể mở rộng cách truy cập property, cách tìm method và cách tìm constructor bằng ba extension point: **PropertyAccessor**, **MethodResolver** và **ConstructorResolver**.

Các thành phần này tách biệt ba nhiệm vụ:

- **PropertyAccessor** đọc hoặc ghi một property trên object đích.
- **MethodResolver** tìm cách gọi một method trên object đích với tên và các đối số đã cho.
- **ConstructorResolver** tìm cách tạo một instance của kiểu được yêu cầu với các đối số đã cho.

Việc đăng ký resolver tùy chỉnh giúp biểu thức làm việc với mô hình dữ liệu riêng, giới hạn những thao tác được phép hoặc tích hợp với cách truy cập object đặc thù của ứng dụng.

## Ba extension point làm nhiệm vụ gì?

| Thành phần | Câu hỏi nó giải quyết | Interface thực thi |
|---|---|---|
| PropertyAccessor | Có thể đọc hoặc ghi property tên này trên object đích không? | **PropertyAccessor** |
| MethodResolver | Có thể gọi method tên này với các kiểu đối số hiện tại không? | **MethodResolver** |
| ConstructorResolver | Có constructor phù hợp để tạo kiểu này với các kiểu đối số hiện tại không? | **ConstructorResolver** |

Các resolver thường không trực tiếp thực hiện thao tác ngay khi được hỏi. Chúng tìm một cách thực thi phù hợp và trả về một executor. SpEL sau đó gọi executor khi biểu thức được đánh giá.

Trong StandardEvaluationContext, các implementation reflective mặc định thường là:

- **ReflectivePropertyAccessor** để truy cập property JavaBean và các property phù hợp thông qua reflection.
- **ReflectiveMethodResolver** để tìm method có thể gọi bằng reflection.
- **ReflectiveConstructorResolver** để tìm constructor có thể gọi bằng reflection.

Ứng dụng có thể thêm resolver riêng, thay thế danh sách mặc định hoặc tạo một danh sách có thứ tự rõ ràng.

## Đăng ký trên StandardEvaluationContext

Cách đơn giản là tạo StandardEvaluationContext rồi thêm từng thành phần:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.addPropertyAccessor(new CustomPropertyAccessor());
context.addMethodResolver(new CustomMethodResolver());
context.addConstructorResolver(new CustomConstructorResolver());
~~~

Các method **addPropertyAccessor(...)**, **addMethodResolver(...)** và **addConstructorResolver(...)** thêm implementation vào danh sách tương ứng của context.

Nếu muốn thay thế toàn bộ danh sách, có thể dùng:

~~~java
context.setPropertyAccessors(propertyAccessors);
context.setMethodResolvers(methodResolvers);
context.setConstructorResolvers(constructorResolvers);
~~~

Các method set... thay danh sách resolver/accessor đang có. Khi thay danh sách, ứng dụng phải tự đưa vào những implementation cần thiết. Nếu bỏ resolver reflective mặc định, các property, method hoặc constructor mà implementation đó từng xử lý có thể không còn truy cập được.

Thứ tự trong danh sách có ý nghĩa: SpEL thử các accessor hoặc resolver theo danh sách đã cấu hình để tìm thành phần phù hợp. Khi cần ưu tiên một accessor tùy chỉnh nhưng vẫn giữ hành vi reflective làm fallback, hãy cấu hình danh sách theo thứ tự mong muốn và thêm ReflectivePropertyAccessor, ReflectiveMethodResolver hoặc ReflectiveConstructorResolver ở vị trí fallback.

## PropertyAccessor: tùy chỉnh cách đọc và ghi property

**PropertyAccessor** cho phép SpEL truy cập một property trên object đích. Interface này cung cấp các thao tác chính:

~~~java
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
~~~

Ý nghĩa:

- **getSpecificTargetClasses()** cho biết accessor áp dụng cho những loại target nào. Trả về null nếu accessor không giới hạn theo kiểu target.
- **canRead(...)** cho biết accessor có thể đọc property hay không.
- **read(...)** trả về giá trị property dưới dạng TypedValue.
- **canWrite(...)** cho biết accessor có thể ghi property hay không.
- **write(...)** thực hiện cập nhật property.

Ví dụ, một accessor chỉ cho phép đọc một số key được chọn từ Map:

~~~java
public class AllowlistedMapPropertyAccessor
        implements PropertyAccessor {

    private static final Set<String> ALLOWED =
            Set.of("theme", "locale");

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Map.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {
        return target instanceof Map<?, ?> map
                && ALLOWED.contains(name)
                && map.containsKey(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {
        if (!canRead(context, target, name)) {
            throw new AccessException("Property is not available: " + name);
        }

        Map<?, ?> map = (Map<?, ?>) target;
        return new TypedValue(map.get(name));
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {
        return false;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {
        throw new AccessException("This accessor is read-only");
    }
}
~~~

Đăng ký accessor:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(
        List.of(new AllowlistedMapPropertyAccessor()));

Map<String, Object> settings = Map.of(
        "theme", "dark",
        "locale", "vi",
        "internalToken", "not-exposed");

ExpressionParser parser = new SpelExpressionParser();

String theme = parser.parseExpression("theme")
        .getValue(context, settings, String.class);
~~~

Accessor chỉ đọc được các key nằm trong allowlist. Property **internalToken** không được accessor này expose.

Trong ví dụ, **setPropertyAccessors(...)** thay danh sách accessor mặc định. Đây là lựa chọn có chủ đích để biểu thức chỉ dùng accessor allowlist. Nếu muốn giữ reflective access cho các object khác, hãy đưa cả accessor tùy chỉnh và accessor reflective vào danh sách theo thứ tự phù hợp. Không nên thêm một allowlist accessor rồi vẫn giữ một fallback rộng nếu mục tiêu là ngăn truy cập các property ngoài danh sách.

Với object nghiệp vụ, accessor tùy chỉnh có thể ánh xạ tên property SpEL sang trường dữ liệu nội bộ, đọc dữ liệu từ một cấu trúc không phải JavaBean hoặc từ chối các property không được expose.

## MethodResolver: tùy chỉnh cách tìm method

**MethodResolver** chịu trách nhiệm tìm cách gọi method trên target object. Nó nhận EvaluationContext, object đích, tên method và danh sách TypeDescriptor mô tả kiểu các đối số:

~~~java
MethodExecutor resolve(
        EvaluationContext context,
        Object targetObject,
        String name,
        List<TypeDescriptor> argumentTypes) throws AccessException;
~~~

Nếu tìm được method phù hợp, resolver trả về một **MethodExecutor**. Executor thực hiện lời gọi và trả về TypedValue:

~~~java
TypedValue execute(
        EvaluationContext context,
        Object target,
        Object... arguments) throws AccessException;
~~~

Ví dụ, ứng dụng muốn chỉ cho phép gọi method **normalize** trên một object TextTools:

~~~java
public class AllowlistedMethodResolver
        implements MethodResolver {

    private static final Set<String> ALLOWED =
            Set.of("normalize");

    private final MethodResolver reflective =
            new ReflectiveMethodResolver();

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!ALLOWED.contains(name)) {
            return null;
        }

        return reflective.resolve(
                context,
                targetObject,
                name,
                argumentTypes);
    }
}
~~~

Đăng ký resolver theo danh sách chỉ chứa resolver allowlist:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setMethodResolvers(
        List.of(new AllowlistedMethodResolver()));
~~~

Resolver tùy chỉnh chỉ ủy quyền việc tìm method cho ReflectiveMethodResolver khi tên method nằm trong allowlist. Vì danh sách context không có một reflective resolver độc lập ở phía sau, method ngoài allowlist không thể được resolver mặc định gọi thay thế.

Trong ứng dụng thật, allowlist nên xét cả target type và chữ ký method, không chỉ tên method. Nhiều lớp có thể có method trùng tên nhưng mức độ an toàn khác nhau. Có thể kiểm tra targetObject.getClass(), số lượng đối số và TypeDescriptor của từng đối số trước khi ủy quyền.

Nếu method không được resolver nào hỗ trợ, SpEL không thể thực hiện lời gọi và sẽ phát sinh lỗi evaluation. Nếu method được tìm thấy nhưng bản thân method ném exception, lỗi phát sinh trong quá trình executor thực thi.

## ConstructorResolver: tùy chỉnh cách tìm constructor

**ConstructorResolver** tìm constructor cho biểu thức có cú pháp **new TypeName(arguments)**. Interface nhận EvaluationContext, tên kiểu và danh sách kiểu đối số:

~~~java
ConstructorExecutor resolve(
        EvaluationContext context,
        String typeName,
        List<TypeDescriptor> argumentTypes) throws AccessException;
~~~

Nếu tìm được constructor phù hợp, resolver trả về **ConstructorExecutor**. Executor tạo object và trả về TypedValue:

~~~java
TypedValue execute(
        EvaluationContext context,
        Object... arguments) throws AccessException;
~~~

Ví dụ, chỉ cho phép tạo một kiểu SafeValue:

~~~java
public class AllowlistedConstructorResolver
        implements ConstructorResolver {

    private static final Set<String> ALLOWED_TYPES =
            Set.of("com.example.SafeValue");

    private final ConstructorResolver reflective =
            new ReflectiveConstructorResolver();

    @Override
    public ConstructorExecutor resolve(
            EvaluationContext context,
            String typeName,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!ALLOWED_TYPES.contains(typeName)) {
            return null;
        }

        return reflective.resolve(
                context,
                typeName,
                argumentTypes);
    }
}
~~~

Đăng ký resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setConstructorResolvers(
        List.of(new AllowlistedConstructorResolver()));
~~~

Với cấu hình này, resolver chỉ ủy quyền cho ReflectiveConstructorResolver khi tên kiểu nằm trong allowlist. Nếu ứng dụng cần hỗ trợ nhiều kiểu, hãy đăng ký từng kiểu được phép và kiểm tra cả số lượng, kiểu đối số cùng tác động của constructor.

TypeLocator vẫn chịu trách nhiệm phân giải tên kiểu thành Class. ConstructorResolver quyết định có constructor nào được phép và phù hợp để gọi. Hai thành phần này phối hợp nhưng không thay thế nhau.

## Thứ tự resolver và hành vi fallback

Một context có thể chứa nhiều PropertyAccessor, MethodResolver hoặc ConstructorResolver. SpEL lần lượt hỏi các thành phần đã đăng ký để tìm cách xử lý phù hợp.

Ví dụ, nếu muốn accessor tùy chỉnh xử lý Map trước, nhưng vẫn dùng reflective access cho JavaBean:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(List.of(
        new AllowlistedMapPropertyAccessor(),
        new ReflectivePropertyAccessor()));
~~~

Danh sách được cấu hình theo thứ tự ưu tiên mong muốn. Accessor tùy chỉnh được hỏi trước; reflective accessor là fallback cho những target/property mà accessor tùy chỉnh không xử lý.

Tương tự, có thể kết hợp resolver tùy chỉnh với resolver reflective nếu muốn fallback cho các method hoặc constructor khác. Tuy nhiên, điều này thay đổi chính sách quyền: một resolver tùy chỉnh trả null có thể để resolver tiếp theo xử lý lời gọi. Vì vậy, nếu mục tiêu là allowlist, hãy bảo đảm không còn resolver rộng hơn có thể xử lý thao tác bị từ chối.

Cần phân biệt hai mục tiêu:

- **Mở rộng khả năng:** thêm accessor/resolver để hỗ trợ kiểu dữ liệu mới nhưng vẫn giữ hành vi mặc định.
- **Giới hạn khả năng:** thay danh sách mặc định bằng danh sách được kiểm soát và không giữ fallback rộng ngoài ý muốn.

## Dùng add... hay set...?

Các API thêm và thay thế phục vụ hai mục tiêu khác nhau:

| API | Tác dụng |
|---|---|
| **addPropertyAccessor(...)** | Thêm accessor vào danh sách hiện tại |
| **setPropertyAccessors(...)** | Thay toàn bộ danh sách property accessor |
| **addMethodResolver(...)** | Thêm method resolver vào danh sách hiện tại |
| **setMethodResolvers(...)** | Thay toàn bộ danh sách method resolver |
| **addConstructorResolver(...)** | Thêm constructor resolver vào danh sách hiện tại |
| **setConstructorResolvers(...)** | Thay toàn bộ danh sách constructor resolver |

Nếu chỉ cần hỗ trợ thêm một kiểu dữ liệu và vẫn muốn hành vi mặc định, các method add... thường thuận tiện. Nếu cần kiểm soát chính xác thứ tự hoặc giới hạn quyền truy cập, hãy tạo danh sách rõ ràng bằng set....

Không nên dùng set... rồi quên thêm lại resolver mặc định cần thiết. Ngược lại, không nên dùng add... cho một allowlist bảo mật nếu resolver mặc định vẫn có thể xử lý những thao tác mà custom resolver từ chối.

## Kết hợp ba thành phần trong một context

Một ứng dụng có thể cần cả ba loại tùy chỉnh. Ví dụ, context cho phép:

- Đọc property từ một cấu trúc dữ liệu đặc thù.
- Gọi một tập method đã chọn.
- Tạo một tập kiểu object đã chọn.

Có thể cấu hình từng danh sách riêng:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(
        List.of(new AllowlistedMapPropertyAccessor()));

context.setMethodResolvers(
        List.of(new AllowlistedMethodResolver()));

context.setConstructorResolvers(
        List.of(new AllowlistedConstructorResolver()));
~~~

Mỗi extension point kiểm soát một loại thao tác. Một property accessor chỉ đọc không tự ngăn method invocation; một method resolver allowlist không tự giới hạn constructor; và constructor resolver không quyết định property nào được đọc. Muốn giới hạn toàn bộ biểu thức, phải xem xét cả ba cùng với TypeLocator, BeanResolver, root object và biến được cung cấp.

## SimpleEvaluationContext và giới hạn extension point

**SimpleEvaluationContext** được thiết kế cho một tập con khả năng SpEL, thường dùng trong data binding khi không cần toàn bộ quyền của StandardEvaluationContext. Builder của nó cho phép cấu hình PropertyAccessor và một số khả năng truy cập method theo phạm vi hỗ trợ.

SimpleEvaluationContext không cung cấp đầy đủ các cơ chế như type reference, constructor invocation và bean reference. Vì vậy, không thể xem nó là một StandardEvaluationContext có thể đăng ký mọi resolver tùy ý.

Nếu use case cần tùy chỉnh cả PropertyAccessor, MethodResolver và ConstructorResolver, StandardEvaluationContext là lựa chọn linh hoạt hơn. Nếu chỉ cần đọc property với tập accessor giới hạn, SimpleEvaluationContext có thể phù hợp và giúp giảm bề mặt thao tác.

## Xử lý lỗi và chẩn đoán

Lỗi liên quan đến resolver có thể xuất hiện ở nhiều thời điểm:

- **ParseException:** chuỗi SpEL sai cú pháp; parser không tạo được Expression.
- **Không tìm thấy accessor/resolver phù hợp:** biểu thức hợp lệ nhưng context không có thành phần hỗ trợ thao tác cần thiết.
- **AccessException:** accessor hoặc resolver gặp vấn đề khi kiểm tra hay thực hiện thao tác.
- **EvaluationException:** SpEL không thể hoàn thành việc đánh giá; nguyên nhân có thể là property không tồn tại, method/constructor không phù hợp, conversion thất bại hoặc executor phát sinh lỗi.

Nên ghi nhận loại thao tác, tên property/method/type và ngữ cảnh cần thiết để chẩn đoán. Tránh ghi toàn bộ object hoặc đối số nếu chúng chứa dữ liệu nhạy cảm.

Khi custom resolver từ chối thao tác, hãy trả về kết quả không tìm thấy phù hợp với hợp đồng interface hoặc phát sinh AccessException khi thực sự có lỗi truy cập. Không nên bắt mọi exception rồi trả null, vì cách đó có thể che giấu lỗi lập trình bên trong resolver và làm SpEL chuyển sang một resolver khác ngoài dự định.

## Bảo mật và giới hạn bề mặt thao tác

Các resolver quyết định phần nào của ứng dụng có thể được biểu thức truy cập. Nếu biểu thức đến từ cấu hình do người dùng chỉnh sửa hoặc từ một nguồn không đáng tin cậy, việc dùng StandardEvaluationContext với các resolver reflective mặc định có thể mở ra nhiều khả năng hơn use case yêu cầu.

Một số nguyên tắc:

- Chỉ expose property cần thiết; dùng PropertyAccessor theo allowlist khi cần.
- Giới hạn method theo target type, tên và chữ ký đối số.
- Chỉ cho phép tạo các kiểu object có constructor phù hợp và không có tác động phụ ngoài ý muốn.
- Không expose service, repository hoặc object có quyền truy cập tài nguyên nếu biểu thức không cần.
- Khi cần giới hạn, thay danh sách mặc định bằng danh sách có kiểm soát thay vì chỉ thêm một resolver allowlist rồi giữ fallback rộng.
- Kết hợp resolver với root object nhỏ, biến rõ ràng và TypeLocator phù hợp.

Một resolver tùy chỉnh không tự tạo ra sandbox hoàn chỉnh. Các thành phần khác của EvaluationContext vẫn có thể cung cấp quyền truy cập bổ sung. Chính sách an toàn phải được thiết kế trên toàn bộ context.

## Khi nào nên viết resolver tùy chỉnh?

Nên cân nhắc resolver/accessor tùy chỉnh khi:

- Dữ liệu không tuân theo JavaBean convention nhưng cần truy cập bằng cú pháp property.
- Muốn ánh xạ property SpEL sang một mô hình dữ liệu riêng.
- Chỉ cho phép gọi một tập method hoặc constructor đã xác định.
- Cần tích hợp một cơ chế object/factory đặc thù.
- Muốn kiểm soát thứ tự ưu tiên giữa nhiều cách truy cập.
- Biểu thức được cấu hình bên ngoài và cần giới hạn bề mặt thao tác.

Nếu chỉ cần đọc một property thông thường hoặc gọi method JavaBean thông dụng, resolver reflective mặc định thường đã đủ. Không nên tạo extension point riêng nếu không có yêu cầu rõ ràng về hành vi hoặc quyền truy cập.

## Kết luận

**PropertyAccessor**, **MethodResolver** và **ConstructorResolver** là ba extension point để kiểm soát cách SpEL đọc/ghi property, gọi method và tạo object. StandardEvaluationContext cho phép thêm hoặc thay thế danh sách của từng loại bằng các API **add...** và **set...**. Các resolver tìm executor phù hợp; executor mới thực hiện thao tác khi biểu thức được đánh giá.

Thứ tự resolver quyết định fallback và có thể ảnh hưởng trực tiếp đến quyền truy cập. Nếu muốn mở rộng, hãy giữ resolver mặc định cần thiết; nếu muốn giới hạn, hãy thay danh sách bằng các implementation được kiểm soát và không để fallback rộng vô tình mở lại thao tác bị từ chối. Kết hợp ba extension point với root object, TypeLocator và các thành phần khác của EvaluationContext giúp biểu thức có đúng khả năng ứng dụng cần.
