# 11.2 Cấu trúc constant pool, tên điểm gọi, method descriptor và `BootstrapMethods`

Lệnh bytecode `invokedynamic` của Java không trỏ trực tiếp đến một method thuộc class cố định như `invokestatic` hay `invokevirtual`. Thay vào đó, nó trỏ tới một **mô tả điểm gọi động** (dynamic call site) trong `constant_pool` của class file. Mô tả ấy cho biết **tên điểm gọi** (invocation name), **kiểu lời gọi** (method descriptor) và **mục trong bảng `BootstrapMethods`** mà JVM phải dùng để liên kết (link) lời gọi tới một `CallSite`.

Bốn mảnh ghép cần phân biệt:

1. **Bytecode `invokedynamic`:** lệnh gọi có operand trỏ tới một mục trong constant pool.
2. **`CONSTANT_InvokeDynamic_info`:** mục constant pool chứa chỉ số bootstrap-method record và chỉ số `NameAndType`.
3. **`CONSTANT_NameAndType_info`:** nơi lưu **tên ký hiệu điểm gọi** và **JVM method descriptor**.
4. **`BootstrapMethods` attribute:** bảng của **class file**, chứa method-handle đến bootstrap method và danh sách các đối số tĩnh (static arguments) của nó.

Khi liên kết, JVM truyền thông tin về caller, tên và kiểu lời gọi cùng các static arguments cho bootstrap method. Bootstrap method trả một `java.lang.invoke.CallSite`; target của call site xác định code được chạy ở điểm gọi đó. Hiểu cấu trúc này giúp bạn đọc được `javap -v`, giải thích lambda/method reference và tối ưu string concatenation, cũng như gỡ lỗi liên kết động mà không nhầm lẫn giữa **tên site**, **tên bootstrap method** và **tên method đích**.

> **Phiên bản:** Ví dụ Java biên dịch bằng `javac --release 17` và chạy với JDK 17+. Việc compiler tạo ra bao nhiêu điểm gọi `invokedynamic` và index `#n` trong `javap` là chi tiết build/toolchain; các ví dụ đã được kiểm thử, nhưng **index không phải giao diện ổn định** để hard-code. Nội dung cấu trúc dựa trên JVMS và API `java.lang.invoke` của Java SE 21.

## 1. `invokedynamic` khác các lời gọi bytecode thông thường ở đâu?

Với lời gọi thông thường như `invokestatic`, operand trỏ đến một symbolic method reference, mang tên class/interface sở hữu, tên method và descriptor. JVM giải quyết tham chiếu này theo quy tắc liên kết method.

Với `invokedynamic`:

```text
Bytecode in một method:
    ... đẩy giá trị đối số lên operand stack ...
    invokedynamic #7, 0
    ... dùng kết quả ...

#7 = CONSTANT_InvokeDynamic
        |
        +-- bootstrap_method_attr_index --> BootstrapMethods[0]
        |                                     |
        |                                     +-- bootstrap method handle
        |                                     +-- static arguments [...]
        |
        +-- name_and_type_index -----------> CONSTANT_NameAndType
                                              |
                                              +-- name: "makeConcatWithConstants"
                                              +-- descriptor: (String,int)String

Khi liên kết thành công:
    bootstrap(...) -> CallSite -> target MethodHandle
    invokedynamic  -> gọi target theo descriptor đã liên kết
```

Sơ đồ trên là **minh họa mô hình**, với tên/mô tả kiểu được rút gọn cho dễ đọc; constant-pool index và bootstrap index cần lấy từ class file thực tế của bạn.

Các điểm khác biệt cốt lõi:

- `CONSTANT_InvokeDynamic` **không có trường chỉ đến class sở hữu method đích** như `CONSTANT_Methodref`. Bootstrap method sẽ quyết định hành vi lời gọi.
- `NameAndType` là tên/descriptor **của call site**, không nhất thiết là tên của một method Java tồn tại trong lớp nguồn.
- JVM vẫn **kiểm soát kiểu**: `CallSite` do bootstrap trả về phải có kiểu tương ứng với method descriptor đã khai báo ở điểm gọi động.
- Sau khi liên kết, mỗi **lệnh `invokedynamic` cụ thể** được gắn với kết quả liên kết của chính nó. Một constant-pool entry có thể được nhiều lệnh dùng chung, nhưng JVMS vẫn xử lý liên kết theo từng vị trí lệnh.
- `invokedynamic` không có nghĩa **mỗi lần gọi đều chạy bootstrap**. Bootstrap phục vụ liên kết; sau đó lời gọi được thực hiện qua target của call site.

## 2. Constant pool trong class file: các loại entry liên quan

`constant_pool` là bảng các cấu trúc có tag trong `ClassFile`, đánh chỉ số bắt đầu từ **1**. Nhiều mục chỉ lưu **index sang mục khác**, vì vậy đọc một entry thường phải lần theo chuỗi tham chiếu. Khi `javap -v` hiển thị `#7`, đó là **chỉ số constant pool**; còn chỉ số `#0` trong chú thích của `InvokeDynamic #0:#8` thường là **bootstrap_methods array index**, không phải constant pool index 0.

| Entry | Tag | Vai trò trong cấu trúc `invokedynamic` |
| --- | --- | --- |
| `CONSTANT_Utf8_info` | 1 | Lưu chuỗi tên, descriptor, tên attribute, recipe hoặc tên thành phần liên quan |
| `CONSTANT_Class_info` | 7 | Mô tả lớp/interface theo tên; có thể dùng ở bootstrap arguments |
| `CONSTANT_String_info` | 8 | Tham chiếu hằng `String`, ví dụ recipe cho nối chuỗi |
| `CONSTANT_NameAndType_info` | 12 | Cặp **name** và **descriptor** của call site |
| `CONSTANT_MethodHandle_info` | 15 | Tham chiếu tới một method/field với reference kind; dùng biểu diễn **bootstrap method handle** hoặc impl handle |
| `CONSTANT_MethodType_info` | 16 | Descriptor của một kiểu phương thức; thường làm static argument cho lambda metafactory |
| `CONSTANT_Dynamic_info` | 17 | **Hằng số động** (`condy`), không phải một lời gọi động |
| `CONSTANT_InvokeDynamic_info` | 18 | Mô tả **điểm gọi động** và liên kết tới `BootstrapMethods` + `NameAndType` |

Các mục kiểu `Methodref`/`InterfaceMethodref` (tag 10/11) cũng có thể xuất hiện **gián tiếp** qua một `CONSTANT_MethodHandle` đến bootstrap hoặc implementation method. Không phải bản thân `InvokeDynamic` có `class_index` giống `Methodref`.

### 2.1. Cấu trúc binary của `CONSTANT_InvokeDynamic_info`

Theo JVMS, dạng dữ liệu:

```text
CONSTANT_InvokeDynamic_info {
    u1 tag;                         // 18
    u2 bootstrap_method_attr_index; // chỉ số trong BootstrapMethods.bootstrap_methods[]
    u2 name_and_type_index;         // chỉ số CONSTANT_NameAndType_info
}
```

Đây là **mô tả cấu trúc class file**, không phải mã Java để biên dịch. `u1` là một byte không dấu; `u2` là hai byte không dấu.

- `tag = 18` nhận diện một `CONSTANT_InvokeDynamic`.
- `bootstrap_method_attr_index` là **chỉ số 0-based** trong mảng `bootstrap_methods` thuộc attribute `BootstrapMethods` của cùng class file.
- `name_and_type_index` là **chỉ số constant pool 1-based hợp lệ**, trỏ tới `CONSTANT_NameAndType_info` có method descriptor.

Trường `bootstrap_method_attr_index` **không** trực tiếp trỏ tới mục `CONSTANT_MethodHandle`. Nó trỏ tới **một record trong attribute**, và record ấy mới chứa `bootstrap_method_ref` trỏ tới `CONSTANT_MethodHandle`.

### 2.2. `CONSTANT_NameAndType_info`

`NameAndType` có cấu trúc:

```text
CONSTANT_NameAndType_info {
    u1 tag;             // 12
    u2 name_index;      // CONSTANT_Utf8_info của tên
    u2 descriptor_index;// CONSTANT_Utf8_info của descriptor
}
```

Ở `invokedynamic`, descriptor phải là **method descriptor**; ở `CONSTANT_Dynamic` (hằng động), descriptor lại là **field descriptor**. Đây là một cách rất nhanh để không nhầm `condy` với một dynamic call site.

Ví dụ:

```text
NameAndType
  name       = "apply"
  descriptor = (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
```

Tên `apply` ở đây **không tự động chỉ đến** method `apply` trên interface `Transformer`. Nó là thông tin được truyền đến `LambdaMetafactory` để tạo hành vi cần thiết; JVM không tự lookup `Transformer.apply` như một lệnh `invokeinterface` chỉ vì tên là `apply`.

### 2.3. `CONSTANT_MethodHandle_info` và `CONSTANT_MethodType_info`

Bootstrap method được biểu diễn bởi một **MethodHandle constant**. Trong `javap -v`, bạn thường thấy:

```text
MethodHandle 6:#...  // REF_invokeStatic ...metafactory:(...)CallSite
```

Số `6` ở đây là `reference_kind` biểu thị `REF_invokeStatic`, khác với bootstrap index hoặc CP tag. Nó chỉ cách method handle tham chiếu tới method mà JVM có thể gọi.

`MethodType` constant lại chứa **một method descriptor**, không phải code executable. Trong `LambdaMetafactory.metafactory`, các `MethodType` thường mô tả SAM method type và instantiated method type; static argument `MethodHandle` trỏ tới implementation method. Cần phân biệt các **method descriptor ở nhiều tầng**: kiểu method bootstrap, kiểu call site và kiểu method được lambda triển khai.

## 3. `BootstrapMethods` nằm ở đâu và chứa gì?

`BootstrapMethods` là **attribute ở cấp `ClassFile`**, không phải entry `CONSTANT_InvokeDynamic` và cũng không phải method bytecode bình thường. Class file có tối đa một attribute `BootstrapMethods`; khi constant pool chứa `CONSTANT_InvokeDynamic` hoặc `CONSTANT_Dynamic` thì class file phải cung cấp attribute này theo định dạng tương ứng.

Cấu trúc rút gọn:

```text
BootstrapMethods_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 num_bootstrap_methods;
    {
        u2 bootstrap_method_ref;
        u2 num_bootstrap_arguments;
        u2 bootstrap_arguments[num_bootstrap_arguments];
    } bootstrap_methods[num_bootstrap_methods];
}
```

Đây là cấu trúc file theo JVMS, **không** phải class Java. Những thành phần quan trọng:

- `attribute_name_index`: constant-pool index của chuỗi UTF-8 `"BootstrapMethods"`.
- `num_bootstrap_methods`: số record trong bảng bootstrap.
- `bootstrap_method_ref`: CP index đến `CONSTANT_MethodHandle_info` cho bootstrap method.
- `bootstrap_arguments[]`: mảng **constant-pool indexes** cho các static arguments bổ sung; không phải các đối số runtime của lời gọi động.
- Một `CONSTANT_InvokeDynamic` chọn **một record** bằng `bootstrap_method_attr_index`; các record có thể dùng chung cùng một bootstrap method handle nhưng static arguments khác nhau.

Các đối số static được biểu diễn bằng hằng/loại loadable hợp lệ trong constant pool như `String`, số, `Class`, `MethodType`, `MethodHandle` và `CONSTANT_Dynamic` khi hợp lệ. JVM **resolve** chúng thành các giá trị rồi truyền cho bootstrap. Mảng `bootstrap_arguments[]` không phải một chuỗi tùy ý mang tên tham số Java.

### 3.1. Phân biệt ba tầng index trong `javap`

Giả sử bạn thấy kết quả giản lược:

```text
#7 = InvokeDynamic  #0:#8
#8 = NameAndType     #9:#10
...
BootstrapMethods:
  0: #66 REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
```

Ở đây:

- `#7` là **CP entry chứa `InvokeDynamic`**, bytecode `invokedynamic #7, 0` trỏ tới đó.
- `#0` (trong `#0:#8`) là **bootstrap record index 0**, khớp dòng `BootstrapMethods: 0: ...`.
- `#8` là **CP entry của `NameAndType`**, từ đó theo `name_index` và `descriptor_index` tới hai `Utf8`.
- `#66` là CP entry của **bootstrap method handle**; không phải index record `0`.
- Các static arguments (nếu có) xuất hiện **bên dưới** bootstrap record, thường dưới tiêu đề `Method arguments:`.

Chỉ nhìn dòng `#7 = InvokeDynamic` mà không theo sang `NameAndType` và `BootstrapMethods` sẽ thiếu một phần quan trọng của cấu trúc.

## 4. Tên điểm gọi (`invokedName`) có ý nghĩa gì?

Một call site có một **tên ký hiệu (symbolic invocation name)** nằm trong `NameAndType`. Java thường biểu diễn nó dưới dạng `String` gửi đến bootstrap method.

Trong các ví dụ biên dịch thông dụng:

| Cơ chế nguồn Java | Tên call site thường gặp | Bootstrap method thường dùng |
| --- | --- | --- |
| String concatenation `"x=" + x` với javac hiện đại | `makeConcatWithConstants` (hoặc `makeConcat` tùy chiến lược) | `StringConcatFactory.makeConcatWithConstants` hoặc `makeConcat` |
| Lambda `x -> ...` | Tên phương thức SAM như `apply`/`run`, tùy functional interface | `LambdaMetafactory.metafactory` |
| Method reference `Type::method` | Tên phương thức SAM như `applyAsInt` | `LambdaMetafactory.metafactory` |
| Bytecode custom `invokedynamic` | Tên do bytecode producer lựa chọn và hợp lệ theo JVMS | Bootstrap method của framework/language |

**Ba tên không nên đánh đồng:**

1. `invokedName`: từ `CONSTANT_NameAndType`, ví dụ `"apply"`.
2. **Bootstrap method name**: ví dụ `"metafactory"`; lấy từ target của `bootstrap_method_ref`.
3. **Implementation method name**: ví dụ `"lambda$withSuffix$0"` hoặc `"square"`; có thể là static argument dạng `MethodHandle`.

JVM truyền `invokedName` cho bootstrap; bootstrap dùng nó theo hợp đồng riêng. **Tên điểm gọi không buộc JVM tìm một method Java có chính tên đó** trước khi bootstrap chạy.

### 4.1. Với lambda capture, `invokedName` không nói số biến capture

Nếu `withSuffix(String suffix)` trả lambda, bytecode tạo instance của functional interface bằng `invokedynamic`. Tên site có thể là `apply` nhưng **descriptor của site** có tham số `String` mang giá trị `suffix` được capture. Vì vậy cần xem **cả name và descriptor**, không suy số capture từ tên `apply`.

Không nên dựa vào tên `lambda$...` hoặc thứ tự generated synthetic methods: đó là chi tiết của trình biên dịch, không phải một giao thức cho application code.

## 5. JVM method descriptor: ngữ pháp và cách đọc

**Method descriptor** có hình thức:

```text
( ParameterDescriptor* ) ReturnDescriptor
```

Nó ghi kiểu các **giá trị được đặt trên operand stack để đi vào call site** và kiểu kết quả, không ghi tên tham số, annotation, generic type arguments hoặc tên method.

Một số ký hiệu:

| Java type | JVM descriptor |
| --- | --- |
| `void` (chỉ return type) | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| nested `IndyConstantPoolDemo.Transformer` | `LIndyConstantPoolDemo$Transformer;` |

Ví dụ:

```text
(Ljava/lang/String;I)Ljava/lang/String;
       |
       +-- nhận String, int; trả String

()Ljava/util/function/IntUnaryOperator;
       |
       +-- không có đối số; trả IntUnaryOperator

(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
       |
       +-- nhận một String; trả Transformer
```

Ở call site do lambda factory tạo, **kiểu trả về có thể là functional interface**, trong khi method do lambda triển khai lại có kiểu trả về hoàn toàn khác. Với method reference không capture, descriptor của **điểm tạo functional interface object** thường là `()L...Interface;`, dù SAM method nhận tham số và trả giá trị.

**Quan trọng:** descriptor trong `CONSTANT_InvokeDynamic` là **kiểu của lời gọi được phát bằng lệnh `invokedynamic`**. Nó không phải descriptor của bootstrap method. Bootstrap method thường có các tham số metadata `(Lookup, String, MethodType, static arguments...)` và trả `CallSite`, trong khi site cần thực hiện có thể nhận `(String,int)` và trả `String`.

### 5.1. Java `MethodType` và method descriptor

Java API `MethodType` biểu diễn trực tiếp cấu trúc các kiểu tham số/return đã resolve:

```java
// Fragment Java 17+, giả định đã import java.lang.invoke.MethodType.
MethodType mt = MethodType.methodType(
        String.class, String.class, int.class);
String descriptor = mt.toMethodDescriptorString();
// "(Ljava/lang/String;I)Ljava/lang/String;"
```

Đây là **fragment**, không phải chương trình độc lập. `MethodType.fromMethodDescriptorString(...)` có thể parse descriptor với class loader thích hợp. Lưu ý việc parse không tự tạo `CallSite` hoặc phát sinh lệnh `invokedynamic`; nó chỉ xử lý **kiểu**.

### 5.2. Phân biệt method descriptor và generic signature

`(Ljava/util/List;)Ljava/lang/Object;` không chứa `List<String>` hay `List<Integer>`. Thông tin generic, nếu có, được ghi ở `Signature` attribute khác. `CONSTANT_InvokeDynamic` ràng buộc hành vi theo **JVM erased/runtime types**, không phải trực tiếp theo Java generic syntax.

## 6. Từ `invokedynamic` đến bootstrap: luồng liên kết

Xét một lệnh bytecode `invokedynamic #7, 0`, các bước khái niệm:

1. JVM lấy CP index `#7` từ operand của lệnh, tìm `CONSTANT_InvokeDynamic_info`.
2. Từ `name_and_type_index`, JVM lấy **tên** và **method descriptor** của site rồi resolve các kiểu tham số/kiểu trả về thành `MethodType`.
3. Từ `bootstrap_method_attr_index`, JVM tìm record trong `BootstrapMethods`, resolve `CONSTANT_MethodHandle` của bootstrap method.
4. JVM resolve các **static arguments** trong record theo thứ tự để có các object/giá trị dùng tại liên kết.
5. JVM gọi bootstrap method với các đối số tương đương `Lookup` cho **caller class**, `String invokedName`, `MethodType invokedType` và danh sách static arguments.
6. Kết quả phải là `CallSite` **không null**, có kiểu khớp `invokedType`. JVM gắn kết quả này với **lệnh cụ thể**; khi chạy lệnh sẽ sử dụng target của call site.
7. Các lần chạy tiếp theo của **cùng vị trí lệnh đã liên kết** không lặp lại bootstrap để resolve lại site. Với `MutableCallSite` hoặc `VolatileCallSite`, target có thể được thay đổi theo hợp đồng của loại call site đó.

```text
ClassFile constant_pool + BootstrapMethods
             |
             v
  resolve bootstrap handle
  resolve static arguments
  resolve name + descriptor
             |
             v
bootstrap(callerLookup, invokedName, invokedType, ...staticArgs)
             |
             v
    CallSite, type == invokedType ?
        |                   |
       yes                  no
        |                   |
        v                   v
  link this instruction   linkage failure
        |
        v
  invoke CallSite target
```

### 6.1. BSM chạy mỗi lần hay một lần?

Sau khi lệnh được liên kết thành công, việc resolve lại **cùng vị trí bytecode** không gọi lại BSM. Tuy nhiên đừng thiết kế bootstrap method phụ thuộc vào tiền đề "body của BSM chắc chắn chạy đúng một lần":

- Hai thread có thể đồng thời kích hoạt việc resolve một site chưa liên kết; theo JVMS, bootstrap **có thể được thực thi đồng thời**. JVM chọn một kết quả để dùng, những kết quả còn lại bị bỏ qua.
- Hai vị trí lệnh `invokedynamic` có thể cùng trỏ một constant-pool entry nhưng được **liên kết riêng theo từng vị trí lệnh**.
- Bootstrap nên có side effects được kiểm soát và an toàn khi nhiều thread đua tới liên kết.
- `ConstantCallSite` có target cố định; `MutableCallSite` và `VolatileCallSite` phục vụ cơ chế thay target mà không sửa bytecode site.

### 6.2. Điều kiện kiểu và lỗi liên kết

Nếu bootstrap trả `null`, không trả một `CallSite`, hoặc `CallSite.type()` không tương đương method descriptor của site, liên kết thất bại với `BootstrapMethodError`. Exception thường xảy ra từ bootstrap có thể được JVM wrap thành `BootstrapMethodError` (trong khi `Error` và một số linkage errors có quy tắc truyền riêng theo JVMS). Không nên khẳng định mọi lỗi liên kết đều là `BootstrapMethodError`: một số lỗi resolve method handle, class loader hoặc verify bytecode thuộc nhóm linkage khác.

**Chữ ký bootstrap** có dạng điển hình:

```java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        /* 0 hoặc nhiều static arguments */ ...) throws Throwable
```

Đây là **sơ đồ API** chứ không phải Java code biên dịch độc lập. Bootstrap handle được gọi theo `MethodHandle.invokeWithArguments`-style adaptation; nên khai báo thực tế có thể linh hoạt hơn prototype cố định, đặc biệt với varargs. Điều quan trọng là **đối số có thể thích ứng** và **kết quả phải thỏa hợp đồng CallSite**.

## 7. Thực hành 1 — Java thật tạo các `CONSTANT_InvokeDynamic`

Tạo tệp **`IndyConstantPoolDemo.java`**:

```java
public final class IndyConstantPoolDemo {
    @FunctionalInterface
    interface Transformer {
        String apply(String value);
    }

    static String label(String name, int count) {
        return "name=" + name + "; count=" + count;
    }

    static Transformer withSuffix(String suffix) {
        return value -> value + suffix;
    }

    public static void main(String[] args) {
        System.out.println(label("Java", 3));
        Transformer exclaim = withSuffix("!");
        System.out.println(exclaim.apply("ready"));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 IndyConstantPoolDemo.java
java IndyConstantPoolDemo
```

**Stdout chính xác:**

```text
name=Java; count=3
ready!
```

Chương trình này có những tình huống sinh `invokedynamic` với `javac` hiện đại:

- Trong `label`: string concatenation với hai giá trị runtime `name` và `count`.
- Trong `withSuffix`: tạo lambda capture biến `suffix` để triển khai functional interface `Transformer`.
- Trong implementation method do compiler tạo cho lambda: `value + suffix` cũng là string concatenation.

Không phải lời gọi `exclaim.apply("ready")` tự động là opcode `invokedynamic`; lời gọi interface có thể được biên dịch thành `invokeinterface`. Opcode `invokedynamic` ở đây được dùng để **tạo lambda object/functional value** và thực hiện **nối chuỗi**.

### 7.1. Xem constant pool và bytecode bằng `javap`

Chạy:

```bash
javap -v -p IndyConstantPoolDemo
javap -c -p IndyConstantPoolDemo
```

- `-v` (verbose) in constant pool, code và `BootstrapMethods`.
- `-p` hiển thị private/generated implementation method, hữu ích khi xem `lambda$...`.
- `-c` in bytecode instructions và operand refs.

Trong một lần biên dịch bằng `javac --release 17`, các dòng tiêu biểu là:

```text
#7  = InvokeDynamic #0:#8
       // #0:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
#8  = NameAndType   #9:#10
       // makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
#11 = InvokeDynamic #1:#12
       // #1:apply:(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
...
BootstrapMethods:
  0: #66 REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
  1: #72 REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
```

Đây là **trích đoạn rút gọn** từ một bản biên dịch đã kiểm chứng. Các dòng `...` là phần bỏ bớt; index `#7`, `#8`, `#11`, `#66`, `#72` **không được giả định bất biến** giữa JDK/compiler, hoặc khi thay source.

Dấu hiệu quan trọng: `#7 = InvokeDynamic #0:#8` liên kết site ở `label` tới bootstrap record **0**; `#11 = InvokeDynamic #1:#12` liên kết site tạo lambda ở `withSuffix` tới record **1**. Bản biên dịch này còn có bootstrap record **2** dùng `StringConcatFactory` cho phép nối chuỗi trong lambda body. Cùng một bootstrap method factory có thể xuất hiện ở nhiều bootstrap records vì **static arguments khác nhau**.

### 7.2. Tự lần theo entry của phép nối chuỗi

Với `label("Java",3)`:

```text
Source:
  "name=" + name + "; count=" + count

Call-site name:
  makeConcatWithConstants

Call-site descriptor:
  (Ljava/lang/String;I)Ljava/lang/String;

Bootstrap record:
  StringConcatFactory.makeConcatWithConstants
  Static arguments: recipe / hằng dùng để nối chuỗi

Runtime inputs:
  name = "Java", count = 3

Result:
  "name=Java; count=3"
```

Một *recipe* có thể mã hóa các phần literal `"name="`, `"; count="` và vị trí chèn giá trị dynamic bằng ký tự điều khiển theo hợp đồng của `StringConcatFactory`. Recipe là **static argument truyền tới bootstrap**, còn `"Java"` và `3` là **runtime operands** tại mỗi lời gọi site.

Không nhầm `"makeConcatWithConstants"` (tên site) với `StringConcatFactory.makeConcatWithConstants` (bootstrap method được trỏ tới bởi `MethodHandle`). Chúng có thể cùng tên nhưng thuộc **hai mảnh metadata khác nhau**.

### 7.3. Tự lần theo entry của lambda có capture

Với `withSuffix(String suffix)`:

```text
Source:
  return value -> value + suffix;

Call-site name:
  apply

Call-site descriptor:
  (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;

Bootstrap record:
  LambdaMetafactory.metafactory
  Static arguments thông thường:
    SAM MethodType
    implementation MethodHandle
    instantiated MethodType

Runtime operand tại điểm tạo lambda:
  suffix: String

Kết quả của invokedynamic:
  một đối tượng triển khai Transformer

Khi gọi functional interface sau đó:
  transformer.apply(value: String) -> String
```

Chú ý chữ ký site `(String)Transformer` khác hẳn chữ ký SAM `(String)String`. Tham số `String` của site là **biến được capture**; kiểu trả về `Transformer` là **functional interface object được tạo**. Chữ ký của implementation method có thể nhận `(suffix, value)` với tên do compiler sinh, nhưng đó **không phải** type của site dùng để tạo lambda.

`LambdaMetafactory` nhận metadata về SAM, implementation method handle và instantiated type để tạo adapter đúng hợp đồng. Bạn đọc được các static arguments này ở dưới `BootstrapMethods: 1:` trong `javap -v`.

## 8. Thực hành 2 — Method reference không capture

Tạo tệp **`NonCapturingIndyDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public final class NonCapturingIndyDemo {
    static int square(int value) {
        return value * value;
    }

    static IntUnaryOperator operation() {
        return NonCapturingIndyDemo::square;
    }

    public static void main(String[] args) {
        IntUnaryOperator op = operation();
        System.out.println("square: " + op.applyAsInt(6));
    }
}
```

```bash
javac --release 17 NonCapturingIndyDemo.java
java NonCapturingIndyDemo
javap -v -p NonCapturingIndyDemo
```

**Stdout của chương trình Java (không tính output của lệnh `javap`):**

```text
square: 36
```

Ở method `operation()`, `javap -v` có entry `InvokeDynamic` với dạng site:

```text
applyAsInt:()Ljava/util/function/IntUnaryOperator;
```

Không có tham số capture, nên phần trong ngoặc của descriptor trống. Trong khi đó, **SAM method** `IntUnaryOperator.applyAsInt(int)` nhận một `int` và trả `int`; implementation method `square(int)` cũng nhận/đưa ra `int`.

Đừng hiểu `()IntUnaryOperator` là “`square` không nhận tham số”. Đây là **chữ ký tại điểm tạo functional object**, không phải chữ ký của operation khi dùng đối tượng đó. Cũng không được kết luận mọi method reference đều có descriptor `()Interface`: method reference **có receiver capture** hoặc có context khác có thể có các tham số site.

Trong ví dụ này, `System.out.println("square: " + ...)` còn có thể làm compiler phát thêm một `StringConcatFactory` site. Khi đếm `InvokeDynamic` trong class file, hãy phân biệt **lambda/method-reference site** và **string-concat site**.

## 9. Phân biệt bootstrap static arguments với runtime arguments

Đây là chỗ nhiều người đọc `javap` bị nhầm.

### 9.1. Static arguments có sẵn từ class file

Các static arguments được mã hóa bằng constant-pool references từ `BootstrapMethods.bootstrap_arguments[]`. Ví dụ:

- `StringConcatFactory.makeConcatWithConstants` nhận recipe và có thể thêm các hằng như string/class token;
- `LambdaMetafactory.metafactory` nhận `MethodType` của SAM, `MethodHandle` implementation và instantiated `MethodType`.

Các dữ liệu này giúp bootstrap quyết định **cách tạo target**. Chúng không phải values do người gọi `label("Java",3)` hoặc `withSuffix("!")` truyền tại runtime.

### 9.2. Runtime arguments được đặt trên operand stack

Sau khi liên kết, một lần chạy của `invokedynamic` lấy **n đối số theo descriptor** từ operand stack. Ví dụ:

```text
call site: (String,int)String
runtime stack arguments: "Java", 3
bootstrap static recipe: "name=...; count=..."
                         ^ không phải argument mà caller truyền tại runtime
```

Với lambda capture:

```text
call site: (String)Transformer
runtime argument: suffix = "!"
bootstrap static args: SAM type, impl handle, instantiated type
```

Cả hai nhóm có thể chứa object kiểu `String` hoặc `MethodType`, nhưng vị trí sử dụng khác nhau. Muốn debug "giá trị nào thay đổi mỗi lần gọi", hãy bắt đầu từ descriptor và các lệnh chuẩn bị operand stack; muốn debug "điểm gọi được tạo ra như thế nào", hãy xem `BootstrapMethods`.

## 10. Prototype bootstrap method và hợp đồng `CallSite`

Bootstrap method điển hình có ba đối số metadata đầu tiên:

| Tham số | Giá trị JVM cung cấp | Mục đích |
| --- | --- | --- |
| `MethodHandles.Lookup caller` | Lookup với ngữ cảnh class chứa `invokedynamic` | Resolve thành phần với quyền phù hợp của caller |
| `String invokedName` | Tên từ `CONSTANT_NameAndType` | Ký hiệu để bootstrap diễn giải |
| `MethodType invokedType` | Type được resolve từ method descriptor | Hợp đồng kiểu target phải đáp ứng |
| `... staticArgs` | Các static arguments từ `BootstrapMethods` | Hints, recipe, implementation handles, constants |

Bootstrap trả một `CallSite`, chẳng hạn:

- `ConstantCallSite`: target cố định sau khi cấu hình; phù hợp phép nối chuỗi/lambda mà target không được thay.
- `MutableCallSite`: target có thể thay, có quy tắc đồng bộ/xem thấy riêng.
- `VolatileCallSite`: thay target theo semantics tương ứng volatile.

Nhìn từ bên ngoài, `CallSite.type()` là kiểu của target mà JVM kỳ vọng ở **đúng call site**. Mọi candidate target phải có kiểu thích hợp với site; nếu logic thực hiện nhận kiểu khác, bootstrap có thể dùng adapter `MethodHandle.asType` hoặc combinators theo các phép chuyển đổi được phép.

### 10.1. Ví dụ bootstrap method *được gọi thủ công* để hiểu contract

Tạo tệp **`BootstrapContractDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class BootstrapContractDemo {
    private static String prepend(String prefix, String value) {
        return prefix + value;
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String invokedName,
                                     MethodType invokedType,
                                     String prefix) throws Throwable {
        if (!invokedName.equals("decorate")) {
            throw new IllegalArgumentException("Unexpected call-site name");
        }
        MethodHandle original = caller.findStatic(
                BootstrapContractDemo.class, "prepend",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle target = MethodHandles.insertArguments(original, 0, prefix);
        if (!target.type().equals(invokedType)) {
            throw new IllegalArgumentException("Incompatible target type");
        }
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodType descriptor = MethodType.methodType(
                String.class, String.class);
        CallSite site = bootstrap(MethodHandles.lookup(),
                "decorate", descriptor, "ID:");
        System.out.println("descriptor: " + descriptor.toMethodDescriptorString());
        System.out.println("target type: " + site.getTarget().type());
        System.out.println("call: " + (String) site.dynamicInvoker().invokeExact("A7"));
    }
}
```

```bash
javac --release 17 BootstrapContractDemo.java
java BootstrapContractDemo
```

**Stdout chính xác:**

```text
descriptor: (Ljava/lang/String;)Ljava/lang/String;
target type: (String)String
call: ID:A7
```

**Điểm cần hiểu đúng:** Chương trình trên **gọi `bootstrap(...)` trực tiếp bằng mã Java** để kiểm chứng bộ tham số `(Lookup, name, type, static argument)` và kết quả `CallSite`. Nó **không** yêu cầu compiler tạo ra một `invokedynamic` trỏ tới method `BootstrapContractDemo.bootstrap`. Bản thân code ghép chuỗi trong `prepend` vẫn có thể được compiler phát thành `invokedynamic` dùng `StringConcatFactory`, nhưng đó là **một site khác**.

Trong một class file tùy biến có `invokedynamic` thực sự dùng bootstrap này, `BootstrapMethods.bootstrap_method_ref` cần trỏ tới `BootstrapContractDemo.bootstrap` với static argument `"ID:"`; site có thể có tên `"decorate"` và descriptor `(Ljava/lang/String;)Ljava/lang/String;`. JVM sẽ thực hiện quy trình liên kết thay cho lời gọi thủ công của `main`.

### 10.2. Đọc ví dụ bootstrap thủ công

- `invokedName == "decorate"` minh họa việc bootstrap **có thể diễn giải** tên site; JVM không tự gọi method tên `decorate`.
- `invokedType` là `(String)String`; `findStatic` tìm method `prepend(String,String)String`.
- `insertArguments(original, 0, "ID:")` gắn prefix, làm target mới có type `(String)String`.
- `new ConstantCallSite(target)` cung cấp callable phù hợp type site.
- `site.dynamicInvoker().invokeExact("A7")` gọi target và trả `"ID:A7"`.
- Trong ví dụ, người viết tự ném `IllegalArgumentException` khi metadata không hợp lệ; nếu một bootstrap thực sự bị JVM gọi và không đáp ứng hợp đồng liên kết, JVM thực thi quy tắc lỗi linkage nêu ở mục 6.2.

Ví dụ này đủ để kiểm tra **kiểu và thành phần dữ liệu bootstrap**, nhưng để thấy bytecode `invokedynamic` thật, hãy dựa vào ví dụ 7–8 hoặc công cụ phát sinh class file/bytecode chuyên dụng có kiểm soát.

## 11. So sánh ba descriptor hay bị trộn lẫn

Một class có lambda có thể chứa **ba hoặc nhiều** method descriptors. Mỗi descriptor phục vụ một lớp trừu tượng khác:

| Descriptor | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;` | `NameAndType` của `CONSTANT_InvokeDynamic` tại `withSuffix` | Một `String suffix` vào; trả về một `Transformer` |
| `(Ljava/lang/String;)Ljava/lang/String;` | `CONSTANT_MethodType` static args của `LambdaMetafactory` | SAM/instantiated signature `apply(String):String` |
| `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;` | MethodHandle impl target / generated method | Method triển khai có thể nhận `suffix` và `value` |
| `(Lookup,String,MethodType,MethodType,MethodHandle,MethodType)CallSite` | Descriptor của method bootstrap `LambdaMetafactory.metafactory` (viết tắt kiểu) | API liên kết, không phải runtime signature của lambda |

Không dùng bootstrap method descriptor để xác định số đối số thực tế của `Transformer.apply(...)`. Không dùng descriptor của generated implementation method để thay thế descriptor site `invokedynamic`. Mỗi tầng có input/output riêng.

### 11.1. Với phép nối chuỗi cũng có hai chữ ký

`StringConcatFactory.makeConcatWithConstants` thường nhận metadata và một recipe; nó là **bootstrap**. Call-site descriptor của `label` là **`(String,int)String`**. Nếu đặt bootstrap descriptor vào chỗ `NameAndType` của site, JVM sẽ kỳ vọng caller truyền `Lookup`, `String`, `MethodType`, recipe... ở mỗi lần chạy, hoàn toàn sai.

### 11.2. MethodType static argument không phải "class" runtime của lambda

`CONSTANT_MethodType` được dùng như static argument để truyền một **chữ ký**, không phải địa chỉ của class triển khai lambda. JVM/runtime có thể tạo lớp ẩn hoặc cơ chế implementation khác tùy compiler/runtime; đừng xây công cụ phụ thuộc vào tên lớp triển khai lambda hoặc giả định có một tệp `.class` ổn định tương ứng mỗi lambda.

## 12. Phân biệt `CONSTANT_Dynamic` (condy) và `CONSTANT_InvokeDynamic`

Hai tag có hình dạng thông tin giống nhau: bootstrap index + name-and-type index. Nhưng bản chất khác:

| Thuộc tính | `CONSTANT_InvokeDynamic` (tag 18) | `CONSTANT_Dynamic` (tag 17) |
| --- | --- | --- |
| Được dùng cho | **Điểm gọi động** | **Hằng số được tính động** |
| Descriptor trong `NameAndType` | **Method descriptor**: `(args)Result` | **Field descriptor**: một loại `Result` |
| Bytecode thường tham chiếu | `invokedynamic` | `ldc` / `ldc_w` / `ldc2_w` khi hợp lệ |
| Metadata thứ ba cho bootstrap | `MethodType` | `Class` của hằng cần tạo |
| Kết quả bootstrap | `CallSite` với type phù hợp | Một giá trị có type phù hợp |
| Lúc sử dụng | Invoke target method handle | Load hằng đã resolve |

Cả hai có thể tham chiếu cùng attribute `BootstrapMethods` của class file, nhưng **không phải cùng một cơ chế runtime**. Một số `bootstrap_arguments[]` còn có thể dẫn đến hằng `CONSTANT_Dynamic` được resolve trước khi bootstrap của call site nhận nó.

Đừng gọi mọi dòng có chữ `Dynamic` trong `javap` là một site `invokedynamic`. Hãy đọc chính xác tag và descriptor.

## 13. Kịch bản gỡ lỗi với `javap -v`

Khi cần giải thích một lời gọi động kỳ lạ trong file `.class`:

1. **Tìm opcode** `invokedynamic #n, 0` trong phần code của method; ghi rõ class và method chứa lệnh.
2. **Tìm constant pool entry `#n`** để xác định tag `InvokeDynamic`, bootstrap index và `NameAndType` index.
3. **Theo `NameAndType`** để ghi tên điểm gọi và descriptor; đọc từng tham số từ trái sang phải, đọc return type sau `)`.
4. **Theo `BootstrapMethods[index]`** để tìm method-handle `REF_...` của bootstrap và số/danh sách static arguments. Không đọc nhầm bootstrap index như CP index.
5. **Phân biệt static arguments và runtime operands**: static từ `BootstrapMethods`; runtime từ bytecode chuẩn bị stack trước `invokedynamic`.
6. **Với lambda**, kiểm tra `LambdaMetafactory` cùng SAM MethodType, implementation MethodHandle và instantiated MethodType; đừng dùng descriptor site để mô tả SAM.
7. **Với string concat**, kiểm tra `StringConcatFactory` và recipe (nếu hiện); đừng cho rằng chuỗi literal và các đối số runtime nằm chung một bảng.
8. **Khi báo lỗi linkage**, đọc cả exception/cause, class loader, module boundaries, method type và khả năng BSM bị gọi đồng thời.
9. **Khi so sánh hai bản build**, đừng diff bằng CP index một cách máy móc. So khớp opcode, name, descriptor, bootstrap target, static args và call-site semantics.
10. **Khi cần xác minh**, chạy lớp với cùng JDK/classpath/module path mà bạn đang phân tích, thay vì chỉ dựa vào giả định về compiler.

### 13.1. Ví dụ đọc một call site lambda theo chuỗi tham chiếu

```text
Code trong withSuffix:
   invokedynamic #11, 0

constant_pool[#11]:
   InvokeDynamic bootstrap=1, name_and_type=#12

constant_pool[#12]:
   NameAndType "apply":
       (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;

BootstrapMethods[1]:
   bootstrap = LambdaMetafactory.metafactory
   static args = [SAM MethodType, impl MethodHandle, instantiated MethodType]

Runtime call-site arguments:
   suffix:String

Runtime call-site result:
   Transformer
```

**Trên sơ đồ:** Các số `#11`, `#12` và `1` là ví dụ từ build đã kiểm chứng, không phải ABI stable. Mục đích là cách **lần theo liên kết**.

### 13.2. Vì sao Reflection không đủ để tìm `invokedynamic`?

`Class.getDeclaredMethods()` cho biết các method được khai báo/được compiler sinh trên class runtime, nhưng **không liệt kê từng lệnh `invokedynamic`** bên trong `Code` attribute của method. Để khảo sát opcode, constant-pool graph và `BootstrapMethods` attribute, hãy dùng `javap -v -p` hoặc công cụ phân tích bytecode/class file. Một bootstrap method có thể là method Java bình thường và xuất hiện trong Reflection, nhưng điều đó không tạo API Reflection ánh xạ tự động tới mọi site dùng nó.

## 14. Các lỗi hiểu sai thường gặp

1. **Nghĩ `CONSTANT_InvokeDynamic` giữ một `class_index` đến target method** — sai; nó giữ bootstrap index và `NameAndType` index.
2. **Nhầm `#0` trong `InvokeDynamic #0:#8` với constant pool entry `#0`** — sai; `#0` là chỉ số mảng bootstrap, CP index bắt đầu từ 1.
3. **Nghĩ tên site `"apply"` là tên method JVM tự tìm** — sai; nó là symbolic name được truyền cho bootstrap.
4. **Nghĩ tên site, tên bootstrap và tên implementation luôn giống nhau** — sai; lambda có thể dùng `apply`, `metafactory` và `lambda$withSuffix$0`.
5. **Nghĩ descriptor site chính là descriptor SAM** — sai khi lambda capture; `(String)Transformer` khác `(String)String`.
6. **Nghĩ `BootstrapMethods` là một entry trong constant pool** — sai; đó là class-level attribute, nhưng nó chứa index tới CP MethodHandle và các static arguments.
7. **Nghĩ `BootstrapMethods.bootstrap_arguments[]` chứa giá trị runtime `"Java"` và `3` của mỗi lần gọi** — sai; đây là static arguments chuẩn bị khi liên kết.
8. **Nghĩ mỗi lần chạy `invokedynamic` đều gọi lại BSM** — sai sau liên kết thành công của cùng vị trí bytecode; nhưng BSM vẫn có thể chạy đồng thời ở đợt liên kết đầu.
9. **Nghĩ hai site dùng cùng CP entry chắc chắn chia sẻ một lần liên kết** — không đúng; JVMS gắn kết quả với từng vị trí `invokedynamic`.
10. **Nghĩ `CallSite` có thể trả target với method type bất kỳ** — sai; type của site phải tương đương descriptor đã khai báo.
11. **Nghĩ source có lambda thì mọi method call tới lambda đều là opcode `invokedynamic`** — không đúng; `invokedynamic` thường dùng tạo functional object, rồi lời gọi SAM có thể là `invokeinterface`.
12. **Nghĩ `CONSTANT_Dynamic` cũng luôn trả `CallSite`** — sai; condy tạo một hằng, bootstrap nhận kiểu `Class` cho hằng.
13. **Nhìn index `#n` từ máy khác rồi hard-code** — compiler, JDK, optimization và sửa source có thể thay index; đọc lại `javap`.
14. **Coi prototype BSM gọi thủ công là đã tạo một bytecode `invokedynamic` riêng** — không; cần đúng instruction + CP entry + `BootstrapMethods` trong class file.
15. **Bỏ qua class loader và quyền Lookup** — việc resolve static argument class, impl method handle và bootstrap target có thể thất bại dù name/descriptor nhìn có vẻ đúng.
16. **Cho rằng `MutableCallSite` khiến bootstrap chạy lại ở mỗi lần đổi target** — sai; target mutation khác với liên kết lại.
17. **Coi mọi build `javac` đều phát phép cộng chuỗi bằng cùng một factory/recipe** — không bảo đảm giữa compiler, cờ biên dịch hoặc phiên bản toolchain.
18. **Nhầm output của `javap` là Java source** — `#7 = InvokeDynamic` và `BootstrapMethods` là mô tả bytecode/class file, không phải khai báo Java có thể copy vào method body.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Trong `CONSTANT_InvokeDynamic_info`, hai trường `u2` sau `tag` là gì? Chúng lần lượt trỏ đến đâu?

**Câu 2.** Trong `#7 = InvokeDynamic #0:#8`, ba con số 7, 0, 8 thuộc những không gian index nào?

**Câu 3.** `BootstrapMethods` là CP entry hay class-level attribute? Một record của nó chứa những gì?

**Câu 4.** Tại sao tên site `apply` và descriptor `(String)Transformer` không chứng minh implementation lambda có chữ ký `apply(String):Transformer`?

**Câu 5.** Với `withSuffix("!")`, đối số `"!"` là runtime operand hay static bootstrap argument?

**Câu 6.** Trong `StringConcatFactory.makeConcatWithConstants`, recipe nằm ở đâu, và các giá trị `name/count` nằm ở đâu?

**Câu 7.** Bootstrap thông thường nhận ba tham số metadata gì trước các static arguments? Nó phải trả kiểu kết quả nào cho `invokedynamic`?

**Câu 8.** Một bootstrap trả `CallSite` với target type `(int)String`, nhưng descriptor site là `(String)String`. Kết quả hợp lệ không?

**Câu 9.** Nếu hai lệnh `invokedynamic` cùng trỏ tới một CP entry, có nhất thiết chỉ có một lần resolve chung cho cả hai vị trí lệnh không?

**Câu 10.** `CONSTANT_Dynamic` khác `CONSTANT_InvokeDynamic` ở descriptor và kiểu kết quả bootstrap như thế nào?

**Câu 11.** Có thể dùng `Class.getDeclaredMethods()` để lấy danh sách mọi `invokedynamic` instruction trong method body không? Nên dùng công cụ gì?

**Câu 12.** Bootstrap có thể được chạy đồng thời bởi nhiều thread không? Kết quả nào được JVM dùng?

### Đáp án gợi ý

1. `bootstrap_method_attr_index` trỏ record `BootstrapMethods`; `name_and_type_index` trỏ CP `NameAndType`.
2. `7` là CP index của `InvokeDynamic`; `0` là bootstrap record index; `8` là CP index của `NameAndType`.
3. Class-level attribute; record có `bootstrap_method_ref` và danh sách `bootstrap_arguments`.
4. Vì site tạo **functional interface object** từ captured `String`; SAM và impl có descriptors riêng trong static args.
5. Runtime operand được truyền khi site tạo functional object; không nằm trong bảng static args.
6. Recipe là static bootstrap argument; `name/count` là runtime operands của site `(String,int)String`.
7. `Lookup caller`, `String name`, `MethodType type`; kết quả là `CallSite` có type đúng descriptor.
8. Không; type không khớp, JVM từ chối liên kết (thường `BootstrapMethodError`).
9. Không; theo JVMS, liên kết được áp dụng theo từng vị trí lệnh `invokedynamic`.
10. `Dynamic` chứa field descriptor, bootstrap nhận `Class` của hằng và tạo giá trị; `InvokeDynamic` chứa method descriptor và tạo `CallSite`.
11. Không; dùng `javap -v -p`, `javap -c -p` hoặc trình phân tích bytecode.
12. Có thể trong đợt resolve ban đầu; JVM chọn một kết quả, bỏ qua kết quả thua cuộc.

## 16. Tài liệu chuẩn để đối chiếu

- [JVMS Java SE 21 — `4.4 The Constant Pool` và `4.4.10 CONSTANT_Dynamic / CONSTANT_InvokeDynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10): cấu trúc tag 17/18, bootstrap index và NameAndType index.
- [JVMS Java SE 21 — `4.7.23 BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23): attribute cấp class, bootstrap method handle và static arguments.
- [JVMS Java SE 21 — `4.3.3 Method Descriptors`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): cú pháp `(parameters)return`.
- [JVMS Java SE 21 — `5.4.3.6 Dynamic Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6): chuẩn bị bootstrap args, resolve, kiểm tra `CallSite`, concurrent linkage.
- [JVMS Java SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic): operand instruction và liên kết với site.
- [Java SE 21 API — `java.lang.invoke` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html): hợp đồng bootstrap, method handles, call sites và dynamic constants.
- [Java SE 21 API — `CallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html), [`MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html), [`StringConcatFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html), [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): kiểu target và các bootstrap factory thực tế.

**Ghi nhớ:** Đọc `invokedynamic` theo thứ tự **opcode → `CONSTANT_InvokeDynamic` → `NameAndType` (tên + descriptor) và `BootstrapMethods` (bootstrap handle + static arguments) → `CallSite`**. Phân biệt đúng ba tầng **site name**, **call-site descriptor** và **bootstrap method/arguments** là chìa khóa để hiểu tại sao lambda, method reference và string concatenation cùng dùng một cơ chế bytecode nhưng có hành vi runtime rất khác nhau.