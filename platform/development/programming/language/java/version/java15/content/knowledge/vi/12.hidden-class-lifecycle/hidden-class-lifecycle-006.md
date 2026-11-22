# Giới hạn instrumentation, redefine và retransform đối với hidden class trong Java

> **Bối cảnh:** Bài thuộc nhóm **Vòng đời lớp ẩn** (hidden class) của module Java 15. Hidden class được chuẩn hóa từ **Java 15** và vẫn có trong các JDK hiện đại (Java 17, 21, 25…). Bài này giải thích chính xác điều mà Java agent và JVM Tool Interface (JVM TI) **có thể quan sát**, điều chúng **không thể sửa** sau khi hidden class đã được định nghĩa, và những cách thiết kế thay thế hợp lệ. Toàn bộ ví dụ sử dụng API ổn định trên **JDK 17+**, không sử dụng cơ chế tạo lớp lỗi thời hoặc preview feature.

## 1. Kết luận cần nhớ trước tiên

Một hidden class có thể được tạo bằng:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(bytes, true);
Class<?> hidden = hiddenLookup.lookupClass();
```

Đoạn trên là **snippet**, giả định `bytes` là classfile hợp lệ thuộc cùng runtime package với lookup class, và được gọi tại nơi có lookup đủ quyền. Đây không phải chương trình độc lập; chương trình đầy đủ nằm ở phần 6.

Hidden class là class thật của JVM, nhưng **không có binary name thông thường để các class khác liên kết hoặc để class loader tìm theo tên**. Với các API instrumentation chính thức:

- `hidden.isHidden()` trả `true`.
- `Instrumentation.isModifiableClass(hidden)` trả `false`: hidden class **không phải mục tiêu hợp lệ** cho redefinition hoặc retransformation bằng Java agent.
- `Instrumentation.retransformClasses(hidden)` **không thể dùng để sửa** hidden class đã định nghĩa.
- `Instrumentation.redefineClasses(new ClassDefinition(hidden, ...))` cũng **không thể dùng để thay định nghĩa** hidden class.
- Điều đó **không có nghĩa hidden class vô hình**: nó có thể xuất hiện trong `Instrumentation.getAllLoadedClasses()`, được nhận qua `Class<?>`, reflection, method handles và những công cụ chẩn đoán có khả năng phù hợp.
- Nếu chủ động **biến đổi classfile bytes trước khi gọi** `defineHiddenClass`, ta đang kiểm soát **đầu vào của lần định nghĩa mới**, **không phải** redefine/retransform một hidden class đã tồn tại.

**Ba việc thường bị nhầm là:** (1) quan sát một lớp đã nạp, (2) can thiệp bytecode trong lúc **định nghĩa** lớp, và (3) **sửa lại** định nghĩa lớp đã tồn tại. Hidden class giới hạn mạnh việc thứ ba, nhưng không biến hai việc đầu thành bất khả thi trong mọi bối cảnh.

## 2. Bốn thuật ngữ: instrumentation, transformation, retransformation, redefinition

| Thuật ngữ | Mục tiêu | Thời điểm thường dùng | Công cụ Java |
| --- | --- | --- | --- |
| **Instrumentation** | Thu thập thông tin hoặc bổ sung logic theo dõi, kiểm thử, đo coverage, profiling… | Trước và/hoặc trong khi chương trình chạy | Agent sử dụng `java.lang.instrument`, JVM TI; đôi khi các công cụ khác |
| **Class-file transformation** | Biến đổi bytecode đầu vào của một **lần định nghĩa lớp** | Trước khi JVM hoàn tất định nghĩa lớp | `ClassFileTransformer.transform(...)` cho các luồng định nghĩa tương ứng; hoặc framework tự biến đổi bytes trước `defineHiddenClass` |
| **Retransformation** | Chạy lại chuỗi biến đổi trên class **đã được nạp** | Sau lần định nghĩa đầu tiên | `Instrumentation.retransformClasses(Class<?>...)` |
| **Redefinition** | Cung cấp classfile bytes thay thế cho class **đã được nạp** | Sau lần định nghĩa đầu tiên | `Instrumentation.redefineClasses(ClassDefinition...)` |

`Instrumentation` là interface dùng trong **Java agent**, khác với khả năng tùy ý sửa mọi class của JVM. `ClassFileTransformer` định nghĩa callback có thể được đăng ký bằng `addTransformer(...)`. Quyền và hành vi của agent phụ thuộc khả năng JVM, thời điểm đăng ký, kiểu lớp và quy tắc của API.

### Hai phương thức sửa lớp đã nạp khác nhau ra sao?

**Retransform**:

```java
void retransformClasses(Class<?>... classes)
        throws UnmodifiableClassException;
```

- Dùng quá trình transformation để tạo phiên bản mới cho class đã tồn tại.
- Những transformer đăng ký với `canRetransform=true` có thể được gọi lại trong quá trình này.
- Yêu cầu cả **JVM/agent hỗ trợ retransformation** và **class là modifiable**.
- Không phải cách tạo ra một `Class<?>` hoàn toàn mới với danh tính khác.

**Redefine**:

```java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
```

- Truyền class đích và **classfile bytes thay thế** thông qua `ClassDefinition`.
- Yêu cầu JVM/agent hỗ trợ redefinition và class đích modifiable.
- Được dùng cho nhu cầu cập nhật mã phương thức trên class đã tồn tại khi các giới hạn tương thích được đáp ứng.
- **Không** cho phép tùy ý đổi cấu trúc class; với các class bình thường, quy tắc JVM vẫn hạn chế việc thêm/xóa/đổi tên field hoặc method, đổi chữ ký, hệ kế thừa và một số thuộc tính classfile.

**Điểm chung cho hidden class:** cả hai thao tác đều không phải cách hợp lệ để sửa một hidden class đã được định nghĩa. Việc JVM hỗ trợ **tính năng ở mức toàn cục** không khiến một hidden class cụ thể trở thành modifiable.

## 3. Hidden class là gì và vì sao có giới hạn này?

Hidden class được định nghĩa bằng `MethodHandles.Lookup.defineHiddenClass(...)`, không thông qua quy trình nạp lớp có binary name thông thường. JVM có thể cấp cho nó một tên runtime có hậu tố riêng, nhưng tên này **không phải binary name có thể tìm bằng `Class.forName`**.

Ví dụ một lần chạy có thể cho tên mang hình thức:

```text
HiddenTarget/0x0000000800c01234
```

Đây **chỉ là hình thức minh họa**. Đừng hard-code phần hậu tố: nó do JVM tạo ra và có thể khác giữa các lần chạy.

Các hệ quả:

1. `hidden.getName()` có thể in được tên runtime; việc **có tên để hiển thị** không đồng nghĩa **có binary name để tìm lại**.
2. `Class.forName(hidden.getName())` không phải cơ chế tìm hidden class.
3. Framework phải giữ `Class<?>` hoặc `MethodHandles.Lookup` được trả về từ `defineHiddenClass`, hoặc những tham chiếu trực tiếp phù hợp, nếu muốn tiếp tục thao tác.
4. Hidden class có thể có vòng đời ngắn và được **unload độc lập** với defining class loader khi không chọn `STRONG`, tùy tình trạng còn tham chiếu và garbage collector.
5. Agent không thể dựa vào “tìm lớp theo tên rồi sửa lại bytecode” như với một class thông thường.

Tài liệu `MethodHandles.Lookup` của JDK hiện hành chỉ rõ hidden class không được sửa bằng **Java agent** hoặc **tool agent qua JVM TI**. Điều này là đặc tính thiết kế, **không phải lỗi do thiếu cờ JVM**.

### Những khác biệt không liên quan đến khả năng modify

- `NESTMATE` cho phép hidden class tham gia nest của lookup class để hỗ trợ quyền truy cập `private` phù hợp. Nó **không** cho phép redefine/retransform hidden class.
- `STRONG` thay đổi quan hệ vòng đời với class loader. Nó **không** biến hidden class thành class modifiable.
- Hidden class có thể có method/field/constructor và thực thi bytecode. Nó **không** phải đối tượng mô phỏng không thể gọi.
- Hidden class không đồng nghĩa với **anonymous class** được khai báo bằng `new Interface() { ... }`. Phân loại bằng `Class.isHidden()`, không suy luận từ tên có dấu `$` hay `isAnonymousClass()`.
- Có được `Lookup` với đặc quyền mạnh **không làm** `Instrumentation.isModifiableClass(hidden)` đổi thành `true`. Đó là hai nhóm capability khác nhau.

## 4. Ba phép kiểm tra của `Instrumentation` và thứ tự quyết định

Các API chính thức trong `java.lang.instrument.Instrumentation`:

```java
boolean isModifiableClass(Class<?> theClass)
boolean isRetransformClassesSupported()
boolean isRedefineClassesSupported()
```

Cần phân biệt:

- `isModifiableClass(clazz)`: class **cụ thể** có thể được **redefine/retransform** không?
- `isRetransformClassesSupported()`: **JVM và cấu hình agent** có hỗ trợ khả năng retransformation không?
- `isRedefineClassesSupported()`: **JVM và cấu hình agent** có hỗ trợ redefinition không?

Một class thường có thể được đánh dấu modifiable nhưng agent chưa có khả năng retransform/redefine. Ngược lại, một agent có cả hai khả năng vẫn không sửa được hidden class.

Quy tắc kiểm tra trước lời gọi:

```java
if (!inst.isRetransformClassesSupported()) {
    // Không có khả năng retransform ở JVM/agent hiện tại.
} else if (!inst.isModifiableClass(target)) {
    // Class đích không được phép retransform.
} else {
    // Mới là ứng viên để thử retransform;
    // vẫn phải xử lý các lỗi hợp lệ khác.
}
```

Đây là **snippet** với `inst` và `target` đã tồn tại trong một method, không phải chương trình độc lập.

Cụ thể đối với hidden class:

```java
boolean hiddenClass = target.isHidden();
boolean modifiable = inst.isModifiableClass(target);
```

Nếu `hiddenClass` là `true` thì `modifiable` là `false` theo giới hạn hidden class. Vì vậy, **đừng nhầm hai cờ capability của agent với phép kiểm tra modifiability của class**.

### Khi lời gọi thất bại, nhận diện đúng nguyên nhân

| Tình huống | Kết quả/ngoại lệ liên quan | Cách hiểu |
| --- | --- | --- |
| Class đích không modifiable, ví dụ hidden class | `isModifiableClass=false`; `retransformClasses`/`redefineClasses` có thể ném `UnmodifiableClassException` | Giới hạn của **class cụ thể** |
| JVM/agent không hỗ trợ tính năng yêu cầu | `isRetransformClassesSupported=false` hoặc `isRedefineClassesSupported=false`; lời gọi có thể ném `UnsupportedOperationException` | Giới hạn **capability/cấu hình agent** |
| Redefine class thường với thay đổi cấu trúc không được phép | Có thể ném `UnsupportedOperationException` | Đã thử cập nhật vượt giới hạn redefinition |
| Classfile thay thế không hợp lệ | Có thể phát sinh `ClassFormatError`, `VerifyError` hoặc lỗi liên kết thích hợp | Lỗi **bytecode đầu vào**, không phải cơ chế cấp quyền sửa hidden |
| Class đích được truyền `null` | `NullPointerException` theo API | Lỗi đối số |
| Tham số method hoặc signature không khớp khi dùng method handles | Lỗi tìm/call method handle tương ứng | Vấn đề khác với modifiability |

**Không lấy một ngoại lệ duy nhất làm kết luận tổng quát:** chương trình có thể bị từ chối **trước** vì chưa có capability, và class hidden vẫn không modifiable ngay cả khi đã có capability.

## 5. Cách lấy `Instrumentation`: Java agent khởi động bằng `premain`

`Instrumentation` không phải một utility có thể lấy tùy ý bằng `new Instrumentation()`. JVM chuyển đối tượng này cho agent qua entry point hợp lệ, điển hình là `premain` khi khởi động bằng `-javaagent`.

Lưu ý:

- Trong file manifest của agent JAR, `Premain-Class` chỉ tới lớp chứa `premain`.
- Thuộc tính `Can-Retransform-Classes: true` và `Can-Redefine-Classes: true` yêu cầu các capability tương ứng **nếu JVM hỗ trợ**.
- Bật manifest capability **không** vượt qua giới hạn không modifiable của hidden class.
- Có thể có cơ chế agent được khởi chạy ở thời điểm khác, nhưng chính sách cho phép, khả năng hỗ trợ và cảnh báo của JDK có thể khác. Bài dùng **khởi động với `-javaagent`** để có kết quả dễ tái lập.
- Không thêm `--add-opens` hoặc những tùy chọn mở module chỉ để mong hidden class trở thành modifiable; đó không phải mục đích của các tùy chọn ấy.

Bài thực hành ở phần kế tiếp sử dụng hai file Java và một manifest; không cần thư viện ngoài.

## 6. Chương trình Java hoàn chỉnh: chứng minh giới hạn trên hidden class

Chương trình được kiểm chứng bằng việc biên dịch và chạy trên **OpenJDK 21**. Nó dùng cú pháp/API có sẵn trên **Java 17+**. Để tương thích Java 17 khi biên dịch bằng JDK mới hơn, có thể dùng `javac --release 17`.

Chúng ta tạo một class bình thường `HiddenTarget` làm **mẫu bytecode**, rồi định nghĩa một hidden class khác từ chính classfile ấy. Agent nhận `Instrumentation` để kiểm tra đối tượng `Class<?>` của hidden class.

### 6.1. File `HiddenModAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class HiddenModAgent {
    private static volatile Instrumentation inst;

    public static void premain(String arguments,
                               Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static Instrumentation getInstrumentation() {
        if (inst == null) {
            throw new IllegalStateException(
                    "Start with -javaagent:hidden-mod-agent.jar");
        }
        return inst;
    }
}
```

Agent giữ đối tượng `Instrumentation` ở trường `volatile` sau khi JVM gọi `premain`. Ở ví dụ này không có transformer; mục tiêu là **kiểm tra giới hạn**, chứ không sửa một class nào.

### 6.2. File `HiddenModDemo.java`

```java
import java.io.InputStream;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public class HiddenModDemo {
    public static void main(String[] args) throws Throwable {
        Instrumentation inst = HiddenModAgent.getInstrumentation();

        // Đọc classfile của một class thông thường làm bytes đầu vào.
        byte[] bytes;
        try (InputStream in = HiddenModDemo.class
                .getResourceAsStream("HiddenTarget.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing HiddenTarget.class");
            }
            bytes = in.readAllBytes();
        }

        Class<?> normal = HiddenTarget.class;

        // Từ bytes này, tạo một class KHÁC, có tính chất hidden.
        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println("normal.hidden=" + normal.isHidden());
        System.out.println("hidden.hidden=" + hidden.isHidden());
        System.out.println("hidden.modifiable="
                + inst.isModifiableClass(hidden));

        // Hidden class vẫn có thể được quan sát qua danh sách loaded.
        System.out.println("hidden.inAllLoaded="
                + Arrays.asList(inst.getAllLoadedClasses())
                        .contains(hidden));

        // Nhưng không có tên để class loader khởi tạo/tìm theo binary name.
        System.out.println("hidden.inInitiated="
                + Arrays.asList(inst.getInitiatedClasses(
                        hidden.getClassLoader())).contains(hidden));

        boolean notFound;
        try {
            Class.forName(hidden.getName(),
                    false, hidden.getClassLoader());
            notFound = false;
        } catch (ClassNotFoundException ex) {
            notFound = true;
        }
        System.out.println("hidden.nameLookupFails=" + notFound);

        // Không sửa được bằng agent, nhưng vẫn gọi được phương thức.
        MethodHandle mh = hiddenLookup.findStatic(
                hidden, "answer",
                MethodType.methodType(String.class));
        String answer = (String) mh.invokeExact();
        System.out.println("hidden.answer=" + answer);

        // Yêu cầu retransform; bị từ chối vì class không modifiable
        // hoặc vì capability không khả dụng trên JVM/agent.
        boolean retransformRejected;
        try {
            inst.retransformClasses(hidden);
            retransformRejected = false;
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException ex) {
            retransformRejected = true;
        }
        System.out.println("retransform.rejected="
                + retransformRejected);

        // Redefinition cũng không được phép trên hidden class.
        boolean redefineRejected;
        try {
            inst.redefineClasses(
                    new ClassDefinition(hidden, bytes));
            redefineRejected = false;
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException ex) {
            redefineRejected = true;
        }
        System.out.println("redefine.rejected=" + redefineRejected);
    }
}

// Cùng package, do javac biên dịch thành HiddenTarget.class.
// Class này BÌNH THƯỜNG; nó không tự trở thành hidden.
class HiddenTarget {
    static String answer() {
        return "OK";
    }
}
```

Tệp `HiddenModDemo.java` chứa **hai top-level class**: `HiddenModDemo` công khai và `HiddenTarget` package-private. `javac` tạo hai file class tương ứng từ cùng file nguồn; không phải tự đặt `HiddenTarget` vào file Java thứ ba.

### 6.3. File `MANIFEST.MF`

```text
Manifest-Version: 1.0
Premain-Class: HiddenModAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
```

Đây là nội dung manifest: lưu thành file text có kết thúc dòng bình thường, tốt nhất có một dòng trống ở cuối. Manifest yêu cầu JVM trao các capability phù hợp; khả năng thực tế vẫn được xác định bằng những phương thức `is...Supported()` của `Instrumentation`.

### 6.4. Lệnh biên dịch, đóng gói agent và chạy

Mở terminal trong thư mục chứa hai file `.java` và `MANIFEST.MF`. Các lệnh sau dùng công cụ `javac`, `jar` và `java` trong JDK 17+:

```bash
javac --release 17 -encoding UTF-8 HiddenModAgent.java HiddenModDemo.java

jar --create --file hidden-mod-agent.jar \
    --manifest MANIFEST.MF HiddenModAgent.class

java -javaagent:hidden-mod-agent.jar HiddenModDemo
```

Dấu `\` ở cuối dòng trong câu lệnh `jar` là **ký hiệu nối dòng cho shell kiểu Bash**. Nếu dùng PowerShell hoặc Command Prompt trên Windows, hãy chạy lệnh `jar` trên **một dòng**:

```text
jar --create --file hidden-mod-agent.jar --manifest MANIFEST.MF HiddenModAgent.class
```

Các tệp `HiddenModDemo.class` và `HiddenTarget.class` nằm trong classpath của ứng dụng, còn `HiddenModAgent.class` được đóng vào agent JAR. Không cần đưa cả ứng dụng vào JAR agent.

### 6.5. Stdout chính xác

Trên JDK 17+ có hỗ trợ agent Java chuẩn, chạy mã như trên cho:

```text
normal.hidden=false
hidden.hidden=true
hidden.modifiable=false
hidden.inAllLoaded=true
hidden.inInitiated=false
hidden.nameLookupFails=true
hidden.answer=OK
retransform.rejected=true
redefine.rejected=true
```

Kết quả này đã được đối chiếu bằng một lần thực thi trên OpenJDK 21. Với một JVM hạn chế capability, kết quả **retransform/redefine bị từ chối** vẫn đúng, nhưng ngoại lệ cụ thể có thể là `UnsupportedOperationException` thay vì `UnmodifiableClassException`. Vì vậy mã bắt cả hai loại và in một cờ rejection.

**Không nên** viết test yêu cầu chính xác **thông điệp** của một ngoại lệ hay hậu tố tên hidden class; các chi tiết ấy có thể phụ thuộc triển khai.

## 7. Giải thích đầy đủ từng kết quả

### 7.1. `normal.hidden=false` và `hidden.hidden=true`

`HiddenTarget.class` là class bình thường do class loader tải theo tên. `hidden` là class khác được tạo bằng `Lookup.defineHiddenClass` từ bytes của `HiddenTarget.class`. **Cùng classfile bytes không có nghĩa cùng class identity**.

Vì vậy:

```java
boolean sameClass = normal == hidden; // false
```

Đây là snippet minh họa với hai biến đã có ở chương trình chính. Không được giả định sửa hoặc nạp `HiddenTarget.class` theo cách thông thường sẽ cập nhật mọi hidden class từng được tạo từ bản bytes cũ.

### 7.2. `hidden.modifiable=false`

Đây là bằng chứng trực tiếp từ Java agent:

```java
inst.isModifiableClass(hidden)
```

Giá trị `false` thể hiện hidden class không phải mục tiêu hợp lệ cho hai nhóm cập nhật động. Không có overload `redefineHiddenClass` của `Instrumentation` để vượt giới hạn này.

Đây cũng là lý do nên **kiểm tra modifiability trước khi gọi API sửa lớp**, thay vì thử và giả định mọi class trong `getAllLoadedClasses()` đều sửa được.

### 7.3. `hidden.inAllLoaded=true`

`Instrumentation.getAllLoadedClasses()` trả một snapshot các class đang được JVM nạp, **bao gồm hidden class/interface**. Trong ví dụ, có tham chiếu mạnh `Class<?> hidden` đang sống, nên hidden class đó có mặt trong snapshot.

Điều này trả lời một hiểu lầm phổ biến: **không thể redefine không đồng nghĩa không thể nhìn thấy**.

### 7.4. `hidden.inInitiated=false`

`Instrumentation.getInitiatedClasses(loader)` mang ngữ nghĩa khác: nó liệt kê những class mà loader có thể **tìm theo tên**, gồm cơ chế nạp và liên kết tên tương ứng. API này **không liệt kê hidden class/interface** hoặc array có phần tử là hidden class.

Do đó, `getAllLoadedClasses()` và `getInitiatedClasses(...)` **không thay thế cho nhau** khi làm báo cáo về hidden class.

### 7.5. `hidden.nameLookupFails=true`

`Class.forName(hidden.getName(), false, hidden.getClassLoader())` không tìm được hidden class theo tên runtime. Đừng thiết kế registry hoặc chương trình gỡ lỗi dựa vào chuỗi `getName()` để tìm lại hidden class.

Thay vì vậy, lưu `Class<?>` hoặc `Lookup` được trả về ngay khi định nghĩa; với công cụ quan sát, dùng API enumerating phù hợp.

### 7.6. `hidden.answer=OK`

Dù không modifiable, hidden class vẫn có method `answer()` chạy được. `hiddenLookup.findStatic(...)` tạo method handle từ lookup thích hợp, rồi `invokeExact()` gọi thành công.

**Không nên nhầm “không cho sửa định nghĩa” với “không thể thi hành/không thể reflection”.** Đây là hai thuộc tính độc lập.

### 7.7. `retransform.rejected=true`

Agent đã thử gọi:

```java
inst.retransformClasses(hidden);
```

Nhưng hidden class không modifiable. Nếu tác vụ bị từ chối vì chính class, API sử dụng `UnmodifiableClassException`; nếu capability retransformation không có, `UnsupportedOperationException` cũng là tình huống có thể xảy ra.

Chương trình bắt hai loại vì mục đích minh họa **không có đường cập nhật hợp lệ** cho hidden class, không phải để đánh đồng nguyên nhân. Trong ứng dụng sản xuất, cần ghi rõ loại ngoại lệ thật và trạng thái capability để hỗ trợ chẩn đoán.

### 7.8. `redefine.rejected=true`

Agent cũng thử:

```java
inst.redefineClasses(new ClassDefinition(hidden, bytes));
```

`ClassDefinition` chứa class đích và bytes cần dùng thay thế. Dù bytes lấy từ classfile hợp lệ của `HiddenTarget`, **class đích vẫn là hidden class không modifiable**.

Nếu đã có capability redefinition, lời gọi sẽ bị từ chối do class không modifiable; nếu thiếu capability, có thể bị từ chối trước ở mức cấu hình agent/JVM. **Không được coi việc thay bytes bằng bytes giống hệt hoặc bật `NESTMATE`/`STRONG` là cách làm cho redefinition hợp lệ.**

## 8. Biến đổi bytecode trước `defineHiddenClass` không phải retransform

Một chiến lược hợp lệ cho framework **tự tạo hidden class** là kiểm soát bytecode **trước lúc JVM định nghĩa**:

```text
Mã nguồn / class mẫu / nguồn sinh bytecode
                |
                v
           byte[] gốc
                |
                v
  Sinh/biến đổi bytecode theo nhu cầu
       (trước khi định nghĩa class)
                |
                v
  Lookup.defineHiddenClass(transformedBytes, ...)
                |
                v
     Class<?> hidden đã tạo
                |
                +--> sử dụng / quan sát / gọi method
                |
                +--> KHÔNG redefine/retransform class này
```

Ví dụ pseudo-code (không phải chương trình chạy độc lập vì `transformBytecode` là API riêng của framework):

```java
byte[] original = readTemplateClassFile();
byte[] transformed = transformBytecode(original);
MethodHandles.Lookup created =
        MethodHandles.lookup().defineHiddenClass(
                transformed, true);
Class<?> generatedClass = created.lookupClass();
```

**Tính đúng đắn:** Sau biến đổi, bytes vẫn phải là **class file JVM hợp lệ**, có package tương thích và đáp ứng điều kiện của lookup. `defineHiddenClass` có thể ném `ClassFormatError`, `VerifyError`, `IllegalAccessException` hoặc lỗi tương ứng nếu dữ liệu/đặc quyền không hợp lệ.

Đây là **tạo một hidden class mới từ bytes đã được thiết kế**, không phải sửa một hidden class cũ. Không thể lấy `Class<?>` cũ rồi yêu cầu JVM “thay code trong đúng class ấy” bằng `defineHiddenClass`.

### Cập nhật mã sinh động sau khi đã tạo lớp

Khi yêu cầu nghiệp vụ đổi logic, một hướng thiết kế là:

1. Giữ **mẫu hoặc mô hình logic gốc** mà ứng dụng kiểm soát.
2. Sinh/biến đổi **bytes mới** theo phiên bản mới của logic.
3. Gọi `defineHiddenClass(...)` để tạo **một hidden class mới**, nhận `Class<?>`/`Lookup`/`MethodHandle` mới.
4. Cập nhật **điểm điều phối do ứng dụng kiểm soát**, ví dụ một registry, factory, service hoặc tham chiếu method handle, để tác vụ mới sử dụng phiên bản mới.
5. Quản lý vòng đời của tham chiếu cũ theo yêu cầu đồng thời và an toàn tài nguyên.

**Giới hạn:** các tham chiếu đang giữ instance/method handle của hidden class cũ **không tự đổi** sang hidden class mới. Chúng vẫn có class identity và hành vi cũ. Đừng mô tả đây là “hot swap cùng một lớp”; thực tế là **tạo và chọn class mới**.

## 9. Phạm vi của `ClassFileTransformer`: đừng đánh đồng với sửa sau định nghĩa

`ClassFileTransformer` là API chính thức cho các agent biến đổi classfile theo các lời gọi/điểm kích hoạt mà API quy định. Với các **lớp bình thường**, agent có thể:

- Đăng ký transformer trước khi class được định nghĩa để biến đổi bytecode ban đầu.
- Dùng `retransformClasses(...)` để chạy lại quá trình transformation nếu có capability và class modifiable.
- Dùng `redefineClasses(...)` để đưa một classfile mới vào một class modifiable, tuân thủ các giới hạn redefinition.

Với **hidden class**, cần phân biệt thêm:

- Việc một class được **quan sát** trong danh sách đã nạp hoặc một công cụ có thông tin về bytecode **không cấp quyền sửa** class đó bằng Java agent.
- Không thể dùng `retransformClasses(hidden)`/`redefineClasses(hidden)` làm vòng đời cập nhật hidden class.
- Đừng viết công cụ giả định `ClassFileTransformer.transform(...)` sẽ cung cấp một cơ chế sửa lại **mọi hidden class** sau khi chúng xuất hiện. Callback transformation và API cập nhật lớp đã nạp có **điều kiện khác nhau**.
- Nếu chính framework sở hữu bytes được đưa vào `defineHiddenClass`, **đặt logic biến đổi vào khâu sinh/chuẩn bị bytes** là hướng rõ ràng, kiểm soát được.
- Không nên khẳng định mọi JVM, framework hoặc agent sẽ báo một tập callback giống hệt nhau cho mọi kiểu lớp. Để biết một tool cụ thể quan sát được sự kiện nào, cần đọc hợp đồng và kiểm thử theo JDK/JVM mục tiêu.

### Cách cấu hình `addTransformer` cho lớp thường (minh họa)

```java
inst.addTransformer(transformer, true);
```

Dòng này là **snippet** cần có `Instrumentation inst`, một `ClassFileTransformer transformer` phù hợp, và capability retransformation. Đối số `true` **chỉ** yêu cầu transformer có khả năng tham gia retransformation; nó **không biến hidden class thành modifiable**.

Một transformer có thể trả `null` khi không thay đổi classfile; điều này khác với việc gọi `retransformClasses(...)` và nhận ngoại lệ.

## 10. Java agent và JVM TI: quan sát khác với sửa

Không nên đồng nhất hai mệnh đề sau:

- “Tool có thể **liệt kê hoặc quan sát** hidden class.”
- “Tool có thể **thay định nghĩa** hidden class.”

JVM TI có nhiều API phục vụ profiler, debugger và agent ở mức JVM. Một số thông tin có thể được đọc hoặc quan sát tùy capability và implementation. Nhưng hidden class không modifiable bởi **RedefineClasses**/**RetransformClasses** theo cơ chế tương ứng.

Với Java agent (`java.lang.instrument`):

| Nhu cầu | Có thể làm với hidden class? | API/gợi ý |
| --- | --- | --- |
| Biết một `Class<?>` có hidden không | **Có** | `clazz.isHidden()` |
| Liệt kê class đã nạp, bao gồm hidden | **Có** | `Instrumentation.getAllLoadedClasses()` |
| Liệt kê hidden qua initiated class loader | **Không** | `getInitiatedClasses(loader)` cố ý loại hidden |
| Tra cứu hidden theo tên | **Không** | `Class.forName(hidden.getName())` không tìm được |
| Truy cập thông tin class/method hợp lệ | **Có, theo quyền** | Reflection, `MethodHandles.Lookup`, API chẩn đoán phù hợp |
| Redefine hidden class đã định nghĩa | **Không** | `redefineClasses` bị từ chối |
| Retransform hidden class đã định nghĩa | **Không** | `retransformClasses` bị từ chối |
| Sửa bytecode trước khi **tạo hidden class mới** | **Có**, nếu sở hữu và có cơ chế tạo bytes hợp lệ | Biến đổi bytes trước `Lookup.defineHiddenClass` |
| Tạo hidden class mới để dùng logic mới | **Có** | `Lookup.defineHiddenClass`; quản lý identity và tham chiếu mới |

**Không nhầm với profiler:** một công cụ có thể báo stack trace, sự kiện hoặc metadata liên quan đến hidden class tùy cơ chế theo dõi mà không cần redefine class ấy. Ngược lại, một agent phụ thuộc tuyệt đối vào retransform để chèn mã theo dõi **sau** khi lớp đã được tạo sẽ gặp giới hạn nói trên.

### Snapshot và vòng đời

`getAllLoadedClasses()` trả dữ liệu tại **thời điểm gọi**; không nên coi đó là registry vĩnh viễn. Hidden class mặc định có thể unload độc lập với defining loader khi không còn tham chiếu phù hợp.

- Nếu `Class<?>`/`MethodHandle`/instance vẫn được giữ, class tương ứng có thể còn tồn tại theo quy tắc reachability của JVM.
- Nếu các tham chiếu đó được giải phóng, thời điểm garbage collector unload class **không được đảm bảo**.
- Vì vậy, không viết test đòi một hidden class “biến mất khỏi `getAllLoadedClasses` ngay sau `System.gc()`”.

Lớp có thể xuất hiện ở lần snapshot này và không còn ở snapshot sau; đó là khác biệt **vòng đời**, không tự chứng minh agent đã redefine/retransform thành công.

## 11. `STRONG`, `NESTMATE` có khắc phục được giới hạn không?

Hai `MethodHandles.Lookup.ClassOption` chính thức:

| Option | Giải quyết điều gì? | Có thay đổi `isModifiableClass(hidden)`? |
| --- | --- | --- |
| `NESTMATE` | Thêm hidden class vào nest của lookup class để có quyền truy cập `private` giữa nestmate hợp lệ | **Không**, vẫn `false` |
| `STRONG` | Ràng buộc vòng đời với defining class loader theo quan hệ mạnh tương tự class thường | **Không**, vẫn `false` |

Ví dụ:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE,
                MethodHandles.Lookup.ClassOption.STRONG);
```

Đây là **snippet** cần bytecode hợp lệ và lookup có đặc quyền thích hợp; không phải chương trình độc lập. Class vừa tạo là **hidden**, có quan hệ nest và vòng đời như tùy chọn, nhưng **không modifiable bởi agent**.

**Về vòng đời:**

- Mặc định, hidden class có thể unload khi không còn những tham chiếu giữ nó sống, ngay cả khi defining loader vẫn còn sống.
- Với `STRONG`, quan hệ giữa hidden class và defining class loader chặt hơn, tương tự class thông thường. Điều này có thể quan trọng khi framework giữ các generated class lâu dài.
- `STRONG` không đảm bảo một mốc thời gian unload cụ thể; nó cũng không làm class biến thành class discoverable theo binary name.

Trong bài toán instrumentation, lựa chọn weak/strong ảnh hưởng đến **quản lý bộ nhớ và vòng đời**, chứ **không** mở tính năng redefine/retransform.

## 12. Nếu một hệ thống cần thay đổi hành vi theo thời gian, nên thiết kế thế nào?

### Trường hợp A: tự sinh hidden class

**Ưu tiên:** tạo một pipeline có phiên bản cho bytecode và một điểm điều phối cập nhật được.

```text
logical behavior v1
        |
        v
generate bytes v1 ----> defineHiddenClass(v1) ---> method handle v1
                                                    |
                                                    v
                                              application router
                                                    ^
                                                    |
generate bytes v2 ----> defineHiddenClass(v2) ---> method handle v2
        ^
        |
logical behavior v2
```

Trong mô hình này, lớp v1 và v2 **khác identity**. Router có thể chuyển các lượt gọi mới sang v2 theo chính sách đồng bộ thích hợp, trong khi công việc đang chạy với v1 vẫn hoàn tất theo cơ chế của ứng dụng.

Có thể dùng `volatile`, `AtomicReference` hoặc phương thức điều phối khác để quản lý tham chiếu tới implementation hiện tại. Nếu dùng `MutableCallSite`, phải hiểu đúng quy tắc công bố thay đổi và đồng bộ của API; không tự giả định việc gán một handle mới làm mọi luồng thấy ngay cùng một giá trị.

### Trường hợp B: đang dùng framework tạo hidden class

- Kiểm tra framework có **hook trước khi class được định nghĩa** không.
- Nếu muốn thêm tracing, cân nhắc instrument **lớp gọi, factory, wrapper hoặc biên public** thay vì cố retransform hidden class đã ra đời.
- Dùng API tracing/metrics/logging chính thức mà framework cung cấp nếu phù hợp.
- Nếu buộc phải sửa logic generated class, cấu hình cơ chế sinh lại lớp hoặc thay đổi điểm phân phối reference trong ứng dụng, chứ không gọi redefine cho hidden class.
- Kiểm tra lifecycle của các tham chiếu được giữ để tránh khiến lớp đã không còn dùng vẫn sống mãi.

### Trường hợp C: viết profiler hoặc công cụ chẩn đoán

- Nếu cần **khám phá** hidden class đang tồn tại, `getAllLoadedClasses` là lựa chọn có ý nghĩa; không thay bằng `getInitiatedClasses`.
- Nếu đã có `Class<?>`, dùng `isHidden()` để phân biệt chính thức, tránh phân tích phần hậu tố tên.
- Không tự suy ra “có thể sửa” từ việc một công cụ hiển thị class hoặc stack frame.
- Với công cụ JVM TI, kiểm tra các capability, phase và quy tắc riêng của API cần gọi. Không suy luận “JVM TI nhìn được thì JVM TI redefine được”.

### Trường hợp D: lớp thông thường cần hot fix

Nếu class **không hidden**, có thể cân nhắc `retransformClasses` hoặc `redefineClasses` khi JVM/agent hỗ trợ **và** `isModifiableClass` là `true`. Nhưng vẫn phải tôn trọng những giới hạn của redefinition, chẳng hạn không tự ý đổi tên/kiểu thành viên, cấu trúc kế thừa và các thuộc tính nest/record/sealed theo quy tắc của JVM.

Không được dùng ví dụ thành công của một class thường để kết luận hidden class cũng cập nhật được.

## 13. Những lỗi thường gặp và cách sửa

| Hiện tượng | Sai lầm nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `isModifiableClass(hidden)` trả `false` | Coi hidden class giống class bình thường | Chấp nhận giới hạn; xử lý ở bước sinh bytes hoặc thay lớp mới |
| `retransformClasses(hidden)` ném `UnmodifiableClassException` | Hidden class không modifiable | Không retry vô hạn; không có cờ bật để biến hidden thành modifiable |
| `redefineClasses(hidden, ...)` bị từ chối | Nhầm redefinition với việc tạo class mới | Dùng `defineHiddenClass` để tạo class mới và chuyển tham chiếu có chủ đích |
| Nhận `UnsupportedOperationException` | JVM/agent thiếu capability hoặc yêu cầu thay đổi không được hỗ trợ | Đọc `is...Supported` và loại thao tác; không đổ mọi lỗi cho hidden |
| Agent in tên hidden class nhưng `Class.forName` thất bại | Tên runtime không phải binary name bình thường | Giữ `Class<?>`/`Lookup`; dùng các API liệt kê phù hợp |
| `getInitiatedClasses` không có hidden class | API cố ý chỉ liệt kê class có thể tìm theo tên | Dùng `getAllLoadedClasses` khi cần snapshot loaded |
| `getAllLoadedClasses` có hidden nhưng transformer không “vá” được | Quan sát không đồng nghĩa modifiable | Thiết kế instrument trước definition hoặc ở biên của framework |
| Bật `Can-Retransform-Classes: true` mà vẫn không sửa hidden | Capability toàn cục không thay đổi tính modifiable từng class | Kiểm tra `isModifiableClass` và đổi chiến lược |
| Bật `NESTMATE` hay `STRONG` mà vẫn bị từ chối | Các option không liên quan redefine/retransform | Dùng option đúng với nest hoặc vòng đời |
| Tạo hidden class từ bytes mới mà code cũ vẫn chạy | Tham chiếu cũ vẫn giữ identity/method handle cũ | Cập nhật router/factory/đối tượng tham chiếu theo quy tắc ứng dụng |
| `System.gc()` không làm hidden class biến mất ngay | GC và class unloading không có mốc thời gian được bảo đảm | Không kiểm thử bằng thời điểm unload tuyệt đối |
| Agent JAR không có `Premain-Class` | JVM không biết entry point khởi động agent | Sửa `MANIFEST.MF` và chạy `-javaagent` đúng |
| `getResourceAsStream` trả `null` | Không có `HiddenTarget.class` trên classpath | Biên dịch cả hai top-level class và kiểm tra thư mục chạy |
| Đưa source text thay cho classfile bytes | `defineHiddenClass` cần bytes class file hợp lệ | Biên dịch/sinh classfile trước khi gọi |
| Kiểm thử phụ thuộc hậu tố tên hidden class | Suffix có thể thay đổi theo JVM/lần chạy | Kiểm tra `isHidden`, class identity và kết quả thực thi |

### Về ngoại lệ của ví dụ

Chương trình bắt `UnmodifiableClassException` và `UnsupportedOperationException` để chứng minh hai thao tác bị **từ chối**, nhưng ứng dụng thực tế nên phân biệt:

- **Không có capability:** agent/JVM không hỗ trợ tính năng.
- **Đích không modifiable:** hidden class không nằm trong tập đối tượng được sửa bằng API.
- **Bytes/structural changes không hợp lệ:** với class thường, đây là lỗi khác khi redefine/retransform.

Vì vậy, một bản log hữu ích nên chứa: loại class (`isHidden`), trạng thái modifiability, hai cờ capability, tên loại ngoại lệ và ngữ cảnh hành động; không dựa duy nhất vào exception message.

## 14. Tự luyện tập và lời giải

**Bài 1.** Một class `H` được tạo bằng `Lookup.defineHiddenClass(...)`. `H.isHidden()` và `inst.isModifiableClass(H)` lần lượt trả gì?

**Đáp án:** `true` và `false`. Hidden class là class thực sự nhưng không phải mục tiêu hợp lệ cho agent redefinition/retransformation.

**Bài 2.** Agent có `isRetransformClassesSupported()==true`. Có thể gọi thành công `retransformClasses(H)` chỉ vì cờ này không?

**Đáp án:** Không. Cần kiểm tra `isModifiableClass(H)`. Với hidden class, nó là `false`.

**Bài 3.** Tại sao `getAllLoadedClasses()` có thể chứa `H` còn `getInitiatedClasses(loader)` lại không chứa?

**Đáp án:** Hai API có hợp đồng khác nhau: phương thức đầu liệt kê các class đã nạp gồm hidden class; phương thức sau chỉ liệt kê các class mà loader có thể tìm theo tên và không bao gồm hidden class.

**Bài 4.** Framework đang giữ bytecode nguồn và muốn thêm một lời gọi logging vào hidden class sắp được tạo. Nên thêm ở đâu?

**Đáp án:** Biến đổi **bytes trước khi gọi `defineHiddenClass`** (sau đó kiểm chứng classfile hợp lệ). Đó là biến đổi trước lần định nghĩa, không phải retransform.

**Bài 5.** Framework đã tạo hidden class v1, muốn cập nhật hành vi cho các lời gọi mới. Có thể gọi `redefineClasses` lên v1 không?

**Đáp án:** Không. Có thể sinh bytes v2, tạo hidden class v2, rồi chuyển bộ định tuyến/factory tham chiếu tới v2 theo thiết kế ứng dụng. Các đối tượng/handle của v1 không tự đổi.

**Bài 6.** Chỉ định `ClassOption.STRONG` có khiến hidden class modifiable không?

**Đáp án:** Không. `STRONG` thay đổi quan hệ vòng đời với loader, không liên quan quyền retransform/redefine.

**Bài 7.** Trong ví dụ, vì sao `hidden.answer=OK` dù `hidden.modifiable=false`?

**Đáp án:** `isModifiableClass` chỉ hỏi khả năng **sửa định nghĩa**, không hỏi khả năng **thực thi**. Lookup/method handle hợp lệ vẫn dùng được.

**Bài 8.** Khi thiếu `Can-Retransform-Classes` và gọi `retransformClasses(hidden)`, vì sao không nên luôn khẳng định ngoại lệ nhận được phải là `UnmodifiableClassException`?

**Đáp án:** JVM có thể từ chối trước vì capability không hỗ trợ và ném `UnsupportedOperationException`. Cần đọc trạng thái capability và loại ngoại lệ thật.

**Bài 9.** Việc một agent có thể liệt kê một hidden class từ `getAllLoadedClasses` có đồng nghĩa nó có thể chèn bytecode vào class đã tạo không?

**Đáp án:** Không. **Khả năng quan sát** và **khả năng sửa sau định nghĩa** là hai điều độc lập.

**Bài 10.** Nếu một hidden class đã unload, có thể dùng tên cũ để yêu cầu class loader tìm lại bằng `Class.forName` không?

**Đáp án:** Không. Ngay cả khi class còn sống, nó cũng không có binary name để được tìm bằng `Class.forName`; tên có hậu tố chỉ phục vụ thông tin runtime.

## 15. Checklist và nguồn tham khảo

### Checklist trước khi thiết kế công cụ

- [ ] Tôi biết hidden class được định nghĩa qua `Lookup.defineHiddenClass` và xác định bằng `Class.isHidden()`.
- [ ] Tôi không nhầm **quan sát lớp** với **sửa class đã định nghĩa**.
- [ ] Tôi biết `Instrumentation.isModifiableClass(hidden)` luôn là `false` theo cơ chế chính thức.
- [ ] Tôi biết hidden class **không thể redefine/retransform** bằng Java agent/JVM TI.
- [ ] Tôi phân biệt `isRetransformClassesSupported`, `isRedefineClassesSupported` với `isModifiableClass`.
- [ ] Tôi hiểu lý do `getAllLoadedClasses` có hidden nhưng `getInitiatedClasses` không có.
- [ ] Tôi không dùng `Class.forName(hidden.getName())` để tìm lại hidden class.
- [ ] Tôi biết cách kiểm soát bytes **trước** `defineHiddenClass` và không gọi đó là redefinition.
- [ ] Tôi biết cách sinh hidden class mới khi muốn logic mới và quản lý tham chiếu cũ/mới.
- [ ] Tôi không coi `NESTMATE`, `STRONG` hay `--add-opens` là cách phá giới hạn modifiability.
- [ ] Tôi biết hidden class có thể unload độc lập với loader theo mặc định, không kiểm thử thời điểm GC.
- [ ] Tôi có thể chạy ví dụ hai class Java + manifest và giải thích đúng từng dòng stdout.

### Tài liệu chính thức, còn áp dụng

1. [Oracle JDK 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, hidden class không thể được Java agent/JVM TI agent sửa, tên/loader/vòng đời.
2. [Oracle JDK 25 — `Instrumentation`](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isModifiableClass`, `isRetransformClassesSupported`, `isRedefineClassesSupported`, `getAllLoadedClasses`, `getInitiatedClasses`, `redefineClasses`, `retransformClasses`.
3. [Oracle JDK 25 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback transformation, quy tắc gọi và các giới hạn chung.
4. [Oracle JDK 25 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cặp class đích và classfile bytes thay thế.
5. [Oracle JDK 25 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
6. [Oracle JDK 25 — JVM Tool Interface](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): API quan sát, khả năng công cụ và redefinition/retransformation.
7. [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): lý do thiết kế và những quy tắc hidden class được chuẩn hóa từ Java 15.

**Tổng kết:** Hidden class có thể **được tạo, thực thi và quan sát** qua các API thích hợp, nhưng một khi đã được định nghĩa, nó **không modifiable bởi `Instrumentation.retransformClasses` hay `Instrumentation.redefineClasses`**. Nếu bạn sở hữu quy trình sinh lớp, hãy thiết kế instrumentation **trước `defineHiddenClass`**, hoặc tạo hidden class phiên bản mới và quản lý chuyển tiếp tham chiếu. Đừng cố dùng quyền agent, `NESTMATE`, `STRONG` hoặc tên runtime của class để giả lập khả năng redefine/retransform vốn không được hỗ trợ.