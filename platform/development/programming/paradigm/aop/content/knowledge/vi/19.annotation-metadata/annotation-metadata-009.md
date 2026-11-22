# Đánh đổi giữa cấu hình bên ngoài và đánh dấu trong mã

## 1. Hai cách bày tỏ ý định AOP, không phải hai loại phép màu

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, ta muốn tách những mối quan tâm cắt ngang như tracing, audit, phân quyền, metrics, retry, validation hay caching khỏi phần lớn code nghiệp vụ. Một câu hỏi quan trọng của thiết kế là **đặt thông tin lựa chọn join point và chính sách can thiệp ở đâu**:

- **Đánh dấu trong mã (in-code annotation / declaration):** người viết source gắn dấu lên type, method hoặc một phần tử được hỗ trợ, chẳng hạn `@Observed` hoặc `@Sensitive`. Một bộ đọc metadata sẽ dùng dấu này khi áp dụng pointcut hoặc tạo cấu hình.
- **Cấu hình bên ngoài (external configuration):** rule về class, method, signature, annotation, loại join point, precedence hoặc policy nằm trong file cấu hình, metadata registry, bộ chọn tập trung, build configuration hoặc một lớp policy được triển khai riêng.

Ví dụ về ý định:

~~~text
CODE-CENTRIC:
   @Observed
   public Receipt pay(Request request) { ... }

EXTERNAL:
   "Observe execution of PaymentService.pay(Request)"
   "Include all methods matching PaymentService.*"
   "Exclude status/health methods"
~~~

Đây là **mô tả minh họa**, không phải cú pháp AOP được mọi engine hiểu. Hai cách mô tả có thể hướng đến **cùng một advice**, nhưng chúng tạo các tradeoff khác nhau về độ tường minh, tính gắn kết với source, phạm vi chính sách, việc refactor, khả năng sửa rules và nguy cơ match sai.

**Luận điểm cốt lõi:** annotation cũng như file cấu hình chỉ là **thông tin đầu vào**. Để advice thực sự chạy cần có **pointcut/matching rule** và **interception mechanism** như proxy, dispatcher, compile-time/binary weaving hoặc load-time transformation mà công cụ cụ thể hỗ trợ.

Không có annotation thì **vẫn có thể có AOP**. Có annotation nhưng không có mechanism thì **không tự có AOP**. Có file cấu hình bên ngoài nhưng không cài cơ chế can thiệp thì **cũng không tự có AOP**.

### Mục tiêu của bài

Sau bài học, bạn có thể:

1. Phân biệt rõ **rule location**, **metadata**, **join point matching** và **runtime interception**.
2. So sánh annotation trong code và cấu hình ngoài theo các tiêu chí thực tế.
3. Hiểu kiểu coupling, phạm vi policy và ảnh hưởng của refactor/versioning.
4. Thiết kế ranh giới trách nhiệm: tác giả code, chủ sở hữu security/audit, vận hành và build pipeline.
5. Mô tả khi nào sử dụng annotation, external config hoặc mô hình kết hợp.
6. Kiểm thử bằng Java 17 rằng cùng một target có thể bị chọn khác nhau mà không sửa code nghiệp vụ.
7. Tránh các ngộ nhận về hot reload, proxy coverage, self-invocation và các giới hạn runtime.
8. Xây bộ test chứng minh **có match đúng** và **có thực thi advice thật**, gồm cả negative coverage.

Bài tập trung vào **Aspect/AOP ở cấp cơ bản và nâng cao**, không gắn vào một framework ứng dụng cụ thể.

## 2. Bốn khâu cần tách ra

Một hệ thống AOP có thể được xem theo chuỗi:

~~~text
1. DECLARE
   annotation trong source, rule file, programmatic registry
           |
2. RESOLVE / MATCH
   type, method, metadata, signature, join point kind
           |
3. INSTALL INTERCEPTION
   tạo proxy, weave bytecode, register dispatcher
           |
4. EXECUTE
   khi join point xảy ra: before/after/around/proceed
~~~

**Dời khâu 1 từ source sang file cấu hình không tự làm thay đổi khả năng của khâu 3.** Ví dụ:

- Một JDK interface proxy chỉ quan sát các lời gọi đi qua proxy. Đổi rule từ annotation sang external method name **không làm nó tự can thiệp vào private method hoặc direct field access**.
- Một bytecode weaver có thể instrument join point mà proxy không thấy, nhưng nó vẫn có thể sử dụng annotation **hoặc** rule ngoài làm tín hiệu.
- Một compile-time weaver có thể cần rebuild khi rule thay đổi; một runtime dispatcher có thể hỗ trợ reload, nhưng chỉ khi đã thiết kế lifecycle và atomic snapshot phù hợp.

Đánh đổi chính là **cách biểu đạt và quản lý ý định**, không phải một sự phân chia tuyệt đối về sức mạnh kỹ thuật của interception engine.

### 2.1. Một cùng advice, hai nguồn rule

~~~text
                 RULE SOURCES
              /                 \
         SOURCE @Observed       external selectors
              \                 /
               \               /
                pointcut resolution
                       |
                 matched joinpoints
                       |
                   timing advice
                       |
                target executions
~~~

Nếu kết quả match cuối giống nhau và runtime mechanism giống nhau, về nguyên tắc before/after behavior có thể giống. Khác biệt sẽ nằm ở **cách thay đổi, kiểm soát và kiểm chứng rules**.

### 2.2. Đừng đồng nhất cấu hình ngoài với pointcut chuỗi đơn giản

External rules có thể là một dữ liệu cấu trúc có type-safe schema, ví dụ:

~~~yaml
policyVersion: 4
rules:
  - concern: metrics
    targetType: example.PaymentService
    method: pay
    parameterTypes:
      - example.Request
    effect: observe
  - concern: metrics
    targetType: example.PaymentService
    method: health
    effect: exclude
~~~

Đây là **ví dụ schema minh họa**, không phải cấu hình có thể dùng nguyên xi với mọi AOP engine. Nó cho thấy rule ngoài có thể mang version, owner và explicit exclusions, thay vì chỉ một chuỗi regex mong manh.

## 3. Annotation trong mã: ưu điểm về tính gần gũi với đối tượng được đánh dấu

Khi method có:

~~~java
@Observed
public String submit(String id) {
    return "saved:" + id;
}
~~~

đây là fragment Java, cần annotation `Observed` được định nghĩa phù hợp. Ý định “method này có metadata Observed” nằm **ngay cạnh chữ ký và logic** của method.

Lợi thế:

- **Discoverability:** developer mở file sẽ thấy dấu; code review dễ phát hiện thay đổi metadata khi sửa method.
- **Refactor support:** IDE/compiler có thể xử lý declaration gần code, giảm sai lệch do rename đối với một số workflows.
- **Intention ownership:** tác giả API có thể tuyên bố method này mang ý nghĩa cần quan sát.
- **Type-level documentation:** annotations có thể đi cùng elements, mặc định, retention, target, và rules khai báo.
- **Nhắm mục tiêu chính xác:** đánh dấu một method cụ thể thay vì pattern bao cả nhóm có quá nhiều false positives.
- **Bản build tái lập:** annotation ở source đi qua quy trình code review và version control như code.

Tuy nhiên, lợi ích không tự động biến thành **runtime guarantee**. Annotation chỉ có hiệu lực nếu component khác thực sự hiểu nó và cài mechanism. Reviewer vẫn phải xem interceptor/pointcut, đặc biệt với security và transaction concerns.

### 3.1. Coupling vào code nghiệp vụ

Đánh dấu `@Observed` làm một type nghiệp vụ **biết tới annotation type** ở cấp source/import/dependency. Điều này có thể chấp nhận được khi `Observed` thuộc hợp đồng miền, nhưng cũng có thể làm code nghiệp vụ phụ thuộc infrastructure metadata mà đội ngũ muốn tách rời.

Cần hỏi:

- Annotation nằm trong một module API ổn định hay library infrastructure tùy phiên bản?
- Domain object cần mang dependency đó để làm gì?
- Có muốn sử dụng target trong chương trình khác không có AOP không?
- Đổi concern có bắt buộc sửa rất nhiều source files không?
- Nếu annotation tên `RequiresAudit`, ai có quyền được xóa dấu này?

**Đánh dấu phân tán ở hàng trăm methods có thể tăng chi phí di trú policy**, dù mỗi dấu rất dễ nhìn thấy.

### 3.2. Ai chịu trách nhiệm đặt annotation?

Nếu compliance yêu cầu mọi thao tác cập nhật dữ liệu phải có audit, mà việc áp audit phụ thuộc developer tự nhớ thêm `@Audited` ở từng method, có thể xảy ra **coverage omission**: method mới không được đánh dấu, nên không được audit.

Một chính sách theo cấu trúc rộng hoặc kiểm tra build-time bắt buộc có thể giảm nguy cơ bỏ sót. Ngược lại, một external rule quá rộng lại có thể audit cả thao tác không phù hợp, ghi dư dữ liệu hoặc ảnh hưởng performance.

### 3.3. Chữ ký thay đổi và metadata có thể mất ngữ nghĩa

Khi method tách thành hai helper, `@Observed` nên ở public boundary, từng helper hay cả hai? Nếu developer chuyển annotation từ interface method sang implementation, scanner hiện tại có còn nhìn thấy không? Nếu rename method, annotation thường vẫn nằm cạnh declaration nhưng **join point coverage** có thể thay đổi do proxy/weaving limitations.

Annotation giúp giữ ý định sát code, không thay thế thiết kế lifecycle/semantics của advice.

## 4. Cấu hình bên ngoài: ưu điểm về quản lý chính sách tập trung

Rule được đặt bên ngoài class nghiệp vụ có thể phù hợp khi:

- **Một concern áp lên nhiều types** dựa trên pattern ổn định, ví dụ mọi API boundary trong một module.
- **Chủ sở hữu policy khác tác giả source**, như đội vận hành tracing hoặc bộ phận audit.
- **Không thể hoặc không muốn sửa source** của các thư viện/third-party code.
- **Muốn thay phạm vi quan sát** mà không thêm/sửa annotations trên hàng trăm methods.
- **Cần bật/tắt policy theo environment**, có audit trail và rollout.
- **Muốn giữ domain code độc lập** với annotation type của engine.

Ví dụ ý niệm:

~~~text
EXTERNAL RULE:
  Concern: metrics
  Include: public execution of type pattern *Service
  Exclude: health, readiness
  Configuration owner: observability team
  Config version: 9
~~~

Cách này giúp quản lý tập trung, nhưng cũng làm một behavior **không hiển thị trực tiếp trong file source của target**. Developer có thể mở `PaymentService.java` và không biết method sẽ chịu logging, retry hoặc authorization nếu không đọc external rules.

### 4.1. Cấu hình ngoài cũng tạo coupling

Không dùng annotation không có nghĩa “không coupling”. External config thường gắn vào **binary/class names, packages, signatures, annotation names, parameter types hoặc deployment artifact identifiers**.

Đổi `example.PaymentService.pay` thành `example.Payments.pay` có thể làm một rule cũ **không match gì**. Một regex dùng `*Service` có thể vô tình match class mới. Coupling chỉ **chuyển từ dependency source/import sang dependency cấu hình với cấu trúc chương trình**.

### 4.2. External không mặc nhiên hot-reload

Một external selector có thể được đọc:
- Khi **compile**: cần rebuild/reweave để rule đổi.
- Khi **class load**: cần classloader/restart hoặc retransform trong giới hạn công nghệ.
- Khi **proxy creation**: cần tạo lại proxy để có rule mới, nếu handler giữ immutable snapshot.
- Trên **mỗi invocation**: có thể đọc cập nhật mới nhưng cần concurrency, validity và cost control.

Vì vậy “đổi file config không cần deploy” chỉ đúng **nếu kiến trúc cài rule hỗ trợ và có phạm vi rõ**. Nếu không, chỉ đổi nội dung file trên disk có thể không thay behavior runtime.

### 4.3. Quy tắc ngoài quá rộng gây blast radius

Một selector `all methods named save` có thể vô tình chọn:
- Method nội bộ và helper có cùng tên.
- Methods xử lý dữ liệu nhạy cảm không nên log payload.
- Methods được gọi tần suất cao gây overhead lớn.
- Đường cache/retry mà semantics khác mong muốn.
- Method mới được thêm ở version sau.

Rule rộng thuận tiện khi cần **default coverage**, nhưng bắt buộc có exclusions, tests và policy về thay đổi API.

## 5. Bảng đánh đổi toàn diện

| Tiêu chí | Annotation trong code | Cấu hình bên ngoài |
| --- | --- | --- |
| **Nhìn thấy ý định** | Dễ nhìn ngay trên declaration | Phải truy vết rule registry/file |
| **Phạm vi cập nhật** | Sửa một hoặc nhiều source files | Có thể sửa một policy trung tâm |
| **Phụ thuộc source** | Target phải biết annotation type | Target có thể không cần import annotation |
| **Coupling** | Với annotation API/metadata | Với names, signatures, package patterns |
| **Độ chính xác ở method** | Dễ đánh dấu trực tiếp | Cần selector đủ chặt và resolver đúng |
| **Tự phủ class mới** | Class mới cần được đánh dấu hoặc meta-rule | Pattern có thể tự match class mới |
| **Nguy cơ bỏ sót** | Developer quên annotation | Config không cập nhật khi rename/move |
| **Nguy cơ áp quá rộng** | Ít nếu đánh dấu hẹp | Cao nếu selector rộng và không kiểm soát |
| **Bên sở hữu policy** | Thường là code owner | Có thể tách cho policy/ops owner |
| **Thay theo môi trường** | Cần một cơ chế điều kiện riêng | Có thể dễ hơn nếu runtime hỗ trợ |
| **Refactoring** | IDE thường nhìn annotation trực tiếp | String selector/regex dễ lỗi khi rename |
| **Review / audit** | Theo source diff | Theo config diff/policy approvals |
| **Runtime overhead** | Phụ thuộc reader/interceptor | Cũng phụ thuộc reader/interceptor |
| **Khả năng dùng third-party types** | Không luôn sửa source được | Selector/weaver có thể bao code ngoài nếu hỗ trợ |
| **Rollback** | Gắn với source/rebuild/deploy | Tùy snapshot/reload/deployment contract |
| **Test cốt lõi** | Annotation discovery + interception | Rule validation + matching + interception |

Không thể quyết định chỉ bằng “annotation hiện đại hơn” hoặc “config linh hoạt hơn”. Phải cân nhắc **chủ sở hữu concern, độ rộng coverage, kỳ vọng deployment và hậu quả khi match sai**.

## 6. Rule trong mã cũng có thể tồn tại mà không dùng annotation

Một API Java có thể tự khai báo rule bằng code:

~~~java
boolean shouldObserve(Method method) {
    return method.getName().equals("submit");
}
~~~

Đây là fragment minh họa, `Method` cần import. Rule đó nằm trong mã nhưng **không phải metadata annotation**. Vì thế so sánh đúng không chỉ là “annotation vs XML/YAML”: có thể có **programmatic configuration**, aspect language declarations, policy registry, generated metadata và nhiều cách kết hợp.

Hai chiều độc lập:

~~~text
WHERE RULE IS STORED:
  source annotation / source selector / external file / central registry

HOW INTERCEPTION HAPPENS:
  proxy / dispatcher / compile-time weaving / binary weaving / load-time weaving
~~~

Một external file có thể chỉ chọn target cho compile-time weaver; một `@Observed` có thể được JDK proxy handler đọc. Không gộp hai trục này làm một.

## 7. Java 17 hoàn chỉnh: cùng target, hai nguồn lựa chọn advice

Ví dụ này dùng **JDK dynamic proxy**, không phải một engine AOP với ngôn ngữ pointcut riêng. Mục đích là minh họa **quy tắc chọn lời gọi** từ hai nguồn có thể khác nhau trong khi **cơ chế can thiệp và target giữ nguyên**.

Định nghĩa:

- `@Observed` có retention `RUNTIME` được gắn trực tiếp lên `Core.submit(String)`.
- `fromAnnotations()` chọn implementation methods có `@Observed`.
- `fromExternalNames(Set<String>)` dùng một tập tên method, đại diện cho **nội dung đã được load từ cấu hình ngoài**. Trong demo tập tên được truyền bằng `Set.of` để chương trình chạy không phụ thuộc file; trong ứng dụng thật bạn có thể parse file có schema/validation.
- `wrap()` dùng **cùng một JDK proxy handler**, chỉ khác `Rule` mà nó nhận.
- Hai proxy ngoài `externalV1` và `externalV2` thể hiện **hai snapshot cấu hình khác nhau**: V1 chỉ chọn `inspect`, V2 chỉ chọn `submit`. **Không có hot-reload tự động:** V2 được tạo thành proxy mới.
- Raw `core.submit("A")` không qua proxy, nên không chạy advice dù method có annotation.
- `byAnnotation.internal("E")` đi qua proxy cho method `internal` không đánh dấu; core gọi `this.submit("E")` nên nested call bỏ qua wrapper.

Tạo file `AspectSelectionDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Set;

public final class AspectSelectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    interface Work {
        String submit(String id);
        String inspect();
        String internal(String id);
    }

    static final class Core implements Work {
        int submissions;

        @Observed
        public String submit(String id) {
            submissions++;
            System.out.println("CORE submit " + id);
            return "saved:" + id;
        }

        public String inspect() {
            System.out.println("CORE inspect");
            return "healthy";
        }

        public String internal(String id) {
            System.out.println("CORE internal");
            return this.submit(id);
        }
    }

    @FunctionalInterface
    interface Rule { boolean matches(Method implementation); }

    static Rule fromAnnotations() {
        return method -> method.isAnnotationPresent(Observed.class);
    }

    static Rule fromExternalNames(Set<String> methodNames) {
        Set<String> snapshot = Set.copyOf(methodNames);
        return method -> snapshot.contains(method.getName());
    }

    static Object invoke(Work target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    static Work wrap(Work target, Rule rule, String label) {
        return (Work) Proxy.newProxyInstance(
            Work.class.getClassLoader(), new Class<?>[] { Work.class },
            (proxy, interfaceMethod, args) -> {
                Method actual = target.getClass().getMethod(
                    interfaceMethod.getName(), interfaceMethod.getParameterTypes());
                if (!rule.matches(actual)) return invoke(target, actual, args);
                System.out.println(label + " BEFORE " + actual.getName());
                Object value = invoke(target, actual, args);
                System.out.println(label + " AFTER " + value);
                return value;
            });
    }

    static void check(boolean value) {
        if (!value) throw new AssertionError("test failed");
    }

    public static void main(String[] args) {
        Core core = new Core();
        Work byAnnotation = wrap(core, fromAnnotations(), "ANNOT");
        Work externalV1 = wrap(core, fromExternalNames(Set.of("inspect")), "CONFIG_V1");
        Work externalV2 = wrap(core, fromExternalNames(Set.of("submit")), "CONFIG_V2");

        System.out.println("DIRECT " + core.submit("A"));
        System.out.println("ANNOT " + byAnnotation.submit("B"));
        System.out.println("ANNOT_INSPECT " + byAnnotation.inspect());
        System.out.println("CONFIG_V1_SUBMIT " + externalV1.submit("C"));
        System.out.println("CONFIG_V1_INSPECT " + externalV1.inspect());
        System.out.println("CONFIG_V2 " + externalV2.submit("D"));
        System.out.println("INTERNAL " + byAnnotation.internal("E"));
        check(core.submissions == 5);
        System.out.println("ASSERT submissions=5");
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AspectSelectionDemo.java
java AspectSelectionDemo
~~~

Đầu ra thực tế **đã được kiểm chứng bằng `javac --release 17` và JVM**:

~~~text
CORE submit A
DIRECT saved:A
ANNOT BEFORE submit
CORE submit B
ANNOT AFTER saved:B
ANNOT saved:B
CORE inspect
ANNOT_INSPECT healthy
CORE submit C
CONFIG_V1_SUBMIT saved:C
CONFIG_V1 BEFORE inspect
CORE inspect
CONFIG_V1 AFTER healthy
CONFIG_V1_INSPECT healthy
CONFIG_V2 BEFORE submit
CORE submit D
CONFIG_V2 AFTER saved:D
CONFIG_V2 saved:D
CORE internal
CORE submit E
INTERNAL saved:E
ASSERT submissions=5
~~~

### 7.1. Vì sao cùng `Core.submit` lúc có advice, lúc không?

`core.submit("A")` gọi target trực tiếp, không có interceptor. `byAnnotation.submit("B")` đi qua proxy có rule kiểm `@Observed`, nên in before/after. `externalV1.submit("C")` vẫn đi qua proxy nhưng rule V1 không chọn `submit`, nên không in advice. `externalV2.submit("D")` cũng đi qua proxy nhưng rule V2 chọn `submit`, nên có advice.

**Cơ chế proxy giống nhau. Chính nguồn rule thay đổi tập lời gọi được chọn.** Và dù annotation hiện diện trên `submit` ở cả bốn cases, annotation không tự ép advice xuất hiện.

### 7.2. Vì sao `inspect()` được quan sát theo V1 nhưng không theo annotation?

`inspect()` không có `@Observed`. Rule annotation không chọn, nên `byAnnotation.inspect()` chỉ chạy core. Rule external V1 lại chứa tên `inspect` nên chọn nó, dù source `Core.inspect` không có annotation.

Đây là lợi thế của external selection khi không muốn sửa source. Đồng thời, nếu V1 bị cấu hình quá rộng hoặc sai, nó cũng có thể chọn một method không mong muốn.

### 7.3. Vì sao thay V1 sang V2 không sửa `Core`?

Dữ liệu rule được truyền vào `fromExternalNames` bằng immutable snapshot `Set.copyOf`. Khi tạo `externalV2`, chương trình cấp rule khác cho một **proxy instance mới**. Core method declarations và `@Observed` giữ nguyên.

**Không suy từ demo rằng file cấu hình production tự reload.** Thực tế muốn cập nhật policy đang chạy cần loader, validation, publication và lifecycle.

### 7.4. Vì sao `INTERNAL saved:E` không có advice?

`byAnnotation.internal("E")` đi qua proxy, nhưng method `internal` không có `@Observed` nên handler delegate cho core. Bên trong `Core.internal` là lời gọi `this.submit("E")` trên core, **không đi qua proxy**. Annotation vẫn nằm trên `submit`, nhưng interception không quan sát internal execution ấy.

Một bytecode weaver instrument execution join point thực có thể bao phủ self-call tùy capability; **đổi rule ngoài hay trong mã không tự chữa giới hạn của proxy**.

### 7.5. Vì sao chỉ tính `submissions=5`?

Các lượt submit là `A`, `B`, `C`, `D` và `E`. Advice có thể xuất hiện hoặc không, nhưng trong ví dụ mỗi đường đã gọi target đúng một lần, nên counter bằng 5. Điều này giúp tách **số lần business execution** và **số lần advice được áp dụng**.

### 7.6. Những giới hạn có chủ đích của demo

- External config được **mô phỏng bằng Set**, không parser file, không remote registry và không hot reload. Nó đủ để so *nguồn rule* nhưng không minh họa I/O config thật.
- Rule external so mỗi `method.getName()`, không phân biệt overloaded signatures. Một hệ thống thật cần selector chặt hơn.
- Handler không nhằm xử lý đầy đủ `equals/hashCode/toString`, access policy hoặc classloader/plugin corner cases.
- Demo minh họa interface proxy, không phải structural introduction hay field/constructor weaving.
- Rule V1/V2 được tạo cho cùng core, nên đọc/ghi core state chia sẻ; các proxy khác nhau không tự tạo transaction/isolation.
- `Set.copyOf` làm snapshot của names, không bảo đảm schema compatibility hoặc rule đã được xác minh.
- `println` dùng để nhìn rõ thứ tự events; trong ứng dụng thật, logging/metrics có lỗi, độ trễ và chính sách privacy riêng.

## 8. External rule cần schema và bộ kiểm tra nghiêm túc

Ví dụ chỉ chọn theo `method.getName()` là cố tình đơn giản. Trong production, hai overloads:

~~~java
String submit(String id);
String submit(String id, boolean urgent);
~~~

đều có cùng `getName() == "submit"`. Nếu rule chỉ nhắm một overload, cần biết:

- Declaring type / inherited method.
- Method name.
- Parameter types và return type khi thích hợp.
- Join point kind: call hay execution.
- Public/private/static/final và giới hạn engine.
- Method annotations, type annotations nếu rule cần.
- Classloader/module scope.
- Include/exclude precedence.

Một selector sai có thể gây **false positive** (chọn method không nên chọn) hoặc **false negative** (bỏ sót method cần được chọn).

### 8.1. Tránh dùng tên package như hợp đồng không đổi

Các tên package/type là phần cấu trúc mã, có thể đổi khi refactor. Nếu external rules ghép trực tiếp vào tên, cần kiểm rằng rename/move làm cập nhật policy. Có thể dùng marker interface, annotation ổn định hoặc một contract rõ hơn làm anchor, dù chúng cũng có tradeoff.

### 8.2. Cấu hình không hợp lệ phải có chính sách

Những lỗi cần phát hiện:
- Method/type không tồn tại trong version mới.
- Selector hợp lệ cú pháp nhưng match 0 join points ngoài mong muốn.
- Rule match quá nhiều join points.
- Điều kiện `include` và `exclude` mâu thuẫn.
- Hai policies có precedence không xác định.
- Value vượt mức cho phép hoặc thiếu parameter.
- Rule đòi join point kind mà current interceptor không hỗ trợ.
- External config tham chiếu classloader không tồn tại.

Có thể **fail-fast**, chặn rollout, cảnh báo hoặc dùng fallback tùy concern. Với authorization, lỗi rule mà âm thầm bỏ can thiệp có thể tạo lỗ hổng; với metrics, fail-open theo hợp đồng có thể được chấp nhận hơn.

## 9. Khi policy là bắt buộc: tính bao phủ quan trọng hơn chỗ đặt rule

Hãy phân biệt ba loại concern:

| Concern | Nếu bỏ sót một method | Chính sách thường cần cân nhắc |
| --- | --- | --- |
| Metrics best-effort | Mất một số quan sát | Alert/coverage report, đôi khi fail-open |
| Audit tuân thủ | Có thể mất bằng chứng quan trọng | Enforce tại boundary đáng tin, fail-closed hoặc durable audit design |
| Authorization | Có thể cho hành động trái quyền | Default-deny / policy-as-code, test bypass toàn diện |
| Retry | Có thể bỏ retry hoặc áp retry nguy hiểm | Chỉ chọn idempotent/transient paths |
| Cache | Có thể gọi business dư hoặc trả dữ liệu sai | Key/TTL/auth isolation và tests |

**Không có vị trí lưu rule nào tự đảm bảo coverage.**

- In-code annotation: có thể **quên đặt dấu**.
- External config: có thể **pattern sai hoặc stale sau refactor**.
- Cả hai: có thể **đúng selector nhưng runtime call bypass proxy**, class không woven hoặc advice bị short-circuit bởi layer khác.

Với những chính sách bảo mật quan trọng, cần thiết kế enforcement ở trust boundary, không chỉ “thấy annotation” hoặc “file config đã có dòng”.

### 9.1. Explicit opt-in vs default-on

- **Opt-in bằng annotation:** chỉ những methods được đánh dấu mới nhận concern. Kiểm soát hẹp, ít bất ngờ, nhưng dễ bỏ sót.
- **Default-on bằng external rule:** toàn bộ methods trong scope nhận concern trừ khi được exclude. Bao phủ rộng, nhưng tăng nguy cơ tác động tới internal helpers, methods sensitive hoặc performance-critical.
- **Hybrid:** rule rộng chỉ áp cho contract marker rõ; exceptions được quản lý có review; quan trọng nhất là có test phát hiện thiếu coverage.

Không có một câu trả lời chung. Hãy chọn theo **hậu quả của false negative so với false positive**.

## 10. Refactoring: ai sẽ phát hiện rule bị lệch?

### 10.1. Rename method khi annotation nằm trên method

Nếu developer đổi tên `submit` thành `placeOrder` nhưng giữ `@Observed` trên declaration mới, metadata vẫn nằm cạnh method. Tuy nhiên, runtime interception có thể khác nếu pointcut khác còn phụ thuộc tên cũ, proxy interface thay đổi hoặc class đã woven không được rebuild.

### 10.2. Rename method khi external rule theo tên

Config `"submit"` có thể **không match** method `placeOrder` mới. Source build vẫn thành công nếu không có kiểm rule; lỗi chỉ xuất hiện dưới dạng thiếu metrics/audit/authorization trong production.

Do đó cần **configuration-to-code validation** ở build/integration:
- Resolve selector trên artifact đã build.
- Assert expected matched-method set.
- Fail nếu mandatory rule có 0 matches.
- Assert không match ngoài type/module cho phép.
- So difference giữa matched sets của hai versions.

### 10.3. Signature changes và overloads

Một rule đặt bằng method name có thể không biết parameter types thay đổi. Annotation gắn cùng declaration có thể theo refactor tốt hơn, nhưng nếu method được chia tách, annotation không tự chọn đúng boundary. Dù lựa chọn nguồn rule nào, **chủ sở hữu business contract phải quyết định lại ý nghĩa can thiệp** sau refactor lớn.

## 11. Versioning: rule cũng là một phần của bản phát hành

Một application version không chỉ bao `.java`/`class` mà còn gồm:

~~~text
Runtime behavior =
  application artifact version
+ aspect/advice implementation version
+ pointcut/config version
+ proxy/weaver/agent version
+ classloader and deployment topology
~~~

Nếu code mới chạy với config cũ, external rule có thể bỏ lỡ methods đã đổi tên hoặc match nhầm methods mới. Nếu code cũ chạy với config mới, rule có thể tham chiếu API chưa tồn tại.

Với annotations, code và metadata thường đi cùng commit/build, nhưng advice implementation có thể nằm ở module khác với version riêng. Cả hai mô hình vẫn cần compatibility policy.

### 11.1. Configuration drift giữa môi trường

Dev có thể bật tracing, staging tắt và production bật audit bắt buộc. Nếu không có **environment matrix**, team có thể test một đường khác đường sẽ release. Metadata annotation có thể giống nhau nhưng **cách diễn giải** bị external settings điều chỉnh.

Một bảng kiểm:
- Rules đang active ở từng môi trường.
- Danh sách join points được match.
- Thứ tự aspects/advice.
- Runtime mechanism và classloader.
- Policy về missing rule/unknown field.
- Tín hiệu giám sát sau rollout.

### 11.2. Version rules cùng artifact hay độc lập?

Cấu hình ngoài độc lập có thể cho phép vận hành linh hoạt; nhưng càng tách lifecycle, càng cần:
- Schema version.
- Minimum/maximum compatible application version.
- Signature validation.
- Owner approval và change log.
- Rollback semantics.
- Canary/shadow matching để phát hiện coverage trước khi apply.

## 12. Khi cần hot reload cấu hình động

Nếu ứng dụng muốn đổi selectors khi đang chạy, cần hiểu **hai việc độc lập**:

1. Thay đổi **rule data**.
2. Đảm bảo **cơ chế interception có thể quan sát tập join points mới**.

Một proxy đã tạo có handler đọc rule qua một `AtomicReference<ImmutableRuleSet>` có thể cho phép đổi policy matching trên **những methods đã đi qua proxy**. Nhưng nó **không làm raw target calls bỗng đi qua proxy**, cũng không tự instrument constructor/field/private execution.

Một compile-time weaver đã chỉ weave một số methods có thể không có hook ở một method ngoài tập đó. Thay rule ngoài để chọn method mới **không giúp method ấy có advice hook nếu chưa được instrument**.

### 12.1. Snapshot rule không được half-applied

Với dynamic config nên:

~~~text
read and parse candidate config
         |
validate entire schema + references
         |
compute immutable RuleSet version N+1
         |
publish atomically to dispatcher
         |
old in-flight invocations -> policy snapshot N, nếu hợp đồng chọn vậy
new invocations -> policy snapshot N+1
~~~

Đây là **mô hình thiết kế**, không phải API sẵn có. Nếu dispatcher kiểm các mutable fields bị thay từng phần, hai requests có thể thấy rule hỗn hợp nửa cũ nửa mới.

Ngoài ra phải xác định **thời điểm chụp snapshot**: lúc proxy call bắt đầu, mỗi join point, hay mỗi attempt trong retry? Nếu một operation gồm nhiều calls và policy đổi giữa chừng, có thể cần version pinning theo logical request.

### 12.2. Rollback và quyền thay đổi rules

Nếu đổi external rule có thể làm bật/tắt authorization, quyền sửa config tương đương **quyền thay policy bảo mật**. Cần authentication/authorization cho control plane, code review hoặc approvals, event audit, immutable histories và rollback an toàn.

Không biến “cấu hình không cần code deploy” thành “bất kỳ người có quyền ghi file đều có thể tắt security concern”.

### 12.3. Cấu hình theo tenant/request

Một policy theo tenant cần làm rõ nguồn tenant identity đáng tin và isolation. Không đặt global mutable `currentTenant` để matcher dùng cho nhiều threads. Có thể truyền request context hoặc resolved policy theo invocation, nhưng lại phải xử lý ThreadLocal cleanup/async context propagation.

**Rule location không giải quyết thread safety hoặc security context**; đó là trách nhiệm riêng.

## 13. Mô hình kết hợp: annotation làm tín hiệu ổn định, config làm chính sách

Một phương án thường dễ bảo trì:

~~~text
SOURCE:
    @BusinessOperation
    public Result execute(...)

EXTERNAL:
    select methods annotated @BusinessOperation
    attach metrics advice in production
    attach test observer in test environment
    configure sampling rates and excludes
~~~

Ví dụ là **mô tả kiến trúc**. Annotation định nghĩa **semantic contract ổn định**: đây là một business operation; config quyết định **concern nào có hiệu lực và mức nào**. Hai bên chia trách nhiệm.

Ưu điểm:
- Giảm coupling rule với method names.
- Đỡ phải sửa code khi đổi sampling/observability policy.
- Dễ giới hạn class set bằng metadata đã review.
- Cho phép công cụ tập trung phát hiện annotations trên artifact.

Rủi ro:
- Cần hai chỗ để hiểu behavior: source và policy.
- Annotation phải được tạo với retention/target phù hợp consumer.
- Người viết method vẫn có thể quên annotation.
- Rule ngoài vẫn có thể bị vô hiệu hóa hoặc thiếu ở môi trường.
- Meta-annotation/interface inheritance behavior phải được định nghĩa rõ.
- Nếu sử dụng security rules, default-deny và coverage tests vẫn phải có.

**Hybrid không tự an toàn hơn**; nó chỉ chia rõ loại ý định và nhóm người quản lý.

### 13.1. Phân biệt marker annotation và behavior configuration

Một marker `@BusinessOperation` không nên được mô tả như “tự tạo metrics”; nó chỉ nói **method thuộc một tập có ý nghĩa miền**. Rule ngoài có thể ánh xạ marker sang advice và parameterize mức thu thập dữ liệu.

Điều này cũng giúp tránh đổi public code contract chỉ để thay một tỷ lệ sampling.

## 14. Tại sao annotation không nên chứa mọi tham số policy?

Một annotation có thể có elements:

~~~java
@Observed(level = "verbose", captureArguments = true)
public Receipt pay(Request request) { ... }
~~~

Đây là fragment minh họa, `Observed` phải khai báo các elements tương ứng. Nếu những tham số này liên quan secrets, external endpoints, sampling operational knobs hoặc tenant-specific settings, hardcode vào source dễ dẫn đến:
- Bắt buộc rebuild/deploy chỉ để thay runtime knob.
- Mỗi environment cần behavior khác nhưng bytecode annotation cố định.
- Có nguy cơ lộ thông tin qua classfile/reflection.
- Bùng nổ annotation attributes làm API khó ổn định.

Một hướng: annotation thể hiện **ý nghĩa ổn định**, external policy quyết định **tần suất, destination, filters hoặc quyền bật/tắt** trong giới hạn security contract.

Ngược lại, nếu policy cần được review như source vì ảnh hưởng bảo mật, đưa toàn bộ thông số ra một dynamic registry không có kiểm soát cũng là lựa chọn nguy hiểm.

## 15. Đánh đổi về kiểm thử và debugging

### 15.1. Với in-code annotation

Các test quan trọng:
- `@Target`/`@Retention` đúng.
- Annotation có mặt trên **đúng element**.
- Reader kiểm interface hay implementation, method hay class?
- Có support `@Inherited` hoặc meta-annotations không?
- Overloaded methods không bị chọn nhầm.
- Annotation có mặt nhưng **interceptor không chạy** trên raw/bypass paths.
- Thay annotation value có đổi behavioral contract như dự định không?

### 15.2. Với external configuration

Các test quan trọng:
- Parser/schema validation.
- Tất cả named types/methods resolve được trên artifact.
- Rule match **đúng tập** join points, không chỉ match nonempty.
- Renames làm tests fail rõ.
- Include/exclude precedence hợp lý.
- Rule version tương thích runtime artifact.
- Hot reload hoặc snapshot publication đúng nếu hỗ trợ.
- Failure policy khi config không đọc được/không hợp lệ.
- Different environments không lệch ngoài chủ đích.
- Unauthorized config changes bị chặn và audit.

### 15.3. Với cả hai

- Test proxy/weaving đã **được cài thực**, không chỉ gọi matcher thuần.
- Test đường có advice và đường **không nên có advice**.
- Test exception và finally cleanup.
- Test short-circuit/retry không đổi kết quả nghiệp vụ ngoài hợp đồng.
- Test async completion và ThreadLocal/request context nếu dùng.
- Test raw vs proxy target, self-invocation, loaders.
- Test chạy đúng artifact phát hành thay vì bản raw.
- Đo overhead/p95-p99 và số join points instrument.

**Đọc được annotation hoặc validate được file config chưa phải integration test của AOP.**

## 16. Advice ordering không phải một vấn đề cú pháp đơn thuần

Một application có thể dùng các concerns:

~~~text
Authorize
  -> Cache
      -> Transaction
          -> Audit
              -> Target
~~~

Thứ tự outer/inner có thể ảnh hưởng:
- Kiểm quyền xảy ra trước hay sau cache hit.
- Audit ghi attempted, returned hay committed.
- Retry ở trong hay ngoài transaction.
- Lock scope có giữ qua network I/O không.
- Exception nào được advice phía ngoài quan sát.

Annotation ngay trên method có thể ghi `@Authorized` và `@Cached` nhưng **thứ tự runtime không tự suy được** nếu không có precedence rule. External config có thể diễn đạt thứ tự tường minh, nhưng rule không được validate vẫn dễ thay đổi behavior ngoài ý muốn.

**Chỗ đặt rule không thay thế việc kiểm order và boundaries.**

## 17. Những sai lầm khi nghĩ “annotation dễ refactor hơn mọi external rule”

Annotation thường theo declaration, nhưng vẫn có các tình huống:
- Annotation nằm trên **interface method**, implementation ở class khác.
- Overriding method không tự inherit method annotation theo mọi kiểu reflection lookup.
- Method được refactor sang helper khiến annotation không còn trên public boundary cần bảo vệ.
- Code generation tạo phương thức mới không copy metadata mong đợi.
- Classloader nạp artifact cũ chưa chứa annotation.
- Annotation `SOURCE` bị mất nếu reader chạy runtime.
- Một type-level marker được scanner hiểu khác giữa hai module.

Vì vậy annotation giảm một số **name-string drift** nhưng không miễn trừ integration tests.

## 18. Những sai lầm khi nghĩ “config ngoài dễ bật tắt tuyệt đối”

Nếu một external rule được cập nhật ở runtime, có thể gặp:
- Proxy handler vẫn giữ snapshot cũ.
- Weaver không instrument methods mới được chọn.
- Cache pointcut match chưa invalidated.
- Nhiều nodes nhận config mới vào các thời điểm khác nhau.
- Một request đang chạy thấy hai phiên bản policy.
- Rule update giữa hai retry attempts.
- Config mới yêu cầu join point kind công cụ không hỗ trợ.
- Security policy bị tắt ở một node khi node khác vẫn enforce.

**Dynamic policy changes là một vấn đề distributed rollout/version consistency**, không chỉ một lệnh sửa file.

Khi behavior bắt buộc phải thống nhất trên nhiều instances, cân nhắc coordinated rollout, version telemetry, canary tests và chế độ an toàn khi policy mismatch.

## 19. Giảm chi phí runtime và rủi ro performance

Không có quy tắc annotation matching luôn nhanh hơn external matching hoặc ngược lại. Chi phí thường đến từ:
- Số join points đã instrument.
- Thời gian resolve `Method` và đọc metadata.
- Chi phí parse/compile external selectors.
- Cache matching table đúng classloader/version.
- Thời gian thực thi advice (logging, metrics, network, lock).
- Số lần `proceed` do retry hoặc nested interception.
- Allocation per invocation / context propagation.

Một chiến lược:
1. Parse, validate và resolve selector lúc startup/build nếu phù hợp.
2. Cache immutable match decisions theo method/signature/classloader.
3. Không scan annotation graph hoặc regex từ đầu trong mọi hot invocation nếu không cần.
4. Không nắm một global lock xuyên `proceed` chỉ để đọc config.
5. Với live policy, dùng snapshot immutable có version và publication an toàn.
6. Theo dõi size/eviction của cache khi loaders động có thể unload.
7. Benchmark baseline không aspect, annotation selection và external selection trên **cùng target/workload**.

**Điểm quan trọng hơn một microbenchmark matcher là tính đúng của behavior**. Một rule sai chọn 10.000 methods thay vì 100 methods có thể gây overhead lớn dù mỗi lần kiểm chỉ vài nanoseconds.

## 20. Quy trình lựa chọn cho dự án

### Trường hợp A: người viết method muốn khai báo intent rõ

Chọn annotation khi:
- Ý nghĩa ổn định thuộc API/domain contract.
- Có quyền sửa source.
- Team muốn các dấu được review cùng code.
- Phạm vi nhỏ, từng method có vai trò rõ.
- Việc quên dấu được kiểm bằng tests hoặc static analysis.

Ví dụ: `@DomainCommand` làm metadata cho các method được xem là thao tác miền; policy bên ngoài có thể xác định logging/metrics theo group đó.

### Trường hợp B: policy chung do nhiều bên quản lý

Cân nhắc external config khi:
- Mọi method trong một phạm vi cần concern đồng nhất.
- Không có quyền sửa source thư viện.
- Team observability muốn đổi sampling hoặc exclusions.
- Cần approvals/rollout/audit ở policy control plane.
- Có kiểm thử selector drift và deployment compatibility.

### Trường hợp C: security hoặc audit bắt buộc

Đừng quyết chỉ theo tiện lợi.
- Xác định **trust boundary thật sự**.
- Định nghĩa default-deny/fail-closed khi appropriate.
- Test tất cả entry paths, kể cả raw and self-invocation.
- Ghi rõ coverage trên artifact runtime.
- Cân nhắc đặt bắt buộc ở tầng không thể bypass dễ dàng.
- Tách metadata khai báo, enforcement mechanism và resource transaction.

### Trường hợp D: cần chia code-domain intent với runtime operations

Cân nhắc hybrid:
- Annotation cho semantic grouping ổn định.
- External policy cho metrics sampling, destinations, allow/exclude lists.
- Immutable versioned snapshots với validation.
- Negative coverage tests.
- Một công cụ báo tập joinpoints được match ở mỗi release.

## 21. Decision matrix thực tế

| Câu hỏi | Nếu trả lời “có” | Hướng cần xem xét |
| --- | --- | --- |
| Source là của mình và intent cần hiển thị cạnh method? | Có | Annotation trong code |
| Cần instrument library mà mình không thể sửa source? | Có | External selector, nếu weaver/proxy coverage hỗ trợ |
| Concern áp dụng mặc định lên cả module? | Có | External scope + exclusions hoặc marker contract |
| Policy thay đổi thường xuyên theo vận hành? | Có | External config có reload/rollout được thiết kế |
| Đây là điều kiện an ninh bắt buộc? | Có | Enforce tại trust boundary, test bypass; không tin vào dấu tự nó |
| Rule theo method names dễ bị refactor? | Có | Annotation/marker, typed rules hoặc generated validation |
| Muốn mọi developer thấy behavior dự kiến khi đọc source? | Có | Annotation/documented contract |
| Muốn tránh phụ thuộc domain source với infrastructure annotation? | Có | External rules hoặc domain-stable marker |
| Có nhiều môi trường khác nhau? | Có | Tách semantic intent khỏi operational knobs |
| Không thể chấp nhận silent no-match? | Có | Fail-fast với assertion matched set |
| Có toolchain weaving ổn định và ABI tests? | Có | Có thể tận dụng rule mạnh, nhưng vẫn test |
| Chỉ cần theo dõi một hoặc hai operations? | Có | Cách đơn giản, tường minh, dễ test nhất |

Không cần cố chọn một phương án cho toàn bộ application. Từng concern có risk/cost khác nhau và có thể dùng chiến lược khác nhau.

## 22. Checklist triển khai

### Xác định contract

- [ ] Viết rõ concern nào, business boundary nào cần AOP.
- [ ] Phân biệt annotation metadata, selector rule và interception mechanism.
- [ ] Chọn source annotation, config ngoài hoặc hybrid với lý do cụ thể.
- [ ] Ghi owner quyền sửa policy và người chịu trách nhiệm review.
- [ ] Ghi expected joinpoints, positive coverage và negative coverage.

### Với annotation

- [ ] `@Target`, `@Retention` đúng consumer.
- [ ] Annotation trên đúng interface/implementation/type/method.
- [ ] Metadata inheritance/meta-annotation/repeatable policy rõ.
- [ ] Đổi declaration/refactor làm tests fail nếu coverage mất.
- [ ] Không nhầm annotation với security hoặc transaction guarantee.
- [ ] Không nhồi secrets/runtime knobs vào annotation values.

### Với external config

- [ ] Có schema, version và validation.
- [ ] Selector phân biệt overloads/signatures phù hợp.
- [ ] File không match hoặc match quá rộng bị phát hiện.
- [ ] Include/exclude và advice precedence được định nghĩa.
- [ ] Config-to-code compatibility check chạy trong CI.
- [ ] Reload/snapshot semantics được mô tả chính xác.
- [ ] Quyền cập nhật config có kiểm soát và audit trail.
- [ ] Có rollback plan cho rules.
- [ ] Môi trường phát hành dùng policy artifact đúng version.

### Với cơ chế can thiệp

- [ ] Biết rõ join point kind và coverage của proxy/weaver.
- [ ] Test gọi qua proxy vs raw target.
- [ ] Test self-invocation, nested calls, exception/finally.
- [ ] Test request đồng thời và async context nếu cần.
- [ ] Tránh duplicate advice/retry/side effects không mong muốn.
- [ ] Kiểm target classloader và build/deploy provenance.
- [ ] Theo dõi matched set, errors, p95/p99, overhead và cache.

## 23. Các nhầm lẫn phổ biến

1. **“Có annotation tức AOP tự chạy.”** Sai: annotation chỉ là metadata.
2. **“Có file config là proxy tự xuất hiện.”** Sai: interception mechanism phải được cài.
3. **“Không dùng annotation thì không thể viết AOP.”** Sai: structural, signature hoặc flow pointcuts có thể dùng nguồn khác.
4. **“Rule ngoài luôn cần ít maintenance.”** Nó có thể stale khi refactor và yêu cầu validation.
5. **“Annotation luôn tốt hơn config về bảo mật.”** Developer có thể bỏ sót hoặc code bypass interceptor.
6. **“External config luôn hot-reload.”** Tùy build/load/proxy lifecycle và publication.
7. **“Đổi V1 sang V2 trong demo nghĩa đổi file runtime.”** Demo tạo **proxy mới** với snapshot khác.
8. **“Source metadata gần code nghĩa runtime coverage đầy đủ.”** Có thể thiếu weaver/proxy và self-call.
9. **“Cấu hình theo method name phân biệt overloads.”** Không nếu không xét parameters.
10. **“Rule match đúng là đủ.”** Còn phải intercept đúng actual invocation.
11. **“Không có annotation nghĩa method không thể được instrument.”** Có thể chọn qua external rule.
12. **“External rule chọn class final thì subclass proxy luôn dùng được.”** Cơ chế proxy có giới hạn riêng.
13. **“Annotation ở interface tự là annotation ở implementation.”** Lookup semantics cần xác định.
14. **“Tất cả loại join point được hỗ trợ chỉ vì config mô tả được.”** Tool có giới hạn capability.
15. **“Một wildcard mới chỉ ảnh hưởng method hiện tại.”** Nó có thể match classes/methods được thêm về sau.
16. **“Config owner không cần code review vì chỉ thay text.”** Config có thể thay bảo mật/hành vi quan trọng.
17. **“Annotation review là đủ, không cần test.”** Chưa chứng minh advice thực sự chạy.
18. **“Thay policy giữa hai requests luôn atomic.”** Cần immutable snapshot/publication.
19. **“ThreadLocal current config tự lan qua executor.”** Không.
20. **“Trình đọc metadata runtime tự thấy CLASS/SOURCE annotations.”** Retention quyết định khả năng reflection.
21. **“Một record cache matcher có thể dùng bất kể classloader.”** Có thể sai type identity và leak loaders.
22. **“Tăng thread count sửa overhead của mọi advice.”** Global lock/I/O có thể vẫn nghẽn.
23. **“Trong code là static, bên ngoài là dynamic.”** Đây là hai trục độc lập.
24. **“Một proxy có thể can thiệp mọi private/self-call.”** JDK interface proxy chỉ thấy đường caller qua proxy.
25. **“Rule source đã đúng thì cả hệ thống không bị bypass.”** Need test mọi entry path.
26. **“Fail-open luôn ổn khi annotation/config bị thiếu.”** Không với authorization bắt buộc.
27. **“Sampling rates nên hardcode vào annotation ở mọi phương thức.”** Có thể làm migration vận hành khó.
28. **“Muốn thêm advice cho methods chưa woven chỉ cần reload config.”** Hook có thể chưa tồn tại.
29. **“Bản config mới chạy với binary cũ chắc phù hợp.”** Signature/version drift có thể phá matching.
30. **“`Set.copyOf` tự động kiểm business validity của rules.”** Nó chỉ sao chép collection theo contract Java.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Annotation và external config giống nhau ở điểm nào?  
**Đáp án:** Cả hai có thể làm nguồn dữ liệu để chọn join points; không tự chạy advice.

**Câu 2.** Vì sao `core.submit("A")` không có advice dù `Core.submit` có `@Observed`?  
**Đáp án:** Vì caller đi thẳng tới raw target, không qua proxy.

**Câu 3.** `externalV1.inspect()` có advice mà `byAnnotation.inspect()` không, vì sao?  
**Đáp án:** V1 chọn tên `inspect` qua rule ngoài, trong khi implementation method không có annotation `@Observed`.

**Câu 4.** Đổi method name có rủi ro nào với external selector?  
**Đáp án:** Selector cũ có thể match 0 methods hoặc chọn nhầm; cần validation và matched-set tests.

**Câu 5.** Annotation làm security tự an toàn không?  
**Đáp án:** Không. Cần enforcement tại trust boundary và test bypass.

**Câu 6.** Có thể thay config runtime để JDK interface proxy intercept private methods không?  
**Đáp án:** Không chỉ bằng config; proxy capability không hỗ trợ interception private execution.

**Câu 7.** Vì sao demo tạo `externalV2` thay vì sửa `externalV1`?  
**Đáp án:** Vì `Rule` dùng immutable snapshot; demo không thiết kế hot reload, nên tạo wrapper với policy khác để so sánh.

**Câu 8.** Có nên đọc YAML và compile regex ở mỗi invocation không?  
**Đáp án:** Thường không; parse/validate sớm, cache decisions phù hợp và đo overhead.

**Câu 9.** Hybrid model có giá trị gì?  
**Đáp án:** Marker annotation có thể ghi ý nghĩa ổn định ở source, external policy điều khiển knobs/concerns thay đổi theo vận hành.

**Câu 10.** Nếu rule ngoài match 0 methods nhưng syntax vẫn hợp lệ, có nên coi là thành công?  
**Đáp án:** Không mặc định; với policy bắt buộc cần fail-fast hoặc cảnh báo nghiêm trọng theo contract.

**Câu 11.** Khi có hai proxy cùng bao một core, việc chọn rule khác có làm hai cores xuất hiện?  
**Đáp án:** Không trong demo; cả hai delegate cùng core, `submissions=5` bao tổng lần thực thi.

**Câu 12.** Tại sao `this.submit("E")` không in advice?  
**Đáp án:** Internal call trên target không qua proxy, dù method được đánh dấu.

**Câu 13.** External config có thể tạo nguy cơ ngoài performance?  
**Đáp án:** Có, policy/bảo mật, dữ liệu nhạy cảm, version mismatch và thay đổi semantic.

**Câu 14.** Điều kiện nào cần trước khi tuyên bố “config không cần deploy”?  
**Đáp án:** Cần mechanism hỗ trợ runtime reload, atomic policy publication và coverage của join points được lựa chọn mới.

## 25. Tổng kết

**Đánh dấu trong mã** nhấn mạnh **ý định nằm sát declaration**, có lợi cho discoverability, code review và chọn method chính xác; đổi lại tăng phụ thuộc metadata vào source, cần sửa nhiều nơi khi chính sách thay đổi và có nguy cơ quên đánh dấu. **Cấu hình bên ngoài** nhấn mạnh **quản lý tập trung và tính điều chỉnh**, hỗ trợ crosscutting theo module/third-party code hoặc operational policy; đổi lại dễ lệch khi đổi signature/package, cần schema validation, chủ sở hữu policy và kiểm soát rollout/rollback.

Cả hai chỉ là **nguồn lựa chọn**. **Pointcut resolution** và **interception runtime** mới quyết định advice có thực sự chạy hay không. Ví dụ Java 17 đã xác minh cùng `Core` có thể được quan sát khác nhau khi chọn rule annotation hoặc rule ngoài, và việc có annotation trên `submit` không làm raw/self calls tự được can thiệp.

Lựa chọn tốt xuất phát từ **contract, mức độ quan trọng của concern, quyền quản lý policy và khả năng kiểm thử**, không phải sở thích cú pháp. Đối với hệ thống lâu dài, thường nên tách **semantic intent ổn định** khỏi **operational knobs dễ thay đổi**, gắn version cho rules và **kiểm cả positive lẫn negative join point coverage trên artifact thật**.