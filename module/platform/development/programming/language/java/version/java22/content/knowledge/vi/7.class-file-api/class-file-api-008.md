# Biến đổi lớp hoặc phương thức bằng transform và bảo toàn phần tử không sửa

Class-File API trong package `java.lang.classfile` cho phép đọc, tạo và biến đổi bytecode Java bằng các model, builder và transform có kiểu rõ ràng. Khi chỉ cần sửa một phần của class file, transform có thể thay thế hoặc loại bỏ đúng phần tử mục tiêu, đồng thời chuyển tiếp những phần tử còn lại sang builder để giữ nguyên nội dung của chúng.

Class-File API xuất hiện dưới dạng preview trong Java 22 qua JEP 457, tiếp tục preview trong Java 23 qua JEP 466 và trở thành API chính thức từ Java 24 qua JEP 484. Bài này sử dụng API ổn định từ Java 24 trở lên, với ví dụ dựa trên Javadoc Java SE 27. Không cần bật `--enable-preview`.

## 1. Model, builder và transform

Class-File API biểu diễn class file theo cấu trúc phân cấp. Một class có thể chứa field, method, attribute; một method có thể chứa attribute và bytecode instruction. Mỗi tầng có model, element và builder tương ứng.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Model | Mô tả bất biến của dữ liệu class file đã đọc. | `ClassModel`, `MethodModel`, `CodeModel` |
| Element | Một thành phần có thể xuất hiện khi duyệt model. | `ClassElement`, `MethodElement`, `CodeElement` |
| Builder | Nhận các element để tạo class file mới. | `ClassBuilder`, `MethodBuilder`, `CodeBuilder` |
| Transform | Quyết định giữ, bỏ hoặc thay thế từng element khi đưa dữ liệu vào builder. | `ClassTransform`, `MethodTransform`, `CodeTransform` |

Đọc một class file thành `ClassModel`:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] originalBytes = Files.readAllBytes(Path.of("Example.class"));

ClassFile classFile = ClassFile.of();
ClassModel model = classFile.parse(originalBytes);
```

`ClassModel` và các model con là mô tả bất biến, không sửa trực tiếp bytecode đang đọc. Muốn thay đổi class file, tạo transform rồi yêu cầu `ClassFile` dựng ra một mảng byte mới.

## 2. Transform hoạt động như thế nào?

Một transform nhận một builder và một element. Với mỗi element, transform có thể thực hiện một trong ba việc:

1. **Giữ lại:** gọi `builder.with(element)` để chuyển element hiện tại sang builder.
2. **Loại bỏ:** không gửi element đó vào builder.
3. **Thay thế:** tạo một hoặc nhiều element mới qua các phương thức của builder, không chuyển element cũ vào builder.

Có thể hình dung transform như một phép biến đổi trên chuỗi element: mỗi element đầu vào được ánh xạ thành không element, một element hoặc nhiều element đầu ra.

<text color="secondary" size="sm">Quy tắc cần nhớ khi viết transform tùy biến:</text>

```java
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.NopInstruction;

CodeTransform removeNops = (builder, element) -> {
    if (!(element instanceof NopInstruction)) {
        builder.with(element); // Giữ nguyên mọi instruction khác.
    }
};
```

Trong ví dụ này, `NopInstruction` bị loại khỏi method body; các element khác được chuyển tiếp nguyên trạng.

Nếu không gọi `builder.with(element)` và cũng không phát element thay thế, element đó sẽ bị loại khỏi kết quả. Đây là lỗi dễ gặp nhất khi viết transform: một nhánh điều kiện chỉ xử lý trường hợp cần thay thế nhưng quên chuyển tiếp các trường hợp còn lại.

`builder.with(element)` giữ nội dung element ở cấp mô hình class file. Điều này không có nghĩa kết quả phải giống từng byte với file ban đầu: constant pool, chỉ số và các cấu trúc phụ thuộc có thể được tạo lại trong quá trình ghi.

## 3. Các cấp độ transform

Class-File API cung cấp transform tương ứng với các cấu trúc khác nhau:

| Transform | Làm việc với | Cách nâng lên cấp lớn hơn |
| --- | --- | --- |
| `CodeTransform` | Các element trong `CodeModel`, chủ yếu là instruction và pseudo-instruction. | `MethodTransform.transformingCode(...)` hoặc `ClassTransform.transformingMethodBodies(...)` |
| `MethodTransform` | Các element của một method, gồm `CodeModel` và các method attribute. | `ClassTransform.transformingMethods(...)` |
| `ClassTransform` | Các element của class, gồm method, field và class attribute. | Dùng trực tiếp với `ClassFile.transformClass(...)`. |

Việc nâng transform cho phép viết logic ở cấp nhỏ nhất cần thiết rồi áp dụng nó cho một method hoặc cả class. Các phần tử ở cấp ngoài phạm vi được chọn sẽ được chuyển tiếp sang builder.

## 4. Biến đổi class và giữ các phần tử khác

Giả sử một thư viện tạo các phương thức trợ giúp có tên bắt đầu bằng `debug`. Ta muốn loại bỏ những phương thức đó khỏi class trước khi đóng gói, đồng thời giữ lại field, constructor, method thông thường và attribute khác.

Có thể dùng `ClassTransform.dropping(...)`:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;

ClassFile classFile = ClassFile.of();
ClassModel model = classFile.parse(originalBytes);

ClassTransform removeDebugMethods = ClassTransform.dropping(
        element -> element instanceof MethodModel method
                && method.methodName().stringValue().startsWith("debug")
);

byte[] transformedBytes = classFile.transformClass(model, removeDebugMethods);
```

`ClassTransform.dropping(predicate)` loại bỏ element khi predicate trả về `true` và chuyển tiếp các element khác. Vì predicate chỉ chọn `MethodModel` có tên bắt đầu bằng `debug`, những method còn lại, field, class attribute và các element khác vẫn được giữ trong class mới.

Không nên xóa method chỉ dựa vào tiền tố tên nếu method đó còn được gọi từ bytecode, reflection, framework hoặc mã bên ngoài. Transform có thể tạo class file hợp lệ về cấu trúc nhưng không thể tự biết việc xóa một method có làm thay đổi hành vi ứng dụng hay không.

### 4.1. Viết transform tường minh

`ClassTransform.dropping(...)` là factory tiện lợi. Có thể viết cùng logic bằng lambda để thấy rõ thao tác giữ element:

```java
ClassTransform removeDebugMethods = (builder, element) -> {
    if (!(element instanceof MethodModel method
            && method.methodName().stringValue().startsWith("debug"))) {
        builder.with(element);
    }
    // Nhánh còn lại không gửi method debug vào builder nên method bị loại.
};
```

Khi transform cần xử lý nhiều trường hợp, cách viết tường minh giúp kiểm soát việc giữ, thay thế hoặc bỏ từng loại element. Hãy luôn có nhánh chuyển tiếp các element mà transform không định sửa.

## 5. Biến đổi method hoặc method body được chọn

`MethodTransform` làm việc với các element của một method. Nếu chỉ muốn sửa bytecode mà giữ nguyên method metadata và attribute khác, dùng `MethodTransform.transformingCode(CodeTransform)`.

Ví dụ, ứng dụng đang gọi hàm tĩnh `legacy.Clock.now()`. Ta muốn chuyển các lời gọi đó sang `app.ClockFacade.now()` trong method `calculate`, còn mọi instruction khác vẫn giữ nguyên.

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.MethodTransform;
import java.lang.classfile.Opcode;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;

CodeTransform redirectClockCalls = (builder, element) -> {
    if (element instanceof InvokeInstruction call
            && call.owner().name().equalsString("legacy/Clock")
            && call.opcode() == Opcode.INVOKESTATIC) {

        // Không chuyển instruction cũ sang builder.
        // Thay bằng lời gọi đến app.ClockFacade với cùng tên và method descriptor.
        builder.invokestatic(
                ClassDesc.of("app.ClockFacade"),
                call.name().stringValue(),
                call.typeSymbol(),
                call.isInterface()
        );
    } else {
        // Giữ nguyên tất cả instruction không thuộc trường hợp cần đổi.
        builder.with(element);
    }
};

MethodTransform transformMethodBody =
        MethodTransform.transformingCode(redirectClockCalls);

ClassTransform transformCalculateOnly = ClassTransform.transformingMethods(
        method -> method.methodName().stringValue().equals("calculate"),
        transformMethodBody
);

ClassFile classFile = ClassFile.of();
ClassModel model = classFile.parse(originalBytes);
byte[] transformedBytes = classFile.transformClass(model, transformCalculateOnly);
```

Quá trình này đi qua ba lớp:

1. `CodeTransform` kiểm tra từng instruction trong method body. Chỉ lời gọi `invokestatic` có owner là `legacy/Clock` mới được thay thế.
2. `MethodTransform.transformingCode(...)` đưa code transform vào phần `CodeModel` của method và chuyển tiếp các method element khác.
3. `ClassTransform.transformingMethods(predicate, ...)` chỉ áp dụng method transform cho method tên `calculate`; các method khác và class element còn lại được giữ.

`ClassTransform.transformingMethodBodies(predicate, codeTransform)` là cách viết rút gọn khi chỉ cần lọc method và áp dụng trực tiếp một `CodeTransform`:

```java
ClassTransform transformCalculateOnly = ClassTransform.transformingMethodBodies(
        method -> method.methodName().stringValue().equals("calculate"),
        redirectClockCalls
);
```

Hai cách trên cùng diễn đạt việc biến đổi code trong một tập method được chọn. Cách tách `MethodTransform` hữu ích khi cần kết hợp nhiều phép biến đổi cấp method hoặc tái sử dụng transform ở nhiều nơi.

### 5.1. Điều kiện để thay instruction an toàn

Ví dụ thay lời gọi chỉ an toàn khi method đích tương thích với lời gọi gốc. Cần bảo đảm:

- Method mới tồn tại với đúng tên và method descriptor được truyền vào builder.
- Số lượng, thứ tự và kiểu tham số tương thích với các giá trị đang nằm trên operand stack.
- Kiểu trả về tương thích với instruction và các instruction tiếp theo.
- Cách gọi là `invokestatic`; không thay bằng lời gọi instance hoặc interface nếu chưa điều chỉnh bytecode tương ứng.
- Class đích có thể được resolve và truy cập trong môi trường chạy thực tế.

Class-File API kiểm tra các giới hạn biểu diễn của class file, nhưng không tự chứng minh rằng method đích tồn tại hoặc rằng thay đổi giữ nguyên logic nghiệp vụ.

## 6. Bảo toàn element không sửa ở từng cấp

Quy tắc `builder.with(element)` áp dụng ở mọi cấp độ transform:

| Cấp độ | Element cần giữ | Builder chuyển tiếp |
| --- | --- | --- |
| Class | Method, field, class attribute không sửa | `ClassBuilder.with(element)` |
| Method | Code attribute, annotation và method attribute không sửa | `MethodBuilder.with(element)` |
| Code | Instruction, label, exception handler và debug pseudo-instruction không sửa | `CodeBuilder.with(element)` |

Các transform factory dựng sẵn thường tự chuyển tiếp những element nằm ngoài phạm vi sửa đổi. Ví dụ:

- `ClassTransform.dropping(filter)` giữ element không khớp filter.
- `ClassTransform.transformingMethods(xform)` chỉ xử lý method và chuyển tiếp class element khác.
- `MethodTransform.transformingCode(xform)` chỉ xử lý `CodeModel` và chuyển tiếp method element khác.
- `ClassTransform.transformingMethodBodies(xform)` chỉ xử lý method body và chuyển tiếp các class element còn lại.

Khi viết transform tùy biến, trách nhiệm chuyển tiếp thuộc về code của transform. Nếu một `switch` chỉ xử lý một vài loại instruction, có thể dùng `default -> builder.with(element)` để giữ những loại chưa cần quan tâm. Cách này cũng giúp transform tiếp tục chuyển tiếp element mới được JDK bổ sung trong tương lai.

Nếu transform phải hiểu và kiểm tra mọi loại element để bảo đảm một thuộc tính bảo mật hoặc định dạng nghiêm ngặt, có thể chọn cách xử lý tường minh và từ chối loại element không nhận biết. Đó là một chính sách khác với transform chỉ sửa một phần và giữ nguyên phần còn lại.

## 7. Kết hợp nhiều transform

Các transform cùng cấp có thể kết hợp bằng `andThen(...)`. Output element mà transform đầu tiên gửi vào builder sẽ trở thành input của transform tiếp theo. Nhờ đó, nhiều bước sửa đổi có thể chạy trong cùng một lần dựng class file.

```java
CodeTransform replaceClock = (builder, element) -> {
    if (element instanceof InvokeInstruction call
            && call.owner().name().equalsString("legacy/Clock")
            && call.opcode() == Opcode.INVOKESTATIC) {
        builder.invokestatic(
                ClassDesc.of("app.ClockFacade"),
                call.name().stringValue(),
                call.typeSymbol(),
                call.isInterface()
        );
    } else {
        builder.with(element);
    }
};

CodeTransform addNopAfterCalls = (builder, element) -> {
    builder.with(element);
    if (element instanceof InvokeInstruction) {
        builder.nop(); // NOP không làm thay đổi operand stack.
    }
};

CodeTransform combined = replaceClock.andThen(addNopAfterCalls);
```

Trong ví dụ, `addNopAfterCalls` chuyển tiếp instruction hiện tại rồi thêm một `nop` sau mỗi lời gọi. `nop` không tiêu thụ hoặc tạo giá trị trên operand stack. Khi hai transform được kết hợp, bước thứ hai nhận cả instruction đã được thay thế bởi bước đầu tiên lẫn instruction được giữ nguyên. Với các thay đổi bytecode thực tế, vẫn phải kiểm tra stack effect, thứ tự lệnh, exception region và control flow.

Với transform có trạng thái qua nhiều element, dùng factory `ofStateful(Supplier)` để mỗi lần duyệt nhận một transform và state mới. Không chia sẻ state mutable giữa các lần transform nếu state đó chỉ dành cho một lần xử lý.

## 8. Kiểm tra class file sau khi biến đổi

Sau khi tạo byte mới, có thể dùng `ClassFile.verify(...)` để kiểm tra các lỗi xác minh class file mà API phát hiện được:

```java
byte[] transformedBytes = classFile.transformClass(model, transformCalculateOnly);

var errors = classFile.verify(transformedBytes);
if (!errors.isEmpty()) {
    throw new IllegalStateException("Invalid class file: " + errors);
}
```

Việc verify giúp phát hiện các vấn đề như bytecode không hợp lệ hoặc stack map không phù hợp. Nó không thay thế kiểm thử hành vi, kiểm tra liên kết method/class, kiểm tra quyền truy cập hay chạy ứng dụng trong môi trường đích.

Khi làm việc với class file có attribute tùy biến, cần cung cấp `AttributeMapper` phù hợp nếu muốn đọc và ghi attribute đó dưới dạng model có kiểu. Nếu không nhận biết attribute hoặc element mới, transform chỉ sửa một phần nên chuyển tiếp chúng bằng `builder.with(element)` khi hợp đồng cho phép. Các option của `ClassFile` cũng cho phép điều chỉnh cách xử lý attribute, debug information, line number, stack map và constant pool.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Quên `builder.with(element)` trong nhánh không sửa | Element không được phát ra builder và bị loại khỏi kết quả. | Chuyển tiếp mọi element không thay đổi. |
| Gọi `builder.with(element)` sau khi đã phát element thay thế | Cả bản cũ và bản mới cùng xuất hiện. | Chỉ phát bản thay thế ở nhánh đã xử lý. |
| Dùng `ClassTransform` khi chỉ cần sửa bytecode một method | Phải tự xử lý nhiều loại class element hơn mức cần thiết. | Dùng `CodeTransform` rồi nâng lên bằng `MethodTransform` hoặc `ClassTransform`. |
| Chỉ lọc theo tên method khi có overload | Có thể biến đổi nhiều method cùng tên. | Lọc thêm `methodTypeSymbol()` nếu cần chọn đúng overload. |
| Thay invocation bằng method descriptor khác | Operand stack có thể không còn hợp lệ. | Giữ nguyên method descriptor hoặc thiết kế lại toàn bộ chuỗi instruction liên quan. |
| Giả định class file mới chắc chắn chạy đúng | Verify không kiểm tra toàn bộ liên kết và hành vi runtime. | Verify, kiểm thử và chạy trong môi trường đích. |
| Xử lý một số instruction rồi bỏ qua phần còn lại | Các instruction không khớp điều kiện bị mất. | Dùng `default -> builder.with(element)` khi mục tiêu là chỉ sửa một tập con. |

## Ghi nhớ

- Class-File API là API chính thức từ Java 24 (JEP 484); Java 22 và 23 chỉ là các vòng preview trước khi API được hoàn thiện.
- `ClassTransform`, `MethodTransform` và `CodeTransform` cho phép chọn đúng cấp cần biến đổi.
- `ClassFile.transformClass(model, transform)` tạo byte mới từ model và transform.
- Trong transform tùy biến, gọi `builder.with(element)` để giữ element không sửa. Không có hành động nào nghĩa là element bị loại.
- Factory như `ClassTransform.dropping`, `transformingMethods` và `transformingMethodBodies` tự chuyển tiếp những element nằm ngoài phạm vi được chọn.
- Thay bytecode phải giữ tính nhất quán của descriptor, operand stack, control flow và các metadata liên quan.
- Dùng `ClassFile.verify(...)` để kiểm tra class file sau biến đổi, sau đó vẫn cần kiểm thử liên kết và hành vi ứng dụng.

## Tài liệu tham khảo

- [JEP 457: Class-File API (Preview, JDK 22)](https://openjdk.org/jeps/457)
- [JEP 466: Class-File API (Second Preview, JDK 23)](https://openjdk.org/jeps/466)
- [JEP 484: Class-File API (Final, JDK 24)](https://openjdk.org/jeps/484)
- [Java SE 27 API — `ClassFile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java SE 27 API — `ClassTransform`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [Java SE 27 API — `MethodTransform`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/MethodTransform.html)
- [Java SE 27 API — `CodeTransform`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [Java SE 27 API — `ClassFileTransform`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFileTransform.html)
- [Java SE 27 API — `CodeBuilder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [Java SE 27 API — `InvokeInstruction`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/instruction/InvokeInstruction.html)
