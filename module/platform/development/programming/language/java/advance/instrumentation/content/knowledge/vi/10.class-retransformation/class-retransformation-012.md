# Retransform nhiều lớp như một tập: thành công đồng bộ hoặc không lớp nào được cài khi yêu cầu thất bại

Trong Java Instrumentation, **Instrumentation.retransformClasses(Class<?>... classes)** không chỉ nhận một lớp. API cho phép truyền **một tập nhiều lớp trong cùng một lời gọi** để JVM xử lý những thay đổi có quan hệ phụ thuộc, ví dụ agent cần instrument cả **Service** và **Repository** với cùng phiên bản logic. Điểm quan trọng nhất của hợp đồng Java 17 là:

> **Nếu lời gọi retransformClasses ném exception thì không lớp nào trong tập yêu cầu đã được retransform bởi lời gọi ấy.**

Vì vậy, hai thao tác **retransformClasses(A.class, B.class)** trong *một lời gọi* và **retransformClasses(A.class)** rồi **retransformClasses(B.class)** trong *hai lời gọi* có ngữ nghĩa thất bại khác nhau. Với một lời gọi, JVM cung cấp bảo đảm **all-or-none đối với việc cài class definitions của tập**. Với hai lời gọi tách biệt, A có thể đã được cập nhật thành công rồi B thất bại, và API không tự hoàn tác A.

Bài học tập trung vào **cách chọn, chuẩn bị, thực thi và xác minh một tập lớp**, điều xảy ra khi một lớp trong tập có bytecode không hợp lệ hoặc không sửa được, cùng những **giới hạn của tính nguyên tử**: trạng thái ứng dụng, log/metric, side effect của callback, thread đang chạy và những batch trước đó **không phải** phần được rollback tự động.

## 1. Những kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **một lời gọi nhiều lớp** với **nhiều lời gọi một lớp**.
2. Hiểu chính xác câu bảo đảm: **một lời gọi thất bại ⇒ không class definition nào của tập được cài bởi lời gọi đó**.
3. Kiểm tra **isRetransformClassesSupported()**, **isModifiableClass(...)** và nhận diện **đúng Class object**, không chỉ tên lớp.
4. Đăng ký **ClassFileTransformer** thích hợp với **canRetransform=true**, đồng thời hiểu kết quả của transformer **canRetransform=false** được JVM tái áp dụng mà không gọi lại callback.
5. Xử lý lỗi hợp lệ: **UnmodifiableClassException**, **UnsupportedOperationException**, **ClassFormatError**, **LinkageError** và những lỗi được API liệt kê.
6. Không nhầm việc một callback đã chạy với việc lớp ấy **đã được JVM cài**.
7. Viết thử nghiệm Java 17 dùng một batch hai lớp: một lượt thành công, một lượt cố ý tạo bytecode lỗi, và một lượt chứa array class không modifiable.
8. Thiết kế thông báo và quy trình retry an toàn, tránh tự tạo trạng thái “nửa mới nửa cũ” do chia batch sai.

## 2. Hình dung một yêu cầu nhiều lớp

Giả sử ứng dụng có hai lớp đã load:

~~~text
Class A: com.example.Service
Class B: com.example.Repository
~~~

Agent cần sửa cả hai trong cùng một phiên bản instrumentation. Với một lời gọi:

~~~java
// Đoạn minh họa trong mã agent đã có Instrumentation inst.
inst.retransformClasses(Service.class, Repository.class);
~~~

Về mặt khái niệm, JVM xử lý:

~~~text
retransformClasses(A, B)
          │
          ▼
  chuẩn bị class bytes của A và B
          │
          ▼
  áp dụng chuỗi transformer cho A và B
          │
          ▼
  kiểm tra định dạng, tính hợp lệ và giới hạn class changes
          │
          ├── bất kỳ lớp nào lỗi
          │           │
          │           ▼
          │     throw exception
          │     KHÔNG cài definition mới cho A hoặc B
          │
          └── tất cả được chấp nhận
                      │
                      ▼
              cài các định nghĩa mới của tập
              lời gọi trở về bình thường
~~~

Sơ đồ mô tả **bảo đảm ở ranh giới API**, không ấn định JVM phải gọi transformer của từng lớp theo trình tự nào hoặc tất cả callback đều phải được gọi khi lỗi được phát hiện sớm. Bảo đảm thực tế cần nhớ là: khi **lời gọi ném exception**, không phần tử nào của tập được retransform thành công bởi lời gọi ấy.

### 2.1. So sánh với hai lời gọi riêng lẻ

~~~java
// Cách 1: một yêu cầu nhiều lớp.
inst.retransformClasses(A.class, B.class);

// Cách 2: hai yêu cầu độc lập.
inst.retransformClasses(A.class);
inst.retransformClasses(B.class);
~~~

| Tình huống | Một lời gọi A+B | Hai lời gọi A rồi B |
| --- | --- | --- |
| Cả A và B hợp lệ | Cả hai được xử lý trong cùng một yêu cầu | Hai yêu cầu độc lập đều có thể thành công |
| B thất bại trước khi cài | **A và B không được cài từ batch thất bại** | A có thể đã thành công và vẫn giữ definition mới |
| Muốn A/B cập nhật cùng phiên bản | Phù hợp hơn khi hai class phụ thuộc lẫn nhau | Cần cơ chế phối hợp/rollback riêng |
| Retry sau thất bại | Có thể sửa nguyên nhân rồi thử lại cùng tập | Phải phân biệt lớp nào đã cập nhật ở các lời gọi trước |
| Lỗi ở lớp không modifiable | Yêu cầu thất bại và không cài lớp nào | Nếu phát hiện ở lượt B, lượt A trước đó không tự bị hoàn tác |

**Không gọi hai lời gọi liên tiếp là một transaction.** API không cung cấp cơ chế commit/rollback chung cho hai lời gọi riêng biệt.

## 3. Chuỗi biến đổi áp dụng lên từng phần tử trong tập

**retransformClasses** chạy lại quá trình transformation từ bytes nền của mỗi lớp theo cơ chế Instrumentation. Với Java 17:

- **Transformer đăng ký với canRetransform=false**: không được gọi lại trong retransformation; JVM tự động **tái áp dụng kết quả đã lưu** từ lần class load/redefine trước, tương đương áp kết quả cũ mà không gọi callback.
- **Transformer đăng ký với canRetransform=true**: có thể được JVM gọi lại cho các lớp trong tập đang retransform.
- **Mỗi transformer** phải giữ input buffer bất biến, **return null** nếu không sửa và **return byte[] mới** nếu cung cấp class file thay thế.
- **Bytes nền khi retransform** không nhất thiết giống byte-for-byte với class file trên đĩa/lúc định nghĩa ban đầu: constant pool/attributes có thể được biểu diễn khác.
- **Kết quả cuối** phải là một định nghĩa class hợp lệ và nằm trong giới hạn thay đổi mà JVM hỗ trợ đối với lớp đã load.

~~~text
Initial bytes của A ── các kết quả không-retransform A ── các transformer có-retransform A ── A'
Initial bytes của B ── các kết quả không-retransform B ── các transformer có-retransform B ── B'
                                                                                       │
                                                                                kiểm tra tập
                                                                                       │
                                                                          chấp nhận hoặc thất bại
~~~

Trong ví dụ, A' và B' là **định nghĩa đề xuất**, không nhất thiết đã được cài ngay khi transformer trả về bytes. Một callback đã in log **A_REPLACEMENT_READY** chỉ chứng minh có một kết quả biến đổi cho A; nếu B có bytecode sai và cả lời gọi thất bại, A' **không được commit**.

### 3.1. Thứ tự các lớp trong varargs không phải cam kết thứ tự callback

~~~java
inst.retransformClasses(B.class, A.class);
~~~

Chương trình nên đối xử với đây như một **tập mục tiêu**, không dựa vào giả định “callback của B luôn chạy trước A” hoặc “đã thấy log của A thì A đã cài”. Lý do chính của API hỗ trợ nhiều lớp là cho phép các thay đổi **liên quan nhau** được xử lý trong cùng một yêu cầu. Một JVM có thể kiểm tra lỗi ở nhiều giai đoạn; mức độ callback đã chạy trước lỗi không phải là chỉ số commit.

Đồng thời, thứ tự các **transformer đối với một class** tuân theo các nhóm **ClassFileTransformer** và thứ tự đăng ký trong nhóm; đó là vấn đề **khác** với thứ tự các phần tử A, B trong tham số varargs.

### 3.2. Không phải batch nào cũng thật sự thay đổi bytecode

Nếu mọi transformer trả **null** hoặc kết quả tương đương bytes cũ, **retransformClasses(A,B)** có thể trở về bình thường nhưng hành vi của A/B không đổi. “Batch hoàn thành” không đồng nghĩa “đúng tính năng mới đã có hiệu lực”.

Để báo **instrumentation thành công theo nghiệp vụ**, cần xác minh thêm:

- Có đúng lớp cần sửa (binary name, defining loader, module).
- Transformer đã thực sự cung cấp class file mới đúng yêu cầu.
- JVM không từ chối và lời gọi trả về bình thường.
- Một lời gọi method **mới** dùng hành vi mong đợi sau retransform.

## 4. Điều kiện trước khi retransform nhiều lớp

### 4.1. Capability của JVM và manifest của agent

Khả năng retransform là **tùy chọn** của JVM và cấu hình agent. Với startup agent, manifest cần yêu cầu:

~~~text
Manifest-Version: 1.0
Premain-Class: BatchAgent
Can-Retransform-Classes: true
~~~

Giá trị mặc định của **Can-Retransform-Classes** là **false** nếu không khai báo. Dù manifest ghi **true**, JVM vẫn phải hỗ trợ; hãy kiểm tra **inst.isRetransformClassesSupported()** trước khi gọi **addTransformer(transformer, true)** và **retransformClasses(...)**.

Nếu agent chỉ có thể làm việc khi capability này hiện diện, fail fast trong khởi động là hợp lý. Nếu tính năng chỉ là tùy chọn, có thể báo **UNSUPPORTED** và không cài transformer hỗ trợ retransform; không tuyên bố đã cập nhật lớp.

### 4.2. Tính modifiable của từng lớp

~~~java
// Đoạn minh họa trong một service có Instrumentation inst.
for (Class<?> type : targets) {
    if (!inst.isModifiableClass(type)) {
        throw new IllegalArgumentException(
                "Class not modifiable: " + type.getName());
    }
}
inst.retransformClasses(targets);
~~~

**isModifiableClass(Class)** là điều kiện cần để một lớp được retransform, nhưng **không đủ**: capability còn phải có, transformer phải tạo bytes hợp lệ, class schema không được sửa theo cách JVM không hỗ trợ, và các phụ thuộc liên kết phải đúng.

**Primitive classes và array classes không modifiable** theo Javadoc. Ví dụ, **int.class** và **int[].class** không thể đưa vào batch để mong JVM đổi bytecode. Cần giữ danh sách là **Class<?>[] thật**, không dùng danh sách tên string để thay thế class identity.

### 4.3. Chọn đúng Class object

Hai class cùng tên **com.acme.Service** do hai defining class loader khác nhau định nghĩa là **hai kiểu runtime khác nhau**. Lấy nhầm **Class** có thể cập nhật không đúng ứng dụng/plugin. Để lập tập:

1. Dùng **inst.getAllLoadedClasses()** hoặc nguồn class identity tin cậy khi phải tìm lớp đã load.
2. Lọc binary name.
3. Kiểm tra **defining class loader**, module và phiên bản/module layer nếu cần.
4. Kiểm tra **isModifiableClass** từng phần tử.
5. Chỉ đưa đúng tập xác định vào một lời gọi.

Không tự gọi **Class.forName** cho một lớp chưa load chỉ để “cho có target”: việc đó có thể làm thay đổi thời điểm class loading, kích hoạt initialization nếu dùng overload mặc định, hoặc đưa một bản class sai loader vào tập.

### 4.4. Dữ liệu null, mảng rỗng và lỗi trước khi xử lý

Javadoc Java 17 quy định:

- **retransformClasses()** với **mảng phần tử rỗng** là hợp lệ và **không làm gì**.
- Tham số **classes == null** hoặc có **phần tử null** gây **NullPointerException**.
- Có lớp không modifiable: **UnmodifiableClassException**.
- JVM/agent không hỗ trợ retransform hoặc thay đổi cấu trúc không được phép: **UnsupportedOperationException**.
- Class bytes không hợp lệ/vi phạm ràng buộc: các loại **ClassFormatError**, **UnsupportedClassVersionError**, **NoClassDefFoundError**, **ClassCircularityError**, **LinkageError** tùy nguyên nhân.

Trong hệ thống thật nên preflight càng nhiều càng tốt, rồi **vẫn phải xử lý exception từ lời gọi thực**. Preflight không loại bỏ race với agent khác, class loader hoặc việc transformer phát sinh lỗi trong thời điểm cập nhật.

## 5. Bài thực hành Java 17: một batch gồm Alpha và Beta

Chúng ta xây một chương trình Java 17 độc lập với thư viện ngoài, gồm:

- **BatchApp$Alpha.value()** ban đầu trả **ALPHA0**.
- **BatchApp$Beta.value()** ban đầu trả **BETA_0**.
- **BatchAgent** được JVM nạp khi khởi động bằng **-javaagent**, cất handle **Instrumentation** và đăng ký một transformer **canRetransform=true**.
- **BatchTransformer** chỉ thay chuỗi trong classfileBuffer khi class đang **retransform**, không sửa ở lần class load đầu tiên.
- Lệnh **success** cập nhật hai literal thành **ALPHA1** và **BETA_1** trong một lời gọi.
- Lệnh **failure** cố ý trả về bytes class file **không hợp lệ cho Beta**, để kiểm tra bảo đảm không cài A lẫn B.
- Lệnh **reject-array** đưa thêm **int[].class** (unmodifiable) vào tập để kiểm tra lỗi trước/hoặc trong xử lý mà không có cập nhật dở dang.

Phương pháp biến đổi dùng một helper đọc **CONSTANT_Utf8** trong constant pool class file. Nó chỉ thay **6 byte ASCII bằng 6 byte ASCII**, đủ cho các class demo do **javac --release 17** tạo và **không phải** thư viện bytecode tổng quát. Trong hệ thống thật nên dùng ASM/Byte Buddy hoặc công cụ class file có verifier phù hợp.

### 5.1. File BatchApp.java

~~~java
// File: BatchApp.java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class BatchApp {

    static final class Alpha {
        static String value() {
            return "ALPHA0";
        }
    }

    static final class Beta {
        static String value() {
            return "BETA_0";
        }
    }

    private static String snapshot() {
        return Alpha.value() + "|" + Beta.value();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                (!"success".equals(args[0])
                 && !"failure".equals(args[0])
                 && !"reject-array".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: BatchApp success|failure|reject-array");
        }

        String mode = args[0];
        Instrumentation inst = AgentState.required();

        // snapshot() gọi cả hai method và bảo đảm hai class
        // đã được tải trước lời gọi retransformClasses.
        String before = snapshot();
        System.out.println("BEFORE=" + before);

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "Retransform capability is not available");
        }

        if (!inst.isModifiableClass(Alpha.class)
                || !inst.isModifiableClass(Beta.class)) {
            throw new IllegalStateException(
                    "The demo classes must be modifiable");
        }

        AgentState.mode = mode;

        Class<?>[] batch = "reject-array".equals(mode)
                ? new Class<?>[] {
                        Alpha.class, int[].class, Beta.class
                  }
                : new Class<?>[] {
                        Alpha.class, Beta.class
                  };

        boolean failed = false;
        try {
            // CHỈ MỘT LỜI GỌI cho cả tập.
            inst.retransformClasses(batch);
            System.out.println("BATCH_OK");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException
                 | LinkageError error) {
            failed = true;
            System.out.println("BATCH_FAILED");
        }

        String after = snapshot();
        System.out.println("AFTER=" + after);

        if ("success".equals(mode)) {
            if (failed || !"ALPHA1|BETA_1".equals(after)) {
                throw new AssertionError(
                        "Expected both new definitions");
            }
        } else {
            if (!failed || !before.equals(after)) {
                throw new AssertionError(
                        "Failed batch must install neither class");
            }
        }
    }
}
~~~

Tại sao **before** phải gọi cả hai method? Vì mục tiêu của **retransformClasses** là **những Class object đã được JVM load**. Trong chương trình này, **snapshot()** chủ động làm cả hai lớp được định nghĩa và chạy ở trạng thái gốc trước khi yêu cầu retransform được gửi.

**AgentState.required()** sẽ ném exception rõ ràng khi ứng dụng chạy không có agent, tránh tạo một “thành công” giả. Tùy chế độ, chương trình ghi **BATCH_OK** hoặc **BATCH_FAILED** và kiểm chứng kết quả cuối. Việc không in tên exception giúp transcript dễ tái lập; trong công cụ thật, nên ghi **class, message và stack trace** của exception vào log chẩn đoán.

**Lưu ý về catch:** Ở đây **LinkageError** bao gồm những lỗi class format/liên kết từ JVM trong bài test. Ví dụ chỉ bắt những failure classes có liên quan; không bắt và nuốt mọi **Throwable** như một chính sách production. **AssertionError** của phép kiểm tra cuối cùng được để nổi lên để thử nghiệm thất bại thật nếu kết quả không đáp ứng yêu cầu.

### 5.2. File BatchAgent.java

~~~java
// File: BatchAgent.java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class BatchAgent {
    private BatchAgent() {
    }

    public static void premain(String options, Instrumentation inst) {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This agent requires retransformation support");
        }
        AgentState.install(inst);
        inst.addTransformer(new BatchTransformer(), true);
    }
}

final class AgentState {
    private static volatile Instrumentation instrumentation;
    static volatile String mode = "off";

    private AgentState() {
    }

    static void install(Instrumentation inst) {
        if (inst == null) {
            throw new NullPointerException("Instrumentation missing");
        }
        if (instrumentation != null) {
            throw new IllegalStateException("Agent already installed");
        }
        instrumentation = inst;
    }

    static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException("Run with -javaagent");
        }
        return current;
    }
}

final class BatchTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        // Bỏ qua class load ban đầu: chỉ biến đổi khi retransform.
        if (classBeingRedefined == null) {
            return null;
        }

        if ("BatchApp$Alpha".equals(className)) {
            return replaceUtf8(
                    classfileBuffer, "ALPHA0", "ALPHA1");
        }

        if ("BatchApp$Beta".equals(className)) {
            if ("failure".equals(AgentState.mode)) {
                // Cố ý không phải class file hợp lệ.
                // Đây là phép thử FAIL của cả batch.
                return new byte[] {0, 1, 2};
            }
            return replaceUtf8(
                    classfileBuffer, "BETA_0", "BETA_1");
        }

        return null;
    }

    private static byte[] replaceUtf8(
            byte[] original, String oldValue, String newValue) {

        byte[] before = oldValue.getBytes(StandardCharsets.US_ASCII);
        byte[] after = newValue.getBytes(StandardCharsets.US_ASCII);

        if (before.length != after.length
                || original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            return null;
        }

        int poolCount = u2(original, 8);
        int p = 10;

        for (int i = 1; i < poolCount; i++) {
            int tag = original[p++] & 0xff;
            switch (tag) {
                case 1 -> {
                    // CONSTANT_Utf8_info.
                    int len = u2(original, p);
                    p += 2;

                    if (len == before.length
                            && matches(original, p, before)) {
                        byte[] result = original.clone();
                        System.arraycopy(
                                after, 0, result, p, after.length);
                        return result;
                    }

                    p += len;
                }

                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> {
                    // CONSTANT_Long / CONSTANT_Double
                    // chiếm hai entry trong constant pool.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant-pool tag " + tag);
            }
        }

        return null;
    }

    private static int u2(byte[] bytes, int index) {
        return ((bytes[index] & 0xff) << 8)
                | (bytes[index + 1] & 0xff);
    }

    private static boolean matches(
            byte[] bytes, int position, byte[] expected) {
        if (position + expected.length > bytes.length) {
            return false;
        }
        for (int i = 0; i < expected.length; i++) {
            if (bytes[position + i] != expected[i]) {
                return false;
            }
        }
        return true;
    }
}
~~~

Phân tích kỹ:

1. **premain(String, Instrumentation)** là entry point startup agent. JVM trực tiếp cấp **Instrumentation**, không tự tạo new interface implementation.
2. Agent kiểm tra **isRetransformClassesSupported()** trước khi đăng ký transformer **canRetransform=true**. Manifest của ví dụ cũng phải yêu cầu capability đó.
3. **AgentState** giữ handle và mode cho cùng một JVM. Lệnh trong **main** đặt **mode** trước khi gọi retransform. **volatile** giúp một callback trên luồng khác đọc được cấu hình mới, nhưng không làm toàn bộ dữ liệu agent trở thành thread-safe.
4. **classBeingRedefined == null** ở class load đầu tiên: transformer **return null**. Do đó hai lớp Alpha/Beta ban đầu thực thi đúng literal gốc.
5. Trong batch, **Alpha** có thể trả bytes thay thế chứa **ALPHA1**, **Beta** có thể trả bytes chứa **BETA_1** hoặc một mảng không có định dạng class file khi mode là **failure**.
6. **replaceUtf8** tạo một **mảng mới** từ input, chỉ thay chuỗi ASCII cùng độ dài. Nó không sửa **classfileBuffer** trực tiếp.
7. **return new byte[] {0,1,2}** dành riêng cho phép thử lỗi. Nó khiến JVM từ chối kết quả class file của Beta, và **không được dùng trong agent thật**. Nó không tương đương **return null**: **null** có nghĩa không sửa, còn mảng invalid là một bản thay thế không được chấp nhận.
8. Agent không cố tình ném exception trong transformer để gây lỗi batch. Theo hợp đồng, exception phát sinh từ callback **ClassFileTransformer** có thể được xử lý như không cung cấp thay đổi và JVM tiếp tục các transformer khác; vì vậy **trả bytes sai** là một phép thử dễ quan sát hơn cho lỗi validate/cài định nghĩa.

**Giới hạn helper:** Bộ đọc constant pool trên chỉ viết cho class demo hợp lệ, không có parser đầy đủ, không xử lý mọi trường hợp Modified UTF-8, không có kiểm tra bounds chặt chẽ cho input độc hại và không sửa method body phức tạp. Đừng áp dụng vào class thật. Sử dụng thư viện ASM, Byte Buddy hoặc class-file toolkit phù hợp khi cần instrument bytecode tổng quát.

### 5.3. File agent.mf

Tạo file văn bản **agent.mf** với một ký tự newline ở cuối:

~~~text
Manifest-Version: 1.0
Premain-Class: BatchAgent
Can-Retransform-Classes: true
~~~

**Can-Retransform-Classes: true** là yêu cầu capability, không phải lời hứa mọi JVM đều hỗ trợ. Nếu chạy dynamic attach thay vì startup agent, cần dùng manifest **Agent-Class** và callback **agentmain** thích hợp; đó không phải cơ chế của demo này.

### 5.4. Biên dịch và đóng gói

Đặt ba file **BatchApp.java**, **BatchAgent.java**, **agent.mf** trong cùng thư mục. Trên JDK 17:

~~~bash
javac --release 17 BatchApp.java BatchAgent.java
jar cfm batch-agent.jar agent.mf \
    BatchAgent.class AgentState.class BatchTransformer.class
~~~

Lệnh **jar** trên được nối bằng **backslash** theo cú pháp shell POSIX. Nếu dùng Windows cmd.exe/PowerShell, đặt lệnh jar trên **một dòng**:

~~~text
jar cfm batch-agent.jar agent.mf BatchAgent.class AgentState.class BatchTransformer.class
~~~

Sau khi đóng gói, file **BatchApp.class**, **BatchApp$Alpha.class**, **BatchApp$Beta.class** nằm trên classpath ứng dụng (thư mục hiện tại). JAR agent cần ba class **BatchAgent, AgentState, BatchTransformer** và manifest. Trong demo không có package, giúp tên class và lệnh jar đơn giản; sản phẩm thật nên dùng namespace/package rõ ràng.

Kiểm tra JAR agent:

~~~bash
jar tf batch-agent.jar
~~~

Danh sách cần có **META-INF/MANIFEST.MF** cùng ba class agent. Nếu thiếu **AgentState.class**, JVM có thể không load đúng agent ngay lúc khởi động.

### 5.5. Trường hợp cả hai lớp đều hợp lệ: success

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp success
~~~

Output kỳ vọng trên HotSpot Java 17 có retransform capability:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_OK
AFTER=ALPHA1|BETA_1
~~~

Diễn giải:

- **BEFORE** được tính từ method gốc, đồng thời bảo đảm hai lớp đã được load.
- Agent ở mode **success** trả bytes khác cho cả Alpha và Beta.
- **retransformClasses(Alpha.class, Beta.class)** hoàn thành bình thường, tức JVM đã xử lý batch không ném lỗi.
- **AFTER** được tính bằng invocation mới và quan sát cả hai giá trị mới.

Nếu output có **BATCH_OK** nhưng **AFTER** vẫn như trước, điều đó có thể là phép transform không tạo thay đổi; assertion của ví dụ sẽ phát hiện và fail. API hoàn thành không phải bằng chứng duy nhất cho nghiệp vụ.

### 5.6. Một lớp lỗi định dạng: failure

Chạy ở **một tiến trình JVM mới** để bắt đầu từ baseline sạch:

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp failure
~~~

Output kỳ vọng:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_FAILED
AFTER=ALPHA0|BETA_0
~~~

Trong mode **failure**, transformer cho Alpha vẫn có thể đã tạo bytes hợp lệ chứa ALPHA1. Transformer cho Beta trả mảng **{0,1,2}**, không phải class file có magic **CAFEBABE**. JVM phải từ chối bản định nghĩa lỗi, lời gọi retransform ném lỗi class-format/liên kết (trong mã demo được bắt qua **LinkageError**).

Theo hợp đồng **retransformClasses**, **không lớp nào của batch được retransform thành công** nếu lời gọi ném exception. Vì vậy **AFTER** vẫn là **ALPHA0|BETA_0**. Việc Alpha **có thể đã qua callback** hoặc một byte[] mới **đã được tạo** không đồng nghĩa Alpha được cài.

**Không suy diễn** JVM bắt buộc gọi callback Alpha trước callback Beta, hoặc phải gọi mọi transformer trước khi phát hiện lỗi. Chúng ta dựa vào **kết quả được bảo đảm bởi API**, không dựa vào thứ tự in log.

### 5.7. Một lớp không modifiable: reject-array

Chạy ở JVM mới:

~~~bash
java -javaagent:batch-agent.jar -cp . BatchApp reject-array
~~~

Output kỳ vọng:

~~~text
BEFORE=ALPHA0|BETA_0
BATCH_FAILED
AFTER=ALPHA0|BETA_0
~~~

Ở mode này, mảng mục tiêu là:

~~~java
// Đoạn minh họa từ BatchApp, không phải file Java độc lập.
new Class<?>[] {
    BatchApp.Alpha.class, int[].class, BatchApp.Beta.class
}
~~~

**int[].class** là array class; theo Javadoc, array classes **không modifiable**. Lời gọi có thể ném **UnmodifiableClassException**. Bởi vì **một lời gọi xử lý cả tập**, Alpha và Beta vẫn nguyên định nghĩa trước yêu cầu thất bại.

**Điểm học quan trọng:** Với array class, hệ thống hoàn toàn có thể phát hiện **isModifiableClass(int[].class) == false** ở preflight và không gửi yêu cầu. Bài test cố tình gửi để chứng minh hành vi failure của API; không khuyến khích làm vậy trong production.

### 5.8. Nếu quên -javaagent thì sao?

~~~bash
java -cp . BatchApp success
~~~

Ứng dụng sẽ thất bại có chủ đích ở **AgentState.required()**, bởi chưa có **Instrumentation** do JVM truyền cho agent. Không có một API Java SE nào cho ứng dụng bình thường tự lấy Instrumentation như biến static toàn cục nếu không có cơ chế agent phù hợp.

## 6. Bảo đảm all-or-none chính xác đến đâu?

Cần tách rõ **lớp được cài** khỏi **mọi sự kiện xảy ra trong khi chuẩn bị**.

### 6.1. Những gì được bảo đảm nếu lời gọi ném exception

Theo Java 17 Instrumentation API:

**Nếu retransformClasses(...) ném exception thì không lớp nào trong tham số của lời gọi đó đã được retransform bởi lời gọi ấy.**

Điều này đủ để tránh trạng thái “A đã mang code mới của batch N, B chưa mang code mới vì batch N thất bại” **do chính batch N**. Chính vì vậy API hỗ trợ một tập lớp, để tạo những cập nhật liên quan lẫn nhau cùng lúc.

Nếu từng lớp đã từng được retransform thành công ở **batch trước**, thất bại của batch mới **không hoàn nguyên batch trước**. Ví dụ:

~~~text
Ban đầu:  A0, B0

Batch #1: retransformClasses(A, B)
  → thành công; có A1, B1

Batch #2: retransformClasses(A, B)
  → thất bại ở B
  → kết quả vẫn là A1, B1
  → KHÔNG có chuyện tự quay về A0, B0
~~~

### 6.2. Những gì không được rollback tự động

| Đối tượng | Khi batch lỗi, điều gì xảy ra? |
| --- | --- |
| **Định nghĩa class của tập được truyền vào batch** | Không lớp nào được cài định nghĩa mới bởi batch thất bại |
| **Log do transformer in trước lỗi** | Vẫn tồn tại trong console/file |
| **Counter/metric tăng trong callback** | Vẫn tăng trừ khi agent tự quản lý trạng thái |
| **Cấu hình static của agent** | Vẫn theo giá trị agent đã ghi; không tự rollback |
| **Network request/I/O do agent thực hiện** | Không được hoàn tác bởi JVM |
| **Class loading hoặc side effect khác xảy ra trong callback** | Không mặc định nằm trong transaction class definitions |
| **Một batch đã thành công trước đó** | Vẫn giữ definition đã cài trước |
| **Định nghĩa lớp không thuộc tập mà agent khác cập nhật độc lập** | Không được bảo vệ bởi batch này |
| **Object hiện có và static fields của ứng dụng** | Không được reset về giá trị khởi tạo |
| **Lời gọi method trên active stack frames** | Có thể tiếp tục bytecode cũ theo quy tắc JVM; không được “quay ngược thời gian” |

Vì thế **all-or-none không phải transaction database của toàn JVM**. Nó chỉ nói về việc **cài các định nghĩa của tập lớp** trong lời gọi retransform. Không có ACID transaction bao phủ mọi trạng thái tiến trình, mọi thread và mọi side effect của agent.

### 6.3. Khi batch thành công, các thread có thấy “chuyển phiên bản” tức thì không?

Theo Javadoc, **active stack frames** của những method đã được retransform có thể tiếp tục chạy **bytecode gốc của method**; **invocation mới** dùng định nghĩa được cập nhật. Điều này nghĩa là một workload đang chạy có thể còn frame A cũ trong khi invocation mới đã chạy A mới.

Ngay cả khi batch được cài thành công như một tập, **không nên hứa với caller rằng mọi business request đang chạy sẽ nhìn thấy “phiên bản A/B mới” như một snapshot tuyến tính hoàn hảo**. Nếu ứng dụng cần thay đổi giao thức giữa A và B mà mọi request phải chọn cùng phiên bản, hãy thiết kế **quiescence, version gating, feature flag hoặc phối hợp phía ứng dụng**. Một batch retransform không thay thế cơ chế điều phối transaction nghiệp vụ.

### 6.4. Static initializer và object instances không được reset

Retransformation không tự chạy lại **<clinit>**, không tái tạo object đã tồn tại và không reset giá trị static fields. Ví dụ đổi bytecode của method đọc một static field không có nghĩa giá trị field lập tức chuyển sang một giá trị mới. Khi kiểm thử kết quả, hãy phân biệt **class definition mới** với **state đang có của các instance và static variables**.

## 7. Tại sao một tập nhiều lớp hữu ích cho thay đổi phụ thuộc?

Xét hai class có giao thức chung:

~~~java
// Pseudocode ý tưởng, không phải file Java độc lập.
class Service {
    Response handle(Request r) {
        return Repository.lookup(r);
    }
}

class Repository {
    static Response lookup(Request r) {
        // ...
    }
}
~~~

Nếu agent muốn cài logic tracing mới cho cả caller và callee, có thể cần A/B cùng được cập nhật để không tạo ra trạng thái method A báo span format mới nhưng B vẫn dùng format cũ.

Một batch **retransformClasses(Service.class, Repository.class)** phù hợp khi **thay đổi class definition** có phụ thuộc. Tuy nhiên, nếu bạn định thêm method/field mới hoặc sửa descriptor mà JVM không cho phép ở retransform, việc gộp batch **không làm biến đổi cấu trúc đó trở nên hợp lệ**. Chọn đúng phương pháp instrumentation: thay method body trong giới hạn được hỗ trợ, hoặc dùng kiến trúc helper ngoại vi/đường triển khai khác.

### 7.1. Một batch chỉ xử lý chính các Class đã chọn

Nếu Service gọi một class thứ ba **Cache** chưa được thêm vào tập, không có bảo đảm rằng Cache sẽ tự được đưa vào batch. Các phép biến đổi của Cache có thể xảy ra độc lập do class loading hoặc agent khác. Muốn cập nhật giao thức gồm A, B và C, phải lập tập mục tiêu đầy đủ **các class cần thay đổi** và quản lý phụ thuộc một cách có chủ đích.

### 7.2. Phân biệt “tập lớp” với “tất cả instance”

**retransformClasses(Class<?>...)** nhận **Class object**, không nhận danh sách instance. JVM cập nhật định nghĩa method của class; những instance của class đã tồn tại vẫn là các object ấy. Không có chuyện mỗi object phải được liệt kê để retransform riêng, cũng không có chuyện class identity bị thay thành một Class mới chỉ vì đổi bytecode.

## 8. Phân loại lỗi từ retransformClasses

| Lỗi hoặc nhóm lỗi | Điều kiện thường gặp | Cách xử lý |
| --- | --- | --- |
| **UnmodifiableClassException** | Một phần tử không modifiable | Kiểm tra class identity, loại bỏ class không được hỗ trợ trước khi gửi |
| **UnsupportedOperationException** | JVM/manifest không hỗ trợ, hoặc thay đổi vượt giới hạn retransform | Kiểm tra capability, schema của class |
| **ClassFormatError** | Transformer trả dữ liệu class file không hợp lệ | Kiểm tra classfileBuffer và byte[] trả về |
| **UnsupportedClassVersionError** | Version class file không được JVM hỗ trợ | Kiểm tra major version và toolchain tạo bytes |
| **NoClassDefFoundError** (trường hợp tên trong classfile khác class cần sửa) | Sai tên nội bộ/binary name trong kết quả | Không đổi class identity/name khi retransform |
| **ClassCircularityError** | Kết quả tạo vòng phụ thuộc kiểu không hợp lệ | Phân tích hierarchy và linking |
| **LinkageError** | Xung đột linkage/verification liên quan | Kiểm tra cause và class loader/module |
| **NullPointerException** | Mảng classes hoặc một phần tử null | Validate input trước khi gửi |
| Lời gọi trả bình thường nhưng không có hành vi mới | Transformer trả null, bytes tương đương, hoặc kiểm tra sai target | Kiểm tra transformer, class identity, invocation sau retransform |

**Đừng bắt exception rồi báo “một phần batch đã được cài”.** Theo hợp đồng, nếu chính lời gọi retransformClasses ném exception, kết quả commit của batch là **none**. Có thể nhiều callback đã chạy, nhưng đó không phải bằng chứng cài đặt.

### 8.1. Transformer throw exception khác với trả bytes lỗi

Theo ClassFileTransformer Javadoc, nếu **transform() ném exception**, JVM vẫn có thể gọi transformer khác và tiếp tục định nghĩa/retransform; đối với callback đó, exception có thể được xử lý giống việc không có bytes thay thế. Vì vậy:

~~~java
// Đoạn minh họa chỉ để phân biệt hành vi.
throw new IllegalStateException("failed inside transform");
~~~

không phải cách đáng tin để **bắt retransformClasses thất bại**. Trong bài demo, nhánh failure trả **mảng không có class file hợp lệ**, dẫn tới lỗi khi JVM kiểm tra kết quả. Với sản phẩm, transformer nên dùng **return null** nếu bỏ qua có chủ đích; báo lỗi nghiệp vụ qua một kênh quản lý riêng khi cần.

### 8.2. Atomic ở API không có nghĩa exception được chẩn đoán tự động

Khi batch 20 lớp thất bại, exception chung không nhất thiết nói ngay lớp nào gây lỗi; log callback có thể giúp khoanh vùng nhưng cũng không phải chuỗi commit. Thiết kế chẩn đoán:

- Ghi request ID, danh sách class identity (class name, loader/module), capability và version agent.
- Ghi các lớp transformer đã nhận, kết quả null/bytes mới, kích thước/hash bytes nếu cần.
- Ghi exception type/message/stack trace từ **retransformClasses**.
- Khi cần, thử **tập nhỏ hơn trong môi trường kiểm thử** để cô lập class lỗi, nhưng hiểu rõ việc chia thành lời gọi mới **làm thay đổi bảo đảm nguyên tử**. Không làm binary search trên production rồi vô tình cài một nửa bản sửa khi tập con đầu tiên thành công.

## 9. Thiết kế một batch production an toàn

### 9.1. Giai đoạn chuẩn bị

1. **Xác định yêu cầu**: những class nào phải thay đổi cùng nhau để giữ tương thích?
2. **Resolve Class object** từ đúng JVM, loader và module; không dựa vào tên class thuần túy.
3. **Kiểm tra capability** với **isRetransformClassesSupported()**.
4. **Kiểm tra modifiable** cho từng phần tử, không đưa array/primitive hoặc class không được hỗ trợ.
5. **Cấu hình transformer** trước khi gọi: bộ lọc class, version advice, dependency/helper class sẵn sàng và state thread-safe.
6. **Dự trù chi phí**: class file lớn, retransformation và verifier có thể gây pause/CPU overhead, nhất là khi nhiều lớp được xử lý cùng một yêu cầu.
7. **Thiết lập bằng chứng**: trạng thái trước và dự kiến sau, probe/test với invocation mới.

### 9.2. Giai đoạn gọi API

~~~java
// Mẫu lập trình minh họa bên trong agent service.
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransform unavailable");
}

Class<?>[] targets = { Service.class, Repository.class };
for (Class<?> target : targets) {
    if (!inst.isModifiableClass(target)) {
        throw new IllegalArgumentException(
                "Not modifiable: " + target.getName());
    }
}

// Một lời gọi chứa toàn bộ tập phụ thuộc.
inst.retransformClasses(targets);
~~~

Đoạn code này dùng các lớp **Service/Repository** như placeholder minh họa và cần đặt trong chương trình thực với imports/khai báo class phù hợp. Nó không phải file Java chạy độc lập.

### 9.3. Giai đoạn xác minh

Khi **retransformClasses** trả bình thường:

1. Không chỉ kiểm tra “không có exception”; kiểm tra các lớp thật có kết quả đúng kỳ vọng.
2. Dùng **invocation mới** để tránh đọc nhầm active frame cũ.
3. Xác nhận những thành phần phụ thuộc tương thích với nhau.
4. Ghi rõ version batch và thời điểm áp dụng để chẩn đoán.
5. Nếu thiếu bằng chứng về hành vi mới, báo **APPLIED_UNVERIFIED** hoặc trạng thái thích hợp thay vì “mọi thứ thành công”.

Khi lời gọi ném exception:

1. Báo **BATCH_FAILED**, kèm lỗi gốc, request ID và tập mục tiêu.
2. **Không đánh dấu một phần tử nào là installed bởi batch thất bại**.
3. Không xóa trạng thái của các batch thành công trước đó.
4. Có thể giữ cấu hình agent ở trạng thái “pending” hoặc revert theo chính sách riêng, nhưng điều này **không tự được JVM thực hiện**.
5. Sau khi sửa nguyên nhân, có thể retry **cùng tập** với điều kiện lớp vẫn modifiable và biến đổi đúng state hiện tại.

### 9.4. Retry không được tạo double instrumentation

Nếu một batch thành công rồi operator không nhận được xác nhận ở tầng quản lý, retry có thể gây advice bị chèn hai lần nếu transformer không idempotent. Hãy thiết kế:

- Transformer nhận dạng marker/callsite của chính nó hoặc xây kết quả xác định từ bytes được JVM cung cấp.
- Không tự ý thêm cùng instruction mỗi lần callback.
- Không lưu cache chỉ theo FQCN nếu có nhiều loader.
- Khi dùng version, xác minh version đã cài bằng hành vi hay metadata có thể kiểm chứng.
- Tránh retry vô hạn trên lỗi **ClassFormatError**: cần sửa logic transformer chứ không chỉ gọi lại.

### 9.5. Batching theo độ lớn và phụ thuộc

Batch quá lớn có thể ảnh hưởng thời gian xử lý, khả năng debug và mức độ rollback khi một lớp lỗi; batch quá nhỏ có thể làm mất yêu cầu cập nhật đồng bộ của những class phụ thuộc. Hãy **nhóm theo tập lớp cần nhất quán về logic**:

~~~text
Nhóm giao thức A:
   Service, Repository, QueryMapper
   → 1 batch vì cùng version instrumentation

Nhóm độc lập B:
   MetricsPrinter
   → batch riêng nếu không ảnh hưởng giao thức A
~~~

Không có quy tắc “batch càng lớn càng tốt”. Mục tiêu là chọn **ranh giới nguyên tử có ý nghĩa**, đủ nhỏ để dễ vận hành, đủ lớn để tránh class definitions phụ thuộc bị triển khai dở dang.

## 10. So sánh với redefineClasses

**Instrumentation.redefineClasses(ClassDefinition...)** cũng nhận **một tập class definitions** và có bảo đảm *nếu lời gọi ném exception thì không lớp nào của tập được redefine*. Nhưng hai API khác nhau:

| Thuộc tính | **retransformClasses** | **redefineClasses** |
| --- | --- | --- |
| Input | Những Class object đã load | Những ClassDefinition chứa Class và bytes mới |
| Nguồn bytes | JVM dựng lại bytes nền rồi áp các transformer | Caller cung cấp class file bytes; JVM áp dụng những transformer thích hợp |
| Mục đích thường gặp | Chạy lại instrumentation để sửa class đang chạy | Cài class definition caller cung cấp trực tiếp |
| Capability | **Can-Retransform-Classes** / JVM support | **Can-Redefine-Classes** / JVM support |
| Multi-class atomic failure | Có | Có |
| Giới hạn schema | Có | Có |
| Active frames | Có thể tiếp tục code cũ | Có thể tiếp tục code cũ |

Không thể dùng **redefineClasses** như cách tránh mọi giới hạn schema hoặc như rollback tự động của retransform. Nếu cần hoàn nguyên một sửa đổi trước, phải có bytes hợp lệ và xét các transformer khác, class identity, khả năng redefine cùng mục tiêu nghiệp vụ; gỡ transformer đơn thuần không xóa code đã cài.

## 11. Các tình huống dễ hiểu sai

### 11.1. “Đã thấy log transformer A” nghĩa là A đã được cài?

**Không.** Transformer có thể đã chạy và trả bytes A', nhưng batch vẫn thất bại khi kiểm tra B'. Log đó chỉ là side effect của giai đoạn tạo bytes và không bị rollback.

### 11.2. “Lớp B có lỗi, JVM sẽ giữ A mới, chỉ bỏ B”?

**Không trong cùng một lời gọi retransformClasses(A,B).** Nếu lời gọi ném exception, không phần tử nào được retransform. Điều này khác với hai lời gọi độc lập.

### 11.3. “Batch thất bại thì mọi class quay về file JAR gốc”?

**Không.** Chúng giữ định nghĩa đã được cài **trước lời gọi thất bại**, có thể đã được retransform trước đó; không có reset class/static state.

### 11.4. “Batch thành công có nghĩa A và B đổi hành vi”?

**Không nhất thiết.** Transformer có thể trả null hoặc bytes tương đương. Bằng chứng thay đổi phải được kiểm chứng riêng.

### 11.5. “All-or-none bảo đảm các request đang chạy chỉ thấy toàn bộ code mới”?

**Không ở mức business transaction.** JVM có thể giữ active frames đang chạy code cũ; cần phối hợp ở tầng ứng dụng nếu muốn mỗi request đi qua một phiên bản giao thức nhất quán.

### 11.6. “Tôi chia tập thành 10 batch nhỏ mà vẫn gọi là một transaction”?

**Không.** Mỗi lời gọi chỉ có bảo đảm thất bại trên **tập của chính nó**. Những batch thành công trước không bị rollback nếu batch sau lỗi.

### 11.7. “isModifiableClass đúng là chắc chắn retransform thành công”?

**Không.** Nó chỉ xác nhận một điều kiện. Capability, class format, module/helper linkage, schema restriction và bytes từ transformer vẫn phải hợp lệ.

## 12. Ma trận test nên có

| Test | Setup | Kỳ vọng |
| --- | --- | --- |
| Hai lớp hợp lệ | Alpha, Beta, transformer trả bytes hợp lệ | Batch hoàn thành; hai method mới có kết quả mới |
| Beta class file lỗi | Alpha hợp lệ, Beta trả bytes invalid | Batch throw; cả hai method giữ hành vi trước |
| Chứa array class | Alpha, int[].class, Beta | **UnmodifiableClassException**; không có cập nhật mới |
| Chứa null | Alpha, null, Beta | **NullPointerException**; không có cập nhật |
| Tập rỗng | **retransformClasses()** | Không lỗi vì API cho phép no-op |
| Không có capability | Manifest/JVM không hỗ trợ | Bị từ chối; không cố gọi addTransformer(true) |
| Transformer trả null | Không có output mới | API có thể hoàn thành mà hành vi không đổi |
| Callback ném RuntimeException | Transformer lỗi nội bộ | Không đồng nhất với batch throw; JVM có thể coi callback như skip |
| Gọi hai batch độc lập | A thành công, B thất bại | A vẫn có định nghĩa mới từ batch trước |
| Retry cùng batch | Idempotent transformer | Không nhân đôi advice |
| Hai loader cùng tên | Hai Class identity độc lập | Đúng class được chọn, không sửa nhầm |
| Method đang chạy | Active frame trước retransform | Frame cũ có thể tiếp tục code cũ; invocation mới dùng code mới |
| Nhiều agent | Transformer chain khác nhau | Kết quả cuối hợp lệ, phụ thuộc thứ tự được kiểm thử |

### 12.1. Khi cần xác minh sâu hơn

- **javap** trên class file gốc chỉ cho thấy file trên đĩa; không tự thấy bytes đã cài runtime.
- Có thể dump **bytes do transformer trả về** trong môi trường kiểm thử và phân tích class file, nhưng đó chưa phải bằng chứng duy nhất về commit.
- Nếu cần xác nhận hành vi, xây probe gọi đúng class/method **sau khi API trả về**, đọc kết quả/metric theo kỳ vọng.
- Đừng lập luận rằng mọi callback đều phải đã được gọi trước khi JVM báo lỗi; chỉ dựa vào bảo đảm API.
- Nếu lớp có handler/stack frames phức tạp, kiểm thử verifier, exception semantics, thread safety và helper accessibility dưới JDK thực tế.

## 13. Checklist vận hành một batch nhiều lớp

- Tôi định danh đầy đủ tập theo **Class + defining loader + module**.
- Tôi hiểu tại sao các lớp này cần cùng một yêu cầu thay vì tách thành nhiều yêu cầu.
- Agent đã khai báo và kiểm tra **Can-Retransform-Classes** / JVM capability.
- Tất cả mục tiêu đều được kiểm tra **isModifiableClass**.
- Mỗi transformer chỉ sửa đúng lớp/method thuộc phạm vi; không mutate classfileBuffer.
- Transformer **canRetransform=false** được hiểu đúng là tái áp dụng kết quả cũ, không tự gọi lại.
- Các byte[] đề xuất hợp lệ về định dạng, class name, class version và giới hạn schema.
- Một lời gọi **retransformClasses(targets)** được dùng cho tập phụ thuộc.
- **Nếu lời gọi throw**, hệ thống báo *none installed for that batch*, không báo partial success.
- Không trông đợi JVM rollback log, counters, I/O, static fields hoặc các batch trước đó.
- Khi **lời gọi thành công**, tôi xác minh invocation mới và hành vi của **tất cả lớp liên quan**.
- Retry là idempotent; các callback, shared state và nhiều agent có thể chạy đồng thời mà không làm hỏng kết quả.

## 14. Tài liệu Java chính thức

- [Java 17 — Instrumentation.retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)): mô tả xử lý một tập, retransform steps và bảo đảm không lớp nào được cài nếu lời gọi ném exception.
- [Java 17 — Instrumentation.isModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#isModifiableClass(java.lang.Class)): array/primitive không modifiable và điều kiện kiểm tra.
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): chuỗi transformer, classfileBuffer không được sửa, return null/bytes và xử lý exception trong callback.
- [Java 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): Premain-Class, Agent-Class và Can-Retransform-Classes.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, class format và ràng buộc của class file.

**Ghi nhớ:** một lời gọi **retransformClasses(A, B, ...)** cho phép JVM cập nhật **một tập định nghĩa lớp** theo hợp đồng *all-or-none khi thất bại*. Nếu bất kỳ phần tử nào khiến lời gọi ném exception, **không class definition nào trong batch ấy được cài**. Đây không phải rollback cho những tác dụng phụ của transformer hay cho những batch đã thành công trước; ứng dụng vẫn cần kiểm soát phiên bản, side effect, retry và kiểm chứng hành vi.
