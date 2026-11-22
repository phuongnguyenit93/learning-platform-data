# Viết transformer chỉ ghi nhận lớp đích và trả null

## 1. Mục tiêu của thực nghiệm

Trong Java Instrumentation, bước thực hành an toàn nhất trước khi bắt đầu sửa bytecode là tạo **một Java agent thật**, đăng ký `ClassFileTransformer`, nhận biết chính xác **class đích** khi JVM đang định nghĩa nó, **ghi một dấu mốc quan sát được**, rồi **trả `null`**.

Đề bài **“Viết transformer chỉ ghi nhận lớp đích và trả null”** yêu cầu hiểu đúng hai hành vi độc lập:

1. **Ghi nhận (observe):** chỉ khi tên class được JVM cung cấp khớp với class đích, transformer mới in log hoặc ghi sự kiện chẩn đoán.
2. **Không biến đổi (no-op transformation):** transformer **luôn trả `null`**, kể cả với class đích. Theo hợp đồng Java SE, `null` nghĩa là **transformer này không tạo classfile thay thế**. JVM tiếp tục quá trình class loading với bytes từ bước trước và những transformers còn lại, nếu có.

Bài sẽ xây một agent dùng **Java 17+**, không cần ASM, Byte Buddy, thư viện ngoài hoặc quyền retransform/redefine. Demo có hai classes ứng dụng: `demo.Unrelated` làm đối chứng **không được ghi log**, và `demo.Target` là class cần quan sát. Khi tạo hai instance của `Target`, log target xuất hiện **một lần** trong thí nghiệm vì JVM định nghĩa class một lần cho cùng class loader.

Bạn sẽ học được:

- Chữ ký và ý nghĩa các tham số của `ClassFileTransformer.transform`.
- Tại sao so sánh `"demo/Target"` thay vì `"demo.Target"`.
- Cách đăng ký transformer trong `premain`.
- Khác biệt giữa `return null`, `return originalBytes`, `return modifiedBytes` và `throw`.
- Vì sao ghi được log không đồng nghĩa class đã được định nghĩa thành công.
- Cách biên dịch Java 17, tạo manifest/JAR và chạy với `-javaagent`, `-Xverify:all`.
- Cách đối chiếu stdout khi **có** và **không** có agent để bảo đảm logic của app không đổi.
- Cách giới hạn overhead, quản lý class loader/module, xử lý lỗi và mở rộng demo có kiểm soát.

## 2. Điều gì xảy ra khi JVM nạp một class?

Một class được JVM sử dụng qua các giai đoạn: tìm bytes từ class loader, biến đổi classfile khi có transformers, xác minh định dạng/bytecode, định nghĩa class, liên kết và khởi tạo tại những thời điểm thích hợp.

Trong demo:

~~~text
Ứng dụng gọi: new demo.Target()
                 |
                 v
Class loader chuẩn bị define "demo/Target"
                 |
                 v
Instrumentation gọi transformer
                 |
                 +--> className có phải "demo/Target"?
                         |
                         +--> Không: return null, không in log
                         |
                         +--> Có:
                               in "transform:seen=demo/Target"
                               in "transform:redefine=false"
                               return null
                 |
                 v
JVM tiếp tục định nghĩa class từ bytes không bị transformer này đổi
                 |
                 v
Target.greet("Java") -> "Hello, Java"
~~~

**Cần phân biệt thời điểm:** `transform` được gọi **trước khi quá trình định nghĩa class hoàn tất**. Trong callback, bạn biết JVM đang xử lý bytes của class mục tiêu; bạn **chưa thể từ log ấy một mình khẳng định JVM đã verify và define thành công**. Bằng chứng tiếp theo trong demo là ứng dụng tạo instance rồi gọi method và nhận đúng giá trị.

Nếu JVM có **nhiều agents/transformers**, việc một transformer trả `null` chỉ nói rằng **transformer đó không thay bytes**. Một transformer khác vẫn có thể sửa classfile. Do đó, không tuyên bố `return null` bảo đảm **toàn JVM** không hề có bytecode modification.

## 3. Hợp đồng ClassFileTransformer ở Java 17

Interface công khai:

~~~java
java.lang.instrument.ClassFileTransformer
~~~

Chữ ký overload năm tham số mà demo sử dụng:

~~~java
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Trong source Java hoàn chỉnh phải import `java.lang.instrument.ClassFileTransformer` và `java.security.ProtectionDomain`. Từ Java 9, interface còn có overload mang tham số `Module`, được giải thích ở mục 12.

| Tham số | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| `loader` | ClassLoader định nghĩa class | Có thể `null` đối với bootstrap loader |
| `className` | Tên class dạng **internal form** | Dùng slash: `demo/Target`; có thể cần xử lý `null` an toàn |
| `classBeingRedefined` | `Class<?>` nếu callback do redefine/retransform | **`null`** trong lần class load ban đầu |
| `protectionDomain` | ProtectionDomain của class | Phục vụ kiểm soát ngữ cảnh bảo vệ, không dùng để phán đoán class name |
| `classfileBuffer` | Input bytes của classfile | **Không được sửa trực tiếp mảng input này** |

### 3.1. Giá trị trả về

- `return null;` — **không có transform** từ transformer hiện tại.
- `return newBytes;` — cung cấp **một classfile hợp lệ** để pipeline tiếp tục; trách nhiệm tạo/verifier hợp lệ thuộc bên transform.
- `return classfileBuffer;` — không cần làm trong demo no-op. Đây không phải cách tốt hơn để nói “không sửa”; nó trả mảng bytes và tạo đường xử lý khác với ý định no-op.
- Ném `IllegalClassFormatException` hoặc unchecked exception — **không phải cách được bảo đảm để chặn class load**. Javadoc quy định các transformer còn lại vẫn được gọi; đối với callback ném exception, xử lý tương đương `null`.

Với bài thực hành này, đáp án mong muốn là:

~~~java
if ("demo/Target".equals(className)) {
    System.out.println("transform:seen=" + className);
}
return null;
~~~

Đoạn trên chỉ minh họa phần logic, chưa chứa toàn bộ class/manifest. **Không** sửa `classfileBuffer`, không cần parser bytecode, không đổi tên method hoặc thêm field.

### 3.2. Trả null không có nghĩa “bỏ qua việc nạp class”

Dễ nhầm `return null` như một kiểu “cấm JVM load class này”. Ý nghĩa thực tế là **transformer không gửi bytes thay thế**. JVM vẫn cố định nghĩa class bằng bytes của pipeline. Nếu bytes cuối hợp lệ và điều kiện class loading đáp ứng, class vẫn được nạp và ứng dụng tiếp tục.

Trong demo, mặc dù `Target` được ghi nhận và callback trả null, method `Target.greet` chạy bình thường, cho kết quả y như khi không có agent.

## 4. Thiết kế đúng phạm vi: một target, còn lại im lặng

Bài sử dụng class name cố định:

~~~text
demo.Target           Binary name trong source Java
demo/Target           Internal name trong ClassFileTransformer
Ldemo/Target;         Descriptor biểu diễn reference type trong JVM
demo/Target.class     Tên file entry class trong JAR/thư mục
~~~

Đừng đem nguyên `demo.Target` vào điều kiện `className.equals(...)`. Khi callback nhận `"demo/Target"`, so sánh dạng dấu chấm sẽ trả false và agent sẽ **không in log**.

Viết điều kiện theo hướng an toàn:

~~~java
if (!"demo/Target".equals(className)) {
    return null;
}
~~~

Đặt literal ở phía trái giúp code không ném `NullPointerException` nếu `className` là null. Với classes khác đích, transformer **không log** và trả `null` ngay.

Một số hướng phát triển khác có thể quan sát namespace, package hoặc class loader, nhưng không cần trong lab cơ bản. Giữ filter càng cụ thể càng dễ đối chiếu.

### 4.1. Vì sao lại tạo Unrelated?

Nếu chỉ có một class `Target`, một log xuất hiện chưa chứng minh bộ lọc không log các class khác. Vì thế ứng dụng sẽ cố tình load thêm `demo.Unrelated` **trước** `demo.Target`. Output với agent chỉ có dòng `transform:seen=demo/Target`, không có dòng `transform:seen=demo/Unrelated`.

### 4.2. Vì sao tạo hai instance Target?

Để phân biệt **class loading** với **object creation**. Một class được JVM định nghĩa theo identity gồm tên nhị phân và defining class loader, không phải mỗi lần `new` lại định nghĩa class.

Trong thí nghiệm, hai đối tượng `new Target()` trên cùng application class loader dẫn tới **một** lần transformer nhìn thấy `demo/Target`, vì callback được gọi ở lần định nghĩa class đầu tiên. Đây không phải quy tắc “mọi JVM sẽ log đúng một lần vĩnh viễn”: một class cùng tên có thể được định nghĩa bởi class loader khác, hoặc một agent có cấu hình lại/redefine/retransform có thể làm callback chạy lại tùy điều kiện.

## 5. Cấu trúc lab

Tạo thư mục:

~~~text
target-only-null-agent/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── agent/
│   │           └── TargetOnlyAgent.java
│   └── app/
│       └── demo/
│           ├── Main.java
│           ├── Target.java
│           └── Unrelated.java
└── out/                      # sinh sau khi build
    ├── agent/
    ├── app/
    └── target-only-agent.jar
~~~

Không cần Maven hoặc Gradle cho thí nghiệm này. `javac` và `jar` từ JDK là đủ.

**Môi trường đã kiểm chứng:** mã biên dịch bằng `javac 24.0.2 --release 17`, chạy bằng `java 24.0.2 -Xverify:all`. Vì source sử dụng API `java.lang.instrument` đã có trong Java 17, có thể chạy trên JDK 17+ tương thích; với production cần chạy integration tests trên chính JDK/vendor mà bạn hỗ trợ.

## 6. Agent hoàn chỉnh: chỉ log target và return null

Tệp **`src/agent/demo/agent/TargetOnlyAgent.java`**:

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class TargetOnlyAgent {
    public static void premain(
            String args, Instrumentation inst) {

        System.out.println("agent:premain");

        inst.addTransformer(
                new TargetOnlyTransformer(),
                false);

        System.out.println("agent:registered");
    }

    static final class TargetOnlyTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] originalBytes) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            System.out.println(
                    "transform:seen=" + className);

            System.out.println(
                    "transform:redefine="
                    + (classBeingRedefined != null));

            return null;
        }
    }
}
~~~

Đây là **source Java hoàn chỉnh, tự biên dịch được** bằng JDK 17+. Nó không import `jdk.internal.*`, ASM, Byte Buddy hay bất kỳ thư viện bên ngoài.

### 6.1. Giải thích từng khối

**`premain(String, Instrumentation)`**

- Là entry point của startup Java agent khi JVM đọc `Premain-Class` từ manifest.
- JVM tự cung cấp đối tượng `Instrumentation`; ứng dụng không tự `new Instrumentation()`.
- Log `agent:premain` giúp xác nhận entry point được gọi.
- `addTransformer(..., false)` đăng ký transformer **không có khả năng retransform**; đủ để quan sát class đích khi nó được nạp trong demo.
- Log `agent:registered` chỉ xuất hiện sau lệnh đăng ký hoàn tất. Đây là dấu mốc registration, **không phải bằng chứng target đã được nạp**.

**`TargetOnlyTransformer`**

- Được đặt là nested static class để lab chỉ cần một tệp nguồn agent.
- Implement `ClassFileTransformer` bằng overload năm tham số.
- Nhận `className` ở dạng internal name, so sánh đúng `demo/Target`.
- Khi không khớp, trả null ngay và không ghi log.
- Khi khớp, ghi tên lớp và kiểm tra `classBeingRedefined != null`.
- Dù là class đích, cuối cùng vẫn **`return null`**: không thay bytes của class.

**`classBeingRedefined` trong demo**

Vì transformer được gọi ở **lần load đầu**, biến này bằng null; log `transform:redefine=false`. Nếu callback đến từ redefine hoặc retransform (trong một agent được thiết kế khác), biến có thể không null. Không thể dùng log này để biết JVM đã verify xong classfile hay chưa.

### 6.2. Tại sao không cần Can-Retransform-Classes?

`inst.addTransformer(transformer, false)` đăng ký transformer có `canRetransform=false`. Không gọi `retransformClasses`, không gọi `redefineClasses`. Do đó manifest không cần:

~~~text
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Hai dòng trên chỉ để đối chiếu những capability **không yêu cầu** trong lab, không được thêm vào manifest của ví dụ. Nếu sau này muốn quan sát class đã load bằng retransformation, phải thiết kế riêng và kiểm tra cả VM support lẫn manifest capability.

### 6.3. Có nên giữ object transformer để xóa sau này?

Trong lab, transformer chỉ được đăng ký một lần và sống cho tới khi JVM kết thúc, nên không cần field tham chiếu. Trong ứng dụng thực, nếu muốn `inst.removeTransformer(transformer)`, bạn phải lưu tham chiếu tới **chính instance đã đăng ký**. Tạo `new TargetOnlyTransformer()` khác sẽ không xóa transformer cũ.

Đồng thời, vì class loading có thể đồng thời, callback có thể vẫn xuất hiện trong một khoảng ngắn sau `removeTransformer`. API không đảm bảo gỡ transformer là rollback mọi class đã từng được biến đổi — trong lab không có bytes nào được biến đổi nên cũng không cần rollback class.

## 7. Ứng dụng demo: Target và Unrelated

Tệp **`src/app/demo/Target.java`**:

~~~java
package demo;

public final class Target {
    public String greet(String value) {
        return "Hello, " + value;
    }
}
~~~

Tệp **`src/app/demo/Unrelated.java`**:

~~~java
package demo;

public final class Unrelated {
    public String ping() {
        return "OK";
    }
}
~~~

Tệp **`src/app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("main:start");

        System.out.println(
                "main:other=" + new Unrelated().ping());

        System.out.println("main:before-target");

        Target first = new Target();

        System.out.println(
                "main:result=" + first.greet("Java"));

        System.out.println(
                "main:second="
                + new Target().greet("World"));

        System.out.println("main:end");
    }
}
~~~

**Thứ tự có mục đích:**

1. `main:start` chứng minh application main đã bắt đầu **sau `premain`**.
2. `new Unrelated()` yêu cầu JVM load class đối chứng; transformer trả null **không log**, vì không phải `demo/Target`.
3. `main:before-target` làm dấu thời gian trước khi class đích được tạo instance.
4. Lần đầu `new Target()` kích hoạt class loading nếu class chưa được define trước đó.
5. Transformer quan sát target, in `transform:seen=demo/Target`, rồi return null.
6. `greet("Java")` vẫn trả `Hello, Java`.
7. Lần `new Target()` thứ hai không tự động làm JVM define lại cùng class, nên không in thêm target hit trong lab.
8. `main:end` xác nhận chương trình chạy hết bình thường.

Vì demo dựa trên thứ tự nạp class, hãy chạy từ **JVM mới** và đừng thêm một agent khác hoặc code initialization khác nạp sẵn `Target` trước `Main` nếu muốn stdout đúng hệt.

## 8. Manifest: bắt buộc để -javaagent tìm được premain

Tệp **`agent.mf`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.TargetOnlyAgent

~~~

**Quan trọng:**

- `Premain-Class` chứa **binary class name** với dấu chấm: `demo.agent.TargetOnlyAgent`, khác với internal class name `demo/Target` bên trong transformer.
- Manifest cần có newline phù hợp, và ở bản thực hành dùng thêm một dòng trống cuối.
- Java agent JAR phải chứa cả `TargetOnlyAgent.class` và nested `TargetOnlyAgent$TargetOnlyTransformer.class`. `jar -C out/agent .` sẽ gom đúng cả hai.
- `Main-Class` không cần thiết cho JAR agent, vì application chạy riêng qua `-cp out/app demo.Main`.
- `Agent-Class` không cần thiết vì demo không hỗ trợ dynamic attach.
- Không cần `Can-Redefine-Classes` hay `Can-Retransform-Classes` như đã giải thích.

**Tránh lỗi rất thực tế:** một source agent compile thành công nhưng final JAR không có `Premain-Class` đúng vẫn khiến `java -javaagent:...` fail **trước khi ứng dụng chạy**. Luôn kiểm tra JAR thực tế.

## 9. Build từng bước với javac, jar

Đứng ở thư mục gốc `target-only-null-agent`.

Nếu dùng Bash:

~~~bash
mkdir -p out/agent out/app
~~~

Nếu dùng PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

Biên dịch **agent** (Java 17 target):

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/TargetOnlyAgent.java
~~~

Biên dịch **ứng dụng**:

~~~bash
javac --release 17 -d out/app src/app/demo/Main.java src/app/demo/Target.java src/app/demo/Unrelated.java
~~~

Đóng gói agent:

~~~bash
jar --create --file out/target-only-agent.jar --manifest agent.mf -C out/agent .
~~~

**Không cần thêm ứng dụng vào agent JAR.** Ứng dụng dùng classpath `out/app`, agent dùng JAR riêng. Cách này giúp thấy rõ vai trò của `-javaagent` so với app classes.

Kiểm tra nội dung JAR:

~~~bash
jar --list --file out/target-only-agent.jar
~~~

Các entries quan trọng dự kiến:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/agent/
demo/agent/TargetOnlyAgent.class
demo/agent/TargetOnlyAgent$TargetOnlyTransformer.class
~~~

JAR có thể có thêm directory entries hay thứ tự khác tùy công cụ; không exact-match toàn bộ danh sách. Điều bắt buộc là **manifest và các agent classes có mặt**.

### 9.1. Kiểm tra manifest thực

Trên hệ thống có `unzip`:

~~~bash
unzip -p out/target-only-agent.jar META-INF/MANIFEST.MF
~~~

Nếu không có `unzip`, dùng `jar --extract` trong một **thư mục tạm**:

~~~bash
jar --extract --file out/target-only-agent.jar META-INF/MANIFEST.MF
~~~

Lệnh này ghi `META-INF/MANIFEST.MF` vào working directory; vì vậy **nên thực hiện trong thư mục kiểm tra tạm** để không ghi đè đường dẫn đang có. Đọc file vừa trích và xác nhận `Premain-Class: demo.agent.TargetOnlyAgent`.

### 9.2. Quét dependency nội bộ của JDK

~~~bash
jdeps --jdk-internals out/target-only-agent.jar
~~~

Agent demo chỉ dùng APIs công khai `java.lang.instrument`, `java.lang` và `java.security`, không phụ thuộc ASM nội bộ hay JDK internal API. Công cụ `jdeps` giúp phát hiện static dependencies, nhưng không thay thế kiểm thử runtime.

## 10. Đối chứng 1: chạy ứng dụng không có agent

Chạy:

~~~bash
java -Xverify:all -cp out/app demo.Main
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
main:start
main:other=OK
main:before-target
main:result=Hello, Java
main:second=Hello, World
main:end
~~~

Điều này thiết lập baseline:

- `Unrelated.ping()` trả `OK`.
- Hai lần gọi `Target.greet` lần lượt trả `Hello, Java` và `Hello, World`.
- Không có bất kỳ dòng nào bắt đầu bằng `agent:` hoặc `transform:`.
- Chương trình kết thúc bình thường, không có lỗi verifier.

Baseline là điều kiện quan trọng để đánh giá agent có thay behavior không. Nếu logic ứng dụng đã sai khi không có agent, không nên quy tất cả lỗi cho transformer.

## 11. Đối chứng 2: chạy cùng ứng dụng với -javaagent

Chạy:

~~~bash
java -Xverify:all -javaagent:out/target-only-agent.jar -cp out/app demo.Main
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
agent:premain
agent:registered
main:start
main:other=OK
main:before-target
transform:seen=demo/Target
transform:redefine=false
main:result=Hello, Java
main:second=Hello, World
main:end
~~~

### 11.1. So sánh trước/sau

| Tiêu chí | Không agent | Có agent |
|---|---|---|
| Log `agent:premain` | Không | Có |
| Log `agent:registered` | Không | Có |
| Log `transform:seen=demo/Target` | Không | Có, **một lần** trong lab |
| Log cho `demo/Unrelated` | Không | Không |
| `main:other` | `OK` | `OK` |
| `Target.greet("Java")` | `Hello, Java` | `Hello, Java` |
| `Target.greet("World")` | `Hello, World` | `Hello, World` |
| Thoát bình thường | Có | Có |
| Biến đổi bytecode bởi transformer này | Không có | **Không có** (`return null`) |

**Bằng chứng bài thực hành đạt yêu cầu:**

1. `premain` chạy và đăng ký transformer trước khi `main` bắt đầu.
2. `demo.Unrelated` được tạo mà **không có log transformer tương ứng**, xác nhận bộ lọc giữ im lặng đối với class khác.
3. Khi JVM định nghĩa `demo.Target`, callback ghi đúng tên nội bộ.
4. `classBeingRedefined == null` trong lần load ban đầu → `transform:redefine=false`.
5. Cả hai đối tượng `Target` vẫn chạy đúng logic gốc; transformer không cấp replacement bytes.
6. Với một defining class loader, `Target` được define một lần dù code tạo hai instances.

Không in `class:transformed=true` trong lab. Log chính xác hơn là **observed/seen**; lớp này **được ghi nhận**, chứ không bị rewrite bởi transformer.

## 12. Từ Java 9: overload có Module và chuyện tương thích

Java 17 `ClassFileTransformer` có hai overload mặc định của `transform`. Trong bài, ta override phiên bản **năm tham số**:

~~~java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Từ Java 9, overload **sáu tham số** bổ sung `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Trong Java SE 17, triển khai mặc định của overload có `Module` **gọi lại overload năm tham số**. Vì vậy agent demo override phương thức năm tham số vẫn quan sát được class trên JVM hiện đại, kể cả khi VM có thể cung cấp thông tin module.

**Trích đoạn sau chỉ minh họa nâng cấp cách quan sát** (không thay thế toàn bộ source demo):

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain,
        byte[] originalBytes) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    String moduleName =
            module != null && module.isNamed()
            ? module.getName() : "unnamed";

    System.out.println("target-module=" + moduleName);
    return null;
}
~~~

Nếu override overload sáu tham số, bạn có thể đọc `module` trực tiếp. Tuy nhiên, **không tự giả định** JVM sẽ gọi cả hai overload: default 6-arg chỉ chuyển tiếp 5-arg khi 6-arg không được override. Chọn **một** kiểu tổ chức rõ ràng và test callback đúng.

### 12.1. Class loader là một phần identity

Hai class loaders khác nhau có thể định nghĩa **hai class cùng binary name `demo.Target`**. Bộ lọc chỉ dùng `className` có thể ghi nhận cả hai. Trong lab chỉ có một application class loader nên đúng một hit.

Với production agent, muốn quan sát **một class identity cụ thể**, cân nhắc phối hợp:

- Tên class nội bộ;
- `ClassLoader` identity và origin/code source;
- `Module` đối với named module;
- nguồn artifact/packaging nếu chính sách cho phép;
- thời điểm load vs retransform/redefine.

Đừng gọi `loader.toString()` không điều kiện: `loader` có thể null nếu bootstrap, và `toString`/formatting phức tạp trong callback có thể kích hoạt class loading khác.

### 12.2. Nếu className null hoặc đang ở bootstrap phase

Viết `"demo/Target".equals(className)` an toàn với null. Không ghi log mù quáng cho mọi invocation vì transformer nhận nhiều classes hệ thống khi JVM bootstrap; logging có thể bị reentrancy, performance overhead hoặc initialization-order issues.

## 13. Return null khác gì những phương án khác?

### 13.1. Return null — không thay đổi từ transformer hiện tại

~~~java
@Override
public byte[] transform(
        ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain, byte[] originalBytes) {

    if ("demo/Target".equals(className)) {
        System.out.println("observed-target");
    }
    return null;
}
~~~

Đây là trích đoạn nằm trong class implement `ClassFileTransformer`, không phải chương trình độc lập. `null` nói với JVM không có classfile thay thế từ transformer này.

### 13.2. Return originalBytes — không cần và dễ gây hiểu sai

~~~java
return originalBytes;
~~~

Điều này cung cấp **byte buffer đầu vào như kết quả**, thay vì sử dụng giá trị đặc biệt `null` để báo không biến đổi. Nó không cần thiết trong lab; tốt hơn là luôn trả null khi bạn không thực sự sinh một classfile mới.

Hơn nữa, **không được mutate `originalBytes`**; nếu một transformer sửa trực tiếp input để “thử” rồi return null, bạn đã vi phạm hợp đồng không mutate input. Khi cần transform thật, dùng một mảng output mới hợp lệ, test verifier và classfile semantics.

### 13.3. Return modifiedBytes — bài toán khác

~~~java
return transformedClassfileBytes;
~~~

Đây là pseudocode: cần một biến `transformedClassfileBytes` chứa classfile hoàn chỉnh. Muốn tạo bytes mới có thể dùng OW2 ASM, Byte Buddy hoặc Java `java.lang.classfile` từ JDK 24+, nhưng **không phải mục tiêu bài này**.

Từ chỗ quan sát target tới biến đổi bytecode là một bước chất lượng khác: phải bảo toàn stack maps, methods, exception semantics, class loader/module visibility và quy tắc không đổi schema khi class đã loaded.

### 13.4. Throw — không phải cách từ chối class được hỗ trợ

Javadoc quy định callback transformer ném exception không bắt tương đương trả null đối với transformer đó; JVM vẫn thử các bước còn lại. Vì vậy `throw new RuntimeException(...)` để “block target class” là sai mục tiêu.

Bài thực hành **không tạo exception cố ý** trong callback, vì nó chỉ cần ghi nhận class name và trả null.

## 14. Lưu ý về class loading, retransformation và redefinition

### 14.1. Class đã load trước khi transformer được đăng ký

`addTransformer` không có nghĩa JVM sẽ gọi lại callback với **tất cả classes đã được nạp trước đó**. Transformer thường nhận các lần class definition **tương lai** và những hoạt động redefine/retransform phù hợp.

Nếu `demo.Target` đã load trước khi bạn đăng ký transformer, việc gọi thêm `new Target()` không bắt buộc tạo callback mới. Đó là một nguyên nhân rất phổ biến khiến người học tưởng filter sai, dù thực tế là **đăng ký quá muộn**.

Với `-javaagent` và `premain`, code ứng dụng `Main.main` chỉ bắt đầu sau khi agent entry point đã return. Vì vậy demo có khả năng nhận lần load đầu của `Target`, miễn không có code khác làm nó load trước.

### 14.2. Muốn quan sát class đã load là một bài khác

Để retransform class đã load, không thể chỉ đổi `false` thành `true` một cách mù quáng:

- Manifest cần `Can-Retransform-Classes: true`.
- JVM phải báo `inst.isRetransformClassesSupported() == true`.
- Transformer phải được đăng ký `addTransformer(transformer, true)`.
- Agent cần có đúng đối tượng `Class<?>` và class phải modifiable.
- Gọi `inst.retransformClasses(targetClass)` khi được phép.
- Hạn chế schema/VM vẫn áp dụng; `return null` vẫn là no-op từ transformer.

Trong Java Instrumentation, `addTransformer(transformer, false)` **không nhận callback khi class được retransform** theo cách retransformation capable, nhưng vẫn có thể tham gia đường class load và redefinition theo hợp đồng. Không thể lấy số log từ demo rồi suy ra số lần `retransformClasses` trong agent khác.

### 14.3. Class đã được define, method có được gọi không?

Log transformer `transform:seen=demo/Target` chỉ là dấu mốc **class load path**. Một class có thể được load nhưng chưa khởi tạo, chưa tạo object hoặc chưa thực thi method. Ngược lại, một class được nạp trước khi bạn đăng ký transformer có thể thực thi nhiều lần mà không có log.

Phân biệt telemetry:

~~~text
transform:seen=demo/Target      -> JVM chuẩn bị xử lý class bytes
main:result=Hello, Java        -> method đã thực thi và trả kết quả
main:second=Hello, World       -> method được gọi tiếp, không define lại class
~~~

Đừng gọi một transformer chỉ ghi class name là **method profiler**: nó không đếm invocations, latency, exceptions hay CPU. Muốn đo method execution cần điểm instrumentation/monitoring khác.

## 15. Vì sao bài no-op có giá trị kỹ thuật?

### 15.1. Kiểm tra packaging trước khi sửa bytecode

Trước khi đưa ASM/Byte Buddy vào agent, việc ghi nhận target class đủ để xác minh:

- JVM đã đọc đúng `Premain-Class` trong agent JAR;
- `premain` thực thi thành công;
- transformer đã được đăng ký;
- code ứng dụng có load class mong đợi **sau registration**;
- tên internal đúng;
- loader/module path không khiến class đích bị nạp từ nguồn khác;
- agent không gây khác biệt behavior rõ ràng trong test.

Một transformer no-op là **smoke test của pipeline**, không phải bằng chứng transformer bytecode tương lai sẽ đúng.

### 15.2. Có thể đưa vào công cụ chẩn đoán class loading

Khi một thư viện plugin dùng nhiều class loaders, no-op transformer có thể ghi lại class target được nạp ở đâu và khi nào. Đó là một cách đơn giản để tìm lý do class agent muốn patch không được callback: sai binary name, class đã được load quá sớm hoặc target nằm trong loader không dự kiến.

Tuy nhiên, **log ngay trong callback** chỉ nên giới hạn khi thực nghiệm; production cần low-overhead event recording, bounded buffer hoặc hệ thống logging không tự gây classloading recursion.

### 15.3. Không có ASM/JDK internal dependency

Code demo dùng duy nhất:

~~~text
java.lang.instrument.Instrumentation
java.lang.instrument.ClassFileTransformer
java.security.ProtectionDomain
java.lang.String / System / ClassLoader
~~~

Nên JAR agent có thể nhỏ, không cần shaded bytecode library và không cần `--add-exports` truy cập package nội bộ JDK. Đây là lợi thế khi dựng bộ test/diagnostics ban đầu.

## 16. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra |
|---|---|---|
| JVM báo thiếu `Premain-Class` | Manifest của final JAR không đúng | Trích `META-INF/MANIFEST.MF` từ JAR phát hành |
| `ClassNotFoundException` cho agent entry | Tên `Premain-Class` sai hoặc thiếu class trong JAR | `jar --list --file ...` |
| Chỉ thấy `main:start`, không có `agent:premain` | Lệnh chạy thiếu `-javaagent` hoặc agent không được nạp | In command line thực tế |
| Có `agent:registered` nhưng không có target hit | Target đã load trước, sai filter, hoặc app không dùng target | Kiểm tra class-loading timing và `demo/Target` |
| Callback có log cho `Unrelated` | Filter bị viết sai hoặc log nằm ngoài điều kiện | Đặt early return trước câu lệnh log |
| Log in `demo.Target` nhưng filter viết `demo/Target` không khớp | Nhầm format tên | Dùng internal slash name |
| `NullPointerException` vì `className.equals(...)` | `className` có thể null | Đổi thành `"demo/Target".equals(className)` |
| Log lặp nhiều lần dù chỉ một source class | Nhiều defining loaders hoặc redefine/retransform | Ghi loader identity và lifecycle callback |
| Mỗi request có hàng nghìn log | Filter quá rộng hoặc quá nhiều class loading | Thu hẹp mục tiêu, dùng sampling/buffer |
| Probe in nhưng method Target lỗi | Lỗi app hoặc transformer khác; no-op không sửa bytes | So baseline, full stack trace, mọi agent |
| `VerifyError` sau khi chỉ đăng ký no-op transformer | Có thể transformer khác hoặc classfile nguồn lỗi | Xác định bytes cuối và danh sách agents |
| Chạy Java 17 báo `UnsupportedClassVersionError` | Agent/app được biên dịch bằng JDK mới mà không dùng `--release 17` | Dùng `javap -verbose` xem major, build lại |
| `-javaagent` làm JVM abort trước main | Manifest/entrypoint lỗi hoặc `premain` throw không bắt | Đọc stderr/exception gốc |
| `removeTransformer` rồi vẫn thấy một callback | Race với class loading đồng thời | Javadoc nói callback có thể đến sau removal |
| Không thấy `Target` dù callback hoạt động trên class khác | JVM có thể đã nạp Target trước hoặc class name/loader khác | Dùng logs kiểm soát và class loader introspection |
| Trả `originalBytes` trong mọi callback | No-op nhưng báo như thể có bytes mới | Dùng `return null` rõ nghĩa hơn |

### 16.1. Debug sai tên class

Để biết Java source của target:

~~~java
System.out.println(Target.class.getName());   // demo.Target
~~~

Đây là ví dụ **đặt trong code có quyền import hoặc truy cập `Target`**; không nên gọi `Target.class` ngay trong `premain` chỉ để tìm tên, vì việc tham chiếu có thể làm **load class đích trước khi transformer được đăng ký**.

Trong callback luôn so sánh với internal name mà JVM truyền, ví dụ `demo/Target`.

### 16.2. Debug classloader khi nhiều modules/plugins

Khi mở rộng code, có thể log classloader identity nhưng tránh gọi methods phức tạp trong callback. Ví dụ chỉ để nghiên cứu:

~~~java
if ("demo/Target".equals(className)) {
    String loaderKind = loader == null
            ? "bootstrap"
            : loader.getClass().getName();
    System.out.println("target-loader-kind=" + loaderKind);
}
return null;
~~~

Đây là **trích đoạn minh họa**, đặt trong `transform`. Nó nhận biết **loại loader**, chưa phân biệt hai instances cùng class loader type. Nếu thực sự cần identity, có thể dùng `System.identityHashCode(loader)` và log PID/context; nhưng số đó không ổn định giữa các lần chạy, tránh đưa vào stdout exact của lab.

### 16.3. Không nên scan toàn bộ getAllLoadedClasses trong transform

`Instrumentation.getAllLoadedClasses()` có thể hữu ích khi chẩn đoán, nhưng quét toàn bộ classes **bên trong mỗi callback** sẽ rất tốn chi phí và có thể gây concurrency/initialization issues. Nếu cần snapshot, thực hiện ở một điểm vận hành có kiểm soát bên ngoài hot path.

## 17. An toàn, hiệu năng và production hardening

### 17.1. Transformer được gọi trong class-loading path

Một JVM có thể định nghĩa hàng nghìn classes khi khởi động. Nếu mỗi callback đều tạo formatter phức tạp, truy vấn mạng hay log đồng bộ, bạn có thể làm chậm startup hoặc tạo classloading recursion. Bài này **lọc trước khi log**, và in rất ít dòng.

Khuyến nghị thực tế:

1. Trả `null` càng sớm càng tốt cho những class không khớp.
2. Tránh nạp những thư viện logging/JSON lớn bên trong callback.
3. Không cố tình block, sleep, lấy global lock nguy hiểm hoặc mở network ngay trong callback.
4. Tránh instrument chính classes của agent và helper nếu không có thiết kế rõ.
5. Nếu nhiều threads/class loaders cùng định nghĩa target name, đừng giả định callback chỉ chạy trên một thread.
6. Nếu ghi counter, dùng cấu trúc thread-safe như `AtomicLong` khi cần và phân biệt class-name hits với identity.
7. Không log dữ liệu nhạy cảm từ `classfileBuffer`; mã demo không cần đọc buffer.
8. Đo chi phí thực sự ở ứng dụng đích thay vì giả định no-op có overhead bằng zero.

### 17.2. Quan sát không làm thay đổi bytecode, nhưng logging vẫn là side effect

`return null` đảm bảo transformer này **không thay class bytes**, nhưng việc `System.out.println` vẫn gây **I/O side effect** và latency. Vì thế “no-op transformer” ở đây nghĩa là **no-op đối với bytecode**, không phải không có tác động hiệu năng hoặc logs.

Một ứng dụng throughput cao nên dùng cơ chế queue/buffer, sampling hoặc JFR phù hợp thay vì in từng hit vào stdout.

### 17.3. Không dùng throw để cấm load

Nếu một transformer throw exception khi thấy một class không được phép, Javadoc không bảo đảm class sẽ không được định nghĩa. Hợp đồng xử lý exception tương đương trả `null` cho callback đó. Nếu bài toán là bảo mật/enforcement, cần cơ chế chính sách đúng lớp, không dùng “transformer throw” làm policy gate.

### 17.4. Không giả định một agent là tất cả các biến đổi

Khi chạy nhiều `-javaagent`, Java Instrumentation có thứ tự gọi transformers. `return null` chỉ loại bỏ thay đổi từ transformer hiện tại; transformer khác vẫn có thể sửa bytes. Khi điều tra khác biệt behavior, ghi **toàn bộ agents** và transformer ordering, chứ không chỉ nhìn target-only agent.

### 17.5. Java 17 minimum và portability

Mẫu này dùng overload transformer năm tham số có sẵn trong Java 17 và tính năng classfile instrumentation của `java.instrument`. Lệnh `javac --release 17` tạo classfile major **61** cho các nguồn demo; JDK 17 tương thích có thể nạp. Nếu một JVM vendor/phiên bản có giới hạn Java agent riêng, hãy kiểm tra trong runtime matrix của dự án.

## 18. Bài tập mở rộng có hướng dẫn

### Bài tập A — sửa sai bộ lọc

Đổi điều kiện thành:

~~~java
if (!"demo.Target".equals(className)) {
    return null;
}
~~~

Chạy lại. Vì sao không còn `transform:seen=demo/Target`? **Đáp án:** JVM đưa tên nội bộ `demo/Target` với dấu slash, không phải binary name `demo.Target`. Khôi phục điều kiện đúng.

### Bài tập B — log class đối chứng

Đưa câu `System.out.println("transform:seen=" + className)` ra **ngoài điều kiện target**, rồi chạy lại. Quan sát số dòng log tăng mạnh vì JVM có thể load nhiều classes. Vì sao đây là sai yêu cầu “chỉ ghi nhận lớp đích”? Khôi phục early return.

### Bài tập C — return null hay return originalBytes?

Thay `return null` bằng `return originalBytes` trong một bản thử cô lập. Kết quả nghiệp vụ có thể vẫn giống nhau, nhưng vì sao vẫn nên dùng null cho no-op? **Đáp án:** đó là hợp đồng rõ ràng về “no transform”; không cần trả mảng, và đừng thao tác trên input buffer.

### Bài tập D — tạo nhiều đối tượng

Tăng lên 100 lần `new Target().greet("Java")` trong cùng process/class loader. Dự đoán số lần in `transform:seen=demo/Target`. **Trong lab này**, vẫn một lần nếu class đã được định nghĩa một lần và không có redefine/retransform; 100 objects không đồng nghĩa 100 class definitions.

### Bài tập E — khi target đã load trước

Thiết kế một test khác trong đó class `Target` đã được load **trước khi đăng ký transformer** (không cần viết đè demo đang chạy), rồi chỉ tạo object tiếp. Vì sao callback có thể không được gọi? Giải thích giới hạn của `addTransformer(..., false)` và cách tiếp cận retransform nếu thực sự cần.

### Bài tập F — lọc theo class loader

Hãy điều chỉnh transformer sáu tham số để chỉ log khi `className` bằng `demo/Target` **và** defining loader đúng một loader đã biết. Tại sao cần xác minh loader trong app có plugin isolation? Giải thích trường hợp hai classes cùng tên do hai loaders định nghĩa.

### Bài tập G — kiểm tra manifest thật

Cố tình đổi `Premain-Class` thành một tên class không có trong agent JAR, đóng gói lại ở thư mục test. Chạy `-javaagent`: JVM có vào `main:start` không? Khôi phục manifest và kiểm tra lại. **Không thử thay thế agent production** bằng artifact cố ý lỗi.

### Bài tập H — thread-safe hit counter

Thay log trực tiếp bằng `AtomicLong` đếm số lần callback thấy target, vẫn `return null`. Hãy giải thích số đếm đo **class transformation callbacks**, không phải số lần gọi `greet`. Đặt nơi công bố counter an toàn, tránh quét counters trong transformer khi JVM đang load.

### Bài tập I — mở rộng sang multi-target

Tạo một tập các internal names được phép quan sát:

~~~java
Set<String> allowedNames = Set.of(
        "demo/Target", "demo/Unrelated");
~~~

Đây là **trích đoạn minh họa** (cần import `java.util.Set` và đặt biến trong class). Thay điều kiện bằng `allowedNames.contains(className)`. Khi đó không còn tuân thủ đề bài một target duy nhất, nhưng giúp hiểu cách phát triển filter có kiểm soát. Mặc định vẫn chỉ ghi `demo/Target`.

### Câu hỏi kiểm tra

1. **`ClassFileTransformer.transform` trả `null` nghĩa là gì?** — Transformer đó không cung cấp classfile thay thế.
2. **`return null` có chặn nạp class không?** — Không.
3. **Tên callback cho `demo.Target` có dấu chấm hay slash?** — `demo/Target`.
4. **`classBeingRedefined` bằng gì khi class load lần đầu?** — `null`.
5. **`loader` có thể null không?** — Có, với bootstrap loader.
6. **Tại sao log target chỉ xuất hiện một lần dù có hai `new Target`?** — Một class definition cho cùng loader trong lab.
7. **`Premain-Class` trong manifest dùng tên nào?** — `demo.agent.TargetOnlyAgent`.
8. **`Can-Retransform-Classes` có cần cho lab không?** — Không.
9. **`-Xverify:all` có làm một no-op agent trở thành bytecode modifier không?** — Không.
10. **Log trong callback có nghĩa JVM đã define thành công chưa?** — Chưa đủ bằng chứng.
11. **Khi có nhiều transformers, một transformer `return null` có bảo đảm tất cả không sửa class không?** — Không.
12. **Gỡ transformer có tự undo bytecode đã cài bởi agent khác không?** — Không.

## 19. Checklist hoàn thành và tài liệu chuẩn

### Trước khi chạy

- [ ] Có đúng **một class đích** `demo.Target` để quan sát.
- [ ] Transformer so sánh `"demo/Target".equals(className)`.
- [ ] Non-target: **không log** và `return null`.
- [ ] Target: log rõ class name nhưng vẫn `return null`.
- [ ] Không mutate `classfileBuffer`, không trả replacement bytes.
- [ ] Agent dùng `premain` và `addTransformer(..., false)`.
- [ ] Có `Premain-Class: demo.agent.TargetOnlyAgent` ở manifest JAR cuối.
- [ ] Thư mục output agent và app tách riêng.
- [ ] Biên dịch bằng `--release 17` nếu runtime tối thiểu là Java 17.
- [ ] Đảm bảo `-javaagent` xuất hiện trong lệnh JVM chạy app.

### Khi kiểm thử

- [ ] Chạy baseline **không agent**, ghi stdout/exit code.
- [ ] Chạy **có agent** với `-Xverify:all`.
- [ ] Xác nhận thứ tự `agent:premain`, `agent:registered`, `main:start`.
- [ ] Xác nhận target hit nằm **sau `main:before-target`** và trước dòng gọi method trong lab.
- [ ] Xác nhận `transform:seen=demo/Target` xuất hiện đúng **một lần** trong lab cô lập.
- [ ] Xác nhận `demo.Unrelated` **không bị log**.
- [ ] Xác nhận hai giá trị `Hello, Java` và `Hello, World` giữ nguyên.
- [ ] Xác nhận `transform:redefine=false` ở lần load đầu.
- [ ] Kiểm tra agent JAR có cả nested transformer class và manifest entry đúng.
- [ ] Xác nhận JAR không kéo JDK internal ASM dependency không cần thiết.
- [ ] Không nhầm “target observed” với “bytecode rewritten/installed”.

### Khi chuyển sang production

- [ ] Giới hạn logging trong class loading path và không block/recursion.
- [ ] Bảo đảm filter chính xác theo class name, loader/module nếu cần.
- [ ] Thiết kế thread-safety khi nhiều class definitions diễn ra song song.
- [ ] Nếu muốn observe already-loaded classes, lên kế hoạch retransform riêng với capability.
- [ ] Không dùng transformer exception làm chính sách từ chối nạp class.
- [ ] Kiểm thử trên runtime/JDK/vendor/module topology thực tế.
- [ ] Nếu bật nhiều agents, ghi nhận toàn bộ transformer chain.
- [ ] Tách logging outcome của transformer với verification/definition và business behavior.
- [ ] Chỉ mở rộng sang bytecode rewriting sau khi baseline no-op đã được kiểm chứng.

**Kết luận:** một transformer dành cho bài thực nghiệm này chỉ cần **filter className đúng**, **ghi nhận đúng class đích**, và **trả `null` trong mọi nhánh**. Nó là cách kiểm chứng đường khởi tạo `premain` và đường class loading của `demo.Target` mà không thêm bytecode. Kết quả trước/sau cho thấy ứng dụng giữ nguyên hai giá trị nghiệp vụ; sự khác biệt duy nhất về stdout là những dòng chẩn đoán do agent chủ động in.

### Tài liệu chính thức

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): overloads 5/6 tham số, tên internal form, `return null` và input buffer không được mutate.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `isRetransformClassesSupported` và `retransformClasses`.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, manifest attributes.
- [JVMS Java SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): binary/internal names, classfile structure.
- [JVMS Java SE 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class definition, linking và resolution stages.
