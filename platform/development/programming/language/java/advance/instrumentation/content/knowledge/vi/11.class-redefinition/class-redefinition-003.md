# Transformer đã đăng ký vẫn tham gia xử lý dữ liệu `redefineClasses`

> **Mục tiêu:** Hiểu chính xác cách những `ClassFileTransformer` đã đăng ký tiếp tục nhận và xử lý **class-file bytes mới được truyền vào `Instrumentation.redefineClasses(...)`**. Biết phân biệt với `retransformClasses(...)`, hiểu thứ tự các nhóm Java/native transformer, xác định `classfileBuffer` thật sự bắt đầu từ đâu, kiểm tra capability và giới hạn của redefinition, rồi thực hành với **Java 17+** để chứng minh ngay cả transformer đăng ký `canRetransform=false` vẫn có callback trong lần redefine.

Bài thuộc chủ đề **Redefinition** của Java Advanced Instrumentation. Tập trung vào điều xảy ra **trong pipeline cập nhật class đã nạp** chứ không đi sâu vào cách viết bytecode injection. Điều phải nhớ: *redefine không trực tiếp bỏ qua chuỗi transformer*. Bytes do caller cung cấp được đưa vào chain, sau đó JVM mới kiểm tra và áp dụng định nghĩa kết quả.

## 1. Bối cảnh: “redefine” không có nghĩa ghi đè nguyên xi bytes caller đưa vào

Giả sử `OrderService` đã được load vào JVM. Một công cụ muốn sửa thân method đã biên dịch và gọi:

```java
// Minh họa trong agent đang có Instrumentation inst,
// Class<?> targetClass và byte[] replacementClassFile.
inst.redefineClasses(
        new java.lang.instrument.ClassDefinition(
                targetClass, replacementClassFile));
```

`replacementClassFile` là một class file **đầy đủ**, chứ không phải patch từng instruction, diff so với class cũ hoặc tên path. `ClassDefinition` gắn cặp **class đã tồn tại** và **mảng byte định nghĩa thay thế**. Sau đó JVM **không nhất thiết** đưa nguyên mảng bytes đó vào runtime ngay. Những transformer Java/JVMTI **vẫn đang đăng ký** có cơ hội xử lý dữ liệu mới.

Đường đi khái niệm:

```text
ClassDefinition(targetClass, replacementClassFile)
                         │
                         ▼
        [1] Java retransformation-incapable
                         │
                         ▼
        [2] Native JVMTI retransformation-incapable
                         │
                         ▼
        [3] Java retransformation-capable
                         │
                         ▼
        [4] Native JVMTI retransformation-capable
                         │
                         ▼
              Class bytes sau chain
                         │
                         ▼
            JVM verify / install định nghĩa
```

Nếu chỉ có hai Java transformer, hai nhóm native vắng mặt nhưng **thứ tự nhóm Java vẫn được giữ**. Nếu tất cả callback trả “không thay đổi”, bytes cuối cùng vẫn mang logic của bản caller cung cấp; nếu một callback trả mảng mới, callback phía sau nhận mảng đã sửa.

**Phân biệt:** `redefineClasses` dùng class bytes do công cụ chỉ định. `retransformClasses` yêu cầu JVM **tính lại** định nghĩa từ initial bytes hiện tại theo quy tắc tái áp dụng transformer. Hai thao tác không tương đương, dù đều có thể thay đổi method bodies ở class đã nạp.

## 2. Hợp đồng chính thức của `ClassFileTransformer`

Interface:

```java
package java.lang.instrument;

// Chỉ dẫn tên API, không phải mã nguồn của một class tự viết.
public interface ClassFileTransformer {
    // Có overload transform(...) nhận Module trên Java 9+.
}
```

Một Java agent thường đăng ký:

```java
inst.addTransformer(myTransformer);        // canRetransform=false
inst.addTransformer(myTransformer, false); // canRetransform=false
inst.addTransformer(myTransformer, true);  // canRetransform=true
```

Các dòng trên là cú pháp ví dụ với `Instrumentation inst` và `ClassFileTransformer myTransformer` đã được tạo; ví dụ chạy độc lập nằm ở mục 7.

Theo Javadoc: transformer đã đăng ký nhận callback cho những **class definition mới** và những **class redefinition** phù hợp. Transformer `canRetransform=true` **còn** nhận callback cho **class retransformation**. Bởi vậy:

- Transformer đăng ký với **`false` vẫn nhận callback trên `redefineClasses`**.
- Transformer đăng ký với **`true` cũng nhận callback trên `redefineClasses`**.
- Chỉ với **`retransformClasses`**, transformer đăng ký **`false` không được gọi lại**. JVM tái áp dụng output đã có từ lần load/redefine tương ứng.
- Native JVMTI `ClassFileLoadHook` nằm trong chuỗi theo nhóm capable/incapable được đặc tả; việc JVM có native agent hay không phụ thuộc môi trường đang chạy.

Điều kiện hiển nhiên: transformer phải **vẫn đang được đăng ký**, sự kiện áp dụng cho class đó, và hoạt động diễn ra sau thời điểm đăng ký. Không thể suy luận một transformer được đăng ký muộn đã xử lý lần load cũ.

### Tóm tắt bằng bảng

| Tình huống | Java `canRetransform=false` | Java `canRetransform=true` |
| --- | --- | --- |
| Class mới được định nghĩa sau khi đăng ký | Callback | Callback |
| `redefineClasses` trên class hiện hữu sau khi đăng ký | **Callback mới** | **Callback mới** |
| `retransformClasses` trên class hiện hữu | **Không callback**, dùng kết quả cũ | **Callback mới** |
| Transformer đã bị `removeTransformer` trước yêu cầu | Không được chủ động đưa vào chain mới, nhưng callback đang diễn ra có thể còn | Tương tự |

Bảng nói về những Java transformer hợp lệ trong một JVM hỗ trợ thao tác tương ứng. Việc capable transformer có thể được đăng ký với `true` còn đòi hỏi capability `isRetransformClassesSupported()` và yêu cầu manifest/config tương ứng. **Khả năng redefine riêng không buộc phải bật khả năng retransform**.

## 3. Bốn nhóm transformer và thứ tự trong một lần redefine

JDK định nghĩa thứ tự:

1. **Java retransformation-incapable** — Java `ClassFileTransformer` đăng ký với `false`.
2. **Native retransformation-incapable** — JVMTI `ClassFileLoadHook` ở environment incapable.
3. **Java retransformation-capable** — Java transformer đăng ký với `true`.
4. **Native retransformation-capable** — JVMTI `ClassFileLoadHook` ở environment capable.

Khi **redefine**, cả bốn nhóm **có callback**, nếu transformer/hook đang bật và sự kiện áp dụng. **Thứ tự nhóm thắng thứ tự đăng ký toàn cục**. Chẳng hạn Java capable C được đăng ký trước Java incapable A, nhưng một yêu cầu redefine sẽ gọi **A trước C**.

Trong từng nhóm Java, thứ tự transformer là thứ tự đăng ký. Với JVMTI, thứ tự các environment trong cùng nhóm theo quy tắc JVMTI, không phải theo tên JAR, tên thư viện hoặc thứ tự log ứng dụng nhìn thấy.

```text
Giả sử đăng ký:
     C (Java capable)      lúc T1
     A (Java incapable)    lúc T2

Khi redefine Target:
     callback A
     callback C
```

Điều này không mâu thuẫn: **capability** ảnh hưởng vị trí nhóm. `canRetransform=true` nghĩa là transformer có thể tham gia retransformation, **không** có nghĩa được chạy trước nhóm incapable.

### Chú ý về native

“Native” trong thứ tự này **không phải** một method Java gắn keyword `native` và cũng không phải một đoạn JNI bất kỳ. Nó là **native JVMTI agent** sử dụng sự kiện `ClassFileLoadHook`. Ở mô hình đủ bốn nhóm, native incapable nằm **giữa** hai nhóm Java; native capable đứng **sau** Java capable.

Bài lab Java phía dưới chỉ chứng minh trực tiếp hai nhóm Java vì không triển khai JVMTI native agent. Thứ tự native được trình bày dựa trên đặc tả chứ không giả vờ xuất hiện trong stdout của chương trình Java.

## 4. Dữ liệu `classfileBuffer` trong redefine bắt đầu từ đâu?

Đối với callback đầu tiên của chuỗi redefinition, Javadoc mô tả input là **`ClassDefinition.getDefinitionClassFile()`** từ đối số caller truyền cho `Instrumentation.redefineClasses(...)`.

Nói cách khác:

```text
byte[] newBytes = Files.readAllBytes(pathToReplacement);
ClassDefinition definition =
        new ClassDefinition(loadedClass, newBytes);

instrumentation.redefineClasses(definition);

            ▼

Callback đầu tiên nhận newBytes (nội dung bản thay thế)
chứ không mặc định nhận bytes đã instrument ở lần load cũ.
```

Sau đó dữ liệu truyền giữa các transformer theo cơ chế **chaining**:

```text
replacement bytes V2
    │
    ├── transformer A nhận V2, trả V2A
    │
    ├── transformer B nhận V2A, trả null → giữ V2A
    │
    ├── transformer C nhận V2A, trả V2C
    │
    └── JVM thấy bytes V2C trước khi verify/install
```

`return null` ở tầng B **không** có nghĩa “hoàn nguyên về V2” hoặc “xóa hiệu ứng A”. Nó chỉ có nghĩa B không đổi dữ liệu mà B vừa nhận. Những transformer phía sau vẫn chạy trên output hiện hành.

### So sánh với class load ban đầu

Với một class load thông thường, input đầu tiên là bytes do `ClassLoader.defineClass` hoặc cơ chế tương đương đưa vào JVM. Với redefine, input đầu tiên là **bytes mới** trong `ClassDefinition`; không buộc phải giống bytes đã nạp lần đầu.

Vì vậy một transformer viết giả định rằng callback luôn nhận phiên bản `.class` nằm trên đường dẫn classpath ban đầu là không an toàn. Sau redefinition, cùng `className` có thể xuất hiện với **nội dung code mới, constant pool khác, StackMapTable khác** — dù vẫn phải tuân thủ những giới hạn schema của redefinition.

### Khác biệt quan trọng với `retransformClasses`

`Instrumentation.retransformClasses(target)` **không có** đối số `byte[]` mới. Nó bắt đầu từ initial bytes gắn với định nghĩa hiện tại; nếu class đã được redefine, căn cứ là lần redefine gần nhất. JVM **không gọi lại** nhóm incapable mà tự tái dùng output đã nhận từ lần load/redefine. Nhóm capable mới được gọi lại.

```text
REDEFINE:
    new bytes từ ClassDefinition
         → gọi Java incapable
         → gọi native incapable
         → gọi Java capable
         → gọi native capable
         → verify/install

RETRANSFORM:
    initial bytes của định nghĩa hiện tại
         → reuse Java incapable output, KHÔNG callback
         → reuse native incapable output, KHÔNG callback
         → gọi Java capable
         → gọi native capable
         → verify/install
```

Đây là điểm cốt lõi của bài học: **không suy diễn quy tắc “incapable không callback” từ retransform sang redefine**.

## 5. `classBeingRedefined` cung cấp tín hiệu gì?

Từ Java 9, callback Java có thể override overload:

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Đây là **chữ ký tham chiếu**, không phải source của method có body. Các điểm quan trọng:

- `module`: module chứa class được định nghĩa/cập nhật.
- `loader`: class loader liên quan; có thể là `null` nếu bootstrap loader.
- `className`: tên nội bộ thường dùng dấu `/`, như `com/example/Target`; trong một số trường hợp có thể `null`.
- `classBeingRedefined`: **`null`** khi class đang được định nghĩa lần đầu; **khác `null`** khi cập nhật class đã tồn tại.
- `protectionDomain`: ngữ cảnh bảo vệ class nếu có.
- `classfileBuffer`: bytes đầu vào **của tầng này**; có thể đã được tầng trước chỉnh sửa.

**Không được suy luận `classBeingRedefined != null` chỉ có nghĩa redefine.** Cả `redefineClasses` **và** `retransformClasses` đều có class đang tồn tại. Callback không chứa một boolean độc lập để khẳng định loại thao tác. Trong bài lab, ta biết đây là redefine vì ứng dụng **chủ động gọi `redefineClasses`**, không phải vì đoạn `transform(...)` tự phân biệt được.

Mẫu log phù hợp:

```java
// Dùng trong callback transform(...):
String phase = classBeingRedefined == null ? "load" : "existing";
System.out.println("transform: " + label + " " + phase);
```

Nếu một agent cần phân biệt hai con đường, hãy ghi thông tin ở **tầng điều phối thao tác** (nơi gọi `redefineClasses`/`retransformClasses`) thay vì đặt tên nhánh `existing` là `"redefine"` một cách cứng nhắc.

## 6. Tiền điều kiện trước khi gọi `redefineClasses`

### 6.1. Capability của JVM và manifest agent

Khả năng redefine là capability tùy chọn của JVM/cấu hình agent. Hỏi:

```java
boolean supported = instrumentation.isRedefineClassesSupported();
```

Đối với startup Java agent, manifest yêu cầu:

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true

```

`Can-Redefine-Classes: true` là điều kiện từ manifest, nhưng bản thân JVM cũng phải hỗ trợ. Nếu `isRedefineClassesSupported()` là `false`, gọi `redefineClasses(...)` có thể ném `UnsupportedOperationException`. Không dùng `isRetransformClassesSupported()` thay cho câu hỏi này.

**Sự khác nhau của hai flag:**

| Flag / API | Vai trò |
| --- | --- |
| `Can-Redefine-Classes: true` | Yêu cầu capability redefine trong manifest agent |
| `isRedefineClassesSupported()` | Kiểm tra runtime có cho phép redefine |
| `Can-Retransform-Classes: true` | Yêu cầu capability retransform cho agent |
| `isRetransformClassesSupported()` | Kiểm tra runtime có cho phép retransform |
| `isModifiableClass(target)` | Hỏi JVM có thể thay đổi class cụ thể không |

Trong thí nghiệm muốn đăng ký **cả Java capable và incapable**, JAR phải yêu cầu **cả hai capability**. Nhưng nếu ứng dụng chỉ muốn redefine với transformer incapable, về nguyên tắc **không cần** yêu cầu retransform để minh chứng hành vi redefine.

### 6.2. Xác định đúng class đã nạp

`ClassDefinition` nhận một `Class<?>`, không chỉ chuỗi tên. Tên lớp giống nhau có thể xuất hiện trong **nhiều class loader**. Hai lớp tên `com.example.Plugin` nhưng đến từ hai loader khác nhau không phải một class runtime.

Trước khi redefine, ghi nhận/kiểm tra:

- `target.getName()`, `target.getClassLoader()`, `target.getModule()` khi cần.
- Class đã tồn tại trong JVM, không phải primitive hoặc array class.
- `instrumentation.isModifiableClass(target)` trả `true`.
- Bytes thay thế có **tên class phù hợp** với target.
- Class-file major version không vượt quá JVM đang chạy.
- Classfile bytes đúng bản đã review/hash, không phải bản debug/JAR cũ nằm ở nơi khác.

### 6.3. Giới hạn schema và cấu trúc

Redefinition thường dùng để thay **method bodies**, constant pool và một số attributes hợp lệ, nhưng không phải cơ chế thay class tùy ý. Các thay đổi như **thêm/xóa/đổi tên field hoặc method, đổi descriptor/signature phương thức theo nghĩa JVM, đổi method modifiers, thay supertype hoặc interface** và một số thuộc tính cấu trúc hiện đại có thể bị cấm. JVM có thể ném `UnsupportedOperationException` hoặc lỗi tương ứng nếu thay đổi vượt giới hạn.

Do vậy, muốn đổi phương thức từ:

```java
public String value() {
    return "OLD";
}
```

sang:

```java
public String value() {
    return "NEW";
}
```

là ví dụ phù hợp nếu **class schema giữ nguyên**. Nhưng đổi `public String value()` thành `public int value(int code)` là đổi chữ ký và không phải tình huống thay method body đơn giản. `redefineClasses` không tạo thêm một **class mới** trong class loader.

### 6.4. Kiểm tra bytes trước khi phát hành

Transformer chạy trước khi JVM verify/install. Nếu có thể, công cụ nên có một bước QA cho **bytes thay thế** và kiểm chứng cả **output cuối sau chuỗi** trong môi trường thử nghiệm. Trên JDK 17, có thể dùng `javap -v` để xem classfile, test bằng class loader riêng nơi thích hợp, hoặc thư viện bytecode khác; Java Class-File API chuẩn `java.lang.classfile` chỉ xuất hiện chính thức từ JDK 24, nên không nên đưa ví dụ ClassFile API JDK 24 vào chương trình cần chạy bằng JDK 17.

Ngay cả khi bytes đầu vào tự nó hợp lệ, một transformer trong chain có thể tạo bytes không hợp lệ. Vì vậy thành công của bước build/sinh file không thay thế được kết quả cuối của `redefineClasses`.

## 7. Lab Java 17+ chạy độc lập: transformer incapable vẫn nhận callback khi redefine

Thí nghiệm này có **hai phiên bản `Target` biên dịch riêng** với cùng class name và cùng schema; nội dung method khác nhau. Agent đăng ký Java capable **trước**, Java incapable **sau**. Từ đó chứng minh:

1. Khi `Target` được load lần đầu, callback **incapable** xảy ra trước capable.
2. Khi gọi **`redefineClasses`**, cả hai callback **vẫn xảy ra**, theo thứ tự incapable rồi capable.
3. Object `Target` đã tạo trước redefine vẫn tồn tại; lần gọi method mới sử dụng định nghĩa cập nhật và trả `"NEW"`.
4. Hai transformer chỉ **log và trả `null`**, nên đây là demo thứ tự/đường đi, không phải demo chèn bytes.

### 7.1. Cấu trúc thư mục

```text
redefinition-chain-demo/
├── agent.mf
├── agent-src/
│   └── RedefineAgent.java
├── app-src/
│   ├── Main.java
│   └── Target.java             // Phiên bản OLD
└── replacement-src/
    └── Target.java             // Phiên bản NEW
```

Sẽ có các thư mục `out/agent`, `out/app`, `out/replacement` được tạo khi compile. **Hai file `Target.java` ở hai source root khác nhau là chủ ý**; không compile chung hai file cùng tên vào một output directory.

### 7.2. File `app-src/Target.java`: bản class ban đầu

```java
public final class Target {
    public String value() {
        return "OLD";
    }
}
```

File này tạo class `Target` trong default package. Nó có constructor `public Target()` được compiler sinh tự động và một instance method `public String value()`. Trong bài lab chỉ thay method body của `value`; giữ class name, constructor, method descriptor, access flags và superclass như cũ.

### 7.3. File `replacement-src/Target.java`: bản thay thế

```java
public final class Target {
    public String value() {
        return "NEW";
    }
}
```

Hai phiên bản **cùng API** và khác duy nhất ở literal trả về của method. Khi biên dịch bằng cùng JDK, đây là case phù hợp để thử redefine method body. Không nạp `out/replacement/Target.class` trực tiếp vào system class loader; chương trình đọc nó thành `byte[]` rồi truyền qua `ClassDefinition`.

### 7.4. File `agent-src/RedefineAgent.java`: đăng ký transformer và gọi redefine

```java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;

        boolean redefine = inst.isRedefineClassesSupported();
        boolean retransform = inst.isRetransformClassesSupported();
        System.out.println("agent: redefine=" + redefine);
        System.out.println("agent: retransform=" + retransform);

        if (!redefine || !retransform) {
            throw new IllegalStateException(
                    "The demo requires both agent capabilities");
        }

        // Cố ý đăng ký capable TRƯỚC.
        inst.addTransformer(logger("capable"), true);

        // Dù đăng ký SAU, incapable thuộc nhóm Java chạy trước.
        inst.addTransformer(logger("incapable"), false);
        System.out.println(
                "agent: registered=capable-then-incapable");
    }

    private static ClassFileTransformer logger(String label) {
        return new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Chỉ quan sát lớp Target, tránh log các class JVM khác.
                if ("Target".equals(className)) {
                    String phase = classBeingRedefined == null
                            ? "load" : "existing";
                    System.out.println(
                            "transform: " + label + " " + phase);
                }

                // Không thay đổi bytes ở tầng hiện tại.
                return null;
            }
        };
    }

    public static void redefine(Class<?> target, Path replacement)
            throws Exception {

        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Agent did not initialize");
        }
        if (!inst.isRedefineClassesSupported()) {
            throw new IllegalStateException(
                    "Redefine capability is unavailable");
        }
        if (!inst.isModifiableClass(target)) {
            throw new UnmodifiableClassException(
                    "Target is not modifiable: " + target.getName());
        }

        byte[] newBytes = Files.readAllBytes(replacement);

        System.out.println("agent: redefine requested");
        inst.redefineClasses(new ClassDefinition(target, newBytes));
        System.out.println("agent: redefine succeeded");
    }
}
```

Giải thích:

- `premain` chạy khi dùng `-javaagent`; Java runtime chuyển vào `Instrumentation`.
- Đăng ký `logger("capable")` với `true` **trước**, nhưng JVM vẫn xử lý nhóm incapable trước trong callback cùng class.
- `ClassFileTransformer` chỉ in log nếu tên nội bộ đúng `Target`. Do lớp nằm trong default package nên tên không có dấu `/`; trong dự án thông thường dùng `com/example/Target`.
- Tên `existing` là chủ ý, vì `classBeingRedefined != null` xuất hiện với cả redefine và retransform.
- `redefine(...)` kiểm tra capability **và** khả năng sửa class cụ thể trước khi đọc bytes.
- `ClassDefinition(target, newBytes)` giữ một đối tượng class hiện hữu và dữ liệu từ file replacement.
- Sau lời gọi thành công, `agent: redefine succeeded` mới được in. Callback log trước đó **chưa** bảo đảm JVM đã áp dụng thành công; log success sau khi API return có ý nghĩa hơn.
- `return null` ở cả hai transformer khiến logic `OLD→NEW` đến từ **replacement class file**, không phải do transformer tự đổi literal.
- `volatile Instrumentation` giúp việc công bố reference rõ hơn trong demo; trong app thật agent còn phải kiểm soát state/lifecycle, tên class, class loader và các trạng thái lỗi khác.

### 7.5. File `app-src/Main.java`: nạp lớp cũ, redefine, gọi object cũ

```java
import java.lang.reflect.Method;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Main <replacement-class-file>");
        }

        System.out.println("app: loading");
        Class<?> targetClass = Class.forName("Target");
        Object instance =
                targetClass.getDeclaredConstructor().newInstance();
        Method value = targetClass.getMethod("value");

        System.out.println("app: before=" + value.invoke(instance));

        // Dùng class đã nạp; không định nghĩa một class Target khác.
        RedefineAgent.redefine(targetClass, Path.of(args[0]));

        // Gọi lại chính object và Method đã lấy trước redefine.
        System.out.println("app: after=" + value.invoke(instance));
    }
}
```

`Class.forName("Target")` đặt sau dòng `"app: loading"` để quan sát sự kiện load. Việc dùng reflection ở đây **không phải điều kiện của redefine**; nó giúp `Main` không tham chiếu tĩnh tới class `Target` trong thời điểm verify/load `Main`, và giúp chứng minh object cũ vẫn được dùng sau cập nhật.

Đoạn `Method` đã lấy trước redefine vẫn đại diện cho cùng method theo tên/descriptor. Sau thành công, lời gọi mới tới method đó nhìn thấy phần thân method cập nhật; đây là kết quả quan trọng về method redefinition, không phải bằng chứng constructor chạy lại.

### 7.6. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true

```

Bài lab yêu cầu **cả hai flag** vì muốn đăng ký **một capable transformer** và thử **redefine**. Nếu chỉ muốn redefine với `canRetransform=false`, capability retransform không phải tiền điều kiện cơ bản. Đảm bảo manifest có newline và dòng trống kết thúc main section.

### 7.7. Biên dịch trên Bash (Linux/macOS/Git Bash)

Dùng **JDK 17+** và thực hiện lệnh tại thư mục `redefinition-chain-demo`:

```bash
mkdir -p out/agent out/app out/replacement

javac -encoding UTF-8 -d out/agent \
    agent-src/RedefineAgent.java

javac -encoding UTF-8 -cp out/agent -d out/app \
    app-src/Main.java app-src/Target.java

javac -encoding UTF-8 -d out/replacement \
    replacement-src/Target.java

jar --create --file out/redefine-agent.jar \
    --manifest agent.mf -C out/agent .

java -javaagent:out/redefine-agent.jar \
    -cp out/agent:out/app \
    Main out/replacement/Target.class
```

Lưu ý:

- Cần compile agent **trước** vì `Main` gọi class `RedefineAgent`.
- Compile `replacement-src/Target.java` **riêng** để không thay `out/app/Target.class` bản OLD.
- `-cp out/agent:out/app` dùng dấu hai chấm trên Unix-like systems.
- `-javaagent` nạp agent trước chương trình chính; JVM sẽ gọi `premain`.
- Đường dẫn `out/replacement/Target.class` truyền vào `Main` là file bytes **mới**.

### 7.8. Biên dịch trên PowerShell (Windows)

```powershell
New-Item -ItemType Directory -Force `
    -Path out/agent, out/app, out/replacement | Out-Null

javac -encoding UTF-8 -d out/agent `
    agent-src/RedefineAgent.java

javac -encoding UTF-8 -cp out/agent -d out/app `
    app-src/Main.java app-src/Target.java

javac -encoding UTF-8 -d out/replacement `
    replacement-src/Target.java

jar --create --file out/redefine-agent.jar `
    --manifest agent.mf -C out/agent .

java -javaagent:out/redefine-agent.jar `
    -cp "out/agent;out/app" `
    Main out/replacement/Target.class
```

PowerShell dùng backtick làm ký tự nối dòng, còn classpath Windows dùng `;`. Không ghép hai cú pháp thành một shell script chung vì có thể làm lệnh `javac`/`java` hiểu sai tham số.

### 7.9. Stdout kỳ vọng khi JVM hỗ trợ cả hai capability

Với HotSpot/OpenJDK JDK 17+ thông dụng, agent manifest hợp lệ, file replacement được biên dịch chính xác và không có agent khác ảnh hưởng class, output dự kiến:

```text
agent: redefine=true
agent: retransform=true
agent: registered=capable-then-incapable
app: loading
transform: incapable load
transform: capable load
app: before=OLD
agent: redefine requested
transform: incapable existing
transform: capable existing
agent: redefine succeeded
app: after=NEW
```

Đọc kết quả từng bước:

1. Agent yêu cầu và JVM thông báo **hai capability khả dụng**.
2. Capable được **đăng ký trước** incapable.
3. Khi `Target` load lần đầu, **incapable chạy trước capable** theo thứ tự nhóm.
4. Khi `redefineClasses` được gọi, **cả hai transformer đều chạy lại**. Đây là điều bài học cần chứng minh.
5. `existing` không tự phân biệt redefine/retransform; ta biết đây là redefine do `agent: redefine requested` và code đang gọi API tương ứng.
6. Sau khi API thành công, **object cũ** gọi `value()` và nhận `"NEW"`.

Nếu JVM không hỗ trợ capability, agent **không** in đầy đủ output trên; `premain` ném lỗi và chương trình có thể không khởi động. Nếu bytes thay thế sai class name/schema, `redefineClasses` có thể ném lỗi sau khi callback log xuất hiện; không được báo `"succeeded"` khi API thực tế thất bại.

**Giới hạn thí nghiệm:** Hai transformer trả `null`, vì vậy bài lab kiểm tra **tham gia callback và thứ tự**, không chứng minh chúng tạo thêm bytes mới. Muốn chứng minh byte-level chaining, hãy dùng thư viện tạo classfile hợp lệ như ASM/Byte Buddy, bảo đảm cùng schema, ghi hash/metadata từng tầng và chạy verifier/runtime test. Không sửa byte thô tùy ý rồi xem đó là production transformer.

## 8. Minh họa bytes thực sự đi qua các tầng

Giả sử có một agent A Java incapable chèn probe logging, agent B native incapable chèn marker, agent C Java capable chèn tracing và agent D native capable chèn sampling. Chúng đều áp dụng cho class `Target`.

### Lần load ban đầu

```text
Target OLD .class
    → A: add logging OLD
    → B: add marker OLD
    → C: add tracing OLD
    → D: add sample OLD
    → installed definition OLD + probes
```

### Lần redefine với `Target NEW .class`

```text
Target NEW .class (bytes trong ClassDefinition)
    → A: CALLBACK MỚI, tạo logging trên NEW
    → B: CALLBACK MỚI, tạo marker trên NEW
    → C: CALLBACK MỚI, tạo tracing trên NEW
    → D: CALLBACK MỚI, tạo sample trên NEW
    → verify/install NEW + probes
```

**Đây là tình huống giả định** minh họa quy tắc JVM, không phải output của bài lab ở mục 7. Nếu A/B không được lập trình để xử lý class mới đúng cách, chúng có thể tạo bytes hỏng, trùng probe hoặc chèn vào method không còn vị trí cũ. Vì vậy không thể dựa vào việc plugin trước đó instrument được bản OLD để kết luận nó sẽ instrument bản NEW thành công.

### Lần retransform sau redefine

```text
Initial bytes của lần redefine NEW gần nhất
    → reuse output A từ lần redefine; KHÔNG callback A
    → reuse output B từ lần redefine; KHÔNG callback B
    → C: CALLBACK MỚI
    → D: CALLBACK MỚI
    → verify/install
```

Việc này khác gọi A/B lại. Lần retransform sau khi redefine dựa trên **định nghĩa hiện tại**, không nhất thiết đi ngược về bytes OLD đầu tiên. Java capable C và native capable D có thể dùng cấu hình probe mới; A/B vẫn giữ phần output incapable từ lần redefine.

### Quan hệ giữa “bytes gốc mới” và “output không đổi”

Nếu một transformer incapable trả `null` trong lần redefine, phần đóng góp của nó không có bytes mới để tái áp dụng sau này, nhưng quy tắc **không callback khi retransform** vẫn đúng. Nếu transformer incapable trả một mảng thay thế trong redefine, chính đóng góp đó được giữ lại theo cơ chế retransformation tương ứng.

Đừng gộp ba khái niệm:

- **Callback được gọi** — thuật toán transformer chạy.
- **Bytes bị thay đổi** — transformer trả mảng khác `null` và hợp lệ.
- **Class được cập nhật thành công** — JVM đã verify/install định nghĩa mới, API trả bình thường.

Một callback xuất hiện trong log chỉ chứng minh **bước 1**, không bảo đảm bước 2 hoặc 3.

## 9. Cơ chế lỗi khi các transformer đã đăng ký vẫn tham gia redefine

### 9.1. Exception trong một Java transformer không tự chặn toàn chain

Theo Javadoc, nếu Java `ClassFileTransformer.transform(...)` ném exception, JVM vẫn có thể tiếp tục gọi các transformer khác. Tầng đó được xử lý như trường hợp **không tạo biến đổi** (tương tự `return null`). Vì vậy:

```java
// Chỉ là code minh họa bên trong transform(...).
if (className != null && className.equals("bad/Target")) {
    throw new IllegalStateException("Agent transform failed");
}
```

Đoạn code không phải phương án fail-closed chắc chắn. Nếu một agent coi instrumentation là bắt buộc, phải có cơ chế chính sách rõ ràng để phát hiện/ghi nhận lỗi và ngăn triển khai hoặc vô hiệu hóa chức năng theo yêu cầu; không chỉ ném runtime exception từ callback rồi giả định JVM sẽ hủy định nghĩa.

### 9.2. Bytes trả về không hợp lệ

Nếu transformer trả mảng bytes không thể định nghĩa hợp lệ, `redefineClasses` có thể thất bại tại bước kiểm chứng/cài đặt sau chain. Lỗi có thể là `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError`, `UnsupportedOperationException` hoặc lỗi liên kết phù hợp. **Tất cả callback có thể đã chạy** trước khi lỗi xuất hiện.

Do đó hãy log riêng:

```text
transform invoked
transform returned bytes / returned null
redefineClasses returned normally / threw
runtime behavior after redefine
```

Không log `"class updated"` ngay trong callback vì JVM chưa áp dụng xong.

### 9.3. Capability, class không thể sửa và schema khác

- `isRedefineClassesSupported()==false`: cấu hình JVM không cho redefine.
- `isModifiableClass(target)==false`: class cụ thể không thể sửa theo cơ chế đó.
- `target` không cùng class name với bytes mới: có thể gây lỗi `NoClassDefFoundError` hoặc lỗi tương ứng khi JVM kiểm tra.
- Thêm field/method, đổi descriptor/supertype và cấu trúc bị cấm: redefinition có thể bị từ chối.
- Bytecode có type/stack-map/branch không hợp lệ: verifier có thể từ chối output.
- Type helper của agent không có trong module/class loader đúng: có thể gặp `NoClassDefFoundError`, `IllegalAccessError` hoặc các linkage errors lúc dùng code.

Khả năng redefine của target không bảo đảm các transformer trong chain có thể giải quyết mọi vấn đề module graph, bootstrap class loader hoặc hệ thống class-loading.

### 9.4. Tính nguyên tử của yêu cầu nhiều class

`redefineClasses(ClassDefinition...)` có thể nhận **nhiều class definitions** trong một yêu cầu. JDK yêu cầu cập nhật theo ngữ nghĩa một tập để hỗ trợ thay đổi liên quan giữa các class. Nếu thao tác thất bại, **không class nào trong tập được redefine thành công** theo hợp đồng API. Tuy nhiên các callback có thể đã chạy và có **side effects trong code agent** như log, counter hoặc cache update.

Vì vậy:

- Không tăng `redefinitions_succeeded_total` ngay trong callback transformer.
- Chỉ coi thao tác thành công sau khi `redefineClasses(...)` trả bình thường.
- Nếu công cụ cần lưu metadata về version hiện hành, cập nhật state sau kết quả API, không phải chỉ sau khi sinh bytecode.
- Nếu nhiều class được redefine một lần, test các liên kết giữa chúng và tránh tách chúng thành các yêu cầu tùy tiện làm lộ trạng thái trung gian.

## 10. Side effects của việc redefine đối với object và method đang chạy

Redefinition có **giới hạn vòng đời** quan trọng:

- Những **instance cũ** không bị thay thành object khác; bộ nhớ và field state của chúng tiếp tục tồn tại.
- **Static variables** giữ giá trị hiện tại; JVM không chạy lại class initializer chỉ vì redefine.
- Nếu một method đã có **active stack frames**, frame đang chạy có thể tiếp tục dùng bytecode phiên bản cũ.
- Những lần gọi method mới sau khi cài đặt định nghĩa thành công dùng phiên bản mới.
- Không có bảo đảm rằng một transformer incapable “giữ mã OLD” từ lần load khi redefine thành công bằng bytes NEW; với redefine, nó nhận **input mới** và có callback mới.

Ví dụ minh họa:

```text
Thread A đã vào Target.value() OLD trước khi redefine.
Thread B yêu cầu redefine Target bằng bytes NEW.
Thread A tiếp tục hoàn thành frame OLD theo quy tắc JVM.
Một lần gọi Target.value() mới sau redefine dùng body NEW.
```

Không dùng ví dụ này để kết luận ứng dụng có thể đổi cấu trúc field/method tùy ý. Bảo toàn đối tượng chỉ có ý nghĩa trong giới hạn redefinition được phép.

### Khi có active traffic

Một lần redefine giữa nhiều thread có thể ảnh hưởng latency, safepoint/runtime coordination và kết quả quan sát ở các thời điểm chuyển tiếp. Trong hệ thống production cần:

1. Xác định khu vực thay đổi đủ nhỏ, có canary/staging.
2. Đặt hạn mức và tránh redefinition thường xuyên trên quá nhiều class.
3. Đo overhead trước/sau và thử các active-call paths.
4. Phối hợp với những agent khác đang instrument class tương tự.
5. Có phương án quay lại phiên bản method body cũ bằng một **lần redefine mới hợp lệ** nếu cần, không giả định `removeTransformer` là nút undo.

## 11. Khi nhiều Java agent cùng đăng ký transformer

Một process có thể nhận nhiều `-javaagent` hoặc agent được nạp bằng phương thức được JVM cho phép. Mỗi agent có thể đăng ký nhiều transformer. JVM quản lý chuỗi theo bốn nhóm; không có một “hợp đồng” rằng transformer của agent C luôn chạy cuối trong mọi JVM.

Một số nguyên tắc để tương thích:

**Một — lọc class chính xác.**

```java
if (!"com/example/OrderService".equals(className)) {
    return null;
}
```

Không instrument helper của chính agent, logging/exporter hoặc thư viện tạo bytecode nếu không chủ động quản lý recursion/reentrancy. Khi redefinition xảy ra, callback có thể chạy trong điều kiện rất nhạy cảm về class loading; việc phụ thuộc vào những class chưa nạp có thể gây vòng lặp.

**Hai — coi `classfileBuffer` là read-only.**

Tạo một mảng `byte[]` **mới** khi cần thay đổi. Không ghi trực tiếp lên mảng input rồi trả `null`, vì điều đó phá hợp đồng chain và có thể làm hỏng giả định của agent phía sau.

**Ba — không suy đoán class file version hoặc source layout.**

Bytes input có thể đến từ `ClassDefinition` khác bản build ban đầu. Dùng parser/bytecode library phù hợp, hiểu method descriptors, frames, constant pool, exception table, và kiểm tra class major version.

**Bốn — idempotence và probe duplication.**

Nếu cùng một logic có thể được chèn qua lần load, redefine nhiều lần, và sau đó retransform, agent cần biết chỗ nào đã có probe. Việc tự chèn wrapper mỗi khi thấy method name có thể làm probe lồng nhau hoặc sinh bytes vượt giới hạn. Tuy nhiên **không** được giả định mọi lần redefine bắt đầu từ bytes đã qua probe cũ; caller có thể cung cấp class file sạch hoặc đã instrument. Nên dùng marker/schema rõ ràng và kiểm chứng theo input hiện tại.

**Năm — log đúng tầng.**

Log callback cho biết thứ tự, nhưng không nói output cuối có hợp lệ hay không. Gắn operation id/target class/loader/transformer group vào log chẩn đoán và log kết quả API ở tầng điều phối; hạn chế log dữ liệu nhạy cảm hoặc toàn bộ bytes.

### Có thể dùng transformer để xử lý dữ liệu redefine mà không thay class?

Có. Lab dùng transformer **quan sát** rồi trả `null`. Nếu công cụ chỉ muốn đo thời điểm redefine hoặc kiểm tra thông tin về class, nó vẫn có callback, nhưng phải tránh làm việc nặng trong hot path và không nên coi callback là sự kiện cập nhật đã thành công.

## 12. `removeTransformer` không hoàn nguyên những gì đã áp dụng

`Instrumentation.removeTransformer(transformer)` ngừng đăng ký transformer cho những lần xử lý sau, nhưng:

- Nó **không tự trả class đang chạy về bytes trước transform**.
- Class-loading/redefinition có thể diễn ra song song; callback đã tiến hành có thể còn đến sau removal.
- Với redefinition tiếp theo, chain chỉ bao gồm những transformer được áp dụng ở thời điểm xử lý; bytes caller đưa vào quyết định baseline mới.
- Nếu transformer đã tạo phụ thuộc vào helper class, việc gỡ agent/helper không có nghĩa lớp đã instrument ngừng gọi helper.

Một chiến lược rollback thực tế có thể là **redefine lại** bằng class bytes đã biết là hợp lệ, trong cùng giới hạn schema, rồi xác nhận không còn instrumentation không mong muốn. Khi có nhiều agent không phối hợp, đôi khi **restart JVM** với bộ agent thống nhất là cách an toàn hơn.

## 13. Phân biệt `redefineClasses` và `retransformClasses` khi debug

| Dấu hiệu | `redefineClasses` | `retransformClasses` |
| --- | --- | --- |
| Caller truyền bytes mới? | **Có**, qua `ClassDefinition` | **Không**, chỉ truyền `Class<?>` |
| Java `canRetransform=false` callback? | **Có** | **Không**, reuse output cũ |
| Java `canRetransform=true` callback? | **Có** | **Có** |
| Native incapable `ClassFileLoadHook`? | Có callback khi áp dụng | Không callback, reuse output |
| Native capable `ClassFileLoadHook`? | Có callback khi áp dụng | Có callback |
| Input cơ sở | Bytes từ `getDefinitionClassFile()` | Initial bytes liên quan class định nghĩa hiện tại |
| Sau khi áp dụng thành công | JVM dùng định nghĩa mới cho các lần invoke mới | Tương tự, nhưng pipeline chuẩn bị bytes khác |
| Ràng buộc cấu trúc | Giới hạn schema/redefinition | Giới hạn schema/retransformation |
| Các active frames | Có thể tiếp tục phiên bản method cũ | Có thể tiếp tục phiên bản method cũ |
| Class initializer | Không tự chạy lại | Không tự chạy lại |

Một log có `classBeingRedefined != null` nhưng thiếu ngữ cảnh caller **không đủ** để điền vào cột tương ứng. Muốn debug chuẩn, hãy nhìn lời gọi điều phối, manifest/capabilities, thứ tự callback, input hash và kết quả API.

## 14. Checklist QA trước khi đưa redefine vào công cụ instrumentation

1. **Đúng JVM/class:** xác định `Class<?>` runtime, class loader, module và class-file version cần cập nhật.
2. **Đúng capability:** `isRedefineClassesSupported()` và `isModifiableClass(target)`; không nhầm retransform capability.
3. **Đúng bytes:** `ClassDefinition` mang đúng class name/schema, file từ nguồn tin cậy và đúng version.
4. **Có transformer nào đang đăng ký?** Liệt kê Java incapable/capable, native JVMTI nếu có và thứ tự trong mỗi nhóm.
5. **Input đúng semantics:** với redefine, transformer đầu nhận bytes caller đưa vào, không tự động nhận bản đã biến đổi của lần load cũ.
6. **Chaining đúng:** một tầng trả `null` thì giữ bytes hiện tại; tầng sau nhận output tầng trước.
7. **Không sửa input tại chỗ:** nếu tạo bytecode mới phải tạo bytes hợp lệ và giữ stack maps/attributes cần thiết.
8. **Có đủ kiểm tra class structure:** không làm sai method descriptors, superclass, fields, modifiers và metadata bị giới hạn.
9. **Không instrument chính agent:** tránh recursion, class loading và helper không thể resolve.
10. **Kiểm tra errors:** không gán ý nghĩa success cho callback; quan sát return/exception từ `redefineClasses`.
11. **Kết quả runtime:** test method gọi mới sau redefine và object hiện hữu; test active-call path khi có thể.
12. **Coexistence:** thử trong môi trường có đủ các Java/native agent thật; không dựa vào một agent duy nhất trong lab.
13. **Bảo toàn metadata:** annotation, exception table, code attributes, record/nest/sealed metadata phải phù hợp với giới hạn.
14. **Rollback:** có bản bytes cũ hợp lệ và chiến lược cập nhật lại/khởi động lại nếu sự cố.
15. **Performance:** đo latency, safepoint pauses, allocations, memory overhead và tác động khi redefinition nhiều class.
16. **Observability:** log class, loader, target version, tên transform và result status; không dump secrets/bytecode rộng khắp.

### Mẫu log có thể chẩn đoán chính xác

```text
requestId=<stable-operation-id>
operation=redefineClasses
target=<binary-name>
loader=<loader-identity>
replacementHash=<sha256>
transformerGroup=<java-incapable|native-incapable|java-capable|native-capable>
transformResult=<unchanged|new-bytes|error>
apiResult=<success|failure>
```

Đây là **schema minh họa**, không phải output chương trình. Không nên dùng raw `ClassLoader.toString()` hoặc đường dẫn chứa bí mật làm metric labels có cardinality cao; phần lớn field phù hợp **debug log giới hạn**, không phải counter dimension.

## 15. Những hiểu nhầm thường gặp

**Hiểu nhầm 1: “Transformer `canRetransform=false` không được gọi lúc redefine.”**  
Sai. Nó nhận callback khi redefine. Chỉ trong **retransform**, JVM bỏ callback incapable và replay output trước.

**Hiểu nhầm 2: “Redefine chỉ áp dụng đúng mảng bytes tôi truyền, không qua agent khác.”**  
Sai. Những transformer đã đăng ký vẫn được áp dụng theo thứ tự; output cuối có thể khác bytes truyền vào `ClassDefinition`.

**Hiểu nhầm 3: “Capable transformer luôn có ưu tiên trước incapable.”**  
Sai. Nhóm Java incapable chạy trước nhóm native incapable, sau đó Java capable và native capable. Capability chỉ định nhóm, không chỉ định thắng chung theo thời gian đăng ký.

**Hiểu nhầm 4: “`classBeingRedefined != null` đủ khẳng định redefine.”**  
Sai. Retransformation cũng cập nhật class hiện hữu; cần biết API được caller gọi.

**Hiểu nhầm 5: “Transformer ném exception thì toàn bộ redefine chắc chắn hủy.”**  
Không đúng. Java `ClassFileTransformer` được đặc tả để những transformer khác tiếp tục xử lý; exception trong callback tương đương không đóng góp bytes ở tầng đó. Lỗi class final hoặc lỗi API là chuyện riêng.

**Hiểu nhầm 6: “Nếu transformer đã in log thì redefine đã thành công.”**  
Sai. JVM còn verify/install bytes sau chain và có thể từ chối. Cần chờ `redefineClasses` trả bình thường.

**Hiểu nhầm 7: “Redefine chạy lại constructor hoặc reset static.”**  
Sai. Object và static state tiếp tục tồn tại; class initializer không tự chạy lại.

**Hiểu nhầm 8: “Đang chạy method cũ sẽ lập tức đổi lệnh ở giữa method.”**  
Sai. Active frames có thể tiếp tục thực thi bytecode cũ; lần gọi mới dùng phiên bản mới.

**Hiểu nhầm 9: “Đăng ký thêm transformer sau khi class load sẽ tự gọi lại class load.”**  
Sai. Chỉ các **yêu cầu cập nhật** hoặc class definition mới sẽ kích hoạt callback phù hợp; đăng ký không tự quay lại lịch sử.

**Hiểu nhầm 10: “Gỡ transformer sẽ tự khôi phục class cũ.”**  
Sai. `removeTransformer` không tự rollback class đã định nghĩa.

**Hiểu nhầm 11: “`return null` sẽ xóa output của transformer trước.”**  
Sai. Nó không thay đổi input bytes hiện tại của tầng đó.

**Hiểu nhầm 12: “Có thể thêm public method mới trong replacement vì `.class` parse hợp lệ.”**  
Không thể kết luận. Schema change có thể bị JVM từ chối trong redefine dù class file tự nó hợp lệ.

**Hiểu nhầm 13: “Hai class cùng tên nghĩa là redefine đúng lớp.”**  
Sai. Class identity liên quan defining class loader; phải dùng đúng `Class<?>` runtime.

**Hiểu nhầm 14: “Java agent và JVMTI native agent có cùng một mốc registration order chung.”**  
Sai. Thứ tự **nhóm** theo API cố định, còn thứ tự trong nhóm được đặc tả riêng.

## 16. Câu hỏi tự kiểm tra

**1.** Transformer Java được thêm bằng `addTransformer(t, false)` có callback khi gọi `redefineClasses` không?  
**Đáp:** Có, nếu vẫn đăng ký và thao tác áp dụng cho class. “Incapable” chỉ bỏ callback khi **retransform**.

**2.** Trong lần redefine, input callback đầu tiên là dữ liệu nào?  
**Đáp:** Class-file bytes mới trong `ClassDefinition.getDefinitionClassFile()` mà caller cung cấp, không mặc định là bytes cuối của lần load cũ.

**3.** Java capable đăng ký trước Java incapable. Khi redefine, ai chạy trước?  
**Đáp:** Java incapable, vì thuộc nhóm 1; Java capable thuộc nhóm 3.

**4.** Nếu transformer capable trả `null`, có loại bỏ output của transformer incapable đã chạy trước không?  
**Đáp:** Không. Bytes hiện hành đi tiếp nguyên trạng.

**5.** `classBeingRedefined != null` có phân biệt được redefine với retransform không?  
**Đáp:** Không. Cả hai cập nhật class đang tồn tại.

**6.** Tại sao bài lab yêu cầu cả `Can-Redefine-Classes` và `Can-Retransform-Classes`?  
**Đáp:** Lab **gọi redefine** và còn **đăng ký Java capable transformer**. Chỉ làm redefine với incapable không nhất thiết yêu cầu capability retransform.

**7.** Nếu bytes replacement đổi method signature, JVM có buộc phải nhận không?  
**Đáp:** Không. Redefinition có giới hạn schema, cho nên class bytes hợp lệ khi load mới chưa chắc hợp lệ để thay class đã load.

**8.** `redefineClasses` trả thành công thì object cũ có bị thay thế không?  
**Đáp:** Không. Instance cũ vẫn còn; những lời gọi method mới dùng định nghĩa mới.

**9.** Nếu callback log rồi `redefineClasses` ném lỗi, có thể cập nhật counter `redefinitions_succeeded_total` không?  
**Đáp:** Không. Callback không phải xác nhận install thành công; chỉ tăng thành công sau khi API return bình thường.

**10.** Sau một lần redefine NEW, lần retransform kế tiếp tái dùng output incapable của OLD hay NEW?  
**Đáp:** Theo hợp đồng, tái dùng kết quả incapable của **lần load/redefine gần nhất** tương ứng định nghĩa hiện tại — ở đây là lần redefine NEW.

**11.** Vì sao phải filter className trong transformer?  
**Đáp:** Tránh xử lý toàn bộ class JVM, hạn chế overhead và recursion, bảo đảm không làm hỏng helper, class loader hoặc agent infrastructure.

**12.** Nếu thay một class trong set nhiều class và thao tác thất bại giữa chừng, trạng thái class update theo API là gì?  
**Đáp:** Không class nào trong yêu cầu được cài định nghĩa mới thành công; nhưng các callback/log side effects đã chạy không tự rollback.

## 17. Tài liệu tham khảo chính thức

- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer tham gia class load, **redefine** và **retransform**; thứ tự bốn nhóm, `classfileBuffer`, `null` và exception.
- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `redefineClasses`, `retransformClasses`, `isRedefineClassesSupported`, `isModifiableClass`, khả năng áp dụng định nghĩa mới.
- [JDK 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cặp `Class<?>` và class-file bytes thay thế, `getDefinitionClassFile`.
- [JDK 17 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR manifest, `premain` và runtime capability.
- [JDK 17 — JVM Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): `ClassFileLoadHook`, `RedefineClasses` và hạn chế class schema.

**Ghi nhớ:** Khi `redefineClasses` được gọi, dữ liệu **trong `ClassDefinition` vẫn đi qua các transformer đang đăng ký** — kể cả transformer Java `canRetransform=false` và những JVMTI hook phù hợp. Chỉ khi **retransform** các transformer incapable mới không được gọi lại và output cũ của chúng được replay. Kiểm tra đúng capability, schema, input bytes, chain và kết quả API trước khi kết luận class đã được cập nhật.