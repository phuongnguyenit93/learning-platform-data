# Điều gì xảy ra khi một transformer không đổi hoặc ném ngoại lệ?

Trong Java Instrumentation, nhiều `ClassFileTransformer` có thể cùng tham gia xử lý một định nghĩa lớp. Hai nhánh rất quan trọng của phương thức `transform(...)` là:

- **Không cần biến đổi:** trả về `null`. Lớp không nhận thay đổi nào từ **transformer này**, và bytecode đầu vào của bước ấy được chuyển tiếp cho transformer kế tiếp.
- **Ném ngoại lệ mà transformer không bắt:** theo hợp đồng `ClassFileTransformer`, JVM **vẫn gọi những transformer còn lại** và **vẫn thử** thực hiện class load, redefine hoặc retransform. Ở bước đang xét, ngoại lệ có tác dụng như **trả về `null`**.

Điểm dễ nhầm: **ngoại lệ của một transformer không mặc nhiên hủy toàn bộ chuỗi biến đổi**, nhưng cũng **không bảo đảm cuối cùng lớp sẽ nạp thành công**. Những transformer khác có thể tạo bytecode hợp lệ hoặc không hợp lệ, và JVM còn phải xác minh/áp dụng định nghĩa lớp cuối cùng.

Bài này thuộc chủ đề **Chuỗi biến đổi**, giải thích kết quả trên đầu vào bytecode, thứ tự gọi, tương tác với retransformation, cách đo/ghi log thất bại và ví dụ Java 17+ có thể chạy độc lập.

## 1. Mô hình cơ bản: từng transformer là một bước trong pipeline

Khi một lớp được nạp, được redefine hoặc được retransform, JVM có thể gọi những transformer đã đăng ký phù hợp. Coi mỗi callback như một bước:

```text
B0 = class bytes ban đầu của lượt xử lý
  |
  v
[T1.transform(B0)]
  | return byte[] B1  -> chuyển B1 cho bước kế tiếp
  | return null       -> chuyển nguyên B0 cho bước kế tiếp
  | throw exception   -> coi như null, chuyển B0 cho bước kế tiếp
  v
[T2.transform(...)]
  |
  v
[T3.transform(...)]
  |
  v
Bfinal = bytes cuối pipeline
  |
  v
JVM kiểm tra các ràng buộc, xác minh và thử định nghĩa/cập nhật lớp
```

Trong sơ đồ, `B0`, `B1` và `Bfinal` là ký hiệu cho các dãy byte ở từng bước, không phải địa chỉ hay tên biến Java có sẵn trong API. Quan trọng là **đầu ra của bước trước trở thành đầu vào của bước sau**. Nếu bước trước không có đầu ra thay thế vì `null` hoặc exception, bước sau nhận bytecode vốn đang có **ngay trước bước thất bại**.

### 1.1. Cấu trúc callback

Java 9+ có overload với `Module`; Java 17+ vẫn hỗ trợ overload năm tham số:

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) throws IllegalClassFormatException;
```

- `classfileBuffer` là **bytecode đầu vào của transformer hiện tại**, không nhất thiết là bytes nguyên bản lấy từ file `.class` trên đĩa. Transformer chạy trước đó có thể đã thay đổi nó.
- `className` có dạng internal name, chẳng hạn `com/example/Service`; có thể `null` trong một số trường hợp do API mô tả. Không so sánh bằng tên file `Service.java`.
- `classBeingRedefined == null` thường thể hiện class đang được định nghĩa lần đầu. Khi khác `null`, callback được gọi trong một lượt redefine/retransform; **chỉ dựa vào tham số đó không phân biệt được hai thao tác**.
- `loader` là defining class loader (có thể `null` với bootstrap loader); hai lớp cùng tên nhưng khác defining loader là hai đích riêng.
- `protectionDomain` cung cấp ngữ cảnh protection domain khi định nghĩa lớp. Không nên suy ra nó luôn không null.
- Kết quả: một **byte array mới, hợp lệ** nếu có biến đổi; hoặc `null` khi không biến đổi. **Không được sửa tại chỗ `classfileBuffer`**.

Trong Java 9+, overload sáu tham số `transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` mặc định gọi overload năm tham số nếu bạn không override phiên bản sáu tham số. Vì vậy ví dụ bên dưới override năm tham số vẫn được gọi trên Java 17+.

### 1.2. Ba kết quả phổ biến

| Transformer thực hiện | Bytecode sang bước tiếp theo | Các transformer sau có chạy không? | Có nghĩa là toàn bộ yêu cầu thành công không? |
|---|---|---|---|
| `return null;` | Bytes hiện hành trước callback này | **Có**, theo chuỗi áp dụng | Không; chỉ không có thay đổi tại bước này |
| `return transformedBytes;` | Mảng bytes mới do callback trả về | **Có** | Chưa biết; JVM còn phải kiểm tra định dạng/giới hạn |
| `throw new IllegalStateException(...);` không bắt | Bytes hiện hành trước callback này, như `null` | **Có** | Không; đây là lỗi logic transformer, có thể được JVM bỏ qua ở bước biến đổi |
| `throw new IllegalClassFormatException(...);` | Tác dụng lên pipeline như `null` | **Có** | Không; checked exception có ích cho chẩn đoán input không hợp lệ, không tự ép class load thất bại |
| `return new byte[0];` hoặc bytes không hợp lệ | Bytes do callback trả, nhưng rất có thể bị JVM từ chối về sau | Các callback sau có thể vẫn được gọi trước khi JVM phát hiện lỗi | **Không**; có thể gây `ClassFormatError` hoặc lỗi khác |

Bảng chỉ xét hợp đồng transform thông thường và trường hợp callback trả/ném lỗi. Những lỗi JVM nghiêm trọng, lỗi instrumentation infrastructure, giới hạn class file hoặc thao tác redefine/retransform bị từ chối vẫn có thể khiến yêu cầu cuối cùng thất bại.

## 2. `return null`: “không đổi ở bước này” nghĩa là gì?

Một transformer thường chỉ xử lý một tập lớp nhất định. Nếu tên lớp không thuộc phạm vi hoặc đã không cần sửa, code chuẩn là:

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String name,
        Class<?> redefining,
        ProtectionDomain domain,
        byte[] input) {
    if (!"com/example/OrderService".equals(name)) {
        return null;
    }

    if (!shouldInstrument(loader, name)) {
        return null;
    }

    // Đây là phần minh họa: createTransformedCopy phải tự bảo đảm
    // bytes đầu ra hợp lệ, không sửa input.
    return createTransformedCopy(input);
}
```

Đây **không phải một chương trình độc lập**: `shouldInstrument` và `createTransformedCopy` là tên hàm minh họa, chưa được định nghĩa. Chương trình thực thi đầy đủ nằm ở phần 6.

### Những điều `null` bảo đảm và không bảo đảm

**Có thể kết luận:**

- Transformer này không cung cấp class bytes thay thế trong lượt gọi đó.
- Transformer sau vẫn có cơ hội xử lý bytes đầu vào ở bước này.
- Nếu toàn bộ các transformer đều trả `null` (hoặc ném ngoại lệ không được bắt), pipeline không tạo class bytes thay thế từ các callback ấy.

**Không thể kết luận:**

- “Class chưa từng được instrument”: một transformer trước có thể đã thay bytes.
- “Class chắc chắn không đổi so với artifact trên đĩa”: class bytes nguồn có thể đã bị sửa bởi build tool, class loader, transformer khác hoặc ở một lần redefine trước.
- “Lớp nạp thành công”: JVM còn xác minh class bytes và thực hiện các bước class loading khác.
- “Agent chạy đúng mục đích”: có thể bộ lọc target, class loader hoặc cấu hình đã sai nên không transformer nào thật sự chèn probe.
- “Không có overhead”: callback vẫn được gọi và có thể làm I/O, kiểm tra metadata hoặc tạo object trước khi trả `null`.

### Mảng bytes mới nhưng nội dung giống cũ thì sao?

API khuyên **trả `null` nếu không cần biến đổi**. Nếu một transformer trả bản copy mới có bytes giống byte-for-byte, JVM sẽ xem nó là một kết quả thay thế ở tầng callback, dù hành vi có thể y hệt. Cách này tạo thêm copy/chi phí, dễ gây nhiễu số liệu “transformer đã biến đổi”, và không giúp chứng minh có probe mới.

Để biểu đạt rõ ràng, hãy giữ quy ước:

```text
no change intended  -> return null
change intended     -> return NEW well-formed byte[]; never modify input
```

`null` không phải chuỗi bytes có độ dài 0; `new byte[0]` **khác `null`** và không phải class file hợp lệ.

## 3. Ném exception: vì sao transformer sau vẫn chạy?

Java SE 21 quy định: nếu callback `transform` ném ngoại lệ mà nó không tự bắt, những transformer sau **vẫn được gọi**; class load, redefine hoặc retransform **vẫn được thử thực hiện**. Đối với bước transform đang xét, ném ngoại lệ có tác dụng giống `return null`.

Hình dung:

```text
T1.transform(B0) -> B1 (một bản class file hợp lệ)
T2.transform(B1) -> throws IllegalStateException
T3.transform(B1) -> B2 (một bản class file hợp lệ)
JVM thử kiểm tra/áp dụng B2
```

**T2 thất bại không làm mất B1.** Không được diễn giải sai rằng pipeline tự rollback về bytes gốc `B0`. Nó giữ bytes đã có trước khi gọi T2 và tiếp tục sang T3.

Nếu `T1` cũng trả `null`, thì `T2` ném ngoại lệ, và `T3` trả `null`, bytes từ ba callback giữ nguyên so với đầu chuỗi. Tuy nhiên không vì thế mà có thể khẳng định mọi phần của class loading đều thành công.

### 3.1. `IllegalClassFormatException` không phải lệnh “veto” class loading

`IllegalClassFormatException` là checked exception được khai báo ở overload năm tham số. Nếu thấy input không phải class file đúng định dạng, transformer **nên ném exception này** để thuận lợi ghi log và debug. Nhưng theo API, nó vẫn có tác dụng giống `return null` trên chuỗi biến đổi; nó **không tự buộc JVM từ chối định nghĩa lớp**.

Muốn **đảm bảo một hệ thống an toàn phải có probe**, không nên dựa vào việc “ném exception để JVM chặn class loading”. Hãy thiết kế chính sách fail-closed ở tầng triển khai/điều phối khi có quyền kiểm soát, xác minh agent và probe đã kích hoạt, hoặc dừng cung cấp chức năng nếu điều kiện không đạt. Việc cố tình trả bytes lỗi để phá class load không phải chiến lược lỗi an toàn hay có tính di động.

### 3.2. Runtime exception và Error trong callback

Một callback có thể gặp `RuntimeException` từ code phân tích bytecode, `IllegalClassFormatException` do định dạng, hoặc các lỗi nghiêm trọng như `OutOfMemoryError`. Hợp đồng API mô tả hành vi exception của transformer, nhưng **không nên thiết kế agent nuốt lỗi JVM nghiêm trọng** hoặc coi việc bắt mọi `Throwable` là cách làm luôn an toàn.

Javadoc ghi nhận transformer có thể tự `catch (Throwable)` để tránh hành vi bất ngờ khi code nội bộ tạo unchecked exception. Trong sản phẩm thực, hãy cân nhắc bắt có chọn lọc những lỗi **có thể phục hồi**, ghi nhận và trả `null`, nhưng phải để hệ thống quản lý lỗi nghiêm trọng theo chính sách rõ ràng.

Ví dụ cách bao lỗi có chẩn đoán (mã **minh họa, chưa độc lập**):

```java
try {
    byte[] output = transformerLogic(input);
    return output; // null nếu không đổi, new byte[] nếu đã đổi
} catch (IllegalClassFormatException e) {
    report("INVALID_INPUT", e);
    return null;
} catch (RuntimeException e) {
    report("TRANSFORMER_BUG", e);
    return null;
}
```

Ở đây `transformerLogic` và `report` là các phương thức cần tự triển khai, còn logic lấy `input` và metadata target đã được giản lược. Điều quan trọng là **báo lỗi trước khi quay về `null`**. Không catch rồi lặng lẽ bỏ qua mọi exception khiến người dùng nghĩ rằng instrument đã thành công.

## 4. Thứ tự transformer: không phải lúc nào cũng đúng thứ tự `addTransformer` toàn cục

Có hai nhóm Java transformer:

- **Retransformation incapable**: đăng ký bằng `addTransformer(t)` hoặc `addTransformer(t, false)`.
- **Retransformation capable**: đăng ký bằng `addTransformer(t, true)` khi JVM hỗ trợ và manifest agent yêu cầu đúng capability.

Thứ tự áp dụng trong specification:

1. Java transformers **không** hỗ trợ retransformation.
2. Native/JVMTI transformers **không** hỗ trợ retransformation.
3. Java transformers **có** hỗ trợ retransformation.
4. Native/JVMTI transformers **có** hỗ trợ retransformation.

**Trong từng nhóm** mới theo thứ tự đăng ký. Vì vậy:

```java
inst.addTransformer(transformerA, true);
inst.addTransformer(transformerB, false);
```

Nếu đăng ký thành công, **B thường chạy trước A** khi một định nghĩa lớp mới hoặc redefine được xử lý, vì thuộc **nhóm khác nhau**, dù A được thêm trước. Nếu hai transformer cùng nhóm `false`, chúng chạy theo thứ tự `addTransformer`. Đây là điểm quan trọng khi phụ thuộc vào output stage trước.

### 4.1. Transformer được gọi ở những thời điểm nào?

| Sự kiện JVM | Transformer đăng ký `false` | Transformer đăng ký `true` |
|---|---|---|
| Định nghĩa một class mới | Được gọi | Được gọi |
| `redefineClasses` | Được gọi | Được gọi |
| `retransformClasses` | **Không được gọi lại**; kết quả đã tạo trước đó được áp dụng lại theo quy tắc JVM | Được gọi lại |

Trong retransform, JVM bắt đầu từ class bytes nền phù hợp và tự **tái áp dụng nguyên trạng kết quả** của nhóm incapable từ lần load/redefine trước, thay vì gọi lại `transform` của nhóm đó. Đây là cơ chế riêng của retransformation, **không phải** do transformer có trả `null` hay từng ném exception.

Ví dụ, transformer A thuộc nhóm incapable:

```text
Load lần đầu:
  A (false) được gọi -> trả null
  B (true) được gọi  -> tạo B1

Retransform sau đó:
  A (false) KHÔNG gọi lại; biến đổi cũ của A được tái áp dụng
  B (true) được gọi lại -> có thể tạo kết quả mới
```

Nếu lúc load A đã tạo bytes `A1`, trong lần retransform phần biến đổi của A sẽ được tái áp dụng theo quy tắc. Nếu A không tạo biến đổi, không có một “lần callback A mới” để báo lỗi hay quyết định lại. Do đó không đặt kỳ vọng rằng sửa biến cấu hình của A rồi gọi `retransformClasses` là A sẽ chạy lại.

**Chú ý:** `ClassFileTransformer` không đảm bảo bytes “ban đầu” của một lần retransformation giống hệt file class ban đầu ở byte level. JVM có thể thay đổi tổ chức constant pool hoặc attributes không ảnh hưởng ngữ nghĩa. Dựa vào dữ liệu được API cung cấp tại **lượt hiện tại** thay vì gán byte-for-byte cho một artifact cũ.

## 5. Ngoại lệ của transformer khác lỗi khi JVM xác minh kết quả

Phân biệt hai loại thất bại:

### Loại A — callback thất bại nhưng pipeline vẫn tiếp tục

```text
Transformer A -> byte[] hợp lệ A1
Transformer B -> ném exception
Transformer C -> return null
JVM           -> thử áp dụng A1
```

Ở đây exception của B **không tự động** ngăn A1 được thử áp dụng. Nếu A1 hợp lệ theo ngữ cảnh, lớp có thể nạp/redefine/retransform thành công. Lỗi B cần được ghi nhận từ code của B hoặc hệ thống giám sát của agent; đừng mặc định ứng dụng gọi `Class.forName` sẽ nhận exception B.

### Loại B — bytecode cuối cùng không hợp lệ

```text
Transformer A -> return malformed byte[]
Transformer B -> return null
JVM           -> kiểm tra class bytes cuối, có thể từ chối
```

Nếu bytes cuối không hợp lệ, JVM có thể ném `ClassFormatError`, `VerifyError` hoặc các lỗi liên quan. Với `Instrumentation.retransformClasses`/`redefineClasses`, specification liệt kê những ngoại lệ như `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError`, `ClassCircularityError`, `LinkageError` hoặc `UnsupportedOperationException` tùy tình huống.

**Không đồng nhất** “`throw` trong `transform`” với “`ClassFormatError` khi JVM xác minh”. Đó là hai tầng khác nhau:

- **Tầng callback:** exception chưa bắt được coi như `null` cho bước đó.
- **Tầng kiểm chứng/áp dụng class file:** bytes cuối hoặc thao tác không hợp lệ có thể làm **toàn bộ yêu cầu cuối thất bại**.

Với yêu cầu retransform nhiều lớp cùng lúc, API quy định nếu `retransformClasses(...)` ném exception, **không lớp nào trong nhóm đó được retransform**. Điều này khác với hành vi `transform` riêng lẻ ném exception rồi JVM vẫn tiếp tục chuỗi callback.

## 6. Chương trình Java 17+ chạy được: một transformer trả null, một transformer ném exception, transformer cuối vẫn chạy

Ví dụ cố tình **không biến đổi bytecode** để kết quả minh bạch. Ba transformer của Java agent khởi động sẽ được đăng ký vào **cùng nhóm** `canRetransform=false`, do đó callback xảy ra theo thứ tự T1 → T2 → T3. T2 ném `IllegalStateException` có chủ đích; T3 vẫn được gọi và lớp vẫn có thể chạy bình thường.

Tạo **3 file** trong một thư mục rỗng: `ChainAgent.java`, `Demo.java`, `agent.mf`. Không cần thư viện ngoài.

### 6.1. `ChainAgent.java`: khai báo agent và ba transformer

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ChainAgent {
    public static void premain(String options, Instrumentation inst) {
        inst.addTransformer(new DemoTransformer("T1_NULL", false));
        inst.addTransformer(new DemoTransformer("T2_THROW", true));
        inst.addTransformer(new DemoTransformer("T3_NULL", false));

        System.out.println("AGENT_READY");
    }
}

final class DemoTransformer implements ClassFileTransformer {
    private final String id;
    private final boolean fail;

    DemoTransformer(String id, boolean fail) {
        this.id = id;
        this.fail = fail;
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // Lớp khác vẫn được JVM xử lý bình thường, nhưng không log.
        if (!"DemoTarget".equals(className)) {
            return null;
        }

        System.out.println("CALL " + id);

        if (fail) {
            // Lỗi có chủ đích để thấy T3 vẫn được gọi.
            throw new IllegalStateException("demo transformer failure");
        }

        // T1 và T3 không thay đổi bytecode.
        return null;
    }
}
```

Hai lớp cùng nằm trong file `ChainAgent.java`: `ChainAgent` là `public`, `DemoTransformer` có quyền truy cập package-private. Cả hai sẽ biên dịch thành `ChainAgent.class` và `DemoTransformer.class`, thuận tiện đóng gói vào JAR bằng lệnh không phụ thuộc wildcard.

Đoạn code này chỉ log khi `className` bằng `DemoTarget`, nên không in hàng loạt callback từ JDK hoặc những class khác. T1 và T3 trả `null`; T2 ném một unchecked exception. **Không có callback nào sửa `classfileBuffer` hoặc trả bytes thay thế**.

### 6.2. `Demo.java`: ứng dụng phải tiếp tục chạy

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("APP_BEFORE");

        // Dùng tên lớp dạng chuỗi để chủ động kích hoạt việc nạp class.
        Class<?> type = Class.forName("DemoTarget");
        Object result = type.getMethod("value").invoke(null);

        System.out.println("APP_RESULT=" + result);
    }
}

final class DemoTarget {
    public static int value() {
        return 7;
    }
}
```

`DemoTarget` có một phương thức static trả về số `7`, không phụ thuộc agent. `Class.forName` giúp đặt điểm nạp `DemoTarget` sau dòng `APP_BEFORE` trong thí nghiệm này. Mã ứng dụng vẫn hoạt động vì exception của T2 **không được JVM truyền nguyên trạng thành exception của `Class.forName`**.

### 6.3. `agent.mf`: manifest cho startup Java agent

```text
Manifest-Version: 1.0
Premain-Class: ChainAgent

```

Bảo đảm tệp manifest kết thúc bằng dòng trống. Ví dụ dùng **startup agent** qua `-javaagent` nên chỉ cần `Premain-Class` và `premain`; không cần `Agent-Class` hay `agentmain` của dynamic attach.

Không yêu cầu `Can-Retransform-Classes` vì ba transformer chỉ dùng `addTransformer(t)`, tương đương đăng ký với `canRetransform=false`.

### 6.4. Lệnh biên dịch và chạy

Trong thư mục chứa ba file, dùng JDK 17 trở lên:

```shell
javac ChainAgent.java Demo.java
jar cfm chain-agent.jar agent.mf ChainAgent.class DemoTransformer.class
java -javaagent:chain-agent.jar -cp . Demo
```

Lệnh `javac` tạo thêm `Demo.class` và `DemoTarget.class`; `-cp .` cho phép JVM tìm thấy chương trình mẫu và class target. JAR agent chỉ cần hai class `ChainAgent` và `DemoTransformer`; `DemoTarget` là một class của **ứng dụng**, không phải class cần nhét vào agent JAR.

**Stdout dự kiến trên HotSpot JDK 17/21 trong thí nghiệm:**

```text
AGENT_READY
APP_BEFORE
CALL T1_NULL
CALL T2_THROW
CALL T3_NULL
APP_RESULT=7
```

Kết quả minh họa ba điểm:

1. T1 trả `null` nhưng T2 vẫn được gọi.
2. T2 ném `IllegalStateException` nhưng T3 **vẫn được gọi**.
3. `DemoTarget.value()` vẫn trả `7` vì không có bytes thay thế, và JVM vẫn có thể nạp lớp bình thường.

**Lưu ý về quan sát:** ví dụ mô tả stdout do chương trình chủ động in. JVM/IDE/agent khác có thể bổ sung chẩn đoán hoặc log vào stderr; không lấy sự vắng mặt của stack trace trên console làm bằng chứng transformer không bị lỗi. Nếu có agent ngoài ví dụ hoặc môi trường đổi cách class được nạp, log thực tế có thể thêm khác biệt.

### 6.5. Thử nghiệm đối chứng A — bỏ transformer ném lỗi

Chỉ sửa `premain` để loại bỏ dòng:

```java
inst.addTransformer(new DemoTransformer("T2_THROW", true));
```

Sau đó biên dịch và đóng gói lại JAR rồi chạy một **JVM mới**:

```shell
javac ChainAgent.java Demo.java
jar cfm chain-agent.jar agent.mf ChainAgent.class DemoTransformer.class
java -javaagent:chain-agent.jar -cp . Demo
```

Stdout dự kiến:

```text
AGENT_READY
APP_BEFORE
CALL T1_NULL
CALL T3_NULL
APP_RESULT=7
```

So sánh thấy: có hoặc không có lỗi nội bộ T2, ứng dụng vẫn nhận kết quả `7`. Điều này **không chứng minh mọi lỗi transformer đều vô hại**: nếu code transformer vô tình sửa buffer, tạo class file không hợp lệ, làm I/O chặn class loading hoặc gây side effect ngoài mong muốn, hệ quả sẽ khác.

### 6.6. Thử nghiệm đối chứng B — thay lỗi bằng `null`

Để T2 giữ tên nhưng không ném, dùng:

```java
inst.addTransformer(new DemoTransformer("T2_THROW", false));
```

Sau khi biên dịch/đóng gói/chạy lại JVM mới, stdout vẫn có ba dòng `CALL`; vì `fail=false` nên T2 trả `null`. Kết quả của `DemoTarget.value()` vẫn là `7`.

Thử nghiệm này mô tả điểm tương đương **trên bytecode pipeline** giữa `throw` và `return null`, nhưng không có nghĩa hai nhánh giống nhau ở **logging, metrics, performance** hoặc khả năng chẩn đoán.

## 7. Bài toán thực tế: một transformer trước đã sửa bytes thì sao?

Trong ví dụ runnable, cả ba transformer đều không trả bytecode mới. Còn trong agent thực, chuỗi có thể là:

```text
Input class bytes: B0

Transformer A (tracing):
  B0 -> B1
  // B1 là class bytes hợp lệ, có bổ sung probe.

Transformer B (metrics):
  nhận B1
  ném IllegalStateException
  // B không tạo đầu ra thay thế.

Transformer C (security checks):
  nhận B1, không phải B0
  B1 -> B2
  // B2 là class bytes hợp lệ sau bước C.

JVM:
  thử xác minh và áp dụng B2.
```

Điều đáng lưu ý:

- **Không rollback các bước trước:** B thất bại không tự gỡ tracing của A.
- **Không bỏ qua các bước sau:** C vẫn có thể chạy và có thể tiếp tục biến đổi.
- **Không nhất thiết còn “metrics”:** B không tạo output, nên hiệu quả riêng của B không được đưa vào bytes cuối.
- **Không mặc nhiên có B2 hợp lệ:** A và C có thể chèn code không tương thích. JVM chỉ chấp nhận kết quả nếu đáp ứng class file và ràng buộc áp dụng.
- **Không gọi đây là transaction stage-by-stage:** class definition/redefinition/retransformation cuối được xử lý theo hợp đồng JVM, không phải mỗi transformer tự commit một phần class. “Giữ thay đổi trước” ở đây nghĩa **giữ bytes đang đi qua pipeline**, không có nghĩa partial class definition đã được cài vào JVM.

Một kiến trúc agent cần chức năng A, B, C **phụ thuộc lẫn nhau** không nên chỉ xếp ba transformer mà mặc định mọi phần luôn được áp dụng. Nên chuẩn bị bytecode hợp lệ, phát hiện thất bại ở từng bước và chỉ công bố feature hoạt động khi có kiểm chứng cuối.

## 8. Đăng ký nhiều transformer: cách đọc log và tránh hiểu sai

### 8.1. Đúng thứ tự đối với cùng nhóm, không phải mọi nhóm

Ba transformer trong thí nghiệm đều `false` nên thứ tự callback khớp thứ tự thêm. Nhưng nếu đăng ký `true` xen kẽ và JVM hỗ trợ, thứ tự callback phải theo **bốn nhóm** của `ClassFileTransformer`. Không thiết kế test “A rồi B” nếu A và B thuộc nhóm capability khác nhau.

Khi cần quan sát thứ tự, log ít nhất:

```text
event=transform
target=com/example/OrderService
loader=<identity của defining loader>
phase=LOAD | REDEFINE_OR_RETRANSFORM
transformer=metrics-v2
retransformCapable=false
decision=SKIP | OUTPUT | EXCEPTION
reason=CLASS_NOT_TARGETED | TRANSFORM_FAILED | ...
```

Đây là schema **minh họa**. Không bắt buộc mọi transformer có đúng các key này. Tránh in data từ method arguments hoặc class bytes khi chưa có lý do và chính sách bảo mật.

### 8.2. `removeTransformer` không hủy callback đang chạy

`Instrumentation.removeTransformer(t)` ngừng đăng ký cho những lần định nghĩa lớp về sau, nhưng API cảnh báo callback có thể vẫn đến **sau khi remove** do class loading đa luồng. Một transformer bị disable phải xử lý race/đồng bộ và bảo vệ trạng thái nội bộ, thay vì giả định không còn thread nào đang thực thi `transform`.

Nếu đăng ký **cùng một instance** nhiều lần, API cho phép nhưng khuyến cáo mạnh không nên làm; `removeTransformer` chỉ gỡ lần đăng ký gần nhất tương ứng. Tạo transformer instance riêng và quản lý lifecycle rõ ràng để báo cáo lỗi đúng callback.

### 8.3. Thread-safety và đệ quy class loading

JVM có thể định nghĩa nhiều class đồng thời. Transformer không được giả định callback là đơn luồng. Một transformer dùng mutable counters, map theo className hoặc output cache cần thread-safe theo thiết kế.

Các thao tác phức tạp trong callback (logging kéo theo class loading, reflective scan, mở file mạng, khóa không kiểm soát) có thể tăng độ trễ, gây tái nhập hoặc deadlock khi hệ thống đang ở giai đoạn class loading. Dùng filter mục tiêu thật sớm, hạn chế I/O, và cẩn trọng với dependency của agent. JVM loại trừ một số class cần cho việc thực thi transformer theo hợp đồng `addTransformer`, nhưng không được suy rằng callback vô điều kiện an toàn khỏi mọi vấn đề class loading.

## 9. Chẩn đoán khi transformer “không có tác dụng”

| Dấu hiệu | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Không có bất kỳ log nào từ T1 | Class chưa được định nghĩa sau khi đăng ký; filter tên/loader sai; transformer không được add | Log đăng ký, class internal name, defining loader, thứ tự khởi động |
| T1 có log rồi trả `null`, T2 vẫn có log | Hành vi bình thường | Đây là chuỗi callback, `null` không dừng pipeline |
| T2 ném exception, T3 vẫn có log | Hành vi do API quy định | Đặt log có kiểm soát **trước** khi ném; đừng dựa vào stack trace ở ứng dụng |
| Class load thành công dù T2 ném | JVM đã coi lỗi T2 như không biến đổi ở bước đó | Kiểm tra JVM đã nhận bytes nào từ các bước trước/sau |
| Instrumentation không hiện diện dù không có exception ở app | Transformer lọc nhầm target, trả `null`, lỗi bị JVM bỏ qua, output không thay đổi | Đếm target/matched/transformed/errors; kiểm chứng probe thực tế |
| Class không nạp được dù chỉ T2 ném exception | Có thể còn lỗi class file, verifier hoặc các transformer khác | Tách từng transformer, xác minh bytes cuối, kiểm tra exception ở tầng JVM |
| `retransformClasses` gọi mà T1 không chạy lại | T1 đăng ký `canRetransform=false` | Đọc capability/manifest, kiểm tra nhóm transformer, phân biệt “reused output” |
| T3 nhận bytes lạ hơn input từ file build | Transformer trước đã thay bytes; redefine/retransform có bytes nền khác | Chụp checksum/hash tại từng stage khi đủ an toàn; so thứ tự |
| Transformer bị remove nhưng đôi khi vẫn có callback | Race do class loading đa luồng | Thiết kế state, shutdown và metric chịu được callback trễ |
| Log ghi “success” sau `return null` | Chỉ báo callback hoàn tất, không có bytes mới | Phân biệt `VISITED`, `UNCHANGED`, `MODIFIED`, `FAILED` và xác minh feature |

### Một bộ đếm tối thiểu hữu ích

```text
transform_calls_total{transformer,phase}
transform_decisions_total{transformer,decision="UNCHANGED"}
transform_decisions_total{transformer,decision="MODIFIED"}
transform_decisions_total{transformer,decision="FAILED"}
transform_class_install_total{status="SUCCESS|ERROR"}      [nếu đo được]
feature_probe_verified_total{feature,class_group}          [nếu đo được]
```

Đây là tên metric gợi ý, không phải API có sẵn. Đặc biệt, không dùng số callback làm số lớp đã được instrument: cùng class có thể retransform nhiều lần, transformer có thể không đổi hoặc ném lỗi, và cùng tên binary có thể xuất hiện ở nhiều defining loader.

### Tại sao exception nên được ghi trong transformer?

Do JVM có thể bỏ qua exception của `transform` theo hợp đồng, một vòng kiểm thử chỉ viết:

```java
Class.forName("com.example.Service");
// Không có exception từ Class.forName -> xem như probe OK? SAI.
```

sẽ bỏ sót lỗi nội bộ. Hãy ghi trạng thái của lần biến đổi trong agent hoặc một hệ thống theo dõi lỗi do agent kiểm soát, rồi kiểm tra hậu điều kiện “probe đã thực sự hoạt động”. Không dùng `System.out.println` ồ ạt trong mọi callback production; ví dụ in console chỉ nhằm học hành vi.

## 10. Hai mẫu xử lý thực tế

### 10.1. Transformer chủ động bỏ qua class không thuộc phạm vi

```java
if (className == null || !className.startsWith("com/example/")) {
    return null;
}
```

Đây là **đoạn mã minh họa trong `transform`**, không phải chương trình độc lập. Nhánh `null` là quyết định bình thường “không sửa”, không nên ghi mức `ERROR` cho hàng nghìn class ngoài phạm vi.

### 10.2. Transformer phát hiện lỗi sửa bytecode

```java
try {
    // mutate(input) là hàm tạo MẢNG MỚI đã qua kiểm tra.
    return mutate(classfileBuffer);
} catch (IllegalClassFormatException e) {
    recordFailure(className, "INVALID_CLASS_INPUT", e);
    return null;
} catch (RuntimeException e) {
    recordFailure(className, "INTERNAL_TRANSFORM_FAILURE", e);
    return null;
}
```

Đây là **mẫu minh họa, chưa thể biên dịch độc lập** nếu chưa cài `mutate` và `recordFailure`. Mục đích là cho thấy: sau lỗi có thể **giữ nguyên bytes của stage này**, vẫn cho pipeline tiếp tục, nhưng lưu dấu thất bại. Nếu feature là bắt buộc, tầng điều phối phải xem trạng thái `FAILED` và xử lý theo chính sách đã định nghĩa, không coi sự sống còn của JVM là thành công nghiệp vụ.

**Thêm các nguyên tắc an toàn:**

- Không chỉnh sửa trực tiếp `classfileBuffer` dù sau đó trả `null`. Vi phạm này làm hành vi các transformer khác và JVM khó xác định.
- Một transformation có thể hợp lệ khi load mới nhưng không hợp lệ khi redefine/retransform vì giới hạn thay đổi cấu trúc. Hãy thiết kế output phù hợp từng phase.
- Khi bắt lỗi, đừng đệ quy log/reflect vô hạn trong class loading; giữ phần ghi nhận lỗi nhỏ gọn và có cơ chế giới hạn.
- Không dùng `catch (Throwable)` rộng như cách “nuốt mọi lỗi” không suy xét `OutOfMemoryError`, `ThreadDeath` hoặc các lỗi nghiêm trọng khác.

## 11. Bài tập tự kiểm tra

1. **T1 trả `null`, T2 trả một mảng bytes mới hợp lệ. Class cuối có thể thay đổi không?** Có. T1 chỉ không đổi ở bước mình; T2 có thể biến đổi.
2. **T1 trả bytes mới `B1`, T2 ném exception, T3 trả `null`. T3 nhận gì?** T3 nhận `B1` (bytes hiện hành trước T2), không tự động quay về `B0`.
3. **Nếu `transform` ném `IllegalClassFormatException`, JVM có luôn ném `ClassFormatError` ra ứng dụng không?** Không. Ở tầng transform, exception có tác dụng như `null` và pipeline vẫn được thử tiếp; lỗi cuối phụ thuộc bytes/hợp đồng JVM.
4. **Nếu mọi transformer trả `null`, class có chắc chắn nạp thành công không?** Không. Bytes gốc có thể không hợp lệ hoặc class loading còn lý do thất bại khác.
5. **Tại sao không nên trả `new byte[0]` để biểu thị “không đổi”?** Đó là mảng bytes thay thế không hợp lệ, khác với `null`; có thể làm JVM từ chối class file.
6. **Một transformer không hỗ trợ retransform có chạy lại khi `retransformClasses` được gọi không?** Không. Theo API, JVM tái áp dụng kết quả biến đổi trước đó của nhóm incapable, không gọi lại callback.
7. **A đăng ký `true` rồi B đăng ký `false`. Khi class mới nạp, ai có thể được gọi trước?** Theo thứ tự nhóm, B (`false`) trước A (`true`), dù thêm sau.
8. **T2 ném lỗi nhưng class chạy bình thường. Agent có nên báo tất cả transformer “thành công” không?** Không. T2 thất bại nội bộ; chỉ nên báo class load cuối đạt khi có bằng chứng, và ghi riêng lỗi T2.
9. **Có thể coi callback count là số class đã instrument không?** Không. Callback có thể `null`/throw, một class qua nhiều lần, và nhiều class loader có các class khác nhau.
10. **Mục tiêu an ninh bắt buộc nhưng transformer ném exception. Dựa vào exception để chặn class loading có an toàn không?** Không. Cần chiến lược kiểm chứng và fail-closed ở nơi có quyền điều phối; không dựa vào throw của `transform`.
11. **`classBeingRedefined != null` đủ biết đang redefine hay retransform không?** Không. Cần thêm ngữ cảnh của thao tác do agent kiểm soát.
12. **Transformer trả bytes mới nhưng JVM từ chối do cấu trúc không được phép. Có thể kết luận `transform` đã thất bại vì exception không?** Không nhất thiết. Callback có thể trả thành công, nhưng bước xác minh/áp dụng **sau callback** thất bại.

## 12. Tài liệu tham khảo chuẩn

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): quy tắc `return null`, việc ném exception, chuỗi input/output, thứ tự bốn nhóm, callback với Java 9+.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses`, capability và các lỗi khi JVM áp dụng class bytes.
- [Java SE 21 — IllegalClassFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html): checked exception khai báo trong `transform`.
- [Java SE 21 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): entry point và manifest của Java agent.

**Tóm tắt:** `return null` nghĩa là **không sửa ở bước này**. `throw` không được bắt có **cùng tác dụng đối với bytecode pipeline**: bỏ qua kết quả của bước này, tiếp tục gọi các transformer sau và thử áp dụng bytes cuối. Nó **không** tự rollback biến đổi trước, **không** tự abort class load và **không** bảo đảm ứng dụng an toàn/đạt mục tiêu instrumentation. Muốn phát hiện lỗi thật, phải đo từng stage và xác minh hiệu quả cuối.