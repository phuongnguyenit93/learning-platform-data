# MethodResolver và cách giới hạn method được phép gọi trong SpEL

SpEL có thể gọi method trên root object, biến, property hoặc bean mà EvaluationContext cho phép truy cập. Khả năng này hữu ích khi biểu thức cần thực hiện một phép tính hoặc truy vấn nhỏ, nhưng cũng mở rộng đáng kể những gì một biểu thức có thể làm.

MethodResolver là thành phần quyết định cách SpEL tìm và chuẩn bị một method để gọi. Khi ứng dụng chỉ muốn cho phép một số method cụ thể, cần kiểm soát resolver và các method ứng viên. Bài học này giải thích cơ chế phân giải method, cách dùng MethodFilter, cách thay thế resolver mặc định bằng allowlist và những giới hạn bảo mật cần tính đến.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Giải thích vai trò của MethodResolver trong quá trình đánh giá lời gọi method.
- Phân biệt MethodResolver với PropertyAccessor, ConstructorResolver và BeanResolver.
- Nhận biết ReflectiveMethodResolver mặc định của StandardEvaluationContext.
- Dùng MethodFilter để giới hạn method được phép gọi trên một kiểu cụ thể.
- Thay thế danh sách MethodResolver bằng resolver do ứng dụng kiểm soát.
- Xây dựng allowlist dựa trên target type, tên method và kiểu tham số.
- Kiểm tra method overload, proxy và hành vi khi method bị từ chối.
- Giới hạn các quyền khác của EvaluationContext để biểu thức không trở thành một điểm thực thi tùy ý.

Bạn nên biết cách gọi method trong SpEL, cách tạo StandardEvaluationContext và cách truyền root object hoặc biến vào context.

## 2. SpEL phân giải một lời gọi method như thế nào?

Khi gặp một biểu thức như:

~~~text
#policy.calculateDiscount(#order.total)
~~~

SpEL cần xác định:

1. Đối tượng nhận lời gọi là gì, ở đây là giá trị của biến policy.
2. Có method tên calculateDiscount trên đối tượng đó hay không.
3. Method overload nào phù hợp với danh sách đối số.
4. Có thể chuyển đổi kiểu đối số sang kiểu tham số của method hay không.
5. Có thể tạo một MethodExecutor để thực hiện lời gọi hay không.

EvaluationContext cung cấp danh sách MethodResolver. SpEL lần lượt hỏi các resolver để tìm một cách thực hiện lời gọi. Resolver có thể trả về một MethodExecutor nếu tìm được method phù hợp, trả về null nếu không thể xử lý lời gọi đó, hoặc ném AccessException khi gặp lỗi trong quá trình phân giải.

Luồng khái quát:

~~~text
Expression có lời gọi method
          |
          v
Xác định target object và đối số
          |
          v
Danh sách MethodResolver
          |
          v
Tìm method phù hợp
          |
          v
MethodExecutor
          |
          v
Thực thi method và nhận kết quả
~~~

MethodResolver tham gia vào bước tìm cách gọi method. Nó không phải nơi kiểm tra toàn bộ quyền truy cập của ứng dụng và cũng không thay thế validation nghiệp vụ.

## 3. ReflectiveMethodResolver mặc định

StandardEvaluationContext thường được khởi tạo với ReflectiveMethodResolver. Resolver này dùng reflection để tìm method phù hợp trên target object, bao gồm việc xử lý overload và chuyển đổi đối số theo cơ chế của SpEL.

Ví dụ:

~~~java
public class PricingPolicy {
    public BigDecimal discount(BigDecimal total) {
        return total.multiply(new BigDecimal("0.10"));
    }

    public void resetAllRules() {
        // Thay đổi trạng thái cấu hình
    }
}
~~~

Nếu PricingPolicy là root object:

~~~java
PricingPolicy policy = new PricingPolicy();

StandardEvaluationContext context =
    new StandardEvaluationContext(policy);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("discount(new java.math.BigDecimal('100'))");

Object result = expression.getValue(context);
~~~

Lời gọi method được resolver mặc định tìm và thực thi nếu method có thể truy cập và đối số phù hợp.

Vấn đề là resolver reflection tổng quát có thể tìm nhiều public method trên object. Nếu root object là một service lớn, biểu thức có thể nhìn thấy nhiều thao tác hơn nhu cầu thực tế. Chỉ đưa một service vào context đã có thể mở rộng đáng kể bề mặt hành vi.

Vì vậy, hãy giới hạn object được expose và giới hạn method mà biểu thức có thể gọi.

## 4. MethodResolver khác gì các thành phần truy cập khác?

EvaluationContext có nhiều cơ chế độc lập:

| Thành phần | Trách nhiệm |
|---|---|
| PropertyAccessor | Đọc hoặc ghi property và field |
| MethodResolver | Tìm cách gọi method trên target object |
| ConstructorResolver | Tìm cách gọi constructor |
| TypeLocator | Phân giải kiểu trong cú pháp T(...) |
| BeanResolver | Phân giải bean trong cú pháp @beanName |
| TypeConverter | Chuyển đổi giá trị giữa các kiểu |
| Variable/function registry | Cung cấp biến và function đã đăng ký |

Giới hạn MethodResolver không tự động giới hạn tất cả khả năng còn lại. Ví dụ, biểu thức vẫn có thể đọc property thông qua PropertyAccessor; cú pháp T(...) vẫn phụ thuộc TypeLocator; cú pháp @beanName phụ thuộc BeanResolver; và function được đăng ký như biến vẫn có thể được gọi theo cơ chế riêng.

Một thiết kế an toàn phải xem xét toàn bộ quyền của context theo use case, thay vì chỉ chặn một nhóm method.

## 5. Dùng MethodFilter để lọc method được phép gọi

Với StandardEvaluationContext và ReflectiveMethodResolver, Spring cung cấp MethodFilter. Filter nhận danh sách method ứng viên và trả về danh sách method được giữ lại.

Ví dụ, PricingPolicy chỉ cho phép gọi discount với đúng một tham số BigDecimal:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(policy);

context.registerMethodFilter(
    PricingPolicy.class,
    methods -> methods.stream()
        .filter(method -> method.getName().equals("discount"))
        .filter(method -> Arrays.equals(
            method.getParameterTypes(),
            new Class<?>[] { BigDecimal.class }))
        .filter(method -> method.getReturnType().equals(BigDecimal.class))
        .toList()
);
~~~

Filter loại bỏ resetAllRules và các overload không nằm trong allowlist. Khi SpEL phân giải lời gọi method trên PricingPolicy, reflective resolver chỉ có thể chọn method còn lại sau khi lọc.

Đăng ký MethodFilter yêu cầu ReflectiveMethodResolver có mặt trong danh sách resolver. StandardEvaluationContext mặc định đã cung cấp resolver này. Nếu ứng dụng đã thay danh sách resolver, hãy kiểm tra resolver thực tế trước khi đăng ký filter; Spring có thể báo lỗi nếu không tìm thấy ReflectiveMethodResolver phù hợp.

### 5.1. Allowlist nên kiểm tra chữ ký, không chỉ tên

Không nên chỉ lọc theo tên method:

~~~java
.filter(method -> method.getName().equals("discount"))
~~~

Nếu class có nhiều overload cùng tên, filter trên có thể giữ lại những chữ ký mà ứng dụng không dự định expose. Hãy xem xét:

- Tên method.
- Kiểu tham số và số lượng tham số.
- Kiểu trả về.
- Modifier và khả năng truy cập.
- Target class thực tế.
- Method được kế thừa hoặc override.

Ví dụ ở trên lọc chính xác một chữ ký nhận BigDecimal và trả về BigDecimal. Với hệ thống có nhiều method, nên tạo hàm kiểm tra chữ ký riêng để allowlist dễ đọc và dễ kiểm thử.

### 5.2. MethodFilter áp dụng theo kiểu target đã đăng ký

MethodFilter được đăng ký cho một kiểu cụ thể. Nếu target là proxy hoặc một subclass do framework tạo ra, cần kiểm tra cách resolver xác định kiểu method và bảo đảm filter áp dụng đúng đối tượng runtime.

Với Spring AOP proxy, hãy test trên đúng proxy mà ứng dụng đưa vào EvaluationContext. Không nên chỉ test trên class đơn giản trong unit test rồi giả định mọi proxy đều có hành vi giống nhau.

MethodFilter là cách thuận tiện khi ứng dụng vẫn muốn dùng reflective method resolution nhưng cần lọc các method trên một số kiểu target đã biết.

## 6. Thay thế danh sách MethodResolver

Nếu cần kiểm soát chặt hơn, có thể thay danh sách MethodResolver của StandardEvaluationContext:

~~~java
context.setMethodResolvers(List.of(customResolver));
~~~

Khi làm vậy, danh sách mới thay thế danh sách resolver hiện có. Nếu chỉ muốn dùng resolver allowlist, đừng giữ lại một ReflectiveMethodResolver tổng quát phía sau, vì resolver đó có thể tiếp tục phân giải các method mà resolver trước từ chối.

Một resolver tùy chỉnh có thể:

- Chỉ chấp nhận một số target class.
- Chỉ chấp nhận một số tên method.
- Kiểm tra chính xác kiểu tham số.
- Từ chối method static hoặc method có tác dụng phụ.
- Trả về MethodExecutor được tạo từ một tập method đã xác định.
- Ghi nhận lý do từ chối theo cách không làm lộ dữ liệu nhạy cảm.

Hợp đồng resolve(...) trả về MethodExecutor khi resolver xử lý được lời gọi. Trả về null có nghĩa resolver này không phân giải lời gọi; các resolver tiếp theo vẫn có thể thử. Vì vậy, nếu muốn từ chối chắc chắn một method, phải bảo đảm không có resolver tổng quát khác có thể cho phép lại lời gọi đó. Một cách là đặt duy nhất allowlist resolver trong context. Với lỗi phân giải thực sự, resolver có thể ném AccessException theo hợp đồng API.

### 6.1. Phác thảo một resolver allowlist

Resolver thực tế nên kiểm tra cả target type và chữ ký. Cấu trúc sau minh họa cách tổ chức:

~~~java
public final class RestrictedMethodResolver
        implements MethodResolver {

    private final ReflectiveMethodResolver delegate =
        new ReflectiveMethodResolver();

    private final Set<MethodKey> allowedMethods;

    public RestrictedMethodResolver(Set<MethodKey> allowedMethods) {
        this.allowedMethods = Set.copyOf(allowedMethods);
    }

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object target,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (target == null) {
            return null;
        }

        MethodKey key = MethodKey.from(
            target.getClass(), name, argumentTypes);

        if (!allowedMethods.contains(key)) {
            return null;
        }

        return delegate.resolve(
            context, target, name, argumentTypes);
    }
}
~~~

MethodKey ở đây là kiểu dữ liệu do ứng dụng định nghĩa để đại diện cho target type, tên method và kiểu tham số. Đây là phác thảo kiến trúc, không phải một lớp hoàn chỉnh có thể copy mà không định nghĩa MethodKey.

Khi sử dụng:

~~~java
context.setMethodResolvers(
    List.of(new RestrictedMethodResolver(allowedMethods))
);
~~~

Vì chỉ có resolver allowlist trong danh sách, method bị từ chối sẽ không được chuyển sang một reflective resolver tổng quát khác.

Trong implementation thật, hãy xử lý proxy class, interface được expose, bridge method, generic method và quy tắc overload. Nếu có thể, allowlist theo một interface/facade ổn định do ứng dụng sở hữu thay vì phụ thuộc class proxy sinh ra lúc runtime.

## 7. Giới hạn method ngay từ thiết kế object

Một cách hiệu quả để giảm quyền là không đưa service tổng quát vào context. Thay vào đó, tạo một facade nhỏ chỉ chứa các thao tác mà biểu thức cần.

Ví dụ:

~~~java
public class PricingExpressionFacade {
    private final PricingPolicy policy;

    public PricingExpressionFacade(PricingPolicy policy) {
        this.policy = policy;
    }

    public BigDecimal calculateDiscount(BigDecimal total) {
        return policy.discount(total);
    }

    public boolean isEligible(BigDecimal total) {
        return total.compareTo(new BigDecimal("100")) >= 0;
    }
}
~~~

Facade không expose resetAllRules, updatePolicy hoặc các thao tác quản trị. Root object của expression chỉ là PricingExpressionFacade.

Biện pháp này có nhiều lợi ích:

- Hợp đồng method dành cho biểu thức nhỏ và ổn định.
- Không expose toàn bộ API của service.
- Dễ viết allowlist và unit test.
- Dễ review thay đổi khi thêm một method mới.
- Có thể kiểm tra tham số và kết quả ngay tại facade.

Dù vậy, facade vẫn cần giới hạn method và dữ liệu được expose. Một method public có thể thực hiện nhiều hành động bên trong; tên method không đủ để kết luận nó an toàn.

## 8. SimpleEvaluationContext và method invocation

SimpleEvaluationContext được thiết kế cho các tình huống cần giới hạn khả năng của SpEL. Theo mặc định, nó không cung cấp đầy đủ các tính năng của StandardEvaluationContext và không bật method invocation rộng rãi.

Nếu use case thực sự cần một số method, builder có thể được cấu hình với các MethodResolver cụ thể:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withMethodResolvers(restrictedResolver)
        .build();
~~~

Hãy kiểm tra phiên bản Spring Framework đang dùng và API builder tương ứng. Chỉ thêm resolver được kiểm soát; không đăng ký reflective resolver tổng quát chỉ để làm cho một biểu thức hoạt động.

Nếu chỉ cần đọc property, không thêm method resolver. Nếu cần gọi method, expose một facade có hợp đồng hẹp và test rõ các lời gọi được cho phép.

## 9. MethodResolver không phải ranh giới bảo mật duy nhất

Một allowlist method không đủ để biến SpEL thành một sandbox. Cần đánh giá các khả năng độc lập:

- **Property access:** PropertyAccessor có thể đọc dữ liệu nhạy cảm hoặc ghi dữ liệu nếu context cho phép.
- **Type references:** TypeLocator ảnh hưởng đến cú pháp T(...).
- **Constructor calls:** ConstructorResolver kiểm soát khả năng tạo object bằng new.
- **Bean references:** BeanResolver kiểm soát cú pháp @beanName.
- **Functions:** Function được đăng ký trong context có thể gọi method đã được expose.
- **Method calls:** MethodResolver quyết định method nào được phân giải.
- **Auto grow và assignment:** Parser configuration cùng quyền ghi property có thể làm thay đổi object graph.

Nếu biểu thức đến từ người dùng hoặc tenant, hãy cân nhắc một ngôn ngữ điều kiện giới hạn riêng thay vì cho phép SpEL tổng quát. Nếu vẫn dùng SpEL, hãy tạo context riêng cho use case, root DTO nhỏ, allowlist rõ ràng và giới hạn kích thước biểu thức.

Không đưa repository, EntityManager, ApplicationContext, service quản trị hoặc object chứa secret vào root object chỉ để thuận tiện.

## 10. Xử lý overload, kiểu tham số và kết quả

Một method có thể có nhiều overload:

~~~java
public String format(String value) { ... }

public String format(BigDecimal value) { ... }

public String format(Object value) { ... }
~~~

Nếu allowlist chỉ kiểm tra tên format, cả ba method có thể được giữ lại. Điều này làm hành vi phụ thuộc vào overload resolution và conversion.

Hãy xác định chữ ký được phép:

- Target type/interface nào.
- Tên method.
- Số lượng tham số.
- Kiểu tham số chính xác hoặc tập kiểu được chấp nhận.
- Kiểu trả về.
- Có cho phép varargs hay không.
- Có cho phép method kế thừa hay không.

Sau khi resolver chọn method, SpEL vẫn cần chuyển đổi đối số nếu phù hợp. Conversion có thể thất bại khi giá trị runtime không tương thích. Method cũng có thể ném exception khi thực thi. Allowlist chỉ kiểm soát khả năng được gọi; nó không bảo đảm method luôn thành công hoặc kết quả luôn hợp lệ.

Ưu tiên method thuần, nhận đầu vào rõ ràng và trả kết quả xác định. Tránh expose method thực hiện I/O, ghi database, gửi message hoặc thay đổi trạng thái toàn cục.

## 11. Kiểm thử allowlist

Một bộ test hữu ích cần xác nhận cả method được phép và method bị từ chối:

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Gọi method đúng tên và chữ ký | Thành công |
| Gọi method không nằm trong allowlist | Không phân giải được hoặc bị từ chối |
| Gọi overload khác kiểu tham số | Bị từ chối |
| Gọi method trên target class khác | Không được allowlist nhầm |
| Gọi method qua proxy runtime | Filter/resolver áp dụng đúng |
| Method nhận đối số không chuyển đổi được | Evaluation thất bại rõ ràng |
| Method ném exception | Lỗi được xử lý theo hợp đồng |
| Có resolver tổng quát phía sau | Test chứng minh method bị từ chối không được resolver sau cho phép lại |
| Dùng SimpleEvaluationContext read-only không có resolver | Method invocation không được cấp |
| Đăng ký restricted resolver | Chỉ các lời gọi được khai báo hoạt động |

Ngoài unit test, hãy test context thực tế được dùng khi ứng dụng tạo expression. Một test với StandardEvaluationContext mới tạo có thể không phản ánh context đã được Spring tùy chỉnh ở runtime.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Method hợp lệ không được tìm thấy | Resolver không hỗ trợ target hoặc chữ ký | Kiểm tra target type, argument types và resolver list |
| Method bị chặn vẫn gọi được | Còn reflective resolver tổng quát phía sau | Thay toàn bộ danh sách resolver hoặc lọc đúng resolver |
| registerMethodFilter báo lỗi | Không có ReflectiveMethodResolver trong context | Kiểm tra danh sách MethodResolver trước khi đăng ký |
| Overload ngoài ý muốn được gọi | Filter chỉ kiểm tra tên method | Kiểm tra chính xác kiểu tham số và kiểu trả về |
| Filter không áp dụng với proxy | Target runtime type khác kiểu đã đăng ký | Test proxy và dùng interface/facade ổn định hoặc resolver tùy chỉnh |
| Method được tìm thấy nhưng evaluate lỗi | Conversion hoặc method execution thất bại | Kiểm tra đối số và exception của method |
| Method bị giới hạn nhưng vẫn đọc được dữ liệu khác | PropertyAccessor và các capability khác độc lập | Giới hạn toàn bộ EvaluationContext theo use case |

Khi debug, hãy xác nhận context đang dùng, danh sách resolver, target object thực tế, chữ ký method và thứ tự resolver. Không thêm một resolver tổng quát để xử lý lỗi trước khi biết vì sao allowlist từ chối lời gọi.

## 13. Bài tập thực hành

1. Tạo PricingPolicy có hai method: calculateDiscount và resetAllRules.
2. Đưa PricingPolicy vào StandardEvaluationContext và thử gọi cả hai method với reflective resolver mặc định.
3. Đăng ký MethodFilter chỉ cho phép calculateDiscount với chữ ký BigDecimal.
4. Thử gọi resetAllRules và một overload không được phép; xác nhận không phân giải được.
5. Thay MethodFilter bằng custom MethodResolver allowlist và thay thế toàn bộ resolver list.
6. Tạo PricingExpressionFacade chỉ expose hai phép đọc an toàn và dùng facade làm root object.
7. Thử cùng biểu thức với target proxy nếu ứng dụng dùng Spring AOP.
8. Viết test để xác nhận không có resolver khác cho phép lại method đã bị từ chối.

## 14. Checklist trước khi expose method cho SpEL

- [ ] Root object có phải DTO hoặc facade nhỏ không?
- [ ] Đã xác định method nào thực sự cần được gọi chưa?
- [ ] Allowlist có kiểm tra target type và chữ ký method không?
- [ ] Có overload hoặc inherited method cần loại trừ không?
- [ ] MethodFilter có gắn đúng target class/runtime proxy không?
- [ ] Nếu dùng custom resolver, resolver tổng quát có bị loại khỏi danh sách không?
- [ ] Method được expose có tác dụng phụ hoặc I/O không?
- [ ] Đã giới hạn PropertyAccessor, TypeLocator, ConstructorResolver và BeanResolver chưa?
- [ ] Đã kiểm thử method được phép, bị từ chối và conversion failure chưa?
- [ ] Biểu thức có nguồn gốc tin cậy và có giới hạn độ dài không?

## 15. Kết luận

MethodResolver quyết định cách SpEL tìm và thực hiện lời gọi method. StandardEvaluationContext thường dùng ReflectiveMethodResolver, nên ứng dụng cần chủ động giới hạn method nếu biểu thức không được phép gọi mọi API trên target object. MethodFilter là cách thuận tiện để lọc method reflection theo kiểu; custom MethodResolver phù hợp khi cần kiểm soát toàn bộ chiến lược phân giải. Hãy allowlist theo target type và chữ ký, loại bỏ resolver tổng quát có thể mở lại quyền bị chặn, expose facade nhỏ và giới hạn cả các capability khác của EvaluationContext.