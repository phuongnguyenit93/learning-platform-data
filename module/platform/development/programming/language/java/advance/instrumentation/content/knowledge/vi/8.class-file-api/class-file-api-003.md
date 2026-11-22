# `MethodModel`, `CodeModel` và chọn đúng phương thức bằng tên cùng descriptor

Khi xây dựng Java instrumentation agent hoặc một công cụ đọc/sửa bytecode, **chọn nhầm phương thức** có thể gây ra lỗi nghiêm trọng: sửa sai overload, sửa nhầm bridge method do compiler tạo ra, hoặc cố thay `Code` của một phương thức `abstract`. Java **Class-File API** giúp đọc cấu trúc `.class` dưới dạng model có kiểu rõ ràng. Ở cấp phương thức, hai model then chốt là **`MethodModel`** và **`CodeModel`**.

Quy tắc cần nhớ trước tiên:

> **Chọn phương thức trong class file bằng cả `methodName` và *method descriptor*.** Chỉ so sánh tên như `process` là chưa đủ, vì một class có thể có nhiều overload cùng tên; descriptor JVM còn chứa cả kiểu trả về.

Bài này hướng dẫn đọc `ClassModel.methods()`, tra cứu bằng tên và descriptor, đi từ `MethodModel` xuống `CodeModel`, xử lý trường hợp không có `Code` và áp dụng predicate lựa chọn vào pipeline biến đổi bytecode.

## 1. Phiên bản JDK và phạm vi API

API ở package **`java.lang.classfile`**, thuộc module `java.base`. Nó được giới thiệu dưới dạng preview trong JDK 22 (JEP 457), preview lần hai trong JDK 23 (JEP 466), và **được chuẩn hóa trong JDK 24 (JEP 484)**.

| JDK | Cách sử dụng |
|---|---|
| 17–21 | **Chưa có** `java.lang.classfile` công khai để biên dịch ví dụ này; dùng thư viện như ASM nếu cần xử lý class file trên các JVM này |
| 22–23 | API ở trạng thái **preview**, chữ ký/cách sử dụng có thể khác bản chuẩn; cần cấu hình preview tương ứng |
| **24+** | `java.lang.classfile` đã là API chính thức; các đoạn đọc model trong bài dùng **JDK 24** và không cần `--enable-preview` |

Ta vẫn có thể dùng `javac --release 17` để tạo **class file mục tiêu tương thích Java 17**, rồi dùng **chương trình phân tích chạy trên JDK 24** để đọc. Đây là hai việc khác nhau: **phiên bản bytecode được phân tích** và **JDK chạy công cụ phân tích**.

## 2. Cây model từ class đến code

Lược đồ:

~~~text
bytes của một tệp .class
          │
          ▼ ClassFile.of().parse(bytes hoặc Path)
      ClassModel
          │
          └── methods() : List<MethodModel>
                 │
                 ├── methodName() : Utf8Entry
                 ├── methodType() : Utf8Entry (JVM descriptor)
                 ├── methodTypeSymbol() : MethodTypeDesc
                 ├── flags() : AccessFlags
                 └── code() : Optional<CodeModel>
                                │
                                ├── CodeElement theo thứ tự
                                │   ├── Instruction (opcode JVM thực thi)
                                │   └── PseudoInstruction (label, line, ...)
                                ├── exceptionHandlers()
                                └── các attribute liên quan Code
~~~

| Model | Mô tả | Dùng khi |
|---|---|---|
| `ClassModel` | Một class file đã parse, gồm metadata, fields, methods và class attributes | Tìm các phương thức trong đúng class |
| `MethodModel` | Một method trong bảng `methods` của class file; chứa tên, descriptor, flags và phần tử method | **Chọn chính xác overload** và đọc thuộc tính cấp method |
| `CodeModel` | Nội dung thuộc tính `Code` của một method; là chuỗi các `CodeElement` có thứ tự | Phân tích hoặc biến đổi lệnh bytecode |
| `Instruction` | Một lệnh JVM thực sự, có `opcode()` | Phân biệt opcode với label và metadata |
| `ClassTransform`/`MethodTransform`/`CodeTransform` | Các phép biến đổi ở cấp class/method/code | Chỉ đưa phương thức đã chọn vào pipeline cần sửa |

`ClassModel.methods()` cho danh sách `MethodModel`. **`MethodModel` không chính là `CodeModel`**: tên, flags và descriptor nằm ở cấp method, còn thân bytecode (nếu tồn tại) nằm trong `CodeModel`.

`ClassFile.parse(...)` dựng model để **phân tích bytes**, không gọi `main`, không tự thực thi code trong `.class`, cũng không phải là `ClassLoader#defineClass`. Model có thể được parse/làm giàu dữ liệu một cách lười (*lazy*), vì thế lỗi dữ liệu malformed vẫn có thể xuất hiện khi truy cập sâu một element.

## 3. Đọc `MethodModel` đúng kiểu dữ liệu

API JDK 24 của `MethodModel` có các accessor:

~~~java
Utf8Entry methodName();
Utf8Entry methodType();
MethodTypeDesc methodTypeSymbol();
Optional<CodeModel> code();
AccessFlags flags();
~~~

Đây là **các chữ ký mô tả API**, không phải một class Java tự chạy. Chú ý: `methodName()` và `methodType()` trả **`Utf8Entry`**, không phải `String`. Có thể lấy nội dung string bằng `.stringValue()` hoặc so sánh trực tiếp với chuỗi nhờ `.equalsString(...)`:

~~~java
boolean sameName = method.methodName().equalsString("calculate");
boolean sameDescriptor = method.methodType().equalsString("(I)I");

if (sameName && sameDescriptor) {
    // Đây là đúng method có name + descriptor được yêu cầu.
}
~~~

Trong đoạn này, `method` là một `MethodModel` đã lấy từ `ClassModel.methods()`. `equalsString` tránh phải xây `String` trung gian chỉ để so sánh; `stringValue()` phù hợp để hiển thị log.

Nếu muốn làm việc với descriptor có cấu trúc thay vì một string:

~~~java
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc wanted = MethodTypeDesc.ofDescriptor("(I)I");
boolean matches = method.methodName().equalsString("calculate")
        && method.methodTypeSymbol().equals(wanted);
~~~

Đây cũng là **đoạn minh họa bên trong method**; cả `method` lẫn `wanted` phải ở scope phù hợp. `MethodTypeDesc.ofDescriptor` giúp biểu diễn descriptor dưới dạng symbolic method type, và từ symbolic descriptor có thể gọi `.descriptorString()` để xuất về chuỗi JVM.

## 4. Method descriptor JVM là gì?

Descriptor của một method có cấu trúc:

~~~text
(kiểu_tham_số_1 kiểu_tham_số_2 ...) kiểu_trả_về
~~~

**Không có dấu phẩy, dấu cách, tên tham số, tên package kiểu Java hoặc từ khóa `public`/`static`.** Descriptor lưu trong class file chứa **tất cả kiểu tham số và kiểu trả về**, trong khi quy tắc overload ở *Java source* dựa trên danh sách tham số (không chỉ khác kiểu trả về).

Các ký hiệu nền tảng:

| Java | Descriptor |
|---|---|
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` (chỉ dùng ở vị trí trả về) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |

Ví dụ:

| Khai báo Java | Tên method trong `.class` | Descriptor |
|---|---|---|
| `int calculate(int x)` | `calculate` | `(I)I` |
| `long calculate(long x)` | `calculate` | `(J)J` |
| `String calculate(String s)` | `calculate` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `void log(String s, int n)` | `log` | `(Ljava/lang/String;I)V` |
| `String[] copy(String[] a)` | `copy` | `([Ljava/lang/String;)[Ljava/lang/String;` |
| `void accept(int[][] data)` | `accept` | `([[I)V` |
| `static void main(String[] args)` | `main` | `([Ljava/lang/String;)V` |
| Constructor không tham số | `<init>` | `()V` |
| Static initializer | `<clinit>` | `()V` |

Tên object dùng dấu gạch chéo `/` theo **internal name** bên trong `L...;`; không dùng `Ljava.lang.String;`. Số chiều mảng được thể hiện bằng số dấu `[`.

Ví dụ sai thường gặp:

~~~text
Sai:   calculate(int):int
Sai:   calculate(I):I
Sai:   calculate(Ljava.lang.String;)Ljava.lang.String;
Đúng:  calculate(I)I
Đúng:  calculate(Ljava/lang/String;)Ljava/lang/String;
~~~

Ký hiệu cuối trong dòng `Đúng` là **tên + descriptor để người đọc nhìn**, không phải một chuỗi descriptor duy nhất. Khi gọi API, hãy truyền `name = "calculate"` và `descriptor = "(I)I"` thành **hai đối số riêng**.

## 5. Vì sao phải so sánh cả tên lẫn descriptor?

Một class hợp lệ có thể có nhiều `MethodModel` cùng trả lời `methodName().equalsString("calculate")`:

~~~java
public static int calculate(int value) { return value + 1; }

public static long calculate(long value) { return value + 2L; }

public static String calculate(String value) {
    return "[" + value + "]";
}
~~~

Cả ba đều mang tên `calculate`, nhưng descriptor lần lượt là:

~~~text
(I)I
(J)J
(Ljava/lang/String;)Ljava/lang/String;
~~~

Nếu code instrument chỉ làm:

~~~java
model.methods().stream()
        .filter(method -> method.methodName().equalsString("calculate"))
        .findFirst();
~~~

thì nó **chọn phần tử đầu tiên phù hợp theo thứ tự trong class file**, có thể không phải overload mà bạn định sửa. `findFirst()` không cung cấp quy tắc nghiệp vụ để chọn overload đúng.

**Luôn gắn điều kiện tên với descriptor**:

~~~java
model.methods().stream()
        .filter(method -> method.methodName().equalsString("calculate")
                && method.methodType().equalsString("(I)I"))
        .findFirst();
~~~

Với class file hợp lệ, cặp **tên + descriptor** xác định một method duy nhất trong một class; khi thực hiện instrumentation, vẫn nên kiểm tra **số lượng kết quả = 1** và báo rõ lỗi khi thiếu target, thay vì âm thầm bỏ qua. Không dùng “tên + số tham số” thay thế descriptor: hai overload có cùng số tham số nhưng khác kiểu vẫn khác method.

## 6. Thực hành JDK 24: parse `.class` và chọn chính xác overload

Bài thực hành dùng **ba file Java độc lập** với tên/class đúng nhau. Dùng JDK **24 hoặc mới hơn** để chạy `InspectMethods`; riêng `Sample` và `Contract` được biên dịch với `--release 17` để chứng minh API có thể đọc class file phiên bản cũ.

Cấu trúc:

~~~text
classfile-lab/
├── Sample.java
├── Contract.java
├── InspectMethods.java
└── out/                 sinh ra trong lúc biên dịch
~~~

### 6.1. `Sample.java`

~~~java
public final class Sample {
    public static int calculate(int value) {
        return value + 1;
    }

    public static long calculate(long value) {
        return value + 2L;
    }

    public static String calculate(String value) {
        return "[" + value + "]";
    }

    public static int combine(int left, int right) {
        return left + right;
    }
}
~~~

Ba overload khác nhau bởi kiểu tham số, đồng thời có descriptor tương ứng với kiểu trả về. `Sample` có constructor mặc định do `javac` sinh, nghĩa là class file sẽ có cả `<init>()V` dù ví dụ không viết constructor tường minh.

### 6.2. `Contract.java`

~~~java
public interface Contract {
    int calculate(int value);
}
~~~

Phương thức interface này là `abstract` và **không có thân `Code`**. Nó sẽ phục vụ kiểm tra trường hợp `MethodModel.code()` trả `Optional.empty()`.

### 6.3. `InspectMethods.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeModel;
import java.lang.classfile.Instruction;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

public final class InspectMethods {
    private static boolean matches(
            MethodModel method, String name, String descriptor) {
        return method.methodName().equalsString(name)
                && method.methodType().equalsString(descriptor);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: InspectMethods <file.class> <name> <descriptor>");
        }

        String name = args[1];
        String descriptor = args[2];

        ClassModel model = ClassFile.of().parse(Path.of(args[0]));

        List<String> candidates = model.methods().stream()
                .filter(method -> method.methodName().equalsString(name))
                .map(method -> method.methodName().stringValue()
                        + method.methodType().stringValue())
                .sorted()
                .toList();

        for (String candidate : candidates) {
            System.out.println("candidate=" + candidate);
        }

        List<MethodModel> matches = model.methods().stream()
                .filter(method -> matches(method, name, descriptor))
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "Expected exactly one method, found " + matches.size());
        }

        MethodModel selected = matches.get(0);
        System.out.println("selected="
                + selected.methodName().stringValue()
                + selected.methodType().stringValue());

        Optional<CodeModel> code = selected.code();
        System.out.println("code=" + code.isPresent());

        code.ifPresent(body -> {
            long instructions = body.elementStream()
                    .filter(element -> element instanceof Instruction)
                    .count();
            System.out.println("instructions=" + instructions);
            System.out.println("handlers="
                    + body.exceptionHandlers().size());
        });
    }
}
~~~

**Phân tích cách chọn:**

1. `ClassFile.of().parse(Path.of(args[0]))` đọc class file thành `ClassModel`.
2. `model.methods()` lấy **toàn bộ methods**. Chúng ta in danh sách ứng viên cùng tên, **sắp xếp** để đầu ra demo ổn định và dễ kiểm tra.
3. `matches` so sánh **cả tên và descriptor** qua `Utf8Entry.equalsString`.
4. Nếu có đúng một match, ta nhận `MethodModel` mục tiêu.
5. `selected.code()` trả `Optional<CodeModel>`; vì vậy ví dụ **không gọi `get()` một cách mù quáng**.
6. `CodeModel.elementStream()` gồm `CodeElement` có thứ tự. Bộ lọc `element instanceof Instruction` chỉ đếm **opcode thật**, tránh đếm label, line number và pseudo-instruction như opcode.
7. `exceptionHandlers()` đọc danh sách entries xử lý ngoại lệ của `Code` attribute, độc lập với việc ta đếm instruction.

Với class file từ `javac`, các phương thức `abstract` hoặc `native` không có thuộc tính `Code`, nên `code()` trả empty. Trường hợp này hoàn toàn hợp lệ; đừng xem nó là lỗi parse.

### 6.4. Biên dịch và chạy

Từ thư mục `classfile-lab`, tạo `out`. Bash/Git Bash:

~~~bash
mkdir -p out
~~~

Hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Sau đó sử dụng **JDK 24+**:

~~~bash
javac --release 17 -d out Sample.java Contract.java
javac -d out InspectMethods.java
java -cp out InspectMethods out/Sample.class calculate '(I)I'
~~~

Chú ý: `--release 17` **chỉ áp dụng cho `Sample` và `Contract`**. Nếu thêm `--release 17` khi biên dịch `InspectMethods`, Java compiler sẽ báo không tìm thấy package `java.lang.classfile`, vì nó chỉ là API chuẩn từ JDK 24.

**Đầu ra mong đợi** khi thực hành bằng `javac` JDK 24 và class mẫu phía trên:

~~~text
candidate=calculate(I)I
candidate=calculate(J)J
candidate=calculate(Ljava/lang/String;)Ljava/lang/String;
selected=calculate(I)I
code=true
instructions=4
handlers=0
~~~

Giải thích `instructions=4`: `javac` thông thường biên dịch `return value + 1` thành các opcode `iload_0`, `iconst_1`, `iadd`, `ireturn`. Hai tham số `candidate` cùng tên nhưng khác descriptor vẫn hiện trong danh sách để bạn thấy điều kiện lọc chính xác.

Thử đổi descriptor mục tiêu:

~~~bash
java -cp out InspectMethods out/Sample.class calculate '(J)J'
~~~

`selected` sẽ là `calculate(J)J`. Số opcode có thể khác theo overload, nên không nên áp dụng kết quả `instructions=4` của `(I)I` cho mọi method.

Thử phương thức không có `Code`:

~~~bash
java -cp out InspectMethods out/Contract.class calculate '(I)I'
~~~

Đầu ra:

~~~text
candidate=calculate(I)I
selected=calculate(I)I
code=false
~~~

Ứng dụng **không in** `instructions` hay `handlers` khi `code()` rỗng. Đây là hành vi chủ động từ `Optional.ifPresent`, không phải do JVM có “0 instruction” trong method abstract.

Thử truyền `(D)D` để tìm một overload không tồn tại. Demo ném `IllegalArgumentException` với `Expected exactly one method, found 0` thay vì chọn nhầm `calculate(int)`.

## 7. Dùng `MethodTypeDesc` để tránh so descriptor sai định dạng

Với một nhóm method cố định, so sánh hai `Utf8Entry` bằng `equalsString` rất trực tiếp. Nếu tạo descriptor động, `MethodTypeDesc` hữu ích hơn:

~~~java
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc target =
        MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)Ljava/lang/String;");

boolean selected = method.methodName().equalsString("calculate")
        && method.methodTypeSymbol().equals(target);
~~~

Đoạn trên đặt **trong một method đã có biến `MethodModel method`**, không phải một chương trình độc lập. Cách này có hai ưu điểm: yêu cầu descriptor có cú pháp JVM hợp lệ và biến điều kiện thứ hai thành so sánh một symbolic method type. `method.methodTypeSymbol().descriptorString()` có thể được dùng để ghi descriptor vào log.

Một lỗi phổ biến là sử dụng biểu diễn **Java source** như `"(java.lang.String)java.lang.String"` làm đối số cho `MethodTypeDesc.ofDescriptor`. Factory này cần cú pháp JVM: `" (Ljava/lang/String;)Ljava/lang/String;"` **không có khoảng trắng đầu**.

Nếu muốn tạo descriptor từ các thành phần symbolically:

~~~java
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;

MethodTypeDesc target = MethodTypeDesc.of(
        ClassDesc.of("java.lang.String"),
        ClassDesc.of("java.lang.String"));
System.out.println(target.descriptorString());
~~~

Đây là đoạn code nằm trong method. Stdout là:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

`MethodTypeDesc.of(returnType, parameterTypes...)` nhận **kiểu trả về trước**, sau đó mới tới các kiểu tham số. Điều này khác với thứ tự hiển thị của descriptor string, nơi kiểu trả về nằm **sau dấu `)`**.

## 8. Tại sao không được bỏ kiểu trả về khi so khớp?

Ngôn ngữ Java không cho phép khai báo hai overload trong **cùng một class** chỉ khác kiểu trả về:

~~~java
int get();
String get();
~~~

Hai dòng trên là **minh họa mã Java không hợp lệ**, không phải snippet để biên dịch. Tuy nhiên, JVM xác định method bằng **tên + descriptor**, và descriptor bao gồm **return type**.

Trường hợp dễ gặp trong thực tế là **bridge method** do compiler tạo ra cho generic interface hoặc covariant return:

~~~java
interface Provider<T> {
    T get();
}

final class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "ok";
    }
}
~~~

Khi `javac` tạo `StringProvider.class`, class thường có cả:

~~~text
get()Ljava/lang/String;    // method thực hiện logic
get()Ljava/lang/Object;    // synthetic bridge, chuyển tiếp tới method trên
~~~

Phương thức thứ hai mang cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`. Nếu instrument chỉ theo tên `get`, bạn có thể chọn **bridge** thay vì method thực thi mong muốn. Nếu instrument cả hai không cân nhắc, bạn có thể tạo **hai lần đo** cho một lời gọi.

Để quan sát:

~~~bash
javac --release 17 -d out StringProvider.java
javap -p -v out/StringProvider.class
~~~

Đối với snippet trên, hãy lưu `Provider` và `StringProvider` vào **file `StringProvider.java`** (chúng đều không khai báo `public`); hoặc tách chúng thành hai file theo tên để biên dịch. Trong output `javap -v`, xem **name, descriptor và flags** của từng method. Khi chọn đối tượng cần sửa, chỉ dùng `get` là thiếu thông tin; phải chỉ ra `()Ljava/lang/String;` hay `()Ljava/lang/Object;`.

Ngoài bridge, generic information như `List<String>` thường nằm trong thuộc tính `Signature`, còn **descriptor JVM dùng kiểu đã xóa generic (*erasure*)**, ví dụ `Ljava/util/List;`. `CodeModel` và method descriptor mô tả bytecode đã được biên dịch, không khôi phục nguyên vẹn cú pháp nguồn Java.

## 9. `CodeModel` cho phép đọc những gì?

`MethodModel.code()` trả `Optional<CodeModel>`. Khi có `CodeModel`, nó mô tả thuộc tính **`Code`** trong `method_info`, trong đó chứa thông tin như mã lệnh, bảng exception handler và các thuộc tính phụ:

~~~text
MethodModel
    │
    ├── name, descriptor, access flags, attributes
    └── CodeModel (nếu có)
            ├── Instruction: opcode JVM thực thi
            ├── LabelTarget / LineNumber: pseudo-instruction
            ├── exceptionHandlers(): exception table entries
            └── Code attributes: ví dụ StackMapTable (truy cập attribute)
~~~

Cách đếm/hiển thị opcode:

~~~java
CodeModel body = selected.code().orElseThrow();

body.elementStream()
        .filter(element -> element instanceof Instruction)
        .map(element -> ((Instruction) element).opcode())
        .forEach(System.out::println);
~~~

Đây là **đoạn trích dùng biến `MethodModel selected` đã chọn ở bước trước**. `Instruction.opcode()` trả enum `Opcode` định danh lệnh. Kết quả in có thể thay đổi theo compiler hoặc code cụ thể; không nên cố đoán offset từ chỉ số phần tử trong stream.

Vì sao cần filter? **`CodeElement` không đồng nghĩa `Instruction`.** Label và line number có thể nằm giữa các opcode trong model; số element hoặc index trong `elementList()` **không phải PC offset bytecode**. Khi instrument, phải giữ nhãn nhảy, exception range, stack-map frame và code attribute nhất quán với bytes cuối cùng.

`body.exceptionHandlers()` đưa ra các mục bắt ngoại lệ trong `Code` attribute. Một phương thức không có `try/catch` có thể có 0 handler, nhưng một `finally` hoặc `try-with-resources` được biên dịch vẫn có thể sinh handler dù source trông không có `catch` trực tiếp.

Không nhầm `CodeModel.exceptionHandlers()` với `throws` khai báo trên method: `throws` được thể hiện bằng thuộc tính `Exceptions` ở cấp method, không phải các entry xử lý ngoại lệ tại runtime.

## 10. Từ predicate chọn method tới Class-File transformation

Khi đã có predicate **tên + descriptor**, có thể tái sử dụng nó với `ClassTransform.transformingMethodBodies(...)` để hướng phép biến đổi **chỉ vào `Code` của phương thức đích**:

~~~java
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;

ClassTransform selective = ClassTransform.transformingMethodBodies(
        method -> method.methodName().equalsString("calculate")
                && method.methodType().equalsString("(I)I"),
        CodeTransform.ACCEPT_ALL
);

byte[] rebuilt = ClassFile.of().transformClass(model, selective);
~~~

**Đây là một fragment đặt bên trong method đang có `ClassModel model`**, không phải chương trình độc lập. `CodeTransform.ACCEPT_ALL` là **identity code transform**: nó đi qua các code element mà **không cố tình thay đổi logic**. Ví dụ chỉ chứng minh cách áp dụng **đúng bộ lọc method** trong pipeline. Muốn thật sự chèn logging hoặc thay logic, bạn cần thay `ACCEPT_ALL` bằng một `CodeTransform` tương ứng, giữ mọi class-file invariant.

`ClassTransform.transformingMethods(Predicate<MethodModel>, MethodTransform)` là lựa chọn khi cần xử lý **cả method model**; `transformingMethodBodies` chỉ xử lý **Code** của những method mà predicate chọn, các element khác được chuyển qua builder theo hợp đồng API. Đối với method `abstract`/`native`, không có `Code` để biến đổi; nên kiểm tra `method.code().isPresent()` nếu nghiệp vụ yêu cầu bắt buộc tồn tại thân method.

Quy trình phù hợp với instrumentation:

1. Parse **đúng bytes của đúng class** (`ClassModel`), không dò mơ hồ theo tên đơn thuần.
2. Chọn method bằng **name + full JVM descriptor**, cân nhắc flags `ACC_BRIDGE` và `ACC_SYNTHETIC`.
3. Phân biệt method có `Code` với method không có `Code`.
4. Áp dụng `ClassTransform`/`MethodTransform`/`CodeTransform` chỉ cho mục tiêu đã định.
5. Xác minh bytes đầu ra (`ClassFile.verify(...)` trả danh sách lỗi nếu có) và kiểm thử class khi tải bằng JVM.
6. Nếu dùng làm Java agent: kiểm tra JVM hỗ trợ class file version của agent, không nạp code compiled JDK 24 vào JVM Java 17 rồi kỳ vọng API tồn tại.

Khi sửa method đang chạy bằng `Instrumentation.redefineClasses` hoặc `retransformClasses`, còn có các giới hạn riêng của **class redefinition** (không được tùy ý thêm/xóa fields/methods hoặc đổi signature) và yêu cầu transformer tương thích. Class-File API giúp xây bytes; nó **không tự cấp** instrumentation capabilities.

## 11. Đối chiếu bằng `javap` và xử lý khi không tìm thấy method

Các lệnh hữu ích:

~~~bash
javap -p -s out/Sample.class
javap -p -c out/Sample.class
javap -p -v out/Sample.class
~~~

- `-p`: hiển thị cả thành viên không public.
- `-s`: hiển thị **descriptor** JVM, hữu ích để copy chính xác vào predicate.
- `-c`: disassemble các opcode.
- `-v`: các chi tiết class file, flags, constant pool, attributes và code.

Nếu một phép tìm trả về 0 kết quả:

- Đảm bảo **đúng file `.class`**; class loader khác nhau có thể có class cùng tên nhưng bytes khác.
- In tất cả `methodName() + methodType()` trong đúng `ClassModel` để nhìn các overload thật.
- Kiểm tra kiểu `int` (`I`) so với `long` (`J`), `String` (`Ljava/lang/String;`) so với `String[]` (`[Ljava/lang/String;`).
- Kiểm tra `void` (`V`), ký hiệu return type, dấu `(` `)` và dấu `;` cuối kiểu reference.
- Nếu là method generic, dùng **descriptor sau erasure**, không chép phần type parameter `List<String>` từ source.
- Nếu tên là constructor, tìm **`<init>`** thay vì tên class Java; với static initializer, tên là **`<clinit>`**.

Nếu tìm được method nhưng `code()` rỗng, hãy xem flags. Method `abstract` hoặc `native` hợp lệ **không có `Code`**. Nếu tìm được 1 method nhưng công cụ vẫn sửa sai, hãy kiểm tra **cờ `ACC_BRIDGE`/`ACC_SYNTHETIC`**, đúng class loader, và predicate thực tế đã được sử dụng trong transform chưa.

## 12. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ lọc `methodName` | Chọn nhầm overload, bridge method | So khớp **cả tên và descriptor** |
| So `method.methodName().equals("calculate")` | `Utf8Entry` không phải String | Dùng `equalsString("calculate")` |
| Dùng `"(int)int"` làm descriptor | Không phải cú pháp JVM | Dùng `"(I)I"` |
| Dùng dấu chấm trong object descriptor | String không khớp | `Ljava/lang/String;` |
| Bỏ kiểu trả về khỏi descriptor | Mất thông tin định danh method ở bytecode | Descriptor phải có return type |
| So method generic bằng cú pháp `List<String>` | Không khớp descriptor đã erasure | Xem `javap -s`, dùng `Ljava/util/List;` |
| Gọi `method.code().get()` với method abstract | `NoSuchElementException` | Xử lý `Optional.empty()` |
| Coi mọi `CodeElement` là opcode | Đếm sai vì có pseudo-instruction | Filter `Instruction` |
| Coi thứ tự `methods()` là quy tắc chọn target | Dễ chọn sai khi compiler thay đổi thứ tự | Lọc duy nhất bằng name + descriptor |
| Cố biên dịch ví dụ API bằng `--release 17` | `java.lang.classfile` không tồn tại ở release 17 | Chạy công cụ phân tích trên **JDK 24+** |
| Thay code nhưng quên kiểm chứng bytes | Có thể lỗi verify/stack map/handler | Xác minh model/bytes và test trong JVM |
| Parse class nhưng tưởng code đã được thực thi | Đánh giá sai side effect | Phân biệt **parse file** với **load/execute class** |

## 13. Câu hỏi tự kiểm tra

1. **`MethodModel` và `CodeModel` khác nhau ở đâu?** `MethodModel` chứa định danh, flags và các element của method; `CodeModel` chứa phần thuộc tính `Code` nếu method có thân.
2. **Có 3 overload `calculate`. Chỉ so sánh tên đã xác định đúng method?** Chưa; cần so sánh cả descriptor.
3. **Descriptor của `int calculate(int)` là gì?** `(I)I`.
4. **Descriptor của `String calculate(String)` là gì?** `(Ljava/lang/String;)Ljava/lang/String;`.
5. **Vì sao `MethodModel.methodType()` không nên so bằng `(int)int`?** Vì nó mô tả **JVM method descriptor**, không phải cú pháp Java source.
6. **`MethodModel.code()` trả gì đối với interface abstract method?** `Optional.empty()`.
7. **Muốn đếm opcode trong `CodeModel`, có thể dùng `elementList().size()`?** Không; danh sách còn có pseudo-instruction.
8. **`StringProvider` có method `get()` trả `String` và synthetic bridge trả `Object`; nên chọn thế nào?** Theo **cả tên và descriptor**, đồng thời xét flags nếu cần.
9. **`java.lang.classfile` có trong JDK 17 không?** Không. API chính thức từ JDK 24.
10. **`ClassTransform.transformingMethodBodies` có nên lọc theo tên trần?** Không; sử dụng predicate name + descriptor để giữ các overload còn lại.
11. **Hai class loader có cùng class name. Chỉ biết class name đã đủ để quyết định bytes sẽ instrument?** Không; phải xác định **đúng class loader/định nghĩa** khi tích hợp với instrumentation.
12. **`ClassFile.verify(...)` trả danh sách rỗng có chứng minh logic ứng dụng đúng?** Không; đó là bước kiểm tra class file, vẫn cần test hành vi.

### Tài liệu chính thức

- [OpenJDK JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484).
- [Java SE 24 — `ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `transformClass`, `verify`.
- [Java SE 24 — `ClassModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html): `methods()`.
- [Java SE 24 — `MethodModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html): `methodName`, `methodType`, `methodTypeSymbol`, `code`.
- [Java SE 24 — `CodeModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html): `CodeElement` và bảng handler.
- [Java SE 24 — `Utf8Entry`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/constantpool/Utf8Entry.html): `stringValue`, `equalsString`.
- [Java SE 24 — `ClassTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `transformingMethods`, `transformingMethodBodies`.
- [Java SE 24 — `Instruction`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/Instruction.html): `opcode()`.
- [Java VM Specification — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html#jvms-4.3.3).

**Ghi nhớ:** `ClassModel` tìm **đúng class**; `MethodModel` chọn **đúng method bằng `name + descriptor`**; `CodeModel` chỉ có khi method có phần `Code`; còn `CodeTransform` mới là bước thực hiện thay đổi bytecode có kiểm soát. Để instrument an toàn, xác định đúng mục tiêu trước khi chỉnh bất kỳ instruction nào.