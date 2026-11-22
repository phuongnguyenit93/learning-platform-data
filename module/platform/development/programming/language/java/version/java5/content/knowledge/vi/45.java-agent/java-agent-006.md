# Giá trị trả về của transformer và thứ tự xử lý

## 1. Mô hình: nhiều bước cùng xử lý dữ liệu của một lớp

Một Java agent có thể đăng ký nhiều `ClassFileTransformer`. Khi JVM xử lý một lớp thuộc phạm vi cần can thiệp, dữ liệu class file đi qua một chuỗi transformer trước khi JVM sử dụng kết quả để định nghĩa lớp.

Mỗi transformer cần trả lời hai câu hỏi:

1. Có thay đổi dữ liệu đầu vào hay không?
2. Nếu thay đổi, dữ liệu class file mới là gì?

Đây là hợp đồng về **dữ liệu lớp**, không phải giá trị trả về của phương thức nghiệp vụ. Nếu một transformer trả `null`, điều đó không làm phương thức của ứng dụng trả `null`.

Ký hiệu sau sẽ được dùng để theo dõi:

```text
B0: dữ liệu lớp ban đầu
T1, T2, T3: các transformer theo thứ tự được áp dụng
B1, B2, B3: kết quả sau từng bước
```

Một chuỗi có thể diễn ra như sau:

```text
B0 ── T1 trả B1 ──> B1 ── T2 trả null ──> B1 ── T3 trả B3 ──> B3
```

T2 không thay đổi dữ liệu nên T3 nhận B1, không phải B0 và cũng không phải một mảng `null`.

Cơ chế transformer có từ Java 5 và vẫn áp dụng trên JDK hiện đại. Những phần liên quan `canRetransform` và `retransformClasses` trong bài là khả năng được bổ sung từ Java 6. Thí nghiệm dùng JDK 17+ và khởi động agent bằng `-javaagent`.

## 2. Ba trường hợp đầu ra cần phân biệt

### 2.1. Trả null: không biến đổi tại bước này

Dạng thường gặp là bỏ qua lớp không thuộc phạm vi:

```java
if (!"demo/Target".equals(className)) {
    return null;
}
```

Đây là đoạn minh họa bên trong callback `transform`, chưa phải chương trình độc lập.

Trả `null` có nghĩa transformer này không cung cấp dữ liệu thay thế. Dữ liệu đã đi tới nó được giữ cho bước tiếp theo.

Không được diễn giải `null` thành:

- Hủy nạp lớp.
- Kết thúc toàn bộ chuỗi transformer.
- Xóa dữ liệu lớp.
- Khôi phục dữ liệu trước mọi transformer.
- Bỏ qua bước kiểm tra của JVM.

Ví dụ, nếu công cụ đo độ bao phủ đã thêm mã trước đó, một agent ghi log trả `null` không tự gỡ phần mã đo độ bao phủ.

### 2.2. Trả byte[] mới: thay dữ liệu cho bước tiếp theo

Khi có thay đổi, transformer phải tạo một mảng mới chứa dữ liệu class file hoàn chỉnh, hợp lệ về cấu trúc và phù hợp với ngữ cảnh xử lý.

Nguyên tắc là:

```java
byte[] output = input.clone();
// Chỉ sửa output theo quy tắc của định dạng class file.
return output;
```

Đoạn trên chỉ minh họa quyền sở hữu mảng, không tự tạo ra một phép biến đổi hữu ích.

**Không sửa trực tiếp mảng đầu vào** `classfileBuffer`. Transformer khác cần một đầu vào có ý nghĩa theo hợp đồng; việc sửa mảng tại chỗ có thể phá chuỗi và không được “hoàn tác” chỉ bằng cách sau đó trả `null` hoặc ném ngoại lệ.

Mảng trả về là toàn bộ class file, không phải mã nguồn Java, không phải chỉ bytecode của một phương thức và không phải một đoạn dữ liệu sẽ tự được nối thêm vào lớp.

Nếu không có thay đổi, trả `null` là cách biểu đạt đúng. Tạo bản sao giống hệt đầu vào rồi trả lại thường chỉ làm tăng cấp phát và khó đọc ý định.

### 2.3. Ném ngoại lệ: không phải lệnh từ chối nạp lớp

Nếu callback ném ngoại lệ ra ngoài, các transformer tiếp theo vẫn được gọi và quá trình nạp/định nghĩa lại/biến đổi lại vẫn được thử tiếp. Về việc cung cấp dữ liệu thay thế, ngoại lệ có hiệu ứng như trả `null`.

Điều đó không bảo đảm lớp chắc chắn nạp thành công: đầu vào trước đó có thể đã hỏng, hoặc một bước sau có thể tạo dữ liệu không hợp lệ.

`IllegalClassFormatException` dùng để báo vấn đề về định dạng đầu vào cho transformer. Nó giúp chẩn đoán, không tạo một cơ chế chặn lớp chắc chắn. Một lỗi bất ngờ của chính agent cũng không nên bị che giấu bằng suy luận “JVM vẫn chạy nên biến đổi đã thành công”.

Cần phân biệt:

| Tình huống | Tác động lên chuỗi | Điều không được suy ra |
| --- | --- | --- |
| Trả `null` | Không cung cấp dữ liệu mới ở bước này | Không có transformer nào khác đã biến đổi |
| Trả mảng mới | Dữ liệu mới đi tới bước sau | JVM đã chấp nhận định nghĩa lớp |
| Callback ném ngoại lệ | Bước sau vẫn được gọi; tiếp tục thử xử lý lớp | Lớp chắc chắn bị chặn hoặc chắc chắn nạp được |
| Kết quả cuối sai định dạng/không hợp lệ | JVM có thể từ chối khi kiểm tra/định nghĩa/liên kết | Ngoại lệ của callback là nguyên nhân duy nhất |

Không cố tình tạo mảng hỏng để thực hiện kiểm soát truy cập. Transformer là điểm mở rộng để xử lý mã, không phải một cơ chế chính sách từ chối lớp đáng tin cậy.

## 3. Thứ tự không chỉ là thứ tự đăng ký

JVM chia transformer thành các nhóm. Thứ tự áp dụng là:

| Thứ tự nhóm | Nhóm |
| --- | --- |
| 1 | Transformer Java không có khả năng biến đổi lại |
| 2 | Transformer native không có khả năng biến đổi lại |
| 3 | Transformer Java có khả năng biến đổi lại |
| 4 | Transformer native có khả năng biến đổi lại |

Trong **mỗi nhóm**, thứ tự đăng ký quyết định thứ tự gọi.

Transformer native trong bảng thuộc cơ chế sự kiện `ClassFileLoadHook` của JVM TI, không phải một đối tượng Java được tạo bằng cách triển khai `ClassFileTransformer`. Bảng nêu đủ hợp đồng; ví dụ thực hành chỉ sử dụng các transformer Java.

Với Java:

```java
inst.addTransformer(transformer);
```

tương đương về khả năng đăng ký với:

```java
inst.addTransformer(transformer, false);
```

Nếu đăng ký với `true`, transformer thuộc nhóm có khả năng biến đổi lại. Điều này không có nghĩa nó chỉ chạy khi biến đổi lại: nó cũng tham gia lúc nạp lớp ban đầu và lúc định nghĩa lại.

Ví dụ:

```text
Thứ tự đăng ký:
    R1(true), N1(false), N2(false), R2(true)

Thứ tự khi nạp lần đầu, không có transformer native:
    N1 → N2 → R1 → R2
```

R1 được đăng ký đầu tiên nhưng phải đứng sau N1/N2 vì khác nhóm. N1 đứng trước N2 vì cả hai cùng nhóm và N1 được đăng ký trước.

Nếu có nhiều tùy chọn `-javaagent`, các `premain` được khởi động theo thứ tự agent trên dòng lệnh. Tuy nhiên, thứ tự transformer sau đó vẫn theo nhóm như trên. “Agent A khởi động trước agent B” không đủ để kết luận mọi transformer của A đều chạy trước mọi transformer của B.

## 4. Đầu vào ở từng loại sự kiện

### Nạp lớp lần đầu

Đầu vào gốc bắt đầu từ dữ liệu mà bộ nạp lớp đưa vào việc định nghĩa lớp. Mỗi đầu ra tiếp tục đi qua chuỗi; JVM không tự trộn các thay đổi độc lập từ nhiều phiên bản nguồn.

Nếu một transformer bỏ qua đầu vào hiện tại và trả một bản class file riêng cũ hơn, nó có thể vô tình loại bỏ mã mà công cụ trước đã thêm. Đây là lỗi phối hợp: “cùng xử lý một lớp” không đồng nghĩa “các thay đổi tự hợp nhất”.

### Định nghĩa lại: redefineClasses

Đầu vào gốc đến từ dữ liệu định nghĩa thay thế do lời gọi `redefineClasses` cung cấp. Các transformer tham gia theo nhóm và thứ tự tương ứng. Lớp đã nạp vẫn phải tuân thủ các giới hạn của việc định nghĩa lại; không được tùy ý đổi cấu trúc như khi nạp lần đầu.

### Biến đổi lại: retransformClasses

Trường hợp này khác một cách quan trọng:

- JVM bắt đầu từ dữ liệu lớp ban đầu theo hợp đồng của API, không đơn giản lấy kết quả cuối đang chạy rồi áp mọi transformer lên thêm một lần.
- Các transformer đăng ký với `canRetransform=false` **không được gọi lại**. Kết quả của chúng từ lần nạp/định nghĩa lại trước được tái sử dụng tự động.
- Các transformer đăng ký với `canRetransform=true` được gọi lại, theo thứ tự nhóm phù hợp.

Dữ liệu gốc mà API tái dựng có thể không giống từng byte với tệp trên đĩa, chẳng hạn bố cục bảng hằng có thể khác. Không dùng phép so sánh toàn bộ byte với tệp gốc làm điều kiện bắt buộc cho mọi lần biến đổi lại.

Với chuỗi N1/N2/R1/R2 ở trên:

```text
Nạp lần đầu:
    B0 → N1 → N2 → R1 → R2 → kết quả

Biến đổi lại:
    dữ liệu gốc + kết quả N1/N2 được tái sử dụng
                           ↓
                           R1 → R2 → kết quả mới
```

Muốn sử dụng khả năng biến đổi lại, agent cần khai báo `Can-Retransform-Classes: true`, JVM phải hỗ trợ và lớp đích phải sửa được. Truyền `true` khi JVM không hỗ trợ có thể làm `addTransformer` ném `UnsupportedOperationException`. Chỉ thêm thuộc tính manifest không tự yêu cầu biến đổi lại bất kỳ lớp nào.

## 5. Thí nghiệm chạy được: nhìn thấy đầu vào của từng bước

Thí nghiệm dưới đây không dùng thư viện ngoài. Lớp đích trả về chuỗi ASCII cố định `STEP_000`. Mỗi transformer tìm dấu đánh dấu đó trong dữ liệu lớp, sao chép mảng và thay chữ số cuối bằng chữ số riêng.

**Giới hạn có chủ đích:** hàm tìm dấu chỉ dùng cho đúng lớp thí nghiệm có duy nhất một dấu ASCII tám byte. Nó không phải bộ phân tích class file tổng quát. Không áp dụng cách tìm/thay byte tùy tiện cho lớp bất kỳ hoặc chuỗi Unicode. Một công cụ xử lý bytecode thực tế cần hiểu cấu trúc class file.

Mọi thay đổi trong ví dụ giữ nguyên độ dài, tên lớp và chữ ký phương thức, nên tập trung quan sát được chuỗi dữ liệu mà không cần thêm mã nghiệp vụ phức tạp.

### 5.1. Tệp src/demo/OrderAgent.java

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class OrderAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation is not supported");
        }
        instrumentation = inst;
        String mode = args == null ? "normal" : args;
        inst.addTransformer(new Step("R1", '3', mode), true);
        inst.addTransformer(new Step("N1", '1', mode), false);
        inst.addTransformer(new Step("N2", '2', mode), false);
        inst.addTransformer(new Step("R2", '4', mode), true);
        System.out.println("[agent] registered R1,N1,N2,R2");
    }

    public static void repeat(Class<?> type) throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null || !inst.isModifiableClass(type)) {
            throw new IllegalStateException("Agent missing or class unmodifiable");
        }
        inst.retransformClasses(type);
    }

    private static final class Step implements ClassFileTransformer {
        private static final byte[] PREFIX =
                "STEP_00".getBytes(StandardCharsets.US_ASCII);
        private final String name;
        private final char digit;
        private final String mode;

        private Step(String name, char digit, String mode) {
            this.name = name;
            this.digit = digit;
            this.mode = mode;
        }

        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> classBeingRedefined, ProtectionDomain domain,
                byte[] input) throws IllegalClassFormatException {
            if (!"demo/Target".equals(className)) {
                return null;
            }
            int position = markerPosition(input);
            String before = new String(input, position, 8,
                    StandardCharsets.US_ASCII);
            if ("N2".equals(name) && "skip".equals(mode)) {
                System.out.println("[" + name + "] input=" + before
                        + " return=null");
                return null;
            }
            if ("N2".equals(name) && "fail".equals(mode)) {
                System.out.println("[" + name + "] input=" + before
                        + " throw=IllegalClassFormatException");
                throw new IllegalClassFormatException("Demonstration failure");
            }
            byte[] output = input.clone();
            output[position + 7] = (byte) digit;
            String after = new String(output, position, 8,
                    StandardCharsets.US_ASCII);
            System.out.println("[" + name + "] input=" + before
                    + " return=" + after);
            return output;
        }

        private static int markerPosition(byte[] bytes)
                throws IllegalClassFormatException {
            int found = -1;
            for (int i = 0; i <= bytes.length - 8; i++) {
                boolean match = true;
                for (int j = 0; j < PREFIX.length; j++) {
                    if (bytes[i + j] != PREFIX[j]) {
                        match = false;
                        break;
                    }
                }
                if (match && bytes[i + 7] >= '0' && bytes[i + 7] <= '9') {
                    if (found != -1) {
                        throw new IllegalClassFormatException("Multiple markers");
                    }
                    found = i;
                }
            }
            if (found == -1) {
                throw new IllegalClassFormatException("Marker not found");
            }
            return found;
        }
    }
}
```

Trong chế độ `normal`, mỗi bước trả một mảng mới. Chế độ `skip` làm N2 trả `null`; chế độ `fail` chủ động ném ngoại lệ ở N2 để kiểm chứng hành vi tiếp tục chuỗi. Ngoại lệ trong nhánh `fail` là lỗi được tạo cho thí nghiệm, không phải kết luận đầu vào đang hỏng.

Bộ lọc tên lớp dùng `demo/Target` vì callback nhận tên dạng nội bộ. Mã chỉ đọc `input`; mọi thay đổi nằm trong `output`.

### 5.2. Tệp src/demo/Target.java

```java
package demo;

public final class Target {
    public static String value() {
        return "STEP_000";
    }
}
```

### 5.3. Tệp src/demo/App.java

```java
package demo;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] main");
        Class<?> target = Class.forName("demo.Target");
        System.out.println("[app] value="
                + target.getMethod("value").invoke(null));
        if (args.length > 0 && "repeat".equals(args[0])) {
            System.out.println("[app] request retransform");
            OrderAgent.repeat(target);
            System.out.println("[app] value="
                    + target.getMethod("value").invoke(null));
        }
    }
}
```

`Class.forName` giúp xác định rõ thời điểm yêu cầu nạp lớp sau dòng `[app] main`. Lời gọi `OrderAgent.repeat` là một điểm nối dành riêng cho bài thực hành để yêu cầu biến đổi lại; ứng dụng thực tế không bắt buộc phải gọi agent như vậy.

### 5.4. Tệp MANIFEST.MF

```text
Manifest-Version: 1.0
Premain-Class: demo.OrderAgent
Can-Retransform-Classes: true

```

Lưu manifest dạng văn bản, có ký tự xuống dòng kết thúc và dòng trống cuối tệp.

Cấu trúc thư mục nguồn:

```text
src/demo/OrderAgent.java
src/demo/Target.java
src/demo/App.java
MANIFEST.MF
```

### 5.5. Biên dịch và đóng gói

Dùng JDK có `javac`, `java`, `jar` trên `PATH`. Từ thư mục chứa `src` và manifest, chạy trong PowerShell:

```powershell
javac --release 17 -d agent-classes src/demo/OrderAgent.java
javac --release 17 -cp agent-classes -d app-classes src/demo/App.java src/demo/Target.java
jar --create --file order-agent.jar --manifest MANIFEST.MF -C agent-classes .
```

Chỉ tiếp tục nếu từng lệnh thành công. Ứng dụng cần `agent-classes` lúc biên dịch vì tham chiếu `OrderAgent.repeat`; khi chạy, JVM nạp lớp agent từ agent JAR. Không đóng gói `Target.class` vào agent JAR.

Ví dụ được biên dịch với `--release 17` và kiểm tra trên JDK 24.0.2 có hỗ trợ biến đổi lại. Các khối dưới đây là stdout của cấu hình một agent trong bài.

## 6. Kết quả và cách đọc

### 6.1. Chế độ normal: mảng mới được truyền tiếp

```powershell
java "-javaagent:order-agent.jar" -cp app-classes demo.App repeat
```

Stdout:

```text
[agent] registered R1,N1,N2,R2
[app] main
[N1] input=STEP_000 return=STEP_001
[N2] input=STEP_001 return=STEP_002
[R1] input=STEP_002 return=STEP_003
[R2] input=STEP_003 return=STEP_004
[app] value=STEP_004
[app] request retransform
[R1] input=STEP_002 return=STEP_003
[R2] input=STEP_003 return=STEP_004
[app] value=STEP_004
```

Bốn chi tiết cần đọc từ kết quả:

1. Thứ tự đăng ký và thứ tự callback khác nhau: N1/N2 thuộc nhóm không có khả năng biến đổi lại nên chạy trước R1/R2.
2. N2 nhận `STEP_001`, tức dữ liệu N1 đã tạo, thay vì nhận lại `STEP_000`.
3. Khi yêu cầu biến đổi lại, không xuất hiện callback N1 hoặc N2.
4. R1 nhận `STEP_002` ở lần biến đổi lại, không phải `STEP_004` của kết quả cuối lần trước.

Giá trị ứng dụng nhận là `STEP_004` vì transformer cuối cùng đã tạo dữ liệu đó. Mục đích của chuỗi đánh dấu là biểu diễn luồng dữ liệu; nó không phải một phép đo hiệu năng.

### 6.2. Chế độ skip: null không xóa thay đổi trước đó

```powershell
java "-javaagent:order-agent.jar=skip" -cp app-classes demo.App
```

Stdout:

```text
[agent] registered R1,N1,N2,R2
[app] main
[N1] input=STEP_000 return=STEP_001
[N2] input=STEP_001 return=null
[R1] input=STEP_001 return=STEP_003
[R2] input=STEP_003 return=STEP_004
[app] value=STEP_004
```

N2 không tạo đầu ra mới. R1 tiếp tục nhận `STEP_001` từ N1. Nếu `null` có nghĩa khôi phục dữ liệu gốc, R1 đã nhận `STEP_000`; kết quả chạy cho thấy điều đó không xảy ra.

Không chỉ nhìn dòng cuối `STEP_004` để đánh giá N2 có chạy hay không: R2 luôn đặt chữ số thành 4. Phải quan sát đầu vào/đầu ra của từng bước.

### 6.3. Chế độ fail: ngoại lệ không dừng chuỗi

```powershell
java "-javaagent:order-agent.jar=fail" -cp app-classes demo.App
```

Stdout:

```text
[agent] registered R1,N1,N2,R2
[app] main
[N1] input=STEP_000 return=STEP_001
[N2] input=STEP_001 throw=IllegalClassFormatException
[R1] input=STEP_001 return=STEP_003
[R2] input=STEP_003 return=STEP_004
[app] value=STEP_004
```

R1 và R2 vẫn chạy sau lỗi của N2. Đầu vào chưa bị N2 sửa tại chỗ nên R1 vẫn nhận `STEP_001`. Ví dụ chứng minh không được dùng `throw new IllegalClassFormatException(...)` như một lệnh chắc chắn chặn lớp.

Nếu cần chẩn đoán lỗi của transformer, hãy ghi nhận thông tin lỗi một cách có kiểm soát; không suy luận rằng ngoại lệ luôn tự xuất hiện với một stack trace hữu ích trên console.

## 7. Vì sao thứ tự có thể làm thay đổi kết quả thực tế?

Trong thí nghiệm, mỗi bước đặt lại chữ số cuối, nên bước chạy sau quyết định chữ số cuối cùng. Với công cụ thực tế, một bước có thể thêm mã theo dõi vào phương thức, còn bước tiếp theo nhận diện/chỉnh sửa chính phương thức đó.

Giả sử hai phép biến đổi có ký hiệu A và B:

```text
B(A(dữ liệu)) không nhất thiết bằng A(B(dữ liệu))
```

Ví dụ, nếu A bọc phương thức bằng logic đo thời gian rồi B lại thay toàn bộ thân phương thức bằng một phiên bản khác, phần đo của A có thể bị loại bỏ. Đổi thứ tự có thể khiến phần đo nằm bao quanh phiên bản thân do B tạo. Không có quy tắc chung rằng “agent cuối luôn thắng tất cả”; điều đó phụ thuộc mỗi transformer thực sự giữ, thêm hay thay phần nào của đầu vào.

Khi phân tích xung đột nhiều agent:

- Xác định lớp/bộ nạp/module mà từng công cụ chọn.
- Xác định nhóm `canRetransform` và thời điểm đăng ký thực tế.
- Kiểm tra từng bước xử lý đầu vào hiện tại hay bỏ qua nó để dùng bản riêng.
- Kiểm tra kết quả ở cả lúc nạp lần đầu và lúc biến đổi lại.
- Xác minh class file cuối và hành vi chương trình, thay vì chỉ kiểm tra callback có được gọi.

Việc nạp lớp có thể diễn ra đồng thời. Thứ tự ở bài là thứ tự áp dụng cho một sự kiện xử lý dữ liệu lớp; không tạo một thứ tự thời gian toàn cục giữa mọi callback của tất cả các lớp và các luồng. Nếu ghi log nhiều lớp, các dòng log có thể xen kẽ.

## 8. Lỗi thường gặp cần tránh

### Nhầm null với byte[0]

`null` có ý nghĩa đặc biệt là không biến đổi. `new byte[0]` là một mảng thay thế rỗng; nó không phải class file hợp lệ. Chuỗi transformer diễn ra trước khi JVM áp dụng kết quả cuối, nên không giả định trả mảng hỏng sẽ lập tức dừng đúng tại callback đó.

### Sửa đầu vào rồi trả null

Điều này vi phạm hợp đồng không sửa `classfileBuffer`. `null` không hoàn tác tác dụng phụ. Luôn tạo mảng đầu ra riêng trước khi biến đổi.

### Cho rằng transformer đăng ký đầu luôn chạy đầu

Chỉ đúng khi xét trong cùng nhóm. Hãy lập bảng nhóm trước, rồi mới áp thứ tự đăng ký trong từng nhóm.

### Cho rằng canRetransform=false nghĩa là không biến đổi được

`false` không cấm transformer thay byte lúc nạp lần đầu hoặc định nghĩa lại. Nó quyết định khả năng được gọi lại trong quá trình `retransformClasses`.

### Cho rằng biến đổi lại luôn cộng thêm một lớp mã lên kết quả cuối

Đầu vào được JVM tái dựng theo hợp đồng, với kết quả của các bước không có khả năng biến đổi lại được tái sử dụng. Một thuật toán đếm số lần mình đã chạy rồi cố gỡ/chèn theo phỏng đoán rất dễ sai.

### Không kiểm tra tính hợp lệ của đầu ra

Chuỗi callback chạy xong không đồng nghĩa JVM đã chấp nhận lớp. Ngoài cấu trúc class file, phải xét chữ ký, ngăn xếp, thuộc tính kiểm tra, liên kết lớp và các giới hạn của định nghĩa lại/biến đổi lại.

### Sao chép cơ chế tìm dấu của thí nghiệm vào công cụ thật

Ví dụ chỉ thay một byte ASCII tại vị trí được kiểm tra trong một lớp do chính bài tạo. Nó không giải quyết bảng hằng tổng quát, chuỗi modified UTF-8, lệnh JVM hay stack map. Khi mục tiêu là chèn mã vào phương thức, cần một cách xử lý class file đúng cấu trúc.

## 9. Bài tập tự kiểm chứng

1. Đổi thứ tự đăng ký N1 và N2, giữ nguyên `false`. Dự đoán đầu vào R1 rồi chạy kiểm tra. Trong chế độ normal, N2 đặt 2 trước và N1 đặt 1 sau, nên R1 nhận `STEP_001`.
2. Đổi thứ tự đăng ký R1 và R2, vẫn giữ `true`. Dự đoán giá trị ứng dụng. R2 chạy trước rồi R1 đặt 3, nên kết quả là `STEP_003`.
3. Chạy chế độ `skip` với đối số ứng dụng `repeat`. Ở phần biến đổi lại, giải thích vì sao R1 nhận `STEP_001` và N2 không được gọi lại.
4. Thêm một transformer cuối cùng trả `null`. Dữ liệu cuối có trở về `STEP_000` không? Không; bước đó giữ nguyên kết quả đã đi tới nó.
5. Giải thích vì sao nhánh `fail` không chứng minh có thể dùng transformer để chắc chắn cấm nạp `demo.Target`.

Điểm cần nắm là: **mỗi transformer nhận dữ liệu đã đi qua các bước trước; `null` giữ dữ liệu hiện tại; mảng mới truyền một kết quả mới; thứ tự được quyết định theo nhóm rồi mới theo đăng ký trong nhóm.** Khi biến đổi lại, cần tính thêm quy tắc tái sử dụng kết quả của các transformer không có khả năng biến đổi lại.

## Tài liệu đối chiếu

- [ClassFileTransformer trên JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng giá trị trả về, ngoại lệ và thứ tự nhóm.
- [Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký, điều kiện hỗ trợ và quy trình biến đổi lại.
- [IllegalClassFormatException](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html): ý nghĩa lỗi định dạng đầu vào.
- [Đặc tả package java.lang.instrument](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest và khởi động agent.
