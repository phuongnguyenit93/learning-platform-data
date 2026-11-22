# Thay đổi aspect và nhu cầu xây dựng hoặc khởi động lại

Khi sửa một **aspect** trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), hệ thống có cần **biên dịch lại, dệt lại, đóng gói lại, triển khai lại hoặc khởi động lại** hay không? Câu trả lời phụ thuộc trước hết vào **thời điểm weaving (dệt)** và **loại thay đổi**. Không có quy tắc “sửa aspect luôn phải restart” hoặc “sửa pointcut là tự cập nhật ngay” đúng cho mọi hệ thống.

Cần phân biệt những việc sau:

- **Sửa định nghĩa:** mã advice, biểu thức pointcut, khai báo ưu tiên, cấu hình bật/tắt hoặc thành viên được thêm vào lớp.
- **Tạo artifact mới:** biên dịch aspect, biên dịch lại lớp liên quan, dệt lại mã nguồn/bytecode và đóng gói.
- **Đưa artifact vào môi trường thực thi:** cập nhật class/JAR, bộ nạp lớp hoặc chuỗi proxy.
- **Làm thay đổi chương trình đang chạy:** restart tiến trình, tạo class loader mới, xây lại proxy hoặc dùng cơ chế instrumentation hỗ trợ biến đổi lớp đã nạp.

**Mấu chốt:** thay tệp `.class`/`.jar` trên đĩa **không tự thay thế định nghĩa class đã được JVM nạp**. Ngược lại, nếu một advice **đã được lắp vào đường gọi** chỉ cần kiểm tra một cờ cấu hình động, người vận hành có thể thay hành vi advice **mà không thay pointcut hoặc dệt lại bytecode**. Hai tình huống này khác nhau về cấu trúc và rủi ro.

Bài tập trung vào **AOP tổng quát**, lấy Java 17 để minh họa các ranh giới về class loading và một mô hình wrapper runtime. Cú pháp cấu hình, khả năng reweaving và hot reload phải được xác minh theo công cụ cụ thể.

## 1. Từ aspect đến hành vi đang chạy

Một **aspect** nhóm các mối quan tâm xuyên suốt, có thể gồm:

- **Pointcut:** lựa chọn những join point (điểm nối) mà mô hình AOP hỗ trợ.
- **Advice:** hành vi chạy trước, sau hoặc bao quanh các điểm được chọn.
- **Precedence/ordering:** thứ tự kết hợp khi nhiều advice cùng khớp.
- **State/lifecycle:** trạng thái của aspect, phạm vi instance và cách lưu trữ nếu có.
- **Inter-type declarations hoặc cơ chế mở rộng kiểu:** trong những hệ thống AOP hỗ trợ thêm thành viên/quan hệ kiểu.

Một thay đổi có thể xảy ra ở **tập điểm**, **nội dung xử lý** hoặc **cách điều phối**:

| Thứ được sửa | Ví dụ | Phần có thể cần cập nhật |
| --- | --- | --- |
| Thân advice | Đổi cách đo thời gian, thay logic audit | Mã advice hoặc interceptor đang được chạy |
| Pointcut | Từ chọn `pay()` sang chọn cả `refund()` | Tập join point được weave/chặn |
| Precedence | Đưa Authorization ra ngoài Cache | Chuỗi advice và hành vi short-circuit |
| Cấu hình runtime | Bật log bổ sung ở advice đã có sẵn | Giá trị cấu hình nếu advice đọc động |
| Kiểu hoặc chữ ký | Advice phụ thuộc method signature mới | Biên dịch, weaving và kiểm tra tương thích |
| Thành viên được sinh vào class | Thêm field/method mới khi nền tảng hỗ trợ | Cấu trúc class sau dệt, có thể vượt khả năng hot redefine |
| Thư viện phụ thuộc | Nâng version JAR chứa aspect | Classpath, artifact, loader, tương thích runtime |

Không được lấy thay đổi một **cờ bật/tắt** làm bằng chứng rằng có thể thêm một **join point mới** vào những class đã nạp. Bật/tắt chỉ thay đổi hành vi của phần đã có thể được gọi tới.

## 2. Bốn thời điểm/cách kết hợp AOP và hệ quả khi sửa aspect

| Cơ chế | Sửa advice/pointcut thường yêu cầu | Đưa thay đổi vào tiến trình đang chạy |
| --- | --- | --- |
| **Compile-time weaving** | Biên dịch/dệt lại những nguồn và lớp bị ảnh hưởng; đóng gói lại | Thường triển khai artifact mới và restart hoặc chuyển sang phiên bản được loader mới nạp |
| **Post-compile/binary weaving** | Dệt lại class/JAR đã biên dịch với aspect mới; tạo artifact mới | Phải bảo đảm runtime nạp bản woven mới; thay JAR trên đĩa không tự đổi lớp đang chạy |
| **Load-time weaving** | Chuẩn bị aspect/cấu hình mới cho loader/agent; đôi khi cần compile aspect | Chủ yếu tác động **lớp được nạp sau đó**; lớp đã nạp thường cần restart/reload hoặc cơ chế redefine/retransform riêng |
| **Runtime proxy/wrapper** | Cấu hình/build lại chuỗi chặn tùy cách thiết kế | Có thể đổi hành vi động nếu proxy đọc cấu hình/handler thay được; proxy tĩnh hoặc điểm chưa được bọc có thể cần tái tạo/redeploy |

Bảng này nêu **khuynh hướng kiến trúc**, không phải cam kết cho mọi triển khai. Có hệ thống hỗ trợ deployment không cần dừng toàn tiến trình bằng cách nạp phiên bản mới trong **class loader khác**; có hệ thống chỉ cho restart. Có công cụ weaving hỗ trợ reweaving hoặc runtime instrumentation; cần phân biệt tính năng đó với **load-time weaving thông thường**.

### 2.1 Vì sao “biên dịch lại” không bằng “khởi động lại”?

- **Recompile:** tạo lại mã trung gian hoặc bytecode từ nguồn.
- **Reweave:** chạy bộ dệt để tạo artifact chứa advice theo pointcut mới.
- **Repackage/redeploy:** phát hành và đặt artifact mới vào môi trường.
- **Reload:** nạp định nghĩa/phiên bản mới qua một ranh giới loader phù hợp.
- **Restart:** kết thúc tiến trình hoặc instance và bắt đầu lại với artifact/cấu hình mới.
- **Runtime redefinition/retransformation:** dùng khả năng đặc biệt của JVM/agent để sửa định nghĩa lớp **đã nạp**, trong giới hạn hỗ trợ.

Một thay đổi có thể hoàn tất ở bước build nhưng **chưa được JVM đang chạy sử dụng**. Ngược lại, đổi cấu hình động trong một advice đã được triển khai có thể không tạo artifact mới nào.

## 3. Compile-time weaving: đổi aspect thường phải xây dựng lại

Trong **dệt ở thời điểm biên dịch**, compiler/weaver tạo ra bytecode đã có advice:

~~~text
Source business + Aspect source/config
                  |
                  v
               Compile/weave
                  |
                  v
             Woven classes/JAR
                  |
                  v
           Deploy + start runtime
~~~

Khi đổi **thân advice**, phải đưa mã advice mới vào những artifact chạy nó. Khi đổi **pointcut**, một lớp từng **không** được weave có thể phải chịu advice và một lớp từng khớp có thể phải được loại bỏ instrumentation cũ; do đó chỉ compile lại riêng class chứa aspect **có thể không đủ**.

Ví dụ trước đây pointcut chọn execution của `BillingService.pay`. Sau khi đổi để chọn thêm `BillingService.refund`, lớp chứa `refund` cần xuất hiện trong **tập weaving mới**. Nếu một incremental build chỉ biên dịch lại source của aspect rồi dùng class nghiệp vụ woven cũ, kết quả có thể thiếu advice tại `refund`.

Nguyên tắc:

1. Phân tích **phụ thuộc giữa aspect, pointcut và class ứng viên**.
2. Đảm bảo incremental build invalidates tất cả artifact chịu tác động.
3. Chạy lại weaving hoặc build đầy đủ theo quy trình được công cụ hỗ trợ.
4. Kiểm tra class/JAR đầu ra và test runtime.
5. Triển khai bản mới để tiến trình thực thi nó.

### 3.1 Thay đổi kiểu mà advice thêm vào chương trình

Một số hệ thống AOP cho phép khai báo thêm **method, field hoặc quan hệ kiểu** trong quá trình dệt. Nếu mã nghiệp vụ cần biên dịch dựa trên thành viên được thêm, phần weaving phải xảy ra đủ sớm để compiler nhận biết chúng.

Sửa loại khai báo này thường ảnh hưởng **cấu trúc lớp** chứ không chỉ thân phương thức. Không nên coi nó như bật một cờ log động. Hot redefine trên JVM tiêu chuẩn còn có các giới hạn riêng đối với thay đổi cấu trúc.

### 3.2 Có phải restart cả máy chủ?

Không nhất thiết **cả máy hoặc toàn cụm**. Thực tế có thể deploy nhiều instance song song rồi chuyển lưu lượng sang instance mới (rolling/canary deployment). Nhưng mỗi JVM instance chạy bản cũ thường phải **ngừng dùng định nghĩa lớp cũ** theo cách hợp lệ: restart process, thay application class loader hoặc một cơ chế cập nhật được hỗ trợ. Triển khai một JAR mới vào thư mục không tự nâng cấp những instance cũ.

## 4. Post-compile weaving: sửa aspect làm thay đổi artifact nhị phân

**Binary weaving** nhận class/JAR đã biên dịch rồi tạo bản woven. Khi thay advice hoặc pointcut:

~~~text
UNWOVEN library/app binaries
             +
UPDATED aspect definitions
             |
             v
         Binary weaver
             |
             v
       NEW woven artifact
             |
             v
         Test / publish
             |
             v
    Runtime loads new artifact
~~~

Các điểm cần lưu ý:

- Nếu **input unwoven** vẫn như cũ, thường không cần biên dịch lại source nghiệp vụ; cần **dệt lại binary với định nghĩa aspect mới**.
- Nếu **aspect được lưu dưới dạng source**, nó có thể phải compile như một phần bước weave.
- Nếu input là JAR bên thứ ba, phải giữ **JAR gốc** để tái tạo bản woven khi pointcut thay đổi.
- **Không weave lại lên output cũ** một cách tùy tiện: reweaving/idempotency phụ thuộc công cụ, có thể báo lỗi hoặc tạo kết quả khác.
- Sau khi tạo woven JAR mới, phải kiểm tra **runtime thực sự nạp** bản mới, không phải artifact cũ trong classpath/container.
- Các class đã được nạp trong JVM không tự đổi khi JAR được thay trên đĩa.

### 4.1 Build cache rất dễ gây bản woven không đồng nhất

Một cache key dành cho bước dệt nên phản ánh ít nhất:

- Hash/version của **input class/JAR**.
- Phiên bản và nội dung aspect hoặc aspect JAR.
- Cấu hình pointcut, precedence, include/exclude filters.
- Phiên bản weaver, JDK/class-file target.
- Classpath/module path và các dependency ảnh hưởng đến match.
- Tùy tool, metadata, generated sources hoặc weaving options.

Nếu cache chỉ nhìn timestamp của source nghiệp vụ, sửa aspect có thể không invalidates lớp cần weave. Dẫn tới môi trường có phần artifact mang advice cũ, phần mang advice mới dù build vẫn báo thành công.

### 4.2 Những thay đổi cần cập nhật chữ ký số và nguồn gốc

Dệt một JAR đã ký làm thay đổi nội dung binary. Phát hành bản woven mới cần quản lý license/quyền sửa, integrity, metadata chữ ký, provenance và rollback; không giữ nhãn gây hiểu nhầm rằng JAR mới là bản gốc chưa đổi.

## 5. Load-time weaving: “lúc nạp” là ranh giới chính

Với **load-time weaving (LTW)**, bộ dệt can thiệp khi class loader định nghĩa lớp theo cấu hình phù hợp:

~~~text
Unwoven class bytes
        |
        v
Loader/agent with weaving configuration
        |
        v
Woven class definition installed in JVM
        |
        v
Object instances and method executions
~~~

Sửa pointcut hoặc cấu hình sau khi nhiều lớp đã được **defined/loaded** đặt ra câu hỏi: các lớp cũ có được dệt lại không? Trong load-time weaving thông thường, **không tự động**.

Ví dụ:

1. JVM khởi động, class `A` được nạp với cấu hình aspect phiên bản 1.
2. Sau đó cập nhật aspect phiên bản 2 để chọn thêm method trong `A`.
3. Nếu không có cơ chế redefine/retransform dành cho lớp đã nạp, **`A` vẫn mang định nghĩa đã cài tại thời điểm nạp**.
4. Một class `B` được nạp sau đó **có thể** được weave theo cấu hình mới nếu loader/agent thật sự sử dụng phiên bản mới, và nếu quy tắc nền tảng cho phép.
5. Kết quả có thể là **hai tập lớp dùng chính sách khác nhau**, điều nguy hiểm khi aspect kiểm soát quyền hoặc audit bắt buộc.

Trong một mô hình LTW có cấu hình aspect được chốt **trước khi loader nạp các kiểu cần dệt**, sửa cấu hình không thể chỉ “reload XML” rồi giả định aspect mới áp dụng cho mọi lớp cũ. Khi cần độ nhất quán trên toàn ứng dụng, restart hoặc redeploy dưới class loader mới thường dễ kiểm soát hơn.

### 5.1 Class loader quyết định phạm vi dệt

Các thành phần có thể được nạp qua loader khác nhau:

- Loader của ứng dụng.
- Loader dành cho plug-in hoặc mô-đun.
- Loader cha chia sẻ thư viện.
- Loader riêng của môi trường thử nghiệm.

Một weaver có thể chỉ can thiệp vào những class loader mà nó kiểm soát hoặc đã được đăng ký. Khi restart một module bằng loader mới, lớp thuộc loader cha có thể **vẫn là phiên bản cũ**. Phải xác định đúng **class nào được định nghĩa bởi loader nào**, và không chỉ dựa vào tên package.

### 5.2 Restart và reloading có phải cùng một điều?

Không. **Reload bằng class loader mới** có thể nạp một bản class mới trong cùng process, nhưng object instance cũ, static state và tham chiếu từ loader cũ vẫn có thể tồn tại. Nếu những tham chiếu đó không được dọn, dễ có memory leak hoặc hành vi pha trộn giữa nhiều phiên bản.

**Restart process** cho một JVM mới với cấu hình và artifact được kiểm soát, nhưng cũng kéo theo vấn đề availability, session, state và rollout; không đồng nghĩa dừng toàn hệ thống khi triển khai nhiều instance.

## 6. Đừng nhầm LTW với runtime instrumentation

Java có gói `java.lang.instrument` cung cấp API cho các **agent** biến đổi mã lớp. Trong một số điều kiện, agent có thể hỗ trợ:

- `Instrumentation.isRetransformClassesSupported()` và `retransformClasses(...)`: yêu cầu biến đổi lại những class đã nạp.
- `Instrumentation.isRedefineClassesSupported()` và `redefineClasses(...)`: thay định nghĩa class bằng class-file bytes mới.
- `Instrumentation.isModifiableClass(...)`: kiểm tra class cụ thể có thể bị thay hay không.

Nhưng **đây là các khả năng tùy chọn**, cần manifest/cấu hình agent thích hợp và được JVM thực tế hỗ trợ. Không thể mặc định một bộ LTW hoặc một agent AOP bất kỳ cung cấp cơ chế hot reweave.

Các giới hạn quan trọng của cơ chế JVM phổ biến:

- Redefine/retransform có các hạn chế về **thay đổi cấu trúc**, ví dụ không tự do thêm/bỏ field hoặc method, đổi method signature hay cấu trúc kế thừa trong mô hình JVM TI tương ứng.
- Không phải mọi class đều modifiable.
- Các **stack frame đang hoạt động** có thể tiếp tục chạy bytecode cũ; các lần invoke mới có thể dùng định nghĩa mới theo hợp đồng instrumentation.
- Cập nhật định nghĩa lớp **không tự chạy lại class initializer** và không tự reset giá trị static field hiện có.
- Bytecode mới phải hợp lệ với verifier/runtime và tương thích việc liên kết tới lớp khác.
- Trạng thái aspect/proxy đang sống có thể không đổi nếu agent chỉ sửa code của một lớp nhưng không thay object/state khác.

**Kết luận của phần này:** runtime redefinition có thể giảm nhu cầu restart trong một số trường hợp, nhưng không phải công tắc thần kỳ để thay mọi pointcut, sinh bất kỳ thành viên mới hoặc áp dụng đồng nhất lên mọi frame/class ngay lập tức.

## 7. Runtime proxy/wrapper: có thể đổi hành vi mà không đổi bytecode

Một kiến trúc **runtime wrapper/proxy** có thể đọc cấu hình động ở mỗi lần gọi. Khi đó có thể thay đổi hành vi advice đã cài đặt bằng cách cập nhật một **state holder** thread-safe.

Sơ đồ:

~~~text
Caller
   |
   v
Stable wrapper/proxy
   |         |
   |         +--> Current policy snapshot
   |                 trace on/off
   |                 validation on/off
   v
Target business method
~~~

Nếu wrapper được thiết kế đọc cấu hình theo **một snapshot trên mỗi lời gọi**, nó có thể bật/tắt tracing hoặc thêm validation đã viết sẵn **không cần rebuild class hoặc restart process**. Tuy nhiên:

- Wrapper chỉ bao phủ các lời gọi đi **qua nó**.
- Nếu pointcut ban đầu không chọn một method nào, **đổi cờ logic** không tự tạo wrapper tại method ấy.
- Nếu cần thêm kiểu join point không được mô hình proxy hỗ trợ, phải dùng kỹ thuật can thiệp thích hợp.
- Nếu không thiết kế để thay handler/interceptor chain động, việc sửa lớp implementation của proxy có thể vẫn cần rebuild/redeploy.
- Bật/tắt một policy được thiết kế sẵn khác với thay source của advice bằng một source mới và mong nó xuất hiện ngay ở JVM cũ.

### 7.1 Phân biệt ba dạng thay đổi

| Tình huống | Có thể đổi động trong wrapper thiết kế phù hợp? |
| --- | --- |
| Bật/tắt logging code **đã tồn tại** | Có thể: đổi cờ cấu hình |
| Thay ngưỡng cảnh báo đã được advice đọc động | Có thể: cập nhật cấu hình |
| Đổi `execution(pay)` thành `execution(refund)` ở class không hề được chặn | Không tự động chỉ bằng cờ; cần cập nhật phạm vi can thiệp |
| Thay bytecode của một phương thức nghiệp vụ đã nạp | Không chỉ bằng cờ; cần deploy/reload/instrumentation phù hợp |
| Thêm field/method vào class đã định nghĩa | Không chỉ bằng cờ hoặc hot redefine tùy ý |
| Đổi thứ tự interceptor chain | Có thể nếu chuỗi được thiết kế thay động và cập nhật nhất quán; không bảo đảm ở mọi proxy |

Khi đổi handler/chain lúc chạy, cần tránh lỗi **trộn cấu hình nửa cũ/nửa mới** trong một request. Một kỹ thuật là lưu một đối tượng cấu hình **bất biến** và thay tham chiếu nguyên tử, để từng invocation lấy một snapshot nhất quán.

## 8. Ví dụ Java 17 chạy độc lập: cập nhật chính sách khi tiến trình đang chạy

Chương trình sau minh họa **một lớp bọc thủ công mang ngữ nghĩa advice**, không phải cú pháp aspect của bộ AOP nào. Mục tiêu là thấy rõ: thay đổi **cờ xử lý trong advice đã được lắp sẵn** có thể có hiệu lực ở lần gọi sau **mà không rebuild hoặc restart**.

Ta dùng `AtomicReference<Policy>` và `record Policy` bất biến. Wrapper chụp một policy duy nhất khi bắt đầu mỗi lời gọi để xử lý đồng nhất trong suốt lần đó.

Lưu toàn bộ mã dưới tên `DynamicAdvicePolicyDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class DynamicAdvicePolicyDemo {
    interface Task {
        String execute(String id);
    }

    record Policy(boolean trace, boolean validate) {}

    static final class BusinessTask implements Task {
        @Override
        public String execute(String id) {
            System.out.println("BUSINESS " + id);
            return "done:" + id;
        }
    }

    static final class AdviceWrapper implements Task {
        private final Task target;
        private final AtomicReference<Policy> policy;

        AdviceWrapper(Task target, AtomicReference<Policy> policy) {
            this.target = target;
            this.policy = policy;
        }

        @Override
        public String execute(String id) {
            Policy current = policy.get(); // Một snapshot cho lần gọi.
            if (current.trace()) {
                System.out.println("ADVICE BEFORE");
            }

            try {
                if (current.validate()
                        && (id == null || id.isBlank())) {
                    throw new IllegalArgumentException("blank id");
                }

                String result = target.execute(id);

                if (current.trace()) {
                    System.out.println("ADVICE AFTER " + result);
                }
                return result;
            } catch (RuntimeException error) {
                if (current.trace()) {
                    System.out.println("ADVICE ERROR "
                            + error.getClass().getSimpleName());
                }
                throw error;
            }
        }
    }

    public static void main(String[] args) {
        AtomicReference<Policy> setting =
                new AtomicReference<>(new Policy(false, false));

        Task task = new AdviceWrapper(new BusinessTask(), setting);

        System.out.println("CASE original");
        System.out.println("RESULT " + task.execute("A"));

        // Thay cấu hình; không tạo lớp/proxy mới và không restart.
        setting.set(new Policy(true, true));
        System.out.println("CASE live-update");
        System.out.println("RESULT " + task.execute("B"));

        System.out.println("CASE invalid");
        try {
            task.execute("");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        setting.set(new Policy(false, true));
        System.out.println("CASE trace-off");
        System.out.println("RESULT " + task.execute("C"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac DynamicAdvicePolicyDemo.java
java DynamicAdvicePolicyDemo
~~~

Stdout:

~~~text
CASE original
BUSINESS A
RESULT done:A
CASE live-update
ADVICE BEFORE
BUSINESS B
ADVICE AFTER done:B
RESULT done:B
CASE invalid
ADVICE BEFORE
ADVICE ERROR IllegalArgumentException
CALLER blank id
CASE trace-off
BUSINESS C
RESULT done:C
~~~

### 8.1 Kết quả minh họa điều gì?

**Lần A:** wrapper tồn tại nhưng `trace=false`, `validate=false`. Nó gọi nghiệp vụ và trả `done:A` mà không in advice.

**Cập nhật cấu hình:** `setting.set(new Policy(true, true))` thay object Policy bằng thao tác nguyên tử. Không có bước compile/weave/reload class; chỉ thay state được wrapper đọc ở lần gọi sau.

**Lần B:** wrapper đọc snapshot mới, in BEFORE, gọi nghiệp vụ và in AFTER với kết quả.

**Lần ID rỗng:** cấu hình `validate=true` làm wrapper ném `IllegalArgumentException` **trước khi gọi** BusinessTask; vẫn in nhánh ADVICE ERROR vì trace đang bật. Không có dòng `BUSINESS` cho request này.

**Lần C:** trace được tắt lại nhưng validation vẫn bật; nghiệp vụ nhận ID hợp lệ, kết quả trả bình thường không có dòng tracing.

### 8.2 Những điều ví dụ KHÔNG chứng minh

- Không có một bộ weaver tự chèn advice hoặc một ngôn ngữ pointcut thực sự. Đây là **wrapper Java thủ công** mô phỏng hành vi AOP ở một điểm đã được bọc.
- Không thêm join point mới; `Task.execute` đã có wrapper từ đầu.
- Không thay bytecode của `BusinessTask`, không redefine class, không cài agent và không động đến class loader.
- Nếu gọi trực tiếp `new BusinessTask().execute("X")`, wrapper không nhìn thấy; do đó không thể lấy ví dụ này làm bằng chứng về phạm vi phủ của một chính sách an ninh bắt buộc.
- `AtomicReference` giúp thay tham chiếu policy an toàn, nhưng **không tự đồng bộ rollout trên nhiều JVM** hoặc đảm bảo yêu cầu đang chạy đổi policy giữa chừng; mỗi invocation trong ví dụ chụp một snapshot.
- Mã cố ý không tích hợp nguồn xác thực. Nếu validation ở production liên quan bảo mật, mọi đường vào phải được kiểm soát ở ranh giới đáng tin, không phụ thuộc duy nhất vào một cờ có thể bị tắt sai.

## 9. Ví dụ luồng xây dựng lại ở compile-time/post-compile

Đối với hệ thống compile-time hoặc binary weaving, khi sửa pointcut nên áp dụng pipeline:

~~~text
1. Edit aspect source / pointcut / precedence
2. Compile aspect (when required)
3. Reweave all impacted sources/classes/JARs
4. Test woven artifact and compare join point coverage
5. Publish artifact version
6. Deploy new version (restart/reload as supported)
7. Verify runtime loaded the intended version
~~~

Sơ đồ ở trên là **quy trình khái niệm**, không phải cú pháp lệnh chung cho mọi weaver.

### 9.1 Ví dụ logic trước/sau thay pointcut

Trước thay đổi:

~~~text
P_v1 = execution(payment.process(..))
Advice applies to:
    payment.process
~~~

Sau thay đổi:

~~~text
P_v2 = execution(payment.process(..))
       OR execution(refund.process(..))
Advice should apply to:
    payment.process
    refund.process
~~~

Đây là **giả mã mô tả tập điểm**, không phải cú pháp AOP dùng chung. Với weaver tạo mã lúc build, phần `refund.process` phải thực sự xuất hiện trong bản woven mới. Nếu runtime vẫn dùng class chưa dệt hoặc chỉ có `P_v1`, việc sửa source của aspect không thể làm advice tự xuất hiện ở `refund`.

### 9.2 Khi nào chỉ cần sửa cấu hình?

Nếu một aspect đã có điều kiện động:

~~~text
selected join point = all operations needed
within advice:
    if currentConfig.traceEnabled:
        emit event
    proceed
~~~

thay `traceEnabled` có thể chỉ là thao tác cập nhật cấu hình, **nếu advice đã được weave/chặn ở đúng phạm vi**, cấu hình được đọc động và bộ phận quản lý cấu hình bảo đảm tính nhất quán. Việc đặt pointcut quá rộng để cho phép đổi tùy ý về sau lại có **chi phí và rủi ro**: mọi join point trong phạm vi vẫn có thể chịu overhead của phần kiểm tra động.

## 10. Sửa aspect ảnh hưởng tới thứ tự advice và trạng thái

### 10.1 Precedence có thể thay đổi ranh giới an ninh

Giả sử:

~~~text
Authorize(Cache(Business))
~~~

Authorization bao ngoài Cache: khi cache hit, quyền vẫn được kiểm tra trước. Nếu thay cấu hình/precedence thành:

~~~text
Cache(Authorize(Business))
~~~

một cache hit ở ngoài có thể **không gọi tiếp** và bỏ qua kiểm tra bên trong. Vì vậy thay precedence **không chỉ là sửa thứ tự log**, và phải được triển khai/test như một thay đổi ngữ nghĩa có ảnh hưởng tới bảo mật.

### 10.2 Thay trạng thái aspect có thể khác thay mã advice

Một aspect có thể chứa bộ đếm, cache, dữ liệu tạm, cấu hình theo instance hoặc theo thread. Khi triển khai mã aspect mới, phải xác định:

- Trạng thái cũ có còn tồn tại trong object cũ không?
- Có tạo aspect instance mới, hay giữ instance cũ và chỉ đổi code?
- Có cần migrate hoặc reset counters/caches/registrations?
- Thread-local values có được cleanup đúng không?
- Có nhiều class loader/phiên bản aspect cùng hiện diện không?
- Các request đang chạy sẽ dùng rule cũ hay mới?

Nếu chỉ đổi một cờ trong state holder, mã class không đổi. Nếu thêm field vào class đã nạp, hot redefine có thể không hỗ trợ. Nếu chuyển cả loader, object cũ còn tham chiếu có thể vẫn sử dụng aspect cũ, gây hành vi pha trộn.

### 10.3 Những điểm mới sinh ở runtime

Nếu một plugin hoặc generator nạp class mới sau lúc cấu hình weaving thay đổi, tùy load-time weaver, class ấy **có thể** được dệt theo phiên bản mới. Nhưng điều đó **không** có nghĩa class trước đó đã được cập nhật. Nguy cơ mixed-version là đáng kể khi cùng một chính sách audit hay authorization phải áp dụng nhất quán.

## 11. Triển khai thực tế: có cần downtime không?

Một hệ thống nhiều instance có thể thực hiện **rolling deployment**:

~~~text
Instance A: old woven version
Instance B: old woven version
Instance C: old woven version

Deploy new version to A and verify
Deploy new version to B and verify
Deploy new version to C and verify
~~~

Trong giai đoạn chuyển đổi có thể đồng thời tồn tại **hai phiên bản aspect**. Nếu aspect ảnh hưởng bảo mật, serialization, transaction hoặc giao thức liên hệ giữa instance, phải xác định có chấp nhận giai đoạn này không.

Các chiến lược thường cần cân nhắc:

- **Rolling update:** thay dần các instance; bảo đảm policy giữa phiên bản cũ/mới có thể cùng tồn tại an toàn.
- **Blue–green:** chuẩn bị nhóm instance mới, test rồi chuyển lưu lượng; cần kiểm tra trạng thái/dữ liệu chia sẻ.
- **Canary:** áp dụng cho tỷ lệ lưu lượng nhỏ và đo hành vi trước mở rộng.
- **Restart có kế hoạch:** khi trạng thái hoặc class loader khiến hot swap không an toàn.
- **Dynamic toggle:** dành cho hành vi đã được thiết kế bật/tắt an toàn, không dùng để thay thế mọi bước kiểm thử.

“Không phải restart toàn cụm” khác với “không instance nào phải restart”. Việc cần dừng một JVM để dùng class woven mới có thể vẫn được che giấu khỏi người dùng bằng kiến trúc triển khai nhiều bản sao và chuyển lưu lượng thích hợp.

## 12. Kiểm thử trước khi quyết định không restart

| Thay đổi | Kiểm tra bắt buộc |
| --- | --- |
| Advice log đổi cách ghi | Mã mới thật sự được gọi? Có lộ dữ liệu nhạy cảm? Có lỗi khi log? |
| Pointcut được mở rộng | Join point mới xuất hiện trong artifact/trace đúng như ý định? |
| Pointcut thu hẹp | Các lớp cũ có còn chứa advice trước đây không? |
| Precedence đổi | Authorization, transaction, audit, cache và retry còn đúng thứ tự không? |
| LTW config đổi | Những class đã nạp có được cập nhật hay chỉ những class nạp sau? |
| Proxy handler đổi động | Mọi proxy thực sự nhìn state/chain mới? Lời gọi đang chạy có snapshot ổn định? |
| Agent retransform | JVM/agent cho phép? Class modifiable? Thay đổi có nằm trong giới hạn? |
| Code thêm field/method | Có thuộc thay đổi cấu trúc không được hot redefine hỗ trợ? |
| Build cache/incremental | Clean build và incremental tạo tập join point/behavior tương đương? |
| Library dependency đổi | Classpath/module path và binary compatibility còn đúng? |
| Rolling deployment | Hai phiên bản policy có thể cùng tồn tại an toàn? |
| Rollback | Có artifact/config cũ và cơ chế trở lại trạng thái ổn định? |

### 12.1 Ba lớp xác minh

**Xác minh artifact:** hash/version, bytecode được dệt, danh sách join point, đúng JAR trên classpath, không instrument trùng.

**Xác minh runtime:** advice thực sự chạy trên những đường gọi cần thiết, thứ tự before/after, kết quả và ngoại lệ được bảo toàn, lỗi và cleanup đúng.

**Xác minh vận hành:** rollout và rollback, nhiều instance, thời điểm áp dụng cấu hình, metrics/audit, hiệu năng, dữ liệu nhạy cảm và policy consistency.

Chỉ thấy file build mới hoặc log “configuration reloaded” không đủ chứng minh toàn bộ hệ thống đã chuyển sang aspect phiên bản mới.

## 13. Những ngộ nhận cần tránh

1. **“Sửa source aspect là JVM tự nhận.”** Sai khi class/advice đã compile/weave và nạp mà không có cơ chế cập nhật.
2. **“Post-compile weaving phải biên dịch lại mọi source nghiệp vụ.”** Không nhất thiết; có thể dệt lại từ binary chưa dệt, nhưng phải cập nhật mọi artifact bị ảnh hưởng.
3. **“Đổi pointcut giống đổi ngưỡng log.”** Không: pointcut có thể đổi tập join point cần can thiệp.
4. **“Load-time weaving luôn áp dụng ngay cả class đã nạp.”** Không; thường phải reload/restart hoặc dùng instrumentation hỗ trợ riêng.
5. **“Thay JAR trên đĩa làm JVM đang chạy dùng code mới.”** Không tự động thay định nghĩa class đã nạp.
6. **“Mọi JVM đều hỗ trợ retransform/redefine mọi class.”** Sai; năng lực tùy JVM/agent và từng class.
7. **“Đổi mọi cấu trúc class đều có thể hot swap.”** Không; có giới hạn field/method/inheritance trong các cơ chế chuẩn tương ứng.
8. **“Tất cả stack frame lập tức chạy code mới.”** Sai với các phương thức đang active theo ngữ nghĩa instrumentation.
9. **“Bật/tắt tracing không cần restart nên thêm execution join point cũng không cần.”** Không suy được; thay cờ không làm xuất hiện hook mới.
10. **“Đổi cấu hình LTW rồi class cũ và mới chắc chắn đồng bộ.”** Không; thời điểm nạp và loader có thể gây mixed-version.
11. **“Một proxy được tạo một lần luôn đọc chain mới.”** Chỉ đúng khi được thiết kế thay chain/config động.
12. **“Reweaving luôn idempotent.”** Không có bảo đảm chung, phải theo hợp đồng công cụ.
13. **“Thứ tự tệp aspect quyết định advice precedence.”** Không thể dựa vào thứ tự file nếu mô hình không định nghĩa.
14. **“Restart toàn cụm là cách duy nhất.”** Không; có triển khai từng instance, nhưng tính nhất quán policy phải kiểm tra.
15. **“Có thể bỏ kiểm thử vì chỉ đổi log.”** Sai: advice có thể gây lỗi, tăng overhead hoặc rò dữ liệu.

## 14. Checklist ra quyết định

Khi nhận yêu cầu thay một aspect đang dùng trong production, hãy đi theo thứ tự:

1. **Định danh thay đổi:** sửa source advice, pointcut, precedence, inter-type, state hay chỉ config?
2. **Xác nhận mô hình dệt:** compile-time, post-compile, LTW, runtime proxy, hay hỗn hợp?
3. **Phân tích phạm vi:** những join point/class nào đã hoặc sẽ chịu ảnh hưởng?
4. **Xác minh thời điểm nạp:** class mục tiêu đã được định nghĩa trong JVM chưa? Qua class loader nào?
5. **Chọn cơ chế cập nhật:** rebuild/reweave, new class loader, process restart, dynamic chain/config, hay runtime instrumentation được hỗ trợ?
6. **Kiểm tra tính năng:** nếu hot redefine/retransform, JVM và agent có thực sự hỗ trợ class ấy và kiểu thay đổi này không?
7. **Bảo toàn trạng thái:** aspect instances, caches, counters, thread context, transactions và active frames sẽ ra sao?
8. **Đóng gói:** artifact/version/manifest/dependencies/provenance đúng chưa? Có bản unwoven để tái tạo?
9. **Kiểm thử:** success/error, call/execution, proxy bypass, security, audit, retry, short-circuit, overhead.
10. **Rollout và rollback:** thay từng instance hay toàn bộ, có giai đoạn mixed-version không?
11. **Quan sát:** kiểm chứng bằng trace và kết quả thực tế rằng **phiên bản mới đang có hiệu lực**.
12. **Tài liệu hóa:** ghi rõ điều kiện nào không restart, điều kiện nào bắt buộc restart hoặc reload.

## 15. Bài tập tự kiểm tra

**Bài 1.** Aspect đang được compile-time weave chọn `execution(pay)`. Đổi pointcut để chọn thêm `execution(refund)`, rồi chỉ thay tệp cấu hình mà không xây lại lớp `refund`. Có chắc advice sẽ xuất hiện tại `refund`?

**Đáp:** không. Tập join point đã dệt thường được quyết định khi build; cần weave lại các class chịu ảnh hưởng và chạy artifact mới.

**Bài 2.** Một JAR được binary weave hôm qua. Hôm nay thay source aspect, nhưng JVM vẫn chạy class cũ. Chỉ thay JAR woven trên đĩa có đủ?

**Đáp:** không. Phải bảo đảm runtime **nạp định nghĩa mới** qua restart/reload hoặc khả năng redefine/retransform phù hợp.

**Bài 3.** LTW agent bắt đầu với pointcut phiên bản 1 và đã nạp class A. Sau đó cấu hình được sửa để chọn thêm method của A. Class A tự cập nhật không?

**Đáp:** không thể giả định. Load-time weaving bình thường dệt lúc nạp class; muốn cập nhật class đã định nghĩa cần cơ chế hỗ trợ riêng hoặc nạp lại trong môi trường mới.

**Bài 4.** Advice đã được cài sẵn quanh `execute` và đọc `AtomicReference<Policy>`. Thay Policy có bắt buộc rebuild/restart không?

**Đáp:** trong mô hình ví dụ Java, không. Wrapper đã tồn tại và đọc snapshot mới mỗi invocation. Nhưng điều đó **không thêm join point mới** và không đảm bảo cập nhật đồng thời mọi JVM.

**Bài 5.** Cần thêm field vào class nghiệp vụ đã nạp vì aspect mới khai báo trạng thái. Có thể mặc định Java Instrumentation redefine class không restart được không?

**Đáp:** không. Thêm field là thay đổi cấu trúc bị hạn chế trong khả năng redefine/retransform tiêu chuẩn; phải xác minh phương án khác, thường cần build/redeploy và class definition mới.

**Bài 6.** Agent có hỗ trợ retransformation, nhưng lời gọi hiện tại đang chạy bytecode cũ. Việc retransformation thành công có tự thay những active frames đó không?

**Đáp:** không theo hợp đồng Java Instrumentation thông thường: active frames có thể tiếp tục chạy định nghĩa cũ, còn các lời gọi mới dùng định nghĩa cập nhật.

**Bài 7.** Tại sao một thay đổi security aspect cần cân nhắc giai đoạn rolling deployment?

**Đáp:** vì các instance cũ và mới có thể cùng phục vụ request với các quy tắc kiểm tra quyền khác nhau. Phải thiết kế policy versioning và chiến lược rollout tương thích, tránh khoảng trống bảo mật.

## 16. Tham khảo

- [AspectJ Developer Guide – Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): mô tả ba thời điểm compile-time, post-compile và load-time weaving trong một hệ thống AOP trên JVM, cùng điều kiện class-loader và giới hạn lớp đã nạp.
- [Java SE 17 – Instrumentation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isRetransformClassesSupported`, `retransformClasses`, `redefineClasses` và ảnh hưởng lên các stack frames/class đã định nghĩa.
- [Java SE 17 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng transformer, thời điểm áp dụng và thứ tự biến đổi.
- [Java SE 17 – AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): ví dụ một nơi lưu cấu hình có thể cập nhật an toàn ở runtime.
- [JVM Specification, Java 17 – Class Loading and Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): khái niệm nạp, liên kết và định nghĩa class.

**Ghi nhớ:** việc cần **rebuild**, **reweave**, **redeploy** hay **restart** phụ thuộc vào **lúc aspect được kết hợp với chương trình** và **cấu trúc nào thay đổi**. Compile-time và post-compile weaving thường yêu cầu tạo artifact mới; LTW bình thường chỉ áp dụng khi lớp được nạp; dynamic wrapper có thể cho thay đổi hành vi đã được cài sẵn; runtime instrumentation là một khả năng riêng có giới hạn. Luôn xác minh **tập join point hiệu lực, artifact đã nạp, trạng thái đang chạy và kết quả nghiệp vụ**, thay vì dựa vào một khẳng định chung rằng “đã reload aspect”.
