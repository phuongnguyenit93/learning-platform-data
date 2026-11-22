# Ảnh hưởng đến đóng gói, triển khai và tính lặp lại của bản dựng

## 1. Vì sao thời điểm weaving ảnh hưởng cả quá trình phát hành?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, **aspect** đóng gói mối quan tâm cắt ngang; **pointcut** lựa chọn các *join point* có thể can thiệp; **advice** định nghĩa hành vi chạy tại chúng. **Weaving (dệt)** là cách kết hợp aspect với chương trình mục tiêu để advice được thực thi ở các join point phù hợp.

Thời điểm weaving không chỉ quyết định “gắn advice lúc nào”, mà còn tác động trực tiếp đến:

- **Artifact phát hành:** class/JAR đã được dệt hay JAR gốc đi kèm runtime weaver, agent hoặc proxy?
- **Dependency và đóng gói:** công cụ weaving, thư viện runtime, cấu hình pointcut, phiên bản JDK và classloader nào bắt buộc hiện diện?
- **Thời điểm kiểm tra:** lỗi pointcut/bytecode được phát hiện lúc build, nạp class hay khi một lời gọi thật đi qua interceptor?
- **Cách triển khai và rollback:** có cần rebuild artifact, đổi agent/flags hoặc tái tạo chuỗi proxy không?
- **Tính tái lập:** cần cố định những inputs nào để hai lần build cho cùng bytes và hai môi trường chạy cho cùng hành vi advice?

Một phân biệt then chốt:

> **Reproducible build**: cùng những đầu vào được kiểm soát tạo artifact cuối giống nhau theo tiêu chí đã công bố. **Reproducible deployment**: cùng artifact cùng môi trường/cấu hình can thiệp tạo phạm vi và hành vi advice tương đương.

Hai mục tiêu liên quan, nhưng **một JAR có cùng SHA-256 không tự bảo đảm advice chạy giống nhau** khi agent, proxy wiring hoặc runtime config khác.

Bài học chỉ trình bày **AOP/Aspect tổng quát và nâng cao**, tập trung vào các thời điểm weaving và hậu quả kiến trúc. Mọi ví dụ Java chạy độc lập bằng JDK 17+, không cần một hệ AOP chuyên biệt.

## 2. Bốn mô hình cần phân biệt

| Mô hình | Khi nào kết hợp/can thiệp | Thứ được triển khai |
| --- | --- | --- |
| **Compile-time weaving (CTW)** | Trong bước biên dịch/build | Artifact thường đã chứa mã được dệt |
| **Post-compile/binary weaving** | Sau compile, trước runtime | Artifact raw và artifact woven là hai trạng thái phải quản lý |
| **Load-time weaving (LTW)** | Khi JVM nạp hoặc định nghĩa class | Có thể là raw bytecode cùng runtime weaver/agent/config |
| **Runtime proxy/interceptor** | Khi lời gọi thực đi qua wrapper | Target bytecode có thể nguyên trạng, hành vi nằm ở chuỗi proxy |

Các công nghệ JVM còn có thể cung cấp **retransformation/redefinition** đối với class đã được định nghĩa, tùy khả năng agent/JVM. Đây là một cơ chế khác LTW thông thường và khác proxy.

Sơ đồ tổng quan:

~~~text
CTW:
source + aspects -> compile/weave -> woven classes -> package -> JVM

Binary:
source -> javac -> raw classes -> weaver -> woven classes -> package -> JVM

LTW:
source -> javac -> raw JAR -----------+
weaver agent + policy ---------------+-> JVM class loading -> transformed class

Runtime proxy:
source -> javac -> app.jar -> create proxy -> intercept -> target
~~~

Hai điều dễ nhầm:

1. **Dệt tĩnh không có nghĩa advice chạy lúc build.** Việc kết hợp diễn ra sớm; advice vẫn chạy khi join point xuất hiện trong chương trình đang thực thi.
2. **LTW không đồng nghĩa proxy.** LTW thường biến đổi class bytecode trong quá trình nạp, còn proxy định tuyến lời gọi qua một đối tượng trung gian và không nhất thiết sửa bytecode target.

## 3. Compile-time weaving: mọi thứ quan trọng diễn ra trong build

Với CTW, compiler/weaver kết hợp mã nghiệp vụ và aspect rồi tạo ra class hoặc artifact mang hành vi AOP. Khi phát hành, bản build đã chứa logic can thiệp ở những nơi công cụ thực sự hỗ trợ và đã dệt.

~~~text
pinned source + pinned dependencies + aspect definitions
                         |
                compiler/weaver
                         |
                    woven classes
                         |
                  package / test
                         |
                    release.jar
~~~

**Ảnh hưởng đến đóng gói:**

- Artifact cuối là sản phẩm của **compiler cộng weaver**, không chỉ riêng `javac`.
- Runtime có thể vẫn cần thư viện hỗ trợ advice do công cụ sử dụng, dù quá trình dệt đã xong.
- Ký hoặc hash JAR cần thực hiện **sau** mọi bước biến đổi bytecode và packaging cuối.
- Có thể test ngay trên class/JAR đã dệt, tạo chứng cứ cụ thể cho bản phát hành.

**Ảnh hưởng đến triển khai:**

- Thay đổi định nghĩa aspect hoặc pointcut thường dẫn đến **rebuild/redeploy** các artifact liên quan.
- Nếu build đã dệt sai, đổi cấu hình runtime thường không thể tự sửa phần bytecode đã kết hợp, trừ khi công nghệ còn cung cấp cơ chế khác.
- Stack trace và debugging có thể phản ánh mã đã biến đổi; cần source mappings và symbol phù hợp.
- Đã dệt một số join point **không bảo đảm** các loại join point khác được can thiệp.

**Ảnh hưởng đến reproducibility:**

- Weaver version, transformation order, input classpath, generated metadata và output packaging đều là đầu vào cần kiểm soát.
- Cùng source nhưng khác weaver hoặc cờ weaving có thể tạo class khác.
- Một công cụ không tất định có thể tạo bytecode khác ngay khi source không đổi.
- Unit test chỉ chạy raw code chưa đủ: **integration test trên woven artifact cuối** mới chứng minh advice được kích hoạt.

Không nói CTW “luôn chạy nhanh hơn” những mô hình khác: advice vẫn gây runtime overhead; JIT, logging, I/O, số join point và cách tổ chức đều ảnh hưởng hiệu năng.

## 4. Binary weaving: bảo vệ ranh giới raw và woven

Trong **post-compile weaving**, class đã biên dịch được đưa qua một bước biến đổi khác:

~~~text
source -> javac -> build/raw-classes/
                         |
                       weave
                         |
                         v
                 build/woven-classes/
                         |
                       package
                         |
                         v
                    release.jar
~~~

Giữ riêng hai loại output mang lại lợi ích lớn:

- Biết chính xác **đầu vào dệt** và **kết quả dệt**, thuận lợi khi so bytecode.
- Không vô tình dùng class đã woven làm raw input ở lần build sau.
- Có thể chạy test với raw classes và woven classes để cô lập bug do instrumentation.
- Dễ truy nguyên class nào được dệt, công cụ nào dệt và version nào.
- Giảm nguy cơ **dệt lặp** nếu một pipeline package tiếp tục instrument bytecode đã biến đổi.

Một pipeline rủi ro:

~~~text
compile -> output/
weave output/ -> output/
package output/
lần build sau dùng lại output/ như raw input -> weave lại
~~~

Lần weave thứ hai có thể bị từ chối, bỏ qua hoặc chèn trùng, **phụ thuộc công cụ**. Không mặc định “dệt lần hai luôn gây advice chạy gấp đôi” hay “weaver luôn idempotent”.

### Vị trí signing và shading

Nếu JAR có chữ ký integrity, sửa class entries **sau khi ký** có thể làm chữ ký không hợp lệ. Cần hoàn tất weaving, shading, relocation và archive packaging trước khi ký artifact phát hành cuối.

Các công cụ đổi tên package/class hoặc gom thư viện thành uber-JAR có thể thay signature mà pointcut phụ thuộc. Thứ tự “weave rồi relocate” hay “relocate rồi weave” phải do pipeline quyết định và được test trên artifact thực, không có một thứ tự chung phù hợp mọi công cụ.

## 5. Load-time weaving: chính deployment trở thành một phần weaving

**Load-time weaving (LTW)** thường biến đổi class bytecode trước hoặc trong khi JVM định nghĩa class. Ứng dụng có thể phát hành bytecode gốc nhưng runtime cần đủ thành phần để weaving xảy ra.

| Đầu vào runtime | Câu hỏi kiểm soát |
| --- | --- |
| Weaver/agent binary | Có đúng version và checksum đã duyệt? |
| Aspect/pointcut config | Có cùng policy và phạm vi class? |
| JVM version và options | Có hỗ trợ bytecode và khả năng instrumentation cần thiết? |
| Classloader | Class mục tiêu do loader nào định nghĩa? |
| Load order | Transformer có được đăng ký **trước** lúc class mục tiêu load? |
| Module system | Có hạn chế quyền truy cập/biến đổi class? |
| Các agent khác | Có policy chồng lấn hay transformer chain khác? |
| Startup lifecycle | Class nào load sớm, class nào load lazy? |
| Error policy | Khi weaving thất bại, ứng dụng fail-open hay fail-closed? |

**Cùng app.jar SHA-256 nhưng agent version khác** có thể tạo behavior khác. Vì vậy, bộ manifest triển khai cần ghi không chỉ app artifact hash mà còn **weaver/agent/config và những JVM flags liên quan**.

Nếu agent được bật sau khi class mục tiêu đã định nghĩa, LTW thông thường có thể bỏ lỡ class ấy. Một số cơ chế instrumentation hỗ trợ retransformation/redefinition của class đã load, nhưng có quyền và hạn chế riêng; **không coi chúng là LTW tự động**.

Một vấn đề khác là **classloader identity**. Class cùng tên từ hai loaders có thể là hai runtime classes độc lập. Nếu một máy load qua loader A còn máy khác qua loader B, weaving scope và kiểm tra điểm can thiệp có thể khác nhau dù artifact file có cùng nội dung.

## 6. Runtime proxy/interceptor: JAR không đổi vẫn có thể đổi advice

Một hệ thống có thể tạo proxy ở runtime và chuyển lời gọi qua handler:

~~~text
Caller -> Proxy / Interceptor -> Target method
             |
        match policy?
        before / after / around behavior
~~~

**Điều kiện tiên quyết:** caller phải giữ **tham chiếu proxy** ở ranh giới muốn can thiệp. Caller gọi thẳng target sẽ bỏ qua proxy đó; lời gọi nội bộ qua `this.otherMethod()` có thể cũng không đi qua wrapper.

Những yếu tố làm behavior khác dù JAR không đổi:

- Runtime flag cho phép hoặc vô hiệu advice.
- Đường tạo proxy khác nhau giữa hai môi trường.
- Cấu hình interceptor chain và thứ tự ưu tiên khác.
- Caller vô tình giữ target thay vì proxy.
- Hai proxy cùng chức năng bọc nhau, làm advice chạy lặp.
- Pointcut runtime có điều kiện theo metadata hoặc trạng thái.
- Phiên bản thư viện tạo proxy hoặc policy config được nạp từ bên ngoài khác nhau.

Không phải mọi proxy được bật/tắt động tùy ý: nếu handler đọc config một lần lúc startup, đổi config ở runtime có thể chưa có tác dụng.

**Proxy và weaving không cùng độ phủ.** Một engine bytecode có thể can thiệp method execution bên trong target khi class được dệt, còn proxy thông thường chỉ thấy lời gọi đi qua wrapper. Việc có `private`, `final`, `static`, constructor, field access hoặc exception-handler join point phụ thuộc mô hình công cụ cụ thể. Không kết luận rằng “mọi AOP đều nhìn được mọi method”.

## 7. Reproducible build và reproducible deployment khác nhau ra sao?

### 7.1. Tái lập inputs

Hai bản build dùng cùng source commit, dependencies và công cụ. Đây chỉ là **điều kiện đầu vào**; output vẫn có thể khác vì timestamp, file ordering, nondeterministic bytecode generation hoặc build metadata.

### 7.2. Tái lập từng byte

Hai artifact độc lập có cùng chuỗi byte; do đó SHA-256 giống hệt. Muốn đạt được phải kiểm soát:

1. Tên và phiên bản compiler/JDK.
2. Cờ biên dịch như `--release` và debug info.
3. Encoding, line endings, generated source, generated resources.
4. Dependency versions/checksums và classpath/module path.
5. Weaver version, cấu hình, thứ tự transformation.
6. Các file class/asset được đưa vào archive.
7. Thứ tự ZIP/JAR entries và timestamps.
8. Manifest, module metadata, version string, host path và build time.
9. Công cụ shading/relocation, compression và signing.
10. Build cache và độ sạch của thư mục output.

**Hash bằng nhau** chứng minh bytes của hai artifact được so là giống nhau, không chứng minh runtime config giống nhau. **Hash khác nhau** không tự khẳng định behavior khác; khác timestamp cũng có thể đổi hash.

### 7.3. Tái lập behavior khi triển khai

Giả sử app JAR hash H xuất hiện trên cả hai máy:

~~~text
Environment A:
  app.jar hash = H
  auditProxy.enabled = false

Environment B:
  app.jar hash = H
  auditProxy.enabled = true

Build bytes: giống
Audit behavior: khác
~~~

Tương tự, LTW với agent version khác hoặc class loading order khác có thể thay đổi tập join point thực sự được instrument. Vì vậy, deployment release nên gắn một **bộ thông tin gồm app hash + runtime toolchain + AOP policy/configuration**, thay vì chỉ app hash.

## 8. Kiểm soát determinism của bản dựng

| Nhóm input | Cần cố định/kiểm tra |
| --- | --- |
| Source | Commit, source generator, encoding và line ending |
| Dependency | Phiên bản/checksum cụ thể, không dùng phiên bản trôi nổi |
| JDK/compiler | Phiên bản exact, target bytecode, compilation flags |
| Weaver | Binary, policy, transformation order, module filters |
| Raw/woven boundary | Không trộn output giữa các bước |
| Archive | Stable entry order, timestamp, manifest, resource processing |
| Generated metadata | Tránh current time, machine name, username, random UUID |
| Code signing | Ký artifact cuối, ghi nhận signing process và timestamping |
| Build runner | Locale, OS/tool behavior khi có ảnh hưởng |
| Tests | So artifact cuối và chạy integration tests thật |

Có thể hướng tới **hermetic build**: mọi input ảnh hưởng output đều khai báo, không tự lấy latest dependency hoặc đọc file ngẫu nhiên ở máy builder.

### Determinism khác idempotence

- **Deterministic weaving:** cùng input và điều kiện có kết quả tương đương theo tiêu chí xác định.
- **Idempotent weaving:** áp dụng lại không tạo thêm side effect/instrumentation ngoài hợp đồng.
- **Byte-for-byte reproducible:** bytes của artifact cuối giống nhau.
- **Behavior reproducible:** cùng điều kiện triển khai tạo behavior advice tương đương.

Một weaver deterministic chưa chắc idempotent khi feed output đã dệt làm input; một weaver idempotent về behavior chưa chắc tạo ZIP bytes giống nhau nếu metadata archive khác.

## 9. Ví dụ Java 17: cùng JAR nhưng hai chế độ AOP qua proxy

Ví dụ độc lập dùng JDK dynamic proxy để minh họa **ảnh hưởng của runtime config tới behavior**, không giả làm ví dụ bytecode weaving.

- `LedgerCore` là mã nghiệp vụ.
- `auditProxy(...)` chạy audit trước/sau, giữ nguyên kết quả và ngoại lệ gốc.
- `--audit` bật proxy cho caller.
- Cùng source biên dịch hai lần, đóng JAR với timestamps được cố định, rồi so SHA-256.
- Dùng cùng artifact chạy một lần ở chế độ thường, một lần ở chế độ audit.

Tạo file `PackagingAopDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class PackagingAopDemo {
    interface Ledger {
        String book(int units);
    }

    static final class LedgerCore implements Ledger {
        @Override
        public String book(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException("units must be positive");
            }
            System.out.println("BUSINESS book");
            return "OK:" + units;
        }
    }

    static Ledger auditProxy(Ledger target) {
        return (Ledger) Proxy.newProxyInstance(
                Ledger.class.getClassLoader(),
                new Class<?>[]{Ledger.class},
                (proxy, method, args) -> {
                    System.out.println("AUDIT before " + method.getName());
                    try {
                        Object result = method.invoke(target, args);
                        System.out.println("AUDIT after " + method.getName());
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        System.out.println("AUDIT throwing "
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                });
    }

    public static void main(String[] args) {
        boolean audit = args.length > 0 && "--audit".equals(args[0]);
        Ledger service = new LedgerCore();
        if (audit) {
            service = auditProxy(service);
        }
        System.out.println("MODE " + (audit ? "AUDIT" : "PLAIN"));
        System.out.println("RESULT " + service.book(2));
        try {
            service.book(0);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }
}
~~~

### 9.1. Lệnh biên dịch và đóng JAR

Trong **Windows PowerShell**, từ thư mục chứa `PackagingAopDemo.java`, chạy các lệnh sau với JDK 17+:

~~~powershell
New-Item -ItemType Directory -Force out-a,out-b | Out-Null

javac --release 17 -encoding UTF-8 -g:none -d out-a PackagingAopDemo.java
if ($LASTEXITCODE -ne 0) { throw "Compile A failed" }

javac --release 17 -encoding UTF-8 -g:none -d out-b PackagingAopDemo.java
if ($LASTEXITCODE -ne 0) { throw "Compile B failed" }

jar --create --file app-a.jar --date=2022-01-01T00:00:00Z --main-class PackagingAopDemo -C out-a .
if ($LASTEXITCODE -ne 0) { throw "JAR A failed" }

jar --create --file app-b.jar --date=2022-01-01T00:00:00Z --main-class PackagingAopDemo -C out-b .
if ($LASTEXITCODE -ne 0) { throw "JAR B failed" }

$hashA = (Get-FileHash -Algorithm SHA256 app-a.jar).Hash
$hashB = (Get-FileHash -Algorithm SHA256 app-b.jar).Hash
if ($hashA -ne $hashB) { throw "JAR HASH MISMATCH" }
Write-Host "SHA256_EQUAL true"

java -jar app-a.jar
java -jar app-b.jar --audit
~~~

Đây là ví dụ với source được giữ cố định và hai thư mục output mới, cùng công cụ build. Tùy chọn `jar --date` đã được kiểm tra trực tiếp trong môi trường chạy thử; không nên suy ra chỉ dùng tùy chọn này thì mọi dự án hoặc phiên bản JDK đều có reproducible JAR. Với dự án thật, còn phải cố định các inputs đã nêu trong mục 8.

Đầu ra đã được kiểm chứng khi chạy thử:

~~~text
SHA256_EQUAL true
MODE PLAIN
BUSINESS book
RESULT OK:2
CALLER units must be positive
MODE AUDIT
AUDIT before book
BUSINESS book
AUDIT after book
RESULT OK:2
AUDIT before book
AUDIT throwing IllegalArgumentException
CALLER units must be positive
~~~

### 9.2. Phân tích kết quả

**`SHA256_EQUAL true`:** trong thí nghiệm cụ thể, hai JAR có cùng bytes. Điều này kiểm tra khả năng tái lập của recipe này với cùng môi trường, **không chứng minh mọi weaver hoặc build pipeline khác đều deterministic**.

**`MODE PLAIN`:** caller giữ target gốc, không có audit wrapper. `book(2)` trả `OK:2`; `book(0)` ném `IllegalArgumentException` theo hợp đồng.

**`MODE AUDIT`:** caller giữ proxy, nên advice chạy trước/sau ở nhánh thành công và ghi lỗi ở nhánh exceptional. Handler bóc `InvocationTargetException` để caller vẫn nhận exception gốc. Logic nghiệp vụ không bị đổi.

**Kết luận:** hai artifact được build cùng bytes, nhưng runtime arguments tạo **hai chế độ advice**. Đây là demo **proxy runtime**, không phải bytecode weaving; nó chứng minh rằng reproducible build và reproducible aspect behavior không đồng nhất.

## 10. Khi dùng weaving thật, pipeline cần bổ sung gì?

Nếu sử dụng CTW/binary weaving thật, một pipeline hợp lý về ý niệm:

~~~text
pinned source / dependencies / toolchain
             |
      compile to raw
             |
       weave with exact tool + policy
             |
    inspect/verify transformed class
             |
       package with normalized metadata
             |
       test on final woven artifact
             |
       hash / sign / publish
~~~

Đây là **pseudocode quy trình**, không phải cú pháp của một weaver cụ thể. Các nguyên tắc:

- **Không ký artifact rồi tiếp tục sửa bytecode** mà không cập nhật xác thực integrity.
- **Không test chỉ trên raw classes** rồi kết luận woven artifact tương đương.
- **Không đưa woven output trở lại bước weaving khác** nếu thiếu hợp đồng dệt lặp rõ.
- **Không ghi hash raw.jar** như thể đó là hash bản đã instrument.
- **Không bỏ qua runtime support dependencies** mà advice đã được dệt cần đến.

Với LTW, phần artifact có thể không chứa mã chèn nhưng deployment phải kèm agent/config và test classloading; với proxy, deployment phải kèm interceptor/wiring policy.

## 11. Uber-JAR, shading, ký JAR và multi-release JAR

### 11.1. Dependency và uber-JAR

Khi gom các dependencies thành một JAR lớn, class files và resources từ nhiều nguồn có thể bị trộn. Nếu một thư viện đã được woven trước đó, bước weaving tổng có thể xử lý lại phần ấy hoặc áp thêm policy chồng lấn.

Vì vậy, phải biết **thư viện đầu vào raw hay woven**, và một chủ sở hữu rõ cho từng bước instrument. Nếu có nhiều version cùng class, cần quy tắc resolution rõ ràng.

### 11.2. Shading/relocation

Một công cụ relocation có thể thay tên package/class mà pointcut dùng để match. Việc weaving trước hay sau relocation có thể chọn tập join point khác nhau.

Kiểm thử phải chạy trên **artifact cuối sau relocation**, không chỉ dựa vào pointcut từng đúng ở source tree.

### 11.3. Ký và checksum

Nếu archive được ký trước khi một công cụ viết lại class entries, chữ ký của entry đã thay có thể không còn hợp lệ. Mọi bước biến đổi cần hoàn tất trước khi ký bản phát hành cuối. Với LTW, JAR trên disk có thể không đổi nhưng **bytecode được định nghĩa trong runtime** đã qua transformation; nên cần chính sách tin cậy cho cả artifact lẫn agent.

### 11.4. Multi-release JAR

JAR có thể chứa các class variants ở `META-INF/versions/...`. Một phiên bản JVM có thể chọn implementation khác phiên bản khác. Nếu chỉ weaving class ở root mà bỏ qua versioned entries được dùng trên JDK khác, AOP coverage có thể khác giữa các môi trường. Phải test những JDK được hỗ trợ với artifact cuối.

## 12. Runtime classloader, module và agent lifecycle

Với LTW/instrumentation, hai máy có thể khác:

- Runtime JDK/JVM version.
- Classloader định nghĩa class.
- Module exports/opens hoặc chính sách truy cập.
- Thứ tự đăng ký transformer.
- Thứ tự class được nạp.
- Những agent khác cùng chạy.
- Trạng thái class đã được định nghĩa trước khi agent cài.
- Quy tắc lỗi khi bytecode transformation không thành công.

Nếu lỗi chỉ xuất hiện trên production, đừng vội kết luận source khác. So **hash app artifact** và **launch flags + agent/version/config** trước, rồi quan sát load order và classloader identity.

Đối với agent runtime, không được giả định `-javaagent` đã được bật thì **mọi class** đều được weaving. Phải xác minh đúng target class nằm trong scope, classloading/transformer chạy ở thời điểm phù hợp, và join point thật tạo advice event đúng kỳ vọng.

## 13. Reproducible release cần lưu thông tin gì?

Một release manifest hữu ích:

| Trường | Lý do |
| --- | --- |
| `applicationArtifactSha256` | Xác thực bytes của JAR phát hành |
| `sourceRevision` | Xác định nguồn build |
| `compilerJdkVersion` | Tái tạo bytecode input |
| `dependencyLockAndChecksums` | Loại trừ thay dependency ngầm |
| `weaverVersion` / `agentVersion` | Tái hiện instrumentation |
| `aspectPolicyVersion` | Khóa tập pointcut/advice |
| `rawAndWovenArtifactIdentity` | Truy vết transformation |
| `jvmOptions` | Tái hiện quyền/module/classloading setup |
| `runtimeWiringVersion` | Tái hiện proxy/interceptor graph |
| `integrationTestResult` | Chứng minh behavior trên release artifact |
| `packageAndSigningMetadata` | Đối chiếu integrity và nguồn phát hành |

Một **SBOM** hoặc provenance record hỗ trợ theo dõi công cụ/dependencies, nhưng **không tự chứng minh các pointcut hoạt động**. Cần test integration hoặc sentinel join point trong môi trường tương đương thật.

### Release identity không chỉ là JAR hash

Có thể mô hình hóa release như một bộ giá trị:

~~~text
DeploymentIdentity = (
  applicationArtifactHash,
  runtimeJdk,
  weaverOrAgentVersion,
  pointcutPolicyVersion,
  jvmFlags,
  classloaderLayout,
  proxyRegistrationConfig
)
~~~

Danh sách là mô hình kiểm soát AOP, chưa bao gồm mọi input nghiệp vụ ngoài như database, external APIs, secrets và network. Nhưng nó tốt hơn hẳn cách coi “rollback app.jar” là rollback đầy đủ.

## 14. Rollback, canary và drift giữa các môi trường

### CTW/binary weaving

Rollback thường cần đúng **woven artifact** của release cũ. Nếu bản cũ được biên dịch từ raw source nhưng dùng một weaver mới, nó có thể không phải bản cũ về mặt bytecode; đừng gọi đây là rollback nguyên trạng.

### LTW

Rollback app JAR nhưng không rollback agent/policy có thể để lại hành vi mới. Một class đã load dưới transformer cũ có thể không tự phục hồi chỉ vì file config thay đổi; lifecycle thường cần restart hoặc cơ chế redefinition được hỗ trợ.

### Runtime proxy

Rollback runtime config/handler và bảo đảm caller vẫn nhận proxy đúng. Cùng application JAR nhưng policy `auditEnabled` khác có thể có AOP behavior khác; không coi checksum ứng dụng giống là đã xác nhận rollout hoàn tất.

### Canary/staging

Canary chỉ có ý nghĩa kiểm tra AOP khi **agent, flags, config, đường gọi và version artifact** phù hợp mục tiêu. Tránh staging không bật weaving trong khi production có weaving rồi dùng staging làm bằng chứng mọi join point đều đúng.

### Các dấu hiệu drift

| Triệu chứng | Cần kiểm tra |
| --- | --- |
| Audit thiếu trên một node | Proxy bypass, agent không khởi động, pointcut không match |
| Audit xuất hiện hai lần | Double weaving, proxy lồng, pointcut chồng lấn |
| JAR khác hash dù source không đổi | Timestamp, metadata, file order, compiler/weaver |
| JAR giống hash nhưng trace khác | Agent, policy, classloader, runtime flag |
| Startup lỗi ở một JVM | Bytecode verifier, module/classfile compatibility |
| Rollback không khôi phục behavior | Runtime config/agent/proxy graph chưa rollback |
| Thêm shading làm advice biến mất | Pointcut theo tên không còn match |
| Advice chỉ chạy sau restart | Class load timing hoặc config chỉ áp dụng ở startup |

## 15. Chiến lược kiểm thử ba lớp

### Lớp A — kiểm thử tính tái lập của build

1. Build sạch cùng nguồn trong **hai workspace độc lập**.
2. Cố định compiler, dependencies, weaver và cờ cấu hình.
3. Chuẩn hóa metadata JAR/ZIP, resource order và generated files.
4. So SHA-256 của **artifact cuối**.
5. Nếu khác, so archive entries, manifest, class bytes và transform logs để tìm nguyên nhân.
6. Không sửa artifact đầu ra thủ công cho “khớp hash” mà bỏ qua nguyên nhân.

### Lớp B — kiểm thử hành vi AOP

1. Một join point được chọn chạy advice đúng số lần.
2. Join point không được chọn không tạo event.
3. Advice quan sát bảo toàn return value và exception gốc.
4. Kiểm thứ tự nhiều advice.
5. Kiểm overload, generic/bridge nếu liên quan, call vs execution.
6. Kiểm self-invocation và đường gọi trực tiếp bỏ qua proxy.
7. Nếu có retry/cache, đếm số lần target thật chạy.
8. Nếu có LTW, kiểm class loading và agent startup.

### Lớp C — kiểm thử deployment

1. Chạy artifact cuối dưới JVM/agent/config release thật.
2. Test canary, restart, rollback với toàn bộ deployment tuple.
3. Kiểm đường thất bại khi agent thiếu, class không dệt hoặc pointcut không match.
4. Đánh giá fail-open/fail-closed nếu instrumentation liên quan chính sách bắt buộc.
5. Đo performance và overhead dưới tải đại diện.
6. Xác minh không ghi thông tin nhạy cảm vào logs/metrics khi thêm advice.

**Một unit test gọi trực tiếp method advice không chứng minh weaver/proxy đã kích hoạt advice ở join point thật.** Tương tự, hash JAR trùng không chứng minh object graph runtime tạo proxy đúng.

## 16. Những ví dụ chẩn đoán

**Tình huống A — cùng source, khác JAR hash:** source không đổi nhưng hai máy có JDK/manifest timestamps khác. Cần pin toolchain và chuẩn hóa packaging. Nếu còn bytecode weaving, phải kiểm cả weaver version và transformation order. Hash khác không tự nói rằng advice sai.

**Tình huống B — cùng JAR, khác audit log:** một máy truyền `--audit`, máy khác không. Đây là runtime policy drift, không phải lỗi reproducible build. Demo Java 17 chứng minh điều này.

**Tình huống C — một JAR woven được dệt lại sau package:** cần kiểm soát raw/woven boundary và chỉ có một chủ sở hữu weaving. Không mặc định mọi weaver luôn từ chối dệt lặp.

**Tình huống D — LTW bỏ sót class:** class đã load trước khi transformer được đăng ký, hoặc classloader/module ngoài scope. Chỉnh startup/agent configuration và test trên deployment đúng, không chỉ copy lại JAR.

**Tình huống E — signer chạy trước weaver:** JAR cuối có class entries đã sửa sau ký. Cần ký sau mọi transformation và xác minh integrity bản phát hành.

**Tình huống F — cùng woven artifact nhưng một node chạy JDK khác:** cần kiểm module/classfile compatibility, multi-release JAR variants và runtime dependencies. Artifact identity không loại bỏ các điều kiện runtime.

## 17. Những sai lầm thường gặp

1. **“CTW nghĩa là advice chạy khi compile.”** Không: chỉ việc kết hợp diễn ra ở build, advice vẫn thực thi tại join point runtime.
2. **“LTW là proxy.”** Không: một bên biến đổi class lúc nạp, bên kia có thể chỉ định tuyến qua wrapper.
3. **“JAR hash giống thì AOP behavior cũng giống.”** Không nếu runtime agent, flags, classloader hoặc proxy policy khác.
4. **“Source giống thì chắc chắn bit-for-bit reproducible.”** Không nếu timestamp, metadata, generated files hoặc toolchain khác.
5. **“Đổi hash chứng minh nghiệp vụ đổi.”** Không nhất thiết; thay metadata đóng gói cũng ảnh hưởng checksum.
6. **“Raw classes và woven classes có thể lưu chung không cần phân biệt.”** Dễ gây dệt lại và build không tái lập.
7. **“Ký JAR rồi thay bytecode không sao.”** Class entry thay đổi có thể phá signature.
8. **“Có agent thì mọi class đều được instrument.”** Phải xác minh scope, classloader, load order và capability.
9. **“Tắt agent là class đã load tự quay về bytecode ban đầu.”** Không có bảo đảm chung.
10. **“Proxy thấy mọi self-invocation và private method.”** Không đúng trong nhiều mô hình proxy thông thường.
11. **“Shading không ảnh hưởng pointcut.”** Đổi tên class có thể đổi matching.
12. **“Một test advice pass là đủ.”** Phải test artifact và đường gọi thật.
13. **“Chỉ cần pin `javac`.”** Weaver, dependencies, config, packaging/signing cũng ảnh hưởng bytes.
14. **“Weaver chạy hai lần luôn tạo double advice.”** Tùy công cụ và cách xử lý input đã dệt.
15. **“Benchmark raw JAR đại diện cho woven JAR.”** Không khi advice gây chi phí ở runtime.
16. **“Rollback JAR là rollback cả AOP.”** Runtime agent/proxy policy có thể vẫn ở version khác.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Dệt tĩnh xong trước khi ứng dụng chạy. Advice có còn chạy ở runtime không?  
**Trả lời:** Có. Dệt là công việc kết hợp; advice chạy lúc join point thực thi.

**Câu 2.** Vì sao binary weaving nên tách hai folder raw/woven?  
**Trả lời:** Để truy vết input/output, tránh dệt lặp ngoài ý định và tạo build sạch, dễ tái lập.

**Câu 3.** Tại sao hai máy chạy cùng `app.jar` vẫn có audit khác nhau?  
**Trả lời:** Runtime flags, proxy registration, agent, config hoặc classloading có thể khác.

**Câu 4.** Hai JAR khác hash có chắc behavior khác nhau?  
**Trả lời:** Không; metadata hoặc timestamps khác cũng thay bytes. Cần test hành vi.

**Câu 5.** Đổi chữ ký JAR sau weaving có được không?  
**Trả lời:** Nên ký artifact cuối sau tất cả bước biến đổi; không nên sửa entry đã ký rồi tin integrity vẫn hợp lệ.

**Câu 6.** Vì sao `jar --date` chưa đủ để bảo đảm reproducible build toàn dự án?  
**Trả lời:** Còn JDK/compiler, dependencies, file order, generated metadata, weaver và nhiều yếu tố khác.

**Câu 7.** Nếu LTW agent chạy sau khi class được định nghĩa thì điều gì có thể xảy ra?  
**Trả lời:** Class có thể không được dệt bởi cơ chế load-time thông thường; cần đánh giá riêng retransformation hoặc startup order.

**Câu 8.** Khi rollback LTW deployment, chỉ rollback JAR có đủ không?  
**Trả lời:** Không. Phải đồng bộ agent, aspect config, JVM options và classload lifecycle liên quan.

**Câu 9.** Demo Java chạy `PLAIN` và `AUDIT` từ hai JAR cùng checksum chứng minh điều gì?  
**Trả lời:** Artifact bytes giống nhau nhưng runtime proxy policy tạo khác biệt về hành vi AOP.

**Câu 10.** Điều gì bổ sung cho bằng chứng hash khi xác minh AOP?  
**Trả lời:** Integration tests trên artifact cuối, xác minh pointcut khớp đúng, advice chạy đúng số lần và không đổi result/exception ngoài hợp đồng.

## 19. Tổng kết

**Các thời điểm weaving khác nhau tạo những yêu cầu đóng gói, triển khai và tái lập khác nhau.** CTW và binary weaving thường đưa behavior vào artifact đã biến đổi; LTW chuyển phần kết hợp sang lifecycle class loading; runtime proxy/interceptor áp dụng advice trên các đường gọi qua wrapper mà không cần sửa target bytecode.

Để **bản dựng tái lập**, phải pin source, JDK, dependencies, weaver, policy, transformation order và metadata đóng gói rồi hash/ký artifact cuối. Để **triển khai tái lập**, còn cần đồng bộ agent/runtime config, classloader, flags, proxy registration và đường gọi thật. Hai chứng cứ bổ sung cho nhau là **artifact provenance/checksum** và **integration test hành vi advice**. Khi quản lý đầy đủ cả hai, có thể phát hành, đối soát, canary và rollback AOP một cách dự đoán được, thay vì chỉ dựa vào việc source code không đổi.