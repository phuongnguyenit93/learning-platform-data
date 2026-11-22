# Phân biệt biến đổi ngoại tuyến, biến đổi lúc nạp và thay đổi lớp đã nạp

Trong Java, **instrumentation** là kỹ thuật quan sát hoặc can thiệp vào hành vi chương trình bằng cách xử lý bytecode của lớp. Ba cách thường bị nhầm lẫn là **biến đổi ngoại tuyến (offline transformation)**, **biến đổi lúc nạp lớp (load-time transformation)** và **thay đổi lớp đã được JVM nạp (retransformation/redefinition)**. Cùng có thể dùng bytecode mới, nhưng chúng khác nhau về **thời điểm áp dụng, nơi lấy bytecode, API kích hoạt và giới hạn của cấu trúc lớp**.

Sau bài này, bạn cần giải thích được: tệp `.class` nào được dùng ở mỗi giai đoạn; vì sao thay một JAR trên đĩa không tự đổi lớp đang chạy; khác nhau giữa `retransformClasses` và `redefineClasses`; khi nào phải khởi động lại ứng dụng; và cách kiểm chứng một agent thực sự can thiệp ở thời điểm nào.

## 1. Trước hết: bytecode trên đĩa khác định nghĩa lớp trong JVM

Luồng thông thường:

```text
.java --javac--> .class/JAR --[đọc bởi ClassLoader]--> defineClass
          ^                              |
          |                              +-- transformer lúc nạp (nếu được đăng ký)
          |                              v
      biến đổi ngoại tuyến       JVM xác minh/liên kết/khởi tạo/sử dụng lớp
                                             |
                                             +-- retransform/redefine (nếu được hỗ trợ và yêu cầu)
```

- **Tệp lớp** là bytecode được lưu trong thư mục, JAR hay một nguồn dữ liệu khác. Thay các byte ở đây không mặc nhiên thay định nghĩa lớp đã được JVM tạo.
- **Định nghĩa lớp đã nạp** thuộc một JVM và một **defining ClassLoader** cụ thể. Tên nhị phân giống nhau nhưng do hai class loader khác nhau định nghĩa vẫn là hai lớp khác nhau.
- **Loading, linking, initialization** là các bước khác nhau. Callback biến đổi lúc nạp xảy ra trước khi định nghĩa mới được JVM xác minh và sử dụng; `retransform` tác động tới lớp đã tồn tại.
- Java không định nghĩa cơ chế “nạp lại cùng lớp mỗi lần gọi phương thức”. Khi lớp đã nạp, thay `.class` hoặc JAR nguồn thường chỉ có hiệu lực với lần nạp mới ở một JVM/class loader phù hợp, hoặc sau một thao tác thay đổi lớp được JVM hỗ trợ.

**Điểm phân biệt cốt lõi:** “Agent được khởi động khi nào?” và “Lớp được biến đổi khi nào?” là hai câu hỏi riêng. Agent gắn vào JVM sau lúc khởi động vẫn có thể xử lý *những lớp được nạp trong tương lai*; muốn đụng đến lớp đã nạp, nó phải yêu cầu retransform/redefine thích hợp.

## 2. Biến đổi ngoại tuyến — offline transformation

**Thời điểm:** sau bước tạo bytecode và **trước** khi JVM mục tiêu định nghĩa lớp. Chương trình build, plugin, công cụ đóng gói hoặc một bước xử lý tệp đọc `.class`/JAR, viết ra bytecode mới, rồi ứng dụng chạy bằng artifact đã biến đổi.

Ví dụ một hệ thống coverage cần chèn lệnh đếm vào mỗi phương thức khi đóng gói:

```text
Nguồn Java --> javac --> build/classes
                           |
                   Offline transformer
                           |
                           v
                  build/instrumented
                           |
                     Đóng gói/JAR
                           |
                    JVM nạp lớp mới
```

Đặc điểm:

1. **Đầu vào/đầu ra:** các byte tệp lớp hoặc JAR; kết quả thường là artifact mới, có thể kiểm tra, lưu trữ và phát hành.
2. **Không cần agent trong JVM đích** nếu mọi lớp cần thiết đã được biến đổi trước lúc chạy. Lớp được nạp theo đường bình thường từ artifact mới.
3. **Khả năng chỉnh cấu trúc rộng hơn:** có thể thêm phương thức/trường/lớp, đổi cấu trúc bytecode miễn tệp lớp hợp lệ và chương trình còn tương thích. Không bị ràng buộc bởi quy tắc thay thế cấu trúc của *lớp đang tồn tại*.
4. **Không cập nhật JVM đang chạy:** ghi đè JAR hoặc `.class` sau khi lớp đã được định nghĩa không làm các đối tượng và phương thức hiện tại tự chuyển sang phiên bản mới.
5. **Đánh đổi:** tăng bước build, khó áp dụng nếu bytecode chỉ được sinh lúc chạy hoặc đến từ thư viện không nằm trong pipeline; phải bảo toàn thông tin debug, tương thích phiên bản class file, tài nguyên đóng gói và chữ ký của JAR nếu có.

Một thao tác biến đổi ngoại tuyến *về nguyên lý* là đọc mảng byte, chuyển đổi bằng một thư viện hiểu định dạng class file (ví dụ ASM hoặc Byte Buddy), rồi ghi artifact khác. Đó là một bước build, không phải lời gọi `Instrumentation.retransformClasses`.

**Nên dùng khi:** biết trước tập lớp sẽ chạy, cần build có thể lặp lại/kiểm tra được, cần thay đổi cấu trúc lớn, hoặc muốn giảm logic instrument ở thời gian khởi động.

## 3. Biến đổi lúc nạp — load-time transformation

**Thời điểm:** JVM chuẩn bị định nghĩa một lớp mới. Java agent đăng ký `ClassFileTransformer` với `Instrumentation.addTransformer(...)`. Khi một lớp đi qua quá trình định nghĩa, JVM đưa bytecode đầu vào qua chuỗi transformer trước khi xác minh/đưa định nghĩa đó vào sử dụng.

Một Java agent khởi động sớm thường có entry point:

```java
public static void premain(String agentArgs, Instrumentation instrumentation) {
    instrumentation.addTransformer(new MyTransformer());
}
```

Trong `transform`, đối với một lớp được nạp lần đầu, `classBeingRedefined == null`. Tên `className` dùng dạng nội bộ, ví dụ `com/example/OrderService`, và có thể không khả dụng cho một số dạng lớp. Transformer trả về:

- `null`: không thay đổi bytecode ở lượt callback này;
- một `byte[]` **mới, hợp lệ**: JVM dùng bytecode mới làm đầu vào cho các bước tiếp theo trong chuỗi transformer/định nghĩa lớp. Không sửa trực tiếp `classfileBuffer`.

Ví dụ phần thân transformer dùng bytecode library (mã **minh họa**, `rewriteWithAsmOrByteBuddy` là hàm cần tự cài đặt; đoạn này không phải chương trình độc lập):

```java
@Override
public byte[] transform(ClassLoader loader, String className,
                        Class<?> classBeingRedefined,
                        ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"com/example/OrderService".equals(className)) {
        return null;
    }
    return rewriteWithAsmOrByteBuddy(classfileBuffer);
}
```

### Những điều load-time *có* và *không* bảo đảm

- **Chỉ xử lý khi có sự kiện định nghĩa lớp:** nếu transformer được đăng ký *sau* khi `OrderService` đã nạp, thêm transformer không làm lớp đó tự chạy lại callback.
- **Có thể can thiệp cấu trúc trước định nghĩa:** khác với redefinition/retransformation, chưa có định nghĩa cũ để phải giữ nguyên cấu trúc; tuy nhiên bytecode vẫn phải hợp lệ, lớp phụ thuộc phải tương thích và class loader/module phải truy cập được những gì code mới dùng.
- **Agent khởi động bằng `-javaagent`:** phương thức `premain` chạy trước `main` của ứng dụng, giúp thiết lập transformer sớm. Một số lớp của nền tảng/agent có thể đã được tải trước lúc transformer sẵn sàng; không giả định mọi lớp trong JVM đều sẽ đi qua nó.
- **Agent được gắn động:** `agentmain` có thể đăng ký transformer cho **các lần nạp về sau**, nhưng không tự sửa những lớp đã nạp.
- **Nhiều transformer có thể nối chuỗi:** đầu ra của transformer trước trở thành đầu vào transformer sau; thứ tự và xung đột có thể ảnh hưởng kết quả. Chỉ xử lý lớp mục tiêu và tránh tạo vòng phụ thuộc khi transformer tự tải thư viện của mình.

**Nên dùng khi:** cần thêm tracing, metrics, profiling, coverage hoặc proxy behavior tự động ở thời điểm lớp được nạp, kể cả với thư viện không sửa nguồn.

## 4. Lớp đã nạp — retransformation và redefinition

Một khi lớp đã được định nghĩa, JVM **không đơn giản chạy lại `defineClass` cùng tên và cùng loader** để ghi đè nó. API `java.lang.instrument.Instrumentation` cung cấp hai cơ chế thay đổi định nghĩa hiện có, tùy năng lực JVM và quyền/cấu hình agent.

### 4.1. `retransformClasses(Class<?>... classes)`

Đây là cách **yêu cầu JVM chạy lại quy trình transformer** đối với những lớp chỉ định:

1. Agent có `Instrumentation` và `isRetransformClassesSupported() == true`; manifest của agent cho phép với `Can-Retransform-Classes: true`.
2. Transformer cần được đăng ký với `addTransformer(transformer, true)` nếu muốn **được gọi lại** khi retransform.
3. Kiểm tra lớp cụ thể qua `isModifiableClass(target)` rồi gọi `retransformClasses(target)`.
4. JVM tạo bytecode đầu vào từ định nghĩa ban đầu hoặc lần redefine gần nhất; các biến đổi của transformer *không có quyền retransform* được tái áp dụng dưới dạng kết quả cũ, còn transformer *có quyền retransform* được gọi lại. Không nên giả định đầu vào là byte array đã chồng nối mọi lần instrument trước.
5. JVM xác minh và cài định nghĩa mới nếu thay đổi hợp lệ; nếu lỗi, thao tác thất bại theo hợp đồng API.

`retransformClasses` **không nhận bytecode thay thế trực tiếp** từ người gọi. Bạn cập nhật hành vi biến đổi của transformer rồi yêu cầu JVM áp dụng lại cho lớp mục tiêu. `classBeingRedefined` trong callback lúc này khác `null`.

### 4.2. `redefineClasses(ClassDefinition... definitions)`

Đây là cách **cung cấp trực tiếp bytecode thay thế** cho một hoặc nhiều lớp đã tồn tại:

```java
// Minh họa API, không phải chương trình độc lập:
byte[] replacement = /* bytecode .class hợp lệ cho đúng lớp đang có */;
instrumentation.redefineClasses(
    new ClassDefinition(ExistingService.class, replacement)
);
```

Điều kiện: `isRedefineClassesSupported() == true`, manifest có `Can-Redefine-Classes: true`, lớp sửa được và bytecode đáp ứng các giới hạn thay đổi. JVM vẫn có thể đưa class bytes qua transformer theo quy tắc của API.

**Khác nhau quan trọng:** retransform thích hợp khi muốn các transformer đã đăng ký xử lý lại; redefine thích hợp khi đã có một bản class file thay thế chính xác (ví dụ trình gỡ lỗi biên dịch lại method rồi hot swap).

### 4.3. Giới hạn của lớp đã nạp

Với cơ chế chuẩn trên HotSpot/JDK thông dụng, retransform/redefine cho phép thay mã thực thi của phương thức trong giới hạn tương thích, nhưng **không cho tùy ý thay schema của lớp**. Những thay đổi như thêm/xóa/đổi tên trường hoặc phương thức, đổi chữ ký hay modifier, thay lớp cha hoặc danh sách interface có thể bị từ chối. Năng lực hỗ trợ là **tùy JVM**; luôn kiểm tra API và xử lý ngoại lệ, không coi HotSwap là thay thế bản build hoàn chỉnh.

Tác động sau khi thay thành công:

- **Lần gọi phương thức mới** thường chạy định nghĩa mới; **stack frame đang thực thi** của phương thức đã thay tiếp tục chạy bytecode cũ cho lần gọi đó.
- **Không tự chạy lại static initializer (`<clinit>`)**, không tạo lại object đã có và không reset trạng thái trường static; thay đổi logic không đồng nghĩa di chuyển cấu trúc hay dữ liệu đối tượng.
- **Đúng lớp/đúng loader:** `com.example.Foo` trong hai defining class loader khác nhau là hai mục tiêu khác nhau.
- **Không phải mọi lớp đều thay được:** tính năng retransform/redefine có thể bị tắt hoặc không được JVM hỗ trợ; từng lớp có thể không modifiable.
- **Không suy ra “đổi trực tiếp bytecode ở đĩa”:** bản mới cài trong JVM không nhất thiết ghi ngược ra JAR. Khi chạy tiến trình mới từ artifact cũ, ứng dụng sẽ trở về bytecode từ artifact đó.
- **Thay đổi đồng bộ nhiều lớp:** một thao tác API có thể chứa nhiều lớp liên quan, nhưng vẫn phải bảo toàn ràng buộc và liên kết nhị phân.

### 4.4. Attach một agent không tự động là retransform

`premain` được gọi khi chạy với `-javaagent`; `agentmain` dành cho agent được nạp vào JVM đang chạy qua cơ chế attach tương ứng. Cả hai đều có thể nhận `Instrumentation`. Từ đó, agent **có thể** đăng ký transformer để xử lý lớp nạp sau hoặc chủ động yêu cầu `retransformClasses`/`redefineClasses` cho lớp hiện tại.

JDK 21 (JEP 451) phát cảnh báo khi agent được nạp động; cờ `-XX:+EnableDynamicAgentLoading` biểu thị lựa chọn cho phép ở JDK 21. Chính sách mặc định về dynamic loading thay đổi theo phiên bản/triển khai JVM. Khởi động bằng `-javaagent` và sửa một lớp đã nạp là hai khía cạnh độc lập.

## 5. Bảng so sánh ba đường đi

| Tiêu chí | Ngoại tuyến (offline) | Lúc nạp (load-time) | Lớp đã nạp (retransform/redefine) |
|---|---|---|---|
| **Thời điểm** | Trước khi JVM mục tiêu nạp lớp | Ngay khi JVM chuẩn bị định nghĩa lớp mới | Sau khi JVM đã định nghĩa lớp |
| **Nơi can thiệp** | File `.class`/JAR hoặc artifact build | Chuỗi transformer trong JVM | Định nghĩa lớp hiện có trong JVM |
| **Nguồn bytecode** | Artifact đầu vào | Bytes JVM/ClassLoader sắp định nghĩa | Bytes nền + các transformer được áp dụng lại; hoặc bytes mới cung cấp cho redefine |
| **Kích hoạt** | Công cụ build/packaging/rewriter | Đăng ký `ClassFileTransformer`; sự kiện class loading | Gọi `retransformClasses` hoặc `redefineClasses` |
| **Có tác dụng với lớp đã nạp?** | Không tự động | Không tự động | Có, nếu lớp/JVM hỗ trợ và bytecode hợp lệ |
| **Thay cấu trúc lớp?** | Có thể trong giới hạn class file/tính tương thích | Có thể trước lúc định nghĩa, nếu bytecode hợp lệ | Bị giới hạn mạnh bởi cơ chế sửa lớp đã nạp |
| **Sự tồn tại của thay đổi** | Trong artifact đầu ra | Trong định nghĩa đã nạp của tiến trình | Trong định nghĩa hiện tại của tiến trình |
| **Ví dụ** | Build-time coverage, weaving cho bản phát hành | Tracing agent lúc khởi động | HotSwap debugger, cập nhật probe trong JVM đang chạy |

**Chú ý:** `-javaagent` tự nó không đồng nghĩa “load-time only”: cùng một agent có thể thực hiện load-time transformation và về sau chủ động gọi retransform.

## 6. Thử nghiệm Java 17+ chạy được: thấy cả hai callback

Ví dụ này **quan sát thời điểm** và cố ý trả `null`, vì vậy **không thay bytecode**. Nó giúp chứng minh “nạp lần đầu” và “xử lý lại lớp đã nạp” là hai sự kiện riêng. Cần JDK chuẩn có `javac`, `jar` và hỗ trợ retransformation.

Tạo ba file Java và một file manifest **cùng thư mục**:

**`TraceAgent.java`**

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class TraceAgent implements ClassFileTransformer {
    private static Instrumentation instrumentation;

    public static void premain(String agentArgs, Instrumentation inst) {
        instrumentation = inst;
        boolean supported = inst.isRetransformClassesSupported();
        inst.addTransformer(new TraceAgent(), supported);
        System.out.println("agent ready; retransformation=" + supported);
    }

    public static void retransform(Class<?> target)
            throws UnmodifiableClassException {
        if (!instrumentation.isRetransformClassesSupported()
                || !instrumentation.isModifiableClass(target)) {
            System.out.println("retransform unavailable");
            return;
        }
        instrumentation.retransformClasses(target);
    }

    @Override
    public byte[] transform(ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain,
            byte[] classfileBuffer) {
        if ("Sample".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "first load" : "retransform/redefine";
            System.out.println("transform Sample: " + phase);
        }
        return null; // chỉ quan sát, không sửa bytecode
    }
}
```

**`Sample.java`**

```java
public final class Sample {
    public static String message() {
        return "hello";
    }
}
```

**`Demo.java`**

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("Demo.main");
        Class<?> target = Class.forName("Sample");
        System.out.println("before: "
                + target.getMethod("message").invoke(null));
        TraceAgent.retransform(target);
        System.out.println("after: "
                + target.getMethod("message").invoke(null));
    }
}
```

**`manifest.mf`** (kết thúc bằng một dòng trống):

```text
Manifest-Version: 1.0
Premain-Class: TraceAgent
Can-Retransform-Classes: true

```

Biên dịch, đóng gói và chạy trong thư mục có bốn file trên:

```shell
javac TraceAgent.java Sample.java Demo.java
jar cfm trace-agent.jar manifest.mf TraceAgent.class
java -javaagent:trace-agent.jar -cp . Demo
```

Trên HotSpot JDK 17/21 hỗ trợ retransformation, đầu ra dự kiến là:

```text
agent ready; retransformation=true
Demo.main
transform Sample: first load
before: hello
transform Sample: retransform/redefine
after: hello
```

**Giải thích kết quả:**

1. `premain` đăng ký transformer trước khi `Demo.main` chạy.
2. `Class.forName("Sample")` tải `Sample` lần đầu; callback nhận `classBeingRedefined == null`.
3. `retransformClasses(target)` kích hoạt callback mới với `classBeingRedefined != null`. Chuỗi `retransform/redefine` chỉ là nhãn quan sát của ví dụ; ở đây lời gọi thực sự là **retransform**.
4. Hai lần in `hello` bằng nhau vì transformer luôn trả `null`. Muốn đổi hành vi thật, thay logic đó bằng phép biến đổi bytecode hợp lệ, chẳng hạn thông qua ASM/Byte Buddy; vẫn phải tuân thủ giới hạn của lớp đã nạp.

Nếu JVM báo `retransformation=false`, ví dụ in `retransform unavailable` và không có callback thứ hai; đây là bằng chứng cần kiểm tra năng lực môi trường chứ không chứng minh code `Sample` không thể instrument bằng cách khác.

## 7. Chọn cơ chế qua các tình huống thực tế

**Tình huống A — Cần thêm trường mới vào lớp để triển khai bản phát hành tiếp theo.** Hãy biến đổi khi build hoặc thay source rồi build lại; chạy phiên bản mới trong tiến trình/class loader mới. Không lên kế hoạch dựa vào việc thêm trường vào lớp đã nạp bằng HotSwap chuẩn.

**Tình huống B — Đo thời gian mọi lời gọi HTTP của thư viện bên thứ ba ngay từ khi khởi động.** Dùng `-javaagent`, đăng ký transformer càng sớm càng tốt, lọc className đúng và đưa probe vào lúc lớp được nạp. Kiểm tra những lớp có thể đã được JVM nạp trước khi agent đăng ký.

**Tình huống C — Ứng dụng đang chạy; muốn bật thêm probe cho một lớp đã được sử dụng.** Agent phải có khả năng truy cập JVM và quyền retransformation, tìm đúng `Class<?>`/class loader, kiểm tra `isModifiableClass`, triển khai transformer hỗ trợ retransform và gọi `retransformClasses`. Nếu bạn đã có bytecode thay thế thích hợp, cân nhắc `redefineClasses`. Cả hai phải đáp ứng giới hạn cấu trúc.

**Tình huống D — Chỉ thay JAR của service trên đĩa rồi mong request tiếp theo dùng code mới.** Điều đó không làm class definition hiện tại tự thay. Cần restart/redeploy, class loader mới có chiến lược quản lý vòng đời riêng, hoặc một cơ chế retransform/redefine hợp lệ tùy mục tiêu.

## 8. Lỗi thường gặp và cách kiểm tra

- **Nhầm file với class đang sống:** đối chiếu artifact, class loader và thời điểm `defineClass`; đừng kết luận từ việc tệp `.class` đã đổi.
- **Đăng ký transformer quá muộn:** lớp đã nạp không phát sinh callback load-time lần nữa. Nếu cần tác động ngay, kiểm tra đường retransform/redefine.
- **Không bật capability:** `addTransformer(t, true)` có thể không hợp lệ nếu JVM/manifest không hỗ trợ; `Can-Retransform-Classes` và `Can-Redefine-Classes` là hai capability khác nhau.
- **Đòi đổi schema sau khi đã nạp:** lớp đã nạp thường không chấp nhận thêm trường/phương thức hay đổi inheritance. Dời thay đổi cấu trúc sang build/deploy hoặc mô hình class loader khác.
- **Tạo bytecode không hợp lệ:** có thể gặp `ClassFormatError`, `VerifyError`, `LinkageError` hoặc ngoại lệ hỗ trợ thao tác; kiểm tra stack map frames, version và dependency. Biến đổi phải tạo bytecode đúng cho đúng định nghĩa lớp.
- **Quên tương tranh/vòng lặp:** transformer có thể bị gọi ở nhiều luồng và khi tải các lớp phụ thuộc; tránh tải lại chính lớp đang xử lý, ghi log tràn lan và dùng trạng thái không an toàn.
- **Nhầm callback với thay đổi thành công:** thấy `transform` chạy không bảo đảm bytecode đã thay (trả `null` là không đổi) hoặc kết quả hợp lệ; kiểm tra hành vi và lỗi sau khi JVM xác minh/cài lớp.
- **Cho rằng mọi method đang chạy lập tức chuyển mã:** frame đang hoạt động có thể tiếp tục bytecode cũ; quan sát trên những lời gọi mới và cân nhắc tác động lên trạng thái có sẵn.
- **Bỏ qua class loader/module:** trùng tên lớp không chứng minh cùng lớp; agent có thể cần xử lý module encapsulation nếu truy cập sâu vào gói không mở.
- **Dùng dynamic attach mà không kiểm tra JDK:** từ JDK 21 có cảnh báo liên quan JEP 451 và các phiên bản sau có thể đặt chính sách khác; kiểm tra cờ hỗ trợ và chính sách môi trường chạy.

### Tự kiểm tra

1. **Transformer được thêm sau khi lớp A đã nạp; lớp A có tự chạy lại callback không?** Không. Cần một yêu cầu retransform/redefine phù hợp nếu muốn xử lý lớp hiện tại.
2. **Offline transformer có thể sửa file JAR trong khi JVM dùng định nghĩa cũ không?** Có. Đó là hai vị trí khác nhau; định nghĩa đang sống không tự cập nhật.
3. **`retransformClasses` khác `redefineClasses` ở đâu?** Retransform cho JVM áp dụng lại chuỗi transformer theo quy tắc capability; redefine nhận bytecode thay thế cho `ClassDefinition`.
4. **Vì sao đổi body của phương thức dễ hơn thêm trường vào lớp đang chạy?** Body có thể được thay trong giới hạn cơ chế sửa lớp; thêm trường thay đổi schema mà HotSwap chuẩn thường không chấp nhận.
5. **Agent tải động có thể làm load-time transformation không?** Có, đối với lớp **được nạp sau** khi nó đăng ký transformer. Để thay lớp trước đó, cần một thao tác dành cho lớp đã nạp.

## Tài liệu tham khảo chính thức

- [Java SE 21 — Instrumentation API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `redefineClasses` và năng lực JVM.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, cách truyền bytecode và thứ tự transformer.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain` và manifest agent.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): cảnh báo và chính sách động khi nạp agent.

**Ghi nhớ:** Offline sửa **artifact trước lúc nạp**; load-time sửa **đầu vào của lần định nghĩa lớp đầu tiên**; retransform/redefine sửa **định nghĩa đã tồn tại** trong phạm vi JVM cho phép.