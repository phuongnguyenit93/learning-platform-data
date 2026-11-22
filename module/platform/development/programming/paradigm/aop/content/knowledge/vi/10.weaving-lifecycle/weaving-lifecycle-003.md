# Dệt khi nạp và quan hệ với cơ chế nạp lớp hoặc mô-đun trong AOP

**Dệt khi nạp (load-time weaving, LTW)** là cách đưa xử lý của **aspect/advice** vào mã chương trình khi các lớp được JVM nạp/định nghĩa, thay vì yêu cầu toàn bộ bytecode đích đã được biến đổi từ bước biên dịch. Cách tiếp cận này đặc biệt hữu ích khi một mối quan tâm cắt ngang phải áp dụng cho nhiều lớp hoặc thư viện, nhưng nó gắn chặt với **vòng đời nạp lớp, class loader, Java module, thời điểm gắn transformer và phạm vi class thật sự được xử lý**.

Một hiểu lầm dễ gặp là: “Chỉ cần khai báo aspect hoặc bật agent thì mọi phương thức được dệt.” Trên thực tế, một advice chỉ hoạt động tại join point nếu **mã chứa điểm đó đã được can thiệp theo cơ chế được hỗ trợ**, kết quả dệt phù hợp với JVM, và runtime dùng đúng phiên bản lớp được xử lý.

Đối với một class chưa được nạp, transformer có thể được gọi trước khi class được JVM định nghĩa. Đối với một class **đã được định nghĩa**, câu chuyện khác: cơ chế nạp thông thường không chạy lại chỉ vì ta thay cấu hình. Nếu muốn can thiệp về sau, cần xét **retransformation/redefinition hoặc một đường interception khác**, với nhiều giới hạn riêng.

> **Trọng tâm:** Phân biệt *load-time weaving* với *load-time class observation*, hiểu trình tự nạp–liên kết–khởi tạo lớp, xác định class loader và Java module ảnh hưởng tới weaving như thế nào, và biết cách kiểm chứng một class thực sự đã được dệt. Bài trình bày AOP cơ bản và nâng cao nói chung, không phụ thuộc framework cụ thể.

## 1. Ôn lại mô hình AOP: từ pointcut đến mã chạy

Trong AOP:

- **Join point:** vị trí/sự kiện mà công cụ có thể can thiệp, chẳng hạn method call hoặc method execution nếu mô hình AOP hỗ trợ.
- **Pointcut:** biểu thức/quy tắc chọn những join point mong muốn.
- **Advice:** hành vi trước, sau, khi lỗi hoặc bao quanh một join point.
- **Aspect:** thành phần đóng gói pointcut và advice cho một mối quan tâm cắt ngang.
- **Weaving:** quá trình kết hợp hành vi aspect với chương trình để advice thực sự được áp dụng.

```text
Aspect / advice / pointcut       Class bytecode chưa dệt
             |                          |
             +------------+-------------+
                          |
                       Weaver
                          |
                          v
              Class bytecode sau dệt
                          |
                      JVM thực thi
                          |
                Advice + hành vi gốc
```

Điều kiện pointcut **đúng** chưa đủ để chứng minh advice sẽ chạy. Phải trả lời thêm: **loại join point được hỗ trợ không, class chứa điểm đó có nằm trong phạm vi biến đổi không, bytecode đã được biến đổi chưa, và JVM có đang dùng đúng class được dệt không?**

Một số AOP được thực hiện bằng **proxy/interceptor** tại ranh giới lời gọi thay vì sửa bytecode của class đích. Đó là cách can thiệp hợp lệ ở mức ý tưởng AOP, nhưng **không nên tự gọi nó là load-time weaving của method body**. Bài này đặt trọng tâm ở quá trình **biến đổi hoặc chuẩn bị bytecode khi class được nạp**, sau đó so sánh với proxy để tránh nhầm phạm vi.

## 2. Các thời điểm dệt: LTW nằm ở đâu?

| Thời điểm | Điều được xử lý | Ưu điểm điển hình | Ràng buộc chính |
| --- | --- | --- | --- |
| **Compile-time weaving** | Source/class trong lúc biên dịch | Có thể phát hiện nhiều lỗi lúc build | Build cần đúng compiler/toolchain và aspect |
| **Post-compile / binary weaving** | `.class` hoặc JAR đã được biên dịch | Không nhất thiết phải sửa source target | Artifact sau dệt phải được đóng gói và chạy thật |
| **Load-time weaving** | Class bytes khi runtime định nghĩa lớp | Có thể can thiệp theo tập class được nạp | Transformer phải được cài đúng lúc; phụ thuộc loader/module/JVM |
| **Runtime proxy/interceptor** | Lời gọi đi qua proxy/hook | Không nhất thiết đổi bytecode của target | Direct call, self-invocation hoặc phương thức ngoài hook có thể bỏ qua |

Bảng mô tả các nhóm cơ chế, **không bảo đảm mọi engine có đầy đủ khả năng tương đương**. Ví dụ, một LTW engine có thể hỗ trợ cả call lẫn execution join point, trong khi engine khác chỉ hỗ trợ một phần. Việc phương thức là `private`, `static`, `final`, synthetic hay nằm ở thư viện khác cũng phải xem theo giới hạn engine.

### Sơ đồ thời điểm

```text
Source code
    |
    +-- compile-time weaving --> .class đã dệt
    |
    +-- javac -----------------> .class gốc
                                  |
                                  +-- post-compile weaving --> .class đã dệt
                                  |
                                  +-- JVM / loader -----------+
                                                              |
                                                         LTW transform
                                                              |
                                                         define class
                                                              |
                                                           execution

Proxy/interceptor: bao quanh đường gọi ở runtime, không tự sửa .class gốc.
```

**Điểm khác biệt thiết yếu của LTW:** việc kết hợp advice xảy ra trên đường chuẩn bị bytecode để JVM **định nghĩa class**. Nó không có nghĩa mỗi lần method được gọi, bytecode lại được weave từ đầu.

## 3. “Nạp class” là một quá trình có nhiều giai đoạn

Trong JVM, nên phân biệt các khái niệm:

1. **Loading:** JVM tìm/thu nhận biểu diễn nhị phân và tạo lớp tương ứng; class loader tham gia quá trình này.
2. **Verification:** kiểm tra các ràng buộc của class file và bytecode.
3. **Preparation:** chuẩn bị các biến static theo quy tắc JVM.
4. **Resolution:** chuyển các symbolic reference thành tham chiếu runtime; thời điểm thực hiện từng resolution có thể khác nhau theo JVM và tình huống.
5. **Initialization:** thực thi các static initializer/class initialization logic khi điều kiện khởi tạo xảy ra.

Các bước liên kết và khởi tạo không nhất thiết xảy ra cùng lúc với câu lệnh `new` mà ta nhìn thấy trong source. Java có **nạp và resolution theo nhu cầu**, còn JVM được phép có những lựa chọn thời điểm hợp lệ theo đặc tả.

Với một transformer kiểu `ClassFileTransformer` của Java Instrumentation, việc can thiệp xảy ra trong đường tạo/định nghĩa class, **trước khi bytecode đã biến đổi được sử dụng như class runtime**. Do đó, một transformer cần trả bytecode **hợp lệ**, với cấu trúc và tham chiếu phù hợp để bước xác minh/liên kết sau đó có thể thành công.

### Loading khác initialization

Ví dụ:

```java
// Mã minh họa, không phải chương trình độc lập.
Class<?> type = Class.forName(
        "example.business.InvoiceService",
        false,
        loader
);
```

Tham số `false` của overload `Class.forName(name, initialize, loader)` yêu cầu **không khởi tạo class chỉ vì lời gọi này**, nhưng vẫn yêu cầu tìm/nạp class theo contract API. Lệnh này hữu ích khi muốn khảo sát “đã load” mà chưa chạy static initializer.

Ngược lại, `Class.forName("...")` thông thường sử dụng semantics khiến class được khởi tạo nếu cần. Dù vậy, **thời điểm định nghĩa class không luôn trùng thời điểm initializer chạy**; một advice vào static initialization join point (nếu engine có) không giống transformation callback khi class được định nghĩa.

### Transformer không phải advice invocation

- **Transformer:** chạy khi class được xử lý; có thể nhận bytes và trả bytes mới.
- **Advice:** chạy mỗi khi một join point đã được kết hợp xuất hiện, theo cơ chế được triển khai.
- **Method invocation:** có thể xảy ra rất nhiều lần sau khi class được nạp một lần.

Một class được transform **một lần** vẫn có thể thực thi method **một triệu lần**; advice được chèn vào method execution có thể chạy một triệu lần tùy pointcut/luồng.

## 4. Kiến trúc LTW tổng quát

Một hệ thống LTW dựa trên instrumentation thường có ba nhóm thành phần:

**(1) Runtime hook:** một agent hoặc khả năng tương đương đăng ký transformer để nhận các class bytes trên đường định nghĩa class.

**(2) Weaver:** phân tích class/method metadata, đối chiếu pointcut, chỉnh sửa bytecode để gọi advice hoặc tạo cấu trúc trung gian phù hợp.

**(3) Runtime support:** các type và hàm mà bytecode đã biến đổi cần gọi khi thực thi, kèm cấu hình, khởi tạo aspect, quản lý context và quan hệ class loader/module.

```text
ClassLoader.loadClass(...)
          |
          v
  Tìm bytes của lớp
          |
          v
  Transformer được gọi
          |
          +-- Không thuộc phạm vi -> giữ nguyên bytes
          |
          +-- Có join point hợp lệ
                      |
                   Weaver
                      |
              Bytecode đã dệt
                      |
                  defineClass
                      |
              JVM verify / link
                      |
              Class có thể chạy
                      |
          Advice được gọi khi join point xảy ra
```

Đây là **sơ đồ nguyên lý**. Trật tự chi tiết, cách nhiều transformer được áp dụng và khả năng biến đổi class đã nạp phụ thuộc JVM/API instrumentation và công cụ weaving cụ thể.

### Phạm vi chọn class và phạm vi match pointcut

Một LTW engine thường cần hai lớp lọc khác nhau:

- **Class filter:** những class/package/module/loader nào được phép đi qua chi phí phân tích/dệt?
- **Join-point matcher:** trong class ấy, call site hoặc method execution nào thỏa pointcut?

Nếu class bị loại ngay ở filter, pointcut bên trong nó không được xét. Ngược lại, transformer có thể quan sát một class nhưng không tìm được join point phù hợp; trường hợp đó **không đồng nghĩa dệt thất bại**.

## 5. Java Instrumentation và `ClassFileTransformer`

Java SE cung cấp API `java.lang.instrument` để tạo agent và đăng ký transformer. Đây là **cơ chế nền tảng** cho một số giải pháp instrumentation/LTW trên JVM, không phải một ngôn ngữ AOP hoàn chỉnh.

Một agent khởi động cùng JVM có thể khai báo phương thức `premain`. Khi JVM chạy với tùy chọn `-javaagent:path/to/agent.jar`, agent được khởi tạo trước khi gọi ứng dụng `main` theo contract của Java Instrumentation.

Một transformer có thể nhận:

- `ClassLoader loader`: loader định nghĩa class, có thể `null` với bootstrap loader.
- `String className`: tên nội bộ kiểu `com/example/Service`, có thể có trường hợp đặc biệt theo API.
- `Class<?> classBeingRedefined`: thường `null` khi class **được load lần đầu**; có giá trị tương ứng khi redefinition/retransformation.
- `ProtectionDomain protectionDomain`: thông tin domain bảo vệ theo runtime.
- `byte[] classfileBuffer`: biểu diễn class file ban đầu hoặc đã được các transformer trước xử lý.
- Ở API hỗ trợ module: `Module module` cung cấp thông tin module liên quan tới class.

Một transformer thường **trả `null` để không thay đổi bytes**, hoặc trả **mảng byte mới** hợp lệ nếu nó thực hiện biến đổi. Việc in log trong transform là **quan sát quá trình load**, không phải dệt advice vào method.

### Ví dụ sơ đồ transformer thật

```java
// Pseudocode: weaveMethods không phải API có sẵn của Java SE.
byte[] transformClass(
        ClassLoader loader,
        String internalClassName,
        byte[] originalBytes) {

    if (!isAllowedByWeavingScope(loader, internalClassName)) {
        return null; // Không biến đổi.
    }

    return weaveMethods(originalBytes, configuredPointcuts);
}
```

Mã này mô tả trách nhiệm, **không phải chương trình Java chạy độc lập**. Để biến đổi bytecode an toàn, một engine cần giải quyết instruction offsets, stack map frames, constant pool, exception tables, verifier constraints và các tham chiếu runtime. Không nên chỉnh bytecode tùy ý theo chuỗi byte mà không hiểu class-file format.

## 6. Ví dụ Java 17+ chạy được: quan sát class lúc được nạp

Ví dụ này có một **agent** và một **ứng dụng**. Agent đăng ký `ClassFileTransformer` để phát hiện đúng lúc class `demo.app.Worker` được định nghĩa. Transformer **không sửa bytecode**: nó trả `null`.

**Tại sao dùng ví dụ “quan sát” thay vì giả vờ đã weave advice?** Java SE cung cấp hook instrumentation nhưng **không cung cấp sẵn một DSL pointcut hay một bộ dệt phương thức đầy đủ**. Ví dụ tập trung vào việc xác minh **thời điểm và phạm vi hook LTW**. Bước kế tiếp trong một engine AOP thật là dùng một bytecode weaver hợp lệ tại hook đó để chèn advice, được giải thích ở những mục sau.

### 6.1. Cấu trúc thư mục

```text
demo/
  src/
    demo/
      agent/
        LoadProbeAgent.java
      app/
        Main.java
        Worker.java
  agent.mf
```

### 6.2. `src/demo/agent/LoadProbeAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class LoadProbeAgent {
    private LoadProbeAgent() { }

    public static void premain(String options, Instrumentation instrumentation) {
        System.out.println("agent.premain");
        instrumentation.addTransformer(new Probe(), false);
    }

    static final class Probe implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String internalName,
                                Class<?> classBeingRedefined,
                                ProtectionDomain protectionDomain,
                                byte[] classfileBuffer) {
            if ("demo/app/Worker".equals(internalName)) {
                System.out.println("agent.transform demo/app/Worker");
            }
            return null; // Quan sát, không sửa bytecode.
        }
    }
}
```

`premain` chạy khi agent được kích hoạt tại JVM startup. `addTransformer(new Probe(), false)` đăng ký transformer với ý định chỉ quan sát đường load và **không khai báo transformer này hỗ trợ retransform**. Tham số `false` **không có nghĩa** toàn bộ JVM không hỗ trợ retransformation; nó chỉ cho biết transformer được đăng ký ở chế độ không hỗ trợ việc gọi lại kiểu đó theo API.

Matcher `"demo/app/Worker"` sử dụng **internal class name có dấu `/`**, khác với tên fully qualified dùng trong `Class.forName` là `"demo.app.Worker"`.

### 6.3. `src/demo/app/Main.java`

```java
package demo.app;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("app.main");

        Class<?> workerType = Class.forName("demo.app.Worker");
        Object worker = workerType.getConstructor().newInstance();
        workerType.getMethod("execute").invoke(worker);

        System.out.println("app.done");
    }
}
```

Ứng dụng cố ý dùng `Class.forName` **sau khi đã in `app.main`** để buộc yêu cầu nạp `Worker` tại một vị trí rõ ràng, tránh phụ thuộc vào việc JVM chủ động resolve một class được tham chiếu trực tiếp trong bytecode của `Main` vào lúc nào.

### 6.4. `src/demo/app/Worker.java`

```java
package demo.app;

public final class Worker {
    public Worker() { }

    public void execute() {
        System.out.println("worker.execute");
    }
}
```

### 6.5. `agent.mf`

```text
Premain-Class: demo.agent.LoadProbeAgent
```

Tệp manifest cần có một dòng kết thúc hợp lệ. Công cụ `jar` sẽ kết hợp nội dung manifest được cung cấp với metadata JAR cần thiết. `Premain-Class` là entry point cho agent được tải khi khởi động, **không phải Main-Class của ứng dụng**.

### 6.6. Biên dịch, tạo agent JAR và chạy

Tại thư mục `demo` chứa `src`, dùng các lệnh sau (chạy lần lượt):

```bash
mkdir -p classes
javac --release 17 -d classes \
  src/demo/agent/LoadProbeAgent.java \
  src/demo/app/Main.java \
  src/demo/app/Worker.java

jar --create --file load-probe-agent.jar \
  --manifest agent.mf -C classes demo/agent

java -cp classes demo.app.Main

java -javaagent:load-probe-agent.jar -cp classes demo.app.Main
```

Khối lệnh trên dùng cú pháp shell có ký tự nối dòng `\`, phù hợp môi trường Unix-like shell. Trên Windows PowerShell, có thể gõ mỗi lệnh trên một dòng để tránh khác biệt ký tự nối dòng; tùy chọn `javac`/`jar`/`java` vẫn giữ nguyên.

**Đầu ra khi chạy KHÔNG có agent:**

```text
app.main
worker.execute
app.done
```

**Đầu ra khi chạy CÓ agent:**

```text
agent.premain
app.main
agent.transform demo/app/Worker
worker.execute
app.done
```

Ví dụ đã được biên dịch với `javac --release 17` và chạy bằng JDK tương thích để đối chiếu hai đầu ra. Mã không yêu cầu thư viện AOP bên ngoài.

### 6.7. Đọc đúng ý nghĩa kết quả

1. `agent.premain` xuất hiện trước `app.main`: agent startup đã được kích hoạt.
2. `app.main` in trước khi gọi `Class.forName("demo.app.Worker")`.
3. Transformer thấy bytes của `demo/app/Worker` trên đường load, in `agent.transform ...`.
4. Transformer trả `null` nên **class vẫn dùng bytes không đổi**.
5. `worker.execute` chạy và chỉ in `worker.execute`; không có advice nào được chèn.
6. Khi không dùng `-javaagent`, `premain` và transformer không được đăng ký, nên không có log của agent.

**Quan trọng:** Dòng `agent.transform` chứng minh transformer **được gọi**, **không chứng minh weaving đã xảy ra**. Một bài kiểm thử weaving thật phải xác nhận mã đã biến đổi và advice thực sự chạy tại join point mong muốn.

### 6.8. Nếu muốn từ “quan sát” tiến tới “weaving” thật

Một weaver có thể thay nhánh:

```java
return null;
```

bằng logic sinh ra **bytecode hợp lệ có thêm lời gọi tới advice**, sau đó trả `byte[]` mới. Chẳng hạn về ý tưởng, thân `execute` có thể được biến đổi thành:

```java
// Pseudocode kết quả mong muốn, không phải mã mà demo agent tự sinh.
void execute() {
    TraceAdvice.before("demo.app.Worker.execute");
    try {
        originalExecuteBody();
    } finally {
        TraceAdvice.after("demo.app.Worker.execute");
    }
}
```

Một bytecode weaver thực tế phải bảo tồn semantics Java, return values, exception flow, verifier rules và đường gọi advice. Nó không thể đơn giản gọi `originalExecuteBody()` nếu method đó không tồn tại; engine phải tạo wrapper/di chuyển/chỉnh sửa instruction flow một cách hợp lệ. Sơ đồ chỉ nhằm giải thích **hiệu ứng cần đạt**, không phải khẳng định agent demo đã thực hiện nó.

## 7. Vì sao cần gắn transformer trước khi class đích được định nghĩa?

Giả sử:

```text
t0  JVM start
t1  Load class A
t2  Agent/transformer được đăng ký
t3  Load class B
t4  A.execute()
t5  B.execute()
```

Nếu A đã được định nghĩa ở `t1` mà transformer mới được đăng ký ở `t2`, **load-time callback thông thường không tự chạy lại cho A**. B được định nghĩa sau `t2` có thể đi qua transformer.

Từ đó:

- Một startup agent thường phải được cung cấp bằng `-javaagent` để được khởi tạo đủ sớm cho các class ứng dụng cần dệt.
- Cấu hình weaving có thể được nạp sớm, trước khi nhiều class mục tiêu được định nghĩa.
- Một đoạn code gọi class mục tiêu khi khởi tạo agent có thể **vô tình nạp target trước khi transformer sẵn sàng**.
- Class được load theo nhu cầu nên cần test ở cả startup path và những đường load muộn.
- Nếu class đã nạp, việc đổi file JAR hoặc đăng ký transformer mới **không tự biến đổi Class object đang sống**.

### Nạp quá sớm trong chính agent

Giả sử agent khởi tạo một helper, helper tham chiếu trực tiếp target business class, và JVM phải load target để giải quyết dependency. Nếu điều này xảy ra **trước `addTransformer`**, cơ hội dệt lần load đầu của class đó có thể đã mất.

Một phương án thiết kế là giữ logic `premain` tối giản:

1. Đọc cấu hình tối thiểu mà không chủ động chạm target.
2. Đăng ký transformer phù hợp.
3. Hoãn khởi tạo những helper có dependency rộng nếu việc ấy có nguy cơ load target.
4. Kiểm tra class thực tế được load sau khi transformer đã sẵn sàng.

Không phải mọi load muộn đều có vấn đề; vấn đề là **thứ tự tương đối giữa thời điểm định nghĩa class và thời điểm hook có hiệu lực**.

## 8. Đã nạp rồi thì sao: retransformation khác LTW thông thường

Java Instrumentation có khả năng liên quan đến:

- `Instrumentation.isRetransformClassesSupported()`: runtime có hỗ trợ cơ chế retransformation không.
- `Instrumentation.addTransformer(transformer, true)`: đăng ký transformer có khả năng tham gia retransformation khi được hỗ trợ.
- `Instrumentation.retransformClasses(...)`: yêu cầu xử lý lại một số class đã nạp, nếu được hỗ trợ và class phù hợp.
- `Instrumentation.isModifiableClass(...)`: kiểm tra một class có thể được biến đổi theo API tương ứng không.
- `Instrumentation.redefineClasses(...)`: cơ chế redefinition khác có tập ràng buộc riêng.

**Retransformation không phải “lần nạp class mới”.** Class object và các instance hiện có không đơn giản bị thay bằng một class vừa được define. JVM áp đặt các giới hạn thay đổi cấu trúc trong quá trình redefinition/retransformation; tùy API/JVM, không thể giả định được thêm/xóa method, field, thay class hierarchy hoặc đổi signature tùy ý.

### Hai phương án cần phân biệt

**Dệt lúc load lần đầu:** transformer tạo bytes phù hợp trước `defineClass`, khi class chưa được sử dụng như type runtime. Đây là load-time weaving theo nghĩa trực tiếp.

**Biến đổi class đã load:** dùng API bổ sung nếu môi trường hỗ trợ; cần kiểm tra modifiability và structural restrictions. Nó không phải một chiến lược đáng tin nếu ứng dụng tùy ý muốn đổi mọi đặc điểm của class giữa lúc đang chạy.

Nếu mục tiêu yêu cầu một cấu trúc bytecode không thể bổ sung sau load, hãy thiết kế agent và weaver để can thiệp **trước định nghĩa class**, hoặc dùng một ranh giới interception khác được hỗ trợ.

## 9. Class loader quyết định class được định nghĩa ở đâu

Một **class loader** tham gia việc tìm và định nghĩa lớp. Trong nhiều ứng dụng JVM có:

- **Bootstrap loader** cho các class nền tảng.
- **Platform loader** cho một tập module nền tảng.
- **Application/system loader** cho mã ứng dụng thông thường.
- **Custom loaders** dùng trong plugin architecture, container hoặc khi cần cô lập phiên bản thư viện.

Không nên mặc định mọi custom loader đều theo một chính sách parent-first giống nhau; điều quan trọng là **lớp đích được định nghĩa bởi loader nào** và transformer/runtime support có quan sát/truy cập được đường load đó không.

### Class identity: tên không đủ

Trong JVM, class có thể được phân biệt theo **tên nhị phân và defining class loader**. Hai class có tên `example.Service` nhưng do hai loader khác nhau định nghĩa có thể là **hai runtime types khác nhau**.

```text
PluginLoader A --defines--> example.Service  [Type A]
PluginLoader B --defines--> example.Service  [Type B]

Tên binary giống nhau, nhưng type identity không nhất thiết giống nhau.
```

Điều đó ảnh hưởng:

- Type matching của pointcut khi class cùng tên xuất hiện ở loader khác.
- Cache metadata theo `Class<?>` hoặc key class name.
- Các cast/reflection callback giữa advice và target.
- Khả năng nạp helper/advice class mà bytes đã dệt sẽ tham chiếu.
- Quy trình reload plugin: loader mới có thể tạo một thế hệ class khác.

### Class loader filter và pointcut filter

Một engine có thể cho phép chỉ weave class do loader cụ thể định nghĩa. Nhờ đó, nó tránh dệt nhầm thư viện framework/runtime hoặc plugin không thuộc chính sách. Nhưng nếu loader filter quá hẹp, target hợp lệ có thể không được instrument.

Đặt điều kiện chỉ theo **class name** cũng chưa chắc đủ khi nhiều loader có class trùng tên; thêm thông tin loader/module/artifact nếu công cụ hỗ trợ và yêu cầu có giá trị.

## 10. Vì sao bytecode đã dệt phải truy cập được advice runtime?

Giả sử weaver chèn vào `app.Service` một instruction tương đương:

```java
TraceRuntime.before("Service.run");
```

Khi JVM xác minh/liên kết/thực thi class đã dệt, nó phải giải quyết tham chiếu tới `TraceRuntime` theo quy tắc nạp lớp và truy cập phù hợp.

Một transformer có thể **nhìn thấy class bytes** nhưng bytecode nó tạo ra lại **không nạp hoặc gọi được advice runtime**. Kết quả có thể là lỗi liên kết/lỗi truy cập hoặc hành vi không mong đợi.

Vì thế phải bảo đảm:

1. Helper/advice class ở đường nạp phù hợp cho target loader.
2. Các type mà helper cần dùng có thể được resolve theo module graph.
3. Mã đã dệt không tham chiếu trái phép tới package/member không được truy cập.
4. Cơ chế khởi tạo helper không tạo vòng nạp hoặc recursion vào cùng transformer.
5. Nếu hỗ trợ nhiều class loader, mỗi loader có thể có **phiên bản helper riêng** hoặc phải chia sẻ một bản được thiết kế cẩn thận.

### Bootstrap classes là trường hợp đặc biệt

Không nên suy luận rằng một agent quan sát được application classes sẽ tự instrument an toàn mọi class lõi do bootstrap loader quản lý. Việc dệt các class nền tảng có thể làm vòng nạp phụ thuộc, thay đổi hiệu năng quan trọng, hoặc chạm tới giới hạn bảo mật/runtime. Các agent có thể cần cung cấp helper qua bootstrap search path hay chiến lược đặc biệt, nhưng đó là bài toán nâng cao phải kiểm thử rất kỹ.

**Giải pháp mặc định nên là phạm vi hẹp đúng nhu cầu**, không phải biến đổi toàn bộ JDK.

## 11. Class loading và JPMS: hai khái niệm liên quan nhưng khác nhau

**Java Platform Module System (JPMS)** là cơ chế tổ chức named modules. Một module có `module-info.java` khai báo quan hệ như:

```java
module com.example.business {
    exports com.example.business.api;
}
```

Một module sử dụng nó:

```java
module com.example.app {
    requires com.example.business;
}
```

Các khái niệm quan trọng:

- **Readability:** module nào được quyền đọc module nào.
- **Exports:** package public API nào cho phép truy cập biên dịch/runtime theo quy tắc JPMS.
- **Opens:** package nào cho phép deep reflective access ở runtime đối với module được chỉ định hoặc rộng hơn.
- **Module layer:** tập module đã resolve trong một cấu trúc runtime, có thể có nhiều layer.
- **Class loader:** cơ chế định nghĩa class; nhiều module có thể được định nghĩa bởi một loader, và một ứng dụng có thể dùng nhiều loader/layer.

**JPMS không phải weaver.** `requires` hoặc `exports` không tự gắn advice vào method. Chúng ảnh hưởng khả năng **code đã dệt** hoặc **helper phản chiếu** truy cập các type/member cần thiết.

### `exports` và `opens` không tương đương

| JPMS declaration | Mục đích chính | Không bảo đảm |
| --- | --- | --- |
| `requires other.module;` | Khai báo dependency/readability | Cho phép truy cập mọi package private trong module kia |
| `exports p;` | Công khai public API package `p` cho các module đọc được | Deep reflection tùy ý lên private member |
| `exports p to x;` | Export public API chỉ cho những module được nêu | Quyền của mọi module khác |
| `opens p;` | Cho phép reflective access sâu với package `p` ở runtime | Compile-time access tương đương `exports` |
| `opens p to x;` | Cho phép reflective access sâu có chọn lọc | Tự động dệt code trong package `p` |

Một agent hoặc weaver chỉ cần đọc **bytes** của class có thể có nhu cầu quyền khác với advice runtime sử dụng **Reflection** để gọi private method. Cần xác định lỗi thực tế thuộc **bytecode transformation**, **module readability**, **Java access control** hay **Reflection access**, thay vì tùy tiện mở mọi package.

## 12. Java 9+ cung cấp thông tin Module cho transformer

Trong Java Instrumentation hiện đại có phiên bản `transform` bổ sung tham số `Module`. Điều này hữu ích khi nhiều named module chứa các class có tên/package tương tự hoặc cần chọn phạm vi theo module.

Ví dụ **đoạn code minh họa thay thế hàm `transform` trong một transformer**, không phải file Java độc lập:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String internalName,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {

    if ("demo/app/Worker".equals(internalName)) {
        String moduleName = module != null && module.isNamed()
                ? module.getName()
                : "<unnamed>";
        System.out.println("module=" + moduleName);
    }

    return null;
}
```

Khi triển khai cụ thể, cần đảm bảo transformer tương thích với version Java mục tiêu và cách override API. `Module.getName()` trả `null` cho unnamed module; kiểm tra `isNamed()` giúp đặt nhãn có ý nghĩa.

### Module name chưa phải điều kiện pointcut đủ

Một class trong module `com.example.business` chưa chắc chứa join point phù hợp. Vẫn cần kết hợp:

- Module/loader/class filter.
- Type/method metadata.
- Loại join point (call hay execution).
- Điều kiện pointcut.
- Cấu hình runtime, nếu có.

Nếu chỉ log `moduleName` trong transform, bạn chỉ biết module nào đang được định nghĩa class, **chưa biết advice có được dệt vào từng method hay chưa**.

## 13. `Instrumentation.redefineModule` và quyền truy cập

Java Instrumentation cung cấp API để điều chỉnh một số quan hệ module đã nạp, chẳng hạn **bổ sung read edges, exports hoặc opens** cho các mục đích phù hợp trong runtime instrumentation.

Nhưng cần hết sức thận trọng:

- Không dùng API này như lời giải chung cho mọi lỗi weaving.
- Chỉ thêm quan hệ/module access thật sự cần cho code đã biến đổi hoặc helper.
- Không mặc định một lần sửa module graph tạo được khả năng instrument những class đã load trước đó.
- Thay module access không tự biến một method thành join point được dệt.
- Một bộ công cụ có thể cần xử lý lại class hoặc lập kế hoạch transformer riêng.

Ví dụ, nếu bytecode đã dệt trong module business tham chiếu `TraceRuntime` ở module agent, phải đảm bảo JVM có thể resolve và truy cập tham chiếu đó theo module graph. Nếu một reflection helper gọi private method, có thể phát sinh thêm nhu cầu opens. **Thêm reads không thay thế opens**, và opens không tự thêm mọi điều kiện matching hoặc weaving.

## 14. Named module và unnamed module

Class chạy trên **classpath** thường thuộc **unnamed module** của class loader tương ứng. Class chạy trên **module path** có thể thuộc **named module** được resolve.

Một agent được cấp bằng JAR không có module descriptor có thể chạy theo cơ chế module/classloader của Java agent, trong khi target lại thuộc named module. Điều này tạo ra những câu hỏi mà một ứng dụng classpath nhỏ không có:

- Target module có đọc được module chứa advice helper không?
- Helper package có cần được export tới target module không?
- Target có gọi được public/static entry point mà weaver chèn vào không?
- Annotation resolver có deep reflection vào package target không?
- Runtime agent có cách chuẩn để điều chỉnh module graph khi cần không?
- Class được nạp bởi loader của module layer nào?

Đừng chuyển một ứng dụng sang module path rồi suy luận **agent nhất định ngừng chạy**; cũng đừng cho rằng **agent chắc chắn có đủ quyền cho mọi reference đã dệt**. Phải kiểm chứng đúng mô hình runtime.

### Module layer và plugin động

Một ứng dụng có thể tạo module layer riêng để nạp plugin sau khi `main` đã bắt đầu. Nếu transformer vẫn được đăng ký và đường class-definition tương ứng được runtime instrumentation quan sát, các class được định nghĩa sau đó **có thể** được xử lý. Nhưng cần lưu ý:

- Class loader của layer mới có thể khác.
- Module graph/readability riêng.
- Cùng tên class ở layer/loader khác có thể là type khác.
- Helper mà class đã dệt gọi cần khả dụng trong layer/loader thích hợp.
- Cache matcher theo class name có thể sai khi plugin reload.

**Không coi module được resolve là mọi class của module đã được load.** JPMS resolve module graph và loading từng class là hai cấp khác nhau.

## 15. Phân biệt quan hệ Java module với quan hệ build module

“Dệt khi nạp module B” có thể bị hiểu nhầm là JVM định nghĩa toàn bộ class của B cùng lúc. Với JPMS, một named module có thể được resolve từ đầu nhưng **từng class vẫn được nạp khi cần**. Transformer làm việc với **class bytes**, không có bước mặc định “transform toàn bộ module một lần” chỉ vì module xuất hiện trong graph.

```text
Module graph đã resolve:
  app ---> business ---> storage

Class loading theo nhu cầu:
  app.Main
  business.OrderService
  storage.ConnectionFactory
  business.Helper
  ...
```

Một LTW engine có thể **lọc theo module** nhưng vẫn nhận callback cho **từng class** khi class được định nghĩa. Điều này khác **post-compile weaving** nơi một tool có thể mở cả JAR chứa nhiều class trước khi chạy chương trình.

### Nếu một module không được sử dụng

Nếu class của module B không bao giờ được nạp, transformer có thể không nhìn thấy những class đó. Điều đó không nhất thiết là lỗi: **không có class-definition event thì không có điểm để LTW xử lý class ấy**.

Một test chỉ kiểm tra startup path có thể bỏ sót class chỉ xuất hiện khi chạy tính năng ít dùng. Cần test cả những đường load muộn nếu coverage quan trọng.

## 16. Method call và method execution: loader của bên nào quan trọng?

Giả sử module `checkout` gọi method `invoice.create()` của module `billing`:

```text
Module checkout                      Module billing
  Checkout.submit()
        |
        +----- call site -----------> InvoiceService.create()
                                            |
                                         execution
```

Nếu pointcut chọn **method call join point** phát sinh từ `Checkout.submit`, bytecode cần dệt thường là **caller class trong checkout**, vì đó là nơi chứa instruction phát lời gọi.

Nếu pointcut chọn **method execution join point** của `InvoiceService.create`, bytecode cần dệt thường là **callee class trong billing**, vì đó là nơi chứa method body.

Với LTW:

- Transformer quan sát checkout class khi nó được nạp thì có thể instrument call site checkout nếu engine hỗ trợ call join point.
- Transformer quan sát billing class khi nó được nạp thì có thể instrument method execution billing nếu engine hỗ trợ execution join point.
- Chỉ nhìn thấy class của một phía **không tự instrument mọi điểm thuộc phía kia**.
- Việc aspect được định nghĩa trong module thứ ba `observability` **không quyết định** nơi bytecode phải được chỉnh.

### Quan sát ở caller chưa chắc tương đương execution ở callee

Một call site có thể được gọi nhiều lần nhưng không dẫn tới target execution vì lời gọi bị chặn hoặc argument evaluation ném lỗi trước khi vào method body. Ngược lại, một target execution có thể được gọi từ nhiều caller và có self-invocation. **Hai loại điểm có thể quan sát tập sự kiện khác nhau**, nên metric và coverage cần xác định ranh giới từ đầu.

## 17. Điểm khác giữa LTW và proxy đối với self-invocation

Xét:

```java
// Đoạn khai báo minh họa.
class PaymentService {
    void run() {
        validate(); // gọi nội bộ trên this
    }

    private void validate() { }
}
```

Một **proxy bên ngoài target** có thể intercept `proxy.run()`, nhưng lời gọi `this.validate()` bên trong target không quay ra proxy. Nếu `validate` là private, proxy dựa trên override/interface cũng không thể intercept trực tiếp như một public method.

Nếu **bytecode của `PaymentService` được weave** tại execution `validate` hoặc call site trong `run` và engine hỗ trợ loại điểm ấy, nó có thể áp dụng advice cho lời gọi nội bộ. Nhưng điều kiện đó **không tự có chỉ vì đã bật agent**:

1. Class phải nằm trong weaving scope.
2. Transformer phải áp dụng đúng lúc và tạo bytes hợp lệ.
3. Pointcut phải khớp join point.
4. Engine phải hỗ trợ can thiệp ở private method/call site tương ứng.
5. JVM phải dùng bản class đã được dệt.

Do đó **LTW có thể giải quyết những lỗ coverage của proxy trong một số mô hình**, nhưng không nên phát biểu “LTW luôn bắt mọi self-invocation” nếu chưa xác minh công cụ.

## 18. Nhiều transformer và thứ tự biến đổi

Một JVM có thể có **nhiều java agents** hoặc nhiều `ClassFileTransformer` được đăng ký. Mỗi transformer có thể quan sát class bytes ở một giai đoạn phù hợp của chuỗi transformation.

Điều này tạo ra các câu hỏi:

- Transformer A nhận bytes gốc hay bytes đã qua B?
- Hai transformer có cùng sửa một method không?
- Một transformer có thể làm mất thông tin mà transformer sau cần để match pointcut không?
- Có một transformer tạo bytecode mà JVM không verify được không?
- Nếu cả hai chèn advice vào cùng method, thứ tự advice thực tế thế nào?
- Một class có thể bị weave hai lần do agent hoặc bước build khác không?

Java Instrumentation có các quy tắc cụ thể về thứ tự transformer dựa trên việc đăng ký và khả năng retransformation; cần xem contract API và cấu hình triển khai. Không nên dựa vào một thứ tự tùy ý trừ khi runtime/tool cam kết.

### Dệt trùng và reentrancy

Nếu method `save` bị dệt hai lần, một advice ghi audit có thể chạy hai lần cho một execution. Nếu advice tự gọi code cũng thỏa pointcut, có thể xảy ra recursion. Giải pháp thường liên quan **matching scope**, nhận diện bytecode đã dệt, loại trừ lớp runtime support hoặc thiết kế idempotency phù hợp, **không phải chỉ xóa log thừa**.

Đừng áp đặt một transformer “bao tất cả” mà không tính tới các transformer quan sát, profiler và công cụ instrumentation cùng chạy.

## 19. Bytecode hợp lệ: giới hạn của class transformation

Dệt advice không chỉ là “chèn một dòng Java” vào file class. Engine phải tạo ra cấu trúc class file đúng:

- Constant pool entries và symbolic references hợp lệ.
- Method descriptors và access flags phù hợp.
- Control-flow graph vẫn có nhánh/return/throw đúng.
- Exception handlers và `finally` tương đương phải bảo toàn semantics.
- Stack map frames, operand stack và local variables phải hợp lệ.
- Bytecode version phù hợp với JDK runtime.
- Không phá invariant của constructor/class initialization.
- Các type helper được resolve theo class loader/module access.
- Không làm sai đồng bộ hóa, exception propagation hay giá trị trả về.

Một lỗi ở một điểm có thể khiến class không load được với `VerifyError`, `ClassFormatError`, `NoClassDefFoundError`, `IllegalAccessError` hoặc lỗi liên kết khác tùy nguyên nhân. **Không phải lỗi nào trong nhóm này cũng bắt nguồn từ pointcut sai**.

### Lỗi ở lớp nào thì sửa lớp ấy

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra |
| --- | --- |
| `premain` không in gì | Agent không được nạp, manifest/đường dẫn sai hoặc startup lỗi |
| Có `premain` nhưng không có transform target | Class chưa load, load quá sớm, filter loại, module/loader khác |
| Có transform nhưng không có advice | Transformer chỉ quan sát, pointcut không khớp, bytes trả `null`, hoặc engine bỏ qua method |
| Class load thất bại sau transform | Bytecode không hợp lệ, helper không resolve, quyền truy cập |
| Advice chỉ chạy trên một số đường gọi | Call vs execution, proxy bypass, variant implementation/loader |
| Advice chạy trùng | Dệt nhiều lượt, nhiều aspect, retry/proceed hoặc matcher quá rộng |
| Advice thấy context sai trên worker | Context propagation/scope, không nhất thiết do load-time weaving |

**Đầu tiên cần phân biệt “transform callback được gọi” với “bytes thực sự thay đổi” và “advice chạy tại join point”.**

## 20. Khởi tạo class và side effect do instrumentation

Khi transformer và helper được load, chúng có thể kích hoạt thêm các class khác. Nếu helper lại tham chiếu những class đang thuộc weaving scope, có thể gây chuỗi nạp phức tạp, recursion hoặc thứ tự khởi tạo khó đoán.

Nên giữ:

- Code bootstrap của agent tối giản.
- Transformer lọc sớm theo class name/package/module.
- Helper của weaver tách rõ khỏi đối tượng nghiệp vụ.
- Logging trong transformer đơn giản, tránh phụ thuộc vào chính code đang được weave.
- Không làm network I/O hoặc blocking nặng trên đường nạp class nếu không thật sự cần.
- Tính tới khả năng nhiều thread có thể yêu cầu nạp class và callback xảy ra ở các thread khác nhau.

Một aspect runtime có thể cần instance state, nhưng **khởi tạo aspect** và **biến đổi class** là các vòng đời khác nhau. Không nên suy từ việc transformer đã chạy rằng instance aspect đã được tạo và sẵn sàng cho mọi lời gọi.

## 21. Cache khi module hoặc class loader thay đổi

Một weaver có thể cache kết quả phân tích:

```text
(classLoader, className, module, configVersion) -> weave decision
```

Đây chỉ là **thiết kế key khái niệm**. Mức cache thực tế còn phụ thuộc bytecode digest, class version, pointcut set và các trạng thái nội bộ.

Nếu chỉ cache theo `className`, hai plugin loader cùng có `com.example.Service` nhưng khác bytes có thể bị dùng nhầm quyết định. Nếu cache giữ reference mạnh tới `ClassLoader` trong hệ thống plugin có unload/reload, nó có thể gây rò bộ nhớ.

Cần xem xét:

- Identity của loader, không chỉ tên.
- Module layer/version.
- Hash/fingerprint của bytes nếu nhiều biến thể cùng tên.
- Phiên bản pointcut và cấu hình.
- Chính sách invalidation khi plugin unload/reload.
- Giữ cache phù hợp với vòng đời loader.

**Một class loader có thể không được thu gom nếu vẫn có reference mạnh không cần thiết từ cache toàn cục**. Công cụ instrumentation có thể có chiến lược cache riêng; không bắt buộc mọi ứng dụng phải tự triển khai.

## 22. Cấu hình LTW có thể thay đổi sau startup không?

Có thể thay đổi cấu hình của một engine đang chạy, nhưng cần phân biệt:

**Quy tắc cho class sẽ load về sau:** nếu transformer đọc cấu hình mới lúc được gọi, class load sau đó có thể nhận cách biến đổi mới.

**Những class đã được định nghĩa:** không tự đổi chỉ vì pointcut được cập nhật. Muốn can thiệp vào chúng, engine cần cơ chế phù hợp (retransformation/redefinition, proxy reconfiguration hoặc restart/redeploy).

**Advice runtime:** một class đã dệt có thể gọi helper đọc cấu hình runtime động ở mỗi invocation. Khi đó **hành vi advice** có thể đổi mà **bytecode không đổi**, nhưng việc thêm một join point trước đây chưa được instrument không tự xảy ra.

Vì vậy có ba kiểu cập nhật khác nhau:

1. **Đổi điều kiện runtime** mà bytecode đã có sẵn khả năng kiểm tra.
2. **Đổi phạm vi weaving cho class sắp nạp**.
3. **Đổi bytecode của class đã nạp** bằng cơ chế động được phép.

Không gom cả ba thành một câu “LTW có hot reload”.

## 23. Phiên bản Java, module và agent compatibility

Một LTW engine có thể tạo bytecode không phù hợp JDK mục tiêu, hoặc dùng API/feature không tồn tại ở runtime cũ. Với Java 17+:

- Class file version phải được runtime hỗ trợ.
- Agent JAR manifest và `premain` phải hợp lệ.
- API `Instrumentation` có thể có khả năng optional; phải kiểm tra support thay vì chỉ gọi.
- Runtime module graph phải cho phép các reference/helper đã được weave.
- Class loader có thể khác giữa unit test và deployment.
- Build tool có thể chạy test bằng một JVM có `-javaagent` nhưng production không có, hoặc ngược lại.

Ví dụ demo đã biên dịch với `--release 17` để tránh phụ thuộc vào API mới hơn 17. Đối với bytecode weaver thực tế, cũng cần kiểm tra nó **hỗ trợ class files của JDK đang chạy** và không làm hỏng những class có đặc điểm compiler mới.

### Dynamic agent attachment không đồng nghĩa startup LTW

Một số Java runtime/công cụ cho phép agent được gắn vào JVM đang chạy và gọi entry point kiểu `agentmain`, nếu việc attach được hỗ trợ/cho phép. Khi ấy nhiều class mục tiêu có thể **đã được định nghĩa**. Phải xác định ranh giới hỗ trợ retransform/redefine; không suy luận dynamic attach có toàn bộ quyền của một startup agent trước class loading.

Các chính sách attach và cảnh báo JVM có thể thay đổi theo phiên bản và môi trường. Với một quy trình cần coverage tin cậy, thường phải **kiểm thử chính xác cách agent được triển khai ở môi trường chạy**.

## 24. AOP theo module: chọn nơi dệt theo join point

Một ứng dụng nhiều module:

```text
module checkout
    CheckoutFlow.submit()  ---- call ---->
module billing
    InvoiceService.create() ---- execution
module tracing
    TraceAdvice
```

Với **execution pointcut** của `InvoiceService.create`, transformer cần xử lý **class định nghĩa execution ở billing** nếu muốn bytecode weaving tại method này.

Với **call pointcut** phát ra từ `CheckoutFlow.submit`, transformer cần xử lý **class caller ở checkout**.

Với một proxy API ở checkout, code tracing có thể intercept lời gọi đi qua proxy mà không sửa bytecode billing; nhưng đường gọi khác vào billing có thể bypass.

Điều quan trọng không phải advice nằm ở module nào, mà là **join point được đặt ở đâu trong bytecode/đường gọi**, và module chứa điểm ấy có được runtime instrumentation quan sát không.

### Module được resolve nhưng class chưa load

Một module `billing` có thể đã được resolve trên module path. `InvoiceService` của nó chưa chắc đã được nạp. Khi class được sử dụng lần đầu, transformer có thể có cơ hội xử lý bytes. **Module resolution và class definition là hai sự kiện khác nhau**.

### Loader của advice khác loader của target

Weaver có thể hoạt động từ agent loader, nhưng code đã dệt trong billing chạy dưới target loader/module. Vì vậy phải kiểm chứng **caller của helper là class đã dệt**, chứ không chỉ agent tự gọi được helper. Không phải mọi cấu hình giúp agent nhìn thấy `TraceRuntime` đều giúp billing resolve được tham chiếu đến nó.

## 25. Security boundary: LTW không thay thế kiểm tra bắt buộc

Một aspect audit có thể được dệt trên nhiều class. Nhưng nếu engine loại trừ một module/plugin hoặc không xử lý class load sớm, một số đường thực thi có thể thiếu audit.

Với chính sách bảo mật:

- Không coi việc có agent là bằng chứng **mọi phương thức nhạy cảm** được can thiệp.
- Xác định điểm thực thi đáng tin cậy không có đường bypass.
- Có test cho class load sớm/muộn, multi-loader, module path và deployment.
- Xác minh đúng policy và thứ tự các advice nếu nhiều aspect cùng match.
- Không đưa bí mật, token hoặc dữ liệu cá nhân vào log transformer chỉ để debug.
- Không mở toàn bộ module cho reflection nếu một thay đổi truy cập hẹp hơn đủ giải quyết vấn đề.

Nếu security check là bất biến phải luôn đúng, việc thiết kế boundary bảo vệ cần độc lập với giả định “weaver chắc sẽ chạy”. AOP có thể là một cách triển khai hoặc lớp bổ sung, nhưng phải có chứng cứ coverage thích hợp.

## 26. Tương tác với asynchronous tasks và thread context

LTW xảy ra khi **class được nạp**, nhưng advice đã weave chạy tại **join point runtime**. Nếu một method được gọi từ worker thread hoặc callback:

- Class có thể đã được weave từ lâu, trước khi worker được tạo.
- Advice vẫn chạy ở worker nếu execution đi qua join point đã dệt.
- Dữ liệu `ThreadLocal` của caller không tự chuyển sang worker.
- Một pointcut dựa trên ngữ cảnh control-flow đồng bộ không tự nối qua executor/task.
- Method trả `CompletableFuture` có thể kết thúc trước khi công việc bất đồng bộ hoàn tất.

**Giới hạn class-loading coverage** và **giới hạn context propagation** là hai vấn đề riêng. Weaving đầy đủ vào method body không tự làm trace ID của thread A xuất hiện trên thread B.

Nếu cần đo end-to-end async, phải xác định join point lúc submit, lúc thực thi, lúc hoàn tất và cách liên kết chúng bằng context phù hợp.

## 27. Kiểm thử LTW: cần quan sát ba lớp chứng cứ

Một quy trình QA tốt phân biệt:

### (1) Agent/transformer đã được kích hoạt?

- `premain` có chạy không?
- Transformer có được đăng ký không?
- Runtime có gọi transformer cho class cụ thể không?
- Class được load ở module/loader nào?

**Chứng cứ:** log callback, diagnostics của instrumentation, số class đi qua filter.

### (2) Bytecode class đích có thực sự được biến đổi đúng?

- Transformer có trả bytes mới thay vì `null` không?
- Pointcut có tìm được join point không?
- Class sau biến đổi có thể verify/link không?
- Reference tới helper có resolve và truy cập được không?

**Chứng cứ:** diagnostics của weaver, snapshot bytes có kiểm soát, kiểm tra bytecode, test class loading. Không lưu/ghi thông tin nhạy cảm từ class/argument vào log.

### (3) Advice có chạy đúng tại đường nghiệp vụ?

- Method execution hoặc call site mong muốn thực sự xảy ra không?
- Advice chạy bao nhiêu lần so với target?
- Kết quả/ngoại lệ có giữ contract?
- Có đường bypass hoặc implementation khác chưa được weave?

**Chứng cứ:** test hành vi từ caller/target, test positive/negative, concurrency và failure paths.

Ba lớp này **không thể thay thế nhau**. Ví dụ demo ở trên chứng minh (1), cố ý **không thực hiện** (2) hoặc (3).

## 28. Ma trận kiểm thử class loading và module

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Agent bật từ `-javaagent` | `premain` chạy trước ứng dụng |
| Không bật agent | Không có transformation callback |
| Target class load sau khi đăng ký | Transformer quan sát đúng class |
| Target class load trước khi đăng ký | Không tự nhận callback load lần đầu sau đó |
| Target class đã load, yêu cầu retransform | Runtime cho phép không; class có modifiable không |
| Một class không nằm trong scope | Không bị weave ngoài ý định |
| Một class đúng scope nhưng pointcut không khớp | Không chèn advice sai |
| Class nằm trong named JPMS module | Module identity và helper access chính xác |
| Class nằm trong unnamed module | Xử lý đúng module không tên |
| Custom class loader | Matching/cache theo loader phù hợp |
| Hai loader nạp cùng tên class | Không dùng nhầm type/bytecode/policy |
| Plugin/module layer load muộn | Transformer bao phủ class ở layer mới nếu được hỗ trợ |
| Helper nằm ở module khác | Class đã dệt có thể resolve/access helper |
| Package không `opens` | Phân biệt lỗi Reflection với lỗi weaving |
| JAR đã biến đổi nhưng runtime dùng bản gốc | Test phát hiện sai artifact/loader |
| Hai transformer cùng áp dụng | Không sinh bytes hỏng hoặc advice trùng |
| Một method private/static/final | Engine có thực sự hỗ trợ join point cần chọn? |
| Self-invocation | Test call site/execution theo cơ chế đã dùng |
| Caller ở module A, callee ở B | Phân biệt nơi có call và execution join point |
| Callback chạy ở worker thread | Advice coverage và context propagation là hai test riêng |
| Target ném exception | Advice giữ/thay outcome đúng contract |
| Thay cấu hình sau load | Behavior nào đổi mà không retransform? |

### Kiểm thử đúng với production configuration

Một test JVM có `-javaagent` không bảo đảm production startup cũng có flag đó. Một ứng dụng chạy từ IDE/classpath có thể khác khi deploy trên module path/container. Cần kiểm tra:

- JVM startup arguments đã thực dùng.
- Đường dẫn và manifest của agent JAR.
- Module path/classpath, loader/layer thực tế.
- Version JDK, bytecode weaver và class-file format.
- Class nào load sớm trong production nhưng muộn ở test.
- Việc bật/tắt các filter và cấu hình dệt.

## 29. Quy trình chẩn đoán khi advice không chạy

**Bước 1 — Kiểm tra agent.** Có đúng `-javaagent`? Manifest có `Premain-Class`? Agent startup có lỗi?

**Bước 2 — Kiểm tra transformer.** Đã đăng ký thành công? Có thấy class đích? Tên nội bộ đúng với `/` hay đang so chuỗi có dấu `.`?

**Bước 3 — Kiểm tra thời điểm.** Class đã được load trước khi transformer đăng ký chưa? Có dynamic attach nhưng thiếu retransform không?

**Bước 4 — Kiểm tra class loader/module.** Target thuộc loader và JPMS module nào? Có plugin layer hoặc nhiều class trùng tên không?

**Bước 5 — Kiểm tra scope.** Transformer có loại class do filter package/module/loader không? Điểm cần chọn nằm ở bytecode của caller hay callee?

**Bước 6 — Kiểm tra pointcut.** Join point là call, execution hay loại khác? Chữ ký, overriding, inherited method, annotation/generic bridge có khớp không?

**Bước 7 — Kiểm tra bytes.** Weaver có thật sự trả bytes đã biến đổi hay `null`? Có lỗi verify/link hoặc helper access không?

**Bước 8 — Kiểm tra thứ tự và các aspect khác.** Around advice ở ngoài có bỏ qua `proceed`, khiến target/inner advice không chạy không?

**Bước 9 — Kiểm tra đường nghiệp vụ.** Lời gọi có xảy ra không, bị proxy bypass, được gọi qua reflection, hay nằm trong worker/process khác?

**Bước 10 — Kiểm tra observability.** Advice đã chạy nhưng log/metric bị tắt hoặc sampling không? Tách “advice entered” khỏi “có stdout”.

Không nên thay `opens` hay thêm wildcard weave toàn bộ module ngay khi chưa phân loại lỗi.

## 30. Những sai lầm thường gặp

1. **“Agent in `premain` nghĩa là mọi class đều đã dệt.”** Chỉ là agent có cơ hội đăng ký transformer.
2. **“Transformer in tên class là advice đã chạy.”** Callback load khác runtime join point.
3. **“Trả `null` từ transformer là dệt thành công.”** `null` nghĩa là không thay bytes trong callback đó.
4. **“Class đã nạp sẽ được dệt khi đổi config.”** Không tự xảy ra nếu không có cơ chế động khác.
5. **“Retransformation như compile lại source.”** API có giới hạn cấu trúc/class modifiability.
6. **“Có named module tức mọi class đã load.”** Module resolution khác class loading.
7. **“`requires`/`exports` tự làm AOP hoạt động.”** JPMS quản lý quyền truy cập, không tự weave.
8. **“Thêm `opens` sửa được mọi vấn đề.”** Chỉ giúp một lớp vấn đề Reflection/access.
9. **“Agent thấy bytes nên target chắc gọi được advice helper.”** Vẫn cần class resolution và module access.
10. **“Cùng class name nghĩa là cùng runtime class.”** Defining loader cũng thuộc identity.
11. **“Một transformer luôn được gọi đúng một lần với mọi class.”** Ràng buộc retransform, loaders và pipeline có thể tạo nhiều sự kiện; cần xem contract.
12. **“LTW cho mọi method kể cả private/final.”** Phải kiểm tra engine và loại join point.
13. **“Call pointcut ở module A có thể thấy mọi call site trong B.”** Không nếu bytecode B không được instrument.
14. **“Execution pointcut ở B chỉ cần weave interface của B.”** Implementation method body có thể ở class khác.
15. **“Weaving đồng nghĩa với proxy.”** Proxy có đường interception riêng và có thể bypass.
16. **“Weave đầy đủ là ThreadLocal tự lan qua executor.”** Class transformation không tự truyền ngữ cảnh.
17. **“Hai agents độc lập sẽ không xung đột.”** Thứ tự, bytes và helper dependencies có thể tương tác.
18. **“Một test startup bao phủ cả plugin load muộn.”** Loader/module layer mới phải được kiểm thử.
19. **“Có advice rồi thì thay được mọi result/argument.”** Quyền thay dữ liệu còn tùy advice, join point và type contract.
20. **“Mất log đồng nghĩa thiếu weaving.”** Có thể advice chạy nhưng sink/metric bị tắt; phải có chứng cứ theo tầng.

## 31. Bài tập thực hành

1. Tạo đúng ba file Java và manifest trong ví dụ, chạy không có agent và có agent; giải thích hai output.
2. Thay matcher class name thành `"demo/app/Main"`. Có thể log transform của Main xuất hiện trước `app.main` không? Vì sao?
3. Thêm class `demo.app.Helper` và gọi `Class.forName` cho nó trước `Worker`; tạo bộ lọc quan sát cả hai class và phân tích thứ tự log.
4. Đổi `Class.forName` thành overload có `initialize=false`. Phân biệt load và initialization; thêm static initializer vào Worker để kiểm tra.
5. Cho agent tạo `new Worker()` **trước `addTransformer`** (đảm bảo app class trên agent classpath phù hợp). Dự đoán việc load class sớm ảnh hưởng hook ra sao và giải thích rủi ro của thiết kế này.
6. Sửa matcher để in thêm thông tin `loader == null`, class loader class/name nếu không null. Đừng dùng thông tin ấy như dữ liệu bảo mật.
7. Thêm phiên bản `transform(Module, ...)` hỗ trợ Java 9+, in `module.isNamed()` và `getName()` cho Worker.
8. Chạy ứng dụng classpath, sau đó tổ chức Main/Worker trong một named JPMS module, điều chỉnh biên dịch và quan sát module name.
9. Thiết kế mô hình hai module `checkout` và `billing`; xác định nơi bytecode cần được dệt nếu chọn call site ở checkout.
10. Với cùng hai module, xác định nơi cần dệt nếu chọn execution của `BillingService.create`, bất kể caller nào.
11. Vẽ timeline: transformer đăng ký ở t2, class A load t1, class B load t3. Có những class nào được can thiệp ở first-load callback?
12. Tìm contract của `Instrumentation.isRetransformClassesSupported()` và `isModifiableClass` trong JDK bạn đang dùng; vì sao kết quả này cần kiểm tra trước khi retransform?
13. Viết test cho hai class cùng tên qua hai custom loader để minh họa class identity và nguy cơ cache chỉ theo tên.
14. Tạo một helper class ở module khác; phân tích những read/export/open edge thực sự cần khi bytecode đã dệt tham chiếu helper.
15. Mô phỏng hai transformer: một chỉ log, một giả định sinh advice. Nêu ít nhất ba lỗi tiềm ẩn nếu cả hai cùng chỉnh một method.
16. Thiết kế test phân biệt “transform callback được gọi” với “bytecode đã sửa” và “advice thực thi”.
17. Một method được gọi từ worker trong executor: LTW có tự truyền trace ID từ `ThreadLocal` của caller không? Nếu không, phần nào phải xử lý riêng?
18. Một module plugin được load sau startup: liệt kê các giả định cần xác minh về transformer registration, class loader, module layer và advice helper.
19. Xây coverage matrix có ít nhất năm đường **phải có advice** và năm đường **không được có advice**, kiểm tra từng đường bằng runtime test.
20. Đưa ra quy trình phát hành nhằm đảm bảo production thực sự chạy với đúng agent JAR, config, module path và JDK version.

**Tự kiểm tra:** Khi thấy `agent.transform`, đã đủ kết luận code được dệt chưa? Vì sao `return null` không thay đổi bytecode? Module đã resolve có nghĩa toàn bộ class đã được load không? Tại sao class loader identity làm matching khác nhau? Nếu pointcut chọn call từ A và execution ở B, loại bytecode nào cần can thiệp? Vì sao retransform khác first-load weaving? `opens` có tự tạo advice không?

## Kết luận

**Dệt khi nạp là sự kết hợp AOP tại ranh giới định nghĩa class, không phải một lần gọi method hoặc một cờ bật toàn cục.** Để hiểu và triển khai đúng, cần nắm **loading–linking–initialization**, thời điểm đăng ký transformer, sự khác biệt giữa first-load và retransformation, phạm vi class loader, Java module readability/exports/opens, và khả năng resolve runtime helper. Một thiết kế LTW đáng tin cậy phải phân biệt **transform callback được gọi**, **bytecode thật sự được dệt** và **advice thực sự chạy tại join point**, đồng thời kiểm thử cả module/class loader, caller/callee, class load sớm/muộn, các đường bypass và cấu hình triển khai. Khi những ranh giới này rõ ràng, AOP mới có thể áp dụng nhất quán mà không đánh đổi sự chính xác của chương trình chỉ để đạt cảm giác “dệt được mọi nơi”.