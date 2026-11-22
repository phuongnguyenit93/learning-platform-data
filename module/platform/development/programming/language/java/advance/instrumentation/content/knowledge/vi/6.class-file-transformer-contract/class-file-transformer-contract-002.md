# Hai dạng `ClassFileTransformer.transform`: có và không có tham số `Module`

Khi viết Java agent, ta thường cài đặt `java.lang.instrument.ClassFileTransformer` để nhận class file bytes trước khi JVM định nghĩa hoặc cập nhật một lớp. Từ Java 9, interface này hỗ trợ **hai overload của `transform`**:

1. Dạng **năm tham số** có từ Java 5, không nhận `Module`.
2. Dạng **sáu tham số** có từ Java 9, nhận thêm `java.lang.Module` ở vị trí đầu tiên.

Điểm tinh tế nhất không phải chỉ là “dạng mới có thêm một tham số”: **hai method mặc định được nối với nhau theo một chiều**. Trên JDK 17, JVM có thể đi vào dạng sáu tham số; nếu transformer không override dạng đó, phần mặc định của interface sẽ gọi dạng năm tham số. Vì thế transformer cũ vẫn tiếp tục hoạt động. Ngược lại, override **chỉ** dạng sáu tham số không làm dạng năm tham số tự chuyển tiếp lên dạng mới.

Bài học thuộc phần **Hợp đồng transformer** và đi vào chữ ký, thứ tự dispatch, vai trò của `Module`, giá trị trả về và cách tự chứng minh method nào được gọi. Các ví dụ dùng Java 17+, không yêu cầu thư viện bytecode bên ngoài.

## 1. Hai chữ ký chính xác

Interface có hai method như sau (bỏ chú thích Javadoc để dễ quan sát):

```java
package java.lang.instrument;

import java.security.ProtectionDomain;

public interface ClassFileTransformer {
    default byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {
        return null;
    }

    default byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {
        return transform(
                loader,
                className,
                classBeingRedefined,
                protectionDomain,
                classfileBuffer);
    }
}
```

Đây là **mã mô tả phần quan trọng của hợp đồng Java 17**, không phải file người học được phép khai báo lại trong package `java.lang.instrument`. `ClassFileTransformer` đã được JDK cung cấp; mã ứng dụng chỉ cần `implements ClassFileTransformer`.

### Dạng năm tham số (di sản trước Java 9)

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
```

- Không có thông tin `Module` trong tham số.
- Phù hợp khi logic chỉ dựa vào tên lớp, class loader, bytes, `ProtectionDomain` và trạng thái redefine/retransform.
- Mã agent Java 8 thường override dạng này. Trong Java 8, đây là method trừu tượng của interface; trên Java 9+, JDK cung cấp phần cài đặt mặc định trả `null`.
- Trên JDK 17, một transformer chỉ override dạng năm tham số **vẫn được JVM gọi thông qua cơ chế chuyển tiếp từ dạng sáu tham số mặc định**.

### Dạng sáu tham số (từ Java 9)

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
```

- `Module` là **tham số đầu tiên**, còn năm tham số phía sau giữ cùng thứ tự.
- `module` thuộc `java.lang.Module`, thể hiện module chứa lớp đang được transform.
- Nó cho phép lọc lớp theo ranh giới JPMS, phân biệt named/unnamed module hoặc xác định module trước khi quyết định biến đổi.
- Chữ ký này đòi hỏi Java 9+; nếu cần biên dịch cho Java 8 thì không thể tham chiếu `java.lang.Module` trong source Java 8.

Cả hai chữ ký cùng trả `byte[]`, có thể khai báo `throws IllegalClassFormatException`, và được cài đặt bằng `@Override`. Tên method vẫn là **`transform`** với chữ thường; `Module` đứng ở cuối hoặc thay `ClassLoader` bằng `Module` đều là chữ ký khác, không phải overload được JVM quy định gọi.

## 2. Quy tắc dispatch: hiểu đúng hướng chuyển tiếp

Hãy hình dung đường gọi trên JDK 17:

```text
JVM chuẩn bị transform một class
             |
             v
transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])
             |
             +-- Transformer override sáu tham số?
             |       |
             |       +-- Có --> chạy logic sáu tham số
             |       |          (không tự gọi method năm tham số)
             |       |
             |       +-- Không --> default method sáu tham số
             |                       |
             |                       v
             |                 gọi transform(ClassLoader, String,
             |                                Class<?>, ProtectionDomain, byte[])
             |                       |
             |                       +-- Override năm tham số? --> chạy logic cũ
             |                       |
             |                       +-- Không --> default năm tham số: return null
             v
JVM nhận byte[] mới hoặc null
```

Đối chiếu theo từng kiểu triển khai:

| Class implement `ClassFileTransformer` | Khi JVM JDK 17 transform lớp | Vì sao? |
|---|---|---|
| Chỉ override `transform` năm tham số | Logic **năm tham số** chạy | Default sáu tham số gọi tiếp năm tham số |
| Chỉ override `transform` sáu tham số | Logic **sáu tham số** chạy | JVM vào overload có `Module` |
| Override **cả hai** | Logic **sáu tham số** chạy | Override sáu tham số thay thế phần default chuyển tiếp |
| Không override method nào | Không có logic tùy biến; nhận `null` | Default sáu tham số → default năm tham số → `null` |

**Không có quy tắc gọi cả hai method lần lượt.** Nếu một class override cả hai, method năm tham số chỉ chạy khi một đoạn code **chủ động gọi nó**, hoặc khi được gọi trực tiếp qua chữ ký năm tham số trong hoàn cảnh khác; JVM Java 9+ không tự chạy method thứ hai sau khi đã gọi override sáu tham số.

**Không có chuyển tiếp mặc định từ năm lên sáu.** Một lời gọi Java trực tiếp tới method năm tham số của class chỉ override method sáu tham số sẽ dùng phần default của method năm tham số (`return null`). Đây là lý do không được coi hai chữ ký là hai API đồng nghĩa hoàn toàn.

Cả hai method đều là `default` ở Java 17 nên **`ClassFileTransformer` không phải functional interface**; cú pháp lambda một method không phù hợp:

```java
// Không hợp lệ trên Java 17:
// ClassFileTransformer transformer = (loader, name, type, domain, bytes) -> null;
```

Thay vào đó dùng class, anonymous class hoặc một thư viện cung cấp implementation thực sự.

## 3. `Module` là thông tin về lớp đang được biến đổi

Khi nhận `Module module`, giá trị này mô tả **module của lớp đích đang được JVM xử lý**. Nó không mặc nhiên là module của agent, của `ClassFileTransformer`, hoặc của thư viện ASM/Byte Buddy.

Ví dụ:

- Lớp ứng dụng nằm trên **classpath** thường thuộc một **unnamed module** của class loader định nghĩa nó. `module.isNamed()` là `false`; `module.getName()` là `null`.
- Một lớp thuộc `java.base` nằm trong **named module** tên `java.base`; `module.isNamed()` là `true`, `module.getName()` trả `"java.base"`.
- Một lớp ứng dụng được đóng gói trong module JPMS có `module-info.class` có thể thuộc named module như `com.example.app`.

Đoạn kiểm tra thông thường:

```java
String moduleLabel;
if (module == null) {
    moduleLabel = "<unavailable>";
} else if (module.isNamed()) {
    moduleLabel = module.getName();
} else {
    moduleLabel = "<unnamed>";
}
```

Đây là **đoạn code trong thân method**, không phải một chương trình độc lập. Cách kiểm tra `null` giúp logging phòng thủ khi được gọi thủ công hoặc trong hoàn cảnh đặc thù; tài liệu API mô tả đây là module của class đang được transform.

### Vì sao không chỉ dựa vào `ClassLoader`?

Trong hệ JPMS, **class loader** và **module** là hai khái niệm khác nhau:

- `ClassLoader` trả lời “ai định nghĩa lớp?”; bootstrap loader được biểu diễn bằng `null` trong callback.
- `Module` trả lời “lớp này thuộc module nào?”.
- Nhiều named module có thể được định nghĩa bởi cùng một loader. Vì thế so sánh `loader` không đủ để phân biệt mọi module.
- Có nhiều unnamed module tương ứng với nhiều loader. Tên `null` của unnamed module không đủ để phân biệt tất cả; khi cần định danh, giữ/so sánh đối tượng `Module` và class loader phù hợp.

Trong transformer mới, có thể lọc an toàn theo cả tên nội bộ của lớp và module:

```java
if ("com/example/Target".equals(className)
        && module != null
        && module.isNamed()
        && "com.example.app".equals(module.getName())) {
    // Áp dụng logic cho class có tên/module mong muốn.
}
```

Đây là **một nhánh điều kiện minh họa**, không phải class runnable độc lập. Với lớp nằm trên classpath, điều kiện `module.isNamed()` sẽ không thỏa. Việc có `Module` trong callback **không tự mở package**, không tự sửa `exports` hoặc `opens`, cũng không tự cấp mọi quyền reflection. Những vấn đề truy cập module phải được giải quyết theo cơ chế JPMS/JVM tương ứng.

## 4. Những tham số còn lại giống nhau

| Tham số | Ý nghĩa | Lưu ý dễ sai |
|---|---|---|
| `ClassLoader loader` | Loader định nghĩa lớp | Có thể `null` cho bootstrap loader |
| `String className` | Tên lớp ở **dạng nội bộ JVM**, ví dụ `demo/Probe` | Dùng `/`, không phải `demo.Probe`; API cho phép giá trị `null` trong một số tình huống |
| `Class<?> classBeingRedefined` | `Class` hiện hữu nếu liên quan tới redefine/retransform | Trong lần định nghĩa lớp mới thường là `null` |
| `ProtectionDomain protectionDomain` | Security/protection domain của lớp | Không suy ra module name chỉ từ domain |
| `byte[] classfileBuffer` | Mảng byte class file đầu vào của lần transform | **Không sửa trực tiếp mảng đầu vào**; trả mảng mới nếu có biến đổi |

Ở dạng sáu tham số, bảng trên vẫn áp dụng, chỉ thêm `Module module` trước `loader`.

**Ví dụ lọc class được nạp mới:**

```java
if (!"demo/Probe".equals(className)) {
    return null;
}
if (classBeingRedefined == null) {
    System.out.println("New class definition: " + className);
}
return null;
```

Code này chưa tạo bytecode mới và không đại diện toàn bộ method. Dùng literal bên trái của `.equals` tránh lỗi khi `className == null`. Khi retransform hoặc redefine, `classBeingRedefined` có thể không null; điều đó **không** tự cho biết transformer đã được đăng ký với `canRetransform=true`.

### Hợp đồng `return` không thay đổi theo overload

```java
return null;             // Giữ nguyên bytecode ở bước transform hiện tại.
return transformedBytes; // Đưa byte[] class file mới vào chuỗi xử lý.
```

Mảng `transformedBytes` trong ví dụ là biến **chỉ tồn tại nếu code của bạn thực sự tạo nó**. Không thể chỉ thay tên method hoặc thêm `Module` là đã sửa bytecode. Khi muốn sửa, cần code tạo class file hợp lệ (ASM, Byte Buddy hoặc logic bytecode phù hợp), rồi trả về một **mảng mới**; JVM sẽ tiếp tục kiểm tra và xử lý các transformer khác.

Nếu không có biến đổi, **trả `null`** là đúng hợp đồng, không phải lỗi. Nếu transformer ném exception không bắt, đặc tả vẫn cho phép các transformer tiếp theo chạy và JVM tiếp tục thử định nghĩa/cập nhật lớp; không nên dựa vào exception để “ngăn JVM nạp class”. `IllegalClassFormatException` giúp báo lỗi đầu vào class file trong quá trình debug nhưng theo hợp đồng vẫn tương đương không thực hiện transform đối với bước đó.

## 5. Ví dụ Java 17+ chạy được: ba transformer, một lớp đích

Ta sẽ dùng một agent JAR đăng ký **ba transformer** theo thứ tự:

1. `LegacyTransformer` chỉ override **năm tham số**.
2. `ModuleTransformer` chỉ override **sáu tham số**.
3. `BothTransformer` override **cả hai**.

Mọi transformer chỉ quan sát lớp `demo.Probe`, in log rồi `return null`. Kết quả minh họa rõ đường gọi thực tế; không cần một thư viện bytecode hoặc thao tác ghi lại class file.

Thư mục:

```text
transform-module-demo/
├── src/demo/
│   ├── ObserveAgent.java
│   ├── Probe.java
│   └── App.java
└── agent.mf
```

### 5.1. Lớp đích `src/demo/Probe.java`

```java
package demo;

public final class Probe {
    private Probe() {
    }
}
```

Lớp `Probe` đơn giản để tách hành vi callback ra khỏi việc sửa instruction. Nó được nạp trong quá trình chạy chương trình ở bước sau.

### 5.2. Ứng dụng `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("[app] before loading Probe");
        Class<?> type = Class.forName("demo.Probe");
        System.out.println("[app] loaded=" + type.getName());
    }
}
```

Dùng `Class.forName("demo.Probe")` sau dòng log đầu tiên để **yêu cầu nạp lớp theo tên tại runtime**. `App` không tham chiếu trực tiếp `Probe.class` hoặc `new Probe()` trong bytecode, nên ví dụ dễ nhìn thấy thời điểm bộ nạp lớp được kích hoạt.

Nếu không dùng agent:

```bash
java -cp out demo.App
```

Stdout:

```text
[app] before loading Probe
[app] loaded=demo.Probe
```

Lệnh này chỉ chạy được **sau bước biên dịch ở mục 5.5**.

### 5.3. Agent và ba transformer `src/demo/ObserveAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    private ObserveAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new LegacyTransformer());
        inst.addTransformer(new ModuleTransformer());
        inst.addTransformer(new BothTransformer());
        System.out.println("[agent] registered 3 transformers");
    }
}

// Legacy: chỉ override method 5 tham số.
final class LegacyTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[legacy-5] demo/Probe");
        }
        return null;
    }
}

// Java 9+: chỉ override method 6 tham số.
final class ModuleTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            String name = module != null && module.isNamed()
                    ? module.getName()
                    : "<unnamed>";
            System.out.println(
                    "[module-6] demo/Probe module=" + name);
        }
        return null;
    }
}

// Có cả hai: trên JDK 17, JVM chọn overload 6 tham số.
final class BothTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[both-5] demo/Probe");
        }
        return null;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] bytes) {

        if ("demo/Probe".equals(className)) {
            System.out.println("[both-6] demo/Probe");
        }
        return null;
    }
}
```

Giải thích từng chỗ:

- `ObserveAgent.premain` là điểm vào startup agent. Chức năng của nó trong bài này chỉ là **đăng ký** ba instance transformer.
- `inst.addTransformer(...)` mặc định tương đương `addTransformer(transformer, false)`; ví dụ chỉ cần sự kiện nạp lớp mới.
- `LegacyTransformer` không override overload có `Module`, nên khi JVM vào overload đó, **default sáu tham số** gọi logic năm tham số và in `[legacy-5]`.
- `ModuleTransformer` override overload sáu tham số, nhận `Module` của `demo.Probe`; vì `Probe` chạy từ `-cp out`, nó thuộc **unnamed module**, nên in `<unnamed>`.
- `BothTransformer` override cả hai; JDK 17 gọi overload sáu tham số, nên in `[both-6]`. Dòng `[both-5]` **không xuất hiện** chỉ vì method có tồn tại.
- Cả ba trả `null`, vì vậy `demo.Probe` được nạp như trước, không phát sinh bản bytecode thay thế.

Bốn class (`ObserveAgent`, `LegacyTransformer`, `ModuleTransformer`, `BothTransformer`) được khai báo trong **một source file**. Java cho phép nhiều top-level class không `public` trong cùng file với một top-level class `public`; `javac` tạo các file `.class` riêng, tất cả đều phải có trong agent JAR.

### 5.4. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.ObserveAgent

```

`Premain-Class` chỉ lớp có `premain`, không chỉ một class transformer. JVM gọi `premain`, rồi agent mới đăng ký các transformer. Phần `META-INF/MANIFEST.MF` thực tế của JAR sẽ chứa header này. Có dòng trống cuối file manifest như ví dụ.

### 5.5. Biên dịch, đóng JAR, chạy

Từ thư mục `transform-module-demo`, với JDK 17+:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/Probe.java src/demo/App.java src/demo/ObserveAgent.java

jar --create --file observe-agent.jar --manifest agent.mf -C out demo/ObserveAgent.class -C out demo/LegacyTransformer.class -C out demo/ModuleTransformer.class -C out demo/BothTransformer.class

java -javaagent:observe-agent.jar -cp out demo.App
```

Mỗi lệnh `jar -C out ...` đóng đúng `.class` tương ứng vào JAR. Không có file class nào cần tải từ Maven/Gradle. Để tránh nhầm class nội bộ với `public class`, kiểm tra danh sách archive:

```bash
jar --list --file observe-agent.jar
```

Phải có `META-INF/MANIFEST.MF`, `demo/ObserveAgent.class`, `demo/LegacyTransformer.class`, `demo/ModuleTransformer.class` và `demo/BothTransformer.class`.

**Stdout dự kiến trên OpenJDK/HotSpot Java 17 trong trường hợp nạp mới thành công:**

```text
[agent] registered 3 transformers
[app] before loading Probe
[legacy-5] demo/Probe
[module-6] demo/Probe module=<unnamed>
[both-6] demo/Probe
[app] loaded=demo.Probe
```

Đối chiếu từng dòng:

1. Agent được gọi và hoàn tất đăng ký **trước khi application `main` bắt đầu**.
2. App in `before loading Probe`, sau đó mới gọi `Class.forName`.
3. `LegacyTransformer` chạy method năm tham số thông qua **default chuyển tiếp**.
4. `ModuleTransformer` nhận module của lớp nằm trên classpath, in tên `<unnamed>` do logic hiển thị của ví dụ.
5. `BothTransformer` chỉ in `[both-6]`; method `[both-5]` không chạy tự động.
6. App tiếp tục chạy bình thường, vì cả ba transformer trả `null`.

Đây là mô hình thực thi có kiểm soát; các công cụ profiler, agent khác hoặc JVM tùy biến có thể thêm log khác hoặc ảnh hưởng thời điểm nạp lớp. Trên JDK thông thường, ví dụ đã lọc callback theo `demo/Probe` để loại bỏ log của các lớp khác.

## 6. Khi nào nên chọn chữ ký nào?

| Tình huống | Cách chọn |
|---|---|
| Duy trì agent viết từ Java 8 và chỉ cần thao tác theo tên lớp/loader | Override **năm tham số**, giữ tương thích nguồn Java cũ |
| Agent mới đặt mục tiêu Java 17+ và cần kiểm tra module | Override **sáu tham số** |
| Logic hoàn toàn không dựa vào module, nhưng agent target Java 9+ | Cả hai có thể dùng; một override năm tham số vẫn chạy qua default sáu tham số |
| Cần vận hành được trên Java 8 **và** xử lý JPMS khi Java 9+ | Thiết kế biên dịch/đóng gói theo phiên bản và cân nhắc khả năng tải class riêng; không dùng `Module` trong class phải nạp trên Java 8 |
| Muốn override cả hai để kiểm soát hai lời gọi khác nhau | Có thể, nhưng phải **chủ động** dùng chung logic nếu không muốn chúng khác biệt |
| Muốn sửa class đã load qua retransform | Chữ ký không quyết định quyền này; phải kiểm tra và đăng ký `canRetransform` phù hợp |
| Chỉ cần quan sát callback | In/log có điều kiện rồi `return null` |

**Nếu override cả hai và muốn dùng chung logic**, có thể cho method sáu tham số gọi một helper riêng. Minh họa:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain domain,
        byte[] bytes) {
    return transformCore(module, loader, className, bytes);
}
```

Đây là **trích đoạn trong một class có helper `transformCore` do bạn định nghĩa**, không phải chương trình độc lập. Với logic có sử dụng `Module`, helper nên nhận tham số module rõ ràng. Nếu hỗ trợ lời gọi năm tham số từ bên ngoài, hãy quyết định hành vi khi module không có trong lời gọi đó; tránh gọi qua lại hai overload theo chu trình vô hạn.

Một cách dùng đúng của dạng năm tham số với class cũ là giữ nguyên code đã hoạt động và nâng phiên bản runtime sau khi test. **Không cần thêm overload sáu tham số chỉ để “bắt buộc tương thích Java 9+”**: default đã tồn tại vì mục đích tương thích đó.

## 7. Nạp mới, redefine và retransform: cách dispatch không thay quyền hạn

`ClassFileTransformer` có thể tham gia nhiều giai đoạn, nhưng việc method nào được override **không tự điều khiển khi nào callback xảy ra**.

### Nạp mới (`load-time transformation`)

Agent đăng ký transformer trước khi class được định nghĩa. JVM gọi callback với bytes đầu vào tương ứng. Trong ví dụ, `classBeingRedefined == null` vì nạp mới.

### Định nghĩa lại (`redefineClasses`)

Nếu JVM hỗ trợ redefine và lớp có thể được sửa, API có thể cung cấp class file bytes mới cho lớp đang tồn tại. Transformer được đăng ký phù hợp có thể tham gia quá trình. Chữ ký có/không có `Module` vẫn tuân theo cơ chế dispatch đã mô tả.

### Biến đổi lại (`retransformClasses`)

Cần phân biệt hai cách đăng ký:

```java
inst.addTransformer(transformer);        // canRetransform=false
inst.addTransformer(transformer, true);  // canRetransform=true
```

Ở ví dụ này, `transformer` là biến chứa một object implement `ClassFileTransformer`, còn `inst` là reference `Instrumentation` trong agent; hai dòng chỉ là **minh họa lựa chọn**, không gọi cả hai cho cùng một instance trong chương trình thật.

- Với `canRetransform=false`, transformer được gọi lúc nạp/định nghĩa lại; khi retransform, kết quả biến đổi trước đó của nhóm transformer không hỗ trợ retransform được **tái áp dụng** mà callback không nhất thiết chạy lại.
- Với `canRetransform=true`, transformer có thể được JVM gọi lại khi retransform.
- `true` chỉ có tác dụng nếu JVM và cấu hình agent hỗ trợ. Kiểm tra `inst.isRetransformClassesSupported()`, `inst.isModifiableClass(clazz)` và thuộc tính manifest `Can-Retransform-Classes: true` khi phù hợp.

Overload có `Module` **không** có quyền retransform cao hơn overload năm tham số. Cũng không thể suy từ `classBeingRedefined != null` rằng một method cụ thể được gọi do `redefine` hay `retransform`; phải dựa vào ngữ cảnh sự kiện.

Trong quá trình retransform/redefine, output phải là class file hợp lệ theo giới hạn áp dụng cho lớp đang tồn tại. Một transformer được gọi đúng method nhưng trả bytes không hợp lệ vẫn có thể gây lỗi verify/redefine.

## 8. `Module` hữu ích nhưng không bảo đảm có thể truy cập mọi lớp

Trong Java Platform Module System, package có thể không được export hoặc open cho module khác. `module` giúp nhận diện bối cảnh của lớp mục tiêu, nhưng không mặc nhiên:

- cho agent quyền đọc mọi module;
- mở tất cả package cho reflection;
- cho phép class loader nhìn thấy bất kỳ dependency nào;
- tạo hoặc thay đổi `module-info.class`;
- cho phép instrument mọi class trong module mà không vướng giới hạn JVM.

Khi cần thay đổi quan hệ module, `Instrumentation.redefineModule(...)` là API **riêng**, với contract và điều kiện riêng. Trước khi thêm thao tác này cần xem yêu cầu cụ thể, không nên thực hiện chỉ vì transformer nhận được `Module`.

**Hai ví dụ phân biệt:**

- Agent chạy trong unnamed module, class cần xem thuộc named module `java.base`: callback có thể thấy `module.getName()` là `"java.base"` nếu lớp đó được transform vào thời điểm thích hợp.
- Agent chạy trong unnamed module, class mục tiêu chạy trên classpath: `module.isNamed()` là `false`, dù agent và mục tiêu có thể do các class loader khác nhau định nghĩa.

Không lấy tên module của agent bằng `ObserveAgent.class.getModule()` rồi dùng nó thay tham số `module` trong callback; hai đối tượng diễn tả **hai vị trí khác nhau**.

## 9. Những lỗi dễ gặp khi tự cài đặt

### 9.1. Định nghĩa sai chữ ký

```java
// Không override overload chuẩn: sai vị trí Module.
public byte[] transform(ClassLoader loader, Module module, String name,
                        Class<?> clazz, ProtectionDomain domain, byte[] bytes) {
    return null;
}
```

Ví dụ trên là **đoạn method sai để học**, không phải code runnable cần đưa vào ứng dụng. Nếu thêm `@Override`, `javac` báo lỗi vì không có method tương ứng trong interface; nếu bỏ annotation, method mới chỉ là overload riêng không được JVM gọi như callback chuẩn.

**Mẹo:** luôn dùng `@Override` và kiểm tra đúng sáu hoặc năm kiểu tham số; `Module` ở đầu trong dạng sáu.

### 9.2. Nghĩ rằng chỉ override sáu tham số thì lời gọi năm cũng chạy

Sai. Default năm tham số trả `null`; không có cơ chế tự chuyển từ năm tham số sang sáu tham số. Nếu hỗ trợ các môi trường chủ động gọi dạng cũ, hãy chọn một phương thức chia sẻ logic minh bạch.

### 9.3. Nghĩ rằng override cả hai sẽ được callback hai lần

Sai trên JDK 17 trong cùng sự kiện: một đường dispatch chọn override sáu tham số. Nếu nhìn thấy nhiều log, trước tiên kiểm tra số transformer được đăng ký, số sự kiện nạp/redefine/retransform, và liệu code có tự gọi method khác hay không.

### 9.4. So sánh class name sai

```java
// Sai khi className là tên nội bộ:
if ("demo.Probe".equals(className)) {
    // Không match "demo/Probe".
}
```

Dùng `"demo/Probe"` với dấu `/`. Lọc cẩn thận cả trường hợp `className == null`.

### 9.5. Gọi `module.getName().equals(...)` trên unnamed module

Với unnamed module, `module.getName()` trả `null`. Dùng:

```java
if (module != null
        && module.isNamed()
        && "com.example.app".equals(module.getName())) {
    // Một named module cụ thể.
}
```

Đây chỉ là nhánh điều kiện trong callback. Không giả định mỗi class trên classpath có một tên module văn bản.

### 9.6. Sửa mảng đầu vào hoặc trả dữ liệu không phải class file

`classfileBuffer` phải được coi là bất biến. Nếu muốn thay đổi, tạo mảng mới chứa class file hợp lệ rồi `return`; nếu không sửa, `return null`. Không thể đổi một method Java an toàn bằng cách thay chuỗi byte tùy tiện mà bỏ qua constant pool, stack maps hoặc verifier.

### 9.7. Hiểu sai vai trò của exception

Callback ném exception không đảm bảo ngừng nạp class. Tài liệu `ClassFileTransformer` quy định các transformer tiếp theo vẫn có thể chạy; JVM tiếp tục nỗ lực định nghĩa/cập nhật lớp. Do đó phải log và xử lý lỗi chủ động, không dựa vào `throw` như cơ chế chặn ứng dụng.

### 9.8. Viết lambda và gặp lỗi biên dịch

Hai method đều có phần cài đặt mặc định ở Java 17, nên `ClassFileTransformer` không có một abstract method làm đích cho lambda. Dùng `new ClassFileTransformer() { @Override ... }` hoặc một class cụ thể.

### 9.9. Nhầm lỗi `Module` với lỗi `ClassLoader`

Nếu transformer chạy nhưng filter theo module không match, xác minh lớp là named hay unnamed module **và** ai là loader của lớp đó. Một tên lớp dạng `demo/Probe` có thể xuất hiện ở nhiều loader, có thể có danh tính module khác nhau.

## 10. Một bảng “triệu chứng → kiểm tra”

| Quan sát | Giải thích có thể xảy ra | Kiểm tra tiếp |
|---|---|---|
| Override năm tham số vẫn in log trên Java 17 | Default sáu tham số chuyển về năm | Đúng hành vi tương thích |
| Override sáu tham số in log, năm không in | Method sáu đã được override | Đúng hành vi dispatch |
| Cài cả hai nhưng chỉ thấy sáu | JVM chọn overload sáu | Không có callback thứ hai mặc định |
| Đăng ký transformer nhưng chẳng thấy log lớp mong muốn | Lớp đã load, filter sai hoặc chưa xảy ra sự kiện | Kiểm tra thời điểm đăng ký, `className`, loader/module |
| `module.getName()` là `null` | Unnamed module | Dùng `module.isNamed()` hoặc kiểm tra null |
| Trả `null`, ứng dụng không đổi | Transformer chỉ quan sát | Muốn sửa phải tạo bytes hợp lệ |
| Có bytes mới nhưng JVM báo lỗi | Class file bị biến đổi sai hoặc vi phạm giới hạn cập nhật | Kiểm tra verifier, cấu trúc class, retransform/redefine constraints |
| `addTransformer(t, true)` không được hỗ trợ | JVM/agent không hỗ trợ retransform | Kiểm tra capability và manifest |
| Compiler báo method không override | Sai chữ ký hoặc nhầm phiên bản Java | So khớp API JDK dùng để compile |
| Log xuất hiện nhiều lần không đoán được | Có nhiều sự kiện/đăng ký/agent | Theo dõi thread, class loader, module, tình huống load/retransform |

## 11. Câu hỏi tự kiểm tra

**1.** Trên JDK 17, class transformer chỉ override dạng năm tham số. Khi JVM đi vào callback có `Module`, điều gì xảy ra?

**Đáp án:** Default sáu tham số chuyển tiếp và gọi logic năm tham số của class đó.

**2.** Class chỉ override dạng sáu tham số. Nếu một thư viện gọi trực tiếp overload năm tham số, logic sáu tham số có chạy không?

**Đáp án:** Không. Phần mặc định năm tham số trả `null` nếu class không override nó.

**3.** Class override cả hai. Một sự kiện nạp class trên JDK 17 làm cả hai method chạy không?

**Đáp án:** Không. JVM gọi overload sáu tham số đã được override; method năm tham số không chạy tự động.

**4.** `Module module` trong callback có phải module của Java agent không?

**Đáp án:** Không; đó là module chứa lớp đang được biến đổi.

**5.** Với lớp `demo.Probe` trên classpath, `module.getName()` thường trả gì?

**Đáp án:** `null`, vì đây là unnamed module; có thể dùng `module.isNamed()` để kiểm tra.

**6.** Vì sao `ClassFileTransformer` không dùng trực tiếp lambda trên Java 17?

**Đáp án:** Hai overload đều là default method, nên interface không có một abstract method duy nhất làm đích cho lambda.

**7.** Đăng ký bằng `addTransformer(t)` khác `addTransformer(t, true)` thế nào?

**Đáp án:** Dạng mặc định không nhận lại callback khi retransform, trong khi `true` có thể nhận callback ở lần retransform nếu runtime/agent hỗ trợ. Cả hai vẫn dùng cùng quy tắc chọn overload.

**8.** Nếu transformer chỉ `return null`, `Module` có khiến JVM đổi bytecode không?

**Đáp án:** Không; `Module` chỉ là ngữ cảnh bổ sung, không phải chỉ thị sửa class file.

## 12. Kết luận cần nhớ

- **Năm tham số**: hợp đồng cũ, không nhận `Module`; trên JDK 17 default trả `null` nếu không override.
- **Sáu tham số**: hợp đồng Java 9+, có `Module` ở đầu; default của nó **gọi dạng năm tham số**.
- **Chỉ override năm** vẫn hoạt động trên JDK mới nhờ default delegation; **chỉ override sáu** được gọi trực tiếp khi JVM dùng overload mới.
- **Override cả hai** không có nghĩa callback chạy hai lần; trên JDK 17 method sáu tham số được chọn.
- `Module` mô tả **lớp đích**, bổ sung cho `ClassLoader`; với lớp trên classpath, thường là unnamed module.
- Các quy tắc `return null`, trả `byte[]` mới, không sửa `classfileBuffer`, và kiểm tra tính hợp lệ của bytecode áp dụng **cho cả hai chữ ký**.

## Tài liệu tham khảo chính thức

- Oracle Java 17 — [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): cả hai overload, default delegation và hợp đồng bytes.
- Oracle Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, retransform/redefine, hỗ trợ capability.
- Oracle Java 17 — [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `isNamed()`, `getName()`, quan hệ module.
- Oracle Java 17 — [Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách khởi động Java agent.
