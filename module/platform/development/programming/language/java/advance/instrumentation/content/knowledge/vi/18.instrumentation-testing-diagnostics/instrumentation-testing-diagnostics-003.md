# Lưu byte đầu vào/đầu ra có chọn lọc và đọc lại bằng javap

## 1. Khi transformer hoạt động nhưng bạn chưa biết JVM đã nhận bytecode gì

Trong hệ thống Java instrumentation, một `ClassFileTransformer` có thể trả về mảng bytes mới mà không ném lỗi, nhưng ứng dụng vẫn xuất hiện `VerifyError`, `NoClassDefFoundError`, method không được hook, hỏng nhánh `try/finally` hoặc dữ liệu quan sát sai. Chỉ log “transform invoked” và một con số thời gian xử lý thường không đủ để tìm nguyên nhân.

Cách chẩn đoán thực dụng là **chụp có chọn lọc classfile bytes ở hai mốc**:

1. **Input snapshot:** sao chép `classfileBuffer` được truyền vào đúng callback transformer mà ta điều tra.
2. **Output snapshot:** sao chép mảng `byte[]` mà transformer **dự định trả về** sau khi biến đổi.

Sau đó dùng công cụ có sẵn trong JDK, **`javap -c -v -p`**, để đọc cả hai classfiles, so cấu trúc constant pool, instructions, method descriptors, attributes, exception table và mã nguồn line information (nếu có).

**Điểm cốt lõi:** Snapshot “before” và “after” nói về **một bước trong pipeline**. Chúng không mặc nhiên là bytes gốc trên ổ đĩa và bytes cuối cùng JVM cài đặt, nhất là khi nhiều transformers cùng tham gia hoặc JVM chuẩn hóa lại một số chi tiết classfile.

### Học xong bạn có thể làm gì?

- Biết chính xác `classfileBuffer` và `return byte[]` nằm ở đâu trong thứ tự transform.
- Lọc theo **internal class name**, defining class loader, `Module` và sự kiện load/retransform/redefine, tránh chụp toàn bộ ứng dụng.
- Lưu hai snapshot dạng **binary `.class`** (không phải chuỗi `byte[]`, `Arrays.toString` hay base64) với giới hạn kích thước và tên ổn định cho demo.
- Chạy một ví dụ **Java 17+**: trước `"BEFORE"`, sau `"AFTER!"`; kiểm chứng bằng `javap -c -v`, rồi chạy ứng dụng để đối chiếu.
- Nhận ra những giới hạn của việc sửa literal trực tiếp trong constant pool; không dùng thủ thuật minh họa làm bytecode writer sản xuất.
- Tránh rủi ro về performance, class-loading reentrancy, I/O lỗi, data sensitivity, duplicate filenames và classloader collisions khi debug agent.

## 2. Pipeline transformer: “input” và “output” thật sự có nghĩa gì?

### 2.1. Từ classfile tới class đang chạy

Hình dung khi một class lần đầu được định nghĩa:

~~~text
Class loader / JVM cung cấp classfile bytes
                    |
                    v
          Transformer A (có thể sửa)
                    |
                    v
       [input của transformer B] -----> chụp BEFORE tại B
                    |
                    v
          Transformer B biến đổi
                    |
                    +---------------> chụp AFTER mà B trả về
                    |
                    v
          Transformer C (nếu có)
                    |
                    v
       JVM kiểm tra/link/định nghĩa class
                    |
                    v
             App thực thi method
~~~

Trong `ClassFileTransformer.transform(...)`:

- Tham số `classfileBuffer` là đầu vào của **callback hiện tại**, có thể **đã được các transformer trước đó sửa**.
- Nếu transformer không muốn thay đổi, trả về **`null`**.
- Nếu tạo bytes mới, trả về một **mảng `byte[]` hợp lệ**; **không sửa `classfileBuffer` tại chỗ**.
- Transformer chạy **trước** khi JVM kiểm tra/chấp nhận kết quả class definition; trả một output không bảo đảm class sẽ verify/link thành công.
- Nếu transformer khác chạy **sau**, output của ta không nhất thiết là output cuối của pipeline.
- Các transformers được gọi theo thứ tự nhóm và thứ tự đăng ký được mô tả trong Javadoc. Khi nhiều agent hoạt động, phải kiểm tra **toàn bộ chuỗi**.

Do đó nên gắn nhãn rõ:

~~~text
transformer-B.input.class
transformer-B.returned.class
~~~

Chứ không tùy tiện đặt tên `original.class` hoặc `jvm-installed.class` nếu chưa có chứng cứ đủ mạnh.

### 2.2. Khi `transform(...)` trả `null` thì “after” là gì?

`null` nghĩa là **không thực hiện biến đổi ở bước này**. Đừng tạo một file mang nhãn `after-transformed` chỉ bằng cách ghi lại input rồi khẳng định transformer đã biến đổi nó.

Có thể chọn chính sách:

| Kết quả callback | Capture policy có ích |
|---|---|
| Transformer trả một `byte[]` mới | Chụp input và bytes trả về, đánh dấu `transformed=true` |
| Transformer trả `null` | Chụp input nếu cần, ghi metadata `unchanged=true`, không bịa ra file after mới |
| Transformer ném exception | Ghi lỗi tối thiểu qua kênh độc lập; không coi output hợp lệ |
| Class không khớp filter | Không chụp, không log dữ liệu nhạy cảm của class đó |
| Classfile vượt giới hạn | Bỏ qua snapshot hoặc fail theo policy, không cấp phát/ghi file vô hạn |

**Trong ví dụ runnable**, transformer chỉ chụp khi tìm được literal chính xác và thực sự trả mảng mới. Nếu không tìm thấy literal, ví dụ trả `null` và không ghi snapshot đôi.

### 2.3. Retransform/redefine khác initial class load

Một callback có thể xảy ra khi class **được load lần đầu**, **retransform** hoặc **redefine**:

- Với initial load, `classBeingRedefined` thường là `null`.
- Với redefine/retransform, `classBeingRedefined` là class object đã tồn tại; nguồn input của callback phải được hiểu theo hợp đồng riêng của Instrumentation.
- Khi `retransformClasses`, JVM có thể gọi lại transformer đăng ký `canRetransform=true`, đồng thời tái áp dụng kết quả các transformer không capable.
- Sau một lần `redefineClasses`, nguồn cơ sở cho retransform tiếp theo có thể là bytes của **lần redefine gần nhất**, không phải JAR lúc startup.
- Nhiều lần callback của **cùng binary name** có thể dùng bytes khác nhau theo thời điểm.

Đừng chỉ đặt tên `MyClass.class` rồi ghi đè liên tục. Nếu mục tiêu là nghiên cứu nhiều lượt, cần metadata gồm **load/redefine/retransform**, sequence number, loader identity, module, timestamp và byte hashes để phân biệt. Demo dưới đây cố ý **chỉ chụp một lượt initial load** để file và stdout xác định.

## 3. Lọc trước khi lưu: chọn class đủ hẹp

Một Java agent thực có thể thấy hàng nghìn hoặc hàng chục nghìn lượt class definition. Nếu mỗi callback đều ghi đầy đủ bytes:

- Startup và class loading bị chậm do filesystem I/O.
- Dung lượng disk tăng nhanh; có thể chứa logic, string literals, URLs, tokens hoặc thông tin nhạy cảm trong constant pool.
- Dump nhiều class từ các loaders khác nhau cùng tên có thể đè lên nhau.
- Helper/logging của chính agent có thể kích hoạt reentrancy hoặc thêm những class loads ngoài ý muốn.
- Việc chụp quá rộng làm nhiễu bằng chứng, khó tìm class gây lỗi.

**Nguyên tắc an toàn:** lọc rẻ tiền bằng metadata **trước khi đọc/sửa/copy classfile bytes**, sau đó mới kiểm tra kích thước và giới hạn lượt chụp.

### 3.1. Thứ tự bộ lọc khuyến nghị

| Tiêu chí | Điều cần kiểm tra | Vì sao |
|---|---|---|
| Class name | `"demo/target/Greeter".equals(className)` | JVM dùng **internal name** với dấu `/`, không phải `demo.target.Greeter` |
| Class loader | `loader == expectedLoader` | Cùng binary name nhưng khác defining loader là class khác |
| Module | `module == null || !module.isNamed()` trong bài lab | Ví dụ app trên classpath thuộc unnamed module; named modules cần policy riêng |
| Phase | `classBeingRedefined == null` | Demo chỉ capture initial load, tránh trộn retransform/redefine |
| Capture budget | `AtomicBoolean.compareAndSet(false, true)` | Chỉ một snapshot được nhận; tránh race callback đồng thời |
| Byte budget | `input.length <= MAX_BYTES` | Không dump class vô hạn, giảm rủi ro memory/disk |
| Transform result | Chỉ lưu khi patch tạo bytes hợp lệ theo chính sách demo | Để cặp before/after có sự khác biệt thật |

**Không dùng `className.endsWith("Service")` trên production để dump cả hệ thống**. Nếu cần nhiều classes, dùng allowlist từ cấu hình với giới hạn kích thước/số file/bộ nhớ/TTL, chính sách bảo mật và nơi lưu riêng.

### 3.2. `className` có thể cần kiểm tra null

Theo hợp đồng `ClassFileTransformer`, tên nội bộ được cung cấp trong nhiều trường hợp, nhưng có những đường class definition đặc biệt mà tên có thể `null`. Viết:

~~~java
if (!"demo/target/Greeter".equals(name)) {
    return null;
}
~~~

an toàn hơn `name.equals(...)` khi chưa biết giá trị. Tương tự, bootstrap-defined classes có `loader == null`; nếu bạn lọc `loader == ClassLoader.getSystemClassLoader()` thì **không** bắt bootstrap classes.

### 3.3. `Module` và class loader không thay thế nhau

Hai class cùng `className` và cùng loader chưa chắc có cùng yêu cầu module access khi triển khai kiến trúc module phức tạp. Với Java 9+, callback sáu tham số nhận `Module`; có thể đọc `module.getName()` nếu named module.

Ví dụ chỉ dùng classpath bình thường nên module của target là **unnamed**, filter cho phép `module == null` (đường tương thích) hoặc `!module.isNamed()`. Trong plugin/custom loader thực tế, điều kiện module, layer và class identity cần được định nghĩa theo mục tiêu. Đừng chỉ so `module.getName()` vì nó có thể null trên unnamed module.

## 4. Thiết kế snapshot để có thể đối chiếu và không làm hỏng runtime

### 4.1. Lưu raw classfile bytes, không phải biểu diễn text

Ví dụ đúng:

~~~java
Files.write(path, classfileBuffer, StandardOpenOption.CREATE_NEW);
~~~

Lời gọi nhận `byte[]` và ghi **byte-for-byte**. Ngược lại, các cách như:

~~~java
System.out.println(Arrays.toString(classfileBuffer));
Files.writeString(path, new String(classfileBuffer));
~~~

không tạo file `.class` dùng được. Bytecode là dữ liệu nhị phân; đổi sang chuỗi có thể làm mất dữ liệu hoặc thay encoding.

Mã ở trên chỉ là **mảnh minh họa API**, không phải chương trình độc lập: `path`/`classfileBuffer` phải có sẵn trong callback và thêm imports. Ví dụ đầy đủ ở phần sau.

### 4.2. Không ghi đè và không lẫn phiên chạy

Demo dùng tên:

~~~text
captures/run-001/Greeter-before.class
captures/run-001/Greeter-after.class
~~~

và `StandardOpenOption.CREATE_NEW`. Nếu path đã tồn tại, lệnh báo lỗi thay vì **ghi đè** snapshot cũ. Mỗi lần chạy dùng một thư mục mới: `run-001`, `run-002`, v.v.

Trong production, có thể đặt cấu trúc:

~~~text
captures/
  run-id/
    loader-id/
      module-id/
        internal/name/target-<sequence>-input.class
        internal/name/target-<sequence>-returned.class
        target-<sequence>-metadata.json
~~~

Đó là **mẫu naming convention**, không phải đầu ra tự có của demo. Không được tin tuyệt đối `System.identityHashCode(loader)` là ID bền vững giữa các lần chạy hoặc vĩnh viễn duy nhất: có thể collision, giá trị không mang nghĩa toàn cục. Nếu cần identity chắc hơn, dùng object identity registry ở phạm vi một process cộng sequence/UUID; nhớ không vô tình giữ class loaders sống quá lâu.

### 4.3. Tài liệu đi kèm nên có gì?

Một manifest/log entry cho từng cặp snapshot nên chứa:

- JVM/version, agent/build version, timestamp và run ID.
- Internal class name, defining loader identity, module/layer nếu liên quan.
- Phase: initial load, redefine hay retransform.
- Transformer ID và thứ tự trong pipeline nếu biết được.
- Input length, returned length, SHA-256 của cả hai; optional classfile major version.
- Transform outcome: transformed, unchanged, skipped, error.
- Lý do skip và giới hạn kích thước.
- Link tới testcase/reproduction context, không lưu secrets vào log.

**Checksum** cho biết hai files có cùng bytes hay không, **không** chứng minh bytes hợp lệ hoặc behavior đúng. `javap` giúp đọc cấu trúc; JVM verifier và test thực thi mới cho thêm thông tin correctness.

### 4.4. Performance và khả năng phục hồi

Việc ghi file ngay trong `transform(...)` có thể giữ class loading chờ I/O, làm thay đổi timing, tăng p99 và gây deadlock nếu chạm filesystem/network mount. Bởi vậy:

1. Bật capture bằng feature flag **chỉ khi chẩn đoán**.
2. Filter trước, cấp phát/copy nhỏ và có giới hạn.
3. Chặn số class, số bytes, số lần/callback theo ngân sách.
4. Không làm blocking network export ngay trong callback.
5. Nếu cần capture nhiều, dùng bounded queue/writer thread được thiết kế cẩn thận; log dropped snapshots, flush/shutdown đúng.
6. Đừng nuốt mọi lỗi rồi tuyên bố capture đã thành công.

Demo dùng synchronous `Files.write` chỉ để dễ tái hiện **một class nhỏ một lần**. Đó không phải mẫu throughput tối ưu cho agent sản phẩm.

## 5. Thí nghiệm Java 17+: Greeter trước và sau biến đổi

Chúng ta tạo:

- Class ứng dụng `demo.target.Greeter`, method `message()` trả literal `"BEFORE"`.
- Startup Java agent `demo.agent.SnapshotAgent`, đăng ký một transformer filter chính xác class này.
- Transformer đọc constant pool và **chỉ đổi một literal ASCII sáu byte** từ `"BEFORE"` thành `"AFTER!"`, không thay độ dài classfile.
- Agent lưu input vào `Greeter-before.class` và bytes trả về vào `Greeter-after.class`.
- App gọi `Greeter.message()`; khi agent được dùng đúng, output là `"AFTER!"`.
- `javap -c -v` dùng để quan sát literal và instruction `ldc` trong hai bản.

**Giới hạn của thí nghiệm:** sửa trực tiếp `CONSTANT_Utf8` mà không dùng parser thư viện là thủ thuật **chỉ cho hai literal ASCII đồng độ dài trong class được kiểm soát**. Nó không phù hợp với classfile tùy ý, bytecode instrumentation thật, thay StackMapTable, thêm branch hoặc thay method signature. Khi xây sản phẩm, dùng bytecode library có verifier/testing như ASM/Byte Buddy; không sao chép parser tối giản thành công cụ tổng quát.

### 5.1. Cây thư mục

~~~text
snapshot-lab/
├── AGENT.MF
├── src/
│   ├── agent/demo/agent/SnapshotAgent.java
│   └── app/demo/
│       ├── app/App.java
│       └── target/Greeter.java
├── out/                         # tạo khi build
│   ├── agent/
│   ├── app/
│   └── snapshot-agent.jar
└── captures/                    # tạo khi chạy
    └── run-001/
        ├── Greeter-before.class
        └── Greeter-after.class
~~~

Các file trong `captures` được tạo bởi agent; **không** đặt chúng vào runtime classpath. Tên file snapshot không trùng `Greeter.class` gốc, nhưng `javap` vẫn có thể đọc **đường dẫn tới classfile bytes** như được minh họa bên dưới.

### 5.2. Tệp `src/app/demo/target/Greeter.java`

~~~java
package demo.target;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "BEFORE";
    }
}
~~~

Method chỉ trả một string literal. Khi biên dịch `javac --release 17`, constant pool chứa `CONSTANT_String` tham chiếu một `CONSTANT_Utf8` với nội dung `BEFORE`. Method có thể dùng instruction `ldc` để lấy literal; sau khi transformer đổi UTF8, instruction không cần thay opcode hay constant-pool index.

### 5.3. Tệp `src/app/demo/app/App.java`

~~~java
package demo.app;

import demo.target.Greeter;

public final class App {
    private App() {}

    public static void main(String[] args) {
        System.out.println("[app] message=" + Greeter.message());
    }
}
~~~

Ứng dụng sẽ trigger load `Greeter` khi cần dùng class (có thể đã được JVM load sớm hơn theo implementation, nhưng trong chạy demo callback vẫn xảy ra sau khi startup agent đã đăng ký). Nó không tự gọi API instrumentation.

### 5.4. Tệp `src/agent/demo/agent/SnapshotAgent.java`

~~~java
package demo.agent;

import java.io.IOException;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SnapshotAgent {
    private SnapshotAgent() {}

    public static void premain(String args, Instrumentation inst) {
        if (args == null || args.isBlank()) {
            throw new IllegalArgumentException(
                    "Pass an empty capture directory as agent argument");
        }
        Path directory = Path.of(args).toAbsolutePath().normalize();
        inst.addTransformer(new SnapshotTransformer(directory), false);
    }

    private static final class SnapshotTransformer implements ClassFileTransformer {
        private static final int MAX_BYTES = 1024 * 1024;
        private final Path directory;
        private final AtomicBoolean captured = new AtomicBoolean();

        SnapshotTransformer(Path directory) {
            this.directory = directory;
        }

        @Override
        public byte[] transform(ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
            return capture(null, loader, name, classBeingRedefined, bytes);
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader, String name,
                Class<?> classBeingRedefined, ProtectionDomain domain, byte[] bytes) {
            return capture(module, loader, name, classBeingRedefined, bytes);
        }

        private byte[] capture(Module module, ClassLoader loader,
                String name, Class<?> redefining, byte[] input) {
            if (!"demo/target/Greeter".equals(name)
                    || loader != ClassLoader.getSystemClassLoader()
                    || (module != null && module.isNamed())
                    || redefining != null || input == null) {
                return null;
            }
            if (!captured.compareAndSet(false, true)) {
                return null;
            }
            if (input.length > MAX_BYTES) {
                System.err.println("[agent] skip capture: classfile too large");
                return null;
            }

            byte[] output = patchLiteral(input);
            if (output == null) {
                System.err.println("[agent] skip capture: expected literal not found");
                return null;
            }
            try {
                Files.createDirectories(directory);
                Files.write(directory.resolve("Greeter-before.class"),
                        input, StandardOpenOption.CREATE_NEW);
                Files.write(directory.resolve("Greeter-after.class"),
                        output, StandardOpenOption.CREATE_NEW);
                System.out.println("[agent] captured demo/target/Greeter");
            } catch (IOException ex) {
                System.err.println("[agent] capture error: "
                        + ex.getClass().getSimpleName());
            }
            return output;
        }

        private static byte[] patchLiteral(byte[] input) {
            if (input.length < 10
                    || (input[0] & 255) != 0xCA
                    || (input[1] & 255) != 0xFE
                    || (input[2] & 255) != 0xBA
                    || (input[3] & 255) != 0xBE) {
                return null;
            }
            int count = u2(input, 8);
            int pos = 10;
            int changed = 0;
            byte[] copy = input.clone();

            for (int entry = 1; entry < count; entry++) {
                if (pos >= input.length) return null;
                int tag = input[pos++] & 255;
                switch (tag) {
                    case 1: {
                        if (pos + 2 > input.length) return null;
                        int length = u2(input, pos);
                        pos += 2;
                        if (pos + length > input.length) return null;
                        if (length == 6 && asciiEquals(input, pos, "BEFORE")) {
                            asciiWrite(copy, pos, "AFTER!");
                            changed++;
                        }
                        pos += length;
                        break;
                    }
                    case 3: case 4:
                    case 9: case 10: case 11: case 12:
                    case 17: case 18:
                        pos += 4;
                        break;
                    case 5: case 6:
                        pos += 8;
                        entry++; // long/double occupy two slots
                        break;
                    case 7: case 8: case 16:
                    case 19: case 20:
                        pos += 2;
                        break;
                    case 15:
                        pos += 3;
                        break;
                    default:
                        return null;
                }
                if (pos > input.length) return null;
            }
            return changed == 1 ? copy : null;
        }

        private static int u2(byte[] bytes, int pos) {
            return ((bytes[pos] & 255) << 8) | (bytes[pos + 1] & 255);
        }

        private static boolean asciiEquals(byte[] bytes, int pos, String text) {
            for (int i = 0; i < text.length(); i++) {
                if ((bytes[pos + i] & 255) != text.charAt(i)) return false;
            }
            return true;
        }

        private static void asciiWrite(byte[] bytes, int pos, String text) {
            for (int i = 0; i < text.length(); i++) {
                bytes[pos + i] = (byte) text.charAt(i);
            }
        }
    }
}
~~~

### 5.5. Vì sao Java code này đáng tin trong phạm vi demo?

**Phần lọc:**

- `"demo/target/Greeter".equals(name)` chỉ chọn đúng internal name, tránh NPE.
- `loader == ClassLoader.getSystemClassLoader()` chỉ nhận target do system loader xử lý. Một bản `Greeter` từ plugin loader khác **không** được chụp.
- `module == null || !module.isNamed()` chỉ nhận bối cảnh classpath của lab.
- `redefining == null` loại retransform/redefine; không lẫn initial load với những callbacks sau.
- `captured.compareAndSet(false, true)` bảo đảm chỉ một lần bắt đầu xử lý dù callbacks có thể concurrent. Cờ được bật **trước** khi kiểm tra kích thước/patch; nếu bỏ qua do lỗi, demo không thử lại — đây là chủ đích “one shot”.
- `MAX_BYTES` chặn classfile trên 1 MiB trong bài lab. Giới hạn này chỉ là ví dụ, không phải ngưỡng JVM hay yêu cầu chung.

**Phần biến đổi:**

- Đọc header classfile `CAFEBABE`, `constant_pool_count` và lần lượt parse tags thường gặp trong classfile Java 17; không giả định constant pool chỉ có UTF8.
- Với một `CONSTANT_Utf8` đúng sáu byte ASCII `BEFORE`, tạo `copy` rồi thay bằng `AFTER!` — cùng độ dài nên không dời offsets.
- Nếu không tìm được **chính xác một** literal phù hợp, trả `null` để không thay class.
- Không sửa trực tiếp mảng `input`, phù hợp hợp đồng transformer. `copy` vẫn giữ structure/length, chỉ thay nội dung UTF8 cho class demo.
- Cả hai overload của `transform` được implement: dạng năm tham số để tương thích API cũ và dạng sáu tham số nhận `Module` từ Java 9+; Java 17 đã hỗ trợ.

**Phần lưu:**

- Lưu chính `input` trước transform và `output` được trả về, không serialize một string.
- `Files.write(..., CREATE_NEW)` giúp từ chối ghi đè snapshot cũ.
- Nếu I/O thất bại, code in `[agent] capture error: ...` rồi **vẫn trả bytes đã biến đổi**. Vì vậy có thể thấy ứng dụng trả AFTER! mà không có đủ hai file; phải kiểm tra stderr và tính toàn vẹn pair.
- Hai lần `Files.write` **không phải một transaction nguyên tử**. Trường hợp file before tạo được nhưng after thất bại cần cleanup/metadata protocol trong production.
- Không dùng network I/O hay instrumentation logging phức tạp bên trong callback. Nhưng `System.out/err` trong callback vẫn là I/O, có thể gây class loading/phụ thuộc bất ngờ ở hệ thống thật; trong lab đơn giản, chúng giúp thấy thứ tự.

**Không nên mở rộng parser này cho classfile tùy ý.** Nó không chứng minh mọi output Java bytecode đều hợp lệ, không cập nhật StackMapTable/offsets, không thêm methods, không xử lý mọi classfile edge case và không thay thế thư viện ASM/Byte Buddy. Với JDK có version cao hơn Java 17, có thể xuất hiện classfile features khác; demo được biên dịch `--release 17` và chỉ dùng class được kiểm soát.

### 5.6. Tệp manifest `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SnapshotAgent

~~~

Manifest phải có newline kết thúc và `Premain-Class` ở main section. Không cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` vì demo **chỉ transform lần load đầu**. Việc ghi snapshot không cần capability bổ sung nào ngoài startup agent đang hoạt động.

### 5.7. Biên dịch từ JDK 17 trở lên

Mở terminal ở root `snapshot-lab`.

**Bash/macOS/Linux:**

~~~bash
mkdir -p out/agent out/app
~~~

**PowerShell/Windows:**

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Biên dịch agent và ứng dụng, đóng gói JAR:

~~~bash
javac --release 17 -d out/agent src/agent/demo/agent/SnapshotAgent.java

javac --release 17 -d out/app src/app/demo/target/Greeter.java src/app/demo/app/App.java

jar cfm out/snapshot-agent.jar AGENT.MF -C out/agent .
~~~

Tệp `out/app/demo/target/Greeter.class` vẫn là **classfile gốc sau javac**; transform diễn ra ở runtime khi class loader nạp class. Không sửa tệp này trên ổ đĩa.

**Tách output directories** của agent và ứng dụng giúp nhận biết agent class không phải target business class. Nếu build bằng Maven/Gradle, nguyên tắc tương tự: agent JAR có manifest; application có target class. Demo không yêu cầu Maven/Gradle.

### 5.8. Chạy với một thư mục capture mới

**Bash/macOS/Linux:**

~~~bash
java -javaagent:out/snapshot-agent.jar=captures/run-001 -cp out/app demo.app.App
~~~

**PowerShell/Windows:**

~~~powershell
java "-javaagent:out/snapshot-agent.jar=captures/run-001" -cp out/app demo.app.App
~~~

Hai tham số cần phân biệt:

- `-javaagent:<jar>=<args>` load startup agent, truyền `captures/run-001` làm agent arguments.
- `-cp out/app` là classpath của **ứng dụng**; JVM tự dùng agent JAR qua `-javaagent`.
- `demo.app.App` là main class; khi chạy nó sẽ tham chiếu `demo.target.Greeter`.

**Stdout chính đã kiểm chứng:**

~~~text
[agent] captured demo/target/Greeter
[app] message=AFTER!
~~~

Đây là kết quả thực tế với thí nghiệm Java 17-target khi chạy trên JDK thử nghiệm có system class loader mặc định. Nếu chạy lại, hãy dùng một thư mục **mới** như `captures/run-002`; `CREATE_NEW` cố ý ngăn ghi đè files `run-001`.

**Nếu không chạy agent**:

~~~bash
java -cp out/app demo.app.App
~~~

ứng dụng dùng literal chưa transform:

~~~text
[app] message=BEFORE
~~~

Điều này giúp chứng minh behavior khác biệt đến từ transformer runtime, không phải do source `Greeter.java` đã bị sửa.

## 6. Dùng `javap` đọc chính hai file đã lưu

### 6.1. Lệnh kiểm tra cả constant pool và bytecode

`javap` là công cụ disassembler thuộc JDK. Trong lab:

~~~bash
javap -c -v captures/run-001/Greeter-before.class
javap -c -v captures/run-001/Greeter-after.class
~~~

Tùy mức thông tin cần đọc, có thể thêm:

~~~bash
javap -c -v -p captures/run-001/Greeter-after.class
~~~

Các flags:

| Flag | Ý nghĩa |
|---|---|
| `-c` | Disassemble bytecode instructions của methods |
| `-v` (hoặc `-verbose`) | Hiện verbose classfile details: constant pool, flags, version, attributes, line tables... |
| `-p` (hoặc `-private`) | Hiển thị mọi members, kể cả private, thay vì chỉ public/protected |
| `-l` | Hiện line/local variable tables nếu có; `-v` cũng cung cấp nhiều thông tin này |
| `-s` | In internal type signatures/descriptors; `-v` cũng có descriptors |
| `-classpath` | Dùng để tìm class theo **class name**; không cần khi bạn đã cung cấp đường dẫn tới file snapshot |

**Chú ý:** truyền `captures/.../Greeter-before.class` vào `javap` là yêu cầu đọc **file classfile đó**. Nếu chỉ dùng:

~~~bash
javap -c -v -classpath out/app demo.target.Greeter
~~~

`javap` sẽ đọc class `Greeter.class` đang nằm trong `out/app`, tức **file gốc sau javac**, không phải file `Greeter-after.class` mà agent đã lưu. Khi debug transformer, nhầm hai đường này có thể dẫn tới kết luận sai rằng biến đổi “không xảy ra”.

### 6.2. Những đoạn cần tìm trong output

Ở snapshot before, phần constant pool và method body sẽ có nội dung tương tự:

~~~text
#N = String             #M          // BEFORE
#M = Utf8                             BEFORE

public static java.lang.String message();
  Code:
     0: ldc           #N                // String BEFORE
     2: areturn
~~~

Ở snapshot after:

~~~text
#N = String             #M          // AFTER!
#M = Utf8                             AFTER!

public static java.lang.String message();
  Code:
     0: ldc           #N                // String AFTER!
     2: areturn
~~~

Đây là **rút gọn các dòng tiêu biểu**, không phải toàn bộ stdout của `javap`. Chỉ số `#N/#M` có thể khác theo compiler/versions. Thí nghiệm thực đã thấy hai snapshots đều có method `message()`, instruction `ldc` cùng vị trí, literal trong constant pool lần lượt `BEFORE` và `AFTER!`.

Tại sao instruction vẫn là `ldc`? Vì classfile `CONSTANT_String` trỏ tới `CONSTANT_Utf8` đã bị đổi, nên không cần thay instruction opcode/operand. Đây là trường hợp demo tối giản; với transformer chèn instructions, khác biệt có thể nằm ở `Code`, branch offsets, exception table, StackMapTable và descriptors.

### 6.3. Đối chiếu với file `.class` gốc

Đọc file do `javac` tạo:

~~~bash
javap -c -v out/app/demo/target/Greeter.class
~~~

Trong lab với **chỉ một transformer không có upstream modifications**, nội dung gốc và capture before dự kiến tương đương, vì callback nhận bytes class loader cung cấp. Nhưng trong một hệ thống có nhiều transformers:

- File `out/app/.../Greeter.class` là build artifact trên ổ đĩa.
- `Greeter-before.class` là **đầu vào callback của transformer này**.
- `Greeter-after.class` là **mảng transformer này trả về**.
- JVM-installed bytes có thể là kết quả của **những bước sau nữa**, hoặc JVM giữ thông tin tương đương nhưng bố trí classfile không byte-for-byte giống snapshot.

Không tự động lấy bất kỳ cặp nào trong bốn mục trên làm “giống nhau chắc chắn”.

### 6.4. Hash, file size và diff: bổ trợ chứ không thay `javap`

Trên Linux/macOS có tiện ích `sha256sum`:

~~~bash
sha256sum captures/run-001/Greeter-before.class captures/run-001/Greeter-after.class
~~~

Trên PowerShell:

~~~powershell
Get-FileHash captures/run-001/Greeter-before.class -Algorithm SHA256
Get-FileHash captures/run-001/Greeter-after.class -Algorithm SHA256
~~~

Chúng cho phép biết hai files **khác về bytes** và giữ tính toàn vẹn khi chuyển cho người khác. Hash **không nói thay đổi nằm ở đâu**; hãy dùng `javap` để hiểu constant pool và instructions.

Một diff text có thể hữu ích:

~~~bash
javap -c -v captures/run-001/Greeter-before.class > before.txt
javap -c -v captures/run-001/Greeter-after.class > after.txt
diff -u before.txt after.txt
~~~

Các lệnh trên tạo **file báo cáo do người chạy tự chọn**, không phải files agent tự tạo. `javap -v` còn in đường dẫn classfile, nên diff có thể chứa các dòng khác nhau chỉ do **tên file**. Cần tập trung vào constant pool/method code/attributes và giải thích những khác biệt phụ do đường dẫn, compiler hoặc version.

Trên PowerShell:

~~~powershell
javap -c -v captures/run-001/Greeter-before.class > before.txt
javap -c -v captures/run-001/Greeter-after.class > after.txt
Compare-Object (Get-Content before.txt) (Get-Content after.txt)
~~~

Nếu chương trình của bạn lưu nhiều output classfiles, thêm checksum và manifest metadata giúp giữ đúng quan hệ **input/output của cùng lượt transform**.

## 7. Đọc `javap` để chẩn đoán những lỗi bytecode thường gặp

Một số triệu chứng và vị trí cần soi:

| Triệu chứng | So sánh trong `javap -v -c -p` | Giả thuyết cần kiểm chứng |
|---|---|---|
| Hook không xuất hiện | `Code` của target method, `invokestatic`/`invokevirtual` gọi helper | Transformer filter nhầm class/method hoặc trả `null` |
| `NoClassDefFoundError` khi chạy | Class/method references, descriptors trong constant pool | Helper không visible ở target class loader/module |
| `NoSuchMethodError` | `Methodref`, owner, name, descriptor | Signature helper thực tế khác reference được chèn |
| `IllegalAccessError` | Owner/descriptor và module/package/class loader context | Quyền access khác điều transformer giả định |
| `VerifyError` | StackMapTable, branch offsets, stack/local use | Frame/bytecode writer sinh invalid code |
| `ClassFormatError` | Classfile header, constant pool, attributes | Bố cục classfile sai trước khi JVM verify |
| `UnsupportedClassVersionError` | `major version` ở classfile header | Writer target sai Java version |
| Exception handler mất tác dụng | `Exception table`, phạm vi `from/to/target` | Chèn instruction sai vùng try/catch/finally |
| Method có vẻ không đổi | Class name, method descriptor, class loader identity | Đang đọc bản `.class` khác hoặc cùng tên khác loader |
| Nhiều bản dump ghi đè | Tên file/sequence/phase metadata | Lỗi naming, nhiều callbacks |
| JVM chạy khác output snapshot | Danh sách transformers và thứ tự; retransform/redefine phase | Còn transformer sau, hoặc runtime chọn bytes khác |

**`javap` là disassembler, không phải formal verifier hoặc profiler.** Nó có thể đọc một classfile và in bytecode nhưng không chứng minh JVM sẽ chấp nhận mọi StackMapTable, module access hoặc dependency. Kết hợp load/run thật, test behavior, JVM exception và — khi phù hợp — bộ kiểm tra bytecode của thư viện viết classfiles.

### 7.1. Constant pool references và descriptors

Ví dụ output:

~~~text
#12 = Methodref          #3.#21   // demo/agent/Hook.enter:()V
#21 = NameAndType        #22:#23  // enter:()V
#22 = Utf8                         enter
#23 = Utf8                         ()V
...
  invokestatic #12                 // Method demo/agent/Hook.enter:()V
~~~

Đây là **mẫu minh họa**, không có trong Greeter demo. Cần xác minh tên owner và method descriptor đúng, helper được đúng loader/module của class đích nhìn thấy, và chữ ký method không khác kiểu return hay số tham số.

### 7.2. Exception tables, monitor và frames

Một transformer chèn logging trước/giữa `try/catch/finally` có thể phá thứ tự side effects hoặc bỏ sót exception path. Nếu instrument method `synchronized` hoặc có monitorenter/monitorexit, kiểm tra cân bằng và scope. `javap -v` có thể cho bạn thấy StackMapTable/exception table, nhưng cần JVM verifier và test runtime để xác nhận hợp lệ.

Nếu agent chỉ đo duration, hãy test cả normal return và exception, phương thức có nhiều return, constructor, static initializer, bridge methods và lambdas. Lưu output bytes của đúng method trước/sau giúp phân biệt “transform chưa chạy” với “transform sai semantics”.

### 7.3. Method đã load vẫn chạy bản cũ?

Nếu class đã load **trước khi** đăng ký transformer qua Attach, thêm transformer không tự replay classes đã load. `javap` trên file output riêng **không chứng minh** JVM đã redefine/retransform class đó. Với loaded classes phải xét `isRetransformClassesSupported`, `isModifiableClass` và `retransformClasses`/`redefineClasses` khi phù hợp, cùng giới hạn active stack frames.

Đây là lý do nên lưu metadata **phase** và xác minh behavior sau thao tác, không chỉ nhìn một `after.class` tồn tại trên disk.

## 8. Những giới hạn bảo mật và vận hành của lưu classfile bytes

### 8.1. Dữ liệu classfile có thể nhạy cảm

Một snapshot có thể chứa:

- Proprietary algorithms và tên class/method/field.
- String literals chứa URLs, headers, tokens, passwords nếu source vô tình hardcode.
- Debug symbols, method parameter names, source file names và line tables.
- Tên internal services, package layout và thông tin dependency.

Không nên tự động lưu toàn bộ classfiles vào `/tmp`, upload lên shared storage hoặc đính kèm incident ticket công khai. Chỉ lưu có consent/policy, trong directory có quyền hạn, thời hạn lưu trữ và cơ chế xóa an toàn phù hợp. Đừng coi file `.class` là “không nhạy cảm” chỉ vì không có source `.java`.

### 8.2. Chặn classpath và path traversal rủi ro

Demo nhận đường dẫn thư mục capture từ agent args của người chạy và dùng `Path.of(args).toAbsolutePath().normalize()`. Đây **không** phải một cơ chế sandbox. Trong sản phẩm:

- Chỉ cho phép ghi vào base directory đã cấu hình/quyền hạn rõ.
- Không dựng filesystem path trực tiếp từ `className`/module name do đầu vào không tin cậy mà không chuẩn hóa/kiểm tra.
- Cân nhắc symlink attacks, file permissions và mọi dạng overwrite.
- Dùng tên opaque/sequence để không lộ cấu trúc hệ thống.
- Giới hạn số files, tổng bytes, tuổi files và vị trí lưu.
- Không tải classfile bí mật tới môi trường phân tích ngoài tổ chức khi chưa được phép.

`CREATE_NEW` chống **ghi đè file đã tồn tại** theo semantics filesystem, nhưng không tự giải quyết mọi race/permission/symlink concern trong hệ thống lớn.

### 8.3. Synchronous I/O trong transformer

Callback có thể chạy ở đường class loading nhạy latency. Nếu `Files.write` chờ disk hoặc antivirus, class definition có thể chậm. Nếu callback gọi library chưa load, logging framework có thể gây recursive class loads. Khi nhiều threads cùng load classes, có nguy cơ contention và phản hồi dây chuyền.

Giải pháp production thường là:

~~~text
filter cực sớm
    |
clone input/returned bytes (bounded)
    |
enqueue snapshot vào bounded internal queue
    |
dedicated writer thread -> file/metadata/metrics
~~~

**Mẫu kiến trúc này không phải code độc lập.** Writer thread cần thiết kế lifecycle, flush, shutdown, overflow/drop counter và hệ thống logging an toàn. Nếu queue đầy, một agent observability thường chọn policy bỏ snapshot có đếm drop thay vì chặn vô hạn thread đang định nghĩa class. Nhưng nếu mục tiêu yêu cầu byte-for-byte capture bắt buộc, chính sách có thể khác và phải được công bố trước.

### 8.4. Cặp snapshot không nguyên tử và thứ tự callback

Hai lệnh `Files.write` riêng biệt không atomic theo cặp. Nếu ghi before thành công nhưng after lỗi, trên disk còn một snapshot lẻ. Một hệ thống đáng tin cần:

1. Ghi vào staging files riêng cho cùng request ID.
2. Flush/kiểm tra tính toàn vẹn, tạo checksum metadata.
3. Chuyển/đánh dấu bộ đôi hoàn tất khi cả hai đã thành công.
4. Không ném lỗi vô tình thay đổi kết quả class loading chỉ vì capture phụ trợ fail, trừ khi policy yêu cầu fail-fast.
5. Theo dõi partial failures và cleanup staging.

`AtomicBoolean` trong demo giới hạn **một callback** chụp; không cấp sequence ID cho hàng nghìn class definitions. Trong production cần một concurrent registry với quota và key được xây từ **class identity / phase / sequence**, tránh overwrite, mất kiểm soát disk và memory leak do giữ loaders.

## 9. Đối chiếu hiệu năng và correctness khi bật capture

Đo snapshot chỉ cho chẩn đoán nếu bạn có thể giải thích **tác dụng phụ của chính việc chụp**.

| Trục | Câu hỏi/metric cần có |
|---|---|
| Class loading latency | Callback có làm thời gian define/verify/link class tăng không? |
| Startup time | Tổng thời gian `premain` và nạp class trước main tăng bao nhiêu? |
| CPU | Parsing, hashing và copy bytes tốn bao nhiêu? |
| Memory | Tổng `byte[]` giữ trong queue bao nhiêu? Có chặn theo quota không? |
| Disk | Số files, tổng bytes, thời gian ghi, write failures |
| Functional correctness | Method vẫn trả kết quả/exception như mong đợi? |
| Transformation correctness | Output có đúng class name, version, method signatures, StackMapTable? |
| Coverage | Có đúng target classes? Có skip unexpected? |
| Security | Files/logs chứa dữ liệu nhạy cảm không? Retention policy phù hợp? |

Khi chẩn đoán một bug chỉ xảy ra dưới tải, bật capture có thể làm bug thay đổi timing; hãy so bản không capture/ít capture, dùng timestamps và logs có giới hạn. Không suy “không còn bug khi capture bật” thành “bug đã được sửa”.

### Một điểm dễ hiểu nhầm: CPU thấp chưa chắc capture rẻ

Nếu filesystem chậm, một thread có thể **block** trong I/O mà CPU utilization không cao, nhưng startup/classloading latency và p99 lại xấu. Vì vậy cần đo elapsed time và blocked time bên cạnh CPU. Nếu capture dùng bounded queue, đừng chỉ đo enqueue time mà bỏ qua write/dropped rate.

## 10. Trường hợp lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có file snapshot | Class name filter không khớp dấu `/`, class chưa load, loader/module/phase filter loại | Xác nhận internal name và target đã thực sự load |
| In `[agent] skip capture: expected literal not found` | Greeter đã đổi source, compiler dùng literal khác hoặc bytes upstream bị sửa | Dùng `javap -v` trên build artifact và xem exact UTF8 |
| In `classfile too large` | Vượt 1 MiB demo | Nâng quota có kiểm soát hoặc chọn class khác |
| In `FileAlreadyExistsException` | Dùng lại thư mục `run-001`, `CREATE_NEW` từ chối overwrite | Chọn directory mới, không xóa snapshot cũ vô tình |
| Có before nhưng thiếu after | Lỗi ghi file thứ hai | Xem stderr, filesystem, quyền; pair không hoàn chỉnh |
| Có after nhưng app vẫn in BEFORE | Đọc nhầm JVM/run, target không load, transformer sau ghi đè output hoặc file artifact khác | Xác minh runtime args, classloader, pipeline và behavior |
| App ném `VerifyError` | Output classfile/frames không hợp lệ | Phân tích `javap -v`, bytecode checker và lỗi verifier |
| `javap` hiện BEFORE ở “after” | Snapshot không phải bytes returned, file nhầm, patch không hoạt động | Kiểm tra file paths và code transform |
| `javap -classpath out/app demo.target.Greeter` vẫn hiện BEFORE | Đang đọc file gốc sau `javac` | Dùng đường dẫn tới `Greeter-after.class` |
| Mỗi lần chạy tạo file trùng tên | Thiếu run/phase/classloader/sequence metadata | Định danh mỗi callback, không overwrite |
| App vẫn đúng nhưng startup chậm | Synchronous filesystem I/O trong callback | Filter hẹp, quota, đo time, async writer bounded |
| Bytecode từ snapshot thiếu mọi biến đổi | Bạn đang chụp ở giữa pipeline, không phải cuối | Xác định thứ tự agent/transformer và phase |

Một bản dump chỉ có ích nếu bạn biết nó thuộc **callback nào**, **lớp nào**, **loader nào** và **thời điểm nào**. Nếu không lưu metadata, hai file classfile giống package có thể dẫn tới suy luận sai.

## 11. Ma trận kiểm thử thực hành

| Case | Điều chỉnh | Kỳ vọng |
|---|---|---|
| 1. Baseline | Chạy app không `-javaagent` | `[app] message=BEFORE` |
| 2. Demo chuẩn | Agent, thư mục mới, target Greeter đúng | Hai file, agent captured, app AFTER! |
| 3. Byte comparison | `javap -v -c` trên before/after | Constant pool literal khác, method `ldc` phù hợp |
| 4. Không ghi đè | Chạy lại cùng `run-001` | Ghi lỗi I/O; file cũ không bị overwrite |
| 5. Thư mục mới | Dùng `run-002` | Capture mới thành công |
| 6. Name filter | Đổi target name hoặc app không load Greeter | Không tạo file mới |
| 7. Loader filter | Load class cùng tên từ custom loader | Callback của loader không khớp không bị capture |
| 8. Phase filter | Chủ động retransform/redefine trong bài mở rộng | Demo không chụp lượt có `classBeingRedefined != null` |
| 9. Không có literal | Sửa Greeter trả `"CHANGED"`, build lại | Patch trả null, không capture pair, app trả source literal |
| 10. Output lỗi | Dùng transformer sinh invalid classfile ở test riêng | JVM có thể từ chối, `javap` không thay verifier |
| 11. Disk đầy/permission | Chỉ trong sandbox kiểm thử có kiểm soát | Capture báo lỗi, không khẳng định có files |
| 12. Multiple transformers | Đăng ký thêm transformer chạy trước/sau | before/after chỉ giới hạn một callback, phân tích pipeline |
| 13. Class lớn | Input dài hơn `MAX_BYTES` | Skip và báo lý do |
| 14. Bảo mật | Chụp class có string literal nhạy cảm trong môi trường giả lập | Quota, quyền truy cập, deletion và no upload ngoài chính sách |

**Không chạy fault injection “disk đầy” trên máy phát triển hay production thật**: dùng sandbox/quota kiểm soát, tránh ảnh hưởng hệ thống và các ứng dụng khác.

## 12. Checklist chẩn đoán trước–sau

### Trước khi bật snapshot

- [ ] Đã xác định **một class/internal name** hoặc allowlist nhỏ có chủ đích?
- [ ] Đã xác định defining class loader và module/phase?
- [ ] Có ngân sách số lần chụp, số bytes, số files, lifetime?
- [ ] Có thư mục riêng, quyền truy cập, không ghi đè và chính sách dọn dữ liệu?
- [ ] Biết rõ snapshot có thể chứa proprietary code, debug symbols và string literals?
- [ ] Biết agent/transformers nào tham gia pipeline, hoặc có kế hoạch tìm hiểu?
- [ ] Biết lỗi cần chứng minh: hook thiếu, VerifyError, linkage error, hay behavior sai?
- [ ] Có test baseline và công cụ đo overhead?

### Khi chụp

- [ ] Filter metadata **trước khi** parse/copy/ghi bytes?
- [ ] Không mutate `classfileBuffer` in-place?
- [ ] Có xử lý `null` output rõ ràng, không tạo nhãn transformed sai?
- [ ] Input và returned bytes có dùng cùng run ID/phase/class identity?
- [ ] Ghi raw bytes, không dùng `String` conversion?
- [ ] Có kiểm soát concurrent callbacks và tránh recursive class loading?
- [ ] Có log skip/I/O failures nhưng không làm lộ thông tin nhạy cảm?
- [ ] Nếu chụp qua queue, có đo dropped/queued/written counts?
- [ ] Có giới hạn synch I/O trong transformer callback?

### Khi dùng `javap`

- [ ] Đọc **đúng đường dẫn file snapshot**, không chỉ `-classpath` trỏ tới build output?
- [ ] Dùng `-v` để đọc constant pool, version, attributes/StackMapTable?
- [ ] Dùng `-c` xem instructions/branch targets, exception table?
- [ ] Dùng `-p` nếu cần private methods/constructors?
- [ ] Phân biệt output snapshot với bytes cuối JVM thực thi?
- [ ] Hash chỉ xác nhận khác bytes, không xác nhận hợp lệ?
- [ ] Đã chạy JVM/test behavior và đọc error đầu tiên?
- [ ] Có ghi nhận scope/limitations của kết luận?

### Sau khi chẩn đoán

- [ ] Không để capture bật vô hạn và không lưu file quá hạn?
- [ ] Không copy snapshot chứa bí mật lên ticket/bucket không có quyền?
- [ ] Có kết luận chính xác: transformer lọc sai, output không hợp lệ, helper invisible hay downstream rewrite?
- [ ] Có thể tái hiện từ source/agent/build/configuration đã xác định?
- [ ] Nếu bug biến mất khi chụp, đã xét measurement overhead/race timing?

## 13. Câu hỏi ôn tập

**1.** Tại sao file before trong callback transformer B không luôn giống file `.class` gốc?

> Vì trước B có thể có transformer A đã sửa bytes. `classfileBuffer` của B là đầu vào **ở vị trí B trong pipeline**.

**2.** File after của B có chắc là bytes cuối cùng JVM cài đặt không?

> Không. Transformer C có thể chạy sau B, JVM còn verify/link và có những chi tiết representation do VM quản lý. File chỉ chứng minh bytes mà B trả về.

**3.** Vì sao phải lọc `className` trước khi đọc/ghi file?

> Để giảm overhead, disk usage, rủi ro nhầm mục tiêu và nguy cơ chụp dữ liệu nhạy cảm của class không liên quan.

**4.** Trong callback, tên class `demo.target.Greeter` xuất hiện dạng nào?

> Internal name `demo/target/Greeter`, dùng dấu `/`, không phải dấu chấm.

**5.** `classBeingRedefined != null` gợi ý điều gì?

> Callback đang xử lý class đã tồn tại trong một lượt redefine/retransform, không phải initial load theo filter demo.

**6.** `Files.writeString(path, new String(bytes))` có phải cách lưu `.class` đúng không?

> Không. Classfile bytes là nhị phân, chuyển qua text encoding có thể làm sai dữ liệu. Dùng `Files.write(path, bytes, ...)`.

**7.** Vì sao `javap -classpath out/app demo.target.Greeter` vẫn in BEFORE khi chạy agent thành công?

> Nó đọc build artifact ở `out/app`, không đọc snapshot `Greeter-after.class`. Cần truyền đường dẫn tới đúng file after.

**8.** `javap -c` và `javap -v` khác nhau thế nào?

> `-c` hiển thị instructions, `-v` thêm constant pool, attributes, version và metadata. Dùng cả hai để đối chiếu rộng hơn.

**9.** Khi after file có method reference tới helper nhưng app ném `NoClassDefFoundError`, nên xem gì?

> Loader/module visibility, method/class owner, descriptors, thời điểm helper xuất hiện, pipeline và first linkage failure — không chỉ xem bytes.

**10.** Nếu `transform` trả `null` thì đã biến đổi bytecode thành công chưa?

> Không ở bước đó; `null` nghĩa là transformer không cung cấp bytes thay thế.

**11.** Trong demo, vì sao `"BEFORE"` có thể đổi thành `"AFTER!"` mà không cần sửa branch offsets?

> Hai literal đều dài sáu byte ASCII trong constant pool; output giữ classfile length và structure, chỉ thay UTF8 value được `ldc` tham chiếu.

**12.** Tại sao không dùng parser constant pool demo cho ứng dụng production?

> Nó là demo hẹp, không hỗ trợ mọi classfile/version/case và không kiểm tra mọi verifier constraints; hãy dùng thư viện bytecode phù hợp và kiểm thử.

**13.** `CREATE_NEW` có đảm bảo cặp snapshot before/after được ghi nguyên tử không?

> Không. Hai lời gọi ghi riêng có thể thành công/thất bại khác nhau. Production cần staging/metadata/commit protocol và cleanup.

**14.** Nếu class có cùng tên nhưng do hai defining loaders nạp, có thể cùng dùng tên file snapshot không?

> Không nên. Class identity gắn với defining loader; cần loader/phase/sequence metadata và cơ chế tránh collision.

**15.** Đã có input/output snapshot và kết quả `javap` hợp lý, có chắc runtime đúng hoàn toàn không?

> Chưa. Cần JVM verify/link thành công, test return/exception/side effects, kiểm tra helpers, modules và các transformers khác.

## 14. Tài liệu chính thức

- Java SE 17, `ClassFileTransformer` — callbacks load/redefine/retransform, order, buffer/return contract, `null` và exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `Instrumentation` — `addTransformer`, `retransformClasses`, `redefineClasses`, runtime capability: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `java.lang.instrument` package — startup agent và manifest `Premain-Class`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `javap` tool — `-c`, `-v`, `-p`, file path và classpath flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Java SE 17, Java Virtual Machine Specification, Chapter 4 — classfile structure, constant pool, Code/StackMapTable attributes: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17, `Files` — `write(Path, byte[], OpenOption...)` và atomicity limitations: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17, `StandardOpenOption.CREATE_NEW` — file creation với kiểm tra tồn tại: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
