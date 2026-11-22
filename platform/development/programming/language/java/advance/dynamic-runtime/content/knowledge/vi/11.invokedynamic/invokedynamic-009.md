# 11.9. Giới hạn của mã nguồn Java: gọi bootstrap trực tiếp và kiểm tra bytecode `invokedynamic` thật

Java có hai khái niệm nghe rất giống nhau nhưng **không đồng nghĩa**:

1. **Gọi một Java method được đặt tên `bootstrap`**, tự tạo `CallSite`, lấy `MethodHandle` bằng `dynamicInvoker()` và gọi bằng `invokeExact()`.
2. **Thực thi một instruction `invokedynamic` trong JVM bytecode**, nơi JVM dựa trên constant pool và thuộc tính `BootstrapMethods` của class file để liên kết (*link*) call site với một bootstrap method.

Chỉ **trường hợp thứ hai** mới là một *dynamic call site* của opcode `invokedynamic` theo Java Virtual Machine Specification (JVMS). `javac` không có cú pháp Java nguồn cho phép bạn chỉ định trực tiếp một bootstrap method tự tạo rồi phát opcode `invokedynamic` tùy ý như khi viết assembler. Bạn **có thể** khai báo và gọi một Java method có chữ ký giống bootstrap thật; nhưng chỉ lời gọi đó không khiến JVM gắn method này vào bảng `BootstrapMethods`.

Bài này chứng minh sự khác biệt bằng **hai chương trình Java 17+ chạy độc lập**, rồi dùng `javap -p -c -v` nhìn tận bytecode. Kết quả mong đợi là:

- `ManualBootstrapOnly.class`: có `invokestatic ... bootstrap`, `CallSite.dynamicInvoker` và `MethodHandle.invokeExact`; **không có opcode `invokedynamic`** và **không có thuộc tính `BootstrapMethods`**.
- `CompilerIndyDemo.class`: có **hai opcode `invokedynamic` thực**, được `javac` sinh cho method reference và nối chuỗi runtime; bảng `BootstrapMethods` trỏ tới **`LambdaMetafactory.metafactory`** và **`StringConcatFactory.makeConcatWithConstants`**, **không** trỏ tới method `ManualBootstrapOnly.bootstrap`.

Đây là khác biệt bản chất giữa **tự viết code gọi bootstrap** và **tạo class file chứa dynamic call site do JVM quản lý**.

## 1. Ba lớp cần tách: source Java, bytecode và JVM linkage

Hãy hình dung quá trình theo ba tầng:

```text
Tầng 1: mã nguồn Java
    |
    | javac biên dịch
    v
Tầng 2: class file (instructions + constant pool + attributes)
    |  - invokestatic, invokevirtual, invokeinterface, ...
    |  - invokedynamic nếu compiler lựa chọn phát sinh
    |  - CONSTANT_InvokeDynamic + BootstrapMethods khi có dynamic call site
    |
    | JVM nạp, xác minh và liên kết khi cần
    v
Tầng 3: runtime
    |  - với invokedynamic: JVM phân giải bootstrap specifier
    |  - gọi bootstrap method handle để lấy CallSite
    |  - dùng target của CallSite cho lời gọi động
    v
Giá trị trả về hoặc exception
```

Một method tên `bootstrap` ở **tầng source** chỉ là một Java method. Để nó trở thành *bootstrap method của một instruction `invokedynamic`*, **tầng class file** phải có một `CONSTANT_InvokeDynamic` tham chiếu tới mục bootstrap tương ứng, và instruction phải chỉ vào symbolic reference đó.

Cả hai tình huống đều có thể dùng `MethodHandle` và `CallSite`, nhưng luồng liên kết khác nhau:

| Câu hỏi | Gọi bootstrap trực tiếp bằng Java | Dynamic call site thật |
| --- | --- | --- |
| Ai gọi bootstrap? | Chính code Java gọi method như mọi method khác | JVM gọi bootstrap method handle khi liên kết instruction |
| Lệnh bytecode tại điểm gọi bootstrap | Thường `invokestatic` nếu là static method | Một **instruction `invokedynamic`** trỏ vào constant pool |
| Ai cung cấp `Lookup`, tên, `MethodType`? | Code Java tự tạo/truyền | JVM lấy thông tin caller, tên và descriptor từ call site specifier |
| `CallSite` được dùng thế nào? | Code nhận object và tự gọi `getTarget()` hoặc `dynamicInvoker()` | JVM liên kết `CallSite` với dynamic call site |
| Có cần `BootstrapMethods` attribute? | **Không**, chỉ vì gọi helper | **Có**, nếu class file chứa `CONSTANT_InvokeDynamic` |
| Có liên kết theo từng occurrence opcode? | Không; chỉ có các lời gọi Java bình thường | Có, JVM lưu kết quả linkage cho dynamic call site |
| Có thể chỉ dùng source Java thông thường để chỉ định custom opcode? | Không | Cần compiler/generator/transformer bytecode tạo cấu trúc class file |

Điều này giải thích vì sao một chương trình in `"bootstrap-called"` vẫn **không chứng minh** có `invokedynamic`. Dòng log chứng minh Java method đã chạy, không chứng minh JVM tự gọi nó do xử lý opcode.

## 2. `invokedynamic` là instruction, không phải cú pháp Java thông thường

JVM có nhiều opcode gọi method, trong đó:

| Instruction | Ý nghĩa điển hình | Đặc điểm |
| --- | --- | --- |
| `invokestatic` | Gọi static method | Chủ yếu dựa vào class và method reference |
| `invokevirtual` | Gọi virtual instance method, hoặc opcode cho lời gọi signature-polymorphic của `MethodHandle.invoke`/`invokeExact` | Không tự biến thành `invokedynamic` vì callee mang tính động |
| `invokeinterface` | Gọi method được dispatch qua interface | Vẫn khác `invokedynamic` |
| `invokespecial` | Constructor, một số private/super method calls | Quy tắc riêng của JVM |
| **`invokedynamic`** | Gọi qua dynamically computed call site được bootstrap | Liên kết theo bootstrap specifier trong class file |

Ký hiệu `MethodHandle.invokeExact` nghe có vẻ “động”, và thực tế JVM có cơ chế đặc biệt cho signature-polymorphic method invocation. Nhưng **opcode tại lời gọi `invokeExact` vẫn là `invokevirtual`**. Đó là một lý do quan trọng phải nhìn vào bytecode, không suy đoán từ tên Java API.

Trong mã Java, nhiều cấu trúc cấp cao **có thể** dẫn tới bytecode `invokedynamic` do compiler chọn, ví dụ:

- Lambda expression hoặc method reference, thường được `javac` liên kết qua `LambdaMetafactory`.
- Nối chuỗi có dữ liệu runtime, thường dùng `StringConcatFactory` ở các bản `javac` hiện đại.
- Một số phương thức do compiler sinh cho `record`, có thể đi qua `ObjectMethods.bootstrap`.

**Không phải mọi biểu thức trông “động” đều sinh `invokedynamic`.** Một lời gọi interface bình thường dùng `invokeinterface`; một Java method được tên `bootstrap` vẫn có thể chỉ là `invokestatic`; một phép nối chuỗi hằng như `"Hello, " + "Java"` có thể được compiler gộp thành hằng và **không cần** dynamic concat site.

Hình dạng bytecode là chi tiết của compiler và class file thực tế. Lệnh `--release 17` xác định API/target release và class file tương ứng, nhưng **không buộc mọi bản compiler phải chọn chiến lược code generation giống hệt nhau** trong tất cả tình huống.

## 3. Ví dụ A: gọi bootstrap thủ công, nhưng class không có `invokedynamic`

Tạo file **`ManualBootstrapOnly.java`**. Chương trình cố ý tránh lambda, method reference và phép `+` nối chuỗi runtime để có một chứng cứ “âm tính” dễ quan sát.

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class ManualBootstrapOnly {
    public static String decorate(String text) {
        return "[".concat(text).concat("]");
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup caller, String name, MethodType type)
            throws NoSuchMethodException, IllegalAccessException {
        System.out.println("manual-bootstrap-entered");
        MethodHandle target = caller.findStatic(
                ManualBootstrapOnly.class, "decorate",
                MethodType.methodType(String.class, String.class));
        return new ConstantCallSite(target.asType(type));
    }

    public static void main(String[] args) throws Throwable {
        MethodType signature =
                MethodType.methodType(String.class, String.class);
        CallSite site = bootstrap(
                MethodHandles.lookup(), "apply", signature);
        MethodHandle invoker = site.dynamicInvoker();
        String value = (String) invoker.invokeExact("Ada");
        System.out.printf("manual=%s%n", value);
    }
}
```

### 3.1. Vì sao method `bootstrap` trông hợp lệ?

Nó nhận ba tham số thường gặp ở một bootstrap method cho dynamic call site:

```text
(MethodHandles.Lookup, String, MethodType) -> CallSite
```

Với một bootstrap thật, JVM cung cấp `Lookup` gắn với **class chứa instruction**, tên symbolic call site và `MethodType` tương ứng descriptor. Nếu class file khai báo thêm static bootstrap arguments, JVM cũng chuyển những giá trị đó theo bootstrap protocol.

Trong **ví dụ A**, `main` tự truyền:

```java
bootstrap(MethodHandles.lookup(), "apply", signature)
```

`MethodHandles.lookup()` được gọi từ code trong `ManualBootstrapOnly.main`, `"apply"` chỉ là chuỗi do người viết tự chọn, còn `signature` cũng được tạo bằng Java API. Không có bước nào yêu cầu JVM đọc một `CONSTANT_InvokeDynamic` để suy ra các giá trị đó.

Trong thân `bootstrap`:

1. `caller.findStatic(...)` tìm handle tới `decorate(String)`.
2. `target.asType(type)` bảo đảm handle có kiểu người gọi yêu cầu, khi conversion hợp lệ.
3. `new ConstantCallSite(...)` tạo một `CallSite` không thể thay đổi target sau khi khởi tạo.
4. `main` lấy `site.dynamicInvoker()`, rồi invoke handle như một object Java bình thường.

**Tạo một `ConstantCallSite` không tự phát sinh opcode `invokedynamic`.** Tương tự, `CallSite.dynamicInvoker()` là một Java API; nó không tự đăng ký một entry vào `BootstrapMethods`.

### 3.2. Kết quả chạy

Sau khi biên dịch ở mục 5, chạy:

```bash
java ManualBootstrapOnly
```

Stdout:

```text
manual-bootstrap-entered
manual=[Ada]
```

Đây là kết quả đã kiểm chứng trên chương trình biên dịch với `javac --release 17`.

Dòng `manual-bootstrap-entered` xuất hiện vì **`main` đã gọi trực tiếp Java method `bootstrap`**, không phải vì runtime liên kết một opcode `invokedynamic`.

### 3.3. Vì sao cố ý dùng `String.concat`?

Method `decorate` dùng:

```java
return "[".concat(text).concat("]");
```

thay vì:

```java
return "[" + text + "]";
```

Nếu dùng `+` với biến `text`, `javac` hiện đại có thể tự sinh `invokedynamic` để nối chuỗi. Khi ấy class manual có `invokedynamic` **do nối chuỗi**, dễ khiến người học ngộ nhận opcode đó liên quan tới helper `bootstrap`. Cách viết bằng `String.concat` giữ ví dụ A tập trung vào so sánh **direct bootstrap call** và **real indy**.

Tương tự, ví dụ dùng `System.out.printf("manual=%s%n", value)` thay vì `"manual=" + value` để tránh tạo thêm một dynamic string-concat site trong class cần kiểm tra.

## 4. Ví dụ B: không gọi bootstrap thủ công nhưng compiler thực sự phát `invokedynamic`

Tạo file thứ hai **`CompilerIndyDemo.java`** cùng thư mục với file đầu tiên:

```java
public final class CompilerIndyDemo {
    @FunctionalInterface
    interface Task {
        String apply(String text);
    }

    public static void main(String[] args) {
        Task task = ManualBootstrapOnly::decorate;
        System.out.printf("reference=%s%n", task.apply("Bob"));

        String input = args.length == 0 ? "Java" : args[0];
        String message = "Hello, " + input;
        System.out.printf("concat=%s%n", message);
    }
}
```

Chỉ có hai cấu trúc cần lưu ý:

1. **Method reference** `ManualBootstrapOnly::decorate`: ở cấu hình compiler đã thử, `javac` tạo một `invokedynamic` có bootstrap thuộc `LambdaMetafactory`. Dynamic call site này tạo implementation của functional interface `Task`. Sau khi object được tạo, `task.apply("Bob")` lại là lời gọi interface bình thường (`invokeinterface`).
2. **String concatenation** `"Hello, " + input`: `input` là biến runtime, nên compiler đã thử phát `invokedynamic` liên kết với `StringConcatFactory.makeConcatWithConstants`.

**Chương trình B không hề gọi `ManualBootstrapOnly.bootstrap`.** Bootstrap thực sự của hai instruction là các bootstrap do JDK cung cấp. `ManualBootstrapOnly.decorate` được tham chiếu như **implementation method** của method reference, không phải method bootstrap.

Điểm tinh tế: *method reference trỏ tới `decorate`* và *bootstrap trỏ tới `LambdaMetafactory.metafactory`* là hai loại method handle khác nhau trong constant pool. Không nên nhìn thấy tên `decorate` trong phần `BootstrapMethods` rồi kết luận nó là bootstrap method.

## 5. Biên dịch, chạy và đọc bytecode bằng JDK 17+

Giữ **cả hai file trong cùng thư mục** rồi chạy:

```bash
javac --release 17 ManualBootstrapOnly.java CompilerIndyDemo.java
java ManualBootstrapOnly
java CompilerIndyDemo
```

Stdout của chương trình thứ nhất:

```text
manual-bootstrap-entered
manual=[Ada]
```

Stdout của chương trình thứ hai:

```text
reference=[Bob]
concat=Hello, Java
```

Các giá trị này đã được kiểm tra bằng `javac --release 17` và `java`. Nếu muốn thay giá trị nối chuỗi runtime, có thể chạy `java CompilerIndyDemo JVM` để nhận kết quả `concat=Hello, JVM`; đó là một biến thể tùy chọn, không nằm trong stdout chuẩn phía trên.

### 5.1. Lệnh disassemble chính xác

Chạy:

```bash
javap -p -c -v ManualBootstrapOnly
javap -p -c -v CompilerIndyDemo
```

Giải nghĩa flags:

- `-c`: in instructions trong method code, ví dụ `invokestatic`, `invokevirtual`, `invokedynamic`.
- `-v`: in thông tin class file chi tiết, bao gồm constant pool, version và `BootstrapMethods`.
- `-p`: hiển thị mọi member, kể cả private; hữu ích khi điều tra method do compiler sinh.

Bạn cũng có thể ghi kết quả ra hai file văn bản để kiểm tra:

```bash
javap -p -c -v ManualBootstrapOnly > manual.txt
javap -p -c -v CompilerIndyDemo > compiler.txt
```

Bash/Linux/macOS, lọc những dòng đáng chú ý:

```bash
grep -nE 'invokedynamic|invokestatic.*bootstrap|invokeExact|BootstrapMethods|LambdaMetafactory|StringConcatFactory' manual.txt compiler.txt
```

PowerShell trên Windows:

```powershell
Select-String -Path manual.txt,compiler.txt -Pattern 'invokedynamic|invokestatic.*bootstrap|invokeExact|BootstrapMethods|LambdaMetafactory|StringConcatFactory'
```

**Cẩn thận khi đếm opcode:** một từ `invokedynamic` có thể xuất hiện ở **constant pool comment** và **instruction**. Muốn đếm số opcode thực sự trong bản disassembly, chỉ đếm các dòng *Code* có offset số và opcode, ví dụ `0: invokedynamic ...` hoặc `45: invokedynamic ...`; không đếm mọi chỗ có chuỗi `InvokeDynamic`.

### 5.2. Kết quả bytecode ở `ManualBootstrapOnly`

Trong phần `main`, những instruction đáng chú ý của bản biên dịch đã kiểm tra là:

```text
14: invokestatic  #66   // Method bootstrap:(Lookup;String;MethodType)CallSite;
19: invokevirtual #70   // Method java/lang/invoke/CallSite.dynamicInvoker:()MethodHandle;
26: invokevirtual #78   // Method java/lang/invoke/MethodHandle.invokeExact:(String)String;
```

Để dễ đọc, phần `//` ở trên đã **rút gọn descriptor** bằng tên kiểu thân thiện; file `javap` thật in descriptor JVM đầy đủ như `Ljava/lang/invoke/CallSite;`. Vị trí offset và số `#66`, `#70`, `#78` là của một lần biên dịch cụ thể, **có thể thay đổi** nếu JDK/compiler/source thay đổi. Opcode và ý nghĩa là thứ cần so sánh.

Kết luận từ lệnh disassemble đã kiểm tra:

```text
ManualBootstrapOnly:
  số instruction invokedynamic = 0
  số mục BootstrapMethods attribute = 0
  số lời gọi invokestatic tới bootstrap = 1
  số lời gọi invokevirtual tới MethodHandle.invokeExact = 1
```

Đây là bằng chứng chính xác rằng **`MethodHandles.lookup()` + `CallSite` + `invokeExact` không đồng nghĩa một instruction `invokedynamic`**.

Lưu ý: class file này vẫn có constant-pool entries để gọi helper `bootstrap` và các method của `java.lang.invoke`. Sự tồn tại của những Methodref đó **khác** với một `CONSTANT_InvokeDynamic` tham chiếu bootstrap specifier.

### 5.3. Kết quả bytecode ở `CompilerIndyDemo`

Trong `main`, bản biên dịch đã kiểm tra có hai instruction:

```text
0:  invokedynamic #7,  0   // InvokeDynamic #0:apply:()LCompilerIndyDemo$Task;
45: invokedynamic #34, 0   // InvokeDynamic #1:makeConcatWithConstants:(Ljava/lang/String;)Ljava/lang/String;
```

Các số constant pool và bytecode offsets **không phải phần bắt buộc phải giống** trên máy khác; tên caller/factory và opcode mới là trọng tâm. Trong class này, kiểm tra đã xác nhận:

```text
CompilerIndyDemo:
  số instruction invokedynamic = 2
  số thuộc tính BootstrapMethods = 1
  số bootstrap entries = 2
```

Hãy để ý đoạn method reference:

```java
Task task = ManualBootstrapOnly::decorate;
```

được thực hiện với `invokedynamic` để tạo functional object; sau đó:

```java
task.apply("Bob");
```

dùng `invokeinterface`, **không phải chính instruction `invokedynamic` thứ hai**. Instruction thứ hai đến từ biểu thức nối chuỗi `"Hello, " + input`.

Một method reference không biến **mọi lần gọi sau đó** thành một lượt bootstrap. Dynamic call site thường làm công việc liên kết phương thức/khởi tạo functional object, còn lời gọi vào functional interface sau đó có bytecode dispatch riêng.

## 6. Đọc `BootstrapMethods` và lần ngược tới instruction

Trong `javap -v CompilerIndyDemo`, sau code và các phần khác có thuộc tính `BootstrapMethods`. Hai bootstrap entries của bản kiểm tra có hình dạng rút gọn:

```text
BootstrapMethods:
  0: REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
     Method arguments:
       ... REF_invokeStatic ManualBootstrapOnly.decorate:(Ljava/lang/String;)Ljava/lang/String;
  1: REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
     Method arguments:
       ... Hello, \u0001
```

Dấu `...` ở đoạn này là **phần descriptor/constant-pool index được lược bớt để dễ nhìn**; muốn thấy bytecode đầy đủ, chạy đúng `javap -v` trên class thực tế. `\u0001` trong recipe là vị trí mà dynamic argument được đưa vào khi thực hiện nối chuỗi; nó không phải ký tự bạn phải tự gõ trong Java source.

Ở phần constant pool, cũng có các entry tương ứng như:

```text
#7  = InvokeDynamic  #0:...   // call site dùng bootstrap entry 0
#34 = InvokeDynamic  #1:...   // call site dùng bootstrap entry 1
```

Khi xem một instruction:

```text
0: invokedynamic #7, 0
```

thì `#7` là **chỉ số constant pool entry** kiểu `CONSTANT_InvokeDynamic`. Phần comment `InvokeDynamic #0:apply` mang chỉ số **bootstrap method entry 0**, không phải “constant pool index 0”.

Cách truy vết có thể áp dụng cho mọi class file:

1. Tìm **instruction `invokedynamic`** ở phần `Code`.
2. Lấy index constant pool mà instruction dùng.
3. Tìm entry `CONSTANT_InvokeDynamic` tương ứng trong constant pool.
4. Từ entry đó, lấy **bootstrap_method_attr_index**; đây là chỉ số zero-based trong mảng `BootstrapMethods`, không phải một bytecode offset.
5. Tìm entry tương ứng trong attribute `BootstrapMethods`.
6. Đọc bootstrap method handle (`REF_invokeStatic ...`) và các **bootstrap arguments**.
7. Đọc `NameAndType`/method descriptor của dynamic call site để hiểu signature mà JVM sẽ yêu cầu `CallSite` phục vụ.

Trong ví dụ B, cả hai bootstrap method handles đều trỏ tới API JDK, vì Java compiler đã chọn bootstrap cho method reference và string concat. Không có `BootstrapMethods` entry trỏ tới `ManualBootstrapOnly.bootstrap`, dù tên `bootstrap` xuất hiện trong chương trình A.

### Cảnh báo: chỉ có `BootstrapMethods` chưa đủ khẳng định tồn tại opcode `invokedynamic`

Từ class file hiện đại, attribute `BootstrapMethods` có thể còn phục vụ **dynamically-computed constants** (`CONSTANT_Dynamic`, hay *condy*). Vì vậy, nếu cần chứng minh một đoạn code **đã sử dụng opcode `invokedynamic`**, phải có **instruction `invokedynamic` thật** trong `Code` và mapping phù hợp.

Quy tắc xác minh chặt: **instruction → constant pool `InvokeDynamic` → bootstrap entry**, không chỉ search chữ `BootstrapMethods`.

## 7. JVM thực sự làm gì khi liên kết một `invokedynamic`?

Mô tả tổng quát cho dynamic call site:

```text
class file:
  Code: invokedynamic #callSiteEntry, 0
  constant pool: name + method descriptor + bootstrap entry index
  BootstrapMethods: bootstrap handle + static bootstrap arguments
                                      |
                                      v
JVM resolution / linkage:
  resolve bootstrap handle và các arguments
  tạo Lookup cho class chứa instruction
  tạo String name + MethodType từ call site specifier
  gọi bootstrap method handle
  xác minh kết quả là CallSite hợp lệ
  xác minh target.type() == descriptor của call site
  liên kết instruction với CallSite được chọn
                                      |
                                      v
runtime invocation:
  mỗi lần instruction chạy: thực thi target của CallSite
  theo signature và trạng thái CallSite liên quan
```

### 7.1. Ba tham số thường có: caller, name, type

Một mẫu bootstrap phổ biến:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) throws Throwable {
    // tìm/chế tạo một target MethodHandle phù hợp
    // trả về CallSite có target.type() khớp type
}
```

Đây là **mẫu API**, không phải chương trình độc lập và không có nghĩa `javac` sẽ tự liên kết tới method này.

- **`caller`**: lookup gắn với class chứa `invokedynamic` instruction. Nó mang các quyền lookup của ngữ cảnh caller theo đặc tả, không phải một lookup tùy tiện do consumer khai báo.
- **`name`**: tên symbolic call site được ghi ở constant pool, do compiler hoặc generator lựa chọn; không tự quyết định target member nếu bootstrap code không sử dụng nó.
- **`type`**: `MethodType` của call site, diễn đạt kiểu các đối số đi qua dynamic call và kiểu trả về.

Một bootstrap có thể nhận thêm **static bootstrap arguments** từ constant pool (chẳng hạn method handles, types, strings hoặc các constants được phép). Các arguments này phục vụ **liên kết**, khác với các **dynamic arguments** được truyền khi instruction được thực thi.

Ví dụ `LambdaMetafactory.metafactory` nhận thêm metadata về functional interface và implementation handle. `StringConcatFactory.makeConcatWithConstants` nhận thêm recipe/constants. Đó là lý do entry `BootstrapMethods` có phần `Method arguments`.

### 7.2. `CallSite` và type checking

Để linkage thành công, bootstrap phải trả kết quả hợp lệ, quy về một `CallSite` không null, và **type của target MethodHandle phải khớp chính xác** với method descriptor của dynamic call site. `target.asType(type)` có thể giúp tạo adapter tương thích trong bootstrap khi các chuyển đổi được hỗ trợ; nhưng compiler/generator vẫn phải cung cấp descriptor phù hợp.

Ba nhóm `CallSite` thường gặp:

- `ConstantCallSite`: target được xác lập một lần, không thay đổi sau khi tạo.
- `MutableCallSite`: target có thể thay đổi, với quy tắc visibility/synchronization riêng.
- `VolatileCallSite`: access tới target theo quy tắc volatile visibility.

`CallSite.dynamicInvoker()` tạo một `MethodHandle` có hành vi gọi current target của call site, rất hữu ích khi bạn thao tác CallSite như object Java. Nhưng **API đó không tự tạo thêm `invokedynamic` opcode** vào class đã biên dịch.

### 7.3. Linkage xảy ra khi nào, có chạy bootstrap đúng một lần không?

Theo quy tắc Java SE/JVMS, một dynamic call site được liên kết khi JVM cần thực thi instruction lần đầu. Sau khi liên kết thành công, instruction sử dụng CallSite đã được chọn mà **không lặp lại bootstrap khi gọi mỗi lần**.

Tuy nhiên, không nên viết bootstrap có side effect và dựa trên giả định **“method bootstrap Java chỉ có thể chạy đúng một lần tuyệt đối”**. Nhiều thread có thể cùng cố liên kết một site chưa được liên kết; runtime có thể thực thi bootstrap method handle ở nhiều thread đồng thời, sau đó **chọn một kết quả** để cài đặt cho dynamic call site. Các kết quả khác bị bỏ qua.

Nếu bootstrap ghi state toàn cục, tạo tài nguyên hoặc đăng ký side effect, nó cần xử lý concurrency và idempotency theo ngữ cảnh ứng dụng. Đây là khác biệt với một helper được gọi thủ công: số lần gọi helper trực tiếp phụ thuộc hoàn toàn vào code Java điều khiển nó.

### 7.4. Lỗi khi bootstrap/linkage thất bại

Nếu bootstrap không được resolve/invoke hợp lệ, kết quả không phải CallSite phù hợp hoặc target method type không khớp, JVM có thể báo **`BootstrapMethodError`** trong quá trình liên kết. Lỗi có thể có cause giúp truy nguồn. Một số lỗi thuộc họ `Error` phát sinh trực tiếp ở bước bootstrap/resolution được lan truyền theo quy tắc JVMS.

Đây **không giống** việc bạn tự gọi `bootstrap(...)` bằng Java rồi nhận một `NoSuchMethodException` hoặc `IllegalAccessException` theo chữ ký method. Lỗi direct helper call chịu quy tắc Java invocation bình thường; lỗi `invokedynamic` linkage được JVM xử lý theo bootstrap/linkage protocol.

Vì vậy, khi debug, cần xác nhận exception xuất hiện lúc **tạo thủ công `CallSite`**, hay lúc **JVM liên kết opcode `invokedynamic`**.

## 8. Vì sao `invokeExact`, `LambdaMetafactory` và `invokedynamic` dễ bị nhầm?

Một hình dung dễ sai:

```java
MethodHandle handle = ...;
handle.invokeExact(arg);
```

Nếu target của handle được chọn động, có phải code trên dùng `invokedynamic` không?

**Không phải chỉ dựa vào cách viết ấy.** `invokeExact` là phương thức signature-polymorphic. JVM dùng cơ chế kiểm tra kiểu đặc biệt cho nó, nhưng bytecode của lời gọi từ Java vẫn có opcode **`invokevirtual`**. Bản disassembly ví dụ A chứng minh điều này.

Một hình dung khác:

```java
Task task = ManualBootstrapOnly::decorate;
```

Với `javac` đã thử, **expression tạo method-reference object** sử dụng `invokedynamic` qua `LambdaMetafactory`. Trong bảng `BootstrapMethods`, implementation handle trỏ tới `ManualBootstrapOnly.decorate`, nhưng **bootstrap handle** trỏ tới `LambdaMetafactory.metafactory`. Việc method reference dẫn tới method `decorate` không biến `decorate` thành bootstrap method.

Với string concatenation:

```java
String message = "Hello, " + input;
```

compiler có thể chọn `invokedynamic` và `StringConcatFactory`; nhưng biểu thức `"Hello, " + "Java"` thuần hằng có thể chỉ là một `ldc` trỏ tới chuỗi đã gộp. Không dùng ví dụ chỉ có constants để kết luận compiler không hỗ trợ dynamic string concat.

### Bảng phân biệt theo tầng

| Code hoặc artifact | Kiểu quyền/cơ chế | Bằng chứng muốn tìm |
| --- | --- | --- |
| Gọi static helper tên `bootstrap` | Java method invocation | `invokestatic` |
| `CallSite site = new ConstantCallSite(handle)` | Java object/API | Constructor call + MethodHandle references |
| `site.dynamicInvoker().invokeExact(...)` | Signature-polymorphic MethodHandle invocation | `invokevirtual ... invokeExact` |
| Lambda/method reference do `javac` biên dịch | Compiler chọn linkage động | `invokedynamic` + `LambdaMetafactory` bootstrap entry |
| String concat runtime do `javac` biên dịch | Compiler chọn linkage động | `invokedynamic` + `StringConcatFactory` bootstrap entry |
| Tự định nghĩa custom dynamic call site ở bytecode | Bytecode generation/transform | `invokedynamic` + bootstrap entry trỏ đúng custom bootstrap |

## 9. Nếu thực sự muốn một `invokedynamic` gọi custom bootstrap thì làm sao?

**Mã nguồn Java thông thường không có statement hoặc expression cho phép viết:**

```text
invokedynamic "apply" (String)String bootstrap=ManualBootstrapOnly.bootstrap
```

Dòng trên là **ý tưởng minh họa**, không phải cú pháp Java và không thể đưa vào `javac` để mong tạo opcode. Để chỉ định **custom bootstrap method** cho một instruction, bạn cần một công cụ **phát sinh hoặc chỉnh class file**, ví dụ compiler cho một ngôn ngữ khác chạy trên JVM, framework bytecode generation hoặc thư viện ASM.

Một hình dạng logic của thao tác bằng ASM là:

```java
// Mảnh mã minh họa ASM, KHÔNG phải chương trình độc lập.
// mv là MethodVisitor từ org.objectweb.asm.
// Cần dependency ASM, class writer, method body và class loader phù hợp.
Handle bsm = new Handle(
        Opcodes.H_INVOKESTATIC,
        "ManualBootstrapOnly",
        "bootstrap",
        "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;"
                + "Ljava/lang/invoke/MethodType;)"
                + "Ljava/lang/invoke/CallSite;",
        false
);

// Trên operand stack phải có một tham số String tương ứng descriptor.
mv.visitInvokeDynamicInsn(
        "apply",
        "(Ljava/lang/String;)Ljava/lang/String;",
        bsm
);
```

Đây chỉ là **minh họa cấu trúc của một bytecode generator dùng ASM**, không phải chương trình Java hoàn chỉnh, không phải mã đã kiểm thử trong hai ví dụ chạy ở mục 3–5. Các tên `Handle`, `Opcodes`, `MethodVisitor` thuộc **thư viện ASM bên ngoài**, không phải Java standard library. Cần import tương ứng, thư viện phụ thuộc, method visitor hợp lệ, stack-map/max-stack đúng, đưa argument lên operand stack, lưu kết quả và nạp class thành công.

Điều quan trọng là `visitInvokeDynamicInsn` yêu cầu:

1. **Call-site name**, ví dụ `"apply"`.
2. **Call-site descriptor**, ví dụ `(Ljava/lang/String;)Ljava/lang/String;`.
3. **Bootstrap method handle**, ở đây tham chiếu tới `ManualBootstrapOnly.bootstrap`.
4. **Các static bootstrap arguments bổ sung** nếu thiết kế bootstrap đòi hỏi.

Khi class file sinh đúng được nạp và instruction thực thi, JVM có thể gọi bootstrap thông qua linkage protocol và dùng `CallSite` trả về. Khi ấy `javap -v` phải cho thấy **bootstrap entry thực sự trỏ tới `ManualBootstrapOnly.bootstrap`** và phần `Code` có instruction `invokedynamic`. Chỉ lúc đó mới có căn cứ nói **custom bootstrap đã được JVM sử dụng để link dynamic call site**.

Nếu dùng ASM trong project thật, chọn phiên bản ASM tương thích class file version, khai báo dependency chính thức và kiểm tra với bytecode verifier; **không nên dựa vào các package ASM nội bộ `jdk.internal.*`** của JDK vì không phải API được hỗ trợ ổn định.

## 10. Khi nào hai kiểu gọi bootstrap có thể trùng kết quả nhưng khác cơ chế?

Một source helper trực tiếp có thể trả đúng `String` như một custom indy site:

```text
direct Java:
  bootstrap(...) -> CallSite -> dynamicInvoker() -> "result"

real invokedynamic:
  [bootstrap specifier] -> JVM linkage -> CallSite -> instruction -> "result"
```

Giá trị cuối cùng giống nhau **không chứng minh đường đi giống nhau**.

Khác biệt có ảnh hưởng thực tế:

- **Đặc tả runtime**: `invokedynamic` lưu linkage trên occurrence opcode, không yêu cầu Java source giữ biến `CallSite`.
- **Bootstrap arguments**: JVM tạo các tham số từ class-file metadata; direct call tự dựng arguments và có thể đưa `Lookup` khác.
- **Quyền truy cập**: `Lookup` do JVM cung cấp gắn với caller class của instruction. Direct Java có thể tự truyền `MethodHandles.lookup()` từ class khác hoặc một lookup đã giảm quyền; kết quả `findStatic` có thể khác.
- **Thời điểm**: manual call chạy đúng nơi source gọi; real indy liên kết theo thời điểm runtime cần thực thi site, và có thể chịu cạnh tranh concurrent linking.
- **Kiểm tra descriptor**: real indy yêu cầu `CallSite` target type khớp descriptor đã ghi trong bytecode. Direct call có thể tự lấy CallSite rồi gọi không đúng type và nhận lỗi call-site của `MethodHandle`.
- **Đọc bytecode**: direct call nằm ở `invokestatic`; real indy nằm ở `invokedynamic` và có bootstrap metadata trong class file.

Một bài test chỉ xác minh `"manual=[Ada]"` hoặc `"reference=[Bob]"` là test kết quả chức năng. Để test **cơ chế** được dạy trong bài này, phải có test bytecode/constant pool riêng.

## 11. Checklist kiểm chứng trên một project Java thực tế

Khi bạn gặp thông tin “framework này dùng `invokedynamic`”, hãy làm theo quy trình:

1. **Xác định class và method thật** chứa call site dự định. Nếu chỉ có một helper `bootstrap` ở source, chưa đủ.
2. **Biên dịch trong cấu hình thực tế** (JDK, `--release`, flags và dependencies), tránh kết luận từ source khác với class đang chạy.
3. **Chạy `javap -c -v -p`** trên class thực tế; xác nhận major version khi thích hợp (`--release 17` thường tạo major version 61).
4. **Tìm instruction offset chứa `invokedynamic`**, không chỉ tìm chuỗi `InvokeDynamic` trong constant pool.
5. **Đọc `CONSTANT_InvokeDynamic`** của instruction để biết name, descriptor và bootstrap index.
6. **Đọc `BootstrapMethods` entry tương ứng** để biết bootstrap method handle và static arguments.
7. **Xác minh bootstrap owner**: `LambdaMetafactory`, `StringConcatFactory`, `ObjectMethods` hay custom method của framework?
8. **So với nguồn Java**: method reference hoặc string concatenation có thể tạo indy; một direct call helper không chứng minh custom bootstrap.
9. **Kiểm tra runtime**: call site có được thực thi không, có lỗi linkage hay không, các arguments có đúng kiểu không?
10. **Nếu xuất hiện `BootstrapMethodError`**, xem cause và descriptor/target type. Với direct Java helper, xem exception nơi method tự ném.
11. **Nếu dùng generated/transformed class**, đảm bảo bạn disassemble **đúng class file cuối cùng đã chạy**, không chỉ `.class` được biên dịch trước bước transform.
12. **Đừng dùng stdout bootstrap như bằng chứng duy nhất**: log có thể do Java code gọi trực tiếp, hoặc do compiler-generated site khác kích hoạt.

Các shell commands cụ thể ở mục 5 dùng được với classpath bình thường. Đối với multi-module project, thêm `--module-path`/classpath thích hợp cho việc biên dịch và chạy; `javap` vẫn cần được trỏ đúng đến class file/module đã tạo.

### Đếm opcode mà không nhầm với constant pool

Trong bản `javap -c -v`, một instruction có dạng offset số:

```text
45: invokedynamic #34, 0
```

còn constant pool có dạng:

```text
#34 = InvokeDynamic #1:#35
```

Cả hai cùng nói về `InvokeDynamic`, nhưng chúng **không phải hai instruction**. Nếu code parser/test chỉ search chuỗi `"invokedynamic"` không phân biệt ngữ cảnh, nó rất dễ đếm gấp đôi. Hãy lọc dòng có **bytecode offset** rồi đối chiếu với constant pool index.

## 12. Lỗi điển hình và cách sửa

| Nhận định / triệu chứng | Vì sao chưa đúng | Cách kiểm chứng hoặc sửa |
| --- | --- | --- |
| “Tôi có method `bootstrap` nên tôi đang dùng `invokedynamic`” | Method name không tạo opcode | `javap -c -v`; tìm instruction và bootstrap entry đúng |
| “`MethodHandle.invokeExact` là opcode `invokedynamic`” | `invokeExact` dùng `invokevirtual` signature-polymorphic | Xem opcode ở call site |
| “Có `CallSite` object nên JVM đã link dynamic call site” | CallSite cũng là Java object tạo thủ công | Kiểm tra `CONSTANT_InvokeDynamic` và `BootstrapMethods` |
| “Class có `BootstrapMethods` nên chắc có `invokedynamic`” | Có thể chỉ dùng `CONSTANT_Dynamic` | Tìm opcode thực sự trong phần `Code` |
| “Method `decorate` xuất hiện ở bootstrap arguments nên nó là bootstrap” | Nó có thể chỉ là implementation method của lambda | Xem bootstrap method handle của entry, không nhầm với static arguments |
| “Một phép `+` chuỗi luôn sinh indy” | Constant folding hoặc compiler strategy có thể khác | Dùng runtime variable và kiểm tra class sau compile |
| “Dùng `--release 17` thì mọi compiler đều sinh identical offsets/CP indexes” | Chiến lược/ordering code generation có thể khác | So opcode, descriptors và liên kết logic, không hardcode `#7`/offset |
| “Java source gọi bootstrap và JVM bootstrap truyền cùng `Lookup` trong mọi trường hợp” | Direct Java tự chọn lookup, JVM lấy caller của instruction | Xác minh lookup class/module ở đúng ngữ cảnh |
| “Bootstrap chắc chắn chỉ chạy đúng một lần ở mọi thread” | Có thể cạnh tranh linkage và nhiều invocations bootstrap cùng chạy | Bootstrap idempotent/thread-safe nếu có side effect |
| “`BootstrapMethodError` là exception của method target” | Nó thường liên quan linkage/validation bootstrap | Xem cause và bootstrap entry |
| “`task.apply` trong lambda luôn là indy” | Việc tạo functional object có thể là indy; gọi `apply` thường là `invokeinterface` | Disassemble từng method, đừng gom chung |
| “Cần custom indy thì gọi `LambdaMetafactory` trực tiếp là đủ” | Tự gọi factory tạo CallSite nhưng không phát instruction | Dùng bytecode emitter/transformer để tạo custom opcode |
| “Đã có opcode thì chắc đúng bootstrap owner” | CP entry có thể trỏ factory khác với kỳ vọng | Truy ngược `CONSTANT_InvokeDynamic` → `BootstrapMethods` |

Một lỗi rất dễ gặp khi thử viết custom bootstrap trong Java là chạy thẳng:

```java
CallSite site = bootstrap(
        MethodHandles.lookup(), "apply",
        MethodType.methodType(String.class, String.class));
```

Đoạn này là **Java code hợp lệ trong ngữ cảnh có method `bootstrap` tương ứng**, nhưng chỉ chứng minh bạn **có thể sử dụng `CallSite` API bằng tay**, không chứng minh đã tác động tới một opcode `invokedynamic`.

## 13. Câu hỏi tự kiểm tra có đáp án

1. **Method Java tên `bootstrap` có tự đăng ký với JVM không?** Không. Để trở thành bootstrap của indy site, class file phải có symbolic reference và bootstrap entry phù hợp.
2. **`MethodHandles.lookup()` gọi trong `main` và chuyển vào helper có giống hoàn toàn Lookup do JVM tạo cho mọi indy site không?** Không. Quyền và lookup class phụ thuộc ngữ cảnh caller; JVM lấy từ class chứa site.
3. **`new ConstantCallSite(handle)` có phát sinh bytecode indy không?** Không. Đây là Java object creation.
4. **`dynamicInvoker().invokeExact(...)` biên dịch ra opcode gì?** Lời gọi `invokeExact` dùng `invokevirtual`, không phải `invokedynamic`.
5. **Vì sao hai ví dụ phải tách file?** Để class manual thật sự có thể được xác minh không chứa `invokedynamic`, còn class compiler có hai opcode rõ nguồn.
6. **`ManualBootstrapOnly.bootstrap` có chạy khi chạy `CompilerIndyDemo` không?** Không trong ví dụ này. Method reference dùng `decorate`; JDK factories xử lý bootstrap.
7. **Mục `BootstrapMethods` của method reference trỏ tới đâu?** `LambdaMetafactory.metafactory`; implementation handle mới trỏ tới `ManualBootstrapOnly.decorate`.
8. **Nối chuỗi `"Hello, " + input` được compiler kiểm thử biến thành gì?** Một `invokedynamic` tới `StringConcatFactory.makeConcatWithConstants`.
9. **Nếu thay `input` bằng literal `"Java"` ngay trong phép nối chuỗi, có chắc vẫn tạo indy không?** Không. Compiler có thể constant-fold.
10. **Tại sao dùng `javap -c -v` chứ không chỉ chạy chương trình?** Vì output giống nhau không tiết lộ opcode hay bootstrap specifier.
11. **Có được xem `BootstrapMethods` là bằng chứng duy nhất của indy không?** Không; attribute còn có thể dành cho dynamic constants.
12. **`#7` trong `invokedynamic #7` và `#0` trong `InvokeDynamic #0:apply` là cùng chỉ số không?** Không; chỉ số đầu chỉ constant pool, chỉ số sau chỉ bootstrap method entry.
13. **Bootstrap của indy trả một CallSite có target type không khớp descriptor thì sao?** JVM không liên kết thành công và có thể báo `BootstrapMethodError`.
14. **Một dynamic call site bị invoke nhiều lần có bootstrap chạy mỗi lần không?** Không. Sau khi link thành công, site dùng kết quả đã liên kết; nhưng có thể có các invocation bootstrap song song trong lúc giải quyết cạnh tranh lần đầu.
15. **Muốn chỉ định `ManualBootstrapOnly.bootstrap` làm bootstrap thật của custom site thì làm gì?** Tạo hoặc biến đổi class file có `invokedynamic` cùng entry `BootstrapMethods` phù hợp, ví dụ bằng ASM hoặc compiler bytecode.
16. **Vì sao `task.apply("Bob")` không phải bằng chứng của opcode indy thứ hai?** Bởi lời gọi interface có thể là `invokeinterface`; trong bài này opcode indy thứ hai thuộc phép nối chuỗi.

## 14. Tài liệu chuẩn để đối chiếu

- [JVMS Java SE 17 — §6.5 `invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic): instruction format, operand stack và việc sử dụng call site.
- [JVMS Java SE 17 — §5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): bootstrap resolution, linkage, concurrency và validation.
- [JVMS Java SE 17 — §4.7.23 `BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23): cách lưu bootstrap references/arguments trong class file.
- [Java SE 17 — `java.lang.invoke` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html): timing và ngữ nghĩa dynamic invocation/linkage.
- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): target và dynamic invoker.
- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`/`invokeExact` là signature-polymorphic.
- [Java SE 17 — `LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): bootstrap cho lambda và method reference.
- [Java SE 17 — `StringConcatFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): bootstrap cho string concatenation.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): lệnh disassembler và các tùy chọn.

**Chốt bài:** **Tên method, object `CallSite` hoặc lời gọi `MethodHandle.invokeExact` không quyết định có `invokedynamic` hay không.** Bằng chứng phải nằm trong **class file thật**: `invokedynamic` instruction, entry `CONSTANT_InvokeDynamic` và `BootstrapMethods` trỏ đúng bootstrap owner. Gọi helper bootstrap bằng Java chỉ là mô phỏng việc tạo target/call site; custom bytecode linkage thật phải được compiler hoặc bytecode generator phát sinh.