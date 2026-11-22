# Kết quả của transformer trước trở thành đầu vào của transformer sau

Trong Java Instrumentation, khi nhiều `ClassFileTransformer` cùng xử lý **một định nghĩa class**, JVM áp dụng các phép biến đổi thành **chuỗi nối tiếp** (*transformation chain*). Mỗi transformer nhận một mảng byte biểu diễn class file ở trạng thái hiện tại. Nếu transformer trả về mảng byte mới, **kết quả đó trở thành đầu vào logic của transformer kế tiếp**. Vì vậy thứ tự thực thi, cách xử lý `null` và lỗi định dạng class file đều ảnh hưởng trực tiếp đến bytecode cuối cùng mà JVM xác minh và sử dụng.

Bài này giải thích chính xác hợp đồng của API, thứ tự transformer khi load/redefine/retransform, cách tránh sửa trực tiếp đầu vào và một Java agent chạy được trên JDK 17+ cho thấy hai transformer liên tiếp biến `SEED → NEXT → DONE`. Mục tiêu là hiểu **chuỗi biến đổi**, chưa cần thư viện ASM hay Byte Buddy.

## 1. Mô hình tổng quát: luồng dữ liệu của một class file

Giả sử JVM cần định nghĩa class `LessonTarget` có bytecode ban đầu `B0`. Hai transformer được đăng ký trong cùng nhóm, theo thứ tự `T1` rồi `T2`:

~~~text
Class-file bytes B0
       |
       v
   T1.transform(...)
       |
       | return B1
       v
   T2.transform(..., classfileBuffer = B1)
       |
       | return B2
       v
 JVM kiểm tra và định nghĩa class từ B2
~~~

Có thể biểu diễn: `B1 = T1(B0)`, `B2 = T2(B1)`. Đây là **hàm hợp thành**: `T2(T1(B0))`; thông thường không thể thay bằng `T1(T2(B0))` vì các phép biến đổi có thể phụ thuộc thứ tự.

Chẳng hạn:

- `T1` tìm một hằng chuỗi `"SEED"` trong constant pool, đổi thành `"NEXT"`.
- `T2` tìm `"NEXT"` trong **bytes đã được T1 biến đổi**, đổi thành `"DONE"`.
- Class được định nghĩa với hằng cuối cùng `"DONE"`.

Nếu `T2` chạy trước `T1`, nó chưa thấy `"NEXT"` nên không thay gì; class có thể kết thúc ở `"NEXT"` thay vì `"DONE"`. Thứ tự là một **ràng buộc thiết kế** khi transformer sau phụ thuộc đầu ra của transformer trước.

Quan trọng: API bảo đảm **nội dung các byte đã biến đổi** được chuyển cho bước sau, không yêu cầu hai transformer thấy cùng một đối tượng `byte[]` theo nghĩa `==`. Không nên phụ thuộc identity của mảng.

## 2. Hợp đồng ClassFileTransformer.transform(...)

Trên Java 17+, một cách override thông dụng là:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException {
    // Đọc bytes hiện tại, có thể tạo bytes mới.
    return null;
}
~~~

Đây là **chữ ký API minh họa**, nằm trong một lớp triển khai `ClassFileTransformer`; phần thân `return null` chỉ minh họa tình huống không thay đổi. Các tham số có ý nghĩa:

| Tham số | Ý nghĩa khi xử lý chuỗi |
| --- | --- |
| `module` | Module của class đang được xác định |
| `loader` | Class loader đang định nghĩa/đã định nghĩa class; có thể `null` với bootstrap loader |
| `className` | Internal name dạng `java/lang/String`; không giả định luôn khác `null` |
| `classBeingRedefined` | Đối tượng `Class<?>` ở lần redefine/retransform; có thể `null` khi định nghĩa mới |
| `protectionDomain` | Miền bảo vệ gắn với class |
| `classfileBuffer` | **Bytes đầu vào tại bước này**, có thể đã được transformer trước thay đổi |
| Giá trị trả về | Bytes đầu ra cho transformer sau hoặc `null` để giữ nguyên đầu vào hiện tại |

Theo đặc tả, transformer **không được chỉnh sửa tại chỗ** mảng `classfileBuffer`. Nếu cần thay bytecode, hãy tạo mảng mới (ví dụ `classfileBuffer.clone()` hoặc bytes do công cụ tạo class file sinh ra) rồi trả về mảng đó.

### Return null có nghĩa gì?

Nếu `T1` trả `null`, JVM dùng nguyên **bytes đang đi vào T1** để tiếp tục sang `T2`. Không có nghĩa là khôi phục lại bytecode ban đầu.

~~~text
B0 --T1 trả B1--> B1 --T2 trả null--> B1 --T3 trả B3--> B3
B0 --T1 trả null--> B0 --T2 trả B2  --> B2
~~~

Tương tự, nếu transformer không quan tâm tới `className` hiện tại, nó nên trả `null` để giữ nguyên chuỗi biến đổi của class đó.

### Ngoại lệ trong transformer

Nếu một transformer ném ngoại lệ không được tự xử lý, **JVM vẫn tiếp tục gọi các transformer còn lại** theo contract; với chuỗi biến đổi, tác dụng của lần ném đó tương đương transformer trả `null`. Ném `IllegalClassFormatException` giúp biểu đạt hoặc chẩn đoán tình huống bytes đầu vào sai định dạng, nhưng **không tự động dừng mọi bước phía sau**.

Cần phân biệt: **lỗi trong transformer** có thể được bỏ qua để tiếp tục, còn **mảng byte mới không hợp lệ** do transformer khác trả về có thể khiến JVM từ chối định nghĩa, redefine hoặc retransform class sau giai đoạn kiểm tra. Không dựa vào việc ném ngoại lệ trong transformer để thực hiện cơ chế rollback.

## 3. Thứ tự thực tế: theo nhóm capability rồi theo thứ tự đăng ký

Lệnh đăng ký thông dụng:

~~~java
inst.addTransformer(transformerA);          // tương đương canRetransform=false
inst.addTransformer(transformerB, false);   // không được gọi khi retransform
inst.addTransformer(transformerC, true);    // có thể được gọi khi retransform
~~~

Với `canRetransform=true`, JVM/agent phải thực sự hỗ trợ retransformation; nếu không, `addTransformer(..., true)` có thể ném `UnsupportedOperationException`. Kiểm tra `inst.isRetransformClassesSupported()` trước nếu cần capability đó.

**Không đúng** khi nói mọi transformer luôn chạy đơn thuần theo thứ tự bạn gọi `addTransformer`. Java Instrumentation định nghĩa bốn **nhóm xử lý có thứ tự ưu tiên**:

| Thứ tự nhóm | Loại transformer |
| --- | --- |
| 1 | Transformer Java **không có** khả năng retransformation |
| 2 | Transformer native **không có** khả năng retransformation |
| 3 | Transformer Java **có** khả năng retransformation |
| 4 | Transformer native **có** khả năng retransformation |

Trong **mỗi nhóm**, transformers chạy theo thứ tự chúng được đăng ký. Transformer native đến từ cơ chế `ClassFileLoadHook` của JVM Tool Interface (JVMTI); khi chỉ dùng Java agent thuần túy, thường cần quan tâm nhiều nhất tới **nhóm Java không có** và **nhóm Java có** retransformation.

Ví dụ nếu một Java agent gọi:

~~~java
inst.addTransformer(transformerB, true);   // nhóm 3, đăng ký sớm
inst.addTransformer(transformerA, false);  // nhóm 1, đăng ký muộn
~~~

thì khi class được định nghĩa mới, `transformerA` vẫn chạy **trước** `transformerB` vì thuộc nhóm ưu tiên cao hơn. Muốn đảm bảo `T1 → T2` chỉ bằng thứ tự đăng ký, hãy để hai transformer trong **cùng nhóm** hoặc thiết kế rõ thứ tự khác nhóm.

Một instance transformer có thể bị đăng ký nhiều lần nhưng API **khuyến cáo tránh điều đó** vì dễ gây biến đổi lặp; nên tạo các instance riêng với trách nhiệm minh bạch.

## 4. Ví dụ đầy đủ: hai transformer phụ thuộc đầu ra của nhau

Ví dụ sau là một Java agent tự chứa. Nó dùng hai transformer trên một class duy nhất:

- `T1` đổi hằng UTF-8 ASCII `SEED` thành `NEXT`.
- `T2` chỉ nhận diện `NEXT`, đổi thành `DONE`.
- `LessonTarget.message()` được JVM định nghĩa **sau khi** agent đã đăng ký hai transformer và trả về `DONE`.

Để demo chạy bằng JDK thuần, code thao tác một mục `CONSTANT_Utf8` của constant pool có **cùng độ dài ASCII**. Đây là kỹ thuật minh họa luồng bytes; không phải công cụ thay bytecode tổng quát. Trong hệ thống thực tế, dùng ASM/Byte Buddy hoặc một parser class file đúng chuẩn.

### 4.1. Tạo TransformerChainDemo.java

Lưu toàn bộ đoạn sau trong **một file** tên `TransformerChainDemo.java`:

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class TransformerChainDemo {
    public static void premain(String options, Instrumentation inst) {
        inst.addTransformer(new MarkerTransformer("T1", "SEED", "NEXT"));
        inst.addTransformer(new MarkerTransformer("T2", "NEXT", "DONE"));
    }

    public static void main(String[] args) {
        System.out.println("main=" + new LessonTarget().message());
    }

    private static final class MarkerTransformer implements ClassFileTransformer {
        private final String label;
        private final String from;
        private final String to;

        MarkerTransformer(String label, String from, String to) {
            this.label = label;
            this.from = from;
            this.to = to;
        }

        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer)
                throws IllegalClassFormatException {
            if (!"LessonTarget".equals(className)) {
                return null;
            }

            byte[] changed = replaceUtf8Constant(classfileBuffer, from, to);
            if (changed == null) {
                throw new IllegalClassFormatException(
                        label + ": expected exactly one " + from);
            }
            System.out.printf("%s input=%s output=%s%n", label, from, to);
            return changed;
        }
    }

    private static byte[] replaceUtf8Constant(
            byte[] original, String from, String to) {
        if (from.length() != to.length()) {
            throw new IllegalArgumentException("Equal-length ASCII only");
        }
        byte[] bytes = original.clone();
        ByteBuffer cp = ByteBuffer.wrap(bytes);
        if (cp.getInt() != 0xCAFEBABE) {
            throw new IllegalArgumentException("Not a class file");
        }
        cp.position(8);
        int count = Short.toUnsignedInt(cp.getShort());
        byte[] source = from.getBytes(StandardCharsets.US_ASCII);
        byte[] replacement = to.getBytes(StandardCharsets.US_ASCII);
        int matches = 0;
        for (int index = 1; index < count; index++) {
            int tag = Byte.toUnsignedInt(cp.get());
            switch (tag) {
                case 1 -> {
                    int length = Short.toUnsignedInt(cp.getShort());
                    int at = cp.position();
                    if (length == source.length
                            && equalsBytes(bytes, at, source)) {
                        System.arraycopy(replacement, 0, bytes, at, length);
                        matches++;
                    }
                    cp.position(at + length);
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 ->
                        cp.position(cp.position() + 4);
                case 5, 6 -> {
                    cp.position(cp.position() + 8);
                    index++;
                }
                case 7, 8, 16, 19, 20 ->
                        cp.position(cp.position() + 2);
                case 15 -> cp.position(cp.position() + 3);
                default -> throw new IllegalArgumentException(
                        "Unknown constant-pool tag: " + tag);
            }
        }
        return matches == 1 ? bytes : null;
    }

    private static boolean equalsBytes(byte[] bytes, int at, byte[] needle) {
        for (int i = 0; i < needle.length; i++) {
            if (bytes[at + i] != needle[i]) {
                return false;
            }
        }
        return true;
    }
}

final class LessonTarget {
    String message() {
        return "SEED";
    }
}
~~~

**Giải thích những chi tiết quyết định:**

1. `premain` được JVM gọi trước `main` khi agent được nạp bằng `-javaagent`. Nhờ vậy, hai transformer được đăng ký trước lần `LessonTarget` được định nghĩa.
2. Cả hai được gọi bằng `addTransformer(transformer)`, nghĩa là `canRetransform=false`. Chúng thuộc **cùng nhóm**, nên `T1` chạy trước `T2`.
3. `"LessonTarget".equals(className)` lọc đúng class mục tiêu; với class khác, trả `null`. Việc đặt literal ở phía trái cũng xử lý an toàn trường hợp `className == null`.
4. `replaceUtf8Constant` sao chép `original.clone()`. Nó đọc header `CAFEBABE`, đi qua từng mục constant pool theo `tag`, chỉ thay một chuỗi `CONSTANT_Utf8` khớp chính xác bốn byte ASCII.
5. `CONSTANT_Long`/`CONSTANT_Double` (tag 5/6) chiếm hai index constant pool, nên vòng lặp tăng thêm `index++`. Không bỏ qua quy tắc này vì có thể đọc sai vị trí mục tiếp theo.
6. `T1` thấy `SEED` và trả bytes chứa `NEXT`. Khi `T2` nhận `classfileBuffer`, nó tìm được `NEXT` **chỉ vì bytes đã qua T1**.
7. Nếu class mục tiêu không chứa **đúng một** marker dự kiến, demo ném `IllegalClassFormatException` để lộ ra điều kiện thử nghiệm không đúng. Do contract vẫn có thể tiếp tục gọi transformer sau, hãy kiểm tra stdout và hành vi thực tế, không xem exception như cơ chế dừng toàn bộ pipeline.

### 4.2. Tạo agent.mf

Tạo file `agent.mf` trong cùng thư mục:

~~~text
Manifest-Version: 1.0
Premain-Class: TransformerChainDemo
~~~

Bảo đảm file manifest **có một dòng trống kết thúc**. Ví dụ này chỉ đo luồng **load-time transformation**, nên không cần khai báo capability retransformation hoặc redefinition.

### 4.3. Biên dịch, đóng JAR agent và chạy

Dùng JDK 17 trở lên. Lệnh sau dùng cú pháp shell có dấu nháy đơn, hoạt động trong Bash và PowerShell:

~~~bash
javac TransformerChainDemo.java
jar --create --file transformer-chain-agent.jar --manifest agent.mf TransformerChainDemo.class 'TransformerChainDemo$MarkerTransformer.class'
java -javaagent:transformer-chain-agent.jar -cp . TransformerChainDemo
~~~

`javac` tạo `TransformerChainDemo.class`, `TransformerChainDemo$MarkerTransformer.class` và `LessonTarget.class`. JAR agent chứa hai class cần để `premain` và transformer chạy; `LessonTarget.class` nằm ở classpath ứng dụng, để JVM đọc và áp dụng transformation khi load.

**Stdout chính xác đã kiểm tra khi chạy ví dụ bằng JDK 24:**

~~~text
T1 input=SEED output=NEXT
T2 input=NEXT output=DONE
main=DONE
~~~

Đây là **bằng chứng thực thi**: nếu `T2` nhận bytes ban đầu chưa qua `T1`, nó không thể tìm mục UTF-8 `NEXT` chỉ có sau khi `T1` đổi `SEED`. Chuỗi thực tế đã cho `LessonTarget.message()` trả về `DONE`.

Code dùng cú pháp `switch ->` và API Instrumentation có sẵn từ Java 17. Có thể chạy lại trong một thư mục sạch, tránh các bản `.class` hoặc JAR cũ che kết quả kiểm thử.

### 4.4. Giới hạn của kỹ thuật sửa constant pool trong ví dụ

Đoạn demo chỉ thay **một** mục UTF-8 ASCII có độ dài bằng nhau. Không dùng nó như bộ sửa mọi chuỗi hoặc mọi method:

- Class file dùng **modified UTF-8** cho mục `CONSTANT_Utf8`; ASCII ngắn trong demo không có khác biệt, còn các ký tự Unicode hoặc `NUL` cần được xử lý đúng định dạng.
- Đổi độ dài chuỗi sẽ phải thay độ dài constant pool entry và có thể làm thay vị trí các bytes phía sau; `System.arraycopy` cùng độ dài không đủ.
- Hằng trong constant pool có thể được nhiều vị trí cùng tham chiếu; đổi nó có thể ảnh hưởng nhiều hành vi khác ngoài mục đích.
- Khi thêm/sửa method bytecode thật cần bảo đảm constant pool, offset, exception table, stack frames và class-file validation hợp lệ.
- Nếu chỉ muốn quan sát mà không thay đổi, transformer nên **trả `null`**, tránh tạo bản sao bytes không cần thiết.

Để biến đổi production code, ưu tiên ASM hoặc Byte Buddy. Dù dùng thư viện nào, **hợp đồng nối tiếp các transformer vẫn giữ nguyên**.

## 5. Trường hợp null, byte[] mới, ngoại lệ: transformer sau nhận gì?

Giả sử có ba transformer Java trong cùng nhóm, đăng ký lần lượt `T1, T2, T3`:

| Hành vi | Bytes mà bước tiếp theo nhận | Hệ quả |
| --- | --- | --- |
| `T1` trả mảng mới `B1` | `B1` | Biến đổi của T1 được đưa vào chuỗi |
| `T2` trả `null` | `B1` | Giữ nguyên mọi sửa đổi đã tích lũy |
| `T2` trả mảng mới `B2` | `B2` | T3 nhìn thấy kết quả T2 |
| `T2` ném ngoại lệ | `B1` | Theo contract, các transformer sau vẫn được gọi |
| `T3` trả bytes sai định dạng | Bytes cuối có thể bị JVM từ chối | Việc chuỗi đã chạy không bảo đảm class được load thành công |

**Một transformer không có API “bỏ qua mọi transformer sau”.** Nếu cần cơ chế lọc tập trung, hãy đăng ký một transformer điều phối nội bộ các bước hoặc để mỗi transformer kiểm tra `className` và trạng thái bytes theo một hợp đồng rõ ràng.

### Không sửa mảng input tại chỗ

Mã sau là **ví dụ sai về contract**:

~~~java
classfileBuffer[100] = 42; // SAI: sửa trực tiếp input của JVM
return classfileBuffer;
~~~

Để chuyển sang mô hình hợp lệ, copy trước:

~~~java
byte[] modified = classfileBuffer.clone();
modified[100] = 42; // Chỉ minh họa phép ghi trên bản sao; index 100 chưa có ý nghĩa class file
return modified;
~~~

Hai đoạn là **mảnh code minh họa**, không phải phép biến đổi class file chạy độc lập. Trong thực tế, không chỉnh một byte theo offset tùy ý; phải tìm đúng cấu trúc class file và tạo output hợp lệ. Quy tắc cốt lõi là **đầu vào thuộc JVM và transformer phải coi là immutable**.

## 6. Retransformation: khi một số transformer không được gọi lại

Đây là điểm dễ gây nhầm nhất nếu đã quen luồng load-time:

- Transformer đăng ký `canRetransform=false` được gọi khi class **load lần đầu** hoặc khi **redefine**, nhưng **không được gọi lại** mỗi lần `retransformClasses(...)`.
- Khi retransform, JVM **tái áp dụng nguyên trạng kết quả của lần biến đổi trước** của những transformer không có retransformation capability.
- Transformer đăng ký `canRetransform=true` được **gọi lại** trong quá trình retransformation và nhận bytes sau các bước tái áp dụng nói trên.

Ví dụ có `A` không có capability và `B` có capability; khi định nghĩa class ban đầu, chuỗi tạo kết quả:

~~~text
Lần load đầu:
B0 --A(false)--> B1 --B(true)--> B2 [định nghĩa class]

Lần retransform tiếp theo:
B0' --áp lại kết quả A đã có--> B1' --gọi lại B(true)--> B2'
       A.transform KHÔNG chạy       B.transform CÓ chạy
~~~

`B0'` là bytes gốc phù hợp cho retransformation từ lần định nghĩa hoặc redefine gần nhất. Chúng **có thể khác biểu diễn nhị phân** so với `B0` ở những chi tiết như cấu trúc constant pool, dù logic tương đương; không thiết kế transformer dựa vào offset byte cố định. Dấu nháy trong `B0'`/`B1'` không hàm ý một lần nạp lại class từ file vật lý.

Ví dụ đăng ký nhóm trộn:

~~~java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("Retransformation unsupported");
}
inst.addTransformer(transformerA, false);
inst.addTransformer(transformerB, true);
~~~

Đoạn trên là **mảnh code cần `Instrumentation inst` và hai transformer đã tạo**, chỉ minh họa capability; không phải chương trình độc lập. Manifest của agent phải có `Can-Retransform-Classes: true` và JVM phải hỗ trợ. Nếu chỉ cần load-time như ví dụ ở mục 4 thì không khai báo và không dùng capability này.

### Vì sao B không nhất thiết tích lũy kết quả B của lần trước?

Mỗi lần retransform bắt đầu lại từ bytes gốc phù hợp, sau đó áp các biến đổi không hỗ trợ retransform theo quy tắc API và gọi các transformer có capability. Nó không mặc định lấy **B2 cuối cùng của lần retransform trước** làm đầu vào của B tiếp theo. Điều này giúp phân biệt biến đổi hợp lệ, lặp lại ổn định với việc vô tình chèn cùng đoạn mã theo từng lần retransform.

Với transformer được phép retransform, nên thiết kế biến đổi **đúng khi chạy nhiều lần**, chú ý cả class đã qua redefine. Nếu cần đánh dấu đã biến đổi, không giả định lần sau sẽ nhận đúng mảng byte đã trả về lần trước.

## 7. Nguồn bytes ban đầu khác nhau theo hoạt động của JVM

Mỗi loại sự kiện có một điểm xuất phát được định nghĩa riêng:

| Hoạt động | Bytes ban đầu đưa vào chuỗi |
| --- | --- |
| Định nghĩa class mới | Bytes mà `ClassLoader.defineClass` hoặc cơ chế tương đương nhận |
| Redefinition | Bytes trong `ClassDefinition.getDefinitionClassFile()` do lời gọi `redefineClasses(...)` cung cấp |
| Retransformation | Bytes từ định nghĩa đầu hoặc redefine gần nhất, kết hợp việc tái áp dụng các biến đổi không hỗ trợ retransformation |

Các transformer được gọi **trước khi** JVM xác minh/áp dụng class bytes cuối. Nếu `T1` tạo một class file hợp lệ nhưng `T2` sinh bytes lỗi, JVM có thể từ chối định nghĩa sau cả chuỗi. Vì thế việc log `T1 success` chưa chứng minh toàn bộ class cuối hợp lệ.

Khi retransform/redefine class đã load, thay đổi bytecode phải tuân thủ những giới hạn về cấu trúc class (chẳng hạn, thường không được thêm/xóa field hoặc method). Một transformer từng thay đổi class lúc load phải bảo đảm rằng output của nó ở lần retransform/redefine về sau vẫn là một phiên bản thay đổi hợp lệ theo quy tắc JVM.

## 8. Thực hành thiết kế nhiều transformer có phụ thuộc lẫn nhau

Trong một agent phức tạp, bạn có thể cần:

1. `T1` bổ sung điểm đánh dấu/metadata phù hợp vào method.
2. `T2` sử dụng đánh dấu này để thêm logic đo thời gian.
3. `T3` kiểm tra hoặc chuẩn hóa kết quả cho class file cuối.

Đây chỉ là ví dụ về **ý tưởng tổ chức trách nhiệm**. Không có bảo đảm rằng những transformer của thư viện bên thứ ba đều tạo ra hoặc nhận dạng đúng marker của nhau. Khi có sự phụ thuộc như vậy, cần kiểm tra định dạng output giữa các bước, xác định thứ tự nhóm, và có test chạy trên JDK dự kiến.

Các nguyên tắc thiết kế:

- **Sắp xếp theo capability có chủ đích.** Cùng nhóm mới được điều khiển thứ tự trực tiếp bằng thứ tự đăng ký; khác nhóm cần xét thứ tự do API quy định.
- **Định nghĩa hợp đồng input/output rõ ràng.** Ví dụ `T2` chỉ hoạt động khi thấy pattern đã do `T1` tạo; nếu không có, trả `null` hoặc thông báo lỗi chẩn đoán.
- **Không giả định độc quyền class file.** Agent khác có thể đăng ký transformer, kể cả transformer native. Bytecode đầu vào của bạn có thể đã khác so với class file trên đĩa.
- **Coi `classfileBuffer` là chỉ đọc.** Parse bytes và trả một mảng riêng khi biến đổi.
- **Chỉ xử lý class cần thiết.** Lọc bằng `className`, `loader` hoặc module thích hợp để tránh can thiệp cả bootstrap/runtime.
- **Tránh trạng thái toàn cục không đồng bộ.** Nhiều thread có thể load nhiều class cùng lúc; transformer có thể bị gọi đồng thời trên các class khác nhau.
- **Thiết kế transformer có thể chạy lặp.** Khi class được redefine hoặc retransform, không cộng dồn vô hạn lệnh/đánh dấu từ assumptions sai về input.
- **Kiểm tra bytes cuối.** Sử dụng công cụ đọc class file và chạy class thực; chỉ so sánh log của transformer là chưa đủ.

### Có thể điều khiển lại thứ tự sau khi đăng ký?

`Instrumentation` cung cấp `removeTransformer(transformer)`. Việc remove ảnh hưởng các lần định nghĩa class **trong tương lai**, nhưng API cảnh báo rằng một transformer vẫn có thể nhận callback sau khi bị remove vì class loading đồng thời. Đăng ký lại có thể ảnh hưởng vị trí thứ tự trong nhóm, song không nên xem đó là cơ chế điều phối an toàn trong lúc JVM đang hoạt động.

Nếu chuỗi nhiều bước cần thứ tự bất biến, thường dễ kiểm soát hơn khi **một transformer điều phối từng bước nội bộ**. Khi đó các bước có thể được gọi tuần tự bằng API do bạn sở hữu, đồng thời vẫn phải tuân thủ hợp đồng không sửa `classfileBuffer` tại chỗ.

## 9. Chẩn đoán khi kết quả không như mong đợi

| Hiện tượng | Kiểm tra nguyên nhân |
| --- | --- |
| Chỉ thấy log `T1`, không thấy `T2` | T2 có được đăng ký trước khi class load? Có bị lọc bởi `className`? Có thuộc sự kiện retransform mà nó không hỗ trợ? |
| `T2` thấy bytes chưa có sửa đổi của T1 | T1 có trả bytes mới hay `null`? Có lỗi/exception? T1/T2 nằm ở hai nhóm capability với thứ tự ngược mong đợi? |
| Ứng dụng vẫn trả `SEED` | Class đã được load trước khi đăng ký? Transformer không trúng internal name? Output không được JVM áp dụng? |
| Ứng dụng trả `NEXT` thay vì `DONE` | Bước T2 không thành công hoặc không được gọi, hãy kiểm tra marker trong input T2 |
| `ClassFormatError` / `VerifyError` | Một trong các transformer sinh bytes sai cấu trúc; kiểm tra class file **sau mỗi bước**, frames và stack |
| Cùng một phép biến đổi xuất hiện nhiều lần | Có thể đăng ký lặp instance hoặc transformer không an toàn khi redefine/retransform |
| Có log transformer nhưng retransform thất bại | Class không modifiable, capability thiếu hoặc bytes vi phạm quy tắc redefine/retransform |
| Sau `removeTransformer` vẫn thấy callback | Có thể có class load đang diễn ra đồng thời; API đã cảnh báo tình huống này |
| Chạy đúng với một JDK nhưng lỗi ở JDK khác | Kiểm tra class-file version, JVMTI capability, thư viện xử lý bytecode và hợp đồng transformer |

Để debug có hệ thống, nên ghi (ở mức log thích hợp) **internal class name**, class loader/module, tên transformer, thứ tự callback, sự kiện định nghĩa/redefine/retransform, kích thước và checksum của byte array **trước/sau**; không log toàn bộ bytecode vào production. Hash/digest cho biết bytes khác nhau, nhưng **không chứng minh** biến đổi có đúng ý nghĩa hay class cuối hợp lệ.

## 10. Bài tập tự kiểm tra

**Bài 1.** `T1` trả `B1`, `T2` trả `null`, `T3` trả `B3`. Input của `T3` là gì?

**Bài 2.** Bạn đăng ký `T2` có `canRetransform=true` trước, sau đó đăng ký `T1` có `canRetransform=false`. Trong một lần định nghĩa class mới, JVM gọi transformer Java nào trước?

**Bài 3.** `T1` chuyển marker `SEED` thành `NEXT`; `T2` phụ thuộc marker `NEXT`. Nếu đảo thứ tự T2 rồi T1 trong cùng nhóm, giá trị mà class trả về theo mô hình demo sẽ là gì?

**Bài 4.** Một transformer không có khả năng retransform đã đổi `SEED` thành `NEXT` ở lần load. Khi `retransformClasses(...)` diễn ra, `transform(...)` của nó có được gọi lại không? Kết quả cũ được xử lý thế nào?

**Bài 5.** Vì sao cách làm sau không đúng: `classfileBuffer[10] = 0; return classfileBuffer;`?

**Bài 6.** `T1` ném `IllegalClassFormatException`. Có chắc JVM dừng hoàn toàn và không gọi `T2` không?

**Bài 7.** Kết quả `T1` và `T2` đều được log là “changed”, nhưng JVM ném `VerifyError`. Log có chứng minh hai phép biến đổi hợp lệ không?

### Đáp án

1. `B1`, vì `null` của T2 giữ nguyên **bytes hiện hành**, không khôi phục `B0`.
2. `T1` (nhóm không retransform) trước `T2` (nhóm có retransform), dù T2 đăng ký sớm hơn.
3. Thường là `NEXT`: T2 không tìm thấy `NEXT` trong bytes chưa qua T1 nên không thay, rồi T1 mới đổi `SEED → NEXT`.
4. **Không gọi lại**; JVM **tái áp dụng kết quả biến đổi đã lưu** theo contract, sau đó gọi các transformer có retransform capability.
5. Vi phạm hợp đồng **không chỉnh sửa mảng đầu vào**, đồng thời việc sửa offset tùy tiện có thể làm class file hỏng.
6. **Không**; ngoại lệ của transformer tương đương trả `null` về tác dụng chuỗi; các transformer tiếp theo vẫn được gọi.
7. **Không**; log chỉ chứng minh callback chạy. JVM còn phải xác minh và chấp nhận class bytes cuối cùng.

## 11. Tài liệu tham khảo chính thức

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): định nghĩa chuỗi `classfileBuffer`, bốn nhóm thứ tự, cách xử lý `null` và ngoại lệ.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `retransformClasses`, capability và semantics tái áp dụng transformer.
- [Java SE 21 — Java Instrumentation package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cách tạo Java agent, `premain` và manifest.
- [Java SE 21 — Java Virtual Machine Specification, Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): constant pool, class-file validation và cấu trúc class file.
