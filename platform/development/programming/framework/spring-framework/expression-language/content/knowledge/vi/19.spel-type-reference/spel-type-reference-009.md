# Rủi ro thực thi code khi cho phép type tùy ý trong SpEL

Spring Expression Language (SpEL) hỗ trợ tham chiếu kiểu Java bằng toán tử T(...). Tính năng này hữu ích khi biểu thức cần dùng hằng số, field static hoặc method static của một class. Ví dụ, một biểu thức có thể dùng Math.PI hoặc gọi Math.max(...).

Tuy nhiên, khi một biểu thức được lấy từ người dùng, tenant hoặc nguồn bên ngoài mà EvaluationContext cho phép phân giải kiểu và gọi method rộng, biểu thức có thể truy cập các API mạnh của JVM. Khi kết hợp với quyền gọi method, constructor hoặc bean reference, một biểu thức cấu hình có thể trở thành đường thực thi hành động ngoài dự kiến.

Bài học này giải thích vai trò của TypeLocator, những quyền mà type reference mở ra, vì sao chỉ kiểm tra cú pháp không đủ để bảo vệ ứng dụng và cách thiết kế context theo allowlist cùng quyền tối thiểu.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Hiểu cú pháp T(...) và cách SpEL phân giải tên class.
- Phân biệt TypeLocator với MethodResolver và ConstructorResolver.
- Nhận biết rủi ro khi biểu thức được phép tham chiếu class tùy ý.
- Giải thích vì sao static method và constructor có thể tạo side effect.
- Giới hạn type reference bằng TypeLocator allowlist.
- Kết hợp giới hạn kiểu với giới hạn method, constructor, bean và property access.
- Chọn SimpleEvaluationContext hoặc một context chuyên biệt cho biểu thức không tin cậy.
- Thiết kế cách cung cấp dữ liệu và kiểm thử chính sách từ chối.

Bạn nên biết cú pháp SpEL cơ bản, StandardEvaluationContext, MethodResolver và cách truyền dữ liệu qua biến trong EvaluationContext.

## 2. Type reference trong SpEL là gì?

Toán tử T(...) cho phép biểu thức tham chiếu một kiểu Java theo tên. Ví dụ:

~~~text
T(java.lang.Math).PI
~~~

Biểu thức đọc hằng số PI từ class Math.

Có thể gọi method static:

~~~text
T(java.lang.Math).max(10, 20)
~~~

Kết quả là 20.

Với các class trong package java.lang, TypeLocator mặc định thường cho phép dùng tên ngắn nhờ import mặc định. Ví dụ:

~~~text
T(Math).max(10, 20)
~~~

Trong tài liệu và cấu hình production, dùng tên đầy đủ như java.lang.Math giúp người đọc nhận diện class chính xác hơn.

Type reference không tạo instance. Nó cung cấp đối tượng Class để các phần còn lại của biểu thức có thể truy cập thành viên static phù hợp. Việc gọi method vẫn cần cơ chế phân giải method; việc tạo instance bằng cú pháp new là một khả năng riêng liên quan tới ConstructorResolver.

## 3. TypeLocator chịu trách nhiệm gì?

TypeLocator là thành phần trong EvaluationContext dùng để phân giải tên kiểu thành Class Java. Khi SpEL gặp T(...), nó hỏi TypeLocator để tìm kiểu tương ứng.

Với StandardEvaluationContext, TypeLocator mặc định thường là StandardTypeLocator. Resolver này dùng class loader để tìm kiểu và hỗ trợ các import đã cấu hình, bao gồm import mặc định java.lang.

Có thể đặt TypeLocator khác:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(customTypeLocator);
~~~

Điểm quan trọng là TypeLocator quyết định những tên kiểu nào có thể được biểu thức tham chiếu. Nếu resolver cho phép mọi class mà class loader có thể tìm thấy, biểu thức có thể tiếp cận một phạm vi API rất rộng.

TypeLocator không tự thực thi method. Nó chỉ giải quyết tên kiểu. Rủi ro phát sinh khi biểu thức tiếp tục dùng Class đó để đọc static field, gọi static method hoặc kết hợp với các khả năng khác của EvaluationContext.

## 4. Vì sao cho phép type tùy ý có thể nguy hiểm?

Một class Java có thể cung cấp nhiều khả năng ngoài phép tính thuần túy. Một số API có thể:

- Đọc thông tin hệ thống hoặc cấu hình môi trường.
- Truy cập file và thư mục.
- Tạo process hoặc tương tác với tiến trình khác.
- Mở kết nối mạng hoặc gọi dịch vụ bên ngoài.
- Thay đổi thuộc tính hệ thống hoặc trạng thái toàn cục.
- Tạo object có quyền truy cập tới tài nguyên khác.

Các nhóm API như Runtime, ProcessBuilder, Files hoặc System minh họa vì sao việc tham chiếu class tùy ý cần được kiểm soát. Bản thân việc phân giải tên class không đồng nghĩa một hành động đã xảy ra; nhưng nếu biểu thức được phép gọi các method phù hợp, nó có thể kích hoạt hành vi vượt xa mục đích tính toán ban đầu.

Ví dụ an toàn trong bài học:

~~~text
T(java.lang.Math).max(#minimum, #requested)
~~~

Biểu thức chỉ tính giá trị lớn hơn trong hai biến.

Ngược lại, không nên cho một biểu thức do người dùng cung cấp tự chọn class và gọi method tùy ý. Nếu context cho phép truy cập các API hệ thống mạnh, biểu thức có thể thực hiện hành động với quyền của tiến trình ứng dụng.

Hậu quả phụ thuộc quyền của JVM process. Nếu ứng dụng chạy với quyền đọc file cấu hình, truy cập mạng nội bộ hoặc kết nối database, một biểu thức có thể khai thác chính những quyền mà tiến trình đó đang có.

## 5. Type reference chỉ là một phần của bề mặt quyền

Để đánh giá rủi ro, cần xem các capability khác của EvaluationContext:

| Thành phần | Khả năng |
|---|---|
| TypeLocator | Phân giải tên class cho T(...) |
| MethodResolver | Tìm và gọi method trên object hoặc kiểu được tham chiếu |
| ConstructorResolver | Phân giải constructor cho cú pháp new |
| BeanResolver | Lấy bean bằng cú pháp @beanName |
| PropertyAccessor | Đọc hoặc ghi property và field |
| Function/variable | Expose method hoặc object qua biến và function |
| Parser configuration | Điều khiển các tính năng như auto-grow và giới hạn biểu thức |

Chỉ giới hạn TypeLocator chưa đủ nếu root object đã chứa một service có method nhạy cảm. Tương tự, chặn method trên class được tham chiếu không ngăn được việc gọi một method nguy hiểm qua bean reference nếu BeanResolver vẫn expose bean đó.

Một chính sách an toàn phải xác định rõ biểu thức cần những capability nào, sau đó chỉ cấp đúng các capability đó.

## 6. Không dùng StandardEvaluationContext toàn quyền cho expression không tin cậy

StandardEvaluationContext được thiết kế linh hoạt và thường cung cấp các resolver/accessor reflection hữu ích cho expression do ứng dụng kiểm soát. Nó phù hợp với nhiều integration point nội bộ, nhưng không nên mặc định rằng context này là sandbox cho input tùy ý.

Nếu nhận chuỗi SpEL từ request hoặc tenant rồi đánh giá bằng StandardEvaluationContext có resolver mặc định, biểu thức có thể có nhiều quyền hơn một bộ lọc điều kiện đơn giản cần có.

Ví dụ use case có rủi ro:

1. Người dùng nhập một chuỗi expression.
2. Backend parse chuỗi đó.
3. Backend đánh giá bằng context chứa service hoặc object nội bộ.
4. Expression có thể tham chiếu type, gọi method hoặc đọc dữ liệu ngoài dự kiến.
5. Hành động xảy ra với quyền của ứng dụng.

Không giải quyết vấn đề bằng cách chỉ cấm một vài chuỗi class name hoặc method name. Danh sách cấm dễ bỏ sót alias, overload, class khác có khả năng tương tự hoặc đường truy cập gián tiếp.

Hãy bắt đầu từ allowlist: chỉ định rõ tên kiểu, property, method và dữ liệu được phép.

## 7. Dùng TypeLocator allowlist

Nếu một use case thực sự cần type reference, hãy tạo TypeLocator chỉ trả về các class được cho phép.

Ví dụ dưới đây minh họa một allowlist rất nhỏ chỉ cho phép Math:

~~~java
public final class AllowlistTypeLocator implements TypeLocator {

    private final Map<String, Class<?>> allowedTypes = Map.of(
        "Math", Math.class,
        "java.lang.Math", Math.class
    );

    @Override
    public Class<?> findType(String typeName) {
        Class<?> type = allowedTypes.get(typeName);

        if (type == null) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return type;
    }
}
~~~

Đăng ký vào context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowlistTypeLocator());
~~~

Sau đó expression có thể dùng:

~~~text
T(Math).max(#left, #right)
~~~

Tên kiểu không nằm trong allowlist sẽ bị từ chối.

Đây là ví dụ minh họa cho chính sách phân giải kiểu. Trong ứng dụng thật, hãy cân nhắc:

- Chỉ dùng tên đầy đủ để tránh alias không mong muốn.
- Không cho phép package wildcard hoặc prefix quá rộng.
- Không tự động cho phép mọi subclass hoặc implementation của một package.
- Giữ danh sách class ngắn và có chủ sở hữu rõ ràng.
- Kiểm thử cả tên được phép, tên không được phép và tên alias.
- Tránh trả thông tin classpath hoặc cấu trúc nội bộ chi tiết ra client khi từ chối.

Nếu use case không cần T(...), cách đơn giản hơn là không cung cấp TypeLocator có khả năng phân giải class tùy ý.

## 8. Type allowlist chưa giới hạn method

Nếu TypeLocator cho phép java.lang.Math, expression có thể tham chiếu class đó. Nhưng nếu MethodResolver vẫn rộng, biểu thức có thể gọi nhiều method public của Math, không chỉ một method ứng dụng dự định sử dụng.

Vì vậy, có hai lớp chính sách:

1. **Type allowlist:** class nào có thể được tham chiếu?
2. **Method allowlist:** method nào trên class đó có thể được gọi?

Có thể dùng MethodFilter với ReflectiveMethodResolver hoặc custom MethodResolver để giới hạn chữ ký. Ví dụ, ứng dụng chỉ muốn cho phép Math.max với hai đối số số học phù hợp. Khi đó filter cần kiểm tra tên method và kiểu tham số, thay vì chỉ giữ mọi method trên Math.

Nếu thay danh sách MethodResolver, không giữ lại một reflective resolver tổng quát phía sau allowlist resolver, vì resolver sau có thể phân giải lại lời gọi đã bị từ chối.

Hãy nhớ method có thể được gọi qua root object hoặc bean mà không cần T(...). Do đó, method allowlist cần áp dụng cho tất cả đường gọi mà expression có thể sử dụng.

## 9. Constructor và cú pháp new là quyền riêng

SpEL có thể tạo object bằng cú pháp new khi ConstructorResolver và TypeLocator cho phép:

~~~text
new java.math.BigDecimal('12.50')
~~~

Đây là một khả năng riêng với T(...). Chặn type reference không nên được xem là bằng chứng constructor đã bị chặn nếu context vẫn có ConstructorResolver có quyền rộng.

Nếu expression chỉ cần tính toán trên dữ liệu đã có, thường không cần cho phép tạo object tùy ý. Hãy:

- Không cấp constructor resolution nếu use case không cần.
- Chỉ cho phép constructor của các kiểu giá trị nhỏ nếu thật sự cần.
- Tránh cho phép class có constructor khởi tạo tài nguyên hoặc thực hiện hành động.
- Kiểm tra giới hạn kích thước và kiểu của đối số.

TypeLocator, ConstructorResolver và MethodResolver cần được cấu hình đồng bộ. Allowlist type mà không giới hạn constructor hoặc method có thể vẫn mở ra nhiều hành vi ngoài ý muốn.

## 10. Bean reference và property access cũng cần giới hạn

Biểu thức có thể truy cập bean bằng @beanName nếu BeanResolver được cấu hình. Một bean có thể giữ tham chiếu tới service, repository hoặc tài nguyên hệ thống. Vì vậy, một expression không dùng T(...) vẫn có thể thực hiện hành động thông qua bean được expose.

PropertyAccessor cũng quan trọng. Root object hoặc bean có thể chứa property nhạy cảm; việc cho phép đọc hoặc ghi property không phù hợp có thể làm lộ dữ liệu hoặc thay đổi trạng thái.

Nguyên tắc thiết kế:

- Không expose ApplicationContext hoặc BeanFactory cho expression không tin cậy.
- Không đăng ký BeanResolver nếu use case không cần bean reference.
- Dùng DTO nhỏ làm root object, chỉ chứa dữ liệu cần thiết.
- Ưu tiên property access read-only cho biểu thức chỉ đọc.
- Không truyền repository, service quản trị, entity graph lớn hoặc object chứa secret.
- Nếu cần một vài thao tác, expose facade nhỏ với method thuần và allowlist rõ ràng.

## 11. SimpleEvaluationContext cho use case giới hạn

SimpleEvaluationContext được thiết kế cho các trường hợp chỉ cần một phần tính năng SpEL. Nó không cung cấp đầy đủ các khả năng mạnh như type reference, constructor invocation và bean reference của StandardEvaluationContext.

Ví dụ context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Hoặc context cho phép binding đọc/ghi:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Method invocation không được bật rộng rãi mặc định; nếu use case cần method, hãy cấu hình resolver được kiểm soát rõ ràng. Chọn read-only nếu chỉ cần đánh giá điều kiện hoặc lấy giá trị.

SimpleEvaluationContext là lựa chọn phù hợp hơn cho nhiều use case data-binding hạn chế, nhưng vẫn cần xem xét object và accessor được cung cấp. Không nên coi bất kỳ EvaluationContext nào là sandbox tuyệt đối nếu ứng dụng đưa vào các object có quyền mạnh.

## 12. Truyền dữ liệu qua biến thay vì ghép chuỗi expression

Nếu người dùng muốn chọn một giá trị, hãy truyền dữ liệu qua biến và giữ expression cố định.

Ví dụ:

~~~java
Expression expression =
    parser.parseExpression("#amount >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("amount", amount);
context.setVariable("minimum", minimum);
~~~

Cách này tách dữ liệu khỏi cú pháp. Người dùng không thể thay đổi cấu trúc expression chỉ bằng cách đưa ký tự đặc biệt vào giá trị amount.

Nếu cần cho người dùng cấu hình điều kiện, hãy định nghĩa một grammar giới hạn như field/operator/value, sau đó backend chuyển cấu trúc đã xác thực thành logic nội bộ. Một ngôn ngữ điều kiện nhỏ thường dễ giới hạn hơn việc cho người dùng nhập SpEL tổng quát.

Không nối chuỗi đầu vào trực tiếp vào T(...), tên method, property path hoặc phần cú pháp khác.

## 13. Quy trình xây dựng context an toàn

Một quy trình thực tế:

1. Xác định biểu thức có thực sự cần type reference không. Nếu không, không expose khả năng này.
2. Xác định dữ liệu đầu vào và tạo DTO chỉ chứa các property cần thiết.
3. Chọn SimpleEvaluationContext nếu use case chỉ cần data binding và một tập tính năng giới hạn.
4. Nếu phải dùng StandardEvaluationContext, thay TypeLocator mặc định bằng allowlist.
5. Giới hạn MethodResolver theo target type và chữ ký method.
6. Không cấp ConstructorResolver, BeanResolver hoặc write access nếu không cần.
7. Giữ root object và các biến không chứa service hay tài nguyên nhạy cảm.
8. Giới hạn độ dài expression, số lượng biểu thức và chi phí đánh giá ở tầng ứng dụng.
9. Đánh giá với dữ liệu có kiểu rõ ràng và xử lý exception tại ranh giới ứng dụng.
10. Ghi log đủ để chẩn đoán nhưng không ghi secret hoặc toàn bộ dữ liệu nhạy cảm.

Giới hạn độ dài và timeout ở tầng ứng dụng là biện pháp bổ sung. Chúng không thay thế allowlist capability và không biến một expression có quyền rộng thành an toàn.

## 14. Kiểm thử chính sách type reference

Hãy tạo test cho các trường hợp sau:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Tham chiếu T(Math) được allowlist | Phân giải thành công |
| Tham chiếu một class không được allowlist | Bị từ chối bởi TypeLocator |
| Dùng alias không được đăng ký | Bị từ chối |
| Gọi method được allowlist | Thành công với kiểu đối số hợp lệ |
| Gọi method khác trên class được phép | Bị từ chối nếu method allowlist không cho phép |
| Gọi overload có chữ ký khác | Bị từ chối |
| Dùng cú pháp new khi constructor bị giới hạn | Không tạo được instance |
| Tham chiếu bean khi BeanResolver không được cấp | Không phân giải được bean |
| Đọc hoặc ghi property ngoài allowlist | Accessor từ chối |
| Đưa input có ký tự cú pháp vào biến | Giá trị vẫn được xử lý như dữ liệu |
| Dùng context read-only | Không thể ghi property qua context đó |

Ngoài unit test, cần kiểm thử đúng context mà ứng dụng sử dụng ở runtime. Một context test tự tạo có thể khác context do Spring integration point cấu hình.

## 15. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| T(...) không phân giải được | TypeLocator không tìm thấy tên class hoặc class không được allowlist | Kiểm tra tên đầy đủ và danh sách kiểu được phép |
| Class được phân giải nhưng method không gọi được | MethodResolver không cho phép hoặc chữ ký không phù hợp | Kiểm tra method allowlist và kiểu đối số |
| Method không mong muốn vẫn được gọi | Còn reflective resolver tổng quát trong danh sách | Thay toàn bộ resolver list hoặc lọc resolver hiện có |
| Expression dùng new vẫn hoạt động | ConstructorResolver còn quyền | Giới hạn hoặc loại constructor resolution |
| Expression vẫn gọi được service | BeanResolver hoặc root object vẫn expose service | Thu hẹp bean access và root DTO |
| TypeLocator allowlist nhưng dữ liệu vẫn lộ | PropertyAccessor hoặc method khác cung cấp đường truy cập | Xem toàn bộ capability, không chỉ type reference |
| Parse thành công nhưng evaluate thất bại | Type resolution, method resolution hoặc runtime conversion lỗi | Phân biệt lỗi parse và lỗi evaluate |
| Tên class khác alias vẫn được chấp nhận | TypeLocator hỗ trợ import hoặc alias rộng | Chỉ chấp nhận tên canonical được chỉ định |

## 16. Bài tập thực hành

1. Parse T(java.lang.Math).PI và T(java.lang.Math).max(10, 20) trong context nội bộ.
2. Tạo TypeLocator chỉ cho phép Math và kiểm tra một tên class khác bị từ chối.
3. Thử tên ngắn Math và tên đầy đủ java.lang.Math; quyết định alias nào được phép.
4. Thêm MethodFilter chỉ cho phép một chữ ký Math method cụ thể.
5. Thử một method khác trên cùng class và xác nhận method filter từ chối.
6. Tạo SimpleEvaluationContext read-only và quan sát các tính năng type reference không được hỗ trợ.
7. Thử một biểu thức có biến chứa chuỗi ký tự đặc biệt để xác nhận dữ liệu không bị diễn giải thành cú pháp.
8. Viết test xác nhận BeanResolver và ConstructorResolver không được cấp khi use case không cần.

## 17. Checklist trước khi cho phép type reference

- [ ] Expression có thật sự cần T(...) không?
- [ ] Nguồn expression có hoàn toàn tin cậy không?
- [ ] TypeLocator có allowlist tên class chính xác không?
- [ ] Có alias hoặc package import nào mở rộng phạm vi không cần thiết không?
- [ ] MethodResolver có giới hạn method và overload không?
- [ ] ConstructorResolver có bị loại hoặc giới hạn không?
- [ ] BeanResolver có thực sự cần thiết không?
- [ ] Root object và PropertyAccessor có expose dữ liệu nhạy cảm không?
- [ ] Có dùng SimpleEvaluationContext cho use case hạn chế được không?
- [ ] Dữ liệu runtime có được truyền qua biến thay vì ghép chuỗi không?
- [ ] Đã kiểm thử cả type/method được phép và bị từ chối chưa?
- [ ] Có giới hạn chi phí và kích thước expression ở tầng ứng dụng không?

## 18. Kết luận

Toán tử T(...) giúp SpEL tham chiếu class Java và truy cập thành viên static. TypeLocator quyết định class nào có thể được phân giải; MethodResolver và ConstructorResolver quyết định những hành vi tiếp theo có thể được gọi hoặc khởi tạo. Nếu cho phép type tùy ý trong expression không tin cậy, ứng dụng có thể vô tình expose các API có quyền đọc file, truy cập mạng, tạo process hoặc thay đổi trạng thái hệ thống. Hãy ưu tiên không cho phép type reference khi không cần, dùng TypeLocator allowlist nếu bắt buộc, giới hạn đồng thời method/constructor/bean/property access và truyền dữ liệu qua biến trong context hẹp.