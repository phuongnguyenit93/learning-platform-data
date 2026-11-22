# Tái hiện thiếu helper, sai module, VerifyError, ClassFormatError và LinkageError

Một Java instrumentation agent có thể trả `byte[]` từ `ClassFileTransformer.transform` mà không báo lỗi, nhưng khi JVM định nghĩa hoặc liên kết class vừa biến đổi, ứng dụng vẫn gặp `NoClassDefFoundError`, `VerifyError`, `ClassFormatError` hay `LinkageError`. Nguyên nhân không phải lúc nào cũng ở code transformer: helper có thể thiếu, sai phiên bản, nằm ngoài tầm nhìn của class loader, hoặc một named module chưa cho phép truy cập. Để chẩn đoán đúng, chúng ta cần **tái hiện từng lỗi riêng, có đối chứng chạy được**, và biết lỗi nảy sinh ở giai đoạn nào.

Bài này thuộc nhóm **Kiểm thử và chẩn đoán** trong Java Advance – instrumentation. Nó xây một phòng thí nghiệm dùng Java 17+ không cần thư viện ngoài, gồm các tình huống:

1. Thiếu helper → `NoClassDefFoundError` (thường có `ClassNotFoundException` làm cause).
2. Helper tồn tại nhưng sai method ABI → `NoSuchMethodError`.
3. Named module chưa mở cho deep reflection → `InaccessibleObjectException`.
4. Bytes classfile hỏng magic number → `ClassFormatError`.
5. Method khai báo trả `int` nhưng bytecode dùng `areturn` → `VerifyError`.
6. Một defining class loader định nghĩa lại cùng binary name → `LinkageError`.
7. Hai lỗi format/verify được tái hiện lần nữa **qua Java agent thật**, minh họa bước JVM kiểm tra output sau callback transformer.

**Tất cả các ca đã được biên dịch và chạy thực tế bằng OpenJDK 24 với `javac --release 17`**; các kết quả chính được ghi dưới đây. Loại exception và cơ chế là điều đáng học, còn tiền tố log, số dòng stack trace hoặc chi tiết thông báo có thể khác giữa JVM implementations.

**Chỉ dùng trên thư mục thử nghiệm và JVM riêng.** Các bytecode mutations dưới đây **cố ý tạo classfile không hợp lệ**; không gắn agent phá bytecode vào ứng dụng đang hoạt động hoặc dữ liệu thật. Mỗi negative test được chạy trong một JVM mới để tránh trạng thái class loading/resolution của lần trước.

## 1. Đừng gộp mọi lỗi vào một nhãn “instrumentation failed”

~~~text
Lớp nguồn / JAR / module
          |
          v
Tìm tên class trong defining loader
          |-- thiếu helper ----------> NoClassDefFoundError
          v
Parse classfile structure
          |-- magic / constant pool sai -> ClassFormatError
          v
Verify instruction + operand stack
          |-- sai loại giá trị -------> VerifyError
          v
Link / resolve symbolic references
          |-- method không tồn tại --> NoSuchMethodError
          |-- loader identity lỗi --> LinkageError
          v
Kiểm tra quyền module / reflection
          |-- private reflection bị chặn -> InaccessibleObjectException
          v
Chạy method và business logic
~~~

Đây là **bản đồ loại kiểm tra**, không phải lịch trình cứng của JVM. Theo Java Virtual Machine Specification (JVMS), JVM có thể resolve một số symbolic references sớm hoặc lười khi instruction thật sự được dùng. Lỗi link có thể đến **sau khi** class load thành công hoặc ở thời điểm nó được JVM chuẩn bị/verify. Cần ghi **giai đoạn và cause chain**, không chỉ một dòng cuối của console.

### 1.1. Hệ phân cấp lỗi rất quan trọng

~~~text
java.lang.Error
  └── LinkageError
       ├── NoClassDefFoundError
       ├── ClassFormatError
       │    └── UnsupportedClassVersionError
       ├── VerifyError
       ├── IncompatibleClassChangeError
       │    ├── NoSuchMethodError
       │    ├── NoSuchFieldError
       │    └── IllegalAccessError
       └── nhiều lỗi liên kết khác

java.lang.RuntimeException
  └── java.lang.reflect.InaccessibleObjectException
~~~

`VerifyError` và `ClassFormatError` **đều thuộc họ `LinkageError`**. Vì vậy trường hợp số 6 chủ ý dùng một **nguyên nhân khác** (define trùng class) để thể hiện `LinkageError` trực tiếp. `InaccessibleObjectException` không thuộc họ này: đó là lỗi API reflection khi không thể bật suppressed access checks.

| Lỗi | Câu hỏi cần đặt đầu tiên |
| --- | --- |
| `ClassNotFoundException` | Lệnh tìm class tường minh (ví dụ `Class.forName`) có đúng tên/loader/path không? |
| `NoClassDefFoundError` | Bytecode/loader có dependency nào không thể định nghĩa hoặc khởi tạo không? |
| `NoSuchMethodError` | Runtime helper class có **đúng owner/name/descriptor** được ghi trong caller hay không? |
| `InaccessibleObjectException` | Package thuộc named module đã **open cho module caller** chưa? |
| `ClassFormatError` | Bytes có đúng cấu trúc classfile, magic, constant pool, attributes không? |
| `VerifyError` | Operand stack, return opcode, types, control flow, stack map có hợp lệ không? |
| `LinkageError` do duplicate | Cùng loader đang cố `defineClass` cùng binary name lần hai? |

**Không nhầm checked `ClassNotFoundException` với `NoClassDefFoundError`.** Lỗi thứ hai là `Error` tại quá trình JVM cần định nghĩa hoặc resolve một class. Nó có thể mang cause là `ClassNotFoundException`, nhưng cũng có thể có nguyên nhân khác như failed class initialization. Cần đọc cả root cause.

## 2. Các tệp cho phòng thí nghiệm Java 17+

Tạo một thư mục riêng có cấu trúc:

~~~text
fault-lab/
  src/
    helper-v1/demo/helper/Probe.java
    helper-v2/demo/helper/Probe.java
    app/demo/app/Caller.java
    app/demo/app/Main.java
    fixture/demo/bytes/Target.java
    fixture/demo/bytes/Run.java
    demo.secret/module-info.java
    demo.secret/demo/secret/Secret.java
    tools/ModuleCheck.java
    tools/FaultLab.java
    agent/CorruptingAgent.java
  MANIFEST.MF

  build/             (javac tạo các thư mục đầu ra)
  mods/demo.secret/  (exploded named module)
  corrupt-agent.jar  (JAR của startup agent)
~~~

Hai tệp `Probe.java` trong `helper-v1` và `helper-v2` có **cùng binary name nhưng khác method**. Chúng chỉ dùng làm hai biến thể **không đặt cùng trên runtime classpath**. Các case khác dùng classfile fixture `demo.bytes.Target` và test harness ở hai lớp độc lập.

Đọc trước cấu trúc, rồi tạo **đúng file** theo từng mục bên dưới. Ví dụ hoàn toàn độc lập với source code của dự án hiện hữu.

## 3. Ca thiếu helper: `NoClassDefFoundError`

Đầu tiên tạo helper có phương thức static mà caller cần:

**`src/helper-v1/demo/helper/Probe.java`**

~~~java
package demo.helper;

public final class Probe {
    public static String label() {
        return "helper-ok";
    }
}
~~~

**`src/app/demo/app/Caller.java`**

~~~java
package demo.app;

public final class Caller {
    public static String call() {
        return demo.helper.Probe.label();
    }
}
~~~

**`src/app/demo/app/Main.java`**

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("RESULT=" + Caller.call());
    }
}
~~~

`Caller.class` chứa symbolic method reference tới `demo/helper/Probe.label:()Ljava/lang/String;`. Điều này tương tự bytecode do transformer chèn vào một class ứng dụng khi nó muốn gọi telemetry helper.

Lúc **compile**, ta đặt helper-v1 trên classpath để `javac` có thể resolve method. Lúc **run**, ta cố tình **bỏ helper** để tạo sai khác giữa compile-time classpath và runtime classpath.

Đối chứng chạy được:

~~~text
RESULT=helper-ok
~~~

Ca thiếu helper đã kiểm thử cho những dòng nhận diện chính:

~~~text
java.lang.NoClassDefFoundError: demo/helper/Probe
Caused by: java.lang.ClassNotFoundException: demo.helper.Probe
~~~

Đây là **trích các dòng cốt lõi** của stack trace, không phải stdout của chương trình `Main`. Trên JVM thử nghiệm, lệnh chạy sai exit code `1` và `RESULT=...` không được in.

**Liên hệ Java agent:** helper đóng gói trong agent JAR chưa chắc được defining loader của lớp đang instrument nhìn thấy. Một bootstrap class không tự tìm xuống system loader; một child/plugin loader có thể có quy tắc delegation/isolation riêng. `Instrumentation.appendToSystemClassLoaderSearch` chỉ mở rộng search của **system loader**, còn `appendToBootstrapClassLoaderSearch` là API khác. Nếu helper được đặt trong named module, còn phải xét readability/exports/opens theo kiểu truy cập.

### 3.1. Tìm thiếu JAR hay sai defining loader?

Hai tình huống có thể tạo triệu chứng giống nhau:

- Không có file `helper.jar` trong runtime environment: lỗi **packaging/classpath**.
- File có mặt, agent load được nó, nhưng loader đang định nghĩa class có lời gọi không nhìn thấy helper: lỗi **loader topology/module access**.

Đừng chỉ dùng `jar --list` để kết luận. Kết hợp thông tin location của JAR, class loader của **lớp chứa invocation**, class loader của helper nếu load được, và module objects. Không gọi `Class.forName` vào class **đang được JVM định nghĩa** ngay trong `transform` để “thử helper”: có thể gây reentrant loading hoặc class circularity.

## 4. Helper có mặt nhưng sai phiên bản ABI: `NoSuchMethodError`

**`src/helper-v2/demo/helper/Probe.java`**

~~~java
package demo.helper;

public final class Probe {
    public static String renamed() {
        return "helper-v2";
    }
}
~~~

`Caller.class` vẫn được biên dịch với helper-v1 nên chờ method `label()Ljava/lang/String;`. Nhưng khi chạy, ta chỉ cung cấp helper-v2, nơi method ấy **không tồn tại**, dù class `demo.helper.Probe` vẫn có thể load. JVM đã kiểm thử ném:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String demo.helper.Probe.label()'
~~~

**Sự khác biệt:** thiếu helper là không tìm được class; sai ABI là đã tìm được class nhưng **không tìm được method có đúng signature**. `NoSuchMethodError` là subclass của `IncompatibleClassChangeError`, rồi `LinkageError`.

Tình huống thực của instrumentation:

~~~text
Bytecode đã inject:
  invokestatic demo/helper/Probe.hit:(Ljava/lang/String;)V

Runtime helper thực tế:
  static void hit(Object event)
~~~

Đây là **mô tả bytecode/contract**, không phải source Java độc lập. Descriptor `(Ljava/lang/String;)V` **không trùng** với `(Ljava/lang/Object;)V` dù source Java có quan hệ subtype. JVM resolution dùng symbolic reference cụ thể, không chạy overload resolution như compiler Java. Nếu đổi method từ static sang instance, có thể gặp `IncompatibleClassChangeError` chứ không phải `NoSuchMethodError`. Vì vậy luôn so cả **owner, name, descriptor và opcode**.

Nếu một helper class đã được load từ v2, append v1.jar sau đó không “nóng” thay thế class cũ trong cùng loader. Test ABI phải chạy JVM mới và chỉ đưa **một phiên bản helper** vào runtime.

## 5. Sai module: quyền deep reflection khác class visibility

Tạo named module không có `exports` hay `opens`:

**`src/demo.secret/module-info.java`**

~~~java
module demo.secret {
}
~~~

**`src/demo.secret/demo/secret/Secret.java`**

~~~java
package demo.secret;

public final class Secret {
    private static String reveal() {
        return "inside";
    }
}
~~~

**`src/tools/ModuleCheck.java`**

~~~java
import java.lang.reflect.InaccessibleObjectException;

public final class ModuleCheck {
    public static void main(String[] args) throws Exception {
        Module secret = ModuleLayer.boot()
                .findModule("demo.secret").orElseThrow();
        Module caller = ModuleCheck.class.getModule();

        System.out.println("OPEN="
                + secret.isOpen("demo.secret", caller));

        Class<?> type = Class.forName("demo.secret.Secret");
        var method = type.getDeclaredMethod("reveal");

        try {
            method.setAccessible(true);
            System.out.println("REFLECT=" + method.invoke(null));
        } catch (InaccessibleObjectException ex) {
            System.out.println("REFLECT=BLOCKED");
        }
    }
}
~~~

Ở đây `ModuleCheck` nằm trên classpath nên thuộc một **unnamed module**. `Secret` nằm trong **named module** có package không open. Có thể lấy class metadata theo tên, nhưng `setAccessible(true)` để gọi private method bị chặn.

Không có quyền opens:

~~~text
OPEN=false
REFLECT=BLOCKED
~~~

Thêm đúng JVM flag:

~~~bash
--add-opens=demo.secret/demo.secret=ALL-UNNAMED
~~~

Kết quả:

~~~text
OPEN=true
REFLECT=inside
~~~

Hai bộ stdout trên đã chạy đúng với module đã resolve qua `--add-modules demo.secret`.

### 5.1. Ba khái niệm JPMS không được trộn

| Điều kiện | Cách kiểm tra | Cách cấu hình điển hình |
| --- | --- | --- |
| Module đã resolve vào layer? | `ModuleLayer.boot().findModule("demo.secret")` | `--module-path` + `--add-modules` |
| Module M có đọc N? | `M.canRead(N)` | `requires`, `--add-reads` hoặc `extraReads` |
| Package có open cho deep reflection? | `M.isOpen("pkg", caller)` | `opens`, `--add-opens` hoặc `extraOpens` |
| Public API có export? | `M.isExported("pkg", caller)` | `exports`, `--add-exports` hoặc `extraExports` |

`InaccessibleObjectException` ở `setAccessible` **khác** `IllegalAccessError` khi JVM kiểm tra quyền truy cập của symbolic reference trong bytecode. Vì vậy “sai module” không tương ứng duy nhất với một exception type. `--add-opens` xử lý deep reflection nhưng không tự tạo module còn thiếu hoặc sửa một `VerifyError`.

Một Java agent có thể dùng `Instrumentation.redefineModule(...)` để **mở rộng** các quan hệ reads/exports/opens của một module đã tồn tại, nếu `isModifiableModule` phù hợp. Đây là phép **additive**, không cho xoá quyền đã cấp; nó không resolve module mới hoặc thay classfile method body. Phải chọn package và target module hẹp để không vô tình mở quá nhiều private state.

### 5.2. Vì sao test module cần hai JVM?

Khi chạy với `--add-opens`, quyền đã được cấp ngay từ startup; nó không phải một nút toggle trong cùng tiến trình để có thể “đóng lại” sau khi test. Chạy ca CLOSED và OPEN ở **hai command java riêng**. Với `Instrumentation.redefineModule`, những read/open edges đã thêm không tự bị thu hồi chỉ vì code agent đổi cấu hình hoặc transformer bị gỡ.

## 6. Classfile format lỗi và bytecode verification lỗi là hai tầng khác nhau

JVM classfile hợp lệ bắt đầu bằng magic number:

~~~text
CA FE BA BE
~~~

Sau magic là `minor_version`, `major_version`, constant pool và các bảng fields/methods/attributes. Kiểm tra format phát hiện magic sai, length/truncation sai, constant pool/descriptor không hợp cấu trúc. Đây là vai trò của `ClassFormatError`.

Verifying đi sâu hơn: instruction operand stack phải có types đúng, branch targets hợp lệ, stack-map frames và kiểu return phải tuân verifier constraints. Đây là vai trò của `VerifyError`.

Một classfile có thể **qua format checking rồi vẫn fail verification**. Ví dụ nếu method khai báo `()I` (trả int) nhưng opcode return là `areturn` (trả reference) trong khi stack đang chứa integer, JVM từ chối bằng `VerifyError`.

### 6.1. Fixture hợp lệ trước khi làm hỏng

**`src/fixture/demo/bytes/Target.java`**

~~~java
package demo.bytes;

public final class Target {
    public static int answer() {
        return 42;
    }
}
~~~

Với `javac --release 17` trong lab, method `answer()I` chứa lệnh:

~~~text
bipush 42  -> bytes 10 2A
ireturn    -> byte  AC
~~~

Ta sẽ chỉ trong lab thay `AC` bằng `B0` (`areturn`) để tạo VerifyError. Method vẫn mang descriptor `()I`, nên có **mismatch giữa kiểu operand stack và opcode**.

Để tạo ClassFormatError, clone bytes hợp lệ rồi đổi `bytes[0]=0` làm hỏng magic. Cả hai hoạt động đều **không ghi đè** file class mà `javac` vừa tạo.

### 6.2. Tránh copy cách patch raw bytes sang production

Pattern `10 2A AC` là sự trùng khớp **đã kiểm chứng của fixture này** với `return 42;`. Trên một classfile bất kỳ, các byte ấy có thể nằm trong constant pool hoặc attributes chứ không phải code. Vì vậy test harness đếm **đúng một match**, nếu sai thì báo lỗi; không được dùng quét ba byte này như một bytecode parser.

Production transformer phải dùng thư viện đọc/xây classfile có hỗ trợ phiên bản bytecode tương ứng; preserve constant pool references, labels, exception tables, `StackMapTable`, `max_stack` và method descriptors. JVM verifier là hàng rào cuối, **không phải** công cụ thay thế cho unit tests của transformer.

## 7. LinkageError do định nghĩa trùng cùng binary name và defining loader

Một class trong JVM được định danh không chỉ bằng tên. **Binary name + defining class loader** là phần quan trọng của class identity. Hai class loaders khác nhau có thể định nghĩa các classes cùng tên (dù loader constraints có thể áp thêm giới hạn). Nhưng một loader không được **định nghĩa lại cùng tên** bằng `defineClass` lần thứ hai.

Ta chọn lỗi này để tái hiện `LinkageError` riêng biệt với các subclasses đã nói ở trên. Trong test:

~~~text
IsolatedLoader L
   |
   +-- defineClass(bytes của demo.bytes.Target) -> thành công
   |
   +-- defineClass(cùng bytes và tên)            -> LinkageError
~~~

Đây không giống việc một application class loader parent-first chọn class có sẵn của parent: tình huống đó có thể không thực hiện `defineClass` lần hai. Test cố ý gọi `defineClass` hai lần để lỗi có thể lặp lại.

### 7.1. `src/tools/FaultLab.java` — harness đầy đủ

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class FaultLab {
    static final class IsolatedLoader extends ClassLoader {
        IsolatedLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = Files.readAllBytes(Path.of(args[0]));

        byte[] malformed = valid.clone();
        malformed[0] = 0;
        try {
            new IsolatedLoader().define(malformed);
            System.out.println("FORMAT=UNEXPECTED");
        } catch (ClassFormatError expected) {
            System.out.println("FORMAT=ClassFormatError");
        }

        byte[] invalidCode = valid.clone();
        int matches = 0;
        for (int i = 0; i + 2 < invalidCode.length; i++) {
            if ((invalidCode[i] & 255) == 0x10
                    && (invalidCode[i + 1] & 255) == 0x2a
                    && (invalidCode[i + 2] & 255) == 0xac) {
                invalidCode[i + 2] = (byte) 0xb0;
                matches++;
            }
        }

        if (matches != 1) {
            throw new IllegalStateException(
                    "Expected one bipush 42;ireturn");
        }

        try {
            Class<?> invalid = new IsolatedLoader().define(invalidCode);
            invalid.getDeclaredMethod("answer");
            System.out.println("VERIFY=UNEXPECTED");
        } catch (VerifyError expected) {
            System.out.println("VERIFY=VerifyError");
        }

        IsolatedLoader loader = new IsolatedLoader();
        loader.define(valid);
        try {
            loader.define(valid);
            System.out.println("DUPLICATE=UNEXPECTED");
        } catch (LinkageError expected) {
            System.out.println("DUPLICATE=LinkageError");
        }
    }
}
~~~

**Tại sao đoạn này có thể chạy?**

- `IsolatedLoader` dùng parent là **platform class loader**, không tự lấy `demo.bytes.Target` từ application classpath của harness.
- `defineClass(null,...)` đọc binary name từ bytes nguồn thay vì suy từ tên file.
- Các mảng bị mutate đều là **clone** của `Target.class` hợp lệ. File `Target.class` vẫn nguyên vẹn trên đĩa.
- Mỗi negative test parse/verify dùng một loader mới để không bị tác động bởi class definitions hoặc verification state của ca trước.
- JVM có thể verify lúc `defineClass` hoặc muộn hơn; `invalid.getDeclaredMethod("answer")` làm test buộc JVM xử lý class đã định nghĩa thêm. Vì cả hai nằm trong khối `try`, `VerifyError` từ một trong hai bước đều được nhận đúng.
- `matches==1` là bất biến của fixture; nếu compiler sinh bytecode khác, test **fail fast** thay vì lặng lẽ tạo false positive.
- Test duplicate dùng **cùng một** loader instance để vi phạm ràng buộc class identity rõ ràng.
- Lệnh `catch` chỉ để kiểm tra **expected failures** trong lab. Không nên bắt `LinkageError` hay `VerifyError` và tiếp tục như không có gì trong ứng dụng production.

**Standard output chính xác đã kiểm chứng:**

~~~text
FORMAT=ClassFormatError
VERIFY=VerifyError
DUPLICATE=LinkageError
~~~

Ba lỗi đều **được harness chủ động bắt**, nên tiến trình exit 0 khi test đạt. Nếu xuất hiện `UNEXPECTED` hoặc `IllegalStateException`, test phải được đánh dấu FAIL dù exit code trong một nhánh khác có thể không như mong đợi.

## 8. Thực hành qua `ClassFileTransformer` thật

Trong `FaultLab`, ta gọi thẳng `ClassLoader.defineClass` trên bytes đã hỏng. Tình huống instrumentation thực tế là transformer nhận bytes hợp lệ từ JVM rồi **trả mảng bytes mới**; JVM mới kiểm tra classfile output. Ta sẽ dùng agent có filter rất hẹp theo tên lớp đích để mô phỏng điều đó.

**`src/fixture/demo/bytes/Run.java`**

~~~java
package demo.bytes;

public final class Run {
    public static void main(String[] args) {
        System.out.println("ANSWER=" + Target.answer());
    }
}
~~~

Không dùng agent, stdout:

~~~text
ANSWER=42
~~~

**`src/agent/CorruptingAgent.java`**

~~~java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class CorruptingAgent {
    public static void premain(String mode, Instrumentation inst) {
        if (!"format".equals(mode) && !"verify".equals(mode)) {
            throw new IllegalArgumentException("Select format or verify");
        }

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name,
                    Class<?> redefined, ProtectionDomain domain,
                    byte[] data) {
                if (!"demo/bytes/Target".equals(name)) {
                    return null;
                }

                byte[] out = data.clone();
                if ("format".equals(mode)) {
                    out[0] = 0;
                } else {
                    int count = 0;
                    for (int i = 0; i + 2 < out.length; i++) {
                        if ((out[i] & 255) == 0x10
                                && (out[i + 1] & 255) == 0x2a
                                && (out[i + 2] & 255) == 0xac) {
                            out[i + 2] = (byte) 0xb0;
                            count++;
                        }
                    }
                    if (count != 1) {
                        System.out.println("PATCH_SKIPPED_UNEXPECTED_PATTERN");
                        return null;
                    }
                }

                System.out.println("TRANSFORM=" + mode);
                return out;
            }
        }, false);
    }
}
~~~

Những điểm cần chú ý:

1. `premain` nhận `Instrumentation` do JVM cung cấp khi chạy `-javaagent`; app không tạo object này.
2. Filter `"demo/bytes/Target"` diễn ra **trước mọi sửa đổi**. Với các classes khác callback trả `null`.
3. `out=data.clone()` giúp không sửa trực tiếp `classfileBuffer` nguồn. Đây là thao tác tối thiểu khi muốn dựng output riêng.
4. Mode `format` phá magic; mode `verify` phá return opcode trong fixture. Cả hai là **negative tests**, không phải một kỹ thuật instrumentation hợp lệ.
5. `return out` **không đồng nghĩa JVM đã chấp nhận class**. Sau callback, JVM còn parse, verify và link.
6. Khi `return null`, transformer không thay đổi bytes ở tầng của nó. Một exception phát sinh **bên trong callback** có thể bị cơ chế `ClassFileTransformer` xử lý như không biến đổi để các transformers khác tiếp tục; đừng ném exception với giả định JVM bắt buộc fail-closed.
7. `println` trong transformer chỉ để học, không phù hợp cho high-throughput production callback; cần filter, counters và buffer nhỏ.

### 8.1. `MANIFEST.MF` cho startup agent

~~~text
Manifest-Version: 1.0
Premain-Class: agent.CorruptingAgent

~~~

Giữ newline và dòng trống kết thúc phần main section. Không dùng `Can-Retransform-Classes` vì demo chỉ sửa **lúc load mới**, không gọi `retransformClasses`.

### 8.2. Chạy ba lần bằng các tiến trình riêng

Baseline (không agent):

~~~bash
java -cp build/fixture demo.bytes.Run
~~~

Output:

~~~text
ANSWER=42
~~~

Cố ý trả classfile sai magic:

~~~bash
java -javaagent:corrupt-agent.jar=format -cp build/fixture demo.bytes.Run
~~~

Những dòng nhận diện được kiểm chứng:

~~~text
TRANSFORM=format
java.lang.ClassFormatError: Incompatible magic value ...
~~~

Cố ý trả classfile bị sai type trong method:

~~~bash
java -javaagent:corrupt-agent.jar=verify -cp build/fixture demo.bytes.Run
~~~

Những dòng nhận diện được kiểm chứng:

~~~text
TRANSFORM=verify
java.lang.VerifyError: Bad type on operand stack
~~~

Đây là **phần cốt lõi của stack trace**, không phải cam kết toàn bộ stderr nguyên văn của mọi JVM. Mỗi lệnh lỗi trả exit code `1` trong thử nghiệm, sau khi in dòng `TRANSFORM=...` từ callback.

**Ý nghĩa chẩn đoán:** `premain` có thể hoàn thành và callback có thể chạy, nhưng JVM từ chối **bytes được trả về sau đó**. Nếu một agent production in `"transform success"` trước khi JVM định nghĩa class, thông điệp ấy chỉ có nghĩa **transformer đã tạo output**, không thể đại diện cho “class đã verify/link chạy an toàn”.

## 9. Biên dịch toàn bộ fixture

Từ thư mục `fault-lab/` dùng JDK 17+:

~~~bash
javac --release 17 -d build/helper-v1 src/helper-v1/demo/helper/Probe.java
javac --release 17 -d build/helper-v2 src/helper-v2/demo/helper/Probe.java
javac --release 17 -cp build/helper-v1 -d build/app src/app/demo/app/Caller.java src/app/demo/app/Main.java
javac --release 17 -d build/fixture src/fixture/demo/bytes/Target.java src/fixture/demo/bytes/Run.java
javac --release 17 -d build/tools src/tools/FaultLab.java src/tools/ModuleCheck.java
javac --release 17 -d mods/demo.secret src/demo.secret/module-info.java src/demo.secret/demo/secret/Secret.java
javac --release 17 -d build/agent src/agent/CorruptingAgent.java
jar --create --file corrupt-agent.jar --manifest MANIFEST.MF -C build/agent .
~~~

Các lệnh dùng một dòng mỗi lệnh, chạy được trong POSIX shell hoặc Windows PowerShell. `--release 17` bảo đảm source phải phù hợp Java 17 public platform APIs và classfile target; Java 17+ compiler có hỗ trợ flag tương ứng.

Sau build:

- `build/helper-v1` chứa phiên bản `Probe.label()`.
- `build/helper-v2` chứa phiên bản **không có** `Probe.label()`.
- `build/app` chứa caller đã compile **dựa trên helper-v1**.
- `build/fixture` chứa `Target` và `Run` hợp lệ.
- `build/tools` chứa hai harness.
- `mods/demo.secret` chứa một exploded named module.
- `corrupt-agent.jar` chứa manifest và class `agent.CorruptingAgent` cùng anonymous nested class do javac sinh.

Vì compiler sinh anonymous transformer class (ví dụ `CorruptingAgent$1.class`), đóng gói bằng `-C build/agent .` sẽ mang theo cả class phụ. Nếu chỉ đóng gói class chính, JVM có thể gặp `NoClassDefFoundError` do nested class bị thiếu, không liên quan bytecode mutation của Target.

### 9.1. Windows: ba ca helper

Trên Windows, classpath separator là **`;`**:

~~~powershell
java -cp "build/app;build/helper-v1" demo.app.Main
java -cp build/app demo.app.Main
java -cp "build/app;build/helper-v2" demo.app.Main
~~~

- Lệnh 1: `RESULT=helper-ok`, exit `0`.
- Lệnh 2: `NoClassDefFoundError: demo/helper/Probe` và cause `ClassNotFoundException`, exit `1` trong JVM đã thử.
- Lệnh 3: `NoSuchMethodError` cho `Probe.label()`, exit `1`.

### 9.2. Linux/macOS: ba ca helper

Classpath separator là **`:`**:

~~~bash
java -cp "build/app:build/helper-v1" demo.app.Main
java -cp build/app demo.app.Main
java -cp "build/app:build/helper-v2" demo.app.Main
~~~

Không thay đổi thứ tự flags hay đổi thành “đặt cả helper-v1 và helper-v2 vào classpath”. Khi có hai class trùng binary name, runtime có thể chọn một phiên bản theo thứ tự tìm class, làm test không còn đo đúng ABI mismatch.

### 9.3. Harness bytecode và module

~~~bash
java -cp build/tools FaultLab build/fixture/demo/bytes/Target.class
java --module-path mods --add-modules demo.secret -cp build/tools ModuleCheck
java --module-path mods --add-modules demo.secret "--add-opens=demo.secret/demo.secret=ALL-UNNAMED" -cp build/tools ModuleCheck
~~~

Output tương ứng đã kiểm chứng:

~~~text
# FaultLab
FORMAT=ClassFormatError
VERIFY=VerifyError
DUPLICATE=LinkageError

# ModuleCheck không opens
OPEN=false
REFLECT=BLOCKED

# ModuleCheck có opens
OPEN=true
REFLECT=inside
~~~

Những dòng bắt đầu bằng `#` ở khối trên là **chú thích để tách ba lượt chạy**, không phải stdout do chương trình Java in. Mỗi command được chạy một lần trong một JVM mới.

Trên Windows PowerShell, giữ trọn `"--add-opens=..."` trong dấu quote để nó là một JVM argument. Đặt flag **trước** tên class `ModuleCheck`, vì phần nằm sau tên class là args của application, không còn là launcher options.

## 10. Những công cụ chuẩn để phân loại lỗi

| Công cụ / phép kiểm | Dùng để làm gì | Không chứng minh điều gì |
| --- | --- | --- |
| `jar --list --file some.jar` | Xem JAR có class/helper nào | Không chứng minh defining loader nhìn thấy nó |
| `javap -c -p Target.class` | Xem instruction như `bipush`, `ireturn` | Không verify output đã bị agent sửa lúc runtime |
| `javap -verbose Target.class` | Major/minor, constant pool, attributes | Không xác nhận đúng module access |
| `java -Xverify:all` | Bật kiểm tra bytecode mạnh hơn | Không sửa lỗi helper thiếu hay ABI mismatch |
| `java "-Xlog:class+load=info"` | Theo dõi nguồn class loading trên HotSpot | Không tự chỉ ra mọi lớp bị agent transform |
| `Class.getClassLoader()` | Biết defining loader của class đã load | Không thay thế kiểm tra module graph |
| `Class.getModule()` | Biết module object chứa class | Không tự cho phép reflection vào private |
| `Module.isOpen(pkg, caller)` | Quyền deep reflection của package tới caller | Không đảm bảo class/method tồn tại |
| `Module.canRead(other)` | Readability edge | Không đảm bảo package được export/open |
| `Throwable.getCause()` | Theo root cause | Không chắc mọi error có cause |
| `$LASTEXITCODE` / `echo $?` | Trạng thái tiến trình vừa chạy | Không đủ với harness tự catch expected error |

Kiểm tra classfile gốc:

~~~bash
javap -c -p build/fixture/demo/bytes/Target.class
javap -verbose build/fixture/demo/bytes/Target.class
java -Xverify:all -cp build/fixture demo.bytes.Run
~~~

Dùng HotSpot class-load logging khi có nhu cầu:

~~~bash
java "-Xlog:class+load=info" -cp build/fixture demo.bytes.Run
~~~

Nếu thư viện bytecode có API `verify` riêng, nên dùng để phát hiện lỗi sớm trước khi trả bytes mới, nhưng JVM vẫn là nơi quyết định cuối cùng về việc định nghĩa class trong runtime cụ thể. Đừng log toàn bộ classfile bytes/constant pool ở production; chúng có thể chứa literals, tên class hoặc dữ liệu cần bảo vệ.

### 10.1. Ba nhóm dữ liệu nên thu cho một lỗi

**Về target:** internal class name, method name và descriptor, classfile major/minor, phase load/redefine/retransform.

**Về runtime:** Java version, defining loader (một ID nhỏ đủ phân biệt), module name, target package, helper location/version, trạng thái module reads/exports/opens.

**Về failure:** exception class chính xác, cause chain, failed symbolic reference, bytecode/toolkit version và transform stage đã tạo output. Có thể thêm hash artifact để đối chiếu, nhưng không lấy hash làm bằng chứng duy nhất của class version khi JVM retransformation có thể tái cấu trúc constant pool.

Không giữ strong references tới `ClassLoader`, `Class<?>` hoặc toàn bộ mảng `classfileBuffer` trong caches không giới hạn; làm vậy có thể cản class unloading và tăng native/heap memory.

## 11. Vì sao cùng tên lỗi có thể có nguyên nhân khác?

### 11.1. `NoClassDefFoundError` không luôn là thiếu file

Ngoài thiếu helper JAR, một class có thể không định nghĩa/khởi tạo được do lỗi ở dependency hoặc static initializer trước đó. Những lần dùng lại class có thể tạo `NoClassDefFoundError: Could not initialize class ...` với cause phù hợp. Xem thông điệp và chuỗi lỗi đầy đủ; đừng luôn khuyến nghị “copy thêm JAR”.

### 11.2. `VerifyError` không chỉ do return opcode

Lỗi verifier có thể do stack height/type mismatch, invoke sai operand types, branch vào vị trí không hợp lệ, uninitialized `this` trong constructor, hoặc `StackMapTable` không đúng sau khi chèn instructions. Bài chọn return opcode vì dễ tái hiện; production patch phải bảo toàn mọi bất biến của method.

### 11.3. `ClassFormatError` không chỉ do magic number

Một class có magic hợp lệ nhưng sai constant pool, attribute lengths, descriptors hoặc bị cắt mất phần cuối vẫn có thể fail format. Ngược lại, một classfile format hợp lệ vẫn có thể fail verifier hoặc link tới helper. Không sửa lỗi bằng cách “đổi 4 byte đầu thành `CAFEBABE`”; phải sửa **cấu trúc gốc hoặc phép biến đổi gây hỏng nó**.

### 11.4. `LinkageError` do loader constraints khác duplicate define

Ví dụ loader A và loader B có thể nạp hai lớp cùng tên độc lập, nhưng một symbolic reference hoặc method signature có thể áp đặt ràng buộc loader identity. Khi vi phạm, JVM cũng có thể ném `LinkageError`. Do đó test duplicate trong bài là **một cơ chế rõ ràng**, không phải toàn bộ lý do LinkageError có thể xuất hiện.

### 11.5. Thời điểm phát sinh có thể muộn

Một injected helper invocation ở nhánh hiếm có thể **chưa được resolve** trong startup smoke test. Ứng dụng chạy vài phút rồi mới đi vào method path chứa probe và báo `NoSuchMethodError`. Cần integration tests trên nhánh bình thường, exception, concurrency, constructors và các nhánh có điều kiện; không chỉ dựa `java -version` và app startup.

## 12. Thiết kế test/rollback phù hợp instrumentation

### 12.1. Tách test của agent khỏi test của ứng dụng

Một chiến lược tốt gồm bốn lớp:

1. **Unit tests của selector:** xác định đúng class/method/descriptor, không instrument helper của chính agent.
2. **Bytecode tests:** parser nhận classfile version, code transform giữ original instruction, output verify thành công, idempotence qua nhiều lần transform.
3. **Loader/module integration:** app có custom loader, bootstrap/system helper, module exports/opens và helper ABI đúng.
4. **End-to-end behavior:** kết quả nghiệp vụ không đổi với hook best-effort, chi phí latency/CPU/GC chấp nhận được, telemetry exporter lỗi không làm sập request.

Các ca cố ý gây `VerifyError` và `ClassFormatError` chỉ nên ở **negative tests riêng**, tuyệt đối không gộp vào agent phát hành. Lệnh `-javaagent:corrupt-agent.jar=format`/`verify` trong bài là công cụ gây lỗi có kiểm soát, không phải "profile" hay "debug flag" cho production.

### 12.2. Những giới hạn khi redefine/retransform

`retransformClasses` và `redefineClasses` có constraints về class modifiability và schema. Một classfile hợp lệ khi load mới có thể không hợp lệ khi redefine vì thêm method/field hoặc đổi hierarchy. Ngược lại, `ClassFileTransformer` có thể trả `null` ở một lượt để giữ bytes của tầng ấy, nhưng không tự hoàn tác những biến đổi từ transformer khác trong pipeline.

Quy trình test cho agent có retransform:

~~~text
Load baseline
   |
   v
Instrument lần đầu -> verify -> link helper -> chạy behavior
   |
   v
Retransform lần 1 -> verify -> đếm hook
   |
   v
Retransform lần 2 -> verify -> không nhân đôi hook
   |
   v
Redefine hợp lệ (nếu hỗ trợ) -> verify -> behavior
   |
   v
Retransform sau redefine -> kiểm tra baseline và telemetry
~~~

Không tái hiện các classfile hỏng trên JVM có production transactions. Hãy bật đúng capability, dùng class giả và có timeout/watchdog vì native/bytecode bugs có thể khiến process kết thúc bất thường.

### 12.3. Khi nào chọn fail-open hay fail-closed?

Nếu instrumentation chỉ dùng để thu optional telemetry, bỏ qua một class chưa hỗ trợ có thể được chấp nhận theo hợp đồng sản phẩm: transformer trả `null`, đồng thời tăng một counter/drop metric ở kênh an toàn. Nhưng nếu instrumentation dùng cho **security enforcement** hoặc audit bắt buộc, âm thầm trả `null` và báo “success” là nguy hiểm. Phải có chính sách fail/rollback rõ ở startup/deployment hoặc policy layer, không coi exception trong transformer là công cụ bảo đảm JVM phải từ chối mọi class.

Một nguyên tắc chung: **đừng làm giảm tính đúng đắn của ứng dụng để giữ telemetry**. Helper nên không throw trên đường hot path hoặc có cơ chế cô lập lỗi thích hợp, không có I/O/blocking không giới hạn.

## 13. Ma trận test đã xác minh

| Ca | Kích hoạt | Dấu hiệu chính | Kỳ vọng |
| --- | --- | --- | --- |
| Helper chuẩn | Runtime dùng helper-v1 | `RESULT=helper-ok` | Exit 0 |
| Helper thiếu | Chỉ có `build/app` | `NoClassDefFoundError`, cause `ClassNotFoundException` | Negative pass |
| Helper sai ABI | Runtime dùng helper-v2 | `NoSuchMethodError` | Negative pass |
| Module bị chặn | Không có `--add-opens` | `OPEN=false`, `REFLECT=BLOCKED` | Negative pass |
| Module được mở | Có `--add-opens` | `OPEN=true`, `REFLECT=inside` | Exit 0 |
| Classfile format | Magic byte đầu bị đổi | `FORMAT=ClassFormatError` | Harness ghi đúng |
| Bytecode verify | `ireturn` bị thay bằng `areturn` | `VERIFY=VerifyError` | Harness ghi đúng |
| Loader duplicate | `defineClass` hai lần cùng loader | `DUPLICATE=LinkageError` | Harness ghi đúng |
| App fixture chuẩn | Không nạp agent gây lỗi | `ANSWER=42` | Exit 0 |
| Transformer format | `-javaagent:corrupt-agent.jar=format` | `TRANSFORM=format` rồi ClassFormatError | Exit khác 0 |
| Transformer verify | `-javaagent:corrupt-agent.jar=verify` | `TRANSFORM=verify` rồi VerifyError | Exit khác 0 |

Những negative tests có uncaught Error nên tiến trình lỗi **thường** có exit code khác 0; `FaultLab` bắt Error để in kết quả, nên exit 0 khi đúng. Hãy assert cả **type/dấu hiệu error** và trạng thái chương trình, đừng chỉ dựa vào một cách.

## 14. Những sai lầm phổ biến

1. **“LinkageError chỉ là lỗi thứ sáu, hoàn toàn khác VerifyError.”** Sai: VerifyError và ClassFormatError là subclasses của LinkageError.
2. **“Có ClassNotFoundException và NoClassDefFoundError là hai lỗi độc lập.”** Có thể chúng cùng một cause chain.
3. **“Transformer trả bytes thành công nên class phải load được.”** JVM vẫn cần parse/verify/link.
4. **“Agent load được helper nên bootstrap/plugin class cũng load được.”** Không: phải kiểm tra loader của target.
5. **“Có JAR helper là đủ.”** Method name/descriptor, static/instance kind và dependency ABI có thể sai.
6. **“--add-opens giải quyết mọi vấn đề module.”** Không: module resolution, readability và public exports khác với deep reflection.
7. **“ClassFormatError là bytecode stack sai.”** Đó thường là VerifyError; ClassFormatError nói về format.
8. **“VerifyError chỉ cần disable verifier.”** Không: phải sửa bytecode transform.
9. **“Quét vài byte trong classfile là parser.”** Không: pattern hack chỉ dành cho fixture đã đếm match.
10. **“Hai loaders định nghĩa cùng tên luôn lỗi.”** Không mặc định; duplicate lỗi khi **cùng defining loader** cố define tên đã có.
11. **“Trả null sẽ undo mọi transformer trước.”** Null chỉ không thay output ở tầng hiện tại.
12. **“Throw trong callback chắc chắn fail-closed.”** Contract ClassFileTransformer không hứa như vậy.
13. **“Chỉ test startup là đủ.”** Linking helper có thể xảy ra muộn khi call site được dùng.
14. **“Catching Throwable rồi tiếp tục là cách phục hồi VerifyError.”** Che giấu lỗi correctness nghiêm trọng.
15. **“Đưa cả helper-v1 và helper-v2 lên classpath sẽ test được ABI mismatch.”** Runtime có thể chọn bản khác do ordering.
16. **“Bật opens cho ALL-UNNAMED là least privilege trong mọi ca.”** Nên cấp đúng module caller khi có thể.
17. **“Lỗi module có thể chữa bằng hỏng magic.”** Format, module và linkage là những tầng khác nhau.
18. **“Log toàn bộ class bytes luôn tốt cho debug.”** Có rủi ro lộ dữ liệu và giữ bộ nhớ không giới hạn.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `ClassFileTransformer.transform` trả `byte[]` không đủ để chứng minh JVM đã define class thành công?
2. Khi JVM nói `NoClassDefFoundError: demo/helper/Probe`, bạn kiểm tra loader nào trước?
3. Nếu `Probe` có mặt nhưng method `label()` không còn, lỗi nào phù hợp?
4. Vì sao signature `label()Ljava/lang/String;` khác `label()Ljava/lang/Object;` dù cùng tên method?
5. `InaccessibleObjectException` thuộc `LinkageError` hay `RuntimeException`?
6. Vì sao `--add-modules demo.secret` cần có trước khi module được tìm trong boot layer, còn `--add-opens` giải quyết chuyện khác?
7. Method private của named module sẽ gọi được từ unnamed app khi nào?
8. Lỗi magic number có phải lỗi verifier opcode không?
9. Vì sao `bipush 42; areturn` là sai trong method descriptor `()I`?
10. Tại sao phải kiểm tra số match của byte pattern bằng đúng 1?
11. Vì sao hai `defineClass` trên **cùng loader** dẫn tới LinkageError?
12. Một classloader khác có thể định nghĩa class có cùng binary name không?
13. Callback in `TRANSFORM=verify` rồi JVM báo VerifyError chứng minh điều gì?
14. Nếu `return null` trong transformer, liệu mọi biến đổi của transformer trước đã bị xóa không?
15. Vì sao đọc stack trace cần phân biệt stdout, stderr và exit code?
16. Cần thêm test nào nếu helper chỉ được gọi trên nhánh exception hiếm?
17. `java -Xverify:all` có sửa được helper thiếu hoặc package chưa opens không?
18. `Instrumentation.redefineModule` có chữa ClassFormatError không?
19. Vì sao `NoClassDefFoundError` đôi khi liên quan static initialization chứ không chỉ thiếu JAR?
20. Khi nào một lỗi transform optional có thể skip, và khi nào cần fail policy rõ?

## 16. Checklist xử lý lỗi ở ứng dụng thật

1. Chạy baseline không instrumentation và ghi nhận output/behavior.
2. Phân loại chính xác error class và tìm **root cause**.
3. Xác minh target class/method internal name và descriptor đã chọn đúng.
4. Xem defining loader của target, search path/loader của helper và các package/module rules.
5. Kiểm tra helper ABI, nested dependencies và version thực sự được load.
6. Nếu sai module, tách resolution, readability, exports, opens; chỉ mở phạm vi cần thiết.
7. Nếu `ClassFormatError`, kiểm tra input/output classfile structure, version và attributes.
8. Nếu `VerifyError`, kiểm tra operand stack, frames, return type, branches, exception handlers.
9. Nếu `LinkageError`, kiểm tra binary name, defining loader, duplicate definitions và constraints.
10. Test từng ca trong một JVM mới, không giữ class-load failure state giữa các negative fixtures.
11. Với output transformer, verify trước khi phát hành; không đẩy bytes cố ý sai vào production.
12. Chạy integration trên JVM versions và loaders/modules thực tế, kể cả nhánh hiếm.
13. Không log quá nhiều hoặc gây classloading recursion bên trong callback.
14. Có cơ chế bỏ qua/rollback với telemetry optional và chiến lược fail rõ khi instrumentation bắt buộc.
15. Duy trì regression tests cho nguyên nhân đã sửa, tránh tái xuất hiện khi nâng JDK/toolkit.

## 17. Kết luận

Tái hiện riêng từng lỗi giúp xác định **đúng tầng cần sửa**: thiếu helper thuộc đường tìm class; sai ABI thuộc symbolic reference; sai module thuộc quyền truy cập; ClassFormatError thuộc cấu trúc file; VerifyError thuộc bytecode type-safety; LinkageError có thể xuất hiện do loader identity hoặc ABI constraints.

**Điểm then chốt cho Java instrumentation:** callback đã chạy không có nghĩa class đã được JVM chấp nhận. JVM vẫn parse, verify, resolve, link và kiểm tra access với output do transformer tạo. Một bộ negative tests chạy trong JVM cách ly, có đối chứng, có expected exception và có kiểm tra loader/module/bytecode là cách đáng tin để chứng minh agent **không làm hỏng tính đúng đắn của ứng dụng**.

### Tài liệu chính thức

- [Oracle Java 17 – LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): cây subclasses.
- [Oracle Java 17 – NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): dependency class không tìm/định nghĩa được.
- [Oracle Java 17 – NoSuchMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html): runtime method ABI mismatch.
- [Oracle Java 17 – ClassFormatError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html): lỗi classfile structure.
- [Oracle Java 17 – VerifyError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html): bytecode verification.
- [Oracle Java 17 – InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi deep reflection access.
- [JVMS 17 – Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile magic, format và verification.
- [JVMS 17 – Loading, Linking, Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loader identity, verification, resolution timing.
- [Oracle Java 17 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer contract và output.
- [Oracle Java 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--add-modules`, `--add-opens`, `-Xverify:all`, classload logging.
