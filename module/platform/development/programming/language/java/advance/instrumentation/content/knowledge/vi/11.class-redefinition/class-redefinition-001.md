# `redefineClasses`: thay định nghĩa lớp bằng bytecode được cung cấp qua `ClassDefinition`

## 1. Mục tiêu và bối cảnh

Java Instrumentation không chỉ can thiệp vào class lúc JVM nạp lần đầu. Với một JVM có hỗ trợ và agent đã yêu cầu capability thích hợp, agent có thể **thay định nghĩa của class đã được nạp** bằng class file bytes mới do chính agent cung cấp:

```java
instrumentation.redefineClasses(
        new ClassDefinition(Target.class, replacementClassFileBytes));
```

Hai ý quan trọng nhất của bài học:

1. **`ClassDefinition` là cặp `Class<?>` đích và `byte[]` chứa *toàn bộ* class file mới**, không phải cặp tên file/JAR, Java source, một đoạn mã phương thức hay một “patch” tùy ý.
2. **`Instrumentation.redefineClasses(...)` là lời yêu cầu JVM cài định nghĩa mới cho class *đã tồn tại***. Nó dùng bytes được cung cấp, có kiểm tra hợp lệ và ràng buộc về cấu trúc; không tự đọc lại `.java` hoặc tìm file `.class` mới nhất trên classpath.

Điều này khác việc load một class có tên mới. Nếu `Target` đã được định nghĩa bởi một class loader, `redefineClasses` giữ **cùng class identity**, các object đang sống và trạng thái runtime thích hợp; chỉ các phần của định nghĩa mà JVM cho phép mới được cập nhật.

Một số tình huống sử dụng: debugger “fix and continue”, thay thân phương thức lúc ứng dụng đang chạy, công cụ quan sát cần cập nhật bytecode đã được biên dịch sẵn hoặc một pipeline agent chủ động tạo bytes rồi chuyển vào JVM.

**Phiên bản:** Ví dụ dùng **Java 17+** và API chuẩn `java.lang.instrument`. Redefinition là **optional capability** của JVM, không nên suy ra từ số phiên bản JDK rằng mọi runtime đều cấp. Hãy kiểm tra trước khi thao tác.

## 2. API chính xác: `ClassDefinition` và `Instrumentation.redefineClasses`

### 2.1. `ClassDefinition` chứa gì?

`ClassDefinition` thuộc package `java.lang.instrument`:

```java
public final class ClassDefinition {
    public ClassDefinition(Class<?> theClass, byte[] theClassFile);
    public Class<?> getDefinitionClass();
    public byte[] getDefinitionClassFile();
}
```

Đây là mô tả chữ ký rút gọn, **không phải mã nguồn class độc lập**. Ý nghĩa:

- `theClass`: **đúng đối tượng `Class<?>` của class đã nạp** mà bạn muốn redefine. Cùng binary name trong hai class loader khác nhau có thể là hai class identity khác nhau.
- `theClassFile`: một mảng `byte[]` chứa **class file hoàn chỉnh** có cấu trúc JVM class file (bắt đầu bằng magic `CAFEBABE`, constant pool, methods, attributes...), không phải bytecode riêng của một method.
- Constructor **không copy mảng bytes**, chỉ giữ tham chiếu. Nếu chương trình khác sửa mảng sau khi tạo `ClassDefinition`, nội dung định nghĩa có thể không còn đúng dự kiến. Hãy coi bytes là **immutable trong suốt lời gọi**.
- Cả đối tượng class lẫn mảng không được `null`; constructor ném `NullPointerException` khi thiếu.
- `getDefinitionClass()` và `getDefinitionClassFile()` trả về hai phần đã gắn với nhau.

Vì sao không chỉ truyền tên lớp? **Class identity trong JVM được xác định bởi tên và defining class loader**. `Class<?>` loại bỏ nhầm lẫn khi cùng tên có trong nhiều plugin, application loader, custom loader hoặc module layer.

### 2.2. `redefineClasses` làm gì?

API Java SE 17:

```java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
```

Phương thức nhận **varargs**: một hoặc nhiều `ClassDefinition`. JVM thay định nghĩa cho đúng những class được chỉ định bằng bytes tương ứng, sau khi áp dụng transformer và xác thực những điều kiện cần thiết.

`ClassNotFoundException` vẫn tồn tại trong chữ ký **vì tương thích API**; Javadoc Java 17 nói phương thức này **không thực sự ném** exception đó. Trong ví dụ đơn giản có thể dùng `throws Exception` để tránh che mất lỗi của ví dụ; production nên phân loại các lỗi thực tế khác như `UnmodifiableClassException`, `UnsupportedOperationException` và các `LinkageError`.

Lời gọi **`redefineClasses()` với mảng rỗng** không thay đổi gì. Khi đưa nhiều `ClassDefinition` vào một lượt, API cho phép thay đổi các class liên quan với nhau như một tập; **nếu lời gọi ném exception, không class nào trong tập được redefine**.

### 2.3. Những gì agent phải tự cung cấp

`redefineClasses` **không** tự:

- Tìm hoặc biên dịch file `.java` vừa được sửa;
- Đọc file `.class` trong thư mục build mới nhất;
- Quét classpath và chọn class cùng tên;
- Tự sinh bytes mới từ body hiện tại;
- Bật capability khi manifest thiếu;
- Cho phép thay mọi modifier, field, method hoặc quan hệ kế thừa.

Agent phải nhận/tạo **full replacement class-file bytes** (ví dụ qua `Files.readAllBytes`, ASM, Byte Buddy hoặc Class-File API trên JDK phù hợp), kiểm tra target identity và gọi API rõ ràng.

## 3. Capability: hai điều kiện tách biệt

### 3.1. Manifest của agent JAR

Với agent được đưa vào JVM bằng `-javaagent`, manifest cần khai báo:

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true

```

- `Premain-Class` chỉ entry point của agent chạy lúc JVM khởi động.
- `Can-Redefine-Classes: true` thông báo agent **cần** khả năng redefine.
- Thuộc tính này nằm ở **main section của `META-INF/MANIFEST.MF` trong agent JAR thực sự được JVM load**.
- Nếu thiếu, đặt `false` hoặc có giá trị khác `true` (không phân biệt hoa/thường), mặc định khả năng được yêu cầu là **`false`**.
- Agent khởi động theo dynamic attach dùng `Agent-Class`; requirement về `Can-Redefine-Classes` vẫn cần được xem xét ở JAR được nạp.

**Không nhầm** `Can-Redefine-Classes` với `Can-Retransform-Classes`. Hai khả năng là **độc lập**. Có thể yêu cầu cả hai, nhưng chỉ bật retransformation không thay thế được quyền redefine.

### 3.2. JVM có thực sự hỗ trợ không?

```java
boolean supported =
        instrumentation.isRedefineClassesSupported();
```

Đặc tả yêu cầu capability được hỗ trợ khi:

```text
Agent manifest yêu cầu Can-Redefine-Classes: true
                         VÀ
JVM hiện tại cung cấp khả năng redefine tương ứng
                         |
                         v
        isRedefineClassesSupported() == true
```

Kết quả không thay đổi trong cùng một lần khởi tạo JVM. Nếu `false`, đừng gọi `redefineClasses` rồi hy vọng JVM tự bật; nó có thể ném `UnsupportedOperationException`.

Cũng cần kiểm tra class cụ thể:

```java
boolean modifiable = instrumentation.isModifiableClass(Target.class);
```

`isModifiableClass` là **điều kiện riêng**. Primitive và array types luôn không modifiable; một số class đặc biệt có thể bị runtime giới hạn. Giá trị `true` **không cam kết mọi thay đổi class file đều hợp lệ**.

**Các kiểm tra gác cổng:**

```java
if (!instrumentation.isRedefineClassesSupported()) {
    // Tắt chức năng redefine hoặc chọn fallback.
} else if (!instrumentation.isModifiableClass(Target.class)) {
    // Lớp đích không được sửa trong runtime này.
} else {
    // Có thể thử redefine với bytes hợp lệ, đúng class identity.
}
```

Đây là đoạn **minh họa**; biến `instrumentation` và `Target` cần được cung cấp trong agent thực tế.

## 4. Redefinition diễn ra thế nào?

```text
JVM đang chạy
  |
  +-- Class Target đã được nạp, có Class<?> identity
  |
  +-- Agent nhận bản .class mới (byte[] từ file/build/transform)
         |
         v
       new ClassDefinition(Target.class, replacementBytes)
         |
         v
       instrumentation.redefineClasses(...)
         |
         +--> JVM chuyển bytes qua các ClassFileTransformer
         |    đã đăng ký cho đường redefine (nếu có)
         |
         +--> kiểm tra tên, version, schema, modifier, frames,
         |    liên kết, giới hạn JVM/JVMTI
         |
         +--> hợp lệ: cài definition mới cho Target
         |       lời gọi mới -> body mới
         |
         +--> lỗi: ném exception/error
                 không cài đặt thay đổi của tập redefine
```

Có **hai lớp xử lý** cần phân biệt: `ClassDefinition` mang bytes agent yêu cầu; nếu đã đăng ký `ClassFileTransformer`, JVM vẫn có thể chuyển bytes đó qua chuỗi transformer **trước khi cài định nghĩa mới**. Vì vậy “dùng bytes do agent cung cấp” không có nghĩa **bỏ qua mọi transformer**.

Theo Javadoc của `Instrumentation.addTransformer`, transformer đã đăng ký được gọi khi class được **load và redefine**; tham số `canRetransform` quyết định hành vi trên **retransformation**, không phải quyền được gọi ở redefine.

Khi `ClassFileTransformer.transform(...)` nhận callback redefine:

- `classBeingRedefined` là đối tượng `Class<?>` đích, không phải `null` như khi load mới;
- `className` là internal name dạng `demo/Service`;
- `loader` là defining class loader của target, có thể `null` cho bootstrap;
- `classfileBuffer` là bytes ở bước hiện tại trong chuỗi transformer, **không được sửa trực tiếp mảng đầu vào**;
- Transformer có thể trả mảng byte mới hợp lệ hoặc `null` để không biến đổi.

Đừng nhầm `return null` của transformer (không sửa bytes) với việc `ClassDefinition` được phép chứa mảng byte `null` (không được).

## 5. Đâu là giới hạn thay định nghĩa?

Java Redefinition không phải **hot swap tùy ý mọi thành phần**. Theo JVM TI `RedefineClasses` và giới hạn được Javadoc Java 17 tham chiếu, thông thường có thể thay **method bodies**, constant pool và các attributes hợp lệ, nhưng không được tự ý:

- Thêm, xóa hoặc đổi tên các **fields** hoặc **methods** đã được định nghĩa;
- Thay method descriptor/signature, thuộc tính ảnh hưởng schema hoặc modifiers mà VM không hỗ trợ;
- Đổi superclass hoặc danh sách interfaces (class hierarchy);
- Đổi các thuộc tính cấu trúc đặc biệt như `NestHost`, `NestMembers`, `Record` hoặc `PermittedSubclasses` theo cách không được cho phép;
- Cung cấp class file mang một **binary name khác** tên của đối tượng `Class<?>` mục tiêu;
- Cung cấp class-file version mới hơn khả năng JVM hoặc bytes không hợp lệ.

Giới hạn có thể phụ thuộc JVM và phiên bản JVMTI. **Không tự suy rằng JVM hỗ trợ mọi dạng hot swap** chỉ vì `isRedefineClassesSupported() == true`.

### Thay body chứ không thay schema

Được thiết kế cho demo:

```java
// Trước
public static String text() {
    return "before";
}

// Sau: giữ nguyên tên, descriptor, modifiers, fields, hierarchy
public static String text() {
    return "after";
}
```

Thay schema không an toàn trong phần lớn JVM phổ biến:

```java
// Bản thay thế thêm field mới, dù cùng binary name:
private int newlyAddedField;
```

Đối với class đã nạp, JVM có thể từ chối với `UnsupportedOperationException` hoặc lỗi thích hợp do thay cấu trúc không hỗ trợ. Đừng dùng việc “biên dịch được” để kết luận “redefine được”.

### Đừng sửa static initializer theo cách mong đợi nó chạy lại

Định nghĩa mới **không kích hoạt tự động chạy lại `<clinit>`** và không reset static fields. Bạn có thể thay mã initializer trong class file nhưng các class đã được khởi tạo **không tự được khởi tạo lần hai** do lời gọi redefine.

## 6. Ví dụ Java 17 hoàn chỉnh: `before` → `after` bằng `ClassDefinition`

Ta tạo **hai file `MessageService.class` có cùng tên binary** nhưng method body khác nhau:

- Bản **v1** được app nạp lúc khởi động.
- Bản **v2** được đọc thành `byte[]` **sau khi class v1 đã nạp**.
- Agent tạo `ClassDefinition(MessageService.class, v2Bytes)` và gọi `redefineClasses`.
- App gọi cùng method của **cùng class identity** lần nữa và nhận kết quả mới.
- Một static counter cho thấy trạng thái không reset khi redefine.

Ví dụ không dùng thư viện bên ngoài và **không cần Class-File API JDK 24**; chỉ dùng JDK 17+.

### 6.1. Cấu trúc thư mục

```text
redefine-demo/
├── src/
│   ├── v1/
│   │   └── MessageService.java
│   ├── v2/
│   │   └── MessageService.java
│   ├── agent/
│   │   └── RedefineAgent.java
│   └── app/
│       └── DemoApp.java
└── agent.mf
```

Sau khi build sẽ có `build/v1/MessageService.class`, `build/v2/MessageService.class`, `agent.jar` và `app.jar`. Hai file source trùng tên class là **cố ý**; chúng được biên dịch **riêng hai lần vào hai thư mục khác nhau**.

### 6.2. `src/v1/MessageService.java`

```java
public final class MessageService {
    private static int calls = 100;

    private MessageService() {
    }

    public static String text() {
        calls++;
        return "before";
    }

    public static int calls() {
        return calls;
    }
}
```

Bản đầu khởi tạo `calls = 100` khi JVM thực sự initialize class. Mỗi lần gọi `text()` tăng bộ đếm.

### 6.3. `src/v2/MessageService.java`

```java
public final class MessageService {
    private static int calls = 100;

    private MessageService() {
    }

    public static String text() {
        calls++;
        return "after";
    }

    public static int calls() {
        return calls;
    }
}
```

So sánh v1 và v2: **cùng tên class, cùng field, cùng modifiers, cùng tên và descriptor của mọi method, cùng superclass**. Khác biệt có chủ đích chỉ là literal trả về trong method `text()`.

Giữ nguyên cả `private constructor` và `calls()`; không thay đổi những thứ JVM có thể coi là schema.

### 6.4. `src/agent/RedefineAgent.java`

```java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    private RedefineAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println(
                "[agent] supported="
                + inst.isRedefineClassesSupported());
    }

    public static void replace(Path replacementFile)
            throws IOException, UnmodifiableClassException,
                   ClassNotFoundException {

        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        if (!inst.isRedefineClassesSupported()) {
            System.out.println("[agent] skipped: unsupported");
            return;
        }

        if (!inst.isModifiableClass(MessageService.class)) {
            System.out.println("[agent] skipped: not modifiable");
            return;
        }

        // Đọc byte[] class file mới: không phải source Java.
        byte[] replacementBytes =
                Files.readAllBytes(replacementFile);

        // Cặp chính xác: Class<?> đã nạp và bytes v2.
        ClassDefinition replacement = new ClassDefinition(
                MessageService.class, replacementBytes);

        // Nếu thành công, các lần gọi method mới dùng definition v2.
        inst.redefineClasses(replacement);

        System.out.println("[agent] redefine completed");
    }
}
```

Giải thích:

- `premain` nhận `Instrumentation` khi JVM start với `-javaagent`. Demo lưu instance trong trường `volatile` cho lời gọi sau đó từ ứng dụng.
- `isRedefineClassesSupported()` và `isModifiableClass(MessageService.class)` được kiểm tra trước.
- `Files.readAllBytes` cung cấp **nội dung nguyên vẹn của `build/v2/MessageService.class`**. Nó **không** tải/định nghĩa class v2 trong JVM.
- `MessageService.class` là đối tượng `Class<?>` đã được runtime load, **không** phải một bản class v2 mới.
- `ClassDefinition` ghép class identity và bytes; `redefineClasses` là bước yêu cầu JVM thay body.
- Không có transformer khác đăng ký trong ví dụ nên bytes từ file là đầu vào trực tiếp cho kiểm tra/cài đặt definition.
- Demo cho lỗi API lan ra để dễ quan sát. Agent production cần logging, kiểm tra artifact và chiến lược rollback hoặc fail-safe phù hợp.

### 6.5. `src/app/DemoApp.java`

```java
import java.nio.file.Path;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DemoApp <replacement-class-file>");
        }

        // Lần đầu dùng v1, bảo đảm class đã được load/initialize.
        System.out.println("[main] before="
                + MessageService.text());
        System.out.println("[main] callsBefore="
                + MessageService.calls());

        // Đọc bytes v2 và redefine ngay trong cùng JVM.
        RedefineAgent.replace(Path.of(args[0]));

        System.out.println("[main] after="
                + MessageService.text());
        System.out.println("[main] callsAfter="
                + MessageService.calls());
    }
}
```

`MessageService.class` luôn trỏ tới **cùng class identity**. Không có `new ClassLoader()` nào được dùng để nạp một bản `MessageService` thứ hai.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true

```

Đây là manifest của **agent.jar**, không phải v1/v2 class file hoặc `app.jar`. Đảm bảo có dòng trống kết thúc main section. `Premain-Class` phải đúng binary name của agent (`RedefineAgent` đang thuộc default package).

### 6.7. Biên dịch và chạy trên Linux/macOS/WSL (POSIX shell)

Đứng trong thư mục `redefine-demo/` chứa `agent.mf`:

```bash
mkdir -p build/v1 build/v2

# Bản class sẽ thực sự được JVM nạp lúc đầu.
javac --release 17 -d build/v1 src/v1/MessageService.java

# Bản replacement giữ cùng binary name nhưng method body mới.
javac --release 17 -d build/v2 src/v2/MessageService.java

# Compiler của app và agent chỉ nhìn thấy class v1.
javac --release 17 -cp build/v1 -d build/v1 \
  src/agent/RedefineAgent.java src/app/DemoApp.java

# Agent chỉ mang lớp RedefineAgent và manifest capability.
jar --create --file agent.jar --manifest agent.mf \
  -C build/v1 RedefineAgent.class

# App JAR chỉ mang v1; KHÔNG đưa v2 vào classpath.
jar --create --file app.jar \
  -C build/v1 DemoApp.class -C build/v1 MessageService.class

java -javaagent:agent.jar -cp "agent.jar:app.jar" \
  DemoApp build/v2/MessageService.class
```

**Stdout mong đợi** trên HotSpot/JDK 17+ có hỗ trợ redefinition:

```text
[agent] supported=true
[main] before=before
[main] callsBefore=101
[agent] redefine completed
[main] after=after
[main] callsAfter=102
```

Ý nghĩa từng dòng:

1. Agent được JVM khởi động, manifest yêu cầu capability và JVM cấp khả năng redefine.
2. Method `MessageService.text()` ở v1 trả `"before"`; lần gọi đầu tăng `calls` từ 100 lên 101.
3. Agent dùng bytes từ `build/v2/MessageService.class` qua `ClassDefinition` để cài body mới.
4. Method `text()` ở các invocation mới trả `"after"`.
5. Static field `calls` **tiếp tục từ 101 lên 102**, không reset về 100; class initializer không chạy lại vì redefine.

Nếu JVM không hỗ trợ, chương trình đi vào nhánh `skipped` và lời gọi cuối vẫn trả `"before"`, count đạt 102. Đây là đường fallback có kiểm soát, **không** phải proof rằng redefine thành công.

### 6.8. Windows PowerShell

Trên Windows dùng dấu **`;`** thay cho `:` trong classpath, và tạo thư mục bằng lệnh PowerShell:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null

javac --release 17 -d build/v1 src/v1/MessageService.java
javac --release 17 -d build/v2 src/v2/MessageService.java
javac --release 17 -cp build/v1 -d build/v1 src/agent/RedefineAgent.java src/app/DemoApp.java

jar --create --file agent.jar --manifest agent.mf -C build/v1 RedefineAgent.class
jar --create --file app.jar -C build/v1 DemoApp.class -C build/v1 MessageService.class

java -javaagent:agent.jar -cp "agent.jar;app.jar" DemoApp build/v2/MessageService.class
```

Để tránh phụ thuộc môi trường, giữ đúng vị trí working directory: tham số file thay thế được truyền vào ứng dụng và `Path.of(args[0])` được giải quyết **tương đối với thư mục hiện hành**.

### 6.9. Kiểm tra có đúng hai artifact khác nhau

```bash
javap -classpath build/v1 -c MessageService
javap -classpath build/v2 -c MessageService

jar --list --file agent.jar
jar --list --file app.jar
```

Hai lần `javap` sẽ cho thấy `text()` của v1 và v2 dùng các literal khác nhau; index constant pool có thể khác giữa build. `agent.jar` có `RedefineAgent.class` và manifest; `app.jar` có `DemoApp.class` và **v1 `MessageService.class`**.

**Không xóa/đè `build/v1/MessageService.class` bằng bản v2 trước khi chạy**: nếu app vô tình load v2 ngay từ đầu, ví dụ không còn chứng minh việc thay định nghĩa trong tiến trình.

## 7. Điều gì thực sự được giữ nguyên sau khi redefine?

### 7.1. Class identity và object đã tồn tại

Redefinition không tạo một class identity mới. Những instance của class vẫn là instance của **cùng class**; các field hiện có và giá trị của chúng được duy trì.

```text
Trước:
  Class<?> identity = MessageService.class
  Existing object -> methods v1

Sau redefine:
  Class<?> identity = MessageService.class  // vẫn cùng identity
  Existing object -> new method invocations dùng v2
```

Nếu method thay đổi hành vi nhưng vẫn cùng signature, object cũ có thể gọi body mới. Không được suy rằng object tự được tạo lại, constructor được gọi lại hoặc state được migration tự động.

### 7.2. Static state và class initializer

Javadoc quy định redefinition không tự gây class initialization ngoài semantics bình thường và **không chạy lại initializer**. Giá trị static variables vẫn như trước lời gọi. Trong demo, counter từ 101 thành 102; một static initializer `calls = 100` trong bytes v2 **không** chạy lại.

Nếu logic mới cần state mới, phải thiết kế migration/bảo toàn tương thích, nhưng không được tự thêm field vào class đã nạp nếu JVM không hỗ trợ thay schema.

### 7.3. Stack frames đang hoạt động

Nếu một thread đã vào method v1 **trước khi** redefine, frame đang hoạt động tiếp tục chạy **bytecode cũ**. Những invocation mới sẽ chạy body v2.

```text
Thread A:  enter slowOperation() ở v1
              |
Thread B:     redefineClasses(v2) thành công
              |
Thread A:  frame cũ tiếp tục phần code của v1
Thread C:  invocation mới chạy body v2
```

Vì thế **“redefine trả về thành công” không nghĩa mọi frame đang chạy chuyển bytecode tức thì**. Không dùng redefine như primitive để thay đồng bộ hay đảm bảo các thread đồng loạt đi qua một cutover điểm duy nhất.

### 7.4. Đồng bộ và hiệu ứng phụ

Nếu code v2 thay thứ tự lock, cách phát event, cấu hình metric hoặc dependency, những invocation mới có hành vi mới trong khi invocation cũ có thể đang hoàn thành bằng code cũ. Agent và ứng dụng cần cân nhắc tính tương thích giữa hai phiên bản, đặc biệt ở module/class loader và giao dịch lâu dài.

## 8. `redefineClasses` so với `retransformClasses`

| Tiêu chí | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| --- | --- | --- |
| Mục tiêu | Thay định nghĩa của class đã nạp | Chạy lại pipeline biến đổi cho class đã nạp |
| Nguồn bytes | Agent **tự cung cấp toàn bộ bytes mới** trong `ClassDefinition` | JVM bắt đầu từ bytes cơ sở của load/redefine gần nhất và áp dụng transformer |
| Lựa chọn class | Đối tượng `Class<?>` trong mỗi `ClassDefinition` | Danh sách `Class<?>` |
| Capability | `Can-Redefine-Classes` + VM hỗ trợ | `Can-Retransform-Classes` + VM hỗ trợ |
| API kiểm tra | `isRedefineClassesSupported()` | `isRetransformClassesSupported()` |
| Cần transformer đăng ký trước? | **Không bắt buộc**; có thể dùng bytes build sẵn | Không bắt buộc để gọi, nhưng transformer quyết định thay đổi bytecode |
| Transformer có được gọi? | Các transformer đăng ký cho class redefinition sẽ được gọi | Các transformer `canRetransform=true` được gọi; kết quả transformer `false` được reuse |
| Đổi cấu trúc tùy ý? | **Không**; chịu ràng buộc JVMTI | **Không**; chịu ràng buộc JVMTI |
| Dùng điển hình | Fix-and-continue, thay method body bằng class file mới | Tracing/coverage tái chạy phép biến đổi |

Cả hai cho phép class đã nạp nhận bytecode mới mà không cần JVM restart, nhưng **hai nguồn bytecode và hai capability khác nhau**.

Một điểm dễ nhầm: `redefineClasses` **có thể gọi lại transformer đã đăng ký kể cả khi được thêm với `canRetransform=false`**, bởi cờ này phân loại xử lý **retransformation**. Không đánh đồng “transformer không hỗ trợ retransform” với “transformer không chạy lúc redefine”.

## 9. Redefinition nhiều class trong một lời gọi

Một lần gọi có thể mang nhiều cặp:

```java
ClassDefinition first = new ClassDefinition(
        FirstService.class, firstBytes);

ClassDefinition second = new ClassDefinition(
        SecondService.class, secondBytes);

instrumentation.redefineClasses(first, second);
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập; agent phải chuẩn bị `instrumentation`, hai class và hai bộ bytes.

Lý do dùng một lời gọi cho một tập: hai class có thể có liên hệ cần cập nhật đồng thời, ví dụ method body của A bắt đầu gọi behavior mới của B. Theo contract, **nếu thao tác ném exception thì không class nào trong tập được redefine**. Đây là **all-or-nothing khi lời gọi thất bại**, không phải một giao dịch dữ liệu nghiệp vụ và không tạo bảo đảm rằng mọi thread đang hoạt động sẽ thấy cùng method version trong cùng thời điểm.

Các thực hành hữu ích:

- Kiểm tra tên, schema, class file version và classloader của **từng** cặp trước khi gọi.
- Không lặp lại cùng `Class<?>` hai lần trong một batch vì yêu cầu không rõ ràng, khó debug và không đem lại lợi ích.
- Dùng một biến thể bytes đã test, kiểm tra tương thích với các class khác trong JVM.
- Lưu phiên bản artifact và kế hoạch rollback **trước** khi thay đổi; chỉ dùng bytes cũ làm rollback nếu chúng vẫn đáp ứng schema/loader và runtime capabilities hiện tại.

Nếu một replacement trong tập không hợp lệ, cả lượt có thể thất bại. Vì thế batch nên đủ nhỏ và có mục đích nhất quán.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | Manifest thiếu `Can-Redefine-Classes: true` hoặc VM không hỗ trợ | Kiểm tra **agent JAR thực được load**, JVM hiện tại và capability |
| `UnsupportedOperationException` khi gọi | Capability không được cấp hoặc replacement yêu cầu thay đổi không được phép | Kiểm tra manifest, class schema và giới hạn JVMTI |
| `UnmodifiableClassException` | Một class mục tiêu không modifiable | Kiểm tra `isModifiableClass` từng class; bỏ qua class đặc biệt |
| `ClassFormatError` | Bytes không phải class file hợp lệ | Đọc đúng `.class`, tránh lẫn source/ZIP/empty bytes; verify |
| `NoClassDefFoundError` | Tên lớp trong bytes không khớp `Class<?>` đích | Đối chiếu internal/binary name, đúng class file và loader |
| `UnsupportedClassVersionError` | Class file version lớn hơn JVM đích hỗ trợ | Build với `javac --release 17` hoặc target version thích hợp |
| `LinkageError` hoặc `VerifyError` | Bytecode/hierarchy/trạng thái liên kết không hợp lệ | Kiểm tra stack maps, method descriptors, references/module/class loader |
| Thêm field/method gây lỗi | Đổi schema không được JVM hỗ trợ | Chỉ đổi body/constant pool hợp lệ, không sửa cấu trúc |
| Redefine thành công nhưng method vẫn trả giá trị cũ ở một thread | Stack frame cũ tiếp tục bytecode v1 | Kiểm tra invocation mới và thời điểm gọi |
| Static counter không reset | Đây là semantics đúng: initializer không chạy lại | Đừng dựa vào redefinition để reset state |
| Code v2 có trên disk nhưng runtime không đổi | Chưa gọi API, đang đọc nhầm path, nạp nhầm bản, hoặc capability false | Log đường dẫn/bytes, check class identity, kết quả API |
| Chỉ đưa v2 JAR vào `-cp` và mong lớp v1 tự đổi | Class loading không tự thay class identity đã định nghĩa | Cần `ClassDefinition` và `redefineClasses` |
| Redefine trong môi trường nhiều agent làm hành vi khác dự kiến | `ClassFileTransformer` khác cũng chạy trên bytes mới | Kiểm tra danh sách và thứ tự transformer, ownership của biến đổi |
| Lời gọi ném lỗi khi một batch có nhiều class | Một replacement vi phạm ràng buộc | Verify từng cặp, rồi retry **có chủ đích** với batch đúng; không sửa class cũ một phần |

**Những lỗi nào là checked?** `UnmodifiableClassException` và `ClassNotFoundException` xuất hiện trong signature. Nhiều lỗi quan trọng khác là unchecked exception hoặc `Error`. Đừng viết `catch (Exception)` rồi tuyên bố đã bắt được mọi lỗi class file. Đối với production, cần phân biệt loại lỗi, log vừa đủ và không vô tình nuốt `LinkageError`.

## 11. Checklist triển khai an toàn trong agent

1. **Kiểm tra capability:** manifest `Can-Redefine-Classes: true` + `isRedefineClassesSupported()`.
2. **Kiểm tra class đích:** dùng đúng `Class<?>` của defining loader cần sửa và `isModifiableClass`.
3. **Chuẩn bị bytes đúng:** full class file mới, không phải source, ZIP/JAR bytes hoặc method-only instructions.
4. **Giữ class identity và schema tương thích:** không đổi tên class, field/method signatures, hierarchy và modifiers không hỗ trợ.
5. **Chọn nguồn bytes có thể kiểm soát:** artifact đã build, verified bytecode emitter hoặc snapshot đáng tin.
6. **Không mutate bytes sau khi gắn `ClassDefinition`:** constructor không copy mảng.
7. **Tính đến transformer khác:** redefine đi qua chuỗi `ClassFileTransformer` được đăng ký.
8. **Giữ nguyên lifecycle của object/state:** initializer không rerun; active frames cũ có thể tiếp tục body cũ.
9. **Kiểm tra output và rollback:** integration test trên JVM/version thật; lưu artifact cũ và kế hoạch phục hồi có kiểm soát.
10. **Theo dõi vận hành:** log target loader, artifact version, định danh bytes/checksum, trạng thái capability, thành công/thất bại và các lỗi `ClassFormatError`/`LinkageError`.
11. **Batch có chủ đích:** nhiều class liên quan có thể thay cùng lượt, nhưng không xem API như transaction nghiệp vụ hay barrier giữa các threads.
12. **Không mở rộng quyền không cần thiết:** manifest chỉ yêu cầu capability agent thật sự cần; không tự động dùng attach hoặc thay module permissions khi không liên quan.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `ClassDefinition(Target.class, bytes)` tạo một `Class<?>` mới hay nối bytes với class đang tồn tại?

**Đáp án:** Nó chỉ tạo parameter block ghép **`Class<?>` hiện có** và bytes đầy đủ. Chính `Instrumentation.redefineClasses` mới yêu cầu JVM cài definition mới.

**Câu 2.** Chỉ sửa `Target.java` và chạy lại `javac` có khiến class trong JVM đang chạy đổi không?

**Đáp án:** Không. Agent cần lấy `Target.class` mới dưới dạng `byte[]`, kiểm tra class đích/capability rồi gọi `redefineClasses`.

**Câu 3.** `Can-Retransform-Classes: true` có thay thế `Can-Redefine-Classes: true` không?

**Đáp án:** Không. Đây là hai optional capabilities độc lập.

**Câu 4.** Redefine bản v2 có cùng name/methods nhưng thêm một field mới có chắc thành công không?

**Đáp án:** Không. Thay schema có thể bị JVMTI/JVM từ chối. Demo giữ field/method schema không đổi.

**Câu 5.** Vì sao trong demo counter là 101 trước và 102 sau, không reset về 100?

**Đáp án:** `redefineClasses` không tự rerun class initializer và giữ giá trị static fields. Chỉ method body mới được áp cho invocation sau.

**Câu 6.** Transformer `canRetransform=false` có được gọi khi `redefineClasses` diễn ra không?

**Đáp án:** Có thể và theo contract các transformer đã đăng ký được gọi khi class redefinition; tham số `canRetransform` chi phối riêng đường retransformation.

**Câu 7.** Một batch redefine A và B ném exception ở replacement B: A đã được đổi một nửa chưa?

**Đáp án:** Theo contract, nếu lời gọi ném exception **không class nào được redefine**. Tuy nhiên điều đó không đồng nghĩa thread execution có khả năng đồng bộ hóa cutover kiểu transaction.

## 13. Tài liệu chính thức

- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, `isRedefineClassesSupported`, `isModifiableClass`, semantics static state/active frames và lỗi.
- [Oracle Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): `Class<?>` + `byte[]`; constructor không copy buffer.
- [Oracle Java SE 17 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): các manifest attributes `Premain-Class`, `Agent-Class`, `Can-Redefine-Classes` và `Can-Retransform-Classes`.
- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback khi load/redefine/retransform và thứ tự áp dụng biến đổi.
- [Oracle JVM TI — `RedefineClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): giới hạn class-file changes, tương tác JVM và semantics runtime.
- [Java Virtual Machine Specification SE 17 — Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): định dạng class file và version.

**Ghi nhớ:** `redefineClasses` **không tìm code mới cho bạn**; nó thay định nghĩa class đã nạp bằng **full class-file bytes** mà bạn đặt trong `ClassDefinition(Class<?>, byte[])`, với capability và giới hạn JVM phù hợp. Method body của invocation mới có thể đổi, nhưng class identity, instance và static state không tự được tạo lại hay reset.
