# Lỗi nạp agent, sai chữ ký và ngoại lệ không được bắt có thể làm JVM không khởi động

> **Tình huống:** Ứng dụng Java chạy bình thường với `java App`, nhưng khi thêm `-javaagent:agent.jar` thì JVM dừng trước khi vào `App.main`. Với agent được nạp **lúc khởi động**, đây là hành vi được quy định: nếu JVM không khởi tạo được agent hoặc `premain` ném ngoại lệ chưa được bắt, **JVM phải hủy quá trình khởi động**. Một agent phục vụ quan sát vẫn chạy bên trong JVM đích và vì thế có thể trở thành điều kiện để toàn bộ ứng dụng được phép bắt đầu.

Bài này tập trung vào **điểm khởi động agent**, cách phân biệt lỗi đóng gói, sai chữ ký với lỗi thực thi, các thí nghiệm Java 17+, cách tìm nguyên nhân từ log và cách lựa chọn hành vi *fail fast* hay *degrade gracefully* một cách có chủ đích.

## 1. Điều gì xảy ra trước `main`?

Với lệnh:

~~~bash
java -javaagent:agent.jar=mode=demo App
~~~

JVM xử lý một chuỗi bước trước khi gọi `public static void main(String[] args)` của `App`:

~~~text
Launcher nhận -javaagent:agent.jar=mode=demo
  |
  v
Mở được JAR và đọc META-INF/MANIFEST.MF?
  |
  v
Tìm được thuộc tính Premain-Class?
  |
  v
Nạp/khởi tạo lớp agent và các lớp nó cần?
  |
  v
Tìm được chữ ký premain hợp lệ?
  |
  v
Gọi premain("mode=demo", Instrumentation)
  |
  +--> premain hoàn tất bình thường --> tiếp tục khởi động ứng dụng --> App.main
  |
  +--> lỗi khởi tạo / ngoại lệ không bắt --> JVM hủy khởi động
~~~

Đây là **vòng đời startup agent**. `-javaagent` yêu cầu JVM nạp agent và gọi `premain` **trước `main`**; `premain` phải trả về bình thường để tiếp tục khởi động. Nếu một bước bắt buộc không thành công, `main` có thể chưa từng được gọi, nên mọi log, health check hoặc cơ chế xử lý lỗi đặt trong `main` đều không có cơ hội chạy.

**Phân biệt ba thời điểm:**

| Thời điểm | Ví dụ lỗi | Dấu hiệu quan trọng |
| --- | --- | --- |
| Trước khi gọi `premain` | Sai đường dẫn JAR, thiếu `Premain-Class`, không tìm thấy lớp agent, sai chữ ký | Không thấy thông điệp đầu tiên từ `premain` |
| Trong `premain` | Parse cấu hình gây `IllegalArgumentException`, thiếu dependency, lỗi khởi tạo transformer, lỗi runtime không được bắt | Có thể thấy vài log agent, nhưng không thấy log `main` |
| Sau khi `premain` trả về | Ứng dụng ném ngoại lệ trong `main`; lỗi class loading/callback xảy ra về sau | `premain` đã chạy; cần truy lại stack trace xem lỗi thuộc ứng dụng hay agent |

Không nên chỉ dựa vào từ "FATAL" hoặc một mã thoát cố định để xác định lỗi; **log đầu tiên có ý nghĩa, loại exception, đường dẫn JAR và việc `main` đã bắt đầu hay chưa** mới giúp khoanh vùng.

## 2. Manifest và chữ ký `premain` phải đúng hợp đồng JVM

Một startup agent là JAR chứa **main manifest attribute** `Premain-Class` trỏ đến tên nhị phân đầy đủ của lớp agent. Ví dụ nếu lớp là `com.acme.agent.StartupAgent`, manifest phải ghi:

~~~text
Manifest-Version: 1.0
Premain-Class: com.acme.agent.StartupAgent
~~~

Giá trị sau `Premain-Class:` là **tên lớp Java**, không phải `StartupAgent.java`, đường dẫn `com/acme/agent/StartupAgent.class` hay tên JAR. Đối với agent khởi động bằng `-javaagent`, chỉ có `Main-Class` (của executable app) hoặc chỉ `Agent-Class` (của dynamic agent) **không thay thế** `Premain-Class`.

JVM thử tìm phương thức theo thứ tự sau:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

Nếu không có chữ ký hai tham số trên, JVM thử:

~~~java
public static void premain(String agentArgs)
~~~

Hai dòng trên là **chữ ký minh họa**, không phải một file Java độc lập. `Instrumentation` ở đây là `java.lang.instrument.Instrumentation`.

Các ràng buộc cần nhớ:

- Phương thức phải là **`public static void`** và tên chính xác **`premain`** (phân biệt hoa/thường).
- Thứ tự tham số của chữ ký hai đối số là **`String` rồi `Instrumentation`**; đảo thứ tự không hợp lệ.
- **`premain(String)` là hợp lệ**; việc thiếu tham số `Instrumentation` không tự nó là lỗi. Tuy nhiên, agent muốn đăng ký transformer thường cần biến thể hai tham số.
- Nếu khai báo cả hai biến thể, JVM ưu tiên **hai tham số**.
- `premain()` không tham số, `premain(Object)`, `premain(Instrumentation, String)`, instance method, private method hoặc phương thức có kiểu trả về khác `void` đều không đáp ứng hợp đồng.
- `agentArgs` là **toàn bộ chuỗi** sau dấu `=` trên `-javaagent`; JVM không tự tách `mode=demo` thành key/value.
- Lớp agent và dependency của nó phải nạp được trong cấu hình class loader/module thực tế của ứng dụng. Việc biên dịch thành công trên máy build không bảo đảm JVM đích nạp được.

**Vì sao chữ ký sai làm cả ứng dụng dừng?** JVM chưa thể xác định điểm vào agent hợp lệ, trong khi startup agent là một phần cấu hình khởi động đã được yêu cầu. Đặc tả `java.lang.instrument` quy định JVM **abort** trong trường hợp không bắt đầu được agent. Đây không phải là một exception để `App.main` tự `catch`.

## 3. Phân loại lỗi theo nguyên nhân gốc

| Nhóm | Triệu chứng thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| **JAR không tồn tại, không đọc được hoặc không phải JAR hợp lệ** | `Error opening zip file or JAR manifest missing`, `agent library failed Agent_OnLoad` hoặc thông báo tương đương | Đường dẫn tương đối/tuyệt đối, quyền đọc, loại file, file thực có trong môi trường deploy |
| **Thiếu/sai `Premain-Class`** | `Failed to find Premain-Class manifest attribute` | `META-INF/MANIFEST.MF` trong *JAR thực tế đã deploy*, vị trí main section và tên attribute |
| **Không tìm thấy lớp agent** | `ClassNotFoundException`; đôi khi `NoClassDefFoundError` do class phụ thuộc bị thiếu | Tên đầy đủ trong manifest, vị trí `.class`, gói dependency và class loader |
| **Chữ ký `premain` sai** | `NoSuchMethodException` hoặc lỗi reflect/instrumentation | `public static void`, loại và thứ tự tham số; kiểm tra bằng `javap` |
| **Nạp lớp không tương thích JVM** | `UnsupportedClassVersionError`, `LinkageError`, `IllegalAccessError` | Phiên bản Java khi biên dịch/chạy, module, dependency và cách đóng gói |
| **Ngoại lệ trong `premain`** | Stack trace có `IllegalStateException`, `ExceptionInInitializerError` hoặc wrapper `InvocationTargetException` | Điểm ném đầu tiên trong code agent; `Caused by` sâu nhất; cấu hình đầu vào |
| **Agent tự yêu cầu capability chưa hỗ trợ** | `UnsupportedOperationException` trong lời gọi `Instrumentation` hoặc khởi tạo công cụ bytecode | Manifest capability, `isRetransformClassesSupported()`, JDK/JVM đang chạy và cách agent xử lý thất bại |

**Lưu ý với `NoClassDefFoundError`:** agent class có thể tồn tại trong JAR nhưng một dependency xuất hiện trong chữ ký, static initializer hoặc thân `premain` lại không có sẵn. Vì vậy đừng sửa tên `Premain-Class` ngay khi thấy tên lớp trong log; hãy đọc toàn bộ `Caused by`.

**Lưu ý với `InvocationTargetException`:** JVM có thể dùng reflection để gọi entry point, nên lỗi gốc từ `premain` có thể nằm trong chuỗi cause bên dưới. Đừng xem wrapper là nguyên nhân cuối cùng.

**Lưu ý với lỗi class version:** ví dụ agent biên dịch cho Java 24 nhưng chạy JVM Java 17 có thể thất bại trước `premain`. Khi cần hỗ trợ Java 17+, có thể biên dịch bằng `javac --release 17` và kiểm tra cả dependency của agent, không chỉ lớp entry point.

## 4. Phòng thí nghiệm: quan sát thành công và sáu kiểu thất bại

Các ví dụ sau là chương trình **độc lập, có thể biên dịch bằng JDK 17+**. Đặt tất cả file trong cùng một thư mục rỗng. Lưu `.java` bằng UTF-8 không BOM; lưu manifest dạng văn bản và kết thúc bằng dấu xuống dòng (có thể thêm dòng trống cuối). Lệnh `javac`, `jar` và `java` chạy trên PowerShell, CMD hoặc shell Unix khi đã có JDK trong PATH.

### 4.1. Ứng dụng nhỏ để phát hiện `main` có chạy hay không

**`App.java`**

~~~java
public final class App {
    public static void main(String[] args) {
        System.out.println("APP_MAIN_REACHED");
        if (args.length > 0 && "fail".equals(args[0])) {
            throw new IllegalStateException("application failure");
        }
    }
}
~~~

In `APP_MAIN_REACHED` là bằng chứng đơn giản nhất: nếu dòng này **vắng mặt**, JVM đã dừng trước hoặc chưa tới `main`; nếu nó **có mặt**, ít nhất `main` đã bắt đầu.

### 4.2. Agent hợp lệ với chữ ký hai đối số

**`HealthyAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class HealthyAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("AGENT_READY: " + args);
    }
}
~~~

**`healthy.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: HealthyAgent
~~~

Dòng trống cuối manifest là dấu kết thúc main section theo định dạng JAR manifest; lưu file sao cho công cụ `jar` đọc được đầy đủ header.

### 4.3. Agent dùng chữ ký một đối số cũng hợp lệ

**`OneArgumentAgent.java`**

~~~java
public final class OneArgumentAgent {
    public static void premain(String args) {
        System.out.println("ONE_ARG_OK: " + args);
    }
}
~~~

**`one-arg.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: OneArgumentAgent
~~~

Ví dụ này quan trọng vì nhiều người chẩn đoán sai: không có tham số `Instrumentation` vẫn là **entry point hợp lệ**.

### 4.4. Agent có thứ tự tham số sai

**`WrongSignatureAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class WrongSignatureAgent {
    // Biên dịch được, nhưng KHÔNG phải chữ ký premain mà JVM yêu cầu.
    public static void premain(Instrumentation inst, String args) {
        System.out.println("WRONG_SIGNATURE");
    }
}
~~~

**`wrong-signature.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: WrongSignatureAgent
~~~

Đây là lỗi *runtime contract*: `javac` chấp nhận phương thức Java hợp lệ, nhưng JVM instrumentation không tìm được chữ ký `premain(String, Instrumentation)` hay `premain(String)`, nên **ứng dụng không khởi động**.

### 4.5. Agent có `premain` đúng chữ ký nhưng ném exception

**`ThrowingAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class ThrowingAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("AGENT_START");
        throw new IllegalStateException("invalid agent config");
    }
}
~~~

**`throwing.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: ThrowingAgent
~~~

`AGENT_START` có thể in ra, nhưng câu lệnh `throw` không được xử lý nên JVM hủy khởi động **trước `App.main`**. Một số JVM hiện `InvocationTargetException` hoặc stack trace nội bộ bên ngoài exception gốc; thông điệp `invalid agent config` mới là manh mối nghiệp vụ.

### 4.6. Agent chủ động vô hiệu hóa mình khi lỗi cấu hình phục hồi được

**`GracefulAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class GracefulAgent {
    public static void premain(String args, Instrumentation inst) {
        try {
            if ("bad".equals(args)) {
                throw new IllegalArgumentException("invalid agent config");
            }
            System.out.println("AGENT_READY");
        } catch (IllegalArgumentException e) {
            System.err.println("AGENT_DISABLED: " + e.getMessage());
        }
    }
}
~~~

**`graceful.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: GracefulAgent
~~~

Vì `premain` đã **bắt ngoại lệ mong đợi và trả về bình thường**, `App.main` vẫn chạy. Nhưng agent không còn bảo đảm cung cấp chức năng đo đạc: trạng thái `AGENT_DISABLED` phải được quan sát và có quy tắc xử lý phù hợp. Cách này chỉ nên dùng nếu thiếu agent **không vi phạm yêu cầu bắt buộc** của dịch vụ.

### 4.7. Hai manifest cố ý sai để thử lỗi trước `premain`

**`missing-class.mf`** trỏ đến lớp không hề được đóng gói:

~~~text
Manifest-Version: 1.0
Premain-Class: MissingAgent
~~~

**`missing-entry.mf`** hoàn toàn thiếu thuộc tính `Premain-Class`:

~~~text
Manifest-Version: 1.0
~~~

Ở dưới ta đóng gói `HealthyAgent.class` vào hai JAR này. Có class Java tồn tại **không sửa được** manifest thiếu hoặc trỏ sai class.

### 4.8. Biên dịch và tạo các JAR

Chạy lần lượt từ thư mục chứa toàn bộ file:

~~~bash
javac --release 17 App.java HealthyAgent.java OneArgumentAgent.java WrongSignatureAgent.java ThrowingAgent.java GracefulAgent.java

jar --create --file healthy-agent.jar --manifest healthy.mf HealthyAgent.class
jar --create --file one-arg-agent.jar --manifest one-arg.mf OneArgumentAgent.class
jar --create --file wrong-signature-agent.jar --manifest wrong-signature.mf WrongSignatureAgent.class
jar --create --file throwing-agent.jar --manifest throwing.mf ThrowingAgent.class
jar --create --file graceful-agent.jar --manifest graceful.mf GracefulAgent.class
jar --create --file missing-class-agent.jar --manifest missing-class.mf HealthyAgent.class
jar --create --file missing-entry-agent.jar --manifest missing-entry.mf HealthyAgent.class
~~~

Nếu lệnh `javac` hoặc `jar` thất bại, sửa lỗi build/manifest **trước khi chạy** thí nghiệm JVM. Một JAR có cả lớp và manifest hợp lệ **không cần** khai báo `Main-Class` để được dùng như một agent với `-javaagent`; `App` mới là lớp có `main`.

### 4.9. Chạy các ca thử và giải thích kết quả

**Ca A — agent tốt**

~~~bash
java -javaagent:healthy-agent.jar=ok App
~~~

**Stdout chính xác với ví dụ:**

~~~text
AGENT_READY: ok
APP_MAIN_REACHED
~~~

**Ca B — chữ ký một tham số hợp lệ**

~~~bash
java -javaagent:one-arg-agent.jar=ok App
~~~

**Stdout:**

~~~text
ONE_ARG_OK: ok
APP_MAIN_REACHED
~~~

**Ca C — chữ ký đảo tham số, ca D — ném ngoại lệ, ca E — thiếu class, ca F — thiếu manifest entry, ca G — sai đường dẫn JAR**

~~~bash
java -javaagent:wrong-signature-agent.jar App
java -javaagent:throwing-agent.jar App
java -javaagent:missing-class-agent.jar App
java -javaagent:missing-entry-agent.jar App
java -javaagent:no-such-agent.jar App
~~~

Hãy **chạy riêng từng dòng** và xem exit code, stdout và stderr của từng tiến trình. Kết quả mong đợi:

| Ca | Điều có thể thấy | `APP_MAIN_REACHED`? |
| --- | --- | --- |
| C — wrong signature | `NoSuchMethodException`, thông báo `-javaagent failed` | **Không** |
| D — uncaught exception | `AGENT_START` rồi `IllegalStateException`/wrapper và lỗi JVM startup | **Không** |
| E — missing class | `ClassNotFoundException: MissingAgent` hoặc lỗi khởi tạo agent | **Không** |
| F — missing manifest entry | `Failed to find Premain-Class manifest attribute` | **Không** |
| G — missing JAR file | Không mở được ZIP/JAR hoặc thất bại tải agent | **Không** |

Các đoạn stderr cụ thể, tên frame nội bộ, vị trí message giữa stdout/stderr và exit code **không phải hợp đồng ổn định giữa JDK/JVM/hệ điều hành**. Trên một JVM, những ca nghiêm trọng có thể hiện `FATAL ERROR in native method`; trên JVM khác thông báo sẽ khác. Kết luận ổn định là startup agent không thành công nên `main` không được gọi.

**Ca H — agent xử lý lỗi và tự tắt chức năng**

~~~bash
java -javaagent:graceful-agent.jar=bad App
~~~

Stdout:

~~~text
APP_MAIN_REACHED
~~~

Stderr:

~~~text
AGENT_DISABLED: invalid agent config
~~~

**Ca I — lỗi trong ứng dụng sau khi agent đã thành công**

~~~bash
java -javaagent:healthy-agent.jar=ok App fail
~~~

Stdout:

~~~text
AGENT_READY: ok
APP_MAIN_REACHED
~~~

Sau đó stderr có `IllegalStateException: application failure` từ `App.main`. Tiến trình có thể kết thúc lỗi, **nhưng đây không phải thất bại nạp agent**: dòng `APP_MAIN_REACHED` đã chứng minh ứng dụng bắt đầu chạy.

## 5. Quy trình debug startup agent ở môi trường thật

Khi ứng dụng chết ngay sau khi thêm `-javaagent`, kiểm tra theo thứ tự từ bên ngoài vào bên trong:

1. **Xác nhận lệnh JVM thực sự dùng** và phiên bản runtime. Trong script, container, service hoặc IDE, vị trí của `-javaagent`, đường dẫn làm việc hiện tại và JDK có thể khác terminal phát triển. Ví dụ:
   
   ~~~bash
   java -version
   java -javaagent:healthy-agent.jar=ok App
   ~~~

   Với một ứng dụng thực tế, dùng đúng command line và file agent mà deployment khởi chạy. Đường dẫn tương đối được diễn giải theo thư mục làm việc của tiến trình, không nhất thiết theo thư mục chứa ứng dụng.

2. **Kiểm tra file JAR đã deploy**, không chỉ file ở thư mục build. Dùng:
   
   ~~~bash
   jar --list --file healthy-agent.jar
   ~~~

   Kỳ vọng có `META-INF/MANIFEST.MF` và `HealthyAgent.class`. Với lớp đóng gói trong package, đường dẫn phải có dạng `com/acme/agent/StartupAgent.class`. Để xem manifest thực, có thể giải nén `META-INF/MANIFEST.MF` vào **thư mục kiểm tra riêng**, rồi đọc file:
   
   ~~~bash
   jar --extract --file healthy-agent.jar META-INF/MANIFEST.MF
   ~~~

   Kiểm tra `Premain-Class` nằm trong *main section* manifest và có tên lớp chính xác. Lệnh extract tạo file dưới thư mục hiện tại, nên hãy chạy tại thư mục kiểm tra để không ghi lên file khác.

3. **Kiểm tra method và bytecode sau biên dịch**; đừng chỉ tin nguồn Java hoặc tên file:
   
   ~~~bash
   javap -public -classpath healthy-agent.jar HealthyAgent
   ~~~

   Với ví dụ, `javap` phải liệt kê `public static void premain(java.lang.String, java.lang.instrument.Instrumentation)`. Nếu lớp thuộc package, dùng tên đầy đủ có dấu chấm. Nếu thấy sai thứ tự tham số hoặc thiếu `static`, sửa code rồi **đóng gói lại JAR mới**.

4. **Đọc root cause của stack trace**, đặc biệt `Caused by` sâu nhất. `ClassNotFoundException` có thể nghĩa là tên `Premain-Class` sai; `NoClassDefFoundError` cũng có thể xuất phát từ thư viện transitive chưa đóng gói. `UnsupportedClassVersionError` cần đối chiếu phiên bản Java. Lỗi `IllegalAccessError` hoặc `InaccessibleObjectException` có thể chỉ ra vấn đề module/readability/openness. `IllegalArgumentException` trong parser cấu hình agent thường nên được log kèm tên tùy chọn bị lỗi, không in bí mật.
5. **Tái hiện độc lập** với app tối giản như `App.java` trước, rồi thử đúng ứng dụng, JDK và cấu hình thực tế. Khi test `-javaagent`, so sánh chạy có và không có agent, và quan sát **mốc `main` đã bắt đầu**. Cẩn thận: việc thay đổi agent có thể làm lỗi ứng dụng biến mất nhưng chưa chứng minh cấu hình/bytecode agent an toàn.
6. **Đảm bảo log chẩn đoán tồn tại trước `main`**. In log ở đầu `premain` hoặc dùng logger đã được khởi tạo an toàn; đừng phụ thuộc logging framework chỉ được bootstrapped trong `main`/Spring context. Ghi rõ phiên bản agent, mode, tên tùy chọn (đã loại bỏ thông tin nhạy cảm), nguyên nhân gốc và hành vi xử lý.

**Kiểm tra trên đúng JDK đích là bắt buộc.** Lớp entry point biên dịch với `--release 17` không đủ nếu JAR lại kéo dependency được build cho Java mới hơn hoặc thư viện đòi module/quyền truy cập không có ở runtime.

## 6. Chọn chính sách lỗi: fail fast hay vô hiệu hóa agent?

Không có một câu trả lời cho mọi ứng dụng. Cần dựa vào **vai trò của agent**:

| Bối cảnh | Cách xử lý hợp lý | Hệ quả cần chấp nhận |
| --- | --- | --- |
| Agent bắt buộc để bảo đảm instrumentation cần thiết cho ứng dụng/chính sách vận hành | **Fail fast**: ném lỗi có ngữ cảnh, cho startup dừng | Dịch vụ không chạy, deployment phải báo lỗi rõ |
| Agent giám sát tùy chọn; ứng dụng vẫn đúng khi không có telemetry | **Degrade gracefully có kiểm soát**: bắt đúng lỗi phục hồi được, log `AGENT_DISABLED`, cleanup và trả về | Ứng dụng chạy nhưng mất telemetry; cần cảnh báo và phân biệt trạng thái |
| Agent đã sửa bytecode/đăng ký hook rồi mới thất bại | Ưu tiên fail fast hoặc rollback có bằng chứng; đừng trả về như thể mọi thứ bình thường | Tác dụng từng phần có thể còn tồn tại; không bảo đảm chỉ `catch` là phục hồi trạng thái |
| Lỗi không kiểm soát như `OutOfMemoryError`, lỗi JVM/class linkage nghiêm trọng | Không cố nuốt mọi `Throwable` để "cho chạy tiếp" | Tiếp tục có thể làm JVM ở trạng thái không đáng tin |

Ví dụ `GracefulAgent` phía trên chỉ bắt **`IllegalArgumentException` từ cấu hình không hợp lệ** và chưa đăng ký transformer hay sửa lớp nào. Đây là ranh giới đơn giản, phù hợp để minh họa lựa chọn vô hiệu hóa agent. Nếu triển khai thật, nên phân tách các bước khởi tạo: **validate trước → acquire/register tài nguyên → publish trạng thái ready**; khi fail giữa chừng phải thu dọn phần đã đăng ký. Không bắt bừa `Throwable` để che lỗi nặng. Trong startup agent, quy tắc hữu ích là:

~~~text
Startup agent REQUIRED:
    fail -> log nguyên nhân -> throw -> JVM không vào main

Startup agent OPTIONAL:
    fail đã dự liệu, chưa gây side-effect không thể hoàn tác
         -> cleanup + báo trạng thái disabled -> premain return
         -> ứng dụng vẫn vào main
~~~

Hai chính sách không nên bị trộn lẫn. Nếu hệ thống dùng agent cho audit/compliance mà chỉ ghi cảnh báo rồi bỏ qua lỗi, hệ thống có thể phục vụ request khi một kiểm soát bắt buộc đang thiếu. Nếu agent chỉ ghi metric tùy chọn, dừng cả dịch vụ vì một endpoint exporter tạm không truy cập được có thể là một lựa chọn quá khắt khe. Quyết định phải được mô tả rõ và kiểm thử với failure injection.

## 7. Những ngộ nhận cần tránh

- **"`premain` phải luôn có `Instrumentation`":** sai. Có cả `premain(String)`; JVM thử chữ ký hai tham số trước.
- **"`javac` compile pass chứng minh JVM sẽ gọi method":** sai. `javac` chỉ kiểm tra cú pháp/chữ ký theo ngôn ngữ Java; instrumentation entry point được tìm theo hợp đồng riêng khi chạy.
- **"Có `Main-Class` hoặc `Agent-Class` thì `-javaagent` tự hiểu":** sai. Startup agent dạng này cần `Premain-Class`.
- **"Agent khởi động lỗi thì app có thể `catch` trong `main`":** sai. `main` chưa được gọi.
- **"`premain` chỉ là code thư viện, throw không ảnh hưởng ứng dụng":** sai. Nó chạy trong JVM đích và ngoại lệ chưa bắt làm quá trình startup abort.
- **"`catch(Exception)` là đủ để luôn an toàn":** sai. Lỗi có thể phát sinh trước khi `premain` được gọi; lỗi dạng `Error` không thuộc `Exception`, và nuốt lỗi sau khi đã đăng ký hook có thể làm hệ thống ở trạng thái một phần.
- **"Lỗi nạp agent và lỗi ứng dụng trong `main` giống nhau":** sai. Hãy tìm bằng chứng `APP_MAIN_REACHED` và root cause thực sự.
- **"`agentmain` attach động cũng luôn làm JVM abort":** không đúng theo đặc tả: khi agent được yêu cầu nạp **sau khi JVM đang chạy**, lỗi `agentmain` không bắt buộc hủy JVM đích; exception không bắt có thể bị bỏ qua nhưng được log. Đây là cơ chế khác với `-javaagent`. Ngoài ra, `Launcher-Agent-Class` trong *executable JAR* cũng khởi tạo trước application main nhưng dùng chữ ký `agentmain`; **lỗi chế độ launcher này vẫn abort**, nên phải phân biệt theo **cách agent được nạp**, không chỉ tên method.

## 8. Checklist trước khi đưa startup agent vào production

- Kiểm tra JAR là artifact đúng phiên bản, đọc được và chứa `META-INF/MANIFEST.MF` cùng agent/dependency cần thiết.
- Kiểm tra `Premain-Class` và `public static void premain(String, Instrumentation)` hoặc `premain(String)` bằng `javap` và bài smoke test.
- Test **đúng runtime JDK, class loader/module, container, quyền hệ thống và startup command** mà production sử dụng; tránh giả định môi trường local giống deploy.
- Tạo test âm tính cho JAR hỏng/mất, class sai, chữ ký sai, cấu hình sai và ngoại lệ trong `premain`; xác nhận log và việc `main` có/không chạy đúng thiết kế.
- Quyết định rõ agent **required** hay **optional**. Với optional agent, ghi được trạng thái disabled và dọn tài nguyên trước khi cho ứng dụng đi tiếp.
- Tránh làm công việc chậm/chặn lâu trong `premain` (gọi mạng không timeout, chờ exporter, tìm dependency vô hạn), vì nó làm chậm hoặc treo startup trước `main`.
- Nếu dùng nhiều `-javaagent`, nhớ JVM gọi `premain` theo **thứ tự tham số trên command line**; một agent lỗi có thể chặn toàn bộ quy trình khởi động.
- Không in token, API key, credential hoặc toàn bộ options chứa dữ liệu nhạy cảm khi chẩn đoán.

**Tự kiểm tra hiểu biết:** Nếu `java App` thành công nhưng `java -javaagent:wrong-signature-agent.jar App` không xuất hiện `APP_MAIN_REACHED`, điều đầu tiên cần làm là kiểm tra **hợp đồng `premain` và manifest**, không debug business logic trong `App.main`. Nếu `APP_MAIN_REACHED` đã xuất hiện trước stack trace ứng dụng, đó là một nhánh chẩn đoán khác.

### Tài liệu chính thức

- [Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): các chế độ khởi chạy, chữ ký `premain`/`agentmain`, luật abort và manifest.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability và hoạt động của transformer.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): định dạng manifest, main section, header.
