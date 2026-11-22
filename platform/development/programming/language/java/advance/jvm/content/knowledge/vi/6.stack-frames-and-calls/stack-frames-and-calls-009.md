# Ánh xạ lambda và nối chuỗi xuống bytecode theo phiên bản trình biên dịch

Cùng một source Java có thể sinh ra **bytecode khác nhau** tùy phiên bản `javac`, `--release`, công cụ build và chiến lược của compiler. Hai ví dụ rất điển hình là biểu thức **lambda/method reference** và phép **nối chuỗi bằng toán tử `+`**. Chúng cho thấy sự khác nhau giữa:

1. **Ngữ nghĩa source Java**: đoạn code phải cho kết quả gì theo Java Language Specification (JLS).
2. **Cách compiler hạ source xuống bytecode** (*lowering/desugaring*): dùng instruction nào, có sinh synthetic method hoặc `StringBuilder` hay không.
3. **Liên kết lúc chạy**: `invokedynamic` cùng bootstrap method liên kết call site.
4. **Triển khai tối ưu của JVM/JIT**: có thể tạo/ẩn class, inline, cache hoặc tạo mã máy theo cách riêng mà vẫn giữ đúng ngữ nghĩa được bảo đảm.

Mục tiêu: đọc được `javap -c -v -p`, phân tích `CONSTANT_InvokeDynamic_info` và `BootstrapMethods`, giải thích capture và functional interface, so sánh Java 8 với Java 9+/17 cho string concatenation, và không suy diễn một mẫu bytecode thành quy tắc bắt buộc cho mọi compiler.

## 1. Khung phiên bản: compiler, target class file và runtime là ba thứ khác nhau

| Phiên bản / lựa chọn | Lambda/method reference | Nối chuỗi `"a" + value` | Điều cần lưu ý |
| --- | --- | --- | --- |
| Java 7 trở về trước | Chưa có cú pháp lambda của Java 8 | Compiler thường dùng `StringBuilder` (hoặc một chiến lược tương thích khác) | JVM `invokedynamic` được bổ sung từ Java 7; có opcode không đồng nghĩa Java source đã có lambda |
| `javac` Java 8 | Thường dùng `invokedynamic` + `LambdaMetafactory` cho lambda/method reference | Thường dùng `new StringBuilder`, `append`, `toString` | Class file Java 8 có major version **52** |
| `javac` Java 9 trở lên với target hỗ trợ tính năng mới | Tiếp tục có thể dùng `invokedynamic` + `LambdaMetafactory` | Java 9 giới thiệu lowering bằng `invokedynamic` + `StringConcatFactory` (JEP 280) | Chiến lược, bootstrap arguments, bố trí synthetic methods có thể đổi theo compiler và bản build |
| Một `javac` hiện đại chạy `--release 8` | Có thể vẫn dùng `invokedynamic` cho lambda như Java 8 | `javac` thông thường sinh đường `StringBuilder` tương thích Java 8 | `--release 8` giới hạn ngôn ngữ/API/định dạng class file; **không biến compiler hiện đại thành đúng binary của javac 8** |
| `javac` hiện đại chạy `--release 17` | Có thể dùng `LambdaMetafactory` | Thường sinh `StringConcatFactory.makeConcatWithConstants` | Class file Java 17 có major version **61**, yêu cầu runtime đọc được phiên bản tương ứng |

**Chú ý:** đây là **các hành vi điển hình của OpenJDK `javac`**, không phải mệnh lệnh từ JLS rằng “mọi compiler phải tạo đúng opcode này”. Java source được chuẩn hóa về **ngữ nghĩa quan sát được**; JVM bytecode cũng có đặc tả riêng, nhưng compiler có nhiều lựa chọn biểu diễn hợp lệ.

Khi điều tra, ghi đủ bốn thông tin: `javac -version`; tùy chọn `--release` hoặc `-source`/`-target`; file `.class` thực sự được tạo ra; và `java -version` của JVM thực thi. Không lấy phiên bản runtime để suy ra chắc chắn phiên bản compiler đã tạo class.

## 2. Vì sao cần phân biệt các lệnh `invoke*`?

| Opcode | Ý nghĩa chính | Liên quan đến bài |
| --- | --- | --- |
| `invokestatic` | Gọi method static đã được liên kết; không có receiver instance | Compiler tạo helper static cho lambda hoặc gọi factory thường có thể dùng các method handle trỏ tới method static |
| `invokevirtual` | Gọi method instance class, có lựa chọn implementation theo runtime receiver | Lời gọi bên trong lambda có thể gọi method instance; chuỗi `StringBuilder.append` là invokevirtual |
| `invokeinterface` | Gọi method qua interface reference, chọn implementation phù hợp receiver | Gọi `IntUnaryOperator.applyAsInt` hoặc `Runnable.run` trên object hàm |
| `invokespecial` | Constructor, `super` và những lời gọi instance đặc biệt | `new StringBuilder; invokespecial <init>` trong lowering Java 8 |
| **`invokedynamic`** | Liên kết **call site** qua bootstrap method được mô tả trong class file | Điểm trung tâm của lambda/method reference và string concat hiện đại |

Không được đồng nhất **`invokedynamic` = “gọi phương thức ảo theo kiểu thực của đối tượng”**. `invokevirtual`/`invokeinterface` là một cơ chế khác. `invokedynamic` liên kết một `CallSite` có target `MethodHandle`; target đó có thể thực hiện nhiều loại thao tác do bootstrap quyết định.

Mỗi instruction `invokedynamic` trong `code[]` tham chiếu tới một entry loại `CONSTANT_InvokeDynamic_info` trong constant pool. Entry ấy dẫn tới một mục `BootstrapMethods` ở cấp class file và một `NameAndType` mô tả tên/descriptor của **dynamic call site**.

## 3. Đọc `CONSTANT_InvokeDynamic_info` và `BootstrapMethods`

Một cấu trúc khái niệm:

```text
code[] của method
  invokedynamic #N, 0
       |
       v
constant_pool[#N] = CONSTANT_InvokeDynamic_info
  ├── bootstrap_method_attr_index ───────┐
  └── name_and_type_index                │
         ├── tên call site               │
         └── descriptor call site        │
                                         v
                   BootstrapMethods[bootstrap_method_attr_index]
                     ├── bootstrap_method_ref
                     │     └── CONSTANT_MethodHandle_info
                     └── bootstrap_arguments[]
                           └── các constant pool entries
```

Trong tệp class, `CONSTANT_InvokeDynamic_info` có các trường `bootstrap_method_attr_index` và `name_and_type_index`. Chỉ số bootstrap trỏ tới **bảng BootstrapMethods**, khác với **index constant pool** được in ngay sau opcode. Số `#N` và số `#0` ở dòng `InvokeDynamic #0:...` **không phải** cùng một loại index.

Bootstrap method được JVM gọi trong quá trình liên kết call site, nhận các thông tin như `MethodHandles.Lookup`, tên call site, `MethodType` và các argument tĩnh. Nó trả về `CallSite` có target thích hợp. Sau khi liên kết, việc **thực thi dynamic call site** sử dụng target này với các **đối số động trên operand stack**.

Phân biệt ba mức dữ liệu:

- **Static bootstrap arguments**: được mô tả trong constant pool/`BootstrapMethods`; ví dụ method type và implementation method handle của lambda, hoặc concat recipe.
- **Dynamic call-site arguments**: giá trị thực trên operand stack khi instruction chạy; với capturing lambda, có thể là các giá trị được capture; với string concatenation, thường là các thành phần cần nối.
- **Đối số của lời gọi functional interface**: đến **sau** khi đã có object lambda, ví dụ `fn.applyAsInt(4)`; `4` không nhất thiết là argument của call site tạo lambda.

Đây là lý do hai instruction `invokedynamic` có thể trông giống nhau trong `javap` nhưng hoạt động rất khác nếu bootstrap methods khác.

## 4. Lambda expression: “tạo object hàm”, sau đó “gọi SAM” là hai bước

Một **functional interface** có một abstract method xét theo quy tắc Java; method này thường gọi là **SAM (single abstract method)**. Ví dụ `IntUnaryOperator` có `int applyAsInt(int operand)`.

Khi compiler nhìn thấy:

```java
int offset = 3;
IntUnaryOperator addOffset = x -> x + offset;
int answer = addOffset.applyAsInt(4);
```

Đây là **fragment minh họa**, giả sử đã import `java.util.function.IntUnaryOperator` và nằm trong method. Có thể tách thành:

1. Compiler kiểm tra lambda tương thích với target type `IntUnaryOperator`, xác định parameter/return type và biến capture.
2. Compiler tạo hoặc tham chiếu **implementation method** có body tương ứng (thường là method private static synthetic tên dạng `lambda$...`); đây là một **chiến lược của `javac`**, không phải tên bắt buộc theo JLS.
3. Bytecode đánh giá và đẩy biến capture `offset` lên operand stack rồi thực hiện **`invokedynamic`**; call site này tạo/trả về một object tương thích `IntUnaryOperator`.
4. Sau đó, `invokeinterface IntUnaryOperator.applyAsInt:(I)I` nhận object hàm và đối số `4` để chạy hành vi mà lambda cung cấp.

**Hai giai đoạn không nên gộp:** `invokedynamic` tại vị trí lambda thường **tạo/lấy function object**; `invokeinterface` tại vị trí `applyAsInt(4)` mới **gọi hàm**.

### Capturing và non-capturing

- `x -> x * 2` không cần đọc biến local bên ngoài: **non-capturing lambda**. Call site tạo function object thường có descriptor **không nhận capture argument**, ví dụ `()Ljava/util/function/IntUnaryOperator;`.
- `x -> x + offset` phải mang giá trị `offset` từ lexical scope: **capturing lambda**. Call site có thể có descriptor `(I)Ljava/util/function/IntUnaryOperator;`; `I` là kiểu capture `offset`.
- `IntUnaryOperator f = SomeClass::triple` có thể là **non-capturing method reference** trỏ tới method handle của `triple`, thường không cần compiler tạo helper `lambda$...` riêng.
- `instance::method` là **bound method reference**: receiver được đánh giá tại thời điểm tạo method reference và có thể là capture. Với receiver null, đánh giá bound reference có thể ném `NullPointerException` ngay lúc tạo.
- Với `ClassName::instanceMethod` dạng unbound method reference, receiver trở thành tham số khi gọi SAM, không phải capture sẵn một object cụ thể.

**Giá trị local được capture phải final hoặc effectively final.** Khi `offset` là primitive, lambda giữ giá trị đã capture, không “nhìn lại slot locals” của caller sau khi caller rời scope. Với một reference tới object mutable, lambda giữ reference; nó vẫn có thể nhìn thấy trạng thái **object** thay đổi sau đó. Không suy diễn capture theo Java là con trỏ tới một local slot đã hết vòng đời.

### Đừng dựa vào identity hay tên class của lambda object

Đặc tả không yêu cầu lambda được hiện thực bằng một anonymous class có tên cố định hoặc phải tạo một object mới ở mọi lần đánh giá non-capturing lambda. JVM có thể tái sử dụng instance, tạo hidden class hay tối ưu bằng JIT. Tránh kiểm thử `getClass().getName()`, class loader, tên synthetic methods, số lượng object hoặc `==` để suy ra “tính đúng” của lambda.

## 5. Vai trò của `LambdaMetafactory`

Trong OpenJDK `javac` điển hình, mục `BootstrapMethods` của lambda/method reference tham chiếu:

```text
REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
```

`LambdaMetafactory.metafactory` nhận thông tin về interface/SAM và method triển khai, rồi tạo call site có thể cho ra function object. Những tham số quan trọng về bản chất:

| Thông tin | Công dụng |
| --- | --- |
| `invokedType` (`MethodType` của call site) | Các kiểu capture đi vào dynamic call site và kiểu object functional interface trả về |
| `samMethodType` | Method type của SAM ở mức kiểu đã erasure/descriptor |
| `implMethod` (`MethodHandle`) | Implementation method được lambda object gọi, như synthetic helper hoặc method đích của method reference |
| `instantiatedMethodType` | Method type sau khi xét target functional interface/generics để kiểm tra và thích nghi kiểu |
| Tên SAM trên call site | Ví dụ `applyAsInt`, `run`, `apply` |

Không nhầm `samMethodType` với `instantiatedMethodType`: generic erasure có thể khiến hai kiểu khác nhau; implementation có thể cần cast, boxing/unboxing, widening hoặc bridge adaptation.

Một số trường hợp đặc biệt như lambdas **serializable**, marker interfaces hoặc bridge methods bổ sung có thể dùng `LambdaMetafactory.altMetafactory`. Không mặc định mọi `invokedynamic` trong một class đều dùng `metafactory`: nối chuỗi hiện đại thường có **bootstrap khác**.

## 6. Ví dụ Java 17 có thể chạy: lambda, capture và method reference

Tạo file **`LambdaTranslation.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LambdaTranslation {
    private static IntUnaryOperator plus(int amount) {
        return x -> x + amount;
    }

    private static int triple(int value) {
        return value * 3;
    }

    public static void main(String[] args) {
        int offset = 3;

        IntUnaryOperator capturing = x -> x + offset;
        IntUnaryOperator plain = x -> x * 2;
        IntUnaryOperator methodReference = LambdaTranslation::triple;
        IntUnaryOperator fromFactory = plus(5);

        System.out.println("capture=" + capturing.applyAsInt(4));
        System.out.println("plain=" + plain.applyAsInt(4));
        System.out.println("methodRef=" + methodReference.applyAsInt(4));
        System.out.println("factory=" + fromFactory.applyAsInt(4));
    }
}
```

Chạy với **JDK 17+** có compiler hỗ trợ `--release 17`:

```bash
javac --release 17 LambdaTranslation.java
java LambdaTranslation
javap -c -v -p LambdaTranslation
```

**Stdout của riêng `java LambdaTranslation`:**

```text
capture=7
plain=8
methodRef=12
factory=9
```

Giải thích:

- `capturing` nhận `offset = 3` và argument `4` nên có kết quả `7`.
- `plain` không dùng capture và nhân `4 * 2 = 8`.
- `methodReference` trỏ tới static method `triple`, kết quả `4 * 3 = 12`.
- `fromFactory` capture tham số `amount = 5` trong method `plus`, nên `4 + 5 = 9`.

### Dấu vết thường gặp trong `javap`

Đọc method `main` sẽ thấy các call sites dạng **`invokedynamic`** để tạo các function objects, rồi các invocation dạng **`invokeinterface`** tới `IntUnaryOperator.applyAsInt:(I)I` khi thực hiện phép tính.

Ví dụ dạng **lược đồ**, không phải output nguyên văn với indexes cố định:

```text
iload_1
invokedynamic #A, 0    // InvokeDynamic: applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
astore_2

invokedynamic #B, 0    // InvokeDynamic: applyAsInt:()Ljava/util/function/IntUnaryOperator;
astore_3

...                    // nạp lambda object và int 4
invokeinterface #C, 2 // IntUnaryOperator.applyAsInt:(I)I
```

Trong lược đồ, `iload_1` đại diện local chứa `offset`, còn `#A`/`#B`/`#C` là chỗ đứng cho constant pool indices thực tế. Vị trí locals/offset cụ thể phụ thuộc compiler; tập trung vào descriptor có **một capture argument** so với descriptor **không có capture**.

Dưới `BootstrapMethods`, có thể thấy `REF_invokeStatic LambdaMetafactory.metafactory`, `MethodType (I)I` và `REF_invokeStatic` trỏ tới implementation methods như `lambda$main$...` hoặc `triple`.

`javap -p` hiển thị các private/synthetic helpers; `javap -v` có thể hiển thị flags `ACC_SYNTHETIC`. Tên helper, số thứ tự lambda và thứ tự bootstrap entries **không ổn định như public API**.

### Vì sao ví dụ lambda cũng có `StringConcatFactory` khi compile `--release 17`?

Bốn câu `System.out.println("capture=" + ...)` còn chứa phép nối chuỗi với giá trị `int` động. Do đó **cùng một class** có thể chứa:

- `invokedynamic` dùng `LambdaMetafactory` để tạo lambda/method-reference object.
- `invokeinterface` để gọi SAM.
- `invokedynamic` dùng `StringConcatFactory` để nối nhãn với kết quả số.
- `invokevirtual` để gọi `PrintStream.println`.

Không đếm tất cả lệnh `invokedynamic` rồi kết luận có bấy nhiêu lambda. **Luôn lần theo từng bootstrap entry**.

## 7. Nối chuỗi trước Java 9: lowering thường dùng `StringBuilder`

Xét source:

```java
String result = "name=" + name + ", count=" + count;
```

Đây là **đoạn minh họa trong một method**. Trên `javac` Java 8 hoặc một `javac` hiện đại biên dịch với `--release 8`, bytecode điển hình có thể gồm:

```text
new java/lang/StringBuilder
dup
invokespecial java/lang/StringBuilder."<init>":()V
ldc "name="
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
aload_0
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
ldc ", count="
invokevirtual java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
iload_1
invokevirtual java/lang/StringBuilder.append:(I)Ljava/lang/StringBuilder;
invokevirtual java/lang/StringBuilder.toString:()Ljava/lang/String;
areturn
```

Đây là **chuỗi opcode mô phỏng không có offset hoặc constant pool index**, không khẳng định `javac` phải sinh cùng một chuỗi hoặc thứ tự append theo mọi phiên bản. Ý tưởng: xây một mutable builder, nối các thành phần theo ngữ nghĩa Java rồi lấy String kết quả.

Hạn chế của cách biên dịch này là **chiến lược nối chuỗi bị “nướng” vào bytecode**: class file có các lời gọi `StringBuilder.append` cụ thể. JVM/JIT vẫn có thể tối ưu builder/escape analysis, nhưng compiler đã quyết định hình dạng bytecode ngay khi build.

JEP 280 thay đổi chiến lược này để runtime có thêm quyền chọn cách nối chuỗi mà không cần thay source; nó **không** thêm một toán tử nối chuỗi mới trong ngôn ngữ Java.

## 8. Từ Java 9: `StringConcatFactory` và concat call site bằng `invokedynamic`

Với `javac` Java 9+ target phù hợp, compiler thường nạp các thành phần động lên operand stack và thực thi **một `invokedynamic`** cho đoạn concat. Bootstrap có thể là:

- `StringConcatFactory.makeConcat`: nối các dynamic arguments theo method type.
- `StringConcatFactory.makeConcatWithConstants`: dùng thêm **recipe** và constants từ `BootstrapMethods`; đây là lựa chọn rất thường thấy trong class file do `javac` Java 17 sinh.

Dạng lược đồ cho ví dụ `"name=" + name + ", count=" + count`:

```text
aload_0
iload_1
invokedynamic #N, 0
  // InvokeDynamic: makeConcatWithConstants:
  // (Ljava/lang/String;I)Ljava/lang/String;
areturn
```

Nếu recipe là “`name=<arg>, count=<arg>`” theo nghĩa mô tả, runtime dùng nó để ghép hai dynamic arguments. Cách mã hóa chính xác trong API `StringConcatFactory`:

| Thành phần recipe | Ý nghĩa |
| --- | --- |
| Ký tự **U+0001** | Placeholder cho một **dynamic argument** được truyền vào call site |
| Ký tự **U+0002** | Placeholder cho một **static constant** truyền qua bootstrap arguments |
| Ký tự bình thường khác | Phần văn bản literal được chèn nguyên dạng trong kết quả |

Ví dụ recipe có thể được biểu diễn **bằng ký hiệu dễ đọc** là `name=[U+0001], count=[U+0001]`. Khi xem `javap -v` thực tế, các placeholder có thể được hiển thị như escape sequences chứ **không phải** chuỗi ký tự ngoặc vuông `[U+0001]`. Không suy ra mỗi dấu `+` trong source tương ứng một recipe entry hay một `invokedynamic` riêng.

**Khác biệt cốt lõi với lambda:**

- Lambda bootstrap trả về call site mà target **tạo function object**; sau đó SAM được gọi riêng.
- String-concat bootstrap trả về call site mà target **tính ra String kết quả trực tiếp từ các argument** của lần concat đó.
- Cùng opcode `invokedynamic` nhưng **bootstrap, call-site descriptor, target và sản phẩm đầu ra** khác nhau.

`StringConcatFactory` xuất hiện từ Java 9. Class Java 8 không thể phụ thuộc vào API này trên runtime Java 8; đó là lý do build cho `--release 8` cần lowering tương thích thay vì gọi `StringConcatFactory`.

## 9. Chương trình Java 17 để so sánh hai cách biên dịch

Tạo file độc lập **`StringConcatTranslation.java`**:

```java
public class StringConcatTranslation {
    static String message(String name, int count) {
        return "name=" + name + ", count=" + count;
    }

    static String sum(int a, int b) {
        return "sum=" + (a + b);
    }

    static String maybeNull(Object value) {
        return "item=" + value;
    }

    static String folded() {
        return "constant=" + "A" + 1 + 2;
    }

    public static void main(String[] args) {
        System.out.println(message("Lan", 7));
        System.out.println(sum(2, 3));
        System.out.println(maybeNull(null));
        System.out.println(folded());
    }
}
```

**Kết quả `java StringConcatTranslation`** giống nhau với class được biên dịch cho Java 8 hoặc Java 17, khi được chạy trên runtime phù hợp:

```text
name=Lan, count=7
sum=5
item=null
constant=A12
```

- `"name=" + name + ", count=" + count` thực hiện string conversion cho tham số động, nhưng compiler quyết định chuỗi bytecode để đạt kết quả.
- `"sum=" + (a + b)` tính số học `int` trước khi nối; nếu viết `"sum=" + a + b` sẽ nối tuần tự từ trái sang phải, cho `sum=23` với đầu vào 2 và 3.
- `"item=" + value` với `value == null` cho chuỗi ký tự `null`, không tự động ném `NullPointerException` chỉ vì nối reference null.
- `"constant=" + "A" + 1 + 2` là biểu thức hằng phù hợp; compiler có thể fold thành `"constant=A12"` và trả qua `ldc`, **không cần** `StringBuilder` hay `invokedynamic` cho chính method `folded`.

### Thực hành trên một JDK hiện đại có hỗ trợ hai release đích

Dùng **cùng một `javac`** (ví dụ JDK 17 hoặc 21), biên dịch tuần tự rồi lưu lại disassembly sau mỗi lần build:

```bash
javac -version

javac --release 8 StringConcatTranslation.java
javap -c -v -p StringConcatTranslation > concat-release8.txt
java StringConcatTranslation

javac --release 17 StringConcatTranslation.java
javap -c -v -p StringConcatTranslation > concat-release17.txt
java StringConcatTranslation
```

**Đọc output `javap` đã lưu:**

1. Với target 8, xem method `message`: class file major **52**; bản `javac` thông dụng thể hiện chuỗi `new StringBuilder`, `append` và `toString`.
2. Với target 17, class file major **61**; `message` thường chứa `invokedynamic makeConcatWithConstants` và có mục `BootstrapMethods` trỏ tới `StringConcatFactory`.
3. `sum` ở hai bản vẫn cần tính `a + b` thành một giá trị `int` trước khi concat; mã lệnh có thể xuất hiện `iadd` rồi đến builder hoặc indy.
4. `maybeNull` vẫn phải cho chuỗi `item=null`; chi tiết gọi `String.valueOf`/`StringBuilder.append` hoặc concat target là chuyện compiler/runtime.
5. `folded` có thể chỉ cần `ldc "constant=A12"` rồi `areturn` ở cả hai bản, vì constant folding.
6. Diff giữa hai output không chỉ do logic chương trình: còn có **constant pool indexes, `BootstrapMethods`, class-file version, line tables** và các quyết định riêng của compiler.

**Lưu ý về lệnh:** `--release` là tùy chọn của `javac` hiện đại, không có trong `javac` JDK 8. Khi dùng JDK 8 thật, compiler không nhận `--release 8`; bạn chỉ cần biên dịch như thông thường hoặc dùng flags mà chính compiler đó hỗ trợ. Một JDK mới có thể dần bỏ hỗ trợ target rất cũ, nên kiểm tra `javac --help` của bản đang dùng.

### So sánh “cùng compiler, khác --release” và “khác compiler”

Hai thực nghiệm trả lời hai câu hỏi **khác nhau**:

- Giữ `javac` JDK 17 cố định, đổi `--release 8` sang `--release 17`: đang khảo sát **quy tắc code generation theo target platform** mà compiler ấy hỗ trợ.
- Giữ `--release 17`, thay `javac` JDK 17 bằng `javac` phiên bản mới hơn: đang khảo sát **sự tiến hóa implementation/compiler** cho cùng target platform.

`--release 17` **không giả lập đúng byte-for-byte** output của `javac` JDK 17 khi được chạy bằng JDK khác; nó chủ yếu giới hạn ngôn ngữ, API nền tảng và class-file target. Nếu công cụ phân tích bytecode cần đúng hình dạng, hãy khóa và ghi cả **phiên bản/build của compiler**.

## 10. Phân tích sâu: phân biệt `BootstrapMethods` của lambda và nối chuỗi

Dùng:

```bash
javap -v -p LambdaTranslation
javap -v -p StringConcatTranslation
```

Tìm các mục ở constant pool:

```text
#N = InvokeDynamic    #bootstrapIndex:#nameAndTypeIndex
#X = MethodHandle     REF_invokeStatic ...
#Y = MethodType       ...
#Z = NameAndType      ...
```

Đây là **lược đồ**, indices thực tế khác nhau. Trong `BootstrapMethods` của `LambdaTranslation`:

- Một bootstrap thường trỏ `LambdaMetafactory.metafactory`; arguments gồm SAM method type, implementation method handle và instantiated method type.
- Capture parameter **không nhất thiết xuất hiện dưới dạng static bootstrap constant**; nó có thể là dynamic argument được load lên stack khi `invokedynamic` được thực thi.
- Với method reference `LambdaTranslation::triple`, implementation method handle thường trỏ thẳng tới `triple:(I)I`; với lambda có biểu thức `x + offset`, có thể trỏ tới synthetic helper method.
- Cùng file còn có thể có bootstrap `StringConcatFactory` cho các chuỗi in kết quả, cần phân biệt bằng bootstrap owner.

Trong `StringConcatTranslation` compiled target 17:

- Bootstrap của `message` thường là `StringConcatFactory.makeConcatWithConstants`, với recipe có placeholder cho `name` và `count`.
- Call-site type có thể có hai tham số động `(Ljava/lang/String;I)Ljava/lang/String;`.
- `folded` có thể không có dynamic call site nào vì được constant-fold.
- Không phải mỗi literal String trong recipe là một lời gọi `StringBuilder.append` hoặc một dynamic argument; compiler có thể nhúng literal vào recipe.

### Về lúc bootstrap được gọi

Resolution/linkage của `invokedynamic` có thể được VM thực hiện theo thời điểm phù hợp với đặc tả, thường khi một call site được sử dụng lần đầu. Việc **liên kết call site** không đồng nghĩa bootstrap method phải chạy **ở mỗi lần thực thi** instruction. Sau liên kết, target đã được xác lập cho call site theo quy tắc phù hợp.

Nếu bootstrap method thất bại, lỗi liên kết như `BootstrapMethodError` có thể xuất hiện. Đây khác với một exception mà **body lambda** ném sau khi người dùng gọi SAM, hoặc một exception do `toString()` trên object động phát sinh trong quá trình nối chuỗi.

## 11. Method reference và target type quyết định adapter

Ngoài lambda thông thường, method reference cũng là một **poly expression**: kiểu của nó phụ thuộc **functional interface target** tại vị trí sử dụng.

Ví dụ:

```java
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, Integer> length = String::length;
Supplier<String> greeting = " hello "::trim;
```

Đây là **fragment minh họa**, không phải chương trình độc lập. Với `String::length` ở đây, receiver là **đối số** của `Function.apply`. Với `" hello "::trim`, receiver cụ thể được **capture khi method reference được đánh giá**, và `Supplier.get()` sau đó dùng receiver ấy.

Khi một method reference có kiểu SAM như `Function<String,Integer>`, quá trình liên kết có thể cần boxing/unboxing hoặc method-type adaptation giữa `String.length:()I` và interface `Function.apply:(Ljava/lang/Object;)Ljava/lang/Object;`. `javap` có thể chỉ ra bridge/adapter qua metadata của metafactory; không được suy ra từ generic type ở source rằng bytecode có đúng một method descriptor giống nguyên văn source.

Một mẹo đọc: xác định **SAM descriptor đã erasure**, **implementation MethodHandle**, và **instantiated method type**. Ba thông tin ấy giải thích cách object lambda cung cấp được một method phù hợp giao diện.

## 12. Lambda object không phải anonymous inner class viết bằng source

Hai đoạn Java có thể có cùng mục đích:

```java
Runnable lambda = () -> System.out.println("run");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
```

Đây là **fragment minh họa**. Khi dùng OpenJDK `javac` thông thường:

- Lambda thường được hạ thành một `invokedynamic` liên kết với `LambdaMetafactory`; compiler có thể tạo một helper method cho body.
- Anonymous class là một **class declaration** thực sự trong Java source, thường tạo thêm class file như `Outer$1.class`, với constructor và method `run()`.
- Trong lambda, từ khóa `this` theo lexical scope chỉ **đối tượng bao quanh** (nếu có); trong anonymous class, `this` chỉ **instance anonymous class**. Đây là khác biệt **ngữ nghĩa**, không thể quyết định chỉ từ việc cả hai cùng implement `Runnable`.
- Một non-capturing lambda có thể được tái sử dụng object khi được đánh giá nhiều lần; không nên áp đặt số lần cấp phát từ một benchmark hoặc heap dump lên JLS contract.
- Compiler được phép chọn biểu diễn khác cho lambda miễn duy trì ngữ nghĩa; vì vậy không xây công cụ trên giả định luôn có file class với tên dạng `$$Lambda$...`.

Cách so sánh bytecode đúng là quan sát **method chứa biểu thức**, **BootstrapMethods** và **các class files phát sinh** trong chính build đang phân tích, chứ không đồng nhất mọi function object với anonymous class.

## 13. Điều gì thuộc bảo đảm của JLS, điều gì là chi tiết compiler/runtime?

| Phát biểu | Phân loại | Cách dựa vào nó |
| --- | --- | --- |
| Lambda phải tương thích functional-interface target type và quy tắc effectively final | **JLS contract** | Có thể dùng làm quy tắc kiểm tra đúng/sai source |
| `applyAsInt(4)` phải cung cấp kết quả đúng của implementation lambda | **Hợp đồng ngôn ngữ/API** | Có thể viết test kết quả và lỗi |
| `javac` sinh method tên `lambda$main$0` | **Chi tiết code generation** | Chỉ dựa khi kiểm thử một compiler/build đã khóa |
| Mọi lần đánh giá lambda đều tạo object mới | **Không được bảo đảm nói chung** | Không phụ thuộc identity object |
| `invokedynamic` có quy tắc constant pool và bootstrap method | **JVMS contract** | Dùng kiểm tra tính hợp lệ class file |
| Java 8 `javac` dùng chuỗi `StringBuilder.append` | **Mẫu compiler theo phiên bản** | Dùng so sánh class files của compiler ấy |
| Java 9+ `javac` dùng `StringConcatFactory` theo JEP 280 | **Lựa chọn code generation phổ biến** | Xác minh bằng `javap` trên build thực |
| Một constant expression có thể được compiler gộp sẵn | **Quy tắc Java về constant expressions + lựa chọn sinh code** | Không đếm opcode theo số toán tử `+` |
| Bootstrap call site được cache/triển khai bằng class nào | **Chi tiết runtime** | Không lấy làm API ổn định |
| String concat với `null` cho literal `null` | **Ngữ nghĩa Java string conversion** | Có thể viết test theo giá trị kết quả |

Một class file hợp lệ có thể chạy cùng một kết quả trên nhiều JVM nhưng có hiệu năng, số object hoặc machine-code khác nhau. Trái lại, hai file class khác nhau hoàn toàn về `StringBuilder`/`invokedynamic` vẫn có thể cùng tuân theo ngữ nghĩa source Java.

## 14. Lỗi thực tế khi nâng JDK và công cụ phân tích bytecode

**1. Instrumentation tìm `StringBuilder.append` rồi bị “mất dấu” nối chuỗi.** Khi chuyển compiler target 8 → 17, concat có thể thành `invokedynamic`. Công cụ bytecode analysis phải hỗ trợ cả hai mẫu hoặc theo dõi ý nghĩa động qua bootstrap, thay vì giả định số lệnh `append` không đổi.

**2. Công cụ chỉ nhìn opcode `invokedynamic` mà không đọc bootstrap.** Nó có thể nhầm lambda factory với string concat; phải xem `CONSTANT_InvokeDynamic_info`, `NameAndType`, `BootstrapMethods` và owner như `LambdaMetafactory` hay `StringConcatFactory`.

**3. Compiler mới sinh class-file version không được runtime cũ hỗ trợ.** Ví dụ Java 17 class-file major 61 không chạy trực tiếp trên JVM Java 8; lỗi `UnsupportedClassVersionError` là vấn đề phiên bản runtime/classfile, không phải “lambda lỗi”.

**4. Cố chạy class tham chiếu `StringConcatFactory` trên Java 8.** API này chỉ có từ Java 9; một class file hoặc tool tự tạo tham chiếu nó không thể kỳ vọng liên kết trên runtime Java 8. Dùng đúng target và chạy test trên runtime hỗ trợ.

**5. Dùng `-source 8 -target 8` rồi nghĩ đã giới hạn API.** Khi build với `javac` mới, hai flags này không thay thế hoàn toàn `--release 8` về kiểm tra API nền tảng. Với môi trường hỗ trợ, `--release` phù hợp hơn cho cross-compilation.

**6. Tin rằng Java 17 source bắt buộc luôn chứa StringConcatFactory trong class file.** Nếu biểu thức concat là constant expression, compiler có thể fold; nếu code viết rõ `new StringBuilder()`, compiler không bị buộc thay source đó thành concat indy.

**7. Thấy method `lambda$...` và gọi trực tiếp vào nó từ thư viện khác.** Nó là chi tiết compiler (thường private/synthetic), không phải public API ổn định; tên/ký hiệu có thể đổi khi biên dịch lại.

**8. Bắt lỗi từ code chạy và nhầm với `BootstrapMethodError`.** Nếu lambda body ném `IllegalArgumentException` sau khi gọi SAM, đó không mặc định là lỗi bootstrap; phân biệt **call-site linkage** với **target execution**.

**9. Suy số lượng lambda objects từ số lệnh indy.** Một call site có thể được thực thi nhiều lần và runtime có quyền tái sử dụng instances trong trường hợp phù hợp; allocation/lifetime không suy trực tiếp từ instruction count.

**10. Đọc `javap` mà bỏ qua compiler flags.** Compiler options, debug info, optimization, vendor và target release có thể thay đổi bytecode offsets, synthetic members, constant-pool indices hoặc bootstrap entries. Lưu thông tin toolchain cùng artifact phân tích.

## 15. Quy trình kiểm tra một class file có lambda và string concat

1. **Ghi môi trường:** `javac -version`, `java -version`, `--release`, bản build, `gradle/maven` toolchain và JAR đã thực thi.
2. **Xác nhận class major:** `javap -v ClassName`; ví dụ Java 8 → 52, Java 17 → 61.
3. **Tìm call site:** `javap -c -v -p ClassName`; lọc từng `invokedynamic` theo **method chứa instruction**.
4. **Tra constant pool:** ở index `#N`, kiểm tra loại `InvokeDynamic` và NameAndType descriptor.
5. **Lần sang `BootstrapMethods`:** ghi owner/method của bootstrap, các method types, implementation handles, recipes, constants.
6. **Với lambda:** xem capture arguments trước `invokedynamic`; xem body helper hoặc method reference target; tìm `invokeinterface` ở nơi SAM được gọi.
7. **Với string concat:** tìm thành phần dynamic đưa lên stack, recipe U+0001/U+0002 hoặc builder chain, kiểm tra constant folding và thứ tự phép tính.
8. **So sánh hai builds:** đảm bảo dùng đúng file class sau mỗi lần compile, không nhìn nhầm cached build output; diff disassembly theo ý nghĩa chứ không chỉ theo `#index`.
9. **Chạy test hành vi:** kết quả, ngoại lệ và side effects theo JLS/API quan trọng hơn việc bytecode trông giống kỳ vọng.
10. **Đối chiếu đặc tả đúng phiên bản:** chỉ nâng hành vi từ “quan sát compiler” thành quy tắc chung nếu thực sự được JLS/JVMS/API bảo đảm.

### Checklist câu hỏi tự kiểm tra

- `invokedynamic` ở chỗ lambda tạo **function object** hay thực hiện một phép **string concatenation**?
- Method reference có capture receiver không? Lambda có capture biến effectively final không?
- `LambdaMetafactory` nhận SAM type, implementation handle và instantiated type nào?
- `StringConcatFactory` nhận call-site argument types, recipe và static constants nào?
- Biểu thức nối chuỗi có constant-fold được không? Dấu ngoặc có đổi phép cộng số học thành nối chuỗi sớm không?
- Mục tiêu chạy Java 8 hay Java 17? `--release` có giới hạn API/classfile phù hợp không?
- Đoạn bytecode mình trích là JVMS bắt buộc hay một lựa chọn của compiler được dùng tại thời điểm build?
- Công cụ bytecode/agent có hiểu `BootstrapMethods`, `invokedynamic` và class-file major version không?

## Tài liệu tham chiếu

- [JLS Java SE 17 `15.27` — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): target typing, lambda semantics, capture.
- [JLS Java SE 17 `15.13` — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): bound/unbound method references và runtime evaluation.
- [JLS Java SE 17 `15.18.1` — String Concatenation Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1): string conversion và ngữ nghĩa toán tử `+`.
- [JVMS Java SE 17 `4.4.10` — `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): cấu trúc constant pool cho dynamic call sites.
- [JVMS Java SE 17 `4.7.23` — `BootstrapMethods` attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23): bootstrap method handles và static arguments.
- [JVMS Java SE 17 `5.4.3.6` — Dynamically-Computed Call Site and Constant Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): linkage bootstrap.
- [JVMS Java SE 17 `6.5` — `invokedynamic` instruction](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic): operand stack và instruction semantics.
- [`LambdaMetafactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): metafactory và altMetafactory cho lambda/method reference.
- [`StringConcatFactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html): makeConcat, makeConcatWithConstants và recipe U+0001/U+0002.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): lý do chuyển chiến lược sinh bytecode sang invokedynamic từ Java 9.
- [`javac` và `javap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) / [`javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): `--release` và cách quan sát class file.

**Ghi nhớ:** Lambda trong `javac` hiện đại thường tạo **function object qua `invokedynamic + LambdaMetafactory`**, sau đó caller gọi SAM; String `+` trên target Java 9+ thường tính **kết quả String qua `invokedynamic + StringConcatFactory`**, thay cho builder chain điển hình ở target Java 8. **Bootstrap method và descriptor mới cho biết call site làm gì; compiler/version mới cho biết tại sao một source lại ra hình dạng bytecode ấy.**
