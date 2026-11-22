# Cảnh báo hoặc lỗi ở bước xây dựng để kiểm tra quy tắc kiến trúc trong AOP

Trong **Aspect-Oriented Programming (AOP – lập trình hướng khía cạnh)**, aspect không chỉ dùng advice để xử lý lời gọi ở runtime. Một số mô hình aspect kết hợp vào chương trình ở **compile-time hoặc post-compile weaving**, có khả năng kiểm tra những đặc điểm **cấu trúc mã và điểm nối tĩnh (static join point shadows)** ngay trong quá trình xây dựng. Khi một quy tắc kiến trúc bị vi phạm, công cụ có thể phát **warning** để người viết xem xét, hoặc **error** để từ chối tạo artifact.

Ví dụ, tổ chức phần mềm quy định **mã domain không được phụ thuộc trực tiếp vào implementation của tầng infrastructure**; hoặc một API legacy chỉ được sử dụng trong giai đoạn chuyển đổi. Thay vì chờ request thật chạy rồi quan sát log, một bộ kiểm tra ở bước build có thể phát hiện các **dependency type, chữ ký API, một số call site hoặc thay đổi cấu trúc type** theo khả năng phân tích của nó.

Bài thuộc nhóm **Thay đổi cấu trúc**: khi aspect có khả năng **introduction/inter-type declaration**, nó có thể bổ sung interface, member hoặc quan hệ type. Quy tắc kiến trúc cần mô tả **cấu trúc mong muốn trước/sau thay đổi**, không chỉ tập phương thức được advice chặn. Trọng tâm bài là thiết kế rule, chọn severity, định vị lỗi, phối hợp với weaving, xây bộ kiểm thử và đưa kết quả vào CI.

**Phạm vi:** kiến thức AOP cơ bản và nâng cao **nói chung**. Không tồn tại một cú pháp warning/error hay loại static join point duy nhất cho mọi công cụ AOP. Ví dụ Java 17 ở dưới dùng **Java Compiler API và annotation processor** để minh họa rõ cách tạo diagnostic thật từ source; processor này **không phải một bytecode weaver**, nhưng là cơ chế bổ trợ hữu ích khi kiến trúc cần kiểm tra type-level structure vượt ngoài khả năng của một pointcut.

## 1. Nền tảng: cấu trúc chương trình và thời điểm kiểm tra

- **Aspect:** tập hợp concern cắt ngang, pointcut/advice, đôi khi có khai báo thay đổi cấu trúc.
- **Join point:** điểm chương trình có thể can thiệp; ví dụ method call, method execution nếu mô hình hỗ trợ.
- **Pointcut:** điều kiện chọn tập join point; có phần xác định tĩnh và có phần phụ thuộc runtime.
- **Advice:** hành vi before/after/around hoặc dạng khác chạy tại join point được chọn.
- **Weaving:** kết hợp aspect vào source, compiled code, lúc load class hoặc qua proxy.
- **Introduction/inter-type declaration:** đưa member, interface hoặc một quan hệ cấu trúc vào type qua một cơ chế AOP có hỗ trợ.
- **Architecture invariant:** tính chất mà cấu trúc phần mềm phải bảo toàn, ví dụ chiều phụ thuộc giữa layer hoặc loại API được phép xuất hiện.
- **Build diagnostic:** warning/error được phát bởi compiler, weaver, processor hoặc analyzer lúc xây dựng.

Với nhiều aspect, cần phân biệt:
1. **Chọn điểm:** pointcut có thể chọn call site hoặc execution point nào.
2. **Thay đổi cấu trúc:** introduction có thể tạo một member/type relation mới.
3. **Kiểm chứng:** rule đọc source, type model, bytecode hoặc effective post-weave structure.
4. **Thi hành:** advice runtime vẫn cần khi điều kiện chỉ xác định được lúc chạy.

### 1.1 Static checking khác runtime advice

| Tiêu chí | Cảnh báo/lỗi khi build | Advice runtime |
| --- | --- | --- |
| Khi nào | Phân tích source, type hoặc bytecode | Khi invocation thật xảy ra |
| Có cần request? | Không | Có |
| Bằng chứng | Type dependency, chữ ký, static call, artifact structure | Args, identity, target, context, control flow |
| Kết quả | Diagnostic hoặc build failure | Log, đo đạc, trả kết quả hoặc exception |
| Giới hạn | Không biết đủ giá trị động, reflection, implementation nạp muộn | Có thể bị bypass nếu lời gọi không qua interception boundary |
| Chủ thể xử lý | Developer, build và CI | Caller, service, người vận hành |

Một lỗi kiến trúc tĩnh có thể được bắt trước khi chương trình chạy. Nhưng **PASS ở build không chứng minh mọi hành vi runtime được bảo vệ**. Ví dụ annotation “yêu cầu kiểm tra quyền” xuất hiện trong source không tự chứng minh người dùng thực sự có quyền khi một request chạy.

### 1.2 Các pha có thể xuất hiện quy tắc

~~~text
Source + architecture rules
          |
          v
Parse / symbol and type resolution
          |
          v
Static architecture checks
          |             |
       WARNING         ERROR
          |             |
          v             +--> build FAIL
Weaving / introductions (if supported)
          |
          v
Post-weave structural checks
          |
          v
Tests -> Package / release
~~~

Đây là **một pipeline khái niệm**. Không mặc định mọi công cụ thực hiện đúng thứ tự ấy: có hệ thống tích hợp weaving vào compiler, có hệ thống biến đổi binary sau compile hoặc chỉ runtime proxy. Một invariant nhắm tới **artifact sau weaving** cần được kiểm trên effective structure đúng pha; kiểm source trước introductions chưa đủ.

## 2. Warning và error cần phản ánh chính sách

### 2.1 Warning – cần review nhưng không tự cấm artifact

Warning hợp lý khi:
- API legacy còn được phép nhưng đang trong lộ trình chuyển đổi.
- Một type có dấu hiệu coupling hoặc naming convention đáng nghi.
- Một method có metadata chưa đầy đủ, cần đánh giá thủ công.
- Một call site có nguy cơ đi qua API cũ nhưng chưa chắc vi phạm.
- Một structural introduction có thể tạo điểm cần review trong bản tiếp theo.

Warning tốt có **mã rule, location, chứng cứ và gợi ý sửa**; warning mơ hồ dễ bị lờ đi khi số lượng lớn.

### 2.2 Error – cấm build khi bất biến bị phá

Error phù hợp khi policy đã có đủ bằng chứng:
- Domain tuyên bố field phụ thuộc concrete infrastructure type bị cấm.
- Public API để lộ một internal type bị cấm.
- Một introduction tạo type/member không hợp lệ theo quy tắc của compiler/weaver.
- Module dependency graph chứa cạnh hoặc cycle bị policy cấm.
- Một static method-call join point từ vùng domain đến API bị cấm, nếu analyzer đủ khả năng xác định.

Cần phân biệt **lỗi cấu trúc thật** với một nghi vấn runtime không chứng minh được từ source. Nếu rule có false positive lớn, không tự động nâng nó thành error mà chưa định nghĩa chính sách ngoại lệ.

### 2.3 Đưa warning thành error theo lộ trình

~~~text
Discover baseline -> Warn -> Fix new violations -> Reduce debt -> Enforce error
~~~

Lộ trình thực tế:
1. Thu thập kết quả rule trên clean build để có baseline.
2. Gỡ cảnh báo không chính xác, hoàn thiện matcher và tài liệu.
3. Chặn hoặc yêu cầu review đối với vi phạm **mới**.
4. Thu hẹp các ngoại lệ có owner và thời hạn.
5. Nâng thành error khi một invariant đã đủ rõ và áp dụng đồng nhất.

**Warning-as-error** là chính sách riêng. Trình biên dịch Java có tùy chọn **-Werror** trong hoàn cảnh phù hợp để warning làm build fail; các analyzer/weaver khác có cơ chế riêng. Không giả định mọi warning tự động dừng build.

## 3. Viết một architecture rule có thể kiểm chứng

Một rule nên có:

| Thành phần | Ví dụ |
| --- | --- |
| ID | ARC001 |
| Mục tiêu | Domain không phụ thuộc concrete infrastructure |
| Scope | Những type thuộc domain package |
| Điều kiện | Field khai báo kiểu thuộc infrastructure package |
| Severity | ERROR |
| Vị trí | Field gây phụ thuộc |
| Thông báo | domain depends on infrastructure |
| Hướng sửa | Đảo dependency qua abstraction thích hợp |
| Ngoại lệ | Có giới hạn, lý do và owner |
| Test | Một fixture PASS, một fixture FAIL |

Ví dụ **pseudo-rule**, không phải một ngôn ngữ cấu hình chung:

~~~text
ARCH-RULE ARC001:
    scope = types in demo.domain
    if declared field type belongs to demo.infra:
        ERROR "depend on an appropriate port instead"

ARCH-RULE ARC002:
    scope = types in demo.domain
    if declared field type belongs to demo.legacy:
        WARNING "review and migrate legacy dependency"
~~~

**Điều kiện phải hẹp và chính xác.** Hai rule trên chỉ kiểm **field type**. Chúng chưa chặn method call, constructor parameter, method return, generic type argument hoặc reflection. Không viết tài liệu “cấm mọi cách sử dụng infrastructure” khi implementation chỉ kiểm một dạng tham chiếu.

### 3.1 Rule call site phải quan sát đúng điểm gọi

Giả sử source có:

~~~text
domain.OrderService.submit()
         |
         +---- call infra.SqlRepository.persist()
                              ^
                              prohibited call edge
~~~

Nếu invariant cấm **dependency từ caller domain sang callee infra**, một rule về **method call** có thể hữu ích. Chỉ chọn **method execution** của persist không đủ kết luận **caller thuộc layer nào**.

Một số ngôn ngữ AOP cho phép khai báo warning/error khi một **static pointcut** match call site có thể xác định tại build, ví dụ ý tưởng:

~~~text
aspect ArchitectureGuard:
    when domain-layer call site targets an infrastructure API:
        declare ERROR "[ARC001] Direct call prohibited"

    when a visible call uses legacy API:
        declare WARNING "[ARC002] Legacy call requires review"
~~~

**Đây là giả mã**, không phải cú pháp tương thích mọi trình biên dịch AOP. Static call matching phụ thuộc call-join-point semantics, owner type, symbol resolution, classpath và các quy tắc generated/bridge methods.

### 3.2 Rule type-level không nhất thiết là pointcut

Muốn kiểm các yêu cầu như:
- Một class phải implement đúng interface.
- Public API không được expose implementation type.
- Class thuộc package A không được khai báo field thuộc package B.
- Một type không được có member bị trùng do introduction.

Ta có thể dùng **type checker, annotation processor, AST analyzer hoặc bytecode scanner** thay vì ép mọi thứ thành một pointcut. Architecture governance có thể là sự phối hợp nhiều loại công cụ, miễn chứng cứ và thời điểm chạy rõ ràng.

## 4. Ví dụ Java 17 có diagnostic thật khi biên dịch

Chương trình **BuildArchitectureRulesDemo.java** chạy một compilation task trong bộ nhớ bằng **Java Compiler API**. Một **annotation processor** duyệt field của type demo.domain.OrderService và:
- Cho phép field kiểu **demo.port.Store**.
- Phát **ERROR ARC001** nếu field kiểu **demo.infra.***.
- Phát **WARNING ARC002** nếu field kiểu **demo.legacy.***.

Ví dụ này **không là một Aspect compiler/weaver**; nó dạy cơ chế build-time diagnostics mà một hệ thống kiểm soát quy tắc kiến trúc có thể áp dụng bên cạnh AOP. Với rule kiểm **static call join point**, cần analyzer thích hợp hơn cho method body hoặc bytecode.

Lưu nguyên file sau với tên **BuildArchitectureRulesDemo.java**:

~~~java
import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class BuildArchitectureRulesDemo {
    static final class Source extends SimpleJavaFileObject {
        final String source;

        Source(String className, String source) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + JavaFileObject.Kind.SOURCE.extension),
                  JavaFileObject.Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreErrors) {
            return source;
        }
    }

    @SupportedAnnotationTypes("*")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class ArchitectureProcessor
            extends AbstractProcessor {
        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment round) {
            if (round.processingOver()) return false;

            for (Element type : round.getRootElements()) {
                if (!(type instanceof TypeElement t)
                        || !t.getQualifiedName().contentEquals(
                                "demo.domain.OrderService")) {
                    continue;
                }

                for (Element field : t.getEnclosedElements()) {
                    if (field.getKind() != ElementKind.FIELD) continue;
                    String usedType = field.asType().toString();

                    if (usedType.startsWith("demo.infra.")) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "ARC001 domain depends on infrastructure: "
                                    + usedType,
                            field);
                    } else if (usedType.startsWith("demo.legacy.")) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.WARNING,
                            "ARC002 review legacy dependency: "
                                    + usedType,
                            field);
                    }
                }
            }
            return false;
        }
    }

    static void check(String scenario, boolean bad) {
        List<JavaFileObject> files = new ArrayList<>();
        files.add(new Source("demo.port.Store",
                "package demo.port; public interface Store {}"));
        files.add(new Source("demo.infra.SqlStore",
                "package demo.infra; public class SqlStore {}"));
        files.add(new Source("demo.legacy.LegacyClient",
                "package demo.legacy; public class LegacyClient {}"));

        String fields = bad
                ? "demo.infra.SqlStore sql; "
                  + "demo.legacy.LegacyClient legacy;"
                : "demo.port.Store store;";
        files.add(new Source("demo.domain.OrderService",
                "package demo.domain; public class OrderService { "
                + fields + " }"));

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK required");
        }

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();
        JavaCompiler.CompilationTask task = compiler.getTask(
                null, null, collector,
                List.of("-proc:only", "--release", "17"),
                null, files);
        task.setProcessors(List.of(new ArchitectureProcessor()));

        boolean successful = Boolean.TRUE.equals(task.call());
        System.out.println("CASE " + scenario);

        collector.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR
                        || d.getKind() == Diagnostic.Kind.WARNING)
                .map(d -> d.getKind().name() + " "
                        + d.getMessage(Locale.ROOT))
                .sorted(Comparator.naturalOrder())
                .forEach(System.out::println);

        System.out.println(
                "RESULT " + (successful ? "PASS" : "FAIL"));
    }

    public static void main(String[] args) {
        check("allowed", false);
        check("violation", true);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --release 17 BuildArchitectureRulesDemo.java
java BuildArchitectureRulesDemo
~~~

Output đã đối chiếu bằng việc biên dịch và chạy mã Java:

~~~text
CASE allowed
RESULT PASS
CASE violation
ERROR ARC001 domain depends on infrastructure: demo.infra.SqlStore
WARNING ARC002 review legacy dependency: demo.legacy.LegacyClient
RESULT FAIL
~~~

### 4.1 Vì sao allowed PASS?

Type **demo.domain.OrderService** chỉ có field **demo.port.Store**. Đây là một abstraction được cho phép theo policy của ví dụ. Processor không phát diagnostic, nên compilation task thành công.

**Giới hạn:** việc phụ thuộc một interface không tự bảo đảm architecture hoàn hảo; nó chỉ **không vi phạm** các rule đã được định nghĩa.

### 4.2 Vì sao violation có cả error và warning?

Hai field trong phiên bản vi phạm được kiểm bởi hai điều kiện:
- Concrete dependency **demo.infra.SqlStore** → ERROR ARC001.
- Legacy dependency **demo.legacy.LegacyClient** → WARNING ARC002.

Một error khiến compilation task trả thất bại. Warning vẫn được thu nhận và hiển thị, không tự làm build fail khi không có error hoặc chính sách warning-as-error.

Diagnostic được sắp xếp khi hiển thị nhằm có **stdout xác định**. Bản thân builder/analyzer production nên định nghĩa một cách ghi kết quả có thể tái lập.

### 4.3 Vì sao dùng -proc:only?

Tùy chọn **-proc:only** chạy annotation processing mà không sinh artifact class output của một compilation thông thường. Trong demo, điều này phù hợp để phân biệt **bước kiểm tra** với **bước đóng gói**. Build production có thể đặt checker trong compiler thật hoặc một build step riêng; không bắt buộc dùng tùy chọn này cho mọi dự án.

### 4.4 Phạm vi giới hạn của processor

Processor này cố ý chỉ xét:
- **Một type duy nhất**, đúng tên demo.domain.OrderService.
- **Những field** được khai báo trên type.
- **Chuỗi tên kiểu field** bắt đầu bằng demo.infra. hoặc demo.legacy.

Nó **không** kiểm:
- Constructor/method parameter hay return types.
- Method calls trong thân hàm.
- Generics với loại bị cấm nằm trong type arguments.
- Import không được dùng, reflection, dynamic class loading.
- Toàn bộ class thuộc domain package khác.
- Type hierarchy sau một AOP structural introduction.
- Runtime authorization, cache bypass hoặc async behavior.

Bởi vậy **PASS của demo không phải chứng chỉ kiến trúc toàn ứng dụng**. Một analyzer production phải duyệt đầy đủ các kinds đã cam kết và kiểm đúng representation.

## 5. Cảnh báo/lỗi khi structural introductions thay đổi type

Một ngôn ngữ AOP có thể **thêm interface hoặc method** vào type thông qua introduction. Ví dụ khái niệm:

~~~text
Before weaving:
  class Ledger { ... }

Structural introduction:
  add interface Auditable to Ledger
  add auditKey() member to Ledger

After weaving:
  Ledger implements Auditable
  Ledger has auditKey()
~~~

Cần xác định quy tắc:
1. Có cho phép một aspect thay public API của Ledger không?
2. Nếu Ledger đã có method auditKey với chữ ký không tương thích, compiler báo gì?
3. Type được giới thiệu có thuộc đúng architectural layer không?
4. Member mới có tạo direct dependency từ domain sang infra không?
5. Rule kiểm **source trước weave** hay **effective structure sau weave**?
6. Pointcut khác có chọn member mới không, và có tạo recursion/advice overlap không?

**Không có quy tắc cố định mọi introduction đều được phép hay bị cấm.** Lỗi/cảnh báo phải theo invariant được chủ sở hữu kiến trúc định nghĩa.

### 5.1 Pre-weave vs post-weave là hai câu hỏi khác

| Pha | Ví dụ invariant | Hạn chế |
| --- | --- | --- |
| Trước weave | Source domain không khai báo direct infra field | Chưa nhìn thấy member được đưa thêm |
| Sau weave | Effective Ledger thật sự implement Auditable | Phụ thuộc pipeline và metadata sau weaving |
| Sau compile/classfile | Classfile không có dependency cấm | Có thể mất thông tin source-level hữu ích |
| Runtime | Audit thật sự phát event ở invocation phù hợp | Không thể suy từ chỉ một type declaration |

Nếu checker chạy trước introduction nhưng invariant nói về **artifact sau weaving**, kết quả PASS chỉ là **kiểm một pha**, không chứng minh trạng thái cuối.

### 5.2 Thứ tự nhiều transformation

Một weaver A có thể đưa thêm method mà weaver B dùng để lựa chọn join point; đổi thứ tự xử lý có thể thay tập điểm B nhìn thấy. Khái niệm:

~~~text
W2(W1(Program)) may differ from W1(W2(Program))
~~~

Do đó cần quản lý build order, version, classpath, mã sinh và quy tắc reweaving theo công cụ thật. Đừng mặc định các phép biến đổi giao hoán hoặc cùng artifact được weave lại nhiều lần mà không thay hành vi.

## 6. Chất lượng rule: loại false positive và false negative

**False positive:** rule báo vi phạm khi cấu trúc hợp lệ theo policy.

**False negative:** một cấu trúc bị cấm không được báo.

Nguyên nhân thường gặp:
- So khớp tên class bằng substring không resolve symbol.
- Nhầm package/tên trùng trong các module khác nhau.
- Bỏ sót constructor parameters hoặc API return types.
- Bỏ sót nested generic types và arrays.
- Không phân biệt method call và method execution.
- Bỏ sót code generation ở pha sau.
- Không nhìn thấy reflection/dynamic loading.
- Scanner trên source chưa biết hierarchy được introduction thay đổi.
- Cache của incremental build giữ metadata cũ.
- Rule bị disable/suppress ngoài ý định.

**Kiểm tra bằng symbol/type model** thường đáng tin hơn tìm chuỗi trong source comment. Nhưng ngay cả type model cũng cần quyết định rõ **kiểu khai báo** khác gì **implementation runtime** khi kiểm dependency.

### 6.1 Mô tả đúng độ phủ

Một architecture report nên cho biết:
- Tập source/module được kiểm.
- Số type/call sites được quan sát.
- Rule IDs nào enabled.
- Những loại dependency có kiểm và không kiểm.
- Số warning/error/suppression theo ID.
- Analyzer chạy pre-weave hay post-weave.
- Classpath, generated sources và build variant.
- Có clean/incremental validation hay không.

Nếu checker không chạy, **không thấy lỗi không phải PASS**. CI nên fail nếu checker bắt buộc bị bỏ qua do plugin bị tắt hoặc task không được thực thi.

## 7. Fixture kiểm thử: đúng phải pass, sai phải fail

Một rule tốt phải có test theo cả hai hướng.

| Test | Expected |
| --- | --- |
| Domain field tham chiếu port được phép | PASS |
| Domain field tham chiếu concrete infra | ERROR ARC001, build FAIL |
| Domain field tham chiếu legacy API | WARNING ARC002 |
| Một type hợp lệ cùng simple name nhưng khác package | Không báo nhầm |
| Domain constructor nhận infra khi rule đã bao phủ constructor | ERROR của rule mở rộng |
| Domain public API trả infra type nếu cấm | ERROR |
| Static call từ domain tới method infra nếu rule call hỗ trợ | ERROR |
| Reflection string chỉ chứa chữ SqlStore | Không báo nhầm như type reference |
| Introduction hợp lệ | PASS post-weave |
| Introduction tạo member conflict | ERROR nếu compiler/weaver quy định |
| Source sau khi sửa dependency bị cấm | PASS ở clean và incremental |
| Processor không chạy dù bắt buộc | CI FAIL về cấu hình kiểm tra |

### 7.1 Kiểm tra boundary có giá trị cao

- **Overload:** các method cùng tên nhưng parameter types khác nhau.
- **Generic erasure:** bridge methods có thể xuất hiện trong bytecode.
- **Inner/nested types:** package, visibility và target name resolution.
- **Interface call:** một call qua interface có thể dẫn tới concrete runtime implementation khác.
- **Default method:** rules static phải rõ điểm call/execution được kiểm.
- **Generated source:** thứ tự tạo mã và phân tích có thể khác.
- **Reflection:** một type có thể được load không có direct dependency được scanner phát hiện.
- **Multi-module:** analyzer có thực sự biết dependency graph đầy đủ không?

Không viết một rule “forbid ALL runtime calls to module X” rồi chỉ scan source text cho tên module X. Hãy giới hạn câu chữ theo bằng chứng có thể nhận diện và bổ sung runtime controls khi cần.

## 8. Tổ chức CI và xử lý kết quả

Một pipeline chặt chẽ có thể có:

~~~text
compile inputs
  |
  +--> source/type architecture checks
  |
  +--> aspect weaving / structural checks
  |
  +--> bytecode consistency checks
  |
  +--> unit/integration/architecture regression tests
  |
  +--> package artifact only if required checks pass
~~~

### 8.1 Chính sách thực thi

- **ERROR:** bất biến bắt buộc bị phá → không phát hành.
- **WARNING:** hiển thị, triage, có owner; fail CI chỉ khi policy yêu cầu.
- **CHECKER FAILED:** lỗi tool/config khác rule violation; không im lặng coi PASS.
- **CHECKER SKIPPED:** không được coi như đã kiểm.
- **SUPPRESSION:** phải có lý do, scope cụ thể, thời hạn; không tắt toàn bộ rule không kiểm soát.

### 8.2 Diagnostic hữu ích hơn một thông báo chung

Một thông báo đề xuất:

~~~text
ERROR ARC001
At: demo.domain.OrderService.sql
Observed: demo.infra.SqlStore
Invariant: domain must not directly reference infrastructure types
Suggestion: introduce a domain-owned port and wire adapter elsewhere
~~~

Đây **không phải stdout của demo**, mà là mẫu thông báo phát triển. Các rule cần ghi **vị trí thật** khi compiler có metadata vị trí nguồn; sử dụng phần tử field ở processor giúp compiler gắn diagnostic đến thành phần liên quan.

### 8.3 Warning baseline và suppression

Nếu hệ thống đã có nhiều vi phạm legacy:
- Chỉ cho baseline những trường hợp được phê duyệt.
- Ngăn baseline tăng tự do.
- Yêu cầu lý do và hạn chót của suppression.
- Không suppress lỗi bắt buộc nếu policy không cho phép.
- Có báo cáo theo thời gian để giảm nợ kiến trúc.
- Khi rule đổi semantics, chạy lại fixture và baseline thay vì tin danh sách suppress cũ.

## 9. Clean build so với incremental build

Một source change có thể làm thay đổi type hierarchy hoặc call edges ở nhiều module. Nếu build incremental không invalidates các kết quả liên quan, checker có thể **không báo lỗi mới**, trong khi clean build lại FAIL.

Kiểm thử pipeline:
1. Clean build với code hợp lệ → PASS.
2. Thêm dependency bị cấm → ARC001 ERROR, FAIL.
3. Gỡ dependency → PASS.
4. Thay interface hoặc structural introduction dùng chung → các consumer liên quan phải được recheck.
5. Chạy cùng chuỗi trên incremental build → kết quả rule nhất quán.
6. Xác minh artifact cuối đã dùng đúng code và thứ tự weaver.

Nếu một rule kiểm **post-weave member** nhưng CI chỉ chạy pre-weave task, đó là lỗi cấu hình kiểm tra, không phải một bằng chứng kiến trúc hợp lệ.

### 9.1 Dependency và precedence cycles

Một graph architecture có thể có cạnh module A→B, B→C, C→A. Nếu policy yêu cầu DAG, analyzer cần phát hiện cycle và báo đường cụ thể.

Nhưng cần phân biệt:
- **Module dependency cycle:** vòng ở type/package/module graph.
- **Advice precedence cycle:** ràng buộc A ngoài B, B ngoài C, C ngoài A; không có thứ tự hợp lệ.
- **Runtime recursion:** advice gọi helper bị chính pointcut chọn lại.

Ba loại này không thể được xử lý chỉ bằng một phép sort đơn giản trên danh sách aspect. Một rule build-time phải nêu rõ **loại cạnh** nó thực sự phân tích.

## 10. Phối hợp với kiểm soát runtime

Một kiến trúc sạch vẫn có thể xuất hiện lỗi:
- Direct target call bypass proxy advice.
- Around advice ngoài short-circuit và bỏ qua kiểm tra quyền bên trong.
- Async completion xảy ra sau method return nên after-returning chạy sớm.
- Cache trả dữ liệu của tenant khác do cache key thiếu thành phần.
- Reflection hoặc dynamic classloading kích hoạt implementation chưa được kiểm.
- Retry lặp lại side effect không idempotent.

Các trường hợp này cần **runtime authorization, validation, tracing hoặc kiểm thử** đúng cách; static warning/error không thể thay thế. Ngược lại, runtime advice cũng không tự bảo đảm mọi structural dependency sạch.

Chính sách kiến trúc nên chia:
- **Static rule:** những điều compiler/weaver/analyzer có thể chứng minh.
- **Runtime invariant:** những điều phụ thuộc identity, args, flow, side effects hoặc môi trường.
- **Test coverage:** chứng minh mọi đường vào cần thiết thực sự được kiểm soát.

## 11. Các ngộ nhận thường gặp

1. **“AOP chỉ có runtime advice.”** Một số cơ chế hỗ trợ khai báo cấu trúc và diagnostics ở build.
2. **“Mọi AOP proxy tự báo lỗi kiến trúc khi compile.”** Không, khả năng phụ thuộc mô hình.
3. **“Warning luôn phải fail.”** Chỉ khi policy warning-as-error được áp dụng.
4. **“Error luôn là lỗi cú pháp.”** Có thể là lỗi custom architectural rule.
5. **“Không thấy ARC001 là không còn dependency.”** Chỉ đúng theo scope checker đã chạy.
6. **“Processor field-only bắt được method calls.”** Không.
7. **“Một method execution pointcut cho biết caller nào vi phạm.”** Chưa đủ nếu invariant về call direction.
8. **“Pre-weave PASS bảo đảm mọi member post-weave đúng.”** Không.
9. **“Một interface introduction luôn giải dependency sai.”** Không nếu quan hệ thực vẫn bị cấm.
10. **“Static analysis luôn nhận ra reflection và mọi implementation runtime.”** Không.
11. **“Chỉ cần 1 test vi phạm.”** Phải có positive và boundary fixtures.
12. **“Cấu hình checker không chạy thì mặc định PASS.”** Phải coi chưa được kiểm chứng.
13. **“Incremental PASS chắc giống clean PASS.”** Cần kiểm cache và invalidation.
14. **“Tất cả warning nên được suppress cho sạch output.”** Làm mất giá trị triage.
15. **“Làm warning thành error là thay được security runtime.”** Không.
16. **“Một rule có tên chung sẽ tự bao phủ mọi loại dependency.”** Cần ghi đúng data model và phạm vi.
17. **“Generated code không đáng quan tâm.”** Có thể là artifact cuối bị policy ràng buộc.
18. **“Chỉ thay thứ tự weaving là giải mọi conflict.”** Một invariant mâu thuẫn vẫn không có lời giải.
19. **“Một diagnostic không có ID/vị trí vẫn đủ.”** Thiếu khả năng tra cứu và sửa nhanh.
20. **“PASS ở build nghĩa hệ thống không thể vi phạm lúc chạy.”** Static và dynamic proof khác nhau.

## 12. Checklist cho một bài thực hành và triển khai thực tế

- [ ] Viết invariant kiến trúc bằng câu ngắn có thể bác bỏ.
- [ ] Chỉ rõ source, typed AST, compiled bytecode hay effective post-weave type được kiểm.
- [ ] Xác định scope: type, field, method signature, call site hoặc execution join point.
- [ ] Chọn severity WARNING/ERROR nhất quán với policy.
- [ ] Gán mã rule, vị trí, observed type/call và hướng sửa.
- [ ] Chọn AOP declaration nếu model hỗ trợ; dùng processor/analyzer bổ trợ khi cần.
- [ ] Kiểm tra quá trình structural introduction có thay representation hay không.
- [ ] Viết test hợp lệ PASS và vi phạm FAIL.
- [ ] Viết test riêng cho warning không fail trong chính sách mặc định.
- [ ] Viết boundary cases: overload, generics, reflection, generated code, module graph.
- [ ] Xác minh checker luôn chạy trong CI và không bị skip.
- [ ] Chạy clean + incremental builds để phát hiện cache stale.
- [ ] Quản lý suppressions/baseline bằng owner và ngày hết hạn.
- [ ] Không log dữ liệu nhạy cảm trong diagnostics hoặc test.
- [ ] Bảo toàn runtime authentication/authorization ngoài quy tắc tĩnh.
- [ ] Không tạo artifact release nếu một invariant bắt buộc FAIL.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Domain khai báo field concrete infra, policy cấm. Warning hay error?

**Đáp:** ERROR nếu ràng buộc bắt buộc có chứng cứ rõ, như ARC001.

**Câu 2.** Một legacy API còn được dùng trong migration, muốn đánh dấu để review?

**Đáp:** WARNING phù hợp; có thể nâng thành ERROR khi policy cấm sử dụng.

**Câu 3.** Processor demo có kiểm method body calls không?

**Đáp:** không. Nó chỉ duyệt field trong một type. Cần AST/call analysis hoặc bytecode scanner để kiểm lời gọi.

**Câu 4.** Tại sao một rule cấm call từ domain tới infra cần phân biệt call và execution?

**Đáp:** invariant nói về **hướng dependency** từ caller. Execution của callee không tự xác định một call site bị cấm.

**Câu 5.** Type được AOP thêm interface sau khi analyzer đã chạy. PASS trước weave chứng minh type cuối đã implement interface chưa?

**Đáp:** chưa; cần kiểm effective post-weave structure.

**Câu 6.** Tại sao warning trong output demo không phải lý do duy nhất của RESULT FAIL?

**Đáp:** có ARC001 ERROR. Warning không mặc định fail nếu không có warning-as-error.

**Câu 7.** Cùng source mà clean build báo ARC001, incremental build không báo. Có đủ an toàn để release?

**Đáp:** chưa. Phải kiểm cache/invalidation và bảo đảm task checker quan sát đúng representation.

**Câu 8.** Nếu người dùng runtime không được phân quyền, error về package dependency có bảo vệ được không?

**Đáp:** không. Static architecture rule không tự kiểm tra identity và permission runtime.

**Câu 9.** Nếu checker đã bị tắt nhưng output không có lỗi, đó có phải PASS?

**Đáp:** không. Đó là **chưa được kiểm tra**, phải có chính sách fail cho bước bắt buộc.

**Câu 10.** Vì sao một architecture rule cần cả fixture hợp lệ?

**Đáp:** để phát hiện false positive, đảm bảo rule không chặn các trường hợp nằm trong chính sách cho phép.

## 14. Kết luận

**Cảnh báo hoặc lỗi ở bước xây dựng để kiểm tra quy tắc kiến trúc** giúp biến kiến trúc từ văn bản hướng dẫn thành **hệ ràng buộc có thể kiểm tra tự động**. Trong AOP có thay đổi cấu trúc, điều này đặc biệt quan trọng vì các introduction hoặc bước weaving có thể khiến type và tập join point sau build khác source ban đầu.

Để thiết kế đúng:
1. **Xác định invariant và pha phân tích trước khi viết rule.**
2. **Warning phục vụ review; error chặn vi phạm không được phép.**
3. **Rule phải có chứng cứ, ID, vị trí và bộ test hai chiều.**
4. **Không hứa quá khả năng phân tích tĩnh hoặc dùng nó thay security runtime.**
5. **Đưa kiểm tra vào CI, quản lý baseline và đối chiếu clean/incremental builds.**

Ghi nhớ: **Một build PASS chỉ có ý nghĩa khi biết checker thực sự đã chạy trên đúng cấu trúc, đúng phạm vi và đúng phiên bản artifact.**
