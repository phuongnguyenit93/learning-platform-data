# Kiểm tra nhiều lần retransform, redefine và thay đổi thứ tự agent

Một Java agent có thể hoạt động ở lần nạp lớp đầu tiên nhưng bị lỗi khi `Instrumentation.retransformClasses(...)` được gọi lần thứ hai, khi lớp bị thay định nghĩa bằng `Instrumentation.redefineClasses(...)`, hoặc khi một agent khác xuất hiện trước nó trên dòng lệnh. Triệu chứng có thể là probe bị chèn lặp, thứ tự advice thay đổi, số lần gọi tăng bất thường, lỗi bytecode verifier, hoặc kết quả khác nhau giữa hai cấu hình `-javaagent`.

Trong **Java Advance – instrumentation**, phần **Kiểm thử và chẩn đoán**, yêu cầu đặt ra là kiểm tra **nhiều lần retransform, nhiều lần redefine và đảo thứ tự agent**. Đây không chỉ là bài toán “gọi API không ném exception”; phải xác minh hành vi ứng dụng sau mỗi lần thay đổi, callback nào thực sự chạy, thứ tự composition, sự ổn định của probe và khả năng khôi phục khi tác động có xung đột.

Bài học này trình bày quy tắc JVM, ma trận kiểm thử, một thí nghiệm **Java 17+ chạy được** dùng hai startup agent A/B, có kiểm tra kết quả cả trước/sau hai lần retransform, hai lần redefine và một lần retransform tiếp theo. Thí nghiệm thật sự biến đổi một chuỗi hằng trong class file (không cần thư viện ngoài), giúp quan sát sự khác biệt do **thứ tự agent** thay vì chỉ in log đăng ký.

## 1. Phân biệt load, retransform và redefine

Cả ba đều có thể đi qua `ClassFileTransformer`, nhưng xuất phát điểm và các callback không giống nhau:

| Hoạt động | Điểm bắt đầu | Transformer được gọi | Bài kiểm tra quan trọng |
| --- | --- | --- | --- |
| **Nạp lớp lần đầu** | Bytes do class loader cung cấp | Các transformer đã đăng ký, theo nhóm và thứ tự quy định | Class verifier chấp nhận, method chạy đúng, hook hoạt động |
| **`retransformClasses(C)`** | Bytecode gốc liên quan lần define hoặc lần redefine gần nhất, được JVM chuẩn bị lại | Transformer **canRetransform=true** được gọi; kết quả cũ của nhóm `false` được tái sử dụng tự động | Không chèn trùng; lặp nhiều lần vẫn đúng; không tưởng callback `false` chạy lại |
| **`redefineClasses(new ClassDefinition(C, bytes))`** | **Bytes mới do caller đưa vào**, thay thế định nghĩa của class | Cả nhóm capable và incapable đã đăng ký được gọi, theo thứ tự | New bytes hợp lệ, cùng schema được JVM hỗ trợ, hành vi mới đúng, state không bị reset |
| **`retransformClasses(C)` sau redefine** | Dựa trên **lần redefine gần nhất**, không nhất thiết là bản JAR ban đầu | Nhóm `false` tái sử dụng kết quả từ lần load/redefine gần nhất; nhóm `true` chạy lại | Bản mới không vô tình quay về baseline cũ; không nhân đôi probe |

Từ `Instrumentation.retransformClasses` trong Javadoc: khi retransform, JVM bắt đầu từ các initial class file bytes tương ứng; kết quả của transformer không có khả năng retransform được **replay mà không gọi lại `transform()`**; còn transformer capable được gọi lại. “Initial class file bytes” không nhất thiết giống byte-for-byte với file `.class` ban đầu: JVM có thể thay đổi bố trí constant pool/attributes mà không đổi ý nghĩa. Do đó **đừng so sánh hash toàn bộ `classfileBuffer` để suy ra JVM đã làm sai**.

### 1.1. `retransformClasses` là transform lại, không phải nối thêm bytes mới vào kết quả cũ

Một nhầm lẫn phổ biến:

```text
Sai:
  load -> chèn hook một lần
  retransform #1 -> lấy bytes đã có hook rồi chèn lần hai
  retransform #2 -> tiếp tục chèn lần ba

Cách hiểu đúng theo API:
  retransform -> JVM dựng chuỗi biến đổi lại từ baseline tương ứng
  -> replay kết quả của nhóm incapable
  -> gọi lại các transformer capable theo thứ tự
  -> kiểm tra và cài định nghĩa mới
```

Tuy vậy, **không được chỉ dựa vào đặc điểm baseline để bỏ kiểm tra idempotence**. Nếu transformer capable nhận classfile đã có marker do transformer khác hoặc do chính nguồn của lần `redefineClasses` đưa vào, việc chèn advice vô điều kiện có thể nhân đôi hook. Bytecode instrumentation trong production nên nhận diện method/hook/marker đã có, xác minh cấu trúc trước khi áp dụng, hoặc thiết kế phép biến đổi mang tính idempotent theo contract của nó.

### 1.2. `redefineClasses` không chỉ là alias của retransform

Với redefine, caller đưa ra `ClassDefinition(Class<?>, byte[])`. Mảng bytes này có thể được tạo từ bản build mới, nguồn class file đã được kiểm chứng hoặc một pipeline riêng. Nó **không tự lấy** baseline đang chạy và không ngầm “đổi cấu hình hook” giúp bạn.

Ví dụ:

```java
// Snippet minh họa, yêu cầu inst, targetClass và verifiedBytes đã có.
inst.redefineClasses(new ClassDefinition(targetClass, verifiedBytes));
```

Về nguyên tắc, `redefineClasses` thích hợp khi muốn cung cấp **định nghĩa class mới**. Nếu muốn áp lại pipeline transformer trên class đang chạy, `retransformClasses` là lựa chọn phù hợp hơn.

## 2. Quy tắc thứ tự transformer quan trọng hơn thứ tự đăng ký nhìn bề ngoài

Đặc tả `ClassFileTransformer` chia thành bốn nhóm và áp dụng theo thứ tự:

1. **Java transformer không có khả năng retransformation** (`canRetransform=false`).
2. **Native transformer không có khả năng retransformation** (JVMTI).
3. **Java transformer có khả năng retransformation** (`canRetransform=true`).
4. **Native transformer có khả năng retransformation** (JVMTI).

**Trong mỗi nhóm**, các transformer được gọi theo **thứ tự đăng ký**. Bytes trả về của transformer trước (nếu không phải `null`) trở thành đầu vào cho transformer tiếp theo. `return null` nghĩa là transformer ấy không thay đổi bytes ở lần gọi đó.

Vì vậy nếu `premain(A)` đăng ký `A.fixed` rồi `A.cap`, tiếp theo `premain(B)` đăng ký `B.fixed` rồi `B.cap`, trình tự callback Java cho lớp được nạp là:

```text
premain(A): register A.fixed, A.cap
premain(B): register B.fixed, B.cap

transform(Target) — class load:
A.fixed -> B.fixed -> A.cap -> B.cap
```

**Không phải** `A.fixed -> A.cap -> B.fixed -> B.cap`: JVM nhóm noncapable trước capable. Khi retransform, `fixed` **không được gọi lại** nhưng kết quả đã ghi nhận được tái áp dụng, nên chỉ nhìn log callback sẽ thấy:

```text
retransform(Target):
  [JVM reuses fixed transforms invisibly]
  A.cap -> B.cap
```

Khi redefine với `ClassDefinition`, cả bốn transformer Java được gọi theo nhóm. Nếu đảo hai tùy chọn `-javaagent`, thứ tự đăng ký trong mỗi nhóm cũng đảo:

```text
B.fixed -> A.fixed -> B.cap -> A.cap
```

Với các agent thực tế, native JVMTI hook có thể xen giữa theo **thứ tự nhóm** trong đặc tả. Ngoài ra, mỗi agent có thể đăng ký transformer sau `premain` hoặc qua attach runtime; đừng suy toàn bộ thứ tự biến đổi chỉ từ thứ tự tên JAR trên command line.

## 3. Điều kiện tiên quyết và giới hạn an toàn

Trước khi đưa target vào ma trận:

- Xác nhận JVM hỗ trợ `Instrumentation.isRetransformClassesSupported()` và `isRedefineClassesSupported()`. Hai khả năng **tùy chọn**, không mặc định bật ở mọi JVM.
- Với **startup agent**, đặt manifest `Can-Retransform-Classes: true` nếu cần đăng ký transformer capable, và `Can-Redefine-Classes: true` nếu cần redefine. Còn phụ thuộc JVM hỗ trợ thực sự.
- Kiểm tra `Instrumentation.isModifiableClass(target)`. Một số lớp như mảng, primitive hoặc cấu trúc đặc biệt không thể sửa; tránh giả định mọi class load được là modifiable.
- Quy định rõ `Class<?>` cụ thể: identity gồm **tên lớp + defining class loader**. Hai `demo.Target` do hai loader khác nhau định nghĩa là hai target khác nhau.
- Không đổi schema ngoài giới hạn JVM: thông thường redefine/retransform **không được thêm/xóa/đổi tên field hoặc method, đổi method signature, superclass hoặc interface**, và có những hạn chế liên quan thuộc tính class file. Sửa thân method/constant pool trong phạm vi hợp lệ thường khả thi.
- Với một yêu cầu sửa nhiều class, API hỗ trợ truyền một tập để các thay đổi liên quan được áp dụng theo khả năng JVM. Nếu yêu cầu thất bại, **không có class nào trong yêu cầu đó được thay đổi** theo contract; vẫn phải xử lý lỗi và báo rõ ràng.
- Một method đang có active stack frame tiếp tục chạy bytecode **cũ** cho frame đó; các lần gọi mới dùng method đã được sửa. Vì thế test phải dùng **lời gọi mới** sau mỗi operation, không chỉ nhìn một lời gọi đang chạy.
- Redefinition/retransformation không chạy lại `<clinit>` chỉ vì đã thay định nghĩa; giá trị static fields vẫn tồn tại. Instance đã tạo trước không tự được reset. Test nên giữ object cũ và kiểm tra lại để xác minh.
- Đừng đồng thời gọi redefine/retransform trên cùng nhóm target từ nhiều luồng mà không có điều phối; lẫn lộn event order làm test không tái lập.

## 4. Thí nghiệm có thể chạy bằng Java 17+: hai agent A và B cùng biến đổi một class

Ví dụ dùng **một JAR agent** hai lần với đối số `A` và `B`. Mỗi lần `premain` đăng ký:
- một transformer **fixed** (`canRetransform=false`) chỉ in log;
- một transformer **capable** (`canRetransform=true`) sửa một hằng chuỗi ASCII dài tám byte trong constant pool của `demo.Target`.

Có hai giá trị thay thế:
- Agent A muốn method trả `AAA00000`.
- Agent B muốn method trả `BBB00000`.

Transformer capable nào chạy **sau cùng** sẽ quyết định chuỗi quan sát được. Khi đảo `-javaagent:A` và `-javaagent:B`, đầu ra ứng dụng sẽ đảo theo. Cả hai transformer đều **nhận biết hằng đã được biến đổi** và ghi đè có chủ đích, nên lần retransform tiếp theo không tích lũy chuỗi “cũ + mới”.

**Phạm vi demo:** việc sửa `CONSTANT_Utf8` trực tiếp dưới đây chỉ an toàn cho literal ASCII có độ dài **bằng nhau** và target được kiểm soát. Đây **không phải** một thư viện sửa bytecode tổng quát. Trong production hãy dùng ASM/Byte Buddy hoặc thư viện classfile phù hợp, kiểm tra verifier/frames và giữ invariant của class file.

### 4.1. Cấu trúc tệp

```text
multi-agent-order/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── MultiAgent.java
│   └── demo/
│       ├── Target.java
│       └── Main.java
└── out/                      # tạo khi biên dịch
```

### 4.2. Target có hằng làm dấu

Tệp `src/demo/Target.java`:

```java
package demo;

public final class Target {
    public String value() {
        return "BASE0000";
    }
}
```

Marker `BASE0000`, `AAA00000`, `BBB00000` đều có **8 ký tự ASCII**. Ở đây Java compiler đặt string literal trong constant pool; transformer thay bytes của UTF-8 entry mà `CONSTANT_String` tham chiếu. Demo không sửa danh sách method/field, descriptor hoặc độ dài một `CONSTANT_Utf8` entry.

### 4.3. Agent và hai transformer

Tệp `src/agent/MultiAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class MultiAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String id, Instrumentation inst) {
        if (!"A".equals(id) && !"B".equals(id)) {
            throw new IllegalArgumentException(
                    "Use -javaagent:agent.jar=A or =B");
        }
        instrumentation = inst;
        inst.addTransformer(new MarkerTransformer(id, false), false);
        inst.addTransformer(new MarkerTransformer(id, true), true);
        System.out.println("premain:" + id);
    }

    public static Instrumentation instrumentation() {
        return instrumentation;
    }

    private static final class MarkerTransformer
            implements ClassFileTransformer {
        private final String id;
        private final boolean capable;

        MarkerTransformer(String id, boolean capable) {
            this.id = id;
            this.capable = capable;
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] bytes) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            System.out.println("transform:" + id + ":"
                    + (capable ? "cap" : "fixed") + ":"
                    + (classBeingRedefined == null
                            ? "load" : "change"));

            if (!capable) {
                return null;
            }
            return patchLiteral(bytes,
                    "A".equals(id) ? "AAA00000" : "BBB00000");
        }

        private static byte[] patchLiteral(
                byte[] input, String replacement) {
            byte[] result = input.clone();
            int cpCount = u2(result, 8);
            int p = 10;
            boolean patched = false;

            for (int i = 1; i < cpCount; i++) {
                int tag = result[p++] & 0xFF;
                switch (tag) {
                    case 1 -> {
                        int len = u2(result, p);
                        p += 2;

                        if (len == 8) {
                            String value = new String(
                                    result, p, len,
                                    StandardCharsets.US_ASCII);
                            if (value.equals("BASE0000")
                                    || value.equals("AAA00000")
                                    || value.equals("BBB00000")) {
                                byte[] data = replacement.getBytes(
                                        StandardCharsets.US_ASCII);
                                System.arraycopy(data, 0, result,
                                        p, data.length);
                                patched = true;
                            }
                        }
                        p += len;
                    }
                    case 3, 4 -> p += 4;
                    case 5, 6 -> {
                        p += 8;
                        i++;
                    }
                    case 7, 8, 16, 19, 20 -> p += 2;
                    case 9, 10, 11, 12, 17, 18 -> p += 4;
                    case 15 -> p += 3;
                    default -> throw new IllegalArgumentException(
                            "cp tag=" + tag);
                }
            }
            return patched ? result : null;
        }

        private static int u2(byte[] b, int p) {
            return ((b[p] & 0xFF) << 8)
                    | (b[p + 1] & 0xFF);
        }
    }
}
```

Đặc điểm cần chú ý:

1. `premain` được gọi hai lần **vì cùng JAR được chỉ định hai lần**, với agent arguments `A` và `B`. Đây là kỹ thuật **thử nghiệm để quan sát thứ tự**, không khuyến nghị nạp trùng cùng agent trong production.
2. Mỗi lần đăng ký hai **instance transformer khác nhau**; không đăng ký lại cùng một đối tượng transformer.
3. Callback chỉ thực sự xử lý `className="demo/Target"`, tránh đụng vào các class của JDK và chính agent.
4. Transformer `fixed` trả `null`; nó được dùng để chứng minh **callback không chạy trên retransform**, không phải “đóng băng toàn bộ class”.
5. Transformer `capable` đọc bytes do transformer trước chuyển tới và tạo bản sao mới; không sửa trực tiếp `classfileBuffer` của JVM.
6. `patchLiteral` duyệt bảng constant pool, bỏ qua các tag có chiều dài cố định và đổi một UTF8 entry có độ dài đúng 8. Đối với chữ ASCII này, byte length và char length trùng nhau; trong trường hợp Unicode/modified UTF-8 thực, không thể áp dụng quy tắc thay bytes giản đơn như vậy.
7. Vì transformer nhận cả giá trị gốc và hai giá trị đã biến đổi, **transformer sau có thể ghi đè kết quả của transformer trước**; việc đảo agent mang ý nghĩa kiểm chứng được trên kết quả chạy method.
8. `classBeingRedefined != null` trong callback chỉ cho biết đang xử lý class **đã có định nghĩa**; trong demo ta in nhãn `change` cho cả redefine và retransform. **Không dùng điều kiện này để phân biệt chính xác hai API**.

Nếu ứng dụng thực tế có nhiều class loader chứa cùng `demo.Target`, chỉ lọc bằng tên là chưa đủ. Cần kết hợp loader identity, module, cấu hình và tránh instrument class helper của chính agent.

### 4.4. Chương trình điều khiển

Tệp `src/demo/Main.java`:

```java
package demo;

import agent.MultiAgent;
import java.io.InputStream;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = MultiAgent.instrumentation();
        System.out.println("support:retransform="
                + inst.isRetransformClassesSupported()
                + ",redefine="
                + inst.isRedefineClassesSupported());

        Class<?> target = Class.forName("demo.Target");
        System.out.println("modifiable="
                + inst.isModifiableClass(target));
        Object instance = target.getConstructor().newInstance();
        Method value = target.getMethod("value");
        System.out.println("initial=" + value.invoke(instance));

        for (int i = 1; i <= 2; i++) {
            System.out.println("retransform:" + i);
            inst.retransformClasses(target);
            System.out.println("after-retransform:" + i
                    + "=" + value.invoke(instance));
        }

        byte[] baseline;
        try (InputStream stream = target.getResourceAsStream(
                "/demo/Target.class")) {
            if (stream == null) {
                throw new IllegalStateException(
                        "Missing class resource");
            }
            baseline = stream.readAllBytes();
        }

        for (int i = 1; i <= 2; i++) {
            System.out.println("redefine:" + i);
            inst.redefineClasses(new ClassDefinition(
                    target, baseline));
            System.out.println("after-redefine:" + i
                    + "=" + value.invoke(instance));
        }

        System.out.println("retransform:post-redefine");
        inst.retransformClasses(target);
        System.out.println("after-post-redefine="
                + value.invoke(instance));
    }
}
```

Giải thích:
- `Class.forName("demo.Target")` làm `Target` được load **sau** khi cả hai agent đã hoàn tất `premain`. `Main` không tham chiếu `Target.class` trước điểm này, nên log dễ quan sát hơn.
- Kiểm tra cả hai capability và `isModifiableClass` trước khi thay class trong hệ thống thật. Demo in giá trị, và các lần thử đã xác minh môi trường hỗ trợ; nếu JVM trả `false`, phải bỏ qua/đánh dấu không hỗ trợ thay vì chạy mù.
- `instance` và `Method value` được **giữ nguyên** qua mọi lần thay đổi; các lời gọi `value.invoke(instance)` sau mỗi operation giúp kiểm tra chính object hiện hữu nhận behavior mới.
- `getResourceAsStream("/demo/Target.class")` đọc bytes `.class` **trong đường classpath của ví dụ** làm dữ liệu để `ClassDefinition`. Nó không đọc định nghĩa đang cài trong bộ nhớ JVM. Trong production, resource JAR có thể không khớp bytecode vốn được `defineClass` dùng; phải lấy bytes từ một nguồn tin cậy, kiểm tra phiên bản và class loader.
- Hai lần `redefineClasses` cố ý dùng **cùng baseline**, cho phép quan sát độ ổn định dưới cùng một định nghĩa đầu vào. Sau đó còn một lần retransform để kiểm tra đường chuyển tiếp giữa hai API.

### 4.5. Manifest và build

Tệp `agent.mf` (**phải có dòng trống kết thúc**):

```text
Manifest-Version: 1.0
Premain-Class: agent.MultiAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

```

Từ thư mục `multi-agent-order`, tạo thư mục output trên Linux/macOS:

```bash
mkdir -p out
```

Hoặc Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 -d out src/agent/MultiAgent.java src/demo/Main.java src/demo/Target.java
jar --create --file agent.jar --manifest agent.mf -C out agent
```

Lệnh `jar -C out agent` chỉ đóng package `agent` vào agent JAR; ứng dụng `demo.Main` và `demo.Target` chạy từ `out`. Dùng JDK/JVM có hỗ trợ cả redefine và retransform như OpenJDK 21 của thí nghiệm. Tập tin agent cần được tìm thấy từ working directory, hoặc dùng đường dẫn tuyệt đối.

**Chạy cấu hình A rồi B:**

```bash
java -javaagent:agent.jar=A -javaagent:agent.jar=B -cp out demo.Main
```

**Đảo thứ tự B rồi A:**

```bash
java -javaagent:agent.jar=B -javaagent:agent.jar=A -cp out demo.Main
```

Cần tạo **hai tiến trình JVM mới** để so sánh thứ tự khởi động. Đổi thứ tự trong một JVM đã chạy không tự sắp xếp lại các transformer đã đăng ký.

## 5. Kết quả thật: A → B, hai lần retransform, hai lần redefine

Đây là stdout quan sát được khi dùng `javac --release 17` trên OpenJDK **21.0.12.1** cho cấu hình A trước B:

```text
premain:A
premain:B
support:retransform=true,redefine=true
transform:A:fixed:load
transform:B:fixed:load
transform:A:cap:load
transform:B:cap:load
modifiable=true
initial=BBB00000
retransform:1
transform:A:cap:change
transform:B:cap:change
after-retransform:1=BBB00000
retransform:2
transform:A:cap:change
transform:B:cap:change
after-retransform:2=BBB00000
redefine:1
transform:A:fixed:change
transform:B:fixed:change
transform:A:cap:change
transform:B:cap:change
after-redefine:1=BBB00000
redefine:2
transform:A:fixed:change
transform:B:fixed:change
transform:A:cap:change
transform:B:cap:change
after-redefine:2=BBB00000
retransform:post-redefine
transform:A:cap:change
transform:B:cap:change
after-post-redefine=BBB00000
```

Có ba quan sát cốt lõi:

1. `premain:A` rồi `premain:B`, nhưng trình tự **load callbacks** được gom `A.fixed → B.fixed → A.cap → B.cap`.
2. Trong **hai lần retransform**, không có dòng `fixed:change`; nhóm capable `A.cap`, `B.cap` được gọi lại. Giá trị kết quả không bị tích lũy thành chuỗi kỳ lạ sau mỗi lần.
3. Trong **hai lần redefine**, cả fixed và capable đều được gọi lại. Sau mỗi redefine và sau lần retransform tiếp theo, kết quả vẫn `BBB00000` vì B là transformer capable cuối cùng.

Ở lần chạy này, mỗi transformer `fixed` có đúng **3 callback** cho `Target` (1 load + 2 redefine); mỗi transformer `cap` có đúng **6 callback** (1 load + 2 retransform + 2 redefine + 1 retransform sau redefine). Đó là **số callback trong kịch bản này**, không phải hằng số JVM cho mọi ứng dụng; nếu class được load/redf ở nơi khác, số lần khác.

## 6. Kết quả thật khi đảo B → A

Cùng lớp, cùng source, chỉ đổi thứ tự hai tùy chọn `-javaagent`. Stdout trên OpenJDK 21.0.12.1:

```text
premain:B
premain:A
support:retransform=true,redefine=true
transform:B:fixed:load
transform:A:fixed:load
transform:B:cap:load
transform:A:cap:load
modifiable=true
initial=AAA00000
retransform:1
transform:B:cap:change
transform:A:cap:change
after-retransform:1=AAA00000
retransform:2
transform:B:cap:change
transform:A:cap:change
after-retransform:2=AAA00000
redefine:1
transform:B:fixed:change
transform:A:fixed:change
transform:B:cap:change
transform:A:cap:change
after-redefine:1=AAA00000
redefine:2
transform:B:fixed:change
transform:A:fixed:change
transform:B:cap:change
transform:A:cap:change
after-redefine:2=AAA00000
retransform:post-redefine
transform:B:cap:change
transform:A:cap:change
after-post-redefine=AAA00000
```

Ở đây `A.cap` là transformer cuối nên class trả `AAA00000`. **Đảo thứ tự agent là một phần của ma trận test** vì hai transformer có thể sửa cùng call site, advice stack hoặc constant pool, dẫn tới hành vi khác dù mỗi agent chạy độc lập đều đúng.

**Giới hạn của demo:** hai agent sửa một constant string theo chính sách “last writer wins”. Trong instrumentation thật, kết quả composition có thể là cả hai probe được chèn, hai advice bao ngoài nhau, hoặc xung đột bytecode; không phải lúc nào cũng có ý nghĩa “agent cuối thắng”. Mục đích của thí nghiệm là chứng minh thứ tự **có thể quan sát và có thể thay đổi kết quả**, không khẳng định mọi transformer đều ghi đè nhau.

## 7. Ma trận kiểm thử nhiều lần: không chỉ kiểm tra kết quả cuối

Đối với mỗi cặp agent A/B hoặc mỗi version/cấu hình mới, tối thiểu nên có bảng sau:

| Test case | Hành động | Điều phải xác minh |
| --- | --- | --- |
| **Baseline không agent** | Chạy ứng dụng không có `-javaagent` | Hành vi gốc và lớp baseline xác định rõ |
| **Chỉ A** | Một startup agent | Kết quả/hook đúng theo A; classload thành công |
| **Chỉ B** | Một startup agent | Kết quả/hook đúng theo B; classload thành công |
| **A → B** | Hai agent theo thứ tự này | `premain`, callback order, method behavior và probe count |
| **B → A** | Đảo startup order trên JVM mới | So sánh sự khác biệt có chủ đích và lỗi xung đột |
| **Retransform #1** | `retransformClasses(target)` | Capable callback được gọi; incapable reused; không duplicated advice |
| **Retransform #2…N** | Lặp lại cùng phép biến đổi | Probe logic/bộ đếm trên *mỗi call mới* không tăng ngoài dự kiến; callback không nhân đôi do đăng ký lặp |
| **Redefine #1** | Cung cấp `ClassDefinition` hợp lệ | Both groups được gọi; class vẫn hợp lệ; method mới hoạt động |
| **Redefine #2…N** | Cùng bytes hoặc version khác đã kiểm chứng | Không tích lũy wrappers/probes; state/instances không bị reset trái kỳ vọng |
| **Retransform sau redefine** | Gọi API ngay sau chuỗi redefine | Baseline mới được dùng; không quay lại behavior/JAR cũ ngoài ý muốn |
| **Tắt/mở probe** | Thay cấu hình, retransform theo thiết kế | Probe disabled thật, không còn extra advice nếu đã gỡ; không chỉ giảm counter |
| **Class loader khác nhau** | Cùng binary name ở hai loader | Không sửa nhầm instance class loader hoặc thiếu helper |
| **Lỗi schema/bytes** | Thử class file không hợp lệ trong môi trường cô lập | JVM từ chối thay đổi, thông báo rõ; không cài nửa một batch |
| **Tải đồng thời** | Threads gọi method trong lúc có cuộc thay định nghĩa | Không deadlock/crash; phân biệt active frames cũ và invokes mới |
| **Agent gỡ đăng ký** | `removeTransformer` | Callback tương lai ngừng; hiểu rằng bytes cũ không tự gỡ ngay |

Nếu có mục tiêu đo hiệu năng, bổ sung latency/cpu/memory/class-load time trên cùng môi trường. Một phép transform “chạy được một lần” không đại diện cho chi phí khi lặp lại nhiều lần dưới tải.

### 7.1. Điều cần assert trong CI

Nên kiểm tra bằng test có điều kiện và đầu ra có cấu trúc, thay vì chỉ `grep` một dòng:

- **Capabilities**: `retransform` và `redefine` được báo `true`, `isModifiableClass(target)` đúng.
- **Callback sequence**: so **các dòng liên quan target**, không suy từ những lớp khác mà JVM đang load.
- **Callback count**: với ví dụ, mỗi `fixed` phải chạy ở load và cả hai redefine, **không chạy** ở ba retransform; mỗi `cap` chạy ở tất cả năm operation sau load.
- **Semantic output**: `value.invoke(instance)` trả kết quả dự kiến sau từng operation, không chỉ sau operation cuối.
- **No duplication**: số hook mỗi lần gọi method đúng kỳ vọng khi retransform lần 1/2/N; phát hiện advice wrapper bị lặp.
- **No stale baseline**: sau redefine, retransform không quay về bản trước redefine.
- **Error path**: khi `isModifiableClass=false` hoặc JVM không hỗ trợ capability, test báo **SKIP/UNSUPPORTED có chủ đích**, không báo pass.
- **Reproducibility**: chỉ thay một yếu tố khi so sánh: thứ tự agent; cố định JVM version, flags, JAR hashes, class loader và testcase.

Nhớ rằng log `transform:...:change` trong demo **không phân biệt API**; đây là lý do test harness đặt nhãn `retransform:1` và `redefine:1` **bên ngoài callback**. Trong hệ thống thực, thiết kế correlation ID theo operation nếu phải debug nhiều thread hoặc nhiều yêu cầu đồng thời.

## 8. Những phép kiểm thử phá vỡ kỳ vọng phổ biến

### 8.1. Một transformer đăng ký sai khả năng

Nếu đăng ký bằng:

```java
// Snippet trong premain; transformer đã được khởi tạo.
inst.addTransformer(transformer); // tương đương canRetransform=false
```

thì transformer vẫn có thể chạy trên class load và redefine, nhưng **không được gọi lại** trong `retransformClasses`. Việc đổi biến cấu hình trong transformer rồi trông chờ retransform sẽ cập nhật probe là sai nếu transformer thuộc nhóm incapable. Để callback chạy lại, cần manifest/capability phù hợp và đăng ký với `inst.addTransformer(transformer, true)`.

Nếu JVM không hỗ trợ retransformation, việc đăng ký capable/operation có thể báo `UnsupportedOperationException`. Bắt buộc kiểm tra `isRetransformClassesSupported()`, manifest và Java VM thực tế, không giả định rằng lỗi chỉ do JAR bị thiếu.

### 8.2. Dùng `return null` sai ngữ nghĩa

`return null` nghĩa là **transformer này không đổi classfile bytes được truyền ở lượt đó**. Nó không có nghĩa `JVM sẽ tự gỡ probe đã cài từ những lượt trước` trong mọi hoàn cảnh. Trên retransform, JVM đang dựng lại pipeline với kết quả các transformer incapable được replay; một transformer capable nay trả `null` có thể thôi thêm phần biến đổi của nó, **nhưng biến đổi của transformer khác hoặc bytes do redefine cung cấp vẫn tồn tại**.

Cần kiểm tra **method behavior** và bytecode thực tế sau khi tắt hook, không chỉ dựa vào kết quả return của một callback.

### 8.3. Chèn probe lần hai vì input đã có hook

Nếu một agent nhận bytes đã có `INVOKESTATIC agent/ProbeHooks.hit()` và vẫn chèn tiếp mỗi lần callback, số probe có thể nhân đôi. Cách xử lý:
- quét method/call sites hoặc marker attribute do agent kiểm soát;
- có rule chính xác để nhận diện đã instrument, không nhầm instruction nghiệp vụ;
- chèn một lần theo identity target + version transform, không theo số lần callback;
- thử `load → retransform × N → redefine → retransform × N` bằng kiểm tra behavior và số hook;
- giữ logic tương thích với các transformer **đứng trước và đứng sau**.

**Không chỉ giữ `Set<Class<?>>` rồi skip mọi lần tiếp theo:** khi target thật sự bị redefine với bytes gốc, cần có khả năng áp lại hook. Bộ nhớ trạng thái đơn giản “đã từng thấy class” có thể khiến probe biến mất sau một redefine. Idempotence nên gắn với **nội dung bytecode đang xử lý và chính sách instrument hiện tại**.

### 8.4. Redefine bằng bytes từ sai nguồn

Nếu caller đọc một `Target.class` không tương ứng với class được defining loader nạp (khác phiên bản, khác package, khác schema), JVM có thể từ chối hoặc tạo behavior không như mong muốn. Đoạn demo đọc tài nguyên từ một đường classpath tự kiểm soát chỉ để đảm bảo baseline rõ ràng.

Với custom loader/shaded JAR/multi-release JAR, nên lưu class identity, hash của **dữ liệu nguồn tin cậy**, build ID và config của phép redefine. Không dựa vào `getResourceAsStream` như một công thức lấy bytes đang cài trên JVM.

### 8.5. Thay đổi field hoặc method schema trong lúc live

Một class file đã build với field mới hoặc signature khác có thể chạy tốt ở startup nhưng **không thể** redefine trên JVM hiện tại. Những giới hạn của `redefineClasses` và `retransformClasses` không bằng quyền load class hoàn toàn mới. Phải test negative case `UnsupportedOperationException` hoặc các `LinkageError` phù hợp, và xác nhận batch không cài một phần.

### 8.6. Nhìn log callback rồi tưởng class đã đổi

Callback có thể in “transform ok” rồi trả `null`; sau đó một transformer khác có thể thay đổi kết quả, hoặc JVM có thể từ chối bytes. Vì vậy cần ít nhất ba mức quan sát:
1. **Pipeline**: các callback nào đã chạy, theo thứ tự nào.
2. **Install**: API retransform/redefine hoàn thành hay ném lỗi.
3. **Runtime**: lời gọi method mới và dữ liệu hook có đúng không.

Thí nghiệm mục 5–6 kiểm tra cả ba: log callback, API không ném lỗi, và giá trị `value()` sau từng bước.

## 9. Class và state sau retransform/redefine

Một số thuộc tính dễ hiểu nhầm khi chạy lặp:

- **Class identity**: target vẫn là cùng lớp logic trong cùng defining loader; API không tạo một `Class<?>` song song để thay thế tham chiếu hiện tại.
- **Instance cũ**: object đã được tạo trước redefinition tiếp tục tồn tại. Khi gọi method *mới*, JVM áp dụng definition mới của method theo quy tắc hỗ trợ.
- **Static state**: việc redefine/retransform tự nó không chạy lại `<clinit>`; các field static hiện hữu giữ giá trị của chúng, trừ khi chương trình tự sửa.
- **Active frames**: method đang chạy trên stack tiếp tục dùng code cũ cho frame đó; lần gọi mới dùng code mới. Nếu test under load, log có thể xen cả output trước và sau một lần thay đổi.
- **Class loader**: JVM không chuyển class sang loader khác khi retransform/redefine; helper được chèn vẫn phải loadable và truy cập hợp lệ từ target.
- **Constant pool**: representation có thể khác byte-for-byte qua những lần JVM dựng lại class file. So sánh **ngữ nghĩa** hoặc fingerprint ổn định được thiết kế riêng, không suy đoán “JVM phải trả lại cùng exact bytes”.
- **Kết quả pipeline**: khi transformer incapable đã từng sửa bytes, JVM có thể replay phần đó mà không gọi callback. Không thấy log `fixed` trong retransform **không có nghĩa phần biến đổi của nó đã biến mất**.

## 10. Kiểm thử với nhiều agent thật

Ngoài thí nghiệm một JAR chạy hai lần, production thường có ít nhất một tổ hợp:
- APM/observability agent, profiling agent và coverage agent.
- Java agent tự viết cùng Byte Buddy/ASM.
- Startup agent cùng dynamic attach agent.
- Native JVMTI agent và Java `ClassFileTransformer`.

Các transformer có thể cùng viết vào một method, thay class signature hoặc thêm helper call. Hãy định nghĩa **contract composition**: probe A trước B hay B trước A? Nếu một transformer trả bytes đã có probe, transformer tiếp theo có chấp nhận cấu trúc ấy không? Nếu A tạm tắt, B có vẫn hoạt động đúng không?

### 10.1. Không dựa vào thứ tự mong manh nếu có thể tránh

Thiết kế tốt ưu tiên:
- allowlist và phạm vi method riêng cho mỗi agent;
- marker hoặc phát hiện advice đã tồn tại;
- bytecode verifier và checksum/signature có ngữ nghĩa;
- phân biệt loại transformer capable/incapable;
- test startup order A→B và B→A trên JVM mới;
- chạy canary với đúng tổ hợp JAR thực tế và flags;
- ghi nguồn/version/class loader trong chẩn đoán.

Nếu hai agent bắt buộc có thứ tự, tài liệu triển khai phải xác định và test chính xác **thứ tự thực của transformer** và các nhóm JVM, không chỉ liệt kê hai JAR trong Dockerfile.

### 10.2. `removeTransformer` và khả năng rollback

`Instrumentation.removeTransformer(transformer)` ngừng transformer được gọi ở những sự kiện tương lai (có thể có callback đang chạy đồng thời khi gỡ). **Nó không tự hoàn nguyên mọi bytecode đã biến đổi trong những class đã nạp.** Nếu muốn gỡ probe, cần thiết kế retransform/redefine phù hợp, xét tác động của các transformer khác và baseline đang được JVM sử dụng.

Đừng thử “đảo ngược thứ tự agent” trong JVM sống rồi hy vọng undo: thứ tự nhóm/đăng ký được xác lập bởi những hành động đăng ký đã xảy ra. Khi cần so sánh A→B/B→A, chạy hai process độc lập với bộ test và JDK tương đương.

## 11. Chẩn đoán khi kết quả không khớp

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| `retransformClasses` báo unsupported | Manifest `Can-Retransform-Classes`, khả năng JVM, cách gọi `addTransformer(..., true)` |
| `redefineClasses` báo unsupported | Manifest `Can-Redefine-Classes`, khả năng JVM, schema change |
| `UnmodifiableClassException` | `isModifiableClass(target)`, loại class, JDK/runtime |
| `VerifyError` / `ClassFormatError` | Classfile bytes, stack-map frames, constant pool, tính hợp lệ của advice |
| `NoSuchMethodError` / `NoClassDefFoundError` | Helper, dependency, descriptor, loader/module visibility |
| Retransform nhiều lần làm probe nhân đôi | Transformer không idempotent, nguồn bytes đã có hook, thay đổi từ agent khác |
| Retransform không gọi transformer mong đợi | Transformer đăng ký incapable, className/loader filter sai, capability chưa bật |
| Redefine làm mất probe | Nguồn `ClassDefinition` không chứa hook, transformer hiện không thêm lại, quy tắc return null/replay |
| Thay thứ tự agent thì logic khác | Bytecode composition order, transformer group, advice conflicts |
| Class còn kết quả cũ ngay sau redefine | Active stack frames, code path bị cache, call-site hoặc quan sát sai đối tượng |
| Callback `transform` báo thành công nhưng API ném lỗi | JVM kiểm tra/verify bytes sau callback, có lỗi schema/linkage |
| `premain` chạy hai lần | Agent JAR bị chỉ định trùng trong CLI, env hoặc wrapper |

**Cách debug:** luôn ghi đối tượng `Class<?> target`, `target.getClassLoader()`, `target.getModule()`, agent JAR/version, capability flags, biến cấu hình và từng operation. Nếu callback cần log, dùng đường ghi nhẹ, không nạp thêm dependency phức tạp trong giai đoạn class loading.

## 12. Quy trình kiểm thử đề xuất trước khi phát hành

1. **Chốt baseline:** JDK/vendor/version, JVM flags, classpath/module path, hash của class file gốc, các agent JAR/version.
2. **Chạy class load không agent** để biết behavior gốc.
3. **Chạy từng agent độc lập** để xác định agent nào tự thay đổi những gì.
4. **Chạy A→B và B→A** ở hai JVM mới, lưu thứ tự callback và kết quả nghiệp vụ.
5. **Thực hiện `retransformClasses` ít nhất hai lần**, kiểm tra cả callback có/không chạy và behavior/hook count sau từng lần.
6. **Thực hiện `redefineClasses` ít nhất hai lần**, với bytes hợp lệ và phiên bản xác định; không chỉ thử một lần.
7. **Retransform sau redefine**, kiểm tra các transformer incapable được replay và capable chạy trên baseline tương ứng.
8. **Kiểm thử thất bại có kiểm soát:** capability false, unmodifiable target, schema sai, helper không nạp được; bảo đảm thông báo lỗi và không viết dở batch.
9. **Test concurrency và phương án rollback** trên workload gần production; tách active stack frames khỏi lời gọi mới.
10. **So sánh đúng phạm vi:** số hook, class identity/state, listener registrations, CPU/memory, startup overhead và khả năng lặp lại.

Một bài test đạt chỉ khi cả API, bytecode đã được áp dụng, **hành vi sau từng operation** và ma trận thứ tự agent đều đúng kỳ vọng. Không dùng riêng “`premain` chạy được” hoặc “`retransformClasses` không ném exception” làm tiêu chí đủ.

## 13. Câu hỏi tự kiểm tra

1. Khi retransform, vì sao transformer đăng ký `canRetransform=false` không in callback mới nhưng phần biến đổi trước đó vẫn có thể ảnh hưởng class?
2. Vì sao `ClassFileTransformer` dùng thứ tự nhóm fixed/capable chứ không đơn thuần chạy tuần tự theo toàn bộ lệnh `addTransformer`?
3. Tại sao kết quả `BBB00000` trong A→B lại trở thành `AAA00000` khi đảo B→A?
4. Nếu `redefineClasses` nhận bytes không có probe, khi nào probe có thể được áp lại? Khi nào nó có thể biến mất?
5. Vì sao phép so sánh hai mảng `classfileBuffer` bằng hash thô không đủ để khẳng định JVM đã nhân đôi bytecode?
6. Tại sao `removeTransformer` không được coi là phép rollback mọi class đang chạy?
7. Vì sao cần kiểm tra `isModifiableClass` bên cạnh hai capability `isRetransformClassesSupported`/`isRedefineClassesSupported`?
8. Nếu có active stack frame đang chạy code cũ trong khi một call mới dùng code mới, test nên ghi nhận sự khác biệt ấy thế nào?
9. Khi nhiều class loader cùng định nghĩa `demo.Target`, cần xác định target nào trước khi retransform/redefine?
10. Hãy thiết kế assertion cho chuỗi `load → retransform ×2 → redefine ×2 → retransform` để phát hiện callback bị lặp, thiếu hoặc sai thứ tự.

## 14. Tài liệu chính thức

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): bốn nhóm transformer, composition order, callback trên load/redefine/retransform và quy tắc `return null`.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, capability, `retransformClasses`, `redefineClasses`, active stack frames và trạng thái static.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cách cung cấp `Class<?>` và bytes cho redefinition.
- [Java SE 21 — gói `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent `premain`, thuộc tính manifest và cách gọi `-javaagent`.
- [JVM Specification SE 21 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): constant pool và các giới hạn cấu trúc class file được minh họa trong thí nghiệm.
