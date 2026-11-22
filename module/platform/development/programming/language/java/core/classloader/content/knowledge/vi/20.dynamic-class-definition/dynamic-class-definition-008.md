# Redefine, retransform và khác biệt với nạp lớp bằng loader mới

## 1. Ba cách thay đổi mã Java lúc JVM đang chạy

Khi ứng dụng cần sửa hành vi method, gắn profiler, cập nhật plugin hoặc chạy hai phiên bản song song, có ba kỹ thuật dễ bị gọi chung là hot reload nhưng có ý nghĩa hoàn toàn khác nhau:

1. **Redefine** dùng **Instrumentation.redefineClasses(ClassDefinition...)** để cung cấp class-file bytes thay thế cho **Class đã tồn tại**.
2. **Retransform** dùng **Instrumentation.retransformClasses(Class<?>...)** để JVM chạy lại chuỗi **ClassFileTransformer** phù hợp trên **Class đã tồn tại**, không truyền replacement bytes trực tiếp vào lệnh này.
3. **Nạp bằng ClassLoader mới** dùng loadClass/findClass/defineClass theo cách thông thường để tạo **runtime Class khác**, ngay cả khi binary name vẫn giống bản cũ.

**Nếu chỉ sửa method body và muốn các instance cũ dùng code mới trên lần gọi tiếp theo, xem redefine/retransform. Nếu phải thay class schema, chạy hai phiên bản đồng thời hoặc thay module/plugin toàn diện, hãy xét ClassLoader mới.**

Các thuật ngữ cần nhớ:

- **Loading**: JVM tìm và định nghĩa class.
- **Linking**: verification/preparation/resolution theo đặc tả.
- **Initialization**: thực hiện static initializers khi active use theo quy tắc Java.
- **Class identity**: với class thông thường, dựa trên **binary name cùng defining ClassLoader**.
- **Instrumentation**: API agent làm việc trên bytecode/classes mà JVM đã hoặc sắp nạp.

Không nhầm **ClassLoader.defineClass** với **Instrumentation.redefineClasses** chỉ vì tên giống nhau: một bên tạo định nghĩa runtime từ loader, bên kia cập nhật định nghĩa hiện có theo những giới hạn đặc biệt.

## 2. Bảng so sánh

| Tiêu chí | redefineClasses | retransformClasses | Loader mới |
| --- | --- | --- | --- |
| Đầu vào | ClassDefinition(Class c, byte[] bytes) | Class<?> targets | Class name và nguồn bytes |
| Có cần Java agent? | Có, Instrumentation | Có, Instrumentation | Không |
| Có truyền class-file bytes thay thế trực tiếp? | Có | Không, transformer pipeline xử lý | Có thể, qua defineClass |
| Class object mục tiêu có thay thành object khác không? | Không | Không | Có Class mới do loader mới định nghĩa |
| Existing instances có dùng method body mới không? | Có, trên invocation mới | Có, trên invocation mới | Không, instances cũ vẫn thuộc Class cũ |
| Static field values có reset không? | Không | Không | Class mới có static state riêng |
| Chạy lại static initializer của class cũ? | Không | Không | Class mới khởi tạo riêng khi được active use |
| Thêm field hoặc method mới? | Không theo giới hạn JVMTI Java 17 | Không theo giới hạn JVMTI Java 17 | Có thể trong class mới |
| Có thể chạy hai phiên bản cùng binary name? | Không thành hai runtime types | Không thành hai runtime types | Có, nếu loaders khác |
| Ví dụ sử dụng | Hot-fix method body | Coverage/APM instrumentation | Plugin reload, isolation, API evolution |
| Rủi ro | Capability, schema, active frames | Transformer ordering, replay | Type identity, delegation, leaks |

**Kết luận quan trọng:** Redefine và retransform không phải cách thay Class object. Loader mới không sửa Class object cũ. Ba hướng giải quyết những vấn đề khác nhau.

## 3. Class đã load có thể được định nghĩa lại bằng defineClass không?

**Không.** Khi một loader đã define class với binary name ví dụ **lesson.hot.Feature**, loader ấy không thể gọi defineClass một lần nữa với cùng name như cách ghi đè bản cũ. JVM có thể ném **LinkageError** do duplicate definition. loadClass có thể tiếp tục trả cùng Class đã được JVM ghi nhận.

Để thay hành vi của đúng Class đang chạy, dùng cơ chế instrumentation nếu hỗ trợ; để có một class cùng tên nhưng mới hoàn toàn, tạo loader khác:

~~~text
Ban đầu:
  Feature Class object
       |
       +-- binary name = lesson.hot.Feature
       +-- defining loader = L1
       +-- method body V1

Redefine / retransform:
  Feature Class object (vẫn là object đó)
       |
       +-- defining loader = L1 (không đổi)
       +-- method body V2 được cài hợp lệ

Loader khác:
  Feature class A = (lesson.hot.Feature, L1)
  Feature class B = (lesson.hot.Feature, L2)

  A != B dù tên hoàn toàn giống nhau
~~~

Các instances thuộc A không tự biến thành instances của B. Cần quản lý traffic/migration nếu chuyển plugin sang B.

## 4. Instrumentation, agent và capability

### 4.1 Java agent cung cấp Instrumentation

Một ứng dụng thường không thể tự gọi constructor để tạo **Instrumentation**. JVM truyền object này vào entry point của Java agent:

~~~java
import java.lang.instrument.Instrumentation;

public class Agent {
    public static void premain(
            String args, Instrumentation instrumentation) {
        // Được JVM gọi khi ứng dụng khởi động với -javaagent
    }

    public static void agentmain(
            String args, Instrumentation instrumentation) {
        // Có thể được gọi khi agent được attach về sau,
        // nếu JVM và chính sách runtime cho phép
    }
}
~~~

Đây là chữ ký minh họa, chưa phải chương trình chạy độc lập.

Cách đơn giản và có thể tái hiện trong bài học là chạy **-javaagent:agent.jar**. JVM đọc **Premain-Class** trong JAR manifest, gọi premain trước application main rồi application mới thực hiện công việc.

Dynamic attach/agentmain là khả năng có điều kiện, có thể bị chính sách JDK hoặc môi trường triển khai hạn chế. Không giả định luôn được attach vào production JVM.

### 4.2 Manifest capabilities

~~~text
Premain-Class: Agent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

Đây là nội dung file **agent.mf**, không phải Java source. Capability phải được yêu cầu phù hợp bằng manifest và JVM thực sự hỗ trợ.

Kiểm tra trong code agent:

~~~java
boolean redefine = inst.isRedefineClassesSupported();
boolean retransform = inst.isRetransformClassesSupported();
boolean targetModifiable = inst.isModifiableClass(Target.class);
~~~

Đây là snippet đặt trong method có biến inst và Target phù hợp.

- **isRedefineClassesSupported** và **isRetransformClassesSupported** là hai khả năng độc lập.
- **isModifiableClass** kiểm tra class cụ thể có sửa được không; kết quả true không thay thế việc kiểm tra capability tương ứng.
- Primitive classes và array classes không thể redefine/retransform.
- Một số VM-defined classes cũng có thể không modifiable.
- Manifest xin capability không ép JVM phải cấp khả năng mà VM không hỗ trợ.

## 5. Dữ liệu class-file hợp lệ và giới hạn thay đổi

Với Java 17/JVMTI chuẩn, redefine/retransform chủ yếu cho phép **sửa method bodies, constant pool và những attributes được phép** của class đã tồn tại. Các thay đổi sau nhìn chung bị cấm:

| Thay đổi | Redefine/retransform Java 17 |
| --- | --- |
| Sửa instructions trong method đang tồn tại | Có thể, nếu bytes hợp lệ |
| Thay constant pool/attributes được phép | Có thể |
| Thêm hoặc bỏ field | Không |
| Thêm hoặc bỏ method | Không |
| Đổi tên hay descriptor của method | Không |
| Đổi field schema | Không |
| Đổi modifiers bị đặc tả hạn chế | Không |
| Đổi direct superclass hoặc implemented interfaces | Không |
| Thay NestHost/NestMembers | Không |
| Thay Record/PermittedSubclasses attributes | Không |
| Bytes khai báo binary name khác target Class | Không |
| Class-file version mới hơn VM hỗ trợ | Không |

Không nên tin rằng một class mới đã **compile thành công** thì chắc chắn có thể redefine class cũ. Hai bản có thể khác schema, annotations/attributes thuộc loại bị cấm, method modifiers hoặc hierarchy.

**Loader mới khác ở đây:** Một loader L2 có thể define type mới có thêm/bớt fields/methods hoặc API khác, miễn là nó là class hợp lệ theo JVM và đáp ứng các ràng buộc loading/module/package tương ứng. Nhưng bạn phải chấp nhận **Class identity mới**.

Các VM/tools đặc biệt có thể cung cấp enhanced hot-swap ngoài chuẩn; không xem đó là cam kết chung của Java 17.

## 6. Môi trường ví dụ Java 17+

Ba ví dụ hoàn chỉnh bên dưới dùng một source tree thống nhất. Hai bản Feature có cùng binary name nhưng khác behavior. TraceTarget dùng để thử transformer. Các demo đã được biên dịch/chạy trên OpenJDK 21 và chỉ sử dụng API Java 17+.

~~~text
project/
├── agent.mf
├── versions/
│   ├── v1/lesson/hot/Feature.java
│   └── v2/lesson/hot/Feature.java
├── retrans-src/lesson/hot/TraceTarget.java
└── host-src/
    ├── Agent.java
    ├── RedefineDemo.java
    ├── RetransformDemo.java
    └── NewLoaderDemo.java
~~~

Output folders khi compile: **v1**, **v2**, **retrans**, **host**. Chạy mọi lệnh từ thư mục **project**. Nếu bạn dùng Windows PowerShell, dấu ngăn nhiều classpath entries là **;** thay vì dấu **:** trên Linux/macOS.

### 6.1 Feature phiên bản 1

**versions/v1/lesson/hot/Feature.java**:

~~~java
package lesson.hot;

public class Feature {
    public static int state = 7;

    static {
        System.out.println("Feature V1 initialized");
    }

    public String label() {
        return "v1";
    }
}
~~~

### 6.2 Feature phiên bản 2

**versions/v2/lesson/hot/Feature.java**:

~~~java
package lesson.hot;

public class Feature {
    public static int state = 999;

    static {
        System.out.println("Feature V2 initialized");
    }

    public String label() {
        return "v2";
    }
}
~~~

Hai bản **giữ đúng cùng schema**: cùng public field state và method label. Chỉ thay method bodies và code của static initializer.

Biên dịch vào hai thư mục riêng:

~~~bash
javac -d v1 versions/v1/lesson/hot/Feature.java
javac -d v2 versions/v2/lesson/hot/Feature.java
~~~

Không đặt hai Feature.java này trong cùng compilation unit hoặc cùng output folder, vì một bản sẽ bị ghi đè hoặc compiler báo trùng class.

### 6.3 Agent dùng chung

**host-src/Agent.java**:

~~~java
import java.lang.instrument.Instrumentation;

public class Agent {
    static volatile Instrumentation instrumentation;

    public static void premain(
            String args, Instrumentation inst) {
        instrumentation = inst;
    }
}
~~~

**agent.mf** (file text manifest, cần có newline cuối file):

~~~text
Premain-Class: Agent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
~~~

Sau khi compile Agent.class vào host, đóng gói:

~~~bash
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
~~~

Trong hai demo instrumentation, **-javaagent:agent.jar** bảo đảm premain đã thiết lập Instrumentation khi main chạy.

## 7. Ví dụ runnable 1 — redefineClasses

**host-src/RedefineDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import lesson.hot.Feature;

public class RedefineDemo {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = Agent.instrumentation;

        System.out.println("redefine supported = "
                + inst.isRedefineClassesSupported());

        Feature object = new Feature();
        Class<?> type = object.getClass();

        System.out.println("before = " + object.label());
        System.out.println("state before = " + Feature.state);

        byte[] replacement = Files.readAllBytes(
                Path.of(args[0]));

        inst.redefineClasses(
                new ClassDefinition(Feature.class, replacement));

        System.out.println("same Class = "
                + (type == object.getClass()));
        System.out.println("same object = " + object.label());
        System.out.println("new object = "
                + new Feature().label());
        System.out.println("state after = " + Feature.state);
    }
}
~~~

Biên dịch sau khi đã có v1/v2 và Agent.java:

~~~bash
javac -cp v1 -d host host-src/Agent.java host-src/RedefineDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp host:v1 RedefineDemo v2/lesson/hot/Feature.class
~~~

Windows PowerShell:

~~~powershell
javac -cp v1 -d host host-src/Agent.java host-src/RedefineDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp "host;v1" RedefineDemo v2/lesson/hot/Feature.class
~~~

**Stdout thực tế trên OpenJDK 21:**

~~~text
redefine supported = true
Feature V1 initialized
before = v1
state before = 7
same Class = true
same object = v2
new object = v2
state after = 7
~~~

### 7.1 Phân tích chi tiết

1. **Feature** lần đầu khởi tạo từ v1, in **Feature V1 initialized**.
2. JVM giữ static field **state = 7**.
3. **ClassDefinition(Feature.class, replacement)** cung cấp bytes của v2 cho đúng Class mục tiêu.
4. **Instrumentation.redefineClasses** cập nhật method code hợp lệ. Không có Class object mới.
5. **same Class = true** vì existing object vẫn có runtime type cũ về identity.
6. **same object = v2** vì một lần gọi method mới trên existing instance sử dụng method body v2.
7. Instance mới cũng gọi method body v2.
8. **state after = 7**, không phải 999. **Feature V2 initialized** cũng không xuất hiện.

Redefinition **không chạy lại static initializer** và không tự reset static fields hay recreate instances.

### 7.2 Khi demo không thể chạy nguyên dạng

Capability redefine là tùy JVM, nên output “supported=true” áp dụng cho OpenJDK test có manifest phù hợp, không phải mọi VM. Nếu không hỗ trợ, gọi redefineClasses có thể ném UnsupportedOperationException. Nếu replacement bytes đổi field/method schema hoặc có binary name khác, JVM từ chối.

**Nếu chỉ muốn thử trên JVM có capability**, demo này là đủ. Production code nên kiểm tra thêm **isModifiableClass(Feature.class)** trước khi can thiệp.

## 8. Ví dụ runnable 2 — retransformClasses

### 8.1 Khác biệt về đầu vào

**retransformClasses(TraceTarget.class)** chỉ nhận Class target. JVM sử dụng **ClassFileTransformer pipeline** phù hợp để tính lại bytes cho định nghĩa hiện hữu, thay vì caller gửi một class-file array cho ClassDefinition.

**retrans-src/lesson/hot/TraceTarget.java**:

~~~java
package lesson.hot;

public class TraceTarget {
    public String label() {
        return "OLD-CODE";
    }
}
~~~

Để không cần phụ thuộc thư viện ngoài, ví dụ chỉ thay một UTF-8 constant có cùng độ dài: **OLD-CODE → NEW-CODE**. Đây là một thủ thuật minh họa rất hẹp, không phải transformer production.

### 8.2 Source RetransformDemo.java

**host-src/RetransformDemo.java**:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.Arrays;
import lesson.hot.TraceTarget;

public class RetransformDemo {
    static byte[] replaceMarker(byte[] original) {
        byte[] search =
                "OLD-CODE".getBytes(StandardCharsets.US_ASCII);
        byte[] replace =
                "NEW-CODE".getBytes(StandardCharsets.US_ASCII);

        byte[] result = Arrays.copyOf(
                original, original.length);

        int matches = 0;

        for (int i = 0;
             i <= result.length - search.length; i++) {
            boolean match = true;

            for (int j = 0; j < search.length; j++) {
                if (result[i + j] != search[j]) {
                    match = false;
                    break;
                }
            }

            if (match) {
                matches++;
                System.arraycopy(
                        replace, 0, result, i, replace.length);
            }
        }

        if (matches != 1) {
            throw new IllegalStateException(
                    "Expected one marker, found " + matches);
        }

        return result;
    }

    public static void main(String[] args) throws Exception {
        Instrumentation inst = Agent.instrumentation;

        System.out.println("retransform supported = "
                + inst.isRetransformClassesSupported());

        TraceTarget existing = new TraceTarget();
        System.out.println("before = " + existing.label());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redef,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if (!"lesson/hot/TraceTarget".equals(name)
                        || redef == null) {
                    return null;
                }

                return replaceMarker(bytes);
            }
        };

        inst.addTransformer(transformer, true);

        try {
            inst.retransformClasses(TraceTarget.class);
        } finally {
            inst.removeTransformer(transformer);
        }

        System.out.println("after = " + existing.label());
        System.out.println("same class = "
                + (existing.getClass() == TraceTarget.class));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -d retrans retrans-src/lesson/hot/TraceTarget.java
javac -cp retrans -d host host-src/Agent.java host-src/RetransformDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp host:retrans RetransformDemo
~~~

Windows PowerShell:

~~~powershell
javac -d retrans retrans-src/lesson/hot/TraceTarget.java
javac -cp retrans -d host host-src/Agent.java host-src/RetransformDemo.java
jar --create --file agent.jar --manifest agent.mf -C host Agent.class
java -javaagent:agent.jar -cp "host;retrans" RetransformDemo
~~~

**Stdout thực tế trên OpenJDK 21:**

~~~text
retransform supported = true
before = OLD-CODE
after = NEW-CODE
same class = true
~~~

### 8.3 Điểm cần hiểu để không triển khai sai

- **addTransformer(transformer, true)** yêu cầu transformer đủ khả năng retransform.
- **ClassFileTransformer** trong Java 17 có hai default transform overloads, **không phải functional interface**. Vì thế ví dụ dùng anonymous class, không dùng lambda.
- Transformer nhận **internal class name** kiểu **lesson/hot/TraceTarget**, không phải tên Java lesson.hot.TraceTarget.
- **redef != null** ở lần retransform; trong lượt load class ban đầu nó thường null.
- Trả **null** khi không sửa bytes.
- Không được tự thay đổi **classfileBuffer** input; ví dụ dùng **Arrays.copyOf**.
- Marker old/new đều 8 ASCII bytes nên chiều dài một constant pool UTF-8 entry không đổi. Code kiểm tra đúng một marker trong file mục tiêu.
- **removeTransformer** chỉ gỡ registration cho những lần biến đổi sau; nó **không tự hoàn nguyên bytecode đã được cài**.
- Existing instance vẫn là cùng object và same class identity, nhưng invocation mới chạy method code mới.

**Giới hạn:** sửa raw bytes bằng tìm chuỗi có thể phá class file khác. Chỉ áp dụng cho fixture đã biên dịch được kiểm soát. Dự án thật cần ASM/Byte Buddy hoặc API class-file phù hợp để thay đổi có cấu trúc, giữ stack map frames và constant pool hợp lệ.

## 9. Ví dụ runnable 3 — hai ClassLoaders mới

### 9.1 Không cần Java agent

Trong ví dụ này ta sẽ **không redefine hoặc retransform**. Ta định nghĩa **hai Class khác nhau** từ đúng hai file Feature.class v1/v2 bằng hai loader riêng.

**host-src/NewLoaderDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public class NewLoaderDemo {
    static final class VersionLoader extends ClassLoader {
        private final Path classFile;

        VersionLoader(Path classFile) {
            super(ClassLoader.getPlatformClassLoader());
            this.classFile = classFile;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("lesson.hot.Feature")) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(classFile);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    static String label(Class<?> type) throws Exception {
        Object object = type.getConstructor().newInstance();
        return (String) type.getMethod("label").invoke(object);
    }

    public static void main(String[] args) throws Exception {
        VersionLoader first = new VersionLoader(
                Path.of("v1/lesson/hot/Feature.class"));

        VersionLoader second = new VersionLoader(
                Path.of("v2/lesson/hot/Feature.class"));

        Class<?> a = first.loadClass("lesson.hot.Feature");
        Class<?> b = second.loadClass("lesson.hot.Feature");

        System.out.println("same name = "
                + a.getName().equals(b.getName()));
        System.out.println("same Class = " + (a == b));
        System.out.println("first loader = "
                + (a.getClassLoader() == first));
        System.out.println("second loader = "
                + (b.getClassLoader() == second));
        System.out.println("first value = " + label(a));
        System.out.println("second value = " + label(b));
    }
}
~~~

Biên dịch/chạy sau khi có v1, v2:

~~~bash
javac -d host host-src/NewLoaderDemo.java
java -cp host NewLoaderDemo
~~~

**Stdout thực tế trên OpenJDK 21:**

~~~text
same name = true
same Class = false
first loader = true
second loader = true
Feature V1 initialized
first value = v1
Feature V2 initialized
second value = v2
~~~

### 9.2 Giải thích

- Hai Class đều có name **lesson.hot.Feature**.
- Defining loaders là hai VersionLoader objects khác nhau, nên **a != b**.
- Mỗi Class có static state riêng, được initialized lần đầu theo lifecycle của nó.
- Existing instances thuộc bản V1 vẫn dùng V1; những objects tạo từ B dùng V2.
- Không có lệnh Instrumentation; đây là class loading bình thường theo hai loaders.

**Vì sao đặt platform loader làm parent?** Ví dụ không đưa v1/v2 lên application classpath. Platform parent không nhìn thấy lớp plugin do test cung cấp, nên findClass riêng được gọi. Nếu dùng parent có sẵn cùng class name, cơ chế **parent-first** có thể trả Class của parent và không tạo bản riêng mong đợi.

Ví dụ tối giản chỉ hỗ trợ một binary name; loader production cần kiểm soát paths, packages, protection domains, modules, resources và trust boundary.

## 10. Instance cũ, static state và active frames

### 10.1 Khi redefine/retransform đã thành công

Theo Instrumentation/JVMTI:

- Một **Class object đang tồn tại** vẫn đại diện class ấy.
- **Existing objects** không được tạo mới. Instance fields giữ giá trị đang có.
- **Static values** giữ trạng thái, dù file replacement có code khởi tạo khác.
- **Static initializer không tự chạy lại** vì redefine/retransform.
- **New method invocation** dùng method body mới.
- **Active frames** đang thực thi method body cũ có thể tiếp tục chạy bytecode cũ tới khi frame hoàn tất.

~~~text
Thread A đã bước vào method V1
          |
JVM cập nhật Class thành V2
          |
          +-- frame A vẫn dùng code V1
          |
Thread B bắt đầu một lần gọi method mới
          |
          +-- dùng code V2
~~~

Do đó, sau khi agent báo cập nhật thành công, không thể kết luận mọi request trong mọi thread ngay lập tức chuyển sang logic mới. Nếu thay behavior liên quan state, giao dịch hoặc security, hãy cân nhắc quiescence, in-flight requests và rollback.

### 10.2 Khi dùng loader mới

Class V2 khác Class V1, nên V2 có static initialization riêng khi được active use. Objects V1 không bị JVM migrate tự động sang V2. Nếu muốn chuyển dữ liệu, ứng dụng cần cơ chế chuyển đổi/serialization/DTO hoặc recreation explicit, đồng thời chuẩn bị giải phóng references của phiên bản cũ.

Không gọi **new loader** là “đổi method body của Class hiện tại”. Đây là **chuyển hệ thống sang type identity mới**.

## 11. Retransformation pipeline chính xác

Retransform không đơn giản là “gọi lại mọi transformer”:

~~~text
Initial class file bytes
          |
          v
Transformer A: canRetransform = false
          |
          +-- reapply previous transform result
          |   KHÔNG gọi lại method transform của A
          |
          v
Transformer B: canRetransform = true
          |
          +-- gọi lại B.transform(...)
          |
          v
Transformer C: canRetransform = true
          |
          +-- gọi lại C.transform(...)
          |
          v
Verify và install bytes hợp lệ cho cùng Class
~~~

**Initial class file bytes** theo API có thể không byte-for-byte trùng với những bytes ban đầu được đưa vào defineClass, vì JVM có thể khác nhau ở constant-pool layout hoặc một số attributes. Đừng viết transformer dựa vào offsets cố định trong class file thực tế.

**Transformer ordering** được ClassFileTransformer quy định. Trong môi trường nhiều agents, những transformations tương tác nhau: cần kiểm tra idempotence, class schema, hiệu năng và thứ tự. RedefineClasses cũng có thể kích hoạt transformers đã đăng ký trong quá trình xử lý replacement bytes, nên agent không nên giả định redefine bỏ qua hoàn toàn chain.

**Transformer được add sau khi Class load không tự sửa Class đã nạp.** Ví dụ 2 phải gọi retransformClasses cụ thể để transformer tác động retroactively.

## 12. Điều gì xảy ra nếu thao tác thất bại?

| Tình huống | Lỗi hoặc biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Capability không hỗ trợ | UnsupportedOperationException | Kiểm tra manifest và is*Supported |
| Class không modifiable | UnmodifiableClassException | Kiểm tra isModifiableClass |
| Thêm field/method hoặc đổi hierarchy | UnsupportedOperationException/VM error liên quan | So sánh schema, chọn loader mới nếu cần |
| Bytes sai định dạng | ClassFormatError | Kiểm tra generator, input bytes |
| Binary name trong bytes không khớp target | NoClassDefFoundError | Kiểm tra tên nội bộ của class file |
| Bytecode verifier từ chối | VerifyError/LinkageError | Xem bytecode và dependencies |
| Classfile version quá mới | UnsupportedClassVersionError | Dùng --release và JDK phù hợp |
| Transformer không được đăng ký capable | Không được gọi lại khi retransform | addTransformer(..., true), capabilities |
| JAR đổi trên đĩa nhưng Class vẫn bản cũ | Không tự reload | Dùng instrumentation hoặc loader mới |
| Loader child trả Class từ parent | Không có version riêng | Hiểu parent delegation và defining loader |

Các thao tác trên **một tập Class** có ngữ nghĩa theo tài liệu: nếu redefinition/retransformation báo exception trong việc áp dụng, **không class nào trong tập đó được cài bản mới**. Không suy rộng điều đó thành rollback toàn bộ side effects của ứng dụng hoặc của transformers bên ngoài.

Một lỗi transformer riêng không nhất thiết ngăn toàn bộ pipeline: Javadoc nêu JVM có thể tiếp tục các transformers khác. Không dùng exception trong transformer như cách rollback chắc chắn; nên validate bytes và log theo hợp đồng phù hợp.

## 13. Khả năng hot-reload và hạn chế của trạng thái ứng dụng

### 13.1 Redefine để vá method

Phù hợp cho một bản sửa logic với schema không đổi. Ưu điểm là existing objects dùng code mới trên invocation mới, không cần thay references toàn hệ thống.

Nhưng nếu logic mới mong đợi static fields mới hoặc invariants mới, JVM không tự chuyển đổi state. Bạn phải thiết kế migration/feature flags/compatibility riêng.

### 13.2 Retransform cho monitoring

Profiler và coverage agent thường muốn thêm một số instructions vào methods hiện có mà không viết lại toàn bộ classes bằng tay. Retransform cho phép thực hiện lại pipeline khi cần enable/disable instrumentation hoặc thay strategy (trong giới hạn API/VM).

Không bảo đảm mọi class đều instrumentable; kiểm tra capabilities và modifiability.

### 13.3 New loader cho plugin evolution

Plugin manager thường nạp implementation V2 trong loader/layer mới, chuyển request tới service V2, rồi dừng V1. V2 có thể có schema khác, nhưng cần:

- Shared interface/DTO/API có cùng Class identity ở host/plugin boundary.
- Parent delegation policy không khiến child vô tình nạp bản cũ từ parent.
- In-flight requests đang dùng V1 có đường kết thúc.
- Plugin V1 được unregister listeners/services/caches.
- Threads/executors/ThreadLocal/TCCL không giữ loader V1 mãi.
- JVM chỉ có thể unload class cũ khi defining loader không còn strong references, không bảo đảm ngay sau stop.

Đừng dùng ClassLoader như sandbox bảo mật cho code không tin cậy; class-loading isolation không đồng nghĩa process isolation.

## 14. Những nhầm lẫn phổ biến

**“Redefine tạo một Class object mới.”** Sai: vẫn là target Class hiện có.

**“Retransform giống defineClass lần hai.”** Sai: retransform vận hành trên Class đã load qua transformer pipeline.

**“Static block bản mới luôn chạy khi redefine.”** Sai: <clinit> không được chủ động chạy lại.

**“Thay source/JAR rồi class tự cập nhật.”** Sai: JVM không tự ghi đè Class đang sống khi file bytes trên đĩa đổi.

**“Redefine có thể thêm method/field tùy ý.”** Sai theo giới hạn Java 17/JVMTI chuẩn.

**“Tất cả threads đang chạy lập tức dùng bytecode mới.”** Sai: active stack frames có thể tiếp tục bytecode cũ.

**“Class mới có cùng tên luôn cast sang Class cũ được.”** Sai nếu defining loaders khác.

**“Transformer canRetransform=false được gọi lại ở mỗi retransform.”** Sai: kết quả cũ được replay theo quy tắc.

**“removeTransformer hoàn nguyên changes đã cài.”** Sai: nó gỡ registration tương lai.

**“ClassFileTransformer dùng lambda Java 17 như Runnable.”** Sai: không phải functional interface; ví dụ 2 dùng anonymous class.

**“Khi isModifiableClass true thì chắc chắn capability được cấp.”** Sai: phải kiểm tra capability riêng.

**“ClassLoader mới luôn giúp unload loader cũ.”** Sai: nếu old threads/callbacks giữ strong references, loader cũ vẫn sống.

## 15. Quy trình quyết định kỹ thuật

~~~text
Muốn sửa hành vi code Java runtime?
          |
          v
Class mục tiêu đã được JVM define chưa?
          |
          +-- Chưa: bình thường dùng ClassLoader/findClass/defineClass
          |
          +-- Rồi
                |
                v
          Chỉ sửa method body / instrumentation hợp lệ?
                |
          +-----+-----+
          |           |
         Có          Không
          |           |
          v           v
    Có agent và      Cần schema mới,
    capability?      API mới, dual versions?
          |           |
       +--+--+        v
       |     |       Loader mới + lifecycle
      Có    Không
       |     |
       v     v
   Redefine/ cần công cụ khác,
   Retransform restart hoặc loader mới
~~~

**Dùng redefine** nếu bạn có replacement class-file bytes và muốn thay definition của Class đang tồn tại.

**Dùng retransform** nếu bạn muốn áp dụng lại transformer chain trên Class đã được nạp.

**Dùng loader mới** nếu cần phiên bản runtime class mới tách biệt, đặc biệt khi yêu cầu schema khác hoặc coexistence.

## 16. Tự kiểm tra

**Câu 1.** Feature v1 đã initialized state=7. Redefine từ bytes có state=999, state có đổi tự động thành 999 không?

**Đáp án:** Không. Static values được giữ; <clinit> không tự chạy lại.

**Câu 2.** Existing object gọi method sau redefine có dùng body mới không?

**Đáp án:** Có trên new invocation, với những ngoại lệ về active frames đang thực thi code cũ.

**Câu 3.** Caller của retransformClasses truyền ClassDefinition hay Class<?>?

**Đáp án:** Class<?> targets; JVM áp dụng transformer pipeline.

**Câu 4.** Transformer không-capable có được gọi lại khi retransform không?

**Đáp án:** Không; kết quả transform cũ được replay theo API.

**Câu 5.** Hai loader định nghĩa class có cùng binary name, liệu Class objects có bằng nhau?

**Đáp án:** Không; defining loader là thành phần class identity.

**Câu 6.** Muốn thêm một field mới vào bản Feature đang sống trên Java 17 chuẩn, có nên redefine không?

**Đáp án:** Không; đó là schema change không được hỗ trợ, cân nhắc loader mới và migration.

**Câu 7.** Vì sao cần Can-Retransform-Classes và addTransformer(..., true)?

**Đáp án:** Capability và đăng ký transformer phải cho phép retransformation; nếu không, lần retransform không thể gọi lại transformer theo mong đợi.

**Câu 8.** Agent mới đăng ký transformer sau khi TraceTarget đã được load. Class có tự thay đổi ngay không?

**Đáp án:** Không; ví dụ phải chủ động gọi retransformClasses.

**Câu 9.** ClassLoader.loadClass có chắc thấy file .class đã thay trên đĩa không?

**Đáp án:** Không. Loader có thể trả Class đã nạp; parent delegation cũng có thể trả Class từ nguồn khác.

**Câu 10.** Dùng loader mới để deploy plugin V2 có tự xóa instance V1 khỏi host registry không?

**Đáp án:** Không. Phải unregister và cleanup references/callbacks/threads để V1 có thể collectible.

## 17. Ghi nhớ

~~~text
Redefine:
  Class C đã tồn tại
      + replacement bytes qua ClassDefinition
      -> method body đổi hợp lệ
      -> same C, same objects, static state giữ nguyên

Retransform:
  Class C đã tồn tại
      + transformer chain được áp dụng lại
      -> method body đổi hợp lệ
      -> same C, same objects, static state giữ nguyên

New ClassLoader:
  Binary name + loader mới
      -> một Class C2 khác, C2 != C
      -> static initialization/state riêng
      -> thích hợp new schema/dual versions
~~~

**Gói gọn một câu:** Redefine **thay definition của cùng Class** từ bytes mới; retransform **tái áp dụng bytecode transformers** trên cùng Class; ClassLoader mới **tạo một type identity mới** và cần quản lý migration, boundary và lifecycle.

### Tài liệu tham khảo chính thức

- Java SE 17 Instrumentation API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17 ClassDefinition API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Java SE 17 ClassFileTransformer API: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17 java.lang.instrument agent package: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17 JVM Tool Interface specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
- Java SE 17 ClassLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 JLS §12: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
