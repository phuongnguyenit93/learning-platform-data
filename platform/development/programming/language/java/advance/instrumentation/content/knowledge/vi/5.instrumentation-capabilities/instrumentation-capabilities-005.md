# `isModifiableClass` khác gì với kiểm tra khả năng chung của Java agent?

## 1. Hai câu hỏi khác nhau khi dùng Instrumentation

Java agent nhận một đối tượng `java.lang.instrument.Instrumentation` từ JVM qua `premain` (khi dùng `-javaagent` lúc khởi động) hoặc `agentmain` (khi nạp agent theo cơ chế động được JVM cho phép). Khi agent muốn thay đổi bytecode của **một lớp đã được nạp**, cần phân biệt **khả năng của môi trường/agent** và **khả năng của chính lớp đó**.

- **Khả năng chung:** `isRetransformClassesSupported()` và `isRedefineClassesSupported()` hỏi **cấu hình JVM hiện tại của agent có cho phép cơ chế retransform hoặc redefine hay không**. Chúng không nhận tham số lớp.
- **Khả năng theo lớp:** `isModifiableClass(Class<?> type)` hỏi **lớp cụ thể có thuộc loại JVM cho phép sửa bằng retransform/redefine hay không**. Phương thức này không tự kiểm tra khả năng chung ở trên.

**Điều quan trọng nhất:** `isModifiableClass(MyService.class) == true` **không đủ** để kết luận agent có thể gọi `retransformClasses(MyService.class)` hoặc `redefineClasses(...)`. Ngược lại, một JVM hỗ trợ retransform vẫn có thể có các lớp **không thể sửa**.

Theo đặc tả `Instrumentation`, kết quả `isModifiableClass` **độc lập** với hai cờ hỗ trợ retransform và redefine. Vì vậy, việc lấy phép AND của hai câu trả lời là cách diễn đạt đúng **điều kiện tiên quyết** cho từng thao tác. <https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html>

## 2. Ba phép kiểm tra trả lời ba câu hỏi

| API | Phạm vi | Khi `true` có nghĩa gì? | Khi `false` có nghĩa gì? |
| --- | --- | --- | --- |
| `inst.isRetransformClassesSupported()` | Cấu hình khả năng của agent/JVM | Có thể yêu cầu **retransform** một lớp đã nạp, nếu lớp ấy modifiable và bytecode hợp lệ | Không được dùng cơ chế retransform trong cấu hình hiện tại |
| `inst.isRedefineClassesSupported()` | Cấu hình khả năng của agent/JVM | Có thể yêu cầu **redefine** một lớp đã nạp, nếu lớp ấy modifiable và định nghĩa mới hợp lệ | Không được dùng cơ chế redefine trong cấu hình hiện tại |
| `inst.isModifiableClass(SomeClass.class)` | **Một `Class<?>` cụ thể** | Lớp ấy có thể là đối tượng được sửa bằng một trong các cơ chế trên, nếu cơ chế tương ứng được hỗ trợ | Lớp ấy không thể retransform/redefine dù hai khả năng chung có `true` |

Cả retransform và redefine đều áp dụng cho **lớp đã được định nghĩa**, nhưng cách lấy bytecode mới khác nhau:

- **Retransform:** `retransformClasses(type)` chạy lại quy trình transform của lớp đã nạp, trong đó các transformer được đăng ký `canRetransform=true` được gọi lại; các transformer không có khả năng retransformation dùng lại kết quả transform trước đó theo đặc tả.
- **Redefine:** `redefineClasses(new ClassDefinition(type, newBytes))` yêu cầu thay định nghĩa lớp bằng **bytecode được cung cấp rõ ràng**; không có nghĩa là chạy lại mã nguồn Java.
- **Modify lúc load lần đầu:** `addTransformer(transformer)` có thể tham gia quá trình tải lớp mới mà **không cần** hỗ trợ retransform của các lớp đã nạp. Đây là hoạt động khác với hai phương thức trên.

Không nên dùng từ “agent hỗ trợ sửa class” theo nghĩa quá chung. Cần nói cụ thể là **sửa khi class load**, **retransform class đã load**, **redefine class đã load** hay **thay đổi module graph**.

### 2.1. Biểu thức quyết định cho từng thao tác

Với một lớp `type` đã biết:

~~~java
boolean modifiable = inst.isModifiableClass(type);
boolean canRetransform = inst.isRetransformClassesSupported()
        && modifiable;
boolean canRedefine = inst.isRedefineClassesSupported()
        && modifiable;
~~~

Đây là **mảnh mã minh họa bên trong một agent đã có `inst` và `type`**; đoạn này không phải một chương trình chạy độc lập. Hai biểu thức `canRetransform`/`canRedefine` chỉ nói rằng **đã qua kiểm tra điều kiện tiên quyết**. Chúng **không bảo đảm** thao tác sẽ thành công với bất kỳ thay đổi bytecode nào. Còn phải xét bytecode hợp lệ, giới hạn thay đổi cấu trúc lớp, xung đột khi biến đổi và khả năng của JVM đang chạy.

### 2.2. Bảng chân trị dễ nhớ

Ký hiệu:

- `M = inst.isModifiableClass(type)`.
- `T = inst.isRetransformClassesSupported()`.
- `D = inst.isRedefineClassesSupported()`.

| M | T | D | Kết luận về điều kiện tiên quyết |
| --- | --- | --- | --- |
| false | bất kỳ | bất kỳ | Không thể retransform hoặc redefine **lớp này** |
| true | false | false | Lớp có thể modifiable, nhưng **không có** cơ chế sửa lớp đã nạp được bật |
| true | true | false | Có thể cân nhắc **retransform**, không thể redefine |
| true | false | true | Có thể cân nhắc **redefine**, không thể retransform |
| true | true | true | Hai thao tác đều **qua điều kiện kiểm tra ban đầu**, nhưng mỗi thao tác vẫn có thể thất bại |

Chẳng hạn `M=true, T=false` **không mâu thuẫn**: API `isModifiableClass` được định nghĩa không phụ thuộc vào `isRetransformClassesSupported`. Lỗi thiết kế thường gặp là dùng mỗi `M` làm điều kiện để gọi `retransformClasses` rồi ngạc nhiên vì `UnsupportedOperationException`.

## 3. Khả năng chung phụ thuộc những gì?

Hai khả năng retransform/redefine **không tự động bật chỉ vì JVM có implementation hỗ trợ**. Với Java agent JAR, manifest là một phần của yêu cầu capability:

| Khả năng | Manifest JAR của agent | Kiểm tra lúc chạy |
| --- | --- | --- |
| Retransform | `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` |
| Redefine | `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` |
| Đặt prefix cho native method | `Can-Set-Native-Method-Prefix: true` | `isNativeMethodPrefixSupported()` |

Theo đặc tả Java 17, cả ba manifest attribute trên là **tùy chọn**, mặc định **false** khi bị bỏ qua; JVM còn phải hỗ trợ capability tương ứng. Bởi vậy, thêm attribute `true` là **yêu cầu một khả năng**, không phải bảo đảm mọi JVM đều trả `true`.

Ngoài manifest, còn phụ thuộc **JVM/JDK đang chạy, cách khởi động agent và cấu hình runtime**. Câu trả lời thực tế phải lấy từ chính đối tượng `Instrumentation` mà JVM truyền cho agent. Không đoán từ Java version hoặc suy từ việc agent đã được load thành công.

Trong một lần chạy JVM, tài liệu API quy định các lần gọi lặp lại `isRetransformClassesSupported()` và `isRedefineClassesSupported()` có kết quả ổn định. Điều này **khác phạm vi** với `isModifiableClass(type)`: phép kiểm tra còn phụ thuộc vào lớp cụ thể đang xét.

**Đừng trộn với các API khác:** `isNativeMethodPrefixSupported()` nói về cơ chế native method prefix. `isModifiableModule(module)` kiểm tra khả năng `redefineModule` để bổ sung quan hệ read/export/open của module; nó **không phải** phép thay thế cho `isModifiableClass` trong bài toán bytecode của class.

## 4. Lớp nào có thể không modifiable?

`isModifiableClass(Class<?> theClass)` nhận đối tượng `Class<?>` cụ thể và trả boolean. Đặc tả bảo đảm:

- **Kiểu nguyên thủy** như `int.class` hoặc `void.class` luôn trả **false**.
- **Kiểu mảng** như `String[].class` hoặc `int[][].class` luôn trả **false**.
- Truyền `null` gây **NullPointerException**.
- Với lớp thông thường, không nên giả định mọi lớp ứng dụng hay lớp JDK đều modifiable; **hỏi JVM bằng API** tại thời điểm cần thao tác. Các loại lớp đặc biệt và giới hạn triển khai có thể làm kết quả khác nhau.

**Không nhầm “lớp ứng dụng” với “lớp luôn sửa được”:** ví dụ `String.class`, một anonymous class, một lớp do framework sinh, hoặc một lớp thuộc JDK cần được kiểm tra riêng. Quyền truy cập Java (như `private`/`public`) không phải phép thử thay thế cho `isModifiableClass`; kiểm tra khả năng sửa bytecode còn khác với việc đọc/ghi field bằng reflection.

`isModifiableClass` chỉ kiểm tra một **Class object**; nó không tìm lớp theo tên và không tự nạp một lớp chưa tồn tại. Để khảo sát những lớp đã được JVM load, agent có thể dùng `getAllLoadedClasses()` rồi kiểm tra từng đối tượng `Class<?>`, nhưng phải cân nhắc số lượng rất lớn và chi phí duyệt. Nếu muốn **biến đổi lớp ngay khi được nạp lần đầu**, hãy đăng ký `ClassFileTransformer` sớm thay vì cố tìm đối tượng `Class<?>` khi lớp chưa load.

## 5. Ví dụ Java 17+: cùng một lớp, hai cấu hình agent khác nhau

Ta tạo **một chương trình Java độc lập và một agent**. Chạy chương trình hai lần bằng hai agent JAR: một JAR không xin capability retransform/redefine, một JAR khai báo xin cả hai. Bài thực hành **không thay đổi bytecode**; nó đo đúng sự khác biệt giữa **kiểm tra chung** và **kiểm tra theo lớp**. Cùng một lớp `Target` có thể `modifiable=true` trong khi cấu hình agent không hỗ trợ retransform/redefine.

### 5.1. Mã nguồn

**Tệp: CapabilityDemo.java**

~~~java
import java.lang.instrument.Instrumentation;

public final class CapabilityDemo {
    static final class Target {
        String value() {
            return "ready";
        }
    }

    public static void main(String[] args) {
        System.out.println("app=" + new Target().value());
    }
}

class CapabilityAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        Class<?> target = CapabilityDemo.Target.class;

        boolean retransformation =
                inst.isRetransformClassesSupported();
        boolean redefinition =
                inst.isRedefineClassesSupported();
        boolean modifiable =
                inst.isModifiableClass(target);

        System.out.println("retransformSupported=" + retransformation);
        System.out.println("redefineSupported=" + redefinition);
        System.out.println("targetModifiable=" + modifiable);
        System.out.println("primitiveModifiable="
                + inst.isModifiableClass(int.class));
        System.out.println("arrayModifiable="
                + inst.isModifiableClass(String[].class));

        System.out.println("canRetransformTarget="
                + (retransformation && modifiable));
        System.out.println("canRedefineTarget="
                + (redefinition && modifiable));
    }
}
~~~

Tệp chứa `public class CapabilityDemo` nên **tên tệp phải là CapabilityDemo.java**. `CapabilityAgent` là class top-level không public cùng tệp để ví dụ ngắn gọn; compiler tạo `CapabilityDemo.class`, `CapabilityDemo$Target.class` và `CapabilityAgent.class`. `premain` nhận `Instrumentation` do JVM cung cấp, không tự tạo đối tượng này. Chỉ dùng `CapabilityDemo.Target.class` cũng khiến lớp được resolve/load sớm; ví dụ cố ý làm vậy để kiểm tra lớp, không minh họa việc thay đổi thứ tự khởi tạo class trong ứng dụng thật.

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 CapabilityDemo.java
~~~

### 5.2. Cấu hình A: chỉ khai báo `Premain-Class`

**Tệp: manifest-basic.mf**

~~~text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent

~~~

Hai dòng khai báo trên tạo agent khởi động được, **nhưng bỏ qua** `Can-Retransform-Classes` và `Can-Redefine-Classes`, nên cả hai mặc định false.

### 5.3. Cấu hình B: xin retransform và redefine

**Tệp: manifest-enabled.mf**

~~~text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Cả hai manifest đều phải được lưu với dòng trống kết thúc phần header chính; lệnh `jar` bên dưới tạo agent JAR và giữ nguyên các attribute.

### 5.4. Đóng gói và chạy hai JVM riêng biệt

Ở thư mục chứa source, hai manifest và các file `.class` đã biên dịch:

~~~bash
jar --create --file agent-basic.jar --manifest manifest-basic.mf CapabilityAgent.class
jar --create --file agent-enabled.jar --manifest manifest-enabled.mf CapabilityAgent.class

java -javaagent:agent-basic.jar CapabilityDemo
java -javaagent:agent-enabled.jar CapabilityDemo
~~~

Bốn lệnh trên là cú pháp dùng được trên Windows PowerShell, Linux và macOS khi Java/JAR đã ở `PATH`; chạy lần lượt. Mỗi lệnh `java` tạo **một JVM mới**, bảo đảm so sánh cấu hình agent một cách độc lập. Trong ứng dụng thực, JAR agent phải chứa các class và dependency mà agent cần; ví dụ agent không cần dependency ngoài JDK và app demo nằm trên class path.

**Ví dụ stdout cấu hình A trên HotSpot hỗ trợ sửa lớp ứng dụng:**

~~~text
retransformSupported=false
redefineSupported=false
targetModifiable=true
primitiveModifiable=false
arrayModifiable=false
canRetransformTarget=false
canRedefineTarget=false
app=ready
~~~

Chú ý dòng `targetModifiable=true` song hành với hai dòng `...Supported=false`: **hoàn toàn hợp lệ**. `Target` có thể sửa về bản chất, nhưng agent chưa được bật hai cơ chế sửa lớp đã nạp. `primitiveModifiable=false` và `arrayModifiable=false` là hành vi được đặc tả bảo đảm.

**Ví dụ stdout cấu hình B trên HotSpot có hỗ trợ cả hai capability:**

~~~text
retransformSupported=true
redefineSupported=true
targetModifiable=true
primitiveModifiable=false
arrayModifiable=false
canRetransformTarget=true
canRedefineTarget=true
app=ready
~~~

Các giá trị `targetModifiable` và giá trị capability trong cấu hình B **phụ thuộc JVM**; ví dụ trên là đầu ra minh họa được kiểm thử trên HotSpot tương thích, không phải lời hứa cho mọi JVM. `app=ready` và hai kiểu nguyên thủy/mảng thì không phụ thuộc cơ chế sửa lớp. **Không có thao tác retransform/redefine nào được thực hiện**: `can...Target=true` ở đây chỉ là đạt yêu cầu kiểm tra trước thao tác.

**Ý nghĩa thực hành:** không thay đổi code class mà chỉ đổi manifest, kết quả `...Supported` có thể đổi; ngược lại `isModifiableClass(Target.class)` không bị hai giá trị đó chi phối.

## 6. Dùng hai cấp kiểm tra trước khi thao tác thật

Giả sử một agent cần gắn thêm probe vào một service **đã load**. Phần code dưới đây là **mảnh mã trong agent**, yêu cầu có sẵn biến `inst` và `serviceClass`, và đã đăng ký transformer thích hợp:

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Cấu hình agent/JVM không cho phép retransform.
    return;
}
if (!inst.isModifiableClass(serviceClass)) {
    // Lớp cụ thể không thể retransform/redefine.
    return;
}

try {
    inst.retransformClasses(serviceClass);
} catch (java.lang.instrument.UnmodifiableClassException ex) {
    // Thông báo rõ lớp không thể sửa; không giả định check đủ.
    reportFailure(ex);
} catch (UnsupportedOperationException ex) {
    // Cấu hình không hỗ trợ hoặc thay đổi bytecode bị cấm.
    reportFailure(ex);
}
~~~

Đây **không phải chương trình độc lập**: `return` chỉ hợp lệ khi đoạn code nằm trong một phương thức, và `reportFailure` là hàm báo lỗi do ứng dụng cần định nghĩa. Mục đích là minh họa thứ tự **check capability → check class → call API → xử lý lỗi thực tế**. Trong production, transformer phải trả bytecode hợp lệ và cần cleanup bằng `removeTransformer(...)` khi không còn sử dụng.

Một biến thể với `redefineClasses` dùng **cặp điều kiện khác**:

~~~java
boolean allowed =
        inst.isRedefineClassesSupported()
        && inst.isModifiableClass(serviceClass);

// Chỉ sau khi allowed mới chuẩn bị ClassDefinition với bytecode hợp lệ.
~~~

Cũng là **mảnh mã minh họa**, không phải chương trình độc lập. `isRetransformClassesSupported` và `isRedefineClassesSupported` **không thay thế cho nhau**. Muốn dùng `redefineClasses` phải tạo bytecode/`ClassDefinition` thích hợp và đáp ứng giới hạn thay đổi cấu trúc lớp của JVM.

### 6.1. Những lỗi vẫn có thể xảy ra sau khi tất cả check đều `true`

Điều kiện tiên quyết **không phải bảo đảm thành công**. `retransformClasses` và `redefineClasses` có thể thất bại khi:

- Bytecode mới không hợp lệ hoặc phiên bản class file không được JVM hỗ trợ: `ClassFormatError`, `UnsupportedClassVersionError`.
- Bytecode có tên lớp không khớp, cấu trúc phụ thuộc xung đột: `NoClassDefFoundError`, `LinkageError` và các lỗi JVM khác.
- Đòi thay đổi cấu trúc lớp vượt điều JVM hỗ trợ (chẳng hạn thêm/xóa field/method ở môi trường HotSpot không hỗ trợ thay đổi schema): `UnsupportedOperationException`.
- Có lớp trong danh sách không thể modifiable: `UnmodifiableClassException`.
- Target đã đổi trạng thái hoặc code instrumentor có lỗi tại lúc thực thi, cần xử lý theo exception thực tế.

Với `retransformClasses(Class<?>... classes)`, Javadoc quy định nếu ném exception thì **không lớp nào trong cả tập đầu vào được retransform thành công một phần**; đây là bảo đảm quan trọng khi instrument đồng thời nhiều lớp. Nhưng điều đó không có nghĩa các **tác động phụ bên ngoài** của agent/transformer được tự động rollback. Không nên sử dụng phép kiểm tra capability như một lời hứa mọi phép sửa bytecode đều an toàn.

### 6.2. Đăng ký transformer cho class mới không đồng nghĩa retransform

Nếu JVM không cho retransform, agent vẫn có thể dùng:

~~~java
inst.addTransformer(transformer); // tương đương canRetransform=false
~~~

Đây là **mảnh mã trong agent có biến `transformer` thuộc `ClassFileTransformer`**. Transformer thông thường có thể xử lý **lần định nghĩa class trong tương lai**. Trong khi đó, `inst.addTransformer(transformer, true)` yêu cầu khả năng retransformation; nếu `isRetransformClassesSupported() == false` sẽ ném `UnsupportedOperationException`.

Vì vậy khi một agent hoạt động được lúc startup nhưng không thể thêm probe vào class **đã load**, cần kiểm tra nó có chỉ hỗ trợ **load-time instrumentation** hay thực sự được bật **retransformation** hay không. Không kết luận “Instrumentation hoàn toàn không hoạt động” chỉ từ một phép kiểm tra global trả false.

## 7. Cách chẩn đoán khi capability và modifiable không khớp kỳ vọng

| Quan sát | Diễn giải và bước tiếp theo |
| --- | --- |
| `modifiable=true`, `retransformSupported=false` | Kiểm tra `Can-Retransform-Classes` trong manifest và JVM có hỗ trợ capability; đừng gọi `retransformClasses` ngay |
| `modifiable=true`, `redefineSupported=false` | Kiểm tra `Can-Redefine-Classes` và lựa chọn thay thế bằng retransform nếu được hỗ trợ |
| `modifiable=false`, `retransformSupported=true` | Tính năng retransform có nhưng **class này** không thể sửa; bỏ qua hoặc tìm ranh giới khác |
| `modifiable=false` với `int.class` hay `String[].class` | Bình thường theo đặc tả; không cố sửa bytecode kiểu nguyên thủy/mảng |
| Cả ba `true` nhưng API vẫn ném `UnsupportedOperationException` | Kiểm tra **kiểu thay đổi bytecode** hoặc giới hạn JVM, không chỉ capability |
| Đăng ký transformer bình thường nhưng `addTransformer(t,true)` thất bại | Agent không có retransformation capability; dùng load-time transform hoặc cấu hình lại agent |
| Chạy `-javaagent` được nhưng dynamic load không được | Cơ chế **nạp agent vào JVM** khác với quyền **sửa class sau khi agent đã có Instrumentation**; kiểm tra chính sách target riêng |
| Thông tin trước và sau thay đổi khác | Xác minh JDK/JVM runtime, manifest, cách nạp và đúng đối tượng `Instrumentation`; không lấy kết quả từ máy khác làm mặc định |

**Quy trình thực tế:**

1. Xác minh agent nhận `Instrumentation` trong `premain`/`agentmain` đúng JVM cần quan sát.
2. Ghi **hai global flags** và manifest yêu cầu capability; tránh công bố dữ liệu nhạy cảm.
3. Xác định rõ **Class<?> của lớp đích** rồi gọi `isModifiableClass` cho chính lớp đó.
4. Chọn **retransform**, **redefine** hoặc **transform lúc load** theo mục tiêu thật.
5. Xử lý exception, kiểm thử cả đường thất bại, benchmark chi phí instrumentation và xác minh kết quả sau thao tác.

Với nhiều JVM/container, PID, class loader và phiên bản JDK có thể khác nhau; kết quả ở agent A không chứng minh điều kiện ở agent B. Ngay cả hai class có **cùng tên nhị phân** nhưng được nạp qua **class loader khác nhau** cũng có `Class<?>` khác nhau: cần kiểm tra đúng lớp thực sự đang được dùng.

## 8. Những hiểu nhầm dễ dẫn đến code sai

1. **“`isModifiableClass` gọi là biết agent có hỗ trợ retransform.”** Sai: kết quả hoàn toàn độc lập với global capability flags.
2. **“`isRetransformClassesSupported` true tức mọi class đều sửa được.”** Sai: kiểm tra thêm `isModifiableClass(type)` cho mỗi lớp.
3. **“`Can-Retransform-Classes: true` đảm bảo luôn thành công.”** Sai: JVM còn phải hỗ trợ, lớp còn phải modifiable và bytecode còn phải hợp lệ.
4. **“`isModifiableClass` true tức có thể thêm field/method.”** Sai: hỗ trợ sửa class không đồng nghĩa mọi thay đổi cấu trúc đều hợp lệ.
5. **“`isModifiableModule` thay cho `isModifiableClass`.”** Sai: một API kiểm tra module graph, API kia kiểm tra khả năng sửa class bytecode.
6. **“Không hỗ trợ retransform thì transformer không làm được gì.”** Sai: transformer có thể xử lý lần load đầu tiên tùy cách đăng ký.
7. **“Tắt dynamic attach tương đương tắt retransform.”** Sai: cơ chế **nạp agent** và capability **bên trong agent đã được nạp** là hai vấn đề độc lập; phải kiểm tra cấu hình cụ thể.
8. **“Check trước rồi sẽ không phải bắt exception.”** Sai: vẫn phải bắt các lỗi mà API quy định, xác thực bytecode và giới hạn runtime.

## 9. Tự kiểm tra kiến thức

1. Vì sao `isModifiableClass(Target.class)` có thể `true` ngay cả khi `isRetransformClassesSupported()` là `false`?
2. Nếu `T=true` nhưng `M=false`, có nên gọi `retransformClasses(Target.class)`? Dự đoán loại exception thích hợp.
3. Trong manifest thiếu `Can-Redefine-Classes`, mặc định thuộc tính là gì?
4. `int.class` và `String[].class` luôn cho kết quả nào với `isModifiableClass`?
5. Khi một transformer theo dõi được lớp mới lúc load nhưng không thể cập nhật lớp đã load, cần xem xét khả năng nào?
6. Vì sao hai phép check đều `true` vẫn chưa bảo đảm bytecode mới được chấp nhận?
7. Vì sao cần kiểm tra `Class<?>` đúng class loader thay vì chỉ so tên lớp?

**Kết luận:** `isRetransformClassesSupported()` / `isRedefineClassesSupported()` kiểm tra **quyền và khả năng của cơ chế trên JVM/agent**; `isModifiableClass(clazz)` kiểm tra **khả năng của lớp cụ thể**. Để thao tác với lớp đã nạp, cần **cả hai loại điều kiện**, chọn đúng thao tác và sẵn sàng xử lý lỗi thật từ JVM.

### Tham khảo chính thức

- [Java 17 — Instrumentation API và các method chi tiết](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — java.lang.instrument, manifest attributes, premain/agentmain](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html)
