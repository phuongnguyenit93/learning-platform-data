# Kiểm tra mã hoặc mô-đun có nằm trong phạm vi dệt (weaving scope)

## 1. Mục tiêu và tình huống thực tế

Trong **Aspect-Oriented Programming (AOP)**, có thể viết đúng pointcut nhưng advice vẫn không chạy. Ví dụ một aspect chọn `execution(void demo..*.run())`, còn ứng dụng có hai method `demo.core.Core.run()` và `demo.extra.Extra.run()`. Pointcut match chữ ký của **cả hai**; tuy nhiên nếu trình dệt (weaver) chỉ xử lý bytecode `Core.class`, lời gọi vào `Extra.run()` sẽ không có advice.

Đây là lỗi thường gặp sau khi:
- Chuyển một class sang package hoặc mô-đun build khác.
- Tách source thành JAR hoặc dependency được compile riêng.
- Đổi cấu hình compile-time/binary/load-time weaving.
- Đóng gói ứng dụng tạo ra bản class plain và woven trùng tên.
- Đổi classloader hoặc sử dụng module path.
- Chỉ cấu hình aspect ở một test/build profile mà không đưa vào bản chạy thực tế.

Sau bài này, bạn biết cách phân biệt **pointcut match** với **bytecode được weave**, kiểm tra các input của compiler/weaver, cách AspectJ tìm aspect, cách runtime chọn class, và cách chứng minh một join point đã thực sự được instrument. Bài có ví dụ Java 17 chạy được cho ba trường hợp: chỉ weave Core, weave thêm Extra, và dùng load-time weaving giới hạn trong package Core.

Phạm vi là AOP cơ bản và nâng cao nói chung, lấy AspectJ làm ví dụ về bytecode weaving; không giả định mọi cơ chế AOP có cùng tập join point hay tính năng.

## 2. Bốn câu hỏi phải trả lời trước khi sửa pointcut

Một đường đi chẩn đoán:

```text
Aspect có được phát hiện và bật?
   |
Target class/JAR có nằm trong weaving input/scope?
   |
Bytecode đã được biến đổi và được JVM load đúng bản?
   |
Join point thực thi có thỏa pointcut và điều kiện runtime?
   |
Advice chạy
```

Mỗi câu hỏi kiểm tra một thành phần độc lập:

| Lớp | Chức năng | Bằng chứng cần có |
|---|---|---|
| **Aspect discovery** | Compiler/weaver tìm thấy aspect và khai báo | Compiled aspect, source input, aspect path, agent configuration |
| **Weaving scope** | Xác định loại bytecode nào có thể được biến đổi | Danh sách source, `-inpath`, LTW include/exclude |
| **Class loading** | Chương trình dùng đúng class đã biến đổi | Artifact chạy thật, classpath/module path, classloader, class loading log |
| **Pointcut / runtime matching** | Join point và điều kiện tại lời gọi thỏa quy tắc | Weave-info và một lần gọi thử thực sự kích hoạt advice |

**Classpath không đồng nghĩa với weaving input.** Việc một JAR xuất hiện trong danh sách dependency chỉ chứng minh compiler có thể tìm thấy type để giải quyết reference, không chứng minh mọi class trong JAR được weave. Tương tự, việc ứng dụng chạy có `aspectjrt` không chứng minh có agent LTW.

Nếu bật logging chi tiết mà vẫn không thấy event, không nên lập tức mở selector thành wildcard rộng hơn. Một pointcut `execution(* *(..))` quá rộng có thể instrument helper nóng, in dữ liệu nhạy cảm hoặc áp nhầm transaction/retry.

## 3. Những cách weave được dùng trong thực tế

### Compile-time weaving (CTW)

Compiler AspectJ `ajc` nhận source Java và aspect source, tạo bytecode có advice tại join point được chọn:

```text
Core.java + ScopeTrace.aj --ajc--> Core.class đã weave
Extra.java --javac--> Extra.class chưa weave
```

Nếu `Extra.java` không được `ajc` xử lý, một `execution` advice trên thân `Extra.run()` không tự xuất hiện chỉ vì pointcut khớp cú pháp.

### Post-compile/binary weaving

Một class/JAR được biên dịch bằng Java compiler, sau đó truyền cho AspectJ:

```text
Extra.java --javac--> out-extra/Extra.class
out-extra --ajc -inpath + -aspectpath--> out-extra-woven/Extra.class
```

Cần phân biệt `-inpath` (**đối tượng cần weave**) và `-aspectpath` (**nơi chứa compiled aspect**). `-classpath` cung cấp những dependency cần để resolve type.

### Load-time weaving (LTW)

Weaver can thiệp khi JVM nạp class. Nó cần agent/cơ chế load phù hợp, compiled aspects có thể nhìn thấy, cấu hình include/exclude, và class chưa bị nạp trước khi agent có cơ hội biến đổi.

```text
plain class --classloader + weaving agent + config--> loaded transformed class
```

Với AspectJ, `aspectjweaver` và cấu hình `META-INF/aop.xml` thường được dùng để khởi tạo LTW. **`aspectjrt` đơn lẻ không bật LTW.** Classloader/module boundaries có thể khiến cấu hình hoạt động ở một thành phần nhưng không ở thành phần khác.

## 4. Kiểm tra phạm vi theo đúng loại join point

Hai dạng điểm chặn cần phân biệt:

```text
Caller method -- call join point --> Target.run()
                                      |
                                      +-- execution join point ở thân Target.run()
```

- `execution(void demo.core.Core.run())` chọn việc thực thi method. Để advice chạy, **Core bytecode chứa execution** phải được weave hoặc biến đổi khi load.
- `call(void demo.core.Core.run())` chọn vị trí thực hiện lời gọi trong **caller**. Cần weave bytecode nơi call site tồn tại, không nhất thiết chỉ weave Core.
- Một lời gọi `this.inner()` trong cùng object vẫn đi vào execution đã weave, nhưng nhiều cơ chế **proxy interception** chỉ chặn lời gọi đi qua proxy, vì vậy tự gọi nội bộ có thể bypass proxy.

Điều đó giải thích vì sao “mô-đun nào phải weave?” không có đáp án chung nếu chưa biết đang cần `call`, `execution` hay proxy invocation.

## 5. Ví dụ thực nghiệm: cấu trúc nguồn

Bốn file:

```text
src/
├── demo/
│   ├── App.java
│   ├── core/Core.java
│   └── extra/Extra.java
└── ScopeTrace.aj
```

**src/demo/core/Core.java:**

```java
package demo.core;
public final class Core {
    public void run() {
        System.out.println("core-body");
    }
}
```

**src/demo/extra/Extra.java:**

```java
package demo.extra;
public final class Extra {
    public void run() {
        System.out.println("extra-body");
    }
}
```

**src/demo/App.java:**

```java
package demo;
import demo.core.Core;
import demo.extra.Extra;
public final class App {
    public static void main(String[] args) {
        new Core().run();
        new Extra().run();
    }
}
```

**src/ScopeTrace.aj:**

```java
public aspect ScopeTrace {
    pointcut selected(): execution(void demo..*.run());

    before(): selected() {
        System.out.println("weave:" +
                thisJoinPointStaticPart.getSignature()
                        .getDeclaringType().getSimpleName());
    }
}
```

Pointcut `execution(void demo..*.run())` đủ rộng để match cả `Core.run()` và `Extra.run()`. Nó không đổi giữa các lượt test. `ScopeTrace.aj` là cú pháp AspectJ code-style và phải được biên dịch bằng compiler phù hợp như `ajc`, không phải Java source thuần cho `javac`.

Khi advice chạy, nó in `weave:Core` hoặc `weave:Extra` trước dòng body. Nếu không có advice, body vẫn in `core-body` hoặc `extra-body`. Vì vậy output tách bạch “method có chạy?” và “advice có chạy?”.

## 6. Chuẩn bị Java 17 và AspectJ

Các ví dụ được thử với **AspectJ 1.9.24** và `ajc -17`. Cần JDK hỗ trợ Java 17, Maven hoặc cách cung cấp các JAR tương ứng.

```bash
mvn -B dependency:get -Dartifact=org.aspectj:aspectjtools:1.9.24 -Dtransitive=false
mvn -B dependency:get -Dartifact=org.aspectj:aspectjrt:1.9.24 -Dtransitive=false
mvn -B dependency:get -Dartifact=org.aspectj:aspectjweaver:1.9.24 -Dtransitive=false
```

Các lệnh dưới đây dùng **Windows PowerShell**, chạy tại thư mục chứa `src`. JAR được tham chiếu theo Maven local repository mặc định; nếu cấu hình repository khác, cần sửa đường dẫn tương ứng.

```powershell
$repo = Join-Path $HOME ".m2/repository/org/aspectj"
$tools = Join-Path $repo "aspectjtools/1.9.24/aspectjtools-1.9.24.jar"
$rt = Join-Path $repo "aspectjrt/1.9.24/aspectjrt-1.9.24.jar"
$weaver = Join-Path $repo "aspectjweaver/1.9.24/aspectjweaver-1.9.24.jar"
```

Với Linux/macOS, nhiều entry classpath được ngăn bằng dấu hai chấm `:` thay cho dấu chấm phẩy `;`.

## 7. Case A: chỉ mô-đun Core được weave

Biên dịch Extra bằng `javac`, còn `Core.java` và `ScopeTrace.aj` bằng `ajc`. Sau đó biên dịch `App` để gọi cả hai:

```powershell
New-Item -ItemType Directory -Force out-extra,out-core-woven,out-app | Out-Null

javac --release 17 -d out-extra src/demo/extra/Extra.java

java -cp $tools org.aspectj.tools.ajc.Main -17 -showWeaveInfo -classpath $rt -d out-core-woven src/demo/core/Core.java src/ScopeTrace.aj

javac --release 17 -classpath "out-extra;out-core-woven" -d out-app src/demo/App.java

java -cp "out-app;out-core-woven;out-extra;$rt" demo.App
```

**Output nghiệp vụ đã kiểm chứng:**

```text
weave:Core
core-body
extra-body
```

Giải thích:

1. `Core.run()` được weave, nên xuất hiện `weave:Core`.
2. `Extra.run()` có chạy, chứng minh bởi `extra-body`.
3. Không xuất hiện `weave:Extra`, dù pointcut mô tả chữ ký của method đó.
4. Vì Extra được biên dịch bằng `javac` riêng và không đưa vào `ajc` như target input, execution bytecode của nó vẫn là bản plain.

Khi có `-showWeaveInfo`, `ajc` báo execution join point `demo.core.Core.run()` được advice của `ScopeTrace` áp dụng. Thông báo dạng diagnostics có thể chứa file path/line number khác giữa các máy và không được tính vào stdout nghiệp vụ cố định ở trên.

Đây là **bằng chứng trực tiếp rằng pointcut scope và weaving scope khác nhau**.

## 8. Case B: mở rộng weaving input sang Extra

Vẫn giữ nguyên `ScopeTrace.aj` và bytecode woven của Core. Lần này dùng `-inpath` để weave class đã biên dịch của Extra:

```powershell
New-Item -ItemType Directory -Force out-extra-woven | Out-Null

java -cp $tools org.aspectj.tools.ajc.Main -17 -showWeaveInfo -classpath "out-extra;out-core-woven;$rt" -inpath out-extra -aspectpath out-core-woven -d out-extra-woven

java -cp "out-app;out-core-woven;out-extra-woven;$rt" demo.App
```

**Output đã kiểm chứng:**

```text
weave:Core
core-body
weave:Extra
extra-body
```

Kết quả thay đổi vì:

- `-inpath out-extra` xác định những class bytecode cần weave.
- `-aspectpath out-core-woven` giúp công cụ tìm compiled aspect `ScopeTrace`.
- `-d out-extra-woven` tạo một output mới đã biến đổi.
- Lệnh chạy dùng `out-extra-woven` **thay cho** `out-extra`, nên JVM chọn đúng bản class đã weave.

Ở Case B, `-showWeaveInfo` còn có thông báo join point của `demo.extra.Extra.run()` được advice áp dụng. Kết hợp **build diagnostics** và **runtime event** là cách xác minh mạnh hơn chỉ nhìn rằng compiler trả exit code 0.

Nếu lệnh binary weaving có lỗi, đừng tiếp tục chạy bản class cũ rồi coi đó là kết quả mới. Trong build tự động, nên dừng khi `ajc` trả mã lỗi khác 0.

## 9. Phân biệt JAR/classpath với artifact đã weave

Một nguyên nhân phổ biến khác: `out-extra-woven/Extra.class` có tồn tại nhưng runtime lại nạp bản plain ở `out-extra` vì có hai bản trùng binary name trên classpath.

Ví dụ:

```text
Mong muốn:
  out-app;out-core-woven;out-extra-woven;aspectjrt

Nguy cơ:
  out-app;out-core-woven;out-extra;out-extra-woven;aspectjrt
```

Với classloader thông thường, tìm kiếm class có thứ tự và có thể chọn bản plain trước. Một custom classloader còn có cơ chế ưu tiên parent/child riêng. **Không khẳng định JVM sẽ hợp nhất hai bản class.**

Những phép kiểm tra có giá trị:

- In đúng command line/startup classpath hoặc module path đang dùng.
- Xem nội dung JAR cuối cùng, xác nhận không có class trùng tên do shading/assembly.
- Quan sát class loading bằng tùy chọn JVM phù hợp, ví dụ `-Xlog:class+load=info` trên JVM hỗ trợ Unified Logging.
- Kiểm tra `Class.getProtectionDomain().getCodeSource()` trong môi trường debug nếu nguồn class được khai báo; đừng dựa tuyệt đối vào đó khi loader cung cấp nguồn `null`.
- Phân biệt một type cùng binary name được nạp bởi **hai classloader** thành hai định nghĩa runtime khác nhau.

**Thông điệp then chốt:** build tạo bản woven không có nghĩa deployment chọn bản woven.

## 10. Case C: load-time weaving theo include scope

Để quan sát cùng hiện tượng ở load time, tạo `Core.class` **plain** rồi dùng AspectJ weaver agent chỉ include package `demo.core`. `ScopeTrace.class` được lấy từ output đã biên dịch ở Case A.

**Tạo Core plain:**

```powershell
New-Item -ItemType Directory -Force out-core-plain,out-config/META-INF | Out-Null
javac --release 17 -d out-core-plain src/demo/core/Core.java
```

Lưu tệp **out-config/META-INF/aop.xml**:

```xml
<aspectj>
    <aspects>
        <aspect name="ScopeTrace"/>
    </aspects>
    <weaver options="-showWeaveInfo">
        <include within="demo.core.*"/>
    </weaver>
</aspectj>
```

Ở đây `<aspects>` khai báo aspect; `<include within="demo.core.*"/>` chỉ cho phép những type thuộc nhóm `demo.core` nằm trong LTW scope. Điều kiện này khác pointcut `execution(void demo..*.run())` ở source aspect.

**Chạy với agent:**

```powershell
java "-javaagent:$weaver" -cp "out-config;out-app;out-core-plain;out-extra;out-core-woven;$rt" demo.App
```

Vì `out-core-plain` được liệt kê trước `out-core-woven`, class Core được JVM tìm từ bản plain; agent biến đổi nó lúc load. Thư mục `out-core-woven` còn cung cấp **compiled aspect**. Trong dự án thật nên đóng gói aspect riêng để không vô tình có các target class trùng tên.

**Stdout nghiệp vụ đã kiểm chứng:**

```text
weave:Core
core-body
extra-body
```

Ở thí nghiệm LTW trên JVM mới, có thể có thêm cảnh báo/diagnostic từ weaver trong stderr. `-showWeaveInfo` cũng báo weave thành công đối với `Core.run()`. Những thông báo đó phụ thuộc phiên bản và môi trường; không phải ba dòng stdout cố định.

Điều được chứng minh: có agent LTW nhưng **Extra vẫn không được weave** vì cấu hình `include` giới hạn target types. Aspect và pointcut được nhận diện đúng không có nghĩa mọi classloader/type đều được instrument.

## 11. Debug load-time weaving theo từng tầng

Khi LTW không chạy, thực hiện theo thứ tự:

1. **Agent**: JVM có thật sự được khởi động với `-javaagent:path/to/aspectjweaver.jar`? JAR runtime khác với JAR weaver.
2. **Config**: `META-INF/aop.xml` có nằm trên resource path mà loader/weaver nhìn thấy không? Artifact fat JAR, shading hoặc packaging có làm mất file?
3. **Aspect**: tên aspect đúng, class đã biên dịch và dependency cần thiết có thể load được không?
4. **Include/exclude**: lớp target có bị bộ lọc `within` loại trừ không? Mẫu include của weaver không phải là pointcut của advice.
5. **Classloader**: JVM dùng loader nào để định nghĩa class? Agent có hoạt động cho loader đó không?
6. **Thời điểm**: target class đã load trước khi cấu hình/weaver được áp dụng chưa?
7. **Class target**: loader có thật sự nạp class cần instrument không, hay một bản trùng tên từ artifact khác?
8. **Join point**: sau khi thấy class thuộc scope, pointcut có match method/annotation/args và điều kiện động không?
9. **Runtime path**: phương thức có được gọi thật không? Có overload, callback, interface implementation hoặc nhánh điều kiện khác?

Chỉ khi có bằng chứng weaving input đúng và class đã load phù hợp mà advice vẫn không chạy, mới nên sửa pointcut. Đừng thay đổi đồng thời agent, pointcut, packaging và API vì sẽ mất khả năng khoanh vùng nguyên nhân.

## 12. Mô-đun build khác mô-đun Java (JPMS)

Từ “mô-đun” có thể chỉ:

- **Mô-đun của build/kiến trúc**: source set, subproject, JAR, package, library.
- **JPMS module**: một module được định nghĩa bằng `module-info.java` với module path, exports/opens và dependency graph.

Với mô-đun build, hãy tìm class/JAR đầu ra và xác định có nằm trong source input, `-inpath` hoặc phạm vi LTW hay không.

Với JPMS, việc weave còn có thể chịu ảnh hưởng module readability, runtime encapsulation, classloader và JVM/AspectJ compatibility. Không nên thêm hàng loạt tùy chọn `--add-opens` một cách mù quáng: cần chỉ ra package nào thực sự cần được mở và cơ chế nào yêu cầu điều đó. Một câu lệnh hoạt động trên classpath không phải bằng chứng nó sẽ hoạt động giống hệt khi chuyển toàn bộ sang module path.

Đừng suy ra “module X phụ thuộc vào thư viện aspect” đồng nghĩa “mọi class trong module X được weave”. Đây là hai quan hệ hoàn toàn khác nhau.

## 13. Loại join point quyết định nơi cần weave

Ví dụ `App.main` gọi `Core.run`:

```text
App.class: bytecode chứa lệnh gọi -> call join point
Core.class: bytecode chứa method body -> execution join point
```

Đối với `execution`, mục tiêu weave là code **chứa thân method**. Đối với `call`, mục tiêu weave là code **của caller** chứa vị trí gọi method. Một lỗi cấu hình hay gặp là chỉ weave target nhưng muốn đo `call` tại một module caller khác; hoặc chỉ weave caller nhưng muốn áp `execution` vào method target.

Với proxy interception, lớp proxy và đường gọi qua proxy là mấu chốt. Self-invocation trong implementation có thể không đi qua proxy. Với AspectJ execution weaving, một self-call vẫn đi vào thân method đã được biến đổi. Không đánh đồng những cơ chế này khi viết kiểm thử phạm vi.

## 14. Đã weave nhưng không có event: các nguyên nhân không phải scope

Ngay cả khi weave-info xác nhận một shadow/join point đã được instrument, một testcase cụ thể vẫn có thể không thấy advice:

- Method chưa được gọi.
- Gọi overload khác hoặc implementation khác với selector.
- `args`, `this`, `target` hay điều kiện runtime của pointcut không thỏa.
- Annotation ở interface nhưng pointcut tìm metadata trên implementation (hoặc ngược lại).
- Compiler sinh generic bridge/synthetic method và matcher chọn signature ngoài dự kiến.
- Advice lọc event, sampling hoặc sink làm mất thông tin.
- Method trả future sớm nhưng side effect diễn ra trong task khác không nằm trong scope.

Nên phân biệt **static match tại vị trí bytecode** với **dynamic match tại một lần chạy**. Dùng fixture đơn giản có `execution` không phụ thuộc điều kiện runtime để xác minh weaving scope, sau đó mới kiểm tra pointcut động và logic ứng dụng.

## 15. Mô-đun bất đồng bộ và callback

Một method nằm trong mô-đun core có thể chỉ gửi việc sang queue/executor, còn side effect thực sự nằm trong mô-đun worker khác:

```text
core.submit() -> returns future
                    |
                    +--> worker.execute() -> actual side effect
```

Nếu chỉ weave execution của `core.submit`, advice quanh nó thường chạy đến thời điểm **trả future handle**. Nó không tự động chặn execution của `worker.execute` nếu class worker không thuộc weaving scope.

Khi cần truy vết/cấp quyền/transaction tại chỗ phát sinh hiệu ứng, hãy:

- Xác định method thật chứa side effect và module/JAR sở hữu nó.
- Đưa đúng bytecode vào scope nếu chính sách AOP yêu cầu.
- Phân biệt event `submitted` và `completed`, quan sát future completion riêng.
- Truyền và khôi phục trace/security context qua executor nếu cần, không giả định `ThreadLocal` tự lan qua thread khác.
- Test cả đường gọi thành công, lỗi và retry trong worker.

Điều này giúp tránh một cảm giác an toàn giả: aspect trên API wrapper vẫn in log nhưng operation thực tế không được giám sát ở tầng xử lý.

## 16. Checklist xác minh trước release

- [ ] Biết đang dùng compile-time, binary hay load-time weaving, hoặc proxy interception.
- [ ] Phân biệt pointcut scope và weaving input scope.
- [ ] Liệt kê chính xác class/JAR/module cần instrument.
- [ ] Biết những source đưa vào `ajc` và những class đưa vào `-inpath`.
- [ ] Compiled aspect có ở đúng `-aspectpath` hoặc LTW config.
- [ ] Có `-showWeaveInfo` hoặc diagnostics phù hợp cho join point mong muốn.
- [ ] Runtime load bản class đã weave, không phải bản plain cùng binary name.
- [ ] Với LTW có `-javaagent`, `aop.xml`, include/exclude và loader thích hợp.
- [ ] Có positive test cho class phải weave và negative test cho class không thuộc phạm vi.
- [ ] Test phủ việc đổi package, tách module/JAR, shade/packaging và build profile.
- [ ] Phân biệt `call` và `execution` khi quyết định weave caller hay target.
- [ ] Kiểm tra overload, override, annotation, bridge method và điều kiện runtime nếu thiếu advice.
- [ ] Kiểm tra async task/consumer/callback nếu side effect chạy ngoài module ban đầu.
- [ ] Không ghi token/secret vào weave diagnostics hoặc issue report.

## 17. Quy trình chẩn đoán ngắn gọn

**Bước 1:** Viết một testcase nhỏ gọi trực tiếp method mong muốn, khẳng định body chạy.

**Bước 2:** Xác định kiểu join point và xem target nằm ở caller, target hay proxy boundary.

**Bước 3:** Kiểm tra lệnh build hoặc agent configuration, chỉ ra danh sách input và scope cụ thể.

**Bước 4:** Bật weave-info, xác định join point có được advice áp dụng ở bytecode không.

**Bước 5:** Xem bản class/JAR thực sự được JVM load, classloader và duplicate classpath entries.

**Bước 6:** So sánh event runtime với expected bằng assertion toàn bộ chuỗi, không chỉ tìm một dòng log bất kỳ.

**Bước 7:** Nếu class đã weave nhưng event thiếu, kiểm tra pointcut static/dynamic, overload, annotation và đường gọi.

**Bước 8:** Đưa test positive/negative vào CI để những lần đổi build hoặc module sau không làm mất advice âm thầm.

## 18. Tổng kết

**Một pointcut đúng về mặt chữ ký chưa chứng minh advice sẽ chạy.** Cần có aspect được nhận diện, target nằm trong phạm vi weaving, bytecode được biến đổi và runtime thực sự load đúng bản class. Khi debug, hãy tách **“không được weave”** khỏi **“pointcut không match”** và **“đường gọi thực tế không đi qua join point”**.

Ba trường hợp Core/Extra chứng minh sự khác biệt bằng cùng một pointcut: ban đầu chỉ Core được weave, sau khi đưa Extra vào `-inpath` thì Extra có advice, còn LTW chỉ include Core nên Extra vẫn plain. Kết hợp **weave-info + runtime behavior + artifact/classloader inspection** giúp kiểm tra chính xác mô-đun nào thật sự nằm trong phạm vi dệt.
