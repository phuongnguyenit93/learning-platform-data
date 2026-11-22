# Điều kiện manifest cùng khả năng JVM trước khi retransformation

**Retransformation** là khả năng yêu cầu JVM chạy lại chuỗi biến đổi bytecode đối với một lớp **đã được nạp**, thông qua `Instrumentation.retransformClasses(Class<?>...)`. Đây là một khả năng **tùy chọn**, không phải quyền mặc định của mọi Java agent. Trước khi dùng, agent phải đáp ứng **hai điều kiện cấp capability**: **JAR của agent khai báo cần retransformation trong manifest** và **JVM hiện tại hỗ trợ capability đó**. Ngay cả khi hai điều kiện đều đạt, lớp cụ thể vẫn cần **modifiable**, và kết quả bytecode phải hợp lệ theo giới hạn retransform.

Bài này tập trung vào manifest `Can-Retransform-Classes`, kiểm tra `isRetransformClassesSupported()` và `isModifiableClass(...)`, cách đăng ký `ClassFileTransformer` với `canRetransform=true`, những lỗi cần chặn trước khi gọi API và ví dụ Java 17+ thực sự chạy được với **hai JAR agent có manifest khác nhau**.

## 1. Ba tầng điều kiện cần phân biệt

Đừng gộp ba câu hỏi sau làm một:

| Tầng | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| **Khai báo của agent** | Agent có yêu cầu quyền retransformation trong JAR manifest không? | `Can-Retransform-Classes: true` trong **manifest của agent JAR**. Nếu thiếu hoặc không phải `true` thì mặc định là `false`. |
| **Capability của JVM/cấu hình** | JVM có cho phép retransformation đối với agent đã khai báo không? | `Instrumentation.isRetransformClassesSupported()`; đây là kiểm tra **tại runtime**, không phải đoán theo tên JVM. |
| **Tính sửa đổi được của lớp** | Lớp đã nạp cụ thể này có thể thay định nghĩa không? | `Instrumentation.isModifiableClass(targetClass)`; vẫn phải kiểm tra dù capability chung là `true`. |

Tóm tắt:

```text
agent.jar/META-INF/MANIFEST.MF
    └─ Can-Retransform-Classes: true ?
             │
             ├─ không → isRetransformClassesSupported() = false
             │
             └─ có
                  │
                  v
             JVM có hỗ trợ capability này?
                  │
                  ├─ không → isRetransformClassesSupported() = false
                  │
                  └─ có → isRetransformClassesSupported() = true
                              │
                              v
                  targetClass đã được nạp và modifiable?
                              │
                              ├─ không → không retransform lớp đó
                              │
                              └─ có → có thể gọi retransformClasses(...)
                                        │
                                        v
                               Transformer chạy/bytes được kiểm tra;
                               kết quả vẫn phải hợp lệ, phù hợp giới hạn.
```

**Điểm rất dễ nhầm:** `isModifiableClass(clazz) == true` **không chứng minh** `isRetransformClassesSupported() == true`. Theo API, hai giá trị **độc lập**: `isModifiableClass` cho biết lớp có thể được thay đổi bởi cơ chế redefine/retransform, còn mỗi capability vẫn phải được kiểm tra riêng.

## 2. Manifest: khai báo quyền retransformation đúng chỗ

### 2.1. Trường bắt buộc cho startup agent

Đối với agent khởi chạy bằng `-javaagent`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

- `Premain-Class`: tên class đầy đủ có `public static void premain(String, Instrumentation)` hoặc `premain(String)`.
- `Can-Retransform-Classes: true`: **yêu cầu capability** cho agent; không bảo đảm một mình nó khiến mọi JVM hỗ trợ.
- Dòng trống cuối ví dụ giúp manifest được xử lý rõ ràng. Các thuộc tính phải nằm trong tệp `META-INF/MANIFEST.MF` **bên trong JAR agent thực tế**, không phải chỉ trong một file text nằm cạnh JAR.

Cách chạy:

```bash
java -javaagent:agent-on.jar -cp out demo.retransform.App
```

JVM đọc manifest, khởi động agent và đưa `Instrumentation` tới `premain`. Khi nhận `Instrumentation`, agent phải **kiểm tra capability** trước khi đăng ký transformer có khả năng retransformation hoặc gọi retransform.

### 2.2. Thiếu, sai hoặc có giá trị khác `true`

Ví dụ manifest **không khai báo** capability:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent

```

Theo đặc tả, `Can-Retransform-Classes` là thuộc tính **tùy chọn**; **mặc định `false`**. Những giá trị khác `true` cũng được xem là `false`. Ví dụ:

| Manifest | Ý nghĩa |
| --- | --- |
| `Can-Retransform-Classes: true` | Agent yêu cầu retransformation; vẫn cần JVM hỗ trợ. |
| `Can-Retransform-Classes: TRUE` | Giá trị boolean không phân biệt hoa/thường; tương đương `true`. |
| `Can-Retransform-Classes: false` | Không yêu cầu retransformation. |
| Không có dòng `Can-Retransform-Classes` | Mặc định `false`. |
| `Can-Retransform-Classes: yes` | Không phải `true`; được xem là `false`. |

**Không** thể bật capability chỉ bằng cách gọi `addTransformer(transformer, true)`. Đối số `true` ở đây yêu cầu **đăng ký một transformer thuộc nhóm có khả năng retransformation**; nó không thay thế manifest và không thể ép JVM cấp một capability không hỗ trợ.

### 2.3. Agent được attach sau khi JVM chạy

Nếu nạp agent theo cơ chế Attach API (khi JVM và môi trường cho phép), JAR phải có entry point `Agent-Class`:

```text
Manifest-Version: 1.0
Agent-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

Class agent cần có `public static void agentmain(String, Instrumentation)` (hoặc dạng một tham số) khi nạp động. `Can-Retransform-Classes` vẫn là **yêu cầu capability** của agent JAR. Nếu một JAR hỗ trợ **cả hai kiểu khởi động**, manifest có thể khai báo đồng thời `Premain-Class` và `Agent-Class`, nhưng JVM chọn entry point theo **cách nạp agent**.

Có thể phân biệt:

- **`-javaagent:...`** → `Premain-Class` và `premain`.
- **Attach API `loadAgent(...)`** → `Agent-Class` và `agentmain`, nếu cơ chế attach được hỗ trợ/cho phép.
- **`Can-Retransform-Classes`** → yêu cầu capability cho hai con đường trên; không quyết định entry point nào được gọi.

Việc cho phép **động nạp agent** (chính sách attach, quyền hệ điều hành, cờ JVM) là câu hỏi khác với **retransformation capability**. Attach thành công không suy ra retransform được; retransform capability có sẵn cũng không bảo đảm attach từ ngoài được.

### 2.4. Đừng nhầm với `Can-Redefine-Classes`

Hai mục manifest **độc lập**:

| Manifest | API tương ứng | Ý nghĩa |
| --- | --- | --- |
| `Can-Retransform-Classes: true` | `isRetransformClassesSupported()`, `retransformClasses(...)`, `addTransformer(..., true)` | Yêu cầu chạy lại chuỗi transformer với lớp đang nạp. |
| `Can-Redefine-Classes: true` | `isRedefineClassesSupported()`, `redefineClasses(...)` | Yêu cầu thay định nghĩa class từ `ClassDefinition` do caller cung cấp. |

Có thể cần **cả hai** nếu agent làm hai loại thao tác. Nhưng khai báo `Can-Redefine-Classes: true` **không thay thế** `Can-Retransform-Classes: true`. Tương tự, manifest có `Premain-Class` hợp lệ **không tự bật** retransform.

## 3. Kiểm tra chính thức bằng `Instrumentation`

Đoạn mẫu an toàn trong `premain`/`agentmain`:

```java
// Trích đoạn bên trong class agent, không phải chương trình độc lập.
public static void configure(Instrumentation inst,
                             ClassFileTransformer transformer,
                             Class<?> targetClass)
        throws UnmodifiableClassException {

    if (!inst.isRetransformClassesSupported()) {
        System.out.println("Retransformation unavailable");
        return;
    }

    if (!inst.isModifiableClass(targetClass)) {
        System.out.println("Target class not modifiable");
        return;
    }

    inst.addTransformer(transformer, true);
    inst.retransformClasses(targetClass);
}
```

Cần import `java.lang.instrument.Instrumentation`, `ClassFileTransformer` và `UnmodifiableClassException`. Đây là đoạn **minh họa thứ tự điều kiện**; agent production còn cần điều phối việc đăng ký lại, xử lý exception, bảo vệ transformer callback và cleanup.

Có hai điểm API then chốt:

1. `isRetransformClassesSupported()` cho biết **cấu hình JVM hiện tại đối với agent đã nhận Instrumentation** có hỗ trợ retransform không. Theo Java 17 API, trong một lần hoạt động của một JVM, những lần gọi lặp trên cùng cấu hình này cho **cùng kết quả**. Không cần hỏi lại mỗi bytecode event chỉ để xem cờ có tự đổi từ `false` sang `true` hay không.
2. `isModifiableClass(target)` kiểm tra **lớp cụ thể**. Các lớp primitive như `int.class` và lớp mảng như `String[].class` **không modifiable**. Một số lớp khác có thể bị JVM đánh dấu không sửa được. Kết quả `isModifiableClass` không phải một phép kiểm tra thay cho capability.

### 3.1. Khi `isRetransformClassesSupported() == false`

Nếu gọi:

```java
// Trích đoạn minh họa trong agent đã có inst và transformer:
inst.addTransformer(transformer, true);
```

trong khi không có capability, API ném `UnsupportedOperationException`. Nếu agent bỏ qua kiểm tra mà gọi `inst.retransformClasses(Target.class)`, lời gọi đó cũng có thể ném `UnsupportedOperationException` vì cấu hình không cho phép retransform.

Nếu agent vẫn cần quan sát các **class được nạp trong tương lai**, nó có thể đăng ký:

```java
// Có thể đăng ký transformer không hỗ trợ retransformation.
inst.addTransformer(transformer, false);
```

Đăng ký `false` cho phép callback ở những trường hợp load/redefine phù hợp, nhưng không làm transformer ấy được **gọi lại** khi retransform. Việc chọn `false` là một chế độ hoạt động có ý nghĩa, không phải “đăng ký lỗi”.

### 3.2. Khi capability là `true` nhưng class không modifiable

Mọi lời gọi retransform phải xem xét **lớp đích**. `retransformClasses(...)` ném `UnmodifiableClassException` nếu một class được chỉ định không thể sửa đổi. Vì vậy **không quét tất cả class đã nạp rồi truyền cả danh sách không lọc** vào retransform.

Một quy trình cho nhiều class:

```java
// Mã minh họa trong agent; không phải chương trình độc lập.
if (inst.isRetransformClassesSupported()) {
    Class<?>[] candidates = inst.getAllLoadedClasses();
    java.util.List<Class<?>> allowed = new java.util.ArrayList<>();

    for (Class<?> candidate : candidates) {
        if (inst.isModifiableClass(candidate)) {
            allowed.add(candidate);
        }
    }

    if (!allowed.isEmpty()) {
        inst.retransformClasses(allowed.toArray(Class<?>[]::new));
    }
}
```

Mẫu này **chỉ minh họa lọc capability**. Agent thực tế phải lọc thêm theo **gói/module/class loader và mục đích instrumentation**, giới hạn kích thước batch, tránh class của chính agent và xử lý transformer không an toàn với bootstrap/system classes. Việc retransform toàn bộ mọi class modifiable chỉ vì API cho phép **không phải chiến lược được khuyến nghị**.

## 4. Ví dụ chạy được: hai manifest, cùng một agent và một JVM tương ứng

Đây là thí nghiệm **Java 17+** không dùng thư viện ngoài. Ta đóng gói **chính xác cùng các class agent** vào **hai JAR** nhưng dùng manifest khác nhau:

- **`agent-on.jar`** có `Can-Retransform-Classes: true`.
- **`agent-off.jar`** **không có** dòng `Can-Retransform-Classes`, tức mặc định `false`.

Chương trình nạp `Target`, kiểm tra capability, rồi thử `retransformClasses(Target.class)` khi đủ điều kiện. Transformer chỉ **in log và trả `null`**, nên hành vi của Target không thay đổi. Vì thế output phân biệt **khả năng gọi lại callback** với **việc sửa logic**.

### 4.1. Cấu trúc tệp

```text
retransform-demo/
├── src/
│   └── demo/
│       └── retransform/
│           ├── ProbeAgent.java
│           ├── ProbeTransformer.java
│           ├── Target.java
│           └── App.java
├── agent-on.mf
└── agent-off.mf
```

Bốn file Java bên dưới là chương trình mẫu đầy đủ, tên class và package nhất quán.

### 4.2. `src/demo/retransform/ProbeAgent.java`

```java
package demo.retransform;

import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class ProbeAgent {
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[agent] retransformationSupported=" + supported);
        if (supported) {
            inst.addTransformer(new ProbeTransformer(), true);
            System.out.println("[agent] registered canRetransform=true");
        } else {
            System.out.println("[agent] skip capable transformer");
        }
    }

    public static void tryRetransform(Class<?> type)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("No startup agent");
        }

        boolean modifiable = inst.isModifiableClass(type);
        System.out.println("[app] modifiable=" + modifiable);
        if (!inst.isRetransformClassesSupported() || !modifiable) {
            System.out.println("[app] skip retransform");
            return;
        }

        inst.retransformClasses(type);
        System.out.println("[app] retransform complete");
    }
}
```

Giải thích:

1. JVM gọi `premain` **trước application `main`**.
2. Nếu thiếu capability, agent **không** thử `addTransformer(..., true)`. Nó in thông điệp và cho phép ứng dụng tiếp tục.
3. Khi `true`, transformer được đăng ký **trước** khi ứng dụng yêu cầu load `Target`.
4. `tryRetransform(...)` kiểm tra độc lập **JVM capability** và **class modifiability** trước khi gọi API.
5. Thí nghiệm dùng class `ProbeAgent` như kênh gọi hàm từ ứng dụng để ngắn gọn. Trong công cụ thật, agent thường có API điều khiển, MBean hoặc luồng điều phối riêng thay vì buộc ứng dụng import class agent.

`instrumentation` được thiết lập trong `premain` rồi đọc trong cùng tiến trình trong lần chạy minh họa. Nếu bạn copy ví dụ sang thiết kế điều khiển đa luồng, cần cân nhắc đồng bộ/volatile và vòng đời, không dùng một biến static không kiểm soát trên nhiều thread.

### 4.3. `src/demo/retransform/ProbeTransformer.java`

```java
package demo.retransform;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ProbeTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(Module module, ClassLoader loader,
            String className, Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain, byte[] classfileBuffer) {
        if ("demo/retransform/Target".equals(className)) {
            System.out.println("[transform] Target phase="
                    + (classBeingRedefined == null ? "load" : "retransform"));
        }
        return null;
    }
}
```

Đây là transformer **không thay bytes**. Với định nghĩa mới, `classBeingRedefined == null`; khi gọi retransform trên class đã nạp, tham số khác `null`.

Hợp đồng `ClassFileTransformer` trên Java 17 còn có overload năm tham số; cả hai overload đều có default method. Do đó interface **không phải functional interface** ở Java 17 và không thể thay class ở trên bằng lambda thông thường mà không tạo interface riêng.

Đừng dựa vào nhãn `phase=retransform` như một bộ nhận diện tổng quát cho mọi trường hợp: `classBeingRedefined != null` cũng xảy ra khi **redefineClasses**. Trong chương trình cụ thể này ta biết đó là retransform vì code gọi `retransformClasses(...)`, không gọi redefine.

### 4.4. `src/demo/retransform/Target.java`

```java
package demo.retransform;

public final class Target {
    private Target() {}

    public static String message() {
        return "original";
    }
}
```

Target là class ứng dụng bình thường. Chúng ta dùng nó để kiểm chứng **callback xảy ra cho class đã nạp**, không thay thế literal hay bytecode.

### 4.5. `src/demo/retransform/App.java`

```java
package demo.retransform;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[app] first=" + Target.message());
        ProbeAgent.tryRetransform(Target.class);
        System.out.println("[app] second=" + Target.message());
    }
}
```

Lời gọi `Target.message()` đầu tiên bảo đảm `Target` đã được nạp trước khi gọi `tryRetransform`. Nếu capability `true`, JVM sẽ gọi transformer **lần thứ hai** cho Target do retransform, dù class không cần nạp mới.

### 4.6. Hai tệp manifest

`agent-on.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent
Can-Retransform-Classes: true

```

`agent-off.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.retransform.ProbeAgent

```

Hai JAR có **cùng bytecode agent**, chỉ khác manifest. Giữ ký tự xuống dòng cuối mỗi manifest; không dùng `Main-Class` thay cho `Premain-Class`. Trong thí nghiệm, agent JAR chứa `ProbeAgent.class` và `ProbeTransformer.class`, còn `App`/`Target` có trong application classpath `out`.

### 4.7. Biên dịch trên JDK 17+ và đóng gói

Từ thư mục `retransform-demo/`, với **Bash**:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/retransform/ProbeAgent.java \
  src/demo/retransform/ProbeTransformer.java \
  src/demo/retransform/Target.java \
  src/demo/retransform/App.java

jar --create --file agent-on.jar --manifest agent-on.mf \
  -C out demo/retransform/ProbeAgent.class \
  -C out demo/retransform/ProbeTransformer.class

jar --create --file agent-off.jar --manifest agent-off.mf \
  -C out demo/retransform/ProbeAgent.class \
  -C out demo/retransform/ProbeTransformer.class
```

Tương đương với **PowerShell**, tạo thư mục `out` rồi chạy từng lệnh trên một dòng:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/retransform/ProbeAgent.java src/demo/retransform/ProbeTransformer.java src/demo/retransform/Target.java src/demo/retransform/App.java
jar --create --file agent-on.jar --manifest agent-on.mf -C out demo/retransform/ProbeAgent.class -C out demo/retransform/ProbeTransformer.class
jar --create --file agent-off.jar --manifest agent-off.mf -C out demo/retransform/ProbeAgent.class -C out demo/retransform/ProbeTransformer.class
```

Dấu `\` ở lệnh Bash có nghĩa **nối dòng**, không phải cú pháp tương đương trong PowerShell. Các lệnh dùng `javac` và `jar` có sẵn trong JDK. Tùy chọn `--release 17` đảm bảo API/source/classfile của ví dụ tương thích Java 17.

### 4.8. Chạy với manifest BẬT retransformation

```bash
java -javaagent:agent-on.jar -cp out demo.retransform.App
```

**Stdout khi chạy trên OpenJDK 24.0.2 hỗ trợ retransformation:**

```text
[agent] retransformationSupported=true
[agent] registered canRetransform=true
[transform] Target phase=load
[app] first=original
[app] modifiable=true
[transform] Target phase=retransform
[app] retransform complete
[app] second=original
```

Phân tích:

- JVM đọc manifest có `Can-Retransform-Classes: true`; trong môi trường thực hành, `isRetransformClassesSupported() == true`.
- Agent đăng ký `ProbeTransformer` với `true` trước khi ứng dụng chạy.
- JVM định nghĩa Target: callback với `classBeingRedefined == null` → `phase=load`.
- Ứng dụng gọi `isModifiableClass(Target.class)`: với class đơn giản trong JVM thử nghiệm kết quả là `true`.
- Lời gọi `retransformClasses(Target.class)` làm transformer **được gọi lại** với `classBeingRedefined != null` → `phase=retransform`.
- Target vẫn trả `original` vì transformer chỉ trả `null`. **Retransformation có thể diễn ra thành công mà không sửa logic**.

### 4.9. Chạy với manifest KHÔNG yêu cầu retransformation

```bash
java -javaagent:agent-off.jar -cp out demo.retransform.App
```

**Stdout trên cùng OpenJDK 24.0.2:**

```text
[agent] retransformationSupported=false
[agent] skip capable transformer
[app] first=original
[app] modifiable=true
[app] skip retransform
[app] second=original
```

Cùng JVM implementation và cùng mã agent, nhưng thiếu dòng capability → `isRetransformClassesSupported() == false`. Agent xử lý an toàn bằng cách **không đăng ký transformer true và không gọi retransform**.

Dòng `[app] modifiable=true` vẫn xuất hiện dù `retransformationSupported=false`. Đây là bằng chứng trực tiếp của việc **không được dùng `isModifiableClass` thay cho `isRetransformClassesSupported`**.

> Đầu ra cụ thể bên trên đã được kiểm chứng khi biên dịch bằng `javac --release 17` và chạy trên **Zulu/OpenJDK 24.0.2**. Trên JVM khác, capability hoặc modifiability có thể khác. Hãy xem stdout là kết quả **của môi trường thí nghiệm**, không phải cam kết mọi JVM trên thế giới đều trả cùng các boolean.

### 4.10. Kiểm tra manifest bên trong JAR thật

Có thể liệt kê nội dung JAR:

```bash
jar --list --file agent-on.jar
jar --list --file agent-off.jar
```

Trong mỗi JAR, kiểm tra mục `META-INF/MANIFEST.MF` bằng công cụ xem ZIP/JAR, xác nhận:

- `agent-on.jar` có `Premain-Class` và `Can-Retransform-Classes: true`.
- `agent-off.jar` có `Premain-Class` nhưng **không** có `Can-Retransform-Classes`.
- Hai JAR đều có class entry point và transformer cần thiết.

**Không** chỉ nhìn file `agent-on.mf` ngoài thư mục mà cho rằng JAR được build từ file đó: với hệ thống CI/CD, bước shading/packaging có thể vô tình thay manifest.

## 5. Thứ tự kiểm tra trong agent production

Một luồng quyết định an toàn:

```text
Agent entry point đã được JVM gọi?
    |
    ├─ không: kiểm tra manifest entry point, -javaagent hoặc Attach
    |
    └─ có: nhận Instrumentation
             |
             v
       isRetransformClassesSupported() ?
             |
             ├─ false:
             |   ├─ log capability unavailable
             |   ├─ có thể chỉ quan sát future class loads bằng transformer false
             |   └─ không gọi retransformClasses
             |
             └─ true:
                  |
                  v
              addTransformer(transformer, true)
                  |
                  v
              xác định lớp đã nạp cần xử lý
                  |
                  v
              isModifiableClass(clazz) ?
                  |
                  ├─ false → skip/ghi lý do
                  |
                  └─ true → retransformClasses(clazz)
                                |
                                v
                         kiểm tra thành công hoặc exception
                                |
                                v
                          xác minh hành vi runtime
```

Không nên coi log “registered transformer” là bằng chứng đã retransform thành công; đăng ký chỉ thiết lập khả năng callback trong những trường hợp được yêu cầu. Tương tự, capability `true` không có nghĩa JVM đã tự động gọi `transform(...)` trên mọi class trước đây.

**Khi cần xử lý các lớp đang nạp**, có thể dùng `Instrumentation.getAllLoadedClasses()` để tìm ứng viên, nhưng nên hạn chế theo scope, `isModifiableClass`, các loader liên quan và giới hạn công việc. Danh sách lớp đã nạp không phải danh sách lớp đều cần/được phép instrument.

## 6. Vì sao `addTransformer(..., true)` và `retransformClasses(...)` là hai bước khác nhau?

- `addTransformer(t, true)`: đăng ký **t** để có thể được callback khi class được load, redefine và retransform (nếu JVM/cấu hình hỗ trợ).
- `retransformClasses(clazz)`: **ra lệnh** JVM chạy lại chuỗi biến đổi cho **class đã nạp** ngay lúc đó. Nếu chưa gọi API này, đăng ký transformer true **không tự quay về quá khứ** để instrument mọi lớp đang tồn tại.

Khi JVM thực hiện retransform:

1. Bắt đầu từ bytes nền của class theo quy tắc JVM (liên quan tới lần load/redefine gần nhất), không phải mặc định đọc lại nguyên file JAR trên đĩa.
2. Với transformer đăng ký `canRetransform=false`: JVM **tái áp dụng hiệu ứng bytecode đã thu được** ở lần load/redefine trước; `transform` của nhóm này **không được gọi lại**.
3. Với transformer đăng ký `canRetransform=true`: JVM gọi lại `transform` theo thứ tự nhóm và thứ tự đăng ký.
4. Sau đó JVM kiểm tra và áp dụng định nghĩa mới nếu hợp lệ.

Đây là lý do một agent trước đó với `canRetransform=false` vẫn có thể để lại tác động trong bytes đang được retransform: **không gọi callback lại** không đồng nghĩa **hoàn nguyên hiệu ứng cũ**.

Lưu ý rằng bytes đầu vào của lần retransform không nhất thiết byte-for-byte trùng bytes từng đưa vào `ClassLoader.defineClass`: có thể khác cách bố trí constant pool, thứ tự mục hoặc một số attribute theo đặc tả. Transformer nên phân tích **mảng hiện tại**, không giả định offset của file class cũ.

## 7. Những giới hạn còn lại kể cả khi mọi cờ đều true

**`isRetransformClassesSupported() == true` và `isModifiableClass(clazz) == true` là điều kiện cần, không phải bằng chứng mọi thay đổi bytecode đều hợp lệ.**

### 7.1. Không tùy ý sửa schema của lớp

Theo giới hạn JVM TI tương ứng, retransform thường cho phép đổi **thân phương thức**, nhưng không tùy ý:

- Thêm, xóa hoặc đổi tên method/field.
- Đổi descriptor/signature của method theo cách làm thay đổi cấu trúc bị cấm.
- Đổi quan hệ kế thừa, các interface hoặc cấu trúc class không được phép.

Các hành động không được hỗ trợ có thể gây `UnsupportedOperationException`. Kể cả chỉ sửa mã của method cũng phải giữ class file hợp lệ, xử lý stack map frames, control flow và constant pool tương thích.

### 7.2. Không tự chạy lại static initializer

Retransformation **không tự gọi lại `<clinit>`** hoặc reset static fields. Nếu class đã khởi tạo, static state giữ nguyên trừ khi chính code có tác động khác. Nếu có frame đang thực thi method cũ, frame đang chạy có thể tiếp tục dùng bytecode cũ; các lời gọi mới sử dụng định nghĩa đã được áp dụng.

Vì thế đừng đặt kỳ vọng “gọi retransform là JVM reset class về trạng thái ban đầu” hoặc “mọi thread lập tức chuyển sang code mới ngay giữa method”.

### 7.3. Lỗi xảy ra sau khi đã qua bước capability

Một số ngoại lệ/lỗi được đặc tả:

| API / giai đoạn | Lỗi có thể gặp | Ý nghĩa |
| --- | --- | --- |
| `addTransformer(t, true)` | `UnsupportedOperationException` | JVM/cấu hình không cho phép retransformation. |
| `retransformClasses(clazz)` | `UnsupportedOperationException` | Không có capability hoặc biến đổi không được hỗ trợ. |
| `retransformClasses(clazz)` | `UnmodifiableClassException` | Class được chọn không modifiable. |
| `retransformClasses(clazz)` | `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError` và lỗi liên quan | Output class không hợp lệ, version không phù hợp hoặc liên kết thất bại. |
| `retransformClasses(null)` hoặc phần tử null | `NullPointerException` | Input không hợp lệ. |

Theo hợp đồng, nếu lời gọi `retransformClasses(...)` cho một tập lớp thất bại, **không lớp nào trong tập đó được retransformed**. Điều này hữu ích cho tính nhất quán, nhưng không loại bỏ nhu cầu ghi log, phân loại lỗi và chọn nhóm lớp cẩn thận.

Transformer có thể ném exception; theo `ClassFileTransformer`, JVM tiếp tục chuỗi như khi transformer ấy trả `null`. Do đó **lỗi Java trong transformer không phải một cơ chế chặn toàn bộ class loading/retransformation đáng tin cậy**. Mặt khác, trả bytes sai định dạng có thể khiến lần retransform thất bại khi JVM kiểm tra output.

### 7.4. Môi trường JVM, version và quyền

- Retransformation là một **optional capability**. Không hard-code mặc định rằng mọi JVM/VM configuration đều hỗ trợ.
- Khi dùng Attach API, vấn đề **có được nạp agent động hay không** lại phụ thuộc cơ chế attach, quyền, chính sách JVM và phiên bản JDK; nó khác với quyền retransform. Đừng trộn hai bài toán.
- Module boundaries và class loader còn ảnh hưởng tới khả năng agent **liên kết helper classes** hoặc truy cập thành phần cần instrument. Có capability retransform không tự mở mọi package bị encapsulate.
- Với một số class lõi đặc biệt, primitive/array, một số VM-defined class, việc sửa đổi có thể bị từ chối. Hãy hỏi `isModifiableClass` thay vì đoán từ tên lớp.
- Khả năng của VM không bảo đảm transformers khác đang chạy trong JVM tương thích với bytecode của bạn.

## 8. Trường hợp nhiều Java agent trong cùng một JVM

Mỗi **agent JAR** cần khai báo yêu cầu capability phù hợp với thao tác của agent đó. Đừng dựa vào việc “agent A đã có `Can-Retransform-Classes: true`, vì thế agent B không cần khai báo mà vẫn chắc chắn có quyền” — hãy kiểm tra chính `Instrumentation` mà JVM đưa vào agent B và manifest thực tế của từng JAR.

Giả sử:

```text
java -javaagent:monitor.jar -javaagent:coverage.jar -cp app.jar example.Main
```

Câu lệnh trên chỉ mang tính mô tả; với `-cp app.jar`, class `example.Main` phải thật sự tồn tại trong JAR/classpath ấy. Khi cả hai agent instrument cùng một lớp:

- Thứ tự gọi `premain` tuân theo thứ tự `-javaagent` trên command line, nếu cả hai khởi động bình thường.
- **Thứ tự biến đổi bytecode** còn chịu quy tắc nhóm: Java/native và `canRetransform=false/true`; trong mỗi nhóm giữ thứ tự đăng ký.
- Trong retransform, những transformer incapable không được gọi lại mà có thể được tái sử dụng hiệu ứng đã có; các transformer capable được gọi lại.
- Khi một agent đã nạp sớm một class, transformer của agent đăng ký muộn hơn có thể không thấy **lần định nghĩa ban đầu**. Nếu có capability và lớp modifiable, agent có thể yêu cầu retransform để xử lý.
- Thay thứ tự agent là cách điều tra tương tác, **không thay thế kiểm tra capability và thiết kế transformer idempotent**.

Nếu cùng một agent được nạp lại hoặc được truyền nhiều lần, chú ý tránh đăng ký transformer trùng và tránh retransform tự lặp. Chỉ số `supported=true` không nói gì về việc có **bao nhiêu transformer** đang tham gia hoặc chúng có thể phối hợp an toàn không.

## 9. Checklist triển khai và QA

Trước khi đưa retransform vào công cụ giám sát hoặc profiler:

1. **Kiểm tra JAR thực tế:** manifest có `Premain-Class` hoặc `Agent-Class` đúng cơ chế và `Can-Retransform-Classes: true`; file JAR trên server/CI là đúng artifact, không phải bản khác.
2. **Kiểm tra startup/load:** `premain` hoặc `agentmain` được gọi thành công; agent nhận được `Instrumentation`, không bị thiếu dependency hay lỗi classloader.
3. **Log capability runtime:** `isRetransformClassesSupported()` một cách rõ ràng. Nếu `false`, vận hành theo degraded mode (ví dụ chỉ instrument future loads) hoặc fail-fast theo chính sách sản phẩm.
4. **Đăng ký đúng kiểu transformer:** muốn callback lại khi retransform thì dùng `addTransformer(t, true)` sau khi capability đã được xác nhận. Đừng dùng `false` rồi chờ callback retransform.
5. **Chọn đúng class:** lớp đã được nạp, `isModifiableClass(clazz)` cho kết quả đúng; lọc package, module, defining loader và loại những class của agent nếu không cố ý can thiệp.
6. **Kiểm tra bytecode:** mọi bản `byte[]` trả về phải hợp lệ và tuân giới hạn retransform (schema không đổi); không sửa mảng `classfileBuffer` tại chỗ.
7. **Thử trên môi trường mục tiêu:** Java version, JVM vendor, flags, classloader, số lượng agent, module system và các security/policy có thể khác môi trường dev.
8. **Quan sát thực tế:** sau khi gọi `retransformClasses`, kiểm tra callback mong đợi và hành vi mới nếu có; không kết luận thành công chỉ từ log đăng ký transformer.
9. **Gỡ đăng ký và cleanup:** khi dừng agent, có thể gọi `removeTransformer(t)`. Việc gỡ **không tự hoàn nguyên** code đã được áp dụng vào class và callback đang chạy có thể vẫn đến sau thao tác gỡ.
10. **Phương án lỗi:** chỉ gửi nhóm class đủ điều kiện, phân loại `UnsupportedOperationException`/`UnmodifiableClassException`/lỗi class format, và định nghĩa rõ trạng thái hoạt động khi không có capability.

Đặc biệt trong production, không nên dùng `retransformClasses` như một thao tác vô hại có thể lặp lại liên tục trên toàn JVM. Nó có chi phí, tác động đến tải class, và có thể tương tác với các agent khác.

## 10. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân / cách xử lý |
| --- | --- |
| `isRetransformClassesSupported() == false` trên JVM vốn có vẻ hỗ trợ | Kiểm tra **manifest của JAR agent đang chạy**: thiếu `Can-Retransform-Classes: true` là nguyên nhân thường gặp. Nếu manifest đúng, JVM/cấu hình có thể không hỗ trợ. |
| `isModifiableClass(Target.class) == true` nhưng không retransform được | `isModifiableClass` độc lập capability; kiểm tra `isRetransformClassesSupported()` trước. |
| `addTransformer(t, true)` ném `UnsupportedOperationException` | Capability chưa được cấp/supported, hoặc cờ manifest không hợp lệ. Đừng retry vô hạn bằng cùng cấu hình. |
| Chỉ thấy `phase=load`, không thấy callback lúc đã nạp | Kiểm tra đã gọi `retransformClasses(...)` chưa; transformer có đăng ký `canRetransform=true` không. |
| `retransformClasses(...)` ném `UnmodifiableClassException` | Kiểm tra `isModifiableClass(clazz)` và loại primitive/array/các lớp VM không hỗ trợ. |
| Nạp được agent qua attach nhưng retransform báo không hỗ trợ | Hai cơ chế khác nhau; kiểm tra manifest `Agent-Class`, `Can-Retransform-Classes` và JVM capability. |
| `Can-Redefine-Classes: true` nhưng retransform false | Đây là hai capability độc lập; thêm cờ retransform nếu cần, và JVM vẫn phải hỗ trợ. |
| Re-transform thành công nhưng application không đổi output | Transformer có thể chỉ trả `null` như ví dụ; hoặc thay đổi chưa tác động luồng kiểm tra, hoặc frame cũ vẫn đang chạy. |
| Error/VerifyError sau callback retransform | Kiểm tra classfile bytes, stack maps, constant pool, method descriptors, giới hạn schema và transformer đứng trước. |
| `-javaagent` thứ nhất hỗ trợ, thứ hai không | Kiểm tra manifest và `Instrumentation` của **từng agent**; không giả định cùng capability cho mọi agent. |
| Manifest text đúng nhưng runtime false | Xác nhận nội dung `META-INF/MANIFEST.MF` **trong đúng JAR chạy**; bước package/shade có thể thay manifest. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Agent có `Premain-Class` đúng nhưng không khai báo `Can-Retransform-Classes`. JVM có bắt buộc hỗ trợ retransform cho agent không?

**Đáp án:** Không. Giá trị manifest mặc định là `false`, nên `isRetransformClassesSupported()` trả `false` theo hợp đồng, dù JVM implementation có khả năng chung.

**Câu 2.** `isModifiableClass(MyClass.class) == true`. Có thể gọi `retransformClasses(MyClass.class)` ngay không?

**Đáp án:** Chưa đủ. Cần `isRetransformClassesSupported() == true`, class đã nạp hợp lệ, và bytes của kết quả phải thỏa quy tắc JVM.

**Câu 3.** Muốn transformer nhận callback khi retransform, đăng ký bằng `addTransformer(transformer, false)` có đủ không?

**Đáp án:** Không. Phải đăng ký `true` khi JVM hỗ trợ; nhóm `false` không được gọi lại trong retransformation.

**Câu 4.** `Can-Redefine-Classes: true` có thay được `Can-Retransform-Classes: true` không?

**Đáp án:** Không. `redefineClasses` và `retransformClasses` là hai capability độc lập, có mục đích khác nhau.

**Câu 5.** Nếu class không modifiable mà agent cố gọi retransform, lỗi nào được đặc tả?

**Đáp án:** `UnmodifiableClassException`. Agent nên kiểm tra `isModifiableClass(clazz)`, đồng thời vẫn xử lý exception khi gọi API.

**Câu 6.** Nếu retransform thành công và transformer trả `null`, JVM có nhất thiết thay output của `Target.message()` không?

**Đáp án:** Không. `null` nghĩa là không sửa bytes. Callback vẫn có thể đã được gọi thành công và class được xử lý lại nhưng hành vi không đổi.

**Câu 7.** Tại sao trong ví dụ `agent-off.jar` in `modifiable=true` mà vẫn in `skip retransform`?

**Đáp án:** Vì `isModifiableClass` không phụ thuộc kết quả `isRetransformClassesSupported`. JVM của thí nghiệm cho phép class này có khả năng sửa đổi, nhưng manifest của agent không yêu cầu retransformation nên capability runtime là `false`.

**Câu 8.** Có thể bật `Can-Retransform-Classes` sau khi agent đã khởi động chỉ bằng cách đổi file manifest trên đĩa?

**Đáp án:** Không. Manifest được JVM đọc khi agent được nạp và capability được xác định theo cấu hình; thay file sau đó **không nâng quyền trên `Instrumentation` đang có**. Cần thiết kế lại quá trình khởi động/nạp theo yêu cầu, không giả định hot-edit manifest có tác dụng.

**Câu 9.** Transformer `false` không được gọi lại khi retransform. Có chắc ảnh hưởng trước đó của nó mất đi?

**Đáp án:** Không. Theo Java Instrumentation API, ảnh hưởng của transformer retransformation-incapable được JVM tái áp dụng từ lần load/redefine trước.

## 12. Tổng kết và tài liệu chính thức

Trước khi dùng `retransformClasses`, hãy ghi nhớ chuỗi điều kiện:

**Manifest `Can-Retransform-Classes: true` → JVM hỗ trợ `isRetransformClassesSupported()` → lớp cụ thể `isModifiableClass(clazz)` → đăng ký `addTransformer(..., true)` → gọi `retransformClasses(...)` → kiểm tra output hợp lệ và hành vi thực tế.**

Cả ba câu hỏi **“agent đã xin quyền chưa?”**, **“JVM đã hỗ trợ chưa?”** và **“class này có sửa được không?”** đều cần được trả lời. Không dùng `Premain-Class`, `Can-Redefine-Classes` hoặc `isModifiableClass` thay thế cho điều kiện retransform.

Tài liệu chuẩn:

1. **Java SE 17 API — `Instrumentation`**: `isRetransformClassesSupported`, `addTransformer`, `isModifiableClass`, `retransformClasses` và các ngoại lệ: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
2. **Java SE 17 API — `java.lang.instrument`**: manifest `Can-Retransform-Classes`, `Premain-Class`, `Agent-Class` và mặc định `false`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. **Java SE 17 API — `ClassFileTransformer`**: callback, thứ tự transformer, tham số `classBeingRedefined` và quy tắc `null`/`byte[]`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **JVMTI Specification — `RetransformClasses`**: capability và giới hạn thay đổi lớp: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RetransformClasses
5. **Java SE 17 Tool Guide — `java` launcher**: cách sử dụng `-javaagent`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html