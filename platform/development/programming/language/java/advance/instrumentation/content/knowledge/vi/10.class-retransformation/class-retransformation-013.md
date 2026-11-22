# Thiết kế bật, tắt điểm đo bằng cấu hình và retransformation có kiểm soát

Trong ứng dụng Java đang chạy, ta có thể muốn bật điểm đo (probe) để quan sát một phương thức khi có sự cố, rồi tắt điểm đo để giảm chi phí vận hành mà không khởi động lại JVM. Với Java Instrumentation, cấu hình xác định trạng thái mong muốn; `ClassFileTransformer` quyết định bytecode cần tạo; `Instrumentation.retransformClasses(...)` áp dụng thay đổi cho lớp đã được nạp. Ba phần này cần được phối hợp có kiểm soát.

## 1. Mục tiêu và thuật ngữ

Sau bài này, bạn có thể:
- Phân biệt **đổi cấu hình** với **đổi bytecode đang có hiệu lực**.
- Chọn giữa bật/tắt logic ngay trong hook và bật/tắt bằng retransformation.
- Thiết kế quy trình chọn đúng lớp, kiểm tra khả năng sửa đổi, giới hạn phạm vi và xác minh kết quả.
- Chạy một Java agent mẫu có thể bật/tắt probe bằng tệp cấu hình khi ứng dụng vẫn đang chạy.
- Xử lý các rủi ro về tải hệ thống, tác động giữa nhiều transformer, lỗi xác minh bytecode và lời gọi đang thực thi.

**Điểm đo (probe)** là đoạn mã bổ sung để ghi nhận sự kiện, thời gian, số lần gọi hoặc thông tin chẩn đoán tại một điểm cụ thể. **Retransformation** là cơ chế yêu cầu JVM chạy lại chuỗi transformer trên lớp đã được nạp rồi cài đặt phiên bản bytecode hợp lệ mới của lớp đó. Nó khác với việc tạo một instance mới hoặc biên dịch lại mã nguồn trên đĩa.

Ví dụ: cần đo số lần gọi `OrderService.work()` chỉ trong khoảng thời gian điều tra. Yêu cầu là bật bằng `probe.enabled=true`, xác minh sự kiện xuất hiện, rồi đặt `false` và xác minh những lần gọi mới không tạo sự kiện nữa.

## 2. Hai kiểu bật/tắt điểm đo

| Kiểu | Khi bật/tắt | Ưu điểm | Chi phí và giới hạn |
| --- | --- | --- | --- |
| **Soft toggle**: bytecode luôn gọi `ProbeHooks.maybeRecord()`; bên trong hook kiểm tra cờ `volatile`/cấu hình | Đổi cờ, không cần retransformation cho mỗi lần chuyển | Thay đổi nhanh, phù hợp bật/tắt thường xuyên | Đường gọi vẫn chịu chi phí gọi hook và nhánh điều kiện; phải tối ưu logic khi tắt |
| **Hard toggle**: khi bật, transformer chèn lời gọi hook; khi tắt, transformer không chèn và retransform lớp | Đổi cấu hình **và** yêu cầu JVM retransform | Khi tắt có thể loại bỏ hẳn lời gọi được agent này chèn | Retransformation có chi phí, phải tuân thủ giới hạn JVM và xử lý lỗi |

**Chọn thiết kế:** nếu cần thay đổi rất thường xuyên, soft toggle thường kinh tế hơn. Nếu phép đo tốn chi phí ngay cả ở trạng thái không hoạt động hoặc cần giảm tối đa tác động khi tắt, hard toggle hợp lý hơn, với tần suất và số lớp được retransform có giới hạn. Có thể kết hợp: dùng retransformation một lần để cài hook, rồi dùng soft toggle cho những thay đổi liên tục.

Đổi một biến cấu hình **không tự động sửa phương thức đã nạp**. Để hard toggle, phải chủ động gọi `retransformClasses` (hoặc công cụ khác có cùng mục đích) trên những `Class<?>` mục tiêu.

## 3. JVM thực hiện retransformation như thế nào?

Với agent khai báo `Can-Retransform-Classes: true`, JVM hỗ trợ capability này và transformer đăng ký bằng `addTransformer(transformer, true)`, luồng cơ bản là:

1. Lấy bytecode cơ sở của lớp (có thể khác byte ban đầu về constant pool hoặc một số thuộc tính).
2. Tái sử dụng kết quả trước đó của các transformer **không** hỗ trợ retransformation, không gọi lại chúng.
3. Gọi lại các transformer **có** hỗ trợ retransformation theo thứ tự của chuỗi.
4. Kiểm tra những thay đổi hợp lệ và cài đặt lớp đã chuyển đổi.

Đối với một transformer có khả năng retransformation, việc trả `null` nghĩa là **transformer đó không thay đổi byte được truyền cho lần gọi hiện tại**. Trong mô hình một transformer tự chèn probe trên bytecode cơ sở, khi tắt rồi retransform, probe do chính transformer đó chèn sẽ biến mất khỏi các lời gọi mới. Tuy nhiên, `null` **không phải lệnh khôi phục mọi thay đổi của toàn bộ JVM**: các transformer khác, đặc biệt transformer không hỗ trợ retransformation, vẫn có thể để lại thay đổi.

Các điều kiện cần kiểm tra trước khi thay đổi:
- Manifest của agent có `Premain-Class` (hoặc `Agent-Class` cho attach phù hợp) và `Can-Retransform-Classes: true`.
- `instrumentation.isRetransformClassesSupported()` trả `true`; `addTransformer(transformer, true)` đã thành công.
- `instrumentation.isModifiableClass(target)` trả `true`; không phải mọi lớp đều có thể sửa.
- Định danh mục tiêu gồm **tên lớp và class loader** (nhiều class loader có thể chứa các lớp trùng tên).
- Thay đổi chỉ ở phần bytecode/thuộc tính được JVM cho phép; không thêm/xóa trường hoặc phương thức, đổi chữ ký, cấu trúc kế thừa hay thay đổi schema bị cấm.
- Hook và các lớp trợ giúp có thể truy cập được từ class loader/module của lớp mục tiêu.

**Tác động khi đang chạy:** stack frame đã vào phương thức trước khi retransformation có thể tiếp tục chạy bytecode cũ. Những lần gọi mới sau đó sử dụng định nghĩa mới. Đối tượng hiện có và biến static vẫn tồn tại; retransformation không chạy lại bộ khởi tạo lớp.

## 4. Quy trình đổi cấu hình an toàn

Một vòng `reconcile(desiredConfig)` nên hoạt động theo thứ tự:

1. **Nạp và xác thực cấu hình:** kiểm tra `enabled`, danh sách lớp/phương thức được phép, phiên bản cấu hình, thời hạn hiệu lực; từ chối giá trị không hợp lệ. Có thể ghi file mới rồi đổi tên nguyên tử để tránh đọc trúng file đang ghi dở.
2. **So sánh với cấu hình đang áp dụng:** nếu trạng thái không đổi, không gọi lại retransformation vô ích. Đặt giới hạn tần suất và gom nhiều thay đổi thành một lần.
3. **Xác định đúng tập mục tiêu:** duyệt `getAllLoadedClasses()` theo allowlist + class loader + chữ ký phương thức; xác nhận bằng `isModifiableClass`. Lớp chưa nạp sẽ được xử lý khi nạp sau này bởi transformer còn đăng ký.
4. **Kiểm tra tác động:** đếm số lớp, kích thước bytecode, tình trạng hệ thống; giới hạn theo lô và tránh thay đổi hàng loạt trong giai đoạn tải cao.
5. **Áp dụng trạng thái cho transformer**, rồi `retransformClasses` trên đúng tập lớp đã duyệt. Đồng bộ hóa các lần cập nhật cấu hình để không có hai tác vụ sửa chồng nhau.
6. **Xác minh thực tế:** ghi nhận số lớp dự kiến/đã thử/đã thành công, lỗi transformer, phiên bản cấu hình; kiểm tra số lần gọi hook ở một ca thử hoặc tín hiệu đo lường thật.
7. **Rollback khi lỗi:** giữ trạng thái áp dụng cuối cùng, khôi phục cờ và retransform lại nếu cần. Không công bố thành công chỉ vì đọc được cấu hình mới.

Với hệ thống nhiều class loader hoặc hàng nghìn lớp, không nên để một cấu hình tự do kích hoạt retransformation toàn bộ JVM. Chọn các class/method cụ thể và đưa quyết định bật/tắt sau xác thực vào một điểm điều phối.

## 5. Ví dụ chạy được: Java 17+, Maven, ASM và startup agent

Ví dụ dùng **hard toggle**. Khi `probe.enabled=true`, agent thêm lời gọi `ProbeHooks.hit()` vào đầu `demo.OrderService.work()`; khi `false`, nó trả `null` trong lần retransformation tiếp theo. Ứng dụng đã khởi động không cần restart. Ta dùng ASM để tạo bytecode hợp lệ; Java Instrumentation API không tự cung cấp thao tác chèn lệnh JVM.

Cấu trúc thư mục:

```text
dynamic-probe/
├── pom.xml
├── probe.properties
└── src/main/java/
    ├── agent/
    │   ├── ProbeAgent.java
    │   └── ProbeTransformer.java
    └── demo/
        ├── OrderService.java
        ├── ProbeHooks.java
        └── Main.java
```

**`pom.xml`** — đóng gói agent và ASM vào cùng một executable agent JAR:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dynamic-probe</artifactId>
    <version>1.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>agent.ProbeAgent</Premain-Class>
                                        <Can-Retransform-Classes>true</Can-Retransform-Classes>
                                    </manifestEntries>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**`probe.properties`** — cấu hình ban đầu:

```properties
probe.enabled=false
```

**`src/main/java/agent/ProbeAgent.java`** — đọc cấu hình, giữ transformer đã đăng ký và điều khiển retransformation:

```java
package agent;

import java.io.IOException;
import java.io.Reader;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Properties;

public final class ProbeAgent {
    private static volatile boolean enabled;
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String args, Instrumentation inst) throws IOException {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation unavailable");
        }
        instrumentation = inst;
        enabled = readEnabled();
        inst.addTransformer(new ProbeTransformer(), true);
        System.out.println("[agent] enabled=" + enabled);
    }

    static boolean enabled() {
        return enabled;
    }

    public static synchronized void reload()
            throws IOException, UnmodifiableClassException {
        boolean next = readEnabled();
        if (next == enabled) {
            return;
        }

        // Demo: chỉ tìm lớp OrderService do application class loader nạp.
        Class<?> target = Arrays.stream(instrumentation.getAllLoadedClasses())
                .filter(c -> c.getName().equals("demo.OrderService"))
                .filter(c -> c.getClassLoader() == ClassLoader.getSystemClassLoader())
                .findFirst()
                .orElse(null);

        if (target != null && !instrumentation.isModifiableClass(target)) {
            throw new IllegalStateException("Target class is not modifiable");
        }

        boolean previous = enabled;
        enabled = next;
        try {
            // Nếu lớp chưa nạp, transformer sẽ áp dụng trạng thái mới khi nạp.
            if (target != null) {
                instrumentation.retransformClasses(target);
            }
        } catch (UnmodifiableClassException | RuntimeException | Error e) {
            enabled = previous;
            throw e;
        }
        System.out.println("[agent] enabled=" + enabled);
    }

    private static boolean readEnabled() throws IOException {
        Properties values = new Properties();
        try (Reader reader = Files.newBufferedReader(
                Path.of("probe.properties"), StandardCharsets.UTF_8)) {
            values.load(reader);
        }
        String raw = values.getProperty("probe.enabled");
        if (raw == null || (!raw.equalsIgnoreCase("true")
                && !raw.equalsIgnoreCase("false"))) {
            throw new IllegalArgumentException(
                    "probe.enabled must be true or false");
        }
        return Boolean.parseBoolean(raw);
    }
}
```

**`src/main/java/agent/ProbeTransformer.java`** — chỉ chèn lời gọi hook vào đúng một phương thức; không đổi chữ ký hay cấu trúc lớp:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

final class ProbeTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain,
            byte[] classfileBuffer) {
        if (!"demo/OrderService".equals(className) || !ProbeAgent.enabled()) {
            return null;
        }

        ClassReader reader = new ClassReader(classfileBuffer);
        ClassWriter writer =
                new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name,
                    String descriptor, String signature, String[] exceptions) {
                MethodVisitor method = super.visitMethod(
                        access, name, descriptor, signature, exceptions);
                if (!"work".equals(name) || !"()I".equals(descriptor)) {
                    return method;
                }
                return new MethodVisitor(Opcodes.ASM9, method) {
                    @Override
                    public void visitCode() {
                        super.visitCode();
                        super.visitMethodInsn(Opcodes.INVOKESTATIC,
                                "demo/ProbeHooks", "hit", "()V", false);
                    }
                };
            }
        };

        reader.accept(visitor, 0);
        return writer.toByteArray();
    }
}
```

`ClassReader` đọc bytecode hiện tại của vòng transform; `ClassVisitor` chọn đúng phương thức `work()I` (không tham số, trả `int`); `visitCode()` thêm lời gọi static ở đầu phương thức. `COMPUTE_MAXS` tính lại giới hạn stack/local cần thiết. Với biến đổi phức tạp làm thay đổi flow/frame, phải tính và kiểm tra stack map frames phù hợp; không áp dụng máy móc ví dụ này cho mọi class file.

**`src/main/java/demo/OrderService.java`**:

```java
package demo;

public class OrderService {
    public int work() {
        return 40 + 2;
    }
}
```

**`src/main/java/demo/ProbeHooks.java`** — tín hiệu đo có thể quan sát:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public final class ProbeHooks {
    private static final AtomicInteger HITS = new AtomicInteger();

    private ProbeHooks() {}

    public static void hit() {
        System.out.println("[probe] hit=" + HITS.incrementAndGet());
    }

    public static int hits() {
        return HITS.get();
    }
}
```

**`src/main/java/demo/Main.java`** — mỗi lần nhấn Enter sẽ đọc lại cấu hình, chuyển trạng thái và gọi phương thức:

```java
package demo;

import agent.ProbeAgent;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class Main {
    public static void main(String[] args) throws Exception {
        OrderService service = new OrderService();
        System.out.println("work=" + service.work()
                + ", hits=" + ProbeHooks.hits());
        System.out.println("Edit probe.properties, then press Enter to reload.");

        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        while (input.readLine() != null) {
            ProbeAgent.reload();
            System.out.println("work=" + service.work()
                    + ", hits=" + ProbeHooks.hits());
        }
    }
}
```

Từ thư mục `dynamic-probe`, cần JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
java -javaagent:target/dynamic-probe-1.0.jar -cp target/dynamic-probe-1.0.jar demo.Main
```

Không dừng ứng dụng: sửa `probe.properties` thành `probe.enabled=true`, lưu file và nhấn Enter trên terminal ứng dụng. Sau đó sửa thành `false`, lưu và nhấn Enter lần nữa.

Đầu ra minh họa (lược bỏ dòng nhắc thao tác):

```text
[agent] enabled=false
work=42, hits=0
[agent] enabled=true
[probe] hit=1
work=42, hits=1
[agent] enabled=false
work=42, hits=1
```

Khi **bật**, `reload()` đặt trạng thái mong muốn rồi retransform `OrderService`; ASM thêm lệnh gọi `ProbeHooks.hit()`. Khi **tắt**, transformer được gọi lại nhưng trả `null`, vì vậy trong ví dụ một-transformer này mã `work()` sau retransform không còn lệnh gọi probe. Biến đếm vẫn bằng `1` vì retransformation không đặt lại trạng thái static. Trong ví dụ, nhấn Enter là thao tác kích hoạt reload chủ động: chỉ sửa file mà không reload thì chưa chuyển trạng thái.

**Giới hạn chủ ý của ví dụ:** ứng dụng demo và agent cùng trong một JAR, dùng system class loader, chọn một lớp và một phương thức, chỉ cho phép một luồng điều khiển reload. Trong sản phẩm thật, probe thường ở agent/helper riêng; phải giải quyết khả năng nhìn thấy helper giữa các module/class loader, nhận cấu hình từ nguồn có kiểm soát và theo dõi mọi lỗi transformer. Đoạn code minh họa nguyên lý, chưa phải hệ thống điều phối production.

## 6. Thiết kế dành cho hệ thống thực tế

Có thể biểu diễn trạng thái cấu hình và trạng thái thực thi riêng biệt:

```text
config version N, desired=ON
         |
         v
Validate + authorize + allowlist
         |
         v
Find loaded Class<?> + modifiability check
         |
         v
Single-flight coordinator + bounded batches
         |
         v
Transformer reads immutable config snapshot
         |
         v
retransformClasses(targets...)
         |
         v
Verify probe hits/errors + record applied version
         |
    PASS / FAIL
     |      |
     v      v
commit   rollback + alert
```

Trong agent phục vụ nhiều lớp, nên dùng snapshot cấu hình bất biến (ví dụ một `record ProbeConfig(long version, boolean enabled, Set<String> targets)`) và thay toàn bộ snapshot atomically. Khi bắt đầu một vòng retransform, khóa điều phối và gắn phiên bản cho lần thay đổi; tránh trộn quyết định của hai phiên bản. Ví dụ dùng `volatile boolean` chỉ đủ để chứng minh một điểm đo đơn giản.

Các quyết định vận hành cần nêu rõ:
- **Phạm vi:** allowlist chính xác tên class, class loader, method descriptor; không quét rồi thay đổi toàn bộ lớp chỉ vì tên package giống nhau.
- **Giới hạn:** giới hạn số lớp/lần, khoảng cách tối thiểu giữa các lần chuyển và thời gian chờ; phân lô theo mức độ ảnh hưởng của ứng dụng.
- **Tín hiệu:** `requested_version`, `applied_version`, `candidate_count`, `modified_count`, `transform_error_count`, `probe_hit_count`, thời gian retransform và số lần rollback.
- **An toàn hook:** hook không gọi ngược vào chính phương thức đang đo, không thực hiện I/O đồng bộ nặng trong đường nóng, tránh tạo dữ liệu nhạy cảm và tránh giữ tham chiếu tới class loader gây rò rỉ.
- **Độ tin cậy:** kiểm tra đầu ra bytecode và hành vi thật; ngoại lệ xảy ra bên trong `ClassFileTransformer.transform` có thể không làm JVM dừng chuỗi transformer, nên cần bắt/ghi nhận lỗi để tránh báo trạng thái sai.
- **Bảo vệ thao tác:** quyền đổi cấu hình, audit người thực hiện/lý do và khả năng tắt nhanh khi probe tăng độ trễ.

Một lựa chọn rollback an toàn là giữ snapshot cấu hình đã áp dụng thành công, khôi phục snapshot đó nếu có lỗi, gọi retransformation cho phần bị ảnh hưởng khi cần và xác minh lại. Với nhiều lớp, phải phân biệt thành công một lô với thành công toàn bộ chiến dịch; cần phát hiện trường hợp đang chuyển dở.

## 7. Trường hợp thử và lỗi thường gặp

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| `false` lúc khởi động | `work()` trả `42`, không tăng `hits` |
| Đổi `false → true` rồi reload | Lần gọi mới tạo một `[probe] hit=...` |
| Đổi `true → false` rồi reload | Lần gọi mới không tăng `hits`; số đếm cũ vẫn giữ |
| Reload cùng trạng thái | Không cần `retransformClasses` |
| Cấu hình có giá trị `maybe` hoặc thiếu key | Từ chối, giữ trạng thái đang áp dụng |
| Class chưa được nạp | Không có class để retransform; transformer xử lý khi lớp được nạp |
| Class không modifiable / capability không có | Từ chối với lỗi rõ ràng, không giả báo thành công |
| Có nhiều transformer cùng tác động | Xem xét thứ tự/chồng lắp bytecode và xác minh hook nào còn lại |
| Lời gọi đang nằm trên stack | Có thể hoàn thành với bytecode cũ; đo trên các lời gọi mới |

Các lỗi tư duy đáng tránh:

1. **Chỉ sửa cấu hình mà không kích hoạt retransform:** code đã nạp vẫn như cũ với hard toggle.
2. **Quên `Can-Retransform-Classes` hoặc đăng ký `addTransformer(transformer)` mặc định:** khả năng retransformation không được bật cho transformer đó.
3. **Gọi `removeTransformer` để mong gỡ probe ngay:** thao tác này ngừng những lần transform tương lai; nó không chủ động loại bỏ bytecode đã được chèn. Cần thiết kế phép retransform phục hồi thích hợp.
4. **Nhầm `return null` với khôi phục toàn bộ bytecode gốc:** các agent khác vẫn có thể biến đổi lớp và transformer không có khả năng retransformation có kết quả được tái sử dụng.
5. **Không phân biệt class loader:** hai lớp cùng tên từ hai loader là hai định nghĩa khác nhau; chọn sai lớp có thể đo sai ứng dụng.
6. **Thay đổi cấu trúc lớp khi retransform:** thêm field/method, đổi signature/hierarchy có thể bị JVM từ chối.
7. **Coi hoàn thành API là đảm bảo probe hoạt động:** cần đo tín hiệu thật và lỗi trong transformer; tránh bất ngờ khi callback bị lỗi hoặc không khớp tên/chữ ký phương thức.
8. **Bật/tắt liên tục trên lớp nóng:** tốn tài nguyên, có thể gây ảnh hưởng độ trễ; cân nhắc soft toggle hoặc giới hạn tần suất.

## 8. Câu hỏi tự kiểm tra

1. Vì sao đổi `probe.enabled=false` trong file không xóa ngay lệnh gọi hook trong bytecode đã nạp?
2. Nếu transformer của bạn trả `null` khi tắt, vì sao thay đổi của một agent khác vẫn có thể còn?
3. Vì sao cần `isRetransformClassesSupported()` **và** `isModifiableClass(target)`?
4. Điều gì xảy ra với lời gọi đang thực thi ở giữa phương thức khi lớp được retransform?
5. Trong hệ thống có nhiều class loader và hàng nghìn lớp, bạn sẽ xác định allowlist, chia lô, xác minh và rollback thế nào?

## 9. Tài liệu tham khảo

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability, đăng ký transformer, `retransformClasses`, `isModifiableClass`.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thứ tự transformer, giá trị trả về và lỗi callback.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cấu hình agent JAR và manifest.
