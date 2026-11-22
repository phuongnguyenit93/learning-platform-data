# ClassFileTransformer: trả null khi không đổi, trả mảng byte mới khi có biến đổi

Trong Java Instrumentation, **ClassFileTransformer.transform(...)** nhận bytecode của một lớp và có thể cung cấp phiên bản thay thế trước khi JVM hoàn tất quá trình định nghĩa, định nghĩa lại hoặc tái biến đổi lớp. Quy tắc trả về rất ngắn nhưng quyết định tính đúng đắn của một agent:

- **Không sửa lớp ở lượt callback này:** trả về **null**.
- **Thực sự muốn thay class file:** tạo một **byte[] mới**, giữ nguyên dữ liệu đầu vào, sửa trên bản sao rồi trả về **mảng mới có class file hợp lệ**.

Đây là **hợp đồng kết quả biến đổi của từng transformer**, không phải một phép thử toàn cục rằng lớp đã thay đổi hành vi. Trong chuỗi nhiều transformer, một transformer trả **null** vẫn có thể đứng trước hoặc sau transformer khác đang thay đổi lớp. Ngược lại, trả một mảng byte khác tham chiếu chưa chắc bytecode có khác biệt có ý nghĩa, và JVM vẫn phải kiểm tra định nghĩa cuối cùng.

Bài này trình bày chính xác ngữ nghĩa trả về, cách quyết định có đổi hay không, thao tác an toàn với bytecode đầu vào, lỗi phổ biến và một chương trình Java 17+ chạy được để thấy cả hai nhánh **return null** và **return byte[] mới**.

## 1. Đọc đúng hợp đồng của ClassFileTransformer

Agent đăng ký một transformer thông qua đối tượng **Instrumentation** mà JVM truyền vào **premain** (agent lúc startup) hoặc **agentmain** (agent được nạp sau startup):

~~~java
// Đoạn minh họa, nằm trong premain/agentmain.
instrumentation.addTransformer(transformer);
~~~

Từ đó, khi có sự kiện định nghĩa lớp phù hợp, JVM có thể gọi transformer trước bước áp dụng/kiểm tra class file. Với Java 17, cách cài đặt thông dụng là ghi đè dạng năm tham số:

~~~java
// Chữ ký trong lớp implements ClassFileTransformer.
// Đây là đoạn minh họa, không phải file Java độc lập.
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {

    if (!"example/Target".equals(className)) {
        return null;
    }

    byte[] replacement = createReplacement(classfileBuffer);
    return replacement; // cần là class file hợp lệ và mảng mới
}
~~~

Từ Java 9 còn có overload sáu tham số bắt đầu bằng **Module module**:

~~~java
// Overload có Module, thích hợp khi cần thông tin JPMS.
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
~~~

Trong Java 17, triển khai mặc định của overload sáu tham số **ủy quyền cho overload năm tham số**; vì vậy ghi đè dạng năm tham số vẫn là cách hợp lệ. Nếu cần phân biệt lớp cùng tên theo module, ghi đè dạng sáu tham số là tiện hơn. Hai đoạn trên là minh họa các chữ ký riêng, không phải hai phương thức bắt buộc phải triển khai cùng lúc.

Các tham số liên quan trực tiếp đến quyết định biến đổi:

| Tham số | Ý nghĩa khi quyết định return |
| --- | --- |
| **module** (overload sáu tham số) | Module chứa lớp đang được xử lý; giúp lọc theo ranh giới JPMS |
| **loader** | Defining class loader, có thể **null** khi được bootstrap loader định nghĩa |
| **className** | Tên nội bộ, ví dụ **java/util/List**, có dấu **/** thay cho dấu **.**; cần xử lý khả năng null phù hợp hợp đồng API |
| **classBeingRedefined** | **null** cho định nghĩa lớp mới; khác null khi đang redefine/retransform |
| **protectionDomain** | Miền bảo vệ liên quan đến lớp được định nghĩa hoặc định nghĩa lại |
| **classfileBuffer** | Dãy byte class file đầu vào của **lượt transformer hiện tại**; tuyệt đối không được mutate trực tiếp |

Quan trọng: **classfileBuffer là input chỉ đọc theo hợp đồng**, không phải buffer mà agent sở hữu và có thể sửa tại chỗ. Việc JVM chuyển nó cho transformer không chuyển quyền sở hữu byte[] sang mã ứng dụng.

## 2. Return null nghĩa là gì?

Trả **null** thể hiện rằng **transformer này không thực hiện phép biến đổi tại lượt gọi này**. Với một lớp không phù hợp phạm vi, tình huống đúng nhất thường là trả ngay:

~~~java
if (className == null || !className.startsWith("com/acme/")) {
    return null;
}
~~~

Điều này có ba hệ quả:

1. Đầu vào được chuyển tiếp không đổi **bởi transformer hiện tại** sang các bước hoặc transformer còn lại.
2. Transformer sau đó vẫn có cơ hội thay bytes. **null** không phải thông báo “cấm mọi transformer khác biến đổi”.
3. Trong một quá trình retransform, **null** không có nghĩa JVM sẽ tự phục hồi lớp về bytecode gốc. Những kết quả biến đổi trước đó và quy tắc retransform có thể còn ảnh hưởng.

Ví dụ:

~~~text
Bytes gốc B0
    │
    ▼
Transformer A: return null
    │
    ▼
Transformer B nhận B0
    │  nếu B trả về B1 hợp lệ
    ▼
JVM tiếp tục xử lý B1
~~~

Ngay cả khi A ghi log **SKIPPED**, việc lớp sau cùng có đổi hay không vẫn phụ thuộc B, các transformer khác, và kết quả xác minh/áp dụng của JVM.

**Khi nào nên return null?**

- Tên lớp, module, loader hoặc sự kiện không nằm trong phạm vi.
- Agent chỉ muốn quan sát lớp và không thay bytes.
- Điều kiện feature flag không bật.
- Mã đã kiểm tra và biết chắc không cần thêm/sửa instruction nào.
- Không tìm thấy pattern an toàn cần sửa trong ví dụ transformer có phạm vi giới hạn.
- Không thể tạo kết quả hợp lệ theo chính sách “fail safely” đã thiết kế; cần ghi dấu lý do riêng và trả null, tránh giả vờ đã sửa lớp.

Không dùng **new byte[0]**, mảng bytes giả hoặc một class file rỗng như ký hiệu “không đổi”: JVM có thể từ chối kết quả đó bằng lỗi class format/verification. **null** mới là tín hiệu “không biến đổi” theo API.

## 3. Return mảng byte mới nghĩa là gì?

Nếu muốn sửa bytecode, transformer tạo **một mảng khác**, chỉnh bản sao và trả mảng kết quả:

~~~java
// Đoạn minh họa trong transform(...).
byte[] changed = classfileBuffer.clone();
// Chỉ thay đổi changed, bằng một phép chỉnh sửa class file hợp lệ.
return changed;
~~~

**clone() chỉ sao chép bytes; nó chưa tự tạo phép biến đổi có ý nghĩa.** Mã thực phải thực hiện một thay đổi hợp lệ trên bản sao (hoặc dùng thư viện bytecode để dựng class file khác), rồi kiểm tra kết quả.

Có bốn khái niệm dễ bị lẫn:

| Điều đã quan sát | Có thể kết luận |
| --- | --- |
| **result != null** | Transformer đã cung cấp một dãy byte thay thế |
| **result != classfileBuffer** | Có một đối tượng mảng khác |
| **!Arrays.equals(result, classfileBuffer)** | Dữ liệu bytes của hai mảng khác nhau |
| Lớp được JVM chấp nhận và hành vi mong muốn được kiểm chứng | Phép biến đổi đã có hiệu lực đúng mục tiêu |

Ba điều đầu **chưa tự chứng minh** điều cuối. Mảng khác tham chiếu nhưng nội dung giống nhau là có thể xảy ra. Mảng khác nội dung nhưng sai định dạng, sai frame hoặc vi phạm giới hạn redefine/retransform vẫn có thể bị từ chối.

Mẫu tư duy nên dùng:

~~~text
shouldTransform?
    ├── Không ──> return null
    └── Có
          │
          ├── đọc/kiểm tra class file
          ├── tạo một byte[] mới
          ├── sửa theo quy tắc bytecode hợp lệ
          ├── xác nhận có kết quả mong muốn
          └── return changedBytes
                        │
                        ▼
             JVM/transformer tiếp theo
             kiểm tra và áp dụng sau đó
~~~

### 3.1. Vì sao không sửa trực tiếp classfileBuffer?

Cách dưới đây **vi phạm hợp đồng**, dù cuối cùng có trả về null hay trả lại chính input:

~~~java
// SAI: đoạn phản ví dụ, không sử dụng trong chương trình thật.
classfileBuffer[0] = 0;
return null;
~~~

Lý do: **classfileBuffer phải được giữ nguyên**. Không biết JVM hay transformer khác đang dựa vào nội dung input theo cách nào; việc mutate có thể dẫn đến dữ liệu không nhất quán, làm hỏng header **CAFEBABE**, gây lỗi khó chẩn đoán, và đi ngược hướng dẫn API.

Cách phù hợp:

~~~java
// ĐÚNG về quyền sở hữu buffer; đoạn minh họa chưa có bước sửa cụ thể.
byte[] candidate = classfileBuffer.clone();
// Chỉ thực hiện sửa đổi trên candidate.
return candidate;
~~~

Nếu cuối cùng xác định candidate không có gì khác và không cần sửa lớp, **return null** sẽ thể hiện chủ đích chính xác hơn. Không cần sao chép cả class file cho những lớp nằm ngoài phạm vi.

## 4. Bài thực hành Java 17+: hai lớp, hai nhánh return

Bài thực hành minh họa:

- Lớp **Ignored** được transformer nhìn thấy nhưng **return null**: phương thức giữ kết quả **STABLE**.
- Lớp **Changed** được transformer tạo **byte[] mới**: thay một hằng chuỗi **"BEFORE"** thành **"AFTER!"** trong constant pool rồi JVM định nghĩa lớp mới với kết quả mới.
- Để độc lập với thư viện ngoài, ví dụ sử dụng một hàm nhỏ chỉ tìm/thay **CONSTANT_Utf8_info** trong class file demo. Hai chuỗi ASCII đều dài **6 byte**; khi thay giữ nguyên độ dài constant pool entry, không làm dịch chuyển offset. Đây là **kỹ thuật tối giản cho demo**; production nên dùng thư viện bytecode phù hợp như ASM hoặc Byte Buddy.

### 4.1. File SampleApp.java

~~~java
// File: SampleApp.java
public final class SampleApp {
    public static void main(String[] args) {
        System.out.println("ignored=" + Ignored.value());
        System.out.println("changed=" + Changed.value());
    }
}

class Ignored {
    static String value() {
        return "STABLE";
    }
}

class Changed {
    static String value() {
        return "BEFORE";
    }
}
~~~

**Ignored.value()** và **Changed.value()** là các lời gọi method tại runtime, nên code bên gọi không chỉ dùng hằng compile-time từ field của lớp khác. Trình biên dịch tạo **SampleApp.class**, **Ignored.class** và **Changed.class**.

### 4.2. File DemoAgent.java

~~~java
// File: DemoAgent.java
import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    private DemoAgent() {
    }

    public static void premain(String options,
                               Instrumentation instrumentation) {
        instrumentation.addTransformer(new DemoTransformer());
        System.out.println("AGENT_READY");
    }
}
~~~

**premain** nhận Instrumentation từ JVM và đăng ký transformer **trước khi main được gọi**. Bài chỉ xử lý những lớp mới được tải sau thời điểm đăng ký nên **addTransformer(transformer)** là đủ; ví dụ không yêu cầu capability retransform.

### 4.3. File DemoTransformer.java

~~~java
// File: DemoTransformer.java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class DemoTransformer implements ClassFileTransformer {

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("Ignored".equals(className)) {
            System.out.println("TRANSFORM Ignored -> null");
            return null; // Chủ ý không sửa.
        }

        if (!"Changed".equals(className)) {
            return null; // Mọi lớp khác cũng giữ nguyên.
        }

        byte[] replacement = replaceDemoUtf8Constant(classfileBuffer);

        if (replacement == null) {
            System.out.println("TRANSFORM Changed -> null (no match)");
            return null;
        }

        System.out.println("TRANSFORM Changed -> new byte[]");
        return replacement;
    }

    private static byte[] replaceDemoUtf8Constant(byte[] original) {
        // Chỉ dành cho class file hợp lệ của ví dụ và chuỗi ASCII cố định.
        // Không phải parser/class writer cho bytecode tùy ý.
        if (original.length < 10
                || (original[0] & 0xff) != 0xca
                || (original[1] & 0xff) != 0xfe
                || (original[2] & 0xff) != 0xba
                || (original[3] & 0xff) != 0xbe) {
            return null;
        }

        int constantPoolCount = readU2(original, 8);
        int p = 10;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = original[p++] & 0xff;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int size = readU2(original, p);
                    p += 2;

                    if (size == 6 && matchesAscii(
                            original, p, "BEFORE")) {
                        byte[] copy = original.clone();
                        byte[] replacement = "AFTER!"
                                .getBytes(StandardCharsets.US_ASCII);
                        System.arraycopy(
                                replacement, 0, copy, p, replacement.length);
                        return copy;
                    }

                    p += size;
                }

                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // long/double chiếm hai slot
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;

                default -> throw new IllegalArgumentException(
                        "Unknown constant-pool tag: " + tag);
            }
        }
        return null;
    }

    private static int readU2(byte[] bytes, int p) {
        return ((bytes[p] & 0xff) << 8) | (bytes[p + 1] & 0xff);
    }

    private static boolean matchesAscii(byte[] bytes, int p,
                                        String needle) {
        if (p + needle.length() > bytes.length) {
            return false;
        }
        for (int i = 0; i < needle.length(); i++) {
            if (bytes[p + i] != (byte) needle.charAt(i)) {
                return false;
            }
        }
        return true;
    }
}
~~~

Điểm quan trọng trong chương trình:

1. **"Ignored".equals(className)** an toàn khi **className** là null, và phân biệt chính xác tên lớp cần bỏ qua.
2. **return null** trong nhánh **Ignored** không tạo/cấp phát mảng mới.
3. Với **Changed**, helper đọc cấu trúc constant pool để chỉ tìm UTF8 entry có giá trị **BEFORE**; chỉ đổi nó nếu đáp ứng điều kiện độ dài.
4. **original.clone()** tạo byte[] khác. **System.arraycopy** chỉ tác động bản sao, giữ nguyên **classfileBuffer** đầu vào.
5. **return replacement** thông báo với JVM có kết quả thay thế. Class **Changed** được định nghĩa với literal mới; gọi **Changed.value()** sau đó trả **AFTER!**.
6. Với class không phù hợp tên hoặc không có constant cần sửa, transformer trả **null**, đúng với hợp đồng không biến đổi.
7. Các log thể hiện **hành động của transformer**. Output của **SampleApp** mới là bằng chứng rằng lớp tương ứng đã thực thi với nội dung mong muốn.

**Phạm vi và giới hạn quan trọng:** Hàm đọc constant pool bên trên giả định class file hợp lệ như file do **javac --release 17** tạo, không thực hiện kiểm tra bounds đầy đủ cho input không tin cậy, không giải mã Modified UTF-8 tổng quát và chỉ thay chuỗi ASCII có cùng độ dài. Không dùng để instrument thư viện bất kỳ hoặc xem là bộ xử lý bytecode production. Phần **return null / return byte[]** mới là kỹ năng cần rút ra từ ví dụ.

### 4.4. Tạo manifest agent.mf

Tạo file văn bản **agent.mf**:

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
~~~

Đặt **newline ở cuối file**. **Premain-Class** là tên nhị phân của lớp agent; nếu chuyển vào package phải cập nhật đầy đủ FQCN ở manifest. Ví dụ chạy theo startup agent **-javaagent**, không phải attach động **agentmain**.

### 4.5. Biên dịch, đóng gói và chạy

Đặt bốn file **SampleApp.java**, **DemoAgent.java**, **DemoTransformer.java**, **agent.mf** vào cùng một thư mục. Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 SampleApp.java DemoAgent.java DemoTransformer.java
jar cfm demo-agent.jar agent.mf DemoAgent.class DemoTransformer.class
java -javaagent:demo-agent.jar -cp . SampleApp
~~~

Output thông thường trên HotSpot Java 17:

~~~text
AGENT_READY
TRANSFORM Ignored -> null
ignored=STABLE
TRANSFORM Changed -> new byte[]
changed=AFTER!
~~~

Các dòng chính cần xác nhận là **TRANSFORM Ignored -> null**, **ignored=STABLE**, **TRANSFORM Changed -> new byte[]**, **changed=AFTER!**. Thời điểm JVM quyết định tải những lớp độc lập có thể khác giữa các implementation, nên không nên xây test production chỉ dựa vào thứ tự log class-load; giá trị cuối phải khớp.

Đối chứng khi **không** dùng agent:

~~~bash
java -cp . SampleApp
~~~

Output:

~~~text
ignored=STABLE
changed=BEFORE
~~~

So sánh hai lượt chạy:

| Lớp | Transformer trả về | Không agent | Có agent |
| --- | --- | --- | --- |
| **Ignored** | **null** | **STABLE** | **STABLE** |
| **Changed** | **byte[] mới**, khác nội dung | **BEFORE** | **AFTER!** |

Ví dụ cho thấy khác biệt giữa **không thực hiện biến đổi** và **đề xuất định nghĩa class mới hợp lệ**, không cần phụ thuộc thư viện bên ngoài.

## 5. Vì sao việc sửa một constant pool entry của ví dụ có hiệu lực?

Trong **Changed.class**, phương thức **value()** thường chứa lệnh JVM **ldc** hoặc dạng tương đương để lấy string literal từ constant pool rồi **areturn**. Khi thay nội dung UTF8 entry của chuỗi được tham chiếu, định nghĩa class mới sẽ trả string tương ứng.

Dùng **javap** để quan sát class file gốc trên đĩa:

~~~bash
javap -c -p Changed
javap -v -p Changed
~~~

Với **javac --release 17**, phần disassembly của method **Changed.value()** thường có dạng:

~~~text
static java.lang.String value();
  Code:
     0: ldc           #7                  // String BEFORE
     2: areturn
~~~

Số index constant pool (ví dụ **#7**) có thể khác theo compiler, vì vậy kết quả ở đây là **đoạn minh họa**, không phải transcript byte-for-byte cố định của mọi JDK. Điều phải kiểm tra là có tham chiếu tới **String BEFORE**. Sau khi chạy agent, file **Changed.class trên đĩa** vẫn có thể chứa **BEFORE**: ví dụ đã thay bytes **trong quá trình định nghĩa lớp ở JVM**, không ghi đè class file trên disk.

Chỉ sửa nội dung một constant pool entry có cùng độ dài là khả thi với class demo vì:

- Hai chuỗi **BEFORE** và **AFTER!** đều gồm 6 byte ASCII.
- Mảng kết quả là một bản sao đầy đủ class file; header và những phần khác giữ nguyên.
- Không thay đổi độ dài Code attribute, offset instruction, field, method hoặc cấu trúc kế thừa.
- JVM vẫn thực hiện quy trình kiểm tra/định nghĩa lớp trước khi cho ứng dụng dùng.

Trong class file thực, sửa constant pool còn có thể tác động mọi chỗ tham chiếu cùng entry; với các chuỗi không ASCII có Modified UTF-8 và độ dài khác, không thể tùy tiện thay bytes theo lối trên. Cần thư viện viết lại class file và tính/duy trì cấu trúc liên quan.

## 6. Chuỗi nhiều transformer: null chỉ là quyết định cục bộ

Instrumentation cho phép đăng ký nhiều transformer; JVM áp dụng chúng theo các nhóm và thứ tự được quy định trong **ClassFileTransformer**. Trong cùng nhóm, transformer được gọi theo thứ tự đăng ký. Kết quả byte[] của transformer trước trở thành **classfileBuffer** của transformer sau; khi trước trả null, dữ liệu đang có được chuyển tiếp.

~~~text
Bytes đầu vào B0
        │
        ▼
Transformer A: thấy lớp không phù hợp
        │ return null
        ▼
Transformer B: biến đổi B0 thành B1
        │ return new byte[] B1
        ▼
Transformer C: nhận B1
        │ return null
        ▼
JVM kiểm tra và có thể định nghĩa lớp với B1
~~~

Như vậy:

- A và C **không sửa** lớp ở lần gọi tương ứng.
- B **đã cung cấp bản thay thế**.
- Việc A hoặc C trả null không làm hủy biến đổi của B.
- JVM vẫn cần xác nhận B1 hợp lệ. Có thể có transformer khác sau đó tiếp tục sửa, nên chỉ log tại B chưa đủ kết luận nội dung cuối cùng.

Khi viết audit/metrics, cần phân biệt:

~~~text
callbackCount       = số lần callback được gọi
skippedCount        = số lần cố ý return null
replacementCount    = số lần trả về byte[] mới
verifiedChangeCount = số lần có bằng chứng lớp/hành vi thực sự đổi đúng
~~~

**replacementCount không đồng nghĩa verifiedChangeCount.** Nếu cần bảo đảm “mảng có khác dữ liệu đầu vào không”, có thể so **Arrays.equals(before, after)** nhưng so sánh byte-by-byte tốn chi phí cho class file lớn và vẫn không chứng minh bản sửa được JVM chấp nhận. Chỉ dùng phép so sánh theo nhu cầu chẩn đoán hoặc test, không áp dụng bừa bãi cho mọi class load ở production.

### 6.1. Đăng ký một transformer hai lần có an toàn không?

**Instrumentation.addTransformer(...)** có thể nhận cùng một instance nhiều lần; API không khuyến khích việc đó. Nếu bị đăng ký lặp, cùng logic có thể được áp dụng nhiều lần trên chuỗi bytes, gây biến đổi trùng hoặc kết quả không hợp lệ. Thiết kế nên giữ đúng một điểm đăng ký cho từng trách nhiệm và quản lý vòng đời **removeTransformer(instance)** có chủ đích.

Các transformer cũng nên viết **idempotent** khi có thể: lớp đã gắn marker hoặc đã có phép biến đổi tương ứng thì lượt sau **return null** thay vì thêm tiếp cùng một instruction.

## 7. Reload, redefine và retransform: cùng hợp đồng trả về, khác bối cảnh

**ClassFileTransformer** có thể được gọi khi lớp được định nghĩa lần đầu, được redefine hoặc được retransform. Việc nó có được gọi khi **retransformClasses(...)** phụ thuộc cách đăng ký:

~~~java
// Trong premain/agentmain, nếu cần nhận callback retransform:
if (instrumentation.isRetransformClassesSupported()) {
    instrumentation.addTransformer(transformer, true);
}
~~~

Đoạn này là minh họa, không phải chương trình độc lập. Với **addTransformer(transformer)** mặc định (**canRetransform=false**), transformer nhận các sự kiện định nghĩa lớp mới và redefine theo hợp đồng, nhưng **không được gọi lại** trong retransform; JVM có thể **tái áp dụng kết quả đã được lưu** từ lần biến đổi trước của nhóm transformer không hỗ trợ retransformation.

Với **canRetransform=true**, callback được gọi trong quá trình retransform phù hợp. Khi đó quy tắc vẫn là:

- **return null** nếu **lượt này** không cung cấp bytes mới.
- **return byte[] mới** nếu cần class file thay thế **hợp lệ với giới hạn retransform**.

Cần tránh một suy luận sai: “Trả null trong retransform sẽ làm JVM lấy lại class gốc chưa instrument.” Không thể suy ra điều này khi còn nhiều transformer, đặc biệt các kết quả từ transformer không hỗ trợ retransform được tái áp dụng tự động.

Một phép **retransformClasses** hoàn thành mà không throw không có nghĩa mọi callback đã trả bytes khác: yêu cầu có thể thành công dù tất cả trả null. Ngược lại, trả byte[] mới không bảo đảm thành công nếu verifier hoặc giới hạn structural change từ chối class file sau cùng.

Việc retransform/redefine lớp đã tồn tại thường bị hạn chế thay đổi schema (thêm/xóa method/field, thay kế thừa, v.v.). Instrumentation ở giai đoạn load mới và retransform sau khi lớp đã chạy cần được kiểm tra ở các điều kiện riêng.

### 7.1. Quy tắc trong trường hợp lớp đã từng được biến đổi

Giả sử transformer thêm mã log vào đầu method. Khi được gọi lại, nếu cứ thêm mã log lần nữa mà không kiểm tra marker/cấu trúc hiện có, có thể dẫn đến chạy log trùng hoặc nở bytecode. Lựa chọn phù hợp là:

1. Nhận diện **đúng lớp và đúng sự kiện**.
2. Kiểm tra class đã có thay đổi tương ứng chưa.
3. Nếu đã đúng trạng thái mong muốn, **return null** cho lượt hiện tại.
4. Nếu cần cập nhật, tạo **class file mới hợp lệ**, đồng thời tuân thủ giới hạn redefine/retransform.

Không giả định **classfileBuffer** trong retransformation luôn là bản sao byte-for-byte của class file đang chạy hoặc file trên đĩa: Javadoc mô tả quá trình tạo lại bytes, có thể khác chi tiết constant pool/attributes.

## 8. Lọc đúng lớp trước khi tốn chi phí biến đổi

Một transformer được đăng ký có thể nhận callback cho rất nhiều lớp. Tạo bản sao cho mọi lớp là lãng phí và có thể tăng thời gian startup; vì vậy ưu tiên điều kiện lọc rẻ và trả null sớm:

~~~java
// Minh họa bên trong transform có Module.
if (className == null) {
    return null;
}
if (loader == null) {
    return null; // Chính sách ví dụ: không đụng lớp bootstrap.
}
if (!className.startsWith("com/example/app/")) {
    return null;
}
if (module != null && module.isNamed()
        && !"com.example.app".equals(module.getName())) {
    return null;
}
// Sau bước lọc mới cân nhắc parse/transform classfileBuffer.
~~~

Những điều kiện này là **chính sách ví dụ**, không phải yêu cầu của JVM. Agent trong thực tế có thể cần xử lý bootstrap classes hoặc module khác. Tên nội bộ với **/** phải được so đúng; dùng **className.equals("com.example.app.Service")** sẽ không khớp tên truyền theo định dạng nội bộ.

Với ứng dụng dùng nhiều class loader, **cùng binary name + defining loader khác nhau** có thể là hai lớp runtime khác nhau. Nếu một agent chỉ muốn sửa bản của một plugin hoặc một web application, cần xét loader/module/nguồn class thích hợp, không dùng tên làm duy nhất.

**Đừng cố gọi loader.loadClass(...) chỉ để kiểm tra lớp ở ngay trong transform.** Lời gọi này có thể kích hoạt class loading lồng nhau, dẫn đến recursion, class circularity, khóa loader hoặc side effect khởi tạo không mong muốn. Giữ logic lọc ít phụ thuộc nhất có thể.

## 9. An toàn luồng và xử lý lỗi trong transformer

Transform callback có thể xảy ra trong lúc JVM tải lớp trên những luồng khác nhau. Hợp đồng **null vs byte[]** phải được bảo toàn ngay cả dưới concurrency.

### 9.1. Không giữ buffer mutable làm state dùng chung

Ví dụ thiết kế nguy hiểm:

~~~java
// SAI: đoạn phản ví dụ, không thực thi.
static byte[] lastInput;

public byte[] transform(..., byte[] classfileBuffer) {
    lastInput = classfileBuffer;
    return null;
}
~~~

Đây không phải chữ ký Java hợp lệ vì **...** chỉ dùng làm ký hiệu minh họa. Vấn đề: việc giữ **classfileBuffer** vào static state vừa tạo rủi ro chia sẻ dữ liệu không cần thiết vừa làm mã khó kiểm soát vòng đời/cấp phát. Nếu cần debug class file, hãy tạo bản sao riêng, giới hạn dung lượng/thời gian lưu và bảo vệ collection theo mô hình đồng thời thích hợp.

**Mỗi invocation nên dùng biến local**, không tái sử dụng một mảng byte[] mutable giữa những lượt transform. Cache bytes nếu thực sự cần thì phải có khóa nhận diện lớp đủ mạnh, chính sách tránh memory leak class loader và synchronization rõ ràng.

### 9.2. Throwable hoặc IllegalClassFormatException có ý nghĩa gì?

Theo hợp đồng, nếu transformer ném exception không được bắt, JVM vẫn có thể gọi các transformer đăng ký khác và tiếp tục thử định nghĩa/redefine/retransform lớp. Đối với kết quả của transformer đó, exception được xử lý theo cách tương đương **không cung cấp biến đổi**.

Đừng sử dụng **throw exception** như phương pháp bình thường để skip lớp. **return null** giúp chủ đích rõ ràng, ít chi phí và dễ đếm trạng thái. **IllegalClassFormatException** thích hợp khi muốn báo input không phải class file đúng định dạng; dù kết quả tương đương null cho callback này, thông tin lỗi giúp chẩn đoán.

Nếu transformer tạo bytes khác nhưng **không hợp lệ**, JVM có thể ném **ClassFormatError**, **VerifyError**, **LinkageError** hoặc lỗi liên quan trong lúc định nghĩa/kiểm tra lớp; trường hợp retransform có thể phát sinh exception tại API caller. Đó là lỗi khác với quyết định **return null**.

### 9.3. Ghi log và metrics sao cho đáng tin

Nên gắn rõ:

~~~text
CLASS_SEEN name=com/example/app/Service loader=...
SKIPPED reason=FILTER
SKIPPED reason=ALREADY_INSTRUMENTED
REPLACEMENT_SUPPLIED name=... inputBytes=... outputBytes=...
CLASS_APPLY_FAILED error=...
BEHAVIOR_VERIFIED probe=...
~~~

Một hệ thống quan sát có thể báo trạng thái cấp callback (**SKIPPED**/**REPLACEMENT_SUPPLIED**) và cấp kết quả JVM (**APPLIED**/**REJECTED**) riêng. Không kết luận “instrumentation thành công” chỉ vì transformer in **REPLACEMENT_SUPPLIED**; verification và việc sử dụng class xảy ra sau đó.

## 10. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Trả **new byte[0]** để skip | JVM nhận class file không hợp lệ | **return null** |
| Sửa **classfileBuffer** rồi **return null** | Vi phạm input bất biến; kết quả không đáng tin | Không mutate input; nếu không sửa **return null** |
| Sửa trực tiếp input rồi trả lại input | Vi phạm hợp đồng, dễ hỏng pipeline | Tạo byte[] khác và sửa bản sao |
| **return classfileBuffer.clone()** cho mọi lớp | Tốn CPU/heap dù không đổi nội dung | Lọc và **return null** khi không cần sửa |
| Xem **result != null** là “bytecode đã đổi đúng” | Có thể mảng mới nhưng byte giống cũ | Test dữ liệu đầu ra và phép áp dụng JVM riêng |
| Không phân biệt **className** nội bộ và FQCN | Lọc sai; transformer toàn trả null | Dùng dạng **com/example/Foo** |
| Chỉ lọc tên, bỏ qua class loader/module | Sửa nhầm lớp trùng tên | Xác định loader/module khi cần |
| Gọi code ứng dụng hoặc I/O nặng trong transform | Rủi ro recursion/deadlock, chậm khởi động | Callback ngắn, hạn chế side effect |
| Quên retransform khi transformer đăng ký muộn | Lớp cũ không được callback lần nữa | Chọn cơ chế retransform/redefine phù hợp |
| Trả byte[] không đúng class format | **VerifyError**, **ClassFormatError** và lỗi startup | Dùng class writer đúng chuẩn, kiểm tra trên JDK mục tiêu |
| Không bảo vệ shared state | Race khi nhiều class loading thread | Atomic/ConcurrentHashMap và lifecycle rõ ràng |

## 11. Checklist QA cho một ClassFileTransformer

Trước khi đăng ký transformer, hãy xác nhận:

- **Điều kiện lọc** quyết định đúng lớp, loader, module, sự kiện và feature flag.
- Với mọi trường hợp không cần sửa, callback **trả null**, không tạo placeholder bytes.
- **classfileBuffer luôn bất biến**; mọi output có thay đổi đều là **mảng mới**.
- Bytes trả về là **class file well-formed**, đúng class file version, cấu trúc constant pool, instruction, stack/frame và metadata liên quan.
- Không có nhánh vô tình trả byte[] mới dù không sửa gì mà lại ghi log “đã biến đổi”.
- Khi nhiều transformer, hiểu kết quả được **xâu chuỗi**; null của mình không hủy output của transformer khác.
- Nếu hỗ trợ retransform, thiết kế an toàn khi callback chạy lại, tuân thủ giới hạn redefine/retransform và kiểm tra capability JVM.
- Không kéo trạng thái class loader/module vào cache dài hạn mà thiếu chiến lược dọn; callback chịu được concurrency và reentrancy.
- Có test **lớp bỏ qua**, **lớp sửa đúng**, **lớp không chứa pattern**, **lớp đã được instrument**, và **bytes không hợp lệ** khi cần.
- Kết quả cuối được xác minh **bên ngoài callback** bằng hành vi của method/class thật, không chỉ bằng một log **return new bytes**.

### Câu hỏi tự kiểm tra

1. **Nếu không muốn sửa một lớp, return null hay clone input rồi return?** **null** là kết quả đúng và rõ nghĩa nhất.
2. **Transformer A trả null; transformer B có thể sửa lớp không?** Có. **null** chỉ là quyết định của A.
3. **Có thể sửa classfileBuffer rồi return null để giữ hiệu ứng không?** Không. Input phải bất biến; JVM không hứa dùng thay đổi đó.
4. **Trả một byte[] mới giống hệt input có đồng nghĩa lớp được sửa không?** Không. Mới về identity chưa có nghĩa khác dữ liệu hoặc khác hành vi.
5. **Nếu transformer cung cấp bytes không hợp lệ thì JVM bắt buộc dùng chúng không?** Không. JVM còn kiểm tra định nghĩa; lỗi có thể chặn load/retransform.
6. **Bỏ qua một lớp ở lượt retransform có luôn xóa các transform cũ không?** Không. Quy tắc tái áp dụng output từ transformer không hỗ trợ retransform và các transformer khác vẫn quan trọng.
7. **Vì sao cần return null trước khi clone?** Vì tránh parse, allocate và sửa những lớp ngoài phạm vi.
8. **Làm thế nào chứng minh ví dụ đã sửa lớp Changed?** So sánh lượt không agent (**changed=BEFORE**) với lượt có agent (**changed=AFTER!**), đồng thời quan sát callback trả byte[] mới.

## 12. Tài liệu tham khảo chuẩn

- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): mô tả ngữ nghĩa return null, mảng byte mới, input không được sửa, thứ tự gọi nhiều transformer và xử lý lỗi.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký/gỡ transformer, capability và retransform/redefine.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, method bytecode, class format, verification metadata.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest, Premain-Class và agent entry point.

**Quy tắc cần nhớ khi viết transformer:** **Không đổi → return null. Có đổi → tạo byte[] mới, sửa bản sao thành class file hợp lệ rồi return.** Sau đó mới dùng kết quả kiểm tra của JVM và phép thử hành vi để xác nhận biến đổi đã thật sự có hiệu lực.
