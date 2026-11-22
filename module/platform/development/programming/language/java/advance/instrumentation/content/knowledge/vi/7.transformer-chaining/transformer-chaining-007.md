# Không giả định mảng byte đầu vào luôn giống bản class trên đĩa

Khi viết Java agent, tham số `classfileBuffer` của `ClassFileTransformer.transform(...)` chứa **bytes class file ở bước hiện tại trong chuỗi biến đổi**. Không có bảo đảm chung rằng mảng bytes này giống hệt tệp `.class` bạn mở từ thư mục build hay JAR trên ổ đĩa. Trong một lượt định nghĩa lớp, transformer đứng trước có thể đã thay đổi bytes; ở một lượt `redefineClasses` hoặc `retransformClasses`, nguồn và cách tái tạo bytes còn phụ thuộc yêu cầu instrumentation trước đó. Một số lớp cũng được sinh trực tiếp trong bộ nhớ, không có tệp `.class` tương ứng để so sánh.

**Nguyên tắc làm việc:** Hãy xem `classfileBuffer` là **đầu vào thực tế và có thẩm quyền của lần callback đó**. Khi muốn biến đổi, đọc và phân tích đúng mảng được truyền vào, tạo một mảng mới rồi trả về. Chỉ dùng “bytes trên đĩa” làm dữ liệu đối chiếu khi bạn xác minh được chúng đến từ đúng class, đúng class loader, đúng phiên bản và đúng giai đoạn xử lý.

## 1. Vì sao chủ đề này quan trọng?

Giả sử một ứng dụng dùng hai agent:

- Agent A chèn phép đo thời gian vào một phương thức.
- Agent B chèn log hoặc thu thập coverage vào cùng phương thức.

Nếu B giả định class file đang xử lý luôn là bản chưa được A sửa và tìm một chuỗi opcode hoặc offset vốn chỉ tồn tại trong bản nguyên gốc, B có thể xác định sai vị trí chèn mã, phá stack map frame hoặc tạo bytecode không hợp lệ. Kết quả có thể là `VerifyError`, `ClassFormatError` hoặc công cụ quan sát cho số liệu sai.

Cách nhìn đúng:

```text
Bytecode ở thời điểm JVM yêu cầu định nghĩa/redefine/retransform
                  |
                  v
          Transformer A
        inputA -> outputA
                  |
                  v
          Transformer B
        inputB = outputA (nếu A trả byte[] mới)
                  |
                  v
          Transformer C ...
                  |
                  v
      JVM kiểm tra và áp dụng class bytes kết quả
```

Nếu A trả `null`, JVM chuyển tiếp bytes hiện tại cho B; nếu A trả một mảng `byte[]` mới, mảng đó trở thành nội dung đầu vào của B. Các transformer kết hợp theo **chuỗi**, không mặc định hoạt động độc lập trên nhiều bản sao của một tệp `.class` gốc.

Đây không chỉ là chuyện thay đổi nội dung. Ngay cả khi logic Java tương đương, bytes có thể khác vì constant pool, attribute, thứ tự các phần không mang ý nghĩa hoặc dữ liệu do compiler/agent/class loader tạo ra.

## 2. `classfileBuffer` thực sự đại diện cho gì?

Chữ ký đầy đủ thường dùng trong Java 17:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Đọc bytes của bước biến đổi hiện tại.
    return null;
}
```

Đây là **phần thân minh họa đặt trong một class implements ClassFileTransformer**, không phải chương trình Java độc lập. `className` thường dùng **tên nội bộ** như `demo/pipeline/Target`; `classBeingRedefined == null` trong lần định nghĩa mới và khác `null` khi redefine hoặc retransform.

Theo hợp đồng Java 17, đầu vào cho **transformer đầu tiên trong chuỗi** phụ thuộc trường hợp:

| Tình huống | Nguồn bytes ban đầu theo hợp đồng |
| --- | --- |
| **Định nghĩa lớp mới** | Bytes được chuyển vào `ClassLoader.defineClass(...)` hoặc cơ chế định nghĩa JVM tương đương. |
| **Định nghĩa lại lớp đã nạp** | Bytes do lời gọi `Instrumentation.redefineClasses(...)` cung cấp trong `ClassDefinition`. |
| **Retransform lớp đã nạp** | JVM bắt đầu từ bytes định nghĩa ban đầu hoặc lần redefine gần nhất theo hợp đồng; kết quả của transformer không hỗ trợ retransformation được tái áp dụng, còn transformer có hỗ trợ được gọi lại. |
| **Transformer thứ hai trở đi trong một chuỗi** | Bytes đầu vào là **kết quả hiện tại** do transformer trước để lại, có thể đã khác bytes nguồn của yêu cầu. |

Trong bảng trên, “transformer đầu tiên” có nghĩa là transformer đầu tiên của **chuỗi áp dụng thực tế**, không phải agent đầu tiên được đặt tên trên lệnh `java` trong mọi trường hợp. JVM phân loại các transformer theo nhóm retransformation capability và nhóm Java/native trước khi áp dụng thứ tự đăng ký trong từng nhóm.

### 2.1. Tên “class file” không đòi hỏi tệp nằm trên hệ thống file

Đặc tả dùng từ **class file** để chỉ một chuỗi bytes hợp lệ theo định dạng JVM ClassFile; chuỗi này **có thể tồn tại hoàn toàn trong bộ nhớ**. Các class có thể được tạo bởi bộ sinh mã, class loader tùy chỉnh, framework, proxy hoặc cơ chế runtime khác mà không có tệp `.class` độc lập nào trên đĩa.

Với class loader thông thường, tệp nguồn có thể nằm trong JAR hoặc module image, không phải thư mục `out`. Với custom loader, bytes chuyển vào `defineClass` có thể đã được giải nén, giải mã hoặc tạo mới từ một nguồn khác. Vì thế hành động “đọc tệp class trên đĩa rồi so sánh” có thể không thực hiện được hoặc so sánh **sai đối tượng**.

### 2.2. Không nên mặc định `getResourceAsStream` trả đúng bytes mà JVM đang dùng

`loader.getResourceAsStream("pkg/Type.class")` trả về **tài nguyên classpath mà loader tìm thấy tại thời điểm đọc**. Nó không phải API chuẩn để truy xuất định nghĩa class đang hoạt động. Lý do có thể khác nhau: class loader không cung cấp resource tương ứng, resource được chọn khác nguồn định nghĩa, có nhiều JAR chứa cùng tên, class được tạo trong bộ nhớ, hoặc các transformer đã biến đổi class sau khi đọc resource.

Trong ví dụ thực hành dưới đây, ta **cố ý dùng classpath đơn giản** để tệp `Target.class` trên đĩa là mốc đối chiếu đáng tin. Không suy rộng kết quả đó thành bảo đảm cho mọi ứng dụng production.

## 3. Quy tắc phối hợp nhiều transformer

Có hai loại đăng ký thường gặp:

```java
// Trích đoạn bên trong premain/agentmain:
instrumentation.addTransformer(transformerA, false);
instrumentation.addTransformer(transformerB, false);
```

Cả A và B thuộc cùng nhóm **Java transformer không hỗ trợ retransformation**. Nếu A đăng ký trước B thì trong lần định nghĩa mới, JVM gọi A trước B. B nhận bytes đã qua A nếu A trả `byte[]` mới.

Theo Java 17, thứ tự **các nhóm** là:

1. Java transformer **không hỗ trợ retransformation** (`canRetransform=false`).
2. Native transformer không hỗ trợ retransformation.
3. Java transformer **hỗ trợ retransformation** (`canRetransform=true`).
4. Native transformer hỗ trợ retransformation.

Trong một nhóm, thứ tự đăng ký quyết định thứ tự thực hiện. Vì vậy với A `canRetransform=true` và B `false`, B có thể chạy trước A **ngay cả khi A được đăng ký trước**. Không nên kết luận thứ tự transform chỉ từ thứ tự agent được liệt kê trong command line.

Các giá trị trả về:

| A trả về | Bytes B nhận |
| --- | --- |
| `null` | Giữ nguyên bytes hiện tại của chuỗi. |
| Một mảng `byte[]` mới hợp lệ | Chuyển mảng bytes mới cho B. |
| Ném exception không bắt | Theo hợp đồng, JVM vẫn tiếp tục gọi các transformer sau; tác dụng tương đương A trả `null`. |
| Bytes không hợp lệ | JVM vẫn thử kiểm tra/áp dụng; có thể phát sinh lỗi class format/verification. Không có cơ chế tự sửa bytes sai. |

**Bắt buộc:** `classfileBuffer` là **mảng đầu vào không được chỉnh sửa trực tiếp**. Khi biến đổi, tạo mảng khác, chẳng hạn `byte[] output = classfileBuffer.clone()`, sửa `output` và trả `output`. Trả `null` khi không cần biến đổi.

## 4. Thí nghiệm chạy được: transformer B nhìn thấy bytes đã bị A thay đổi

Ta dùng **Java 17+**, không cần thư viện ngoài. Agent đăng ký hai transformer cùng nhóm theo thứ tự A → B:

- **A** sửa một string literal ngắn bằng cách thay đúng một chuỗi ASCII có độ dài không đổi trong constant pool: `FROM_DISK` → `FROM_LIVE`.
- **B** đọc `classfileBuffer` được JVM chuyển tới, đọc riêng `Target.class` từ resource của class loader, rồi so sánh. B không thay đổi bytes.
- **Ứng dụng** nạp `Target` sau khi `premain` đã đăng ký A và B, gọi `Target.message()` bằng reflection để tránh tham chiếu tĩnh từ trước.
- Ta sẽ quan sát **B nhận `FROM_LIVE`**, trong khi resource `Target.class` vẫn chứa `FROM_DISK`.

Thí nghiệm cố ý thay đúng một literal ASCII có **cùng độ dài 9 byte** để không làm lệch cấu trúc class file. Cách “tìm rồi sửa bytes thô” chỉ dành cho phép kiểm chứng nhỏ đã biết chính xác nội dung đầu vào. Trong hệ thống thật, nên dùng parser/bytecode library chuyên dụng và kiểm tra cấu trúc constant pool, stack map, mô hình class.

### 4.1. Cấu trúc thư mục

```text
pipeline-demo/
├── src/
│   └── demo/
│       └── pipeline/
│           ├── Agent.java
│           ├── FirstTransformer.java
│           ├── SecondTransformer.java
│           ├── Target.java
│           └── App.java
└── agent.mf
```

Mỗi file Java dưới đây được khai báo bằng đúng tên class public; toàn bộ thuộc package `demo.pipeline`.

### 4.2. `src/demo/pipeline/Target.java`

```java
package demo.pipeline;

public final class Target {
    private Target() {}

    public static String message() {
        return "FROM_DISK";
    }
}
```

String literal `FROM_DISK` được compiler đưa vào class file. Trong thí nghiệm không có công cụ build hay bước khác sửa `Target.class` trên đĩa sau khi biên dịch.

### 4.3. `src/demo/pipeline/Agent.java`

```java
package demo.pipeline;

import java.lang.instrument.Instrumentation;

public final class Agent {
    private Agent() {}

    public static void premain(String options, Instrumentation inst) {
        inst.addTransformer(new FirstTransformer(), false);
        inst.addTransformer(new SecondTransformer(), false);
        System.out.println("[agent] registered A then B");
    }
}
```

Vì A và B được đăng ký với `false`, cả hai nằm trong cùng nhóm Java retransformation-incapable. JVM gọi A rồi B khi `Target` được định nghĩa lần đầu sau lúc đăng ký.

### 4.4. `src/demo/pipeline/FirstTransformer.java`

```java
package demo.pipeline;

import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class FirstTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"demo/pipeline/Target".equals(className)) {
            return null;
        }

        byte[] from = "FROM_DISK".getBytes(StandardCharsets.US_ASCII);
        byte[] to = "FROM_LIVE".getBytes(StandardCharsets.US_ASCII);
        byte[] result = classfileBuffer.clone();

        int matches = 0;
        int foundAt = -1;

        for (int i = 0; i <= result.length - from.length; i++) {
            boolean equal = true;
            for (int j = 0; j < from.length; j++) {
                if (result[i + j] != from[j]) {
                    equal = false;
                    break;
                }
            }
            if (equal) {
                matches++;
                foundAt = i;
            }
        }

        if (matches != 1 || from.length != to.length) {
            throw new IllegalStateException(
                    "Expected exactly one fixed-length marker, got "
                            + matches);
        }

        System.arraycopy(to, 0, result, foundAt, to.length);
        System.out.println("[A] replaced FROM_DISK -> FROM_LIVE");
        return result;
    }
}
```

Giải thích:

1. A chỉ xử lý `Target`; tên JVM nội bộ dùng dấu `/`.
2. A **clone** `classfileBuffer` và sửa mảng kết quả; nó không sửa mảng được JVM truyền vào.
3. Tìm đúng một chỗ xuất hiện của ASCII literal `FROM_DISK` và kiểm tra hai chuỗi dài bằng nhau trước khi ghi. Trong class mẫu, vị trí đó là payload của UTF-8 constant-pool entry dành cho literal.
4. Khi A trả `result`, JVM truyền **bytes đã đổi** tới transformer tiếp theo.
5. Nếu class mẫu bị sửa khiến marker không còn đúng một lần, A ném lỗi để báo vấn đề trong log; theo hợp đồng, exception này không tự dừng việc định nghĩa lớp. Vì vậy đừng dùng chiến lược này cho production.

Java 17 định nghĩa `ClassFileTransformer` với các phương thức `transform` mặc định; **không được dùng lambda trực tiếp** như một functional interface. Class ở trên override dạng sáu tham số nên biên dịch hợp lệ.

### 4.5. `src/demo/pipeline/SecondTransformer.java`

```java
package demo.pipeline;

import java.io.IOException;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.Arrays;

public final class SecondTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"demo/pipeline/Target".equals(className)) {
            return null;
        }

        byte[] resourceBytes;
        try (InputStream input = loader.getResourceAsStream(
                "demo/pipeline/Target.class")) {
            if (input == null) {
                throw new IllegalStateException("Target resource missing");
            }
            resourceBytes = input.readAllBytes();
        } catch (IOException e) {
            throw new IllegalStateException("Reading class resource failed", e);
        }

        // ISO-8859-1 ánh xạ 1:1 byte -> ký tự Unicode 0..255,
        // đủ để phát hiện chuỗi ASCII trong thí nghiệm này.
        String incoming = new String(
                classfileBuffer, StandardCharsets.ISO_8859_1);
        String resource = new String(
                resourceBytes, StandardCharsets.ISO_8859_1);

        System.out.println("[B] inputHasFROM_LIVE="
                + incoming.contains("FROM_LIVE"));
        System.out.println("[B] resourceHasFROM_DISK="
                + resource.contains("FROM_DISK"));
        System.out.println("[B] inputEqualsResource="
                + Arrays.equals(classfileBuffer, resourceBytes));

        return null;
    }
}
```

B không lấy “bản gốc từ ổ đĩa” để ghi đè mảng đầu vào. B chỉ dùng resource làm **mốc chứng minh**; giá trị đáng tin cho bước instrumentation hiện tại là `classfileBuffer`. B trả `null` để giữ nguyên kết quả đã được A áp dụng.

**Giới hạn của phép so sánh:** Trong chương trình mẫu, classpath là thư mục `out` và resource trả bytes của `out/demo/pipeline/Target.class`, nên ta biết mốc tham chiếu. Ngoài mô hình này, cùng đường dẫn resource có thể không phản ánh bytes đưa vào `defineClass`; đừng dùng cách đọc resource như một oracle chung.

### 4.6. `src/demo/pipeline/App.java`

```java
package demo.pipeline;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("[app] before Target load");

        Class<?> type = Class.forName(
                "demo.pipeline.Target",
                true,
                ClassLoader.getSystemClassLoader());

        Object result = type.getMethod("message").invoke(null);
        System.out.println("[app] Target.message=" + result);
    }
}
```

Lời gọi `Class.forName` diễn ra **sau khi** `App.main` bắt đầu. Tên đích nằm trong chuỗi, nên `App` không bắt buộc tham chiếu tĩnh tới kiểu `Target` trước khi in log. Khi JVM cần định nghĩa `Target`, hai transformer đã đăng ký nhận callback.

### 4.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.pipeline.Agent

```

JAR agent phải chứa đủ `Agent.class`, `FirstTransformer.class`, `SecondTransformer.class`. Giữ dòng trống kết thúc manifest. Không cần `Can-Retransform-Classes: true` vì thí nghiệm chỉ quan sát **lần định nghĩa mới**.

### 4.8. Biên dịch và tạo agent JAR

Đứng trong thư mục `pipeline-demo/`, dùng JDK 17+. Với Bash:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/pipeline/Agent.java \
  src/demo/pipeline/FirstTransformer.java \
  src/demo/pipeline/SecondTransformer.java \
  src/demo/pipeline/Target.java \
  src/demo/pipeline/App.java

jar --create --file pipeline-agent.jar --manifest agent.mf \
  -C out demo/pipeline/Agent.class \
  -C out demo/pipeline/FirstTransformer.class \
  -C out demo/pipeline/SecondTransformer.class
```

Với PowerShell, tạo thư mục rồi chạy lệnh một dòng (dấu `\` tiếp dòng trong Bash **không** phải cú pháp tiếp dòng của PowerShell):

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/pipeline/Agent.java src/demo/pipeline/FirstTransformer.java src/demo/pipeline/SecondTransformer.java src/demo/pipeline/Target.java src/demo/pipeline/App.java
jar --create --file pipeline-agent.jar --manifest agent.mf -C out demo/pipeline/Agent.class -C out demo/pipeline/FirstTransformer.class -C out demo/pipeline/SecondTransformer.class
```

`--release 17` bảo đảm mã/classfile nhắm API Java 17. Có thể kiểm tra nội dung JAR bằng `jar --list --file pipeline-agent.jar`; JAR agent không cần chứa `Target.class` hay `App.class` vì hai class này được nạp qua `-cp out`.

### 4.9. Chạy agent và đọc stdout

```bash
java -javaagent:pipeline-agent.jar -cp out demo.pipeline.App
```

Với đúng các file và một JVM mới không có transformer khác chỉnh `Target`, các dòng stdout do chương trình mẫu tạo ra theo thứ tự:

```text
[agent] registered A then B
[app] before Target load
[A] replaced FROM_DISK -> FROM_LIVE
[B] inputHasFROM_LIVE=true
[B] resourceHasFROM_DISK=true
[B] inputEqualsResource=false
[app] Target.message=FROM_LIVE
```

Giải thích từng mốc:

1. JVM gọi `Agent.premain`, A/B được đăng ký trước application `main`.
2. App in dòng đầu tiên rồi yêu cầu JVM định nghĩa `Target`.
3. A nhận bytes của lần định nghĩa mới, thay literal `FROM_DISK` thành `FROM_LIVE` trong **mảng sao chép**, trả bytes mới.
4. B được gọi sau A, nên `classfileBuffer` của B chứa literal `FROM_LIVE`. B lại đọc resource `Target.class` chưa bị sửa trên đĩa, vẫn chứa `FROM_DISK`. Vì thế `Arrays.equals(...)` trả `false`.
5. JVM định nghĩa `Target` từ bytes cuối cùng. Lời gọi `message()` trả `FROM_LIVE` mặc dù compiler đã ghi `FROM_DISK` trong class file trên đĩa.

**Thử đối chứng** không có startup agent:

```bash
java -cp out demo.pipeline.App
```

Stdout:

```text
[app] before Target load
[app] Target.message=FROM_DISK
```

Hai lần chạy là hai JVM mới. Agent không sửa `out/demo/pipeline/Target.class` trên đĩa; tác động nằm trong quá trình class definition. Có thể đọc file bằng `javap -v -classpath out demo.pipeline.Target` để xem string literal ban đầu, nhưng `javap` đọc artifact trên classpath, **không tự động dump bytecode đang được JVM thực thi**.

> Chương trình mẫu minh họa đúng hợp đồng với một chuỗi literal ASCII đơn giản và compiler `javac` JDK 17+. Nếu chủ động chỉnh `Target.java`, thêm bản trùng trong classpath hoặc dùng agent khác, kết quả và vị trí marker có thể thay đổi; đó là lý do ví dụ xác thực số lần xuất hiện trước khi sửa.

## 5. Khi nào bytes của transformer đầu tiên cũng khác nội dung class trên đĩa?

Ví dụ trên chứng minh **transformer B** nhận bytes khác bản resource. Ngay cả transformer **đầu tiên** cũng không nên mặc định đầu vào là “file nguyên gốc trên đĩa”:

| Nguồn định nghĩa | Tại sao so sánh trực tiếp với tệp không đáng tin |
| --- | --- |
| Custom `ClassLoader` | Loader có thể đọc bytes từ mạng, database, gói mã hóa hoặc tạo/chỉnh bytes trước khi gọi `defineClass`. |
| Runtime bytecode generation | Proxy/class sinh ra khi chạy có thể không có bản `.class` trên đĩa. |
| Class trong JAR hoặc module | Dữ liệu đến từ entry được chọn trong archive/module, không nhất thiết từ đường dẫn `out/Type.class` mà công cụ đoán. |
| Multi-release JAR | JVM có thể chọn bản entry theo phiên bản runtime; entry cấp gốc không nhất thiết là bản được nạp. |
| Nhiều classpath/module path entry | Tên class trùng nhau ở các nguồn khác nhau; **defining loader** và thứ tự tìm kiếm mới xác định nguồn được dùng. |
| Class đã redefine | Định nghĩa runtime có thể dựa vào bytes đưa vào `ClassDefinition`, không trùng bản deploy cũ. |
| Retransformation | JVM dùng bytes cơ sở của định nghĩa gần nhất và tái áp dụng các biến đổi của transformer incapable; bytes có thể khác cả bản đĩa lẫn output của lần gọi trước. |

Điểm đối chiếu quan trọng là **danh tính lớp**: trong JVM, danh tính class gắn với **tên nhị phân + defining class loader**. Hai class loader khác nhau có thể định nghĩa hai class cùng tên từ bytes khác nhau; tìm một file `com/acme/Foo.class` không bảo đảm đó là bytes của đúng class đang được transform.

Nếu bạn thật sự cần kiểm chứng provenance của class, có thể ghi lại defining loader, module, code source khi có, URL resource (chỉ dùng tham khảo), checksum bytes **ngay tại callback** và metadata build. Không đưa kết quả resource lookup thành điều kiện chắc chắn rằng mọi bytes trong `classfileBuffer` là một bản sao tệp ấy.

## 6. Retransformation: nguy cơ giả định “lần sau lại thấy bytes gốc”

`Instrumentation.retransformClasses(Class<?>...)` là tính năng riêng, có thể không được JVM/cấu hình hỗ trợ. Với class đã nạp và các transformer có khả năng retransformation khác nhau, JVM thực hiện quy tắc đặc biệt:

```text
Bytes nền của định nghĩa/lần redefine gần nhất
        |
        v
Tự tái áp dụng hiệu ứng từ transformer canRetransform=false
        |    (không gọi lại transform() của transformer false)
        v
Gọi transformer canRetransform=true
        |    (nhận bytes đã bao gồm hiệu ứng được tái áp dụng)
        v
Kiểm tra và cài đặt định nghĩa được retransform
```

Ở đây, `canRetransform=false` **không** có nghĩa hiệu ứng trước đó nhất thiết bị bỏ khi retransform. Thay vào đó JVM có thể tái sử dụng kết quả biến đổi cũ của nhóm incapable **mà không gọi lại callback**.

Ví dụ khái niệm, **không phải đoạn code chạy độc lập**:

```text
Lúc class load:
  A (false): thêm marker A vào bytes
  B (true):  nhận bytes có marker A, thêm marker B
  JVM cài đặt class đã qua A và B

Lúc retransform:
  A (false): không được gọi lại
  JVM tái áp dụng biến đổi của A từ lần load/redefine trước
  B (true):  được gọi lại, có thể nhận bytes đã có marker A
  JVM cài đặt kết quả mới
```

Trong Java 17, *initial class file bytes* dùng làm cơ sở retransform **có thể không giống byte-for-byte** bytes của `defineClass`/`redefineClasses` trước đó: constant pool có thể khác cách bố trí, thêm/bớt mục, đổi thứ tự; một số attribute có thể vắng; những cấu trúc không có ý nghĩa thứ tự có thể được hoán đổi. Vì thế **không được coi checksum hoặc offset của buffer lần load là bất biến cho mọi lần retransform**.

Một vài hệ quả:

- Transformer có hỗ trợ retransformation cần chịu được **nhiều lần callback cho cùng một class**.
- Tránh chèn cùng helper hoặc marker hai lần nếu bytes đã chứa nó; nên có kiểm tra idempotence ở **mức cấu trúc bytecode**, không chỉ so sánh với tệp trên đĩa.
- Với lớp đã được transform nhiều lần, không thể suy luận nguồn của bytes từ một lần gọi `retransformClasses` nếu không hiểu toàn bộ chuỗi transformer hiện diện.
- Retransformation và redefinition có giới hạn thay đổi schema class; không tùy ý thêm/xóa field/method hay đổi inheritance. Phải giữ định nghĩa hợp lệ cho JVM đang dùng.
- `isRetransformClassesSupported()` và `isModifiableClass(clazz)` cần được kiểm tra trước khi dựa vào khả năng xử lý lại lớp.

## 7. Redefinition: caller cung cấp bytes, không bắt buộc từ bản trên đĩa

Trong `Instrumentation.redefineClasses(ClassDefinition...)`, chương trình gọi API truyền vào **định nghĩa class mới** qua `ClassDefinition.getDefinitionClassFile()`. Bytes này có thể được tạo từ một file, tải từ nơi khác hoặc được công cụ instrumentation tạo trong bộ nhớ. Transformer được gọi theo quy tắc redefinition trước khi bytes được kiểm tra và cài đặt.

Do vậy, ngay cả transformer đầu tiên cũng phải phân tích **mảng do JVM cấp**; không mở `Foo.class` trên disk rồi mặc định đó là input. Một lần redefine có thể thay nội dung method mà không thay tệp artifact cũ, vì việc áp dụng vào runtime không tự ghi ngược lên JAR.

Các phép biến đổi trong lần redefine cũng được ghép theo chuỗi. Khi xử lý trường hợp `classBeingRedefined != null`, transformer phải bảo đảm output đáp ứng **semantics của redefinition**, nghĩa là legal replacement cho class đã tồn tại.

## 8. Cách viết transformer bền vững khi không kiểm soát toàn bộ chuỗi

1. **Lọc đúng đối tượng.** Kiểm tra `className` dạng internal name (`/`), `loader`, `module` và `classBeingRedefined` khi có ý nghĩa. Không chỉ dùng basename như `Service.class`.
2. **Phân tích chính `classfileBuffer`.** Dùng parser class file/ASM/Byte Buddy phù hợp với version, constant pool và attributes của bytes hiện tại. Không dựa vào opcode offset, thứ tự mục constant pool hoặc checksum từ artifact gốc.
3. **Không sửa buffer đầu vào.** Khi thay đổi, tạo mảng output mới rồi trả. Nếu không thay đổi, trả `null`; đừng trả một mảng rác hoặc giữ tham chiếu mutable ngoài callback để sửa sau.
4. **Kiểm tra tính hợp lệ.** Phải xử lý stack map frames, max stack, nhánh, exception handler, constant pool, descriptor và version. Một transformer phía trước có thể đã thêm mã khiến offset ban đầu không còn đúng.
5. **Idempotence.** Tìm marker/hình thái cấu trúc đang tồn tại trước khi instrument; không tăng lớp wrapper/helper vô hạn qua các lần retransform.
6. **Hợp tác với nhiều agent.** Không giả định thứ tự transform chỉ dựa vào thứ tự JVM argument; kiểm tra `canRetransform`/nhóm native/Java và thứ tự đăng ký thực tế.
7. **Đo lường phù hợp.** Nếu cần so sánh, ghi hash của **bytes được callback nhận**, hash của bytes **trả về**, class name, defining loader và loại sự kiện. Hash của resource trên disk là một loại dữ liệu riêng.
8. **Xử lý lỗi rõ ràng.** Nếu class bytes không hợp lệ, có thể ném `IllegalClassFormatException` để phục vụ logging/debugging, nhưng không dựa vào ngoại lệ để chặn mọi lần nạp lớp: JVM vẫn thử tiếp tục như khi transformer trả `null`.
9. **Giữ callback ngắn và an toàn.** Class loading có thể đồng thời trên nhiều thread. Tránh I/O nặng trong `transform`, dependency dễ gây đệ quy class load, deadlock và logger cần lớp chưa được tải.
10. **Kiểm chứng kết quả ở runtime.** Kết quả thành công là JVM chấp nhận bytes và hành vi ứng dụng đúng. Việc hash đầu vào khác hash trên đĩa **một mình** không đủ chứng minh instrumentation đúng.

### Quy trình chẩn đoán khi A và B xung đột

Một quy trình thực tế là chạy A đơn lẻ, chạy B đơn lẻ, rồi chạy cả hai với cùng JDK/classpath; log thứ tự đăng ký và loại transformer; lấy class identity tại callback; so sánh hash trước/sau từng bước; lưu bản dump **khi đã có quyền làm vậy** để kiểm tra bằng `javap -v` hoặc verifier phù hợp. Sau đó thử tải lớp mới và retransform/redefine riêng khi feature được hỗ trợ.

Nếu B chỉ hoạt động khi không có A, trước hết hãy kiểm tra xem B có phụ thuộc vào bytecode gốc, offset cố định hoặc thứ tự constant pool của file trên đĩa hay không. Thay đổi thứ tự agent có thể làm lộ lỗi nhưng không giải quyết vấn đề thiết kế nếu B vẫn giả định nguồn bytes cố định.

## 9. Những ngộ nhận và triệu chứng hay gặp

| Nhận định hoặc triệu chứng | Cách hiểu đúng |
| --- | --- |
| “`classfileBuffer` lúc nào cũng là bytes `out/Foo.class`.” | Sai. Buffer thuộc bước transform hiện tại; nguồn ban đầu là bytes JVM được yêu cầu định nghĩa/redefine/retransform. |
| “Hai transformer đều nhìn thấy cùng bản class từ đĩa.” | Sai khi transformer đứng trước trả bytes mới; transformer sau nhận kết quả trước. |
| “A trả `null` thì JVM trả lại bytes gốc trên đĩa cho B.” | Không. `null` giữ **bytes hiện tại**, có thể đã qua các transformer khác. |
| “A chạy trước nếu `-javaagent:a.jar` nằm trước B trong mọi trường hợp.” | Không đủ: còn thứ tự đăng ký và các nhóm Java/native, `canRetransform`. |
| “`getResourceAsStream` là snapshot class runtime.” | Không. Đó là resource lookup, có thể trùng hoặc khác nguồn định nghĩa. |
| “Nếu tệp không có trên đĩa thì callback không thể chạy.” | Sai. Class có thể sinh từ bytes trong bộ nhớ. |
| “`classBeingRedefined != null` nghĩa là đang nạp class mới.” | Ngược lại: đó là redefinition/retransformation cho class đã tồn tại. |
| “Retransform sẽ gọi lại mọi transformer, kể cả false.” | Không. Nhóm `canRetransform=false` không được gọi lại; hiệu ứng cũ được tái áp dụng theo quy tắc. |
| “Bytes retransform luôn byte-for-byte bằng bytes từ `defineClass` lúc đầu.” | Không. Java 17 nêu rõ có thể khác về constant pool, attribute và thứ tự một số thành phần. |
| “Sửa trực tiếp mảng `classfileBuffer` giúp tiết kiệm bộ nhớ.” | Vi phạm hợp đồng. Tạo output byte array mới. |
| “Nếu A ném exception thì class load chắc chắn dừng.” | Không. JVM đối xử tương đương A trả `null` và tiếp tục các transformer sau. |
| “`javap -v` trên JAR cho thấy bytes class đã transform trong JVM.” | Không. Nó đọc artifact được cung cấp, không tự truy cập định nghĩa class runtime đã biến đổi. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** A trả mảng `byte[]` mới có thêm đoạn ghi log; B được đăng ký sau A trong cùng nhóm. B thấy bytes nào?

**Đáp án:** B nhận bytes mới A trả về, qua tham số `classfileBuffer`. Nó không mặc định nhận bytes của bản `.class` ban đầu trên disk.

**Câu 2.** B trả `null` sau khi A đã đổi bytes. JVM có bỏ biến đổi của A không?

**Đáp án:** Không. `null` của B chỉ có nghĩa B không thay đổi gì thêm; bytes sau A vẫn là đầu vào của giai đoạn tiếp theo.

**Câu 3.** Vì sao trong bài thực hành `Target.message()` trả `FROM_LIVE` nhưng resource `Target.class` vẫn chứa `FROM_DISK`?

**Đáp án:** A đã sửa bytes trong đường định nghĩa class **ở bộ nhớ**, không ghi lại tệp. B thấy bytes sau A và JVM cài đặt class từ bytes đã transform.

**Câu 4.** Nếu một custom loader tạo bytes class trong bộ nhớ, nên lấy bản gốc trên đĩa ở đâu?

**Đáp án:** Có thể không có bản đĩa. Hãy xử lý bytes JVM thực sự chuyển qua callback và, nếu cần provenance, instrument nguồn tạo/định nghĩa class theo thiết kế của loader.

**Câu 5.** Lần đầu A đăng ký `canRetransform=false`, B đăng ký `true`. Khi gọi retransform, A có nhận callback lần nữa?

**Đáp án:** Không. JVM tái áp dụng hiệu ứng của A từ lần load/redefine trước mà không gọi A, rồi gọi B theo nhóm có thể retransformation.

**Câu 6.** Có thể tính SHA-256 của `Foo.class` trên đĩa và yêu cầu hash của `classfileBuffer` phải luôn bằng nó không?

**Đáp án:** Không. Hash trên disk đo một artifact cụ thể; hash callback đo bytes ở một điểm của chuỗi runtime. Hai đối tượng có thể hợp lệ nhưng khác nhau.

**Câu 7.** Một transformer chỉ chạy tốt khi nó là agent duy nhất. Có thể sửa bằng cách ép B luôn chạy trước A không?

**Đáp án:** Thay thứ tự có thể hữu ích để cô lập lỗi, nhưng giải pháp bền vững là làm B hiểu và xử lý đúng bytes đầu vào của **chuỗi biến đổi thực tế**, tuân thủ giới hạn cấu trúc class và kiểm chứng tương thích.

## 11. Ghi nhớ và tài liệu gốc

**Năm điểm quan trọng:**

1. `classfileBuffer` là **bytes ở bước hiện tại của pipeline**, không có bảo đảm là bản class `.class` đang nằm trên ổ đĩa.
2. Trong chuỗi, **bytes A trả về là đầu vào B nhận**; trả `null` giữ bytes hiện tại.
3. Nguồn đầu vào khác nhau giữa **class definition**, **redefinition**, **retransformation**; lớp còn có thể được tạo không qua file trên disk.
4. Retransformation có quy tắc **tái sử dụng biến đổi incapable** và bytes nền có thể thay đổi cách bố trí constant pool/attribute.
5. Viết transformer đúng nghĩa là **đọc bytes được truyền vào, không sửa mảng đầu vào, tạo bytes output hợp lệ và kiểm tra kết quả khi JVM áp dụng**.

Nguồn chuẩn Java SE 17 để tra cứu:

- [ClassFileTransformer — chaining, `classfileBuffer`, thứ tự và đầu vào cho load/redefine/retransform](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Instrumentation — addTransformer, removeTransformer, retransformClasses, redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [ClassLoader — defineClass và tài nguyên classpath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java Virtual Machine Specification, Java SE 17, §5 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)