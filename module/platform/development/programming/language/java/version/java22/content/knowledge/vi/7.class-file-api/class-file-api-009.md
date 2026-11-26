# Chèn logging hoặc đo thời gian vào bytecode và giữ nguyên hành vi phương thức

Class-File API cho phép đọc, tạo và biến đổi Java class file bằng API chuẩn của JDK. Ta có thể dùng API này để chèn lời gọi logging hoặc đo thời gian vào thân phương thức mà không cần viết lại toàn bộ bytecode thủ công.

Một ví dụ thường gặp là đo thời gian chạy của phương thức @@BT@@calculate@@BT@@: ghi nhận thời điểm bắt đầu khi vào phương thức, tính thời gian đã trôi qua trước mỗi lệnh trả về và gửi kết quả đến một helper. Các lệnh gốc vẫn được giữ lại; giá trị trả về tiếp tục nằm trên operand stack và được trả về như trước.

Class-File API từng là preview trong Java 22 và Java 23, sau đó trở thành API ổn định trong Java 24 theo JEP 484. Khi áp dụng trên JDK hiện đại, hãy dùng package @@BT@@java.lang.classfile@@BT@@ đã hoàn thiện; không cần bật preview feature.

## 1. Các lớp chính trong Class-File API

Class-File API mô hình hóa class file thành các model và element:

| Thành phần | Vai trò |
|---|---|
| @@BT@@ClassFile@@BT@@ | Tạo ngữ cảnh để parse và transform class file |
| @@BT@@ClassModel@@BT@@ | Biểu diễn một class file đã được đọc |
| @@BT@@MethodModel@@BT@@ | Biểu diễn một phương thức, gồm metadata và code |
| @@BT@@CodeModel@@BT@@ | Biểu diễn phần bytecode trong thuộc tính Code |
| @@BT@@ClassTransform@@BT@@ | Chọn các thành phần của class cần biến đổi |
| @@BT@@CodeTransform@@BT@@ | Biến đổi từng @@BT@@CodeElement@@BT@@ trong thân phương thức |
| @@BT@@CodeBuilder@@BT@@ | Phát ra các instruction mới và chuyển tiếp instruction gốc |

Luồng làm việc thường có ba bước:

@@BT@@@@BT@@@@BT@@mermaid
flowchart TD
    A["Đọc byte[] của class file"] --> B["ClassFile.parse"]
    B --> C["ClassModel"]
    C --> D["ClassTransform chọn phương thức"]
    D --> E["CodeTransform chèn instruction"]
    E --> F["ClassFile.transformClass"]
    F --> G["byte[] class file mới"]
    G --> H["Verify và nạp class đã biến đổi"]
@@BT@@@@BT@@@@BT@@

@@BT@@ClassFile.transformClass(model, transform)@@BT@@ tạo ra byte array mới. Bản thân lời gọi này không thực thi class và cũng không tự thay thế class đang được JVM nạp. Việc ghi file, nạp bằng class loader hoặc tích hợp vào Java agent là bước triển khai riêng.

## 2. Ví dụ phương thức cần đo thời gian

Giả sử có class sau:

@@BT@@@@BT@@@@BT@@java
package com.example;

public class PriceCalculator {

    public int calculate(int quantity, int unitPrice) {
        if (quantity <= 0 || unitPrice <= 0) {
            return 0;
        }

        return quantity * unitPrice;
    }
}
@@BT@@@@BT@@@@BT@@

Khi biên dịch, phương thức @@BT@@calculate(int, int)@@BT@@ có hai nhánh trả về. Ta muốn đo thời gian từ lúc phương thức bắt đầu đến ngay trước mỗi lệnh @@BT@@ireturn@@BT@@.

Một helper nhận tên phương thức và thời gian tính bằng nanosecond:

@@BT@@@@BT@@@@BT@@java
package com.example;

public final class TimingLog {

    private TimingLog() {}

    public static void record(String methodName, long elapsedNanos) {
        // Gửi dữ liệu tới hệ thống logging hoặc metrics.
        // Helper này cần được thiết kế để không ném exception ra ngoài.
    }
}
@@BT@@@@BT@@@@BT@@

Trong môi trường thực tế, helper có thể ghi vào logger, metrics registry hoặc hàng đợi ghi log. Nên giữ helper ngắn và không ném exception ra ngoài để lỗi ghi log không làm thay đổi kết quả của phương thức đang được đo.

## 3. Tạo CodeTransform để chèn thời điểm bắt đầu và kết thúc

Ta cần lưu thời điểm bắt đầu vào một local variable mới. Khi gặp mỗi instruction trả về, transformer tính thời gian đã trôi qua và gọi @@BT@@TimingLog.record@@BT@@.

### Lưu thời điểm bắt đầu trong atStart

@@BT@@CodeTransform.atStart@@BT@@ được gọi trước khi các code element gốc được xử lý. Có thể dùng @@BT@@CodeBuilder.allocateLocal(TypeKind.LONG)@@BT@@ để xin một local slot mới, sau đó gọi @@BT@@System.nanoTime()@@BT@@ và lưu kết quả:

@@BT@@@@BT@@@@BT@@java
int startTimeSlot = builder.allocateLocal(TypeKind.LONG);

builder.invokestatic(
    SYSTEM,
    "nanoTime",
    MethodTypeDesc.of(CD_long)
);
builder.lstore(startTimeSlot);
@@BT@@@@BT@@@@BT@@

Khi đang transform một phương thức có sẵn, @@BT@@allocateLocal@@BT@@ cấp slot mới sau vùng local mà phương thức gốc đang sử dụng. Nhờ vậy, biến được thêm vào không ghi đè tham số hay local variable hiện có.

### Chèn lệnh ghi thời gian trước ReturnInstruction

@@BT@@ReturnInstruction@@BT@@ đại diện cho các lệnh trả về của phương thức, gồm trả về @@BT@@void@@BT@@, kiểu số nguyên, số thực, @@BT@@long@@BT@@, @@BT@@double@@BT@@ hoặc reference.

Tại vị trí này, giá trị trả về của phương thức đã nằm trên operand stack. Ta đẩy các đối số dành cho helper lên phía trên, gọi helper, rồi chuyển tiếp instruction trả về gốc:

@@BT@@@@BT@@@@BT@@java
if (element instanceof ReturnInstruction) {
    builder.loadConstant(methodName);

    builder.invokestatic(
        SYSTEM,
        "nanoTime",
        MethodTypeDesc.of(CD_long)
    );

    builder.lload(startTimeSlot);
    builder.lsub();

    builder.invokestatic(
        TIMING_LOG,
        "record",
        MethodTypeDesc.of(CD_void, CD_String, CD_long)
    );
}

builder.with(element);
@@BT@@@@BT@@@@BT@@

Thứ tự trên tạo ra lời gọi có dạng @@BT@@TimingLog.record(methodName, System.nanoTime() - startTime)@@BT@@.

@@BT@@builder.with(element)@@BT@@ chuyển tiếp instruction gốc. Nếu phần tử hiện tại là @@BT@@ireturn@@BT@@, nó vẫn được phát ra sau lời gọi helper.

Điểm quan trọng là giá trị trả về đã nằm bên dưới các đối số mới trên operand stack. Lệnh gọi helper tiêu thụ tên phương thức và thời gian, trả về @@BT@@void@@BT@@, nên giá trị gốc vẫn còn trên stack để instruction return sử dụng. Cách này áp dụng cho cả kiểu trả về nguyên thủy và reference.

## 4. CodeTransform hoàn chỉnh

Đoạn code sau tạo một transformer có state riêng cho mỗi lần biến đổi thân phương thức:

@@BT@@@@BT@@@@BT@@java
package com.example;

import java.lang.classfile.CodeBuilder;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.TypeKind;
import java.lang.classfile.instruction.ReturnInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;

import static java.lang.constant.ConstantDescs.CD_String;
import static java.lang.constant.ConstantDescs.CD_long;
import static java.lang.constant.ConstantDescs.CD_void;

public final class TimingTransforms {

    private static final ClassDesc SYSTEM =
        ClassDesc.of("java.lang.System");

    private static final ClassDesc TIMING_LOG =
        ClassDesc.of("com.example.TimingLog");

    private TimingTransforms() {}

    public static CodeTransform measureNormalReturns(String methodName) {
        return CodeTransform.ofStateful(() -> new CodeTransform() {

            private int startTimeSlot;

            @Override
            public void atStart(CodeBuilder builder) {
                startTimeSlot = builder.allocateLocal(TypeKind.LONG);

                builder.invokestatic(
                    SYSTEM,
                    "nanoTime",
                    MethodTypeDesc.of(CD_long)
                );

                builder.lstore(startTimeSlot);
            }

            @Override
            public void accept(CodeBuilder builder, CodeElement element) {
                if (element instanceof ReturnInstruction) {
                    builder.loadConstant(methodName);

                    builder.invokestatic(
                        SYSTEM,
                        "nanoTime",
                        MethodTypeDesc.of(CD_long)
                    );

                    builder.lload(startTimeSlot);
                    builder.lsub();

                    builder.invokestatic(
                        TIMING_LOG,
                        "record",
                        MethodTypeDesc.of(CD_void, CD_String, CD_long)
                    );
                }

                // Giữ nguyên code element gốc.
                builder.with(element);
            }
        });
    }
}
@@BT@@@@BT@@@@BT@@

Có hai chi tiết quan trọng:

- @@BT@@CodeTransform.ofStateful@@BT@@ nhận một supplier tạo transformer mới cho mỗi lần duyệt code. Biến @@BT@@startTimeSlot@@BT@@ vì thế thuộc riêng từng phương thức đang được biến đổi.
- @@BT@@atStart@@BT@@ chạy một lần trước các code element; @@BT@@accept@@BT@@ xử lý từng element và chuyển tiếp các element không cần thay đổi bằng @@BT@@builder.with(element)@@BT@@.

Trong ví dụ này, tên @@BT@@measureNormalReturns@@BT@@ nhấn mạnh rằng thời gian chỉ được ghi khi phương thức đi tới một instruction return bình thường. Nếu phương thức ném exception trước khi return, transformer không ghi thời gian kết thúc cho lần gọi đó.

## 5. Chọn phương thức và biến đổi class file

Ta dùng @@BT@@ClassTransform.transformingMethodBodies@@BT@@ để chỉ áp dụng CodeTransform cho phương thức cần đo.

Ví dụ dưới đây chỉ chọn @@BT@@calculate(int, int)@@BT@@. Descriptor @@BT@@(II)I@@BT@@ có nghĩa là nhận hai tham số @@BT@@int@@BT@@ và trả về @@BT@@int@@BT@@:

@@BT@@@@BT@@@@BT@@java
package com.example;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;

public final class InstrumentPriceCalculator {

    private InstrumentPriceCalculator() {}

    public static byte[] instrument(byte[] originalBytes) {
        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(originalBytes);

        ClassTransform transform =
            ClassTransform.transformingMethodBodies(
                method ->
                    method.methodName().stringValue().equals("calculate")
                    && method.methodType().stringValue().equals("(II)I"),
                TimingTransforms.measureNormalReturns("calculate")
            );

        return classFile.transformClass(model, transform);
    }
}
@@BT@@@@BT@@@@BT@@

Nếu class có nhiều overload cùng tên, hãy kiểm tra cả method descriptor để chỉ chọn đúng chữ ký. Có thể mở rộng predicate để bỏ qua constructor, static initializer, bridge method hoặc method được sinh tự động nếu không muốn đo các trường hợp đó.

@@BT@@transformingMethodBodies@@BT@@ chỉ biến đổi phần code của những method thỏa predicate. Các method khác và những thành phần class không nằm trong phạm vi transform được chuyển tiếp.

## 6. Ghi và kiểm tra class file mới

Sau khi nhận được byte array đã biến đổi, có thể ghi ra một thư mục output riêng:

@@BT@@@@BT@@@@BT@@java
import java.nio.file.Files;
import java.nio.file.Path;

Path inputClassPath = Path.of("build/classes/com/example/PriceCalculator.class");
Path outputClassPath = Path.of("build/instrumented/com/example/PriceCalculator.class");

byte[] original = Files.readAllBytes(inputClassPath);

byte[] instrumented =
    InstrumentPriceCalculator.instrument(original);

Files.createDirectories(outputClassPath.getParent());
Files.write(outputClassPath, instrumented);
@@BT@@@@BT@@@@BT@@

Không nên ghi đè class gốc trong lần thử đầu tiên. Hãy giữ bản gốc để so sánh và có thể quay lại nếu class sau biến đổi không chạy đúng.

JDK 24 cung cấp @@BT@@ClassFile.verify(byte[])@@BT@@ để kiểm tra class file và trả về danh sách lỗi xác minh:

@@BT@@@@BT@@@@BT@@java
import java.lang.classfile.ClassFile;
import java.util.List;

ClassFile classFile = ClassFile.of();

List<VerifyError> errors = classFile.verify(instrumented);

if (!errors.isEmpty()) {
    throw new IllegalStateException(
        "Invalid transformed class: " + errors
    );
}
@@BT@@@@BT@@@@BT@@

Sau bước xác minh, vẫn nên nạp class trong môi trường thử nghiệm và kiểm tra kết quả với nhiều nhánh thực thi. Việc xác minh cấu trúc class file không thay thế kiểm thử hành vi khi chạy ứng dụng.

## 7. Vì sao cách chèn này giữ được giá trị trả về?

Xét phương thức gốc:

@@BT@@@@BT@@@@BT@@java
public int calculate(int quantity, int unitPrice) {
    return quantity * unitPrice;
}
@@BT@@@@BT@@@@BT@@

Trước lệnh @@BT@@ireturn@@BT@@, bytecode gốc đã đặt giá trị kết quả lên operand stack. Transformer thêm các lệnh gọi helper nhưng không lấy hoặc thay đổi giá trị đó:

@@BT@@@@BT@@@@BT@@mermaid
flowchart TD
    A["Bytecode gốc tính kết quả"] --> B["Đẩy int kết quả lên operand stack"]
    B --> C["Đẩy tên method và elapsed time"]
    C --> D["Gọi TimingLog.record"]
    D --> E["Giá trị int gốc vẫn còn trên stack"]
    E --> F["ireturn gốc"]
@@BT@@@@BT@@@@BT@@

Điều này giữ nguyên:

- Các phép tính và nhánh điều kiện trong thân phương thức.
- Giá trị trả về khi đi qua đường return bình thường.
- Các instruction gốc, vì transformer luôn gọi @@BT@@builder.with(element)@@BT@@.
- Việc truyền exception gốc trên các đường không đi qua @@BT@@ReturnInstruction@@BT@@, vì mẫu transform này không bắt hoặc thay thế exception.

Tuy nhiên, instrumentation vẫn tạo thêm lời gọi phương thức và tiêu tốn thời gian. Để tránh làm thay đổi kết quả quan sát được, helper logging phải không ném exception ra ngoài. Nếu helper ném exception, exception đó có thể thay thế giá trị trả về ban đầu. Logging cũng có thể gây thêm cấp phát, I/O hoặc tranh chấp thread; cần thiết kế helper phù hợp với yêu cầu hiệu năng.

## 8. Đo thời gian khi phương thức ném exception

Mẫu @@BT@@measureNormalReturns@@BT@@ chỉ ghi thời gian cho các đường kết thúc bằng return bình thường. Nó không ghi thời gian nếu một lời gọi bên trong ném exception, nếu phương thức thực hiện @@BT@@athrow@@BT@@ hoặc nếu exception thoát ra từ một đoạn code khác.

Muốn đo cả trường hợp thành công và thất bại, cần bổ sung exception handler bao quanh phần thân phương thức:

1. Ghi thời điểm bắt đầu trước khi chạy code gốc.
2. Đặt nhãn bắt đầu và kết thúc cho vùng được bảo vệ.
3. Tại handler, lưu exception gốc vào local variable.
4. Ghi thời gian thất bại bằng helper không ném exception.
5. Ném lại chính exception gốc bằng @@BT@@athrow@@BT@@.

Đây là biến đổi phức tạp hơn vì phải phối hợp exception table hiện có, các @@BT@@try/finally@@BT@@ đã được compiler chuyển thành bytecode, nhãn nhảy và stack map. Cần kiểm tra kỹ thứ tự handler và bảo đảm exception gốc không bị thay thế. Với nhu cầu cơ bản, đo các đường return bình thường thường là điểm bắt đầu dễ kiểm chứng hơn.

## 9. Những giới hạn cần lưu ý

| Vấn đề | Ảnh hưởng và cách xử lý |
|---|---|
| Constructor | Không chèn lời gọi helper trước khi constructor hoàn tất khởi tạo @@BT@@this@@BT@@ nếu helper có thể quan sát trạng thái đối tượng chưa khởi tạo |
| Method overload | Lọc theo cả tên và descriptor để tránh biến đổi nhầm phương thức cùng tên |
| Abstract hoặc native method | Không có Code attribute thông thường để chèn instruction |
| Exception path | Mẫu trên chỉ ghi thời gian ở các đường return bình thường |
| Helper logging | Phải được class loader và module của class đích truy cập được; nên không ném exception |
| Local variable | Dùng @@BT@@allocateLocal@@BT@@ để tránh ghi đè slot gốc |
| Operand stack | Giữ giá trị trả về trên stack; helper phải có descriptor chính xác và trả về @@BT@@void@@BT@@ |
| Class version và attributes | Kiểm tra class file sau transform, đặc biệt khi xử lý class có cấu trúc hoặc attributes đặc biệt |
| Hiệu năng | Đo thêm lời gọi @@BT@@nanoTime@@BT@@, helper logging và chi phí biến đổi |
| Nạp class | ClassFile API tạo byte array mới; cần bước ghi file, class loader hoặc agent để sử dụng class đó |

Không nên biến đổi constructor, method đồng bộ hoặc method có vòng đời đặc biệt một cách máy móc. Ví dụ, chèn logging trước return của một synchronized method vẫn chạy khi monitor còn được giữ; helper chậm có thể kéo dài thời gian giữ khóa. Hãy cân nhắc vị trí chèn và tác động của helper đến luồng thực thi.

## 10. Khi nào nên dùng Class-File API?

Class-File API phù hợp khi cần:

- Chèn logging, tracing hoặc đo thời gian vào các method đã biên dịch.
- Tạo công cụ phân tích và biến đổi bytecode chạy trên nhiều phiên bản JDK hiện đại.
- Viết bộ xử lý class file mà không phụ thuộc vào các package nội bộ của JDK.
- Chỉ biến đổi một nhóm method bằng predicate, giữ nguyên các thành phần khác của class.
- Kết hợp nhiều CodeTransform hoặc ClassTransform thành các bước xử lý có thể tái sử dụng.

Class-File API xử lý cấu trúc class file; nó không tự cung cấp cơ chế cài đặt agent hoặc thay thế class đã nạp. Nếu muốn biến đổi class ngay khi JVM tải class, cần tích hợp bước transform với cơ chế nạp class phù hợp, chẳng hạn Java Instrumentation API hoặc một class loader riêng.

## Kết luận

Class-File API cho phép chèn logging hoặc đo thời gian bằng cách kết hợp @@BT@@ClassTransform@@BT@@ và @@BT@@CodeTransform@@BT@@. Với mẫu đo thời gian, @@BT@@atStart@@BT@@ lưu thời điểm bắt đầu vào local slot mới, còn @@BT@@accept@@BT@@ chèn lời gọi helper trước các @@BT@@ReturnInstruction@@BT@@ và chuyển tiếp instruction gốc.

Cách làm này giữ nguyên các lệnh nghiệp vụ và giá trị trả về trên đường return bình thường, với điều kiện helper logging không ném exception. Mẫu cơ bản không ghi thời gian cho đường thoát bằng exception; muốn hỗ trợ trường hợp đó cần bổ sung exception handler và kiểm tra kỹ exception table.

Class-File API được hoàn thiện trong Java 24 theo JEP 484. Đây là API chuẩn còn dùng được trên JDK hiện đại để phân tích, tạo và biến đổi bytecode mà không cần dựa vào các package nội bộ.

## Tài liệu tham khảo

- [JEP 457: Class-File API (Preview), JDK 22](https://openjdk.org/jeps/457)
- [JEP 466: Class-File API (Second Preview), JDK 23](https://openjdk.org/jeps/466)
- [JEP 484: Class-File API, JDK 24](https://openjdk.org/jeps/484)
- [Java SE 24 API — ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java SE 24 API — ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [Java SE 24 API — CodeTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [Java SE 24 API — CodeBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [Java SE 24 API — ReturnInstruction](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ReturnInstruction.html)
