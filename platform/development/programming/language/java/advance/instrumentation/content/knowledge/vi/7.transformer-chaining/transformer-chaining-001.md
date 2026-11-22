# `addTransformer` với `canRetransform = false` hoặc `true`: hiểu đúng chuỗi biến đổi bytecode

Trong Java Instrumentation, một agent đăng ký `ClassFileTransformer` để JVM cho phép quan sát hoặc thay đổi bytes của class trong lúc **class được định nghĩa, được redefine hoặc được retransform**. Tham số thứ hai của `Instrumentation.addTransformer(transformer, canRetransform)` quyết định transformer đó có được **gọi lại trong các lần retransformation** hay không.

Điểm quan trọng nhất của bài:

- `canRetransform = false`: transformer vẫn chạy khi class được **load** hoặc **redefine**. Khi `retransformClasses(...)`, JVM **không gọi lại** transformer này mà **tái sử dụng kết quả biến đổi của lần load/redefine trước đó**.
- `canRetransform = true`: transformer chạy khi class được **load**, **redefine** và được **gọi lại** khi class được **retransform**.
- Giá trị `true` chỉ hợp lệ nếu cấu hình agent/JVM hỗ trợ retransformation; **`addTransformer(..., true)` không tự cấp capability**.
- Cả hai loại nằm trong **một transformation chain**, có thứ tự nhóm rõ ràng. Giá trị `false` **không đồng nghĩa với “không thể instrument”**.

Sau bài học, bạn có thể chọn overload `addTransformer` đúng mục đích, dự đoán transformer nào được gọi lại, đọc input/output của chuỗi biến đổi và kiểm chứng hành vi qua chương trình Java 17+.

## 1. Hai overload của `Instrumentation.addTransformer`

API thuộc module `java.instrument`:

~~~java
void addTransformer(ClassFileTransformer transformer);

void addTransformer(
        ClassFileTransformer transformer,
        boolean canRetransform);
~~~

Overload một tham số **tương đương**:

~~~java
inst.addTransformer(transformer, false);
~~~

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `transformer` | Đối tượng triển khai `java.lang.instrument.ClassFileTransformer`; JVM gọi phương thức `transform(...)` của đối tượng đó |
| `canRetransform` | Transformer có thuộc nhóm **retransformation capable** hay không |

`addTransformer` **đăng ký callback** vào cơ chế instrumentation của JVM. Đây không phải lời gọi biến đổi một class cụ thể ngay tại thời điểm đăng ký. Các class được JVM xử lý sau đó sẽ đi qua chain theo điều kiện của mỗi hoạt động; lớp đã load trước khi đăng ký **không tự động được xử lý lại**.

Hai nhóm transformer:

- **Retransformation incapable**: đăng ký bằng `false` hoặc overload một tham số.
- **Retransformation capable**: đăng ký bằng `true`.

Tên nhóm *incapable* dễ gây hiểu nhầm: nghĩa là **không được gọi lại khi retransform**, chứ không có nghĩa không thể tạo một biến đổi bytecode ở thời điểm load/redefine.

## 2. Khi nào `transform(...)` được gọi?

| Hoạt động JVM | `addTransformer(t, false)` | `addTransformer(t, true)` |
|---|---|---|
| Định nghĩa class mới (`ClassLoader.defineClass` hoặc tương đương) | **Gọi `transform`** | **Gọi `transform`** |
| `Instrumentation.redefineClasses(...)` | **Gọi `transform`** | **Gọi `transform`** |
| `Instrumentation.retransformClasses(...)` | **Không gọi lại; tái sử dụng hiệu ứng của lần load/redefine gần nhất** | **Gọi lại `transform`** |
| Chạy method bình thường, không có hoạt động định nghĩa/redefine/retransform class | Không | Không |

Các transformer không nhất thiết nhận **mọi** class phụ trợ: đặc tả `Instrumentation.addTransformer` có ngoại lệ cho định nghĩa của những lớp mà transformer đã đăng ký đang phụ thuộc vào, để tránh vấn đề vòng lặp khởi tạo. Trong thực tế nên filter bằng `className` và tránh dùng logger/phụ thuộc phức tạp bên trong `transform`.

### Phân biệt redefinition và retransformation

- **Redefinition**: agent truyền **một bộ bytes mới** cho lớp đã tải bằng `redefineClasses(new ClassDefinition(clazz, bytes))`. Cả transformer `false` và `true` được gọi trong quy trình này.
- **Retransformation**: agent gọi `retransformClasses(clazz)` để JVM bắt đầu lại từ **initial class file bytes** tương ứng, phát lại tác dụng của các transformer `false`, rồi gọi các transformer `true` để tính kết quả mới. *Initial bytes* có thể là định nghĩa mới nhất từ `redefineClasses`, và không bắt buộc giống nguyên byte từng vị trí với bản đã chuyển trước đó (chẳng hạn layout constant pool có thể thay đổi).

`canRetransform` là thuộc tính của **registration transformer**, không phải nhãn gắn vĩnh viễn lên class. Cùng một class có thể đã đi qua nhiều transformer thuộc cả hai nhóm.

## 3. `false`: callback không chạy lại nhưng hiệu ứng cũ vẫn được tái áp dụng

Giả sử một class ban đầu có bytecode `B0` và agent đăng ký:

~~~java
inst.addTransformer(transformerA, false);
~~~

Ở lần load đầu tiên, `transformerA` nhận `B0` và trả bytes `B1`. Khi sau đó class được retransform, JVM **không gọi `transformerA.transform(...)` thêm lần nữa**. Thay vào đó JVM tái sử dụng hiệu ứng biến đổi trước, tương đương việc đưa `B1` vào bước tiếp theo của chain.

~~~text
Lần load ban đầu:
B0 ── A(false).transform(...) ──> B1

Lần retransform tiếp theo:
B0 ── [áp dụng lại kết quả A đã lưu, KHÔNG gọi A] ──> B1
~~~

Điều này giữ tác dụng của một transformer `false` qua các lần retransformation, ngay cả khi transformer đó không được kích hoạt lại. **Không** được giải thích `false` là “mất mọi biến đổi của A sau khi retransform”.

Nếu transformer trả `null` tại lần load, bước của nó **không thay đổi bytes**. Khi retransform, kết quả “không đổi” đó được xem như tác dụng cũ của transformer.

Một transformer false có thể là công cụ áp dụng các thay đổi **cố định ở lần load đầu**. Việc không gọi lại tránh tính toán hoặc side effect lặp lại trong những lần retransform do agent khác khởi xướng.

## 4. `true`: callback chạy lại trong retransformation

Giả sử agent đăng ký thêm:

~~~java
inst.addTransformer(transformerB, true);
~~~

Lần load:

~~~text
B0 ── A(false) ──> B1 ── B(true) ──> B2
~~~

Khi `retransformClasses(Target.class)` được gọi:

~~~text
B0 ── [tái áp dụng kết quả A đã lưu] ──> B1
                                         │
                                         └── B(true).transform(...) ──> B3
~~~

`B(true)` **nhận input đã bao gồm hiệu ứng A** và có thể trả `B3` khác `B2`, ví dụ vì cấu hình instrumentation của B đã đổi. Chính sự khác biệt này làm `true` phù hợp với transformer cần áp dụng lại các quy tắc theo cấu hình mới.

Tuy nhiên, `true` **không tự làm JVM gọi lại transformer vào mọi thời điểm**. Phải có một **yêu cầu retransformation thật** (`retransformClasses`) hoặc một hoạt động load/redefine class. Đăng ký `true` xong rồi tiếp tục gọi method như thường sẽ **không** gây một vòng callback mới.

`true` cũng **không** có nghĩa transformer được phép thay bất kỳ cấu trúc class nào. Bytes trả về vẫn phải hợp lệ về class file và tuân thủ giới hạn redefinition/retransformation (chẳng hạn không tùy tiện thêm/bớt method hoặc field).

## 5. Capability JVM: điều kiện để đăng ký `true`

Để dùng retransformation, agent thường khai báo trong **main section** của manifest của JAR được nạp làm agent:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: true

~~~

`Can-Retransform-Classes` là yêu cầu capability:

1. Thuộc tính là tùy chọn, **mặc định `false`** khi không khai báo.
2. `true` yêu cầu retransformation, nhưng chỉ thành công khi JVM **có hỗ trợ và cho phép capability đó**.
3. `Instrumentation.isRetransformClassesSupported()` trả về trạng thái hỗ trợ trong cấu hình JVM hiện tại; nhiều lời gọi trên cùng một JVM trả cùng kết quả.
4. Nếu phương thức trên trả `false`, `addTransformer(t, true)` **ném `UnsupportedOperationException`**. Đăng ký `addTransformer(t, false)` vẫn được phép và có thể hữu ích cho load/redefine.
5. Không nhầm `Can-Retransform-Classes` với `Can-Redefine-Classes`. Hai thuộc tính cấp **hai capability riêng**.

Để tránh lỗi:

~~~java
if (inst.isRetransformClassesSupported()) {
    inst.addTransformer(transformer, true);
} else {
    inst.addTransformer(transformer, false);
}
~~~

Đây là **đoạn minh họa** đặt trong callback agent nơi đã có `Instrumentation inst` và `ClassFileTransformer transformer`. Nhánh `else` không biến một transformer false thành transformer có thể tham gia callback retransform; nó chỉ cho phép quan sát các lần load/redefine phù hợp.

`isRetransformClassesSupported()` kiểm tra **capability JVM**, không phải khả năng sửa một class cụ thể. Trước khi yêu cầu `retransformClasses(Target.class)`, còn nên kiểm tra `inst.isModifiableClass(Target.class)`. Cả hai điều kiện cần đều đúng vẫn chưa đủ để bảo đảm bytes mới hợp lệ.

## 6. Thứ tự thực thi khi có nhiều transformer

JVM **không** đơn giản gọi mọi transformer theo thứ tự đăng ký toàn cục. `ClassFileTransformer` đặc tả thứ tự **bốn nhóm**:

1. **Java transformer không hỗ trợ retransform (`false`)**.
2. **Native transformer không hỗ trợ retransform** (qua JVMTI `ClassFileLoadHook`).
3. **Java transformer hỗ trợ retransform (`true`)**.
4. **Native transformer hỗ trợ retransform**.

**Trong mỗi nhóm**, transformer được gọi theo thứ tự chúng được đăng ký. Một `true` đăng ký **trước** `false` vẫn chạy **sau** nhóm false trong chuỗi.

Ví dụ:

~~~java
inst.addTransformer(transformerB, true);   // đăng ký trước
inst.addTransformer(transformerA, false);  // đăng ký sau
~~~

Ở hoạt động load/redefine class, xét riêng hai Java transformer này, thứ tự vẫn là **A(false) → B(true)**, không phải B rồi A. Nếu có thêm A2(false), thứ tự giữa A(false) và A2(false) mới dựa trên thời điểm đăng ký của chúng.

Với Java-only chain:

~~~text
Bytes gốc
   │
   ▼
A1(false) → A2(false) → B1(true) → B2(true)
   │                                 │
   └──── mỗi bước nhận bytes của bước trước ─────┘
                                      │
                                      ▼
                             Bytes để JVM kiểm tra
~~~

Nếu có native transformers, chúng được chèn theo đúng vị trí nhóm 2 và 4 như trên. Khi retransformation, nhóm `false` **tái sử dụng tác dụng đã lưu mà không gọi callback**, trong khi nhóm `true` thực sự chạy callback.

**Mọi transformer phải tương thích với kết quả của transformer trước nó.** Thứ tự rất quan trọng nếu A thay mã method còn B thêm logging vào mã đã thay. Nếu B tự giả định bytes đầu vào luôn là bản gốc, nó có thể tạo ra bytecode sai hoặc vô tình ghi đè tác dụng của A.

## 7. `ClassFileTransformer.transform`: input, output và thông tin callback

Với Java 17+, có thể override phiên bản có tham số `Module`:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Đọc classfileBuffer; trả null nếu không cần sửa.
    return null;
}
~~~

Đây là **thân method minh họa** bên trong lớp implement `ClassFileTransformer`, không phải chương trình Java độc lập. Một phiên bản overload cũ không có tham số `Module` cũng tồn tại để tương thích các triển khai từ Java trước 9.

Ý nghĩa các tham số:

| Tham số | Ý nghĩa cần nhớ |
|---|---|
| `module` | Module của class đang được xử lý |
| `loader` | Class loader định nghĩa lớp, có thể `null` với bootstrap loader |
| `className` | Tên nội bộ JVM như `demo/Work`, **không phải** `demo.Work`; có trường hợp có thể `null` |
| `classBeingRedefined` | `null` ở lần định nghĩa mới; **khác null** khi callback do **redefine hoặc retransform**. Chỉ dựa vào trường này không phân biệt được hai thao tác sau |
| `protectionDomain` | Protection domain liên quan class |
| `classfileBuffer` | Bytes đầu vào của **bước hiện tại trong chain**, có thể đã chịu tác dụng của transformer đứng trước |

Quy ước trả về:

- `return null`: **không thay đổi bytes**; bước tiếp theo thấy input hiện tại.
- `return newBytes`: thay bytes đầu vào bằng một **mảng byte mới** chứa class file hợp lệ cho bước tiếp theo.
- **Không sửa trực tiếp `classfileBuffer`**. Nếu cần biến đổi, hãy tạo mảng mới (thường bằng ASM, Byte Buddy hoặc thao tác class file được kiểm chứng).

Một transformer có thể `throw IllegalClassFormatException` khi phát hiện cấu trúc class file không hợp lệ. Theo hợp đồng API, nếu `transform` ném exception không được xử lý, JVM vẫn tiếp tục gọi transformer phía sau và việc load/redefine/retransform vẫn được thử; hiệu ứng của bước ném exception tương đương `return null`. Vì vậy **ném exception trong transformer không phải cơ chế đáng tin để hủy toàn bộ class load**. Agent nên log lỗi phù hợp và tránh phá hỏng quá trình bootstrap.

Thông thường nên viết một filter rõ ràng:

~~~java
if (!"demo/Work".equals(className)) {
    return null;
}
~~~

Cách so sánh này cũng an toàn khi `className == null`. Không nên log/biến đổi mọi lớp của JVM ngay từ lần học đầu tiên; transformer có thể được gọi trong lúc runtime đang tải những lớp mà chính agent phụ thuộc.

## 8. Ví dụ Java 17+: quan sát `false` và `true` trên một lớp

Để quan sát callback và thứ tự thực tế mà không cần thư viện ASM, ta tạo hai transformer **chỉ in log rồi trả `null`**. Chúng không sửa class file. Ví dụ này làm rõ **khi nào mỗi callback chạy**, còn các sơ đồ `B0/B1/B2` phía trên diễn tả chuỗi bytes nếu transformer có thật sự thay bytecode.

Cấu trúc thư mục:

~~~text
transformer-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── TraceAgent.java
│       ├── Work.java
│       └── Demo.java
└── out/               tạo trong bước biên dịch
~~~

### 8.1. Agent: `src/demo/TraceAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class TraceAgent {
    private static volatile Instrumentation current;

    public static void premain(String options, Instrumentation inst) {
        current = inst;
        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[premain] supported=" + supported);

        inst.addTransformer(new LogTransformer("A(false)"), false);
        if (supported) {
            inst.addTransformer(new LogTransformer("B(true)"), true);
        }
    }

    public static Instrumentation instrumentation() {
        if (current == null) {
            throw new IllegalStateException("Start JVM with -javaagent");
        }
        return current;
    }

    private static final class LogTransformer
            implements ClassFileTransformer {
        private final String name;

        private LogTransformer(String name) {
            this.name = name;
        }

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {
            if (!"demo/Work".equals(className)) {
                return null;
            }

            String phase = classBeingRedefined == null
                    ? "load" : "revisit";
            System.out.println("[transform] " + name + " " + phase);
            return null;
        }
    }
}
~~~

Lớp này đăng ký A ở nhóm `false` **luôn luôn** và B ở nhóm `true` **chỉ nếu JVM hỗ trợ retransform**. `phase = revisit` có nghĩa callback xử lý lại một class đã tồn tại, **không tự phân biệt redefine với retransform**; ở thí nghiệm này, chỉ có `retransformClasses`, nên có thể biết đây là retransformation từ lệnh gọi trong `Demo`.

`return null` giúp ví dụ chỉ đo callback, không làm thay đổi hành vi thực thi của class.

### 8.2. Lớp mục tiêu: `src/demo/Work.java`

~~~java
package demo;

public final class Work {
    public static int answer() {
        return 7;
    }
}
~~~

### 8.3. Ứng dụng: `src/demo/Demo.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("[main] loading demo.Work");
        Class<?> target = Class.forName("demo.Work");

        Object answer = target.getMethod("answer").invoke(null);
        System.out.println("[main] answer=" + answer);

        Instrumentation inst = TraceAgent.instrumentation();
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            System.out.println("[main] skip retransform");
            return;
        }

        System.out.println("[main] request retransform");
        inst.retransformClasses(target);

        Object after = target.getMethod("answer").invoke(null);
        System.out.println("[main] answer=" + after);
    }
}
~~~

`Class.forName("demo.Work")` chủ động tải lớp sau khi agent đã đăng ký transformer. Phản chiếu (`getMethod` và `invoke`) chỉ phục vụ việc tránh tham chiếu đến `Work.class` trước thời điểm ta muốn tải; cả hai lời gọi trả cùng kết quả vì transformer chỉ ghi log.

### 8.4. Manifest và lệnh chạy

Tạo `MANIFEST.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: true

~~~

Giữ **dòng trống cuối** trong manifest. Chạy trong thư mục `transformer-lab`.

Trên Bash/Git Bash:

~~~bash
mkdir -p out
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Biên dịch và đóng gói bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac --release 17 -d out src/demo/TraceAgent.java src/demo/Work.java src/demo/Demo.java
jar --create --file trace.jar --manifest MANIFEST.MF -C out .
java -javaagent:trace.jar -cp trace.jar demo.Demo
~~~

`--release 17` tạo class file tương thích Java 17; chương trình dùng `java.instrument`, không cần thêm dependencies. Dấu `/` trong đường dẫn được JDK chấp nhận trên Windows.

Trên JVM thông thường (ví dụ HotSpot có hỗ trợ retransformation và modifiable class), **đầu ra mong đợi**:

~~~text
[premain] supported=true
[main] loading demo.Work
[transform] A(false) load
[transform] B(true) load
[main] answer=7
[main] request retransform
[transform] B(true) revisit
[main] answer=7
~~~

**Đọc bằng chứng theo từng dòng:**

1. `[premain] supported=true`: JVM cấp capability khi agent khai báo `Can-Retransform-Classes: true`.
2. A(false) và B(true) **cùng** được gọi trong lần load `demo.Work`.
3. `Demo` yêu cầu `inst.retransformClasses(target)` sau khi lớp đã được tải.
4. Trong lần retransform chỉ có `[transform] B(true) revisit`; **không có dòng A(false) thứ hai**. JVM vẫn tái dùng tác dụng A ở cấp bytes.
5. `answer=7` trước/sau bởi cả hai transformer **trả `null`**, không sửa method.

Nếu JVM báo `supported=false`, agent chỉ đăng ký A(false); sau khi load và in `[main] answer=7`, chương trình sẽ in `[main] skip retransform` và kết thúc. Kết quả tùy JVM/cấu hình, không nên cố thay `false` thành `true` trong log.

Nếu `isModifiableClass(target)` trả `false`, `Demo` cũng bỏ qua thao tác retransform dù capability chung `true`. Đây là lý do **kiểm tra khả năng toàn JVM và khả năng của lớp đích riêng biệt**.

## 9. Đối chứng: thiếu capability sẽ ra sao?

Nếu thay manifest bằng:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.TraceAgent
Can-Retransform-Classes: false

~~~

Trong JVM không cấp retransformation, dòng `supported=false`; ví dụ vẫn đăng ký A(false) và xử lý lần load của `demo.Work`. Nhưng không đăng ký B(true) và không gọi `retransformClasses` vì nhánh guard trong code đã kiểm tra khả năng.

Nếu bỏ guard và gọi thẳng:

~~~java
inst.addTransformer(new LogTransformer("B(true)"), true);
~~~

đoạn này là **minh họa bên trong `TraceAgent`**. Khi `isRetransformClassesSupported() == false`, `addTransformer(..., true)` **ném `UnsupportedOperationException`** theo API. Ví dụ có guard để cho phép thử trên những JVM không hỗ trợ mà vẫn quan sát A(false). `LogTransformer` ở đây là inner class private thuộc `TraceAgent`, không dùng nó như một lớp độc lập từ file khác.

**Tóm ý về hai mức `true`:**

- `Can-Retransform-Classes: true` trong manifest: **agent yêu cầu capability**.
- `isRetransformClassesSupported() == true`: **JVM xác nhận capability hiện có**.
- `addTransformer(t, true)`: **đăng ký đúng transformer vào nhóm capable**.
- `retransformClasses(clazz)`: **chủ động yêu cầu xử lý lại một class đã tải**.

Thiếu bất kỳ bước thích hợp nào, câu “có `true` thì class sẽ tự biến đổi lại” là sai.

## 10. Tình huống thực tế: hai agent, hai transformer

Giả sử agent **A** thêm mã đếm method invocation lúc class load bằng transformer `false`; agent **B** muốn đổi các điểm log khi cấu hình giám sát thay đổi nên đăng ký transformer `true`.

~~~text
Khi định nghĩa class:
Bytes B0 → A(false) tạo B1 → B(true) tạo B2 → JVM định nghĩa class

Khi agent B yêu cầu retransform:
Initial bytes B0
    → dùng lại tác dụng A trên bytes, không gọi A
    → B(true) chạy với bytes đã qua A, tạo B3
    → JVM kiểm tra và áp dụng định nghĩa mới
~~~

Giả sử B ban đầu bật log mức `INFO`, sau đó đổi sang `DEBUG` rồi gọi `retransformClasses`. B có thể tính lại bytes với cấu hình mới, còn tác dụng A được giữ. Đây là ví dụ khái niệm, **không phải mã bytecode thực thi**; việc đặt probe vào method đòi hỏi ASM/Byte Buddy và xử lý đúng stack map frames cùng giới hạn retransform.

Nếu một **transformer `false` mới** được đăng ký *sau khi class đã tải*, gọi retransform trên class đó **không khiến callback false mới này chạy**. Để tạo biến đổi từ transformer ấy, cần áp dụng nó lúc một class được định nghĩa/redefine phù hợp; không suy rằng `retransformClasses` sẽ gọi lại nhóm false.

Nếu A và B cùng thay code, không được giả định B luôn nhìn thấy bytes gốc. Theo chain, B nhận bytes đã qua A. Dùng thư viện bytecode đúng phiên bản, xử lý lỗi và kiểm thử trên class cụ thể để tránh ghi đè instrumentation của các agent khác.

## 11. Quản lý registration và những lỗi thường gặp

### `removeTransformer` có hoàn tác class không?

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

Lời gọi này **gỡ registration** của đối tượng transformer (nếu cùng instance đã thêm nhiều lần thì gỡ lần thêm gần nhất phù hợp). Nó **không tự động khôi phục bytes của các class đã load**. Nếu muốn thay đổi trạng thái class đã tồn tại, cần cơ chế redefine/retransform phù hợp và bảo đảm kết quả cuối hợp lệ. Vì class loading diễn ra đồng thời, transformer vẫn có thể nhận một số callback **sau khi** gỡ registration; vì thế cần viết callback có khả năng xử lý cuộc gọi trễ.

Không nên đăng ký lặp lại cùng instance nhiều lần: API cho phép nhưng đặc tả khuyến cáo tránh, vì dễ sinh nhiều lần biến đổi không chủ ý và khó hiểu thứ tự khi gỡ.

### Những sai lầm dễ gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `addTransformer(t, true)` ném `UnsupportedOperationException` | Agent không yêu cầu hoặc JVM không cấp retransformation | Xem manifest **JAR agent**, kiểm tra `isRetransformClassesSupported()` |
| A(false) biến mất khỏi log khi `retransformClasses` | Đây là hành vi đúng: kết quả A được áp dụng lại **không gọi callback** | So sánh log lúc load và lúc retransform; không coi thiếu log là mất instrumentation |
| `true` đã đăng ký nhưng class cũ không đổi | Chưa thực hiện `retransformClasses` hoặc class không modifiable | Gọi API có chủ đích, kiểm tra guard và kết quả |
| Transformer mới đăng ký false nhưng không tác động class đã tải | False không được gọi ở bước retransformation | Đăng ký trước lần load/redefine phù hợp |
| Lệnh gọi retransform có `UnmodifiableClassException` | Target không thể sửa trong JVM này | Kiểm tra `isModifiableClass` và loại class |
| `ClassFormatError`, verification/linkage error | Transformer trả bytes không hợp lệ hoặc không tương thích | Kiểm tra bytes cuối, stack frames và các thay đổi schema |
| Class transformer chạy thứ tự trái với kỳ vọng đăng ký | Thứ tự **nhóm false/true** có ưu tiên trước thời điểm đăng ký | Phân nhóm rồi đối chiếu thứ tự **trong nhóm** |
| Callback thấy `className` là `demo/Work`, filter `demo.Work` không khớp | Tên class callback dùng **internal form** | So sánh với `"demo/Work"` |
| B vẫn thấy bytes đã bị A thay | Bytecode của các transformer được **xâu chuỗi** | Đừng giả định mỗi callback nhận original bytes |
| Dòng `revisit` xuất hiện nhưng không biết redefine hay retransform | `classBeingRedefined` không phân biệt hai trường hợp | Xem caller đã yêu cầu `redefineClasses` hay `retransformClasses` |
| Callback ném exception nhưng class vẫn load | JVM tiếp tục chain, coi tác dụng bước lỗi như `null` | Log bên trong transformer, đừng dùng throw làm “cancel” |
| `removeTransformer` xong nhưng ứng dụng vẫn chạy code đã instrument | Gỡ callback không trực tiếp hoàn tác class đang chạy | Xác định cách retransform/redefine phục hồi phù hợp |

Trong agent thật, tránh side effect và I/O nặng trong `transform`: callback có thể chạy khi JVM đang load các lớp cốt lõi hoặc khi nhiều thread yêu cầu load class. Nên filter lớp sớm, giữ transformer có thể chạy nhiều lần (*idempotent* khi cần), và tránh tạo liên kết phụ thuộc vào chính những lớp đang instrument.

## 12. Quy trình quyết định trước khi viết agent

1. **Mục tiêu chỉ cần biến đổi khi class được load/redefine?** Đăng ký `false` là đủ. Nó không có callback retransform nhưng kết quả cũ được giữ qua quy trình retransform đúng đặc tả.
2. **Cần tính lại một biến đổi cho class đã tải khi cấu hình agent đổi?** Yêu cầu `Can-Retransform-Classes: true`, kiểm tra hỗ trợ, đăng ký transformer `true`, rồi gọi `retransformClasses` trên lớp modifiable.
3. **Có nhiều transformer?** Thiết kế thứ tự theo nhóm false → true và theo thời điểm trong cùng nhóm; nhớ native transformer cũng tham gia thứ tự chuẩn.
4. **Transformer cần trả bytes?** Không sửa `classfileBuffer` tại chỗ, dùng mảng mới chứa toàn bộ class file hợp lệ, kiểm chứng stack map frames và giới hạn cấu trúc khi xử lý lại class đã tải.
5. **Muốn đo kết quả?** Ghi log chính xác tên class, loại registration và thời điểm load/redefine/retransform, sau đó so sánh với bytes/hiệu ứng thực tế. Số lần callback **không phản ánh trực tiếp** số lần tác dụng bytecode được tái áp dụng.

## 13. Tự kiểm tra

1. **`inst.addTransformer(t)` thuộc nhóm nào?** Tương đương `inst.addTransformer(t, false)`.
2. **Đăng ký `false` có được gọi khi class lần đầu được load?** Có. Nó có thể thay bytecode lúc load.
3. **Class đã được A(false) biến đổi, JVM gọi `retransformClasses`: có gọi A lần nữa không?** Không. JVM dùng lại kết quả biến đổi A của lần load/redefine trước.
4. **B(true) đã đăng ký, khi `retransformClasses` chạy có gọi B lại không?** Có, nếu request được JVM chấp nhận.
5. **`addTransformer(B, true)` trước `addTransformer(A, false)`, thứ tự load của hai Java transformer?** A(false) rồi B(true) vì thứ tự nhóm ưu tiên.
6. **`Can-Retransform-Classes: true` nhưng `isRetransformClassesSupported() == false`, đăng ký transformer true được không?** Không; `addTransformer(..., true)` ném `UnsupportedOperationException`.
7. **`transform` không muốn đổi bytes thì trả gì?** `null`. Không sửa `classfileBuffer`.
8. **`classBeingRedefined != null` có chứng minh đang gọi `redefineClasses` không?** Không; retransform cũng truyền `Class<?>` hiện có.
9. **Hai transformer biến đổi cùng class: callback thứ hai nhận original bytes?** Không nhất thiết; nó nhận bytes đầu ra của các bước trước trong chain.
10. **Gỡ A khỏi registration thì JVM khôi phục mọi class đã instrument ngay?** Không; gỡ callback không phải thao tác rollback class.
11. **Vì sao ví dụ Java giữ `answer=7` cả hai lần?** Vì A/B chỉ ghi log rồi `return null`, không thay định nghĩa `demo.Work`.

### Tài liệu chuẩn

- [Java SE 21 — `Instrumentation`: `addTransformer`, `isRetransformClassesSupported`, `retransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- [Java SE 21 — `ClassFileTransformer`: thứ tự nhóm, input/output, callback và xử lý lỗi](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- [Java SE 21 — `java.lang.instrument` package specification: agent JAR và `Can-Retransform-Classes`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- [Java SE 21 — `UnmodifiableClassException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html).

**Kết luận cần ghi nhớ:** `false` **không có callback retransform nhưng hiệu ứng cũ được áp dụng lại**; `true` **có callback retransform** nếu JVM/agent đã có capability. Khi nhiều transformer tham gia, **thứ tự nhóm quyết định chuỗi bytes**, còn `retransformClasses` quyết định lúc nào thực sự xử lý lại một class đã tải.