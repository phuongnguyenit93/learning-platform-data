# Tái sử dụng kết quả transformer không hỗ trợ retransformation mà không gọi lại

Trong Java Instrumentation, `Instrumentation.retransformClasses(...)` có thể xử lý lại một lớp **đã được JVM tải**. Tuy nhiên, không phải transformer nào đã tác động đến lớp cũng được gọi lại. Đối với transformer đăng ký bằng `Instrumentation.addTransformer(transformer, false)`, JVM **tự áp dụng lại hiệu ứng của lần biến đổi trước** trong quá trình retransformation **mà không gọi lại phương thức `transform(...)`** của transformer đó.

Đây là quy tắc rất quan trọng khi nhiều Java agent hoặc nhiều `ClassFileTransformer` cùng tham gia vào một chuỗi biến đổi.

**Hai nhận định cần tránh:**

- “Transformer không hỗ trợ retransform không chạy lại, nên kết quả instrumentation trước đó bị mất.” **Sai**: kết quả cũ vẫn được tái áp dụng về mặt ngữ nghĩa.
- “Mỗi lần retransform là chạy lại tất cả transformer trên bytecode vừa được cài ở lượt trước.” **Sai**: JVM bắt đầu lại từ **initial class-file bytes** tương ứng lần load hoặc redefine gần nhất, áp dụng lại kết quả transformer incapable, rồi gọi nhóm capable.

Bài này giải thích đầy đủ nguồn bytes, thời điểm callback, thứ tự biến đổi, ranh giới capability và một ví dụ Java 17+ thực sự sửa constant pool để kiểm chứng cả **hành vi của class** lẫn **số lần callback**.

## 1. `canRetransform=false` thật sự có nghĩa gì?

Hai overload của `Instrumentation`:

~~~java
void addTransformer(ClassFileTransformer transformer);
void addTransformer(
        ClassFileTransformer transformer,
        boolean canRetransform);
~~~

Cách đăng ký một tham số **tương đương**:

~~~java
inst.addTransformer(transformer, false);
~~~

Đây là chữ ký API và một fragment với biến `inst`, `transformer` đã được khai báo; không phải chương trình tự chạy.

| Cách đăng ký | Tên nhóm | Khi class load | Khi `redefineClasses` | Khi `retransformClasses` |
|---|---|---|---|---|
| `addTransformer(t)` | *Retransformation incapable* | Gọi `t.transform` | Gọi `t.transform` | **Không gọi**; tái áp dụng kết quả trước |
| `addTransformer(t, false)` | *Retransformation incapable* | Gọi `t.transform` | Gọi `t.transform` | **Không gọi**; tái áp dụng kết quả trước |
| `addTransformer(t, true)` | *Retransformation capable* | Gọi `t.transform` | Gọi `t.transform` | **Gọi lại** `t.transform` |

Một transformer **incapable** vẫn hoàn toàn có khả năng đổi bytecode lúc **load** hoặc **redefine**. Từ “incapable” chỉ nhấn mạnh nó **không nhận callback lúc retransform**, chứ không cấm nó tạo bytecode mới.

Thuộc tính `canRetransform` gắn với **registration của transformer**, không phải là một cờ cố định trên chính đối tượng `Class<?>`. Cùng một class có thể được biến đổi lần lượt bởi transformer `false` và `true`.

## 2. Quy trình chính thức khi gọi `retransformClasses`

Ví dụ fragment:

~~~java
inst.retransformClasses(Target.class);
~~~

Giả sử `inst` là `Instrumentation` do JVM cấp, và `Target.class` đã được tải. Theo hợp đồng `Instrumentation.retransformClasses`:

1. JVM bắt đầu từ **initial class-file bytes**: bytes của lần định nghĩa lớp ban đầu hoặc bộ bytes được cung cấp trong **lần `redefineClasses` gần nhất**, trước các biến đổi.
2. Với mỗi transformer được đăng ký bằng **`canRetransform=false`**, JVM dùng lại kết quả của lần `transform` tại **lần class load hoặc redefine tương ứng**. Tác dụng giống như tái áp dụng phép biến đổi cũ **không thay đổi**, nhưng **không gọi callback**.
3. Với mỗi transformer được đăng ký bằng **`canRetransform=true`**, JVM **thực sự gọi lại** `transform(...)` theo thứ tự của chuỗi.
4. Kết quả cuối được kiểm tra và cài làm định nghĩa mới của class nếu hợp lệ; nếu thao tác thất bại, JVM trả lỗi tương ứng.

Sơ đồ gồm hai Java transformer A và B:

~~~text
Khi load Target:
Original bytes B0
  └── A(false).transform(B0) → B1       [A được gọi]
      └── B(true).transform(B1) → B2   [B được gọi]
          └── JVM định nghĩa Target bằng B2

Khi retransform lần 1:
Initial bytes B0 (không bắt đầu từ B2)
  └── reuse hiệu ứng A → B1            [KHÔNG gọi A]
      └── B(true).transform(B1) → B3   [B được gọi lại]
          └── JVM cài Target từ B3

Khi retransform lần 2:
Initial bytes B0
  └── reuse hiệu ứng A → B1            [KHÔNG gọi A]
      └── B(true).transform(B1) → B4   [B được gọi lại]
          └── JVM cài Target từ B4
~~~

`B0…B4` chỉ là ký hiệu logic cho các bộ class-file bytes, không phải tên biến Java có sẵn. Kết quả `B3` và `B4` có thể giống hoặc khác nhau tùy logic của B. **Lần retransform thứ hai không tự lấy đầu ra B3 làm base rồi chồng thêm mọi phép biến đổi.**

### “Reuse kết quả cũ” có nghĩa là gì?

Đặc tả nói **kết quả từ lần class load hoặc redefine trước** được dùng lại trong chuỗi. Điều đó không bắt buộc người viết agent phải biết JVM giữ một **cache vật lý** theo cấu trúc nào. Hãy coi đây là **cam kết về ngữ nghĩa bytecode**, không phải cam kết về bộ nhớ hoặc object identity của mảng `byte[]`.

Điều quan trọng hơn: nếu A(false) tính toán dựa trên một cấu hình thay đổi tại runtime, **đổi cấu hình sau khi class đã load rồi gọi retransform không làm JVM gọi A lại**. Với class đã được xử lý, JVM giữ hiệu ứng A tương ứng lần load/redefine trước, bất kể logic hiện tại của A có thể trả kết quả khác nếu được gọi.

## 3. Vì sao phải phân biệt “kết quả bytecode” và “số lần callback”?

Giả sử class ban đầu có:

~~~java
public static String message() {
    return "INIT";
}
~~~

Agent đăng ký:

- **A(false)**: khi `Target` được load, đổi literal `"INIT"` thành `"BASE"` trong `CONSTANT_Utf8_info`.
- **B(true)**: ở lần load chỉ quan sát, trả `null`; ở lần retransformation chuyển `"BASE"` thành `"LIVE"`.

Các literal đều dài **4 byte ASCII**, vì thế trong thí nghiệm kiểm soát có thể thay một entry trong constant pool mà không thay độ dài của class file.

Lần load:

~~~text
Target.message() gốc → "INIT"
      │
      ▼ A(false) chạy, đổi "INIT" → "BASE"
      ▼ B(true) chạy, return null
Target.message() sau load → "BASE"
~~~

Lần retransform:

~~~text
Bộ bytes nền tương ứng "INIT"
      │
      ▼ JVM tự tái áp dụng hiệu ứng A → "BASE"
        [không gọi A.transform lại]
      ▼ B(true) chạy, đổi "BASE" → "LIVE"
Target.message() sau retransform → "LIVE"
~~~

Số callback của A **không tăng**, nhưng tác dụng `"BASE"` từ A **vẫn là input của B**. Muốn chứng minh điều này, cần kiểm tra **hành vi `Target.message()`** bên cạnh bộ đếm callback. Chỉ in log của A có thể khiến người học lầm tưởng A không còn hiệu lực.

## 4. Thực hành Java 17+: transformer `false` thật sự sửa class file

Ví dụ dùng **JDK 17 trở lên**, không dùng thư viện ngoài. Các file Java ở **default package** để giảm nhiễu, không có yêu cầu phải triển khai trong package production. Mọi file là độc lập và có đúng tên class.

Cây thư mục:

~~~text
retransform-reuse/
├── Target.java
├── CpPatch.java
├── DemoAgent.java
├── DemoApp.java
├── MANIFEST.MF
└── out/              tạo bằng javac
~~~

### 4.1. `Target.java`

~~~java
public final class Target {
    public static String message() {
        return "INIT";
    }
}
~~~

Đây là class đích; được `Class.forName("Target")` tải **sau** khi agent đăng ký hai transformer. Chúng ta không sửa method signature, fields hay hierarchy.

### 4.2. `CpPatch.java` — tìm đúng UTF-8 constant pool entry

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class CpPatch {
    public static byte[] replaceUtf8(
            byte[] source, String oldValue, String newValue) {
        byte[] oldBytes = oldValue.getBytes(StandardCharsets.UTF_8);
        byte[] newBytes = newValue.getBytes(StandardCharsets.UTF_8);
        if (oldBytes.length != newBytes.length) {
            throw new IllegalArgumentException(
                    "replacement must have same UTF-8 length");
        }

        byte[] output = source.clone();
        ByteBuffer bb = ByteBuffer.wrap(output);
        if (bb.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("not a class file");
        }
        bb.getShort(); // minor version
        bb.getShort(); // major version
        int entries = Short.toUnsignedInt(bb.getShort());
        int replacements = 0;

        for (int i = 1; i < entries; i++) {
            int tag = Byte.toUnsignedInt(bb.get());
            switch (tag) {
                case 1 -> {
                    int length = Short.toUnsignedInt(bb.getShort());
                    int offset = bb.position();
                    if (length == oldBytes.length
                            && Arrays.equals(
                                Arrays.copyOfRange(
                                    output, offset, offset + length),
                                oldBytes)) {
                        System.arraycopy(
                                newBytes, 0, output, offset, length);
                        replacements++;
                    }
                    bb.position(offset + length);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                    bb.position(bb.position() + 4);
                case 5, 6 -> {
                    bb.position(bb.position() + 8);
                    i++; // long/double chiếm hai slot
                }
                case 7, 8, 16, 19, 20 ->
                    bb.position(bb.position() + 2);
                case 15 ->
                    bb.position(bb.position() + 3);
                default -> throw new IllegalArgumentException(
                        "unknown constant tag " + tag);
            }
        }

        if (replacements != 1) {
            throw new IllegalArgumentException(
                    "expected one literal; found " + replacements);
        }
        return output;
    }
}
~~~

Giải thích ngắn gọn và lưu ý:

1. Luôn tạo `byte[] output = source.clone()`; **không sửa trực tiếp** mảng `classfileBuffer` được JVM truyền vào transformer.
2. `ByteBuffer` đọc class-file magic `0xCAFEBABE`, version và constant pool. Các giá trị `tag` cho biết độ dài entry cần đọc/bỏ qua.
3. Riêng entry **`CONSTANT_Utf8` (tag 1)**, demo chỉ sửa chuỗi ASCII khớp toàn bộ và **có cùng độ dài**; `replacements != 1` được coi là lỗi.
4. CONSTANT_Long/Double chiếm hai slot trong constant pool, vì vậy cần tăng `i` thêm một lần.
5. Đây là **parser tối thiểu**, phù hợp thí nghiệm với `"INIT"`, `"BASE"`, `"LIVE"`; không phải công cụ bytecode production. Nó không hỗ trợ thay đổi độ dài entry, modified UTF-8 tổng quát, labels, attributes, stack map frames hoặc method bodies tùy ý. Với biến đổi phức tạp, dùng ASM, Byte Buddy hoặc Java Class-File API đúng phiên bản JDK.

Nhờ chỉ thay giá trị của literal UTF-8 với cùng độ dài, class file đầu ra vẫn giữ đúng định danh và cấu trúc của `Target`.

### 4.3. `DemoAgent.java` — hai transformer và bộ đếm

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class DemoAgent {
    private static Instrumentation instrumentation;
    private static final AtomicInteger frozen = new AtomicInteger();
    private static final AtomicInteger dynamic = new AtomicInteger();

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("retransform=false");
            return;
        }
        inst.addTransformer(new FrozenTransformer(), false);
        inst.addTransformer(new DynamicTransformer(), true);
        System.out.println("retransform=true");
    }

    public static Instrumentation inst() { return instrumentation; }

    public static void counts() {
        System.out.println(
                "calls frozen=" + frozen.get()
                + " dynamic=" + dynamic.get());
    }

    static final class FrozenTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module, ClassLoader loader, String name,
                Class<?> existingClass, ProtectionDomain domain,
                byte[] bytes) {
            if (!"Target".equals(name)) return null;
            System.out.println(
                    "frozen call=" + frozen.incrementAndGet());
            return CpPatch.replaceUtf8(bytes, "INIT", "BASE");
        }
    }

    static final class DynamicTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module, ClassLoader loader, String name,
                Class<?> existingClass, ProtectionDomain domain,
                byte[] bytes) {
            if (!"Target".equals(name)) return null;

            if (existingClass == null) {
                System.out.println(
                        "dynamic load call=" + dynamic.incrementAndGet());
                return null;
            }

            System.out.println(
                    "dynamic revisit call=" + dynamic.incrementAndGet());
            return CpPatch.replaceUtf8(bytes, "BASE", "LIVE");
        }
    }
}
~~~

Trong lần load, **A(false)** đổi `"INIT"` thành `"BASE"` và **B(true)** chỉ ghi log. Trong lần retransform, A **không** được callback, B được callback và đổi `"BASE"` sang `"LIVE"`.

`existingClass == null` nghĩa callback đang xử lý một **lớp mới được định nghĩa**; khi nó khác null, callback xảy ra trong quá trình **redefine hoặc retransform**. Không thể dựa riêng vào tham số đó để phân biệt hai hoạt động. Trong chương trình này chỉ gọi `retransformClasses`, nên có thể giải thích chính xác log `revisit` là retransform.

`name` là **JVM internal name**, ở đây `"Target"` vì class nằm trong default package. Với package `demo`, tên sẽ có dạng `"demo/Target"`. Filter theo tên giúp chương trình không đổi/lấy log của các class JDK đang được tải. `AtomicInteger` là bộ đếm callback an toàn khi nhiều thread truy cập.

### 4.4. `DemoApp.java` — quan sát class qua ba thời điểm

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = DemoAgent.inst();
        if (!inst.isRetransformClassesSupported()) {
            System.out.println("skipped");
            return;
        }

        Class<?> clazz = Class.forName("Target");
        Method message = clazz.getMethod("message");
        System.out.println("initial=" + message.invoke(null));
        DemoAgent.counts();

        if (!inst.isModifiableClass(clazz)) {
            System.out.println("unmodifiable");
            return;
        }

        inst.retransformClasses(clazz);
        System.out.println("afterFirst=" + message.invoke(null));
        DemoAgent.counts();

        inst.retransformClasses(clazz);
        System.out.println("afterSecond=" + message.invoke(null));
        DemoAgent.counts();
    }
}
~~~

`Class.forName("Target")` là thời điểm tải class đích theo ý định của demo. `getMethod("message")` và `invoke(null)` lấy kết quả **của method đang thực thi trong JVM**, không phải chỉ đọc một bản sao file trên ổ đĩa.

`isModifiableClass` là phép kiểm tra khả năng sửa **class cụ thể**. Nó khác với `isRetransformClassesSupported()`, vốn hỏi **JVM/agent có capability** hay không. Nếu JVM hoặc lớp đích không hỗ trợ, demo thoát an toàn thay vì yêu cầu retransform.

### 4.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true

~~~

Đây là manifest nằm trong JAR agent. Phải có dòng trống kết thúc. `Can-Retransform-Classes: true` **yêu cầu** capability nhưng không tự bảo đảm mọi JVM cung cấp. Nó **khác** `Can-Redefine-Classes`, thuộc tính dùng khi muốn thay định nghĩa bằng bytes truyền vào `redefineClasses`.

### 4.6. Biên dịch và chạy

Từ thư mục `retransform-reuse`, tạo `out`.

Với Bash/Git Bash:

~~~bash
mkdir -p out
~~~

Với PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Chạy các lệnh JDK 17+:

~~~bash
javac --release 17 -d out Target.java CpPatch.java DemoAgent.java DemoApp.java
jar --create --file demo.jar --manifest MANIFEST.MF -C out .
java -javaagent:demo.jar -cp demo.jar DemoApp
~~~

`javac` tạo thêm `DemoAgent$FrozenTransformer.class` và `DemoAgent$DynamicTransformer.class`. `jar ... -C out .` tự đóng gói các inner classes, nên không cần ghi tên `$...` tường minh. Java chạy bằng **`-javaagent` trước tên main class**; không cần `Main-Class` trong manifest vì ta dùng `-cp demo.jar DemoApp`.

**Stdout đã kiểm chứng khi chạy trên JDK 24 với `javac --release 17`:**

~~~text
retransform=true
frozen call=1
dynamic load call=1
initial=BASE
calls frozen=1 dynamic=1
dynamic revisit call=2
afterFirst=LIVE
calls frozen=1 dynamic=2
dynamic revisit call=3
afterSecond=LIVE
calls frozen=1 dynamic=3
~~~

**Phân tích chính xác output:**

- Khi load `Target`, A tạo `BASE` và B được gọi lần đầu, nhưng không đổi bytes.
- `initial=BASE` xác nhận **A đã có tác dụng thật sự**.
- Lần `retransformClasses(clazz)` thứ nhất không có log `frozen call=2`. Dù vậy, B nhận base đã được tái áp dụng hiệu ứng A, tìm thấy `BASE` và tạo `LIVE`, dẫn tới `afterFirst=LIVE`.
- Lần `retransformClasses(clazz)` thứ hai cũng **không gọi lại A**. B vẫn có base chứa `BASE`, do đó `afterSecond=LIVE`.
- Tổng số callback A **luôn là 1**, B tăng từ 1 đến 3, như `calls frozen=1 dynamic=3`.

Nếu JVM thiếu capability retransformation, demo có thể in `retransform=false` rồi `skipped`; những dòng của đường thành công phụ thuộc khả năng của JVM. Nếu phép thay bytes không hợp lệ, có thể có lỗi class format hoặc kết quả khác. Không nên sử dụng stdout cố định trên làm lời hứa cho mọi phiên bản/bản phân phối JVM.

## 5. Bảng bằng chứng: callback không chạy lại nhưng tác dụng vẫn còn

| Hoạt động | Gọi A(false)? | Gọi B(true)? | Hiệu ứng được dùng | Hành vi method |
|---|---|---|---|---|
| Load `Target` | Có, 1 lần | Có, 1 lần | A: `INIT→BASE`; B: không đổi | `BASE` |
| Retransform lần 1 | **Không** | Có, lần 2 | Replay A: `BASE`; B: `BASE→LIVE` | `LIVE` |
| Retransform lần 2 | **Không** | Có, lần 3 | Replay A: `BASE`; B: `BASE→LIVE` | `LIVE` |

Điểm quan trọng nhất: **không có log A không chứng minh A bị mất tác dụng**. Trong ví dụ, B sửa được literal `"BASE"` ở cả hai lượt vì JVM đã tái áp dụng hiệu ứng cũ của A trong pipeline.

Một phép kiểm tra chỉ dùng hai transformer luôn `return null` sẽ minh họa callback nhưng **không chứng minh tác dụng bytecode được giữ**. Vì vậy ví dụ sử dụng một bộ bytes thay đổi thật, rồi kiểm tra hành vi phương thức.

## 6. Nếu transformer `false` trả `null` thì sao?

`ClassFileTransformer` cho phép:

~~~java
return null; // không sửa classfileBuffer ở bước này
~~~

Khi A(false) trả `null` trong lần load/redefine, JVM coi bước A là **không biến đổi bytes**. Trong các lần retransform về sau, nó **không gọi lại A** và tái áp dụng đúng tác dụng “không đổi” của bước trước.

~~~text
Load:
B0 -- A(false) returns null --> B0 -- B(true) --> B1

Retransform:
B0 -- reuse A's previous no-op, no callback --> B0
   -- B(true) --> B2
~~~

Giả sử A dựa trên `featureFlag` và ở lần load, flag đang tắt nên A trả `null`. Sau khi đổi `featureFlag=true` và gọi `retransformClasses`, **A không được gọi lại để tính hiệu ứng mới**. Trạng thái flag hiện tại không biến A(false) thành transformer capable.

Muốn tính lại logic trên class đã tải, hãy chọn cơ chế phù hợp **ngay từ thiết kế**: transformer `true` có thể được gọi khi retransform; hoặc có thể dùng `redefineClasses` nếu agent có capability riêng và bạn chuẩn bị bytes hợp lệ. Không nên dựa vào việc thay đổi một biến của A rồi mong JVM tự chạy callback A ở lần retransform.

## 7. Thứ tự bốn nhóm transformer

Đặc tả `ClassFileTransformer` sắp xếp theo **bốn nhóm**:

1. **Java retransformation-incapable** (`canRetransform=false`).
2. **Native retransformation-incapable** (qua JVM TI).
3. **Java retransformation-capable** (`canRetransform=true`).
4. **Native retransformation-capable**.

**Trong mỗi nhóm**, transformer chạy theo thứ tự được đăng ký. Nhưng thứ tự **nhóm** có ưu tiên hơn thứ tự đăng ký toàn cục.

Ví dụ fragment:

~~~java
inst.addTransformer(transformerB, true);  // đăng ký trước
inst.addTransformer(transformerA, false); // đăng ký sau
~~~

Khi class load/redefine, trong hai **Java** transformer này, A(false) **vẫn đứng trước** B(true) dù A được đăng ký sau. Khi retransform, JVM áp dụng lại tác dụng A ở vị trí nhóm incapable, **không gọi A**, rồi mới gọi B.

Khi có A1(false), A2(false), B(true):

~~~text
Load:
B0 → A1(false) → B1 → A2(false) → B2 → B(true) → B3

Retransform:
B0 → [reuse A1 → B1] → [reuse A2 → B2] → B(true) → B4
      không callback A1   không callback A2   callback B
~~~

Nếu có native transformer, chúng tham gia ở các nhóm 2 và 4 tương ứng. Kết quả đầu ra của một bước trở thành **input của bước sau**, nên B không thể mặc định `classfileBuffer` mình nhận vẫn là bytes gốc nguyên vẹn.

## 8. Vì sao retransform nhiều lần không tự chồng mã B của lượt trước?

**Sai lầm phổ biến:** hiểu retransformation thành “lấy class đang được cài và gọi lại A, B trên đúng bytes đó”.

~~~text
Sai:
B0 -- A --> B1 -- B --> B2
B2 -- A --> ... -- B --> B3
B3 -- A --> ... -- B --> B4
~~~

Trong khi nguyên tắc đúng là:

~~~text
Đúng:
B0 -- [tái áp dụng A] --> B1 -- B(true) --> B2
B0 -- [tái áp dụng A] --> B1 -- B(true) --> B3
B0 -- [tái áp dụng A] --> B1 -- B(true) --> B4
~~~

Đó là lý do trong demo `CpPatch` B(true) **luôn** tìm được `"BASE"` ở mỗi lượt retransform dù class sau lượt trước đang trả `"LIVE"`.

Điều này làm giảm nguy cơ chồng lặp một biến đổi chỉ vì dùng output của lượt trước làm base, **nhưng không phải lời bảo đảm transformer capable luôn idempotent**. Có thể nhiều agent cùng instrument một method, các transformer capable khác thay đổi input, và bytes từ lần **redefine** gần nhất thay đổi nền. Vẫn cần logic phân tích class đúng và kiểm chứng output khi biến đổi phức tạp.

### Initial bytes không nhất thiết giống bit-for-bit

API nêu rõ initial class-file bytes được sử dụng khi retransform **có thể không giống từng byte** với mảng ban đầu được đưa vào `ClassLoader.defineClass` hoặc `redefineClasses`. Ví dụ constant pool có thể thay đổi thứ tự/bố cục, một số attribute có thể không tồn tại, hoặc thứ tự method không có ý nghĩa có thể khác.

Vì thế đừng giả định **offset tuyệt đối** của một UTF-8 entry trong constant pool được giữ cố định giữa các lần callback. Trong production, parse class file bằng công cụ hiểu cấu trúc, không gắn patch theo vị trí byte thủ công.

## 9. Re-define khác với re-transform tại chỗ nào?

| Hoạt động | Dữ liệu đầu vào quan trọng | A(false) | B(true) |
|---|---|---|---|
| Class load | Bytes dùng để định nghĩa class | Được gọi | Được gọi |
| `retransformClasses` | Initial bytes + tác dụng incapable từ lần load/redefine | **Không được gọi; reuse** | **Được gọi** |
| `redefineClasses` | Bytes mới do caller đưa trong `ClassDefinition` | **Được gọi** | **Được gọi** |

Đặc tả nói **lần class load hoặc redefine** là cơ sở cho kết quả mà nhóm incapable tái áp dụng. Vì thế, nếu agent thực hiện một lần **redefine** sau load, A(false) có thể được gọi trong quá trình redefine và tạo kết quả mới. Những lần retransform sau dựa trên nền liên quan đến redefine mới nhất, không nhất thiết là bytes của bản class tải ban đầu.

Muốn dùng `redefineClasses`, agent phải yêu cầu capability **`Can-Redefine-Classes`** và kiểm tra `isRedefineClassesSupported()`; điều này **khác** capability retransformation.

## 10. Capability và việc chọn class đích

Manifest agent thường có:

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true

~~~

`Can-Retransform-Classes: true` là **yêu cầu**. Trước khi đăng ký B(true) hoặc yêu cầu retransform, kiểm tra JVM:

~~~java
if (!inst.isRetransformClassesSupported()) {
    return;
}
if (!inst.isModifiableClass(clazz)) {
    return;
}
inst.retransformClasses(clazz);
~~~

Đoạn trên là fragment trong method có `Instrumentation inst` và `Class<?> clazz`.

- `isRetransformClassesSupported()` kiểm tra capability chung, tùy JVM và manifest.
- `isModifiableClass(clazz)` kiểm tra lớp cụ thể; primitive và array class không modifiable.
- `addTransformer(t, true)` sẽ ném `UnsupportedOperationException` nếu cấu hình JVM không hỗ trợ retransform.
- `retransformClasses` có thể thất bại do capability, class không modifiable, bytes sai format/version, hoặc thay đổi không hợp lệ về cấu trúc (chẳng hạn thêm field/method).
- Lời gọi với nhiều class tạo một nhóm để hỗ trợ thay đổi liên quan; khi thao tác ném lỗi, API quy định **không class nào trong nhóm được retransform**.

Với lớp đang thực thi, **active method frames** tiếp tục chạy bytecode cũ; **lời gọi mới** dùng định nghĩa mới. Retransformation không chạy lại static initializer và không tạo lại object hiện hữu.

Những điều kiện này không làm A(false) được gọi lại. Đó là **cơ chế riêng** của nhóm incapable theo hợp đồng callback.

## 11. Lưu ý khi dùng `removeTransformer`

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

Lệnh này **gỡ registration**, không trực tiếp hoàn tác bytecode trong các lớp đã tải. Một class đã được instrument tiếp tục chạy định nghĩa đang cài cho đến khi có thay đổi lớp hợp lệ.

Nếu muốn phục hồi class sau khi remove, cần chủ động thiết kế quá trình retransform/redefine và xét **tập transformer còn đăng ký**, biến đổi đã áp dụng, hạn chế JVM cùng bytecode cuối; không xem `removeTransformer` là nút hoàn tác tự động.

Do concurrency, đặc tả còn lưu ý transformer có thể nhận callback **sau khi bị gỡ** vì có hoạt động class loading đã bắt đầu trước đó. Transformer cần an toàn với callback đến muộn.

## 12. `return null`, exception và kiểm tra bytes

Trong callback:

~~~java
if (!"demo/Target".equals(className)) {
    return null;
}
return transformedClassBytes;
~~~

Đây là fragment trong một `transform(...)` có tham số `className` và `byte[] transformedClassBytes`, không tự chạy độc lập.

- **`return null`**: không biến đổi ở bước này. Với transformer incapable, tác dụng “không đổi” của lần trước sẽ được áp dụng ở các lần retransformation tiếp theo mà không callback.
- **`return byte[]`**: phải là mảng mới chứa class file hợp lệ; không sửa trực tiếp `classfileBuffer`.
- **Ném exception không bắt trong `transform`**: JVM vẫn thử gọi các transformer còn lại và tiếp tục thử load/redefine/retransform; về hiệu ứng bước transformer đó tương đương không thay đổi. Đừng dùng `throw` như cơ chế chắc chắn hủy class load.
- **Biến đổi không hợp lệ**: nếu class file cuối sai, JVM có thể ném lỗi format, version, verifier hoặc linkage. Chỉ vì transformer A và B đã chạy không có nghĩa định nghĩa được chấp nhận.

Với mã production, cần filter theo class loader/tên/method, tránh class JDK hoặc phụ thuộc bootstrap, tạo bytes bằng thư viện đáng tin, cập nhật đúng stack-map frames, exception ranges và labels khi sửa control flow.

## 13. Giải thích các lỗi và triệu chứng thường gặp

| Quan sát | Giải thích | Kiểm tra |
|---|---|---|
| A(false) chỉ có log ở lúc load | Hành vi **đúng**: không callback ở retransform | Xem hiệu ứng bytes, không chỉ số log |
| Sau retransform class vẫn có hiệu ứng A | JVM tự tái áp dụng kết quả A cũ | So sánh hành vi class và input của B |
| B(true) thấy bytes đã qua A | Transformation chain được xếp theo nhóm | Kiểm tra `canRetransform` và thứ tự áp dụng |
| B không tìm thấy literal từ A | A chưa tác dụng trên lớp đó, biến đổi lỗi hoặc sai class loader | Kiểm tra đúng tên internal, bytes đầu vào, lifecycle |
| Thay cấu hình A(false) nhưng class cũ không đổi | A không được gọi lại khi retransform | Dùng transformer capable hoặc cơ chế redefine phù hợp |
| Đăng ký A(false) sau khi class đã tải, chỉ gọi retransform | Không có callback mới cho A ở đường retransformation | Thiết kế đăng ký trước lần load/redefine phù hợp |
| `UnsupportedOperationException` lúc `addTransformer(..., true)` | Thiếu capability retransformation | Kiểm tra manifest và `isRetransformClassesSupported()` |
| `UnmodifiableClassException` lúc retransform | Class cụ thể không thể sửa | Hỏi `isModifiableClass` |
| `ClassFormatError`/`LinkageError` | Bytes biến đổi sai định dạng/giới hạn | Kiểm tra từng bước và bytes cuối |
| `classBeingRedefined != null`, tưởng chắc chắn là redefine | Trường này cũng khác null khi retransform | Xác định API thực sự kích hoạt callback |
| Gỡ A rồi thấy instrumentation vẫn hoạt động | `removeTransformer` không trực tiếp khôi phục class | Thiết kế rollback rõ ràng |
| Biến đổi lặp làm tăng probe | Transformer capable không tương thích input chain | Kiểm thử idempotence, nhiều agent và redefinition |

**Quy trình debug:** xác định đúng agent JAR và manifest → thời điểm class load → registration của từng transformer → class loader và internal name → output A(false) khi load/redefine → input B(true) khi retransform → kiểm tra bytes/hành vi định nghĩa cuối.

Không nên dùng “A có log mới hay không” làm thước đo duy nhất của “hiệu ứng A còn tồn tại hay không”.

## 14. Các hệ quả thiết kế và hiệu năng

Không gọi lại A(false) có thể tránh việc chạy lại callback A tốn CPU, nhưng **toàn bộ retransform không miễn phí**. JVM vẫn phải xử lý yêu cầu, áp dụng lại các tác dụng của nhóm incapable theo hợp đồng, gọi nhóm capable, kiểm tra bytecode, và có thể cần điều chỉnh mã JIT đã tối ưu hóa.

Chọn `false` khi một biến đổi nên được quyết định **lúc load/redefine** và giữ nguyên khi các agent khác yêu cầu retransformation. Chọn `true` nếu biến đổi cần **tính lại theo cấu hình mới** khi class đã tải. Không mặc định tất cả agent phải đăng ký capable vì nó đòi capability và tăng bề mặt callback cần kiểm soát.

Với nhiều agent:

1. Thiết kế đầu ra của transformer sau tương thích **bytes đã được transformer trước sửa**, không giả định đầu vào luôn là class file nguyên bản.
2. Filter sớm theo internal class name, module và class loader để giảm overhead, tránh tự instrument nhầm class phụ thuộc.
3. Test cả **số callback** và **kết quả thực tế** của class trước/sau retransform.
4. Phân biệt `retransformClasses` với `redefineClasses`; chỉ thao tác thứ hai làm nhóm incapable được **gọi callback lại** trên định nghĩa mới.
5. Có chiến lược tắt/bỏ instrumentation rõ ràng; chỉ `removeTransformer` không phải thao tác rollback bytecode.
6. Nếu code transformer phức tạp, dùng API bytecode có hỗ trợ phiên bản JDK đích thay vì sửa class file bằng cách thay bytes thô như demo.

## 15. Tự kiểm tra

1. **`addTransformer(A)` có tương đương `addTransformer(A, false)`?** Có.
2. **A(false) có được phép đổi bytecode khi class load không?** Có.
3. **Khi `retransformClasses` chạy, A(false) có được gọi lại?** Không.
4. **A(false) không được gọi lại, vậy hiệu ứng A bị xóa?** Không; JVM tái áp dụng kết quả biến đổi cũ.
5. **Kết quả biến đổi cũ được lấy theo mốc nào?** Lần class load hoặc **redefine gần nhất** có liên quan, không đơn giản là output của lần retransform cuối.
6. **Vì sao B(true) có thể thấy literal `BASE` dù A không chạy ở lượt retransform?** Vì hiệu ứng A đã được JVM tái áp dụng trước B.
7. **Lần retransform thứ hai lấy output `LIVE` của B ở lần trước rồi áp B thêm lần nữa?** Không theo mô hình cơ bản; JVM dựng lại từ initial bytes và kết quả incapable, rồi gọi B.
8. **A(false) trả `null` khi load, sau đó cấu hình đổi. Retransform có gọi A để quyết định lại?** Không.
9. **Tại sao cùng A(false) có thể được gọi lại ở `redefineClasses`?** Vì redefinition không phải retransformation; API yêu cầu callback A trong redefine.
10. **Thứ tự giữa Java A(false) và B(true) nếu B đăng ký trước?** A vẫn chạy trước B theo nhóm.
11. **Dùng `removeTransformer(A)` có tự sửa tất cả class cũ về trước instrument không?** Không.
12. **Nếu JVM không hỗ trợ retransform, có thể ép đăng ký B(true) không?** Không; phải kiểm tra capability.
13. **Output `calls frozen=1 dynamic=3` chứng minh gì?** A chỉ callback ở lần load, B callback ở lần load và hai lần retransform.
14. **Vì sao cần quan sát `initial=BASE`, `afterFirst=LIVE`?** Vì chúng xác nhận **tác dụng biến đổi bytes** bên cạnh việc đếm callback.
15. **Có nên dùng `CpPatch` của ví dụ để sửa mọi class trong production?** Không; nó cố ý giới hạn một literal ASCII có cùng độ dài.

### Tài liệu chuẩn

- [Java SE 21 — `Instrumentation.retransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đặc tả quá trình **reuse** kết quả transformer incapable mà không callback, capability, giới hạn và lỗi.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thứ tự bốn nhóm, đầu vào/đầu ra và cách xử lý `return null`/exception.
- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent manifest và `Can-Retransform-Classes`.
- [Java Virtual Machine Specification 21 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): constant pool, tag và `CONSTANT_Utf8_info`.
- [Java SE 21 — `UnmodifiableClassException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): class không thể sửa.

**Ghi nhớ:** `canRetransform=false` nghĩa là **không gọi lại `transform(...)` trong lần retransformation**, **không có nghĩa hiệu ứng bytecode đã có biến mất**. JVM dùng lại kết quả từ lần load/redefine trước, sau đó gọi những transformer `true` để tạo định nghĩa cuối cho lớp.