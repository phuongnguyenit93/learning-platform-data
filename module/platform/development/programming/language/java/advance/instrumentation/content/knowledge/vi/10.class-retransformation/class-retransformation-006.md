# Gọi lại các transformer hỗ trợ retransformation theo đúng thứ tự

Trong Java Instrumentation, một class đã được JVM nạp có thể được **retransform** để áp dụng lại chuỗi biến đổi bytecode mà không cần khởi động lại tiến trình. Tuy nhiên, **không phải mọi `ClassFileTransformer` đã đăng ký đều được gọi lại**. JVM phân biệt transformer **có khả năng retransformation** (`canRetransform=true`) và transformer **không có khả năng này** (`canRetransform=false`). Khi `Instrumentation.retransformClasses(...)` được gọi, JVM **tái áp dụng kết quả cũ của nhóm không hỗ trợ** rồi **gọi lại nhóm hỗ trợ theo thứ tự được quy định**, chuyển đầu ra của bước trước thành đầu vào của bước sau.

Bài này thuộc chủ đề **Retransformation** trong Java Advance — Instrumentation. Trọng tâm là hiểu chính xác **transformer nào được gọi lại, thứ tự nào được áp dụng, bytes nào đi vào từng transformer**, và cách xác minh bằng một Java agent JDK 17+ có kết quả chạy thực tế. Đặc biệt, không được đồng nhất **thứ tự đăng ký toàn cục** với **thứ tự thực thi**, vì JVM sắp các transformer thành nhiều nhóm ưu tiên.

## 1. Phân biệt load, redefine và retransform

Ba sự kiện này liên quan tới `ClassFileTransformer` nhưng có điểm xuất phát khác nhau:

| Sự kiện | API hoặc nguồn kích hoạt | Input ban đầu | Transformer có `canRetransform=false` | Transformer có `canRetransform=true` |
| --- | --- | --- | --- | --- |
| **Load class lần đầu** | `ClassLoader.defineClass` hoặc tương đương | Bytes dùng để định nghĩa class | **Được gọi** | **Được gọi** |
| **Redefine class** | `Instrumentation.redefineClasses(...)` | Class bytes mới được cung cấp trong `ClassDefinition` | **Được gọi** | **Được gọi** |
| **Retransform class** | `Instrumentation.retransformClasses(...)` | Bytes gốc phù hợp của lần load hoặc redefine gần nhất | **Không được gọi lại; kết quả cũ được tái áp dụng** | **Được gọi lại** |

Hai hiểu nhầm thường gặp:

1. `canRetransform=false` **không có nghĩa** transformer chỉ chạy một lần trong suốt đời JVM. Nó vẫn có thể được gọi khi class được định nghĩa mới hoặc **redefine**. Nó chỉ **không nhận callback trong lượt retransformation**.
2. `canRetransform=true` **không có nghĩa** JVM tự động gọi transformer liên tục. Transformer được gọi lại khi một thao tác retransform được yêu cầu cho class phù hợp, hoặc khi class được load/redefine theo quy tắc API.

Chữ “retransform” là một **thao tác trên class đã load**, không phải việc Java tự reload class loader hay tạo class object mới. JVM thay thế định nghĩa method phù hợp trong phạm vi cho phép. Những frame method đang chạy có thể tiếp tục thực thi bytecode cũ; những lời gọi mới đi theo định nghĩa đã được áp dụng.

## 2. Bốn nhóm thứ tự chuẩn của ClassFileTransformer

Hợp đồng của Java SE `ClassFileTransformer` quy định **bốn nhóm**, theo thứ tự từ trước tới sau:

| Thứ tự | Nhóm | Cách đăng ký/nguồn |
| --- | --- | --- |
| **1** | Transformer **Java không hỗ trợ** retransformation | `inst.addTransformer(t, false)` hoặc `inst.addTransformer(t)` |
| **2** | Transformer **native không hỗ trợ** retransformation | JVMTI `ClassFileLoadHook` không có capability tương ứng |
| **3** | Transformer **Java hỗ trợ** retransformation | `inst.addTransformer(t, true)` |
| **4** | Transformer **native hỗ trợ** retransformation | JVMTI `ClassFileLoadHook` có capability tương ứng |

**Trong cùng một nhóm, các transformer chạy theo thứ tự được đăng ký.** Giữa các nhóm, JVM ưu tiên theo số nhóm nêu trên, **không** theo thời điểm đăng ký toàn cục.

Ví dụ:

~~~java
inst.addTransformer(transformerB, true);  // nhóm 3, đăng ký đầu
inst.addTransformer(transformerA, false); // nhóm 1, đăng ký sau
inst.addTransformer(transformerC, true);  // nhóm 3, đăng ký cuối
~~~

Ở **lần load đầu** của class được quan sát, thứ tự của ba **Java transformer** này là:

~~~text
A (nhóm 1) -> B (nhóm 3) -> C (nhóm 3)
~~~

**Không phải** `B -> A -> C` dù `B` được đăng ký trước. Nếu có transformer native, chúng được xen vào theo **vị trí nhóm 2 hoặc 4**, không phải tùy ý đặt trước/sau các Java transformer.

Khi **retransform**, thứ tự **callback Java mới** là:

~~~text
B (nhóm 3) -> C (nhóm 3)
~~~

Nhưng điều này **không có nghĩa** kết quả của `A` bị xóa. JVM tái áp dụng **kết quả đã có của A**, đúng vị trí của nhóm 1, **trước** khi gọi lại `B`. Phần tiếp theo làm rõ điều đó.

## 3. Chính xác chuyện gì xảy ra trong một lượt retransform?

Theo contract của `Instrumentation.retransformClasses(...)`, JVM thực hiện một chuỗi logic:

1. Bắt đầu từ **class bytes ban đầu** của lần định nghĩa hoặc redefine gần nhất, trước các phép biến đổi tương ứng.
2. Theo thứ tự nhóm chuẩn, đối với mỗi transformer **không hỗ trợ retransform**, JVM **dùng lại đầu ra đã được ghi nhận ở lần load/redefine trước**, xem như tự tái áp dụng phép biến đổi đó; **không gọi `transform(...)` của transformer này**.
3. Với mỗi transformer **hỗ trợ retransform**, JVM thực sự **gọi lại `transform(...)`** và cung cấp `classfileBuffer` là bytes tại vị trí hiện hành của chuỗi.
4. Sau khi các bước trong chuỗi hoàn tất, JVM **kiểm tra và áp dụng class bytes cuối** nếu hợp lệ. Nếu có lỗi làm thao tác thất bại, `retransformClasses(...)` báo lỗi; không có class nào trong lượt gọi đó được retransform thành công.

Sơ đồ cho ba Java transformer `A(false)`, `B(true)`, `C(true)`:

~~~text
LẦN LOAD ĐẦU:
  B0 --[gọi A]--> B1 --[gọi B]--> B2 --[gọi C]--> B3
                         class được định nghĩa từ B3

LẦN RETRANSFORM:
  B0' --[tái áp dụng kết quả A, KHÔNG gọi A]--> B1'
      --[gọi lại B]---------------------------> B2'
      --[gọi lại C]---------------------------> B3'
                            kiểm tra và áp dụng B3'
~~~

`B0'` có thể **không giống byte-for-byte** với `B0`: JVM được phép thay đổi thứ tự/số lượng mục constant pool hoặc một số chi tiết class-file representation mà không đổi ngữ nghĩa. Không viết transformer dựa trên giả định rằng cùng một constant-pool index, method order hoặc offset byte luôn tồn tại ở các lần retransform.

**Quan trọng:** JVM không mặc định lấy **B3 của lần retransform trước** làm đầu vào nguyên vẹn cho lần sau. Mỗi lượt được dựng từ bytes gốc phù hợp, tái áp dụng bước không hỗ trợ và chạy lại các bước có hỗ trợ. Do vậy một transformer `B(true)` nên hoạt động đúng khi được gọi nhiều lần và không nên phụ thuộc vào việc nhận lại chính mảng bytes nó đã trả về ở lần trước.

### “Kết quả cũ” không đồng nghĩa “gọi lại code cũ”

Giả sử `A(false)` đã thay `BASE` thành `ONE1` khi class được load. Ở lần retransform, JVM dùng lại tác dụng của `A` để `B(true)` vẫn nhìn thấy `ONE1`; **không chạy lại logic `A.transform(...)`**. Nếu `A` có side effect như tăng bộ đếm hoặc in log trong callback, side effect đó không xuất hiện lại chỉ vì class được retransform.

Không nên suy luận rằng việc không thấy log của `A` chứng tỏ class bytes bị “mất lớp biến đổi A”. Trong thiết kế đúng, có thể xảy ra đồng thời: **A không được gọi lại** và **đầu ra A vẫn có hiệu lực**.

## 4. Capability và manifest: điều kiện trước khi gọi lại

Muốn sử dụng retransformation từ Java agent, cần đáp ứng **cả hai điều kiện môi trường**:

- JAR agent khai báo `Can-Retransform-Classes: true` trong manifest.
- JVM implementation và cấu hình hiện hành thực sự hỗ trợ capability đó.

Kiểm tra bằng API:

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Chọn phương án load-time instrumentation hoặc báo rõ không hỗ trợ.
    return;
}
~~~

Đây là **đoạn minh họa đặt trong code có biến `Instrumentation inst`**; không phải chương trình chạy độc lập.

Khi đã có capability:

~~~java
inst.addTransformer(myTransformer, true);
~~~

là đăng ký một transformer thuộc nhóm hỗ trợ retransformation. Ngược lại:

~~~java
inst.addTransformer(myTransformer);         // canRetransform mặc định false
inst.addTransformer(otherTransformer, false);
~~~

đều thuộc nhóm Java không hỗ trợ. Nếu gọi `addTransformer(t, true)` khi JVM/agent không cho phép retransform, API có thể ném `UnsupportedOperationException`.

Trước khi thực sự gọi:

~~~java
inst.retransformClasses(Target.class);
~~~

cũng cần kiểm tra `inst.isModifiableClass(Target.class)`. Primitive class và array class **không bao giờ modifiable** theo API; ngoài ra có những class phụ thuộc JVM không thể sửa. `isModifiableClass == true` vẫn **không bảo đảm** mọi bytecode do transformer tạo ra đều hợp lệ để retransform: cấu trúc class và JVM verifier vẫn áp dụng các giới hạn riêng.

**Lưu ý:** `Can-Retransform-Classes` nằm trong **manifest của JAR agent**, không phải trong file Java hay classpath của ứng dụng. `-javaagent:...` tải agent và gọi `premain`; nó không tương đương việc tự chạy một class chứa method `premain` bằng `java ClassName`.

## 5. Demo đầy đủ JDK 17+: chứng minh nhóm trước và gọi lại đúng thứ tự

Ví dụ này được thiết kế để quan sát **cả thứ tự callback lẫn bytes thực sự chuyển giữa các bước**. Nó dùng **ba transformer Java**, nhưng **đăng ký sai thứ tự theo trực giác** để thấy JVM tự áp dụng thứ tự nhóm.

Mỗi transformer thay **một hằng chuỗi ASCII đúng 4 byte** trong constant pool của class đích:

| Transformer | `canRetransform` | Marker đầu vào | Marker đầu ra |
| --- | --- | --- | --- |
| `T1-incapable` | `false` | `BASE` | `ONE1` |
| `T2-capable` | `true` | `ONE1` | `TWO2` |
| `T3-capable` | `true` | `TWO2` | `DONE` |

**Thứ tự đăng ký cố ý:** T2 trước, T1 sau, T3 cuối. Nhưng thứ tự xử lý lúc load vẫn là **T1 → T2 → T3**, vì T1 thuộc nhóm 1 và T2/T3 thuộc nhóm 3.

Khi gọi retransform, T1 **không nhận callback**, còn T2 vẫn nhận marker `ONE1` từ phép biến đổi của T1 được JVM tái áp dụng. T3 nhận marker `TWO2` do T2 vừa tạo. Kết quả cuối vẫn là `DONE`.

### 5.1. Tạo RetransformOrderDemo.java

Lưu toàn bộ code sau trong **một file** `RetransformOrderDemo.java`. File có public class làm agent/ứng dụng và một class thường `OrderTarget`:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class RetransformOrderDemo {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("JVM/agent cannot retransform");
        }

        // Deliberately register a capable transformer before an incapable one.
        inst.addTransformer(new MarkerTransformer("T2-capable", "ONE1", "TWO2"), true);
        inst.addTransformer(new MarkerTransformer("T1-incapable", "BASE", "ONE1"), false);
        inst.addTransformer(new MarkerTransformer("T3-capable", "TWO2", "DONE"), true);
    }

    public static void main(String[] args) throws UnmodifiableClassException {
        System.out.println("supported="
                + instrumentation.isRetransformClassesSupported());
        System.out.println("before=" + new OrderTarget().message());
        System.out.println("modifiable="
                + instrumentation.isModifiableClass(OrderTarget.class));
        instrumentation.retransformClasses(OrderTarget.class);
        System.out.println("after=" + new OrderTarget().message());
    }

    private static final class MarkerTransformer implements ClassFileTransformer {
        private final String label;
        private final String expected;
        private final String replacement;

        MarkerTransformer(String label, String expected, String replacement) {
            this.label = label;
            this.expected = expected;
            this.replacement = replacement;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer)
                throws IllegalClassFormatException {
            if (!"OrderTarget".equals(className)) {
                return null;
            }
            byte[] changed = replaceConstant(classfileBuffer, expected, replacement);
            if (changed == null) {
                throw new IllegalClassFormatException(
                        label + ": marker " + expected + " not found exactly once");
            }
            System.out.printf("%s phase=%s %s->%s%n", label,
                    classBeingRedefined == null ? "load" : "retransform",
                    expected, replacement);
            return changed;
        }
    }

    private static byte[] replaceConstant(byte[] original, String from, String to) {
        if (from.length() != to.length()) {
            throw new IllegalArgumentException("Same-length ASCII only");
        }
        byte[] copy = original.clone();
        ByteBuffer pool = ByteBuffer.wrap(copy);
        if (pool.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("Not a class file");
        }
        pool.position(8);
        int constantPoolCount = Short.toUnsignedInt(pool.getShort());
        byte[] expected = from.getBytes(StandardCharsets.US_ASCII);
        byte[] replacement = to.getBytes(StandardCharsets.US_ASCII);
        int found = 0;
        for (int slot = 1; slot < constantPoolCount; slot++) {
            int tag = Byte.toUnsignedInt(pool.get());
            switch (tag) {
                case 1 -> {
                    int size = Short.toUnsignedInt(pool.getShort());
                    int offset = pool.position();
                    if (size == expected.length
                            && bytesEqual(copy, offset, expected)) {
                        System.arraycopy(replacement, 0, copy, offset, size);
                        found++;
                    }
                    pool.position(offset + size);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                        pool.position(pool.position() + 4);
                case 5, 6 -> {
                    pool.position(pool.position() + 8);
                    slot++;
                }
                case 7, 8, 16, 19, 20 ->
                        pool.position(pool.position() + 2);
                case 15 -> pool.position(pool.position() + 3);
                default -> throw new IllegalArgumentException("Invalid CP tag " + tag);
            }
        }
        return found == 1 ? copy : null;
    }

    private static boolean bytesEqual(byte[] bytes, int offset, byte[] match) {
        for (int n = 0; n < match.length; n++) {
            if (bytes[offset + n] != match[n]) return false;
        }
        return true;
    }
}

final class OrderTarget {
    String message() {
        return "BASE";
    }
}
~~~

**Vì sao ví dụ có parser constant pool?** Chúng ta muốn chứng minh transformer sau nhận **bytes do bước trước tạo ra**, không chỉ chứng minh thứ tự qua println. `replaceConstant` đi qua các mục constant pool, tìm **đúng một** hằng UTF-8 ASCII 4 byte và thay bằng bytes mới trên **bản sao** của class file. Nếu tìm không đúng một marker, demo ném `IllegalClassFormatException` để bộc lộ tình huống kiểm thử sai giả định.

Parser có xử lý `CONSTANT_Long` và `CONSTANT_Double` chiếm **hai index** trong constant pool (do đó có `slot++`). Đây chỉ là **demo trên class mục tiêu đơn giản**, không phải thư viện chỉnh sửa classfile tổng quát. File class dùng **modified UTF-8**; code thay ASCII cùng độ dài vì byte encoding trùng với ASCII trong trường hợp này. Không dùng kỹ thuật sửa bytes theo cách này cho chữ Unicode, chuỗi đổi độ dài, nhiều marker hoặc class phức tạp. Trong production, dùng thư viện xử lý class file đúng chuẩn như ASM/Byte Buddy hoặc JDK Class-File API (JDK 24+).

### 5.2. Tạo agent.mf

Tạo file manifest tên `agent.mf` trong cùng thư mục:

~~~text
Manifest-Version: 1.0
Premain-Class: RetransformOrderDemo
Can-Retransform-Classes: true
~~~

**File manifest cần có dòng trống cuối**. Khai báo `Can-Retransform-Classes: true` là thiết yếu vì demo đăng ký T2/T3 với `canRetransform=true` và thực sự gọi `retransformClasses`. Chỉ khai báo manifest không thể ép một JVM vốn không hỗ trợ capability phải hỗ trợ; `premain` kiểm tra và báo lỗi rõ ràng khi điều kiện không đáp ứng.

### 5.3. Biên dịch, đóng JAR và chạy

Dùng **JDK 17+**. Trong Bash hoặc PowerShell, thực hiện:

~~~bash
javac RetransformOrderDemo.java
jar --create --file order-agent.jar --manifest agent.mf 'RetransformOrderDemo.class' 'RetransformOrderDemo$MarkerTransformer.class'
java -javaagent:order-agent.jar -cp . RetransformOrderDemo
~~~

Các class file do `javac` tạo:

- `RetransformOrderDemo.class`: chứa `premain` và `main`.
- `RetransformOrderDemo$MarkerTransformer.class`: helper transformer cần nằm trong JAR agent.
- `OrderTarget.class`: class nghiệp vụ **nằm trên classpath ứng dụng**, không cần đóng trong JAR agent.

Cặp dấu nháy đơn quanh tên file có ký tự `$` giúp tránh shell nội suy tên class lồng. Khi chạy bằng PowerShell hoặc Bash, các lệnh trên phù hợp. Nếu dùng một shell khác, cần bảo đảm giữ nguyên dấu `$` trong tên file khi truyền vào `jar`.

### 5.4. Stdout đã kiểm chứng

**Kết quả thực tế khi biên dịch/chạy trên Zulu OpenJDK 24.0.2:**

~~~text
supported=true
T1-incapable phase=load BASE->ONE1
T2-capable phase=load ONE1->TWO2
T3-capable phase=load TWO2->DONE
before=DONE
modifiable=true
T2-capable phase=retransform ONE1->TWO2
T3-capable phase=retransform TWO2->DONE
after=DONE
~~~

Các dòng quan trọng:

1. `supported=true`: môi trường thử nghiệm có retransformation capability.
2. `T1-incapable phase=load` xuất hiện **trước** T2 dù T2 được đăng ký trước: **nhóm ưu tiên quyết định thứ tự thực thi**.
3. `T2-capable phase=load ONE1->TWO2`: T2 nhận dữ liệu đã được T1 biến đổi.
4. `T3-capable phase=load TWO2->DONE`: T3 nhận dữ liệu mới từ T2.
5. `before=DONE`: class `OrderTarget` được định nghĩa với giá trị cuối.
6. `modifiable=true`: class đích trên JVM thử nghiệm có thể retransform.
7. **Không có dòng T1 ở phase=retransform.** Điều này đúng vì T1 đăng ký với `false`.
8. T2 vẫn thấy `ONE1` ở phase=retransform: **tác dụng của T1 đã được JVM tái áp dụng, dù T1 không hề được gọi lại**.
9. T3 vẫn nhận `TWO2` từ T2, nên `after=DONE`. Điều này chứng minh thứ tự T2 → T3 trong nhóm capable.

Ví dụ còn một chi tiết hữu ích: `classBeingRedefined == null` ở lần load đầu, và khác `null` khi class được retransform. Hàm in log dùng nhãn `retransform` khi tham số khác `null` **vì demo không thực hiện redefine**. Trong agent tổng quát, tham số khác `null` cũng có thể xuất hiện ở lần **redefine**, nên không được dùng duy nhất điều kiện này để phân biệt tuyệt đối hai sự kiện.

Nếu sử dụng JVM không hỗ trợ retransformation, ví dụ chủ động lỗi trong `premain`; output ở trên **không cam kết** xuất hiện trên mọi JVM. Class file vẫn phải biên dịch được với Java 17+, nhưng việc thực thi retransform phụ thuộc manifest/JVM.

## 6. Đi sâu vào phép tái áp dụng transformer không hỗ trợ

Điểm cần nhớ nhất là **replay không phải callback**. Việc Java agent đăng ký T1 với `false` khiến callback của T1 bị bỏ qua tại lượt retransform; tuy nhiên JVM vẫn tái sử dụng kết quả đã được hình thành ở lần load hoặc redefine gần nhất.

Ví dụ giản lược theo demo:

~~~text
Nguồn class lúc đầu:        OrderTarget.message() -> "BASE"

Load:
    T1(false): BASE -> ONE1
    T2(true):  ONE1 -> TWO2
    T3(true):  TWO2 -> DONE

Retransform:
    JVM tự áp kết quả cũ của T1: BASE -> ONE1
    T2(true) được gọi lại:      ONE1 -> TWO2
    T3(true) được gọi lại:      TWO2 -> DONE
~~~

Điều này có một hệ quả quan trọng khi thiết kế các phép biến đổi phụ thuộc nhau: nếu T2 dựa vào marker do T1 tạo lúc load, việc T1 không chạy lại **không nhất thiết phá** T2. Chính cơ chế replay giữ cho chuỗi có đầu vào phù hợp. Ngược lại, nếu T2 **mong nhận output DONE của lượt retransform trước** và chỉ chèn thêm một thay đổi vào DONE, T2 có thể sai vì bytes đầu vào đúng của nó ở ví dụ này là **ONE1**, không phải DONE.

Một số thực hành đáng lưu ý:

- Nếu T1 tính toán ngẫu nhiên một marker lúc load, kết quả **đã áp dụng** của nó được dùng lại; không tính ngẫu nhiên mới chỉ vì có retransform.
- Nếu T1 ghi đếm trong callback, đếm đó không tăng khi chỉ retransform class, bởi T1 không được gọi lại.
- Nếu T1 không biến đổi gì (trả `null` lúc load), thì “kết quả” của nó cũng là **đầu vào giữ nguyên**, không phải một mảng byte mới bắt buộc được cấp.
- Nếu class từng được **redefine**, căn cứ replay sẽ theo **lần redefine gần nhất** chứ không phải vĩnh viễn theo file `.class` ban đầu trên đĩa.

API không hứa mọi chi tiết class-file bytes đều đồng nhất giữa các lượt, vì thế cần kiểm tra **ý nghĩa và cấu trúc** của kết quả thay vì so sánh chỉ số constant pool cố định.

## 7. Transformer trả null, trả bytes hoặc ném lỗi thì sao?

Trong cùng một chuỗi:

| Hành vi của transformer có khả năng retransform | Đầu vào transformer kế tiếp | Ý nghĩa |
| --- | --- | --- |
| Trả mảng `byte[] B` mới | Nội dung mảng B | Phép biến đổi được đưa vào bước kế tiếp |
| Trả `null` | Bytes hiện có ngay trước transformer đó | Không thay đổi ở bước này |
| Ném exception khi thực thi `transform` | JVM vẫn tiếp tục các transformer còn lại theo hợp đồng; tác dụng của bước đó như trả `null` | Không dùng exception như cơ chế dừng pipeline |
| Trả class bytes sai định dạng | Các bước sau vẫn có thể được gọi, nhưng class bytes cuối có thể bị verifier từ chối | Lời gọi `retransformClasses` có thể thất bại |

Với transformer không hỗ trợ retransform, nó **không chạy lại** trong lượt này nên không có kết quả `return` hoặc exception **mới** từ callback của nó. JVM tái áp dụng hiệu ứng của lần trước.

Hợp đồng `ClassFileTransformer` yêu cầu **không sửa trực tiếp mảng `classfileBuffer` do JVM cung cấp**. Nếu biến đổi, tạo mảng mới và trả về. Demo đã làm đúng điều đó với `original.clone()`. Nếu không có class cần sửa, `return null` là đúng:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"com/example/OrderService".equals(className)) {
        return null;
    }
    return transformKnownClass(classfileBuffer);
}
~~~

Đây là **mã minh họa** trong một class implement `ClassFileTransformer`; `transformKnownClass(byte[])` phải do ứng dụng cung cấp. Trả `null` để không thay đổi class hiện tại khác với việc trả một bản sao bytes rồi sửa logic không cần thiết.

Khi retransform/redefine thất bại vì bytes cuối không hợp lệ, các class tham gia cùng một lời gọi `retransformClasses(...)` **không được cập nhật một phần** theo hợp đồng API. Điều này không làm hoàn tác mọi side effect mà code transformer tự thực hiện trước khi thất bại (ví dụ ghi log hoặc tăng bộ đếm), vì các side effect đó nằm ngoài phép cập nhật class bytes.

## 8. Thứ tự đăng ký và thứ tự callback: những tình huống thực tế

### Tình huống A: hai Java transformer đều capable

~~~java
inst.addTransformer(first, true);
inst.addTransformer(second, true);
~~~

Cả hai thuộc **nhóm 3**. Với cùng một class được retransform, `first.transform(...)` được gọi trước `second.transform(...)`; bytes do first trả về thành đầu vào của second. Nếu first trả `null` thì second nhận input mà first đã nhìn thấy.

### Tình huống B: có một transformer không capable

~~~java
inst.addTransformer(firstCapable, true);
inst.addTransformer(secondIncapable, false);
~~~

Ở lần load/redefine, `secondIncapable` thuộc nhóm 1 nên được gọi **trước** `firstCapable` mặc dù đăng ký muộn hơn. Ở retransform, effect cũ của second được reapply **trước** khi gọi lại first.

### Tình huống C: hai transformer không capable

~~~java
inst.addTransformer(incapableA);
inst.addTransformer(incapableB, false);
~~~

Cả hai thuộc nhóm 1, nên ở lần load/redefine chạy theo thứ tự A → B. Trong lượt retransform, **không có callback mới của cả A lẫn B**, nhưng output trước của cả hai được tái áp dụng **đúng chuỗi** trước những transformer có capability.

### Tình huống D: Java agent cộng native JVMTI agent

Thứ tự không đơn thuần là “mọi Java agent trước mọi native agent”. Thứ tự đúng là **Java incapable → native incapable → Java capable → native capable**. Nếu T2 Java capable nhận input đã qua một native incapable transformer, đó là hệ quả nhóm 2 được áp dụng trước nhóm 3. Khi nhiều agent cùng can thiệp, phải xem **tất cả các nhóm**, không chỉ log của Java agent mình sở hữu.

### Tình huống E: thay đổi thứ tự bằng remove/add

`Instrumentation.removeTransformer(transformer)` có thể gỡ đăng ký cho những định nghĩa class về sau. Tuy nhiên API cảnh báo do tải class đa luồng, một transformer **vẫn có thể nhận callback sau khi remove** do race. Không nên dựa vào remove/add ở runtime để đảm bảo thứ tự đồng bộ tuyệt đối. Tốt hơn nên xác định pipeline có thứ tự từ khi khởi tạo agent, dùng một transformer điều phối nội bộ nếu cần nhiều bước phụ thuộc chặt chẽ.

## 9. Không được suy luận thứ tự giữa các class/thread từ log toàn cục

Thứ tự **trong một chuỗi biến đổi cho một class** được API quy định. Nhưng JVM có thể load/retransform nhiều class, kể cả bởi các thread khác nhau; log của callbacks từ các class khác **có thể đan xen**.

Ví dụ log:

~~~text
T1(OrderA)
T1(OrderB)
T2(OrderA)
T2(OrderB)
~~~

không nói rằng với OrderA, T2 chạy trước T1. Nó chỉ cho thấy các sự kiện của **hai class khác nhau** xen kẽ. Để phân tích thứ tự, gắn vào log ít nhất:

- `className` theo **internal name** (dùng dấu `/`, ví dụ `com/example/OrderA`).
- Class loader và module để phân biệt các class trùng tên.
- ID phiên transform hoặc phase load/retransform do agent theo dõi.
- Tên transformer và thứ tự callback **trong cùng một class invocation**.
- Optional checksum/độ dài của bytes trước-sau (không cần ghi toàn bộ bytecode).

Vì `ClassFileTransformer.transform(...)` có thể được JVM gọi đồng thời, không chia sẻ bộ đếm/trạng thái biến đổi tùy tiện giữa nhiều thread. Nếu cần metrics nên dùng công cụ đồng bộ đúng; nếu chỉ kiểm thử thứ tự ở demo, ta cố tình retransform **một** class trên thread chính để stdout dễ kiểm chứng.

## 10. Hai dạng lỗi về capability rất dễ bị đánh đồng

### 10.1. Có capability nhưng class không modifiable

Nếu `inst.isRetransformClassesSupported() == true` nhưng `inst.isModifiableClass(type) == false`, transformer đăng ký capable vẫn không cho phép retransform class đó. Ví dụ primitive và array class luôn không modifiable; nhiều loại class do JVM định nghĩa có hạn chế riêng.

Kiểm tra:

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(target)) {
    inst.retransformClasses(target);
}
~~~

Đây là **mảnh mã minh họa** với biến `Instrumentation inst`, `Class<?> target` và xử lý `UnmodifiableClassException` phù hợp ở scope bên ngoài. **Cả hai kiểm tra đều cần**, nhưng vẫn phải handle lỗi do transformer hoặc class bytes.

### 10.2. Class modifiable nhưng thiếu capability

Nếu `isModifiableClass(type) == true` còn `isRetransformClassesSupported() == false`, không thể gọi `retransformClasses(type)` thành công. Năng lực sửa một class nói chung và năng lực retransform của môi trường là **hai câu hỏi khác nhau**.

Manifest thiếu `Can-Retransform-Classes: true` là một nguyên nhân thường gặp, bên cạnh JVM không hỗ trợ. Nếu dùng `Can-Redefine-Classes`, đó là một capability **khác**, không thể thay cho `Can-Retransform-Classes`.

## 11. Giới hạn tái định nghĩa class không biến mất vì đúng thứ tự

Đúng thứ tự callback **không bảo đảm** JVM chấp nhận bytes cuối. Retransformation có các ràng buộc cấu trúc class; trên HotSpot/JVM TI, việc thay method body thường là hướng hợp lệ nhưng không thể tùy ý thêm/xóa field/method, đổi method signature hoặc superclass trong class đã load.

Cần nhớ:

- Transformer phải tạo **class file hợp lệ**, phù hợp class file version và JVM verifier.
- Cần giữ nguyên những thuộc tính cấu trúc bị hạn chế khi retransform/redefine.
- Phải giải quyết stack maps, exception table, labels và branch offsets nếu chèn bytecode phức tạp.
- Nếu class hiện có method đang chạy, **frame cũ có thể tiếp tục dùng bytes cũ**, còn lời gọi mới sử dụng định nghĩa mới. Kết quả quan sát tức thời cần tính tới điều đó.
- Retransformation **không tự chạy lại static initializer** và không tự đặt lại static fields hoặc trạng thái các object hiện có.
- Transformer được gọi trong phần xử lý lệnh yêu cầu, **trước khi** JVM xác minh và áp dụng bytes cuối. Log “transform succeeded” không tương đương “class installed successfully”.

Trong demo, thay hằng ASCII cùng độ dài không làm thay class structure. Với bytecode production, dùng framework hỗ trợ và test ở đúng JVM mục tiêu.

## 12. Chẩn đoán sự cố theo dấu vết callback

| Hiện tượng | Cách giải thích có thể đúng | Kiểm tra |
| --- | --- | --- |
| Transformer `false` không in log khi retransform | **Đúng hợp đồng**: result cũ được dùng lại | Kiểm tra bytes mà capable transformer tiếp theo nhận |
| Transformer `true` không in log khi retransform | Có thể chưa đăng ký, sai class filter, không có retransform hoặc lỗi trước khi vào callback | Kiểm tra manifest, capability, target, log wrapper |
| Transformer đăng ký trước nhưng chạy sau | Thuộc **nhóm khác** | In group/canRetransform, so với 4-group order |
| T2 không thấy marker do T1 tạo | T1 trả `null`/lỗi, hoặc thứ tự nhóm/đăng ký sai, hoặc class input khác dự kiến | So sánh marker/checksum giữa các bước |
| T2 nhìn thấy marker từ load cũ nhưng T1 không chạy | Cơ chế **replay kết quả của transformer không capable** | Không coi đó là lỗi |
| Kết quả bị cộng dồn sau nhiều retransform | Transformer không idempotent hoặc giả định sai về bytes đầu vào | Kiểm tra cơ chế replay; chạy retransform nhiều lần |
| Callback chạy đúng mà method vẫn cho giá trị cũ | Có thể frame cũ đang chạy, class bytes không đổi thực sự, hoặc redefine/retransform thất bại | Kiểm tra kết quả lệnh, method mới gọi, bytecode sau transform |
| `UnsupportedOperationException` | Thiếu capability hoặc thay đổi class không được hỗ trợ | Manifest, `isRetransformClassesSupported`, JVM TI restrictions |
| `UnmodifiableClassException` | Lớp đích không thể sửa | `isModifiableClass(target)` |
| `ClassFormatError` / `VerifyError` | Bytecode cuối bị hỏng | Verify output cuối và từng bước, stack maps |
| Order đúng trên máy A, sai trên máy B | Có native agent khác, thứ tự đăng ký thay đổi, JVM khác | Liệt kê Java/native agents, nhóm và thời điểm |
| Log đan xen lạ | Có nhiều class/thread đang được transform | Gắn class loader, module, thread, invocation ID |

**Quy trình debug đề xuất:** trước khi sửa bytes, chạy một lượt transformer **chỉ log** trả `null` để xác minh phân nhóm và callback. Sau đó thêm một phép biến đổi đơn giản, verify class; cuối cùng mới ghép các bước transformer phụ thuộc nhau. Không cần ghi log mọi class trong production: điều đó vừa chậm, vừa có thể gây rủi ro reentrancy.

## 13. Kiểm thử để không vô tình làm sai pipeline

Ngoài test một lần trong demo, một bộ regression test tốt cho retransformation nên bao gồm:

1. **Initial load:** expected callback order của cả nhóm incapable và capable.
2. **One retransform:** chỉ các capable callback được gọi; incapable không bị gọi lại.
3. **Replay:** bytes đưa vào capable đầu tiên vẫn chứa effect cũ của incapable.
4. **Multiple retransforms:** chạy ít nhất hai lần, xác nhận output không bị cộng dồn sai.
5. **Return null:** một capable transformer trả `null`; subsequent transformer nhận đúng bytes hiện hành.
6. **Chained transformation:** output trước là input sau, đúng thứ tự capable trong cùng nhóm.
7. **Agent mismatch:** manifest thiếu capability; phát hiện trước khi gọi retransform.
8. **Unmodifiable class:** không cố sửa `int[].class` hoặc lớp bị JVM đánh dấu `false`.
9. **Invalid output:** phát sinh bytes lỗi trong môi trường kiểm thử cô lập để xác nhận lỗi được báo đúng, không giả vờ class đã cập nhật.
10. **Loaded/active frames:** hiểu rằng code đang chạy trước transform có thể không nhìn thấy method bytes mới ngay trong frame hiện tại.

Với test nhiều transformer, **không nên chỉ dùng số dòng log toàn cục** để chứng minh thứ tự. Hãy đối chiếu **class mục tiêu, phase và marker/bytecode giữa các bước**, như demo `BASE → ONE1 → TWO2 → DONE`.

## 14. Bài tập tự kiểm tra

**Câu 1.** Đăng ký `T2(true)` trước `T1(false)`, cả hai Java. Khi một class mới được load, callback nào chạy trước?

**Câu 2.** Có hai Java transformer `A(true)` rồi `B(true)`. Khi retransform class, thứ tự callback nào được bảo đảm trong cùng nhóm? Nếu A trả `null` thì B nhận gì?

**Câu 3.** `X(false)` từng đổi marker `BASE → ONE1`. Ở retransform, không thấy `X.transform(...)` trong log, nhưng transformer `Y(true)` vẫn nhìn thấy `ONE1`. Có mâu thuẫn không?

**Câu 4.** Một Java transformer `A(false)` và native transformer `N(false)` cùng xử lý class. Nhóm nào trước?

**Câu 5.** Bạn gọi retransform hai lần. Transformer capable có nên mặc nhiên lấy output cuối của lần trước làm input không?

**Câu 6.** `isModifiableClass(MyClass.class)` trả `true`, nhưng `isRetransformClassesSupported()` trả `false`. Có thể gọi `retransformClasses(MyClass.class)` không?

**Câu 7.** Nếu T1 capable ném `IllegalClassFormatException` trong callback, T2 capable có chắc **không** được gọi nữa không?

**Câu 8.** Class đang có frame hoạt động trong một thread. Bạn retransform thành công ở thread khác. Frame hiện tại có nhất thiết đổi bytecode ngay giữa chừng không?

**Câu 9.** Một transformer incapable từng được gọi lúc load. Sau đó một công cụ thực hiện `redefineClasses(...)` và tiếp theo gọi `retransformClasses(...)`. Mốc đầu vào/replay gắn với lần nào?

**Câu 10.** Agent nhận ba sự kiện log theo thứ tự `A(T1)`, `B(T1)`, `A(T2)`. Có kết luận được T2 chạy “sai thứ tự” trong class A không?

### Đáp án

1. **T1(false)**, vì nhóm Java incapable là nhóm 1, trước nhóm Java capable là nhóm 3.
2. **A rồi B** theo thứ tự đăng ký. Nếu A trả `null`, B nhận **bytes hiện hành** mà A vừa nhìn thấy, không được mặc định khôi phục bytes gốc ban đầu khi trước A đã có biến đổi khác.
3. **Không.** JVM tái áp dụng output cũ của X mà không gọi lại X, sau đó mới gọi Y.
4. Nhóm **Java incapable (1)** trước nhóm **native incapable (2)**.
5. **Không.** Replay bắt đầu từ bytes gốc phù hợp rồi áp dụng kết quả của các transformer không capable; capable được gọi lại trên đầu vào của lượt đó, không phải mặc định chính output cuối lần trước.
6. **Không.** Cần cả capability JVM/agent và class modifiable.
7. **Không.** Theo contract, exception trong `transform` không tự cắt chuỗi; JVM vẫn gọi các transformer sau.
8. **Không.** Active frames có thể tiếp tục chạy bytecode cũ; lời gọi mới dùng định nghĩa mới đã được áp dụng.
9. Theo **lần redefine gần nhất** (và các kết quả transformer được ghi nhận liên quan tới định nghĩa đó), không nhất thiết theo lần load đầu tiên.
10. **Không.** Log có thể đan xen giữa class A và B; trong class A, thứ tự T1 trước T2 vẫn đúng.

## 15. Ghi nhớ

**Quy tắc chuẩn xác nhất:**

- **Lúc load/redefine:** chạy các nhóm theo thứ tự **Java incapable → native incapable → Java capable → native capable**, rồi theo thứ tự đăng ký bên trong từng nhóm.
- **Lúc retransform:** **không callback** nhóm incapable; **replay kết quả cũ** của họ ở đúng vị trí; **callback nhóm capable** theo thứ tự nhóm và thứ tự đăng ký.
- **Bytes là một chuỗi nối tiếp**: output của bước trước là input của bước sau; `null` giữ bytes hiện có.
- **Không tích lũy mù quáng output capable từ lượt trước**; mỗi lượt retransform dựng lại từ nguồn bytes phù hợp rồi áp dụng chuỗi theo API.
- **Thứ tự đúng chưa đủ**: cần manifest/capability, class modifiable, bytes hợp lệ, giới hạn JVM TI và kiểm thử trên runtime thật.

## 16. Tài liệu kỹ thuật chính thức

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): bốn nhóm thứ tự, truyền `classfileBuffer`, capable/incapable, `null`/exception, nghĩa vụ không sửa input array.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses` và cách replay các biến đổi trước đó.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR manifest, `premain` và điều kiện capability.
- [Java SE 21 — Java Virtual Machine Tool Interface (JVMTI)](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): native `ClassFileLoadHook`, khả năng RetransformClasses và ràng buộc class structure.
