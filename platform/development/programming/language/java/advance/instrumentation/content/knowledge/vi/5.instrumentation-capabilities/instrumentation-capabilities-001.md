# Manifest khai báo khả năng khác với khả năng JVM thực sự hỗ trợ

## 1. Vấn đề: khai báo `true` không phải bằng chứng tính năng đã dùng được

Khi đóng gói Java agent, ta có thể đặt các thuộc tính như sau trong `META-INF/MANIFEST.MF`:

~~~text
Premain-Class: demo.agent.CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

Nhiều người hiểu nhầm rằng ba dòng `Can-*` đã **bật chắc chắn** những tính năng tương ứng. Trên thực tế, các dòng này là **khai báo nhu cầu của agent**; JVM vẫn có quyền không cung cấp một capability tùy chọn. Hơn nữa, ngay cả khi JVM báo có capability, từng lớp cụ thể và từng thay đổi classfile vẫn phải đáp ứng điều kiện riêng.

Một tình huống điển hình:

- Agent JAR có `Can-Retransform-Classes: true`.
- `premain` gọi `Instrumentation.isRetransformClassesSupported()` và nhận `false` trên một JVM/cấu hình không cung cấp khả năng này.
- Nếu vẫn gọi `addTransformer(transformer, true)` hoặc `retransformClasses(...)`, thao tác yêu cầu retransformation có thể ném `UnsupportedOperationException`.
- Agent vẫn có thể dùng `addTransformer(transformer)` để quan sát hoặc biến đổi **những lần nạp lớp mới**, miễn cơ chế instrumentation thông thường đang hoạt động.

**Mục tiêu bài học:** biết phân biệt thông tin trong manifest, kết quả truy vấn capability thực tế, khả năng sửa từng class và sự hợp lệ của phép biến đổi; triển khai kiểm tra và phương án fallback trước khi gọi API có điều kiện.

## 2. Bốn tầng quyết định một thao tác có thành công hay không

Không nên gom mọi điều kiện thành một cờ duy nhất. Hãy lần lượt hỏi bốn câu:

| Tầng | Câu hỏi | Kiểm tra / nguồn sự thật | Kết luận có thể rút ra |
|---|---|---|---|
| 1. **Khai báo của agent** | JAR có yêu cầu capability này không? | `Can-Retransform-Classes`, `Can-Redefine-Classes`, `Can-Set-Native-Method-Prefix` trong main manifest | Agent **yêu cầu** quyền; chưa có bảo đảm JVM cấp |
| 2. **Capability của JVM đang chạy** | JVM hiện tại có thực sự cung cấp khả năng đã yêu cầu? | `Instrumentation.isRetransformClassesSupported()`, `isRedefineClassesSupported()`, `isNativeMethodPrefixSupported()` | Có thể quyết định gọi hay bỏ qua nhóm API tương ứng |
| 3. **Lớp đích** | Đối tượng `Class<?>` này có thể bị sửa không? | `Instrumentation.isModifiableClass(targetClass)` | Nếu `false`, không thực hiện retransform/redefine lớp đó |
| 4. **Phép biến đổi cụ thể** | Classfile mới có hợp lệ và nằm trong giới hạn được JVM cho phép không? | Validator, verifier, exception từ API và kiểm thử runtime | Có thể thất bại dù các kiểm tra capability trước đó đều `true` |

Sơ đồ quyết định:

~~~text
Manifest yêu cầu feature?
    |
    +-- Không --> không dùng API phụ thuộc feature đó
    |
    +-- Có
         |
         v
JVM đang chạy báo is...Supported() = true?
    |
    +-- Không --> bỏ qua / degrade / báo lỗi theo chính sách agent
    |
    +-- Có
         |
         v
Nếu sửa class đã nạp: isModifiableClass(target) = true?
    |
    +-- Không --> bỏ qua target / báo không hỗ trợ
    |
    +-- Có
         |
         v
Thử thao tác hợp lệ: retransformClasses / redefineClasses
         |
         +-- Lỗi classfile, giới hạn cấu trúc, lỗi liên kết ...
         |       --> ghi nhận và xử lý theo chính sách
         |
         +-- Thành công --> xác minh hành vi mới
~~~

Hai tầng sau cùng dành cho **retransform/redefine class đã nạp**. Trường hợp chỉ dùng transformer tại **lần định nghĩa class mới**, bạn không cần bật các manifest flag đó.

## 3. Ba thuộc tính `Can-*` có ý nghĩa gì?

Các thuộc tính này xuất hiện trong **main section** của manifest agent JAR. Giá trị được hiểu là Boolean; `true` (không phân biệt chữ hoa/chữ thường) yêu cầu khả năng, giá trị khác hoặc vắng thuộc tính được hiểu là `false`. Giá trị mặc định là `false`.

| Manifest attribute | Agent xin khả năng | API truy vấn | API chịu ảnh hưởng |
|---|---|---|---|
| `Can-Retransform-Classes: true` | Yêu cầu retransform các lớp đã nạp | `isRetransformClassesSupported()` | `addTransformer(t, true)`, `retransformClasses(...)` |
| `Can-Redefine-Classes: true` | Yêu cầu redefine lớp đã nạp bằng classfile được cung cấp | `isRedefineClassesSupported()` | `redefineClasses(ClassDefinition...)` |
| `Can-Set-Native-Method-Prefix: true` | Yêu cầu hỗ trợ prefix cho việc phân giải tên phương thức native sau biến đổi | `isNativeMethodPrefixSupported()` | `setNativeMethodPrefix(t, prefix)` |

**Phân biệt:**

- `Premain-Class` xác định entry point của agent khởi động bằng `-javaagent`; nó **không** thể thay thế các cờ `Can-*`.
- `Agent-Class` dùng cho agent được nạp động trên JVM hỗ trợ; không tự cấp khả năng retransform/redefine.
- `Can-Retransform-Classes` **không đồng nghĩa** với `Can-Redefine-Classes`. Có thể cần tính năng này mà không cần tính năng kia.
- `Can-Set-Native-Method-Prefix` không có nghĩa JVM cho phép sửa tùy ý native code. Native method không có Java bytecode body để chèn lệnh; prefix hỗ trợ cách dùng wrapper và cơ chế tìm implementation native.
- Những flag này không xác nhận ứng dụng đã instrument thành công, không kiểm tra class nào đã được nạp, và không khẳng định class bytes sinh ra là hợp lệ.

### 3.1. Tại sao hai điều kiện phải cùng đúng?

Theo hợp đồng `java.lang.instrument`, retransformation hoặc redefinition là **khả năng tùy chọn của JVM**. Đối với mỗi tính năng:

~~~text
Yêu cầu của agent JAR = true
            VÀ
Khả năng JVM/cấu hình hiện tại = supported
            ↓
is...Supported() trả true
~~~

Các tình huống:

| Manifest của agent | JVM/cấu hình có capability | Kết quả truy vấn capability của agent | Nên làm gì? |
|---|---|---|---|
| Không khai báo / `false` | Có | `false` | Không dùng capability đó; nếu đủ, chỉ transform khi load |
| Không khai báo / `false` | Không | `false` | Không dùng capability đó |
| `true` | Không | `false` | Graceful fallback hoặc fail-fast theo yêu cầu |
| `true` | Có | `true` | Có thể tiến tới **kiểm tra class và thao tác**, chưa bảo đảm thành công |

Bảng áp dụng tương tự cho ba feature, với phương thức `is...Supported()` tương ứng. **Đọc manifest để biết “agent muốn gì”; truy vấn `Instrumentation` để biết “runtime này thực sự cho phép gì”.**

### 3.2. Capability có thay đổi sau mỗi lần gọi không?

Ba phương thức `isRetransformClassesSupported()`, `isRedefineClassesSupported()` và `isNativeMethodPrefixSupported()` được đặc tả trả **cùng một kết quả ở các lần gọi trong một JVM instance**. Vì thế agent có thể truy vấn một lần khi `premain`/`agentmain` khởi động, lưu vào một đối tượng cấu hình capability bất biến và đưa quyết định nhất quán cho những thành phần cần dùng.

Điều đó khác với trạng thái **một class có nằm trong danh sách lớp đã nạp, có thể sửa hay không**, vốn cần xét đúng đối tượng `Class<?>`. Không kết luận chỉ từ capability tổng quát.

## 4. `isModifiableClass` là phép kiểm tra riêng

Giả sử:

~~~java
boolean retransformEnabled = inst.isRetransformClassesSupported();
boolean modifiable = inst.isModifiableClass(Target.class);
~~~

Hai Boolean không có quan hệ bao hàm. Theo API:

- `isModifiableClass(c)` kiểm tra **class đó có thuộc loại modifiable** hay không.
- Nó **không phụ thuộc vào giá trị** `isRetransformClassesSupported()` hay `isRedefineClassesSupported()`.
- Để thực sự retransform, cần **cả** `isRetransformClassesSupported() == true` và `isModifiableClass(c) == true`.
- Để redefine, cần **cả** `isRedefineClassesSupported() == true` và `isModifiableClass(c) == true`.
- **Primitive class** và **array class** không bao giờ modifiable. Ví dụ `int.class`, `int[].class`, `String[].class` đều trả `false` với `isModifiableClass`.

Lưu ý: `isModifiableClass(c) == true` **không chứng minh mọi thay đổi của class đều hợp lệ**. Một JVM có thể cho phép sửa body phương thức nhưng không cho thay đổi cấu trúc class, field, method, superclass hoặc những đặc tính nhất định. `UnsupportedOperationException`, `UnmodifiableClassException`, `ClassFormatError`, `UnsupportedClassVersionError` hoặc `LinkageError` vẫn có thể xuất hiện theo loại thao tác và class bytes.

### Class identity và class loader

Khi kiểm tra lớp thật, hãy giữ đối tượng `Class<?>` đã tìm được; đừng chọn lớp chỉ bằng tên chuỗi. Hai loader khác nhau có thể định nghĩa hai class **cùng binary name nhưng khác identity**. Kết quả `isModifiableClass` và mục tiêu `retransformClasses` phải gắn với **đúng class object** trong JVM, không phải tên class do công cụ bên ngoài phỏng đoán.

Đặc biệt, đừng gọi `Class.forName` một cách tùy tiện trong `premain` chỉ để “kiểm tra có thể instrument không”, nếu mục tiêu là chặn **lần nạp class đầu tiên**. Việc tra cứu có thể khiến lớp được nạp trước khi transformer đăng ký.

## 5. Những API nhìn giống nhau nhưng có điều kiện khác nhau

### 5.1. `addTransformer(transformer)`: không đòi retransformation

~~~java
inst.addTransformer(transformer);
~~~

Tương đương với `inst.addTransformer(transformer, false)`. Nó đăng ký transformer **không có khả năng nhận callback retransform mới**, nhưng vẫn có thể được gọi khi JVM định nghĩa một class mới hoặc khi class được redefine. Đây là lựa chọn hợp lệ cho Java agent chỉ cần instrument lúc nạp lớp.

Không nên khai báo `Can-Retransform-Classes: true` chỉ vì agent có `ClassFileTransformer`. Hãy khai báo khi thật sự cần **chạy lại transform đối với lớp đã nạp**.

### 5.2. `addTransformer(transformer, true)`: yêu cầu thêm capability

~~~java
if (inst.isRetransformClassesSupported()) {
    inst.addTransformer(transformer, true);
} else {
    inst.addTransformer(transformer); // Chỉ load-time/redefinition callbacks.
}
~~~

Nếu gọi overload `true` khi cấu hình JVM không cho phép retransformation, `addTransformer` có thể ném `UnsupportedOperationException`. Cách kiểm tra trước giúp chương trình có nhánh fallback rõ ràng.

**Quan trọng:** đăng ký với `canRetransform=true` chỉ nói transformer có thể tham gia **lượt retransform được yêu cầu sau này**. Nó không khiến JVM tự đi qua toàn bộ `getAllLoadedClasses()` để gọi lại transformer.

### 5.3. `retransformClasses(c)`: yêu cầu chạy lại chuỗi biến đổi

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

Đây là **mẫu sử dụng API minh họa**. `targetClass` phải là một đối tượng `Class<?>` hợp lệ đã lấy từ JVM, và đoạn code thật cần khai báo/bắt `UnmodifiableClassException`, xử lý lỗi verifier/linkage cùng chính sách bảo vệ ứng dụng.

- Với transformer đăng ký `canRetransform=true`, JVM gọi lại callback cho lượt retransform.
- Với transformer đăng ký `canRetransform=false`, callback **không** được gọi lại trong lượt đó; JVM tái sử dụng kết quả transform trước theo cơ chế đặc tả.
- Lớp đang có active stack frames có thể tiếp tục chạy bytecode của phiên bản cũ cho các frame đó; lời gọi mới dùng định nghĩa mới.
- `retransformClasses` không chạy lại static initializer của class.

### 5.4. `redefineClasses(definitions)`: thay định nghĩa bằng classfile đầu vào

`redefineClasses` nhận `ClassDefinition` chứa class đích và mảng byte của định nghĩa thay thế. Cần `isRedefineClassesSupported()` cùng `isModifiableClass`, rồi **kiểm tra bytes và giới hạn thay đổi**. Khác với retransform, bạn chủ động cung cấp định nghĩa mới; công việc của công cụ là bảo đảm classfile phù hợp. Thành công của `isRedefineClassesSupported()` **không** bảo đảm mọi `ClassDefinition` đều được chấp nhận.

Nếu một lượt redefine/retransform trên nhóm class ném exception thì theo hợp đồng của API, toàn bộ lượt đó không được áp dụng. Tuy nhiên agent vẫn phải báo lỗi và tránh tiếp tục giả định class đã được sửa.

### 5.5. `setNativeMethodPrefix`: capability riêng, bài toán riêng

Phương thức:

~~~java
inst.setNativeMethodPrefix(transformer, "$myAgent$");
~~~

chỉ nên gọi khi **`isNativeMethodPrefixSupported()` là `true`** và `transformer` đã được đăng ký. Phương thức này hỗ trợ xử lý resolution của native method khi transformer tạo wrapper Java và đổi tên phương thức native trong classfile; nó **không tạo wrapper tự động**. Nếu capability không có, có thể gặp `UnsupportedOperationException`; nếu transformer chưa được đăng ký, có thể gặp `IllegalArgumentException`.

Sơ đồ ý tưởng:

~~~text
Native method trước khi instrument:
    native long calculate(long input);

Sau khi có classfile transformation hợp lệ:
    long calculate(long input) {
        // Đo thời gian, rồi gọi native method đã đổi tên.
        return $myAgent$calculate(input);
    }
    native long $myAgent$calculate(long input);

Native prefix hỗ trợ JVM tìm JNI implementation theo quy tắc resolution.
~~~

Đây là **mô tả nguyên lý**, không phải chương trình Java độc lập: để chạy cần native library/JNI và một transformer thực sự tạo bytecode hợp lệ. Không khai báo capability này cho agent chỉ instrument phương thức Java thông thường.

## 6. Thực hành Java 17+: cùng một agent, hai manifest

Thí nghiệm dưới đây chứng minh ba điểm: **không khai báo capability** sẽ cho kết quả kiểm tra khác với **yêu cầu capability khi JVM hỗ trợ**; `isModifiableClass` là phép kiểm tra độc lập; **load-time transformer** vẫn có ích khi retransform/redefine chưa được cấp.

Ví dụ chỉ quan sát lớp `demo.app.Work` và trả `null`, nên không sửa bytecode. Yêu cầu duy nhất là JDK 17 trở lên có công cụ `javac`, `jar`, `java` và hỗ trợ startup Java agents.

### 6.1. Cây thư mục

~~~text
capability-demo/
├── Manifest-basic.mf
├── Manifest-requested.mf
└── src/
    ├── demo/
    │   ├── agent/
    │   │   └── CapabilityAgent.java
    │   └── app/
    │       ├── App.java
    │       └── Work.java
    └── ...
~~~

Phần `...` trong sơ đồ chỉ biểu diễn có thể có thư mục output sau khi build; ba tệp Java và hai manifest nêu trên là **đầy đủ** cho ví dụ.

### 6.2. Tệp `src/demo/agent/CapabilityAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class CapabilityAgent {
    private CapabilityAgent() {}

    public static void premain(String args, Instrumentation inst) {
        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();
        boolean canNativePrefix = inst.isNativeMethodPrefixSupported();

        System.out.println("[agent] retransform=" + canRetransform);
        System.out.println("[agent] redefine=" + canRedefine);
        System.out.println("[agent] nativePrefix=" + canNativePrefix);

        // Primitive và array class luôn không modifiable.
        System.out.println("[agent] int[] modifiable="
                + inst.isModifiableClass(int[].class));

        // Java 17: ClassFileTransformer không phải functional interface;
        // override rõ ràng một trong hai phương thức transform.
        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classBytes) {

                if ("demo/app/Work".equals(className)) {
                    System.out.println("[agent] observed demo.app.Work");
                }
                return null; // Không thay đổi class bytes.
            }
        };

        // JVM có thể retransform: đăng ký transformer capable.
        // JVM không hỗ trợ: vẫn quan sát được lần nạp class mới.
        inst.addTransformer(observer, canRetransform);
        System.out.println("[agent] transformer canRetransform="
                + canRetransform);
    }
}
~~~

**Lý do ví dụ dùng anonymous class thay vì lambda:** `ClassFileTransformer` trong JDK 17 có hai overload `transform(...)` với phần triển khai mặc định; nó **không phải functional interface** để khởi tạo bằng biểu thức lambda. Viết anonymous class và override rõ overload 6 tham số giúp tránh lỗi biên dịch.

Việc `inst.addTransformer(observer, canRetransform)` dùng kết quả query tại runtime **không tự thực hiện retransform**. Trên JVM báo `false`, callback vẫn được đăng ký dạng không retransform-capable để nhận lần nạp class mới.

### 6.3. Tệp `src/demo/app/App.java`

~~~java
package demo.app;

public final class App {
    private App() {}

    public static void main(String[] args)
            throws ReflectiveOperationException {

        System.out.println("[app] main");
        Class<?> workClass = Class.forName("demo.app.Work");
        workClass.getMethod("run").invoke(null);
    }
}
~~~

Ứng dụng chủ động yêu cầu nạp `Work` bằng reflection sau khi in dòng `[app] main`. Nó không cần gọi agent API.

### 6.4. Tệp `src/demo/app/Work.java`

~~~java
package demo.app;

public final class Work {
    private Work() {}

    public static void run() {
        System.out.println("[app] Work.run");
    }
}
~~~

### 6.5. Hai tệp manifest

**`Manifest-basic.mf`** (chỉ cung cấp entry point):

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent

~~~

**`Manifest-requested.mf`** (yêu cầu cả ba capability tùy chọn):

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true

~~~

Phần trống cuối manifest ở hai code block đại diện cho newline kết thúc file manifest. Tất cả thuộc tính được đặt trong **main section**, không đặt dưới một entry riêng của JAR.

### 6.6. Biên dịch và đóng gói

Chạy từ thư mục `capability-demo`. Trên Bash:

~~~bash
mkdir -p out/agent out/app
~~~

Trên Windows PowerShell, thay lệnh tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Sau đó chạy:

~~~bash
javac --release 17 -d out/agent src/demo/agent/CapabilityAgent.java
javac --release 17 -d out/app src/demo/app/App.java src/demo/app/Work.java

jar cfm out/agent-basic.jar Manifest-basic.mf -C out/agent .
jar cfm out/agent-requested.jar Manifest-requested.mf -C out/agent .
~~~

Hai JAR chứa **cùng bytecode agent**, chỉ khác manifest. Để xác nhận manifest thực sự nằm trong JAR, có thể dùng `jar tf out/agent-basic.jar` và `jar tf out/agent-requested.jar` kiểm tra `META-INF/MANIFEST.MF`; trích xuất vào thư mục kiểm tra riêng nếu cần xem nội dung.

### 6.7. Chạy JAR không yêu cầu capability

~~~bash
java -javaagent:out/agent-basic.jar -cp out/app demo.app.App
~~~

Theo hợp đồng manifest (các capability tùy chọn **không được yêu cầu**), đầu ra dự kiến:

~~~text
[agent] retransform=false
[agent] redefine=false
[agent] nativePrefix=false
[agent] int[] modifiable=false
[agent] transformer canRetransform=false
[app] main
[agent] observed demo.app.Work
[app] Work.run
~~~

Có ba điểm cần quan sát:

1. Các query capability đều `false` vì JAR **không xin** ba quyền tương ứng.
2. `int[].class` không modifiable, không phụ thuộc flag manifest.
3. Transformer **vẫn nhận class definition** và quan sát `demo.app.Work` dù không xin retransform. Lý do là việc biến đổi lúc class **được nạp lần đầu** khác với yêu cầu retransform class **đã nạp**.

Trong một JVM có thêm agent hoặc custom loader tải `demo.app.Work` từ sớm, thời điểm callback có thể khác; thứ tự đầu ra trên dành cho ví dụ tự chạy, không có tác nhân khác nạp trước lớp mục tiêu.

### 6.8. Chạy JAR yêu cầu cả ba capability

~~~bash
java -javaagent:out/agent-requested.jar -cp out/app demo.app.App
~~~

Trên bản **HotSpot JDK 17 thông thường hỗ trợ cả ba capability**, kết quả dự kiến:

~~~text
[agent] retransform=true
[agent] redefine=true
[agent] nativePrefix=true
[agent] int[] modifiable=false
[agent] transformer canRetransform=true
[app] main
[agent] observed demo.app.Work
[app] Work.run
~~~

Đây là **kết quả có điều kiện theo JVM**: nếu một JVM/VM configuration không hỗ trợ một capability đã yêu cầu, dòng tương ứng sẽ in `false`, đồng thời `canRetransform` dùng khi đăng ký transformer sẽ phản ánh giá trị thực. Chương trình vẫn chạy với đường load-time instrumentation cơ bản.

Chúng ta không có cơ sở coi output `true/true/true` là hợp đồng cho mọi vendor, mọi cấu hình và mọi phiên bản Java. Chính vì thế phải **in và sử dụng kết quả truy vấn**, không suy diễn từ những dòng manifest.

## 7. Nếu JVM báo `false` thì agent nên làm gì?

Không có một chính sách phù hợp cho tất cả công cụ. Chọn theo yêu cầu thực tế:

| Nhu cầu của agent | Capability thiếu | Hành vi phù hợp |
|---|---|---|
| Chỉ muốn theo dõi lớp mới nạp | Retransform | Vẫn gọi `addTransformer(transformer)`; ghi rõ phạm vi chỉ bao gồm các lần nạp về sau |
| Cần quan sát class đã nạp, nhưng có thể chấp nhận không đầy đủ | Retransform | Degrade: không sửa class cũ, phát cảnh báo chính xác về phạm vi quan sát |
| Bắt buộc hot patch class đang chạy để bảo đảm chức năng | Redefine hoặc retransform tùy thiết kế | Fail-fast, không đưa hệ thống vào trạng thái tưởng đã vá |
| Chỉ instrument phương thức Java thường | Native method prefix | Không yêu cầu native prefix; không phát sinh chức năng thiếu |
| Cần wrapper native method để ghi metric | Native method prefix | Tắt riêng nhánh native instrumentation hoặc từ chối khởi động nếu đó là tính năng bắt buộc |
| JVM báo capability true, nhưng một lớp không modifiable | Theo class | Bỏ qua lớp đó và báo lý do; không tiếp tục gọi thao tác sẽ thất bại |

Một quy tắc tốt: phân biệt **required capabilities** và **optional capabilities** trong thiết kế agent. Không ghi một log `Instrumentation ready` rồi giả định mọi tính năng đã sẵn sàng. Thay vào đó, log trạng thái rõ:

~~~text
Capabilities: retransform=..., redefine=..., nativePrefix=...
Effective mode: load-time only / load-time + retransformation
Target: skipped, class not modifiable / eligible for operation
~~~

Đây là **mẫu log mô tả**, không phải output cố định từ Java API. Các nhãn cụ thể do agent triển khai quyết định.

## 8. Mẫu kiểm tra capability thực tế trước khi retransform

Đoạn sau thể hiện **mẫu thiết kế** sau khi đã lấy được `Instrumentation inst` từ agent và có `Class<?> target` chính xác. Nó **không phải tệp Java độc lập** vì `inst` và `target` do agent thực cung cấp:

~~~java
if (!inst.isRetransformClassesSupported()) {
    System.err.println("Retransformation is not available");
} else if (!inst.isModifiableClass(target)) {
    System.err.println("Target class is not modifiable");
} else {
    try {
        inst.retransformClasses(target);
        System.out.println("Retransformation completed");
    } catch (java.lang.instrument.UnmodifiableClassException ex) {
        System.err.println("Target became unavailable: " + ex);
    } catch (UnsupportedOperationException ex) {
        System.err.println("Unsupported retransform operation: " + ex);
    } catch (LinkageError ex) {
        System.err.println("Invalid transformed class/linkage: " + ex);
    }
}
~~~

**Cảnh báo về tên thông báo:** `retransformClasses` có thể ném các lỗi khác theo contract (ví dụ `ClassFormatError`, `UnsupportedClassVersionError`). Đoạn này gom một số lỗi qua `LinkageError` để minh họa phân nhánh; chính sách production phải quyết định lỗi nào có thể xử lý cục bộ, lỗi nào phải báo fatal. **Không dùng catch `Throwable` để nuốt âm thầm** một thất bại, rồi báo đã instrument thành công.

Ngay cả khi callback của transformer nhận `classBeingRedefined` và class bytes, một lần retransform vẫn phải tôn trọng cấu trúc class, verifier và tính tương thích. Nếu transformer trả `null`, không có nghĩa nó đã thay bytecode của class.

## 9. Những ngộ nhận dễ tạo lỗi thực tế

### Nhầm 1 — “Manifest là một lệnh bắt JVM bật capability”

Sai. Manifest **khai báo nhu cầu**, còn JVM/cấu hình hiện tại cung cấp capability hay không là điều kiện bên ngoài. Agent phải kiểm tra bằng `Instrumentation` và có cách xử lý khi kết quả không đúng kỳ vọng.

### Nhầm 2 — “`isModifiableClass == true` có nghĩa `retransformClasses` chắc chắn chạy”

Sai. Tính modifiable là điều kiện về class, **độc lập** với việc capability retransform/redefine có được cấp hay không. Và một class modifiable vẫn có thể bị từ chối nếu thao tác cố đổi cấu trúc không được phép hoặc cung cấp classfile sai.

### Nhầm 3 — “Không có `Can-Retransform-Classes` thì `ClassFileTransformer` không chạy”

Sai. Transformer load-time vẫn được gọi qua `addTransformer(transformer)` cho định nghĩa class mới. Capability retransform liên quan tới **lượt yêu cầu xử lý lại class đã nạp** và việc callback có tham gia lượt đó hay không.

### Nhầm 4 — “`addTransformer(t, true)` tự sửa mọi lớp hiện tại”

Sai. Nó chỉ đăng ký transformer có khả năng tham gia **những lượt retransform về sau**. Cần thao tác `retransformClasses(...)` riêng cho class phù hợp; class đã nạp không được hồi tố tự động chỉ vì agent vừa đăng ký.

### Nhầm 5 — “Có `Can-Redefine-Classes` là có thể thêm field/method tùy ý”

Sai. Việc redefine/retransform bị giới hạn bởi hợp đồng JVM TI và classfile format; có thể thay đổi bytecode của method hợp lệ nhưng nhiều thay đổi schema hoặc quan hệ kế thừa không được hỗ trợ. Test một implementation cụ thể trước khi deploy.

### Nhầm 6 — “Native method prefix dùng để đổi tên hàm Java bất kỳ”

Sai. `setNativeMethodPrefix` hỗ trợ **native method resolution** sau khi transformer làm wrapper, không phải API đổi tên class/method tổng quát hay instrument trực tiếp machine code của thư viện native.

### Nhầm 7 — “Có JDK 17 nghĩa là mọi JVM đều hỗ trợ ba capability”

Sai. Đây là optional features với JVM implementation và cấu hình cụ thể. Các JDK thường gặp có thể hỗ trợ, nhưng agent di động phải đưa ra quyết định từ `Instrumentation.is...Supported()` của **process đang chạy**.

### Nhầm 8 — “Java code in `premain` kiểm tra capability thành công là xong”

Chưa đủ. Agent production cần kiểm tra đúng class loader, class target, tính hợp lệ của bytes, exception khi thao tác và chứng cứ hành vi. Các phương thức kiểm tra capability giúp **chọn phương án hợp lệ**, không tự kiểm thử sản phẩm instrumentation.

## 10. Checklist kiểm thử trên nhiều JVM/cấu hình

Trước khi phát hành agent, kiểm tra:

1. **Đúng JAR**: kiểm tra `META-INF/MANIFEST.MF` thực sự chứa thuộc tính main section, không chỉ nhìn file manifest ở workspace trước khi đóng gói.
2. **Đúng runtime**: ghi lại Java vendor, Java version và JVM options từ môi trường đích khi cần chẩn đoán, tránh dùng kết quả từ máy developer để kết luận cho server.
3. **Biên hỗ trợ**: kiểm tra cả ba `is...Supported()` đối với feature agent cần; không bật bừa những feature agent không dùng.
4. **Đúng overload**: `addTransformer(t)` cho load-time; `addTransformer(t,true)` chỉ khi hỗ trợ retransform và thực sự cần.
5. **Target modifiability**: với lớp đã nạp, dùng đúng `Class<?>` và `isModifiableClass`; thử cả array/primitive như ca kiểm thử luôn bị từ chối.
6. **Lỗi phép biến đổi**: kiểm thử bytes sai, thay đổi cấu trúc không được hỗ trợ và đường fallback khi class không sửa được.
7. **Không nhầm success log**: “transformer registered” khác “class retransformed” và càng khác “hành vi đã thay đổi đúng”.
8. **Tương thích thư viện bytecode**: JDK classfile version, method frames, các loader/module và thứ tự nhiều transformers phải được kiểm tra.
9. **Tác động vận hành**: đo startup overhead, kiểm soát I/O trong callback, không giữ ứng dụng ở trạng thái đã patch một phần khi capability bắt buộc thiếu.

Một ma trận thử nghiệm tối thiểu:

| Kịch bản | Điều cần quan sát | Kết quả hợp lý |
|---|---|---|
| Agent không khai báo `Can-*` | Ba `is...Supported` + transformer lúc class load | Feature tùy chọn trả `false`; load-time callback vẫn hoạt động |
| Agent khai báo cả ba `Can-*`, JVM hỗ trợ | Ba `is...Supported` | Có thể trả `true`, nhưng đây mới là điều kiện bước đầu |
| Agent khai báo `true`, JVM không hỗ trợ một capability | Query và nhánh fallback | Query của feature đó `false`; không gọi API yêu cầu feature |
| Class array/primitive | `isModifiableClass` | Luôn `false`, dù manifest/JVM hỗ trợ retransform |
| Class thường có thể sửa và feature được hỗ trợ | `retransformClasses` hoặc `redefineClasses` | Còn phải kiểm tra classfile và giới hạn phép biến đổi |
| Transformer không có `canRetransform` | Lượt retransform của class đã nạp | Callback ấy không chạy lại; JVM tái sử dụng biến đổi trước theo đặc tả |

## 11. Tự đánh giá kiến thức

**Câu 1.** `Can-Retransform-Classes: true` có đủ để gọi `retransformClasses` chưa?

> Chưa. Cần `isRetransformClassesSupported()` báo `true` và class mục tiêu phải modifiable, sau đó classfile thay đổi vẫn phải hợp lệ.

**Câu 2.** JVM hỗ trợ retransform, nhưng manifest agent thiếu `Can-Retransform-Classes`. `isRetransformClassesSupported()` trả gì theo contract?

> `false` đối với cấu hình khả năng mà agent đó nhận được. Có sẵn tính năng ở phía JVM chỉ là một trong hai điều kiện.

**Câu 3.** Nếu `isModifiableClass(int[].class)` trả `false` khi tất cả capability query khác đều `true`, có mâu thuẫn không?

> Không. Primitive/array classes vốn không modifiable. Hỗ trợ capability toàn cục không có nghĩa mọi class đều có thể sửa.

**Câu 4.** Một agent chỉ muốn log khi lớp nghiệp vụ được nạp có cần `Can-Retransform-Classes` không?

> Không. `addTransformer(transformer)` đủ để nhận class definitions mới. Chỉ khi cần chạy lại transformer trên những class đã nạp thì mới cần retransform capability.

**Câu 5.** Khác biệt giữa `retransformClasses` và `redefineClasses`?

> `retransformClasses` yêu cầu chạy lại chuỗi xử lý từ nguồn class bytes phù hợp và gọi lại các transformer được đăng ký `canRetransform=true`; `redefineClasses` nhận classfile bytes mới dưới dạng `ClassDefinition`. Cả hai chịu giới hạn class modification.

**Câu 6.** Vì sao `isNativeMethodPrefixSupported` có thể `false` dù agent không có lỗi?

> Đây là capability tùy chọn. Đặc biệt, một agent không yêu cầu `Can-Set-Native-Method-Prefix: true` sẽ không có capability đó. Nếu agent không instrument native methods, việc thiếu feature này có thể hoàn toàn bình thường.

**Câu 7.** Trên một JVM báo `true` cho `isRetransformClassesSupported()`, chạy `addTransformer(t,true)` đã đảm bảo method của class được sửa chưa?

> Chưa. Mới chỉ đăng ký transformer; cần đúng class, yêu cầu retransform hoặc đợi class definition mới, và transformer phải trả class bytes mới hợp lệ thay vì `null` nếu muốn thay mã.

## 12. Nguồn đặc tả chính thức

- Java SE 17, `java.lang.instrument` — startup agent, manifest và ba capability tùy chọn: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java SE 17, `Instrumentation` — `is...Supported`, `isModifiableClass`, `addTransformer`, `retransformClasses`, `redefineClasses`, `setNativeMethodPrefix`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer` — callback và cơ chế retransformation-capable transformer: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `ClassDefinition` — cặp class và classfile bytes cho redefine: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- JVM Tool Interface — giới hạn class redefine/retransform: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
