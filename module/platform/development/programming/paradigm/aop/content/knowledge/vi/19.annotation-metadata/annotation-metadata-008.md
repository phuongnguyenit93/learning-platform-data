# Kiểm tra annotation thiếu, mâu thuẫn hoặc đặt sai chỗ trong AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, annotation cho phép method, type hoặc tham số **khai báo ý định** liên quan đến một concern cắt ngang: quan sát, ghi audit, kiểm soát quyền, retry, timeout, cache hoặc validation. Nhưng việc có annotation trong source **không có nghĩa hành vi đã được thực thi**. Một hệ thống dùng annotation-driven AOP có thể gặp ba loại lỗi đặc biệt nguy hiểm:

1. **Thiếu:** nơi cần annotation bắt buộc lại không có, hoặc annotation có retention khiến bộ đọc metadata không tìm thấy.
2. **Mâu thuẫn:** hai annotation chỉ thị hành vi đối nghịch, giá trị thuộc tính không hợp lệ, hoặc nhiều policy không thể cùng thỏa.
3. **Đặt sai chỗ:** annotation hợp lệ theo cú pháp Java nhưng nằm trên member hoặc loại join point **không được hệ thống interception hiện tại quan sát**, hoặc được đặt ở implementation trong khi resolver chỉ tra cứu interface.

Ví dụ một method **@Observe** bị thiếu có thể dẫn tới không có metric; một method vừa có **@Observe** vừa **@IgnoreObserve** có thể được chạy tùy cách xử lý mơ hồ; một **@RequiresPermission** chỉ gắn trên method mà runtime không intercept có thể khiến developer tin sai rằng quyền truy cập đã được bảo vệ.

**Mục tiêu bài:** biết định nghĩa policy metadata trước khi kiểm tra; nhận biết lỗi cú pháp, lỗi semantic placement và lỗi interception coverage; dùng cơ chế build/startup validation; phân biệt interface annotation với implementation annotation; xác minh kết quả bằng Java 17 và một bộ test có oracle độc lập.

Bài nằm trong chủ đề **Annotation và siêu dữ liệu** và chỉ trình bày kiến thức **AOP cơ bản/nâng cao nói chung**, không dựa trên một bộ framework cụ thể. Ví dụ Java 17 là một **policy validator đọc metadata bằng reflection**; nó không phải bytecode weaver và không thay thế các test chạy advice thật.

## 1. Phân biệt annotation, pointcut và enforcement

Các khái niệm:
- **Join point** là điểm chương trình có thể can thiệp, ví dụ method call hoặc method execution nếu mô hình hỗ trợ.
- **Pointcut** là điều kiện chọn join point, có thể dựa vào method/type annotation.
- **Advice** là hành vi before, after, around hay dạng khác được thực thi tại join point đã chọn.
- **Aspect** nhóm pointcut/advice và chính sách áp dụng.
- **Weaving/interception** đưa advice vào đường chạy bằng compile-time, post-compile, load-time hoặc proxy/wrapper.
- **Annotation metadata** chỉ thể hiện declaration và attributes; không tự gọi advice.
- **Metadata resolver** quyết định annotation nào **có hiệu lực** khi các khai báo nằm trên interface, implementation, superclass, type hoặc meta-annotation.
- **Validator** kiểm tra completeness, conflicts, placement, retention và cấu hình trước hoặc trong khi ứng dụng chạy.

~~~text
Source annotation declares intention
                |
                v
       Annotation validator
        /              \
   Invalid             Valid
       |                 |
  Error/Warning   Effective metadata lookup
                         |
                         v
                 Pointcut selection
                         |
                         v
             Does interception occur?
                  /            \
                 No            Yes
                 |              |
          No advice event    Advice + target
~~~

Điều quan trọng là **không đánh đồng ba câu hỏi**: metadata có đúng không, join point có được intercept không, và business/security contract có được giữ đúng khi chạy không.

Một annotation hoàn hảo vẫn có thể vô hiệu nếu lời gọi bypass proxy. Ngược lại, một advice có thể chạy trên một method không annotate nếu pointcut lựa chọn bằng signature hoặc package. Hai điều này đều phụ thuộc vào hợp đồng AOP.

## 2. Phân loại lỗi bằng một bảng kiểm chứng

| Loại | Ví dụ | Cần kiểm gì? |
| --- | --- | --- |
| Thiếu bắt buộc | Public API operation chưa có @Observe | Interface/type nào thuộc rule, opt-out có được phép? |
| Mâu thuẫn trực tiếp | Cả @Observe và @IgnoreObserve | Mutually exclusive hay có precedence? |
| Giá trị sai | @Observe("") | Operation label có nonblank, hợp lệ? |
| Đặt sai ElementType | Annotation METHOD đặt trên field | Compiler kiểm @Target |
| Đặt sai AOP boundary | Annotation ở private helper, proxy chỉ thấy interface | Method có thực sự instrument được không? |
| Sai nguồn metadata | Interface không có marker, implementation có | Resolver đọc nơi nào? |
| Sai retention | SOURCE annotation được runtime reflection tìm | @Retention và pha đọc |
| Conflict type/method | Type yêu cầu audit, method muốn bỏ | Override có được phép? |
| Conflict giữa aspect | Hai advice có precedence cycle | Kiểm graph ưu tiên |
| Repeatable/composed | Hai role annotations hoặc meta-annotation | Resolver hiểu nhiều marker ra sao? |
| Nguy cơ động | Marker security nhưng direct call bypass | Integration test actual enforcement |

**Java compiler không tự hiểu mọi ràng buộc AOP.** Compiler bắt được annotation đặt lên loại phần tử mà @Target cấm; nhưng nó không biết một team có cấm @Observe trên private method hay không. Đây là chính sách kiến trúc phải được mô tả thêm.

## 3. Muốn tìm annotation thiếu phải xác định “bắt buộc ở đâu”

Một lỗi phổ biến là quét mọi method rồi báo thiếu annotation ở mọi getter, helper, generated method và function nội bộ. Khi đó validator tạo false positives, khiến người phát triển tắt luôn rule.

Thay vào đó, viết một **contract có thể kiểm chứng**. Ví dụ:
- Những interface đánh dấu **@CheckedService** chứa những public operations cần quyết định policy observation.
- Mỗi method được **khai báo trong interface đó** phải có **chính xác một** trong hai lựa chọn: @Observe hoặc @IgnoreObserve.
- @IgnoreObserve chỉ dành cho một concern quan sát **không bắt buộc**, và phải có reason.
- Nếu có @Observe, operation name không được rỗng.
- Cả hai annotation trên cùng method là lỗi; không chọn annotation “đứng trước” trong source.
- Implementation-only annotations không tự được đọc bởi interface-only resolver.
- Method có annotation không nằm trong interface được kiểm như một trường hợp **có thể đặt ngoài phạm vi**.

Phạm vi trên được chọn vì mục tiêu là xây validator **minh họa**. Một hệ thống thực tế có thể chọn mọi exported operation theo class, package, module, annotation khác hoặc tập static join points mà weaver nhận diện được.

### 3.1 Có phải mọi annotation đều bắt buộc?

Không. Với logging và metrics, policy có thể opt-in, chỉ annotate những method cần thiết. Nhưng nếu module tuyên bố “mọi public operation phải audit”, thì missing annotation là vi phạm của một **invariant bắt buộc**.

Với authorization, cần thận trọng: **đừng cho một opt-out dễ dàng** làm mất kiểm tra quyền. Có thể dùng fail-closed khi cấu hình thiếu/mâu thuẫn và bảo vệ tại ranh giới đáng tin thay vì phụ thuộc duy nhất vào annotation.

### 3.2 Không dùng việc thiếu log để kết luận annotation thiếu

Không có log cũng có thể do:
- Method không hề chạy.
- Method có chạy nhưng không qua proxy.
- Around advice ngoài short-circuit trước khi đến advice bên trong.
- Advice đang chạy nhưng sink/log exporter bị filter hoặc lỗi.
- Annotation ở interface, trong khi resolver lại đọc implementation.
- Exception path không đi qua after-returning advice.

Muốn chẩn đoán, tách **declaration test**, **metadata lookup test**, **interception coverage test** và **runtime behavior test**.

## 4. @Target: cú pháp đúng chưa đủ chứng minh vị trí đúng

Java định nghĩa annotation bằng **@interface**. Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Observe {
    String value();
}
~~~

Đây là mảnh khai báo, không có hàm main. @Target(METHOD) quy định annotation được dùng trên **method declaration**. Nó không nói method phải public hay thuộc interface.

Một số ElementType khác: **TYPE**, **FIELD**, **PARAMETER**, **CONSTRUCTOR**, **ANNOTATION_TYPE**, **TYPE_USE**. Chọn đúng loại tùy dữ liệu pointcut/resolver có thể quan sát.

Nếu đặt annotation chỉ cho METHOD lên một field, compiler sẽ từ chối. Nhưng ví dụ sau **có thể hợp cú pháp**:

~~~java
@Observe("internal")
private void helper() {
    // helper không được expose qua interface proxy
}
~~~

Nếu project dùng **JDK interface proxy**, lời gọi tới private helper **không xuất hiện như một lời gọi method trên proxy interface**. Vì vậy annotation ở đây **đặt sai chỗ theo cơ chế AOP đã chọn**, dù không phải lỗi @Target.

Ngược lại, một bộ weaver trực tiếp lên method executions có thể có tập join point khác. Không khẳng định mọi cơ chế AOP đều không thể can thiệp private method. Validator phải được viết **theo execution model thực tế**, không theo giả định mơ hồ.

### 4.1 Type-level và method-level khác nhau

Một annotation đặt trên class không tự trở thành annotation của mọi method. Muốn type-level marker tạo default policy cho tất cả method, resolver phải có **quy tắc tường minh**:
- Bao gồm public declared methods hay cả inherited methods?
- Có loại static/bridge/synthetic methods không?
- Method-level opt-out có được phép không?
- Nếu superclass/interface và concrete type xung đột, bên nào thắng?

Tương tự, annotation trên parameter hoặc type-use không tự hiện diện trên Method.getAnnotation.

## 5. @Retention: annotation có thể biến mất khỏi nơi runtime đọc

Java hỗ trợ:
- **RetentionPolicy.SOURCE:** chỉ cần ở source; không lưu trong classfile theo chính sách retention.
- **RetentionPolicy.CLASS:** được lưu trong classfile, nhưng không có hợp đồng runtime reflection như RUNTIME.
- **RetentionPolicy.RUNTIME:** có thể đọc bằng reflection trên phần tử tương ứng khi chạy.

Nếu một runtime interceptor tra **Method.getAnnotation(Observe.class)**, annotation phải có **RUNTIME retention**. Nếu kiến trúc chỉ kiểm bằng source processor, SOURCE có thể là lựa chọn phù hợp.

Tuy nhiên, chọn RUNTIME **không tự sửa** sai khác giữa interface/implementation, không làm proxy intercept target raw calls và không bảo đảm policy không bị bypass.

Bộ kiểm tra nên xác định:
1. Annotation type có retention mong đợi không?
2. Công cụ đọc source, classfile hay runtime element?
3. Nếu runtime, đang đọc đúng Method/Type/Parameter chưa?
4. Nếu có bytecode transformation/introduction, metadata thực tế đã được giữ/biến đổi thế nào?
5. Reflection test có kiểm đúng element sau compile không?

## 6. Interface method khác implementation method

Một ví dụ kinh điển:

~~~java
interface BillingApi {
    @Observe("charge")
    String charge(String id);
}

class BillingImpl implements BillingApi {
    public String charge(String id) {
        return "charged:" + id;
    }
}
~~~

Đây là mảnh minh họa cần @Observe đã khai báo. Annotation nằm trên **interface method**. Khi gọi **BillingApi.class.getMethod(...).getAnnotation(Observe.class)**, ta có thể thấy annotation; nhưng **BillingImpl.class.getMethod(...).getAnnotation(Observe.class)** không tự chứa annotation method từ interface.

Java **@Inherited** không giải quyết điều này. @Inherited liên quan class-level annotation được kế thừa qua superclass theo API phù hợp; nó **không tự sao chép method annotations**, và không thực hiện interface-to-implementation annotation inheritance.

Nếu AOP proxy cung cấp interface Method cho interceptor, một resolver đọc interface là hợp lý. Nếu bộ weaver chọn implementation method execution, resolver lại cần tìm metadata từ implementation hoặc theo chính sách fallback sang interface. **Không có resolution order dùng chung cho mọi bộ AOP.**

### 6.1 Xung đột giữa các nguồn metadata

Giả sử:
- Interface method có @Observe("transfer").
- Implementation method có @IgnoreObserve.
- Class có một annotation mặc định quan sát.

Những nguồn đó **không tự hòa giải**. Cần quyết định:
- Một marker explicit trên implementation có được override interface contract?
- Nếu có, opt-out có được phép với concern bảo mật?
- Nếu nhiều interfaces khai cùng signature nhưng policy khác, có reject không?
- Một method override từ superclass có được “kế thừa” policy theo resolver tự viết không?
- Với overloaded methods, resolver có so đúng parameter types không?

Một phương án an toàn với invariant bắt buộc là **fail fast** khi khai báo trái nhau, thay vì dựa vào thứ tự reflection để chọn ngẫu nhiên.

## 7. Annotation conflict là một quan hệ chính sách

Hai annotation khác loại cùng đặt lên một method có thể hợp lệ cú pháp:

~~~java
@Observe("refund")
@IgnoreObserve(reason = "manual")
String refund();
~~~

Đây là mảnh minh họa. Nếu policy quy định một cái phải observe và cái kia phải skip, ta có một **semantic conflict**.

Nhưng **không phải mọi cặp annotation đều xung đột**. @Observed và @Measured có thể là hai concern bổ sung. Validator cần có **compatibility matrix**:

| Cặp/quan hệ | Có thể hợp lệ? | Câu hỏi cần trả lời |
| --- | --- | --- |
| Observe + IgnoreObserve | Không nếu mutually exclusive | Từ chối hay có override hợp lệ? |
| Observe + Measured | Có | Thứ tự advice/đơn vị đếm là gì? |
| Retry + Transaction | Có điều kiện | Mỗi attempt có transaction riêng không? |
| Retry + non-idempotent mutation | Rủi ro | Dedup/idempotency và budget? |
| Cache + Authorization | Có điều kiện | Authorization có trước private cache hit? |
| Type policy + method policy | Có điều kiện | Rule override có được phép? |
| Interface policy + impl policy | Có điều kiện | Nguồn metadata nào ưu tiên? |
| Hai precedence edges ngược nhau | Không nếu cả hai bắt buộc | Có cycle không? |

Một conflict checker có thể cần kết hợp:
- Kiểm cặp mutually exclusive.
- Kiểm attribute values/uniqueness.
- Kiểm graph precedence của nhiều aspects.
- Kiểm security restrictions và những combination bị cấm.

**Không dùng thứ tự annotation trong source làm thứ tự advice.** Thứ tự advice do precedence/weaving model quyết định, và cần test success, error, short-circuit, retry.

## 8. Ví dụ Java 17 hoàn chỉnh: validator thiếu, xung đột, sai chỗ

Chương trình **AnnotationRuleDemo.java** dùng Java reflection và policy riêng. Nó có một interface hợp lệ và một interface có lỗi:
- **ARC001:** method trong contract thiếu cả Observe lẫn IgnoreObserve.
- **ARC002:** hai annotation mutually exclusive cùng tồn tại.
- **ARC003:** Observe có operation rỗng.
- **ARC004:** annotation trên implementation method **không thuộc interface** đang được validate.
- **ARC005:** annotation chỉ trên implementation không thấy được với **interface-only metadata resolver**.

ARC001–ARC004 là **ERROR** theo policy ví dụ; ARC005 là **WARNING** để yêu cầu sửa/kiểm tra. Với security hoặc audit bắt buộc, một implementation-only annotation không có hiệu lực cũng có thể cần được nâng thành ERROR.

Mã được **biên dịch và thực thi bằng JDK với --release 17**, không phụ thuộc thư viện ngoài. Lưu thành **AnnotationRuleDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class AnnotationRuleDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface CheckedService {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observe { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface IgnoreObserve { String reason(); }

    @CheckedService
    interface HealthyApi {
        @Observe("ping") String ping();
        @IgnoreObserve(reason = "low value") String health();
    }

    static final class HealthyImpl implements HealthyApi {
        public String ping() { return "pong"; }
        public String health() { return "ok"; }
    }

    @CheckedService
    interface BillingApi {
        @Observe("charge") String charge(String id);
        String status();
        @Observe("refund") @IgnoreObserve(reason = "manual") String refund();
        @Observe("") String report();
        @IgnoreObserve(reason = "low value") String health();
    }

    static final class BillingImpl implements BillingApi {
        public String charge(String id) { return "charged:" + id; }
        @Observe("status") public String status() { return "ready"; }
        public String refund() { return "refunded"; }
        public String report() { return "report"; }
        public String health() { return "ok"; }
        @Observe("internal") private String helper() { return "secret"; }
    }

    static List<String> validate(Class<?> api, Class<?> implementation) {
        List<String> issues = new ArrayList<>();
        if (!api.isAnnotationPresent(CheckedService.class)) {
            issues.add("ERROR ARC000 " + api.getSimpleName()
                    + ": missing @CheckedService");
        }

        Method[] interfaceMethods = api.getDeclaredMethods();
        Arrays.sort(interfaceMethods, Comparator.comparing(Method::getName));
        for (Method method : interfaceMethods) {
            Observe observed = method.getAnnotation(Observe.class);
            IgnoreObserve ignored =
                    method.getAnnotation(IgnoreObserve.class);
            if (observed == null && ignored == null) {
                issues.add("ERROR ARC001 " + method.getName()
                        + ": missing @Observe or @IgnoreObserve");
            } else if (observed != null && ignored != null) {
                issues.add("ERROR ARC002 " + method.getName()
                        + ": conflicting @Observe and @IgnoreObserve");
            } else if (observed != null && observed.value().isBlank()) {
                issues.add("ERROR ARC003 " + method.getName()
                        + ": blank operation");
            }
        }

        for (Method implMethod : implementation.getDeclaredMethods()) {
            Observe mark = implMethod.getAnnotation(Observe.class);
            if (mark == null) continue;
            try {
                Method contract = api.getMethod(
                        implMethod.getName(), implMethod.getParameterTypes());
                if (!contract.isAnnotationPresent(Observe.class)) {
                    issues.add("WARNING ARC005 " + implMethod.getName()
                            + ": implementation-only @Observe"
                            + " invisible to interface-only resolver");
                }
            } catch (NoSuchMethodException error) {
                issues.add("ERROR ARC004 " + implMethod.getName()
                        + ": @Observe on method absent from interface");
            }
        }
        issues.sort(Comparator.naturalOrder());
        return issues;
    }

    static void scenario(String name, Class<?> api, Class<?> implementation) {
        List<String> issues = validate(api, implementation);
        System.out.println("CASE " + name);
        issues.forEach(System.out::println);
        long errors = issues.stream()
                .filter(s -> s.startsWith("ERROR")).count();
        long warnings = issues.stream()
                .filter(s -> s.startsWith("WARNING")).count();
        System.out.println("RESULT " + (errors == 0 ? "PASS" : "FAIL")
                + " errors=" + errors + " warnings=" + warnings);
    }

    public static void main(String[] args) {
        scenario("valid", HealthyApi.class, HealthyImpl.class);
        scenario("invalid", BillingApi.class, BillingImpl.class);
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+**:

~~~bash
javac --release 17 AnnotationRuleDemo.java
java AnnotationRuleDemo
~~~

Stdout đã được kiểm chứng:

~~~text
CASE valid
RESULT PASS errors=0 warnings=0
CASE invalid
ERROR ARC001 status: missing @Observe or @IgnoreObserve
ERROR ARC002 refund: conflicting @Observe and @IgnoreObserve
ERROR ARC003 report: blank operation
ERROR ARC004 helper: @Observe on method absent from interface
WARNING ARC005 status: implementation-only @Observe invisible to interface-only resolver
RESULT FAIL errors=4 warnings=1
~~~

### 8.1 Vì sao HealthyApi PASS?

**ping()** có @Observe, **health()** có @IgnoreObserve với reason. Cả hai phù hợp rule phải chọn một trong hai. Implementation không có annotation không hiệu lực bị kiểm tra. Kết quả là **0 errors, 0 warnings**.

Nếu một concern **bắt buộc**, không nên lấy opt-out ví dụ làm chính sách cho phép bỏ kiểm tra quyền. Đây chỉ là mô hình cho observability có quy định bỏ qua rõ.

### 8.2 ARC001: status thiếu trên interface

**BillingApi.status()** không khai báo lựa chọn nào, nên vi phạm contract được @CheckedService đánh dấu. Có @Observe trên **BillingImpl.status()** cũng **không sửa** sự thiếu ở interface nếu resolver chỉ đọc interface method.

Điều này giải thích vì sao cùng status có cả ARC001 và ARC005: đó là hai bằng chứng khác nhau của **thiếu contract annotation** và **implementation-only intent không hiển thị**.

### 8.3 ARC002: refund mâu thuẫn

**BillingApi.refund()** vừa @Observe vừa @IgnoreObserve. Hai marker đều hợp lệ với Java METHOD target, nhưng mâu thuẫn theo policy ứng dụng. Không được chọn một cách tình cờ annotation nằm trước trong source.

### 8.4 ARC003: report có annotation nhưng cấu hình sai

**BillingApi.report()** có @Observe("") nên không bị thiếu marker, song operation label không hợp lệ. Kiểm giá trị khác kiểm sự hiện diện. Trong thực tế, còn cần giới hạn độ dài label, định dạng, cardinality và trường chứa dữ liệu nhạy cảm.

### 8.5 ARC004: helper được đánh dấu ngoài phạm vi

**BillingImpl.helper()** là private và không có method tương ứng trên interface. Trong ví dụ **interface-only** đó là sai vị trí. Với execution weaving có khả năng nhìn các method khác, rule có thể cần thay đổi; ARC004 là luật của **mô hình kiểm cụ thể**, không phải điều cấm của Java.

### 8.6 ARC005: implementation-only marker

Implementation method status có @Observe, nhưng interface method không có. Một interceptor chỉ đọc **Method từ interface proxy** sẽ không thấy marker implementation. Warning cần dẫn người phát triển tới annotation placement policy hoặc metadata resolver hỗ trợ hợp đồng khác.

### 8.7 Phạm vi mà ví dụ chưa chứng minh

Đây là **validator metadata bằng reflection**, không tạo proxy và không weave method execution:
- Nó chỉ kiểm **các method được khai báo trong interface cụ thể**, không quét toàn ứng dụng.
- Nó chưa kiểm inherited interface methods hoặc generic bridge methods.
- Nó chưa kiểm reason rỗng của @IgnoreObserve; có thể bổ sung khi policy yêu cầu.
- Nó chưa chứng minh aspect được đăng ký/pointcut được áp dụng runtime.
- Nó không kiểm security principal, token hoặc tenant identity.

**PASS từ validator không phải bằng chứng đã thực thi advice.** Muốn chứng minh behavior, tạo integration test gọi method qua boundary được instrument và assert hit count, return value, exception, short-circuit và đường bypass.

## 9. Kiểm tra ở compile-time, startup và runtime

Có ba nhóm kiểm tra bổ sung:

| Pha | Kiểm gì tốt? | Không tự chứng minh |
| --- | --- | --- |
| **Compile-time/source** | @Target, @Retention policy, types, attributes, contract completeness qua processor/analyzer | Target runtime được chọn chính xác |
| **Post-compile/bytecode** | Classfile annotations, generated methods, introductions, cấu trúc sau weaving | Mọi request được phân quyền |
| **Startup/reflection** | Effective runtime metadata, conflict interface/implementation, configuration | Mọi lời gọi qua proxy |
| **Runtime integration** | Advice có chạy đúng khi join point xảy ra, result/error/cancellation | Cấu trúc toàn bộ artifact nếu coverage test chưa đủ |

Một annotation processor có thể kiểm một số annotation declarations ở compile-time và phát warning/error. Nhưng processor **không tự chuyển mọi method body thành around advice**. Runtime weaving hoặc proxy là một trách nhiệm riêng.

### 9.1 Fail fast theo mức nghiêm trọng

Với required metadata và vi phạm chắc chắn, nên phát **ERROR** ở build hoặc khởi động. Với một dấu hiệu có thể vẫn hợp lệ theo model, phát **WARNING** kèm scope rõ ràng.

Không âm thầm bỏ qua lỗi vì hệ thống “vẫn chạy” trong môi trường thử nghiệm. Nếu validator bắt buộc bị tắt, trạng thái đúng là **chưa được kiểm tra**, không phải PASS.

### 9.2 Diagnostic có thể hành động

Một thông báo tốt có:
- ID ổn định và severity.
- Interface/type/method signature.
- Annotation thấy được và annotation được yêu cầu.
- Ranh giới instrumentation/resolution.
- Hướng sửa hoặc quy trình xin ngoại lệ.

Ví dụ:

~~~text
ERROR ARC001 BillingApi.status(): no observation choice
Observed: no @Observe and no @IgnoreObserve on interface method
Policy: @CheckedService requires exactly one choice per method
Suggestion: annotate interface method or change policy explicitly
~~~

Đây là **mẫu diagnostic giải thích**, không phải stdout thực tế của demo.

## 10. @Inherited, @Repeatable, meta-annotation và override

### 10.1 @Inherited không áp lên method overrides như nhiều người tưởng

Java @Inherited chủ yếu liên quan class-level annotations được truy vấn qua superclass hierarchy. Nó không khiến annotation method ở interface tự xuất hiện trên implementation method.

Nếu muốn một annotation được coi là kế thừa ở method, cần **metadata resolver riêng**, test superclass, interface, override và xung đột.

### 10.2 @Repeatable

Khi annotation type có @Repeatable và container phù hợp, một element có thể chứa nhiều declarations cùng loại. Một resolver muốn lấy tất cả thường dùng **getAnnotationsByType**.

Không được mặc định repeatable annotation nghĩa advice tự chạy nhiều lần. Hợp đồng có thể là một tập policy/labels, còn advice chỉ chạy một lần.

Các điều cần kiểm:
- Duplicate labels có hợp lệ không?
- Hai permissions kết hợp AND hay OR?
- Nếu repeatable xung đột với type-level default, precedence ra sao?
- Code có đang đọc getAnnotation rồi bỏ sót phần tử trong container không?

### 10.3 Meta-annotation

Một annotation type có thể được trang trí bằng annotation khác; Java reflection **không tự** chuyển mọi meta-annotation thành direct annotation trên method sử dụng nó.

Nếu hỗ trợ composed annotations, resolver phải duyệt đồ thị meta-annotation, chống recursion/cycle, xử lý attribute aliases, trùng metadata và precedence. Không xây resolver theo giả định “có annotation ở đâu đó trong graph thì như đặt trực tiếp”.

## 11. Nhiều aspect và policy xung đột

Method có thể đồng thời được quan sát, ghi audit và đo thời gian mà **không hề mâu thuẫn**. Vấn đề là **ngữ nghĩa kết hợp**:
- Advice nào bao ngoài advice nào?
- Nếu cache short-circuit, metric/audit bên trong có được gọi không?
- Nếu Retry gọi continuation nhiều lần, ta đếm request hay attempts?
- Nếu security advice được đặt bên trong một cache trả private data, có bỏ qua authorization bắt buộc không?
- Nếu một advice dịch ngoại lệ, audit có thấy kết quả cuối hay exception gốc?
- Nếu một method trả CompletionStage, success event được ghi khi trả stage hay khi stage hoàn tất?

Một graph precedence có cạnh A→B, B→C, C→A là **bất khả thi** nếu tất cả cạnh đều có nghĩa bắt buộc A bao ngoài B. Validator architecture có thể phát hiện cycle trước khi chạy.

Nhưng **thứ tự annotation xuất hiện ở source không đồng nghĩa thứ tự advice**; chỉ dùng policy công bố và kiểm thử execution order.

## 12. Annotation đúng nhưng không được intercept

Với proxy-based AOP:
- Gọi qua proxy có thể kích hoạt handler/advice.
- Gọi raw target có thể **bypass proxy**.
- Trong delegation model, self-invocation trên target có thể không đi qua proxy.
- Method không xuất hiện trên proxy interface không thể được dispatch như interface method tương ứng.
- Các cơ chế weaving trực tiếp có tập join point khác.

Vì vậy **wrong placement** không chỉ là @Target sai mà còn là **annotation đặt trên một điểm không thể được cơ chế áp dụng thấy**.

### 12.1 Cách phân tích khi advice không chạy

~~~text
Did the method actually execute?
       |
       +-- No --> no join point occurrence, no advice expected
       |
       +-- Yes --> did the call cross an interception boundary?
                       |
                       +-- No --> coverage/bypass issue
                       |
                       +-- Yes --> did resolver see effective metadata?
                                       |
                                       +-- No --> retention/placement problem
                                       |
                                       +-- Yes --> did pointcut select it?
                                                       |
                                                       +-- No --> matcher problem
                                                       +-- Yes --> advice order,
                                                                  short-circuit,
                                                                  error/log filtering
~~~

Không sửa annotation một cách mù quáng khi thiếu log. Có thể lỗi nằm ở call path, pointcut hoặc telemetry, không phải annotation source.

## 13. Các ca kiểm thử cần có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Required interface method được annotate đúng | PASS |
| Required method không có marker | Missing ERROR |
| Observe và IgnoreObserve cùng method | Conflict ERROR |
| Operation value rỗng hoặc invalid | Attribute ERROR |
| Marker trên private method ngoài proxy interface | Placement violation theo policy |
| Implementation-only annotation, resolver interface-only | Missing + warning/error về mismatch |
| @Target METHOD đặt trên FIELD | Compiler error |
| SOURCE retention nhưng runtime reflection cần marker | Không visible ở runtime |
| @Inherited trên class vs method override | Không suy inheritance sai |
| Two repeatable annotations | Resolver lấy đủ values |
| Meta-annotation | Chỉ effective nếu resolver hỗ trợ |
| Interface và implementation annotations khác nhau | Apply documented conflict policy |
| Method overloaded | Phân biệt signature, không chỉ tên |
| Bridge/synthetic methods | Đúng contract scope, không báo thiếu giả |
| Bytecode introduction thêm member | Kiểm đúng pre/post-weave representation |
| Direct call bypass proxy | Không nhận nhầm metadata false |
| Self-invocation trên target | Test actual coverage |
| Exception path | Advice giữ nguyên lỗi nghiệp vụ |
| Cache hit và short-circuit | Concern bắt buộc không bị bypass |
| Async completion | Không nhầm method return với completion |
| Concurrent invocations | Không dùng shared mutable currentAnnotation/currentUser |
| Validator bị skip | Không báo PASS giả |

Từng fixture nên có **oracle tường minh**: ID lỗi, severity, vị trí, số lần advice hoặc behavior cần có. Tránh lấy expected bằng cách gọi lại chính validator đang được test.

### 13.1 Test cả trường hợp hợp lệ

Một validator quá rộng có thể báo thiếu trên mọi helper và chặn cả những trường hợp được policy cho phép. Vì vậy luôn có:
- **Positive fixtures:** đủ metadata, không conflict, placement đúng.
- **Negative fixtures:** thiếu/mâu thuẫn/sai vị trí.
- **Boundary fixtures:** inheritance, repeatable, overloaded, generated methods, interface/implementation mismatch.
- **Behavior tests:** gọi qua proxy/weaving thực, quan sát advice và kiểm return/error.
- **Security tests:** mọi đường cần bảo vệ được enforcement, không chỉ có annotation.

## 14. Cảnh báo, lỗi và quản lý policy trong CI

| Phát hiện | Mức phù hợp |
| --- | --- |
| Thiếu annotation required cho bảo mật | ERROR, fail closed |
| Conflict trực tiếp giữa các lựa chọn bắt buộc | ERROR |
| Operation label không hợp lệ | ERROR |
| Annotation implementation-only khi resolver interface-only | WARNING hoặc ERROR nếu bắt buộc |
| Annotation legacy cần thay dần | WARNING |
| Annotation ở vị trí ngoài capability đã biết | ERROR nếu intent chắc chắn không thể áp dụng |
| Có khả năng false positive | Xem lại rule, không tự fail toàn bộ |

Trong CI:
1. Compiler kiểm syntax/@Target.
2. Source/type analyzer kiểm completeness và các ràng buộc tĩnh.
3. Weaving/instrumentation tạo cấu trúc thực nếu được dùng.
4. Validator đọc **effective metadata** sau biến đổi khi contract cần.
5. Integration tests xác minh **thực thi advice**.
6. Không đóng gói artifact khi mandatory checks fail.

Kiểm **clean** và **incremental build**, đặc biệt khi metadata đến từ generated sources, bridge methods hoặc structural introductions. Kết quả PASS khi checker bị skip **không hợp lệ** như bằng chứng kiến trúc.

## 15. Bảo mật và dữ liệu nhạy cảm

Một annotation tên @RequiresPermission không tự thực thi authorization. Nếu system cho phép bỏ qua một required marker hoặc một outer cache có thể short-circuit trước kiểm quyền, có thể tạo đường bypass.

Biện pháp:
- Giữ ranh giới kiểm quyền **đáng tin**, không phụ thuộc duy nhất vào metadata tự nguyện.
- Required annotation thiếu hoặc conflict phải fail theo policy.
- Không dùng logging guard để skip security/audit bắt buộc.
- Kiểm identity từ nguồn đã xác thực, không dùng trace ID hoặc tenant string tự khai làm authority.
- Không log raw args, tokens, password, PII hoặc payload chỉ để chẩn đoán validator.
- Với async, phân biệt return stage với successful completion và quyền còn hiệu lực lúc execute.
- Test cả direct/proxy calls, cache-hit, denied requests, exception và retry.

Validator bảo vệ **chất lượng cấu hình**; runtime checks bảo vệ **hành vi thực tế**.

## 16. Checklist kiểm tra annotation AOP

- [ ] Xác định chính xác API/type/method thuộc phạm vi bắt buộc.
- [ ] Định nghĩa missing policy và opt-out có được phép không.
- [ ] Định nghĩa các cặp mutually exclusive và precedence có thể chấp nhận.
- [ ] Kiểm attributes bắt buộc như operation nonblank và giới hạn dữ liệu.
- [ ] Đặt @Target đúng loại element; bổ sung semantic placement rules.
- [ ] Chọn @Retention theo nơi metadata sẽ được đọc.
- [ ] Quy định interface/implementation/superclass/type metadata resolution.
- [ ] Không dựa vào @Inherited cho method/interface annotations.
- [ ] Kiểm repeatable/composed annotations khi resolver hỗ trợ.
- [ ] Biết interception model: call, execution, proxy, weaving.
- [ ] Kiểm annotated private/static/helper/constructor có thật được instrument không.
- [ ] Báo diagnostic có ID, severity, method/signature và gợi ý.
- [ ] Test đầy đủ valid, missing, conflicting, misplaced và blank value.
- [ ] Test overload, override, inherited interface, bridge/generated methods.
- [ ] Test direct call, self-invocation, short-circuit, exception và async.
- [ ] Phân biệt metadata validation với runtime enforcement.
- [ ] Không cho annotation opt-out bỏ security/audit bắt buộc.
- [ ] Kiểm validator không bị skip trong CI; clean/incremental nhất quán.
- [ ] Đo overhead/caching của metadata resolver khi áp dụng rộng.
- [ ] Không giữ request-specific state trong shared aspect hoặc metadata cache.

## 17. Những nhầm lẫn thường gặp

1. **Có @Target(METHOD) nghĩa method phải public.** Sai, private method cũng là method.
2. **Có annotation là advice tự chạy.** Sai, cần pointcut và weaving/interception.
3. **RUNTIME retention nghĩa mọi method invocation được chọn.** Không, chỉ giúp reflection thấy marker ở element tương ứng.
4. **@Inherited tự áp dụng cho method override trong interface.** Không.
5. **Annotation ở interface tự xuất hiện trên implementation method.** Không.
6. **Một marker implementation-only luôn được JDK interface proxy đọc.** Không.
7. **Hai annotation trên method luôn mâu thuẫn.** Chỉ mâu thuẫn theo policy tương ứng.
8. **Java compiler tự bắt mọi semantic conflict.** Không, compiler chủ yếu kiểm quy tắc ngôn ngữ.
9. **Có Ignore marker là hợp lệ cho mọi concern.** Không với security/audit bắt buộc.
10. **Không có log đồng nghĩa method không có annotation.** Có thể coverage/pointcut/log sink sai.
11. **Bộ kiểm tra reflection là bytecode weaver.** Không.
12. **Một lần PASS chứng minh mọi đường gọi đã được bảo vệ.** Không.
13. **Một type-level marker tự được kế thừa xuống từng method.** Cần resolver policy.
14. **Repeatable annotation bắt buộc advice chạy nhiều lần.** Không.
15. **Static analyzer luôn biết mọi dynamic target/reflection call.** Không.
16. **Chỉ cần test vi phạm, không cần fixture hợp lệ.** Dễ false positives.
17. **Nhiều aspects có thể xếp theo thứ tự annotation xuất hiện.** Không.
18. **Shared aspect nên lưu currentUser trong field.** Có thể data race/cross-request contamination.

## 18. Câu hỏi ôn tập

**Câu 1.** Một interface đánh dấu @CheckedService nhưng có method không mang Observe hoặc IgnoreObserve. Theo policy ví dụ, lỗi nào?

**Đáp:** ARC001, missing annotation trên một operation thuộc required contract.

**Câu 2.** Một method có cả @Observe và @IgnoreObserve. Java có thể compile không?

**Đáp:** có thể compile vì hai annotation types đều cho METHOD; rule nghiệp vụ phát ARC002 conflict.

**Câu 3.** Annotation nằm trên private helper trong hệ thống chỉ dùng interface proxy. Đó là lỗi cú pháp Java?

**Đáp:** không. @Target(METHOD) cho phép, nhưng wrong placement theo interception boundary nên có thể phát ARC004.

**Câu 4.** Implementation method có @Observe, interface method tương ứng không có. Interface-only resolver có tự nhìn thấy implementation annotation không?

**Đáp:** không. Cần di chuyển annotation hoặc chọn resolver policy khác. Demo phát missing ARC001 và warning ARC005.

**Câu 5.** @Retention(RUNTIME) đảm bảo annotation trên implementation tự xuất hiện ở interface Method?

**Đáp:** không. Retention chỉ quyết định metadata có thể đọc ở đúng element; không sao chép giữa các method declarations.

**Câu 6.** @Inherited có truyền annotation trên interface method vào implementation override không?

**Đáp:** không, vì @Inherited không cung cấp semantics đó.

**Câu 7.** Một method có @Observe("") khác gì không annotate?

**Đáp:** có marker nhưng giá trị cấu hình sai, ARC003; không annotate mới là missing ARC001.

**Câu 8.** Nếu một required authorization annotation tồn tại nhưng lời gọi bypass proxy, có chắc quyền đã được kiểm không?

**Đáp:** không. Cần enforcement ở ranh giới đáng tin và integration tests cho đường bypass.

**Câu 9.** Validator startup PASS đủ để khẳng định advice được gọi cho method annotated chưa?

**Đáp:** chưa. Nó kiểm metadata; phải có behavior test trên interception boundary thật.

**Câu 10.** Khi một checker không phát error, nên hỏi gì trước?

**Đáp:** rule có chạy không, đã kiểm đúng source/effective metadata và đúng các method/join points trong contract chưa?

## 19. Kết luận

**Kiểm tra annotation thiếu, mâu thuẫn hoặc đặt sai chỗ** là bài toán thiết kế một **hợp đồng metadata** cùng khả năng can thiệp AOP thực sự:
- **Thiếu:** xác định element nào bắt buộc annotate.
- **Mâu thuẫn:** phát hiện policy và giá trị không tương thích.
- **Sai vị trí:** phân biệt Java @Target hợp lệ với method/type mà interceptor thật có thể quan sát.
- **Đúng nguồn:** giải rõ annotation ở interface, implementation, hierarchy và retention.
- **Đúng hành vi:** kiểm chứng join point, advice, result, exception, security và coverage.

**Ghi nhớ:** annotation là **ý định**, không tự là enforcement. Một metadata validator tốt ngăn cấu hình sai từ sớm, còn test interception/runtime mới chứng minh concern đã được áp dụng ở những đường thực thi cần thiết.
