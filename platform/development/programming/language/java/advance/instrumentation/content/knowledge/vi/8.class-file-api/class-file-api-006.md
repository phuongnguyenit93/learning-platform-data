# ClassTransform, MethodTransform, CodeTransform và ghép các phép biến đổi trong Class-File API

Java Class-File API cung cấp cách **đọc, tạo và biến đổi file `.class`** bằng các model và builder có kiểu dữ liệu rõ ràng, thay vì tự sửa mảng byte tùy tiện. Ba loại transform quan trọng khi tổ chức một phép biến đổi là:

- **`ClassTransform`**: xử lý các phần tử cấp **class** như method, field và attribute.
- **`MethodTransform`**: xử lý các phần tử cấp **method**, bao gồm `CodeModel` (thân method) và các method attribute.
- **`CodeTransform`**: xử lý các phần tử trong **method body** như instruction, label và một số metadata.

Điểm mạnh của API không chỉ là có ba loại callback: ta có thể **ghép các phép biến đổi cùng cấp bằng `andThen`** và **nâng phép biến đổi cấp thấp lên cấp cao** bằng các factory như `MethodTransform.transformingCode(...)`, `ClassTransform.transformingMethods(...)` và `ClassTransform.transformingMethodBodies(...)`.

Bài học sẽ giải thích hợp đồng chuyển đổi, cách ghép đúng kiểu, trình tự áp dụng, ví dụ chạy được trên **JDK 24+**, cách kiểm tra class file kết quả và ranh giới với `java.lang.instrument.ClassFileTransformer`.

## 1. Phiên bản Java: lý do ví dụ dùng JDK 24+

**`java.lang.classfile` là API chuẩn từ JDK 24**, sau các giai đoạn preview ở những phiên bản JDK trước. Các interface như `ClassFile`, `ClassModel`, `ClassTransform`, `MethodTransform`, `CodeTransform` dùng trong bài nằm trong module `java.base` và không cần dependency bên ngoài.

- Với **JDK 24 trở lên**: dùng API chuẩn; ví dụ có thể biên dịch thông thường bằng `javac --release 24`.
- Với **JDK 17**: package `java.lang.classfile` **chưa tồn tại**. Không thể biên dịch ví dụ trong bài bằng JDK 17 bằng cách chỉ thêm import hoặc đổi cờ `--release`.
- Với **JDK 22/23**: Class-File API từng là preview và có khác biệt theo phiên bản; không giả định mọi method/type giống bản chuẩn JDK 24.
- Nếu phải instrument trên Java 17, cân nhắc thư viện bytecode như ASM, Byte Buddy, Javassist; hoặc dùng tool tạo bytecode bằng JDK 24+ rồi kiểm tra **class file version** và khả năng chạy trên JVM mục tiêu.

Vì chủ đề này trực tiếp yêu cầu **Class-File API**, ví dụ dùng JDK 24+ là lựa chọn chính xác hơn việc cố viết mã gọi các interface không tồn tại ở Java 17. Nên dùng JDK 25 hoặc mới hơn khi thực hành, nhưng biên dịch với `--release 24` để kiểm tra tương thích API chuẩn ban đầu.

**Không đánh đồng** các tên sau:

```text
java.lang.classfile.ClassTransform          // Phép biến đổi trong Class-File API
java.lang.classfile.MethodTransform         // Phép biến đổi bên trong method
java.lang.classfile.CodeTransform           // Phép biến đổi các CodeElement
java.lang.instrument.ClassFileTransformer   // Callback của JVM instrumentation
```

`ClassFileTransformer` là điểm vào của cơ chế instrumentation khi JVM load/retransform/redefine lớp. Bên trong callback đó, bạn **có thể dùng** Class-File API để tạo bytes mới; nhưng `ClassTransform` không tự đăng ký vào JVM.

## 2. Mô hình phân cấp: Model → Element → Transform → Builder

Một file `.class` có cấu trúc lồng nhau:

```text
ClassModel                            ClassBuilder
  ├── FieldModel                       └── (field và attribute)
  ├── MethodModel                     MethodBuilder
  │     ├── method attribute             ├── method attribute
  │     └── CodeModel                  CodeBuilder
  │            ├── instruction           ├── instruction
  │            ├── label                 ├── label
  │            └── code metadata         └── code metadata
  └── class attribute
```

Đọc class file:

```java
ClassFile cf = ClassFile.of();
ClassModel original = cf.parse(classBytes);
```

Đoạn này chỉ là **mã minh họa bên trong một method**, với biến `classBytes` đã được chuẩn bị. `ClassModel` mô tả class file nguồn; API cho phép xem các `MethodModel`, `FieldModel`, attributes và cấu trúc code. Nó không phải một bản sao của `java.lang.Class<?>` đang chạy.

Tại mỗi cấp, một transform nhận **builder đầu ra** và **phần tử đầu vào**:

| Cấp | Transform | Input element | Output builder |
|---|---|---|---|
| Class | `ClassTransform` | `ClassElement` | `ClassBuilder` |
| Method | `MethodTransform` | `MethodElement` | `MethodBuilder` |
| Code | `CodeTransform` | `CodeElement` | `CodeBuilder` |

Cả ba đều là functional interface và hỗ trợ cú pháp lambda `(builder, element) -> { ... }`. Về ý nghĩa, transform **không bắt buộc phải trả về phần tử**; nó thực hiện thao tác *phát* phần tử tới builder.

**Ba quyết định khi nhận một element:**

1. **Giữ nguyên:** `builder.with(element)`.
2. **Bỏ đi:** không gửi element đó tới builder.
3. **Thay thế / thêm mới:** gửi một hoặc nhiều element mới theo API của builder, có thể bỏ phần tử cũ.

Bỏ quên `builder.with(element)` trong nhánh mặc định **có thể làm mất dữ liệu class file**, không phải chỉ “không thay đổi”. Đây là quy tắc quan trọng nhất khi tự viết transform.

## 3. `ClassTransform`: biến đổi thành phần cấp class

`ClassTransform` xử lý chuỗi `ClassElement`. Các phần tử có thể là `MethodModel`, `FieldModel` hoặc attribute cấp class. Bạn có thể thêm, giữ, sửa hoặc bỏ một phần tử theo hợp đồng builder.

### 3.1. Ví dụ nhỏ: loại bỏ một method không còn cần dùng

```java
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;

ClassTransform dropDebug = ClassTransform.dropping(
        element -> element instanceof MethodModel method
                && method.methodName().stringValue().equals("debug"));
```

Đây là **đoạn trong thân method**, không phải file Java độc lập. `ClassTransform.dropping(predicate)` giúp loại bỏ phần tử phù hợp và **giữ các phần tử không khớp**. Trong ví dụ, method có tên `debug` bị xóa khỏi class file kết quả; những method và attribute khác được chuyển tiếp.

Tương đương với lambda tự viết:

```java
ClassTransform dropDebug = (builder, element) -> {
    if (element instanceof MethodModel method
            && method.methodName().stringValue().equals("debug")) {
        return; // Không gửi method này: bỏ nó.
    }
    builder.with(element);
};
```

`return` ở đây kết thúc lời gọi callback trên **một phần tử**, không có nghĩa dừng toàn bộ chuỗi transform. Class có thể trở nên không hợp lệ hoặc ứng dụng có thể gặp `NoSuchMethodError` nếu code khác còn tham chiếu method đã loại bỏ. Chỉ xóa khi đã hiểu các ràng buộc này.

### 3.2. Cách gọi transform cấp class

```java
ClassFile cf = ClassFile.of();
ClassModel model = cf.parse(bytes);
byte[] result = cf.transformClass(model, dropDebug);
```

Các biến `bytes`, `dropDebug` phải có sẵn (đây là trích đoạn minh họa). `transformClass` tạo **byte[] class file mới**. Nó không tự nạp lớp mới vào JVM và không tự thay `java.lang.Class<?>` đã tồn tại.

Một số tiện ích:

- `ClassTransform.ACCEPT_ALL`: chuyển tiếp tất cả class elements.
- `ClassTransform.dropping(predicate)`: loại bỏ class elements theo điều kiện.
- `ClassTransform.transformingFields(fieldTransform)`: áp dụng transform lên các field.
- `ClassTransform.transformingMethods(methodTransform)`: áp dụng transform lên các method.
- `ClassTransform.transformingMethods(predicate, methodTransform)`: chỉ áp dụng cho method được chọn.
- `ClassTransform.transformingMethodBodies(predicate, codeTransform)`: áp dụng trực tiếp lên thân code của method được chọn.
- `ClassTransform.andThen(other)`: nối **hai ClassTransform** theo thứ tự.

Lưu ý `ClassTransform` xử lý **class elements**; nó không tự đi xuống mọi bytecode instruction. Muốn sửa code bên trong method, cần **lift** một `CodeTransform` lên cấp class, hoặc gọi API builder tương ứng.

## 4. `MethodTransform`: biến đổi cấu trúc của từng method

`MethodTransform` xử lý `MethodElement` và ghi kết quả vào `MethodBuilder`. Bên trong method, phần tử `CodeModel` mô tả code attribute; các phần tử khác có thể chứa annotations hoặc metadata.

Ví dụ **chỉ kiểm tra một phần tử rồi giữ nguyên**:

```java
MethodTransform observeMethod = (builder, element) -> {
    System.out.println("method-element=" + element.getClass().getSimpleName());
    builder.with(element);
};
```

Đoạn này không độc lập chạy được vì cần import `MethodTransform` và bối cảnh gọi transform. Việc log tên implementation class chỉ dùng minh họa: không nên viết logic nghiệp vụ phụ thuộc vào tên các implementation class nội bộ.

Khi sử dụng `ClassTransform.transformingMethods(observeMethod)`, `observeMethod` sẽ được áp dụng cho các method thuộc class. Các phần tử **không phải method** được factory chuyển tiếp để giữ cấu trúc class.

### 4.1. Đi từ MethodTransform xuống CodeTransform

Giả sử đã có `CodeTransform codeTransform`. Ta tạo:

```java
MethodTransform methodTransform =
        MethodTransform.transformingCode(codeTransform);
```

Factory này tìm `CodeModel` trong method, áp dụng `codeTransform`, đồng thời **giữ các method element khác**. Vì vậy an toàn và rõ nghĩa hơn việc tự bỏ qua tất cả method attributes.

Sau đó nâng thêm một cấp:

```java
ClassTransform classTransform =
        ClassTransform.transformingMethods(
                method -> method.methodName().stringValue().equals("value"),
                methodTransform);
```

Kết quả: chỉ method có tên `value` được đi vào `methodTransform`, rồi code bên trong đi vào `codeTransform`. Các method khác được chuyển qua không bị sửa.

**Thứ tự phân cấp:**

```text
ClassTransform
    └── chọn MethodModel "value"
            └── MethodTransform
                    └── tìm CodeModel
                            └── CodeTransform cho CodeElement
```

Trường hợp chỉ cần thao tác code có thể dùng rút gọn:

```java
ClassTransform sameScope =
        ClassTransform.transformingMethodBodies(
                method -> method.methodName().stringValue().equals("value"),
                codeTransform);
```

Hai đoạn trên mô tả **hai cách xây pipeline thay thế nhau**, không phải yêu cầu chạy cả hai. Factory `transformingMethodBodies` trực tiếp nâng CodeTransform lên ClassTransform cho method thỏa predicate.

### 4.2. `MethodTransform` không dùng để “xóa method”

Vì `MethodTransform` đang xử lý **các phần tử bên trong một method đã được chọn**, nếu muốn **xóa toàn bộ một method**, hãy thực hiện ở cấp `ClassTransform`, nơi `MethodModel` là một `ClassElement`. Nếu xóa bừa `CodeModel` khỏi một method concrete có code, class kết quả có thể không hợp lệ.

Đây là nguyên tắc lựa chọn cấp thao tác: **muốn loại bỏ đối tượng nào, hãy tìm cấp mà đối tượng đó xuất hiện như một element**.

## 5. `CodeTransform`: chỉnh dòng instruction trong thân method

`CodeTransform` xử lý các `CodeElement`. Đây là cấp cần dùng khi chèn, đổi hoặc bỏ một bytecode instruction, label, handler hoặc metadata được API mô hình hóa ở cấp code.

### 5.1. Mẫu an toàn: chèn instruction rồi giữ instruction cũ

```java
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.ReturnInstruction;

CodeTransform addNopBeforeReturn = (builder, element) -> {
    if (element instanceof ReturnInstruction) {
        builder.nop();
    }
    builder.with(element);
};
```

Đây là **mã minh họa trong thân method**. `builder.nop()` phát thêm instruction `nop` (không làm gì) trước mỗi return; `builder.with(element)` giữ chính return instruction và những code elements khác.

Với logic tổng quát, chèn instruction khác `nop` đòi hỏi tính toán stack effects, labels, exception handlers và tính hợp lệ của control-flow. API có thể hỗ trợ xây dựng metadata class file, nhưng không biến mọi sửa đổi logic thành đúng tự động.

### 5.2. Mẫu loại bỏ instruction

```java
import java.lang.classfile.instruction.NopInstruction;

CodeTransform removeNops = (builder, element) -> {
    if (!(element instanceof NopInstruction)) {
        builder.with(element);
    }
};
```

Vì `nop` không ảnh hưởng operand stack, bỏ `nop` đơn lẻ là thao tác dễ hiểu để học cách drop một `CodeElement`. Không suy rộng ví dụ này thành quyền xóa tùy tiện `return`, `goto`, label target hoặc instruction được nhánh khác tham chiếu: làm vậy có thể khiến code sai hoặc không verify được.

### 5.3. Giữ phần tử mặc định là bắt buộc khi không muốn thay

Trong lambda:

```java
CodeTransform careless = (builder, element) -> {
    if (element instanceof ReturnInstruction) {
        builder.nop();
    }
};
```

**Đây là ví dụ sai để nhận diện lỗi.** Vì thiếu `builder.with(element)`, mọi element nguồn không được chuyển tiếp; `return` cũ cũng bị bỏ, có thể khiến method body không hợp lệ. Khi code review một `CodeTransform`, luôn kiểm tra mọi nhánh có chủ ý giữ/thay/bỏ element.

## 6. Hai chiều ghép phép biến đổi: `andThen` và “lifting”

Có **hai thao tác khác nhau** rất dễ bị nhầm.

### 6.1. Ghép cùng cấp với `andThen`

```java
CodeTransform combinedCode =
        addNopBeforeReturn.andThen(removeNops);
```

Cả hai đều là `CodeTransform`, nên phương thức có thể kết nối chúng:

```text
CodeModel nguồn
     |
     v
addNopBeforeReturn
     |  output elements (gồm nop vừa thêm)
     v
removeNops
     |  output elements (nop bị loại)
     v
CodeBuilder đích
```

**`first.andThen(second)` nghĩa là kết quả element của `first` được đưa vào `second`**. Đó không phải “áp dụng hai lambda độc lập lên hai bản sao của input”. API dùng một *chained builder* nên không nhất thiết cần tạo classfile trung gian trên đĩa.

Cũng có các dạng:

```java
ClassTransform classChain = classTransformA.andThen(classTransformB);
MethodTransform methodChain = methodTransformA.andThen(methodTransformB);
CodeTransform codeChain = codeTransformA.andThen(codeTransformB);
```

Đây là **mã mẫu có các biến A/B đã khai báo**, không phải file runnable độc lập. Mỗi `andThen` giữ cùng loại `ClassTransform`, `MethodTransform` hoặc `CodeTransform`.

Không thể ghép trực tiếp **khác cấp**:

```java
// Sai kiểu, không biên dịch:
ClassTransform wrong = classTransformA.andThen(codeTransformA);
```

Hãy **lift** `codeTransformA` trước:

```java
ClassTransform lifted =
        ClassTransform.transformingMethodBodies(codeTransformA);
ClassTransform right = classTransformA.andThen(lifted);
```

Lưu ý `andThen` có hướng: nếu đổi `A.andThen(B)` thành `B.andThen(A)`, kết quả có thể khác. Với bytecode, thao tác thứ hai luôn nhìn thấy element đã được thao tác thứ nhất phát ra.

### 6.2. Nâng cấp thấp lên cấp cao (lifting)

Nâng bằng các factory:

```text
CodeTransform
    |
    +-- MethodTransform.transformingCode(codeTransform)
    |       -> MethodTransform
    |             |
    |             +-- ClassTransform.transformingMethods(methodTransform)
    |                        -> ClassTransform
    |
    +-- ClassTransform.transformingMethodBodies(codeTransform)
            -> ClassTransform trực tiếp
```

Lifting có thể đi kèm predicate để chỉ xử lý các method được chọn. Ví dụ lọc theo method name:

```java
ClassTransform selected = ClassTransform.transformingMethodBodies(
        m -> m.methodName().stringValue().equals("value"),
        addNopBeforeReturn.andThen(removeNops));
```

Đây là mẫu rất hữu ích khi cần áp dụng một `CodeTransform` nhỏ cho hàng loạt method trong một class. Thay vì viết lại logic vòng lặp của toàn `ClassModel` và từng `MethodModel`, ta tái sử dụng các transform độc lập.

### 6.3. Cách kết hợp cả hai chiều

Ví dụ tổ chức:

```text
CodeTransform A (insert nop) --andThen--> CodeTransform B (remove nop)
                                 |
                                 v
               MethodTransform.transformingCode(A.andThen(B))
                                 |
                                 v
    ClassTransform.transformingMethods(filter, methodTransform)
                                 |
                            andThen
                                 |
                                 v
             ClassTransform.dropping(debug method)
                                 |
                                 v
                    ClassFile.transformClass(...)
```

Ở đây pipeline có hai loại thứ tự:

1. **Bên trong method body**: A rồi B.
2. **Trên ClassElement stream**: bước xử lý method body rồi bước loại method debug.

Bước class-transform sau có thể quan sát output từ class-transform trước; thành phần nào không được gửi tiếp sẽ không tới output cuối.

## 7. Ví dụ hoàn chỉnh JDK 24+: kết hợp cả ba loại transform

Mục tiêu thực hành:

- Đọc class file chứa ba method `value`, `debug` và `main`.
- Dùng **`CodeTransform`** A chèn `nop` ngay trước return của method `value`.
- Dùng **`CodeTransform`** B loại `nop` mà A vừa sinh; hai transform được nối bằng `andThen`.
- Dùng **`MethodTransform.transformingCode`** để gắn A+B vào code của một method.
- Dùng **`ClassTransform.transformingMethods`** để chọn method `value`.
- Dùng **`ClassTransform.dropping`** để bỏ method `debug`.
- Nối hai `ClassTransform` bằng `andThen`, ghi class file mới, kiểm tra `ClassFile.verify` và chạy class kết quả.

Bài này **không dùng Java agent** để tránh lẫn trình tự xử lý bytes của API với thời điểm JVM đăng ký transformer. Toàn bộ logic chạy offline trên file `.class`, nên dễ kiểm tra đầu vào và đầu ra.

Cấu trúc thư mục:

```text
classfile-transform-demo/
├── src/
│   ├── TransformDemo.java
│   └── demo/
│       └── Target.java
├── out/                 (tạo bằng javac)
└── patched/             (chương trình tự tạo)
```

### 7.1. Lớp nguồn `src/demo/Target.java`

```java
package demo;

public final class Target {
    private Target() {
    }

    public static int value() {
        return 7;
    }

    public static void debug() {
        System.out.println("debug should not run");
    }

    public static void main(String[] args) {
        System.out.println("value=" + value());
    }
}
```

`debug()` không được gọi từ `main`, nên việc xóa nó trong ví dụ không làm ứng dụng thất bại. `value()` có một `ireturn`, cho phép ghi nhận đúng một `nop` được thêm vào và một `nop` bị xóa ở pipeline sau.

### 7.2. Công cụ `src/TransformDemo.java`

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.MethodModel;
import java.lang.classfile.MethodTransform;
import java.lang.classfile.instruction.NopInstruction;
import java.lang.classfile.instruction.ReturnInstruction;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

public final class TransformDemo {
    private TransformDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path input = Path.of("out", "demo", "Target.class");
        Path output = Path.of("patched", "demo", "Target.class");

        ClassFile cf = ClassFile.of();
        ClassModel original = cf.parse(input);

        AtomicInteger inserted = new AtomicInteger();
        AtomicInteger removed = new AtomicInteger();

        // A: thêm nop trước mỗi return.
        CodeTransform addNop = (builder, element) -> {
            if (element instanceof ReturnInstruction) {
                builder.nop();
                inserted.incrementAndGet();
            }
            builder.with(element);
        };

        // B: nhận cả nop do A sinh và bỏ chúng.
        CodeTransform dropNop = (builder, element) -> {
            if (element instanceof NopInstruction) {
                removed.incrementAndGet();
            } else {
                builder.with(element);
            }
        };

        // Ghép cùng cấp: CodeTransform -> CodeTransform.
        CodeTransform codePipeline = addNop.andThen(dropNop);

        // Nâng CodeTransform -> MethodTransform.
        MethodTransform methodPipeline =
                MethodTransform.transformingCode(codePipeline);

        // Nâng MethodTransform -> ClassTransform,
        // chỉ áp dụng cho method value.
        ClassTransform changeValue =
                ClassTransform.transformingMethods(
                        m -> m.methodName().stringValue().equals("value"),
                        methodPipeline);

        // Một ClassTransform độc lập loại bỏ method debug.
        ClassTransform dropDebug = ClassTransform.dropping(
                element -> element instanceof MethodModel method
                        && method.methodName()
                                .stringValue().equals("debug"));

        // Ghép hai ClassTransform theo thứ tự.
        ClassTransform combined = changeValue.andThen(dropDebug);

        byte[] result = cf.transformClass(original, combined);

        // Đọc lại model kết quả và dùng API verify.
        ClassModel updated = cf.parse(result);
        boolean debugPresent = updated.methods().stream()
                .anyMatch(m -> m.methodName()
                        .stringValue().equals("debug"));
        boolean verified = cf.verify(result).isEmpty();

        Files.createDirectories(output.getParent());
        Files.write(output, result);

        System.out.println("insertedNops=" + inserted.get());
        System.out.println("removedNops=" + removed.get());
        System.out.println("debugPresent=" + debugPresent);
        System.out.println("verified=" + verified);
        System.out.println("saved=patched/demo/Target.class");
    }
}
```

**Tại sao ví dụ này hữu ích?**

1. `addNop` thực sự thêm một `CodeElement` mới bằng `builder.nop()`.
2. `dropNop` nằm sau `addNop` và nhận các element được phát ra, bao gồm `nop` vừa sinh. Nếu `andThen` chỉ chạy hai transform trên hai bản sao độc lập, bộ đếm `removed` sẽ không chứng minh được quan hệ này.
3. `MethodTransform.transformingCode` bảo toàn method elements ngoài code, còn `ClassTransform.transformingMethods(filter, ...)` giữ nguyên các method không được chọn.
4. `dropDebug` là transform **cấp class** vì xóa một `MethodModel` trọn vẹn.
5. `combined` biểu diễn một phép biến đổi thống nhất; `ClassFile.transformClass` tạo bytes của class file mới.
6. `ClassFile.verify` là bước kiểm tra bổ sung; nó không thay thế kiểm thử hành vi ứng dụng và mọi ràng buộc tại runtime.

### 7.3. Biên dịch

Mở terminal tại thư mục `classfile-transform-demo`, đảm bảo đang sử dụng **JDK 24+**, sau đó chạy:

```bash
java -version
javac -version
mkdir out

javac --release 24 -encoding UTF-8 -d out src/demo/Target.java src/TransformDemo.java
```

Với JDK 24+ dùng API chuẩn, **không cần `--enable-preview`**, không cần `--add-exports`, không cần tải ASM. `--release 24` chỉ hợp lệ nếu `javac` được chạy từ JDK có hỗ trợ release đó.

Trên Windows PowerShell, cmd hoặc Unix shell, `mkdir out` có thể thay bằng lệnh tạo thư mục tương ứng nếu thư mục đã tồn tại. Mọi lệnh tiếp theo giả định `out/demo/Target.class` và `out/TransformDemo.class` đã được tạo.

### 7.4. Chạy công cụ biến đổi

```bash
java -cp out TransformDemo
```

Stdout **dự kiến trên JDK 24+ khi công cụ chạy thành công**:

```text
insertedNops=1
removedNops=1
debugPresent=false
verified=true
saved=patched/demo/Target.class
```

Cách đọc:

- `insertedNops=1`: method `value()` có một lệnh return, A phát thêm một `nop` trước lệnh đó.
- `removedNops=1`: B đã quan sát và bỏ `nop` do A phát ra; đây là hiệu quả của `A.andThen(B)`.
- `debugPresent=false`: `ClassTransform.dropping` xóa method `debug` khỏi class file kết quả.
- `verified=true`: API báo không có lỗi qua `cf.verify(result)`.
- `saved=...`: bytes mới được ghi ra file tách biệt, không ghi đè `out/demo/Target.class`.

Bản class đã biến đổi vẫn có method `value` và `main`, không có `debug`. Vì `nop` được thêm rồi lại bỏ, logic của `value()` vẫn trả `7`.

### 7.5. Chạy file class mới

```bash
java -cp patched demo.Target
```

Stdout:

```text
value=7
```

Ở đây `patched` là classpath, không phải `out`: bằng cách đó JVM nạp **bản đã biến đổi**. Nếu vô tình chạy `java -cp out demo.Target`, bạn sẽ chạy class gốc và không kiểm tra được output của công cụ.

Thử so sánh:

```bash
javap -classpath out demo.Target
javap -classpath patched demo.Target
```

Trong mô tả của `javap`, class gốc có method `debug`, còn class mới không có method đó. Dùng `javap -c -classpath patched demo.Target` nếu muốn xem instruction của các method. Không cần đặt một JAR agent hoặc dùng Attach API cho bước này.

### 7.6. Thử đổi thứ tự để thấy tính không giao hoán

Trong file `TransformDemo.java`, thay:

```java
CodeTransform codePipeline = addNop.andThen(dropNop);
```

bằng:

```java
CodeTransform codePipeline = dropNop.andThen(addNop);
```

Đây là **một thay đổi trong file đầy đủ ở mục 7.2**, không phải chương trình độc lập mới. Sau khi biên dịch lại và chạy công cụ:

- `dropNop` chạy trước, nên không nhìn thấy `nop` mà A chưa phát ra.
- `addNop` chạy sau, vì vậy `nop` mới được giữ trong bytes đầu ra.
- Với class `Target` do `javac` tạo ra ở ví dụ này (không có `nop` ban đầu trong `value()`), bộ đếm `removedNops` dự kiến là `0`, còn `insertedNops` vẫn là `1`.
- Chương trình vẫn in `value=7`, vì `nop` không đổi hành vi; sự khác biệt nhìn thấy rõ hơn với `javap -c`.

**Kết luận:** `A.andThen(B)` và `B.andThen(A)` không nhất thiết tương đương. Khi thao tác bytecode thật như chèn lời gọi, thay owner method, đổi branch hoặc sửa exception handler, khác biệt có thể ảnh hưởng hành vi chương trình, không chỉ số lượng `nop`.

## 8. Chọn đúng cấp transform cho từng bài toán

| Yêu cầu | Transform thích hợp | Giải thích |
|---|---|---|
| Xóa toàn bộ method `debug()` | `ClassTransform` | MethodModel là ClassElement |
| Thay đổi thành phần attribute của một method | `MethodTransform` | MethodElement thuộc method |
| Chèn instruction trước `return` | `CodeTransform` | ReturnInstruction là CodeElement |
| Chỉnh tất cả method bodies | `ClassTransform.transformingMethodBodies(codeXform)` | Lift code transform lên toàn class |
| Chỉ chỉnh method `value()` | `ClassTransform.transformingMethods(filter, MethodTransform.transformingCode(codeXform))` | Filter method, rồi xử lý code |
| Ghép hai phép đổi instruction | `codeA.andThen(codeB)` | Hai phép cùng cấp CodeTransform |
| Ghép hai phép sửa cấu trúc class | `classA.andThen(classB)` | Hai phép cùng cấp ClassTransform |
| Biến đổi một MethodModel trực tiếp từ builder | `ClassBuilder.transformMethod(model, methodTransform)` | API builder cấp class |
| Biến đổi một CodeModel trực tiếp trong builder | `MethodBuilder.transformCode(model, codeTransform)` | API builder cấp method |

**`MethodBuilder.transformCode(...)`** và **`ClassBuilder.transformMethod(...)`** là những đường gọi trực tiếp khi bạn đang chủ động xây class/method bằng builder. Các factory `transformingCode` và `transformingMethods` phù hợp hơn khi muốn diễn tả pipeline tái sử dụng trên nhiều phần tử.

Không nên tạo `ClassTransform` riêng cho từng instruction rồi đi qua toàn bộ tree bằng tay khi đã có `CodeTransform` và factory lifting. Ngược lại, không nên ép một phép xóa toàn method xuống `CodeTransform`.

## 9. Mở rộng: `atStart`, `atEnd` và transform có trạng thái

Ngoài hàm xử lý từng element (`accept`), transform hỗ trợ **hook vòng đời**:

- `atStart(builder)`: chạy trước khi xử lý các member elements của một cấu trúc.
- `accept(builder, element)`: xử lý từng element.
- `atEnd(builder)`: chạy sau khi xử lý xong các element.

Ví dụ tình huống cần `atStart`: chèn một instruction đầu method body trước các instruction đã có. Tình huống cần `atEnd`: sau khi quét class, bổ sung attribute chưa thấy hoặc hoàn tất thao tác gom thông tin. Các hook này phải được áp dụng đúng cấp element và cần cân nhắc label/stack maps khi thêm code.

Mẫu sau chỉ **minh họa tổ chức stateful transform** chứ không phải file Java độc lập:

```java
CodeTransform countReturns = CodeTransform.ofStateful(() ->
        new CodeTransform() {
            private int count;

            @Override
            public void accept(CodeBuilder builder, CodeElement element) {
                if (element instanceof ReturnInstruction) {
                    count++;
                }
                builder.with(element);
            }

            @Override
            public void atEnd(CodeBuilder builder) {
                System.out.println("returns=" + count);
            }
        });
```

`CodeBuilder`, `CodeElement`, `ReturnInstruction` và `CodeTransform` là các API đã được import trong một class/method bên ngoài đoạn trên. Mỗi lần tái sử dụng transform qua `ofStateful(supplier)`, supplier tạo implementation có **state riêng** cho lượt traversal. Điều đó tránh rò rỉ biến đếm giữa các method/class khi cùng một instance transform được nâng lên và áp dụng nhiều lần.

Không nên dùng một biến instance `count` chung không kiểm soát nếu transform có khả năng tái sử dụng trong nhiều luồng hoặc nhiều method. `AtomicInteger` trong ví dụ mục 7 là bộ đếm **cố ý dùng trong một lần chạy thử trên đúng một method được chọn**, không phải kiến trúc stateful tổng quát cho một agent production.

Ngoài `ofStateful`, các loại transform có factory tiện ích `endHandler(...)`, `dropping(...)` (ở loại hỗ trợ) và `ACCEPT_ALL`. Dùng chúng khi logic đơn giản để tránh tự viết boilerplate xử lý tất cả elements.

## 10. Khi cần biến đổi bytecode trong Java agent

Class-File API tạo class bytes, còn `java.lang.instrument` quyết định **thời điểm JVM đưa bytes cho agent** và cách agent đăng ký với JVM.

Luồng tích hợp:

```text
premain/agentmain
   |
   +--> instrumentation.addTransformer(...)
                |
                v
       ClassFileTransformer.transform(...)
                |
                v
       ClassFile.of().parse(classfileBuffer)
                |
                v
       ClassTransform (có thể lift MethodTransform/CodeTransform)
                |
                v
       ClassFile.transformClass(...) -> byte[]
                |
                v
       return new bytes cho JVM
```

**Mẫu callback tích hợp (trích đoạn thuộc một class `ClassFileTransformer`; chưa bao gồm agent, manifest hay đăng ký):**

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    try {
        ClassFile cf = ClassFile.of();
        ClassModel model = cf.parse(classfileBuffer);
        return cf.transformClass(model, combined);
    } catch (RuntimeException failure) {
        System.err.println("Transformation failed: " + failure);
        return null;
    }
}
```

Trong đoạn này biến `combined` là một `ClassTransform` đã được xây dựng hợp lệ và nằm trong phạm vi class/instance bao quanh. Cũng phải có các import/bối cảnh triển khai đầy đủ; **đây không phải chương trình tự chạy**.

Những điểm cần nhớ:

- `className` ở dạng nội bộ `"demo/Target"`, không phải `"demo.Target"`; có thể `null` ở một số tình huống.
- `return null` nghĩa là **không thay bytecode ở callback này**; không có nghĩa chặn transformer khác.
- Trả mảng mới chỉ khi có biến đổi phù hợp; không sửa trực tiếp `classfileBuffer` của JVM.
- Agent dùng Class-File API chuẩn phải chạy trên JVM đủ mới để cung cấp API; không thể đưa class đã compile với JDK 24 vào JVM 17 rồi mong agent load được.
- Với retransform/redefine, JVM có giới hạn về các thay đổi cấu trúc lớp (ví dụ không tự do thêm/xóa method); vì vậy **bước xóa `debug`** trong ví dụ offline **không phải** phép đổi có thể áp dụng tùy ý lên class đã load.
- Đừng để instrumentation của agent gây recursion vô hạn khi agent vô tình instrument các lớp hỗ trợ chính nó.
- Nếu dùng classfile bytes để nạp vào hệ thống thật, cần kiểm tra class version, dependency, module access, bytecode verifier và hành vi ứng dụng.

Tích hợp như trên biến `ClassTransform` thành **công cụ bên trong** `ClassFileTransformer`, chứ không làm hai loại interface trở thành một.

## 11. Kiểm tra tính hợp lệ và giới hạn thực tế

### 11.1. `verify` là bước cần nhưng chưa đủ

```java
boolean verified = ClassFile.of().verify(transformedBytes).isEmpty();
```

Đây là đoạn minh họa với `transformedBytes` đã được tạo. `verify` kiểm tra class bytes theo các quy tắc xác minh do API cung cấp, nhưng **không bảo đảm hành vi nghiệp vụ đúng**: bạn vẫn cần test class thực tế, gọi method và xác nhận kết quả.

Khi phép biến đổi ảnh hưởng stack map frames, branches, exception tables hay constant pool, cần hiểu cách builder xử lý chúng và options trong `ClassFile`. Những class mới sửa có thể biên dịch từ source bình thường nhưng thất bại khi được JVM nạp nếu tạo sai class bytes.

### 11.2. Model là dữ liệu mô tả, không phải class đang thực thi

`ClassFile.of().parse(input)` không nạp `java.lang.Class<?>` vào JVM. Nó chỉ tạo model cho file bytes. `ClassFile.of().transformClass(model, transform)` trả bytes mới; nếu không ghi, không gửi cho class loader/agent, thì **không có thay đổi runtime**.

### 11.3. Giữ bytecode không đổi không có nghĩa giữ đúng mọi byte

Việc parse → build có thể làm thay đổi chi tiết biểu diễn, thứ tự constant pool, layout instruction hoặc metadata tùy lựa chọn builder/option, ngay cả khi hành vi logic được giữ nguyên. Không nên kiểm thử bằng cách bắt buộc `Arrays.equals(oldBytes, newBytes)` khi mục đích là **bảo toàn ngữ nghĩa**. Hãy kiểm tra phiên bản class, method/field cần giữ, verify, và hành vi.

### 11.4. Phải chủ động giữ phần tử khi viết callback

Ở cả ba loại transform, mặc định an toàn nhất là:

```java
builder.with(element);
```

Nếu có một nhánh để thay thế hoặc loại bỏ, hãy làm rõ tại nhánh đó. Khi viết `switch` trên `CodeElement`, phải cân nhắc các element mới được thêm trong những bản JDK sau. Không tự assume mọi loại instruction/attribute đều đã được liệt kê.

### 11.5. Chú ý method lọc được có nhiều overload

Điều kiện `m.methodName().stringValue().equals("value")` chọn **mọi method cùng tên**, kể cả overload khác descriptor. Nếu hệ thống có `value()` và `value(int)`, filter theo tên sẽ áp dụng cho cả hai. Khi cần chính xác, hãy lọc thêm **method descriptor** qua API của `MethodModel` tương ứng. Ví dụ bài này không có overload nên chỉ một method được chọn.

### 11.6. Không tự ý xóa phần tử liên quan control-flow

`NopInstruction` là bài tập dễ kiểm tra vì nó không thay operand stack. Nhưng drop `LabelTarget` hoặc `ExceptionCatch` chưa xem tham chiếu có thể phá control-flow; drop return/branch hoặc thay invoke instruction có thể sai stack effects. Cần hiểu `CodeModel`, `CodeBuilder`, stack maps và quy tắc JVM trước khi sửa sâu.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `package java.lang.classfile does not exist` | Dùng JDK 17 hoặc cũ hơn bản chuẩn | Dùng JDK 24+; kiểm tra `java -version`, `javac -version` |
| `--release 24` không được hỗ trợ | `javac` cũ hơn JDK 24 | Dùng JDK 24+ |
| `ClassTransform.andThen(codeTransform)` không biên dịch | Hai transform khác cấp | Lift CodeTransform sang ClassTransform trước |
| Kết quả thiếu method/attribute | Callback quên `builder.with(element)` | Có nhánh mặc định chuyển tiếp các element cần giữ |
| Đã có CodeTransform nhưng method không đổi | Không lift vào method/class hoặc filter sai | Dùng `transformingCode`, `transformingMethods` hoặc `transformingMethodBodies` |
| `debug` vẫn tồn tại | Pipeline không có `ClassTransform.dropping` hoặc filter tên sai | Kiểm tra `MethodModel.methodName()` |
| `removedNops=0` | Stage loại nop chạy **trước** stage thêm nop hoặc không có nop đầu vào | Xem thứ tự `andThen` |
| Class được verify nhưng hành vi sai | Logic biến đổi đúng cấu trúc nhưng sai nghiệp vụ | Chạy test runtime/behavior |
| `VerifyError`/lỗi load ở JVM | Stack maps, label, class version, code không hợp lệ | Inspect classfile, verify, `javap`, kiểm tra version/branch |
| Runtime vẫn chạy class cũ | Đang dùng classpath `out` thay vì `patched` | Chạy `java -cp patched demo.Target` |
| `NoSuchMethodError` sau khi xóa method | Có code vẫn gọi method đã xóa | Kiểm tra reference và API compatibility trước khi drop |
| State bị chia sẻ giữa nhiều methods | Tái sử dụng transform có biến đếm mutable | Dùng `ofStateful` hoặc state riêng theo traversal |
| Agent chạy Java 17 không nạp được | Agent sử dụng API/class version Java 24+ | Chọn runtime tương thích hoặc công cụ bytecode khác |
| Muốn redefine class đã load nhưng xóa method | Giới hạn redefine/retransform | Tách quy trình build-time/offline và live instrumentation |

## 13. Bài tập tự kiểm tra

### Bài 1: chọn cấp transform

Muốn bỏ hẳn method `debug` trong class, nên dùng gì?

**Đáp án:** `ClassTransform`, vì `MethodModel` là `ClassElement`. `MethodTransform` xử lý phần tử **bên trong** method, không phải điều kiện xóa cả method.

### Bài 2: ghép hai CodeTransform

`A` thêm `nop` trước mỗi return; `B` bỏ mọi `nop`. `A.andThen(B)` tạo ra gì?

**Đáp án:** `B` nhận element mà `A` vừa phát, nên `nop` mới bị bỏ; return và các element khác vẫn được giữ nếu callbacks có `builder.with(element)`.

### Bài 3: đảo thứ tự

Vẫn hai phép trên, `B.andThen(A)` có giống `A.andThen(B)` không?

**Đáp án:** Không nhất thiết. Nếu input không có nop, B không bỏ gì; A thêm nop sau, do đó nop được giữ trong đầu ra.

### Bài 4: ghép khác cấp

Tại sao không viết `classTransform.andThen(codeTransform)`?

**Đáp án:** `ClassTransform.andThen` đòi một `ClassTransform`; `CodeTransform` thao tác `CodeElement`, không phải `ClassElement`. Phải nâng cấp bằng `ClassTransform.transformingMethodBodies(codeTransform)` hoặc qua `MethodTransform.transformingCode`.

### Bài 5: xử lý tất cả method bodies

Có sẵn `CodeTransform ct`. Viết một biểu thức áp dụng nó cho toàn bộ thân method trong một class.

**Đáp án:**

```java
ClassTransform result = ClassTransform.transformingMethodBodies(ct);
```

Đây là biểu thức trong bối cảnh có `ct` và import ClassTransform; chưa phải class độc lập.

### Bài 6: giữ cấu trúc method

Có sẵn `CodeTransform ct`, nhưng chỉ cần thay code, giữ các method attributes còn lại. Dùng factory nào?

**Đáp án:** `MethodTransform.transformingCode(ct)`. Nó xử lý `CodeModel` và chuyển tiếp phần tử method khác.

### Bài 7: nhận model và trả bytes

Sau khi `ClassFile.of().parse(bytes)`, có `ClassTransform t`. API nào tạo class file mới?

**Đáp án:**

```java
byte[] output = ClassFile.of().transformClass(
        ClassFile.of().parse(bytes), t);
```

Đây là trích đoạn dùng `bytes`, `t` có sẵn; output là mảng classfile mới, không tự được JVM cài đặt.

### Bài 8: JDK tối thiểu

Có thể biên dịch toàn bộ ví dụ với `javac` JDK 17 không?

**Đáp án:** Không. API `java.lang.classfile` chuẩn hóa ở JDK 24; bài tập yêu cầu JDK 24+.

### Bài 9: tính hợp lệ

Tại sao `cf.verify(newBytes).isEmpty()` vẫn chưa đủ để tuyên bố công cụ “đúng”?

**Đáp án:** Nó là kiểm tra theo API về bytes/classfile, không chứng minh logic phương thức, tương thích mọi caller, module/class loader và hành vi runtime. Cần thêm test ứng dụng và phù hợp mục tiêu.

### Bài 10: tích hợp agent

Một `ClassTransform` có tự chạy khi class được JVM load không?

**Đáp án:** Không. Cần caller gọi `ClassFile.transformClass`. Nếu muốn tự động transform khi JVM load lớp, phải đăng ký `java.lang.instrument.ClassFileTransformer` phù hợp và gọi Class-File API bên trong callback.

## 14. Tổng kết

- **ClassTransform / MethodTransform / CodeTransform** là ba tầng biến đổi tương ứng **ClassElement / MethodElement / CodeElement**.
- **`builder.with(element)`** là cách giữ phần tử; không phát phần tử là cách bỏ; phát phần tử mới là cách thay hoặc bổ sung.
- **`A.andThen(B)`** ghép **hai transform cùng cấp**, trong đó B xử lý đầu ra A, không phải bản sao input độc lập.
- **Lifting** đưa CodeTransform vào MethodTransform và ClassTransform bằng các factory, giúp tái sử dụng logic bytecode nhỏ trong cấu trúc lớn.
- **`ClassFile.transformClass(model, transform)`** tạo bytes class file mới. Nó không tự làm thay đổi một class đang chạy.
- **JDK 24+** là điều kiện đúng để dùng API chuẩn. Java 17 không có `java.lang.classfile`.
- Với bài toán instrumentation, **ClassFileTransformer** (callback của JVM) và **ClassTransform** (phép xử lý bytes) là hai trách nhiệm **khác nhau nhưng có thể phối hợp**.
- Khi viết transform thực tế, phải kiểm thử **bytes, verifier, hành vi và tương thích**, không chỉ thấy compile thành công.

## Tài liệu tham khảo chính thức

- [Oracle JDK 25: Package `java.lang.classfile` — đọc, lifting và composing transforms](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html).
- [Oracle JDK 25: `ClassFileTransform` — hợp đồng `accept`, `atStart`, `atEnd`, `andThen` và `ofStateful`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFileTransform.html).
- [Oracle JDK 25: `ClassTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html).
- [Oracle JDK 25: `MethodTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/MethodTransform.html).
- [Oracle JDK 25: `CodeTransform`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/CodeTransform.html).
- [Oracle JDK 25: `ClassFile` — parse, transformClass và verify](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html).
- [OpenJDK: JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484).
